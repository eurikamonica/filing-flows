"""scripts/seo_reportcard.py: the report card from a company's estimate history and guidance record, the move model,
guidance credibility with the metric's orientation, the ranking page and sitemap."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_reportcard as R  # noqa: E402


def w(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o))


def test_models():
    hist = [{'est': 1, 'act': 1.1, 'surprise': .1, 'beat': 1, 'move': .05}, {'est': 1, 'act': 1.2, 'surprise': .2, 'beat': 1, 'move': .03},
            {'est': 1, 'act': .9, 'surprise': -.1, 'beat': 0, 'move': -.08}, {'est': 1, 'act': 1.05, 'surprise': .05, 'beat': 1, 'move': -.01}]
    m = R.move_model(hist, {'move': .06}, .04)
    assert m['n'] == 4 and abs(m['median_abs'] - .05) < 1e-9 and m['up_share'] == .5 and m['up_on_beat'] == 2 / 3 and m['held'] == .75 and m['down_on_miss'] == 1
    rec = {'metrics': [{'name': 'Revenue', 'metric': 'revenue', 'hits': {'better': 'higher'}, 'rows': [
        {'label': f'Q{k}', 'actual': 110, 'vsMid': 10, 'guides': [{'lo': 90, 'hi': 100}]} for k in range(4)]},
        {'name': 'Tax rate', 'hits': {'better': 'lower'}, 'rows': [{'label': f'Q{k}', 'actual': 12, 'vsMid': -20, 'guides': [{'lo': 14, 'hi': 16}]} for k in range(3)]}]}
    c = R.credibility(rec)
    assert c[0]['above'] == 4 and c[0]['style'].startswith('conservative') and abs(c[0]['p_next'] - 5 / 6) < 1e-9
    assert c[1]['lower'] and c[1]['above'] == 3 and c[1]['avg_vs_mid'] == 20          # a low tax rate against a guided range is the beat
    assert R.credibility({'metrics': [{'name': 'x', 'rows': [{'actual': 1, 'guides': [{'lo': 0, 'hi': 2}]}]}]}) is None


def test_pages(tmp_path):
    s = tmp_path
    w(s / 'data' / 'index.json', {'companies': [{'cik': 1, 'ticker': 'AAA', 'name': 'ALPHA INC', 'revenue': 1e9}]})
    (s / 'c' / 'aaa').mkdir(parents=True)
    (s / 'c' / 'aaa' / 'index.html').write_text('<nav class="seo-toc" aria-label="On this page"></nav>')
    w(s / 'data' / 'c' / '1.json', {'quarters': [{'end': '2026-06-30', 'label': 'Q2 2026'}, {'end': '2026-03-31', 'label': 'Q1 2026'}, {'end': '2025-12-31', 'label': 'Q4 2025'}, {'end': '2025-09-30', 'label': 'Q3 2025'}]})
    w(s / 'disclosures' / 'data' / 'research' / 'earnings' / 'c' / 'AAA.json', {'report_date': '2099-01-01', 'consensus': {'eps': 2}, 'implied': {'move': .05}, 'avg_move': .03,
      'nongaap': {'points': [{'quarter': '2026-06-30', 'gaap': 1.0}]},
      'history': [{'quarter': q, 'reported': r, 'est': 1, 'act': a, 'surprise': a - 1, 'beat': int(a > 1), 'move': m, 'excess': m / 2} for q, r, a, m in
                  [('2025-09-30', '2025-10-20', 1.1, .04), ('2025-12-31', '2026-01-25', .9, -.06), ('2026-03-31', '2026-04-24', 1.2, .02), ('2026-06-30', '2026-07-24', 1.05, .01)]]})
    w(s / 'data' / 'guidance-record' / '1.json', {'metrics': [{'name': 'Revenue', 'metric': 'revenue', 'hits': {'better': 'higher'}, 'rows': [
        {'label': l, 'actual': a, 'vsMid': 5, 'guides': [{'lo': 90e6, 'hi': 100e6}]} for l, a in [('Q2 2026', 105e6), ('Q1 2026', 99e6), ('Q4 2025', 97e6), ('Q3 2025', 101e6)]]}]})
    assert R.write(str(s), 'https://example.com') == 1
    p = (s / 'c' / 'aaa' / 'report-card' / 'index.html').read_text()
    assert 'beat the analysts&#x27; EPS estimate in 3 of its last 4 reports (75%)' in p and '<td>Q2 2026</td>' in p and '$90M–$100M' in p and '(above)' in p
    assert 'options price in about <b>±5.0%</b>' in p and 'How credible is its guidance' in p and 'href="report-card/"' in (s / 'c' / 'aaa' / 'index.html').read_text()
    idx = (s / 'disclosures' / 'report-cards' / 'index.html').read_text()
    assert 'Most reliable beaters' in idx and "c/aaa/report-card/" in idx
    assert (s / 'sitemap-reportcards.xml').read_text().count('<url>') == 2 and 'sitemap-reportcards.xml' in (s / 'robots.txt').read_text()
