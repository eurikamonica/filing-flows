"""Copy the Disclosure Hub's static site into the Filing Flows Pages build, plus the per-ticker holders index.

    python disclosures/automation/stage-public.py --out _site/disclosures

Collector-only files (cache/, discovery-state.json, npx-queue-state.json) stay in the repository
for incremental collection but are left out of the public site, exactly as the stand-alone
update-and-deploy workflow does.

holders/{TICKER}.json joins the hub's data by ticker so a company page on the Sankey site can show who holds it:
- institutional: the latest 13F snapshot of every processed manager that lists the ticker's CUSIP
  (CUSIP → ticker from the price module's OpenFIGI cache)
- officials: reviewed records (assets / transactions) whose verified ticker matches
"""
import argparse
import gzip
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    for v in out.values():
        v['institutional'].sort(key=lambda x: -(x.get('value_usd') or 0))
        v['officials'].sort(key=lambda x: (x.get('date') or ''), reverse=True)
        v['counts'] = {'institutional': len(v['institutional']), 'officials': len(v['officials'])}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_site/disclosures')
    args = ap.parse_args()
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(DOCS, out, ignore=shutil.ignore_patterns('cache', 'discovery-state.json', 'npx-queue-state.json'))
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
