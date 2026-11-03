"""Charts drawn into the search pages as inline SVG — no script, so they show for every reader and for search engines
(and work with JavaScript off). Small and plain: a few kilobytes each, colours from the site's charts (grey revenue,
green profit, red loss).

    bars(points, fmt, title)        a series by period, oldest left: [(label, value)], negatives below the line
    hbars(items, fmt, title)        ranked items: [(label, value)] (segments, holders, suppliers)
    diverging(items, fmt, title)    changes, left red / right green: [(label, value)]
    pair(rows, names, title)        two companies side by side, one row per measure: [(measure, a, b, fmt)]
    ranges(rows, fmt, title)        guided low–high ranges with the reported figure: [(label, lo, hi, actual)]
"""
import html

GREY, GREEN, RED, BLUE, INK, MUTED, LINE, ORANGE = '#8a8f98', '#2e8b57', '#c0563d', '#5d7fa3', '#2b2b2b', '#6b6b6b', '#d8d4cc', '#c08a3e'
FONT = "font-family='IBM Plex Sans,system-ui,sans-serif'"


def _e(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def _fig(svg, title, note=None, w=640, h=240):
    cap = f"<figcaption class='muted small'>{_e(note)}</figcaption>" if note else ''
    return (f"<figure class='seo-svg' style='margin:14px 0'><svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='{_e(title)}' "
            f"xmlns='http://www.w3.org/2000/svg' {FONT} style='height:auto'><title>{_e(title)}</title>"
            f"<text x='0' y='16' font-size='14' font-weight='600' fill='{INK}'>{_e(title)}</text>{svg}</svg>{cap}</figure>")


def _clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + '…'


def bars(points, fmt, title, note=None, color=None):
    """[(label, value)] oldest first; a bar per period with its value above (below when negative)."""
    pts = [(l, v) for l, v in points if v is not None]
    if len(pts) < 2:
        return ''
    W, H, top, bot, left = 640, 240, 40, 34, 6
    hi, lo = max(0, max(v for _, v in pts)), min(0, min(v for _, v in pts))
    span = (hi - lo) or 1
    ph = H - top - bot
    y0 = top + ph * hi / span
    step = (W - left) / len(pts)
    bw = min(56, step * 0.62)
    out = [f"<line x1='0' x2='{W}' y1='{y0:.0f}' y2='{y0:.0f}' stroke='{LINE}'/>"]
    for i, (l, v) in enumerate(pts):
        x = left + i * step + (step - bw) / 2
        hgt = abs(v) / span * ph
        y = y0 - hgt if v >= 0 else y0
        c = color or (RED if v < 0 else GREY if i < len(pts) - 1 else BLUE)
        out.append(f"<rect x='{x:.0f}' y='{y:.0f}' width='{bw:.0f}' height='{max(hgt, 1):.0f}' rx='2' fill='{c}'/>")
        ty = y - 5 if v >= 0 else y0 - 5                         # a negative bar's figure above the line, clear of the period labels
        out.append(f"<text x='{x + bw / 2:.0f}' y='{ty:.0f}' font-size='11' text-anchor='middle' fill='{INK}'>{_e(fmt(v))}</text>")
        out.append(f"<text x='{x + bw / 2:.0f}' y='{H - 12}' font-size='11' text-anchor='middle' fill='{MUTED}'>{_e(_clip(l, 12))}</text>")
    return _fig(''.join(out), title, note, W, H)


def hbars(items, fmt, title, note=None, color=BLUE, n=10):
    """[(label, value)] largest first, one row each."""
    its = [(l, v) for l, v in items if v is not None and v > 0][:n]
    if not its:
        return ''
    W, row, top, lab = 640, 24, 30, 230
    H = top + row * len(its) + 8
    mx = max(v for _, v in its)
    out = []
    for i, (l, v) in enumerate(its):
        y = top + i * row
        w = max(2, (W - lab - 90) * v / mx)
        out.append(f"<text x='{lab - 8}' y='{y + 15}' font-size='12' text-anchor='end' fill='{INK}'>{_e(_clip(l, 34))}</text>"
                   f"<rect x='{lab}' y='{y + 4}' width='{w:.0f}' height='15' rx='2' fill='{color}'/>"
                   f"<text x='{lab + w + 6:.0f}' y='{y + 15}' font-size='11' fill='{INK}'>{_e(fmt(v))}</text>")
    return _fig(''.join(out), title, note, W, H)


def diverging(items, fmt, title, note=None, n=10):
    """[(label, change)]: decreases to the left in red, increases to the right in green."""
    its = [(l, v) for l, v in items if v is not None and v != 0][:n]
    if not its:
        return ''
    W, row, top, lab = 640, 24, 30, 210
    H = top + row * len(its) + 8
    mx = max(abs(v) for _, v in its)
    half = (W - lab - 20) / 2
    mid = lab + half
    out = [f"<line x1='{mid:.0f}' x2='{mid:.0f}' y1='{top}' y2='{H - 6}' stroke='{LINE}'/>"]
    for i, (l, v) in enumerate(its):
        y = top + i * row
        w = max(2, (half - 70) * abs(v) / mx)
        x = mid if v > 0 else mid - w
        tx, anc = (mid + w + 5, 'start') if v > 0 else (mid - w - 5, 'end')
        out.append(f"<text x='{lab - 8}' y='{y + 15}' font-size='12' text-anchor='end' fill='{INK}'>{_e(_clip(l, 30))}</text>"
                   f"<rect x='{x:.0f}' y='{y + 4}' width='{w:.0f}' height='15' rx='2' fill='{GREEN if v > 0 else RED}'/>"
                   f"<text x='{tx:.0f}' y='{y + 15}' font-size='11' text-anchor='{anc}' fill='{INK}'>{_e(fmt(v))}</text>")
    return _fig(''.join(out), title, note, W, H)


def pair(rows, names, title, note=None):
    """Two companies, one row per measure: [(measure, a, b, fmt)], bars scaled within each row."""
    rs = [r for r in rows if r[1] is not None and r[2] is not None]
    if not rs:
        return ''
    W, row, top, lab = 640, 44, 44, 170
    H = top + row * len(rs) + 6
    span = W - lab - 110
    out = [f"<rect x='{lab}' y='24' width='10' height='10' fill='{BLUE}'/><text x='{lab + 14}' y='33' font-size='11' fill='{INK}'>{_e(names[0])}</text>"
           f"<rect x='{lab + 200}' y='24' width='10' height='10' fill='{GREY}'/><text x='{lab + 214}' y='33' font-size='11' fill='{INK}'>{_e(names[1])}</text>"]
    for i, (m, a, b, fmt) in enumerate(rs):
        y = top + i * row
        mx = max(abs(a), abs(b)) or 1
        out.append(f"<text x='{lab - 8}' y='{y + 20}' font-size='12' text-anchor='end' fill='{INK}'>{_e(m)}</text>")
        for j, (v, c) in enumerate(((a, BLUE), (b, GREY))):
            w = max(2, span * abs(v) / mx)
            yy = y + 4 + j * 17
            out.append(f"<rect x='{lab}' y='{yy}' width='{w:.0f}' height='14' rx='2' fill='{RED if v < 0 else c}'/>"
                       f"<text x='{lab + w + 6:.0f}' y='{yy + 11}' font-size='11' fill='{INK}'>{_e(fmt(v))}</text>")
    return _fig(''.join(out), title, note, W, H)


def ranges(rows, fmt, title, note=None, legend=('guided range', 'reported (above / within / below)')):
    """Ranges with a point against each: [(label, lo, hi, point)] (guided low–high against what was reported; a valuation
    method's low–high against its point estimate). One row per item, the range a horizontal bar, the point a dot with
    its figure: labels are read in full and never cross each other."""
    rs = [r for r in rows if r[1] is not None]
    if not rs or not any(r[3] is not None for r in rs):  # nothing reported to hold the ranges to: the table says it
        return ''
    rh, top, bot, W = 26, 44, 10, 640
    H = top + rh * len(rs) + bot
    left = 236                                              # the labels' column
    vals = [v for r in rs for v in (r[1], r[2], r[3]) if v is not None]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda v: left + (W - left - 70) * (v - lo) / (hi - lo)
    out = []
    for i, (l, a, b, act) in enumerate(rs):
        cy = top + i * rh + rh / 2
        b = a if b is None else b
        out.append(f"<text x='{left - 10}' y='{cy + 4:.0f}' font-size='11' text-anchor='end' fill='{INK}'>{_e(_clip(l, 36))}</text>")
        out.append(f"<rect x='{X(a):.0f}' y='{cy - 6:.0f}' width='{max(4, X(b) - X(a)):.0f}' height='12' rx='3' fill='{GREY}' opacity='.45'/>")
        if act is not None:
            c = GREEN if act >= b else RED if act < a else BLUE
            out.append(f"<circle cx='{X(act):.0f}' cy='{cy:.0f}' r='5' fill='{c}'/>"
                       f"<text x='{max(X(act), X(b)) + 9:.0f}' y='{cy + 4:.0f}' font-size='11' fill='{INK}'>{_e(fmt(act))}</text>")
    legend = (f"<rect x='0' y='26' width='14' height='10' fill='{GREY}' opacity='.45'/><text x='18' y='35' font-size='11' fill='{MUTED}'>{_e(legend[0])}</text>"
              f"<circle cx='160' cy='31' r='5' fill='{BLUE}'/><text x='169' y='35' font-size='11' fill='{MUTED}'>{_e(legend[1])}</text>")
    return _fig(legend + ''.join(out), title, note, W, H)


def duo(points, names, fmt, title, note=None):
    """Two series side by side per period: [(label, a, b)] oldest first (net income against operating cash flow)."""
    pts = [p for p in points if p[1] is not None or p[2] is not None]
    if len(pts) < 2:
        return ''
    W, H, top, bot = 640, 250, 46, 34
    vals = [v for p in pts for v in p[1:] if v is not None]
    hi, lo = max(0, max(vals)), min(0, min(vals))
    span = (hi - lo) or 1
    ph = H - top - bot
    y0 = top + ph * hi / span
    step = W / len(pts)
    bw = min(24, step * 0.34)
    out = [f"<line x1='0' x2='{W}' y1='{y0:.0f}' y2='{y0:.0f}' stroke='{LINE}'/>",
           f"<rect x='0' y='24' width='10' height='10' fill='{GREY}'/><text x='14' y='33' font-size='11' fill='{INK}'>{_e(names[0])}</text>"
           f"<rect x='170' y='24' width='10' height='10' fill='{GREEN}'/><text x='184' y='33' font-size='11' fill='{INK}'>{_e(names[1])}</text>"]
    for i, (l, a, b) in enumerate(pts):
        cx = i * step + step / 2
        for j, (v, c) in enumerate(((a, GREY), (b, GREEN))):
            if v is None:
                continue
            hgt = abs(v) / span * ph
            x = cx - bw - 1 if j == 0 else cx + 1
            y = y0 - hgt if v >= 0 else y0
            # the series' colour whatever the sign (a loss is below the line already; red on both would hide which is which)
            out.append(f"<rect x='{x:.0f}' y='{y:.0f}' width='{bw:.0f}' height='{max(hgt, 1):.0f}' rx='2' fill='{c}'{' opacity=\'.6\'' if v < 0 else ''}/>")
            if len(pts) <= 8:
                ty = y - 4 if v >= 0 else y + hgt + 11
                # the figure sits outside the pair (left series to the left, right series to the right) so it never crosses the
                # neighbour's taller bar, and the two figures never overlap
                anchor, tx = ("end", x + bw) if j == 0 else ("start", x)
                out.append(f"<text x='{tx:.0f}' y='{ty:.0f}' font-size='10' text-anchor='{anchor}' fill='{INK}'>{_e(fmt(v))}</text>")
        out.append(f"<text x='{cx:.0f}' y='{H - 12}' font-size='11' text-anchor='middle' fill='{MUTED}'>{_e(_clip(l, 12))}</text>")
    last = pts[-1]
    note = note or f"Latest ({last[0]}): {names[0]} {fmt(last[1])}, {names[1]} {fmt(last[2])}."
    return _fig(''.join(out), title, note, W, H)


def scatter(points, xlab, ylab, title, me=None, note=None, xfmt=lambda v: f'{v:+.0f}%', yfmt=lambda v: f'{v:.0f}%'):
    """[(label, x, y, size)] — peers as dots, `me` (a label) highlighted and named; the axes cross at the peers' medians."""
    pts = [p for p in points if p[1] is not None and p[2] is not None]
    if len(pts) < 3:
        return ''
    W, H, L, R, T, B = 640, 300, 46, 16, 34, 36
    xs, ys = sorted(p[1] for p in pts), sorted(p[2] for p in pts)
    q = lambda v, f: v[min(len(v) - 1, max(0, int(f * (len(v) - 1))))]
    x0, x1, y0, y1 = q(xs, .05), q(xs, .95), q(ys, .05), q(ys, .95)
    mine = next((p for p in pts if p[0] == me), None)
    if mine:
        x0, x1, y0, y1 = min(x0, mine[1]), max(x1, mine[1]), min(y0, mine[2]), max(y1, mine[2])
    px, py = (x1 - x0) * .08 or 1, (y1 - y0) * .08 or 1
    x0, x1, y0, y1 = x0 - px, x1 + px, y0 - py, y1 + py
    X = lambda v: L + (W - L - R) * (min(max(v, x0), x1) - x0) / (x1 - x0)
    Y = lambda v: T + (H - T - B) * (y1 - min(max(v, y0), y1)) / (y1 - y0)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    smax = max((p[3] or 0) for p in pts) or 1
    out = [f"<line x1='{X(mx):.0f}' x2='{X(mx):.0f}' y1='{T}' y2='{H - B}' stroke='{LINE}' stroke-dasharray='3 3'/>",
           f"<line x1='{L}' x2='{W - R}' y1='{Y(my):.0f}' y2='{Y(my):.0f}' stroke='{LINE}' stroke-dasharray='3 3'/>",
           f"<text x='{W - R}' y='{H - 8}' font-size='11' text-anchor='end' fill='{MUTED}'>{_e(xlab)} →</text>",
           f"<text x='4' y='{T - 6}' font-size='11' fill='{MUTED}'>↑ {_e(ylab)}</text>",
           f"<text x='{X(mx) + 4:.0f}' y='{H - B - 4}' font-size='10' fill='{MUTED}'>median {_e(xfmt(mx))}</text>",
           f"<text x='{L + 2}' y='{Y(my) - 4:.0f}' font-size='10' fill='{MUTED}'>median {_e(yfmt(my))}</text>"]
    for p in sorted(pts, key=lambda p: -(p[3] or 0)):
        if p is mine:
            continue
        r = 3 + 9 * ((p[3] or 0) / smax) ** .5
        out.append(f"<circle cx='{X(p[1]):.0f}' cy='{Y(p[2]):.0f}' r='{r:.1f}' fill='{GREY}' opacity='.45'><title>{_e(p[0])}</title></circle>")
    if mine:
        r = 3 + 9 * ((mine[3] or 0) / smax) ** .5
        right = X(mine[1]) > W - 190                      # near the right edge: the name goes to its left
        tx = X(mine[1]) - max(r, 6) - 4 if right else X(mine[1]) + max(r, 6) + 4
        out.append(f"<circle cx='{X(mine[1]):.0f}' cy='{Y(mine[2]):.0f}' r='{max(r, 6):.1f}' fill='{BLUE}' stroke='#fff' stroke-width='2'/>"
                   f"<text x='{tx:.0f}' y='{Y(mine[2]) + 4:.0f}' font-size='12' font-weight='600' fill='{INK}' text-anchor='{'end' if right else 'start'}'>{_e(me)} ({_e(xfmt(mine[1]))}, {_e(yfmt(mine[2]))})</text>")
    return _fig(''.join(out), title, note, W, H)


PALETTE = ('#5d7fa3', '#2e8b57', '#c0563d', '#8a8f98', '#7b6aa8', '#c08a3e', '#6fae8a', '#b0a68f', '#a05a8c', '#4f9fb8')


def stacked(periods, series, fmt, title, note=None, colors=None, legend=True):
    """Stacked bars, one per period: periods [label …] oldest first; series [(name, [v per period])]. Positive values
    stack up from the baseline, negative down (a cash-flow statement: sources above, uses below)."""
    series = [(n, v) for n, v in series if any(x for x in v if x)]
    if len(periods) < 2 or not series:
        return ''
    W, H, top, bot, left = 640, 260, 46, 34, 6
    up = [sum(max(0, (v[i] or 0)) for _, v in series) for i in range(len(periods))]
    dn = [sum(min(0, (v[i] or 0)) for _, v in series) for i in range(len(periods))]
    hi, lo = max(up + [0]), min(dn + [0])
    span = (hi - lo) or 1
    ph = H - top - bot
    y0 = top + ph * hi / span
    step = (W - left) / len(periods)
    bw = min(48, step * 0.66)
    cols = colors or PALETTE
    out = [f"<line x1='0' x2='{W}' y1='{y0:.0f}' y2='{y0:.0f}' stroke='{LINE}'/>"]
    if legend:
        x = 0
        for k, (n, _) in enumerate(series[:8]):
            out.append(f"<rect x='{x}' y='24' width='10' height='10' fill='{cols[k % len(cols)]}'/><text x='{x + 13}' y='33' font-size='10.5' fill='{INK}'>{_e(_clip(n, 22))}</text>")
            x += 20 + 6.2 * min(len(n), 22)
    for i, lab in enumerate(periods):
        x = left + i * step + (step - bw) / 2
        yu, yd = y0, y0
        for k, (n, v) in enumerate(series):
            val = v[i] or 0
            if not val:
                continue
            hgt = abs(val) / span * ph
            if val > 0:
                yu -= hgt
                y = yu
            else:
                y = yd
                yd += hgt
            out.append(f"<rect x='{x:.0f}' y='{y:.0f}' width='{bw:.0f}' height='{max(hgt, 0.5):.1f}' fill='{cols[k % len(cols)]}'><title>{_e(lab)}: {_e(n)} {_e(fmt(val))}</title></rect>")
        if len(periods) <= 10 and up[i]:
            out.append(f"<text x='{x + bw / 2:.0f}' y='{yu - 4:.0f}' font-size='10' text-anchor='middle' fill='{INK}'>{_e(fmt(up[i]))}</text>")
        out.append(f"<text x='{x + bw / 2:.0f}' y='{H - 12}' font-size='11' text-anchor='middle' fill='{MUTED}'>{_e(_clip(lab, 10))}</text>")
    return _fig(''.join(out), title, note, W, H)


def river(periods, series, fmt, title, note=None, colors=None):
    """A stacked area ("river"): periods oldest first; series [(name, [v per period])] — a company's revenue lines
    over time, each band's share visible at every period."""
    series = [(n, [max(0, x or 0) for x in v]) for n, v in series if any(x for x in v if x)]
    if len(periods) < 3 or not series:
        return ''
    W, H, top, bot, left, right = 640, 260, 46, 30, 6, 6
    tot = [sum(v[i] for _, v in series) for i in range(len(periods))]
    mx = max(tot) or 1
    ph = H - top - bot
    X = lambda i: left + (W - left - right) * i / (len(periods) - 1)
    Y = lambda v: top + ph * (1 - v / mx)
    cols = colors or PALETTE
    base = [0.0] * len(periods)
    out, x = [], 0
    for k, (n, v) in enumerate(series[:9]):
        out.append(f"<rect x='{x}' y='24' width='10' height='10' fill='{cols[k % len(cols)]}'/><text x='{x + 13}' y='33' font-size='10.5' fill='{INK}'>{_e(_clip(n, 22))}</text>")
        x += 20 + 6.2 * min(len(n), 22)
    for k, (n, v) in enumerate(series):
        topl = [base[i] + v[i] for i in range(len(periods))]
        path = 'M' + ' L'.join(f"{X(i):.1f},{Y(topl[i]):.1f}" for i in range(len(periods))) + ' L' + ' L'.join(f"{X(i):.1f},{Y(base[i]):.1f}" for i in reversed(range(len(periods)))) + ' Z'
        out.append(f"<path d='{path}' fill='{cols[k % len(cols)]}' opacity='.85'><title>{_e(n)}: {_e(fmt(v[-1]))} latest</title></path>")
        last = len(periods) - 1
        if v[last] / mx > 0.07:
            out.append(f"<text x='{X(last) - 4:.0f}' y='{(Y(topl[last]) + Y(base[last])) / 2 + 4:.0f}' font-size='10' text-anchor='end' fill='#fff' font-weight='600'>{_e(fmt(v[last]))}</text>")
        base = topl
    for i, lab in enumerate(periods):
        if len(periods) <= 10 or i % max(1, len(periods) // 8) == 0 or i == len(periods) - 1:
            out.append(f"<text x='{X(i):.0f}' y='{H - 10}' font-size='10.5' text-anchor='{'start' if i == 0 else 'end' if i == len(periods) - 1 else 'middle'}' fill='{MUTED}'>{_e(_clip(lab, 10))}</text>")
    return _fig(''.join(out), title, note, W, H)


def line_marks(days, values, marks, fmt, title, note=None, color=INK):
    """A line over time with marks on it: days [ISO …], values [v …] (the price), marks [(day, kind, label)] with kind
    one of buy, sell, earnings, event. The legend names the kinds present."""
    pts = [(d, v) for d, v in zip(days, values) if v is not None]
    if len(pts) < 10:
        return ''
    W, H, top, bot, left, right = 640, 280, 46, 30, 44, 10
    t0, t1 = pts[0][0], pts[-1][0]
    import datetime as _dt
    ord_ = lambda d: _dt.date.fromisoformat(d[:10]).toordinal()
    o0, o1 = ord_(t0), ord_(t1)
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda d: left + (W - left - right) * (ord_(d) - o0) / ((o1 - o0) or 1)
    Y = lambda v: top + (H - top - bot) * (hi - v) / (hi - lo)
    out = []
    for k in range(4):
        v = lo + (hi - lo) * (k + 1) / 4
        out.append(f"<line x1='{left}' x2='{W - right}' y1='{Y(v):.0f}' y2='{Y(v):.0f}' stroke='{LINE}'/><text x='{left - 4}' y='{Y(v) + 4:.0f}' font-size='10' text-anchor='end' fill='{MUTED}'>{_e(fmt(v))}</text>")
    step = max(1, len(pts) // 300)
    path = 'M' + ' L'.join(f"{X(d):.1f},{Y(v):.1f}" for d, v in pts[::step])
    out.append(f"<path d='{path}' fill='none' stroke='{color}' stroke-width='1.6'/>")
    KIND = {'buy': (GREEN, 'Insider buy', '▲'), 'sell': (RED, 'Insider sale', '▼'), 'earnings': (BLUE, 'Earnings report', '●'), 'event': (ORANGE, '8-K event', '◆'), 'plan': (GREY, 'Planned sale (Form 144)', '▽')}
    by = dict(zip(days, values))
    seen = []
    for d, kind, lab in marks:
        if kind not in KIND or d < t0 or d > t1:
            continue
        v = by.get(d) or next((vv for dd, vv in pts if dd >= d), None)
        if v is None:
            continue
        c, _, g = KIND[kind]
        yoff = -12 if kind in ('buy', 'earnings') else 14
        out.append(f"<text x='{X(d):.1f}' y='{Y(v) + yoff + (4 if yoff > 0 else 0):.1f}' font-size='11' text-anchor='middle' fill='{c}'>{g}<title>{_e(d)} · {_e(lab)}</title></text>")
        if kind not in seen:
            seen.append(kind)
    x = 0
    for kind in seen:
        c, name, g = KIND[kind]
        out.append(f"<text x='{x}' y='33' font-size='11' fill='{c}'>{g}</text><text x='{x + 13}' y='33' font-size='10.5' fill='{INK}'>{_e(name)}</text>")
        x += 24 + 6.2 * len(name)
    for d in (t0, t1):
        out.append(f"<text x='{X(d):.0f}' y='{H - 10}' font-size='10.5' text-anchor='{'start' if d == t0 else 'end'}' fill='{MUTED}'>{_e(d[:10])}</text>")
    return _fig(''.join(out), title, note, W, H)


def calendar(start, days, title, note=None, fmt=None, label='companies'):
    """A month-style grid from `start` (ISO, a Monday) over the weeks covering `days` {ISO: (count, weight)}: each
    weekday cell shaded by its weight (the market value or count reporting), with the count printed."""
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start)
    d0 -= _dt.timedelta(days=d0.weekday())
    last = max((_dt.date.fromisoformat(d) for d in days), default=d0)
    weeks = max(1, (last - d0).days // 7 + 1)
    W, top, cell, gap = 640, 40, 58, 6
    cw = (W - 6 * gap) / 5
    H = top + weeks * (cell + gap) + 6
    mx = max((w for _, w in days.values()), default=1) or 1
    out = [f"<text x='{gap + i * (cw + gap) + cw / 2:.0f}' y='34' font-size='11' text-anchor='middle' fill='{MUTED}'>{n}</text>" for i, n in enumerate(('Mon', 'Tue', 'Wed', 'Thu', 'Fri'))]
    for w in range(weeks):
        for i in range(5):
            d = d0 + _dt.timedelta(days=7 * w + i)
            k = d.isoformat()
            x, y = gap + i * (cw + gap), top + w * (cell + gap)
            n, wt = days.get(k, (0, 0))
            a = 0.08 + 0.85 * ((wt / mx) ** 0.5 if wt else 0)
            out.append(f"<rect x='{x:.0f}' y='{y}' width='{cw:.0f}' height='{cell}' rx='6' fill='{BLUE}' opacity='{a:.2f}'/>"
                       f"<text x='{x + 7:.0f}' y='{y + 15}' font-size='10.5' fill='{INK if a < 0.5 else '#fff'}'>{d.day}{' ' + d.strftime('%b') if d.day <= 7 or (w == 0 and i == 0) else ''}</text>"
                       + (f"<text x='{x + cw - 7:.0f}' y='{y + cell - 9}' font-size='15' font-weight='600' text-anchor='end' fill='{INK if a < 0.5 else '#fff'}'>{n}</text>"
                          + (f"<text x='{x + 7:.0f}' y='{y + cell - 9}' font-size='9.5' fill='{INK if a < 0.5 else '#fff'}'>{_e(fmt(wt))}</text>" if fmt and wt else '') if n else ''))
    return _fig(''.join(out), title, note, W, int(H))
