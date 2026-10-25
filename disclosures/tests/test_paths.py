"""app/paths.py (the daily-bar collector and cache) and the pieces of app/paths_build.py that need no model: parsing
Yahoo and Stooq daily bars, merging a refresh after a dividend or a split, the deterministic two-part cache, the
universe, officials' approximate holdings and portfolio returns."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import paths as P  # noqa: E402


def yahoo_payload(days, closes, adj=None, opens=None, vols=None):
    ts = [int(dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp()) for d in days]
    q = {'open': opens or closes, 'high': [c * 1.01 if c else None for c in closes], 'low': [c * 0.99 if c else None for c in closes], 'close': closes,
         'volume': vols or [1000] * len(days)}
    return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': -14400}, 'indicators': {'quote': [q], 'adjclose': [{'adjclose': adj or closes}]}}]}}


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


class Bars(unittest.TestCase):
    def test_parse_yahoo_daily(self):
        days = weekdays('2026-01-05', 30)
        closes = [100 + i for i in range(30)]
        closes[3] = None                                   # a day without a close is dropped
        b = P.parse_yahoo_daily(yahoo_payload(days, closes, adj=[c * 0.98 if c else None for c in closes]))
        self.assertEqual(len(b['t']), 29)
        self.assertNotIn(days[3], b['t'])
        self.assertEqual(b['t'][0], days[0])
        i = b['t'].index(days[10])
        self.assertAlmostEqual(b['ac'][i], 110 * 0.98, places=3)
        self.assertTrue(all(h >= max(o, c) and lo <= min(o, c) for o, h, lo, c in zip(b['o'], b['h'], b['l'], b['c'])))
        with self.assertRaises(ValueError):                 # weekly bars are refused
            P.parse_yahoo_daily(yahoo_payload(weekdays('2026-01-05', 200)[::5], [100.0] * 40))

    def test_parse_stooq_daily(self):
        days = weekdays('2026-01-05', 25)
        text = 'Date,Open,High,Low,Close,Volume\n' + '\n'.join(f'{d},{10 + i},{11 + i},{9 + i},{10.5 + i},{1000 + i}' for i, d in enumerate(days))
        b = P.parse_stooq_daily(text)
        self.assertEqual(b['t'], days)
        self.assertEqual(b['ac'], b['c'])
        self.assertEqual(b['v'][0], 1000)
        with self.assertRaises(ValueError):
            P.parse_stooq_daily('<html>Exceeded the daily hits limit</html>')

    def test_merge_after_dividend_and_split(self):
        days = weekdays('2025-01-02', 300)
        old = {'t': days, 'o': [100.0] * 300, 'h': [101.0] * 300, 'l': [99.0] * 300, 'c': [100.0] * 300, 'ac': [90.0] * 300, 'v': [1000] * 300}
        # the refresh covers the last 60 days; a 2-for-1 split restated the closes and a dividend the adjusted closes
        new = {'t': days[-60:] + weekdays('2026-03-20', 3), 'o': [50.0] * 63, 'h': [50.5] * 63, 'l': [49.5] * 63, 'c': [50.0] * 63, 'ac': [44.0] * 63, 'v': [2000] * 63}
        m = P.merge(old, new)
        self.assertEqual(m['t'], sorted(set(days) | set(new['t'])))
        self.assertAlmostEqual(m['c'][0], 50.0)              # older closes put on the split basis
        self.assertAlmostEqual(m['ac'][0], 44.0)             # and the adjusted closes on the dividend basis
        self.assertEqual(m['v'][0], 2000)                    # volume scales the other way
        self.assertEqual(m['c'][-1], 50.0)
        self.assertEqual(P.merge(None, new), new)
        self.assertEqual(P.merge(old, None), old)

    def test_cache_is_split_and_deterministic(self):
        root = tempfile.mkdtemp()
        days = weekdays('2024-01-02', 600)
        doc = {'ticker': 'AAA', 'source': 'yahoo', 't': days, **{k: [1.0 + i / 1000 for i in range(600)] for k in ('o', 'h', 'l', 'c', 'ac')}, 'v': [5] * 600}
        P.save(root, 'AAA', doc)
        base = P.cache_path(root, 'AAA', '.base').read_bytes()
        P.save(root, 'AAA', doc)
        self.assertEqual(base, P.cache_path(root, 'AAA', '.base').read_bytes())
        back = P.load(root, 'AAA')
        self.assertEqual(back['t'], days)
        self.assertEqual(back['ac'], doc['ac'])
        self.assertNotIn('base', back)
        self.assertIsNone(P.load(root, 'ZZZ'))

    def test_universe_orders_by_market_value(self):
        root = Path(tempfile.mkdtemp())
        (root / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'price', 'mcap'],
                                                     'rows': [[1, 'small', 'S', 'technology', 'industrial', 1, 10], [2, 'BRK.B', 'B', 'financials', 'insurer', 1, 99],
                                                              [3, 'bad ticker!', 'X', 'other', 'industrial', 1, 50]]}))
        u = P.universe(root / 'index.json')
        self.assertEqual([c['t'] for c in u], ['BRK-B', 'SMALL'])
        self.assertEqual(P.universe(None), [])


class Portfolios(unittest.TestCase):
    def test_official_holdings_and_portfolio_returns(self):
        try:
            import paths_build as PB
        except ImportError as exc:                           # the model modules are not there yet
            self.skipTest(str(exc))
        today = dt.date.today()
        o = {'scored_fields': ['date', 'ticker', 'd', 'midpoint', 'excess_trade', 'excess_follow', 'disclosed'],
             'scored': [[(today - dt.timedelta(days=30)).isoformat(), 'AAA', 1, 300.0, None, None, ''],
                        [(today - dt.timedelta(days=20)).isoformat(), 'BBB', 1, 100.0, None, None, ''],
                        [(today - dt.timedelta(days=10)).isoformat(), 'BBB', -1, 100.0, None, None, ''],
                        [(today - dt.timedelta(days=900)).isoformat(), 'CCC', 1, 500.0, None, None, '']]}
        self.assertEqual(PB.official_holdings(o), [('AAA', 1.0)])
        days = weekdays('2023-01-02', 900)
        rng = np.random.default_rng(1)
        uni = {t: (days, 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 900)))) for t in ('AAA', 'BBB', 'SPY')}
        dates, R, cover = PB.portfolio_series([('AAA', 0.75), ('BBB', 0.25), ('NONE', 1.0)], uni)
        self.assertAlmostEqual(cover, 0.5)
        self.assertEqual(R.shape[1], 2)                       # the portfolio and SPY
        a = np.diff(np.log(uni['AAA'][1]))[-len(R):]
        b = np.diff(np.log(uni['BBB'][1]))[-len(R):]
        self.assertTrue(np.allclose(R[:, 0], np.log1p(0.75 * np.expm1(a) + 0.25 * np.expm1(b))))
        # the same ticker on two rows (share classes, options) and SPY held directly: one column each, SPY still last
        dates, R2, cover = PB.portfolio_series([('AAA', 0.5), ('BBB', 0.25), ('AAA', 0.25), ('SPY', 0.5)], uni)
        self.assertEqual(R2.shape[1], 2)
        s = np.diff(np.log(uni['SPY'][1]))[-len(R2):]
        self.assertTrue(np.allclose(R2[:, 0], np.log1p(0.5 * np.expm1(a) + 0.167 * np.expm1(b) + 0.333 * np.expm1(s)), atol=1e-3))
        self.assertTrue(np.allclose(R2[:, 1], s))


if __name__ == '__main__':
    unittest.main()


class Build(unittest.TestCase):
    """The whole build on synthetic bars: six correlated stocks, the market and the sector ETF, two portfolios."""

    def test_end_to_end(self):
        import paths_build as PB
        root = Path(tempfile.mkdtemp())
        days = weekdays('2021-01-04', 1150)
        rng = np.random.default_rng(7)
        mkt = rng.normal(0.0003, 0.011, len(days))
        names = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
        series = {'SPY': mkt, 'XLK': 0.9 * mkt + rng.normal(0, 0.006, len(days))}
        for k, t in enumerate(names):
            series[t] = (0.8 + 0.1 * k) * mkt + rng.normal(0, 0.015, len(days))
        for t, r in series.items():
            c = 50 * np.exp(np.cumsum(r))
            o = c * np.exp(rng.normal(0, 0.004, len(days)))
            h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, len(days))))
            lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, len(days))))
            P.save(root, t, {'ticker': t, 'source': 'test', 't': days, 'o': o.round(4).tolist(), 'h': h.round(4).tolist(), 'l': lo.round(4).tolist(),
                             'c': c.round(4).tolist(), 'ac': c.round(4).tolist(), 'v': rng.integers(1e5, 1e6, len(days)).tolist()})
        (root / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'],
                                                     'rows': [[100 + k, t, t + ' Corp', 'technology', 'industrial', 1e9 * (10 - k)] for k, t in enumerate(names)]}))
        ppl = root / 'people'
        (ppl / 'm').mkdir(parents=True)
        (ppl / 'o').mkdir(parents=True)
        (ppl / 'managers.json').write_text(json.dumps({'fields': ['cik', 'name'], 'rows': [[1, 'Fund One']]}))
        (ppl / 'm' / '1.json').write_text(json.dumps({'cik': 1, 'name': 'Fund One', 'slug': 'fund-one', 'holdings_fields': ['ticker', 'name', 'weight', 'value', 'status', 'delta_pct'],
                                                      'holdings': [['AAA', 'A', 0.6, 6, None, None], ['BBB', 'B', 0.4, 4, None, None]]}))
        (ppl / 'officials.json').write_text(json.dumps({'fields': ['slug', 'name'], 'rows': [['jane-roe', 'Jane Roe']]}))
        today = dt.date.today()
        (ppl / 'o' / 'jane-roe.json').write_text(json.dumps({'name': 'Jane Roe', 'slug': 'jane-roe', 'scored_fields': ['date', 'ticker', 'd', 'midpoint'],
                                                             'scored': [[(today - dt.timedelta(days=40)).isoformat(), 'CCC', 1, 50000.5]]}))
        st = PB.build(root, root / 'index.json', ppl, workers=1)
        self.assertEqual((st['companies'], st['failed']), (6, 0), st)
        pub = root / 'public'
        d = json.loads((pub / 'c' / '100.json').read_text())
        json.dumps(d, allow_nan=False)
        self.assertEqual(set(d['paths']['models']), set(PB.PM.MODELS))
        e = d['paths']['ensemble']
        self.assertTrue(e['end']['p10'] < d['price'] * 1.0001 < e['end']['p90'] * 1.5)
        self.assertEqual(len(e['q']), len(d['paths']['days']))
        self.assertIsNotNone(e['joint']['market']['p_stock_down10'])
        self.assertEqual([a['role'] for a in d['assets']][:3], ['stock', 'market', 'sector'])
        for k in ('self', 'pooled', 'peer'):
            self.assertTrue(d['analogs'][k] and d['analogs'][k].get('q'), k)
        self.assertTrue(d['analogs']['peers'])
        self.assertTrue({'state', 'overlays', 'signals'} <= set(d['pa']))
        self.assertNotIn('recent', d['pa']['state'])
        ix = json.loads((pub / 'index.json').read_text())
        self.assertEqual(len(ix['rows']), 6)
        rules = json.loads((pub / 'rules.json').read_text())
        self.assertTrue(rules['rules'] and any((r.get('stats') or {}).get('evidence') for r in rules['rules']))
        models = json.loads((pub / 'models.json').read_text())
        self.assertTrue({'ensemble', 'naive_normal', 'cholesky'} <= set(models['paths']))
        self.assertTrue(models['analogs'])
        led = json.loads((pub / 'ledger.json').read_text())
        self.assertEqual(len(led['weeks']), 1)
        self.assertFalse(led['weeks'][0]['resolved'])
        port = json.loads((pub / 'portfolios' / 'index.json').read_text())
        self.assertEqual((len(port['managers']), len(port['officials'])), (1, 1))
        m = json.loads((pub / 'portfolios' / 'm' / '1.json').read_text())
        self.assertAlmostEqual(m['coverage'], 1.0)
        self.assertTrue(m['ensemble']['q'])
        o = json.loads((pub / 'portfolios' / 'o' / 'jane-roe.json').read_text())
        self.assertTrue(o['approximate'])
        # a second build the same week keeps the frozen week as it was
        before = (root / 'cache' / 'ledger').glob('*.json').__next__().read_text()
        PB.build(root, root / 'index.json', None, workers=1)
        self.assertEqual(before, next((root / 'cache' / 'ledger').glob('*.json')).read_text())
