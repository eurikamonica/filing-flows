"""Regressions behind red Actions runs: the site index's formatted revenue, Form 4 rows without a value, partial sources."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))


class Universe(unittest.TestCase):
    def test_formatted_revenue_and_null(self):
        import consensus
        import debt
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'index.json'
            # the site index: 'rev' is a display string, 'revenue' is null for companies without a revenue line
            p.write_text(json.dumps({'companies': [{'cik': 1, 'ticker': 'aa', 'rev': '$2.6B', 'revenue': None},
                                                   {'cik': 2, 'ticker': 'bb', 'rev': '$9.0B', 'revenue': 9e9},
                                                   {'cik': 3, 'ticker': 'cc', 'rev': '$1B', 'revenue': '1e9'}]}))
            self.assertEqual([r['ticker'] for r in consensus.universe(p)][0], 'BB')
            self.assertEqual([r['revenue'] for r in debt.universe(p)], [9e9, 0, 0])


class PartialIsAWarning(unittest.TestCase):
    def test_flag(self):
        import collect
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertFalse(collect._flag('npx', {'status': 'ok'}))
            self.assertFalse(collect._flag('npx', {'status': 'partial', 'error': 'response size limit'}))
            self.assertTrue(collect._flag('congress', {'status': 'error', 'error': 'HTTP 503'}))
        out = buf.getvalue()
        self.assertIn('::warning::npx: partial — response size limit', out)
        self.assertIn('::error::congress: error — HTTP 503', out)


if __name__ == '__main__':
    unittest.main()
