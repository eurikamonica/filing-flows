"""smart.py: trades from 13F changes, insider data sets and active-ETF portfolios; each trade's score, each actor's
weighted accuracy and skill weight, the stock scores and the published files."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np  # noqa: F401
    import smart as S
except ImportError:                                        # numpy is installed in CI; skip elsewhere
    S = None


def tsv(cols, rows):
    return '\t'.join(cols) + '\n' + ''.join('\t'.join(str(r.get(c, '')) for c in cols) + '\n' for r in rows)


def gz(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(obj, f)


def series(start, n, f):
    """n weekdays of closes from start: f(i) → close."""
    out, d, i = [], dt.date.fromisoformat(start), 0
    while len(out) < n:
        if d.weekday() < 5:
            out.append([d.isoformat(), float(f(i))])
            i += 1
        d += dt.timedelta(days=1)
    return out


@unittest.skipIf(S is None, 'numpy not installed')
class Parsing(unittest.TestCase):
    def test_form345(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'q.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('SUBMISSION.tsv', tsv(['ACCESSION_NUMBER', 'FILING_DATE', 'DOCUMENT_TYPE', 'ISSUERCIK', 'ISSUERNAME', 'ISSUERTRADINGSYMBOL'], [
                    {'ACCESSION_NUMBER': 'a1', 'FILING_DATE': '03-SEP-2026', 'DOCUMENT_TYPE': '4', 'ISSUERCIK': '0001045810', 'ISSUERNAME': 'NVIDIA CORP', 'ISSUERTRADINGSYMBOL': 'NVDA'},
                    {'ACCESSION_NUMBER': 'a2', 'FILING_DATE': '04-SEP-2026', 'DOCUMENT_TYPE': '4/A', 'ISSUERCIK': '1', 'ISSUERNAME': 'X', 'ISSUERTRADINGSYMBOL': 'XX'},
                    {'ACCESSION_NUMBER': 'a3', 'FILING_DATE': '05-SEP-2026', 'DOCUMENT_TYPE': '4', 'ISSUERCIK': '1067983', 'ISSUERNAME': 'BERKSHIRE', 'ISSUERTRADINGSYMBOL': 'brk.b'},
                    {'ACCESSION_NUMBER': 'a4', 'FILING_DATE': '05-SEP-2026', 'DOCUMENT_TYPE': '4', 'ISSUERCIK': '2', 'ISSUERNAME': 'NO TICKER', 'ISSUERTRADINGSYMBOL': 'NONE'}]))
                z.writestr('REPORTINGOWNER.tsv', tsv(['ACCESSION_NUMBER', 'RPTOWNERCIK', 'RPTOWNERNAME', 'RPTOWNER_RELATIONSHIP', 'RPTOWNER_TITLE'], [
                    {'ACCESSION_NUMBER': 'a1', 'RPTOWNERCIK': '0001197647', 'RPTOWNERNAME': 'HUANG JEN HSUN', 'RPTOWNER_RELATIONSHIP': 'Director,Officer,TenPercentOwner', 'RPTOWNER_TITLE': 'President and CEO'},
                    {'ACCESSION_NUMBER': 'a1', 'RPTOWNERCIK': '9', 'RPTOWNERNAME': 'A TRUST', 'RPTOWNER_RELATIONSHIP': 'Other'},
                    {'ACCESSION_NUMBER': 'a3', 'RPTOWNERCIK': '8', 'RPTOWNERNAME': 'Smith Jane', 'RPTOWNER_RELATIONSHIP': 'Director'},
                    {'ACCESSION_NUMBER': 'a4', 'RPTOWNERCIK': '7', 'RPTOWNERNAME': 'Doe John', 'RPTOWNER_RELATIONSHIP': 'Officer', 'RPTOWNER_TITLE': 'CFO'}]))
                z.writestr('NONDERIV_TRANS.tsv', tsv(['ACCESSION_NUMBER', 'TRANS_DATE', 'TRANS_CODE', 'TRANS_SHARES', 'TRANS_PRICEPERSHARE'], [
                    {'ACCESSION_NUMBER': 'a1', 'TRANS_DATE': '01-SEP-2026', 'TRANS_CODE': 'S', 'TRANS_SHARES': '1000', 'TRANS_PRICEPERSHARE': '180'},
                    {'ACCESSION_NUMBER': 'a1', 'TRANS_DATE': '01-SEP-2026', 'TRANS_CODE': 'S', 'TRANS_SHARES': '500', 'TRANS_PRICEPERSHARE': '181'},
                    {'ACCESSION_NUMBER': 'a1', 'TRANS_DATE': '01-SEP-2026', 'TRANS_CODE': 'M', 'TRANS_SHARES': '9000', 'TRANS_PRICEPERSHARE': '1'},
                    {'ACCESSION_NUMBER': 'a2', 'TRANS_DATE': '01-SEP-2026', 'TRANS_CODE': 'P', 'TRANS_SHARES': '10', 'TRANS_PRICEPERSHARE': '500'},
                    {'ACCESSION_NUMBER': 'a3', 'TRANS_DATE': '02-SEP-2026', 'TRANS_CODE': 'P', 'TRANS_SHARES': '100', 'TRANS_PRICEPERSHARE': '480'},
                    {'ACCESSION_NUMBER': 'a3', 'TRANS_DATE': '02-SEP-2026', 'TRANS_CODE': 'P', 'TRANS_SHARES': '1', 'TRANS_PRICEPERSHARE': '0'},
                    {'ACCESSION_NUMBER': 'a4', 'TRANS_DATE': '02-SEP-2026', 'TRANS_CODE': 'P', 'TRANS_SHARES': '100', 'TRANS_PRICEPERSHARE': '20'}]))
            rows = S.process_form345(p)
        self.assertEqual(len(rows), 2)                     # the 4/A, the option exercise and the line without a ticker are left out
        nv = next(r for r in rows if r[3] == 'NVDA')
        self.assertEqual(nv[:3], ['1197647', 'HUANG JEN HSUN', 'CEO'])                 # the first owner listed; title → CEO
        self.assertEqual((nv[6], nv[7], nv[8], nv[9], nv[10]), ('2026-09-01', '2026-09-03', -1, 1500.0, 270500))   # two lines, one sale
        bk = next(r for r in rows if r[3] == 'BRK-B')
        self.assertEqual((bk[2], bk[8], bk[10]), ('Director', 1, 48000))

    def test_links_and_dates(self):
        html = ('<a href="/files/structureddata/data/insider-transactions-data-sets/2025q4_form345.zip">x</a>'
                '<a href="https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip">y</a>')
        links = S.ins_links(html)
        self.assertEqual(list(links), ['2025q4', '2026q3'])
        self.assertTrue(links['2025q4'].startswith('https://www.sec.gov/files/'))
        self.assertEqual(S.dmy('05-SEP-2026'), '2026-09-05')
        self.assertEqual(S.quarter_end('2026q3'), '2026-09-30')
        self.assertEqual(S.quarter_end('2025q4'), '2025-12-31')
        self.assertEqual(S.tick('brk.b, brk.a'), 'BRK-B')
        self.assertEqual(S.bucket('g:NANCY PELOSI'), '55')                             # docs/smart.js computes the same

    def test_f13_changes(self):
        def ch(cusip, sh, pr, v, pv, status):
            return {'cusip': cusip, 'put_call': 'NONE', 'share_type': 'SH', 'shares': sh, 'prior_shares': pr, 'value_usd': v, 'prior_value_usd': pv, 'status': status}
        m = {'snapshots': [
            {'period': '2026-06-30', 'filed': '2026-08-14', 'complete': True, 'baseline_period': '2026-03-31', 'total_usd': 1_000_000, 'changes': [
                ch('AAA', 200, 100, 20_000, 10_000, 'INCREASE'),          # +100 shares at $100: 1% of the portfolio
                ch('BBB', 0, 50, 0, 5_000, 'EXIT'),                       # an exit at the prior price: −0.5%
                ch('CCC', 1000, 500, 50_000, 49_000, 'INCREASE'),         # 2-for-1 split, value unchanged: no trade
                ch('DDD', 101, 100, 10_100, 10_000, 'INCREASE'),          # a 1% top-up: too small
                ch('EEE', 10, 0, 500, 0, 'NEW'),                          # 0.05% of the portfolio: too small
                {**ch('FFF', 100, 0, 9000, 0, 'NEW'), 'put_call': 'CALL'}]},
            {'period': '2026-03-31', 'filed': '2026-05-15', 'complete': True, 'baseline_period': '2025-09-30', 'total_usd': 1e6,
             'changes': [ch('ZZZ', 100, 0, 50_000, 0, 'NEW')]}]}       # a two-quarter gap: not one decision
        ev = S.f13_events_of(m)
        self.assertEqual(ev, [['AAA', '2026-06-30', '2026-08-14', 0.01, '', 100, 10000], ['BBB', '2026-06-30', '2026-08-14', -0.005, 'x', -50, -5000]])
        self.assertEqual(S.f13_events_of(m, skip_cusips=frozenset({'AAA'}))[0][0], 'BBB')


class FakeUniverse:
    def __init__(self, cusips=None, known=()):
        self.cusip_ticker = cusips or {}
        self.cusip_type = {}
        self._known = set(known)

    def known(self, t):
        return t in self._known

    def name(self, t):
        return t + ' Inc'


@unittest.skipIf(S is None, 'numpy not installed')
class Scoring(unittest.TestCase):
    def test_etf_trades_net_of_flows(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pos0 = [['AAA', 'c1', 100, 1000], ['BBB', 'c2', 100, 1000], ['CCC', 'c3', 100, 1000], ['DDD', 'c4', 100, 1000], ['EEE', 'c5', 100, 1000], ['FFF', 'c6', 100, 1000]]
            pos1 = [['AAA', 'c1', 110, 1100], ['BBB', 'c2', 110, 1100], ['CCC', 'c3', 110, 1100], ['DDD', 'c4', 110, 1100], ['EEE', 'c5', 220, 2200], ['', 'c7', 50, 500]]
            gz(root / 'cache' / 'nport_active' / '2026q1_nport.json.gz', {'funds': {'S1': {'name': 'Fund', 'date': '2026-03-31', 'filed': '2026-05-29', 'na': 6000, 'pos': pos0}}})
            gz(root / 'cache' / 'nport_active' / '2026q2_nport.json.gz', {'funds': {'S1': {'name': 'Fund', 'date': '2026-06-30', 'filed': '2026-08-28', 'na': 7300, 'pos': pos1}}})
            (root / 'public').mkdir()
            (root / 'public' / 'index.json').write_text(json.dumps({'fields': ['symbol', 'series'], 'rows': [['ARKK', 'S1']]}))
            E = S.Events()
            n = S.add_etf_events(E, root, FakeUniverse({'c7': 'GGG'}, known={'AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF'}))
            E.freeze()
        got = {E.tickers[E.t[i]]: (int(E.d[i]), E.ref[i]) for i in range(E.n)}
        self.assertEqual(n, 3)                             # the 10% inflow scaled every line: only real trades remain
        self.assertEqual(got, {'EEE': (1, ''), 'FFF': (-1, 'x'), 'GGG': (1, 'n')})
        self.assertEqual(E.actors[0]['name'], 'ARKK · Fund')

    def _two(self, b_rounds):
        P = S.Prices.__new__(S.Prices)
        P.series = {}
        days = series('2024-01-01', 700, lambda i: 100)
        ords = np.array([S.ordinal(r[0]) for r in days], dtype=np.int32)
        P.series['SPY'] = (ords, np.array([100.0 + i * 0.01 for i in range(700)]), '')
        P.series['UP'] = (ords, np.array([100.0 * (1.001 ** i) for i in range(700)]), '')
        P.series['DOWN'] = (ords, np.array([100.0 * (0.999 ** i) for i in range(700)]), '')
        P.series['NEW'] = (ords, np.array([100.0] * 700), '')
        E = S.Events()
        a = E.actor('g:A', 'A', 'gov')
        b = E.actor('g:B', 'B', 'gov')
        for k in range(12):
            day = days[20 + k * 30][0]
            E.add(a, 'UP', day, None, 1, 10000)
            E.add(a, 'DOWN', day, None, -1, 10000)
            if k < b_rounds:
                E.add(b, 'UP', day, None, -1, 10000)
                E.add(b, 'DOWN', day, None, 1, 10000)
        today = ords[-1]
        E.add(a, 'NEW', S.iso(today - 10), None, 1, 10000)
        E.add(b, 'NEW', S.iso(today - 10), None, 1, 10000)
        E.freeze()
        O = S.outcomes(E, P, P.get('SPY'), today)
        sk = S.skills(E, O, O['end'] <= today, u=0.5)
        return P, E, O, sk, a, b, today

    def test_skill_votes_and_backtest(self):
        """A always buys winners and sells losers, B the opposite. With records of the same length the group's rate is a
        coin flip, A's weight is positive and B's negative; when B has a short record, A's vote decides a stock both buy."""
        P, E, O, sk, a, b, today = self._two(12)
        self.assertTrue(np.isnan(O['ex'][-1]))             # the newest trades are waiting for their 63 days
        self.assertGreater(O['ex'][0], 0)                  # UP beat SPY
        self.assertTrue((sk['L_side'][a] > 0.5).all() and (sk['L_side'][b] < -0.5).all())
        self.assertAlmostEqual(sk['all']['acc'][a], 1.0)
        self.assertAlmostEqual(sk['all']['acc'][b], 0.0)
        P, E, O, sk, a, b, today = self._two(3)
        self.assertLess(sk['L_side'][b].max(), sk['L_side'][a].min() - 1)
        V = S.votes(E, today, sk['L_side'])
        ti = E.tidx['NEW']
        self.assertGreater(V['all']['S'][ti], 0)
        self.assertEqual(V['all']['raw'][ti], 100)          # everyone alike: two buyers
        summary, hist, calib, u = S.backtest(E, O, P, P.get('SPY'), today)
        self.assertIn('dates', summary)
        self.assertTrue(0.3 <= u <= 0.7)

    def test_shrinkage_toward_the_group(self):
        """One right trade does not make a record: the posterior stays near the group's rate."""
        P = S.Prices.__new__(S.Prices)
        days = series('2024-01-01', 300, lambda i: 100)
        ords = np.array([S.ordinal(r[0]) for r in days], dtype=np.int32)
        P.series = {'SPY': (ords, np.full(300, 100.0), ''), 'UP': (ords, np.array([100 * 1.002 ** i for i in range(300)]), '')}
        E = S.Events()
        a = E.actor('i:X', 'X', 'ins')
        E.add(a, 'UP', days[10][0], None, 1, 50000)
        E.freeze()
        O = S.outcomes(E, P, P.get('SPY'), ords[-1])
        sk = S.skills(E, O, O['end'] <= ords[-1], u=0.5)
        self.assertEqual(sk['all']['acc'][a], 1.0)
        self.assertLess(sk['side']['p'][a * 2], 0.75)      # 1 trade against k = 8 at the group's rate


    def test_daily_sales_are_one_decision(self):
        """An insider selling a falling stock every day for a month has one decision on record, not twenty."""
        P = S.Prices.__new__(S.Prices)
        days = series('2024-01-01', 300, lambda i: 100)
        ords = np.array([S.ordinal(r[0]) for r in days], dtype=np.int32)
        P.series = {'SPY': (ords, np.full(300, 100.0), ''), 'DOWN': (ords, np.array([100 * 0.998 ** i for i in range(300)]), '')}
        E = S.Events()
        a = E.actor('i:X', 'X', 'ins')
        for k in range(20):
            E.add(a, 'DOWN', days[10 + k][0], None, -1, 50000)
        E.freeze()
        O = S.outcomes(E, P, P.get('SPY'), ords[-1])
        sk = S.skills(E, O, O['end'] <= ords[-1], u=0.5)
        self.assertEqual((int(sk['all']['n'][a]), int(sk['all']['decisions'][a])), (20, 1))
        self.assertAlmostEqual(sk['all']['neff'][a], 1.0)
        self.assertLess(sk['side']['p'][a * 2 + 1], 0.75)  # one right decision, shrunk toward the group


    def test_combined_periods(self):
        P = {p['key']: p for p in S.combined_periods(S.ordinal('2026-10-19'))}
        self.assertTrue(P['prev']['label'].startswith("Q3 2026 — this quarter's filings (Jul–Sep)"))
        self.assertEqual((P['prev']['start'], P['prev']['end']), ('2026-07-01', '2026-09-30'))
        self.assertIn('Nov 14', P['prev']['note'])                # the 45-day 13F deadline
        self.assertEqual((P['prev2']['label'], P['both']['start'], P['both']['end']), ('Q2 2026 (Apr–Jun)', '2026-04-01', '2026-09-30'))
        self.assertEqual((P['qtd']['label'], P['qtd']['start']), ('Q4 2026 to date (Oct 1 – Oct 19)', '2026-10-01'))
        P = {p['key']: p for p in S.combined_periods(S.ordinal('2027-02-03'))}
        self.assertTrue(P['prev']['label'].startswith('Q4 2026'))  # across the year end
        self.assertEqual(P['prev2']['start'], '2026-07-01')


    def test_insider_tickers_and_prices(self):
        ciks = ({'1045810': ['NVDA'], '1067983': ['BRK-B', 'BRK-A']}, {'NVDA': '1045810', 'BRK-B': '1067983', 'BRK-A': '1067983'})
        self.assertEqual(S.issuer_ticker('0001067983', 'BRK-A', ciks), 'BRK-A')      # the filer's symbol, when SEC lists it for the issuer
        self.assertEqual(S.issuer_ticker('1067983', 'BRKB', ciks), 'BRK-B')          # else SEC's first ticker for the issuer
        self.assertEqual(S.issuer_ticker('999', 'NVDA', ciks), '')                   # a symbol that belongs to another company
        self.assertEqual(S.issuer_ticker('999', 'ZZZ', ciks), 'ZZZ')                 # an issuer SEC does not list (OTC, delisted)
        P = S.Prices.__new__(S.Prices)
        days = series('2026-07-01', 30, lambda i: 100)
        ords = np.array([S.ordinal(r[0]) for r in days], dtype=np.int32)
        P.series = {'AAA': (ords, np.full(30, 20.0), '')}
        E = S.Events()
        a = E.actor('i:X', 'X', 'ins')
        E.add(a, 'AAA', days[5][0], None, 1, 1e9, usd=1e9, shares=1000)          # $1M a share typed in: 1,000 × $20 instead
        E.add(a, 'AAA', days[6][0], None, 1, 25000, usd=25000, shares=1000)      # $25 against a $20 close: as filed
        E.add(a, 'ZZZ', days[6][0], None, -1, 5e9, usd=5e9, shares=100)          # no close, $50M a share: no dollar value
        E.freeze()
        self.assertEqual(S.fix_insider_usd(E, P), 2)
        self.assertEqual(E.usd[0], 20000.0)
        self.assertEqual(E.usd[1], 25000.0)
        self.assertTrue(np.isnan(E.usd[2]))


@unittest.skipIf(S is None, 'numpy not installed')
class Build(unittest.TestCase):
    def test_offline_build_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            hub, root = Path(d) / 'hub', Path(d) / 'smart'
            n = 800
            days = series('2023-06-01', n, lambda i: 100)
            def px(t, f):
                gz(hub / 'cache' / 'prices' / f'{t}.json.gz', {'ticker': t, 'fetched_at': '2026-10-18T00:00:00+00:00', 'rows': [[r[0], f(i), 1000] for i, r in enumerate(days)]})
            px('SPY', lambda i: 100 + i * 0.02)
            px('AAA', lambda i: 50 * 1.0015 ** i)
            px('BBB', lambda i: 80 * 0.9995 ** i)
            snaps = []
            q = ['2024-03-31', '2024-06-30', '2024-09-30', '2024-12-31', '2025-03-31', '2025-06-30', '2025-09-30', '2025-12-31', '2026-03-31']
            for k in range(1, len(q)):
                buy = 'c1' if k % 2 else 'c2'
                snaps.append({'period': q[k], 'filed': q[k][:5] + ('05-15' if q[k][5:7] == '03' else '08-14' if q[k][5:7] == '06' else '11-14' if q[k][5:7] == '09' else '02-14'),
                              'complete': True, 'baseline_period': q[k - 1], 'total_usd': 1e6,
                              'changes': [{'cusip': buy, 'put_call': 'NONE', 'share_type': 'SH', 'shares': 300, 'prior_shares': 100, 'value_usd': 30000,
                                           'prior_value_usd': 10000, 'status': 'INCREASE'}]})
            gz(hub / 'cache' / 'holdings' / '123.json.gz', {'cik': '123', 'label': 'Test Capital', 'snapshots': snaps})
            (hub / 'cache' / 'prices' / 'cusips.json').write_text(json.dumps({'c1': {'ticker': 'AAA'}, 'c2': {'ticker': 'BBB'}}))
            gz(hub / 'cache' / 'insiders' / 'trades.json.gz', [{'insider': 'Doe Jane', 'role': 'CEO', 'ticker': 'AAA', 'code': 'P', 'date': days[-5][0], 'value': 50000, 'issuer': 'AAA Inc'}])
            gz(root / 'cache' / 'ins' / '2024q1.json.gz', {'quarter': '2024q1', 'rows': [['1', 'Doe Jane', 'CEO', 'AAA', '5', 'AAA Inc', '2024-02-01', '2024-02-03', 1, 1000, 50000, 0],
                                                                                          ['1', 'Doe Jane', 'CEO', 'BBB', '6', 'BBB Inc', '2024-02-05', '2024-02-07', -1, 1000, 80000, 0],
                                                                                          ['2', 'Plan Joe', 'CFO', 'AAA', '5', 'AAA Inc', '2024-02-05', '2024-02-07', -1, 1000, 80000, 1],
                                                                                          ['3', 'Tiny Tim', 'Officer', 'AAA', '5', 'AAA Inc', '2024-02-05', '2024-02-07', 1, 10, 500, 0]]})
            st = S.build(root, hub, None, offline=True, today=S.ordinal(days[-1][0]))
            pub = root / 'public'
            idx = json.loads((pub / 'index.json').read_text())
            self.assertEqual(st['events'], {'f13': 8, 'etf': 0, 'ins': 3, 'gov': 0})   # the 10b5-1 sale and the $500 trade are left out
            self.assertEqual(idx['counts']['f13']['trades'], 8)
            self.assertTrue((pub / 't' / 'AAA.json').exists())
            self.assertTrue((pub / 'a' / 'f13' / (S.bucket('f:123') + '.json')).exists())
            rec = json.loads((pub / 'a' / 'f13' / (S.bucket('f:123') + '.json')).read_text())['actors']['f:123']
            self.assertEqual(rec['stats']['scored'], 7)    # the last quarter's 63 days have not passed
            self.assertEqual(rec['stats']['hit'], 0.5714)  # it bought the winner (4) and the loser (3 scored) in turn
            names = json.loads((pub / 'actors.json').read_text())['rows']
            self.assertEqual({r[0] for r in names}, {'f:123', 'i:DOE JANE'})
            t = json.loads((pub / 't' / 'AAA.json').read_text())
            self.assertTrue(t['votes'] and t['votes'][0][0] == 'i:DOE JANE')                # the CEO's purchase this week
            json.dumps(idx, allow_nan=False)
            # All flows: the quarter whose 13F reports are arriving (Q1 2026 here) has the manager's buy, Q2 to date the CEO's
            cix = json.loads((pub / 'combined' / 'index.json').read_text())
            self.assertEqual([p['key'] for p in cix['periods']], ['prev', 'prev2', 'both', 'qtd', 'd90'])
            F = cix['fields']
            prev = json.loads((pub / 'combined' / 'prev.json').read_text())
            row = dict(zip(F, prev['rows'][0]))
            self.assertEqual((row['f13_b'], row['f13_s'], row['groups_buy']), (1, 0, 1))
            self.assertEqual(row['ticker'], 'BBB')
            self.assertTrue(11000 < row['f13_usd'] < 11200)            # 200 shares × BBB's close at the quarter end, not the filing's $100
            self.assertEqual(prev['actors']['f13'][0][0], 'f:123')
            qtd = json.loads((pub / 'combined' / 'qtd.json').read_text())
            r2 = dict(zip(F, next(r for r in qtd['rows'] if r[0] == 'AAA')))
            self.assertEqual((r2['ins_b'], r2['ins_usd'], r2['f13_b']), (1, 50000, 0))


if __name__ == '__main__':
    unittest.main()
