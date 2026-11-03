"""13F back-fill: a fake SEC answers two quarters of one manager; the worker writes the collector's files and its
state, and the collector merges the finished manager into live.json without re-processing it."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import backfill13f as B  # noqa: E402
import holdings as H  # noqa: E402


def cover(period, value):
    return (f'<edgarSubmission xmlns="urn:cover"><formData><coverPage><reportCalendarOrQuarter>{period}</reportCalendarOrQuarter>'
            f'<filingManager><name>Test Manager</name></filingManager></coverPage><summaryPage><tableEntryTotal>1</tableEntryTotal>'
            f'<tableValueTotal>{value}</tableValueTotal><isConfidentialOmitted>false</isConfidentialOmitted></summaryPage></formData></edgarSubmission>').encode()


def table(shares, value):
    return (f'<informationTable xmlns="urn:table"><infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>'
            f'<cusip>037833100</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType>'
            f'</shrsOrPrnAmt></infoTable></informationTable>').encode()


class FakeSec:
    calls = bytes = 0

    def __init__(self):
        self.docs = {
            'https://data.sec.gov/submissions/CIK0000000042.json': json.dumps({'name': 'TEST MANAGER', 'filings': {'recent': {
                'form': ['13F-HR', '13F-HR'], 'accessionNumber': ['0000000042-25-000001', '0000000042-25-000002'],
                'filingDate': ['2025-05-15', '2025-08-14'], 'acceptanceDateTime': ['', ''], 'primaryDocument': ['primary_doc.xml', 'primary_doc.xml']},
                'files': []}}).encode()}
        for acc, period, sh, val in (('000000004225000001', '03-31-2025', 10, 1000), ('000000004225000002', '06-30-2025', 15, 1800)):
            base = f'https://www.sec.gov/Archives/edgar/data/42/{acc}/'
            self.docs[base + 'index.json'] = json.dumps({'directory': {'item': [{'name': 'primary_doc.xml'}, {'name': 'infotable.xml'}]}}).encode()
            self.docs[base + 'primary_doc.xml'] = cover(period, val)
            self.docs[base + 'infotable.xml'] = table(sh, val)

    def get(self, url, immutable=False):
        self.calls += 1
        if url not in self.docs:
            raise RuntimeError('HTTP 404 ' + url)
        return self.docs[url]

    def json(self, url, immutable=False):
        return json.loads(self.get(url))


class Backfill(unittest.TestCase):
    def test_writes_collector_files_and_merges(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'catalogs').mkdir()
            (d / 'catalogs' / 'holdings.json').write_text(json.dumps([
                {'cik': '42', 'name': 'Test Manager', 'kind': 'holdings', 'processed': False, 'latest_filing': '2025-08-14', 'filing_count': 2},
                {'cik': '7', 'name': 'Done Already', 'kind': 'holdings', 'processed': True, 'latest_filing': '2025-08-14', 'filing_count': 2},
                {'cik': '9', 'name': 'Broken', 'kind': 'holdings', 'processed': False, 'latest_filing': '2025-01-14', 'filing_count': 1}]))
            cfg = {'since': '2025-01-01'}
            stats = B.run(d, cfg, minutes=1, sec=FakeSec())
            self.assertEqual((stats['managers'], stats['errors'], stats['remaining']), (1, 1, 0))   # 9 waits out its back-off
            st = json.loads((d / 'holdings-backfill.json').read_text())
            row = st['managers']['42']
            self.assertEqual((row['period_count'], row['latest_period'], row['cache'], row['shard']),
                             (2, '2025-06-30', 'cache/holdings/42.json.gz', 'shards/holdings/42.json'))
            with gzip.open(d / row['cache'], 'rt') as f:
                full = json.load(f)
            self.assertEqual(full['snapshots'][-1]['changes'][0]['status'], 'INCREASE')
            self.assertTrue((d / 'shards' / 'holdings' / '42-2025-06-30.json').exists())
            self.assertIn('retry_after', st['attempts']['9'])
            # a second run has nothing to do
            self.assertEqual(B.run(d, cfg, minutes=1, sec=FakeSec())['managers'], 0)
            # the collector merges the finished manager and, with backfill_separately, takes no new manager itself
            out = H.collect_holdings(None, {**cfg, '_data_root': str(d), 'managers': [], 'backfill_separately': True, 'batch_size': 4},
                                     {'managers': [], 'discovery': {'directory': [{'cik': '42', 'name': 'Test Manager', 'kind': 'holdings'},
                                                                                  {'cik': '9', 'name': 'Broken', 'kind': 'holdings'}]}})
            self.assertEqual([m['cik'] for m in out['managers']], ['42'])
            self.assertEqual(out['counts']['attempted_this_run'], 0)
            self.assertTrue(next(r for r in out['directory'] if r['cik'] == '42')['processed'])

    def test_only_an_sec_block_stops_the_run(self):
        class Odd(FakeSec):                  # a parse error whose text happens to contain "403", then SEC's real block
            def get(self, url, immutable=False):
                if '/data/7/' in url or 'CIK0000000007' in url:
                    raise ValueError('Value reconciliation failed: 124294149 vs 31312403')
                if 'CIK0000000005' in url:
                    raise B.Blocked('HTTP 403 from SEC (rate limit?)')
                return super().get(url, immutable)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'catalogs').mkdir()
            (d / 'catalogs' / 'holdings.json').write_text(json.dumps([
                {'cik': '7', 'name': 'Odd', 'processed': False, 'latest_filing': '2025-09-01'},
                {'cik': '42', 'name': 'Test Manager', 'processed': False, 'latest_filing': '2025-08-14'},
                {'cik': '5', 'name': 'Blocked', 'processed': False, 'latest_filing': '2025-07-01'},
                {'cik': '3', 'name': 'Never reached', 'processed': False, 'latest_filing': '2025-06-01'}]))
            stats = B.run(d, {'since': '2025-01-01'}, minutes=1, sec=Odd())
            self.assertEqual((stats['managers'], stats['errors']), (1, 2))
            self.assertTrue(stats['blocked'].startswith('HTTP 403'))
            self.assertNotIn('3', json.loads((d / 'holdings-backfill.json').read_text())['attempts'])

    def test_range_change_starts_over(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'catalogs').mkdir()
            (d / 'catalogs' / 'holdings.json').write_text('[]')
            (d / 'holdings-backfill.json').write_text(json.dumps({'since': '2024-01-01', 'managers': {'1': {}}}))
            B.run(d, {'since': '2025-01-01'}, minutes=1, sec=FakeSec())
            self.assertEqual(json.loads((d / 'holdings-backfill.json').read_text())['managers'], {})


class WatchedHistory(unittest.TestCase):
    def test_a_watched_fund_carries_its_history_from_watch_since(self):
        """The watched funds (config holdings.watch) and the listed managers are read from `watch_since` (the 13F XML
        era) rather than the universe's `since`; a row read with the shallow range is read again, and every other
        manager keeps the universe's range."""
        sec = FakeSec()
        sec.docs['https://data.sec.gov/submissions/CIK0000000042.json'] = json.dumps({'name': 'TEST MANAGER', 'filings': {'recent': {
            'form': ['13F-HR', '13F-HR', '13F-HR'], 'accessionNumber': ['0000000042-14-000001', '0000000042-25-000001', '0000000042-25-000002'],
            'filingDate': ['2014-02-14', '2025-05-15', '2025-08-14'], 'acceptanceDateTime': ['', '', ''],
            'primaryDocument': ['primary_doc.xml', 'primary_doc.xml', 'primary_doc.xml']}, 'files': []}}).encode()
        base = 'https://www.sec.gov/Archives/edgar/data/42/000000004214000001/'
        sec.docs[base + 'index.json'] = json.dumps({'directory': {'item': [{'name': 'primary_doc.xml'}, {'name': 'infotable.xml'}]}}).encode()
        sec.docs[base + 'primary_doc.xml'] = cover('12-31-2013', 500)
        sec.docs[base + 'infotable.xml'] = table(5, 500)

        class Client:
            def get(self, url, sec=False):
                return FakeSec.get(sec_, url)

            def json(self, url, sec=False):
                return json.loads(FakeSec.get(sec_, url))
        sec_ = sec
        with tempfile.TemporaryDirectory() as d:
            cfg = {'since': '2025-01-01', 'watch_since': '2013-06-30', 'watch': [{'cik': '42', 'name': 'Test Manager'}], 'managers': [],
                   'batch_size': 4, '_data_root': d, 'discover_all': False}
            import datetime as dt
            recent = dt.datetime.now(dt.timezone.utc).isoformat()
            old = {'managers': [{'cik': '42', 'name': 'TEST MANAGER', 'since': '2025-01-01', 'snapshots': [], 'filings': [], 'last_success': recent}],
                   'attempts': {'42': {'last_attempt': recent, 'last_success': recent}}, 'discovery': {'directory': []}}
            out = H.collect_holdings(Client(), cfg, old)            # read an hour ago with the shallow range: due again at once
            m = next(x for x in out['managers'] if x['cik'] == '42')
            self.assertEqual(m['since'], '2013-06-30')
            self.assertEqual([x['period'] for x in m['snapshots']], ['2013-12-31', '2025-03-31', '2025-06-30'])
            # not watched: the universe's range, the 2013 filing left alone
            cfg2 = {**cfg, 'watch': [], 'managers': [{'cik': '42', 'name': 'Test Manager'}], 'watch_since': None}
            fresh = {**old, 'managers': [], 'attempts': {}}                   # never read: the universe's range
            m2 = next(x for x in H.collect_holdings(Client(), cfg2, fresh)['managers'] if x['cik'] == '42')
            self.assertEqual((m2['since'], [x['period'] for x in m2['snapshots']]), ('2025-01-01', ['2025-03-31', '2025-06-30']))

    def test_a_manager_keeps_the_range_on_file_until_the_relay_deepens_it(self):
        """A manager outside the watch list is refreshed with the range of its reading on file (the relay deepens it by
        size); a merged relay row with a deeper date carries that date on, and the catalog row shows the range and size."""
        sec = FakeSec()

        class Client:
            def get(self, url, sec=False):
                return FakeSec.get(sec_, url)

            def json(self, url, sec=False):
                return json.loads(FakeSec.get(sec_, url))
        sec_ = sec
        with tempfile.TemporaryDirectory() as d:
            cfg = {'since': '2025-01-01', 'watch_since': '2013-06-30', 'watch': [], 'managers': [], 'tiers': [[0, 500, '2021-01-01']],
                   'batch_size': 4, '_data_root': d, 'discover_all': False}
            old = {'managers': [{'cik': '42', 'name': 'TEST MANAGER', 'since': '2021-01-01', 'snapshots': [], 'filings': [], 'last_success': '2020-01-01T00:00:00+00:00'}],
                   'attempts': {}, 'discovery': {'directory': [{'cik': '42', 'name': 'Test Manager', 'kind': 'holdings'}]}}
            out = H.collect_holdings(Client(), cfg, old)
            m = next(x for x in out['managers'] if x['cik'] == '42')
            self.assertEqual(m['since'], '2021-01-01')                      # the deeper reading on file is kept, not the universe's 2025
            row = next(r for r in out['directory'] if r['cik'] == '42')
            self.assertEqual((row['since'], row['total_usd'], row['position_count']), ('2021-01-01', 1800.0, 1))


class Tiers(unittest.TestCase):
    def test_target_since_by_size(self):
        from holdings13f.ranges import target_since, size_of
        cfg = {'since': '2025-01-01', 'watch_since': '2013-06-30', 'watch': [{'cik': '1067983'}], 'managers': [],
               'tiers': [[1e9, 500, '2013-06-30'], [0, 500, '2021-01-01']]}
        self.assertEqual(target_since(cfg, '1067983'), '2013-06-30')                          # watched
        self.assertEqual(target_since(cfg, '42'), '2025-01-01')                               # size unknown: the universe's range
        self.assertEqual(target_since(cfg, '42', 5e9, 40), '2013-06-30')                      # a large concentrated fund
        self.assertEqual(target_since(cfg, '42', 5e9, 4000), '2025-01-01')                    # an index giant: no tier
        self.assertEqual(target_since(cfg, '42', 2e8, 60), '2021-01-01')                      # the long tail
        self.assertEqual(target_since(cfg, '42', 2e8, 60, current='2016-01-01'), '2016-01-01')   # never shallower than on file
        self.assertEqual(size_of({'total_usd': 5, 'position_count': 2}), (5.0, 2))
        self.assertEqual(size_of({'snapshots': [{'total_usd': 7, 'positions': [{}, {}, {}]}]}), (7.0, 3))
        self.assertEqual(size_of({}), (None, None))

    def test_the_relay_deepens_processed_managers_by_tier(self):
        """After the first pass, the relay reads the managers whose size calls for a deeper date again from that date:
        the largest first, the index giants and the managers already deep enough left alone."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'catalogs').mkdir()
            (d / 'catalogs' / 'holdings.json').write_text(json.dumps([
                {'cik': '42', 'name': 'Test Manager', 'kind': 'holdings', 'processed': True, 'latest_filing': '2025-08-14', 'filing_count': 2,
                 'since': '2025-01-01', 'total_usd': 1800, 'position_count': 1},
                {'cik': '7', 'name': 'Giant', 'kind': 'holdings', 'processed': True, 'latest_filing': '2025-08-14', 'filing_count': 2,
                 'since': '2025-01-01', 'total_usd': 5e11, 'position_count': 4000},
                {'cik': '8', 'name': 'Deep already', 'kind': 'holdings', 'processed': True, 'latest_filing': '2025-08-14', 'filing_count': 2,
                 'since': '2013-06-30', 'total_usd': 3e9, 'position_count': 30},
                {'cik': '9', 'name': 'Unknown size', 'kind': 'holdings', 'processed': True, 'latest_filing': '2025-08-14', 'filing_count': 2}]))
            cfg = {'since': '2025-01-01', 'tiers': [[1e9, 500, '2013-06-30'], [0, 500, '2021-01-01']]}
            todo = B.pending(json.loads((d / 'catalogs' / 'holdings.json').read_text()), {}, cfg=cfg)
            self.assertEqual([(r['cik'], r['since']) for r in todo], [('42', '2021-01-01')])
            stats = B.run(d, cfg, minutes=1, sec=FakeSec())
            self.assertEqual((stats['managers'], stats['remaining']), (1, 0))
            st = json.loads((d / 'holdings-backfill.json').read_text())
            self.assertEqual(st['managers']['42']['since'], '2021-01-01')      # the relay's row carries the deeper date on
            self.assertEqual(B.run(d, cfg, minutes=1, sec=FakeSec())['managers'], 0)
            # the relay's own earlier row (a shallow first pass) is deepened too, by the size it recorded
            st['managers']['42'] = {**st['managers']['42'], 'since': '2025-01-01', 'total_usd': 2e9, 'position_count': 1}
            (d / 'holdings-backfill.json').write_text(json.dumps(st))
            todo = B.pending(json.loads((d / 'catalogs' / 'holdings.json').read_text()), st, cfg=cfg)
            self.assertEqual([(r['cik'], r['since']) for r in todo], [('42', '2013-06-30')])


if __name__ == '__main__':
    unittest.main()
