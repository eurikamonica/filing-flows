/* The site's top navigation, in six groups — every page of the site, the Disclosures sections among them:
 *   Companies · Industries & themes · Money & people · Filings & news · Markets & odds · Method
 * On a wide screen each group opens a menu (hover, click or keyboard); on a phone the whole navigation folds into one
 * menu button. <nav class="nav" id="site-nav" data-base="../" data-here="disclosures"> is filled in here, so the list
 * of pages lives in one place. FFNav.mark() highlights the group of the current page (the app calls it on each route). */
(function (global) {
  'use strict';
  // every page of the site, the Disclosures sections included (they open here: web/hub-shell.js)
  const GROUPS = [
    { id: 'companies', label: 'Companies', items: [
      ['home', '#home', 'Latest filings', 'Every new 10-Q, 10-K and earnings release, drawn'],
      ['ipo', '#ipo', 'IPO & prospectuses', 'S-1 / F-1 filings, quality measures and cash-flow Sankeys'],
      ['chart', '#chart', 'Charts', 'Any company’s figures over time, side by side'],
      ['studio', '#studio', 'Videos', 'Animated charts to post: growth races, rankings, holders, earnings'],
      ['screener', '#screener', 'Screener', 'Every company by its figures, ready-made screens'],
      ['valuation', '#valuation', 'Valuation', 'Fair value by every method, company by company'],
      ['consensus', '#consensus', 'Consensus & odds', 'Analysts, prediction markets and the earnings calendar'],
      ['quality', '#quality', 'Earnings quality', 'Accruals, cash conversion, reserves'],
      ['traps', '#traps', 'Analysis traps', 'Where the figures mislead, with the innocent explanation'],
      ['buyouts', '#buyouts', 'Buyouts', 'Who a private buyer could take over, and at what price'],
      ['composer', '#composer', 'Chart composer', 'A page of charts for one stock or ETF, to print or post'],
      ['az', 'c/', 'All companies A–Z', 'Every company with an earnings Sankey'],
    ] },
    { id: 'industries', label: 'Industries & themes', items: [
      ['sectors', '#sectors', 'Sectors & industries', 'Every sector and SIC industry: combined charts, growth, who sells to whom'],
      ['chains', '#chains', 'Supply chains & themes', 'Where the money flows: AI capex, power, GLP-1…'],
      ['model', '#model', 'Growth model', 'Company, industry, sector and theme forecasts'],
      ['rotation', '#rotation', 'Rotation (RRG)', 'Which sectors and themes lead, week by week'],
      ['maps', '#maps', 'Market maps', 'Money flows, heatmaps, the ownership network'],
      ['workforce', '#workforce', 'Workforce', 'Headcount and pay from the filings'],
    ] },
    { id: 'money', label: 'Money & people', items: [
      ['signals', '#signals', 'Signals', 'What funds, insiders and officials did, this quarter'],
      ['smart', '#smart', 'Smart money', 'Every disclosed trade, scored by what came next'],
      ['allflows', '#allflows', 'All flows', '13F, ETFs, insiders and officials together'],
      ['flows', '#flows', 'Market flows', 'What the 13F managers added, sold and net-bought'],
      ['holdings', '#holdings', '13F managers', 'Each manager’s quarters and moves'],
      ['insiders', '#insiders', 'Insider trades', 'Form 4 buying and selling'],
      ['form144', '#form144', 'Form 144', 'Planned sales by officers and directors'],
      ['trades', '#trades', 'Officials’ trades', 'Congress, the President and state officials'],
      ['stakes', '#stakes', '13D / 13G stakes', 'Who owns more than 5%'],
      ['cross', '#cross', 'Cross-holdings', 'Who holds whom: US government, the President, Congress, Nvidia, Alphabet…'],
      ['investors', '#investors', 'Corporate investors', 'What companies invest in: private stakes, 13F holdings'],
      ['etf', '#etf', 'ETFs', 'Every US-listed ETF: prices, distributions, prospectus, holdings'],
      ['people', '#people', 'People & index', 'Every manager, official and insider: copy-the-filings backtests'],
    ] },
    { id: 'filings', label: 'Filings & news', items: [
      ['feed', '#feed', 'Your feed', 'What the companies you follow disclosed, newest first'],
      ['daily', 'daily/', 'Today in the filings', 'The whole market’s disclosures, each day'],
      ['events', '#events', '8-K events', 'Deals, new debt, impairments, restatements, leadership changes'],
      ['news', '#news', 'News', 'Press releases, FDA approvals, SEC actions'],
      ['calls', '#calls', 'Earnings calls', 'What management said, and practice questions'],
      ['earnings', '#earnings', 'Earnings season', 'Who reports when, and how they did'],
      ['filings', '#filings', 'Filings radar', 'Unusual filings worth a look'],
      ['guidance', '#guidance', 'Guidance', 'What companies forecast, and how it turned out'],
      ['notes', '#notes', 'Notes & ties', 'Every note of a 10-K drawn, and how the figures tie'],
      ['hidden', '#hidden', 'Hidden leverage', 'Leases, guarantees and contracts off the balance sheet'],
      ['outside', '#outside', 'Beyond the filings', 'Free public data on companies: jobs, web, patents…'],
      ['debt', '#debt', 'Debt & rates', 'Maturities, coverage, market rates and banks’ CDs'],
      ['account', '#account', 'Alerts', 'E-mail when your companies file'],
    ] },
    { id: 'markets', label: 'Markets & odds', items: [
      ['options', '#options', 'Options', 'Walls, max pain and the paths prices can take'],
      ['paths', '#paths', 'Price paths', 'Seven path models and price patterns'],
      ['moves', '#moves', 'Move odds', 'How far prices move after an event'],
      ['forecast', '#forecast', 'Close forecast', 'Where prices close today, this week and this quarter'],
      ['odds', '#odds', 'Odds', 'Rotation forecasts and how they did'],
      ['mmodels', '#mmodels', 'Market models', 'The market’s valuation gauges'],
      ['opportunity', '#opportunity', 'Opportunity', 'Stocks and ETFs off their usual range'],
      ['momentum', '#momentum', 'Momentum', 'Stocks, ETFs and sectors ranked by absolute, relative and composite momentum'],
      ['strategies', '#strategies', 'Strategies', 'Rules tested on the site’s data'],
      ['shorts', '#shorts', 'Short interest', 'FINRA short positions, twice a month'],
      ['cot', '#cot', 'COT', 'Futures positions by trader type'],
    ] },
    { id: 'method', label: 'Method', items: [
      ['method', '#method', 'Method', 'How every figure is read and drawn'],
      ['data', '#data', 'Data catalog', 'Every kind of data: its source, its one home, how fresh'],
      ['status', '#status', 'Data health', 'Every source: when it was last read'],
      ['directory', '#directory', 'Directory', 'Every manager, official and filer collected'],
      ['npx', '#npx', 'Proxy votes (N-PX)', 'How funds voted'],
      ['banks', '#banks', 'Banks (FDIC)', 'Bank financials'],
      ['congress', '#congress', 'Officials’ reports', 'The disclosure records as filed'],
      ['review', '#review', 'PDF / OCR review', 'Check scanned reports against the official page'],
    ] },
  ];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function href(base, h, here) {
    if (here === 'disclosures' && h.startsWith('disclosures/')) return './' + h.slice(12);
    return base + h;
  }

  function build(nav) {
    const base = nav.dataset.base || '', here = nav.dataset.here || '';
    nav.innerHTML = GROUPS.map((g, gi) => {
      if (g.href) return `<a class="nav-top" href="${esc(href(base, g.href, here))}" data-nav="${g.nav}">${esc(g.label)}</a>`;
      return `<div class="nav-group${gi >= GROUPS.length - 2 ? ' end' : ''}" data-group="${g.id}"><button class="nav-top" type="button" aria-expanded="false" aria-haspopup="true">${esc(g.label)}<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></button>
        <div class="nav-menu${g.items.length > 7 ? ' wide' : ''}" role="menu">${g.items.map(([id, h, l, d]) =>
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
