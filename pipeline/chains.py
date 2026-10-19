"""Supply chains and trading themes drawn as money flows: the site's #chains pages (web/chains.js).

config/chains.json lists each chain. Four kinds:

  spend      buyers' spending (capital expenditures) -> what it is spent on -> the listed suppliers it reaches (-> their
             own suppliers). A supplier's revenue line comes from its filing; the part of it taken to come from these
             buyers is the filing's named customers where it names them ("Microsoft accounted for 26% of revenue"),
             otherwise an assumed share (config). A buyer x supplier matrix is then balanced to both sides' totals by
             RAS / iterative proportional fitting, the method statistical agencies use for input-output tables: named
             cells stay fixed, the rest are scaled until every buyer's row and every supplier's column add up. What
             the buyers spent that no listed supplier accounts for is a node of its own, never spread around.
  customers  who the companies' revenue comes from: named customers (concentration disclosures and revenue tagged by
             customer), else assumed shares, the rest "other customers".
  geo        where the revenue comes from, country by country, as each company reports it.
  basket     a theme's companies grouped into layers, by revenue.

Every chain also has a profit view (gross profit of the attributed revenue: who keeps the margin) and a cash view (where
the companies' cash came from and went in the last twelve months, from pipeline/capital.py's reading of the cash-flow
statement). Figures are trailing twelve months, in US dollars (foreign filers converted as on their own pages).

refresh() is the network half, run inside the scan's time budget: for each chain company it reads the latest 10-K /
20-F and the 10-Q after it (pipeline/xfacts.py), for the investor companies their latest 13F (stakes in chain
companies: money flowing back), and for spend-chain buyers the capital-expenditure outlook in their latest earnings
release.
"""
import datetime as dt
import json
import math
import os
import re
import sys

from . import xfacts

CFG_PATH = "config/chains.json"
VERSION = 1
CHECK_HOURS = 20                 # a chain company's filings are looked up again after this long
REFRESH_PER_RUN = 45             # companies read per scan run (each: one to seven SEC requests)
QH = 32                         # quarters of capital expenditures kept for spend-chain buyers (the forecast model)
SEG_DEPTH = 10                  # older 10-Q / 10-K instances read for a supplier's segment history, a few per visit
MIN_UNTRACED = 0.08              # at least this share of buyers' spending is taken as land, buildings and work no
                                 # listed supplier books (when suppliers' estimates already exceed what buyers spent)
CAP_PALETTE = ["#2f6db3", "#c4572e", "#1f8a5b", "#8a4fbf", "#b8860b", "#c23b74", "#2c9aa8", "#6b7d1f", "#a0522d",
               "#4f5fbf", "#7a7974", "#d07a1f", "#3e7d6e", "#9c3b3b"]


def _d(s):
    return dt.date.fromisoformat(s)


def load_cfg(path=CFG_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"::warning::chains config not read ({e})")
        return {"chains": []}


def tickers(cfg, roles=None):
    """Every ticker the chains name (buyers, members, second tier, investors)."""
    out = []
    for ch in cfg.get("chains", []):
        out += [b["t"] for b in ch.get("buyers", [])]
        for L in ch.get("layers", []):
            out += [m["t"] for m in L.get("members", [])]
        out += [k["t"] for k in ch.get("tier2", [])]
    out += cfg.get("investors", [])
    return list(dict.fromkeys(t.upper() for t in out))


def seg_tickers(cfg):
    """Suppliers of spend chains whose chain line is a segment: their segment history feeds the forecast model."""
    out = set()
    for ch in cfg.get("chains", []):
        if ch.get("kind") != "spend":
            continue
        for L in ch.get("layers", []):
            for m in L.get("members", []):
                if m.get("seg") or m.get("parts"):
                    out.add(m["t"].upper())
    return out


def buyer_tickers(cfg):
    return {b["t"].upper() for ch in cfg.get("chains", []) if ch.get("kind") == "spend" for b in ch.get("buyers", [])}


# ------------------------------------------------------------------------------------------------ one company's figures

def _quarters_of(per):
    """{(start, end): v} durations -> {end: quarter value}: three-month facts, else a year to date minus the year to date
    one quarter shorter with the same start."""
    span = lambda s, e: (_d(e) - _d(s)).days
    q = {e: v for (s, e), v in per.items() if 80 <= span(s, e) <= 100}
    by_start = {}
    for (s, e), v in per.items():
        by_start.setdefault(s, []).append((span(s, e), e, v))
    for s, rows in by_start.items():
        rows.sort()
        for (sp1, e1, v1), (sp2, e2, v2) in zip(rows, rows[1:]):
            if e2 not in q and 80 <= sp2 - sp1 <= 100:
                q[e2] = v2 - v1
    return dict(sorted(q.items()))


class Co:
    """A stored company (build.Store record) seen through what the chains need, in US dollars."""

    def __init__(self, cik, rec, usd=None, ticker=None):
        self.cik = int(cik)
        self.rec = rec
        self.cur = rec.get("currency") or "USD"
        self.u = usd if (usd and self.cur != "USD") else rec
        p = rec.get("profile") or {}
        self.ticker = ticker or (p.get("tickers") or [""])[0]
        self.name = p.get("name") or self.ticker
        self.xf = rec.get("xf") or {}
        self._q = {}
        self._conv = None

    # ---- quarters
    def quarterly(self, key):
        if key in self._q:
            return self._q[key]
        out = {}
        q = (self.rec.get("quality") or {}) if self.cur == "USD" else {}
        hist = q.get("hist") or {}
        if key in (hist.get("keys") or []):
            per, vals, fy = hist.get("periods") or [], {}, {}
            for idx, rows in (hist.get("v") or {}).get(key, []):
                if rows:
                    vals[idx] = rows[0][0]
            for i, row in enumerate(per):
                if i not in vals:
                    continue
                s, e, kind = row[0], row[1], row[2]
                if kind == "q":
                    out[e] = vals[i]
                elif kind == "fy":
                    fy[(s, e)] = vals[i]
            for (s, e), v in fy.items():                         # Q4 = the year minus its first three quarters
                if e not in out:
                    qs = [qv for qe, qv in out.items() if s < qe < e]
                    if len(qs) == 3:
                        out[e] = v - sum(qs)
        if key in ("capex", "ocf"):
            for r in (q.get("cap") or {}).get("q") or []:
                v = (r.get("items") or {}).get(key)
                if v is not None and r.get("end"):
                    out[r["end"]] = abs(v) if key == "capex" else v
        for e, qq in (self.u.get("quarters") or {}).items():
            raw = qq.get("raw") or {}
            v = raw.get(key)
            if key == "gp" and v is None and raw.get("revenue") is not None and raw.get("cor") is not None:
                v = raw["revenue"] - raw["cor"]
            if v is not None:
                out[e] = abs(v) if key == "capex" else v
        self._q[key] = dict(sorted(out.items()))
        return self._q[key]

    def history(self, key):
        """Quarterly figures {end: v} over as many years as are on file: the long companyfacts reading (spend-chain
        buyers), the company's revenue history, and its stored quarters on top (dollars)."""
        out = {e: v * self.conv for e, v in ((self.xf.get("qh") or {}).get(key) or [])}
        out.update(self.quarterly(key))
        return dict(sorted(out.items()))

    def segment_history(self, pattern):
        """Quarterly revenue {end: v} of the line(s) whose label matches, from every instance read (the latest
        10-K and 10-Q, and the older ones collected for the forecast model): three-month facts, and the quarters
        a filing gives only as a year to date (Q4 = year − nine months, Q2 = six months − Q1 …)."""
        rx = re.compile(pattern, re.I)
        merged = {}
        for p in [self.xf.get("q"), self.xf.get("k"), {"axes": self.xf.get("mh") or {}}]:
            for a, mm in ((p or {}).get("axes") or {}).items():
                for m, d in mm.items():
                    cur = merged.setdefault(a, {}).setdefault(m, {"l": d.get("l") or m, "f": {}})
                    for x in d.get("f") or []:
                        cur["f"].setdefault((x[0], x[1]), x[2])
        pref = ["StatementBusinessSegmentsAxis", "ProductOrServiceAxis"]
        for a in sorted(merged, key=lambda a: pref.index(a) if a in pref else 2):
            hits = [d for d in merged[a].values() if rx.search(d["l"] or "")]
            if not hits:
                continue
            series = [_quarters_of(d["f"]) for d in hits]
            ends = set(series[0])
            for q in series[1:]:
                ends &= set(q)
            out = {e: sum(q[e] for q in series) * self.conv for e in sorted(ends)}
            if out:
                return out
        return {}

    def ttm(self, key):
        """{"v", "end", "py" (the twelve months a year earlier, when on file), "q" (latest quarter), "basis"} or None."""
        q = self.quarterly(key)
        ends = list(q)

        def four(last):
            seq = [last]
            for _ in range(3):
                target = _d(seq[-1]) - dt.timedelta(days=91)
                cand = [e for e in ends if abs((_d(e) - target).days) <= 25]
                if not cand:
                    return None
                seq.append(min(cand, key=lambda e: abs((_d(e) - target).days)))
            return seq

        if ends:
            last = ends[-1]
            seq = four(last)
            if seq:
                out = {"v": sum(q[e] for e in seq), "end": last, "q": q[last], "basis": "ttm"}
                target = _d(last) - dt.timedelta(days=365)
                cand = [e for e in ends if abs((_d(e) - target).days) <= 25]
                if cand:
                    prev = four(min(cand, key=lambda e: abs((_d(e) - target).days)))
                    if prev:
                        out["py"] = sum(q[e] for e in prev)
                return out
        years = self.u.get("years") or {}
        for e in sorted(years, reverse=True):                  # a foreign filer with only its annual report
            v = (years[e].get("raw") or {}).get(key)
            if key == "gp" and v is None:
                raw = years[e].get("raw") or {}
                v = raw["revenue"] - raw["cor"] if raw.get("revenue") is not None and raw.get("cor") is not None else None
            if v is not None:
                return {"v": abs(v) if key == "capex" else v, "end": e, "basis": "fy"}
        return None

    @property
    def conv(self):
        """US dollars per unit of the company's own currency (1 for dollar filers): from its converted quarters."""
        if self._conv is None:
            self._conv = 1.0
            if self.cur != "USD" and self.u is not self.rec:
                a = self.rec.get("quarters") or {}
                b = self.u.get("quarters") or {}
                num = sum((b[e].get("raw") or {}).get("revenue") or 0 for e in b if e in a)
                den = sum((a[e].get("raw") or {}).get("revenue") or 0 for e in b if e in a)
                if num > 0 and den > 0:
                    self._conv = num / den
        return self._conv

    # ---- extra XBRL facts (xfacts.py)
    def parses(self):
        return [p for p in (self.xf.get("q"), self.xf.get("k")) if p]

    def _axes(self):
        axes = {}
        for p in reversed(self.parses()):                       # the 10-K first, the 10-Q's facts on top
            for a, mm in (p.get("axes") or {}).items():
                for m, d in mm.items():
                    cur = axes.setdefault(a, {}).setdefault(m, {"l": d.get("l") or m, "f": {}})
                    for s, e, v in d.get("f") or []:
                        cur["f"][(s, e)] = v
        return axes

    def member(self, pattern):
        """Trailing twelve months of the revenue line(s) whose label matches: {"v", "end", "yoy", "labels", "axis"}."""
        rx = re.compile(pattern, re.I)
        pref = ["StatementBusinessSegmentsAxis", "ProductOrServiceAxis"]
        axes = self._axes()
        newest = max((p.get("end") or "" for p in self.parses()), default="")
        rank = lambda a: (pref.index(a) if a in pref else 3 if a in ("StatementGeographicalAxis", "MajorCustomersAxis") else 2, a)
        for a in sorted(axes, key=rank):
            rows = []
            for m, d in axes[a].items():
                if not rx.search(d["l"] or ""):
                    continue
                t = xfacts.ttm([[s, e, v] for (s, e), v in d["f"].items()])
                if t and t.get("v") is not None and not (newest and (_d(newest) - _d(t["end"])).days > 100):
                    rows.append((d["l"], t))                    # (a line the company no longer reports is skipped)
            if not rows:
                continue
            end = max(t["end"] for _, t in rows)
            rows = [(l, t) for l, t in rows if t["end"] == end]
            v = sum(t["v"] for _, t in rows)
            prev = sum(t["v"] / (1 + t["yoy"]) for _, t in rows if t.get("yoy") not in (None, -1))
            basis = rows[0][1]["basis"]
            return {"v": v * self.conv, "end": end, "basis": basis, "labels": sorted({l for l, _ in rows}),
                    "axis": a, "yoy": (v / prev - 1) if prev > 0 and all(t.get("yoy") is not None for _, t in rows) else None,
                    "how": "segment" if basis != "annualized" else f"segment, {rows[0][1].get('months')} months annualized"}
        return self._member_from_lines(rx)

    def _member_from_lines(self, rx):
        """The chart's own revenue lines (the breakdown the site draws), four quarters in a row."""
        per = {}
        for e, q in (self.u.get("quarters") or {}).items():
            ls, vals = q.get("lines_struct") or {}, q.get("lines") or {}
            ids = [x["id"] for x in ls.get("leaves", []) + ls.get("groups", []) if rx.search(x.get("label") or "")]
            if ids and all(i in vals for i in ids):
                per[e] = (sum(vals[i] for i in ids), sorted({x["label"] for x in ls.get("leaves", []) + ls.get("groups", [])
                                                              if x["id"] in ids}))
        ends = sorted(per)
        if len(ends) < 4:
            return None
        last4 = ends[-4:]
        if (_d(last4[-1]) - _d(last4[0])).days > 300:
            return None
        return {"v": sum(per[e][0] for e in last4), "end": last4[-1], "basis": "ttm", "labels": per[last4[-1]][1],
                "axis": "chart lines", "yoy": None, "how": "segment"}

    def geo(self):
        """{label: trailing-twelve-month revenue} by country or region, or {}."""
        axes = self._axes().get("StatementGeographicalAxis") or {}
        rows = {}
        for m, d in axes.items():
            t = xfacts.ttm([[s, e, v] for (s, e), v in d["f"].items()])
            if t and t.get("v"):
                rows[d["l"]] = (t["v"] * self.conv, t["end"])
        if not rows:
            return {}
        end = max(e for _, e in rows.values())
        rows = {l: v for l, (v, e) in rows.items() if e == end and v > 0}
        # countries and the regions that contain them can both be tagged: keep the set that adds up to total revenue
        tot = xfacts.ttm(*[p.get("total") or [] for p in reversed(self.parses())])
        if tot and tot.get("v") and tot.get("end") == end:
            from .dims import best_partition
            part = best_partition({l: (l, v) for l, v in rows.items()}, tot["v"] * self.conv)
            if part:
                return {x["id"]: rows[x["id"]] for x in part["leaves"]}
        agg = re.compile(r"(?i)foreign|international|non-?u\.?s|outside|^total|all other countries combined")
        return {l: v for l, v in rows.items() if not agg.search(l)} or rows

    def customers(self):
        """Named (and anonymous) major customers: [{"label", "pct", "v", "period", "how"}], newest filing first."""
        rev = self.ttm("revenue")
        out = []
        region = re.compile(r"(?i)^(china|asia|asia pacific|apac|emea|europe|americas|north america|taiwan|korea|japan|united states|"
                            r"u\.s\.|singapore|international|other countries)\b")
        for c in xfacts.customers(*self.parses()):
            if c["pct"] >= 0.995 or region.search(c["l"] or ""):         # read before xfacts v2: regions, totals
                continue
            out.append({"label": c["l"] or "a customer", "pct": c["pct"], "v": c["pct"] * rev["v"] if rev else None,
                        "period": [c["s"], c["e"]], "how": "share of revenue", **({"seg": c["seg"]} if c.get("seg") else {})})
        for m, d in (self._axes().get("MajorCustomersAxis") or {}).items():   # dollars tagged by customer
            t = xfacts.ttm([[s, e, v] for (s, e), v in d["f"].items()])
            if t and t.get("v"):
                lab = d["l"]
                out = [x for x in out if x["label"] != lab]
                out.append({"label": lab, "v": t["v"] * self.conv, "pct": (t["v"] * self.conv / rev["v"]) if rev else None,
                            "period": [None, t["end"]], "how": "revenue by customer"})
        return out

    def rpo(self):
        best = (None, None)
        for p in self.parses():
            d, v = xfacts.latest_instant(p.get("rpo") or [])
            if d and (best[0] is None or d > best[0]):
                best = (d, v * self.conv)
        return best

    def lease_ttm(self):
        t = xfacts.ttm(*[p.get("lease") or [] for p in reversed(self.parses())])
        return {**t, "v": t["v"] * self.conv} if t and t.get("v") else None

    def cash(self):
        """The capital-allocation reading for the last twelve months (pipeline/capital.py), in dollars."""
        cap = ((self.rec.get("quality") or {}).get("cap") or {}).get("ttm") or {}
        items = dict(cap.get("items") or {})
        if not items:
            return None
        f = self.conv
        debt = cap.get("debt") or {}
        if debt.get("iss") is not None or debt.get("rep") is not None:
            items.pop("borrow", None)
            if debt.get("iss"):
                items["debt_in"] = abs(debt["iss"])
            if debt.get("rep"):
                items["debt_out"] = -abs(debt["rep"])
        return {"end": cap.get("end"), "label": cap.get("label"), "items": {k: v * f for k, v in items.items() if v}}


# ------------------------------------------------------------------------------------------------ the balancing

def ras(prior, row_t, col_t, iters=400, tol=1e-7):
    """Scale positive prior cells {(i, j): w} until each row adds up to row_t[i] and each column to col_t[j]
    (iterative proportional fitting). Row totals are first scaled to the columns' sum; the columns end exact."""
    x = {k: float(v) for k, v in prior.items() if v and v > 0}
    rows, cols = {}, {}
    for (i, j) in x:
        rows.setdefault(i, []).append(j)
        cols.setdefault(j, []).append(i)
    R = sum(max(row_t.get(i, 0), 0) for i in rows)
    C = sum(max(col_t.get(j, 0), 0) for j in cols)
    if R <= 0 or C <= 0:
        return {k: 0.0 for k in x}
    rt = {i: max(row_t.get(i, 0), 0) * C / R for i in rows}
    for _ in range(iters):
        for i, js in rows.items():
            s = sum(x[(i, j)] for j in js)
            if s > 0:
                f = rt[i] / s
                for j in js:
                    x[(i, j)] *= f
        err = 0.0
        for j, is_ in cols.items():
            s = sum(x[(i, j)] for i in is_)
            if s > 0:
                f = max(col_t.get(j, 0), 0) / s
                err = max(err, abs(f - 1))
                for i in is_:
                    x[(i, j)] *= f
        if err < tol:
            break
    return x


# ------------------------------------------------------------------------------------------------ building one chain

def _short(name):
    n = re.sub(r"(?i),?\s+(inc\.?|corp(oration)?\.?|co\.?|ltd\.?|limited|plc|n\.v\.|s\.a\.|holdings?|group|company|"
               r"technologies|technology|platforms|com)\b\.?", "", name or "").strip(" ,.")
    return n.title() if n.isupper() and len(n) > 4 else n


def _resolve(m, co):
    """The revenue line(s) a member stands for: [{"label", "v", "share", "end", "yoy", "how"}] or None."""
    total = co.ttm("revenue")
    tyoy = (total["v"] / total["py"] - 1) if total and total.get("py") and total["py"] > 0 else None
    plans = []
    share = m.get("share", 1)
    if m.get("parts"):
        plans.append(m["parts"])
    else:
        plans.append([{"seg": m.get("seg"), "share": share}])
    for a in m.get("alt") or []:
        plans.append([{"seg": a.get("seg"), "share": a.get("share", share)}])
    if m.get("seg") or m.get("parts"):
        plans.append(None)                                     # nothing matched: the whole company, flagged
    for parts in plans:
        out = []
        if parts is None:
            if total:
                out.append({"label": "total revenue (the named line was not found)", "v": total["v"], "share": share,
                            "end": total["end"], "yoy": tyoy, "how": "total, line not found"})
            return out or None
        for p in parts:
            if p.get("seg"):
                mv = co.member(p["seg"])
                if not mv:
                    out = None
                    break
                out.append({"label": " + ".join(mv["labels"]), "v": mv["v"], "share": p.get("share", 1), "end": mv["end"],
                            "yoy": mv.get("yoy"), "how": mv.get("how", "segment")})
            else:
                if not total:
                    out = None
                    break
                out.append({"label": "total revenue", "v": total["v"], "share": p.get("share", 1), "end": total["end"],
                            "yoy": tyoy, "how": "total"})
        if out:
            return out
    return None


def _margin(co):
    gp, rev = co.ttm("gp"), co.ttm("revenue")
    if gp and rev and rev["v"] > 0 and gp["end"] == rev["end"]:
        return max(min(gp["v"] / rev["v"], 1.0), 0.0)
    return None


def _cogs_share(co):
    cor, rev = co.ttm("cor"), co.ttm("revenue")
    if cor and rev and rev["v"] > 0:
        return max(min(cor["v"] / rev["v"], 1.0), 0.0)
    m = _margin(co)
    return 1 - m if m is not None else None


class Graph:
    def __init__(self, cols):
        self.cols = cols
        self.nodes, self.links, self._ix = [], [], {}

    def node(self, nid, col, label, value=0.0, **kw):
        if nid not in self._ix:
            self._ix[nid] = len(self.nodes)
            self.nodes.append({"id": nid, "col": col, "label": label, "v": 0.0, **kw})
        n = self.nodes[self._ix[nid]]
        n["v"] = max(n["v"], value)
        n.update({k: v for k, v in kw.items() if v is not None})
        return n

    def link(self, s, t, v, known=0.0, why=None, **kw):
        if not v or v <= 0:
            return
        for l in self.links:
            if l["s"] == s and l["t"] == t:
                l["v"] += v
                l["k"] += known
                return
        self.links.append({"s": s, "t": t, "v": v, "k": known, **({"why": why} if why else {}), **kw})

    def done(self):
        inflow, outflow = {}, {}
        for l in self.links:
            outflow[l["s"]] = outflow.get(l["s"], 0) + l["v"]
            inflow[l["t"]] = inflow.get(l["t"], 0) + l["v"]
        for n in self.nodes:
            n["v"] = max(n["v"], inflow.get(n["id"], 0), outflow.get(n["id"], 0))
        used = set(inflow) | set(outflow)
        nodes = [n for n in self.nodes if n["id"] in used]
        for l in self.links:
            l["k"] = round(min(max(l["k"] / l["v"], 0), 1), 3) if l["v"] else 0
            l["v"] = round(l["v"])
        for n in nodes:
            n["v"] = round(n["v"])
        return {"cols": self.cols, "nodes": nodes, "links": [l for l in self.links if l["v"] > 0]}


def _layer_color(i):
    return CAP_PALETTE[i % len(CAP_PALETTE)]


def _company_row(co, m, layer, parts, attr, role, extra=None):
    rev = co.ttm("revenue")
    rpo_day, rpo_v = co.rpo()
    base = sum(p["v"] for p in parts)
    yoys = [p["yoy"] for p in parts if p.get("yoy") is not None]
    return {"id": m.get("id") or co.ticker, "t": co.ticker, "cik": co.cik, "name": _short(co.name), "layer": layer,
            "role": role, "line": "; ".join(p["label"] for p in parts), "base": round(base),
            "share": round(attr / base, 4) if base else None, "attr": round(attr),
            "how": ", ".join(sorted({p["how"] for p in parts})), "end": max(p["end"] for p in parts),
            "yoy": round(yoys[0], 4) if len(yoys) == 1 else None,
            "rev": round(rev["v"]) if rev else None, "gm": _margin(co),
            **({"rpo": round(rpo_v), "rpo_day": rpo_day} if rpo_v else {}),
            **({"cur": co.cur} if co.cur != "USD" else {}), **(extra or {})}


def build_spend(ch, cos, missing):
    g = Graph([{"id": "buyers", "name": "Who spends"}, {"id": "layers", "name": "On what"},
               {"id": "suppliers", "name": "Listed suppliers"}] + ([{"id": "tier2", "name": "Their suppliers"}] if ch.get("tier2") else []))
    metric = (ch.get("spend") or {}).get("metric", "capex")
    buyers, rows = [], []
    for b in ch.get("buyers", []):
        co = cos.get(b["t"])
        if not co:
            missing.append(b["t"])
            continue
        s = co.ttm(metric)
        if not s or s["v"] <= 0:
            missing.append(b["t"])
            continue
        lease = co.lease_ttm() if (ch.get("spend") or {}).get("lease") else None
        S = s["v"] + (lease["v"] if lease else 0)
        ocf = co.ttm("ocf")
        buyers.append({"id": b["t"], "t": b["t"], "cik": co.cik, "name": _short(co.name), "S": S, "capex": s["v"],
                       "capex_py": s.get("py"), "lease": lease["v"] if lease else None, "end": s["end"],
                       "q": s.get("q"), "ocf": ocf["v"] if ocf else None, "rx": re.compile(b.get("names") or b["t"], re.I),
                       "guide": (co.xf.get("guide") or None), "cash": co.cash()})
    if not buyers:
        return None
    S_tot = sum(b["S"] for b in buyers)
    sups, known = [], {}
    for li, L in enumerate(ch.get("layers", [])):
        for m in L.get("members", []):
            co = cos.get(m["t"])
            parts = _resolve(m, co) if co else None
            if not parts:
                missing.append(m["t"])
                continue
            prior = sum(p["v"] * p["share"] for p in parts)
            base = sum(p["v"] for p in parts)
            rev = co.ttm("revenue")
            named = {}
            for c in co.customers():
                hit = next((b for b in buyers if b["rx"].search(c["label"])), None)
                if hit and c.get("v"):
                    named[hit["id"]] = named.get(hit["id"], 0) + min(c["v"], base)
            nsum = sum(named.values())
            if nsum > base:
                named = {k: v * base / nsum for k, v in named.items()}
                nsum = base
            attr_rev = min(max(prior, nsum), base)
            gm = _margin(co) if L.get("basis") == "gp" else None
            f = (gm if gm is not None else 0.12) if L.get("basis") == "gp" else 1.0
            sid = m.get("id") or m["t"]
            for bid, v in named.items():
                known[(bid, sid)] = v * f
            sups.append({"id": sid, "t": m["t"], "layer": L["id"], "R": attr_rev * f, "R_rev": attr_rev, "f": f,
                         "named": named, "co": co, "m": m, "parts": parts, "base": base, "prior": prior,
                         "gp_assumed": L.get("basis") == "gp" and gm is None})
    R_tot = sum(s["R"] for s in sups)
    other = 0.0
    if R_tot > (1 - MIN_UNTRACED) * S_tot:                 # suppliers book more than these buyers spent: others buy too
        other = R_tot - (1 - MIN_UNTRACED) * S_tot
        untraced = MIN_UNTRACED * S_tot
    else:
        untraced = S_tot - R_tot
    u_frac = untraced / S_tot if S_tot else 0
    row_t = {b["id"]: b["S"] * (1 - u_frac) for b in buyers}
    if other > 0:
        row_t["_other"] = other
    aff = ch.get("affinity") or {}
    prior, col_t = {}, {}
    k_row, k_col = {}, {}
    for (bid, sid), v in known.items():
        k_row[bid] = k_row.get(bid, 0) + v
        k_col[sid] = k_col.get(sid, 0) + v
    for s in sups:
        col_t[s["id"]] = max(s["R"] - k_col.get(s["id"], 0), 0)
        for bid in row_t:
            if (bid, s["id"]) in known:
                continue
            w = (row_t[bid] * (s["R"] / R_tot if R_tot else 0)) * ((aff.get(bid) or {}).get(s["t"], 1.0) if bid != "_other" else 1.0)
            if w > 0:
                prior[(bid, s["id"])] = w
    rest_row = {bid: max(t - k_row.get(bid, 0), 0) for bid, t in row_t.items()}
    est = ras(prior, rest_row, col_t)
    M = {}
    for k, v in list(known.items()) + list(est.items()):
        M[k] = M.get(k, 0) + v
    layers = {L["id"]: (li, L) for li, L in enumerate(ch.get("layers", []))}
    # nodes
    for b in buyers:
        g.node(b["id"], 0, b["t"], b["S"], t=b["t"], cik=b["cik"], sub=b["name"], color="#44505a")
    if other > 0:
        g.node("_other", 0, "Other buyers", other, sub="suppliers' sales these buyers do not account for", est=True)
    for lid, (li, L) in layers.items():
        g.node("L:" + lid, 1, L["name"], color=_layer_color(li), zh=L.get("zh"), layer=lid)
    g.node("_untraced", 1, "Not traced to listed suppliers", untraced, sub=ch.get("untraced"), est=True, color="#9a9893")
    for s in sups:
        li = layers[s["layer"]][0]
        g.node(s["id"], 2, s["m"].get("label") or s["t"], s["R"], t=s["t"], cik=s["co"].cik, layer=s["layer"],
               color=_layer_color(li))
    for b in buyers:
        u = b["S"] - sum(M.get((b["id"], s["id"]), 0) for s in sups)
        if u > 0:
            g.link(b["id"], "_untraced", u, 0, why="not traced to a listed supplier")
    for (bid, sid), v in M.items():
        s = next(x for x in sups if x["id"] == sid)
        g.link(bid, "L:" + s["layer"], v, known.get((bid, sid), 0))
    for s in sups:
        g.link("L:" + s["layer"], s["id"], s["R"], sum(v for (b_, sid), v in known.items() if sid == s["id"]),
               why=_why(s))
    # second tier: the suppliers' own suppliers, out of the suppliers' cost of goods
    tier_rows = []
    for k in ch.get("tier2", []):
        co = cos.get(k["t"])
        parts = _resolve(k, co) if co else None
        if not parts:
            missing.append(k["t"])
            continue
        Rk = sum(p["v"] * p["share"] for p in parts)
        froms = [(sid, w) for sid, w in (k.get("from") or {}).items() if any(s["id"] == sid for s in sups)]
        named = {}
        for c in co.customers():
            for sid, _ in froms:
                sc = next(s for s in sups if s["id"] == sid)
                if re.search(re.escape(_short(sc["co"].name).split()[0]), c["label"], re.I) and c.get("v"):
                    named[sid] = named.get(sid, 0) + c["v"]
        wsum = sum(w for sid, w in froms if sid not in named) or 1
        rest = max(Rk - sum(named.values()), 0)
        kid = k.get("id") or k["t"]
        drawn = 0
        for sid, w in froms:
            sc = next(s for s in sups if s["id"] == sid)
            cs = _cogs_share(sc["co"])
            cap = (cs if cs is not None else 0.5) * sc["R_rev"] * k.get("cogs_cap", 0.5)
            v = named.get(sid) if sid in named else rest * w / wsum
            v = min(v, cap)
            if v > 0:
                g.node(kid, 3, k.get("label") or k["t"], t=k["t"], cik=co.cik, color="#6d6a8f")
                g.link(sid, kid, v, v if sid in named else 0,
                       why=("named customer in the supplier's filing" if sid in named else
                            f"assumed: {k.get('share', 1):.0%} of its revenue serves these chips, split by size, "
                            f"at most {k.get('cogs_cap', 0.5):.0%} of the buyer's cost of goods"))
                drawn += v
        tier_rows.append(_company_row(co, k, "tier2", parts, drawn, "tier2", {"note": k.get("note")}))
    view = g.done()
    # tables
    comp = []
    for s in sups:
        co = s["co"]
        comp.append(_company_row(co, s["m"], s["layer"], s["parts"], s["R_rev"], "supplier", {
            "named": [{"b": b, "v": round(v)} for b, v in s["named"].items()],
            "customers": [{"label": c["label"], "pct": c.get("pct"), "how": c["how"]} for c in co.customers()][:8],
            "prior": round(s["prior"]), **({"basis": "gp", "drawn": round(s["R"])} if s["f"] != 1.0 else {}),
            **({"gp_assumed": True} if s["gp_assumed"] else {}), "note": s["m"].get("note")}))
    matrix = [{"b": b, "s": s, "v": round(v), "named": (b, s) in known} for (b, s), v in sorted(M.items(), key=lambda kv: -kv[1])
              if v >= 1]
    wallet = []
    for s in sups:
        cents = 100 * s["R"] / S_tot if S_tot else None
        py_b = sum(b["capex_py"] or 0 for b in buyers)
        yoys = [p["yoy"] for p in s["parts"] if p.get("yoy") is not None]
        cents_py = None
        if py_b > 0 and len(yoys) == len(s["parts"]) and all(y > -1 for y in yoys):
            r_py = sum(p["v"] * p["share"] / (1 + p["yoy"]) for p in s["parts"]) * s["f"]
            cents_py = 100 * r_py / py_b
        wallet.append({"id": s["id"], "t": s["t"], "layer": s["layer"], "cents": round(cents, 2) if cents is not None else None,
                       "cents_py": round(cents_py, 2) if cents_py is not None else None})
    known_tot = sum(known.values())
    traced = sum(s["R"] for s in sups)
    funding = []
    for b in buyers:                       # how each buyer's spending was paid for: its cash sources, pro rata
        items = (b.get("cash") or {}).get("items") or {}
        srcs = {k: v for k, v in items.items() if v and v > 0 and k in dict(SRC)}
        tot = sum(srcs.values())
        cap = b["capex"]
        for k, v in srcs.items():
            if tot > 0:
                funding.append({"b": b["id"], "src": k, "label": dict(SRC)[k], "v": round(cap * v / tot)})
        if not srcs:
            funding.append({"b": b["id"], "src": "unknown", "label": "Cash flow not read yet", "v": round(cap)})
        if b.get("lease"):
            funding.append({"b": b["id"], "src": "lease", "label": "Finance leases", "v": round(b["lease"])})
    return {"views": {"flow": view}, "companies": comp + tier_rows, "matrix": matrix, "wallet": wallet, "funding": funding,
            "buyers": [{k: (round(v) if isinstance(v, float) else v) for k, v in b.items() if k not in ("rx",)} for b in buyers],
            "coverage": {"spend": round(S_tot), "traced": round(min(traced, S_tot)), "named": round(known_tot),
                         "untraced": round(untraced), "other_buyers": round(other), "suppliers": len(sups)},
            "_sups": sups, "_buyers": buyers}


def _why(s):
    parts = s["parts"]
    line = "; ".join(f"{p['label']} × {p['share']:.0%}" if p["share"] != 1 else p["label"] for p in parts)
    if s["named"]:
        line += " (named customers in the filing: " + ", ".join(s["named"]) + ")"
    if s["f"] != 1.0:
        line += f"; gross profit only ({s['f']:.0%} margin{' assumed' if s['gp_assumed'] else ''})"
    return line


def build_customers(ch, cos, missing):
    cust = ch.get("customers", [])
    g = Graph([{"id": "customers", "name": "Who pays"}, {"id": "layers", "name": "Layer"}, {"id": "companies", "name": "Companies"}])
    rx = [(c["id"], re.compile(c["match"], re.I)) for c in cust]
    comp = []
    totals = {}
    for li, L in enumerate(ch.get("layers", [])):
        g.node("L:" + L["id"], 1, L["name"], color=_layer_color(li), zh=L.get("zh"), layer=L["id"])
        for m in L.get("members", []):
            co = cos.get(m["t"])
            parts = _resolve(m, co) if co else None
            if not parts:
                missing.append(m["t"])
                continue
            base = sum(p["v"] * p.get("share", 1) for p in parts)
            if base <= 0:
                continue
            named = {}
            for c in co.customers():
                cid = next((i for i, r in rx if r.search(c["label"] or "")), None)
                if cid and c.get("v"):
                    named[cid] = named.get(cid, 0) + c["v"]
            nsum = sum(named.values())
            if nsum > base:
                named = {k: v * base / nsum for k, v in named.items()}
            flows = dict(named)
            for cid, frac in (m.get("split") or {}).items():
                if cid not in named:
                    flows[cid] = base * frac
            fsum = sum(flows.values())
            if fsum > base:                                    # assumed shares give way to named ones
                over = fsum - base
                est = {k: v for k, v in flows.items() if k not in named}
                es = sum(est.values()) or 1
                for k in est:
                    flows[k] -= over * est[k] / es
            nid = m.get("id") or m["t"]
            g.node(nid, 2, m.get("label") or m["t"], base, t=m["t"], cik=co.cik, layer=L["id"], color=_layer_color(li))
            g.link("L:" + L["id"], nid, base, sum(named.values()), why=_line(parts))
            for cid, v in flows.items():
                name = next(c["name"] for c in cust if c["id"] == cid)
                g.node("C:" + cid, 0, name, color="#44505a")
                g.link("C:" + cid, "L:" + L["id"], v, v if cid in named else 0)
                totals[cid] = totals.get(cid, 0) + v
            rest = base - sum(flows.values())
            if rest > 0:
                g.node("C:_rest", 0, ch.get("rest") or "Other customers", est=True, color="#9a9893")
                g.link("C:_rest", "L:" + L["id"], rest, 0)
            comp.append(_company_row(co, m, L["id"], parts, base, "member", {
                "named": [{"b": k, "v": round(v)} for k, v in named.items()],
                "customers": [{"label": c["label"], "pct": c.get("pct"), "how": c["how"]} for c in co.customers()][:8],
                "flows": {k: round(v) for k, v in flows.items()}}))
    if not comp:
        return None
    return {"views": {"flow": g.done()}, "companies": comp,
            "customers": [{"id": c["id"], "name": c["name"], "v": round(totals.get(c["id"], 0))} for c in cust]}


def build_geo(ch, cos, missing):
    regions = ch.get("regions", [])
    rx = [(r["id"], re.compile(r["match"], re.I)) for r in regions]
    g = Graph([{"id": "regions", "name": "Where it is sold"}, {"id": "layers", "name": "Layer"}, {"id": "companies", "name": "Companies"}])
    comp, totals = [], {}
    for li, L in enumerate(ch.get("layers", [])):
        g.node("L:" + L["id"], 1, L["name"], color=_layer_color(li), zh=L.get("zh"), layer=L["id"])
        for m in L.get("members", []):
            co = cos.get(m["t"])
            parts = _resolve(m, co) if co else None
            if not parts:
                missing.append(m["t"])
                continue
            base = sum(p["v"] * p.get("share", 1) for p in parts)
            rev = co.ttm("revenue")
            geo = co.geo()
            gsum = sum(geo.values())
            flows, known = {}, 0
            if gsum > 0:
                scale = base / gsum
                for lab, v in geo.items():
                    rid = next((i for i, r in rx if r.search(lab)), regions[-1]["id"] if regions else "_rest")
                    flows[rid] = flows.get(rid, 0) + v * scale
                known = base
            else:
                flows["_none"] = base
            nid = m.get("id") or m["t"]
            g.node(nid, 2, m.get("label") or m["t"], base, t=m["t"], cik=co.cik, layer=L["id"], color=_layer_color(li))
            g.link("L:" + L["id"], nid, base, known, why=_line(parts))
            for rid, v in flows.items():
                name = next((r["name"] for r in regions if r["id"] == rid), "Not broken down by country")
                g.node("R:" + rid, 0, name, est=rid == "_none", color="#44505a")
                g.link("R:" + rid, "L:" + L["id"], v, v if rid != "_none" else 0)
                totals[rid] = totals.get(rid, 0) + v
            comp.append(_company_row(co, m, L["id"], parts, base, "member", {
                "geo": {k: round(v) for k, v in sorted(geo.items(), key=lambda kv: -kv[1])},
                "regions": {k: round(v) for k, v in flows.items()},
                "china": round(flows.get("china", 0) / base, 4) if base and gsum else None}))
    if not comp:
        return None
    return {"views": {"flow": g.done()}, "companies": comp,
            "regions": [{"id": r["id"], "name": r["name"], "v": round(totals.get(r["id"], 0))} for r in regions] +
                       ([{"id": "_none", "name": "Not broken down by country", "v": round(totals["_none"])}] if totals.get("_none") else [])}


def build_basket(ch, cos, missing):
    g = Graph([{"id": "theme", "name": "Theme"}, {"id": "layers", "name": "Layer"}, {"id": "companies", "name": "Companies"}])
    comp = []
    g.node("theme", 0, ch["name"], color="#44505a")
    for li, L in enumerate(ch.get("layers", [])):
        g.node("L:" + L["id"], 1, L["name"], color=_layer_color(li), zh=L.get("zh"), layer=L["id"])
        for m in L.get("members", []):
            co = cos.get(m["t"])
            parts = _resolve(m, co) if co else None
            if not parts:
                missing.append(m["t"])
                continue
            base = sum(p["v"] * p.get("share", 1) for p in parts)
            if base <= 0:
                continue
            nid = m.get("id") or m["t"]
            sure = base if all(p["share"] == 1 and p["how"] != "total, line not found" for p in parts) else 0
            g.link("theme", "L:" + L["id"], base, sure)
            pieces = []
            if m.get("split_members") and m.get("seg") and parts[0]["how"] == "segment":
                for piece in m["seg"].split("|"):
                    mv = co.member(piece)
                    if mv and mv["v"] > 0:
                        pieces.append((f"{m['t']} · {' + '.join(mv['labels'])}", mv["v"]))
            if len(pieces) > 1:
                for lab, v in pieces:
                    pid = f"{nid}:{lab}"
                    g.node(pid, 2, lab, v, t=m["t"], cik=co.cik, layer=L["id"], color=_layer_color(li))
                    g.link("L:" + L["id"], pid, v, v, why=lab)
            else:
                g.node(nid, 2, m.get("label") or m["t"], base, t=m["t"], cik=co.cik, layer=L["id"], color=_layer_color(li))
                g.link("L:" + L["id"], nid, base, sure, why=_line(parts))
            comp.append(_company_row(co, m, L["id"], parts, base, "member"))
    if not comp:
        return None
    return {"views": {"flow": g.done()}, "companies": comp}


def _line(parts):
    return "; ".join(f"{p['label']} × {p['share']:.0%}" if p.get("share", 1) != 1 else p["label"] for p in parts)


# ---- the profit and cash views (every kind)

def profit_view(ch, rows):
    g = Graph([{"id": "theme", "name": "Chain revenue"}, {"id": "layers", "name": "Layer"},
               {"id": "companies", "name": "Gross profit kept"}])
    g.node("theme", 0, "Gross profit in this chain", color="#17734a")
    lix = {L["id"]: i for i, L in enumerate(ch.get("layers", []))}
    for r in rows:
        if r["role"] == "tier2" or r.get("gm") is None or not r.get("attr"):
            continue
        gp = r["attr"] * r["gm"]
        if gp <= 0:
            continue
        L = next((x for x in ch.get("layers", []) if x["id"] == r["layer"]), None)
        if not L:
            continue
        g.node("L:" + L["id"], 1, L["name"], color=_layer_color(lix[L["id"]]), layer=L["id"])
        g.node(r["id"], 2, r["id"] if r["id"] != r["t"] else r["t"], gp, t=r["t"], cik=r["cik"], layer=L["id"],
               color=_layer_color(lix[L["id"]]), gm=round(r["gm"], 4))
        g.link("theme", "L:" + L["id"], gp, gp)
        g.link("L:" + L["id"], r["id"], gp, gp, why=f"{r['gm']:.0%} gross margin on the attributed revenue")
    return g.done()


SRC = [("ocf", "Operating cash flow"), ("debt_in", "New borrowing"), ("borrow", "Net new borrowing"), ("stock", "Shares sold"),
       ("inv_other", "Investments sold"), ("fin_other", "Other financing in"), ("cash", "Cash drawn down")]
USE = [("capex", "Capital expenditures"), ("acq", "Acquisitions"), ("buyback", "Buybacks"), ("div", "Dividends"),
       ("withhold", "Tax on employee stock"), ("debt_out", "Debt repaid"), ("borrow", "Net debt repaid"),
       ("inv_other", "Investments bought"), ("fin_other", "Other financing out"), ("ocf", "Cash burned in operations"),
       ("cash", "Added to cash")]


CASH_COLOR = {"S:ocf": "#17734a", "S:debt_in": "#2f6db3", "S:borrow": "#2f6db3", "S:stock": "#8a4fbf", "S:inv_other": "#7a7974",
              "S:fin_other": "#9a9893", "S:cash": "#b8860b", "U:capex": "#c4572e", "U:acq": "#a0522d", "U:buyback": "#2c9aa8",
              "U:div": "#1f8a5b", "U:withhold": "#9a9893", "U:debt_out": "#4f5fbf", "U:borrow": "#4f5fbf", "U:inv_other": "#7a7974",
              "U:fin_other": "#9a9893", "U:ocf": "#b8432f", "U:cash": "#b8860b"}


def cash_view(entities, by_layer=None):
    """Sources -> companies (or layers) -> uses, from each one's twelve-month capital-allocation reading."""
    g = Graph([{"id": "sources", "name": "Cash from"}, {"id": "who", "name": "Companies"}, {"id": "uses", "name": "Cash to"}])
    for e in entities:
        c = e.get("cash")
        if not c:
            continue
        items = c["items"]
        who = e["group"] if by_layer else e["id"]
        g.node(who, 1, e.get("glabel") or e["id"], t=None if by_layer else e.get("t"), cik=None if by_layer else e.get("cik"),
               color=e.get("color") or "#44505a", layer=e.get("layer"))
        for k, name in SRC:
            v = items.get(k)
            if v and v > 0:
                g.node("S:" + k, 0, name, color=CASH_COLOR.get("S:" + k))
                g.link("S:" + k, who, v, v, c=CASH_COLOR.get("S:" + k))
        for k, name in USE:
            v = items.get(k)
            if v and v < 0:
                g.node("U:" + k, 2, name, color=CASH_COLOR.get("U:" + k))
                g.link(who, "U:" + k, -v, -v, c=CASH_COLOR.get("U:" + k))
    return g.done()


def _norm(name):
    n = re.sub(r"(?i)\b(inc|corp|corporation|co|ltd|limited|plc|n\.?v|s\.?a|holdings?|group|company|class [a-z]|cl [a-z]|com|"
               r"new|the|ord|shs|adr|sponsored)\b\.?", " ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def stakes(cfg, cos, rows):
    """Money flowing back: shares of this chain's companies held by the investor companies (their latest 13F)."""
    want = {}
    for r in rows:
        co = cos.get(r["t"])
        if co:
            want[_norm(co.name)] = r["t"]
    out = []
    for inv in cfg.get("investors", []):
        co = cos.get(inv.upper())
        f13 = (co.xf.get("f13") if co else None) or {}
        for issuer, cusip, v in f13.get("rows") or []:
            t = want.get(_norm(issuer))
            if t and t != inv:
                out.append({"from": inv, "to": t, "v": round(v), "period": f13.get("period"), "url": f13.get("url"),
                            "issuer": issuer})
    return sorted(out, key=lambda x: -x["v"])


# ------------------------------------------------------------------------------------------------ all chains

def build(store, out, index=None, usd=None, cfg=None, now=None):
    """Write out/chains/index.json and out/chains/<id>.json. index: the site index rows (ticker -> cik); usd: cik -> the
    company's record converted to dollars (render's foreign filers)."""
    cfg = cfg or load_cfg()
    now = now or dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    tick = {}
    for t, cik in ((store.state.get("chain_ciks") or {}).get("m") or {}).items():
        tick[t.upper()] = int(cik)
    for r in index or []:
        if r.get("ticker"):
            tick.setdefault(r["ticker"].upper().replace(".", "-"), int(r["cik"]))
    cos = {}
    for t in tickers(cfg):
        cik = tick.get(t)
        if not cik:
            continue
        rec = store.company(cik)
        if not rec.get("quarters") and not rec.get("years") and not rec.get("xf"):
            continue
        cos[t] = Co(cik, rec, (usd or {}).get(cik), ticker=t)
    os.makedirs(os.path.join(out, "chains"), exist_ok=True)
    listing = []
    for ch in cfg.get("chains", []):
        missing = []
        try:
            kind = ch.get("kind", "basket")
            res = {"spend": build_spend, "customers": build_customers, "geo": build_geo}.get(kind, build_basket)(ch, cos, missing)
        except Exception as e:                                         # one chain never stops the others
            print(f"::warning::chain {ch.get('id')} not built: {e}")
            import traceback
            traceback.print_exc()
            continue
        if not res:
            print(f"  chain {ch['id']}: nothing on file yet (missing {', '.join(missing[:8])})")
            continue
        rows = res["companies"]
        if kind == "spend":
            try:                                                       # the forecast model (chainmodel.py)
                from . import chainmodel
                res["model"] = chainmodel.run(ch, res, cos)
            except Exception as e:
                print(f"::warning::chain {ch['id']}: forecast model not run: {e}")
                import traceback
                traceback.print_exc()
        res["views"]["profit"] = profit_view(ch, rows)
        lix = {L["id"]: i for i, L in enumerate(ch.get("layers", []))}
        if ch.get("kind") == "spend":
            ents = [{"id": b["t"], "t": b["t"], "cik": b["cik"], "cash": b.get("cash")} for b in res["_buyers"]]
            res["views"]["cash"] = cash_view(ents)
        else:
            ents = []
            for r in rows:
                co = cos.get(r["t"])
                if co and r["role"] == "member" and not any(e["t"] == r["t"] for e in ents):
                    L = next(x for x in ch["layers"] if x["id"] == r["layer"])
                    ents.append({"id": r["t"], "t": r["t"], "cik": r["cik"], "cash": co.cash(), "group": "L:" + L["id"],
                                 "glabel": L["name"], "color": _layer_color(lix[L["id"]]), "layer": L["id"]})
            res["views"]["cash"] = cash_view(ents, by_layer=len(ents) > 14)
        res["stakes"] = stakes(cfg, cos, rows + [{"t": b["t"]} for b in res.get("buyers", [])])
        for k in [k for k in res if k.startswith("_")]:
            res.pop(k)
        ends = sorted(r["end"] for r in rows if r.get("end"))
        doc = {"id": ch["id"], "name": ch["name"], "zh": ch.get("zh"), "theme": ch.get("theme"), "kind": ch.get("kind"),
               "about": ch.get("about"), "generated": now, "asof": ends[-1] if ends else None,
               "oldest": ends[0] if ends else None, "untraced_note": ch.get("untraced"),
               "spend_label": (ch.get("spend") or {}).get("label"),
               "layers": [{"id": L["id"], "name": L["name"], "zh": L.get("zh"), "color": _layer_color(i), "basis": L.get("basis"),
                           "tickers": list(dict.fromkeys(m["t"] for m in L.get("members", [])))}
                          for i, L in enumerate(ch.get("layers", []))],
               "missing": sorted(set(missing)), **res}
        with open(os.path.join(out, "chains", f"{ch['id']}.json"), "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        flow = res["views"]["flow"]
        top = sorted((n for n in flow["nodes"] if n.get("t") and n["col"] == 2), key=lambda n: -n["v"])[:3]
        listing.append({"id": ch["id"], "name": ch["name"], "zh": ch.get("zh"), "theme": ch.get("theme"), "kind": ch.get("kind"),
                        "about": ch.get("about"), "asof": doc["asof"], "companies": len(rows),
                        "total": round(sum(r["attr"] for r in rows if r["role"] != "tier2")),
                        "spend": (res.get("coverage") or {}).get("spend"),
                        "buyers": [b["t"] for b in res.get("buyers") or []],
                        "top": [{"t": n["t"], "v": n["v"]} for n in top],
                        "layers": [{"id": L["id"], "name": L["name"], "zh": L.get("zh"), "color": _layer_color(i),
                                    "tickers": [r["t"] for r in rows if r["layer"] == L["id"]]}
                                   for i, L in enumerate(ch.get("layers", []))],
                        "missing": len(set(missing))})
        print(f"  chain {ch['id']}: {len(rows)} companies, {len(flow['links'])} flows"
              + (f"; not on file: {', '.join(sorted(set(missing)))}" if missing else ""))
    with open(os.path.join(out, "chains", "index.json"), "w") as f:
        json.dump({"generated": now, "about": cfg.get("about"), "chains": listing}, f, separators=(",", ":"))
    if listing and not os.environ.get("PYTEST_CURRENT_TEST"):
        with_x = sum(1 for c in cos.values() if c.xf.get("k") or c.xf.get("q"))
        print(f"::notice::chains: {len(listing)} built; {with_x} of {len(cos)} companies have their segment and customer facts read; "
              + "; ".join(f"{c['id']} {c['companies']}" + (f" (missing {c['missing']})" if c["missing"] else "") for c in listing))
    return listing


# ------------------------------------------------------------------------------------------------ the network half

GUIDE = re.compile(r"(?i)(capital expenditures?|capex|capital spending|capital investments?)[^.]{0,160}?"
                   r"\$\s?(\d+(?:\.\d+)?)\s*(?:(?:-|–|to|and)\s*\$?\s?(\d+(?:\.\d+)?))?\s*(billion|million)")


def capex_guidance(paras):
    """Sentences of an earnings release that give a capital-expenditure outlook: [{"text", "lo", "hi", "year"}]."""
    out = []
    for p in paras:
        for sent in re.split(r"(?<=[.;])\s+", p):
            if not re.search(r"(?i)expect|anticipat|outlook|guidance|plan|forecast|range", sent):
                continue
            m = GUIDE.search(sent)
            if not m:
                continue
            unit = 1e9 if m.group(4).lower() == "billion" else 1e6
            lo = float(m.group(2)) * unit
            hi = float(m.group(3)) * unit if m.group(3) else lo
            yr = re.search(r"\b(20\d\d)\b", sent)
            fy = re.search(r"(?i)fiscal (?:year )?(20\d\d)", sent)
            out.append({"text": sent.strip()[:400], "lo": lo, "hi": hi,
                        "year": (fy or yr).group(1) if (fy or yr) else None})
    return out[:4]


def _infotable(xml_text):
    """13F information table -> [[issuer, cusip, value in dollars]] (summed per CUSIP)."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    rows = {}
    for el in root.iter():
        if el.tag.split("}")[-1] != "infoTable":
            continue
        d = {x.tag.split("}")[-1]: (x.text or "").strip() for x in el.iter()}
        try:
            v = float(d.get("value") or 0)
        except ValueError:
            continue
        cus = d.get("cusip") or d.get("nameOfIssuer")
        r = rows.setdefault(cus, [d.get("nameOfIssuer") or "", cus, 0.0])
        r[2] += v
    return sorted(rows.values(), key=lambda r: -r[2])


def refresh(store, sec, dims, text, time_up, queue_history=None, limit=REFRESH_PER_RUN, cfg=None):
    """Read the extra facts of the chain companies whose filings changed (or were never read), a few dozen per run."""
    cfg = cfg or load_cfg()
    want = tickers(cfg)
    if not want:
        return
    st = store.state
    cm = st.get("chain_ciks") or {}
    age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(cm["t"])).days if cm.get("t") else 99
    unknown = set(want) - set(cm.get("m") or {}) - set(cm.get("none") or [])
    if age >= 7 or unknown:                                      # SEC's ticker list, once a week or for a new ticker
        try:
            data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
            m = {}
            for v in data.values():                              # the list puts each company's main ticker first
                m.setdefault(str(v["ticker"]).upper().replace(".", "-"), int(v["cik_str"]))
            st["chain_ciks"] = cm = {"t": dt.datetime.utcnow().isoformat(timespec="seconds"),
                                     "m": {t: m[t] for t in want if t in m}, "none": [t for t in want if t not in m]}
            if cm["none"]:
                print(f"  chain tickers SEC does not list: {', '.join(cm['none'])}")
        except Exception as e:
            print(f"::warning::chain tickers not looked up ({e})")
            if not cm.get("m"):
                return
    buyers = buyer_tickers(cfg)
    segs = seg_tickers(cfg)
    investors = {t.upper() for t in cfg.get("investors", [])}
    now = dt.datetime.utcnow()
    todo = []
    for t, cik in (cm.get("m") or {}).items():
        rec = store.company(cik)
        xf = rec.get("xf") or {}
        newest = max(((q.get("filed") or "", q.get("accn")) for q in (rec.get("quarters") or {}).values()
                      if q.get("form", "").startswith(("10-Q", "10-K"))), default=("", None))[1]
        have = {(xf.get("k") or {}).get("accn"), (xf.get("q") or {}).get("accn")}
        checked = xf.get("checked")
        age = (now - dt.datetime.fromisoformat(checked)).total_seconds() / 3600 if checked else 1e9
        shallow = t in segs and len(xf.get("mh_accns") or []) < SEG_DEPTH and age >= 1
        if xf.get("v") != VERSION * 1000 + xfacts.VERSION or (newest and newest not in have) or age >= CHECK_HOURS or shallow:
            pri = (0 if t in buyers and not xf.get("qh") else 1 if not xf else 2 if newest and newest not in have
                   else 3 if not shallow else 4)                 # the forecast model's buyers first
            todo.append((pri, -age, t, cik))
    todo.sort()
    done = 0
    for _, _, t, cik in todo:
        if done >= limit or time_up():
            break
        done += 1
        try:
            _refresh_one(store, sec, dims, text, t, cik, t in buyers, t in investors, queue_history, t in segs)
        except Exception as e:
            print(f"  chain facts skipped for {t}: {e}", file=sys.stderr)
    if done:
        print(f"::notice::chain facts: {done} companies read ({len(todo) - done} waiting)")


def _rows(sub):
    r = sub.get("filings", {}).get("recent", {})
    keys = list(r.keys())
    return [{k: r[k][i] for k in keys} for i in range(len(r.get("accessionNumber", [])))]


def _merge_axes(into, axes, keep=("ProductOrServiceAxis", "StatementBusinessSegmentsAxis")):
    """Add an instance's revenue lines to the merged history; figures already there (from a newer filing) win."""
    for a, mm in (axes or {}).items():
        if a not in keep:
            continue
        for m, d in mm.items():
            cur = into.setdefault(a, {}).setdefault(m, {"l": d.get("l") or m, "f": []})
            have = {(x[0], x[1]) for x in cur["f"]}
            cur["f"] += [x for x in d.get("f") or [] if (x[0], x[1]) not in have]


def _refresh_one(store, sec, dims, text, t, cik, is_buyer, is_investor, queue_history, seg_hist=False):
    rec = store.company(cik)
    xf = dict(rec.get("xf") or {})
    if xf.get("v") != VERSION * 1000 + xfacts.VERSION:
        xf = {}
    sub = sec.get_json(sec.submissions_url(cik))
    rows = _rows(sub)
    annual = next((r for r in rows if r["form"] in ("10-K", "20-F", "40-F", "10-KT")), None)
    quarter = next((r for r in rows if r["form"] == "10-Q"), None)
    if quarter and annual and quarter["filingDate"] < annual["filingDate"]:
        quarter = None
    for key, r in (("k", annual), ("q", quarter)):
        if not r:
            xf.pop(key, None)
            continue
        if (xf.get(key) or {}).get("accn") == r["accessionNumber"]:
            continue
        inst, lab = dims.find_files(cik, r["accessionNumber"])
        if not inst:
            xf[key] = {"accn": r["accessionNumber"], "form": r["form"], "filed": r["filingDate"], "none": True}
            continue
        labels = dims.parse_labels(sec.get(lab)) if lab else {}
        p = xfacts.parse(sec.get(inst), labels)
        xf[key] = {"accn": r["accessionNumber"], "form": r["form"], "filed": r["filingDate"], **p}
    newest = (xf.get("q") or xf.get("k") or {}).get("accn")
    if is_buyer and newest and (xf.get("qh") or {}).get("accn") != newest:
        try:                                                 # seven-plus years of quarterly capex (companyfacts)
            from . import facts as F
            from .build import primary_currency
            raw = sec.get_json(sec.companyfacts_url(cik))
            fx = F.index_facts(raw, primary_currency(raw) or "USD")
            ends = F.quarter_ends(fx)[-QH:]
            qh = {"accn": newest}
            for key in ("capex", "revenue", "ocf"):
                qh[key] = [[e, v] for e in ends for v in [F.value(fx, key, e)] if v is not None]
            xf["qh"] = qh
        except Exception as e:
            print(f"  capex history not read for {t}: {e}", file=sys.stderr)
    if seg_hist:                                             # older instances: the segment lines' history
        done = list(xf.get("mh_accns") or [])
        mh = xf.get("mh") or {}
        for key in ("q", "k"):                               # the latest two are already read
            p = xf.get(key) or {}
            if p.get("accn") and p["accn"] not in done:
                _merge_axes(mh, p.get("axes"))
                done.append(p["accn"])
        older = [r for r in rows if r["form"] in ("10-Q", "10-K") and r["accessionNumber"] not in done]
        for r in older[:3]:
            if len(done) >= SEG_DEPTH:
                break
            try:
                inst, lab = dims.find_files(cik, r["accessionNumber"])
                if inst:
                    labels = dims.parse_labels(sec.get(lab)) if lab else {}
                    _merge_axes(mh, xfacts.parse(sec.get(inst), labels).get("axes"))
            except Exception as e:
                print(f"  older filing not read for {t} {r['accessionNumber']}: {e}", file=sys.stderr)
            done.append(r["accessionNumber"])
        xf["mh"], xf["mh_accns"] = mh, done
    if is_buyer:
        rel = next((r for r in rows if r["form"] == "8-K" and "2.02" in (r.get("items") or "")), None)
        if rel and (xf.get("guide") or {}).get("accn") != rel["accessionNumber"]:
            try:
                from .build import _exhibit
                name = _exhibit(cik, rel["accessionNumber"], rel.get("primaryDocument"))
                url = sec.doc_url(cik, rel["accessionNumber"], name)
                g = capex_guidance(text.paragraphs(sec.get(url)))
                xf["guide"] = {"accn": rel["accessionNumber"], "filed": rel["filingDate"], "url": url, "rows": g}
            except Exception as e:
                print(f"  capex outlook not read for {t}: {e}", file=sys.stderr)
    if is_investor:
        f13 = next((r for r in rows if r["form"] == "13F-HR"), None)
        if f13 and (xf.get("f13") or {}).get("accn") != f13["accessionNumber"]:
            try:
                idx = sec.get_json(sec.filing_index_url(cik, f13["accessionNumber"]))
                names = [i["name"] for i in idx.get("directory", {}).get("item", []) if i["name"].lower().endswith(".xml")]
                info = next((n for n in names if "primary_doc" not in n.lower()), None)
                if info:
                    xf["f13"] = {"accn": f13["accessionNumber"], "filed": f13["filingDate"],
                                 "period": f13.get("reportDate"), "rows": _infotable(sec.get(sec.doc_url(cik, f13["accessionNumber"], info)))[:250],
                                 "url": sec.filing_base(cik, f13["accessionNumber"]) + f"/{f13['accessionNumber']}-index.htm"}
            except Exception as e:
                print(f"  13F not read for {t}: {e}", file=sys.stderr)
    xf["v"] = VERSION * 1000 + xfacts.VERSION
    xf["checked"] = dt.datetime.utcnow().isoformat(timespec="seconds")
    rec["xf"] = xf
    if not rec.get("profile") and queue_history:                # not on the site yet: its charts are queued too
        try:
            queue_history(cik)
        except Exception:
            pass
    store.put(cik, rec)


def main():
    import argparse
    from .build import Store, load
    ap = argparse.ArgumentParser(description="Build the chains pages' data from a store (no network).")
    ap.add_argument("--store", default="store")
    ap.add_argument("--out", default="_site/data")
    ap.add_argument("--index", default=None, help="the site's data/index.json (ticker -> CIK), optional")
    a = ap.parse_args()
    ix = load(a.index, {}).get("companies") if a.index else None
    build(Store(a.store), a.out, ix)


if __name__ == "__main__":
    main()
