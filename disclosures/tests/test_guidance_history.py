"""Guidance history (app/guidance_history.py): every earnings release's guidance kept beyond the 8-K window, older
releases read a few per run from EDGAR, and the prior ranges of the latest release taken from it."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import events8k as E  # noqa: E402
import guidance_history as GH  # noqa: E402


def release(acc, filed, body, cik='999999'):
    """A minimal 8-K submission with an Exhibit 99.1 earnings release."""
    return f"""<SEC-HEADER>
ACCESSION NUMBER:		{acc}
CONFORMED SUBMISSION TYPE:	8-K
FILED AS OF DATE:		{filed.replace('-', '')}
ITEM INFORMATION:		Results of Operations and Financial Condition
FILER:
	COMPANY DATA:
		COMPANY CONFORMED NAME:			EXAMPLE DEVICES INC
		CENTRAL INDEX KEY:			{cik.zfill(10)}
</SEC-HEADER>
<DOCUMENT>
<TYPE>8-K
<TEXT><html><body><p>Item 2.02 Results of Operations and Financial Condition</p></body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-99.1
<TEXT>
<html><body><p>Exhibit 99.1</p>
<p><b>Example Devices Reports Results</b></p>
<p>SAN JOSE, Calif., {filed} (GLOBE NEWSWIRE) -- Example Devices Inc. (NASDAQ: EXDV) today reported its results.</p>
<p>{body}</p></body></html>
</TEXT>
</DOCUMENT>
"""


class History(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        p = self.root / 'cache' / 'prices'
        p.mkdir(parents=True, exist_ok=True)
        (p / 'sec-tickers.json').write_text(json.dumps({'rows': [{'ticker': 'EXDV', 'cik': 999999}]}))

    def test_rows_and_backfill(self):
        # the 8-K store holds the latest release (Oct): it enters the history and the company joins the back-fill queue
        now = E.parse_8k(release('0000999999-26-000030', '2026-10-15',
                                 'For the full year 2026, the company now expects revenue of $3.10 billion to $3.20 billion.'),
                         '0000999999-26-000030', 'https://www.sec.gov/Archives/edgar/data/999999/000099999926000030/')
        shards = E.store(self.root)
        shards.add(now)
        shards.save()
        older = {
            '0000999999-26-000020': ('2026-07-15', 'For the full year 2026, the company expects revenue of $3.00 billion to $3.20 billion.'),
            '0000999999-26-000010': ('2026-04-15', 'For the full year 2026, the company expects revenue of $2.90 billion to $3.10 billion.'),
            '0000999999-26-000005': ('2026-02-15', 'The company declared a quarterly dividend.'),
        }
        sub = {'cik': '999999', 'filings': {'recent': {
            'accessionNumber': ['0000999999-26-000030', '0000999999-26-000025', *older.keys()],
            'filingDate': ['2026-10-15', '2026-09-01', *[v[0] for v in older.values()]],
            'form': ['8-K', '8-K', '8-K', '8-K', '8-K'],
            'items': ['2.02,9.01', '5.02', '2.02,9.01', '2.02', '2.02,9.01']}}}

        class Client:
            calls = []

            def json(self, url, sec=False):
                self.calls.append(url)
                assert url == 'https://data.sec.gov/submissions/CIK0000999999.json'
                return sub

            def get(self, url, sec=False, headers=None):
                self.calls.append(url)
                acc = url.rsplit('/', 1)[1][:-4]
                return release(acc, older[acc][0], older[acc][1]).encode()

        c = Client()
        r = GH.collect(c, self.root, {'budget': 1}, today=dt.date(2026, 10, 29))
        self.assertEqual((r['new_from_8k'], r['read'], r['backfilled'], r['waiting']), (1, 1, 0, 1))
        doc = GH.load(self.root, '999999')
        self.assertEqual([x['filed'] for x in doc['releases']], ['2026-10-15', '2026-07-15'])
        self.assertFalse(doc['backfill']['done'])
        r = GH.collect(c, self.root, {'budget': 8}, today=dt.date(2026, 10, 29))
        doc = GH.load(self.root, '999999')
        self.assertEqual([x['filed'] for x in doc['releases']], ['2026-10-15', '2026-07-15', '2026-04-15'])
        self.assertTrue(doc['backfill']['done'], 'the release without guidance is read once and not again')
        self.assertEqual(doc['backfill']['tried'].get('0000999999-26-000005'), 3)
        self.assertFalse(any('000025' in u for u in c.calls), 'only item 2.02 8-Ks are read')
        n = len(c.calls)
        GH.collect(c, self.root, {'budget': 8}, today=dt.date(2026, 10, 29))
        self.assertEqual(len(c.calls), n, 'a company whose releases are all read is not asked for again')
        rev = next(i for i in doc['releases'][1]['items'] if i['metric'] == 'revenue')
        self.assertEqual((rev['period'], rev['lo'], rev['hi']), ('FY2026', 3.0e9, 3.2e9))
        self.assertNotIn('quote', rev, 'the history keeps figures, not sentences')

        # published per ticker; the latest release's prior range now comes from the release before it
        pub = GH.publish(self.root)
        self.assertEqual([x['filed'] for x in pub['EXDV']['releases']], ['2026-10-15', '2026-07-15', '2026-04-15'])
        self.assertTrue(pub['EXDV']['complete'])
        g = E.guidance_by_ticker(self.root, today=dt.date(2026, 10, 29))['EXDV']
        top = next(i for i in g['items'] if i['metric'] == 'revenue')
        self.assertEqual((top['prior']['lo'], top['prior']['filed'], top['change'], top['range']), (3.0e9, '2026-07-15', 'raised', 'narrowed'))
        self.assertEqual(g['tags'][:2], ['raised', 'narrowed'])
        self.assertEqual([f for f, _, _ in GH.earlier(self.root, '999999', '0000999999-26-000030', '2026-10-15')], ['2026-07-15', '2026-04-15'])

    def test_release_of_keeps_company_figures_only(self):
        row = {'accession': 'a', 'filed': '2026-10-01', 'url': 'u', 'guidance': 'raised', 'guidance_tags': ['raised'],
               'guidance_items': [{'metric': 'revenue', 'basis': '', 'period': 'FY2026', 'unit': 'usd', 'lo': 1e9, 'hi': 1.1e9, 'quote': 'x'},
                                  {'metric': 'revenue', 'basis': '', 'period': 'FY2026', 'unit': 'usd', 'lo': 5e8, 'hi': 5e8, 'scope': 'segment'}]}
        rel = GH.release_of(row)
        self.assertEqual(len(rel['items']), 1)
        self.assertEqual(rel['items'][0], {'metric': 'revenue', 'period': 'FY2026', 'unit': 'usd', 'lo': 1e9, 'hi': 1.1e9})
        self.assertIsNone(GH.release_of({'accession': 'b', 'guidance_items': []}))
        doc = {'cik': '1', 'releases': [], 'backfill': {}}
        self.assertTrue(GH.add(doc, rel))
        self.assertFalse(GH.add(doc, dict(rel)), 'the same release twice is not new')


if __name__ == '__main__':
    unittest.main()
