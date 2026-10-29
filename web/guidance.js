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
   Colours: violet / indigo / plum (guided) and their pale tints (assumed) — neither the current chart's grey, green
   and red nor the comparison view's dark strips and hatching. Non-GAAP figures (adjusted EPS, EBITDA …) are listed
   in the footer, never drawn into GAAP flows. No dependencies; works in the browser and in node (tests). */
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
  function guides(items, period, implied) {
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
    return G;
  }

  function project(base, G) {
    const all = new Map(base.nodes.map((n) => [n.id, n]));
    const rev = all.get('revenue');
    if (!rev || !G.revenue) return null;
    const net = all.get('net');
    const cut = net ? net.col : Infinity;
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
    return { F, LV, guided, nodes, links, byId, ins, notes, f };
  }

  // the base line's "· 25% of revenue" wording, recomputed
  function shareText(n, F, P) {
    const line = (n.lines || [])[1];
    const m = line && /·\s*[\d.,]+%\s+of\s+(.+)$/.exec(dec(line[1]));
    const parents = P.ins.get(n.id);
    if (!m || parents.length !== 1) return '';
    const pv = F[parents[0].s];
    return pv > 0 ? ` · ${(F[n.id] / pv * 100).toFixed(F[n.id] / pv >= 0.1 ? 0 : 1)}% of ${m[1]}` : '';
  }
  function baseShare(n, P) {
    const parents = P.ins.get(n.id);
    if (parents.length !== 1) return '';
    const p = P.byId.get(parents[0].s);
    return p && p.v > 0 ? `${(n.v / p.v * 100).toFixed(n.v / p.v >= 0.1 ? 0 : 1)}% of ${dec(p.name).toLowerCase()}` : '';
  }

  function future(base, g, opts) {
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
    const G = guides(items, tg.period, implied);
    // a guided revenue far from the base period is a misread (or a different scope): not drawn
    const R = G.revenue && G.revenue.at({});
    if (!(R > 0) || R < base.nodes.find((n) => n.id === 'revenue').v * 0.4 || R > base.nodes.find((n) => n.id === 'revenue').v * 2.5) {
      return { error: 'The guided revenue does not match the scale of the reported revenue; not drawn.' };
    }
    const P = project(base, G);
    if (!P) return { error: 'This chart has no revenue node to project.' };
    const { F, LV, guided } = P;
    const per = tg.label.replace(/^FY(\d{4})$/, 'FY$1');
    const nodes = [];
    P.nodes.forEach((n) => {
      const v = F[n.id];
      if (!(v > 0)) return;
      const g1 = G[n.id] && guided[n.id] ? G[n.id] : null;
      const role = ROLE(n.color);
      const lines = [[(n.lines && n.lines[0] && n.lines[0][0]) || 'name', n.name], ['val', enc(money(v)) + enc(shareText(n, F, P))]];
      let note;
      if (g1) {
        const it = g1.it, w = words(it);
        const shown = it.unit === 'usd' ? range(Object.assign({}, it, implied ? { lo: g1.lo(F), hi: g1.hi(F) } : {})) : range(it);
        lines.push([it.change === 'lowered' || it.change === 'withdrawn' ? 'gdn' : it.change === 'raised' ? 'gup' : 'gnt',
          enc(`guided ${it.unit !== 'usd' ? `${NAMES[it.metric] ? NAMES[it.metric].toLowerCase() + ' ' : ''}` : ''}${shown}${w.length ? ' · ' + w.join(' · ') : ''}`)]);
        if (it.prior) lines.push(['gas', enc(priorText(it))]);
        if (n.v > 0 && !implied) {
          const d = (v / n.v - 1) * 100;
          lines.push(['gas', enc(`${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(Math.abs(d) < 10 ? 1 : 0)}% vs ${dec(base.label)} reported`)]);
        }
        note = { guided: true, item: it };
      } else {
        lines.push(['gas', enc(n.col < (P.byId.get('revenue') || {}).col ? `assumed: same mix as ${dec(base.label)}` : (baseShare(n, P) ? `assumed: ${baseShare(n, P)} in ${dec(base.label)}` : P.ins.get(n.id).length ? 'the sum of the lines into it' : `assumed: as in ${dec(base.label)}`))]);
        note = { guided: false };
      }
      const out = Object.assign({}, n, { v, color: (g1 ? 'f_' : 'fa_') + role, lines, gnote: note, notes: undefined, cmp: undefined, cmp_y: undefined });
      if (g1 && g1.lo && g1.hi) {
        const lo = g1.lo(F), hi = g1.hi(F);
        if (isFinite(lo) && isFinite(hi) && hi > lo) out.range = [lo, hi];
      }
      nodes.push(out);
    });
    const keep = new Set(nodes.map((n) => n.id));
    const links = P.links.filter((l) => keep.has(l.s) && keep.has(l.t) && LV.get(l) > 0)
      .map((l) => ({ s: l.s, t: l.t, v: LV.get(l), color: (guided[l.t] ? 'f_' : 'fa_') + ROLE(l.color) }));
    const nGuided = nodes.filter((n) => n.gnote.guided).length;
    const company = dec(o.name || '');
    // everything the release guided, drawn or not
    const listed = (g.items || []).filter((it) => it.period !== 'long-term' && it.unit !== 'bps').slice(0, 14).map((it) => {
      const w = words(it);
      return `${it.basis === 'non-GAAP' ? 'adj. ' : it.basis === 'GAAP' ? 'GAAP ' : ''}${NAMES[it.metric] || it.metric}${it.scope === 'segment' ? ', a segment' : it.scope === 'organic' ? ', organic' : ''}${it.period ? ` (${it.period})` : ''}` +
        `${it.lo != null ? ' ' + range(it) : ''}${w.length ? ' ' + w.join(' ') : ''}${it.prior ? ' ' + priorText(it) : ''}`;
    });
    const footer = [
      `Guidance view (not a forecast by Filing Flows): violet bars = a figure ${company || 'the company'} guided, drawn at the midpoint; the dashed box ` +
      'spans the guided range and its tick marks the low end. Pale violet = not guided: the line keeps its share of its parent from ' +
      `${dec(base.label)}, so the chart adds up. Change words: ▲ raised / ▼ lowered = the midpoint moved; →← narrowed / ←→ widened = the range ` +
      'width changed; = reaffirmed; ✦ initiated; ✕ withdrawn — against the prior range the release states, else the company’s previous release on file.',
      `In the release${g.filed ? ` of ${fdate(g.filed)}` : ''}: ${listed.join('; ')}.` + (listed.length < (g.items || []).length ? ' …' : ''),
      'Only GAAP or basis-free guidance is drawn into the flows; adjusted (non-GAAP) figures are listed, not drawn. The cash-flow part is left out (not guided).',
    ];
    if (implied) footer.splice(1, 0, `${tg.label}: the full-year guidance minus the three reported quarters of FY${tg.fy}.`);
    P.notes.forEach((x) => footer.push(x));
    const words0 = (g.tags || []).filter((x) => x !== 'updated' && x !== 'mixed').map((x) => WORD[x]).filter(Boolean);
    return {
      future: true, kind: tg.kind, period: tg.label, bg: '#fbfaff',
      title: `${company ? company + ': ' : ''}${per} as guided`,
      subtitle: `From the ${g.form || '8-K'} earnings release filed ${fdate(g.filed)}${words0.length ? ' · ' + words0.join(' · ') : ''} · ${nGuided} guided line${nGuided === 1 ? '' : 's'}, the rest at ${dec(base.label)} shares`,
      nodes, links, footer, checks: [],
      legend: [['f_rev', 'Guided revenue'], ['f_profit', 'Guided profit'], ['f_cost', 'Guided cost'], ['fa_rev', 'Not guided: assumed (revenue)'],
        ['fa_profit', 'Assumed (profit)'], ['fa_cost', 'Assumed (cost)']],
      guidance: g, base: base.label,
    };
  }

  // the notes panel of a node in the guidance view (HTML)
  function noteHTML(n, g, esc) {
    const e = esc || enc;
    const note = n.gnote || {};
    if (note.guided) {
      const it = note.item;
      const w = words(it);
      return `<p><b>Guided:</b> ${e(range(it))}${it.basis ? ` (${e(it.basis)})` : ''}${it.period ? ` for ${e(it.period)}` : ''}${w.length ? ` · ${e(w.join(' · '))}` : ''}</p>` +
        (it.prior ? `<p class="muted">${e(priorText(it))}</p>` : '') +
        (it.quote ? `<blockquote><p>${e(it.quote)}</p></blockquote>` : '') +
        `<div class="src">From the earnings release${g && g.filed ? ` filed ${e(fdate(g.filed))}` : ''}${g && g.url ? ` · <a href="${e(g.url)}" target="_blank" rel="noopener">open filing ↗</a>` : ''}</div>`;
    }
    return '<p class="empty">Not guided: the line keeps its share of its parent from the period on file, so the chart adds up. It is an assumption, not a figure the company gave.</p>';
  }

  const api = { future, target, usable, words, range, priorText, noteHTML, WORD, NAMES, money };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.FFGuidance = api;
})(typeof window !== 'undefined' ? window : globalThis);
