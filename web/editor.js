/* Sankey editor and what-if scenario, two opt-in panels under a company's earnings chart (client-side only; the
   default chart and its fixed format never change).
   - Edit this chart: merge sibling lines (e.g. small segments) into one, fold a line into "Other", rename a line,
     change a line's colour role (revenue grey, profit green, cost red, non-cash slate), then export PNG / JPG — the
     export carries the Filing Flows mark like every chart the site draws.
   - What-if scenario: sliders for revenue growth (against this quarter), gross margin, operating expenses as a share
     of revenue and the tax rate → the projected income statement as a Sankey, and earnings per share when the share
     count is on file. Clearly a what-if: nothing here is a forecast.
   Uses window.Sankey (layout, toSVG, exportScene) and FFUx. */
(function (root) {
  'use strict';
  const U = root.FFUx;
  const { esc, t, fin, num, money } = U;
  const ROLES = [['rev', 'Revenue (grey)'], ['profit', 'Profit (green)'], ['cost', 'Cost (red)'], ['noncash', 'Non-cash (slate)']];
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const html = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');   // the spec keeps names HTML-escaped

  // ---------- the graph ----------
  function graph(spec) {
    const ins = new Map(), outs = new Map();
    for (const n of spec.nodes) { ins.set(n.id, []); outs.set(n.id, []); }
    for (const l of spec.links) { if (outs.has(l.s)) outs.get(l.s).push(l); if (ins.has(l.t)) ins.get(l.t).push(l); }
    return { ins, outs };
  }
  // a leaf hangs from one parent: a source with one outflow (a segment) or a sink with one inflow (an expense line)
  function parentOf(spec, id, G) {
    G = G || graph(spec);
    const i = G.ins.get(id) || [], o = G.outs.get(id) || [];
    if (!i.length && o.length === 1) return { id: o[0].t, side: 'in', link: o[0] };
    if (!o.length && i.length === 1) return { id: i[0].s, side: 'out', link: i[0] };
    return null;
  }
  function siblings(spec, id, G) {
    G = G || graph(spec);
    const p = parentOf(spec, id, G);
    if (!p) return [];
    return spec.nodes.filter((n) => n.id !== id && (() => { const q = parentOf(spec, n.id, G); return q && q.id === p.id && q.side === p.side; })()).map((n) => n.id);
  }
  const node = (spec, id) => spec.nodes.find((n) => n.id === id);
  // "$1.2B · 12% of revenue": the share text of a line under its parent, worded like its siblings
  function valLine(spec, n, parent, sibId) {
    const P = node(spec, parent);
    const sib = sibId && node(spec, sibId);
    const sv = sib && (sib.lines || []).find((x) => x[0] === 'val');
    const m = sv && /· [\d.,]+% of (.+)$/.exec(U.dec(sv[1]));
    const of = m ? m[1] : U.dec(P ? P.name : '').toLowerCase();
    const share = P && P.v ? n.v / P.v : null;
    const sp = fin(share) ? (Math.abs(share) < 0.1 ? num(share * 100, 1) : num(share * 100, 0)) + '%' : '';
    return html(`${money(n.v)}${sp ? ` · ${sp} of ${of}` : ''}`);
  }
  const sum = (a, b) => (fin(a) && fin(b) ? a + b : fin(a) ? a : fin(b) ? b : null);

  // merge sibling leaves into one line (named `name`), at the place of the first
  function merge(spec, ids, name) {
    const G = graph(spec);
    const p0 = parentOf(spec, ids[0], G);
    if (!p0 || ids.length < 2) throw new Error('Pick two or more lines that split from (or flow into) the same line');
    for (const id of ids) { const p = parentOf(spec, id, G); if (!p || p.id !== p0.id || p.side !== p0.side) throw new Error('Only lines that hang from the same line can be merged'); }
    const parts = ids.map((id) => node(spec, id)), links = ids.map((id) => parentOf(spec, id, G).link);
    const first = parts[0], id = 'fx:m:' + ids.join('+').replace(/[^A-Za-z0-9:+_-]/g, '').slice(0, 60);
    const m = { id, col: first.col, color: first.color, name: html(name), pos: first.pos, v: parts.reduce((a, n) => a + (n.v || 0), 0),
      q: parts.reduce((a, n) => sum(a, n.q), null), y: parts.reduce((a, n) => sum(a, n.y), null), lines: [['name', html(name)], ['val', '']],
      source: `Merged in the editor: ${parts.map((n) => U.dec(n.name)).join(', ')}.` };
    m.lines[1][1] = valLine(spec, m, p0.id, ids[0]);
    const at = spec.nodes.indexOf(first);
    spec.nodes = spec.nodes.filter((n) => !ids.includes(n.id));
    spec.nodes.splice(Math.min(at, spec.nodes.length), 0, m);
    const L = links[0];
    spec.links = spec.links.filter((l) => !links.includes(l));
    spec.links.push(p0.side === 'in' ? { s: id, t: p0.id, v: m.v, q: m.q, y: m.y, color: L.color } : { s: p0.id, t: id, v: m.v, q: m.q, y: m.y, color: L.color });
    return spec;
  }
  // fold one leaf into its siblings' "Other" line (created when there is none), so the parent still adds up
  function fold(spec, id) {
    const G = graph(spec);
    const p = parentOf(spec, id, G);
    if (!p) throw new Error('Only a line at the edge of the chart can be folded into “Other”');
    const other = siblings(spec, id, G).find((s) => /^other\b/i.test(U.dec(node(spec, s).name)) && parentOf(spec, s, G));
    if (other) return merge(spec, [other, id], U.dec(node(spec, other).name));
    const n = node(spec, id);
    n.name = 'Other'; n.lines = [['name', 'Other'], ['val', '']];
    n.lines[1][1] = valLine(spec, n, p.id, siblings(spec, id, G)[0]);
    n.source = `Folded into “Other” in the editor.`;
    return spec;
  }
  function rename(spec, id, name) {
    const n = node(spec, id);
    if (!n || !name.trim()) return spec;
    n.name = html(name.trim());
    if (n.lines && n.lines[0]) n.lines[0][1] = html(name.trim());
    return spec;
  }
  function recolor(spec, id, role) {
    const n = node(spec, id);
    if (!n || !ROLES.some((r) => r[0] === role)) return spec;
    n.color = role;
    const p = parentOf(spec, id);
    if (p) p.link.color = role;
    return spec;
  }

  // ---------- the what-if ----------
  function baseOf(q) {
    const h = q.headline || {}, v = (id) => { const n = (q.nodes || []).find((x) => x.id === id); return n && fin(n.v) ? +n.v : null; };
    const R = fin(h.revenue) ? +h.revenue : v('revenue');
    if (!fin(R) || R <= 0) return null;
    const COR = v('cor'), GP = v('gp') != null ? v('gp') : fin(COR) ? R - COR : null;
    const OI = v('oi') != null ? v('oi') : fin(h.oi) ? +h.oi : null;
    if (!fin(OI)) return null;
    const OPEX = v('opex') != null ? v('opex') : fin(GP) ? GP - OI : R - OI;
    const PRE = v('pretax');
    const NONOP = v('nonop_in') != null ? v('nonop_in') : v('nonop_out') != null ? -v('nonop_out') : fin(PRE) ? PRE - OI : 0;
    const TAX = v('tax');
    const pre = fin(PRE) ? PRE : OI + NONOP;
    return { R, GP, OPEX, OI, NONOP, PRE: pre, TAX, NET: v('net') != null ? v('net') : fin(h.ni) ? +h.ni : null, hasGP: fin(GP),
      gm: fin(GP) ? GP / R : null, opex: OPEX / R, tax: fin(TAX) && pre > 0 ? Math.min(0.5, Math.max(0, TAX / pre)) : 0.21 };
  }
  function project(B, p) {
    const R = B.R * (1 + p.growth);
    const GP = B.hasGP ? R * p.gm : R;                              // no gross profit line: costs are all operating
    const OPEX = R * p.opex, OI = GP - OPEX, PRE = OI + B.NONOP;
    const TAX = PRE > 0 ? PRE * p.tax : 0, NET = PRE - TAX;
    return { R, COR: R - GP, GP, OPEX, OI, NONOP: B.NONOP, PRE, TAX, NET };
  }
  function scenarioSpec(q, company, P, sh) {
    const N = (id, col, color, name, v, pos, parent, of) => ({ id, col, color, name, pos, v, lines: [[id === 'revenue' ? 'big' : 'name', name], ['val', '']], _p: parent, _of: of });
    const nodes = [N('revenue', 0, 'rev', 'Revenue', P.R, 'above')];
    const links = [];
    const add = (n, s, color) => { nodes.push(n); links.push({ s, t: n.id, v: n.v, color }); };
    let opexFrom = 'revenue', opexCol = 1;
    if (P.COR > 0 && P.GP > 0 && P.GP < P.R) { add(N('cor', 1, 'cost', 'Cost of revenue', P.COR, 'right', 'revenue', 'revenue'), 'revenue', 'cost'); add(N('gp', 1, 'profit', 'Gross profit', P.GP, 'above', 'revenue', 'revenue'), 'revenue', 'profit'); opexFrom = 'gp'; opexCol = 2; }
    const loss = P.OI <= 0 || P.PRE <= 0;
    add(N('opex', opexCol, 'cost', 'Operating expenses', Math.min(P.OPEX, opexFrom === 'gp' ? P.GP : P.R), 'below', opexFrom, opexFrom === 'gp' ? 'gross profit' : 'revenue'), opexFrom, 'cost');
    if (!loss) {
      add(N('oi', opexCol, 'profit', 'Operating profit', P.OI, 'above', opexFrom, opexFrom === 'gp' ? 'gross profit' : 'revenue'), opexFrom, 'profit');
      if (P.NONOP > 0) { nodes.push(N('nonop_in', opexCol + 1, 'profit', 'Other income, net', P.NONOP, 'left', 'pretax', 'pre-tax')); links.push({ s: 'nonop_in', t: 'pretax', v: P.NONOP, color: 'profit' }); }
      if (P.NONOP < 0) add(N('nonop_out', opexCol + 1, 'cost', 'Other expense, net', -P.NONOP, 'right', 'oi', 'operating profit'), 'oi', 'cost');
      nodes.push(N('pretax', opexCol + 1, 'profit', 'Pre-tax earnings', P.PRE, 'above', 'oi', 'operating profit'));
      links.push({ s: 'oi', t: 'pretax', v: Math.min(P.OI, P.PRE), color: 'profit' });
      add(N('net', opexCol + 2, 'profit', 'Net earnings', P.NET, 'above_left', 'pretax', 'pre-tax'), 'pretax', 'profit');
      if (P.TAX > 0) add(N('tax', opexCol + 2, 'cost', 'Income tax', P.TAX, 'below_right', 'pretax', 'pre-tax'), 'pretax', 'cost');
    }
    const byId = new Map(nodes.map((n) => [n.id, n]));
    for (const n of nodes) {
      const par = byId.get(n._p);
      n.lines[1][1] = n.id === 'revenue' ? money(n.v) : `${money(n.v)}${par && par.v ? ` · ${num(n.v / par.v * 100, Math.abs(n.v / par.v) < 0.1 ? 1 : 0)}% of ${n._of}` : ''}`;
      delete n._p; delete n._of;
    }
    return { title: html(`What-if: ${company} — ${U.dec(q.label)} scenario`), subtitle: html('A scenario from the sliders, not a forecast · based on the reported quarter'),
      footer: [html('Scenario built on Filing Flows from the reported quarter: revenue growth, gross margin, operating expenses and tax rate set by the reader. Not a forecast; not investment advice.')],
      kind: 'profit', nodes, links, checks: [], _loss: loss, _eps: sh && fin(P.NET) ? P.NET / sh.v : null };
  }

  // ---------- the panels ----------
  function mount(body, ctx) {
    const S = root.Sankey;
    if (!S || !ctx || !ctx.q || !(ctx.q.nodes || []).length) return;
    const wrap = document.createElement('div');
    wrap.className = 'fx-tools';
    wrap.innerHTML = `<details class="fx-panel" id="fx-edit"><summary>✎ Edit this chart <span class="muted">merge, fold, rename, recolour — then export</span></summary><div class="fx-panel-body"></div></details>
      <details class="fx-panel" id="fx-whatif"><summary>⇢ What-if scenario <span class="muted">sliders on this quarter — not a forecast</span></summary><div class="fx-panel-body"></div></details>`;
    body.appendChild(wrap);
    let edited = null;
    const ed = wrap.querySelector('#fx-edit'), wi = wrap.querySelector('#fx-whatif');
    ed.addEventListener('toggle', () => { if (ed.open && !edited) { edited = clone(ctx.q); drawEditor(); } });
    wi.addEventListener('toggle', () => { if (wi.open && !wi.dataset.on) { wi.dataset.on = '1'; drawWhatIf(); } });

    async function preview(host, spec) {
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      const scene = S.layout(spec, {});
      host.innerHTML = S.toSVG(scene, S.dec(spec.title));
      host.querySelectorAll('.note-mark, .hit').forEach((x) => x.remove());
      return scene;
    }
    function exportBtns(box, getSpec, slug) {
      box.querySelectorAll('[data-fxx]').forEach((b) => b.addEventListener('click', async () => {
        b.disabled = true;
        try { const blob = await S.exportScene(S.layout(getSpec(), {}), b.dataset.fxx); U.download(blob, `${slug}.${b.dataset.fxx}`); } finally { b.disabled = false; }
      }));
    }
    function drawEditor() {
      const box = ed.querySelector('.fx-panel-body'), G = graph(edited);
      const rows = edited.nodes.map((n) => {
        const p = parentOf(edited, n.id, G);
        return `<tr><td>${p ? `<input type="checkbox" data-sel="${esc(n.id)}" aria-label="Select ${t(n.name)}">` : ''}</td>
          <td><input class="input fx-nm" data-nm="${esc(n.id)}" value="${t(n.name)}" aria-label="Name"></td>
          <td><select data-col="${esc(n.id)}" aria-label="Colour">${ROLES.map(([k, l]) => `<option value="${k}"${k === n.color ? ' selected' : ''}>${l}</option>`).join('')}</select></td>
          <td class="num">${money(n.v)}</td><td>${p ? `<button type="button" class="btn fx-sm" data-fold="${esc(n.id)}" title="Fold into its siblings' “Other”">Fold</button>` : ''}</td></tr>`;
      }).join('');
      box.innerHTML = `<p class="muted q-small">Tick lines that split from (or flow into) the same line to merge them; “Fold” moves one edge line into “Other” so every total still adds up. Names and colours apply at once.</p>
        <div class="fx-row"><input class="input" id="fx-mname" placeholder="Name for the merged line" value="Other"><button type="button" class="btn" id="fx-merge">Merge selected</button>
          <button type="button" class="btn" id="fx-reset">Reset</button><span class="fx-sp"></span><button type="button" class="btn" data-fxx="png">PNG ↓</button><button type="button" class="btn" data-fxx="jpg">JPG ↓</button></div>
        <p class="fx-msg" role="status"></p>
        <div class="fx-ed-grid"><div class="tbl-wrap"><table class="fx-ed-tbl"><thead><tr><th></th><th>Line</th><th>Colour</th><th class="num">Value</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div class="sheet fit fx-prev"></div></div>`;
      preview(box.querySelector('.fx-prev'), edited);
      const msg = box.querySelector('.fx-msg');
      const redo = (f) => { try { f(); drawEditor(); } catch (e) { msg.textContent = e.message; } };
      box.querySelector('#fx-merge').addEventListener('click', () => redo(() => merge(edited, [...box.querySelectorAll('[data-sel]:checked')].map((x) => x.dataset.sel), box.querySelector('#fx-mname').value || 'Other')));
      box.querySelector('#fx-reset').addEventListener('click', () => { edited = clone(ctx.q); drawEditor(); });
      box.querySelectorAll('[data-fold]').forEach((b) => b.addEventListener('click', () => redo(() => fold(edited, b.dataset.fold))));
      box.querySelectorAll('[data-nm]').forEach((i) => i.addEventListener('change', () => redo(() => rename(edited, i.dataset.nm, i.value))));
      box.querySelectorAll('[data-col]').forEach((s) => s.addEventListener('change', () => redo(() => recolor(edited, s.dataset.col, s.value))));
      exportBtns(box, () => edited, `${ctx.slug || 'chart'}-edited-sankey`);
    }
    function drawWhatIf() {
      const box = wi.querySelector('.fx-panel-body'), B = baseOf(ctx.q);
      if (!B) { box.innerHTML = '<p class="muted">This chart has no revenue and operating profit lines to build a scenario from.</p>'; return; }
      const sh = U.shares(ctx.c);
      const p = { growth: 0, gm: B.gm == null ? 1 : B.gm, opex: B.opex, tax: B.tax };
      const sl = (k, label, min, max, step, fmt) => `<label class="fx-sl"><span>${label} <b data-out="${k}">${fmt(p[k])}</b></span><input type="range" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${p[k]}"></label>`;
      const pc = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v) * 100, 1)}%`, pp = (v) => `${num(v * 100, 1)}%`;
      box.innerHTML = `<p class="muted q-small">Start: ${t(ctx.q.label)} as reported. Move the sliders; other income stays as reported. A what-if, not a forecast.</p>
        <div class="fx-sliders">${sl('growth', 'Revenue vs this quarter', -0.5, 1, 0.01, pc)}${B.hasGP ? sl('gm', 'Gross margin', 0, 0.95, 0.005, pp) : ''}${sl('opex', 'Operating expenses, % of revenue', 0, 0.95, 0.005, pp)}${sl('tax', 'Tax rate', 0, 0.5, 0.005, pp)}
          <button type="button" class="btn" id="fx-wreset">Back to reported</button><button type="button" class="btn" data-fxx="png">PNG ↓</button></div>
        <div class="fx-ed-grid"><div><table class="fx-ed-tbl" id="fx-wtbl"></table><p class="muted q-small" id="fx-weps"></p></div><div class="sheet fit fx-prev"></div></div>`;
      let spec = null;
      const actual = project(B, { growth: 0, gm: p.gm, opex: B.opex, tax: B.tax });
      const draw = () => {
        const P = project(B, p);
        spec = scenarioSpec(ctx.q, U.dec(ctx.c.profile.name), P, sh);
        preview(box.querySelector('.fx-prev'), spec);
        const rowsT = [['Revenue', 'R'], ['Gross profit', 'GP'], ['Operating expenses', 'OPEX'], ['Operating profit', 'OI'], ['Pre-tax earnings', 'PRE'], ['Income tax', 'TAX'], ['Net earnings', 'NET']]
          .filter(([, k]) => k !== 'GP' || B.hasGP);
        box.querySelector('#fx-wtbl').innerHTML = `<thead><tr><th>Line</th><th class="num">Scenario</th><th class="num">Reported</th></tr></thead><tbody>${rowsT.map(([l, k]) => `<tr><td>${l}</td><td class="num">${money(P[k])}</td><td class="num">${money(actual[k])}</td></tr>`).join('')}</tbody>`;
        box.querySelector('#fx-weps').textContent = (spec._loss ? 'The scenario has an operating or pre-tax loss: the chart shows the costs only. ' : '') +
          (sh ? `Earnings per share ≈ ${U.usd(spec._eps)} on ${num(sh.v / 1e6, 0)}M ${sh.basis} shares (fiscal ${U.dec(sh.label || '')}); reported quarter ≈ ${U.usd(actual.NET / sh.v)}.` : 'Earnings per share need the share count, which is not on file for this company.');
      };
      box.querySelectorAll('[data-k]').forEach((r) => r.addEventListener('input', () => {
        p[r.dataset.k] = +r.value;
        box.querySelector(`[data-out="${r.dataset.k}"]`).textContent = r.dataset.k === 'growth' ? pc(+r.value) : pp(+r.value);
        draw();
      }));
      box.querySelector('#fx-wreset').addEventListener('click', () => { wi.dataset.on = ''; drawWhatIf(); });
      exportBtns(box, () => spec, `${ctx.slug || 'chart'}-what-if-sankey`);
      draw();
    }
  }
  root.FFEditor = { mount, merge, fold, rename, recolor, parentOf, siblings, baseOf, project, scenarioSpec };
  if (typeof module !== 'undefined') module.exports = root.FFEditor;
})(typeof globalThis !== 'undefined' ? globalThis : this);
