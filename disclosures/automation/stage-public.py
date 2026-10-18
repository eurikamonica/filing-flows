"""Copy the Disclosure Hub's static site into the Filing Flows Pages build, plus the per-ticker holders index.

    python disclosures/automation/stage-public.py --out _site/disclosures

Collector-only files (cache/, discovery-state.json, npx-queue-state.json) stay in the repository
for incremental collection but are left out of the public site, exactly as the stand-alone
update-and-deploy workflow does.

holders/{TICKER}.json joins the hub's data by ticker so a company page on the Sankey site can show who holds it:
- institutional: the latest 13F snapshot of every processed manager that lists the ticker's CUSIP
  (CUSIP → ticker from the price module's OpenFIGI cache)
- officials: reviewed records (assets / transactions) whose verified ticker matches, US House PTRs read by machine and
  US Senate electronic PTRs
- insiders (Form 4), stakes (Schedules 13D / 13G), form144 (notices of proposed sales), short (FINRA short interest,
  a year of settlement dates), events8k (the latest 8-Ks, classified) and news (press releases, FDA, SEC actions)
"""
import argparse
import gzip
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
DOCS = ROOT / 'docs'
DATA = DOCS / 'data'


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def clean_ticker(t):
    t = (t or '').strip().upper().replace('/', '-').replace('.', '-').rstrip('*')
    return t if re.fullmatch(r'[A-Z0-9-]{1,10}', t) else ''


def holders_index():
    cusips = load_json(DATA / 'cache' / 'prices' / 'cusips.json', {})
    by_cusip = {c: clean_ticker(v.get('ticker')) for c, v in cusips.items() if v.get('ticker')}
    live = load_json(DATA / 'live.json', {})
    out = {}
    generated = live.get('generated_at')
    # 13F: latest complete snapshot per processed manager
    for row in (live.get('modules', {}).get('holdings', {}) or {}).get('managers', []):
        cache = row.get('cache')
        if not cache or not re.fullmatch(r'cache/holdings/\d+\.json\.gz', cache):
            continue
        try:
            with gzip.open(DATA / cache, 'rt', encoding='utf-8') as f:
                m = json.load(f)
        except Exception:
            continue
        snaps = [s for s in m.get('snapshots', []) if s.get('complete')] or m.get('snapshots', [])
        if not snaps:
            continue
        s = snaps[-1]
        changes = {c['id']: c for c in s.get('changes', [])}
        for p in s.get('positions', []):
            if p.get('put_call') != 'NONE' or p.get('share_type') != 'SH':
                continue
            ticker = clean_ticker(p.get('ticker')) or by_cusip.get(p.get('cusip', ''))
            if not ticker:
                continue
            ch = changes.get(p['id'], {})
            out.setdefault(ticker, {'ticker': ticker, 'generated_at': generated, 'institutional': [], 'officials': []})['institutional'].append({
                'manager': m.get('label') or m.get('name'), 'cik': m.get('cik'), 'period': s.get('period'), 'filed': s.get('filed'),
                'issuer': p.get('issuer'), 'cusip': p.get('cusip'), 'shares': p.get('shares'), 'value_usd': p.get('value_usd'),
                'weight': p.get('weight'), 'status': ch.get('status', 'BASE'), 'delta_shares': ch.get('delta_shares'),
                'price_avg_q': p.get('price_avg_q'), 'source_url': (s.get('sources') or [{}])[-1].get('url')})
    # officials: reviewed, source-checked rows only
    for r in (live.get('modules', {}).get('congress', {}) or {}).get('records', []):
        ticker = clean_ticker(r.get('ticker'))
        if not ticker:
            continue
        out.setdefault(ticker, {'ticker': ticker, 'generated_at': generated, 'institutional': [], 'officials': []})['officials'].append({
            'person': r.get('person'), 'jurisdiction': r.get('jurisdiction'), 'kind': r.get('kind'), 'asset': r.get('asset'),
            'owner': r.get('owner'), 'amount_min': r.get('amount_min'), 'amount_max': r.get('amount_max'),
            'date': r.get('transaction_date') or r.get('valuation_date') or r.get('filed_date'), 'transaction_type': r.get('transaction_type'),
            'report_type': r.get('report_type'), 'filed_date': r.get('filed_date'), 'source_url': r.get('source_url'), 'page': r.get('page'),
            'price_on_date': r.get('price_on_date'), 'est_shares_min': r.get('est_shares_min'), 'est_shares_max': r.get('est_shares_max')})
    # officials: US House transaction reports read by machine (the filer's own ticker, checked against SEC listings)
    trades = load_json(DATA / 'market' / 'officials-trades.json', {}).get('trades', [])
    per = {}
    for tr in trades:
        ticker = clean_ticker(tr.get('ticker_canon') or tr.get('ticker'))
        if not ticker or tr.get('read') not in ('machine', 'electronic') or tr.get('ticker_status') != 'listed' or per.get(ticker, 0) >= 40:
            continue
        per[ticker] = per.get(ticker, 0) + 1
        out.setdefault(ticker, {'ticker': ticker, 'generated_at': generated, 'institutional': [], 'officials': []})['officials'].append({
            'person': tr.get('person'), 'jurisdiction': tr.get('jurisdiction'), 'kind': 'transaction', 'asset': tr.get('asset_raw'),
            'owner': tr.get('owner'), 'amount_min': tr.get('amount_min'), 'amount_max': tr.get('amount_max'), 'date': tr.get('date'),
            'transaction_type': tr.get('type'), 'report_type': 'PTR', 'filed_date': tr.get('filed_date'), 'source_url': tr.get('source_url'),
            'page': tr.get('page'), 'read': tr.get('read'), 'name_check': tr.get('name_check')})
    # insiders: Form 4 purchases and larger sales of the last 120 days
    ipath = DATA / 'cache' / 'insiders' / 'trades.json.gz'
    if ipath.exists():
        try:
            with gzip.open(ipath, 'rt', encoding='utf-8') as f:
                itrades = json.load(f)
        except Exception:
            itrades = []
        count = {}
        for tr in itrades:
            ticker = clean_ticker(tr.get('ticker'))
            if not ticker or count.get(ticker, 0) >= 25 or not (tr['code'] == 'P' or (tr.get('value') or 0) >= 100_000):
                continue
            count[ticker] = count.get(ticker, 0) + 1
            out.setdefault(ticker, {'ticker': ticker, 'generated_at': generated, 'institutional': [], 'officials': []}).setdefault('insiders', []).append(
                {k: tr.get(k) for k in ('insider', 'role', 'title', 'code', 'date', 'shares', 'price', 'value', 'after', 'plan_10b5_1', 'url')})
    base = lambda t: out.setdefault(t, {'ticker': t, 'generated_at': generated, 'institutional': [], 'officials': []})
    # Schedules 13D / 13G (largest holders, activists) and Form 144 notices, from the ownership cache (app/ownership.py)
    try:
        import ownership as OWN
        tick = OWN.cik_tickers(DATA)
        count = {}
        for r in OWN.with_changes(OWN._load(DATA / 'cache' / 'ownership', 'stakes'), tick):
            t = clean_ticker(r.get('ticker'))
            if not t or count.get(t, 0) >= 25:
                continue
            count[t] = count.get(t, 0) + 1
            r['label'] = OWN.stake_label(r)
            base(t).setdefault('stakes', []).append({k: (OWN._clip(r[k], 280) if k == 'purpose' else r.get(k)) for k in (
                'form', 'filed', 'event_date', 'filer', 'holder', 'person', 'persons', 'percent', 'shares', 'change', 'prev_percent', 'label',
                'rule', 'purpose', 'url') if r.get(k) not in (None, '')})
        count = {}
        for r in OWN._load(DATA / 'cache' / 'ownership', 'form144'):
            t = clean_ticker(tick.get(r.get('issuer_cik') or '', ''))
            if not t or count.get(t, 0) >= 25 or (r.get('value') or 0) < 25_000:
                continue
            count[t] = count.get(t, 0) + 1
            base(t).setdefault('form144', []).append({k: r.get(k) for k in (
                'filed', 'seller', 'seller_name', 'relationship', 'shares', 'value', 'sale_date', 'acquired', 'plan_date', 'url') if r.get(k) not in (None, '')})
    except Exception as exc:
        print(f'::warning::holders index: 13D / 13G / Form 144 left out ({exc})')
    # 8-K events (the latest 15 per company, 120 days) and news (press releases, FDA, SEC actions naming it)
    try:
        import events8k as EV
        for t, rows in EV.by_ticker(DATA).items():
            t = clean_ticker(t)
            if t:
                base(t)['events8k'] = rows
    except Exception as exc:
        print(f'::warning::holders index: 8-K events left out ({exc})')
    try:
        import news as NW
        for t, rows in NW.by_ticker(DATA).items():
            t = clean_ticker(t)
            if t:
                base(t)['news'] = rows
    except Exception as exc:
        print(f'::warning::holders index: news left out ({exc})')
    # FINRA short interest: each ticker's settlement dates (a year), for stocks already indexed or with a real position
    try:
        import shorts as SH
        for t, h in SH.history_by_ticker(DATA, 24).items():
            t = clean_ticker(t)
            if t and (t in out or (h[-1][1] or 0) >= 250_000):
                base(t)['short'] = h
    except Exception as exc:
        print(f'::warning::holders index: short interest left out ({exc})')
    # this quarter's 13F flow and the signal flags, for the company page's summary line
    flows = load_json(DATA / 'market' / 'by-ticker.json', {})
    sig = {r['ticker']: r for r in load_json(DATA / 'market' / 'signals.json', {}).get('rows', [])}
    for ticker, v in out.items():
        f = (flows.get('rows') or {}).get(ticker)
        if f:
            v['flows'] = dict(zip(flows.get('fields', []), f), label=flows.get('label'))
        if ticker in sig:
            v['signal'] = {k: sig[ticker].get(k) for k in ('tags', 'heat', 'pressure')}
    for v in out.values():
        v['institutional'].sort(key=lambda x: -(x.get('value_usd') or 0))
        v['officials'].sort(key=lambda x: (x.get('date') or ''), reverse=True)
        v['counts'] = {'institutional': len(v['institutional']), 'officials': len(v['officials']), 'insiders': len(v.get('insiders', [])),
                       'stakes': len(v.get('stakes', [])), 'form144': len(v.get('form144', [])), 'short': len(v.get('short', [])),
                       'events8k': len(v.get('events8k', [])), 'news': len(v.get('news', []))}
    return out


def join_earnings(out, site_data):
    """Signals + the Sankey site's latest quarter per ticker (revenue, growth, margin, link), with two more flags."""
    path = Path(out) / 'data' / 'market' / 'signals.json'
    sig, ix = load_json(path, None), load_json(Path(site_data) / 'index.json', None)
    if not sig or not ix:
        return 0
    by = {}
    for e in ix.get('companies', []) if isinstance(ix, dict) else ix:
        t = clean_ticker(e.get('ticker'))
        if t and (t not in by or (e.get('filed') or '') > (by[t].get('filed') or '')):
            by[t] = e
    n = 0
    for r in sig.get('rows', []):
        e = by.get(clean_ticker(r.get('ticker')))
        if not e:
            continue
        r['earn'] = {'cik': e.get('cik'), 'label': e.get('label'), 'rev': e.get('rev'), 'yoy': e.get('yoy'), 'om': e.get('om'),
                     'filed': e.get('filed'), 'form': e.get('form')}
        yoy, om = e.get('yoy'), e.get('om')
        if isinstance(yoy, (int, float)) and yoy >= 25 and 'revenue_surge' not in r['tags']:
            r['tags'].append('revenue_surge'); r['heat'] += 1
        if isinstance(yoy, (int, float)) and isinstance(om, (int, float)) and yoy >= 15 and om >= 15 and 'profitable_growth' not in r['tags']:
            r['tags'].append('profitable_growth')
        n += 1
    sig['rows'].sort(key=lambda r: (-r['heat'], -((r.get('f13') or {}).get('usd_net') or 0)))
    path.write_text(json.dumps(sig, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_site/disclosures')
    ap.add_argument('--site-data', default=None, help="the Sankey site's data folder (index.json), to join earnings into signals")
    ap.add_argument('--history', default=None, help="public/ of the branch rotation-history (the RRG and the long rotation)")
    ap.add_argument('--debt', default=None, help="public/ of the branch debt-history (Debt & rates: app/debt.py)")
    ap.add_argument('--consensus', default=None, help="public/ of the branch consensus-history (Consensus: app/consensus.py)")
    args = ap.parse_args()
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(DOCS, out, ignore=shutil.ignore_patterns('cache', 'discovery-state.json', 'npx-queue-state.json', 'meta.json'))
    if args.history and (Path(args.history) / 'rrg.json').exists():
        shutil.copytree(args.history, out / 'data' / 'market' / 'history', dirs_exist_ok=True)
        st = {}
        try:
            st = json.loads((Path(args.history) / 'status.json').read_text(encoding='utf-8'))
        except Exception:
            pass
        print(f"::notice::rotation history: {st.get('tickers_published')} tickers, built {st.get('built_at')}, "
              f"long momentum clock {st.get('long_quarters')}")
    if args.debt and (Path(args.debt) / 'index.json').exists():
        shutil.copytree(args.debt, out / 'data' / 'debt', dirs_exist_ok=True)
        try:
            st = json.loads((Path(args.debt) / 'status.json').read_text(encoding='utf-8'))
            print(f"::notice::debt & rates: {st.get('companies')} companies, {st.get('banks')} banks, built {st.get('built_at')}")
        except Exception:
            pass
    if args.consensus and (Path(args.consensus) / 'index.json').exists():
        shutil.copytree(args.consensus, out / 'data' / 'consensus', dirs_exist_ok=True)
        try:
            st = json.loads((Path(args.consensus) / 'status.json').read_text(encoding='utf-8'))
            print(f"::notice::consensus: {st.get('companies')} companies, {st.get('markets')} prediction markets, built {st.get('built_at')}")
        except Exception:
            pass
    if args.site_data:
        print(f'signals joined with earnings for {join_earnings(out, args.site_data)} tickers')
        try:
            import sys
            sys.path.insert(0, str(ROOT / 'app'))
            import rotation
            rot = rotation.build(args.site_data, DATA)
            mon = rot.pop('monthly', None)
            if mon:
                (out / 'data' / 'market' / 'rotation-monthly.json').write_text(json.dumps(mon, separators=(',', ':')), encoding='utf-8')
            (out / 'data' / 'market' / 'rotation.json').write_text(json.dumps(rot, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            print(f"::notice::rotation: {len(rot['companies'])} companies, {len(rot['sectors'])} sectors, "
                  f"quarters {rot.get('quarters', [''])[0] if rot.get('quarters') else '-'}…{rot['quarters'][-1] if rot.get('quarters') else '-'}")
        except Exception as exc:
            print(f'::warning::rotation not built: {exc}')
    # which snapshot this build publishes (U07): the commit, when it was built, when each data set was last made
    import datetime as _dt, os as _os
    def _stamp(path, key):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8')).get(key)
        except Exception:
            return None
    build = {'published_at': _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds'), 'commit': (_os.environ.get('GITHUB_SHA') or '')[:12],
             'collected_at': _stamp(DATA / 'live.json', 'generated_at'), 'market_built_at': _stamp(DATA / 'market' / 'meta.json', 'built_at'),
             'options_at': _stamp(DATA / 'market' / 'options.json', 'generated_at')}
    (out / 'data' / 'build.json').write_text(json.dumps(build), encoding='utf-8')
    print(f"::notice::disclosures snapshot: collected {build['collected_at']}, market views {build['market_built_at']}, commit {build['commit']}")
    holders = holders_index()
    hdir = out / 'data' / 'holders'
    hdir.mkdir(parents=True, exist_ok=True)
    for ticker, payload in holders.items():
        (hdir / f'{ticker}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (hdir / 'index.json').write_text(json.dumps({'tickers': sorted(holders), 'generated_at': next(iter(holders.values()), {}).get('generated_at')}), encoding='utf-8')
    n = sum(1 for p in out.rglob('*') if p.is_file())
    print(f'disclosure hub staged to {out} ({n} files, holders for {len(holders)} tickers)')


if __name__ == '__main__':
    main()
