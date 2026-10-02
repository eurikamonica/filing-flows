/* Earnings Sankey: layout + rendering in the earnings-sankey standard format.
 *
 * layout(spec, {compare}) turns the pipeline's JSON (nodes with column, colour role, label lines and a
 * preferred label side; links with current and previous-quarter values) into a scene: a flat display
 * list of bands, bars and text. The same scene is drawn as interactive SVG on screen and onto a canvas
 * for PNG/JPG/PDF export. Shapes flagged `ui` (note markers, hit areas) exist only on screen.
 */
(function (global) {
  'use strict';

  const PALETTE = {
    rev: { node: '#7a7974', flow: '#d9d8d3' },
    profit: { node: '#17734a', flow: '#a8d1b9' },
    cost: { node: '#ea6a52', flow: '#f6c3b8' },
    noncash: { node: '#5b7fa6', flow: '#cdd8e6' },
  };
  const LEGEND = [['rev', 'Revenue'], ['profit', 'Profit & gains'], ['cost', 'Costs'], ['noncash', 'Non-cash items']];
  const BG = '#fcfcfb';
  const INK = '#1d1d1b', INK2 = '#3d3c39', INK3 = '#6b6a66', SUBINK = '#5c5b57', MARK = '#17734a';
  const FONT = "'IBM Plex Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif";
  // style: [font size, weight, line height, colour]
  const STY = {
    name: [18, 600, 22, INK], big: [26, 600, 30, INK], ocf: [22, 600, 26, INK],
    val: [15, 400, 20, INK2], mut: [14, 400, 19, INK3], cmp: [14, 500, 19, INK2],
  };
  const NW = 14;          // node bar width
  const LGAP = 8;         // label distance from a bar (left/right)
  const VGAP = 6;         // label distance from a bar (above/below)
  const PAD = 12;         // minimum free space between neighbours in a column
  const SPREAD = 28;      // vertical gap between siblings that split from / merge into one node
  const REV_PX = 430;     // the largest node is drawn about this tall
  const MARGIN = 60;
  const HEAD = 168;       // content starts below title + subtitle
  const NOTE_PAD = 16;    // room after a name for the note marker

  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let mctx = null;
  function measure(text, size, weight) {
    if (!mctx) mctx = document.createElement('canvas').getContext('2d');
    mctx.font = `${weight} ${size}px ${FONT}`;
    return mctx.measureText(text).width;
  }

  function wrap(text, size, weight, maxW) {
    const words = text.split(/\s+/);
    const out = [];
    let cur = '';
    for (const w of words) {
      const t = cur ? cur + ' ' + w : w;
      if (cur && measure(t, size, weight) > maxW) { out.push(cur); cur = w; } else cur = t;
    }
    if (cur) out.push(cur);
    return out;
  }

  function labelBlock(n, compare) {
    const lines = (n.lines || [['name', n.name]]).map(([st, t]) => ({ st: STY[st] ? st : 'mut', t: dec(t) }));
    if (compare && n.cmp) lines.push({ st: 'cmp', t: dec(n.cmp) });
    let w = 0, h = 0;
    lines.forEach((l, i) => {
      const [size, weight, lh] = STY[l.st];
      l.w = measure(l.t, size, weight) + (i === 0 && n.notes ? NOTE_PAD : 0);
      w = Math.max(w, l.w);
      h += lh;
    });
    return { lines, w: Math.ceil(w), h };
  }

  // ---------- geometry helpers ----------
  function overlap(a, b, m) {
    const ox = Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]) + m;
    const oy = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]) + m;
    return ox > 0 && oy > 0 ? ox * oy : 0;
  }
  const ease = (t) => 3 * t * t - 2 * t * t * t;   // y-progress of the band curve (control points at mid-x)
  function bezX(x0, x1, t) {
    const xm = (x0 + x1) / 2, u = 1 - t;
    return u * u * u * x0 + 3 * u * u * t * xm + 3 * u * t * t * xm + t * t * t * x1;
  }
  function bandPath(x0, a0, x1, a1, th) {
    const xm = (x0 + x1) / 2, f = (v) => v.toFixed(2);
    return `M${f(x0)} ${f(a0)} C${f(xm)} ${f(a0)} ${f(xm)} ${f(a1)} ${f(x1)} ${f(a1)} ` +
      `L${f(x1)} ${f(a1 + th)} C${f(xm)} ${f(a1 + th)} ${f(xm)} ${f(a0 + th)} ${f(x0)} ${f(a0 + th)} Z`;
  }

  // ---------- layout ----------
  function layout(spec, opts) {
    opts = opts || {};
    const compare = !!opts.compare && !!spec.compare;
    const nodes = spec.nodes.map((n, i) => Object.assign({}, n, { idx: i, ins: [], outs: [] }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = spec.links
      .filter((l) => byId.has(l.s) && byId.has(l.t) && l.v > 0)
      .map((l, i) => Object.assign({}, l, { idx: i, S: byId.get(l.s), T: byId.get(l.t) }));
    links.forEach((l) => { l.S.outs.push(l); l.T.ins.push(l); });
    // stack flows in the order the nodes are listed (the pipeline lists nodes top to bottom)
    nodes.forEach((n) => {
      n.outs.sort((a, b) => a.T.idx - b.T.idx);
      n.ins.sort((a, b) => a.S.idx - b.S.idx);
    });
    const maxV = Math.max(...nodes.map((n) => Math.abs(n.v || 0)));
    const K = REV_PX / maxV;
    nodes.forEach((n) => {
      n.h = Math.max(Math.abs(n.v || 0) * K, 2);
      n.lab = labelBlock(n, compare);
      n.light = !n.ins.length || !n.outs.length;
    });
    links.forEach((l) => { l.th = l.v * K; });
    nodes.forEach((n) => {
      let o = 0;
      n.outs.forEach((l) => { l.so = o; o += l.th; });
      o = 0;
      n.ins.forEach((l) => { l.to = o; o += l.th; });
    });

    // 1. tree placement: profit stays level, siblings peel downward
    const placed = new Set();
    function put(n, top, from, dir) { n.top = top; n.from = from; n.dir = dir; placed.add(n); }
    function bfs(start, top) {
      put(start, top, null, 0);
      const q = [start];
      while (q.length) {
        const p = q.shift();
        p.outs.forEach((l, i) => {
          if (placed.has(l.T)) return;
          put(l.T, p.top + l.so - l.to + i * SPREAD, p, 1);
          q.push(l.T);
        });
        const a = p.ins.findIndex((l) => placed.has(l.S));
        p.ins.forEach((l, i) => {
          if (placed.has(l.S)) return;
          put(l.S, p.top + l.to - l.so + (a < 0 ? i : i - a) * SPREAD, p, -1);
          q.push(l.S);
        });
      }
    }
    const biggest = (arr) => arr.reduce((a, b) => (Math.abs(b.v) > Math.abs(a.v) ? b : a));
    const root = biggest(nodes);
    bfs(root, 0);
    for (;;) {
      const rest = nodes.filter((n) => !placed.has(n));
      if (!rest.length) break;
      bfs(biggest(rest), root.top);
    }

    // 2. columns; gaps are sized from the label sides actually chosen (recomputed until stable)
    const ncol = Math.max(...nodes.map((n) => n.col)) + 1;
    const cols = Array.from({ length: ncol }, () => []);
    nodes.forEach((n) => cols[n.col].push(n));
    const rootCol = root.col;
    const colOrder = [];
    for (let c = rootCol; c < ncol; c++) colOrder.push(c);
    for (let c = rootCol - 1; c >= 0; c--) colOrder.push(c);

    function labelRect(n, pos) {
      const { w, h } = n.lab, x = n.x, t = n.top, b = n.top + n.h, c = t + n.h / 2, cx = x + NW / 2;
      switch (pos) {
        case 'left': return [x - LGAP - w, c - h / 2, w, h, 'end'];
        case 'right': return [x + NW + LGAP, c - h / 2, w, h, 'start'];
        case 'above': return [cx - w / 2, t - VGAP - h, w, h, 'middle'];
        case 'below': return [cx - w / 2, b + VGAP, w, h, 'middle'];
        case 'above_left': return [x + NW - w, t - VGAP - h, w, h, 'end'];
        case 'above_right': return [x, t - VGAP - h, w, h, 'start'];
        case 'below_left': return [x + NW - w, b + VGAP, w, h, 'end'];
        case 'below_right': return [x, b + VGAP, w, h, 'start'];
        default: return [x + NW + LGAP, c - h / 2, w, h, 'start'];
      }
    }
    const posOf = (n) => n.at || n.pos;
    function extRight(n) {
      const p = posOf(n), w = n.lab.w;
      return p === 'right' ? LGAP + w : /_right$/.test(p) ? w - NW : /^(above|below)$/.test(p) ? (w - NW) / 2 : 0;
    }
    function extLeft(n) {
      const p = posOf(n), w = n.lab.w;
      return p === 'left' ? LGAP + w : /_left$/.test(p) ? w - NW : /^(above|below)$/.test(p) ? (w - NW) / 2 : 0;
    }
    const vr = (r) => [r[1], r[1] + r[3]];
    const vov = (a, b, m) => a[0] < b[1] + m && b[0] < a[1] + m;
    function computeXs() {
      const gaps = [];
      for (let c = 0; c < ncol - 1; c++) {
        const A = cols[c], B = cols[c + 1];
        let g = A.length && B.length ? 200 : 110;
        A.forEach((a) => {
          const ra = vr(labelRect(a, posOf(a))), ea = extRight(a);
          g = Math.max(g, ea + 24);
          B.forEach((b) => {
            const rb = vr(labelRect(b, posOf(b))), eb = extLeft(b);
            if (vov(ra, rb, 8)) g = Math.max(g, ea + eb + 28);
            if (vov(ra, [b.top, b.top + b.h], 6)) g = Math.max(g, ea + 18);
            if (vov(rb, [a.top, a.top + a.h], 6)) g = Math.max(g, eb + 18);
          });
        });
        B.forEach((b) => { g = Math.max(g, extLeft(b) + 24); });
        gaps.push(Math.ceil(g));
      }
      const leftNeed = Math.max(0, ...cols[0].map(extLeft));
      const xs = [MARGIN + leftNeed + 4];
      gaps.forEach((g, c) => xs.push(xs[c] + NW + g));
      return xs;
    }

    function descendants(n) {
      const out = [], st = [n];
      while (st.length) {
        const p = st.pop();
        nodes.forEach((m) => { if (m.from === p) { out.push(m); st.push(m); } });
      }
      return out.filter((m) => (n.dir >= 0 ? m.col > n.col : m.col < n.col) || (n.dir === 0 && m.col !== n.col));
    }
    function shift(n, d) {
      n.top += d;
      descendants(n).forEach((m) => { m.top += d; });
    }
    function footprint(n) {
      const r = labelRect(n, posOf(n));
      return [Math.min(n.top, r[1]), Math.max(n.top + n.h, r[1] + r[3])];
    }

    // 3. resolve vertical collisions inside each column (light nodes move out of the way first)
    function resolveColumns() {
      for (let iter = 0; iter < 40; iter++) {
        let moved = false;
        for (const c of colOrder) {
          const list = cols[c].slice().sort((a, b) => a.top + a.h / 2 - (b.top + b.h / 2));
          for (let i = 1; i < list.length; i++) {
            const A = list[i - 1], B = list[i];
            const fa = footprint(A), fb = footprint(B);
            const d = fa[1] + PAD - fb[0];
            if (d <= 0.5) continue;
            const above = i >= 2 ? footprint(list[i - 2])[1] + PAD : -Infinity;
            if (A.light && !B.light && fa[0] - d >= above) shift(A, -d);
            else shift(B, d);
            moved = true;
          }
        }
        if (!moved) break;
      }
    }

    function bandGeom(l) {
      return { x0: l.S.x + NW, x1: l.T.x, a0: l.S.top + l.so, a1: l.T.top + l.to };
    }
    function bandBoxes() {
      const boxes = [];
      links.forEach((l) => {
        const g = bandGeom(l), N = 20;
        let px = g.x0, py = g.a0;
        for (let i = 1; i <= N; i++) {
          const t = i / N, x = bezX(g.x0, g.x1, t), y = g.a0 + (g.a1 - g.a0) * ease(t);
          boxes.push({ r: [px, Math.min(py, y), x - px, Math.abs(y - py) + Math.max(l.th, 0.8)], l });
          px = x; py = y;
        }
      });
      return boxes;
    }
    function candidates(n) {
      let c;
      if (!n.ins.length && !n.outs.length) c = ['left', 'right', 'above', 'below'];
      else if (!n.ins.length) c = ['left', 'above_left', 'below_left', 'above', 'below'];
      else if (!n.outs.length) c = ['right', 'below_right', 'above_right', 'below', 'above'];
      else c = ['above', 'below_left', 'above_right', 'above_left', 'below', 'below_right'];
      return [n.pos].concat(c.filter((p) => p !== n.pos));
    }

    // 4. label placement: preferred side unless it would sit on a band, a bar or another label
    function placeLabels() {
      const boxes = bandBoxes();
      const done = [];
      const order = nodes.slice().sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
      const issues = [];
      order.forEach((n) => {
        let best = null;
        candidates(n).forEach((pos, rank) => {
          const r = labelRect(n, pos);
          let hard = 0, soft = 0, bandArea = 0, band = null, withLabel = null, withBar = null;
          done.forEach((o) => {
            const v = overlap(r, o.r, 6);
            if (!v) return;
            if (o.n.light && !n.light) soft += v; else hard += v;   // a small neighbour can move out of the way
            withLabel = withLabel || o.n;
          });
          nodes.forEach((m) => {
            if (m === n) return;
            const v = overlap(r, [m.x, m.top, NW, m.h], 4);
            if (v) { hard += v; withBar = withBar || m; }
          });
          boxes.forEach((b) => {
            const v = overlap(r, b.r, 4);
            if (v) { bandArea += v; if (!band || v > band.v) band = { v, b }; }
          });
          const s = rank * 100 + (bandArea ? 3000 + bandArea * 2 : 0) + (soft ? 1500 + soft * 0.5 : 0) + (hard ? 20000 + hard * 4 : 0);
          hard += soft;
          if (!best || s < best.s) best = { s, pos, r, hard, band, withLabel, withBar };
        });
        n.at = best.pos;
        n.lr = best.r;
        done.push({ r: best.r, n });
        if (best.hard > 0 || best.band) issues.push({ n, best, boxes });
      });
      return issues;
    }

    // move a light node vertically away from whatever its label (or band) collides with
    function nudge(issues) {
      let moved = false;
      const away = (target, mine, theirs) => {
        const dir = mine[1] + mine[3] / 2 >= theirs[1] + theirs[3] / 2 ? 1 : -1;
        const amt = dir > 0 ? theirs[1] + theirs[3] + 8 - mine[1] : mine[1] + mine[3] + 8 - theirs[1];
        shift(target, dir * Math.min(Math.max(amt, 6), 240));
        moved = true;
      };
      issues.forEach(({ n, best, boxes }) => {
        const r = best.r;
        const other = best.withLabel || best.withBar;
        if (other) {
          const oRect = best.withLabel ? other.lr : [other.x, other.top, NW, other.h];
          if (n.light && (!other.light || Math.abs(n.v) <= Math.abs(other.v))) away(n, r, oRect);
          else if (other.light) away(other, oRect, r);
          return;
        }
        if (best.band) {
          const l = best.band.b.l, br = best.band.b.r;
          if (n.light) {
            // smallest vertical shift that clears every band (down first; up only while the column order holds)
            const others = boxes.filter((b) => b.l.S !== n && b.l.T !== n);
            const clear = (dy) => !others.some((b) => overlap([r[0], r[1] + dy, r[2], r[3]], b.r, 4));
            const list = cols[n.col].slice().sort((a, b) => a.top + a.h / 2 - (b.top + b.h / 2));
            const i = list.indexOf(n);
            const floor = i > 0 ? footprint(list[i - 1])[1] + PAD : -Infinity;
            let dy = null;
            for (let k = 1; k <= 60 && dy === null; k++) {
              if (clear(k * 6)) dy = k * 6;
              else if (footprint(n)[0] - k * 6 >= floor && clear(-k * 6)) dy = -k * 6;
            }
            if (dy !== null) { shift(n, dy); moved = true; } else away(n, r, br);
          } else {
            const src = l.S !== n && l.S.light && !l.S.ins.length ? l.S : l.T !== n && l.T.light && !l.T.outs.length ? l.T : null;
            if (src) {
              // pull the far end of the band towards the label's level so the band clears it
              const dir = br[1] + br[3] / 2 < r[1] + r[3] / 2 ? -1 : 1;
              shift(src, dir * Math.min(r[3] + 12, 120));
              moved = true;
            }
          }
        }
      });
      return moved;
    }

    let issues = [];
    let xs = computeXs();
    for (let outer = 0; outer < 4; outer++) {
      nodes.forEach((n) => { n.x = xs[n.col]; });
      for (let round = 0; round < 10; round++) {
        resolveColumns();
        issues = placeLabels();
        if (!issues.length || !nudge(issues)) break;
      }
      resolveColumns();
      issues = placeLabels();
      const nx = computeXs();
      if (nx.every((v, i) => Math.abs(v - xs[i]) < 1)) break;
      xs = nx;
    }
    nodes.forEach((n) => { n.x = xs[n.col]; n.lr = labelRect(n, n.at); });

    // 5. normalise into the page
    let minY = Infinity, maxY = -Infinity, maxX = 0;
    nodes.forEach((n) => {
      minY = Math.min(minY, n.top, n.lr[1]);
      maxY = Math.max(maxY, n.top + n.h, n.lr[1] + n.lr[3]);
      maxX = Math.max(maxX, n.x + NW, n.lr[0] + n.lr[2]);
    });
    links.forEach((l) => {
      const g = bandGeom(l);
      minY = Math.min(minY, g.a0, g.a1);
      maxY = Math.max(maxY, g.a0 + l.th, g.a1 + l.th);
    });
    const dy = HEAD - minY;
    nodes.forEach((n) => { n.top += dy; n.lr = labelRect(n, n.at); });
    let bottom = maxY + dy;

    const title = dec(compare ? spec.compare.title : spec.title);
    const subtitle = dec(spec.subtitle || '');
    let W = Math.max(maxX + MARGIN, 1500, measure(title, 40, 600) + 2 * MARGIN, measure(subtitle, 18, 400) + 2 * MARGIN);
    W = Math.ceil(W);

    const shapes = [];
    // bands
    links.forEach((l) => {
      const g = bandGeom(l), pal = PALETTE[l.color] || PALETTE.rev;
      const cls = { ls: l.s, lt: l.t };            // link ends (not `s`/`t`: `t` is the shape type)
      if (compare && l.q != null) {
        if (l.q <= 0) {
          shapes.push(Object.assign({ t: 'path', d: bandPath(g.x0, g.a0, g.x1, g.a1, l.th), fill: pal.node, band: true }, cls));
        } else {
          const base = Math.min(l.q, l.v) * K, strip = l.th - base;
          shapes.push(Object.assign({ t: 'path', d: bandPath(g.x0, g.a0, g.x1, g.a1, base), fill: pal.flow, band: true }, cls));
          if (strip > 0.05) {
            shapes.push(Object.assign({ t: 'path', d: bandPath(g.x0, g.a0 + base, g.x1, g.a1 + base, Math.max(strip, 0.6)),
              fill: pal.node, band: true }, cls));
          }
        }
      } else {
        shapes.push(Object.assign({ t: 'path', d: bandPath(g.x0, g.a0, g.x1, g.a1, Math.max(l.th, 0.8)), fill: pal.flow, band: true }, cls));
      }
    });
    // bars + labels
    const hit = [];
    nodes.forEach((n) => {
      const pal = PALETTE[n.color] || PALETTE.rev;
      shapes.push({ t: 'rect', x: n.x, y: n.top, w: NW, h: n.h, fill: pal.node, group: n.id });
      const [lx, ly, lw, lh, anchor] = n.lr;
      let y = ly;
      n.lab.lines.forEach((ln, i) => {
        const [size, weight, lineH, color] = STY[ln.st];
        const tx = anchor === 'end' ? lx + lw : anchor === 'middle' ? lx + lw / 2 : lx;
        const textW = ln.w - (i === 0 && n.notes ? NOTE_PAD : 0);
        let x = tx;
        if (i === 0 && n.notes) {
          // keep the name aligned with the other lines; the marker sits after the name
          if (anchor === 'end') x = tx - NOTE_PAD;
          else if (anchor === 'middle') x = tx - NOTE_PAD / 2;
          const right = anchor === 'end' ? x : anchor === 'middle' ? x + textW / 2 : x + textW;
          shapes.push({ t: 'circle', cx: right + 9, cy: y + lineH / 2 + 0.5, r: 4.5, fill: MARK, ui: true, group: n.id, marker: true });
        }
        shapes.push({ t: 'text', x, y: y + lineH / 2 + size * 0.35, text: ln.t, size, weight, fill: color, anchor, group: n.id });
        y += lineH;
      });
      const hx = Math.min(n.x, lx) - 4, hy = Math.min(n.top, ly) - 4;
      const hr = [hx, hy, Math.max(n.x + NW, lx + lw) + 4 - hx, Math.max(n.top + n.h, ly + lh) + 4 - hy];
      shapes.push({ t: 'rect', x: hr[0], y: hr[1], w: hr[2], h: hr[3], fill: 'transparent', ui: true, hit: true, group: n.id });
      hit.push({ id: n.id, rect: hr });
    });

    // comparison callout in an empty corner
    if (compare && spec.compare && spec.compare.bullets && spec.compare.bullets.length) {
      const bw = 560, items = [];
      let bh = 30;
      spec.compare.bullets.forEach((b) => {
        const lines = wrap(dec(b), 16, 400, bw - 22);
        items.push(lines);
        bh += lines.length * 22 + 8;
      });
      const occupied = nodes.map((n) => n.lr).concat(nodes.map((n) => [n.x, n.top, NW, n.h]));
      const boxes = bandBoxes().map((b) => b.r);
      const free = (r) => !occupied.some((o) => overlap(r, o, 16)) && !boxes.some((o) => overlap(r, o, 16));
      const cands = [[MARGIN, bottom - bh], [W - MARGIN - bw, HEAD], [W - MARGIN - bw, bottom - bh], [MARGIN, HEAD + 40]];
      let pos = cands.find(([x, y]) => free([x, y, bw, bh]));
      if (!pos) { pos = [MARGIN, bottom + 36]; bottom += 36 + bh; }
      const [cx, cy] = pos;
      shapes.push({ t: 'text', x: cx, y: cy + 18, text: `What changed vs ${dec(spec.compare.vs)}`, size: 18, weight: 600, fill: INK, anchor: 'start' });
      let yy = cy + 30;
      items.forEach((lines) => {
        shapes.push({ t: 'circle', cx: cx + 5, cy: yy + 11, r: 3, fill: INK2 });
        lines.forEach((ln) => {
          shapes.push({ t: 'text', x: cx + 18, y: yy + 16, text: ln, size: 16, weight: 400, fill: INK2, anchor: 'start' });
          yy += 22;
        });
        yy += 8;
      });
    }

    // header
    shapes.push({ t: 'text', x: MARGIN, y: 44 + 38, text: title, size: 40, weight: 600, fill: INK, anchor: 'start', spacing: -0.5 });
    shapes.push({ t: 'text', x: MARGIN, y: 44 + 48 + 4 + 19, text: subtitle, size: 18, weight: 400, fill: SUBINK, anchor: 'start' });

    // legend + footer
    const used = new Set(nodes.map((n) => n.color).concat(links.map((l) => l.color)));
    const legend = LEGEND.filter(([k]) => used.has(k) || k === 'rev' || k === 'profit' || k === 'cost');
    const lgItems = legend.map(([k, t]) => ({ k, t, w: 14 + 8 + measure(t, 14, 400) }));
    if (compare) lgItems.push({ k: 'strip', t: `Dark strip = increase vs ${dec(spec.compare.vs)}`, w: 0 });
    if (compare) lgItems[lgItems.length - 1].w = 14 + 8 + measure(lgItems[lgItems.length - 1].t, 14, 400);
    const lgW = lgItems.reduce((s, it) => s + it.w, 0) + 20 * (lgItems.length - 1);
    const footer = (spec.footer || []).map(dec);
    if (compare) {
      footer.push(`Comparison view: band width = current quarter; dark strip = increase vs ${dec(spec.compare.vs)} (no strip = it fell). ` +
        'Δ = scale + mix: scale = change explained by the parent node growing, mix = change in the item’s share of its parent. ' +
        'n/m = a comparison period was negative.');
    }
    const fW = W - 2 * MARGIN - lgW - 40;
    const fLines = [];
    footer.forEach((p) => wrap(p, 13, 400, fW).forEach((l) => fLines.push(l)));
    const fH = fLines.length * 18;
    const H = Math.ceil(bottom + 44 + fH + 30);
    let fy = H - 30 - fH;
    fLines.forEach((l) => {
      shapes.push({ t: 'text', x: MARGIN, y: fy + 13, text: l, size: 13, weight: 400, fill: INK3, anchor: 'start' });
      fy += 18;
    });
    let lx = W - MARGIN - lgW;
    const ly = H - 30 - 16;
    lgItems.forEach((it) => {
      if (it.k === 'strip') {
        shapes.push({ t: 'rect', x: lx, y: ly + 1, w: 14, h: 14, fill: PALETTE.profit.flow, r: 3 });
        shapes.push({ t: 'rect', x: lx, y: ly + 10, w: 14, h: 5, fill: PALETTE.profit.node });
      } else {
        shapes.push({ t: 'rect', x: lx, y: ly + 1, w: 14, h: 14, fill: PALETTE[it.k].node, r: 3 });
      }
      shapes.push({ t: 'text', x: lx + 22, y: ly + 13, text: it.t, size: 14, weight: 400, fill: INK2, anchor: 'start' });
      lx += it.w + 20;
    });

    return { W, H, bg: BG, shapes, hit, issues: issues.map((i) => i.n.id), nodes: nodes.map((n) => ({ id: n.id, label: n.lr, bar: [n.x, n.top, NW, n.h] })) };
  }

  // ---------- renderers ----------
  function toSVG(scene, aria) {
    const out = [`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${scene.W} ${scene.H}" width="${scene.W}" height="${scene.H}" ` +
      `role="img" aria-label="${esc(aria || 'Earnings Sankey')}" font-family="${esc(FONT)}" style="font-variant-numeric: tabular-nums">`,
      `<rect x="0" y="0" width="${scene.W}" height="${scene.H}" fill="${scene.bg}"/>`];
    let group = null;
    const close = () => { if (group !== null) out.push('</g>'); group = null; };
    scene.shapes.forEach((s) => {
      if (s.band) {
        close();
        out.push(`<path class="band" data-s="${esc(s.ls)}" data-t="${esc(s.lt)}" d="${s.d}" fill="${s.fill}"/>`);
        return;
      }
      if ((s.group || null) !== group) {
        close();
        if (s.group) { out.push(`<g class="node" data-node="${esc(s.group)}">`); group = s.group; }
      }
      if (s.t === 'rect') {
        const cls = s.hit ? ' class="hit"' : s.group ? ' class="bar"' : '';
        out.push(`<rect${cls} x="${s.x.toFixed(2)}" y="${s.y.toFixed(2)}" width="${s.w.toFixed(2)}" height="${s.h.toFixed(2)}"` +
          `${s.r ? ` rx="${s.r}"` : ''} fill="${s.fill}"/>`);
      } else if (s.t === 'circle') {
        out.push(`<circle${s.marker ? ' class="note-mark"' : ''} cx="${s.cx.toFixed(2)}" cy="${s.cy.toFixed(2)}" r="${s.r}" fill="${s.fill}"/>`);
      } else if (s.t === 'text') {
        out.push(`<text x="${s.x.toFixed(2)}" y="${s.y.toFixed(2)}" font-size="${s.size}" font-weight="${s.weight}" fill="${s.fill}"` +
          `${s.anchor !== 'start' ? ` text-anchor="${s.anchor}"` : ''}${s.spacing ? ` letter-spacing="${s.spacing}"` : ''}>${esc(s.text)}</text>`);
      }
    });
    close();
    out.push('</svg>');
    return out.join('');
  }

  function toCanvas(scene, scale) {
    const c = document.createElement('canvas');
    c.width = Math.round(scene.W * scale);
    c.height = Math.round(scene.H * scale);
    const ctx = c.getContext('2d');
    ctx.scale(scale, scale);
    ctx.fillStyle = scene.bg;
    ctx.fillRect(0, 0, scene.W, scene.H);
    scene.shapes.forEach((s) => {
      if (s.ui) return;                         // notes markers and hit areas are screen-only
      ctx.fillStyle = s.fill;
      if (s.t === 'path') ctx.fill(new Path2D(s.d));
      else if (s.t === 'rect') {
        if (s.r && ctx.roundRect) { ctx.beginPath(); ctx.roundRect(s.x, s.y, s.w, s.h, s.r); ctx.fill(); } else ctx.fillRect(s.x, s.y, s.w, s.h);
      } else if (s.t === 'circle') { ctx.beginPath(); ctx.arc(s.cx, s.cy, s.r, 0, Math.PI * 2); ctx.fill(); }
      else if (s.t === 'text') {
        ctx.font = `${s.weight} ${s.size}px ${FONT}`;
        ctx.textAlign = s.anchor === 'end' ? 'right' : s.anchor === 'middle' ? 'center' : 'left';
        ctx.textBaseline = 'alphabetic';
        if (s.spacing && 'letterSpacing' in ctx) ctx.letterSpacing = `${s.spacing}px`;
        ctx.fillText(s.text, s.x, s.y);
        if (s.spacing && 'letterSpacing' in ctx) ctx.letterSpacing = '0px';
      }
    });
    return c;
  }

  // a one-page PDF holding the chart as a JPEG (no library needed)
  function pdfFromJpeg(jpeg, iw, ih, pw, ph) {
    const enc = new TextEncoder();
    const parts = [], offsets = [];
    let len = 0;
    const push = (x) => { const b = typeof x === 'string' ? enc.encode(x) : x; parts.push(b); len += b.length; };
    push('%PDF-1.4\n%âãÏÓ\n');
    const obj = (n, body) => { offsets[n] = len; push(`${n} 0 obj\n`); [].concat(body).forEach(push); push('\nendobj\n'); };
    obj(1, '<< /Type /Catalog /Pages 2 0 R >>');
    obj(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
    obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
    obj(4, [`<< /Type /XObject /Subtype /Image /Width ${iw} /Height ${ih} /ColorSpace /DeviceRGB /BitsPerComponent 8 ` +
      `/Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`, jpeg, '\nendstream']);
    const content = `q ${pw} 0 0 ${ph} 0 0 cm /Im0 Do Q`;
    obj(5, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
    const xref = len;
    push('xref\n0 6\n0000000000 65535 f \n' + [1, 2, 3, 4, 5].map((i) => String(offsets[i]).padStart(10, '0') + ' 00000 n \n').join('') +
      `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    const out = new Uint8Array(len);
    let o = 0;
    parts.forEach((p) => { out.set(p, o); o += p.length; });
    return out;
  }

  function canvasBlob(canvas, type, quality) {
    return new Promise((res) => canvas.toBlob(res, type, quality));
  }

  async function exportScene(scene, format) {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const canvas = toCanvas(scene, 2);
    if (format === 'png') return canvasBlob(canvas, 'image/png');
    if (format === 'jpg') return canvasBlob(canvas, 'image/jpeg', 0.94);
    const blob = await canvasBlob(canvas, 'image/jpeg', 0.95);
    const jpeg = new Uint8Array(await blob.arrayBuffer());
    const pdf = pdfFromJpeg(jpeg, canvas.width, canvas.height, +(scene.W * 0.75).toFixed(2), +(scene.H * 0.75).toFixed(2));
    return new Blob([pdf], { type: 'application/pdf' });
  }

  global.Sankey = { layout, toSVG, toCanvas, exportScene, PALETTE, dec, esc };
})(window);
