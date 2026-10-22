"""Estimated industry money flows from BEA input-output tables: every SIC industry, SIC major group and sector.

Writes gamma/io/<key>.json (key: a 4-digit SIC, "sic2-<2 digits>" or "sector-<id>") for the Industries (SIC) page's
"Estimated flow (BEA input-output)" view — four columns, every number an estimate at industry-average precision:

  1. where the money comes from    each member company's revenue over the last four quarters, plus borrowing or cash
                                   reserves where a company spent more than it took in
  2. what the industry spends it on cash operating costs (revenue − operating income − D&A) split as BEA's Use table
                                   splits the company's industry's spending: purchased inputs, employees, taxes on
                                   production; capital spending; and the operating cash left over
  3. supplying industries          purchased inputs by the industry's own input mix (BEA Use table), capital spending by
                                   its own asset mix (BEA fixed assets: investment by industry and asset type) —
                                   pipeline/data/bea_io.json, scripts/bea_io.py; the imported share of each commodity
                                   goes to "Imports"
  4. listed suppliers              within a supplying industry, the listed companies mapped to it, each by its revenue
                                   over the industry's gross output (all listed when their revenue is larger: much of it
                                   is sold abroad); the rest "Unlisted & private"

A company's SIC code says which BEA industries it is in (scripts/bea_io.py: 1987 SIC → … → 2017 NAICS → BEA detail).
"""
import datetime as dt
import json
import os
import re
from collections import defaultdict

from . import chains, sectors

DATA = os.path.join(os.path.dirname(__file__), 'data', 'bea_io.json')
TOP_COMPANIES = 12            # column 1: the largest members by revenue, the rest together
TOP_INDUSTRIES = 18           # column 3
TOP_SUPPLIERS = 16            # column 4
CATS = [('purchases', 'Purchased inputs'), ('capex', 'Capital spending'), ('employees', 'Employees (pay & benefits)'),
        ('taxes', 'Taxes on production'), ('left', 'Operating cash left over'),
        ('finleft', 'Interest, claims & profit (banks, insurers)')]
MAJOR = {'01': 'Agricultural production — crops', '02': 'Agricultural production — livestock', '07': 'Agricultural services',
         '08': 'Forestry', '09': 'Fishing, hunting and trapping', '10': 'Metal mining', '12': 'Coal mining',
         '13': 'Oil and gas extraction', '14': 'Nonmetallic minerals mining', '15': 'Building construction',
         '16': 'Heavy construction', '17': 'Construction special trades', '20': 'Food and kindred products',
         '21': 'Tobacco products', '22': 'Textile mill products', '23': 'Apparel', '24': 'Lumber and wood products',
         '25': 'Furniture and fixtures', '26': 'Paper and allied products', '27': 'Printing and publishing',
         '28': 'Chemicals and allied products', '29': 'Petroleum refining', '30': 'Rubber and plastics',
         '31': 'Leather products', '32': 'Stone, clay, glass and concrete', '33': 'Primary metal industries',
         '34': 'Fabricated metal products', '35': 'Industrial machinery and computer equipment',
         '36': 'Electronic and other electrical equipment', '37': 'Transportation equipment',
         '38': 'Instruments and related products', '39': 'Miscellaneous manufacturing', '40': 'Railroad transportation',
         '41': 'Local and interurban passenger transit', '42': 'Trucking and warehousing', '44': 'Water transportation',
         '45': 'Air transportation', '46': 'Pipelines', '47': 'Transportation services', '48': 'Communications',
         '49': 'Electric, gas and sanitary services', '50': 'Wholesale trade — durable goods',
         '51': 'Wholesale trade — nondurable goods', '52': 'Building materials and garden supplies',
         '53': 'General merchandise stores', '54': 'Food stores', '55': 'Auto dealers and gas stations',
         '56': 'Apparel and accessory stores', '57': 'Furniture and home furnishings stores', '58': 'Eating and drinking places',
         '59': 'Miscellaneous retail', '60': 'Depository institutions', '61': 'Nondepository credit institutions',
         '62': 'Security and commodity brokers', '63': 'Insurance carriers', '64': 'Insurance agents and brokers',
         '65': 'Real estate', '67': 'Holding and other investment offices', '70': 'Hotels and lodging',
         '72': 'Personal services', '73': 'Business services', '75': 'Auto repair and services', '78': 'Motion pictures',
         '79': 'Amusement and recreation services', '80': 'Health services', '81': 'Legal services',
         '82': 'Educational services', '83': 'Social services', '87': 'Engineering, accounting, research and management',
         '99': 'Nonclassifiable establishments'}


# operating spending (staff, premises, technology, services) as a share of revenue for lenders and insurers, whose
# revenue less income is mostly interest or claims paid: US banks' non-interest expense against gross revenue (interest
# income + fees), insurers' expense ratios (health: the rest of an ~85% medical-loss ratio)
FIN_SPEND = [((6000, 6199), .40, 'banks and lenders: non-interest expense ≈ 40% of gross revenue'),
             ((6311, 6311), .18, 'life insurers: expenses ≈ 18% of revenue'),
             ((6324, 6324), .15, 'health insurers: expenses ≈ 15% of premiums (medical-loss ratio ≈ 85%)'),
             ((6300, 6399), .28, 'property & casualty and other insurers: expense ratio ≈ 28%')]


def fin_ratio(sic):
    s = int(sic)
    for (lo, hi), r, _ in FIN_SPEND:
        if lo <= s <= hi:
            return r
    return None


def fin_notes(sics):
    seen = []
    for s in sics:
        for (lo, hi), _, note in FIN_SPEND:
            if lo <= int(s) <= hi and note not in seen:
                seen.append(note)
                break
    return seen


def load(path=DATA):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def bea_mix(io, sic):
    """{BEA detail industry: weight} for an SEC SIC code. SEC uses some codes the 1987 list does not (7370, 2080,
    6770 …): a code ending in 0 takes every listed code of its three-digit group, one ending in 00 its two-digit group,
    the industries weighted by output."""
    sic = str(sic or '').zfill(4)
    m = io['sic'].get(sic)
    if m:
        return {b: w for b, w in m}
    for n in ((3, 2) if sic.endswith('00') else (3,) if sic.endswith('0') else ()):
        acc = {}
        for code, pairs in io['sic'].items():
            if code.startswith(sic[:n]):
                for b, _ in pairs:
                    acc[b] = io['industries'][b]['output']
        if acc:
            tot = sum(acc.values())
            return {b: v / tot for b, v in acc.items() if v / tot >= 0.01}
    return {}


def ttm(co, key, latest=None):
    """The sum of the last four quarters (consecutive: the first ends at most ~10 months before the last), or None."""
    h = co.history(key)
    ends = sorted(e for e, v in h.items() if v is not None)
    if len(ends) < 4:
        return None, None
    last4 = ends[-4:]
    span = (dt.date.fromisoformat(last4[-1]) - dt.date.fromisoformat(last4[0])).days
    if not 240 <= span <= 300:
        return None, None
    if latest and (dt.date.fromisoformat(latest) - dt.date.fromisoformat(last4[-1])).days > 400:
        return None, None
    return sum(h[e] for e in last4), last4[-1]


def company_figures(co, latest):
    """TTM revenue, operating income (pretax when none), D&A and capex in dollars; None when revenue or income is
    missing."""
    rev, end = ttm(co, 'revenue', latest)
    if not rev or rev <= 0:
        return None
    oi, _ = ttm(co, 'oi', latest)
    how = []
    if oi is None:
        oi, _ = ttm(co, 'pretax', latest)
        how.append('pretax income for operating income')
    if oi is None:
        return None
    da, _ = ttm(co, 'da', latest)
    if da is None:
        da = 0.0
        how.append('no D&A')
    capex, _ = ttm(co, 'capex', latest)
    if capex is None:
        capex = 0.0
        how.append('no capex')
    return {'revenue': rev, 'oi': oi, 'da': abs(da), 'capex': abs(capex), 'end': end, 'how': how}


class Flows:
    """One company's estimated spending, by category and supplying industry, kept so any grouping can add them up."""

    def __init__(self, io):
        self.io = io
        inv = io['invest']
        self.inv = (inv['suppliers'], inv['imports'])

    def company(self, f, mix):
        I = self.io['industries']
        w = {b: x for b, x in mix.items() if b in I}
        tot = sum(w.values())
        if not tot:
            return None
        w = {b: x / tot for b, x in w.items()}
        inter = sum(x * I[b]['inter'] for b, x in w.items())
        comp = sum(x * I[b]['comp'] for b, x in w.items())
        tax = sum(x * I[b]['tax'] for b, x in w.items())
        if f.get('financial'):
            # banks and insurers: what revenue less income leaves is mostly interest and claims paid, which are not
            # purchases (and the filings' figures here do not separate them): operating spending is a typical expense
            # ratio of revenue instead (FIN_SPEND)
            cost = f['revenue'] * f['financial']
        else:
            cost = max(0.0, f['revenue'] - f['oi'] - f['da'])
        spend = {'purchases': cost * inter, 'employees': cost * comp, 'taxes': cost * tax, 'capex': f['capex']}
        sup = defaultdict(float)
        imports = 0.0
        if inter > 0:
            for b, x in w.items():
                share = x * I[b]['inter'] / inter
                for i, s in I[b]['suppliers'].items():
                    sup[('purchases', i)] += spend['purchases'] * share * s
                imports += spend['purchases'] * share * I[b]['imports']
        imp_p = imports
        # capital spending: each of the company's BEA industries buys its own asset mix (fixed assets by industry), the
        # economy's investment mix for one without
        imp_c = 0.0
        caps = self.io.get('capex') or {}
        for b, x in w.items():
            cm = caps.get(I[b].get('fa') or '')
            sups, imp = (cm['suppliers'], cm['imports']) if cm else self.inv
            for i, s in sups.items():
                sup[('capex', i)] += f['capex'] * x * s
            imp_c += f['capex'] * x * imp
        total = sum(spend.values())
        left = f['revenue'] - total
        return {'revenue': f['revenue'], 'spend': spend, 'left': max(0.0, left), 'gap': max(0.0, -left),
                'left_key': 'finleft' if f.get('financial') else 'left',
                'sup': dict(sup), 'imports': {'purchases': imp_p, 'capex': imp_c}}


def doc_for(key, title, members, listed, io, meta):
    """The four-column view for a set of member companies. members: [(company record, flows)]; listed: {BEA industry:
    [(cik, ticker, name, revenue × weight)]} for column 4."""
    I = io['industries']
    members = sorted(members, key=lambda m: -m[1]['revenue'])
    nodes, links = [], []
    seen = set()

    def node(id_, col, label, color, **kw):
        if id_ not in seen:
            seen.add(id_)
            nodes.append({'id': id_, 'col': col, 'label': label, 'color': color, **kw})

    def link(s, t, v):
        if v > 0:
            links.append([s, t, round(v)])
    # columns 1 → 2
    top = members[:TOP_COMPANIES]
    rest = members[TOP_COMPANIES:]
    for c, _ in CATS:
        node('k:' + c, 1, dict(CATS)[c], {'purchases': '#5d7fa3', 'capex': '#7b6aa8', 'employees': '#9a8f7a',
                                         'taxes': '#a08a5a', 'left': '#5e9a78', 'finleft': '#6f9a8a'}[c])
    groups = [(m['ticker'] or m['name'], m['cik'], [fl]) for m, fl in top]
    if rest:
        groups.append((f'Other {len(rest)} companies', None, [fl for _, fl in rest]))
    gap_to = defaultdict(float)
    for label, cik, fls in groups:
        sid = 'm:' + (str(cik) if cik else 'other')
        node(sid, 0, label, '#8fa9c4', cik=cik)
        for fl in fls:
            spend = sum(fl['spend'].values())
            cover = min(1.0, fl['revenue'] / spend) if spend else 1.0
            for c, v in fl['spend'].items():
                link(sid, 'k:' + c, v * cover)
                gap_to[c] += v * (1 - cover)
            link(sid, 'k:' + fl['left_key'], fl['left'])
    if sum(gap_to.values()) > 0:
        node('m:gap', 0, 'Borrowing & cash reserves', '#b9b2a3')
        for c, v in gap_to.items():
            link('m:gap', 'k:' + c, v)
    # columns 2 → 3
    by_ind = defaultdict(float)
    by_cat_ind = defaultdict(float)
    imports = defaultdict(float)
    for _, fl in members:
        for (c, i), v in fl['sup'].items():
            by_ind[i] += v
            by_cat_ind[(c, i)] += v
        for c, v in fl['imports'].items():
            imports[c] += v
    ranked = [i for i, _ in sorted(by_ind.items(), key=lambda kv: -kv[1]) if i != '_OTHER'][:TOP_INDUSTRIES]
    for i in ranked:
        node('i:' + i, 2, I[i]['name'], '#88a3c0', bea=i)
    node('i:other', 2, 'Other industries', '#b7c3cf')
    node('i:imports', 2, 'Imports', '#c9a77a')
    for (c, i), v in by_cat_ind.items():
        link('k:' + c, 'i:' + i if i in ranked else 'i:other', v)
    for c, v in imports.items():
        link('k:' + c, 'i:imports', v)
    # columns 3 → 4: listed suppliers by revenue over the industry's gross output
    sup_flow = defaultdict(float)                 # (industry node, supplier key) → $
    for i, v in by_ind.items():
        if i == '_OTHER' or i not in I:
            continue
        cands = listed.get(i) or []
        out = I[i]['output'] or 1
        tot = sum(r for *_, r in cands)
        scale = 1.0 / tot if tot > out else 1.0 / out
        src = 'i:' + i if i in ranked else 'i:other'
        for cik, tk, nm, r in cands:
            sup_flow[(src, (cik, tk, nm))] += v * r * scale
        if tot < out:
            sup_flow[(src, 'unlisted')] += v * (1 - tot / out)
    if by_ind.get('_OTHER'):
        sup_flow[('i:other', 'unlisted')] += by_ind['_OTHER']
    totals = defaultdict(float)
    for (_, s), v in sup_flow.items():
        if s != 'unlisted':
            totals[s] += v
    best = {s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:TOP_SUPPLIERS]}
    for s in best:
        node('s:' + str(s[0]), 3, s[1] or s[2], '#6f8fb3', cik=s[0], name=s[2])
    node('s:other', 3, 'Other listed companies', '#a9b8c8')
    node('s:unlisted', 3, 'Unlisted & private', '#c3c8cd')
    agg = defaultdict(float)
    for (src, s), v in sup_flow.items():
        tgt = 's:unlisted' if s == 'unlisted' else ('s:' + str(s[0]) if s in best else 's:other')
        agg[(src, tgt)] += v
    for (src, tgt), v in agg.items():
        link(src, tgt, v)
    revenue = sum(fl['revenue'] for _, fl in members)
    total = {c: sum(fl['spend'][c] for _, fl in members) for c in ('purchases', 'capex', 'employees', 'taxes')}
    total['left'] = sum(fl['left'] for _, fl in members if fl['left_key'] == 'left')
    total['finleft'] = sum(fl['left'] for _, fl in members if fl['left_key'] == 'finleft')
    total['gap'] = sum(fl['gap'] for _, fl in members)
    total['imports'] = sum(imports.values())
    used = [n for n in nodes if any(l[0] == n['id'] or l[1] == n['id'] for l in links)]
    return {'key': key, 'title': title, 'generated': dt.datetime.now(dt.timezone.utc).isoformat(), 'estimate': True,
            'companies': len(members), 'revenue': round(revenue), 'totals': {k: round(v) for k, v in total.items()},
            'cols': ['Where the money comes from', 'What the industry spends it on', 'Supplying industries', 'Listed suppliers'],
            'nodes': used, 'links': [l for l in links if l[2] >= max(1.0, 1e-4 * revenue)], **meta,
            'source': {'io_year': io['year'], 'scale_year': io['scale_year'], 'capex': io.get('capex_note'), **io['source']}}


def build(store, out, index, usd_recs=None, path=DATA):
    if not os.path.exists(path):
        print('::warning::BEA input-output data missing (pipeline/data/bea_io.json); run scripts/bea_io.py')
        return None
    io = load(path)
    F = Flows(io)
    latest = max((p.get('end') or p.get('filed') or '' for p in index), default=None) or None
    latest = latest[:10] if latest else None
    rec = []
    skipped = defaultdict(int)
    for p in index:
        sic = str(p.get('sic') or '').strip().zfill(4)
        if not re.fullmatch(r'\d{4}', sic) or sic == '0000':
            continue
        mix = bea_mix(io, sic)
        if not mix:
            skipped['no BEA industry for the SIC code'] += 1
            continue
        usd = (usd_recs or {}).get(p['cik'])
        if (p.get('currency') or 'USD') != 'USD' and not usd:
            skipped['foreign filer without dollar figures'] += 1     # its own currency would be added to dollars
            continue
        co = chains.Co(p['cik'], store.company(p['cik']), usd, ticker=p.get('ticker'))
        try:
            f = company_figures(co, latest)
        except Exception:
            f = None
        if not f:
            skipped['no four quarters of revenue and income'] += 1
            continue
        f['financial'] = fin_ratio(sic)
        fl = F.company(f, mix)
        if not fl:
            continue
        m = {'cik': int(p['cik']), 'ticker': p.get('ticker') or '', 'name': p.get('name') or '', 'sic': sic,
             'sector': p.get('sector') or sectors.sector_of(sic), 'industry': p.get('industry') or '', 'how': f['how']}
        rec.append((m, fl, mix))
    # column 4's candidates: every company with revenue, by the BEA industries its SIC code is in
    listed = defaultdict(list)
    for m, fl, mix in rec:
        for b, w in mix.items():
            listed[b].append((m['cik'], m['ticker'], m['name'], fl['revenue'] * w))
    os.makedirs(os.path.join(out, 'gamma', 'io'), exist_ok=True)
    groups = defaultdict(list)
    names = {}
    for m, fl, mix in rec:
        groups[m['sic']].append((m, fl))
        names.setdefault(m['sic'], m['industry'] or 'SIC ' + m['sic'])
        groups['sic2-' + m['sic'][:2]].append((m, fl))
        groups['sector-' + m['sector']].append((m, fl))
    written = 0
    for key, members in groups.items():
        if key.startswith('sic2-'):
            d2 = key[5:]
            title, level = f'SIC {d2} · {MAJOR.get(d2, "Major group " + d2)}', 'major group'
        elif key.startswith('sector-'):
            title, level = sectors.SECTORS.get(key[7:], key[7:]), 'sector'
        else:
            title, level = f'SIC {key} · {names[key]}', 'industry'
        mixes = defaultdict(float)
        for m, fl in members:
            for b, w in bea_mix(io, m['sic']).items():
                mixes[b] += fl['revenue'] * w
        tot = sum(mixes.values()) or 1
        meta = {'level': level, 'bea': [[b, io['industries'][b]['name'], round(v / tot, 3)] for b, v in
                                        sorted(mixes.items(), key=lambda kv: -kv[1])[:6]],
                'financial': fin_notes({m['sic'] for m, _ in members}),
                'partial': sorted({h for m, _ in members for h in m['how']}),
                'partial_n': sum(1 for m, _ in members if m['how'])}
        doc = doc_for(key, title, members, listed, io, meta)
        with open(os.path.join(out, 'gamma', 'io', key + '.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, separators=(',', ':'))
        written += 1
    print(f'ioflow: {written} industry money flows (BEA {io["year"]} input-output) from {len(rec)} companies; '
          f'skipped {dict(skipped)}')
    return written
