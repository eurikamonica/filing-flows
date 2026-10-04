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
  const FRESH = new Set(['index.json', 'site.json']);          // small files that change: ask the server each time
  function getJSON(p, fresh) {
    if (fresh) cache.delete(p);
    if (!cache.has(p)) {
      const get = FRESH.has(p) || fresh ? fetch(BASE + p, { cache: 'no-cache' }).catch(() => fetch(BASE + p)) : fetch(BASE + p);
      const got = get.then((r) => {
        if (!r.ok) { const err = new Error(`${p}: HTTP ${r.status}`); err.status = r.status; throw err; }
        return r.json();
      });
      got.catch(() => cache.delete(p));                          // a failure is not kept: the next visit asks again
      cache.set(p, got);
    }
    return cache.get(p);
  }
  const prefs = {
    get(k, d) { try { const v = localStorage.getItem('ff:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ff:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };
  const savedCmp = prefs.get('compare', null);                       // 'q' | 'y' | null (older builds stored true)
  const state = { compare: savedCmp === true ? 'q' : savedCmp, zoom: prefs.get('zoom', 'fit'), decreases: prefs.get('decreases', false), charts: [] };
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
  // where node notes come from: the MD&A of a 10-Q/10-K, or the press release of an 8-K
  const noteSource = (form) => (form === '8-K' ? 'the earnings release (8-K, Exhibit 99.1)'
    : `the ${form} (${mdnaItem(form)}, Management’s Discussion and Analysis)`);
  const prelimTag = '<span class="tag prelim" title="Read from the 8-K earnings release; replaced by the 10-Q/10-K when filed">Preliminary · 8-K</span>';
  const finalTag = (rc) => `<span class="tag final" title="${t(releaseCheckText(rc))}">Final · ${rc.ok ? 'confirms' : 'revises'} the 8-K</span>`;
  const listJoin = (a) => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);
  function releaseCheckText(rc) {
    const ok = rc.fields.filter((f) => f.ok).map((f) => f.name.toLowerCase());
    const bad = rc.fields.filter((f) => !f.ok).map((f) => `${f.name.toLowerCase()} ${money(f.release)} in the release, ${money(f.final)} as filed`);
    let out = `Replaces the preliminary chart read from the 8-K earnings release filed ${date(rc.filed)}.`;
    if (ok.length) out += ` ${listJoin(ok).replace(/^./, (x) => x.toUpperCase())} ${bad.length ? 'match' : 'all match the filing'}.`;
    if (bad.length) out += ` Revised: ${bad.join('; ')}.`;
    return out;
  }

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
  async function blobBase64(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let bin = '';
    for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    return btoa(bin);
  }
  const nativeApp = window.FilingFlowsApp || null;               // set when the page runs inside the Android app
  const canShare = !!(nativeApp && typeof nativeApp.shareFile === 'function');
  if (nativeApp) document.documentElement.classList.add('in-app');  // the app has its own tabs and toolbar
  async function saveBlob(blob, name) {
    const native = window.FilingFlowsApp;                       // the Android app saves files itself
    if (native && typeof native.saveFile === 'function') {
      native.saveFile(name, blob.type || 'application/octet-stream', await blobBase64(blob));
      return 'saved';
    }
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
    const has = (c) => !!(c && c.bullets && c.bullets.length);
    const cmpOf = (m) => (m === 'y' ? spec.compare_y : m === 'q' ? spec.compare : null);
    const yearly = spec.period === 'fy' && !ctx.custom;      // a full year has no "previous quarter"
    el.innerHTML = `
      <div class="controls">
        <div class="seg" role="group" aria-label="Chart view">
          <button type="button" data-view="std">Standard</button>
          <button type="button" data-view="q" ${yearly ? 'hidden' : ''} ${has(spec.compare) ? '' : 'disabled title="No previous quarter on file"'}>vs ${has(spec.compare) ? t(spec.compare.vs) : 'previous quarter'}</button>
          <button type="button" data-view="y" ${ctx.custom ? 'hidden' : ''} ${has(spec.compare_y) ? '' : `disabled title="No ${yearly ? 'earlier year' : 'year-ago quarter'} on file"`}>vs ${has(spec.compare_y) ? t(spec.compare_y.vs) : 'year ago'}</button>
        </div>
        <label class="dec-toggle" hidden title="Hatched areas with a dashed outline show what each line lost"><input type="checkbox" data-dec ${state.decreases ? 'checked' : ''}> Show decreases</label>
        <div class="seg" role="group" aria-label="Zoom">
          <button type="button" data-zoom="fit">Fit</button>
          <button type="button" data-zoom="full">100%</button>
        </div>
        <div class="export" role="group" aria-label="Export chart"><span>Export</span>
          <button class="btn" type="button" data-x="png">PNG</button>
          <button class="btn" type="button" data-x="jpg">JPG</button>
          <button class="btn" type="button" data-x="pdf">PDF</button>
          ${canShare ? '<button class="btn" type="button" data-x="share">Share</button>' : ''}
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
    let own = ctx.custom ? 'q' : undefined;                     // a requested comparison opens on its comparison
    const pick = () => (own !== undefined ? own : state.compare);
    const mode = () => (has(cmpOf(pick())) ? pick() : null);   // active comparison, if this chart has it
    if (acct.prefs && typeof acct.prefs.cmp_decreases === 'boolean') state.decreases = acct.prefs.cmp_decreases;
    const cmpOn = () => !!mode();

    function sync() {
      $$('[data-view]', el).forEach((b) => b.classList.toggle('on', b.dataset.view === (mode() || 'std')));
      $('.dec-toggle', el).hidden = !mode();
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
        <p class="hint"><span class="dot"></span><span>Click any node to read what ${t(ctx.company)} wrote about it in this ${ctx.form === '8-K' ? 'earnings release' : t(ctx.form)}. A green dot marks the ${withNotes} line${withNotes === 1 ? '' : 's'} with their own passage in ${ctx.form === '8-K' ? 'the release' : 'the MD&amp;A'}.</span></p>
        <p class="empty">Notes stay on the page: exported PNG, JPG and PDF files show the chart only.</p>`;
    }
    function nodeNotes(n) {
      const lines = (n.lines || []).slice(1).map((l) => `<div>${t(l[1])}</div>`).join('') + (mode() && (mode() === 'y' ? n.cmp_y : n.cmp) ? `<div>${t(mode() === 'y' ? n.cmp_y : n.cmp)}</div>` : '');
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
          `<div class="src">Quoted verbatim from ${t(noteSource(ctx.form))}${
            ctx.docUrl ? ` · <a href="${t(ctx.docUrl)}" target="_blank" rel="noopener">open filing ↗</a>` : ''}</div>`;
      } else {
        body = `<p class="empty">${ctx.form === '8-K' ? 'The earnings release has no passage about this line.' : `The ${t(ctx.form)} has no separate MD&amp;A passage about this line.`}</p>`;
      }
      const trend = ctx.trend ? trendBlock(ctx.trend(n.id), n) : '';
      const source = sourceBlock(n, spec.cite, ctx.cik);                    // where the figure was taken from
      return `<div class="eyebrow">${ctx.group ? t(ctx.groupName) : t(ctx.company)} · ${t(ctx.label)}</div>
        <div class="k">${t(n.name)}</div><div class="v">${lines}</div>${source}${trend}${body}
        <button class="btn" type="button" data-clear>Close note</button>`;
    }
    function select(id) {
      const svg = $('svg', sheet);
      if (!svg) return;
      $$('.node.sel', svg).forEach((g) => g.classList.remove('sel'));
      $$('.band.on', svg).forEach((p) => p.classList.remove('on'));
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
      $$('.band', svg).filter((p) => p.dataset.s === id || p.dataset.t === id).forEach((p) => p.classList.add('on'));
      notes.innerHTML = nodeNotes(byId.get(id));
      wireTrend(notes);
      notes.classList.add('open');
      notes.scrollTop = 0;
      const clear = $('[data-clear]', notes);
      if (clear) clear.addEventListener('click', () => select(null));
    }
    async function draw() {
      await fontsReady();
      scene = S.layout(spec, { compare: mode(), decreases: state.decreases });
      sheet.innerHTML = S.toSVG(scene, S.dec(mode() ? cmpOf(mode()).title : spec.title));
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
      const v = b.dataset.view === 'std' ? null : b.dataset.view;
      if (ctx.custom) own = v;
      else { state.compare = v; prefs.set('compare', v); }
      draw();
      if (ctx.onView) ctx.onView(mode());
    }));
    $('[data-dec]', el).addEventListener('change', (ev) => {
      state.decreases = ev.target.checked;
      prefs.set('decreases', state.decreases);
      draw();
      if (acct.prefs && acct.prefs.cmp_decreases !== state.decreases) {   // signed in: e-mailed charts follow
        const on = state.decreases;
        savePrefs({ cmp_decreases: on })
          .then(() => toast(acct.flash || (on ? 'Your e-mailed comparison charts will show decreases too' : 'Your e-mailed comparison charts will not show decreases')))
          .catch(() => {})
          .finally(() => { acct.flash = null; });
      }
    });
    $$('[data-zoom]', el).forEach((b) => b.addEventListener('click', () => {
      state.zoom = b.dataset.zoom;
      prefs.set('zoom', state.zoom);
      sync();
    }));
    $$('[data-x]', el).forEach((b) => b.addEventListener('click', async () => {
      if (!scene) return;
      const share = b.dataset.x === 'share';
      const fmt = share ? 'png' : b.dataset.x;
      b.disabled = true;
      try {
        const blob = await S.exportScene(scene, fmt);
        const name = `${ctx.slug}${ctx.custom ? (mode() ? `-vs-${ctx.vsSlug}` : '') : mode() === 'q' ? '-vs-prev-quarter' : mode() === 'y' ? (yearly ? '-vs-prior-year' : '-vs-year-ago') : ''}-sankey.${fmt}`;
        if (share) {                                               // Android share sheet (X, messages, mail …)
          nativeApp.shareFile(name, 'image/png', await blobBase64(blob));
          return;
        }
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
    el.mode = mode;
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
    const forms = new Set(prefs.get('forms', ['10-Q', '10-K', '8-K']));
    const ix = await getJSON('index.json');
    const site = await getJSON('site.json').catch(() => ({}));
    const sectors = ix.sector_names || {};
    const stars = ix.companies.filter((c) => c.starred);
    const groups = ix.sectors.length + ix.industries.length;
    app.innerHTML = `
      <section class="hero">
        <div class="eyebrow">SEC EDGAR · 10-Q, 10-K and 8-K earnings releases</div>
        <h1>Every new quarterly report, drawn as one flow from revenue to cash</h1>
        <p>A scan of EDGAR every 15 minutes picks up new 10-Q and 10-K filings and earnings releases (8-K), reads their financial statements and draws revenue, costs, profit and operating cash flow as a Sankey. Click any node for what the company itself wrote about that line.</p>
        ${ix.demo ? `<p class="note-rule">${t(ix.demo)}</p>` : ''}
        <div class="status"><span>Last update <b>${date(ix.generated)}</b> ${t((ix.generated || '').slice(11, 16))} UTC</span>
          <span><b>${ix.companies.length}</b> companies</span><span><b>${groups}</b> sector and industry charts</span><span>Scans every 15 minutes</span></div>
      </section>
      ${stars.length ? `<section class="section">
        <div class="section-head"><h2>Starred</h2><span class="muted">Multi-quarter history${site.repo ? ` · add companies in <a href="https://github.com/${t(site.repo)}/edit/main/config/starred.txt" target="_blank" rel="noopener">config/starred.txt</a>` : ''}</span></div>
        <div class="cards">${stars.map((c) => `<a class="card" href="#c-${c.cik}">
          <div class="t"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span></div>
          <div class="big">${t(c.rev)}</div>
          <div class="n">${t(c.label)} revenue · <span class="${tone(c.yoy)}">${pct(c.yoy)} Y/Y</span> · ${margin(c.om)} op. margin</div></a>`).join('')}</div>
      </section>` : ''}
      <section class="cta" id="cta" hidden>
        <div><h2>Get new charts by e-mail</h2>
          <p class="muted">Pick companies or sectors; a daily report arrives every morning at 8:00 your time with each new filing’s chart and analysis (or get each one as soon as it is out). No password: sign in with a code sent to your inbox.</p></div>
        <form class="cta-form" id="cta-form"><input type="email" required placeholder="you@example.com" aria-label="E-mail address" autocomplete="email">
          <button class="btn primary" type="submit">Get alerts</button></form>
      </section>
      <section class="section daily" id="daily" hidden></section>
      <section class="section">
        <div class="section-head"><h2>Latest filings</h2><span class="muted">Newest first</span></div>
        <div class="filters">
          <input id="f-text" type="search" placeholder="Filter by name" aria-label="Filter by name">
          <select id="f-sector" aria-label="Sector"><option value="">All sectors</option>${
            Object.entries(sectors).map(([k, v]) => `<option value="${k}">${t(v)}</option>`).join('')}</select>
          <fieldset class="checks" id="f-forms"><legend>Form</legend>${['10-Q', '10-K', '8-K'].map((f) =>
            `<label><input type="checkbox" value="${f}" ${forms.has(f) ? 'checked' : ''}> ${f}${f === '8-K' ? ' <span class="muted">earnings release</span>' : ''}</label>`).join('')}</fieldset>
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
    $('#cta-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      prefs.set('signin-email', $('#cta-form input').value.trim());
      location.hash = 'account';
    });
    Promise.all([sb(), currentUser()]).then(([c, user]) => {        // only when accounts are switched on
      const box = $('#cta');
      if (!box || !c) return;
      if (user) {
        box.querySelector('h2').textContent = 'Your alerts';
        box.querySelector('p').textContent = `Signed in as ${user.email}. Choose companies, sectors and how often.`;
        box.querySelector('form').outerHTML = '<a class="btn primary" href="#account">Manage alerts</a>';
      }
      box.hidden = false;
    }).catch(() => {});
    dailyPanel($('#daily'), ix).catch((e) => console.warn('daily report panel:', e.message));
    let limit = 60;
    const draw = () => {
      const q = $('#f-text').value.trim().toLowerCase(), sec = $('#f-sector').value;
      const list = ix.companies.filter((c) => (!q || c.name.toLowerCase().includes(q) || (c.ticker || '').toLowerCase().startsWith(q)) &&
        (!sec || c.sector === sec) && forms.has(c.form));
      $('#rows').innerHTML = list.slice(0, limit).map((c) => row(`c-${c.cik}`, [
        `<td>${date(c.filed)}</td>`, companyCell(c), `<td>${t(c.label)}</td>`, `<td class="mono">${t(c.form)}${c.prelim ? ' <span class="tag prelim">prelim</span>' : ''}</td>`,
        `<td class="num">${t(c.rev)}</td>`, `<td class="num ${tone(c.yoy)}">${pct(c.yoy)}</td>`, `<td class="num">${margin(c.om)}</td>`,
        `<td>${t(sectors[c.sector] || '')}</td>`])).join('') || '<tr><td colspan="8" class="muted">No filings match.</td></tr>';
      $('#more').hidden = list.length <= limit;
      bindRows($('#rows'));
    };
    ['#f-text', '#f-sector'].forEach((s) => $(s).addEventListener('input', () => { limit = 60; draw(); }));
    $$('#f-forms input').forEach((box) => box.addEventListener('change', () => {
      forms.clear();
      $$('#f-forms input:checked').forEach((x) => forms.add(x.value));
      prefs.set('forms', [...forms]);
      limit = 60;
      draw();
    }));
    $('#more').addEventListener('click', () => { limit += 120; draw(); });
    draw();
  }

  async function company(cik, end, all, opt) {
    opt = opt || {};
    setNav('');
    const [ix, site] = await Promise.all([getJSON('index.json'), getJSON('site.json').catch(() => ({}))]);
    let c;
    try {
      c = await getJSON(`c/${cik}.json`);
    } catch (err) {
      if (err.status === 404) return missingCompany(cik);          // found by the search, not drawn yet
      throw err;
    }
    const p = c.profile, qs = c.quarters, ys = c.years || [];
    const fy = !!opt.fy && ys.length > 0;                           // a full fiscal year (10-K)
    const cmpId = opt.cmp || null;                                  // a comparison this reader asked for
    if (cmpId) all = false;
    const q = fy ? (ys.find((x) => x.end === end) || ys[0]) : ((end && qs.find((x) => x.end === end)) || qs[0]);
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
          ${ticker ? `<button class="btn follow" type="button" hidden data-follow="ticker:${t(ticker)}">☆ Follow</button>` : ''}
          ${cmpId ? '' : `<button class="btn send" type="button" hidden data-send="${p.cik}|${(all ? qs : [q]).map((x) => x.end).join(',')}|${fy ? 'fy' : 'q'}"
            title="Sent to the address you signed in with: chart, analysis and what changed">✉ Email me ${all ? `all ${qs.length} quarters` : t(q.label) + (fy ? ' full year' : '')}</button>`}
          ${c.starred ? '<span class="tag star">★ Starred · multi-quarter history</span>' : ''}${!all && !cmpId && q.form === '8-K' ? prelimTag : ''}${!all && !cmpId && q.release_check ? finalTag(q.release_check) : ''}
          <span>CIK <span class="mono">${p.cik}</span></span><span>SIC <span class="mono">${t(p.sic)}</span> ${t(p.industry)}</span>
          ${fye ? `<span>Fiscal year ends ${fye}</span>` : ''}${p.category ? `<span>${t(p.category)}</span>` : ''}
        </div>
        ${introHTML(c.intro)}
      </div>
      <div class="pills" role="tablist" aria-label="Period">
        ${qs.map((x) => `<a class="pill ${!all && !fy && !cmpId && x === q ? 'on' : ''}" href="#c-${cik}-${x.end}">${t(x.label)}${x.form === '8-K' ? ' · 8-K' : ''}</a>`).join('')}
        ${ys.map((x) => `<a class="pill year ${fy && x === q ? 'on' : ''}" href="#c-${cik}-fy-${x.end}" title="The full fiscal year, from the 10-K">${t(x.label)} · full year</a>`).join('')}
        ${qs.length > 1 ? `<a class="pill ${all ? 'on' : ''}" href="#c-${cik}-all">All ${qs.length} quarters</a>` : ''}
        <button class="pill cmp ${cmpId ? 'on' : ''}" type="button" id="cmp-open" hidden aria-expanded="false" aria-controls="cmp-panel">⇄ Compare any two</button>
      </div>
      <section class="section cmp-panel" id="cmp-panel" hidden></section>
      <div id="body"></div>`;
    const body = $('#body');
    initCompare(c, cik);
    if (cmpId) {
      showComparison(body, c, cmpId, ticker);
      return;
    }
    if (all) {
      body.innerHTML = `<div class="section"><div class="section-head"><h2>Trend</h2>
        <span class="muted">Revenue, operating profit, net earnings and operating cash flow; each row to its own scale</span></div>
        <div class="sheet fit" id="trend"></div></div>
        <div class="section"><div class="section-head"><h2>Quarter by quarter</h2>
        <span class="muted">Same format each quarter; open one for notes, comparison and export</span></div>
        <div class="thumbs">${qs.map((x, i) => `<a class="thumb" href="#c-${cik}-${x.end}"><div class="sheet fit" data-i="${i}"><div class="loading">Drawing…</div></div>
        <span><b>${t(x.label)}</b> <span class="muted">· ${t(x.form)} filed ${date(x.filed)} · revenue ${money(x.headline.revenue)} · net ${money(x.headline.ni)}</span></span></a>`).join('')}</div></div>
        ${historyTable(qs, cik)}`;
      fontsReady().then(() => {
        const h = $('#trend');
        if (!h) return;
        const sc = S.history(c);
        h.style.maxWidth = `${sc.W}px`;                          // a few quarters make a narrow chart: never blown up
        h.innerHTML = S.toSVG(sc, `${S.dec(p.name)} quarter by quarter`);
      });
      $$('.thumb .sheet', body).forEach((h) => staticChart(h, qs[+h.dataset.i]));
      bindRows(body);
      return;
    }
    const ui = chartUI(q, {
      company: S.dec(p.name), form: q.form, label: q.label, docUrl: q.doc_url,
      slug: `${(ticker || p.cik)}-${q.label}`.replace(/\s+/g, '-'),
      onView: () => renderChanges(),
      trend: (id) => trendSeries(fy ? ys : qs, q, id, fy), cik: p.cik,
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
          <dt>Form</dt><dd><span class="mono">${t(q.form)}</span>${q.form === '8-K' ? ' · Item 2.02 earnings release, preliminary until the 10-Q/10-K is filed' : ''}</dd>
          <dt>Period</dt><dd>${fy ? `${t(q.label)} · fiscal year ended ${date(q.end)}` : `${t(q.label)} · quarter ended ${date(q.end)} (calendar ${calLabel(q.cal)})`}</dd>
          <dt>Filed</dt><dd>${date(q.filed)}</dd>
          ${q.release_check ? `<dt>Earnings release</dt><dd>${t(releaseCheckText(q.release_check))}</dd>` : ''}
          ${acc ? `<dt>Accession</dt><dd class="mono">${acc}</dd>` : ''}
          <dt>Documents</dt><dd>${q.doc_url ? `<a href="${t(q.doc_url)}" target="_blank" rel="noopener">${q.form === '8-K' ? 'Press release' : 'Report'} ↗</a> · ` : ''}${
            q.index_url ? `<a href="${t(q.index_url)}" target="_blank" rel="noopener">Filing index ↗</a>` : `<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${p.cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">EDGAR filings ↗</a>`}</dd>
          <dt>Data</dt><dd>${q.form === '8-K' ? 'This quarter read from the tables in the press release (Exhibit 99.1); earlier quarters from XBRL company facts'
            : fy ? 'Full-year values as reported in the 10-K (XBRL company facts); revenue lines from the filing’s own XBRL instance'
            : 'XBRL company facts; revenue lines from the filing’s own XBRL instance'}</dd>
        </dl>
      </div>`;
    body.appendChild(text);
    if (prefs.get('owner', false) && !fy) {               // owner tool (see #owner): only for the verified owner
      ownerVerified().then(async (ok) => {
        const osets = ok ? await ownerSettings() : null;
        const thread = ok && text.isConnected ? threadSection(q, p, site.repo, osets) : null;
        if (thread) text.after(thread);
      });
    }
    if (qs.length > 1) {
      const h = document.createElement('div');
      h.innerHTML = historyTable(qs, cik);
      body.appendChild(h);
      bindRows(h);
    }
    function renderChanges() {
      const box = $('#changes');
      if (!box) return;
      box.innerHTML = changesHTML(q);
    }
    renderChanges();
  }

  // the ready-to-post X thread for a quarter (the same text the e-mails carry): which filing, what each image shows (with
  // Save buttons), every post with its role and a Copy button, and "Email me this thread"
  const ROLES = { headline: 'Headline and charts', business: 'What the company does', about: 'The company in its own words',
    analysis: 'Analysis', quote: 'From the filing', source: 'Source' };
  function threadSection(q, p, repo, osets) {
    const posts = q.x_thread || [];
    if (!posts.length) return null;
    const ticker = (p.tickers || [])[0] || String(p.cik);
    const intent = 'https://x.com/intent/post?text=' + encodeURIComponent(posts[0].text);
    const direct = !!acct.client && (!osets || osets.thread_direct !== false);   // straight to the inbox (owner setting)
    let mail = '';
    if (direct) mail = '<button class="btn primary" type="button" id="thread-mail">✉ Email me this thread</button>';
    else if (repo) {
      const title = `Email thread: ${ticker} ${S.dec(q.label)} [${p.cik} ${q.end}]`;
      const bodyTxt = 'Sends this quarter’s X thread and its charts to the inbox in the MAIL_USERNAME (or MAIL_TO) secret. ' +
        'Press Create; the issue closes itself once the e-mail has gone out (about two minutes).';
      mail = `<a class="btn primary" target="_blank" rel="noopener" href="https://github.com/${t(repo)}/issues/new?title=${
        encodeURIComponent(title)}&body=${encodeURIComponent(bodyTxt)}">Email me this thread</a>`;
    }
    const acc = accession(q.index_url);
    const form = q.form === '8-K' ? 'Earnings release (8-K)' : q.form;
    const vs = q.compare_y && q.compare_y.vs;
    const charts = [['std', 'Chart 1', `${S.dec(q.label)}: where the revenue went, from costs to profit and operating cash flow`]]
      .concat(vs ? [['y', 'Chart 2', `the same flows compared with ${S.dec(vs)}; a dark strip inside a band is growth`]] : []);
    const sec = document.createElement('section');
    sec.className = 'section';
    sec.id = 'thread';
    sec.innerHTML = `
      <div class="section-head"><h2>X thread</h2><span class="muted">Ready to post by hand · ${posts.length} posts · every post fits 280 characters</span></div>
      <dl class="facts thread-info">
        <dt>Filing</dt><dd>${t(form)} filed ${date(q.filed)} · quarter ended ${date(q.end)}${acc ? ` · <span class="mono">${acc}</span>` : ''}</dd>
        <dt>Images for post 1</dt><dd>${charts.map(([m, name, cap]) => `<div class="thread-img"><span><b>${name}</b> · ${t(cap)}</span>
          <button class="btn small" type="button" data-img="${m}">Save PNG</button></div>`).join('')}</dd>
      </dl>
      <div class="thread-actions">${mail}<a class="btn" target="_blank" rel="noopener" href="${t(intent)}">Open post 1 in X</a>
        <button class="btn" type="button" data-copy-all>Copy all</button></div>
      ${mail ? `<p class="note-rule" id="thread-mail-note">${direct ? 'Sends the thread with both chart PNGs attached to the address you signed in with, usually within two minutes.'
        : '“Email me” opens GitHub with the request filled in: press Create and the thread arrives with both charts attached. Change this in Owner tools.'}</p>` : ''}
      <ol class="thread">${posts.map((x, i) => `<li>
        <div class="thread-meta"><span>Post ${i + 1} of ${posts.length}${ROLES[x.role] ? ` · <b>${ROLES[x.role]}</b>` : ''} · ${x.len}/280${i ? ' · reply to the post above' : ' · attach the charts'}</span>
          <button class="btn small" type="button" data-copy="${i}">Copy</button></div>
        <pre>${t(x.text)}</pre></li>`).join('')}</ol>`;
    const copy = async (txt, btn) => {
      try {
        const native = window.FilingFlowsApp;
        if (native && typeof native.copyText === 'function') native.copyText(txt);
        else await navigator.clipboard.writeText(txt);
        btn.textContent = 'Copied';
      } catch (e) {
        const pre = btn.closest('li') ? $('pre', btn.closest('li')) : $('pre', sec);
        const r = document.createRange();
        r.selectNodeContents(pre);
        const sel = getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        btn.textContent = 'Selected: press Ctrl+C';
      }
      setTimeout(() => { btn.textContent = btn.hasAttribute('data-copy-all') ? 'Copy all' : 'Copy'; }, 1800);
    };
    $$('[data-copy]', sec).forEach((b) => b.addEventListener('click', () => copy(posts[+b.dataset.copy].text, b)));
    $('[data-copy-all]', sec).addEventListener('click', (ev) => copy(posts.map((x) => x.text).join('\n\n---\n\n'), ev.currentTarget));
    $$('[data-img]', sec).forEach((b) => b.addEventListener('click', async () => {
      const m = b.dataset.img === 'y' ? 'y' : null;
      b.disabled = true;
      try {
        await fontsReady();
        const blob = await S.exportScene(S.layout(q, { compare: m, decreases: state.decreases }), 'png');
        const name = `${ticker}-${S.dec(q.label)}-${m ? '2-vs-' + S.dec(vs) : '1-chart'}.png`.replace(/[^A-Za-z0-9.]+/g, '-');
        const res = await saveBlob(blob, name);
        toast(res === 'saved' ? `Saved ${name}` : 'Download unavailable here');
      } catch (err) {
        toast(`Could not save: ${err.message}`);
      } finally {
        b.disabled = false;
      }
    }));
    const btn = $('#thread-mail', sec);
    if (btn) btn.addEventListener('click', async () => {
      btn.disabled = true;
      toast(await askFor({ cik: +p.cik, period_end: q.end, kind: 'thread' }, 'Thread'));
      btn.disabled = false;
    });
    return sec;
  }

  // "what changed" bullets vs the previous quarter and vs the year-ago quarter
  function changesHTML(q) {
    return [q.compare, q.compare_y].filter((c) => c && c.bullets && c.bullets.length)
      .map((c) => `<h3>What changed vs ${t(c.vs)}</h3><ul class="changes">${c.bullets.map((b) => `<li>${t(b)}</li>`).join('')}</ul>`).join('');
  }

  function introHTML(intro) {
    if (!intro) return '';
    const text = typeof intro === 'string' ? intro : intro.text;
    if (!text) return '';
    const url = intro.url, filed = intro.filed, when = filed ? ` filed ${date(filed)}` : '';
    const where = intro.source === '8-K' ? `earnings release (8-K)${when}, “About” section`
      : intro.source === '10-Q' ? `10-Q${when}, Note 1 to the financial statements (no 10-K on file yet)`
      : `10-K${when}, Item 1. Business`;
    return `<p class="intro">${t(text)}<span class="src">Quoted verbatim from the company’s ${where}${
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

  // ---------- where a figure comes from: the line or calculation, the filing it is in, links to check it ----------
  function sourceBlock(n, cite, cik) {
    if (!n.source && !cite) return '';
    const links = [];
    if (cite && cite.doc) links.push([cite.doc, /Exhibit 99/.test(cite.text) ? 'Press release' : 'The filing']);
    if (cite && cite.ix) links.push([cite.ix, 'Inline XBRL viewer']);
    const tag = /^us-gaap:(\w+)$/.exec(n.tag || '');
    if (tag && cik) links.push([`https://data.sec.gov/api/xbrl/companyconcept/CIK${String(cik).padStart(10, '0')}/us-gaap/${tag[1]}.json`,
      `XBRL data for ${tag[1]}`]);
    if (cite && cite.index) links.push([cite.index, 'Filing index']);
    return `<div class="node-src"><div class="eyebrow">Source</div>
      ${n.source ? `<p>${t(n.source)}</p>` : ''}
      ${cite ? `<p class="cite">${t(cite.text)}.</p>` : ''}
      ${links.length ? `<p class="links">${links.map(([u, l]) => `<a href="${t(u)}" target="_blank" rel="noopener">${t(l)} ↗</a>`).join(' · ')}</p>` : ''}</div>`;
  }

  // ---------- a node's last five quarters (or fiscal years), in its note ----------
  // Two small panels on one time axis (never two scales on one axis): the amount as columns, and its change against a
  // year earlier as a line. The current period is drawn at full strength; a readout above names the hovered period.
  const TREND_N = 5;
  function nodeAt(spec, id) {
    const find = (k) => (spec.nodes || []).find((x) => x.id === k);
    const own = find(id);
    if (own) return { v: own.v, y: own.y, q: own.q };
    if (id === 'fcf' || id === 'fcf_neg') {                       // free cash flow changes sides when it turns negative
      const o = find('ocf'), c = find('capex');
      if (!o || !c || o.v == null || c.v == null) return null;
      const sg = id === 'fcf' ? 1 : -1, d = (k) => (o[k] != null && c[k] != null ? sg * (o[k] - c[k]) : null);
      return { v: sg * (o.v - c.v), y: d('y'), q: d('q') };
    }
    return null;
  }
  function trendSeries(specs, cur, id, years) {
    const keep = specs.filter((x) => x.end <= cur.end).slice(0, TREND_N).reverse();
    const chg = (v, b) => (v != null && b != null && v > 0 && b > 0 ? (v / b - 1) * 100 : null);   // n/m when ≤ 0
    const pts = keep.map((x) => {
      const a = nodeAt(x, id) || {};
      return { label: x.label, end: x.end, cur: x.end === cur.end, v: a.v == null ? null : a.v,
        yoy: chg(a.v, a.y), qoq: years ? null : chg(a.v, a.q) };
    });
    return { years: !!years, pts: pts.filter((p) => p.v != null) };
  }
  const MARK_ROLE = { rev: 'rev', profit: 'profit', cost: 'cost', noncash: 'noncash' };
  function trendBlock(series, n) {
    const pts = series && series.pts;
    if (!pts || pts.length < 2) return '';
    const panels = [['yoy', series.years ? 'Change vs the year before' : 'Change vs a year earlier']]
      .concat(series.years ? [] : [['qoq', 'Change vs the previous quarter']]);
    const W = 320, PL = 6, PR = 40, TOP = 18, BH = 92, GAP = 22, LH = 58, XL = 18, SHORT = 20;   // PR: room for end labels
    const enough = (key) => pts.filter((p) => p[key] != null).length >= 2;
    const tops = [];                                          // where each change panel starts (a short note when empty)
    let yAt = TOP + BH + GAP;
    panels.forEach(([key]) => { tops.push(yAt); yAt += enough(key) ? LH + GAP : SHORT; });
    const H = yAt - GAP + XL + (enough(panels[panels.length - 1][0]) ? 0 : GAP);
    const role = MARK_ROLE[n.color] || 'rev';
    const band = (W - PL - PR) / pts.length, bw = Math.min(24, band * 0.5);
    const cx = (i) => PL + band * i + band / 2;
    const vals = pts.map((p) => p.v), vmax = Math.max(0, ...vals), vmin = Math.min(0, ...vals);
    const vy = (v) => TOP + (vmax - v) / ((vmax - vmin) || 1) * BH;
    const base = vy(0);
    const f = (x) => x.toFixed(1);
    const col = (p, i) => {                                         // 4px rounded data end, square at the baseline
      const x = cx(i) - bw / 2, top = vy(Math.max(p.v, 0)), bot = vy(Math.min(p.v, 0)), r = Math.min(4, Math.abs(bot - top) / 2);
      const d = p.v >= 0
        ? `M${f(x)} ${f(bot)}V${f(top + r)}Q${f(x)} ${f(top)} ${f(x + r)} ${f(top)}H${f(x + bw - r)}Q${f(x + bw)} ${f(top)} ${f(x + bw)} ${f(top + r)}V${f(bot)}Z`
        : `M${f(x)} ${f(top)}V${f(bot - r)}Q${f(x)} ${f(bot)} ${f(x + r)} ${f(bot)}H${f(x + bw - r)}Q${f(x + bw)} ${f(bot)} ${f(x + bw)} ${f(bot - r)}V${f(top)}Z`;
      return `<path class="tr-col${p.cur ? ' cur' : ''}" data-i="${i}" d="${d}" fill="var(--mk-${role})"/>`;
    };
    const last = pts.length - 1, lp = pts[last];
    const capY = lp.v >= 0 ? vy(lp.v) - 5 : vy(lp.v) + 13;
    // a change panel: its own zero line and scale (each panel reads on its own; never two scales on one axis)
    const linePanel = ([key, title], k) => {
      const y0 = tops[k];
      const vals = pts.map((p) => p[key]).filter((x) => x != null);
      const head = `<text class="tr-cap" x="${PL}" y="${y0 - 4}">${title}${vals.length < 2 ? ': not enough periods on file' : ''}</text>`;
      if (vals.length < 2) return head;
      const ymax = Math.max(0, ...vals), ymin = Math.min(0, ...vals), span = (ymax - ymin) || 1;
      const yy = (v) => y0 + 8 + (ymax - v) / span * (LH - 16);
      const segs = [];
      let run = [];
      pts.forEach((p, i) => { if (p[key] == null) { if (run.length) segs.push(run); run = []; } else run.push([cx(i), yy(p[key])]); });
      if (run.length) segs.push(run);
      const li = pts.map((p) => p[key] != null).lastIndexOf(true);
      const ly = yy(pts[li][key]);                                             // the value at the end of the line
      return head + `<line x1="${PL}" x2="${W - PR}" y1="${f(yy(0))}" y2="${f(yy(0))}" class="tr-axis"/>` +
        segs.map((sg) => `<polyline points="${sg.map(([x, y]) => `${f(x)},${f(y)}`).join(' ')}" class="tr-line"/>`).join('') +
        pts.map((p, i) => (p[key] == null ? '' : `<circle class="tr-dot${p.cur ? ' cur' : ''}" data-i="${i}" cx="${f(cx(i))}" cy="${f(yy(p[key]))}" r="4"/>`)).join('') +
        `<text class="tr-lab" x="${f(cx(li) + 9)}" y="${f(ly + 4)}" text-anchor="start">${pct(pts[li][key])}</text>`;
    };
    const line = panels.map(linePanel).join('');
    const chgs = (p) => [p.yoy != null ? `Y/Y ${pct(p.yoy)}` : null, p.qoq != null ? `Q/Q ${pct(p.qoq)}` : null].filter(Boolean);
    const hits = pts.map((p, i) => `<rect class="tr-hit" data-i="${i}" x="${f(PL + band * i)}" y="0" width="${f(band)}" height="${H - XL}" fill="transparent"><title>${t(p.label)}: ${[money(p.v)].concat(chgs(p)).join(' · ')}</title></rect>`).join('');
    const unit = series.years ? 'fiscal years' : 'quarters';
    const aria = `${S.dec(n.name)}, last ${pts.length} ${unit}: ` + pts.map((p) => `${S.dec(p.label)} ${money(p.v)}${chgs(p).length ? ` (${chgs(p).join(', ')})` : ''}`).join('; ');
    const data = t(JSON.stringify(pts.map((p) => [S.dec(p.label), money(p.v)].concat(chgs(p)))));
    return `<figure class="trend" data-pts="${data}">
      <figcaption><span class="tr-title">Last ${pts.length} ${unit}</span><span class="tr-read" aria-live="polite"></span></figcaption>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(aria)}">
        <text class="tr-cap" x="${PL}" y="11">Amount</text>
        <line x1="${PL}" x2="${W - PR}" y1="${f(base)}" y2="${f(base)}" class="tr-axis"/>
        ${pts.map(col).join('')}
        <text class="tr-lab" x="${f(cx(last))}" y="${f(capY)}" text-anchor="middle">${money(lp.v)}</text>
        ${line}
        ${pts.map((p, i) => `<text class="tr-x${p.cur ? ' cur' : ''}" x="${f(cx(i))}" y="${H - 4}" text-anchor="middle">${t(p.label)}</text>`).join('')}
        ${hits}
      </svg></figure>`;
  }
  function wireTrend(root) {
    const fig = $('.trend', root);
    if (!fig) return;
    const pts = JSON.parse(S.dec(fig.dataset.pts));
    const read = $('.tr-read', fig);
    const show = (i) => {
      read.textContent = pts[i].join(' · ');                    // "Q3 FY26 · $2.4B · Y/Y +15% · Q/Q +10%"
      $$('[data-i]', fig).forEach((el) => el.classList.toggle('on', +el.dataset.i === i));
    };
    show(pts.length - 1);
    $$('.tr-hit', fig).forEach((h) => {
      h.addEventListener('pointerenter', () => show(+h.dataset.i));
      h.addEventListener('click', () => show(+h.dataset.i));
    });
    $('svg', fig).addEventListener('pointerleave', () => show(pts.length - 1));
  }

  // ---------- "Compare any two periods" (readers who turned it on in their alerts) ----------
  // The page cannot read SEC itself (no CORS), so the request goes into Supabase; the GitHub workflow draws the
  // comparison from SEC data within a few minutes and writes it back into the reader's row; this page shows it.
  const monthYear = (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  function periodLabel(co, kind, end) {
    const x = ((co.periods || {})[kind] || []).find((y) => y.end === end) ||
      (kind === 'fy' ? (co.years || []) : co.quarters).find((y) => y.end === end);
    return x ? x.label : `${kind === 'fy' ? 'year' : 'quarter'} ended ${date(end)}`;
  }
  function tableMissing(err) {                       // supabase/schema.sql not run again since this feature arrived
    return !!err && (err.code === '42P01' || err.code === 'PGRST205' || err.code === 'PGRST204' || /does not exist|schema cache/i.test(err.message || ''));
  }
  const OWNER_UPDATE = 'The site owner has to update the database first (run supabase/schema.sql again)';

  async function initCompare(co, cik) {
    const btn = $('#cmp-open'), panel = $('#cmp-panel');
    if (!btn) return;
    const cl = await sb();
    if (!cl || !(await currentUser())) return;
    const pr = acct.prefs || await loadPrefs().catch(() => null);
    if (!pr || !pr.custom_compare || !btn.isConnected) return;
    btn.hidden = false;
    btn.addEventListener('click', () => {
      const open = panel.hidden;
      panel.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      btn.classList.toggle('open', open);
      if (open && !panel.dataset.ready) comparePanel(panel, co, cik, cl);
      if (open) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  }

  function comparePanel(panel, co, cik, cl) {
    panel.dataset.ready = '1';
    const per = co.periods || { q: [], fy: [] };
    const rows = new Map();                          // fiscal year -> { q: {1..4: period}, y: period }
    const row = (fy) => { if (!rows.has(fy)) rows.set(fy, { fy, q: {}, y: null }); return rows.get(fy); };
    (per.q || []).forEach((x) => { if (x.fy && x.q) row(x.fy).q[x.q] = x; });
    (per.fy || []).forEach((x) => { if (x.fy) row(x.fy).y = x; });
    const years = [...rows.values()].sort((a, b) => b.fy - a.fy);
    const calendar = !(per.q || []).some((x) => / FY\d/.test(x.label));
    const fyName = (fy) => (calendar ? String(fy) : `FY${String(fy).slice(2)}`);
    const cell = (x, kind) => (x ? `<td><label class="pick" title="${t(x.label)} · ${kind === 'fy' ? 'fiscal year' : 'quarter'} ended ${date(x.end)}">
      <input type="checkbox" data-end="${x.end}" data-kind="${kind}" data-label="${t(x.label)}"><span>${monthYear(x.end)}</span></label></td>` : '<td class="none">—</td>');
    panel.innerHTML = `
      <div class="section-head"><h2>Compare any two periods</h2><span class="muted">Tick two quarters, or two full fiscal years. Drawn from SEC data on request, usually within 1–3 minutes.</span></div>
      ${years.length ? `<div class="tbl-wrap"><table class="period-grid"><thead><tr><th>Fiscal year</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Full year</th></tr></thead><tbody>
        ${years.map((r) => `<tr><th>${fyName(r.fy)}</th>${[1, 2, 3, 4].map((n) => cell(r.q[n], 'q')).join('')}${cell(r.y, 'fy')}</tr>`).join('')}
        </tbody></table></div>
      <div class="cmp-bar"><span id="cmp-sum">Pick two periods</span>
        <button class="btn small" type="button" id="cmp-swap" disabled title="Which period is drawn, and which it is compared with">⇄ Swap</button>
        <button class="btn primary" type="button" id="cmp-go" disabled>Draw comparison</button></div>`
        : '<p class="muted">The list of this company’s periods arrives with its next update (each scan adds it for a few companies at a time).</p>'}
      <p class="muted small" id="cmp-msg" role="status"></p>
      <div id="cmp-recent"></div>`;
    let sel = [], swapped = false;
    const msg = (x) => { $('#cmp-msg', panel).textContent = x || ''; };
    const pair = () => {
      if (sel.length !== 2) return null;
      const [x, y] = sel.slice().sort((m, n) => (m.dataset.end < n.dataset.end ? 1 : -1));   // the later one is drawn
      return swapped ? [y, x] : [x, y];
    };
    const update = () => {
      const ab = pair();
      $('#cmp-sum', panel).innerHTML = ab ? `<b>${ab[0].dataset.label}</b> compared with <b>${ab[1].dataset.label}</b>`
        : sel.length === 1 ? `${sel[0].dataset.label} compared with …` : 'Pick two periods';
      $('#cmp-go', panel).disabled = !ab;
      $('#cmp-swap', panel).disabled = !ab;
    };
    $$('input[data-end]', panel).forEach((box) => box.addEventListener('change', () => {
      msg('');
      if (box.checked) {
        if (sel.length && sel[0].dataset.kind !== box.dataset.kind) {
          sel.forEach((x) => { x.checked = false; });
          sel = [];
          msg('Quarters are compared with quarters, fiscal years with fiscal years.');
        }
        sel.push(box);
        if (sel.length > 2) sel.shift().checked = false;
      } else {
        sel = sel.filter((x) => x !== box);
      }
      swapped = false;
      update();
    }));
    if (years.length) {
      $('#cmp-swap', panel).addEventListener('click', () => { swapped = !swapped; update(); });
      $('#cmp-go', panel).addEventListener('click', async (ev) => {
        const ab = pair();
        if (!ab) return;
        ev.currentTarget.disabled = true;
        msg('Asking…');
        const r = await cl.from('chart_requests').insert({ cik: +cik, kind: ab[0].dataset.kind, a_end: ab[0].dataset.end, b_end: ab[1].dataset.end })
          .select('id').single();
        if (r.error) {
          ev.currentTarget.disabled = false;
          msg(tableMissing(r.error) ? OWNER_UPDATE : /limit/i.test(r.error.message) ? 'Limit reached: 20 comparisons a day' : `Could not ask: ${r.error.message}`);
          return;
        }
        location.hash = `c-${cik}-cmp-${r.data.id}`;
      });
    }
    recentComparisons($('#cmp-recent', panel), co, cik, cl);
  }

  async function recentComparisons(box, co, cik, cl) {
    const r = await cl.from('chart_requests').select('id,kind,a_end,b_end,status,created_at').eq('cik', +cik)
      .order('created_at', { ascending: false }).limit(8);
    if (!box.isConnected || r.error || !r.data || !r.data.length) return;
    const word = { pending: 'waiting', working: 'drawing', done: 'ready', failed: 'failed' };
    box.innerHTML = `<h3>Your comparisons of this company</h3><ul class="cmp-list">${r.data.map((x) =>
      `<li><a href="#c-${cik}-cmp-${x.id}">${t(periodLabel(co, x.kind, x.a_end))} vs ${t(periodLabel(co, x.kind, x.b_end))}</a>
       <span class="muted">· ${word[x.status] || t(x.status)} · asked ${date(x.created_at)}</span></li>`).join('')}</ul>`;
  }

  async function showComparison(body, co, id, ticker) {
    body.innerHTML = '<div class="cmp-wait"><div class="loading">Loading your comparison…</div></div>';
    const cl = await sb();
    const user = cl ? await currentUser() : null;
    if (!cl || !user) {
      body.innerHTML = `<div class="cmp-wait"><h2>Sign in to see this comparison</h2><p class="muted">Comparisons you ask for are kept with your account.</p>
        <p><a class="btn primary" href="#account">Sign in</a></p></div>`;
      prefs.set('after-signin', location.hash.replace(/^#/, ''));
      return;
    }
    const started = Date.now();
    const poll = async () => {
      if (!body.isConnected) return;
      const r = await cl.from('chart_requests').select('*').eq('id', +id).maybeSingle();
      if (!body.isConnected) return;
      const row = r.data;
      if (r.error || !row) {
        body.innerHTML = `<div class="cmp-wait"><h2>This comparison is not available</h2><p class="muted">${r.error ? t(r.error.message) : 'It may belong to another account.'}</p></div>`;
        return;
      }
      const a = periodLabel(co, row.kind, row.a_end), b = periodLabel(co, row.kind, row.b_end);
      if (row.status === 'pending' || row.status === 'working') {
        const secs = Math.max(0, Math.round((Date.now() - new Date(row.created_at).getTime()) / 1000));
        body.innerHTML = `<div class="cmp-wait"><div class="spinner" aria-hidden="true"></div>
          <h2>${t(a)} compared with ${t(b)}</h2>
          <p>${row.status === 'working' ? 'Reading both filings from SEC and drawing the chart…' : 'Waiting for the next run of the request workflow…'}</p>
          <p class="muted">Usually 1–3 minutes (up to 10 when nothing wakes the workflow) · asked ${secs < 90 ? `${secs} s` : `${Math.round(secs / 60)} min`} ago.
            This page updates itself; you can also leave and find it later under ⇄ Compare any two.</p></div>`;
        setTimeout(poll, Date.now() - started < 30 * 60e3 ? 5000 : 30000);
        return;
      }
      if (row.status === 'failed') {
        body.innerHTML = `<div class="cmp-wait"><h2>Could not draw ${t(a)} compared with ${t(b)}</h2><p>${t(row.error || 'Unknown error')}</p>
          <p class="muted">Pick two other periods under ⇄ Compare any two.</p></div>`;
        return;
      }
      renderComparison(body, co, row, ticker);
    };
    poll();
  }

  function renderComparison(body, co, row, ticker) {
    const spec = row.result, cu = spec.custom || {}, p = co.profile, cik = p.cik;
    const slug = (x) => String(x || '').replace(/\s+/g, '-');
    body.innerHTML = `<div class="cmp-head"><div class="eyebrow">Your comparison · ${cu.kind === 'fy' ? 'fiscal years' : 'quarters'}</div>
      <h2>${t(cu.a_label)} compared with ${t(cu.b_label)}</h2>
      <p class="muted">Drawn on request from SEC data${row.done_at ? ` on ${date(row.done_at)}` : ''}. Band width is ${t(cu.a_label)}; a dark strip is the increase over ${t(cu.b_label)}.
        <a href="#c-${cik}">Back to the latest chart</a></p></div>`;
    const ui = chartUI(spec, {
      company: S.dec(p.name), form: spec.form, label: spec.label, docUrl: spec.doc_url, custom: true, cik: p.cik,
      slug: slug(`${ticker || cik}-${cu.a_label}`), vsSlug: slug(cu.b_label), onView: () => {},
    });
    body.appendChild(ui);
    const acc = accession(spec.index_url), accB = accession(cu.b_index_url);
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose"><h2>Analysis</h2>${(spec.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        ${changesHTML(spec)}
        <p class="note-rule">Written by fixed rules from the reported figures (no language model).</p></div>
      <div class="prose"><h2>Filings</h2>
        <dl class="facts">
          <dt>${t(cu.a_label)}</dt><dd><span class="mono">${t(spec.form)}</span> filed ${date(spec.filed)}${acc ? ` · <span class="mono">${acc}</span>` : ''}${
            spec.index_url ? ` · <a href="${t(spec.index_url)}" target="_blank" rel="noopener">filing ↗</a>` : ''}</dd>
          <dt>${t(cu.b_label)}</dt><dd>filed ${date(cu.b_filed)}${accB ? ` · <span class="mono">${accB}</span>` : ''}${
            cu.b_index_url ? ` · <a href="${t(cu.b_index_url)}" target="_blank" rel="noopener">filing ↗</a>` : ''}</dd>
          <dt>Data</dt><dd>${cu.kind === 'fy' ? 'Full-year values' : 'Quarterly values (fourth quarters and cash flows as year-to-date minus the prior year-to-date)'} from SEC’s XBRL company facts; revenue lines from the filings’ own XBRL instances when both report them the same way</dd>
        </dl></div>`;
    body.appendChild(text);
  }

  // ---------- a company the site has no chart for yet (found by the search) ----------
  let secList = null;
  function secCompanies() {                          // [cik, ticker, name] for every company on SEC's ticker list
    if (!secList) secList = getJSON('companies.json').then((d) => d.companies || []).catch(() => { secList = null; return []; });
    return secList;
  }
  async function askForCompany(cik) {
    const cl = await sb();
    const r = await cl.from('company_requests').insert({ cik: +cik });
    if (r.error && r.error.code === '23505') return { ok: true, msg: 'Already asked: the next scan builds it' };
    if (r.error && tableMissing(r.error)) return { ok: false, msg: OWNER_UPDATE };
    if (r.error && /limit/i.test(r.error.message)) return { ok: false, msg: 'Limit reached: 10 companies a day' };
    if (r.error) return { ok: false, msg: `Could not ask: ${r.error.message}` };
    return { ok: true, msg: 'Asked: the next scan reads its filings from SEC' };
  }
  async function missingCompany(cik) {
    setNav('');
    const all = await secCompanies();
    const hit = all.find((x) => x[0] === +cik);
    const name = hit ? hit[2] : `CIK ${cik}`, ticker = hit ? hit[1] : '';
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a></div>
        <h1>${t(name)}</h1>
        <div class="meta">${ticker ? `<span class="tag mono">${t(ticker)}</span>` : ''}<span>CIK <span class="mono">${+cik}</span></span>
          <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${+cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">EDGAR filings ↗</a></div>
      </div>
      <section class="build-box" id="build-box">
        <h2>No charts for this company yet</h2>
        <p>Companies are drawn when they file a 10-Q, 10-K or earnings release during the regular scan (every 15 minutes).
          <span id="build-how">Ask for it and the next scan reads its last five 10-Qs and two 10-Ks from SEC; this page fills in by itself (usually 10–30 minutes).</span></p>
        <div class="row"><button class="btn primary" id="build-go" type="button" hidden>Build its charts</button>
          <span class="muted" id="build-msg" role="status"></span></div>
      </section>`;
    const box = $('#build-box'), btn = $('#build-go'), msg = (x) => { $('#build-msg').textContent = x || ''; };
    const cl = await sb();
    if (!cl) {
      $('#build-how').textContent = 'Its charts appear here after its next filing.';
      return;
    }
    btn.hidden = false;
    let watching = false;
    const watch = async () => {                      // the scan publishes data/c/<cik>.json; the request row says how it went
      if (!box.isConnected) return;
      watching = true;
      btn.disabled = true;
      try {
        await getJSON(`c/${+cik}.json`, true);
        if (box.isConnected) { acct.flash = 'Its charts are ready'; route(); }
        return;
      } catch (e) { /* not published yet */ }
      const r = await cl.from('company_requests').select('status,error,created_at').eq('cik', +cik)
        .order('created_at', { ascending: false }).limit(1);
      const last = r.data && r.data[0];
      if (!box.isConnected) return;
      if (last && last.status === 'failed') {
        msg(`Not built: ${last.error || 'SEC has no 10-Q or 10-K figures for it'}`);
        btn.disabled = false;
        watching = false;
        return;
      }
      msg(last && last.status === 'done' ? 'Built: publishing the site…'
        : last && last.status === 'queued' ? 'The scan is reading its filings from SEC…' : 'Waiting for the next scan…');
      setTimeout(watch, 20000);
    };
    if (await currentUser()) {
      const r = await cl.from('company_requests').select('status').eq('cik', +cik).order('created_at', { ascending: false }).limit(1);
      if (r.data && r.data[0] && ['pending', 'queued', 'done'].includes(r.data[0].status)) watch();
    }
    btn.addEventListener('click', async () => {
      if (!(await currentUser())) {
        prefs.set('pending-build', String(+cik));
        prefs.set('after-signin', `c-${+cik}`);
        location.hash = 'account';
        return;
      }
      btn.disabled = true;
      const res = await askForCompany(cik);
      msg(res.msg);
      if (res.ok && !watching) setTimeout(watch, 3000);
      else btn.disabled = false;
    });
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
        <div class="meta">${level === 's' ? `<button class="btn follow" type="button" hidden data-follow="sector:${t(id)}">☆ Follow</button>` : ''}
          <span class="tag">${level === 's' ? 'Sector' : 'Industry · SIC ' + t(g.id)}</span>
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
        ${changesHTML(q)}
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

  async function methodPage() {
    setNav('method');
    const ix = await getJSON('index.json').catch(() => ({}));
    const au = ix.release_audit || { checked: 0, matched: 0, mismatches: [] };
    const names = { revenue: 'revenue', oi: 'operating profit', ni: 'net earnings', ocf: 'operating cash flow' };
    const auditHTML = `<h2>Checking the 8-K reader</h2>
        <p>Every quarter first drawn from an earnings release is compared with the company’s 10-Q or 10-K when it arrives (revenue, operating profit, net earnings and operating cash flow, within 0.5%).</p>
        <p><b>${au.checked}</b> release${au.checked === 1 ? '' : 's'} checked so far${au.checked ? `, <b>${au.matched}</b> matched (${(au.matched / au.checked * 100).toFixed(0)}%)` : ''}.</p>
        ${au.mismatches.length ? `<div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Quarter end</th><th>Line</th><th class="num">8-K</th><th class="num">10-Q/10-K</th></tr></thead><tbody>${
          au.mismatches.slice().reverse().flatMap((m) => Object.entries(m.fields).map(([k, [a, b]]) =>
            `<tr><td><a href="#c-${m.cik}">${t(m.ticker)}</a></td><td>${date(m.end)}</td><td>${names[k] || k}</td><td class="num">${money(a)}</td><td class="num">${money(b)}</td></tr>`)).join('')
        }</tbody></table></div>` : ''}`;
    app.innerHTML = `
      <div class="page-head"><div class="eyebrow">Method</div><h1>How each chart is built</h1></div>
      <div class="cols"><div class="prose">
        <h2>Scanning</h2>
        <p>Every 15 minutes a scheduled job reads EDGAR’s live feed of new 10-Q and 10-K filings (plus the daily index as a fallback). Each new filing is processed once its XBRL data appears in the SEC’s company-facts API, which can lag the filing by a few hours; until then it waits in a retry queue.</p>
        <h2>Earnings releases (8-K)</h2>
        <p>Most companies publish results in an 8-K press release days or weeks before the 10-Q or 10-K. The scan also reads 8-K filings with Item 2.02 (results of operations): the statements printed in the release are read by fixed rules. Before anything is drawn, one of the release’s earlier-period columns must equal the revenue and net earnings the company already filed in XBRL (this pins down the columns, the units and the period), the statement must reconcile, and the quarter must end at least a week before the release. These charts are marked preliminary and are replaced automatically when the 10-Q or 10-K arrives.</p>
        <h2>Numbers</h2>
        <p>All figures are GAAP values reported in XBRL. A quarter is taken directly when a three-month value exists; otherwise it is year-to-date minus the prior year-to-date, which is how fourth quarters (10-K) and all quarterly cash flows are derived. Revenue lines and segments come from the dimensional facts in the filing’s own XBRL instance and are used only when they add up to total revenue.</p>
        <h2>Layout</h2>
        <p>Revenue lines merge into revenue; profit stays on top and costs peel downward; operating profit plus other income becomes pre-tax earnings, which splits into tax, minority interests and net earnings; operating cash flow is bridged directly from net earnings and splits into capital expenditures and free cash flow (when capex exceeds operating cash flow, the gap enters as negative free cash flow). Each label shows the amount, its share of the node it splits from or flows into, and the change year over year and quarter over quarter. Loss-making quarters use a funding view: revenue, other income and the net loss together fund all costs.</p>
        <p>The comparison view keeps the same picture and marks the part of every band that grew since the previous quarter as a dark strip. Each label adds Δ = scale + mix: scale is the change explained by the parent node growing, mix the change in the item’s share of its parent.</p>
        <h2>Full years and any two periods</h2>
        <p>Each 10-K also gets a full-year chart from the year’s reported totals, compared with the year before. Signed-in readers who turn on “Compare any two periods” can pick any two quarters (or two fiscal years) that SEC’s XBRL data covers, back to 2009–2011; the comparison is drawn from SEC data on request by the same rules, the first period against the second.</p>
      </div><div class="prose">
        ${auditHTML}
        <h2>Text</h2>
        <p>No language model is used anywhere. Company descriptions are the opening paragraphs of Item 1 (Business) of the latest 10-K; for a company that has not filed a 10-K yet, the “About” paragraph of its earnings release, or else the description of business in Note 1 of its 10-Q. Node notes are the paragraphs under the matching heading in Management’s Discussion and Analysis of the same filing, quoted verbatim. Analysis paragraphs are sentences filled from the numbers by fixed rules.</p>
        <h2>Starred companies</h2>
        <p>Companies listed in <span class="mono">config/starred.txt</span> keep eight quarters and three fiscal years (others keep seven and two) and are back-filled from their filing history when first added.</p>
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
      const exact = (c) => (c.ticker || '').toLowerCase() === q;
      const match = (c) => (c.ticker || '').toLowerCase().startsWith(q) || c.name.toLowerCase().includes(q);
      const here = ix.companies.filter(match).sort((a, b) => exact(b) - exact(a) || b.revenue - a.revenue);
      const draw = (list) => {
        items = list.slice(0, 8);
        hi = 0;
        box.innerHTML = items.map((c, i) => `<a href="#c-${c.cik}" class="${i === hi ? 'hi' : ''}${c.off ? ' off' : ''}"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span>${
          c.off ? '<span class="tag">no chart yet</span>' : ''}</a>`).join('') ||
          '<div class="muted" style="padding:8px 10px">No company found</div>';
        box.hidden = false;
      };
      draw(here);
      const all = await secCompanies();                 // every SEC company with a ticker, also those not drawn yet
      if (input.value.trim().toLowerCase() !== q || !all.length) return;
      const have = new Set(ix.companies.map((c) => +c.cik));
      const there = [];
      for (const [cik, ticker, name] of all) {          // SEC lists the largest first
        if (have.has(cik)) continue;
        const c = { cik, ticker, name, off: true };
        if (match(c)) there.push(c);
        if (there.length >= 16) break;
      }
      if (!there.length) return;
      draw(here.filter(exact).concat(there.filter(exact), here.filter((c) => !exact(c)), there.filter((c) => !exact(c))));
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

  // ---------- accounts: passwordless sign-in (a code by e-mail) and alert preferences, stored in Supabase ----------
  const SUPABASE_JS = ['cdn.jsdelivr.net/npm', 'fastly.jsdelivr.net/npm', 'unpkg.com']   // tried in turn (some networks block one)
    .map((h) => `https://${h}/@supabase/supabase-js@2.58.0/dist/umd/supabase.js`);
  const PREF_DEFAULTS = { tickers: [], sectors: [], all_above: false, min_revenue: 1e9, starred: false,
    frequency: 'daily', email_on: true, push_on: true, final_too: true };
  const MAIL_DEFAULTS = { chart_q: false, chart_y: false, chart_history: false, attach_images: 'png', attach_pdf: true, cmp_decreases: false,
    changes_detail: false, custom_compare: false, digest_hour: 8, tz: null };   // columns added after the first release (see savePrefs)
  const acct = { client: undefined, prefs: null, flash: null, owner: undefined, osets: undefined };
  function browserTZ() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch (e) { return null; }
  }
  const hourWords = (h) => `${+h}:00`;

  function loadScript(src, ms) {
    return new Promise((res, rej) => {
      const el = document.createElement('script');
      const fail = () => { clearTimeout(timer); el.remove(); rej(new Error('could not load ' + src)); };
      const timer = setTimeout(fail, ms || 6000);                // a blocked host can hang instead of failing
      el.src = src;
      el.onload = () => { clearTimeout(timer); res(); };
      el.onerror = fail;
      document.head.appendChild(el);
    });
  }
  async function sb() {
    if (acct.client !== undefined) return acct.client;
    if (window.FF_SUPABASE) return (acct.client = window.FF_SUPABASE);          // injected by tests
    const site = await getJSON('site.json').catch(() => ({}));
    if (!site.supabase_url || !site.supabase_key) return (acct.client = null);
    try {
      for (const src of SUPABASE_JS) {
        if (window.supabase && window.supabase.createClient) break;
        await loadScript(src).catch((e) => console.warn(e.message));
      }
      acct.client = window.supabase.createClient(site.supabase_url, site.supabase_key);
    } catch (e) {
      console.warn('accounts are off on this page:', e.message);
      acct.client = null;
    }
    return acct.client;
  }
  async function currentUser() {
    const c = await sb();
    if (!c) return null;
    const { data } = await c.auth.getSession();
    return data && data.session ? data.session.user : null;
  }
  function syncApp() {                     // the Android app checks for new charts in the background with these
    const native = window.FilingFlowsApp;
    if (!native || typeof native.setFollows !== 'function') return;
    const p = acct.prefs;
    try {
      native.setFollows(JSON.stringify(p ? { tickers: p.tickers, sectors: p.sectors, all_above: p.all_above,
        min_revenue: p.min_revenue, starred: p.starred, push_on: p.push_on, final_too: p.final_too !== false } : null));
    } catch (e) { /* older app */ }
  }
  async function loadPrefs() {
    const c = await sb();
    const user = await currentUser();
    if (!c || !user) return null;
    const got = await c.from('subscriptions').select('*').eq('user_id', user.id).maybeSingle();
    if (got.error) throw new Error(got.error.message);
    let row = got.data;
    if (!row) {
      const base = Object.assign({ user_id: user.id, email: user.email }, PREF_DEFAULTS);
      let ins = await c.from('subscriptions').insert(Object.assign({ tz: browserTZ() }, base)).select().single();
      if (ins.error && ins.error.code === 'PGRST204') ins = await c.from('subscriptions').insert(base).select().single();   // older database
      if (ins.error) throw new Error(ins.error.message);
      row = ins.data;
    } else if ('tz' in row && !row.tz && browserTZ()) {          // the daily report's time zone: this browser's
      const up = await c.from('subscriptions').update({ tz: browserTZ() }).eq('user_id', user.id).select().single();
      if (!up.error && up.data) row = up.data;
    }
    acct.prefs = row;
    if (typeof row.cmp_decreases === 'boolean' && row.cmp_decreases !== state.decreases) {   // the account setting wins
      state.decreases = row.cmp_decreases;
      prefs.set('decreases', state.decreases);
      $$('[data-dec]').forEach((cb) => { cb.checked = state.decreases; });
      state.charts.forEach((c) => c.redraw && c.redraw());
    }
    syncApp();
    return row;
  }
  async function savePrefs(patch) {
    const c = await sb();
    const user = await currentUser();
    const row = Object.assign({}, PREF_DEFAULTS, acct.prefs || {}, patch, { user_id: user.id, email: user.email });
    if (browserTZ()) row.tz = browserTZ();                      // the daily report goes out at its hour in this time zone
    ['unsub_token', 'created_at', 'updated_at'].forEach((k) => delete row[k]);
    let up = await c.from('subscriptions').upsert(row).select().single();
    if (up.error && up.error.code === 'PGRST204' && Object.keys(MAIL_DEFAULTS).some((k) => k in row)) {
      // the database predates the e-mail content options (supabase/schema.sql not run again yet): save the rest
      Object.keys(MAIL_DEFAULTS).forEach((k) => delete row[k]);
      up = await c.from('subscriptions').upsert(row).select().single();
      if (!up.error) acct.flash = 'Saved, except the e-mail content options: the site owner has to update the database first';
    }
    if (up.error) throw new Error(up.error.message);
    acct.prefs = up.data;
    syncApp();
    return up.data;
  }

  // Follow / Following buttons on company and sector pages
  async function initFollowButtons() {
    const btns = $$('[data-follow]');
    if (!btns.length) return;
    const c = await sb();
    if (!c) return;                                   // accounts not switched on: the buttons stay hidden
    const user = await currentUser();
    const p = user ? (acct.prefs || await loadPrefs().catch(() => null)) : null;
    btns.forEach((b) => {
      const [kind, value] = b.dataset.follow.split(':');
      const list = kind === 'ticker' ? 'tickers' : 'sectors';
      const on = () => !!(acct.prefs && (acct.prefs[list] || []).includes(value));
      const paint = () => { b.textContent = on() ? '★ Following' : '☆ Follow'; b.classList.toggle('on', on()); };
      paint();
      b.hidden = false;
      if (b.dataset.wired) return;
      b.dataset.wired = '1';
      b.addEventListener('click', async () => {
        if (!(await currentUser())) {
          prefs.set('pending-follow', b.dataset.follow);
          prefs.set('after-signin', location.hash.replace(/^#/, ''));
          location.hash = 'account';
          return;
        }
        const cur = (acct.prefs && acct.prefs[list]) || [];
        b.disabled = true;
        try {
          await savePrefs({ [list]: on() ? cur.filter((x) => x !== value) : cur.concat([value]) });
          toast(on() ? `Following ${value}: new charts will be sent to you` : `Stopped following ${value}`);
        } catch (err) {
          toast(`Could not save: ${err.message}`);
        } finally {
          b.disabled = false;
          paint();
        }
      });
      if (!p) b.title = 'Sign in with your e-mail to follow';
    });
  }

  // "Email me this report": a queued request; the sender mails it to the signed-in address (any quarter on the site)
  async function requestReports(cik, ends, kind) {
    const c = await sb();
    const user = await currentUser();
    const rows = ends.map((end) => Object.assign({ cik: +cik, period_end: end }, kind === 'fy' ? { kind: 'fy' } : {}));
    let r = await c.from('send_requests').insert(rows);
    let dup = 0;
    if (r.error && r.error.code === '23505' && rows.length > 1) {     // some already on their way: add the rest
      r = { error: null };
      for (const row of rows) {
        const one = await c.from('send_requests').insert([row]);
        if (one.error && one.error.code === '23505') dup++;
        else if (one.error) { r = one; break; }
      }
    }
    if (r.error && r.error.code === '23505') return 'Already on its way to your inbox';
    if (r.error && /limit/i.test(r.error.message)) return 'Limit reached: 30 reports a day';
    if (r.error && kind === 'fy' && tableMissing(r.error)) return OWNER_UPDATE;
    if (r.error) return `Could not send: ${r.error.message}`;
    const n = rows.length - dup;
    if (!n) return 'Already on its way to your inbox';
    return `${n === 1 ? 'Report' : n + ' reports'} on the way to ${user.email}, usually within 10 minutes`;
  }
  // one queued e-mail of any kind (send_requests): a day's report, or the owner's X thread of a quarter
  async function askFor(row, what) {
    const c = await sb();
    const user = c ? await currentUser() : null;
    if (!user) return 'Sign in first';
    if (!acct.prefs) await loadPrefs().catch(() => null);      // the sender reads the address from the account's row
    const r = await c.from('send_requests').insert([row]);
    if (r.error && r.error.code === '23505') return `${what} already on its way to your inbox`;
    if (r.error && /limit/i.test(r.error.message)) return 'Limit reached: 30 e-mails a day';
    if (r.error && (tableMissing(r.error) || /check constraint|violates row-level/i.test(r.error.message))) return OWNER_UPDATE;
    if (r.error) return `Could not send: ${r.error.message}`;
    return `${what} on the way to ${user.email}, usually within a few minutes`;
  }

  // ---------- the daily report of one filing date (home page and owner tools): today and the five days before ----------
  function localISO(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }
  function dayEntries(ix, day) {                       // the same filings pipeline/notify.py entries_for_day() picks
    const out = [], seen = new Set();
    ix.companies.forEach((e) => {
      const found = [];
      if (e.filed === day || e.after_release === day) found.push(e);
      (e.also || []).forEach((a) => { if (a.filed === day) found.push(Object.assign({}, e, a, { prelim: a.form === '8-K' })); });
      found.forEach((x) => { const k = `${x.cik}:${x.end}:${x.form}`; if (!seen.has(k)) { seen.add(k); out.push(x); } });
    });
    return out;
  }
  const normTicker = (x) => String(x || '').trim().toUpperCase().replace(/\./g, '-');
  const followsAny = (p) => !!(p && ((p.tickers || []).length || (p.sectors || []).length || p.all_above || p.starred));
  function followed(e, p) {                            // the same rules as pipeline/notify.py reasons()
    return (e.ticker && (p.tickers || []).map(normTicker).includes(normTicker(e.ticker))) || (p.sectors || []).includes(e.sector)
      || (p.all_above && (e.revenue || 0) >= (p.min_revenue || 0)) || (p.starred && e.starred);
  }
  async function dailyPanel(box, ix, opt) {
    opt = opt || {};
    const c = await sb();
    if (!c || !box.isConnected) return;
    const user = await currentUser();
    const p = user ? (acct.prefs || await loadPrefs().catch(() => null)) : null;
    const owner = user ? await ownerVerified() : false;
    const osets = owner ? await ownerSettings() : null;
    const minOwner = osets && osets.min_revenue != null ? +osets.min_revenue : 1e9;
    const scope = owner ? (e) => (e.revenue || 0) >= minOwner
      : followsAny(p) ? (e) => followed(e, p) : (e) => (e.revenue || 0) >= 1e9;
    const mineWord = owner ? 'in your report' : followsAny(p) ? 'you follow' : 'over $1B';
    const now = new Date();
    const days = [0, 1, 2, 3, 4, 5].map((i) => {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      const iso = localISO(d), all = dayEntries(ix, iso);
      const name = i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'short' });
      return { iso, i, name, short: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        long: d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }), all: all.length, mine: all.filter(scope).length };
    });
    const first = days.find((d) => d.mine) || days.find((d) => d.all) || days[1];
    let pick = first.iso;
    const hour = owner && osets ? osets.daily_hour : p && p.digest_hour != null ? p.digest_hour : 8;
    const auto = owner ? (osets && osets.daily_on === false ? 'Your scheduled owner report is off (Owner tools).'
      : `Your owner report also arrives by itself every morning at ${hourWords(hour)} ${t((osets && osets.tz) || 'Asia/Shanghai')} time.`)
      : p && p.email_on && p.frequency === 'daily' ? `The report of new filings also arrives by itself every morning at ${hourWords(hour)} your time (change it in <a href="#account">Alerts</a>).`
      : `Get it every morning by itself: choose “Daily report” in <a href="#account">${user ? 'your alerts' : 'Alerts'}</a>.`;
    const what = owner ? `every company with quarterly revenue of $${(minOwner / 1e9).toLocaleString('en-US', { maximumFractionDigits: 2 })}B or more, with its X thread`
      : followsAny(p) ? 'the companies you follow' : 'every company with quarterly revenue of $1B or more (follow companies to narrow it)';
    box.innerHTML = `<div class="section-head"><h2>${opt.title || 'Daily report'}</h2>
        <span class="muted">One e-mail for a day’s filings: what each company does, its chart and the analysis</span></div>
      <div class="days" role="radiogroup" aria-label="Filing date">${days.map((d) => `<button type="button" class="day${d.iso === pick ? ' on' : ''}"
          role="radio" aria-checked="${d.iso === pick}" data-day="${d.iso}" ${d.all ? '' : 'disabled'}>
          <b>${d.name}</b><span>${d.short}</span><span class="n">${d.all ? `${d.all} filing${d.all === 1 ? '' : 's'}${user ? ` · ${d.mine} ${mineWord}` : ''}` : 'no filings'}</span></button>`).join('')}</div>
      <div class="row"><button class="btn primary" type="button" id="day-send"></button><span class="muted small" id="day-msg" role="status"></span></div>
      <p class="muted small">Covers ${what}. Dates are filing dates on SEC EDGAR. ${auto}</p>`;
    const label = () => { const d = days.find((x) => x.iso === pick); $('#day-send', box).textContent = `✉ Email me the report for ${d.i < 2 ? d.name.toLowerCase() : d.long}`; };
    label();
    $$('[data-day]', box).forEach((b) => b.addEventListener('click', () => {
      pick = b.dataset.day;
      $$('[data-day]', box).forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); });
      label();
    }));
    $('#day-send', box).addEventListener('click', async (ev) => {
      if (!(await currentUser())) {
        prefs.set('pending-day', pick);
        prefs.set('after-signin', location.hash.replace(/^#/, '') || 'home');
        location.hash = 'account';
        return;
      }
      const btn = ev.currentTarget;
      btn.disabled = true;
      $('#day-msg', box).textContent = await askFor({ cik: 0, period_end: pick, kind: 'day' }, 'Report');
      btn.disabled = false;
    });
    box.hidden = false;
  }

  async function initSendButtons() {
    const btns = $$('[data-send]');
    if (!btns.length) return;
    if (!(await sb())) return;
    btns.forEach((b) => {
      b.hidden = false;
      if (b.dataset.wired) return;
      b.dataset.wired = '1';
      b.addEventListener('click', async () => {
        if (!(await currentUser())) {
          prefs.set('pending-send', b.dataset.send);
          prefs.set('after-signin', location.hash.replace(/^#/, ''));
          location.hash = 'account';
          return;
        }
        const [cik, ends, kind] = b.dataset.send.split('|');
        b.disabled = true;
        toast(await requestReports(cik, ends.split(','), kind));
        b.disabled = false;
      });
    });
  }

  async function accountPage() {
    setNav('account');
    const c = await sb();
    if (!c) {
      app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>E-mail alerts are not switched on yet</h1>
        <p class="muted" style="max-width:70ch">The site owner still has to connect the accounts service (see “Accounts and alerts” in the README).</p></div>`;
      return;
    }
    if (!(await currentUser())) return signInView(c);
    const p = await loadPrefs();
    const pending = prefs.get('pending-follow', null), pendingSend = prefs.get('pending-send', null);
    const pendingBuild = prefs.get('pending-build', null), pendingOwner = prefs.get('pending-owner', false);
    const pendingDay = prefs.get('pending-day', null);
    if (pendingDay) {                                 // "Email me the report for …" from before signing in
      prefs.set('pending-day', null);
      acct.flash = await askFor({ cik: 0, period_end: pendingDay, kind: 'day' }, 'Report');
    }
    if (pending) {                                    // a Follow click from before signing in
      prefs.set('pending-follow', null);
      const [kind, value] = pending.split(':');
      const list = kind === 'ticker' ? 'tickers' : 'sectors';
      if (!(p[list] || []).includes(value)) await savePrefs({ [list]: (p[list] || []).concat([value]) });
      acct.flash = `Following ${value}`;
    }
    if (pendingSend) {                                // an "Email me" click from before signing in
      prefs.set('pending-send', null);
      const [cik, ends, kind] = pendingSend.split('|');
      acct.flash = await requestReports(cik, ends.split(','), kind);
    }
    if (pendingBuild) {                               // "Build its charts" from before signing in
      prefs.set('pending-build', null);
      acct.flash = (await askForCompany(pendingBuild)).msg;
    }
    if (pendingOwner) prefs.set('pending-owner', false);       // signing in from the owner tools page
    if (pending || pendingSend || pendingBuild || pendingOwner || pendingDay) {
      const back = prefs.get('after-signin', null);
      prefs.set('after-signin', null);
      if (back && back !== 'account') { location.hash = back; return; }
    }
    settingsView(c, await currentUser(), acct.prefs);
  }

  function signInView(c) {
    const email0 = prefs.get('signin-email', '') || '';
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Sign in with your e-mail</h1>
        <p class="muted" style="max-width:68ch">No password. We send a sign-in code to your inbox; enter it here. New addresses get an account automatically.</p></div>
      <form class="auth" id="auth-email"><label>E-mail address<input type="email" required autocomplete="email" value="${t(email0)}"></label>
        <button class="btn primary" type="submit">Send code</button></form>
      <form class="auth" id="auth-code" hidden><label>Code from the e-mail<input inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,10}" required></label>
        <button class="btn primary" type="submit">Sign in</button> <button class="btn" type="button" id="auth-back">Use another address</button></form>
      <p class="auth-msg muted" id="auth-msg" role="status"></p>
      <p class="muted small">By signing up you agree to the <a href="terms.html">terms</a>; the <a href="privacy.html">privacy policy</a> lists exactly what is stored.</p>`;
    const msg = (x) => { $('#auth-msg').textContent = x; };
    let email = '';
    $('#auth-email').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      email = $('#auth-email input').value.trim();
      const btn = $('#auth-email button');
      btn.disabled = true;
      msg('Sending…');
      // emailRedirectTo: where a link in the e-mail lands if a template still sends one (without it Supabase uses the
      // browser's Referer, which is only the domain: https://you.github.io/ instead of the site)
      const r = await c.auth.signInWithOtp({ email, options: { shouldCreateUser: true, emailRedirectTo: location.origin + location.pathname } });
      btn.disabled = false;
      if (r.error) { msg(`Could not send the code: ${r.error.message}`); return; }
      prefs.set('signin-email', email);
      $('#auth-email').hidden = true;
      $('#auth-code').hidden = false;
      $('#auth-code input').focus();
      msg(`Code sent to ${email}. It can take a minute; check the spam folder too.`);
    });
    $('#auth-back').addEventListener('click', () => { $('#auth-code').hidden = true; $('#auth-email').hidden = false; msg(''); });
    $('#auth-code').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const token = $('#auth-code input').value.trim();
      msg('Checking…');
      const r = await c.auth.verifyOtp({ email, token, type: 'email' });
      if (r.error) { msg(`That code did not work: ${r.error.message}`); return; }
      prefs.set('signin-email', null);
      await accountPage();
    });
  }

  function settingsView(c, user, p) {
    Promise.all([getJSON('index.json'), getJSON('site.json').catch(() => ({}))]).then(([ix, site]) => {
      const inApp = !!window.FilingFlowsApp;
      const appLink = !inApp && site.repo ? ` · <a href="https://github.com/${t(site.repo)}/releases/tag/android" target="_blank" rel="noopener">get the app</a>` : '';
      const names = ix.sector_names || {};
      const tickers = ix.companies.map((x) => x.ticker).filter(Boolean).sort();
      const m = Object.assign({}, MAIL_DEFAULTS, p);
      app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Your alerts</h1>
          <div class="meta"><span>Signed in as <b>${t(user.email)}</b></span><button class="btn small" type="button" id="sign-out">Sign out</button></div></div>
        <form class="prefs" id="prefs-form">
          <fieldset><legend>Companies</legend>
            <div class="chips" id="chips"></div>
            <div class="row"><input id="add-ticker" list="ticker-list" placeholder="Ticker, e.g. AAPL" autocomplete="off" aria-label="Add a company">
              <datalist id="ticker-list">${tickers.map((x) => `<option value="${t(x)}">`).join('')}</datalist>
              <button class="btn" type="button" id="add-btn">Add</button></div>
            <p class="muted small">Or use ☆ Follow on any company page.</p></fieldset>
          <fieldset><legend>Sectors</legend><p class="muted small">Every company in the sectors you tick.</p><div class="grid-checks">${Object.entries(names).map(([k, v]) =>
            `<label><input type="checkbox" name="sector" value="${k}" ${(p.sectors || []).includes(k) ? 'checked' : ''}> ${t(v)}</label>`).join('')}</div></fieldset>
          <fieldset><legend>Also</legend>
            <label><input type="checkbox" id="all-above" ${p.all_above ? 'checked' : ''}> Every company with quarterly revenue of at least
              $<input type="number" id="min-rev" min="0" step="0.1" value="${(p.min_revenue / 1e9).toFixed(1).replace(/\.0$/, '')}" style="width:5em"> billion</label>
            <label><input type="checkbox" id="starred" ${p.starred ? 'checked' : ''}> The site’s starred companies</label></fieldset>
          <fieldset><legend>When</legend>
            <label class="long"><input type="radio" name="freq" value="daily" ${p.frequency === 'daily' ? 'checked' : ''}><span>Daily report every morning at
              <select id="digest-hour" aria-label="Hour of the daily report">${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${+m.digest_hour === h ? 'selected' : ''}>${hourWords(h)}</option>`).join('')}</select>
              your time${browserTZ() ? ` (${t(browserTZ())})` : ''}: every new chart since the last report, with what each company does and the analysis, in one e-mail</span></label>
            <label><input type="radio" name="freq" value="instant" ${p.frequency !== 'daily' ? 'checked' : ''}> As soon as a chart is out (checked every 15 minutes)</label>
            <label class="long"><input type="checkbox" id="final-too" ${p.final_too !== false ? 'checked' : ''}><span>After a preliminary chart from an earnings release (8-K), also send the final one when the 10-Q/10-K is filed, marked as final and compared with the release</span></label></fieldset>
          <fieldset><legend>How</legend>
            <label><input type="checkbox" id="email-on" ${p.email_on ? 'checked' : ''}> E-mail to ${t(user.email)}: the chart, the analysis and what changed</label>
            <label><input type="checkbox" id="push-on" ${p.push_on ? 'checked' : ''}> Notifications in the Android app${appLink}</label></fieldset>
          <fieldset><legend>In each e-mail</legend>
            <p class="muted small">Every e-mail shows this quarter’s chart (tap it for the interactive one), the analysis and what changed. Also show:</p>
            <label><input type="checkbox" id="chart-q" ${m.chart_q ? 'checked' : ''}> The chart compared with the previous quarter</label>
            <label><input type="checkbox" id="chart-y" ${m.chart_y ? 'checked' : ''}> The chart compared with the same quarter a year earlier</label>
            <label class="long"><input type="checkbox" id="chart-history" ${m.chart_history ? 'checked' : ''}><span>History: revenue, operating profit, net earnings and operating cash flow for every quarter on file</span></label>
            <label class="long"><input type="checkbox" id="changes-detail" ${m.changes_detail ? 'checked' : ''}><span>Detail: every line of the chart with its change against a year earlier and the previous quarter (by default the e-mail lists the three main changes)</span></label>
            <label class="long"><input type="checkbox" id="cmp-decreases" ${m.cmp_decreases ? 'checked' : ''}><span>In comparison charts, also draw decreases as hatched areas with a dashed outline (the same as “Show decreases” on company pages)</span></label>
            <p class="muted small">Attached files</p>
            <div class="inline-radios" role="radiogroup" aria-label="Chart image files"><span>Chart images</span>${[['png', 'PNG'], ['jpg', 'JPG'], ['none', 'None']].map(([v, l]) =>
              `<label><input type="radio" name="attach" value="${v}" ${m.attach_images === v ? 'checked' : ''}> ${l}</label>`).join('')}</div>
            <label class="long"><input type="checkbox" id="attach-pdf" ${m.attach_pdf ? 'checked' : ''}><span>PDF report: company profile, the charts and the analysis</span></label></fieldset>
          <fieldset><legend>On company pages</legend>
            <label class="long"><input type="checkbox" id="custom-compare" ${m.custom_compare ? 'checked' : ''}><span>Compare any two periods: company pages get a ⇄ Compare any two button. Tick any two quarters (or two fiscal years) back to 2009–2011, when SEC’s XBRL data starts, and the comparison Sankey is drawn from SEC data within a few minutes</span></label></fieldset>
          <div class="row"><button class="btn primary" type="submit">Save</button><span class="muted" id="save-msg" role="status"></span></div>
        </form>
        <section class="section" id="requests"></section>
        <p class="muted small" style="margin-top:28px">To stop everything, untick e-mail and notifications and save, or use the unsubscribe link in any alert e-mail.</p>
        <div class="row danger"><button class="btn small" type="button" id="del-acct">Delete my account</button>
          <span id="del-confirm" hidden><span class="small">This removes your address and settings for good.</span>
          <button class="btn small warn" type="button" id="del-yes">Delete</button> <button class="btn small" type="button" id="del-no">Keep it</button></span>
          <span class="muted small" id="del-msg" role="status"></span></div>`;
      showRequests(c, ix);
      let list = (p.tickers || []).slice();
      const chips = () => {
        $('#chips').innerHTML = list.length ? list.map((x) => `<span class="chip"><a href="#home" data-tk="${t(x)}">${t(x)}</a>
          <button type="button" aria-label="Remove ${t(x)}" data-rm="${t(x)}">×</button></span>`).join('') : '<span class="muted small">None yet</span>';
        $$('#chips [data-rm]').forEach((b) => b.addEventListener('click', () => { list = list.filter((x) => x !== b.dataset.rm); chips(); }));
        $$('#chips [data-tk]').forEach((a) => {
          const co = ix.companies.find((x) => x.ticker === a.dataset.tk);
          if (co) a.href = `#c-${co.cik}`;
        });
      };
      chips();
      const add = () => {
        const v = $('#add-ticker').value.trim().toUpperCase();
        if (v && !list.includes(v)) list.push(v);
        $('#add-ticker').value = '';
        chips();
      };
      $('#add-btn').addEventListener('click', add);
      $('#add-ticker').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
      $('#sign-out').addEventListener('click', async () => { await c.auth.signOut(); acct.prefs = null; acct.owner = undefined; acct.osets = undefined; syncApp(); location.hash = 'home'; });
      $('#del-acct').addEventListener('click', () => { $('#del-confirm').hidden = false; $('#del-acct').hidden = true; });
      $('#del-no').addEventListener('click', () => { $('#del-confirm').hidden = true; $('#del-acct').hidden = false; });
      $('#del-yes').addEventListener('click', async () => {
        const r = await c.rpc('delete_account');
        if (r.error || r.data !== true) { $('#del-msg').textContent = `Could not delete: ${(r.error && r.error.message) || 'try again'}`; return; }
        await c.auth.signOut();
        acct.prefs = null;
        syncApp();
        app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Your account is deleted</h1>
          <p class="muted">Your address and settings are gone. You can sign up again at any time.</p><p><a href="#home">Back to the latest filings</a></p></div>`;
      });
      $('#prefs-form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        $('#save-msg').textContent = 'Saving…';
        try {
          await savePrefs({
            tickers: list, sectors: $$('input[name="sector"]:checked').map((x) => x.value),
            all_above: $('#all-above').checked, min_revenue: Math.round(Math.max(0, +$('#min-rev').value || 0) * 1e9),
            starred: $('#starred').checked, frequency: $('input[name="freq"]:checked').value, final_too: $('#final-too').checked,
            email_on: $('#email-on').checked, push_on: $('#push-on').checked,
            chart_q: $('#chart-q').checked, chart_y: $('#chart-y').checked, chart_history: $('#chart-history').checked,
            attach_images: ($('input[name="attach"]:checked') || {}).value || 'png', attach_pdf: $('#attach-pdf').checked,
            cmp_decreases: $('#cmp-decreases').checked, changes_detail: $('#changes-detail').checked,
            custom_compare: $('#custom-compare').checked, digest_hour: +$('#digest-hour').value,
          });
          state.decreases = $('#cmp-decreases').checked;           // company pages follow the account setting
          prefs.set('decreases', state.decreases);
          $('#save-msg').textContent = acct.flash || 'Saved.';
          acct.flash = null;
        } catch (err) {
          $('#save-msg').textContent = `Could not save: ${err.message}`;
        }
      });
    });
  }

  async function showRequests(c, ix) {
    const box = $('#requests');
    const r = await c.from('send_requests').select('*')            // '*': with or without the newer kind column
      .order('created_at', { ascending: false }).limit(10);
    if (!box || !box.isConnected) return;
    const byCik = new Map(ix.companies.map((x) => [String(x.cik), x]));
    const state = (x) => (x.status === 'sent' ? `sent ${date(x.sent_at)}` : x.status === 'failed' ? `not sent: ${t(x.error || 'error')}` : 'on its way');
    const rows = (r.data || []).map((x) => {
      const co = byCik.get(String(x.cik));
      const fy = x.kind === 'fy';
      if (x.kind === 'day') return `<tr><td>Daily report</td><td>filings dated ${date(x.period_end)}</td><td class="muted">${state(x)}</td></tr>`;
      return `<tr><td>${co ? `<a href="#c-${x.cik}-${fy ? 'fy-' : ''}${x.period_end}">${t(co.ticker || co.name)}</a>` : x.cik}</td>
        <td>${x.kind === 'thread' ? 'X thread · ' : ''}${fy ? 'fiscal year' : 'quarter'} ended ${date(x.period_end)}</td><td class="muted">${state(x)}</td></tr>`;
    }).join('');
    box.innerHTML = `<div class="section-head"><h2>Reports you asked for</h2><span class="muted">✉ Email me on any company page sends that quarter or fiscal year, old ones included</span></div>
      ${rows ? `<div class="tbl-wrap"><table><tbody>${rows}</tbody></table></div>` : '<p class="muted small">None yet.</p>'}`;
  }

  async function unsubscribePage(token) {
    setNav('account');
    const c = await sb();
    let ok = false;
    if (c) {
      const r = await c.rpc('unsubscribe', { token });
      ok = !r.error && r.data === true;
    }
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>${ok ? 'You are unsubscribed' : 'This link did not work'}</h1>
      <p class="muted" style="max-width:68ch">${ok ? 'No more alert e-mails will be sent. To turn them back on, sign in and tick “E-mail” in your alerts.'
        : 'The link may be old or already used. Sign in to change your alerts.'}</p><p><a href="#account">Manage alerts</a></p></div>`;
  }

  // ---------- owner tools: the X thread panel on company pages, for the site owner only ----------
  // With accounts switched on, only an account listed in Supabase's site_owners table (signed in) can use them; the
  // database answers "am I the owner?" without revealing the list. Without accounts, the switch is per browser only.
  async function ownerVerified() {
    const c = await sb();
    if (!c) return true;                                     // no accounts on this site: the browser switch decides
    if (!(await currentUser())) return false;
    if (acct.owner === undefined) {
      const r = await c.rpc('am_i_owner');
      acct.owner = !r.error && r.data === true;
    }
    return acct.owner;
  }
  async function ownerPage() {
    setNav('');
    const c = await sb();
    const user = c ? await currentUser() : null;
    const head = '<div class="eyebrow">Site owner</div><h1>Owner tools</h1>';
    const back = '<p><a href="#home">Back to the latest filings</a></p>';
    if (c && !user) {
      app.innerHTML = `<div class="page-head">${head}
        <p class="muted" style="max-width:68ch">Sign in with the site owner’s e-mail address to use the owner tools.</p>
        <p><a class="btn primary" href="#account" id="owner-signin">Sign in</a></p>${back}</div>`;
      $('#owner-signin').addEventListener('click', () => { prefs.set('pending-owner', true); prefs.set('after-signin', 'owner'); });
      return;
    }
    if (c && !(await ownerVerified())) {
      prefs.set('owner', false);
      app.innerHTML = `<div class="page-head">${head}
        <p class="muted" style="max-width:68ch">Signed in as <b>${t(user.email)}</b>, which is not a site owner’s address.
          The owner adds their address once in Supabase (SQL Editor:
          <span class="mono">insert into public.site_owners (email) values ('…');</span>).</p>${back}</div>`;
      return;
    }
    const on = prefs.get('owner', false);
    const osets = c ? await ownerSettings(true) : null;
    const o = Object.assign({ thread_direct: true, daily_on: true, daily_hour: 8, tz: browserTZ() || 'Asia/Shanghai',
      min_revenue: 1e9, instant_threads: false }, osets || {});
    const settingsHTML = !c ? `<p class="muted" style="max-width:68ch">Accounts are not switched on, so these settings come from
        <span class="mono">config/x.json</span> (keys daily_on, daily_hour, tz, min_revenue, instant_threads).</p>`
      : !osets ? `<p class="muted" style="max-width:68ch">${OWNER_UPDATE}: the owner settings table is new.</p>`
      : `<form class="prefs" id="owner-form">
        <fieldset><legend>“Email me this thread”</legend>
          <label class="long"><input type="radio" name="thread-mail" value="direct" ${o.thread_direct ? 'checked' : ''}><span>Send it straight to my inbox
            (${t(user.email)}), with both chart PNGs attached, usually within two minutes</span></label>
          <label class="long"><input type="radio" name="thread-mail" value="github" ${o.thread_direct ? '' : 'checked'}><span>Open a GitHub issue with the
            request filled in (the older way: press Create on GitHub)</span></label></fieldset>
        <fieldset><legend>Daily report</legend>
          <label class="long"><input type="checkbox" id="daily-on" ${o.daily_on ? 'checked' : ''}><span>Every morning at
            <select id="daily-hour" aria-label="Hour of the daily report">${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${+o.daily_hour === h ? 'selected' : ''}>${hourWords(h)}</option>`).join('')}</select>
            ${t(browserTZ() || o.tz)} time: every filing since the last report — what the company does, the charts, the analysis and the
            ready-to-post X thread — in one e-mail to ${t(user.email)}</span></label>
          <label>Companies with quarterly revenue of at least $<input type="number" id="daily-min" min="0" step="0.1"
            value="${(+o.min_revenue / 1e9).toFixed(2).replace(/\.?0+$/, '')}" style="width:5em"> billion</label>
          <label class="long"><input type="checkbox" id="instant-threads" ${o.instant_threads ? 'checked' : ''}><span>Also e-mail the new X threads
            right after each scan (as before the daily report)</span></label></fieldset>
        <div class="row"><button class="btn primary" type="submit">Save</button><span class="muted" id="owner-msg" role="status"></span></div>
      </form>`;
    app.innerHTML = `<div class="page-head">${head}
      <p class="muted" style="max-width:68ch">Readers never see these. ${c ? `Verified: signed in as <b>${t(user.email)}</b>.`
          : 'Accounts are not switched on for this site, so the switch below only stays in this browser.'}</p></div>
      <section class="section"><div class="section-head"><h2>X thread on company pages</h2></div>
        <p class="muted" style="max-width:68ch">Shows the ready-to-post thread under each quarter in this browser: the filing, what each image shows
          (with Save PNG), every post with Copy, and “Email me this thread”.</p>
        <p><button class="btn${on ? '' : ' primary'}" type="button" id="owner-toggle">${on ? 'Turn off in this browser' : 'Turn on in this browser'}</button></p>
        <p class="muted" id="owner-state">${on ? 'On: company pages show the X thread.' : 'Off: company pages look the same as for readers.'}</p></section>
      <section class="section"><div class="section-head"><h2>Settings</h2></div>${settingsHTML}</section>
      <section class="section daily" id="daily" hidden></section>
      ${back}`;
    $('#owner-toggle').addEventListener('click', () => { prefs.set('owner', !on); ownerPage(); });
    const form = $('#owner-form');
    if (form) form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      $('#owner-msg').textContent = 'Saving…';
      const patch = { thread_direct: $('input[name="thread-mail"]:checked').value === 'direct', daily_on: $('#daily-on').checked,
        daily_hour: +$('#daily-hour').value, tz: browserTZ() || o.tz, min_revenue: Math.round(Math.max(0, +$('#daily-min').value || 0) * 1e9),
        instant_threads: $('#instant-threads').checked, updated_at: new Date().toISOString() };
      const r = await c.from('owner_settings').update(patch).eq('id', true).select().single();
      if (r.error) { $('#owner-msg').textContent = `Could not save: ${r.error.message}`; return; }
      acct.osets = r.data;
      $('#owner-msg').textContent = 'Saved.';
      getJSON('index.json').then((ix) => dailyPanel($('#daily'), ix, { title: 'Send a daily report now' })).catch(() => {});
    });
    if (c) getJSON('index.json').then((ix) => dailyPanel($('#daily'), ix, { title: 'Send a daily report now' })).catch(() => {});
  }
  async function ownerSettings(fresh) {
    const c = await sb();
    if (!c) return null;
    if (acct.osets !== undefined && !fresh) return acct.osets;
    const r = await c.from('owner_settings').select('*').maybeSingle();
    acct.osets = r.error ? null : (r.data || null);
    return acct.osets;
  }

  // ---------- router ----------
  async function route() {
    state.charts = [];
    if (toastEl) { toastEl.remove(); toastEl = null; }
    let h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    if (/^(access_token|error)=/.test(h)) {               // back from a link in a sign-in e-mail (if a template sends links)
      const failed = h.startsWith('error=');
      const user = failed ? null : await currentUser().catch(() => null);   // Supabase reads the sign-in from the address
      acct.flash = failed ? 'That sign-in link has expired or was used already. Enter your e-mail for a new code.'
        : user ? 'Signed in' : null;
      history.replaceState(null, '', location.pathname + location.search + '#account');
      h = 'account';
    }
    let m;
    try {
      if ((m = /^c-(\d+)-fy-(\d{4}-\d{2}-\d{2})$/.exec(h))) await company(m[1], m[2], false, { fy: true });
      else if ((m = /^c-(\d+)-cmp-(\d+)$/.exec(h))) await company(m[1], null, false, { cmp: m[2] });
      else if ((m = /^c-(\d+)(?:-(\d{4}-\d{2}-\d{2}|all))?$/.exec(h))) await company(m[1], m[2] !== 'all' ? m[2] : null, m[2] === 'all');
      else if ((m = /^([si])-([a-z0-9-]+?)(?:-(CY\d{4}Q\d))?$/.exec(h))) await group(m[1], m[2], m[3]);
      else if (h === 'sectors') await sectorsPage();
      else if (h === 'method') await methodPage();
      else if (h === 'account') await accountPage();
      else if (h === 'owner') await ownerPage();
      else if ((m = /^unsubscribe-([0-9a-f-]{36})$/.exec(h))) await unsubscribePage(m[1]);
      else await home();
      initFollowButtons();
      initSendButtons();
      if (acct.flash) { toast(acct.flash); acct.flash = null; }
    } catch (err) {
      app.innerHTML = `<div class="page-head"><h1>Not available</h1><p class="muted">${t(err.message)}. The data may not have been generated yet; the scan runs every 15 minutes.</p><p><a href="#home">Back to the latest filings</a></p></div>`;
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
  if (window.FilingFlowsApp) currentUser().then((u) => u && !acct.prefs && loadPrefs()).catch(() => {});   // the app's notifications use the follows
})();
