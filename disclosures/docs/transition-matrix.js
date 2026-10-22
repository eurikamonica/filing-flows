/* Crowd Flow transition audit — descriptive history, not a forecast (research spec v5 §6.6–6.7, §8.3, §11, §15.6).
   How stocks moved between Hype-map quadrants from one report quarter to the next, separately for each clock
   (quarter-aligned; public as of 30 days, the 45-day deadline and 90 days), with sample sizes, Wilson 95% intervals
   and the spread between quarter pairs; for the deadline view also what stocks did over the next 4 and 12 weeks
   against SPY by quadrant, beside price-only, crowd-only and coverage-only baselines and a within-date shuffle of the
   13F side. window.CrowdTransitions.render(el, {hub, view, ticker, quad, compact}). Data: data/market/crowd-transitions.json
   (app/crowd_clocks.py audit). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const qlabel = (p) => { const [y, m] = String(p).split('-'); return 'Q' + Math.ceil(+m / 3) + ' ' + y; };
  const VIEW_LABEL = { quarter_aligned: 'Quarter-aligned (retrospective)', public_knowledge_asof_30d: 'Public as of 30 days', public_knowledge_asof_45d: 'Public as of the 45-day deadline', public_knowledge_asof_90d: 'Public as of 90 days' };
  const GROUPS = [['BR', 'Bought and rising'], ['SR', 'Sold while rising'], ['SF', 'Sold and falling'], ['BF', 'Bought while falling'], ['boundary', 'On an axis'],
    ['all', 'Every eligible stock (unconditional)'], ['price_rising', 'Price-only: rising'], ['price_falling', 'Price-only: falling'], ['crowd_added', 'Crowd-only: net added'], ['crowd_cut', 'Crowd-only: net cut'],
    ['coverage_high', 'Coverage-only: ≥ 90% matched'], ['coverage_low', 'Coverage-only: < 90% matched']];
  const store = {};
  const load = (hub) => { const url = (hub || '') + 'data/market/crowd-transitions.json';
    return store[url] || (store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete store[url]; throw e; })); };
  const sel = (id, label, opts, v) => `<label style="display:inline-flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted,#777)">${label}<select data-ctc="${id}">${opts.map(([k, l]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
  const badge = '<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;background:var(--chip,#eef1f4);color:var(--muted,#555)">Descriptive only · not a forecast</span>';

  function matrixTable(A, M, quad) {
    const order = A.definitions.order, word = A.definitions.quadrants;
    let h = `<table class="fv-tbl" style="width:100%;font-size:13px;border-collapse:collapse"><thead><tr><th style="text-align:left">This quarter ↓ · next quarter →</th><th style="text-align:right">Stocks</th>${order.map((q) => `<th style="text-align:right">${esc(word[q])}</th>`).join('')}</tr></thead><tbody>`;
    M.rows.forEach((r) => {
      const hl = quad && r.from === quad;
      h += `<tr${hl ? ' style="outline:2px solid var(--accent,#2a6fb0)"' : ''}><td><b>${esc(word[r.from])}</b></td><td style="text-align:right">${num(r.n)}</td>` + r.cells.map((c, j) => {
        const a = fin(c.p) ? Math.min(0.55, 0.06 + c.p * 0.8) : 0;
        const tip = `${num(c.n)} of ${num(r.n)} stock-quarters went to ${word[order[j]]}` + (fin(c.lo) ? `; Wilson 95%: ${pct(c.lo)}–${pct(c.hi)}` : '') + (fin(c.pair_min) ? `; across quarter pairs: ${pct(c.pair_min)}–${pct(c.pair_max)}` : '');
        return `<td style="text-align:right;background:rgba(42,111,176,${a.toFixed(2)})" title="${esc(tip)}">${r.n ? `<b>${pct(c.p)}</b><br><span class="muted" style="font-size:11px">${fin(c.lo) ? pct(c.lo) + '–' + pct(c.hi) : ''}</span>` : '<span class="muted">—</span>'}</td>`;
      }).join('') + '</tr>';
    });
    return h + '</tbody></table>';
  }

  function postTable(pp) {
    let h = `<table class="fv-tbl" style="width:100%;font-size:13px;margin-top:6px"><thead><tr><th style="text-align:left">Stocks at the decision day</th><th style="text-align:right">n (4w)</th><th style="text-align:right">Median 4w vs SPY</th><th style="text-align:right">Beat SPY, 4w</th><th style="text-align:right">n (12w)</th><th style="text-align:right">Median 12w vs SPY</th><th style="text-align:right">Beat SPY, 12w</th></tr></thead><tbody>`;
    GROUPS.forEach(([k, w], i) => {
      const a = ((pp['4w'] || {}).groups || {})[k], b = ((pp['12w'] || {}).groups || {})[k];
      if (!a && !b) return;
      h += `<tr${i === 5 ? ' style="border-top:2px solid var(--line,#ddd)"' : ''}><td>${esc(w)}</td><td style="text-align:right">${num(a && a.n)}</td><td style="text-align:right">${a ? spct(a.median) : '—'}</td><td style="text-align:right">${a ? pct(a.beat_spy) : '—'}</td><td style="text-align:right">${num(b && b.n)}</td><td style="text-align:right">${b ? spct(b.median) : '—'}</td><td style="text-align:right">${b ? pct(b.beat_spy) : '—'}</td></tr>`;
    });
    h += '</tbody></table>';
    const nc = (h_) => { const c = ((pp[h_] || {}).negative_control) || {}; return fin(c.observed) ? `${h_}: added − cut median gap ${spct(c.observed, 2)}; shuffled 13F side (${num(c.shuffles)} shuffles within each decision day) 90% range ${spct(c.shuffled_p05, 2)} … ${spct(c.shuffled_p95, 2)}, two-sided p ≈ ${num(c.p_two_sided, 3)}` : `${h_}: too few stocks`; };
    h += `<p class="sub" style="margin:4px 0 0">Negative control — ${esc(nc('4w'))} · ${esc(nc('12w'))}. ${num((pp['4w'] || {}).origins)} decision days with a full 4-week window, ${num((pp['12w'] || {}).origins)} with 12 weeks: the dates, not the stocks, are the independent units.</p>`;
    return h;
  }

  function render(el, opt) {
    opt = opt || {};
    el.innerHTML = '<p class="muted">Loading the transition audit…</p>';
    return load(opt.hub).then((A) => {
      if (!A || !A.views) { el.innerHTML = '<p class="muted">The transition audit is not built yet.</p>'; return; }
      const views = Object.keys(VIEW_LABEL).filter((v) => A.views[v]);
      const st = { view: views.includes(opt.view) ? opt.view : views[0], pop: 'covered' };
      function paint() {
        const V = A.views[st.view] || {}, M = V[st.pop];
        let h = `<h4 style="margin:0 0 4px">Quadrant transitions, quarter to quarter ${badge}</h4>`;
        h += `<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin:4px 0 8px">${sel('view', 'Clock', views.map((v) => [v, VIEW_LABEL[v]]), st.view)}${sel('pop', 'Stocks counted', [['covered', 'Covered: ≥ 5 matched holders, ≥ 80% matched'], ['all_eligible', 'Every eligible stock']], st.pop)}</div>`;
        if (!M || !M.stock_quarters) {
          h += `<p class="sub">No stock meets this rule in this view${st.view.endsWith('30d') && st.pop === 'covered' ? ' — at 30 days most large managers have not filed yet, so few stocks have 80% of their holders matched' : ''}.</p>`;
        } else {
          if (opt.quad && opt.ticker) {
            const r = M.rows.find((x) => x.from === opt.quad);
            if (r && r.n) {
              const best = r.cells.map((c, j) => [c, A.definitions.order[j]]).sort((a, b) => (b[0].p || 0) - (a[0].p || 0));
              h += `<p class="sub" style="margin:0 0 6px"><b>${esc(opt.ticker)}</b> is in <b>${esc(A.definitions.quadrants[opt.quad])}</b> in the quarter shown. Of the ${num(r.n)} stock-quarters in that quadrant before (${num(M.quarter_pairs)} quarter pairs), the next quarter they were: ${best.map(([c, q]) => `${esc(A.definitions.quadrants[q])} ${pct(c.p)}${fin(c.lo) ? ` (${pct(c.lo)}–${pct(c.hi)})` : ''}`).join(' · ')}. Peers' history, not a forecast for ${esc(opt.ticker)}.</p>`;
            }
          }
          const table = matrixTable(A, M, opt.quad);
          h += opt.compact ? `<details><summary>The whole table (${esc(VIEW_LABEL[st.view])})</summary>${table}</details>` : table;
          h += `<p class="sub" style="margin:4px 0 0">${num(M.stock_quarters)} stock-quarters, ${num(M.issuers)} stocks, <b>${num(M.quarter_pairs)} quarter pairs</b> — the independent periods. Intervals treat stocks as independent (they are not: stocks in one quarter move together); hover a cell for the range across quarter pairs.</p>`;
          if (M.post_publication && !opt.compact) {
            h += `<h4 style="margin:12px 0 2px">After the deadline: what stocks did next, against SPY</h4><p class="sub" style="margin:0">From the close of each decision day; stocks grouped by the quadrant they were in on what was public then. Compare each quadrant with the baselines below the line — a quadrant is only interesting where it differs from them by more than the shuffled control.</p>` + postTable(M.post_publication);
          }
        }
        if (!opt.compact) {
          const e3 = (A.experiment_3 || {})[st.pop];
          if (e3) {
            const g = (o, k) => (o && o[k] ? `${pct(o[k].beat_spy)} of ${num(o[k].n)}` : '—');
            h += `<h4 style="margin:12px 0 2px">The retrospective picture against what was knowable</h4><p class="sub" style="margin:0">Same quarter (quarter-aligned, not knowable in time): stocks managers net added beat SPY in ${esc(g(e3.same_quarter_retrospective, 'added'))}; net cut: ${esc(g(e3.same_quarter_retrospective, 'cut'))}. After the deadline (public as-of, next 12 weeks): net added ${esc(g(e3.next_12w_after_public, 'added'))}; net cut ${esc(g(e3.next_12w_after_public, 'cut'))}. The gap between the two rows is the part of the attractive picture no one could act on.</p>`;
          }
          const fc = (A.filing_calendar || {}).pooled;
          if (fc) {
            const s = fc.share_by_day;
            h += `<p class="sub" style="margin:8px 0 0"><b>Calendar-only baseline (13F arrival):</b> of ${num(fc.reports)} quarterly reports, ${pct(s['15'])} were filed within 15 days of the quarter end, ${pct(s['30'])} within 30, ${pct(s['46'])} by day 45 (the deadline), ${pct(s['90'])} by day 90. Any model of “when will new 13F buying become public” has to beat this calendar first.</p>`;
          }
          h += `<details style="margin-top:6px"><summary>Definitions and limits</summary><p class="sub">${esc(A.note || '')} X: ${esc(A.definitions.x)}. Y: ${esc(A.definitions.y.quarter_aligned)} (quarter-aligned); ${esc(A.definitions.y.public_knowledge_asof)} (public as-of). On an axis: net 0 or price 0, its own row, never forced into a quadrant. Populations: ${esc(A.definitions.populations.covered)} (covered); ${esc(A.definitions.populations.all_eligible)}. ${esc(A.definitions.industry_benchmark_note)} Prices: ${esc(A.price_basis || '')}. ${esc((A.sample || {}).note || '')} Built ${esc((A.generated_at || '').slice(0, 10))}.</p></details>`;
        }
        el.innerHTML = h;
        el.querySelectorAll('[data-ctc]').forEach((c) => { c.onchange = () => { st[c.dataset.ctc] = c.value; paint(); }; });
      }
      paint();
    }).catch((e) => { el.innerHTML = `<p class="muted">The transition audit could not load (${esc(e.message)}).</p>`; });
  }
  if (typeof window !== 'undefined') window.CrowdTransitions = { render, load };
})();
