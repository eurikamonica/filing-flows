"""What happens after an 8-K, and after an insider trade: two small statistics files from the data already published.

data/event-stats.json — for every 8-K item code (1.01 material agreement, 5.02 officers and directors, 2.05 exit costs …) and
for every item combination, the stock's move over the next 1, 5 and 21 trading days after the filing, across every 8-K in
the move-odds universe (disclosures/data/research/paths/moves/n/<KEY>.json: each company's filings with the time of day;
moves/a/<KEY>.json: the daily log returns). A filing accepted after the close is measured from the next session; one
accepted before or during the session from that day's close against the previous one. The move is the stock's own and its
excess over SPY, so a market-wide day does not read as a reaction.

data/insider-stats.json — insiders' Form 4 trades scored by the smart-money module (disclosures/data/smart/t/<T>.json, each
trade's return less SPY's over the next 63 trading days), by pattern: buys and sales, by size, cluster buys (three or more
insiders buying the same stock within thirty days), repeat buyers; how often each pattern beat the market and by how much.

    python scripts/event_stats.py --site _site
"""
import argparse
import datetime as dt
import json
import math
import os
import statistics
from collections import defaultdict

HORIZONS = (1, 5, 21)
MIN_N = 12
SKIP = {'9.01', '7.01'}            # exhibits and Reg FD: never the news itself


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def decode(doc):
    """moves/a file → (days, cumulative log price index: cum[k] = log price at day k relative to day 0)"""
    if doc.get('dates'):
        days = list(doc['dates'])
    else:
        d = dt.date.fromisoformat(doc['d0'])
        days = [doc['d0']]
        for ch in doc.get('gaps') or '':
            d += dt.timedelta(days=int(ch, 36))
            days.append(d.isoformat())
    cum, s = [0.0], 0.0
    for r in doc.get('r') or []:
        s += r / 1e4
        cum.append(s)
    return days, cum[:len(days)]


def prices(doc):
    """(days, closes) with the last close pinned to doc['last'] (the returns are in whole basis points)"""
    days, cum = decode(doc)
    if not days or not doc.get('last'):
        return days, []
    end = cum[-1]
    return days, [doc['last'] * math.exp(c - end) for c in cum]


def bisect_day(days, day):
    """index of the first trading day >= day (len(days) when none)"""
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo


def reaction(days, cum, day, time, horizons=HORIZONS, spy=None):
    """the move from the last close before the news to the close h sessions later: {h: (own, excess)}; None when the
    data does not reach. time 'HH:MM' (Eastern) as EDGAR gives it; after 16:00 the first session is the next one."""
    i = bisect_day(days, day)
    if i >= len(days):
        return None
    if days[i] == day and (time or '00:00') >= '16:00':
        i += 1                                     # after the close: the reaction is the next session
    base = i - 1                                   # the close before the news
    if base < 0:
        return None
    out = {}
    for h in horizons:
        j = base + h
        if j >= len(days):
            out[h] = None
            continue
        own = cum[j] - cum[base]
        ex = None
        if spy:
            sd, sc = spy
            a, b = bisect_day(sd, days[base]), bisect_day(sd, days[j])
            if a < len(sd) and b < len(sd) and sd[a] == days[base] and sd[b] == days[j]:
                ex = own - (sc[b] - sc[a])
        out[h] = (own, ex)
    return out


def summarise(vals):
    """[(own, excess)] → counts, medians, up-share and the typical size of the move"""
    own = [math.expm1(v[0]) for v in vals if v and v[0] is not None]
    exc = [math.expm1(v[1]) for v in vals if v and v[1] is not None]
    if len(own) < MIN_N:
        return None
    r = lambda x, d=4: round(x, d)
    return {'n': len(own), 'median': r(statistics.median(own)), 'mean': r(statistics.fmean(own)), 'up': r(sum(1 for v in own if v > 0) / len(own)),
            'abs_median': r(statistics.median(abs(v) for v in own)), 'p10': r(sorted(own)[len(own) // 10]), 'p90': r(sorted(own)[-max(1, len(own) // 10)]),
            'excess_median': r(statistics.median(exc)) if exc else None, 'excess_up': r(sum(1 for v in exc if v > 0) / len(exc)) if exc else None}


ITEM_NAMES = {'1.01': 'Material definitive agreement', '1.02': 'Termination of a material agreement', '1.03': 'Bankruptcy or receivership',
              '1.04': 'Mine safety violation', '5.06': 'Change in shell company status (a SPAC merger closing)', '6.01': 'Asset-backed securities: servicer information',
              '6.02': 'Asset-backed securities: change of servicer or trustee', '6.03': 'Asset-backed securities: change in credit enhancement',
              '6.04': 'Asset-backed securities: failure to make a distribution', '6.05': 'Asset-backed securities: securities act updating',
              '1.05': 'Material cybersecurity incident', '2.01': 'Completed acquisition or disposition', '2.02': 'Results of operations',
              '2.03': 'New debt or off-balance-sheet obligation', '2.04': 'Triggering event accelerating an obligation', '2.05': 'Exit or disposal costs',
              '2.06': 'Material impairment', '3.01': 'Delisting notice or listing-rule failure', '3.02': 'Unregistered sale of equity',
              '3.03': 'Change to shareholders’ rights', '4.01': 'Change in auditor', '4.02': 'Restatement: financials not to be relied on',
              '5.01': 'Change in control', '5.02': 'Directors and officers: departures, appointments, pay', '5.03': 'Charter or bylaw amendment',
              '5.04': 'Trading-plan blackout', '5.05': 'Code of ethics change or waiver', '5.07': 'Shareholder vote results', '5.08': 'Shareholder nominations',
              '7.01': 'Regulation FD disclosure', '8.01': 'Other events', '9.01': 'Exhibits'}


def event_stats(hub, today=None):
    """the 8-K statistics: by item code, by item set and by topic, with the recent sample behind the index page"""
    mv = os.path.join(hub, 'research', 'paths', 'moves')
    spy_doc = read(os.path.join(mv, 'a', 'SPY.json'))
    spy = decode(spy_doc)[:2] if spy_doc else None
    by_item, by_set, by_topic = defaultdict(lambda: {h: [] for h in HORIZONS}), defaultdict(lambda: {h: [] for h in HORIZONS}), defaultdict(lambda: {h: [] for h in HORIZONS})
    n_events, n_companies = 0, 0
    ndir = os.path.join(mv, 'n')
    for fn in sorted(os.listdir(ndir)) if os.path.isdir(ndir) else []:
        key = fn[:-5]
        nd, ad = read(os.path.join(ndir, fn)), read(os.path.join(mv, 'a', fn))
        if not nd or not ad or ad.get('kind') not in (None, 'stock'):
            continue
        days, cum = decode(ad)
        if len(days) < 30:
            continue
        n_companies += 1
        for ev in nd.get('events') or []:
            try:
                day, time, form, items = ev[0], ev[1], ev[2], ev[3]
            except (IndexError, TypeError):
                continue
            if not str(form).startswith('8-K'):
                continue
            codes = [c.strip() for c in (items.split(',') if isinstance(items, str) else items or []) if c.strip()]
            core = [c for c in codes if c not in SKIP]
            if not core:
                continue
            rx = reaction(days, cum, day, time, spy=spy)
            if not rx:
                continue
            n_events += 1
            for h in HORIZONS:
                for c in core:
                    by_item[c][h].append(rx[h])
                by_set['+'.join(sorted(core))][h].append(rx[h])
                for t in (ev[6] if len(ev) > 6 else None) or []:
                    by_topic[t][h].append(rx[h])
    pack = lambda d: {k: {'h%d' % h: summarise(v[h]) for h in HORIZONS} for k, v in d.items() if summarise(v[1])}
    items = pack(by_item)
    for k, v in items.items():
        v['name'] = ITEM_NAMES.get(k, 'Item ' + k)
    return {'generated_at': (today or dt.date.today()).isoformat(), 'horizons': list(HORIZONS), 'events': n_events, 'companies': n_companies,
            'note': 'Each 8-K in the move-odds universe, measured from the last close before it was accepted by EDGAR (a filing after 16:00 ET counts from '
                    'the next session) to the close 1, 5 and 21 sessions later. Excess is the move less SPY’s over the same days. Items 9.01 and 7.01 '
                    'are not counted as the news. Not investment advice.',
            'items': items, 'sets': {k: v for k, v in pack(by_set).items() if v['h1']['n'] >= 40}, 'topics': pack(by_topic)}


def insider_stats(hub, today=None):
    """insiders' scored Form 4 trades by pattern (the smart-money module's per-stock files)"""
    tdir = os.path.join(hub, 'smart', 't')
    pats = defaultdict(list)                 # pattern → [(excess 63d, d)]
    n_trades, n_stocks = 0, 0
    for fn in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        d = read(os.path.join(tdir, fn))
        if not d or not d.get('trades'):
            continue
        F = d.get('trade_fields') or ['date', 'actor', 'name', 'group', 'd', 'size', 'ex', 'ex2', 'follow', 'known']
        ins = [dict(zip(F, t)) for t in d['trades'] if len(t) >= 7 and t[3] == 'ins']
        if not ins:
            continue
        n_stocks += 1
        ins.sort(key=lambda t: t['date'])
        buys = [t for t in ins if t['d'] > 0]
        seen = defaultdict(int)
        for t in ins:
            if t.get('ex') is None:
                continue
            n_trades += 1
            side = 'buy' if t['d'] > 0 else 'sell'
            ex = t['ex'] if side == 'buy' else -t['ex']           # a sale is right when the stock lags
            usd = t.get('size') or 0
            pats[side].append(ex)
            pats[side + ('_large' if usd >= 1e6 else '_mid' if usd >= 1e5 else '_small')].append(ex)
            if side == 'buy':
                d0 = dt.date.fromisoformat(t['date'])
                others = {b['actor'] for b in buys if b['actor'] != t['actor'] and abs((dt.date.fromisoformat(b['date']) - d0).days) <= 30}
                pats['buy_cluster' if len(others) >= 2 else 'buy_lone'].append(ex)
                pats['buy_repeat' if seen[t['actor']] else 'buy_first'].append(ex)
            seen[t['actor']] += 1
    LABEL = {'buy': 'All insider buys', 'sell': 'All insider sales (right when the stock then lags)', 'buy_small': 'Buys under $100k', 'buy_mid': 'Buys $100k–$1M',
             'buy_large': 'Buys of $1M or more', 'sell_small': 'Sales under $100k', 'sell_mid': 'Sales $100k–$1M', 'sell_large': 'Sales of $1M or more',
             'buy_cluster': 'Cluster buys: three or more insiders within 30 days', 'buy_lone': 'A single insider buying', 'buy_repeat': 'Repeat buyer (bought this stock before)',
             'buy_first': 'First buy of this stock on file'}
    out = {}
    for k, xs in pats.items():
        if len(xs) < MIN_N:
            continue
        out[k] = {'label': LABEL.get(k, k), 'n': len(xs), 'hit': round(sum(1 for x in xs if x > 0) / len(xs), 4), 'median_excess': round(statistics.median(xs), 4),
                  'mean_excess': round(statistics.fmean(xs), 4)}
    return {'generated_at': (today or dt.date.today()).isoformat(), 'horizon_days': 63, 'trades': n_trades, 'stocks': n_stocks,
            'note': 'Insiders’ open-market Form 4 trades over the last 400 days with a scored outcome: the stock’s return less SPY’s over the 63 trading days '
                    'after the trade. A buy is a hit when the stock beat the market; a sale when it lagged. Dollar sizes are the filer’s. Not investment advice.',
            'patterns': out}


def write(site, today=None):
    hub = os.path.join(site, 'disclosures', 'data')
    os.makedirs(os.path.join(site, 'data'), exist_ok=True)
    ev = event_stats(hub, today)
    with open(os.path.join(site, 'data', 'event-stats.json'), 'w', encoding='utf-8') as f:
        json.dump(ev, f, separators=(',', ':'))
    ins = insider_stats(hub, today)
    with open(os.path.join(site, 'data', 'insider-stats.json'), 'w', encoding='utf-8') as f:
        json.dump(ins, f, separators=(',', ':'))
    return ev, ins


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    a = ap.parse_args()
    ev, ins = write(a.site)
    print(f"event stats: {ev['events']} 8-Ks from {ev['companies']} companies, {len(ev['items'])} items, {len(ev['sets'])} item sets; "
          f"insider stats: {ins['trades']} scored trades, {len(ins['patterns'])} patterns")
