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


def write_extras(root, n=90):
    """A Fair value index (research-valuation public/index.json) for the even companies, and MD&A tone records
    (data branch outlook/<cik>.json) for every third company, filed through 2024–2026."""
    root = Path(root)
    F = ['cik', 'ticker', 'kind', 'price', 'dcf_value', 'mc_p10', 'mc_p90', 'mc_p_above', 'p_implied']
    rows = [[1000 + i, f'C{i:03d}', 'operating', 50.0, 60.0 + i, 40.0, 90.0, 0.6, 0.35] for i in range(0, n, 2)]
    (root / 'valindex.json').write_text(json.dumps({'fields': F, 'rows': rows}))
    (root / 'outlook').mkdir()
    for i in range(0, n, 3):
        docs = [{'kind': 'mdna', 'form': '10-Q', 'filed': (dt.date(2024, 5, 1) + dt.timedelta(days=91 * j)).isoformat(),
                 'counts': {'n': 6, 'positive': 3, 'negative': j % 3, 'hedged': 1, 'tone': round((3 - j % 3) / 6 - 0.2 * (i % 2), 3)}} for j in range(9)]
        docs.append({'kind': 'release', 'form': '8-K', 'filed': '2026-10-01', 'counts': {'n': 4, 'tone': 1.0}})   # not an MD&A
        (root / 'outlook' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'docs': docs}))
    return root / 'valindex.json', root / 'outlook'


class TestBuild(World):
    def test_valuation_odds_and_mdna_are_shown_and_frozen(self):
        tmp = tempfile.mkdtemp()
        try:
            vi, ol = write_extras(tmp)
            led = Path(tmp) / 'l.json'
            pub = Path(tmp) / 'pub'
            shutil.copytree(self.pub, pub)
            doc = MA.build(pub, self.fund, self.gd, led, today=self.today, verbose=False, force=True, valuation=vi, outlook=ol)
            rows = {r['id']: r for r in json.loads((pub / 'ma-hybrid-rows.json').read_text())['rows']}
            r0 = rows.get('C000') or next(v for k, v in rows.items() if int(k[1:]) % 2 == 0)
            self.assertAlmostEqual(r0['val']['dcf_value'], 60.0 + int(r0['id'][1:]))
            self.assertAlmostEqual(r0['val']['dcf_gap_now'], math.log(r0['close'] / r0['val']['dcf_value']), places=3)
            odd = next(v for k, v in rows.items() if int(k[1:]) % 2 == 1)
            self.assertIsNone(odd['val'])                                    # not in the index: nothing made up
            m = next(v for k, v in rows.items() if int(k[1:]) % 3 == 0)
            self.assertEqual(m['mdna']['filed'], (dt.date(2024, 5, 1) + dt.timedelta(days=91 * 8)).isoformat())   # the latest MD&A
            s = json.loads((pub / 'ma' / f"{r0['id']}.json").read_text())
            self.assertEqual(s['now']['val']['dcf_value'], r0['val']['dcf_value'])
            e = list(FB.load(led)['families']['ma:26'].values())[0]['forecast']
            for k in ('dcf_gap', 'p_above', 'p_implied', 'mdna_tone'):
                self.assertEqual(len(e[k]), len(e['ids']))
            self.assertTrue(any(v is not None for v in e['dcf_gap']) and any(v is None for v in e['dcf_gap']))
            ev = doc['scores']['mdna_events']
            self.assertEqual(ev['filings'], len(range(0, 90, 3)) * 9)       # the 8-K release is not counted
            self.assertTrue(ev['13'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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

    def test_no_macro_or_bars_no_new_parts(self):
        d = json.loads((self.pub / 'ma-hybrid.json').read_text())
        self.assertIsNone(d['scores']['macro'])                             # no macro.json: no macro tests, no macro model
        self.assertNotIn('ma_macro', d['scores']['models']['26'])
        self.assertIsNone(d['scores']['ndays']['daily'])                    # no daily bars: the weekly form only
        self.assertIn('above:200', d['scores']['ndays']['weekly']['26'])
        self.assertFalse((self.pub / 'ma-daily').exists() and any((self.pub / 'ma-daily').iterdir()))


# ------------------------------------------------------------------ daily bars and the macro
def write_bars(folder, pub, ids, start=dt.date(2016, 10, 17), fetched='2026-10-31T03:00:00+00:00', seed=11, recent=40):
    """research-paths' daily bars (cache/ohlc/<T>.json.gz + <T>.base.json.gz) made from each company's weekly closes:
    every Friday's close is the week's, Monday to Thursday lie between the two Fridays (a little noise)."""
    rng = np.random.default_rng(seed)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in ids:
        d = json.loads((Path(pub) / 't' / f'{t}.json').read_text())
        p, s0 = d['p'], dt.date.fromisoformat(d['start'])
        ts, cs = [], []
        for k in range(1, len(p)):
            fri = s0 + dt.timedelta(days=7 * k)
            for j in range(5):
                day_ = fri - dt.timedelta(days=4 - j)
                if day_ < start:
                    continue
                f = (j + 1) / 5
                v = p[k] if j == 4 else math.exp((1 - f) * math.log(p[k - 1]) + f * math.log(p[k]) + rng.normal(0, 0.004))
                ts.append(day_.isoformat())
                cs.append(round(float(v), 4))
        cut = len(ts) - recent
        with gzip.open(folder / f'{t}.base.json.gz', 'wt') as fh:
            json.dump({'t': ts[:cut], 'c': cs[:cut]}, fh)
        with gzip.open(folder / f'{t}.json.gz', 'wt') as fh:
            json.dump({'ticker': t, 'source': 'yahoo', 'fetched_at': fetched, 'base': True, 't': ts[cut:], 'c': cs[cut:]}, fh)
        out[t] = (ts, cs)
    return out


def macro_value(k, i):
    return {'vix': 18 + 6 * math.sin(i / 7), 'credit': 2.2 + 0.6 * math.sin(i / 11), 'dcredit': 0.3 * math.sin(i / 3), 'curve': 1 + math.sin(i / 17),
            'dy10': 0.3 * math.cos(i / 4), 'claims': 10 * math.sin(i / 9), 'sahm': max(0.0, 0.6 * math.sin(i / 20)), 'usd13': 2 * math.sin(i / 5),
            'oil13': 10 * math.sin(i / 6), 'nfci': -0.4 + 0.3 * math.sin(i / 13), 'cpi': 2.5 + math.sin(i / 15), 'ff': 2 + 1.5 * math.sin(i / 25),
            'unrate': 5 + 1.2 * math.sin(i / 30)}[k]


def write_macro(pub):
    """public/macro.json: month-end values from 2005 and the weekly block from 2009-01-02, every reading the page uses."""
    months = [f'{y}-{m:02d}' for y in range(2005, 2027) for m in range(1, 13) if (y, m) <= (2026, 10)]
    keys = list(MA.MACRO_READINGS) + ['unrate']
    monthly = {'months': months, 'data': {k: [round(macro_value(k, i), 4) for i in range(len(months))] for k in keys}}
    w0 = dt.date(2009, 1, 2)
    weekly = {'start': w0.isoformat(), 'grid_index0': (w0 - START).days // 7, 'data': {k: [] for k in keys}}
    for j in range((END - w0).days // 7 + 1):
        d = w0 + dt.timedelta(days=7 * j)
        i = months.index(f'{d.year}-{d.month:02d}') - 1                  # the month before: what is known by then
        for k in keys:
            weekly['data'][k].append(monthly['data'][k][i])
    feats = [{'key': k, 'label': k.upper(), 'unit': '%'} for k in keys]
    (Path(pub) / 'macro.json').write_text(json.dumps({'generated_at': '2026-11-01T00:00:00+00:00', 'features': feats, 'weekly': weekly, 'monthly': monthly}))


class DailyMacroWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pub, cls.fund, cls.gd = write_world(cls.tmp, n=80, seed=9)
        D = json.loads((cls.pub / 'rrg.json').read_text())                # a second fund beside SPY for the fund rules
        D['series'] = [{'id': 'QQQ', 'start': START.isoformat(), 'c': [round(v * 1.3, 4) for v in D['bench']['c']]}]
        (cls.pub / 'rrg.json').write_text(json.dumps(D))
        write_macro(cls.pub)
        cls.bars = Path(cls.tmp) / 'ohlc'
        ids = [f'C{i:03d}' for i in range(80) if i % 8]                     # every eighth company has no daily bars
        cls.written = write_bars(cls.bars, cls.pub, ids)
        cls.today = END + dt.timedelta(days=3)
        cls.ledger = Path(cls.tmp) / 'ledger.json'
        cls.doc = MA.build(cls.pub, cls.fund, cls.gd, cls.ledger, today=cls.today, verbose=False, force=True, bars=cls.bars, bars_sha='sha-1')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestDaily(DailyMacroWorld):
    def test_sma(self):
        x = np.random.default_rng(1).lognormal(0, 0.1, 300)
        for n in (1, 5, 50, 250):
            a = MA.sma(x, n)
            self.assertTrue(np.all(np.isnan(a[:n - 1])))
            np.testing.assert_allclose(a[n - 1:], [x[i - n + 1:i + 1].mean() for i in range(n - 1, len(x))])

    def test_bars_join_their_base_and_an_unfinished_day_is_dropped(self):
        ts, cs = self.written['C001']
        dn, cl = MA.load_daily(self.bars, ['C001'])['C001']
        self.assertEqual(len(dn), len(ts))                                   # base + recent part, in order
        self.assertEqual(str(np.datetime64(int(dn[-1]), 'D')), ts[-1])
        self.assertAlmostEqual(cl[0], cs[0])
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(self.bars / 'C001.base.json.gz', tmp / 'C001.base.json.gz')
            rec = MA.read_gz(self.bars / 'C001.json.gz')
            for when, n in (((ts[-1] + 'T15:00:00+00:00'), len(ts) - 1), ((ts[-1] + 'T22:00:00+00:00'), len(ts))):
                with gzip.open(tmp / 'C001.json.gz', 'wt') as fh:
                    json.dump(dict(rec, fetched_at=when), fh)
                self.assertEqual(len(MA.load_daily(tmp, ['C001'])['C001'][0]), n, when)   # before 21:15 UTC: not a close yet
            (tmp / 'C001.base.json.gz').unlink()
            self.assertNotIn('C001', MA.load_daily(tmp, ['C001']))           # the recent part alone is not used
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_daily_signals_use_no_later_day(self):
        days = MA.grid(self.pub)[3]
        dn, cl = MA.load_daily(self.bars, ['C001'])['C001']
        g = MA.daily_on_grid({'C001': (dn, cl)}, ['C001'], days)
        t = int(np.searchsorted(days, np.datetime64('2024-03-01')))
        j = int(np.searchsorted(dn, days[t].astype('datetime64[D]').astype(np.int64), side='right')) - 1
        self.assertAlmostEqual(g['above:50'][0, t], math.log(cl[j] / cl[j - 49:j + 1].mean()), places=12)
        self.assertAlmostEqual(g['cross:50/200'][0, t], math.log(cl[j - 49:j + 1].mean() / cl[j - 199:j + 1].mean()), places=12)
        cl2 = cl.copy()
        cl2[j + 1:] *= 3.0                                                   # every later day changed
        g2 = MA.daily_on_grid({'C001': (dn, cl2)}, ['C001'], days)
        np.testing.assert_array_equal(g['above:20'][0, :t + 1], g2['above:20'][0, :t + 1])
        keep = np.ones(len(dn), bool)                                        # a week with no bar: no signal that Friday
        keep[(dn > dn[j] - 7) & (dn <= dn[j])] = False
        g3 = MA.daily_on_grid({'C001': (dn[keep], cl[keep])}, ['C001'], days)
        self.assertTrue(np.isnan(g3['above:5'][0, t]))

    def test_the_latest_cross(self):
        dn = np.arange(400, dtype=np.int64) + 19000
        cl = np.r_[np.linspace(100, 60, 260), np.linspace(60, 130, 140)]
        now = MA.daily_now(dn, cl)
        self.assertEqual(now['up50_200'], 1)
        k = np.where(np.diff(np.sign(MA.sma(cl, 50) - MA.sma(cl, 200))) > 0)[0][-1] + 1
        self.assertEqual(now['x50_200'], [str(np.datetime64(int(dn[k]), 'D')), 1, int(len(cl) - 1 - k)])
        self.assertAlmostEqual(now['d200'], math.log(cl[-1] / cl[-200:].mean()), places=4)

    def test_daily_files_rows_and_scores(self):
        rows = json.loads((self.pub / 'ma-hybrid-rows.json').read_text())
        self.assertEqual(rows['bars_sha'], 'sha-1')
        with_bars = [r for r in rows['rows'] if r['d_asof']]
        self.assertTrue(with_bars and len(with_bars) < len(rows['rows']))   # the companies without bars get no daily numbers
        r = with_bars[0]
        f = json.loads((self.pub / 'ma-daily' / f"{r['id']}.json").read_text())
        ts, cs = self.written[r['id']]
        dates = [dt.date.fromisoformat(f['start'])]
        for g in f['gap']:
            dates.append(dates[-1] + dt.timedelta(days=g))
        self.assertEqual([d.isoformat() for d in dates], ts[-MA.DAILY_ROWS:])
        np.testing.assert_allclose(f['p'], cs[-MA.DAILY_ROWS:], rtol=1e-4)
        self.assertFalse((self.pub / 'ma-daily' / 'C000.json').exists())   # no bars, no file
        nd = self.doc['scores']['ndays']
        self.assertNotIn('above:5', nd['weekly']['26'])                    # 5 days have no weekly form
        D = nd['daily']
        d250 = dt.date.fromisoformat(ts[MA.NDAYS[-1] - 1])                   # the first Friday with 250 bars behind it
        self.assertEqual(D['from'], (d250 + dt.timedelta(days=(4 - d250.weekday()) % 7)).isoformat())
        self.assertIn('above:5', D['26'])
        self.assertIsNone(D['26']['above:5']['weekly_form'])
        self.assertIsNotNone(D['26']['above:20']['weekly_form'])
        self.assertTrue(D['26']['above:200']['periods'][D['periods'][0]]['net'])

    def test_daily_mode_refreshes_only_the_daily_part(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            pub, bars = tmp / 'pub', tmp / 'ohlc'
            shutil.copytree(self.pub, pub)
            shutil.copytree(self.bars, bars)
            before = (pub / 'ma-hybrid.json').read_bytes()
            rec = MA.read_gz(bars / 'C001.json.gz')                           # a new day for one company
            nxt = (dt.date.fromisoformat(rec['t'][-1]) + dt.timedelta(days=3)).isoformat()
            rec['t'].append(nxt)
            rec['c'].append(rec['c'][-1] * 1.05)
            with gzip.open(bars / 'C001.json.gz', 'wt') as fh:
                json.dump(rec, fh)
            self.assertFalse(MA.daily_needed(pub, 'sha-1'))
            self.assertTrue(MA.daily_needed(pub, 'sha-2'))
            MA.build_daily(pub, bars, 'sha-2', verbose=False)
            self.assertEqual((pub / 'ma-hybrid.json').read_bytes(), before)  # the weekly numbers are left alone
            R = json.loads((pub / 'ma-hybrid-rows.json').read_text())
            row = next(r for r in R['rows'] if r['id'] == 'C001')
            self.assertEqual((row['d_asof'], R['daily_asof'], R['bars_sha']), (nxt, nxt, 'sha-2'))
            self.assertEqual(json.loads((pub / 'ma-daily' / 'C001.json').read_text())['asof'], nxt)
            self.assertFalse(MA.daily_needed(pub, 'sha-2'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMacro(DailyMacroWorld):
    def test_macro_known_only_after_its_month(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            months = [f'2008-{m:02d}' for m in range(1, 7)]
            (tmp / 'macro.json').write_text(json.dumps({'monthly': {'months': months, 'data': {'x': list(range(6))}},
                                                        'weekly': {'start': '2009-01-02', 'data': {'x': [1000 + j for j in range(30)]}}}))
            days = np.datetime64('2008-01-04') + 7 * np.arange(80)
            x = MA.macro_load(tmp, days)['x']['x']
            at = lambda d: x[int(np.searchsorted(days, np.datetime64(d)))]
            self.assertTrue(np.isnan(at('2008-01-04')))                      # no month before it
            self.assertEqual(at('2008-02-01'), 0)                            # January's value, from the first Friday after its end
            self.assertEqual(at('2008-02-29'), 0)                            # February's end day itself: still January's
            self.assertEqual(at('2008-03-07'), 1)
            self.assertEqual(at('2008-08-08'), 5)                            # June's, 39 days on
            self.assertTrue(np.isnan(at('2008-08-15')))                      # 46 days: not carried further
            self.assertEqual(at('2009-01-02'), 1000)                         # the weekly block from its first Friday
            self.assertEqual(at('2009-01-30'), 1004)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_thirds_and_z_from_the_past_only(self):
        x = np.random.default_rng(4).normal(0, 1, 400)
        third, cut, z = MA.expanding(x, 156)
        self.assertTrue(np.all(third[:156] == -1))
        t = 300
        np.testing.assert_allclose(cut[t], np.quantile(x[:t], [1 / 3, 2 / 3]))
        self.assertAlmostEqual(z[t], float(np.clip((x[t] - x[:t].mean()) / x[:t].std(), -3, 3)))
        y = x.copy()
        y[t + 1:] += 5
        t2, c2, z2 = MA.expanding(y, 156)
        np.testing.assert_array_equal(third[:t + 1], t2[:t + 1])
        np.testing.assert_allclose(z[:t + 1], z2[:t + 1])

    def test_unemployment_flags(self):
        un = np.r_[np.full(100, 4.0), 4.0 + 0.1 * np.arange(1, 11), np.full(40, 5.0)]
        f = MA.macro_flags({'x': {'unrate': un}})
        self.assertFalse(f['unemp_up'][99])                                  # flat: not above its 12-month average
        self.assertTrue(f['unemp_up'][105])                                  # rising: above it
        self.assertFalse(f['sahm_on'][99])
        self.assertTrue(f['sahm_on'][120])                                   # the 3-month average 1 point above its 12-month low
        self.assertAlmostEqual(f['sahm3'][149], 1.0)

    def test_fund_rules(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            W = 600
            start = dt.date(1995, 1, 6)
            k = np.arange(W)
            up = 100 * np.exp(0.002 * k)                                     # always above its 40-week average
            crash = up.copy()
            crash[300:330] *= np.exp(-0.02 * np.arange(1, 31))               # a fall, then the old trend from a lower level
            crash[330:] *= math.exp(-0.6)
            D = {'start': start.isoformat(), 'weeks': (start + dt.timedelta(days=7 * (W - 1))).isoformat(), 'benchmark': 'SPY',
                 'bench': {'start': start.isoformat(), 'c': [round(float(v), 6) for v in up]},
                 'series': [{'id': 'QQQ', 'start': start.isoformat(), 'c': [round(float(v), 6) for v in crash]}]}
            (tmp / 'rrg.json').write_text(json.dumps(D))
            days = MA.grid(tmp)[3]
            mac = {'x': {'ff': np.full(W, 2.0)}}
            rising = {'unemp_up': np.ones(W, bool), 'sahm_on': np.zeros(W, bool), 'known': np.ones(W, bool),
                      'unrate': np.full(W, 5.0), 'unrate12': np.full(W, 4.0), 'sahm3': np.zeros(W)}
            I = MA.index_timing(tmp, days, mac, rising, W - 1)
            per = I['periods'][0]
            spy, qqq = I['funds']['SPY']['rules'], I['funds']['QQQ']['rules']
            for r in ('above40', 'trend_unemployment', 'trend_sahm'):         # never below the average: the same as holding
                self.assertAlmostEqual(spy[r][per]['cagr'], spy['hold'][per]['cagr'], places=6)
                self.assertEqual(spy[r][per]['switches'], 0)
            self.assertAlmostEqual(qqq['trend_unemployment'][per]['cagr'], qqq['above40'][per]['cagr'], places=6)   # unemployment up: out
            self.assertAlmostEqual(qqq['trend_sahm'][per]['cagr'], qqq['hold'][per]['cagr'], places=6)              # Sahm off: stays in
            self.assertGreater(qqq['above40'][per]['maxdd'], qqq['hold'][per]['maxdd'])                             # a smaller fall
            # the arithmetic, independently: decided at the close, held the next week, cash at 2% a year, 5 bp a switch
            c = crash
            m40 = np.array([c[i - 39:i + 1].mean() if i >= 39 else np.nan for i in range(W)])
            s0 = int(np.argmax(np.isfinite(m40) & (MA.years_of(days) >= MA.INDEX_FROM)))
            pos = c > np.nan_to_num(m40, nan=np.inf)
            eq, prev = 1.0, None
            for u in range(s0 + 1, W):
                held = pos[u - 1]
                r = c[u] / c[u - 1] - 1 if held else 0.02 / MA.WEEKS_A_YEAR
                if prev is not None and held != prev:
                    r -= MA.SWITCH_BP / 1e4
                prev = held
                eq *= 1 + r
            want = eq ** (MA.WEEKS_A_YEAR / (W - 1 - s0)) - 1
            self.assertAlmostEqual(qqq['above40'][per]['cagr'], want, places=4)
            self.assertEqual(I['funds']['QQQ']['now']['in']['above40'], bool(pos[-1]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_macro_scores_models_and_ledger(self):
        S = self.doc['scores']
        M = S['macro']
        self.assertEqual(set(M['index']['funds']), {'SPY', 'QQQ'})
        self.assertEqual(set(M['index']['funds']['SPY']['rules']), set(MA.INDEX_RULES))
        self.assertEqual(set(M['regimes']['now']), set(MA.MACRO_READINGS))
        self.assertTrue(all(len(v) == 3 for v in M['regimes']['26'].values() if isinstance(v, list)))
        for m in ('ma_macro', 'ma_macro_09'):                                # the macro model and its check
            self.assertIn(m, S['models']['26'])
            self.assertIn(m, S['net_by_year']['26'])
        e = list(FB.load(self.ledger)['families']['ma:26'].values())[0]['forecast']
        self.assertEqual(len(e['s_macro']), len(e['ids']))
        self.assertEqual(set(e['macro']) - {'unemp_up', 'sahm3', 'sahm_on', 'funds'}, set(MA.MACRO_READINGS))
        self.assertEqual(set(e['macro']['funds']['SPY']), set(MA.INDEX_RULES))
        rows = json.loads((self.pub / 'ma-hybrid-rows.json').read_text())['rows']
        self.assertTrue(any(r['pct_macro'] is not None for r in rows))


class TestCalendarAndDistance(DailyMacroWorld):
    def test_own_season_uses_past_years_only(self):
        rng = np.random.default_rng(2)
        rel = rng.normal(0, 0.02, (3, 700))
        S = MA.seasonal(rel, 13)
        Y = MA.HY.fwd_sum(rel, 13)
        t = 600
        want = np.mean([Y[1, t - 52 * k] for k in range(1, 11)])            # the same 13 weeks of the last 10 years
        self.assertAlmostEqual(S[1, t], want, places=12)
        self.assertTrue(np.isnan(S[0, 52 * 3 - 1]) and np.isfinite(S[0, 52 * 3]))   # at least three years of it
        rel2 = rel.copy()
        rel2[:, t + 1:] += 1.0                                                # everything after t changed
        np.testing.assert_array_equal(MA.seasonal(rel2, 13)[:, :t + 1], S[:, :t + 1])

    def test_own_percentile(self):
        X = np.random.default_rng(3).normal(0, 1, (4, 400))
        X[2, :150] = np.nan
        pc = MA.own_pct(X, 0, win=259, need=104)
        for i, t in ((0, 300), (1, 120), (2, 380)):
            past = X[i, max(0, t - 259):t]
            past = past[np.isfinite(past)]
            self.assertAlmostEqual(pc[i, t], ((past < X[i, t]).sum() + 0.5 * (past == X[i, t]).sum()) / len(past))
        self.assertTrue(np.isnan(pc[0, 103]) and np.isfinite(pc[0, 104]))   # 104 earlier weeks at least
        self.assertTrue(np.isnan(pc[2, 200]))                                # only 50 known weeks behind it

    def test_year_angle_and_months(self):
        days = np.array(['2024-01-05', '2024-07-05', '2024-12-27'], dtype='datetime64[D]')
        a = MA.year_angle(days)
        self.assertAlmostEqual(a[0], 2 * np.pi * 4 / 365.25)
        self.assertAlmostEqual(a[1] / (2 * np.pi), 186 / 365.25)
        g = np.datetime64('2010-01-01') + 7 * np.arange(200)                 # Fridays
        c = np.ones(200)
        jan = (g.astype('datetime64[M]').astype(int) % 12) == 0
        steps = np.where(jan, 1.01, 1.0)                                      # every January week +1%, the rest flat
        c = np.cumprod(steps)
        r = MA.month_returns(c, g)
        self.assertAlmostEqual(r['2011-01'], 1.01 ** int(((g.astype('datetime64[M]') == np.datetime64('2011-01')) & jan).sum()) - 1, places=10)
        self.assertAlmostEqual(r['2011-02'], 0.0, places=12)
        m = MA.by_month(r)
        self.assertGreater(m['1']['mean'], 0.03)
        self.assertAlmostEqual(m['6']['mean'], 0.0, places=8)

    def test_sell_in_may_arithmetic(self):
        S = self.doc['scores']['calendar']
        rule = S['sell_in_may']['rule']
        self.assertTrue(rule)
        A = MA.load(self.pub, self.fund, self.gd)
        res = MA.month_returns(A['spy'], A['days'])
        first = next(iter(rule))
        keys = [k for k in sorted(res) if int(k[:4]) >= int(first[:4])]
        mac = MA.macro_load(self.pub, A['days'])
        cash = {}
        mo = A['days'].astype('datetime64[M]')
        for t in range(len(A['days'])):
            if str(mo[t]) not in cash and np.isfinite(mac['x']['ff'][t]):
                cash[str(mo[t])] = mac['x']['ff'][t] / 100 / 12
        eq = np.prod([1 + (res[k] if int(k[5:7]) in (11, 12, 1, 2, 3, 4) else cash.get(k, 0.0)) for k in keys])
        self.assertAlmostEqual(rule[first]['nov_apr']['cagr'], eq ** (12 / len(keys)) - 1, places=4)
        self.assertEqual(set(S['spy']['months'][S['spy']['periods'][0]]), {str(m) for m in range(1, 13)})
        self.assertEqual(len(S['signals']['by_month']['above40'][S['signals']['periods'][0]]), 12)

    def test_distance_tables(self):
        D = self.doc['scores']['distance']
        self.assertEqual(len(D['by']), len(MA.WS) * len(MA.GS))
        r = D['by']['0.5|0.05']['13']
        self.assertEqual(len(r['n']), MA.DIST_BUCKETS)
        for j in range(MA.DIST_BUCKETS):
            if r['back'][j] is not None:
                self.assertTrue(0 <= r['back'][j] <= 1)
                self.assertTrue(r['q10'][j] <= r['q50'][j] <= r['q90'][j])
        ds = [v for v in r['d'] if v is not None]
        self.assertEqual(ds, sorted(ds))                                      # the bands run from below the line to above it
        R = D['regression']
        self.assertTrue(0 < R['0|0']['13']['random_walk_slope'] < 1)          # a random walk's distance shrinks by itself
        self.assertIsNotNone(R['0.5|0.05']['26']['ret_slope'])

    def test_company_season_and_new_fields(self):
        rows = json.loads((self.pub / 'ma-hybrid-rows.json').read_text())['rows']
        r = next(x for x in rows if x['hd_pct'] is not None and x['seas13'] is not None)
        self.assertTrue(0 <= r['hd_pct'] <= 1)
        f = json.loads((self.pub / 'ma' / f"{r['id']}.json").read_text())
        self.assertEqual(len(f['season']['m']), 12)
        A = MA.load(self.pub, self.fund, self.gd)
        i = A['ids'].index(r['id'])
        want = MA.company_season(A['C'][i], A['spy'], A['days'])
        np.testing.assert_allclose([v for v in f['season']['m'] if v is not None], [v for v in want['m'] if v is not None], rtol=1e-6)
        for m in ('ma_time', 'ma_dist'):
            self.assertIn(m, self.doc['scores']['models']['26'])
        e = list(FB.load(self.ledger)['families']['ma:13'].values())[0]['forecast']
        for k in ('s_time', 's_dist', 'hd_pct', 'seas'):
            self.assertEqual(len(e[k]), len(e['ids']), k)
        self.assertIn('13', self.doc['scores']['seasonal'])


if __name__ == '__main__':
    unittest.main()
