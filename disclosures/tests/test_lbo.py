"""lbo.py: deal filings from the form indexes, the company-year sample and its labels, the history model, premiums from
merger proxies, headline matching (target or buyer), rumor scores, LBO inputs and the published files."""
import datetime as dt
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import lbo as L  # noqa: E402

TODAY = dt.date(2026, 10, 30)
COS = [{'cik': 30697, 'ticker': 'WEN', 'name': "WENDY'S CO", 'sector': 'consumer-disc', 'sic': '5812', 'revenue': 2.2e9},
       {'cik': 1835632, 'ticker': 'MRVL', 'name': 'Marvell Technology, Inc.', 'sector': 'technology', 'sic': '3674', 'revenue': 7e9},
       {'cik': 1633978, 'ticker': 'LITE', 'name': 'Lumentum Holdings Inc.', 'sector': 'technology', 'sic': '3674', 'revenue': 2e9},
       {'cik': 2, 'ticker': 'OTLK', 'name': 'Outlook Therapeutics, Inc.', 'sector': 'health', 'sic': '2834', 'revenue': 1e6},
       {'cik': 3, 'ticker': 'TGT', 'name': 'TARGET CORP', 'sector': 'consumer-staples', 'sic': '5331', 'revenue': 1e11}]


def site(d):
    p = Path(d) / 'index.json'
    p.write_text(json.dumps({'companies': COS}))
    return p


class Indexes(unittest.TestCase):
    def test_parse_form_index(self):
        txt = ('Form Type   Company Name   CIK   Date Filed  File Name\n'
               'SC 13E3          Ashford Inc.                                                  1604738     2024-04-12  edgar/data/1604738/0001104659-24-046768.txt\n'
               'SC 13E3/A        Ashford Inc.                                                  1604738     2024-05-12  edgar/data/1604738/0001104659-24-056768.txt\n'
               'DEFM14A          Quanex Building Products CORP                                 1423221     2024-06-06  edgar/data/1423221/0001104659-24-068913.txt\n'
               '10-K             Apple Inc.                                                    320193      2024-11-01  edgar/data/320193/x.txt\n')
        rows = L.parse_form_index(txt)
        self.assertEqual([r[0] for r in rows], ['SC 13E3', 'DEFM14A'])        # amendments and other forms left out
        self.assertEqual(rows[0][1:4], [1604738, 'Ashford Inc.', '2024-04-12'])


class History(unittest.TestCase):
    def test_features_and_label(self):
        x = L.features({'revenue': 1e9, 'oi': 1.5e8, 'da': 5e7, 'ocf': 1.8e8, 'capex': 4e7, 'debt': 4e8, 'cash': 1e8, 'float': 1.2e9}, {'revenue': 9e8})
        self.assertAlmostEqual(x['ebitda_yield'], 2e8 / 1.5e9)
        self.assertAlmostEqual(x['net_lev'], 1.5)
        self.assertAlmostEqual(x['fcf_margin'], 0.14)
        self.assertAlmostEqual(x['growth'], 1 / 9)
        self.assertIsNone(L.features({'revenue': 1e6, 'oi': 1, 'float': 1e9}))       # too small to count
        self.assertIsNone(L.features({'revenue': 1e9, 'oi': 1e8, 'float': 1e9, 'debt': 0, 'cash': 2e9}))   # negative EV
        ev = [('2025-05-01', 'merger', 'DEFM14A', 'p')]
        self.assertEqual(L.label(ev, 2024, {'merger'}), 1)                   # April 2025 – March 2026 after fiscal 2024
        self.assertEqual(L.label(ev, 2023, {'merger'}), 0)
        self.assertEqual(L.label(ev, 2024, {'private'}), 0)

    def test_sample_and_model(self):
        rnd = random.Random(7)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            idx, gone = [], {}
            for c in range(1, 601):                                      # small companies are bought far more often
                for y in range(2011, 2024):
                    if rnd.random() < (0.12 if c <= 150 else 0.01):
                        gone[c] = y
                        idx.append(['DEFM14A', c, f'C{c}', f'{y + 1}-06-01', f'edgar/data/{c}/0000-{y}-{c}.txt'])
                        break
            idx.append(['DEFM14A', 9, 'C9', '2021-06-01', 'edgar/data/9/acq.txt'])   # an acquirer's proxy: it goes on reporting
            gone.pop(9, None)
            for y in range(2011, 2026):
                fig = {k: {'_at': 'x'} for k in L.FRAMES}
                for c in range(1, 601):
                    if c in gone and y > gone[c]:
                        continue                                         # bought: no more annual reports
                    small = c <= 150
                    fig['revenue'][str(c)] = 1e8 * rnd.uniform(0.8, 1.2) if small else 5e9 * rnd.uniform(0.8, 1.2)
                    fig['oi'][str(c)] = 1e7 * rnd.uniform(0.5, 1.5) * (1 if small else 40)
                    fig['float'][str(c)] = 1e8 * rnd.uniform(0.8, 1.2) if small else 8e9 * rnd.uniform(0.8, 1.2)
                for k, v in fig.items():
                    L.wgz(root / 'cache' / 'frames' / f'{k}-{y}.json.gz', v)
            for y in range(2011, 2027):
                L.write_json(root / 'cache' / 'index' / f'{y}Q1.json', [r for r in idx if r[3].startswith(str(y))])
            rows = L.sample(root, TODAY)
            self.assertTrue(rows)
            # a company still reporting three years later was not bought, whatever it filed
            self.assertEqual([r[3] for r in rows if r[0] == 2019 and r[1] == 9], [0])
            m = L.history_model(rows, 3)
            self.assertGreater(m['auc_test'], 0.65)
            s_small = L.score(m, rows[[r[1] for r in rows].index(1)][2])
            s_big = L.score(m, rows[[r[1] for r in rows].index(500)][2])
            self.assertGreater(s_small['p'], s_big['p'])
            self.assertEqual(s_small['drivers'][0][0], 'size')
            lifts = L.lift_tables(rows, 3)
            self.assertGreater(lifts['size'][0][2], lifts['size'][4][2])


class Premiums(unittest.TestCase):
    def test_premiums_of(self):
        t = ('The merger consideration of $32.05 per share in cash, without interest, represents a premium of approximately 18.5% over the '
             'closing price on October 1, 2026, and a premium of approximately 31% to the unaffected share price on September 12, 2026.')
        p = L.premiums_of(t)
        self.assertEqual(p[0][0], 31.0)                                       # the unaffected price first
        self.assertEqual(p[1][0], 18.5)
        self.assertEqual(float(L.CASH_PS.search(t)[1]), 32.05)
        self.assertEqual(L.premiums_of('no premium here; a 500% premium of nothing'), [])


class Rumors(unittest.TestCase):
    def test_headlines(self):
        with tempfile.TemporaryDirectory() as d:
            comps = L.OUT.universe(site(d))
        find = L.headline_matcher(comps)
        c, role = find("Wendy's Gets $1.4bn Take-Private Offer From Peltz-Led Group")
        self.assertEqual((c['ticker'], role), ('WEN', 'target'))
        c, role = find('Marvell Is in Talks to Buy an $83 Billion AI Laser Maker')
        self.assertEqual((c['ticker'], role), ('MRVL', 'buyer'))
        c, role = find('Lumentum Holdings (LITE) Is Reportedly In Advanced Acquisition Talks')
        self.assertEqual(c['ticker'], 'LITE')
        self.assertEqual(find('GFL Lifts 2026 Outlook as Take-Private Deadline Nears')[0], None)   # an ordinary word
        self.assertEqual(find('Target Hospitality explores a sale')[0], None)                     # 'Target' never alone

    def test_score(self):
        items = [{'date': '2026-10-29', 'kind': 'news'}, {'date': '2026-10-29', 'kind': 'news'}, {'date': '2026-10-29', 'kind': 'news', 'role': 'buyer'},
                 {'date': '2026-09-14', 'kind': '8-K'}, {'date': '2025-01-01', 'kind': 'deal'}]
        s = L.rumor_score(items, TODAY)
        self.assertAlmostEqual(s, round(1.5 * 0.5 ** (1 / 45) * 1.2 + 3 * 0.5 ** (46 / 45), 2))   # news once a day (a buyer's at a fifth); old ones fade out


class Build(unittest.TestCase):
    def test_inputs_and_build(self):
        self.assertIsNone(L.lbo_inputs({'kind': 'bank', 'price': 10, 'inputs': {'revenue': 1, 'ebitda': 1, 'shares': 1}}))
        i = L.lbo_inputs({'kind': 'industrial', 'price': 10, 'price_date': '2026-10-29', 'inputs': {'revenue': 1e9, 'ebitda': 2e8, 'shares': 1e8, 'debt': 1e8}})
        self.assertEqual((i['price'], i['debt']), (10, 1e8))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'rl'
            sd = Path(d) / 'sd'
            val = Path(d) / 'val'
            L.write_json(sd / 'rates.json', {'series': {'SOFR': {'last': ['2026-10-28', 3.9]}, 'BAMLH0A2HYB': {'last': ['2026-10-28', 3.3]}}})
            L.write_json(sd / 'events8k.json', {'rows': [{'ticker': 'WEN', 'filed': '2026-10-29', 'topics': ['other'], 'headline': 'Board forms special committee to evaluate proposal', 'url': 'u'}]})
            L.write_json(sd / 'stakes.json', {'latest': []})
            L.write_json(sd / 'deals.json', {'deals': []})
            L.write_json(val / 'c' / '30697.json', {'kind': 'industrial', 'price': 6.3, 'inputs': {'revenue': 2.2e9, 'ebitda': 4.6e8, 'shares': 1.9e8, 'debt': 2.7e9, 'cash': 3e8}})
            L.write_json(root / 'cache' / 'news.json', [{'title': "Wendy's Gets $1.4bn Take-Private Offer", 'date': '2026-10-29', 'url': 'n', 'source': 'Reuters'}])
            st = L.build(root, site(d), val, sd, TODAY)
            self.assertEqual(st['with_inputs'], 1)
            self.assertEqual(st['with_rumors'], 1)
            doc = json.loads((root / 'public' / 'c' / '30697.json').read_text())
            self.assertEqual(doc['rates']['base'], 3.9)
            self.assertEqual([x['kind'] for x in doc['rumors']], ['news', '8-K'])
            self.assertTrue((root / 'public' / 'history.json').exists() and (root / 'public' / 'rumors.json').exists())


if __name__ == '__main__':
    unittest.main()
