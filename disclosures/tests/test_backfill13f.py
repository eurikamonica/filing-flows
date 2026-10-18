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

    def test_range_change_starts_over(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'catalogs').mkdir()
            (d / 'catalogs' / 'holdings.json').write_text('[]')
            (d / 'holdings-backfill.json').write_text(json.dumps({'since': '2024-01-01', 'managers': {'1': {}}}))
            B.run(d, {'since': '2025-01-01'}, minutes=1, sec=FakeSec())
            self.assertEqual(json.loads((d / 'holdings-backfill.json').read_text())['managers'], {})


if __name__ == '__main__':
    unittest.main()
