"""filings_radar.py: the parsers (late filings, auditor changes, restatements, listing notices, SEC letters, buybacks,
dividends, offerings, IPOs, deals, CEO pay, contracts and lobbying) and one whole run against a fake SEC / Yahoo /
USAspending / LDA."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import filings_radar as F

TODAY = dt.date(2026, 10, 19)


class Parsers(unittest.TestCase):
    def test_form_index(self):
        lines = ['Form Type   Company Name   CIK   Date Filed  File Name', '-' * 80,
                 'NT 10-K'.ljust(17) + 'Flag Co'.ljust(62) + '111'.ljust(12) + '20261016    edgar/data/111/0000000111-26-000001.txt',
                 'SC TO-T'.ljust(17) + 'Target Two Inc'.ljust(62) + '666'.ljust(12) + '20261016    edgar/data/666/0000000777-26-000009.txt',
                 'SC TO-T'.ljust(17) + 'Acquirer Two'.ljust(62) + '777'.ljust(12) + '20261016    edgar/data/777/0000000777-26-000009.txt',
                 '10-Q'.ljust(17) + 'Other'.ljust(62) + '999'.ljust(12) + '20261016    edgar/data/999/0000000999-26-000001.txt']
        rows = F.parse_form_index('\n'.join(lines))
        self.assertEqual(rows[0], ('NT 10-K', 111, 'Flag Co', '2026-10-16', '0000000111-26-000001'))
        self.assertEqual([r[1] for r in rows], [111, 666, 777])                 # 10-Q is not on the radar; a tender under both parties

    def test_red_flags(self):
        a = F.parse_auditor_change('On October 14, 2026, the Audit Committee dismissed CBIZ CPAs P.C. (“CBIZ CPAs”) as the Company’s '
                                   'independent registered public accounting firm. There were no disagreements with CBIZ CPAs. The Audit '
                                   'Committee approved the engagement of BDO USA, P.C. (“BDO”) as the Company’s new independent registered public accounting firm.')
        self.assertEqual((a['change'], a['old'], a['new'], a['disagreements']), ('dismissed', 'CBIZ CPAs P.C.', 'BDO USA, P.C.', False))
        r = F.parse_auditor_change('Resignation of Independent Registered Public Accounting Firm On October 13, 2026, Stephano Slack LLC '
                                   '(“Stephano Slack”) resigned as the independent registered public accounting firm of Arrive AI Inc. The report '
                                   'included a paragraph on substantial doubt about its ability to continue as a going concern.')
        self.assertEqual((r['change'], r['old'], r['going_concern']), ('resigned', 'Stephano Slack LLC', True))
        self.assertEqual(F.severity('auditor', r), 'high')
        s = F.parse_restatement('On October 15, 2026, the Audit Committee concluded that the statements for the quarters ended March 31, 2026 '
                                'and June 30, 2026 should no longer be relied upon. The Company identified an error in the accounting for warrants.')
        self.assertEqual(s['periods'], ['2026-03-31', '2026-06-30'])
        self.assertIn('error in the accounting for warrants', s['reason'])
        n = F.parse_listing_notice('received a notice from the Listing Qualifications Department of The Nasdaq Stock Market LLC stating that the closing '
                                   'bid price of the common stock was below the minimum $1.00 per share requirement under Rule 5550(a)(2). The Company '
                                   'has until April 12, 2027 to regain compliance.')
        self.assertEqual((n['exchange'], n['reason_key'], n['deadline'], n['determination']), ('Nasdaq', 'bid_price', '2027-04-12', False))
        self.assertEqual(F.severity('listing', n), 'low')
        nt = F.parse_nt('PART III — NARRATIVE State below in reasonable detail why Forms 10-K could not be filed within the prescribed time period. '
                        'The Company requires additional time to complete its goodwill impairment test. PART IV — OTHER INFORMATION (3) Is it '
                        'anticipated that any significant change in results of operations ... ☒ Yes ☐ No')
        self.assertEqual(nt['reason'], 'The Company requires additional time to complete its goodwill impairment test')
        self.assertTrue(nt['significant_change'])

    def test_capital_and_dilution(self):
        b = F.parse_buyback('Apple announced that its Board authorized an additional $110 billion share repurchase program, which expires on December 31, 2028.')
        self.assertEqual((b['amount'], b['increase'], b['expires']), (110e9, True, '2028-12-31'))
        d = F.parse_dividend('declared a regular quarterly cash dividend of $0.87 per share, an increase of 5%, payable on November 13, 2026, '
                             'to shareholders of record at the close of business on October 30, 2026.')
        self.assertEqual((d['amount'], d['freq'], d['record'], d['payable'], d['change']), (0.87, 'quarterly', '2026-10-30', '2026-11-13', 'increase'))
        self.assertEqual(F.parse_dividend('declares increase in regular quarterly dividend to $0.87 per share, payable Nov. 26, 2026 to '
                                          'shareholders of record as of Nov. 12, 2026.')['amount'], 0.87)
        atm = F.parse_offering('Up to $150,000,000 Common Stock. We have entered into an Open Market Sale Agreement with Jefferies LLC. We may sell '
                               'shares of our common stock having an aggregate offering price of up to $150,000,000.', '424B5')
        self.assertEqual((atm['kind'], atm['amount']), ('atm', 150e6))
        firm = F.parse_offering('We are offering 12,500,000 shares of our common stock. The public offering price is $24.00 per share.', '424B5')
        self.assertEqual((firm['kind'], firm['amount']), ('firm', 3e8))
        self.assertEqual(F.parse_offering('$1,000,000,000 4.750% Senior Notes due 2036', '424B5')['kind'], 'debt')

    def test_ipo_and_deals(self):
        p = F.parse_ipo('20,000,000 Shares Class A Common Stock. This is the initial public offering of Acme Robotics, Inc. The initial public '
                        'offering price is $18.00 per share. Approved for listing on the Nasdaq Global Select Market under the symbol “ACME.” The date '
                        'of this prospectus is October 15, 2026. Lock-up: not to sell for 180 days after the date of this prospectus without the '
                        'prior written consent of the representatives.')
        self.assertEqual((p['ipo'], p['price'], p['shares'], p['symbol'], p['lockup_days'], p['date']), (True, 18.0, 2e7, 'ACME', 180, '2026-10-15'))
        d = F.parse_deal('entered into an Agreement and Plan of Merger with BigPharma Corp., a Delaware corporation. Merger Sub will merge with and '
                         'into the Company. Each share will be converted into the right to receive $45.50 per share in cash. The merger is expected '
                         'to close in the first quarter of 2027.')
        self.assertEqual((d['cash'], d['acquirer'], d['filer_is_target'], F.close_date(d['close_text'], '2026-10-12')),
                         (45.5, 'BigPharma Corp.', True, '2027-03-31'))
        m = F.parse_deal('entered into an Agreement and Plan of Merger with SmallCo Inc. Each share of SmallCo common stock will be converted into '
                         'the right to receive 0.4500 shares of Acquirer Holdings common stock and $10.00 in cash. Expected to close in the second half of 2027.')
        self.assertEqual((m['cash'], m['ratio'], m['target']), (10.0, 0.45, 'SmallCo Inc.'))
        s, ann, days = F.spread({'cash': 10.0, 'ratio': 0.45, 'acquirer_ticker': 'A', 'target_ticker': 'T', 'close_by': '2027-12-31'},
                                {'A': 100.0, 'T': 50.0}, TODAY)
        self.assertEqual((s, days), (0.1, 438))

    def test_letters_pay_and_gov(self):
        t = 'We note your non-GAAP measures. Please revise your segment disclosure (ASC 280) and identify the chief operating decision maker. Non-GAAP.'
        self.assertEqual(F.letter_topics(t), ['segments', 'non_gaap'])
        self.assertEqual(F.letter_about('Re: Form 10-K for the Fiscal Year Ended December 31, 2025'), ('10-K', '2025-12-31'))
        pr = F.paycomp_rows({'PeoTotalCompAmt': [('2023-12-31', 10e6), ('2024-12-31', 12e6), ('2025-12-31', 15e6)],
                             'PeoActuallyPaidCompAmt': [('2023-12-31', 9e6), ('2024-12-31', 14e6), ('2025-12-31', 4e6)],
                             'TotalShareholderRtnAmt': [('2023-12-31', 120), ('2024-12-31', 150), ('2025-12-31', 110)]})
        self.assertEqual((pr['total_chg'], pr['tsr_chg'], pr['misaligned']), (0.25, -0.2667, True))
        self.assertGreater(pr['corr'], 0.9)
        names = F.name_index([{'ticker': 'LMT', 'title': 'LOCKHEED MARTIN CORP'}, {'ticker': 'ACME', 'title': 'Acme Widgets Inc'}])
        self.assertEqual([F.match_recipient(x, names) for x in ('LOCKHEED MARTIN CORPORATION', 'RAYTHEON COMPANY', 'ACME WIDGETS FEDERAL LLC',
                                                               'ACME', 'SPACE EXPLORATION TECHNOLOGIES CORP')], ['LMT', 'RTX', 'ACME', None, None])
        q, issues = F.lobbying_quarters([
            {'filing_year': 2026, 'filing_period': 'second_quarter', 'expenses': '3000000', 'income': None,
             'registrant': {'name': 'LOCKHEED MARTIN CORPORATION'}, 'client': {'name': 'LOCKHEED MARTIN CORPORATION'},
             'lobbying_activities': [{'general_issue_code_display': 'Defense'}]},
            {'filing_year': 2026, 'filing_period': 'second_quarter', 'income': '250000', 'registrant': {'name': 'BIG LAW LLP'},
             'client': {'name': 'Lockheed Martin Corp'}, 'lobbying_activities': [{'general_issue_code_display': 'Budget/Appropriations'}]},
            {'filing_year': 2026, 'filing_period': 'second_quarter', 'income': '99', 'registrant': {'name': 'X'}, 'client': {'name': 'Other Co'}}],
            'LOCKHEED MARTIN CORP')
        self.assertEqual(q, {'2026Q2': 3250000.0})
        self.assertEqual(issues[0], 'Defense')

    def test_uudecode(self):
        import binascii
        data = b'%PDF-1.4 test bytes ' * 5
        enc = 'begin 644 x.pdf\n' + ''.join(binascii.b2a_uu(data[i:i + 45]).decode() for i in range(0, len(data), 45)) + '`\nend\n'
        self.assertEqual(F.uudecode(enc), data)


# ------------------------------------------------------------------ a whole run
def idx_line(form, name, cik, acc, day='20261016'):
    return form.ljust(17) + name.ljust(62) + str(cik).ljust(12) + f'{day}    edgar/data/{cik}/{acc}.txt'


def sub(typ, body, header=''):
    return f'<SEC-HEADER>\nCONFORMED SUBMISSION TYPE:\t{typ}\nFILED AS OF DATE:\t20261016\n{header}</SEC-HEADER>\n<DOCUMENT>\n<TYPE>{typ}\n<FILENAME>d.htm\n<TEXT>\n<html><p>{body}</p></html>\n</TEXT>\n</DOCUMENT>\n'


class FakeClient:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, url, sec=False, data=None, headers=None, allow_block=False):
        self.calls.append(url)
        for k, v in self.routes.items():
            if url == k or (k.endswith('*') and url.startswith(k[:-1])):
                v = v(url, data) if callable(v) else v
                return (v if isinstance(v, bytes) else (v if isinstance(v, str) else json.dumps(v)).encode()), url, ''
        raise RuntimeError('HTTP 404 from fake')

    def get(self, url, sec=False, headers=None, allow_block=False):
        return self.request(url, sec=sec, headers=headers)[0]


def folder(cik, acc):
    return F.folder(cik, acc)


class WholeRun(unittest.TestCase):
    def test_run_and_build(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            accs = {'nt': '0000000111-26-000001', 'up': '0000000222-26-000002', 'co': '0000000222-26-000003', 'atm': '0000000333-26-000004',
                    'ipo': '0000000444-26-000005', 'prox': '0000000555-26-000006', 'to': '0000000777-26-000009'}
            index = '\n'.join(['Form Type  Company Name  CIK  Date Filed  File Name', '-' * 60,
                               idx_line('NT 10-K', 'Flag Co', 111, accs['nt']), idx_line('UPLOAD', 'Big Corp', 222, accs['up']),
                               idx_line('CORRESP', 'Big Corp', 222, accs['co']), idx_line('424B5', 'Dilute Inc', 333, accs['atm']),
                               idx_line('424B4', 'Acme Robotics, Inc.', 444, accs['ipo']), idx_line('DEFM14A', 'Target Therapeutics', 555, accs['prox']),
                               idx_line('SC TO-T', 'Target Two Inc', 666, accs['to']), idx_line('SC TO-T', 'Acquirer Two Corp', 777, accs['to'])])
            tick = {str(i): {'cik_str': c, 'ticker': t, 'title': n} for i, (c, t, n) in enumerate(
                [(111, 'FLAG', 'Flag Co'), (222, 'BIG', 'Big Corp'), (333, 'DIL', 'Dilute Inc'), (555, 'TGT', 'Target Therapeutics'),
                 (666, 'TWO', 'Target Two Inc'), (777, 'ACQ', 'Acquirer Two Corp'), (888, 'AUD', 'Auditor Swap Inc'), (999, 'BUY', 'Buyback Corp'),
                 (1000, 'DIV', 'Dividend Co'), (1001, 'LMT', 'LOCKHEED MARTIN CORP'), (1002, 'PARENT', 'BigPharma Corp')])}
            letter = ('Re: Big Corp Form 10-K for the Fiscal Year Ended December 31, 2025. We note your revenue recognition policy under ASC 606. '
                      'Please tell us how you identify performance obligations. Please revise your non-GAAP measures.')
            routes = {
                F.TICKERS: tick,
                'https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.20261016.idx': index,
                folder(111, accs['nt']) + accs['nt'] + '.txt': sub('NT 10-K', 'PART III — NARRATIVE could not be filed within the prescribed time period. '
                                                                   'The Company needs more time to finish its inventory count. PART IV other'),
                folder(222, accs['up']) + 'index.json': {'directory': {'item': [{'name': 'filename1.htm', 'size': '4000'}]}},
                folder(222, accs['up']) + 'filename1.htm': f'<p>{letter}</p>',
                folder(222, accs['co']) + 'index.json': {'directory': {'item': [{'name': 'response.htm', 'size': '4000'}]}},
                folder(222, accs['co']) + 'response.htm': '<p>In response to the Staff’s comment on revenue recognition (ASC 606), we have revised.</p>',
                folder(333, accs['atm']) + 'index.json': {'directory': {'item': [{'name': 'd1424b5.htm', 'size': '90000'}, {'name': 'ex5-1.htm', 'size': '95000'}]}},
                folder(333, accs['atm']) + 'd1424b5.htm': '<p>Up to $150,000,000 Common Stock. Open Market Sale Agreement with Jefferies. Shares of our common stock '
                                                          'having an aggregate offering price of up to $150,000,000.</p>',
                folder(444, accs['ipo']) + 'index.json': {'directory': {'item': [{'name': 'prospectus.htm', 'size': '900000'}]}},
                folder(444, accs['ipo']) + 'prospectus.htm': '<p>20,000,000 Shares Class A Common Stock. This is the initial public offering. The initial public '
                                                             'offering price is $18.00 per share. Listed on the Nasdaq Global Select Market under the symbol “ACME.” '
                                                             'The date of this prospectus is October 15, 2026.</p>',
                folder(555, accs['prox']) + accs['prox'] + '.txt': sub('DEFM14A', 'Agreement and Plan of Merger with BigPharma Corp., a Delaware corporation. '
                                                                       'Merger Sub will merge with and into the Company. You will be entitled to receive '
                                                                       '$45.50 in cash per share. The merger is expected to close in the first quarter of 2027.'),
                folder(666, accs['to']) + accs['to'] + '.txt': sub('SC TO-T', 'Offer to purchase all outstanding shares at $12.00 per share, net to the '
                                                                   'seller in cash. The offer will expire at one minute after 11:59 p.m. on November 20, 2026.',
                                                                   'SUBJECT COMPANY:\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\tTarget Two Inc\n\t\tCENTRAL INDEX KEY:\t0000000666\n'
                                                                   'FILED BY:\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\tAcquirer Two Corp\n\t\tCENTRAL INDEX KEY:\t0000000777\n'),
                F.CHART.format(sym='TGT', rng='6mo'): {'chart': {'result': [{'timestamp': [1760572800], 'indicators': {'quote': [{'close': [44.0]}]}}]}},
                F.CHART.format(sym='TWO', rng='6mo'): {'chart': {'result': [{'timestamp': [1760572800], 'indicators': {'quote': [{'close': [11.9]}]}}]}},
                F.CHART.format(sym='ACME', rng='2y'): {'chart': {'result': [{'timestamp': [1760572800, 1760659200], 'indicators': {'quote': [{'close': [24.0, 27.0]}]}}]}},
                F.USA + 'search/spending_by_category/recipient/': {'results': [{'name': 'LOCKHEED MARTIN CORPORATION', 'amount': 2.5e9, 'recipient_id': 'x'}],
                                                                   'page_metadata': {'hasNext': False}},
                F.USA + 'search/spending_by_award/': {'results': [{'Award ID': 'A1', 'Recipient Name': 'LOCKHEED MARTIN CORP', 'Award Amount': 9e8,
                                                                   'Awarding Agency': 'Department of Defense', 'Start Date': '2026-10-10'}]},
                F.LDA[0] + 'filings/*': {'results': [{'filing_year': 2026, 'filing_period': 'second_quarter', 'expenses': '3000000',
                                                     'registrant': {'name': 'LOCKHEED MARTIN CORPORATION'}, 'client': {'name': 'LOCKHEED MARTIN CORPORATION'},
                                                     'lobbying_activities': [{'general_issue_code_display': 'Defense'}]}], 'next': None},
            }
            for i, (q, cik_vals) in enumerate([('CY2026Q2I', {}), ('CY2026Q1I', {}), ('CY2025Q4I', {}), ('CY2025Q3I', {}), ('CY2025Q2I', {})]):
                vals = {111: 1e8, 222: 1e9, 333: 4e7 if i else 5e7, 555: 1e8, 666: 2e8, 777: 3e8, 888: 1e7, 999: 5e8, 1000: 2e8, 1001: 2.4e8}
                if i == 4:
                    vals[333] = 2.5e7
                routes[F.FRAME.format(tax='us-gaap', concept='CommonStockSharesOutstanding', unit='shares', period=q)] = \
                    {'data': [{'cik': c, 'val': v, 'end': '2026-06-30'} for c, v in vals.items()]}
            routes[F.FRAME.format(tax='us-gaap', concept='PaymentsForRepurchaseOfCommonStock', unit='USD', period='CY2025')] = \
                {'data': [{'cik': 999, 'val': 4e9, 'end': '2025-12-31'}]}
            routes[F.CONCEPT.format(cik=1001, tax='ecd', concept='PeoTotalCompAmt')] = {'units': {'USD': [
                {'end': '2024-12-31', 'val': 20e6, 'form': 'DEF 14A'}, {'end': '2025-12-31', 'val': 25e6, 'form': 'DEF 14A'}]}}
            routes[F.CONCEPT.format(cik=1001, tax='ecd', concept='TotalShareholderRtnAmt')] = {'units': {'USD': [
                {'end': '2024-12-31', 'val': 150, 'form': 'DEF 14A'}, {'end': '2025-12-31', 'val': 120, 'form': 'DEF 14A'}]}}
            # the hub's 8-K events: an auditor change, a buyback, a dividend, a merger agreement
            ev = [{'accession': '0000000888-26-000010', 'cik': '888', 'filed': '2026-10-15', 'items': ['4.01', '9.01'], 'topics': ['auditor'],
                   'url': folder(888, '0000000888-26-000010'), 'quote': 'Stephano Slack LLC resigned', 'headline': ''},
                  {'accession': '0000000999-26-000011', 'cik': '999', 'filed': '2026-10-16', 'items': ['8.01'], 'topics': ['buyback'],
                   'url': folder(999, '0000000999-26-000011'), 'quote': '', 'headline': 'Buyback Corp authorizes $2 billion repurchase'},
                  {'accession': '0000001000-26-000012', 'cik': '1000', 'filed': '2026-10-16', 'items': ['8.01'], 'topics': ['dividend'],
                   'url': folder(1000, '0000001000-26-000012'), 'quote': '', 'headline': 'Dividend Co raises dividend'},
                  {'accession': '0000000555-26-000013', 'cik': '555', 'filed': '2026-10-12', 'items': ['1.01'], 'topics': ['deal'],
                   'url': folder(555, '0000000555-26-000013'), 'quote': 'Agreement and Plan of Merger', 'headline': ''},
                  {'accession': '0000000222-26-000014', 'cik': '222', 'filed': '2026-10-16', 'items': ['2.02'], 'topics': ['earnings'],
                   'url': folder(222, '0000000222-26-000014'), 'quote': '', 'headline': ''}]
            e8 = '<DOCUMENT>\n<TYPE>8-K\n<TEXT>\n<p>{}</p>\n</TEXT>\n</DOCUMENT>'
            routes[folder(888, '0000000888-26-000010') + '0000000888-26-000010.txt'] = e8.format(
                'Item 4.01 Changes in Registrant’s Certifying Accountant.</p><p>On October 13, 2026, Stephano Slack LLC (“Stephano Slack”) resigned as the '
                'independent registered public accounting firm of the Company. There were no disagreements.')
            routes[folder(999, '0000000999-26-000011') + '0000000999-26-000011.txt'] = e8.format(
                'Item 8.01 Other Events.</p><p>The Board authorized a share repurchase program of up to $2 billion of common stock with no expiration date.')
            routes[folder(1000, '0000001000-26-000012') + '0000001000-26-000012.txt'] = e8.format(
                'Item 8.01 Other Events.</p><p>The Board raised its regular quarterly dividend to $0.50 per share, payable on November 30, 2026, to '
                'shareholders of record on November 2, 2026.')
            routes[folder(555, '0000000555-26-000013') + '0000000555-26-000013.txt'] = e8.format(
                'Item 1.01 Entry into a Material Definitive Agreement.</p><p>The Company entered into an Agreement and Plan of Merger with BigPharma '
                'Corp., a Delaware corporation. Merger Sub will merge with and into the Company. Each share will be converted into the right to receive '
                '$45.50 per share in cash. The merger is expected to close in the first quarter of 2027.')
            (d / 'ev.json').write_text(json.dumps({'rows': ev}))
            (d / 'off.json').write_text(json.dumps({'trades': [
                {'ticker': 'LMT', 'ticker_canon': 'LMT', 'ticker_status': 'listed', 'name_check': 'matches', 'asset_type': 'ST', 'type': 'purchase',
                 'date': '2026-10-01', 'filed_date': '2026-10-10', 'amount_min': 15001, 'amount_max': 50000, 'person': 'Jane Roe', 'jurisdiction': 'US House'}]}))
            pr = d / 'rh' / 't'
            pr.mkdir(parents=True)
            for t, c in {'FLAG': 5.0, 'BIG': 100.0, 'DIL': 10.0, 'BUY': 80.0, 'DIV': 40.0, 'LMT': 450.0, 'AUD': 2.0, 'PARENT': 60.0, 'ACQ': 30.0}.items():
                (pr / f'{t}.json').write_text(json.dumps({'t': t, 'start': '2026-01-02', 'c': [c * 0.9, c]}))
            fake = FakeClient(routes)
            st = F.run_all(d / 'rf', d / 'ev.json', d / 'off.json', d / 'rh', minutes=5, backfill=5, client=fake, today=TODAY)
            pub = d / 'rf' / 'public'
            flags = json.loads((pub / 'redflags.json').read_text())['rows']
            kinds = {(r['ticker'], r['kind']) for r in flags}
            self.assertEqual(kinds, {('FLAG', 'late'), ('AUD', 'auditor')})
            aud = next(r for r in flags if r['kind'] == 'auditor')
            self.assertEqual((aud['old'], aud['change'], aud['severity']), ('Stephano Slack LLC', 'resigned', 'high'))
            late = next(r for r in flags if r['kind'] == 'late')
            self.assertIn('inventory count', late['reason'])
            th = json.loads((pub / 'letters.json').read_text())['threads']
            self.assertEqual((th[0]['ticker'], th[0]['n'], th[0]['topics'][0], th[0]['about_form']), ('BIG', 2, 'revenue', '10-K'))
            cap = json.loads((pub / 'capital.json').read_text())
            self.assertEqual((cap['buybacks'][0]['ticker'], cap['buybacks'][0]['amount'], cap['buybacks'][0]['pct_mcap']), ('BUY', 2e9, 0.05))
            self.assertEqual((cap['upcoming'][0]['ticker'], cap['upcoming'][0]['record'], cap['upcoming'][0]['yield']), ('DIV', '2026-11-02', 0.05))
            self.assertEqual(cap['returns'][0]['ticker'], 'BUY')                       # $4B of buybacks on a $40B market cap
            dil = json.loads((pub / 'dilution.json').read_text())
            self.assertEqual((dil['offerings'][0]['kind'], dil['offerings'][0]['pct_mcap']), ('atm', 0.3))
            self.assertEqual((dil['share_growth'][0]['ticker'], dil['share_growth'][0]['change']), ('DIL', 1.0))
            ipo = json.loads((pub / 'ipos.json').read_text())['priced'][0]
            self.assertEqual((ipo['symbol'], ipo['raised'], ipo['lockup_ends'], ipo['since_ipo']), ('ACME', 3.6e8, '2027-04-13', 0.5))
            deals = {x['target_ticker']: x for x in json.loads((pub / 'deals.json').read_text())['deals']}
            self.assertEqual((deals['TGT']['cash'], deals['TGT']['acquirer_ticker'], deals['TGT']['close_by']), (45.5, 'PARENT', '2027-03-31'))
            self.assertEqual(round(deals['TGT']['spread'], 4), round(45.5 / 44 - 1, 4))
            self.assertEqual(len(deals['TGT']['docs']), 2)                              # the 8-K and the proxy, one deal
            self.assertEqual((deals['TWO']['cash'], deals['TWO']['acquirer_ticker'], deals['TWO']['close_by']), (12.0, 'ACQ', '2026-11-20'))
            pay = json.loads((pub / 'paycomp.json').read_text())['rows']
            self.assertEqual((pay[0]['ticker'], pay[0]['total_chg'], pay[0]['misaligned']), ('LMT', 0.25, True))
            gov = json.loads((pub / 'gov.json').read_text())
            self.assertEqual((gov['contracts'][0]['ticker'], gov['awards'][0]['ticker'], gov['lobbying'][0]['trailing4']), ('LMT', 'LMT', 3e6))
            self.assertEqual((gov['overlap'][0]['person'], gov['overlap'][0]['contracts_90d']), ('Jane Roe', 2.5e9))
            c = json.loads((pub / 'c' / 'LMT.json').read_text())
            self.assertTrue(c['contracts'] and c['lobbying'] and c['officials'] and c['paycomp'])
            self.assertEqual(st['deals_pending'], 2)
            self.assertFalse(st['errors'], st['errors'])
            # a second run reads nothing it already read
            n0 = len(fake.calls)
            F.run_all(d / 'rf', d / 'ev.json', d / 'off.json', d / 'rh', minutes=5, backfill=5, client=fake, today=TODAY)
            again = [u for u in fake.calls[n0:] if 'Archives/edgar/data' in u]
            self.assertEqual(again, [])


if __name__ == '__main__':
    unittest.main()
