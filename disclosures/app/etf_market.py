"""ETF market data and the joins with the rest of the Disclosure Hub (used by etf.py).

  universe   every exchange-listed ETF (Nasdaq Trader's symbol directory flags them, for all US exchanges), matched to
             the SEC's fund tickers (registrant CIK, series and class id of 1940-Act funds) or, for commodity and crypto
             trusts and ETNs, to the SEC's company tickers (they file 10-Ks).
  market     Yahoo Finance: weekly closes and volume for five years (returns, volatility, drawdown, dollar volume) and
             the fund modules (net assets, NAV, yield, category, family, expense ratio as Yahoo reports it, beta).
  joins      13F managers holding the ETF (latest complete quarter of the Hub's 13F shards), officials' trades in it,
             FINRA short interest, and the companies inside it seen through the Hub's other data.
"""
import datetime as dt
import json
import math
import re
import time
import urllib.parse
from pathlib import Path

from core import read_json, write_json  # noqa: F401
import etf_tags as TG

YQ = 'https://query2.finance.yahoo.com'
NASDAQ_DIR = 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt'


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


# ------------------------------------------------------------------ universe
def parse_nasdaq_dir(text):
    """nasdaqtraded.txt → [{symbol, name, exchange}] for the ETFs (no test issues). Exchange codes: Q Nasdaq,
    N NYSE, P NYSE Arca, Z Cboe BZX, A NYSE American, V IEX."""
    lines = [l for l in text.splitlines() if l and not l.startswith('File Creation Time')]
    if not lines:
        return []
    head = lines[0].split('|')
    ix = {k: i for i, k in enumerate(head)}
    out = []
    for l in lines[1:]:
        p = l.split('|')
        if len(p) < len(head):
            continue
        if p[ix['ETF']] != 'Y' or p[ix.get('Test Issue', 0)] == 'Y':
            continue
        sym = p[ix['Symbol']].strip()
        if not sym or '$' in sym:
            continue
        out.append({'symbol': sym, 'name': p[ix['Security Name']].strip(), 'exchange': {'Q': 'Nasdaq', 'N': 'NYSE', 'P': 'NYSE Arca', 'Z': 'Cboe BZX',
                                                                                        'A': 'NYSE American', 'V': 'IEX'}.get(p[ix['Listing Exchange']], p[ix['Listing Exchange']])})
    return out


def kind_of(name):
    n = name or ''
    if re.search(r'\bETN\b|exchange[- ]traded notes?|\bnotes? due\b', n, re.I):
        return 'etn'
    return 'etf'


def build_universe(nasdaq_rows, mf, cos):
    """mf: SEC company_tickers_mf.json; cos: company_tickers_exchange.json. Each ETF gets its registrant CIK and, for
    1940-Act funds, its series and class id; act = '40' (registered fund), '33' (trust filing 10-Ks: commodities,
    crypto, currency) or 'etn' (a bank's note)."""
    F = mf.get('fields') or ['cik', 'seriesId', 'classId', 'symbol']
    by_sym = {}
    for r in mf.get('data') or []:
        d = dict(zip(F, r))
        if d.get('symbol'):
            by_sym.setdefault(str(d['symbol']).upper(), d)
    G = cos.get('fields') or ['cik', 'name', 'ticker', 'exchange']
    by_t = {}
    for r in cos.get('data') or []:
        d = dict(zip(G, r))
        if d.get('ticker'):
            by_t.setdefault(str(d['ticker']).upper(), d)
    per_series = {}
    for d in by_sym.values():
        per_series[d.get('seriesId')] = per_series.get(d.get('seriesId'), 0) + 1
    out = []
    for r in nasdaq_rows:
        s = r['symbol'].upper()
        m, c = by_sym.get(s) or by_sym.get(s.replace('.', '-')), by_t.get(s) or by_t.get(s.replace('.', '-'))
        e = {**r, 'kind': kind_of(r['name'])}
        if m:
            e.update(cik=int(m['cik']), series=m.get('seriesId'), cls=m.get('classId'), act='40', series_classes=per_series.get(m.get('seriesId'), 1))
        elif c:
            e.update(cik=int(c['cik']), act='etn' if e['kind'] == 'etn' else '33', registrant=c.get('name'))
        else:
            e.update(cik=None, act='etn' if e['kind'] == 'etn' else None)
        L = TG.leverage(r['name'], sym=s)                # the name only here; etf.build reads the prospectus as well
        e['leveraged'], e['inverse'] = bool(L['dir']), L['dir'] < 0
        out.append(e)
    return out


def issuer_of(name):
    """The brand at the start of an ETF's name (iShares, Vanguard, SPDR, Invesco …)."""
    n = re.sub(r'^(the)\s+', '', name or '', flags=re.I)
    for pat, brand in ((r'^ishares', 'iShares (BlackRock)'), (r'^vanguard', 'Vanguard'), (r'^(spdr|select sector spdr|the select sector)', 'SPDR (State Street)'),
                       (r'^invesco', 'Invesco'), (r'^schwab', 'Schwab'), (r'^proshares', 'ProShares'), (r'^direxion', 'Direxion'), (r'^first trust', 'First Trust'),
                       (r'^global x', 'Global X'), (r'^wisdomtree', 'WisdomTree'), (r'^vaneck', 'VanEck'), (r'^jpmorgan|^j\.p\. morgan', 'J.P. Morgan'),
                       (r'^dimensional', 'Dimensional'), (r'^fidelity', 'Fidelity'), (r'^ark\b', 'ARK'), (r'^franklin', 'Franklin Templeton'),
                       (r'^pimco', 'PIMCO'), (r'^goldman sachs', 'Goldman Sachs'), (r'^american century|^avantis', 'American Century / Avantis'),
                       (r'^xtrackers', 'Xtrackers (DWS)'), (r'^grayscale', 'Grayscale'), (r'^roundhill', 'Roundhill'), (r'^yieldmax', 'YieldMax'),
                       (r'^defiance', 'Defiance'), (r'^janus', 'Janus Henderson'), (r'^pacer', 'Pacer'), (r'^amplify', 'Amplify'), (r'^capital group', 'Capital Group'),
                       (r'^t\. ?rowe', 'T. Rowe Price'), (r'^bitwise', 'Bitwise'), (r'^tidal', 'Tidal'), (r'^innovator', 'Innovator'), (r'^sprott', 'Sprott'),
                       (r'^nuveen', 'Nuveen'), (r'^columbia', 'Columbia'), (r'^alps', 'ALPS'), (r'^krane|^kraneshares', 'KraneShares'), (r'^simplify', 'Simplify'),
                       (r'^neos', 'NEOS'), (r'^graniteshares', 'GraniteShares'), (r'^tema', 'Tema'), (r'^abrdn|^aberdeen', 'abrdn'), (r'^united states', 'USCF'),
                       (r'^teucrium', 'Teucrium'), (r'^morgan stanley', 'Morgan Stanley'), (r'^bny|^bnym', 'BNY'), (r'^hartford', 'Hartford'),
                       (r'^principal', 'Principal'), (r'^putnam', 'Putnam'), (r'^virtus', 'Virtus'), (r'^strive', 'Strive'), (r'^matthews', 'Matthews'),
                       (r'^eaton vance', 'Eaton Vance'), (r'^blackrock', 'BlackRock'), (r'^state street', 'State Street'), (r'^cambria', 'Cambria'),
                       (r'^volatility shares', 'Volatility Shares'), (r'^tuttle', 'Tuttle'), (r'^etf series solutions|^us global', 'U.S. Global')):
        if re.search(pat, n, re.I):
            return brand
    w = re.findall(r"[A-Za-z][A-Za-z.&'-]+", n)
    return w[0] if w else None


# ------------------------------------------------------------------ market data
def parse_chart(body):
    """Yahoo chart (weekly) → [[date, close, adjclose, volume]]."""
    r = (body.get('chart') or {}).get('result') or []
    if not r:
        return [], {}
    r = r[0]
    ts = r.get('timestamp') or []
    q = ((r.get('indicators') or {}).get('quote') or [{}])[0]
    adj = (((r.get('indicators') or {}).get('adjclose') or [{}])[0]).get('adjclose') or q.get('close') or []
    out = []
    for i, t in enumerate(ts):
        c = (q.get('close') or [None] * len(ts))[i]
        if c is None:
            continue
        out.append([dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), round(c, 4), round(adj[i], 4) if i < len(adj) and adj[i] is not None else round(c, 4),
                    (q.get('volume') or [None] * len(ts))[i]])
    return out, r.get('meta') or {}


def market_stats(w):
    """From weekly [date, close, adj, volume]: total returns over 1m/3m/YTD/1y/3y/5y (annualised past a year),
    annualised volatility (1y), worst drawdown (5y) and the average weekly dollar volume ÷ 5 (≈ daily)."""
    if len(w) < 3:
        return {}
    last = w[-1]
    d_last = dt.date.fromisoformat(last[0])

    def back(days):
        cut = (d_last - dt.timedelta(days=days)).isoformat()
        prev = [x for x in w if x[0] <= cut]
        return prev[-1] if prev else None

    def ret(days, annual=False):
        b = back(days)
        if not b or not b[2]:
            return None
        r = last[2] / b[2] - 1
        yrs = days / 365.25
        return (1 + r) ** (1 / yrs) - 1 if annual and yrs > 1 else r

    ytd = [x for x in w if x[0] < f'{d_last.year}-01-01']
    rs = [math.log(b[2] / a[2]) for a, b in zip(w[-53:], w[-52:]) if a[2] and b[2] and a[2] > 0 and b[2] > 0]
    vol = None
    if len(rs) >= 20:
        m = sum(rs) / len(rs)
        vol = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1)) * math.sqrt(52)
    peak, mdd = None, 0.0
    for x in w:
        if x[2] is None:
            continue
        peak = x[2] if peak is None or x[2] > peak else peak
        mdd = min(mdd, x[2] / peak - 1)
    dv = [x[1] * x[3] for x in w[-13:] if x[3]]
    return {'price': last[1], 'price_date': last[0], 'r1m': ret(30), 'r3m': ret(91), 'ytd': (last[2] / ytd[-1][2] - 1) if ytd and ytd[-1][2] else None,
            'r1y': ret(365), 'r3y': ret(3 * 365, True), 'r5y': ret(5 * 365, True), 'vol1y': vol, 'max_dd': mdd if len(w) > 26 else None,
            'dollar_vol': sum(dv) / len(dv) / 5 if dv else None}


def raw(v):
    return v.get('raw') if isinstance(v, dict) else (v if isinstance(v, (int, float)) else None)


def parse_fund_summary(body):
    """Yahoo quoteSummary fund modules → the market facts the screener shows (Yahoo's own figures, labelled as such)."""
    r = ((body.get('quoteSummary') or {}).get('result') or [None])[0] or {}
    pr, sd, ks, fp = r.get('price') or {}, r.get('summaryDetail') or {}, r.get('defaultKeyStatistics') or {}, r.get('fundProfile') or {}
    th, perf = r.get('topHoldings') or {}, r.get('fundPerformance') or {}
    fees = fp.get('feesExpensesInvestment') or {}
    nav = raw(sd.get('navPrice')) or raw(ks.get('navPrice'))
    price = raw(pr.get('regularMarketPrice'))
    out = {'y_price': price, 'y_nav': nav, 'premium': (price / nav - 1) if price and nav else None,
           'y_assets': raw(sd.get('totalAssets')) or raw(ks.get('totalAssets')), 'y_yield': raw(sd.get('yield')) or raw(ks.get('yield')),
           'y_beta3y': raw(ks.get('beta3Year')), 'y_category': fp.get('categoryName') or ks.get('category'), 'y_family': fp.get('family') or ks.get('fundFamily'),
           'y_expense': raw(fees.get('annualReportExpenseRatio')) or raw(sd.get('expenseRatio')) or raw(ks.get('annualReportExpenseRatio')),
           'y_turnover': raw(fees.get('annualHoldingsTurnover')), 'y_inception': (ks.get('fundInceptionDate') or {}).get('fmt') if isinstance(ks.get('fundInceptionDate'), dict) else None,
           'y_avg_vol': raw(sd.get('averageVolume')), 'y_name': pr.get('longName') or pr.get('shortName'),
           'y_pe': raw((th.get('equityHoldings') or {}).get('priceToEarnings')), 'y_pb': raw((th.get('equityHoldings') or {}).get('priceToBook')),
           'y_duration': raw((th.get('bondHoldings') or {}).get('duration')), 'y_maturity': raw((th.get('bondHoldings') or {}).get('maturity')),
           'y_sectors': [[k, raw(v)] for d in th.get('sectorWeightings') or [] for k, v in d.items() if raw(v)],
           'y_mix': {k: raw(th.get(k)) for k in ('stockPosition', 'bondPosition', 'cashPosition', 'otherPosition', 'preferredPosition', 'convertiblePosition') if raw(th.get(k)) is not None},
           'y_trailing': {k: raw(v) for k, v in ((perf.get('trailingReturns') or {}).items()) if raw(v) is not None and k != 'asOfDate'}}
    return out


HISTORY_FROM = 631152000                               # 1990-01-01 00:00 UTC


def collect_market(h, root, etfs, crumb_fn, minutes=20.0, refresh_hours=20):
    """Yahoo per ETF, largest first then the stalest: weekly closes (since 1990 or the launch) and the fund modules. Kept in
    cache/market/<SYM>.json; state in state.json → market (its 'from': the first day asked for — an ETF fetched with a
    shorter history is refetched first, largest first, like one never fetched)."""
    root = Path(root); t0 = time.time()
    st = read_json(root / 'state.json', {}) or {}
    S = st.setdefault('market', {})
    try:
        crumb = crumb_fn(h)
    except Exception as exc:
        crumb = None
        print('::warning::yahoo crumb failed:', exc, flush=True)
    nowdt = dt.datetime.now(dt.timezone.utc)

    def due(e):
        s = S.get(e['symbol']) or {}
        if s.get('retry_after') and s['retry_after'] > now():
            return None
        if not s.get('at') or s.get('from') != HISTORY_FROM:   # never fetched, or fetched before the history went back to 1990
            return (0, -(e.get('assets') or (5e10 if e.get('act') in ('33', 'uit') or e['symbol'] in ('SPY', 'DIA', 'MDY') else 0)))
        age = (nowdt - dt.datetime.fromisoformat(s['at'])).total_seconds() / 3600
        return (1, -age) if age >= refresh_hours else None

    order = [e for d, e in sorted([(due(e), e) for e in etfs if due(e) is not None], key=lambda x: x[0])]
    done = errs = 0
    for e in order:
        if time.time() - t0 > minutes * 60:
            break
        sym = e['symbol']
        s = S.setdefault(sym, {})
        rec = {'symbol': sym, 'at': now()}
        try:
            # every week since 1990 (or the launch): explicit dates, since range=max answers with quarterly bars
            p2 = int(time.time()) + 86400
            ch = h.json(f'{YQ}/v8/finance/chart/{urllib.parse.quote(sym)}?period1={HISTORY_FROM}&period2={p2}&interval=1wk&includeAdjustedClose=true')
            w, meta = parse_chart(ch)
            rec['weekly'] = w
            rec['currency'] = meta.get('currency')
            if crumb:
                try:
                    fs = h.json(f'{YQ}/v10/finance/quoteSummary/{urllib.parse.quote(sym)}?modules=price,summaryDetail,defaultKeyStatistics,fundProfile,topHoldings,fundPerformance&crumb={urllib.parse.quote(crumb)}')
                    rec['fund'] = parse_fund_summary(fs)
                except Exception as exc:
                    rec['fund_error'] = str(exc)[:120]
            pth = root / 'cache' / 'market' / f'{sym}.json'
            pth.parent.mkdir(parents=True, exist_ok=True)
            pth.write_text(json.dumps(rec, separators=(',', ':')), encoding='utf-8')
            s.update(at=now(), fails=0, error=None, retry_after=None, **{'from': HISTORY_FROM})
            done += 1
        except Exception as exc:
            errs += 1
            s['fails'] = (s.get('fails') or 0) + 1
            s['error'] = str(exc)[:160]
            s['retry_after'] = (nowdt + dt.timedelta(hours=min(96, 6 * 2 ** s['fails']))).isoformat(timespec='seconds')
        if done % 100 == 0:
            write_json(root / 'state.json', st)
    st['market_summary'] = {'etfs': len(etfs), 'on_file': sum(1 for e in etfs if (S.get(e['symbol']) or {}).get('at')), 'this_run': done, 'errors': errs, 'at': now()}
    write_json(root / 'state.json', st)
    return st['market_summary']


# ------------------------------------------------------------------ joins with the Hub
def holders_13f(hub, cusips, periods=2):
    """13F managers holding each ETF CUSIP in the latest complete quarter (and the one before, for the change), from the
    Hub's 13F shards: {cusip: {period, holders, usd, shares, top: [[manager, usd, shares, change_shares]], prev_holders, prev_usd}}."""
    hub = Path(hub)
    cat = read_json(hub / 'catalogs' / 'holdings.json', [])
    names = {str(c['cik']): c['name'] for c in cat}
    flows = read_json(hub / 'market' / 'flows.json', {})
    cov = sorted((flows.get('coverage') or {}).items())
    # the latest quarter with most managers on file counts as complete
    full = [p for p, n in cov if cov and n >= 0.6 * max(x[1] for x in cov)]
    use = full[-periods:] if full else []
    want = set(cusips)
    agg = {}
    for pi, per in enumerate(use):
        for f in (hub / 'shards' / 'holdings').glob(f'*-{per}.json'):
            cik = f.name.split('-')[0]
            try:
                rows = json.loads(f.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            seen = {}
            for r in rows:
                c = (r.get('cusip') or '').upper()
                if c not in want or (r.get('put_call') or 'NONE') != 'NONE':
                    continue
                v = seen.setdefault(c, [0, 0])
                v[0] += r.get('value_usd') or 0
                v[1] += r.get('shares') or 0
            for c, (usd, sh) in seen.items():
                a = agg.setdefault(c, {})
                a.setdefault(per, {})[cik] = (usd, sh)
    out = {}
    for c, by in agg.items():
        if not use or use[-1] not in by:
            continue
        cur, prev = by.get(use[-1], {}), by.get(use[-2], {}) if len(use) > 1 else {}
        top = sorted(cur.items(), key=lambda x: -x[1][0])[:25]
        out[c] = {'period': use[-1], 'holders': len(cur), 'usd': sum(v[0] for v in cur.values()), 'shares': sum(v[1] for v in cur.values()),
                  'prev_holders': len(prev) if prev else None, 'prev_usd': sum(v[0] for v in prev.values()) if prev else None,
                  'new': sum(1 for k in cur if prev and k not in prev), 'exits': sum(1 for k in prev if k not in cur) if prev else None,
                  'top': [[names.get(k, k), round(u), round(s), round(s - prev[k][1]) if k in prev else None, k] for k, (u, s) in top]}
    return out, use


def officials_by_ticker(hub):
    d = read_json(Path(hub) / 'market' / 'officials-trades.json', {})
    out = {}
    for t in d.get('trades') or []:
        k = (t.get('ticker_canon') or t.get('ticker') or '').upper()
        if k:
            out.setdefault(k, []).append({key: t.get(key) for key in ('person', 'jurisdiction', 'type', 'date', 'filed_date', 'amount_min', 'amount_max', 'owner', 'source_url')})
    return out


def shorts_by_ticker(hub):
    d = read_json(Path(hub) / 'market' / 'short-interest.json', {})
    out = {}
    for r in d.get('rows') or []:
        k = (r.get('ticker') or r.get('symbol') or '').upper()
        if k:
            out[k] = {kk: r.get(kk) for kk in r if kk not in ('ticker', 'symbol')}
    return out, d.get('settlement_date')
