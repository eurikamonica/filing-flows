"""Holdings crowding from 13F: how many managers own each stock and how many make it one of their biggest bets, quarter by
quarter — the inputs of the crowding views and videos (13F holdings tab, crowding.js → market/crowding.json).

One pass over every manager's cached 13F reports (market.scan_13f's `see` hook, beside cross-holdings): for each quarter
and stock (common shares, no options; ETFs and other funds left out), the managers holding it, the managers whose ten
largest stock positions include it (only managers with 20 or more stock positions count, so a five-stock filer does not
make five "top-ten" bets), and the value held.

Each quarter, for the stocks at least MIN_HOLDERS managers hold:
  breadth     managers holding ÷ managers that filed
  top share   managers with it among their ten largest stock positions ÷ managers with 20+ stock positions
  score       100 × √(breadth × top share): 0–100, 100 = every manager holds it as a top-ten position. An absolute level,
              so a rise means more managers piled in — not that other stocks fell back.
  conviction  (shown, not scored) top-ten holders ÷ its holders with 20+ stock positions
Sectors are added up in the browser (the site's sector map), weighted by the value held.
"""
from __future__ import annotations

import datetime as dt
import heapq
import math
from collections import defaultdict

MIN_HOLDERS = 20        # a stock needs this many holders to be scored
KEEP_ROWS = 10          # holders a stock needs in some quarter to be published at all
TOP = 10                # the "top-ten" of a manager's stock positions
MIN_BOOK = 20           # stock positions a manager needs for its top ten to count


class Gather:
    """The see-hook of market.scan_13f: per quarter and CUSIP [holders, holders among managers with MIN_BOOK+ stock
    positions, of whom TOP-ten holders, value held]; per quarter [managers, managers with MIN_BOOK+, stock value]."""

    def __init__(self, is_fund, keep_after=None):
        self.is_fund = is_fund
        today = dt.date.today()
        self.keep_after = keep_after or dt.date(today.year - 3, 12, 31).isoformat()
        self.per = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0.0]))
        self.tot = defaultdict(lambda: [0, 0, 0.0])
        self.issuer = {}

    def see(self, m):
        for s in m.get('snapshots') or []:
            period = s.get('period') or ''
            if not s.get('complete') or period <= self.keep_after:
                continue
            book = defaultdict(float)
            for p in s.get('positions') or []:
                c = p.get('cusip')
                if not c or p.get('put_call') != 'NONE' or p.get('share_type') != 'SH' or self.is_fund(c):
                    continue
                v = p.get('value_usd') or 0
                if v > 0:
                    book[c] += v
                    if c not in self.issuer and p.get('issuer'):
                        self.issuer[c] = p['issuer']
            if not book:
                continue
            big = len(book) >= MIN_BOOK
            top = set(heapq.nlargest(TOP, book, key=book.get)) if big else ()
            t = self.tot[period]
            t[0] += 1
            t[1] += big
            t[2] += sum(book.values())
            per = self.per[period]
            for c, v in book.items():
                a = per[c]
                a[0] += 1
                if big:
                    a[1] += 1
                    a[2] += c in top
                a[3] += v


def periods_of(gather, coverage=None):
    """The quarters to score: those most managers have filed (60% of the best-covered quarter, as market.pick_periods)."""
    n = {p: t[0] for p, t in gather.tot.items()}
    if coverage:
        n = {p: coverage.get(p, v) for p, v in n.items()}
    if not n:
        return []
    best = max(n.values())
    return sorted(p for p, v in n.items() if v >= 0.6 * best)


def build(gather, cusip_ticker, names=None, coverage=None, stamp=None):
    """market/crowding.json: per quarter the managers and the stock value they filed; per ticker (stocks KEEP_ROWS+
    managers hold in some quarter) holders, top-ten holders, value held ($ millions) and the score, one value a quarter
    (null when not held or not scored)."""
    periods = periods_of(gather, coverage)
    if not periods:
        return None
    rows = defaultdict(lambda: [[None] * len(periods) for _ in range(5)])   # holders, top10, usd $M, score, conviction
    by_ticker = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0.0]))
    for k, p in enumerate(periods):
        for c, a in gather.per[p].items():
            t = cusip_ticker.get(c)
            if not t:
                continue
            b = by_ticker[p][t]                 # two CUSIPs of one ticker (a re-issued line): added together
            for i in range(4):
                b[i] += a[i]
    for k, p in enumerate(periods):
        mgrs, big = gather.tot[p][0] or 1, gather.tot[p][1]
        for t, a in by_ticker[p].items():
            if a[0] < KEEP_ROWS and not any(by_ticker[q].get(t, (0,))[0] >= KEEP_ROWS for q in periods):
                continue
            r = rows[t]
            r[0][k] = a[0]
            r[1][k] = a[2]
            r[2][k] = round(a[3] / 1e6, 1)
            r[3][k] = round(100 * math.sqrt(a[0] / mgrs * a[2] / big), 1) if a[0] >= MIN_HOLDERS and big else None
            r[4][k] = round(a[2] / a[1], 4) if a[1] >= MIN_HOLDERS // 2 else None     # too few large books to tell
    names = names or (lambda t: '')
    return {'generated_at': stamp or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'periods': periods,
            'managers': [gather.tot[p][0] for p in periods],
            'managers_big': [gather.tot[p][1] for p in periods],
            'stock_usd': [round(gather.tot[p][2] / 1e6) for p in periods],
            'fields': ['holders', 'top10', 'usd_m', 'score', 'conviction'],
            'rows': dict(sorted(rows.items())),
            'names': {t: (names(t) or '')[:40] for t in sorted(rows)},
            'params': {'min_holders': MIN_HOLDERS, 'top': TOP, 'min_book': MIN_BOOK},
            'note': ('13F crowding, each quarter: breadth = managers holding ÷ managers that filed; top share = managers whose '
                     f'{TOP} largest stock positions include it ÷ managers with {MIN_BOOK}+ stock positions; score = 100 × '
                     f'√(breadth × top share), 0–100 (100 = every manager holds it as a top-{TOP} position), for the stocks at '
                     f'least {MIN_HOLDERS} managers hold. Common shares only; options, ETFs and other funds left out. '
                     'Quarter-end positions as filed, not trades.')}
