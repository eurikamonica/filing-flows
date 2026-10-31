"""Employees (Disclosures → Workforce, and the "Workforce" view of each company page): how many people each company
employs, read from its own 10-K, and what that says — revenue and profit per employee against its industry, and hiring
or layoffs year on year.

  collect  For the site's companies, largest first: the SEC's list of each company's filings (data.sec.gov/submissions),
           then the main document of each of its last five 10-Ks (once each; the number found is cached by accession).
           The headcount is read from the text ("As of December 31, 2025, we had approximately 1,556,000 employees"):
           the human-capital paragraphs first, the whole document after; the sentence is kept as the evidence.
  build    public/: index.json (one row per company), c/<cik>.json (the years, the sentences, the peers), status.json.
           Revenue and net income are the hub's annual XBRL frames (app/frames.py), matched to each fiscal year end.

Median employee pay: the pay-ratio disclosure every US proxy statement (DEF 14A) carries since 2018 (Regulation S-K
Item 402(u)): "the annual total compensation of our median employee was $58,226" and the CEO's pay as a multiple of it.
The latest proxy of each company is read once (cache/pay.json, by accession). The median is of all employees worldwide
(the company may leave out up to 5% abroad), counting salary, bonus, overtime and benefits as the company measures them.

A headcount is what the company says at one date (usually its fiscal year end); some count full-time employees only,
some include contractors or part-time staff, and the wording is kept so a reader can tell. Not investment advice.

    python disclosures/app/employees.py collect --root emp --universe site/index.json --minutes 25
    python disclosures/app/employees.py build --root emp --universe site/index.json --frames-root disclosures/docs/data
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402

SUBS = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
DOC = 'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}'
YEARS = 5
INTERVAL = 0.12                                   # the SEC allows ten requests a second
MAX_DOC = 40 * 1024 * 1024

# ---------------------------------------------------------------- reading the number
WORD_NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
ADJ = r'(?:(?:full[- ]time(?:[- ]equivalent)?|full-|part[- ]time|hourly|salaried|total|global|worldwide|permanent|regular|active|at-will|U\.S\.|domestic|non-union|union|direct|seasonal|temporary|dedicated)(?:\s+and\s+|\s*,\s*|\s+)){0,4}'
NOUN = r'(?:employees|team members|associates|colleagues|workers|staff members|full[- ]time equivalents|FTEs|people|persons|individuals|personnel|partners|teammates|crew members)'
PEOPLE = ADJ + NOUN
NUM = r'(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*(?:million|thousand)|\d{1,7})'
QUAL = r'(?:approximately|about|around|roughly|over|more than|nearly|almost|some|a total of|an aggregate of|a workforce of|a global workforce of)?\s*'
PATTERNS = [
    re.compile(r'\b(?:had|employ(?:ed|s)?|employing|have|has|with|of|our|totaled|totalled|consisted of|comprised)\s+' + QUAL + NUM + r'\s+' + PEOPLE, re.I),
    re.compile(r'\b(?:workforce|headcount|employee base|employee population)\s+(?:of|was|totaled|totalled|consisted of|comprised|included)\s+' + QUAL + NUM + r'(?:\s+' + PEOPLE + r')?', re.I),
    re.compile(r'\b' + QUAL + NUM + r'\s+' + PEOPLE + r'\s+(?:worldwide|globally|around the world|in total|across|were employed|are employed)', re.I),
]
# "88,000 (56%) hourly employees and approximately 68,000 (44%) salaried employees": the two added up
SPLIT = re.compile(r'\b' + QUAL + NUM + r'\s*(?:\(\d+%\))?\s+hourly\s+' + NOUN + r'\s+and\s+' + QUAL + NUM + r'\s*(?:\(\d+%\))?\s+salaried\s+' + NOUN, re.I)
DATE = re.compile(r'\b(?:as of|at|on)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})', re.I)
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'])}
BAD_CONTEXT = re.compile(r'%|percent|401\(k\)|of (?:whom|which|these)|collective bargaining', re.I)
LOCAL_AFTER = re.compile(r'^\W{0,3}(?:were\s+|are\s+)?(?:located\s+|based\s+|employed\s+)?(?:in|within)\s+(?:the\s+)?(?:U\.S\.|US\b|United States|North America|our (?:U\.S\.|domestic)|[A-Z][a-z]+ (?:operations|segment))', re.I)


def _num(s):
    s = s.lower().replace(',', '').strip()
    m = re.match(r'([\d.]+)\s*(million|thousand)?', s)
    if not m:
        return None
    v = float(m.group(1))
    v *= 1e6 if m.group(2) == 'million' else 1e3 if m.group(2) == 'thousand' else 1
    return int(round(v))


def plain(doc):
    """The document's text, tags and inline-XBRL markup out, entities decoded, whitespace collapsed."""
    t = doc.decode('utf-8', 'replace') if isinstance(doc, bytes) else doc
    t = re.sub(r'(?is)<(script|style|ix:header)\b.*?</\1>', ' ', t)
    t = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h\d|td)>', '\n', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html.unescape(t).replace('\xa0', ' ')
    return re.sub(r'[ \t\r\f\v]+', ' ', t)


def sentences(text):
    for para in re.split(r'\n\s*\n|\n', text):
        for s in re.split(r'(?<=[.;])\s+(?=[A-Z])', para):
            s = s.strip()
            if 20 <= len(s) <= 900:
                yield s


def headcount(doc):
    """{'count', 'as_of', 'sentence', 'where'} from a 10-K's text, or None. The human-capital section is read first."""
    text = plain(doc)
    low = text.lower()
    spans = []
    for h in ('human capital', 'our employees', 'employees\n', 'employees ', 'workforce'):
        i = low.find(h)
        while i >= 0 and len(spans) < 6:
            spans.append(text[i:i + 6000])
            i = low.find(h, i + 6000)
        if spans:
            break
    for where, body in [('human capital section', '\n'.join(spans)), ('document', text)]:
        best = None
        for s in sentences(body):
            if 'employ' not in s.lower() and not re.search(r'workforce|headcount|team members|associates', s, re.I):
                continue
            for m in SPLIT.finditer(s):
                n = (_num(m.group(1)) or 0) + (_num(m.group(2)) or 0)
                if 5 <= n <= 3_000_000 and (best is None or best[0] < 2.5):
                    d = DATE.search(s)
                    best = (2.5, n, s, d.group(1) if d else None)
            for k, pat in enumerate(PATTERNS):
                for m in pat.finditer(s):
                    n = _num(m.group(1))
                    if n is None or n < 5 or n > 3_000_000 or (1900 <= n <= 2100 and ',' not in m.group(1)):
                        continue
                    pre, post = s[max(0, m.start() - 60):m.start()], s[m.end():m.end() + 60]
                    if BAD_CONTEXT.search(m.group(0)) or re.search(r'%|percent|approximately \d+% of', pre, re.I):
                        continue
                    local = bool(LOCAL_AFTER.search(post)) or bool(re.search(r'\b(?:U\.S\.|domestic)\s+' + NOUN, m.group(0), re.I))
                    score = (2 if re.search(r'full[- ]time|total|worldwide|globally|global workforce|around the world', m.group(0) + post[:20], re.I) else 0) \
                        + (1 if DATE.search(s) else 0) - k * 0.1 - (3 if local else 0)
                    if best is None or score > best[0] or (score == best[0] and n > best[1]):
                        d = DATE.search(s)
                        best = (score, n, s, d.group(1) if d else None)
        if best:
            return {'count': best[1], 'as_of': iso_date(best[3]), 'sentence': best[2][:600], 'where': where}
    return None


def iso_date(s):
    if not s:
        return None
    m = re.match(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', s)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    try:
        return dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------- the median employee's pay (DEF 14A pay ratio)
MONEY = re.compile(r'\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,7}(?:\.\d+)?)')
RATIO = re.compile(r'\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?:\s*(?:to|:|-to-)\s*(?:1|one)\b|\s+times\b)', re.I)
MEDIAN_WHO = re.compile(r'median\s+(?:of\s+the\s+annual\s+total\s+compensation|(?:annual\s+)?total\s+compensation\s+of\s+all|(?:[\w&.\'’-]+\s+){0,3}?(?:employee|associate|team member|colleague|worker))', re.I)
BEFORE = re.compile(r'\$\s?(\d{1,3}(?:,\d{3})+|\d{4,7})(?:\.\d+)?\s+(?:for|to|of)\s+(?:our|the)\s+median\s+(?:[\w&.\'’-]+\s+){0,3}?(?:employee|associate|team member)', re.I)


def median_pay(doc):
    """{'pay', 'ratio', 'sentence'} from a proxy statement's pay-ratio paragraph, or None. The amount is the first dollar
    figure after the words "median employee" (or "median of the annual total compensation"), between $5,000 and $1M; the
    paragraph is found by "pay ratio" or "median employee", the CEO's amount is not taken."""
    text = plain(doc)
    low = text.lower()
    spans, i = [], low.find('pay ratio')
    while i >= 0 and len(spans) < 4:
        spans.append(text[max(0, i - 200):i + 5000])
        i = low.find('pay ratio', i + 5000)
    for where, body in (('pay ratio section', '\n'.join(spans)), ('document', text)):
        best = None
        for s in sentences(body):
            m = MEDIAN_WHO.search(s)
            if not m or not re.search(r'compensation|pay|earn', s, re.I):
                continue
            b = BEFORE.search(s)                                # "$21,005,009 for our CEO and $66,524 for our median employee"
            if b and 5_000 <= float(b.group(1).replace(',', '')) <= 1_000_000:
                r = RATIO.search(s)
                cand = {'pay': round(float(b.group(1).replace(',', ''))), 'ratio': float(r.group(1).replace(',', '')) if r else None, 'sentence': s[:600], 'where': where}
                if best is None or 3 > best[0]:
                    best = (3, cand)
                continue
            after = s[m.end():m.end() + 320]
            for mm in MONEY.finditer(after):
                v = float(mm.group(1).replace(',', ''))
                if 5_000 <= v <= 1_000_000:
                    pre = re.sub(r'(?:other than|excluding|except(?: for)?|not including)\s+(?:our|the)?\s*(?:chief executive officer|ceo)', '',
                                 after[max(0, mm.start() - 80):mm.start()].lower())
                    if re.search(r'chief executive|\bceo\b|our president', pre) and not re.search(r'median', pre):
                        continue
                    if re.search(r'cost of|added|adding|includ(?:ed|ing)|benefits?\s*\(?$|\($', pre[-40:]):
                        continue                                # "added the cost of medical and dental benefits ($16,795)"
                    own = RATIO.search(s)
                    r = own or RATIO.search(body[body.find(s):body.find(s) + 1500] if s in body else '')
                    ratio = float(r.group(1).replace(',', '')) if r else None
                    cand = {'pay': round(v), 'ratio': ratio if ratio and 1 <= ratio <= 50_000 else None, 'sentence': s[:600], 'where': where}
                    score = (2 if 'annual total compensation' in s.lower() else 0) + (1 if own else 0) + (1 if re.search(r'(?:was|of|totaled|were|is)\s*$', pre) else 0)
                    if best is None or score > best[0]:
                        best = (score, cand)
                    break
        if best:
            return best[1]
        flat = re.sub(r'\s+', ' ', body)                         # a sentence broken across lines by the layout
        b = BEFORE.search(flat)
        if b and 5_000 <= float(b.group(1).replace(',', '')) <= 1_000_000:
            r = RATIO.search(flat[b.start():b.start() + 800])
            return {'pay': round(float(b.group(1).replace(',', ''))), 'ratio': float(r.group(1).replace(',', '')) if r else None,
                    'sentence': flat[max(0, b.start() - 200):b.end() + 100], 'where': where}
    return None


def proxies(subs, n=1):
    """The latest proxy statements (DEF 14A): [{'acc', 'doc', 'filed', 'form'}], newest first."""
    r = (subs.get('filings') or {}).get('recent') or {}
    out = []
    for i, form in enumerate(r.get('form') or []):
        if form != 'DEF 14A':
            continue
        doc = (r.get('primaryDocument') or [''])[i] if i < len(r.get('primaryDocument') or []) else ''
        if doc:
            out.append({'acc': r['accessionNumber'][i], 'doc': doc, 'filed': r['filingDate'][i], 'form': form})
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- the SEC
class Sec:
    def __init__(self):
        ua = (os.environ.get('SEC_USER_AGENT') or '').strip()
        if '@' not in ua:
            raise ValueError('Set SEC_USER_AGENT to project name + a contact email')
        self.ua, self.last = ua, 0.0

    def get(self, url):
        for attempt in range(4):
            time.sleep(max(0.0, INTERVAL - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': self.ua, 'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.read(MAX_DOC)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                time.sleep(2 ** (attempt + 1))
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(2 ** attempt)
        raise RuntimeError('SEC request failed: ' + url)


def tenks(subs, years=YEARS):
    """The last `years` annual reports (10-K, 20-F, 40-F and their amendments are skipped) from a submissions document:
    [{'acc', 'doc', 'filed', 'period', 'form'}] newest first."""
    r = (subs.get('filings') or {}).get('recent') or {}
    out = []
    for i, form in enumerate(r.get('form') or []):
        if form not in ('10-K', '20-F', '40-F', '10-KT'):
            continue
        doc = (r.get('primaryDocument') or [''])[i] if i < len(r.get('primaryDocument') or []) else ''
        if not doc:
            continue
        out.append({'acc': r['accessionNumber'][i], 'doc': doc, 'filed': r['filingDate'][i], 'period': (r.get('reportDate') or [''] * (i + 1))[i] or None, 'form': form})
        if len(out) >= years:
            break
    return out


def universe(path):
    d = read_json(path, {}) or {}
    cos = d.get('companies') or []
    return sorted([c for c in cos if c.get('cik')], key=lambda c: -(c.get('revenue') or c.get('market_cap') or 0))


def collect(root, universe_path, minutes=25, years=YEARS, sec=None, refresh_days=14):
    """Fill cache/found.json {cik: {acc: result or None}} — the newest report of every company first, then older ones."""
    root = Path(root)
    t0 = time.monotonic()
    sec = sec or Sec()
    found_p, subs_p, pay_p = root / 'cache' / 'found.json', root / 'cache' / 'subs.json', root / 'cache' / 'pay.json'
    found, subs, pay = read_json(found_p, {}), read_json(subs_p, {}), read_json(pay_p, {})
    cos = universe(universe_path)
    stats = {'docs': 0, 'found': 0, 'subs': 0, 'errors': 0, 'left': 0, 'proxies': 0, 'pay_found': 0}
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=refresh_days)).isoformat()

    def out_of_time():
        return time.monotonic() - t0 > minutes * 60

    # 1) the list of annual reports, refreshed every two weeks (a new 10-K a year per company)
    for c in cos:
        k = str(int(c['cik']))
        if (subs.get(k) or {}).get('at', '') > stale and 'proxies' in (subs.get(k) or {}):
            continue
        if out_of_time():
            stats['left'] += 1
            continue
        try:
            body = sec.get(SUBS.format(cik=int(k)))
            js = json.loads(body) if body else {}
            subs[k] = {'at': now(), 'reports': tenks(js) if body else [], 'proxies': proxies(js) if body else []}
            stats['subs'] += 1
        except Exception as exc:                        # noqa: BLE001
            stats['errors'] += 1
            print(f'employees subs {k}: {str(exc)[:120]}', flush=True)
    # 2) the reports, newest first across companies: everyone's latest, then everyone's previous, …
    for depth in range(years):
        for c in cos:
            k = str(int(c['cik']))
            reps = (subs.get(k) or {}).get('reports') or []
            if depth >= len(reps):
                continue
            rp = reps[depth]
            if rp['acc'] in (found.get(k) or {}):
                continue
            if out_of_time():
                stats['left'] += 1
                continue
            try:
                doc = sec.get(DOC.format(cik=int(k), acc=rp['acc'].replace('-', ''), doc=rp['doc']))
                hc = headcount(doc) if doc else None
                if hc:
                    hc.update({'filed': rp['filed'], 'period': rp['period'], 'form': rp['form'],
                               'url': DOC.format(cik=int(k), acc=rp['acc'].replace('-', ''), doc=rp['doc'])})
                    stats['found'] += 1
                found.setdefault(k, {})[rp['acc']] = hc
                stats['docs'] += 1
            except Exception as exc:                    # noqa: BLE001
                stats['errors'] += 1
                print(f'employees doc {k} {rp["acc"]}: {str(exc)[:120]}', flush=True)
        if stats['docs'] and stats['docs'] % 200 == 0:
            write_json(found_p, found)
        if depth == 0:                                  # 3) after everyone's latest 10-K: everyone's latest proxy (median pay)
            for c in cos:
                k = str(int(c['cik']))
                for rp in (subs.get(k) or {}).get('proxies') or []:
                    if rp['acc'] in (pay.get(k) or {}):
                        continue
                    if out_of_time():
                        stats['left'] += 1
                        continue
                    url = DOC.format(cik=int(k), acc=rp['acc'].replace('-', ''), doc=rp['doc'])
                    try:
                        doc = sec.get(url)
                        mp = median_pay(doc) if doc else None
                        if mp:
                            mp.update({'filed': rp['filed'], 'form': rp['form'], 'url': url})
                            stats['pay_found'] += 1
                        pay.setdefault(k, {})[rp['acc']] = mp
                        stats['proxies'] += 1
                    except Exception as exc:            # noqa: BLE001
                        stats['errors'] += 1
                        print(f'employees proxy {k} {rp["acc"]}: {str(exc)[:120]}', flush=True)
                if stats['proxies'] and stats['proxies'] % 200 == 0:
                    write_json(pay_p, pay)
            write_json(pay_p, pay)
    write_json(found_p, found)
    write_json(subs_p, subs)
    write_json(pay_p, pay)
    stats['seconds'] = round(time.monotonic() - t0)
    return stats


# ---------------------------------------------------------------- the build
def _frames(hub_root):
    import frames as FR
    out = {}
    years = [f'CY{y}' for y in range(2018, dt.date.today().year + 1)]
    for field, concepts in (('rev', FR.REVENUE), ('ni', ['NetIncomeLoss']), ('oi', ['OperatingIncomeLoss'])):
        for concept in concepts:
            for y in years:
                for cik, row in FR.load(hub_root, concept, y).items():
                    if isinstance(row, list) and len(row) == 2 and row[0] is not None:
                        out.setdefault(cik, {}).setdefault(row[1], {}).setdefault(field, row[0])
    return out


def _near(fig, day, days=50):
    """The fiscal-year figures whose end is nearest a date (within `days`)."""
    if not fig or not day:
        return None, None
    d = dt.date.fromisoformat(day)
    best = min(fig, key=lambda e: abs((dt.date.fromisoformat(e) - d).days))
    return (best, fig[best]) if abs((dt.date.fromisoformat(best) - d).days) <= days else (None, None)


def _pct_rank(v, vals):
    vals = sorted(x for x in vals if x is not None)
    if v is None or len(vals) < 5:
        return None
    lo = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    return round((lo + eq / 2) / len(vals), 3)


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def build(root, universe_path, hub_root=None, out=None):
    root = Path(root)
    out = Path(out or root / 'public')
    t0 = time.monotonic()
    found = read_json(root / 'cache' / 'found.json', {})
    paid = {}
    for k, per in (read_json(root / 'cache' / 'pay.json', {}) or {}).items():
        got = [x for x in per.values() if x]
        if got:
            paid[k] = max(got, key=lambda x: x.get('filed') or '')
    cos = {str(int(c['cik'])): c for c in universe(universe_path)}
    fig = _frames(hub_root) if hub_root else {}
    rows, docs = {}, {}
    for k, per in found.items():
        c = cos.get(k)
        if not c:
            continue
        years = {}
        for acc, hc in per.items():
            if not hc:
                continue
            day = hc.get('as_of') or hc.get('period')
            if not day:
                continue
            key = hc.get('period') or day
            if key in years and years[key].get('filed', '') >= hc.get('filed', ''):
                continue
            years[key] = {**hc, 'acc': acc}
        if not years:
            continue
        ys = []
        for key in sorted(years):
            h = years[key]
            e, f = _near(fig.get(k), h.get('period') or h.get('as_of'))
            ys.append({'period': key, 'as_of': h.get('as_of'), 'count': h['count'], 'filed': h.get('filed'), 'url': h.get('url'),
                       'sentence': h.get('sentence'), 'where': h.get('where'), 'fy_end': e,
                       'rev': (f or {}).get('rev'), 'ni': (f or {}).get('ni'), 'oi': (f or {}).get('oi')})
        for i, y in enumerate(ys):
            y['rev_emp'] = y['rev'] / y['count'] if y.get('rev') and y['count'] else None
            y['ni_emp'] = y['ni'] / y['count'] if y.get('ni') is not None and y['count'] else None
            if i:
                p = ys[i - 1]
                gap = (dt.date.fromisoformat(y['period']) - dt.date.fromisoformat(p['period'])).days if y['period'] and p['period'] else None
                if gap and 300 <= gap <= 430 and p['count']:
                    y['change'] = y['count'] / p['count'] - 1
                    y['change_n'] = y['count'] - p['count']
                    if y.get('rev') and p.get('rev'):
                        y['rev_growth'] = y['rev'] / p['rev'] - 1
        last = ys[-1]
        rows[k] = {'cik': int(k), 'ticker': c.get('ticker'), 'name': c.get('name'), 'sector': c.get('sector'), 'sic': c.get('sic'),
                   'employees': last['count'], 'as_of': last.get('as_of') or last['period'], 'change': last.get('change'),
                   'change_n': last.get('change_n'), 'rev_growth': last.get('rev_growth'), 'rev_emp': last.get('rev_emp'),
                   'ni_emp': last.get('ni_emp'), 'years': len(ys)}
        mp = paid.get(k)
        if mp:
            rows[k].update({'median_pay': mp['pay'], 'pay_ratio': mp.get('ratio'), 'pay_filed': mp.get('filed')})
        docs[k] = ys
    # peers: the same 3-digit SIC industry when it has five companies, else the sector
    def ind(r):
        s = str(r.get('sic') or '')
        return s[:3] if len(s) >= 3 else None
    by_ind, by_sec = {}, {}
    for k, r in rows.items():
        if ind(r):
            by_ind.setdefault(ind(r), []).append(k)
        by_sec.setdefault(r.get('sector') or 'other', []).append(k)
    for k, r in rows.items():
        peers = by_ind.get(ind(r)) if ind(r) and len(by_ind.get(ind(r), [])) >= 5 else by_sec.get(r.get('sector') or 'other', [])
        group = f'SIC {ind(r)}' if ind(r) and len(by_ind.get(ind(r), [])) >= 5 else (r.get('sector') or 'other')
        for f in ('rev_emp', 'ni_emp', 'change'):
            r[f + '_pct'] = _pct_rank(r.get(f), [rows[p].get(f) for p in peers])
            r[f + '_med'] = _median([rows[p].get(f) for p in peers])
        r['peer_group'], r['peers'] = group, len(peers)
        r['flag'] = ('layoffs' if (r.get('change') or 0) <= -0.05 else 'hiring' if (r.get('change') or 0) >= 0.1 else None)
        if r['flag'] == 'layoffs' and (r.get('rev_growth') or 0) > 0:
            r['flag'] = 'fewer people, more revenue'
        doc = {'generated_at': now(), 'row': _clean(r), 'years': _clean(docs[k]), 'pay': _clean(paid.get(k)),
               'peers': [[rows[p]['ticker'], rows[p]['name'], rows[p]['employees'], _r(rows[p].get('rev_emp'), 0), _r(rows[p].get('ni_emp'), 0), _r(rows[p].get('change'), 4)]
                         for p in sorted(peers, key=lambda p: -(rows[p].get('rev_emp') or 0))[:40]]}
        (out / 'c').mkdir(parents=True, exist_ok=True)
        write_json(out / 'c' / f'{k}.json', doc)
    fields = ['cik', 'ticker', 'name', 'sector', 'employees', 'as_of', 'change', 'change_n', 'rev_growth', 'rev_emp', 'ni_emp', 'rev_emp_pct',
              'ni_emp_pct', 'rev_emp_med', 'change_pct', 'flag', 'peer_group', 'years', 'median_pay', 'pay_ratio']
    srt = sorted(rows.values(), key=lambda r: -(r['employees'] or 0))
    write_json(out / 'index.json', {'generated_at': now(), 'fields': fields, 'rows': [[_clean(r.get(f)) for f in fields] for r in srt],
                                    'note': ('Headcounts as each company states them in its 10-K (the sentence is kept); revenue and net income '
                                             'from its XBRL facts for the fiscal year nearest the headcount date. Peers: the same 3-digit SIC '
                                             'industry when it has five companies on file, else the sector.')})
    st = {'built_at': now(), 'companies': len(rows), 'with_change': sum(1 for r in rows.values() if r.get('change') is not None),
          'reports_read': sum(len(v) for v in found.values()), 'median_pay': sum(1 for r in rows.values() if r.get('median_pay')), 'headcounts_found': sum(1 for v in found.values() for x in v.values() if x),
          'universe': len(cos), 'seconds': round(time.monotonic() - t0)}
    write_json(out / 'status.json', st)
    return st


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 6)
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--universe', required=True)
    c.add_argument('--minutes', type=float, default=25)
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--universe', required=True)
    b.add_argument('--frames-root', default=None)
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.universe, a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.universe, a.frames_root)), flush=True)


if __name__ == '__main__':
    main()
