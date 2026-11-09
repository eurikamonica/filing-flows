"""The quarterly ETF holdings history: every public N-PORT quarter-end report since 2019 (etf.py nport_weights,
quarterly_history, history_by_symbol, collect_history), published per ETF as a compact block for the holdings videos
(actual_weights.quarterly_block, capture)."""
import datetime as dt
import gzip
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import actual_weights as A  # noqa: E402
import etf as E  # noqa: E402


def tsv(cols, rows):
    return '\t'.join(cols) + '\n' + ''.join('\t'.join(str(r.get(c, '')) for c in cols) + '\n' for r in rows)


def nport_zip(path, reports, registrants=None):
    """reports: [(accession, series, report date, filed, net assets, [(holding id, CUSIP, ISIN, ticker, %, category, payoff)])];
    registrants: {accession: CIK} (REGISTRANT.tsv; a unit investment trust's report names no series)"""
    sub, info, hold, ids, regs = [], [], [], [], []
    for acc, s, rd, fd, na, lines in reports:
        d = dt.date.fromisoformat(rd).strftime('%d-%b-%Y').upper()
        f = dt.date.fromisoformat(fd).strftime('%d-%b-%Y').upper()
        sub.append({'ACCESSION_NUMBER': acc, 'REPORT_DATE': d, 'FILING_DATE': f})
        info.append({'ACCESSION_NUMBER': acc, 'SERIES_ID': s, 'SERIES_NAME': s, 'NET_ASSETS': na})
        regs.append({'ACCESSION_NUMBER': acc, 'CIK': (registrants or {}).get(acc, ''), 'REGISTRANT_NAME': 'R'})
        for hid, cu, isin, tk, p, cat, pay in lines:
            hold.append({'ACCESSION_NUMBER': acc, 'HOLDING_ID': hid, 'ISSUER_CUSIP': cu, 'PERCENTAGE': p, 'CURRENCY_VALUE': p * na / 100,
                         'ASSET_CAT': cat, 'PAYOFF_PROFILE': pay})
            if isin or tk:
                ids.append({'HOLDING_ID': hid, 'IDENTIFIER_ISIN': isin, 'IDENTIFIER_TICKER': tk})
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('SUBMISSION.tsv', tsv(['ACCESSION_NUMBER', 'FILING_DATE', 'REPORT_DATE'], sub))
        z.writestr('FUND_REPORTED_INFO.tsv', tsv(['ACCESSION_NUMBER', 'SERIES_ID', 'SERIES_NAME', 'NET_ASSETS'], info))
        z.writestr('FUND_REPORTED_HOLDING.tsv', tsv(['ACCESSION_NUMBER', 'HOLDING_ID', 'ISSUER_CUSIP', 'PERCENTAGE', 'CURRENCY_VALUE', 'ASSET_CAT', 'PAYOFF_PROFILE'], hold))
        z.writestr('IDENTIFIERS.tsv', tsv(['HOLDING_ID', 'IDENTIFIER_ISIN', 'IDENTIFIER_TICKER'], ids))
        z.writestr('REGISTRANT.tsv', tsv(['ACCESSION_NUMBER', 'CIK', 'REGISTRANT_NAME'], regs))
    return path


REPORTS = [
    ('a1', 'S1', '2026-03-31', '2026-05-20', 1000, [('h1', '67066G104', '', 'NVDA', 8, 'EC', 'Long'),
                                                   ('h2', '037833100', '', '', 6, 'EC', 'Long'),        # CUSIP only (iShares, Vanguard)
                                                   ('h3', 'N/A', 'IE00B4BNMY34', '', 1, 'EC', 'Long'),  # placeholder CUSIP, an ISIN
                                                   ('h4', '912828XX1', '', '', 10, 'DBT', 'Long'),     # a bond: not equity
                                                   ('h5', '88160R101', '', 'TSLA', 2, 'EC', 'Short')]),
    ('a2', 'S1', '2026-03-31', '2026-06-02', 1000, [('h6', '67066G104', '', 'NVDA', 9, 'EC', 'Long'),  # the amendment replaces a1
                                                   ('h7', '037833100', '', '', 6, 'EC', 'Long'),
                                                   ('h8', '037833100', '', '', 0.5, 'EC', 'Long')]),   # two lines, one security
    ('b1', 'S2', '2026-02-28', '2026-04-20', 500, [('h9', '037833100', 'US0378331005', 'AAPL', 20, 'EC', 'Long'),
                                                  ('h10', '67066G104', '', 'NVDA', 30, 'EC', 'Long')]),
    ('c1', 'S3', '2026-03-31', '2026-05-01', 100, [('h11', '67066G104', '', 'NVDA', 50, 'EC', 'Long'),  # not an ETF series
                                                  ('h12', '037833100', '', 'AAPL', 50, 'EC', 'Long')]),
]


class Extract(unittest.TestCase):
    def test_every_report_compact_and_amendments_win(self):
        with tempfile.TemporaryDirectory() as d:
            out = E.nport_weights(nport_zip(Path(d) / 'n.zip', REPORTS), {'S1', 'S2'})
        K = out['keys']
        self.assertNotIn('S3', out['funds'])
        r = out['funds']['S1']['2026-03-31']
        self.assertEqual(r['acc'], 'a2')                                   # the later filing for the same date
        self.assertEqual([K[i] for i in r['k']], ['NVDA', '037833100'])   # largest first; no bond, no short, two lines added
        self.assertEqual(r['v'], [90000, 65000])                          # millionths of net assets
        self.assertEqual((r['n'], r['eq'], r['na']), (2, 0.155, 1000.0))
        b = out['funds']['S2']['2026-02-28']
        self.assertEqual([K[i] for i in b['k']], ['NVDA', 'AAPL'])
        self.assertEqual(out['ids'], {'037833100': 'AAPL'})               # S2 gives the ticker for S1's bare CUSIP

    def test_a_unit_investment_trust_is_kept_under_its_cik(self):
        """SPY, DIA, MDY and QQQ are unit investment trusts: one fund each, and their N-PORT reports name no series the ETF
        list knows (SERIES_ID blank, or one assigned later). Kept under the registrant's CIK (trust_ciks: the ETFs alone
        on their registrant), merged with any series-keyed quarters by history_by_symbol. A registrant that reports other
        series too (a family with one ETF and mutual funds) is no trust: its unknown series stay out, as does another
        registrant's."""
        reports = [('u1', '', '2026-03-31', '2026-05-28', 5e11, [('h1', '67066G104', '', 'NVDA', 7.5, 'EC', 'Long'), ('h2', '037833100', '', 'AAPL', 7, 'EC', 'Long')]),
                   ('u2', 'S000099', '2025-12-31', '2026-02-27', 4e11, [('h3', '67066G104', '', 'NVDA', 8, 'EC', 'Long'), ('h4', '037833100', '', 'AAPL', 6, 'EC', 'Long')]),
                   ('x1', '', '2026-03-31', '2026-05-01', 100, [('h5', '67066G104', '', 'NVDA', 50, 'EC', 'Long'), ('h6', '037833100', '', 'AAPL', 50, 'EC', 'Long')]),
                   ('f1', 'S000500', '2026-03-31', '2026-05-01', 100, [('h7', '67066G104', '', 'NVDA', 50, 'EC', 'Long'), ('h8', '037833100', '', 'AAPL', 50, 'EC', 'Long')]),
                   ('f2', 'S000501', '2026-03-31', '2026-05-01', 100, [('h9', '67066G104', '', 'NVDA', 40, 'EC', 'Long'), ('h10', '037833100', '', 'AAPL', 60, 'EC', 'Long')])]
        regs = {'u1': 884394, 'u2': 884394, 'x1': 12345, 'f1': 777, 'f2': 777}
        with tempfile.TemporaryDirectory() as d:
            out = E.nport_weights(nport_zip(Path(d) / 'n.zip', reports, regs), {'S1'}, {884394: 'cik884394', 777: 'cik777'})
            self.assertEqual(sorted(out['funds']), ['cik884394'])              # u2's series is not on the ETF list either: the CIK; 777 reports two series: no trust
            self.assertEqual(sorted(out['funds']['cik884394']), ['2025-12-31', '2026-03-31'])
            self.assertEqual(out['funds']['cik884394']['2026-03-31']['v'], [75000, 70000])
            # without the map (an older reading) the trust is dropped, as before
            self.assertEqual(E.nport_weights(nport_zip(Path(d) / 'n2.zip', reports, regs), {'S1'})['funds'], {})
            # history_by_symbol: a quarter under the series id and one under the CIK make one series for the symbol
            root = Path(d) / 'etf'
            K = ['NVDA', 'AAPL']
            set_file(root / 'cache' / 'nport_weights' / '2026q1_nport.json.gz', K, {
                'cik884394': {'2026-03-31': {'acc': 'u1', 'filed': '2026-05-28', 'na': 5e11, 'n': 2, 'eq': 0.145, 'k': [0, 1], 'v': [75000, 70000]}},
                'S000099': {'2025-12-31': {'acc': 'u2', 'filed': '2026-02-27', 'na': 4e11, 'n': 2, 'eq': 0.14, 'k': [0, 1], 'v': [80000, 60000]}},
                'cik777': {'2026-03-31': {'acc': 'f1', 'filed': '2026-05-01', 'na': 100, 'n': 2, 'eq': 1, 'k': [0, 1], 'v': [500000, 500000]}}})
            etfs = [{'symbol': 'SPY', 'series': 'S000099', 'act': '33', 'cik': 884394},        # the list's act: a trust filing 10-Ks
                    {'symbol': 'AAA', 'series': 'S000500', 'act': '40', 'cik': 777}, {'symbol': 'BBB', 'series': 'S000501', 'act': '40', 'cik': 777}]
            self.assertEqual(E.trust_ciks(etfs), {884394: 'cik884394'})        # AAA and BBB share a registrant: no trust
            cons = {'NVDA': {'sector': 'technology'}, 'AAPL': {'sector': 'technology'}}
            q = E.history_by_symbol(root, etfs, {}, {}, {}, {}, cons, {'NVDA', 'AAPL'}, lambda k: k if k in cons else None)[0]
            self.assertEqual([x['date'] for x in q['SPY']], ['2025-12-31', '2026-03-31'])
            self.assertEqual(dict(q['SPY'][1]['positions']), {'NVDA': 0.075, 'AAPL': 0.07})
            self.assertNotIn('AAA', q)                                        # no series-keyed quarter and no CIK key for them
        self.assertEqual(E.trust_ciks.__doc__.split()[0], '{registrant')

    def test_placeholder_cusips_fall_back_to_the_isin(self):
        with tempfile.TemporaryDirectory() as d:
            out = E.nport_weights(nport_zip(Path(d) / 'n.zip', REPORTS[:1]), {'S1'})
        r = out['funds']['S1']['2026-03-31']
        self.assertEqual([out['keys'][i] for i in r['k']], ['NVDA', '037833100', 'IE00B4BNMY34'])
        self.assertIsNone(E._ident('000000000'))
        self.assertIsNone(E._ident('N/A'))


def set_file(path, keys, funds):
    E.save_gz(path, {'source': path.name, 'keys': keys, 'funds': funds})
    return path


class History(unittest.TestCase):
    def test_same_names_every_quarter_and_full_sector_weights(self):
        sec = {'NVDA': 'technology', 'AAPL': 'technology', 'XOM': 'energy', 'JPM': 'financials'}
        classify = lambda k: (k if k.isalpha() else None, sec.get(k))
        with tempfile.TemporaryDirectory() as d:
            K = ['NVDA', 'AAPL', 'XOM', 'JPM', '999999999']
            q1 = set_file(Path(d) / '2025q4_nport.json.gz', K, {'S1': {'2025-12-31': {'acc': 'x1', 'filed': '2026-02-20', 'na': 1e9, 'n': 5, 'eq': 0.99,
                                                                                       'k': [2, 0, 1, 3, 4], 'v': [400000, 300000, 200000, 80000, 9000]}}})
            q2 = set_file(Path(d) / '2026q1_nport.json.gz', K, {'S1': {'2026-03-31': {'acc': 'x2', 'filed': '2026-05-20', 'na': 1e9, 'n': 4, 'eq': 0.98,
                                                                                       'k': [0, 1, 3, 2], 'v': [500000, 300000, 170000, 1000]},
                                                                        '2025-12-31': {'acc': 'x0', 'filed': '2026-01-05', 'na': 1e9, 'n': 1, 'eq': 0.5,
                                                                                       'k': [0], 'v': [500000]}}})   # an earlier filing of the same date
            h = E.quarterly_history([q1, q2], classify, top=2, keys=3)['S1']
        self.assertEqual([x['date'] for x in h], ['2025-12-31', '2026-03-31'])
        self.assertEqual(h[0]['accession'], 'x1')                          # the later filing of 2025-12-31 kept
        self.assertEqual(dict(h[0]['positions']), {'XOM': 0.4, 'NVDA': 0.3, 'AAPL': 0.2})   # names: top 2 of any quarter
        self.assertEqual(dict(h[1]['positions']), {'NVDA': 0.5, 'AAPL': 0.3, 'XOM': 0.001})  # XOM's small weight, exact
        self.assertEqual(h[0]['sector_weights'], {'energy': 0.4, 'technology': 0.5, 'financials': 0.08, 'other': 0.01})
        self.assertAlmostEqual(sum(h[1]['sector_weights'].values()), 0.98)  # every line, plus lines too small to keep

    def test_classifier_names_and_sectors(self):
        etfs = [{'symbol': 'IVV', 'series': 'S1'}, {'symbol': 'XLF', 'series': 'S9'}]
        holds = {'S9': {'weights': [['316773100', 0.02, 1], ['JPM', 0.1, 1]]},                 # the financials sector ETF
                 'S8': {'top': [['LINDE PLC', 'LINDE PLC', 'N/A', 'IE00B4BNMY34', None, 1, 0.01, 'EC', 'CORP', 'IE', 'Long']]}}
        cusip_t = {'02079K305': 'GOOGL', '02079K107': 'GOOG', '316773100': 'FITB'}
        t_cusip = {t: c for c, t in cusip_t.items()}
        cons = {'GOOGL': {'sector': 'technology'}, 'JPM': {'sector': 'financials'}}
        uit = {'SPY': {'rows': [['LINDE PLC', 'LIN', 'G54950103', 0.004, '-']]}, 'MDY': {'rows': [['Okta', 'OKTA', '679295105', 0.01, 'Information Technology']]}}

        def key_ticker(k):
            k = E.norm_t(k)
            if k in cons:
                return k
            if k in cusip_t:
                return cusip_t[k]
            return k if k.isalpha() and len(k) <= 6 else None
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            K = ['02079K107', '316773100', 'G54950103', 'IE00B4BNMY34', 'OKTA']
            set_file(root / 'cache' / 'nport_weights' / '2026q1_nport.json.gz', K, {
                'S1': {'2026-03-31': {'acc': 'x', 'filed': '2026-05-01', 'na': 1, 'n': 5, 'eq': 0.5, 'k': [0, 1, 2, 3, 4], 'v': [200000, 100000, 100000, 50000, 50000]}}})
            E.save_gz(root / 'cache' / 'nport_weights' / '2026q1_nport.ids.json.gz', {'ids': {'IE00B4BNMY34': 'LIN'}})
            cl = E.make_classifier(root, etfs, holds, uit, cusip_t, t_cusip, cons, {'LIN', 'GOOG', 'FITB', 'OKTA'}, key_ticker, {'LIN': 'Linde plc'})
            q, sector_of, labels = E.history_by_symbol(root, etfs, holds, uit, cusip_t, t_cusip, cons, {'LIN', 'GOOG', 'FITB', 'OKTA'}, key_ticker, classifier=cl)
        snap = q['IVV'][0]
        self.assertEqual(dict(snap['positions']), {'GOOG': 0.2, 'FITB': 0.1, 'LIN': 0.15, 'OKTA': 0.05})   # the ISIN via another fund
        self.assertEqual(sector_of('GOOG'), 'technology')        # the issuer's other share class (02079K…)
        self.assertEqual(sector_of('FITB'), 'financials')        # held by the financials sector ETF
        self.assertEqual(sector_of('OKTA'), 'technology')        # GICS of the MidCap sponsor file
        self.assertEqual(snap['sector_weights'], {'technology': 0.25, 'financials': 0.1, 'other': 0.15})  # LIN: no sector known
        self.assertEqual((snap['partial'], snap['date_basis'], snap['source']), (True, 'reported', 'SEC N-PORT (quarter-end)'))
        self.assertEqual(labels, {})                             # no foreign security without a US listing here

    def test_foreign_securities(self):
        """A foreign line: its local ticker is no US company's ('MC' is LVMH in Paris, Moelis here; 'SAN' Sanofi's and
        Santander's); the same company's US listing by its name (Sanofi → SNY), else a '~' key with its name; the
        sector from the global sector funds (an ISIN here, its CINS there), else a word of its name; 'N.A' tickers never
        a key; a fund's ETF lines are ETFs."""
        lvmh, sanofi, schn, hdfc, tte = 'FR0000121014', 'FR0000120578', 'FR0000121972', 'INE040A01034', 'FR0000120271'
        row = lambda name, cusip, isin, tick, w: [name, name, cusip, isin, tick, 1, w, 'EC', 'CORP', isin[:2], 'Long']
        etfs = [{'symbol': s_, 'series': s_} for s_ in ('EWQ', 'RXI', 'EXI', 'VXUS', 'AOR', 'IXJ')]
        holds = {
            'EWQ': {'top': [row('TOTALENERGIES SE', 'N/A', tte, 'N.A', 0.08), row('SCHNEIDER ELECTRIC SE', 'N/A', schn, 'N.A', 0.07),
                            row('LVMH MOET HENNESSY LOUIS VUITTON SE', 'N/A', lvmh, 'MC', 0.06), row('SANOFI SA', 'N/A', sanofi, 'N.A', 0.05)],
                    'weights': [['N.A', 0.08, 1], ['N.A', 0.07, 1], ['MC', 0.06, 1], ['N.A', 0.05, 1], ['N.A', 0.01, 1]]},
            'RXI': {'top': [row('LVMH Moet Hennessy Louis Vuitton SE', 'N/A', lvmh, 'N.A', 0.05)], 'weights': [['N.A', 0.05, 1]]},
            'EXI': {'top': [row('Schneider Electric S.E.', 'N/A', schn, 'N.A', 0.04)], 'weights': [['N.A', 0.04, 1]]},
            'IXJ': {'top': [row('Sanofi', 'N/A', sanofi, 'N.A', 0.03)], 'weights': [['N.A', 0.03, 1]]},
            'VXUS': {'top': [row('Schneider Electric SE', 'F86921107', schn, None, 0.01)], 'weights': [['F86921107', 0.01, 1]]}}
        cons = {'MC': {'sector': 'financials', 'name': 'Moelis & Co'}, 'TTE': {'sector': 'energy', 'name': 'TotalEnergies SE'}}
        us_names = {'MC': 'Moelis & Co', 'SAN': 'Banco Santander, S.A.', 'SNY': 'Sanofi', 'TTE': 'TotalEnergies SE', 'AGG': 'iShares Core US Aggregate'}
        etfs.append({'symbol': 'AGG', 'series': 'X'})
        key_ticker = lambda k: E.norm_t(k) if E.norm_t(k) in cons else (E.norm_t(k) if k.isalpha() and len(k) <= 5 else None)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'cache' / 'nport_weights').mkdir(parents=True)
            E.save_gz(root / 'cache' / 'nport_weights' / '2026q1_nport.ids.json.gz', {'ids': {lvmh: 'MC', sanofi: 'SAN', tte: 'TTE'}})
            ticker, classify, labels = E.make_classifier(root, etfs, holds, {}, {}, {}, cons, set(us_names), key_ticker, us_names, repair=True)
        f_lvmh, f_schn = E.foreign_key(lvmh), E.foreign_key(schn)
        self.assertEqual(classify(lvmh), (f_lvmh, 'consumer-disc'))          # not Moelis: its own key, RXI's sector
        self.assertEqual(labels[f_lvmh], ['LVMH Moet Hennessy Louis Vuitton', 'consumer-disc'])
        self.assertEqual(classify(sanofi), ('SNY', 'health'))                # not Santander: Sanofi's US listing, IXJ's sector
        self.assertEqual(classify(tte), ('TTE', 'energy'))                   # the local ticker is the US one: the same company
        self.assertEqual(classify('F86921107'), (f_schn, 'industrials'))     # a CINS: as the ISIN of the same line
        self.assertEqual(classify('MC'), ('MC', 'financials'))               # a US fund's MC is Moelis still
        self.assertEqual(classify('AGG'), ('AGG', 'etf'))
        self.assertTrue(E.is_foreign(lvmh) and E.is_foreign('F86921107') and not E.is_foreign('037833100') and not E.is_foreign('US0378331005'))
        self.assertEqual(E.norm_name('ASML HOLDING NV COMMON STOCK EUR 0.09'), 'asml')
        self.assertEqual(E.norm_name('Agnico Eagle Mines Ltd./Mines Agnico Eagle Ltee'), 'agnico eagle mines')
        self.assertEqual(E.norm_name('TORONTO DOMINION BANK (THE)'), 'toronto dominion bank')
        self.assertEqual(E.short_name("L'AIR LIQUIDE SA"), "L'Air Liquide")
        # the latest holdings: placeholders never a key; a foreign line's local ticker gives way to its ISIN; the flag
        self.assertEqual([w[0] for w in holds['EWQ']['weights']], [tte, schn, lvmh, sanofi])   # the fifth 'N.A' line: dropped
        self.assertEqual([x[11] for x in holds['EWQ']['top']], [0, 0, 0, 0])
        self.assertEqual(holds['VXUS']['weights'][0][0], schn)                  # the ISIN of the line rather than its CINS
        # a word of the name when no sector fund holds it
        holds2 = {'INDA': {'top': [row('HDFC BANK LTD', 'N/A', hdfc, 'N.A', 0.06)], 'weights': [['N.A', 0.06, 1]]}}
        with tempfile.TemporaryDirectory() as d:
            t2, c2, l2 = E.make_classifier(Path(d), [], holds2, {}, {}, {}, {}, set(), key_ticker, {}, repair=True)
        self.assertEqual(c2(hdfc), (E.foreign_key(hdfc), 'financials'))
        self.assertEqual(l2[E.foreign_key(hdfc)][0], 'HDFC Bank')


class Publish(unittest.TestCase):
    def snaps(self):
        return [{'date': '2025-12-31', 'accession': 'x1', 'positions': [['NVDA', 0.3], ['AAPL', 0.2]], 'sector_weights': {'technology': 0.5, 'other': 0.49},
                 'equity_weight_covered': 0.99, 'n': 500, 'net_assets': 1e9, 'partial': True},
                {'date': '2026-03-31', 'accession': 'x2', 'positions': [['NVDA', 0.35]], 'sector_weights': {'technology': 0.4, 'energy': 0.1},
                 'equity_weight_covered': 0.98, 'n': 498, 'net_assets': 1.1e9, 'partial': True}]

    def test_block(self):
        b = A.quarterly_block(self.snaps())
        self.assertEqual(b['dates'], ['2025-12-31', '2026-03-31'])
        self.assertEqual(b['names'], ['NVDA', 'AAPL'])           # by their largest weight
        self.assertEqual(b['w'], [[30000, 20000], [35000, 0]])   # hundred-thousandths; not held = 0
        self.assertEqual(b['sectors'], ['technology', 'energy', 'other'])
        self.assertEqual(b['sw'], [[50000, 0, 49000], [40000, 10000, 0]])
        self.assertEqual((b['acc'], b['n'], b['unit']), (['x1', 'x2'], [500, 498], 1e-5))

    def test_foreign_names_and_broken_snapshots(self):
        snaps = [{'date': '2025-12-31', 'accession': 'x1', 'positions': [['~ABCDEF', 0.3], ['TTE', 0.2]], 'sector_weights': {'industrials': 0.3, 'energy': 0.2},
                  'equity_weight_covered': 0.99, 'n': 50, 'net_assets': 1e9, 'partial': True},
                 {'date': '2026-03-31', 'accession': 'x2', 'positions': [['~ABCDEF', 0.35], ['TTE', 0.1]], 'sector_weights': {'industrials': 0.35},
                  'equity_weight_covered': 0.98, 'n': 50, 'net_assets': 1e9, 'partial': True}]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'etf'
            pub = root / 'public'
            (pub / 'e').mkdir(parents=True)
            (root / 'cache' / 'actual_weights').mkdir(parents=True)
            # a snapshot kept before: every foreign line under one 'N-A' — not a portfolio, dropped
            (root / 'cache' / 'actual_weights' / 'EWQ.json').write_text(json.dumps({'symbol': 'EWQ', 'snapshots': [
                {'date': '2026-01-31', 'positions': [['N-A', 0.9], ['TTE', 0.08]]},
                {'date': '2025-11-28', 'positions': [['TTE', 0.08], ['F86921107', 0.07]]}]}))
            (pub / 'e' / 'EWQ.json').write_text(json.dumps({'name': 'EWQ', 'holdings': {'date': '2026-04-30', 'acc': 'a9'},
                                                            'weights': [['FR0000121972', 0.08, 1], ['TTE', 0.07, 1], ['N.A', 0.01, 1]]}))
            key_of = {'FR0000121972': '~ABCDEF', 'F86921107': '~ABCDEF', 'TTE': 'TTE'}.get
            labels = {'~ABCDEF': ['Schneider Electric', 'industrials']}
            sector_of = lambda t: {'TTE': 'energy'}.get(t) or (labels.get(t) or [None, None])[1]
            A.capture(root, pub, [{'symbol': 'EWQ', 'aum': 9}], quarterly={'EWQ': snaps}, sector_of=sector_of, key_of=key_of, labels=labels)
            out = json.loads((pub / 'weights' / 'EWQ.json').read_text())
        self.assertEqual([x['date'] for x in out['snapshots']], ['2025-11-28', '2026-04-30'])     # the 'N-A' one dropped
        self.assertEqual(out['snapshots'][0]['positions'], [['TTE', 0.08], ['~ABCDEF', 0.07]])   # the CINS keyed again
        self.assertEqual(out['snapshots'][1]['positions'], [['~ABCDEF', 0.08], ['TTE', 0.07]])
        self.assertEqual(out['snapshots'][1]['sector_weights'], {'industrials': 0.08, 'energy': 0.07})
        self.assertEqual(out['quarterly']['names'], ['~ABCDEF', 'TTE'])
        self.assertEqual((out['labels'], out['secs']), ({'~ABCDEF': 'Schneider Electric'}, {'~ABCDEF': 'industrials'}))

    def test_capture_publishes_every_etf_with_two_quarters(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'etf'
            pub = root / 'public'
            (pub / 'e').mkdir(parents=True)
            (pub / 'e' / 'SPY.json').write_text(json.dumps({'name': 'SPY', 'holdings': {'date': '2026-10-30', 'date_basis': 'observed', 'source': 'sponsor holdings file',
                                                                                          'sector_map': {'NVDA': '-'}},
                                                             'weights': [['NVDA', 0.08, 1], ['XOM', 0.02, 1]]}))
            q = {'IVV': self.snaps(), 'TINY': self.snaps()[:1]}
            sector_of = {'NVDA': 'technology', 'XOM': 'energy'}.get
            st = A.capture(root, pub, [{'symbol': 'SPY', 'aum': 9}, {'symbol': 'IVV', 'aum': 8}, {'symbol': 'TINY', 'aum': 1}], quarterly=q, sector_of=sector_of)
            self.assertEqual((st['published'], st['with_quarterly_history']), (2, 1))
            ivv = json.loads((pub / 'weights' / 'IVV.json').read_text())
            self.assertEqual(ivv['snapshots'], [])
            self.assertEqual(ivv['quarterly']['dates'], ['2025-12-31', '2026-03-31'])
            self.assertFalse((pub / 'weights' / 'TINY.json').exists())   # one report: the ETF page's latest holdings already show it
            spy = json.loads((pub / 'weights' / 'SPY.json').read_text())
            self.assertEqual(spy['snapshots'][0]['sector_weights'], {'technology': 0.08, 'energy': 0.02})
            self.assertNotIn('quarterly', spy)


class Collect(unittest.TestCase):
    def test_backfill_newest_first_a_few_a_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'etf'
            src = nport_zip(Path(d) / 'src.zip', REPORTS)
            calls = []

            def fake_download(url, dest, ua=None):
                calls.append(Path(url).name)
                shutil.copy(src, dest)
                return dest
            old_dl, old_series = E.download, E.etf_series
            E.download, E.etf_series = fake_download, lambda r: {'S1', 'S2'}
            try:
                links = {'nport': [f'https://www.sec.gov/files/dera/data/form-n-port-data-sets/{q}_nport.zip' for q in ('2019q3', '2025q4', '2026q2', '2026q1')]}
                tmp = Path(d) / 'tmp'
                tmp.mkdir()
                self.assertEqual([x[0] for x in E.collect_history(root, links, tmp, max_new=2)], ['2026q2_nport.zip', '2026q1_nport.zip'])
                self.assertEqual([x[0] for x in E.collect_history(root, links, tmp, max_new=2)], ['2025q4_nport.zip'])   # 2019 Q3: before the data sets
                self.assertEqual(E.collect_history(root, links, tmp, max_new=2), [])
                st = json.loads((root / 'state.json').read_text())
                st['nport_weights']['2026q1_nport.zip'].pop('v')                   # read by an older version of the reader: read again
                (root / 'state.json').write_text(json.dumps(st))
                self.assertEqual([x[0] for x in E.collect_history(root, links, tmp, max_new=2)], ['2026q1_nport.zip'])
            finally:
                E.download, E.etf_series = old_dl, old_series
            self.assertEqual(calls, ['2026q2_nport.zip', '2026q1_nport.zip', '2025q4_nport.zip', '2026q1_nport.zip'])
            st = json.loads((root / 'state.json').read_text())['nport_weights']
            self.assertEqual((st['2026q2_nport.zip']['series'], st['2026q2_nport.zip']['v']), (2, E.HIST_VERSION))
            data = E.load_gz(E.hist_path(root, '2026q2_nport.zip'))
            self.assertEqual(sorted(data['funds']), ['S1', 'S2'])
            self.assertEqual(E.load_gz(E.hist_path(root, '2026q2_nport.zip', ids=True))['ids'], {'037833100': 'AAPL'})
            self.assertEqual(list(tmp.iterdir()), [])                     # each download deleted after reading


if __name__ == '__main__':
    unittest.main()
