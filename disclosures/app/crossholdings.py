"""Cross-holdings (4.19): who holds whom — the holders whose stakes are public, and the companies that are both held and
holders themselves.

Holders
  gov        the US government's equity stakes since 2025 (config/government-stakes.json: each row cites the company's SEC
             filing or the agency's release); value = shares × the latest close where a share count is disclosed, else
             the amount invested
  president  the President's OGE 278-T trades (app/president.py, read by OCR): purchases − sales at range midpoints
  officials  members of Congress (House and Senate periodic transaction reports): net buying over the last months at
             range midpoints, per member and all together
  ta         Trump Accounts (the children's accounts; Treasury's lineup of 2026-07-01): every contribution goes to the
             default fund, SPYM, which holds the S&P 500 — shown as dollars per $1,000 in an account
  corp       listed operating companies that file 13F (Alphabet, Nvidia, Amazon, Berkshire, SoftBank …): their own
             stakes in other listed companies, from their latest 13F
  inst       the largest 13F managers (Vanguard, BlackRock …), shown in each company's holder list, not in the map

Every company that appears is described by who holds it (13F managers in all, the special holders above, % of shares
outstanding where SEC's cover-page count is on file) — so a chain like Trump Accounts → NVIDIA → Intel ← US government
can be read off the map.

  Gather    rides along with market.scan_13f (one pass over the 13F cache): each listed filer's latest portfolio, the
            largest managers' portfolios, and per ticker the holders and dollars in each manager's latest 13F
  build     market/crossholdings.json
"""
import datetime as dt
import gzip
import heapq
import json
import re
from collections import defaultdict
from pathlib import Path

from core import now, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
FRAME = 'https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/{period}.json'
SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
FINANCIAL = range(6000, 6800)          # SIC: finance, insurance, real estate — managers of other people's money
ALWAYS_CORP = {1067983, 1065521}       # Berkshire Hathaway, SoftBank Group: insurers / holding companies investing their own capital
SPYM_FALLBACK = ('https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings'
                 '&dataType=fund')


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gz(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Gather:
    """Collects, while market.scan_13f reads every manager once: listed filers' portfolios, the top managers' portfolios
    and per-ticker holder counts / dollars / shares from each manager's latest complete 13F."""

    def __init__(self, listed_ciks, top=12, cusip_ticker=None):
        self.listed = set(int(c) for c in listed_ciks)
        self.cusip_ticker = cusip_ticker or {}
        self.top = top
        self.filers = {}                       # cik → {name, period, total, positions}
        self.heap = []                         # (total, cik, record) of the largest managers
        self.agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0]))   # period → ticker → [holders, usd, shares]
        self.managers = 0

    def see(self, m):
        try:
            cik = int(m.get('cik'))
        except (TypeError, ValueError):
            return
        snaps = [s for s in m.get('snapshots') or [] if s.get('complete') and s.get('positions')]
        if not snaps:
            return
        s = max(snaps, key=lambda x: x.get('period') or '')
        pos = []
        for p in s['positions']:
            if p.get('put_call') not in (None, 'NONE') or p.get('share_type') not in (None, 'SH'):
                continue
            t = (self.cusip_ticker.get(p.get('cusip')) or p.get('ticker') or '').upper().replace('/', '-').replace('.', '-')
            if not t:
                continue
            pos.append((t, p.get('shares') or 0, p.get('value_usd') or 0, p.get('issuer')))
        if not pos:
            return
        self.managers += 1
        per = self.agg[s.get('period')]
        seen = set()
        for t, sh, usd, _ in pos:
            a = per[t]
            if t not in seen:
                a[0] += 1
                seen.add(t)
            a[1] += usd
            a[2] += sh
        rec = {'cik': cik, 'name': m.get('label') or m.get('name'), 'period': s.get('period'), 'filed': s.get('filed'),
               'total': s.get('total_usd') or sum(p[2] for p in pos), 'positions': pos}
        if cik in self.listed:
            self.filers[cik] = rec
        item = (rec['total'], cik, rec)
        if len(self.heap) < self.top + 25:     # room for the listed financial filers that will be counted as managers
            heapq.heappush(self.heap, item)
        elif item[0] > self.heap[0][0]:
            heapq.heapreplace(self.heap, item)


# ------------------------------------------------------------------ reference data
def listed_ciks(root):
    """{cik: [tickers]} from SEC's company tickers (the hub's weekly cache)."""
    out = defaultdict(list)
    for r in (read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}) or {}).get('rows') or []:
        if r.get('cik') and r.get('ticker'):
            out[int(r['cik'])].append(r['ticker'].upper().replace('.', '-'))
    return out


def sic_codes(root, ciks, client=None, max_new=250):
    """{cik: sic} for the listed 13F filers, from EDGAR's submissions (cached; a code never changes often)."""
    path = Path(root) / 'cache' / 'crossholdings' / 'sic.json'
    cache = read_json(path, {}) or {}
    new = 0
    for c in sorted(ciks):
        if str(c) in cache or client is None or new >= max_new:
            continue
        try:
            d = client.json(SUBMISSIONS.format(cik=int(c)), sec=True)
            cache[str(c)] = {'sic': int(d.get('sic') or 0), 'desc': d.get('sicDescription'), 'name': d.get('name')}
        except Exception as exc:
            cache[str(c)] = {'sic': None, 'error': str(exc)[:80]}
        new += 1
    if new:
        write_json(path, cache)
    return {int(k): v for k, v in cache.items()}


def shares_outstanding(root, client=None, today=None):
    """{cik: shares} — SEC's cover-page share counts (dei frames) for the last two calendar quarters, newest wins."""
    today = today or dt.date.today()
    y, q = today.year, (today.month - 1) // 3
    periods = []
    for _ in range(3):
        if q == 0:
            y, q = y - 1, 4
        periods.append(f'CY{y}Q{q}I')
        q -= 1
    base = Path(root) / 'cache' / 'frames'
    out = {}
    for per in reversed(periods):
        p = base / f'EntityCommonStockSharesOutstanding-{per}.json.gz'
        fresh = p.exists() and (dt.datetime.now().timestamp() - p.stat().st_mtime) < 6 * 86400
        if client is not None and not fresh:
            try:
                body = client.json(FRAME.format(period=per), sec=True)
                vals = {str(r['cik']): r['val'] for r in body.get('data', []) if r.get('val')}
                p.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(p, 'wt', encoding='utf-8') as f:
                    json.dump(vals, f, separators=(',', ':'))
            except Exception:
                pass
        for k, v in (_gz(p, {}) or {}).items():
            out[int(k)] = v
    return out


def last_close(root, ticker):
    rows = _gz(Path(root) / 'cache' / 'prices' / f'{ticker}.json.gz')
    rows = rows.get('rows') if isinstance(rows, dict) else rows
    for r in reversed(rows or []):
        if r and len(r) > 1 and _num(r[1]):
            return float(r[1]), r[0]
    return None, None


def fund_weights(root, cfg, client=None):
    """{ticker: weight (0–1)} of the Trump Accounts' default fund (SPYM, State Street's daily holdings file), refreshed
    daily; iShares IVV's file (the same S&P 500 index) if SPYM's cannot be read."""
    path = Path(root) / 'cache' / 'crossholdings' / 'trump-accounts.json'
    cache = read_json(path, {}) or {}
    age = None
    if cache.get('at'):
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cache['at'])
    if client is not None and (age is None or age > dt.timedelta(hours=20)):
        got = None
        try:
            from etf import parse_uit_holdings
            rows = parse_uit_holdings(client.get(cfg.get('spym_url')))
            w = {}
            for r in rows:
                t, wt = (r[1] or '').upper().replace('.', '-'), _num(r[3] if len(r) > 3 else None)
                if t and wt:
                    w[t] = w.get(t, 0) + wt
            if len(w) >= 400:
                got = {'fund': 'SPYM', 'source': cfg.get('spym_url'), 'weights': w}
        except Exception as exc:
            cache['error'] = f'SPYM: {str(exc)[:120]}'
        if got is None:
            try:
                from consensus import parse_ishares
                rows = parse_ishares(client.get(SPYM_FALLBACK).decode('utf-8', 'replace'))
                if len(rows) >= 400:
                    got = {'fund': 'IVV', 'source': SPYM_FALLBACK, 'weights': {t.upper().replace('.', '-'): w for t, w in rows}}
            except Exception as exc:
                cache['error'] = (cache.get('error') or '') + f' IVV: {str(exc)[:120]}'
        if got:
            tot = sum(got['weights'].values()) or 1
            got['weights'] = {t: round(v / tot, 7) for t, v in got['weights'].items()}
            cache = {**got, 'at': now()}
            write_json(path, cache)
    return cache


# ------------------------------------------------------------------ the holders
def gov_holder(root, cfg_path=None):
    doc = read_json(cfg_path or ROOT / 'config' / 'government-stakes.json', {}) or {}
    edges, private = [], []
    for s in doc.get('stakes') or []:
        row = {k: s.get(k) for k in ('name', 'agency', 'instrument', 'pct', 'status', 'scope', 'announced', 'source', 'how', 'shares',
                                     'warrant_shares', 'cost_usd', 'listed_abroad')}
        if s.get('source') == 'tracker':
            row['source'] = doc.get('tracker')
        if not s.get('ticker'):
            private.append(row)
            continue
        t = s['ticker'].upper()
        px, day = last_close(root, t)
        value, basis = None, None
        if s.get('shares') and px:
            value, basis = s['shares'] * px, 'shares × close'
        elif s.get('cost_usd'):
            value, basis = s['cost_usd'], 'amount invested'
        edges.append({'ticker': t, 'usd': round(value) if value else None, 'basis': basis, 'price': px, 'price_date': day, **row})
    return {'id': 'gov', 'kind': 'gov', 'label': 'US government', 'as_of': doc.get('as_of'), 'note': doc.get('note'),
            'source': doc.get('tracker'), 'edges': edges, 'private': private}


def president_holder(root, top=60):
    d = read_json(Path(root) / 'market' / 'president.json', {}) or {}
    rows = [r for r in d.get('tickers') or [] if r.get('ticker')]
    rows.sort(key=lambda r: -(r.get('buy_mid', 0) + r.get('sell_mid', 0)))
    edges = [{'ticker': r['ticker'], 'usd': r['net_mid'], 'buy_mid': r['buy_mid'], 'sell_mid': r['sell_mid'], 'buys': r['buys'],
              'sells': r['sells'], 'first': r['first'], 'last': r['last']} for r in rows[:top]]
    st = d.get('stats') or {}
    return {'id': 'president', 'kind': 'president', 'label': 'President Trump', 'as_of': (st.get('span') or [None, None])[1],
            'span': st.get('span'), 'trades': st.get('trades'), 'with_ticker': st.get('with_ticker'),
            'filings': [{k: f.get(k) for k in ('name', 'url', 'filed', 'kind', 'pages', 'pages_read', 'rows', 'coverage', 'text_pages', 'ocr_pages')} for f in d.get('filings') or []],
            'note': d.get('note'), 'edges': edges, 'pending': not rows}


def officials_holder(trades, months=12, top_people=12, today=None):
    """Congress all together (net purchases − sales at range midpoints over `months`) and the most active members."""
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=int(months * 30.44))).isoformat()
    by_t, by_p = {}, {}
    for t in trades or []:
        if (t.get('date') or '') < since or t.get('type') not in ('purchase', 'sale', 'sale_partial', 'sale_full') or t.get('ticker_status') not in (None, 'listed'):
            continue
        tk = (t.get('ticker_canon') or t.get('ticker') or '').upper()
        if not tk:
            continue
        lo, hi = t.get('amount_min') or 0, t.get('amount_max') or (t.get('amount_min') or 0) * 2
        mid = (lo + hi) / 2
        sign = 1 if t['type'] == 'purchase' else -1
        a = by_t.setdefault(tk, {'ticker': tk, 'buy': 0.0, 'sell': 0.0, 'buyers': set(), 'sellers': set(), 'n': 0})
        a['buy' if sign > 0 else 'sell'] += mid
        (a['buyers'] if sign > 0 else a['sellers']).add(t.get('person'))
        a['n'] += 1
        p = by_p.setdefault(t.get('person') or '?', {'person': t.get('person'), 'jurisdiction': t.get('jurisdiction'), 'buy': 0.0, 'sell': 0.0,
                                                    'n': 0, 'tickers': defaultdict(float)})
        p['buy' if sign > 0 else 'sell'] += mid
        p['n'] += 1
        p['tickers'][tk] += sign * mid
    edges = []
    for a in by_t.values():
        edges.append({'ticker': a['ticker'], 'usd': round(a['buy'] - a['sell']), 'buy_mid': round(a['buy']), 'sell_mid': round(a['sell']),
                      'buyers': len(a['buyers']), 'sellers': len(a['sellers']), 'trades': a['n'],
                      'people': sorted(x for x in a['buyers'] | a['sellers'] if x)[:8]})
    edges.sort(key=lambda e: -(e['buy_mid'] + e['sell_mid']))
    people = sorted(by_p.values(), key=lambda p: -(p['buy'] + p['sell']))[:top_people]
    people = [{'person': p['person'], 'jurisdiction': p['jurisdiction'], 'buy_mid': round(p['buy']), 'sell_mid': round(p['sell']), 'trades': p['n'],
               'top': [[t, round(v)] for t, v in sorted(p['tickers'].items(), key=lambda kv: -abs(kv[1]))[:6]]} for p in people]
    return {'id': 'officials', 'kind': 'officials', 'label': 'Congress (net trades)', 'since': since, 'edges': edges, 'people': people}


def ta_holder(weights_doc, cfg, top=30):
    w = weights_doc.get('weights') or {}
    ta = cfg.get('trump_accounts') or {}
    edges = [{'ticker': t, 'weight': v, 'per_1000': round(v * 1000, 2)} for t, v in sorted(w.items(), key=lambda kv: -kv[1])[:top]]
    return {'id': 'ta', 'kind': 'ta', 'label': 'Trump Accounts', 'fund': weights_doc.get('fund'), 'as_of': (weights_doc.get('at') or '')[:10],
            'source': weights_doc.get('source'), 'lineup': ta.get('funds'), 'lineup_source': ta.get('lineup_source'),
            'lineup_date': ta.get('lineup_date'), 'holdings': len(w), 'edges': edges, 'pending': not w,
            'note': ta.get('_note')}


# ------------------------------------------------------------------ build
def primary_ticker(tickers, universe=None):
    """The common share line among a company's SEC tickers (no preferred / note suffix, a price file if any)."""
    c = sorted(tickers, key=lambda t: ('-' in t and not re.fullmatch(r'[A-Z]+-[AB]', t), len(t), t))
    if universe is not None:
        priced = [t for t in c if 'prices' in universe.sources.get(t, ())]
        if priced:
            return priced[0]
    return c[0] if c else None


def build(root, universe, gather, trades, client=None, cfg=None, quarter=None):
    root = Path(root)
    cfg = cfg or (read_json(ROOT / 'config' / 'settings.json', {}) or {}).get('crossholdings') or {}
    lc = listed_ciks(root)
    ticker_cik = {t: c for c, ts in lc.items() for t in ts}
    sic = sic_codes(root, set(gather.filers), client)
    so = shares_outstanding(root, client)
    # who is a corporate holder (an operating company investing its own money) and who manages others' money
    corps, fin_listed = [], {}
    for cik, rec in gather.filers.items():
        code = (sic.get(cik) or {}).get('sic')
        t = primary_ticker(lc.get(cik, []), universe)
        if cik in ALWAYS_CORP or (code and code not in FINANCIAL):
            corps.append({**rec, 'ticker': t, 'sic': code, 'sic_desc': (sic.get(cik) or {}).get('desc')})
        else:
            fin_listed[cik] = t
    corps.sort(key=lambda r: -r['total'])
    corp_ciks = {c['cik'] for c in corps}
    insts = [r for _, _, r in sorted(gather.heap, key=lambda x: -x[0]) if r['cik'] not in corp_ciks][:int(cfg.get('institutions', 12))]
    for r in insts:
        r['ticker'] = fin_listed.get(r['cik'])
    holders = [gov_holder(root), president_holder(root, int(cfg.get('president_top', 60))),
               officials_holder(trades, int(cfg.get('officials_months', 12))), ta_holder(fund_weights(root, cfg, client), cfg)]
    for c in corps:
        tot = c['total'] or 1
        edges = [{'ticker': t, 'usd': round(usd), 'shares': sh, 'weight': round(usd / tot, 5), 'issuer': iss}
                 for t, sh, usd, iss in sorted(c['positions'], key=lambda p: -p[2]) if usd > 0]
        holders.append({'id': f"corp:{c['cik']}", 'kind': 'corp', 'label': c['name'], 'ticker': c['ticker'], 'cik': c['cik'], 'sic': c['sic'],
                        'sic_desc': c['sic_desc'], 'as_of': c['period'], 'filed': c['filed'], 'total': round(c['total']), 'positions': len(edges),
                        'edges': edges[:60]})
    # the companies on the map: what the special holders hold, the companies that are holders, and a few biggest weights
    score = defaultdict(float)
    for h in holders:
        for k, e in enumerate(h['edges']):
            if h['kind'] == 'ta':
                score[e['ticker']] += 2.0 if k < 15 else 0.3
            elif h['kind'] == 'officials':
                score[e['ticker']] += 1.5 if k < 25 else 0.2
            elif h['kind'] == 'president':
                score[e['ticker']] += 1.5 if k < 30 else 0.2
            elif h['kind'] == 'corp':
                score[e['ticker']] += 1.0 + min(3.0, (e['usd'] or 0) / 1e9)
            else:
                score[e['ticker']] += 4.0
    for c in corps:
        if c['ticker']:
            score[c['ticker']] += 5.0
    sources_n = defaultdict(set)
    for h in holders:
        for e in h['edges']:
            sources_n[e['ticker']].add(h['id'])
    for t, s in sources_n.items():
        score[t] += 2.0 * (len(s) - 1)
    keep = [t for t, _ in sorted(score.items(), key=lambda kv: -kv[1])][:int(cfg.get('max_companies', 160))]
    keep_set = set(keep)
    # each company: who holds it
    periods = sorted(gather.agg)
    q = quarter or (periods[-1] if periods else None)
    use = [p for p in periods if q and p >= q] or periods[-1:]
    companies = []
    holder_of = {h.get('ticker'): h['id'] for h in holders if h.get('ticker')}
    for t in keep:
        cik = ticker_cik.get(t)
        h13 = [0, 0.0, 0.0]
        for p in use:
            a = gather.agg[p].get(t)
            if a:
                h13 = [h13[0] + a[0], h13[1] + a[1], h13[2] + a[2]]
        out_sh = so.get(cik) if cik else None
        px, day = last_close(root, t)
        top_inst = []
        for r in insts:
            for tk, sh, usd, _ in r['positions']:
                if tk == t and usd > 0:
                    top_inst.append({'cik': r['cik'], 'name': r['name'], 'ticker': r.get('ticker'), 'usd': round(usd), 'shares': sh,
                                     'pct': round(sh / out_sh, 5) if out_sh and sh else None, 'period': r['period']})
                    break
        top_inst.sort(key=lambda x: -x['usd'])
        companies.append({'ticker': t, 'name': universe.name(t) if universe else '', 'cik': cik, 'price': px, 'price_date': day,
                          'shares_out': out_sh, 'mcap': round(px * out_sh) if px and out_sh else None,
                          'f13_holders': h13[0], 'f13_usd': round(h13[1]), 'f13_pct': round(h13[2] / out_sh, 4) if out_sh and h13[2] else None,
                          'top_institutions': top_inst[:12], 'is_holder': holder_of.get(t)})
    # percentages on the edges where the share count is known
    so_t = {c['ticker']: c['shares_out'] for c in companies}
    for h in holders:
        for e in h['edges']:
            o = so_t.get(e['ticker'])
            if o and e.get('shares'):
                e['pct_out'] = round(e['shares'] / o, 5)
            e['on_map'] = e['ticker'] in keep_set
    # chains: a holder → a company that is itself a holder → what that company holds
    chains = []
    for h in holders:
        for e in h['edges']:
            mid_id = holder_of.get(e['ticker'])
            if not mid_id or mid_id == h['id']:
                continue
            mid = next(x for x in holders if x['id'] == mid_id)
            for e2 in mid['edges'][:8]:
                chains.append({'from': h['id'], 'via': e['ticker'], 'to': e2['ticker'], 'usd1': e.get('usd'), 'usd2': e2.get('usd'),
                               'w1': e.get('weight') or e.get('per_1000'), 'pct2': e2.get('pct_out')})
    # mutual holdings among companies that are both holders and held
    mutual = []
    corp_by_t = {h.get('ticker'): h for h in holders if h['kind'] == 'corp' and h.get('ticker')}
    for a, ha in corp_by_t.items():
        for e in ha['edges']:
            hb = corp_by_t.get(e['ticker'])
            if hb and any(x['ticker'] == a for x in hb['edges']) and a < e['ticker']:
                mutual.append([a, e['ticker']])
    doc = {'generated_at': now(), 'quarter': q, 'managers': gather.managers,
           'holders': holders, 'companies': companies,
           'institutions': [{'cik': r['cik'], 'name': r['name'], 'ticker': r.get('ticker'), 'total': round(r['total']), 'period': r['period']} for r in insts],
           'chains': chains[:400], 'mutual': mutual,
           'note': ('Who holds whom, from public filings. 13F: each manager\'s latest quarter-end report (long common shares; '
                    'companies that file 13F report their own stakes, asset managers their clients\'). US government: stakes as '
                    'announced, valued at the latest close where a share count is disclosed. President: OGE 278-T trades read '
                    'by OCR, purchases − sales at range midpoints. Congress: net trades over the last months at range midpoints. '
                    'Trump Accounts: the default fund\'s weights, in dollars per $1,000 in an account. % of shares outstanding uses '
                    'SEC\'s cover-page count. Not investment advice.')}
    write_json(root / 'market' / 'crossholdings.json', doc)
    return {'holders': len(holders), 'companies': len(companies), 'corporate_filers': len(corps), 'chains': len(chains)}
