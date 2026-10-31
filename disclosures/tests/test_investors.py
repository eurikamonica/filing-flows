"""investors.py: the gains ranking from frames (first gains concept a quarter, fourth quarters from the annual report),
13D/13G subjects, the sentences that name an investor, and the build that merges the evidence."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import frames as FR  # noqa: E402
import investors as I  # noqa: E402


def put(root, concept, period, vals):
    p = FR.path_for(root, concept, period)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, 'wt') as f:
        json.dump(vals, f)


class Fake:
    def __init__(self, docs):
        self.docs = docs

    def get(self, url, immutable=False, sec=True):
        for k, v in self.docs.items():
            if k in url:
                return v.encode()
        raise RuntimeError('HTTP 404')

    def json(self, url, sec=True):
        return json.loads(self.get(url))


class Ranking(unittest.TestCase):
    def test_rank_and_build(self):
        with tempfile.TemporaryDirectory() as d:
            P = FR.calendar_quarters(I.QUARTERS)
            for p in P[-4:]:
                put(d, 'GainLossOnInvestments', p, {'1045810': 5e9, '320193': -1e8})
                put(d, I.OTHER[3], p, {'1045810': 25e9, '320193': 30e9})
            put(d, 'GainLossOnInvestments', P[-4], {'1045810': 5e9, '320193': -1e8, '1111': 1e9})
            uni = [{'cik': 1045810, 'ticker': 'NVDA', 'name': 'NVIDIA CORP', 'sector': 'technology'}, {'cik': 320193, 'ticker': 'AAPL', 'name': 'Apple Inc.'},
                   {'cik': 1111, 'ticker': 'GLD', 'name': 'SPDR GOLD TRUST'}, {'cik': 50863, 'ticker': 'INTC', 'name': 'INTEL CORP'}]
            rows, _ = I.ranking(d, uni)
            self.assertEqual([r['t'] for r in rows], ['NVDA', 'AAPL'])                 # the gold trust is not an investor
            self.assertEqual((rows[0]['gains'], rows[0]['share']), (20e9, 0.2))
            ev = {'at': '2099-01-01', 'names': ['Nvidia'], 'stakes': [], 'own': [],
                  'f13': {'period': '2026-06-30', 'filed': '2026-08-14', 'total': 3e10, 'positions': 1, 'url': 'u',
                          'top': [{'issuer': 'INTEL CORP', 'usd': 3e10, 'price_gain': 2e10, 'status': 'held'}], 'sold': []},
                  'others': [{'name': 'INTEL CORP', 'cik': 50863, 'form': '8-K', 'filed': '2025-09-18', 'url': 'x', 'q': 'an investment from NVIDIA'}]}
            (Path(d) / 'cache' / 'ev').mkdir(parents=True)
            (Path(d) / 'cache' / 'ev' / '1045810.json').write_text(json.dumps(ev))
            u = Path(d) / 'u.json'
            u.write_text(json.dumps({'companies': uni}))
            I.build(d, u)
            doc = json.loads((Path(d) / 'public' / 'c' / '1045810.json').read_text())
            h = doc['holdings']
            self.assertEqual(len(h), 1)                                                   # 13F and the 8-K: one row, both sources
            self.assertEqual((h[0]['t'], h[0]['grade'], h[0]['price_gain'], h[0]['also'][0]['grade']), ('INTC', 'A', 2e10, 'C'))
            ix = json.loads((Path(d) / 'public' / 'index.json').read_text())
            self.assertEqual(dict(zip(ix['fields'], ix['rows'][0]))['top_gainer'], 'INTEL CORP')


class Reading(unittest.TestCase):
    def test_sentence_and_stakes(self):
        c = Fake({'doc.htm': '<p>Intel had a great quarter. In addition, NVIDIA has invested $2 billion in CoreWeave Class A common stock.</p>',
                  'led.htm': '<p>Industry initiatives led by Nvidia and Microsoft continue.</p>',
                  'index-headers': 'SUBJECT COMPANY: COMPANY DATA: COMPANY CONFORMED NAME: Serve Robotics Inc. CENTRAL INDEX KEY: 0001832483 '
                                   'FILED BY: COMPANY DATA: COMPANY CONFORMED NAME: NVIDIA CORP CENTRAL INDEX KEY: 0001045810'})
        self.assertIn('$2 billion in CoreWeave', I.sentence(c, 'https://x/doc.htm', ['Nvidia'], {}))
        self.assertIsNone(I.sentence(c, 'https://x/led.htm', ['Nvidia'], {}))           # 'led by' without an investment
        subs = {'filings': {'recent': {'form': ['SC 13G/A', '4'], 'accessionNumber': ['0001-26-1', '0001-26-2'], 'filingDate': ['2026-02-01', '2026-03-01']}}}
        s = I.stakes_filed(c, 1045810, subs)
        self.assertEqual((s[0]['name'], s[0]['cik']), ('Serve Robotics Inc.', 1832483))
        self.assertEqual(I.brand('NVIDIA CORP'), 'Nvidia')


if __name__ == '__main__':
    unittest.main()
