"""Move odds headlines (app/move_headlines.py): the company's searchable name, the search for a day, the feed parsed, the
headlines kept (about the company, in the window, no automatic 13F notes, no junk sources, reputable first), the days
wanted (the last ones again, then the biggest moves), a run against a fake feed that stops when asked to slow down, and
the headlines published with the filings in New York time."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import move_headlines as H   # noqa: E402
import move_news as N        # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Apple shares fall after iPhone sales miss - Reuters</title><link>https://news.google.com/rss/articles/AAA?oc=5</link>
 <pubDate>Fri, 30 Oct 2026 13:05:00 GMT</pubDate><source url="https://www.reuters.com">Reuters</source></item>
<item><title>XYZ Capital Buys 1,200 Shares of Apple Inc. (NASDAQ:AAPL) - MarketBeat</title><link>https://news.google.com/rss/articles/BBB</link>
 <pubDate>Fri, 30 Oct 2026 09:00:00 GMT</pubDate><source url="https://www.marketbeat.com">MarketBeat</source></item>
<item><title>Vanguard Group Inc. Raises Stake in Apple (AAPL) - Somewhere</title><link>https://news.google.com/rss/articles/CCC</link>
 <pubDate>Fri, 30 Oct 2026 10:00:00 GMT</pubDate><source url="https://x.example">Somewhere</source></item>
<item><title>Why AAPL stock is moving today - The Motley Fool</title><link>https://news.google.com/rss/articles/DDD</link>
 <pubDate>Thu, 29 Oct 2026 21:30:00 GMT</pubDate><source url="https://www.fool.com">The Motley Fool</source></item>
<item><title>Pineapple prices jump in Hawaii - Local</title><link>https://news.google.com/rss/articles/EEE</link>
 <pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate><source url="https://l.example">Local</source></item>
<item><title>Apple earnings preview - Blog</title><link>https://news.google.com/rss/articles/FFF</link>
 <pubDate>Mon, 26 Oct 2026 12:00:00 GMT</pubDate><source url="https://b.example">Blog</source></item>
<item><title>Apple &amp; the services slowdown - CNBC</title><link>https://news.google.com/rss/articles/GGG</link>
 <pubDate>Fri, 30 Oct 2026 15:00:00 GMT</pubDate><source url="https://www.cnbc.com">CNBC</source></item>
</channel></rss>"""


class Pieces(unittest.TestCase):
    def test_names(self):
        self.assertEqual(H.short_name('Apple Inc.'), 'Apple')
        self.assertEqual(H.short_name('HALOZYME THERAPEUTICS, INC.'), 'Halozyme Therapeutics')
        self.assertEqual(H.short_name('ACME CORP /DE/'), 'Acme')
        self.assertEqual(H.short_name('Alphabet Inc. (Class A)'), 'Alphabet')
        self.assertEqual(H.keys_of('General Motors Co', 'GM'), (['General Motors'], 'GM'))
        self.assertEqual(H.keys_of('Apple Inc.', 'AAPL'), (['Apple'], 'AAPL'))

    def test_query(self):
        q = H.query('Apple Inc.', 'AAPL', '2026-10-30')
        self.assertEqual(q, '("Apple" OR "AAPL stock" OR "(AAPL)") after:2026-10-29 before:2026-10-31')
        self.assertIn('"stock market"', H.query('the market', 'SPY', '2026-10-30'))

    def test_parse_and_keep(self):
        items = H.parse(RSS.encode())
        self.assertEqual(items[0][:3], ['2026-10-30T13:05Z', 'Reuters', 'Apple shares fall after iPhone sales miss'])
        self.assertEqual(items[6][2], 'Apple & the services slowdown')
        kept = H.keep(items, 'Apple Inc.', 'AAPL', '2026-10-30')
        titles = [k[2] for k in kept]
        self.assertEqual(titles[:2], ['Apple shares fall after iPhone sales miss', 'Apple & the services slowdown'])   # reputable, about the move, first
        self.assertIn('Why AAPL stock is moving today', titles)                 # the ticker, the day before
        self.assertNotIn('XYZ Capital Buys 1,200 Shares of Apple Inc. (NASDAQ:AAPL)', titles)   # a 13F note from a junk source
        self.assertNotIn('Vanguard Group Inc. Raises Stake in Apple (AAPL)', titles)          # a 13F note
        self.assertNotIn('Pineapple prices jump in Hawaii', titles)              # not about the company
        self.assertNotIn('Apple earnings preview', titles)                       # outside the two days (and a day either side)
        self.assertEqual(len(H.keep(items, 'the market', 'SPY', '2026-10-30')), 4)   # the market: every in-window non-note

    def test_windows_wanted(self):
        days = [(dt.date(2023, 1, 2) + dt.timedelta(days=i)).isoformat() for i in range(1400)]
        days = [d for d in days if dt.date.fromisoformat(d).weekday() < 5]
        closes = [100 * math.exp(0.0005 * i) for i in range(len(days))]
        closes[500] = closes[499] * 0.8                                         # a big fall
        for i in range(501, len(closes)):
            closes[i] = closes[500] * math.exp(0.0005 * (i - 500))
        today = dt.date.fromisoformat(days[-1])
        w = H.wanted({'days': {}, 'windows': []}, days, closes, today)
        self.assertEqual(w[0], ((today - dt.timedelta(days=6)).isoformat(), today.isoformat()))   # the last week
        self.assertEqual(w[1], (today.replace(day=1).isoformat(), today.isoformat()))             # this month so far
        self.assertIn(((dt.date.fromisoformat(days[500]) - dt.timedelta(days=1)).isoformat(), days[500]), w)   # the big fall
        self.assertNotIn(w[0], H.wanted({'days': {}, 'windows': []}, days, closes, today, recent=False))
        # a month searched to the end is not asked again; a full one is (by its halves, queued when it came back)
        m = H.months_back(today)[3]
        done = {'windows': [[m[0], m[1], '2026-01-01T00:00Z', 40]]}
        self.assertNotIn(m, H.wanted(done, days, closes, today))
        self.assertTrue(all(d in H.checked_days(done, days) for d in days if m[0] <= d <= m[1]))
        full = {'windows': [[m[0], m[1], '2026-01-01T00:00Z', 100]]}
        self.assertFalse(any(m[0] <= d <= m[1] for d in H.checked_days(full, days)))

    def test_trading_day(self):
        days = ['2026-10-29', '2026-10-30', '2026-11-02']
        self.assertEqual(H.trading_day(days, '2026-10-29T19:00Z'), '2026-10-29')   # 15:00 New York
        self.assertEqual(H.trading_day(days, '2026-10-29T21:00Z'), '2026-10-30')   # 17:00: the next day
        self.assertEqual(H.trading_day(days, '2026-10-31T15:00Z'), '2026-11-02')   # a Saturday
        self.assertEqual(H.trading_day(days, '2026-10-30T07:00Z'), '2026-10-30')   # dated only
        self.assertIsNone(H.trading_day(days, '2026-11-03T15:00Z'))


class Run(unittest.TestCase):
    def test_refresh_publish_and_slow_down(self):
        class Feed:
            def __init__(self, fail_after=None, full_for=None):
                self.urls, self.fail_after, self.full_for = [], fail_after, full_for

            def get(self, url, headers=None):
                u = unquote(url)
                self.urls.append(u)
                if self.fail_after is not None and len(self.urls) > self.fail_after:
                    raise RuntimeError('HTTP 429 from news.google.com')
                if self.full_for and self.full_for in u:                   # a month the feed fills to the brim
                    extra = ''.join(f'<item><title>Apple note {i}</title><link>https://news.google.com/rss/articles/Z{i}</link><pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate><source url="https://x">X</source></item>' for i in range(100))
                    return RSS.replace('</channel>', extra + '</channel>').encode()
                return RSS.encode()
        days = [(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(669)]
        days = [d for d in days if dt.date.fromisoformat(d).weekday() < 5]
        closes = [100 * math.exp(0.002 * math.sin(i)) for i in range(len(days))]
        bars = lambda t: (days, closes)                                          # noqa: E731
        today = dt.date(2026, 10, 31)
        with tempfile.TemporaryDirectory() as d:
            f = Feed(full_for='after:2026-10-01 before:2026-11-01')
            st = H.refresh(f, d, [{'t': 'AAPL', 'name': 'Apple Inc.'}], bars, queries=12, today=today)
            self.assertEqual(st['searched'], 12)                                 # six windows each a round: the market, then the company
            self.assertIn('q=("stock market"', f.urls[0])                       # the market first
            self.assertTrue(any('"Apple"' in u and 'after:2026-10-25 before:2026-11-01' in u for u in f.urls))   # the last week
            self.assertGreaterEqual(st.get('split', 0), 1)                      # October came back full: its halves next
            doc = json.loads((Path(d) / 'cache' / 'headlines' / 'AAPL.json').read_text())
            self.assertEqual(doc['days']['2026-10-30'][0][2], 'Apple shares fall after iPhone sales miss')   # 13:05 GMT: that day
            self.assertIn('Why AAPL stock is moving today', [x[2] for x in doc['days']['2026-10-30']])     # 17:30 the day before: the next day
            self.assertTrue(any(w[3] >= H.FULL for w in doc['windows']))
            # published with the filings
            self.assertEqual(N.publish(d, [{'t': 'AAPL', 'cik': None}], bars), 2)   # the market and the company
            pub = json.loads((Path(d) / 'public' / 'moves' / 'n' / 'AAPL.json').read_text())
            row = next(r for r in pub['headlines'] if r[4] == 'Why AAPL stock is moving today')
            self.assertEqual(row[:4], ['2026-10-30', '2026-10-29', '17:30', 'The Motley Fool'])   # 21:30 GMT = 17:30 EDT
            self.assertIn('2026-10-30', pub['checked'])
            self.assertEqual(pub['events'], [])
            self.assertTrue((Path(d) / 'public' / 'moves' / 'n' / 'SPY.json').exists())
            # asked to slow down: the run stops
            g = Feed(fail_after=1)
            st2 = H.refresh(g, d, [{'t': 'AAPL', 'name': 'Apple Inc.'}], bars, queries=50, today=dt.date(2026, 11, 20))
            self.assertTrue(st2['blocked'])
            self.assertEqual(len(g.urls), 2)

    def test_ranking(self):
        items = [['2026-10-30T12:00Z', 'Yahoo Finance', "Here's How Much a $1000 Investment in Apple Made 10 Years Ago Would Be Worth", 'https://a'],
                 ['2026-10-30T12:05Z', 'Some Blog', 'Apple stock jumps after earnings beat', 'https://b'],
                 ['2026-10-30T12:10Z', 'Reuters', 'Apple names new design chief', 'https://c']]
        self.assertEqual([k[1] for k in H.keep(items, 'Apple Inc.', 'AAPL', '2026-10-30')], ['Reuters', 'Some Blog', 'Yahoo Finance'])

    def test_new_york_time(self):
        self.assertEqual(H._et('2022-10-26T07:00Z'), ('2022-10-26', ''))         # dated only by the feed
        self.assertEqual(H._et('2026-01-15T14:30Z'), ('2026-01-15', '09:30'))   # EST
        self.assertEqual(H._et('2026-07-15T03:10Z'), ('2026-07-14', '23:10'))   # EDT, the day before


if __name__ == '__main__':
    unittest.main()
