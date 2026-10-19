"""X post formats from the fair value & credit module (disclosures/app/valuation.py → data/research/valuation/):

  pvgo_growth        "70% of $X's price is a bet on growth" — the no-growth value against the price
  fair_value_range   one company's football field in lines: DCF, peers, analysts, Polymarket, our model vs the price
  mc_odds            Monte Carlo DCF: the large companies with the most / fewest scenarios worth more than the price
  distress_watch     the highest blended one-year distress probabilities among $2B+ companies (a ranking, stated so)
  wacc_gap           a large company whose cost of debt and of capital run far above the median company's
  pe_band            large companies at the bottom (or top) of their own P/E range since mid-2022

Every number a post uses is in its task; descriptions, never recommendations.
"""
import datetime as dt

from . import engage as E
from .xkinds import kind

ROOT = "research/valuation/"


def _index(site, max_age_days=5):
    """Rows of the published index as dicts, or [] when missing or stale."""
    try:
        d = E.hub_cached(site, ROOT + "index.json")
    except Exception as err:                                   # noqa: BLE001
        print(f"valuation posts: index not available ({str(err)[:90]})")
        return []
    gen = (d.get("generated_at") or "")[:10]
    if gen and gen < (dt.date.today() - dt.timedelta(days=max_age_days)).isoformat():
        print(f"valuation posts: index is from {gen}; skipped")
        return []
    F = d.get("fields") or []
    return [dict(zip(F, r)) for r in d.get("rows") or []]


def _doc(site, cik):
    try:
        return E.hub_cached(site, f"{ROOT}c/{int(cik)}.json")
    except Exception:                                          # noqa: BLE001
        return None


def money(v):
    """$1,234 / $56.70 / $8.25 — whole dollars from $100 up."""
    if v is None:
        return "—"
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


def pc(v, d=0):
    return f"{v * 100:.{d}f}%"


def _tk(r):
    return E._tk(r.get("ticker"))


def _known(site, by_ticker, rows):
    """Order: trending names, then the site's companies, then the rest — each by market value."""
    hot = {t: i for i, t in enumerate(E.trending(site))}
    return sorted(rows, key=lambda r: (_tk(r) not in hot, hot.get(_tk(r), 0), _tk(r) not in by_ticker, -(r.get("mcap") or 0)))


def _fit(texts, room=250):
    return [t for t in texts if E.social.xlen(t) <= room]


def _tags(tag, site, by_ticker, tk, key):
    return E.H.pick(tag, (E._chart(site, by_ticker, tk) or [None])[0] if tk else None, key=key)


@kind("pvgo_growth", tag="valuation", hashtags=["#valuation", "#DCF", "#stocks", "#investing"], cooldown=20, schedule=["morning"],
      label="✦ Price paid for growth", title="How much of a well-known stock's price is a bet on growth (PVGO), from its own figures",
      guide="Say what share of the market value is paid for growth and what the company would be worth if it never grew (its no-growth "
            "value: operating profit after tax ÷ cost of capital, minus net debt). Give the price. One question about whether the growth "
            "is priced right. Never say the stock is cheap or expensive.", corpus=10)
def plan_pvgo_growth(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if isinstance(r.get("pvgo_share"), (int, float)) and (r.get("mcap") or 0) >= 50e9 and r.get("price")]
    for r in _known(site, by_ticker, [r for r in R if r["pvgo_share"] >= 0.6 or r["pvgo_share"] <= 0]):
        tk = _tk(r)
        if not state_ok("pvgo_growth", tk, hours=24 * 14):
            continue
        d = _doc(site, r["cik"]) or {}
        pv, W = d.get("pvgo") or {}, d.get("wacc") or {}
        if not isinstance(pv.get("per_share"), (int, float)) or not isinstance(pv.get("rate"), (int, float)):
            continue
        name = E.short_name(r.get("name") or tk, tk)
        share, v0, px, rate = r["pvgo_share"], pv["per_share"], r["price"], pv["rate"]
        basis = "net income" if pv.get("basis", "").startswith("net income") else "after-tax operating profit"
        rev = d.get("reverse") or {}
        ig, hg = rev.get("implied_growth"), rev.get("history_growth")
        task = (f"PRICE vs NO-GROWTH VALUE, ${tk} ({name}), from its filings and the share price:\n"
                f"- price {money(px)}\n- no-growth value {money(v0)} a share = {basis} of {E.money(pv.get('earnings'))} ÷ a {pc(rate, 1)} cost of capital"
                f"{', minus net debt' if basis != 'net income' else ''}\n- share of the market value paid for growth (PVGO): {pc(share)}"
                + (f"\n- reverse DCF: the price needs {pc(ig)} revenue growth a year for five years; the last four quarters grew {pc(hg)}"
                   if isinstance(ig, (int, float)) and isinstance(hg, (int, float)) else "")
                + "\n\nOpen with the share paid for growth, give the no-growth value and the price, end with one question. Describe, never recommend.")
        if share > 0:
            fbs = [f"{pc(share)} of ${tk}'s price is a bet on growth.\n\nWith no growth at all, {name}'s {basis} of {E.money(pv.get('earnings'))} "
                   f"at a {pc(rate, 1)} cost of capital is worth about {money(v0)} a share. It trades at {money(px)}.\n\nPriced right?",
                   f"${tk} at {money(px)}: about {money(v0)} of that is today's earnings power with zero growth. The other {pc(share)} is the market's "
                   f"bet on growth. How much of it do you believe?"]
            if isinstance(ig, (int, float)) and isinstance(hg, (int, float)):
                fbs.append(f"To justify {money(px)}, ${tk} needs about {pc(ig)} revenue growth a year for five years (DCF, {pc(rate, 1)} cost of capital). "
                           f"It grew {pc(hg)} over the last year. Doable?")
        else:
            fbs = [f"${tk} trades at {money(px)}, below its no-growth value of about {money(v0)} a share ({basis} of {E.money(pv.get('earnings'))} "
                   f"at a {pc(rate, 1)} cost of capital). The market is pricing in a decline. Fair?"]
        fbs = _fit(fbs)
        if not fbs:
            continue
        return {"kind": "pvgo_growth", "task": task, "cashtags": [tk], "items": E._items(site, by_ticker, [tk], 1), "fallback": fbs[0],
                "fallbacks": fbs, "lines": "\n" in fbs[0], "tags": _tags("valuation", site, by_ticker, tk, f"pvgo:{tk}:{today}")}
    print("pvgo_growth: no large company with a growth share of 60%+ (or below its no-growth value) not posted lately")
    return None


FF_LABEL = {"DCF — Monte Carlo 10th–90th percentile": "DCF (80% of scenarios)", "P/E vs peers": "P/E vs peers", "EV/EBITDA vs peers": "EV/EBITDA vs peers",
            "EV/Sales vs peers": "EV/Sales vs peers", "Residual income": "Residual income", "Analysts' price targets": "Analysts' targets",
            "Polymarket implied price": "Polymarket", "Our model (Rotation forecast)": "Our model, next quarter",
            "P/TBV vs ROTCE (bank peers)": "P/TBV vs bank peers", "P/B vs ROE (insurer peers)": "P/B vs insurer peers", "P/FFO vs REIT peers": "P/FFO vs REIT peers"}


@kind("fair_value_range", tag="valuation", hashtags=["#valuation", "#stocks", "#investing", "#DCF"], cooldown=20, schedule=["evening"],
      label="✦ Fair value ranges", title="One well-known stock: what a DCF, peer multiples, analysts, Polymarket and our model each say, against the price",
      guide="One line per method with its range (\"DCF (80% of scenarios): $a–$b\"), the price on the first line, a short closing question. "
            "Do not pick a winner or call the stock cheap or expensive.", corpus=10)
def plan_fair_value_range(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if (r.get("mcap") or 0) >= 20e9 and r.get("price")]
    for r in _known(site, by_ticker, R):
        tk = _tk(r)
        if not state_ok("fair_value_range", tk, hours=24 * 21):
            continue
        d = _doc(site, r["cik"]) or {}
        ff = [b for b in d.get("football") or [] if b.get("method") in FF_LABEL and isinstance(b.get("low"), (int, float)) and isinstance(b.get("high"), (int, float))]
        if len(ff) < 4:
            continue
        px = r["price"]

        def line(b):
            lo, hi = money(b["low"]), money(b["high"])
            return f"{FF_LABEL[b['method']]}: {lo}" if lo == hi else f"{FF_LABEL[b['method']]}: {lo}–{hi}"
        lines = [line(b) for b in ff]
        task = (f"${tk} ({E.short_name(r.get('name') or tk, tk)}) at {money(px)} — what each method says (ranges per share; from app/valuation.py):\n"
                + "\n".join(f"- {line(b)}" + (f" (central {money(b['point'])})" if isinstance(b.get("point"), (int, float)) else "") for b in ff)
                + "\n\nFormat with line breaks: the price line, one line per method, then a short question. Never say which is right.")
        fbs = []
        for head, close in ((f"${tk} at {money(px)}. What each method says it's worth:", "Where do you land?"),
                            (f"Valuing ${tk} ({money(px)}) five ways:", "Which one do you trust?")):
            for k in range(len(lines), 2, -1):
                t = f"{head}\n\n" + "\n".join(lines[:k]) + f"\n\n{close}"
                if E.social.xlen(t) <= 225:
                    fbs.append(t)
                    break
        if not fbs:
            continue
        return {"kind": "fair_value_range", "task": task, "cashtags": [tk], "items": E._items(site, by_ticker, [tk], 1), "fallback": fbs[0],
                "fallbacks": fbs, "lines": True, "tags": _tags("valuation", site, by_ticker, tk, f"ff:{tk}:{today}")}
    print("fair_value_range: no large company with four or more methods not posted lately")
    return None


@kind("mc_odds", tag="valuation", hashtags=["#valuation", "#DCF", "#MonteCarlo", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Monte Carlo odds", title="Large companies with the most scenarios worth more than today's price (Monte Carlo DCF)",
      guide="Say it is a Monte Carlo DCF (2,000 scenarios each, the company's own growth and margin history). One line per stock: cashtag and "
            "the share of scenarios worth more than the price. Models, not promises — one question.", corpus=4)
def plan_mc_odds(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if isinstance(r.get("mc_p_above"), (int, float)) and (r.get("mcap") or 0) >= 20e9]
    R = [r for r in R if state_ok("mc_odds", _tk(r), hours=24 * 14)]
    if len(R) < 8:
        print("mc_odds: fewer than eight large companies with a Monte Carlo DCF")
        return None
    top = sorted(R, key=lambda r: -r["mc_p_above"])[:5]
    low = sorted(R, key=lambda r: r["mc_p_above"])[:5]
    task = ("MONTE CARLO DCF, 2,000 scenarios per company (growth, margin and cost of capital drawn around each company's own history), "
            "share of scenarios worth more than today's price, companies worth $20B+:\nMost:\n"
            + "\n".join(f"- ${_tk(r)} {pc(r['mc_p_above'])} (price {money(r['price'])})" for r in top)
            + "\nFewest:\n" + "\n".join(f"- ${_tk(r)} {pc(r['mc_p_above'])}" for r in low)
            + "\n\nFormat with line breaks: one headline line, one line per cashtag with its share, then a short question.")
    t1 = ("Monte Carlo DCF, 2,000 scenarios each. Share of scenarios worth more than today's price:\n\n"
          + "\n".join(f"${_tk(r)} {pc(r['mc_p_above'])}" for r in top) + "\n\nModels, not promises. Which one surprises you?")
    t2 = ("Fewest Monte Carlo scenarios (out of 2,000) worth more than today's price:\n\n"
          + "\n".join(f"${_tk(r)} {pc(r['mc_p_above'])}" for r in low) + "\n\nPriced for perfection, or is the model missing something?")
    fbs = _fit([t1, t2])
    if not fbs:
        return None
    use = [_tk(r) for r in (top if fbs[0] == t1 else low)]
    fbs = [f for f in fbs if all(f"${t}" in f for t in use[:2])]      # the required cashtags are the first list's
    return {"kind": "mc_odds", "task": task, "cashtags": use[:2], "allowed": [_tk(r) for r in top + low], "items": E._items(site, by_ticker, use, 2),
            "fallback": fbs[0], "fallbacks": fbs, "lines": True, "tags": E.H.pick("valuation", None, key=f"mc:{today}")}


@kind("distress_watch", tag="credit", hashtags=["#credit", "#CreditRisk", "#bonds", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Distress watch", title="The highest one-year distress probabilities among $2B+ companies (Merton, bond spreads, Altman Z, debt cushion)",
      guide="Say the probabilities are a model blend (Merton distance to default, the bond-calibrated spread, Altman Z, the debt cushion), "
            "a ranking and not a default forecast. One line per cashtag. One neutral question. No alarmist words.", corpus=4)
def plan_distress_watch(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if isinstance(r.get("distress_pd"), (int, float)) and (r.get("mcap") or 0) >= 2e9 and r.get("kind") == "industrial"]
    R = sorted([r for r in R if state_ok("distress_watch", _tk(r), hours=24 * 21)], key=lambda r: -r["distress_pd"])[:5]
    if len(R) < 4 or R[0]["distress_pd"] < 0.01:
        print("distress_watch: fewer than four $2B+ companies with a blended distress probability of 1%+")
        return None

    def p(v):
        return pc(v, 1)
    task = ("ONE-YEAR DISTRESS PROBABILITY (a blend in log-odds of: Merton distance to default from the share price, the bond-calibrated 5-year "
            "spread, Altman Z mapped to rating-equivalent default rates, and the debt cushion score — not calibrated to realized defaults), "
            "companies worth $2B+:\n" + "\n".join(f"- ${_tk(r)}: {p(r['distress_pd'])}" + (f", distance to default {r['distance_to_default']:.1f}"
                                                                                      if isinstance(r.get('distance_to_default'), (int, float)) else "")
                                                   + (f", Altman Z {r['altman_z']:.1f}" if isinstance(r.get('altman_z'), (int, float)) else "") for r in R)
            + "\n\nSay it is a model ranking, not a prediction. Line breaks, one line per cashtag, then a neutral question.")
    t1 = ("Highest one-year distress probabilities among $2B+ companies (model blend: Merton, bond spreads, Altman Z, debt cushion):\n\n"
          + "\n".join(f"${_tk(r)} {p(r['distress_pd'])}" for r in R) + "\n\nA ranking, not a default forecast. Any surprises?")
    t2 = ("Credit stress, ranked (blend of equity-implied and bond-implied default odds, $2B+ companies):\n\n"
          + "\n".join(f"${_tk(r)} {p(r['distress_pd'])}" for r in R) + "\n\nWhich of these would you look at first?")
    fbs = _fit([t1, t2])
    if not fbs:
        return None
    tks = [_tk(r) for r in R]
    return {"kind": "distress_watch", "task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks, 2),
            "fallback": fbs[0], "fallbacks": fbs, "lines": True, "must": (r"model|blend|ranking", "say the numbers are a model blend / ranking"),
            "tags": E.H.pick("credit", None, key=f"distress:{today}")}


def _median(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    return xs[len(xs) // 2] if xs else None


@kind("wacc_gap", tag="credit", hashtags=["#credit", "#CostOfCapital", "#bonds", "#stocks"], cooldown=24 * 6, schedule=["weekly"],
      label="✦ Cost of capital outlier", title="A large company paying far more for its debt and capital than the median company",
      guide="Give the company's cost of debt and its WACC, and the median company's, from the facts. Ask what explains the gap. "
            "Never say the company is risky or safe.", corpus=6)
def plan_wacc_gap(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if isinstance(r.get("wacc"), (int, float)) and isinstance(r.get("kd"), (int, float))]
    if len(R) < 30:
        return None
    mk, mw = _median([r["kd"] for r in R]), _median([r["wacc"] for r in R])
    cands = [r for r in R if (r.get("mcap") or 0) >= 10e9 and r["kd"] - mk >= 0.015 and state_ok("wacc_gap", _tk(r), hours=24 * 30)]
    for r in sorted(cands, key=lambda r: -(r["kd"] - mk)):
        tk = _tk(r)
        d = _doc(site, r["cik"]) or {}
        W = d.get("wacc") or {}
        how = W.get("kd_how") or ""
        task = (f"COST OF CAPITAL, ${tk} ({E.short_name(r.get('name') or tk, tk)}), from its filings, bond data and prices:\n"
                f"- cost of debt {pc(r['kd'], 1)} ({how})\n- WACC {pc(r['wacc'], 1)}"
                + (f" (beta {W['beta']:.2f})" if isinstance(W.get("beta"), (int, float)) else "")
                + f"\n- the median company tracked: cost of debt {pc(mk, 1)}, WACC {pc(mw, 1)}\n\nGive both pairs, ask what explains the gap.")
        fbs = _fit([f"${tk} pays about {pc(r['kd'], 1)} on its debt, and its overall cost of capital is {pc(r['wacc'], 1)}. The median company we track: "
                    f"{pc(mk, 1)} and {pc(mw, 1)}. What explains the gap?",
                    f"Cost of capital check: ${tk} {pc(r['wacc'], 1)} (debt at {pc(r['kd'], 1)}) vs {pc(mw, 1)} for the median company. "
                    f"A higher hurdle for every project. Temporary, or structural?"])
        if fbs:
            return {"kind": "wacc_gap", "task": task, "cashtags": [tk], "items": E._items(site, by_ticker, [tk], 1), "fallback": fbs[0],
                    "fallbacks": fbs, "tags": _tags("credit", site, by_ticker, tk, f"wacc:{tk}")}
    print("wacc_gap: no $10B+ company with a cost of debt 1.5 points above the median")
    return None


@kind("pe_band", tag="valuation", hashtags=["#valuation", "#PE", "#stocks", "#investing"], cooldown=44, schedule=["close"],
      label="✦ P/E range extremes", title="Large companies at the bottom (or top) of their own P/E range since mid-2022",
      guide="One line per cashtag with its P/E and where it sits in its own range (percentile). Say the range is its own history since mid-2022. "
            "One question; never call a stock cheap, a bargain or expensive as a verdict.", corpus=6)
def plan_pe_band(site, rows, c, by_ticker, state_ok, today):
    R = [r for r in _index(site) if isinstance(r.get("pe_pct"), (int, float)) and isinstance(r.get("pe"), (int, float)) and (r.get("mcap") or 0) >= 10e9]
    R = [r for r in R if state_ok("pe_band", _tk(r), hours=24 * 10)]
    lo = sorted([r for r in R if r["pe_pct"] <= 0.1], key=lambda r: (r["pe_pct"], -(r.get("mcap") or 0)))[:5]
    hi = sorted([r for r in R if r["pe_pct"] >= 0.9], key=lambda r: (-r["pe_pct"], -(r.get("mcap") or 0)))[:5]
    pick, where = (lo, "bottom") if len(lo) >= 3 else (hi, "top") if len(hi) >= 3 else (None, None)
    if not pick:
        print("pe_band: fewer than three $10B+ companies at either end of their P/E range")
        return None

    def ordinal(v):
        n = int(round(v * 100))
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    task = (f"P/E AGAINST EACH COMPANY'S OWN RANGE (weekly, since mid-2022; trailing EPS counted 60 days after each quarter), companies worth $10B+, "
            f"at the {where} of their range:\n" + "\n".join(f"- ${_tk(r)}: P/E {r['pe']:.1f}, {ordinal(r['pe_pct'])} percentile of its range" for r in pick)
            + "\n\nLine breaks: a headline, one line per cashtag (P/E and percentile), one question.")
    lines = "\n".join(f"${_tk(r)} P/E {r['pe']:.1f} ({ordinal(r['pe_pct'])} pct)" for r in pick)
    if where == "bottom":
        fbs = [f"Near the bottom of their own P/E range since 2022:\n\n{lines}\n\nCheap for a reason, or overlooked?",
               f"Lowest P/E vs their own history (since 2022):\n\n{lines}\n\nWhat is the market worried about?"]
    else:
        fbs = [f"At the top of their own P/E range since 2022:\n\n{lines}\n\nEarned it, or stretched?",
               f"Highest P/E vs their own history (since 2022):\n\n{lines}\n\nWhat would it take to justify these?"]
    fbs = _fit(fbs)
    if not fbs:
        return None
    tks = [_tk(r) for r in pick]
    return {"kind": "pe_band", "task": task, "cashtags": tks[:2], "allowed": tks, "items": E._items(site, by_ticker, tks, 2), "fallback": fbs[0],
            "fallbacks": fbs, "lines": True, "tags": E.H.pick("valuation", None, key=f"pe:{today}:{where}")}
