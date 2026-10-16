"""Form 4 insider trades (4.4): open-market purchases and sales by officers, directors and 10% owners.

Form 4 is due two business days after the trade, so it is the most current ownership data SEC publishes. Each run reads
EDGAR's "current filings" feed for form 4 (newest first), skips accessions it has already read, downloads up to
`batch` new filings (the full submission .txt, which carries the ownershipDocument XML) and keeps:
  P  open-market or private purchase      S  open-market or private sale
Grants (A), option exercises (M), tax withholding (F), gifts (G) and the like are skipped: they are not decisions to
buy or sell at the market price. Each row carries the 10b5-1 plan flag when the filer ticked it.

Cache:   cache/insiders/trades.json.gz (rolling `keep_days`) and cache/insiders/seen.json (read accessions)
Publish: market/insiders.json — the latest notable trades, a per-ticker 90-day summary with cluster buys, used by the
         Signals tab, the company pages (holders index) and the X posts (pipeline/engage.py kind "insider").
"""
import datetime as dt
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from core import localname, now, parse_xml, read_json, text_of, write_json

FEED = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include'
        '&start={start}&count=100&output=atom')
ROLE_ORDER = ['CEO', 'CFO', 'President', 'COO', 'Chair', 'Officer', 'Director', '10% owner']


def _num(v):
    try:
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def feed_entries(client, pages=4):
    """[(accession, filing folder URL)] from the current-filings feed, newest first, deduplicated."""
    out, seen = [], set()
    for page in range(pages):
        body = client.get(FEED.format(start=page * 100), sec=True)
        root = parse_xml(body)
        n = 0
        for entry in (e for e in root.iter() if localname(e.tag) == 'entry'):
            n += 1
            href = next((l.get('href') for l in entry.iter() if localname(l.tag) == 'link' and l.get('href')), '')
            m = re.search(r'/Archives/edgar/data/(\d+)/(\d{18})/(\d{10}-\d{2}-\d{6})-index\.html?', href)
            if m and m.group(3) not in seen:
                seen.add(m.group(3))
                out.append((m.group(3), f'https://www.sec.gov/Archives/edgar/data/{m.group(1)}/{m.group(2)}/'))
        if n < 100:
            break
    return out


def role_of(rel):
    """'CEO', 'CFO', 'Director', '10% owner' … from the reportingOwnerRelationship block."""
    title = (text_of(rel, 'officerTitle') or '').strip()
    t = title.lower()
    if text_of(rel, 'isOfficer') in ('1', 'true'):
        if re.search(r'chief executive|\bceo\b', t):
            return 'CEO', title
        if re.search(r'chief financial|\bcfo\b', t):
            return 'CFO', title
        if re.search(r'chief operating|\bcoo\b', t):
            return 'COO', title
        if re.search(r'\bpresident\b', t):
            return 'President', title
        if re.search(r'chair', t):
            return 'Chair', title
        return 'Officer', title
    if text_of(rel, 'isDirector') in ('1', 'true'):
        return ('Chair', title) if 'chair' in t else ('Director', title)
    if text_of(rel, 'isTenPercentOwner') in ('1', 'true'):
        return '10% owner', title
    return 'Other', title


def parse_form4(xml_bytes, accession, folder):
    """Rows for the P / S transactions in one ownershipDocument."""
    root = parse_xml(xml_bytes)
    if localname(root.tag) != 'ownershipDocument':
        return []
    issuer = next((e for e in root.iter() if localname(e.tag) == 'issuer'), None)
    owners = [e for e in root.iter() if localname(e.tag) == 'reportingOwner']
    names, roles = [], []
    for o in owners:
        names.append(text_of(o, 'rptOwnerName'))
        rel = next((e for e in o.iter() if localname(e.tag) == 'reportingOwnerRelationship'), None)
        roles.append(role_of(rel) if rel is not None else ('Other', ''))
    best = min(range(len(roles)), key=lambda i: ROLE_ORDER.index(roles[i][0]) if roles[i][0] in ROLE_ORDER else 99) if roles else None
    plan = text_of(root, 'aff10b5One') in ('1', 'true')
    rows = []
    for tx in (e for e in root.iter() if localname(e.tag) == 'nonDerivativeTransaction'):
        code = text_of(tx, 'transactionCode')
        if code not in ('P', 'S'):
            continue
        shares, price = _num(text_of(tx, 'transactionShares')), _num(text_of(tx, 'transactionPricePerShare'))
        if not shares:
            continue
        rows.append({'accession': accession, 'url': folder, 'issuer_cik': text_of(issuer, 'issuerCik').lstrip('0'),
                     'issuer': text_of(issuer, 'issuerName'), 'ticker': (text_of(issuer, 'issuerTradingSymbol') or '').upper().strip(),
                     'insider': names[best] if best is not None else '', 'role': roles[best][0] if best is not None else '',
                     'title': roles[best][1] if best is not None else '', 'owners': len(owners),
                     'code': code, 'date': text_of(tx, 'transactionDate')[:10], 'security': text_of(tx, 'securityTitle'),
                     'shares': shares, 'price': price, 'value': round(shares * price) if price else None,
                     'after': _num(text_of(tx, 'sharesOwnedFollowingTransaction')),
                     'direct': text_of(tx, 'directOrIndirectOwnership') != 'I', 'plan_10b5_1': plan})
    return rows


def xml_from_submission(txt):
    m = re.search(rb'<XML>\s*(.*?)\s*</XML>', txt, re.S | re.I)
    return m.group(1) if m else None


def collect(client, root, cfg=None):
    cfg = cfg or {}
    root = Path(root)
    cdir = root / 'cache' / 'insiders'
    cdir.mkdir(parents=True, exist_ok=True)
    seen = set(read_json(cdir / 'seen.json', []))
    store = cdir / 'trades.json.gz'
    trades = json.load(gzip.open(store, 'rt', encoding='utf-8')) if store.exists() else []
    entries = [(a, f) for a, f in feed_entries(client, int(cfg.get('feed_pages', 4))) if a not in seen]
    batch = int(cfg.get('batch', 250))
    read = errors = 0
    for accession, folder in entries[:batch]:
        try:
            txt = client.get(folder + accession + '.txt', sec=True)
            xml = xml_from_submission(txt)
            if xml:
                m = re.search(r'FILED AS OF DATE:\s*(\d{4})(\d{2})(\d{2})', txt[:4000])
                for t in parse_form4(xml, accession, folder):
                    if m:
                        t['filed'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
                    trades.append(t)
            seen.add(accession)
            read += 1
        except Exception as exc:
            errors += 1
            if errors > 20:
                break
            print(f'Form 4 {accession}: {exc}', flush=True)
    keep = (dt.date.today() - dt.timedelta(days=int(cfg.get('keep_days', 120)))).isoformat()
    uniq = {}
    for t in trades:
        if t.get('date', '') >= keep:
            uniq[(t['accession'], t['code'], t['date'], t['shares'], t.get('price'))] = t
    trades = sorted(uniq.values(), key=lambda t: (t['date'], t['accession']), reverse=True)
    with gzip.open(store.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
        json.dump(trades, f, separators=(',', ':'))
    store.with_suffix('.tmp').replace(store)
    write_json(cdir / 'seen.json', sorted(seen)[-60000:])
    return {'status': 'ok' if errors <= 20 else 'partial', 'read': read, 'waiting': max(0, len(entries) - batch), 'errors': errors,
            'trades': len(trades), 'updated_at': now()}


def summary(trades, today=None):
    """Per ticker over 90 days: open-market buys and sales, insiders, cluster buys (3+ insiders buying within 30 days)."""
    today = today or dt.date.today()
    d90, d30 = (today - dt.timedelta(days=90)).isoformat(), (today - dt.timedelta(days=30)).isoformat()
    by = {}
    for t in trades:
        if not t.get('ticker') or t['date'] < d90:
            continue
        a = by.setdefault(t['ticker'], {'ticker': t['ticker'], 'issuer': t['issuer'], 'cik': t['issuer_cik'], 'buys': 0, 'buy_value': 0,
                                        'sells': 0, 'sell_value': 0, 'buyers': set(), 'buyers30': set(), 'sellers': set(), 'last': '',
                                        'top_buy': None, 'ceo_cfo_sell': 0, 'plan_sells': 0})
        v = t.get('value') or 0
        if t['code'] == 'P':
            a['buys'] += 1; a['buy_value'] += v; a['buyers'].add(t['insider'])
            if t['date'] >= d30:
                a['buyers30'].add(t['insider'])
            if not a['top_buy'] or v > a['top_buy']['value']:
                a['top_buy'] = {k: t.get(k) for k in ('insider', 'role', 'title', 'date', 'shares', 'price', 'value', 'url')}
        else:
            a['sells'] += 1; a['sell_value'] += v; a['sellers'].add(t['insider'])
            a['plan_sells'] += bool(t.get('plan_10b5_1'))
            if t.get('role') in ('CEO', 'CFO'):
                a['ceo_cfo_sell'] += v
        a['last'] = max(a['last'], t['date'])
    out = []
    for a in by.values():
        out.append({**a, 'buyers': sorted(a['buyers']), 'sellers': len(a['sellers']), 'cluster': len(a['buyers30']) >= 3,
                    'buyers30': len(a['buyers30'])})
    return out


def notable(trades, n=400, min_buy=50_000, min_sell=1_000_000):
    """The latest trades worth showing: every purchase from $50K, sales from $1M (CEO / CFO sales from $250K)."""
    rows = [t for t in trades if t.get('value') and (t['code'] == 'P' and t['value'] >= min_buy or
                                                      t['code'] == 'S' and (t['value'] >= min_sell or t.get('role') in ('CEO', 'CFO') and t['value'] >= 250_000))]
    return rows[:n]


def publish(root, out_dir):
    root = Path(root)
    store = root / 'cache' / 'insiders' / 'trades.json.gz'
    if not store.exists():
        return None
    trades = json.load(gzip.open(store, 'rt', encoding='utf-8'))
    summ = summary(trades)
    data = {'generated_at': now(), 'trades_on_file': len(trades),
            'since': min((t['date'] for t in trades), default=None),
            'note': ('Form 4 open-market and private purchases (P) and sales (S) by officers, directors and 10% owners, as '
                     'filed with the SEC (due two business days after the trade). Grants, option exercises, tax withholding '
                     'and gifts are left out. "10b5-1" marks trades the filer says were made under a pre-arranged plan.'),
            'latest': notable(trades),
            'summary': sorted([a for a in summ if a['buys'] or a['sell_value'] >= 1_000_000],
                              key=lambda a: (-a['buyers30'], -a['buy_value']))}
    path = Path(out_dir) / 'insiders.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return data
