"""app/moves_close.py (move odds at the close): the day after the nightly run's files added from Yahoo's daily bars gives
the numbers a full rebuild with that day gives; a session still open adds nothing; industries from their members; the
VIX term structure; when a close is due."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import moves as M  # noqa: E402
import moves_close as C  # noqa: E402
import paths as P  # noqa: E402


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def ts(day, hh=14, mm=30):
    return int(dt.datetime.fromisoformat(f'{day}T{hh:02d}:{mm:02d}:00+00:00').timestamp())


def chart(days, closes, adj=None, session=None):
    """Yahoo's daily chart answer for these days; `session`: the day whose regular hours (14:30-21:00 UTC) it reports."""
    adj = adj or closes
    s = session or days[-1]
    return {'chart': {'result': [{'meta': {'gmtoffset': 0, 'currentTradingPeriod': {'regular': {'start': ts(s), 'end': ts(s, 21, 0)}}},
                                  'timestamp': [ts(d) for d in days],
                                  'indicators': {'quote': [{'open': closes, 'high': closes, 'low': closes, 'close': closes, 'volume': [100] * len(days)}],
                                                 'adjclose': [{'adjclose': adj}]}}]}}


class Fixture:
    """Bars for the market, an index, two volatility indices and six companies of one industry: the nightly run's files
    on all days but the last (base), and on every day (full)."""

    def __init__(self, tmp):
        self.days = weekdays('2024-01-02', 401)
        rng = np.random.default_rng(7)
        self.bars = {}
        for t in ('SPY', 'XLK', 'IDX-GSPC'):
            self.bars[t] = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(self.days)))))
        self.bars['IDX-VIX'] = list(20 * np.exp(np.cumsum(rng.normal(0, 0.05, len(self.days)))))
        self.bars['IDX-VIX3M'] = list(22 * np.exp(np.cumsum(rng.normal(0, 0.03, len(self.days)))))
        rows = []
        self.val = Path(tmp) / 'val'
        (self.val / 'c').mkdir(parents=True)
        for i in range(6):
            t = f'CO{i}'
            self.bars[t] = list(50 * np.exp(np.cumsum(rng.normal(0, 0.02, len(self.days)))))
            rows.append([1000 + i, t, f'COMPANY {i} INC', 'technology', 'industrial', 1e9 * (10 - i)])
            (self.val / 'c' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'industry': 'Semiconductors', 'sic': '3674'}, indent=2))
        (self.val / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'], 'rows': rows}))
        self.base = self.nightly(Path(tmp) / 'base', len(self.days) - 1)
        self.full = self.nightly(Path(tmp) / 'full', len(self.days))

    def nightly(self, root, n):
        for t, closes in self.bars.items():
            d = self.days[:n]
            P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00',
                             't': d, 'o': closes[:n], 'h': closes[:n], 'l': closes[:n], 'c': closes[:n], 'ac': closes[:n], 'v': [100] * n})
        st = M.build(root, self.val / 'index.json')
        assert st['errors'] == [], st['errors']
        return root / 'public' / 'moves'

    def yahoo(self, n=None, fail=()):
        """A stand-in for Yahoo's chart API: each asset's last 22 days (to day n)."""
        sym = {v: k for k, v in P.YAHOO_SYMBOL.items()}
        n = n or len(self.days)

        def get(s):
            k = sym.get(s, s)
            if k in fail or k not in self.bars:
                raise RuntimeError('HTTP 404')
            return chart(self.days[n - 22:n], self.bars[k][n - 22:n])
        return get


def rows_of(path):
    ix = json.loads((Path(path) / 'index.json').read_text())
    return ix, {r[0]: dict(zip(ix['fields'], r)) for r in ix['rows']}


NUMBERS = ['as_of', 'n', 'last', 'move', 'pct', 'z', 'zpct', 'every', 'last_as', 'move5', 'pct5', 'move21', 'pct21'] + \
    [f'{s}{h}' for s in ('sim', 'ext', 'all') for h in M.HORIZONS] + ['back', 'high', 'rv21', 'rvpct', 'level', 'lpct', 'out5', 'out21']


class Close(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.F = Fixture(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_day_added_as_a_rebuild_would_have_it(self):
        out = Path(self.tmp.name) / 'live'
        st = C.run(self.F.base, out, workers=2, get=self.F.yahoo(), now_ts=ts(self.F.days[-1], 23, 0), log=lambda *a: None)
        self.assertEqual(st['errors'], [])
        self.assertEqual((st['as_of'], st['base_as_of']), (self.F.days[-1], self.F.days[-2]))
        ix, got = rows_of(out)
        _, want = rows_of(self.F.full)
        self.assertEqual(set(got), set(want))
        for k in want:
            if k == 'SIC-3674':
                continue                                   # from its members' rounded returns: below
            for f in NUMBERS:
                self.assertEqual(got[k][f], want[k][f], f'{k} {f}')
        # the industry: its members' clipped mean, within a basis point of the rebuild's
        self.assertEqual(got['SIC-3674']['as_of'], self.F.days[-1])
        self.assertLess(abs(got['SIC-3674']['move'] - want['SIC-3674']['move']), 2e-4)
        self.assertEqual(ix['close']['base_as_of'], self.F.days[-2])
        self.assertEqual(ix['breadth'], json.loads((self.F.full / 'index.json').read_text())['breadth'])
        # each file carries the day, encoded as the nightly run encodes it, and the rest of the file as it was
        for k in ('CO0', 'IDX-VIX', 'VIX-TERM', 'SPY'):
            a = json.loads((out / 'a' / f'{k}.json').read_text())
            b = json.loads((self.F.full / 'a' / f'{k}.json').read_text())
            self.assertEqual({x: a[x] for x in ('d0', 'r', 'as_of')}, {x: b[x] for x in ('d0', 'r', 'as_of')}, k)
            self.assertAlmostEqual(a['last'], b['last'], delta=1e-5 * abs(b['last']))     # Yahoo's six digits
            self.assertEqual(a['links'], b['links'])

    def test_a_session_still_open_adds_nothing(self):
        out = Path(self.tmp.name) / 'open'
        st = C.run(self.F.base, out, workers=2, get=self.F.yahoo(), now_ts=ts(self.F.days[-1], 19, 0), log=lambda *a: None)
        self.assertEqual((st['updated'], st['as_of']), (0, self.F.days[-2]))
        self.assertEqual((out / 'a' / 'SPY.json').read_bytes(), (self.F.base / 'a' / 'SPY.json').read_bytes())

    def test_an_asset_yahoo_does_not_answer_waits(self):
        out = Path(self.tmp.name) / 'partial'
        st = C.run(self.F.base, out, workers=2, get=self.F.yahoo(fail=('CO3', 'IDX-VIX3M')), now_ts=ts(self.F.days[-1], 23, 0), log=lambda *a: None)
        _, got = rows_of(out)
        self.assertEqual(got['CO3']['as_of'], self.F.days[-2])        # left as the nightly run had it
        self.assertEqual(got['VIX-TERM']['as_of'], self.F.days[-2])   # needs both
        self.assertEqual(got['SIC-3674']['as_of'], self.F.days[-1])   # five of six members: enough
        self.assertEqual(got['CO0']['as_of'], self.F.days[-1])
        self.assertTrue(any(e.startswith('CO3') for e in st['errors']))

    def test_too_few_companies_publish_nothing(self):
        out = Path(self.tmp.name) / 'few'
        with self.assertRaisesRegex(RuntimeError, 'only 4 of 6 companies'):
            C.run(self.F.base, out, workers=2, get=self.F.yahoo(fail=('CO4', 'CO5')), now_ts=ts(self.F.days[-1], 23, 0), log=lambda *a: None)
        self.assertFalse((out / 'index.json').exists())


class Pieces(unittest.TestCase):
    def test_new_returns(self):
        b = {'t': ['2026-11-05', '2026-11-06', '2026-11-09'], 'ac': [10.0, 11.0, 12.1], 'c': [10.0, 11.0, 12.1]}
        r = C.new_returns(['2026-11-04', '2026-11-05'], b)
        self.assertEqual([d for d, _ in r], ['2026-11-06', '2026-11-09'])
        self.assertAlmostEqual(r[0][1], math.log(1.1))
        self.assertEqual(C.new_returns(['2026-10-01'], b), [])         # the bars do not reach back: the nightly run's
        self.assertEqual(C.new_returns(['2026-11-05'], dict(b, ac=[10.0, 400.0, 401.0])), [])   # a bad print

    def test_composite_needs_most_members(self):
        doc = {'as_of': '2026-11-06'}
        mem = [{'key': f'M{i}', 'days_set': {'2026-11-06'}} for i in range(10)]
        add = {f'M{i}': [('2026-11-09', 0.01)] for i in range(5)}
        self.assertEqual(C.composite_returns(doc, mem, add), [])        # 5 of 10: under 60%
        add.update({f'M{i}': [('2026-11-09', 0.02)] for i in range(5, 7)})
        (d, r), = C.composite_returns(doc, mem, add)
        self.assertEqual(d, '2026-11-09')
        self.assertAlmostEqual(r, math.log1p((5 * math.expm1(0.01) + 2 * math.expm1(0.02)) / 7))

    def test_due(self):
        end = ts('2026-11-09', 21, 0)
        live = {'as_of': '2026-11-06', 'built_at': '2026-11-07T03:00:00+00:00'}
        ok, why = C.due(live, {'as_of': '2026-11-06'}, ('2026-11-09', end), now_ts=end + 900)
        self.assertTrue(ok, why)
        self.assertFalse(C.due(live, {'as_of': '2026-11-09'}, ('2026-11-09', end), now_ts=end + 900)[0])   # the nightly run has it
        early = {'as_of': '2026-11-09', 'built_at': dt.datetime.fromtimestamp(end + 700, dt.timezone.utc).isoformat()}
        self.assertFalse(C.due(early, None, ('2026-11-09', end), now_ts=end + 1200)[0])
        self.assertTrue(C.due(early, None, ('2026-11-09', end), now_ts=end + 3000)[0])     # once more, for the closing prints
        late = dict(early, built_at=dt.datetime.fromtimestamp(end + 3100, dt.timezone.utc).isoformat())
        self.assertFalse(C.due(late, None, ('2026-11-09', end), now_ts=end + 6000)[0])

    def test_closed_bars(self):
        days = ['2026-11-05', '2026-11-06', '2026-11-09']
        p = chart(days, [1.0, 2.0, 3.0])
        self.assertEqual(C.closed_bars(p, now_ts=ts('2026-11-09', 20, 0))[0]['t'], days[:2])     # 3 pm New York: open
        self.assertEqual(C.closed_bars(p, now_ts=ts('2026-11-09', 21, 5))[0]['t'], days[:2])     # five minutes after: not yet final
        self.assertEqual(C.closed_bars(p, now_ts=ts('2026-11-09', 21, 15))[0]['t'], days)
        p = chart(days, [1.0, 2.0, 3.0], session='2026-11-10')                                   # the next session's hours
        self.assertEqual(C.closed_bars(p, now_ts=ts('2026-11-10', 15, 0))[0]['t'], days)


if __name__ == '__main__':
    unittest.main()
