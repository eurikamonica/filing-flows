"""Debt & rates: every company's borrowing, what it pays, how safe it is — from its own SEC filings, plus market rates.

  collect  per company (largest first, new filings first, then the stalest; within a time budget):
             companyfacts (XBRL)       debt, cash, interest, EBIT, maturities, weighted rates, revolver, convertibles,
                                       quarter-end history since 2009 (debt_facts.py)
             10-K / 10-Q XBRL instance each bond, loan, revolver and convertible tagged on its own (debt_docs.py)
             term sheets (FWP)         every bond priced since 2001 found by EDGAR full-text search: coupon, size,
                                       maturity, price, yield, spread to Treasuries, ratings, conversion terms
             424B2 / 424B5 covers      tranches named on prospectus covers when there is no term sheet
             credit agreements         facility, size, SOFR margin and fee, floor, maturity, financial covenants
             8-K items 1.01 / 2.03     the timeline of new financing obligations
             FDIC (banks)              deposits, CDs (time deposits by size), brokered and uninsured deposits, deposit
                                       cost, cost of funds and margin of the company's bank subsidiaries
           Parsed results live in <root>/companies/<cik>.json on the branch "debt-history"; documents already read are
           never fetched again.
  rates    FRED (Treasury curve, SOFR, commercial paper, prime, Moody's Aaa/Baa, ICE BofA spreads by rating) and the
           FDIC's national deposit rates (savings, money market, CDs from 1 to 60 months)
  build    public/ — index.json (one row per company), c/<cik>.json (the company page), rates.json, banks.json,
           calibration.json: the safety analysis and the implied CDS (debt_model.py) with weekly prices from the
           rotation history.

    python app/debt.py collect --root debt --site-index site/index.json --minutes 30
    python app/debt.py rates   --root debt
    python app/debt.py build   --root debt --prices rh/public
"""
import argparse
import datetime as dt
import gzip
import json
import math
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Client, read_json, write_json  # noqa: E402
import debt_docs as DD  # noqa: E402
import debt_facts as DF  # noqa: E402
import debt_model as DM  # noqa: E402
import hidden_leverage as HL  # noqa: E402

SEC = 'https://data.sec.gov'
ARCH = 'https://www.sec.gov/Archives/edgar/data'
EFTS = 'https://efts.sec.gov/LATEST/search-index'
FDIC = 'https://api.fdic.gov/banks'
BANK_SIC = {'6021', '6022', '6029', '6035', '6036', '6712', '6111', '6153'}
STRUCTURED_SIC = {'6211', '6199', '6021', '6022'}      # issuers of thousands of structured-note 424B2s
FDIC_FIELDS = ('CERT,REPDTE,ASSET,DEP,DEPDOM,NTR,NTRTIME,NTRTMLGJ,NTRTMMED,NTRSMMDA,BRO,COREDEP,DEPINS,DEPUNA,EINTEXP,EDEPDOM,'
               'INTEXPY,NIMY,INTINCY')
RATE_SERIES = {
    'DGS1MO': '1-month Treasury', 'DGS3MO': '3-month Treasury', 'DGS6MO': '6-month Treasury', 'DGS1': '1-year Treasury',
    'DGS2': '2-year Treasury', 'DGS3': '3-year Treasury', 'DGS5': '5-year Treasury', 'DGS7': '7-year Treasury',
    'DGS10': '10-year Treasury', 'DGS20': '20-year Treasury', 'DGS30': '30-year Treasury', 'SOFR': 'SOFR (overnight)',
    'DFF': 'Fed funds (effective)', 'DPRIME': 'Bank prime loan rate', 'DCPN30': 'Commercial paper, AA nonfinancial, 30 days',
    'RIFSPPFAAD30NB': 'Commercial paper, AA financial, 30 days', 'RIFSPPNA2P2D30NB': 'Commercial paper, A2/P2 nonfinancial, 30 days',
    'DAAA': "Moody's Aaa corporate yield", 'DBAA': "Moody's Baa corporate yield", 'BAMLC0A0CM': 'ICE BofA US corporate (IG) spread',
    'BAMLC0A1CAAA': 'AAA spread', 'BAMLC0A2CAA': 'AA spread', 'BAMLC0A3CA': 'A spread', 'BAMLC0A4CBBB': 'BBB spread',
    'BAMLH0A0HYM2': 'High-yield spread', 'BAMLH0A1HYBB': 'BB spread', 'BAMLH0A2HYB': 'B spread', 'BAMLH0A3HYC': 'CCC and lower spread',
    'MORTGAGE30US': '30-year mortgage rate', 'TERMCBAUTO48NS': '48-month new car loan (banks)',
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def cik10(c):
    return f'{int(c):010d}'


def _client():
    cfg = read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {})
    http = cfg.get('http', {})
    return Client(tempfile.mkdtemp(prefix='debt-raw-'),
                  {**http, 'extra_hosts': ['efts.sec.gov', 'fred.stlouisfed.org', 'api.stlouisfed.org', 'www.fdic.gov'],
                   'host_intervals': {**http.get('host_intervals', {}), 'data.sec.gov': 0.13, 'www.sec.gov': 0.13, 'efts.sec.gov': 0.25,
                                      'api.fdic.gov': 0.3, 'fred.stlouisfed.org': 0.4, 'www.fdic.gov': 1.0},
                   'timeout': 60, 'max_response_mb': 60})


# ------------------------------------------------------------------ universe
def _num(v):
    """A numeric revenue (the site index's 'rev' is a formatted string such as \"$2.6B\" and 'revenue' may be null)."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def universe(site_index):
    ix = read_json(site_index, {}) if site_index else {}
    rows = {}
    for r in ix.get('companies', []):
        if not r.get('cik'):
            continue
        c = int(r['cik'])
        if c not in rows or (r.get('filed') or '') > (rows[c].get('filed') or ''):
            rows[c] = r
    out = [{'cik': c, 'ticker': r.get('ticker'), 'name': r.get('name'), 'sector': r.get('sector'), 'industry': r.get('industry'),
            'sic': str(r.get('sic') or ''), 'revenue': _num(r.get('revenue'))} for c, r in rows.items()]
    out.sort(key=lambda r: -(r['revenue'] or 0))
    return out


# ------------------------------------------------------------------ one company
def _recent(sub):
    r = sub.get('filings', {}).get('recent', {})
    n = len(r.get('form', []))
    g = lambda k: r.get(k) or [''] * n
    return [dict(form=f, acc=a, doc=d, date=fd, items=i, desc=ds, report=rp) for f, a, d, fd, i, ds, rp in
            zip(g('form'), g('accessionNumber'), g('primaryDocument'), g('filingDate'), g('items'), g('primaryDocDescription'), g('reportDate'))]


def _efts(client, q, forms, cik, pages=2):
    hits = []
    for p in range(pages):
        url = f'{EFTS}?q={q}&forms={forms}&ciks={cik10(cik)}' + (f'&from={100 * p}' if p else '')
        try:
            body = client.json(url, sec=True)
        except Exception as exc:
            print(f'  efts {cik} {q[:30]}: {exc}', flush=True)
            break
        hh = body.get('hits', {}).get('hits', [])
        hits += hh
        if len(hh) < 100:
            break
    return hits


def _instance(client, cik, acc):
    """(instruments, accession) from one filing's XBRL instance and label linkbase."""
    a = acc.replace('-', '')
    idx = client.json(f'{ARCH}/{int(cik)}/{a}/index.json', sec=True)
    names = [i['name'] for i in idx.get('directory', {}).get('item', [])]
    inst = [n for n in names if n.endswith('_htm.xml')] or [n for n in names if n.endswith('.xml') and not re.search(r'_(cal|def|lab|pre)\.xml$|FilingSummary|MetaLinks', n)]
    if not inst:
        return []
    raw = client.get(f'{ARCH}/{int(cik)}/{a}/{inst[0]}', sec=True)
    labs = {}
    lab = [n for n in names if n.endswith('_lab.xml')]
    if lab:
        try:
            labs = DD.parse_labels(client.get(f'{ARCH}/{int(cik)}/{a}/{lab[0]}', sec=True))
        except Exception:
            labs = {}
    return DD.parse_instance(raw, labs)


def collect_one(client, root, co, state, deep=True):
    """Fetch and parse what is new for one company. Returns the company record (also written to companies/<cik>.json)."""
    cik = co['cik']
    path = Path(root) / 'companies' / f'{cik}.json'
    rec = read_json(path, {}) or {}
    rec.update({k: co[k] for k in ('cik', 'ticker', 'name', 'sector', 'industry', 'sic') if co.get(k)})
    docs = rec.setdefault('docs', {})                      # accession:file -> parsed (or the reason it was skipped)
    sub = client.json(f'{SEC}/submissions/CIK{cik10(cik)}.json', sec=True)
    rec['sic'] = str(sub.get('sic') or rec.get('sic') or '')
    rec['sic_description'] = sub.get('sicDescription')
    rec['name'] = sub.get('name') or rec.get('name')
    rows = _recent(sub)
    # companyfacts: the snapshot and the quarter-end history
    try:
        cf = client.json(f'{SEC}/api/xbrl/companyfacts/CIK{cik10(cik)}.json', sec=True)
        snap, src = DF.snapshot(cf)
        rec['snapshot'], rec['sources'] = snap, src
        rec['history'] = DF.history(cf)
        rec['hidden_leverage'] = HL.extract(cf, cik, snap.get('balance_date'))
    except Exception as exc:
        rec['facts_error'] = f'{type(exc).__name__}: {exc}'[:200]
    # the latest 10-K and the latest 10-Q after it: each instrument
    periodic = [r for r in rows if r['form'] in ('10-K', '10-Q', '20-F', '40-F', '10-K/A')]
    tenk = next((r for r in periodic if r['form'] in ('10-K', '20-F', '40-F')), None)
    tenq = next((r for r in periodic if r['form'] == '10-Q' and (not tenk or r['date'] > tenk['date'])), None)
    latest_periodic = tenq or tenk
    if latest_periodic and latest_periodic.get('doc'):
        # One primary filing per company; cache by accession to bound SEC load.
        # Text matches are leads, not amounts, and never modify modeled debt.
        f = latest_periodic
        if (rec.get('hidden_text_source') != f['acc']
                or not isinstance(rec.get('hidden_text_signals'), list)):
            try:
                raw = client.get(f'{ARCH}/{int(cik)}/{f["acc"].replace("-", "")}/{f["doc"]}', sec=True)
                rec['hidden_text_signals'] = HL.scan_filing_text(
                    raw, cik, f['acc'], f['doc'], f['form'], f['date'])
                rec['hidden_text_source'] = f['acc']
                rec.pop('hidden_text_error', None)
            except Exception as exc:
                rec['hidden_text_error'] = str(exc)[:180]
        if isinstance(rec.get('hidden_leverage'), dict):
            rec['hidden_leverage']['text_signals'] = rec.get('hidden_text_signals', [])
            rec['hidden_leverage']['text_filing'] = {
                'accession': rec.get('hidden_text_source'), 'form': f['form'],
                'filed': f['date'], 'source_url': HL.sec_url(cik, f['acc'], f['doc'])}
    for kind, f in (('10-K', tenk), ('10-Q', tenq)):
        if not f:
            continue
        key = f'xbrl:{f["acc"]}'
        if key not in docs:
            try:
                docs[key] = {'instruments': _instance(client, cik, f['acc']), 'form': f['form'], 'date': f['date'], 'report': f['report']}
            except Exception as exc:
                docs[key] = {'error': str(exc)[:160], 'form': f['form'], 'date': f['date']}
        rec[f'xbrl_{kind}'] = key
    # financing events (8-K items 1.01 entry into a material agreement, 2.03 direct financial obligation, 2.04 trigger)
    ev = []
    for r in rows:
        if r['form'].startswith('8-K') and re.search(r'\b(1\.01|2\.03|2\.04)\b', r['items'] or '') and r['date'] >= '2010-01-01':
            ev.append({'date': r['date'], 'items': r['items'], 'acc': r['acc'], 'doc': r['doc'], 'desc': r['desc']})
    rec['events'] = ev[:80]
    if deep:
        # bond term sheets via full-text search ("term sheet" covers pricing / final term sheets)
        structured = rec['sic'] in STRUCTURED_SIC
        fwps = _efts(client, '%22term%20sheet%22', 'FWP', cik, pages=1 if structured else 3)
        fwps.sort(key=lambda h: h['_source'].get('file_date', ''), reverse=True)
        n_new = 0
        for h in fwps:
            if n_new >= (15 if structured else 60):
                break
            key = h['_id']
            if key in docs:
                continue
            acc, fn = key.split(':', 1)
            try:
                raw = client.get(f'{ARCH}/{int(cik)}/{acc.replace("-", "")}/{fn}', sec=True)
                docs[key] = {'kind': 'fwp', 'date': h['_source'].get('file_date'), 'tranches': DD.parse_term_sheet(raw, h['_source'].get('file_date'))}
            except Exception as exc:
                docs[key] = {'kind': 'fwp', 'date': h['_source'].get('file_date'), 'error': str(exc)[:120]}
            n_new += 1
        have_fwp = any(d.get('kind') == 'fwp' and d.get('tranches') for d in docs.values())
        if not have_fwp and not structured:                 # prospectus covers when no term sheet was found
            for r in [r for r in rows if r['form'] in ('424B2', '424B5', '424B3')][:12]:
                key = f'{r["acc"]}:{r["doc"]}'
                if key in docs:
                    continue
                try:
                    raw = client.get(f'{ARCH}/{int(cik)}/{r["acc"].replace("-", "")}/{r["doc"]}', sec=True)
                    docs[key] = {'kind': '424b', 'date': r['date'], 'tranches': DD.parse_prospectus_cover(raw, r['date'])}
                except Exception as exc:
                    docs[key] = {'kind': '424b', 'date': r['date'], 'error': str(exc)[:120]}
        # credit agreements: exhibits whose description names a credit / loan agreement, newest first
        hits = _efts(client, '%22credit%20agreement%22', '8-K,10-K,10-Q', cik, pages=1)
        cand = []
        for h in hits:
            s = h['_source']
            ft, desc = str(s.get('file_type', '')).upper(), str(s.get('file_description', '')).upper()
            if not ft.startswith('EX-10'):
                continue
            score = 2 if re.search(r'CREDIT|LOAN|FACILITY', desc) else 1 if 'AMEND' in desc or re.search(r'EX(HIBIT)?[- ]?10', desc) else 0
            cand.append((score, s.get('file_date', ''), h['_id']))
        cand.sort(reverse=True)
        got = 0
        for score, date, key in sorted(cand, key=lambda x: (x[0], x[1]), reverse=True)[:6]:
            if got >= 3:
                break
            if key in docs:
                got += 1
                continue
            acc, fn = key.split(':', 1)
            try:
                raw = client.get(f'{ARCH}/{int(cik)}/{acc.replace("-", "")}/{fn}', sec=True)
                if len(raw) > 6e6:
                    raw = raw[:6000000]
                parsed = DD.parse_credit_agreement(raw, date)
                docs[key] = {'kind': 'agreement', 'date': date, **{('agreement_kind' if k == 'kind' else k): v for k, v in parsed.items()}}
            except Exception as exc:
                docs[key] = {'kind': 'agreement', 'date': date, 'error': str(exc)[:120]}
            got += 1
    rec['fetched_at'] = now()
    rec['signature'] = signature(rows)
    write_json(path, rec)
    return rec


def signature(rows):
    keep = [r['acc'] for r in rows if r['form'] in ('10-K', '10-Q', '20-F', '8-K', 'FWP', '424B2', '424B5')]
    return keep[0] if keep else None


def collect(client, root, cos, minutes=30.0, refresh_days=21, first=()):
    root = Path(root)
    st = read_json(root / 'state.json', {}) or {}
    S = st.setdefault('companies', {})
    t0 = time.time()
    today = dt.datetime.now(dt.timezone.utc)
    first = {str(x).upper() for x in first}

    def due(co):
        s = S.get(str(co['cik'])) or {}
        if s.get('retry_after') and s['retry_after'] > now():
            return None
        if not s.get('fetched_at'):
            return (0, -_num(co.get('revenue')))
        age = (today - dt.datetime.fromisoformat(s['fetched_at'])).days
        return (1, -age) if age >= refresh_days else None

    order = [c for c in cos if (c.get('ticker') or '').upper() in first]
    rest = sorted([(d, c) for c in cos if (d := due(c)) is not None and c not in order], key=lambda x: x[0])
    order += [c for _, c in rest]
    done = errors = 0
    for co in order:
        if time.time() - t0 > minutes * 60:
            break
        s = S.setdefault(str(co['cik']), {})
        try:
            collect_one(client, root, co, s)
            s.update(fetched_at=now(), fails=0, error=None, retry_after=None)
            done += 1
        except Exception as exc:
            errors += 1
            s['fails'] = (s.get('fails') or 0) + 1
            s['error'] = f'{type(exc).__name__}: {exc}'[:200]
            s['retry_after'] = (today + dt.timedelta(days=min(30, 2 ** s['fails']))).isoformat(timespec='seconds')
            print(f'  {co.get("ticker")} {co["cik"]}: {s["error"]}', flush=True)
        if done % 20 == 0:
            write_json(root / 'state.json', st)
    have = sum(1 for c in cos if (S.get(str(c['cik'])) or {}).get('fetched_at'))
    st['summary'] = {'companies': len(cos), 'on_file': have, 'this_run': done, 'errors': errors, 'at': now()}
    write_json(root / 'state.json', st)
    return st['summary']


# ------------------------------------------------------------------ banks (FDIC)
def _norm_name(s):
    s = re.sub(r'\s*/[A-Z]{2,3}/?\s*$', '', (s or '').upper())          # SEC state suffixes: 'BANK OF AMERICA CORP /DE/'
    s = re.sub(r'[^A-Z0-9 ]', ' ', s.replace('&', ' AND '))
    s = re.sub(r'\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|THE|GROUP|HOLDINGS?|BANCORPORATION|NA|N A|NATIONAL ASSOCIATION|FINANCIAL|BANCSHARES|AND)\b', ' ', s)
    return re.sub(r'\s+', '', s)


def collect_banks(client, root, minutes=8.0):
    """FDIC: every active institution with its holding company once, then quarterly financials of the subsidiaries of
    each bank company on the site (matched by holding-company name)."""
    root = Path(root); t0 = time.time()
    inst_path = root / 'cache' / 'fdic_institutions.json'
    inst = read_json(inst_path, {})
    if not inst.get('rows') or (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(inst['at'])).days > 7:
        rows, off = [], 0
        while True:
            b = client.json(f'{FDIC}/institutions?filters=ACTIVE:1&fields=CERT,NAME,NAMEHCR,RSSDHCR,ASSET,DEP,STALP&limit=10000&offset={off}')
            d = [x['data'] for x in b.get('data', [])]
            rows += d
            if len(d) < 10000:
                break
            off += 10000
        inst = {'at': now(), 'rows': rows}
        write_json(inst_path, inst)
    by_hc = {}
    for r in inst['rows']:
        k = _norm_name(r.get('NAMEHCR') or r.get('NAME'))
        by_hc.setdefault(k, []).append(r)
    out = 0
    for p in sorted((root / 'companies').glob('*.json')):
        if time.time() - t0 > minutes * 60:
            break
        rec = read_json(p, {})
        if str(rec.get('sic')) not in BANK_SIC:
            continue
        subs = by_hc.get(_norm_name(rec.get('name'))) or []
        if not subs:
            rec['fdic'] = {'matched': False}
            write_json(p, rec); continue
        subs = sorted(subs, key=lambda r: -(r.get('ASSET') or 0))[:3]
        b = rec.get('fdic') or {}
        if b.get('at') and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(b['at'])).days < 20:
            continue
        series = {}
        for s in subs:
            try:
                fin = client.json(f'{FDIC}/financials?filters=CERT:{s["CERT"]}%20AND%20REPDTE:[20091231%20TO%2099991231]&fields={FDIC_FIELDS}&sort_by=REPDTE&sort_order=ASC&limit=100')
                series[str(s['CERT'])] = {'name': s['NAME'], 'rows': [x['data'] for x in fin.get('data', [])]}
            except Exception as exc:
                series[str(s['CERT'])] = {'name': s['NAME'], 'error': str(exc)[:120]}
        rec['fdic'] = {'matched': True, 'at': now(), 'holding': subs[0].get('NAMEHCR'), 'subsidiaries': series}
        write_json(p, rec); out += 1
    return {'banks_updated': out}


def bank_summary(fd):
    """Deposits and CDs of the largest subsidiary bank: latest quarter and the quarterly series since 2010."""
    if not fd or not fd.get('matched'):
        return None
    subs = [v for v in (fd.get('subsidiaries') or {}).values() if v.get('rows')]
    if not subs:
        return None
    main = max(subs, key=lambda v: (v['rows'][-1].get('DEP') or 0))
    rows = main['rows']
    ser = []
    prev = {}
    for r in rows:
        d = r.get('REPDTE')
        if not d:
            continue
        q = int(d[4:6]) // 3
        ytd_dep = r.get('EDEPDOM'); ytd_int = r.get('EINTEXP')
        if q > 1 and prev.get('y') == d[:4]:
            dq = None if ytd_dep is None or prev.get('dep') is None else ytd_dep - prev['dep']
            iq = None if ytd_int is None or prev.get('int') is None else ytd_int - prev['int']
        else:
            dq, iq = ytd_dep, ytd_int
        prev = {'y': d[:4], 'dep': ytd_dep, 'int': ytd_int}
        depdom = r.get('DEPDOM') or r.get('DEP')
        tm = r.get('NTRTIME')
        ser.append({'date': f'{d[:4]}-{d[4:6]}-{d[6:]}', 'deposits': _k(r.get('DEP')), 'domestic': _k(depdom), 'time': _k(tm),
                    'time_over_250k': _k(r.get('NTRTMLGJ')), 'time_100_250k': _k(r.get('NTRTMMED')),
                    'time_small': _k(tm - (r.get('NTRTMLGJ') or 0) - (r.get('NTRTMMED') or 0)) if tm is not None else None,
                    'money_market': _k(r.get('NTRSMMDA')), 'brokered': _k(r.get('BRO')), 'uninsured': _k(r.get('DEPUNA')),
                    'insured': _k(r.get('DEPINS')), 'interest_bearing': _k(r.get('NTR')),
                    'deposit_cost': (4 * dq / depdom) if dq is not None and depdom else None,
                    'cost_of_funds': (r.get('INTEXPY') or 0) / 100 if r.get('INTEXPY') is not None else None,
                    'nim': (r.get('NIMY') or 0) / 100 if r.get('NIMY') is not None else None,
                    'asset_yield': (r.get('INTINCY') or 0) / 100 if r.get('INTINCY') is not None else None})
    last = ser[-1] if ser else {}
    return {'bank': main['name'], 'holding': fd.get('holding'), 'latest': last, 'series': ser,
            'cd_share': (last.get('time') or 0) / last['domestic'] if last.get('domestic') else None,
            'uninsured_share': (last.get('uninsured') or 0) / last['deposits'] if last.get('deposits') else None}


def _k(v):
    return None if v is None else v * 1000.0          # FDIC reports thousands of dollars


# ------------------------------------------------------------------ rates
def fetch_rates(client, root):
    import macro_history as MH
    folder = Path(root) / 'cache' / 'rates'; folder.mkdir(parents=True, exist_ok=True)
    got, bad = 0, []
    for sid in RATE_SERIES:
        p = folder / f'{sid}.csv'
        if p.exists() and time.time() - p.stat().st_mtime < 18 * 3600:
            continue
        try:
            body = MH.fetch_one(sid)
            if len(MH.parse_csv(body)) > 10:
                p.write_text(body, encoding='utf-8'); got += 1
        except Exception as exc:
            bad.append(f'{sid}: {exc}'[:80])
        time.sleep(0.4)
    # FDIC national deposit rates: the current month's table, kept month by month
    nat = read_json(Path(root) / 'cache' / 'fdic_national_rates.json', {'months': {}})
    try:
        html = client.get('https://www.fdic.gov/national-rates-and-rate-caps').decode('utf-8', 'replace')
        cur = parse_national_rates(html)
        if cur.get('rates'):
            nat['months'][cur['as_of'] or now()[:7]] = cur['rates']
        try:
            prev = client.get('https://www.fdic.gov/resources/bankers/national-rates/previous-rates.html').decode('utf-8', 'replace')
            for m, r in parse_previous_rates(prev).items():
                nat['months'].setdefault(m, r)
        except Exception:
            pass
        write_json(Path(root) / 'cache' / 'fdic_national_rates.json', nat)
    except Exception as exc:
        bad.append(f'FDIC national rates: {exc}'[:120])
    return {'rates_updated': got, 'failed': bad}


PRODUCTS = ['Savings', 'Interest Checking', 'Money Market', '1 month CD', '3 month CD', '6 month CD', '12 month CD', '24 month CD',
            '36 month CD', '48 month CD', '60 month CD']


def parse_national_rates(html):
    t = DD.to_text(html)
    m = re.search(r'Monthly Rate Cap Information as of\s+([A-Z][a-z]+ \d{1,2}, \d{4})', t)
    as_of = DD.parse_date(m.group(1))[:7] if m else None
    rates = {}
    for p in PRODUCTS:
        mm = re.search(re.escape(p) + r'\s*\|\s*(\d+\.\d+)\s*\|\s*(\d+\.\d+)', t)
        if mm:
            rates[p] = {'national': float(mm.group(1)), 'cap': float(mm.group(2))}
    return {'as_of': as_of, 'rates': rates}


def parse_previous_rates(html):
    """Best effort: month tables on the previous-rates page ('<Month YYYY>' heading followed by product rows)."""
    t = DD.to_text(html)
    out = {}
    for m in re.finditer(r'([A-Z][a-z]+)\s+(\d{4})', t):
        mon = DD.MON3.get(m.group(1).lower()[:3])
        if not mon:
            continue
        seg = t[m.end():m.end() + 2500]
        rates = {}
        for p in PRODUCTS:
            mm = re.search(re.escape(p) + r'\s*\|\s*(\d+\.\d+)', seg)
            if mm:
                rates[p] = {'national': float(mm.group(1))}
        if len(rates) >= 4:
            out.setdefault(f'{m.group(2)}-{mon:02d}', rates)
    return out


def load_rates(root):
    import macro_history as MH
    folder = Path(root) / 'cache' / 'rates'
    out = {}
    for sid in RATE_SERIES:
        p = folder / f'{sid}.csv'
        if p.exists():
            out[sid] = MH.parse_csv(p.read_text(encoding='utf-8'))
    return out


def rate_at(series, day):
    """Latest value on or before a date (decimal, e.g. 0.0425)."""
    if not series:
        return None
    if isinstance(day, str):
        day = dt.date.fromisoformat(day[:10])
    lo, hi = 0, len(series) - 1
    if series[0][0] > day:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid][0] <= day:
            lo = mid
        else:
            hi = mid - 1
    return series[lo][1] / 100.0


# ------------------------------------------------------------------ prices (rotation history weekly closes)
def load_prices(prices_dir, ticker):
    if not prices_dir or not ticker:
        return None
    p = Path(prices_dir) / 't' / f'{ticker.replace(".", "-")}.json'
    if not p.exists():
        p = Path(prices_dir) / 't' / f'{ticker}.json'
        if not p.exists():
            return None
    d = json.loads(p.read_text(encoding='utf-8'))
    s = dt.date.fromisoformat(d['start'])
    return [(s + dt.timedelta(days=7 * i), v) for i, v in enumerate(d['c']) if v is not None]


def vol_at(px, i, n=52):
    """Annualised volatility of the n weekly log returns up to index i."""
    if i < 12:
        return None
    lo = max(1, i - n + 1)
    r = [math.log(px[k][1] / px[k - 1][1]) for k in range(lo, i + 1) if px[k][1] > 0 and px[k - 1][1] > 0]
    if len(r) < 12:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1) * 52)


# ------------------------------------------------------------------ build
def issues_of(rec):
    """Every tranche from term sheets and prospectus covers, newest first, de-duplicated (a 424B repeating a term sheet)."""
    out, seen = [], set()
    docs = rec.get('docs') or {}
    for key, d in sorted(docs.items(), key=lambda kv: kv[1].get('date') or '', reverse=True):
        if d.get('kind') not in ('fwp', '424b'):
            continue
        for t in d.get('tranches') or []:
            k = (t.get('coupon'), t.get('maturity', '')[:4] if t.get('maturity') else t.get('maturity_year'), t.get('currency'), bool(t.get('floating')))
            if k in seen:
                continue
            seen.add(k)
            acc, fn = key.split(':', 1)
            out.append({**t, 'date': t.get('trade_date') or d.get('date'), 'source': d['kind'],
                        'url': f'{ARCH}/{int(rec["cik"])}/{acc.replace("-", "")}/{fn}'})
    return out


def agreements_of(rec):
    out = []
    for key, d in (rec.get('docs') or {}).items():
        if d.get('kind') != 'agreement' or d.get('error') or d.get('agreement_kind') in ('indenture', 'other', None):
            continue
        acc, fn = key.split(':', 1)
        out.append({**{k: v for k, v in d.items() if k != 'margin_text'}, 'url': f'{ARCH}/{int(rec["cik"])}/{acc.replace("-", "")}/{fn}'})
    out.sort(key=lambda a: a.get('dated') or a.get('date') or '', reverse=True)
    return out


def instruments_of(rec):
    docs = rec.get('docs') or {}
    for k in ('xbrl_10-Q', 'xbrl_10-K'):
        d = docs.get(rec.get(k) or '') or {}
        if d.get('instruments'):
            inst = d['instruments']
            other = docs.get(rec.get('xbrl_10-K') or '') if k == 'xbrl_10-Q' else None
            if other and other.get('instruments') and len(other['instruments']) > len(inst):
                names = {i['name'] for i in inst}
                yr = dt.date.today().year
                inst = inst + [dict(i, from_10k=True) for i in other['instruments'] if i['name'] not in names
                               and not (i.get('maturity_year') and i['maturity_year'] < yr)]
            return inst, d.get('form'), d.get('report') or d.get('date')
    return [], None, None


def monthly_implied(rec, px, rates):
    """Month-end implied spread / distance to default since 2010 from as-filed debt and shares and weekly prices."""
    hist = rec.get('history') or []
    if not px or not hist:
        return []
    out, hi = [], 0
    last_m = None
    for i, (d, close) in enumerate(px):
        if d.year < 2010:
            continue
        m = (d.year, d.month)
        nxt = px[i + 1][0] if i + 1 < len(px) else None
        if nxt and (nxt.year, nxt.month) == m:
            continue                                     # month-end weeks only
        ds = d.isoformat()
        while hi + 1 < len(hist) and hist[hi + 1]['filed'] <= ds:
            hi += 1
        h = hist[hi]
        if h['filed'] > ds or not h.get('total_debt') or not h.get('shares'):
            continue
        sig = vol_at(px, i)
        r1 = rate_at(rates.get('DGS1'), ds)
        if sig is None or r1 is None:
            continue
        imp = DM.implied(close * h['shares'], sig, None, h['total_debt'], r1)
        if imp:
            out.append([ds[:7], round(imp['spread_5y_bps'], 2), round(imp['dd'], 3), round(sig, 4)])
        last_m = m
    return out


def build(root, prices=None, verbose=True):
    root = Path(root); pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    rates = load_rates(root)
    today = dt.date.today().isoformat()
    r1, r5 = rate_at(rates.get('DGS1'), today), rate_at(rates.get('DGS5'), today)
    sofr = rate_at(rates.get('SOFR'), today)
    oas_now = {sid: (rates[sid][-1][1] if rates.get(sid) else None) for _, sid in DM.RATING_BANDS}
    recs = []
    for p in sorted((root / 'companies').glob('*.json')):
        rec = read_json(p, {})
        if rec.get('cik'):
            recs.append(rec)
    # pass 1: model spreads per company (month-end) and calibration pairs from term sheets
    pairs, cache = [], {}
    for rec in recs:
        px = load_prices(prices, rec.get('ticker'))
        mi = monthly_implied(rec, px, rates)
        cache[rec['cik']] = (px, mi)
        bym = {m: d for m, _, d, _ in mi}
        for t in issues_of(rec):
            if t.get('currency') != 'USD' or t.get('floating') or t.get('convertible') or t.get('spread_bps') is None:
                continue
            mat = t.get('maturity') or (f"{t['maturity_year']}-06-30" if t.get('maturity_year') else None)
            if not mat or not t.get('date'):
                continue
            yrs = (dt.date.fromisoformat(mat) - dt.date.fromisoformat(t['date'][:10])).days / 365.25
            if not (1 <= yrs <= 40) or not (5 <= t['spread_bps'] <= 1500):
                continue
            ms = bym.get(t['date'][:7])
            if ms is not None:
                pairs.append((ms, t['spread_bps'], yrs))
    fit = DM.fit_calibration(pairs)
    write_json(pub / 'calibration.json', {'generated_at': now(), 'pairs': len(pairs), 'fit': fit,
                                          'note': 'log(issue spread to Treasuries) = a + b·(Merton distance to default, capped at 15) + c·log(years to maturity), '
                                                  'fitted on USD fixed-rate bonds priced in term sheets (spread at issue) and the issuer\'s model spread that month.'})
    if verbose:
        print('calibration:', len(pairs), 'pairs', fit, flush=True)
    index, banks, hidden_index = [], [], []
    for rec in recs:
        px, mi = cache.get(rec['cik'], (None, []))
        snap = rec.get('snapshot') or {}
        inst, inst_form, inst_date = instruments_of(rec)
        ags = agreements_of(rec)
        price = px[-1][1] if px else None
        price_date = px[-1][0].isoformat() if px else None
        sig = vol_at(px, len(px) - 1) if px else None
        A = DM.analyse(snap, inst, ags, price=price, sigma_E=sig, r1=r1, r5=r5, fit=fit, oas_now=oas_now, sofr=sofr)
        if str(rec.get('sic')) in BANK_SIC:
            # a bank's borrowing is mostly deposits: the industrial ratios and the stock-implied spread do not apply
            A['bank'] = True
            for k in ('cushion_score', 'altman_z', 'liquidity_to_due12', 'liquidity_to_due24', 'implied', 'if_converted'):
                A.pop(k, None)
        iss = issues_of(rec)
        bank = bank_summary(rec.get('fdic'))
        hist = []
        for h in rec.get('history') or []:
            ebitda = None if h.get('operating_income') is None else h['operating_income'] + (h.get('da') or 0)
            ie = abs(h['interest_expense']) if h.get('interest_expense') else None
            hist.append([h['end'], h.get('total_debt'), (h.get('cash') or 0) + (h.get('investments') or 0) if h.get('cash') is not None else None,
                         ie, ebitda, h.get('operating_income'), round(ie / h['total_debt'], 5) if ie and h.get('total_debt') else None])
        if mi and fit:
            mi = [row + [round(DM.calibrated(row[2], fit), 1)] for row in mi]
        doc = {'cik': rec['cik'], 'ticker': rec.get('ticker'), 'name': rec.get('name'), 'sector': rec.get('sector'), 'industry': rec.get('industry'),
               'sic': rec.get('sic'), 'sic_description': rec.get('sic_description'), 'generated_at': now(), 'fetched_at': rec.get('fetched_at'),
               'price': price, 'price_date': price_date, 'equity_vol': sig,
               'snapshot': snap, 'sources': rec.get('sources') or {}, 'analysis': A,
               'hidden_leverage': rec.get('hidden_leverage') or {},
               'instruments': inst[:60], 'instruments_from': {'form': inst_form, 'date': inst_date},
               'issues': iss[:400], 'agreements': ags[:6], 'events': rec.get('events') or [],
               'history_fields': ['end', 'total_debt', 'cash_and_investments', 'interest_ttm', 'ebitda_ttm', 'ebit_ttm', 'effective_rate'],
               'history': hist,
               'implied_fields': ['month', 'model_5y_bps', 'distance_to_default', 'equity_vol'] + (['calibrated_5y_bps'] if fit else []),
               'implied_history': mi, 'bank': bank,
               'market': {'treasury_1y': r1, 'treasury_5y': r5, 'sofr': sofr}}
        if bank and rates.get('DFF'):
            by = {}
            for dd_, v in rates['DFF']:
                if dd_.year >= 2010:
                    by.setdefault(dd_.strftime('%Y-%m'), []).append(v)
            doc['market_series'] = {'fedfunds': [[m, round(sum(v) / len(v), 3)] for m, v in sorted(by.items())]}
        write_json(pub / 'c' / f'{rec["cik"]}.json', _clean(doc))
        hs = HL.summarize(rec.get('hidden_leverage') or {})
        hidden_index.append({'cik': rec['cik'], 'ticker': rec.get('ticker'),
                             'name': rec.get('name'), 'sector': rec.get('sector'),
                             'recognized_debt': A.get('total_debt'),
                             'net_debt': A.get('net_debt'), **hs})
        imp = A.get('implied') or {}
        conv = A.get('convertibles') or {}
        covs = [c['cushion'] for c in A.get('covenants') or [] if c.get('cushion') is not None]
        last_fixed = next((t for t in iss if t.get('spread_bps') is not None and not t.get('convertible')), None)
        index.append([rec['cik'], rec.get('ticker'), rec.get('name'), rec.get('sector'), _r(A.get('total_debt')), _r(A.get('net_debt')),
                      _r(A.get('leverage'), 2), _r(A.get('net_leverage'), 2), _r(A.get('interest_coverage'), 2), _r(A.get('liquidity_to_due12'), 2),
                      _r(imp.get('calibrated_5y_bps') or imp.get('spread_5y_bps'), 1), _r(imp.get('dd'), 2), imp.get('rating_band'),
                      _r(A.get('effective_rate'), 4), _r(A.get('floating_share'), 3), _r(conv.get('total_face')), _r(conv.get('in_the_money_face')),
                      _r(min(covs), 3) if covs else None, len(iss), last_fixed.get('date') if last_fixed else None,
                      last_fixed.get('spread_bps') if last_fixed else None, A.get('cushion_score'),
                      _r(bank['latest'].get('deposit_cost'), 4) if bank else None, _r(bank.get('cd_share'), 3) if bank else None,
                      snap.get('balance_date')])
        if bank:
            L = bank['latest']
            banks.append([rec['cik'], rec.get('ticker'), rec.get('name'), bank['bank'], L.get('date'), _r(L.get('deposits')), _r(bank.get('cd_share'), 3),
                          _r(L.get('time_over_250k')), _r(bank.get('uninsured_share'), 3), _r(L.get('brokered')), _r(L.get('deposit_cost'), 4),
                          _r(L.get('cost_of_funds'), 4), _r(L.get('nim'), 4)])
    write_json(pub / 'index.json', {'generated_at': now(), 'fields': ['cik', 'ticker', 'name', 'sector', 'total_debt', 'net_debt', 'leverage', 'net_leverage',
                                                                  'interest_coverage', 'liquidity_to_due12', 'implied_cds_5y_bps', 'distance_to_default',
                                                                  'rating_band', 'effective_rate', 'floating_share', 'convertible_face', 'convertible_itm_face',
                                                                  'min_covenant_cushion', 'issues', 'last_issue_date', 'last_issue_spread_bps', 'cushion_score',
                                                                  'deposit_cost', 'cd_share', 'balance_date'],
                                    'rows': index, 'calibration': fit, 'market': {'treasury_1y': r1, 'treasury_5y': r5, 'sofr': sofr, 'oas': oas_now}})
    write_json(pub / 'hidden' / 'index.json', {
        'generated_at': now(), 'scope': 'SEC companyfacts + source-linked filing text',
        'note': 'Amounts are independent classifications, not additive; missing is not zero.',
        'rows': hidden_index})
    write_json(pub / 'banks.json', {'generated_at': now(), 'fields': ['cik', 'ticker', 'name', 'bank', 'date', 'deposits', 'cd_share', 'time_over_250k',
                                                                  'uninsured_share', 'brokered', 'deposit_cost', 'cost_of_funds', 'nim'], 'rows': banks})
    write_json(pub / 'rates.json', rates_doc(root, rates))
    st = read_json(root / 'state.json', {})
    write_json(pub / 'status.json', {'built_at': now(), 'companies': len(index), 'banks': len(banks), 'calibration_pairs': len(pairs),
                                     'collector': st.get('summary')})
    if verbose:
        print(f'debt build: {len(index)} companies, {len(banks)} banks', flush=True)
    return {'companies': len(index), 'banks': len(banks), 'pairs': len(pairs)}


def rates_doc(root, rates):
    """Monthly averages since 2010 for every series, the last year daily for the curve, and FDIC national rates."""
    out = {'generated_at': now(), 'series': {}, 'labels': RATE_SERIES}
    for sid, obs in rates.items():
        by = {}
        for d, v in obs:
            if d.year >= 2010:
                by.setdefault(d.strftime('%Y-%m'), []).append(v)
        out['series'][sid] = {'monthly': [[m, round(sum(v) / len(v), 4)] for m, v in sorted(by.items())],
                              'last': [str(obs[-1][0]), obs[-1][1]] if obs else None}
    curve = ['DGS1MO', 'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30']
    out['curve_tenors'] = [1 / 12, .25, .5, 1, 2, 3, 5, 7, 10, 20, 30]
    out['curve_now'] = [rates[s][-1][1] if rates.get(s) else None for s in curve]
    yago = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    out['curve_year_ago'] = [rate_at(rates.get(s), yago) * 100 if rates.get(s) and rate_at(rates.get(s), yago) is not None else None for s in curve]
    nat = read_json(Path(root) / 'cache' / 'fdic_national_rates.json', {'months': {}})
    out['fdic_national'] = dict(sorted(nat.get('months', {}).items()))
    return out


def _r(v, d=0):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(v, d) if d else round(v)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 6)
    if isinstance(o, set):
        return sorted(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'rates', 'banks', 'build'])
    ap.add_argument('--root', default='debt')
    ap.add_argument('--site-index', default=None)
    ap.add_argument('--minutes', type=float, default=30)
    ap.add_argument('--tickers', default='')
    ap.add_argument('--prices', default=None, help='public/ of the rotation-history branch (weekly closes in t/)')
    a = ap.parse_args()
    if a.cmd == 'collect':
        cos = universe(a.site_index)
        print(json.dumps(collect(_client(), a.root, cos, a.minutes, first=[t for t in re.split(r'[\s,;]+', a.tickers) if t])), flush=True)
    elif a.cmd == 'rates':
        print(json.dumps(fetch_rates(_client(), a.root)), flush=True)
    elif a.cmd == 'banks':
        print(json.dumps(collect_banks(_client(), a.root, a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.prices)), flush=True)


if __name__ == '__main__':
    main()
