"""Insiders from SEC's Form 3/4/5 data sets (app/insiders_history.py): each owner's holdings at each quarter-end — the
latest report of each holding, direct and indirect, footnotes read for "See footnote" — counted once beside 13F (an
owner that files 13F, a block a 13F holder reports, one family block several owners report), stale holdings dropped,
valued at the quarter's 13F price; and the data sets listed and read."""
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import holders_history as HH  # noqa: E402
import insiders_history as I  # noqa: E402

TABLES = {
    'SUBMISSION': ['ACCESSION_NUMBER', 'FILING_DATE', 'PERIOD_OF_REPORT', 'DATE_OF_ORIG_SUB', 'NO_SECURITIES_OWNED', 'NOT_SUBJECT_SEC16',
                   'FORM3_HOLDINGS_REPORTED', 'FORM4_TRANS_REPORTED', 'DOCUMENT_TYPE', 'ISSUERCIK', 'ISSUERNAME', 'ISSUERTRADINGSYMBOL', 'REMARKS', 'AFF10B5ONE'],
    'REPORTINGOWNER': ['ACCESSION_NUMBER', 'RPTOWNERCIK', 'RPTOWNERNAME', 'RPTOWNER_RELATIONSHIP', 'RPTOWNER_TITLE', 'RPTOWNER_TXT', 'RPTOWNER_STREET1',
                       'RPTOWNER_STREET2', 'RPTOWNER_CITY', 'RPTOWNER_STATE', 'RPTOWNER_ZIPCODE', 'RPTOWNER_STATE_DESC', 'FILE_NUMBER'],
    'NONDERIV_TRANS': ['ACCESSION_NUMBER', 'NONDERIV_TRANS_SK', 'SECURITY_TITLE', 'SECURITY_TITLE_FN', 'TRANS_DATE', 'TRANS_DATE_FN', 'DEEMED_EXECUTION_DATE',
                       'DEEMED_EXECUTION_DATE_FN', 'TRANS_FORM_TYPE', 'TRANS_CODE', 'EQUITY_SWAP_INVOLVED', 'EQUITY_SWAP_TRANS_CD_FN', 'TRANS_TIMELINESS',
                       'TRANS_TIMELINESS_FN', 'TRANS_SHARES', 'TRANS_SHARES_FN', 'TRANS_PRICEPERSHARE', 'TRANS_PRICEPERSHARE_FN', 'TRANS_ACQUIRED_DISP_CD',
                       'TRANS_ACQUIRED_DISP_CD_FN', 'SHRS_OWND_FOLWNG_TRANS', 'SHRS_OWND_FOLWNG_TRANS_FN', 'VALU_OWND_FOLWNG_TRANS', 'VALU_OWND_FOLWNG_TRANS_FN',
                       'DIRECT_INDIRECT_OWNERSHIP', 'DIRECT_INDIRECT_OWNERSHIP_FN', 'NATURE_OF_OWNERSHIP', 'NATURE_OF_OWNERSHIP_FN'],
    'NONDERIV_HOLDING': ['ACCESSION_NUMBER', 'NONDERIV_HOLDING_SK', 'SECURITY_TITLE', 'SECURITY_TITLE_FN', 'TRANS_FORM_TYPE', 'TRANS_FORM_TYPE_FN',
                         'SHRS_OWND_FOLWNG_TRANS', 'SHRS_OWND_FOLWNG_TRANS_FN', 'VALU_OWND_FOLWNG_TRANS', 'VALU_OWND_FOLWNG_TRANS_FN',
                         'DIRECT_INDIRECT_OWNERSHIP', 'DIRECT_INDIRECT_OWNERSHIP_FN', 'NATURE_OF_OWNERSHIP', 'NATURE_OF_OWNERSHIP_FN'],
    'DERIV_TRANS': ['ACCESSION_NUMBER', 'DERIV_TRANS_SK', 'SECURITY_TITLE', 'SECURITY_TITLE_FN', 'CONV_EXERCISE_PRICE', 'CONV_EXERCISE_PRICE_FN', 'TRANS_DATE',
                    'TRANS_DATE_FN', 'DEEMED_EXECUTION_DATE', 'DEEMED_EXECUTION_DATE_FN', 'TRANS_FORM_TYPE', 'TRANS_CODE', 'EQUITY_SWAP_INVOLVED',
                    'EQUITY_SWAP_TRANS_CD_FN', 'TRANS_TIMELINESS', 'TRANS_TIMELINESS_FN', 'TRANS_SHARES', 'TRANS_SHARES_FN', 'TRANS_TOTAL_VALUE',
                    'TRANS_TOTAL_VALUE_FN', 'TRANS_PRICEPERSHARE', 'TRANS_PRICEPERSHARE_FN', 'TRANS_ACQUIRED_DISP_CD', 'TRANS_ACQUIRED_DISP_CD_FN',
                    'EXCERCISE_DATE', 'EXCERCISE_DATE_FN', 'EXPIRATION_DATE', 'EXPIRATION_DATE_FN', 'UNDLYNG_SEC_TITLE', 'UNDLYNG_SEC_TITLE_FN',
                    'UNDLYNG_SEC_SHARES', 'UNDLYNG_SEC_SHARES_FN', 'UNDLYNG_SEC_VALUE', 'UNDLYNG_SEC_VALUE_FN', 'SHRS_OWND_FOLWNG_TRANS',
                    'SHRS_OWND_FOLWNG_TRANS_FN', 'VALU_OWND_FOLWNG_TRANS', 'VALU_OWND_FOLWNG_TRANS_FN', 'DIRECT_INDIRECT_OWNERSHIP',
                    'DIRECT_INDIRECT_OWNERSHIP_FN', 'NATURE_OF_OWNERSHIP', 'NATURE_OF_OWNERSHIP_FN'],
    'DERIV_HOLDING': ['ACCESSION_NUMBER', 'DERIV_HOLDING_SK', 'SECURITY_TITLE', 'SECURITY_TITLE_FN', 'CONV_EXERCISE_PRICE', 'CONV_EXERCISE_PRICE_FN',
                      'TRANS_FORM_TYPE', 'TRANS_FORM_TYPE_FN', 'EXERCISE_DATE', 'EXERCISE_DATE_FN', 'EXPIRATION_DATE', 'EXPIRATION_DATE_FN',
                      'UNDLYNG_SEC_TITLE', 'UNDLYNG_SEC_TITLE_FN', 'UNDLYNG_SEC_SHARES', 'UNDLYNG_SEC_SHARES_FN', 'UNDLYNG_SEC_VALUE',
                      'UNDLYNG_SEC_VALUE_FN', 'SHRS_OWND_FOLWNG_TRANS', 'SHRS_OWND_FOLWNG_TRANS_FN', 'VALU_OWND_FOLWNG_TRANS',
                      'VALU_OWND_FOLWNG_TRANS_FN', 'DIRECT_INDIRECT_OWNERSHIP', 'DIRECT_INDIRECT_OWNERSHIP_FN', 'NATURE_OF_OWNERSHIP', 'NATURE_OF_OWNERSHIP_FN'],
    'FOOTNOTES': ['ACCESSION_NUMBER', 'FOOTNOTE_ID', 'FOOTNOTE_TXT'],
}
TSLA, BRK, META, SPLT = '0001318605', '0001067983', '0001326801', '0000000777'


def row(table, **kv):
    return [str(kv.get(h, '')) for h in TABLES[table]]


def filing(acc, filed, period, issuer, owners):
    return ([row('SUBMISSION', ACCESSION_NUMBER=acc, FILING_DATE=filed, PERIOD_OF_REPORT=period, DOCUMENT_TYPE='4', ISSUERCIK=issuer)],
            [row('REPORTINGOWNER', ACCESSION_NUMBER=acc, RPTOWNERCIK=c, RPTOWNERNAME=n, RPTOWNER_RELATIONSHIP=r, RPTOWNER_TITLE=t) for c, n, r, t in owners])


def make_set(path):
    T = {k: [] for k in TABLES}
    def add(acc, filed, period, issuer, owners, lines=(), fns=()):
        s, o = filing(acc, filed, period, issuer, owners)
        T['SUBMISSION'] += s
        T['REPORTINGOWNER'] += o
        for table, kv in lines:
            T[table].append(row(table, ACCESSION_NUMBER=acc, **kv))
        for fid, txt in fns:
            T['FOOTNOTES'].append(row('FOOTNOTES', ACCESSION_NUMBER=acc, FOOTNOTE_ID=fid, FOOTNOTE_TXT=txt))
    musk = [('0001494730', 'Musk Elon', 'Director,Officer,TenPercentOwner', 'CEO')]
    # Musk: his trust's shares after two trades on one day (the later line counts), a direct award held, an RSU left out
    add('A1', '15-SEP-2025', '12-SEP-2025', TSLA, musk, [
        ('NONDERIV_TRANS', dict(NONDERIV_TRANS_SK=10, SECURITY_TITLE='Common Stock', TRANS_DATE='12-SEP-2025', TRANS_CODE='P', TRANS_PRICEPERSHARE='379.2', SHRS_OWND_FOLWNG_TRANS='411000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='By Trust')),
        ('NONDERIV_TRANS', dict(NONDERIV_TRANS_SK=11, SECURITY_TITLE='Common Stock', TRANS_DATE='12-SEP-2025', TRANS_CODE='P', TRANS_PRICEPERSHARE='381.5', SHRS_OWND_FOLWNG_TRANS='411200.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='By Trust')),
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=5, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='96000.0', DIRECT_INDIRECT_OWNERSHIP='D')),
        ('DERIV_TRANS', dict(DERIV_TRANS_SK=7, SECURITY_TITLE='Restricted Stock Unit', TRANS_DATE='12-SEP-2025', SHRS_OWND_FOLWNG_TRANS='78458.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    add('A2', '04-AUG-2025', '03-AUG-2025', TSLA, musk, [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=3, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='410000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='By Trust'))])
    # Berkshire's shares in Warren Buffett's own Form 4 (the same 300 shares as Berkshire's 13F), and Berkshire itself
    add('B1', '10-SEP-2025', '08-SEP-2025', TSLA, [('0000315090', 'BUFFETT WARREN E', 'TenPercentOwner', '')], [
        ('NONDERIV_TRANS', dict(NONDERIV_TRANS_SK=1, SECURITY_TITLE='Common Stock', TRANS_DATE='08-SEP-2025', SHRS_OWND_FOLWNG_TRANS='300.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='By Berkshire Hathaway Inc.'))])
    add('B2', '10-SEP-2025', '08-SEP-2025', TSLA, [('0000000999', 'BERKSHIRE HATHAWAY INC', 'TenPercentOwner', '')], [
        ('NONDERIV_TRANS', dict(NONDERIV_TRANS_SK=1, SECURITY_TITLE='Common Stock', TRANS_DATE='08-SEP-2025', SHRS_OWND_FOLWNG_TRANS='305.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    # one family company's shares in two owners' reports ("See footnote" both): counted once, for the owner with the most
    fam = 'Held by Walton Enterprises, LLC, of which the reporting person is a managing member.'
    add('W1', '20-AUG-2025', '18-AUG-2025', TSLA, [('0000000501', 'WALTON JIM C', 'TenPercentOwner', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='200000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='See Footnote', NATURE_OF_OWNERSHIP_FN='F1'))],
        [('F1', fam)])
    add('W2', '21-AUG-2025', '19-AUG-2025', TSLA, [('0000000502', 'Walton Rob', 'Director', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='200000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='See footnote (2)', NATURE_OF_OWNERSHIP_FN='F2')),
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=2, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='10.0', DIRECT_INDIRECT_OWNERSHIP='D'))],
        [('F2', fam)])
    # a company's board member reporting the company's shares ("by Daimler North America"): named with it
    add('D1', '22-AUG-2025', '20-AUG-2025', TSLA, [('0000000901', 'KROEGER HARALD', 'Director', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='90000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='By Daimler North America Corporation'))])
    # two directors with the same number of shares of their own: two holdings, not one block
    for acc, cik, nm in (('E1', '0000000911', 'SAME ONE'), ('E2', '0000000912', 'SAME TWO')):
        add(acc, '23-AUG-2025', '21-AUG-2025', TSLA, [(cik, nm, 'Director', '')], [
            ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='60000.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    # a fund's general partner, the fund and a director in one joint filing (the partner's aggregate: 157,000), the fund's
    # own report (120,000, part of it) and the director's own shares: the partner counts, the director's own shares too
    add('J1', '24-AUG-2025', '22-AUG-2025', TSLA, [('0000000921', 'SILVER LAKE GROUP, L.L.C.', 'TenPercentOwner', ''),
                                                  ('0000000922', 'SILVER LAKE TECHNOLOGY ASSOCIATES V, L.P.', 'TenPercentOwner', ''),
                                                  ('0000000923', 'DURBAN EGON', 'Director', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='157000.0', DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='See footnotes', NATURE_OF_OWNERSHIP_FN='F1'))],
        [('F1', 'Held by SL SPV-2, L.P. and Silver Lake Technology Associates V, L.P.')])
    add('J2', '25-AUG-2025', '22-AUG-2025', TSLA, [('0000000922', 'SILVER LAKE TECHNOLOGY ASSOCIATES V, L.P.', 'TenPercentOwner', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='120000.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    add('J3', '25-AUG-2025', '22-AUG-2025', TSLA, [('0000000923', 'DURBAN EGON', 'Director', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='5000.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    for acc, filed, n, txt in (('O1', '12-DEC-2024', '152713846.0', 'Continued from footnote: National Indemnity Company, Berkshire Hathaway'),
                               ('O2', '11-FEB-2025', '264941431.0', 'The shares reported on this form are held by Berkshire Hathaway subsidiaries')):
        add(acc, filed, filed, '0000797468', [('0000315090', 'BUFFETT WARREN E', 'TenPercentOwner', '')], [
            ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS=n, DIRECT_INDIRECT_OWNERSHIP='I', NATURE_OF_OWNERSHIP='See Footnote', NATURE_OF_OWNERSHIP_FN='F3'))],
            [('F3', txt)])
    # a class of common stock held in the derivative table (Class B, convertible one for one)
    add('Z1', '05-SEP-2025', '02-SEP-2025', TSLA, [('0000000601', 'ZUCK MARK', 'Director,Officer', 'Chair')], [
        ('DERIV_HOLDING', dict(DERIV_HOLDING_SK=1, SECURITY_TITLE='Class B Common Stock', SHRS_OWND_FOLWNG_TRANS='50.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    # an officer's last report: counted for two years, then left out
    add('G1', '01-JUL-2025', '30-JUN-2025', TSLA, [('0000000701', 'Person Gone', 'Officer', 'CFO')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='40.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    # Berkshire's own insiders: class A at 1,500 class B (as the 13F side counts it)
    add('K1', '01-SEP-2025', '29-AUG-2025', BRK, [('0000315090', 'BUFFETT WARREN E', 'Director,Officer,TenPercentOwner', 'Chair & CEO')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Class A Common Stock', SHRS_OWND_FOLWNG_TRANS='10.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    # a stock split 5 for 1 in Q3 2020: a report before the quarter, one inside it at a pre-split price, one late in it
    # with no price (after the split)
    add('S1', '04-MAY-2020', '01-MAY-2020', SPLT, [('0000000801', 'Big Founder', 'Director,TenPercentOwner', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='100.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    add('S2', '17-AUG-2020', '15-AUG-2020', SPLT, [('0000000802', 'Quarter Mid', 'Officer', 'CTO')], [
        ('NONDERIV_TRANS', dict(NONDERIV_TRANS_SK=1, SECURITY_TITLE='Common Stock', TRANS_DATE='15-AUG-2020', TRANS_CODE='S', TRANS_PRICEPERSHARE='900', SHRS_OWND_FOLWNG_TRANS='50.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    add('S3', '11-SEP-2020', '10-SEP-2020', SPLT, [('0000000803', 'Report Late', 'Director', '')], [
        ('NONDERIV_HOLDING', dict(NONDERIV_HOLDING_SK=1, SECURITY_TITLE='Common Stock', SHRS_OWND_FOLWNG_TRANS='70.0', DIRECT_INDIRECT_OWNERSHIP='D'))])
    with zipfile.ZipFile(path, 'w') as z:
        for name, head in TABLES.items():
            z.writestr(f'{name}.tsv', '\n'.join('\t'.join(r) for r in [head] + T[name]) + '\n')


PAGE_HTML = ('<a href="/files/structureddata/data/insider-transactions-data-sets/2009q4_form345.zip">2009 Q4</a>'
             '<a href="/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip">2026 Q3</a>'
             '<a href="/files/structureddata/data/insider-transactions-data-sets/2025q3_form345.zip">2025 Q3</a>')


class Insiders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.zip = self.tmp / 'fixture.zip'
        make_set(self.zip)
        self.hub = self.tmp / 'hub'
        (self.hub / 'cache' / 'prices').mkdir(parents=True)
        (self.hub / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': [
            {'ticker': 'TSLA', 'title': 'Tesla, Inc.', 'cik': 1318605}, {'ticker': 'BRK-B', 'title': 'BERKSHIRE HATHAWAY INC', 'cik': 1067983},
            {'ticker': 'BRK-A', 'title': 'BERKSHIRE HATHAWAY INC', 'cik': 1067983}, {'ticker': 'META', 'title': 'Meta Platforms', 'cik': 1326801},
            {'ticker': 'SPLT', 'title': 'Split Co', 'cik': 777}]}))
        self.root = self.tmp / 'hh'
        c = self.root / 'public' / 'c'
        c.mkdir(parents=True)
        P = ['2025-06-30', '2025-09-30', '2025-12-31', '2027-12-31']
        (c / 'TSLA.json').write_text(json.dumps({'ticker': 'TSLA', 'name': 'Tesla, Inc.', 'periods': P,
            'total': [[100, 10_000_000, 3e9], [100, 10_000_000, 4e9], [100, 10_000_000, 4.5e9], [100, 1_000_000_000, 5e11]],   # the last: none of them half a percent
            'who': [['c102909', 'Vanguard Group', 'Vanguard', [102909]], ['c999', 'Berkshire Hathaway', 'Berkshire', [999]]],
            'top': [[[0, 500, 150000]], [[0, 500, 200000], [1, 300, 120000]], [[0, 500, 225000], [1, 300, 135000]], [[0, 500, 250000]]]}))
        (c / 'BRK-B.json').write_text(json.dumps({'ticker': 'BRK-B', 'name': 'Berkshire Hathaway', 'periods': ['2025-09-30'],
            'total': [[50, 20000, 10000000]], 'who': [['c102909', 'Vanguard Group', 'Vanguard', [102909]]], 'top': [[[0, 9000, 4500000]]]}))
        after = [[0, 2500, 550000], [1, 1500, 330000], [2, 600, 132000]]
        (c / 'SPLT.json').write_text(json.dumps({'ticker': 'SPLT', 'name': 'Split Co', 'periods': ['2020-06-30', '2020-09-30', '2020-12-31'],
            'total': [[10, 1000, 1000000], [10, 5000, 1100000], [10, 5000, 1200000]], 'who': [['c1', 'A', 'A', [1]], ['c2', 'B', 'B', [2]], ['c3', 'C', 'C', [3]]],
            'top': [[[0, 500, 500000], [1, 300, 300000], [2, 120, 120000]], after, after]}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self, url, dest=None):
        if url == I.PAGE:
            return PAGE_HTML.encode()
        if url.endswith('2026q3_form345.zip'):
            raise HH.Missing(url)
        shutil.copy(self.zip, dest)
        return dest

    def test_listing_follows_the_pages_links_from_2010(self):
        sets = I.listing(PAGE_HTML)
        self.assertEqual([n for _, n in sets], ['2025q3_form345.zip', '2026q3_form345.zip'])
        self.assertTrue(sets[1][0].startswith('https://www.sec.gov/files/datastandardsinnovation/'), 'the newest live at another address')

    def test_read_set(self):
        d = I.read_set(self.zip)
        musk = d['points']['1318605']['1494730']
        self.assertEqual(musk['|I:by trust'], [['2025-09-12', '2025-09-15', 411200, 381.5, 'By Trust']], 'the last line of the day, one point a quarter, the trade price, its words')
        self.assertEqual(musk['|D'], [['2025-09-12', '2025-09-15', 96000, 381.5, '']], "a holding: its filing's trade price")
        self.assertEqual(set(musk), {'|I:by trust', '|D'}, 'the RSU is not a share')
        self.assertIn('B|D', d['points']['1318605']['601'], 'Class B common stock in the derivative table')
        jim = d['points']['1318605']['501']['|I:fn#1']
        self.assertEqual(jim[0][4], 'Held by Walton Enterprises, LLC, of which the reporting person is a managing member.', 'a footnoted holding: its place, the footnote\'s words')
        self.assertEqual(d['groups'], {'1318605': [[921, 922, 923]]}, 'the owners of a joint filing')
        self.assertEqual(set(d['points']['1067983']['315090']), {'A|D'})
        self.assertEqual(list(d['points']['797468']['315090']), ['|I:fn#1'], 'one footnoted holding, reworded from one report to the next: one key')
        self.assertEqual([x[2] for x in d['points']['797468']['315090']['|I:fn#1']], [152_713_846, 264_941_431], 'its last report each quarter')
        self.assertEqual(d['owners']['1494730'], ['Musk Elon', 'Director,Officer,TenPercentOwner', 'CEO'])

    def test_collect_and_build(self):
        r = I.collect(self.root, 5, page_html=PAGE_HTML, fetch=self.fetch)
        self.assertEqual(r, {'read': ['2025q3_form345.zip'], 'left': 0})
        st = I.build(self.root, self.hub)
        self.assertEqual(st['tickers'], 3)
        sp = json.loads((self.root / 'public' / 'i' / 'SPLT.json').read_text())
        self.assertEqual(sp['splits'], {'2020-09-30': 5}, 'the split found from the 13F side')
        got = lambda i: {sp['who'][w][1]: sh for w, sh, _ in sp['top'][i]}
        self.assertEqual(got(0), {'Founder Big': 100})
        self.assertEqual(got(1), {'Founder Big': 500, 'Mid Quarter': 250, 'Late Report': 70},
                         'reported before the quarter: ×5; inside it at the old price: ×5; late in it with no price: as reported')
        self.assertEqual(sp['top'][1][0][2], 500 * 220, 'at the new 13F price')
        doc = json.loads((self.root / 'public' / 'i' / 'TSLA.json').read_text())
        who = {w[0]: w for w in doc['who']}
        named = lambda i: [(who_[1], sh, usd) for who_, (w, sh, usd) in ((doc['who'][x[0]], x) for x in doc['top'][i])]
        # 2025-06-30: only the officer's report of that day
        self.assertEqual(named(0), [('Gone Person', 40, 12000)])
        # 2025-09-30: Musk's trust and award; Buffett's Berkshire block and Berkshire itself left (13F); the family block once
        self.assertEqual(named(1), [('Elon Musk', 507200, 507200 * 400), ('Rob Walton', 200010, 200010 * 400), ('Silver Lake Group, L.L.C.', 157000, 157000 * 400),
                                    ('Harald Kroeger', 90000, 90000 * 400), ('Two Same', 60000, 60000 * 400), ('One Same', 60000, 60000 * 400),
                                    ('Egon Durban', 5000, 5000 * 400), ('Mark Zuck', 50, 20000), ('Gone Person', 40, 16000)])
        self.assertEqual(doc['total'][1], [9, 1079300, 1079300 * 400])
        self.assertNotIn(922, who, 'a fund of a joint filing whose partner counts its shares')
        self.assertEqual(who[921][3], 'SL SPV-2, L.P. and Silver Lake Technology', "a holding through companies: named from the footnote's words")
        self.assertEqual(who[901][3], 'Daimler North America Corporation', "a company's shares: its name")
        self.assertEqual(who[502][3], 'Walton Enterprises, LLC', 'the family company')
        self.assertEqual(who[1494730][3], '', 'his trust: no company named')
        self.assertEqual(who[1494730][2], 'CEO · director · 10% owner')
        self.assertNotIn(315090, who, "Buffett's only holding is Berkshire's 13F block")
        self.assertNotIn(999, who, 'a 13F filer')
        self.assertNotIn(501, who, 'the family block went to the owner with the most')
        # two years and more after the last reports: nobody (none of them half a percent of the stock)
        self.assertIsNone(doc['total'][3])
        self.assertEqual(doc['top'][3], [])
        # a founder who seldom reports: half a percent of the stock or more counts for five years
        ls = {'|D': (['2020-01-10'], [['2020-01-10', '2020-01-12', 6_000_000, 0]])}
        self.assertEqual(I.holdings_at(ls, '2023-06-30', 730), {}, 'two years: gone')
        self.assertEqual(I.holdings_at(ls, '2023-06-30', 730, big=5_000_000), {'|D': (6_000_000, '2020-01-10', 0, '')}, 'a large holding: five years')
        self.assertEqual(I.holdings_at(ls, '2025-06-30', 730, big=5_000_000), {}, 'and not after')
        brk = json.loads((self.root / 'public' / 'i' / 'BRK-B.json').read_text())
        self.assertEqual(brk['top'][0], [[0, 15000, 15000 * 500]], 'class A as 1,500 class B, at the 13F price per class B share')
        self.assertEqual(brk['who'][0][1], 'Warren E Buffett')


if __name__ == '__main__':
    unittest.main()
