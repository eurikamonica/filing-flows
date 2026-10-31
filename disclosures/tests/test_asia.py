"""asia.py: names of US companies as Asian reports write them, the collect queue, the build (relations per US company,
amounts from shares, anonymous customers kept out)."""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import asia as A  # noqa: E402

UNI = [{'cik': 320193, 'ticker': 'AAPL', 'name': 'Apple Inc.'}, {'cik': 1045810, 'ticker': 'NVDA', 'name': 'NVIDIA CORP'},
       {'cik': 1046179, 'ticker': 'TSM', 'name': 'TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD'}, {'cik': 313838, 'ticker': 'SONY', 'name': 'Sony Group Corp'},
       {'cik': 354950, 'ticker': 'HD', 'name': 'HOME DEPOT, INC.'}, {'cik': 1018724, 'ticker': 'AMZN', 'name': 'AMAZON COM INC'}]


class Names(unittest.TestCase):
    def test_match(self):
        m = A.Matcher(UNI)
        for label, t in [('アップル', 'AAPL'), ('Apple Inc.', 'AAPL'), ('Apple Operations International', 'AAPL'), ('蘋果', 'AAPL'),
                         ('애플', 'AAPL'), ('輝達', 'NVDA'), ('NVIDIA Corporation', 'NVDA'), ('台積電', 'TSM'), ('ソニーグループ株式会社', 'SONY'),
                         ('The Home Depot, Inc.', 'HD'), ('ＡＰＰＬＥ　ＩＮＣ．', 'AAPL'), ('Amazon.com, Inc.', 'AMZN')]:
            c = m(label)
            self.assertIsNotNone(c, label)
            self.assertEqual(c['ticker'], t, label)
        for label in ['A社', '甲公司', '客戶A', 'B', 'Hong Kong Techtronics', 'Deutsche Telekom']:
            self.assertIsNone(m(label), label)


class Flow(unittest.TestCase):
    def test_collect_and_build(self):
        fake = types.SimpleNamespace(
            list_reports=lambda http, since, until, key=None: [{'id': 'r1', 'code': '6857', 'name': '株式会社アドバンテスト', 'filed': '2026-06-20'},
                                                              {'id': 'r2', 'code': '7777', 'name': 'X', 'filed': '2026-06-21'}],
            read_report=lambda http, rep, key=None: (
                {'code': '6857', 'name': '株式会社アドバンテスト', 'name_en': 'ADVANTEST CORPORATION', 'fy': '2026-03-31', 'currency': 'JPY',
                 'revenue': 1_000_000_000_000, 'rows': [
                     {'role': 'customer', 'label': 'Taiwan Semiconductor Manufacturing Company, Ltd.', 'amount': 150_000_000_000, 'share': 0.15, 'sentence': 'TSMC 150,000 15.0%'},
                     {'role': 'customer', 'label': 'アップル', 'amount': None, 'share': 0.2, 'sentence': 'アップル 20.0%'},
                     {'role': 'customer', 'label': 'A社', 'amount': 1e11, 'share': 0.1, 'anonymous': True}],
                 'concentration': {}} if rep['id'] == 'r1' else None))
        with tempfile.TemporaryDirectory() as d:
            orig = A.module
            A.module = lambda mk: fake
            os.environ['EDINET_API_KEY'] = 'k'
            try:
                st = A.collect(d, markets=['jp'], minutes=1, http=object())
            finally:
                A.module = orig
                del os.environ['EDINET_API_KEY']
            self.assertEqual(st['jp']['read'], 2)
            st2 = A.collect(d, markets=['jp'], minutes=1, http=object())          # no EDINET key: skipped, not an error
            self.assertIn('skipped', st2['jp'])
            u = Path(d) / 'u.json'
            u.write_text(json.dumps({'companies': UNI}))
            b = A.build(d, u)
            self.assertEqual(b['markets']['jp']['named'], 2)
            aapl = json.loads((Path(d) / 'public' / 'c' / '320193.json').read_text())
            s = aapl['suppliers'][0]
            self.assertEqual((s['name_en'], s['share'], s['computed']), ('ADVANTEST CORPORATION', 0.2, True))
            self.assertEqual(s['usd'], round(0.2 * 1e12 / 150))
            tsm = json.loads((Path(d) / 'public' / 'c' / '1046179.json').read_text())
            self.assertEqual(tsm['suppliers'][0]['usd'], 1_000_000_000)


if __name__ == '__main__':
    unittest.main()
