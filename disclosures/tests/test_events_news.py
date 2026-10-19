"""4.7 collectors: every 8-K (app/events8k.py) and the news wires / government releases (app/news.py), against real
EDGAR / PR Newswire / SEC samples (tests/fixtures; trimmed copies of Oct 16–17 2026) and one hand-written 8-K with a
press release that raises guidance."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import core
import events8k as E
import news as N

FIX = Path(__file__).resolve().parent / 'fixtures'
read = lambda name: (FIX / name).read_text(encoding='utf-8')

RAISE = """<SEC-DOCUMENT>0000000000-26-000001.txt : 20261016
<SEC-HEADER>0000000000-26-000001.hdr.sgml : 20261016
<ACCEPTANCE-DATETIME>20261016161502
ACCESSION NUMBER:		0000000000-26-000001
CONFORMED SUBMISSION TYPE:	8-K
PUBLIC DOCUMENT COUNT:		2
CONFORMED PERIOD OF REPORT:	20261016
ITEM INFORMATION:		Results of Operations and Financial Condition
ITEM INFORMATION:		Entry into a Material Definitive Agreement
ITEM INFORMATION:		Financial Statements and Exhibits
FILED AS OF DATE:		20261016
DATE AS OF CHANGE:		20261016

FILER:

	COMPANY DATA:
		COMPANY CONFORMED NAME:			EXAMPLE DEVICES INC
		CENTRAL INDEX KEY:			0000999999
</SEC-HEADER>
<DOCUMENT>
<TYPE>8-K
<SEQUENCE>1
<FILENAME>d8k.htm
<TEXT>
<html><body><p>Item 1.01 Entry into a Material Definitive Agreement.</p>
<p>On October 15, 2026, Example Devices Inc. entered into an Agreement and Plan of Merger with Widget Corp., under which
the Company will acquire Widget Corp. for $41.00 per share in cash, about $2.1 billion in total.</p>
<p>Item 2.02 Results of Operations and Financial Condition.</p><p>The information in this Item 2.02 is furnished.</p>
<p>Item 9.01 Financial Statements and Exhibits.</p></body></html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-99.1
<SEQUENCE>2
<FILENAME>ex99-1.htm
<TEXT>
<html><body><p>Exhibit 99.1</p>
<p><b>Example Devices Reports Record Third Quarter Results and Raises Full-Year Outlook</b></p>
<p>SAN JOSE, Calif., Oct. 16, 2026 (GLOBE NEWSWIRE) -- Example Devices Inc. (NASDAQ: EXDV) today reported revenue of $812
million for the third quarter, up 24% from a year ago.</p>
<p>The Company raises its full-year 2026 revenue guidance to $3.10 billion to $3.15 billion, from $2.95 billion to $3.05 billion.</p>
<p>This release contains forward-looking statements, including our guidance, which involve risks.</p></body></html>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


def tickers(root, rows):
    p = Path(root) / 'cache' / 'prices'
    p.mkdir(parents=True, exist_ok=True)
    (p / 'sec-tickers.json').write_text(json.dumps({'fetched_at': '2026-10-17T00:00:00+00:00', 'rows': rows}))


class EightK(unittest.TestCase):
    def test_restatement_from_the_header_items(self):
        r = E.parse_8k(read('8k-restatement.txt'), '0001500435-26-000064', 'https://www.sec.gov/Archives/edgar/data/1500435/000150043526000064/')
        self.assertEqual((r['form'], r['filed'], r['accepted'], r['cik'], r['company']), ('8-K', '2026-10-16', '2026-10-16T17:30', '1500435', 'GoPro, Inc.'))
        self.assertEqual((r['items'], r['code'], r['topics'][0], r['score']), (['2.02', '4.02', '8.01'], '4.02', 'restatement', 9))
        self.assertTrue(r['quote'].startswith('While preparing the proxy statement'))
        self.assertEqual((r['quote_src'], E.label(r)), ('Item 4.02', 'a restatement'))

    def test_deal_and_guidance_raised_from_the_release(self):
        r = E.parse_8k(RAISE, '0000000000-26-000001', 'u/')
        self.assertEqual(r['items'], ['2.02', '1.01', '9.01'])
        self.assertEqual(r['topics'][:2], ['guidance', 'deal'])
        self.assertIn('earnings', r['topics'])
        self.assertEqual(r['guidance'], 'raised')
        self.assertTrue(r['guidance_quote'].startswith('The Company raises its full-year 2026 revenue guidance'))
        self.assertEqual(r['headline'], 'Example Devices Reports Record Third Quarter Results and Raises Full-Year Outlook')
        self.assertEqual((r['code'], r['quote_src']), ('1.01', 'Item 1.01'))
        self.assertIn('$41.00 per share in cash', r['quote'])
        self.assertEqual(E.label(r), 'guidance raised')
        self.assertEqual(E.guidance(['We reaffirm our full-year outlook.']), ('reaffirmed', 'We reaffirm our full-year outlook.'))
        self.assertEqual(E.guidance(['The company is withdrawing its 2026 guidance.'])[0], 'withdrawn')
        self.assertEqual(E.guidance(['We lowered our revenue outlook for the year.'])[0], 'lowered')

    def test_what_is_not_news(self):
        """Oct 18 2026, the first 300 real 8-Ks: a bonus for the CEO read as "a CEO change", an old merger repeated "as
        previously reported" as a deal, "improved outlook on credit quality" as guidance raised, a consent as a press release."""
        sec = lambda *ps: {'5.02': list(ps)}
        self.assertFalse(any(E._says(dict((t[0], t[4]) for t in E.TOPICS)['ceo'], x) for x in E._sentences_of(
            ['The Compensation Committee approved a cash bonus of $500,000 for the Chief Executive Officer.'])))
        self.assertTrue(any(E._says(dict((t[0], t[4]) for t in E.TOPICS)['ceo'], x) for x in E._sentences_of(
            ['On October 14, 2026, John Doe notified the Board of his decision to retire as Chief Executive Officer.'])))
        self.assertFalse(any(E._says(dict((t[0], t[4]) for t in E.TOPICS)['deal'], x) for x in E._sentences_of(
            ['As previously reported, on September 2, 2026, the Company entered into an Agreement and Plan of Merger with Parent.'])))
        self.assertEqual(E.guidance(['The decrease was the result of improved outlook on credit quality.']), (None, None))
        self.assertEqual(E.guidance(['The outlook reflects input costs at current levels and assumes no further increases.']), (None, None))
        self.assertEqual(E.guidance(['The Company lowered its fiscal 2026 adjusted EPS guidance to $1.10.'])[0], 'lowered')
        self.assertIsNone(E.dateline(['CONSENT OF INDEPENDENT VALUATION ADVISOR', 'We hereby consent to the use of our name.']))
        off = dict((t[0], t[4]) for t in E.TOPICS)['offering']
        self.assertFalse(E._says(off, 'On October 15, 2026, the Company closed its previously announced private offering of $730.0 million '
                                      'in aggregate principal amount of notes.'))
        self.assertTrue(E._says(off, 'On October 15, 2026, the Company closed its registered direct offering of 4,000,000 shares of common stock.'))
        self.assertEqual(E.headline(['2900 Independence Court, Elkhart, Indiana 46514', 'New York, NY 10017-2630',
                                     'THOR INDUSTRIES ANNOUNCES INCREASED REGULAR QUARTERLY DIVIDEND',
                                     'Elkhart, Indiana, October 13, 2026 – THOR Industries, Inc. (NYSE: THO) today announced …']),
                         'THOR INDUSTRIES ANNOUNCES INCREASED REGULAR QUARTERLY DIVIDEND')
        self.assertEqual(E.headline(['Chief Accounting Officer Financial Relations Board', 'Fox Factory Announces CEO Transition',
                                     'DULUTH, Ga., Oct. 16, 2026 (GLOBE NEWSWIRE) -- Fox Factory today announced …']), 'Fox Factory Announces CEO Transition')
        self.assertEqual(E.headline(['Exhibit 99.1', 'Contact: ir@example.com (408) 555-0100', 'Example Devices Reports Record Third Quarter Results',
                                     'SAN JOSE, Calif., Oct. 16, 2026 (GLOBE NEWSWIRE) -- Example Devices today reported results.']),
                         'Example Devices Reports Record Third Quarter Results')
        t = E.item_sections(['Item 5.02 Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; '
                             'Compensatory Arrangements of Certain Officers. On October 14, 2026, John Doe notified the Board of his decision to retire.'])
        self.assertTrue(t['5.02'][0].startswith('On October 14, 2026'))

    def test_daily_index_and_collection(self):
        idx = ('8-K         EXAMPLE DEVICES INC                                          999999      20261016    edgar/data/999999/0000000000-26-000001.txt\n'
               '8-K         GoPro, Inc.                                                  1500435     20261016    edgar/data/1500435/0001500435-26-000064.txt\n'
               '10-Q        SOME CO                                                      123         20261016    edgar/data/123/0000000123-26-000001.txt\n')
        self.assertEqual([a for a, _ in E.parse_daily_index(idx)], ['0000000000-26-000001', '0001500435-26-000064'])
        root = Path(tempfile.mkdtemp())
        tickers(root, [{'ticker': 'GPRO', 'title': 'GoPro, Inc.', 'cik': 1500435}, {'ticker': 'EXDV', 'title': 'Example Devices', 'cik': 999999}])
        subs = {'0000000000-26-000001': RAISE, '0001500435-26-000064': read('8k-restatement.txt')}

        class Client:
            calls = []

            def get(self, url, sec=False, headers=None):
                self.calls.append(url)
                if 'getcurrent' in url:
                    return b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
                if 'daily-index' in url:
                    if url.endswith('form.20261016.idx'):
                        return idx.encode()
                    raise RuntimeError('HTTP 404 from www.sec.gov')
                return next(t for a, t in subs.items() if url.endswith(a + '.txt')).encode()

        c = Client()
        r = E.collect(c, root, {'backfill_days': 5, 'index_days_per_run': 10}, today=dt.date(2026, 10, 17))
        self.assertEqual((r['kept'], r['waiting'], r['on_file']), (2, 0, 2))
        self.assertEqual([p.name for p in (root / 'cache' / 'events8k').glob('*.json.gz')], ['2026-10-16.json.gz'])
        n = len(c.calls)
        E.collect(c, root, {'backfill_days': 5, 'index_days_per_run': 10}, today=dt.date(2026, 10, 17))
        self.assertFalse(any(u.endswith('.txt') for u in c.calls[n:]))
        st = json.loads((root / 'cache' / 'events8k' / 'state.json').read_text())
        st['parser'] = E.PARSER - 1                                       # an older parser: everything on file is read again
        (root / 'cache' / 'events8k' / 'state.json').write_text(json.dumps(st))
        n = len(c.calls)
        r = E.collect(c, root, {'backfill_days': 5, 'index_days_per_run': 10, 'batch': 10}, today=dt.date(2026, 10, 17))
        self.assertEqual((sum(u.endswith('.txt') for u in c.calls[n:]), r['reparse_left']), (2, 0))
        self.assertEqual(json.loads((root / 'cache' / 'events8k' / 'state.json').read_text())['parser'], E.PARSER)
        out = E.publish(root, root / 'market', today=dt.date(2026, 10, 17))
        d = json.loads((root / 'market' / 'events8k.json').read_text())
        self.assertEqual((out['rows'], d['rows'][0]['ticker'] in ('EXDV', 'GPRO')), (2, True))
        self.assertEqual(d['counts'].get('restatement'), 1)
        self.assertEqual(E.by_ticker(root, today=dt.date(2026, 10, 17))['EXDV'][0]['label'], 'guidance raised')

    def test_stable_gzip(self):
        p = Path(tempfile.mkdtemp()) / 'x.json.gz'
        self.assertTrue(core.write_gz(p, [{'a': 1}]))
        b = p.read_bytes()
        self.assertFalse(core.write_gz(p, [{'a': 1}]))                 # unchanged: not rewritten
        self.assertEqual(p.read_bytes(), b)


class Hosts(unittest.TestCase):
    def test_every_source_host_is_approved(self):
        """Oct 18 2026: the first news run failed every PR Newswire and FDA feed with "Unapproved data host"."""
        from urllib.parse import urlparse
        import ownership, senate, shorts
        urls = list(N.PRN) + [N.OPENFDA, N.FDA_PRESS] + [u for _, u in N.SEC_FEEDS] + [E.FEED, ownership.FEED, ownership.DAILY,
                                                                                   shorts.PARTS, shorts.DATA, senate.HOME]
        self.assertEqual([u for u in urls if urlparse(u).hostname not in core.HOSTS], [])


class News(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        tickers(self.root, [{'ticker': 'TFC', 'title': 'Truist Financial Corp', 'cik': 92230}, {'ticker': 'CLPS', 'title': 'CLPS Inc', 'cik': 1724542},
                            {'ticker': 'TJGC', 'title': 'TJGC Group Ltd', 'cik': 2},
                            {'ticker': 'PFE', 'title': 'PFIZER INC', 'cik': 78003}])
        self.names = N.Names(self.root)

    def test_wire_releases(self):
        rows, skipped = N.prn_rows(N.rss_items((FIX / 'prn-earnings.xml').read_bytes()), self.names)
        self.assertEqual(skipped, {'law firm': 1, 'not English': 1})
        by = {r['company']: r for r in rows}
        self.assertEqual(by['Truist Financial Corporation']['tickers'], ['TFC'])
        self.assertEqual(by['Truist Financial Corporation']['match'], 'exchange tag')
        self.assertTrue(all(r['url'].startswith('https://www.prnewswire.com/') and 'description' not in r for r in rows))   # no body text kept

    def test_fda_and_sec(self):
        fda = N.fda_rows({'results': [
            {'application_number': 'NDA219999', 'sponsor_name': 'PFIZER INC', 'products': [{'brand_name': 'EXAMPLA', 'active_ingredients': [{'name': 'EXAMPLINIB'}]}],
             'submissions': [{'submission_type': 'ORIG', 'submission_status': 'AP', 'submission_status_date': '20261014'}]},
            {'application_number': 'ANDA218725', 'sponsor_name': 'AUROBINDO PHARMA LTD', 'products': [{}],
             'submissions': [{'submission_type': 'ORIG', 'submission_status': 'AP', 'submission_status_date': '20261006'}]}]}, self.names, '20261001')
        self.assertEqual(len(fda), 1)                                    # generics (ANDA) left out
        self.assertEqual((fda[0]['tickers'], fda[0]['published'][:10]), (['PFE'], '2026-10-14'))
        self.assertTrue(fda[0]['title'].startswith('FDA approved Exampla (examplinib)'))
        sus = N.sec_rows('suspension', N.rss_items((FIX / 'sec-suspensions.xml').read_bytes()), self.names)
        self.assertEqual(sus[0]['tickers'], ['TJGC'])
        self.assertEqual(N.named_companies('SEC Charges Acme Robotics Corp. with Misleading Investors'), ['Acme Robotics Corp'])

    def test_collect_and_publish(self):
        prn = (FIX / 'prn-earnings.xml').read_bytes()
        sus = (FIX / 'sec-suspensions.xml').read_bytes()

        class Client:
            def get(self, url, sec=False, headers=None):
                if 'prnewswire' in url:
                    if url.endswith('earnings-list.rss'):
                        return prn
                    raise RuntimeError('HTTP 404 from www.prnewswire.com')
                if 'trading-suspensions' in url:
                    return sus
                return b'<rss><channel></channel></rss>'

            def json(self, url, sec=False):
                return {'results': []}

        r = N.collect(Client(), self.root, today=dt.date(2026, 10, 17))
        self.assertEqual(r['status'], 'partial')                         # the six other PR Newswire feeds failed here
        self.assertGreaterEqual(r['added'], 3)
        again = N.collect(Client(), self.root, today=dt.date(2026, 10, 17))
        self.assertEqual(again['added'], 0)                              # nothing kept twice
        N.publish(self.root, self.root / 'market', today=dt.date(2026, 10, 17), days=400)
        d = json.loads((self.root / 'market' / 'news.json').read_text())
        self.assertTrue(any(x['tickers'] == ['TFC'] for x in d['rows']))
        self.assertIn('TFC', N.by_ticker(self.root))


if __name__ == '__main__':
    unittest.main()
