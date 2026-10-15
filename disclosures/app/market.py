"""Market-wide views built from the hub's caches (4.3), written to docs/data/market/:

flows.json            13F money flows across every processed manager: per security, the shares and estimated dollars
                      added / sold, how many managers bought, sold, opened, exited — for the latest well-covered quarter,
                      the current year to date, and the early filers of the quarter now being filed
officials-trades.json transactions machine-read from US House periodic transaction reports (the filer states the
                      ticker, e.g. "NVIDIA Corporation (NVDA) [ST] P 06/26/2024"), plus reviewed transaction records;
                      every ticker checked against SEC's listed-company tickers and the CUSIP map, with a name check
options13f.json       the put and call positions managers disclose in 13F (long options only; value = the underlying's value):
                      per underlying, call and put notional, how many managers hold each, changes since the prior quarter,
                      the largest holders; per manager, the largest option books; the biggest position changes
by-ticker-history.json net 13F managers (buyers − sellers) per ticker and quarter, for the rotation charts
signals.json          one row per ticker joining the three: institutional crowding, officials' trades, price momentum
                      (daily closes), with transparent tags and a heat score. The Filing Flows publish step adds the
                      latest earnings figures (stage-public.py --site-data).

Dollar flows: quantity change × the median quarter-end price that all reporting managers imply for the security
(value ÷ shares), which is robust to the occasional filer reporting in thousands. Quarter-end disclosures are not
trades; a manager's change is the difference between two consecutive disclosures. Common shares only (no options).
"""
import datetime as dt
import gzip
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from core import now, read_json, write_json
import insiders as INS

TOP = 40
FUND_TYPES = {'ETP', 'Open-End Fund', 'Closed-End Fund', 'Fund of Funds', 'Unit', 'Equity WRT', 'Right'}
SEC_TICKERS = 'https://www.sec.gov/files/company_tickers.json'
SUFFIX = {'INC', 'INCORPORATED', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'LIMITED', 'PLC', 'LP', 'LLC', 'HOLDINGS', 'HOLDING',
          'HLDGS', 'GROUP', 'GRP', 'CLASS', 'CL', 'A', 'B', 'C', 'COMMON', 'STOCK', 'SHARES', 'SHS', 'ORDINARY', 'ORD', 'ADR', 'ADS',
          'SPONSORED', 'SPON', 'THE', 'NEW', 'COM', 'SA', 'NV', 'AG', 'SE', 'TR', 'TRUST', 'UNITS', 'UNIT', 'DEL', 'N', 'V', 'REIT'}


# ------------------------------------------------------------------ names and tickers
def canon(ticker):
    t = (ticker or '').strip().upper().replace('.', '-').replace('/', '-').rstrip('*')
    return t if re.fullmatch(r'[A-Z][A-Z0-9-]{0,9}', t) else ''


def norm_name(name):
    words = re.sub(r'[^A-Z0-9 ]+', ' ', (name or '').upper().replace('&', ' AND ')).split()
    core = [w for w in words if w not in SUFFIX]
    return ' '.join(core or words)


class Universe:
    """Listed tickers and their names: SEC's company tickers (cached weekly), the OpenFIGI CUSIP map, price files."""

    def __init__(self, root):
        root = Path(root)
        self.names, self.sources = {}, defaultdict(set)
        for row in (read_json(root / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
            t = canon(row.get('ticker'))
            if t:
                self.names.setdefault(t, row.get('title') or '')
                self.sources[t].add('sec')
        self.cusips = read_json(root / 'cache' / 'prices' / 'cusips.json', {})
        self.cusip_ticker, self.cusip_type = {}, {}
        for cusip, v in self.cusips.items():
            t = canon(v.get('ticker'))
            if re.fullmatch(r'[A-Z]{1,5}\d?(EUR|GBP|CHF|CAD|JPY|AUD|HKD)', t) and 'sec' not in self.sources.get(t, ()):
                t = ''                                   # a foreign-currency line OpenFIGI returned, not a US ticker
            if t:
                self.cusip_ticker[cusip] = t
                self.cusip_type[cusip] = v.get('security_type')
                self.names.setdefault(t, v.get('name') or '')
                self.sources[t].add('cusip')
        for p in (root / 'cache' / 'prices').glob('*.json.gz'):
            t = canon(p.name[:-8])
            if t:
                self.sources[t].add('prices')
        sec = {t for t, src in self.sources.items() if 'sec' in src}
        if len(sec) >= 8000:      # SEC's list is complete: an OpenFIGI ticker it lacks and no price feed knows is an old line
            for c, t in list(self.cusip_ticker.items()):
                if t not in sec and 'prices' not in self.sources.get(t, ()):
                    self.cusip_ticker[c] = ''
        self.by_name = defaultdict(set)
        for t, n in self.names.items():
            k = norm_name(n)
            if k:
                self.by_name[k].add(t)

    def known(self, ticker):
        return canon(ticker) in self.sources

    def name(self, ticker):
        return self.names.get(canon(ticker), '')

    def suggest(self, text):
        """(ticker, confidence) from an asset description: exact normalised-name match is 'high', a unique match on the
        first two name words 'medium'."""
        k = norm_name(re.sub(r'\(.*?\)|\[.*?\]', ' ', text or ''))
        if not k:
            return None, None
        exact = self.by_name.get(k)
        if exact and len(exact) == 1:
            return next(iter(exact)), 'high'
        head = ' '.join(k.split()[:2])
        if len(head) >= 4:
            hits = {t for n, ts in self.by_name.items() if n == head or n.startswith(head + ' ') for t in ts}
            if len(hits) == 1:
                return next(iter(hits)), 'medium'
        return None, None

    def name_check(self, ticker, text):
        """'matches' when the listed name's first word appears in the filer's description, 'check' when it does not,
        None when the ticker has no listed name to compare with."""
        listed = norm_name(self.name(ticker))
        if not listed:
            return None
        first = listed.split()[0]
        words = set(norm_name(text).split())
        return 'matches' if first in words or (len(first) >= 4 and any(w.startswith(first[:4]) for w in words)) else 'check'


def refresh_sec_tickers(client, root, max_age_days=7):
    path = Path(root) / 'cache' / 'prices' / 'sec-tickers.json'
    old = read_json(path, {})
    if old.get('fetched_at'):
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(old['fetched_at'])
        if age < dt.timedelta(days=max_age_days):
            return old
    payload = client.json(SEC_TICKERS, sec=True)
    rows = [{'ticker': v.get('ticker'), 'title': v.get('title'), 'cik': v.get('cik_str')} for v in payload.values()]
    out = {'fetched_at': now(), 'source': SEC_TICKERS, 'rows': rows}
    write_json(path, out)
    return out


# ------------------------------------------------------------------ 13F flows
def _quarter_end(day):
    q = (day.month - 1) // 3
    return dt.date(day.year, 3 * q + 1, 1) - dt.timedelta(days=1)


NICE_SPLITS = (2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 30,
               1 / 40, 1 / 50, 3 / 2, 5 / 4)


def scan_13f(root, keep_after, opts=None):
    """One pass over every cached manager, keeping per (period, cusip) the holder count, price samples (value ÷ shares)
    and each manager's quantity change (shares, prior shares). Only periods after keep_after are kept. Returns
    (raw, prices, coverage, managers); summarise() turns raw into flows after split detection. When opts is a dict it
    is filled with each manager's option positions: opts[manager index][period] = {(cusip, 'PUT'|'CALL'): [shares, usd, issuer]}."""
    raw = defaultdict(lambda: defaultdict(lambda: {'issuer': None, 'holders': 0, 'moves': []}))
    samples = defaultdict(lambda: defaultdict(list))
    coverage = defaultdict(int)
    managers = []
    for path in sorted((Path(root) / 'cache' / 'holdings').glob('*.json.gz')):
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                m = json.load(f)
        except Exception:
            continue
        idx = len(managers)
        managers.append({'cik': m.get('cik'), 'name': m.get('label') or m.get('name')})
        for s in m.get('snapshots', []):
            period = s.get('period') or ''
            if not s.get('complete') or period <= keep_after:
                continue
            coverage[period] += 1
            per, smp = raw[period], samples[period]
            for p in s.get('positions', []):
                if opts is not None and p.get('put_call') in ('PUT', 'CALL') and p.get('cusip'):
                    book = opts.setdefault(idx, {}).setdefault(period, {})
                    a = book.setdefault((p['cusip'], p['put_call']), [0, 0, p.get('issuer')])
                    a[0] += p.get('shares') or 0
                    a[1] += p.get('value_usd') or 0
                if p.get('put_call') != 'NONE' or p.get('share_type') != 'SH':
                    continue
                st = per[p.get('cusip')]
                st['issuer'] = st['issuer'] or p.get('issuer')
                st['holders'] += 1
                if p.get('shares') and p.get('value_usd') and len(smp[p['cusip']]) < 31:
                    smp[p['cusip']].append(p['value_usd'] / p['shares'])
            for ch in s.get('changes', []):
                if not ch.get('delta_shares') or ch.get('put_call') != 'NONE' or ch.get('share_type') != 'SH':
                    continue
                st = per[ch.get('cusip')]
                st['issuer'] = st['issuer'] or ch.get('issuer')
                st['moves'].append((ch.get('shares') or 0, ch.get('prior_shares') or 0, idx))
    prices = {p: {c: statistics.median(v) for c, v in per.items() if v} for p, per in samples.items()}
    return raw, prices, dict(coverage), managers


def _keep(top, shares, idx, n=3):
    top.append((shares, idx))
    top.sort(reverse=True)
    del top[n:]


def split_factor(moves, p_now, p_prev):
    """k when the security split k-for-1 (or reverse-split) between the two quarter-ends, else 1: most continuing
    holders' quantities moved by the same nice ratio and the implied price moved the opposite way."""
    ratios = sorted(s / ps for s, ps, _ in moves if s and ps)
    if len(ratios) < 3:
        return 1
    med = ratios[len(ratios) // 2]
    if 0.75 <= med <= 1.3:
        return 1
    k = min(NICE_SPLITS, key=lambda x: abs(med / x - 1))
    if abs(med / k - 1) > 0.15:
        return 1
    if p_now and p_prev:
        implied = (p_prev / p_now) / k          # ≈ 1 / (true price return); a split leaves it within a broad band
        if not 0.4 <= implied <= 2.5:
            return 1
    return k


def conversions(per):
    """Holders moved from one CUSIP to another in the same quarter (re-domiciles, share-class unifications, mergers
    paid in stock): an old line that (nearly) vanished, whose exiting managers opened — manager for manager — one other
    line. Each vanished line pairs with its single best match, and the overlap must be most of both sides. Returns the
    (cusip, manager) moves to leave out of the flows and {cusip: the cusip it was converted from / to}."""
    exiters, newcomers = defaultdict(set), defaultdict(set)
    for c, st in per.items():
        for shares, prior, idx in st['moves']:
            if prior and not shares:
                exiters[c].add(idx)
            elif shares and not prior:
                newcomers[c].add(idx)
    opened = defaultdict(set)
    for c, who in newcomers.items():
        if len(who) >= 10:
            for idx in who:
                opened[idx].add(c)
    skip, converted = set(), {}
    for x, gone in exiters.items():
        if len(gone) < 10 or per[x]['holders'] > 0.1 * len(gone):
            continue
        overlap = defaultdict(int)
        for idx in gone:
            for c in opened.get(idx, ()):
                if c != x:
                    overlap[c] += 1
        if not overlap:
            continue
        c, n = max(overlap.items(), key=lambda kv: kv[1])
        if n >= 0.5 * len(gone) and n >= 0.5 * len(newcomers[c]) and c not in converted:
            both = gone & newcomers[c]
            for idx in both:
                skip.add((c, idx)); skip.add((x, idx))
            converted[c] = {'from': x, 'managers': len(both)}
            converted[x] = {'to': c, 'managers': len(both)}
    return skip, converted


def summarise(raw, prices, periods_all):
    """Per (period, cusip) flows with splits adjusted: add / sold shares, buyers, sellers, new, exits, holders,
    the largest buyers and sellers, plus flags for securities that first appear (IPO, spin-off, new CUSIP) or vanish."""
    out = {}
    order = sorted(periods_all)
    for i, period in enumerate(order):
        prev = order[i - 1] if i else None
        per = {}
        skip, converted = conversions(raw.get(period, {}))
        for c, st in raw.get(period, {}).items():
            k = split_factor(st['moves'], prices.get(period, {}).get(c), prices.get(prev, {}).get(c) if prev else None)
            a = {'issuer': st['issuer'], 'add': 0, 'sold': 0, 'buyers': 0, 'sellers': 0, 'new': 0, 'exits': 0, 'holders': st['holders'],
                 'split': k if k != 1 else None, 'top_buy': [], 'top_sell': [], 'b': set(), 's': set(),
                 'converted': converted.get(c)}
            for shares, prior, idx in st['moves']:
                if (c, idx) in skip:
                    continue
                d = shares - prior * k
                if abs(d) < 1e-9 or (prior and abs(d) / (prior * k) < 1e-4):
                    continue
                if d > 0:
                    a['add'] += d; a['buyers'] += 1; a['new'] += not prior; a['b'].add(idx)
                    _keep(a['top_buy'], d, idx)
                else:
                    a['sold'] -= d; a['sellers'] += 1; a['exits'] += not shares; a['s'].add(idx)
                    _keep(a['top_sell'], -d, idx)
            before = raw.get(prev, {}).get(c) if prev else None
            a['first'] = bool(prev) and (before is None or not before['holders']) and a['new'] >= 3
            a['gone'] = not st['holders'] and a['exits'] >= 3
            per[c] = a
        out[period] = per
    return out


def pick_periods(coverage, today=None):
    """(quarter, ytd periods, early period or None): the latest quarter most managers have filed, the current year's
    well-covered quarters, and a newer quarter that only early filers have reported so far."""
    if not coverage:
        return None, [], None
    best = max(coverage.values())
    full = sorted(p for p, n in coverage.items() if n >= 0.6 * best)
    quarter = full[-1] if full else max(coverage)
    newer = [p for p in coverage if p > quarter and coverage[p] >= 10]
    early = max(newer) if newer else None
    year = quarter[:4]
    ytd = [p for p in full if p.startswith(year)]
    return quarter, ytd, early


def flow_rows(summ, prices, universe, managers, periods):
    rows = {}
    for period in periods:
        price = prices.get(period, {})
        for c, st in summ.get(period, {}).items():
            px = price.get(c)
            r = rows.get(c)
            if r is None:
                ticker = universe.cusip_ticker.get(c, '')
                r = rows[c] = {'cusip': c, 'ticker': ticker, 'issuer': st['issuer'], 'name': universe.name(ticker) if ticker else '',
                               'type': universe.cusip_type.get(c), 'sh_add': 0, 'sh_sold': 0, 'usd_add': 0.0, 'usd_sold': 0.0,
                               'b': set(), 's': set(), 'new': 0, 'exits': 0, 'holders': 0, 'price': None, 'top_buy': [], 'top_sell': [],
                               'first': False, 'gone': False, 'split': None, 'converted': None}
            r['sh_add'] += st['add']; r['sh_sold'] += st['sold']
            if px:
                r['usd_add'] += st['add'] * px; r['usd_sold'] += st['sold'] * px
                r['price'] = px
            r['b'] |= st['b']; r['s'] |= st['s']; r['new'] += st['new']; r['exits'] += st['exits']
            r['holders'] = st['holders']                     # the latest period's holder count
            r['first'] = r['first'] or st['first']
            r['gone'] = st['gone']
            r['split'] = st['split'] or r['split']
            r['converted'] = st.get('converted') or r['converted']
            for sh, idx in st['top_buy']:
                r['top_buy'].append((sh * (px or 0), managers[idx]['name'], period))
            for sh, idx in st['top_sell']:
                r['top_sell'].append((sh * (px or 0), managers[idx]['name'], period))
    out = []
    for c, r in rows.items():
        b, s = r.pop('b'), r.pop('s')
        r['buyers'], r['sellers'] = len(b), len(s)          # distinct managers across the window
        r['usd_add'], r['usd_sold'] = round(r['usd_add']), round(r['usd_sold'])
        r['usd_net'] = r['usd_add'] - r['usd_sold']
        r['sh_net'] = r['sh_add'] - r['sh_sold']
        r['top_buy'] = [{'manager': n, 'usd': round(u), 'period': p} for u, n, p in sorted(r['top_buy'], reverse=True)[:3] if u > 0]
        r['top_sell'] = [{'manager': n, 'usd': round(u), 'period': p} for u, n, p in sorted(r['top_sell'], reverse=True)[:3] if u > 0]
        r['price'] = round(r['price'], 4) if r['price'] else None
        r['fund'] = r['type'] in FUND_TYPES
        out.append(r)
    return out


def ranked(rows, n=TOP):
    fresh = [r for r in rows if r['first']]
    gone = [r for r in rows if r['gone']]
    rows = [r for r in rows if not r['first'] and not r['gone'] and r['buyers'] + r['sellers'] >= 3]   # one odd filer is not a flow
    pos = [r for r in rows if r['usd_net'] > 0]
    neg = [r for r in rows if r['usd_net'] < 0]
    return {'first_on_file': sorted(fresh, key=lambda r: (-r['holders'], -r['usd_add']))[:n],
            'retired': sorted(gone, key=lambda r: -r['usd_sold'])[:n],
            'added': sorted(rows, key=lambda r: -r['usd_add'])[:n],
            'sold': sorted(rows, key=lambda r: -r['usd_sold'])[:n],
            'net_buy': sorted(pos, key=lambda r: -r['usd_net'])[:n],
            'net_sell': sorted(neg, key=lambda r: r['usd_net'])[:n],
            'most_buyers': sorted(rows, key=lambda r: (-(r['buyers'] - r['sellers']), -r['usd_net']))[:n],
            'most_sellers': sorted(rows, key=lambda r: (-(r['sellers'] - r['buyers']), r['usd_net']))[:n],
            'new_positions': sorted(rows, key=lambda r: (-r['new'], -r['usd_add']))[:n],
            'exits': sorted(rows, key=lambda r: (-r['exits'], -r['usd_sold']))[:n]}


def history(summ, prices, periods, cusips):
    """Per listed security, net managers and net dollars in each of the last periods (for sparklines)."""
    out = {}
    for c in cusips:
        h = []
        for p in periods:
            st = summ.get(p, {}).get(c)
            px = prices.get(p, {}).get(c)
            if st:
                h.append([p, st['buyers'] - st['sellers'], round((st['add'] - st['sold']) * px) if px else None])
            else:
                h.append([p, None, None])
        out[c] = h
    return out


def build_flows(root, universe, scan=None, opts=None):
    today = dt.datetime.now(dt.timezone.utc).date()
    keep_after = (_quarter_end(today) - dt.timedelta(days=2 * 366)).isoformat()
    raw, prices, coverage, managers = scan or scan_13f(root, keep_after, opts)
    quarter, ytd, early = pick_periods(coverage)
    if not quarter:
        return None, None
    summ = summarise(raw, prices, coverage)
    windows = {'quarter': [quarter], 'ytd': ytd or [quarter]}
    if early:
        windows['early'] = [early]
    hist_periods = [p for p in sorted(coverage) if coverage[p] >= 10][-6:]
    out = {'generated_at': now(), 'managers_on_file': len(managers), 'coverage': {p: coverage[p] for p in sorted(coverage)},
           'windows': {}, 'note': ('Changes between consecutive quarter-end 13F disclosures of the managers processed so far — not '
                                   'trades and not every holder. Dollar values: quantity change × the median quarter-end price the '
                                   'reporting managers imply (value ÷ shares). Stock splits are detected and adjusted. Securities '
                                   'that first appear (IPOs, spin-offs, new CUSIPs) or disappear (mergers, retired CUSIPs) are '
                                   'listed separately. Common shares only; options excluded. "Stocks" leaves out ETFs and funds.')}
    every = {}
    listed = set()
    for key, periods in windows.items():
        rows = flow_rows(summ, prices, universe, managers, periods)
        every[key] = rows
        stocks = [r for r in rows if not r['fund']]
        lists = {'stocks': ranked(stocks), 'all': ranked(rows)}
        for univ in lists.values():
            for lst in univ.values():
                listed.update(r['cusip'] for r in lst)
        n = len(periods)
        label = {'quarter': f'Quarter ended {quarter}', 'ytd': f'{periods[0][:4]} year to date ({n} quarter{"s" if n != 1 else ""} on file)',
                 'early': f'Early filers for the quarter ended {early} ({coverage.get(early, 0)} managers so far)'}[key]
        core = [r for r in stocks if not r['first'] and not r['gone']]
        out['windows'][key] = {'label': label, 'periods': periods, 'managers': coverage.get(periods[-1], 0),
                               'securities': len(rows), 'splits': sum(1 for r in rows if r['split']),
                               'totals': {'usd_add': sum(r['usd_add'] for r in core), 'usd_sold': sum(r['usd_sold'] for r in core)},
                               'lists': lists}
    out['history_periods'] = hist_periods
    out['history'] = history(summ, prices, hist_periods, listed)
    out['_by_quarter'] = ticker_history(summ, universe, [p for p in sorted(coverage) if coverage[p] >= 10], coverage)
    out['_ctx'] = {'prices': prices, 'coverage': coverage, 'managers': managers, 'quarter': quarter}
    return out, every


def ticker_history(summ, universe, periods, coverage):
    """Net 13F managers (distinct buyers − sellers) per listed stock and quarter: {'periods', 'coverage', 'rows': {T: [n…]}}."""
    rows = {}
    for i, period in enumerate(periods):
        per = defaultdict(lambda: [set(), set()])
        for c, st in summ.get(period, {}).items():
            t = universe.cusip_ticker.get(c)
            if not t or universe.cusip_type.get(c) in FUND_TYPES:
                continue
            per[t][0] |= st['b']; per[t][1] |= st['s']
        for t, (b, s_) in per.items():
            rows.setdefault(t, [None] * len(periods))[i] = len(b) - len(s_)
    return {'periods': periods, 'coverage': [coverage.get(p, 0) for p in periods], 'rows': rows}


# ------------------------------------------------------------------ 13F option positions (puts and calls managers disclose)
def options13f(opts, managers, universe, coverage, quarter, equity_prices, n=300):
    """Disclosed long put and call positions per underlying for the latest well-covered quarter, with changes against
    each manager's previous complete 13F, the largest holders, the largest option books and the biggest moves."""
    if not opts or not quarter:
        return None
    periods = sorted(p for p in coverage if p <= quarter)[-6:]
    prev_of = {}
    agg = {}                                     # (cusip) → per period {'C': [usd, managers, shares], 'P': …}
    holders = defaultdict(list)                  # cusip → [(usd, manager, pc, shares, chg_sh)] for the latest quarter
    moves = []
    books = []
    for idx, per in opts.items():
        mine = sorted(per)
        for period in mine:
            if period not in periods:
                continue
            for (c, pc), (sh, usd, issuer) in per[period].items():
                a = agg.setdefault(c, {'issuer': issuer, 'p': {}})
                b = a['p'].setdefault(period, {'CALL': [0, 0, 0], 'PUT': [0, 0, 0]})[pc]
                b[0] += usd; b[1] += 1; b[2] += sh
        if quarter not in per:
            continue
        before = [p for p in mine if p < quarter]
        old = per[before[-1]] if before and before[-1] == _prev_q(quarter) else None
        call = put = 0
        for (c, pc), (sh, usd, issuer) in per[quarter].items():
            px = usd / sh if sh else None
            o = (old or {}).get((c, pc))
            chg = None if old is None else sh - (o[0] if o else 0)
            holders[c].append((usd, managers[idx]['name'], pc, sh, chg))
            call += usd if pc == 'CALL' else 0
            put += usd if pc == 'PUT' else 0
            if chg and px:
                moves.append({'manager': managers[idx]['name'], 'cusip': c, 'pc': pc, 'usd': round(usd), 'chg_usd': round(chg * px),
                              'kind': 'new' if not o else 'added' if chg > 0 else 'cut'})
        if old is not None:
            for (c, pc), (sh, usd, issuer) in old.items():
                if (c, pc) not in per[quarter] and sh:
                    px = equity_prices.get(quarter, {}).get(c) or (usd / sh)
                    moves.append({'manager': managers[idx]['name'], 'cusip': c, 'pc': pc, 'usd': 0, 'chg_usd': -round(sh * px), 'kind': 'closed'})
                    holders[c].append((0, managers[idx]['name'], pc, 0, -sh))
        if call or put:
            top = sorted(per[quarter].items(), key=lambda kv: -kv[1][1])[:5]
            books.append({'manager': managers[idx]['name'], 'cik': managers[idx]['cik'], 'call_usd': round(call), 'put_usd': round(put),
                          'positions': len(per[quarter]),
                          'top': [{'ticker': universe.cusip_ticker.get(c, ''), 'issuer': v[2], 'pc': pc, 'usd': round(v[1])} for (c, pc), v in top]})
    rows = []
    for c, a in agg.items():
        now_ = a['p'].get(quarter)
        if not now_:
            continue
        t = universe.cusip_ticker.get(c, '')
        hs = holders.get(c, [])
        d = {pc: sum(h[4] * ((now_[pc][0] / now_[pc][2]) if now_[pc][2] else 0) for h in hs if h[2] == pc and h[4]) for pc in ('CALL', 'PUT')}
        rows.append({'cusip': c, 'ticker': t, 'name': universe.name(t) if t else '', 'issuer': a['issuer'],
                     'fund': universe.cusip_type.get(c) in FUND_TYPES,
                     'call_usd': round(now_['CALL'][0]), 'put_usd': round(now_['PUT'][0]), 'call_mgrs': now_['CALL'][1],
                     'put_mgrs': now_['PUT'][1], 'call_sh': now_['CALL'][2], 'put_sh': now_['PUT'][2],
                     'pc_usd': round(now_['PUT'][0] / now_['CALL'][0], 3) if now_['CALL'][0] else None,
                     'd_call_usd': round(d['CALL']), 'd_put_usd': round(d['PUT']),
                     'new_call': sum(1 for h in hs if h[2] == 'CALL' and h[4] is not None and h[4] == h[3] and h[3] > 0),
                     'new_put': sum(1 for h in hs if h[2] == 'PUT' and h[4] is not None and h[4] == h[3] and h[3] > 0),
                     'closed_call': sum(1 for h in hs if h[2] == 'CALL' and h[3] == 0),
                     'closed_put': sum(1 for h in hs if h[2] == 'PUT' and h[3] == 0),
                     'top': [{'manager': m, 'pc': pc, 'usd': round(u), 'chg_sh': ch} for u, m, pc, sh, ch in sorted(hs, key=lambda h: -h[0])[:6] if u],
                     'hist': [[p, round(a['p'][p]['CALL'][0]), round(a['p'][p]['PUT'][0]), a['p'][p]['CALL'][1], a['p'][p]['PUT'][1]]
                              for p in periods if p in a['p']]})
    rows.sort(key=lambda r: -(r['call_usd'] + r['put_usd']))
    for m in moves:
        m['ticker'] = universe.cusip_ticker.get(m['cusip'], '')
        m['issuer'] = agg.get(m['cusip'], {}).get('issuer')
    moves.sort(key=lambda m: -abs(m['chg_usd']))
    books.sort(key=lambda b: -(b['call_usd'] + b['put_usd']))
    tot = lambda pc: sum(r[pc] for r in rows)
    return {'generated_at': now(), 'quarter': quarter, 'periods': periods, 'managers': len(books),
            'totals': {'call_usd': tot('call_usd'), 'put_usd': tot('put_usd'),
                       'by_period': [[p, round(sum(a['p'].get(p, {}).get('CALL', [0])[0] for a in agg.values())),
                                      round(sum(a['p'].get(p, {}).get('PUT', [0])[0] for a in agg.values())),
                                      sum(1 for per in opts.values() if p in per)] for p in periods]},
            'rows': rows[:n], 'books': books[:80], 'moves': moves[:150],
            'note': ('13F lists long put and call positions only (options written are not reported), valued at the underlying '
                     'shares, not the premium paid. Many holders are market makers hedging other books, so a put is not '
                     'necessarily a bearish bet. Changes compare each manager with its own previous quarter; values are '
                     'quarter-end, up to 45 days old when filed.')}


def _prev_q(period):
    d = dt.date.fromisoformat(period)
    return _quarter_end(d).isoformat()


# ------------------------------------------------------------------ officials' trades (House PTRs, machine-read)
TX = re.compile(r'(?<![A-Za-z(])(P|S \(partial\)|S|E)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})')
TICK = re.compile(r'\(([A-Z][A-Z0-9]{0,5}(?:[.\-/][A-Z0-9]{1,3})?)\)')
TAG = re.compile(r'\[([A-Z]{2})\]')
OWNER = re.compile(r'(?:^|\s)(SP|JT|DC)\s')
TYPES = {'P': 'purchase', 'S': 'sale', 'S (partial)': 'partial sale', 'E': 'exchange'}


def _iso(mdy):
    try:
        return dt.datetime.strptime(mdy, '%m/%d/%Y').date().isoformat()
    except ValueError:
        return ''


def parse_ptr_candidate(c):
    """One House PTR candidate (a text window around an amount range) → the transaction row it belongs to, or None.
    The excerpt can start with the previous row's "F S: New / D: …" notes and end with the next row; the row is the
    text between them."""
    e = c.get('excerpt') or ''
    m = TX.search(e)
    if not m:
        return None
    head = e[:m.start()]
    start = 0
    g = head.rfind('Gains > $200?')
    if g >= 0:
        start = g + len('Gains > $200?')
    for x in re.finditer(r'F S: \w+(?: D: [^.]*\.)?', head):
        start = max(start, x.end())
    end = e.find('F S:', m.end())
    row = e[start:end if end >= 0 else len(e)]
    tickers = [t for t in TICK.findall(row) if t != 'PARTIAL']
    tag = TAG.search(row)
    owner = None
    pre = row[:max(0, m.start() - start)]
    for o in OWNER.finditer(pre):
        owner = o.group(1)
    asset = re.sub(r'S O: .*?(?=\b[A-Z][a-z])', '', pre)               # drop the "subholding of" account line where we can
    asset = re.sub(r'\s+', ' ', re.sub(r'(?:^|\s)(SP|JT|DC)\s', ' ', asset)).strip(' -')
    return {'ticker': tickers[0].replace('/', '.') if tickers else '', 'asset_type': tag.group(1) if tag else '',
            'type': TYPES[m.group(1)], 'date': _iso(m.group(2)), 'notified': _iso(m.group(3)), 'owner': owner or 'Self',
            'asset_raw': asset[:160], 'amount_min': c.get('amount_min'), 'amount_max': c.get('amount_max')}


def officials_trades(root, universe, live=None):
    root = Path(root)
    live = live if live is not None else read_json(root / 'live.json', {})
    cong = (live.get('modules') or {}).get('congress') or {}
    today = dt.date.today().isoformat()
    trades, seen, stats = [], set(), defaultdict(int)
    for rep in cong.get('reports', []):
        if rep.get('jurisdiction') != 'US House' or rep.get('report_type') != 'PTR' or not rep.get('shard'):
            continue
        shard = read_json(root / rep['shard'], {})
        for c in shard.get('candidates', []):
            t = parse_ptr_candidate(c)
            if not t:
                stats['no transaction pattern'] += 1
                continue
            if not t['ticker']:
                stats['no ticker (bonds, funds, private)'] += 1
                continue
            if not ('2012-01-01' <= t['date'] <= today):
                stats['date out of range'] += 1
                continue
            key = (rep.get('person'), t['ticker'], t['date'], t['type'], t['amount_min'], t['owner'])
            if key in seen:
                stats['duplicate (amendment / repeated row)'] += 1
                continue
            seen.add(key)
            trades.append(_checked({**t, 'person': rep.get('person'), 'jurisdiction': 'US House', 'report_id': rep.get('report_id'),
                                    'filed_date': rep.get('filed_date'), 'source_url': rep.get('source_url'), 'page': c.get('page'),
                                    'read': 'machine'}, universe))
    for r in cong.get('records', []):                       # reviewed transaction rows (any jurisdiction)
        if r.get('kind') != 'transaction':
            continue
        t = {'ticker': (r.get('ticker') or '').strip(), 'asset_type': '', 'type': r.get('transaction_type') or 'other',
             'date': r.get('transaction_date') or '', 'notified': '', 'owner': r.get('owner') or 'Self', 'asset_raw': r.get('asset') or '',
             'amount_min': r.get('amount_min'), 'amount_max': r.get('amount_max'), 'person': r.get('person'),
             'jurisdiction': r.get('jurisdiction'), 'report_id': r.get('report_id'), 'filed_date': r.get('filed_date'),
             'source_url': r.get('source_url'), 'page': r.get('page'), 'read': 'reviewed'}
        if not t['ticker']:
            sug, conf = universe.suggest(t['asset_raw'])
            t['suggested'], t['confidence'] = sug, conf
        trades.append(_checked(t, universe))
    trades.sort(key=lambda t: (t['date'], t['person'] or ''), reverse=True)
    stats['trades'] = len(trades)
    stats['tickers'] = len({t['ticker_canon'] for t in trades if t.get('ticker_canon')})
    stats['listed'] = sum(t.get('ticker_status') == 'listed' for t in trades)
    stats['name check'] = sum(t.get('name_check') == 'check' for t in trades)
    return trades, dict(stats)


def _checked(t, universe):
    tk = canon(t.get('ticker'))
    t['ticker_canon'] = tk
    if tk:
        t['ticker_status'] = 'listed' if universe.known(tk) else 'not in listings'
        t['listed_name'] = universe.name(tk)
        t['name_check'] = universe.name_check(tk, t.get('asset_raw') or '')
        if t['ticker_status'] != 'listed':
            sug, conf = universe.suggest(t.get('asset_raw') or '')
            if sug and sug != tk:
                t['suggested'], t['confidence'] = sug, conf
    return t


def officials_summary(trades, since):
    agg = {}
    for t in trades:
        tk = t.get('ticker_canon')
        if not tk or t['date'] < since or t.get('asset_type') == 'OP':
            continue
        a = agg.setdefault(tk, {'ticker': tk, 'name': t.get('listed_name') or t.get('asset_raw'), 'buys': 0, 'sells': 0, 'people_buy': set(),
                                'people_sell': set(), 'buy_min': 0, 'sell_min': 0, 'last': ''})
        if t['type'] == 'purchase':
            a['buys'] += 1; a['people_buy'].add(t['person']); a['buy_min'] += t.get('amount_min') or 0
        elif 'sale' in t['type']:
            a['sells'] += 1; a['people_sell'].add(t['person']); a['sell_min'] += t.get('amount_min') or 0
        a['last'] = max(a['last'], t['date'])
    rows = []
    for a in agg.values():
        rows.append({**a, 'people_buy': sorted(p for p in a['people_buy'] if p), 'people_sell': sorted(p for p in a['people_sell'] if p)})
    return rows


# ------------------------------------------------------------------ prices and signals
def price_stats(root, ticker):
    path = Path(root) / 'cache' / 'prices' / (re.sub(r'[^A-Za-z0-9-]', '_', ticker) + '.json.gz')
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            rows = json.load(f)['rows']
    except Exception:
        return None
    if len(rows) < 30:
        return None
    closes = [r[1] for r in rows]
    last = closes[-1]
    ret = lambda n: (last / closes[-1 - n] - 1) if len(closes) > n and closes[-1 - n] else None
    year = closes[-252:]
    high = max(year)
    ma200 = sum(closes[-200:]) / len(closes[-200:])
    spark = [round(c, 4) for c in closes[-130::5]]
    return {'last': round(last, 4), 'date': rows[-1][0], 'r1m': ret(21), 'r3m': ret(63), 'r6m': ret(126), 'r1y': ret(252),
            'from_high': last / high - 1 if high else None, 'above_ma200': last > ma200, 'spark': spark}


def insider_summary(root):
    store = Path(root) / 'cache' / 'insiders' / 'trades.json.gz'
    if not store.exists():
        return {}
    try:
        with gzip.open(store, 'rt', encoding='utf-8') as f:
            return {canon(a['ticker']): a for a in INS.summary(json.load(f)) if canon(a['ticker'])}
    except Exception:
        return {}


def build_signals(root, flows_every, trades, universe):
    q = {r['ticker']: r for r in (flows_every or {}).get('quarter', []) if r.get('ticker') and not r['fund'] and not r['first'] and not r['gone']}
    today = dt.date.today()
    d90 = {r['ticker']: r for r in officials_summary(trades, (today - dt.timedelta(days=90)).isoformat())}
    d365 = {r['ticker']: r for r in officials_summary(trades, (today - dt.timedelta(days=365)).isoformat())}
    # institutional thresholds relative to this quarter's distribution
    nets = sorted((r['buyers'] - r['sellers'] for r in q.values()), reverse=True)
    usd = sorted((r['usd_net'] for r in q.values()), reverse=True)
    crowd_cut = max(8, nets[min(len(nets) - 1, 60)] if nets else 8)
    inflow_cut = max(50e6, usd[min(len(usd) - 1, 60)] if usd else 50e6)
    outflow_cut = min(-50e6, usd[-min(len(usd), 61)] if usd else -50e6)
    news = sorted((r['new'] for r in q.values()), reverse=True)
    new_cut = max(10, news[min(len(news) - 1, 100)] if news else 10)
    ins = insider_summary(root)
    tickers = set(q) | set(d365) | {t for t, a in ins.items() if a['buys']}
    rows = []
    for tk in tickers:
        f = q.get(tk)
        o90, o365 = d90.get(tk), d365.get(tk)
        px = price_stats(root, tk)
        tags = []
        if f:
            net = f['buyers'] - f['sellers']
            if net >= crowd_cut and f['buyers'] >= 2 * max(1, f['sellers']):
                tags.append('crowded_buy')
            if f['new'] >= new_cut:
                tags.append('new_money')
            if f['usd_net'] >= inflow_cut:
                tags.append('big_inflow')
            if -net >= crowd_cut and f['sellers'] >= 2 * max(1, f['buyers']):
                tags.append('crowded_exit')
            if f['usd_net'] <= outflow_cut:
                tags.append('big_outflow')
        if o90 and o90['buys']:
            tags.append('officials_buying')
        if o365 and len(o365['people_buy']) >= 2:
            tags.append('officials_cluster')
        if o90 and o90['sells'] > (o90['buys'] or 0):
            tags.append('officials_selling')
        ia = ins.get(tk)
        if ia:
            if ia['buys'] and ia['buy_value'] >= 100_000:
                tags.append('insider_buying')
            if ia['cluster']:
                tags.append('insider_cluster')
            if ia['ceo_cfo_sell'] >= 1_000_000 and not ia['buys']:
                tags.append('insider_selling')
        if px:
            if px['from_high'] is not None and px['from_high'] >= -0.03:
                tags.append('near_high')
            if px['r3m'] is not None and px['r3m'] >= 0.2:
                tags.append('momentum')
            if px['r3m'] is not None and px['r3m'] <= -0.2:
                tags.append('drawdown')
            if f and ('crowded_buy' in tags or 'big_inflow' in tags) and px['r3m'] is not None and px['r3m'] <= -0.1:
                tags.append('buying_the_dip')
        heat = (2 * ('crowded_buy' in tags) + ('new_money' in tags) + ('big_inflow' in tags) + 2 * ('officials_buying' in tags)
                + ('officials_cluster' in tags) + ('near_high' in tags) + ('momentum' in tags)
                + ('insider_buying' in tags) + 2 * ('insider_cluster' in tags))
        pressure = (2 * ('crowded_exit' in tags) + ('big_outflow' in tags) + ('officials_selling' in tags) + ('drawdown' in tags)
                    + ('insider_selling' in tags))
        if not tags:
            continue
        rows.append({'ticker': tk, 'name': universe.name(tk) or (f or {}).get('issuer') or (o365 or {}).get('name') or '',
                     'tags': tags, 'heat': heat, 'pressure': pressure,
                     'f13': {k: f[k] for k in ('buyers', 'sellers', 'new', 'exits', 'holders', 'usd_add', 'usd_sold', 'usd_net', 'cusip')} if f else None,
                     'top_buy': (f or {}).get('top_buy', [])[:2],
                     'officials': ({'d90_buys': (o90 or {}).get('buys', 0), 'd90_sells': (o90 or {}).get('sells', 0),
                                    'y_buys': o365['buys'], 'y_sells': o365['sells'], 'people_buy': o365['people_buy'][:6],
                                    'people_sell': o365['people_sell'][:6], 'last': o365['last']} if o365 else None),
                     'price': px,
                     'insiders': ({'buys': ia['buys'], 'buy_value': ia['buy_value'], 'buyers': ia['buyers'][:4], 'sells': ia['sells'],
                                   'sell_value': ia['sell_value'], 'cluster': ia['cluster'], 'top_buy': ia['top_buy'], 'last': ia['last']}
                                  if ia else None)})
    rows.sort(key=lambda r: (-r['heat'], -((r['f13'] or {}).get('usd_net') or 0)))
    # keep sparklines only where they are shown
    for r in rows[200:]:
        if r['price']:
            r['price'].pop('spark', None)
    rows = [r for r in rows if r['heat'] >= 2 or r['pressure'] >= 2 or r['officials'] or (r['insiders'] or {}).get('buys')][:900]
    return rows, {'crowd_net_managers': crowd_cut, 'new_positions': new_cut, 'inflow_usd': inflow_cut, 'outflow_usd': outflow_cut}


TAGS = {
    'crowded_buy': 'Crowded buy: far more 13F managers added than cut this quarter',
    'new_money': 'New money: among the most new positions opened this quarter',
    'big_inflow': 'Big inflow: among the largest estimated net dollar additions this quarter',
    'crowded_exit': 'Crowded exit: far more managers cut than added',
    'big_outflow': 'Big outflow: among the largest estimated net dollar reductions',
    'officials_buying': 'Officials buying: a public official reported a purchase in the last 90 days',
    'officials_cluster': 'Officials cluster: two or more officials reported purchases within a year',
    'officials_selling': 'Officials selling: more reported sales than purchases in the last 90 days',
    'near_high': 'Near 52-week high: within 3% of the highest close of the last year',
    'momentum': 'Momentum: up 20% or more over three months',
    'drawdown': 'Drawdown: down 20% or more over three months',
    'buying_the_dip': 'Buying the dip: managers crowding in while the price fell 10%+ over three months',
    'insider_buying': 'Insider buying: officers or directors bought $100K+ of stock in the open market in the last 90 days (Form 4)',
    'insider_cluster': 'Insider cluster: three or more insiders bought within 30 days (Form 4)',
    'insider_selling': 'Insider selling: the CEO or CFO sold $1M+ in 90 days with no insider purchases (Form 4)',
    'revenue_surge': 'Revenue surge: latest quarter revenue up 25%+ year over year (Filing Flows)',
    'profitable_growth': 'Profitable growth: revenue up 15%+ with an operating margin of 15%+ (Filing Flows)',
}


# ------------------------------------------------------------------ watched funds (superinvestors)
def watchlist(root, watch, universe, top=6):
    """The latest complete 13F of each watched fund: new positions, the largest adds and cuts, exits — in dollars."""
    funds, missing = [], []
    for w in watch:
        cik = str(int(w['cik']))
        path = Path(root) / 'cache' / 'holdings' / f'{cik}.json.gz'
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                m = json.load(f)
        except Exception:
            missing.append({'cik': cik, 'name': w.get('name')})
            continue
        if w.get('key') and w['key'].upper() not in (m.get('name') or '').upper():
            missing.append({'cik': cik, 'name': w.get('name'), 'error': f"CIK belongs to {m.get('name')}"})
            continue
        snaps = [s for s in m.get('snapshots', []) if s.get('complete')]
        if not snaps:
            missing.append({'cik': cik, 'name': w.get('name')})
            continue
        s = snaps[-1]
        rows = []
        for c in s.get('changes', []):
            if c.get('put_call') != 'NONE' or c.get('share_type') != 'SH' or not c.get('delta_shares'):
                continue
            px = (c['value_usd'] / c['shares']) if c.get('shares') and c.get('value_usd') else (
                (c.get('prior_value_usd') or 0) / c['prior_shares'] if c.get('prior_shares') else 0)
            t = universe.cusip_ticker.get(c.get('cusip'), '')
            rows.append({'ticker': t, 'issuer': c.get('issuer'), 'status': c.get('status'), 'usd': round(abs(c['delta_shares']) * px),
                         'shares': c['delta_shares'], 'weight': round((c.get('weight') or 0) * 100, 2), 'value': c.get('value_usd')})
        pick = lambda st: sorted([r for r in rows if r['status'] == st], key=lambda r: -r['usd'])[:top]
        funds.append({'cik': cik, 'name': w.get('name') or m.get('name'), 'filer': m.get('name'), 'period': s.get('period'),
                      'filed': s.get('filed'), 'total_usd': s.get('total_usd'), 'positions': len(s.get('positions', [])),
                      'new': pick('NEW'), 'added': pick('INCREASE'), 'cut': pick('DECREASE'), 'exited': pick('EXIT'),
                      'top': sorted(({'ticker': universe.cusip_ticker.get(p.get('cusip'), ''), 'issuer': p.get('issuer'),
                                      'weight': round((p.get('weight') or 0) * 100, 2)} for p in s.get('positions', [])
                                     if p.get('put_call') == 'NONE'), key=lambda r: -r['weight'])[:5],
                      'source': ((s.get('sources') or [{}])[-1]).get('url')})
    funds.sort(key=lambda f: f.get('filed') or '', reverse=True)
    return {'generated_at': now(), 'funds': funds, 'missing': missing}


# ------------------------------------------------------------------ publish
def publish(root, client=None, min_interval_hours=3, force=False, live=None):
    root = Path(root)
    out_dir = root / 'market'
    meta = read_json(out_dir / 'meta.json', {})
    if not force and meta.get('built_at'):
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(meta['built_at'])
        if age < dt.timedelta(hours=min_interval_hours):
            return {'status': 'skipped', 'reason': f'built {age.seconds // 60} minutes ago'}
    errors = []
    if client is not None:
        try:
            refresh_sec_tickers(client, root)
        except Exception as exc:
            errors.append(f'SEC tickers: {exc}')
    universe = Universe(root)
    opts = {}
    flows, every = build_flows(root, universe, opts=opts)
    by_quarter, ctx = (flows.pop('_by_quarter', None), flows.pop('_ctx', None)) if flows else (None, None)
    trades, tstats = officials_trades(root, universe, live)
    signals, cuts = build_signals(root, every, trades, universe)
    stamp = now()
    if flows:
        _write(out_dir / 'flows.json', flows)
        by = {}
        for r in every.get('quarter', []):
            t = r.get('ticker')
            if not t or r['fund']:
                continue
            a = by.setdefault(t, [0, 0, 0, 0, 0, 0])
            for i, k in enumerate(('buyers', 'sellers', 'new', 'exits', 'usd_net', 'holders')):
                a[i] += r[k] or 0
        _write(out_dir / 'by-ticker.json', {'generated_at': stamp, 'label': flows['windows']['quarter']['label'],
                                             'fields': ['buyers', 'sellers', 'new', 'exits', 'usd_net', 'holders'], 'rows': by})
        if by_quarter:
            _write(out_dir / 'by-ticker-history.json', {'generated_at': stamp, **by_quarter})
        try:
            o13 = options13f(opts, ctx['managers'], universe, ctx['coverage'], ctx['quarter'], ctx['prices'])
            if o13:
                _write(out_dir / 'options13f.json', o13)
        except Exception as exc:
            errors.append(f'13F options: {exc}')
    today = dt.date.today()
    off = {'generated_at': stamp, 'stats': tstats,
           'note': ('US House periodic transaction reports read by machine: the ticker is the one the filer wrote next to the '
                    'asset, checked against SEC listed-company tickers and the CUSIP map; amounts are the disclosed ranges. '
                    'Reviewed rows come from the review desk. Dates are transaction dates; reports can arrive up to 45 days later.'),
           'summary': {'d90': sorted(officials_summary(trades, (today - dt.timedelta(days=90)).isoformat()),
                                     key=lambda r: (-len(r['people_buy']), -r['buys'], -r['buy_min']))[:TOP],
                       'ytd': sorted(officials_summary(trades, f'{today.year}-01-01'),
                                     key=lambda r: (-len(r['people_buy']), -r['buys'], -r['buy_min']))[:TOP]},
           'trades': trades[:4000]}
    _write(out_dir / 'officials-trades.json', off)
    _write(out_dir / 'signals.json', {'generated_at': stamp, 'quarter': (flows or {}).get('windows', {}).get('quarter', {}).get('label'),
                                      'thresholds': cuts, 'tags': TAGS, 'rows': signals,
                                      'note': ('Signals are descriptive flags computed from public filings and daily closes — what '
                                               'happened, not what will happen, and never a recommendation.')})
    watch = (read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {}).get('holdings') or {}).get('watch') or []
    if watch:
        _write(out_dir / 'watchlist.json', watchlist(root, watch, universe))
    write_json(out_dir / 'meta.json', {'built_at': stamp, 'errors': errors, 'trades': tstats.get('trades'), 'signals': len(signals)})
    return {'status': 'ok' if not errors else 'partial', 'errors': errors, 'trades': tstats.get('trades'), 'signals': len(signals),
            'securities': (flows or {}).get('windows', {}).get('quarter', {}).get('securities')}


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(path)


if __name__ == '__main__':
    import sys
    r = publish(Path(__file__).resolve().parents[1] / 'docs' / 'data', force='--force' in sys.argv)
    print(r)
