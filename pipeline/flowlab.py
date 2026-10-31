"""Money flow lab (beta 2) — experimental money flows beside the Industries page's estimated money flow, and "where each
dollar goes" for every company.

Built from what pipeline/ioflow_beta.py has already worked out for each company (its BEA split, US share, supplying
industries, capital spending by asset mix) plus the company's own cash-flow statement (pipeline/capital.py, the Capital
allocation tab). It never changes the published view (gamma/io/) or Beta 1.1 (gamma/io-beta/).

    data/gamma/flowlab/<key>.json      one industry level (a SIC code, "sic2-NN", "sector-<id>"), four views:
        cash      filed cash flow: where the cash came from (operating cash flow, borrowing, shares, sales of assets,
                  cash on hand) and where it went (capital spending, acquisitions, buybacks, dividends, debt repaid,
                  cash kept) — every band a filed figure (grade A), nothing estimated
        people    pay & benefits, followed further: the estimated pay (Beta 1.1) split as US employers pay (wages,
                  health insurance, pensions, social insurance — BEA NIPA), and the wages as US households use them
                  (taxes, then spending by BLS Consumer Expenditure shares, and saving) — a national-average model (D)
        tiers     the supply chain two steps up: purchased inputs → the industries that supply them (tier 1) → what
                  those suppliers in turn spend it on: their own suppliers (tier 2), imports, their employees, taxes,
                  and what is left to them. Each tier is part of the money before it, never added on top
        capex     capital spending by asset type (structures, equipment, software & IT, other), then the industries
                  that build and sell those assets (BEA fixed assets), imports, and what is spent outside the US
    data/flowlab/c/<cik>.json          one company: every dollar it spent over the last four quarters — suppliers,
                                       employees, taxes, capital spending, acquisitions, shareholders, lenders — and
                                       where each of those goes next
    data/flowlab/index.json            what was built, what was held back and why

Evidence grades on every band: A filed figure · B computed from filed figures · C industry average (input-output
tables) applied to filed figures · D national-average model (not this company's or industry's own records).
Checks before a view is written: every node passes on what it receives (to 0.1%), and nothing comes out of nowhere.
"""
import datetime as dt
import json
import os
from collections import defaultdict

VERSION = "lab-2.0"
TOL = 0.001
TOP_IND, TOP_TIER2, TOP_CO_SUP = 12, 14, 8
GRADES = {"A": "Filed figure (SEC financial statements)", "B": "Computed from filed figures",
          "C": "Industry average (input-output tables) applied to filed figures",
          "D": "National-average model — not this company's or industry's own records"}

# ---- how US employers pay: BEA NIPA, 2025 (Table 7.8 supplements; wage and salary disbursements, Table 2.1/FRED A576RC1)
#      wages ≈ $12.9T; employer health insurance $1,226.5B; pension and other benefit funds $605.3B (pension & insurance
#      funds $1,831.8B less health); employer contributions for government social insurance $888.1B
PAY = [("wages", "Wages & salaries", 0.8259), ("health", "Employer health insurance", 0.0785),
       ("pension", "Employer pensions & other benefits", 0.0388), ("social", "Employer Social Security, Medicare & unemployment tax", 0.0568)]
PAY_SRC = "BEA NIPA 2025: wages and salaries ≈ $12.9T; supplements (Table 7.8): health insurance $1,226B, pension and other funds $605B, employer social insurance $888B"
PAY_TO = {"health": ("r:insurers", "Health insurers & plans"), "pension": ("r:funds", "Pension & benefit funds"),
          "social": ("r:gov_social", "Government — social insurance")}
# ---- how wages are used: employee payroll tax (6.2% Social Security below the cap + 1.45% Medicare ≈ 7% on average),
#      income taxes (personal current taxes ≈ 12–13% of personal income, BEA NIPA Table 2.1), saving ≈ 4.5% of take-home
#      (personal saving rate), the rest spent as BLS Consumer Expenditure Survey 2024 (all consumer units, $78,535), less
#      "personal insurance and pensions" (mostly the payroll tax taken above)
WAGE_TAX = [("payroll", "Employee payroll tax (Social Security, Medicare)", 0.07), ("income", "Income taxes (federal, state)", 0.13)]
SAVING = 0.045
CEX = [("housing", "Housing", 26266), ("transport", "Transportation", 13318), ("food", "Food", 10169), ("healthcare", "Healthcare", 6197),
       ("entertainment", "Entertainment", 3609), ("charity", "Cash contributions", 2292), ("apparel", "Apparel & services", 2001),
       ("education", "Education", 1569), ("other", "Personal care, alcohol, reading & other", 3317)]
CEX_SRC = "BLS Consumer Expenditures 2024 (released Dec 2025): average annual spending by category, all consumer units"
WAGE_SRC = ("payroll tax: statutory 6.2% + 1.45%, about 7% of all wages with the Social Security cap; income taxes: personal current "
            "taxes ≈ 12–13% of personal income (BEA NIPA Table 2.1); saving: personal saving rate ≈ 4.5% (BEA)")

CASH_IN = {"ocf": "Operating cash flow", "borrow": "Net borrowing", "stock": "Shares issued", "sales": "Sales of assets & businesses",
           "nci": "Partners' money in", "inv_other": "Other investing (in)", "fin_other": "Other financing (in)",
           "cash": "Cash drawn from the balance sheet", "fx": "Exchange-rate gains on cash", "unrec": "Not reconciled (in)"}
CASH_OUT = {"capex": "Capital spending", "realestate": "Real estate bought", "acq": "Acquisitions", "buyback": "Buybacks",
            "div": "Dividends", "withhold": "Taxes paid on employees' shares", "borrow": "Net debt repaid", "nci": "Paid to partners",
            "inv_other": "Other investing (out)", "fin_other": "Other financing (out)", "cash": "Cash added to the balance sheet", "stock": "Shares issued (net out)", "sales": "Asset sales (net out)",
            "ocf": "Operating cash outflow", "fx": "Exchange-rate losses on cash", "unrec": "Not reconciled (out)"}
CASH_COLOR = {"capex": "#7b6aa8", "acq": "#8c6bb1", "realestate": "#8c6bb1", "buyback": "#2e8b57", "div": "#3f9e6a", "withhold": "#6fae8a",
              "borrow": "#b0563d", "nci": "#9a8f7a", "cash": "#4f7fa8", "ocf": "#5d7fa3", "stock": "#c08a3e", "sales": "#9aa6b2"}


def asset_class(code):
    """BEA commodity → the kind of capital asset bought."""
    if code.startswith("23"):
        return "structures", "Structures (construction)"
    if code[:4] in ("5112", "5415", "5182", "5191") or code.startswith("518") or code.startswith("519"):
        return "software", "Software & IT"
    if code[:2] in ("33", "42", "44", "45", "48", "49") or code[:2] == "4B" or code.startswith("336"):
        return "equipment", "Equipment (incl. dealer & freight margins)"
    return "other", "Other assets & services"


class Doc:
    """A Sankey view: nodes [id, col, label, color, grade], links [source, target, value, grade, note index]."""

    def __init__(self, cols):
        self.cols, self.nodes, self.links, self.notes, self._n, self._l = cols, [], [], [], {}, {}

    def node(self, id_, col, label, color, grade):
        if id_ not in self._n:
            self._n[id_] = len(self.nodes)
            self.nodes.append([id_, col, label, color, grade])

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)
        return self.notes.index(text)

    def link(self, s, t, v, grade, note):
        if not v or v <= 0:
            return
        k = (s, t)
        if k in self._l:
            self.links[self._l[k]][2] += v
            return
        self._l[k] = len(self.links)
        self.links.append([s, t, v, grade, self.note(note)])

    def check(self):
        """[] when money is conserved: each middle node passes on what it receives; every link joins known nodes."""
        ins, outs = defaultdict(float), defaultdict(float)
        bad = []
        for s, t, v, *_ in self.links:
            if s not in self._n or t not in self._n:
                bad.append(f"link {s}→{t} to an unknown node")
            outs[s] += v
            ins[t] += v
        total = sum(v for s, t, v, *_ in self.links if self.nodes[self._n[s]][1] == 0) if self.links else 0
        for n in self.nodes:
            i, o = ins.get(n[0], 0.0), outs.get(n[0], 0.0)
            if i > 0 and o > 0 and abs(i - o) > TOL * max(total, 1.0):
                bad.append(f"{n[2]}: receives {i:.0f}, passes on {o:.0f}")
        return bad

    def out(self, **kw):
        for l in self.links:
            l[2] = round(l[2], 2)
        used = {x for l in self.links for x in l[:2]}
        return {"cols": self.cols, "nodes": [n for n in self.nodes if n[0] in used], "links": self.links, "notes": self.notes, **kw}


# ------------------------------------------------------------------ helpers on one company's beta record
def cash_period(rec):
    """The company's latest cash-flow period: trailing twelve months, else its last fiscal year (pipeline/capital.py)."""
    if (rec.get("currency") or "USD") != "USD":
        return None
    cap = ((rec.get("quality") or {}).get("cap")) or {}
    p = cap.get("ttm") or ((cap.get("fy") or [None])[-1])
    if not p or not p.get("items"):
        return None
    return {"label": p.get("label"), "end": p.get("end"), "kind": p.get("kind"), "items": p["items"]}


def pay_split(d, src, col, amount, grade_in, note_in, to_house=True):
    """Pay → how US employers pay it (wages, health, pensions, social insurance) → (optionally) how wages are used."""
    for k, label, sh in PAY:
        d.node("p:" + k, col, label, "#9a8f7a" if k == "wages" else "#b0a68f", "D")
        d.link(src, "p:" + k, amount * sh, "D", f"{label}: {sh:.1%} of US employee compensation — {PAY_SRC}")
        if k in PAY_TO and to_house:
            tid, tl = PAY_TO[k]
            d.node(tid, col + 1, tl, "#a7a196", "D")
            d.link("p:" + k, tid, amount * sh, "D", f"{label} paid to {tl.lower()}")
    if not to_house:
        return
    w = amount * PAY[0][2]
    for k, label, sh in WAGE_TAX:
        d.node("h:" + k, col + 1, label, "#a08a5a", "D")
        d.link("p:wages", "h:" + k, w * sh, "D", f"{label}: {sh:.0%} of wages — {WAGE_SRC}")
    home = w * (1 - sum(sh for *_, sh in WAGE_TAX))
    d.node("h:save", col + 1, "Saving", "#2e8b57", "D")
    d.link("p:wages", "h:save", home * SAVING, "D", f"Saving: {SAVING:.1%} of take-home pay — {WAGE_SRC}")
    tot = sum(x for *_, x in CEX)
    for k, label, x in CEX:
        d.node("h:" + k, col + 1, label, "#7f97b3", "D")
        d.link("p:wages", "h:" + k, home * (1 - SAVING) * x / tot, "D",
               f"{label}: {x / tot:.1%} of household spending (personal insurance & pensions left out: mostly the payroll tax) — {CEX_SRC}")


# ------------------------------------------------------------------ industry views
def view_cash(members):
    d = Doc(["Came from", "Cash moved", "Where it went"])
    d.node("pool", 1, "Cash moved", "#5f7d99", "A")
    n, labels = 0, set()
    for m, fl in members:
        cp = (fl.get("x") or {}).get("cash")
        if not cp:
            continue
        n += 1
        labels.add(cp.get("label") or "")
        for k, v in cp["items"].items():
            g = "B" if k in ("inv_other", "fin_other", "unrec") else "A"
            if v > 0:
                d.node("in:" + k, 0, CASH_IN.get(k) or k.replace("_", " ").capitalize() + " (in)", CASH_COLOR.get(k, "#8a96a3"), g)
                d.link("in:" + k, "pool", v, g, "the companies' cash-flow statements (SEC XBRL), latest four quarters or fiscal year")
            elif v < 0:
                d.node("out:" + k, 2, CASH_OUT.get(k) or k.replace("_", " ").capitalize() + " (out)", CASH_COLOR.get(k, "#8a96a3"), g)
                d.link("pool", "out:" + k, -v, g, "the companies' cash-flow statements (SEC XBRL), latest four quarters or fiscal year")
    if not n:
        return None
    return d, {"companies": n, "of": len(members)}


def view_people(members, io):
    d = Doc(["Employee pay", "How employers pay it", "Where it goes next"])
    us = sum(fl["spend"].get("employees", 0.0) for _, fl in members)
    abroad = sum(fl["spend"].get("employees_out", 0.0) for _, fl in members)
    if us <= 0:
        return None
    d.node("e:us", 0, "Employees — US (estimate)", "#9a8f7a", "C")
    pay_split(d, "e:us", 1, us, "C", "")
    if abroad > 0:
        d.node("e:out", 0, "Employees — outside the US (estimate)", "#b0a68f", "C")
        d.node("p:abroad", 1, "Pay abroad (not split: no comparable table)", "#c9c2b3", "C")
        d.link("e:out", "p:abroad", abroad, "C", "employee pay outside the US, Beta 1.1 (FIGARO / ADB multi-country tables)")
    return d, {"us": us, "abroad": abroad}


def tier_split(d, io, by_ind, src_of, col, grade="C"):
    """Tier-1 industries (receiving by_ind) → their own suppliers (tier 2), imports, employees, taxes, what is left."""
    I = io["industries"]
    t2 = defaultdict(float)
    va = defaultdict(float)
    edges = []
    for i, v in by_ind.items():
        if i not in I:
            va["unsplit"] += v
            edges.append((i, "unsplit", v))
            continue
        x = I[i]
        inter, comp, tax = x["inter"], x["comp"], x["tax"]
        s = inter + comp + tax
        if s > 1:
            inter, comp, tax = inter / s, comp / s, tax / s
        norm = (sum(x["suppliers"].values()) + x["imports"]) or 1.0     # the published shares are rounded
        for j, sh in x["suppliers"].items():
            t2[j] += v * inter * sh / norm
            edges.append((i, "t2:" + j, v * inter * sh / norm))
        for k, a in (("imports", v * inter * x["imports"] / norm), ("comp", v * comp), ("tax", v * tax), ("left", v * max(0.0, 1 - inter - comp - tax))):
            va[k] += a
            edges.append((i, k, a))
    top = [j for j, _ in sorted(t2.items(), key=lambda kv: -kv[1]) if j != "_OTHER"][:TOP_TIER2]
    names = {"imports": ("Imports", "#c9a77a"), "comp": ("Suppliers' employees", "#9a8f7a"), "tax": ("Suppliers' taxes on production", "#a08a5a"),
             "left": ("Left to the suppliers (operating surplus)", "#2e8b57"), "unsplit": ("Not split further", "#c9c2b3")}
    for i, k, a in edges:
        if a <= 0:
            continue
        sid = src_of(i)
        if k.startswith("t2:"):
            j = k[3:]
            tid = "t2:" + j if j in top else "t2:other"
            d.node(tid, col, (I[j]["name"] if j in I else "Other industries") + " (tier 2)" if j in top else "Other industries (tier 2)", "#88a3c0", grade)
            d.link(sid, tid, a, grade, "each tier-1 industry's own purchases × its input mix (BEA Use table): part of the money it received, not added on top")
        else:
            nm, color = names[k]
            d.node("v:" + k, col, nm, color, grade)
            d.link(sid, "v:" + k, a, grade, "each tier-1 industry's receipts split as BEA's Use table splits its output: intermediate inputs (domestic → tier 2, imported), "
                   "employee compensation, taxes on production, and the rest (gross operating surplus)")


def view_tiers(members, io):
    I = io["industries"]
    by_ind = defaultdict(float)
    imports = 0.0
    for _, fl in members:
        for (c, i), v in fl["sup"].items():
            if c == "purchases":
                by_ind[i] += v
        imports += fl["imports"].get("purchases", 0.0)
    if not by_ind:
        return None
    d = Doc(["Purchases", "Tier 1: supplying industries", "Tier 2: what the suppliers spend it on"])
    d.node("k:p", 0, "Purchased inputs — US (estimate)", "#5d7fa3", "C")
    top = [i for i, _ in sorted(by_ind.items(), key=lambda kv: -kv[1]) if i != "_OTHER"][:TOP_IND]
    folded = defaultdict(float)
    for i, v in by_ind.items():
        tid = "t1:" + (i if i in top else "other")
        d.node(tid, 1, I[i]["name"] if i in top else "Other industries", "#7f97b3", "C")
        d.link("k:p", tid, v, "C", "purchased inputs × the industry's input mix (BEA Use table), domestic part")
        folded[i] += v
    if imports > 0:
        d.node("t1:imports", 1, "Imports", "#c9a77a", "C")
        d.link("k:p", "t1:imports", imports, "C", "each commodity's imported share (BEA Use table)")
    tier_split(d, io, folded, lambda i: "t1:" + (i if i in top else "other"), 2)
    return d, {"tier1": sum(by_ind.values()), "imports": imports}


def view_capex(members, io):
    I = io["industries"]
    cls, by_ind, imp, out_us, filed = defaultdict(float), defaultdict(float), 0.0, 0.0, 0.0
    for _, fl in members:
        filed += fl["capex"]
        for (c, i), v in fl["sup"].items():
            if c == "capex":
                by_ind[i] += v
        imp += fl["imports"].get("capex", 0.0)
        out_us += fl.get("capex_out", 0.0)
    if filed <= 0:
        return None
    d = Doc(["Capex", "Kind of asset (estimate)", "Who builds and sells it"])
    d.node("cx", 0, "Capital spending (filed)", "#7b6aa8", "A")
    top = [i for i, _ in sorted(by_ind.items(), key=lambda kv: -kv[1]) if i != "_OTHER"][:TOP_IND + 4]
    for i, v in by_ind.items():
        k, lab = asset_class(i) if i != "_OTHER" else ("other", "Other assets & services")
        cls[k] += v
        d.node("a:" + k, 1, lab, "#8c6bb1", "C")
        tid = "s:" + (i if i in top else "other")
        d.node(tid, 2, I[i]["name"] if i in top else "Other industries", "#88a3c0", "C")
        d.link("a:" + k, tid, v, "C", "BEA fixed assets: investment by industry and asset type, domestic part")
    for k, v in cls.items():
        d.link("cx", "a:" + k, v, "C", "capital spending (US share) × the industry's asset mix (BEA fixed assets)")
    if imp > 0:
        d.node("a:imports", 1, "Imported equipment & software", "#c9a77a", "C")
        d.link("cx", "a:imports", imp, "C", "the imported share of each asset (BEA)")
    if out_us > 0:
        d.node("a:abroad", 1, "Spent outside the US (not split)", "#a3a6ad", "B")
        d.link("cx", "a:abroad", out_us, "B", "capital spending × the 10-K's share of revenue outside the US")
    return d, {"filed": filed, "classes": dict(cls), "imports": imp, "abroad": out_us}


# ------------------------------------------------------------------ one company: every dollar it spent
def company_doc(m, fl, io):
    I = io["industries"]
    x = fl.get("x") or {}
    cp = x.get("cash")
    items = (cp or {}).get("items") or {}
    d = Doc(["Spent", "On what", "Where it goes next"])
    d.node("all", 0, "Everything spent", "#5f7d99", "B")
    sp = fl["spend"]
    cost_f = f"revenue × {fl['fin']:.0%} (typical expense ratio of lenders and insurers)" if fl.get("fin") else "revenue − operating income − D&A"
    us_f = f", × {fl['us']:.0%} US share (10-K)" if fl.get("geo") else ""
    # operating spending in the US, by BEA
    pur = sp.get("purchases", 0.0)
    if pur > 0:
        d.node("k:pur", 1, "Suppliers — US (estimate)", "#5d7fa3", "C")
        d.link("all", "k:pur", pur, "C", f"({cost_f}{us_f}) × {fl['coef']['inter']:.1%} purchased-input share (BEA Use table)")
        by = defaultdict(float)
        for (c, i), v in fl["sup"].items():
            if c == "purchases":
                by[i] += v
        top = [i for i, _ in sorted(by.items(), key=lambda kv: -kv[1]) if i != "_OTHER" and i in I][:TOP_CO_SUP]
        for i, v in by.items():
            tid = "s:" + (i if i in top else "other")
            d.node(tid, 2, I[i]["name"] if i in top else "Other supplying industries", "#88a3c0", "C")
            d.link("k:pur", tid, v, "C", "the industry's input mix (BEA Use table), domestic part")
        imp = fl["imports"].get("purchases", 0.0)
        if imp > 0:
            d.node("s:imports", 2, "Imports", "#c9a77a", "C")
            d.link("k:pur", "s:imports", imp, "C", "each input's imported share (BEA Use table)")
    emp = sp.get("employees", 0.0)
    if emp > 0:
        d.node("k:emp", 1, "Employees — US (estimate)", "#9a8f7a", "C")
        d.link("all", "k:emp", emp, "C", f"({cost_f}{us_f}) × {fl['coef']['comp']:.1%} employee-compensation share (BEA Use table)")
        pay_split(d, "k:emp", 2, emp, "C", "", to_house=False)
    tx = sp.get("taxes", 0.0)
    if tx > 0:
        d.node("k:ptax", 1, "Taxes on production — US (estimate)", "#a08a5a", "C")
        d.link("all", "k:ptax", tx, "C", f"({cost_f}{us_f}) × {fl['coef']['tax']:.1%} (BEA Use table): property, sales and excise taxes, licences")
    for k in ("purchases_out", "employees_out", "taxes_out", "other_out", "outside"):
        v = sp.get(k, 0.0)
        if v > 0:
            lab = {"purchases_out": "Suppliers — outside the US (estimate)", "employees_out": "Employees — outside the US (estimate)",
                   "taxes_out": "Taxes on production — outside the US (estimate)", "other_out": "Employees & other costs — outside the US",
                   "outside": "Costs outside the US (not split)"}[k]
            d.node("k:" + k, 1, lab, "#8a8f98", "C" if k != "outside" else "B")
            d.link("all", "k:" + k, v, "C" if k != "outside" else "B", "operating spending outside the US: Beta 1.1, multi-country input-output tables (FIGARO, ADB)"
                   if k != "outside" else f"({cost_f}) × the share of revenue earned outside the US (10-K)")
    # capital spending, as filed, by kind of asset
    capex = fl.get("capex") or 0.0
    if capex > 0:
        d.node("k:capex", 1, "Capital spending (filed)", "#7b6aa8", "A")
        d.link("all", "k:capex", capex, "A", "purchases of property, plant and equipment over four quarters (SEC XBRL)")
        cls = defaultdict(float)
        for (c, i), v in fl["sup"].items():
            if c == "capex":
                cls[asset_class(i) if i != "_OTHER" else ("other", "Other assets & services")] += v
        for (k, lab), v in cls.items():
            d.node("a:" + k, 2, lab, "#8c6bb1", "C")
            d.link("k:capex", "a:" + k, v, "C", "the industry's asset mix (BEA fixed assets: investment by industry and asset type)")
        if fl["imports"].get("capex", 0.0) > 0:
            d.node("a:imports", 2, "Imported equipment & software", "#c9a77a", "C")
            d.link("k:capex", "a:imports", fl["imports"]["capex"], "C", "each asset's imported share (BEA)")
        if fl.get("capex_out", 0.0) > 0:
            d.node("a:abroad", 2, "Spent outside the US (not split)", "#a3a6ad", "B")
            d.link("k:capex", "a:abroad", fl["capex_out"], "B", "capital spending × the share of revenue outside the US (10-K)")
    # income tax, from the income statement
    it = x.get("tax")
    if it and it > 0:
        d.node("k:itax", 1, "Income taxes", "#a08a5a", "B")
        d.link("all", "k:itax", it, "B", "income tax expense over four quarters (income statement; cash paid can differ)")
    # from the cash-flow statement: acquisitions, shareholders, lenders
    per = f"cash-flow statement, {cp['label']}" if cp else ""
    for k, lab, col in (("acq", "Acquisitions", "#8c6bb1"), ("realestate", "Real estate bought", "#8c6bb1")):
        v = -(items.get(k) or 0.0)
        if v > 0:
            d.node("k:" + k, 1, lab, col, "A")
            d.link("all", "k:" + k, v, "A", per)
    sh = {k: -(items.get(k) or 0.0) for k in ("div", "buyback", "withhold")}
    if sum(v for v in sh.values() if v > 0) > 0:
        d.node("k:holders", 1, "Shareholders", "#2e8b57", "A")
        for k, lab in (("div", "Dividends"), ("buyback", "Buybacks"), ("withhold", "Taxes paid on employees' shares")):
            if sh[k] > 0:
                d.link("all", "k:holders", sh[k], "A", per)
                d.node("h:" + k, 2, lab, "#3f9e6a", "A")
                d.link("k:holders", "h:" + k, sh[k], "A", per)
    debt = -(items.get("borrow") or 0.0)
    if debt > 0:
        d.node("k:debt", 1, "Lenders (net debt repaid)", "#b0563d", "A")
        d.link("all", "k:debt", debt, "A", per + " — borrowing less repayments, shown net")
    bad = d.check()
    total = sum(l[2] for l in d.links if l[0] == "all")
    if bad or total <= 0:
        return None, bad or ["nothing spent"]
    rev = fl["revenue"]
    return d.out(cik=m["cik"], ticker=m["ticker"], name=m["name"], sic=m["sic"], total=round(total, 2), revenue=round(rev, 2),
                 end=fl["end"], form=fl.get("form"), doc=fl.get("doc"), cash=(cp or {}).get("label"), us=fl.get("us"),
                 geo=(fl.get("geo") or {}).get("text"), fin=bool(fl.get("fin")), how=fl.get("how") or [],
                 grades=GRADES, version=VERSION), None


# ------------------------------------------------------------------ build
def build(out, rec_all, io, groups):
    """rec_all: [(member, beta record)] from pipeline/ioflow_beta.py; groups: {key: (title, level, [(member, record)])}."""
    root = os.path.join(out, "gamma", "flowlab")
    croot = os.path.join(out, "flowlab", "c")
    os.makedirs(root, exist_ok=True)
    os.makedirs(croot, exist_ok=True)
    held, written = [], 0
    for key, (title, level, members) in groups.items():
        views, why = {}, {}
        for name, fn in (("cash", lambda: view_cash(members)), ("people", lambda: view_people(members, io)),
                         ("tiers", lambda: view_tiers(members, io)), ("capex", lambda: view_capex(members, io))):
            try:
                r = fn()
            except Exception as e:                                  # noqa: BLE001 — one view must not stop the rest
                why[name] = f"error: {type(e).__name__}: {e}"
                continue
            if not r:
                continue
            d, meta = r
            bad = d.check()
            if bad:
                why[name] = bad[:3]
                continue
            views[name] = d.out(meta=meta)
        if why:
            held.append({"key": key, "views": why})
        if not views:
            continue
        doc = {"key": key, "title": title, "level": level, "companies": len(members),
               "revenue": round(sum(fl["revenue"] for _, fl in members), 2), "views": views, "grades": GRADES, "version": VERSION,
               "sources": {"pay": PAY_SRC, "households": CEX_SRC, "wages": WAGE_SRC, "bea_year": io["year"], "scale_year": io["scale_year"]}}
        with open(os.path.join(root, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        written += 1
    cos, cheld = 0, []
    for m, fl in rec_all:
        try:
            doc, bad = company_doc(m, fl, io)
        except Exception as e:                                      # noqa: BLE001
            doc, bad = None, [f"error: {type(e).__name__}: {e}"]
        if not doc:
            cheld.append({"cik": m["cik"], "why": (bad or [])[:2]})
            continue
        with open(os.path.join(croot, f"{int(m['cik'])}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        cos += 1
    with open(os.path.join(out, "flowlab", "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "levels": written, "companies": cos, "held": held[:200], "companies_held": cheld[:200]}, f, separators=(",", ":"))
    print(f"money flow lab: {written} industry levels, {cos} companies ({len(cheld)} held back), {len(held)} levels with a view held back")
    return written, cos
