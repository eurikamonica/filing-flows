"""Macro release calendar and first prints: when each US data release came out (the day and the clock time, Eastern),
what it said the first time — before any revision — and how the 2-year and 10-year Treasury yields and SPY moved that
day; the FOMC's statements the same way. For event studies of macro release days (Disclosures → Rotation → "Macro
release calendar") and so that the macro clock (app/macro_history.py) reads each figure as it was known at the time.

  fetch   FRED / ALFRED real-time data through the FRED API (needs FRED_API_KEY; without it nothing is fetched and the
          rest of the site is unchanged): for each series every value it has ever had and the days it held it
          (output_type=1, one row per real-time period), the release it belongs to and that release's dates, the
          scheduled ones included → <root>/cache/macro-rt/<ID>.json.gz and release-<id>.json; the Federal Reserve's FOMC
          calendar (the current page, and one page per earlier year, read once) → <root>/cache/fomc/.
  build   public/macro-calendar.json
            events     every release day since 1995: date, clock time (ET), release, what it published (the newest
                       period it reported for the first time, or "revision" when it only revised), per series the value
                       printed that day, the headline (m/m %, change, level or annualized q/q %), the prior period as
                       known that day, the value today and the y/y rate as printed; the day's change in the 2-year and
                       10-year Treasury yields (basis points, FRED DGS2 / DGS10) and SPY's return (basis points, from
                       the hub's daily returns, when given); the FOMC's statement days with their type, projections,
                       press conference and minutes date
            upcoming   the scheduled release days of the next 120 days and the next FOMC statements
            stats      per release: how much SPY and the 2-year yield moved on its days against the other trading days
          public/macro-firsts.json — per series the first print of every period, the day it was printed and today's
          value (the revision is the difference)

The release day is the day ALFRED first holds a value (its real-time start), which is the agency's release date; a
period whose first value only appears with the series' first vintage (before ALFRED kept history), or later than
MAX_LAG after the period ended, has no first print. Clock times are the agencies' usual ones (8:30 a.m. for BLS, BEA
and Census, 9:15 for industrial production, 10:00 for JOLTS, 2:00 p.m. for FOMC statements since 2013).

    FRED_API_KEY=… python app/macro_calendar.py fetch --root hist
    python app/macro_calendar.py build --root hist [--spy SPY.json]
"""
import argparse
import bisect
import datetime as dt
import gzip
import html as _html
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://api.stlouisfed.org/fred/'
FOMC_NOW = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
FOMC_YEAR = 'https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm'
UA = 'Mozilla/5.0 (compatible; FilingFlows; +https://filing-flows.com)'
OBS_START = '1990-01-01'
FIRST_YEAR = 1995                       # events kept from here
UPCOMING_DAYS = 120
MAX_LAG = {'w': 14, 'm': 75, 'q': 120}  # days from the end of a period to its first print, at most (shutdowns included)

# release key -> (name, agency, usual time ET)
RELEASES = {
    'cpi': ('Consumer prices (CPI)', 'BLS', '08:30'),
    'jobs': ('Employment report', 'BLS', '08:30'),
    'ppi': ('Producer prices (PPI)', 'BLS', '08:30'),
    'retail': ('Retail sales', 'Census Bureau', '08:30'),
    'pce': ('Personal income and outlays (PCE prices)', 'BEA', '08:30'),
    'gdp': ('GDP', 'BEA', '08:30'),
    'ip': ('Industrial production', 'Federal Reserve', '09:15'),
    'housing': ('Housing starts', 'Census Bureau', '08:30'),
    'claims': ('Jobless claims', 'Labor Department', '08:30'),
    'jolts': ('Job openings (JOLTS)', 'BLS', '10:00'),
    'fomc': ('FOMC statement', 'Federal Reserve', '14:00'),
}
# series id -> (label, short label, unit, frequency, headline, decimals, scale, release key)
#   headline: pct = % change on the prior period; chg = change in level; lvl = the level; ann = annualized % change
#   scale: multiply values for display (claims are people: shown in thousands)
SERIES = {
    'CPIAUCSL': ('Consumer prices (CPI), all items', 'CPI', 'index', 'm', 'pct', 1, 1, 'cpi'),
    'CPILFESL': ('Core CPI (ex food and energy)', 'core CPI', 'index', 'm', 'pct', 1, 1, 'cpi'),
    'PAYEMS': ('Nonfarm payrolls', 'payrolls', 'k', 'm', 'chg', 0, 1, 'jobs'),
    'UNRATE': ('Unemployment rate', 'unemployment', '%', 'm', 'lvl', 1, 1, 'jobs'),
    'CES0500000003': ('Average hourly earnings', 'hourly pay', '$', 'm', 'pct', 1, 1, 'jobs'),
    'PPIFIS': ('Producer prices, final demand', 'PPI', 'index', 'm', 'pct', 1, 1, 'ppi'),
    'RSAFS': ('Retail and food services sales', 'retail sales', '$m', 'm', 'pct', 1, 1, 'retail'),
    'PCEPI': ('PCE prices', 'PCE prices', 'index', 'm', 'pct', 1, 1, 'pce'),
    'PCEPILFE': ('Core PCE prices', 'core PCE', 'index', 'm', 'pct', 1, 1, 'pce'),
    'GDPC1': ('Real GDP', 'GDP', '$bn', 'q', 'ann', 1, 1, 'gdp'),
    'INDPRO': ('Industrial production', 'production', 'index', 'm', 'pct', 1, 1, 'ip'),
    'HOUST': ('Housing starts (annual rate)', 'starts', 'k', 'm', 'lvl', 0, 1, 'housing'),
    'ICSA': ('Initial jobless claims', 'claims', 'k', 'w', 'lvl', 0, 0.001, 'claims'),
    'JTSJOL': ('Job openings (JOLTS)', 'openings', 'k', 'm', 'lvl', 0, 1, 'jolts'),
}
EVENT_FIELDS = ['date', 'time', 'release', 'kind', 'period', 'values', 'y2', 'y10', 'spy', 'cal']
# cal: 1 = the day is on the agency's release calendar (FRED release dates), 0 = it is not (an archive date of ALFRED,
# not a release: leave it out of event studies), None = no calendar on file for that year
VALUE_FIELDS = ['printed', 'headline', 'prior', 'today', 'yoy', 'headline_today']
# headline_today: the same headline on today's data (the period and the one before as they stand now): with 'headline'
# it gives the revision of the reported change, not of the level (a benchmark moves every level)


# ----------------------------------------------------------------------------------------------------- fetching
def _get(url, timeout=40, tries=3, pause=2.0):
    """Body of a GET (bytes); the FRED key never appears in an error message."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}'
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:                               # noqa: BLE001 — network: retried
            last = type(e).__name__
        time.sleep(pause * (k + 1))
    raise RuntimeError(f'{_safe(url)}: {last}')


def _safe(url):
    return re.sub(r'api_key=[^&]+', 'api_key=…', url)


def _fred(path, key, **params):
    q = urllib.parse.urlencode({**params, 'api_key': key, 'file_type': 'json'})
    return json.loads(_get(f'{API}{path}?{q}').decode('utf-8'))


def fred_realtime(sid, key):
    """Every real-time period of a series: [[obs date, value | None, real-time start, real-time end]], oldest first."""
    rows, offset = [], 0
    while True:
        d = _fred('series/observations', key, series_id=sid, realtime_start='1776-07-04', realtime_end='9999-12-31',
                  observation_start=OBS_START, output_type=1, limit=100000, offset=offset, sort_order='asc')
        obs = d.get('observations') or []
        for o in obs:
            v = o.get('value')
            rows.append([o['date'], None if v in (None, '.', '') else float(v), o['realtime_start'], o['realtime_end']])
        offset += len(obs)
        if not obs or offset >= int(d.get('count') or 0):
            return rows


def fred_release(sid, key):
    r = (_fred('series/release', key, series_id=sid).get('releases') or [{}])[0]
    return {'id': r.get('id'), 'name': r.get('name'), 'link': r.get('link')}


def fred_release_dates(rid, key):
    d = _fred('release/dates', key, release_id=rid, realtime_start='1776-07-04', realtime_end='9999-12-31',
              include_release_dates_with_no_data='true', limit=10000, sort_order='asc')
    return sorted({x['date'] for x in d.get('release_dates') or []})


def _age_h(p):
    return (time.time() - p.stat().st_mtime) / 3600 if p.exists() else 1e9


def write_gz(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'))
    tmp.replace(p)


def read_gz(p, default=None):
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def fetch_fred(root, key, ids=None, max_age_h=6, pause=0.6, budget_s=420, verbose=True):
    """Real-time rows and release dates of each series; a series fetched within max_age_h hours is kept."""
    folder = Path(root) / 'cache' / 'macro-rt'
    t0, done, failed, releases = time.monotonic(), [], [], {}
    for sid in ids or SERIES:
        if time.monotonic() - t0 > budget_s:
            break
        p = folder / f'{sid}.json.gz'
        old = read_gz(p) if p.exists() else None
        if old and _age_h(p) < max_age_h:
            if old.get('release', {}).get('id'):
                releases[old['release']['id']] = old['release']
            continue
        try:
            rel = (old or {}).get('release') or fred_release(sid, key)
            time.sleep(pause)
            rows = fred_realtime(sid, key)
            if not rows:
                raise RuntimeError('no observations')
            write_gz(p, {'sid': sid, 'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                         'release': rel, 'rows': rows})
            if rel.get('id'):
                releases[rel['id']] = rel
            done.append(f'{sid} {len(rows)}')
        except Exception as e:                               # noqa: BLE001 — one series failing keeps the others
            failed.append(f'{sid}: {e}')
        time.sleep(pause)
    for rid, rel in releases.items():
        p = folder / f'release-{rid}.json'
        if _age_h(p) < max_age_h or time.monotonic() - t0 > budget_s:
            continue
        try:
            dates = fred_release_dates(rid, key)
            p.write_text(json.dumps({'id': rid, 'name': rel.get('name'), 'dates': dates}), encoding='utf-8')
        except Exception as e:                               # noqa: BLE001
            failed.append(f'release {rid}: {e}')
        time.sleep(pause)
    if verbose:
        print(f'macro calendar: FRED real-time {len(done)} series fetched ({", ".join(done) or "all fresh"}); '
              f'{len(failed)} failed{": " + "; ".join(failed) if failed else ""}', flush=True)
    return done, failed


# FOMC ---------------------------------------------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                         'september', 'october', 'november', 'december'])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS['sept'] = 9


def _text(s):
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _released(chunk):
    m = re.search(r'Released\s+([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s+(\d{4})', chunk)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    return dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()


def _ymd(s):
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()
    except ValueError:
        return None


def _statement_date(chunk):
    m = re.search(r'monetary/?(\d{8})a\.htm', chunk)                     # the press release (2009 on: monetaryYYYYMMDDa)
    if m:
        return _ymd(m.group(1))
    for href in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*Statement\s*</a>', chunk, flags=re.I):
        m = re.search(r'((?:19|20)\d{6})', href)                          # older pages: /fomc/19960131DEFAULT.htm …
        if m:
            return _ymd(m.group(1))
    return None


def _kind(text):
    t = text.lower()
    if 'cancel' in t:
        return None
    if 'notation' in t:
        return 'notation vote'
    if 'unscheduled' in t:
        return 'unscheduled'
    if 'conference call' in t:
        return 'conference call'
    return 'meeting'


def _meeting(date, kind, chunk, year):
    presser = bool(re.search(r'fomcpres+conf', chunk))
    minutes = _released(chunk)
    if minutes and minutes <= date:                     # an action's own press release, not minutes (weeks later)
        minutes = None
    return {'date': date, 'kind': kind, 'sep': 'fomcprojtabl' in chunk, 'presser': presser,
            'minutes': minutes, 'time': fomc_time(date, kind, presser)}


def fomc_time(date, kind, presser):
    """The usual clock time (ET) of a statement: 2:00 p.m. since 2013; 12:30 p.m. on the 2011–12 press-conference days,
    2:15 p.m. otherwise before; unscheduled actions and notation votes have no usual time."""
    if kind != 'meeting':
        return None
    if date >= '2013-01-01':
        return '14:00'
    if date >= '2011-04-01' and presser:
        return '12:30'
    return '14:15'


def parse_fomc_current(page):
    """{year: [meeting]} from the FOMC calendar page (the recent years and the next): each meeting's statement date —
    from its statement link, or for a meeting still ahead the last day of the meeting."""
    out = {}
    heads = list(re.finditer(r'<h4[^>]*>\s*(?:<a[^>]*>)?\s*(\d{4}) FOMC Meetings', page))
    for i, h in enumerate(heads):
        year = int(h.group(1))
        end = heads[i + 1].start() if i + 1 < len(heads) else len(page)
        tail = re.search(r'<footer|<div[^>]*id="footer|class="panel-footer|Last Update', page[h.end():end])
        panel = page[h.end():h.end() + tail.start() if tail else end]          # the last panel stops at the footer
        parts = re.split(r'(?=<div[^>]*class="[^"]*fomc-meeting__month)', panel)[1:]
        rows = []
        for chunk in parts:
            mm = re.search(r'fomc-meeting__month[^>]*>(.*?)</div>', chunk, flags=re.S)
            dd = re.search(r'fomc-meeting__date[^>]*>(.*?)</div>', chunk, flags=re.S)
            if not mm or not dd:
                continue
            month, days = _text(mm.group(1)), _text(dd.group(1))
            kind = _kind(days + ' ' + chunk[:400])
            if kind is None:
                continue
            date = _statement_date(chunk)
            if date is None:                                              # a meeting ahead: its last day
                names = [MONTHS[w.lower()] for w in re.findall(r'[A-Za-z]+', month) if w.lower() in MONTHS]
                nums = [int(x) for x in re.findall(r'\d{1,2}', days)]
                if not names or not nums:
                    continue
                m_end = names[-1]
                try:
                    date = dt.date(year, m_end, nums[-1]).isoformat()
                except ValueError:
                    continue
            meeting = _meeting(date, kind, chunk, year)
            meeting['sep'] = meeting['sep'] or '*' in days
            meeting['ahead'] = not _statement_date(chunk)               # no statement yet: the date is the last day
            if meeting['ahead']:
                meeting['presser'] = None                                # not known before the meeting
            rows.append(meeting)
        if rows:
            out[year] = rows
    return out


def parse_fomc_year(page, year):
    """[meeting] from an earlier year's page (one panel per meeting or call); only those with a statement."""
    rows = []
    for chunk in re.split(r'(?=<h5)', page)[1:]:
        head = _text(re.search(r'<h5[^>]*>(.*?)</h5>', chunk, flags=re.S).group(1)) if re.search(r'<h5', chunk) else ''
        if not re.search(r'\b(?:19|20)\d\d\b', head):
            continue
        kind = _kind(head)
        date = _statement_date(chunk)
        if kind is None or date is None or date[:4] not in (str(year), str(year + 1)):
            continue
        rows.append(_meeting(date, kind, chunk, year))
    return rows


def fetch_fomc(root, max_age_h=20, pause=0.5, verbose=True, today=None):
    folder = Path(root) / 'cache' / 'fomc'
    folder.mkdir(parents=True, exist_ok=True)
    cur, msgs = folder / 'current.json', []
    if _age_h(cur) >= max_age_h:
        try:
            years = parse_fomc_current(_get(FOMC_NOW).decode('utf-8', 'replace'))
            if years:
                cur.write_text(json.dumps({str(y): v for y, v in years.items()}), encoding='utf-8')
                msgs.append(f'calendar page: {", ".join(str(y) for y in sorted(years))}')
        except Exception as e:                               # noqa: BLE001
            msgs.append(f'calendar page failed: {e}')
    on_page = set(json.loads(cur.read_text(encoding='utf-8')).keys()) if cur.exists() else set()
    this_year = (today or dt.date.today()).year
    for year in range(FIRST_YEAR, this_year):
        p = folder / f'{year}.json'
        if str(year) in on_page or p.exists():
            continue
        try:
            rows = parse_fomc_year(_get(FOMC_YEAR.format(year=year)).decode('utf-8', 'replace'), year)
            if rows:
                p.write_text(json.dumps(rows), encoding='utf-8')
                msgs.append(f'{year}: {len(rows)}')
        except Exception as e:                               # noqa: BLE001 — a year not yet moved to its own page
            msgs.append(f'{year}: {e}')
        time.sleep(pause)
    if verbose:
        print('macro calendar: FOMC ' + ('; '.join(msgs) or 'all on file'), flush=True)


def load_fomc(root):
    folder, out = Path(root) / 'cache' / 'fomc', {}
    for p in sorted(folder.glob('[12][0-9][0-9][0-9].json')):
        for m in json.loads(p.read_text(encoding='utf-8')):
            out[m['date']] = m
    cur = folder / 'current.json'
    if cur.exists():
        for rows in json.loads(cur.read_text(encoding='utf-8')).values():
            for m in rows:
                out[m['date']] = m                                         # the current page is the newer source
    return [out[d] for d in sorted(out)]


def fetch(root, verbose=True):
    key = os.environ.get('FRED_API_KEY', '').strip()
    if key:
        fetch_fred(root, key, verbose=verbose)
    elif verbose:
        print('macro calendar: FRED_API_KEY is not set — first prints and release dates need the FRED API (a free key: '
              'fredaccount.stlouisfed.org → API keys; add it as the repository secret FRED_API_KEY)', flush=True)
    fetch_fomc(root, verbose=verbose)


# ----------------------------------------------------------------------------------------------------- real time
def _d(s):
    return dt.date.fromisoformat(s)


def period_end(d, freq):
    if freq == 'm':
        return dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1) - dt.timedelta(days=1)
    if freq == 'q':
        m = 3 * ((d.month - 1) // 3) + 3
        return dt.date(d.year + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
    return d                                                    # weekly: FRED dates a week by its last day


class RealTime:
    """One series' real-time periods: what each period's value was on any day, and what was first printed."""

    def __init__(self, rows, freq):
        self.freq = freq
        self.rows = sorted(([o, v, s, e] for o, v, s, e in rows if v is not None and math.isfinite(v)),
                           key=lambda r: (r[0], r[2]))
        self.by_obs = {}
        for o, v, s, e in self.rows:
            self.by_obs.setdefault(o, []).append((s, e, v))
        self.obs = sorted(self.by_obs)
        self.first_vintage = min((r[2] for r in self.rows), default=None)

    def value(self, obs, day):
        """The value of period `obs` as known on `day` (ISO strings), or None."""
        for s, e, v in self.by_obs.get(obs, ()):
            if s <= day <= e:
                return v
        return None

    def latest(self, obs):
        h = self.by_obs.get(obs)
        return max(h)[2] if h else None

    def first(self, obs):
        """(day first printed, value) — None when the first value came with the series' first vintage or too late to be
        the release (a period added later)."""
        h = self.by_obs.get(obs)
        if not h:
            return None
        s, _, v = min(h)
        lag = (_d(s) - period_end(_d(obs), self.freq)).days
        if s == self.first_vintage or lag < 0 or lag > MAX_LAG.get(self.freq, 120):
            return None
        return s, v

    def previous(self, obs, back=1):
        i = bisect.bisect_left(self.obs, obs) - back
        return self.obs[i] if i >= 0 else None

    def year_ago(self, obs):
        d = _d(obs)
        if self.freq == 'w':
            return (d - dt.timedelta(days=364)).isoformat()
        return dt.date(d.year - 1, d.month, d.day).isoformat()

    def known(self, days):
        """For each day (dates, any order): the newest period known that day, valued as known that day; NaN before the
        first vintage or when the newest known period is over 400 days old. The as-known basis of macro_history."""
        import numpy as np
        if not self.rows:
            return np.full(len(days), np.nan)
        if getattr(self, '_vint', None) is None:                # once per series: the newest period of each vintage
            vint = sorted({r[2] for r in self.rows})
            o = np.array([np.datetime64(r[0]) for r in self.rows])
            s = np.array([np.datetime64(r[2]) for r in self.rows])
            e = np.array([np.datetime64(r[3]) for r in self.rows])
            v = np.array([r[1] for r in self.rows], float)
            V = np.array([np.datetime64(x) for x in vint])
            best_v, pe = np.full(len(V), np.nan), np.full(len(V), np.datetime64('NaT', 'D'))
            for k, day in enumerate(V):
                live = (s <= day) & (e >= day)
                if live.any():
                    j = np.flatnonzero(live)[np.argmax(o[live])]
                    best_v[k] = v[j]
                    pe[k] = np.datetime64(period_end(_d(str(o[j])), self.freq))
            self._vint = (V, best_v, pe)
        V, best_v, pe = self._vint
        q = np.array([np.datetime64(d) for d in days], 'datetime64[D]')
        i = np.searchsorted(V, q, side='right') - 1
        ok = i >= 0
        out = np.where(ok, best_v[np.clip(i, 0, None)], np.nan)
        with np.errstate(invalid='ignore'):
            age = (q - pe[np.clip(i, 0, None)]).astype('timedelta64[D]').astype(float)
        return np.where(ok & (age <= 400), out, np.nan)


def load_rt(root, ids=None):
    """{series id: RealTime} for the series on file."""
    folder, out = Path(root) / 'cache' / 'macro-rt', {}
    for sid in ids or SERIES:
        doc = read_gz(folder / f'{sid}.json.gz')
        if doc and doc.get('rows'):
            out[sid] = RealTime(doc['rows'], SERIES[sid][3] if sid in SERIES else 'm')
    return out


def load_known(root, freq_of):
    """{series id: RealTime} for macro_history (its .known(days) gives the as-known values); freq_of: series id → its
    frequency ('w', 'm', 'q'). Series without a real-time file are left out."""
    folder, out = Path(root) / 'cache' / 'macro-rt', {}
    if not folder.exists():
        return out
    for p in folder.glob('*.json.gz'):
        sid = p.name[:-len('.json.gz')]
        if sid not in freq_of:
            continue
        doc = read_gz(p)
        if doc and doc.get('rows'):
            out[sid] = RealTime(doc['rows'], freq_of[sid])
    return out


def headline(kind, cur, prev, decimals=1):
    if cur is None:
        return None
    if kind == 'lvl':
        return cur
    if prev is None:
        return None
    if kind == 'chg':
        return cur - prev
    if prev == 0:
        return None
    if kind == 'pct':
        return 100 * (cur / prev - 1)
    if kind == 'ann':
        return 100 * ((cur / prev) ** 4 - 1) if cur / prev > 0 else None
    return None


def _r(v, d=4):
    return None if v is None or not math.isfinite(v) else round(v, d)


def series_events(sid, rt):
    """{day: {'kind': 'first'|'revision', 'period', 'values': VALUE_FIELDS}} for one series: on
    each day it printed something, the newest period it printed for the first time (else the newest it revised)."""
    _, _, _, freq, kind, dec, scale, _ = SERIES[sid]
    starts = {}
    for o, v, s, e in rt.rows:
        starts.setdefault(s, []).append(o)
    out = {}
    for day, obs_list in starts.items():
        if day == rt.first_vintage:
            continue
        firsts = [o for o in obs_list if (rt.first(o) or (None,))[0] == day]
        if firsts:
            o, kd = max(firsts), 'first'
        else:
            o, kd = max(obs_list), 'revision'
        if day[:4] < str(FIRST_YEAR):
            continue
        cur = rt.value(o, day)
        p = rt.previous(o)
        prior = rt.value(p, day) if p else None
        ya = rt.year_ago(o)
        then = rt.value(ya, day) if ya in rt.by_obs else None
        yoy = 100 * (cur / then - 1) if kind in ('pct', 'ann') and cur is not None and then not in (None, 0) else None
        h = headline(kind, cur, prior)
        h_now = headline(kind, rt.latest(o), rt.latest(p) if p else None)
        sc = (lambda x: None if x is None else x * scale)
        hs = (lambda x: _r(sc(x) if kind in ('chg', 'lvl') else x, 3))
        out[day] = {'kind': kd, 'period': o,
                    'values': [_r(sc(cur)), hs(h), _r(sc(prior)), _r(sc(rt.latest(o))), _r(yoy, 3), hs(h_now)]}
    return out


# ----------------------------------------------------------------------------------------------------- markets
def daily_changes(obs):
    """{iso day: change in basis points from the previous observation} for a yield series [(date, value)]."""
    out, prev = {}, None
    for d, v in obs:
        if v is None or not math.isfinite(v):
            continue
        if prev is not None:
            out[d.isoformat()] = round(100 * (v - prev), 1)
        prev = v
    return out


def spy_returns(doc):
    """{iso day: SPY log return into that day in basis points} from a hub daily-returns file (d0 + gaps | dates, r)."""
    if not doc or not doc.get('r'):
        return {}
    if doc.get('dates'):
        days = list(doc['dates'])
    else:
        d = dt.date.fromisoformat(doc['d0'])
        days = [doc['d0']]
        for ch in doc.get('gaps') or '':
            d += dt.timedelta(days=int(ch, 36))
            days.append(d.isoformat())
    return {days[k + 1]: int(x) for k, x in enumerate(doc['r']) if k + 1 < len(days)}


def _mean(a):
    return round(sum(a) / len(a), 1) if a else None


def day_stats(events, spy, y2):
    """Per release: SPY's and the 2-year yield's average absolute move on its days against the trading days with no
    macro release or FOMC statement at all, over the same span."""
    if not spy:
        return {}
    any_day = {e[0] for e in events}
    out = {}
    for rel in RELEASES:
        days = sorted({e[0] for e in events if e[2] == rel and e[0] in spy and e[9] != 0})
        if len(days) < 5:
            continue
        span = [d for d in spy if days[0] <= d <= days[-1]]
        quiet = [d for d in span if d not in any_day]
        a, b = [abs(spy[d]) for d in days], [abs(spy[d]) for d in quiet]
        ya = [abs(y2[d]) for d in days if d in y2]
        yb = [abs(y2[d]) for d in quiet if d in y2]
        out[rel] = {'days': len(days), 'quiet_days': len(quiet), 'from': days[0], 'to': days[-1],
                    'spy_abs': _mean(a), 'spy_abs_quiet': _mean(b), 'spy_mean': _mean([spy[d] for d in days]),
                    'spy_mean_quiet': _mean([spy[d] for d in quiet]),
                    'ratio': round(_mean(a) / _mean(b), 2) if b and _mean(b) else None,
                    'y2_abs': _mean(ya), 'y2_abs_quiet': _mean(yb)}
    return out


# ----------------------------------------------------------------------------------------------------- build
def _release_dates(root, rid):
    p = Path(root) / 'cache' / 'macro-rt' / f'release-{rid}.json'
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding='utf-8')).get('dates') or []


def build(root, spy_path=None, today=None, verbose=True):
    root = Path(root)
    today = today or dt.date.today()
    iso_today = today.isoformat()
    folder = root / 'cache' / 'macro-rt'
    docs = {sid: read_gz(folder / f'{sid}.json.gz') for sid in SERIES}
    docs = {k: v for k, v in docs.items() if v and v.get('rows')}
    fomc = load_fomc(root)
    if not docs and not fomc:
        if verbose:
            print('macro calendar build: nothing on file; skipped', flush=True)
        return None
    import macro_history as MH                                  # the yields already fetched for the macro clock
    raw = MH.load_cache(root)
    y2 = daily_changes(raw.get('DGS2') or [])
    y10 = daily_changes(raw.get('DGS10') or [])
    spy = {}
    if spy_path and Path(spy_path).exists():
        try:
            spy = spy_returns(json.loads(Path(spy_path).read_text(encoding='utf-8')))
        except ValueError:
            spy = {}
    rts = {sid: RealTime(d['rows'], SERIES[sid][3]) for sid, d in docs.items()}
    calendars = {}                                               # release key -> the agency's release dates (FRED)
    for sid, d in docs.items():
        rid = (d.get('release') or {}).get('id')
        if rid and SERIES[sid][7] not in calendars:
            calendars[SERIES[sid][7]] = set(_release_dates(root, rid))
    by_day = {}                                                  # (day, release) -> {series id: its event}
    for sid, rt in rts.items():
        for day, ev in series_events(sid, rt).items():
            if day <= iso_today:
                by_day.setdefault((day, SERIES[sid][7]), {})[sid] = ev
    events = []
    for (day, rel), evs in by_day.items():
        firsts = [e['period'] for e in evs.values() if e['kind'] == 'first']
        kind, period = ('first', max(firsts)) if firsts else ('revision', max(e['period'] for e in evs.values()))
        cal = calendars.get(rel)
        on_cal = None if not cal or day < min(cal) else int(day in cal)
        events.append([day, RELEASES[rel][2], rel, kind, period, {s: e['values'] for s, e in evs.items()},
                       y2.get(day), y10.get(day), spy.get(day), on_cal])
    for m in fomc:
        if m['date'] > iso_today or m['date'][:4] < str(FIRST_YEAR):
            continue
        info = {k: m.get(k) for k in ('kind', 'sep', 'presser', 'minutes')}
        events.append([m['date'], m.get('time'), 'fomc', 'statement', None, info, y2.get(m['date']), y10.get(m['date']),
                       spy.get(m['date']), 1])
    events.sort(key=lambda r: (r[0], r[1] or '99', r[2]))
    # the days ahead: each release's scheduled dates (FRED's release calendar) and the FOMC's next statements
    horizon = (today + dt.timedelta(days=UPCOMING_DAYS)).isoformat()
    upcoming, rel_meta = [], {}
    for sid, d in docs.items():
        r = d.get('release') or {}
        key = SERIES[sid][7]
        if r.get('id') and key not in rel_meta:
            rel_meta[key] = {'fred_id': r['id'], 'fred_name': r.get('name'), 'link': r.get('link')}
            for day in _release_dates(root, r['id']):
                if iso_today <= day <= horizon:
                    upcoming.append([day, RELEASES[key][2], key, None])
    for m in fomc:
        if iso_today <= m['date'] <= horizon:
            upcoming.append([m['date'], m.get('time'), 'fomc', {k: m.get(k) for k in ('kind', 'sep')}])
    upcoming.sort(key=lambda r: (r[0], r[1] or '99'))
    stats = day_stats(events, spy, y2)
    last = {}
    for e in events:
        last[e[2]] = e[0]
    doc = {
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'source': 'FRED / ALFRED (Federal Reserve Bank of St. Louis), federalreserve.gov (FOMC calendar)',
        'timezone': 'America/New_York',
        'releases': {k: {'name': v[0], 'agency': v[1], 'time': v[2], 'series': [s for s, x in SERIES.items() if x[7] == k],
                         'last': last.get(k), **rel_meta.get(k, {})} for k, v in RELEASES.items()},
        'series': {sid: {'label': s[0], 'short': s[1], 'unit': s[2], 'freq': s[3], 'headline': s[4], 'decimals': s[5],
                         'first_vintage': rts[sid].first_vintage if sid in rts else None, 'on_file': sid in rts}
                   for sid, s in SERIES.items()},
        'fields': EVENT_FIELDS, 'value_fields': VALUE_FIELDS,
        'events': events, 'upcoming': upcoming, 'stats': stats,
        'markets': {'y2': 'DGS2', 'y10': 'DGS10', 'spy': bool(spy),
                    'note': 'The day\'s change: yields close to close in basis points (FRED DGS2 / DGS10); SPY log return '
                            'into the day in basis points. A release at 8:30 a.m. comes before the open, so the day\'s '
                            'move is the first full reaction; one at 2:00 p.m. shares the day with the morning.'},
        'note': ('Release days and first prints from ALFRED real-time data: "printed" is the value published that day, '
                 '"prior" the period before as known that day (the release usually revises it), "today" the value now. '
                 'The headline is the change the release reported on the prior period as revised that day. Periods first '
                 'published before ALFRED kept a series\' history have no first print. Clock times are the agencies\' usual '
                 'ones; unscheduled FOMC actions have none.'),
    }
    firsts = {'generated_at': doc['generated_at'], 'series': {}}
    for sid, rt in rts.items():
        _, _, _, freq, kind, dec, scale, _ = SERIES[sid]
        rows = [(o, rt.first(o), rt.latest(o)) for o in rt.obs]
        rows = [(o, f, l) for o, f, l in rows if o[:4] >= str(FIRST_YEAR - 1)]
        firsts['series'][sid] = {'label': SERIES[sid][0], 'unit': SERIES[sid][2], 'freq': freq, 'scale': scale,
                                 'first_vintage': rt.first_vintage, 'obs': [o for o, _, _ in rows],
                                 'first': [None if f is None else _r(f[1] * scale) for _, f, _ in rows],
                                 'first_on': [None if f is None else f[0] for _, f, _ in rows],
                                 'today': [_r(l * scale) if l is not None else None for _, _, l in rows]}
    out = root / 'public'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'macro-calendar.json').write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    (out / 'macro-firsts.json').write_text(json.dumps(firsts, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        n_first = sum(1 for e in events if e[3] == 'first')
        print(f'macro-calendar.json: {len(events)} release days ({n_first} with first prints, '
              f'{sum(1 for e in events if e[2] == "fomc")} FOMC statements) since {events[0][0] if events else "—"}; '
              f'{len(upcoming)} ahead; SPY {"joined" if spy else "not given"}; series on file: {", ".join(sorted(rts)) or "none"}',
              flush=True)
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['fetch', 'build'])
    ap.add_argument('--root', default='hist')
    ap.add_argument('--spy', default=None, help="the hub's daily-returns file for SPY (data/research/paths/moves/a/SPY.json)")
    a = ap.parse_args()
    if a.cmd == 'fetch':
        fetch(a.root)
    else:
        build(a.root, spy_path=a.spy)


if __name__ == '__main__':
    main()
