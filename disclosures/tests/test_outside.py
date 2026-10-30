"""outside.py: names and matching, the pipeline from ClinicalTrials.gov, recalls (FDA, CPSC, NHTSA), the Federal
Register, the FEC, Wikipedia attention, cost shocks, and the published files — all on small stand-in answers."""
import datetime as dt
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import outside as O  # noqa: E402

TODAY = dt.date(2026, 10, 29)
COS = [{'cik': 78003, 'ticker': 'PFE', 'name': 'PFIZER INC', 'sector': 'health', 'sic': '2834', 'revenue': 6e10},
       {'cik': 37996, 'ticker': 'F', 'name': 'FORD MOTOR CO', 'sector': 'consumer-disc', 'sic': '3711', 'revenue': 1.8e11},
       {'cik': 1318605, 'ticker': 'TSLA', 'name': 'Tesla, Inc.', 'sector': 'consumer-disc', 'sic': '3711', 'revenue': 9e10},
       {'cik': 936468, 'ticker': 'LMT', 'name': 'LOCKHEED MARTIN CORP', 'sector': 'industrials', 'sic': '3760', 'revenue': 7e10},
       {'cik': 320193, 'ticker': 'AAPL', 'name': 'Apple Inc.', 'sector': 'technology', 'sic': '3571', 'revenue': 4e11},
       {'cik': 1551152, 'ticker': 'ABBV', 'name': 'AbbVie Inc.', 'sector': 'health', 'sic': '2834', 'revenue': 5e10},
       {'cik': 909832, 'ticker': 'COST', 'name': 'COSTCO WHOLESALE CORP /NEW', 'sector': 'consumer-staples', 'sic': '5331', 'revenue': 2.5e11},
       {'cik': 1, 'ticker': 'GE', 'name': 'GE', 'sector': 'industrials', 'sic': '3600', 'revenue': 1e10}]


def site(d):
    p = Path(d) / 'index.json'
    p.write_text(json.dumps({'companies': COS}))
    return p


class Names(unittest.TestCase):
    def test_display_and_match(self):
        self.assertEqual(O.display_name('LOCKHEED MARTIN CORP'), 'Lockheed Martin')
        self.assertEqual(O.display_name('Apple Inc.'), 'Apple Inc')                  # one word keeps its suffix
        self.assertEqual(O.display_name('COSTCO WHOLESALE CORP /NEW'), 'Costco Wholesale')
        with tempfile.TemporaryDirectory() as d:
            find = O.matcher(O.universe(site(d)))
        self.assertEqual(find('Pfizer Laboratories Div Pfizer Inc')['ticker'], 'PFE')
        self.assertEqual(find('Ford Motor Company')['ticker'], 'F')
        self.assertEqual(find('TESLA, INC.')['ticker'], 'TSLA')
        self.assertIsNone(find('Pfizerco Holdings'))                                # whole words only
        self.assertIsNone(find('Abbott'))                                           # not on this list
        self.assertIsNone(find('GE Appliances'))                                    # too short a name to match alone
        self.assertIsNone(find('Chrysler (FCA US, LLC)'))                           # an alias whose company is not on the list


class Trials(unittest.TestCase):
    def test_fetch_and_summary(self):
        def study(i, sponsor, phases, status, pcd, cond='Asthma'):
            return {'protocolSection': {'identificationModule': {'nctId': f'NCT{i:08d}', 'briefTitle': f'Study {i}'},
                                        'statusModule': {'overallStatus': status, 'primaryCompletionDateStruct': {'date': pcd}},
                                        'sponsorCollaboratorsModule': {'leadSponsor': {'name': sponsor}}, 'conditionsModule': {'conditions': [cond]},
                                        'designModule': {'phases': phases, 'studyType': 'INTERVENTIONAL', 'enrollmentInfo': {'count': 100}},
                                        'armsInterventionsModule': {'interventions': [{'name': f'PF-{i}'}]}}}
        pages = [{'studies': [study(1, 'Pfizer', ['PHASE3'], 'RECRUITING', '2027-03'), study(2, 'Pfizer Inc.', ['PHASE2', 'PHASE3'], 'ACTIVE_NOT_RECRUITING', '2026-12-15'),
                              study(3, 'Pfizerbio Ltd', ['PHASE1'], 'RECRUITING', '2027-01')], 'nextPageToken': 'x'},
                 {'studies': [study(4, 'Pfizer', ['PHASE1'], 'RECRUITING', '2026-11'), study(5, 'Pfizer', ['PHASE3'], 'COMPLETED', '2025-06'),
                              study(6, 'Pfizer', [], 'RECRUITING', '2027-05', 'Obesity')]}]
        calls = []

        def fetch(url, params):
            if params['query.lead'] != 'pfizer':
                return {'studies': [study(9, 'Hospira, Inc.', ['PHASE1'], 'COMPLETED', '2020-01')]}   # a subsidiary, queried on its own
            calls.append(params)
            return pages[len(calls) - 1]
        with tempfile.TemporaryDirectory() as d:
            pfe = next(c for c in O.universe(site(d)) if c['ticker'] == 'PFE')
        st = O.trials_fetch(pfe, fetch)
        self.assertEqual([s['id'] for s in st], ['NCT00000001', 'NCT00000002', 'NCT00000004', 'NCT00000005', 'NCT00000006', 'NCT00000009'])   # not "Pfizerbio"
        self.assertEqual(calls[1]['pageToken'], 'x')
        s = O.trials_summary(st, TODAY)
        self.assertEqual((s['active'], s['phases']['PHASE3']['active'], s['phases']['PHASE1']['active'], s['completed_2y']), (4, 2, 1, 1))
        self.assertEqual([x[0] for x in s['due']], ['NCT00000002', 'NCT00000001'])     # phase 2–3, by date
        self.assertEqual(s['conditions'][0], ('Asthma', 3))


class Recalls(unittest.TestCase):
    def test_sources_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            comps = O.universe(site(d))
        find = O.matcher(comps)
        pfe = next(c for c in comps if c['ticker'] == 'PFE')

        def fetch(url, params):
            if 'device' in url:
                raise RuntimeError('HTTP 404')
            return {'results': [{'report_date': '20260923', 'classification': 'Class II', 'recalling_firm': 'Pfizer Inc.', 'product_description': 'Dopamine',
                                 'reason_for_recall': 'Sterility', 'status': 'Ongoing', 'recall_number': 'D-1'},
                                {'report_date': '20260101', 'classification': 'Class I', 'recalling_firm': 'Hospira Inc', 'product_description': 'x'}]} if 'drug' in url else {'results': []}
        fda = O.fda_recalls(pfe, '2021-10-29', fetch)
        self.assertEqual([x['firm'] for x in fda], ['Pfizer Inc.', 'Hospira Inc'])            # Hospira: Pfizer's
        cp = O.cpsc_match([{'RecallDate': '2026-05-01T00:00:00', 'Title': 'Costco recalls chairs', 'Manufacturers': [], 'Importers': [{'Name': 'Costco Wholesale Corporation'}],
                            'Hazards': [{'Name': 'Fall'}], 'Products': [{'NumberOfUnits': 'About 10,000'}], 'RecallNumber': '26-1', 'URL': 'u'},
                           {'RecallDate': '2026-05-02', 'Title': 'Other', 'Manufacturers': [{'Name': 'Bamamon'}]}], find)
        self.assertEqual(list(cp), [909832])
        nh = O.nhtsa_match([{'manufacturer': 'Ford Motor Company', 'report_received_date': '2026-10-01T00:00:00.000', 'subject': 'Brakes', 'potentially_affected': '12000',
                             'nhtsa_id': '26V1', 'component': 'SERVICE BRAKES'},
                            {'manufacturer': 'Tesla, Inc.', 'report_received_date': '2025-01-01', 'subject': 'Seat', 'potentially_affected': 'x'}], find)
        self.assertEqual(sorted(nh), [37996, 1318605])
        s = O.recalls_summary(nh[37996] + [dict(nh[37996][0], date='2024-03-01', units=5)], TODAY)
        self.assertEqual((s['n'], s['last_12m'], s['units_12m']), (2, 1, 12000))
        self.assertEqual(s['latest'][0]['date'], '2026-10-01')


class FedregFec(unittest.TestCase):
    def test_fedreg(self):
        seen = {}

        def fetch(url, params):
            seen['p'] = params
            return {'count': 84, 'results': [{'publication_date': '2026-09-22', 'type': 'Notice', 'agencies': [{'name': 'Defense Department'}, {'raw_name': 'DSCA'}],
                                               'title': 'Arms Sales Notification', 'html_url': 'h'}]}
        with tempfile.TemporaryDirectory() as d:
            lmt = next(c for c in O.universe(site(d)) if c['ticker'] == 'LMT')
        r = O.fedreg(lmt, '2025-10-29', fetch)
        self.assertEqual(r['count'], 84)
        self.assertIn(('conditions[term]', '"Lockheed Martin"'), seen['p'])
        self.assertEqual(r['agencies_recent'][0], ('Defense Department', 1))

    def test_fec(self):
        def fetch(url, params):
            if url.endswith('/committees/'):
                return {'results': [{'committee_id': 'C00303024', 'name': "LOCKHEED MARTIN CORPORATION EMPLOYEES' POLITICAL ACTION COMMITTEE", 'committee_type': 'Q',
                                     'organization_type': 'C', 'affiliated_committee_name': 'LOCKHEED MARTIN CORPORATION'},
                                    {'committee_id': 'C9', 'name': 'FRIENDS OF MARTIN', 'committee_type': 'H', 'affiliated_committee_name': None}]}
            if '/totals/' in url:
                return {'results': [{'receipts': 2e6, 'disbursements': 1.5e6, 'fed_candidate_committee_contributions': 1e6, 'last_cash_on_hand_end_period': 5e5}]}
            return {'results': [{'recipient_name': 'NRCC', 'total': 15000}, {'recipient_name': 'DCCC', 'total': 15000}]}
        with tempfile.TemporaryDirectory() as d:
            lmt = next(c for c in O.universe(site(d)) if c['ticker'] == 'LMT')
        r = O.fec(lmt, 'k', [2026, 2024], fetch)
        self.assertEqual(r['pacs'][0][0], 'C00303024')
        self.assertEqual(r['cycles']['2026']['to_candidates'], 1e6)
        self.assertEqual(len(r['top_recipients']), 2)


class AttentionCosts(unittest.TestCase):
    def test_attention(self):
        days = {}
        d0 = dt.date(2025, 10, 1)
        for i in range(400):
            d = d0 + dt.timedelta(days=i)
            days[d.isoformat()] = 1000 + (5000 if i >= 393 else 0)
        a = O.attention(days)
        self.assertEqual(a['avg7'], 6000)
        self.assertEqual(a['avg90'], 1000)
        self.assertEqual(a['ratio'], 6.0)
        self.assertEqual(a['peaks'][0][1], 6000)

    def test_pageviews_tops_up_and_stops_when_limited(self):
        with tempfile.TemporaryDirectory() as d:
            comps = O.universe(site(d))
            calls = []

            def fetch(url):
                calls.append(url)
                if 'Ford' in url:
                    raise RuntimeError('HTTP 429')
                return {'items': [{'timestamp': '2026102700', 'views': 5}, {'timestamp': '2026102800', 'views': 7}]}
            wmap = {'78003': 'Pfizer', '37996': 'Ford_Motor_Company'}
            O.time.sleep, real = (lambda s: None), O.time.sleep
            try:
                r = O.pageviews(d, comps, wmap, budget_s=60, fetch=fetch, today=TODAY)
                self.assertEqual(r['updated'], 1)
                self.assertEqual((r['waiting'], r['rate_limited']), (1, False))   # Ford: asked to wait, tried again next run
                self.assertEqual(json.loads((Path(d) / 'cache' / 'views' / '78003.json').read_text())['days']['2026-10-28'], 7)
                calls.clear()
                O.pageviews(d, comps, {'78003': 'Pfizer'}, budget_s=60, fetch=fetch, today=TODAY)
                self.assertEqual(calls, [])                                     # up to date: nothing asked
            finally:
                O.time.sleep = real

    def test_cost_panel_recovers_the_slope(self):
        rnd = random.Random(2)
        oil = {}
        for y in range(2021, 2027):
            for q in range(1, 5):
                oil[f'CY{y}Q{q}'] = 60 * (1.3 if (y + q) % 3 == 0 else 1.0) * (1 + rnd.uniform(-0.1, 0.1))
        qfig = {}
        for c in range(30):
            per = {}
            gm0 = rnd.uniform(0.2, 0.4)
            for q in oil:
                gm = gm0 - 0.10 * O.math.log(oil[q] / 60) + rnd.gauss(0, 0.002)   # 10 margin points per 100% oil
                per[q] = {'rev': 100.0, 'gp': 100 * gm, 'oi': 100 * (gm - 0.1)}
            qfig[str(c)] = per
        sec, co = O.cost_panel(qfig, {'oil': oil}, lambda cik: 'materials')
        f = sec['materials']['oil']
        self.assertAlmostEqual(f['b_gm'], -0.10, delta=0.01)
        self.assertLess(f['t_gm'], -10)
        self.assertIsNotNone(co['0']['oil']['shrunk_gm'])


class Build(unittest.TestCase):
    def test_build_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            root, sp = Path(d) / 'ro', site(d)
            O.write_json(root / 'cache' / 'trials' / '78003.json', {'at': O.now(), 'data': [
                {'id': 'NCT1', 'title': 't', 'phases': ['PHASE3'], 'status': 'RECRUITING', 'pcd': '2027-02', 'n': 300, 'conditions': ['RSV'], 'drugs': ['x'], 'sponsor': 'Pfizer'}]})
            O.write_json(root / 'cache' / 'fda' / '78003.json', {'at': O.now(), 'data': [{'source': 'FDA drug', 'date': '2026-09-23', 'class': 'Class II', 'what': 'x', 'why': 'y'}]})
            O.write_json(root / 'cache' / 'nhtsa.json', [{'manufacturer': 'Ford Motor Company', 'report_received_date': '2026-10-01', 'subject': 'Brakes', 'potentially_affected': '9'}])
            O.write_json(root / 'cache' / 'cpsc.json', [])
            O.write_json(root / 'cache' / 'fedreg' / '936468.json', {'at': O.now(), 'data': {'count': 3, 'docs': [['2026-09-22', 'Notice', 'DoD', 'Arms sale', 'h']]}})
            O.write_json(root / 'cache' / 'views' / '320193.json', {'article': 'Apple_Inc.', 'days': {f'2026-10-{i:02d}': 100 for i in range(1, 28)}})
            st = O.build(root, sp, today=TODAY)
            self.assertEqual((st['trials'], st['recalls'], st['fedreg'], st['attention']), (1, 2, 1, 1))
            ix = json.loads((root / 'public' / 'index.json').read_text())
            rows = {r[1]: dict(zip(ix['fields'], r)) for r in ix['rows']}
            self.assertEqual(rows['PFE']['trials_active'], 1)
            self.assertEqual(rows['F']['recalls_12m'], 1)
            lists = json.loads((root / 'public' / 'lists.json').read_text())
            self.assertEqual(lists['catalysts'][0][1], 'PFE')
            self.assertTrue((root / 'public' / 'c' / '320193.json').exists())


if __name__ == '__main__':
    unittest.main()


FIN = [{'cik': 19617, 'ticker': 'JPM', 'name': 'JPMORGAN CHASE & CO', 'sector': 'financials', 'sic': '6021', 'revenue': 2.5e11},
       {'cik': 70858, 'ticker': 'BAC', 'name': 'BANK OF AMERICA CORP /DE/', 'sector': 'financials', 'sic': '6021', 'revenue': 1.9e11},
       {'cik': 831001, 'ticker': 'C', 'name': 'CITIGROUP INC', 'sector': 'financials', 'sic': '6021', 'revenue': 1.6e11},
       {'cik': 1, 'ticker': 'FXNC', 'name': 'FIRST NATIONAL CORP', 'sector': 'financials', 'sic': '6022', 'revenue': 1e8},
       {'cik': 2, 'ticker': 'BA', 'name': 'BOEING CO', 'sector': 'industrials', 'sic': '3721', 'revenue': 7e10},
       {'cik': 93410, 'ticker': 'CVX', 'name': 'CHEVRON CORP', 'sector': 'energy', 'sic': '2911', 'revenue': 2e11},
       {'cik': 107263, 'ticker': 'WMB', 'name': 'WILLIAMS COMPANIES, INC.', 'sector': 'energy', 'sic': '4922', 'revenue': 1e10},
       {'cik': 1166691, 'ticker': 'NUE', 'name': 'NUCOR CORP', 'sector': 'materials', 'sic': '3312', 'revenue': 3e10}]


def fin_universe(d):
    p = Path(d) / 'index.json'
    p.write_text(json.dumps({'companies': COS + FIN}))
    return O.universe(p)


class Complaints(unittest.TestCase):
    def test_matching_is_strict(self):
        with tempfile.TemporaryDirectory() as d:
            f = O.cfpb_matcher(fin_universe(d))
        self.assertEqual(f('JPMORGAN CHASE & CO.')['ticker'], 'JPM')
        self.assertEqual(f('BANK OF AMERICA, NATIONAL ASSOCIATION')['ticker'], 'BAC')     # the bank, banking words after
        self.assertEqual(f('CITIBANK, N.A.')['ticker'], 'C')                              # a known alias
        self.assertEqual(f('FORD MOTOR CREDIT CO.')['ticker'], 'F')                       # a captive lender
        self.assertIsNone(f('FIRST NATIONAL BANK OF OMAHA'))                              # a common word is never enough
        self.assertIsNone(f("BOEING EMPLOYEES' CREDIT UNION"))                            # credit unions never
        self.assertIsNone(f('Tesla Land Transfer'))                                       # not a lender's name

    def test_summary(self):
        years = [{'A': 120, 'B': 30}, {'A': 100}, {'A': 80}]
        det = {'total': 150, 'products': [['Credit card', 90]], 'issues': [['Billing', 40]],
               'responses': [['Closed with explanation', 120], ['Closed with monetary relief', 15], ['Closed with non-monetary relief', 15]],
               'timely': [['Yes', 147], ['No', 3]]}
        s = O.cfpb_summary(['A', 'B'], years, det, 3e9)
        self.assertEqual(s['last_12m'], 150)
        self.assertEqual(s['years'], [80, 100, 150])                                      # oldest first
        self.assertAlmostEqual(s['change'], 0.5)
        self.assertEqual(s['per_bn'], 50.0)
        self.assertAlmostEqual(s['relief_share'], 0.1)
        self.assertAlmostEqual(s['any_relief_share'], 0.2)
        self.assertAlmostEqual(s['late_share'], 0.02)
        self.assertIsNone(O.cfpb_summary(['Z'], years, None, 1e9))

    def test_windows(self):
        w = O.cfpb_windows(TODAY, 3)
        self.assertEqual(w[0], ('2025-10-29', '2026-10-29'))
        self.assertEqual(w[1][1], '2025-10-28')                                           # no overlap


class Environment(unittest.TestCase):
    HEAD = ['REGISTRY_ID', 'FAC_NAME', 'FAC_CITY', 'FAC_STATE', 'FAC_ACTIVE_FLAG', 'FAC_COMPLIANCE_STATUS', 'FAC_SIC_CODES', 'FAC_NAICS_CODES',
            'FAC_PROGRAMS_WITH_SNC', 'CWA_SNC_FLAG', 'RCRA_SNC_FLAG', 'SDWA_SNC_FLAG', 'CAA_HPV_FLAG', 'FAC_QTRS_WITH_NC', 'FAC_INSPECTION_COUNT',
            'FAC_FORMAL_ACTION_COUNT', 'FAC_DATE_LAST_FORMAL_ACTION', 'FAC_TOTAL_PENALTIES', 'FAC_PENALTY_COUNT', 'FAC_DATE_LAST_PENALTY',
            'FAC_MAJOR_FLAG', 'GHG_CO2_RELEASES', 'TRI_ON_SITE_RELEASES']

    def fac(self, rid, name, sic='', naics='', status='No Violation Identified', snc='0', pen='', pdate='', co2='', active='Y'):
        return [rid, name, 'X', 'TX', active, status, sic, naics, snc, 'N', 'N', 'N', 'N', '0', '2', '1' if pen else '0', '', pen, '1' if pen else '0',
                pdate, 'Y', co2, '']

    def test_bulk_and_summary(self):
        import csv
        import io
        import zipfile
        rows = [self.fac('1', 'CHEVRON REFINERY RICHMOND', sic='2911', status='Significant Violation', snc='1', pen='$3,000,000', pdate='05/07/2026', co2='4366329'),
                self.fac('2', 'CHEVRON 53504', naics='447110'),                                    # a branded gas station: retail, not refining
                self.fac('3', 'CHEVRON USA - WELL 6H', naics='211120', pen='$3,000,000', pdate='05/07/2026'),   # the same settlement again
                self.fac('4', 'NUCOR STEEL', sic='3312', pen='$100,000', pdate='01/02/2025'),
                self.fac('5', 'NUCOR CORP', active='N'),                                           # inactive
                self.fac('6', 'WILLIAMS ROGER MEDICAL CENTER', naics='622110'),                     # an ordinary word: never alone
                self.fac('7', 'TRANSCONTINENTAL GAS PIPELINE COMPANY', naics='486210')]             # an alias
        with tempfile.TemporaryDirectory() as d:
            comps = fin_universe(d)
            buf = io.StringIO()
            w = csv.writer(buf, quoting=csv.QUOTE_ALL)
            w.writerow(self.HEAD)
            w.writerows(rows)
            z = Path(d) / 'e.zip'
            with zipfile.ZipFile(z, 'w') as zf:
                zf.writestr('ECHO_EXPORTER.csv', buf.getvalue())
            m = O.epa_bulk(z, comps, lambda c: c['sector'] in O.EPA_SECTORS)
        names = {k: sorted(r[0] for r in v) for k, v in m.items()}
        self.assertEqual(names[93410], ['CHEVRON REFINERY RICHMOND', 'CHEVRON USA - WELL 6H'])
        self.assertEqual(names[1166691], ['NUCOR STEEL'])
        self.assertEqual(names[107263], ['TRANSCONTINENTAL GAS PIPELINE COMPANY'])
        s = O.epa_summary(m[93410], 2e11)
        self.assertEqual(s['facilities'], 2)
        self.assertEqual(s['snc'], 1)
        self.assertEqual(s['in_violation'], 1)
        self.assertEqual(s['penalties_5y'], 3_000_000)                                       # counted once
        self.assertEqual(s['last_penalty'], '2026-05-07')
        self.assertEqual(s['co2_t'], 4366329)
        self.assertEqual(s['top'][0][0], 'CHEVRON REFINERY RICHMOND')
