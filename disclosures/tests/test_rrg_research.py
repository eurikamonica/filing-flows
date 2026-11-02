"""Rotation research (app/rrg_research.py): the RRG at any frequency equals the chart's (weekly: transition_rrg's), the
counts of crossings, turn-backs and lagging rebounds on a hand-made path, an outcome past the end of the data is never
counted, the browser (docs/rrg-lab.js) gets the same numbers from the same lines, and the weekly and daily files have
what the hub reads."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
try:
    import numpy as np
    import rrg_research as R
    import transition_rrg as TR
except ImportError:                                          # numpy is part of the analysis extras
    np = None


def walk(rng, n, s, lines=1):
    return 100 * np.exp(np.cumsum(rng.normal(0, s, (lines, n)), 1))


@unittest.skipIf(np is None, 'numpy not installed')
class Formula(unittest.TestCase):
    def test_weekly_equals_the_transition_model(self):
        rng = np.random.default_rng(5)
        rs = walk(rng, 400, .03, 5)
        rs[1, 50:53] = np.nan
        a, b = TR.rrg_states(rs), R.states(rs, 14, 4, 52, 26)
        for k in ('x', 'y', 's', 't', 'dev', 'roc'):
            np.testing.assert_array_equal(np.isnan(a[k]), np.isnan(b[k]))
            np.testing.assert_allclose(np.nan_to_num(a[k]), np.nan_to_num(b[k]), atol=1e-12)

    def test_daily_parameters(self):
        rs = walk(np.random.default_rng(2), 600, .01)
        S = R.states(rs, 21, 5, 252, 126)
        self.assertEqual((S['sh'], S['n'], S['long']), (5, 21, 252))
        first = int(np.argmax(np.isfinite(S['x'][0])))
        self.assertGreaterEqual(first, 126)                    # at least 126 days of the gap on file before it is scaled

    def test_quadrants(self):
        q = R.quadrants(np.array([[101, 101, 99, 99, np.nan]]), np.array([[101, 99, 99, 101, 100]]))
        self.assertEqual(q[0].tolist(), [0, 1, 2, 3, -1])


@unittest.skipIf(np is None, 'numpy not installed')
class Counts(unittest.TestCase):
    def path(self):
        """One line, by hand: Improving near the RS-Ratio line and moving toward it (week 1), turns back (week 3), comes
        again (week 5), crosses into Leading (week 7); falls into Weakening (week 9), into Lagging (week 10), rebounds to
        Improving (week 13) and heads for the line again (week 14, the last)."""
        x = [99.5, 99.6, 99.4, 99.0, 99.2, 99.5, 99.8, 100.3, 100.6, 100.4, 99.6, 99.0, 98.7, 98.9, 99.3]
        y = [100.5, 100.6, 100.4, 100.2, 100.4, 100.6, 100.7, 100.6, 100.2, 99.6, 99.4, 99.3, 99.6, 100.2, 100.5]
        x, y = np.array([x]), np.array([y])
        C = np.array([np.linspace(100, 114, 15)])
        B = np.full((1, 15), 100.0)
        return x, y, C, B, np.datetime64('2020-01-03') + 7 * np.arange(15)

    def test_hand_made_path(self):
        x, y, C, B, days = self.path()
        r = R.research(x, y, C, B, days, horizons=(1, 2, 4), unit='weeks')
        b = {v['key']: v for v in r['boundaries']}
        il = b['improving_to_leading']
        self.assertEqual(il['episodes'], 3)                       # weeks 1, 4 and 14 (each run of approaching weeks once)
        self.assertEqual(il['crossed']['1'], {'hits': 0, 'n': 2, 'share': 0.0})   # week 14 is the last: not seen
        self.assertEqual(il['crossed']['4']['hits'], 1)           # week 4 → over at week 7; week 1 turned back
        self.assertEqual(il['periods_to_cross']['median'], 3)
        self.assertEqual(il['landed_in_target'], {'hits': 1, 'n': 1, 'share': 1.0})
        lag = r['lagging']
        self.assertEqual(lag['entries'], 1)                       # week 10
        self.assertEqual(lag['improving']['4'], {'hits': 1, 'n': 1, 'share': 1.0})
        self.assertEqual(lag['improving']['2'], {'hits': 0, 'n': 1, 'share': 0.0})
        self.assertEqual(lag['periods_to_improving']['median'], 3)
        self.assertAlmostEqual(lag['lowest_rs_ratio']['median'], 98.7, places=1)
        self.assertEqual(r['direction'], {'changes': 4, 'clockwise': 1.0, 'counter_clockwise': 0.0, 'across': 0.0})
        self.assertEqual(r['dwell']['leading']['median'], 2)      # weeks 7-8; the first and last runs are not complete
        self.assertEqual(r['lines'], 1)

    def test_an_outcome_past_the_end_is_not_counted(self):
        x, y, C, B, days = self.path()
        r = R.research(x[:, :13], y[:, :13], C[:, :13], B[:, :13], days[:13], horizons=(1, 2, 4), unit='weeks')
        self.assertEqual(r['lagging']['entries'], 1)
        self.assertEqual(r['lagging']['improving']['4']['n'], 0)  # week 10 + 4 is past the end: unknown, not a miss
        self.assertEqual(r['lagging']['improving']['2']['n'], 1)  # week 12 is on file: two weeks seen, still Lagging

    def test_chunks_add_up(self):
        rng = np.random.default_rng(9)
        C = walk(rng, 500, .04, 12); B = np.broadcast_to(walk(rng, 500, .02), C.shape)
        S = R.states(100 * C / B, 14, 4, 52, 26)
        days = np.datetime64('2010-01-01') + 7 * np.arange(500)
        whole = R.research(S['x'], S['y'], C, B, days)
        acc = R.Research(R.H_W, 'weeks')
        for i in (0, 5):
            acc.add(S['x'][i:i + 5 + 2 * (i > 0)], S['y'][i:i + 5 + 2 * (i > 0)], C[i:i + 5 + 2 * (i > 0)], B[i:i + 5 + 2 * (i > 0)], days)
        self.assertEqual(json.dumps(acc.to_json(), sort_keys=True), json.dumps(whole, sort_keys=True))


@unittest.skipIf(np is None or shutil.which('node') is None, 'numpy or node not installed')
class SameInTheBrowser(unittest.TestCase):
    """docs/rrg-lab.js research() on the same lines gives the same counts, shares and medians."""

    def test_python_and_javascript_agree(self):
        rng = np.random.default_rng(21)
        W = 700
        C = walk(rng, W, .035, 6)
        C[2, :120] = np.nan                                       # a late start
        C[3, 300:304] = np.nan                                    # a gap: the averages restart
        Bm = walk(rng, W, .015)
        B = np.broadcast_to(Bm, C.shape)
        with np.errstate(invalid='ignore'):
            S = R.states(100 * C / B, 14, 4, 52, 26)
        days = [str(d) for d in np.datetime64('2008-01-04') + 7 * np.arange(W)]
        py = R.research(S['x'], S['y'], C, B, np.array(days, dtype='datetime64[D]'))
        nul = lambda a: [None if not np.isfinite(v) else float(v) for v in a]
        lines = [{'x': nul(S['x'][i]), 'y': nul(S['y'][i]), 'c': nul(C[i]), 'b': nul(B[i])} for i in range(len(C))]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'lines.json'
            f.write_text(json.dumps({'lines': lines, 'days': days}))
            js = subprocess.run(['node', '-e', "const L=require(process.argv[1]);const d=require(process.argv[2]);"
                                 "process.stdout.write(JSON.stringify(L.research(d.lines,d.days,[1,4,13,26],'weeks')))",
                                 str(ROOT / 'docs' / 'rrg-lab.js'), str(f)], capture_output=True, text=True, check=True)
        jv = json.loads(js.stdout)

        def same(a, b, where):
            if isinstance(a, dict):
                self.assertEqual(set(a), set(b), where)
                for k in a:
                    same(a[k], b[k], where + '.' + k)
            elif isinstance(a, list):
                self.assertEqual(len(a), len(b), where)
                for i, (u, v) in enumerate(zip(a, b)):
                    same(u, v, f'{where}[{i}]')
            elif isinstance(a, float) or isinstance(b, float):
                self.assertAlmostEqual(a, b, delta=1.5e-4, msg=where)
            else:
                self.assertEqual(a, b, where)
        for k in ('lines', 'from', 'to', 'transitions', 'boundaries', 'lagging', 'quadrants', 'dwell', 'direction', 'cycles'):
            same(py[k], jv[k], k)
        self.assertGreater(py['lagging']['entries'], 50)
        self.assertGreater(sum(b['episodes'] for b in py['boundaries']), 200)


@unittest.skipIf(np is None, 'numpy not installed')
class Files(unittest.TestCase):
    def test_weekly_file(self):
        rng = np.random.default_rng(11)
        W = 600
        g0 = np.datetime64('2010-01-01')
        weeks = str(g0 + np.timedelta64(7 * (W - 1), 'D'))
        w = lambda s: walk(rng, W, s)[0].round(4).tolist()
        with tempfile.TemporaryDirectory() as tmp:
            pub = Path(tmp)
            (pub / 't').mkdir()
            series = [{'id': f'X{i}', 'name': f'X{i}', 'group': 'sector-etf', 'start': str(g0), 'c': w(.03)} for i in range(4)]
            series += [{'id': t, 'name': t, 'group': 'style-etf', 'start': str(g0), 'c': w(.03)} for t in ('QQQ', 'IWM', 'GLD')]
            tickers = {}
            for i in range(6):
                t = f'C{i}'
                tickers[t] = {'n': t, 's': 'x'}
                doc = {'t': t, 'start': str(g0), 'c': w(.04), 'v': [5000] * W}
                if i < 4:
                    doc.update(bx=w(.03), bi=w(.03))
                (pub / 't' / f'{t}.json').write_text(json.dumps(doc))
            (pub / 'rrg.json').write_text(json.dumps({'start': str(g0), 'weeks': weeks, 'bench': {'start': str(g0), 'c': w(.02)},
                                                      'series': series, 'tickers': tickers}))
            (pub / 'industries.json').write_text(json.dumps({'rows': [{'id': f'sic4:{i}', 'start': str(g0), 'c': w(.03)} for i in range(3)]}))
            R.build_weekly(pub, verbose=False)
            doc = json.loads((pub / 'rrg-research.json').read_text())
        self.assertEqual(doc['schema'], 'rrg_research.v1')
        self.assertEqual(doc['rrg'], {'sh': 4, 'n': 14, 'long': 52, 'min_norm': 26})
        g = doc['groups']
        self.assertEqual({k: v['lines'] for k, v in g.items()},
                         {'sectors': 4, 'index_etfs': 2, 'styles': 1, 'industries': 3, 'companies': 6, 'companies_vs_industry': 4})
        s = g['sectors']
        self.assertEqual([b['key'] for b in s['boundaries']], [b[0] for b in R.BOUNDS])
        self.assertEqual(set(s['lagging']['improving']), {'1', '4', '13', '26'})
        self.assertEqual(len(s['lagging']['states']), 6)
        self.assertEqual(set(s['quadrants']['forward_vs_benchmark']), {'leading', 'weakening', 'lagging', 'improving', 'any'})

    def test_daily_file(self):
        rng = np.random.default_rng(4)
        import datetime as dt
        d0, days = dt.date(2004, 6, 1), []
        while len(days) < 1600:
            if d0.weekday() < 5:
                days.append(d0.isoformat())
            d0 += dt.timedelta(days=1)
        lv = lambda s: walk(rng, len(days), s)[0].tolist()
        data = {'SPY': (days, lv(.01), 500.0), 'XLK': (days, lv(.015), 200.0), 'XLE': (days, lv(.02), 90.0), 'QQQ': (days, lv(.013), 400.0),
                'EWJ': (days, lv(.012), 70.0), 'TLT': (days, lv(.01), 90.0), 'SMH': (days, lv(.02), 250.0), 'SIC-3674': (days, lv(.018), None),
                'AAA': (days[200:], lv(.03)[200:], 20.0)}
        miss = list(data['XLK'][0]); vals = list(data['XLK'][1])
        del miss[900], vals[900]                                  # a missing day: the close before
        data['XLK'] = (miss, vals, 200.0)
        assets = [{'key': 'SPY', 'kind': 'market', 'group': 'market'}, {'key': 'XLK', 'kind': 'sector', 'group': 'sector'},
                  {'key': 'XLE', 'kind': 'sector', 'group': 'sector'}, {'key': 'QQQ', 'kind': 'market', 'group': 'market'},
                  {'key': 'EWJ', 'kind': 'etf', 'group': 'country'}, {'key': 'TLT', 'kind': 'style', 'group': 'bonds'},
                  {'key': 'SMH', 'kind': 'style', 'group': 'industry'}, {'key': 'SIC-3674', 'kind': 'industry'}, {'key': 'AAA', 'kind': 'stock'},
                  {'key': 'IDX-VIX', 'kind': 'volatility', 'group': 'volatility'}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'rrg-research-daily.json'
            doc = R.build_daily(data, assets, out, chunk=1, verbose=False)
            back = json.loads(out.read_text())
        self.assertEqual(back['freq'], 'd')
        self.assertEqual(back['rrg'], {'sh': 5, 'n': 21, 'long': 252, 'min_norm': 126})
        self.assertEqual({k: v['lines'] for k, v in back['groups'].items()},
                         {'sectors': 2, 'index_etfs': 1, 'world': 1, 'bonds_commodities': 1, 'industry_etfs': 1, 'industries': 1, 'companies': 1})
        self.assertEqual(back['groups']['sectors']['horizons'], [1, 5, 21, 63])
        self.assertGreaterEqual(back['groups']['sectors']['from'], '2005-01-03')
        self.assertEqual(doc['groups']['sectors']['lines'], 2)
        self.assertIsNone(R.build_daily({'XLK': data['XLK']}, assets, Path('/nonexistent/x.json')))   # no SPY: nothing written


if __name__ == '__main__':
    unittest.main()
