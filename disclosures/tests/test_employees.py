"""employees.py: the headcount read from 10-K sentences (real wordings), the list of annual reports, and the build."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import employees as E  # noqa: E402

CASES = [  # sentence as filed → the count it states
    ('As of December 31, 2025, we employed approximately 1,576,000 full-time and part-time employees.', 1576000),
    ('Our business is focused on serving people and this is delivered by our approximately 2.1 million associates around the world with approximately 1.6 million in the U.S.', 2100000),
    ('As of September 27, 2025, the Company had approximately 166,000 full-time equivalent employees.', 166000),
    ('Employees At December 31, 2025, we employed approximately 88,000 (56%) hourly employees and approximately 68,000 (44%) salaried employees.', 156000),
    ('Each of our approximately 67,200 full- and part-time employees in 44 countries make an important contribution.', 67200),
    ('As of December 31, 2025, a total of 710 persons were employed by the Company, of which 32% were located in our corporate office.', 710),
    ('As of December 31, 2025, we had 592 total at-will employees, of which 591 were full-time.', 592),
    ('We had a global workforce of 78,865 employees as of December 31, 2025, and we have offices in more than 90 cities.', 78865),
    ('As of June 30, 2026, we employed approximately 223,000 people on a full-time basis, 121,000 in the U.S. and 102,000 internationally.', 223000),
    ('As of December 31, 2025, our employee population, including all full-time, part-time and temporary workers, consisted of approximately 97,100 individuals.', 97100),
]


def doc(sentence, extra=''):
    return f'<html><body><p>Item 1. Business</p><p>We make things.</p><p><b>Human Capital</b></p><p>{sentence}</p><p>Approximately 30% of our employees are women.</p>{extra}</body></html>'


class Read(unittest.TestCase):
    def test_wordings(self):
        for s, n in CASES:
            hc = E.headcount(doc(s))
            self.assertIsNotNone(hc, s)
            self.assertEqual(hc['count'], n, s)

    def test_dates_and_noise(self):
        hc = E.headcount(doc('As of January 3, 2026, we had 13,138 full-time and part-time associates, including 635 directly employed optometrists.'))
        self.assertEqual((hc['count'], hc['as_of']), (13138, '2026-01-03'))
        self.assertIsNone(E.headcount(doc('In 2025, 95% of all eligible employees completed annual performance reviews.')))
        self.assertIsNone(E.headcount(doc('The 2021 Employee Stock Purchase Plan authorizes 32,250,222 shares.')))
        hc = E.headcount(doc('We have 401(k) plans.', '<p>As of December 31, 2025, we had 9,811 employees.</p>'))
        self.assertEqual(hc['count'], 9811)

    def test_tenks(self):
        subs = {'filings': {'recent': {'form': ['10-Q', '10-K', '8-K', '10-K/A', '10-K'], 'accessionNumber': ['a', 'b', 'c', 'd', 'e'],
                                       'primaryDocument': ['q.htm', 'k.htm', 'x.htm', 'ka.htm', 'k2.htm'], 'filingDate': ['2026-05-01', '2026-02-01', '', '', '2025-02-01'],
                                       'reportDate': ['2026-03-31', '2025-12-31', '', '', '2024-12-31']}}}
        self.assertEqual([r['acc'] for r in E.tenks(subs)], ['b', 'e'])


class Build(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cos = []
            found = {}
            for i in range(8):
                cik = 100 + i
                cos.append({'cik': cik, 'ticker': f'T{i}', 'name': f'Co {i}', 'sector': 'technology', 'sic': '7372', 'revenue': 1e9 * (i + 1)})
                found[str(cik)] = {
                    f'a{i}': {'count': 1000 * (i + 1), 'as_of': '2024-12-31', 'period': '2024-12-31', 'sentence': 's', 'where': 'human capital section', 'filed': '2025-02-01'},
                    f'b{i}': {'count': 1000 * (i + 1) * (0.9 if i == 0 else 1.2), 'as_of': '2025-12-31', 'period': '2025-12-31', 'sentence': 's', 'where': 'document', 'filed': '2026-02-01'},
                }
            (root / 'cache').mkdir()
            (root / 'cache' / 'found.json').write_text(json.dumps(found))
            (root / 'u.json').write_text(json.dumps({'companies': cos}))
            fr = root / 'hub' / 'cache' / 'frames'
            fr.mkdir(parents=True)
            for y in (2024, 2025):
                rev = {str(100 + i): [1e8 * (i + 1) * (1.1 if y == 2025 else 1), f'{y}-12-31'] for i in range(8)}
                with gzip.open(fr / f'Revenues-CY{y}.json.gz', 'wt') as f:
                    json.dump(rev, f)
            st = E.build(root, root / 'u.json', root / 'hub')
            self.assertEqual(st['companies'], 8)
            ix = json.loads((root / 'public' / 'index.json').read_text())
            rows = {r[1]: dict(zip(ix['fields'], r)) for r in ix['rows']}
            self.assertAlmostEqual(rows['T0']['change'], -0.1)
            self.assertEqual(rows['T0']['flag'], 'fewer people, more revenue')
            self.assertEqual(rows['T3']['flag'], 'hiring')
            self.assertAlmostEqual(rows['T2']['rev_emp'], 1.1e8 * 3 / 3600, places=3)
            c = json.loads((root / 'public' / 'c' / '100.json').read_text())
            self.assertEqual(len(c['years']), 2)
            self.assertEqual(c['row']['peer_group'], 'SIC 737')


if __name__ == '__main__':
    unittest.main()
