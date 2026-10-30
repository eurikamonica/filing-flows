/* The site's top navigation, in four groups, shared by the app (index.html) and the Disclosure Hub (disclosures/):
 *   Companies · Industries & themes · Market signals · Method
 * On a wide screen each group opens a menu (hover, click or keyboard); on a phone the whole navigation folds into one
 * menu button. <nav class="nav" id="site-nav" data-base="../" data-here="disclosures"> is filled in here, so the list
 * of pages lives in one place. FFNav.mark() highlights the group of the current page (the app calls it on each route). */
(function (global) {
  'use strict';
  const GROUPS = [
    { id: 'companies', label: 'Companies', items: [
      ['home', '#home', 'Latest filings', 'Every new 10-Q, 10-K and earnings release, drawn'],
      ['ipo', '#ipo', 'IPO & prospectuses', 'S-1 / F-1 filings, quality measures and cash-flow Sankeys'],
      ['chart', '#chart', 'Charts', 'Any company’s figures over time, side by side'],
      ['studio', '#studio', 'Videos', 'Animated charts to post: growth races, rankings, RRG, earnings'],
      ['az', 'c/', 'All companies A–Z', 'Every company with an earnings Sankey'],
    ] },
    { id: 'industries', label: 'Industries & themes', items: [
      ['sectors', '#sectors', 'Sectors', 'Sector and industry totals, quarter by quarter'],
      ['gamma', '#gamma', 'Industries (SIC)', 'Growth distributions and who sells to whom'],
      ['chains', '#chains', 'Supply chains & themes', 'Where the money flows: AI capex, power, GLP-1…'],
      ['model', '#model', 'Growth model', 'Company, industry, sector and theme forecasts'],
    ] },
    { id: 'signals', label: 'Market signals', items: [
      ['feed', '#feed', 'Feed', 'What changed today, across the site'],
      ['etfs', 'disclosures/#etf', 'ETF scanner', 'Every US-listed ETF: prices, distributions, prospectus, holdings'],
      ['disclosures', 'disclosures/', 'Disclosures', '13F flows, insiders, officials, short interest…'],
      ['cross', 'disclosures/#cross', 'Cross-holdings', 'Who holds whom: US government, the President, Congress, Nvidia, Alphabet…'],
      ['account', '#account', 'Alerts', 'E-mail when your companies file'],
    ] },
    { id: 'method', label: 'Method', href: '#method', nav: 'method' },
  ];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function href(base, h, here) {
    if (here === 'disclosures' && h.startsWith('disclosures/')) return './' + h.slice(12);
    return base + h;
  }

  function build(nav) {
    const base = nav.dataset.base || '', here = nav.dataset.here || '';
    nav.innerHTML = GROUPS.map((g) => {
      if (g.href) return `<a class="nav-top" href="${esc(href(base, g.href, here))}" data-nav="${g.nav}">${esc(g.label)}</a>`;
      return `<div class="nav-group" data-group="${g.id}"><button class="nav-top" type="button" aria-expanded="false" aria-haspopup="true">${esc(g.label)}<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></button>
        <div class="nav-menu" role="menu">${g.items.map(([id, h, l, d]) =>
          `<a role="menuitem" href="${esc(href(base, h, here))}" data-nav="${id}"${here === id ? ' class="on" aria-current="page"' : ''}><b>${esc(l)}</b><span>${esc(d)}</span></a>`).join('')}</div></div>`;
    }).join('') +
      // phones: the site's settings live in this menu instead of a lone button beside the logo (web/appearance.js)
      '<button class="nav-top nav-settings" type="button">Settings &amp; appearance</button>';
    const settings = nav.querySelector('.nav-settings');
    settings.addEventListener('click', () => {
      setMobile(false);
      const A = global.FFAppearance;
      if (A && A.open) A.open(); else { const b = document.getElementById('ff-appearance-button'); if (b) b.click(); }
    });
    const groups = Array.from(nav.querySelectorAll('.nav-group'));
    const close = (except) => groups.forEach((g) => { if (g !== except) { g.classList.remove('open'); g.querySelector('.nav-top').setAttribute('aria-expanded', 'false'); } });
    groups.forEach((g) => {
      const b = g.querySelector('.nav-top');
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const open = !g.classList.contains('open');
        close(g);
        g.classList.toggle('open', open);
        b.setAttribute('aria-expanded', String(open));
      });
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') { close(); b.focus(); } });
    });
    nav.addEventListener('click', (ev) => { if (ev.target.closest('a')) { close(); setMobile(false); } });
    document.addEventListener('click', (ev) => { if (!nav.contains(ev.target)) close(); });
    // phones: one menu button for the whole navigation
    const header = nav.closest('header');
    let btn = header && header.querySelector('.menu-btn');
    if (header && !btn) {
      btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'menu-btn';
      btn.setAttribute('aria-label', 'Menu');
      btn.setAttribute('aria-controls', nav.id || '');
      btn.setAttribute('aria-expanded', 'false');
      btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 4.5h14M2 9h14M2 13.5h14" stroke="currentColor" stroke-width="1.6"/></svg>';
      nav.parentNode.insertBefore(btn, nav);
    }
    function setMobile(open) {
      if (!header || !btn) return;
      header.classList.toggle('nav-open', open);
      btn.setAttribute('aria-expanded', String(open));
    }
    if (btn) btn.addEventListener('click', (ev) => { ev.stopPropagation(); setMobile(!header.classList.contains('nav-open')); });
    document.addEventListener('click', (ev) => { if (header && !header.contains(ev.target)) setMobile(false); });
    global.addEventListener('hashchange', () => { close(); setMobile(false); });
    mark();
  }

  function mark() {
    document.querySelectorAll('.nav').forEach((nav) => {
      nav.querySelectorAll('.nav-group').forEach((g) => g.classList.toggle('on', !!g.querySelector('a.on')));
    });
  }

  function init() { document.querySelectorAll('nav.nav[data-ff-nav]:not([data-built])').forEach((n) => { n.dataset.built = '1'; build(n); }); }
  init();                                                   // the script comes right after the header: build at once
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  global.FFNav = { mark, GROUPS };
})(window);
