"""scripts/seo_quality.py: the 0–100 score from the quality research rows, with the reasons and the pages;
scripts/seo_cashflow.py runway(): cash runway and the debt wall."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_quality as Q  # noqa: E402
import seo_cashflow as C  # noqa: E402


def rows():
    F = ['ticker', 'cik', 'name', 'sector', 'mcap', 'accruals', 'da', 'm_score', 'm_flag', 'dechow_f', 'dechow_band', 'c_score', 'c_n', 'f_score', 'f_n', 'ng_gap', 'smooth', 'growth']
    R = [['AAA', 1, 'ALPHA INC', 'technology', 20e9, -0.05, 0.01, -2.6, False, 0.8, 'normal', 1, 6, 8, 9, 0.0, 1.1, 0.1],
         ['BBB', 2, 'BETA CORP', 'technology', 30e9, 0.12, 0.09, -1.2, True, 2.6, 'high', 5, 6, 3, 9, -0.25, 0.25, 0.5],
         ['CCC', 3, 'GAMMA BANK', 'financials', 5e9, 0.01, 0.02, None, None, 1.2, 'normal', 2, 5, 6, 9, -0.05, 0.9, 0.05],
         ['DDD', 4, 'DELTA', 'health', 1e9, 0.03, None, None, None, None, None, None, None, 5, 9, None, None, None]]
    return {'fields': F, 'rows': R}


def test_score():
    sc = Q.score_all(rows())
    by = {x['ticker']: x for x in sc}
    assert 'DDD' not in by                                              # too few components to score
    assert by['AAA']['score'] > by['CCC']['score'] > by['BBB']['score'] and by['AAA']['grade'] == 'A' and by['BBB']['grade'] == 'E'
    assert by['AAA']['rank'] == 1 and sum(w for _, w, _ in by['AAA']['parts'].values()) > 99.9
    assert 'beneish' not in by['CCC']['parts'] and sum(w for _, w, _ in by['CCC']['parts'].values()) > 99.9     # a bank: rescaled without Beneish
    lost, won = Q.reasons(by['BBB'])
    assert lost and 'accruals' in lost[0][3] and any('flagged' in t for _, _, _, t in lost)
    assert by['AAA']['parts']['smoothness'][0] == 5 and by['BBB']['parts']['smoothness'][0] < 1


def test_pages(tmp_path):
    s = tmp_path
    (s / 'disclosures' / 'data' / 'research' / 'quality').mkdir(parents=True)
    (s / 'disclosures' / 'data' / 'research' / 'quality' / 'index.json').write_text(json.dumps(rows()))
    (s / 'data').mkdir()
    (s / 'data' / 'index.json').write_text(json.dumps({'companies': [{'cik': 1, 'ticker': 'AAA', 'name': 'ALPHA INC'}, {'cik': 2, 'ticker': 'BBB', 'name': 'BETA CORP'}]}))
    for sl in ('aaa', 'bbb'):
        (s / 'c' / sl).mkdir(parents=True)
        (s / 'c' / sl / 'index.html').write_text('<nav class="seo-toc" aria-label="On this page"></nav>')
    assert Q.write(str(s), 'https://example.com') == 3
    p = (s / 'c' / 'bbb' / 'earnings-quality' / 'index.html').read_text()
    assert 'Beta earnings quality score' in p and 'grade E' in p and 'Revenue grew 50%' in p and 'What earned and lost points' in p
    assert 'href="earnings-quality/"' in (s / 'c' / 'bbb' / 'index.html').read_text()
    idx = (s / 'disclosures' / 'earnings-quality' / 'index.html').read_text()
    assert 'Highest scores' in idx and 'Beneish M-score flagged' in idx and 'c/bbb/earnings-quality/' in idx
    d = json.loads((s / 'data' / 'quality-score.json').read_text())
    assert d['n'] == 3 and d['rows'][0][0] == 'AAA' and 'sitemap-quality.xml' in (s / 'robots.txt').read_text()


def test_runway():
    q = [{'label': f'Q{k}', 'items': {'ocf': -20e6, 'capex': -5e6}} for k in range(4)]
    ttm = {'label': 'TTM', 'items': {'ocf': -80e6, 'capex': -20e6}}
    c = {'quality': {'val': {'cash_all': 200e6, 'debt': 50e6, 'b_ltd_c': 10e6, 'end': '2026-09-30'}, 'cap': {'maturities': {'label': 'FY2025', 'buckets': [[1, 10e6], [2, 40e6]]}}}}
    rw = C.runway(c, q, ttm)
    assert rw['burn'] == 100e6 and rw['months'] == 24 and rw['due12'] == 10e6 and rw['net'] == 150e6 and rw['buckets'] == [(1, 10e6), (2, 40e6)]
    body, line = C.runway_section('Alpha', rw)
    assert 'runway of about' in line and 'operations themselves consumed cash' in line and 'Cash runway' in body and 'debt maturities by year' in body
    # self-funding, and a burn that is new (latest quarter annualised)
    ttm2 = {'label': 'TTM', 'items': {'ocf': 90e6, 'capex': -20e6}}
    q3 = [{'label': f'Q{k}', 'items': {'ocf': 25e6, 'capex': -5e6}} for k in range(4)]
    assert C.runway(c, q3, ttm2)['burn'] is None and 'funds itself' in C.runway_section('Alpha', C.runway(c, q3, ttm2))[1]
    q2 = [{'label': 'Q1', 'items': {'ocf': 30e6, 'capex': -5e6}}, {'label': 'Q2', 'items': {'ocf': 30e6, 'capex': -5e6}}, {'label': 'Q3', 'items': {'ocf': -5e6, 'capex': -5e6}}, {'label': 'Q4', 'items': {'ocf': -5e6, 'capex': -5e6}}]
    rw2 = C.runway(c, q2, ttm2)
    assert rw2['burn'] == 40e6 and rw2['months'] == 60
    assert C.runway({'quality': {}}, q, ttm) is None


def test_chain_index(tmp_path):
    import seo
    data = tmp_path / 'data'
    periods = [['2025-01-01', '2025-03-31', 'q', 'Q1 2025'], ['2025-04-01', '2025-06-30', 'q', 'Q2 2025'], ['2025-07-01', '2025-09-30', 'q', 'Q3 2025'], ['2025-01-01', '2025-12-31', 'fy', 'FY2025'],
               ['2026-01-01', '2026-03-31', 'q', 'Q1 2026']]
    for cik, base in ((1, 100.0), (2, 50.0)):
        (data / 'c').mkdir(parents=True, exist_ok=True)
        (data / 'c' / f'{cik}.json').write_text(json.dumps({'quality': {'hist': {'keys': ['revenue'], 'periods': periods, 'v': {'revenue': [[i, [[base * (i + 1), None]]] for i in range(5)]}},
                                                                         'cap': {'hq': {'keys': ['ocf', 'capex'], 'rows': [['2025-12-31', 10, -7], ['2026-03-31', 12, -9]]}}}}))
    d = {'companies': [{'cik': 1, 'role': 'supplier', 'attr': 500, 'rev': 1000}, {'cik': 2, 'role': 'supplier', 'attr': 100, 'rev': 100}, {'cik': 3, 'role': 'tier2', 'attr': 1, 'rev': 1}],
         'buyers': [{'cik': 1, 't': 'A'}, {'cik': 2, 't': 'B'}]}
    ci = seo.chain_index(str(data), d)
    labels = [l for l, _, _ in ci['revenue']]
    assert labels == ['Q1 2025', 'Q2 2025', 'Q3 2025', 'Q4 2025', 'Q1 2026']
    assert abs(ci['revenue'][0][1] - (100 * 0.5 + 50)) < 1e-9 and ci['revenue'][0][2] == 2
    assert abs(ci['revenue'][3][1] - ((400 - 600) * 0.5 + (200 - 300))) < 1e-9          # Q4 = FY − three quarters, per company
    assert abs(ci['revenue_yoy'] - ((500 * 0.5 + 250) / 100 - 1)) < 1e-9
    assert ci['capex'] == [('Q4 2025', 14, 2), ('Q1 2026', 18, 2)] and abs(ci['capex_yoy'] or 0) == 0 or ci['capex_yoy'] is None
    assert seo.chain_index(str(data), {'companies': [], 'buyers': []}) is None
