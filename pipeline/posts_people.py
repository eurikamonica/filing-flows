"""X posts about the people behind the disclosures, the index and the analysts (Disclosures → People & index,
disclosures/app/people.py; data at data/research/people/). Registered with pipeline/xkinds.py:

  clone13f        what copying a manager's 13Fs with the filing lag returned, against SPY
  committee_trade an official's trade in a sector one of their committees oversees (a fact pattern, never an accusation)
  insider_context a new insider trade beside the history of similar trades (event study: mean, 95% interval, n)
  preview13f      an early read on a manager's next 13F from what it already filed ("our estimate")
  sp500_candidates the names that meet the S&P 500's published rules and are not members yet
  pt_hitrate      how often a stock's analysts' price targets were reached within 12 months
"""
import datetime as dt

from . import engage, social
from .xkinds import kind

RP = "research/people/"
NO_ACCUSE = (r"insider trading|corrupt|illegal|scandal|conflict of interest|profit(ed|ing) from|\bcrime\b",
             "state the trade, the committee and the dates only: a fact pattern, no accusation or verdict")
NO_ESTIMATE = (r"\bwill\b|guarantee|certain to|definitely", "an estimate: say what the filings show and that the 13F may differ")


def _rows(d):
    return [dict(zip(d.get("fields") or [], r)) for r in (d or {}).get("rows") or []]


def _file(site, name):
    try:
        return engage.hub_cached(site, RP + name)
    except Exception as err:
        print(f"people posts: {name} not available ({str(err)[:90]})")
        return None


def _pct(v, d=0):
    return engage.pct_fmt(v, d)


def _tk(t):
    return engage._tk(t)


@kind("clone13f", tag="13f", cooldown=48, schedule=["weekly", "evening"], label="✦ Copy-the-13F", corpus=6,
      title="What copying a large manager's 13Fs (bought the day after each filing) returned against SPY",
      guide="Name the manager, the period, the clone's return and SPY's over the same days, and that it bought each 13F the day after "
            "it was filed (the 45-day lag). Past returns are not a forecast; never say the manager is a good or bad investor.")
def plan_clone13f(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "managers.json")
    cands = [r for r in _rows(d) if r.get("clone_total") is not None and r.get("spy_total") is not None and (r.get("coverage") or 0) >= 0.7
             and r.get("clone_start") and state_ok("clone13f", r["cik"], hours=24 * 30)]
    if not cands:
        print("clone13f: no manager with a priced clone backtest")
        return None
    cands.sort(key=lambda r: -abs(r["excess"] or 0))
    r = cands[0]
    page = _file(site, f"m/{r['cik']}.json") or {}
    top = [h for h in (page.get("holdings") or []) if h[0]][:3]
    tks = [_tk(h[0]) for h in top]
    name = engage.short_name(r["name"])
    yrs = (dt.date.fromisoformat(r["clone_end"]) - dt.date.fromisoformat(r["clone_start"])).days / 365.25
    task = (f"COPY-THE-13F BACKTEST (Disclosures → People & index): {name} (13F filer CIK {r['cik']}). Each 13F bought at the close of the first "
            f"trading day after it was filed (about 45 days after the quarter), value-weighted, held until the next one. From {r['clone_start']} to "
            f"{r['clone_end']} ({yrs:.1f} years): the clone returned {_pct(r['clone_total'])}, SPY {_pct(r['spy_total'])} over the same days "
            f"(difference {_pct(r['excess'])}); the clone's worst drawdown {_pct(r['max_dd'])}. Price returns, no dividends or costs; "
            f"{_pct(r['coverage'])} of the portfolio had prices. Latest 13F ({r['period']}): {r['positions']} positions, "
            + (", ".join(f"${t} {_pct(h[2])}" for t, h in zip(tks, top)) if top else "") +
            ".\n\nOne post: who, the lag, the two returns, one line that it is history. Never say which to own.")
    held = (" Top holdings now: " + " ".join(f"${t}" for t in tks) + ".") if tks else ""
    top1 = f" Largest position: ${tks[0]}." if tks else ""
    f1 = f"Copying {name}'s 13F since {engage._day(r['clone_start'])}, buying the day after each filing: {_pct(r['clone_total'])}. SPY over the same days: {_pct(r['spy_total'])}.{held} Does the 45-day lag cost that much?"
    f2 = f"{name}'s 13F, copied with the 45-day filing lag ({engage._day(r['clone_start'])} → {engage._day(r['clone_end'])}): {_pct(r['clone_total'])} vs SPY {_pct(r['spy_total'])}. Worst drawdown {_pct(r['max_dd'])}.{top1} Worth the wait?"
    f3 = f"What a 13F copycat got: {name}, each filing bought the day it became public, {_pct(r['clone_total'])} since {engage._day(r['clone_start'])}; SPY {_pct(r['spy_total'])}.{top1} Skill, or the stocks everyone owns?"
    return {"task": task, "cashtags": tks[:1], "allowed": tks, "items": engage._items(site, by_ticker, tks, 2), "fallback": f1, "fallbacks": [f1, f2, f3],
            "event_key": f"clone13f:{r['cik']}", "must": (r"SPY", "give SPY's return over the same days")}


@kind("committee_trade", tag="congress", cooldown=24, schedule=["evening"], label="✦ Committee overlap", corpus=6,
      title="An official's disclosed trade in a sector one of their committees oversees (facts only)",
      guide="State who, the committee, the ticker, the trade type, the date and the amount range, and that the sector falls under that "
            "committee's jurisdiction. A fact pattern from public filings: no accusation, no motive, no verdict.")
def plan_committee_trade(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "officials.json")
    since = (today - dt.timedelta(days=60)).isoformat()
    picks = []
    for r in _rows(d):
        if not r.get("overlaps"):
            continue
        page = _file(site, f"o/{r['slug']}.json") or {}
        for o in page.get("overlaps") or []:
            if (o.get("filed") or o.get("date") or "") >= since and o.get("ticker") and state_ok("committee_trade", f"{r['slug']}:{o['ticker']}", hours=24 * 20):
                picks.append((o.get("filed") or o.get("date"), page, o))
    if not picks:
        print("committee_trade: no recent trade under a committee's jurisdiction")
        return None
    picks.sort(key=lambda x: x[0], reverse=True)
    _, p, o = picks[0]
    tk = _tk(o["ticker"])
    who = p["name"] + (f" ({(p.get('party') or '')[:1]}-{p['state']})" if p.get("party") and p.get("state") else "")
    chamber = "Senator" if p.get("chamber") == "US Senate" else "Rep."
    amt = engage.amount_range(o.get("amount_min"), o.get("amount_max"))
    verb = {"purchase": "bought", "sale": "sold", "partial sale": "sold part of a holding in", "exchange": "exchanged"}.get(o.get("type"), "traded")
    task = (f"OFFICIAL'S TRADE UNDER A COMMITTEE'S JURISDICTION (House / Senate periodic transaction report; committees from the congress-legislators "
            f"project): {chamber} {who} {verb} ${tk} ({amt}) on {o['date']}, reported {o.get('filed') or '—'}" + (f", owner: {o['owner']}" if o.get("owner") else "")
            + f". {p['name']} sits on the {o['committee']}, which oversees {o['area']}. This is a fact pattern from public filings: do not allege "
              "wrongdoing, motive or advantage.\n\nOne post: who, the trade, the committee, the dates. Ask the audience what disclosure rules should say, nothing more.")
    f1 = f"{chamber} {who} {verb} ${tk} ({amt}) on {engage._day(o['date'])}, reported {engage._day(o.get('filed') or o['date'])}. Committee: {o['committee']} — it oversees {o['area']}. Should members trade in sectors they oversee?"
    f2 = f"Disclosed: {chamber} {p['name']} {verb} ${tk}, {amt}, {engage._day(o['date'])}. Sits on the {o['committee']} ({o['area']}). Reported {engage._day(o.get('filed') or o['date'])}. Your view on the rules?"
    f3 = f"${tk}: {verb} by {chamber} {who} on {engage._day(o['date'])} ({amt}), a member of the {o['committee']}, whose remit covers {o['area']}. Facts from the filing. What would a fair rule look like?"
    return {"task": task, "cashtags": [tk], "items": engage._items(site, by_ticker, [tk], 1), "fallback": f1, "fallbacks": [f1, f2, f3],
            "forbid": NO_ACCUSE, "event_key": f"committee_trade:{p['slug']}:{tk}:{o['date']}",
            "source_reply": f"The report: {o['source_url']}" if o.get("source_url") else ""}


@kind("insider_context", tag="insider", cooldown=24, schedule=["morning"], label="✦ Insider trade in context", corpus=8,
      title="A new insider trade beside what similar trades did against SPY (event study)",
      guide="Give the trade (who, role, side, value, date), then the history of similar trades: the average excess return over SPY in "
            "the three months after disclosure, the 95% interval and how many. History is not a forecast for this trade.")
def plan_insider_context(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "insider_context.json") or {}
    cands = [t for t in d.get("recent") or [] if t.get("expected") and not t.get("plan") and (t.get("value") or 0) >= 250_000
             and t.get("ticker") and state_ok("insider_context", _tk(t["ticker"]), hours=24 * 10)]
    if not cands:
        print("insider_context: no sizeable open-market trade with a history row")
        return None
    cands.sort(key=lambda t: (-(t["expected"]["n"] >= 100), -(t.get("value") or 0)))
    t = cands[0]
    tk, x = _tk(t["ticker"]), t["expected"]
    role = t["role"]
    side = "bought" if t["side"] == "buy" else "sold"
    sz = engage.money(t["value"])
    cell = (t.get("cell") or "").split("|")
    size_lab = cell[2] if len(cell) > 2 else "this size"
    others = " with other insiders trading the same way within a month" if t.get("cluster") and len(cell) > 3 else ""
    name = t["insider"].title() if t["insider"].isupper() else t["insider"]
    task = (f"INSIDER TRADE IN CONTEXT (Form 4, open market): {name} ({role}) {side} {sz} of ${tk} on {t['date']} "
            f"({t['shares']:,.0f} shares at ${t['price']:,.2f}).\nHISTORY OF SIMILAR TRADES (event study over {d.get('trades'):,} scored "
            f"trades, {(d.get('window') or ['', ''])[0]} to {(d.get('window') or ['', ''])[1]}): {role} {'purchases' if t['side'] == 'buy' else 'sales'} of "
            f"{size_lab}{others}: the stock's return less SPY's over the 63 trading days (3 months) after disclosure averaged {_pct(x['mean'], 1)}, "
            f"95% interval {_pct(x['lo'], 1)} to {_pct(x['hi'], 1)}, n = {x['n']:,} decisions; {_pct(x['hit'])} beat SPY (median {_pct(x['median'], 1)}).\n\n"
            "One post: the trade, then the history with its interval and n, then that history is not a forecast. Never say what the stock will do.")
    hist = f"{role} {'buys' if t['side'] == 'buy' else 'sales'} of {size_lab}{others}: {_pct(x['mean'], 1)} vs SPY over 3 months on average, n={x['n']:,}, 95% CI {_pct(x['lo'], 1)} to {_pct(x['hi'], 1)}"
    f1 = f"${tk}: {name} ({role}) {side} {sz} on {engage._day(t['date'])}. Similar {hist}. History, not a forecast. How do you read it?"
    f2 = f"Insider {'purchase' if t['side'] == 'buy' else 'sale'} at ${tk}: {sz} by its {role} on {engage._day(t['date'])}. What similar trades did: {hist}. Signal or noise?"
    f3 = f"{name} ({role}) {side} {sz} of ${tk} on {engage._day(t['date'])}. The base rate for {role} {'buys' if t['side'] == 'buy' else 'sales'} of {size_lab}: {_pct(x['mean'], 1)} vs SPY after 3 months (n={x['n']:,}). Does this one differ?"
    return {"task": task, "cashtags": [tk], "items": engage._items(site, by_ticker, [tk], 1), "fallback": f1, "fallbacks": [f1, f2, f3],
            "must": (r"n\s*=\s*\d|\d+ (trades|decisions)", "give how many similar trades the history counts"),
            "event_key": f"insider_context:{tk}:{t['date']}:{t['insider']}", "source_reply": f"The Form 4: {t['url']}" if t.get("url") else ""}


@kind("preview13f", tag="13f", cooldown=48, schedule=["weekly"], label="✦ Next 13F preview", corpus=4,
      title="An early read on a manager's next 13F from the filings it has already made this quarter (an estimate)",
      guide="Say it is an estimate from early filings (Form 4s, 13D / 13G) and the drifted weights; name the manager, the quarter, the "
            "due date and the likely adds or cuts with their source. The 13F may differ; never present it as the filing.")
def plan_preview13f(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "preview13f.json") or {}
    cands = [p for p in d.get("previews") or [] if p.get("predictions") and state_ok("preview13f", p["cik"], hours=24 * 14)]
    if not cands:
        print("preview13f: no early filings by the tracked managers")
        return None
    cands.sort(key=lambda p: -len(p["predictions"]))
    p = cands[0]
    name = engage.short_name(p["name"])
    preds = p["predictions"][:4]
    tks = [_tk(x["ticker"]) for x in preds]
    lines = "; ".join(f"${_tk(x['ticker'])} {'likely added' if x['d'] > 0 else 'likely cut' if x['d'] < 0 else 'mixed'} "
                      f"({', '.join(e['source'] + ' ' + e['date'] for e in x['evidence'][:2])})" for x in preds)
    score = f" Earlier previews: {d['predictions_scored']} scored, {_pct(d['hit_rate'])} right." if d.get("predictions_scored") else ""
    task = (f"13F PREVIEW (an estimate, Disclosures → People & index): {name}'s 13F for the quarter ended {p['quarter']} is due {p['due']}. "
            f"What it has already filed since its last 13F ({p['base_period']}): {lines}.{score}\n\nOne post: the manager, the due date, the early "
            "signals with their source, and that the 13F may differ. Never say it will happen.")
    f1 = f"{name}'s 13F is due {engage._day(p['due'])}. Early filings this quarter already show: {lines}. Our estimate from the filings, not the 13F itself. What else changed?"
    f2 = f"Before the 13F (due {engage._day(p['due'])}): {name}'s own Form 4s and 13D / 13G filings point to {lines}. An estimate; the filing may differ. What do you expect?"
    return {"task": task, "cashtags": tks[:1], "allowed": tks, "items": engage._items(site, by_ticker, tks, 2), "fallback": f1, "fallbacks": [f1, f2],
            "forbid": NO_ESTIMATE, "must": (r"estimate|may differ", "say it is an estimate"), "event_key": f"preview13f:{p['cik']}:{p['quarter']}"}


@kind("sp500_candidates", tag="index", hashtags=["#SP500", "#IndexInclusion", "#stocks"], cooldown=72, schedule=["weekly"], corpus=3,
      label="✦ S&P 500 candidates", title="Names that meet the S&P 500's published rules and are not members yet",
      guide="List the cashtags with market caps; say they meet the published rules (size, four quarters of positive GAAP earnings, "
            "liquidity) and that the index committee decides and only when a seat opens. No prediction of a price move.")
def plan_sp500_candidates(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "sp500.json") or {}
    el = [r for r in _rows(d) if r.get("eligible") and state_ok("sp500_candidates", r["ticker"], hours=24 * 20)][:6]
    if len(el) < 3:
        print("sp500_candidates: fewer than three eligible names")
        return None
    tks = [_tk(r["ticker"]) for r in el]
    lines = "\n".join(f"${_tk(r['ticker'])} {engage.money(r['mcap'])}" for r in el)
    rec = f" Track record: {d['joined_within_year']} of {d['resolved']} earlier calls joined within a year." if d.get("resolved") else ""
    task = (f"S&P 500 INCLUSION SCREEN ({len(el)} shown; {d.get('members')} members on file): US companies above S&P's {engage.money(d['threshold'])} market-cap "
            f"minimum, with the last four quarters' GAAP net income positive and the latest quarter positive, liquid, not in the index:\n"
            + "\n".join(f"- ${_tk(r['ticker'])} ({r['name']}): market cap {engage.money(r['mcap'])}, net income last 4 quarters {engage.money(r['ni_4q'])}, "
                        f"first flagged {r.get('first_flagged')}" for r in el) + f"{rec}\n\nFormat with line breaks: a headline, one “$TICKER $cap” line each, "
            "then that the committee decides when a seat opens. No prediction.")
    f1 = f"Meets the S&P 500 rules, not in the index yet:\n\n{lines}\n\nSize, four profitable quarters, liquidity. The committee picks when a seat opens. Who goes in next?"
    f2 = f"S&P 500 candidates by the published rules:\n\n{lines}\n\nAll above the {engage.money(d['threshold'])} line with positive GAAP earnings. Which one gets the call?"
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": engage._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True,
            "forbid": (r"\bwill (be )?(join|add|includ)|guaranteed", "the committee decides: no prediction")}


@kind("pt_hitrate", tag="analysts", cooldown=48, schedule=["evening"], label="✦ Price-target hit rate", corpus=6,
      title="How often a stock's analysts' price targets were reached within 12 months",
      guide="Give the stock, how many monthly targets were tracked, how many reached within 12 months (the hit rate), and the price "
            "against the target 12 months on. Only targets whose 12 months are over count; say since when.")
def plan_pt_hitrate(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "pt_hits.json") or {}
    cands = [r for r in _rows(d) if (r.get("resolved") or 0) >= 6 and state_ok("pt_hitrate", r["ticker"], hours=24 * 30)]
    if not cands:
        print("pt_hitrate: no stock with six resolved targets yet (the record starts with the consensus snapshots on file)")
        return None
    cands.sort(key=lambda r: (_tk(r["ticker"]) not in by_ticker, -(r["resolved"] or 0)))
    r = cands[0]
    tk = _tk(r["ticker"])
    name = engage.short_name(r.get("name") or tk, tk)
    err = f" Twelve months on, the price sat {_pct(r['median_error_12m'])} from the target (median)." if r.get("median_error_12m") is not None else ""
    task = (f"ANALYSTS' PRICE-TARGET RECORD for ${tk} ({name}), from daily consensus snapshots since {d.get('tracking_since')}: {r['resolved']} monthly mean "
            f"targets with their 12 months over; {r['hits']} were reached ({_pct(r['hit_rate'])}).{err} {r['pending']} targets are still inside their window"
            + (f", {r['touched_so_far']} of them touched already" if r.get("touched_so_far") else "") + ".\n\nOne post: the hit rate with its counts, the error, since when. No advice.")
    f1 = f"${tk} analysts' price targets: {r['hits']} of {r['resolved']} reached within 12 months ({_pct(r['hit_rate'])}), tracked since {engage._day(d['tracking_since'])}.{err} Useful, or noise?"
    f2 = f"How good are the targets on ${tk}? {_pct(r['hit_rate'])} of {r['resolved']} mean price targets were hit within a year.{err} Would you follow them?"
    return {"task": task, "cashtags": [tk], "items": engage._items(site, by_ticker, [tk], 1), "fallback": f1, "fallbacks": [f1, f2],
            "must": (r"\d+ of \d+|\d+%", "give the counts or the rate")}
