/* Analysis-trap charts on the company pages (c/<slug>/analysis-traps/): each chart is a data contract embedded as
   <script type="application/json" class="trap-chart"> (docs/TRAP_RESEARCH_VOL2.md §37: chart_id, data_kind observed |
   derived | scenario | unknown, unit, period, coverage, sources, not_supported_claims) rendered as an SVG with a table
   beside it, and never a different number from the table. The reader may change inputs: the result is then labelled a
   scenario, and the observed figures stay one click away (Reset). No colour carries meaning alone.
   G01 fcf_bridge: prior FCF → other operating cash → working capital → capex cut → current FCF, with the three readings
   that leave the figures unchanged (expansion completed / maintenance deferred / not known).
   G04 liquidity_matrix: cash + realised FCF + drawable facility − debt due − minimum operating cash, by realisation
   and by facility; a facility counts only when the reader marks it drawable.
   Also: "Record a view" (a reader's judgement, grounds, falsifying condition and next review, kept in this browser only). */
(function (root) {
  'use strict';
  var fin = function (v) { return v != null && isFinite(+v); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  function money(v) {
    if (!fin(v)) return '—';
    if (+v === 0) return '$0';
    var a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 1e12) return s + '$' + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B';
    if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(0) + 'M';
    return s + '$' + (a / 1e3).toFixed(0) + 'K';
  }
  /* ---- G01: the bridge arithmetic (Q01: the steps add to the end; what is not explained stays in `other`) ---- */
  function bridge(v) {
    var prior = +v.prior_fcf, cur = +v.current_fcf, d = cur - prior;
    var capex = fin(v.capex_reduction) ? +v.capex_reduction : 0;
    var wc = fin(v.wc_cash_change) ? +v.wc_cash_change : null;
    var other = d - capex - (wc == null ? 0 : wc);
    return { prior: prior, other: other, wc: wc, capex: capex, current: cur, delta: d, covered: wc != null };
  }
  function bridgeSvg(b, scenario) {
    var steps = [['FCF before', b.prior, 'total'], ['Other operating cash', b.other, 'step'], ['Working capital', b.wc == null ? 0 : b.wc, b.wc == null ? 'missing' : 'step'], ['Capex cut', b.capex, 'step'], ['FCF now', b.current, 'total']];
    var vals = [0, b.prior, b.prior + b.other, b.prior + b.other + (b.wc || 0), b.current];
    var lo = Math.min(0, Math.min.apply(null, vals)), hi = Math.max(0, Math.max.apply(null, vals)) || 1;
    var W = 560, H = 220, L = 10, T = 18, w = (W - 2 * L) / steps.length, sy = function (y) { return T + (hi - y) / (hi - lo) * (H - T - 40); };
    var run = 0, out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="FCF bridge" style="width:100%;max-width:' + W + 'px;height:auto;font:12px system-ui,sans-serif">';
    steps.forEach(function (s, i) {
      var x = L + i * w + 8, bw = w - 16, y0, y1;
      if (s[2] === 'total') { y0 = 0; y1 = s[1]; run = s[1]; } else { y0 = run; y1 = run + s[1]; run = y1; }
      var top = Math.min(sy(y0), sy(y1)), h = Math.max(2, Math.abs(sy(y0) - sy(y1)));
      var fill = s[2] === 'total' ? 'var(--ink-2,#444)' : s[1] >= 0 ? 'var(--accent,#2b6cb0)' : 'var(--neg,#b42318)';
      out += '<rect x="' + x + '" y="' + top + '" width="' + bw + '" height="' + h + '" fill="' + fill + '" fill-opacity="' + (scenario ? 0.45 : 0.85) + '"' + (scenario ? ' stroke="' + fill + '" stroke-dasharray="4 3"' : '') + (s[2] === 'missing' ? ' fill="none" stroke="var(--muted,#888)" stroke-dasharray="2 3"' : '') + '><title>' + esc(s[0]) + ': ' + esc(s[2] === 'missing' ? 'not in the data' : money(s[1])) + '</title></rect>';
      out += '<text x="' + (x + bw / 2) + '" y="' + (top - 4) + '" text-anchor="middle" fill="currentColor">' + esc(s[2] === 'missing' ? 'n/a' : (s[2] === 'step' && s[1] > 0 ? '+' : '') + money(s[1])) + '</text>';
      out += '<text x="' + (x + bw / 2) + '" y="' + (H - 22) + '" text-anchor="middle" fill="var(--muted,#666)">' + esc(s[0]) + '</text>';
    });
    out += '<line x1="' + L + '" x2="' + (W - L) + '" y1="' + sy(0) + '" y2="' + sy(0) + '" stroke="var(--line,#ccc)"/>';
    out += '<text x="' + L + '" y="' + (H - 6) + '" fill="var(--muted,#666)">' + (scenario ? 'Scenario: the reader’s inputs, not the filing' : 'Observed: the cash flow statements') + '</text></svg>';
    return out;
  }
  var READINGS = [
    ['expansion', 'Expansion completed', 'The capex programme ended; maintenance spending is steady and the new capacity is in use. The FCF step is permanent.', 'Completed projects in the 10-K (construction in progress transferred), stable repairs and maintenance, capacity or volume data'],
    ['deferred', 'Maintenance deferred', 'Necessary repairs were pushed out; downtime or asset age is rising. The cash will have to be spent later.', 'Rising maintenance backlog, asset age, unplanned downtime; capex guidance back up'],
    ['unknown', 'Not known', 'Only the cash flow statement is on file. The figures are the same either way; the reading is not.', 'Neither side has evidence yet: the finding stays "to verify", not good and not bad']];
  function renderBridge(el, c) {
    var v = {}; (c.values || []).forEach(function (x) { v[x.name] = x.value; });
    var obs = bridge(v), cur = obs, reading = 'unknown', scenario = false;
    function draw() {
      var b = cur, rows = [['FCF before', b.prior], ['Other operating cash', b.other], ['Working capital', b.covered ? b.wc : null], ['Capex cut', b.capex], ['FCF now', b.current], ['Change in FCF', b.delta]];
      var r = READINGS.filter(function (x) { return x[0] === reading; })[0];
      el.innerHTML = '<p><b>' + esc(c.question) + '</b> <span class="muted">' + esc(c.period_basis || '') + ' · ' + esc(scenario ? 'scenario' : c.data_kind) + (b.covered ? '' : ' · partial: working capital not in the data, its part sits in "other"') + '</span></p>'
        + bridgeSvg(b, scenario)
        + '<div class="tbl-wrap"><table><tbody>' + rows.map(function (x) { return '<tr><td>' + esc(x[0]) + '</td><td class="num">' + (x[1] == null ? 'n/a' : esc(money(x[1]))) + '</td></tr>'; }).join('') + '</tbody></table></div>'
        + '<p class="muted">Check: before + other + working capital + capex cut = now (' + esc(money(b.prior)) + ' + ' + esc(money(b.other)) + ' + ' + esc(money(b.covered ? b.wc : 0)) + ' + ' + esc(money(b.capex)) + ' = ' + esc(money(b.current)) + '). "Other" is what the two named parts do not explain; it is not called an improvement.</p>'
        + '<p><label>Working capital <input type="number" step="1" id="tc-wc" value="' + (b.covered ? Math.round(b.wc / 1e6) : '') + '" style="width:7em"> $M</label> <label>Capex cut <input type="number" step="1" id="tc-cx" value="' + Math.round(b.capex / 1e6) + '" style="width:7em"> $M</label> <button class="btn" id="tc-reset" type="button">Reset to the filing</button></p>'
        + '<p>Same figures, three readings:</p><p class="tc-readings">' + READINGS.map(function (x) { return '<label><input type="radio" name="tc-read" value="' + x[0] + '"' + (x[0] === reading ? ' checked' : '') + '> ' + esc(x[1]) + '</label>'; }).join(' ') + '</p>'
        + '<div class="trap-card"><p><b>' + esc(r[1]) + '</b>: ' + esc(r[2]) + '</p><p class="muted">Evidence that would support it: ' + esc(r[3]) + '.</p><p class="muted">The reading changes nothing in the figures above. A real company gets no reading assigned by the site; the filing decides.</p></div>'
        + (c.sources && c.sources.length ? '<p class="muted">Source: ' + c.sources.map(function (s) { return s.url ? '<a href="' + esc(s.url) + '" rel="nofollow">' + esc(s.period) + '</a>' : esc(s.period); }).join(' · ') + ' · cut-off ' + esc(c.evidence_cutoff || '') + '</p>' : '');
      el.querySelector('#tc-wc').onchange = el.querySelector('#tc-cx').onchange = function () {
        var wc = el.querySelector('#tc-wc').value, cx = el.querySelector('#tc-cx').value;
        var v2 = { prior_fcf: v.prior_fcf, current_fcf: v.current_fcf, capex_reduction: cx === '' ? 0 : +cx * 1e6, wc_cash_change: wc === '' ? null : +wc * 1e6 };
        cur = bridge(v2); scenario = true; draw();
      };
      el.querySelector('#tc-reset').onclick = function () { cur = obs; scenario = false; draw(); };
      Array.prototype.forEach.call(el.querySelectorAll('input[name=tc-read]'), function (i) { i.onchange = function () { reading = i.value; draw(); }; });
    }
    draw();
  }
  /* ---- G04: cash margin at a point (Q04) ---- */
  function margin(cash, fcf, rate, facility, due, minCash) {
    return (+cash || 0) + (fin(fcf) ? Math.max(0, +fcf) * rate : 0) + (+facility || 0) - (+due || 0) - (+minCash || 0);
  }
  function renderLiquidity(el, c) {
    var v = {}; (c.values || []).forEach(function (x) { v[x.name] = x.value; });
    var facility = 0, drawable = false, minCash = 0;
    var rates = fin(v.fcf_ttm) && v.fcf_ttm > 0 ? [0, 0.25, 0.5, 0.75, 1] : [0];
    function draw() {
      var cols = [0].concat(drawable && facility > 0 ? [facility] : []);
      var scenario = drawable || minCash > 0;
      el.innerHTML = '<p><b>' + esc(c.question) + '</b> <span class="muted">' + esc(c.period_basis || '') + ' · ' + esc(scenario ? 'scenario' : c.data_kind) + '</span></p>'
        + '<div class="tbl-wrap"><table><thead><tr><th>FCF realised → facility drawn</th>' + cols.map(function (f) { return '<th class="num">' + (f ? esc(money(f)) : 'none') + '</th>'; }).join('') + '</tr></thead><tbody>'
        + rates.map(function (r) { return '<tr><td>' + (fin(v.fcf_ttm) ? (v.fcf_ttm > 0 ? Math.round(100 * r) + '% of ' + esc(money(v.fcf_ttm)) : 'FCF negative (' + esc(money(v.fcf_ttm)) + '), counted as 0') : 'FCF not in the data, counted as 0') + '</td>' + cols.map(function (f) { var m = margin(v.cash, v.fcf_ttm, r, f, v.due_12m, minCash); return '<td class="num" style="' + (m < 0 ? 'font-weight:600' : '') + '">' + esc(money(m)) + (m < 0 ? ' short' : m === 0 ? ' (at the floor)' : '') + '</td>'; }).join('') + '</tr>'; }).join('')
        + '</tbody></table></div>'
        + '<p class="muted">Margin = cash and investments ' + esc(money(v.cash)) + ' + realised FCF + drawable facility − debt due within a year ' + esc(money(v.due_12m)) + ' − minimum operating cash. Negative is the gap below the floor; zero is the floor reached, not "no risk". The filing does not say when inside the year the debt falls due: a year-end margin can hide a mid-year gap.</p>'
        + '<p><label><input type="checkbox" id="tc-draw"' + (drawable ? ' checked' : '') + '> A credit facility is drawable (not in the data; enter it from the 10-K)</label> <label>Facility <input type="number" step="1" min="0" id="tc-fac" value="' + Math.round(facility / 1e6) + '" style="width:7em"' + (drawable ? '' : ' disabled') + '> $M</label> <label>Minimum operating cash <input type="number" step="1" min="0" id="tc-min" value="' + Math.round(minCash / 1e6) + '" style="width:7em"> $M</label></p>'
        + (c.sources && c.sources.length ? '<p class="muted">Source: ' + c.sources.map(function (s) { return s.url ? '<a href="' + esc(s.url) + '" rel="nofollow">' + esc(s.period) + '</a>' : esc(s.period); }).join(' · ') + ' · cut-off ' + esc(c.evidence_cutoff || '') + '</p>' : '');
      el.querySelector('#tc-draw').onchange = function (e) { drawable = e.target.checked; draw(); };
      el.querySelector('#tc-fac').onchange = function (e) { facility = Math.max(0, +e.target.value || 0) * 1e6; draw(); };
      el.querySelector('#tc-min').onchange = function (e) { minCash = Math.max(0, +e.target.value || 0) * 1e6; draw(); };
    }
    draw();
  }
  /* ---- Record a view: this browser only ---- */
  function renderNote(el, key) {
    var F = [['judgement', 'My reading today'], ['grounds', 'Main grounds'], ['falsified', 'What would change my mind'], ['next', 'Next review (event or date)']];
    var d = {};
    try { d = JSON.parse(root.localStorage.getItem(key) || '{}') || {}; } catch (e) { d = {}; }
    el.innerHTML = '<p><b>Record a view</b> <span class="muted">kept in this browser only; nothing is sent anywhere</span></p>'
      + F.map(function (f) { return '<p><label>' + esc(f[1]) + '<br><textarea data-k="' + f[0] + '" rows="2" style="width:100%;max-width:640px">' + esc(d[f[0]] || '') + '</textarea></label></p>'; }).join('')
      + '<p><button class="btn" type="button" id="tc-save">Save here</button> <button class="btn" type="button" id="tc-clear">Clear</button> <span class="muted" id="tc-saved">' + (d.saved_at ? 'saved ' + esc(d.saved_at) : '') + '</span></p>';
    el.querySelector('#tc-save').onclick = function () {
      var o = { saved_at: new Date().toISOString().slice(0, 16).replace('T', ' ') };
      Array.prototype.forEach.call(el.querySelectorAll('textarea'), function (t) { o[t.getAttribute('data-k')] = t.value; });
      try { root.localStorage.setItem(key, JSON.stringify(o)); el.querySelector('#tc-saved').textContent = 'saved ' + o.saved_at; } catch (e) { el.querySelector('#tc-saved').textContent = 'could not save in this browser'; }
    };
    el.querySelector('#tc-clear').onclick = function () { try { root.localStorage.removeItem(key); } catch (e) { } renderNote(el, key); };
  }
  function init() {
    if (typeof document === 'undefined') return;
    Array.prototype.forEach.call(document.querySelectorAll('script.trap-chart'), function (s) {
      var c; try { c = JSON.parse(s.textContent); } catch (e) { return; }
      var el = document.createElement('div'); el.className = 'trap-chart-box'; s.parentNode.insertBefore(el, s.nextSibling);
      try {
        if (c.chart_id === 'fcf_bridge') renderBridge(el, c);
        else if (c.chart_id === 'liquidity_matrix') renderLiquidity(el, c);
        else el.remove();
      } catch (e) { el.innerHTML = '<p class="muted">The chart could not be drawn; the table above holds the figures.</p>'; }
    });
    var n = document.getElementById('trap-note');
    if (n) renderNote(n, 'ff:trap-note:' + (n.getAttribute('data-key') || ''));
  }
  var api = { bridge: bridge, margin: margin, money: money, READINGS: READINGS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.FFTrapCharts = api;
  if (typeof document !== 'undefined') { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init(); }
})(typeof window !== 'undefined' ? window : globalThis);
