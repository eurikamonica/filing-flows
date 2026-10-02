/* Filing Flows: hash-routed single page app over the static JSON written by pipeline/build.py. */
(function () {
  'use strict';
  const S = window.Sankey;
  const BASE = window.FF_DATA || 'data/';
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const app = $('#app');

  // ---------- small utilities ----------
  const cache = new Map();
  function getJSON(p) {
    if (!cache.has(p)) {
      cache.set(p, fetch(BASE + p).then((r) => {
        if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
        return r.json();
      }));
    }
    return cache.get(p);
  }
  const prefs = {
    get(k, d) { try { const v = localStorage.getItem('ff:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ff:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };
  const state = { compare: prefs.get('compare', false), zoom: prefs.get('zoom', 'fit'), charts: [] };
  const t = (s) => S.esc(S.dec(s == null ? '' : s));
  const sign = (x) => (x > 0 ? '+' : x < 0 ? '−' : '');
  const pct = (x, d) => (x == null || isNaN(x) ? '—' : sign(+x.toFixed(d || 0)) + Math.abs(x).toFixed(d || 0) + '%');
  const margin = (x) => (x == null || isNaN(x) ? '—' : (x < 0 ? '\u2212' : '') + Math.abs(x).toFixed(1) + '%');
  const tone = (x) => (x == null ? '' : x > 0.05 ? 'pos' : x < -0.05 ? 'neg' : '');
  function money(v) {
    if (v == null) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e9) return `${s}$${(a / 1e9).toFixed(1)}B`;
    if (a >= 0.95e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
    return `${s}$${(a / 1e3).toFixed(0)}K`;
  }
  function date(s) {
    if (!s) return '—';
    const d = new Date(s.length <= 10 ? s + 'T00:00:00Z' : s);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }
  const calLabel = (cal) => (cal ? `Q${cal.slice(-1)} ${cal.slice(2, 6)}` : '');
  const accession = (url) => { const m = /(\d{10}-\d{2}-\d{6})-index/.exec(url || ''); return m ? m[1] : null; };
  const mdnaItem = (form) => (form === '10-K' ? 'Item 7' : 'Item 2');

  let fontsP = null;
  function fontsReady() {
    if (!fontsP) {
      const loads = document.fonts
        ? ['400 15px "IBM Plex Sans"', '500 14px "IBM Plex Sans"', '600 18px "IBM Plex Sans"'].map((f) => document.fonts.load(f).catch(() => null))
        : [];
      fontsP = Promise.race([Promise.all(loads), new Promise((r) => setTimeout(r, 2500))]);
    }
    return fontsP;
  }
  if (document.fonts && document.fonts.addEventListener) {
    let timer = null;
    document.fonts.addEventListener('loadingdone', () => {
      clearTimeout(timer);
      timer = setTimeout(() => state.charts.forEach((c) => c.redraw()), 60);
    });
  }

  // ---------- export helpers ----------
  // Inside the claude.ai artifact viewer files go through its `downloads` capability (the viewer confirms);
  // everywhere else (GitHub Pages, local) a normal browser download.
  async function saveBlob(blob, name) {
    const host = window.claude;
    if (host && typeof host.use === 'function') {
      const dl = await host.use('downloads').catch(() => null);
      if (dl) {
        try { await dl.save({ filename: name, data: blob }); return 'saved'; } catch (e) { return e && e.code === 'declined' ? 'declined' : 'failed'; }
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 120000);
    return 'saved';
  }
  let toastEl = null;
  function toast(msg, action) {
    if (toastEl) toastEl.remove();
    toastEl = document.createElement('div');
    toastEl.className = 'toast';
    toastEl.setAttribute('role', 'status');
    toastEl.innerHTML = `<span>${t(msg)}</span>${action ? '<button type="button">Preview</button>' : ''}`;
    if (action) $('button', toastEl).addEventListener('click', action);
    document.body.appendChild(toastEl);
    const mine = toastEl;
    setTimeout(() => { if (mine === toastEl) { mine.remove(); toastEl = null; } }, 7000);
  }
  function previewDialog(blob, fmt, name, scene) {
    const src = fmt === 'pdf' ? S.toCanvas(scene, 1).toDataURL('image/png') : URL.createObjectURL(blob);
    const d = document.createElement('div');
    d.className = 'dialog';
    d.innerHTML = `<div class="box" role="dialog" aria-modal="true" aria-label="Exported file">
      <div class="row"><h3>${t(name)}</h3><span class="muted">${(blob.size / 1024).toFixed(0)} KB · ${scene.W * 2} × ${scene.H * 2} px</span></div>
      <img alt="Exported chart" src="${src}">
      <p class="muted">The export contains the chart only; notes from the filing stay on the page. If the download did not start, ${
        fmt === 'pdf' ? 'use the button below.' : 'right-click the image and choose “Save image as”.'}</p>
      <div class="row"><button class="btn primary" type="button" data-dl>Download ${fmt.toUpperCase()}</button><button class="btn" type="button" data-close>Close</button></div>
    </div>`;
    const close = () => { d.remove(); if (fmt !== 'pdf') URL.revokeObjectURL(src); };
    d.addEventListener('click', (e) => { if (e.target === d || e.target.hasAttribute('data-close')) close(); });
    $('[data-dl]', d).addEventListener('click', () => saveBlob(blob, name));
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } });
    document.body.appendChild(d);
  }

  // ---------- the chart component: Sankey + notes panel + view / zoom / export controls ----------
  function chartUI(spec, ctx) {
    const el = document.createElement('section');
    const hasCmp = !!(spec.compare && spec.compare.bullets && spec.compare.bullets.length);
    el.innerHTML = `
      <div class="controls">
        <div class="seg" role="group" aria-label="Chart view">
          <button type="button" data-view="std">Standard</button>
          <button type="button" data-view="cmp" ${hasCmp ? '' : 'disabled title="No previous quarter on file"'}>Compare vs ${hasCmp ? t(spec.compare.vs) : 'previous quarter'}</button>
        </div>
        <div class="seg" role="group" aria-label="Zoom">
          <button type="button" data-zoom="fit">Fit</button>
          <button type="button" data-zoom="full">100%</button>
        </div>
        <div class="export" role="group" aria-label="Export chart"><span>Export</span>
          <button class="btn" type="button" data-x="png">PNG</button>
          <button class="btn" type="button" data-x="jpg">JPG</button>
          <button class="btn" type="button" data-x="pdf">PDF</button>
        </div>
      </div>
      <div class="hintline">${ctx.group ? 'Click a company bar to open its own chart.' :
        '<span class="dot"></span><span>Click any node for what the company wrote about it in the filing. Exports show the chart only.</span>'}</div>
      <div class="stage">
        <div class="sheet"><div class="loading">Drawing…</div></div>
        <aside class="notes" aria-live="polite"></aside>
      </div>`;
    const sheet = $('.sheet', el), notes = $('.notes', el);
    const byId = new Map(spec.nodes.map((n) => [n.id, n]));
    let scene = null, selected = null;
    const cmpOn = () => state.compare && hasCmp;

    function sync() {
      $$('[data-view]', el).forEach((b) => b.classList.toggle('on', (b.dataset.view === 'cmp') === cmpOn()));
      $$('[data-zoom]', el).forEach((b) => b.classList.toggle('on', b.dataset.zoom === state.zoom));
      sheet.classList.toggle('fit', state.zoom === 'fit');
      if (scene) sheet.style.setProperty('--min-w', `${Math.round(scene.W * 0.5)}px`);   // never shrink below half size
    }
    function intro() {
      if (ctx.group) {
        return `<div class="eyebrow">How to read</div>
          <p class="hint"><span>Each grey bar on the left is one company. Click it to open that company’s own chart, with notes from its filing.</span></p>
          <p class="empty">Exports (PNG, JPG, PDF) contain the chart only.</p>`;
      }
      const withNotes = spec.nodes.filter((n) => n.notes).length;
      return `<div class="eyebrow">Notes from the filing</div>
        <p class="hint"><span class="dot"></span><span>Click any node to read what ${t(ctx.company)} wrote about it in this ${t(ctx.form)}. A green dot marks the ${withNotes} line${withNotes === 1 ? '' : 's'} with their own passage in the MD&amp;A.</span></p>
        <p class="empty">Notes stay on the page: exported PNG, JPG and PDF files show the chart only.</p>`;
    }
    function nodeNotes(n) {
      const lines = (n.lines || []).slice(1).map((l) => `<div>${t(l[1])}</div>`).join('') + (cmpOn() && n.cmp ? `<div>${t(n.cmp)}</div>` : '');
      let body;
      const m = /^L:m(\d+)$/.exec(n.id);
      if (ctx.group && m && ctx.companies && ctx.companies[+m[1]]) {
        const co = ctx.companies[+m[1]];
        body = `<p><a href="#c-${co.cik}">Open the ${t(co.ticker)} chart →</a></p>`;
      } else if (ctx.group) {
        body = '<p class="empty">This line is a sum across the companies in the group; it has no filing text of its own.</p>';
      } else if (n.notes && n.notes.length) {
        const same = (h) => S.dec(h).trim().toLowerCase() === S.dec(n.name).trim().toLowerCase();
        body = n.notes.map((x) => `<blockquote>${x.heading && !same(x.heading) ? `<h4>${t(x.heading)}</h4>` : ''}${
          String(x.text).split(/\n\n+/).map((p) => `<p>${t(p)}</p>`).join('')}</blockquote>`).join('') +
          `<div class="src">Quoted verbatim from the ${t(ctx.form)} (${mdnaItem(ctx.form)}, Management’s Discussion and Analysis)${
            ctx.docUrl ? ` · <a href="${t(ctx.docUrl)}" target="_blank" rel="noopener">open filing ↗</a>` : ''}</div>`;
      } else {
        body = `<p class="empty">The ${t(ctx.form)} has no separate MD&amp;A passage about this line.</p>`;
      }
      return `<div class="eyebrow">${ctx.group ? t(ctx.groupName) : t(ctx.company)} · ${t(ctx.label)}</div>
        <div class="k">${t(n.name)}</div><div class="v">${lines}</div>${body}
        <button class="btn" type="button" data-clear>Close note</button>`;
    }
    function select(id) {
      const svg = $('svg', sheet);
      if (!svg) return;
      $$('.node.sel', svg).forEach((g) => g.classList.remove('sel'));
      $$('path.band.on', svg).forEach((p) => p.classList.remove('on'));
      selected = id;
      if (!id || !byId.has(id)) {
        selected = null;
        svg.classList.remove('has-sel');
        notes.classList.remove('open');
        notes.innerHTML = intro();
        return;
      }
      svg.classList.add('has-sel');
      $$('.node', svg).filter((g) => g.dataset.node === id).forEach((g) => g.classList.add('sel'));
      $$('path.band', svg).filter((p) => p.dataset.s === id || p.dataset.t === id).forEach((p) => p.classList.add('on'));
      notes.innerHTML = nodeNotes(byId.get(id));
      notes.classList.add('open');
      notes.scrollTop = 0;
      const clear = $('[data-clear]', notes);
      if (clear) clear.addEventListener('click', () => select(null));
    }
    async function draw() {
      await fontsReady();
      scene = S.layout(spec, { compare: cmpOn() });
      sheet.innerHTML = S.toSVG(scene, S.dec(cmpOn() ? spec.compare.title : spec.title));
      $$('.node', sheet).forEach((g) => {
        const n = byId.get(g.dataset.node);
        g.setAttribute('tabindex', '0');
        g.setAttribute('role', 'button');
        g.setAttribute('aria-label', `${S.dec(n.name)}: ${S.dec((n.lines[1] || [])[1] || '')}`);
      });
      sync();
      select(selected);
    }
    sheet.addEventListener('click', (e) => {
      const g = e.target.closest('[data-node]');
      select(g ? g.dataset.node : null);
    });
    sheet.addEventListener('keydown', (e) => {
      const g = e.target.closest && e.target.closest('[data-node]');
      if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(g.dataset.node); }
    });
    $$('[data-view]', el).forEach((b) => b.addEventListener('click', () => {
      state.compare = b.dataset.view === 'cmp';
      prefs.set('compare', state.compare);
      draw();
      if (ctx.onView) ctx.onView(cmpOn());
    }));
    $$('[data-zoom]', el).forEach((b) => b.addEventListener('click', () => {
      state.zoom = b.dataset.zoom;
      prefs.set('zoom', state.zoom);
      sync();
    }));
    $$('[data-x]', el).forEach((b) => b.addEventListener('click', async () => {
      if (!scene) return;
      const fmt = b.dataset.x;
      b.disabled = true;
      try {
        const blob = await S.exportScene(scene, fmt);
        const name = `${ctx.slug}${cmpOn() ? '-vs-prev' : ''}-sankey.${fmt}`;
        const res = await saveBlob(blob, name);
        toast(res === 'declined' ? 'Export cancelled' : res === 'failed' ? 'Download unavailable here; use Preview to save the image'
          : `Exported ${name}`, () => previewDialog(blob, fmt, name, scene));
      } catch (err) {
        toast(`Export failed: ${err.message}`);
      } finally {
        b.disabled = false;
      }
    }));
    el.redraw = draw;
    el.cmpOn = cmpOn;
    el.className = 'chart-ui';
    el.getScene = () => scene;                       // used by tests/e2e.py to check exports
    state.charts.push(el);
    draw();
    return el;
  }

  // a static, non-interactive chart (thumbnails of earlier quarters)
  async function staticChart(host, spec) {
    await fontsReady();
    host.innerHTML = S.toSVG(S.layout(spec, {}), S.dec(spec.title));
    $$('.note-mark, .hit', host).forEach((x) => x.remove());
  }

  // ---------- pages ----------
  function setNav(page) {
    $$('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === page));
  }
  function row(href, cells) {
    return `<tr data-href="${href}">${cells.join('')}</tr>`;
  }
  function bindRows(root) {
    $$('tr[data-href]', root).forEach((tr) => tr.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      location.hash = tr.dataset.href;
    }));
  }
  function companyCell(c) {
    return `<td><span class="co"><span class="mono">${t(c.ticker || '')}</span><a class="name" href="#c-${c.cik}">${t(c.name)}</a></span></td>`;
  }

  async function home() {
    setNav('home');
    const ix = await getJSON('index.json');
    const site = await getJSON('site.json').catch(() => ({}));
    const sectors = ix.sector_names || {};
    const stars = ix.companies.filter((c) => c.starred);
    const groups = ix.sectors.length + ix.industries.length;
    app.innerHTML = `
      <section class="hero">
        <div class="eyebrow">SEC EDGAR · 10-Q and 10-K · XBRL</div>
        <h1>Every new quarterly report, drawn as one flow from revenue to cash</h1>
        <p>An hourly scan of EDGAR picks up new 10-Q and 10-K filings, reads their XBRL financial data and draws revenue, costs, profit and operating cash flow as a Sankey. Click any node for what the company itself wrote about that line.</p>
        ${ix.demo ? `<p class="note-rule">${t(ix.demo)}</p>` : ''}
        <div class="status"><span>Last update <b>${date(ix.generated)}</b> ${t((ix.generated || '').slice(11, 16))} UTC</span>
          <span><b>${ix.companies.length}</b> companies</span><span><b>${groups}</b> sector and industry charts</span><span>Scans every hour</span></div>
      </section>
      ${stars.length ? `<section class="section">
        <div class="section-head"><h2>Starred</h2><span class="muted">Multi-quarter history${site.repo ? ` · add companies in <a href="https://github.com/${t(site.repo)}/edit/main/config/starred.txt" target="_blank" rel="noopener">config/starred.txt</a>` : ''}</span></div>
        <div class="cards">${stars.map((c) => `<a class="card" href="#c-${c.cik}">
          <div class="t"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span></div>
          <div class="big">${t(c.rev)}</div>
          <div class="n">${t(c.label)} revenue · <span class="${tone(c.yoy)}">${pct(c.yoy)} Y/Y</span> · ${margin(c.om)} op. margin</div></a>`).join('')}</div>
      </section>` : ''}
      <section class="section">
        <div class="section-head"><h2>Latest filings</h2><span class="muted">Newest first</span></div>
        <div class="filters">
          <input id="f-text" type="search" placeholder="Filter by name" aria-label="Filter by name">
          <select id="f-sector" aria-label="Sector"><option value="">All sectors</option>${
            Object.entries(sectors).map(([k, v]) => `<option value="${k}">${t(v)}</option>`).join('')}</select>
          <select id="f-form" aria-label="Form"><option value="">10-Q and 10-K</option><option>10-Q</option><option>10-K</option></select>
        </div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Filed</th><th>Company</th><th>Period</th><th>Form</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th>Sector</th></tr></thead>
          <tbody id="rows"></tbody></table></div>
        <div><button class="btn" id="more" type="button" hidden>Show more</button></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Sectors</h2><span class="muted">Combined Sankeys of every company that reported in the latest calendar quarter</span></div>
        <div class="cards">${ix.sectors.map((s) => `<a class="card" href="#s-${s.id}">
          <div class="t"><span>${t(s.name)}</span></div><div class="n">${s.count} companies · ${calLabel(s.cal)}</div></a>`).join('') ||
          '<p class="muted">Sector charts appear once two companies in a sector have reported for the same quarter.</p>'}</div>
      </section>`;
    let limit = 60;
    const draw = () => {
      const q = $('#f-text').value.trim().toLowerCase(), sec = $('#f-sector').value, form = $('#f-form').value;
      const list = ix.companies.filter((c) => (!q || c.name.toLowerCase().includes(q) || (c.ticker || '').toLowerCase().startsWith(q)) &&
        (!sec || c.sector === sec) && (!form || c.form === form));
      $('#rows').innerHTML = list.slice(0, limit).map((c) => row(`c-${c.cik}`, [
        `<td>${date(c.filed)}</td>`, companyCell(c), `<td>${t(c.label)}</td>`, `<td class="mono">${t(c.form)}</td>`,
        `<td class="num">${t(c.rev)}</td>`, `<td class="num ${tone(c.yoy)}">${pct(c.yoy)}</td>`, `<td class="num">${margin(c.om)}</td>`,
        `<td>${t(sectors[c.sector] || '')}</td>`])).join('') || '<tr><td colspan="8" class="muted">No filings match.</td></tr>';
      $('#more').hidden = list.length <= limit;
      bindRows($('#rows'));
    };
    ['#f-text', '#f-sector', '#f-form'].forEach((s) => $(s).addEventListener('input', () => { limit = 60; draw(); }));
    $('#more').addEventListener('click', () => { limit += 120; draw(); });
    draw();
  }

  async function company(cik, end, all) {
    setNav('');
    const [ix, c] = await Promise.all([getJSON('index.json'), getJSON(`c/${cik}.json`)]);
    const p = c.profile, qs = c.quarters;
    const q = (end && qs.find((x) => x.end === end)) || qs[0];
    const sectors = ix.sector_names || {};
    const ticker = (p.tickers || [])[0] || '';
    const indSlug = String(p.sic || 'none');
    const hasInd = ix.industries.some((i) => i.id === indSlug);
    const hasSec = ix.sectors.some((s) => s.id === p.sector);
    const fye = p.fye ? new Date(Date.UTC(2001, +p.fye.slice(0, 2) - 1, +p.fye.slice(2))).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : null;
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a><span>/</span>${hasSec ? `<a href="#s-${p.sector}">${t(sectors[p.sector])}</a>` : `<span>${t(sectors[p.sector] || 'Other')}</span>`}
          <span>/</span>${hasInd ? `<a href="#i-${indSlug}">${t(p.industry)}</a>` : `<span>${t(p.industry || 'SIC ' + p.sic)}</span>`}</div>
        <h1>${t(p.name)}</h1>
        <div class="meta">
          ${ticker ? `<span class="tag mono">${t(ticker)}</span>` : ''}${(p.exchanges || []).filter(Boolean).slice(0, 1).map((x) => `<span>${t(x)}</span>`).join('')}
          ${c.starred ? '<span class="tag star">★ Starred · multi-quarter history</span>' : ''}
          <span>CIK <span class="mono">${p.cik}</span></span><span>SIC <span class="mono">${t(p.sic)}</span> ${t(p.industry)}</span>
          ${fye ? `<span>Fiscal year ends ${fye}</span>` : ''}${p.category ? `<span>${t(p.category)}</span>` : ''}
        </div>
        ${introHTML(c.intro)}
      </div>
      <div class="pills" role="tablist" aria-label="Quarter">
        ${qs.map((x) => `<a class="pill ${!all && x === q ? 'on' : ''}" href="#c-${cik}-${x.end}">${t(x.label)}</a>`).join('')}
        ${qs.length > 1 ? `<a class="pill ${all ? 'on' : ''}" href="#c-${cik}-all">All ${qs.length} quarters</a>` : ''}
      </div>
      <div id="body"></div>`;
    const body = $('#body');
    if (all) {
      body.innerHTML = `<div class="section"><div class="section-head"><h2>Quarter by quarter</h2>
        <span class="muted">Same format each quarter; open one for notes, comparison and export</span></div>
        <div class="thumbs">${qs.map((x, i) => `<a class="thumb" href="#c-${cik}-${x.end}"><div class="sheet fit" data-i="${i}"><div class="loading">Drawing…</div></div>
        <span><b>${t(x.label)}</b> <span class="muted">· ${t(x.form)} filed ${date(x.filed)} · revenue ${money(x.headline.revenue)} · net ${money(x.headline.ni)}</span></span></a>`).join('')}</div></div>
        ${historyTable(qs, cik)}`;
      $$('.thumb .sheet', body).forEach((h) => staticChart(h, qs[+h.dataset.i]));
      bindRows(body);
      return;
    }
    const ui = chartUI(q, {
      company: S.dec(p.name), form: q.form, label: q.label, docUrl: q.doc_url,
      slug: `${(ticker || p.cik)}-${q.label}`.replace(/\s+/g, '-'),
      onView: () => renderChanges(),
    });
    body.appendChild(ui);
    const acc = accession(q.index_url);
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose">
        <h2>Analysis</h2>
        ${(q.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        <div id="changes"></div>
        <p class="note-rule">Written by fixed rules from the reported figures (no language model): growth, margins, the line that drove the change, and cash conversion.</p>
      </div>
      <div class="prose">
        <h2>Filing</h2>
        <dl class="facts">
          <dt>Form</dt><dd class="mono">${t(q.form)}</dd>
          <dt>Period</dt><dd>${t(q.label)} · quarter ended ${date(q.end)} (calendar ${calLabel(q.cal)})</dd>
          <dt>Filed</dt><dd>${date(q.filed)}</dd>
          ${acc ? `<dt>Accession</dt><dd class="mono">${acc}</dd>` : ''}
          <dt>Documents</dt><dd>${q.doc_url ? `<a href="${t(q.doc_url)}" target="_blank" rel="noopener">Report ↗</a> · ` : ''}${
            q.index_url ? `<a href="${t(q.index_url)}" target="_blank" rel="noopener">Filing index ↗</a>` : `<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${p.cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">EDGAR filings ↗</a>`}</dd>
          <dt>Data</dt><dd>XBRL company facts; revenue lines from the filing’s own XBRL instance</dd>
        </dl>
      </div>`;
    body.appendChild(text);
    if (qs.length > 1) {
      const h = document.createElement('div');
      h.innerHTML = historyTable(qs, cik);
      body.appendChild(h);
      bindRows(h);
    }
    function renderChanges() {
      const box = $('#changes');
      if (!box) return;
      box.innerHTML = q.compare && q.compare.bullets && q.compare.bullets.length
        ? `<h3>What changed vs ${t(q.compare.vs)}</h3><ul class="changes">${q.compare.bullets.map((b) => `<li>${t(b)}</li>`).join('')}</ul>` : '';
    }
    renderChanges();
  }

  function introHTML(intro) {
    if (!intro) return '';
    const text = typeof intro === 'string' ? intro : intro.text;
    if (!text) return '';
    const url = intro.url, filed = intro.filed;
    return `<p class="intro">${t(text)}<span class="src">Quoted verbatim from the company’s 10-K${filed ? ` filed ${date(filed)}` : ''}, Item 1. Business${
      url ? ` · <a href="${t(url)}" target="_blank" rel="noopener">open ↗</a>` : ''}</span></p>`;
  }

  function historyTable(qs, cik) {
    const max = Math.max(...qs.map((x) => x.headline.revenue || 0));
    const ocf = (x) => { const n = x.nodes.find((m) => m.id === 'ocf'); return n ? n.v : null; };
    return `<div class="section"><div class="section-head"><h2>History</h2><span class="muted">${qs.length} quarters on file</span></div>
      <div class="tbl-wrap"><table><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class="num">Revenue</th><th class="num">Y/Y</th>
      <th class="num">Op. margin</th><th class="num">Net earnings</th><th class="num">Operating cash flow</th></tr></thead><tbody>
      ${qs.map((x) => row(`c-${cik}-${x.end}`, [`<td><a href="#c-${cik}-${x.end}">${t(x.label)}</a></td>`, `<td class="mono">${t(x.form)}</td>`,
        `<td>${date(x.filed)}</td>`,
        `<td class="num"><span class="bar-cell"><i style="width:${Math.max(2, (x.headline.revenue / max) * 90).toFixed(0)}px"></i>${money(x.headline.revenue)}</span></td>`,
        `<td class="num ${tone(x.headline.yoy)}">${pct(x.headline.yoy)}</td>`, `<td class="num">${margin(x.headline.om)}</td>`,
        `<td class="num">${money(x.headline.ni)}</td>`, `<td class="num">${money(ocf(x))}</td>`])).join('')}
      </tbody></table></div></div>`;
  }

  async function group(level, id, cal) {
    setNav('sectors');
    const [ix, g] = await Promise.all([getJSON('index.json'), getJSON(`${level}/${id}.json`)]);
    const q = (cal && g.quarters.find((x) => x.cal === cal)) || g.quarters[0];
    const sectors = ix.sector_names || {};
    const byCik = new Map(ix.companies.map((c) => [String(c.cik), c]));
    const secId = level === 'i' ? (ix.industries.find((x) => x.id === id) || {}).sector : id;
    const inds = level === 's' ? ix.industries.filter((x) => x.sector === id) : [];
    const total = q.companies.reduce((s, c) => s + c.revenue, 0);
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a><span>/</span><a href="#sectors">Sectors</a>${
          level === 'i' && secId ? `<span>/</span>${ix.sectors.some((s) => s.id === secId) ? `<a href="#s-${secId}">${t(sectors[secId])}</a>` : t(sectors[secId] || '')}` : ''}</div>
        <h1>${t(g.name)}${level === 's' ? ' sector' : ''}</h1>
        <div class="meta"><span class="tag">${level === 's' ? 'Sector' : 'Industry · SIC ' + t(g.id)}</span>
          <span>${q.count} companies</span><span>Fiscal quarters ending in calendar ${calLabel(q.cal)}</span></div>
      </div>
      <div class="pills" aria-label="Calendar quarter">${g.quarters.map((x) => `<a class="pill ${x === q ? 'on' : ''}" href="#${level}-${id}-${x.cal}">${calLabel(x.cal)}</a>`).join('')}</div>
      <div id="body"></div>`;
    const body = $('#body');
    body.appendChild(chartUI(q, {
      group: true, groupName: S.dec(g.name), label: calLabel(q.cal), companies: q.companies,
      slug: `${id}-${q.cal}`, form: '',
    }));
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose"><h2>Analysis</h2>${(q.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        ${q.compare && q.compare.bullets && q.compare.bullets.length ? `<h3>What changed vs ${t(q.compare.vs)}</h3><ul class="changes">${q.compare.bullets.map((b) => `<li>${t(b)}</li>`).join('')}</ul>` : ''}
        <p class="note-rule">Sum of each company’s fiscal quarter that ends in this calendar quarter. Written by fixed rules from the reported figures.</p></div>
      <div class="prose">${inds.length ? `<h2>Industries</h2><div class="cards">${inds.map((x) => `<a class="card" href="#i-${x.id}"><div class="t"><span>${t(x.name)}</span></div>
        <div class="n">${x.count} companies · ${calLabel(x.cal)}</div></a>`).join('')}</div>` : ''}</div>`;
    body.appendChild(text);
    const tbl = document.createElement('div');
    tbl.className = 'section';
    tbl.innerHTML = `<div class="section-head"><h2>Companies</h2><span class="muted">${calLabel(q.cal)} revenue</span></div>
      <div class="tbl-wrap"><table><thead><tr><th class="num">#</th><th>Company</th><th>Period</th><th class="num">Revenue</th><th class="num">Share</th><th class="num">Y/Y</th><th class="num">Op. margin</th></tr></thead><tbody>
      ${q.companies.map((m, i) => {
        const c = byCik.get(String(m.cik)) || { cik: m.cik, ticker: m.ticker, name: m.ticker };
        const latest = c.cal === q.cal;
        return row(`c-${m.cik}`, [`<td class="num muted">${i + 1}</td>`, companyCell(c), `<td>${latest ? t(c.label) : calLabel(q.cal)}</td>`,
          `<td class="num">${money(m.revenue)}</td>`, `<td class="num">${margin((m.revenue / total) * 100)}</td>`,
          `<td class="num ${latest ? tone(c.yoy) : ''}">${latest ? pct(c.yoy) : '—'}</td>`, `<td class="num">${latest ? margin(c.om) : '—'}</td>`]);
      }).join('')}</tbody></table></div>`;
    body.appendChild(tbl);
    bindRows(tbl);
  }

  async function sectorsPage() {
    setNav('sectors');
    const ix = await getJSON('index.json');
    const names = ix.sector_names || {};
    const counts = {};
    ix.companies.forEach((c) => { counts[c.sector] = (counts[c.sector] || 0) + 1; });
    const have = new Map(ix.sectors.map((s) => [s.id, s]));
    app.innerHTML = `
      <div class="page-head"><div class="eyebrow">Sectors and industries</div><h1>Combined Sankeys by sector and industry</h1>
        <p class="muted" style="max-width:72ch">Companies are grouped by the SIC code on their EDGAR profile. A group chart adds up every company whose fiscal quarter ends in the same calendar quarter; the ten largest appear by name.</p></div>
      ${Object.entries(names).map(([id, name]) => {
        const s = have.get(id), inds = ix.industries.filter((x) => x.sector === id);
        if (!counts[id] && !s) return '';
        return `<section class="section"><div class="section-head"><h2>${s ? `<a href="#s-${id}">${t(name)}</a>` : t(name)}</h2>
          <span class="muted">${counts[id] || 0} companies with filings on record${s ? ` · combined chart for ${calLabel(s.cal)}` : ''}</span></div>
          ${inds.length ? `<div class="cards">${inds.map((x) => `<a class="card" href="#i-${x.id}"><div class="t"><span>${t(x.name)}</span></div>
          <div class="n">SIC ${t(x.id)} · ${x.count} companies · ${calLabel(x.cal)}</div></a>`).join('')}</div>` : ''}</section>`;
      }).join('')}`;
  }

  function methodPage() {
    setNav('method');
    app.innerHTML = `
      <div class="page-head"><div class="eyebrow">Method</div><h1>How each chart is built</h1></div>
      <div class="cols"><div class="prose">
        <h2>Scanning</h2>
        <p>Every hour a scheduled job reads EDGAR’s live feed of new 10-Q and 10-K filings (plus the daily index as a fallback). Each new filing is processed once its XBRL data appears in the SEC’s company-facts API, which can lag the filing by a few hours; until then it waits in a retry queue.</p>
        <h2>Numbers</h2>
        <p>All figures are GAAP values reported in XBRL. A quarter is taken directly when a three-month value exists; otherwise it is year-to-date minus the prior year-to-date, which is how fourth quarters (10-K) and all quarterly cash flows are derived. Revenue lines and segments come from the dimensional facts in the filing’s own XBRL instance and are used only when they add up to total revenue.</p>
        <h2>Layout</h2>
        <p>Revenue lines merge into revenue; profit stays on top and costs peel downward; operating profit plus other income becomes pre-tax earnings, which splits into tax, minority interests and net earnings; operating cash flow is bridged directly from net earnings. Each label shows the amount, its share of the node it splits from or flows into, and the change year over year and quarter over quarter. Loss-making quarters use a funding view: revenue, other income and the net loss together fund all costs.</p>
        <p>The comparison view keeps the same picture and marks the part of every band that grew since the previous quarter as a dark strip. Each label adds Δ = scale + mix: scale is the change explained by the parent node growing, mix the change in the item’s share of its parent.</p>
      </div><div class="prose">
        <h2>Text</h2>
        <p>No language model is used anywhere. Company descriptions are the opening paragraphs of Item 1 (Business) of the latest 10-K. Node notes are the paragraphs under the matching heading in Management’s Discussion and Analysis of the same filing, quoted verbatim. Analysis paragraphs are sentences filled from the numbers by fixed rules.</p>
        <h2>Starred companies</h2>
        <p>Companies listed in <span class="mono">config/starred.txt</span> keep eight quarters of history (others keep three) and are back-filled from their filing history when first added.</p>
        <h2>Sectors</h2>
        <p>Sector and industry charts sum every company whose fiscal quarter ends in the same calendar quarter, grouped by SIC code. Detail lines appear only when every company reports them; comparisons need at least 90% of the revenue to have prior-period data.</p>
        <h2>Limits</h2>
        <p>Banks, insurers and other companies whose statements do not follow the revenue-to-net-income pattern may show coarse charts. Custom XBRL tags outside the standard taxonomy are grouped into “Other operating costs”.</p>
      </div></div>`;
  }

  // ---------- search ----------
  function setupSearch() {
    const input = $('#q'), box = $('#suggest');
    let hi = 0, items = [];
    const close = () => { box.hidden = true; };
    input.addEventListener('input', async () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { close(); return; }
      const ix = await getJSON('index.json');
      items = ix.companies.filter((c) => (c.ticker || '').toLowerCase().startsWith(q) || c.name.toLowerCase().includes(q))
        .sort((a, b) => ((b.ticker || '').toLowerCase() === q) - ((a.ticker || '').toLowerCase() === q) || b.revenue - a.revenue).slice(0, 8);
      hi = 0;
      box.innerHTML = items.map((c, i) => `<a href="#c-${c.cik}" class="${i === hi ? 'hi' : ''}"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span></a>`).join('') ||
        '<div class="muted" style="padding:8px 10px">No company on file yet</div>';
      box.hidden = false;
    });
    input.addEventListener('keydown', (e) => {
      if (box.hidden || !items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        hi = (hi + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
        $$('a', box).forEach((a, i) => a.classList.toggle('hi', i === hi));
      } else if (e.key === 'Enter') {
        location.hash = `c-${items[hi].cik}`;
        input.value = '';
        close();
      } else if (e.key === 'Escape') close();
    });
    box.addEventListener('click', () => { input.value = ''; close(); });
    document.addEventListener('click', (e) => { if (!e.target.closest('.search')) close(); });
  }

  function setupTheme() {
    const saved = prefs.get('theme', null);
    if (saved) document.documentElement.setAttribute('data-theme', saved);
    $('#theme').addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme') ||
        (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      prefs.set('theme', next);
    });
  }

  // ---------- router ----------
  async function route() {
    state.charts = [];
    if (toastEl) { toastEl.remove(); toastEl = null; }
    const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    let m;
    try {
      if ((m = /^c-(\d+)(?:-(\d{4}-\d{2}-\d{2}|all))?$/.exec(h))) await company(m[1], m[2] !== 'all' ? m[2] : null, m[2] === 'all');
      else if ((m = /^([si])-([a-z0-9-]+?)(?:-(CY\d{4}Q\d))?$/.exec(h))) await group(m[1], m[2], m[3]);
      else if (h === 'sectors') await sectorsPage();
      else if (h === 'method') methodPage();
      else await home();
    } catch (err) {
      app.innerHTML = `<div class="page-head"><h1>Not available</h1><p class="muted">${t(err.message)}. The data may not have been generated yet; the scan runs every hour.</p><p><a href="#home">Back to the latest filings</a></p></div>`;
    }
  }
  let lastPage = null;
  window.addEventListener('hashchange', () => {
    const page = location.hash.split('-').slice(0, 2).join('-');
    route().then(() => { if (page !== lastPage) window.scrollTo(0, 0); lastPage = page; });
  });
  setupSearch();
  setupTheme();
  route();
})();
