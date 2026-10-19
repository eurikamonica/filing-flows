"""X posts for earnings season (Disclosures → Earnings season; disclosures/app/earnings_season.py, branch
research-earnings, published at disclosures/data/research/earnings/).

    earn_preview      the most-watched report of the next session: consensus, Polymarket, our model, implied vs usual move
    earn_three_way    this week's reporters: Polymarket vs our model, side by side
    earn_scorecard    the week's scorecard: how many beat, how many calls Polymarket and our model got right
    earn_moves        priced vs delivered: the options-implied move against the actual move after the report
    earn_pead         the post-earnings drift model's largest predictions (60 sessions vs SPY, with its 80% range)
    earn_breadth      the season so far: beat rate, surprise, strongest and weakest sector, estimates raised vs cut
    earn_squeeze      highest short-squeeze scores (short interest × days to cover × momentum)
    earn_nongaap      adjusted vs GAAP EPS: where the gap just widened
    earn_vrp          options pricing far more (or less) volatility than the stock has shown
    earn_readthrough  peers already reported: the read-through for the ones still to report
    earn_dist         one stock's price on a date: Polymarket's median against the options market's

Every number in a post is in the plan's task (the facts); rule-written phrasings ("fallbacks") are used when no model
answers and train the local models (pipeline/corpus.py). Not investment advice: the posts never say what to do.
"""
import datetime as dt
import re

from . import engage as E
from .xkinds import kind

HUB = "research/earnings/"


def _hub(site, name):
    try:
        return E.hub_cached(site, HUB + name)
    except Exception as err:                       # noqa: BLE001 — not published yet
        print(f"earnings posts: {name} not available ({str(err)[:90]})")
        return None


def _rows(d):
    if not d:
        return []
    F = d.get("fields")
    return [dict(zip(F, r)) for r in d.get("rows") or []] if F else list(d.get("rows") or [])


def fname(t):
    return re.sub(r"[^A-Za-z0-9-]", "_", str(t).upper().replace(".", "-"))


def tk(t):
    return E._tk(t)


def pc(v, d=0):
    return f"{v * 100:.{d}f}%"


def spc(v, d=1):
    return E.pct_fmt(v, d)


def wday(iso):
    d = dt.date.fromisoformat(iso[:10])
    return f"{d:%a} {d:%b} {d.day}"


def fin(v):
    return isinstance(v, (int, float)) and v == v


def _fit(head, lines, close, limit=215):
    """head + lines + close, dropping lines from the end (never below three) until it fits."""
    k = len(lines)
    while k > 3 and E.social.xlen(f"{head}\n\n" + "\n".join(lines[:k]) + f"\n\n{close}") > limit:
        k -= 1
    return f"{head}\n\n" + "\n".join(lines[:k]) + f"\n\n{close}", k


# ------------------------------------------------------------------ previews
@kind("earn_preview", tag="earnings", schedule=["evening", "morning"], cooldown=10, label="✦ Earnings preview",
      title="The most-watched report of the next session: consensus, Polymarket, our model, the options-implied vs usual move",
      guide="First line “$TICKER reports <day>”, then 3–5 bullet lines starting with “• ” (consensus EPS and analysts, Polymarket's beat "
            "odds, our model's probability, the options-implied move against the usual move, the beat record), then one short question. "
            "Say “our model” for the site's probability. Never say what the stock will do.", corpus=8)
def plan_earn_preview(site, rows, c, by_ticker, state_ok, today):
    ix = _rows(_hub(site, "index.json"))
    last = E.next_trading_day(E.next_trading_day(today)).isoformat()      # the next session, or the one after it
    cands = [r for r in ix if r.get("report_date") and today.isoformat() <= r["report_date"] <= last
             and state_ok("earn_preview", tk(r["ticker"]), hours=24 * 20)]
    cands.sort(key=lambda r: r["report_date"])
    if cands:
        cands = [r for r in cands if r["report_date"] == cands[0]["report_date"]]
    cands.sort(key=lambda r: (r.get("polymarket") is not None, r.get("implied") is not None, tk(r["ticker"]) in by_ticker, r.get("n") or 0), reverse=True)
    for r in cands[:12]:
        t = tk(r["ticker"])
        d = _hub(site, f"c/{fname(r['ticker'])}.json")
        if not d:
            continue
        cons, pm, m, im = d.get("consensus") or {}, d.get("polymarket") or {}, d.get("model") or {}, d.get("implied") or {}
        hist = d.get("history") or []
        facts = []
        if fin(cons.get("eps")):
            facts.append(f"Street EPS {E.eps_fmt(cons['eps'])}" + (f" ({cons['n']:.0f} analysts)" if fin(cons.get("n")) else ""))
        if fin(pm.get("p")):
            facts.append(f"Polymarket: {pc(pm['p'])} chance of a beat")
        if fin(m.get("p")):
            facts.append(f"Our model: {pc(m['p'])} chance of a beat")
        avg = d.get("avg_move")
        if fin(im.get("move")) and fin(avg):
            facts.append(f"Options price a ±{pc(im['move'], 1)} move; the usual move is ±{pc(avg, 1)}")
        elif fin(avg):
            facts.append(f"Usual move after a report: ±{pc(avg, 1)}")
        if len(hist) >= 3:
            facts.append(f"Beat {sum(h['beat'] for h in hist)} of the last {len(hist)} quarters")
        if len(facts) < 3:
            continue
        day = wday(r["report_date"])
        if fin(im.get("move")) and fin(avg) and avg:
            q = "Is the options market too nervous?" if im["move"] > 1.15 * avg else "Is the options market too calm?" if im["move"] < 0.85 * avg else "Fairly priced?"
        else:
            q = "Beat or miss?"
        task = (f"${t} ({d.get('name')}) REPORTS {day.upper()} (quarter ending {d.get('quarter')}). The facts (use only these):\n"
                + "\n".join(f"- {f}" for f in facts)
                + "\n\nFormat: first line “$TICKER reports <day>”, then the facts as bullet lines starting with “• ”, then one short question. "
                  "“Our model” is the site's own probability (a logistic model of earlier reports). No prediction of the stock, no advice.")

        def fb(intro, close, nb):
            body = "\n".join("• " + f for f in facts[:nb])
            txt = f"{intro}\n\n{body}\n\n{close}"
            while E.social.xlen(txt) > 225 and nb > 3:
                nb -= 1
                body = "\n".join("• " + f for f in facts[:nb])
                txt = f"{intro}\n\n{body}\n\n{close}"
            return txt
        f1 = fb(f"${t} reports {day}", q, 5)
        f2 = fb(f"Into ${t} earnings ({day}):", "Who's closer: the crowd, the options or the model?", 4)
        f3 = fb(f"${t} earnings, {day}", "Beat or miss?", 3)
        return {"task": task, "cashtags": [t], "items": E._items(site, by_ticker, [t], 1), "fallback": f1, "fallbacks": [f1, f2, f3], "lines": True}
    print("earn_preview: no previewed report in the next session")
    return None


@kind("earn_three_way", tag="polymarket", schedule=["morning"], cooldown=72, label="✦ Polymarket vs our model (this week)",
      title="This week's reporters: Polymarket's beat odds next to our model's",
      guide="A headline line, one line per company “$TICKER <day>: Polymarket NN% · our model NN%”, then a question about where they disagree.",
      corpus=4)
def plan_earn_three_way(site, rows, c, by_ticker, state_ok, today):
    ix = _rows(_hub(site, "index.json"))
    soon = (today + dt.timedelta(days=6)).isoformat()
    cands = [r for r in ix if r.get("report_date") and today.isoformat() <= r["report_date"] <= soon and fin(r.get("polymarket")) and fin(r.get("model"))
             and state_ok("earn_three_way", tk(r["ticker"]), hours=24 * 6)]
    cands.sort(key=lambda r: (abs(r["polymarket"] - r["model"]), r.get("n") or 0), reverse=True)
    picks = cands[:5]
    if len(picks) < 3:
        print("earn_three_way: fewer than three reporters with both Polymarket odds and our model")
        return None
    picks.sort(key=lambda r: r["report_date"])
    lines = [f"${tk(r['ticker'])} {wday(r['report_date'])[:3]}: Polymarket {pc(r['polymarket'])} · our model {pc(r['model'])}" for r in picks]
    task = ("WILL THEY BEAT? This week's reporters with a Polymarket beat market, and the site's own model (a logistic model of earlier "
            "reports), with the analysts' consensus EPS:\n"
            + "\n".join(f"- ${tk(r['ticker'])} reports {wday(r['report_date'])}: Polymarket {pc(r['polymarket'])}; our model {pc(r['model'])}; consensus EPS "
                        f"{E.eps_fmt(r.get('eps'))}" for r in picks)
            + "\n\nFormat with line breaks: a headline, one line per company exactly as “$TICKER <day>: Polymarket NN% · our model NN%”, then a question.")
    f1, k = _fit("Will they beat? Polymarket vs our model this week:", lines, "Where would you side with the model?")
    f2, _ = _fit("Earnings this week, odds of a beat:", lines[:k], "Who's right on each?")
    tks = [tk(r["ticker"]) for r in picks[:k]]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


# ------------------------------------------------------------------ after the reports
@kind("earn_scorecard", tag="earnings", schedule=["weekly"], cooldown=24 * 5, label="✦ Earnings scorecard (week)",
      title="The week's reports: how many beat, how many calls Polymarket and our model got right",
      guide="One or two sentences: the week, how many reports beat, Polymarket's and our model's right calls (say whether ours was "
            "frozen before each report), optionally the biggest upset with its cashtag. End with a question.", corpus=3)
def plan_earn_scorecard(site, rows, c, by_ticker, state_ok, today):
    sc = _hub(site, "scorecard.json")
    if not sc:
        return None
    weeks = [w for w in sc.get("weeks") or [] if w["week"] < (today - dt.timedelta(days=today.weekday())).isoformat() and (w.get("pm_n") or 0) >= 3]
    if not weeks:
        print("earn_scorecard: no complete week with three Polymarket calls")
        return None
    w = weeks[0]
    if not state_ok("earn_scorecard", w["week"], hours=24 * 30):
        return None
    wk_end = (dt.date.fromisoformat(w["week"]) + dt.timedelta(days=6)).isoformat()
    rows_ = [r for r in sc.get("rows") or [] if w["week"] <= r["reported"] <= wk_end]
    upset = max([r for r in rows_ if r.get("polymarket_right") == 0 and fin(r.get("surprise"))], key=lambda r: abs(r["surprise"]), default=None)
    frozen = (w.get("frozen_n") or 0) >= 3
    mr, mn = (w["frozen_right"], w["frozen_n"]) if frozen else (w["model_right"], w["model_n"])
    how = "frozen before each report" if frozen else "walk-forward backtest"
    lab = E._day(w["week"])
    task = (f"EARNINGS SCORECARD, week of {lab} ({w['week']}): {w['beats']} of {w['n']} reports beat the EPS consensus. Polymarket (price 24 hours "
            f"before) called {w['pm_right']} of {w['pm_n']} right; our model ({how}) called {mr} of {mn} right."
            + (f" Reports inside the options-implied move: {w['moves_inside']} of {w['moves_n']}." if w.get("moves_n") else "")
            + (f"\nBiggest upset for Polymarket: ${tk(upset['ticker'])} — Polymarket had {pc(upset['polymarket'])} on a beat, EPS surprise "
               f"{spc(upset['surprise'])}." if upset else "")
            + "\n\nWrite one or two sentences with these counts, then a question. A call is right when the probability was on the result's side of 50%.")
    up = (f" Biggest upset: ${tk(upset['ticker'])} (Polymarket {pc(upset['polymarket'])}, EPS {spc(upset['surprise'])})." if upset else "")
    f1 = (f"Earnings week of {lab}: {w['beats']} of {w['n']} reports beat. Polymarket called {w['pm_right']} of {w['pm_n']}; our model ({how}) "
          f"{mr} of {mn}.{up} Who do you trust next week?")
    f2 = (f"Scorecard, week of {lab}: Polymarket {w['pm_right']}/{w['pm_n']}, our model {mr}/{mn} on beat-or-miss calls. "
          f"{w['beats']} of {w['n']} reports beat.{up} Crowd or model?")
    cash = [tk(upset["ticker"])] if upset else []
    return {"task": task, "cashtags": cash, "items": E._items(site, by_ticker, cash, 1), "fallback": f1, "fallbacks": [f1, f2],
            "event_key": f"earn_scorecard:{w['week']}"}


@kind("earn_moves", tag="earnings", schedule=["close"], cooldown=20, label="✦ Priced vs delivered (moves)",
      title="The options-implied move against the actual move after the last reports",
      guide="A headline, one line per company “$TICKER: options ±N% → moved ±M%”, then how many stayed inside the implied move.", corpus=4)
def plan_earn_moves(site, rows, c, by_ticker, state_ok, today):
    sc = _hub(site, "scorecard.json")
    since = (today - dt.timedelta(days=4)).isoformat()
    rs = [r for r in (sc or {}).get("rows") or [] if r["reported"] >= since and fin(r.get("implied")) and fin(r.get("move")) and r["implied"] > 0
          and state_ok("earn_moves", tk(r["ticker"]), hours=24 * 10)]
    rs.sort(key=lambda r: abs(r["move"]) / r["implied"], reverse=True)
    picks = rs[:5]
    if len(picks) < 3:
        print("earn_moves: fewer than three reports with an implied move and a result")
        return None
    inside = sum(1 for r in picks if abs(r["move"]) <= r["implied"])
    lines = [f"${tk(r['ticker'])}: options ±{pc(r['implied'], 1)} → moved {spc(r['move'])}" for r in picks]
    task = ("PRICED VS DELIVERED after the latest earnings (options-implied move frozen before the report; actual move = close before the report "
            "to the close after):\n" + "\n".join(f"- {l}" for l in lines)
            + f"\n{inside} of {len(picks)} stayed inside the implied move.\n\nFormat with line breaks: a headline, the lines as given, then one closing line.")
    f1, k = _fit("Priced vs delivered after earnings:", lines, f"{inside} of {len(picks)} stayed inside the options-implied move. Surprised?")
    f2, _ = _fit("What the options priced, what the stock did:", lines[:k], "Which one did you see coming?")
    tks = [tk(r["ticker"]) for r in picks[:k]]
    if k < len(picks):
        f1 = f1.replace(f"{inside} of {len(picks)} stayed inside the options-implied move. Surprised?", "Which move surprised you most?")
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


@kind("earn_pead", tag="earnings", schedule=["close"], cooldown=48, label="✦ Post-earnings drift",
      title="The drift model's largest predictions for the 60 sessions after the latest reports",
      guide="A headline saying it is the site's post-earnings drift model (60 sessions vs SPY), one line per company with its prediction, then "
            "the 80% range and that it is a model, not a promise.", corpus=3)
def plan_earn_pead(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "pead.json")
    since = (today - dt.timedelta(days=7)).isoformat()
    rs = [r for r in (d or {}).get("rows") or [] if r["reported"] >= since and fin(r.get("pred")) and state_ok("earn_pead", tk(r["ticker"]), hours=24 * 20)]
    up = sorted([r for r in rs if r["pred"] > 0], key=lambda r: -r["pred"])[:3]
    dn = sorted([r for r in rs if r["pred"] < 0], key=lambda r: r["pred"])[:2]
    picks = up + dn
    w = (d or {}).get("interval80")
    if len(picks) < 3 or not fin(w):
        print("earn_pead: fewer than three recent drift predictions")
        return None
    lines = [f"${tk(r['ticker'])} {spc(r['pred'])}" for r in picks]
    task = ("POST-EARNINGS DRIFT, the site's model (linear, fitted walk-forward on past reports: standardised surprise, surprise, two-session "
            "reaction): predicted excess return vs SPY over the next 60 sessions —\n"
            + "\n".join(f"- ${tk(r['ticker'])} reported {r['reported']}, EPS surprise {spc(r['surprise'])}: {spc(r['pred'])}" for r in picks)
            + f"\nIts 80% range is ±{pc(w)} around each prediction.\n\nFormat with line breaks; say it is a model with a wide range.")
    f1, k = _fit("Our post-earnings drift model, next 60 sessions vs SPY:", lines, f"80% range: ±{pc(w)}. A model, not a promise. Agree?")
    f2, _ = _fit("After the report, the drift our model predicts (vs SPY, 60 sessions):", lines[:k], f"Wide range (±{pc(w)}). Which call looks wrong?")
    tks = [tk(r["ticker"]) for r in picks[:k]]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


def season_label(s):
    m = re.match(r"CY(\d{4})Q(\d)", s or "")
    return f"Q{m.group(2)} {m.group(1)}" if m else (s or "")


@kind("earn_breadth", tag="earnings", schedule=["weekly"], cooldown=24 * 3, label="✦ Earnings season so far",
      title="The season so far: beat rate against last season, surprise, strongest and weakest sector, estimates raised vs cut",
      guide="Two sentences: the season's beat rate against the season before and the mean surprise; the strongest and weakest sector with "
            "their counts. End with a question. No cashtags needed.", corpus=3)
def plan_earn_breadth(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "season.json")
    o = (d or {}).get("overall") or {}
    if (o.get("n") or 0) < 20 or not state_ok("earn_breadth", d.get("season"), hours=24 * 3):
        print("earn_breadth: fewer than twenty reports this season")
        return None
    p = d.get("previous") or {}
    secs = [s for s in d.get("sectors") or [] if (s.get("n") or 0) >= 5 and fin(s.get("beat_pct"))]
    best = max(secs, key=lambda s: s["beat_pct"], default=None)
    worst = min(secs, key=lambda s: s["beat_pct"], default=None)
    lab, plab = season_label(d["season"]), season_label(p.get("season"))
    facts = [f"{o['beats']} of {o['n']} reports beat EPS estimates ({pc(o['beat_pct'])})"]
    if fin(p.get("beat_pct")):
        facts.append(f"{plab}: {pc(p['beat_pct'])} of {p['n']}")
    if fin(o.get("mean_surprise")):
        facts.append(f"mean surprise {spc(o['mean_surprise'])}")
    if best and worst and best is not worst:
        facts.append(f"strongest: {best['sector']} {pc(best['beat_pct'])} ({best['n']}); weakest: {worst['sector']} {pc(worst['beat_pct'])} ({worst['n']})")
    if (o.get("est_n") or 0) >= 10:
        facts.append(f"estimates a week after the report: {o['est_raised']} raised, {o['est_cut']} cut")
    task = (f"{lab.upper()} EARNINGS SEASON SO FAR (actual EPS vs the average estimate):\n" + "\n".join(f"- {f}" for f in facts)
            + "\n\nTwo sentences with these numbers, then a question. No advice.")
    sec = (f" Strongest: {best['sector']} {pc(best['beat_pct'])} ({best['n']}); weakest: {worst['sector']} {pc(worst['beat_pct'])} ({worst['n']})."
           if best and worst and best is not worst else "")
    prev = f" ({plab}: {pc(p['beat_pct'])})" if fin(p.get("beat_pct")) else ""
    ms = f" Mean surprise {spc(o['mean_surprise'])}." if fin(o.get("mean_surprise")) else ""
    f1 = f"{lab} earnings so far: {pc(o['beat_pct'])} of {o['n']} reports beat EPS estimates{prev}.{ms}{sec} Is the bar too low?"
    if E.social.xlen(f1) > 230:
        f1 = f"{lab} earnings so far: {pc(o['beat_pct'])} of {o['n']} reports beat EPS estimates{prev}.{ms} Is the bar too low?"
    f2 = f"{o['beats']} of {o['n']} companies have beaten EPS estimates this season ({lab}){prev}.{sec} Which sector surprises next?"
    if E.social.xlen(f2) > 230:
        f2 = f"{o['beats']} of {o['n']} companies have beaten EPS estimates this season ({lab}){prev}. Which sector surprises next?"
    return {"task": task, "cashtags": [], "items": [], "fallback": f1, "fallbacks": [f1, f2], "event_key": f"earn_breadth:{d['season']}:{o['n']}"}


# ------------------------------------------------------------------ indicators
@kind("earn_squeeze", tag="short", schedule=["morning"], cooldown=72, label="✦ Short squeeze scores",
      title="Highest short-squeeze scores: short interest × days to cover × momentum",
      guide="A headline naming the score's parts, one line per stock “$TICKER N% short · N days to cover”, then that it is a ranking, not a forecast.",
      corpus=3)
def plan_earn_squeeze(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "squeeze.json")
    rs = [r for r in (d or {}).get("rows") or [] if state_ok("earn_squeeze", tk(r["ticker"]), hours=24 * 14)][:5]
    if len(rs) < 3:
        print("earn_squeeze: fewer than three ranked names")
        return None
    lines = [f"${tk(r['ticker'])} {pc(r['short_pct'], 1)} short · {r['dtc']:.1f} days to cover" for r in rs]
    task = ("SHORT-SQUEEZE SCORE = short interest as a share of shares outstanding × days to cover × (1 + one-month return); FINRA short interest "
            f"(settlement {(d or {}).get('settlement_date') or 'latest'}). Highest now:\n"
            + "\n".join(f"- ${tk(r['ticker'])} ({r.get('name')}): {pc(r['short_pct'], 1)} of shares short, {r['dtc']:.1f} days to cover, one-month return "
                        f"{spc(r['momentum'])}" for r in rs)
            + "\n\nFormat with line breaks: a headline, one line per stock, then that it is a ranking, not a forecast.")
    f1, k = _fit("Highest short-squeeze scores (short interest × days to cover × momentum):", lines, "A ranking, not a forecast. Which one are you watching?")
    f2, _ = _fit("Crowded shorts, slow to cover:", lines[:k], "Which of these squeezes first, if any?")
    tks = [tk(r["ticker"]) for r in rs[:k]]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


@kind("earn_nongaap", tag="earnings", schedule=["weekly"], cooldown=24 * 6, label="✦ Adjusted vs GAAP gap",
      title="Where adjusted (Street) EPS pulled furthest away from GAAP diluted EPS last quarter",
      guide="A headline, one line per company “$TICKER Street $X vs GAAP $Y”, then a question about the adjustments. Never call it fraud.", corpus=3)
def plan_earn_nongaap(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "nongaap.json")
    rs = [r for r in (d or {}).get("rows") or [] if r.get("flag") and r.get("points") and state_ok("earn_nongaap", tk(r["ticker"]), hours=24 * 60)][:4]
    if len(rs) < 2:
        print("earn_nongaap: fewer than two widening gaps")
        return None
    lines = []
    for r in rs:
        pt = r["points"][-1]
        lines.append(f"${tk(r['ticker'])} Street {E.eps_fmt(pt['street'])} vs GAAP {E.eps_fmt(pt['gaap'])} (gap {pc(r['gap_pct'])}, was {pc(r['gap_prev_mean'])})")
    task = ("ADJUSTED VS GAAP EPS, latest quarter: Street EPS (the actual the consensus records, usually adjusted) against GAAP diluted EPS from the "
            "10-Q / 10-K (SEC XBRL); the gap as a share of Street EPS, now and the average of the quarters before:\n" + "\n".join(f"- {l}" for l in lines)
            + "\n\nFormat with line breaks: a headline, the lines, then a question about the adjustments. Neutral wording: never imply wrongdoing.")
    head = "Adjusted vs GAAP EPS: where the gap just widened"
    k = len(lines)
    while k > 2 and E.social.xlen(f"{head}\n\n" + "\n".join(lines[:k]) + "\n\nWhich adjustments would you question?") > 230:
        k -= 1
    f1 = f"{head}\n\n" + "\n".join(lines[:k]) + "\n\nWhich adjustments would you question?"
    f2 = "Street EPS vs GAAP, last quarter:\n\n" + "\n".join(lines[:k]) + "\n\nOne-offs, or a habit?"
    tks = [tk(r["ticker"]) for r in rs[:k]]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


@kind("earn_vrp", tag="options", hashtags=["#options", "#volatility", "#stocks"], schedule=["morning"], cooldown=48,
      label="✦ Implied vs realised volatility", title="Options pricing far more volatility than the stock has shown (30-day IV vs realised)",
      guide="A headline, one line per stock “$TICKER IV N% vs realised N%”, then a question (fear, or a catalyst ahead?).", corpus=3)
def plan_earn_vrp(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "options.json")
    rs = [r for r in (d or {}).get("rows") or [] if fin(r.get("vrp")) and fin(r.get("iv30")) and fin(r.get("rv30")) and r["vrp"] >= 0.08
          and state_ok("earn_vrp", tk(r["ticker"]), hours=24 * 7)]
    rs.sort(key=lambda r: -r["vrp"])
    rs = rs[:5]
    if len(rs) < 3:
        print("earn_vrp: fewer than three stocks with implied volatility well above realised")
        return None
    lines = [f"${tk(r['ticker'])} IV {pc(r['iv30'])} vs realised {pc(r['rv30'])}" for r in rs]
    task = ("OPTIONS PRICING MORE VOLATILITY THAN THE STOCK HAS SHOWN: 30-day implied volatility (CBOE) against 30-day realised volatility from "
            "daily closes —\n" + "\n".join(f"- {l} ({r.get('name') or ''})" for l, r in zip(lines, rs))
            + "\n\nFormat with line breaks: a headline, the lines, then a question.")
    f1, k = _fit("Options pricing far more volatility than the stock has shown (30-day implied vs realised):", lines, "Fear, or a catalyst ahead?")
    f2, _ = _fit("Implied vol way above realised:", lines[:k], "Which one is the options market right about?")
    tks = [tk(r["ticker"]) for r in rs[:k]]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2], "lines": True}


@kind("earn_readthrough", tag="earnings", schedule=["morning"], cooldown=72, label="✦ Peer read-through",
      title="A sector's peers already reported: the read-through for the ones still to report",
      guide="One or two sentences: the sector's average EPS surprise so far, which companies still report (cashtags with dates), what the "
            "read-through says, then a question.", corpus=3)
def plan_earn_readthrough(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "readthrough.json")
    soon = (today + dt.timedelta(days=7)).isoformat()
    rs = [r for r in (d or {}).get("rows") or [] if today.isoformat() <= (r.get("report_date") or "") <= soon and fin(r.get("pred")) and fin(r.get("peer_mean"))
          and (r.get("n_peers") or 0) >= 3 and state_ok("earn_readthrough", tk(r["ticker"]), hours=24 * 20)]
    by = {}
    for r in rs:
        by.setdefault(r.get("sector") or "Other", []).append(r)
    if not by:
        print("earn_readthrough: no sector with peers reported and companies due this week")
        return None
    sec, group = max(by.items(), key=lambda kv: len(kv[1]))
    group.sort(key=lambda r: r["report_date"])
    group = group[:3]
    if len(group) < 2:
        print("earn_readthrough: fewer than two companies due in one sector")
        return None
    pm, n, pred = group[0]["peer_mean"], group[0]["n_peers"], group[0]["pred"]
    names = ", ".join(f"${tk(r['ticker'])} ({E._day(r['report_date'])})" for r in group)
    task = (f"PEER READ-THROUGH, {sec}: {n} companies in the sector already reported this season with an average EPS surprise of {spc(pm)}. "
            f"Historically a company's surprise moved {d.get('beta'):.2f}× its sector's so far, so the read-through is {spc(pred)} for those still to "
            f"report:\n" + "\n".join(f"- ${tk(r['ticker'])} ({r.get('name')}) reports {r['report_date']} ({E._day(r['report_date'])})" for r in group)
            + "\n\nOne or two sentences, then a question. Peers = same sector (no supplier map).")
    f1 = f"{sec.capitalize()} peers have beaten EPS estimates by {spc(pm)} on average this season ({n} reports). Next up: {names}. Read-through: {spc(pred)}. Does it carry over?"
    f2 = f"Read-through for {names}: {n} {sec} peers already reported, average EPS surprise {spc(pm)}. Same story, or different?"
    tks = [tk(r["ticker"]) for r in group]
    return {"task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks), "fallback": f1, "fallbacks": [f1, f2]}


@kind("earn_dist", tag="polymarket", schedule=["morning"], cooldown=48, label="✦ Polymarket vs options (price)",
      title="One stock's price on a date: Polymarket's median against the options market's risk-neutral one",
      guide="One or two sentences: the stock and date, Polymarket's median, the options market's median and 80% range, then a question.", corpus=3)
def plan_earn_dist(site, rows, c, by_ticker, state_ok, today):
    d = _hub(site, "distributions.json")
    soon = (today + dt.timedelta(days=7)).isoformat()
    rs = []
    for r in (d or {}).get("rows") or []:
        pm, op = r.get("polymarket") or {}, r.get("options") or {}
        if r.get("kind") != "price" or not (today.isoformat() <= (r.get("end") or "") <= soon) or not fin(pm.get("median")) or not fin(op.get("median")) \
                or not fin(op.get("q10")) or not fin(op.get("q90")) or not fin(r.get("spot")):
            continue
        if state_ok("earn_dist", tk(r["ticker"]), hours=24 * 7):
            rs.append((abs(pm["median"] - op["median"]) / r["spot"], r))
    if not rs:
        print("earn_dist: no Polymarket price ladder with an options expiry beside it this week")
        return None
    _, r = max(rs, key=lambda x: x[0])
    t, pm, op = tk(r["ticker"]), r["polymarket"], r["options"]
    task = (f"${t} PRICE ON {r['end']} ({E._day(r['end'])}): Polymarket's ladder (“{r.get('title')}”) has a median of {E.px_fmt(pm['median'])}; the options market "
            f"(risk-neutral distribution at the {r['expiry']} expiry) has a median of {E.px_fmt(op['median'])} and an 80% range of {E.px_fmt(op['q10'])}–"
            f"{E.px_fmt(op['q90'])}. Last price {E.px_fmt(r['spot'])}.\n\nOne or two sentences, then a question. Risk-neutral is not a forecast.")
    f1 = (f"${t} on {E._day(r['end'])}: Polymarket's median is {E.px_fmt(pm['median'])}, the options market's {E.px_fmt(op['median'])} "
          f"(80% range {E.px_fmt(op['q10'])}–{E.px_fmt(op['q90'])}). Which crowd is right?")
    f2 = (f"Two markets, one stock: for ${t} by {E._day(r['end'])}, Polymarket centers on {E.px_fmt(pm['median'])}, options on {E.px_fmt(op['median'])}. "
          "Who's mispricing it?")
    return {"task": task, "cashtags": [t], "items": E._items(site, by_ticker, [t], 1), "fallback": f1, "fallbacks": [f1, f2]}
