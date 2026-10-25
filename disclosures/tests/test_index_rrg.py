"""index_rrg.py: the four index ETFs around their centre — the centre's weights, cash, the comparison, next week's price
for each quadrant, the chain's routes, the published file and its ledger."""
import datetime as dt, json, math, sys, tempfile, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import index_rrg as IR
import transition_rrg as TR


def market(weeks=1000, seed=7):
    """Four correlated weekly series (a market factor and a style factor) since 2000, as rrg.json holds them."""
    rng = np.random.default_rng(seed)
    f = rng.normal(0.0015, 0.022, weeks)
    style = np.cumsum(rng.normal(0, 0.004, weeks)) * 0.05 + rng.normal(0, 0.006, weeks)
    beta = np.array([1.25, 1.0, 1.15, 0.9]); tilt = np.array([1.0, 0.0, -0.6, -0.8])
    R = beta[:, None] * f[None, :] + tilt[:, None] * style[None, :] + rng.normal(0, 0.008, (4, weeks))
    P = 100 * np.exp(np.cumsum(R, 1))
    return P


def write_public(root, P):
    pub = root / 'public'; pub.mkdir(parents=True)
    start = dt.date(2000, 1, 7)
    W = P.shape[1]
    ser = lambda i: [round(float(v), 4) for v in P[i]]
    doc = {'start': start.isoformat(), 'weeks': (start + dt.timedelta(days=7 * (W - 1))).isoformat(), 'benchmark': 'SPY',
           'bench': {'id': 'SPY', 'start': start.isoformat(), 'c': ser(1)},
           'series': [{'id': t, 'name': t, 'group': 'style-etf', 'start': start.isoformat(), 'c': ser(i)} for i, t in enumerate(IR.TICKERS) if t != 'SPY']}
    (pub / 'rrg.json').write_text(json.dumps(doc))
    mac = root / 'cache' / 'macro'; mac.mkdir(parents=True)
    lines = ['observation_date,DGS3MO'] + [f'{(dt.date(1999, 12, 1) + dt.timedelta(days=d)).isoformat()},{2 + math.sin(d / 400):.2f}' for d in range(0, 7 * W + 60)]
    (mac / 'DGS3MO.csv').write_text('\n'.join(lines))
    return pub


class Centre(unittest.TestCase):
    def test_weights_are_known_when_the_week_starts_and_the_relative_moves_add_to_zero(self):
        P = market(300)
        R = IR.log_returns(P)
        W = IR.vol_weights(R)
        t = 150
        self.assertAlmostEqual(W[:, t].sum(), 1.0)
        R2 = R.copy(); R2[:, t:] = np.random.default_rng(1).normal(0, 0.1, R2[:, t:].shape)   # week t on changed
        self.assertTrue(np.allclose(IR.vol_weights(R2)[:, t], W[:, t]))
        rc, _ = IR.centre_returns(R, np.zeros(R.shape[1]))
        rel = R[:, t] - rc['vol'][t]
        self.assertAlmostEqual(float((W[:, t] * rel).sum()), 0.0, places=12)
        self.assertGreater(W[2, t], 0); self.assertLess(W[0, t], W[3, t])                  # the most volatile weighs least

    def test_cash_uses_the_rate_known_before_the_week(self):
        days = np.datetime64('2020-01-03') + 7 * np.arange(5)
        rates = [(np.datetime64('2019-12-30'), 2.0), (np.datetime64('2020-01-08'), 10.0)]
        r = IR.cash_returns(days, rates)
        self.assertAlmostEqual(r[1], math.log(1.02) * 7 / 365.25)                          # the week to Jan 10: 2%
        self.assertAlmostEqual(r[2], math.log(1.10) * 7 / 365.25)
        self.assertTrue(np.isnan(r[0]))

    def test_levels_and_relative(self):
        lv = IR.level(np.array([np.nan, 0.1, np.nan, -0.1]))
        self.assertTrue(np.isnan(lv[0]))
        self.assertEqual((lv[1], lv[2]), (100.0, 100.0))                                   # the base, then carried
        self.assertAlmostEqual(lv[3], 100 * math.exp(-0.1))
        self.assertEqual(IR.relative(np.array([[50.0, 60.0]]), np.array([100.0, 120.0])).tolist(), [[50.0, 50.0]])


class Pieces(unittest.TestCase):
    def test_labels_count_overlapping_origins_as_fewer(self):
        ev = {'origins': 600, 'predictions': 2400, 'brier_skill_vs_stay': [0.05, 0.02, 0.08], 'brier_skill_vs_freq': [0.04, 0.01, 0.07], 'ece': 0.01}
        self.assertEqual(IR.labelled(ev, 4), 'calibrated')
        self.assertEqual(IR.labelled(ev, 13), 'insufficient_data')                       # 600 / 13 < 50 independent origins
        self.assertEqual(IR.labelled({**ev, 'brier_skill_vs_stay': [-0.01, -0.03, 0.01]}, 4), 'descriptive_only')
        self.assertEqual(IR.labelled({**ev, 'ece': 0.05}, 4), 'experimental')
        s = IR.block_skill([1.0] * 40, [2.0] * 40, 4)
        self.assertEqual(s[0], 0.5)

    def test_leader_matrix_uses_only_known_outcomes(self):
        rng = np.random.default_rng(3)
        X = 100 + rng.normal(0, 1, (4, 400))
        st, ld = IR.leader_states(X)
        self.assertTrue((st >= 0).all() and (ld >= 0).all())
        IR.FIT0 = 0
        A = IR.leader_matrix(st, ld, 200, 4)[0]
        st2, ld2 = st.copy(), ld.copy(); st2[201:] = 0; ld2[201:] = 3                      # everything after week 200 changed
        self.assertTrue(np.allclose(IR.leader_matrix(st2, ld2, 200, 4)[0], A))

    def test_routes_start_where_the_index_stands(self):
        P1 = np.full((16, 16), 1 / 16)
        r = IR.chain_paths(P1, 4 * 2 + 1, n=4000)
        self.assertTrue(all(p[0][0] == 1 for p in r))
        self.assertTrue(all(all(a != b for a, b in zip(p[0], p[0][1:])) for p in r))       # a stay is one step
        self.assertLessEqual(sum(p[1] for p in r), 1.0)


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        cls.P = market()
        cls.pub = write_public(cls.root, cls.P)
        cls.doc = IR.build(cls.pub, verbose=False)

    def test_the_file(self):
        d = self.doc
        self.assertIn(d['centre'], IR.CENTRES)
        self.assertIn(d['replay'], ('plain', 'vol'))
        self.assertEqual(set(d['compare']), set(IR.CENTRES))
        self.assertEqual(d['compare']['spy']['lines'], 3)                                   # SPY against itself: no line
        for t in IR.TICKERS:
            r = d['now'][t]
            f = r['fan']
            self.assertTrue(all(a <= b <= c <= e <= g for a, b, c, e, g in zip(f['q10'], f['q25'], f['q50'], f['q75'], f['q90'])))
            if 'odds' in r:
                for h in ('1', '4', '13'):
                    self.assertAlmostEqual(sum(r['odds'][h]), 1.0, places=3)
        self.assertTrue((self.pub / 'index-rrg.json').exists())
        for k in ('q',):
            for h in ('1', '4', '13'):
                self.assertIn(d['model']['heads'][k][h]['label'], ('calibrated', 'experimental', 'descriptive_only', 'insufficient_data'))

    def test_next_week_closes_put_it_on_the_line(self):
        d = self.doc
        days, P = IR.load_prices(self.pub)
        R = IR.log_returns(P)
        cash = IR.cash_returns(days, IR.bill_rates(self.root / 'cache' / 'macro'))
        rc, Wv = IR.centre_returns(R, cash)
        L = IR.level(rc[d['centre']])
        RS = IR.relative(P, L)
        S = TR.rrg_states(RS, IR.N_RRG)
        o = len(days) - 1
        for i, t in enumerate(IR.TICKERS):
            nw = d['now'][t].get('next_week')
            if not nw or nw['x100'] is None:
                continue
            r = math.log(nw['x100'] / P[i, o])
            x, _ = IR.step_one(S, RS, o, i, (1 - nw['own_weight']) * r)
            self.assertAlmostEqual(x, 100.0, delta=0.02)
            qs = [q for q, _, _ in nw['ranges']]
            self.assertEqual(len(qs), len(set(qs)))

    def test_the_ledger_freezes_once(self):
        root = self.root
        out = IR.ledger_update(root, '2026-10-25T00:00:00+00:00', 'abc')
        self.assertEqual(out['origins'], 1)
        L = json.loads((root / 'ledger' / 'index.json').read_text())
        first = L['origins'][0]['rows']
        IR.ledger_update(root, '2026-10-26T00:00:00+00:00', 'def')
        L2 = json.loads((root / 'ledger' / 'index.json').read_text())
        self.assertEqual(len(L2['origins']), 1)
        self.assertEqual(L2['origins'][0]['rows'], first)
        self.assertEqual(L2['origins'][0]['code'], 'abc')
        self.assertTrue((root / 'public' / 'index-ledger.json').exists())


if __name__ == '__main__':
    unittest.main()
