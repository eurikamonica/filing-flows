"""macro_calendar.py: first prints and release days from ALFRED real-time periods, the FOMC calendar pages, the joined
market moves, and macro_history reading each figure as it was known that day."""
import datetime as dt, gzip, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import macro_calendar as MC
try:
    import numpy as np
    import macro_history as MH
except ImportError:
    np = None


def realtime(vintages):
    """ALFRED-style real-time rows from [(vintage day, {period: value})]: each vintage sets those periods' values from
    that day until the next vintage that changes them."""
    hist = {}                                                   # period -> [(start, value)]
    for day, upd in sorted(vintages):
        for o, v in upd.items():
            if not hist.get(o) or hist[o][-1][1] != v:
                hist.setdefault(o, []).append((day, v))
    rows = []
    for o, h in hist.items():
        for k, (s, v) in enumerate(h):
            e = (dt.date.fromisoformat(h[k + 1][0]) - dt.timedelta(days=1)).isoformat() if k + 1 < len(h) else '9999-12-31'
            rows.append([o, v, s, e])
    return rows


def month(y, m):
    return dt.date(y, m, 1).isoformat()


def payrolls():
    """A dump on 1999-01-08 (1998 back), then each month printed on the 5th of the next with the prior month revised
    up by 10; one revision-only day (an annual benchmark) on 2000-02-20."""
    v = [(f'1999-01-08', {month(1998, m): 1000.0 + 10 * m for m in range(1, 13)})]
    level = 1120.0
    for i in range(14):                                         # 1999-01 … 2000-02
        y, m = 1999 + i // 12, i % 12 + 1
        ny, nm = y + (m == 12), m % 12 + 1
        py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
        day = dt.date(ny, nm, 5).isoformat()
        prev_first = level
        level += 100.0
        v.append((day, {month(y, m): level, month(py, pm): prev_first + 10}))
    v.append(('2000-02-20', {month(1999, 6): 9999.0}))          # a revision-only day
    return realtime(v)


class FirstPrints(unittest.TestCase):
    def setUp(self):
        self.rt = MC.RealTime(payrolls(), 'm')

    def test_dump_has_no_first_print(self):
        self.assertEqual(self.rt.first_vintage, '1999-01-08')
        self.assertIsNone(self.rt.first(month(1998, 6)))       # came with the first vintage: not a release
        self.assertEqual(self.rt.first(month(1999, 3)), ('1999-04-05', 1420.0))

    def test_value_as_known_and_today(self):
        o = month(1999, 3)
        self.assertEqual(self.rt.value(o, '1999-04-05'), 1420.0)
        self.assertEqual(self.rt.value(o, '1999-05-04'), 1420.0)       # the day before the next release
        self.assertEqual(self.rt.value(o, '1999-05-05'), 1430.0)       # revised with April's print
        self.assertIsNone(self.rt.value(o, '1999-04-04'))              # not out yet
        self.assertEqual(self.rt.latest(o), 1430.0)

    def test_headline_is_change_on_the_prior_as_revised_that_day(self):
        ev = MC.series_events('PAYEMS', self.rt)
        e = ev['1999-04-05']
        self.assertEqual(e['kind'], 'first')
        self.assertEqual(e['period'], month(1999, 3))
        printed, head, prior, today, yoy, head_now = e['values']
        self.assertEqual((printed, prior, today), (1420.0, 1330.0, 1430.0))   # February revised from 1320 to 1330
        self.assertEqual(head, 90.0)
        self.assertEqual(head_now, 100.0)                                    # March 1430 − February 1330, as they stand now

    def test_revision_only_day_and_dump_day(self):
        ev = MC.series_events('PAYEMS', self.rt)
        self.assertNotIn('1999-01-08', ev)
        self.assertEqual(ev['2000-02-20']['kind'], 'revision')
        self.assertEqual(ev['2000-02-20']['period'], month(1999, 6))

    def test_late_first_value_is_not_a_print(self):
        rows = realtime([('2001-01-10', {month(2000, 11): 5.0}), ('2001-06-01', {month(2000, 12): 6.0})])
        rt = MC.RealTime(rows, 'm')
        self.assertIsNone(rt.first(month(2000, 12)))            # 152 days after the month: added later, not released

    def test_headlines(self):
        self.assertAlmostEqual(MC.headline('pct', 101.0, 100.0), 1.0)
        self.assertAlmostEqual(MC.headline('ann', 101.0, 100.0), 100 * (1.01 ** 4 - 1))
        self.assertEqual(MC.headline('lvl', 4.1, 4.0), 4.1)
        self.assertIsNone(MC.headline('pct', 1.0, None))


@unittest.skipIf(np is None, 'numpy not installed')
class Known(unittest.TestCase):
    def test_known_reads_the_vintage_of_the_day(self):
        rt = MC.RealTime(payrolls(), 'm')
        days = [dt.date(1999, 1, 7), dt.date(1999, 4, 4), dt.date(1999, 4, 5), dt.date(1999, 5, 4)]
        k = rt.known(days)
        self.assertTrue(np.isnan(k[0]))                         # before the first vintage
        self.assertEqual(k[1], 1320.0)                           # February as printed, on 4 Apr (revised on 5 Apr)
        self.assertEqual(k[2], 1420.0)                           # March, printed that day
        self.assertEqual(k[3], 1420.0)                           # not yet revised

    def test_macro_history_uses_first_prints(self):
        rows = realtime([('2010-01-08', {month(2009, m): 9.0 for m in range(1, 13)})] +
                        [(dt.date(2010, m + 1, 5).isoformat(), {month(2010, m): 9.0 + m / 10, month(2010, m - 1) if m > 1
                          else month(2009, 12): (9.0 + (m - 1) / 10 if m > 1 else 9.0) + 0.5}) for m in range(1, 10)])
        rt = {'UNRATE': MC.RealTime(rows, 'm')}
        latest = [(dt.date.fromisoformat(o), v) for o, v in sorted({r[0]: r[1] for r in sorted(rows, key=lambda r: r[2])}.items())]
        days = [dt.date(2010, 6, 30)]
        F_latest = MH.features({'UNRATE': latest}, days)
        F_rt = MH.features({'UNRATE': latest}, days, rt)
        self.assertAlmostEqual(F_rt['unrate'][0], 9.5)                  # May as printed on 5 June
        self.assertNotAlmostEqual(F_latest['unrate'][0], F_rt['unrate'][0])   # the latest vintage carries the revision
        F_before = MH.features({'UNRATE': latest}, [dt.date(2009, 6, 30)], rt)
        F_old = MH.features({'UNRATE': latest}, [dt.date(2009, 6, 30)])
        np.testing.assert_allclose(F_before['unrate'], F_old['unrate'], equal_nan=True)   # before ALFRED: as before


CURRENT = """
<div class="panel panel-default"><div class="panel-heading"><h4><a id="1">2026 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting"><div class="fomc-meeting__month col-xs-5"><strong>January</strong></div>
<div class="fomc-meeting__date col-xs-4">27-28</div><div><strong>Statement:</strong><br>
<a href="/monetarypolicy/files/monetary20260128a1.pdf">PDF</a> | <a href="/newsevents/pressreleases/monetary20260128a.htm">HTML</a>
<a href="/newsevents/pressreleases/monetary20260128a1.htm">Implementation Note</a></div>
<div><a href="/monetarypolicy/fomcpressconf20260128.htm">Press Conference</a></div>
<div class="fomc-meeting__minutes"><strong>Minutes:</strong> (Released February 18, 2026)</div></div>
<div class="row fomc-meeting"><div class="fomc-meeting__month col-xs-5"><strong>April/May</strong></div>
<div class="fomc-meeting__date col-xs-4">30-1*</div><div></div></div>
<div class="row fomc-meeting"><div class="fomc-meeting__month col-xs-5"><strong>June</strong></div>
<div class="fomc-meeting__date col-xs-4">16-17 (cancelled)</div><div></div></div>
</div>
<footer><a href="/monetarypolicy/fomcpressconf.htm">Press conferences</a></footer>
"""
YEAR_1996 = """
<div class="panel"><div class="panel-heading"><h5>January 30-31 Meeting - 1996</h5></div>
<p><a href="/fomc/19960131DEFAULT.htm">Statement</a></p><p><a href="/fomc/minutes/19960130.htm">Minutes</a> (Released March 29, 1996)</p></div>
<div class="panel"><div class="panel-heading"><h5>March 26 Meeting - 1996</h5></div><p>Minutes (Released May 24, 1996)</p></div>
"""
YEAR_2020 = """
<div class="panel"><h5>March 15 (unscheduled) Meeting - 2020</h5><p><a href="/newsevents/pressreleases/monetary20200315a.htm">Statement</a></p>
<a href="/monetarypolicy/fomcpresconf20200315.htm">Press Conference</a> Minutes (Released April 08, 2020)</div>
<div class="panel"><h5>March 17-18 (cancelled) Meeting - 2020</h5></div>
<div class="panel"><h5>March 23 (notation vote) - 2020</h5><a href="/newsevents/pressreleases/monetary20200323a.htm">Statement</a>
(Released March 23, 2020)</div>
<div class="panel"><h5>March 10 Conference Call - 2008</h5><p><a href="/newsevents/press/monetary/20080311a.htm">Statement</a></p></div>
"""


class Fomc(unittest.TestCase):
    def test_current_page(self):
        y = MC.parse_fomc_current(CURRENT)[2026]
        self.assertEqual([m['date'] for m in y], ['2026-01-28', '2026-05-01'])          # cancelled left out
        jan, may = y
        self.assertEqual((jan['kind'], jan['presser'], jan['minutes'], jan['time'], jan['ahead']),
                         ('meeting', True, '2026-02-18', '14:00', False))
        self.assertEqual((may['ahead'], may['sep'], may['presser']), (True, True, None))   # the footer's link not read

    def test_earlier_years(self):
        y96 = MC.parse_fomc_year(YEAR_1996, 1996)
        self.assertEqual([(m['date'], m['minutes'], m['time']) for m in y96], [('1996-01-31', '1996-03-29', '14:15')])
        y20 = MC.parse_fomc_year(YEAR_2020, 2020)
        self.assertEqual([(m['date'], m['kind'], m['minutes'], m['time']) for m in y20],
                         [('2020-03-15', 'unscheduled', '2020-04-08', None), ('2020-03-23', 'notation vote', None, None)])
        y08 = MC.parse_fomc_year(YEAR_2020, 2008)
        self.assertEqual([(m['date'], m['kind']) for m in y08], [('2008-03-11', 'conference call')])

    def test_statement_times(self):
        self.assertEqual(MC.fomc_time('2012-06-20', 'meeting', True), '12:30')
        self.assertEqual(MC.fomc_time('2012-08-01', 'meeting', False), '14:15')
        self.assertEqual(MC.fomc_time('2019-07-31', 'meeting', True), '14:00')
        self.assertIsNone(MC.fomc_time('2020-03-15', 'unscheduled', True))


class Markets(unittest.TestCase):
    def test_spy_returns_decode(self):
        doc = {'d0': '2024-01-02', 'gaps': '113', 'r': [10, -20, 5]}
        self.assertEqual(MC.spy_returns(doc), {'2024-01-03': 10, '2024-01-04': -20, '2024-01-07': 5})

    def test_yield_changes(self):
        obs = [(dt.date(2024, 1, 2), 4.30), (dt.date(2024, 1, 3), None), (dt.date(2024, 1, 4), 4.37)]
        self.assertEqual(MC.daily_changes(obs), {'2024-01-04': 7.0})

    def test_key_never_in_errors(self):
        self.assertNotIn('secret', MC._safe('https://api.stlouisfed.org/fred/x?series_id=A&api_key=secret&file_type=json'))


@unittest.skipIf(np is None, 'numpy not installed')
class Build(unittest.TestCase):
    def test_build_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rt_dir = root / 'cache' / 'macro-rt'
            MC.write_gz(rt_dir / 'PAYEMS.json.gz', {'sid': 'PAYEMS', 'release': {'id': 50, 'name': 'Employment Situation'},
                                                    'rows': payrolls()})
            cal = [dt.date(1999 + i // 12, i % 12 + 1, 5).isoformat() for i in range(1, 15)] + ['2000-12-08']
            cal.remove('1999-06-05')                                         # one print off the calendar
            (rt_dir / 'release-50.json').write_text(json.dumps({'id': 50, 'dates': cal + ['2099-01-01']}))
            fomc = root / 'cache' / 'fomc'
            fomc.mkdir(parents=True)
            (fomc / '1999.json').write_text(json.dumps([{'date': '1999-05-18', 'kind': 'meeting', 'sep': False,
                                                         'presser': False, 'minutes': None, 'time': '14:15'}]))
            (fomc / 'current.json').write_text(json.dumps({'2000': [{'date': '2000-12-19', 'kind': 'meeting', 'sep': True,
                                                                     'presser': None, 'minutes': None, 'time': '14:15', 'ahead': True}]}))
            macro = root / 'cache' / 'macro'
            macro.mkdir(parents=True)
            days = [dt.date(1999, 1, 1) + dt.timedelta(days=i) for i in range(500)]
            for sid, base in (('DGS2', 5.0), ('DGS10', 5.5)):
                (macro / f'{sid}.csv').write_text('observation_date,' + sid + '\n' + '\n'.join(
                    f'{x.isoformat()},{base + 0.01 * (i % 7):.2f}' for i, x in enumerate(days)))
            spy = {'d0': '1999-01-04', 'dates': [x.isoformat() for x in days[3:]], 'r': [(-1) ** i * (50 if (x.day == 5) else 10)
                                                                                          for i, x in enumerate(days[4:])]}
            (root / 'spy.json').write_text(json.dumps(spy))
            doc = MC.build(root, spy_path=root / 'spy.json', today=dt.date(2000, 10, 1), verbose=False)
            F = doc['fields']
            ev = [dict(zip(F, e)) for e in doc['events']]
            apr = next(e for e in ev if e['date'] == '1999-04-05')
            self.assertEqual((apr['time'], apr['release'], apr['kind'], apr['period'], apr['cal']), ('08:30', 'jobs', 'first', '1999-03-01', 1))
            self.assertEqual(apr['values']['PAYEMS'][1], 90.0)
            self.assertIsNotNone(apr['y2'])
            self.assertIsNotNone(apr['spy'])
            self.assertEqual(next(e for e in ev if e['date'] == '1999-06-05')['cal'], 0)
            self.assertTrue(any(e['release'] == 'fomc' and e['date'] == '1999-05-18' for e in ev))
            self.assertFalse(any(e['date'] > '2000-10-01' for e in ev))              # nothing after "today"
            self.assertEqual([u[0] for u in doc['upcoming']], ['2000-12-08', '2000-12-19'])
            st = doc['stats']['jobs']
            self.assertGreater(st['spy_abs'], st['spy_abs_quiet'])                 # the synthetic release days move more
            firsts = json.loads((root / 'public' / 'macro-firsts.json').read_text())['series']['PAYEMS']
            k = firsts['obs'].index('1999-03-01')
            self.assertEqual((firsts['first'][k], firsts['first_on'][k], firsts['today'][k]), (1420.0, '1999-04-05', 1430.0))
            self.assertIsNone(firsts['first'][firsts['obs'].index('1998-06-01')])


if __name__ == '__main__':
    unittest.main()
