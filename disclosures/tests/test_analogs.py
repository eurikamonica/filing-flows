"""app/analogs.py: price-path analogues (own past and pooled), correlated-asset historical simulation, the lead-lag
regression and the walk-forward scorecard — no look-ahead, planted patterns and leads recovered, the Spearman rank
correlation checked by hand, and the speed on a full-size universe (timings printed)."""
import math
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import analogs as A  # noqa: E402

H = 63
MOVE = 0.15                                   # the planted move after the planted pattern (log return over 63 days)
V_SHAPE = np.r_[np.full(30, -0.012), np.full(30, 0.012)]   # the planted 60-day pattern (daily log returns): a V


def bdays(n, start='2014-01-02'):
    """n business days (Monday-Friday, no holidays) as 'YYYY-MM-DD'."""
    d = np.busday_offset(np.datetime64(start, 'D'), np.arange(n), roll='forward')
    return [str(x) for x in d]


def closes(r, p0=100.0):
    """Closes from daily log returns (r[0] is ignored: the first close is p0)."""
    return p0 * np.exp(np.r_[0.0, np.cumsum(r[1:])])


def walk(rng, n, sigma=0.015):
    return closes(rng.normal(0, sigma, n))


def plant(r, ends, last=True):
    """The V over the 60 bars ending at each end, then the fixed move over the next 63 bars; also at the last bar."""
    n = len(r)
    for e in list(ends) + ([n - 1] if last else []):
        r[e - 59:e + 1] = V_SHAPE
        if e + H < n:
            r[e + 1:e + H + 1] = MOVE / H
    return r


def idx_of(dates, d):
    return dates.index(d)


def assert_finite(tc, obj, where='out'):
    """Every number in a nested result is finite (None is allowed: it means 'not available')."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert_finite(tc, v, f'{where}.{k}')
    elif isinstance(obj, (list, tuple)):
        for j, v in enumerate(obj):
            assert_finite(tc, v, f'{where}[{j}]')
    elif isinstance(obj, (float, np.floating)):
        tc.assertTrue(math.isfinite(obj), where)


def lead_universe(seed=11, n=800, noise_names=8):
    """TGT, its noisy copy CLONE, a leader LEAD (TGT's daily return = LEAD's 10 business days = 2 weeks earlier, plus
    noise), unrelated noise series N0.., and SPY."""
    rng = np.random.default_rng(seed)
    dates = bdays(n)
    rl = rng.normal(0, 0.015, n)
    rt = np.r_[np.zeros(10), rl[:-10]] + rng.normal(0, 0.012, n)
    U = {'LEAD': (dates, closes(rl)), 'TGT': (dates, closes(rt)),
         'CLONE': (dates, closes(rt + rng.normal(0, 0.002, n))), 'SPY': (dates, walk(rng, n, 0.01))}
    for j in range(noise_names):
        U[f'N{j}'] = (dates, walk(rng, n))
    return dates, U


class SelfAnalogues(unittest.TestCase):
    def test_planted_pattern_found_and_move_forecast(self):
        rng = np.random.default_rng(7)
        n, ends = 2200, (400, 700, 1000, 1300, 1600, 1900)
        dates = bdays(n)
        ac = closes(plant(rng.normal(0, 0.01, n), ends))
        out = A.self_analogs(dates, ac, k=len(ends))
        got = sorted(idx_of(dates, nb['date']) for nb in out['neighbors'])
        self.assertEqual(len(got), len(ends))
        for g, e in zip(got, ends):                       # every planted date found (to within two bars)
            self.assertLessEqual(abs(g - e), 2)
        self.assertAlmostEqual(out['end']['q50'], MOVE, delta=0.03)
        self.assertAlmostEqual(out['mean'], MOVE, delta=0.03)
        self.assertEqual(out['p_up'], 1.0)
        self.assertEqual(len(out['q']['q50']), H)
        self.assertAlmostEqual(out['q']['q50'][-1], out['end']['q50'], places=4)
        # the six planted matches are much closer than the six best of a plain random walk
        plain = A.self_analogs(dates, walk(np.random.default_rng(8), n, 0.01), k=len(ends))
        self.assertGreater(out['similarity'], 0.8)
        self.assertGreater(out['similarity'], plain['similarity'] + 0.15)
        # with k = 25 the six planted dates are still the six nearest; the other analogues dilute the similarity
        out25 = A.self_analogs(dates, ac, k=25)
        first6 = sorted(idx_of(dates, nb['date']) for nb in out25['neighbors'][:6])
        self.assertTrue(all(abs(g - e) <= 2 for g, e in zip(first6, ends)))
        self.assertLess(out25['similarity'], out['similarity'])
        assert_finite(self, out25)

    def test_no_look_ahead(self):
        rng = np.random.default_rng(3)
        n, i = 2000, 1500
        dates = bdays(n)
        a = walk(rng, n)
        b = a.copy()
        b[i + 1:] = b[i] * np.exp(np.cumsum(rng.normal(0.01, 0.05, n - i - 1)))   # a different future
        oa, ob = A.self_analogs(dates, a, as_of=i), A.self_analogs(dates, b, as_of=i)
        self.assertEqual(oa, ob)
        self.assertEqual(oa, A.self_analogs(dates, a, as_of=dates[i]))          # an index or a date
        self.assertEqual(oa, A.self_analogs(dates[:i + 1], a[:i + 1]))           # same as truncating the history
        self.assertEqual(oa['as_of'], dates[i])
        tt = sorted(idx_of(dates, nb['date']) for nb in oa['neighbors'])
        self.assertTrue(all(t + H <= i for t in tt))                             # each analogue's future known by then
        self.assertTrue(all(b_ - a_ >= H for a_, b_ in zip(tt, tt[1:])))          # no overlapping futures
        self.assertTrue(10 <= len(tt) <= 25)                     # 1,186 candidate days hold at most 18 such futures
        self.assertEqual(oa['k'], len(tt))
        w = [nb['w'] for nb in oa['neighbors']]
        self.assertAlmostEqual(sum(w), 1.0, places=3)
        d = [nb['dist'] for nb in oa['neighbors']]
        self.assertEqual(d, sorted(d))
        self.assertTrue(all(w1 >= w2 - 1e-5 for w1, w2 in zip(w, w[1:])))          # nearer analogues weigh more
        q = [oa['end'][k] for k in A.QK]
        self.assertEqual(q, sorted(q))
        nb0 = oa['neighbors'][0]
        t0 = idx_of(dates, nb0['date'])
        self.assertAlmostEqual(nb0['fwd'], math.log(a[t0 + H] / a[t0]), places=4)
        self.assertAlmostEqual(nb0['path'][9], math.log(a[t0 + 10] / a[t0]), places=4)
        self.assertEqual(A.self_analogs(dates, a, as_of=i, min_gap=10)['k'], 25)

    def test_short_and_dirty_histories(self):
        rng = np.random.default_rng(5)
        need = 60 + H + 50
        self.assertIsNone(A.self_analogs(bdays(need - 1), walk(rng, need - 1)))
        out = A.self_analogs(bdays(need), walk(rng, need))
        self.assertIsNotNone(out)
        self.assertEqual(out['n_candidates'], 50)                 # the year window shrinks to keep 50 candidates
        self.assertEqual(out['long_window'], 60)
        self.assertIsNone(A.self_analogs(bdays(2000), walk(rng, 2000), as_of=need - 2))
        self.assertIsNone(A.self_analogs(bdays(500), walk(rng, 500), as_of='2000-01-01'))   # before the series
        a = walk(rng, 1200)
        a[100:105] = np.nan
        a[300] = 0.0
        a[:3] = np.nan
        out = A.self_analogs(bdays(1200), a)
        self.assertGreaterEqual(out['k'], 8)                      # ~950 candidate days: about a dozen futures
        assert_finite(self, out)
        flat = np.full(600, 50.0)                                                    # a halted stock: no division by zero
        assert_finite(self, A.self_analogs(bdays(600), flat))


class PooledAnalogues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(21)
        n = 1500
        cls.dates = bdays(n)
        cls.U = {}
        cls.plants = {}
        for j in range(16):
            r = rng.normal(0, 0.01, n)
            if j < 6:                                  # the pattern planted once in six tickers, at different dates
                e = 420 + 150 * j
                plant(r, [e], last=False)
                cls.plants[f'S{j:02d}'] = e
            cls.U[f'S{j:02d}'] = (cls.dates, closes(r))
        r = plant(rng.normal(0, 0.01, n), [], last=True)
        cls.U['TGT'] = (cls.dates, closes(r))

    def test_planted_pattern_across_tickers(self):
        out = A.pooled_analogs('TGT', self.U, k=6)
        hits = [nb for nb in out['neighbors']
                if nb['ticker'] in self.plants and abs(idx_of(self.dates, nb['date']) - self.plants[nb['ticker']]) <= 3]
        self.assertGreaterEqual(len(hits), 5)
        self.assertGreaterEqual(len({nb['ticker'] for nb in hits}), 5)
        self.assertAlmostEqual(out['end']['q50'], MOVE, delta=0.04)
        self.assertGreater(out['p_up'], 0.8)
        assert_finite(self, out)

    def test_neighbours_from_several_tickers(self):
        out = A.pooled_analogs('S10', self.U, k=50)
        self.assertEqual(out['k'], 50)
        self.assertGreaterEqual(len({nb['ticker'] for nb in out['neighbors']}), 8)
        self.assertTrue(all({'ticker', 'date', 'dist', 'fwd', 'path'} <= set(nb) for nb in out['neighbors']))
        self.assertEqual(len(out['q']['q05']), H)
        by = {}
        for nb in out['neighbors']:                    # no two analogues of one ticker with overlapping futures
            by.setdefault(nb['ticker'], []).append(idx_of(self.dates, nb['date']))
        for ts in by.values():
            ts.sort()
            self.assertTrue(all(b - a >= H for a, b in zip(ts, ts[1:])))
        # a target given as (dates, ac), not in the universe, works the same
        out2 = A.pooled_analogs(self.U['S10'], self.U, k=50)
        self.assertEqual(out2['end'], out['end'])

    def test_library_no_look_ahead(self):
        end = self.dates[1100]
        lib = A.build_library(self.U, 60, H, 5, end)
        e = np.datetime64(end).astype(np.int64)
        P = A.prepare_universe(self.U)
        fwd_end = np.array([P[lib.tickers[k]].days[t + H] for k, t in zip(lib.tick, lib.t)])
        self.assertTrue((fwd_end <= e).all())                            # every forward period ends by the cut-off
        self.assertTrue((lib.t >= 252).all())
        self.assertGreater(len(lib), 1000)
        rng = np.random.default_rng(1)
        V = {}
        for t, (d, c) in self.U.items():                                 # a different future for every ticker
            c2 = c.copy()
            c2[1101:] = c2[1100] * np.exp(np.cumsum(rng.normal(0, 0.05, len(c) - 1101)))
            V[t] = (d, c2)
        lib2 = A.build_library(V, 60, H, 5, end)
        self.assertTrue(np.array_equal(lib.F, lib2.F) and np.array_equal(lib.fwd, lib2.fwd))
        o1 = A.pooled_analogs('S03', self.U, as_of_date=end)
        o2 = A.pooled_analogs('S03', V, as_of_date=end)
        self.assertEqual(o1, o2)
        self.assertEqual(o1['as_of'], end)
        self.assertEqual(o1, A.pooled_analogs('S03', self.U, as_of_date=end, lib=lib))
        with self.assertRaises(ValueError):                              # a library that ends after the as-of date
            A.pooled_analogs('S03', self.U, as_of_date=self.dates[1000], lib=lib)

    def test_library_bound_and_query(self):
        lib = A.build_library(self.U, 60, H, 5, self.dates[-1], max_lib=2000)
        self.assertLessEqual(len(lib), 2000)
        self.assertGreater(lib.step, 5)
        f = A.feature_vector(*self.U['TGT'])
        idx, dist, med = A.query(lib, f, 10)
        self.assertEqual(len(idx), 10)
        brute = np.sqrt(((lib.F.astype(float) - f) ** 2).sum(axis=1))
        self.assertAlmostEqual(dist[0], brute.min(), places=3)           # the chunked matrix product = brute force
        self.assertTrue(np.all(np.diff(dist) >= -1e-6))
        self.assertAlmostEqual(med, float(np.median(brute)), places=2)

    def test_short_target(self):
        rng = np.random.default_rng(2)
        self.assertIsNone(A.pooled_analogs((bdays(100), walk(rng, 100)), self.U))
        out = A.pooled_analogs((self.dates[-200:], walk(rng, 200)), self.U)   # under a year: year features shortened
        self.assertEqual(out['k'], 50)
        assert_finite(self, out)
        self.assertIsNone(A.pooled_analogs('NOPE', self.U))


class CorrelatedPeers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dates, cls.U = lead_universe()

    def test_clone_first_lead_detected_noise_not(self):
        d, ac = self.U['TGT']
        out = A.correlated_peers(d, ac, self.U, top=20, target_ticker='TGT')
        names = [p['ticker'] for p in out]
        self.assertEqual(names[0], 'CLONE')
        self.assertNotIn('TGT', names)
        self.assertGreater(out[0]['corr'], 0.95)
        self.assertEqual(out[0]['n'], 104)                               # 504 trading days = 104 weeks
        self.assertEqual([abs(p['corr']) for p in out], sorted((abs(p['corr']) for p in out), reverse=True))
        lead = next(p for p in out if p['ticker'] == 'LEAD')
        self.assertEqual(lead['best_lag'], 2)
        self.assertLess(lead['lead_p'], 0.01)
        self.assertGreater(lead['lead_corr'], 0.5)
        self.assertEqual(sorted(lead['lead_lag']), [1, 2, 3, 4])
        self.assertLess(abs(lead['corr']), 0.3)
        noise = [p['lead_p'] for p in out if p['ticker'].startswith('N') or p['ticker'] == 'SPY']
        self.assertEqual(len(noise), 9)
        self.assertTrue(all(pv > 0.01 for pv in noise), noise)          # none passes the bar the planted lead clears
        self.assertLessEqual(sum(pv < 0.05 for pv in noise), 1)         # ~0.45 of 9 expected by chance at 5%
        self.assertTrue(all(0 <= p['lead_p'] <= 1 for p in out))
        assert_finite(self, out)

    def test_lead_p_false_positive_rate(self):
        """On 200 unrelated random walks the Bonferroni-adjusted lead p-value is below 0.05 about 5% of the time or
        less (it is slightly conservative), so 'significant leader' means something."""
        rng = np.random.default_rng(5)
        n = 800
        d = bdays(n)
        U = {f'Z{j:03d}': (d, walk(rng, n)) for j in range(200)}
        U['TGT'] = (d, walk(rng, n))
        out = A.correlated_peers(*U['TGT'], U, top=200, target_ticker='TGT')
        p = np.array([x['lead_p'] for x in out])
        self.assertEqual(len(p), 200)
        self.assertLess((p < 0.05).mean(), 0.08)
        self.assertLess((p < 0.01).mean(), 0.025)

    def test_fisher_p_by_hand(self):
        r, n = 0.3, 100
        z = math.atanh(r) * math.sqrt(n - 3)
        p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
        self.assertAlmostEqual(A._fisher_p(r, n, 1), p, places=10)
        self.assertAlmostEqual(A._fisher_p(r, n, 4), 4 * p, places=10)
        self.assertEqual(A._fisher_p(0.01, n, 4), 1.0)

    def test_exclusions_and_matrix_reuse(self):
        d, ac = self.U['TGT']
        U = dict(self.U)
        U['HALF'] = (d[-300:], self.U['CLONE'][1][-300:])               # only ~60 of 104 weeks: excluded
        out = A.correlated_peers(d, ac, U, top=20)                       # no target_ticker: exact copy dropped
        names = [p['ticker'] for p in out]
        self.assertNotIn('TGT', names)
        self.assertNotIn('HALF', names)
        self.assertEqual(names[0], 'CLONE')
        self.assertEqual(len(out), len(self.U) - 1)
        wm = A.weekly_matrix(U, d[-1], 108)
        self.assertEqual(A.correlated_peers(d, ac, U, top=20, wm=wm), out)
        self.assertEqual(len(A.correlated_peers(d, ac, U, top=3, wm=wm)), 3)
        # as of an earlier date: only weeks up to then (and a matrix ending later is refused)
        early = A.correlated_peers(d, ac, U, top=20, end_date=d[650])
        self.assertEqual(early, A.correlated_peers(d[:651], ac[:651], U, top=20))
        with self.assertRaises(ValueError):
            A.correlated_peers(d, ac, U, wm=wm, end_date=d[650])
        self.assertEqual(A.correlated_peers(d[:200], ac[:200], U), [])  # too short for the 80% overlap


class PeerConditional(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(31)
        n = 1500
        cls.dates = bdays(n)
        f = rng.normal(0, 0.01, n)
        cls.U = {'SPY': (cls.dates, closes(0.6 * f + rng.normal(0, 0.004, n)))}
        for j in range(6):
            cls.U[f'P{j}'] = (cls.dates, closes(f + rng.normal(0, 0.008, n)))
        cls.U['TGT'] = (cls.dates, closes(f + rng.normal(0, 0.01, n)))

    def test_shape_weights_and_no_look_ahead(self):
        d, ac = self.U['TGT']
        peers = A.correlated_peers(d, ac, self.U, top=4, target_ticker='TGT')
        self.assertEqual(len(peers), 4)
        i = 1300
        out = A.peer_conditional('TGT', peers, self.U, as_of=self.dates[i])
        self.assertEqual(out['method'], 'peer')
        self.assertEqual(out['as_of'], self.dates[i])
        self.assertEqual(sorted(out['basket']), sorted(p['ticker'] for p in peers if p['ticker'] != 'SPY'))
        self.assertTrue(out['spy'])
        self.assertEqual(set(out['features']), {f'{a}_{w}' for a in ('basket', 'spy', 'own') for w in (5, 21, 63)})
        self.assertTrue(0 < out['k'] <= 40)
        self.assertEqual(set(out['q']), set(A.QK))
        self.assertTrue(all(len(v) == H for v in out['q'].values()))
        self.assertTrue(0 <= out['p_up'] <= 1 and 0 <= out['similarity'] <= 1)
        w = np.array([nb['w'] for nb in out['neighbors']])
        dist = np.array([nb['dist'] for nb in out['neighbors']])
        self.assertAlmostEqual(w.sum(), 1.0, places=3)
        w_hand = np.exp(-dist ** 2 / (2 * np.median(dist ** 2)))
        np.testing.assert_allclose(w, w_hand / w_hand.sum(), atol=2e-4)
        tt = sorted(idx_of(self.dates, nb['date']) for nb in out['neighbors'])
        self.assertTrue(all(t + H <= i for t in tt))
        self.assertTrue(all(b - a >= H for a, b in zip(tt, tt[1:])))
        nb0 = out['neighbors'][0]
        t0 = idx_of(self.dates, nb0['date'])
        self.assertAlmostEqual(nb0['fwd'], math.log(ac[t0 + H] / ac[t0]), places=4)    # the TARGET's next move
        # a different future for everyone does not change the forecast
        rng = np.random.default_rng(4)
        V = {t: (dd, np.r_[c[:i + 1], c[i] * np.exp(np.cumsum(rng.normal(0, 0.05, len(c) - i - 1)))])
             for t, (dd, c) in self.U.items()}
        self.assertEqual(out, A.peer_conditional('TGT', peers, V, as_of=self.dates[i]))
        assert_finite(self, out)

    def test_inputs(self):
        names = A.peer_conditional('TGT', ['P0', 'P1', 'TGT', 'NOPE'], self.U)          # plain tickers are fine
        self.assertEqual(names['basket'], ['P0', 'P1'])
        no_spy = {k: v for k, v in self.U.items() if k != 'SPY'}
        self.assertIsNone(A.peer_conditional('TGT', [], no_spy))                        # nothing to condition on
        only_spy = A.peer_conditional('TGT', [], self.U)
        self.assertEqual(only_spy['basket'], [])
        self.assertEqual(len(only_spy['features']), 6)
        rng = np.random.default_rng(0)
        self.assertIsNone(A.peer_conditional((bdays(150), walk(rng, 150)), ['P0'], self.U))


class LeadLag(unittest.TestCase):
    def test_none_without_leaders_and_beta_with_one(self):
        dates, U = lead_universe(n=1100)
        d, ac = U['TGT']
        self.assertIsNone(A.lead_lag_forecast('TGT', [], U))
        self.assertIsNone(A.lead_lag_forecast('TGT', [{'ticker': 'N0', 'lead_p': 0.3, 'best_lag': 1}], U))
        peers = A.correlated_peers(d, ac, U, top=20, target_ticker='TGT')
        out = A.lead_lag_forecast('TGT', peers, U)
        self.assertIsNotNone(out)
        self.assertEqual(out['n_leaders'], sum(p['lead_p'] < 0.05 for p in peers))
        self.assertIn('LEAD', out['beta'])
        self.assertGreater(out['beta']['LEAD'], 0.5)              # the next 21 days share 10 days with the last 2 weeks
        self.assertGreater(out['r2_in'], 0.2)
        self.assertEqual(out['n_train'], 756 - 21 + 1)
        q = [out['q_end'][k] for k in A.QK]
        self.assertEqual(q, sorted(q))
        # the point forecast is the fitted line at the leaders' latest returns
        self.assertAlmostEqual(out['point'], out['alpha'] + sum(lr['beta'] * lr['x_now'] for lr in out['leaders']), places=3)
        self.assertTrue(out['q_end']['q05'] < out['point'] < out['q_end']['q95'])
        # no look-ahead: as of an earlier day, a different future changes nothing
        i = 1000
        V = {t: (dd, np.r_[c[:i + 1], c[i] * np.exp(np.cumsum(np.random.default_rng(9).normal(0, .05, len(c) - i - 1)))])
             for t, (dd, c) in U.items()}
        lead = [{'ticker': 'LEAD', 'lead_p': 0.001, 'best_lag': 2}]
        self.assertEqual(A.lead_lag_forecast('TGT', lead, U, as_of=dates[i]), A.lead_lag_forecast('TGT', lead, V, as_of=dates[i]))
        assert_finite(self, out)


class Evaluation(unittest.TestCase):
    def test_spearman_by_hand(self):
        # no ties: ρ = 1 − 6 Σd² ÷ (n (n² − 1)) = 1 − 6 × 16 ÷ 120 = 0.2
        self.assertAlmostEqual(A.spearman([10, 20, 30, 40, 50], [3, 1, 4, 5, 2]), 0.2, places=12)
        # ties take the average rank: ranks (1, 2, 3, 4) vs (1, 2.5, 2.5, 4) → 4.5 ÷ √(5 × 4.5) = 3 ÷ √10
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [1, 2, 2, 3]), 3 / math.sqrt(10), places=12)
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0, places=12)
        self.assertEqual(A.rankdata([3, 1, 3, 2]).tolist(), [3.5, 1.0, 3.5, 2.0])
        self.assertAlmostEqual(A.spearman([1, 2, np.nan, 4, 5], [2, 1, 9, 4, 3]), 0.6, places=12)   # NaN pair dropped
        self.assertIsNone(A.spearman([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(A.spearman([1, 2], [1, 2]))

    def test_pinball_and_pit(self):
        row = {'q': dict(zip(A.QK, [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3])), 'realized': 0.05}
        s = A._score([row])
        e = 0.05 - np.array([-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3])
        self.assertAlmostEqual(s['pinball'], float(np.mean(np.maximum(A.QS * e, (A.QS - 1) * e))), places=6)
        self.assertEqual((s['cover80'], s['cover50']), (1.0, 1.0))
        self.assertAlmostEqual(s['pit'][0], 0.625, places=3)                      # halfway between q50 and q75

    def test_naive_calibration_on_random_walks(self):
        rng = np.random.default_rng(41)
        n = 1500
        dates = bdays(n)
        U = {f'R{j:02d}': (dates, walk(rng, n)) for j in range(20)}
        origins = dates[300:n - H - 1:30]
        out = A.evaluate_universe('naive', U, sorted(U), origins, max_tickers=20, max_origins=40)
        self.assertEqual(out['n_tickers'], 20)
        self.assertGreater(out['n'], 500)
        self.assertTrue(0.6 <= out['cover80'] <= 0.95, out['cover80'])
        self.assertTrue(0.3 <= out['cover50'] <= 0.7, out['cover50'])
        self.assertLess(abs(out['ic']), 0.15)                                     # no skill on a random walk
        self.assertEqual(len(out['pit']), out['n'])
        self.assertEqual(sum(out['pit_hist']), out['n'])
        assert_finite(self, out)
        one = A.evaluate('naive', 'R00', U, origins)
        self.assertEqual(one['n'], len(origins))
        r0 = one['rows'][3]                                        # origin bar 390: a full 252-day window
        i = dates.index(r0['origin'])
        c = U['R00'][1]
        self.assertAlmostEqual(r0['realized'], math.log(c[i + H] / c[i]), places=4)
        j = np.arange(i - 251, i + 1)
        self.assertAlmostEqual(r0['q']['q50'], float(np.median(np.log(c[j] / c[j - H]))), places=4)

    def test_every_method_walk_forward(self):
        dates, U = lead_universe(n=1300)
        origins = [dates[k] for k in (950, 1050, 1150, 1230)]
        rng = np.random.default_rng(6)
        for m in A.METHODS:
            out = A.evaluate(m, 'TGT', U, origins)
            for key in ('n', 'cover80', 'cover50', 'pinball', 'ic', 'pit'):
                self.assertIn(key, out)
            self.assertGreater(out['n'], 0, m)
            self.assertEqual(out['n'] + out['n_skipped'], len(origins))
            assert_finite(self, out)
            # every forecast uses data on or before its origin only: a different future after the origin changes no
            # forecast (only the realized outcome)
            k0 = dates.index(origins[0])
            V = {t: (dd, np.r_[c[:k0 + 1], c[k0] * np.exp(np.cumsum(rng.normal(0, .05, len(c) - k0 - 1)))])
                 for t, (dd, c) in U.items()}
            a = A.evaluate(m, 'TGT', U, origins[:1])['rows'][0]
            b = A.evaluate(m, 'TGT', V, origins[:1])['rows'][0]
            self.assertEqual(a['q'], b['q'], m)
            self.assertNotEqual(a['realized'], b['realized'])
        self.assertEqual(A.evaluate('self', 'TGT', U, [dates[-10]])['n'], 0)     # no outcome yet: skipped
        empty = A.evaluate('self', 'TGT', U, [dates[100]])                          # too little history
        self.assertEqual((empty['n'], empty['cover80'], empty['pit']), (0, None, []))
        with self.assertRaises(ValueError):
            A.evaluate('magic', 'TGT', U, origins)
        sc = A.evaluate_universe('peer', U, sorted(U), origins, max_tickers=5, max_origins=2)
        self.assertEqual((sc['n_tickers'], sc['n_origins']), (5, 2))
        self.assertIn('ic_xs', sc)


class Benchmarks(unittest.TestCase):
    """Speed on a full-size universe: 1,750 stocks × 2,500 bars plus SPY and 11 sector funds (timings printed)."""

    def test_speed(self):
        rng = np.random.default_rng(99)
        n, T = 2500, 1750
        dates = bdays(n, '2016-11-01')
        mkt = rng.normal(0.0003, 0.01, n)
        sec = rng.normal(0, 0.007, (11, n))
        U = {'SPY': (dates, closes(mkt))}
        for s in range(11):
            U[f'X{s:02d}'] = (dates, closes(mkt + sec[s]))
        for j in range(T):
            r = rng.uniform(0.6, 1.4) * mkt + sec[j % 11] + rng.normal(0, 0.016, n)
            U[f'T{j:04d}'] = (dates, closes(r))
        best = lambda f, reps: min(_timed(f) for _ in range(reps))
        t_prep = _timed(lambda: A.prepare_universe(U))
        P = A.prepare_universe(U)
        d, ac = U['T0005']
        t_self = best(lambda: A.self_analogs(d, ac), 5)
        lib_box = {}
        t_lib = _timed(lambda: lib_box.setdefault('lib', A.build_library(P, 60, H, 5, dates[-1])))
        lib = lib_box['lib']
        t_pool = best(lambda: A.pooled_analogs('T0005', P, lib=lib), 5)
        t_wm = _timed(lambda: A.weekly_matrix(P, dates[-1], 108))
        wm = A.weekly_matrix(P, dates[-1], 108)
        t_peers = best(lambda: A.correlated_peers(d, ac, P, wm=wm, target_ticker='T0005'), 3)
        t_peers_cold = _timed(lambda: A.correlated_peers(d, ac, U, target_ticker='T0005'))   # raw universe
        peers = A.correlated_peers(d, ac, P, wm=wm, target_ticker='T0005')
        t_pc = best(lambda: A.peer_conditional('T0005', peers, P), 3)
        lead = [{'ticker': 'X05', 'lead_p': 0.001, 'best_lag': 2}]
        t_ll = best(lambda: A.lead_lag_forecast('T0005', lead, P), 3)
        print(f'\n  analogs benchmarks ({T} stocks + 12 funds × {n} bars, {len(lib)} library rows, step {lib.step}):'
              f'\n    prepare_universe {t_prep:.2f} s · self_analogs {t_self * 1e3:.1f} ms · build_library {t_lib:.2f} s'
              f' · pooled query {t_pool * 1e3:.1f} ms\n    weekly_matrix {t_wm * 1e3:.0f} ms · correlated_peers'
              f' {t_peers * 1e3:.1f} ms with the matrix, {t_peers_cold * 1e3:.0f} ms from the raw universe · peer_conditional'
              f' {t_pc * 1e3:.1f} ms · lead_lag_forecast {t_ll * 1e3:.1f} ms', flush=True)
        self.assertLessEqual(len(lib), 200000)
        self.assertLess(t_self, 0.05)
        self.assertLess(t_pool, 0.2)
        self.assertLess(t_peers_cold, 2.0)
        self.assertEqual(peers[0]['ticker'], 'X05')                     # T0005's own sector fund (sector 5 % 11)


def _timed(f):
    t = time.perf_counter()
    f()
    return time.perf_counter() - t


if __name__ == '__main__':
    unittest.main()
