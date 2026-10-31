/* The Sankey on the search pages (scripts/seo.py, seo_history.py, seo_zh.py, seo_intl.py): every
   <figure class="seo-chart" data-src="…/data/c/<cik>.json" data-label="Q2 FY27" data-compare="q|y"> is drawn from the
   company's own data by sankey.js — that quarter (data-label; the newest without it), and with buttons for the
   comparison variants the data has: against the previous quarter (Q/Q) and the same quarter a year earlier (Y/Y), the
   increases drawn inside each band, with what changed listed under the chart. A figure that cannot be drawn is removed. */
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const MODES = [['', 'This quarter'], ['q', 'vs previous quarter (Q/Q)'], ['y', 'vs a year earlier (Y/Y)']];
  async function one(f) {
    try {
      const d = await (await fetch(f.dataset.src)).json();
      const q = f.dataset.label ? (d.quarters || []).find((x) => x.label === f.dataset.label) : (d.quarters || [])[0];
      if (!q || !q.nodes || !window.Sankey) { f.remove(); return; }
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      const have = MODES.filter(([m]) => !m || (m === 'q' ? q.compare : q.compare_y));
      let mode = have.some(([m]) => m === f.dataset.compare) ? f.dataset.compare : '';
      const bar = document.createElement('div');
      bar.className = 'seo-sk-modes';
      bar.setAttribute('role', 'group');
      bar.setAttribute('aria-label', 'Compare');
      const chart = document.createElement('div'), notes = document.createElement('div');
      notes.className = 'seo-sk-notes';
      const draw = () => {
        const sc = Sankey.layout(q, mode ? { compare: mode, decreases: true } : {});
        chart.innerHTML = Sankey.toSVG(sc, Sankey.dec(q.title));
        chart.querySelectorAll('.note-mark, .hit').forEach((x) => x.remove());
        bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.m === mode)));
        const cmp = mode === 'q' ? q.compare : mode === 'y' ? q.compare_y : null;
        notes.innerHTML = cmp && (cmp.bullets || []).length ? `<h3>${esc(Sankey.dec(cmp.title || 'What changed'))}</h3><ul>${cmp.bullets.slice(0, 6).map((b) => `<li>${esc(Sankey.dec(b))}</li>`).join('')}</ul>` : '';
      };
      bar.innerHTML = have.length > 1 ? have.map(([m, l]) => `<button type="button" data-m="${m}">${esc(l)}</button>`).join('') : '';
      bar.addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) { mode = b.dataset.m; draw(); } });
      f.innerHTML = '';
      f.append(bar, chart, notes);
      draw();
    } catch (err) { f.remove(); }
  }
  function start() { document.querySelectorAll('figure.seo-chart[data-src]').forEach(one); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
