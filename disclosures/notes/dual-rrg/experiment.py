"""Experiment 1 of the research specification v5 (design: DESIGN.md, fixed before the run).

  python notes/dual-rrg/experiment.py --public <rotation-history>/public --index <site>/data/index.json --out notes/dual-rrg

Writes results.json; README.md is written by hand from it.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'app'))
import chaos_forecast as CF          # noqa: E402
import rotation_history as RH        # noqa: E402

H = 4                                 # weeks ahead
STEP = 4                              # weeks between origins (non-overlapping windows)
TEST_FROM = '2012-01-06'
TRAIN_FROM = '2006-01-06'
SEED = 20261023


def load(public, index):
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    g0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - g0).astype(int) // 7) + 1
    weeks = [str(g0 + 7 * i) for i in range(W)]
    bench = np.full(W, np.nan)
    o = int((np.datetime64(D['bench']['start']) - g0).astype(int) // 7)
    b = np.array([np.nan if x is None else x for x in D['bench']['c']], float)
    bench[o:o + len(b)] = b[:W - o]
    ix = json.loads(Path(index).read_text(encoding='utf-8'))
    best = {}
    for r in ix.get('companies', []):
        t = (r.get('ticker') or '').strip()
        if not t or not r.get('sic'):
            continue
        try:
            t = RH.symbol(t)
        except ValueError:
            continue
        if t not in best or (r.get('filed') or '') > (best[t].get('filed') or ''):
            best[t] = r
    companies, series, C, V = [], {}, {}, {}
    for t, r in best.items():
        p = Path(public) / 't' / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        f = int((np.datetime64(d['start']) - g0).astype(int) // 7)
        if f < 0 or f >= W:
            continue
        c = d['c'][:W - f]
        series[t] = (f, c)
        a = np.full(W, np.nan); a[f:f + len(c)] = [np.nan if x is None else x for x in c]
        v = np.full(W, np.nan); vv = (d.get('v') or [None] * len(c))[:W - f]
        v[f:f + len(vv)] = [np.nan if x is None else 1000.0 * x for x in vv]
        C[t], V[t] = a, v
        companies.append({'t': t, 's': r.get('sector') or 'other', 'sic': str(r.get('sic') or ''), 'ind': r.get('industry') or '',
                          'rev': r.get('revenue') or 0})
    return weeks, bench, companies, series, C, V


def full(arr, W):
    return np.array([np.nan if x is None else x for x in arr], float)


def panel(weeks, bench, companies, series, C, V):
    W = len(weeks)
    bm = RH.industry_benchmarks(companies, series, weeks, rev_hist={})        # equal weights: nothing later leaks in
    tick = [c['t'] for c in companies if c['t'] in bm]
    grp = {t: bm[t]['level'] + ':' + bm[t]['code'] for t in tick}
    feats = {}
    for t in tick:
        c, bx, bi = C[t], full(bm[t]['ex'], W), full(bm[t]['all'], W)
        with np.errstate(divide='ignore', invalid='ignore'):
            cm = CF.rrg_series(np.where(bench > 0, 100 * c / bench, np.nan))
            ci = CF.rrg_series(np.where(bx > 0, 100 * c / bx, np.nan))
            im = CF.rrg_series(np.where(bench > 0, 100 * bi / bench, np.nan))
            lc, lx, lb = np.log(c), np.log(bx), np.log(bench)
        feats[t] = {'cm': cm, 'ci': ci, 'im': im, 'lc': lc, 'lx': lx, 'lb': lb, 'v': V[t]}
    origins = [i for i in range(156, W - H) if weeks[i] >= TRAIN_FROM and (i - weeks.index(TRAIN_FROM) if TRAIN_FROM in weeks else i) % STEP == 0]
    rows = []
    for i in origins:
        for t in tick:
            F = feats[t]
            lc, lx, lb = F['lc'], F['lx'], F['lb']
            if not (np.isfinite(lc[i]) and np.exp(lc[i]) >= 3):
                continue
            dv = np.exp(lc[i - 12:i + 1]) * F['v'][i - 12:i + 1]
            if np.sum(np.isfinite(dv)) < 10 or np.nanmean(dv) < 10e6:
                continue
            if np.sum(np.isfinite(lc[i - 155:i + 1])) < 150:
                continue
            x = [F['cm']['x'][i], F['cm']['y'][i], F['ci']['x'][i], F['ci']['y'][i], F['im']['x'][i], F['im']['y'][i],
                 (lc[i] - lc[i - 13]) - (lx[i] - lx[i - 13]), (lc[i] - lc[i - 1]) - (lx[i] - lx[i - 1])]
            y = (lc[i + H] - lc[i]) - (lx[i + H] - lx[i])
            ym = (lc[i + H] - lc[i]) - (lb[i + H] - lb[i])
            if not all(np.isfinite(x)) or not np.isfinite(y) or not np.isfinite(ym):
                continue
            rows.append((i, t, grp[t], *x, y, ym))
    return rows, bm


COLS = ['cm_x', 'cm_y', 'ci_x', 'ci_y', 'im_x', 'im_y', 'mom13', 'rev1']
MODELS = {'MOM': ['mom13', 'rev1'], 'B2m': ['cm_x', 'cm_y'], 'B2': ['ci_x', 'ci_y'], 'B3': ['ci_x', 'ci_y', 'im_x', 'im_y'],
          'B3+': ['ci_x', 'ci_y', 'im_x', 'im_y', 'mom13', 'rev1'], 'NC': ['ci_x', 'ci_y', 'nc_x', 'nc_y']}


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1]) if len(a) > 2 else np.nan


def run(rows, weeks):
    rng = np.random.default_rng(SEED)
    by = {}
    for r in rows:
        by.setdefault(r[0], []).append(r)
    origins = sorted(by)
    data = {}
    for i in origins:
        g = by[i]
        X = np.array([r[3:3 + len(COLS)] for r in g], float)
        # negative control: the industry coordinates shuffled across industries within the origin
        inds = sorted({r[2] for r in g})
        perm = dict(zip(inds, rng.permutation(len(inds))))
        im_by = {}
        for r, x in zip(g, X):
            im_by.setdefault(r[2], (x[4], x[5]))
        nc = np.array([im_by[inds[perm[r[2]]]] for r in g])
        data[i] = {'X': np.c_[X, nc], 'y': np.array([r[-2] for r in g]), 'ym': np.array([r[-1] for r in g])}
    names = COLS + ['nc_x', 'nc_y']
    test = [i for i in origins if weeks[i] >= TEST_FROM]
    out = {m: {'ic': [], 'icm': [], 'spread': [], 'origins': []} for m in MODELS}
    for i in test:
        train = [j for j in origins if j + H <= i]
        if len(train) < 52:
            continue
        Xt = np.vstack([data[j]['X'] for j in train]); yt = np.concatenate([data[j]['y'] for j in train])
        ymt = np.concatenate([data[j]['ym'] for j in train])
        Xq, yq, ymq = data[i]['X'], data[i]['y'], data[i]['ym']
        if len(yq) < 30:
            continue
        mu, sd = Xt.mean(0), Xt.std(0) + 1e-12
        lo, hi = np.percentile(yt, [1, 99]); ytw = np.clip(yt, lo, hi)
        lo2, hi2 = np.percentile(ymt, [1, 99]); ymtw = np.clip(ymt, lo2, hi2)
        for m, cols in MODELS.items():
            k = [names.index(c) for c in cols]
            A = np.c_[np.ones(len(Xt)), (Xt[:, k] - mu[k]) / sd[k]]
            beta = np.linalg.lstsq(A.T @ A + 1e-3 * np.eye(A.shape[1]), A.T @ ytw, rcond=None)[0]
            betam = np.linalg.lstsq(A.T @ A + 1e-3 * np.eye(A.shape[1]), A.T @ ymtw, rcond=None)[0]
            Aq = np.c_[np.ones(len(Xq)), (Xq[:, k] - mu[k]) / sd[k]]
            p, pm = Aq @ beta, Aq @ betam
            out[m]['ic'].append(spearman(p, yq)); out[m]['icm'].append(spearman(pm, ymq))
            q = np.argsort(p); n5 = max(1, len(q) // 5)
            out[m]['spread'].append(float(yq[q[-n5:]].mean() - yq[q[:n5]].mean()))
            out[m]['origins'].append(weeks[i])
    return out


def ci(x, reps=2000, seed=SEED):
    x = np.asarray([v for v in x if np.isfinite(v)], float)
    if len(x) < 5:
        return None
    rng = np.random.default_rng(seed)
    bs = rng.choice(x, (reps, len(x)), replace=True).mean(1)
    return [round(float(x.mean()), 4), round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]


def summarise(out):
    s = {}
    for m, r in out.items():
        s[m] = {'origins': len(r['ic']), 'ic_vs_industry': ci(r['ic']), 'ic_vs_spy': ci(r['icm']), 'quintile_spread_4w': ci(r['spread'])}
        for name, lo, hi in (('2012_2018', '2012', '2019'), ('2019_end', '2019', '9999')):
            sel = [v for v, o in zip(r['ic'], r['origins']) if lo <= o[:4] < hi]
            s[m]['ic_' + name] = ci(sel)
    pairs = {}
    for a, b in (('B3', 'B2'), ('B2', 'MOM'), ('B2', 'B2m'), ('B3+', 'MOM'), ('B3', 'NC'), ('B3+', 'B3')):
        d = [x - y for x, y in zip(out[a]['ic'], out[b]['ic'])]
        pairs[f'{a} - {b}'] = ci(d)
    return s, pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', required=True)
    ap.add_argument('--index', required=True)
    ap.add_argument('--out', default=str(HERE))
    a = ap.parse_args()
    weeks, bench, companies, series, C, V = load(a.public, a.index)
    print('companies with closes and SIC:', len(companies), flush=True)
    rows, bm = panel(weeks, bench, companies, series, C, V)
    levels = {}
    for v in bm.values():
        levels[v['level']] = levels.get(v['level'], 0) + 1
    print('rows', len(rows), 'benchmarks by level', levels, flush=True)
    out = run(rows, weeks)
    s, pairs = summarise(out)
    res = {'design': 'DESIGN.md', 'data_through': weeks[-1], 'companies': len(companies), 'with_benchmark': len(bm),
           'benchmark_levels': levels, 'rows': len(rows),
           'eligible_per_origin_median': int(np.median(np.bincount([r[0] for r in rows])[np.bincount([r[0] for r in rows]) > 0])),
           'models': s, 'paired_ic_differences': pairs, 'seed': SEED}
    Path(a.out, 'results.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
