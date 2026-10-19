"""What the buyers' capital spending costs them and what it has earned so far: the "AI investment return" part of a
spend chain's page (pipeline/chains.py, after the forecast model in pipeline/chainmodel.py).

For each buyer, from its own filings:

  Depreciation. Every quarter's capex is taken to depreciate in equal parts over L quarters, from the quarter after it
  is spent; L (an effective life: equipment, buildings and construction not yet in service together) is the one that
  best reproduces the depreciation the company reported over the last three years, with a constant for assets bought
  before the eight years on file. Ahead, the same rule runs on the capex path of the forecast (base, −20%, +20%), so the
  depreciation still to come from what has been spent — and what the next quarters add — is shown, not guessed.

  Return so far. The spending of the last two years needs, every year, its depreciation (1/L of it) plus a return on it
  (a 10% pre-tax hurdle) in extra operating profit: compared with the operating profit the company actually added over
  the same two years. And operating profit added (after a 21% tax) per dollar of net property and equipment added.

  Cash. Free cash flow over the next four quarters: operating cash flow carried forward at its last-year growth (held
  between −20% and +40%) minus the capex of each case.

  Per share. Lower capex means lower depreciation later: what the −20% case changes in depreciation over the next two
  years, after tax, per diluted share — before any effect on revenue.
"""
import datetime as dt

from . import chainmodel as CM

HURDLE = 0.10
TAX = 0.21
FIT_Q = 12                       # quarters the depreciation rule is fitted on
LIVES = range(12, 61)            # effective lives tried, in quarters (3 to 15 years)
AHEAD = 10                       # quarters of depreciation projected


def _q(series):
    """{end: v} -> {calendar quarter: v}"""
    return CM.by_quarter({e: v for e, v in series.items() if v is not None})


def fit_life(C, D):
    """(L quarters, base, rms error) of the straight-line rule that best reproduces reported depreciation D from capex C."""
    ks = sorted(k for k in D if k - 1 in C)[-FIT_Q:]
    if len(ks) < 6:
        return None
    first = min(C)
    best = None
    for L in LIVES:
        pred = {k: sum(C.get(v, 0) for v in range(max(k - L, first), k)) / L for k in ks}
        base = max(sum(D[k] - pred[k] for k in ks) / len(ks), 0.0)
        sse = sum((D[k] - pred[k] - base) ** 2 for k in ks)
        if best is None or sse < best[2]:
            best = (L, base, sse)
    L, base, sse = best
    return L, base, (sse / len(ks)) ** 0.5


def project(C, L, base, path, f, k_last, ahead=AHEAD):
    """Depreciation per quarter after k_last, capex = history, then the path × f (held flat after its end)."""
    full = dict(C)
    last_v = None
    for k in range(k_last + 1, k_last + ahead + 1):
        if k in path:
            last_v = path[k] * f
        if last_v is not None:
            full[k] = last_v
    first = min(C)
    return {k: sum(full.get(v, 0) for v in range(max(k - L, first), k)) / L + base for k in range(k_last + 1, k_last + ahead + 1)}


def ttm_at(series_q, k):
    if all(series_q.get(x) is not None for x in range(k - 3, k + 1)):
        return sum(series_q[x] for x in range(k - 3, k + 1))
    return None


def buyer(b, co, model):
    """The figures for one buyer ($B), or None."""
    C = {k: v / 1e9 for k, v in _q(co.history("capex")).items()}
    D = {k: v / 1e9 for k, v in _q(co.history("dep")).items()}
    da = False
    if len(D) < 8:
        D, da = {k: v / 1e9 for k, v in _q(co.history("da")).items()}, True
    if len(C) < 8 or len(D) < 6:
        return None
    fl = fit_life(C, D)
    if not fl:
        return None
    L, base, rms = fl
    kc = max(C)
    path = {CM.cq_from_label(q): v for q, v in ((model or {}).get("buyer_paths") or {}).get(b["t"], [])}
    proj = {sc: project(C, L, base, path, f, kc) for sc, f in CM.SCEN.items()}
    OI = {k: v / 1e9 for k, v in _q(co.history("oi")).items()}
    OCF = {k: v / 1e9 for k, v in _q(co.history("ocf")).items()}
    REV = {k: v / 1e9 for k, v in _q(co.history("revenue")).items()}
    ko = max(OI) if OI else kc
    oi_now, oi_2y = ttm_at(OI, ko), ttm_at(OI, ko - 8)
    capex_8q = sum(C.get(k, 0) for k in range(kc - 7, kc + 1))
    need = capex_8q * (4.0 / L + HURDLE)                       # a year's depreciation + the hurdle return
    ppe = sorted(((co.xf.get("qh") or {}).get("ppe") or []))
    ppe_q = {CM.cq(e): v / 1e9 * co.conv for e, v in ppe}
    kp = max(ppe_q) if ppe_q else None
    d_ppe = (ppe_q[kp] - ppe_q[kp - 8]) if kp is not None and (kp - 8) in ppe_q else None
    d_oi = (oi_now - oi_2y) if oi_now is not None and oi_2y is not None else None
    kf = max(OCF) if OCF else kc
    ocf_now, ocf_py = ttm_at(OCF, kf), ttm_at(OCF, kf - 4)
    g = max(min(ocf_now / ocf_py - 1, 0.4), -0.2) if ocf_now and ocf_py and ocf_py > 0 else 0.0
    nxt = list(range(kc + 1, kc + 5))
    fcf = {}
    for sc, f in CM.SCEN.items():
        capex_next = sum(path.get(k, C[kc]) * f for k in nxt)
        fcf[sc] = {"capex": round(capex_next, 3), "ocf": round(ocf_now * (1 + g), 3) if ocf_now else None,
                   "fcf": round(ocf_now * (1 + g) - capex_next, 3) if ocf_now else None}
    shares = None
    for s in reversed(((co.rec.get("quality") or {}).get("cap") or {}).get("shares") or []):
        if s.get("diluted"):
            shares = s["diluted"]
            break
    two = list(range(kc + 1, kc + 9))
    d_dep = sum(proj["base"][k] - proj["down"][k] for k in two)
    rev_now = ttm_at(REV, max(REV)) if REV else None
    dep_hist = [[CM.qlabel(k), round(v, 4)] for k, v in sorted(D.items())[-16:]]
    return {
        "t": b["t"], "life_q": L, "life_y": round(L / 4, 1), "base": round(base, 3), "rms": round(rms, 3), "da_used": da,
        "dep_ttm": round(ttm_at(D, max(D)) or 0, 3), "capex_ttm": round(ttm_at(C, kc) or 0, 3),
        "dep_next4": {sc: round(sum(p[k] for k in nxt), 3) for sc, p in proj.items()},
        "dep_years": {sc: _years(p) for sc, p in proj.items()},
        "dep_path": {sc: [[CM.qlabel(k), round(v, 4)] for k, v in sorted(p.items())] for sc, p in proj.items()},
        "dep_hist": dep_hist,
        "oi_ttm": round(oi_now, 3) if oi_now is not None else None, "oi_2y": round(oi_2y, 3) if oi_2y is not None else None,
        "rev_ttm": round(rev_now, 3) if rev_now else None,
        "capex_8q": round(capex_8q, 3), "need": round(need, 3), "d_oi": round(d_oi, 3) if d_oi is not None else None,
        "cover": round(d_oi / need, 3) if d_oi is not None and need > 0 else None,
        "d_ppe": round(d_ppe, 3) if d_ppe is not None else None,
        "roic_incr": round(d_oi * (1 - TAX) / d_ppe, 4) if d_oi is not None and d_ppe and d_ppe > 0 else None,
        "ocf_ttm": round(ocf_now, 3) if ocf_now else None, "ocf_growth": round(g, 4), "fcf_next4": fcf,
        "shares": shares, "down_dep_2y": round(d_dep, 3),
        "down_eps_2y": round(d_dep * 1e9 * (1 - TAX) / shares, 3) if shares else None,
        "last": CM.qlabel(kc),
    }


def _years(p):
    by = {}
    for k, v in p.items():
        by.setdefault(k // 4, []).append(v)
    return {str(y): round(sum(v), 3) for y, v in by.items() if len(v) == 4}


def run(ch, res, cos):
    model = res.get("model") if isinstance(res.get("model"), dict) and not res["model"].get("error") else None
    rows = []
    for b in res.get("_buyers") or []:
        co = cos.get(b["t"])
        if not co:
            continue
        try:
            r = buyer(b, co, model)
        except (ValueError, ZeroDivisionError, KeyError) as e:
            print(f"  capex return not computed for {b['t']}: {e}")
            r = None
        if r:
            rows.append(r)
    if not rows:
        return None
    tot = lambda key, sc=None: round(sum((r[key][sc] if sc else r[key]) or 0 for r in rows), 3)
    # combined: a quarter counts when every buyer has a figure for it, reported or (after its last report) projected
    H = {r["t"]: {CM.cq_from_label(q): v for q, v in r["dep_hist"]} for r in rows}
    last_common = min(max(h) for h in H.values())
    hist = [[CM.qlabel(k), round(sum(H[t][k] for t in H), 4)] for k in sorted(set.intersection(*[set(h) for h in H.values()]))
            if k <= last_common][-16:]
    combined = {}
    for sc in CM.SCEN:
        P = {r["t"]: {CM.cq_from_label(q): v for q, v in r["dep_path"][sc]} for r in rows}
        out = []
        for k in range(last_common + 1, last_common + AHEAD + 1):
            vals = [H[t].get(k, P[t].get(k)) for t in H]
            if any(v is None for v in vals):
                break
            out.append([CM.qlabel(k), round(sum(vals), 4)])
        combined[sc] = out
    covered = [r for r in rows if r.get("cover") is not None]
    return {"hurdle": HURDLE, "tax": TAX, "buyers": rows,
            "combined": {"dep_hist": hist, "dep_path": combined,
                         "dep_ttm": tot("dep_ttm"), "capex_ttm": tot("capex_ttm"),
                         "dep_next4": {sc: tot("dep_next4", sc) for sc in CM.SCEN},
                         "capex_8q": tot("capex_8q"), "need": tot("need"),
                         "d_oi": round(sum(r["d_oi"] for r in covered), 3) if covered else None,
                         "need_covered": round(sum(r["need"] for r in covered), 3) if covered else None},
            "asof": dt.date.today().isoformat()}
