"""Can the gravity + tidal signal survive trading costs? Turnover-reduction experiment (not part of the site build).

Sector-neutral long-short on the weekly signal (M2: damping, the four pendulum links, the planet's velocity and links):
  smoothing   the score averaged over the last K weeks (exponential, span K) — a slower ranking
  buffer      enter a leg in the top / bottom 10%, leave only when the name falls out of the top / bottom X%
  rebalance   trade every R weeks, hold in between
  costs       per side, both legs; turnover measured from the actual weight changes
Rules are chosen on 2012-2018 only; 2019-2026 is reported once for the chosen rule (and for every rule, for honesty).

  python gravity_portfolio.py --public hist/public --out notes/gravity-pendulum
"""
import argparse, itertools, json, math
from pathlib import Path
import numpy as np
import gravity_pendulum as G


def simulate(preds, days, span=1, entry=.9, exit_=.9, every=1, cost_bp=10.0):
    """preds: list of dicts with t, ids, pred, raw (next-week sector-relative log return). Returns weekly net/gross."""
    ema = {}; a = 2 / (span + 1)
    L, S = set(), set(); out = []
    for k, o in enumerate(preds):
        sc = {}
        for i, p in zip(o['ids'], o['pred']):
            ema[i] = p if i not in ema else ema[i] + a * (p - ema[i]); sc[i] = ema[i]
        ids = np.array(list(sc)); v = np.array([sc[i] for i in ids])
        pct = (np.argsort(np.argsort(v)) + .5) / len(v); rank = dict(zip(ids, pct))
        turn = 0.0
        if k % every == 0:
            newL = {i for i in L if rank.get(i, 0) >= exit_} | {i for i in ids if rank[i] >= entry}
            newS = {i for i in S if rank.get(i, 1) <= 1 - exit_} | {i for i in ids if rank[i] <= 1 - entry}
            newS -= newL
            def tw(old, new):
                if not old and not new: return 0.0
                wo = {i: 1 / len(old) for i in old} if old else {}; wn = {i: 1 / len(new) for i in new} if new else {}
                return 0.5 * sum(abs(wn.get(i, 0) - wo.get(i, 0)) for i in set(wo) | set(wn))
            turn = tw(L, newL) + tw(S, newS)              # fraction of each leg traded, summed over the two legs
            L, S = newL, newS
        r = dict(zip(o['ids'], o['raw']))
        lr = [r[i] for i in L if i in r and np.isfinite(r[i])]; sr = [r[i] for i in S if i in r and np.isfinite(r[i])]
        gross = (np.mean(lr) if lr else 0) - (np.mean(sr) if sr else 0)
        cost = 2 * turn * cost_bp / 1e4                    # each traded unit is bought and sold: 2 sides
        out.append({'t': o['t'], 'year': str(days[o['t']])[:4], 'gross': float(gross), 'net': float(gross - cost), 'turn': turn,
                    'nL': len(L), 'nS': len(S)})
    return out


def stats(w, lo=None, hi=None):
    w = [x for x in w if (lo is None or x['year'] >= lo) and (hi is None or x['year'] <= hi)]
    if len(w) < 30: return {}
    g = np.array([x['gross'] for x in w]); n = np.array([x['net'] for x in w]); tr = np.array([x['turn'] for x in w])
    ci = G.block_ci(n, block=13)
    return {'weeks': len(w), 'gross_ann': float(g.mean() * 52), 'net_ann': float(n.mean() * 52), 'net_ann_ci': [c * 52 for c in ci],
            'net_sharpe': float(n.mean() / n.std() * math.sqrt(52)) if n.std() > 0 else None, 'turnover_per_year': float(tr.sum() / len(w) * 52),
            'avg_names_per_leg': float(np.mean([x['nL'] for x in w]))}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--public', default='hist/public'); ap.add_argument('--out', default='notes/gravity-pendulum')
    a = ap.parse_args()
    D = G.load(a.public); B = G.build(D)
    cols = ['v', 'k1', 'k2', 'k3', 'k4', 'planet_v', 'pk1', 'pk2', 'pk3', 'pk4']
    rows = G.panel(B, D, 1)
    t0 = int(np.searchsorted(D['days'], np.datetime64('2012-01-01')))
    preds = G.walk_forward(rows, cols, 1, t0, keep=True)
    print('weekly predictions', len(preds), flush=True)
    grid = list(itertools.product([1, 4, 13, 26], [(.9, .9), (.9, .8), (.9, .7), (.9, .5)], [1, 4, 13]))
    res = []
    for span, (en, ex), every in grid:
        w = simulate(preds, D['days'], span, en, ex, every, 10.0)
        r = {'span': span, 'entry': en, 'exit': ex, 'every': every, 'train': stats(w, '2012', '2018'), 'test': stats(w, '2019', '2026')}
        res.append(r)
        print(span, en, ex, every, 'train net', round(r['train']['net_ann'] * 100, 2), 'test net', round(r['test']['net_ann'] * 100, 2),
              'turn/yr', round(r['test']['turnover_per_year'], 1), flush=True)
    best = max(res, key=lambda r: r['train']['net_sharpe'] or -9)
    # the chosen rule at other cost levels, on the untouched half
    sens = {}
    for c in (5, 10, 20, 30):
        w = simulate(preds, D['days'], best['span'], best['entry'], best['exit'], best['every'], c)
        sens[f'{c}bp'] = {'train': stats(w, '2012', '2018'), 'test': stats(w, '2019', '2026')}
    yearly = {}
    w = simulate(preds, D['days'], best['span'], best['entry'], best['exit'], best['every'], 10)
    for y in sorted({x['year'] for x in w}):
        ys = [x['net'] for x in w if x['year'] == y]; yearly[y] = float(np.sum(ys))
    out = {'grid': res, 'chosen_on_2012_2018': {k: best[k] for k in ('span', 'entry', 'exit', 'every')}, 'chosen': best, 'cost_sensitivity': sens, 'net_by_year_10bp': yearly,
           'baseline_no_reduction': next(r for r in res if r['span'] == 1 and r['exit'] == .9 and r['every'] == 1)}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / 'portfolio.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    print('CHOSEN', out['chosen_on_2012_2018'], json.dumps(best['test']), json.dumps(sens), flush=True)


if __name__ == '__main__':
    main()
