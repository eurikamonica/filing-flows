"""Moving averages+ (app/ma_hybrid.py) on a synthetic world: first-filed quarters count only after their filing, per-share
figures follow the price file's splits, the earnings line sits on the price at a constant P/E, the hybrid line's weights,
guidance windows, no look-ahead, a planted trend is found, and the published files and the ledger."""
import datetime as dt
import gzip
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import forecast_book as FB  # noqa: E402
import ma_hybrid as MA  # noqa: E402

START = dt.date(2006, 1, 6)                       # a Friday
END = dt.date(2026, 10, 30)
W = (END - START).days // 7 + 1
SPLIT_WEEK = 700                                  # company C000 splits 2:1 in the week of 2019-05-31


def week(k):
    return START + dt.timedelta(days=7 * k)


def next_quarter_end(d):
    m = d.month + 3
    y, m = d.year + (m - 1) // 12, (m - 1) % 12 + 1
    first_after = dt.date(y + (m == 12), m % 12 + 1, 1)
    return first_after - dt.timedelta(days=1)


def write_world(root, n=90, seed=7, drift=0.003, guide=True):
    """rrg.json + t/<T>.json (closes, volume, splits), eps-fundamental/<cik>.json (quarters as first filed, 35 days
    after each quarter's end, EPS at a P/E near 20), guidance/<cik>.json.gz (releases from 2023) for every other company."""
    rng = np.random.default_rng(seed)
    root = Path(root)
    pub, fund, gd = root / 'public', root / 'fund', root / 'guide'
    for p in (pub / 't', fund, gd):
        p.mkdir(parents=True)
    spy_r = rng.normal(0.0015, 0.02, W)
    spy = 100 * np.exp(np.cumsum(spy_r))
    tickers = {}
    for i in range(n):
        t, cik = f'C{i:03d}', 1000 + i
        mu, level = np.zeros(W), 0.0
        for k in range(W):                                   # each company's drift against SPY wanders: the trend pays
            if k % 26 == 0:
                level = 0.6 * level + rng.normal(0, drift)
            mu[k] = level
        p = 50 * np.exp(np.cumsum(spy_r + mu + rng.normal(0, 0.03, W)))
        tickers[t] = {'n': f'Company {i}', 's': 'technology'}
        sp = [[SPLIT_WEEK, 2.0]] if i == 0 else []
        (pub / 't' / f'{t}.json').write_text(json.dumps({'t': t, 'start': START.isoformat(), 'c': [round(float(x), 4) for x in p],
                                                         'p': [round(float(x), 4) for x in p], 'v': [1000.0] * W, 'sp': sp}))
        quarters = []
        end = dt.date(2008, 3, 31)
        while end <= dt.date(2026, 9, 30):
            k = min(W - 1, max(0, (end - START).days // 7))
            filed = end + dt.timedelta(days=35)
            eps = float(p[k] / 20 / 4 * math.exp(rng.normal(0, 0.05)))      # on the price file's (latest) basis
            shares = 1e8
            if i == 0 and filed < week(SPLIT_WEEK):                          # before the split: twice the EPS, half the shares
                eps, shares = eps * 2, shares / 2
            quarters.append({'end': end.isoformat(), 'fields': {'eps': {'val': eps, 'filed': filed.isoformat()},
                             'revenue': {'val': eps * shares * 5, 'filed': filed.isoformat()},
                             'diluted_shares': {'val': shares, 'filed': filed.isoformat()}}})
            end = next_quarter_end(end)
        (fund / f'{cik}.json').write_text(json.dumps({'cik': cik, 'ticker': t, 'quarters': quarters}))
        if guide and i % 2 == 0:
            rel = [{'filed': (dt.date(2023, 2, 1) + dt.timedelta(days=91 * j)).isoformat(), 'label': ['raised', 'reaffirmed', 'lowered'][(i + j) % 3]}
                   for j in range(15)]
            with gzip.open(gd / f'{cik}.json.gz', 'wt') as f:
                json.dump({'cik': cik, 'releases': rel}, f)
    (pub / 'rrg.json').write_text(json.dumps({'start': START.isoformat(), 'weeks': END.isoformat(), 'benchmark': 'SPY',
                                              'bench': {'start': START.isoformat(), 'c': [round(float(x), 4) for x in spy]}, 'series': [], 'tickers': tickers}))
    return pub, fund, gd


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pub, cls.fund, cls.gd = write_world(cls.tmp)
        cls.today = END + dt.timedelta(days=3)
        cls.ledger = Path(cls.tmp) / 'ledger.json'
        cls.doc = MA.build(cls.pub, cls.fund, cls.gd, cls.ledger, today=cls.today, verbose=False, force=True)
        cls.A = MA.load(cls.pub, cls.fund, cls.gd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestInputs(World):
    def test_a_quarter_counts_after_its_filing(self):
        A = self.A
        i = A['ids'].index('C005')
        q = json.loads((self.fund / '1005.json').read_text())['quarters']
        filed = dt.date.fromisoformat(q[10]['fields']['eps']['filed'])
        days = [dt.date.fromisoformat(str(d)) for d in A['days']]
        k = next(j for j, d in enumerate(days) if d > filed)            # the first Friday after the filing
        before, after = A['EPS'][i, k - 1], A['EPS'][i, k]
        ttm = sum(x['fields']['eps']['val'] for x in q[7:11])
        self.assertAlmostEqual(after, ttm, places=6)
        self.assertNotAlmostEqual(before, ttm, places=6)

    def test_split_restates_the_eps(self):
        A = self.A
        i = A['ids'].index('C000')
        k = SPLIT_WEEK
        pe = A['P'][i] / A['EPS'][i]
        before, after = np.nanmedian(pe[k - 60:k - 10]), np.nanmedian(pe[k + 30:k + 80])
        self.assertTrue(14 < before < 28 and 14 < after < 28, (before, after))   # a P/E near 20 on both sides of the split
        # without the restatement the quarters filed before the split would halve the P/E there
        q = json.loads((self.fund / '1000.json').read_text())['quarters']
        dnum = A['days'].astype('datetime64[D]').astype(np.int64)
        raw_eps, _, _ = MA.company_fundamentals(q, [], dnum)
        self.assertLess(np.nanmedian(A['P'][i, k - 60:k - 10] / raw_eps[k - 60:k - 10]), 12)

    def test_earnings_line_on_the_price_at_its_usual_pe(self):
        A = self.A
        L = MA.lines(A['P'], A['EPS'])
        t = len(A['days']) - 1
        r = L['el'][:, t] / A['P'][:, t]
        r = r[np.isfinite(r)]
        self.assertGreater(len(r), 50)
        self.assertLess(abs(np.median(np.log(r))), 0.25)                 # a P/E near 20 all along: the line sits near the price

    def test_hybrid_line_weights(self):
        A = self.A
        L = MA.lines(A['P'], A['EPS'])
        G = np.zeros_like(A['G'])
        l0, l1 = MA.hybrid_log(L, 0, 0, G), MA.hybrid_log(L, 1, 0, G)
        m = np.isfinite(L['el']) & np.isfinite(L['ma40'])
        np.testing.assert_allclose(l0[m], np.log(L['ma40'][m]))
        np.testing.assert_allclose(l1[m], np.log(L['el'][m]))
        no_el = ~np.isfinite(L['el']) & np.isfinite(L['ma40'])
        np.testing.assert_allclose(l1[no_el], np.log(L['ma40'][no_el]))   # no earnings line: the 40-week average
        up = MA.hybrid_log(L, 0.5, 0.1, np.ones_like(G)) - MA.hybrid_log(L, 0.5, 0, G)
        self.assertAlmostEqual(float(np.nanmax(np.abs(up[m] - math.log(1.1)))), 0, places=9)

    def test_guidance_window(self):
        A = self.A
        i = A['ids'].index('C002')
        days = [dt.date.fromisoformat(str(d)) for d in A['days']]
        k = next(j for j, d in enumerate(days) if d > dt.date(2023, 2, 1))
        first = ['raised', 'reaffirmed', 'lowered'][(2 + 0) % 3]           # C002's first release (write_world)
        self.assertEqual(A['G'][i, k], MA.LAB[first])
        self.assertTrue(np.all(A['G'][i, k:k + MA.GUIDE_WEEKS - 1] == A['G'][i, k]))
        self.assertTrue(np.isnan(A['G'][i, k - 1]))
        self.assertTrue(np.all(np.isnan(A['G'][A['ids'].index('C001')])))   # no releases: no guidance

    def test_no_look_ahead(self):
        tmp = tempfile.mkdtemp()
        try:
            pub, fund, gd = write_world(tmp, n=70, seed=3)
            A = MA.load(pub, fund, gd)
            cut = int(np.searchsorted(A['days'], np.datetime64('2018-01-05')))
            B = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in A.items()}
            noise = np.exp(np.random.default_rng(5).normal(0, 0.2, B['P'][:, cut:].shape))
            B['P'][:, cut:] *= noise
            B['C'][:, cut:] *= noise
            outs = []
            for X in (A, B):
                L = MA.lines(X['P'], X['EPS'])
                raw, Z, ok = MA.inputs(X, L)
                Ydm = MA.HY.demean(MA.HY.fwd_sum(np.diff(np.log(X['C']), axis=1, prepend=np.nan) - np.diff(np.log(X['spy']), prepend=np.nan)[None], 26), ok)
                F, _ = MA.walk_forward(X['days'], Z, ok, Ydm, MA.MODELS['hybrid'], 26)
                outs.append((raw, L, F))
            k = cut - 40                                                     # a 2017 week: its inputs, and fits on years before it
            for name in ('tr40', 'tr10_40', 'val'):
                np.testing.assert_array_equal(outs[0][0][name][:, k], outs[1][0][name][:, k])
            np.testing.assert_array_equal(outs[0][1]['el'][:, k], outs[1][1]['el'][:, k])
            np.testing.assert_allclose(outs[0][2][:, k], outs[1][2][:, k])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBuild(World):
    def test_files(self):
        d = json.loads((self.pub / 'ma-hybrid.json').read_text())
        self.assertEqual(d['asof'], END.isoformat())
        self.assertEqual(set(d['scores']['models']), {'13', '26'})
        self.assertEqual(len(d['scores']['lines']['26']), len(MA.WS) * len(MA.GS))
        rows = json.loads((self.pub / 'ma-hybrid-rows.json').read_text())['rows']
        self.assertGreater(len(rows), 50)
        s = json.loads((self.pub / 'ma' / f"{rows[0]['id']}.json").read_text())
        self.assertEqual(len(s['p']), MA.SERIES_WEEKS)
        self.assertEqual(len(s['ma40']), len(s['el']))
        self.assertIn('pct_hybrid', s['now'])
        self.assertIn('raised', d['scores']['guidance_events']['13'])

    def test_planted_trend_is_found(self):
        m = self.doc['scores']['models']['26']['ma']
        first = list(m)[0]
        self.assertGreater(m[first]['ic']['mean'], 0.02)                   # drifts persist: the averages rank them
        r = self.doc['scores']['rules']['26']['above40'][first]['gross']
        self.assertGreater(r['mean'], 0)

    def test_ledger_freezes_and_resolves(self):
        tmp = tempfile.mkdtemp()
        try:
            led = Path(tmp) / 'l.json'
            early = END - dt.timedelta(days=7 * 27) + dt.timedelta(days=3)
            MA.build(self.pub, self.fund, self.gd, led, today=early, verbose=False, force=True)
            MA.build(self.pub, self.fund, self.gd, led, today=self.today, verbose=False, force=True)
            b = FB.load(led)
            for h in MA.HORIZONS:
                done = FB.entries(b, f'ma:{h}', resolved=True)
                self.assertEqual(len(done), 1, h)
                self.assertEqual(len(done[0][1]['actual']['rel']), len(done[0][1]['forecast']['ids']))
            sc = MA.ledger_scores(b)
            self.assertIsNotNone(sc['ma:26']['ic'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_skips_a_week_already_built(self):
        self.assertIsNone(MA.build(self.pub, self.fund, self.gd, None, today=self.today, verbose=False))
        self.assertTrue(MA.fresh(self.pub, END.isoformat()))


if __name__ == '__main__':
    unittest.main()
