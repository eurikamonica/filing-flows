"""US Senate periodic transaction reports (4.6), from the Senate's electronic financial disclosure site (eFD).

Senators (and candidates, and senior staff) report each transaction in stocks, bonds and other securities over $1,000 within
45 days, on a periodic transaction report (PTR). Most PTRs are filed electronically and published as an HTML table:
date, owner (self, spouse, joint, child), ticker, asset, type, amount range. Paper PTRs are scanned images and are only
listed (with their link), never read.

eFD asks every visitor to accept its terms of use (the prohibition on commercial use of the data): each run opens a session
(home page → the agreement form, with Django's CSRF token), then searches PTRs (report type 11) — the last weeks every
`min_interval_minutes`, plus one older month per run back to `since` — and reads up to `batch` queued reports.

Cache:   cache/senate/reports.json (every PTR found: who, filed, link, status) and cache/senate/trades.json.gz
Used by: market.py (officials-trades.json, jurisdiction "US Senate"), so Senate trades sit with the House's in the hub's
         Officials' trades (✦ X per row), the company pages and the X posts.
"""
import datetime as dt
import gzip
import html
import json
import re
from pathlib import Path
from urllib.parse import urlencode

from core import now, read_json, write_json

BASE = 'https://efdsearch.senate.gov'
HOME = BASE + '/search/home/'
SEARCH = BASE + '/search/'
DATA = BASE + '/search/report/data/'
OWNERS = {'self': 'Self', 'spouse': 'SP', 'joint': 'JT', 'child': 'DC', 'dependent child': 'DC'}
TYPES = {'purchase': 'purchase', 'sale (full)': 'sale', 'sale': 'sale', 'sale (partial)': 'partial sale', 'exchange': 'exchange'}
ASSETS = {'stock': 'ST', 'stock option': 'OP', 'corporate bond': 'CS', 'municipal security': 'GS', 'government security': 'GS',
          'mutual fund': 'MF', 'exchange traded fund': 'EF', 'non-public stock': 'PS', 'other securities': 'OT', 'cryptocurrency': 'CT',
          'commodities/futures': 'FU'}


def _text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _mdy(s):
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', s or '')
    try:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat() if m else ''
    except ValueError:
        return ''


def amount(s):
    """'$1,001 - $15,000' → (1001, 15000); 'Over $50,000,000' → (50000001, None), the open top range stored as its first
    dollar, as the House reader stores it; anything else → (None, None)."""
    nums = [int(x.replace(',', '')) for x in re.findall(r'\$\s*([\d,]+)', s or '')]
    if re.search(r'(?i)\bover\b', s or '') and nums:
        return nums[0] + 1, None
    if len(nums) >= 2:
        return nums[0], nums[1]
    return (nums[0], nums[0]) if nums else (None, None)


# ------------------------------------------------------------------ eFD session
def csrf_cookie(client):
    return next((c.value for c in client.jar if c.name == 'csrftoken'), '')


def open_session(client):
    """Accept eFD's terms of use for this session (the site requires it before any search or report)."""
    page = client.get(HOME).decode('utf-8', 'replace')
    tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
    if not tok:
        if 'search/report/data' in page or 'Search Reports' in page:
            return True                                   # already accepted in this session
        raise RuntimeError('eFD home page without the agreement form')
    client.request(HOME, data=urlencode({'prohibition_agreement': '1', 'csrfmiddlewaretoken': tok.group(1)}).encode(),
                   headers={'Referer': HOME, 'Content-Type': 'application/x-www-form-urlencoded'})
    return True


def search(client, start_date, end_date='', start=0, length=100):
    """One page of PTR search results → (rows, total). Dates are MM/DD/YYYY."""
    csrf = csrf_cookie(client)
    form = {'start': str(start), 'length': str(length), 'report_types': '[11]', 'filer_types': '[]',
            'submitted_start_date': f'{start_date} 00:00:00', 'submitted_end_date': f'{end_date} 23:59:59' if end_date else '',
            'candidate_state': '', 'senator_state': '', 'office_id': '', 'first_name': '', 'last_name': '', 'csrfmiddlewaretoken': csrf}
    body = client.request(DATA, data=urlencode(form).encode(), headers={
        'Referer': SEARCH, 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json, text/javascript, */*',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})[0]
    d = json.loads(body)
    return d.get('data') or [], int(d.get('recordsFiltered') or d.get('recordsTotal') or 0)


def report_of(row):
    """A search result row → the report: id, person, office, filed date, link, electronic or paper."""
    first, last, label, link, filed = (list(row) + [''] * 5)[:5]
    m = re.search(r'href="(/search/view/(ptr|paper)/([0-9a-f-]+)/?)"', link or '')
    if not m:
        return None
    last = re.sub(r',\s*', ' ', last or '')
    person = re.sub(r'\s+', ' ', f'{first} {last}').strip()
    office = re.search(r'\(([^)]+)\)\s*$', label or '')
    return {'report_id': 'senate-' + m.group(3), 'person': person, 'office': office.group(1) if office else 'Senate',
            'filed_date': _mdy(filed) or _mdy(_text(link)), 'source_url': BASE + m.group(1), 'format': 'electronic' if m.group(2) == 'ptr' else 'paper',
            'title': _text(link)}


def parse_ptr(page, rep):
    """The transactions table of one electronic PTR → trade rows in the officials-trades shape."""
    out = []
    body = re.search(r'<tbody>(.*?)</tbody>', page, re.S)
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body.group(1) if body else '', re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 8:
            continue
        num, day, owner, tick, asset, kind, typ, amt = tds[:8]
        comment = _text(tds[8]) if len(tds) > 8 else ''
        name = _text(re.split(r'<div', asset, maxsplit=1)[0])
        detail = _text(''.join(re.findall(r'<div[^>]*>(.*?)</div>', asset, re.S)))
        t = _text(tick)
        lo, hi = amount(_text(amt))
        kind_t = _text(kind)
        out.append({'ticker': '' if t in ('--', '') else t.upper(), 'asset_type': ASSETS.get(kind_t.lower(), ''), 'asset_kind': kind_t,
                    'type': TYPES.get(_text(typ).lower(), _text(typ).lower() or 'other'), 'date': _mdy(_text(day)), 'notified': '',
                    'owner': OWNERS.get(_text(owner).lower(), _text(owner) or 'Self'),
                    'asset_raw': (name + (f' ({detail})' if detail else ''))[:200], 'amount_min': lo, 'amount_max': hi,
                    'person': rep['person'], 'jurisdiction': 'US Senate', 'report_id': rep['report_id'], 'filed_date': rep['filed_date'],
                    'source_url': rep['source_url'], 'read': 'electronic', 'row': _text(num),
                    **({'comment': comment[:160]} if comment and comment != '--' else {})})
    return out


# ------------------------------------------------------------------ collect
def collect(client, root, cfg=None, today=None):
    cfg = cfg or {}
    today = today or dt.date.today()
    cdir = Path(root) / 'cache' / 'senate'
    cdir.mkdir(parents=True, exist_ok=True)
    reports = {r['report_id']: r for r in read_json(cdir / 'reports.json', [])}
    store = cdir / 'trades.json.gz'
    trades = json.load(gzip.open(store, 'rt', encoding='utf-8')) if store.exists() else []
    state = read_json(cdir / 'state.json', {})
    since = cfg.get('since', '2024-01-01')
    due = (state.get('searched_at') or '') < (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=int(cfg.get('min_interval_minutes', 90)))).isoformat()
    cursor = state.get('cursor') or (today - dt.timedelta(days=int(cfg.get('recent_days', 60)))).isoformat()
    backfill = cursor > since
    waiting = [r for r in reports.values() if r['format'] == 'electronic' and r.get('status') not in ('read', 'empty') and (r.get('fails') or 0) < 4]
    if not due and not waiting and not backfill:
        return {'status': 'ok', 'skipped': 'searched recently', 'reports': len(reports), 'trades': len(trades), 'updated_at': now()}
    errors, found = [], 0
    open_session(client)

    def scan(start, end=''):
        nonlocal found
        fmt = lambda d: dt.date.fromisoformat(d).strftime('%m/%d/%Y')
        off = 0
        for _ in range(int(cfg.get('max_pages', 6))):
            rows, total = search(client, fmt(start), fmt(end) if end else '', off, 100)
            for row in rows:
                r = report_of(row)
                if r and r['report_id'] not in reports:
                    reports[r['report_id']] = {**r, 'status': 'listed' if r['format'] == 'paper' else 'waiting', 'found_at': now()}
                    found += 1
            off += len(rows)
            if not rows or off >= total:
                break

    try:
        if due:
            scan((today - dt.timedelta(days=int(cfg.get('recent_days', 60)))).isoformat())
            state['searched_at'] = now()
        if backfill:                                  # one older month per run, back to `since`
            end = dt.date.fromisoformat(cursor) - dt.timedelta(days=1)
            start = max(dt.date.fromisoformat(since), end - dt.timedelta(days=31))
            scan(start.isoformat(), end.isoformat())
            state['cursor'] = start.isoformat()
    except Exception as exc:
        errors.append(f'search: {str(exc)[:200]}')
        print(f'Senate eFD search: {exc}', flush=True)
    queue = sorted((r for r in reports.values() if r['format'] == 'electronic' and r.get('status') not in ('read', 'empty') and (r.get('fails') or 0) < 4),
                   key=lambda r: r.get('filed_date') or '', reverse=True)
    read = 0
    by_report = {}
    for t in trades:
        by_report.setdefault(t['report_id'], []).append(t)
    for r in queue[:int(cfg.get('batch', 40))]:
        try:
            page = client.get(r['source_url'], headers={'Referer': SEARCH}).decode('utf-8', 'replace')
            if 'prohibition_agreement' in page:          # the session lapsed: accept again, retry once
                open_session(client)
                page = client.get(r['source_url'], headers={'Referer': SEARCH}).decode('utf-8', 'replace')
            rows = parse_ptr(page, r)
            by_report[r['report_id']] = rows
            r.update({'status': 'read' if rows else 'empty', 'trades': len(rows), 'read_at': now()})
            read += 1
        except Exception as exc:
            r['fails'] = (r.get('fails') or 0) + 1
            r['status'] = 'error'
            errors.append(f"{r['report_id']}: {str(exc)[:120]}")
            if len(errors) > 8:
                break
    trades = sorted((t for ts in by_report.values() for t in ts), key=lambda t: (t.get('date') or '', t['report_id']), reverse=True)
    with gzip.open(store.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
        json.dump(trades, f, separators=(',', ':'))
    store.with_suffix('.tmp').replace(store)
    write_json(cdir / 'reports.json', sorted(reports.values(), key=lambda r: (r.get('filed_date') or '', r['report_id']), reverse=True))
    state['updated_at'] = now()
    write_json(cdir / 'state.json', state)
    left = sum(1 for r in reports.values() if r['format'] == 'electronic' and r.get('status') not in ('read', 'empty'))
    return {'status': 'ok' if not errors else 'partial', 'found': found, 'read': read, 'waiting': left, 'reports': len(reports),
            'paper': sum(r['format'] == 'paper' for r in reports.values()), 'trades': len(trades), 'cursor': state.get('cursor'),
            'errors': errors[:5], 'updated_at': now()}


def load(root):
    cdir = Path(root) / 'cache' / 'senate'
    store = cdir / 'trades.json.gz'
    trades = json.load(gzip.open(store, 'rt', encoding='utf-8')) if store.exists() else []
    return trades, read_json(cdir / 'reports.json', [])
