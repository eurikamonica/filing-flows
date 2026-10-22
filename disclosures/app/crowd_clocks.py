"""Crowd Flow clocks (research specification v5, §6, §12 and §17.2): the Hype Map in three named views that never mix
clocks, comparable 13F manager cohorts with public-at times, and a descriptive quarter-to-quarter transition audit on
the full eligible denominator. Built by market.publish → market/hype-history.json and market/crowd-transitions.json.

view_id
  legacy_snapshot        the original Signals Hype map, unchanged: the latest well-covered report quarter's net managers
                         (every change on file) against each stock's trailing 63 trading days to the Signals build. A
                         mixed-clock snapshot: useful as "what is known now", not a quarter-to-quarter series.
  quarter_aligned        report quarter q: comparable managers' net change q−1 → q against the price from the end of q−1 to
                         the end of q. Retrospective: the full quarter's 13Fs were only public weeks after the quarter end.
  public_knowledge_asof  decision day d = the first trading day after the quarter end + 45 days (the 13F deadline, moved
                         to a trading day): only comparable pairs whose 13Fs (and amendments) were all filed before d,
                         against the trailing 63 trading days to d; forward returns run from the close of d. Checkpoints
                         at 30 and 90 days feed the audit. The quarter now being filed also has a
                         "live" origin at the latest close, with its partial coverage shown.

Comparable pair: one manager's complete, non-confidential 13F for quarter q and for the quarter immediately before it,
both in our feed. A manager that has not filed, filed late, skipped a quarter or asked for confidential treatment is
"not matched" — unknown, never a zero. Coverage = matched holders at q−1 ÷ holders at q−1 known by the same time.

Declared exceptions to strict truncation invariance (spec §1.1): stock-split detection and CUSIP conversions use the
finalised holder population (a split or re-domicile is a public corporate action at the time; only its detection uses
later filers), and dollar estimates use the quarter-end price the reporting managers imply (value ÷ shares), a public
quarter-end price measured from whichever filings are on file. Neither enters a quadrant.

Everything here is descriptive (status descriptive_only): counts, sample sizes and intervals, no forward probability.
"""
import bisect
from array import array
import datetime as dt
import gzip
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

OFFSETS = (30, 45, 90)          # public_knowledge_asof checkpoints: days after the quarter end (45 = the 13F deadline)
PRIMARY = 1                     # the checkpoint the map and the post-publication study use: the close after the deadline
OFFSET_NAME = {30: '30 days', 45: 'the 45-day deadline', 90: '90 days'}
NB = len(OFFSETS) + 1           # pair buckets: one per checkpoint + "after the last checkpoint / not reached yet"
TRAIL = 63                      # trading days in the trailing three-month window (as price_stats r3m)
HORIZONS = (('4w', 28), ('12w', 84))
QUADS = ('BR', 'SR', 'SF', 'BF', 'boundary')
QUAD_LABEL = {'BR': 'Bought and rising', 'SR': 'Sold while rising', 'SF': 'Sold and falling', 'BF': 'Bought while falling',
              'boundary': 'On an axis (net 0 or price 0)'}
FUND_TYPES = {'ETP', 'Open-End Fund', 'Closed-End Fund', 'Fund of Funds', 'Unit', 'Equity WRT', 'Right'}
SCHEMA = 'hype_history.v2'
AUDIT_SCHEMA = 'crowd_transitions.v1'
CLOCK_VERSION = 'crowd_clocks_v1'
PRICE_BASIS = ('daily closes from the hub price cache (Yahoo chart "close", Stooq fallback): split-adjusted price returns, '
               'dividends not included; benchmark SPY on the same basis')


# ------------------------------------------------------------------ calendar
def qend(period):
    return dt.date.fromisoformat(period)


def prev_q(period):
    d = qend(period)
    return (dt.date(d.year, d.month - 2, 1) - dt.timedelta(days=1)).isoformat() if d.month > 3 else f'{d.year - 1}-12-31'


def next_q(period):
    d = qend(period) + dt.timedelta(days=1)                      # first day of the next quarter
    m = d.month + 3
    y = d.year + (m > 12)
    return (dt.date(y, (m - 1) % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


class Clock:
    """Trading days (SPY's closes) and the public_knowledge_asof checkpoints. A checkpoint's anchor is the quarter end +
    offset days, moved forward to a trading day when it is not one (so the 45-day deadline lands where 13F rules put
    it: the next business day); its decision day is the first trading day after the anchor — a report filed on the
    anchor day (EDGAR accepts until 10 pm ET) can first be acted on at that close. A filing counts at a checkpoint when
    it was filed before the decision day. A checkpoint is reached only once the price file has its decision day."""

    def __init__(self, trading_days=None, today=None):
        self.days = sorted(trading_days or [])
        if today is None:
            today = dt.datetime.now(dt.timezone.utc).date()
        self.today = today if isinstance(today, str) else today.isoformat()
        self._cp = {}

    def _next(self, day, strict):
        """First trading day on or after (strict: after) day; None beyond the price file or after today."""
        if self.days:
            i = (bisect.bisect_right if strict else bisect.bisect_left)(self.days, day)
            d = self.days[i] if i < len(self.days) else None
        else:                                                  # no price file: weekdays
            x = dt.date.fromisoformat(day) + dt.timedelta(days=1 if strict else 0)
            while x.weekday() >= 5:
                x += dt.timedelta(days=1)
            d = x.isoformat()
        return d if d is not None and d <= self.today else None

    def latest(self):
        """The latest close on file (on or before today)."""
        if not self.days:
            return self._next(self.today, False) or self.today
        i = bisect.bisect_right(self.days, self.today)
        return self.days[i - 1] if i else None

    def checkpoints(self, period):
        """Decision days for OFFSETS (None when not reached yet)."""
        if period not in self._cp:
            e, out = qend(period), []
            for o in OFFSETS:
                a = self._next((e + dt.timedelta(days=o)).isoformat(), False)
                out.append(self._next(a, True) if a else None)
            self._cp[period] = out
        return self._cp[period]

    def anchors(self, period):
        e = qend(period)
        return [self._next((e + dt.timedelta(days=o)).isoformat(), False) for o in OFFSETS]

    def bucket(self, period, public):
        """First checkpoint index by which a report filed on `public` was known (filed before the decision day); NB−1
        when only after the last checkpoint or when that checkpoint has not come yet."""
        for c, d in enumerate(self.checkpoints(period)):
            if d is not None and public < d:
                return c
        return NB - 1


def clock_from_prices(root, today=None):
    rows = price_rows(root, 'SPY') or []
    return Clock([r[0] for r in rows], today)


# ------------------------------------------------------------------ manager pairs (one pass over the 13F cache)
class Tally:
    """Per report quarter: how many managers had a complete report for the quarter before (the at-risk reporters),
    how many form a comparable pair at each checkpoint (index NB−1 = everything on file now), why the others do not
    (as of now), and when original reports were first filed (days after the quarter end) — the calendar-only
    baseline for filing arrival."""

    def __init__(self, want=None):
        self.want = want                  # CUSIPs worth keeping per-security detail for (listed common stock); None = all
        self.q = defaultdict(lambda: {'prior_reporters': 0, 'ok': [0] * NB, 'confidential': 0, 'incomplete': 0,
                                      'gap': 0, 'first_in_feed': 0, 'not_filed': 0, 'lags': Counter()})
        # per period and CUSIP, difference arrays over checkpoints: unchanged comparable holders, holders seen from the
        # next quarter, and moves from report versions that a later amendment replaced (shares, prior, manager, lo, hi)
        self.cells = defaultdict(lambda: defaultdict(lambda: {'same': [0] * NB, 'ph': [0] * NB, 'asof': []}))

    def as_json(self, periods):
        out = {}
        for p in periods:
            t = self.q.get(p)
            if not t:
                continue
            out[p] = {k: v for k, v in t.items() if k != 'lags'}
        return out


def _ranges(keys):
    """[(lo, hi, key)] for runs of equal keys over checkpoint indices 0..NB−1."""
    out, lo = [], 0
    for c in range(1, len(keys) + 1):
        if c == len(keys) or keys[c] != keys[lo]:
            out.append((lo, c, keys[lo]))
            lo = c
    return out


def manager_pairs(m, clock, tally=None):
    """One manager's 13F record seen at each checkpoint (index NB−1 = everything on file now), as it stood then: only
    filings filed before the decision day, amendments included only once filed (holdings13f.core.resolve on that
    prefix). Returns (pairs, holders):

      pairs   {q: [(lo, hi, changes)]} — at checkpoints lo..hi−1 this manager's q report and q−1 report formed a
              comparable pair (both complete, non-confidential, consecutive); changes is None when they are the final
              ones (snapshot['changes']), else the change list as it stood then.
      holders {p: [(lo, hi, positions)]} — at checkpoints lo..hi−1 of the quarter after p, the manager's complete p
              report as it stood then; positions None when it is the final one.

    A later amendment or a late filing therefore never changes what an earlier checkpoint saw (truncation invariance)."""
    from holdings13f.core import resolve, compare
    fil = defaultdict(list)
    for f in m.get('filings') or []:
        if f.get('period') and f.get('filed'):
            fil[f['period']].append(f)
    for fs in fil.values():
        fs.sort(key=lambda f: (f['filed'], f.get('accepted') or '', f.get('accession') or ''))
    snaps = {s['period']: s for s in m.get('snapshots') or [] if s.get('period')}
    for q, s in snaps.items():                            # an older cache row without its filings: one filing
        if q not in fil:
            fil[q] = [{'filed': s.get('filed') or s.get('available_at', '')[:10] or '9999-12-31', '_final': True}]
    periods = sorted(fil)
    first = periods[0] if periods else None
    total = {p: len(fs) for p, fs in fil.items()}
    known = lambda p, d: total.get(p, 0) if d is None else sum(1 for f in fil.get(p) or () if f['filed'] < d)
    cache = {}

    def view(p, n):
        """Period p's snapshot from its first n filings (in filing order); the cached final one when n is all."""
        if not n:
            return None
        if n == total.get(p) or fil[p][0].get('_final'):
            return snaps.get(p)
        if (p, n) not in cache:
            r = resolve(fil[p][:n])
            cache[(p, n)] = r[0] if r else None
        return cache[(p, n)]

    def days(q):
        return [*clock.checkpoints(q)[:NB - 1], None]          # unreached checkpoints behave like now (never queried)

    pairs, holders = {}, {}
    for q in periods:
        p = prev_q(q)
        ds = days(q)
        keys = []
        for d in ds:
            kq, kp = known(q, d), known(p, d)
            sq, sp = view(q, kq), view(p, kp)
            ok = bool(sq and sp and sq.get('complete') and sp.get('complete') and not sq.get('confidential')
                      and not sp.get('confidential'))
            keys.append((kq, kp) if ok else None)
        fin = (total.get(q, 0), total.get(p, 0))
        out = []
        for lo, hi, key in _ranges(keys):
            if key is None:
                continue
            if key == fin:
                out.append((lo, NB if hi == NB else hi, None))
            else:
                out.append((lo, hi, compare(view(p, key[1]), view(q, key[0]))))
            if tally is not None:
                for c in range(lo, hi):
                    tally.q[q]['ok'][c] += 1
        if out:
            pairs[q] = out
        # holders of p seen from the next quarter's checkpoints
        n = next_q(q)
        hk = []
        for d in days(n):
            k = known(q, d)
            v = view(q, k)
            hk.append(k if v and v.get('complete') else None)
        hold = []
        for lo, hi, k in _ranges(hk):
            if k is None:
                continue
            hold.append((lo, hi, None if k == total.get(q) else (view(q, k) or {}).get('positions') or []))
        if hold:
            holders[q] = hold
        if tally is not None:                             # why not comparable, as of now
            t = tally.q[q]
            sq, sp = snaps.get(q), snaps.get(p)
            if keys[-1] is None and sq is not None:
                if not sq.get('complete') or (sp is not None and not sp.get('complete')):
                    t['incomplete'] += 1
                elif sp is None:
                    t['first_in_feed' if q == first else 'gap'] += 1
                else:
                    t['confidential'] += 1
            if sp is not None and sp.get('complete'):
                t['prior_reporters'] += 1
            real = [f for f in fil.get(q) or () if not f.get('_final')]
            if real:
                lag = (dt.date.fromisoformat(real[0]['filed']) - qend(q)).days
                t['lags'][max(0, min(lag, 400))] += 1
    if tally is not None:                                 # a complete last report, nothing filed for the next quarter yet
        for p, s in snaps.items():
            n = next_q(p)
            if s.get('complete') and n not in fil and n <= clock.today:
                tally.q[n]['prior_reporters'] += 1
                tally.q[n]['not_filed'] += 1
    return pairs, holders


def _common(r, want=None):
    return (r.get('put_call') == 'NONE' and r.get('share_type') == 'SH' and r.get('cusip')
            and (want is None or r['cusip'] in want))


def record_versions(tally, pairs, held, idx, keep_after):
    """Into tally.cells: the report versions that held only until a later amendment (the final versions are read by
    market.scan_13f from the snapshot itself)."""
    for q, ranges in pairs.items():
        if q <= keep_after:
            continue
        cells = tally.cells[q]
        for lo, hi, ch in ranges:
            if ch is None:
                continue
            for r in ch:
                if not _common(r, tally.want):
                    continue
                cell = cells[r['cusip']]
                if not r.get('delta_shares'):
                    if r.get('shares'):
                        cell['same'][lo] += 1
                        if hi < NB:
                            cell['same'][hi] -= 1
                else:
                    cell['asof'].append((r.get('shares') or 0, r.get('prior_shares') or 0, idx, lo, hi))
    for p, ranges in held.items():
        if p <= keep_after:
            continue
        cells = tally.cells[p]
        for lo, hi, pos in ranges:
            if pos is None:
                continue
            for r in pos:
                if _common(r, tally.want):
                    cell = cells[r['cusip']]
                    cell['ph'][lo] += 1
                    if hi < NB:
                        cell['ph'][hi] -= 1


def cohorts(raw, prices, summ, skips, universe, tally):
    """Per report quarter and listed common stock (CUSIPs summed per ticker): difference arrays over checkpoints
    (cumulate(·, c) = the state at checkpoint c) of [added, cut, unchanged, entries, exits, est. net $, holders at
    q−1]. Comparable pairs only; split-adjusted with the factor summarise() found; CUSIP conversions left out like the
    flows. Final changes count from their first checkpoint on; earlier versions (before an amendment) only over their
    own checkpoints."""
    out = {}
    for q, per in raw.items():
        prev = prev_q(q)
        px = prices.get(q, {})
        skip = (skips or {}).get(q, ())
        rows = {}
        cells = tally.cells.get(q) or {}
        before_cells = tally.cells.get(prev) or {}
        for c in set(per) | set(cells) | set(before_cells):   # prior holders alone count too (none filed yet)
            t = universe.cusip_ticker.get(c)
            if not t or universe.cusip_type.get(c) in FUND_TYPES:
                continue
            st = per.get(c) or {'moves': []}
            cell = cells.get(c) or {}
            k = ((summ.get(q) or {}).get(c) or {}).get('split') or 1
            acc = rows.setdefault(t, [[0, 0, 0, 0, 0, 0.0, 0] for _ in range(NB)])
            p = px.get(c) or 0

            def put(shares, prior, at, sign):
                a, d = acc[at], shares - prior * k
                if abs(d) < 1e-9 or (prior and abs(d) / (prior * k) < 1e-4):
                    a[2] += sign
                elif d > 0:
                    a[0] += sign; a[3] += sign * (not prior); a[5] += sign * d * p
                else:
                    a[1] += sign; a[4] += sign * (not shares); a[5] += sign * d * p
            for mv in st['moves']:
                b = mv[3] if len(mv) > 3 else -1
                if b >= 0 and (c, mv[2]) not in skip:
                    put(mv[0], mv[1], b, 1)
            for shares, prior, idx, lo, hi in cell.get('asof') or ():
                if (c, idx) not in skip:
                    put(shares, prior, lo, 1)
                    if hi < NB:
                        put(shares, prior, hi, -1)
            for b, n in enumerate(cell.get('same') or ()):
                if n:                                    # unchanged raw quantity: after a k-for-1 split that is a cut
                    acc[b][2 if k == 1 else 1 if k > 1 else 0] += n
            before = before_cells.get(c)
            if before:
                for b, n in enumerate(before.get('ph') or ()):
                    acc[b][6] += n
        out[q] = rows
    return out


def cumulate(buckets, upto):
    """The state at checkpoint upto: the prefix sum of the difference arrays."""
    s = [0, 0, 0, 0, 0, 0.0, 0]
    for b in range(upto + 1):
        for i, v in enumerate(buckets[b]):
            s[i] += v
    return s


def crowd_state(acc):
    """{x, add, cut, same, entry, exit, usd, prior, matched, n, cov} from cumulated counters. matched = comparable
    managers that held the stock at q−1; n = every comparable manager with a position at q−1 or q."""
    add, cut, same, entry, ex, usd, prior = acc
    matched = cut + same + add - entry
    return {'x': add - cut, 'add': add, 'cut': cut, 'same': same, 'entry': entry, 'exit': ex, 'usd': usd, 'prior': prior,
            'matched': matched, 'n': matched + entry, 'cov': (min(1.0, matched / prior) if prior else None)}


# ------------------------------------------------------------------ prices
def price_rows(root, ticker):
    path = Path(root) / 'cache' / 'prices' / (re.sub(r'[^A-Za-z0-9-]', '_', ticker) + '.json.gz')
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return [r for r in json.load(f)['rows'] if r and r[1]]
    except Exception:
        return None


class Prices:
    """Daily closes per ticker, loaded once and kept compact (day ordinals and closes in arrays: thousands of tickers)."""

    def __init__(self, root, since=None):
        self.root, self.cache = root, {}
        self.since = since or '2000-01-01'

    def rows(self, t):
        if t not in self.cache:
            r = price_rows(self.root, t)
            if r:
                r = [x for x in r if x[0] >= self.since]
            self.cache[t] = ((array('i', [dt.date.fromisoformat(x[0]).toordinal() for x in r]), array('d', [float(x[1]) for x in r]))
                             if r else None)
        return self.cache[t]

    def at(self, t, day, max_gap=10):
        """(index, date, close) of the last close on or before day, within max_gap calendar days."""
        rd = self.rows(t)
        if not rd or not day:
            return None
        days, closes = rd
        o = dt.date.fromisoformat(day).toordinal()
        i = bisect.bisect_right(days, o) - 1
        if i < 0 or o - days[i] > max_gap:
            return None
        return i, dt.date.fromordinal(days[i]).isoformat(), closes[i]

    def day(self, t, i):
        rd = self.rows(t)
        return dt.date.fromordinal(rd[0][i]).isoformat() if rd and 0 <= i < len(rd[0]) else None

    def change(self, t, start, end):
        a, b = self.at(t, start), self.at(t, end)
        return (b[2] / a[2] - 1) if a and b and a[2] and b[1] > a[1] else None

    def trailing(self, t, day, n=TRAIL):
        rd, a = self.rows(t), self.at(t, day, max_gap=5)
        if not a or a[0] < n:
            return None
        start = rd[1][a[0] - n]
        return (a[2] / start - 1) if start else None

    def forward(self, t, day, days, last):
        """Close of `day` → last close on or before day + days; None while that end is after the last close on file."""
        end = (dt.date.fromisoformat(day) + dt.timedelta(days=days)).isoformat()
        if not last or end > last:
            return None
        return self.change(t, day, end)


# ------------------------------------------------------------------ the views
def flag_rules(states):
    """The Hype map's 13F flags with this quarter's own thresholds (as build_signals): crowded buy 1, new money 2, big
    inflow 4, crowded exit 8, big outflow 16. states: {ticker: crowd_state}. Returns ({ticker: bits}, thresholds)."""
    vals = [s for s in states.values() if s['n']]
    nets = sorted((s['x'] for s in vals), reverse=True)
    usd = sorted((s['usd'] for s in vals), reverse=True)
    news = sorted((s['entry'] for s in vals), reverse=True)
    crowd = max(8, nets[min(len(nets) - 1, 60)] if nets else 8)
    inflow = max(50e6, usd[min(len(usd) - 1, 60)] if usd else 50e6)
    outflow = min(-50e6, usd[-min(len(usd), 61)] if usd else -50e6)
    new_cut = max(10, news[min(len(news) - 1, 100)] if news else 10)
    out = {}
    for t, s in states.items():
        b, s_, net = s['add'], s['cut'], s['x']
        f = ((net >= crowd and b >= 2 * max(1, s_)) * 1 | (s['entry'] >= new_cut) * 2 | (s['usd'] >= inflow) * 4
             | (-net >= crowd and s_ >= 2 * max(1, b)) * 8 | (s['usd'] <= outflow) * 16)
        if f:
            out[t] = f
    return out, {'crowd_net_managers': crowd, 'new_positions': new_cut, 'inflow_usd': round(inflow), 'outflow_usd': round(outflow)}


def quadrant(x, y):
    """BR / SR / SF / BF, 'boundary' on an axis (x = 0 or y = 0), None when either is unknown. Raw values only: the
    chart's −60% … +120% clip is display-only."""
    if x is None or y is None:
        return None
    if x == 0 or y == 0:
        return 'boundary'
    return ('BR' if y > 0 else 'BF') if x > 0 else ('SR' if y > 0 else 'SF')


def eligible(s, population):
    """all_eligible: some comparable manager had a position at q−1 or q and the price window is defined.
    covered: at least 5 matched prior holders and ≥ 80% of the known prior holders matched."""
    if not s or not s['n'] or s.get('y') is None:
        return False
    if population == 'covered':
        return s['matched'] >= 5 and (s['cov'] or 0) >= 0.8
    return True


def officials_window(trades, lo, hi, by='filed_date'):
    """{ticker: [purchases, sales]} with `by` in [lo, hi) — filed_date for what was public, date for when it happened."""
    out = defaultdict(lambda: [0, 0])
    for t in trades or ():
        k = t.get('ticker_canon') or t.get('ticker')
        d = t.get(by) or ''
        if not k or not (lo <= d < hi):
            continue
        typ = t.get('type') or ''
        if typ == 'purchase':
            out[k][0] += 1
        elif 'sale' in typ:
            out[k][1] += 1
    return out


def build_states(cohort, coverage, tally, clock, px, trades=None):
    """Both clock-separated views, for every listed stock with comparable coverage (the full denominator).
    Returns {'qa': [{period, meta, states}], 'pa': {offset index or 'live': [{period, meta, states}]}}."""
    full = max(coverage.values() or [0])
    periods = sorted(cohort)
    good = lambda p: full and coverage.get(p, 0) >= 0.6 * full
    last = clock.latest()
    spy = lambda a, b: px.change('SPY', a, b)
    qa, pa = [], defaultdict(list)
    for q in periods:
        p = prev_q(q)
        rows = cohort[q]
        if not good(p):
            continue
        tq = tally.q.get(q) or {}
        if good(q) and q <= clock.today:                         # quarter_aligned: every comparable pair on file
            st = {}
            for t, b in rows.items():
                s = crowd_state(cumulate(b, NB - 1))
                s['y'] = px.change(t, p, q)
                st[t] = s
            if trades:
                off = officials_window(trades, (qend(p) + dt.timedelta(days=1)).isoformat(),
                                       (qend(q) + dt.timedelta(days=1)).isoformat(), by='date')
                for t, s in st.items():
                    s['off'] = off.get(t)
            finalised = (qend(q) + dt.timedelta(days=OFFSETS[-1])).isoformat() <= clock.today
            qa.append({'period': q, 'states': st,
                       'meta': {'report_quarter_end': q, 'price_window': [p, q], 'spy': _r(spy(p, q)),
                                'managers_filed': coverage.get(q, 0), 'prior_reporters': tq.get('prior_reporters', 0),
                                'comparable_managers': (tq.get('ok') or [0] * NB)[NB - 1], 'finalised': finalised,
                                'not_comparable': {k: tq.get(k, 0) for k in ('confidential', 'incomplete', 'gap', 'not_filed')}}})
        cps = clock.checkpoints(q)
        reached = [c for c, d in enumerate(cps) if d is not None]
        origins = [(c, cps[c]) for c in reached]
        if cps[PRIMARY] is None and coverage.get(q, 0) >= 10 and last:   # the quarter being filed: as of the latest close
            origins.append(('live', last))
        for c, d in origins:
            upto = c if c != 'live' else NB - 1
            st = {}
            for t, b in rows.items():
                s = crowd_state(cumulate(b, upto))
                if not s['n'] and not s['prior']:
                    continue
                s['y'] = px.trailing(t, d)
                for h, days in HORIZONS:
                    r, m = px.forward(t, d, days, last), px.forward('SPY', d, days, last)
                    s['f' + h] = r
                    s['e' + h] = (r - m) if r is not None and m is not None else None
                st[t] = s
            if trades:
                off = officials_window(trades, (dt.date.fromisoformat(d) - dt.timedelta(days=91)).isoformat(), d)
                for t, s in st.items():
                    s['off'] = off.get(t)
            spy_start = px.at('SPY', d, max_gap=5)
            window_start = px.day('SPY', spy_start[0] - TRAIL) if spy_start and spy_start[0] >= TRAIL else None
            known = (tq.get('ok') or [0] * NB)[upto]
            pa[c].append({'period': q, 'states': st,
                          'meta': {'report_quarter_end': q, 'kind': 'live' if c == 'live' else f'{OFFSETS[c]}d',
                                   'offset_days': None if c == 'live' else OFFSETS[c],
                                   'anchor': None if c == 'live' else clock.anchors(q)[c], 'decision_day': d,
                                   'filings_before': d if c != 'live' else None, 'price_window': [window_start, d],
                                   'comparable_managers_public': known, 'prior_reporters': tq.get('prior_reporters', 0),
                                   'forward_end': {h: (dt.date.fromisoformat(d) + dt.timedelta(days=days)).isoformat() for h, days in HORIZONS},
                                   'spy_forward': {h: _r(px.forward('SPY', d, days, last)) for h, days in HORIZONS},
                                   'partial': c == 'live'}})
    return {'qa': qa, 'pa': dict(pa)}


def _r(v, n=4):
    return None if v is None or not math.isfinite(v) else round(v, n)


def _usd(v):
    if not v:
        return 0
    m = 10 ** max(0, int(math.log10(abs(v))) - 2)         # three significant figures
    return int(round(v / m) * m)


def hype_history(views, signals, legacy, universe, generated_at):
    """market/hype-history.json (schema hype_history.v2): per view the quarters with their clock metadata and per stock
    the points. Rows: every stock flagged in some view's quarter, plus every 13F stock on the Signals list."""
    qa, pa = views['qa'], views['pa'].get(PRIMARY, []) + views['pa'].get('live', [])
    pa.sort(key=lambda o: (o['period'], o['meta']['decision_day']))
    flags = {'qa': [], 'pa': []}
    thresholds = {'qa': [], 'pa': []}
    for key, seq in (('qa', qa), ('pa', pa)):
        for o in seq:
            f, th = flag_rules(o['states'])
            flags[key].append(f); thresholds[key].append(th)
    wanted = set()
    for key in flags:
        for f in flags[key]:
            wanted |= set(f)
    wanted |= {r['ticker'] for r in signals or () if r.get('f13')}
    rows = {}
    for t in sorted(wanted):
        ra, rp = [], []
        for j, o in enumerate(qa):
            s = o['states'].get(t)
            if not s or not s['n']:
                ra.append(None); continue
            fl = flags['qa'][j].get(t, 0)
            leg = (legacy.get(t) or {}).get(o['period'])
            ra.append([s['x'], s['add'], s['cut'], s['entry'], _usd(s['usd']), _r(s['y']), fl, _heat(fl),
                       None if s['cov'] is None else round(100 * s['cov']), leg, *(s.get('off') or [0, 0])])
        for j, o in enumerate(pa):
            s = o['states'].get(t)
            if not s or not s['n']:
                rp.append(None); continue
            fl = flags['pa'][j].get(t, 0)
            rp.append([s['x'], s['add'], s['cut'], s['entry'], _usd(s['usd']), _r(s['y']), fl, _heat(fl),
                       None if s['cov'] is None else round(100 * s['cov']), _r(s.get('e4w')), _r(s.get('e12w')), *(s.get('off') or [0, 0])])
        if any(ra) or any(rp):
            rows[t] = {'name': universe.name(t) or '', 'qa': ra, 'pa': rp}
    return {
        'schema_version': SCHEMA, 'clock_version': CLOCK_VERSION, 'generated_at': generated_at, 'status': 'descriptive_only',
        'price_basis': PRICE_BASIS,
        'views': {
            'legacy_snapshot': {**(legacy.get('_clock') or {}), 'note': (
                'The original Hype map from Signals: net managers in the latest well-covered report quarter (every change on '
                'file) against each stock\'s trailing three months to its latest close. Mixed clocks — the 13F quarter ended '
                'months before the price window does — so it is a snapshot of what is known now, not a transition series.')},
            'quarter_aligned': {'periods': [o['period'] for o in qa], 'clock': [o['meta'] for o in qa], 'thresholds': thresholds['qa'],
                                'fields': ['net_managers', 'added', 'cut', 'new_positions', 'usd_net', 'r_quarter', 'flags', 'heat',
                                           'coverage_pct', 'net_managers_legacy', 'officials_buys_in_q', 'officials_sales_in_q'],
                                'note': ('Report quarter q: comparable managers (complete 13Fs for q and the quarter before) — added '
                                         'minus cut — against the price from the end of the quarter before to the end of q. '
                                         'Retrospective: these 13Fs were public only weeks after the quarter end. Officials: '
                                         'transactions dated in the quarter (reported later).')},
            'public_knowledge_asof': {'origins': [o['meta'] for o in pa], 'periods': [o['period'] for o in pa],
                                      'thresholds': thresholds['pa'], 'offset_days': OFFSETS[PRIMARY],
                                      'fields': ['net_managers', 'added', 'cut', 'new_positions', 'usd_net', 'r_trailing_3m', 'flags',
                                                 'heat', 'coverage_pct', 'excess_4w_vs_spy', 'excess_12w_vs_spy',
                                                 'officials_buys_public_3m', 'officials_sales_public_3m'],
                                      'note': ('Decision day: the first trading day after the 13F deadline (quarter end + 45 days, '
                                               'moved to a trading day). Only comparable 13F pairs whose filings were all filed '
                                               'before that day; '
                                               'price: trailing 63 trading days to it; forward: from its close over the next 4 and '
                                               '12 weeks, minus SPY over the same days (blank until those weeks have passed). '
                                               'Officials: reports filed in the 91 days before the decision day. "live" = the '
                                               'quarter being filed, as of the latest close, partial.')},
        },
        'flags': {'crowded_buy': 1, 'new_money': 2, 'big_inflow': 4, 'crowded_exit': 8, 'big_outflow': 16},
        'rows': rows,
        'note': ('Each view keeps its own clock: never compare a point in one view with a point in another. Comparable pair = '
                 'one manager\'s complete, non-confidential 13Fs for the quarter and the one before; a missing filing is '
                 'unknown, not zero. Flags use each quarter\'s own thresholds within the view; "new on the map" = flagged in '
                 'this quarter of the view, not the one before. Descriptive, not a forecast or advice.')}


def _heat(f):
    return 2 * bool(f & 1) + bool(f & 2) + bool(f & 4)


# ------------------------------------------------------------------ the transition audit (descriptive)
def wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - r) / d, 4), round((c + r) / d, 4)


def matrix(seq, population):
    """4×4 (+ boundary) transition counts between consecutive report quarters of one view, the row-wise shares with
    Wilson 95% intervals (stock-quarters treated as independent — they are not: see by_pair for the spread between
    quarter pairs), and the per-pair matrices."""
    pairs = []
    for a, b in zip(seq, seq[1:]):
        if next_q(a['period']) != b['period']:
            continue
        cnt = {i: Counter() for i in QUADS}
        for t, s in a['states'].items():
            if not eligible(s, population):
                continue
            s2 = b['states'].get(t)
            if not eligible(s2, population):
                continue
            cnt[quadrant(s['x'], s['y'])][quadrant(s2['x'], s2['y'])] += 1
        pairs.append({'from': a['period'], 'to': b['period'], 'counts': [[cnt[i][j] for j in QUADS] for i in QUADS]})
    pooled = [[sum(p['counts'][i][j] for p in pairs) for j in range(len(QUADS))] for i in range(len(QUADS))]
    rows = []
    for i, row in enumerate(pooled):
        n = sum(row)
        cells = []
        for j, k in enumerate(row):
            lo, hi = wilson(k, n)
            spread = [p['counts'][i][j] / sum(p['counts'][i]) for p in pairs if sum(p['counts'][i]) >= 20]
            cells.append({'n': k, 'p': round(k / n, 4) if n else None, 'lo': lo, 'hi': hi,
                          'pair_min': round(min(spread), 4) if spread else None, 'pair_max': round(max(spread), 4) if spread else None})
        rows.append({'from': QUADS[i], 'n': n, 'cells': cells})
    return {'quarter_pairs': len(pairs), 'stock_quarters': sum(sum(r) for r in pooled),
            'issuers': len({t for a in seq for t, s in a['states'].items() if eligible(s, population)}),
            'rows': rows, 'by_pair': pairs}


def _dist(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    q = lambda f: v[min(len(v) - 1, max(0, int(round(f * (len(v) - 1)))))]
    return {'n': len(v), 'median': round(statistics.median(v), 4), 'p25': round(q(.25), 4), 'p75': round(q(.75), 4),
            'beat_spy': round(sum(1 for x in v if x > 0) / len(v), 4)}


def post_publication(seq, population, perms=500, seed=7):
    """After the decision day: forward excess returns vs SPY by public crowd quadrant, beside the price-only, crowd-only,
    coverage-only and unconditional baselines, per-origin medians (dates are the independent units), and a negative
    control — 13F net managers shuffled across stocks within each decision day."""
    groups = defaultdict(lambda: defaultdict(list))
    per_origin = defaultdict(lambda: defaultdict(list))
    units = defaultdict(list)
    for o in seq:
        if o['meta'].get('partial'):
            continue
        d = o['meta']['decision_day']
        for t, s in o['states'].items():
            if not eligible(s, population):
                continue
            qd = quadrant(s['x'], s['y'])
            for h, _ in HORIZONS:
                e = s.get('e' + h)
                if e is None:
                    continue
                keys = [qd, 'all', 'price_rising' if s['y'] > 0 else 'price_falling' if s['y'] < 0 else None,
                        'crowd_added' if s['x'] > 0 else 'crowd_cut' if s['x'] < 0 else None,
                        ('coverage_high' if (s['cov'] or 0) >= 0.9 else 'coverage_low')]
                for k in keys:
                    if k:
                        groups[h][k].append(e)
                        per_origin[h][(k, d)].append(e)
                units[(h, d)].append((s['x'], e))
    out = {}
    rng = random.Random(seed)
    for h, _ in HORIZONS:
        g = {k: _dist(v) for k, v in groups[h].items()}
        med = defaultdict(list)
        for (k, d), v in per_origin[h].items():
            if len(v) >= 10:
                med[k].append([d, round(statistics.median(v), 4), len(v)])
        days = sorted({d for (hh, d) in units if hh == h})
        stat = lambda pairs: _gap([e for x, e in pairs if x > 0], [e for x, e in pairs if x < 0])
        obs = stat([u for d in days for u in units[(h, d)]])
        null = []
        if obs is not None:
            for _ in range(perms):
                sh = []
                for d in days:
                    xs = [x for x, _ in units[(h, d)]]
                    rng.shuffle(xs)
                    sh.extend(zip(xs, [e for _, e in units[(h, d)]]))
                v = stat(sh)
                if v is not None:
                    null.append(v)
        pval = (1 + sum(1 for v in null if abs(v) >= abs(obs))) / (1 + len(null)) if null else None
        out[h] = {'groups': g, 'per_origin_medians': {k: sorted(v) for k, v in med.items()}, 'origins': len(days),
                  'negative_control': {'statistic': 'median excess (net added > 0) − median excess (net cut < 0)',
                                       'observed': _r(obs), 'shuffled_p05': _r(_pct(null, .05)), 'shuffled_p95': _r(_pct(null, .95)),
                                       'p_two_sided': _r(pval, 3), 'shuffles': len(null),
                                       'method': '13F net managers shuffled across stocks within each decision day; prices fixed'}}
    return out


def _gap(a, b):
    return statistics.median(a) - statistics.median(b) if len(a) >= 10 and len(b) >= 10 else None


def _pct(v, f):
    if not v:
        return None
    v = sorted(v)
    return v[min(len(v) - 1, int(f * (len(v) - 1)))]


def retrospective_gap(qa, pa, population):
    """Experiment 3: how often the 13F side and the price side agree in the retrospective same-quarter view, against
    how often the public as-of 13F side was followed by beating SPY over the next 12 weeks."""
    spy = {o['period']: o['meta'].get('spy') for o in qa}
    same = defaultdict(list)
    for o in qa:
        m = spy.get(o['period'])
        if m is None:
            continue
        for t, s in o['states'].items():
            if eligible(s, population) and s['x']:
                same['added' if s['x'] > 0 else 'cut'].append(s['y'] - m > 0)
    after = defaultdict(list)
    for o in pa:
        if o['meta'].get('partial'):
            continue
        for t, s in o['states'].items():
            if eligible(s, population) and s['x'] and s.get('e12w') is not None:
                after['added' if s['x'] > 0 else 'cut'].append(s['e12w'] > 0)
    share = lambda v: {'n': len(v), 'beat_spy': round(sum(v) / len(v), 4) if v else None}
    return {'same_quarter_retrospective': {k: share(v) for k, v in same.items()},
            'next_12w_after_public': {k: share(v) for k, v in after.items()},
            'note': ('Same quarter: net added / cut by comparable managers in quarter q and whether the stock beat SPY in that '
                     'same quarter — not knowable in time. After public: the as-of state and whether it beat SPY over the 12 '
                     'weeks after the decision day. The difference is the part of the attractive retrospective picture that '
                     'was not available to act on.')}


def filing_calendar(tally, periods):
    """C0, the calendar-only baseline for 13F arrival: share of the quarter's original reports first filed within k days
    of the quarter end (of reports filed so far)."""
    marks = (15, 20, 25, 30, 35, 40, 45, 46, 50, 60, 75, 90, 120)
    by, pooled = {}, Counter()
    for p in periods:
        lags = (tally.q.get(p) or {}).get('lags') or Counter()
        n = sum(lags.values())
        if not n:
            continue
        pooled.update(lags)
        by[p] = {'reports': n, 'share_by_day': {str(k): round(sum(v for d, v in lags.items() if d < k) / n, 4) for k in marks}}
    n = sum(pooled.values())
    return {'days': list(marks), 'by_quarter': by,
            'pooled': {'reports': n, 'share_by_day': {str(k): round(sum(v for d, v in pooled.items() if d < k) / n, 4) for k in marks}} if n else None,
            'note': 'Original reports first filed before day k after the quarter end, of those filed so far. Statutory deadline: 45 days.'}


def audit(views, tally, coverage, generated_at):
    """market/crowd-transitions.json: the descriptive transition audit (schema crowd_transitions.v1)."""
    qa = views['qa']
    pa_all = views['pa']
    out = {'schema_version': AUDIT_SCHEMA, 'clock_version': CLOCK_VERSION, 'generated_at': generated_at,
           'status': 'descriptive_only', 'probabilities': None, 'price_basis': PRICE_BASIS,
           'definitions': {
               'quadrants': QUAD_LABEL, 'order': list(QUADS),
               'x': 'comparable 13F managers that added minus those that cut (split-adjusted share counts)',
               'y': {'quarter_aligned': 'price change from the end of the quarter before to the end of the report quarter',
                     'public_knowledge_asof': 'price change over the 63 trading days to the decision day'},
               'populations': {'all_eligible': 'every listed common stock with a comparable manager holding it at q−1 or q and a price',
                               'covered': '≥ 5 matched prior holders and ≥ 80% of the known prior holders matched'},
               'target_versions': {'crowd_quadrant': 'crowd_quadrant_v1', 'post_publication': 'excess_return_vs_spy_v1 (4w, 12w)'},
               'industry_benchmark': None,
               'industry_benchmark_note': 'Not in this build yet: the 13F builder has no point-in-time industry series; returns are vs SPY.'},
           'views': {}}
    for pop in ('all_eligible', 'covered'):
        out['views'].setdefault('quarter_aligned', {})[pop] = matrix(qa, pop)
    for c, seq in pa_all.items():
        if c == 'live':
            continue
        key = f'public_knowledge_asof_{OFFSETS[c]}d'
        v = out['views'].setdefault(key, {})
        for pop in ('all_eligible', 'covered'):
            v[pop] = matrix(seq, pop)
            if c == PRIMARY:
                v[pop]['post_publication'] = post_publication(seq, pop)
    prim = pa_all.get(PRIMARY, [])
    out['experiment_3'] = {pop: retrospective_gap(qa, prim, pop) for pop in ('all_eligible', 'covered')}
    periods = sorted(set(o['period'] for o in qa) | set(o['period'] for seq in pa_all.values() for o in seq))
    out['filing_calendar'] = filing_calendar(tally, sorted(coverage))
    out['managers'] = tally.as_json(periods)
    out['coverage_by_origin'] = {f'{OFFSETS[c]}d' if c != 'live' else 'live':
                                 [{'period': o['period'], 'decision_day': o['meta']['decision_day'],
                                   'comparable_managers_public': o['meta']['comparable_managers_public'],
                                   'prior_reporters': o['meta']['prior_reporters'],
                                   'median_stock_coverage': _median([s['cov'] for s in o['states'].values() if s['cov'] is not None and s['prior'] >= 5])}
                                  for o in seq] for c, seq in pa_all.items()}
    out['sample'] = {'stratum': 'price_and_13f', 'independent_periods': len(qa),
                     'issuers': len({t for o in qa for t, s in o['states'].items() if s['n']}),
                     'note': ('Many stocks on one date are not many independent periods: '
                              f'{len(qa)} report quarters, {len(prim)} decision days after the 45-day deadline.')}
    out['note'] = ('Descriptive history only (release gate G0/G1): how stocks moved between Hype-map quadrants from one report '
                   'quarter to the next, separately for each clock, with sample sizes and intervals — not a forecast. Each '
                   'view has its own labels, denominators and windows; never compare cells across views.')
    return out


def _median(v):
    v = [x for x in v if x is not None]
    return round(statistics.median(v), 4) if v else None


def legacy_series(summ, universe, periods):
    """{ticker: {period: net managers on the original count}} — every change on file, as by-ticker-history."""
    out = defaultdict(dict)
    for p in periods:
        per = defaultdict(lambda: [set(), set()])
        for c, st in (summ.get(p) or {}).items():
            t = universe.cusip_ticker.get(c)
            if not t or universe.cusip_type.get(c) in FUND_TYPES:
                continue
            per[t][0] |= st['b']; per[t][1] |= st['s']
        for t, (b, s) in per.items():
            out[t][p] = len(b) - len(s)
    return out
