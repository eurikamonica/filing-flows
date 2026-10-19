"""X post formats from the hub's market maps (disclosures/app/market_maps.py → data/research/market/): where the
disclosed money went, a watched manager's portfolio by sector and its holdings race (GIF), the market map (PNG), the most
crowded stocks among the watched 13F managers, the corporate debt maturity wall, the valuation thermometer and net
liquidity. Registered with pipeline/xkinds.py; every number a post uses is in its task."""
import datetime as dt

from . import engage
from .xkinds import kind

BASE = "research/market/"


def _file(site, name):
    try:
        return engage.hub_cached(site, BASE + name)
    except Exception as err:                             # noqa: BLE001 — not published yet
        print(f"market maps: {name} not available ({str(err)[:90]})")
        return None


def usd(v):
    return engage.money(v)


def susd(v):
    return ("+" if v > 0 else "") + engage.money(v)


def spts(v, d=1):
    """A return difference in percentage points: 0.025 → "+2.5"."""
    x = v * 100
    if round(abs(x), d) == 0:
        return f"{0:.{d}f}"
    return ("+" if x > 0 else "−") + f"{abs(x):.{d}f}"


def pct(v, d=0):
    return f"{v * 100:.{d}f}%"


def spct(v, d=1):
    if round(abs(v), d) == 0:
        return f"{0:.{d}f}%"
    return ("+" if v > 0 else "−") + f"{abs(v):.{d}f}%"


def day(iso):
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
        return f"{d:%b} {d.day}, {d.year}"
    except (TypeError, ValueError):
        return str(iso or "")


def tk(t):
    return (t or "").upper().replace("-", ".")


def first_ok(fbs, cashtags, tags=("#stocks",), allowed=None, lines=False):
    """The phrasings that pass the post checks (a plan keeps only those)."""
    out = []
    for f in fbs:
        try:
            engage.clean(f, cashtags, list(tags), allowed=allowed, lines=lines)
            out.append(f)
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ where the disclosed money went
@kind("money_flow", tag="flows", cooldown=72, schedule=["evening"], label="✦ Money-flow map",
      title="Where the disclosed money went this quarter: sectors and stocks net bought and sold by 13F managers, insiders and officials",
      guide="Open with the period, then the sector with the largest net inflow and the one with the largest outflow, then the most "
            "net-bought and most net-sold stock with their dollars; say the groups are combined; end with a short question.")
def plan_money_flow(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "flows.json")
    pers = [p for p in (d or {}).get("periods") or [] if p.get("top_in") and p.get("top_out") and p.get("sectors")]
    if not pers:
        return None
    p = pers[0]
    a, b = p["top_in"][0], p["top_out"][0]
    ta, tb = tk(a["ticker"]), tk(b["ticker"])
    if not state_ok("money_flow", f"{ta}:{tb}:{p['key']}", hours=24 * 7):
        return None
    named = [x for x in p["sectors"] if x["id"] != "other"]
    if len(named) < 2:
        return None
    s_in, s_out = named[0], named[-1]
    groups = [g for g in p.get("groups") or [] if g.get("buy") or g.get("sell")]
    label = (p.get("label") or "").split(" (")[0].split(" —")[0]
    task = (f"MONEY-FLOW MAP, {p.get('label')} (SEC 13F reports, Form 4 insider trades, House and Senate reports; each name's trades "
            f"netted per stock, groups combined):\n"
            + "\n".join(f"- {g['label']}: bought {usd(g['buy'])}, sold {usd(g['sell'])}, net {susd(g['net'])}" for g in groups)
            + f"\n- largest sector inflow: {s_in['label']} {susd(s_in['net'])} net; largest outflow: {s_out['label']} {susd(s_out['net'])}"
            + "\n- most net-bought: " + "; ".join(f"${tk(x['ticker'])} {susd(x['net'])}" for x in p["top_in"][:3])
            + "\n- most net-sold: " + "; ".join(f"${tk(x['ticker'])} {susd(x['net'])}" for x in p["top_out"][:3])
            + "\n\nOpen with the period, then the sectors, then the two stocks with their dollars, then a short question.")
    allowed = [tk(x["ticker"]) for x in p["top_in"][:3] + p["top_out"][:3]]
    fbs = [f"Where the disclosed money went, {label}: {s_in['label']} {susd(s_in['net'])} net, {s_out['label']} {susd(s_out['net'])}. "
           f"Most net-bought: ${ta} ({susd(a['net'])}); most net-sold: ${tb} ({susd(b['net'])}). 13F managers, insiders and officials combined. "
           "Which flow surprises you?",
           f"{label}, all disclosed flows netted: ${ta} drew {susd(a['net'])}, ${tb} saw {susd(b['net'])}. By sector, {s_in['label']} led "
           f"({susd(s_in['net'])}) and {s_out['label']} lagged ({susd(s_out['net'])}). Follow the money or fade it?",
           f"Money-flow map, {label}: {s_in['label']} {susd(s_in['net'])}, {s_out['label']} {susd(s_out['net'])}. Top net buy ${ta}, "
           f"top net sale ${tb}. What does that tell you?"]
    fbs = first_ok(fbs, [ta, tb], allowed=allowed)
    if not fbs:
        return None
    return {"kind": "money_flow", "task": task, "cashtags": [ta, tb], "allowed": allowed, "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "event_key": f"money_flow:{ta}:{tb}:{p['key']}"}


# ------------------------------------------------------------------ a watched manager's portfolio by sector
def _manager_shift(m):
    secs = [s for s in m.get("sectors") or [] if s.get("w") is not None and s.get("prev_w") is not None]
    return sum(abs(s["w"] - s["prev_w"]) for s in secs) / 2, secs


@kind("manager_sectors", tag="13f", cooldown=72, schedule=["weekly"], label="✦ Manager by sector",
      title="A watched 13F manager's portfolio by sector against the quarter before, with its biggest add (holdings race GIF when there is one)",
      guide="Name the manager and the quarter, give the three largest sectors with this quarter's weight and last quarter's, then the "
            "biggest add with its share change; end with a short question. 13F positions are quarter-end holdings filed weeks later.")
def plan_manager_sectors(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "managers.json")
    cands = []
    mans = (d or {}).get("managers") or []
    latest = max((m["period"] for m in mans), default="")
    for m in mans:
        if not m.get("prev_period") or m["period"] < latest or (m.get("total") or 0) < 1e9 or not state_ok("manager_sectors", m["cik"], hours=24 * 30):
            continue
        shift, secs = _manager_shift(m)
        secs = [x for x in secs if x["id"] != "other" and x["prev_w"]]
        adds = [p for s in secs for p in s["positions"] if p["ticker"] and p["status"] in ("added", "new") and p["usd"] > 0]
        if len(secs) >= 3 and adds:
            cands.append((shift, m, secs, max(adds, key=lambda p: p["usd"] - p["prev_usd"])))
    if not cands:
        return None
    shift, m, secs, add = max(cands, key=lambda x: (x[0], x[1]["total"]))
    top = secs[:3]
    a = tk(add["ticker"])
    chg = f"{add['shares_chg'] * 100:+.0f}% shares" if add.get("shares_chg") is not None else "a new position"
    lines = "\n".join(f"- {s['label']}: {pct(s['w'])} of the portfolio (last quarter {pct(s['prev_w'])})" for s in top)
    task = (f"13F BY SECTOR — {m['name']}, quarter ended {day(m['period'])} (against {day(m['prev_period'])}; filed {m.get('filed')}), "
            f"long stock positions {usd(m['total'])}:\n{lines}\n- biggest add: ${a} ({add['issuer']}): {chg}, now {usd(add['usd'])}\n\n"
            "Name the manager and quarter, the three sectors with both weights, the biggest add, then a short question.")
    who = m["name"].split(" (")[0]
    sec_txt = ", ".join(f"{s['label']} {pct(s['w'])} (from {pct(s['prev_w'])})" for s in top)
    fbs = [f"{who}'s 13F by sector, quarter ended {day(m['period'])}: {sec_txt}. Biggest add: ${a} ({chg}). Rotation or noise?",
           f"How {who} positioned for {day(m['period'])} (13F): {sec_txt}. The largest addition was ${a}, {usd(add['usd'])}. What do you read into it?",
           f"{who}, quarter ended {day(m['period'])}: {top[0]['label']} {pct(top[0]['w'])} of the 13F portfolio (from {pct(top[0]['prev_w'])}). "
           f"Biggest add ${a} ({chg}). Conviction or crowding?"]
    fbs = first_ok(fbs, [a])
    if not fbs:
        return None
    gif = BASE + f"img/race-{m['cik']}.gif"
    e = by_ticker.get(a)
    return {"kind": "manager_sectors", "task": task, "cashtags": [a], "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "event_key": f"manager_sectors:{m['cik']}", "hub_images": [gif],
            "tags": engage.H.pick("13f", e, key=f"manager_sectors:{m['cik']}")}


# ------------------------------------------------------------------ the holdings race
@kind("holdings_race", tag="13f", cooldown=24 * 6, schedule=["weekly"], label="✦ Holdings race (GIF)",
      title="The largest holdings of a famous 13F portfolio, quarter by quarter, as an animated bar chart",
      guide="Name the portfolio, the first and last quarter, and how the top three weights changed between them; say the GIF shows "
            "every quarter; end with a short question.")
def plan_holdings_race(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "managers.json")
    st = _file(site, "status.json") or {}
    have = set(st.get("images") or [])
    for m in (d or {}).get("managers") or []:
        gif = f"race-{m['cik']}.gif"
        race = m.get("race") or []
        if gif not in have or len(race) < 3 or not state_ok("holdings_race", m["cik"], hours=24 * 28):
            continue
        q0, q1 = race[0], race[-1]
        w0 = {t: w for t, _, w in q0["top"]}
        top = [(t, w) for t, _, w in q1["top"][:3] if w]
        if len(top) < 3:
            continue
        who = m["name"].split(" (")[0]
        parts = [f"${tk(t)} {pct(w0[t])} → {pct(w)}" if w0.get(t) else f"${tk(t)} new → {pct(w)}" for t, w in top]
        task = (f"HOLDINGS RACE — {m['name']}: largest 13F positions in each of {len(race)} quarters, from {day(q0['period'])} to "
                f"{day(q1['period'])}; portfolio {usd(q0['total'])} → {usd(q1['total'])}. Top three now, weight then → now: "
                + "; ".join(parts) + ".\n\nThe GIF attached shows every quarter. One post: the portfolio, the span, the three weights, a question.")
        cash = [tk(t) for t, _ in top]
        fbs = [f"{who}'s largest holdings, {day(q0['period'])} → {day(q1['period'])}: " + ", ".join(parts) + f". {len(race)} quarters of 13Fs in one race. "
               "Which move stands out?",
               f"{len(race)} quarters of {who} in one chart: " + ", ".join(parts) + f" (portfolio {usd(q0['total'])} → {usd(q1['total'])}). What changed most?"]
        fbs = first_ok(fbs, cash[:1], allowed=cash)
        if not fbs:
            continue
        return {"kind": "holdings_race", "task": task, "cashtags": cash[:1], "allowed": cash, "items": [], "fallback": fbs[0], "fallbacks": fbs,
                "hub_images": [BASE + "img/" + gif], "event_key": f"holdings_race:{m['cik']}"}
    return None


# ------------------------------------------------------------------ the market map
@kind("market_map", tag="movers", cooldown=20, schedule=["morning"], label="✦ Market map (image)",
      title="Yesterday's market map: sectors and the largest stocks by the day's move, with the heatmap image",
      guide="Give the session's date, the best and worst sector by cap-weighted move, then the three largest companies with their moves; "
            "say the image is the map; end with a short question.")
def plan_market_map(site, rows, c, by_ticker, state_ok, today):
    hm = _file(site, "heatmap.json")
    if not hm or not hm.get("cells") or not hm.get("sectors"):
        return None
    asof = hm.get("asof") or ""
    if asof and asof < (today - dt.timedelta(days=4)).isoformat():
        return None
    if not state_ok("market_map", asof or str(today), hours=20):
        return None
    F = hm["fields"]
    cells = [dict(zip(F, r)) for r in hm["cells"] if r[F.index("chg")] is not None]
    secs = sorted([s for s in hm["sectors"] if s.get("chg") is not None and s["id"] != "other"], key=lambda s: -s["chg"])
    if len(cells) < 5 or len(secs) < 2:
        return None
    big = sorted(cells, key=lambda x: -x["mcap"])[:3]
    movers = sorted(cells[:120], key=lambda x: -abs(x["chg"]))[:2]
    best, worst = secs[0], secs[-1]
    cash = [tk(x["ticker"]) for x in big]
    allowed = cash + [tk(x["ticker"]) for x in movers if tk(x["ticker"]) not in cash]
    task = (f"MARKET MAP, session of {day(asof)} (Nasdaq screener, delayed; the image is a treemap of the {len(cells)} largest US stocks, "
            f"size = market value, colour = the day's move):\n- best sector: {best['label']} {spct(best['chg'])} (cap-weighted); worst: "
            f"{worst['label']} {spct(worst['chg'])}\n- the largest companies: " + "; ".join(f"${tk(x['ticker'])} {spct(x['chg'])}" for x in big)
            + "\n- biggest movers among the 120 largest: " + "; ".join(f"${tk(x['ticker'])} {spct(x['chg'])}" for x in movers)
            + "\n\nOne post: the date, both sectors, the three giants, a short question. The map is attached.")
    giants = ", ".join(f"${tk(x['ticker'])} {spct(x['chg'])}" for x in big)
    fbs = [f"Market map, {day(asof)}: {best['label']} {spct(best['chg'])}, {worst['label']} {spct(worst['chg'])}. The giants: {giants}. "
           "What stood out to you?",
           f"{day(asof)} in one picture: {best['label']} led ({spct(best['chg'])}), {worst['label']} lagged ({spct(worst['chg'])}); {giants}. "
           "Rotation or noise?"]
    fbs = first_ok(fbs, cash, allowed=allowed)
    if not fbs:
        return None
    return {"kind": "market_map", "task": task, "cashtags": cash, "allowed": allowed, "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "hub_images": [BASE + "img/heatmap.png"], "event_key": f"market_map:{asof}"}


# ------------------------------------------------------------------ crowding
@kind("crowded", tag="13f", cooldown=24 * 6, schedule=["weekly"], label="✦ Most crowded stocks",
      title="The stocks the most watched 13F managers share, with the crowding index and how crowded names did after past 13F deadlines",
      guide="Headline line, then one line per stock with how many of the watched managers hold it, then the walk-forward comparison "
            "of crowded and single-holder names if given, then a question. Line breaks.")
def plan_crowded(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "network.json")
    cr = [r for r in (d or {}).get("crowding") or [] if r.get("holders", 0) >= 3 and state_ok("crowded", tk(r["ticker"]), hours=24 * 30)][:5]
    if len(cr) < 4:
        return None
    cr.sort(key=lambda r: (-r["holders"], -r["index"]))
    n = d.get("managers")
    chk = (d.get("check") or {})
    qs = chk.get("quarters") or []
    task = (f"MOST CROWDED STOCKS among {n} well-known 13F managers (the hub's watchlist, latest 13Fs): "
            + "; ".join(f"${tk(r['ticker'])} held by {r['holders']} (crowding index {r['index']:.0f} of 100)" for r in cr) + "."
            + (f"\nWalk-forward check: over {len(qs)} quarters, names held by 3 or more did {spts(chk['mean_spread'])} percentage points better than "
               f"names one manager held, on average, over the 63 trading days after the 13F deadline (better in {pct(chk['hit_rate'])} of quarters)."
               if qs and chk.get("mean_spread") is not None and chk.get("hit_rate") is not None else "")
            + "\n\nFormat with line breaks: a headline, one “$TICKER · N of M hold it” line per stock, then one closing line or question.")
    body = "\n".join(f"${tk(r['ticker'])} · {r['holders']} of {n} hold it" for r in cr)
    tail = (f"Past {len(qs)} quarters: crowded vs single-holder names {spts(chk['mean_spread'])} pts. Safety or risk?"
            if qs and chk.get("mean_spread") is not None else "Safety in numbers, or a crowded exit?")
    cash = [tk(r["ticker"]) for r in cr]
    fbs = [f"The most crowded stocks among {n} famous 13F managers:\n\n{body}\n\n{tail}",
           f"Where the big names overlap (latest 13Fs, {n} managers):\n\n{body}\n\nSafety in numbers, or a crowded exit?"]
    fbs = first_ok(fbs, cash[:2], allowed=cash, lines=True)
    if not fbs:
        return None
    return {"kind": "crowded", "task": task, "cashtags": cash[:2], "allowed": cash, "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "lines": True}


# ------------------------------------------------------------------ debt maturity wall
@kind("maturity_wall", tag="debt", hashtags=["#CorporateDebt", "#credit", "#bonds"], cooldown=24 * 13, schedule=["weekly"],
      label="✦ Debt maturity wall", title="How much corporate debt falls due next year and after, by rating band, and the biggest borrowers due",
      guide="Give next year's and the year after's maturities, how much of next year's is rated BB or lower, and the two largest "
            "borrowers due next year with their amounts; say it covers the companies the site reads; end with a question.")
def plan_maturity_wall(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "maturity.json")
    if not d or not d.get("totals") or len(d["totals"]) < 3:
        return None
    y1 = d["asof_year"] + 1
    t1, t2 = d["totals"][1], d["totals"][2]
    low = sum(d["wall"].get(b, [0, 0])[1] for b in ("BB", "B", "CCC"))
    big = [x for x in d.get("next_year_top") or [] if x.get("ticker")][:2]
    if not t1 or len(big) < 2 or not state_ok("maturity_wall", str(y1), hours=24 * 13):
        return None
    cash = [tk(x["ticker"]) for x in big]
    task = (f"DEBT MATURITY WALL (debt instruments of the {d['companies']:,} companies the site reads, from their latest 10-K / 10-Q):\n"
            f"- due in {y1}: {usd(t1)}; in {y1 + 1}: {usd(t2)}\n- of the {y1} total, rated BB or lower (issuer band): {usd(low)}\n"
            f"- largest {y1} maturities: " + "; ".join(f"${tk(x['ticker'])} {usd(x['usd'])} ({x['band']})" for x in big)
            + "\n\nOne post: the two years, the lower-rated share, the two borrowers, a question. Say it covers the companies the site reads.")
    fbs = [f"Corporate debt maturity wall: {usd(t1)} falls due in {y1} and {usd(t2)} in {y1 + 1} across the {d['companies']:,} companies we track; "
           f"{usd(low)} of {y1}'s is rated BB or lower. Biggest {y1} maturities: ${cash[0]} {usd(big[0]['usd'])}, ${cash[1]} {usd(big[1]['usd'])}. "
           "Refinancing risk or non-event?",
           f"{usd(t1)} of corporate debt comes due in {y1} ({d['companies']:,} companies we track), {usd(low)} of it rated BB or lower. "
           f"Largest: ${cash[0]} and ${cash[1]}. At today's rates, who feels it?"]
    fbs = first_ok(fbs, cash)
    if not fbs:
        return None
    return {"kind": "maturity_wall", "task": task, "cashtags": cash, "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "event_key": f"maturity_wall:{y1}"}


# ------------------------------------------------------------------ valuation thermometer
@kind("valuation_gauge", tag="valuation", hashtags=["#StockMarket", "#valuation", "#investing"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Market valuation gauges", title="Buffett indicator, Shiller CAPE and the forward P/E with their historical percentiles",
      guide="Give each gauge with its percentile and the start of its history; if a fit is given, say what past ten-year real returns "
            "looked like from similar levels and that the range is wide; never predict; end with a question.")
def plan_valuation_gauge(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "thermometer.json")
    g = (d or {}).get("gauges") or {}
    b, cp, fp = g.get("buffett"), g.get("cape"), g.get("fwd_pe")
    parts, facts = [], []
    if b and b.get("value") and b.get("percentile") is not None:
        parts.append(f"Buffett indicator {b['value']:.2f}x GDP ({pct(b['percentile'])} percentile since {b['history_from'][:4]})")
        facts.append(f"- Buffett indicator: {b['value']:.2f}x GDP, {pct(b['percentile'])} percentile of its history since {b['history_from'][:4]} ({b.get('note', '')[:160]})")
    if cp and cp.get("value") and cp.get("percentile") is not None:
        parts.append(f"Shiller CAPE {cp['value']:.1f} ({pct(cp['percentile'])} percentile since {cp['history_from'][:4]})")
        facts.append(f"- Shiller CAPE: {cp['value']:.1f}, {pct(cp['percentile'])} percentile since {cp['history_from'][:4]}")
    if fp and fp.get("value"):
        parts.append(f"S&P 500 forward P/E {fp['value']:.1f}")
        facts.append(f"- S&P 500 forward P/E: {fp['value']:.1f} (analysts' consensus)")
    if len(parts) < 2 or not state_ok("valuation_gauge", str(today.isocalendar()[1]), hours=24 * 6):
        return None
    fit = (cp or {}).get("fit")
    fit_txt = ""
    if fit and fit.get("next10y_real") is not None and fit.get("lo80") is not None:
        facts.append(f"- fit since {cp['history_from'][:4]}: past ten-year real returns from a CAPE like this centred on {spct(fit['next10y_real'] * 100)} a year, "
                     f"80% range {spct(fit['lo80'] * 100)} to {spct(fit['hi80'] * 100)} (overlapping windows; a description, not a forecast)")
        fit_txt = (f" From a CAPE like this, past ten-year real returns ran {spct(fit['next10y_real'] * 100)} a year "
                   f"({spct(fit['lo80'] * 100)} to {spct(fit['hi80'] * 100)}).")
    task = "MARKET VALUATION GAUGES:\n" + "\n".join(facts) + "\n\nOne post: the gauges with their percentiles, the fit if given (as history, not a forecast), a question."
    fbs = [f"$SPY valuation check: {'; '.join(parts[:2])}.{fit_txt} Expensive, or different this time?",
           f"Valuation gauges for $SPY this week: {'; '.join(parts)}. Where do you stand?",
           f"$SPY by the classic yardsticks: {'; '.join(parts[:2])}. Stretched, or justified?"]
    fbs = first_ok(fbs, ["SPY"])
    if not fbs:
        return None
    return {"kind": "valuation_gauge", "task": task, "cashtags": ["SPY"], "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "event_key": f"valuation_gauge:{today.isocalendar()[1]}"}


# ------------------------------------------------------------------ liquidity
@kind("liquidity", tag="liquidity", hashtags=["#liquidity", "#Fed", "#markets"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Net liquidity", title="Fed balance sheet minus the Treasury General Account minus reverse repo: the level and the weekly change",
      guide="Define net liquidity in a few words, give the level, the one-week and four-week change, the high-yield spread and the "
            "curve; end with a question. No predictions.")
def plan_liquidity(site, rows, c, by_ticker, state_ok, today):
    d = _file(site, "liquidity.json")
    L = (d or {}).get("latest") or {}
    if not L.get("net") or L.get("chg_1w") is None or L.get("chg_4w") is None:
        return None
    if not state_ok("liquidity", L["week"], hours=24 * 6):
        return None
    net = usd(L["net"] * 1e9)
    w1, w4 = susd(L["chg_1w"] * 1e9), susd(L["chg_4w"] * 1e9)
    hy = f"{L['hy_spread']:.2f}%" if L.get("hy_spread") is not None else None
    cv = f"{L['curve']:+.2f}" if L.get("curve") is not None else None
    task = (f"NET LIQUIDITY, week of {day(L['week'])} (FRED: Fed total assets WALCL minus the Treasury General Account minus overnight reverse "
            f"repo): {net}; change {w1} on the week, {w4} over 4 weeks"
            + (f", {susd(L['chg_52w'] * 1e9)} over 52 weeks" if L.get("chg_52w") is not None else "")
            + f". Fed {usd(L['fed'] * 1e9)}, TGA {usd(L['tga'] * 1e9)}, reverse repo {usd(L['rrp'] * 1e9)}."
            + (f" High-yield spread {hy}." if hy else "") + (f" 10-year minus 2-year curve {cv} pts." if cv else "")
            + "\n\nOne post: what net liquidity is, the level and both changes, the spread and the curve, a question.")
    extra = ", ".join(x for x in ((f"HY spread {hy}" if hy else ""), (f"10y−2y {cv}" if cv else "")) if x)
    fbs = [f"Net liquidity (Fed balance sheet − TGA − reverse repo): {net}, {w1} on the week and {w4} over 4 weeks." + (f" {extra}." if extra else "")
           + " Tailwind or headwind for $SPY?",
           f"Liquidity check, week of {day(L['week'])}: Fed {usd(L['fed'] * 1e9)} minus TGA {usd(L['tga'] * 1e9)} minus reverse repo "
           f"{usd(L['rrp'] * 1e9)} = {net} ({w4} in 4 weeks). What does it mean for $SPY?"]
    fbs = first_ok(fbs, ["SPY"])
    if not fbs:
        return None
    return {"kind": "liquidity", "task": task, "cashtags": ["SPY"], "items": [], "fallback": fbs[0], "fallbacks": fbs,
            "event_key": f"liquidity:{L['week']}"}
