"""scripts/screener.py: the merged table, the preset screens and the static page."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import screener as S  # noqa: E402


def w(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o))


def test_build(tmp_path):
    s = tmp_path
    hub = s / 'disclosures' / 'data'
    w(s / 'data' / 'index.json', {'companies': [{'cik': 1, 'ticker': 'AAA', 'name': 'ALPHA INC', 'sector': 'technology', 'industry': 'Chips', 'label': 'Q3 2026', 'filed': '2026-10-20', 'revenue': 5e9, 'yoy': 25.0, 'om': 30.0},
                                              {'cik': 2, 'ticker': 'BBB', 'name': 'BETA CORP', 'sector': 'health', 'label': 'Q3 2026', 'revenue': 1e8, 'yoy': -5.0, 'om': -40.0},
                                              {'cik': 3, 'ticker': '', 'name': 'NO TICKER'}, {'cik': 4, 'ticker': 'ZZZ', 'name': 'UNKNOWN'}]})
    w(hub / 'research' / 'quality' / 'index.json', {'fields': ['ticker', 'mcap', 'price', 'growth', 'margin', 'fcf_y', 'sy', 'z_zone', 'm_flag', 'f_score'],
                                                     'rows': [['AAA', 50e9, 100.0, 0.3, 0.25, 0.06, 0.04, 'safe', False, 7], ['BBB', 5e8, 3.0, -0.1, -0.5, -0.2, 0, 'distress', True, 2]]})
    w(s / 'data' / 'quality-score.json', {'fields': ['ticker', 'score', 'grade'], 'rows': [['AAA', 80, 'A'], ['BBB', 20, 'E']]})
    w(hub / 'research' / 'earnings' / 'index.json', {'fields': ['ticker', 'report_date', 'beat_rate', 'implied'], 'rows': [['AAA', '2099-01-01', 0.9, 0.05]]})
    w(hub / 'market' / 'signals.json', {'rows': [{'ticker': 'AAA', 'tags': ['big_inflow'], 'heat': 3, 'f13': {'usd_net': 1e9, 'buyers': 100, 'sellers': 50},
                                                 'price': {'last': 100, 'r1m': 0.02, 'r3m': 0.1, 'r1y': 0.3, 'from_high': -0.05, 'above_ma200': True}}]})
    w(hub / 'market' / 'insiders.json', {'summary': [{'ticker': 'BBB', 'buys': 3, 'sells': 0, 'buy_value': 2e6, 'sell_value': 0}]})
    w(hub / 'market' / 'short-interest.json', {'rows': [{'ticker': 'BBB', 'dtc': 9.0, 'change_pct': 20.0}]})
    w(s / 'data' / 'c' / '2.json', {'quality': {'val': {'cash_all': 50e6, 'debt': 0}, 'cap': {'q': [{'label': f'Q{k}', 'items': {'ocf': -20e6, 'capex': -5e6}} for k in range(4)],
                                                                                              'ttm': {'label': 'TTM', 'items': {'ocf': -80e6, 'capex': -20e6}}}}})
    (s / 'c' / 'aaa').mkdir(parents=True)
    (s / 'c' / 'aaa' / 'index.html').write_text('x')
    n, presets = S.write(str(s), 'https://example.com')
    assert n == 2 and presets['quality-growth'] == 1 and presets['momentum'] == 1 and presets['distress'] == 1 and presets['low-quality-earnings'] == 0
    d = json.loads((s / 'disclosures' / 'data' / 'screener.json').read_text())
    rows = [dict(zip(d['fields'], r)) for r in d['rows']]
    a, b = rows[0], rows[1]
    assert a['ticker'] == 'AAA' and a['qscore'] == 80 and a['f13_net'] == 1e9 and a['beat_rate'] == 0.9 and a['net_cash'] is None
    assert b['runway_months'] == 6 and b['ins_buys'] == 3 and b['short_dtc'] == 9 and b['z_zone'] == 'distress' and b['cash'] == 50e6
    page = (s / 'disclosures' / 'screener' / 'index.html').read_text()
    assert 'Stock screener: 2 companies' in page and "href='../../c/aaa/'" in page and 'Distress watch' in page and '6 mo' in page and 'No company passes today' in page
    assert 'sitemap-screener.xml' in (s / 'robots.txt').read_text()
