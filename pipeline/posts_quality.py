"""X posts from the Quality research (disclosures/app/quality.py, published at disclosures/data/research/quality/):
Piotroski 9/9 lists, Altman's distress zone, Beneish screen flags, shareholder-yield leaders, FCF before / after stock
compensation, operating leverage, the cheapest names against their sector's growth-adjusted line, and the monthly
composite ranking with its frozen track record. Every number in a post is in its task (the facts the model sees)."""
from . import engage, hashtags as H, social, xkinds as X
from .xkinds import kind

BASE = "research/quality/"
LIST_MIN = 3


def _data(site):
    try:
        d = engage.hub_cached(site, BASE + "index.json")
    except Exception as err:                              # noqa: BLE001
        print(f"quality posts: research/quality not available ({str(err)[:100]})")
        return None, {}
    F = d.get("fields") or []
    rows = {}
    for r in d.get("rows") or []:
        x = dict(zip(F, r))
        x["ticker"] = engage._tk(x.get("ticker"))
        rows[x["ticker"]] = x
    return d, rows


def _pct(v, d=1):
    return ("−" if v < 0 else "") + f"{abs(v) * 100:.{d}f}%"


def _signed_pct(v, d=1):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v) * 100:.{d}f}%"


def _num(v, d=2):
    return ("−" if v < 0 else "") + f"{abs(v):.{d}f}"


def _name(r):
    return engage.short_name(r.get("name") or r["ticker"], r["ticker"])


def _tags(tag, key):
    X.load()
    return H.pick(tag, None, key=key)


def _chart_items(site, by_ticker, tks, n=4):
    try:
        return engage._items(site, by_ticker, tks, n)
    except Exception:                                     # noqa: BLE001 — charts are optional
        return []


def _list(kind_name, site, by_ticker, state_ok, picks, head, line, closings, tag, facts, n=6, hours=24 * 30):
    """A list post: the head, one line per company, a closing question — as many lines as fit with the hashtags."""
    picks = [r for r in picks if state_ok(kind_name, r["ticker"], hours=hours)][:n]
    if len(picks) < LIST_MIN:
        print(f"{kind_name}: fewer than {LIST_MIN} companies")
        return None
    tags = _tags(tag, f"{kind_name}:" + ",".join(r["ticker"] for r in picks))
    room = 250 - social.xlen(" " + " ".join(tags))
    k = len(picks)
    while k > LIST_MIN and social.xlen(f"{head}\n\n" + "\n".join(line(r) for r in picks[:k]) + f"\n\n{max(closings, key=len)}") > room:
        k -= 1
    picks = picks[:k]
    body = "\n".join(line(r) for r in picks)
    tks = [r["ticker"] for r in picks]
    task = (f"{head.upper()}:\n" + "\n".join(f"- {facts(r)}" for r in picks)
            + "\n\nFormat with line breaks: the headline line, one line per company (name and cashtag, then its number), then "
              "one short closing question. No advice, no prediction.")
    fbs = [f"{head}\n\n{body}\n\n{q}" for q in closings]
    return {"kind": kind_name, "task": task, "cashtags": tks[:2], "allowed": tks, "items": _chart_items(site, by_ticker, tks),
            "fallback": fbs[0], "fallbacks": fbs, "lines": True, "tags": tags}


@kind("quality_piotroski", tag="quality", hashtags=["#QualityStocks", "#Piotroski", "#investing"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Piotroski 9/9", title="Companies passing all nine Piotroski checks in their latest fiscal year (Quality research)",
      guide="A list of companies with a perfect Piotroski F-score (9 of 9): say in the headline that all nine checks of "
            "profitability, leverage and efficiency passed; one line per company with its cashtag; a short question.", corpus=6)
def plan_piotroski(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    picks = sorted((r for r in R.values() if r.get("f_score") == 9 and (r.get("mcap") or 0) >= 2e9), key=lambda r: -r["mcap"])
    return _list("quality_piotroski", site, by_ticker, state_ok, picks,
                 "Piotroski F-score 9/9 — all nine checks passed in the latest fiscal year",
                 lambda r: f"{_name(r)} ${r['ticker']}",
                 ["Which one would you dig into?", "Any of these on your list?"], "quality",
                 lambda r: f"{_name(r)} ${r['ticker']}: F-score 9/9 (fiscal year ended {r.get('fy_end')}), market cap {engage.money(r['mcap'])}")


@kind("quality_altman", tag="distress", hashtags=["#AltmanZ", "#credit", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Altman distress zone", title="Large companies in the Altman Z-score distress zone (latest fiscal year)",
      guide="Large companies whose Altman Z-score is in the distress zone (Z below 1.81 for manufacturers, Z'' below 1.1 for "
            "others): one line per company with its score; say it is a statistical model, ask what the market sees.", corpus=5)
def plan_altman(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    picks = sorted((r for r in R.values() if r.get("z_zone") == "distress" and r.get("z") is not None and (r.get("mcap") or 0) >= 5e9),
                   key=lambda r: -r["mcap"])
    return _list("quality_altman", site, by_ticker, state_ok, picks,
                 "Large companies in the Altman Z-score distress zone",
                 lambda r: f"{_name(r)} ${r['ticker']}: {r['z_model']} {_num(r['z'])}",
                 ["Temporary, or a real warning?", "Does the market already price it in?"], "distress",
                 lambda r: (f"{_name(r)} ${r['ticker']}: Altman {r['z_model']} {_num(r['z'])} (distress zone: Z below 1.81, Z'' below 1.1), "
                            f"market cap {engage.money(r['mcap'])}"))


@kind("quality_beneish", tag="forensic", hashtags=["#ForensicAccounting", "#Beneish", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Beneish screen", title="A large company whose Beneish M-score flags possible earnings manipulation (a statistical screen)",
      guide="One company whose Beneish M-score is above −1.78: always say it 'screens as a possible earnings manipulator on the "
            "Beneish M-score — a statistical flag, not an accusation'; give M and the index that drives it; ask what explains it.", corpus=4)
def plan_beneish(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    cands = sorted((r for r in R.values() if r.get("m_flag") and r.get("m_score") is not None and (r.get("mcap") or 0) >= 2e9),
                   key=lambda r: -r["mcap"])
    LABEL = {"dsri": "receivables vs sales index", "gmi": "gross margin index", "aqi": "asset quality index", "sgi": "sales growth index",
             "depi": "depreciation index", "sgai": "SG&A index", "lvgi": "leverage index", "tata": "accruals to assets"}
    for r in cands:
        if not state_ok("quality_beneish", r["ticker"], hours=24 * 60):
            continue
        try:
            comp = engage.hub_cached(site, f"{BASE}c/{r['ticker']}.json")
            idx = (((comp.get("metrics") or {}).get("beneish") or {}).get("idx")) or {}
        except Exception:                                 # noqa: BLE001
            idx = {}
        # the index pulling M up the most against a neutral 1 (TATA against 0)
        W = {"dsri": 0.92, "gmi": 0.528, "aqi": 0.404, "sgi": 0.892, "depi": 0.115, "sgai": -0.172, "lvgi": -0.327, "tata": 4.679}
        drv = max((k for k in idx if idx[k] is not None), key=lambda k: W[k] * (idx[k] - (0 if k == "tata" else 1)), default=None)
        dtxt = f"{LABEL[drv]} {_num(idx[drv])}" if drv else ""
        tk = r["ticker"]
        task = (f"BENEISH M-SCORE SCREEN (eight-index model, fiscal year ended {r.get('fy_end')}): ${tk} ({_name(r)}) M = {_num(r['m_score'])}, "
                f"above the −1.78 line where the model flags a possible earnings manipulator. "
                + (f"Biggest driver: {dtxt}. " if dtxt else "")
                + "Indices: " + ", ".join(f"{LABEL[k]} {_num(v)}" for k, v in idx.items() if v is not None)
                + ".\n\nSay it screens as a possible earnings manipulator on the Beneish M-score — a statistical flag, not an "
                  "accusation. Give M and the driver; ask what explains it.")
        f1 = (f"${tk} screens as a possible earnings manipulator on the Beneish M-score (M = {_num(r['m_score'])}, above the −1.78 line) — "
              f"a statistical flag, not an accusation." + (f" Driver: {dtxt}." if dtxt else "") + " What explains it?")
        f2 = (f"Beneish M-score check: ${tk} at {_num(r['m_score'])} vs the −1.78 line" + (f", led by its {dtxt}" if dtxt else "")
              + ". A statistical flag, not an accusation. Growth story or a closer look?")
        fbs = [f for f in (f1, f2) if social.xlen(f) <= 215] or [f"${tk} screens as a possible earnings manipulator on the Beneish M-score "
                                                                 f"(M = {_num(r['m_score'])}) — a statistical flag, not an accusation. What explains it?"]
        return {"kind": "quality_beneish", "task": task, "cashtags": [tk], "items": _chart_items(site, by_ticker, [tk], 1),
                "fallback": fbs[0], "fallbacks": fbs, "must": (r"not an accusation", "say it is a statistical flag, not an accusation"),
                "tags": _tags("forensic", f"beneish:{tk}")}
    print("quality_beneish: no large company flagged")
    return None


@kind("quality_yield", tag="yield", hashtags=["#ShareholderYield", "#Buybacks", "#dividends"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Shareholder yield", title="Highest shareholder yield (dividends + net buybacks) among $5B+ companies",
      guide="A list of the highest shareholder yields (dividends plus buybacks minus new stock sold, over market cap): one line "
            "per company with the total and its two parts; a question about durability.", corpus=5)
def plan_yield(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    picks = sorted((r for r in R.values() if (r.get("mcap") or 0) >= 5e9 and r.get("sy") is not None and 0.03 <= r["sy"] <= 0.3),
                   key=lambda r: -r["sy"])
    return _list("quality_yield", site, by_ticker, state_ok, picks,
                 "Highest shareholder yield (dividends + net buybacks) among $5B+ companies",
                 lambda r: f"${r['ticker']} {_pct(r['sy'])} ({_pct(r['div_y'])} div + {_pct(r['bb_y'])} buybacks)",
                 ["Which payout is the most durable?", "Cash returned or cash borrowed?"], "yield",
                 lambda r: (f"{_name(r)} ${r['ticker']}: shareholder yield {_pct(r['sy'])} = dividends {_pct(r['div_y'])} + net buybacks "
                            f"{_pct(r['bb_y'])} of a {engage.money(r['mcap'])} market cap (fiscal year ended {r.get('fy_end')})"))


@kind("quality_sbc", tag="sbc", hashtags=["#StockComp", "#FreeCashFlow", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ FCF after stock comp", title="How much of the free-cash-flow yield stock-based compensation takes away ($10B+ companies)",
      guide="A list: each company's free-cash-flow yield before and after subtracting stock-based compensation, written "
            "'X% → Y%'; ask whether stock comp should count as a cost.", corpus=5)
def plan_sbc(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    picks = [r for r in R.values() if (r.get("mcap") or 0) >= 10e9 and r.get("fcf_y") and r.get("fcf_sbc_y") is not None and r["fcf_y"] > 0.01]
    picks.sort(key=lambda r: -(r["fcf_y"] - r["fcf_sbc_y"]) / r["fcf_y"])
    picks = [r for r in picks if (r["fcf_y"] - r["fcf_sbc_y"]) / r["fcf_y"] >= 0.3]
    return _list("quality_sbc", site, by_ticker, state_ok, picks,
                 "Free-cash-flow yield → after stock-based compensation",
                 lambda r: f"${r['ticker']} {_pct(r['fcf_y'])} → {_pct(r['fcf_sbc_y'])}",
                 ["Should stock comp count as a cost?", "Which of these gaps surprises you?"], "sbc",
                 lambda r: (f"{_name(r)} ${r['ticker']}: FCF yield {_pct(r['fcf_y'])}, after stock-based compensation {_pct(r['fcf_sbc_y'])} "
                            f"(market cap {engage.money(r['mcap'])}, fiscal year ended {r.get('fy_end')})"))


@kind("quality_leverage", tag="leverage", hashtags=["#OperatingLeverage", "#earnings", "#stocks"], cooldown=24 * 4, schedule=["evening"],
      label="✦ Operating leverage", title="A large company whose operating profit moves several times faster than its revenue",
      guide="One company's operating leverage: how many % operating profit has moved for each 1% of revenue, its fixed costs a "
            "quarter and the variable share of each revenue dollar (a regression over its recent quarters); say leverage cuts both ways.", corpus=5)
def plan_leverage(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    cands = sorted((r for r in R.values() if (r.get("mcap") or 0) >= 5e9 and r.get("dol") and 2.5 <= r["dol"] <= 15 and r.get("fixed_q")),
                   key=lambda r: -r["mcap"])
    for r in cands:
        tk = r["ticker"]
        if not state_ok("quality_leverage", tk, hours=24 * 45):
            continue
        dol, fixed, var = _num(r["dol"], 1), engage.money(r["fixed_q"]), f"{r['var_ratio'] * 100:.0f}%"
        task = (f"OPERATING LEVERAGE (regression of operating costs on revenue over the recent quarters): ${tk} ({_name(r)}): for each 1% "
                f"change in revenue, operating profit moves about {dol}% ({dol}x the revenue change); fixed costs about {fixed} a quarter; variable costs {var} of each "
                f"revenue dollar. Market cap {engage.money(r['mcap'])}.\n\nState the leverage, the fixed costs, that it cuts both ways; one question.")
        f1 = (f"${tk}: every 1% move in revenue has moved operating profit about {dol}%. Fixed costs ≈ {fixed} a quarter, {var} of each revenue "
              f"dollar variable. Leverage cuts both ways — which way next?")
        f2 = (f"Operating leverage at ${tk}: ~{fixed} of fixed costs a quarter means profit swings about {dol}x revenue. Great on the way up. "
              f"And on the way down?")
        fbs = [f for f in (f1, f2) if social.xlen(f) <= 215] or [f1[:200].rsplit(".", 1)[0] + "."]
        return {"kind": "quality_leverage", "task": task, "cashtags": [tk], "items": _chart_items(site, by_ticker, [tk], 1),
                "fallback": fbs[0], "fallbacks": fbs, "tags": _tags("leverage", f"lev:{tk}")}
    print("quality_leverage: no reliable high-leverage company")
    return None


@kind("quality_cheap", tag="relvalue", hashtags=["#valuation", "#stocks", "#investing"], cooldown=24 * 4, schedule=["evening"],
      label="✦ Cheap vs growth-adjusted line", title="The company furthest below its sector's EV/Sales line for its growth + margin",
      guide="One company whose EV/Sales sits furthest below the line its sector draws for companies with the same revenue growth "
            "plus operating margin: give its multiple, the line's multiple and the growth + margin figure; ask whether the discount "
            "has a reason. Never call it undervalued.", corpus=5)
def plan_cheap(site, rows, c, by_ticker, state_ok, today):
    d, R = _data(site)
    if not d:
        return None
    names = d.get("sector_names") or {}
    cands = sorted((r for r in R.values() if (r.get("mcap") or 0) >= 5e9 and r.get("resid") is not None and r.get("line_ev_s")
                    and r.get("r40") is not None and r["r40"] >= 15 and r.get("ev_s")), key=lambda r: r["resid"])
    for r in cands:
        tk = r["ticker"]
        if not state_ok("quality_cheap", tk, hours=24 * 30):
            continue
        sec = names.get(r["sector"], r["sector"])
        ev, line, r40 = f"{r['ev_s']:.1f}x", f"{r['line_ev_s']:.1f}x", f"{r['r40']:.0f}"
        task = (f"GROWTH-ADJUSTED VALUATION, {sec} (log EV/Sales against revenue growth % + operating margin %, all {sec} companies over "
                f"$300M): ${tk} ({_name(r)}) trades at {ev} sales with growth + margin of {r40} (growth {_pct(r['growth'])}, operating margin "
                f"{_pct(r['margin'])}); the sector line puts companies with that score at about {line}.\n\nGive the two multiples and the "
                "score; ask whether the discount has a reason. Never call it undervalued.")
        f1 = (f"${tk} trades at {ev} sales. {sec} companies with its growth + margin ({r40}) trade near {line} on the sector line. "
              f"Discount for a reason?")
        f2 = f"Growth + margin of {r40}, yet ${tk} sits at {ev} sales vs {line} for its {sec} peers on the same line. What is the market missing — or seeing?"
        fbs = [f for f in (f1, f2) if social.xlen(f) <= 215] or [f1]
        return {"kind": "quality_cheap", "task": task, "cashtags": [tk], "items": _chart_items(site, by_ticker, [tk], 1),
                "fallback": fbs[0], "fallbacks": fbs, "tags": _tags("relvalue", f"cheap:{tk}")}
    print("quality_cheap: nobody far enough below the line")
    return None


@kind("quality_factors", tag="factors", hashtags=["#FactorInvesting", "#quant", "#stocks"], cooldown=24 * 25, schedule=["weekly"],
      label="✦ Monthly factor ranking", title="This month's composite quality / value ranking, frozen, with last month's result",
      guide="The month's composite ranking (equal-weight percentiles of eight quality and value factors), frozen when published: "
            "the top names as cashtags and, when scored, last month's top tenth minus bottom tenth return and rank IC. "
            "Say it is a ranking with a public track record, not a recommendation.", corpus=2)
def plan_factors(site, rows, c, by_ticker, state_ok, today):
    try:
        led = engage.hub_cached(site, BASE + "ledger.json")
    except Exception as err:                              # noqa: BLE001
        print(f"quality_factors: ledger not available ({str(err)[:100]})")
        return None
    months = led.get("months") or {}
    if not months:
        return None
    mo = max(months)
    cur = months[mo]
    if not state_ok("quality_factors", mo, hours=24 * 25):
        return None
    tks = [engage._tk(t) for t, _ in (cur.get("top") or [])[:5]]
    if len(tks) < 3:
        return None
    done = [months[m] for m in sorted(months) if m < mo and months[m].get("result")]
    last = done[-1] if done else None
    res = last["result"] if last else None
    label = f"{mo}"
    task = (f"COMPOSITE RANKING FOR {label} (equal-weight percentiles of 8 factors: Piotroski F, gross profit / assets, accruals, asset "
            f"growth, net issuance, shareholder yield, FCF yield after stock comp, cheapness vs the sector's growth-adjusted line; "
            f"{cur.get('n')} US companies over $300M), frozen on {str(cur.get('frozen_at'))[:10]}. Top five: " + ", ".join(f"${t}" for t in tks) + "."
            + (f" Last scored month ({last['month']}): top tenth {_signed_pct(res['top'])}, bottom tenth {_signed_pct(res['bottom'])}, "
               f"spread {_signed_pct(res['spread'])}, rank IC {_num(res['ic'], 2)} ({led.get('scored')} months scored)." if res else
               " First month on the ledger: no result yet.")
            + "\n\nSay it is a frozen ranking with a public track record, not a recommendation.")
    lines = " ".join(f"${t}" for t in tks)
    if res:
        f1 = (f"Our {label} quality + value ranking is frozen. Top five: {lines}. Last month: top tenth {_signed_pct(res['top'])} vs bottom "
              f"{_signed_pct(res['bottom'])} (IC {_num(res['ic'], 2)}). A ranking with a track record, not a tip. Thoughts?")
    else:
        f1 = (f"Our {label} quality + value ranking is frozen. Top five: {lines}. Every month is scored in public from here. "
              f"A ranking with a track record, not a tip. Thoughts?")
    f2 = f"Composite factor ranking, {label} (8 quality and value factors): {lines} lead. Frozen today, scored next month. Which one surprises you?"
    fbs = [f for f in (f1, f2) if social.xlen(f) <= 215] or [f2]
    return {"kind": "quality_factors", "task": task, "cashtags": tks[:2], "allowed": tks, "items": _chart_items(site, by_ticker, tks),
            "fallback": fbs[0], "fallbacks": fbs, "event_key": f"quality_factors:{mo}", "tags": _tags("factors", f"factors:{mo}")}
