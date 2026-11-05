"""The X card and the post's opening line: one point per quarter, in words and big numbers.

The site's chart (web/sankey.js, every line with its notes) stays as it is. For X a phone shows the picture a few inches
wide, so a post gets its own card instead:

    insight(c, q)            the one thing the quarter says, picked from the figures by fixed rules (see CANDIDATES):
                             {"kind", "line" (the post's opening), "headline" (the card's big text), "stats", "score"}
    spec(c, q, ins)          the chart spec for Sankey.layout with an "xcard" header: the kicker ($TICK · name · quarter),
                             the headline, two key numbers drawn large; fewer lines (the top revenue sources, no cost
                             breakdowns, no cash-flow bridge, no tiny lines, no pass-through nodes); one credit line
                             instead of the notes
    rule_post(c, q, tags)    the post written by rules (the fallback when no model writes it):
                             "$MRK: revenue grew 5% but operating profit fell 18%. Q3 2026 revenue $18.1B … 👇 #earnings"

Every number comes from the chart data (the nodes and their year-ago values); nothing is estimated. The model that
writes posts (pipeline/tweet.py) gets the insight as its suggested opening and may pick a better one from the filing.
"""
import re

from . import social

CASH_TARGET = "ocf"


def _pct(v, signed=True):
    if v is None:
        return "—"
    r = round(v)
    if r == 0:
        return "0%"
    return (("+" if r > 0 else "−") if signed else "") + f"{abs(r)}%"


def _money(v):
    return social.money(v, abs(v or 0) >= 1e9)


def _growth(now, before):
    if now is None or before is None or before <= 0 or now <= 0:
        return None
    return (now / before - 1) * 100


class Q:
    """One quarter's chart data with its year-ago values (from the links' "y")."""

    def __init__(self, c, q):
        self.c, self.q = c, q
        self.nodes = {n["id"]: n for n in q.get("nodes") or []}
        self.links = q.get("links") or []
        self.h = q.get("headline") or {}
        p = c.get("profile") or {}
        self.tick = ((p.get("tickers") or [""])[0] or "").replace("-", ".")
        self.name = social.display_name(p.get("name") or "")
        self.short = re.sub(r",?\s+(Inc|Corp|Corporation|Co|Company|Ltd|Plc|Holdings|Group|N\.?V|S\.?A|LLC|L\.?P)\.?$", "", self.name).rstrip(" ,&")

    def v(self, nid):
        n = self.nodes.get(nid)
        return n.get("v") if n else None

    def prior(self, nid, key="y"):
        """The node's value a year earlier (key "y") or a quarter earlier ("q"): its inflows' sum, else its outflows'."""
        for side in ("t", "s"):
            ls = [l for l in self.links if l.get(side) == nid]
            if ls and all(l.get(key) is not None for l in ls):
                return sum(l[key] for l in ls)
        return None

    def yoy(self, nid):
        if nid == "revenue" and self.h.get("yoy") is not None:
            return self.h["yoy"]
        return _growth(self.v(nid), self.prior(nid))

    def profit_node(self):
        """Operating profit, or (banks, insurers) pre-tax earnings."""
        for k in ("oi", "pretax"):
            if self.v(k) is not None:
                return k
        return None

    def sources(self):
        """The revenue lines that flow into revenue: [(node, link)], largest first."""
        out = [(self.nodes[l["s"]], l) for l in self.links if l.get("t") == "revenue" and l.get("s") in self.nodes]
        return sorted(out, key=lambda x: -(x[1].get("v") or 0))

    def prev_quarter(self):
        """The quarter before on file (same kind of period), or None."""
        qs = [x for x in self.c.get("quarters") or [] if x.get("end") and x.get("end") < (self.q.get("end") or "")]
        qs.sort(key=lambda x: x["end"], reverse=True)
        return qs[0] if qs else None


def _stat_rev(d):
    r = d.yoy("revenue")
    return ["Revenue", _money(d.v("revenue")), f"{_pct(r)} Y/Y" if r is not None else "", "up" if (r or 0) > 0 else "down" if (r or 0) < 0 else ""]


def _stat_profit(d):
    k = d.profit_node()
    if not k:
        return None
    g = d.yoy(k)
    lab = "Operating profit" if k == "oi" else "Pre-tax earnings"
    v = d.v(k)
    return [lab if v >= 0 else lab.replace("profit", "loss").replace("earnings", "loss"), _money(v),
            f"{_pct(g)} Y/Y" if g is not None else "", "up" if (g or 0) > 0 else "down" if (g or 0) < 0 else ""]


def _stat_margin(d):
    om, k = d.h.get("om"), d.profit_node()
    if om is None or not k:
        return None
    pv, pr = d.prior(k), d.prior("revenue")
    before = pv / pr * 100 if pv is not None and pr else None
    ch = f"{'+' if om - before >= 0 else '−'}{abs(om - before):.1f} pts Y/Y" if before is not None else ""
    return ["Operating margin", f"{om:.1f}%", ch, "up" if before is not None and om > before else "down" if before is not None and om < before else ""]


def _stat_cash(d):
    ocf, ni = d.v(CASH_TARGET), d.h.get("ni")
    if ocf is None:
        return None
    return ["Operating cash flow", _money(ocf), f"{ocf / ni * 100:.0f}% of net earnings" if ni and ni > 0 else "", ""]


def _stat_net(d):
    ni = d.h.get("ni")
    if ni is None:
        return None
    g = d.yoy("net")
    return ["Net earnings" if ni >= 0 else "Net loss", _money(abs(ni)) if ni < 0 else _money(ni),
            f"{_pct(g)} Y/Y" if g is not None else "", "up" if (g or 0) > 0 else "down" if (g or 0) < 0 else ""]


# ------------------------------------------------------------------ the candidates: (score, kind, line, headline, stats)
def _squeeze(d):
    r, k = d.yoy("revenue"), d.profit_node()
    o = d.yoy(k) if k else None
    if r is None or o is None or r < 0 or o > r - 10:
        return None
    word = "fell" if o < 0 else "rose only"
    return (80 + min(r - o, 60), "squeeze", f"revenue grew {abs(round(r))}% but {'operating profit' if k == 'oi' else 'pre-tax earnings'} {word} {abs(round(o))}%",
            f"{d.short} sold more but kept less", [_stat_rev(d), _stat_profit(d)])


def _leverage(d):
    r, k = d.yoy("revenue"), d.profit_node()
    o = d.yoy(k) if k else None
    if r is None or o is None or r < 3 or o < r + 10:
        return None
    return (70 + min(o - r, 60), "leverage", f"{'operating profit' if k == 'oi' else 'pre-tax earnings'} grew faster than sales, {_pct(o)} vs {_pct(r)}",
            "Profit is growing faster than sales", [_stat_rev(d), _stat_profit(d)])


def _pace(d):
    r, p = d.yoy("revenue"), d.prev_quarter()
    rp = ((p or {}).get("headline") or {}).get("yoy")
    if r is None or rp is None:
        return None
    if r - rp >= 5 and r > 0:
        return (60 + min(r - rp, 40), "accel", f"revenue growth sped up to {_pct(r)} from {_pct(rp)} the quarter before",
                f"Growth sped up: {_pct(r)} from {_pct(rp)}", [_stat_rev(d), _stat_profit(d) or _stat_net(d)])
    if rp - r >= 10 and rp > 0:
        return (55 + min(rp - r, 40), "decel", f"revenue growth slowed to {_pct(r)} from {_pct(rp)} the quarter before",
                f"Growth slowed: {_pct(r)} from {_pct(rp)}", [_stat_rev(d), _stat_profit(d) or _stat_net(d)])
    return None


def _segment(d):
    src = d.sources()
    rev, before = d.v("revenue"), d.prior("revenue")
    if len(src) < 2 or rev is None or before is None or rev <= before or any(l.get("y") is None for _, l in src):
        return None
    total = rev - before
    n, l = max(src, key=lambda x: x[1]["v"] - x[1]["y"])
    share = (l["v"] - l["y"]) / total
    if share < 0.6 or total / before < 0.03:
        return None
    seg = social.dec(n.get("name") or "")
    g = _growth(l["v"], l["y"])
    return (62 + share * 20, "segment", f"{seg} delivered {share * 100:.0f}% of the {_money(total)} revenue gain" + (f" ({_pct(g)} Y/Y)" if g is not None else ""),
            f"{seg} drove {share * 100:.0f}% of the growth", [_stat_rev(d), [seg, _money(l["v"]), f"{_pct(g)} Y/Y" if g is not None else "", "up" if (g or 0) > 0 else ""]])


def _cents(d):
    om, k = d.h.get("om"), d.profit_node()
    if om is None or om < 20 or not k:
        return None
    pv, pr = d.prior(k), d.prior("revenue")
    before = pv / pr * 100 if pv is not None and pr else None
    tail, bonus = "", 0
    if before is not None and om - before >= 2:
        tail, bonus = f", up from {round(before)}¢ a year ago", 15
    elif before is not None and before - om >= 2:
        tail, bonus = f", down from {round(before)}¢ a year ago", 10
    return (40 + om / 2 + bonus, "cents", f"about {round(om)}¢ of every revenue dollar is operating profit{tail}",
            f"{round(om)}¢ of every $1 of sales is operating profit", [_stat_rev(d), _stat_margin(d)])


def _cash(d):
    ocf, ni = d.v(CASH_TARGET), d.h.get("ni")
    if ocf is None or not ni or ni <= 0:
        return None
    ratio = ocf / ni
    if ocf < 0:
        return (72, "cash", f"profitable on paper, but operating cash flow was {_money(ocf)}", "Profit, but no cash", [_stat_net(d), _stat_cash(d)])
    if ratio >= 1.4:
        return (50 + min((ratio - 1) * 20, 30), "cash", f"cash came in ahead of profit — operating cash flow {_money(ocf)}, {ratio * 100:.0f}% of net earnings",
                "Cash came in ahead of profit", [_stat_net(d), _stat_cash(d)])
    if ratio <= 0.6:
        return (58, "cash", f"only {ratio * 100:.0f}% of net earnings came in as operating cash flow ({_money(ocf)})",
                "Profit that didn't turn into cash", [_stat_net(d), _stat_cash(d)])
    return None


def _loss(d):
    ni = d.h.get("ni")
    if ni is None or ni >= 0:
        return None
    before = d.prior("net")
    if before is not None and before > 0:
        return (75, "loss", f"swung to a net loss of {_money(-ni)} from a {_money(before)} profit a year ago", "Swung to a loss", [_stat_rev(d), _stat_net(d)])
    if before is not None and before < 0 and -ni < -before * 0.8:
        return (60, "loss", f"the net loss narrowed to {_money(-ni)} from {_money(-before)} a year ago", "The losses are shrinking", [_stat_rev(d), _stat_net(d)])
    if before is not None and before < 0 and -ni > -before * 1.25:
        return (62, "loss", f"the net loss widened to {_money(-ni)} from {_money(-before)} a year ago", "The losses are getting bigger", [_stat_rev(d), _stat_net(d)])
    return (45, "loss", f"still losing money — a net loss of {_money(-ni)}", "Still losing money", [_stat_rev(d), _stat_net(d)])


def _decline(d):
    r = d.yoy("revenue")
    if r is None or r > -5:
        return None
    return (60 + min(-r, 40), "decline", f"revenue fell {abs(round(r))}% from a year ago", f"Revenue down {abs(round(r))}% from a year ago",
            [_stat_rev(d), _stat_profit(d) or _stat_net(d)])


def _plain(d):
    r = d.yoy("revenue")
    rev = d.v("revenue")
    if rev is None:
        return None
    if r is None:
        return (1, "plain", f"revenue {_money(rev)}", f"Revenue {_money(rev)}", [_stat_rev(d), _stat_net(d)])
    return (1, "plain", f"revenue {'grew' if r >= 0 else 'fell'} {abs(round(r))}% to {_money(rev)}", f"Revenue {_pct(r)} to {_money(rev)}",
            [_stat_rev(d), _stat_profit(d) or _stat_net(d)])


CANDIDATES = (_squeeze, _leverage, _loss, _decline, _pace, _segment, _cash, _cents, _plain)


def insight(c, q):
    d = Q(c, q)
    best = None
    for f in CANDIDATES:
        try:
            r = f(d)
        except (TypeError, ValueError, ZeroDivisionError, KeyError):
            r = None
        if r and (best is None or r[0] > best[0]):
            best = r
    if not best:
        return None
    score, kind, line, headline, stats = best
    return {"kind": kind, "score": round(score, 1), "line": line, "headline": headline, "stats": [s for s in stats if s]}


# ------------------------------------------------------------------ the card's chart: fewer lines, bigger type
_YQ = re.compile(r"Y/Y\s*([+−-]?\d[\d.,]*%|n/m)")


def _lines(n, is_rev):
    """[(style, text)] for the card: the name, the value with its share, the Y/Y change (no Q/Q, no notes)."""
    src = n.get("lines") or [["name", n.get("name")]]
    val = next((t for st, t in src if st == "val"), None)
    yy = next((m.group(1) for st, t in src for m in [_YQ.search(t or "")] if m), None)
    out = [["xbig" if is_rev else "xname", n.get("name") or ""]]
    if val:
        out.append(["xval", val])
    if yy and yy != "n/m":
        out.append(["xup" if yy.startswith("+") else "xdn" if yy[:1] in "−-" else "xmut", f"{yy} Y/Y"])
    return out


def spec(c, q, ins=None, top_sources=3, tiny=0.015):
    """The chart spec of the X card (see the module's docstring)."""
    d = Q(c, q)
    ins = ins if ins is not None else insight(c, q)
    nodes = {n["id"]: dict(n) for n in q.get("nodes") or []}
    links = [dict(l) for l in q.get("links") or []]
    rev = d.v("revenue") or max((abs(n.get("v") or 0) for n in nodes.values()), default=1)

    # 1. no cash-flow bridge: operating cash flow and everything joined to it (without going through net earnings)
    if CASH_TARGET in nodes:
        adj = {}
        for l in links:
            if "net" not in (l["s"], l["t"]):
                adj.setdefault(l["s"], set()).add(l["t"])
                adj.setdefault(l["t"], set()).add(l["s"])
        drop, todo = set(), [CASH_TARGET]
        while todo:
            k = todo.pop()
            if k not in drop:
                drop.add(k)
                todo += list(adj.get(k, ()))
        drop |= {l["t"] for l in links if l["s"] == "net" and (nodes.get(l["t"], {}).get("color") == "noncash" or str(l["t"]).startswith("wc"))}
        links = [l for l in links if l["s"] not in drop and l["t"] not in drop]
    # 2. no cost breakdowns (SG&A, R&D … inside operating expenses): the parent line stays, whole
    links = [l for l in links if not str(l["t"]).startswith("I:")]
    # 3. only the lines that flow straight into revenue (a group's parts — iPhone and Mac inside Products — go); the
    #    largest of them, the rest as one "Other" line
    direct = {l["s"] for l in links if l["t"] == "revenue"}
    links = [l for l in links if l["t"] not in direct]
    src = sorted([l for l in links if l["t"] == "revenue"], key=lambda l: -(l["v"] or 0))
    if len(src) > top_sources + 1:
        rest = src[top_sources:]
        links = [l for l in links if l not in rest]
        other = {"s": "x:other", "t": "revenue", "v": sum(l["v"] for l in rest), "color": "rev"}
        for k in ("y", "q"):
            if all(l.get(k) is not None for l in rest):
                other[k] = sum(l[k] for l in rest)
        links.insert(top_sources, other)
        g = _growth(other["v"], other.get("y"))
        nodes["x:other"] = {"id": "x:other", "name": f"{len(rest)} other lines", "v": other["v"], "color": "rev",
                            **({"col": nodes[rest[0]["s"]]["col"]} if isinstance(nodes.get(rest[0]["s"], {}).get("col"), int) else {}),
                            "lines": [["name", f"{len(rest)} other lines"], ["val", f"{_money(other['v'])} · {other['v'] / rev * 100:.0f}% of revenue"]]
                            + ([["mut", f"Y/Y {_pct(g)}"]] if g is not None else [])}
    # 4. tiny lines at either end (under 1.5% of revenue: minority interests, a small other income) go; the main
    #    results always stay
    keep = {"revenue", "gp", "oi", "pretax", "net"}
    for _ in range(3):
        outs, ins_ = {l["s"] for l in links}, {l["t"] for l in links}
        small = {l["t"] for l in links if l["t"] not in outs and l["t"] not in keep and abs(l["v"] or 0) < tiny * rev}
        small |= {l["s"] for l in links if l["s"] not in ins_ and l["t"] != "revenue" and l["s"] not in keep and abs(l["v"] or 0) < tiny * rev}
        if not small:
            break
        links = [l for l in links if l["t"] not in small and l["s"] not in small]
    reparent = {}
    # 5. a node that only passes its whole value on (operating profit → pre-tax earnings of the same size) is skipped
    for _ in range(3):
        merged = False
        for x in list(nodes):
            into = [l for l in links if l["t"] == x]
            outs = [l for l in links if l["s"] == x]
            if len(into) != 1 or not outs or x in ("revenue", "net"):
                continue
            p = into[0]["s"]
            if [l for l in links if l["s"] == p] != into or abs(into[0]["v"] - (nodes[x].get("v") or 0)) > 0.005 * abs(nodes[x].get("v") or 1) \
                    or abs((nodes.get(p, {}).get("v") or 0) - (nodes[x].get("v") or 0)) > 0.005 * abs(nodes[x].get("v") or 1):
                continue
            links = [l for l in links if l is not into[0]]
            for l in outs:
                l["s"] = p
                reparent[l["t"]] = p                      # its share now reads "of operating profit", not "of pre-tax"
            merged = True
        if not merged:
            break
    used = {l["s"] for l in links} | {l["t"] for l in links}
    order = [n["id"] for n in q.get("nodes") or []] + ["x:other"]
    out_nodes = []
    for k in order:
        if k in used and k in nodes:
            n = dict(nodes[k])
            n["lines"] = _lines(n, k == "revenue")
            if k in reparent and n["lines"][1:2] and n["lines"][1][0] == "xval":
                pv = nodes.get(reparent[k], {}).get("v") or 0
                if pv > 0 and n.get("v") is not None:
                    sh = abs(n["v"]) / pv * 100
                    pname = social.dec(nodes[reparent[k]].get("name") or "").lower()
                    mv = social.money(n["v"], rev >= 1e9)
                    n["lines"][1][1] = f"{mv} · {sh:.0f}% of {pname}" if sh >= 9.95 else f"{mv} · {sh:.1f}% of {pname}"
            n.pop("notes", None)
            out_nodes.append(n)
    if "x:other" in used:                              # after the sources it joins, before revenue
        oth = next(n for n in out_nodes if n["id"] == "x:other")
        out_nodes.remove(oth)
        i = next((i for i, n in enumerate(out_nodes) if n["id"] == "revenue"), len(out_nodes))
        out_nodes.insert(i, oth)
    # columns without gaps: a dropped column (pre-tax earnings, the parts of a revenue group) leaves no empty stretch
    cols = sorted({n.get("col") for n in out_nodes if isinstance(n.get("col"), int)})
    if cols:
        at = {c_: i for i, c_ in enumerate(cols)}
        for n in out_nodes:
            if isinstance(n.get("col"), int):
                n["col"] = at[n["col"]]
    prelim = q.get("form") == "8-K"
    kicker = " · ".join(x for x in (f"${d.tick}" if d.tick else "", d.short, f"{q.get('label')} earnings" + (" (preliminary)" if prelim else "")) if x)
    credit = (f"From the {social.form_words(q)} filed {social.fdate(q.get('filed'))} · GAAP · filing-flows.com · @FilingFlows · "
              "read automatically by fixed rules; check the filing · not investment advice")
    xc = {"kicker": kicker, "headline": (ins or {}).get("headline") or "", "stats": (ins or {}).get("stats") or [_stat_rev(d)], "credit": credit}
    return {"nodes": out_nodes, "links": links, "label": q.get("label"), "end": q.get("end"), "title": q.get("title"), "xcard": xc}


def plain_spec(c, q):
    """The card with its numbers but no headline (engagement posts, whose text makes a different point)."""
    ins = insight(c, q) or {}
    return spec(c, q, dict(ins, headline=""))


# ------------------------------------------------------------------ the rule-based post
def rule_post(c, q, tags, limit=270):
    """'$TICK: <the point>. <quarter> revenue $X (+Y% Y/Y)[, led by Z]. 👇 #tags' — fits the limit, the extras dropped
    first."""
    d = Q(c, q)
    ins = insight(c, q)
    head = f"${d.tick}: " if d.tick else f"{d.short}: "
    point = (ins or {}).get("line") or ""
    point = point[:1].upper() + point[1:]
    r = d.yoy("revenue")
    rev = d.v("revenue")
    lab = q.get("label") or ""
    prelim = " (preliminary)" if q.get("form") == "8-K" else ""
    facts = f"{lab}{prelim} revenue {_money(rev)}" + (f" ({_pct(r)} Y/Y)" if r is not None else "") if rev is not None else f"{lab}{prelim}"
    src = d.sources()
    lead = ""
    if src and (ins or {}).get("kind") != "segment":
        n, l = src[0]
        g = _growth(l["v"], l.get("y"))
        lead = f", led by {social.dec(n.get('name') or '')}" + (f" ({_pct(g)})" if g is not None else "")
    om = d.h.get("om")
    extra = f" Operating margin {om:.1f}%." if om is not None and (ins or {}).get("kind") not in ("cents", "squeeze", "leverage") else ""
    tail = (" " + " ".join(tags)) if tags else ""
    for body in (f"{head}{point}. {facts}{lead}.{extra} 👇", f"{head}{point}. {facts}{lead}. 👇", f"{head}{point}. {facts}. 👇", f"{head}{point}. 👇"):
        for t in (tail, ""):
            if social.xlen(body + t) <= limit:
                return body + t
    return (head + point)[:limit]
