"""Fast CBOE collection: offline fixtures, no network and no simulated quotes on site."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import options


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class FakeClient:
    def json(self, url):
        if url.endswith('/NVDA.json'):
            raise RuntimeError('HTTP 429 from cdn.cboe.com')
        return {'timestamp': '2026-10-26 14:45:00', 'data': {'options': []}}


def fresh_summary(ticker, *args):
    return (
        {'ticker': ticker, 'spot': 250.0, 'iv30': 30.0, 'pc_oi': 1.3,
         'net_gex': 1200, 'skew25': 0.02, 'contracts': 600},
        {'ticker': ticker, 'spot': 250.0, 'paths': [{'exp': '2026-12-18'}],
         'path_probs': [0.05, 0.5, 0.95]},
    )


class SupplementOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.market = self.root / 'market'
        self.out = self.market / 'options'
        self.out.mkdir(parents=True)

    def test_missing_paths_are_prioritized_and_explicit_requests_go_first(self):
        save(self.out / 'AAPL.json', {'ticker': 'AAPL', 'paths': [{'exp': '2027-01-15'}]})
        save(self.out / 'MSFT.json', {'ticker': 'MSFT', 'smiles': []})
        save(self.out / 'NVDA.json', {'ticker': 'NVDA', 'paths': []})
        cfg = {'fast_priority': ['AAPL', 'MSFT', 'NVDA'], 'always': ['AAPL'],
               'from_signals': 0, 'from_13f': 0, 'fast_max_tickers': 2}
        self.assertEqual(options.fast_underlyings(self.root, cfg), ['MSFT', 'NVDA'])
        self.assertEqual(options.fast_underlyings(self.root, cfg, ('TSLA',))[0], 'TSLA')

    def test_failed_cboe_query_preserves_valid_old_row_and_file(self):
        old = {'ticker': 'NVDA', 'spot': 200, 'iv30': 25, 'as_of': '2026-10-23 20:00:00'}
        save(self.market / 'options.json', {'rows': [old], 'generated_at': '2026-10-23'})
        save(self.out / 'NVDA.json', {'ticker': 'NVDA', 'as_of': old['as_of'],
                                      'paths': [{'exp': '2026-11-20'}]})
        cfg = {'fast_priority': ['AAPL', 'NVDA'], 'always': ['AAPL', 'NVDA'],
               'from_signals': 0, 'from_13f': 0, 'fast_max_tickers': 2}
        with patch.object(options, 'parse_chain', return_value=(250, 30, 0, [])), \
             patch.object(options, 'summarise', side_effect=fresh_summary):
            result = options.collect(FakeClient(), self.root, cfg, fast=True)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['underlyings'], 2)
        current = json.loads((self.market / 'options.json').read_text())
        rows = {r['ticker']: r for r in current['rows']}
        self.assertEqual(rows['NVDA']['as_of'], old['as_of'])
        self.assertEqual(rows['AAPL']['as_of'], '2026-10-26 14:45:00')
        self.assertEqual(current['scan']['mode'], 'supplement')
        self.assertEqual(current['scan']['retained'], 1)
        self.assertEqual(json.loads((self.out / 'NVDA.json').read_text())['paths'][0]['exp'],
                         '2026-11-20')
        self.assertEqual(json.loads((self.out / 'AAPL.json').read_text())['paths'][0]['exp'],
                         '2026-12-18')

    def test_all_failed_preserves_history_and_marks_partial(self):
        save(self.market / 'options.json', {
            'rows': [{'ticker': 'NVDA', 'iv30': 22.0, 'spot': 100, 'as_of': '2026-10-23'}]})
        save(self.out / 'NVDA.json', {'ticker': 'NVDA', 'paths': [{'exp': '2026-12-18'}]})
        cfg = {'fast_priority': ['NVDA'], 'always': ['NVDA'],
               'from_signals': 0, 'from_13f': 0}
        result = options.collect(FakeClient(), self.root, cfg, fast=True)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['underlyings'], 1)
        self.assertEqual(json.loads((self.market / 'options.json').read_text())
                         ['rows'][0]['as_of'], '2026-10-23')
        self.assertTrue(json.loads((self.out / 'NVDA.json').read_text())['paths'])

    def test_unsourced_failure_is_not_a_fake_chain(self):
        cfg = {'fast_priority': ['NVDA'], 'always': ['NVDA'],
               'from_signals': 0, 'from_13f': 0}
        result = options.collect(FakeClient(), self.root, cfg, fast=True)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(json.loads((self.market / 'options.json').read_text())['rows'], [])


if __name__ == '__main__':
    unittest.main()
