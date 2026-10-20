"""Forecast model for spend chains (pipeline/chains.py): how each supplier's revenue follows the buyers' capital spending.

For each supplier j, its quarterly revenue line y_t (the segment the chain uses when its history is long enough, else
total revenue) is modelled as

    y_t = a + c·(t − t̄) + Σ_ℓ b_ℓ · X_{t−ℓ} + e_t,        ℓ ∈ {−1, 0, 1, 2}

where X is the chain buyers' combined capital expenditures by calendar quarter. ℓ = −1 lets the supplier book revenue a
quarter before the buyers pay (chips shipped to server makers before the servers are installed and paid for); ℓ = 1, 2
after (construction billed as the work is done, power gear delivered later). Σ b is the supplier's revenue per dollar
of the buyers' capex; a + c·t is the rest of its business (other buyers), with a trend.

Bayesian linear regression with a Gaussian prior (the "θ0" of the method): b is centred on the balanced chain — the
supplier's twelve-month revenue from these buyers in the chain's matrix ÷ their twelve-month capex — spread over the
lags with a profile by layer; a and c are close to free. The posterior is conjugate (the noise variance by iteration),
so the share comes with an interval, and how far it moved from the prior says how much the filings had to say.

Validation, out of sample: a rolling origin — the model fitted on the quarters up to t0 predicts t0+1, (1) given the
buyers' actual capex (the supply-chain link alone) and (2) with the buyers' capex projected from their own past (the
whole forecast) — against two naive forecasts: the last quarter, and the last quarter grown at its last-year rate.
Interval coverage is counted too.

Forecast: the next four quarters, the buyers' capex from their own guidance where their latest earnings release gave
one, else a damped trend; base, down (−20% from the next quarter) and up (+20%) cases; 80% intervals from the posterior
predictive. Pure Python (the pipeline does not need numpy).
"""
import datetime as dt
import math
import re

LAGS = (-1, 0, 1, 2)
PROFILES = {                                   # prior spread of a supplier's share over the lags, by layer
    "lead": (0.35, 0.4, 0.18, 0.07),           # chips, servers, networking, optics, memory: billed before or with capex
    "even": (0.15, 0.4, 0.3, 0.15),
    "late": (0.05, 0.35, 0.35, 0.25),          # power, cooling, construction: billed as work is done or later
}
MIN_Q = 10                                     # quarters of history a supplier needs for its own fit
DAMP = 0.7                                     # a trend fades: 70% of it carries into each next quarter
SCEN = {"base": 1.0, "down": 0.8, "up": 1.2}
Z80 = 1.2816


def cq(end):
    """Calendar quarter of a fiscal quarter: the one holding most of its days (end − 45 days) -> int year*4 + q − 1."""
    d = dt.date.fromisoformat(end) - dt.timedelta(days=45)
    return d.year * 4 + (d.month - 1) // 3


def qlabel(k):
    return f"{k // 4}Q{k % 4 + 1}"


def cq_from_label(label):
    y, q = str(label).split("Q")
    return int(y) * 4 + int(q) - 1


def by_quarter(series):
    """{end: v} -> {calendar quarter: v} (a later end in the same quarter wins)."""
    out = {}
    for e in sorted(series):
        out[cq(e)] = series[e]
    return out


# ------------------------------------------------------------------ small linear algebra (p <= 7)

def inv(M):
    n = len(M)
    A = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-15:
            raise ZeroDivisionError("singular")
        A[c], A[piv] = A[piv], A[c]
        p = A[c][c]
        A[c] = [x / p for x in A[c]]
        for r in range(n):
            if r != c and A[r][c]:
                f = A[r][c]
                A[r] = [x - f * y for x, y in zip(A[r], A[c])]
    return [row[n:] for row in A]


def matvec(M, v):
    return [sum(a * b for a, b in zip(row, v)) for row in M]


def quad(v, M, w=None):
    w = w if w is not None else v
    return sum(v[i] * sum(M[i][j] * w[j] for j in range(len(w))) for i in range(len(v)))


def fit(rows, y, m0, sd0, iters=5):
    """Conjugate Bayesian linear regression: prior N(m0, diag(sd0²)), noise variance by iteration.
    Returns (posterior mean, posterior covariance, noise variance)."""
    p = len(m0)
    L0 = [1.0 / max(s, 1e-9) ** 2 for s in sd0]
    ybar = sum(y) / len(y)
    s2 = max(sum((v - ybar) ** 2 for v in y) / max(len(y) - 1, 1) * 0.1, (0.01 * abs(ybar)) ** 2, 1e-12)
    XtX = [[sum(r[i] * r[j] for r in rows) for j in range(p)] for i in range(p)]
    Xty = [sum(r[i] * v for r, v in zip(rows, y)) for i in range(p)]
    mu = cov = None
    for _ in range(iters):
        A = [[XtX[i][j] / s2 + (L0[i] if i == j else 0.0) for j in range(p)] for i in range(p)]
        cov = inv(A)
        mu = matvec(cov, [Xty[i] / s2 + L0[i] * m0[i] for i in range(p)])
        res = [v - sum(a * b for a, b in zip(r, mu)) for r, v in zip(rows, y)]
        s2 = max(sum(e * e for e in res) / max(len(y) - 2, 1), (0.01 * abs(ybar)) ** 2, 1e-12)
    return mu, cov, s2


# ------------------------------------------------------------------ the buyers' capex: history and path

def damped(last, g, h):
    return last * math.exp(g * sum(DAMP ** k for k in range(1, h + 1)))


def growth(series_q, upto=None):
    """Quarterly growth rate of a capex series: from its last twelve months against the twelve before (steadier than
    quarter to quarter), else the median quarter-to-quarter change; held within −12% and +15% a quarter."""
    ks = sorted(k for k in series_q if upto is None or k <= upto)
    if len(ks) >= 8 and ks[-1] - ks[-8] == 7:
        a = sum(series_q[k] for k in ks[-4:])
        b = sum(series_q[k] for k in ks[-8:-4])
        g = math.log(a / b) / 4 if a > 0 and b > 0 else 0.0
    else:
        ks = ks[-5:]
        rates = sorted(math.log(series_q[b] / series_q[a]) for a, b in zip(ks, ks[1:])
                       if series_q[a] > 0 and series_q[b] > 0 and b == a + 1)
        g = rates[len(rates) // 2] if rates else 0.0
    return max(min(g, 0.15), -0.12)


def buyer_path(hist_q, guide, fye, last_k, horizon_k):
    """A buyer's quarterly capex from its last actual quarter to horizon_k: its guidance for a fiscal year (spread over
    that year's remaining quarters after what it already spent), else a damped trend. -> ({k: v}, guided year or None)."""
    out, guided = {}, None
    g = growth(hist_q)
    last = hist_q.get(last_k)
    if last is None:
        return out, None
    fy_q = {}
    if guide and guide.get("year") and guide.get("mid"):
        try:
            Y, m = int(guide["year"]), int((fye or "1231")[:2])
            end_k = cq(dt.date(Y, m, 28).isoformat()) if m != 12 else cq(f"{Y}-12-31")
            ks = list(range(end_k - 3, end_k + 1))
            spent = sum(hist_q.get(k, 0) for k in ks if k <= last_k)
            left = [k for k in ks if k > last_k]
            if left and guide["mid"] > spent:
                per = (guide["mid"] - spent) / len(left)
                for k in left:
                    fy_q[k] = per
                guided = Y
        except (ValueError, TypeError):
            pass
    prev, h = last, 0
    for k in range(last_k + 1, horizon_k + 1):
        if k in fy_q:
            out[k] = fy_q[k]
            prev, h = fy_q[k], 0
        else:
            h += 1
            out[k] = damped(prev, g, h) if not fy_q or k > max(fy_q) else damped(last, g, h)
    return out, guided


# ------------------------------------------------------------------ one supplier

def design(X, k, t0):
    return [1.0, (k - t0) / 4.0] + [X.get(k - l) for l in LAGS]


def supplier_model(y_q, X, beta0, profile, backtest=True):
    """Fit, backtest and return the parameters for one supplier (all money in $B)."""
    ks = sorted(k for k in y_q if all(X.get(k - l) is not None for l in LAGS))
    if len(ks) < MIN_Q:
        return None
    t0 = sum(ks) / len(ks)
    h = PROFILES.get(profile, PROFILES["even"])

    def prior(sample):
        ys = [y_q[k] for k in sample]
        xs = [sum(X[k - l] * w for l, w in zip(LAGS, h)) for k in sample]
        ybar, xbar = sum(ys) / len(ys), sum(xs) / len(xs)
        sdy = (sum((v - ybar) ** 2 for v in ys) / max(len(ys) - 1, 1)) ** 0.5
        m0 = [ybar - beta0 * xbar, 0.0] + [beta0 * w for w in h]
        sd0 = [3 * sdy + 0.5 * abs(ybar) + 1e-6, sdy + 1e-6] + [0.75 * beta0 * max(w, 0.15) + 1e-5 for w in h]
        return m0, sd0

    def fit_on(sample):
        m0, sd0 = prior(sample)
        rows = [design(X, k, t0) for k in sample]
        return fit(rows, [y_q[k] for k in sample], m0, sd0) + (m0, sd0)

    mu, cov, s2, m0, sd0 = fit_on(ks)
    rows = [design(X, k, t0) for k in ks]
    yhat = [sum(a * b for a, b in zip(r, mu)) for r in rows]
    ys = [y_q[k] for k in ks]
    ybar = sum(ys) / len(ys)
    tss = sum((v - ybar) ** 2 for v in ys) or 1e-12
    r2 = 1 - sum((a - b) ** 2 for a, b in zip(ys, yhat)) / tss
    nb = len(LAGS)
    share = sum(mu[2:])
    one = [0, 0] + [1] * nb
    var_s = quad(one, cov)
    var_s0 = sum(s * s for s in sd0[2:])
    lag = sum(l * b for l, b in zip(LAGS, mu[2:])) / share if share > 0 else None
    out = {"n": len(ks), "first": qlabel(ks[0]), "last": qlabel(ks[-1]), "t0": t0, "mu": mu, "cov": cov, "s2": s2,
           "share": share, "share_sd": var_s ** 0.5, "share0": beta0, "share0_sd": var_s0 ** 0.5,
           "dataw": max(0.0, min(1.0, 1 - var_s / var_s0)) if var_s0 > 0 else 0.0, "lag": lag, "r2": r2,
           "fit": [[qlabel(k), y_q[k], f] for k, f in zip(ks, yhat)]}
    if backtest:
        out["bt"] = _backtest(ks, y_q, X, fit_on, t0)
    return out


def _backtest(ks, y_q, X, fit_on, t0):
    """Rolling origin, one quarter ahead, out of sample."""
    err, err_u, err_rw, err_gr, cover = [], [], [], [], []
    origins = [i for i in range(MIN_Q - 2, len(ks) - 1)][-6:]
    for i in origins:
        train, k1 = ks[:i + 1], ks[i + 1]
        if k1 != ks[i] + 1:
            continue
        try:
            mu, cov, s2, _, _ = fit_on(train)
        except ZeroDivisionError:
            continue
        actual = y_q[k1]
        if not actual:
            continue
        x = design(X, k1, t0)
        pred = sum(a * b for a, b in zip(x, mu))
        sd = (quad(x, cov) + s2) ** 0.5
        err.append(abs(pred / actual - 1))
        cover.append(abs(actual - pred) <= Z80 * sd)
        # the whole forecast: the buyers' capex after t0 projected from their own trend up to t0
        Xu = {k: v for k, v in X.items() if k <= ks[i]}
        g = growth(Xu)
        for kk in range(ks[i] + 1, k1 + 2):
            Xu[kk] = damped(X[ks[i]], g, kk - ks[i])
        xu = design(Xu, k1, t0)
        err_u.append(abs(sum(a * b for a, b in zip(xu, mu)) / actual - 1))
        last = y_q[ks[i]]
        err_rw.append(abs(last / actual - 1))
        yr = y_q.get(ks[i] - 4)
        gr = (last / yr) ** 0.25 if yr and yr > 0 and last > 0 else 1.0
        err_gr.append(abs(last * gr / actual - 1))
    if not err:
        return None
    m = lambda a: round(sum(a) / len(a), 4)
    return {"n": len(err), "mape": m(err), "mape_uncond": m(err_u), "mape_rw": m(err_rw), "mape_growth": m(err_gr),
            "cover80": round(sum(cover) / len(cover), 3)}


def forecast(model, y_q, Xs, ks_future):
    """[[quarter, mean, lo80, hi80]] for each future quarter, given the capex path Xs (actual + projected)."""
    mu, cov, s2, t0 = model["mu"], model["cov"], model["s2"], model["t0"]
    out = []
    for k in ks_future:
        x = design(Xs, k, t0)
        if any(v is None for v in x):
            break
        m = sum(a * b for a, b in zip(x, mu))
        sd = (quad(x, cov) + s2) ** 0.5
        out.append([qlabel(k), m, m - Z80 * sd, m + Z80 * sd])
    return out


def chain_part(model_or_prior, Xs, ks, prior_share=None, profile="even"):
    """Revenue from these buyers in quarters ks: Σ_k Σ_ℓ b_ℓ X_{k−ℓ} (no intercept: the rest of the business)."""
    if model_or_prior:
        b = model_or_prior["mu"][2:]
    else:
        b = [prior_share * w for w in PROFILES.get(profile, PROFILES["even"])]
    tot = 0.0
    for k in ks:
        xs = [Xs.get(k - l) for l in LAGS]
        if any(v is None for v in xs):
            return None
        tot += sum(bb * x for bb, x in zip(b, xs))
    return tot


# ------------------------------------------------------------------ the chain

def profile_of(layer_id, ch):
    L = next((x for x in ch.get("layers", []) if x["id"] == layer_id), {})
    if L.get("lag") in PROFILES:
        return L["lag"]
    if re.search(r"power|build|construct|contract|cool", layer_id + " " + (L.get("name") or ""), re.I):
        return "late"
    if re.search(r"accel|chip|server|network|optic|memory|storage", layer_id + " " + (L.get("name") or ""), re.I):
        return "lead"
    return "even"


def run(ch, res, cos):
    """The model for one spend chain. res: build_spend's result (with its private _buyers, _sups)."""
    B = res.get("_buyers") or []
    sups = res.get("_sups") or []
    if not B or not sups:
        return None
    # the buyers' quarterly capex, by calendar quarter ($B)
    hist = {}
    weights = {b["t"]: b["capex"] for b in B}
    wt = sum(weights.values()) or 1
    for b in B:
        co = cos.get(b["t"])
        h = by_quarter(co.history("capex")) if co else {}
        hist[b["t"]] = {k: v / 1e9 for k, v in h.items() if v is not None and v >= 0}
    allk = sorted({k for h in hist.values() for k in h})
    X = {}
    for k in allk:
        cov_k = sum(weights[t] for t, h in hist.items() if k in h) / wt
        if cov_k >= 0.8:
            X[k] = sum(h[k] for h in hist.values() if k in h)
    if len(X) < MIN_Q + 3:
        return {"error": f"the buyers' capex history is too short ({len(X)} quarters)"}
    last_x = max(X)
    # paths: each buyer from its own last quarter; the chain's X beyond last_x
    horizon = last_x + 7
    paths, guided = {}, {}
    for b in B:
        co = cos.get(b["t"])
        h = hist[b["t"]]
        if not h:
            continue
        g = None
        for r in ((b.get("guide") or {}).get("rows") or []):
            if r.get("lo") and r.get("year"):
                g = {"year": r["year"], "mid": (r["lo"] + r["hi"]) / 2 / 1e9, "text": r.get("text")}
                break
        fye = ((co.rec.get("profile") or {}).get("fye") if co else None) or "1231"
        p, gy = buyer_path(h, g, fye, max(h), horizon)
        paths[b["t"]] = p
        if gy:
            guided[b["t"]] = {"year": gy, "mid": g["mid"]}
    Xs = {}
    for scen, f in SCEN.items():
        Z = dict(X)
        for k in range(last_x + 1, horizon + 1):
            tot = 0.0
            for t, h in hist.items():
                v = h.get(k)
                tot += v if v is not None else paths.get(t, {}).get(k, 0.0) * f
            Z[k] = tot
        # quarters some buyers already reported but not all: the reported part is actual, the rest projected
        Xs[scen] = Z
    out_s = []
    sum_last4 = {}
    for s in sups:
        co = s["co"]
        m = s["m"]
        pattern = m.get("seg") or "|".join(p["seg"] for p in m.get("parts") or [] if p.get("seg"))
        y_kind, y = "total revenue", {}
        if pattern:
            yy = by_quarter(co.segment_history(pattern))
            if len(yy) >= MIN_Q:
                y, y_kind = yy, "segment: " + "; ".join(p["label"] for p in s["parts"])
        if not y:
            y = by_quarter(co.history("revenue"))
        y = {k: v / 1e9 for k, v in y.items() if v is not None}
        x_ttm = sum(X.get(k, 0) for k in range(last_x - 3, last_x + 1))
        beta0 = (s["R_rev"] / 1e9) / x_ttm if x_ttm > 0 else 0.0
        prof = profile_of(s["layer"], ch)
        mdl = None
        try:
            mdl = supplier_model(y, X, beta0, prof)          # fitted and backtested on reported capex only
        except ZeroDivisionError:
            mdl = None
        last_y = max(y) if y else last_x
        fut = list(range(last_y + 1, last_y + 5))
        last4 = list(range(last_y - 3, last_y + 1))
        row = {"id": s["id"], "t": s["t"], "layer": s["layer"], "y_kind": y_kind, "profile": prof,
               "share0": round(beta0, 5), "basis": "gp" if s["f"] != 1.0 else "rev", "margin": s["f"] if s["f"] != 1.0 else None}
        base_now = chain_part(mdl, Xs["base"], last4, beta0, prof)
        if mdl:
            row.update({"n": mdl["n"], "first": mdl["first"], "last": mdl["last"], "share": round(mdl["share"], 5),
                        "share_lo": round(mdl["share"] - Z80 * mdl["share_sd"], 5), "share_hi": round(mdl["share"] + Z80 * mdl["share_sd"], 5),
                        "share0_lo": round(beta0 - Z80 * mdl["share0_sd"], 5), "share0_hi": round(beta0 + Z80 * mdl["share0_sd"], 5),
                        "dataw": round(mdl["dataw"], 3), "lag": round(mdl["lag"], 2) if mdl["lag"] is not None else None,
                        "b": [round(v, 5) for v in mdl["mu"][2:]], "r2": round(mdl["r2"], 3), "bt": mdl.get("bt"),
                        "fit": [[q, round(a, 4), round(f, 4)] for q, a, f in mdl["fit"]],
                        "fc": {sc: [[q, round(a, 4), round(lo, 4), round(hi, 4)] for q, a, lo, hi in forecast(mdl, y, Xs[sc], fut)] for sc in SCEN}})
        else:
            row.update({"n": len(y), "note": "history too short for its own fit: the prior share only"})
        row["hist"] = [[qlabel(k), round(v, 4)] for k, v in sorted(y.items())[-24:]]
        row["chain_now"] = round(base_now, 4) if base_now is not None else None
        row["chain_next"] = {sc: (round(v, 4) if v is not None else None) for sc in SCEN
                             for v in [chain_part(mdl, Xs[sc], fut, beta0, prof)]}
        out_s.append(row)
    # Sankey factors: each buyer's next four quarters ÷ its last four; each supplier's chain revenue next ÷ now
    factors = {}
    for sc, f in SCEN.items():
        fb = {}
        for t, h in hist.items():
            if not h:
                continue
            lk = max(h)
            now = sum(h.get(k, 0) for k in range(lk - 3, lk + 1))
            nxt = sum(paths.get(t, {}).get(k, 0) * f for k in range(lk + 1, lk + 5))
            if now > 0 and nxt > 0:
                fb[t] = round(nxt / now, 4)
        fs = {r["id"]: round(r["chain_next"][sc] / r["chain_now"], 4) for r in out_s
              if r.get("chain_now") and r["chain_next"].get(sc) is not None and r["chain_now"] > 0}
        factors[sc] = {"b": fb, "s": fs}
    bts = [r["bt"] for r in out_s if r.get("bt")]
    summ = None
    if bts:
        avg = lambda k: round(sum(b[k] for b in bts) / len(bts), 4)
        summ = {"suppliers": len(bts), "mape": avg("mape"), "mape_uncond": avg("mape_uncond"), "mape_rw": avg("mape_rw"),
                "mape_growth": avg("mape_growth"), "cover80": avg("cover80"),
                "beats_rw": sum(1 for b in bts if b["mape_uncond"] < b["mape_rw"]),
                "beats_growth": sum(1 for b in bts if b["mape_uncond"] < b["mape_growth"])}
    return {"x": [[qlabel(k), round(v, 4)] for k, v in sorted(X.items())[-28:]],
            "x_path": {sc: [[qlabel(k), round(Xs[sc][k], 4)] for k in range(last_x + 1, horizon + 1)] for sc in SCEN},
            "last_x": qlabel(last_x), "guided": guided, "lags": list(LAGS), "profiles": PROFILES,
            "buyer_paths": {t: [[qlabel(k), round(v, 4)] for k, v in sorted(p.items())] for t, p in paths.items()},
            "suppliers": out_s, "factors": factors, "backtest": summ,
            "scenarios": {k: v - 1 for k, v in SCEN.items()}}
