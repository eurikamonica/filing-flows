"""4.19 cross-holdings: the President's 278-T reader (president.py) and the holder graph (crossholdings.py).

The 278-T lines below are copied from the text layer of the President's reports as OGE posts them (Acrobat's OCR of a
scan), misreadings included — the reader has to cope with exactly these."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import president as P
import crossholdings as XH
from market import Universe


def page(n, *lines):
    return {'page': n, 'source': 'text', 'lines': [[ln] for ln in lines]}


def universe(root, rows):
    (root / 'cache' / 'prices').mkdir(parents=True, exist_ok=True)
    (root / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': rows}))
    (root / 'cache' / 'prices' / 'cusips.json').write_text('{}')
    return Universe(root)


SEC_ROWS = [
    {'ticker': 'NVDA', 'title': 'NVIDIA CORP', 'cik': 1045810},
    {'ticker': 'GOOGL', 'title': 'Alphabet Inc.', 'cik': 1652044},
    {'ticker': 'GOOG', 'title': 'Alphabet Inc.', 'cik': 1652044},
    {'ticker': 'NFLX', 'title': 'NETFLIX INC', 'cik': 1065280},
    {'ticker': 'WHR', 'title': 'WHIRLPOOL CORP /DE/', 'cik': 106640},
    {'ticker': 'WHR-PA', 'title': 'WHIRLPOOL CORP /DE/', 'cik': 106640},
    {'ticker': 'DIS', 'title': 'Walt Disney Co', 'cik': 1744489},
    {'ticker': 'ALAB', 'title': 'Astera Labs, Inc.', 'cik': 1736297},
    {'ticker': 'TXN', 'title': 'TEXAS INSTRUMENTS INC', 'cik': 97476},
    {'ticker': 'INTC', 'title': 'INTEL CORP', 'cik': 50863},
    {'ticker': 'MBLY', 'title': 'Mobileye Global Inc.', 'cik': 1910139},
    {'ticker': 'BRK-B', 'title': 'BERKSHIRE HATHAWAY INC', 'cik': 1067983},
    {'ticker': 'AAPL', 'title': 'Apple Inc.', 'cik': 320193},
]


class Words(unittest.TestCase):
    def test_types(self):
        for tok in ('lourchaso', '1ourchaso', 'l0urchase', 'IDUrchase', 'IPUrchaSO', 'curchasc', 'oun:halo', 'pun:haae', 'PURCHASE'):
            self.assertEqual(P.tx_type(tok), 'P', tok)
        for tok in ('sale', 'salo', 'sato', "5'110", '5:llo', 's:,lo'):
            self.assertEqual(P.tx_type(tok), 'S', tok)
        for tok in ('CHURCH', 'RESEARCH', 'Church', 'SYS', 'SA', 'CLASS', 'INC'):   # names, not a garbled type
            self.assertIsNone(P.tx_type(tok), tok)

    def test_dates(self):
        cases = {'7/17/2026': '2026-07-17', '717/2026': '2026-07-07', '7/812026': '2026-07-08', '2/1012026': '2026-02-10',
                 '2l20l2028': '2026-02-20', '1/612028': '2026-01-06', '11612026': '2026-01-06', '8/1.9/2026': '2026-08-19'}
        for tok, iso in cases.items():
            self.assertEqual(P.read_date(tok, '2026-09-14', '2025-01-01'), iso, tok)
        for tok in ('081532', '1000001', '15001', '2026.11.14'):          # a maturity code, figures, a signature stamp
            self.assertIsNone(P.read_date(tok, '2026-09-14', '2025-01-01'), tok)
        self.assertIsNone(P.read_date('7/17/2026', '2026-05-08', '2025-01-01'))     # after the report: a misread
        self.assertEqual(P.parse_date('Due Oct 1, 2031 lourchaso 7 /16/2026 No', '2026-09-14', '2025-01-01')[0], None)  # spaced: glued by the row reader

    def test_amounts(self):
        cases = {'Yes $1 000 001 - $5 000 000': (1000001, 5000000), 'No $500 001 - $1 .000.000': (500001, 1000000),
                 'No $50 001·$100000': (50001, 100000), 'No $1 001 : $15 000': (1001, 15000), 'no $100 001 -$250 ODO': (100001, 250000),
                 'no SS00,001- $1,000,000': (500001, 1000000), 'Yos $250 001 • ssoo.ooo': (250001, 500000),
                 'No s1.ooo.001- S5.ooo.ooo': (1000001, 5000000), 'Yoa sso.001 -s100.000': (50001, 100000),
                 '$100 001 -$250;000': (100001, 250000), 'sale 7/8/2026 ....   $1 001 -$15 000': (1001, 15000),
                 'sale 7/27/2026 no $50 001 - $': (50001, 100000), 'Yes $15,003 - $50,000': (15001, 50000)}
        for text, want in cases.items():
            self.assertEqual(P.parse_amount(text)[0], want, text)
        self.assertEqual(P.parse_amount('Transactions in excess of $1,000 made on behalf of the filer')[0], None)


class Rows(unittest.TestCase):
    def test_report_page(self):
        pg = page(4,
                  'OGE Form 278-T (Updated February 2024)',
                  'Donald J Trump                                                Page 04 of37',
                  '#                O..Crtllllon                         Date   Received Over   30 Davs Aao   Amount',
                  '67               NATERA INC',
                  '                                              10urchaso             7/17/2026             No $1 001 • $15 000',
                  '68               DEXCOMINC',
                  '                                              IDUrchase             7/17/2026             No $1,001 -$15,000',
                  '69               MCCORMICK & CO INC NON VOTING                  10urchase   7/17/2026   No $1 001 -$15,000',
                  '80               ALPHABET INC CL A                              lourchaso   7/1 7/2026  No $1 001 -$15 000',
                  '97               ALPHABET INC CL C                              sale        7/17/2026   No $1 001 - $15 000',
                  '302              MOHAWK INDS INC                                                   7/8/2026',
                  '                                                              ourchaso',
                  '                                                                          """ $15,001 -$50 000',
                  '122              NVIDIA CORP                                    salo        7/17/2026   No $1 001 - $15 000',
                  '123              TESLA INC                                      sa1e        8"•"026     No $15 001 -$50,000',
                  '[25 Godaddy Inc sale 6/23/2026 No|$1,001 - $15,000')
        rows = P.parse_lines([pg], '2026-09-14', 'r1')
        by = {r['n']: r for r in rows}
        self.assertEqual(sorted(by), [25, 67, 68, 69, 80, 97, 122, 123, 302])
        self.assertEqual((by[67]['description'], by[67]['type'], by[67]['date'], by[67]['amount_min']), ('NATERA INC', 'purchase', '2026-07-17', 1001))
        self.assertEqual(by[80]['date'], '2026-07-17')
        self.assertEqual((by[302]['description'], by[302]['type'], by[302]['date'], by[302]['amount_max']), ('MOHAWK INDS INC', 'purchase', '2026-07-08', 50000))
        self.assertEqual((by[122]['type'], by[122]['description']), ('sale', 'NVIDIA CORP'))
        self.assertTrue(by[123]['date_estimated'])                 # the date column is noise: the row above's date
        self.assertEqual(by[123]['date'], '2026-07-17')
        self.assertEqual(by[25]['description'], 'Godaddy Inc')

    def test_unreadable_type_from_neighbours(self):
        pg = page(2, '1 APPLE INC lourchase 3/23/2026 Yes $1,001 - $15,000',
                     '2 EXELON CORP l)U- 1/21/2026 Vos $1 .001-$15,000',
                     '3 HOME DEPOT INC purchase 3/23/2026 Yo■ $1,001 -$15,000')
        rows = P.parse_lines([pg], '2026-05-08')
        self.assertEqual([r['type'] for r in rows], ['purchase'] * 3)
        self.assertTrue(rows[1]['type_inferred'])
        self.assertEqual(rows[1]['description'], 'EXELON CORP')

    def test_weak_and_best_pages(self):
        noise = page(3, *[f'~~ {i} :: "-•- $1 00{i} ..:; ~' for i in range(8)])
        good = {'page': 3, 'source': 'ocr', 'conf': 85.0,
                'lines': [[f'{i} Kla Corp purchase 6/23/2026 No| $50,001 - $100,000'] for i in range(1, 9)]}
        self.assertTrue(P.weak_page(noise, 10))
        self.assertFalse(P.weak_page(noise, 3))                    # the last page is the boilerplate
        self.assertEqual(P.best_pages([noise, good])[0]['source'], 'ocr')


class Reports(unittest.TestCase):
    def test_report_meta(self):
        base = 'https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/'
        r = P.report_meta(base + '322B8A28DB21CC9285258CFD002C0D0B/$FILE/Donald%20J.%20Trump%209.3.25%20278-T.pdf')
        self.assertEqual((r['filed'], r['kind'], r['name']), ('2025-09-03', '278T', 'Donald J. Trump 9.3.25 278-T.pdf'))
        r = P.report_meta(base + '0BDCCCE7DE13AEFA85258E8A002DE2B5/$FILE/Donald-J-Trump.09.17.2026-278T.pdf')
        self.assertEqual((r['filed'], r['kind']), ('2026-09-17', '278T'))
        r = P.report_meta(base + '405E4EC4E27BE8D185258DF7002DD1C0/$FILE/Trump%2C%20Donald%20J.-05.08.2026-278T(2).pdf')
        self.assertEqual((r['filed'], r['name']), ('2026-05-08', 'Trump, Donald J.-05.08.2026-278T(2).pdf'))
        self.assertIn('/$FILE/Trump,%20Donald%20J.-05.08.2026-278T(2).pdf', r['url'])
        r = P.report_meta(base + '69AEAA9D7455ACD585258E27002DDEE1/$FILE/Donald-J-Trump-2026-278ANNUAL.pdf')
        self.assertEqual((r['kind'], r['filed']), ('annual', '2026-05-15'))
        self.assertIsNone(P.report_meta(base + '6E78B163F816EF6A852586630075291D/$FILE/Trump,%20Ivanka%202021.pdf'))

    def test_search_api(self):
        body = {'data': [
            {'name': 'Trump, Donald J', 'title': 'President', 'docDate': '2026-10-08T04:00:00',
             'type': "278 Transaction (<a href='https:\\/\\/extapps2.oge.gov\\/201\\/Presiden.nsf\\/PAS+Index\\/0BDCCCE7DE13AEFA85258E8A002DE2B5\\/$FILE\\/Donald-J-Trump.09.17.2026-278T.pdf'>View</a>)"},
            {'name': 'Trump, Donald J', 'title': 'Presidential Candidate', 'docDate': '2024-08-23T04:21:52',
             'type': "Presidential Candidate (<a href='https:\\/\\/extapps2.oge.gov\\/201\\/Presiden.nsf\\/201%20Request?OpenForm&Filer=Trump'>Request</a>)"},
            {'name': 'Trump, Ivanka', 'title': 'Advisor', 'docDate': '2021-01-20T00:00:00', 'type': 'Termination'}]}

        class Client:
            def get(self, url):
                assert 'API.xsp' in url
                return json.dumps(body).replace('\\\\/', '\\/').encode()
        rows = P.api_reports(Client())
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['kind'], rows[0]['posted'], rows[0]['filed']), ('278T', '2026-10-08', '2026-09-17'))

    def test_publish_from_cached_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            u = universe(root, SEC_ROWS)
            rid = 'E590116FC9631E9885258E7A002DE209'
            base = root / 'cache' / 'president'
            (base / 'ocr').mkdir(parents=True)
            (base / 'state.json').write_text(json.dumps({'reports': {rid: {
                'id': rid, 'name': 'Donald-J-Trump-09.8.2026-278T.pdf', 'url': 'https://example.invalid/r.pdf', 'filed': '2026-09-08',
                'posted': '2026-09-22', 'kind': '278T', 'pages': 2, 'pages_done': 2}}}))
            pages = [page(1, 'OGE Form 278-T', 'Fllo(s lnformaUon'),
                     page(2, '1 NVIDIA CORP lourchaso 7/17/2026 No $15 001 -$50 000',
                             '2 NVIDlA CORP lourchaso 7/20/2026 No $1 001 - $15 000',
                             '3 ALPHABET INC CL C sale 7/17/2026 No $1 001 - $15 000',
                             '4 NETFLIXINC lourchase 7/1 7/2026 No $1,001-$15000',
                             '5 MIAMI DADE CNTY FL AVIATION REV RFDG SER A B/E PTC 5.00 % Due Oct 1, 2031 lourchaso 717/2026 Yes $1 000 001 - $5 000 000',
                             '6 lshares Tr Russell 1000 Etf ourchaso 7/17/2026 No $1 000 001 • $5 000 000')]
            with gzip.open(base / 'ocr' / f'{rid}.json.gz', 'wt') as f:
                json.dump({'pages': pages}, f)
            P.publish(root, root / 'market', u)
            d = json.loads((root / 'market' / 'president.json').read_text())
            by = {r['n']: r for r in d['trades']}
            self.assertEqual([by[n]['ticker'] for n in range(1, 7)], ['NVDA', 'NVDA', 'GOOG', 'NFLX', None, None])
            self.assertEqual([by[n]['asset'] for n in (1, 5, 6)], ['stock', 'bond', 'fund'])
            nv = next(t for t in d['tickers'] if t['ticker'] == 'NVDA')
            self.assertEqual((nv['buys'], nv['buy_mid'], nv['net_mid']), (2, round((15001 + 50000) / 2 + (1001 + 15000) / 2), round((15001 + 50000) / 2 + (1001 + 15000) / 2)))
            f = d['filings'][0]
            self.assertEqual((f['rows'], f['last_row_number'], f['coverage'], f['text_pages']), (6, 6, 1.0, 2))
            self.assertEqual(d['stats']['span'], ['2026-07-07', '2026-07-20'])


class Names(unittest.TestCase):
    def test_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            u = universe(Path(tmp), SEC_ROWS)
            T = P.Tickers(u)
            cases = {'NVIDIA CORP': 'NVDA', 'NVIDlA CORP': 'NVDA', 'ALPHABET INC CL A': 'GOOGL', 'ALPHABET INC CL C': 'GOOG',
                     'ALPHABET INC CL A UNSOLICITED': 'GOOGL', 'NETFLIXINC': 'NFLX', 'WHIRLPOOL CORP': 'WHR', 'DISNEY WALT CO': 'DIS',
                     'ASTERA LABS INC': 'ALAB', 'TEXAS INSTRS INC': 'TXN', 'INTELCORP': 'INTC', 'BERKSHIRE HATHAWAY INC NEW CL B UNSOLICITED': 'BRK-B',
                     'Apple Inc': 'AAPL'}
            for desc, want in cases.items():
                self.assertEqual(T(desc)[0], want, desc)
            for desc in ('MIAMI DADE CNTY FL AVIATION REV RFDG SER A B/E PTC 5.00 % Due Oct 1, 2031', 'INTEL CORP3.75% DUE 08 /05/27',
                         'VANGUARD S&P 500 ETF UNSOLICITED', 'SCHWAB GOVERNMENT MONEY FUND'):
                self.assertEqual(T(desc)[0], None, desc)


class Graph(unittest.TestCase):
    def test_officials_holder(self):
        today = dt.date(2026, 10, 22)
        trades = [{'person': 'A', 'ticker': 'NVDA', 'type': 'purchase', 'date': '2026-09-01', 'amount_min': 1001, 'amount_max': 15000},
                  {'person': 'B', 'ticker': 'NVDA', 'type': 'sale_partial', 'date': '2026-08-01', 'amount_min': 15001, 'amount_max': 50000},
                  {'person': 'A', 'ticker': 'NVDA', 'type': 'purchase', 'date': '2024-01-01', 'amount_min': 1001, 'amount_max': 15000},   # too old
                  {'person': 'C', 'ticker': 'XYZ', 'type': 'purchase', 'date': '2026-09-01', 'amount_min': 1001, 'amount_max': 15000,
                   'ticker_status': 'unlisted'}]
        h = XH.officials_holder(trades, 12, today=today)
        self.assertEqual(len(h['edges']), 1)
        e = h['edges'][0]
        self.assertEqual((e['ticker'], e['buyers'], e['sellers'], e['usd']), ('NVDA', 1, 1, round(8000.5 - 32500.5)))

    def test_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            u = universe(root, SEC_ROWS + [{'ticker': 'BLK', 'title': 'BlackRock, Inc.', 'cik': 2012383}])
            (root / 'cache' / 'crossholdings').mkdir(parents=True)
            (root / 'cache' / 'crossholdings' / 'sic.json').write_text(json.dumps({'1045810': {'sic': 3674}, '1652044': {'sic': 7370}, '2012383': {'sic': 6211}}))
            (root / 'cache' / 'crossholdings' / 'trump-accounts.json').write_text(json.dumps(
                {'fund': 'SPYM', 'weights': {'NVDA': 0.079, 'AAPL': 0.075, 'GOOGL': 0.03}, 'at': '2099-01-01T00:00:00+00:00'}))
            (root / 'market').mkdir()
            (root / 'market' / 'president.json').write_text(json.dumps({'tickers': [
                {'ticker': 'NVDA', 'buy_mid': 40000, 'sell_mid': 8000, 'net_mid': 32000, 'buys': 2, 'sells': 1, 'first': '2026-07-17', 'last': '2026-07-20'}],
                'stats': {'trades': 3, 'span': ['2026-07-17', '2026-07-20']}, 'filings': []}))

            def mgr(cik, name, positions, total):
                return {'cik': cik, 'label': name, 'snapshots': [{'period': '2026-06-30', 'filed': '2026-08-14', 'complete': True, 'total_usd': total,
                                                                 'positions': [{'ticker': t, 'shares': sh, 'value_usd': v, 'issuer': t} for t, sh, v in positions]}]}
            g = XH.Gather(XH.listed_ciks(root), 12, {})
            g.see(mgr(1045810, 'NVIDIA CORP', [('INTC', 214_776_632, 5_000_000_000), ('ARM', 1_100_000, 150_000_000)], 5_150_000_000))
            g.see(mgr(1652044, 'Alphabet Inc.', [('MBLY', 0, 0), ('INTC', 1000, 30_000)], 30_000))
            g.see(mgr(2012383, 'BlackRock, Inc.', [('NVDA', 2_000_000_000, 400e9), ('INTC', 400_000_000, 9e9)], 5e12))
            gov = XH.gov_holder(root)
            self.assertTrue(any(e['ticker'] == 'INTC' for e in gov['edges']))
            out = XH.build(root, u, g, [], client=None, cfg={'institutions': 5, 'president_top': 10, 'trump_accounts': {'funds': ['SPYM']}}, quarter='2026-06-30')
            self.assertEqual(out['corporate_filers'], 2)                  # Nvidia, Alphabet; BlackRock manages others' money
            d = json.loads((root / 'market' / 'crossholdings.json').read_text())
            kinds = {h['id']: h for h in d['holders']}
            self.assertEqual(kinds['president']['edges'][0]['ticker'], 'NVDA')
            self.assertEqual([e['ticker'] for e in kinds['ta']['edges']], ['NVDA', 'AAPL', 'GOOGL'])
            corp = next(h for h in d['holders'] if h['kind'] == 'corp' and h['ticker'] == 'NVDA')
            self.assertEqual(corp['edges'][0]['ticker'], 'INTC')
            self.assertTrue(all(e['usd'] > 0 for h in d['holders'] if h['kind'] == 'corp' for e in h['edges']))
            self.assertIn('BlackRock, Inc.', [i['name'] for i in d['institutions']])
            intc = next(c for c in d['companies'] if c['ticker'] == 'INTC')
            self.assertGreaterEqual(intc['f13_holders'], 2)
            nv = next(c for c in d['companies'] if c['ticker'] == 'NVDA')
            self.assertTrue(nv['is_holder'])
            # government → INTC and Nvidia → INTC, with Nvidia itself held by the President and the Trump Accounts
            self.assertTrue(any(ch['via'] == 'NVDA' and ch['to'] == 'INTC' for ch in d['chains']))


if __name__ == '__main__':
    unittest.main()
