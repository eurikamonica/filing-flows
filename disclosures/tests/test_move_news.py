"""app/move_news.py: the company filings next to the move odds — the filing list kept, the acceptance time in New York
time, the trading day a filing could move, the 8-Ks read around the big moves first, the published events."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import move_news as N  # noqa: E402

import datetime as _dt
DAYS = [d.isoformat() for d in (_dt.date(2026, 8, 3) + _dt.timedelta(days=i) for i in range(91)) if d.weekday() < 5]
# small moves but for a fall on the 30th (after the release filed on the 29th after the close) and a rise on the 14th
CLOSES = [100.0]
for d in DAYS[1:]:
    CLOSES.append(CLOSES[-1] * (0.90 if d == '2026-10-30' else 1.08 if d == '2026-10-14' else 1.0 + 0.001 * (len(CLOSES) % 3 - 1)))
SUB = {'cik': 1018724, 'filings': {'recent': {
    'accessionNumber': ['0001-26-000040', '0001-26-000038', '0001-26-000037', '0001-26-000030', '0001-26-000031', '0001-26-000029', '0001-26-000020'],
    'form': ['10-Q', '8-K', '4', '8-K', '424B5', '424B5', '8-K'],
    'filingDate': ['2026-10-30', '2026-10-29', '2026-10-28', '2026-10-14', '2026-10-14', '2026-10-14', '2026-10-05'],
    'acceptanceDateTime': ['2026-10-30T20:01:00.000Z', '2026-10-29T20:01:44.000Z', '2026-10-28T21:00:00.000Z', '2026-10-14T11:30:00.000Z',
                           '2026-10-14T12:00:00.000Z', '2026-10-14T13:00:00.000Z', '2026-10-05T14:00:00.000Z'],
    'items': ['', '2.02,9.01', '', '8.01,9.01', '', '', '9.01'],
}, 'files': []}}


class FakeClient:
    def __init__(self):
        self.asked = []

    def json(self, url, sec=False):
        self.asked.append(url)
        return SUB

    def get(self, url, sec=False):
        self.asked.append(url)
        return b''


class Lists(unittest.TestCase):
    def test_rows_kept_and_times_in_new_york(self):
        rows = N.submissions(FakeClient(), 1018724, '2026-01-01')
        forms = [r[1] for r in rows]
        self.assertNotIn('4', forms)                                  # insider forms left out
        self.assertEqual(forms.count('424B5'), 1)                     # one prospectus a day
        self.assertFalse(any(r[0] == '0001-26-000020' for r in rows))  # an 8-K with exhibits only
        r = next(r for r in rows if r[0] == '0001-26-000038')
        self.assertEqual(r[3], '16:01')                               # 20:01 UTC in October = 16:01 EDT
        self.assertEqual(N._et('2026-12-01T21:30:00.000Z'), '16:30')  # EST in December

    def test_the_trading_day_a_filing_could_move(self):
        self.assertEqual(DAYS[N.trading_day(DAYS, '2026-10-29', '16:01')], '2026-10-30')   # after the close: the next day
        self.assertEqual(DAYS[N.trading_day(DAYS, '2026-10-14', '07:30')], '2026-10-14')   # before the open: that day
        self.assertEqual(DAYS[N.trading_day(DAYS, '2026-10-10', '10:00')], '2026-10-12')   # a Saturday: the Monday
        self.assertEqual(N.trading_day(DAYS, '2026-10-30', '16:01'), -1)                   # after the last day on file


class Reads(unittest.TestCase):
    def test_the_big_days_first(self):
        doc = {'filings': N.submissions(FakeClient(), 1018724, '2026-01-01'), 'read': {}, 'tried': {}}
        big = N.big_days(DAYS, CLOSES)
        self.assertIn(DAYS.index('2026-10-30'), big)
        accs = N.to_read(doc, DAYS, CLOSES)
        self.assertEqual(accs[0], '0001-26-000038')                   # the earnings release before the fall
        self.assertIn('0001-26-000030', accs)                         # the 8.01 on the day of the rise

    def test_refresh_and_publish(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            def fake_read(client, cik, acc):
                calls.append(acc)
                return {'h': 'Amazon.com Announces Third Quarter Results', 'q': 'Net sales increased 12%.', 't': ['earnings'], 'g': 'raised'}
            old = N.read_8k
            N.read_8k = fake_read
            try:
                st = N.refresh(FakeClient(), d, [{'t': 'AMZN', 'cik': 1018724}], lambda t: (DAYS, CLOSES), subs=5, reads=5, today=__import__('datetime').date(2026, 10, 31))
            finally:
                N.read_8k = old
            self.assertEqual(st['lists'], 1)
            self.assertGreaterEqual(st['read'], 1)
            self.assertEqual(calls[0], '0001-26-000038')
            self.assertEqual(N.publish(d, [{'t': 'AMZN', 'cik': 1018724}], lambda t: (DAYS, CLOSES)), 1)
            pub = json.loads((Path(d) / 'public' / 'moves' / 'n' / 'AMZN.json').read_text())
            ev = next(e for e in pub['events'] if e[7] == '0001-26-000038')
            self.assertEqual(ev[:4], ['2026-10-29', '16:01', '8-K', '2.02,9.01'])
            self.assertEqual(ev[4], 'Amazon.com Announces Third Quarter Results')
            self.assertEqual(ev[8], 'raised')
            # a week later nothing is asked again; read 8-Ks are not read again
            calls.clear()
            N.read_8k = fake_read
            try:
                st2 = N.refresh(FakeClient(), d, [{'t': 'AMZN', 'cik': 1018724}], lambda t: (DAYS, CLOSES), subs=5, reads=5, today=__import__('datetime').date(2026, 11, 2))
            finally:
                N.read_8k = old
            self.assertEqual(st2['lists'], 0)
            self.assertNotIn('0001-26-000038', calls)


if __name__ == '__main__':
    unittest.main()
