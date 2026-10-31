"""The charts on a company's search page (c/<slug>/), beside the Sankey:

  drawn into the page (inline SVG, readable without script and by search engines) from the company's own data:
    capital allocation    where the cash came from and where it went (cash-flow statement, latest four quarters / year)
    profit and cash       net income against operating cash flow, quarter by quarter
    shares                diluted shares by fiscal year (buybacks and dilution)
    debt maturities       long-term debt falling due by year
    place in its industry revenue growth against operating margin, every company of its SIC industry
  interactive, loaded when scrolled to (web/seo-embed.js), the same views as the app:
    where each $1 goes (the detailed Sankey, money flow lab), rotation (RRG), quality, fair value, outlook,
    Asian customers & suppliers, the industry's money flow (input-output), and the supply chains and themes it is in
    (their pictures, pipeline/ogimg.py)
"""
import html
import seo_svg as SV

CASH = {'ocf': 'Operating cash flow', 'capex': 'Capital spending', 'acq': 'Acquisitions', 'realestate': 'Real estate bought',
        'sales': 'Asset & business sales', 'buyback': 'Buybacks', 'div': 'Dividends', 'withhold': 'Taxes on employees’ shares',
        'stock': 'Shares issued', 'borrow': 'Net borrowing (+) / repaid (−)', 'nci': 'Partners', 'inv_other': 'Other investing',
        'fin_other': 'Other financing', 'cash': 'Cash drawn (+) / kept (−)', 'fx': 'Exchange rates', 'unrec': 'Not reconciled'}


def _e(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def static(c, r, peers_all, money):
    """The drawn charts, as one HTML string ('' when there is nothing to draw)."""
    p = c.get('profile') or {}
    name = p.get('name') or r.get('name') or ''
    out = []
    qs8 = [x for x in (c.get('quarters') or [])[:9] if (x.get('headline') or {}).get('revenue')]
    gr = []
    for i, x in enumerate(qs8[:8]):
        hh, prev = x['headline'], (qs8[i + 1]['headline'] if i + 1 < len(qs8) else {})
        qoq = (hh['revenue'] / prev['revenue'] - 1) * 100 if prev.get('revenue') and prev['revenue'] > 0 else None
        gr.append((x.get('label'), hh.get('yoy'), qoq))
    if sum(1 for g in gr if g[1] is not None or g[2] is not None) >= 3:
        cap_ = lambda v: None if v is None else max(-150.0, min(400.0, v))
        out.append(SV.duo([(l, cap_(y), cap_(q)) for l, y, q in reversed(gr)], ('Y/Y', 'Q/Q'), lambda v: '—' if v is None else f"{v:+.0f}%",
                          f"{name}: revenue growth, year over year and quarter over quarter"))
    Q = c.get('quality') or {}
    cap = Q.get('cap') or {}
    per = cap.get('ttm') or ((cap.get('fy') or [None])[-1])
    if per and per.get('items'):
        items = sorted(((CASH.get(k, k), v) for k, v in per['items'].items() if k in CASH and v), key=lambda kv: -abs(kv[1]))
        out.append(SV.diverging(items, money, f"{name}: where the cash came from (+) and went (−), {per.get('label')}", n=12,
                                note='From the cash-flow statement as filed (SEC XBRL). Cash is fungible: the bars do not say which dollar paid for what.'))
    qs = [x for x in (Q.get('q') or []) if x.get('label')][-8:]
    if len(qs) >= 3:
        out.append(SV.duo([(x['label'], x.get('ni'), x.get('ocf')) for x in qs], ('Net income', 'Operating cash flow'), money,
                          f"{name}: profit against cash, quarter by quarter"))
    sh = [x for x in (cap.get('shares') or []) if x.get('diluted')][-8:]
    if len(sh) >= 3:
        vals, splits = [x['diluted'] for x in sh], []
        for i in range(len(vals) - 1, 0, -1):                 # a stock split: an earlier count scaled by a near-whole ratio
            k = vals[i] / vals[i - 1]
            for s in (2, 3, 4, 5, 10, 20):
                if abs(k / s - 1) < 0.12 or (s >= 4 and abs(k / s - 1) < 0.2):
                    vals[:i] = [v * s for v in vals[:i]]
                    splits.append(f"{s}-for-1 split before {sh[i].get('label')}")
                    break
        first, last = vals[0], vals[-1]
        out.append(SV.bars([(x.get('label'), v) for x, v in zip(sh, vals)], lambda v: f"{v / 1e9:.2f}B" if v >= 1e9 else f"{v / 1e6:.0f}M",
                           f"{name}: diluted shares by fiscal year" + (' (split-adjusted)' if splits else ''), color=SV.GREY,
                           note=f"{(last / first - 1) * 100:+.1f}% since {sh[0].get('label')}: " + ('buybacks shrank the count' if last < first else 'more shares outstanding (issuance, stock pay)')
                           + (f"; earlier years scaled for the {', '.join(splits)}." if splits else '.')))
    mat = cap.get('maturities') or {}
    if mat.get('buckets'):
        fy = mat.get('fy') or 0
        lab = lambda k: f"{fy + k}" if k < 6 else 'Later'
        out.append(SV.bars([(lab(b[0]), b[1]) for b in mat['buckets'] if b[1]], money, f"{name}: long-term debt falling due ({mat.get('label')})",
                           color=SV.RED, note=f"Cash {money(mat.get('cash'))}, short-term investments {money(mat.get('sti'))}, long-term debt {money(mat.get('ltd'))} at {mat.get('at')}."))
    sic = r.get('sic')
    peers = [x for x in peers_all if x.get('sic') == sic and x.get('om') is not None and x.get('yoy') is not None and (x.get('revenue') or 0) > 0]
    me = r.get('ticker') or name
    pts = [((x.get('ticker') or x.get('name')) if x['cik'] != r['cik'] else me, max(-100, min(300, x['yoy'])), max(-100, min(100, x['om'])), x.get('revenue'))
           for x in peers]
    if len(pts) >= 4 and any(x['cik'] == r['cik'] for x in peers):
        out.append(SV.scatter(pts, 'revenue growth, year over year', 'operating margin', f"{name} in its industry: growth against margin ({len(pts)} companies, SIC {sic})",
                              me=me, note=f"{r.get('industry') or 'Same SIC industry'}; dot size is quarterly revenue; dashed lines are the industry's medians."))
    body = ''.join(x for x in out if x)
    return f"<h2>Charts</h2>{body}" if body else ''


def live(cik, ticker, sic, sector, chains, images, depth=2):
    """Slots for the interactive views (web/seo-embed.js fills them when scrolled to), and the themes' pictures."""
    up = '../' * depth
    slots = [('flowlab', 'Where each $1 goes', ''), ('asia', 'Named in Asian annual reports', '')]
    if ticker:
        slots += [('hub:rotation', 'Rotation against the market and its industry (RRG)', ''), ('hub:quality', 'Earnings quality', ''),
                  ('hub:fairvalue', 'Fair value by method', ''), ('hub:outlook', 'Outlook & guidance', '')]
    if sic:
        slots.append(('industry', 'Its industry’s money flow (input-output)', ''))
    s = ''.join(f"<section class='seo-live' data-kind='{_e(k)}' data-cik='{_e(cik)}' data-ticker='{_e(ticker)}' data-sic='{_e(sic)}' data-sector='{_e(sector)}'>"
                f"<h2>{_e(t)}</h2><p class='muted'>Loading the interactive chart…</p></section>" for k, t, _ in slots)
    th = ''
    for ch in chains[:6]:
        img = images.get(f"chain-{ch['id']}")
        th += (f"<a class='seo-theme' href='{up}chains/{_e(ch['id'])}/'>" + (f"<img loading='lazy' src='{_e(img)}' alt='{_e(ch['name'])} money flow' width='600' height='315'>" if img else '')
               + f"<span>{_e(ch['name'])} · {_e(ch['role'])}</span></a>")
    if th:
        th = f"<h2>In supply chains and themes</h2><div class='seo-themes'>{th}</div>"
    return (th + s + f"<script>window.FF_BASE='{up}';</script><script src='{up}chains.js' defer></script><script src='{up}flowlab.js' defer></script>"
            f"<script src='{up}asia-links.js' defer></script><script src='{up}seo-embed.js' defer></script>")


def _ufmt(unit):
    return (lambda v: f"${v:.2f}") if unit == 'ps' else (lambda v: f"{v:.1f}%") if unit == 'pct' else None


def guidance_outlook(name, rec, ol, money):
    """Guided ranges against what was reported (data/guidance-record/<cik>.json) and the latest forward-looking
    statements (data/outlook/<cik>.json): topics, and what is new, updated or dropped since the filing before."""
    out = []
    for m in [m for m in (rec or {}).get('metrics') or [] if sum(1 for x in m.get('rows') or [] if (x.get('guides') or []))][:2]:
        f = _ufmt(m.get('unit')) or money
        rows = [(x.get('label'), (x.get('guides') or [{}])[-1].get('lo'), (x.get('guides') or [{}])[-1].get('hi'), x.get('actual'))
                for x in reversed((m.get('rows') or [])[:8]) if (x.get('guides') or [{}])[-1].get('lo') is not None]
        h = m.get('hits') or {}
        out.append(SV.ranges(rows, f, f"{name} {m.get('name')}: guidance against what was reported",
                             note=(f"Met or beat {h['hitOrBeat']} of {h['n']} guided periods." if h.get('n') else 'No guided period reported yet.')
                             + ' Grey: the last range guided before the figures came out; dot: the reported figure.'))
    doc = next((d for d in (ol or {}).get('docs') or [] if d.get('kind') == 'mdna' and d.get('counts')), None)
    if doc:
        c = doc['counts']
        out.append(SV.hbars([(k.replace('_', ' ').capitalize(), v) for k, v in c.get('topics') or []], str,
                             f"{name}: what its forward-looking statements are about ({doc.get('form')} filed {doc.get('filed')})",
                             note=f"{c.get('n', 0)} statements; tone {c.get('tone', 0):+.2f} (−1 all cautious, +1 all confident); {c.get('hedged', 0)} hedged."))
        out.append(SV.hbars([('New', c.get('new')), ('Updated', c.get('updated')), ('Dropped', c.get('dropped')),
                             ('Confident', c.get('positive')), ('Cautious', c.get('negative'))], str,
                            f"{name}: outlook statements against the filing before", color=SV.GREY))
    body = ''.join(x for x in out if x)
    return f"<h2>Guidance and outlook</h2>{body}" if body else ''
