"""ladders.py: hourly readings of closing-price ladders, the expected value, the options' view (max pain, walls, implied
range), the combined range, the price-history backfill, the resolution and the backtest."""
import datetime as dt, json, math, random, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import consensus as C
import ladders as L


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes; self.calls = 0; self.urls = []

    def json(self, url, headers=None):
        return json.loads(self.get(url))

    def get(self, url, headers=None, tries=1, timeout=0):
        self.calls += 1; self.urls.append(url)
        for k, v in self.routes.items():
            if k in url:
                v = v(url) if callable(v) else v
                return json.dumps(v).encode()
        if 'polymarket' in url:
            return b'[]'
        raise RuntimeError('HTTP 404')


def opt_sym(root, exp, typ, k):
    d = dt.date.fromisoformat(exp)
    return f'{root}{d:%y%m%d}{typ}{int(round(k * 1000)):08d}'


class Pieces(unittest.TestCase):
    def test_expected_value_of_a_ladder(self):
        st = C.ladder_stats([(335, .885), (340, .825), (345, .385), (350, .0862), (355, .0862)])
        self.assertAlmostEqual(st['median']['value'], 343.69, places=1)
        self.assertTrue(340 < st['mean']['value'] < 348)
        self.assertAlmostEqual(st['mean']['tails'], 0.115 + 0.0862, places=3)
        sym = C.ladder_stats([(90, .9), (95, .7), (100, .5), (105, .3), (110, .1)])     # symmetric: the mean is the median
        self.assertAlmostEqual(sym['mean']['value'], 100, delta=0.6)

    def test_max_pain_matches_brute_force(self):
        rnd = random.Random(4)
        rows = [{'type': rnd.choice('CP'), 'k': float(rnd.randrange(80, 121, 5)), 'oi': rnd.randrange(0, 900)} for _ in range(60)]
        ks = sorted({r['k'] for r in rows if r['oi']})
        pay = lambda s: sum(r['oi'] * (max(0, s - r['k']) if r['type'] == 'C' else max(0, r['k'] - s)) for r in rows)
        self.assertEqual(L._max_pain(rows), min(ks, key=pay))

    def test_digital_falls_with_the_strike_and_skew_lifts_low_strikes(self):
        flat = L.digital([(k, 0.3) for k in range(80, 121, 5)], 100, 7 / 365)
        ps = [p for _, p in flat]
        self.assertTrue(all(a >= b for a, b in zip(ps, ps[1:])))
        self.assertAlmostEqual(dict(flat)[100], 0.5, delta=0.02)
        skew = L.digital([(k, 0.3 + 0.004 * (100 - k)) for k in range(80, 121, 5)], 100, 7 / 365)
        own = L.digital([(k, 0.32) for k in (90, 95, 100)], 100, 7 / 365)      # N(d2) at the strike's own volatility
        self.assertGreater(dict(skew)[95], dict(own)[95])                      # minus vega × a falling smile lifts it

    def test_rows_realign_when_strikes_are_added(self):
        rec = {'strikes': [100, 110], 'rows': [['2026-01-01T10'] + [None] * 11 + [[.8, .2], [.7, .3]]]}
        L.align(rec, [90, 110, 120])
        self.assertEqual(rec['strikes'], [90, 100, 110, 120])
        self.assertEqual(rec['rows'][0][12], [None, .8, .2, None])
        self.assertEqual(rec['rows'][0][13], [None, .7, .3, None])

    def test_fit_finds_the_weights_and_the_width(self):
        rnd = random.Random(7)
        groups = []
        for i in range(60):                              # the close lands where the expected value said, give or take 1%
            S = 100.0; ev = S * (1 + rnd.uniform(-0.03, 0.03)); a = ev * (1 + rnd.gauss(0, 0.01))
            rows = [{'t': '2026-01-01T10', 'spot': S, 'ev': ev, 'median': ev, 'q10': ev * 0.95, 'q90': ev * 1.05, 'mp': S * 1.02, 'cw': None, 'pw': None,
                     'oq10': None, 'omed': None, 'oq90': None, 'p': None, 'op': None}]
            groups.append({'key': str(i), 'end': f'2026-01-{1 + i % 28:02d}', 'ticker': 'X', 'actual': a, 'strikes': [], 'rows': rows})
        P = L.fit(groups)
        self.assertEqual(P['w_ev'], 1.0)
        self.assertEqual(P['w_mp'], 0.0)
        self.assertLess(P['k'], 0.6)                     # the ladder's ±5% was far too wide for a 1% miss: narrowed
        ev = L.evaluate(groups, P)
        self.assertAlmostEqual(ev['inside80']['combined'], 0.8, delta=0.05)
        self.assertLess(ev['mae']['combined'], ev['mae']['price'])


class Collect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'lad'
        site = Path(self.tmp.name) / 'index.json'
        site.write_text(json.dumps({'companies': [{'cik': 320193, 'ticker': 'AAPL', 'name': 'Apple Inc.', 'revenue': 4e11}]}))
        self.site = site

    def tearDown(self):
        self.tmp.cleanup()

    def routes(self, now):
        today = now.astimezone(L.ET).date()
        d1, d4, dpast = (today + dt.timedelta(days=1)).isoformat(), (today + dt.timedelta(days=4)).isoformat(), (today - dt.timedelta(days=2)).isoformat()
        self.d1, self.d4, self.dpast = d1, d4, dpast

        def mk(title, p, tok, closed=False, out=None):
            return {'groupItemTitle': title, 'question': title, 'bestBid': str(p - 0.01), 'bestAsk': str(p + 0.01), 'closed': closed,
                    'outcomePrices': json.dumps(out or [str(p), str(1 - p)]), 'clobTokenIds': json.dumps([tok, tok + 'n']), 'active': not closed}
        open_day = {'id': 'e1', 'title': f'Apple (AAPL) closes above ___ on {dt.date.fromisoformat(d1):%B} {dt.date.fromisoformat(d1).day}?',
                    'slug': f'aapl-close-above-{d1}', 'endDate': d1 + 'T20:00:00Z', 'closed': False, 'tags': [{'slug': 'stocks'}],
                    'markets': [mk('$335', .9, 'a1'), mk('$340', .8, 'a2'), mk('$345', .4, 'a3'), mk('$350', .1, 'a4'), mk('$355', .05, 'a5')]}
        open_week = {'id': 'e2', 'title': 'Apple (AAPL) closes week of Oct 19 at ___?', 'slug': f'aapl-week-{d4}', 'endDate': d4 + 'T20:00:00Z',
                     'closed': False, 'tags': [{'slug': 'stocks'}],
                     'markets': [mk('<$330', .1, 'b1'), mk('$330-$340', .3, 'b2'), mk('$340-$350', .4, 'b3'), mk('>$350', .2, 'b4')]}
        closed_day = {'id': 'e3', 'title': f'Apple (AAPL) closes above ___ on {dt.date.fromisoformat(dpast):%B} {dt.date.fromisoformat(dpast).day}?',
                      'slug': f'aapl-close-above-{dpast}', 'endDate': dpast + 'T20:00:00Z', 'closed': True, 'tags': [{'slug': 'stocks'}],
                      'markets': [mk('$330', .99, 'c1', True, ['1', '0']), mk('$340', .99, 'c2', True, ['1', '0']), mk('$350', .01, 'c3', True, ['0', '1'])]}
        crude = {'id': 'e4', 'title': 'WTI Crude Oil (WTI) closes above ___ on October 19?', 'slug': 'wti', 'endDate': d1 + 'T20:00:00Z', 'closed': False,
                 'tags': [{'slug': 'stocks'}], 'markets': [mk('$90', .6, 'w1'), mk('$95', .3, 'w2')]}
        close_past = L.close_utc(dpast)

        def clob(url):
            tok = url.split('market=')[1].split('&')[0]
            base = {'c1': .95, 'c2': .6, 'c3': .2, 'a1': .9, 'a2': .8, 'a3': .5, 'a4': .2, 'a5': .1}.get(tok, .5)
            end = int(url.split('endTs=')[1].split('&')[0])
            return {'history': [{'t': end - 3600 * h, 'p': base} for h in range(48, 0, -1)]}

        def chart(url):
            daily = 'interval=1d' in url
            if daily:
                days = [today - dt.timedelta(days=i) for i in range(10, -1, -1)]
                ts = [int(dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=L.ET).timestamp()) for d in days]
                cl = [345.0 if d.isoformat() == dpast else 342.0 for d in days]
            else:
                ts = [int((now - dt.timedelta(hours=h)).timestamp()) for h in range(24 * 5, 0, -1)]
                cl = [343.0] * len(ts)
            return {'chart': {'result': [{'meta': {'regularMarketPrice': 343.0, 'regularMarketTime': int(now.timestamp())}, 'timestamp': ts,
                                          'indicators': {'quote': [{'close': cl}]}}]}}

        opts = []
        for exp, oi_c, oi_p in ((d4, {350: 9000, 345: 3000, 340: 1000}, {330: 8000, 335: 2000, 340: 1500}),):
            for k in range(320, 371, 5):
                opts.append({'option': opt_sym('AAPL', exp, 'C', k), 'iv': 0.28, 'open_interest': oi_c.get(k, 100), 'volume': 1, 'delta': .5, 'gamma': .01, 'bid': 1, 'ask': 1.1})
                opts.append({'option': opt_sym('AAPL', exp, 'P', k), 'iv': 0.28 + 0.002 * (343 - k), 'open_interest': oi_p.get(k, 100), 'volume': 1, 'delta': -.5, 'gamma': .01, 'bid': 1, 'ask': 1.1})
        return {'tag_slug=stocks&closed=false': [open_day, open_week, crude], 'tag_slug=stocks&closed=true': [closed_day],
                'prices-history': clob, 'v8/finance/chart/AAPL': chart,
                'delayed_quotes/options/AAPL.json': {'timestamp': now.isoformat(), 'data': {'current_price': 343.0, 'options': opts}}}

    def test_collect_reads_scores_and_publishes(self):
        now = L.utcnow()
        h = FakeHttp(self.routes(now))
        orig = C.Http
        C.Http = lambda *a, **k: h
        try:
            out = L.collect(self.root, self.site, minutes=2, verbose=False)
        finally:
            C.Http = orig
        self.assertEqual(out['live'], 2)
        self.assertEqual(out['closed_seen'], 1)
        self.assertGreater(out['backfill_requests'], 0)
        doc = json.loads((self.root / 'public' / 't' / 'AAPL.json').read_text())
        self.assertEqual([m['end'] for m in doc['open']], [self.d1, self.d4])
        day, week = doc['open']
        self.assertTrue(335 < day['ev'] < 350)
        self.assertEqual(day['options']['exp'], self.d4)        # no option expires on the daily ladder's date: the next one
        self.assertFalse(day['options']['exact'])
        self.assertTrue(week['options']['exact'])
        self.assertEqual(week['options']['call_wall'], 350)
        self.assertEqual(week['options']['put_wall'], 330)
        self.assertIsNotNone(week['options']['max_pain'])
        self.assertTrue(week['options']['q10'] < 343 < week['options']['q90'])
        self.assertEqual(len(week['op']), len(week['strikes']))
        c = week['combined']
        self.assertTrue(c['lo'] < c['center'] < c['hi'])
        self.assertEqual(c['basis'], 'prior')
        self.assertEqual(day['history'][-1][0], L.hkey(now))      # the live reading last, the rebuilt hours before it
        self.assertGreater(len(day['history']), 1)
        self.assertFalse(any('wti' in (m['url'] or '') for m in doc['open']))
        # the closed ladder: rebuilt from the CLOB history, resolved at the close of its day, scored
        self.assertEqual(doc['resolved_n'], 1)
        r = doc['resolved'][0]
        self.assertEqual(r['actual'], 345.0)
        self.assertGreater(r['readings'], 40)
        self.assertTrue(doc['backtest'])
        bt = json.loads((self.root / 'public' / 'backtest.json').read_text())
        self.assertEqual(bt['resolved'], 1)
        b = {x['bucket']: x for x in bt['rows']}
        self.assertIn('6–24 hours', b)
        self.assertIsNotNone(b['6–24 hours']['mae']['ev'])
        idx = json.loads((self.root / 'public' / 'index.json').read_text())
        self.assertEqual(idx['rows'][0][0], 'AAPL')
        # a second run within the hour replaces the reading; history is kept per hour
        h2 = FakeHttp(self.routes(now))
        C.Http = lambda *a, **k: h2
        try:
            L.collect(self.root, self.site, minutes=2, verbose=False)
        finally:
            C.Http = orig
        doc2 = json.loads((self.root / 'public' / 't' / 'AAPL.json').read_text())
        self.assertEqual(len(doc2['open'][0]['history']), len(day['history']))
        self.assertFalse(any('prices-history' in u for u in h2.urls))   # rebuilt once


if __name__ == '__main__':
    unittest.main()
