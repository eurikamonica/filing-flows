"""4.6 collectors: Schedules 13D / 13G and Form 144 (app/ownership.py), FINRA short interest (app/shorts.py) and US Senate
PTRs (app/senate.py), against real EDGAR / FINRA / eFD samples (tests/fixtures; trimmed copies of filings of Oct 16 2026)."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import market
import ownership as O
import senate as SEN
import shorts as SH

FIX = Path(__file__).resolve().parent / 'fixtures'
read = lambda name: (FIX / name).read_text(encoding='utf-8')


def tickers(root, rows):
    p = Path(root) / 'cache' / 'prices'
    p.mkdir(parents=True, exist_ok=True)
    (p / 'sec-tickers.json').write_text(json.dumps({'fetched_at': '2026-10-17T00:00:00+00:00', 'rows': rows}))


class Stakes(unittest.TestCase):
    def test_13d_amendment(self):
        txt = read('sched13d-amendment.txt')
        r = O.parse_stake(O.xml_from_submission(txt), '0001193125-26-424467', 'https://www.sec.gov/Archives/edgar/data/1265131/000119312526424467/', O.header(txt))
        self.assertEqual((r['form'], r['amendment'], r['filed'], r['event_date']), ('13D/A', 23, '2026-10-16', '2026-10-16'))
        self.assertEqual((r['issuer_cik'], r['cusip'], r['filer'], r['filer_cik']), ('1265131', '432748101', 'FORD GERALD J', '1021572'))
        self.assertEqual((r['person'], r['persons'], r['percent']), ('Gerald J. Ford', 5, 27.3))   # the largest single holding
        self.assertTrue(r['purpose'].startswith('On October 16, 2026, counsel to Gerald J. Ford delivered a letter'))   # boilerplate gone
        self.assertLessEqual(len(r['purpose']), 600)

    def test_13g_below_five_percent(self):
        txt = read('sched13g-exit.txt')
        r = O.parse_stake(O.xml_from_submission(txt), '0001104659-26-116664', 'u/', O.header(txt))
        self.assertEqual((r['form'], r['rule'], r['exit'], r['percent'], r['persons']), ('13G/A', 'passive investor', True, 4.5, 4))
        self.assertEqual((r['issuer_cik'], r['event_date']), ('1835856', '2026-09-30'))
        self.assertEqual(O.stake_label({**r, 'new': False}), 'below 5%')
        self.assertEqual(O.holder_of(r), 'Millennium Management LLC')
        self.assertEqual(O.holder_of({'person': 'Gerald J. Ford', 'filer': 'FORD GERALD J', 'person_type': 'IN'}), 'Gerald J. Ford')
        self.assertEqual(O.holder_of({'person': 'Donnalley David James', 'filer': 'Donnalley David James', 'person_type': 'IN'}), 'David James Donnalley')
        self.assertEqual(O.holder_of({'person': 'GOODMAN COREY S', 'filer': 'venBio Global Strategic Fund, L.P.', 'person_type': 'IN'}),
                         'venBio Global Strategic Fund, L.P.')

    def test_form144(self):
        txt = read('form144.txt')
        r = O.parse_form144(O.xml_from_submission(txt), '0002060619-26-000002', 'u/', O.header(txt))
        self.assertEqual((r['issuer_cik'], r['seller'], r['relationship']), ('2051380', 'Nemati Marc A.', 'Officer, Director'))
        self.assertEqual(r['seller_name'], 'Marc Nemati')             # as the filing spells it under past sales
        self.assertEqual(O.natural_name('Vittitow Matthew W.', True), 'Matthew W. Vittitow')
        self.assertEqual(O.natural_name('Vittitow Family Trust', True), 'Vittitow Family Trust')
        self.assertEqual(O.natural_name('Matthew Vittitow', False), 'Matthew Vittitow')
        self.assertEqual((r['shares'], r['value'], r['sale_date'], r['plan_date'], r['sold_3m']), (4108, 7601, '2026-10-16', '2025-09-30', 10493))
        self.assertEqual((r['broker'], r['acquired'], r['exchange']), ('Morgan Stanley', 'Vesting of restricted stock unit', 'NYSE'))

    def test_daily_index(self):
        idx = ('Form Type   Company Name                                                  CIK         Date Filed  File Name\n'
               '-' * 120 + '\n'
               '10-Q        SOME CO                                                       123         20261016    edgar/data/123/0000000123-26-000001.txt\n'
               '144         GrabAGun Digital Holdings Inc.                                2051380     20261016    edgar/data/2051380/0002060619-26-000002.txt\n'
               '144         Nemati Marc A.                                                2060619     20261016    edgar/data/2060619/0002060619-26-000002.txt\n'
               'SCHEDULE 13D/A Hilltop Holdings Inc.                                     1265131     20261016    edgar/data/1265131/0001193125-26-424467.txt\n'
               'SCHEDULE 13G/A Better Home & Finance Holding Co                         1835856     20261016    edgar/data/1835856/0001104659-26-116664.txt\n')
        got = O.parse_daily_index(idx)
        self.assertEqual([(k, a) for k, a, _ in got], [('form144', '0002060619-26-000002'), ('stakes', '0001193125-26-424467'),
                                                        ('stakes', '0001104659-26-116664')])       # once per filing, 10-Q left out
        self.assertEqual(got[1][2], 'https://www.sec.gov/Archives/edgar/data/1265131/000119312526424467/')

    def test_collect_publish_and_changes(self):
        root = Path(tempfile.mkdtemp())
        tickers(root, [{'ticker': 'HTH', 'title': 'Hilltop Holdings', 'cik': 1265131}, {'ticker': 'PGUN', 'title': 'GrabAGun', 'cik': 2051380},
                       {'ticker': 'BETR', 'title': 'Better Home', 'cik': 1835856}])
        subs = {'0001193125-26-424467': read('sched13d-amendment.txt'), '0001104659-26-116664': read('sched13g-exit.txt'),
                '0002060619-26-000002': read('form144.txt'), '0002060636-26-000002': read('form144.txt')}
        feed144 = read('feed-144.xml')

        class Client:
            calls = []

            def get(self, url, sec=False, headers=None):
                self.calls.append(url)
                if 'getcurrent' in url:
                    if 'type=144' in url and 'start=0' in url:
                        return feed144.encode()
                    return b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
                if 'daily-index' in url:
                    if url.endswith('form.20261016.idx'):
                        return ('SCHEDULE 13D/A Hilltop Holdings Inc.        1265131     20261016    edgar/data/1265131/0001193125-26-424467.txt\n'
                                'SCHEDULE 13G/A Better Home & Finance       1835856     20261016    edgar/data/1835856/0001104659-26-116664.txt\n').encode()
                    raise RuntimeError('HTTP 404 from www.sec.gov')
                for acc, txt in subs.items():
                    if url.endswith(acc + '.txt'):
                        return txt.encode()
                raise RuntimeError('HTTP 404 from www.sec.gov')

        c = Client()
        r = O.collect(c, root, {'backfill_days': 6, 'index_days_per_run': 10}, today=dt.date(2026, 10, 17))
        self.assertEqual((r['stakes'], r['form144'], r['waiting']), (2, 2, 0))       # the feed's two 144s, the index's two stakes
        self.assertIn('20261016', json.loads((root / 'cache' / 'ownership' / 'state.json').read_text())['index_days'])
        n = len(c.calls)
        O.collect(c, root, {'backfill_days': 6, 'index_days_per_run': 10}, today=dt.date(2026, 10, 17))
        self.assertFalse(any(u.endswith('.txt') for u in c.calls[n:]))                # nothing read twice
        # an earlier filing by the same holder: the change is computed against it
        store = root / 'cache' / 'ownership' / 'stakes.json.gz'
        rows = json.load(gzip.open(store, 'rt'))
        old = {**next(x for x in rows if x['form'] == '13D/A'), 'accession': '0001193125-26-000001', 'filed': '2026-05-01', 'percent': 25.1,
               'form': '13D/A', 'amendment': 22}
        with gzip.open(store, 'wt') as f:
            json.dump(rows + [old], f)
        O.publish(root, root / 'market', today=dt.date(2026, 10, 17))
        st = json.loads((root / 'market' / 'stakes.json').read_text())
        hth = next(x for x in st['latest'] if x['accession'] == '0001193125-26-424467')
        self.assertEqual((hth['ticker'], hth['prev_percent'], hth['change'], hth['label']), ('HTH', 25.1, 2.2, 'raised'))
        self.assertEqual(next(x for x in st['latest'] if x['ticker'] == 'BETR')['label'], 'below 5%')
        self.assertEqual(st['summary'][0]['ticker'], 'HTH')
        fm = json.loads((root / 'market' / 'form144.json').read_text())
        self.assertEqual((fm['on_file'], len(fm['latest']), fm['small']), (2, 0, 2))      # both notices under $100K: counted, not listed


class Shorts(unittest.TestCase):
    def rows(self, day, n, base):
        return [{'symbolCode': f'T{i}', 'issueName': f'Test {i} Inc', 'marketClassCode': 'NNM', 'settlementDate': day,
                 'currentShortPositionQuantity': base + i * 1000, 'previousShortPositionQuantity': base, 'changePercent': round(i * 1000 / base * 100, 2),
                 'averageDailyVolumeQuantity': 300_000, 'daysToCoverQuantity': 3.1, 'stockSplitFlag': None, 'revisionFlag': None}
                for i in range(n)]

    def test_collect_pages_and_publish(self):
        root = Path(tempfile.mkdtemp())
        tickers(root, [{'ticker': f'T{i}', 'title': f'T{i}', 'cik': i + 1} for i in range(6001)])
        pages = {'2026-09-30': self.rows('2026-09-30', 6000, 2_000_000), '2026-09-15': self.rows('2026-09-15', 10, 1_000_000)}

        class Client:
            posts = []

            def get(self, url, sec=False, headers=None):
                return json.dumps({'availablePartitions': [{'partitions': ['2026-09-15']}, {'partitions': ['2026-09-30']}]}).encode()

            def post_json(self, url, payload, headers=None):
                self.posts.append(payload)
                day = payload['compareFilters'][0]['fieldValue']
                return pages[day][payload['offset']:payload['offset'] + payload['limit']]

        c = Client()
        r = SH.collect(c, root, {'keep_dates': 2})
        self.assertEqual((r['fetched'], r['on_file']), ([['2026-09-30', 6000], ['2026-09-15', 10]], 2))
        self.assertEqual([p['offset'] for p in c.posts if p['compareFilters'][0]['fieldValue'] == '2026-09-30'], [0, 5000])   # paged
        out = SH.publish(root, root / 'market', min_short=2_000_000)
        d = json.loads((root / 'market' / 'short-interest.json').read_text())
        self.assertEqual((out['date'], d['previous_date'], d['shown']), ('2026-09-30', '2026-09-15', 6000))
        t5 = next(x for x in d['rows'] if x['ticker'] == 'T5')
        self.assertEqual((t5['short'], t5['change'], t5['hist']), (2_005_000, 5000, [['2026-09-15', 1_005_000], ['2026-09-30', 2_005_000]]))
        self.assertEqual(d['top']['rise'][0], 'T5999')
        self.assertEqual(SH.history_by_ticker(root)['T1'], [['2026-09-15', 1001000, 0.1, 3.1, 300000], ['2026-09-30', 2001000, 0.05, 3.1, 300000]])
        c.posts.clear()
        SH.collect(c, root, {'keep_dates': 2, 'rechecks': 1})                    # the newest date is read again once, then left
        SH.collect(c, root, {'keep_dates': 2, 'rechecks': 1})
        self.assertEqual(sum(1 for p in c.posts if p['offset'] == 0), 1)


class Senate(unittest.TestCase):
    def test_search_rows_and_report_table(self):
        rows = json.loads(read('senate-search.json'))['data']
        reps = [SEN.report_of(r) for r in rows]
        self.assertEqual((reps[2]['person'], reps[2]['filed_date']), ('James Conley Justice II', '2026-09-28'))
        rep = next(r for r in reps if r['person'] == 'Sheldon Whitehouse')
        ts = SEN.parse_ptr(read('senate-ptr.html'), rep)
        self.assertEqual(len(ts), 5)
        jpm = ts[0]
        self.assertEqual((jpm['ticker'], jpm['type'], jpm['owner'], jpm['amount_min'], jpm['amount_max'], jpm['date'], jpm['asset_type']),
                         ('JPM', 'partial sale', 'SP', 15001, 50000, '2026-09-04', 'ST'))
        self.assertEqual((jpm['jurisdiction'], jpm['read'], jpm['filed_date']), ('US Senate', 'electronic', '2026-10-01'))
        self.assertEqual(SEN.amount('Over $50,000,000'), (50000001, None))       # stored as the House stores its open top range

    def test_collect_and_merge_with_the_house(self):
        root = Path(tempfile.mkdtemp())
        search, ptr = read('senate-search.json'), read('senate-ptr.html')

        class Client:
            jar = [type('C', (), {'name': 'csrftoken', 'value': 'tok'})()]
            gets, posts = [], []

            def get(self, url, sec=False, headers=None):
                self.gets.append(url)
                if url.endswith('/search/home/'):
                    return b'<form><input type="hidden" name="csrfmiddlewaretoken" value="abc"></form>'
                if '6bf3b6f7' in url:
                    return ptr.encode()
                return b'<html><table><tbody></tbody></table></html>'

            def request(self, url, sec=False, data=None, headers=None):
                self.posts.append((url, data, headers))
                if url.endswith('/search/report/data/'):
                    return search.encode(), url, 'application/json'
                return b'', url, 'text/html'

        c = Client()
        r = SEN.collect(c, root, {'since': '2026-08-01', 'batch': 10}, today=dt.date(2026, 10, 17))
        self.assertEqual((r['found'], r['read'], r['trades'], r['waiting']), (4, 4, 5, 0))
        agree = next(p for p in c.posts if p[0].endswith('/search/home/'))
        self.assertIn(b'prohibition_agreement=1', agree[1])
        self.assertEqual(next(p for p in c.posts if p[0].endswith('/data/'))[2]['X-CSRFToken'], 'tok')
        n = len(c.gets)
        r = SEN.collect(c, root, {'since': '2026-08-01', 'batch': 10}, today=dt.date(2026, 10, 17))
        self.assertFalse(any('/view/ptr/' in u for u in c.gets[n:]))            # read reports are not read again
        tickers(root, [{'ticker': 'JPM', 'title': 'JPMorgan Chase & Co', 'cik': 19617}, {'ticker': 'V', 'title': 'VISA INC.', 'cik': 1403161},
                       {'ticker': 'ADI', 'title': 'Analog Devices', 'cik': 6281}])
        trades, stats = market.officials_trades(root, market.Universe(root), live={'modules': {}})
        sen = [t for t in trades if t['jurisdiction'] == 'US Senate']
        self.assertEqual(len(sen), 5)
        self.assertTrue(all(t['ticker_status'] == 'listed' for t in sen))
        latest, monitor = market.latest_reports(root, {'modules': {}}, trades)
        wh = next(x for x in latest if x['person'] == 'Sheldon Whitehouse')
        self.assertEqual((wh['status'], wh['trades'], wh['sells'], wh['office']), ('read', 5, 5, 'US Senate'))
        self.assertEqual(monitor['senate']['electronic_read'], 4)


if __name__ == '__main__':
    unittest.main()
