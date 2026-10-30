"""Shares outstanding before XBRL: the count on the cover page of each 10-K (and 10-Q) filed from 1993 until the
company's first XBRL filing, read from EDGAR's text and HTML, so the market value history (rank_panel.py: the
video studio's leaderboards, the value strategies) reaches back to the 1990s instead of starting in 2009–2011.

  where      every 10-K, 10-K405, 10-KSB, 10-KT (pass 1) and 10-Q, 10-QSB (pass 2) on the company's EDGAR filing list
             (data.sec.gov/submissions) dated 1993 to the first XBRL filing; the first 160 KB of the main document (the
             full .txt submission before 2001), never the exhibits
  reading    the cover page (up to PART I): "Indicate the number of shares outstanding of each of the issuer's classes
             of common stock, as of the latest practicable date" and its answer, in whatever form it was written —
             "122,691,266 shares of Common Stock Issued and Outstanding as of August 4, 1995", "As of March 1, 2004,
             there were 1,234,567 shares of the registrant's common stock outstanding", a table of classes (summed),
             "123.4 million shares". Dollar amounts (the market value held by non-affiliates), authorized shares and
             par values are not counts. The date beside the count is its date (else the filing date)
  checked    a count is dropped when it is off by more than 4 times from both of its neighbours that agree with each
             other (a misread, not a change in shares); rank_panel puts every count on today's split basis
Kept on the branch rotation-history as cache/cover/<CIK>.json: [[date, shares, form, accession], …]; state.json's
"cover" entry records each company's progress. A company is done once both passes are read.

  python app/cover_shares.py collect --root hist --site-index site/index.json --minutes 38
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import re
import time
import urllib.request
from pathlib import Path

UA_DEFAULT = 'Filing Flows research filingflows@gmail.com'
SINCE = '1993-01-01'
UNTIL = '2011-12-31'                             # never after the company's first XBRL filing either
PASSES = [('annual', ('10-K', '10-K405', '10-KSB', '10-KT', '10-K40', '10-KSB40')), ('quarterly', ('10-Q', '10-QSB', '10-QT'))]
READ_BYTES = 160_000
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
                                           'october', 'november', 'december'])}
MON3 = {k[:3]: v for k, v in MONTHS.items()}
NUM = r'(\d{1,3}(?:[,.]\d{3})+|\d{5,}|\d+(?:\.\d+)?(?=\s*(?:million|billion)\b))'


def http_get(url, ua, limit=None, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(limit) if limit else r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    raise OSError(f'could not read {url}')


def text_of(raw):
    """Readable text from an HTML or SGML filing (tags out, entities decoded, whitespace collapsed)."""
    s = raw.decode('latin-1', errors='replace') if isinstance(raw, bytes) else raw
    s = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|td|th|li)>', ' \n ', s)
    s = re.sub(r'<[^>]{0,2000}>', ' ', s)
    s = html.unescape(s).replace('\xa0', ' ')
    s = re.sub(r'[ \t\r\f\v]+', ' ', s)
    s = re.sub(r'\n\s*', '\n', s)
    return s


def cover_of(text):
    """The cover page: from the start to the first PART I heading that follows the cover's questions (or 40,000 chars)."""
    t = text[:60000]
    start = 0
    m = re.search(r'(?i)(indicate (the )?number of shares outstanding|latest practicable date|shares outstanding of each|'
                  r'number of shares of [^.]{0,80}outstanding|shares of [^.]{0,60}outstanding (as of|at|on) )', t)
    anchor = m.start() if m else 0
    end = None
    for p in re.finditer(r'(?i)\bPART\s+I\b(?!I)', t):
        if p.start() > (anchor if anchor else 800):
            end = p.start()
            break
    return t[start:end or 40000], anchor


DATE_RX = re.compile(r'(?i)\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2}),?\s*(\d{4})\b'
                     r'|\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b')


def _date(m):
    try:
        if m.group(1):
            mon = MONTHS.get(m.group(1).lower()) or MON3.get(m.group(1).lower()[:3])
            return dt.date(int(m.group(3)), mon, int(m.group(2)))
        y = int(m.group(6))
        y = y + (1900 if y >= 50 else 2000) if y < 100 else y
        return dt.date(y, int(m.group(4)), int(m.group(5)))
    except (ValueError, TypeError):
        return None


def _num(s):
    s = s.replace(',', '').replace('.', '') if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', s) else s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


BAD_BEFORE = re.compile(r'(?i)(\$\s*$|\$\s*\(?$|aggregate market value[^.]{0,200}$|authori[sz]ed[^.]{0,80}$|excludes? (approximately )?$|'
                        r'non-?affiliates[^.]{0,60}$|\bno\.?\s*$|file number[^.]{0,20}$|zip[^.]{0,20}$|telephone[^.]{0,30}$|'
                        r'irs employer[^.]{0,60}$|commission file[^.]{0,30}$)')
BAD_AFTER = re.compile(r'(?i)^\s*(%|percent|per share|\)?\s*\(?(area|zip)|authori[sz]ed|of the (aggregate|voting)|shares (were |are )?(held|owned|beneficially) by)')


def parse_cover(raw, filed=None):
    """→ (date, shares, how) or None: the count of common shares outstanding on the cover page."""
    text = text_of(raw)
    cover, anchor = cover_of(text)
    low = cover.lower()
    cands = []
    for m in re.finditer(NUM + r'(\s*(million|billion))?', cover):
        v = _num(m.group(1))
        if v is None:
            continue
        if m.group(3):
            v *= 1e6 if m.group(3).lower() == 'million' else 1e9
        if v < 10_000 or v > 5e11:
            continue
        before, after = cover[max(0, m.start() - 160):m.start()], cover[m.end():m.end() + 60]
        if BAD_BEFORE.search(before) or BAD_AFTER.search(after):
            continue
        if re.search(r'\d{4}$', m.group(1)) and 1900 <= v <= 2100:
            continue                                                  # a year
        win = low[max(0, m.start() - 250):m.end() + 250]
        if 'outstanding' not in win:
            continue
        if not re.search(r'(?i)\b(shares?|common|stock|class|units?)\b', cover[max(0, m.start() - 250):m.end() + 120]):
            continue
        dist = min(abs(o.start() - (m.start() - max(0, m.start() - 250))) for o in re.finditer('outstanding', win))
        after_q = m.start() >= anchor - 200 if anchor else True       # the answer can open the sentence the anchor is in
        cl = list(re.finditer(r'(?i)\b(?:class|series)\s+([a-c])\b', cover[max(0, m.start() - 160):m.start()])) or \
            list(re.finditer(r'(?i)\b(?:class|series)\s+([a-c])\b', cover[m.end():m.end() + 60]))[:1]
        cands.append({'v': v, 'pos': m.start(), 'dist': dist, 'after_q': after_q, 'cls': cl[-1].group(1).upper() if cl else None})
    if not cands:
        return None
    pool = [c for c in cands if c['after_q']] or cands
    pool.sort(key=lambda c: c['pos'])
    first = pool[0]
    # several classes, each with its count (within 600 characters of the first): their sum is the common stock
    classes = {}
    for c in pool:
        if c['pos'] - first['pos'] > 600:
            break
        if c['cls'] and c['cls'] not in classes:
            classes[c['cls']] = c['v']
    if len(classes) >= 2:
        v, how = sum(classes.values()), 'classes ' + '+'.join(sorted(classes))
    else:
        v, how = first['v'], 'cover'
    # the date written beside the count (after "as of" / "at" / "on"), else the filing date
    seg = cover[max(0, first['pos'] - 260):first['pos'] + 260]
    dates = [(abs((d_.start() + max(0, first['pos'] - 260)) - first['pos']), _date(d_)) for d_ in DATE_RX.finditer(seg)]
    dates = [x for x in dates if x[1] and 1990 <= x[1].year <= 2013]
    if filed:
        f = dt.date.fromisoformat(filed)
        dates = [x for x in dates if dt.timedelta(days=-400) <= f - x[1] <= dt.timedelta(days=200)]
    d = min(dates)[1] if dates else (dt.date.fromisoformat(filed) if filed else None)
    return (d.isoformat() if d else None, v, how)


# ------------------------------------------------------------------ EDGAR filing lists
def filings(cik, ua, sleep=0.12):
    """Every 10-K / 10-Q type filing of a company, oldest first: [{form, date, acc, doc, xbrl}]."""
    base = 'https://data.sec.gov/submissions/'
    d = json.loads(http_get(f'{base}CIK{int(cik):010d}.json', ua))
    pages = [d['filings']['recent']]
    for f in d['filings'].get('files') or []:
        time.sleep(sleep)
        pages.append(json.loads(http_get(base + f['name'], ua)))
    out = []
    for p in pages:
        n = len(p.get('form') or [])
        for k in range(n):
            out.append({'form': p['form'][k], 'date': p['filingDate'][k], 'acc': p['accessionNumber'][k],
                        'doc': (p.get('primaryDocument') or [''] * n)[k] or '', 'xbrl': bool((p.get('isXBRL') or [0] * n)[k])})
    out.sort(key=lambda r: r['date'])
    return out


def doc_url(cik, f):
    acc = f['acc']
    if f['doc']:
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{f['doc']}"
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}.txt"


def clean(points):
    """Drop a count far (over 4×) from both neighbours that agree with each other (a misread)."""
    pts = sorted(p for p in points if p[0] and p[1])
    keep = []
    for i, p in enumerate(pts):
        if 0 < i < len(pts) - 1:
            a, c = pts[i - 1][1], pts[i + 1][1]
            if 1 / 1.5 < a / c < 1.5 and min(abs(math.log(p[1] / a)), abs(math.log(p[1] / c))) > math.log(4):
                continue
        keep.append(p)
    return keep


def read_company(cik, ua, forms, sleep=0.12, deadline=None, have=()):
    """The cover counts of one company's filings of the given forms before its first XBRL filing. → (points, done)."""
    fl = filings(cik, ua, sleep)
    first_x = next((f['date'] for f in fl if f['xbrl'] and f['date'] >= '2009-06-01'), None)   # the voluntary XBRL of 2005–08 aside
    until = min(UNTIL, first_x) if first_x else UNTIL
    want = [f for f in fl if f['form'].replace('/A', '') in forms and not f['form'].endswith('/A') and SINCE <= f['date'] < until and f['acc'] not in have]
    pts = []
    for f in want:
        if deadline and time.time() > deadline:
            return pts, False
        time.sleep(sleep)
        try:
            raw = http_get(doc_url(cik, f), ua, READ_BYTES)
        except Exception:                                      # older filings: the document only inside the full .txt
            try:
                time.sleep(sleep)
                raw = http_get(doc_url(cik, {**f, 'doc': ''}), ua, READ_BYTES)
            except Exception:
                continue
        r = parse_cover(raw, f['date'])
        if r and r[0]:
            pts.append([r[0], r[1], f['form'], f['acc']])
    return pts, True


def collect(root, site_index, ua, minutes=38.0, limit=None, tickers=None):
    root = Path(root)
    t0 = time.time()
    deadline = t0 + minutes * 60
    folder = root / 'cache' / 'cover'
    folder.mkdir(parents=True, exist_ok=True)
    st_p = root / 'cover-state.json'
    state = json.loads(st_p.read_text()) if st_p.exists() else {}
    cos = [c for c in json.loads(Path(site_index).read_text()).get('companies') or [] if c.get('cik') and c.get('ticker')]
    cos.sort(key=lambda c: -(c.get('revenue') or 0))
    if tickers:
        want = [t.strip().upper() for t in tickers.split(',') if t.strip()]
        cos = [c for c in cos if c['ticker'].upper() in want] + [c for c in cos if c['ticker'].upper() not in want]
    done = n_pts = errs = 0
    for pname, forms in PASSES:
        for c in cos:
            if time.time() > deadline or (limit and done >= limit):
                break
            cik = str(int(c['cik']))
            s = state.setdefault(cik, {})
            if s.get(pname) or (s.get('retry_after') and s['retry_after'] > dt.datetime.now(dt.timezone.utc).isoformat()):
                continue
            p = folder / f'{cik}.json'
            old = json.loads(p.read_text()) if p.exists() else []
            try:
                pts, complete = read_company(cik, ua, forms, deadline=deadline, have={x[3] for x in old})
            except Exception as exc:
                errs += 1
                s.update(error=f'{type(exc).__name__}: {str(exc)[:120]}', retry_after=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(timespec='seconds'))
                continue
            allp = sorted({x[3]: x for x in old + pts}.values())
            p.write_text(json.dumps(clean(allp), separators=(',', ':')))
            n_pts += len(pts)
            if complete:
                s[pname] = dt.date.today().isoformat()
                s['n'] = len(allp)
                s.pop('error', None)
                done += 1
                print(f"{c['ticker']} ({pname}): {len(pts)} counts", flush=True)
                if done % 20 == 0:                              # a run stopped from outside keeps its progress
                    st_p.write_text(json.dumps(state, separators=(',', ':')))
        st_p.write_text(json.dumps(state, separators=(',', ':')))
    left = {pn: sum(1 for c in cos if not state.get(str(int(c['cik'])), {}).get(pn)) for pn, _ in PASSES}
    st_p.write_text(json.dumps(state, separators=(',', ':')))
    return {'companies_done': done, 'counts': n_pts, 'errors': errs, 'left': left, 'minutes': round((time.time() - t0) / 60, 1)}


def points(root, cik):
    """[(date, shares)] read so far for one company (rank_panel's cover counts before XBRL)."""
    p = Path(root) / 'cache' / 'cover' / f'{int(cik)}.json'
    try:
        return [(d, v) for d, v, *_ in json.loads(p.read_text())]
    except (OSError, ValueError):
        return []


def main():
    ap = argparse.ArgumentParser(description='Cover-page share counts before XBRL (app/cover_shares.py)')
    sub = ap.add_subparsers(dest='cmd')
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--site-index', required=True)
    c.add_argument('--minutes', type=float, default=38)
    c.add_argument('--limit', type=int, default=None)
    c.add_argument('--tickers', default='')
    o = sub.add_parser('one')
    o.add_argument('--cik', required=True)
    o.add_argument('--forms', default='annual')
    a = ap.parse_args()
    ua = os.environ.get('SEC_USER_AGENT') or UA_DEFAULT
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, ua, a.minutes, a.limit, a.tickers)))
    elif a.cmd == 'one':
        forms = dict(PASSES)[a.forms]
        pts, _ = read_company(a.cik, ua, forms)
        for p in pts:
            print(p)


if __name__ == '__main__':
    main()
