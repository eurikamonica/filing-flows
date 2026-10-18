"""consensus.py: prediction-market ladders become monotone implied distributions, markets map to the right company, and
Yahoo's analyst consensus is parsed into estimates, revisions and surprises."""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import consensus as C

COS = [{'cik': 1, 'ticker': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Tech', 'revenue': 4e11},
       {'cik': 2, 'ticker': 'NVDA', 'name': 'NVIDIA Corp', 'sector': 'Tech', 'revenue': 1e11},
       {'cik': 3, 'ticker': 'SMCI', 'name': 'Super Micro Computer, Inc.', 'sector': 'Tech', 'revenue': 2e10},
       {'cik': 4, 'ticker': 'TECH', 'name': 'Bio-Techne Corp', 'sector': 'Health', 'revenue': 1e9},
       {'cik': 5, 'ticker': 'FDX', 'name': 'FedEx Corp', 'sector': 'Industrials', 'revenue': 9e10},
       {'cik': 6, 'ticker': 'MSTR', 'name': 'Strategy Inc', 'sector': 'Tech', 'revenue': 5e8},
       {'cik': 7, 'ticker': 'BRK.B', 'name': 'Berkshire Hathaway Inc', 'sector': 'Fin', 'revenue': 3e11}]


def mk(title, k, yes, closed=False, out=None, slug='x'):
    return {'groupItemTitle': title, 'question': title, 'outcomePrices': json.dumps(out or [str(yes), str(1 - yes)]), 'closed': closed,
            'slug': slug, 'clobTokenIds': '["1"]', 'id': k, 'active': True}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes; self.calls = 0

    def json(self, url, headers=None):
        return json.loads(self.get(url))

    def get(self, url, headers=None, tries=1, timeout=0):
        self.calls += 1
        for k, v in self.routes.items():
            if k in url:
                return json.dumps(v).encode() if not isinstance(v, bytes) else v
        if 'polymarket' in url:
            return b'[]'
        raise RuntimeError('HTTP 404')


class Ladders(unittest.TestCase):
    def test_strikes(self):
        self.assertEqual(C.strike_of('$170'), (170.0, 170.0))
        self.assertEqual(C.strike_of('<$2.50T'), (None, 2.5e12))
        self.assertEqual(C.strike_of('$2.50-$3.00T'), (2.5e12, 3e12))
        self.assertEqual(C.strike_of('>$365'), (365.0, None))
        self.assertEqual(C.strike_of('↓ $280'), (280.0, 280.0))

    def test_isotonic(self):
        self.assertEqual(C.isotonic_decreasing([0.9, 0.5, 0.6, 0.1]), [0.9, 0.55, 0.55, 0.1])

    def test_ladder_median_and_bounds(self):
        st = C.ladder_stats([(100, 0.9), (110, 0.6), (120, 0.4), (130, 0.1)])
        self.assertAlmostEqual(st['median']['value'], 115.0)
        self.assertIsNone(st['median']['bound'])
        st2 = C.ladder_stats([(100, 0.3), (110, 0.1)])
        self.assertEqual(st2['median'], {'value': 100, 'bound': 'below'})     # the median lies under the lowest strike

    def test_brackets_normalise_overround(self):
        st = C.bracket_stats([((None, 100), 0.2), ((100, 110), 0.6), ((110, None), 0.4)])
        self.assertAlmostEqual(st['overround'], 1.2)
        self.assertAlmostEqual(st['median']['value'], 100 + 10 * (0.5 - 1 / 6) / 0.5)   # 1/6 below 100, 1/2 of the mass in 100–110

    def test_resolved_range(self):
        pts = [((100, 100), 0, True), ((110, 110), 0, True), ((120, 120), 0, False)]
        self.assertEqual(C.resolved_range('above', pts), [110, 120])
        self.assertEqual(C.resolved_range('bracket', [((None, 100), 0, False), ((100, 110), 0, True)]), [100, 110])


class Mapping(unittest.TestCase):
    def setUp(self):
        self.m = C.Mapper(COS)

    def test_ticker_in_title(self):
        self.assertEqual(self.m.from_text('Will FedEx (FDX) beat quarterly earnings?')['ticker'], 'FDX')
        self.assertEqual(self.m.ticker('BRK-B')['ticker'], 'BRK.B')

    def test_generic_tag_needs_the_title_to_back_it(self):
        self.assertIsNone(self.m.from_text('Will OpenAI launch a phone?', ['tech', 'ai']))         # tag 'tech' is not Bio-Techne
        self.assertEqual(self.m.from_text('Nvidia’s Market Cap end of 2026?', ['nvda', 'stocks'])['ticker'], 'NVDA')
        self.assertEqual(self.m.from_text('Will MicroStrategy be margin called?', ['mstr'])['ticker'], 'MSTR')

    def test_ambiguous_words_do_not_match(self):
        self.assertIsNone(self.m.from_text('Super Bowl ad from an AI lab?'))
        self.assertEqual(self.m.from_text('Will Apple release a foldable iPhone?')['ticker'], 'AAPL')

    def test_kalshi_series(self):
        S = [{'ticker': 'KXNVDAA', 'title': 'NVIDIA annual KPI', 'category': 'Companies', 'tags': ['KPIs']},
             {'ticker': 'KXEARNINGSMENTIONAAPL', 'title': 'What will Apple say on its earnings call?', 'category': 'Mentions', 'tags': []},
             {'ticker': 'KXSUPERBOWLAD', 'title': 'Super Bowl ads', 'category': 'Companies', 'tags': []}]
        got = [(s['ticker'], c['ticker'], k) for s, c, k in C.kalshi_company(S, self.m)]
        self.assertEqual(got, [('KXNVDAA', 'NVDA', 'kpi'), ('KXEARNINGSMENTIONAAPL', 'AAPL', 'mention')])


class Scan(unittest.TestCase):
    def test_poly_scan_classifies(self):
        ev = [{'id': 1, 'title': 'Will FedEx (FDX) beat quarterly earnings?', 'slug': 'fdx-q', 'endDate': '2026-12-17T00:00:00Z', 'tags': [{'slug': 'fdx'}],
               'markets': [mk('', 'a', 0.62, slug='fdx-quarterly-earnings-nongaap-eps-12-16-2026-4pt05')]},
              {'id': 2, 'title': 'Will NVIDIA (NVDA) close above ___ end of October?', 'slug': 'nvda-above', 'endDate': '2026-10-30T20:00:00Z',
               'tags': [], 'markets': [mk('$190', 'b', 0.9), mk('$200', 'c', 0.7), mk('$210', 'd', 0.3), mk('$220', 'e', 0.1)]},
              {'id': 3, 'title': 'What will Apple (AAPL) hit in October 2026?', 'slug': 'aapl-hit', 'endDate': '2026-11-01T00:00:00Z', 'tags': [],
               'markets': [mk('↑ $360', 'f', 0.3), mk('↑ $350', 'g', 0.7), mk('↓ $320', 'h', 0.2), mk('↓ $330', 'i', 0.6)]},
              {'id': 4, 'title': 'Which companies will be acquired before 2027?', 'slug': 'acq', 'endDate': '2027-01-01T00:00:00Z', 'tags': [],
               'markets': [mk('Super Micro', 'j', 0.05), mk('Unknown Co', 'k', 0.1)]}]
        h = FakeHttp({'tag_slug=earnings&closed=false&limit=100&offset=0': ev})
        out = C.poly_scan(h, C.Mapper(COS), verbose=False)
        by = {m['kind']: m for m in out}
        b = by['beat']
        self.assertEqual((b['ticker'], b['basis'], b['report_date'], b['eps_strike'], b['p']), ('FDX', 'nongaap', '2026-12-16', 4.05, 0.62))
        self.assertAlmostEqual(by['above']['stats']['median']['value'], 205.0)
        self.assertAlmostEqual(by['hit']['stats_high']['median']['value'], 355.0)
        self.assertAlmostEqual(by['hit']['stats_low']['median']['value'], 327.5)
        self.assertEqual([(m['ticker'], m['outcomes'][0]['q']) for m in out if m['kind'] == 'other'], [('SMCI', 'Super Micro')])


class KalshiScan(unittest.TestCase):
    def test_kpi_ladder(self):
        with tempfile.TemporaryDirectory() as d:
            series = {'series': [{'ticker': 'KXTSLAA', 'title': 'Tesla total deliveries in 2026', 'category': 'Companies', 'tags': []}]}
            mk_ = lambda k, b, a: {'strike_type': 'greater', 'floor_strike': k, 'yes_bid_dollars': str(b), 'yes_ask_dollars': str(a), 'yes_sub_title': f'Above {k}',
                                   'close_time': '2027-01-02T00:00:00Z', 'volume_fp': '10'}
            ev = {'events': [{'title': 'Tesla deliveries 2026', 'markets': [mk_(1.4e6, .85, .87), mk_(1.6e6, .45, .47), mk_(1.8e6, .05, .07)]}]}
            h = FakeHttp({'series?category=Companies': series, 'series_ticker=KXTSLAA': ev, 'series?category=': {'series': []}})
            out = C.kalshi_scan(h, d, C.Mapper(COS + [{'cik': 9, 'ticker': 'TSLA', 'name': 'Tesla, Inc.', 'revenue': 1e11}]), verbose=False)
            self.assertEqual((out[0]['ticker'], out[0]['kind']), ('TSLA', 'kpi'))
            self.assertAlmostEqual(out[0]['stats']['median']['value'], 1.6e6 - 0.2e6 * (0.5 - 0.46) / (0.86 - 0.46))


YAHOO = {'quoteSummary': {'result': [{
    'financialData': {'currentPrice': {'raw': 200.0}, 'targetMeanPrice': {'raw': 230.0}, 'targetHighPrice': {'raw': 300.0}, 'targetLowPrice': {'raw': 150.0},
                      'targetMedianPrice': {'raw': 228.0}, 'numberOfAnalystOpinions': {'raw': 40}, 'recommendationMean': {'raw': 1.8}, 'recommendationKey': 'buy'},
    'earningsTrend': {'trend': [{'period': '0q', 'endDate': '2026-09-30', 'earningsEstimate': {'avg': {'raw': 1.5}, 'low': {'raw': 1.3}, 'high': {'raw': 1.7}, 'numberOfAnalysts': {'raw': 30}},
                                 'revenueEstimate': {'avg': {'raw': 9e10}}, 'epsTrend': {'current': {'raw': 1.5}, '30daysAgo': {'raw': 1.4}},
                                 'epsRevisions': {'upLast30days': {'raw': 5}}},
                                {'period': '-5d'}]},
    'earningsHistory': {'history': [{'quarter': {'fmt': '2026-06-30'}, 'epsEstimate': {'raw': 1.0}, 'epsActual': {'raw': 1.1}}]},
    'earnings': {'earningsChart': {'quarterly': [{'periodEndDate': {'fmt': '2026-06-30'}, 'reportedDate': {'fmt': '2026-07-30'}}]}},
    'calendarEvents': {'earnings': {'earningsDate': [{'fmt': '2026-10-30'}], 'isEarningsDateEstimate': False}},
    'upgradeDowngradeHistory': {'history': [{'epochGradeDate': 1790000000, 'firm': 'X', 'toGrade': 'Buy', 'fromGrade': 'Hold', 'action': 'up', 'currentPriceTarget': 250}]},
    'defaultKeyStatistics': {'sharesOutstanding': {'raw': 1e9}}}]}}


class Analysts(unittest.TestCase):
    def test_parse(self):
        a = C.parse_yahoo(YAHOO)
        self.assertEqual(a['targets']['mean'], 230.0)
        self.assertEqual([p['period'] for p in a['periods']], ['0q'])
        self.assertEqual(a['periods'][0]['eps']['numberOfAnalysts'], 30)
        self.assertEqual(a['next_earnings']['date'], '2026-10-30')
        s = a['surprises'][0]
        self.assertEqual((s['quarter'], s['reported']), ('2026-06-30', '2026-07-30'))
        self.assertAlmostEqual(s['surprise'], 0.1)
        self.assertEqual(a['actions'][0]['target'], 250)

    def test_collect_snapshots_and_build(self):
        with tempfile.TemporaryDirectory() as d:
            ix = Path(d) / 'ix.json'; ix.write_text(json.dumps({'companies': COS}))
            h = FakeHttp({'getcrumb': b'crumb', 'quoteSummary/AAPL': YAHOO})
            C.time.sleep = lambda s: None
            res = C.collect_analysts(h, d, C.universe(ix), minutes=1)
            self.assertEqual(res['this_run'], 1)
            rec = json.loads((Path(d) / 'companies' / '1.json').read_text())
            self.assertEqual(list(rec['snapshots'].values())[0][1], 1.5)
            again = C.collect_analysts(h, d, C.universe(ix), minutes=1)      # fresh and failed ones are not refetched
            self.assertEqual((again['this_run'], again['errors']), (0, 0))
            C.write_json(Path(d) / 'cache' / 'markets_now.json', {'markets': [
                {'source': 'polymarket', 'kind': 'above', 'ticker': 'AAPL', 'cik': 1, 'title': 't', 'url': 'u', 'end': '2099-01-01', 'closed': False,
                 'stats': C.ladder_stats([(190, .8), (210, .2)])}]})
            C.build(d, None, verbose=False)
            doc = json.loads((Path(d) / 'public' / 'c' / '1.json').read_text())
            self.assertAlmostEqual(doc['markets'][0]['implied_price']['median'], 200.0)
            ix2 = json.loads((Path(d) / 'public' / 'index.json').read_text())
            row = dict(zip(ix2['fields'], next(r for r in ix2['rows'] if r[1] == 'AAPL')))
            self.assertEqual((row['eps_q'], row['pm_implied_price'], row['beat_rate']), (1.5, 200.0, 1.0))


class Calibration(unittest.TestCase):
    def test_brier(self):
        c = {'1': {'p_day_before': 0.9, 'yes': True}, '2': {'p_day_before': 0.2, 'yes': False}, '3': {'p_day_before': 0.6, 'yes': False}}
        r = C.calibration(c)
        self.assertEqual(r['n'], 3)
        self.assertAlmostEqual(r['brier'], (0.01 + 0.04 + 0.36) / 3)
        self.assertAlmostEqual(r['hit_rate'], 2 / 3)

    def test_price_ledger_freezes_then_scores(self):
        with tempfile.TemporaryDirectory() as d:
            m = {'source': 'polymarket', 'kind': 'above', 'ticker': 'AAPL', 'cik': 1, 'title': 't', 'url': 'u', 'end': '2026-10-30', 'closed': False,
                 'stats': C.ladder_stats([(190, .9), (200, .5), (210, .1)])}
            C.update_price_ledger(d, [m], '2026-10-20')
            C.update_price_ledger(d, [{**m, 'closed': True, 'stats': None, 'actual': [205, 210]}], '2026-10-31')
            r = C.score_price_ledger(C.read_json(Path(d) / 'cache' / 'price_ledger.json', {}))
            self.assertEqual(r['n'], 1)
            self.assertAlmostEqual(r['rows'][0]['err_pct'], (200 / 207.5 - 1) * 100)
            self.assertTrue(r['rows'][0]['inside80'])


if __name__ == '__main__':
    unittest.main()
