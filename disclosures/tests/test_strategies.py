"""strategies.py: the loader (splits undone for the price filter, the last full week), the engine (costs, cash, borrowing,
drift), a few rules, the statistics (PSR, the luck bar, PBO) and the live ledger (frozen weeks, late freezes)."""
import json
import math
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import strategies as S

warnings.filterwarnings('ignore', category=RuntimeWarning)


def panel(T=400, names=('SPY', 'TLT', 'EFA', 'GLD', 'AAA', 'BBB', 'CCC'), etfs=('SPY', 'TLT', 'EFA', 'GLD'), seed=1):
    rng = np.random.default_rng(seed)
    N = len(names)
    R = np.vstack([rng.normal(0.002, 0.02, T) for _ in names])
    R[:, 0] = np.nan
    C = 100 * np.cumprod(np.nan_to_num(R, nan=0.0) + 1, axis=1)
    dates = np.datetime64('2000-01-07') + np.arange(T) * S.WEEK
    D = {'tickers': list(names), 'sectors': ['etf' if n in etfs else 'tech' for n in names], 'is_etf': np.array([n in etfs for n in names]),
         'dates': dates, 'C': C, 'PX': C.copy(), 'DV': np.full((N, T), 1e9), 'R': R, 'cost': np.full((N, T), 0.001),
         'rf': np.full(T, 0.0005), 'ix': {n: i for i, n in enumerate(names)}, 't0': 60,
         'month_end': np.array([(d + S.WEEK).astype('datetime64[M]') != d.astype('datetime64[M]') for d in dates]),
         'complete': np.ones(T, dtype=bool), 'sec': None, 'f13': None}
    D['t_end'] = T - 1
    return D


class Engine(unittest.TestCase):
    def test_buy_and_hold_with_one_cost(self):
        D = panel()
        w = np.zeros(7); w[0] = 1.0
        s = S.simulate(D, {60: w}, 60)
        exp = D['R'][0, 61:]
        self.assertAlmostEqual(s['net'][0], (1 - 0.001) * (1 + exp[0]) - 1, places=12)     # one-way cost on the first week only
        np.testing.assert_allclose(s['net'][1:], exp[1:], atol=1e-12)
        self.assertEqual(s['turn'][0], 1.0)

    def test_cash_short_and_leverage(self):
        D = panel()
        D['R'][:] = 0.0
        w = np.zeros(7); w[0] = 1.5                                        # 150% long: 50% borrowed at cash + 0.5%
        s = S.simulate(D, {60: w}, 60, 62)
        fw = (1 + S.FIN_SPREAD) ** (1 / 52) - 1
        self.assertAlmostEqual(s['net'][0], (1 - 1.5 * 0.001) * (1 - 0.5 * 0.0005 - 0.5 * fw) - 1, places=12)
        w = np.zeros(7); w[0], w[1] = 1.0, -1.0                            # long-short: proceeds earn cash, the short pays borrow
        s = S.simulate(D, {60: w}, 60, 62)
        bw = (1 + S.BORROW) ** (1 / 52) - 1
        self.assertAlmostEqual(s['net'][0], (1 - 2 * 0.001) * (1 + 1.0 * 0.0005 - bw) - 1, places=12)

    def test_drift_between_rebalances(self):
        D = panel()
        w = np.zeros(7); w[0], w[1] = 0.5, 0.5
        s = S.simulate(D, {60: w}, 60, 70)
        v = 0.5 * np.cumprod(1 + D['R'][0, 61:71]) + 0.5 * np.cumprod(1 + D['R'][1, 61:71])
        eq = np.cumprod(1 + s['net'])
        self.assertAlmostEqual(eq[-1] * 1.0, v[-1] * (1 - 0.001), places=10)   # held weights drift; no rebalancing cost

    def test_hold_is_the_next_weeks_target(self):
        D = panel()
        Wt, t0 = S.r_trend(D, 40)
        s = S.simulate(D, Wt, t0)
        last = max(t for t in Wt if t <= D['t_end'])
        i = D['ix']['SPY']
        above = D['C'][i, last] > np.nanmean(D['C'][i, last - 39:last + 1])
        if last == D['t_end']:
            self.assertEqual(bool(s['hold'][i] > 0), bool(above))


class Rules(unittest.TestCase):
    def test_trend_and_universe(self):
        D = panel()
        Wt, t0 = S.r_trend(D, 40)
        self.assertGreaterEqual(t0, 60)
        for t, w in Wt.items():
            i = D['ix']['SPY']
            self.assertEqual(w[i] == 1.0, D['C'][i, t] > np.nanmean(D['C'][i, t - 39:t + 1]))
        D['PX'][D['ix']['AAA'], :] = 3.0                                   # under $5: out of the stock universe
        u = S.universe(D, 200)
        self.assertFalse(u[D['ix']['AAA']])
        self.assertTrue(u[D['ix']['BBB']])
        self.assertFalse(u[D['ix']['SPY']])                                # ETFs are not stocks

    def test_cross_section_long_short(self):
        D = panel()
        Wt, _ = S._xs(D, S.s_mom(52, 4), top=0.34, side='ls', min_names=3)
        for w in Wt.values():
            self.assertAlmostEqual(w.sum(), 0.0)
            self.assertAlmostEqual(np.abs(w).sum(), 2.0)

    def test_halloween_months(self):
        D = panel()
        Wt, _ = S.r_halloween(D)
        for t, w in Wt.items():
            m = int(str(D['dates'][t] + S.WEEK)[5:7])
            self.assertEqual(w[0] == 1.0, m in (11, 12, 1, 2, 3, 4))


class Stats(unittest.TestCase):
    def test_metrics(self):
        r = np.full(104, 0.01)
        m = S.metrics(r, np.zeros(104))
        self.assertAlmostEqual(m['cagr'], 1.01 ** 52 - 1, places=10)
        self.assertEqual(m['maxdd'], 0.0)
        r2 = np.array([0.1, -0.5] + [0.0] * 50)
        self.assertAlmostEqual(S.metrics(r2, np.zeros(52))['maxdd'], -0.5)

    def test_psr_and_luck_bar(self):
        self.assertAlmostEqual(S.psr(0.0, 500, 0.0, 3.0), 0.5)
        self.assertGreater(S.psr(0.1, 1000, 0.0, 3.0), 0.99)
        srs = list(np.random.default_rng(0).normal(0, 0.05, 50))
        self.assertGreater(S.sr0_for_trials(srs), 0.05)                     # the best of 50 coin flips looks good
        self.assertAlmostEqual(S._norm_ppf(0.975), 1.959964, places=4)

    def test_pbo(self):
        rng = np.random.default_rng(3)
        noise = rng.normal(0, 0.02, (520, 8))
        self.assertGreater(S.pbo(noise)['pbo'], 0.25)                       # settings with no skill: the best one is luck
        skill = noise.copy()
        skill[:, 0] += 0.01                                                 # one setting really is better
        self.assertLess(S.pbo(skill)['pbo'], 0.05)


class Ledger(unittest.TestCase):
    def test_freeze_and_score(self):
        D = panel()
        D['complete'][-3:] = False                                          # the grid's last weeks are not closed yet
        D['t_end'] = len(D['dates']) - 4
        sims = {'spy': S.simulate(D, S.r_hold(D)[0], 60)}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'l.json'
            made = str(D['dates'][D['t_end']]) + 'T22:00:00+00:00'
            L, live = S.ledger_update(p, D, sims, made_at=made)
            self.assertEqual(L['rules']['spy']['weeks'][-1]['week'], str(D['dates'][D['t_end']]))
            L2, _ = S.ledger_update(p, D, sims, made_at=made)              # the same week is never frozen twice
            self.assertEqual(len(L2['rules']['spy']['weeks']), 1)
            D['complete'][-3:] = True                                       # two more weeks close: the frozen week is scored
            live = S.live_scores(D, L2)
            t = D['t_end']
            self.assertEqual(live['spy']['weeks'], len(D['dates']) - 1 - t)
            self.assertAlmostEqual(live['spy']['ret'], round(D['C'][0, -1] / D['C'][0, t] * (1 - 0.001) - 1, 4), places=4)
            L2['rules']['spy']['weeks'][0]['made_at'] = str(D['dates'][t] + 5 * S.DAY) + 'T09:00:00+00:00'
            late = S.live_scores(D, L2)                                     # frozen on Wednesday: counts from the week after
            self.assertEqual(late['spy']['weeks'], len(D['dates']) - 2 - t)


class Load(unittest.TestCase):
    def test_load_undoes_splits_and_finds_the_last_full_week(self):
        with tempfile.TemporaryDirectory() as d:
            pub = Path(d)
            (pub / 't').mkdir()
            n = 120
            (pub / 'rrg.json').write_text(json.dumps({'start': '2000-01-07', 'bench': {'c': []}, 'series': [{'id': 'SPY'}]}))
            (pub / 'macro.json').write_text(json.dumps({'monthly': {'months': ['2000-01'], 'data': {'ff': [5.2]}}}))
            c = [10.0 + k * 0.1 for k in range(n)]
            (pub / 't' / 'SPY.json').write_text(json.dumps({'t': 'SPY', 'start': '2000-01-07', 'c': c + [None], 'p': c + [None], 'v': [1000] * (n + 1)}))
            p = [2.0] * n                                                   # a 4-for-1 split at week 100: $8 before it
            (pub / 't' / 'AAA.json').write_text(json.dumps({'t': 'AAA', 's': 'tech', 'start': '2000-01-07', 'c': c + [12.0], 'p': p + [2.0],
                                                           'v': [1000] * (n + 1), 'sp': [[100, 4.0]]}))
            D = S.load(pub, today='2030-01-01')
            i = D['ix']['AAA']
            self.assertAlmostEqual(D['PX'][i, 50], 8.0)
            self.assertAlmostEqual(D['PX'][i, 110], 2.0)
            self.assertEqual(D['t_end'], n - 1)                              # the last week has one name in two: not full
            self.assertAlmostEqual(D['rf'][5], 1.052 ** (1 / 52) - 1)


if __name__ == '__main__':
    unittest.main()
