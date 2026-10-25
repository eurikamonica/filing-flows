/* Custom charts (#chart): any line items of any companies on the site, quarter by quarter. Pick companies (up to six)
   and lines (revenue, operating profit, net earnings, operating cash flow, operating margin, and every line of their
   Sankeys — R&D, cost of revenue, segments …), as lines or bars. The choice lives in the address
   (#chart/c=320193,1067983&i=h:revenue,n:Research & development&t=line) so a chart can be shared; CSV and SVG downloads.
   Data: data/c/<cik>.json — the quarters on the page plus the longer revenue / profit / cash history (quality.hist). */
(function (root) {
  'use strict';
  const U = root.FFUx;
  const { esc, t, fin, num, money, day } = U;
  const HEAD = [['revenue', 'Revenue'], ['oi', 'Operating profit'], ['ni', 'Net earnings'], ['ocf', 'Operating cash flow'], ['om', 'Operating margin (%)']];
  const NODE_IS_HEAD = { revenue: 'revenue', oi: 'oi', net: 'ni', ocf: 'ocf' };
  const MAX_CO = 6, MAX_SERIES = 8;

  // every series of one company: { 'h:revenue': Map(end → value), 'n:<line name>': Map(...) }, with labels
  function seriesOf(c) {
    const S = {}, label = {};
    const put = (key, lab, end, v) => { if (!fin(v) || !end) return; (S[key] = S[key] || new Map()).set(end, +v); label[key] = lab; };
    // a company reporting in another currency: its dollar charts (pipeline/fx.py) when the page has them, so every
    // line on the chart is in dollars; the long history (reported currency) is converted at each quarter's own rate
    const foreign = c.currency && c.currency !== 'USD';
    const quarters = foreign && c.usd && c.usd.quarters ? c.usd.quarters : (c.quarters || []);
    const rate = new Map();
    if (foreign && c.usd && c.usd.quarters) {
      for (const u of c.usd.quarters) {
        const r = (c.quarters || []).find((q) => q.end === u.end);
        if (r && r.headline && u.headline && r.headline.revenue) rate.set(u.end, u.headline.revenue / r.headline.revenue);
      }
    }
    const hist = (c.quality || {}).hist;
    if (hist && hist.periods && hist.v && (!foreign || rate.size)) {
      const last = Math.max(...rate.values(), 0) || 1;
      for (const [k, rows] of Object.entries(hist.v)) {
        const lab = (HEAD.find((h) => h[0] === k) || [])[1];
        if (!lab) continue;
        for (const [pi, vals] of rows || []) {
          const p = hist.periods[pi];
          if (!(p && p[2] === 'q' && vals && vals[0])) continue;
          const f = foreign ? (rate.get(p[1]) || (k === 'om' ? 1 : null)) : 1;   // a quarter before the dollar versions: skipped
          if (f != null) put('h:' + k, lab, p[1], k === 'om' ? vals[0][0] : vals[0][0] * f);
        }
      }
    }
    for (const q of quarters) {
      if (q.end && /^(Q|q)/.test(String(q.label || 'Q'))) {
        const h = q.headline || {};
        for (const [k, lab] of HEAD) if (fin(h[k])) put('h:' + k, lab, q.end, h[k]);
        for (const n of q.nodes || []) {
          if (NODE_IS_HEAD[n.id]) continue;
          const name = U.dec(n.name);
          put('n:' + name, name, q.end, n.v);
        }
      }
    }
    return { S, label };
  }

  function parse(arg) {
    const st = { c: [], i: ['h:revenue'], t: 'line' };
    for (const part of String(arg || '').split('&')) {
      const [k, v] = part.split('=');
      if (!v) continue;
      if (k === 'c') st.c = v.split(',').map((x) => +x).filter((x) => x > 0).slice(0, MAX_CO);
      if (k === 'i') st.i = v.split(',').map(decodeURIComponent).filter(Boolean).slice(0, MAX_SERIES);
      if (k === 't' && (v === 'line' || v === 'bar')) st.t = v;
    }
    return st;
  }
  const serialize = (st) => `chart/c=${st.c.join(',')}&i=${st.i.map((x) => encodeURIComponent(x)).join(',')}&t=${st.t}`;

  // the plotted series: [{key, company, label, unit, pts: [[end, v]]}]
  function plotted(st, data) {
    const out = [];
    for (const cik of st.c) {
      const d = data.get(cik);
      if (!d) continue;
      for (const key of st.i) {
        const m = d.ser.S[key];
        if (!m || !m.size) continue;
        out.push({ key, cik, company: d.name, ticker: d.ticker, label: d.ser.label[key], unit: key === 'h:om' ? '%' : '$', pts: [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])) });
        if (out.length >= MAX_SERIES) return out;
      }
    }
    return out;
  }

  function svg(series, type, W = 860, H = 380) {
    if (!series.length) return '<p class="muted">Pick at least one company and one line.</p>';
    const L = 74, R = series.some((s) => s.unit === '%') && series.some((s) => s.unit === '$') ? 56 : 20, T = 18, B = 46;
    const ends = [...new Set(series.flatMap((s) => s.pts.map((p) => p[0])))].sort();
    const ts = ends.map((e) => Date.parse(e)), t0 = Math.min(...ts), t1 = Math.max(...ts);
    const xOf = type === 'bar' ? (e) => L + (ends.indexOf(e) + 0.5) * (W - L - R) / ends.length : (e) => L + (t1 > t0 ? (Date.parse(e) - t0) / (t1 - t0) : 0.5) * (W - L - R);
    const axis = (unit) => {
      const vals = series.filter((s) => s.unit === unit).flatMap((s) => s.pts.map((p) => p[1]));
      if (!vals.length) return null;
      let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
      if (lo === hi) hi = lo + 1;
      const pad = (hi - lo) * 0.06; hi += hi > 0 ? pad : 0; lo -= lo < 0 ? pad : 0;
      return { lo, hi, y: (v) => T + (hi - v) / (hi - lo) * (H - T - B), f: unit === '%' ? (v) => num(v, Math.abs(v) < 10 ? 1 : 0) + '%' : (v) => money(v) };
    };
    const A = { '$': axis('$'), '%': axis('%') }, main = A['$'] || A['%'];
    let g = '';
    for (let i = 0; i <= 4; i++) {
      const v = main.lo + (main.hi - main.lo) * i / 4, y = main.y(v);
      g += `<line class="fx-grid" x1="${L}" x2="${W - R}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"/><text class="fx-ax" x="${L - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${esc(main.f(v))}</text>`;
      if (A['$'] && A['%']) { const v2 = A['%'].lo + (A['%'].hi - A['%'].lo) * i / 4; g += `<text class="fx-ax" x="${W - R + 6}" y="${(A['%'].y(v2) + 4).toFixed(1)}">${esc(A['%'].f(v2))}</text>`; }
    }
    if (main.lo < 0) g += `<line class="fx-zero" x1="${L}" x2="${W - R}" y1="${main.y(0).toFixed(1)}" y2="${main.y(0).toFixed(1)}"/>`;
    const step = Math.max(1, Math.ceil(ends.length / 8));
    ends.forEach((e, i) => { if (i % step === 0 || i === ends.length - 1) g += `<text class="fx-ax" x="${xOf(e).toFixed(1)}" y="${H - B + 18}" text-anchor="middle">${esc(e.slice(0, 7))}</text>`; });
    const bw = type === 'bar' ? Math.max(2, (W - L - R) / ends.length * 0.8 / series.length) : 0;
    series.forEach((s, k) => {
      const ax = A[s.unit], col = U.PALETTE[k % U.PALETTE.length];
      if (type === 'bar') {
        for (const [e, v] of s.pts) {
          const x = xOf(e) - (series.length * bw) / 2 + k * bw, y0 = ax.y(0), y1 = ax.y(v);
          g += `<rect x="${x.toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${(bw * 0.92).toFixed(1)}" height="${Math.max(1, Math.abs(y1 - y0)).toFixed(1)}" fill="${col}"><title>${esc(s.ticker || s.company)} · ${esc(s.label)} · ${esc(e)}: ${esc(ax.f(v))}</title></rect>`;
        }
      } else {
        g += `<path d="${s.pts.map((p, i) => `${i ? 'L' : 'M'}${xOf(p[0]).toFixed(1)},${ax.y(p[1]).toFixed(1)}`).join(' ')}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>`;
        for (const [e, v] of s.pts) g += `<circle cx="${xOf(e).toFixed(1)}" cy="${ax.y(v).toFixed(1)}" r="3.4" fill="${col}"><title>${esc(s.ticker || s.company)} · ${esc(s.label)} · ${esc(e)}: ${esc(ax.f(v))}</title></circle>`;
      }
    });
    const legend = series.map((s, k) => `<span class="fx-leg"><i style="background:${U.PALETTE[k % U.PALETTE.length]}"></i>${esc(s.ticker || s.company)} · ${esc(s.label)}${s.unit === '%' && A['$'] ? ' (right axis)' : ''}</span>`).join('');
    return `<svg class="fx-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Custom chart: ${esc(series.map((s) => (s.ticker || s.company) + ' ' + s.label).join(', '))}" xmlns="http://www.w3.org/2000/svg"><style>.fx-grid{stroke:#dedcd5;stroke-width:1}.fx-zero{stroke:#6b6a66;stroke-width:1}.fx-ax{font:12px 'IBM Plex Sans',Arial,sans-serif;fill:#6b6a66}</style>${g}</svg><div class="fx-legend">${legend}</div>`;
  }

  async function render(app, A, arg) {
    const here = A && A.here ? A.here : () => true;
    if (A && A.setNav) A.setNav('chart');
    const st = parse(arg);
    const ix = await U.site('index.json');
    if (!here()) return;
    const cos = ((ix && ix.companies) || []).slice().sort((a, b) => (b.revenue || 0) - (a.revenue || 0));
    const data = new Map();
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Charts · <a href="#studio">Videos →</a></div><h1>Chart any line, any company</h1>
      <p class="muted" style="max-width:72ch">Every line of the companies' earnings Sankeys, quarter by quarter, side by side. The address keeps your choice, so the chart can be shared.</p></div>
      <div class="fx-cc"><div class="fx-cc-side">
        <h3>Companies</h3><div id="fx-cos"></div>
        <form id="fx-addco" class="fx-row"><input class="input" list="fx-colist" id="fx-co" placeholder="Ticker or company" aria-label="Add a company" autocomplete="off"><button class="btn" type="submit">Add</button></form>
        <datalist id="fx-colist">${cos.slice(0, 3000).map((c) => `<option value="${esc(c.ticker || c.cik)}">${t(c.name)}</option>`).join('')}</datalist>
        <h3>Lines</h3><input class="input" id="fx-filter" placeholder="Filter lines" aria-label="Filter lines"><div id="fx-items" class="fx-items"></div>
      </div><div class="fx-cc-main">
        <div class="fx-row"><div class="pills" role="group" aria-label="Chart type"><button type="button" class="pill" data-ct="line">Lines</button><button type="button" class="pill" data-ct="bar">Bars</button></div>
          <span class="fx-sp"></span><button type="button" class="btn" id="fx-link">Copy link</button><button type="button" class="btn" id="fx-csv">CSV ↓</button><button type="button" class="btn" id="fx-svg">SVG ↓</button></div>
        <div id="fx-plot" class="fx-plot"></div><p class="muted q-small">Quarterly values as reported (three-month periods); fiscal quarters are placed at their end dates. Read automatically from SEC filings — check the filing before relying on a figure.</p>
      </div></div>`;
    const $ = (s) => app.querySelector(s);
    const save = () => { try { history.replaceState(null, '', '#' + serialize(st)); } catch (e) { /* file:// */ } };
    async function ensure() {
      await Promise.all(st.c.filter((cik) => !data.has(cik)).map(async (cik) => {
        const c = await U.site(`c/${cik}.json`);
        if (c) data.set(cik, { c, name: U.dec(c.profile.name), ticker: (c.profile.tickers || [])[0] || '', ser: seriesOf(c) });
      }));
    }
    function drawSide() {
      $('#fx-cos').innerHTML = st.c.map((cik) => { const d = data.get(cik); return `<span class="tag">${esc(d ? d.ticker || d.name : cik)} <button type="button" class="fx-x" data-rmco="${cik}" aria-label="Remove">×</button></span>`; }).join(' ') || '<span class="muted">None yet: add one.</span>';
      const count = new Map();
      for (const cik of st.c) { const d = data.get(cik); if (d) for (const k of Object.keys(d.ser.S)) count.set(k, (count.get(k) || 0) + 1); }
      const lab = (k) => { for (const d of data.values()) if (d.ser.label[k]) return d.ser.label[k]; return k.slice(2); };
      const keys = [...count.keys()].sort((a, b) => (a[0] === 'h' ? 0 : 1) - (b[0] === 'h' ? 0 : 1) || count.get(b) - count.get(a) || lab(a).localeCompare(lab(b)));
      const f = ($('#fx-filter').value || '').toLowerCase();
      $('#fx-items').innerHTML = keys.filter((k) => !f || lab(k).toLowerCase().includes(f)).slice(0, 150).map((k) => `<label class="fx-item"><input type="checkbox" data-it="${esc(k)}" ${st.i.includes(k) ? 'checked' : ''}> ${esc(lab(k))}${st.c.length > 1 ? ` <small class="muted">${count.get(k)}/${st.c.length}</small>` : ''}</label>`).join('') || '<span class="muted">Add a company to see its lines.</span>';
      app.querySelectorAll('[data-ct]').forEach((b) => b.classList.toggle('on', b.dataset.ct === st.t));
    }
    function drawPlot() { $('#fx-plot').innerHTML = svg(plotted(st, data), st.t); }
    async function update() { await ensure(); if (!here()) return; save(); drawSide(); drawPlot(); }
    const box = app.querySelector('.fx-cc');            // listeners on the page's own box (the #app element outlives the page)
    box.addEventListener('click', (e) => {
      const rm = e.target.closest('[data-rmco]');
      if (rm) { st.c = st.c.filter((x) => x !== +rm.dataset.rmco); update(); }
      const ct = e.target.closest('[data-ct]');
      if (ct) { st.t = ct.dataset.ct; update(); }
    });
    box.addEventListener('change', (e) => {
      const it = e.target.closest('[data-it]');
      if (!it) return;
      st.i = it.checked ? [...new Set(st.i.concat(it.dataset.it))].slice(-MAX_SERIES) : st.i.filter((x) => x !== it.dataset.it);
      update();
    });
    $('#fx-filter').addEventListener('input', drawSide);
    $('#fx-addco').addEventListener('submit', (e) => {
      e.preventDefault();
      const v = $('#fx-co').value.trim().toUpperCase();
      const hit = cos.find((c) => String(c.ticker || '').toUpperCase() === v || String(c.cik) === v) || cos.find((c) => U.dec(c.name).toUpperCase().startsWith(v));
      if (!hit) { $('#fx-co').setCustomValidity('Not a company on the site'); $('#fx-co').reportValidity(); return; }
      $('#fx-co').setCustomValidity(''); $('#fx-co').value = '';
      if (!st.c.includes(+hit.cik) && st.c.length < MAX_CO) st.c.push(+hit.cik);
      update();
    });
    $('#fx-link').addEventListener('click', () => { const u = location.href.split('#')[0] + '#' + serialize(st); (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => { $('#fx-link').textContent = 'Copied'; }, () => prompt('Link to this chart', u)); });
    $('#fx-csv').addEventListener('click', () => U.csv(plotted(st, data).flatMap((s) => s.pts.map(([end, v]) => ({ company: s.company, ticker: s.ticker, line: s.label, quarter_end: end, value: v }))), 'filing-flows-chart'));
    $('#fx-svg').addEventListener('click', () => { const s = $('#fx-plot svg'); if (s) U.download(new Blob([s.outerHTML], { type: 'image/svg+xml' }), 'filing-flows-chart.svg'); });
    if (!st.c.length && cos.length) st.c = [+cos[0].cik];
    update();
  }
  root.FFCharts = { render, seriesOf, parse, serialize, plotted, svg };
  if (typeof module !== 'undefined') module.exports = root.FFCharts;
})(typeof globalThis !== 'undefined' ? globalThis : this);
