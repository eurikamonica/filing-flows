"""The EPS forecast: one GAAP diluted EPS figure per company for its next quarter, with an 80% range and the
probability that it beats the same quarter last year, and a record of every forecast frozen before the report.

Three estimates of the same quarter, all on the SEC GAAP diluted basis:
  F  the fundamental model (eps_fundamental.forecast): revenue, margins, tax and shares from the company's filings;
  S  Wall Street's consensus, converted to GAAP: analysts estimate adjusted EPS, so the company's typical gap between
     its adjusted and its GAAP EPS (median of its last four reported quarters, each GAAP figure as first filed) is
     subtracted;
  G  the company's own guidance from its last earnings release (eps_guide.py), converted the same way when it is
     adjusted; a full-year range gives the fourth quarter as the year less the three quarters already reported.
They are averaged with weights inverse to their walk-forward squared relative errors (S's weight fitted on the
quarters where both F and S existed, pooled across companies; G, untested yet, takes S's weight). The range and the
probability come from the pooled walk-forward residuals (scaled by each company's usual |EPS|), and the probability is
shrunk toward the base rate by the factor that minimised its Brier score; both are checked out of sample by
splitting the companies in two (fit on one half, score on the other).

Every run freezes each company's forecast for the coming quarter in store/eps-ledger.json and stops updating it once
the quarter is reported (its earnings release or 10-Q is on the site); when the GAAP figure is filed the row is scored.
That ledger is the out-of-sample record: data/eps-fundamental/scorecard.json.
"""
import bisect
import datetime as dt
import json
import math
import statistics
from pathlib import Path

from . import eps_fundamental as F
from .eps_gaap import iso, read, write, summary

TOL = 25                       # days: analysts label a quarter by its calendar month end (NVIDIA's Oct 26 is "Oct 31")
CAP = 5.0                      # relative errors beyond 5x the company's usual |EPS| count as 5


def num(v):
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def near(keys, end, tol=TOL):
    best = None
    for k in keys:
        d = abs((iso(k) - iso(end)).days)
        if d <= tol and (best is None or d < best[0]):
            best = (d, k)
    return best[1] if best else None


def gaap_map(series):
    """{quarter end: {"eps", "filed", "derived"}}: the GAAP diluted EPS as first filed, on today's share basis."""
    rows = []
    for r in series:
        e = r["fields"].get("eps")
        if not e:
            continue
        rows.append({"end": r["end"], "eps": e["val"], "filed": e["filed"], "derived": bool(e.get("derived")),
                     "diluted_shares": (r["fields"].get("diluted_shares") or {}).get("val") or 0})
    m = {x["end"]: x for x in rows}
    with_sh = [x for x in rows if x["diluted_shares"] > 0]
    for x in F.split_adjusted(with_sh) if with_sh else []:
        m[x["end"]] = x
    return m


def scale_at(gm, cutoff, before=None):
    """The company's usual |EPS| from its last four quarters public at the cutoff."""
    last = [abs(v["eps"]) for k, v in sorted(gm.items()) if v["filed"] < cutoff and (before is None or k < before)][-4:]
    return max(0.10, sum(last) / len(last)) if last else 0.25


# ---------------------------------------------------------------------------------------------------- Wall Street
def surprises(cons):
    a = (cons or {}).get("analysts") or {}
    s = a.get("surprises") or (cons or {}).get("surprises") or []
    return sorted((x for x in s if num(x.get("eps_est")) and num(x.get("eps_act")) and x.get("reported") and x.get("quarter")),
                  key=lambda x: x["reported"])


def gaps(cons, gm, cutoff):
    """[(reported, quarter end, adjusted EPS - GAAP EPS)] for quarters whose both figures were public at the cutoff."""
    out = []
    for x in surprises(cons):
        if x["reported"] >= cutoff:
            continue
        k = near(gm, x["quarter"])
        if not k or gm[k]["filed"] >= cutoff:
            continue
        out.append((x["reported"], k, float(x["eps_act"]) - gm[k]["eps"]))
    return out


def typical_gap(gs):
    return statistics.median([g for _, _, g in gs[-4:]]) if gs else None


def street_live(cons, gm, target_end, cutoff):
    a = (cons or {}).get("analysts") or {}
    p = next((x for x in a.get("periods") or [] if x.get("period") == "0q"), None)
    e = (p or {}).get("eps") or {}
    if not p or not num(e.get("avg")) or not p.get("end") or abs((iso(p["end"]) - iso(target_end)).days) > TOL:
        return None
    if a.get("as_of") and str(a["as_of"])[:10] > cutoff:
        return None
    gs = gaps(cons, gm, cutoff)
    g = typical_gap(gs)
    return {"consensus": float(e["avg"]), "analysts": e.get("numberOfAnalysts"), "low": e.get("low"), "high": e.get("high"),
            "gap": round(g, 4) if g is not None else None, "gaps_n": len(gs),
            "gaap_equivalent": round(float(e["avg"]) - g, 4) if g is not None else None,
            "as_of": a.get("as_of"), "next_report": (a.get("next_earnings") or {}).get("date")}


def street_rows(cons, gm):
    """Past quarters as the converted consensus would have forecast them: the estimate before the report less the
    median gap of the quarters reported before it."""
    out, prior = [], []
    for x in surprises(cons):
        k = near(gm, x["quarter"])
        if k:
            if prior:
                g = statistics.median([v for v in prior[-4:]])
                out.append({"end": k, "reported": x["reported"], "street_adj": float(x["eps_est"]),
                            "street": float(x["eps_est"]) - g, "actual": gm[k]["eps"]})
            prior.append(float(x["eps_act"]) - gm[k]["eps"])
    return out


# ---------------------------------------------------------------------------------------------------- guidance
def to_gaap(row, gap):
    mid = row["mid"]
    if row["basis"] == "gaap":
        return mid
    if row["basis"] == "adjusted":
        return mid - gap if gap is not None else None
    if gap is None or abs(gap) <= max(0.03, 0.05 * abs(mid)):          # "diluted EPS", no basis named: GAAP when the
        return mid                                                       # company's two figures are about the same
    return None


def guidance(gdoc, gm, target_end, cutoff, gap):
    """The company's own figure for the target quarter, on the GAAP basis, or None."""
    t = iso(target_end)
    rels = [r for r in (gdoc or {}).get("releases") or [] if (r.get("filed") or "") < cutoff]
    rels.sort(key=lambda r: r.get("filed") or "", reverse=True)
    for rel in rels:
        f = iso(rel["filed"])
        if not (t - dt.timedelta(days=120) <= f <= t + dt.timedelta(days=20)):
            continue
        for r in rel.get("rows") or []:
            if r.get("period") == "q":
                v = to_gaap(r, gap)
                if v is not None:
                    return {"value": round(v, 4), "kind": "quarter", "basis": r["basis"], "range": [r["lo"], r["hi"]],
                            "text": r["text"], "url": rel.get("url"), "filed": rel["filed"]}
    ya = near(gm, (t - dt.timedelta(days=364)).isoformat(), 20)
    if not ya or not gm[ya].get("derived"):                  # full-year guidance only fixes a fiscal fourth quarter
        return None
    q123 = [k for k in gm if t - dt.timedelta(days=300) <= iso(k) <= t - dt.timedelta(days=60) and gm[k]["filed"] < cutoff]
    if len(q123) != 3:
        return None
    for rel in rels:
        if iso(rel["filed"]) < t - dt.timedelta(days=330):
            break
        for r in rel.get("rows") or []:
            if r.get("period") != "fy":
                continue
            fy = to_gaap(r, 4 * gap if gap is not None else None)
            if fy is None:
                continue
            v = fy - sum(gm[k]["eps"] for k in q123)
            return {"value": round(v, 4), "kind": "full year less three quarters", "basis": r["basis"],
                    "range": [r["lo"], r["hi"]], "text": r["text"], "url": rel.get("url"), "filed": rel["filed"]}
    return None


# ---------------------------------------------------------------------------------------------------- calibration
def rel_sq(err, scale):
    return min((err / scale) ** 2, CAP ** 2)


def street_bias(pairs):
    """Companies usually beat their consensus: the median of (actual - converted consensus) / usual |EPS| over the
    quarters fitted on, added back to the converted consensus."""
    res = [(p["actual"] - p["street"]) / p["scale"] for p in pairs]
    return statistics.median(res) if len(res) >= 50 else 0.0


def blend_of(r, w, b):
    return (1 - w) * r["forecast"] + w * (r["street"] + b * r["scale"])


def fit_weight(pairs):
    """S's share of the F/S average and S's beat bias: the share (0, 0.05 ... 1) with the lowest mean relative error."""
    if len(pairs) < 20:
        return 0.5, 0.0
    b = street_bias(pairs)
    best = min((sum(min(abs(p["actual"] - blend_of(p, w, b)) / p["scale"], CAP) for p in pairs) / len(pairs), w)
               for w in [i / 20 for i in range(21)])
    return best[1], b


def stage_pools(rows, min_n=150):
    """The fundamental model's scaled residuals by business stage (mature companies miss by less), else all of them."""
    allp = residuals(rows, "forecast")
    by = {}
    for r in rows:
        by.setdefault(r.get("stage"), []).append(r)
    pools = {k: residuals(v, "forecast") for k, v in by.items() if len(v) >= min_n}
    return lambda stage: pools.get(stage) or allp


def norm(r):
    """A row's residual unit: the company's usual |EPS| times how predictable the company has been (v)."""
    return r["scale"] * r.get("v", 1.0)


def residuals(rows, key):
    return sorted(max(-2 * CAP, min(2 * CAP, (r["actual"] - r[key]) / norm(r))) for r in rows if r.get(key) is not None)


def add_predictability(frows, others=(), k=8):
    """v = how hard the company has been to forecast: the median of its own earlier walk-forward misses (relative to
    its usual |EPS|, before each row's cutoff), shrunk toward the median of all companies with k pseudo-quarters, as a
    multiple of that median. Ranges are then narrower for steady companies and wider for erratic ones."""
    rel = lambda x: min(abs(x["actual"] - x["forecast"]) / x["scale"], CAP)
    pool_m = statistics.median([rel(r) for r in frows]) if frows else 1.0
    pool_m = pool_m or 1.0
    by = {}
    for r in frows:
        by.setdefault(r["cik"], []).append(r)

    def v_at(cik, cutoff):
        past = [rel(x) for x in by.get(cik, []) if cutoff is None or x["filed"] < cutoff]
        m = statistics.median(past) if past else pool_m
        return (len(past) * m + k * pool_m) / (len(past) + k) / pool_m
    for r in list(frows) + list(others):
        r["v"] = v_at(r["cik"], r.get("cutoff"))
    return v_at


def q(pool, p):
    return F.quantile(pool, p) if pool else None


def p_up(pool, point, scale, base):
    """P(actual > year-ago) under the pooled residuals (scale: the residual unit, usual |EPS| x predictability)."""
    if not pool or base is None:
        return None
    x = (base - point) / scale
    return 1 - bisect.bisect_right(pool, x) / len(pool)


def fit_shrink(rows, pool_of, key):
    """k in p' = rate + k (p - rate) minimising the Brier score; rate = share of quarters above the year-ago figure."""
    data = []
    for r in rows:
        if r.get("same_quarter_last_year") is None:
            continue
        p = p_up(pool_of(r), r[key], norm(r), r["same_quarter_last_year"])
        if p is not None:
            data.append((p, float(r["actual"] > r["same_quarter_last_year"])))
    if len(data) < 50:
        return 1.0, None, data
    rate = sum(y for _, y in data) / len(data)
    best = min((sum((rate + k * (p - rate) - y) ** 2 for p, y in data) / len(data), k) for k in [i / 20 for i in range(21)])
    return best[1], rate, data


def two_fold(rows):
    a = [r for r in rows if int(r["cik"]) % 2 == 0]
    b = [r for r in rows if int(r["cik"]) % 2 == 1]
    return a, b


def validate(frows, prows):
    """Out-of-sample checks by splitting the companies in two: the S weight, the 80% range and the probability are
    fitted on one half and scored on the other."""
    out = {}
    fa, fb = two_fold(frows)
    pa, pb = two_fold(prows)
    scored = []
    for fit_p, test_p in ((pa, pb), (pb, pa)):
        w, b = fit_weight(fit_p)
        for r in test_p:
            scored.append({**r, "blend": blend_of(r, w, b)})
    bc, bn = 0, 0
    for fit_p, test_p in ((pa, pb), (pb, pa)):            # the blend's 80% range, fitted on the other half
        w, b = fit_weight(fit_p)
        pool = residuals([{**r, "blend": blend_of(r, w, b)} for r in fit_p], "blend")
        if len(pool) < 50:
            continue
        lo, hi = q(pool, .10), q(pool, .90)
        for r in test_p:
            x = blend_of(r, w, b)
            bn += 1
            bc += x + lo * norm(r) <= r["actual"] <= x + hi * norm(r)
    if bn:
        out["blend_range"] = {"n": bn, "coverage_80": round(bc / bn, 4)}
    if scored:
        out["paired"] = {"n": len(scored), "fundamental": summary(scored, "forecast", "same_quarter_last_year"),
                         "street": summary(scored, "street", "same_quarter_last_year"),
                         "blend": summary(scored, "blend", "same_quarter_last_year"),
                         "blend_vs_street": summary(scored, "blend", "street")}
    cov, brier, base_brier, n = 0, 0.0, 0.0, 0
    for fit, test in ((fa, fb), (fb, fa)):
        pools = stage_pools(fit)
        k, rate, _ = fit_shrink(fit, lambda r: pools(r.get("stage")), "forecast")
        for r in test:
            pool = pools(r.get("stage"))
            if not pool:
                continue
            lo, hi = q(pool, .10), q(pool, .90)
            n += 1
            cov += r["forecast"] + lo * norm(r) <= r["actual"] <= r["forecast"] + hi * norm(r)
            p = p_up(pool, r["forecast"], norm(r), r["same_quarter_last_year"])
            if p is not None and rate is not None:
                y = float(r["actual"] > r["same_quarter_last_year"])
                brier += (rate + k * (p - rate) - y) ** 2
                base_brier += (rate - y) ** 2
    if n:
        out["fundamental_range"] = {"n": n, "coverage_80": round(cov / n, 4)}
        out["probability"] = {"n": n, "brier": round(brier / n, 4), "brier_base_rate": round(base_brier / n, 4)}
    return out


# ---------------------------------------------------------------------------------------------------- the run
def reported_set(index_path):
    """{cik: [quarter ends on the site]}: a quarter whose earnings release or 10-Q is in."""
    d = read(index_path, {}) if index_path else {}
    out = {}
    for r in d.get("companies") or []:
        if r.get("cik") and r.get("end"):
            out.setdefault(str(r["cik"]), set()).add(r["end"])
    return out


def run(store, out, consensus=None, guide=None, ledger=None, index=None, today=None):
    root, dst = Path(store), Path(out)
    dst.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today().isoformat()
    asof = (iso(today) + dt.timedelta(days=1)).isoformat()      # filings of today count
    reported = reported_set(index)
    frows, prows, live = [], [], {}
    for file in sorted(root.glob("*.json")):
        if file.name == "progress.json":
            continue
        d = read(file, {})
        series = d.get("quarters") or []
        if not series:
            continue
        cik = file.stem
        gm = gaap_map(series)
        cons = read(Path(consensus) / f"{cik}.json", None) if consensus else None
        bt = F.backtest(series)
        for r in bt["rows"]:
            frows.append({**r, "cik": cik})
        srows = street_rows(cons, gm) if cons else []
        for s in srows:                                        # quarters where both F and S existed
            fr = next((r for r in bt["rows"] if r["end"] == s["end"]), None)
            if fr and s["reported"] > fr["cutoff"]:
                prows.append({**fr, "cik": cik, "street": s["street"], "street_adj": s["street_adj"]})
        live[cik] = {"d": d, "gm": gm, "cons": cons, "bt": bt,
                     "events": read(root.parent / "eps-events" / file.name, {}).get("events", [])}
    # the pooled fits on every quarter
    v_at = add_predictability(frows, prows)
    w_s, b_s = fit_weight(prows)
    pool_f = residuals(frows, "forecast")
    pools_f = stage_pools(frows)
    blend_rows = [{**r, "blend": blend_of(r, w_s, b_s)} for r in prows]
    pool_b = residuals(blend_rows, "blend") if len(blend_rows) >= 100 else pool_f
    k_f, rate_f, _ = fit_shrink(frows, lambda r: pools_f(r.get("stage")), "forecast")
    k_b, rate_b, _ = fit_shrink(blend_rows, lambda r: pool_b, "blend") if len(blend_rows) >= 100 else (k_f, rate_f, None)
    checks = validate(frows, prows)
    book = read(ledger, {"v": 1, "rows": {}}) if ledger else {"v": 1, "rows": {}}
    rows = book.setdefault("rows", {})
    shown = 0
    for cik, L in live.items():
        d, gm, cons = L["d"], L["gm"], L["cons"]
        fc = F.forecast(d["quarters"], asof, events=L["events"])
        target = fc["target_end"] if fc else None
        st = None
        if cons:
            p0 = next((x for x in ((cons.get("analysts") or {}).get("periods") or []) if x.get("period") == "0q"), None)
            tgt = target or (p0 or {}).get("end")
            st = street_live(cons, gm, tgt, asof) if tgt else None
            if st and not target and st.get("gaap_equivalent") is not None:
                target = tgt
        head = None
        if target:
            ya_k = near(gm, (iso(target) - dt.timedelta(days=364)).isoformat(), 20)
            year_ago = gm[ya_k]["eps"] if ya_k else (fc or {}).get("eps_gaap_last_year")
            scale = scale_at(gm, asof)
            unit = scale * v_at(cik, None)                  # the residual unit for this company's range
            g = guidance(read(Path(guide) / f"{cik}.json", None) if guide else None, gm, target, asof, (st or {}).get("gap"))
            parts, weights = {}, {}
            if fc:
                parts["fundamental"], weights["fundamental"] = fc["point"], 1 - w_s
            if st and st.get("gaap_equivalent") is not None:
                st["beat"] = round(b_s * scale, 4)                # companies usually beat their consensus by this much
                parts["street"], weights["street"] = round(st["gaap_equivalent"] + b_s * scale, 4), w_s
            if g:
                parts["guidance"], weights["guidance"] = g["value"], w_s
            if parts:
                tot = sum(weights.values())
                point = sum(parts[k] * weights[k] for k in parts) / tot
                blended = len(parts) > 1 or "fundamental" not in parts
                pool, k, rate = (pool_b, k_b, rate_b) if blended else (pools_f((fc or {}).get("company_stage")), k_f, rate_f)
                p = p_up(pool, point, unit, year_ago)
                head = {"target_end": target, "point": round(point, 4),
                        "p10": round(point + q(pool, .10) * unit, 4) if pool else None,
                        "p90": round(point + q(pool, .90) * unit, 4) if pool else None,
                        "predictability": round(unit / scale, 3),
                        "p_up": round(rate + k * (p - rate), 4) if p is not None and rate is not None else None,
                        "year_ago": year_ago, "scale": round(scale, 4), "kind": "blend" if blended else "fundamental",
                        "components": parts, "weights": {k2: round(v / tot, 3) for k2, v in weights.items()},
                        "street": st, "guidance": g, "as_of": asof}
                shown += 1
        # the ledger: the forecast is refreshed every run until the quarter is reported, then frozen for good
        if head:
            key = f"{cik}|{head['target_end']}"
            old = rows.get(key)
            is_in = any(abs((iso(e) - iso(head["target_end"])).days) <= 10 for e in reported.get(cik, ()))
            if is_in:
                if old and not old.get("locked"):
                    old["locked"], old["locked_at"] = True, today
            elif not (old and old.get("locked")):
                rows[key] = {"cik": int(cik), "ticker": d.get("ticker"), "target_end": head["target_end"], "frozen_at": today,
                             "point": head["point"], "p10": head["p10"], "p90": head["p90"], "p_up": head["p_up"],
                             "year_ago": head["year_ago"], "scale": head["scale"], "components": head["components"],
                             "kind": head["kind"], "street_adj": (st or {}).get("consensus"), "locked": False}
        L["head"] = head
        L["fc"] = fc
    # score what has been reported and filed
    for key, r in rows.items():
        if r.get("actual") is not None or not r.get("target_end"):
            continue
        L = live.get(str(r["cik"]))
        if not L:
            continue
        k = near(L["gm"], r["target_end"], 20)
        if k and L["gm"][k]["filed"] < asof:
            r["actual"], r["actual_filed"], r["locked"] = L["gm"][k]["eps"], L["gm"][k]["filed"], True
            r["valid"] = r["frozen_at"] < L["gm"][k]["filed"]
    cutoff_keep = (iso(today) - dt.timedelta(days=3 * 366)).isoformat()
    book["rows"] = {k: v for k, v in rows.items() if (v.get("target_end") or "") >= cutoff_keep}
    if ledger:
        write(ledger, book)
    scored = [r for r in book["rows"].values() if r.get("actual") is not None and r.get("valid")]
    sc_rows = [{"actual": r["actual"], "point": r["point"], "year_ago": r["year_ago"], "scale": r.get("scale") or max(.10, abs(r["year_ago"] or 0)),
                "street": (r.get("components") or {}).get("street"), "fundamental": (r.get("components") or {}).get("fundamental"),
                "p10": r.get("p10"), "p90": r.get("p90")} for r in scored if r.get("year_ago") is not None]
    card = {"as_of": today, "frozen": sum(1 for r in book["rows"].values() if r.get("point") is not None),
            "scored": len(scored), "vs_year_ago": summary(sc_rows, "point", "year_ago"),
            "vs_street": summary([r for r in sc_rows if r["street"] is not None], "point", "street"),
            "coverage_80": round(sum(r["p10"] <= r["actual"] <= r["p90"] for r in sc_rows if r["p10"] is not None) /
                                 max(1, sum(1 for r in sc_rows if r["p10"] is not None)), 4) if sc_rows else None,
            "recent": sorted(({"ticker": r.get("ticker"), "cik": r["cik"], "target_end": r["target_end"], "point": r["point"],
                               "actual": r["actual"], "year_ago": r["year_ago"], "frozen_at": r["frozen_at"]} for r in scored),
                             key=lambda x: x["target_end"], reverse=True)[:40],
            "note": "Forecasts frozen before each report (store/eps-ledger.json) and scored when the GAAP figure is filed."}
    write(dst / "scorecard.json", card)
    # per company
    by_cik = {}
    for r in book["rows"].values():
        if r.get("cik"):
            by_cik.setdefault(str(r["cik"]), []).append(r)
    for cik, L in live.items():
        bt = L["bt"]
        track = {k: bt.get(k) for k in ("n", "closer_share", "median_ae_model", "median_ae_baseline", "rel_error_model", "rel_error_baseline")}
        mine = sorted(by_cik.get(cik, []), key=lambda r: r["target_end"], reverse=True)[:8]
        write(dst / f"{cik}.json", {"cik": L["d"].get("cik"), "ticker": L["d"].get("ticker"), "source": "SEC_FIRST_FILED_COMPANYFACTS",
                                    "as_of": asof, "headline": L.get("head"), "forecast": L.get("fc"), "track": track,
                                    "ledger": [{k: r.get(k) for k in ("target_end", "frozen_at", "point", "p10", "p90", "year_ago", "actual", "locked")}
                                               for r in mine],
                                    "backtest": {k: v for k, v in bt.items() if k != "rows"}})
    fsum = summary(frows, "forecast", "same_quarter_last_year")
    write(dst / "backtest.json", {
        "as_of": today, "n": fsum.get("n", 0), "companies": len({r["cik"] for r in frows}), "fundamental": fsum,
        "by_stage": {s: summary([r for r in frows if r["stage"] == s], "forecast", "same_quarter_last_year")
                     for s in sorted({r["stage"] for r in frows})},
        "street_weight": round(w_s, 3), "street_beat_bias": round(b_s, 4), "paired_quarters": len(prows),
        "range": {"fundamental": [q(pool_f, .10), q(pool_f, .90)], "blend": [q(pool_b, .10), q(pool_b, .90)]},
        "probability_shrink": {"fundamental": k_f, "blend": k_b, "base_rate": rate_f},
        "out_of_sample": checks, "live_forecasts": shown, "companies_stored": len(live),
        "label": "STRICT_FIRST_FILED_GAAP_EPS_WALK_FORWARD",
        "notes": ["Fourth quarters derived from the 10-K (year less nine months); EPS checked against net income / shares.",
                  "Out-of-sample checks split the companies in two: fitted on one half, scored on the other.",
                  "Analyst estimates are Yahoo's archived pre-report consensus, not audited point-in-time vintages."]})
    print(f"::notice::EPS model: {len(live)} companies, {shown} with a forecast; walk-forward {fsum.get('n', 0)} quarters "
          f"(closer than year-ago {fsum.get('closer_share')}), street weight {w_s:.2f} on {len(prows)} paired quarters; "
          f"ledger {card['frozen']} frozen, {card['scored']} scored")
    return card
