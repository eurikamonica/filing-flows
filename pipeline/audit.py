"""Figures that disagree with each other, found across every chart after a scan (data/audit.json; a line in the log).

Every chart is read from SEC's XBRL facts by rules; a filer's tagging slip or a rule's blind spot shows up as figures
that cannot both be right. These checks catch the patterns met so far (see the commit log of pipeline/facts.py):

- jump: revenue many times the previous quarter's (or the year-ago quarter's) while its lines barely moved (a total
  read from another tag in one period: Blue Owl's narrower "Revenues", Plexus' nine months in thousands)
- lines: revenue lines adding up to far more than revenue (a narrower total; hedging losses are a known, legitimate case)
- year: a full year's figure far from its four quarters' sum (a 10-K's tag that the quarters do not use, Nasdaq's D&A;
  a proxy statement's net income)
- fourth: a fourth quarter equal to the full year while the three quarters before were substantial (a quarter context
  carrying the year's figure, Tractor Supply)
- comparison: a chart's previous-quarter figure far from what the previous quarter's own chart shows (the stored
  figures disagree: one of the two reads is wrong)
- preliminary: a quarter still drawn from its earnings release long after the 10-Q was due (a missed filing)

The audit changes nothing: it is a list to look at (and a count to watch), written beside the site's data.
"""
import datetime as dt
import json
import os

KEYS = ("revenue", "costs", "oi", "pretax", "net", "ocf", "da", "sbc", "capex", "tax")
MISSED_DAYS = 75            # a preliminary quarter this old should have been replaced by its 10-Q / 10-K
LIMIT = 40                  # examples kept per check


def _nodes(p):
    return {n["id"]: n for n in p.get("nodes", [])}


def _rel(a, b):
    if a is None or b is None or b == 0:
        return None
    return abs(a / b - 1)


def _money(x):
    if x is None:
        return "—"
    a, s = abs(x), "-" if x < 0 else ""
    return f"{s}{a / 1e9:.2f}B" if a >= 1e9 else f"{s}{a / 1e6:.1f}M" if a >= 1e6 else f"{s}{a / 1e3:.0f}K"


def check_company(d, today=None):
    """[(check, period label, detail)] for one company's rendered file (data/c/<cik>.json)."""
    today = today or dt.date.today()
    out = []
    qs, ys = d.get("quarters") or [], d.get("years") or []
    for i, p in enumerate(qs):
        N = _nodes(p)
        R = N.get("revenue") or {}
        Rv, Rq, Ry = R.get("v"), R.get("q"), R.get("y")
        lines = [n for n in p.get("nodes", []) if n["id"].startswith("L:") and n.get("color") == "rev"]
        S = sum(n.get("v") or 0 for n in lines) if lines else None
        for prev, S_prev, word, big in ((Rq, sum(n.get("q") or 0 for n in lines) if lines else None, "previous quarter", 2.2),
                                        (Ry, sum(n.get("y") or 0 for n in lines) if lines else None, "year-ago quarter", 3.0)):
            if Rv and prev and Rv > 0 and prev > 0 and S and S_prev and S_prev > 0:
                jt, jl = Rv / prev, S / S_prev
                if (jt > big or jt < 1 / big) and 0.6 < jl < 1.6:
                    out.append(("jump", p.get("label"), f"revenue {_money(prev)} → {_money(Rv)} ({jt:.1f}×) against the "
                                                        f"{word}; its lines {_money(S_prev)} → {_money(S)}"))
        if Rv and S and Rv > 0 and S > 1.15 * Rv:
            out.append(("lines", p.get("label"), f"lines add up to {_money(S)} against revenue {_money(Rv)}"))
        if i + 1 < len(qs):
            pp = qs[i + 1]
            try:
                gap = (dt.date.fromisoformat(p["end"]) - dt.date.fromisoformat(pp["end"])).days
            except (KeyError, ValueError):
                gap = 0
            if 75 <= gap <= 105 and pp.get("form") != "8-K":
                PN = _nodes(pp)
                for k in ("revenue", "costs", "oi", "pretax", "net", "ocf"):
                    a, b = (N.get(k) or {}).get("q"), (PN.get(k) or {}).get("v")
                    r = _rel(a, b)
                    if r is not None and r > 0.3 and max(abs(a), abs(b)) > 0.02 * abs(Rv or 1):
                        out.append(("comparison", p.get("label"), f"{k}: {_money(a)} on this chart, {_money(b)} on "
                                                                  f"{pp.get('label')}'s own"))
        if p.get("form") == "8-K" and p.get("end"):
            try:
                age = (today - dt.date.fromisoformat(p["end"])).days
            except ValueError:
                age = 0
            if age >= MISSED_DAYS:
                out.append(("preliminary", p.get("label"), f"still from the earnings release {age} days after the quarter end"))
    for y in ys:
        YN = _nodes(y)
        try:
            e0 = dt.date.fromisoformat(y["end"])
        except (KeyError, ValueError):
            continue
        four = [p for p in qs if p.get("end") and 0 <= (e0 - dt.date.fromisoformat(p["end"])).days < 360]
        if len(four) != 4:
            continue
        for k in KEYS:
            vals = [(_nodes(p).get(k) or {}).get("v") for p in four]
            a = (YN.get(k) or {}).get("v")
            if a is None or any(v is None for v in vals) or abs(a) < 1e6:
                continue
            b = sum(vals)
            if abs(b / a - 1) > 0.1:
                out.append(("year", y.get("label"), f"{k}: year {_money(a)}, four quarters {_money(b)}"))
        q4 = next((p for p in four if p.get("end") == y.get("end")), None)
        if q4 and q4.get("form") == "10-K":
            QN = _nodes(q4)
            for k in KEYS:
                a, b = (QN.get(k) or {}).get("v"), (YN.get(k) or {}).get("v")
                others = [(_nodes(p).get(k) or {}).get("v") for p in four if p is not q4]
                others = [x for x in others if x is not None]
                if a is None or not b or abs(a / b - 1) > 0.02 or len(others) < 2:
                    continue
                if all(abs(x) < 0.6 * abs(b) for x in others) and sum(abs(x) for x in others) > 0.3 * abs(b):
                    out.append(("fourth", q4.get("label"), f"{k}: the fourth quarter {_money(a)} equals the year"))
    return out


def run(out_dir, today=None):
    """Audit every company file under out_dir/c; write out_dir/audit.json; return the summary dict."""
    cdir = os.path.join(out_dir, "c")
    counts, examples, companies = {}, {}, 0
    for fn in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(cdir, fn)) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        companies += 1
        name = (d.get("profile") or {}).get("name") or fn[:-5]
        for check, label, detail in check_company(d, today):
            counts[check] = counts.get(check, 0) + 1
            ex = examples.setdefault(check, [])
            if len(ex) < LIMIT:
                ex.append({"cik": fn[:-5], "name": name, "period": label, "detail": detail})
    summary = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "companies": companies,
               "counts": dict(sorted(counts.items())), "examples": examples}
    with open(os.path.join(out_dir, "audit.json"), "w") as f:
        json.dump(summary, f, separators=(",", ":"))
    words = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing"
    print(f"audit: {companies} companies; figures that disagree: {words} (data/audit.json)")
    return summary


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "data")
