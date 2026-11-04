"""The newer drawn charts (scripts/seo_svg.py) and the sections built on them: capital allocation by year, the revenue
river, the earnings calendar grid, the peer table, dollar amounts named in an 8-K."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402
import seo_hub as H  # noqa: E402
import seo_svg as SV  # noqa: E402
import seo_topics as T  # noqa: E402

money = lambda v: f"${v / 1e9:.1f}B"


def test_stacked_river_calendar_line():
    s = SV.stacked(['FY23', 'FY24', 'FY25'], [('OCF', [5e9, 6e9, 9e9]), ('Capex', [-1e9, -2e9, -3e9]), ('Nothing', [0, 0, 0])], money, 'alloc')
    assert s.count('<rect') >= 6 + 2 and 'Nothing' not in s and '$9.0B' in s          # an all-zero series is left out; totals above the bars
    assert SV.stacked(['a'], [('x', [1])], money, 't') == ''
    r = SV.river(['Q1', 'Q2', 'Q3', 'Q4'], [('A', [1, 2, 3, 4]), ('B', [2, 2, 2, 2])], str, 'river')
    assert r.count('<path') == 2 and r.count('<title>') >= 3
    c = SV.calendar('2026-11-04', {'2026-11-03': (5, 1e11), '2026-11-05': (2, 2e10)}, 'cal', fmt=money)
    assert c.count('<rect') == 5 and '>5<' in c and '$100.0B' in c                      # one week, Monday-aligned
    days = [f"2026-01-{i:02d}" for i in range(1, 29)]
    ln = SV.line_marks(days, [100 + i for i in range(28)], [(days[3], 'buy', 'CEO bought'), (days[10], 'earnings', 'Q1'), ('2025-01-01', 'event', 'old')], lambda v: f"${v:.0f}", 'line')
    assert '▲' in ln and '●' in ln and 'Insider buy' in ln and '◆' not in ln            # a mark outside the window is left out


def test_sections():
    me = {'cik': 1, 'ticker': 'AAA', 'name': 'ALPHA INC', 'label': 'Q3 2026', 'revenue': 10e9, 'yoy': 20.0, 'om': 30.0}
    peers = [{'cik': 2, 'ticker': 'BBB', 'name': 'BETA INC', 'label': 'Q3 2026', 'revenue': 8e9, 'yoy': 5.0, 'om': 10.0},
             {'cik': 3, 'ticker': 'CCC', 'name': 'GAMMA INC', 'label': 'Q2 2026', 'revenue': 6e9, 'yoy': -2.0, 'om': 12.0}]
    p = seo.peer_table(me, peers, 'Widgets')
    assert "class='me'" in p and "href='../bbb/'" in p and 'against the peers&#x27; median +5%' in p and '30.0%' in p
    qs = [{'label': f'Q{k}', 'nodes': [{'id': 'revenue', 'name': 'Revenue'}, {'id': 'a', 'name': 'Cloud'}, {'id': 'b', 'name': 'Ads &amp; other'}],
           'links': [{'s': 'a', 't': 'revenue', 'v': 10 + 5 * (4 - k)}, {'s': 'b', 't': 'revenue', 'v': 10}]} for k in (4, 3, 2, 1)]
    r = T.segment_river('Alpha', qs)
    assert 'Ads &amp; other' in r and 'Cloud went from' in r          # the name is unescaped once, then escaped for the SVG
    assert H.amounts('for $2.5 billion in cash, or $12.50 per share, plus $300 million of debt and $5,000 of fees') == [2.5e9, 3e8]
