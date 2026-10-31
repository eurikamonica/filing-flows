/* Money flow lab (beta) — pipeline/flowlab.py.
   FFFlowLab.industry(root, {sic, sector, here})  below the Industries page's estimated money flow: the corrected
     allocation (Beta 1.1, data/gamma/io-beta/), the filed cash flow, pay followed to households, two tiers of suppliers
     and capital spending by kind of asset (data/gamma/flowlab/<key>.json)
   FFFlowLab.company(root, {cik, ticker, name, here})  the company page's "Where each $1 goes" (data/flowlab/c/<cik>.json)
   Drawn with the site's Sankey (chains.js layout, sankey.js); a band or a bar opens where its figure comes from. */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const B = () => global.FF_BASE || '';                // the site root from a search page (c/<slug>/ → '../../')
  function usd(v) {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    if (a >= 1e12) return s + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + (a / 1e9).toFixed(a >= 1e11 ? 0 : a >= 1e10 ? 1 : 2) + 'B';
    if (a >= 1e6) return s + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M';
    if (a >= 1e3) return s + (a / 1e3).toFixed(0) + 'K';
    return s + a.toFixed(0);
  }
  const cents = (v, tot) => (tot ? (100 * v / tot >= 9.95 ? (100 * v / tot).toFixed(0) : (100 * v / tot).toFixed(1)) + '¢' : '—');
  const GRADE = { A: 'Filed figure (SEC financial statements)', B: 'Computed from filed figures', C: 'Industry average (input-output tables) applied to filed figures',
    D: 'National-average model — not this company’s or industry’s own records' };
  const WORD = { A: 'filed', B: 'computed', C: 'estimate', D: 'model' };
  const SHADE = { A: 1, B: 0.75, C: 0.3, D: 0.08 };
  const cache = {};
  const getJSON = (u) => cache[u] || (cache[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).catch((e) => { delete cache[u]; throw e; }));
  let shareP = null;
  function withShare(fn) {
    if (global.FFShare) return fn(global.FFShare);
    if (!shareP) shareP = new Promise((res) => { const sc = document.createElement('script'); sc.src = B() + 'disclosures/chart-share.js'; sc.onload = () => res(global.FFShare || null); sc.onerror = () => res(null); document.head.appendChild(sc); });
    shareP.then((S) => { if (S) fn(S); });
  }
  const chip = (g) => `<span class="fl-g fl-g-${esc(g)}" title="${esc(GRADE[g] || '')}">${esc(g)}</span>`;
  const legend = () => `<p class="fl-legend small">${['A', 'B', 'C', 'D'].map((g) => `${chip(g)} ${esc(GRADE[g])}`).join(' &nbsp; ')}. Darker bands are filed or computed figures, lighter ones estimates.</p>`;
  function css() {
    if (document.getElementById('fl-css')) return;
    const s = document.createElement('style');
    s.id = 'fl-css';
    s.textContent = `.fl-g{display:inline-block;min-width:16px;padding:0 4px;border-radius:4px;font:600 11px/16px var(--mono,monospace);text-align:center;color:#fff}
.fl-g-A{background:#1f5f46}.fl-g-B{background:#4f7f6a}.fl-g-C{background:#8a7a4a}.fl-g-D{background:#9a5b4a}
.fl-beta{display:inline-block;margin-left:8px;padding:1px 7px;border-radius:9px;background:#8a4fbf;color:#fff;font:600 11px/18px var(--sans,sans-serif);vertical-align:middle}
.fl-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.fl-tabs button{cursor:pointer;padding:7px 11px;border:1px solid #a7b2bc;border-radius:7px;background:transparent;color:inherit;font:inherit}
.fl-tabs button[aria-pressed="true"]{background:#184a68;color:#fff;border-color:#184a68}
.fl-chart{overflow-x:auto}.fl-chart svg{min-width:760px;width:100%;height:auto}.fl-chart .band{cursor:pointer}.fl-chart.sel .band:not(.on){opacity:.35}
.fl-panel{border:1px solid var(--line,#d6d3cc);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:14px}.fl-panel:empty{display:none}
.fl-legend{margin:6px 0 2px}.fl-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0}
.fl-card{border:1px solid var(--line,#d6d3cc);border-radius:8px;padding:8px 10px}.fl-card span{display:block;font-size:12px;opacity:.75}.fl-card strong{font-size:18px}
.fl-bar{height:8px;border-radius:4px;background:#5d7fa3;min-width:2px}`;
    document.head.appendChild(s);
  }

  // ---- a view (cols, nodes [id,col,label,color,grade], links [s,t,v,grade,note]) → a scene for sankey.js
  function sums(v) {
    const vin = {}, vout = {};
    v.links.forEach((l) => { vout[l[0]] = (vout[l[0]] || 0) + l[2]; vin[l[1]] = (vin[l[1]] || 0) + l[2]; });
    return { vin, vout };
  }
  function scene(v, o) {
    const { vin, vout } = sums(v);
    const nodes = v.nodes.map((n) => ({ id: n[0], col: n[1], t: n[2], label: WORD[n[4]] || '', v: Math.max(vin[n[0]] || 0, vout[n[0]] || 0), color: n[3],
      est: n[4] === 'C' || n[4] === 'D', grade: n[4] })).filter((n) => n.v > 0);
    const links = v.links.map((l) => ({ s: l[0], t: l[1], v: l[2], k: SHADE[l[3]] != null ? SHADE[l[3]] : 0.3 }));
    return global.FFChains.layout({ cols: v.cols.map((c, i) => ({ id: 'c' + i, name: c })), nodes, links }, o);
  }
  function draw(host, panel, v, o) {
    if (!global.FFChains || !global.Sankey) { host.innerHTML = '<p class="muted">The chart library did not load.</p>'; return null; }
    const sc = scene(v, o);
    host.innerHTML = global.Sankey.toSVG(sc, o.title);
    const svg = host.querySelector('svg');
    const byId = new Map(v.nodes.map((n) => [n[0], n]));
    const { vin, vout } = sums(v);
    const total = v.links.filter((l) => (byId.get(l[0]) || [])[1] === 0).reduce((a, l) => a + l[2], 0);
    if (svg) svg.addEventListener('click', (ev) => {
      const band = ev.target.closest && ev.target.closest('.band');
      const g = ev.target.closest && ev.target.closest('[data-node]');
      svg.querySelectorAll('.band.on').forEach((p) => p.classList.remove('on'));
      host.classList.toggle('sel', !!(band || g));
      if (band) {
        band.classList.add('on');
        const l = v.links.find((x) => x[0] === band.dataset.s && x[1] === band.dataset.t);
        if (!l) return;
        panel.innerHTML = `<b>${esc((byId.get(l[0]) || [])[2])} → ${esc((byId.get(l[1]) || [])[2])}</b>: ${usd(l[2])}` +
          (o.perDollar ? ` (${cents(l[2], total)} of every dollar spent)` : ` (${(100 * l[2] / (total || 1)).toFixed(1)}% of the first column)`) +
          `<br>${chip(l[3])} ${esc(GRADE[l[3]])}<br><span class="muted small">How: ${esc(v.notes[l[4]] || '')}</span>`;
      } else if (g) {
        const n = byId.get(g.dataset.node);
        if (!n) return;
        svg.querySelectorAll('.band').forEach((p) => { if (p.dataset.s === n[0] || p.dataset.t === n[0]) p.classList.add('on'); });
        const val = Math.max(vin[n[0]] || 0, vout[n[0]] || 0);
        const outs = v.links.filter((x) => x[0] === n[0]).sort((a, b) => b[2] - a[2]);
        panel.innerHTML = `<b>${esc(n[2])}</b>: ${usd(val)}${o.perDollar ? ` · ${cents(val, total)} of every dollar` : ''} ${chip(n[4])}` +
          (outs.length ? '<br>' + outs.slice(0, 8).map((x) => `${esc((byId.get(x[1]) || [])[2])} ${usd(x[2])}`).join(' · ') : '');
      } else panel.innerHTML = '';
    });
    return sc;
  }

  // ---------------------------------------------------------------- pay → which US households → how they spend
  // BLS Consumer Expenditure Survey 2022, income-quintile table 1101 (aggregate × quintile share ÷ consumer units: per
  // household a year). Cash contributions of the second fifth are suppressed by BLS (interpolated between its neighbours).
  const CEX_Q = [
    { inc: 14191, aft: 16337, earn: 0.4, c: { food: 5081, housing: 13343, apparel: 902, transport: 4910, healthcare: 3359, entertainment: 1226, education: 653, charity: 866, insurance: 655, other: 1567 } },
    { inc: 37441, aft: 39300, earn: 0.9, c: { food: 6533, housing: 17972, apparel: 1214, transport: 8172, healthcare: 4444, entertainment: 1970, education: 507, charity: 1363, insurance: 2359, other: 2086 } },
    { inc: 65659, aft: 63676, earn: 1.3, c: { food: 8581, housing: 21600, apparel: 1728, transport: 10745, healthcare: 5965, entertainment: 2935, education: 657, charity: 1854, insurance: 5444, other: 2555 } },
    { inc: 108730, aft: 99891, earn: 1.8, c: { food: 10754, housing: 26168, apparel: 2258, transport: 14713, healthcare: 6680, entertainment: 3758, education: 1179, charity: 2170, insurance: 10766, other: 3367 } },
    { inc: 244025, aft: 196794, earn: 2.1, c: { food: 15737, housing: 42411, apparel: 3616, transport: 22937, healthcare: 8807, entertainment: 7384, education: 3680, charity: 6407, insurance: 24529, other: 5151 } },
  ];
  const Q_NAME = ['lowest fifth', 'second fifth', 'middle fifth', 'fourth fifth', 'top fifth'];
  const HH_CAT = [['housing', 'Housing'], ['transport', 'Transportation'], ['food', 'Food'], ['insurance', 'Social Security & pensions (payroll)'],
    ['healthcare', 'Healthcare'], ['entertainment', 'Entertainment'], ['charity', 'Cash contributions'], ['apparel', 'Apparel & services'],
    ['education', 'Education'], ['other', 'Personal care, alcohol, tobacco & other']];
  // usual weekly earnings of full-time wage and salary workers, Q3 2026 (BLS CPS, table 5) × 52: 10th, 25th, 50th, 75th, 90th
  const EARN = [[10, 32968], [25, 44148], [50, 64064], [75, 99216], [90, 151788]];
  const HH_SRC = 'Pay: proxy statement (DEF 14A pay ratio: the median employee’s annual total compensation) or estimated pay ÷ the 10-K headcount. ' +
    'US earnings: BLS usual weekly earnings of full-time workers, Q3 2026, × 52. Households: BLS Consumer Expenditure Survey 2022 by income fifth ' +
    '(income before and after taxes, spending by category), matched by income per earner; the lowest fifth (mostly retirees and students) is not used for workers.';
  function earnPct(pay) {
    if (!fin(pay) || pay <= 0) return null;
    if (pay <= EARN[0][1]) return { p: 10, below: true };
    if (pay >= EARN[4][1]) return { p: 90, above: true };
    for (let i = 0; i < EARN.length - 1; i++) {
      const [p0, v0] = EARN[i], [p1, v1] = EARN[i + 1];
      if (pay <= v1) return { p: p0 + (p1 - p0) * Math.log(pay / v0) / Math.log(v1 / v0) };
    }
    return null;
  }
  const pctText = (e) => (!e ? '—' : e.below ? 'below the 10th percentile' : e.above ? 'above the 90th percentile' : `about the ${Math.round(e.p)}th percentile`);
  // a worker's pay → weights over the income fifths, by household income per earner (second fifth to top fifth)
  function fifths(pay) {
    const per = CEX_Q.map((q) => q.inc / q.earn), w = [0, 0, 0, 0, 0];
    if (!fin(pay) || pay <= per[1]) { w[1] = 1; return w; }
    if (pay >= per[4]) { w[4] = 1; return w; }
    for (let i = 1; i < 4; i++) {
      if (pay <= per[i + 1]) { const f = Math.log(pay / per[i]) / Math.log(per[i + 1] / per[i]); w[i] = 1 - f; w[i + 1] = f; return w; }
    }
    w[4] = 1; return w;
  }
  // one dollar of wages, as households of that mix use it: taxes, spending by category, saving
  function budget(w) {
    const out = { tax: 0, save: 0, over: 0, cat: {} };
    HH_CAT.forEach(([k]) => { out.cat[k] = 0; });
    w.forEach((wq, i) => {
      if (!wq) return;
      const q = CEX_Q[i], tax = Math.max(0, 1 - q.aft / q.inc), avail = 1 - tax;
      const raw = {}; let s = 0;
      HH_CAT.forEach(([k]) => { raw[k] = q.c[k] / q.inc; s += raw[k]; });
      const k0 = s > avail ? avail / s : 1;
      out.tax += wq * tax; out.save += wq * Math.max(0, avail - s); out.over += wq * Math.max(0, s / avail - 1);
      HH_CAT.forEach(([k]) => { out.cat[k] += wq * raw[k] * k0; });
    });
    return out;
  }
  const mixText = (w) => w.map((x, i) => [x, i]).filter((z) => z[0] > 0.04).sort((a, b) => b[0] - a[0]).map(([x, i]) => `${Math.round(100 * x)}% ${Q_NAME[i]}`).join(', ');
  // a view: wages → taxes / spending / saving → categories
  function householdView(wages, b, label) {
    const v = { cols: ['Wages', 'Taxes, spending, saving', 'Spent on'], nodes: [], links: [], notes: [HH_SRC, 'Federal, state and local income and other personal taxes: (income before taxes − after taxes) ÷ income before taxes for the matched households (BLS CEX)', 'Saving: after-tax income less spending for the matched households (BLS CEX)'] };
    v.nodes.push(['w', 0, label, '#9a8f7a', 'C'], ['tax', 1, 'Income & other personal taxes', '#a08a5a', 'D'], ['spend', 1, 'Household spending', '#7f97b3', 'D']);
    v.links.push(['w', 'tax', wages * b.tax, 'D', 1]);
    let sp = 0;
    HH_CAT.forEach(([k, l]) => { const x = wages * b.cat[k]; if (x > 0) { v.nodes.push(['c:' + k, 2, l, k === 'insurance' ? '#a08a5a' : '#88a3c0', 'D']); v.links.push(['spend', 'c:' + k, x, 'D', 0]); sp += x; } });
    v.links.push(['w', 'spend', sp, 'D', 0]);
    if (b.save > 0) { v.nodes.push(['save', 1, 'Saving', '#2e8b57', 'D']); v.links.push(['w', 'save', wages * b.save, 'D', 2]); }
    return v;
  }
  let empIdx = null;
  const empIndex = () => empIdx || (empIdx = getJSON(B() + 'disclosures/data/research/employees/index.json').then((d) => {
    const F = d.fields || [], m = new Map();
    (d.rows || []).forEach((r) => { const o = {}; F.forEach((k, i) => { o[k] = r[i]; }); m.set(+o.cik, o); });
    return m;
  }).catch(() => new Map()));
  const WAGE_SHARE = 0.8259;                       // wages in employee compensation (BEA NIPA 2025)
  function payOf(row, compUS, compOut) {           // [pay, how, grade]
    if (row && fin(row.median_pay) && row.median_pay > 0) return [row.median_pay, 'median employee, proxy statement', 'A'];
    if (row && row.employees > 0 && (compUS + compOut) > 0) return [(compUS + compOut) * WAGE_SHARE / row.employees, 'estimated wages ÷ 10-K headcount', 'C'];
    return [null, null, null];
  }

  // ---------------------------------------------------------------- industries
  const VIEWS = [
    ['alloc', 'Revenue allocation (corrected)'], ['cash', 'Filed cash flow'], ['people', 'Pay → households'],
    ['tiers', 'Supplier tiers'], ['capex', 'Capital spending by asset'],
  ];
  const INTRO = {
    alloc: 'The chart above, corrected: costs, employees and taxes are estimates (BEA), capital spending is filed, and what is left is called what it is — EBITDA − capital spending, not operating cash flow. Costs earned outside the US are split by multi-country tables, not the US one.',
    cash: 'Only filed figures: every member’s own cash-flow statement (latest four quarters, else the last fiscal year) — where the cash came from and where it went. ΔCash = operating + investing + financing cash flow + exchange rates. Cash is fungible: this does not say which dollar paid for which asset.',
    people: 'The estimated pay is not the end of the money: employers pay it as wages, health insurance, pensions and social insurance (BEA, 2025), and households pay taxes, save and spend the wages (BLS Consumer Expenditures 2024). A national-average model, not these employees’ own spending.',
    tiers: 'Purchased inputs, two steps up the supply chain. Each supplying industry passes the money on as its own purchases (tier 2), imports, its employees’ pay, taxes, and what is left to it. Every tier is part of the money before it — the columns add to the same total, they are not added on top of each other.',
    capex: 'Capital spending as filed, split by the kind of asset the industry buys (BEA fixed assets: structures, equipment, software) and the industries that build or sell them; the imported share and the part spent outside the US are shown apart.',
  };
  function viewPost(d, which, v) {
    const { vout } = sums(v);
    const top = v.links.filter((l) => v.nodes.find((n) => n[0] === l[0] && n[1] === 0)).sort((a, b) => b[2] - a[2]);
    const nm = new Map(v.nodes.map((n) => [n[0], n[2]]));
    const label = (VIEWS.find((x) => x[0] === which) || [])[1];
    const items = which === 'cash' ? v.links.filter((l) => l[0] === 'pool').sort((a, b) => b[2] - a[2]).slice(0, 5) : top.slice(0, 5);
    const tot = Object.values(vout).length ? items.reduce((a, l) => a + l[2], 0) : 0;
    return { title: `${label} (beta) — ${d.title}`,
      paras: [`${d.title}: ${label.toLowerCase()} (beta). ` + items.map((l) => `${nm.get(which === 'cash' ? l[1] : l[1])} ${usd(l[2])}`).join(', ') + '.', INTRO[which]],
      lines: [`${d.title} — ${label.toLowerCase()} (beta):`].concat(items.slice(0, 4).map((l) => `${nm.get(l[1])} ${usd(l[2])}${tot ? ' (' + Math.round(100 * l[2] / tot) + '%)' : ''}`)).concat(['Filing Flows money flow lab.']) };
  }
  function industry(root, o) {
    if (!root) return;
    css();
    const here = o.here || (() => true);
    const sic = String(o.sic || '');
    const levels = [['This industry', sic], ['Major group', 'sic2-' + sic.slice(0, 2)]].concat(o.sector ? [['Sector', 'sector-' + o.sector]] : []);
    const st = { key: sic, view: 'alloc' };
    root.innerHTML = `<div class="fl-tabs" role="group" aria-label="Level">${levels.map((l) => `<button type="button" data-k="${esc(l[1])}">${esc(l[0])}</button>`).join('')}</div>
      <div class="fl-tabs" role="group" aria-label="View">${VIEWS.map((x) => `<button type="button" data-v="${x[0]}">${esc(x[1])}</button>`).join('')}</div>
      <p class="muted small" id="fl-intro"></p><div id="fl-share"></div><div class="fl-chart" id="fl-chart"></div><div class="fl-panel" id="fl-panel"></div><div id="fl-more"></div>${legend()}`;
    const $ = (s) => root.querySelector(s);
    const press = () => {
      root.querySelectorAll('[data-k]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === st.key)));
      root.querySelectorAll('[data-v]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === st.view)));
    };
    async function show() {
      press();
      const chart = $('#fl-chart'), more = $('#fl-more'), panel = $('#fl-panel');
      chart.innerHTML = '<p class="muted">Loading…</p>'; more.innerHTML = ''; delete more.dataset.pay; panel.innerHTML = ''; $('#fl-share').innerHTML = '';
      $('#fl-intro').textContent = INTRO[st.view];
      if (st.view === 'alloc') return showAlloc(chart, more, panel);
      let d = null;
      try { d = await getJSON(B() + `data/gamma/flowlab/${st.key}.json`); } catch (e) { d = null; }
      if (!here()) return;
      let v = d && d.views && d.views[st.view];
      if (!v) { chart.innerHTML = '<p class="muted">Not built for this level yet: its companies need four quarters of figures' + (st.view === 'cash' ? ' and a cash-flow statement read (the scan reads a few dozen companies a run)' : '') + ', or the view did not pass the checks.</p>'; return; }
      if (st.view === 'people' && (v.meta || {}).members && (v.meta.members || []).length) {
        const idx = await empIndex();
        if (!here()) return;
        const mm = v.meta.members.map(([cik, us, out]) => { const r = idx.get(+cik); const [pay, how, g] = payOf(r, us, out); return { cik, us, pay, how, g, t: (r || {}).ticker || cik, name: (r || {}).name || '' }; }).filter((x) => fin(x.pay));
        const W = mm.reduce((a, x) => a + x.us, 0);
        if (W > 0) {
          const w = [0, 0, 0, 0, 0];
          mm.forEach((x) => { fifths(x.pay).forEach((f, i) => { w[i] += f * x.us / W; }); });
          const b = budget(w);
          const wagesTotal = v.links.filter((l) => l[1] === 'p:wages').reduce((a, l) => a + l[2], 0);
          const keep = v.links.filter((l) => l[0] !== 'p:wages');
          const nv = { cols: v.cols, meta: v.meta, notes: v.notes.concat([HH_SRC]), nodes: v.nodes.filter((n) => !String(n[0]).startsWith('h:')), links: keep };
          const ni = nv.notes.length - 1;
          nv.links.push(['p:wages', 'hh:tax', wagesTotal * b.tax, 'D', ni]);
          nv.nodes.push(['hh:tax', 2, 'Income & other personal taxes', '#a08a5a', 'D']);
          HH_CAT.forEach(([k, l]) => { const x = wagesTotal * b.cat[k]; if (x > 0) { nv.nodes.push(['hh:' + k, 2, l, k === 'insurance' ? '#a08a5a' : '#7f97b3', 'D']); nv.links.push(['p:wages', 'hh:' + k, x, 'D', ni]); } });
          if (b.save > 0) { nv.nodes.push(['hh:save', 2, 'Saving', '#2e8b57', 'D']); nv.links.push(['p:wages', 'hh:save', wagesTotal * b.save, 'D', ni]); }
          v = nv;
          const shown = mm.length, filedN = mm.filter((x) => x.g === 'A').length;
          $('#fl-intro').textContent = INTRO.people + ` Wages here are spent as US households earning like these companies’ employees spend: ${shown} of ${v.meta.members.length} companies with a pay figure (${filedN} from proxy statements), weighted by their US pay — ${mixText(w)} by household income.`;
          more.dataset.pay = JSON.stringify(mm.sort((a, b2) => b2.us - a.us).slice(0, 15));
        }
      }
      const label = (VIEWS.find((x) => x[0] === st.view) || [])[1];
      const first = v.links.filter((l) => (v.nodes.find((n) => n[0] === l[0]) || [])[1] === 0).reduce((a, l) => a + l[2], 0);
      const sub = { cash: `${usd(first)} of cash moved · ${(v.meta || {}).companies || 0} of ${d.companies} companies with a cash-flow statement read · all filed`,
        people: `${usd(first)} of estimated pay · national-average model below the first column`,
        tiers: `${usd(first)} of estimated purchased inputs (US) · each tier part of the one before`,
        capex: `${usd(first)} of filed capital spending · kinds of asset estimated` }[st.view];
      const opts = { title: `${label} (beta) — ${d.title}`, subtitle: sub,
        footer: ['Money flow lab (beta). Grades: A filed (SEC), B computed from filings, C industry average (BEA input-output), D national-average model (BEA NIPA, BLS Consumer Expenditures).',
          'Estimates are industry averages, not any company’s actual payments. Not investment advice.'] };
      const sc = draw(chart, panel, v, opts);
      if (sc) withShare((S) => { const el = $('#fl-share'); if (el && here()) el.innerHTML = S.bar({ key: `flowlab-${st.view}-${st.key}`, title: opts.title, scene: () => sc, post: () => viewPost(d, st.view, v) }); });
      const ends = v.nodes.filter((n) => n[1] === v.cols.length - 1).map((n) => [n, v.links.filter((l) => l[1] === n[0]).reduce((a, l) => a + l[2], 0)]).sort((a, b) => b[1] - a[1]);
      more.innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>${esc(v.cols[v.cols.length - 1])}</th><th class="num">Amount</th><th class="num">Share</th><th>Evidence</th></tr></thead><tbody>${
        ends.slice(0, 24).map(([n, x]) => `<tr><td>${esc(n[2])}</td><td class="num">${usd(x)}</td><td class="num">${(100 * x / (first || 1)).toFixed(1)}%</td><td>${chip(n[4])} ${esc(WORD[n[4]])}</td></tr>`).join('')}</tbody></table></div>` +
        `<details class="method-note"><summary>Sources and how each band is computed</summary><ul>${v.notes.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` +
        (d.sources ? `<p class="small">${esc(d.sources.pay)}. ${esc(d.sources.households)}. ${esc(d.sources.wages)}. BEA input-output ${esc(d.sources.bea_year)}, scaled to ${esc(d.sources.scale_year)}.</p>` : '') + '</details>';
      if (more.dataset.pay) {
        const mm = JSON.parse(more.dataset.pay);
        more.innerHTML += `<h3>Pay at the largest employers here</h3><div class="tbl-wrap"><table><thead><tr><th>Company</th><th class="num">Pay</th><th>From</th><th>Place in US full-time earnings</th><th>Households like theirs</th></tr></thead><tbody>${
          mm.map((x) => `<tr><td><a href="${B()}#c-${esc(x.cik)}-dollar"><b>${esc(x.t)}</b></a> <span class="muted small">${esc(x.name)}</span></td><td class="num">${usd(x.pay)}</td><td>${chip(x.g)} ${esc(x.how)}</td><td>${esc(pctText(earnPct(x.pay)))}</td><td>${esc(mixText(fifths(x.pay)))}</td></tr>`).join('')}</tbody></table></div>`;
      }
    }
    async function showAlloc(chart, more, panel) {
      let d = null;
      try { d = await getJSON(B() + `data/gamma/io-beta/${st.key}.json`); } catch (e) { d = null; }
      if (!here()) return;
      if (!d || !(d.links || []).length) { chart.innerHTML = '<p class="muted">The corrected allocation is not built for this level (or held back by its checks).</p>'; return; }
      const v = { cols: d.cols.map((c) => c.name), notes: [], nodes: d.nodes.map((n) => [n.id, n.col, n.label, n.color, n.grade]),
        links: d.links.map((l) => { const p = d.prov[l[0] + '|' + l[1]] || {}; const txt = [p.formula, p.source].filter(Boolean).join(' — ') + (p.lo != null && p.hi != null ? ` (range ${usd(p.lo)} – ${usd(p.hi)})` : ''); return [l[0], l[1], l[2], p.grade || 'C', txt]; }) };
      v.links.forEach((l) => { let i = v.notes.indexOf(l[4]); if (i < 0) { v.notes.push(l[4]); i = v.notes.length - 1; } l[4] = i; });
      const F = d.filed || {};
      const opts = { title: 'Revenue allocation, corrected (beta) — ' + d.title,
        subtitle: `${usd(d.revenue)} revenue over four quarters · ${d.companies} companies · darker bands filed or computed, lighter ones estimates`,
        footer: ['Filed figures from SEC filings; US spending split by BEA input-output, spending abroad by multi-country tables (FIGARO, ADB); suppliers by revenue share unless a filing names them.',
          'Supplier amounts are a modelled allocation, not verified purchases. Not investment advice.'] };
      draw(chart, panel, v, opts);
      more.innerHTML = `<div class="fl-cards">${[['Revenue (filed)', F.revenue], ['Operating cash flow (filed)', F.ocf], ['Capital spending (filed)', F.capex], ['Free cash flow (filed)', F.fcf], ['EBITDA − capital spending', F.ebitda_capex]]
        .filter((z) => fin(z[1])).map((z) => `<div class="fl-card"><span>${esc(z[0])}</span><strong>${usd(z[1])}</strong></div>`).join('')}</div>` +
        '<p class="small">The chart above calls EBITDA − capital spending “operating cash left over”; it is not operating cash flow (it is before interest, tax and working capital) and not free cash flow — both are shown here as filed. <a href="' + B() + 'beta/money-flow.html#' + esc(st.key) + '">Open the full Beta 1.1 page →</a></p>';
    }
    root.querySelectorAll('[data-k]').forEach((b) => b.addEventListener('click', () => { st.key = b.dataset.k; show(); }));
    root.querySelectorAll('[data-v]').forEach((b) => b.addEventListener('click', () => { st.view = b.dataset.v; show(); }));
    show();
  }

  // ---------------------------------------------------------------- one company: every dollar it spent
  function companyPost(d, rows) {
    const who = d.ticker || d.name;
    return { title: `Where each $1 ${who} spends goes (beta)`,
      paras: [`Every dollar ${d.name} spent over the four quarters to ${d.end} (${usd(d.total)} in all): ` + rows.slice(0, 6).map((r) => `${r[0]} ${cents(r[1], d.total)}`).join(', ') + '.',
        'Capital spending, acquisitions, dividends, buybacks and debt repaid are filed; how operating costs split between suppliers, employees and taxes is an industry average (BEA input-output).'],
      lines: [`Where each $1 ${who} spends goes (est.):`].concat(rows.slice(0, 5).map((r) => `${r[0]} ${cents(r[1], d.total)}`)).concat(['Filing Flows · beta']) };
  }
  async function company(root, o) {
    if (!root) return;
    css();
    const here = o.here || (() => true);
    root.innerHTML = '<p class="muted">Loading…</p>';
    let d = null;
    try { d = await getJSON(B() + `data/flowlab/c/${parseInt(o.cik, 10)}.json`); } catch (e) { d = null; }
    if (!here()) return;
    if (!d) {
      root.innerHTML = `<section class="section"><div class="section-head"><h2>Where each $1 goes <span class="fl-beta">Beta</span></h2></div><p class="muted">Not built for ${esc(o.name || 'this company')} yet: it needs four quarters of revenue and operating income and an SIC code with a BEA industry. Foreign filers without dollar figures are left out.</p></section>`;
      return;
    }
    const nm = new Map(d.nodes.map((n) => [n[0], n]));
    const rows = d.links.filter((l) => l[0] === 'all').map((l) => [(nm.get(l[1]) || [])[2], l[2], (nm.get(l[1]) || [])[4], l[1]]).sort((a, b) => b[1] - a[1]);
    const filed = rows.filter((r) => r[2] === 'A' || r[2] === 'B').reduce((a, r) => a + r[1], 0);
    root.innerHTML = `<section class="section"><div class="section-head"><h2>Where each $1 ${esc(d.ticker || d.name)} spends goes <span class="fl-beta">Beta</span></h2>
      <span class="muted">Four quarters to ${esc(d.end)}${d.cash ? ' · cash-flow statement: ' + esc(d.cash) : ''}</span></div>
      <p>${esc(d.name)} spent about <b>${usd(d.total)}</b> over the last four quarters (revenue ${usd(d.revenue)}). Of every dollar, <b>${cents(filed, d.total)}</b> is a filed or computed figure; the rest — how operating costs split between suppliers, employees and taxes — is an industry average.</p>
      <div class="tbl-wrap"><table><thead><tr><th>Every $1 spent</th><th class="num">Cents</th><th class="num">Amount</th><th style="width:30%"></th><th>Evidence</th></tr></thead><tbody>${
        rows.map((r) => `<tr><td>${esc(r[0])}</td><td class="num"><b>${cents(r[1], d.total)}</b></td><td class="num">${usd(r[1])}</td><td><div class="fl-bar" style="width:${Math.max(1, 100 * r[1] / rows[0][1]).toFixed(1)}%"></div></td><td>${chip(r[2])} ${esc(WORD[r[2]])}</td></tr>`).join('')}</tbody></table></div>
      <div id="fl-share"></div><div class="fl-chart" id="fl-chart"></div><div class="fl-panel" id="fl-panel"></div>${legend()}
      <details class="method-note"><summary>How this is worked out</summary>
      <p><b>Spent</b> = operating spending (${d.fin ? 'revenue × the typical expense ratio of lenders and insurers' : 'revenue − operating income − depreciation & amortization'}) + capital spending + income taxes + acquisitions + dividends + buybacks + net debt repaid. It is cash going out over a year, not a profit-and-loss statement; borrowing or cash on hand pays for what revenue does not.</p>
      <p><b>Operating spending</b> is split as BEA’s input-output tables split the spending of the company’s industry${d.us != null && d.us < 1 ? ` — the ${Math.round(100 * d.us)}% earned in the US by the US table, the rest by multi-country tables (FIGARO, ADB)` : ''}: purchased inputs (and the industries that supply them, with the imported share apart), employee pay, taxes on production. ${d.geo ? 'US share from the 10-K: “' + esc(String(d.geo).slice(0, 220)) + '…”' : ''}</p>
      <p><b>Employee pay</b> is split as US employers pay (BEA NIPA 2025): wages, health insurance, pensions and benefits, social insurance — national averages, not this company’s benefits. Stock-based pay is inside operating spending as expensed, though it is not cash.</p>
      <p><b>Capital spending</b> is filed; the kinds of asset (structures, equipment, software) follow the industry’s asset mix in BEA’s fixed-asset tables. <b>Acquisitions, dividends, buybacks and debt repaid</b> are the company’s own cash-flow statement${d.cash ? ' (' + esc(d.cash) + ')' : ' — not read for this company yet'}. Income taxes are the income-statement expense; cash paid can differ.</p>
      <p>Money is conserved in every column; a company whose figures do not add up is held back.${d.doc ? ` Source filing: <a href="${esc(d.doc)}" target="_blank" rel="noopener">${esc(d.form || 'SEC filing')}</a>.` : ''}</p>
      <ul class="small">${d.notes.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details></section>`;
    const opts = { title: `Where each $1 ${d.ticker || d.name} spends goes (beta)`, perDollar: true,
      subtitle: `${usd(d.total)} spent over the four quarters to ${d.end} · percentages are cents of every dollar · darker bands filed, lighter ones estimates`,
      footer: ['Capital spending, acquisitions, dividends, buybacks, debt repaid: SEC filings. Suppliers, employees, taxes: industry averages (BEA input-output); pay split: BEA NIPA.',
        'Estimates are industry averages, not the company’s actual payments. Not investment advice.'] };
    const sc = draw(root.querySelector('#fl-chart'), root.querySelector('#fl-panel'), d, opts);
    if (sc) withShare((S) => { const el = root.querySelector('#fl-share'); if (el && here()) el.innerHTML = S.bar({ key: 'dollar-' + d.cik, title: opts.title, scene: () => sc, post: () => companyPost(d, rows) }); });
    households(root, d, o, here);
  }

  // ---- the company's employees: what they are paid, where that sits among US earners, how households like theirs spend
  async function households(root, d, o, here) {
    const box = document.createElement('section');
    box.className = 'section';
    root.appendChild(box);
    const link = (id) => (d.links.find((l) => l[0] === 'all' && l[1] === id) || [])[2] || 0;
    const compUS = link('k:emp'), compOut = link('k:employees_out');
    const wages = (d.links.find((l) => l[0] === 'k:emp' && l[1] === 'p:wages') || [])[2] || compUS * WAGE_SHARE;
    let row = null, one = null;
    try { row = (await empIndex()).get(+d.cik) || null; } catch (e) { row = null; }
    try { one = await getJSON(B() + `disclosures/data/research/employees/c/${+d.cik}.json`); } catch (e) { one = null; }
    if (!here()) return;
    const P = (one && one.pay) || null;
    const [pay, how] = payOf(row, compUS, compOut);
    const head = `<div class="section-head"><h2>Who the pay goes to, and how they spend it <span class="fl-beta">Beta</span></h2><span class="muted">Pay matched to US households</span></div>`;
    if (!fin(pay) || wages <= 0) {
      box.innerHTML = head + `<p class="muted">No pay figure for ${esc(d.name)} yet: the median employee’s pay is read from its proxy statement (DEF 14A), and the headcount from its 10-K, a few hundred companies a day.</p>`;
      return;
    }
    const e = earnPct(pay), w = fifths(pay), b = budget(w);
    const est = row && row.employees > 0 ? (compUS + compOut) * WAGE_SHARE / row.employees : null;
    const cards = [
      P ? ['Median employee pay (proxy)', usd(P.pay), `${P.form || 'DEF 14A'} filed ${P.filed || ''}${P.ratio ? ` · CEO pay ${Math.round(P.ratio)}× this` : ''}`] : null,
      fin(est) ? ['Average wage (estimate)', usd(est), `estimated wages ÷ ${Number(row.employees).toLocaleString('en-US')} employees (10-K)`] : null,
      ['Place in US full-time earnings', e ? (e.below ? '<10th pct.' : e.above ? '>90th pct.' : Math.round(e.p) + 'th pct.') : '—', 'BLS weekly earnings, Q3 2026'],
      ['Households like theirs', mixText(w), 'by income per earner (BLS CEX)'],
    ].filter(Boolean);
    box.innerHTML = head + `<p>${esc(d.name)}’s pay figure is <b>${usd(pay)}</b> (${esc(how)}) — ${esc(pctText(e))} of US full-time earners. Households earning like that per worker are the ${esc(mixText(w))} of US households by income. Below, the company’s estimated US wages (${usd(wages)}) are spent the way those households spend: taxes, then housing, transport, food and the rest, and what they save.${b.over > 0.02 ? ` Those households spend about ${Math.round(100 * b.over)}% more than their after-tax income (savings drawn, help from family); the spending is scaled to the pay.` : ''}</p>
      <div class="fl-cards">${cards.map((c) => `<div class="fl-card"><span>${esc(c[0])}</span><strong>${esc(c[1])}</strong><span>${esc(c[2])}</span></div>`).join('')}</div>
      ${P && P.sentence ? `<p class="small muted">“${esc(String(P.sentence).slice(0, 320))}” ${P.url ? `<a href="${esc(P.url)}" target="_blank" rel="noopener">proxy statement</a>` : ''}</p>` : ''}
      <div class="fl-chart" id="fl-hh-chart"></div><div class="fl-panel" id="fl-hh-panel"></div>
      <details class="method-note"><summary>How the pay is matched</summary><p>${esc(HH_SRC)}</p>
      <p>The proxy’s median covers employees worldwide (up to 5% abroad may be left out) and is total compensation as the company measures it; a company with many part-time or overseas staff has a low median. Households are matched by income per earner because most households have more than one; the result is how US households at that income spend on average, not these employees’ own records.</p></details>`;
    const v = householdView(wages, b, 'Wages — US (estimate)');
    draw(box.querySelector('#fl-hh-chart'), box.querySelector('#fl-hh-panel'), v, { title: `How ${d.ticker || d.name}’s US wages are spent (beta model)`, perDollar: true,
      subtitle: `${usd(wages)} of estimated US wages · pay ${usd(pay)} (${how}) · spent like the ${mixText(w)} of US households`,
      footer: ['Wages: BEA input-output estimate. Pay: proxy statement or estimate ÷ headcount. Households: BLS Consumer Expenditure Survey 2022 by income fifth; earnings: BLS CPS Q3 2026.',
        'A national-average model of households at that income, not these employees’ own spending. Not investment advice.'] });
  }

  global.FFFlowLab = { industry, company, _hh: { earnPct, fifths, budget } };
})(window);
