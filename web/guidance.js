/* The Sankey's "Show guidance" view: the next period as the company guided it.

   Data: disclosures/data/holders/<TICKER>.json → guidance (disclosures/app/events8k.py guidance_by_ticker, read by
   disclosures/app/guidance.py from the latest earnings release): per metric the guided range, its period and basis, and
   the change against the release's own prior range or else the company's previous release (raised / lowered by the
   midpoint, narrowed / widened by the width, reaffirmed, initiated, withdrawn).

   future(base, guidance, opts) → a Sankey spec (web/sankey.js layout) of the guided period:
   - guided lines (GAAP or basis-free figures only: revenue, gross margin or gross profit, operating expenses,
     operating income or margin, other income, tax rate, net income) take the guided midpoint; the bar carries a
     dashed box for the guided range;
   - every other line keeps its share of its parent from the base period ("assumed"), so the chart adds up;
   - the revenue lines on the left keep their mix; the cash-flow part after net earnings is left out (not guided);
   - a quarter with only full-year guidance is drawn as the implied last quarter when the first three are on file
     (full year minus Q1–Q3 as reported).
   Colours: only what is new changes colour. Guided lines are violet / indigo / plum; every other line keeps the
   standard grey, green and red. Compared with the quarter just reported or the year-ago quarter (compare, compare_y;
   drawn by web/sankey.js like the history comparison), the part a band already had stays in its standard colour, the
   increase is a violet strip and a decrease is hatched; each line gets Y/Y · Q/Q and "● Δ · scale · mix". Non-GAAP
   figures (adjusted EPS, EBITDA …) are listed in the footer, never drawn into GAAP flows. No dependencies; works in
   the browser and in node (tests). */
(function (global) {
  'use strict';

  const WORD = { raised: '▲ raised', lowered: '▼ lowered', narrowed: '→← narrowed', widened: '←→ widened', reaffirmed: '= reaffirmed',
    initiated: '✦ initiated', withdrawn: '✕ withdrawn', mixed: '▲▼ mixed', new: 'first on file', updated: 'updated' };
  const NAMES = { revenue: 'Revenue', gross_margin: 'Gross margin', gross_profit: 'Gross profit', opex: 'Operating expenses',
    operating_income: 'Operating income', operating_margin: 'Operating margin', other_income: 'Other income', tax_rate: 'Tax rate',
    net_income: 'Net income', eps: 'EPS', ffo_ps: 'FFO per share', ebitda: 'EBITDA', ebitda_margin: 'EBITDA margin', fcf: 'Free cash flow',
    ocf: 'Operating cash flow', capex: 'Capital expenditures', interest_expense: 'Interest expense', sbc: 'Stock-based compensation',
    da: 'Depreciation & amortization', ffo: 'FFO', net_interest_margin: 'Net interest margin' };
  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const enc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function money(v) {
    const a = Math.abs(v), sg = v < 0 ? '−' : '';
    if (a >= 0.995e9) return `${sg}$${(a / 1e9).toFixed(a >= 100e9 ? 0 : a >= 10e9 ? 1 : 2)}B`;
    if (a >= 0.995e6) return `${sg}$${(a / 1e6).toFixed(a >= 100e6 ? 0 : 1)}M`;
    return `${sg}$${Math.round(a / 1e3)}K`;
  }
  function val(v, unit) {
    if (v == null) return '—';
    if (unit === 'usd') return money(v);
    if (unit === 'ps') return `${v < 0 ? '−' : ''}$${Math.abs(v).toFixed(2)}`;
    if (unit === 'pct') return `${+v.toFixed(2)}%`;
    if (unit === 'growth') return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(+v.toFixed(2))}%`;
    if (unit === 'bps') return `${v > 0 ? '+' : ''}${v} bps`;
    return String(v);
  }
  // "$63.7B–$66.3B", "≈ $6.7B", "at least $290M"
  function range(it) {
    if (!it || it.lo == null) return '';
    const one = Math.abs(it.hi - it.lo) < 1e-9 * Math.max(1, Math.abs(it.hi));
    const v = one ? val(it.lo, it.unit) : `${val(it.lo, it.unit)}–${val(it.hi, it.unit).replace(/^\$/, it.unit === 'usd' || it.unit === 'ps' ? '$' : '')}`;
    return `${it.bound === 'min' ? 'at least ' : it.bound === 'max' ? 'up to ' : it.approx && one ? '≈ ' : ''}${v}`;
  }
  // the change words of one item: ['▲ raised', '→← narrowed']
  function words(it) {
    const w = [];
    const c = it.change || it.said;
    if (c && c !== 'new' && WORD[c] && !(c === 'reaffirmed' && it.range)) w.push(WORD[c]);
    if (it.range && WORD[it.range]) w.push(WORD[it.range]);
    if (c === 'reaffirmed' && it.range) w.push('midpoint kept');
    if (it.ends && !/·/.test(it.ends)) w.push(it.ends);
    return w;
  }
  function priorText(it) {
    if (!it.prior) return '';
    return `from ${range(Object.assign({ unit: it.unit }, it.prior))}${it.prior.src === 'earlier release' && it.prior.filed ? ` (release of ${fdate(it.prior.filed)})` : ''}`;
  }
  function fdate(x) {
    if (!x) return '';
    const d = new Date(x + 'T00:00:00Z');
    return isNaN(d) ? x : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }
  const mid = (it) => (it.lo + it.hi) / 2;

  // ---------- periods ----------
  // a period label of the site ("Q2 FY27", "Q3 2026", "FY26") → {q, y (4 digits)}
  function parseLabel(label) {
    const m = /Q([1-4])\s*(?:FY)?\s*'?(\d{2,4})/i.exec(label || '');
    if (m) return { q: +m[1], y: +m[2] < 100 ? 2000 + +m[2] : +m[2] };
    const f = /FY\s*'?(\d{2,4})/i.exec(label || '');
    return f ? { q: null, y: +f[1] < 100 ? 2000 + +f[1] : +f[1] } : null;
  }
  // a guidance period ("Q3 FY2027", "Q4 2026", "FY2026") → {q, y, fiscal}
  function parsePeriod(p) {
    const d = /^(Q|FY)@(\d{4}-\d{2}-\d{2})$/.exec(p || '');        // a period named by the day it ends (guidance.py PER_DATE)
    if (d) return { q: d[1] === 'Q' ? 0 : null, y: +d[2].slice(0, 4), at: d[2] };
    const m = /^Q([1-4]) (FY)?(\d{4})$/.exec(p || '');
    if (m) return { q: +m[1], y: +m[3], fiscal: !!m[2] };
    const f = /^FY(\d{4})$/.exec(p || '');
    return f ? { q: null, y: +f[1] } : null;
  }
  const usable = (g) => ((g && g.items) || []).filter((it) => it.lo != null && !it.scope && it.period && it.period !== 'long-term' && it.unit &&
    it.unit !== 'growth' && it.unit !== 'bps');
  // GAAP, else basis-free; never non-GAAP into the flows
  function choose(items, metric, period, units) {
    const xs = items.filter((it) => it.metric === metric && it.period === period && units.includes(it.unit));
    return xs.find((x) => x.basis === 'GAAP') || xs.find((x) => !x.basis) || null;
  }

  // which period to draw: {kind: 'q' | 'implied' | 'fy', period, label}
  function target(g, base, company) {
    const items = usable(g);
    const revs = items.filter((it) => it.metric === 'revenue' && it.unit === 'usd' && it.basis !== 'non-GAAP');
    const b = parseLabel(base.label);
    if (!b) return null;
    if (base.period !== 'fy' && b.q) {
      const nq = b.q === 4 ? 1 : b.q + 1, ny = b.q === 4 ? b.y + 1 : b.y;
      const qs = revs.map((it) => [it, parsePeriod(it.period)]).filter(([, p]) => p && p.q === nq && Math.abs(p.y - ny) <= 1)
        .sort((x, y) => Math.abs(x[1].y - ny) - Math.abs(y[1].y - ny));
      if (qs.length) return { kind: 'q', period: qs[0][0].period, label: qs[0][0].period };
      // full-year guidance, three quarters of that fiscal year on file: the implied fourth quarter
      const per = (company && company.periods && company.periods.q) || [];
      const cur = per.find((x) => x.end === base.end);
      if (cur && cur.q === 3) {
        const fy = revs.find((it) => { const p = parsePeriod(it.period); return p && p.q === null && p.y === cur.fy; });
        const ytd = per.filter((x) => x.fy === cur.fy && x.q >= 1 && x.q <= 3);
        if (fy && ytd.length === 3) return { kind: 'implied', period: fy.period, label: `Q4 FY${cur.fy} (implied)`, fy: cur.fy, ytd: ytd.map((x) => x.end) };
      }
      return null;
    }
    // a full year: the next fiscal year's guidance
    const fys = revs.filter((it) => { const p = parsePeriod(it.period); return p && p.q === null && p.y === b.y + 1; });
    return fys.length ? { kind: 'fy', period: fys[0].period, label: fys[0].period } : null;
  }

  // ---------- the projection ----------
  const ROLE = (c) => (c === 'rev' || c === 'profit' || c === 'cost' ? c : 'cost');

  // guided values: {nodeId: {v(F) → value, lo(F), hi(F), it}} (F: future values computed so far)
  // opts.full (the ultra-detailed canvas, web/flowdetail.js): the cash lines a company guides too — capital spending,
  // operating and free cash flow, depreciation & amortization, stock-based pay, interest expense
  function guides(items, period, implied, opts) {
    const G = {};
    const pick = (m, u) => choose(items, m, period, u);
    const sub = (id, x) => (implied ? x - (implied.ytd[id] || 0) : x);
    const rev = pick('revenue', ['usd']);
    if (rev) G.revenue = { it: rev, at: () => sub('revenue', mid(rev)), lo: () => sub('revenue', rev.lo), hi: () => sub('revenue', rev.hi) };
    const gm = pick('gross_margin', ['pct']), gpu = pick('gross_profit', ['usd']);
    if (gpu) G.gp = { it: gpu, at: () => sub('gp', mid(gpu)), lo: () => sub('gp', gpu.lo), hi: () => sub('gp', gpu.hi) };
    else if (gm && implied && rev) {      // full-year margin × full-year revenue − the gross profit so far
      G.gp = { it: gm, at: () => mid(gm) / 100 * mid(rev) - (implied.ytd.gp || 0), lo: () => gm.lo / 100 * mid(rev) - (implied.ytd.gp || 0), hi: () => gm.hi / 100 * mid(rev) - (implied.ytd.gp || 0) };
    } else if (gm) G.gp = { it: gm, at: (F) => mid(gm) / 100 * F.revenue, lo: (F) => gm.lo / 100 * F.revenue, hi: (F) => gm.hi / 100 * F.revenue };
    const opex = pick('opex', ['usd']);
    if (opex) G.opex = { it: opex, at: () => sub('opex', mid(opex)), lo: () => sub('opex', opex.lo), hi: () => sub('opex', opex.hi) };
    const oi = pick('operating_income', ['usd']), om = pick('operating_margin', ['pct']);
    if (oi) G.oi = { it: oi, at: () => sub('oi', mid(oi)), lo: () => sub('oi', oi.lo), hi: () => sub('oi', oi.hi) };
    else if (om && !implied) G.oi = { it: om, at: (F) => mid(om) / 100 * F.revenue, lo: (F) => om.lo / 100 * F.revenue, hi: (F) => om.hi / 100 * F.revenue };
    const other = pick('other_income', ['usd']);
    if (other && mid(other) > 0) G.nonop_in = { it: other, at: () => sub('nonop_in', mid(other)), lo: () => sub('nonop_in', other.lo), hi: () => sub('nonop_in', other.hi) };
    // the tax rate: this period's, else the full year's rate of the same fiscal year (companies guide it for the year)
    const pp = /(\d{4})$/.exec(period || '');
    const tax = pick('tax_rate', ['pct']) || (pp ? choose(items, 'tax_rate', `FY${pp[1]}`, ['pct']) : null);
    if (tax && !implied) G.tax = { it: tax, at: (F) => mid(tax) / 100 * F.pretax, lo: (F) => tax.lo / 100 * F.pretax, hi: (F) => tax.hi / 100 * F.pretax, of: 'pretax' };
    const ni = pick('net_income', ['usd']);
    if (ni && mid(ni) > 0) G.net = { it: ni, at: () => sub('net', mid(ni)), lo: () => sub('net', ni.lo), hi: () => sub('net', ni.hi) };
    if (opts && opts.full && !implied) {
      [['capex', 'capex'], ['ocf', 'ocf'], ['fcf', 'fcf'], ['da', 'da'], ['sbc', 'sbc'], ['interest_expense', 'interest']].forEach(([m, id]) => {
        const it = pick(m, ['usd']);
        if (it && mid(it) > 0) G[id] = { it, at: () => mid(it), lo: () => it.lo, hi: () => it.hi };
      });
    }
    return G;
  }

  function project(base, G, opts) {
    const all = new Map(base.nodes.map((n) => [n.id, n]));
    const rev = all.get('revenue');
    if (!rev || !G.revenue) return null;
    const net = all.get('net');
    const cut = net && !(opts && opts.full) ? net.col : Infinity;      // the canvas carries the cash flows on
    const nodes = base.nodes.filter((n) => n.col <= cut);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = base.links.filter((l) => byId.has(l.s) && byId.has(l.t) && l.v > 0);
    const outs = new Map(), ins = new Map();
    nodes.forEach((n) => { outs.set(n.id, []); ins.set(n.id, []); });
    links.forEach((l) => { outs.get(l.s).push(l); ins.get(l.t).push(l); });
    // downstream of revenue
    const down = new Set(['revenue']);
    for (let grew = true; grew;) {
      grew = false;
      links.forEach((l) => { if (down.has(l.s) && !down.has(l.t)) { down.add(l.t); grew = true; } });
    }
    const F = {}, LV = new Map(), guided = {}, notes = [];
    const R0 = rev.v, R = G.revenue.at(F);
    if (!(R > 0)) return null;
    const f = R / R0;
    // left of revenue (segments, products) and what hangs off them: the same mix
    nodes.forEach((n) => { if (!down.has(n.id) && (n.col < rev.col || ins.get(n.id).some((l) => !down.has(l.s) && byId.get(l.s).col < rev.col))) F[n.id] = n.v * f; });
    links.forEach((l) => { if (F[l.s] != null && !down.has(l.s)) LV.set(l, l.v * f); });
    F.revenue = R;
    guided.revenue = true;
    // other sources into the flows (other income, a tax benefit): guided, else as in the base period
    nodes.forEach((n) => {
      if (!down.has(n.id) && F[n.id] == null) {
        F[n.id] = G[n.id] ? G[n.id].at(F) : n.v;
        if (G[n.id]) guided[n.id] = true;
        outs.get(n.id).forEach((l) => LV.set(l, F[n.id] * (l.v / (n.v || 1))));
      }
    });
    // walk the flows: a node is known when all its inflows are; its outflows are split guided first, the rest by base shares
    const done = new Set(Object.keys(F).filter((k) => k !== 'revenue'));
    const queue = ['revenue'];
    let guard = 0;
    while (queue.length && guard++ < 500) {
      const id = queue.shift();
      const os = outs.get(id) || [];
      if (os.length) {
        const total = F[id];
        const fixed = new Map();
        os.forEach((l) => {
          const g = G[l.t];
          if (g && ins.get(l.t).length === 1) {
            const v = g.at(F);
            if (v != null && isFinite(v) && v >= 0) fixed.set(l, v);
          }
        });
        if (fixed.size === os.length && os.length > 1) {          // all children guided: the profit line is the remainder
          const prof = os.find((l) => byId.get(l.t).color === 'profit') || os[0];
          fixed.delete(prof);
          notes.push(`${dec(byId.get(prof.t).name)} is the remainder of ${dec(byId.get(id).name)} (its own guidance did not add up).`);
        }
        let rest = total - [...fixed.values()].reduce((a, b) => a + b, 0);
        if (rest < -1e-6 * Math.abs(total)) {
          notes.push(`The guided parts of ${dec(byId.get(id).name)} add up to more than it; the rest is drawn as zero.`);
          rest = 0;
        }
        const free = os.filter((l) => !fixed.has(l));
        const baseSum = free.reduce((a, l) => a + l.v, 0);
        os.forEach((l) => {
          if (fixed.has(l)) { LV.set(l, fixed.get(l)); guided[l.t] = true; } else LV.set(l, Math.max(0, baseSum > 0 ? rest * l.v / baseSum : rest / free.length));
        });
      }
      done.add(id);
      os.forEach((l) => {
        const t = l.t;
        if (done.has(t) || queue.includes(t)) return;
        if (ins.get(t).every((x) => LV.has(x))) {
          F[t] = ins.get(t).reduce((a, x) => a + LV.get(x), 0);
          queue.push(t);
        }
      });
    }
    return { F, LV, guided, nodes, links, byId, ins, outs, notes, f };
  }

  // the chart's own number formats (pipeline/sankey.py Fmt): one unit for the chart, B when revenue is in billions
  function fmtOf(revenue) {
    const B = revenue >= 1e9;
    const money = (v) => {
      if (v == null) return 'n/a';
      const a = Math.abs(v), sg = v < 0 ? '−' : '';
      if (a >= 0.95e12) return `${sg}$${(a / 1e12).toFixed(2)}T`;
      if (B && a >= 5e6) { const b = a / 1e9; return `${sg}$${b >= 0.95 ? b.toFixed(1) : b.toFixed(2)}B`; }
      const m = a / 1e6;
      return m >= 0.95 ? `${sg}$${m.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M` : `${sg}$${Math.round(a / 1e3).toLocaleString('en-US')}K`;
    };
    const num = (v) => {
      const x = v / (B ? 1e9 : 1e6), a = Math.abs(x);
      return `${v > 0 ? '+' : v < 0 ? '−' : '±'}${a >= 0.95 ? a.toFixed(1) : a.toFixed(2)}`;
    };
    const delta = (v) => `${v > 0 ? '+' : v < 0 ? '−' : '±'}${money(Math.abs(v))}`;
    return { money, num, delta };
  }
  function pctChange(a, b) {
    if (a == null || b == null) return '—';
    if (a <= 0 || b <= 0) return 'n/m';
    const g = Math.round((a / b - 1) * 100);
    return `${g > 0 ? '+' : g < 0 ? '−' : ''}${Math.abs(g)}%`;
  }
  const shareOf = (v, p) => { if (!(p > 0) || v == null) return null; const x = v / p * 100; return x < 10 ? `${x.toFixed(1)}%` : `${x.toFixed(0)}%`; };

  // the node a base line's "· 25% of revenue" refers to: the one its stated share fits (the line it flows from or into
  // first, then any line of the chart)
  function parentOf(n, P) {
    const line = (n.lines || [])[1];
    const m = line && /·\s*([\d.,]+)%\s+of\s+(.+)$/.exec(dec(line[1]));
    if (!m || !(n.v > 0)) return null;
    const pct = parseFloat(m[1].replace(/,/g, '')), tol = /\./.test(m[1]) ? 0.051 : 0.51;
    const cands = [...(P.ins.get(n.id) || []).map((l) => l.s), ...(P.outs.get(n.id) || []).map((l) => l.t), ...P.nodes.map((x) => x.id)];
    for (const id of cands) {
      const p = P.byId.get(id);
      if (p && p.id !== n.id && p.v > 0 && Math.abs(n.v / p.v * 100 - pct) <= tol) return { id: p.id, label: m[2] };
    }
    return null;
  }
  // the base line's "· 25% of revenue" wording, recomputed for the guided period
  function shareText(n, F, par) {
    const s = par && shareOf(F[n.id], F[par.id]);
    return s ? ` · ${s} of ${par.label}` : '';
  }
  // "84% of operating expenses" in the base period (the assumption an unguided line keeps)
  function baseShare(n, P, par) {
    const p = par && P.byId.get(par.id);
    const x = p && shareOf(n.v, p.v);
    return x ? `${x} of ${par.label}` : '';
  }

  // the guidance view plus the company's guidance record (opts.history: holders/<TICKER>.json → guidance_history)
  function future(base, g, opts) {
    const o = opts || {};
    const rec = o.history ? record(o.history, o.company) : null;
    const out = futureSpec(base, g, o);
    if (rec && rec.metrics.length) {
      out.record = rec;
      if (!out.error) {
        const lines = rec.metrics.filter((m) => m.hits.n).slice(0, 3).map((m) => summaryLine(m));
        const moved = rec.metrics.filter((m) => movesLine(m)).slice(0, 2).map((m) => `${m.name} guides between releases: ${movesLine(m)}`);
        if (lines.length || moved.length) {
          out.footer.splice(1, 0, `Guidance record (${rec.releases} release${rec.releases === 1 ? '' : 's'} since ${fdate(rec.since)}, held to the reported GAAP figures): ` +
            lines.concat(moved).join('; ') + '.');
        }
      }
    }
    return out;
  }

  function futureSpec(base, g, opts) {
    const o = opts || {};
    if (!g || !(g.items || []).length) return { error: 'No guidance on file for this company in the last 120 days of 8-K earnings releases.' };
    if (g.label === 'withdrawn' && !usable(g).length) return { error: 'The company withdrew its guidance.' };
    const tg = target(g, base, o.company);
    if (!tg) return { error: `The latest release${g.filed ? ` (${fdate(g.filed)})` : ''} gives no revenue guidance for the period after ${dec(base.label)}.` };
    const items = usable(g);
    let implied = null;
    if (tg.kind === 'implied') {
      const qs = (o.company && o.company.quarters) || [];
      const ytd = {};
      tg.ytd.forEach((end) => {
        const q = qs.find((x) => x.end === end);
        (q ? q.nodes : []).forEach((n) => { ytd[n.id] = (ytd[n.id] || 0) + (+n.v || 0); });
      });
      implied = { ytd };
    }
    const G = guides(items, tg.period, implied, { full: o.full });
    // a guided revenue far from the base period is a misread (or a different scope): not drawn
    const R = G.revenue && G.revenue.at({});
    if (!(R > 0) || R < base.nodes.find((n) => n.id === 'revenue').v * 0.4 || R > base.nodes.find((n) => n.id === 'revenue').v * 2.5) {
      return { error: 'The guided revenue does not match the scale of the reported revenue; not drawn.' };
    }
    const P = project(base, G, { full: o.full });
    if (!P) return { error: 'This chart has no revenue node to project.' };
    const { F, LV, guided } = P;
    const per = tg.label.replace(/^FY(\d{4})$/, 'FY$1');
    const fm = fmtOf(F.revenue);
    const parent = {};
    P.nodes.forEach((n) => { const x = parentOf(n, P); if (x) parent[n.id] = x; });
    // the periods it is compared with (the historical comparison's grammar): the period just reported and, for a
    // quarter, the same quarter a year earlier
    const yq = yearAgo(tg, base, o.company);
    const valuesOf = (spec) => spec ? new Map(spec.nodes.map((n) => [n.id, +n.v])) : new Map();
    const curV = valuesOf(base), agoV = valuesOf(yq);
    const linkOf = (spec) => spec ? new Map(spec.links.map((l) => [`${l.s}|${l.t}`, +l.v])) : new Map();
    const curL = linkOf(base), agoL = linkOf(yq);
    const deltaLine = (id, v, vals, label) => {
      const v0 = vals.get(id);
      if (v0 == null) return ['cnt', enc(`Δ n/a (not in ${dec(label)})`)];
      const d = v - v0;
      const st = Math.abs(d) <= Math.abs(v0) * 0.005 ? 'cnt' : d > 0 ? 'cup' : 'cdn';
      let txt = `● Δ ${fm.delta(d)}`;
      const p = parent[id];
      if (p && vals.get(p.id) != null && F[p.id] != null) {
        const c0 = v0, c1 = v, p0 = vals.get(p.id), p1 = F[p.id];
        if (p0 <= 0 || p1 <= 0 || c0 < 0 || c1 < 0) txt += ' · scale/mix n/m';
        else {
          const scale = (p1 - p0) * c0 / p0, mix = p1 * (c1 / p1 - c0 / p0);
          txt += ` · scale ${fm.num(scale)} · mix ${fm.num(mix)}`;
        }
      }
      return [st, enc(txt)];
    };
    const nodes = [];
    P.nodes.forEach((n) => {
      const v = F[n.id];
      if (!(v > 0)) return;
      const g1 = G[n.id] && guided[n.id] ? G[n.id] : null;
      const role = ROLE(n.color);
      const lines = [[(n.lines && n.lines[0] && n.lines[0][0]) || 'name', n.name], ['val', enc(fm.money(v)) + enc(shareText(n, F, parent[n.id]))],
        ['mut', tg.kind === 'fy' ? `Y/Y ${pctChange(v, curV.get(n.id))}` : `Y/Y ${pctChange(v, yq ? agoV.get(n.id) : null)} · Q/Q ${pctChange(v, curV.get(n.id))}`]];
      let note;
      if (g1) {
        const it = g1.it, w = words(it);
        const shown = it.unit === 'usd' ? range(Object.assign({}, it, implied ? { lo: g1.lo(F), hi: g1.hi(F) } : {})) : range(it);
        lines.push([it.change === 'lowered' || it.change === 'withdrawn' ? 'gdn' : it.change === 'raised' ? 'gup' : 'gnt',
          enc(`guided ${it.unit !== 'usd' ? `${NAMES[it.metric] ? NAMES[it.metric].toLowerCase() + ' ' : ''}` : ''}${shown}${w.length ? ' · ' + w.join(' · ') : ''}`)]);
        if (it.prior) lines.push(['gas', enc(priorText(it))]);
        note = { guided: true, item: it };
      } else {
        lines.push(['gas', enc(n.col < (P.byId.get('revenue') || {}).col ? `assumed: same mix as ${dec(base.label)}` : (baseShare(n, P, parent[n.id]) ? `assumed: ${baseShare(n, P, parent[n.id])} in ${dec(base.label)}` : P.ins.get(n.id).length ? 'the sum of the lines into it' : `assumed: as in ${dec(base.label)}`))]);
        note = { guided: false };
      }
      // only the guided lines change colour; every other line keeps its standard grey / green / red
      const out = Object.assign({}, n, { v, color: g1 ? 'f_' + role : n.color, lines, gnote: note, notes: undefined,
        cmp: deltaLine(n.id, v, curV, base.label), cmp_y: yq ? deltaLine(n.id, v, agoV, yq.label) : undefined });
      if (g1 && g1.lo && g1.hi) {
        const lo = g1.lo(F), hi = g1.hi(F);
        if (isFinite(lo) && isFinite(hi) && hi > lo) out.range = [lo, hi];
      }
      nodes.push(out);
    });
    const keep = new Set(nodes.map((n) => n.id));
    const links = P.links.filter((l) => keep.has(l.s) && keep.has(l.t) && LV.get(l) > 0)
      .map((l) => {
        const k = `${l.s}|${l.t}`;
        return { s: l.s, t: l.t, v: LV.get(l), color: guided[l.t] ? 'f_' + ROLE(l.color) : l.color,
          q: curL.has(k) ? curL.get(k) : null, y: yq && agoL.has(k) ? agoL.get(k) : null };
      });
    const nGuided = nodes.filter((n) => n.gnote.guided).length;
    const company = dec(o.name || '');
    // everything the release guided, drawn or not
    const listed = (g.items || []).filter((it) => it.period !== 'long-term' && it.unit !== 'bps').slice(0, 14).map((it) => {
      const w = words(it);
      return `${it.basis === 'non-GAAP' ? 'adj. ' : it.basis === 'GAAP' ? 'GAAP ' : ''}${NAMES[it.metric] || it.metric}${it.scope === 'segment' ? ', a segment' : it.scope === 'organic' ? ', organic' : ''}${it.period ? ` (${it.period})` : ''}` +
        `${it.lo != null ? ' ' + range(it) : ''}${w.length ? ' ' + w.join(' ') : ''}${it.prior ? ' ' + priorText(it) : ''}`;
    });
    const footer = [
      `Guidance view (not a forecast by Filing Flows): violet, indigo and plum = a figure ${company || 'the company'} guided, drawn at the midpoint; the dashed box ` +
      'spans the guided range and its tick marks the low end. Grey, green and red = not guided, in the standard colours: the line keeps its share of its parent from ' +
      `${dec(base.label)}, so the chart adds up. Change words: ▲ raised / ▼ lowered = the midpoint moved; →← narrowed / ←→ widened = the range ` +
      'width changed; = reaffirmed; ✦ initiated; ✕ withdrawn — against the prior range the release states, else the company’s previous release on file.',
      `In the release${g.filed ? ` of ${fdate(g.filed)}` : ''}: ${listed.join('; ')}.` + (listed.length < (g.items || []).length ? ' …' : ''),
      'Only GAAP or basis-free guidance is drawn into the flows; adjusted (non-GAAP) figures are listed, not drawn. ' +
        (o.full ? 'The cash flows go on: the cash lines guided (capital spending, operating and free cash flow, D&A, stock-based pay) as guided, the rest at their shares.' : 'The cash-flow part is left out (not guided).'),
    ];
    if (implied) footer.splice(1, 0, `${tg.label}: the full-year guidance minus the three reported quarters of FY${tg.fy}.`);
    P.notes.forEach((x) => footer.push(x));
    const words0 = (g.tags || []).filter((x) => x !== 'updated' && x !== 'mixed').map((x) => WORD[x]).filter(Boolean);
    // the comparison views (web/sankey.js draws them as for history: dark strip = increase, hatched = decrease, Δ = scale + mix)
    const vs = (spec, vals, ago) => ({
      vs: dec(spec.label), heading: `As guided vs ${dec(spec.label)}${ago ? ' (a year earlier)' : ''}`,
      title: `${company ? company + ': ' : ''}${per} as guided vs ${dec(spec.label)}${ago ? ' (a year earlier)' : ''}`,
      bullets: bulletsVs(nodes, vals, dec(spec.label), fm),
    });
    return {
      future: true, kind: tg.kind, period: tg.label, bg: '#fbfaff',
      title: `${company ? company + ': ' : ''}${per} as guided`,
      subtitle: `From the ${g.form || '8-K'} earnings release filed ${fdate(g.filed)}${words0.length ? ' · ' + words0.join(' · ') : ''} · ${nGuided} guided line${nGuided === 1 ? '' : 's'}, the rest at ${dec(base.label)} shares`,
      nodes, links, footer, checks: [],
      legend: [['f_rev', 'Guided revenue'], ['f_profit', 'Guided profit'], ['f_cost', 'Guided cost'], ['rev', 'Revenue (not guided)'],
        ['profit', 'Profit (not guided)'], ['cost', 'Costs (not guided)']],
      guidance: g, base: base.label,
      compare: vs(base, curV, tg.kind === 'fy'), compare_y: yq ? vs(yq, agoV, true) : null,
    };
  }

  // the same quarter a year before the guided one (fiscal quarters as the site labels them)
  function yearAgo(tg, base, company) {
    if (!company || tg.kind === 'fy') return null;
    const per = (company.periods && company.periods.q) || [];
    const cur = per.find((x) => x.end === base.end);
    if (!cur) return null;
    const nq = cur.q === 4 ? 1 : cur.q + 1, nfy = cur.q === 4 ? cur.fy + 1 : cur.fy;
    const ago = per.find((x) => x.q === nq && x.fy === nfy - 1);
    return ago ? (company.quarters || []).find((q) => q.end === ago.end) || null : null;
  }

  // "As guided vs …": the main changes in words (revenue, gross margin, operating profit, the largest guided move)
  function bulletsVs(nodes, vals, label, fm) {
    const out = [], N = new Map(nodes.map((n) => [n.id, n]));
    const pct = (a, b) => pctChange(a, b);
    const r = N.get('revenue'), r0 = vals.get('revenue');
    if (r && r0 != null) out.push(`Revenue ${fm.money(r.v)} as guided vs ${fm.money(r0)} in ${label}: ${fm.delta(r.v - r0)} (${pct(r.v, r0)}).`);
    const gp = N.get('gp'), gp0 = vals.get('gp');
    if (gp && r && gp0 != null && r0 > 0) {
      const a = gp.v / r.v * 100, b = gp0 / r0 * 100, d = a - b;
      out.push(`Gross margin ${a.toFixed(1)}% vs ${b.toFixed(1)}% in ${label} (${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(1)} pts)${gp.gnote && gp.gnote.guided ? ', from the guided margin' : ''}.`);
    }
    const oi = N.get('oi'), oi0 = vals.get('oi');
    if (oi && oi0 != null) {
      const dr = r && r0 != null ? r.v - r0 : 0, share = dr > 0 ? Math.round((oi.v - oi0) / dr * 100) : null;
      out.push(`Operating profit ${fm.money(oi.v)} vs ${fm.money(oi0)}: ${fm.delta(oi.v - oi0)} (${pct(oi.v, oi0)})${share != null && isFinite(share) ? `; ${share}% of the revenue change reaches it` : ''}${oi.gnote && oi.gnote.guided ? '' : ' (not guided itself: from the guided lines and assumed shares)'}.`);
    }
    const moves = nodes.filter((n) => n.gnote && n.gnote.guided && n.id !== 'revenue' && vals.get(n.id) != null)
      .map((n) => [n, n.v - vals.get(n.id)]).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
    if (moves.length) out.push(`Largest guided change after revenue: ${dec(moves[0][0].name)} ${fm.delta(moves[0][1])} (${pct(moves[0][0].v, vals.get(moves[0][0].id))}).`);
    return out;
  }

  // ---------- every source of guidance, one list ----------
  // The earnings releases (8-K) and the outlook of the 10-Q / 10-K MD&A (pipeline/outlook.py guided_items): a company that
  // guides in either counts. A filing's figure that only repeats what a release said in the three weeks before (the 10-Q
  // filed a few days after the earnings release) is left out; anything else it guides — a period, a metric or a range the
  // releases did not give, or an update — is a guide of its own, dated the filing's day.
  // history: holders → guidance_history; outlook: data/outlook/<cik>.json; latest: holders → guidance (the latest release)
  function sources(history, outlook, latest) {
    const byAcc = new Map();
    [latest].concat((history && history.releases) || []).forEach((r) => {
      if (r && r.filed && (r.items || []).length && !byAcc.has(r.accession || r.filed)) byAcc.set(r.accession || r.filed, Object.assign({ src: '8-K' }, r));
    });
    const rels = [...byAcc.values()];
    const key = (it) => [it.metric, it.basis || '', it.unit, it.period].join('|');
    const days = (a, b) => (Date.parse(a) - Date.parse(b)) / 864e5;
    ((outlook && outlook.docs) || []).filter((d) => d.kind === 'mdna' && (d.items || []).length && d.filed && !byAcc.has(d.accn)).forEach((d) => {
      const items = d.items.filter((it) => !rels.some((r) => r.src === '8-K' && days(d.filed, r.filed) >= 0 && days(d.filed, r.filed) <= 21 &&
        (r.items || []).some((x) => key(x) === key(it) && Math.abs(x.lo - it.lo) <= 1e-6 * Math.max(1, Math.abs(x.lo)) && Math.abs(x.hi - it.hi) <= 1e-6 * Math.max(1, Math.abs(x.hi)))));
      if (items.length) rels.push({ filed: d.filed, accession: d.accn, url: d.url, label: null, tags: [], items, src: d.form || '10-Q' });
    });
    rels.sort((a, b) => (a.filed < b.filed ? 1 : -1));
    return rels.length ? { releases: rels, complete: !!(history && history.complete) } : null;
  }

  // ---------- the reported period against its guidance ("vs guidance" on the quarter's or the year's own Sankey) ----------
  // spec: a reported quarter or fiscal year (the site's spec); src: {g: the latest guidance, hist: guidance_history}
  // (holders/<TICKER>.json); opts: {company, name}. The guide the period is held to is the last release on file, filed by
  // the period's end, that guided it (revenue in dollars, GAAP or basis-free) — as the record holds it. The guided figures
  // are projected onto the period before (the base the company guided from), as the guidance view does; a line is
  // compared only when guidance fixes it: a guided line, or one that follows from guided lines alone (cost of revenue =
  // guided revenue − guided gross profit; a line that is the only one out of a fixed line). Every other line stays plain.
  // → a copy of spec with links' g (guided value), nodes' g, grange and cmp_g ([style, text]) and compare_g, or {error}.
  function versus(spec, src, opts) {
    const o = opts || {}, company = o.company || {};
    if (!spec || !spec.nodes || !spec.end) return { error: 'No reported period.' };
    const all = sources(src && src.hist, src && src.outlook, src && src.g);
    const rels = all ? all.releases : [];
    if (!rels.length) return { error: 'No guidance on file for this company.' };
    const isFy = spec.period === 'fy';
    const P = periodsOf(company);
    let off = null;
    const here = (period, filed) => { const per = periodFor(period, filed, P, off); return !!per && per.end === spec.end && per.kind === (isFy ? 'fy' : 'q'); };
    let rel = null, items = null, tp = null;
    for (const r of rels) {
      if (r.filed > spec.end) continue;                    // given after the period ended: a result, not a guide
      off = yearOffset(r, P);
      const its = usable(r).filter((it) => here(it.period, r.filed));
      const rev = its.find((it) => it.metric === 'revenue' && it.unit === 'usd' && it.basis !== 'non-GAAP');
      if (rev) {
        rel = r; tp = rev.period;
        items = usable(r).map((it) => (here(it.period, r.filed) ? Object.assign({}, it, { period: tp }) : it));
        break;
      }
    }
    if (!rel) return { error: `No revenue guidance on file for ${dec(spec.label)} from a release before it ended.` };
    const list = ((isFy ? company.years : company.quarters) || []).filter((x) => x && x.end < spec.end && x.nodes)
      .sort((a, b) => (a.end < b.end ? 1 : -1));
    const base = list[0];
    if (!base) return { error: `The period before ${dec(spec.label)} is not on file, so its guidance cannot be drawn.` };
    const G = guides(items, tp, null, { full: o.full });
    const R = G.revenue && G.revenue.at({}), R0 = (base.nodes.find((n) => n.id === 'revenue') || {}).v;
    if (!(R > 0) || !(R0 > 0) || R < R0 * 0.4 || R > R0 * 2.5) return { error: 'The guided revenue does not match the scale of the reported revenue; not drawn.' };
    // a guided line far from the same line in the base period is a misread: not drawn as guided
    const B0 = new Map(base.nodes.map((n) => [n.id, +n.v]));
    Object.keys(G).forEach((id) => {
      if (id === 'revenue' || !(B0.get(id) > 0)) return;
      const v = G[id].at({ revenue: R, pretax: B0.get('pretax') });
      const r = v / B0.get(id);
      if (!(r >= 0.33 && r <= 3)) delete G[id];
    });
    const PJ = project(base, G, { full: o.full });
    if (!PJ) return { error: 'This chart has no revenue node to project.' };
    const { F, LV, guided } = PJ;
    const key = (l) => `${l.s}|${l.t}`;
    // fixed by guidance: guided nodes (a tax rate only once pre-tax earnings are fixed), lines into them, the remainder
    // of a fixed line whose other parts are fixed, and a line all of whose inflows are fixed
    const det = new Set(), dl = new Set();
    const fix = (withTax) => {
      Object.keys(guided).forEach((id) => { if (guided[id] && (id !== 'tax' || withTax)) det.add(id); });
      for (let grew = true; grew;) {
        grew = false;
        PJ.links.forEach((l) => {
          const k = key(l);
          if (dl.has(k)) return;
          const into = det.has(l.t) && guided[l.t] && PJ.ins.get(l.t).length === 1;
          const rest = det.has(l.s) && PJ.outs.get(l.s).every((x) => x === l || dl.has(key(x)));
          if (into || rest) { dl.add(k); grew = true; }
        });
        PJ.nodes.forEach((n) => {
          const ins = PJ.ins.get(n.id) || [];
          if (!det.has(n.id) && ins.length && ins.every((x) => dl.has(key(x)))) { det.add(n.id); grew = true; }
        });
      }
    };
    fix(false);
    if (guided.tax && det.has('pretax')) fix(true);
    const fm = fmtOf(R0);
    const ACT = new Map(spec.nodes.map((n) => [n.id, +n.v]));
    const better = (n) => (ROLE(n.color) === 'cost' ? 'lower' : 'higher');
    const pctTxt = (a, b) => (b > 0 && a >= 0 ? `${a >= b ? '+' : '−'}${Math.abs((a / b - 1) * 100).toFixed(1)}%` : 'n/m');
    const cmpLine = (n) => {
      const a = +n.v, gv = F[n.id], g1 = G[n.id] && guided[n.id] ? G[n.id] : null;
      if (!(gv > 0)) return null;
      const lo = g1 && g1.lo ? g1.lo(F) : null, hi = g1 && g1.hi ? g1.hi(F) : null;
      const it = g1 ? g1.it : null;
      let where = '';
      if (lo != null && hi != null && isFinite(lo) && isFinite(hi)) {
        const oc = outcome(a, { unit: 'usd', lo, hi, bound: it && it.unit === 'usd' ? it.bound : null });
        where = oc === 'above' ? 'above the range' : oc === 'below' ? 'below the range' : oc === 'met' ? 'met' : 'within the range';
      }
      const up = a > gv * 1.0005, dn = a < gv * 0.9995;
      const good = better(n) === 'higher' ? up : dn, bad = better(n) === 'higher' ? dn : up;
      // a cost guidance only implies (cost of revenue = guided revenue − guided gross profit) moves with the revenue it
      // serves: neither better nor worse in itself
      const st = where === 'within the range' || where === 'met' || (!good && !bad) || (!g1 && better(n) === 'lower') ? 'cnt' : good ? 'cup' : 'cdn';
      const what = g1 ? (it.unit === 'usd' ? `guided ${range(it)}` : `guided ${NAMES[it.metric] ? NAMES[it.metric].toLowerCase() + ' ' : ''}${range(it)} → ${fm.money(gv)}`) : `implied by guidance ${fm.money(gv)}`;
      return [st, enc(`◆ ${what} · ${pctTxt(a, gv)}${where ? ' · ' + where : ''}`)];
    };
    // the reported period must be built like the base where a comparison rests on it: a line that splits differently
    // now (other expense out of operating profit this quarter, not last) is not held to the projected split
    const sides = (ls) => { const o = new Map(), i = new Map(); ls.filter((l) => l.v > 0).forEach((l) => { (o.get(l.s) || o.set(l.s, new Set()).get(l.s)).add(l.t); (i.get(l.t) || i.set(l.t, new Set()).get(l.t)).add(l.s); }); return { o, i }; };
    const A = sides(spec.links), B = sides(PJ.links.map((l) => ({ s: l.s, t: l.t, v: LV.get(l) || l.v })));
    const same = (x, y) => (x ? x.size : 0) === (y ? y.size : 0) && [...(x || [])].every((v) => y && y.has(v));
    const sameOuts = (id) => same(A.o.get(id), B.o.get(id)), sameIns = (id) => same(A.i.get(id), B.i.get(id));
    [...dl].forEach((k) => { const [a, b] = k.split('|'); if (!sameOuts(a) || !sameIns(b)) dl.delete(k); });
    [...det].forEach((id) => { if (!(guided[id] && G[id]) && !sameIns(id)) det.delete(id); });
    const nodes = spec.nodes.map((n) => {
      if (!det.has(n.id) || !(F[n.id] > 0)) return n;
      const g1 = G[n.id] && guided[n.id] ? G[n.id] : null, out = Object.assign({}, n, { g: F[n.id], cmp_g: cmpLine(n) });
      if (g1 && g1.lo && g1.hi) {
        const lo = g1.lo(F), hi = g1.hi(F);
        if (isFinite(lo) && isFinite(hi) && hi > lo) out.grange = [lo, hi];
      }
      return out;
    });
    const LVk = new Map(PJ.links.map((l) => [key(l), LV.get(l)]));
    const links = spec.links.map((l) => (dl.has(key(l)) && LVk.get(key(l)) != null ? Object.assign({}, l, { g: LVk.get(key(l)) }) : l));
    const nC = nodes.filter((n) => n.g != null).length;
    if (!nC) return { error: 'None of this period’s lines can be compared with its guidance.' };
    const name = dec(o.name || '');
    const when = fdate(rel.filed);
    // the main results against the guide, in words
    const bullets = [];
    const N = new Map(nodes.map((n) => [n.id, n]));
    const say = (id, label) => {
      const n = N.get(id);
      if (!n || n.g == null) return;
      const g1 = G[id] && guided[id] ? G[id] : null;
      const rng = g1 && g1.it.unit === 'usd' ? ` (guided ${range(g1.it)})` : '';
      bullets.push(`${label} ${fm.money(+n.v)} vs ${fm.money(n.g)} ${g1 ? 'guided' : 'implied by guidance'}${rng}: ${fm.delta(+n.v - n.g)} (${pctTxt(+n.v, n.g)})${n.cmp_g && /range|met/.test(n.cmp_g[1]) ? ' — ' + /(above the range|below the range|within the range|met)/.exec(dec(n.cmp_g[1]))[1] : ''}.`);
    };
    say('revenue', 'Revenue');
    const gm = choose(items, 'gross_margin', tp, ['pct']);
    if (gm && ACT.get('gp') != null && ACT.get('revenue') > 0) {
      const a = ACT.get('gp') / ACT.get('revenue') * 100;
      bullets.push(`Gross margin ${a.toFixed(1)}% vs guided ${range(gm)}${gm.basis ? ` (${gm.basis})` : ''}: ${a - mid(gm) >= 0 ? '+' : '−'}${Math.abs(a - mid(gm)).toFixed(1)} pts vs the midpoint.`);
    } else say('gp', 'Gross profit');
    say('opex', 'Operating expenses');
    say('oi', 'Operating profit');
    say('net', 'Net earnings');
    const notDrawn = (rel.items || []).filter((it) => here(it.period, rel.filed) && it.lo != null && (it.basis === 'non-GAAP' || it.unit === 'ps'))
      .slice(0, 4).map((it) => `${it.basis === 'non-GAAP' ? 'adj. ' : ''}${NAMES[it.metric] || it.metric} ${range(it)}`);
    if (notDrawn.length) bullets.push(`Also guided, not drawn (no GAAP line to hold it to here): ${notDrawn.join('; ')}.`);
    return Object.assign({}, spec, {
      nodes, links,
      compare_g: {
        vs: `guidance (${when}${rel.src && rel.src !== '8-K' ? ', ' + rel.src : ''})`, release: rel.filed, url: rel.url || null, period: tp, src: rel.src || '8-K',
        heading: `${dec(spec.label)} vs guidance`,
        title: `${name ? name + ': ' : ''}${dec(spec.label)} vs guidance`,
        bullets: bullets.slice(0, 6),
        footer: `Compared with the guidance in the ${rel.src && rel.src !== '8-K' ? `${rel.src} (its MD&A outlook)` : 'earnings release'} of ${when} (the last guidance on file before ${dec(spec.label)} ended): ` +
          `band and bar = as reported; guidance is drawn on the top edge of each band (vs the previous quarter or a year earlier keep the bottom edge): above guidance, the band grows past the guided figure on its top edge — that growth in violet dots on a violet tint, the guided amount below it in the band's own colour; short of guidance, a dense-dot area with a dashed outline above the band (what was guided beyond what was reported); ` +
          `the bracket beside a bar spans the guided range. Lines compared: those the guidance fixes — guided GAAP or basis-free figures, and lines that follow from them alone ` +
          `(guided margins × guided revenue); every other line is drawn plain. ◆ teal = better than guided (higher revenue or profit, lower costs), orange = worse, grey = within the range.`,
      },
    });
  }

  // ---------- the record: every guided period against what the company then reported, and how each guide moved ----------
  // history: holders/<TICKER>.json → guidance_history {releases: [{filed, accession, url, label, tags, items}] newest first}
  // company: the site's company file (quarters, years, periods) — the reported figures, GAAP
  const HIGHER_IS_BETTER = { revenue: true, gross_profit: true, gross_margin: true, operating_income: true, operating_margin: true,
    net_income: true, other_income: true, opex: false, tax_rate: false };
  // other income is left out: its guidance usually excludes the gains and losses on investments the statements include
  const RECORD_METRICS = ['revenue', 'gross_margin', 'gross_profit', 'operating_margin', 'operating_income', 'opex', 'net_income', 'tax_rate'];
  function nodeV(spec, id) { const n = (spec.nodes || []).find((x) => x.id === id); return n ? +n.v : null; }
  // the reported value of a guided metric in a period (null when the chart has no such line)
  function reported(metric, spec) {
    const r = nodeV(spec, 'revenue');
    switch (metric) {
      case 'revenue': return r;
      case 'gross_profit': return nodeV(spec, 'gp');
      case 'gross_margin': { const gp = nodeV(spec, 'gp'); return gp != null && r > 0 ? gp / r * 100 : null; }
      case 'operating_income': return nodeV(spec, 'oi');
      case 'operating_margin': { const oi = nodeV(spec, 'oi'); return oi != null && r > 0 ? oi / r * 100 : null; }
      case 'opex': return nodeV(spec, 'opex');
      case 'net_income': return nodeV(spec, 'net');
      case 'tax_rate': { const tx = nodeV(spec, 'tax'), pt = nodeV(spec, 'pretax'); return tx != null && pt > 0 ? tx / pt * 100 : null; }
      case 'other_income': return nodeV(spec, 'nonop_in');
      default: return null;
    }
  }
  // the site's periods: [{kind 'q' | 'fy', q, fy, end, filed, label, spec}]
  function periodsOf(company) {
    const per = (company && company.periods) || {};
    const qi = new Map((per.q || []).map((x) => [x.end, x])), yi = new Map((per.fy || []).map((x) => [x.end, x]));
    return {
      q: ((company && company.quarters) || []).map((s) => Object.assign({ kind: 'q', spec: s, end: s.end, filed: s.filed, label: s.label }, qi.get(s.end) || {})),
      y: ((company && company.years) || []).map((s) => Object.assign({ kind: 'fy', spec: s, end: s.end, filed: s.filed, label: s.label }, yi.get(s.end) || {})),
      allq: per.q || [], ally: per.fy || [],
    };
  }
  const dayDiff = (a, b) => (Date.parse(a) - Date.parse(b)) / 864e5;
  // The site numbers fiscal years by the calendar year they end in; companies do not all: Home Depot's and Lowe's "fiscal
  // 2026" ends in early 2027 (the site's FY27), Johnson & Johnson's 2026 ends on January 3, 2027. The offset from a
  // release: the quarter it reports (its own words, guidance.py read → reported) is the site's last quarter ended before
  // it was filed. null when the release does not say or the quarters do not agree.
  function yearOffset(rel, P) {
    const rp = rel && rel.reported;
    if (!rp || !rp[0] || !rel.filed) return null;
    const last = P.allq.filter((x) => x.end && x.end < rel.filed && dayDiff(rel.filed, x.end) < 120).sort((a, b) => (a.end < b.end ? 1 : -1))[0];
    if (!last || !last.fy || (rp[1] && last.q && rp[1] !== last.q)) return null;
    return last.fy - rp[0];
  }
  // a guided period ("Q3 FY2027", "Q4 2025", "FY2026", "Q@2026-09-27") in the site's numbering: {kind, fy, q, end}
  // (end when the site knows the period, reported or not). Without the release's offset: a guide is about a period not
  // over when it was given, so a label whose period (in the site's numbering) ended over 75 days before is the next year's
  function resolve(period, filed, P, off) {
    const p = parsePeriod(period);
    if (!p) return null;
    const kind = p.q === null ? 'fy' : 'q', list = kind === 'fy' ? P.ally : P.allq;
    if (p.at) {
      const x = list.find((z) => z.end && Math.abs(dayDiff(z.end, p.at)) <= 12);
      if (x) return { kind, fy: x.fy, q: x.q || null, end: x.end };
      // a period not on the site yet ("the quarter ending December 27, 2026"): counted on from the last one it has
      const last = list.filter((z) => z.end && z.fy && (kind === 'fy' || z.q)).sort((a, b) => (a.end < b.end ? 1 : -1))[0];
      if (last && kind === 'q') {
        const n = Math.round(dayDiff(p.at, last.end) / 91.3);
        if (n > 0 && n <= 8) { let q = last.q + n, fy = last.fy; while (q > 4) { q -= 4; fy += 1; } return { kind, fy, q, end: p.at }; }
      }
      if (last && kind === 'fy') {
        const n = Math.round(dayDiff(p.at, last.end) / 365.25);
        if (n > 0 && n <= 3) return { kind, fy: last.fy + n, q: null, end: p.at };
      }
      return { kind, fy: null, q: null, end: p.at };
    }
    let fy = p.y + (off || 0);
    const find = (y) => list.find((z) => z.fy === y && (kind === 'fy' || z.q === p.q));
    if (off == null) {
      const same = find(fy);
      if (same && same.end && filed && dayDiff(filed, same.end) > 75) fy += 1;
    }
    const x = find(fy);
    return { kind, fy, q: kind === 'q' ? p.q : null, end: x ? x.end : null };
  }
  // … and the site's period with its figures (a spec), or null when the site has not reported it
  function siteFor(res, P) {
    if (!res) return null;
    if (res.fy == null) return (res.kind === 'fy' ? P.y : P.q).find((x) => x.end === res.end) || null;
    return (res.kind === 'fy' ? P.y : P.q).find((x) => x.fy === res.fy && (res.kind === 'fy' || x.q === res.q)) || null;
  }
  function periodFor(period, filed, P, off) {
    return siteFor(resolve(period, filed, P, off), P);
  }
  // a guided figure far from what the company reports is a misread (a segment's figure, a base year, a change read as a
  // level): [low, high] multiples of the reference allowed per metric
  const SCALE_OK = { revenue: [0.5, 2.0], gross_profit: [0.33, 3], operating_income: [0.2, 5], net_income: [0.2, 5], opex: [0.33, 3], other_income: [0.05, 20] };
  function plausible(metric, unit, v, ref) {
    if (unit === 'pct') return metric === 'tax_rate' ? v > -30 && v < 60 : v > -100 && v <= 100;
    if (unit !== 'usd' || !(ref > 0) || !SCALE_OK[metric]) return true;
    const r = Math.abs(v) / ref, [a, b] = SCALE_OK[metric];
    return r >= a && r <= b;
  }
  function cmpRange(cur, old) {
    const scale = Math.max(Math.abs(old.lo), Math.abs(old.hi), Math.abs(cur.lo), Math.abs(cur.hi), 1e-9), eps = scale * 0.002;
    const mid = (cur.lo + cur.hi) / 2, pmid = (old.lo + old.hi) / 2, w = cur.hi - cur.lo, pw = old.hi - old.lo;
    return { change: mid > pmid + eps ? 'raised' : mid < pmid - eps ? 'lowered' : 'reaffirmed', range: w < pw - eps ? 'narrowed' : w > pw + eps ? 'widened' : null };
  }
  function outcome(actual, it) {
    const tolU = it.unit === 'usd' ? Math.max(Math.abs(it.hi), Math.abs(it.lo)) * 0.001 : it.unit === 'ps' ? 0.005 : 0.05;
    if (it.bound === 'min') return actual >= it.lo - tolU ? 'met' : 'below';
    if (it.bound === 'max') return actual <= it.hi + tolU ? 'met' : 'above';
    let lo = it.lo, hi = it.hi;
    if (Math.abs(hi - lo) <= tolU) {               // a point guide ("approximately $9.2 billion"): within 1% (0.25 pts) is in line
      const band = it.unit === 'usd' ? Math.abs(lo) * 0.01 : 0.25;
      lo -= band; hi += band;
    }
    return actual > hi + tolU ? 'above' : actual < lo - tolU ? 'below' : 'within';
  }
  const okBasis = (it) => (it.metric === 'revenue' || it.metric === 'tax_rate' || it.metric === 'other_income') ? it.basis !== 'non-GAAP' : it.basis === 'GAAP';

  function record(history, company) {
    const rels = ((history && history.releases) || []).filter((r) => r && r.filed).slice().sort((a, b) => (a.filed < b.filed ? -1 : 1));
    if (!rels.length) return null;
    const P = periodsOf(company || {});
    // the latest figure the site has of a metric, a quarter's or a year's: what a guide with no result yet is checked against
    const latestOf = (metric, kind) => { const xs = (kind === 'fy' ? P.y : P.q).slice().sort((a, b) => (a.end < b.end ? 1 : -1)); for (const x of xs) { const v = reported(metric, x.spec); if (v != null) return Math.abs(v); } return null; };
    // every guide of a metric (basis, unit) for a period of the site, oldest first; each release's periods read in the
    // site's numbering (yearOffset), so "fiscal 2026" of a company that names years by their start lands on the site's FY27
    const series = new Map();
    let dropped = 0;
    rels.forEach((r) => {
      const off = yearOffset(r, P);
      (r.items || []).forEach((it, i, all) => {
        if (it.lo == null || !it.period || it.period === 'long-term' || it.scope || !['usd', 'pct', 'ps'].includes(it.unit)) return;
        // a rate or cost with no basis next to the same metric with one ("in the mid-70s" beside the GAAP and
        // non-GAAP margins): a remark, not a guide of its own
        if (!it.basis && it.metric !== 'revenue' && all.some((x) => x.metric === it.metric && x.basis)) return;
        const res = resolve(it.period, r.filed, P, off);
        if (!res) return;
        const pk = res.fy != null ? `${res.kind}:${res.fy}:${res.q || ''}` : `${res.kind}@${res.end}`;
        const k = [it.metric, it.basis || '', it.unit, pk].join('|');
        if (!series.has(k)) series.set(k, { metric: it.metric, basis: it.basis || '', unit: it.unit, period: it.period, res, guides: [] });
        const sr = series.get(k);
        if (sr.guides.some((x) => x.filed === r.filed)) return;
        sr.guides.push({ filed: r.filed, url: r.url, lo: it.lo, hi: it.hi, approx: it.approx, bound: it.bound, said: it.said, src: r.src });
      });
    });
    const rows = [];
    series.forEach((sr) => {
      const per = siteFor(sr.res, P);
      // a figure for a period already reported is a result quoted in a later release, not guidance; so is one given
      // after the period ended (the site knows every period's end, also of quarters whose figures it no longer keeps)
      if (per && per.filed) sr.guides = sr.guides.filter((x) => x.filed < per.filed);
      if (sr.res.end) sr.guides = sr.guides.filter((x) => x.filed <= sr.res.end);
      // and a figure far from what the company reports (for that period, else its latest) is a misread: left out
      const actual0 = per ? reported(sr.metric, per.spec) : null;
      const ref = actual0 != null ? Math.abs(actual0) : latestOf(sr.metric, sr.res.kind);
      const n0 = sr.guides.length;
      sr.guides = sr.guides.filter((x) => plausible(sr.metric, sr.unit, (x.lo + x.hi) / 2, ref));
      dropped += n0 - sr.guides.length;
      if (!sr.guides.length) return;
      sr.guides.forEach((gd, i) => {
        if (i) Object.assign(gd, cmpRange(gd, sr.guides[i - 1]));
        else gd.change = gd.said === 'initiated' ? 'initiated' : 'first';
      });
      sr.first = sr.guides[0];
      if (per) {
        // the guides given before the figures were reported; the last of them is the one the result is held to
        const before = sr.guides.filter((x) => !per.filed || x.filed < per.filed);
        if (before.length && okBasis(sr) && RECORD_METRICS.includes(sr.metric)) {
          const actual = reported(sr.metric, per.spec);
          if (actual != null) {
            const last = before[before.length - 1], mid = (last.lo + last.hi) / 2;
            Object.assign(sr, { site: per, actual, final: last, outcome: outcome(actual, Object.assign({ unit: sr.unit }, last)),
              vsMid: sr.unit === 'pct' ? actual - mid : mid ? (actual / mid - 1) * 100 : null,
              vsFirst: before.length > 1 ? outcome(actual, Object.assign({ unit: sr.unit }, before[0])) : null });
          }
        }
      }
      rows.push(sr);
    });
    // per metric: the hit rate on the periods with a reported figure, and the moves of the guides revised in between
    const byMetric = new Map();
    rows.forEach((sr) => {
      const k = `${sr.metric}|${sr.basis}|${sr.unit}`;
      if (!byMetric.has(k)) byMetric.set(k, { metric: sr.metric, basis: sr.basis, unit: sr.unit, rows: [] });
      byMetric.get(k).rows.push(sr);
    });
    const metrics = [...byMetric.values()].map((m) => {
      m.rows.sort((a, b) => ((a.site && a.site.end) || a.first.filed) < ((b.site && b.site.end) || b.first.filed) ? 1 : -1);
      const done = m.rows.filter((x) => x.outcome);
      const count = (o) => done.filter((x) => x.outcome === o).length;
      const better = HIGHER_IS_BETTER[m.metric] !== false;
      m.hits = { n: done.length, above: count('above'), within: count('within'), below: count('below'), met: count('met'),
        better: better ? 'higher' : 'lower' };
      m.hits.hitOrBeat = m.hits.within + m.hits.met + (better ? m.hits.above : m.hits.below);
      const mids = done.map((x) => x.vsMid).filter((x) => x != null && isFinite(x));
      m.hits.avgVsMid = mids.length ? mids.reduce((a, b) => a + b, 0) / mids.length : null;
      const moves = { raised: 0, lowered: 0, reaffirmed: 0, narrowed: 0, widened: 0 };
      m.rows.forEach((sr) => sr.guides.slice(1).forEach((gd) => { moves[gd.change] = (moves[gd.change] || 0) + 1; if (gd.range) moves[gd.range] += 1; }));
      m.moves = moves;
      m.name = `${m.basis === 'non-GAAP' ? 'Adjusted ' : m.basis === 'GAAP' && m.metric !== 'revenue' ? 'GAAP ' : ''}${(NAMES[m.metric] || m.metric).replace(/^./, (c) => (m.basis ? c.toLowerCase() : c))}`;
      m.name = m.name.replace(/^(GAAP|Adjusted) (.)/, (x, a, b) => `${a} ${b.toLowerCase()}`).replace(/^./, (c) => c.toUpperCase());
      return m;
    }).filter((m) => m.rows.length);
    const order = (m) => [RECORD_METRICS.indexOf(m.metric) < 0 ? 99 : RECORD_METRICS.indexOf(m.metric), m.basis === 'non-GAAP' ? 1 : 0, -m.hits.n];
    metrics.sort((a, b) => { const x = order(a), y = order(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]; });
    // the releases' own words over time ("raised", "lowered" …) — the other half of the record of moves
    const said = { raised: 0, lowered: 0, narrowed: 0, widened: 0, reaffirmed: 0, initiated: 0, withdrawn: 0 };
    rels.forEach((r) => (r.tags || []).forEach((t) => { if (t in said) said[t] += 1; }));
    // a period not on the site: still to be reported when it was guided after the latest figures on file; otherwise it
    // is older than the quarters the site keeps (left out of the table unless its guide moved)
    const lastFiled = [...P.q, ...P.y].map((x) => x.filed || '').sort().pop() || '';
    const lastQ = P.q.filter((x) => x.q && x.fy).sort((a, b) => (a.end < b.end ? 1 : -1))[0];
    const fiscalStyle = P.q.some((x) => /FY\d{2}$/.test(x.label || ''));
    const later = (res) => {                        // a period after the latest one on the site (in the site's numbering)
      if (!res || !lastQ || res.fy == null) return res && res.end && lastQ ? res.end > lastQ.end : null;
      return res.kind === 'fy' ? res.fy > lastQ.fy || (res.fy === lastQ.fy && lastQ.q < 4) : res.fy > lastQ.fy || (res.fy === lastQ.fy && res.q > lastQ.q);
    };
    // the label in the site's own words, so a guided year shows as the site names it (Home Depot's fiscal 2026: FY27)
    const siteLabel = (res, fallback) => {
      if (!res || res.fy == null) return fallback;
      const yy = String(res.fy).slice(-2);
      return res.kind === 'fy' ? (fiscalStyle ? `FY${yy}` : `FY${res.fy}`) : (fiscalStyle ? `Q${res.q} FY${yy}` : `Q${res.q} ${res.fy}`);
    };
    metrics.forEach((m) => m.rows.forEach((r) => {
      if (!r.site) {
        const l = later(r.res);
        r.pending = l === null ? (r.guides[r.guides.length - 1].filed || '') >= lastFiled : l;
      }
      r.label = r.site ? r.site.label : siteLabel(r.res, r.period);
    }));
    return { metrics, releases: rels.length, since: rels[0].filed, latest: rels[rels.length - 1].filed, said, dropped, complete: !!(history && history.complete) };
  }

  const OUT = { above: 'above the range', within: 'within the range', below: 'below the range', met: 'met' };
  function fmtVal(v, unit, fm) {
    if (v == null) return '—';
    if (unit === 'usd') return fm ? fm(v) : money(v);
    if (unit === 'ps') return `$${v.toFixed(2)}`;
    return `${(+v).toFixed(1)}%`;
  }
  function guideText(gd, unit) {
    return range(Object.assign({ unit }, gd));
  }
  // the one-line summary of a metric's record: "Revenue: in or above the guided range 8 of 8 quarters (5 above, 3 within) · avg +3.1% vs midpoint"
  function summaryLine(m) {
    const h = m.hits;
    if (!h.n) return '';
    const good = h.better === 'higher' ? 'in or above' : 'in or below';
    const parts = [];
    if (h.above) parts.push(`${h.above} above`);
    if (h.within) parts.push(`${h.within} within`);
    if (h.below) parts.push(`${h.below} below`);
    if (h.met) parts.push(`${h.met} met`);
    const avg = h.avgVsMid == null ? '' : m.unit === 'pct' ? ` · on average ${h.avgVsMid >= 0 ? '+' : '−'}${Math.abs(h.avgVsMid).toFixed(1)} pts vs the midpoint`
      : ` · on average ${h.avgVsMid >= 0 ? '+' : '−'}${Math.abs(h.avgVsMid).toFixed(1)}% vs the midpoint`;
    return `${m.name}: ${good} the guided range ${h.hitOrBeat} of ${h.n} period${h.n === 1 ? '' : 's'} (${parts.join(', ')})${avg}`;
  }
  function movesLine(m) {
    const mv = m.moves, parts = [];
    if (mv.raised) parts.push(`▲ raised ${mv.raised}×`);
    if (mv.lowered) parts.push(`▼ lowered ${mv.lowered}×`);
    if (mv.reaffirmed) parts.push(`= reaffirmed ${mv.reaffirmed}×`);
    if (mv.narrowed) parts.push(`→← narrowed ${mv.narrowed}×`);
    if (mv.widened) parts.push(`←→ widened ${mv.widened}×`);
    return parts.join(' · ');
  }

  // the record as HTML: per metric a summary, a strip of dots (each period's result against its guided range, drawn as
  // % from the guided midpoint) and the table of guides, moves and results
  // ---------- the record drawn: how each guided period's range moved, and where the results landed ----------
  // The guide path: per metric, each period (oldest left) as a group of bars — one per release that guided it, oldest
  // first — and the reported figure as a dot; all on one scale, % (points for a rate) from the last guide's midpoint, so
  // periods of different size line up. Raised guides step up, cuts step down, a narrowing range shortens the bars.
  function pathHTML(rec, esc) {
    const e = esc || enc;
    if (!rec || !rec.metrics) return '';
    const COLR = { above: '#0b7a75', within: '#3a2a8c', below: '#d9480f', met: '#0b7a75' };
    const charts = rec.metrics.filter((m) => m.rows.some((r) => r.guides.length > 1 || r.outcome)).slice(0, 3).map((m) => {
      const rows = m.rows.filter((r) => r.guides.length > 1 || r.outcome).slice(0, 8).reverse();
      if (!rows.length) return '';
      const ref = (r) => { const g = r.guides[r.guides.length - 1]; return (g.lo + g.hi) / 2; };
      const rel = (v, r) => (m.unit === 'pct' ? v - ref(r) : ref(r) ? (v / ref(r) - 1) * 100 : 0);
      const vals = [];
      rows.forEach((r) => { r.guides.forEach((g) => vals.push(rel(g.lo, r), rel(g.hi, r))); if (r.actual != null) vals.push(rel(r.actual, r)); });
      const sorted = vals.map(Math.abs).sort((a, b) => a - b);
      const span = Math.max(m.unit === 'pct' ? 0.5 : 1, sorted[Math.floor((sorted.length - 1) * 0.9)] * 1.2);   // an outlier stays at the edge
      const W = 640, H = 230, x0 = 56, x1 = W - 10, y0 = 14, y1 = H - 40, gw = (x1 - x0) / rows.length;
      const Y = (v) => y0 + (span - Math.max(-span, Math.min(span, v))) / (2 * span) * (y1 - y0);
      const u = m.unit === 'pct' ? ' pts' : '%';
      let svg = `<svg class="gr-path" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(m.name)}: how each period's guidance moved and what was reported">`;
      [span, span / 2, 0, -span / 2, -span].forEach((t) => {
        svg += `<line x1="${x0}" x2="${x1}" y1="${Y(t).toFixed(1)}" y2="${Y(t).toFixed(1)}" stroke="${t === 0 ? '#8c8a84' : '#e4e2dc'}"${t === 0 ? ' stroke-dasharray="3 3"' : ''}/>` +
          `<text x="${x0 - 6}" y="${(Y(t) + 4).toFixed(1)}" text-anchor="end" class="gr-ax">${t > 0 ? '+' : t < 0 ? '−' : ''}${Math.abs(t).toFixed(span < 3 ? 1 : 0)}${u}</text>`;
      });
      rows.forEach((r, i) => {
        const gx = x0 + i * gw, n = r.guides.length + 1, slot = Math.min(22, (gw - 12) / n), start = gx + (gw - slot * n) / 2;
        const mids = [];
        r.guides.forEach((g, j) => {
          const cx = start + (j + 0.5) * slot, top = Y(rel(g.hi, r)), bot = Y(rel(g.lo, r)), point = Math.abs(g.hi - g.lo) < 1e-9 * Math.max(1, Math.abs(g.hi));
          const op = (0.45 + 0.55 * (j + 1) / r.guides.length).toFixed(2);
          svg += `<rect x="${(cx - 4).toFixed(1)}" y="${Math.min(top, bot - (point ? 3 : 0)).toFixed(1)}" width="8" height="${Math.max(point ? 6 : 2, bot - top).toFixed(1)}" rx="2" fill="#5b3fc4" fill-opacity="${op}"${point ? ' stroke="#5b3fc4" stroke-dasharray="2 1.5"' : ''}>` +
            `<title>${e(`${r.label}: guided ${guideText(g, m.unit)} on ${fdate(g.filed)}${j ? ` (${WORD[g.change] || g.change}${g.range ? ', ' + WORD[g.range] : ''})` : ''}`)}</title></rect>`;
          mids.push([cx, Y(rel((g.lo + g.hi) / 2, r))]);
        });
        if (mids.length > 1) svg += `<polyline points="${mids.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ')}" fill="none" stroke="#5b3fc4" stroke-width="1.4"/>`;
        if (r.actual != null && r.outcome) {
          const ax = start + (n - 0.5) * slot, ay = Y(rel(r.actual, r)), col = COLR[r.outcome] || '#6b6a80';
          const last = mids[mids.length - 1];
          svg += `<line x1="${last[0].toFixed(1)}" y1="${last[1].toFixed(1)}" x2="${ax.toFixed(1)}" y2="${ay.toFixed(1)}" stroke="${col}" stroke-dasharray="3 2" stroke-width="1.2"/>` +
            `<circle cx="${ax.toFixed(1)}" cy="${ay.toFixed(1)}" r="5" fill="${col}"><title>${e(`${r.label}: reported ${fmtVal(r.actual, m.unit)} — ${OUT[r.outcome]}`)}</title></circle>`;
        } else if (r.pending) {
          svg += `<text x="${(start + (n - 0.5) * slot).toFixed(1)}" y="${(Y(0) + 4).toFixed(1)}" text-anchor="middle" class="gr-ax">?</text>`;
        }
        svg += `<text x="${(gx + gw / 2).toFixed(1)}" y="${H - 22}" text-anchor="middle" class="gr-lab">${e(r.label)}</text>` +
          `<text x="${(gx + gw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" class="gr-ax">${r.guides.length} guide${r.guides.length === 1 ? '' : 's'}</text>`;
      });
      svg += '</svg>';
      return `<div class="gr-pathbox"><h4>${e(m.name)}: how the guidance moved</h4>${svg}</div>`;
    }).filter(Boolean);
    if (!charts.length) return '';
    return `<div class="gr-paths">${charts.join('')}<p class="muted">Each bar is one release’s guided range for that period, oldest left (paler = earlier), on one scale: % from the last guide’s midpoint (points for a rate). The line follows the midpoint; the dot is what was reported — teal above the range, violet within, orange below; ? = not reported yet.</p></div>`;
  }

  // Where the results landed in the guided ranges, every metric and period together, oriented so that right is better
  // (above the range for revenue and profit, below it for costs and the tax rate): a company that lands in the better
  // third or beyond most of the time guides conservatively.
  // [worse than the range, worse third, middle third, better third, better than the range]: every figure held to a result
  function landingBins(rec) {
    const bins = [0, 0, 0, 0, 0];
    if (!rec || !rec.metrics) return bins;
    rec.metrics.forEach((m) => m.rows.forEach((r) => {
      if (!r.outcome || !r.final || r.actual == null) return;
      const g = r.final, better = HIGHER_IS_BETTER[m.metric] !== false;
      let lo = g.lo, hi = g.hi;
      if (Math.abs(hi - lo) < 1e-9 * Math.max(1, Math.abs(hi))) { const band = m.unit === 'usd' ? Math.abs(lo) * 0.01 : m.unit === 'ps' ? 0.01 : 0.25; lo -= band; hi += band; }
      let k = r.actual > hi ? 4 : r.actual < lo ? 0 : (r.actual - lo) / (hi - lo) < 1 / 3 ? 1 : (r.actual - lo) / (hi - lo) > 2 / 3 ? 3 : 2;
      if (!better) k = 4 - k;
      bins[k] += 1;
    }));
    return bins;
  }
  function landingHTML(rec, esc) {
    const e = esc || enc;
    if (!rec || !rec.metrics) return '';
    const bins = landingBins(rec);
    const n = bins.reduce((a, b) => a + b, 0);
    if (n < 2) return '';
    const names = ['Worse than the range', 'Worse third', 'Middle third', 'Better third', 'Better than the range'];
    const cols = ['#d9480f', '#e8a17a', '#8f84c9', '#6fb8a8', '#0b7a75'];
    const max = Math.max(...bins), W = 640, H = 150, bw = (W - 40) / 5;
    let svg = `<svg class="gr-land" viewBox="0 0 ${W} ${H}" role="img" aria-label="Where the reported figures landed in the guided ranges">`;
    bins.forEach((v, i) => {
      const h = max ? v / max * (H - 56) : 0, x = 20 + i * bw;
      svg += `<rect x="${(x + 10).toFixed(1)}" y="${(H - 40 - h).toFixed(1)}" width="${(bw - 20).toFixed(1)}" height="${Math.max(h, v ? 2 : 0).toFixed(1)}" rx="3" fill="${cols[i]}"/>` +
        `<text x="${(x + bw / 2).toFixed(1)}" y="${(H - 46 - h).toFixed(1)}" text-anchor="middle" class="gr-lab">${v}</text>` +
        `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 22}" text-anchor="middle" class="gr-ax">${names[i]}</text>`;
    });
    svg += '</svg>';
    const good = bins[3] + bins[4], bad = bins[0] + bins[1];
    const verdict = good / n >= 0.6 ? `lands in the better third or beyond ${good} of ${n} times: it guides conservatively`
      : bad / n >= 0.5 ? `lands in the worse third or beyond ${bad} of ${n} times: its guidance tends to be optimistic`
        : `lands around the middle of its ranges (${bins[2]} of ${n} in the middle third)`;
    return `<div class="gr-landbox"><h4>Where the results landed</h4>${svg}<p class="muted">Every guided figure held to a reported one (${n}), in thirds of its range; right is better — above the range for revenue and profit, below it for costs and tax. The company ${e(verdict)}.</p></div>`;
  }

  function recordHTML(rec, esc, opts) {
    const e = esc || enc, o = opts || {};
    if (!rec || !rec.metrics.length) return '';
    const fm = o.money || money;
    const COL = { above: '#0b7a75', within: '#3a2a8c', below: '#d9480f', met: '#0b7a75' };
    const keepRow = (r) => r.outcome || r.pending || r.guides.length > 1;
    const show = rec.metrics.filter((m) => m.hits.n || m.rows.some((r) => r.guides.length > 1)).slice(0, o.max || 6);
    const dev = (m, v, mid) => (m.unit === 'pct' ? v - mid : mid ? (v / mid - 1) * 100 : 0);
    // each reported period as a dot against its guided range, all on one scale: % (points for a rate) from the midpoint
    const strip = (m) => {
      const done = m.rows.filter((r) => r.outcome && r.vsMid != null).slice(0, 10).reverse();
      if (!done.length) return '';
      const halfs = done.map((r) => {
        const g = r.final, mid = (g.lo + g.hi) / 2, point = Math.abs(g.hi - g.lo) < 1e-9 * Math.max(1, Math.abs(g.hi));
        return point ? (m.unit === 'pct' ? 0.25 : 1) : Math.abs(dev(m, g.hi, mid));
      });
      const devs = done.map((r) => Math.abs(r.vsMid)).sort((a, b) => a - b);
      const typical = devs[Math.floor((devs.length - 1) * 0.8)];      // an outlier does not squeeze the others
      const span = Math.max(1, ...halfs.map((h) => h * 1.6), typical * 1.25);
      const W = 600, rowH = 24, H = done.length * rowH + 30, x0 = 92, x1 = W - 54;
      const X = (v) => x0 + (Math.max(-span, Math.min(span, v)) + span) / (2 * span) * (x1 - x0);
      const u = m.unit === 'pct' ? ' pts' : '%';
      let svg = `<svg class="gr-strip" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(m.name)}: what was reported against the guided range, period by period">`;
      svg += `<line x1="${X(0).toFixed(1)}" x2="${X(0).toFixed(1)}" y1="2" y2="${H - 24}" stroke="#8c8a84" stroke-dasharray="3 3"/>`;
      svg += `<text x="${X(0).toFixed(1)}" y="${H - 8}" text-anchor="middle" class="gr-ax">guided midpoint</text>`;
      svg += `<text x="${x0}" y="${H - 8}" class="gr-ax">−${span.toFixed(1)}${u}</text><text x="${x1}" y="${H - 8}" text-anchor="end" class="gr-ax">+${span.toFixed(1)}${u}</text>`;
      done.forEach((r, i) => {
        const y = 4 + i * rowH, g = r.final, mid = (g.lo + g.hi) / 2;
        const point = Math.abs(g.hi - g.lo) < 1e-9 * Math.max(1, Math.abs(g.hi));
        const lo = point ? -(m.unit === 'pct' ? 0.25 : 1) : dev(m, g.lo, mid), hi = point ? (m.unit === 'pct' ? 0.25 : 1) : dev(m, g.hi, mid);
        svg += `<text x="0" y="${y + 14}" class="gr-lab">${e(r.label)}</text>`;
        svg += `<rect x="${X(lo).toFixed(1)}" y="${y + 3}" width="${Math.max(2, X(hi) - X(lo)).toFixed(1)}" height="14" rx="3" fill="#e4dff7" stroke="#8f84c9"${point ? ' stroke-dasharray="3 2"' : ''}/>`;
        const out = Math.abs(r.vsMid) > span, cx = X(r.vsMid), col = COL[r.outcome] || '#6b6a80';
        svg += `<circle cx="${cx.toFixed(1)}" cy="${y + 10}" r="5.5" fill="${col}"><title>${e(`${r.label}: reported ${fmtVal(r.actual, m.unit, fm)} vs guided ${guideText(r.final, m.unit)} — ${OUT[r.outcome]}`)}</title></circle>`;
        // beyond the scale: the dot stays at the edge, its value written beside it inside the plot
        if (out) svg += `<text x="${(r.vsMid > 0 ? cx - 9 : cx + 9).toFixed(1)}" y="${y + 14}" text-anchor="${r.vsMid > 0 ? 'end' : 'start'}" class="gr-ax gr-out-lab" fill="${col}">${r.vsMid > 0 ? '+' : '−'}${Math.abs(r.vsMid).toFixed(1)}${u}</text>`;
      });
      return svg + '</svg>';
    };
    const chips = (m) => {
      const h = m.hits;
      if (!h.n) return '<p class="muted">No reported figure to hold it to (adjusted figures are not in the GAAP statements); its moves between releases are below.</p>';
      const pct = Math.round(h.hitOrBeat / h.n * 100);
      const avg = h.avgVsMid == null ? '' : `<span class="gr-chip">avg ${h.avgVsMid >= 0 ? '+' : '−'}${Math.abs(h.avgVsMid).toFixed(1)}${m.unit === 'pct' ? ' pts' : '%'} vs midpoint</span>`;
      return `<p class="gr-chips"><span class="gr-chip good"><b>${h.better === 'higher' ? 'Met or beat' : 'Met or came in lower'} ${h.hitOrBeat} of ${h.n}</b> (${pct}%)</span>` +
        `<span class="gr-chip within">● inside the range ${h.within + h.met}</span><span class="gr-chip above">● above ${h.above}</span><span class="gr-chip below">● below ${h.below}</span>${avg}</p>`;
    };
    const table = (m) => {
      const rows = m.rows.filter(keepRow).slice(0, 10).map((r) => {
        const moves = r.guides.map((gd, i) => `<span class="gr-move ${i ? gd.change : 'first'}">${i ? e((WORD[gd.change] || gd.change) + (gd.range ? ' ' + WORD[gd.range] : '')) + ' ' : ''}${e(guideText(gd, m.unit))} <span class="muted">${e(fdate(gd.filed))}</span></span>`).join('<span class="gr-arrow">→</span>');
        const res = r.outcome ? `<span class="gr-out ${r.outcome}">● ${e(OUT[r.outcome])}</span>${r.vsFirst && r.vsFirst !== r.outcome ? `<br><span class="muted">vs the first guide: ${e(OUT[r.vsFirst])}</span>` : ''}`
          : r.pending ? '<span class="muted">to be reported</span>' : '<span class="muted">before the periods on this site</span>';
        const vm = r.vsMid == null ? '' : m.unit === 'pct' ? `${r.vsMid >= 0 ? '+' : '−'}${Math.abs(r.vsMid).toFixed(1)} pts` : `${r.vsMid >= 0 ? '+' : '−'}${Math.abs(r.vsMid).toFixed(1)}%`;
        return `<tr><td>${e(r.label)}</td><td class="gr-moves">${moves}</td><td class="num">${r.actual != null ? e(fmtVal(r.actual, m.unit, fm)) : '—'}</td><td>${res}</td><td class="num">${e(vm)}</td></tr>`;
      }).join('');
      return rows ? `<div class="table-wrap"><table class="gr-table"><thead><tr><th>Period</th><th>Guided, and how it moved (release dates)</th><th class="num">Reported</th><th>Result</th><th class="num">vs midpoint</th></tr></thead><tbody>${rows}</tbody></table></div>` : '';
    };
    const sd = rec.said, words = Object.keys(sd).filter((k) => sd[k]).map((k) => `${WORD[k] || k} ${sd[k]}×`).join(' · ');
    return `<div class="gr-head"><h3>Guidance record</h3><span class="muted">${rec.releases} earnings release${rec.releases === 1 ? '' : 's'} with guidance since ${e(fdate(rec.since))}${rec.complete ? '' : ' (earlier releases are still being read)'}${words ? ` · what the releases said: ${e(words)}` : ''}</span></div>` +
      // the first metric open, the others one click away (their summary stays in view)
      show.map((m, i) => `<details class="gr-metric"${i === 0 ? ' open' : ''}><summary><h4>${e(m.name)}</h4>${chips(m)}</summary>
        ${movesLine(m) ? `<p class="gr-moves-sum">Moves between releases: ${e(movesLine(m))}</p>` : ''}
        ${strip(m)}${table(m)}</details>`).join('') +
      `<p class="muted gr-note">Each guided period is held to the last guidance given before its figures were reported; a single figure ("approximately") counts as in line within 1% (0.25 pts for a rate), drawn as a dashed box. Reported figures are GAAP, from the company's 10-Q / 10-K or earnings release on this site; adjusted (non-GAAP) guidance shows its moves only. ● teal = above, ● indigo = inside, ● orange = below the range.</p>`;
  }

  // the notes panel of a node in the guidance view (HTML)
  const NODE_METRIC = { revenue: ['revenue'], gp: ['gross_margin', 'gross_profit'], opex: ['opex'], oi: ['operating_margin', 'operating_income'],
    net: ['net_income'], tax: ['tax_rate'] };
  function noteHTML(n, g, esc, rec) {
    const e = esc || enc;
    const note = n.gnote || {};
    const mine = rec && (NODE_METRIC[n.id] || []).map((k) => rec.metrics.find((m) => m.metric === k && m.basis !== 'non-GAAP' && m.hits.n)).find(Boolean);
    const track = mine ? `<p class="gr-note-line"><b>Track record:</b> ${e(summaryLine(mine).replace(mine.name + ': ', ''))}${movesLine(mine) ? ` · ${e(movesLine(mine))}` : ''}</p>` : '';
    if (note.guided) {
      const it = note.item;
      const w = words(it);
      return track + `<p><b>Guided:</b> ${e(range(it))}${it.basis ? ` (${e(it.basis)})` : ''}${it.period ? ` for ${e(it.period)}` : ''}${w.length ? ` · ${e(w.join(' · '))}` : ''}</p>` +
        (it.prior ? `<p class="muted">${e(priorText(it))}</p>` : '') +
        (it.quote ? `<blockquote><p>${e(it.quote)}</p></blockquote>` : '') +
        `<div class="src">From the earnings release${g && g.filed ? ` filed ${e(fdate(g.filed))}` : ''}${g && g.url ? ` · <a href="${e(g.url)}" target="_blank" rel="noopener">open filing ↗</a>` : ''}</div>`;
    }
    return track + '<p class="empty">Not guided: the line keeps its share of its parent from the period on file, so the chart adds up. It is an assumption, not a figure the company gave.</p>';
  }

  const api = { future, versus, sources, resolve, yearOffset, plausible, pathHTML, landingHTML, landingBins, target, usable, words, range, priorText, noteHTML, record, recordHTML, summaryLine, movesLine, outcome, WORD, NAMES, money };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.FFGuidance = api;
})(typeof window !== 'undefined' ? window : globalThis);
