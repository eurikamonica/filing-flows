/* The data catalog (#data): every kind of data the site publishes — where it comes from, its one home on the site, the
 * branch or store that keeps it, the workflow that makes it, how often and how fresh it is — measured in the built site
 * at each deploy (scripts/data_catalog.py → data/catalog.json, described by config/data-catalog.json). Below: what is
 * kept more than once, the data no kind describes yet, and identical files published twice. */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const size = (b) => (b == null ? '—' : b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(b >= 1e8 ? 0 : 1)} MB` : b >= 1e3 ? `${Math.round(b / 1e3)} KB` : `${b} B`);
  const count = (n) => Number(n || 0).toLocaleString('en-US');
  const pl = (n, one, many) => `${count(n)} ${n === 1 ? one : many || one + 's'}`;
  const age = (h) => (h == null ? '' : h < 1 ? 'under an hour ago' : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`);
  // how old a kind may be before it is late, from its cadence ("every 15 minutes", "every 3 hours", "daily" …)
  function expected(cadence) {
    const c = String(cadence || '').toLowerCase();
    let m;
    if ((m = /every (\d+) minutes/.exec(c))) return 1;
    if (/hourly/.test(c)) return 1;
    if ((m = /every (\d+) hours?/.exec(c))) return +m[1];
    if (/times a day/.test(c)) return 8;
    if (/daily/.test(c)) return 24;
    if (/weekdays/.test(c)) return 72;
    if (/weekly/.test(c)) return 168;
    if (/twice a month/.test(c)) return 400;
    return null;                                           // monthly, quarterly: no lateness shown
  }
  const late = (k) => { const e = expected(k.cadence); return e != null && k.age_h != null && k.age_h > 3 * e + 6; };
  const PAGE = (p) => {                                  // a page's address as a short label (a company page: its view)
    if (!/^#c-\d+/.test(p)) return p.replace(/^#/, '');
    const v = p.replace(/^#c-\d+-?/, '').replace(/^x-/, '');
    return v ? 'company: ' + v : 'company page';
  };

  function row(k) {
    const homes = (k.homes || []).map((h) => (h.missing ? `<code class="dc-miss" title="not in this build">${esc(h.path)}</code>`
      : h.path.endsWith('/') ? `<code>${esc(h.path)}</code>`                 // a folder: no page of its own to open
        : `<a href="${esc(h.path)}" target="_blank" rel="noopener"><code>${esc(h.path)}</code></a>`)).join(' ');
    const where = homes + (k.remote ? `${homes ? '<br>' : ''}<span class="muted">read from the repository:</span> <code>${esc(k.remote.replace(/^https:\/\/raw\.githubusercontent\.com\/[^/]+\/[^/]+\//, ''))}</code>` : '')
      + (k.published === false ? `<span class="muted">${esc(k.note || 'not published: the collectors’ own store')}</span>` : '');
    const pages = (k.pages || []).map((p) => `<a href="${esc(p)}">${esc(PAGE(p))}</a>`).join(' · ');
    const upd = k.updated ? `<span class="${late(k) ? 'dc-late' : ''}" title="${esc(k.updated)}">${esc(age(k.age_h))}</span>` : '<span class="muted">—</span>';
    return `<tr data-q="${esc([k.id, k.title, k.what, k.source, k.store, k.workflow, k.script, (k.homes || []).map((h) => h.path).join(' ')].join(' ').toLowerCase())}">
      <td class="dc-what"><b>${esc(k.title)}</b><div class="muted">${esc(k.what || '')}</div>${pages ? `<div class="dc-pages">${pages}</div>` : ''}</td>
      <td>${esc(k.source || '')}</td>
      <td class="dc-home">${where || '<span class="muted">—</span>'}</td>
      <td>${esc(k.store || '')}<div class="muted">${esc([k.workflow, k.script].filter(Boolean).join(' · '))}</div><div class="muted">${esc(k.cadence || '')}</div></td>
      <td class="num">${k.files ? `${esc(size(k.bytes))}<div class="muted">${count(k.files)} files</div>` : '<span class="muted">—</span>'}</td>
      <td>${upd}</td></tr>`;
  }

  function html(cat) {
    const kinds = cat.kinds || [], groups = cat.groups || [];
    const total = Object.values(cat.totals || {}).reduce((a, t) => a + (t.bytes || 0), 0);
    const files = Object.values(cat.totals || {}).reduce((a, t) => a + (t.files || 0), 0);
    const lateN = kinds.filter(late).length, missing = kinds.reduce((a, k) => a + (k.homes || []).filter((h) => h.missing).length, 0);
    const d = cat.duplicates || { groups: 0, bytes: 0, top: [] };
    const sections = groups.map(([id, label]) => {
      const list = kinds.filter((k) => k.group === id);
      if (!list.length) return '';
      return `<section class="section dc-group" data-group="${esc(id)}"><div class="section-head"><h2>${esc(label)}</h2><span class="muted">${pl(list.length, 'kind')} · ${esc(size(list.reduce((a, k) => a + (k.bytes || 0), 0)))} on the site</span></div>
        <div class="tbl-wrap"><table class="small dc-table"><thead><tr><th>Data</th><th>Source</th><th>Home on the site</th><th>Kept in · made by · how often</th><th class="num">Size</th><th>Made</th></tr></thead>
        <tbody>${list.map(row).join('')}</tbody></table></div></section>`;
    }).join('');
    const overlaps = (cat.overlaps || []).map((o) => `<div class="dc-overlap"><h3>${esc(o.title)}</h3><p>${esc(o.what)}</p><p class="muted"><b>One copy:</b> ${esc(o.plan)}</p></div>`).join('');
    const unl = cat.unlisted || [];
    return `<div class="page-head"><div class="eyebrow">Method</div><h1>Data catalog</h1>
        <p class="muted" style="max-width:80ch">Every kind of data the site publishes: where it comes from, its one home on the site, the branch or store that keeps it, what makes it, how often, and when it was last made. Measured in the site at each deploy.</p>
        <div class="meta"><span>${pl(kinds.length, 'kind')} of data</span><span>${esc(size(total))} in ${count(files)} files on the site</span>${lateN ? `<span class="dc-late">${lateN} late</span>` : ''}${missing ? `<span class="dc-late">${pl(missing, 'home')} not in this build</span>` : ''}<span>measured ${esc(String(cat.generated_at || '').replace('T', ' ').slice(0, 16))} UTC${cat.commit ? ` · ${esc(cat.commit)}` : ''}</span></div></div>
      <div class="gamma-toolbar"><input id="dc-q" type="search" placeholder="Find data: 13F, prices, ETF, officials…" aria-label="Find data">
        <select id="dc-g" aria-label="Group"><option value="">Every group</option>${groups.map(([id, label]) => `<option value="${esc(id)}">${esc(label)}</option>`).join('')}</select></div>
      ${sections}
      ${overlaps ? `<section class="section"><div class="section-head"><h2>Kept more than once</h2><span class="muted">the same data in two forms or stores, and the one copy each should be</span></div>${overlaps}</section>` : ''}
      <section class="section"><div class="section-head"><h2>Checks</h2><span class="muted">so that nothing on the site goes undescribed or is published twice</span></div>
        <details${unl.length ? '' : ' hidden'}><summary>${pl(cat.unlisted_folders || unl.length, 'folder')} of data no kind describes yet</summary><div class="tbl-wrap"><table class="small"><thead><tr><th>Path</th><th class="num">Files</th><th class="num">Size</th></tr></thead><tbody>
          ${unl.map((r) => `<tr><td><code>${esc(r.path)}</code></td><td class="num">${count(r.files)}</td><td class="num">${esc(size(r.bytes))}</td></tr>`).join('')}</tbody></table></div></details>
        ${(cat.branches && cat.branches.unread && cat.branches.unread.length) ? `<details><summary>${pl(cat.branches.unread.length, 'data branch', 'data branches')} nothing here reads</summary><p>${cat.branches.unread.map((b) => `<code>${esc(b)}</code>`).join(' ')}</p><p class="muted small">Named like a data branch (…-history, …-data, research-…, probes) but no kind above keeps its data there: old probes, or a data set to add to the catalog. ${pl(cat.branches.used.length, 'data branch', 'data branches')} are in use.</p></details>` : ''}
        <details><summary>${pl(d.groups, 'group')} of identical files (${esc(size(d.bytes))} repeated)</summary>${(d.top || []).length ? `<div class="tbl-wrap"><table class="small"><thead><tr><th class="num">Size</th><th class="num">Copies</th><th>Paths</th></tr></thead><tbody>
          ${d.top.map((g) => `<tr><td class="num">${esc(size(g.bytes))}</td><td class="num">${g.copies}</td><td>${g.paths.map((p) => `<code>${esc(p)}</code>`).join('<br>')}</td></tr>`).join('')}</tbody></table></div>` : ''}<p class="muted small">Files of the same size and the same SHA-1 under data/ and disclosures/data/ (4 KB to 16 MB). Unchanged quarters of one record are expected here.</p></details>
      </section>`;
  }

  function css() {
    if (document.getElementById('dc-css')) return;
    const s = document.createElement('style');
    s.id = 'dc-css';
    s.textContent = `.dc-table td{vertical-align:top}.dc-what{min-width:240px;max-width:380px}.dc-home code,.dc-home a{word-break:break-all}
.dc-pages{margin-top:4px;font-size:12px}.dc-pages a{white-space:nowrap}.dc-late{color:var(--neg,#b8432f);font-weight:600}.dc-miss{color:var(--neg,#b8432f);text-decoration:line-through}
.dc-overlap{border-left:3px solid var(--line,#ddd);padding:2px 0 2px 12px;margin:10px 0}.dc-overlap h3{margin:0 0 4px;font-size:15px}.dc-overlap p{margin:2px 0;max-width:90ch}
.dc-group[hidden]{display:none}`;
    document.head.appendChild(s);
  }

  async function render(app, ctx) {
    const here = (ctx && ctx.here) || (() => true);
    if (ctx && ctx.setNav) ctx.setNav('data');
    css();
    app.innerHTML = '<div class="page-head"><h1>Data catalog</h1><p class="muted">Loading…</p></div>';
    let cat;
    try { cat = await ctx.getJSON('catalog.json', true); } catch (e) { cat = null; }
    if (!here()) return;
    if (!cat || !Array.isArray(cat.kinds)) {
      app.innerHTML = '<div class="page-head"><div class="eyebrow">Method</div><h1>Data catalog</h1><p class="muted">The catalog is measured at each deploy of the site; it has not been written yet.</p></div>';
      return;
    }
    app.innerHTML = html(cat);
    const q = app.querySelector('#dc-q'), g = app.querySelector('#dc-g');
    const filter = () => {
      const s = q.value.trim().toLowerCase(), grp = g.value;
      app.querySelectorAll('.dc-group').forEach((sec) => {
        let shown = 0;
        sec.querySelectorAll('tbody tr').forEach((tr) => { const on = !s || tr.dataset.q.includes(s); tr.hidden = !on; shown += on; });
        sec.hidden = (grp && sec.dataset.group !== grp) || !shown;
      });
    };
    q.addEventListener('input', filter);
    g.addEventListener('change', filter);
  }
  global.FFCatalog = { render, _t: { html, expected, late, size, age } };
  if (typeof module !== 'undefined') module.exports = global.FFCatalog;
})(typeof window !== 'undefined' ? window : globalThis);
