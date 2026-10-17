"""Experiments behind chaos_forecast.py (run by hand; not part of the site build).

  grid     embedding dimension m, number of analogues k and which coordinates span the phase space
  smap     Sugihara's S-map test: locally weighted linear maps with nonlinearity theta = 0 (one global linear map)
           ... 8 (very local). Forecast skill that RISES with theta = state-dependent (nonlinear) dynamics, the
           signature chaos theory looks for; skill that is best at theta = 0 = linear dynamics plus noise.
  horizon  simplex skill against forecast horizon (1..H steps): deterministic chaos gives high short-range skill that
           decays; linear mean reversion gives skill that decays smoothly; pure noise gives ~0 at every horizon.
  rrg      weekly RRG of the site's companies: next (RS-Ratio, RS-Momentum) step and the price mapped back from it.

  python chaos_experiments.py --public hist/public --out experiments/
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

import chaos_forecast as C


def grid(P, emb_sets, first_test, forecast_vars, ms=(1, 2, 3), ks=(20, 60, 150)):
    slow = [v for v in forecast_vars if v not in ('rel', 'ret')]
    rows = []
    for name, emb in emb_sets.items():
        emb = [v for v in emb if v in forecast_vars]
        for m in ms:
            for k in ks:
                t0 = time.time()
                R = C.run_panel(P, emb, forecast_vars, first_test, m=m, k=k, surrogate=False, verbose=False)
                for r in R['recs']:
                    r.setdefault('sur', np.full_like(r['fp']['delta'], np.nan))
                ev = C.evaluate(R)
                s = ev['summary']['analog_cal']; raw = ev['summary']['analog']
                land = ev['landing']
                rows.append({'embedding': name, 'm': m, 'k': k, 'dims': len(emb) * m,
                             'arrow_hit_cal': s['arrow_hit'], 'arrow_hit_raw': raw['arrow_hit'],
                             'slow_landing_skill_cal': float(np.nanmean([land['analog_cal'][v]['vs_best_naive'] for v in slow])),
                             'slow_landing_skill_raw': float(np.nanmean([land['analog'][v]['vs_best_naive'] for v in slow])),
                             'slow_landing_skill_linear': float(np.nanmean([land['linear'][v]['vs_best_naive'] for v in slow])),
                             'rel_ic_raw': raw['rel_landing_ic_ci'][0], 'rel_ic_raw_lo': raw['rel_landing_ic_ci'][1], 'rel_ic_raw_hi': raw['rel_landing_ic_ci'][2],
                             'rel_q5q1_raw': raw['rel_quintile_spread_ci'][0], 'seconds': round(time.time() - t0, 1)})
                print(' grid', rows[-1], flush=True)
    return rows


def _phase(P, emb_vars, forecast_vars, first_test, m=2):
    planet, _ = P.layers()
    fv = [P.vi[v] for v in forecast_vars]
    return C.Layer(planet[..., fv], P.lag[fv], [v for v in emb_vars if v in forecast_vars], forecast_vars, first_test, m=m)


def smap(P, emb_vars, forecast_vars, first_test, thetas=(0, .25, .5, 1, 2, 4, 8), lib_cap=3000, q_cap=100, seed=1):
    """For each test origin t: library = complete-case states whose next step was public by t (random subsample of
    lib_cap), queries = up to q_cap companies at t. Target: next landing of each coordinate (planet layer, in spread
    units). Locally weighted linear map with weights exp(-theta * d / mean d), one solve for all coordinates.
    Skill: correlation and MSE against the better naive landing (stay put / back to the sun)."""
    L = _phase(P, emb_vars, forecast_vars, first_test)
    rng = np.random.default_rng(seed)
    V = L.V
    pred = {th: [] for th in thetas}
    truth, known = [], []
    for t in range(first_test, L.T - 1):
        e, s, Zl, Dl = L.library(t)
        full = np.isfinite(Dl).all(1)
        e, s, Zl, Dl = e[full], s[full], Zl[full], Dl[full]
        if len(e) < 200:
            continue
        if len(e) > lib_cap:
            pick = rng.choice(len(e), lib_cap, replace=False); e, s, Zl, Dl = e[pick], s[pick], Zl[pick], Dl[pick]
        Yl = (L.K[e, s] + Dl) / L.scale
        q = np.nonzero(np.isfinite(L.Z[:, t]).all(-1) & np.isfinite(L.D[:, t]).all(-1))[0]
        if len(q) > q_cap:
            q = rng.choice(q, q_cap, replace=False)
        if not len(q):
            continue
        Zq = L.Z[q, t]
        truth.append((L.K[q, t] + L.D[q, t]) / L.scale); known.append(L.K[q, t] / L.scale)
        A = np.c_[np.ones(len(Zl)), Zl]; Aq = np.c_[np.ones(len(Zq)), Zq]
        d = np.linalg.norm(Zl[None] - Zq[:, None], axis=-1)
        dbar = d.mean(axis=1, keepdims=True)
        reg = 1e-3 * np.eye(A.shape[1]); reg[0, 0] = 0
        for th in thetas:
            W = np.exp(-th * d / dbar)
            out = np.empty((len(q), V))
            for i in range(len(q)):
                Aw = A * W[i][:, None]
                b = np.linalg.solve(Aw.T @ A + reg * W[i].sum(), Aw.T @ Yl)
                out[i] = Aq[i] @ b
            pred[th].append(out)
    Y = np.vstack(truth); K0 = np.vstack(known)
    rows = []
    for j, v in enumerate(forecast_vars):
        base = min(np.mean((Y[:, j] - K0[:, j]) ** 2), np.mean(Y[:, j] ** 2))
        row = {'var': v, 'n': int(len(Y))}
        for th in thetas:
            pj = np.vstack(pred[th])[:, j]
            row[f'rho_{th}'] = float(np.corrcoef(pj, Y[:, j])[0, 1])
            row[f'skill_{th}'] = float(1 - np.mean((pj - Y[:, j]) ** 2) / base)
        best = max(thetas, key=lambda th: row[f'skill_{th}'])
        row['best_theta'] = best
        row['gain_best_vs_linear'] = row[f'skill_{best}'] - row['skill_0']
        rows.append(row)
        print(' smap', {k: (round(x, 3) if isinstance(x, float) else x) for k, x in row.items()}, flush=True)
    return rows


def horizon(P, emb_vars, forecast_vars, first_test, H=4, k=60, lib_cap=8000, seed=2):
    """Simplex (analogue) skill of the landing h steps ahead, h = 1..H, vs the persistence of the coordinate."""
    L = _phase(P, emb_vars, forecast_vars, first_test)
    rng = np.random.default_rng(seed)
    from sklearn.neighbors import KDTree
    rows = []
    for h in range(1, H + 1):
        fut = np.full_like(L.X, np.nan); fut[:, :-h] = L.X[:, h:]
        tr, pr, kn = [], [], []
        for t in range(first_test, L.T - h):
            okZ = np.isfinite(L.Z[:, :t - h + 1]).all(-1)      # library outcome (s+h) public by t
            e, s = np.nonzero(okZ)
            if len(e) < 300:
                continue
            if len(e) > lib_cap:
                pick = rng.choice(len(e), lib_cap, replace=False); e, s = e[pick], s[pick]
            late = (s[:, None] + h + L.lag[None, :]) > t
            Yl = fut[e, s] / L.scale; Yl[late] = np.nan
            q = np.nonzero(np.isfinite(L.Z[:, t]).all(-1))[0]
            tree = KDTree(L.Z[e, s]); dist, idx = tree.query(L.Z[q, t], k=k)
            w = np.exp(-(dist / np.maximum(np.median(dist, 1, keepdims=True), 1e-9)) ** 2)
            Yn = Yl[idx]; fin = np.isfinite(Yn)
            mu = (w[..., None] * np.nan_to_num(Yn)).sum(1) / np.maximum((w[..., None] * fin).sum(1), 1e-9)
            pr.append(mu); tr.append(fut[q, t] / L.scale); kn.append(L.K[q, t] / L.scale)
        Pp, Y, K0 = np.vstack(pr), np.vstack(tr), np.vstack(kn)
        for j, v in enumerate(forecast_vars):
            ok = np.isfinite(Pp[:, j]) & np.isfinite(Y[:, j]) & np.isfinite(K0[:, j])
            rows.append({'h': h, 'var': v, 'rho_analog': float(np.corrcoef(Pp[ok, j], Y[ok, j])[0, 1]),
                         'rho_persist': float(np.corrcoef(K0[ok, j], Y[ok, j])[0, 1]), 'n': int(ok.sum())})
        print(' horizon', h, {r['var']: round(r['rho_analog'], 3) for r in rows if r['h'] == h}, flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--out', default='chaos-experiments')
    ap.add_argument('--only', default='grid,smap,horizon,rrg')
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pub = Path(a.public)
    Pq = C.load_quarterly(pub / 'rotation-long.json')
    Pm = C.load_monthly(pub / 'rotation-long-monthly.json', Pq)
    ftq = next(i for i, c in enumerate(Pq.cals) if C.cal_end(c).year >= 2015)
    ftm = next(i for i, c in enumerate(Pm.cals) if C.cal_end(c).year >= 2013)
    fq = C.FORECAST_Q; fm = [v for v in C.FORECAST_M if v in Pm.vi]
    only = set(a.only.split(','))
    res = {}
    import pandas as pd
    if 'grid' in only:
        print('== grid (quarterly)')
        g = grid(Pq, {'price': ['rel', 'mom121', 'vola', 'hi52'], 'price+fund': C.EMBED_Q,
                      'price+fund+volume': C.EMBED_Q + ['volz', 'om']}, ftq, fq)
        print('== grid (monthly)')
        g += [dict(r, freq='m') for r in grid(Pm, {'price': C.EMBED_M, 'price+rs': C.EMBED_M + ['rs', 'mom121']}, ftm, fm, ks=(30, 100, 300))]
        pd.DataFrame(g).to_csv(out / 'grid.csv', index=False); res['grid'] = g
    if 'smap' in only:
        print('== S-map (quarterly)'); sq = smap(Pq, C.EMBED_Q, fq, ftq)
        print('== S-map (monthly)'); sm = smap(Pm, C.EMBED_M, fm, ftm, q_cap=80)
        pd.DataFrame([dict(r, freq='q') for r in sq] + [dict(r, freq='m') for r in sm]).to_csv(out / 'smap.csv', index=False)
        res['smap'] = {'q': sq, 'm': sm}
    if 'horizon' in only:
        print('== horizon'); hq = horizon(Pq, C.EMBED_Q, fq, ftq, H=4); hm = horizon(Pm, C.EMBED_M, fm, ftm, H=6, k=100)
        pd.DataFrame([dict(r, freq='q') for r in hq] + [dict(r, freq='m') for r in hm]).to_csv(out / 'horizon.csv', index=False)
        res['horizon'] = {'q': hq, 'm': hm}
    if 'rrg' in only:
        print('== RRG weekly')
        closes = C.weekly_closes(pub / 't', Pq.tickers + ['SPY'])
        rr, inv = C.rrg_experiment(closes, closes['SPY'], Pq.tickers)
        rr.to_csv(out / 'rrg_steps.csv', index=False); inv.to_csv(out / 'rrg_price_inversion.csv', index=False)
        res['rrg'] = C.rrg_summary(rr, inv)
        print(json.dumps(C.jsonable(res['rrg']), indent=1))
    (out / 'experiments.json').write_text(json.dumps(C.jsonable(res), indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
