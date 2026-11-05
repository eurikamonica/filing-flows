/* The Disclosures sections as pages of the site: #signals, #smart, #etf/SPY, #rotation/rrg … open here, under the site's
 * own header, search, theme and footer — no second site. The hub's page (disclosures/index.html) is read once for its
 * sections, its styles and its scripts; the scripts load the first time a section opens, into a container kept beside
 * the app's own (#hub-root: they bind to it once and keep their state as the reader moves between pages), and read the
 * hub's data under disclosures/ (window.FF_HUB_ROOT) and link to the site's pages from here (window.FF_SITE_ROOT). The
 * hub's styles apply inside the container only (each rule scoped to #hub-root as it loads).
 * The app's router (app.js) sends every address that names a section here; disclosures/ itself forwards to it. */
(function (root) {
  'use strict';
  const HUB = 'disclosures/';
  root.FF_HUB_ROOT = HUB;                         // the hub's scripts read their data from here
  root.FF_SITE_ROOT = '';                         // and link to the site's own pages from here
  // the sections (disclosures/index.html's buttons; the page read at load adds any new one)
  const TABS = new Set(('signals smart allflows flows insiders trades stakes form144 events news calls earnings filings options paths '
    + 'opportunity strategies odds mmodels moves rotation composer shorts maps etf cot valuation consensus quality screener traps '
    + 'workforce outside notes guidance buyouts debt hidden cross people holdings congress npx banks review directory status').split(' '));
  const LABEL = {};
  // the site's own page answers these (the hub's version of it is not shown twice)
  const SITE = new Set(['investors']);
  // the site's navigation leads to every section: the hub's own picker is not needed here
  const EXTRA = `
#hub-root .hub-layout{display:block}
#hub-root nav.modules{display:none}
#hub-root .hub-head{margin-bottom:10px;padding-bottom:0}
#hub-root .hub-head .crumbs{margin:0 0 2px}
#hub-root .hub-head h1{margin:2px 0 4px}
#hub-root .hub-head .intro{max-width:none;margin:2px 0 0;padding:0;border:0;font-size:13px;line-height:1.5;color:var(--muted)}
#hub-root .hub-head .intro .src{display:inline;margin:0}
#hub-root .hub-head .hub-sources{display:inline}
#hub-root .hub-head .hub-sources[open]{display:block;margin:4px 0}
#hub-root .hub-head .mode-pick{display:inline-flex;gap:6px;align-items:center;margin-left:10px;white-space:nowrap}
#hub-root .hub-head .mode-pick select{font-size:12px;padding:2px 6px;min-height:0}
#hub-root.hub-loading .hub-main::before{content:'Loading…';color:var(--muted)}
/* a section that opens with its own title: that is the page's title (the h1 stays for screen readers) */
#hub-root:has(#workspace > .section-head:first-child h2) #hub-title{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
`;
  let ready = null, box = null, app = null;
  const TITLE = typeof document !== 'undefined' ? document.title : '';
  const owns = (h) => { const t = String(h || '').replace(/^#\/?/, '').split('/')[0]; return TABS.has(t) && !SITE.has(t); };

  // a stylesheet's rules, each kept to the container: ':root' is the container (its colours), 'body' the box inside it,
  // 'html[…]' and ':root[…]' (the theme) stay in front
  function scope(css, S, B) {
    B = B || S;
    css = String(css || '').replace(/\/\*[\s\S]*?\*\//g, '');
    let out = '', i = 0;
    const sel = (list) => {
      const parts = [];
      let depth = 0, cur = '';
      for (const ch of list) {
        if (ch === '(' || ch === '[') depth++;
        else if (ch === ')' || ch === ']') depth--;
        if (ch === ',' && !depth) { parts.push(cur); cur = ''; } else cur += ch;
      }
      parts.push(cur);
      return parts.map((p) => {
        let s = p.trim();
        if (!s) return s;
        if (/^(html|:root)\b/.test(s)) {
          const m = /^(html|:root)((\[[^\]]*\]|[.:#][\w-]+(\([^)]*\))?)*)/.exec(s), attrs = m[2], rest = s.slice(m[0].length).trim();
          if (!attrs && m[1] === ':root' && !rest) return S;                              // the colours: on the container
          const head = 'html' + attrs;
          if (!rest) return head + ' ' + S;
          return rest.startsWith('body') ? head + ' ' + B + rest.slice(4) : head + ' ' + S + ' ' + rest;
        }
        if (/^body\b/.test(s)) return B + s.slice(4);
        return S + ' ' + s;
      }).join(', ');
    };
    while (i < css.length) {
      const open = css.indexOf('{', i), semi = css.indexOf(';', i);
      if (open < 0) break;
      if (semi >= 0 && semi < open && /^\s*@/.test(css.slice(i, semi))) { out += css.slice(i, semi + 1) + '\n'; i = semi + 1; continue; }
      const head = css.slice(i, open).trim();
      let depth = 1, j = open + 1;
      while (j < css.length && depth) { if (css[j] === '{') depth++; else if (css[j] === '}') depth--; j++; }
      const body = css.slice(open + 1, j - 1);
      if (/^@(media|supports|container|layer)\b/.test(head)) out += head + '{' + scope(body, S, B) + '}\n';
      else if (/^@/.test(head)) out += head + '{' + body + '}\n';            // @keyframes, @font-face, @page: as they are
      else if (head) out += sel(head) + '{' + body + '}\n';
      i = j;
    }
    return out;
  }

  // a script of the hub's page: downloaded in parallel with the others, run in the page's order (async = false)
  const script = (src) => new Promise((ok, bad) => {
    const el = document.createElement('script');
    el.src = src;
    el.async = false;
    el.onload = () => ok();
    el.onerror = () => bad(new Error(src + ' did not load'));
    document.head.appendChild(el);
  });

  async function load() {
    const html = await fetch(HUB + 'index.html', { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('the Disclosures page did not load (HTTP ' + r.status + ')'); return r.text(); });
    const doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('nav button[data-tab]').forEach((b) => { if (SITE.has(b.dataset.tab)) return; TABS.add(b.dataset.tab); LABEL[b.dataset.tab] = b.textContent.trim(); });
    // the styles first (the hub's own; the site's nav and refresh styles are on the page already)
    const sheets = [...doc.querySelectorAll('link[rel="stylesheet"]')].map((l) => l.getAttribute('href') || '').filter((h) => h && !/^(\.\.\/|https?:|\/\/)/.test(h));
    const css = await Promise.all(sheets.map((h) => fetch(HUB + h).then((r) => (r.ok ? r.text() : '')).catch(() => '')));
    const st = document.createElement('style');
    st.id = 'hub-css';
    st.textContent = css.map((c) => scope(c, '#hub-root', '#hub-root > .hub-body')).join('\n') + EXTRA;
    document.head.appendChild(st);
    // the container: the section's title and the hub's sources, its data switch, the section picker and the workspace
    app = document.getElementById('app');
    box = document.createElement('main');
    box.id = 'hub-root';
    box.className = 'wrap hub-root';
    box.hidden = true;
    const intro = doc.querySelector('.page-head .intro'), mode = doc.getElementById('mode'), layout = doc.querySelector('.hub-layout');
    if (!layout) throw new Error('the Disclosures page has no sections');
    box.innerHTML = `<div class="hub-body"><section class="page-head hub-head">`
      + `<div class="crumbs"><a href="#signals">Disclosures</a><span>›</span><span id="hub-crumb">Signals</span></div><h1 id="hub-title">Disclosures</h1>`
      + `<div class="intro">${intro ? intro.innerHTML : ''}<label class="mode-pick" for="mode"><span>Data</span> ${mode ? mode.outerHTML : '<select id="mode"><option value="official">Official snapshot</option></select>'}</label></div></section>`
      + layout.outerHTML + '</div>';
    if (!box.querySelector('#buildtime')) box.querySelector('.intro').insertAdjacentHTML('beforeend', '<span class="src" id="buildtime"></span>');
    app.after(box);
    // the scripts in the page's order; the site's own (../) are loaded already
    const list = [...doc.querySelectorAll('script[src]')].map((s) => s.getAttribute('src') || '').filter((s) => s && !/^(\.\.\/|https?:|\/\/)/.test(s));
    box.classList.add('hub-loading');
    await Promise.all(list.map((s) => script(HUB + s)));    // ~80 files: one after the other took ~8 s on the live site
    box.classList.remove('hub-loading');
    // links the hub writes for its own page (./#x, disclosures/#x) open here
    box.addEventListener('click', (e) => {
      const a = e.target.closest('a[href]');
      if (!a) return;
      const h = a.getAttribute('href');
      const m = /^(?:\.\/|disclosures\/|\.\.\/disclosures\/)(#.*)$/.exec(h || '');
      if (m) { e.preventDefault(); location.hash = m[1]; }
    });
  }

  function title(h) {
    const tab = String(h || '').replace(/^#\/?/, '').split('/')[0], t = document.getElementById('hub-title');
    const lab = LABEL[tab] || (document.querySelector(`#hub-root nav button[data-tab="${tab}"]`) || {}).textContent || 'Disclosures';
    const c = document.getElementById('hub-crumb');
    if (t) t.textContent = lab;
    if (c) c.textContent = lab;
    document.title = lab + ' · Filing Flows';
    return tab;
  }

  // the app's router: a section's address → this container, the app's own pages hidden; its first visit loads the hub
  async function show(h, ctx) {
    app = app || document.getElementById('app');
    if (!ready) ready = load().catch((e) => { ready = null; throw e; });
    if (!box) { app.hidden = false; app.innerHTML = '<div class="page-head"><p class="muted">Loading Disclosures…</p></div>'; }
    await ready;
    if (ctx && ctx.here && !ctx.here()) return null;        // the reader went on to another page while the hub loaded
    app.hidden = true;
    box.hidden = false;
    const tab = title(h);
    if (ctx && ctx.setNav) ctx.setNav(tab);
    // the hub follows the address itself (its hashchange); its first load read it already
    return tab;
  }
  // another page of the site: the container hidden, the page's own title back, and nothing of the page shown before it
  function hide() {
    if (box && !box.hidden) {
      box.hidden = true;
      if (app) app.innerHTML = '';
      document.title = TITLE;
    }
    if (app) app.hidden = false;
  }
  root.FFHubShell = { owns, show, hide, scope, TABS, LABEL };
  if (typeof module !== 'undefined') module.exports = root.FFHubShell;
})(typeof window !== 'undefined' ? window : globalThis);
