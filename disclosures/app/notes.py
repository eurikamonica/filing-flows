"""Notes: every note of a company's latest 10-K as tables, charts, the ties between them (勾稽) and what links them (联动).

For one filing (app/xbrl_filing.py reads it):
  reports   the SEC's own list (FilingSummary.xml): the statements, each note and its detail reports (matched to the note
            by the report's name, the way the SEC titles them: "Debt - Schedule of Debt (Details)" → "Debt")
  tables    every statement and detail report rebuilt from the facts as the filing presents it (its presentation tree,
            labels, one column per period and dimension member); where two facts say the same thing, the more precise
  checks    勾稽, each recomputed from the facts, for the latest two fiscal years:
              sum        every calculation relationship the company filed (total = Σ weight × part)
              rollfwd    every roll-forward the filing presents (opening + movements = closing); the direction of each
                         movement from its debit / credit balance against the balance's, else its label
              members    a dimension's members against the total they split (segments, markets, regions, classes …),
                         nested members too (Data Center = Compute + Networking)
              tie        named ties across statements and notes: the balance sheet balances; cash at the end of the cash
                         flow statement = the balance sheet's; net income, stock-based compensation, deferred taxes,
                         dividends and buybacks in each place they appear; debt, leases and deferred revenue = their
                         current + long-term parts; EPS = net income ÷ shares; the effective tax rate; intangibles
              cf_bs      each balance sheet change against its cash flow line (receivables, inventories, payables,
                         accruals, prepaid, deferred revenue) — gaps are what the cash flow leaves out (acquired balances,
                         amounts not yet paid, reclassifications); a gap matching a disclosed non-cash item is named
              dup        the same fact reported twice (e.g. in millions and rounded to billions) must agree
            status: tie (within the rounding of the figures), round (within 3 × that or 0.1%), gap (explained or not)
  links     联动 — the statement lines each note explains (the same concept in its tables, or a total the note breaks
            down), and the notes each check touches, so a page can light up one from the other
  charts    one per detail report, from its shape: roll-forward (waterfall), schedule by year (maturities, payments,
            amortization), composition (parts of a total, this year and last), members (a split by segment, market,
            region …), tax-rate bridge (statutory → effective), else the key figures
  analysis  per note, sentences written by rules from the numbers: growth, the largest parts and movers, ratios that
            matter for the note (days of inventory, receivables, warranty and stock compensation against revenue,
            commitments against cost of revenue, the effective tax rate, customer concentration), checks that do not tie

  python notes.py one --cik 1045810 --out <dir> [--ticker NVDA]          one company's latest 10-K
  python notes.py collect --root <branch> --site-index <index.json> --minutes 40     the site's companies, largest first
"""
import argparse
import datetime as dt
import html as H
import itertools
import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbrl_filing as X

DAY = dt.timedelta(days=1)
STATEMENT_KINDS = [('oci', r'comprehensive (income|loss)'), ('cf', r'cash flow'), ('eq', r"(stockholders|shareholders|owners)['’]? (equity|deficit)|changes in equity|statements? of equity"),
                   ('bs', r'balance sheet|financial (position|condition)|statements? of condition'), ('is', r'income|operations|earnings|statements? of (loss|profit)')]


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _d(s):
    return dt.date.fromisoformat(s)


def norm_title(s):
    s = s or ''
    while True:                                           # "Investments (Narrative) (Details)", "Debt (Notes)", "… (Detail)"
        t = re.sub(r'\s*\((details?|tables?|polic(y|ies)|narrative|notes?|textual)\)\s*$', '', s, flags=re.I)
        if t == s:
            break
        s = t
    s = re.sub(r'(?i)\s*\(narrative\)', '', s)
    s = re.sub(r'(?i)^\s*note\s+\d+\s*[-–—:.]?\s*', '', s)
    return re.sub(r'[^a-z0-9]+', ' ', s.lower().replace('’', "'").replace('&', ' and ')).strip()


# ------------------------------------------------------------------ the model of one filing
class Filing:
    def __init__(self, F, crdr=None):
        self.F = F
        self.ctx = F['contexts']
        self.lab = F['labels']
        self.crdr = crdr or {}
        self.by_c = {}
        self.num = {}                                     # (c, period, dims) → (value, decimals, unit)
        for f in F['facts']:
            self.by_c.setdefault(f['c'], []).append(f)
            if not fin(f['v']):
                continue
            k = self.ctx[f['ctx']]
            key = (f['c'], self.pkey(k), tuple(sorted(k['dims'].items())))
            dec = self.dec(f.get('d'))
            old = self.num.get(key)
            if old is not None and old[2] != f.get('u'):         # the same amount in another currency (notional in EUR and USD)
                if f.get('u') == 'USD':
                    self.num[key] = (f['v'], dec, f.get('u'))
                continue
            if old is None or (dec is None) or (old[1] is not None and dec > old[1]):
                self.num[key] = (f['v'], dec, f.get('u'))
            elif old is not None and abs(old[0] - f['v']) > self.tol_of(old[1]) + self.tol_of(dec):
                self.dups = getattr(self, 'dups', []) + [(key, old, (f['v'], dec))]
        self.reports = F['reports']
        self.by_local = {}
        for c in self.by_c:
            self.by_local.setdefault(c.split(':')[-1], []).append(c)
        durs = sorted({(c['s'], c['e']) for c in self.ctx.values() if 's' in c and not c['dims'] and 330 <= (_d(c['e']) - _d(c['s'])).days <= 380},
                      key=lambda x: x[1])
        self.fys = list(reversed(durs))                   # fiscal years, the latest first
        self.fy = self.fys[0] if self.fys else None

    @staticmethod
    def pkey(k):
        return ('i', k['i']) if 'i' in k else ('d', k['s'], k['e'])

    @staticmethod
    def dec(d):
        if d in (None, '', 'INF'):
            return None
        try:
            return int(d)
        except ValueError:
            return None

    @staticmethod
    def tol_of(dec):
        return 0.0 if dec is None else 0.5 * 10 ** (-dec)

    def label(self, c, pref=None):
        L = self.lab.get(c) or {}
        for k in ([pref] if pref else []) + ['terse', 'label', 'verbose']:
            if k and L.get(k):
                return re.sub(r'\s*\[(Member|Axis|Domain|Line Items|Table|Abstract|Roll Forward|Text Block)\]$', '', L[k])
        return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', c.split(':')[-1])

    def get(self, c, p, dims=()):
        r = self.num.get((c, p, tuple(sorted(dict(dims).items())) if dims else ()))
        return r

    def v(self, c, p, dims=()):
        r = self.get(c, p, dims)
        return r[0] if r else None

    def unit(self, c):
        for f in self.by_c.get(c, []):
            if f.get('u'):
                return f['u']
        return None

    def text(self, c):
        for f in self.by_c.get(c, []):
            if isinstance(f['v'], str) and not self.ctx[f['ctx']]['dims']:
                return f['v']
        return None

    # periods
    def dur(self, i=0):
        return ('d',) + self.fys[i] if len(self.fys) > i else None

    def inst(self, i=0):
        """The balance sheet date of fiscal year i (0 = the latest), i = −1 … the opening of the latest year."""
        return ('i', self.fys[i][1]) if len(self.fys) > i else None

    def opening(self, i=0):
        return ('i', (_d(self.fys[i][0]) - DAY).isoformat()) if len(self.fys) > i else None

    def fy_label(self, i=0):
        if len(self.fys) <= i:
            return ''
        e = _d(self.fys[i][1])
        return 'FY' + str(e.year if e.month > 6 else e.year)    # NVIDIA's year ending Jan 2026 is its FY2026


# ------------------------------------------------------------------ report structure
def classify_reports(FL):
    """→ statements [{report, kind}], notes [{report, num, details: [reports], tables, policies}]"""
    statements, notes = [], []
    for r in FL.reports:
        if r['cat'] == 'Statements' and 'parenthetical' not in r['short'].lower():
            kind = next((k for k, rx in STATEMENT_KINDS if re.search(rx, r['short'], re.I)), 'other')
            statements.append({'report': r, 'kind': kind})
    num = 0
    for r in FL.reports:
        if r['cat'] != 'Notes':
            continue
        sec = '//xbrl.sec.gov/' in r['role'] or re.match(r'(?i)schedule\b', r['short'])
        if not sec:
            num += 1
        notes.append({'report': r, 'num': None if sec else num, 'key': norm_title(r['short']), 'details': [], 'tables': [], 'policies': []})
    by_role = {n['report']['role']: n for n in notes}
    rep_of_role = {r['role']: r for r in FL.reports}
    stop = {'and', 'of', 'the', 'notes', 'note', 'other', 'a', 'in', 'for', 'details', 'detail', 'narrative', 'tables'}
    for r in FL.reports:
        if r['cat'] not in ('Details', 'Tables', 'Policies'):
            continue
        n, up, hops = None, r.get('parent'), 0             # the parent chain: details → tables → note
        while up and n is None and hops < 4:
            n = by_role.get(up)
            up = (rep_of_role.get(up) or {}).get('parent')
            hops += 1
        if n is None:
            t = norm_title(r['short'])
            cands = [x for x in notes if t == x['key'] or t.startswith(x['key'] + ' ')]
            n = max(cands, key=lambda x: len(x['key'])) if cands else None
        if n is None:                                      # the note's words all in the report's title
            tw = set(norm_title(r['short']).split()) - stop
            best = max(((len(set(x['key'].split()) - stop), x) for x in notes if (set(x['key'].split()) - stop) and (set(x['key'].split()) - stop) <= tw),
                       key=lambda z: z[0], default=(0, None))
            n = best[1]
        if n is None and r['cat'] == 'Policies' and notes:
            n = notes[0]
        if n is None:
            continue
        n[{'Details': 'details', 'Tables': 'tables', 'Policies': 'policies'}[r['cat']]].append(r)
    # detail reports with neither a parent nor the note's name: the SEC lists them in note order, so a report goes to the note
    # of its neighbours (when they differ, the one whose name shares more word stems with it)
    det = [r for r in FL.reports if r['cat'] == 'Details']
    owner = {r['r']: n['id'] if 'id' in n else i for i, n in enumerate(notes) for r in n['details']}
    stem = lambda t: {w[:5] for w in norm_title(t).split() if w not in stop and len(w) > 2}
    _ts = {}

    def text_stems(i):
        if i not in _ts:
            tb = [nd['c'] for nd in FL.F['pre'].get(notes[i]['report']['role'], []) if nd['c'].endswith('TextBlock')]
            _ts[i] = stem(plain(FL.text(tb[0]) or '', 30000)) if tb else set()
        return _ts[i]
    for k, r in enumerate(det):
        if r['r'] in owner:
            continue
        prev = next((owner[det[j]['r']] for j in range(k - 1, -1, -1) if det[j]['r'] in owner), None)
        nxt = next((owner[det[j]['r']] for j in range(k + 1, len(det)) if det[j]['r'] in owner), None)
        cands = [c for c in (prev, nxt) if c is not None]
        if not cands:
            continue
        if prev is not None and nxt is not None and nxt - prev > 1:
            cands = list(range(prev, nxt + 1))            # the notes in between, whose details may be this one alone
        if len(set(cands)) == 1:
            pick = cands[0]
        else:                                            # the candidate note whose name or text holds more of the report's words
            ws = stem(r['short'])
            pick = max(cands, key=lambda c: (len(ws & stem(notes[c]['report']['short'])), len(ws & text_stems(c)), c == nxt))
        notes[pick]['details'].append(r)
        owner[r['r']] = pick
    for n in notes:                                     # back in the filing's order
        n['details'].sort(key=lambda r: r['pos'])
    return statements, notes


def title_of(FL, r):
    """A report's title from the company's schema ('9952164 - Disclosure - Shareholders’ Equity'), else the SEC's list (whose
    curly quotes are sometimes '???')."""
    t = (FL.F.get('roles') or {}).get(r['role'])
    if t:
        t = re.sub(r'^\s*\d+\s*-\s*(Statement|Disclosure|Document|Schedule)\s*-\s*', '', t).strip()
        if t:
            return t
    return r['short']


# ------------------------------------------------------------------ tables
def build_table(FL, role, max_cols=24):
    """One report as presented: rows (the presentation tree), columns (period × dimension members), cells (values)."""
    seq = FL.F['pre'].get(role) or []
    d = FL.F['def'].get(role) or {'axes': {}}
    allowed = {ax: set(m) for ax, m in d['axes'].items()}
    cols = {}
    for n in seq:
        for f in FL.by_c.get(n['c'], []):
            if not fin(f['v']):
                continue
            k = FL.ctx[f['ctx']]
            if any(ax not in allowed or m not in allowed[ax] for ax, m in k['dims'].items()):
                continue
            dims = tuple(sorted(k['dims'].items()))
            cols.setdefault(('i', None, k['i'], dims) if 'i' in k else ('d', k['s'], k['e'], dims), 1)
    keep = [c for c in cols if c[0] == 'd']
    if keep:
        ends = {(c[2], c[3]) for c in keep}
        for c in cols:
            if c[0] == 'i' and (c[2], c[3]) not in ends and not any(x[0] == 'd' and c[3] == x[3] and _d(x[1]) - DAY == _d(c[2]) for x in keep):
                keep.append(c)
    else:
        keep = list(cols)
    order = {(ax, m): j for ax, mem in d['axes'].items() for j, m in enumerate(mem)}
    keep.sort(key=lambda c: (len(c[3]), [order.get(x, 99) for x in c[3]], c[3], -_d(c[2]).toordinal()))
    mlab = {n['c']: FL.label(n['c'], n['pref']) for n in seq if n['pref']}
    out_cols = [{'kind': c[0], 's': c[1], 'e': c[2], 'dims': dict(c[3]), 'label': ' · '.join(mlab.get(m) or FL.label(m) for ax, m in c[3])} for c in keep]
    rows, cells = [], []
    for n in seq:
        c = n['c']
        is_num = any(fin(f['v']) for f in FL.by_c.get(c, []))
        rows.append({'c': c, 'label': FL.label(c, n['pref'] if n['pref'] not in ('start', 'end') else None), 'depth': n['depth'], 'pref': n['pref'],
                     'abstract': not is_num, 'u': FL.unit(c) if is_num else None})
        vals = []
        for col in out_cols:
            dims = tuple(sorted(col['dims'].items()))
            if col['kind'] == 'd':
                if n['pref'] == 'start':
                    r = FL.num.get((c, ('i', (_d(col['s']) - DAY).isoformat()), dims)) or FL.num.get((c, ('i', col['s']), dims))
                else:
                    r = FL.num.get((c, ('d', col['s'], col['e']), dims)) or FL.num.get((c, ('i', col['e']), dims))
            else:
                r = FL.num.get((c, ('i', col['e']), dims))
            vals.append(r[0] if r else None)
        cells.append(vals)
    use = [j for j in range(len(out_cols)) if any(cells[i][j] is not None for i in range(len(rows)))][:max_cols]
    out_cols = [out_cols[j] for j in use]
    cells = [[r[j] for j in use] for r in cells]
    # drop the dimension scaffolding rows ([Table], [Axis], [Domain], members, [Line Items]) that carry no numbers
    keep_r = [i for i, r in enumerate(rows) if not (r['abstract'] and re.search(r'(Table|Axis|Domain|Member|LineItems)$', r['c']))]
    return {'rows': [rows[i] for i in keep_r], 'cols': out_cols, 'cells': [cells[i] for i in keep_r]}


def plain(h, limit=None):
    """HTML (a text block) → readable plain text; tables become 'a | b | c' lines."""
    if not h:
        return ''
    s = re.sub(r'(?i)<br\s*/?>', '\n', h)
    s = re.sub(r'(?i)</(p|div|tr|li|h\d)>', '\n', s)
    s = re.sub(r'(?i)</t[dh]>', ' | ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = H.unescape(s)
    s = re.sub(r'[ \t\xa0]+', ' ', s)
    s = re.sub(r'(\s*\|\s*)+\n', '\n', s)
    s = re.sub(r'\n\s*\n+', '\n', s).strip()
    return s[:limit] if limit else s


def prose(h, limit=2400):
    """The note's text without its tables: the paragraphs a reader needs, the numbers left in."""
    if not h:
        return []
    h = re.sub(r'(?is)<table.*?</table>', '\n', h)
    paras = [p.strip() for p in plain(h).split('\n')]
    out, n = [], 0
    for p in paras:
        if len(p) < 3 or re.fullmatch(r'[\d\s|$().,%—–-]+', p):
            continue
        out.append(p)
        n += len(p)
        if n > limit:
            break
    return out


# ------------------------------------------------------------------ checks
def _status(diff, tol, total):
    a = abs(diff)
    if a <= tol + 1e-9 * max(1.0, abs(total)):
        return 'tie'
    if a <= max(3 * tol, 0.001 * abs(total)):
        return 'round'
    return 'gap'


class Checks:
    def __init__(self, FL):
        self.FL = FL
        self.items = []
        self.seen = set()

    def add(self, kind, title, parts, result, where=None, explain=None, period=None, key=None, info=False):
        """info=True: the two figures need not agree (a gap is a difference to explain, not an error)."""
        """parts: [(label, concept, value, sign, decimals)], result: (label, concept, value, decimals)."""
        if key and key in self.seen:
            return None
        if key:
            self.seen.add(key)
        calc = sum(s * v for _, _, v, s, _ in parts)
        tol = sum(Filing.tol_of(d) for *_, d in parts) + Filing.tol_of(result[3])
        diff = result[2] - calc
        st = _status(diff, tol, result[2])
        ch = {'id': f'k{len(self.items) + 1}', 'kind': kind, 'title': title, 'period': period,
              'parts': [[l, c, v, s] for l, c, v, s, _ in parts], 'result': [result[0], result[1], result[2]],
              'calc': calc, 'diff': diff, 'tol': tol, 'status': 'info' if info and st == 'gap' else st,
              'where': sorted(set(where or [])), 'explain': explain}
        self.items.append(ch)
        return ch


def role_labels(FL, role):
    return {n['c']: FL.label(n['c'], n['pref'] if n['pref'] not in ('start', 'end') else None) for n in FL.F['pre'].get(role, [])}


def calc_checks(FL, K, report_of_role, periods):
    """Every calculation relationship, for the latest two years (each relationship once per period and member set)."""
    for role, rel in FL.F['cal'].items():
        rid = report_of_role.get(role)
        RL = role_labels(FL, role)
        for parent, kids in rel.items():
            for key, (val, dec, unit) in list(FL.num.items()):
                c, p, dims = key
                if c != parent or p not in periods:
                    continue
                parts, missing = [], 0
                for ch, w in kids:
                    r = FL.num.get((ch, p, dims))
                    if r is None:
                        missing += 1
                        continue
                    parts.append((RL.get(ch) or FL.label(ch), ch, r[0], w, r[1]))
                if len(parts) < 1 or (missing and len(parts) < 2):
                    continue
                calc = sum(s * v for _, _, v, s, _ in parts)
                tol = sum(Filing.tol_of(d) for *_, d in parts) + Filing.tol_of(dec)
                if missing and _status(val - calc, tol, val) != 'tie':
                    continue                              # parts not all reported here: not a check
                sig = (parent, tuple(sorted(ch for ch, _ in kids)), p, dims)
                pl = RL.get(parent) or FL.label(parent, 'total')
                title = pl if not dims else pl + ' — ' + ', '.join(FL.label(m) for _, m in dims)
                K.add('sum', title, parts, (pl, parent, val, dec), where=[rid] if rid else [], period=p, key=('sum',) + sig)


MINUS_WORDS = re.compile(r'(?i)\b(utiliz|deduct|decrease|reduction|lapse|settle|payment|paid|vested|cancel|forfeit|recogni[sz]ed as revenue|revenue recogni|impair|amortiz|depreciat|write-?off|disposal|repurchas|dividend|withhold|expir|release|redemption|repay|used|charge-?off|sales of|sold)')


def rollforward_checks(FL, K, report_of_role, periods):
    """Opening + movements = closing, for every roll-forward the filing presents (each dimension member set too)."""
    durs = [p for p in periods if p[0] == 'd']
    for role, seq in FL.F['pre'].items():
        rid = report_of_role.get(role)
        for i, n in enumerate(seq):
            if n['pref'] != 'start':
                continue
            c = n['c']
            j = next((k for k in range(i + 1, len(seq)) if seq[k]['c'] == c and seq[k]['pref'] == 'end'), None)
            if j is None:
                continue
            bu = FL.unit(c)
            if not bu or '/' in bu or bu == 'pure':
                continue                                  # per-share prices and rates do not add up
            between = [m for m in seq[i + 1:j] if m['c'] != c and FL.unit(m['c']) == bu]
            same = [m for m in between if m['depth'] == n['depth']]
            moves = same if same and not all(m['pref'] == 'total' for m in same) else [m for m in between if m['depth'] == n['depth'] + 1]
            parents = {pc for rel in FL.F['cal'].values() for pc, ks in rel.items() if any(k in {x['c'] for x in moves} for k, _ in ks)}
            if any(m['pref'] != 'total' for m in moves):
                moves = [m for m in moves if m['pref'] != 'total' and m['c'] not in parents]   # subtotals would count twice
            left_out = [m for m in between if m not in moves]
            if not moves:
                continue
            layered = any(FL.by_c.get(m['c']) and all('i' in FL.ctx[f['ctx']] for f in FL.by_c[m['c']])
                          for m in between)              # other balances inside it: a roll-forward in layers
            bal = FL.crdr.get(c)
            dimsets = {tuple(sorted(FL.ctx[f['ctx']]['dims'].items())) for f in FL.by_c.get(c, [])}
            for p in durs:
                for dims in dimsets:
                    o = FL.num.get((c, ('i', (_d(p[1]) - DAY).isoformat()), dims)) or FL.num.get((c, ('i', p[1]), dims))
                    e = FL.num.get((c, ('i', p[2]), dims))
                    if not o or not e:
                        continue
                    vals = []
                    for m in moves:
                        r = FL.num.get((m['c'], p, dims))
                        if r is None:
                            continue
                        mb = FL.crdr.get(m['c'])
                        lab = FL.label(m['c'], m['pref'] if m['pref'] not in ('start', 'end') else None)
                        if m['pref'] in ('negated',):
                            s = -1
                        elif bal and mb:
                            s = 1 if mb == bal else -1
                        else:
                            s = -1 if MINUS_WORDS.search(lab) else 1
                        vals.append([lab, m['c'], r[0], s, r[1]])
                    if not vals:
                        continue
                    elsewhere = {m['c'] for m in moves if any(k[0] == m['c'] and k[1] == p for k in FL.num)}
                    target = e[0] - o[0]
                    if len({x[1] for x in vals}) < len(elsewhere) and _status(target - sum(x[3] * x[2] for x in vals), 0, e[0]) != 'tie':
                        continue                          # some movements are reported only by member: not a check here
                    tol0 = sum(Filing.tol_of(x[4]) for x in vals) + Filing.tol_of(o[1]) + Filing.tol_of(e[1])
                    if left_out and len(vals) <= 12 and not any(abs(target - sum(sg * x[2] for sg, x in zip(sgs, vals))) <= tol0 + 1e-6
                                                             for sgs in itertools.product((1, -1), repeat=len(vals))):
                        continue                          # lines at other levels carry part of the movement: not a check
                    tol = sum(Filing.tol_of(x[4]) for x in vals) + Filing.tol_of(o[1]) + Filing.tol_of(e[1])
                    if _status(target - sum(x[3] * x[2] for x in vals), tol, e[0]) == 'gap' and len(vals) <= 12:
                        best = None                      # the signs the numbers fit, closest to the first guess
                        for signs in itertools.product((1, -1), repeat=len(vals)):
                            if abs(target - sum(s * x[2] for s, x in zip(signs, vals))) <= tol + 1e-6:
                                flips = sum(s != x[3] for s, x in zip(signs, vals))
                                if best is None or flips < best[0]:
                                    best = (flips, signs)
                        if best:
                            for s, x in zip(best[1], vals):
                                x[3] = s
                    if layered and _status(target - sum(x[3] * x[2] for x in vals), tol, e[0]) == 'gap':
                        continue                          # its layers move between other balances: not a check of this one
                    parts = [('Opening balance', c, o[0], 1, o[1])] + [tuple(x) for x in vals]
                    t = FL.label(c, 'total')
                    if dims:
                        t += ' — ' + ', '.join(FL.label(mm) for _, mm in dims)
                    ch = K.add('rollfwd', t + ' (roll-forward)', parts, ('Closing balance', c, e[0], e[1]), where=[rid] if rid else [], period=p,
                               key=('roll', c, p, dims))
                    if ch and ch['status'] == 'gap':
                        ch['explain'] = ('Recomputed from the lines tagged in the XBRL. A movement tagged with another element, only by member or only '
                                         'inside a subtotal leaves the tagged lines short of the closing balance even when the printed table adds up.')


CHART_SKIP_AXES = re.compile(r'(?i)(EquityComponents|SubsequentEvent|BalanceSheetLocation|DerivativeInstrumentRisk)')
AXIS_NAMES = {'StatementGeographicalAxis': 'region', 'StatementBusinessSegmentsAxis': 'segment', 'ProductOrServiceAxis': 'product or market',
              'IncomeStatementLocationAxis': 'income statement line', 'LongtermDebtTypeAxis': 'note', 'DebtInstrumentAxis': 'instrument',
              'FinancialInstrumentAxis': 'type of security', 'PropertyPlantAndEquipmentByTypeAxis': 'asset class', 'FiniteLivedIntangibleAssetsByMajorClassAxis': 'class',
              'IncomeTaxAuthorityAxis': 'jurisdiction', 'OtherCommitmentsAxis': 'commitment', 'AwardTypeAxis': 'award type', 'StatementEquityComponentsAxis': 'equity component',
              'ValuationAllowancesAndReservesTypeAxis': 'account', 'BusinessAcquisitionAxis': 'acquisition', 'SegmentsAxis': 'segment'}


def axis_name(FL, ax):
    return AXIS_NAMES.get(ax.split(':')[-1]) or FL.label(ax).replace(' [Axis]', '').lower()


NON_ADDITIVE_AXES = re.compile(r'(?i)(Range|Concentration|MajorCustomers|StatementScenario|Award|Plan|Title|Individual|Hedging|Subsequent|Legal|Restatement|Adjustment|Creation|Retirement|RelatedParty|Grantee|Vesting)')


def member_checks(FL, K, report_of_role, periods):
    """A dimension's members against their total (nested members too), when every member is reported."""
    for role, d in FL.F['def'].items():
        rid = report_of_role.get(role)
        seq = FL.F['pre'].get(role) or []
        concepts = [n['c'] for n in seq if not re.search(r'(Table|Axis|Domain|Member|LineItems|Abstract)$', n['c'])]
        for ax, mem in d['axes'].items():
            if NON_ADDITIVE_AXES.search(ax) or len(mem) < 3:
                continue
            # the member tree from the definition arcs is flattened in `mem`; rebuild parent → children from the presentation
            kids = {}
            pre_mem = [n for n in seq if n['c'] in mem]
            stack = []
            for n in pre_mem:
                while stack and stack[-1]['depth'] >= n['depth']:
                    stack.pop()
                if stack:
                    kids.setdefault(stack[-1]['c'], []).append(n['c'])
                stack.append(n)
            domain = mem[0]
            for parent, children in kids.items():
                if len(children) < 2:
                    continue
                for c in concepts:
                    u = FL.unit(c)
                    if u not in ('USD', 'shares') and not (u or '').startswith(('USD', 'EUR', 'GBP', 'JPY', 'CAD')):
                        continue
                    if '/' in (u or ''):
                        continue
                    for p in periods:
                        others = {}
                        base = None
                        for (cc, pp, dims), r in FL.num.items():
                            if cc != c or pp != p:
                                continue
                            dd = dict(dims)
                            if parent == domain and ax not in dd:
                                rest = tuple(sorted(dd.items()))
                                others.setdefault(rest, {})['__total__'] = r
                            elif dd.get(ax) in children + [parent]:
                                rest = tuple(sorted((k, v) for k, v in dd.items() if k != ax))
                                others.setdefault(rest, {})[dd[ax]] = r
                        for rest, got in others.items():
                            tot = got.get(parent) or got.get('__total__')
                            if tot is None or not all(ch in got for ch in children):
                                continue
                            parts = [(FL.label(ch), c, got[ch][0], 1, got[ch][1]) for ch in children]
                            calc = sum(x[2] for x in parts)
                            if abs(calc - tot[0]) > 0.02 * max(abs(tot[0]), 1) and abs(calc) < abs(tot[0]):
                                continue                  # not every member listed: a partial split, not a check
                            pl = FL.label(parent) if parent != domain else 'Total'
                            title = f"{FL.label(c, 'total')} by {FL.label(ax).replace(' [Axis]', '')}" + (f' ({pl})' if parent != domain else '')
                            if rest:
                                title += ' — ' + ', '.join(FL.label(m) for _, m in rest)
                            K.add('members', title, parts, (pl, c, tot[0], tot[1]), where=[rid] if rid else [], period=p,
                                  key=('mem', c, ax, parent, p, rest), info=True,
                                  explain='Members can overlap or be netted (netting of derivatives, eliminations between segments, items shown under more than one member).')


def first(FL, names, p, dims=()):
    """The first of several concepts with a value for period p (a bare local name: us-gaap first, then any prefix)."""
    if p is None:
        return None
    for nm in names:
        cands = [nm] if ':' in nm else ['us-gaap:' + nm] + [c for c in FL.by_local.get(nm, []) if not c.startswith('us-gaap:')]
        for c in cands:
            r = FL.num.get((c, p, dims))
            if r is not None:
                return c, r[0], r[1]
    return None


CF_END_CASH = ['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', 'CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsAndShortTermInvestments']
WC = [('Accounts receivable', ['AccountsReceivableNetCurrent', 'ReceivablesNetCurrent', 'AccountsNotesAndLoansReceivableNetCurrent'], ['IncreaseDecreaseInAccountsReceivable', 'IncreaseDecreaseInReceivables', 'IncreaseDecreaseInAccountsAndNotesReceivable'], 1),
      ('Inventories', ['InventoryNet', 'InventoryGross'], ['IncreaseDecreaseInInventories'], 1),
      ('Prepaid expenses and other current assets', ['PrepaidExpenseAndOtherAssetsCurrent', 'PrepaidExpenseCurrent', 'OtherAssetsCurrent'], ['IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets', 'IncreaseDecreaseInPrepaidExpense', 'IncreaseDecreaseInOtherCurrentAssets', 'IncreaseDecreaseInPrepaidExpensesOther'], 1),
      ('Accounts payable', ['AccountsPayableCurrent', 'AccountsPayableTradeCurrent'], ['IncreaseDecreaseInAccountsPayable', 'IncreaseDecreaseInAccountsPayableTrade'], 1),
      ('Accrued liabilities', ['AccruedLiabilitiesCurrent', 'AccountsPayableAndAccruedLiabilitiesCurrent', 'OtherLiabilitiesCurrent'], ['IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities', 'IncreaseDecreaseInAccruedLiabilities', 'IncreaseDecreaseInAccountsPayableAndAccruedLiabilities', 'IncreaseDecreaseInOtherCurrentLiabilities'], 1),
      ('Deferred revenue', ['ContractWithCustomerLiability'], ['IncreaseDecreaseInContractWithCustomerLiability', 'IncreaseDecreaseInDeferredRevenue'], 1)]
WC_EXPLAIN = {'Accrued liabilities': [('BusinessCombinationConsiderationPayable', 'amounts still owed for acquisitions')],
              'Accounts payable': [('CapitalExpendituresIncurredButNotYetPaid', 'capital spending not yet paid')]}


def tie_checks(FL, K, where_of):
    y, p0 = FL.dur(0), FL.dur(1)
    pairs = [(FL.dur(0), FL.inst(0), FL.opening(0))]
    if p0:
        pairs.append((FL.dur(1), FL.inst(1), FL.opening(1)))
    W = lambda *cs: sorted({w for c in cs for w in where_of.get(c, [])})
    for dur, end, opening in pairs:
        # the balance sheet balances
        a = first(FL, ['Assets'], end)
        le = first(FL, ['LiabilitiesAndStockholdersEquity'], end)
        if a and le:
            K.add('tie', 'Total assets = total liabilities and equity', [(FL.label(le[0], 'total'), le[0], le[1], 1, le[2])], (FL.label(a[0], 'total'), a[0], a[1], a[2]),
                  where=W(a[0]), period=end, key=('bs', end))
        # cash: the cash flow statement's ending cash = the balance sheet's (with any restricted cash)
        cfe = first(FL, CF_END_CASH[:1], end)
        bsc = first(FL, ['CashAndCashEquivalentsAtCarryingValue'], end)
        if cfe and bsc:
            parts = [(FL.label(bsc[0]), bsc[0], bsc[1], 1, bsc[2])]
            for nm in ('RestrictedCashCurrent', 'RestrictedCashNoncurrent', 'RestrictedCashAndCashEquivalentsAtCarryingValue', 'RestrictedCashAndCashEquivalentsNoncurrent', 'RestrictedCash'):
                r = first(FL, [nm], end)
                if r:
                    parts.append((FL.label(r[0]), r[0], r[1], 1, r[2]))
            K.add('tie', 'Cash at the end of the cash flow statement = cash on the balance sheet', parts, ('Ending cash (cash flow statement)', cfe[0], cfe[1], cfe[2]),
                  where=W(cfe[0], bsc[0]), period=end, key=('cash', end), info=True,
                  explain='Restricted cash, and cash held in assets for sale, sit outside "cash and cash equivalents" on the balance sheet; the cash flow statement counts them.')
        # cash in banks: cash and equivalents less the money-market and securities counted as equivalents
        ce = first(FL, ['CashEquivalentsAtCarryingValue'], end)
        # stock-based compensation in the cash flow statement, the note and the equity statement
        sbc = first(FL, ['ShareBasedCompensation'], dur)
        for nm, title in (('AllocatedShareBasedCompensationExpense', 'Stock-based compensation: cash flow statement = the note'),
                          ('AdjustmentsToAdditionalPaidInCapitalSharebasedCompensationRequisiteServicePeriodRecognitionValue', 'Stock-based compensation: cash flow statement = equity statement')):
            o = first(FL, [nm], dur)
            if sbc and o and o[0] != sbc[0]:
                K.add('tie', title, [(FL.label(o[0]), o[0], o[1], 1, o[2])], (FL.label(sbc[0]), sbc[0], sbc[1], sbc[2]), where=W(sbc[0], o[0]), period=dur, key=('sbc', nm, dur),
                      explain='The equity statement can include compensation capitalized into inventory or assets, or awards assumed in acquisitions.', info=True)
        # dividends and buybacks: the equity statement against the cash paid
        for names_eq, names_cf, title, why in (
                (['DividendsCommonStockCash', 'DividendsCommonStock', 'Dividends'], ['PaymentsOfDividendsCommonStock', 'PaymentsOfDividends'], 'Dividends declared (equity statement) vs paid (cash flow statement)',
                 'Dividends declared but not yet paid at year end, or dividend equivalents on unvested awards.'),
                (['StockRepurchasedAndRetiredDuringPeriodValue', 'TreasuryStockValueAcquiredCostMethod', 'StockRepurchasedDuringPeriodValue'], ['PaymentsForRepurchaseOfCommonStock', 'PaymentsForRepurchaseOfEquity'],
                 'Shares repurchased (equity statement) vs cash paid (cash flow statement)',
                 'Repurchases traded but not yet settled at year end, and the 1% U.S. excise tax on buybacks, which is recorded in equity but paid later.')):
            e_ = first(FL, names_eq, dur)
            c_ = first(FL, names_cf, dur)
            if e_ and c_:
                K.add('tie', title, [(FL.label(c_[0]), c_[0], c_[1], 1, c_[2])], (FL.label(e_[0]), e_[0], e_[1], e_[2]), where=W(e_[0], c_[0]), period=dur, key=('cap', names_eq[0], dur), explain=why, info=True)
        # depreciation and amortization
        da = first(FL, ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'DepreciationAndAmortization'], dur)
        dep = first(FL, ['Depreciation', 'DepreciationNonproduction'], dur)
        am = first(FL, ['AmortizationOfIntangibleAssets'], dur)
        if da and dep and am:
            K.add('tie', 'Depreciation and amortization (cash flow statement) = depreciation + intangible amortization (notes)',
                  [(FL.label(dep[0]), dep[0], dep[1], 1, dep[2]), (FL.label(am[0]), am[0], am[1], 1, am[2])], (FL.label(da[0]), da[0], da[1], da[2]),
                  where=W(da[0], dep[0], am[0]), period=dur, key=('da', dur),
                  explain='The cash flow line can also hold amortization of capitalized software, debt costs or other assets.', info=True)
        # tax: the effective rate, and cash paid against current tax
        tax = first(FL, ['IncomeTaxExpenseBenefit'], dur)
        pre = first(FL, ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
                         'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic'], dur)
        etr = first(FL, ['EffectiveIncomeTaxRateContinuingOperations'], dur)
        if tax and pre and etr and pre[1]:
            K.add('tie', 'Effective tax rate = income tax ÷ income before tax', [(f'{FL.label(tax[0])} ÷ {FL.label(pre[0])}', tax[0], tax[1] / pre[1], 1, 4)],
                  (FL.label(etr[0]), etr[0], etr[1], min(etr[2] if etr[2] is not None else 3, 3)), where=W(tax[0], etr[0]), period=dur, key=('etr', dur))
        # EPS
        ni = first(FL, ['NetIncomeLossAvailableToCommonStockholdersBasic', 'NetIncomeLoss'], dur)
        for sh_names, eps_names, title in ((['WeightedAverageNumberOfSharesOutstandingBasic'], ['EarningsPerShareBasic', 'EarningsPerShareBasicAndDiluted'], 'Basic EPS = net income ÷ basic weighted shares'),
                                           (['WeightedAverageNumberOfDilutedSharesOutstanding'], ['EarningsPerShareDiluted', 'EarningsPerShareBasicAndDiluted'], 'Diluted EPS = net income ÷ diluted weighted shares')):
            sh, eps = first(FL, sh_names, dur), first(FL, eps_names, dur)
            if ni and sh and eps and sh[1]:
                K.add('tie', title, [(f'{FL.label(ni[0])} ÷ shares', ni[0], ni[1] / sh[1], 1, 3)], (FL.label(eps[0]), eps[0], eps[1], eps[2] if eps[2] is not None else 2),
                      where=W(eps[0], sh[0]), period=dur, key=('eps', eps_names[0], dur), info=True,
                      explain='EPS divides the income left to common shareholders: after preferred dividends and the earnings allocated to '
                              'participating securities (the two-class method), and for diluted EPS with dilutive items added back.')
        # splits into current + long-term
        for tot, cur, non, title in ((['LongTermDebt', 'DebtLongtermAndShorttermCombinedAmount'], ['LongTermDebtCurrent', 'DebtCurrent'], ['LongTermDebtNoncurrent'], 'Debt = short-term portion + long-term debt'),
                                     (['OperatingLeaseLiability'], ['OperatingLeaseLiabilityCurrent'], ['OperatingLeaseLiabilityNoncurrent'], 'Operating lease liabilities = current + long-term'),
                                     (['FinanceLeaseLiability'], ['FinanceLeaseLiabilityCurrent'], ['FinanceLeaseLiabilityNoncurrent'], 'Finance lease liabilities = current + long-term'),
                                     (['ContractWithCustomerLiability'], ['ContractWithCustomerLiabilityCurrent'], ['ContractWithCustomerLiabilityNoncurrent'], 'Deferred revenue = current + long-term'),
                                     (['ProductWarrantyAccrual'], ['ProductWarrantyAccrualClassifiedCurrent'], ['ProductWarrantyAccrualNoncurrent'], 'Warranty liability = current + long-term'),
                                     (['IntangibleAssetsNetExcludingGoodwill'], ['FiniteLivedIntangibleAssetsNet'], ['IndefiniteLivedIntangibleAssetsExcludingGoodwill'], 'Intangible assets on the balance sheet = finite-lived + indefinite-lived (note)')):
            t_, c_ = first(FL, tot, end), first(FL, cur, end)
            n_ = first(FL, non, end)
            if t_ and c_ and n_:
                parts = [(FL.label(c_[0]), c_[0], c_[1], 1, c_[2]), (FL.label(n_[0]), n_[0], n_[1], 1, n_[2])]
                K.add('tie', title, parts, (FL.label(t_[0], 'total'), t_[0], t_[1], t_[2]), where=W(t_[0], c_[0], n_[0]), period=end, key=('split', tot[0], end), info=True,
                      explain='The total and its two parts can be defined differently (a total at face value against carrying amounts, or a total for one '
                              'business only); the difference is the definition, not an error.')
        # goodwill: the change against the movement disclosed
        if opening:
            g1, g0 = first(FL, ['Goodwill'], end), first(FL, ['Goodwill'], opening)
            gm = first(FL, ['GoodwillPeriodIncreaseDecrease'], dur)
            if g1 and g0 and gm:
                K.add('tie', 'Goodwill: opening + change in the year = closing', [('Opening goodwill', g0[0], g0[1], 1, g0[2]), (FL.label(gm[0]), gm[0], gm[1], 1, gm[2])],
                      ('Closing goodwill', g1[0], g1[1], g1[2]), where=W(g1[0], gm[0]), period=dur, key=('gw', dur))
            # accumulated other comprehensive income moves by other comprehensive income
            aoci1, aoci0 = first(FL, ['AccumulatedOtherComprehensiveIncomeLossNetOfTax'], end), first(FL, ['AccumulatedOtherComprehensiveIncomeLossNetOfTax'], opening)
            ocis = [x for x in (first(FL, [nm], dur) for nm in ('OtherComprehensiveIncomeLossNetOfTaxPortionAttributableToParent', 'OtherComprehensiveIncomeLossNetOfTax',
                                                                'OtherComprehensiveIncomeLossNetOfTaxIncludingPortionAttributableToNoncontrollingInterest')) if x]
            oci = None
            if aoci1 and aoci0 and ocis:                 # the version of other comprehensive income that closes the balance, else the first
                oci = min(ocis, key=lambda x: abs(aoci1[1] - aoci0[1] - x[1]))
            if aoci1 and aoci0 and oci:
                K.add('tie', 'Accumulated OCI: opening + other comprehensive income = closing', [('Opening AOCI', aoci0[0], aoci0[1], 1, aoci0[2]), (FL.label(oci[0]), oci[0], oci[1], 1, oci[2])],
                      ('Closing AOCI', aoci1[0], aoci1[1], aoci1[2]), where=W(aoci1[0], oci[0]), period=dur, key=('aoci', dur), info=True,
                      explain='Accumulated OCI also moves by amounts booked to it directly: the effect of adopting a new standard, balances moved to '
                              'retained earnings, the share of noncontrolling interests, businesses sold or bought.')
            # balance sheet changes against the cash flow statement's working-capital lines
            for name, bs_names, cf_names, sign in WC:
                b1, b0 = first(FL, bs_names, end), None
                if b1:
                    b0 = first(FL, [b1[0]], opening)
                cf = first(FL, cf_names, dur)
                if not (b1 and b0 and cf):
                    continue
                delta = b1[1] - b0[1]
                gap = delta - cf[1]
                why = ['The cash flow line leaves out balances that came with acquisitions, amounts that are not cash (owed for acquisitions or '
                       'capital spending, reclassified between lines) and currency moves.']
                for nm, what in WC_EXPLAIN.get(name, []):
                    x1, x0 = first(FL, [nm], end), first(FL, [nm], opening)
                    if x1 is None:
                        x1 = first(FL, [nm], dur)
                        x0 = first(FL, [nm], FL.dur(1) if dur == FL.dur(0) else None) if x1 else None
                    if x1 and x0:
                        dx = x1[1] - x0[1]
                        if abs(dx) > 0.25 * abs(gap) and abs(gap) > 0:
                            why.append(f'{what.capitalize()} rose by {dx / 1e6:,.0f} million' if dx > 0 else f'{what.capitalize()} fell by {-dx / 1e6:,.0f} million')
                K.add('cf_bs', f'{name}: change on the balance sheet vs the cash flow statement', [(FL.label(cf[0]), cf[0], cf[1], 1, cf[2])],
                      (f'Change in {FL.label(b1[0])}', b1[0], delta, min([d for d in (b1[2], b0[2]) if d is not None], default=None)),
                      where=W(b1[0], cf[0]), period=dur, key=('wc', name, dur), explain=' '.join(why), info=True)


GENERIC_TOKENS = {'liability', 'liabilities', 'asset', 'assets', 'amount', 'net', 'current', 'noncurrent', 'total', 'value', 'other', 'and', 'of', 'the',
                  'in', 'for', 'to', 'including', 'excluding', 'gross', 'carrying', 'fair', 'balance', 'period', 'per', 'at', 'from', 'with', 'without'}


def name_tokens(c):
    return {t.lower() for t in re.findall(r'[A-Z][a-z]+|[a-z]+', c.split(':')[-1])} - GENERIC_TOKENS


def value_match_checks(FL, K, statements, notes):
    """A note's figure filed under a different concept than the statement line it explains, at the same date and to the
    same value (e.g. a roll-forward's closing balance and the balance sheet line): a link and a tie."""
    periods = [p for p in (FL.inst(0), FL.dur(0)) if p]
    assets = FL.v('us-gaap:Assets', FL.inst(0)) or 0
    floor = max(1e6, 0.0005 * abs(assets))
    st_vals = {}
    for s in statements:
        for n in FL.F['pre'].get(s['report']['role'], []):
            for p in periods:
                r = FL.num.get((n['c'], p, ()))
                if r and abs(r[0]) >= floor and (FL.unit(n['c']) or '').startswith('USD') and '/' not in (FL.unit(n['c']) or ''):
                    st_vals.setdefault(p, []).append((n['c'], r, s['report']['r']))
    for nt in notes:
        for d in nt['details']:
            for n in FL.F['pre'].get(d['role'], []):
                for p in periods:
                    r = FL.num.get((n['c'], p, ()))
                    if not r or abs(r[0]) < floor:
                        continue
                    if Filing.tol_of(r[1]) > 5e5:
                        continue                          # a figure rounded to billions matches too much
                    toks = name_tokens(n['c'])
                    hits = [(c, rr, sid) for c, rr, sid in st_vals.get(p, []) if c != n['c'] and Filing.tol_of(rr[1]) <= 5e5
                            and abs(rr[0] - r[0]) <= Filing.tol_of(rr[1]) + Filing.tol_of(r[1]) and toks & name_tokens(c)]
                    hits = list({c: (c, rr, sid) for c, rr, sid in hits}.values())
                    if len(hits) != 1 or n['c'] in {c for c, _, _ in st_vals.get(p, [])}:
                        continue
                    c, rr, sid = hits[0]
                    K.add('tie', f"{FL.label(n['c'], 'total')} (note) = {FL.label(c)} (statement)", [(FL.label(n['c'], 'total'), n['c'], r[0], 1, r[1])],
                          (FL.label(c), c, rr[0], rr[1]), where=[d['r'], sid], period=p, key=('vm', n['c'], c, p))


def dup_checks(FL, K):
    for key, a, b in getattr(FL, 'dups', [])[:40]:
        c, p, dims = key
        K.add('dup', f'{FL.label(c)} reported twice', [(f'reported as {b[0]:,.0f}', c, b[0], 1, b[1])], (f'reported as {a[0]:,.0f}', c, a[0], a[1]), period=p, key=('dup', key))


# ------------------------------------------------------------------ charts
SCHEDULE = re.compile(r'(NextTwelveMonths|NextRollingTwelveMonths|InYearTwo|InYearThree|InYearFour|InYearFive|YearTwo|YearThree|YearFour|YearFive|SecondYear|ThirdYear|FourthYear|FifthYear|AfterYearFive|Thereafter|AfterFifthYear|RemainderOfFiscalYear|DueInNext|DueInSecond|DueInThird|DueInFourth|DueInFifth|DueAfter)')


def _num_rows(T):
    return [(i, r) for i, r in enumerate(T['rows']) if not r['abstract']]


def _fit_signs(steps, target, tol):
    """Signs for unsigned movements that make them add up to target (closest to the first guess); steps [[label, v]]."""
    if abs(sum(x[1] for x in steps) - target) <= tol or len(steps) > 12:
        return steps
    best = None
    for signs in itertools.product((1, -1), repeat=len(steps)):
        if abs(sum(sg * abs(x[1]) for sg, x in zip(signs, steps)) - target) <= tol:
            flips = sum((sg > 0) != (x[1] > 0) for sg, x in zip(signs, steps))
            if best is None or flips < best[0]:
                best = (flips, signs)
    return [[x[0], sg * abs(x[1])] for sg, x in zip(best[1], steps)] if best else steps


def _waterfalls(FL, T):
    rows, cols, cells = T['rows'], T['cols'], T['cells']
    out = []
    for si, r in enumerate(rows):
        if r['pref'] != 'start' or (r['u'] or '').count('/') or r['u'] == 'pure':
            continue
        ei = next((i for i in range(si + 1, len(rows)) if rows[i]['c'] == r['c'] and rows[i]['pref'] == 'end'), None)
        if ei is None:
            continue
        cands = []
        for j, col in enumerate(cols):
            if col['kind'] != 'd' or cells[si][j] is None or cells[ei][j] is None:
                continue
            steps = []
            for i in range(si + 1, ei):
                v = cells[i][j]
                if v is None or rows[i]['abstract'] or rows[i]['u'] != r['u']:
                    continue
                cb, cm = FL.crdr.get(r['c']), FL.crdr.get(rows[i]['c'])
                sg = -1 if rows[i]['pref'] == 'negated' else (1 if cm == cb else -1) if (cb and cm) else (-1 if MINUS_WORDS.search(rows[i]['label']) else 1)
                steps.append([rows[i]['label'], sg * v])
            if not steps:
                continue
            target = cells[ei][j] - cells[si][j]
            steps = _fit_signs(steps, target, 0.002 * max(1.0, abs(cells[ei][j])) + 1)
            cands.append((col['e'], sum(abs(x[1]) for x in steps), j, steps))
        if not cands:
            continue
        latest = max(c[0] for c in cands)
        cands = sorted([c for c in cands if c[0] == latest], key=lambda c: -c[1])[:3]      # the latest year; members with the most movement
        for e, _, j, steps in cands:
            out.append({'type': 'waterfall', 'unit': r['u'], 'period': e, 'member': cols[j]['label'], 'title': r['label'],
                        'start': ['Opening', cells[si][j]], 'steps': steps, 'end': ['Closing', cells[ei][j]]})
    return out


def _rate_bridge(FL, T, role):
    """Statutory → effective tax rate, from the reconciliation's dollar amounts (their calculation weights give the signs)
    as points of income before tax; the latest year whose items add up."""
    rows, cols, cells = T['rows'], T['cols'], T['cells']
    rels = [FL.F['cal'].get(role) or {}] + [r for k, r in FL.F['cal'].items() if k != role]      # its own calculation, else the filing's
    parent = kids = None
    for rel in rels:                                  # the dollar reconciliation (the percent one rounds to 0.1 point)
        parent = next((pc for pc, ks in rel.items() if any('AtFederalStatutoryIncomeTaxRate' in ch for ch, _ in ks) and (FL.unit(pc) or '').startswith('USD')), None)
        if parent:
            kids = list(rel[parent])
            break
    if not parent:
        return None
    known = {ch for ch, _ in kids}
    for r in rows:                                    # lines the calculation does not name: their sign is fitted below
        if not r['abstract'] and r['c'] != parent and r['c'] not in known and r['u'] == FL.unit(parent) and r['c'].split(':')[-1].startswith(('IncomeTaxReconciliation', 'EffectiveIncomeTaxRateReconciliation')):
            kids.append((r['c'], None))
    stat = next(ch for ch, _ in kids if 'AtFederalStatutoryIncomeTaxRate' in ch)
    pos = {r['c']: i for i, r in enumerate(rows) if not r['abstract']}
    if parent not in pos or stat not in pos:
        return None
    for j, col in enumerate(cols):
        if col['dims'] or col['kind'] != 'd':
            continue
        S, E = cells[pos[stat]][j], cells[pos[parent]][j]
        if not S or E is None:
            continue
        pre = S / 0.21 if abs(S) > 0 else None
        variants = []
        for mode in ('prefer_total', 'all'):             # a total with its members, or the members as lines of their own
            steps = []
            for ch, wt in kids:
                if ch == stat or ch not in pos:
                    continue
                vals = [(cols[k]['label'], cells[pos[ch]][k]) for k in range(len(cols)) if cols[k]['e'] == col['e'] and cols[k]['s'] == col['s']
                        and cells[pos[ch]][k] not in (None, 0) and len(cols[k]['dims']) <= 1]
                nodim = [v for lab, v in vals if not lab]
                use = ([('', nodim[0])] if nodim else vals) if mode == 'prefer_total' else vals
                for lab, v in use:
                    steps.append([rows[pos[ch]]['label'] + (f' — {lab}' if lab else ''), (wt if wt is not None else 1) * v / pre, wt is None])
            free = [k for k, x in enumerate(steps) if x[2]]
            target = (E - S) / pre - sum(x[1] for x in steps if not x[2])
            if free and len(free) <= 10:                  # unsigned lines: the signs that close the bridge, fewest flips first
                best = None
                for signs in itertools.product((1, -1), repeat=len(free)):
                    tot = sum(sg * steps[k][1] for sg, k in zip(signs, free))
                    if abs(target - tot) <= 0.0015:
                        flips = sum(sg < 0 for sg in signs)
                        if best is None or flips < best[0]:
                            best = (flips, signs)
                if best:
                    for sg, k in zip(best[1], free):
                        steps[k][1] *= sg
            steps = [x[:2] for x in steps]
            variants.append((abs((E - S) / pre - sum(x[1] for x in steps)), steps))
        steps = min(variants, key=lambda x: x[0])[1]
        gap = (E - S) / pre - sum(x[1] for x in steps)
        if abs(gap) > 0.0015 or len(steps) < 2:
            continue
        steps = [x for x in steps if abs(x[1]) >= 0.0005] + ([['Not itemized', gap]] if abs(gap) >= 0.0005 else [])
        return {'type': 'waterfall', 'unit': 'pure', 'period': col['e'], 'member': '', 'title': 'Effective tax rate', 'rate': 1,
                'start': ['Statutory rate', S / pre], 'steps': steps, 'end': ['Effective rate', E / pre]}
    return None


def _schedule(FL, T):
    rows, cols, cells = T['rows'], T['cols'], T['cells']
    sch = [(i, r) for i, r in _num_rows(T) if SCHEDULE.search(r['c']) or re.fullmatch(r'(?i)(fiscal )?(year )?20\d\d( and thereafter)?|thereafter|remainder of.*', r['label'].strip())]
    if len(sch) < 3:
        return None
    series = []
    for j in range(len(cols)):
        vals = [[r['label'], cells[i][j]] for i, r in sch if cells[i][j] is not None]
        if len(vals) >= 3:
            series.append({'name': cols[j]['label'] or 'Total', 'values': vals})
    return {'type': 'schedule', 'unit': sch[0][1]['u'], 'period': cols[0]['e'], 'series': series[:6]} if series else None


def _calc_charts(FL, T, role):
    """Totals with their parts in the report's own calculation: all parts added → composition (this year and last);
    some subtracted → bridge (a waterfall from the first part to the total)."""
    rows, cols, cells = T['rows'], T['cols'], T['cells']
    rel = FL.F['cal'].get(role) or {}
    pos = {r['c']: i for i, r in enumerate(rows) if not r['abstract']}
    nd = [j for j, c in enumerate(cols) if not c['dims']]
    out = []
    for parent, kids in rel.items():
        if parent not in pos:
            continue
        i = pos[parent]
        js = [j for j in nd if cells[i][j] is not None]
        ends = sorted({cols[j]['e'] for j in js}, reverse=True)[:2]
        js = [next(j for j in js if cols[j]['e'] == e) for e in ends]
        present = sorted([(ch, wt) for ch, wt in kids if ch in pos and js and cells[pos[ch]][js[0]] is not None], key=lambda x: pos[x[0]])
        if len(present) < 2 or not js:
            continue
        if all(wt > 0 for _, wt in present):
            tl = rows[i]['label'] if rows[i]['label'].strip().lower() not in ('total', 'totals') else FL.label(parent, 'label')
            out.append({'type': 'composition', 'unit': rows[i]['u'], 'total': tl, 'periods': ends,
                        'parts': [[rows[pos[ch]]['label'], [cells[pos[ch]][j] for j in js]] for ch, wt in present], 'totals': [cells[i][j] for j in js]})
        elif pos[parent] > max(pos[ch] for ch, _ in present) and len(present) == len([k for k in kids if k[0] in pos]) and abs(
                sum(wt * cells[pos[ch]][js[0]] for ch, wt in present) - cells[i][js[0]]) <= 0.002 * max(1.0, abs(cells[i][js[0]])) + 1:
            j = js[0]
            first_ = present[0]
            out.append({'type': 'waterfall', 'unit': rows[i]['u'], 'period': cols[j]['e'], 'member': '', 'title': rows[i]['label'], 'bridge': 1,
                        'start': [rows[pos[first_[0]]]['label'], first_[1] * cells[pos[first_[0]]][j]],
                        'steps': [[rows[pos[ch]]['label'], wt * cells[pos[ch]][j]] for ch, wt in present[1:]], 'end': [rows[i]['label'], cells[i][j]]})
    # the outermost totals first (the one whose parts are not themselves parts of another)
    return out


def _members(FL, T, role):
    rows, cols, cells = T['rows'], T['cols'], T['cells']
    seq = FL.F['pre'].get(role) or []
    d = FL.F['def'].get(role) or {'axes': {}}
    depth = {n['c']: n['depth'] for n in seq}
    out = []
    for ax, mem in d['axes'].items():
        if NON_ADDITIVE_AXES.search(ax) or CHART_SKIP_AXES.search(ax):
            continue
        mcols = [j for j, c in enumerate(cols) if ax in c['dims'] and (len(c['dims']) == 1 or (len(c['dims']) == 2 and all(
            a == ax or re.search(r'(FairValueByFairValueHierarchyLevel|ConsolidationItems)', a) for a in c['dims'])))]
        if len(mcols) < 2:
            continue
        best = None
        for i, r in _num_rows(T):
            if (r['u'] or '') not in ('USD', 'shares'):
                continue
            got = [j for j in mcols if cells[i][j] is not None]
            names = {cols[j]['dims'][ax] for j in got}
            if any(cells[i][j] < 0 for j in got):
                continue                                  # a split with negative parts reads better as a table
            if len(names) >= 2 and (best is None or len(names) > best[2]):
                best = (i, got, len(names))
        if not best:
            continue
        i, got, _ = best
        ends = sorted({cols[j]['e'] for j in got}, reverse=True)[:2]
        order = []
        for j in got:
            m = cols[j]['dims'][ax]
            if m not in order:
                order.append(m)
        base = min(depth.get(m, 9) for m in order)
        mlab = {n['c']: FL.label(n['c'], n['pref']) for n in seq if n['c'] in order}
        vals = [[mlab.get(m) or FL.label(m), [next((cells[i][j] for j in got if cols[j]['dims'][ax] == m and cols[j]['e'] == e), None) for e in ends],
                 depth.get(m, base) - base] for m in order]
        total = next((cells[i][j] for j in range(len(cols)) if not cols[j]['dims'] and cols[j]['e'] == ends[0] and cells[i][j] is not None), None)
        out.append({'type': 'members', 'unit': rows[i]['u'], 'row': rows[i]['label'], 'axis': axis_name(FL, ax), 'periods': ends, 'members': vals[:16], 'total': total})
    return out


def charts_for(FL, T, role):
    """Up to two charts for a detail report, the most telling first."""
    if not T['rows'] or not T['cols']:
        return []
    cands = []
    cands += _waterfalls(FL, T)
    rb = _rate_bridge(FL, T, role)
    if rb:
        return cands + [rb]
    sc = _schedule(FL, T)
    if sc:
        cands.append(sc)
    cands += _members(FL, T, role)
    cands += _calc_charts(FL, T, role)
    if not cands:
        figs = []
        for i, r in _num_rows(T):
            j = next((j for j in range(len(T['cols'])) if T['cells'][i][j] is not None), None)
            if j is not None:
                figs.append([r['label'] + (f" ({T['cols'][j]['label']})" if T['cols'][j]['label'] else ''), T['cells'][i][j], r['u'], T['cols'][j]['e']])
        return [{'type': 'figures', 'figures': figs[:14]}] if figs else []
    return cands[:3]


# ------------------------------------------------------------------ analysis
def pct(a, b):
    return (a / b - 1) if fin(a) and fin(b) and b else None


def fmt_money(v):
    if not fin(v):
        return '—'
    a = abs(v)
    s = '−' if v < 0 else ''
    if a >= 1e9:
        return f'{s}${a / 1e9:,.1f}B'
    if a >= 1e6:
        return f'{s}${a / 1e6:,.0f}M'
    return f'{s}${a:,.0f}'


def fmt_pct(v, d=0):
    return '—' if not fin(v) else f'{v * 100:+.{d}f}%'


def lc(t):
    """Lower-case a label's first letter unless it starts a name or an acronym ('Data Center', 'U.S.')."""
    return t[0].lower() + t[1:] if t and t[0].isupper() and (len(t) < 2 or t[1].islower()) and not re.match(r'(?i)(data center|united|china|taiwan|israel|europe|u\.s\.)', t) else t


def analyse_chart(ch, title):
    out = []
    if not ch:
        return out
    money = lambda v: fmt_money(v) if (ch.get('unit') or 'USD').startswith('USD') or ch.get('unit') is None else (f'{v * 100:.1f}%' if ch.get('unit') == 'pure' else (f'{v / 1e6:,.0f}M shares' if ch.get('unit') == 'shares' else f'{v:,.4g}'))
    t = ch['type']
    if t == 'waterfall' and ch.get('bridge'):
        out.append(f"{ch['start'][0]} {money(ch['start'][1])} → {lc(ch['end'][0])} {money(ch['end'][1])}" + (
            ': ' + ', '.join(f"{lc(x[0])} {'+' if x[1] > 0 else '−'}{money(abs(x[1]))}" for x in sorted(ch['steps'], key=lambda x: -abs(x[1]))[:2]) if ch['steps'] else '') + '.')
    elif t == 'composition' and len(ch['totals']) >= 1:
        tot = ch['totals']
        line = f"{ch['total']}: {money(tot[0])}"
        if len(tot) > 1 and fin(tot[1]) and tot[1]:
            line += f" ({fmt_pct(pct(tot[0], tot[1]))} on the year before)"
        parts = [(n, v[0]) for n, v in ch['parts'] if fin(v[0]) and v[0] > 0]
        pos_tot = sum(x[1] for x in parts)
        if len(parts) >= 2 and pos_tot:
            big = max(parts, key=lambda x: x[1])
            if big[1] / pos_tot < 0.95:
                line += f"; the largest part is {lc(big[0])} at {big[1] / pos_tot * 100:.0f}%"
        out.append(line + '.')
        if len(tot) > 1:
            mv = [(n, v[0] - v[1]) for n, v in ch['parts'] if fin(v[0]) and fin(v[1])]
            if mv:
                m = max(mv, key=lambda x: abs(x[1]))
                if abs(m[1]) > 0:
                    out.append(f"Biggest mover: {lc(m[0])} {'+' if m[1] > 0 else '−'}{money(abs(m[1]))}.")
    elif t == 'waterfall' and ch.get('unit') != 'pure':
        s, e = ch['start'][1], ch['end'][1]
        adds = sorted([x for x in ch['steps'] if x[1] > 0], key=lambda x: -x[1])
        subs = sorted([x for x in ch['steps'] if x[1] < 0], key=lambda x: x[1])
        line = f"From {money(s)} to {money(e)}"
        if fin(s) and s:
            line += f" ({fmt_pct(pct(e, s))})"
        if adds:
            line += f"; {lc(adds[0][0])} added {money(adds[0][1])}"
        if subs:
            line += f", {lc(subs[0][0])} took out {money(-subs[0][1])}"
        out.append(line + '.')
    elif t == 'waterfall':
        s, e = ch['start'][1], ch['end'][1]
        big = sorted(ch['steps'], key=lambda x: -abs(x[1]))[:2]
        out.append(f"From the statutory {s * 100:.1f}% to an effective {e * 100:.1f}%" + (
            ': ' + ', '.join(f"{lc(x[0])} {x[1] * 100:+.1f} pts" for x in big) if big else '') + '.')
    elif t == 'schedule':
        sr = ch['series'][0]
        vals = [v for _, v in sr['values'] if fin(v)]
        tot = sum(vals)
        if tot:
            out.append(f"{money(tot)} scheduled; {vals[0] / tot * 100:.0f}% in the first year" + (f", {vals[-1] / tot * 100:.0f}% in the last bucket ({lc(sr['values'][-1][0])})" if len(vals) > 2 else '') + '.')
    elif t == 'members':
        top = [m for m in ch['members'] if (m[2] if len(m) > 2 else 0) == 0]
        cur = [(m[0], m[1][0]) for m in top if fin(m[1][0])]
        if len(cur) >= 2:
            tot = ch.get('total') if fin(ch.get('total')) else sum(x[1] for x in cur)
            big = max(cur, key=lambda x: x[1])
            line = f"{ch['row']} by {ch.get('axis', 'member').lower()}: {big[0]} is the largest at {money(big[1])}" + (f" ({big[1] / tot * 100:.0f}% of the total)" if tot else '')
            if len(ch['periods']) > 1:
                gr = [(m[0], pct(m[1][0], m[1][1])) for m in ch['members'] if fin(m[1][0]) and fin(m[1][1]) and m[1][1] > 0]
                if gr:
                    hi, lo = max(gr, key=lambda x: x[1]), min(gr, key=lambda x: x[1])
                    line += f"; fastest growth {hi[0]} {fmt_pct(hi[1])}" + (f", slowest {lo[0]} {fmt_pct(lo[1])}" if lo[0] != hi[0] else '')
            out.append(line + '.')
    return out


def _p2(x):
    return f'{x:.2f}' if abs(x) < 1 else f'{x:.1f}'


def ratios(FL):
    """Ratios that put a note's numbers against the business — attached to the note whose concepts they use."""
    y, e, e0, o = FL.dur(0), FL.inst(0), FL.inst(1), FL.opening(0)
    v = lambda c, p: FL.v('us-gaap:' + c, p) if p else None
    rev = v('Revenues', y) or v('RevenueFromContractWithCustomerExcludingAssessedTax', y)
    rev0 = v('Revenues', FL.dur(1)) or v('RevenueFromContractWithCustomerExcludingAssessedTax', FL.dur(1))
    cogs = v('CostOfRevenue', y) or v('CostOfGoodsAndServicesSold', y)
    out = []

    def add(concept, text):
        out.append(('us-gaap:' + concept, text))
    inv, inv0 = v('InventoryNet', e), v('InventoryNet', e0)
    if inv and cogs:
        add('InventoryNet', f"Inventories cover {inv / cogs * 365:.0f} days of cost of revenue" + (f" (a year earlier {inv0 / v('CostOfRevenue', FL.dur(1)) * 365:.0f})" if inv0 and v('CostOfRevenue', FL.dur(1)) else '') +
            (f"; inventories grew {fmt_pct(pct(inv, inv0))} against revenue {fmt_pct(pct(rev, rev0))}" if inv0 and rev and rev0 else '') + '.')
    ar, ar0 = v('AccountsReceivableNetCurrent', e), v('AccountsReceivableNetCurrent', e0)
    if ar and rev:
        add('AccountsReceivableNetCurrent', f"Receivables equal {ar / rev * 365:.0f} days of revenue" + (f" (a year earlier {ar0 / rev0 * 365:.0f})" if ar0 and rev0 else '') + '.')
    w = v('ProductWarrantyAccrualWarrantiesIssued', y)
    if w and rev:
        add('ProductWarrantyAccrual', f"Warranty provisions were {_p2(w / rev * 100)}% of revenue" + (f" (a year earlier {_p2(v('ProductWarrantyAccrualWarrantiesIssued', FL.dur(1)) / rev0 * 100)}%)" if rev0 and v('ProductWarrantyAccrualWarrantiesIssued', FL.dur(1)) else '') + '.')
    sbc = v('ShareBasedCompensation', y) or v('AllocatedShareBasedCompensationExpense', y)
    if sbc and rev:
        add('AllocatedShareBasedCompensationExpense', f"Stock-based compensation was {sbc / rev * 100:.1f}% of revenue.")
    cmt = sum(x for x in (v('UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount', e), v('PurchaseObligation', e)) if x) or None
    oc = [r[0] for (c, p, dims), r in FL.num.items() if c == 'us-gaap:OtherCommitment' and p == e]
    if (oc or cmt) and cogs:
        tot = (cmt or 0) + sum(oc)
        add('OtherCommitment', f"Commitments disclosed total {fmt_money(tot)}, {tot / cogs:.1f}× a year's cost of revenue.")
    tax, pre = v('IncomeTaxExpenseBenefit', y), v('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', y)
    paid = v('IncomeTaxesPaidNet', y)
    if tax and pre:
        add('IncomeTaxExpenseBenefit', f"Effective tax rate {tax / pre * 100:.1f}%" + (f"; cash taxes paid {fmt_money(paid)}, {paid / tax * 100:.0f}% of the expense" if paid else '') + '.')
    gw, assets = v('Goodwill', e), v('Assets', e)
    if gw and assets:
        add('Goodwill', f"Goodwill is {gw / assets * 100:.1f}% of total assets" + (f" (a year earlier {v('Goodwill', e0) / v('Assets', e0) * 100:.1f}%)" if v('Goodwill', e0) and v('Assets', e0) else '') + '.')
    debt, ie = v('LongTermDebt', e), v('InterestExpenseNonoperating', y) or v('InterestExpense', y)
    debt0 = v('LongTermDebt', e0)
    if debt and ie and debt0:
        add('LongTermDebt', f"Interest expense is {ie / ((debt + debt0) / 2) * 100:.2f}% of average debt.")
    dr = v('ContractWithCustomerLiability', e)
    if dr and rev:
        add('ContractWithCustomerLiability', f"Deferred revenue equals {dr / rev * 365:.0f} days of revenue.")
    CUST = re.compile(r'(?i)customer(one|two|three|four|five|six|a|b|c|d|e|f|\d+)member$')

    def conc_of(bench):
        return sorted({r[0] for (c, p, dims), r in FL.num.items() if c == 'us-gaap:ConcentrationRiskPercentage1' and p in (y, e)
                       and any(ax.endswith('ConcentrationRiskByBenchmarkAxis') and bench.search(m) for ax, m in dims)
                       and any(ax.endswith('MajorCustomersAxis') and CUST.search(m) for ax, m in dims)
                       and not any(ax.endswith('StatementGeographicalAxis') for ax, m in dims)}, reverse=True)
    cr = conc_of(re.compile(r'(?i)(SalesRevenue|Revenue)'))
    if cr:
        add('Revenues', f"The largest direct customers took {', '.join(f'{x * 100:.0f}%' for x in cr[:3])} of revenue ({sum(cr[:3]) * 100:.0f}% together).")
    ca = conc_of(re.compile(r'(?i)AccountsReceivable'))
    if ca:
        add('AccountsReceivableNetCurrent', f"The largest customers hold {', '.join(f'{x * 100:.0f}%' for x in ca[:3])} of receivables ({sum(ca[:3]) * 100:.0f}% together).")
    return out


# ------------------------------------------------------------------ build
def build(FL, meta):
    statements, notes = classify_reports(FL)
    report_of_role = {r['role']: r['r'] for r in FL.reports}
    rep_by_r = {r['r']: r for r in FL.reports}
    note_of_report = {}
    for i, n in enumerate(notes):
        n['id'] = f"n{i + 1}"
        note_of_report[n['report']['r']] = n['id']
        for r in n['details'] + n['tables'] + n['policies']:
            note_of_report[r['r']] = n['id']
    stmt_of_report = {s['report']['r']: s['kind'] for s in statements}
    periods = [p for p in (FL.dur(0), FL.dur(1), FL.inst(0), FL.inst(1), FL.opening(0), FL.opening(1)) if p]
    # where each concept appears: report ids
    where_of = {}
    for r in FL.reports:
        for n in FL.F['pre'].get(r['role'], []):
            where_of.setdefault(n['c'], set()).add(r['r'])
    K = Checks(FL)
    tie_checks(FL, K, {c: sorted(v) for c, v in where_of.items()})
    rollforward_checks(FL, K, report_of_role, periods)
    calc_checks(FL, K, report_of_role, [p for p in (FL.dur(0), FL.inst(0)) if p])
    member_checks(FL, K, report_of_role, [p for p in (FL.dur(0), FL.inst(0)) if p])
    value_match_checks(FL, K, statements, notes)
    dup_checks(FL, K)
    for ch in K.items:
        cs = {ch['result'][1]} | {p[1] for p in ch['parts']}
        rs = set(ch['where'])
        for c in cs:
            rs |= where_of.get(c, set())
        ch['notes'] = sorted({note_of_report[r] for r in rs if r in note_of_report}, key=lambda x: int(x[1:]))
        ch['statements'] = sorted({stmt_of_report[r] for r in rs if r in stmt_of_report})
        ch['scope'] = ('statement' if not ch['notes'] else 'note' if not ch['statements'] else 'statement-note') if ch['kind'] not in ('cf_bs',) else 'cf-bs'
        if ch['kind'] in ('tie',) and len(ch['notes']) >= 2 and not ch['statements']:
            ch['scope'] = 'note-note'
    # statements: their lines, with the notes that explain each
    concept_notes = {}
    for n in notes:
        for r in n['details']:
            for node in FL.F['pre'].get(r['role'], []):
                concept_notes.setdefault(node['c'], set()).add(n['id'])
            for parent in (FL.F['cal'].get(r['role']) or {}):
                concept_notes.setdefault(parent, set()).add(n['id'])
    st_out = []
    for s in statements:
        T = build_table(FL, s['report']['role'])
        lines = []
        for r in T['rows']:
            ck = [ch for ch in K.items if r['c'] in ({ch['result'][1]} | {p[1] for p in ch['parts']})] if not r['abstract'] else []
            ns = set(concept_notes.get(r['c'], set())) if not r['abstract'] else set()
            for ch in ck:
                if ch['kind'] in ('tie', 'cf_bs', 'rollfwd'):
                    ns |= set(ch['notes'])
            for ch in K.items:
                if ch['kind'] == 'tie' and ch['result'][1] == r['c'] and len(ch['parts']) == 1 and ch['parts'][0][1] != r['c']:
                    ns |= set(ch['notes'])
            ns = sorted(ns, key=lambda x: int(x[1:]))
            ck = [ch['id'] for ch in ck]
            lines.append({'notes': ns, 'checks': ck[:12]})
        st_out.append({'id': s['report']['r'], 'kind': s['kind'], 'title': s['report']['short'], 'table': slim(T, concepts=True), 'lines': lines})
    # notes
    rat = ratios(FL)
    note_out = []
    for n in notes:
        r = n['report']
        title = title_of(FL, r)
        tb = [nd['c'] for nd in FL.F['pre'].get(r['role'], []) if nd['c'].endswith('TextBlock')]
        txt = FL.text(tb[0]) if tb else None
        tables = []
        concepts = set()
        for d in n['details']:
            T = build_table(FL, d['role'], max_cols=14)
            if not any(not row['abstract'] for row in T['rows']) or not T['cols']:
                continue
            chs = charts_for(FL, T, d['role'])
            concepts |= {row['c'] for row in T['rows'] if not row['abstract']}
            sub = re.sub(r'(?i)\s*\((details|narrative)\)\s*$', '', title_of(FL, d))
            sub = sub[len(title):].lstrip(' -–—') if sub.lower().startswith(title.lower()) else sub
            an = []
            for ch in chs:
                for t in analyse_chart(ch, sub):
                    if t not in an:
                        an.append(t)
            tables.append({'id': d['r'], 'title': sub or title, 'charts': chs, 'table': slim(T), 'analysis': an})
        lines_explained = []
        for s in st_out:
            for row, ln in zip(s['table']['rows'], s['lines']):
                if n['id'] in ln['notes'] and [s['id'], row['label'], row['c']] not in lines_explained:
                    lines_explained.append([s['id'], row['label'], row['c']])
        checks = [ch['id'] for ch in K.items if n['id'] in ch['notes']]
        an = [t for c, t in rat if c in concepts]
        for t in tables:
            an += t['analysis'][:2]
        bad = [ch for ch in K.items if n['id'] in ch['notes'] and ch['status'] == 'gap' and ch['kind'] not in ('cf_bs',)]
        if bad:
            an.append(f"{len(bad)} check{'s' if len(bad) > 1 else ''} in this note do{'' if len(bad) > 1 else 'es'} not tie: " + '; '.join(b['title'] for b in bad[:3]) + '.')
        note_out.append({'id': n['id'], 'num': n['num'], 'title': title, 'r': r['r'], 'text': prose(txt), 'text_len': len(plain(txt)) if txt else 0,
                         'policies': [p['short'] for p in n['policies']], 'tables': tables, 'checks': checks, 'lines': lines_explained[:40],
                         'analysis': an[:10]})
    summary = {k: sum(1 for ch in K.items if ch['status'] == k) for k in ('tie', 'round', 'gap', 'info')}
    summary['all'] = len(K.items)
    read = curated_read(meta, note_out)
    # a bank's 10-K can hold a thousand ties: every one that does not tie and every tie across statements and notes is kept,
    # then the company's own sums and splits up to MAX_CHECKS (the counts above are of all of them)
    keep = [ch for ch in K.items if ch['status'] != 'tie' or ch['kind'] in ('tie', 'cf_bs', 'rollfwd')]
    rest = [ch for ch in K.items if ch not in keep]
    keep_ids = {ch['id'] for ch in keep} | {ch['id'] for ch in rest[:max(0, MAX_CHECKS - len(keep))]}
    for s_ in st_out:
        for ln in s_['lines']:
            ln['checks'] = [i for i in ln['checks'] if i in keep_ids]
    for n_ in note_out:
        n_['checks'] = [i for i in n_['checks'] if i in keep_ids]
    doc = {**meta, 'fy': FL.fy_label(0), 'fy_end': FL.fy[1] if FL.fy else None, 'periods': {'cur': FL.dur(0), 'prev': FL.dur(1), 'end': FL.inst(0), 'end_prev': FL.inst(1)},
           'statements': st_out, 'notes': note_out, 'checks': [slim_check(ch, FL) for ch in K.items if ch['id'] in keep_ids], 'summary': summary, 'read': read,
           'built_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    return doc


def _n(v):
    if not fin(v):
        return None
    return int(v) if float(v).is_integer() and abs(v) < 1e15 else round(v, 6)


READS = Path(__file__).resolve().parent / 'notes_reads'
MAX_CHECKS = 450


def curated_read(meta, notes):
    """A written reading of this filing (notes_reads/<TICKER>.json), used only for the filing it was written for."""
    t = meta.get('ticker')
    p = READS / f'{t}.json' if t else None
    if not p or not p.exists():
        return None
    d = json.loads(p.read_text(encoding='utf-8'))
    if d.get('accession') != meta.get('accession'):
        return None
    key = {norm_title(n['title']): n['id'] for n in notes}
    ids = lambda names: [key[norm_title(x)] for x in names if norm_title(x) in key]
    return {'by': d.get('by'), 'summary': d.get('summary') or [], 'threads': [{**th, 'notes': ids(th.get('notes') or [])} for th in d.get('threads') or []],
            'notes': {key[norm_title(k)]: v for k, v in (d.get('notes') or {}).items() if v and norm_title(k) in key}}


def slim(T, concepts=False):
    """A table for the page: labels, depths, units and values (concept names only where the page links lines)."""
    rows = []
    for r in T['rows']:
        o = {'label': r['label'], 'd': r['depth']}
        if concepts:
            o['c'] = r['c']
        if r['abstract']:
            o['abstract'] = 1
        else:
            if r['pref'] in ('total', 'start', 'end', 'negated'):
                o['pref'] = r['pref']
            if r['u'] and r['u'] != 'USD':
                o['u'] = r['u']
        rows.append(o)
    return {'rows': rows, 'cols': [{'e': c['e'], 's': c['s'], 'label': c['label']} if c['label'] else {'e': c['e'], 's': c['s']} for c in T['cols']],
            'cells': [[_n(v) for v in r] for r in T['cells']]}


def slim_check(ch, FL):
    p = ch['period']
    per = (p[1] if p and p[0] == 'i' else f'{p[1]}..{p[2]}') if p else None
    o = {'id': ch['id'], 'kind': ch['kind'], 'scope': ch['scope'], 'title': ch['title'], 'period': per, 'parts': [[l, _n(v), s] for l, c, v, s in ch['parts']],
         'result': [ch['result'][0], _n(ch['result'][2])], 'calc': _n(ch['calc']), 'diff': _n(ch['diff']), 'tol': _n(ch['tol']), 'status': ch['status'],
         'notes': ch['notes'], 'statements': ch['statements'], 'where': ch['where'], 'u': FL.unit(ch['result'][1]) or 'USD'}
    if ch['explain'] and ch['status'] != 'tie':
        o['explain'] = ch['explain']
    return o


# ------------------------------------------------------------------ fetch and run
UA_DEFAULT = 'FilingFlows research (public data reader)'


def http_get(url, ua):
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


ANNUAL = ('10-K', '20-F', '40-F', '10-KT')


def latest_10k(cik, ua, forms=ANNUAL):
    """The latest annual report with XBRL (amendments left out: they rarely carry the full notes)."""
    sub = json.loads(http_get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', ua))
    r = sub['filings']['recent']
    for i, f in enumerate(r['form']):
        if f in forms and (r.get('isXBRL') or [1] * len(r['form']))[i]:
            return {'accession': r['accessionNumber'][i], 'filed': r['filingDate'][i], 'period': r['reportDate'][i], 'form': f,
                    'doc': r['primaryDocument'][i], 'name': sub.get('name'), 'tickers': sub.get('tickers') or []}
    return None


def crdr_of(meta_links_path, xsd_path=None):
    out = {}
    try:
        m = json.loads(Path(meta_links_path).read_text())
        inst = next(iter(m['instance'].values()))
        for k, t in inst.get('tag', {}).items():
            if t.get('crdr'):
                pre, loc = k.split('_', 1)
                out[pre + ':' + loc] = t['crdr']
    except (OSError, ValueError, StopIteration, KeyError):
        pass
    return out


def run_one(cik, folder, ua, ticker=None, sleep=0.12, info=None):
    info = info or latest_10k(cik, ua)
    if not info:
        return None
    folder = Path(folder) / info['accession']
    paths = X.fetch(cik, info['accession'], folder, ua, sleep=sleep)
    ml = folder / 'MetaLinks.json'
    if not ml.exists():
        try:
            ml.write_bytes(http_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{info['accession'].replace('-', '')}/MetaLinks.json", ua))
        except Exception:
            pass
    if 'instance' not in paths or 'summary' not in paths:
        return None
    FL = Filing(X.load(paths), crdr_of(ml))
    meta = {'ticker': ticker or (info['tickers'][0] if info['tickers'] else None), 'cik': int(cik), 'name': info['name'], 'form': info['form'],
            'accession': info['accession'], 'filed': info['filed'], 'period': info['period'],
            'url': f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{info['accession'].replace('-', '')}/{info['doc']}"}
    return build(FL, meta)


VERSION = 2                                            # raise when the checks change: every company is read again, after new ones
INDEX_FIELDS = ['ticker', 'name', 'cik', 'form', 'fy', 'fy_end', 'filed', 'notes', 'tables', 'checks', 'tie', 'round', 'info', 'gap', 'revenue']


def collect(root, site_index, ua, minutes=40.0, recheck_days=7, limit=None, tickers=None):
    """The site's companies, largest first: a company is (re)built when never built, when the site shows a 10-K filed after
    the one on file, or when it was last checked a week ago and has a newer annual report. public/c/<T>.json per company;
    public/index.json the list; state.json what was read when. Raw XBRL files are deleted once read."""
    import shutil
    root = Path(root)
    t0 = time.time()
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    st_p = root / 'state.json'
    state = json.loads(st_p.read_text()) if st_p.exists() else {}
    cos = json.loads(Path(site_index).read_text()).get('companies') or []
    cos = [c for c in cos if c.get('ticker') and c.get('cik')]
    cos.sort(key=lambda c: -(c.get('revenue') or 0))
    if tickers:
        want = [t.strip().upper() for t in tickers.split(',') if t.strip()]
        cos = [c for c in cos if c['ticker'].upper() in want] + [c for c in cos if c['ticker'].upper() not in want]
    now = dt.datetime.now(dt.timezone.utc)

    def due(c):
        s_ = state.get(c['ticker']) or {}
        if s_.get('retry_after') and s_['retry_after'] > now.isoformat():
            return None
        if not s_.get('accession'):
            return 0
        if c.get('form') in ANNUAL and c.get('filed') and c['filed'] > (s_.get('filed') or ''):
            return 1                                       # the site has a newer annual report than the one on file
        if s_.get('v') != VERSION:
            return 0                                       # read with an older version of these checks: again, largest first with the new
        if not s_.get('checked') or (now - dt.datetime.fromisoformat(s_['checked'])).days >= recheck_days:
            return 3
        return None
    order = sorted([(due(c), i, c) for i, c in enumerate(cos) if due(c) is not None], key=lambda x: (x[0], x[1]))
    if tickers:
        order = [(0, i, c) for i, c in enumerate(cos) if c['ticker'].upper() in want] + [x for x in order if x[2]['ticker'].upper() not in want]
    done = errs = same = 0
    cache = root / '_cache'
    for _, _, c in order[:limit] if limit else order:
        if time.time() - t0 > minutes * 60:
            break
        t = c['ticker']
        s_ = state.setdefault(t, {})
        try:
            info = latest_10k(c['cik'], ua)
            time.sleep(0.12)
            if not info:
                s_.update(checked=now.isoformat(timespec='seconds'), error='no annual report with XBRL')
                continue
            if info['accession'] == s_.get('accession') and s_.get('v') == VERSION and (pub / 'c' / f'{t}.json').exists():
                s_['checked'] = now.isoformat(timespec='seconds')
                same += 1
                continue
            doc = run_one(c['cik'], cache, ua, t, info=info)
            if not doc:
                s_.update(checked=now.isoformat(timespec='seconds'), error='no FilingSummary or instance')
                continue
            doc['ticker'] = t
            (pub / 'c' / f'{t}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
            sm = doc['summary']
            s_.clear()
            s_.update(cik=int(c['cik']), accession=doc['accession'], filed=doc['filed'], checked=now.isoformat(timespec='seconds'), v=VERSION,
                      row=[t, doc.get('name'), int(c['cik']), doc.get('form'), doc.get('fy'), doc.get('fy_end'), doc.get('filed'), len(doc['notes']),
                           sum(len(n['tables']) for n in doc['notes']), sm.get('all', len(doc['checks'])), sm.get('tie', 0), sm.get('round', 0), sm.get('info', 0), sm.get('gap', 0),
                           c.get('revenue')])
            done += 1
        except Exception as exc:                          # one company never stops the batch
            errs += 1
            fails = (s_.get('fails') or 0) + 1
            s_.update(error=f'{type(exc).__name__}: {str(exc)[:160]}', fails=fails,
                      retry_after=(now + dt.timedelta(hours=min(168, 12 * 2 ** fails))).isoformat(timespec='seconds'))
        finally:
            shutil.rmtree(cache, ignore_errors=True)
        if (done + errs) % 25 == 0:
            st_p.write_text(json.dumps(state, separators=(',', ':')))
    st_p.write_text(json.dumps(state, separators=(',', ':')))
    rows = [v['row'] for k, v in state.items() if v.get('row') and (pub / 'c' / f'{k}.json').exists()]
    gen = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    (pub / 'index.json').write_text(json.dumps({'generated_at': gen, 'fields': INDEX_FIELDS, 'rows': rows}, separators=(',', ':')), encoding='utf-8')
    status = {'built_at': gen, 'companies': len(rows), 'this_run': done, 'unchanged': same, 'errors': errs, 'due_left': max(0, len(order) - done - same - errs)}
    (pub / 'status.json').write_text(json.dumps(status))
    return status


def main():
    ap = argparse.ArgumentParser(description='Notes of the latest 10-K: tables, charts, ties (app/notes.py)')
    sub = ap.add_subparsers(dest='cmd')
    o = sub.add_parser('one')
    o.add_argument('--cik', required=True)
    o.add_argument('--ticker')
    o.add_argument('--out', required=True)
    o.add_argument('--cache', default=None)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--site-index', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--limit', type=int, default=None)
    c.add_argument('--tickers', default='')
    a = ap.parse_args()
    ua = os.environ.get('SEC_USER_AGENT') or UA_DEFAULT
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, ua, a.minutes, limit=a.limit, tickers=a.tickers)))
        return
    if a.cmd == 'one':
        doc = run_one(a.cik, a.cache or Path(a.out) / '_cache', ua, a.ticker)
        out = Path(a.out) / 'c'
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{doc['ticker']}.json").write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        print(json.dumps({'ticker': doc['ticker'], 'notes': len(doc['notes']), 'checks': len(doc['checks']), **doc['summary']}))


if __name__ == '__main__':
    main()
