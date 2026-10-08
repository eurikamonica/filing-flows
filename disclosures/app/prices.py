"""Optional price-based cost estimates (4.1).

13F reports quantities and quarter-end values, never what a manager paid. Congressional / state disclosures report
dollar ranges, never share counts. With daily closes from a public price source we can add clearly-labelled estimates:
- 13F: quantity change × average daily close of the report quarter ("smoothed" cost of the change)
- reviewed transactions: close on (or just before) the transaction date → implied share range for the disclosed amount

Identifiers: 13F rows carry CUSIPs; OpenFIGI maps them to tickers. Prices: Stooq daily CSV (no key).
Everything is cached under docs/data/cache/prices/ (collector-only; not part of the public site).
"""
import csv
import datetime as dt
import gzip
import io
import json
import re
from pathlib import Path
from core import now, read_json, write_json

OPENFIGI = 'https://api.openfigi.com/v3/mapping'
STOOQ = 'https://stooq.com/q/d/l/?s={symbol}&i=d'


def stooq_symbol(ticker):
    t = ticker.strip().upper().replace('/', '-').replace('.', '-')
    if not re.fullmatch(r'[A-Z0-9-]{1,10}', t):
        raise ValueError('Unsupported ticker for price lookup: ' + ticker)
    return t.lower() + '.us'


def parse_stooq(text, since):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        day, close = (r.get('Date') or '').strip(), (r.get('Close') or '').strip()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or day < since:
            continue
        try:
            rows.append([day, float(close)])
        except ValueError:
            continue
    if not rows:
        raise ValueError('No daily rows in the price response')
    return sorted(rows)


def quarter_window(period):
    end = dt.date.fromisoformat(period)
    start = dt.date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
    return start.isoformat(), end.isoformat()


def quarter_average(rows, period):
    start, end = quarter_window(period)
    inside = [c for d, c in rows if start <= d <= end]
    before = [(d, c) for d, c in rows if d <= end]
    close = before[-1][1] if before and before[-1][0] >= start else None
    return (sum(inside) / len(inside) if inside else None), close, len(inside)


def close_on(rows, day, max_gap_days=7):
    before = [(d, c) for d, c in rows if d <= day]
    if not before:
        return None, None
    d, c = before[-1]
    if (dt.date.fromisoformat(day) - dt.date.fromisoformat(d)).days > max_gap_days:
        return None, None
    return c, d


class PriceStore:
    def __init__(self, client, cfg, root):
        self.client, self.cfg = client, cfg
        self.dir = Path(root) / 'cache' / 'prices'
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cusips = read_json(self.dir / 'cusips.json', {})
        self.since = cfg.get('history_since', '2023-01-01')
        self.refresh_hours = float(cfg.get('refresh_hours', 24))
        self.fetched_tickers = 0
        self.mapped_cusips = 0
        self.errors = []

    # -- CUSIP → ticker (OpenFIGI, batches of 10 jobs without an API key)
    def map_cusips(self, cusips):
        todo = [c for c in dict.fromkeys(cusips) if re.fullmatch(r'[0-9A-Z]{9}', c or '') and c not in self.cusips]
        budget = int(self.cfg.get('cusip_batch', 200))
        todo = todo[:budget]
        size = 100 if self.client.options.get('openfigi_key') else 10
        for i in range(0, len(todo), size):
            jobs = todo[i:i + size]
            try:
                answer = self.client.post_json(OPENFIGI, [{'idType': 'ID_CUSIP', 'idValue': c} for c in jobs])
            except Exception as exc:
                self.errors.append(f'OpenFIGI batch: {exc}')
                break
            if not isinstance(answer, list) or len(answer) != len(jobs):
                self.errors.append('OpenFIGI: unexpected response shape')
                break
            for cusip, item in zip(jobs, answer):
                rows = item.get('data') or []
                pick = next((r for r in rows if r.get('exchCode') == 'US'), rows[0] if rows else None)
                self.cusips[cusip] = {'ticker': (pick or {}).get('ticker'), 'name': (pick or {}).get('name'),
                                      'security_type': (pick or {}).get('securityType'), 'checked_at': now(),
                                      'error': item.get('error') if not rows else None}
                self.mapped_cusips += 1
        write_json(self.dir / 'cusips.json', self.cusips)

    def ticker_for(self, cusip):
        return (self.cusips.get(cusip) or {}).get('ticker')

    # -- daily closes per ticker
    def history(self, ticker, budget):
        path = self.dir / (re.sub(r'[^A-Za-z0-9-]', '_', ticker.upper()) + '.json.gz')
        cached = None
        if path.exists():
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                cached = json.load(f)
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cached['fetched_at'])).total_seconds() / 3600
            if age < self.refresh_hours or self.fetched_tickers >= budget:
                return cached['rows']
        if self.fetched_tickers >= budget:
            return None
        try:
            text = self.client.get(STOOQ.format(symbol=stooq_symbol(ticker))).decode('utf-8', 'replace')
            rows = parse_stooq(text, self.since)
        except Exception as exc:
            self.errors.append(f'{ticker}: {exc}')
            self.fetched_tickers += 1
            return cached['rows'] if cached else None
        self.fetched_tickers += 1
        with gzip.open(path.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
            json.dump({'ticker': ticker, 'source': 'stooq', 'fetched_at': now(), 'rows': rows}, f, separators=(',', ':'))
        path.with_suffix('.tmp').replace(path)
        return rows


def apply_prices(data, client, cfg, root):
    """Annotate 13F positions and reviewed transactions in place; returns the prices module status."""
    from shards import load_manager
    store = PriceStore(client, cfg, root)
    budget = int(cfg.get('ticker_batch', 60))
    holdings = data.get('modules', {}).get('holdings', {})
    managers = holdings.get('managers', [])
    positions_priced = positions_total = 0
    # 1) collect CUSIPs across managers (loading cached managers as needed)
    loaded = []
    for i, row in enumerate(managers):
        if 'snapshots' not in row and row.get('cache'):
            try:
                row = load_manager(root, row)
            except Exception as exc:
                store.errors.append(f"manager {row.get('cik')}: {exc}")
                continue
        if 'snapshots' not in row:
            continue
        managers[i] = row
        loaded.append(row)
    cusips = [p['cusip'] for m in loaded for s in m.get('snapshots', []) for p in s.get('positions', []) if p.get('put_call') == 'NONE' and p.get('share_type') == 'SH']
    store.map_cusips(cusips)
    # 2) prices per position
    histories = {}
    for m in loaded:
        for s in m.get('snapshots', []):
            for p in s.get('positions', []):
                positions_total += 1
                ticker = store.ticker_for(p.get('cusip', '')) if p.get('put_call') == 'NONE' and p.get('share_type') == 'SH' else None
                for k in ('ticker', 'price_avg_q', 'price_close_q', 'price_days'):
                    p.pop(k, None)
                if not ticker:
                    continue
                if ticker not in histories:
                    histories[ticker] = store.history(ticker, budget)
                rows = histories[ticker]
                if not rows:
                    continue
                avg, close, days = quarter_average(rows, s['period'])
                if avg is None:
                    continue
                p.update(ticker=ticker, price_avg_q=round(avg, 4), price_close_q=close, price_days=days)
                positions_priced += 1
    # 3) reviewed transactions with an explicit ticker and date
    records = data.get('modules', {}).get('congress', {}).get('records', [])
    records_priced = 0
    for r in records:
        for k in ('price_on_date', 'price_date', 'est_shares_min', 'est_shares_max'):
            r.pop(k, None)
        ticker, day = (r.get('ticker') or '').strip(), r.get('transaction_date') or r.get('valuation_date') or ''
        if not ticker or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            continue
        if ticker not in histories:
            try:
                histories[ticker] = store.history(ticker, budget)
            except Exception as exc:
                store.errors.append(f'{ticker}: {exc}'); histories[ticker] = None
        rows = histories[ticker]
        if not rows:
            continue
        close, on = close_on(rows, day)
        if close is None or close <= 0:
            continue
        r.update(price_on_date=close, price_date=on,
                 est_shares_min=round(r['amount_min'] / close, 2) if r.get('amount_min') is not None else None,
                 est_shares_max=round(r['amount_max'] / close, 2) if r.get('amount_max') is not None else None)
        records_priced += 1
    unmapped = sum(1 for c in set(cusips) if store.cusips.get(c) and not store.cusips[c].get('ticker'))
    return {'status': 'partial' if store.errors else 'ok', 'errors': store.errors[:50], 'last_attempt': now(), 'updated_at': now(), 'error': None,
            'counts': {'cusips_seen': len(set(cusips)), 'cusips_mapped': sum(1 for c in set(cusips) if store.ticker_for(c)), 'cusips_unmapped': unmapped,
                       'cusips_pending': sum(1 for c in set(cusips) if c not in store.cusips), 'tickers_fetched_this_run': store.fetched_tickers,
                       'positions_priced': positions_priced, 'positions_total': positions_total, 'records_priced': records_priced},
            'coverage_note': 'Estimates only. 13F: quantity change × average daily close of the report quarter; transactions: close on or just before the disclosed date (up to 7 days back). Source: Stooq daily closes; CUSIP→ticker via OpenFIGI. Options, non-share quantities and unmapped securities have no estimate. Actual execution prices are not disclosed.',
            'source': 'stooq + openfigi', 'history_since': store.since}
