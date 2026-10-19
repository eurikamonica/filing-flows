"""People, index and analysts (4.18): the 13F managers and officials as pages of their own, what copying them would have
returned, insider trades against their history, an early look at the next 13F, the S&P 500's likely next members, and how
often analysts' price targets are reached.

  managers     the largest 13F managers (and a configured list of well-known ones): latest portfolio, last quarter's
               adds and cuts, and a clone portfolio — each 13F bought at the close of the first trading day after it was
               filed (usually about 45 days after the quarter), value-weighted over the common-share positions with a
               price, held (drifting) until the next filing; price returns (dividends left out for the clone and SPY alike)
  officials    every member of Congress with scored trades (smart money, branch smart-history): the midpoint-weighted
               average excess return over SPY in the 63 trading days after each disclosure (a sale counts when the stock
               then lagged), their committees (unitedstates/congress-legislators) and trades in sectors under those
               committees' jurisdiction ("potential overlap": a documented committee → sector map, config/people.json)
  insiders     an event study over the scored open-market Form 4 trades: by side, role, size and whether other insiders
               traded the same way within 30 days → the average excess return over SPY in the 63 trading days after the
               disclosure, with a 95% interval clustered by month; each new insider trade gets the matching row
  preview13f   before a 13F is due: what the manager's own earlier filings already show for the quarter (Form 4s as a 10%
               owner, 13D / 13G filings) and the portfolio's weights drifted with prices; frozen with a timestamp, scored
               when the 13F arrives (direction hit rate; weight error against the unchanged-portfolio guess)
  sp500        S&P 500 rule screen: US filer, market cap at least the threshold, the last four quarters' net income summed
               positive and the latest quarter positive, traded value at least 0.75× market cap a year and 250,000 shares
               a month, not already a member (iShares IVV holdings); every candidate's first appearance is kept and
               scored when it joins
  pt_hits      analysts' mean price target (daily consensus snapshots, branch consensus-history): one target a month per
               stock, reached within 12 months or not, and the price against the target after 12 months; until a
               window has fully elapsed it only counts as "touched so far"

Publish (public/ → disclosures/data/research/people/): index.json, managers.json, m/<cik>.json, officials.json,
o/<slug>.json, insider_context.json, preview13f.json, sp500.json, pt_hits.json, status.json.

    python app/people.py run --root people --hub disclosures/docs/data --smart smart --consensus cons --legislators cl
"""
import argparse
import datetime as dt
import gzip
import json
import math
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import read_json  # noqa: E402
import market as MK  # noqa: E402
import smart as SM  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'people.json'
FUND = re.compile(r'\bETF\b|\bETN\b|SPDR|ISHARES|PROSHARES|DIREXION|VANGUARD|INVESCO QQQ|SELECT SECTOR|\bFUND\b|GRAYSCALE|\bTRUST\b|'
                  r'\bNOTES?\b|\bWARRANTS?\b|\bRIGHTS?\b|\bUNITS?\b|DEPOSITARY|ACQUISITION CORP', re.I)
FRAMES = 'https://data.sec.gov/api/xbrl/frames/{tax}/{concept}/{unit}/{period}.json'
SIZE_EDGES = [(0, 1e5, '<$100K'), (1e5, 1e6, '$100K–$1M'), (1e6, 1e7, '$1M–$10M'), (1e7, float('inf'), '$10M+')]
ROLE_GROUP = {'CEO': 'CEO', 'CFO': 'CFO', 'President': 'President / COO', 'COO': 'President / COO', 'Chair': 'Chair',
              'Director': 'Director', '10% owner': '10% owner', 'Officer': 'Other officer', 'Other': 'Other officer'}
MIN_CELL = 30            # decisions a row of the event study needs; fewer → the broader row is used
SUFFIXES = re.compile(r'\b(INC|INCORPORATED|LLC|L L C|LP|L P|LTD|LIMITED|CORP|CORPORATION|CO|COMPANY|PLC|SA|AG|NV|THE|GROUP|HOLDINGS?|'
                      r'MANAGEMENT|MGMT|ADVISORS?|ADVISERS?|PARTNERS|CAPITAL|INVESTMENTS?|ASSET|ASSOCIATES)\b')


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def log(*a):
    print(*a, flush=True)


def r4(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def cfg_load(path=None):
    d = read_json(Path(path) if path else CONFIG, {}) or {}
    d.setdefault('top_managers', 150)
    d.setdefault('keep_managers', 300)
    d.setdefault('positions_cap', 400)
    d.setdefault('managers_include', {})
    d.setdefault('sp500_min_mcap', 22.7e9)
    d.setdefault('committee_sectors', {})
    d.setdefault('defense_sic', [[3480, 3489], [3720, 3729], [3760, 3769], [3795, 3795], [3812, 3812]])
    return d


def slugify(s, extra=''):
    s = re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:60].strip('-')
    return (s + ('-' + extra if extra else '')) or extra or 'x'


def company_key(s):
    """A manager's or holder's name for matching across filings: upper case, no punctuation, no legal or generic words."""
    s = SUFFIXES.sub(' ', SM.norm_name(s))
    return re.sub(r'\s+', ' ', s).strip()


def person_key(s):
    """A person's name for matching: lower case, no punctuation, no middle initials or suffixes ('David J. Taylor' → 'david taylor')."""
    s = re.sub(r'[^a-z ]', ' ', (s or '').lower().replace('.', ' '))
    w = [x for x in s.split() if len(x) > 1 and x not in ('jr', 'sr', 'ii', 'iii', 'iv', 'hon', 'dr', 'mr', 'mrs', 'ms')]
    return ' '.join([w[0], w[-1]]) if len(w) >= 2 else ' '.join(w)


def iso(o):
    return dt.date.fromordinal(int(o)).isoformat()


def ordinal(day):
    return dt.date.fromisoformat(str(day)[:10]).toordinal()


def wj(path, obj):
    SM.wj(path, obj)


# ------------------------------------------------------------------ prices
class Px:
    """Daily closes (and volumes) per ticker from the Hub's price cache and smart-history's top-ups, aligned on demand."""

    def __init__(self, dirs):
        self.dirs = [Path(d) for d in dirs if d]
        self.s = {}

    def get(self, t):
        if t in self.s:
            return self.s[t]
        best = None
        for d in self.dirs:
            p = d / SM.price_file(t)
            if not p.exists():
                continue
            rows = (SM.load_gz(p, {}) or {}).get('rows') or []
            rows = [r for r in rows if r and len(r) > 1 and r[1] and r[1] > 0]
            if len(rows) < 5:
                continue
            ser = (np.array([ordinal(r[0]) for r in rows], dtype=np.int64), np.array([float(r[1]) for r in rows]),
                   np.array([float(r[2]) if len(r) > 2 and r[2] is not None else np.nan for r in rows]))
            if best is None or ser[0][-1] > best[0][-1]:
                best = ser
        self.s[t] = best
        return best

    def close_on(self, t, day, after=False, tol=6):
        """The close on `day` (ordinal) or the last one before it (after=True: the first one on or after it), within tol days."""
        s = self.get(t)
        if s is None:
            return None
        d, c = s[0], s[1]
        if after:
            i = int(np.searchsorted(d, day, 'left'))
            return float(c[i]) if i < len(d) and d[i] - day <= tol else None
        i = int(np.searchsorted(d, day, 'right')) - 1
        return float(c[i]) if i >= 0 and day - d[i] <= tol else None


# ------------------------------------------------------------------ managers: 13F portfolios
def compact_snapshots(m, cap):
    """A manager's cached 13F history → [[period, filed, total_usd, [[cusip, shares, value], …] or None]] (common shares
    only; the first quarter on file lists no positions in the cache, only its total)."""
    out = []
    for s in m.get('snapshots') or []:
        if not s.get('complete') or s.get('confidential') or not s.get('period'):
            continue
        pos = [[c.get('cusip'), c.get('shares') or 0, c.get('value_usd') or 0] for c in s.get('changes') or []
               if c.get('status') != 'EXIT' and c.get('put_call') == 'NONE' and c.get('share_type') == 'SH' and (c.get('value_usd') or 0) > 0]
        pos.sort(key=lambda x: -x[2])
        out.append([s['period'], (s.get('filed') or s.get('available_at') or '')[:10], s.get('total_usd') or 0, pos[:cap] if pos else None,
                    {c.get('cusip'): [c.get('status'), r4(c.get('delta_pct'), 1)] for c in (s.get('changes') or [])[:600]
                     if c.get('put_call') == 'NONE' and c.get('status') in ('NEW', 'EXIT', 'INCREASE', 'DECREASE')} if pos else None])
    out.sort(key=lambda x: x[0])
    return out


def update_managers(root, hub, cfg, minutes=None):
    """cache/managers.json.gz: every manager's name and latest assets; the 13F history (compact) of the largest ones and
    the configured list. Only the files whose git blob changed since the last run are read (smart.GitBlobs)."""
    root, hub = Path(root), Path(hub)
    path = root / 'cache' / 'managers.json.gz'
    cache = SM.load_gz(path, {}) or {}
    have = cache.setdefault('managers', {})
    hdir = hub / 'cache' / 'holdings'
    git = SM.GitBlobs(hdir)
    shas = git.listing()
    on_disk = {p.name: p for p in hdir.glob('*.json.gz')}
    names = sorted(n for n in (set(shas) | set(on_disk)) if n.endswith('.json.gz'))

    def stamp(n):
        if n in shas:
            return shas[n]
        st = on_disk[n].stat()
        return f'{st.st_size}-{int(st.st_mtime)}'

    todo = [n for n in names if (have.get(n[:-8]) or {}).get('sha') != stamp(n)]
    git.prefetch([shas[n] for n in todo if n not in on_disk and n in shas])
    t0, read, errors = time.time(), 0, 0
    full = {}
    for n in todo:
        if minutes and time.time() - t0 > minutes * 60:
            break
        try:
            raw = on_disk[n].read_bytes() if n in on_disk else git.read(shas[n])
            m = json.loads(gzip.decompress(raw)) if raw else None
        except (OSError, ValueError, EOFError):
            m = None
        if not m:
            errors += 1
            continue
        cik = n[:-8]
        snaps = compact_snapshots(m, cfg['positions_cap'])
        aum = snaps[-1][2] if snaps else 0
        have[cik] = {'sha': stamp(n), 'name': (m.get('label') or m.get('name') or cik)[:90], 'aum': aum,
                     'period': snaps[-1][0] if snaps else None}
        full[cik] = snaps
        read += 1
    git.close()
    if shas:
        listed = {n[:-8] for n in shas if n.endswith('.json.gz')}
        for cik in [c for c in have if c not in listed]:
            del have[cik]
    keep = set(sorted(have, key=lambda c: -(have[c].get('aum') or 0))[:cfg['keep_managers']]) | {str(c) for c in cfg['managers_include']}
    hist = cache.setdefault('history', {})
    for cik in list(hist):
        if cik not in keep or cik not in have:
            del hist[cik]
    for cik, snaps in full.items():
        if cik in keep:
            hist[cik] = snaps
    missing = [c for c in keep if c in have and c not in hist]       # entered the top since the last full read
    if missing:
        for c in missing:
            have[c]['sha'] = None                                      # read again next run
    cache['updated'] = now()
    SM.save_gz(path, cache)
    return {'managers': len(have), 'changed': len(todo), 'read': read, 'errors': errors, 'kept': len(hist), 'reread_next': len(missing),
            'seconds': round(time.time() - t0)}


def trading_days(px):
    spy = px.get('SPY')
    return spy[0] if spy is not None else None


def clone_backtest(snaps, U, px, today=None):
    """Each 13F with positions bought at the first close after its filing date, value-weighted over the positions with a
    price, held until the next one; NAV against SPY over the same days."""
    days = trading_days(px)
    if days is None:
        return None
    today = today or int(days[-1])
    legs = [s for s in snaps if s[3] and s[1]]
    if not legs:
        return None
    spy_c = px.get('SPY')[1]
    nav, spy_nav = [1.0], [1.0]
    dates = []
    covers, n_legs = [], 0
    for k, s in enumerate(legs):
        start_ord = ordinal(s[1]) + 1
        i0 = int(np.searchsorted(days, start_ord, 'left'))
        # the last 13F is held until today, or until 50 days after the next quarter end when no newer 13F came (a manager
        # that stopped filing is not held forever)
        end_ord = ordinal(legs[k + 1][1]) + 1 if k + 1 < len(legs) else min(today, ordinal(quarter_end_after(s[0])) + 50) + 1
        i1 = int(np.searchsorted(days, end_ord, 'left'))
        if i0 >= len(days) or i1 <= i0:
            continue
        span = days[i0:i1 + 1] if i1 < len(days) else days[i0:]
        tot = sum(p[2] for p in s[3])
        w, paths = [], []
        for cusip, _sh, val in s[3]:
            t = U.cusip_ticker.get(cusip) if U else None
            ser = px.get(t) if t else None
            if ser is None:
                continue
            d, c = ser[0], ser[1]
            j = np.searchsorted(d, span, 'right') - 1
            if j[0] < 0 or span[0] - d[j[0]] > 6:          # no close near the start: left out (coverage says how much)
                continue
            p = c[np.maximum(j, 0)]                         # a series that stops (merger, delisting) stays at its last close
            paths.append(p / p[0])
            w.append(val)
        if not w or tot <= 0:
            continue
        covers.append(float(sum(w) / tot))
        w = np.array(w) / sum(w)
        port = (np.vstack(paths) * w[:, None]).sum(0)
        sp = spy_c[i0:i0 + len(span)] / spy_c[i0]
        base, sbase = nav[-1], spy_nav[-1]
        for j in range(1, len(span)):
            nav.append(base * port[j])
            spy_nav.append(sbase * sp[j])
            dates.append(int(span[j]))
        n_legs += 1
    if len(dates) < 20:
        return None
    nav = np.array(nav[1:])
    spy_nav = np.array(spy_nav[1:])
    years = max((dates[-1] - dates[0]) / 365.25, 1e-9)

    def mdd(x):
        peak = np.maximum.accumulate(np.r_[1.0, x])
        return float((np.r_[1.0, x] / peak - 1).min())
    months, seen = [], set()
    for i in range(len(dates) - 1, -1, -1):              # the last day of each month
        m = iso(dates[i])[:7]
        if m not in seen:
            seen.add(m)
            months.append([m, r4(nav[i]), r4(spy_nav[i])])
    months.reverse()
    return {'start': iso(dates[0]), 'end': iso(dates[-1]), 'first_filing': legs[0][1], 'filings': n_legs,
            'total': r4(nav[-1] - 1), 'spy_total': r4(spy_nav[-1] - 1),
            'cagr': r4(nav[-1] ** (1 / years) - 1) if years >= 0.5 else None, 'spy_cagr': r4(spy_nav[-1] ** (1 / years) - 1) if years >= 0.5 else None,
            'excess': r4(nav[-1] - spy_nav[-1]), 'max_dd': r4(mdd(nav)), 'spy_max_dd': r4(mdd(spy_nav)), 'years': r4(years, 2),
            'coverage': r4(sum(covers) / len(covers)) if covers else None, 'monthly': months}


def manager_pages(root, hub, cfg, U, px, smart_root=None):
    """managers.json (summary rows) and m/<cik>.json (one page each) for the largest managers and the configured list."""
    cache = SM.load_gz(Path(root) / 'cache' / 'managers.json.gz', {}) or {}
    have, hist = cache.get('managers') or {}, cache.get('history') or {}
    include = {str(c): v for c, v in (cfg.get('managers_include') or {}).items()}
    top = [c for c in sorted(hist, key=lambda c: -(have.get(c, {}).get('aum') or 0))][:cfg['top_managers']]
    top += [c for c in include if c in hist and c not in top]
    records = smart_records(smart_root, ['f:' + c for c in top]) if smart_root else {}
    rows, pages = [], {}
    for cik in top:
        snaps = hist[cik]
        info = have.get(cik) or {}
        last = next((s for s in reversed(snaps) if s[3]), None)
        if not last:
            continue
        tot = sum(p[2] for p in last[3]) or 1
        chg = last[4] or {}
        holdings = []
        for cusip, sh, val in last[3][:40]:
            t = U.cusip_ticker.get(cusip) if U else ''
            st = chg.get(cusip) or [None, None]
            holdings.append([t or '', re.sub(r'\s*/[A-Z]{2,}/?\s*$', '', U.name(t) if (U and t) else '')[:48], r4(val / last[2] if last[2] else val / tot), val, st[0], st[1]])
        adds = sorted(([U.cusip_ticker.get(c, '') if U else '', v[0], v[1]] for c, v in chg.items() if v[0] in ('NEW', 'INCREASE')),
                      key=lambda x: (x[1] != 'NEW', -(x[2] or 0)))[:12]
        cuts = sorted(([U.cusip_ticker.get(c, '') if U else '', v[0], v[1]] for c, v in chg.items() if v[0] in ('EXIT', 'DECREASE')),
                      key=lambda x: (x[1] != 'EXIT', x[2] or 0))[:12]
        bt = clone_backtest(snaps, U, px)
        name = include.get(cik, {}).get('label') or info.get('name') or cik
        slug = slugify(re.sub(r'\b(INC|LLC|LP|LTD|CORP|CO)\b\.?', '', name, flags=re.I), cik)
        rec = records.get('f:' + cik)
        page = {'cik': cik, 'name': name, 'slug': slug, 'aum': last[2], 'period': last[0], 'filed': last[1], 'positions': len(last[3]),
                'holdings_fields': ['ticker', 'name', 'weight', 'value', 'status', 'delta_pct'], 'holdings': holdings,
                'adds': [a for a in adds if a[0]], 'cuts': [a for a in cuts if a[0]], 'clone': bt, 'record': rec,
                'quarters': [[s[0], s[1], s[2]] for s in snaps]}
        pages[cik] = page
        rows.append([cik, name, slug, last[2], last[0], last[1], len(last[3]), (bt or {}).get('start'), (bt or {}).get('end'),
                     (bt or {}).get('total'), (bt or {}).get('spy_total'), (bt or {}).get('excess'), (bt or {}).get('max_dd'),
                     (bt or {}).get('coverage'), (rec or {}).get('hit'), (rec or {}).get('decisions')])
    fields = ['cik', 'name', 'slug', 'aum', 'period', 'filed', 'positions', 'clone_start', 'clone_end', 'clone_total', 'spy_total',
              'excess', 'max_dd', 'coverage', 'hit', 'decisions']
    return {'fields': fields, 'rows': rows}, pages


def smart_records(smart_root, ids):
    """{actor id: stats} from smart-history's public/a/<group>/<bucket>.json (the actors' records)."""
    out = {}
    if not smart_root:
        return out
    by_file = defaultdict(list)
    for a in ids:
        g = {'f': 'f13', 'i': 'ins', 'g': 'gov', 'e': 'etf'}.get(a[:1])
        if g:
            by_file[(g, SM.bucket(a))].append(a)
    for (g, b), aids in by_file.items():
        d = read_json(Path(smart_root) / 'public' / 'a' / g / f'{b}.json', {}) or {}
        for a in aids:
            x = (d.get('actors') or {}).get(a)
            if x:
                out[a] = x.get('stats')
    return out


# ------------------------------------------------------------------ officials
def load_legislators(cl_dir):
    """(people {bioguide: {...}}, committees {thomas id: name}, membership {bioguide: [committee ids]}) from a checkout
    of unitedstates/congress-legislators (or None)."""
    if not cl_dir or not Path(cl_dir, 'legislators-current.yaml').exists():
        return None
    import yaml
    leg = yaml.safe_load(open(Path(cl_dir) / 'legislators-current.yaml', encoding='utf-8')) or []
    com = yaml.safe_load(open(Path(cl_dir) / 'committees-current.yaml', encoding='utf-8')) or []
    mem = yaml.safe_load(open(Path(cl_dir) / 'committee-membership-current.yaml', encoding='utf-8')) or {}
    people = {}
    for x in leg:
        bid = (x.get('id') or {}).get('bioguide')
        if not bid:
            continue
        nm, term = x.get('name') or {}, (x.get('terms') or [{}])[-1]
        last = person_key(nm.get('last') or '').split(' ')[-1]
        firsts = {(x or '').strip().lower()[:1] for x in (nm.get('first'), nm.get('nickname'), nm.get('middle')) if x}
        people[bid] = {'bioguide': bid, 'name': nm.get('official_full') or f"{nm.get('first', '')} {nm.get('last', '')}".strip(),
                       'keys': {person_key(nm.get('official_full')), person_key(f"{nm.get('first', '')} {nm.get('last', '')}"),
                                person_key(f"{nm.get('nickname', '')} {nm.get('last', '')}") if nm.get('nickname') else '',
                                person_key(f"{nm.get('middle', '')} {nm.get('last', '')}") if nm.get('middle') else ''} - {''},
                       'last': last, 'initials': firsts,
                       'chamber': 'US Senate' if term.get('type') == 'sen' else 'US House', 'party': term.get('party'), 'state': term.get('state')}
    names = {}
    for c in com:
        names[c['thomas_id']] = c['name']
        for s in c.get('subcommittees') or []:
            names[c['thomas_id'] + s['thomas_id']] = f"{c['name']} — {s['name']}"
    member = defaultdict(list)
    for cid, ms in mem.items():
        for m in ms or []:
            if m.get('bioguide'):
                member[m['bioguide']].append([cid, m.get('title') or ''])
    return {'people': people, 'committees': names, 'membership': dict(member)}


def match_legislator(L, name, chamber=None):
    """The current member a disclosure name belongs to: the full name, else the same last name in the same chamber with
    a first name, nickname or middle name of the same initial ('Daniel Crenshaw' → Dan Crenshaw); None when not unique."""
    if not L:
        return None
    k = person_key(name)
    pool = [p for p in L['people'].values() if not chamber or p['chamber'] == chamber]
    hits = [p for p in pool if k in p['keys']]
    if len(hits) == 1:
        return hits[0]
    if hits or not k:
        return None
    words = k.split(' ')
    first = words[0][:1]
    hits = [p for p in pool if p.get('last') == words[-1] and first in p.get('initials', set())]
    return hits[0] if len(hits) == 1 else None


def sector_index(site_index):
    """{ticker: (sector id, sic)} from the Sankey site's data/index.json."""
    out = {}
    rows = (site_index or {}).get('companies') if isinstance(site_index, dict) else (site_index or [])
    for r in rows or []:
        t = MK.canon((r.get('ticker') or '').replace('.', '-'))
        if t:
            out.setdefault(t, (r.get('sector') or 'other', r.get('sic')))
    return out


def jurisdiction(cfg, cid, sector, sic):
    """The committee's matching rule for a stock (None when it does not fall under it). A subcommittee id inherits its
    full committee's rule unless it has its own."""
    rules = cfg.get('committee_sectors') or {}
    rule = rules.get(cid) or rules.get(cid[:4])
    if not rule:
        return None
    if sector and sector in (rule.get('sectors') or []):
        return rule.get('label') or sector
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    ranges = list(rule.get('sic') or []) + (cfg['defense_sic'] if rule.get('defense') else [])
    for lo, hi in ranges:
        if lo <= s <= hi:
            return rule.get('label') or 'defense'
    return None


def officials(smart_root, hub, cfg, L, sectors, today=None):
    """officials.json rows and o/<slug>.json pages."""
    today = today or dt.date.today()
    trades_pub = read_json(Path(hub) / 'market' / 'officials-trades.json', {}) or {}
    recent = defaultdict(list)
    for t in trades_pub.get('trades') or []:
        if t.get('asset_type') not in (None, '', 'ST') or t.get('ticker_status') not in (None, 'listed'):
            continue
        recent[person_key(t.get('person'))].append(t)
    actors = {}
    gdir = Path(smart_root) / 'public' / 'a' / 'gov' if smart_root else None
    for p in sorted(gdir.glob('*.json')) if gdir and gdir.exists() else []:
        for aid, x in ((read_json(p, {}) or {}).get('actors') or {}).items():
            actors[aid] = x
    names = {person_key(x['name']): aid for aid, x in actors.items()}
    for k, ts in recent.items():                         # people with recent trades but no scored record yet
        if k not in names and ts:
            aid = 'g:' + SM.norm_name(ts[0]['person'])
            actors.setdefault(aid, {'name': ts[0]['person'], 'sub': ts[0].get('jurisdiction') or '', 'stats': {}, 'trades': []})
            names[k] = aid
    rows, pages = [], {}
    for aid, x in actors.items():
        name, chamber = x.get('name') or aid[2:], x.get('sub') or ''
        tr = x.get('trades') or []
        w = np.array([abs(t[3] or 0) or 1.0 for t in tr if t[7] is not None])
        fol = np.array([t[2] * max(-1.0, min(1.0, t[7])) for t in tr if t[7] is not None])
        exs = np.array([t[2] * max(-1.0, min(1.0, t[5])) for t in tr if t[5] is not None])
        perf = {'n': len(tr), 'scored': int(len(fol)),
                'follow': r4(float((fol * w).sum() / w.sum())) if len(fol) else None,
                'trade': r4(float(exs.mean())) if len(exs) else None,
                'hit': r4(float((exs > 0).mean())) if len(exs) else None,
                'first': min((t[0] for t in tr), default=None), 'last': max((t[0] for t in tr), default=None)}
        leg = match_legislator(L, name, chamber if chamber in ('US House', 'US Senate') else None)
        coms = []
        if leg:
            for cid, title in (L['membership'].get(leg['bioguide']) or []):
                coms.append([cid, L['committees'].get(cid, cid), title])
        k = person_key(name)
        recent_tr = sorted(recent.get(k, []), key=lambda t: t.get('date') or '', reverse=True)
        overlaps = []
        seen = set()
        for t in recent_tr:
            tk = MK.canon(t.get('ticker_canon') or t.get('ticker') or '')
            sec, sic = sectors.get(tk, (None, None))
            for cid, cname, _title in coms:
                j = jurisdiction(cfg, cid, sec, sic)
                if j and (tk, t.get('date'), cid[:4]) not in seen:
                    seen.add((tk, t.get('date'), cid[:4]))
                    overlaps.append({'ticker': tk, 'date': t.get('date'), 'type': t.get('type'), 'amount_min': t.get('amount_min'),
                                     'amount_max': t.get('amount_max'), 'filed': t.get('filed_date'), 'owner': t.get('owner'),
                                     'committee': cname, 'committee_id': cid, 'area': j, 'source_url': t.get('source_url')})
        slug = slugify(name)
        page = {'id': aid, 'name': name, 'slug': slug, 'chamber': chamber, 'bioguide': (leg or {}).get('bioguide'),
                'party': (leg or {}).get('party'), 'state': (leg or {}).get('state'), 'committees': coms, 'performance': perf,
                'record': x.get('stats') or {},
                'recent_fields': ['date', 'ticker', 'type', 'amount_min', 'amount_max', 'owner', 'filed', 'source_url'],
                'recent': [[t.get('date'), MK.canon(t.get('ticker_canon') or t.get('ticker') or ''), t.get('type'), t.get('amount_min'),
                            t.get('amount_max'), t.get('owner'), t.get('filed_date'), t.get('source_url')] for t in recent_tr[:60]],
                'scored_fields': ['date', 'ticker', 'd', 'midpoint', 'excess_trade', 'excess_follow', 'disclosed'],
                'scored': [[t[0], t[1], t[2], t[3], t[5], t[7], t[9]] for t in tr[:80]],
                'overlaps': overlaps[:40]}
        pages[slug] = page
        rows.append([slug, name, chamber, page['party'], page['state'], len(coms), perf['n'], perf['scored'], perf['follow'], perf['trade'],
                     perf['hit'], len(overlaps), perf['last'] or (recent_tr[0]['date'] if recent_tr else None), len(recent_tr)])
    rows.sort(key=lambda r: (-(r[7] or 0), r[1]))
    fields = ['slug', 'name', 'chamber', 'party', 'state', 'committees', 'trades', 'scored', 'follow', 'trade', 'hit', 'overlaps', 'last', 'recent']
    return {'fields': fields, 'rows': rows}, pages


# ------------------------------------------------------------------ insiders: event study
def size_bucket(usd):
    for lo, hi, lab in SIZE_EDGES:
        if lo <= (usd or 0) < hi:
            return lab
    return SIZE_EDGES[-1][2]


def load_insider_trades(smart_root):
    """Every scored insider trade in smart-history's actor files: [day ordinal, ticker, d, usd, role group, excess from the
    trade, excess from the disclosure, actor id]."""
    out = []
    lo, hi = dt.date(2000, 1, 1).toordinal(), dt.date.today().toordinal()
    idir = Path(smart_root) / 'public' / 'a' / 'ins' if smart_root else None
    for p in sorted(idir.glob('*.json')) if idir and idir.exists() else []:
        for aid, x in ((read_json(p, {}) or {}).get('actors') or {}).items():
            role = ROLE_GROUP.get(x.get('sub') or '', 'Other officer')
            for t in x.get('trades') or []:
                if not t[0] or not t[1]:
                    continue
                try:
                    o = ordinal(t[0])
                except ValueError:
                    continue
                if lo <= o <= hi:                              # a typo'd year (0024, 2027) in a filing is left out
                    out.append([o, t[1], int(t[2]), float(t[3] or 0), role, t[5], t[7], aid])
    return out


def clusters(trades, window=30):
    """For each trade: True when another insider traded the same stock the same way within `window` days."""
    by = defaultdict(list)
    for i, t in enumerate(trades):
        by[(t[1], t[2])].append(i)
    flag = [False] * len(trades)
    for idx in by.values():
        idx.sort(key=lambda i: trades[i][0])
        for a in range(len(idx)):
            i = idx[a]
            for b in range(a + 1, len(idx)):
                j = idx[b]
                if trades[j][0] - trades[i][0] > window:
                    break
                if trades[j][7] != trades[i][7]:
                    flag[i] = flag[j] = True
    return flag


def cell_stats(xs, months):
    """Mean, a 95% interval clustered by calendar month, median, share above zero."""
    x = np.clip(np.array(xs, dtype=float), -1.0, 1.0)
    n = len(x)
    m = float(x.mean())
    g = defaultdict(float)
    for v, mo in zip(x - m, months):
        g[mo] += v
    se = math.sqrt(sum(v * v for v in g.values())) / n if n else float('nan')
    if len(g) > 1:
        se *= math.sqrt(len(g) / (len(g) - 1))
    return {'n': n, 'mean': r4(m), 'lo': r4(m - 1.96 * se), 'hi': r4(m + 1.96 * se), 'median': r4(float(np.median(x))),
            'hit': r4(float((x > 0).mean())), 'months': len(g)}


def insider_study(trades):
    """The event-study table: decisions (one per insider, stock and side within 30 days) by side, role, size, cluster,
    with the broader rows the lookup falls back to."""
    flag = clusters(trades)
    dec = {}
    for i, t in enumerate(trades):
        if t[6] is None:
            continue
        key = (t[7], t[1], t[2], t[0] // 30)
        dec.setdefault(key, []).append(i)
    cells = defaultdict(lambda: ([], []))
    for key, idx in dec.items():
        t = trades[idx[0]]
        usd = sum(trades[i][3] for i in idx)
        fol = float(np.mean([trades[i][6] for i in idx]))
        cl = any(flag[i] for i in idx)
        mo = iso(t[0])[:7]
        side = 'buy' if t[2] > 0 else 'sale'
        for k in ((side,), (side, t[4]), (side, t[4], size_bucket(usd)), (side, t[4], size_bucket(usd), 'cluster' if cl else 'alone')):
            cells[k][0].append(fol)
            cells[k][1].append(mo)
    table = {}
    for k, (xs, ms) in cells.items():
        if len(xs) >= 10:
            table['|'.join(k)] = cell_stats(xs, ms)
    return table


def lookup(table, side, role, usd, cluster):
    """The most specific row with enough decisions: side · role · size · cluster, then broader."""
    keys = [(side, role, size_bucket(usd), 'cluster' if cluster else 'alone'), (side, role, size_bucket(usd)), (side, role), (side,)]
    for k in keys:
        row = table.get('|'.join(k))
        if row and row['n'] >= MIN_CELL:
            return '|'.join(k), row
    return None, None


def insider_context(smart_root, hub, today=None):
    trades = load_insider_trades(smart_root)
    table = insider_study(trades) if trades else {}
    d = read_json(Path(hub) / 'market' / 'insiders.json', {}) or {}
    latest = [t for t in d.get('latest') or [] if t.get('code') in ('P', 'S')]
    recent = []
    by = defaultdict(set)
    for t in latest:
        by[(t.get('ticker'), t.get('code'))].add(t.get('insider'))
    for t in latest:
        side = 'buy' if t['code'] == 'P' else 'sale'
        role = ROLE_GROUP.get(t.get('role') or '', 'Other officer')
        cl = len(by[(t.get('ticker'), t.get('code'))]) > 1
        if t.get('plan_10b5_1'):
            key, row = None, None
        else:
            key, row = lookup(table, side, role, t.get('value'), cl)
        recent.append({'date': t.get('date'), 'ticker': t.get('ticker'), 'insider': t.get('insider'), 'role': role, 'title': t.get('title'),
                       'side': side, 'value': t.get('value'), 'shares': t.get('shares'), 'price': t.get('price'), 'cluster': cl,
                       'plan': bool(t.get('plan_10b5_1')), 'url': t.get('url'), 'cell': key, 'expected': row})
    rows = [[k] + [v[x] for x in ('n', 'mean', 'lo', 'hi', 'median', 'hit', 'months')] for k, v in sorted(table.items())]
    first = min((t[0] for t in trades), default=None)
    last = max((t[0] for t in trades), default=None)
    return {'generated_at': now(), 'trades': len(trades), 'window': [iso(first) if first else None, iso(last) if last else None],
            'table_fields': ['cell', 'n', 'mean', 'lo', 'hi', 'median', 'hit', 'months'], 'table': rows, 'recent': recent,
            'min_cell': MIN_CELL,
            'note': ('Open-market Form 4 purchases and sales by officers, directors and 10% owners (pre-arranged 10b5-1 plan trades are '
                     'not scored). One decision per insider, stock and side in a 30-day span. The figure is the stock\'s return less '
                     'SPY\'s over the 63 trading days after the trade was disclosed (what someone copying it could have had), capped '
                     'at ±100%; the 95% interval is clustered by calendar month, because trades in the same month share the market. '
                     'History, not a forecast for any one trade. Not investment advice.')}


# ------------------------------------------------------------------ 13F preview
def quarter_end_after(period):
    y, m = int(period[:4]), int(period[5:7])
    m += 3
    if m > 12:
        y, m = y + 1, m - 12
    return (dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1) - dt.timedelta(days=1)).isoformat()


def preview_evidence(cik, name, hub, smart_root, since, until):
    """What the manager's own filings already show between two dates: Form 4s as a reporting owner (name match) and
    13D / 13G filings (filer CIK or name match) → [{ticker, d, source, date, detail}]."""
    out = []
    key = company_key(name)
    for t in SM.load_gz(Path(hub) / 'cache' / 'insiders' / 'trades.json.gz', []) or []:
        if t.get('code') not in ('P', 'S') or not (since < (t.get('date') or '') <= until):
            continue
        if key and company_key(t.get('insider')) == key:
            out.append({'ticker': MK.canon(t.get('ticker') or ''), 'd': 1 if t['code'] == 'P' else -1, 'source': 'Form 4',
                        'date': t.get('date'), 'detail': f"{'bought' if t['code'] == 'P' else 'sold'} {t.get('shares') or 0:,.0f} shares"
                        + (f" at ${t['price']:,.2f}" if t.get('price') else '')})
    st = read_json(Path(hub) / 'market' / 'stakes.json', {}) or {}
    for r in st.get('latest') or []:
        if not (since < (r.get('filed') or '') <= until):
            continue
        if str(r.get('filer_cik') or '').lstrip('0') != str(cik).lstrip('0') and company_key(r.get('filer')) != key:
            continue
        tk = MK.canon(r.get('ticker') or '')
        if not tk:
            continue
        prev, pct = r.get('prev_percent'), r.get('percent')
        d = -1 if r.get('exit') else 1 if r.get('new') or prev is None else (1 if (pct or 0) > prev else -1 if (pct or 0) < prev else 0)
        if d:
            out.append({'ticker': tk, 'd': d, 'source': f"Schedule {r.get('form')}", 'date': r.get('filed'),
                        'detail': f"{pct:g}% of the class" + (f" (from {prev:g}%)" if prev is not None else '') if pct is not None else ''})
    return out


def drift_weights(last, U, px, at_ord):
    """The last 13F's weights moved with prices to a date (no trades assumed)."""
    vals = {}
    q_ord = ordinal(last[0])
    for cusip, _sh, val in last[3] or []:
        t = U.cusip_ticker.get(cusip) if U else None
        if not t:
            continue
        a, b = px.close_on(t, q_ord), px.close_on(t, at_ord)
        vals[t] = vals.get(t, 0) + (val * b / a if a and b else val)
    tot = sum(vals.values()) or 1
    return {t: v / tot for t, v in vals.items()}


def preview13f(root, hub, cfg, U, px, smart_root=None, today=None):
    """Current previews (frozen into cache/preview_ledger.json with a timestamp) and the scored history."""
    today = today or dt.date.today()
    cache = SM.load_gz(Path(root) / 'cache' / 'managers.json.gz', {}) or {}
    have, hist = cache.get('managers') or {}, cache.get('history') or {}
    lpath = Path(root) / 'cache' / 'preview_ledger.json'
    ledger = read_json(lpath, {}) or {}
    top = sorted(hist, key=lambda c: -(have.get(c, {}).get('aum') or 0))[:cfg['top_managers']]
    top += [str(c) for c in cfg.get('managers_include') or {} if str(c) in hist and str(c) not in top]
    stamp = now()
    current = []
    for cik in top:
        snaps = hist[cik]
        last = next((s for s in reversed(snaps) if s[3]), None)
        if not last:
            continue
        target = quarter_end_after(last[0])
        name = have.get(cik, {}).get('name') or cik
        ev = preview_evidence(cik, name, hub, smart_root, last[0], min(target, today.isoformat()))
        at = min(ordinal(target), today.toordinal())
        w = drift_weights(last, U, px, at)
        base = {}
        tot = sum(v for _c, _s, v in last[3]) or 1
        for cusip, _sh, val in last[3]:
            t = U.cusip_ticker.get(cusip) if U else None
            if t:
                base[t] = base.get(t, 0) + val / tot
        preds = {}
        for e in ev:
            p = preds.setdefault(e['ticker'], {'ticker': e['ticker'], 'd': 0, 'evidence': []})
            p['evidence'].append(e)
            p['d'] = int(np.sign(sum(x['d'] for x in p['evidence'])))
        rows = sorted(preds.values(), key=lambda p: -len(p['evidence']))
        for p in rows:
            p['weight_last'] = r4(base.get(p['ticker'], 0.0))
            p['weight_drift'] = r4(w.get(p['ticker'], 0.0))
        key = f'{cik}|{target}'
        led = ledger.setdefault(key, {'cik': cik, 'name': name, 'quarter': target, 'base_period': last[0], 'versions': []})
        sig = json.dumps([[p['ticker'], p['d']] for p in rows], sort_keys=True)
        drift_top = sorted(w.items(), key=lambda kv: -kv[1])[:25]
        if not led['versions'] or led['versions'][-1].get('sig') != sig:
            led['versions'].append({'at': stamp, 'sig': sig, 'preds': [[p['ticker'], p['d']] for p in rows],
                                    'drift': [[t, r4(v)] for t, v in drift_top]})
        if rows:
            current.append({'cik': cik, 'name': name, 'quarter': target, 'due': (dt.date.fromisoformat(target) + dt.timedelta(days=45)).isoformat(),
                            'base_period': last[0], 'first_made': led['versions'][0]['at'], 'predictions': rows[:20]})
    # scoring: a ledger entry whose quarter has arrived in the manager's 13F history
    scored = []
    for key, led in ledger.items():
        snaps = hist.get(led['cik']) or []
        got = next((s for s in snaps if s[0] == led['quarter'] and s[3]), None)
        if not got:
            continue
        vers = [v for v in led['versions'] if v['at'][:10] <= (got[1] or '9999')]
        if not vers:
            continue
        v = vers[-1]
        chg = got[4] or {}
        actual = {}
        tot = sum(x[2] for x in got[3]) or 1
        wt = {}
        for cusip, _sh, val in got[3]:
            t = U.cusip_ticker.get(cusip) if U else None
            if t:
                wt[t] = wt.get(t, 0) + val / tot
        for cusip, (status, _dp) in chg.items():
            t = U.cusip_ticker.get(cusip) if U else None
            if t:
                actual[t] = 1 if status in ('NEW', 'INCREASE') else -1
        hits = [1 if actual.get(t, 0) == d else 0 for t, d in v['preds'] if d]
        drift = dict(v.get('drift') or [])
        names = set(wt) | set(drift)
        mae_drift = float(np.mean([abs(wt.get(t, 0) - drift.get(t, 0)) for t in names])) if names else None
        led['scored'] = {'filed': got[1], 'predictions': len(hits), 'right': sum(hits), 'mae_drift_top25': r4(mae_drift)}
        scored.append([led['name'], led['cik'], led['quarter'], v['at'], got[1], len(hits), sum(hits), r4(mae_drift)])
    wj(lpath, ledger)
    tot_p = sum(s[5] for s in scored)
    return {'generated_at': stamp, 'previews': current, 'scored_fields': ['name', 'cik', 'quarter', 'made', 'filed', 'predictions', 'right', 'mae_drift_top25'],
            'scored': scored, 'hit_rate': r4(sum(s[6] for s in scored) / tot_p) if tot_p else None, 'predictions_scored': tot_p,
            'note': ('An estimate of the next 13F from what the manager has already filed in the quarter — Form 4s it filed as a '
                     '10% owner and its Schedule 13D / 13G filings — and its last 13F\'s weights moved with prices. Each preview is '
                     'frozen with its time and scored when the 13F arrives. Most of a 13F is not visible early; an empty preview '
                     'means no early filing, not no change. Not investment advice.')}


# ------------------------------------------------------------------ S&P 500 candidates
def fetch_frame(tax, concept, unit, period, ua, timeout=60):
    req = urllib.request.Request(FRAMES.format(tax=tax, concept=concept, unit=unit, period=period), headers={'User-Agent': ua, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode('utf-8'))
    return {str(x['cik']): [x.get('val'), x.get('end'), x.get('accn')] for x in d.get('data') or [] if x.get('val') is not None}


def calendar_quarters(today, n):
    """The last n calendar quarters that have ended at least 50 days ago ('CY2026Q2' …), newest first."""
    out = []
    d = today - dt.timedelta(days=50)
    y, q = d.year, (d.month - 1) // 3 + 1
    q -= 1
    if q == 0:
        y, q = y - 1, 4
    for _ in range(n):
        out.append(f'CY{y}Q{q}')
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def update_frames(root, hub, today, ua, offline=False):
    """Net income per company for the last six calendar quarters (the Hub's frames cache, else fetched) and shares
    outstanding for the last three quarter ends (dei, fetched) → cache/frames/*.json."""
    fdir = Path(root) / 'cache' / 'frames'
    fdir.mkdir(parents=True, exist_ok=True)
    errors = []
    qs = calendar_quarters(today, 6)
    years = sorted({f'CY{q[2:6]}' for q in qs})                 # annual frames: Q4 = the year less its first three quarters
    for p in qs + years:
        out = fdir / f'NetIncomeLoss-{p}.json'
        hub_f = Path(hub) / 'cache' / 'frames' / f'NetIncomeLoss-{p}.json.gz'
        if out.exists() and (time.time() - out.stat().st_mtime) < 7 * 86400:
            continue
        if hub_f.exists():
            d = SM.load_gz(hub_f, {}) or {}
            wj(out, {str(k): [v, None, None] for k, v in d.items()} if d and not isinstance(next(iter(d.values())), list) else d)
            continue
        if offline:
            continue
        try:
            wj(out, fetch_frame('us-gaap', 'NetIncomeLoss', 'USD', p, ua))
            time.sleep(0.3)
        except Exception as exc:
            errors.append(f'NetIncomeLoss {p}: {str(exc)[:80]}')
    for p in qs[:3]:
        out = fdir / f'Shares-{p}I.json'
        if out.exists() and (time.time() - out.stat().st_mtime) < 7 * 86400 or offline:
            continue
        try:
            wj(out, fetch_frame('dei', 'EntityCommonStockSharesOutstanding', 'shares', p + 'I', ua))
            time.sleep(0.3)
        except Exception as exc:
            errors.append(f'shares {p}: {str(exc)[:80]}')
    return {'quarters': qs, 'errors': errors[:10]}


def sp500(root, hub, cfg, px, cons_root=None, today=None):
    today = today or dt.date.today()
    fdir = Path(root) / 'cache' / 'frames'
    qs = calendar_quarters(today, 6)
    ni = {p: read_json(fdir / f'NetIncomeLoss-{p}.json', {}) or {} for p in qs}
    annual = {}
    for q in qs:
        y = f'CY{q[2:6]}'
        if y not in annual:
            annual[y] = read_json(fdir / f'NetIncomeLoss-{y}.json', {}) or {}

    def quarter_value(cik, q):
        """A calendar quarter's net income; Q4 (rarely reported on its own) as the year less Q1–Q3."""
        v = ni.get(q, {}).get(cik)
        v = v[0] if isinstance(v, list) else v
        if v is not None or not q.endswith('Q4'):
            return v
        y = q[:6]
        fy = annual.get(y, {}).get(cik)
        fy = fy[0] if isinstance(fy, list) else fy
        parts = []
        for k in ('Q1', 'Q2', 'Q3'):
            x = read_json(fdir / f'NetIncomeLoss-{y}{k}.json', {}).get(cik) if f'{y}{k}' not in ni else ni[f'{y}{k}'].get(cik)
            parts.append(x[0] if isinstance(x, list) else x)
        return fy - sum(parts) if fy is not None and all(x is not None for x in parts) else None
    shares = {}
    for p in reversed(qs[:3]):                                  # oldest first: the newest wins
        for cik, v in (read_json(fdir / f'Shares-{p}I.json', {}) or {}).items():
            if v and v[0]:
                shares[cik] = v
    members = set()
    cons = read_json(Path(cons_root) / 'cache' / 'constituents.json', {}) if cons_root else {}
    spx = (cons or {}).get('spx') or {}
    for m in spx.get('members') or []:
        t = m[0] if isinstance(m, (list, tuple)) else m.get('ticker') if isinstance(m, dict) else m
        if t:
            members.add(MK.canon(str(t).replace('.', '-')))
    tick_rows = (read_json(Path(hub) / 'cache' / 'prices' / 'sec-tickers.json', {}) or {}).get('rows') or []
    by_cik = defaultdict(list)
    for r in tick_rows:
        t = MK.canon((r.get('ticker') or '').replace('.', '-'))
        if t and r.get('cik'):
            by_cik[str(r['cik']).lstrip('0')].append((t, r.get('title') or ''))
    in_index_cik = {c for c, ts in by_cik.items() if any(t in members for t, _ in ts)}
    rows = []
    t_ord = today.toordinal()
    for cik, ts in by_cik.items():
        if cik in in_index_cik or not shares.get(cik):
            continue
        t, title = ts[0]
        if FUND.search(title or ''):
            continue
        vals = [quarter_value(cik, p) for p in qs]
        last4 = None
        for s in range(0, 3):                                  # the newest four consecutive quarters on file
            win = vals[s:s + 4]
            if len(win) == 4 and all(v is not None for v in win):
                last4 = win
                break
        if not last4:
            continue
        ser = px.get(t)
        if ser is None:
            continue
        d, c, v = ser
        if t_ord - d[-1] > 7:
            continue
        mcap = float(c[-1]) * float(shares[cik][0])
        if mcap < cfg['sp500_min_mcap']:
            continue
        k = d >= t_ord - 365
        dv = float(np.nansum(c[k] * v[k])) if k.any() else 0.0
        months = max(1.0, (int(d[k][-1]) - int(d[k][0])) / 30.4) if k.sum() > 1 else 1.0
        monthly_shares = float(np.nansum(v[k])) / months if k.any() else 0.0
        rows.append({'ticker': t, 'name': title[:60], 'cik': cik, 'mcap': round(mcap), 'price': r4(float(c[-1]), 2),
                     'shares': shares[cik][0], 'shares_date': shares[cik][1], 'ni_4q': round(sum(last4)), 'ni_last': round(last4[0]),
                     'eligible_earnings': sum(last4) > 0 and last4[0] > 0, 'turnover': r4(dv / mcap) if mcap else None,
                     'monthly_shares': round(monthly_shares)})
    for r in rows:
        r['eligible_liquidity'] = (r['turnover'] or 0) >= 0.75 and r['monthly_shares'] >= 250_000
        r['eligible'] = r['eligible_earnings'] and r['eligible_liquidity']
    rows.sort(key=lambda r: (not r['eligible'], -r['mcap']))
    lpath = Path(root) / 'cache' / 'sp500_calls.json'
    calls = read_json(lpath, {}) or {}
    for i, r in enumerate([r for r in rows if r['eligible']]):
        c = calls.setdefault(r['ticker'], {'first': today.isoformat(), 'mcap': r['mcap'], 'rank': i + 1, 'cik': r['cik']})
        c['last'] = today.isoformat()
        r['first_flagged'] = c['first']
    if members and len(members) >= 450:                        # a full members list: score the earlier calls
        for t, c in calls.items():
            if t in members and not c.get('joined'):
                c['joined'] = today.isoformat()
    wj(lpath, calls)
    hist = sorted(([t, c['first'], c.get('last'), c.get('joined'), c.get('rank')] for t, c in calls.items()), key=lambda r: r[1], reverse=True)
    resolved = [h for h in hist if h[3] or (dt.date.fromisoformat(h[1]) + dt.timedelta(days=365)) <= today]
    return {'generated_at': now(), 'threshold': cfg['sp500_min_mcap'], 'members': len(members), 'members_source': spx.get('source'),
            'members_at': spx.get('at'), 'quarters': qs[:4],
            'fields': ['ticker', 'name', 'mcap', 'price', 'ni_4q', 'ni_last', 'turnover', 'monthly_shares', 'eligible_earnings',
                       'eligible_liquidity', 'eligible', 'first_flagged'],
            'rows': [[r.get(k) for k in ['ticker', 'name', 'mcap', 'price', 'ni_4q', 'ni_last', 'turnover', 'monthly_shares',
                                         'eligible_earnings', 'eligible_liquidity', 'eligible', 'first_flagged']] for r in rows[:120]],
            'history_fields': ['ticker', 'first_flagged', 'last_flagged', 'joined', 'rank'], 'history': hist[:300],
            'joined_within_year': sum(1 for h in resolved if h[3] and (dt.date.fromisoformat(h[3]) - dt.date.fromisoformat(h[1])).days <= 365),
            'resolved': len(resolved),
            'note': ('A rule screen, not S&P\'s decision: the index committee also weighs sector balance and its own float and '
                     'domicile tests, and adds names only when a seat opens. Net income from the SEC\'s XBRL frames (calendar '
                     'quarters), shares outstanding from the cover page (dei), price and volume from the Hub. Threshold: S&P\'s '
                     'published minimum market cap, set in config/people.json. Not investment advice.')}


# ------------------------------------------------------------------ analysts' price targets
def pt_hits(cons_root, px, today=None):
    today = today or dt.date.today()
    t_ord = today.toordinal()
    rows, by_sector = [], defaultdict(lambda: [0, 0, 0, 0, 0, []])
    cdir = Path(cons_root) / 'companies' if cons_root else None
    first_seen = None
    for p in sorted(cdir.glob('*.json')) if cdir and cdir.exists() else []:
        rec = read_json(p, {}) or {}
        t = MK.canon((rec.get('ticker') or '').replace('.', '-'))
        snaps = rec.get('snapshots') or {}
        if not t or not snaps:
            continue
        months = {}
        for day in sorted(snaps):                               # the first snapshot of each month
            v = snaps[day]
            if isinstance(v, list) and len(v) >= 8 and v[5] and v[7]:
                months.setdefault(day[:7], (day, float(v[5]), float(v[7])))
        if not months:
            continue
        ser = px.get(t)
        n = resolved = hits = touched = pending = 0
        errs = []
        for day, tgt, p0 in months.values():
            first_seen = min(first_seen or day, day)
            n += 1
            s_ord = ordinal(day)
            if ser is None:
                pending += 1
                continue
            d, c = ser[0], ser[1]
            k = (d > s_ord) & (d <= s_ord + 365)
            path = c[k]
            up = tgt >= p0
            reached = bool(len(path)) and (bool((path >= tgt).any()) if up else bool((path <= tgt).any()))
            elapsed = s_ord + 365 <= int(d[-1])
            if elapsed:
                resolved += 1
                hits += int(reached)
                j = int(np.searchsorted(d, s_ord + 365, 'right')) - 1
                if j >= 0:
                    errs.append(float(c[j]) / tgt - 1)
            else:
                pending += 1
                touched += int(reached)
        sec = rec.get('sector') or 'other'
        b = by_sector[sec]
        b[0] += n
        b[1] += resolved
        b[2] += hits
        b[3] += touched
        b[4] += pending
        b[5] += errs
        rows.append([t, (rec.get('name') or '')[:50], sec, n, resolved, hits, r4(hits / resolved) if resolved else None, pending, touched,
                     r4(float(np.median(errs))) if errs else None, max(months)])
    rows.sort(key=lambda r: (-(r[4] or 0), -(r[3] or 0)))
    sectors = [[s, b[0], b[1], b[2], r4(b[2] / b[1]) if b[1] else None, b[4], b[3], r4(float(np.median(b[5]))) if b[5] else None]
               for s, b in sorted(by_sector.items())]
    full_from = (dt.date.fromisoformat(first_seen + '-01' if len(first_seen) == 7 else first_seen) + dt.timedelta(days=365)).isoformat() if first_seen else None
    return {'generated_at': now(), 'tracking_since': first_seen, 'first_full_results': full_from,
            'fields': ['ticker', 'name', 'sector', 'targets', 'resolved', 'hits', 'hit_rate', 'pending', 'touched_so_far', 'median_error_12m', 'last_month'],
            'rows': rows, 'sector_fields': ['sector', 'targets', 'resolved', 'hits', 'hit_rate', 'pending', 'touched_so_far', 'median_error_12m'],
            'sectors': sectors,
            'note': ('One mean price target a month per stock (the first daily consensus snapshot of the month). A target is reached '
                     'when any close in the next 12 months gets to it; the hit rate counts only targets whose 12 months are over, and '
                     'targets still inside their window only show as "touched so far". Error: the close 12 months later against the '
                     'target. The record starts with the consensus snapshots on file. Not investment advice.')}


# ------------------------------------------------------------------ run
def run(args):
    root = Path(args.root)
    pub = root / 'public'
    cfg = cfg_load(args.config)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    st = {'started': now(), 'errors': []}
    hub = Path(args.hub)
    U = MK.Universe(hub)
    px = Px([hub / 'cache' / 'prices', Path(args.smart) / 'cache' / 'prices' if args.smart else None])

    def step(name, f):
        t0 = time.time()
        try:
            out = f()
            st[name] = {'seconds': round(time.time() - t0)}
            return out
        except Exception as exc:                               # one part failing leaves the others published
            import traceback
            traceback.print_exc()
            st['errors'].append(f'{name}: {exc.__class__.__name__}: {str(exc)[:200]}')
            return None

    st['managers_read'] = step('managers_read', lambda: update_managers(root, hub, cfg, minutes=args.minutes))
    mg = step('managers', lambda: manager_pages(root, hub, cfg, U, px, args.smart))
    if mg:
        summary, pages = mg
        for p in (pub / 'm').glob('*.json') if (pub / 'm').exists() else []:
            p.unlink()
        for cik, page in pages.items():
            wj(pub / 'm' / f'{cik}.json', page)
        wj(pub / 'managers.json', {'generated_at': now(), **summary,
                                   'note': ('The largest 13F managers by reported assets, plus a few well-known ones. Clone: each 13F bought at the close '
                                            'of the first trading day after it was filed, weighted by value over the common-share positions with a '
                                            'price (coverage = that share of the portfolio), held until the next 13F. Price returns, dividends left '
                                            'out for the clone and SPY alike; no costs. 13Fs list only US long positions at quarter end. Not investment advice.')})
        st['managers_published'] = len(pages)
    L = load_legislators(args.legislators)
    site_ix = read_json(Path(args.site_index), {}) if args.site_index else {}
    sectors = sector_index(site_ix)
    off = step('officials', lambda: officials(args.smart, hub, cfg, L, sectors, today))
    if off:
        summary, pages = off
        for p in (pub / 'o').glob('*.json') if (pub / 'o').exists() else []:
            p.unlink()
        for slug, page in pages.items():
            wj(pub / 'o' / f'{slug}.json', page)
        wj(pub / 'officials.json', {'generated_at': now(), **summary, 'committees_source': 'unitedstates/congress-legislators' if L else None,
                                    'note': ('Performance: each disclosed trade\'s stock return less SPY\'s over the 63 trading days after the '
                                             'disclosure (a sale counts when the stock then lagged), weighted by the middle of the reported '
                                             'amount range; "trade" measures the same from the trade date. Potential overlap: a trade in a '
                                             'sector under one of the member\'s committees (config/people.json lists the map); it is a '
                                             'fact pattern, not a finding of wrongdoing. Not investment advice.')})
        st['officials_published'] = len(pages)
    ic = step('insiders', lambda: insider_context(args.smart, hub, today))
    if ic:
        wj(pub / 'insider_context.json', ic)
        st['insider_trades'] = ic['trades']
    pv = step('preview13f', lambda: preview13f(root, hub, cfg, U, px, args.smart, today))
    if pv:
        wj(pub / 'preview13f.json', pv)
        st['previews'] = len(pv['previews'])
    st['frames'] = step('frames', lambda: update_frames(root, hub, today, SM.SEC_UA, offline=args.offline))
    sp = step('sp500', lambda: sp500(root, hub, cfg, px, args.consensus, today))
    if sp:
        wj(pub / 'sp500.json', sp)
        st['sp500_candidates'] = sum(1 for r in sp['rows'] if r[10])
    pt = step('pt_hits', lambda: pt_hits(args.consensus, px, today))
    if pt:
        wj(pub / 'pt_hits.json', pt)
        st['pt_stocks'] = len(pt['rows'])
    st['finished'] = now()
    wj(pub / 'index.json', {'generated_at': now(), 'parts': ['managers', 'officials', 'insider_context', 'preview13f', 'sp500', 'pt_hits'],
                            'status': {k: v for k, v in st.items() if k != 'errors'}, 'errors': st['errors'][:10]})
    flat = {k: v for k, v in st.items() if isinstance(v, (int, float, str))}
    wj(pub / 'status.json', {**flat, 'errors': len(st['errors'])})
    log(json.dumps({k: v for k, v in st.items()}, default=str)[:3000])
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--root', default='people')
    r.add_argument('--hub', default='disclosures/docs/data')
    r.add_argument('--smart', default=None, help='a checkout of the branch smart-history (public/a, cache/prices)')
    r.add_argument('--consensus', default=None, help='a checkout of the branch consensus-history (companies/, cache/constituents.json)')
    r.add_argument('--legislators', default=None, help='a checkout of unitedstates/congress-legislators (the three *-current.yaml files)')
    r.add_argument('--site-index', default=None, help="the Sankey site's data/index.json (sectors and SIC codes)")
    r.add_argument('--config', default=None)
    r.add_argument('--minutes', type=float, default=30)
    r.add_argument('--offline', action='store_true')
    r.add_argument('--today', default=None)
    a = ap.parse_args()
    if a.cmd == 'run':
        st = run(a)
        return 0 if len(st['errors']) < 6 else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
