"""X posts from the follow feed's data (web/feed.js, disclosures/events-view.js): who traded a stock and when, and the
week's most-disclosed stocks. Facts from the Disclosure Hub's published tables — Form 4 insider trades
(market/insiders.json), officials' House and Senate reports (officials-trades.json), Schedules 13D / 13G
(stakes.json), Form 144 notices (form144.json) and 8-Ks (events8k.json). Registered with pipeline/xkinds.py.
"""
import datetime as dt
import re

from . import engage as E, hashtags as H, social
from .xkinds import kind

TAGS = ["#SECfilings", "#Form4", "#StocksToWatch"]


def _t(t):
    t = re.sub(r"[./\s]+", ".", str(t or "").strip().upper())
    return t if re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}", t) else ""


def _table(site, name, key):
    try:
        return E.hub_json(site, name).get(key) or []
    except Exception:
        return []


def _short(v):
    """$15K, $1.2M — the post's compact amounts (the same text goes into the task)."""
    return E.money(v) if isinstance(v, (int, float)) else ""


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def disclosed(site, today, days):
    """{ticker: [event]} of the disclosures filed in the last `days` days; an event: (date, kind, line, fact)."""
    since = (today - dt.timedelta(days=days)).isoformat()
    out = {}

    def add(t, date, k, line, fact):
        t = _t(t)
        if t and date and date[:10] >= since:
            out.setdefault(t, []).append((date[:10], k, line, fact))

    for x in _table(site, "insiders.json", "latest"):
        if x.get("code") not in ("P", "S") or not _f(x.get("shares")):
            continue
        who = social.display_name(str(x.get("insider") or "an insider")).title() if str(x.get("insider") or "").isupper() else str(x.get("insider") or "an insider")
        role = x.get("title") if x.get("title") and len(x["title"]) <= 22 else (x.get("role") or "insider")
        verb = "bought" if x["code"] == "P" else "sold"
        px = f" at ${_f(x['price']):,.2f}" if _f(x.get("price")) else ""
        line = f"{E._day(x['date'])} · {role} {who} {verb} {_f(x['shares']):,.0f} sh{px}"
        add(x.get("ticker"), x.get("date") or "", "insider", line, f"Form 4: {role} {who} {verb} {_f(x['shares']):,.0f} shares{px} on {x.get('date')}"
            + (f" ({_short(_f(x.get('value')))})" if _f(x.get("value")) else "") + (", under a 10b5-1 plan" if x.get("plan_10b5_1") else ""))
    for o in _table(site, "officials-trades.json", "trades"):
        if o.get("ticker_status") != "listed" or o.get("asset_type") == "OP":
            continue
        lo, hi = _f(o.get("amount_min")), _f(o.get("amount_max"))
        amt = f"{_short(lo)}–{_short(hi)}" if lo and hi else f"over {_short(lo - 1)}" if lo else "an undisclosed amount"
        verb = {"purchase": "bought", "sale": "sold", "partial sale": "sold part"}.get(o.get("type"), "traded")
        line = f"{E._day(o.get('date'))} · {o.get('person')} {verb} ({amt})"
        add(o.get("ticker_canon") or o.get("ticker"), o.get("filed_date") or o.get("date") or "", "official", line,
            f"{o.get('jurisdiction')} report: {o.get('person')} {verb} ({amt}), traded {o.get('date')}, reported {o.get('filed_date')}")
    for s in _table(site, "stakes.json", "latest"):
        pc = _f(s.get("percent"))
        if pc is None:
            continue
        holder = s.get("holder") or social.display_name(str(s.get("filer") or "a holder"))
        line = f"{E._day(s.get('filed'))} · {holder} reported {pc:g}% ({s.get('form')})"
        add(s.get("ticker"), s.get("filed") or "", "stake", line, f"Schedule {s.get('form')} filed {s.get('filed')}: {holder} holds {pc:g}%")
    for f in _table(site, "form144.json", "latest"):
        sh = _f(f.get("shares"))
        if not sh:
            continue
        who = f.get("seller_name") or social.display_name(str(f.get("seller") or "an insider"))
        line = f"{E._day(f.get('filed'))} · {who} filed to sell {sh:,.0f} sh (Form 144)"
        add(f.get("ticker"), f.get("filed") or "", "f144", line, f"Form 144 filed {f.get('filed')}: {who} plans to sell {sh:,.0f} shares" + (f" (~{_short(_f(f.get('value')))})" if _f(f.get("value")) else ""))
    for r in _table(site, "events8k.json", "rows"):
        add(r.get("ticker"), r.get("filed") or "", "8k", f"{E._day(r.get('filed'))} · 8-K: {r.get('label')}", f"8-K filed {r.get('filed')}: {r.get('label')}")
    return out


def _fit(head, lines, close, tags, keep=3):
    room = 250 - social.xlen(" " + " ".join(tags))
    n = len(lines)
    while n > keep and social.xlen(f"{head}\n\n" + "\n".join(lines[:n]) + f"\n\n{close}") > room:
        n -= 1
    return f"{head}\n\n" + "\n".join(lines[:n]) + f"\n\n{close}", n


@kind("who_traded", tag="disclosed", hashtags=TAGS, cooldown=20, schedule=["evening"], label="✦ Who traded it, and when",
      title="The stock with the most disclosed trades this month: insiders, officials, 13D / 13G and Form 144, dated",
      guide="A dated timeline of who traded one stock: the header with the cashtag, one line per trade exactly as listed "
            "(date · who · what · price or amount), then a short question. Line breaks. Never say the trades predict anything.", corpus=6)
def plan_who_traded(site, rows, c, by_ticker, state_ok, today):
    ev = {t: [e for e in v if e[1] != "8k"] for t, v in disclosed(site, today, 30).items()}
    cands = [(t, v) for t, v in ev.items() if len(v) >= 4 and len({e[1] for e in v}) >= 1 and state_ok("who_traded", t, hours=24 * 7)]
    if not cands:
        print("who_traded: no stock with four disclosed trades in 30 days")
        return None
    cands.sort(key=lambda tv: (tv[0] in by_ticker, len({e[1] for e in tv[1]}), len(tv[1])), reverse=True)
    t, v = cands[0]
    v = sorted(v, key=lambda e: e[0])[-8:]            # by the filing date (what "disclosed in the last 30 days" means)
    tags = H.pick("disclosed", by_ticker.get(t), key=f"who_traded:{t}:{today}")
    head = f"Who traded ${t} in the last 30 days:"
    lines = [e[2] for e in v]
    f1, n = _fit(head, lines, "What stands out to you?", tags)
    f2, _ = _fit(f"${t}, the disclosed trades of the last 30 days:", lines, "Signal or noise?", tags)
    f3, _ = _fit(f"Every disclosed ${t} trade since {E._day((today - dt.timedelta(days=30)).isoformat())}:", lines, "Which one would you look at first?", tags)
    task = (f"WHO TRADED ${t} — disclosures filed in the last 30 days (since {E._day((today - dt.timedelta(days=30)).isoformat())}; SEC Forms 4 / 144, "
            f"Schedules 13D / 13G, House and Senate reports), oldest first:\n"
            + "\n".join(f"- {e[3]} → line: “{e[2]}”" for e in v)
            + "\n\nFormat with line breaks: the header line with the cashtag, one line per trade exactly as listed, then one short question.")
    e0 = by_ticker.get(t)
    items = []
    if e0:
        try:
            cj, fq = E.figures(site, e0)
            if fq:
                items = [(e0, cj, fq)]
        except Exception:
            pass
    return {"kind": "who_traded", "task": task, "cashtags": [t], "items": items, "fallback": f1, "fallbacks": [f1, f2, f3], "lines": True, "tags": tags}


@kind("disclosure_week", tag="disclosed", hashtags=TAGS, cooldown=24 * 6, schedule=["weekly"], label="✦ Most-disclosed stocks",
      title="The stocks with the most SEC and congressional disclosures this week: insider trades, officials, 8-Ks, 13D / 13G, Form 144",
      guide="A list post: a header, one line per stock with its count of disclosures this week and what they were, then a question. Line breaks.", corpus=3)
def plan_disclosure_week(site, rows, c, by_ticker, state_ok, today):
    ev = disclosed(site, today, 7)
    NAMES = {"insider": ("insider trade", "insider trades"), "official": ("official", "officials"), "8k": ("8-K", "8-Ks"), "stake": ("13D/G", "13D/Gs"), "f144": ("Form 144", "Form 144s")}
    rank = sorted(((t, v) for t, v in ev.items() if len(v) >= 3 and state_ok("disclosure_week", t, hours=24 * 6)),
                  key=lambda tv: (len({e[1] for e in tv[1]}), len(tv[1]), tv[0] in by_ticker), reverse=True)[:6]
    if len(rank) < 3:
        print("disclosure_week: fewer than three stocks with three disclosures this week")
        return None

    def what(v):
        cnt = {}
        for e in v:
            cnt[e[1]] = cnt.get(e[1], 0) + 1
        return ", ".join(f"{n} {NAMES[k][0] if n == 1 else NAMES[k][1]}" for k, n in sorted(cnt.items(), key=lambda kv: -kv[1]))
    lines = [f"${t} — {len(v)}: {what(v)}" for t, v in rank]
    tags = H.pick("disclosed", None, key=f"disclosure_week:{today}")
    head = "The most-disclosed stocks this week (SEC and congressional filings):"
    f1, n = _fit(head, lines, "Which one would you dig into?", tags)
    f2, _ = _fit("Busiest filing week:", lines[:n], "Anything here on your list?", tags)
    picks = [t for t, _ in rank[:n]]
    task = ("THE MOST-DISCLOSED STOCKS THIS WEEK (filed in the last 7 days: Form 4 insider trades, House and Senate reports, 8-Ks, "
            "Schedules 13D / 13G, Form 144 notices):\n" + "\n".join(f"- {l}" for l in lines[:n])
            + "\n\nFormat with line breaks: the header, one line per stock exactly as listed, then a short question.")
    return {"kind": "disclosure_week", "task": task, "cashtags": picks[:2], "allowed": picks, "items": [], "fallback": f1, "fallbacks": [f1, f2],
            "lines": True, "tags": tags}
