"""scripts/event_stats.py and scripts/seo_timeline.py: the reaction window around a filing's time of day, the statistics
by 8-K item and insider pattern, the timeline page with its marks, the insider-signals page and the events/impact page."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import event_stats as ES  # noqa: E402
import seo_timeline as T  # noqa: E402
import seo_hub as H  # noqa: E402
import seo  # noqa: E402


def w(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o))


def series(n, step):
    """n trading days from 2026-01-05 (a Monday), weekdays only, each day's return `step` bp"""
    import datetime as dt
    d = dt.date(2026, 1, 5)
    days = []
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += dt.timedelta(days=1)
    ds = [dt.date.fromisoformat(x) for x in days]
    return days, {'d0': days[0], 'gaps': ''.join(str((b - a).days) for a, b in zip(ds, ds[1:])), 'r': [step] * (n - 1), 'last': 100.0, 'kind': 'stock'}


def test_reaction_window():
    days, doc = series(60, 100)                                   # +1% a day
    d, cum = ES.decode(doc)
    assert d == days and abs(cum[1] - 0.01) < 1e-9
    day = days[10]
    before = ES.reaction(d, cum, day, '08:30')                    # before the open: that day's close counts
    after = ES.reaction(d, cum, day, '16:30')                     # after the close: from the next session
    assert abs(before[1][0] - 0.01) < 1e-9 and abs(after[1][0] - 0.01) < 1e-9 and abs(before[21][0] - 0.21) < 1e-9
    assert ES.reaction(d, cum, '2027-01-01', '09:00') is None and ES.reaction(d, cum, days[-1], '16:30')[1] is None
    spy_days, spy_doc = series(60, 50)
    rx = ES.reaction(d, cum, day, '08:30', spy=ES.decode(spy_doc))
    assert abs(rx[5][1] - 0.025) < 1e-9                           # excess over SPY's half-percent days
    _, closes = ES.prices(doc)
    assert abs(closes[-1] - 100) < 1e-9 and closes[-2] < closes[-1]


def site(tmp_path):
    s = tmp_path
    days, doc = series(300, 20)
    hub = s / 'disclosures' / 'data'
    w(hub / 'research' / 'paths' / 'moves' / 'a' / 'SPY.json', {**series(300, 10)[1], 'kind': 'market'})
    for t in ('AAA', 'BBB'):
        w(hub / 'research' / 'paths' / 'moves' / 'a' / f'{t}.json', {**doc, 'key': t})
        evs = [[days[k], '16:10' if k % 2 else '08:00', '8-K', '5.02,9.01', f'Officer change {k}', '', [], f'000-{k}'] for k in range(20, 260, 12)]
        evs += [[days[k], '08:00', '8-K', '1.01,9.01', f'Deal {k}', '', ['deal'], f'001-{k}'] for k in range(25, 260, 12)]
        w(hub / 'research' / 'paths' / 'moves' / 'n' / f'{t}.json', {'key': t, 'events': evs})
        trades = [[days[k], f'i:{k % 4}', f'Insider {k % 4}', 'ins', 1 if (k // 9) % 3 else -1, 2e6 if (k // 9) % 2 else 5e4, 0.02 if k % 5 else -0.01, None, None, days[k]] for k in range(30, 280, 9)]
        w(hub / 'smart' / 't' / f'{t}.json', {'ticker': t, 'trade_fields': ['date', 'actor', 'name', 'group', 'd', 'size', 'ex', 'ex2', 'follow', 'known'], 'trades': trades})
        w(hub / 'holders' / f'{t}.json', {'form144': [{'sale_date': days[200], 'value': 3e6, 'seller_name': 'A Director'}]})
        w(hub / 'research' / 'earnings' / 'c' / f'{t}.json', {'history': [{'reported': days[100], 'surprise': .05, 'beat': 1}, {'reported': days[160], 'surprise': -.02, 'beat': 0}]})
    w(s / 'data' / 'index.json', {'companies': [{'cik': 1, 'ticker': 'AAA', 'name': 'ALPHA INC', 'revenue': 1e9}, {'cik': 2, 'ticker': 'BBB', 'name': 'BETA CORP', 'revenue': 2e9}]})
    for sl in ('aaa', 'bbb'):
        (s / 'c' / sl).mkdir(parents=True)
        (s / 'c' / sl / 'index.html').write_text('<nav class="seo-toc" aria-label="On this page"></nav>')
    return s


def test_stats_and_pages(tmp_path):
    s = site(tmp_path)
    ev, ins = ES.write(str(s))
    assert ev['companies'] == 2 and ev['items']['5.02']['h1']['n'] == 40 and ev['items']['1.01']['name'] == 'Material definitive agreement'
    assert abs(ev['items']['5.02']['h1']['median'] - 0.002) < 1e-6 and ev['items']['5.02']['h1']['up'] == 1 and ev['sets']['5.02']['h21']['n'] == 40
    assert abs(ev['items']['1.01']['h1']['excess_median'] - 0.001) < 1e-6 and 'deal' in ev['topics']
    p = ins['patterns']
    assert p['buy']['n'] + p['sell']['n'] == ins['trades'] and p['buy_large']['n'] + p['buy_small']['n'] == p['buy']['n'] and p.get('buy_cluster', p.get('buy_lone'))['n'] <= p['buy']['n'] and p['buy_large']['hit'] > p['buy_small']['hit'] - 1
    assert 0 < p['buy']['hit'] < 1 and 0 <= p['sell']['hit'] <= 1
    assert T.write(str(s), 'https://example.com') == 3
    page = (s / 'c' / 'aaa' / 'timeline' / 'index.html').read_text()
    assert 'Alpha stock timeline' in page and 'Insider buy' in page and ('Form 144: A Director plans to sell ' + seo.money(3e6)) in page and 'Officer change' in page
    assert "href='../report-card/'" not in page                       # no report card for this company: no link to one
    assert 'What this kind of 8-K usually did' in page and '<b>5.02</b>' in page and 'Insiders’ record here' in page and 'old enough to score' in page
    assert 'href="timeline/"' in (s / 'c' / 'aaa' / 'index.html').read_text()
    sig = (s / 'disclosures' / 'insider-signals' / 'index.html').read_text()
    assert 'Do insider trades predict the stock?' in sig and 'Cluster buys' in sig and 'c/aaa/timeline/' in sig
    sm = (s / 'sitemap-timelines.xml').read_text()
    assert sm.count('<url>') == 3 and 'sitemap-timelines.xml' in (s / 'robots.txt').read_text()
    # the hub's event pages and the impact page draw on the same statistics
    assert H.impact_page(str(s), 'https://example.com', ev).endswith('/events/impact/')
    imp = (s / 'events' / 'impact' / 'index.html').read_text()
    assert 'Which 8-K items move stocks?' in imp and '<b>5.02</b>' in imp and 'Item combinations' in imp
    u = H.usually(['5.02', '9.01'], ev)
    assert 'What usually follows' in u and '40</b> 8-Ks reporting Item 5.02' in u and H.usually(['9.01'], ev) == '' and H.usually(['5.02'], None) == ''
