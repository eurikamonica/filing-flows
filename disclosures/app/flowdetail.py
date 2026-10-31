"""Detailed Sankey: every flow of a company's income statement and cash flow statement, split as far as the filing and its
notes go — beside the standard chart on the company page (web/flowdetail.js), never instead of it.

For each 10-Q / 10-K (app/xbrl_filing.py reads its XBRL in full):
  structure  the statements' own calculation trees (total = Σ weight × part, as the company filed them): net income ←
             pre-tax income ← operating income ← gross profit ← revenue, each with what it subtracts and adds; then each
             line the statement shows as one figure is split further where a note's calculation tree does it and its
             parts add up to the line in the same period (other income → interest income, interest expense, gains on
             investments …; income tax → current and deferred, federal, state and foreign; operating expenses → their
             lines); revenue by the filing's products and services, else its segments, else its regions (a dimension
             whose members add up to total revenue; nested members kept: Data Center = Compute + Networking), cost of
             revenue on the same members when they add up. The cash flow statement the same way: net income → operating
             cash flow (each non-cash item and working-capital line), and operating cash flow, with the investing and
             financing lines and what was added to or drawn from cash.
  flows      every calculation is one junction of the Sankey (its total and its parts meet there). Which parts flow in and
             which flow out follows from the weights: the income statement's last line (net income) is the root, and a
             part's junction is oriented as the root times the signs of the weights on the way to it — so revenue flows
             into gross profit, costs flow out of it, a cost's own parts flow out of the cost, and a loss funds the costs
             it did not cover. Within a junction the flows are filled in order (the main inflow first), so every node's
             inflows equal its outflows. Small parts (under 0.3% of revenue) are summed into "Other …".
  periods    the quarter (three months; the cash flow statement, year to date in a 10-Q, less the previous 10-Q's year to
             date; a fourth quarter = the 10-K's year less the third quarter's nine months), the quarter before (Q/Q) and
             the same quarter a year earlier (Y/Y, the filing's own comparative columns); each fiscal year from its 10-K
             with the year before.

The result is a spec in the format web/sankey.js draws (nodes with column, colour role, label lines, values now / Q/Q /
Y/Y; links the same), with the site's ids on the main lines (revenue, cor, gp, opex, oi, pretax, tax, net, ocf) so the
guidance comparison (web/guidance.js versus) works on it as on the standard chart.

  python flowdetail.py one --cik 1045810 --out <dir> [--ticker NVDA]
  python flowdetail.py collect --root <branch> --site-index <index.json> --minutes 40
  python flowdetail.py index --root <branch>
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbrl_filing as X
import notes as N

VERSION = 1
FOLD = 0.003                 # parts under 0.3% of revenue are summed into "Other …" (per junction and side)
MAX_PARTS = 9                # at most this many parts per side of a junction; the smallest beyond it are summed too
NOTE_DEPTH = 2               # a line split by a note, its parts by another note: this many levels at most

# the site's ids for the main lines (pipeline/sankey.py): the guidance comparison and the colours rest on them
MAIN = [
    ('revenue', ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax',
                 'SalesRevenueNet', 'RevenuesNetOfInterestExpense', 'SalesRevenueGoodsNet', 'SalesRevenueServicesNet']),
    ('cor', ['CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold', 'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization']),
    ('gp', ['GrossProfit']),
    ('opex', ['OperatingExpenses']),
    ('costs', ['CostsAndExpenses', 'OperatingCostsAndExpenses', 'BenefitsLossesAndExpenses']),
    ('oi', ['OperatingIncomeLoss']),
    ('nonop', ['NonoperatingIncomeExpense']),
    ('pretax', ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic', 'IncomeLossBeforeIncomeTaxes']),
    ('tax', ['IncomeTaxExpenseBenefit', 'IncomeTaxesPaidNet']),
    ('net', ['NetIncomeLoss', 'ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'IncomeLossFromContinuingOperations']),
    ('ocf', ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']),
    ('icf', ['NetCashProvidedByUsedInInvestingActivities', 'NetCashProvidedByUsedInInvestingActivitiesContinuingOperations']),
    ('fincf', ['NetCashProvidedByUsedInFinancingActivities', 'NetCashProvidedByUsedInFinancingActivitiesContinuingOperations']),
    ('capex', ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets']),
    ('cash_chg', ['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect',
                  'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect',
                  'CashAndCashEquivalentsPeriodIncreaseDecrease', 'CashPeriodIncreaseDecrease']),
]
MAIN_OF = {loc: k for k, locs in MAIN for loc in locs}
SHORT = {'revenue': 'revenue', 'gp': 'gross profit', 'opex': 'opex', 'costs': 'costs', 'oi': 'operating profit', 'pretax': 'pre-tax',
         'net': 'net earnings', 'ocf': 'OCF', 'cor': 'cost of revenue', 'tax': 'income tax', 'nonop': 'other income',
         'icf': 'investing', 'fincf': 'financing', 'cash_chg': 'cash'}
NAMES = {'revenue': 'Revenue', 'gp': 'Gross profit', 'oi': 'Operating profit', 'pretax': 'Pre-tax earnings', 'net': 'Net earnings',
         'ocf': 'Operating cash flow', 'icf': 'Investing activities', 'fincf': 'Financing activities', 'tax': 'Income tax',
         'cor': 'Cost of revenue', 'opex': 'Operating expenses'}
# a calculation that bridges to a line instead of splitting it (statutory tax → effective tax)
BRIDGE = re.compile(r'(?:IncomeTaxReconciliation|EffectiveIncomeTaxRateReconciliation|IncomeTaxExpenseBenefitContinuingOperationsIncomeTaxReconciliation)')
REV_AXES = ['srt:ProductOrServiceAxis', 'us-gaap:StatementBusinessSegmentsAxis', 'srt:StatementGeographicalAxis']
AXIS_WORD = {'srt:ProductOrServiceAxis': 'products and services', 'us-gaap:StatementBusinessSegmentsAxis': 'segments',
             'srt:StatementGeographicalAxis': 'regions'}


def _d(s):
    return dt.date.fromisoformat(s[:10])


def local(c):
    return c.split(':')[-1]


def key_of(c, dims=()):
    return c + ''.join(f'|{a}={m}' for a, m in sorted(dims))


def parse_key(k):
    """'us-gaap:Revenues|srt:ProductOrServiceAxis=nvda:DataCenterMember' → (concept, ((axis, member),)); a cash flow
    statement line is prefixed 'cf>' (the same concept can be a line of both statements: gains on investments)."""
    if k.startswith('cf>'):
        k = k[3:]
    c, *ds = k.split('|')
    return c, tuple(tuple(d.split('=', 1)) for d in ds)


# ------------------------------------------------------------------ periods of one filing
def periods(FL):
    """{'cur', 'ytd', 'py', 'pytd'} → ('d', start, end) of the filing: the quarter (or year) it reports, its year to date,
    and the same two a year earlier; 'annual' when the filing reports a fiscal year."""
    dpe = next((f['v'] for f in FL.F['facts'] if f['c'] == 'dei:DocumentPeriodEndDate' and isinstance(f['v'], str)), None)
    form = next((f['v'] for f in FL.F['facts'] if f['c'] == 'dei:DocumentType' and isinstance(f['v'], str)), '') or ''
    durs = sorted({(c['s'], c['e']) for c in FL.ctx.values() if 's' in c and not c['dims']})
    if not durs:
        return None
    if dpe:
        try:
            e0 = _d(dpe)
        except ValueError:
            e0 = None
        ends = [e for _, e in durs if e0 and abs((_d(e) - e0).days) <= 7]
        end = max(ends, key=lambda e: sum(1 for s, x in durs if x == e)) if ends else None
    else:
        end = None
    if not end:
        end = max(e for _, e in durs)
    at = [(s, e) for s, e in durs if e == end]
    days = lambda p: (_d(p[1]) - _d(p[0])).days
    annual = form.upper().startswith('10-K') or not any(80 <= days(p) <= 100 for p in at)
    cur = next((p for p in at if (330 <= days(p) <= 380 if annual else 80 <= days(p) <= 100)), None)
    if not cur:
        return None
    # year to date: the longest period ending with the quarter, a twelve-month column left out (Amazon shows one)
    ytd = max((p for p in at if days(p) <= 285), key=days) if not annual else cur

    def year_ago(p):
        e1 = _d(p[1]) - dt.timedelta(days=364)
        c = [(s, e) for s, e in durs if abs((_d(e) - e1).days) <= 10 and abs(days((s, e)) - days(p)) <= 10]
        return min(c, key=lambda x: abs((_d(x[1]) - e1).days)) if c else None
    out = {'cur': ('d',) + cur, 'ytd': ('d',) + ytd}
    py, pytd = year_ago(cur), year_ago(ytd)
    out['py'] = ('d',) + py if py else None
    out['pytd'] = ('d',) + pytd if pytd else None
    out['annual'] = annual
    out['form'] = form or ('10-K' if annual else '10-Q')
    focus = next((f['v'] for f in FL.F['facts'] if f['c'] == 'dei:DocumentFiscalPeriodFocus' and isinstance(f['v'], str)), '') or ''
    m = re.match(r'Q([1-3])$', focus.strip().upper())
    out['fq'] = 4 if annual else int(m.group(1)) if m else max(1, min(3, round(days(ytd) / 91.3)))
    return out


# ------------------------------------------------------------------ the statements' trees, split further by the notes
class Tree:
    """Junctions {sum key: {'kids': [(key, weight)], 'via': where the split comes from}} on one filing, rooted at net income
    (and operating cash flow, for the cash part)."""

    def __init__(self, FL, P):
        self.FL, self.P = FL, P
        self.J, self.via, self.seen = {}, {}, set()
        st, notes = N.classify_reports(FL)
        self.st = {s['kind']: s['report'] for s in st if s['kind'] not in ()}
        self.titles = {}
        for n in notes:
            t = N.title_of(FL, n['report'])
            self.titles[n['report']['role']] = t
            for r in n['details'] + n['tables']:
                self.titles[r['role']] = t + ' — ' + re.sub(r'^.*?-\s*', '', N.title_of(FL, r)) if ' - ' in N.title_of(FL, r) else t
        self.stmt_title = {s['report']['role']: N.title_of(FL, s['report']) for s in st}

    def v(self, key, p):
        if p is None:
            return None
        c, dims = parse_key(key)
        return self.FL.v(c, p, dims)

    def tol(self, key, p):
        c, dims = parse_key(key)
        g = self.FL.get(c, p, dims)
        return N.Filing.tol_of(g[1]) if g else 0.0

    def ties(self, total, kids, p):
        """The parts add up to the total in period p (within their rounding), with two or more of them non-zero."""
        tv = self.v(total, p)
        if tv is None:
            return False
        s, n, tol = 0.0, 0, self.tol(total, p)
        for k, w in kids:
            x = self.v(k, p)
            if x is None:
                continue
            s += w * x
            tol += self.tol(k, p)
            n += x != 0
        return n >= 2 and abs(s - tv) <= max(tol * 1.01, abs(tv) * 0.0015, 1.0)

    def add(self, total, kids, via):
        self.J[total] = {'kids': kids, 'via': via}
        self.seen.update(k for k, _ in kids)
        self.seen.add(total)

    def grow(self, role, root, p, depth=0, note_depth=0):
        """Expand root by the statement's calculation (role), else a note's; then each part the same way."""
        cal = self.FL.F['cal']
        c, dims = parse_key(root)
        kids, via = None, None
        if not dims and role in cal and c in cal[role]:
            cand = [(key_of(k), w) for k, w in cal[role][c] if key_of(k) not in self.seen]
            have = [(k, w) for k, w in cand if self.v(k, p) is not None]
            if self.ties(root, have, p):
                kids, via = have, self.stmt_title.get(role, 'the statement')
            elif len(cand) - len(have) == 1 and have and self.v(root, p) is not None:
                # one line the statement shows only with a dimension (Caterpillar's interest expense "excluding Financial
                # Products"): what the others leave of the total, the statement's own sum
                (mk, mw), = [(k, w) for k, w in cand if self.v(k, p) is None]
                r = (self.v(root, p) - sum(w * self.v(k, p) for k, w in have)) / mw
                if r and abs(r) <= 5 * abs(self.v(root, p)) + 1:
                    kids, via = cand, self.stmt_title.get(role, 'the statement')
        if kids is None and not dims and note_depth < NOTE_DEPTH:
            best = None
            for r, tree in cal.items():
                if r == role or r in self.stmt_title or c not in tree:
                    continue
                cand = [(key_of(k), w) for k, w in tree[c]]
                if any(k in self.seen for k, _ in cand) or any(BRIDGE.match(local(k)) for k, _ in cand):
                    continue
                cand = [(k, w) for k, w in cand if self.v(k, p) is not None]
                if not self.ties(root, cand, p):
                    continue
                nz = sum(1 for k, _ in cand if self.v(k, p))
                if not best or nz > best[0]:
                    best = (nz, cand, self.titles.get(r) or self.role_title(r))
            if best:
                kids, via = best[1], best[2]
                note_depth += 1
                if MAIN_OF.get(local(c)) == 'tax':
                    note_depth = NOTE_DEPTH          # income tax: one split (federal, state, foreign or current, deferred)
        if kids is None:
            return
        self.add(root, kids, via)
        for k, _ in kids:
            self.grow(role, k, p, depth + 1, note_depth if via != self.stmt_title.get(role) else 0)

    def role_title(self, r):
        t = (self.FL.F.get('roles') or {}).get(r) or r.rsplit('/', 1)[-1]
        return re.sub(r'^\s*\d+\s*-\s*(Statement|Disclosure|Document|Schedule)\s*-\s*', '', t).strip()

    # revenue (and cost of revenue) by the members of one dimension
    def members(self, c, p, axis):
        out = {}
        for (cc, pk, dims), (v, _, _) in self.FL.num.items():
            if cc == c and pk == p and len(dims) == 1 and dims[0][0] == axis and v is not None:
                out[dims[0][1]] = v
        return out

    def split_dims(self, total, p, axes=REV_AXES, need_axis=None):
        """(axis, junctions) splitting total by one dimension's members, nested members as groups; or None."""
        c, dims = parse_key(total)
        if dims:
            return None
        tv = self.v(total, p)
        if not tv:
            return None
        cands = [c] + [x for x in self.FL.by_c if local(x) in dict(MAIN)['revenue']] if MAIN_OF.get(local(c)) == 'revenue' else [c]
        for axis in ([need_axis] if need_axis else axes):
            for cc in dict.fromkeys(cands):
                tot = self.FL.v(cc, p)                      # another revenue concept may carry only the split (Alphabet)
                if tot is not None and abs(tot - tv) > max(abs(tv) * 0.0015, 1.0):
                    continue
                m = {k: v for k, v in self.members(cc, p, axis).items() if v and not k.endswith('Domain')}
                if not 2 <= len(m) <= 30:
                    continue
                got = _nest(m, tv)
                gap = False
                if not got and axis != 'srt:ProductOrServiceAxis':
                    # segments that leave a little out (hedging gains, corporate): the rest as one more part
                    s_ = sum(m.values())
                    if 0 < abs(tv - s_) <= abs(tv) * 0.03 and all(v > 0 for v in m.values()):
                        got, gap = (list(m), {}), True
                if got:
                    top, groups = got
                    J = {}
                    mk = lambda x: key_of(cc, ((axis, x),))
                    J[total] = [(mk(x), 1.0) for x in top] + ([('gap:' + total, 1.0)] if gap else [])
                    for g, parts in groups.items():
                        J[mk(g)] = [(mk(x), 1.0) for x in parts]
                    return axis, cc, J
        return None


def _nest(m, total, tol_r=0.0015):
    """Members (name → value) → (top level, {group: parts}) whose top level adds up to total; a member equal to the sum of
    two or more others is their group (Data Center = Compute + Networking). None when nothing adds up."""
    tol = max(abs(total) * tol_r, 1.0)
    items = sorted(m.items(), key=lambda x: -abs(x[1]))
    if len(items) > 18:
        items = items[:18]
    names = [k for k, _ in items]
    val = dict(items)
    # duplicates (the same figure under two members): keep the first
    seen, uniq = {}, []
    for k in names:
        if any(abs(val[k] - val[u]) <= tol * 0.1 and val[k] == val[u] for u in uniq if u in seen):
            continue
        seen[k] = True
        uniq.append(k)
    names = uniq
    if abs(sum(val[k] for k in names) - total) <= tol:
        return names, {}
    groups = {}
    used = set()
    for g in names:
        rest = [k for k in names if k != g and k not in groups and abs(val[k]) < abs(val[g]) and k not in used]
        sub = _subset(rest, val, val[g], max(abs(val[g]) * tol_r, 1.0))
        if sub and len(sub) >= 2:
            groups[g] = sub
            used.update(sub)
    top = [k for k in names if k not in used]
    if groups and abs(sum(val[k] for k in top) - total) <= tol:
        return top, groups
    return None


def _subset(names, val, target, tol, limit=12):
    names = names[:limit]
    best = None
    n = len(names)
    for mask in range(1, 1 << n):
        s = 0.0
        pick = []
        for i in range(n):
            if mask >> i & 1:
                s += val[names[i]]
                pick.append(names[i])
        if abs(s - target) <= tol and (best is None or len(pick) > len(best)):
            best = pick
    return best


def _find(FL, role, locs, p):
    """The first of these concepts the statement presents (or the filing has) with a figure in period p."""
    pres = [nd['c'] for nd in FL.F['pre'].get(role, [])] if role else []
    for loc in locs:
        for c in pres:
            if local(c) == loc and FL.v(c, p) is not None:
                return c
    for loc in locs:
        for c in FL.by_local.get(loc, []):
            if FL.v(c, p) is not None:
                return c
    return None


def read_filing(FL):
    """One filing → its structure and its figures: {'periods', 'J' (junctions), 'via', 'labels', 'vals': {period: {key: v}},
    'root', 'cash_root', 'axis'}; None when the statements cannot be read."""
    P = periods(FL)
    if not P:
        return None
    T = Tree(FL, P)
    # a combined "statement of income and comprehensive income" is listed as comprehensive income (notes.py)
    isr, cfr = (T.st.get('is') or T.st.get('oci') or {}).get('role'), (T.st.get('cf') or {}).get('role')
    if not isr:
        return None
    cur, ytd = P['cur'], P['ytd']
    cal = FL.F['cal']
    # the root: net income, the statement's top-most calculation total
    root = None
    for loc in dict(MAIN)['net']:
        c = _find(FL, isr, [loc], cur)
        if c and (c in cal.get(isr, {}) or root is None):
            root = c
            if c in cal.get(isr, {}):
                break
    if not root:
        return None
    rk = key_of(root)
    T.seen.add(rk)
    T.grow(isr, rk, cur)
    # a statement without a calculation down to revenue: the standard lines, where the filing has them
    if not any(main_of(k) == 'revenue' for j in T.J.values() for k, _ in j['kids']):
        _skeleton(T, FL, isr, rk, cur)
    rev = next((k for j in T.J.values() for k, _ in j['kids'] if main_of(k) == 'revenue'), None)
    axis = None
    if rev and rev in T.J:                         # revenue split by the statement (sales + other income): its sales by members
        big = max((k for k, w in T.J[rev]['kids'] if w > 0 and main_of(k) == 'revenue' and k not in T.J),
                  key=lambda k: abs(T.v(k, cur) or 0), default=None)
        if big and abs(T.v(big, cur) or 0) >= 0.6 * abs(T.v(rev, cur) or 1):
            rev = big
    if rev and rev not in T.J:
        got = T.split_dims(rev, cur)
        if got:
            axis, cc, J = got
            for t, kids in J.items():
                T.add(t, kids, 'dims:' + axis)
    # cost of revenue on the same members
    cor = next((k for j in T.J.values() for k, _ in j['kids'] if main_of(k) == 'cor'), None)
    if axis and cor and cor not in T.J:
        m = T.members(parse_key(cor)[0], cur, axis)
        if m and len(m) <= 12:
            got = _nest({k: v for k, v in m.items() if v}, T.v(cor, cur))
            if got and not got[1]:
                T.add(cor, [(key_of(parse_key(cor)[0], ((axis, x),)), 1.0) for x in got[0]], 'dims:' + axis)
    # the cash flow statement (a 10-Q's is year to date): net income → operating cash flow → the rest of the cash flows
    cash_root = None
    if cfr:
        ck = None
        for loc in dict(MAIN)['cash_chg']:
            c = _find(FL, cfr, [loc], ytd)
            if c and c in cal.get(cfr, {}):
                ck = key_of(c)
                break
        ok = None
        for loc in dict(MAIN)['ocf']:
            c = _find(FL, cfr, [loc], ytd)
            if c:
                ok = key_of(c)
                break
        if ok:
            T2 = Tree.__new__(Tree)
            T2.__dict__.update(T.__dict__)
            T2.J, T2.seen = {}, set()
            if ck:
                T2.seen.add(ck)
                T2.grow(cfr, ck, ytd, note_depth=NOTE_DEPTH)
            if ok not in T2.J:
                T2.seen.add(ok)
                T2.grow(cfr, ok, ytd, note_depth=NOTE_DEPTH)
            depth, todo = {ck or ok: 0}, [ck or ok]
            while todo:
                t = todo.pop(0)
                for k, _ in T2.J.get(t, {}).get('kids', []):
                    if k not in depth:
                        depth[k] = depth[t] + 1
                        todo.append(k)
            od = depth.get(ok, 0)
            for t in list(T2.J):
                d = depth.get(t, 0)
                under_ocf = t != ok and _under(T2.J, ok, t)
                if t != ok and t != ck and (d >= 2 and not under_ocf or under_ocf and d - od >= 2):
                    del T2.J[t]
            # the net income in operating cash flow is the income statement's (ProfitLoss there, NetIncomeLoss here …)
            nis = [k for k, _ in T2.J.get(ok, {}).get('kids', []) if MAIN_OF.get(local(k)) == 'net']
            if ok in T2.J and nis:
                ni = nis[0]
                in_is = ni in T.J or any(k == ni for j in T.J.values() for k, _ in j['kids'])
                same = abs((T.v(ni, cur) or 0) - (T.v(rk, cur) or 0)) <= max(abs(T.v(rk, cur) or 0) * 0.0015, 1.0)
                if in_is or same:
                    if in_is and ni != rk:
                        rk = ni                  # the flows start where the cash flow statement picks net income up
                    top = ck if ck in T2.J and any(k == ok for k, _ in T2.J[ck]['kids']) else ok
                    cf = lambda k: k if k == ni else 'cf>' + k
                    for t, j in T2.J.items():
                        if t != ni:
                            T.J[cf(t)] = {'kids': [(cf(k), w) for k, w in j['kids']], 'via': j['via']}
                    cash_root = cf(top)
                    T.cash_ni = ni
    keys = set(T.J) | {k for j in T.J.values() for k, _ in j['kids']}
    vals = {}
    for name in ('cur', 'ytd', 'py', 'pytd'):
        p = P.get(name)
        vals[name] = {k: T.v(k, p) for k in keys} if p else {}
        vals[name] = {k: v for k, v in vals[name].items() if v is not None}
        _residuals(T.J, vals[name])
    labels = {}
    for k in keys:
        c, dims = parse_key(k)
        labels[k] = ('Other (outside the split)' if k.startswith('gap:') else FL.label(dims[-1][1]) if dims else tidy(FL.label(c, 'terse')))
    return {'periods': {k: (list(v[1:]) if isinstance(v, tuple) else v) for k, v in P.items()}, 'J': {t: j['kids'] for t, j in T.J.items()},
            'via': {t: j['via'] for t, j in T.J.items()}, 'labels': labels, 'vals': vals, 'root': rk, 'cash_root': cash_root,
            'cash_ni': getattr(T, 'cash_ni', None), 'axis': axis}


def tidy(label):
    """A line's label as a chart shows it: "Increase (Decrease) in Accounts Receivable" → "Accounts receivable"."""
    t = re.sub(r'(?i)^\s*(?:\(?increase\)?\s*(?:\(?decrease\)?)?|\(?decrease\)?\s*\(?increase\)?|changes?)\s*(?:/\s*decrease\s*)?(?:in|of)\s+', '', label or '')
    t = re.sub(r'(?i)^net cash (?:provided by|used in|provided by \(used in\)|\(used in\) provided by|from)\s*(?:\(used in\)\s*)?', '', t)
    t = re.sub(r'(?i),?\s*net of cash acquired$', '', t).strip(' ,:')
    t = re.sub(r'(?i),?\s*continuing operations$', '', t)
    t = re.sub(r'(?i)\b(income tax(?:es)?|tax(?:es)?)\s+expense\s*\(benefit\)', r'\1', t)
    t = re.sub(r'(?i)\s*expense\s*\(benefit\)|\s*\(benefit\)', '', t).strip(' ,')
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    ws = t.split()
    long = [w for w in ws[1:] if len(w) >= 3 and w.lower() not in ('and', 'the', 'for', 'net', 'per')]
    if long and all(w[0].isupper() for w in long):        # Title Case → sentence case ("Accounts Receivable"), acronyms kept
        t = ' '.join([ws[0]] + [w.lower() if w[:1].isupper() and w[1:].islower() else w for w in ws[1:]])
    return t or label


def _residuals(J, vals):
    """A part with no figure of its own in a junction whose total and other parts have one: what they leave."""
    for _ in range(4):
        ch = False
        for t, j in J.items():
            kids = j['kids'] if isinstance(j, dict) else j
            miss = [(k, w) for k, w in kids if k not in vals]
            if t in vals and len(miss) == 1 and len(kids) >= 2:
                (k, w), = miss
                vals[k] = (vals[t] - sum(ww * vals[x] for x, ww in kids if x in vals)) / w
                ch = True
        if not ch:
            break


def _under(J, top, k):
    """k is somewhere below top in the junctions J."""
    todo, seen = [top], set()
    while todo:
        t = todo.pop()
        for x, _ in J.get(t, {}).get('kids', []):
            if x == k:
                return True
            if x not in seen:
                seen.add(x)
                todo.append(x)
    return False


def _skeleton(T, FL, isr, rk, p):
    """A statement whose calculation does not reach revenue: net income ← pre-tax ← operating income ← gross profit ←
    revenue from the standard lines, each step kept only where it adds up."""
    f = lambda k: (lambda c: key_of(c) if c else None)(_find(FL, isr, dict(MAIN)[k], p))
    rev, cor, gp, oi, pre, tax = (f(k) for k in ('revenue', 'cor', 'gp', 'oi', 'pretax', 'tax'))
    steps = []
    if pre and tax and rk not in T.J:
        steps.append((rk, [(pre, 1.0), (tax, -1.0)]))
    if oi and pre and pre not in T.J:
        nonop = f('nonop')
        steps.append((pre, [(oi, 1.0)] + ([(nonop, 1.0)] if nonop else [])))
    if gp and oi and oi not in T.J:
        ox = f('opex')
        if ox:
            steps.append((oi, [(gp, 1.0), (ox, -1.0)]))
    elif rev and oi and oi not in T.J:
        cx = f('costs')
        if cx:
            steps.append((oi, [(rev, 1.0), (cx, -1.0)]))
    if rev and cor and gp and gp not in T.J:
        steps.append((gp, [(rev, 1.0), (cor, -1.0)]))
    for t, kids in steps:
        if T.ties(t, kids, p) or (len(kids) == 1 and abs((T.v(kids[0][0], p) or 0) - (T.v(t, p) or 0)) <= 1):
            if len(kids) == 1:
                continue
            T.add(t, kids, 'the statement (standard lines)')
            for k, _ in kids:
                T.grow(isr, k, p)


# ------------------------------------------------------------------ periods of a company: quarters and years
def quarter_values(F, prev):
    """The three-month figures of filing F (read_filing) with the filing before it in the same fiscal year (prev, or None):
    the income statement's own quarter; the cash flow statement's year to date less prev's. → (now, year ago) {key: v}."""
    cur, py = dict(F['vals']['cur']), dict(F['vals'].get('py') or {})
    cash = cash_keys(F)
    fq = F['periods']['fq']
    if F['periods'].get('annual'):
        return None
    if F.get('cash_root') and F['cash_root'] in cur:      # a cash flow statement with the quarter's own column (Amazon)
        return cur, py
    for k in cash:
        cur.pop(k, None)
        py.pop(k, None)
    if fq == 1:
        for k in cash:
            if k in F['vals']['ytd']:
                cur[k] = F['vals']['ytd'][k]
            if k in (F['vals'].get('pytd') or {}):
                py[k] = F['vals']['pytd'][k]
    elif prev and prev['periods'].get('fq') == fq - 1 and prev['periods']['ytd'][0] == F['periods']['ytd'][0]:
        # a line the earlier statement did not show was nil then (the junctions' sums catch a renamed line)
        same = lambda a, b: a in b or (parse_key(a)[0] in {parse_key(x)[0] for x in b})
        for k in cash:
            if k in F['vals']['ytd'] and prev.get('cash_root'):
                cur[k] = F['vals']['ytd'][k] - prev['vals']['ytd'].get(k, 0.0)
            pp = prev['vals'].get('pytd') or {}
            if k in (F['vals'].get('pytd') or {}) and pp:
                py[k] = F['vals']['pytd'][k] - pp.get(k, 0.0)
    return cur, py


def q4_values(K, Q3):
    """A fourth quarter: the 10-K's year less the third quarter's nine months (and the same a year earlier)."""
    if not K or not Q3 or Q3['periods'].get('fq') != 3 or Q3['periods']['ytd'][0] != K['periods']['cur'][0]:
        return None
    cur = {k: v - Q3['vals']['ytd'][k] for k, v in K['vals']['cur'].items() if k in Q3['vals']['ytd']}
    py = {k: v - Q3['vals']['pytd'][k] for k, v in (K['vals'].get('py') or {}).items() if k in (Q3['vals'].get('pytd') or {})}
    return cur, py


def cash_keys(F):
    """The keys of the cash flow part of a filing's structure (net income, shared with the income statement, left out)."""
    return {k for t, kids in F['J'].items() for k in [t] + [x for x, _ in kids] if k.startswith('cf>')}


# ------------------------------------------------------------------ flows
class Flows:
    """The junctions of a structure filled with one period's figures: links {(source, target): value}; each node's kind
    ('src': money that flows on — revenue, profit, gains, cash sources; 'use': a cost, a loss absorbed, a cash use) and the
    node its share is given of."""

    def __init__(self, F, vals, ref_total, fold=None):
        self.F, self.vals = F, vals
        self.fold = fold               # {junction: {side: [keys]}} decided on the period shown (reused for Q/Q, Y/Y)
        self.ref = abs(ref_total or 0) or 1.0
        self.links, self.kind, self.parent, self.order, self.folded, self.decided = {}, {}, {}, [], {}, {}
        self.alias = {}
        self.jx = []                   # each junction's inflow and outflow nodes (the columns: inflows one before outflows)

    def v(self, k):
        """A key's figure in the junction's own terms; an "Other" part is its parts weighted as their junction weighs them."""
        if k in self.folded:
            X = k.rsplit('~', 1)[0]
            w = dict(self.F['J'].get(X, []))
            xs = [(self.vals.get(x), w.get(x, 1.0)) for x in self.folded[k]]
            return sum(a * b for a, b in xs if a is not None) if any(a is not None for a, _ in xs) else None
        return self.vals.get(k)

    def nid(self, k):
        return self.alias.get(k, k)

    def run(self):
        F = self.F
        root = F['root']
        self.rev = next((k for k in F['J'] if main_of(k) == 'revenue'), None) or \
            next((k for j in F['J'].values() for k, _ in j if main_of(k) == 'revenue'), None)
        self.order.append(root)
        self.kind[root] = 'src' if (self.v(root) or 0) >= 0 else 'use'
        self.junction(root, 1)
        if F.get('cash_root'):
            if F.get('cash_ni') and F['cash_ni'] != root:
                self.alias[F['cash_ni']] = root          # operating cash flow's net income is the income statement's
            self.junction(F['cash_root'], 1)
        return self

    def junction(self, X, sigma, depth=0):
        """X = Σ w·part: inflows (σ·w·v > 0) fill outflows in order; X itself is the outflow (or, for a loss, the inflow)."""
        if depth > 14 or X not in self.F['J']:
            return
        vX = self.v(X)
        if vX is None:
            return
        raw = [(k, w) for k, w in self.F['J'][X] if self.v(k) not in (None, 0)]
        # the parts must add up in this period too (a fourth quarter derived from a year whose note splits a line the
        # third quarter did not): otherwise the line stays whole
        tot = sum(w * self.v(k) for k, w in raw)
        if not raw or abs(tot - vX) > max(abs(vX) * 0.002, 0.6e6 * (len(raw) + 1) if self.ref >= 1e9 else 600.0 * (len(raw) + 1)):
            return
        kids = self.fold_of(X, raw, sigma)
        terms = [(k, sigma * w * self.v(k), w) for k, w in kids]
        Xn = self.nid(X)
        aX = sigma * -vX
        ins = sorted([(self.nid(k), a) for k, a, _ in terms if a > 0], key=lambda x: -x[1])
        outs = [(self.nid(k), -a) for k, a, _ in terms if a < 0]
        main = ins[0][0] if ins else None
        if aX > 0:
            ins.append((Xn, aX))
        elif aX < 0:
            outs.append((Xn, -aX))
        # top to bottom: what flows on above what is paid out
        if Xn not in self.order:
            self.order.append(Xn)
        for k, a, _ in sorted(terms, key=lambda t: t[1] < 0):
            kn = self.nid(k)
            if kn not in self.order:
                self.order.append(kn)
            self.kind.setdefault(kn, 'src' if a > 0 else 'use')
        # shares: what a cost pays out is a share of the cost (R&D of operating expenses); what a profit line pays out, of
        # its main inflow on the main lines (cost of revenue of revenue), else of the total (interest expense of other
        # income); an inflow of the total (other income of pre-tax); the total of its main inflow (gross profit of
        # revenue), of revenue when it is larger than that (pre-tax earnings)
        chain = main and main_of(main) in ('revenue', 'gp', 'oi', 'pretax', 'net', 'ocf', 'costs', 'opex')
        for k, a, _ in terms:
            kn = self.nid(k)
            if a < 0:
                self.parent.setdefault(kn, Xn if aX > 0 or not chain else main)
            elif kn != main or k not in self.F['J']:
                self.parent.setdefault(kn, Xn)
        if aX < 0 and main and main_of(X) != 'revenue':
            if abs(vX) <= abs(self.v(main) if main in self.vals else abs(vX)) + 1e-9 * self.ref:
                self.parent.setdefault(Xn, main)
            elif getattr(self, 'rev', None) and self.rev != Xn:
                self.parent.setdefault(Xn, self.rev)
        self.fill(ins, outs)
        self.jx.append(([k for k, _ in ins], [k for k, _ in outs]))
        for k, w in kids:
            if k in self.folded or self.nid(k) == self.F['root'] and k != X:
                continue
            self.junction(k, sigma * (1 if w > 0 else -1), depth + 1)

    def fold_of(self, X, kids, sigma):
        """Small parts (and the smallest beyond MAX_PARTS per side) as one "Other" part per side."""
        if self.fold is not None:
            rec = self.fold.get(X) or {}
        else:
            sides = {'in': [], 'out': []}
            for k, w in kids:
                a = sigma * w * self.v(k)
                sides['in' if a > 0 else 'out'].append((k, abs(a)))
            rec = {}
            for side, lst in sides.items():
                lst.sort(key=lambda x: -x[1])
                small = [k for i, (k, a) in enumerate(lst) if a < FOLD * self.ref or (len(lst) > MAX_PARTS and i >= MAX_PARTS - 1)]
                if len(small) >= 2:
                    rec[side] = small
            if rec:
                self.decided[X] = rec
        if not rec:
            return kids
        gone = set()
        for side, keys in rec.items():
            self.folded[f'{X}~{side}'] = keys
            gone.update(keys)
        out = [(k, w) for k, w in self.F['J'][X] if k not in gone and self.vals.get(k) not in (None, 0)]
        for side in rec:
            if self.v(f'{X}~{side}') not in (None, 0):
                out.append((f'{X}~{side}', 1.0))
        return out

    def fill(self, ins, outs):
        ins = [list(x) for x in ins]
        outs = [list(x) for x in outs]
        i = j = 0
        eps = 1e-9 * self.ref
        while i < len(ins) and j < len(outs):
            a = min(ins[i][1], outs[j][1])
            if a > eps:
                key = (ins[i][0], outs[j][0])
                self.links[key] = self.links.get(key, 0) + a
            ins[i][1] -= a
            outs[j][1] -= a
            if ins[i][1] <= eps:
                i += 1
            if outs[j][1] <= eps:
                j += 1


# ------------------------------------------------------------------ the spec web/sankey.js draws
def money(v, unit):
    if v is None:
        return 'n/a'
    a, sign = abs(v), '−' if v < 0 else ''
    if a >= 0.95e12:
        return f'{sign}${a / 1e12:.2f}T'
    if unit == 'B' and a >= 5e6:
        b = a / 1e9
        return f'{sign}${b:.1f}B' if b >= 0.95 else f'{sign}${b:.2f}B'
    m = a / 1e6
    return f'{sign}${m:,.1f}M' if m >= 0.95 else f'{sign}${a / 1e3:,.0f}K'


def pct_change(a, b):
    if a is None or b is None:
        return '—'
    if a <= 0 or b <= 0:
        return 'n/m'
    g = round((a / b - 1) * 100)
    return ('+' if g > 0 else '−' if g < 0 else '') + f'{abs(g)}%'


def share(v, p):
    if not p or v is None or p <= 0:
        return None
    s = v / p * 100
    return f'{s:.1f}%' if s < 10 else f'{s:.0f}%'


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main_of(k):
    c, dims = parse_key(k)
    return None if dims or '~' in k or k.startswith('gap:') else MAIN_OF.get(local(c))


def spec_of(F, now, q=None, y=None, annual=False):
    """(nodes, links) for figures now — with the Q/Q and Y/Y figures of every node and link, for the comparison strips — on
    filing F's structure."""
    rev = next((k for k in F['J'] if main_of(k) == 'revenue' and k in now), None) or \
        next((k for j in F['J'].values() for k, _ in j if main_of(k) == 'revenue' and k in now), None)
    R = abs(now.get(rev) or 0) if rev else 0
    fl = Flows(F, now, R).run()
    fq = Flows(F, q, R, fl.decided).run() if q else None
    fy = Flows(F, y, R, fl.decided).run() if y else None
    unit = 'B' if R >= 1e9 else 'M'

    def node_v(f, k):
        if f is None:
            return None
        a = sum(v for (s, t), v in f.links.items() if t == k)
        b = sum(v for (s, t), v in f.links.items() if s == k)
        return max(a, b) if (a or b) else None
    ins, outs = {}, {}
    for (s, t) in fl.links:
        outs.setdefault(s, []).append(t)
        ins.setdefault(t, []).append(s)
    keys = [k for k in fl.order if k in ins or k in outs]
    # columns: in each junction the inflows one column before the outflows, from net income outwards; the income
    # statement first, then the cash flows, which start after its last column (a split income tax ends one column after
    # net income) with net income where it is
    col = {F['root']: 0}
    cashj = lambda a, b: any(k.startswith('cf>') or main_of(k) == 'ocf' for k in list(a) + list(b))

    def settle(js, shift=0):
        for _ in range(len(js) + 2):
            ch = False
            for a, b in js:
                # operating cash flow's own junction: net income where the income statement ends, the other lines one
                # column on, operating cash flow after them (an outflow, or — cash burned — an inflow)
                wide = F['root'] in a and any(main_of(k) == 'ocf' for k in list(a) + list(b))
                if wide:
                    offs = {k: 0 if k == F['root'] else 2 + shift if main_of(k) == 'ocf' else 1 + shift for k in list(a) + list(b)}
                elif any(main_of(k) == 'ocf' for k in list(a) + list(b)) and F.get('cash_root') in list(a) + list(b):
                    # operating cash flow → investing, financing, cash: the sections one column after it, whichever way
                    # they flow (their own parts then keep clear of the operating lines)
                    offs = {k: 0 if main_of(k) == 'ocf' else 1 for k in list(a) + list(b)}
                else:
                    offs = {k: 0 for k in a}
                    offs.update({k: 1 for k in b})
                known = [k for k in list(a) + list(b) if k in col]
                if not known:
                    continue
                base = col[known[0]] - offs[known[0]]
                for k in list(a) + list(b):
                    if k not in col:
                        col[k], ch = base + offs[k], True
            if not ch:
                break
    settle([j for j in fl.jx if not cashj(*j)])
    settle([j for j in fl.jx if cashj(*j)], shift=max(0, max(col.values()) - col[F['root']]))
    for k in keys:
        col.setdefault(k, 0)
    lo = min(col.values()) if col else 0
    col = {k: c - lo for k, c in col.items()}
    cash = cash_keys(F)
    into_rev = set()
    stack = [rev] if rev else []
    while stack:
        x = stack.pop()
        for s in ins.get(x, []):
            if s not in into_rev:
                into_rev.add(s)
                stack.append(s)
    ocf = next((k for k in keys if main_of(k) == 'ocf'), None)

    def color(k):
        if k == rev or k in into_rev:
            return 'rev'
        kind = fl.kind.get(k, 'src')
        if k in cash and k != ocf and main_of(k) not in ('cash_chg',):
            return 'cost' if kind == 'use' else 'noncash'
        return 'profit' if kind == 'src' else 'cost'
    lab = F['labels']
    ids, nodes, byk = {}, [], {}
    for k in keys:
        m = main_of(k)
        i = m if m and m not in ids.values() else ('o:' + k if '~' in k else 'k:' + k)
        ids[k] = i
        if '~' in k:
            name = f'Other ({len(fl.folded.get(k, []))} items)'
        else:
            name = NAMES.get(m) or lab.get(k) or local(k)
            if not m and not parse_key(k)[1] and re.fullmatch(r'(?i)(?:total )?(?:net )?(?:revenues?|sales)', name.strip()):
                # a part labelled like the total ("Revenue" beside premiums): named by what it is
                name = 'Revenue from contracts with customers' if 'FromContractWithCustomer' in parse_key(k)[0] else 'Other revenue'
            if m == 'net' and parse_key(k)[0].endswith('ProfitLoss'):
                name = 'Net earnings (incl. minority interests)'
            if m == 'cash_chg':
                name = 'Added to cash' if (now.get(k) or 0) > 0 else 'Drawn from cash'
        short = name if len(name) <= 52 else name[:50].rsplit(' ', 1)[0].rstrip(',;:-–') + ' …'
        n = {'id': i, 'col': col.get(k, 0), 'color': color(k), 'name': esc(short), 'full': esc(name) if short != name else None,
             'pos': 'left' if not ins.get(k) else 'right' if not outs.get(k) else 'above' if fl.kind.get(k) == 'src' else 'below',
             'v': node_v(fl, k), 'q': node_v(fq, k), 'y': node_v(fy, k)}
        nodes.append(n)
        byk[k] = n
    links = []
    for (s, t), v in fl.links.items():
        links.append({'s': byk[s]['id'], 't': byk[t]['id'], 'v': v, 'q': fq.links.get((s, t)) if fq else None,
                      'y': fy.links.get((s, t)) if fy else None, 'color': byk[t]['color']})
    for k, n in byk.items():
        pk = fl.parent.get(k)
        p = byk.get(pk)
        lines = [['big' if n['id'] == 'revenue' else 'ocf' if n['id'] == 'ocf' else 'name', n['name']]]
        val = money(n['v'], unit)
        if p and p is not n:
            sh = share(n['v'], p['v'])
            if sh and n['v'] <= p['v'] * 1.0005:        # a part larger than its parent (other inflows joined): no share
                val += f" · {sh} of {SHORT.get(p['id']) or esc(lab.get(pk, '') or '').lower()[:30]}"
        lines.append(['val', val])
        lines.append(['mut', f"Y/Y {pct_change(n['v'], n['y'])}" + ('' if annual else f" · Q/Q {pct_change(n['v'], n['q'])}")])
        if '~' in k:
            parts = fl.folded.get(k, [])
            lines.append(['mut', esc(', '.join(lab.get(x, local(x)) for x in parts[:2]) + (' …' if len(parts) > 2 else ''))])
        n['lines'] = lines
        n['cmp'] = _delta(n, p, 'q', 'no prior quarter', unit)
        n['cmp_y'] = _delta(n, p, 'y', 'no year-ago period', unit)
        txt = []
        if '~' in k:
            X = k.rsplit('~', 1)[0]
            w = dict(F['J'].get(X, []))
            txt.append('Small parts summed here: ' + '; '.join(f"{lab.get(x, local(x))} {money(abs((now.get(x) or 0) * w.get(x, 1)), unit)}"
                                                                for x in fl.folded.get(k, [])) + '.')
        else:
            c, dims = parse_key(k)
            if k in F['J'] and F['via'].get(k):
                v0 = F['via'][k]
                txt.append('Split into its parts by ' + (f"the filing’s {AXIS_WORD.get(v0[5:], 'members')}" if v0.startswith('dims:') else f'“{v0}”') + '.')
            if k.startswith('gap:'):
                txt.append('What the split leaves of the total (items the filing does not assign to a member).')
            else:
                txt.append('XBRL: ' + c + ''.join(f' · {a.split(":")[-1]} = {m.split(":")[-1]}' for a, m in dims) + '.')
                if not dims and c.startswith('us-gaap:'):
                    n['tag'] = c
        if n.get('full'):
            txt.insert(0, f"{n['full']}.")
        n['source'] = esc(' '.join(txt)).replace('&amp;amp;', '&amp;')
    return nodes, links


def _delta(n, p, attr, missing, unit):
    if n.get(attr) is None:
        return f'Δ n/a ({missing})'
    d = n['v'] - n[attr]
    txt = f"Δ {'+' if d > 0 else '−' if d < 0 else '±'}{money(abs(d), unit)}"
    if p and p is not n and p.get(attr) is not None:
        c0, c1, p0, p1 = n[attr], n['v'], p[attr], p['v']
        if p0 > 0 and p1 > 0 and c0 >= 0 and c1 >= 0:
            scale = (p1 - p0) * c0 / p0
            mix = p1 * (c1 / p1 - c0 / p0)
            f = lambda x: ('+' if x > 0 else '−' if x < 0 else '±') + (lambda y: f'{abs(y):.1f}' if abs(y) >= 0.95 else f'{abs(y):.2f}')(x / (1e9 if unit == 'B' else 1e6))
            txt += f' · scale {f(scale)} · mix {f(mix)}'
        else:
            txt += ' · scale/mix n/m'
    return txt


# ------------------------------------------------------------------ a company: its quarters and years
def assemble(filings):
    """filings: [(meta {'accession', 'filed', 'form', 'url'}, read_filing result)] → {'quarters': [...], 'years': [...]}, the
    latest first; each with nodes and links for web/sankey.js and the figures the comparisons rest on."""
    fs = sorted([x for x in filings if x[1]], key=lambda x: x[1]['periods']['cur'][1])
    quarters, years = [], []
    for i, (m, F) in enumerate(fs):
        P = F['periods']
        if P.get('annual'):
            years.append({'end': P['cur'][1], 'start': P['cur'][0], 'meta': m, 'F': F, 'now': F['vals']['cur'], 'y': F['vals'].get('py') or {}})
            q3 = next((G for _, G in reversed(fs[:i]) if G['periods'].get('fq') == 3 and G['periods']['ytd'][0] == P['cur'][0]), None)
            got = q4_values(F, q3)
            if got:
                quarters.append({'end': P['cur'][1], 'start': None, 'fq': 4, 'meta': m, 'F': F, 'now': got[0], 'y': got[1], 'cash': bool(F.get('cash_root'))})
            continue
        prev = next((G for _, G in reversed(fs[:i]) if not G['periods'].get('annual') and G['periods'].get('fq') == P['fq'] - 1
                     and G['periods']['ytd'][0] == P['ytd'][0]), None)
        got = quarter_values(F, prev)
        if got:
            cash = P['fq'] == 1 or prev is not None
            quarters.append({'end': P['cur'][1], 'start': P['cur'][0], 'fq': P['fq'], 'meta': m, 'F': F, 'now': got[0], 'y': got[1], 'cash': cash})
    quarters.sort(key=lambda x: x['end'])
    out_q, out_y = [], []
    ok = lambda nodes: len(nodes) >= 6 and any(n['id'] == 'revenue' for n in nodes) and any(n['id'] == 'net' for n in nodes)
    for i, q in enumerate(quarters):
        prevq = quarters[i - 1] if i and 70 <= (_d(q['end']) - _d(quarters[i - 1]['end'])).days <= 130 else None
        nodes, links = spec_of(q['F'], q['now'], prevq['now'] if prevq else None, q['y'] or None)
        if ok(nodes):                                    # a statement read only in part is not drawn
            out_q.append(_period(q, nodes, links, prevq))
    for y in sorted(years, key=lambda x: x['end']):
        nodes, links = spec_of(y['F'], y['now'], None, y['y'] or None, annual=True)
        if ok(nodes):
            out_y.append(_period(y, nodes, links, None, annual=True))
    return {'quarters': out_q[::-1], 'years': out_y[::-1]}


def _period(q, nodes, links, prevq, annual=False):
    m = q['meta']
    F = q['F']
    return {'end': q['end'], 'start': q.get('start'), 'period': 'fy' if annual else 'q', 'fq': None if annual else q['fq'],
            'form': m.get('form'), 'accession': m.get('accession'), 'filed': m.get('filed'), 'url': m.get('url'),
            'q_end': prevq['end'] if prevq else None, 'has_y': any(n.get('y') is not None for n in nodes),
            'cash': bool(F.get('cash_root')) and (annual or q.get('cash', False)), 'axis': F.get('axis'),
            'nodes': nodes, 'links': links}


def bullets(nodes, attr, unit, n=4):
    """The lines that moved most against the comparison period (the comparison button needs a few)."""
    rows = [x for x in nodes if x.get(attr) is not None and x.get('v') is not None and x['id'] not in ('revenue',)]
    rows.sort(key=lambda x: -abs(x['v'] - x[attr]))
    out = []
    for x in rows[:n]:
        d = x['v'] - x[attr]
        out.append(f"{x['name']}: {money(x['v'], unit)}, {'+' if d >= 0 else '−'}{money(abs(d), unit)} ({pct_change(x['v'], x[attr])})")
    return out


# ------------------------------------------------------------------ collecting: the site's companies, largest first
UA_DEFAULT = N.UA_DEFAULT
Q_FORMS, K_FORMS = ('10-Q',), ('10-K', '10-KT')
PER_COMPANY_SECONDS = 300


def _compact(o):
    """Whole dollars, no empty fields (the files are read by every visitor's browser)."""
    if isinstance(o, float):
        return int(round(o)) if abs(o) >= 1000 else round(o, 6)
    if isinstance(o, dict):
        return {k: _compact(v) for k, v in o.items() if v is not None}
    if isinstance(o, (list, tuple)):
        return [_compact(x) for x in o]
    return o


def dump(o):
    return json.dumps(_compact(o), separators=(',', ':'), ensure_ascii=False)


def filings_of(cik, ua):
    """What a company's charts need, newest first: its 10-Qs since the latest 10-K, that 10-K, and the 10-Q before it (the
    third quarter, whose nine months make the fourth quarter); amendments and filings without XBRL left out."""
    sub = json.loads(N.http_get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', ua))
    r = sub['filings']['recent']
    out, k_seen = [], False
    for i, f in enumerate(r['form']):
        if f not in Q_FORMS + K_FORMS or not (r.get('isXBRL') or [1] * len(r['form']))[i]:
            continue
        if any(x['period'] == r['reportDate'][i] for x in out):
            continue
        out.append({'accession': r['accessionNumber'][i], 'filed': r['filingDate'][i], 'period': r['reportDate'][i], 'form': f,
                    'url': f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{r['accessionNumber'][i].replace('-', '')}/{r['primaryDocument'][i]}"})
        if f in K_FORMS:
            if k_seen:
                break
            k_seen = True
        elif k_seen:                                     # the 10-Q before the 10-K: enough
            break
        if len(out) >= 6:
            break
    return {'name': sub.get('name'), 'tickers': sub.get('tickers') or [], 'filings': out}


def read_cached(cik, f, cache, reads, ua, sleep=0.12):
    """One filing read (read_filing), from reads/<accession>.json when read before with this version."""
    rp = Path(reads) / f"{f['accession']}.json"
    if rp.exists():
        try:
            d = json.loads(rp.read_text())
            if d.get('v') == VERSION:
                return d['read']
        except (OSError, ValueError):
            pass
    folder = Path(cache) / f['accession']
    try:
        paths = X.fetch(cik, f['accession'], folder, ua, sleep=sleep)
        if 'instance' not in paths or 'summary' not in paths:
            got = None
        else:
            got = read_filing(N.Filing(X.load(paths)))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps({'v': VERSION, 'read': got}, separators=(',', ':'), ensure_ascii=False))
    return got


def build_company(cik, ua, root, ticker=None, info=None, sic=None):
    """A company's detailed charts. A bank's, broker's or insurer's (SIC 6000–6399, health insurers kept) cash flow statement
    is left out: its lending, deposits and securities dwarf what it earns and are not the cash from its business the chart
    follows."""
    info = info or filings_of(cik, ua)
    try:
        sc = int(sic or 0)
        fin = 6000 <= sc < 6300 or (6300 <= sc < 6400 and sc != 6324)    # banks, credit, brokers; insurers but health
    except ValueError:
        fin = False
    reads = Path(root) / 'reads' / str(int(cik))
    pairs = []
    for f in info['filings']:
        got = read_cached(cik, f, Path(root) / '_cache', reads, ua)
        if got and fin:
            got = dict(got, cash_root=None, cash_ni=None)
            got['J'] = {t: k for t, k in got['J'].items() if not t.startswith('cf>')}
        pairs.append((f, got))
    keep = {f"{f['accession']}.json" for f in info['filings']}
    for p in reads.glob('*.json'):                       # reads no longer needed
        if p.name not in keep:
            p.unlink()
    doc = assemble(pairs)
    for per in doc['quarters'] + doc['years']:
        unit = 'B' if max((n['v'] or 0 for n in per['nodes']), default=0) >= 1e9 else 'M'
        per['bullets_q'] = bullets(per['nodes'], 'q', unit)
        per['bullets_y'] = bullets(per['nodes'], 'y', unit)
    return {'v': VERSION, 'cik': int(cik), 'ticker': ticker or (info['tickers'][0] if info['tickers'] else None), 'name': info['name'],
            'generated': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), **doc}


def collect(root, site_index, ua, minutes=40.0, tickers=None, limit=None, recheck_days=5):
    """The site's companies, largest first: a company is (re)built when never built, read with another version, when the
    site shows a filing newer than the newest on file, or every few days. public/c/<TICKER>.json; state.json."""
    import signal
    root = Path(root)
    t0 = time.time()
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    st_p = root / 'state.json'
    state = json.loads(st_p.read_text()) if st_p.exists() else {}
    cos = [c for c in (json.loads(Path(site_index).read_text()).get('companies') or []) if c.get('ticker') and c.get('cik')]
    cos.sort(key=lambda c: -(c.get('revenue') or 0))
    want = [t.strip().upper() for t in (tickers or '').split(',') if t.strip()]
    now = dt.datetime.now(dt.timezone.utc)

    def due(c):
        s_ = state.get(c['ticker']) or {}
        if c['ticker'].upper() in want:
            return -1
        if s_.get('retry_after') and s_['retry_after'] > now.isoformat():
            return None
        if not s_.get('filed'):
            return 0
        if s_.get('v') != VERSION:
            return 1
        if c.get('filed') and c['filed'] > s_['filed']:
            return 2
        if not s_.get('checked') or (now - dt.datetime.fromisoformat(s_['checked'])).days >= recheck_days:
            return 3
        return None
    order = sorted([(due(c), i, c) for i, c in enumerate(cos) if due(c) is not None], key=lambda x: (x[0], x[1]))
    done = errs = same = 0

    def too_long(*_):
        raise TimeoutError(f'over {PER_COMPANY_SECONDS} s')
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, too_long)
    for _, _, c in (order[:limit] if limit else order):
        if time.time() - t0 > minutes * 60:
            break
        t = c['ticker']
        s_ = state.setdefault(t, {})
        try:
            info = filings_of(c['cik'], ua)
            time.sleep(0.12)
            if not info['filings']:
                s_.update(checked=now.isoformat(timespec='seconds'), error='no 10-Q or 10-K with XBRL')
                continue
            top = info['filings'][0]
            if s_.get('accession') == top['accession'] and s_.get('v') == VERSION and (pub / 'c' / f'{t}.json').exists():
                s_['checked'] = now.isoformat(timespec='seconds')
                same += 1
                continue
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(PER_COMPANY_SECONDS)
            try:
                doc = build_company(c['cik'], ua, root, t, info, sic=c.get('sic'))
            finally:
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
            (pub / 'c' / f'{t}.json').write_text(dump(doc), encoding='utf-8')
            s_.clear()
            s_.update(v=VERSION, accession=top['accession'], filed=top['filed'], checked=now.isoformat(timespec='seconds'),
                      row=[t, doc['name'], int(c['cik']), len(doc['quarters']), len(doc['years']),
                           doc['quarters'][0]['end'] if doc['quarters'] else None, top['filed']])
            done += 1
        except Exception as e:                              # one company's failure never stops the batch
            errs += 1
            s_.update(error=f'{type(e).__name__}: {str(e)[:200]}', checked=now.isoformat(timespec='seconds'),
                      retry_after=(now + dt.timedelta(days=2)).isoformat(timespec='seconds'))
            print(f'{t}: {type(e).__name__}: {e}', file=sys.stderr)
    shutil.rmtree(root / '_cache', ignore_errors=True)
    return write_index(root, state, {'built': done, 'errors': errs, 'unchanged': same, 'waiting': max(0, len(order) - done - errs - same)})


INDEX_FIELDS = ['ticker', 'name', 'cik', 'quarters', 'years', 'latest_end', 'filed']


def write_index(root, state=None, extra=None):
    root = Path(root)
    pub, st_p = root / 'public', root / 'state.json'
    if state is None:
        state = json.loads(st_p.read_text()) if st_p.exists() else {}
    st_p.write_text(json.dumps(state, separators=(',', ':')))
    rows = [v['row'] for k, v in sorted(state.items()) if v.get('row') and (pub / 'c' / f'{k}.json').exists()]
    gen = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    pub.mkdir(parents=True, exist_ok=True)
    (pub / 'index.json').write_text(json.dumps({'generated_at': gen, 'v': VERSION, 'fields': INDEX_FIELDS, 'rows': rows}, separators=(',', ':')))
    status = {'built_at': gen, 'companies': len(rows), **(extra or {})}
    (pub / 'status.json').write_text(json.dumps(status))
    return status


def main():
    ap = argparse.ArgumentParser(description='Detailed Sankey of each company: every flow split by the filing and its notes')
    sub = ap.add_subparsers(dest='cmd')
    o = sub.add_parser('one')
    o.add_argument('--cik', required=True)
    o.add_argument('--ticker')
    o.add_argument('--out', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--site-index', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--limit', type=int, default=None)
    c.add_argument('--tickers', default='')
    i = sub.add_parser('index')
    i.add_argument('--root', required=True)
    a = ap.parse_args()
    ua = os.environ.get('SEC_USER_AGENT') or UA_DEFAULT
    if a.cmd == 'index':
        print(json.dumps(write_index(a.root)))
    elif a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, ua, a.minutes, tickers=a.tickers, limit=a.limit)))
    elif a.cmd == 'one':
        doc = build_company(a.cik, ua, a.out, a.ticker)
        out = Path(a.out) / 'public' / 'c'
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{doc['ticker']}.json").write_text(dump(doc), encoding='utf-8')
        print(json.dumps({'ticker': doc['ticker'], 'quarters': [(q['end'], len(q['nodes'])) for q in doc['quarters']],
                          'years': [(y['end'], len(y['nodes'])) for y in doc['years']]}))
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
