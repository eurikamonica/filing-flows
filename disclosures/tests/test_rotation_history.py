import datetime as dt, gzip, json, math, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import frames as FR
import rotation_history as RH


def yahoo_payload(weeks, start=dt.date(2010, 1, 4), base=50.0, drift=0.002, amp=0.08, period=40, extra_day=True):
    """A weekly chart answer: Monday timestamps (UTC 13:30 = 9:30 New York), close, volume and adjusted close."""
    ts, close, adj, vol = [], [], [], []
    for i in range(weeks):
        d = dt.datetime.combine(start + dt.timedelta(days=7 * i), dt.time(13, 30), dt.timezone.utc)
        p = base * math.exp(drift * i + amp * math.sin(2 * math.pi * i / period))
        ts.append(int(d.timestamp())); close.append(p); adj.append(p * 0.98); vol.append(1_000_000 + 1000 * i)
    if extra_day:                                     # Yahoo adds the latest day of an unfinished week as its own bar
        d = dt.datetime.combine(start + dt.timedelta(days=7 * (weeks - 1) + 2), dt.time(20, 0), dt.timezone.utc)
        ts.append(int(d.timestamp())); close.append(close[-1] * 1.01); adj.append(adj[-1] * 1.01); vol.append(5)
    return {'chart': {'result': [{'meta': {'gmtoffset': -14400}, 'timestamp': ts,
                                  'indicators': {'quote': [{'close': close, 'volume': vol}], 'adjclose': [{'adjclose': adj}]}}]}}


class FakeClient:
    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def json(self, url, sec=False):
        self.calls.append(url)
        t = url.split('/chart/')[1].split('?')[0]
        if t in self.fail:
            raise RuntimeError('HTTP 404 from query1.finance.yahoo.com')
        seed = sum(map(ord, t))
        return yahoo_payload(26 if 'range=6mo' in url else 860, base=20 + seed % 80, drift=0.0005 * (seed % 7), period=30 + seed % 25)

    def get(self, url, sec=False):
        self.calls.append(url)
        raise RuntimeError('HTTP 404 from stooq.com')


class Weeks(unittest.TestCase):
    def test_friday_and_resampling(self):
        self.assertEqual(RH.friday(dt.date(2026, 10, 12)).isoformat(), '2026-10-16')      # Monday
        self.assertEqual(RH.friday(dt.date(2026, 10, 18)).isoformat(), '2026-10-16')      # Sunday belongs to the week before
        rows = RH.parse_stooq('Date,Open,High,Low,Close,Volume\n2026-10-12,1,1,1,10,100\n2026-10-13,1,1,1,11,200\n'
                              '2026-10-16,1,1,1,12,300\n2026-10-19,1,1,1,13,50\n')
        self.assertEqual(rows, [['2026-10-16', 12.0, 600], ['2026-10-23', 13.0, 50]])
        with self.assertRaises(ValueError):
            RH.parse_stooq('<html>Exceeded the daily hits limit</html>')

    def test_yahoo_weekly_uses_adjusted_closes_and_one_row_per_week(self):
        rows = RH.parse_yahoo(yahoo_payload(10))
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0][0], '2010-01-08')
        self.assertAlmostEqual(rows[0][1], 50 * 0.98, places=3)
        self.assertEqual(rows[-1][2], 5)                  # the unfinished week's latest bar replaces it, volume not added
        with self.assertRaises(ValueError):
            RH.parse_yahoo({'chart': {'result': None, 'error': {'description': 'No data found'}}})

    def test_align_on_the_grid(self):
        weeks = ['2026-09-25', '2026-10-02', '2026-10-09', '2026-10-16']
        f, c, v = RH.align([['2026-10-02', 10.0, 5], ['2026-10-16', 12.0, 7]], weeks)
        self.assertEqual((f, c, v), (1, [10.0, 10.0, 12.0], [5, None, 7]))


class CollectAndBuild(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.site = self.dir / 'site'
        self.site.mkdir()
        cos = [{'cik': 1000 + i, 'ticker': t, 'name': t + ' Corp', 'sector': s, 'revenue': (10 - i) * 1e9, 'filed': '2026-08-01',
                'end': '2026-06-30'} for i, (t, s) in enumerate([('AAA', 'technology'), ('BBB', 'technology'), ('CCC', 'technology'),
                                                                  ('DDD', 'energy'), ('BRK.B', 'financials')])]
        (self.site / 'index.json').write_text(json.dumps({'companies': cos, 'sector_names': {'technology': 'Technology'}}))

    def test_collect_resumes_backs_off_and_refreshes(self):
        root = self.dir / 'hist'
        tickers = RH.universe(self.site / 'index.json')
        self.assertEqual(tickers[:3], ['SPY', 'XLK', 'XLC'])
        self.assertIn('BRK-B', tickers)                                       # class shares as Yahoo writes them
        c = FakeClient(fail={'XLC'})
        r = RH.collect(c, root, tickers, batch=5, refresh=0)
        self.assertEqual((r['new'], r['failed']), (4, 1))
        st = json.loads((root / 'state.json').read_text())
        self.assertEqual(st['tickers']['XLC']['fails'], 1)
        self.assertGreater(st['tickers']['XLC']['retry_after'], st['tickers']['XLC']['tried_at'])
        self.assertEqual(st['summary']['on_file'], 4)
        r = RH.collect(FakeClient(), root, tickers, batch=100, refresh=0)     # the next run goes on; XLC waits its turn
        st = json.loads((root / 'state.json').read_text())
        self.assertNotIn('fetched_at', st['tickers']['XLC'])
        self.assertEqual(st['summary']['on_file'], len(tickers) - 1)
        st['tickers']['SPY']['fetched_at'] = '2020-01-01T00:00:00+00:00'      # stale: refreshed with the last months only
        (root / 'state.json').write_text(json.dumps(st))
        c = FakeClient()
        r = RH.collect(c, root, tickers, batch=0, refresh=10)
        self.assertEqual(r['refreshed'], 1)
        self.assertIn('range=6mo', c.calls[0])
        self.assertGreater(len(RH.load(root, 'SPY')['rows']), 800)          # merged, not replaced
        c = FakeClient()
        RH.collect(c, root, tickers, batch=0, refresh=0, first=['XLC'])        # asked for: fetched now, whatever the wait
        self.assertIn('/XLC?', c.calls[0])

    def test_build_writes_the_rrg_file_ticker_files_and_the_long_rotation(self):
        root = self.dir / 'hist'
        tickers = RH.universe(self.site / 'index.json')
        RH.collect(FakeClient(), root, tickers, batch=100, refresh=0)
        periods = FR.calendar_quarters(12 + 5 + 3)
        for i, per in enumerate(periods):                                      # figures for the five companies
            for concept, k in (('Revenues', 1.0), ('OperatingIncomeLoss', .2 + .02 * math.sin(i)), ('GrossProfit', .5), ('NetIncomeLoss', .15)):
                p = FR.path_for(root, concept, per)
                p.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(p, 'wt') as f:
                    json.dump({str(1000 + j): (10 - j) * 1e9 * (1 + .03 * i) * k for j in range(5)}, f)
        out = RH.build(root, self.site, self.dir / 'nodata', quarters_long=12, months_long=24, today=dt.date(2026, 10, 17))
        pub = root / 'public'
        rrg = json.loads((pub / 'rrg.json').read_text())
        self.assertEqual(rrg['bench']['id'], 'SPY')
        ids = [s['id'] for s in rrg['series']]
        self.assertIn('XLK', ids)
        self.assertIn('s:technology', ids)                                    # three members: an index
        self.assertNotIn('s:energy', ids)                                     # one member: no index
        tech = next(s for s in rrg['series'] if s['id'] == 's:technology')
        self.assertEqual(tech['members'], 3)
        self.assertEqual((rrg['bench']['start'], len(rrg['bench']['c'])), ('2010-01-08', 860))
        aaa = json.loads((pub / 't' / 'AAA.json').read_text())
        self.assertEqual((aaa['n'], aaa['s']), ('AAA Corp', 'technology'))
        self.assertTrue((pub / 't' / 'BRK-B.json').exists())
        self.assertEqual(out['long_companies'], 5)
        rot = json.loads((pub / 'rotation-long.json').read_text())
        self.assertEqual(len(rot['quarters']), 12)
        F = rot['fields']
        p = rot['companies'][0]['p'][-1]
        self.assertIsNotNone(p[F.index('vola')])                              # weekly returns, annualised with 52
        self.assertIsNotNone(p[F.index('volz')])
        self.assertIsNotNone(p[F.index('rel')])
        mon = json.loads((pub / 'rotation-long-monthly.json').read_text())
        self.assertEqual(len(mon['months']), 24)
        self.assertTrue(json.loads((pub / 'status.json').read_text())['collector']['on_file'] >= 5)


if __name__ == '__main__':
    unittest.main()
