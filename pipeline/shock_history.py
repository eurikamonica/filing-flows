"""Compact, independent SEC quarterly history for the shock panel; no imputation.

One companyfacts request supplies all available quarters since 2009. Incremental
collection lives on shock-history, so it does not wait for the chart scan queue.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import time
import urllib.request

from . import facts as F, fsa as W

VERSION = 1
KEYS = ('revenue', 'oi', 'ni', 'ocf', 'capex', 'gp', 'rd', 'sbc')
PRIORITY = ('AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'PLTR', 'AMD', 'CRM', 'ORCL')


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def compute(companyfacts, now=None):
    """Latest disclosed USD facts with compact per-value filing evidence."""
    fx, rows = F.index_facts(companyfacts, currency='USD'), []
    ev = W.Evidence(fx)
    ends = sorted({e for key in KEYS for tag in F.CONCEPTS[key] for s, e in fx.get(tag, {})
                   if e >= '2009-01-01' and W._dur(fx[tag], e, False)[0] is not None})
    balances = sorted((fx.get('__instants__') or {}).get('Assets', {}))
    for end in ends:
        prev = max((d for d in set(ends + balances) if 75 <= (F.d(end)-F.d(d)).days <= 105), default=None)
        values, refs = {}, {}
        for key in KEYS:
            # Match existing concept priority, but get value and provenance from the
            # same duration reader (3m or YTD difference with the same fiscal start).
            candidates = []
            for tag in F.CONCEPTS[key]:
                value, used, how = W._dur(fx.get(tag), end, False)
                if finite(value):
                    candidates.append((tag, value, used, how))
            if candidates:
                preferred = next((x for x in candidates if x[0] == F.TOTAL_FIRST.get(key)), None)
                if preferred is None and key in F.CASH_FLOW_KEYS:
                    preferred = next((x for x in candidates if F.cash_flow_only(fx[x[0]])), None)
                tag, value, used, how = preferred or (max(candidates, key=lambda x:x[1]) if key in F.MAX_KEYS else candidates[0])
                values[key], refs[key] = value, ev.ref(tag, how, used)
        if 'revenue' not in values and not any(k in values for k in ('ni', 'oi', 'ocf')):
            continue
        if 'gp' not in values and 'revenue' in values:
            cost, cost_ref = W.keyed(fx, ev, 'cor', end, False)
            if finite(cost):
                values['gp'] = values['revenue'] - cost
                refs['gp'] = {'derived': 'revenue minus cost of revenue', 'inputs': [refs['revenue'], cost_ref]}
        for key, tag, day in [('assets_open','Assets',prev), ('assets_close','Assets',end),
                              ('current_assets','AssetsCurrent',end), ('current_liabilities','LiabilitiesCurrent',end)]:
            if day:
                value, ref, _ = W.balance(fx, ev, [tag], day)
                if finite(value):
                    values[key], refs[key] = value, ref
        wc, wc_refs = W.working_capital(fx, ev, end, prev, False)
        # Do not infer zero inventory or substitute accrued liabilities for payables.
        if finite(wc.get('dso')):
            values['dso'], refs['dso'] = wc['dso'], {'derived':'average receivables / revenue * days', 'inputs':wc_refs}
        if all(finite(wc.get(k)) for k in ('dso','dio','dpo')) and not wc.get('ap_proxy'):
            values['ccc'], refs['ccc'] = wc['dso']+wc['dio']-wc['dpo'], {'derived':'DSO + DIO - DPO', 'inputs':wc_refs}
        rows.append({'end':end, 'values':values, 'sources':refs})
    return {'v':VERSION, 'cik':companyfacts.get('cik'), 'unit':'USD', 'generated_at':now or dt.datetime.now(dt.timezone.utc).isoformat(),
            'rows':rows, 'src':ev.out(), 'source':'SEC companyfacts',
            'coverage':{k:sum(finite(r['values'].get(k)) for r in rows) for k in (*KEYS,'assets_open','assets_close','current_assets','current_liabilities','dso','ccc')},
            'basis':'Latest reported versions; quarter values may be same-start YTD differences. Not a point-in-time dataset.'}


def read(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False))
    tmp.replace(path)


def queue(companies, ledger, now):
    """New/changed companies first; old failures back off; refresh successful facts weekly."""
    priority = set(PRIORITY)
    for c in companies:
        if c.get('ticker') in PRIORITY:
            peers = sorted((p for p in companies if p.get('sic') == c.get('sic') and p.get('ticker')),
                           key=lambda p:-(p.get('revenue') or 0))[:6]
            priority.update(p['ticker'] for p in peers)
    pending = []
    for c in companies:
        if not str(c.get('cik','')).isdigit():
            continue
        old = ledger.get(str(c['cik']), {})
        age = now-old.get('attempted_at',0)
        if age < (6*3600 if old.get('error') else 0):
            continue
        if old.get('v') == VERSION and old.get('filed','') >= c.get('filed','') and age < 7*86400:
            continue
        pending.append(c)
    return sorted(pending, key=lambda c:(0 if ledger.get(str(c['cik']),{}).get('v') == VERSION and c.get('filed','') > ledger[str(c['cik'])].get('filed','') else 1 if ledger.get(str(c['cik']),{}).get('v') != VERSION else 2,
                                         c.get('ticker') not in priority, -(c.get('revenue') or 0), str(c['cik'])))


def collect(root, index, limit=300, minutes=8, fetch=None):
    if fetch is None:
        from . import sec
        # Leave ample request headroom for the site's other SEC collectors.
        sec.MIN_INTERVAL = max(sec.MIN_INTERVAL, 0.5)
        fetch = lambda cik:sec.get_json(sec.companyfacts_url(cik))
    root = Path(root)
    ledger = read(root/'ledger.json', {})
    companies = index.get('companies', [])
    todo, start = queue(companies, ledger, time.time()), time.monotonic()
    attempted = succeeded = 0
    for c in todo[:limit]:
        if time.monotonic()-start >= minutes*60:
            break
        cik = str(c['cik'])
        attempted += 1
        old = ledger.get(cik,{})
        try:
            doc = compute(fetch(int(cik)))
            if str(doc.get('cik')) != cik:
                raise ValueError('SEC company identity mismatch')
            write(root/'public'/'c'/f'{cik}.json', doc)
            ledger[cik] = {'v':VERSION, 'filed':c.get('filed',''), 'attempted_at':time.time(), 'quarters':len(doc['rows']),
                           'first':doc['rows'][0]['end'] if doc['rows'] else None, 'last':doc['rows'][-1]['end'] if doc['rows'] else None}
            succeeded += 1
        except Exception as exc:
            # Keep last successful data and its version; expose failures without credentials/URLs.
            ledger[cik] = {**old, 'attempted_at':time.time(), 'error':type(exc).__name__}
        write(root/'ledger.json', ledger)
    universe = {str(c['cik']) for c in companies if str(c.get('cik','')).isdigit()}
    have = [v for k,v in ledger.items() if k in universe and v.get('v') == VERSION]
    status = {'v':VERSION, 'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'total':len(universe),
              'processed':len(have), 'with_history':sum(v.get('quarters',0)>0 for v in have),
              'ready24':sum(v.get('quarters',0)>=24 for v in have), 'pending':len(universe)-len(have),
              'failed':sum(bool(v.get('error')) for k,v in ledger.items() if k in universe),
              'run':{'attempted':attempted, 'succeeded':succeeded}, 'earliest':'2009-01-01',
              'schedule':'Every 20 minutes; GitHub scheduling may be delayed', 'batch_limit':limit,
              'note':'Counts are source quarters, not guaranteed complete model rows. Missing facts are never imputed.'}
    write(root/'public'/'status.json', status)
    return status


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--index', default='https://filing-flows.com/data/index.json')
    p.add_argument('--limit', type=int, default=300)
    p.add_argument('--minutes', type=float, default=8)
    args = p.parse_args()
    if args.index.startswith('https://'):
        with urllib.request.urlopen(args.index, timeout=30) as response:
            index = json.load(response)
    else:
        index = read(args.index,{})
    if not index.get('companies'):
        raise SystemExit('Company index unavailable; existing data preserved')
    print(json.dumps(collect(args.root,index,max(1,min(args.limit,1000)),max(1,min(args.minutes,9)))))


if __name__ == '__main__':
    main()
