"""Which US indices each company belongs to — now and before (public/members.json, run by etf.build; the site's company
pages show the tags, the video studio's leaderboards filter by them).

  now      the full holdings of the ETFs that track each index (N-PORT, or the sponsor's daily file for SPY / DIA /
           MDY): S&P 500 (IVV, VOO, SPY), Nasdaq-100 (QQQ, QQQM), Dow Jones Industrial Average (DIA), S&P MidCap 400 (IJH,
           MDY), S&P SmallCap 600 (IJR), Russell 1000 (IWB), Russell 2000 (IWM), Russell 3000 (IWV — the broad market).
           For the S&P 500, Wikipedia's member list (with each company's CIK and the date it joined) as well.
  before   S&P 500: Wikipedia's dated table of additions and removals — the last revision of “List of S&P 500
           companies” that carried it — then the member list month by month in the page's later revisions (a removal
           dated to the month it left the list). Dow: “Historical components of the Dow Jones Industrial Average”, one
           table per change, matched to the site's companies by name. The other indices from this module's first build
           on (each build's members kept in cache/members/seen.json), so their “former” members grow from now.
Tickers of the past are mapped to today's through the CIK in Wikipedia's member lists where they carry one (FB → META);
companies delisted or gone are not on the site and are left out.
"""
import datetime as dt
import html
import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = 'Filing Flows research filingflows@gmail.com'
INDEXES = [('sp500', 'S&P 500', ['IVV', 'VOO', 'SPY'], 450), ('ndx', 'Nasdaq-100', ['QQQ', 'QQQM'], 90), ('dji', 'Dow Jones Industrial Average', ['DIA'], 28),
           ('sp400', 'S&P MidCap 400', ['IJH', 'MDY'], 350), ('sp600', 'S&P SmallCap 600', ['IJR'], 500), ('r1000', 'Russell 1000', ['IWB'], 900),
           ('r2000', 'Russell 2000', ['IWM'], 1700), ('r3000', 'Russell 3000', ['IWV'], 2500)]
WIKI = 'https://en.wikipedia.org/w/api.php'
SP500_PAGE = 'List_of_S&P_500_companies'
DOW_PAGE = 'Historical_components_of_the_Dow_Jones_Industrial_Average'
SNAP_FROM = dt.date(2024, 1, 1)                      # monthly revisions of the S&P 500 list from here (the change table ends)


def get(url, timeout=40, tries=4):
    """A page, politely: Wikipedia answers 429 to quick bursts, so wait and try again (5, 15, 45 seconds)."""
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, text/html'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode('utf-8', 'replace')
            time.sleep(1.2)
            return body
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or k == tries - 1:
                raise
            time.sleep(5 * 3 ** k)


# ------------------------------------------------------------------ html tables (with rowspan / colspan)
class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.heads, self._h, self._htext = [], [], [], None, ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('h2', 'h3', 'h4'):
            self._h, self._htext = tag, ''
        if tag == 'table':
            self.stack.append({'id': a.get('id'), 'cls': a.get('class') or '', 'rows': [], 'head': self.heads[-1] if self.heads else '', 'cell': None, 'row': None})
        elif self.stack:
            t = self.stack[-1]
            if tag == 'tr':
                t['row'] = []
            elif tag in ('td', 'th') and t['row'] is not None:
                t['cell'] = {'text': '', 'rs': int(re.sub(r'\D', '', a.get('rowspan') or '1') or 1), 'cs': int(re.sub(r'\D', '', a.get('colspan') or '1') or 1), 'th': tag == 'th'}
            elif tag == 'br' and t['cell'] is not None:
                t['cell']['text'] += ' '
            elif tag in ('sup', 'style') and t['cell'] is not None:
                t['cell']['skip'] = t['cell'].get('skip', 0) + 1

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3', 'h4') and self._h == tag:
            self.heads.append(re.sub(r'\[edit\]|\s+', ' ', self._htext).strip())
            self._h = None
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ('sup', 'style') and t['cell'] is not None and t['cell'].get('skip'):
            t['cell']['skip'] -= 1
        elif tag in ('td', 'th') and t['cell'] is not None and t['row'] is not None:
            c = t['cell']; c['text'] = re.sub(r'\s+', ' ', c['text']).strip(); t['row'].append(c); t['cell'] = None
        elif tag == 'tr' and t['row'] is not None:
            t['rows'].append(t['row']); t['row'] = None
        elif tag == 'table':
            done = self.stack.pop()
            self.tables.append({'id': done['id'], 'cls': done['cls'], 'head': done['head'], 'rows': grid(done['rows'])})

    def handle_data(self, data):
        if self._h:
            self._htext += data
        if self.stack and self.stack[-1]['cell'] is not None and not self.stack[-1]['cell'].get('skip'):
            self.stack[-1]['cell']['text'] += data


def grid(rows):
    """Rows of cells with rowspan / colspan → rows of texts (a spanning cell repeated where it spans), and whether the
    row is a header row."""
    out, carry = [], {}
    for r in rows:
        line, col = [], 0
        cells = list(r)
        k = 0
        while k < len(cells) or col in carry:
            if col in carry:
                text, left = carry[col]
                line.append(text)
                if left > 1:
                    carry[col] = (text, left - 1)
                else:
                    del carry[col]
                col += 1
                continue
            c = cells[k]; k += 1
            for j in range(c['cs']):
                line.append(c['text'])
                if c['rs'] > 1:
                    carry[col] = (c['text'], c['rs'] - 1)
                col += 1
        out.append({'cells': line, 'th': all(c['th'] for c in r) if r else False})
    return out


def tables(page_html):
    p = Tables()
    p.feed(page_html)
    return p.tables


def iso(text):
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%d %B %Y'):
        try:
            return dt.datetime.strptime(text.strip().replace('.', ''), fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text or '')
    return '-'.join(m.groups()) if m else None


def sym(s):
    return re.sub(r'[^A-Z0-9\-]', '', str(s or '').upper().replace('.', '-'))


# ------------------------------------------------------------------ Wikipedia: the S&P 500 list and its history
def sp500_members(tabs):
    """[{symbol, name, cik, added}] from the member table (id constituents)."""
    t = next((x for x in tabs if x['id'] == 'constituents'), None)
    if not t or not t['rows']:
        return []
    head = [c.lower() for c in t['rows'][0]['cells']]
    col = lambda *names: next((i for i, h in enumerate(head) if any(n in h for n in names)), None)
    i_s, i_n, i_c, i_d = col('symbol', 'ticker'), col('security', 'company'), col('cik'), col('date added', 'date first added')
    out = []
    for r in t['rows'][1:]:
        c = r['cells']
        if i_s is None or len(c) <= i_s:
            continue
        out.append({'symbol': sym(c[i_s]), 'name': c[i_n] if i_n is not None and i_n < len(c) else '',
                    'cik': (c[i_c].lstrip('0') if i_c is not None and i_c < len(c) and c[i_c].strip().isdigit() else None),
                    'added': iso(c[i_d]) if i_d is not None and i_d < len(c) else None})
    return [x for x in out if x['symbol']]


def sp500_changes(tabs):
    """[(date, added symbol, added name, removed symbol, removed name)] from the change table (id changes)."""
    t = next((x for x in tabs if x['id'] == 'changes'), None)
    if not t:
        return []
    out = []
    for r in t['rows']:
        c = r['cells']
        if r['th'] or len(c) < 5:
            continue
        d = iso(c[0])
        if d:
            out.append((d, sym(c[1]), c[2], sym(c[3]), c[4]))
    return out


def revisions(title, starts, cache):
    """{month start: revision id} — the revision in force at each date (one request lists every revision since the first
    month; a past month's revision never changes, so it is kept)."""
    have = cache.get('rev', {})
    need = [d for d in starts if d.isoformat() not in have]
    if need:
        q = urllib.parse.urlencode({'action': 'query', 'prop': 'revisions', 'titles': title, 'rvlimit': 'max', 'rvdir': 'newer',
                                    'rvstart': (min(need) - dt.timedelta(days=120)).isoformat() + 'T00:00:00Z', 'rvprop': 'ids|timestamp', 'format': 'json'})
        revs, cont = [], {}
        for _ in range(20):
            body = json.loads(get(WIKI + '?' + q + ('&' + urllib.parse.urlencode(cont) if cont else '')))
            page = next(iter(body['query']['pages'].values()))
            revs += [(r['timestamp'][:10], r['revid']) for r in page.get('revisions') or []]
            cont = body.get('continue') or {}
            if not cont:
                break
        revs.sort()
        for d in need:
            before = [rid for day, rid in revs if day < d.isoformat()]
            if before:
                have[d.isoformat()] = before[-1]
    cache['rev'] = have
    return have


def revision_html(revid):
    q = urllib.parse.urlencode({'action': 'parse', 'oldid': revid, 'prop': 'text', 'format': 'json', 'formatversion': 2})
    return json.loads(get(WIKI + '?' + q))['parse']['text']


def months(start, today):
    out, d = [], start.replace(day=1)
    while d <= today:
        out.append(d)
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


# ------------------------------------------------------------------ Wikipedia: the Dow's compositions
SUFFIX = r'\b(the|inc|incorporated|corp|corporation|company|co|plc|ltd|limited|group|holdings|technologies|international|n ?v|s ?a)\b'


def norm_name(s):
    s = re.sub(r'\(.*?\)', ' ', html.unescape(str(s or '')).lower())
    s = re.sub(r'[^a-z0-9 ]+', ' ', s.replace('&', ' and '))
    s = re.sub(SUFFIX, ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def dow_compositions(tabs):
    """[(date, [company names])], oldest first: each wikitable under a dated heading is the index from that date."""
    out = []
    for t in tabs:
        if 'wikitable' not in t['cls']:
            continue
        d = iso(t['head'] or '')
        if not d:
            continue
        names = []
        for r in t['rows']:
            for c in r['cells']:
                if '↓' in c:                           # left the index on that date
                    continue
                c = re.sub(r'[↑†‡*]', '', c).strip()
                if c and not re.fullmatch(r'[\d\s,.%-]*', c) and len(c) < 90:
                    names.append(c)
        if len(names) >= 10:
            out.append((d, names))
    return sorted(out)


# ------------------------------------------------------------------ collect (network) and build
def collect(root, today=None):
    """Fetch what changed: today's S&P 500 list, the Dow's history page (weekly), the S&P list's monthly revisions."""
    today = today or dt.date.today()
    cdir = Path(root) / 'cache' / 'members'
    cdir.mkdir(parents=True, exist_ok=True)
    cpath = cdir / 'wiki.json'
    try:
        cache = json.loads(cpath.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    stamp = cache.get('fetched', {})
    def fresh(k, days):
        return stamp.get(k) and stamp[k] > (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    try:
        if not fresh('sp500', 1):
            q = urllib.parse.urlencode({'action': 'parse', 'page': SP500_PAGE, 'prop': 'text', 'format': 'json', 'formatversion': 2})
            cache['sp500_now'] = sp500_members(tables(json.loads(get(WIKI + '?' + q))['parse']['text']))
            stamp['sp500'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if not fresh('dow', 7):
            q = urllib.parse.urlencode({'action': 'parse', 'page': DOW_PAGE, 'prop': 'text', 'format': 'json', 'formatversion': 2})
            cache['dow'] = dow_compositions(tables(json.loads(get(WIKI + '?' + q))['parse']['text']))
            stamp['dow'] = dt.datetime.now(dt.timezone.utc).isoformat()
        revs = revisions(SP500_PAGE, months(SNAP_FROM, today), cache)
        snaps = cache.setdefault('snaps', {})
        for k, rid in sorted(revs.items()):
            if str(rid) in snaps:
                continue
            tabs = tables(revision_html(rid))
            snaps[str(rid)] = {'members': [[m['symbol'], m['cik']] for m in sp500_members(tabs)], 'changes': sp500_changes(tabs)}
    except Exception as exc:                               # noqa: BLE001 — what was fetched is kept
        print('members: wikipedia', str(exc)[:200])
    cache['fetched'] = stamp
    cpath.write_text(json.dumps(cache, separators=(',', ':')), encoding='utf-8')
    return cache


BASE = Path(__file__).resolve().parents[1] / 'config' / 'sp500-history.json'   # the change table as of mid-2024, kept


def same_company(a, b):
    """Two names of one company (a ticker is reused: CCI was Countrywide Credit in 1997, Crown Castle now)."""
    na, nb = norm_name(a).split(), norm_name(b).split()
    return not na or not nb or na[0] == nb[0] or na[0].startswith(nb[0]) or nb[0].startswith(na[0])


def sp500_history(cache, cik_ticker, ticker_name=None):
    """{ticker: [[from, to or None], …]} from the change table of the last revision that carried one (the kept base
    when none was fetched), then the monthly member lists after it."""
    revs = sorted((k, str(v)) for k, v in (cache.get('rev') or {}).items())
    snaps = dict(cache.get('snaps') or {})
    try:
        base = json.loads(BASE.read_text(encoding='utf-8'))
        snaps['base'] = {'members': base['members'], 'changes': [tuple(c) for c in base['changes']]}
        revs = sorted(revs + [(base['as_of'], 'base')])
    except (OSError, ValueError, KeyError):
        pass
    ticker_name = ticker_name or {}
    with_changes = [(k, r) for k, r in revs if r in snaps and snaps[r].get('changes')]
    tick_of = {}                                           # Wikipedia symbol → today's ticker, through the CIK where known
    for _, r in revs:
        for s, cik in (snaps.get(r) or {}).get('members', []):
            if cik and cik in cik_ticker:
                tick_of.setdefault(s, cik_ticker[cik])
    for m in cache.get('sp500_now') or []:
        if m.get('cik') and m['cik'] in cik_ticker:
            tick_of[m['symbol']] = cik_ticker[m['cik']]
    T = lambda s: tick_of.get(s, s)
    iv = {}
    if with_changes:
        k0, r0 = with_changes[-1]
        members = {T(s) for s, _ in snaps[r0]['members']}
        end = {t: None for t in members}                   # open at the revision (the snapshots below may close them)
        for d, add, an, rem, rn in sorted(snaps[r0]['changes'], reverse=True):
            a, b = T(add) if add else None, T(rem) if rem else None
            if a and a in ticker_name and not same_company(an, ticker_name[a]):
                a = None                                   # the ticker belonged to another company then
            if b and b in ticker_name and not same_company(rn, ticker_name[b]):
                b = None
            if a and a in members:
                iv.setdefault(a, []).append([d, end.pop(a, None)])
                members.discard(a)
            if b:
                members.add(b)
                end[b] = d
        for t in members:                                  # members since before the table begins
            iv.setdefault(t, []).append([None, end.get(t)])
        start_k = k0
    else:
        start_k = None
    # the monthly lists after the change table: joins and departures dated to the month they show
    seq = [(k, {T(s) for s, _ in snaps[r]['members']}) for k, r in revs if r in snaps and snaps[r].get('members') and (start_k is None or k >= start_k)]
    for (k1, a), (k2, b) in zip(seq, seq[1:]):
        for t in b - a:
            iv.setdefault(t, []).append([k2, None])
        for t in a - b:
            open_ = [x for x in iv.get(t, []) if x[1] is None]
            if open_:
                open_[-1][1] = k2
            else:
                iv.setdefault(t, []).append([None, k2])
    added = {T(m['symbol']): m.get('added') for m in cache.get('sp500_now') or []}
    for t, lst in iv.items():                              # the member list's own “date added” for a start the table lacks
        for x in lst:
            if x[0] is None and x[1] is None and added.get(t):
                x[0] = added[t]
        lst.sort(key=lambda x: x[0] or '0000')
    return iv


def dow_history(cache, name_ticker):
    """{ticker: [[from, to or None], …]} from the Dow's compositions, matched by normalised name."""
    comps = cache.get('dow') or []
    iv = {}
    for i, (d, names) in enumerate(comps):
        nxt = comps[i + 1][0] if i + 1 < len(comps) else None
        for n in names:
            t = name_ticker.get(norm_name(n))
            if not t:
                continue
            lst = iv.setdefault(t, [])
            if lst and lst[-1][1] == d:                     # still a member: extend
                lst[-1][1] = nxt
            elif not lst or lst[-1][1] is not None:
                lst.append([d, nxt])
    return iv


def build(root, by, pub, site_companies=None, today=None, fetch=True):
    """by: {ticker: [[etf, weight, value], …]} (etf.build's holdings by company); site_companies: [{ticker, cik, name}]."""
    today = today or dt.date.today()
    root, pub = Path(root), Path(pub)
    cache = collect(root, today) if fetch else (json.loads((root / 'cache' / 'members' / 'wiki.json').read_text(encoding='utf-8'))
                                               if (root / 'cache' / 'members' / 'wiki.json').exists() else {})
    held = {}
    for t, lst in (by or {}).items():
        for e, w, _ in lst:
            if w and w > 0:
                held.setdefault(e, set()).add(t)
    now, src = {}, {}
    for key, name, etfs, min_n in INDEXES:
        for e in etfs:
            if len(held.get(e, ())) >= min_n:
                now[key], src[key] = held[e], e
                break
    if 'sp500' not in now and cache.get('sp500_now'):
        now['sp500'], src['sp500'] = {m['symbol'] for m in cache['sp500_now']}, 'Wikipedia'
    # names and CIKs: the site's companies where given, and Wikipedia's S&P 500 list (every Dow company is in it)
    cos = list(site_companies or []) + [{'ticker': m['symbol'], 'cik': m.get('cik'), 'name': m.get('name')} for m in cache.get('sp500_now') or []]
    cik_ticker = {str(c.get('cik')).lstrip('0'): sym(c.get('ticker')) for c in cos if c.get('cik') and c.get('ticker')}
    name_ticker = {}
    for c in cos:
        n = norm_name(c.get('name'))
        if n and c.get('ticker'):
            name_ticker.setdefault(n, sym(c['ticker']))
    ticker_name = {}
    for c in cos:
        if c.get('ticker') and c.get('name'):
            ticker_name.setdefault(sym(c['ticker']), c['name'])
    hist = {'sp500': sp500_history(cache, cik_ticker, ticker_name), 'dji': dow_history(cache, name_ticker)}
    # this module's own record: when each ticker was first and last seen in each index's tracker
    spath = root / 'cache' / 'members' / 'seen.json'
    try:
        seen = json.loads(spath.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        seen = {}
    day = today.isoformat()
    for key, members in now.items():
        s = seen.setdefault(key, {})
        for t in members:
            s.setdefault(t, [day, day])[1] = day
    spath.parent.mkdir(parents=True, exist_ok=True)
    spath.write_text(json.dumps(seen, separators=(',', ':')), encoding='utf-8')
    added = {sym(m['symbol']): m.get('added') for m in cache.get('sp500_now') or []}
    # the S&P 500 today closes the history: a member then and not now left after the last list on hand (dated to the
    # month it disappears when the monthly lists could be read, else “after <date>”); a member now has an open period
    approx = {}
    sp_now = now.get('sp500') or set()
    last_list = max([k for k, r in (cache.get('rev') or {}).items() if str(r) in (cache.get('snaps') or {})] + [json.loads(BASE.read_text(encoding='utf-8')).get('as_of', '') if BASE.exists() else ''])
    if sp_now:
        for t, lst in hist['sp500'].items():
            if t not in sp_now:
                for x in lst:
                    if x[1] is None:
                        x[1] = last_list or day
                        approx[t] = last_list
        for t in sp_now:
            lst = hist['sp500'].setdefault(t, [])
            if not any(x[1] is None for x in lst):
                lst.append([added.get(t), None])
    rows = {}
    for key, members in now.items():
        for t in members:
            rows.setdefault(t, {'now': [], 'was': {}})['now'].append(key)
    for key, iv in hist.items():
        for t, lst in iv.items():
            if t in cik_ticker.values() or t in rows:
                r = rows.setdefault(t, {'now': [], 'was': {}})
                r['was'][key] = lst
    for key, s in seen.items():                            # gone from a tracker for more than ten days: a former member
        if key in hist:
            continue
        for t, (a, b) in s.items():
            if b < (today - dt.timedelta(days=10)).isoformat():
                rows.setdefault(t, {'now': [], 'was': {}})['was'][key] = [[a, b]]
    for t, r in rows.items():
        if 'sp500' in r['now'] and added.get(t):
            r['since'] = {'sp500': added[t]}
        if t in approx and 'sp500' in r.get('was', {}):
            r['left_after'] = {'sp500': approx[t]}
        if not r['was']:
            del r['was']
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'indexes': {k: {'name': n, 'source': src.get(k), 'n': len(now.get(k, ()))} for k, n, _, _ in INDEXES},
           'history': {'sp500': 'Wikipedia: the dated change table and the member list month by month since 2024',
                       'dji': 'Wikipedia: the historical components, one table per change', 'others': 'from ' + min((v[0] for s in seen.values() for v in s.values()), default=day)},
           'rows': rows,
           'note': ("Now: the full holdings of the ETFs that track each index. Before: Wikipedia's S&P 500 change table and member lists, "
                    "and the Dow's historical components; the other indices from this page's first build on. Tickers of the past are mapped "
                    "to today's through the CIK where Wikipedia gives one.")}
    pub.mkdir(parents=True, exist_ok=True)
    (pub / 'members.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return {k: v['n'] for k, v in doc['indexes'].items()} | {'rows': len(rows), 'sp500_hist': len(hist['sp500']), 'dji_hist': len(hist['dji'])}
