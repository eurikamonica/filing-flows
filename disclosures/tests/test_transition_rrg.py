"""RRG quadrant odds and paths (app/transition_rrg.py): the vectorised RRG equals the chart's formula, the walk-forward
predictions at an origin never see later weeks, the labels follow the rules fixed in advance, a known Markov chain is
recovered and called calibrated while pure noise is not, and the published file has what the page reads."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import transition_rrg as TR
    import chaos_forecast as CF
except ImportError:                                          # numpy is part of the analysis extras
    np = None

DAYS = None if np is None else np.datetime64('2004-01-02') + 7 * np.arange(1200)
TRUE = None if np is None else np.array([[.80, .15, .03, .02], [.05, .75, .18, .02], [.03, .02, .80, .15], [.17, .02, .03, .78]])


def markov(lines=60, weeks=1200, P=None, seed=1):
    """Quadrant paths from a known weekly chain (or i.i.d. draws when P is a vector)."""
    rng = np.random.default_rng(seed)
    Q = np.zeros((lines, weeks), int)
    Q[:, 0] = rng.integers(0, 4, lines)
    for t in range(1, weeks):
        if P.ndim == 1:
            Q[:, t] = rng.choice(4, lines, p=P)
        else:
            u = rng.random(lines)
            Q[:, t] = (u[:, None] > np.cumsum(P[Q[:, t - 1]], 1)).sum(1).clip(0, 3)
    H = rng.integers(0, 4, (lines, weeks))
    return Q, H


@unittest.skipIf(np is None, 'numpy not installed')
class Panel(unittest.TestCase):
    def test_vectorised_rrg_equals_the_chart_formula(self):
        rng = np.random.default_rng(3)
        rs = 100 * np.exp(np.cumsum(rng.normal(0, .03, (6, 300)), 1))
        rs[1, 40:43] = np.nan                                    # a gap restarts the averages, as in the browser
        rs[2, :70] = np.nan                                      # a late start
        x, y = TR.rrg_panel(rs)
        for i in range(6):
            S = CF.rrg_series(rs[i])
            np.testing.assert_array_equal(np.isnan(x[i]), np.isnan(S['x']))
            np.testing.assert_allclose(np.nan_to_num(x[i]), np.nan_to_num(S['x']), atol=1e-9)
            np.testing.assert_allclose(np.nan_to_num(y[i]), np.nan_to_num(S['y']), atol=1e-9)

    def test_quadrant_and_heading_codes(self):
        x = np.array([[101., 102, 101, 99, 98, 100]]); y = np.array([[101., 99, 98, 97, 101, 101]])
        Q, H = TR.states(x, y)
        self.assertEqual(Q[0].tolist(), [0, 1, 1, 2, 3, -1])   # on an axis: no quadrant
        self.assertEqual(H[0].tolist(), [-1, 1, 2, 2, 3, -1])  # no step before the first week

    def test_liquidity_floor(self):
        C = np.full((2, 20), 10.0); V = np.full((2, 20), 2e6)    # $20M a week
        C[1] = 2.0                                               # under $3
        ok = TR.liquid(C, V)
        self.assertFalse(ok[0, :9].any())                        # fewer than 10 weeks of volume
        self.assertTrue(ok[0, 9:].all())
        self.assertFalse(ok[1].any())


@unittest.skipIf(np is None, 'numpy not installed')
class Smoothing(unittest.TestCase):
    def test_rows_are_distributions_shrunk_toward_the_prior(self):
        N = np.array([[10., 0, 0, 0], [0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 1000]])
        prior = np.array([.25, .25, .25, .25])
        P = TR.smooth(N, prior)
        np.testing.assert_allclose(P.sum(1), 1)
        np.testing.assert_allclose(P[1], prior)                  # no data: the prior
        self.assertAlmostEqual(P[0, 0], (10 + 2.5) / 20)         # λ = 10
        self.assertGreater(P[3, 3], .99)

    def test_chain_matrix_is_stochastic_and_collapses_to_quadrants(self):
        rng = np.random.default_rng(0)
        for joint in (False, True):
            P = TR.chain_matrix(rng.integers(0, 50, (16, 16)).astype(float), rng.integers(1, 50, (4, 4)).astype(float), joint)
            np.testing.assert_allclose(P.sum(1), 1)
            np.testing.assert_allclose(TR.chain_quadrant(np.linalg.matrix_power(P, 13), joint).sum(1), 1)


@unittest.skipIf(np is None, 'numpy not installed')
class NoLookAhead(unittest.TestCase):
    def test_predictions_at_an_origin_ignore_every_later_week(self):
        Q, H = markov(P=TRUE)
        IQ = markov(P=TRUE, seed=9)[0]
        ok = np.ones(Q.shape, bool)
        o = 700
        Q2, H2, IQ2, ok2 = Q.copy(), H.copy(), IQ.copy(), ok.copy()
        rng = np.random.default_rng(5)
        Q2[:, o + 1:] = rng.integers(-1, 4, Q2[:, o + 1:].shape)   # scramble everything after the origin
        H2[:, o + 1:] = rng.integers(-1, 4, H2[:, o + 1:].shape)
        IQ2[:, o + 1:] = rng.integers(-1, 4, IQ2[:, o + 1:].shape)
        ok2[:, o + 1:] = rng.random(ok2[:, o + 1:].shape) > .5
        for h in TR.HORIZONS:
            A = TR.Direct(Q, H, IQ, ok, h, ['q', 'qh', 'iq']); B = TR.Direct(Q2, H2, IQ2, ok2, h, ['q', 'qh', 'iq'])
            for head in ('q', 'qh', 'iq'):
                ma, pa = A.predict(o, head); mb, pb = B.predict(o, head)
                np.testing.assert_array_equal(ma, mb)
                np.testing.assert_array_equal(pa, pb)
        for joint in (False, True):
            A = TR.Chain(Q, H, IQ, ok, joint); B = TR.Chain(Q2, H2, IQ2, ok2, joint)
            for k in TR.HORIZONS:
                np.testing.assert_array_equal(A.predict(o, k)[1], B.predict(o, k)[1])

    def test_the_outcome_week_itself_does_count_once_it_is_the_origin(self):
        Q, H = markov(P=TRUE)
        ok = np.ones(Q.shape, bool)
        F = TR.Direct(Q, H, Q, ok, 4, ['q'])
        before = F.cq[600 - 4].sum()
        self.assertEqual(before, ok[:, :597].sum())              # pairs w → w + 4 with w + 4 ≤ 600


@unittest.skipIf(np is None, 'numpy not installed')
class Labels(unittest.TestCase):
    def ev(self, **k):
        d = {'origins': 100, 'predictions': 5000, 'brier_skill_vs_stay': [.05, .02, .08], 'brier_skill_vs_freq': [.04, .01, .07], 'ece': .01}
        d.update(k)
        return d

    def test_rules_fixed_in_advance(self):
        self.assertEqual(TR.label(self.ev()), 'calibrated')
        self.assertEqual(TR.label(self.ev(ece=.03)), 'experimental')
        self.assertEqual(TR.label(self.ev(brier_skill_vs_freq=[.01, -.01, .03])), 'experimental')
        self.assertEqual(TR.label(self.ev(brier_skill_vs_stay=[-.01, -.03, .01])), 'descriptive_only')
        self.assertEqual(TR.label(self.ev(origins=49)), 'insufficient_data')
        self.assertEqual(TR.label(self.ev(predictions=1999)), 'insufficient_data')

    def test_a_known_chain_is_recovered_and_called_calibrated(self):
        Q, H = markov(P=TRUE)
        ok = np.ones(Q.shape, bool)
        ev = TR.evaluate_direct(Q, H, Q, ok, DAYS, 4, ['q'])['q']
        self.assertEqual(ev['label'], 'calibrated')
        F = TR.Direct(Q, H, Q, ok, 4, ['q'])
        np.testing.assert_allclose(F.known(Q.shape[1])[0], np.linalg.matrix_power(TRUE, 4), atol=.02)

    def test_noise_is_not_a_forecast(self):
        Q, H = markov(P=np.array([.4, .1, .3, .2]))              # the next quadrant does not depend on this one
        ok = np.ones(Q.shape, bool)
        ev = TR.evaluate_direct(Q, H, Q, ok, DAYS, 4, ['q', 'qh'])
        for head in ('q', 'qh'):
            self.assertNotIn(ev[head]['label'], ('calibrated', 'experimental'))
            self.assertLessEqual(ev[head]['brier_skill_vs_freq'][0], 0)


@unittest.skipIf(np is None, 'numpy not installed')
class Build(unittest.TestCase):
    def test_published_file(self):
        rng = np.random.default_rng(11)
        W = 900
        g0 = np.datetime64('2006-01-06')
        weeks = str(g0 + np.timedelta64(7 * (W - 1), "D"))
        walk = lambda s: (100 * np.exp(np.cumsum(rng.normal(0, s, W)))).round(4).tolist()
        with tempfile.TemporaryDirectory() as tmp:
            pub = Path(tmp)
            (pub / 't').mkdir()
            spy = walk(.02)
            series = [{'id': f'E{i}', 'name': f'E{i}', 'group': 'sector-etf', 'start': str(g0), 'c': walk(.03)} for i in range(25)]
            tickers = {}
            for i in range(30):
                t = f'C{i}'
                tickers[t] = {'n': t, 's': 'x', 'rev': 1e9, 'start': str(g0)}
                doc = {'t': t, 'start': str(g0), 'c': walk(.04), 'v': [5000] * W}
                if i < 25:
                    doc.update(bl='SIC 1', blevel='sic4', bcode='0001', bn=30, bx=walk(.03), bi=walk(.03))
                (pub / 't' / f'{t}.json').write_text(json.dumps(doc))
            (pub / 'rrg.json').write_text(json.dumps({'start': str(g0), 'weeks': weeks, 'bench': {'start': str(g0), 'c': spy},
                                                      'series': series, 'tickers': tickers}))
            (pub / 'industries.json').write_text(json.dumps({'rows': [{'id': f'sic4:{i:04d}', 'start': str(g0), 'c': walk(.03)} for i in range(20)]
                                                             + [{'id': 'sic4:short', 'start': str(g0), 'c': walk(.03)[:100]}]}))
            doc = TR.build(pub, verbose=False)
            back = json.loads((pub / 'rrg-transition-model.json').read_text())
        self.assertEqual(back['schema_version'], 'rrg_transition_model.v1')
        self.assertEqual(set(back['groups']), {'etf_vs_market', 'industry_vs_market', 'company_vs_market', 'company_vs_industry'})
        gi = back['groups']['industry_vs_market']
        self.assertEqual((gi['lines'], gi['primary']), (20, 'q'))                  # under three years of weeks: left out
        self.assertEqual(set(gi['bands']), {'1', '4', '13'})
        self.assertFalse(gi['chain']['joint'])
        g = back['groups']['company_vs_industry']
        self.assertEqual(g['primary'], 'iq')
        self.assertEqual(g['lines'], 25)
        for h in ('1', '4', '13'):
            self.assertEqual(len(g['heads']['iq'][h]['P']), 16)
            self.assertIn(g['heads']['iq'][h]['label'], ('calibrated', 'experimental', 'descriptive_only', 'insufficient_data'))
            np.testing.assert_allclose(np.array(g['heads']['q'][h]['P']).sum(1), 1, atol=1e-3)
        self.assertTrue(g['chain']['joint'])
        self.assertEqual(np.array(g['chain']['P1']).shape, (16, 16))
        self.assertEqual(set(g['chain']['labels']), {'1', '4', '13'})
        self.assertFalse(back['groups']['company_vs_market']['chain']['joint'])
        self.assertEqual(doc['test_from'], '2012-01-06')


@unittest.skipIf(np is None, 'numpy not installed')
class Replay(unittest.TestCase):
    """The replayed ranges (company page): stepping a path through the formula reproduces the chart, and the
    walk-forward coverage of the ranges is measured on lines whose moves really are like their past."""

    def panel(self, lines=40, weeks=900, seed=4):
        rng = np.random.default_rng(seed)
        vol = rng.uniform(.02, .06, lines)[:, None]
        C = 50 * np.exp(np.cumsum(rng.normal(0, 1, (lines, weeks)) * vol, 1))
        return C, np.full(C.shape, 100.0), np.ones(C.shape, bool)

    def test_stepping_the_real_moves_reproduces_the_chart(self):
        C, B, _ = self.panel()
        rel = 100 * C / B
        LR = np.full(rel.shape, np.nan); LR[:, 1:] = np.log(rel[:, 1:] / rel[:, :-1])
        S = TR.rrg_states(rel)
        o, L = 600, np.arange(C.shape[0])
        cum, X, Y = TR.step_paths(S, rel, o, L, LR[:, o + 1:o + 14][:, None, :])
        np.testing.assert_allclose(X[:, 0, :], S['x'][:, o + 1:o + 14], atol=1e-9)
        np.testing.assert_allclose(Y[:, 0, :], S['y'][:, o + 1:o + 14], atol=1e-9)
        cum, X, Y = TR.replay(S, rel, LR, o)
        self.assertEqual(cum.shape, (C.shape[0], 144, 13))     # every 13-week run of the last 156 weeks

    def test_ranges_of_a_random_walk_hold_their_coverage(self):
        C, B, ok = self.panel()
        out = TR.band_check(C, B, ok, DAYS[:C.shape[1]] if len(DAYS) >= C.shape[1] else
                            np.datetime64('2004-01-02') + 7 * np.arange(C.shape[1]))
        for h in ('1', '4'):
            cv = out[h]['coverage']
            self.assertAlmostEqual(cv['p80'], .8, delta=.05)
            self.assertAlmostEqual(cv['p50'], .5, delta=.05)
        # 13 weeks: three years hold only about a dozen independent 13-week runs, so the ranges come out too narrow even
        # for a pure random walk (as on the real data: 74% for the 80% range) — the check says so instead of hiding it
        self.assertTrue(.68 < out['13']['coverage']['p80'] < .79)
        self.assertEqual(out['1']['coverage']['p80'], out['1']['coverage']['x80'])   # one week: x moves with the price

    def test_band_labels(self):
        self.assertEqual(TR.band_label(.79, .52), 'calibrated')
        self.assertEqual(TR.band_label(.74, .50), 'experimental')
        self.assertEqual(TR.band_label(None, .5), 'insufficient_data')


if __name__ == '__main__':
    unittest.main()
