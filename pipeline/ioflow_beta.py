"""Money flow Beta 1.0 — a test version of the Industries page's "Estimated money flow (BEA input-output)" that keeps
what the filings say apart from what is estimated, and says where every band comes from.

Built next to pipeline/ioflow.py, which it reuses and never changes: writes data/gamma/io-beta/<key>.json and
data/gamma/io-beta/index.json, read by the page web/beta/money-flow.html. The published view (gamma/io/) is untouched.

What changes against the published view
  - two layers: figures from the filings (revenue, operating income, D&A, capital spending, operating cash flow, free
    cash flow) are shown as such; the BEA split (purchased inputs, employees, taxes on production, imports) is labelled
    an estimate, with a range
  - "Operating cash left over" was revenue − cash operating costs − capital spending = operating income + D&A − capex.
    It is now called that ("EBITDA − capital spending"), and the real operating cash flow and free cash flow sit beside it
  - US and the rest of the world: BEA's tables describe the US economy. When a 10-K states the share of revenue earned
    outside the United States, only the US share of costs and capital spending is split by BEA; the rest is one node,
    "outside the US (not split)"
  - segments: a company that reports business segments has each segment matched by name to a BEA industry of the same
    kind (manufacturing to manufacturing …) and weighted by the segment's revenue; segments without a clear match keep
    the company's own industry mix
  - suppliers a filing names (data/network: a supplier's 10-K stating sales to the company, or the company naming its
    supplier, with dollars) are drawn as stated flows; every other supplier amount is a modelled allocation, labelled so
  - every band carries its provenance: evidence grade, source, coefficient, formula and range
      A  filed figure (SEC financial statements)
      B  computed from filed figures, or stated in the filing's text
      C  industry average (BEA input-output) applied to filed figures
      D  modelled allocation — not verified purchases
  - checks before anything is written: money is conserved column to column, imports are counted once, supplier
    allocations add up to their industry, and the filed figures match the companies' records. A level that fails is
    not published (index.json lists it)
"""
import datetime as dt
import json
import os
import re
from collections import defaultdict

from . import chains, ioflow, sectors

VERSION = "beta-1.0"
GRADES = {"A": "Filed figure (SEC financial statements)",
          "B": "Computed from filed figures, or stated in the filing's text",
          "C": "Industry average (BEA input-output) applied to filed figures",
          "D": "Modelled allocation — not verified purchases"}
SHADE = {"A": 1.0, "B": 0.75, "C": 0.3, "D": 0.06}        # band darkness on the page (web/chains.js: k)
TOP_COMPANIES, TOP_INDUSTRIES, TOP_SUPPLIERS = 12, 18, 16
TOL = 0.001                                                 # the checks: 0.1% of revenue
COLORS = {"purchases": "#5d7fa3", "employees": "#9a8f7a", "taxes": "#a08a5a", "outside": "#8a8f98", "capex": "#7b6aa8",
          "left": "#2e8b57", "finleft": "#6f9a8a"}
CAT_LABEL = {"purchases": "Purchased inputs (estimate)", "employees": "Employees (estimate)",
             "taxes": "Taxes on production (estimate)", "outside": "Costs outside the US (not split)",
             "capex": "Capital spending (filed)", "left": "EBITDA − capital spending",
             "finleft": "Interest, claims & profit (banks, insurers; estimate)"}
CAT_GRADE = {"purchases": "C", "employees": "C", "taxes": "C", "outside": "B", "capex": "A", "left": "B", "finleft": "C"}
GENERIC = {"and", "the", "of", "other", "products", "product", "services", "service", "solutions", "segment", "group",
           "systems", "technologies", "technology", "manufacturing", "equipment", "industries", "industrial", "total",
           "north", "america", "americas", "international", "global", "corporate", "all", "inc", "company", "business",
           "businesses", "net", "sales", "revenue", "revenues", "us", "u.s", "united", "states", "engineered"}


# ------------------------------------------------------------------ what the filings say
GEO_OUT = re.compile(r"(?:approximately|about|roughly|nearly|over|more than)?\s*(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,120}?"
                     r"(?:revenues?|sales)[^.]{0,120}?(?:outside (?:of )?the (?:united states|u\.s\.?)|from (?:international|foreign|"
                     r"non-u\.s\.?) (?:operations|customers|markets|sources)|(?:international|foreign|non-u\.s\.?) (?:revenues?|sales))",
                     re.I)
GEO_OUT2 = re.compile(r"(?:international|foreign|non-u\.s\.?) (?:revenues?|sales|operations)[^.]{0,80}?(?:accounted for|"
                      r"represented|were|was|comprised|made up)\s*(?:approximately|about)?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.I)
GEO_US = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,100}?(?:revenues?|sales)[^.]{0,80}?(?:in|from|within) the "
                    r"(?:united states|u\.s\.?)(?! and)", re.I)


def us_share(rec):
    """The share of revenue earned in the United States, from a sentence of the latest 10-K ("Approximately 46% of our
    revenues … were derived outside the United States"), or None. The first year a sentence lists is the latest."""
    cn = rec.get("cn") or {}
    for s in cn.get("s") or []:
        t = s.get("t") or ""
        if re.search(r"customer|supplier|vendor|employee|workforce|backlog", t, re.I):
            continue
        for rx, outside in ((GEO_OUT, True), (GEO_OUT2, True), (GEO_US, False)):
            m = rx.search(t)
            if m:
                p = float(m.group(1)) / 100
                if 0 < p < 1:
                    return {"us": round(1 - p if outside else p, 4), "text": t[:400], "url": cn.get("url"), "form": cn.get("form"),
                            "filed": cn.get("filed")}
    return None


def stated_suppliers(out, cik):
    """Suppliers named with dollars in filings (data/network/c/<cik>.json, written by pipeline/custnet.py)."""
    p = os.path.join(out, "network", "c", f"{int(cik)}.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    rows = []
    for s in d.get("suppliers") or []:
        if s.get("cik") and s.get("usd") and s["usd"] > 0:
            rows.append({"cik": int(s["cik"]), "t": s.get("t") or "", "name": s.get("name") or s.get("label") or "",
                         "usd": float(s["usd"]), "pct": s.get("pct"), "q": (s.get("q") or "")[:300], "url": s.get("url"),
                         "form": s.get("form"), "fy": s.get("fy"), "by": s.get("by")})
    return rows


def _words(s):
    return {w for w in re.findall(r"[a-z][a-z\-]{2,}", (s or "").lower()) if w not in GENERIC}


def _stem(w):
    return re.sub(r"(ings|ing|ers|er|es|s)$", "", w)


_STEMS, _DF = {}, {}


def _name_stems(io, b):
    if b not in _STEMS:
        _STEMS[b] = {_stem(x) for x in _words(io["industries"][b]["name"])}
    return _STEMS[b]


def _df(io):
    """How many BEA industry names use each word stem."""
    if not _DF:
        for b in io["industries"]:
            for w in _name_stems(io, b):
                _DF[w] = _DF.get(w, 0) + 1
    return _DF


def segment_mix(io, rec, base):
    """The company's BEA mix from its business segments (latest quarter's revenue by segment), or None.
    A segment is matched to the BEA industry of the same kind (first digit of the code) whose name shares the most
    distinctive words with it; unmatched segments keep the company's own mix."""
    I = io["industries"]
    lead = max(base.items(), key=lambda kv: kv[1])[0][:1] if base else None
    qs = rec.get("quarters") or {}
    for end in sorted(qs, reverse=True):
        q = qs[end]
        st, lines = q.get("lines_struct") or {}, q.get("lines") or {}
        if st.get("axis") != "StatementBusinessSegmentsAxis" or len(st.get("leaves") or []) < 2:
            continue
        vals = {l["id"]: lines.get(l["id"]) for l in st["leaves"]}
        tot = sum(v for v in vals.values() if v and v > 0)
        if not tot:
            continue
        mix, segs, matched = defaultdict(float), [], 0.0
        for l in st["leaves"]:
            v = vals.get(l["id"])
            if not v or v <= 0:
                continue
            w = v / tot
            words = {_stem(x) for x in _words(l["label"])}
            best, score = None, 0.0
            for b, ind in I.items():
                if lead and b[:1] != lead:
                    continue
                shared = words & _name_stems(io, b)
                # a word few BEA industries use ("pump") says more than a common one ("electronic"): 1 / its frequency
                sc = sum(1.0 / _df(io)[w] for w in shared)
                if sc > score or (sc == score and sc and ind["output"] > I[best]["output"]):
                    best, score = b, sc
            if best and score >= 0.34:                          # one word used by at most three industries, or several
                mix[best] += w
                matched += w
                segs.append({"segment": l["label"], "share": round(w, 4), "bea": best, "bea_name": I[best]["name"]})
            else:
                for b, x in base.items():
                    mix[b] += w * x
                segs.append({"segment": l["label"], "share": round(w, 4), "bea": None, "bea_name": "the company's own industry mix"})
        if matched < 0.05:
            return None
        return {"mix": dict(mix), "segments": segs, "end": end, "matched": round(matched, 4)}
    return None


# ------------------------------------------------------------------ ranges: the spread of sibling industries
class Ranges:
    """For a coefficient of a BEA industry, the 10th and 90th percentiles among its sibling industries (same first
    three digits, or two when fewer than three): how much the figure moves if the company looks like a neighbour."""

    def __init__(self, io):
        self.I = io["industries"]
        self.sib = {}
        for b in self.I:
            for n in (3, 2, 1):
                s = [x for x in self.I if x[:n] == b[:n]]
                if len(s) >= 3:
                    self.sib[b] = s
                    break
            else:
                self.sib[b] = list(self.I)
        self._c = {}

    @staticmethod
    def _q(vals, p):
        v = sorted(vals)
        if not v:
            return 0.0
        i = (len(v) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(v) - 1)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)

    def share(self, b, key):
        k = ("s", b, key)
        if k not in self._c:
            vals = [self.I[x][key] for x in self.sib[b]]
            own = self.I[b][key]
            self._c[k] = (min(own, self._q(vals, 0.1)), max(own, self._q(vals, 0.9)))
        return self._c[k]

    def supplier(self, b, i):
        k = ("p", b, i)
        if k not in self._c:
            vals = [self.I[x]["suppliers"].get(i, 0.0) * self.I[x]["inter"] for x in self.sib[b]]
            own = self.I[b]["suppliers"].get(i, 0.0) * self.I[b]["inter"]
            self._c[k] = (min(own, self._q(vals, 0.1)), max(own, self._q(vals, 0.9)))
        return self._c[k]


# ------------------------------------------------------------------ one company
def company(io, R, co, rec, sic, latest, out):
    f = ioflow.company_figures(co, latest)
    if not f:
        return None
    I = io["industries"]
    base = ioflow.bea_mix(io, sic)
    seg = segment_mix(io, rec, base) if base else None
    mix = (seg or {}).get("mix") or base
    w = {b: x for b, x in mix.items() if b in I}
    tot = sum(w.values())
    if not tot:
        return None
    w = {b: x / tot for b, x in w.items()}
    ocf, _ = ioflow.ttm(co, "ocf", latest)
    fin = ioflow.fin_ratio(sic)
    geo = us_share(rec)
    us = geo["us"] if geo else 1.0
    rev, oi, da, capex = f["revenue"], f["oi"], f["da"], f["capex"]
    cost = rev * fin if fin else max(0.0, rev - oi - da)
    cost_us, cost_out = cost * us, cost * (1 - us)
    coef = {k: sum(x * I[b][k] for b, x in w.items()) for k in ("inter", "comp", "tax")}
    rng = {k: (sum(x * R.share(b, k)[0] for b, x in w.items()), sum(x * R.share(b, k)[1] for b, x in w.items()))
           for k in ("inter", "comp", "tax", "imports")}
    spend = {"purchases": cost_us * coef["inter"], "employees": cost_us * coef["comp"], "taxes": cost_us * coef["tax"],
             "outside": cost_out, "capex": capex}
    left = rev - sum(spend.values())
    # supplying industries: purchases (US share) by each BEA industry's input mix; capital spending (US share) by its
    # asset mix; the imported share of each commodity to Imports; capital spending outside the US not split
    sup, sup_rng = defaultdict(float), defaultdict(lambda: [0.0, 0.0])
    imports = {"purchases": 0.0, "capex": 0.0}
    for b, x in w.items():
        p_b = cost_us * x                                       # the part of US spending in industry b's shape
        for i, s in I[b]["suppliers"].items():
            sup[("purchases", i)] += p_b * I[b]["inter"] * s
            lo, hi = R.supplier(b, i)
            sup_rng[("purchases", i)][0] += p_b * lo
            sup_rng[("purchases", i)][1] += p_b * hi
        imports["purchases"] += p_b * I[b]["inter"] * I[b]["imports"]
    caps = io.get("capex") or {}
    inv = io["invest"]
    for b, x in w.items():
        cm = caps.get(I[b].get("fa") or "")
        sups, imp = (cm["suppliers"], cm["imports"]) if cm else (inv["suppliers"], inv["imports"])
        for i, s in sups.items():
            sup[("capex", i)] += capex * us * x * s
        imports["capex"] += capex * us * x * imp
    for k, v in list(sup_rng.items()):
        sup_rng[k] = [min(v[0], sup[k]), max(v[1], sup[k])]
    qs = rec.get("quarters") or {}
    last = qs.get(f["end"]) or {}
    return {"revenue": rev, "oi": oi, "da": da, "capex": capex, "ocf": ocf, "fcf": (ocf - capex) if ocf is not None else None,
            "end": f["end"], "how": f["how"], "fin": fin, "geo": geo, "us": us, "cost": cost, "coef": coef, "rng": rng,
            "spend": spend, "left": max(0.0, left), "gap": max(0.0, -left), "left_key": "finleft" if fin else "left",
            "sup": dict(sup), "sup_rng": dict(sup_rng), "imports": imports, "capex_out": capex * (1 - us),
            "mix": w, "segments": (seg or {}).get("segments"), "stated": stated_suppliers(out, co.cik),
            "doc": last.get("doc_url"), "form": last.get("form"), "filed": last.get("filed")}


# ------------------------------------------------------------------ one level (industry, major group, sector)
def doc_for(key, title, level, members, listed, io):
    I = io["industries"]
    members = sorted(members, key=lambda m: -m[1]["revenue"])
    nodes, links, prov, seen = [], [], {}, set()
    revenue = sum(fl["revenue"] for _, fl in members)

    def node(id_, col, label, color, grade, **kw):
        if id_ not in seen:
            seen.add(id_)
            nodes.append({"id": id_, "col": col, "label": label, "color": color, "grade": grade, "est": grade in ("C", "D"), **kw})

    def link(s, t, v, grade, p):
        if v <= 0:
            return
        k = s + "|" + t
        for l in links:
            if l[0] == s and l[1] == t:
                l[2] += v
                prov[k]["v"] += v
                for a in ("lo", "hi"):
                    if p.get(a) is not None and prov[k].get(a) is not None:
                        prov[k][a] += p[a]
                return
        links.append([s, t, v])
        prov[k] = {"grade": grade, "v": v, **p}

    for c, lab in CAT_LABEL.items():
        node("k:" + c, 1, lab, COLORS[c], CAT_GRADE[c])
    top, rest = members[:TOP_COMPANIES], members[TOP_COMPANIES:]
    groups = [(m["ticker"] or m["name"], m["cik"], [(m, fl)]) for m, fl in top]
    if rest:
        groups.append((f"Other {len(rest)} companies", None, rest))
    gap_to = defaultdict(float)
    for label, cik, mm in groups:
        sid = "m:" + (str(cik) if cik else "other")
        node(sid, 0, label, "#5f7d99", "A", cik=cik)
        for m, fl in mm:
            who = m["ticker"] or m["name"]
            spend = sum(fl["spend"].values())
            cover = min(1.0, fl["revenue"] / spend) if spend else 1.0
            src = f"{who} {fl['form'] or '10-Q/10-K'} (four quarters to {fl['end']})"
            cost_f = (f"revenue × {fl['fin']:.0%} (typical expense ratio)" if fl["fin"] else
                      "revenue − operating income − D&A")
            us_f = f" × {fl['us']:.0%} US share" if fl["geo"] else ""
            for c, v in fl["spend"].items():
                if c == "capex":
                    p = {"source": src, "formula": "capital spending as filed", "url": fl["doc"]}
                elif c == "outside":
                    p = {"source": src + "; US share: " + (fl["geo"] or {}).get("form", "10-K") + " text", "formula":
                         f"({cost_f}) × {1 - fl['us']:.0%} outside the US", "quote": (fl["geo"] or {}).get("text"),
                         "url": (fl["geo"] or {}).get("url")}
                else:
                    ck = {"purchases": "inter", "employees": "comp", "taxes": "tax"}[c]
                    lo, hi = fl["rng"][ck]
                    p = {"source": src + "; BEA " + str(io["year"]) + " Use table", "coef": fl["coef"][ck],
                         "formula": f"({cost_f}){us_f} × {fl['coef'][ck]:.1%} ({c} share of spending, BEA)",
                         "lo": fl["cost"] * fl["us"] * lo * cover, "hi": fl["cost"] * fl["us"] * hi * cover}
                link(sid, "k:" + c, v * cover, CAT_GRADE[c], p)
                gap_to[c] += v * (1 - cover)
            link(sid, "k:" + fl["left_key"], fl["left"], CAT_GRADE[fl["left_key"]],
                 {"source": src, "formula": "operating income + D&A − capital spending (not operating cash flow: before interest, "
                  "tax and working capital)" if not fl["fin"] else "revenue − estimated operating spending"})
    if sum(gap_to.values()) > 0:
        node("m:gap", 0, "Borrowing & cash reserves", "#b9b2a3", "B")
        for c, v in gap_to.items():
            link("m:gap", "k:" + c, v, "B", {"source": "filed figures", "formula": "spending above revenue (EBITDA below capital spending)"})
    # columns 2 → 3: supplying industries
    by_ind, by_cat_ind, rng_ind = defaultdict(float), defaultdict(float), defaultdict(lambda: [0.0, 0.0])
    imports, capex_out = defaultdict(float), 0.0
    for _, fl in members:
        for (c, i), v in fl["sup"].items():
            by_ind[i] += v
            by_cat_ind[(c, i)] += v
            r = fl["sup_rng"].get((c, i))
            if r:
                rng_ind[(c, i)][0] += r[0]
                rng_ind[(c, i)][1] += r[1]
            else:
                rng_ind[(c, i)][0] += v
                rng_ind[(c, i)][1] += v
        for c, v in fl["imports"].items():
            imports[c] += v
        capex_out += fl["capex_out"]
    ranked = [i for i, _ in sorted(by_ind.items(), key=lambda kv: -kv[1]) if i != "_OTHER"][:TOP_INDUSTRIES]
    for i in ranked:
        node("i:" + i, 2, I[i]["name"], "#88a3c0", "C", bea=i)
    node("i:other", 2, "Other industries", "#b7c3cf", "C")
    node("i:imports", 2, "Imports", "#c9a77a", "C")
    node("i:capex_out", 2, "Capital spending outside the US (not split)", "#a3a6ad", "B")
    for (c, i), v in by_cat_ind.items():
        t = "i:" + i if i in ranked else "i:other"
        lo, hi = rng_ind[(c, i)]
        link("k:" + c, t, v, "C", {"source": f"BEA {io['year']} Use table (scaled to {io['scale_year']})" if c == "purchases"
                                   else "BEA fixed assets: investment by industry and asset type",
                                   "formula": ("purchased inputs × the industry's input mix" if c == "purchases" else
                                               "capital spending (US share) × the industry's asset mix") +
                                   " (domestic part; the imported part goes to Imports)", "lo": lo, "hi": hi})
    for c, v in imports.items():
        link("k:" + c, "i:imports", v, "C", {"source": f"BEA {io['year']} Use table: imports ÷ total supply, by commodity",
                                             "formula": f"{c} × each commodity's imported share"})
    link("k:capex", "i:capex_out", capex_out, "B", {"source": "capital spending as filed × the 10-K's share of revenue outside the US",
                                                   "formula": "capital spending × (1 − US share)"})
    # columns 3 → 4: suppliers — first the ones a filing names (stated, with dollars), then the modelled allocation
    stated_rows, stated_flow = [], defaultdict(float)
    ind_of = defaultdict(list)
    for b, cands in listed.items():
        for cik, tk, nm, r in cands:
            ind_of[cik].append((r, b))
    member_ciks = {m["cik"] for m, _ in members}
    for m, fl in members:
        for s in fl["stated"]:
            if s["cik"] in member_ciks:
                continue
            inds = sorted(ind_of.get(s["cik"]) or [], reverse=True)
            b = next((b for _, b in inds if by_ind.get(b, 0) > 0), None)
            row = {**s, "buyer": m["ticker"] or m["name"], "industry": I[b]["name"] if b else None, "drawn": 0.0}
            if b:
                room = by_ind[b] - stated_flow[b]
                take = min(s["usd"], max(room, 0.0))
                if take > 0:
                    stated_flow[b] += take
                    row["drawn"] = take
                    row["capped"] = take < s["usd"]
                    row["bea"] = b
            stated_rows.append(row)
    sup_flow, sup_prov = defaultdict(float), {}
    for i, v in by_ind.items():
        if i == "_OTHER":
            continue
        src = "i:" + i if i in ranked else "i:other"
        if i not in I:                                          # government and other non-industry suppliers
            sup_flow[(src, "unlisted")] += v
            continue
        model_v = v - stated_flow.get(i, 0.0)                   # what is left for the modelled allocation
        cands = [c for c in (listed.get(i) or []) if c[0] not in member_ciks]   # a company does not buy from itself here
        out_ = I[i]["output"] or 1
        tot = sum(r for *_, r in cands)
        scale = 1.0 / tot if tot > out_ else 1.0 / out_
        for cik, tk, nm, r in cands:
            sup_flow[(src, (cik, tk, nm))] += model_v * r * scale
        if tot < out_:
            sup_flow[(src, "unlisted")] += model_v * (1 - tot / out_)
        sup_prov[i] = {"share_den": "the industry's US gross output" if tot <= out_ else "the listed companies' combined revenue"}
    if by_ind.get("_OTHER"):
        sup_flow[("i:other", "unlisted")] += by_ind["_OTHER"]
    totals = defaultdict(float)
    for (_, s), v in sup_flow.items():
        if s != "unlisted":
            totals[s] += v
    best = {s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:TOP_SUPPLIERS]}
    for s in best:
        node("s:" + str(s[0]), 3, s[1] or s[2], "#6f8fb3", "D", cik=s[0], name=s[2])
    node("s:other", 3, "Other listed companies", "#a9b8c8", "D")
    node("s:unlisted", 3, "Unlisted & private", "#c3c8cd", "D")
    agg = defaultdict(float)
    for (src, s), v in sup_flow.items():
        agg[(src, "s:unlisted" if s == "unlisted" else ("s:" + str(s[0]) if s in best else "s:other"))] += v
    for (src, tgt), v in agg.items():
        link(src, tgt, v, "D", {"source": "listed companies mapped to the supplying industry by their SIC code",
                                "formula": "industry purchases × the supplier's revenue ÷ " +
                                ("the industry's US gross output" if tgt != "s:unlisted" else "(1 − listed share of the industry's output)"),
                                "note": "Modelled allocation — not verified purchases"})
    for r in stated_rows:
        if r["drawn"] > 0:
            b = r["bea"]
            src = "i:" + b if b in ranked else "i:other"
            node("x:" + str(r["cik"]), 3, (r["t"] or r["name"]) + " ✓", "#2f5f8a", "B", cik=r["cik"], name=r["name"], stated=True)
            link(src, "x:" + str(r["cik"]), r["drawn"], "B",
                 {"source": f"{r['form'] or '10-K'} ({r['fy'] or ''}): " + ("the buyer names the supplier" if r["by"] == "self" else
                                                                             "the supplier names the buyer"),
                  "formula": "dollars stated in the filing" + (" (capped at the model's purchases from this industry)" if r.get("capped") else ""),
                  "quote": r["q"], "url": r["url"]})
    # the filed layer and the totals
    filed = {"revenue": revenue, "oi": sum(fl["oi"] for _, fl in members), "da": sum(fl["da"] for _, fl in members),
             "capex": sum(fl["capex"] for _, fl in members)}
    with_ocf = [fl for _, fl in members if fl["ocf"] is not None]
    filed["ocf"] = sum(fl["ocf"] for fl in with_ocf) if with_ocf else None
    filed["fcf"] = sum(fl["fcf"] for fl in with_ocf) if with_ocf else None
    filed["ocf_n"] = len(with_ocf)
    filed["ebitda_capex"] = sum(fl["oi"] + fl["da"] - fl["capex"] for _, fl in members if not fl["fin"])
    est = {}
    for c, ck in (("purchases", "inter"), ("employees", "comp"), ("taxes", "tax")):
        v = sum(fl["spend"][c] for _, fl in members)
        est[c] = {"v": v, "lo": sum(fl["cost"] * fl["us"] * fl["rng"][ck][0] for _, fl in members),
                  "hi": sum(fl["cost"] * fl["us"] * fl["rng"][ck][1] for _, fl in members)}
    est["imports"] = {"v": sum(imports.values())}            # no range: the commodity mix decides it, not one coefficient
    est["outside"] = {"v": sum(fl["spend"]["outside"] for _, fl in members)}
    geo_n = sum(1 for _, fl in members if fl["geo"])
    seg_n = sum(1 for _, fl in members if fl["segments"])
    # denominators of each column's percentages (the chart prints each node's share of its column)
    col_tot = defaultdict(float)
    vin, vout = defaultdict(float), defaultdict(float)
    for s, t, v in links:
        vout[s] += v
        vin[t] += v
    for n in nodes:
        col_tot[n["col"]] += max(vin[n["id"]], vout[n["id"]])
    cols = [{"name": "Where the money comes from", "den": col_tot[0], "den_what": "revenue (plus borrowing where spending exceeded it)"},
            {"name": "What it is spent on", "den": col_tot[1], "den_what": "the same total"},
            {"name": "Supplying industries", "den": col_tot[2], "den_what": "purchased inputs + capital spending"},
            {"name": "Suppliers", "den": col_tot[3], "den_what": "domestic purchases from those industries (imports and spending outside the US excluded)"}]
    used = [n for n in nodes if vin[n["id"]] > 0 or vout[n["id"]] > 0]
    floor = max(1.0, 1e-4 * revenue)
    sic0, sec0 = members[0][0]["sic"], members[0][0]["sector"]
    one_sector = len({m["sector"] for m, _ in members}) == 1
    related = {"industry": sic0 if level == "industry" else None,
               "major": "sic2-" + sic0[:2] if level in ("industry", "major group") else None,
               "sector": key if level == "sector" else ("sector-" + sec0 if one_sector else None)}
    doc = {"key": key, "title": title, "level": level, "version": VERSION, "related": related,
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "companies": len(members), "revenue": round(revenue), "filed": {k: (round(v) if isinstance(v, float) else v) for k, v in filed.items()},
           "estimate": {k: {a: (round(x) if isinstance(x, float) else x) for a, x in v.items()} for k, v in est.items()},
           "geo_n": geo_n, "seg_n": seg_n, "cols": cols, "grades": GRADES, "shade": SHADE,
           "nodes": used, "links": [[s, t, round(v)] for s, t, v in links if v >= floor],
           "prov": {k: {a: (round(x) if isinstance(x, float) and a in ("v", "lo", "hi") else (round(x, 5) if isinstance(x, float) else x))
                        for a, x in p.items()} for k, p in prov.items()},
           "members": [{"cik": m["cik"], "ticker": m["ticker"], "name": m["name"], "sic": m["sic"], "end": fl["end"],
                        "revenue": round(fl["revenue"]), "oi": round(fl["oi"]), "da": round(fl["da"]), "capex": round(fl["capex"]),
                        "ocf": round(fl["ocf"]) if fl["ocf"] is not None else None, "fcf": round(fl["fcf"]) if fl["fcf"] is not None else None,
                        "us": fl["us"] if fl["geo"] else None, "geo": fl["geo"], "segments": fl["segments"], "doc": fl["doc"],
                        "form": fl["form"], "how": fl["how"]} for m, fl in members[:60]],
           "stated": stated_rows[:40],
           "source": {"io_year": io["year"], "scale_year": io["scale_year"], **io["source"]}}
    return doc, links, nodes


def check(doc, links, nodes):
    """The checks a level must pass before it is published. Returns a list of failures."""
    bad = []
    rev = doc["revenue"] or 1
    vin, vout = defaultdict(float), defaultdict(float)
    for s, t, v in links:
        vout[s] += v
        vin[t] += v
    col = {n["id"]: n["col"] for n in nodes}
    src0 = sum(v for k, v in vout.items() if col.get(k) == 0)
    gap = vout.get("m:gap", 0.0)
    if abs(src0 - gap - doc["revenue"]) > TOL * rev:
        bad.append(f"column 1 adds up to {src0 - gap:,.0f}, revenue is {doc['revenue']:,.0f}")
    in1 = sum(v for k, v in vin.items() if col.get(k) == 1)
    if abs(in1 - src0) > TOL * rev:
        bad.append(f"column 2 receives {in1:,.0f}, column 1 sends {src0:,.0f}")
    for k in ("k:purchases", "k:capex"):
        if abs(vin.get(k, 0) - vout.get(k, 0)) > TOL * rev:
            bad.append(f"{k[2:]}: {vin.get(k, 0):,.0f} in, {vout.get(k, 0):,.0f} out to the supplying industries")
    for n in nodes:
        if n["col"] == 2 and n["id"] not in ("i:imports", "i:capex_out"):
            if abs(vin[n["id"]] - vout[n["id"]]) > TOL * rev:
                bad.append(f"{n['label']}: {vin[n['id']]:,.0f} bought, {vout[n['id']]:,.0f} allocated to suppliers")
    if vout.get("i:imports", 0) > 0:
        bad.append("imports passed on to suppliers (counted twice)")
    if abs(vin.get("i:imports", 0) - doc["estimate"]["imports"]["v"]) > TOL * rev:
        bad.append("imports in the chart differ from the imports total")
    f = doc["filed"]
    m = doc["members"]
    if len(m) == doc["companies"] and abs(sum(x["revenue"] for x in m) - f["revenue"]) > TOL * rev:
        bad.append("filed revenue does not match the members' records")
    if vin.get("k:capex", 0) > f["capex"] * (1 + TOL) + 1:
        bad.append("capital spending above the filed figure")
    return bad


def build(store, out, index, usd_recs=None, path=ioflow.DATA):
    if not os.path.exists(path):
        print("::warning::money flow beta: BEA input-output data missing")
        return None
    io = ioflow.load(path)
    R = Ranges(io)
    latest = max((p.get("end") or p.get("filed") or "" for p in index), default=None) or None
    latest = latest[:10] if latest else None
    rec_all, skipped = [], defaultdict(int)
    for p in index:
        sic = str(p.get("sic") or "").strip().zfill(4)
        if not re.fullmatch(r"\d{4}", sic) or sic == "0000" or not ioflow.bea_mix(io, sic):
            skipped["no BEA industry"] += 1
            continue
        usd = (usd_recs or {}).get(p["cik"])
        if (p.get("currency") or "USD") != "USD" and not usd:
            skipped["foreign filer without dollar figures"] += 1
            continue
        rec = store.company(p["cik"])
        co = chains.Co(p["cik"], rec, usd, ticker=p.get("ticker"))
        try:
            fl = company(io, R, co, rec, sic, latest, out)
        except Exception as e:                                  # noqa: BLE001 — one company must not stop the rest
            skipped["error: " + type(e).__name__] += 1
            fl = None
        if not fl:
            skipped["no four quarters of revenue and income"] += 1
            continue
        m = {"cik": int(p["cik"]), "ticker": p.get("ticker") or "", "name": p.get("name") or "", "sic": sic,
             "sector": p.get("sector") or sectors.sector_of(sic), "industry": p.get("industry") or ""}
        rec_all.append((m, fl))
    listed = defaultdict(list)
    for m, fl in rec_all:
        for b, w in fl["mix"].items():
            listed[b].append((m["cik"], m["ticker"], m["name"], fl["revenue"] * w))
    root = os.path.join(out, "gamma", "io-beta")
    os.makedirs(root, exist_ok=True)
    groups, names = defaultdict(list), {}
    for m, fl in rec_all:
        groups[m["sic"]].append((m, fl))
        names.setdefault(m["sic"], m["industry"] or "SIC " + m["sic"])
        groups["sic2-" + m["sic"][:2]].append((m, fl))
        groups["sector-" + m["sector"]].append((m, fl))
    idx, failed = [], []
    for key, members in groups.items():
        if key.startswith("sic2-"):
            d2 = key[5:]
            title, level = f"SIC {d2} · {ioflow.MAJOR.get(d2, 'Major group ' + d2)}", "major group"
        elif key.startswith("sector-"):
            title, level = sectors.SECTORS.get(key[7:], key[7:]), "sector"
        else:
            title, level = f"SIC {key} · {names[key]}", "industry"
        doc, links, nodes = doc_for(key, title, level, members, listed, io)
        bad = check(doc, links, nodes)
        if bad:
            failed.append({"key": key, "title": title, "why": bad[:5]})
            continue
        doc["checks"] = ["money conserved column to column", "imports counted once", "supplier allocations add up to their industry",
                         "filed figures match the companies' records"]
        with open(os.path.join(root, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        idx.append({"key": key, "title": title, "level": level, "companies": doc["companies"], "revenue": doc["revenue"]})
    with open(os.path.join(root, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "levels": sorted(idx, key=lambda r: r["key"]), "failed": failed, "skipped": dict(skipped),
                   "bea": {"year": io["year"], "scale_year": io["scale_year"]}}, f, separators=(",", ":"))
    print(f"money flow beta: {len(idx)} levels written, {len(failed)} held back by the checks, from {len(rec_all)} companies")
    if failed:
        print("::warning::money flow beta: " + "; ".join(f"{x['key']}: {x['why'][0]}" for x in failed[:5]))
    return len(idx)
