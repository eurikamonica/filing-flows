// momentum.js (the Hub's Momentum tab): the leaderboards from the latest-week files with the shapes app/momentum.py
// writes (companies; ETFs with the rank inside the asset class), the sectors and styles computed here from rrg.json by
// momentum-view.js, the breadth tiles, the summary by sector, the filters and sorts, the short horizons (a day to a
// quarter, from the Move odds index), the CSV rows, the deep links and a ticker's history. The hub's helpers and fetch stubbed; no browser, no network.
const assert = require('node:assert/strict');
const path = require('node:path');
global.window = global;
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.compact = (v) => (Math.abs(v) >= 1e9 ? fmt(v / 1e9, 2) + 'B' : Math.abs(v) >= 1e6 ? fmt(v / 1e6, 2) + 'M' : fmt(v, 1));
global.uniq = (a) => [...new Set(a)];
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.field = (id, label, items, v) => `<select id="${id}">${items.map((x) => `<option value="${esc(x[0])}"${String(x[0]) === String(v) ? ' selected' : ''}>${esc(x[1])}</option>`).join('')}</select>`;
global.table = (h, rows) => `<table class="lb"><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.head = (t, s, tag) => `<h2>${t}</h2><p class="sub">${s}</p><span>${tag}</span>`;
global.state = { tab: 'momentum' };
global.exported = [];
let renders = 0;
global.render = () => { renders++; };
const MV = require(path.join(__dirname, '..', 'docs', 'momentum-view.js'));
const M = require(path.join(__dirname, '..', 'docs', 'momentum.js'));
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, m, tol = 1e-12) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const tick = () => new Promise((r) => setTimeout(r, 0));

// the latest-week files (app/momentum.py build: LATEST, the percentiles of FIELDS, [p_comp_group], the meta columns sorted)
const LATEST = ['m12_1', 'm6_1', 'm1', 'hi52', 'vol', 'ra12', 'comp', 'rel_b', 'rel_s', 'rcomp'];
const P = ['p_m12_1', 'p_m6_1', 'p_hi52', 'p_ra12', 'p_comp'];
const STOCKS = { v: 1, generated_at: '2026-11-08T03:00:00+00:00', universe: 'momentum', week: '2026-11-06', month: '2026-10-30', n: 8, cols: [...LATEST, ...P, 'n', 's'],
  rows: {
    NVDA: [0.8, 0.3, 0.05, -0.02, 0.45, 1.78, 2.1, 0.4, 0.2, 1.5, 95, 90, 92, 88, 100, 'NVIDIA', 'technology'],
    AAPL: [0.1, 0.05, -0.01, -0.08, 0.25, 0.4, 0.4, -0.05, -0.2, -0.3, 55, 50, 60, 52, 62, 'Apple', 'technology'],
    MSFT: [0.2, 0.1, 0.02, -0.03, 0.22, 0.91, 1.2, 0.05, -0.1, 0.4, 70, 65, 80, 75, 85, 'Microsoft', 'technology'],
    XOM: [-0.1, -0.05, 0.01, -0.15, 0.25, -0.4, -0.6, -0.25, 0.02, -1.1, 20, 25, 30, 22, 25, 'Exxon Mobil', 'energy'],
    CVX: [-0.2, -0.1, -0.02, -0.2, 0.24, -0.83, -1.3, -0.35, -0.05, -1.6, 10, 15, 15, 12, 12, 'Chevron', 'energy'],
    OXY: [0.05, 0.0, 0.0, -0.1, 0.3, 0.17, 0.1, -0.1, 0.1, -0.5, 45, 45, 45, 45, 50, 'Occidental', 'energy'],
    JPM: [0.3, 0.15, 0.03, -0.01, 0.2, 1.5, 1.4, 0.15, 0.08, 0.9, 80, 80, 95, 92, 90, 'JPMorgan', 'financials'],
    NEWC: [null, 0.1, 0.01, null, null, null, null, null, null, null, null, 70, null, null, null, 'Newco', 'financials'],
  } };
const ETFS = { v: 1, generated_at: '2026-11-08T04:00:00+00:00', universe: 'momentum', week: '2026-11-06', month: '2026-10-30', n: 6, cols: [...LATEST, ...P, 'p_comp_group', 'ac', 'aum', 'dv', 'n'],
  rows: {
    SPY: [0.15, 0.08, 0.01, -0.02, 0.15, 1.0, 1.1, 0, null, null, 60, 55, 80, 70, 70, 60, 'Equity', 6e11, 3e10, 'SPDR S&P 500'],
    QQQ: [0.25, 0.12, 0.02, -0.01, 0.2, 1.25, 1.6, 0.09, null, 0.8, 75, 70, 90, 80, 85, 80, 'Equity', 3e11, 2e10, 'Invesco QQQ'],
    SMH: [0.6, 0.2, 0.04, -0.03, 0.35, 1.7, 1.9, 0.33, null, 1.4, 95, 85, 85, 95, 95, 100, 'Equity', 3e10, 2e9, 'VanEck Semiconductor'],
    TINY: [0.9, 0.5, 0.1, 0, 0.6, 1.5, 2.5, 0.6, null, 1.8, 100, 100, 100, 90, 100, 100, 'Equity', 5e6, 1e4, 'Tiny Theme ETF'],
    GLD: [0.3, 0.2, 0.03, -0.04, 0.16, 1.9, 2.0, 0.12, null, 1.1, 85, 95, 75, 100, 98, null, 'Commodity: precious metals', 1e11, 4e9, 'SPDR Gold'],
    TLT: [-0.05, -0.02, 0.0, -0.12, 0.14, -0.36, -0.5, -0.2, null, -1.4, 10, 10, 10, 10, 10, null, 'Fixed income', 5e10, 3e9, 'iShares 20+ Year Treasury'],
  } };
// rrg.json: SPY, four sector ETFs, two style ETFs, a site sector index and a line of another kind (left out)
const N = 300, start = '2018-01-05';
const W = Array.from({ length: N }, (_, i) => new Date(Date.parse(start) + 7 * i * 864e5).toISOString().slice(0, 10));
const close = (mu, a, ph) => Array.from({ length: N }, (_, t) => +(100 * Math.exp(mu * t + a * Math.sin(t / 6 + ph))).toFixed(4));
const RRG = { generated_at: '2026-11-08T02:00:00+00:00', benchmark: 'SPY', start, weeks: W[N - 1], bench: { id: 'SPY', start, c: close(0.002, 0.01, 0) },
  series: [
    { id: 'XLK', name: 'Technology (XLK)', group: 'sector-etf', sector: 'technology', start, c: close(0.004, 0.03, 1) },
    { id: 'XLE', name: 'Energy (XLE)', group: 'sector-etf', sector: 'energy', start, c: close(-0.001, 0.05, 2) },
    { id: 'XLF', name: 'Financials (XLF)', group: 'sector-etf', sector: 'financials', start, c: close(0.0025, 0.02, 3) },
    { id: 'XLV', name: 'Health Care (XLV)', group: 'sector-etf', sector: 'health', start: W[10], c: close(0.001, 0.02, 4).slice(10) },
    { id: 'QQQ', name: 'Nasdaq-100 (QQQ)', group: 'style-etf', start, c: close(0.0035, 0.03, 5) },
    { id: 'GLD', name: 'Gold (GLD)', group: 'style-etf', start, c: close(0.003, 0.015, 6) },
    { id: 's:technology', name: 'Technology · site companies', group: 'site-sector', sector: 'technology', start, c: close(0.0038, 0.03, 1.2) },
    { id: 'zz', name: 'Something else', group: 'other', start, c: close(0.01, 0.01, 0) },
  ] };
const FILES = { 'data/market/history/momentum-latest.json': STOCKS, 'data/etf/momentum-latest.json': ETFS, 'data/market/history/rrg.json': RRG };
global.fetch = async (u) => (FILES[u] ? { ok: true, json: async () => JSON.parse(JSON.stringify(FILES[u])) } : { ok: false, status: 404, json: async () => null });
const order = (html, ts) => ts.map((t) => html.indexOf(`#momentum/${encodeURIComponent(t)}"><b>`)).every((x, i, a) => x > 0 && (i === 0 || a[i - 1] < x));

(async () => {
  // percentiles as app/momentum.py _pct: ties at their mean rank, none under five values
  assert.deepEqual(M.moPct({ a: 1, b: 2, c: 3, d: 4 }), {}); n++;
  assert.deepEqual(M.moPct({ a: 1, b: 2, c: 2, d: 3, e: 5, x: null, y: NaN }), { a: 0, b: 38, c: 38, d: 75, e: 100 }); n++;
  // the spread of the composite: tails gathered, the counts on the bars
  const h = M.moHist([-5, -2.9, -0.2, 0.1, 0.4, 0.45, 1.2, 3.5, null]);
  ok(h.startsWith('<svg') && (h.match(/<rect/g) || []).length === 14, 'fourteen bins');
  ok(h.includes('below −3σ: 1') && h.includes('+3σ and above: 1') && h.includes('0.00σ to +0.50σ: 3') && h.includes('−0.50σ to 0.00σ: 1'), 'the counts per bin');
  ok(M.moHist([1, 2]) === '', 'too few to draw');

  // companies: loading, then the leaderboard by the composite score
  state.mou = 'stocks';
  ok(/Reading the momentum readings/.test(M.momentumView()), 'loading first');
  await tick(); await tick();
  ok(renders > 0, 'a render when the file arrives');
  let html = M.momentumView();
  ok(order(html, ['NVDA', 'JPM', 'MSFT', 'AAPL', 'OXY', 'XOM', 'CVX', 'NEWC']), 'composite score, highest first, the unscored last');
  ok(html.includes('8 of 8 companies') && html.includes('weekly closes to 2026-11-06') && html.includes('monthly ranks to 2026-10-30'), 'the counts and dates');
  // breadth over the seven with a 12-1 return: 5 up, 3 above +1σ, 1 below −1σ, 3 ahead of SPY, 3 within 5% of the high
  ok(html.includes('<label>In an uptrend</label><strong>71%</strong>') && html.includes('<label>Strong uptrend</label><strong>43%</strong>') && html.includes('<label>Strong downtrend</label><strong>14%</strong>'), 'trend breadth');
  ok(html.includes('<label>Ahead of SPY</label><strong>43%</strong>') && html.includes('<label>Near the high</label><strong>43%</strong>') && html.includes('<label>Median composite</label><strong>+0.40σ</strong>'), 'relative breadth and the median');
  ok(html.includes('How the composite score is spread'), 'the spread');
  // by sector: technology (median 1.2) before energy (−0.6); financials has two companies, under three: left out
  const bs = html.slice(html.indexOf('<h3>By sector'), html.indexOf('</table>', html.indexOf('<h3>By sector')));
  ok(bs.indexOf('data-mogrp="technology"') > 0 && bs.indexOf('data-mogrp="technology"') < bs.indexOf('data-mogrp="energy"') && !bs.includes('data-mogrp="financials"'), 'sectors by their median composite');
  ok(bs.includes('Technology') && bs.includes('+1.20σ') && /NVDA.*MSFT.*AAPL/.test(bs), 'the median and the strongest of a sector');
  ok(html.includes('<th>vs sector ETF</th>') && html.includes('<th>Relative composite</th>') && !html.includes('<th>Rank in class</th>'), 'the companies\' columns');
  ok(exported.length === 8 && exported[0].ticker === 'NVDA' && exported[0].sector === 'Technology' && exported[0].composite_rank === 100 && exported[0].rel_sector === 0.2 && exported[0].week === '2026-11-06', 'CSV rows');
  // sorts and filters
  state.mosort = 'm12_1'; state.modir = 'asc';
  html = M.momentumView();
  ok(order(html, ['CVX', 'XOM', 'OXY', 'AAPL', 'MSFT', 'JPM', 'NVDA', 'NEWC']), '12-1, lowest first, the missing last');
  ok(html.includes('12-1 month return, lowest first'), 'the heading says the order');
  state.mogrp = 'energy'; state.mosort = 'comp'; state.modir = 'desc';
  html = M.momentumView();
  ok(order(html, ['OXY', 'XOM', 'CVX']) && !html.includes('#momentum/NVDA"><b>') && !html.includes('<h3>By sector'), 'a sector: its companies, no summary');
  ok(html.includes('3 of 8 companies') && html.includes('<label>In an uptrend</label><strong>33%</strong>'), 'breadth of the selection');
  state.mogrp = ''; state.moq = 'micro';
  html = M.momentumView();
  ok(html.includes('1 of 8 companies') && html.includes('#momentum/MSFT"><b>'), 'a search on the name');
  state.moq = '';

  // ETFs: $100M or more by default, the rank inside the asset class, no sector column
  state.mou = 'etfs';
  M.momentumView(); await tick(); await tick();
  html = M.momentumView();
  ok(order(html, ['GLD', 'SMH', 'QQQ', 'SPY', 'TLT']) && !html.includes('#momentum/TINY"><b>'), 'by the composite score; the small fund filtered out');
  ok(html.includes('<th>Rank in class</th>') && html.includes('<th>Net assets</th>') && !html.includes('<th>vs sector ETF</th>') && !html.includes('value="rel_s"'), 'the ETFs\' columns and sorts');
  ok(html.includes('left out: leveraged and inverse ETFs') && html.includes('cash-like funds'), 'what the universe leaves out');
  ok(html.includes('data-mogrp="Equity"') && !html.includes('data-mogrp="Fixed income"'), 'asset classes with three ETFs or more summarised');
  ok(exported.find((r) => r.ticker === 'SMH').rank_in_class === 100 && exported.find((r) => r.ticker === 'GLD').net_assets === 1e11, 'CSV rows with the class rank and the assets');
  state.moaum = '0';
  html = M.momentumView();
  ok(order(html, ['TINY', 'GLD', 'SMH']), 'any size: the small fund back, first');
  state.moaum = '1e8';

  // sectors and styles: computed here, the same numbers as momentum-view.js; the other kind of line left out
  state.mou = 'sectors';
  M.momentumView(); await tick(); await tick();
  html = M.momentumView();
  const S = M.moStore.sectors.data;
  ok(S.list.length === 8 && S.week === W[N - 1] && S.here, 'SPY, four sector ETFs, two style ETFs, a site index');
  ok(!S.list.some((r) => r.t === 'zz'), 'another kind of line is left out');
  const wk = Object.fromEntries(W.map((w, i) => [w, i]));
  const xlk = MV.factors(MV.fullOf(RRG.series[0], wk, N), MV.fullOf(RRG.bench, wk, N))[N - 1];
  const row = S.list.find((r) => r.t === 'XLK');
  for (const k of ['m12_1', 'm6_1', 'hi52', 'comp', 'rel_b', 'rcomp', 'ra12']) near(row[k], xlk[k], 'XLK ' + k);
  const spy = S.list.find((r) => r.t === 'SPY');
  ok(spy.g === 'Benchmark' && spy.rel_b === null && spy.rcomp === null, 'SPY: no relative momentum against itself');
  const comps = S.list.map((r) => r.comp).filter((v) => v != null);
  ok(S.list.find((r) => r.comp === Math.max(...comps)).p_comp === 100 && S.list.find((r) => r.comp === Math.min(...comps)).p_comp === 0, 'ranks among the lines');
  ok(html.includes('computed in your browser') && html.includes('Site companies') && html.includes('#momentum/s%3Atechnology"><b>'), 'the site index, linked');
  const ahead = S.list.filter((r) => r.rel_b != null);
  ok(!html.includes('<h3>By sector') && html.includes(`<label>Ahead of SPY</label><strong>${Math.round(100 * ahead.filter((r) => r.rel_b > 0).length / ahead.length)}%</strong>`), 'no summary; SPY itself not counted ahead of SPY');
  state.mogrp = 'Sector ETF';
  html = M.momentumView();
  ok(html.includes('4 of 8 lines') && html.includes('<label>Ahead of SPY</label>'), 'the sector ETFs alone');
  state.mogrp = '';

  // short horizons: the returns over the last 1, 5, 10, 21 and 63 trading days from the Move odds index (moves.js mvData)
  state.mou = 'stocks'; state.mogrp = ''; state.mosort = 'h5'; state.modir = 'desc';
  global.mvData = () => ({ loading: true });
  ok(/Reading the daily closes/.test(M.momentumView()), 'the daily closes load first');
  const F = ['key', 'ticker', 'name', 'kind', 'as_of', 'move', 'pct', 'move5', 'pct5', 'move10', 'pct10', 'move21', 'pct21', 'move63', 'pct63'];
  const R = (t, as, m1, m5, q5) => [t, t, t, t === 'SPY' ? 'market' : 'stock', as, m1, 50, m5, q5, m5 * 1.5, 60, m5 * 2, 65, m5 * 3, 70];
  const IX = { fields: F, as_of: '2026-11-12', rows: [R('SPY', '2026-11-12', 0.002, 0.01, 55), R('NVDA', '2026-11-12', 0.01, 0.05, 96), R('MSFT', '2026-11-12', 0.004, 0.02, 70),
    R('AAPL', '2026-11-12', -0.003, -0.01, 40), R('XOM', '2026-11-12', 0.006, 0.03, 85), R('OXY', '2026-11-12', -0.01, -0.04, 3), R('JPM', '2026-11-12', 0.001, 0.015, 60),
    R('CVX', '2026-11-10', 0.02, 0.09, 99)] };
  global.mvData = () => ({ data: IX });
  html = M.momentumView();
  ok(order(html, ['NVDA', 'XOM', 'MSFT', 'JPM', 'AAPL', 'OXY']) && html.indexOf('#momentum/OXY"><b>') < html.indexOf('#momentum/CVX"><b>') && html.indexOf('#momentum/OXY"><b>') < html.indexOf('#momentum/NEWC"><b>'), 'by the week, highest first; a line not at the latest close and one without daily closes after them');
  ok(html.includes('6 of 8 companies with daily closes to the close of 2026-11-12') && html.includes('Return over the last 1 week (5 trading days), highest first'), 'the coverage and the heading');
  ok(html.includes('<label>Up</label><strong>67%</strong>') && html.includes('<label>Ahead of SPY</label><strong>67%</strong>') && html.includes('SPY +1.0% over the same days') && html.includes('<label>Extreme for their own history</label><strong>33%</strong>'), 'the breadth over the week');
  const hb = html.slice(html.indexOf('<h3>By sector'), html.indexOf('</table>', html.indexOf('<h3>By sector')));
  ok(hb.includes('the last 1 week') && hb.includes('data-mogrp="technology"') && !hb.includes('data-mogrp="energy"') && hb.includes('+2.0%') && /NVDA.*MSFT.*AAPL/.test(hb), 'by sector: the median week, the strongest (energy has two with daily closes: left out)');
  ok(['Day', 'Week', '2 weeks', 'Month', 'Quarter', 'vs SPY, week', 'Own history, week'].every((h) => html.includes(`<th>${h}</th>`)) && !html.includes('<th>12-1</th>'), 'the horizons\' columns');
  ok(html.includes('<b><span class="positive">+5.0%</span></b>') && html.includes('<td>96</td>'), 'the ranked column in bold; the move against its own history');
  ok(exported[0].ticker === 'NVDA' && exported[0].week === 0.05 && Math.abs(exported[0].vs_spy_week - 0.04) < 1e-12 && exported[0].own_percentile_week === 96 && exported[0].daily_close === '2026-11-12', 'the CSV rows');
  ok(/daily closes to 2026-11-12/.test(M.momentumNotice().text), 'the notice says which closes');
  state.modir = 'asc';
  html = M.momentumView();
  ok(order(html, ['OXY', 'AAPL', 'JPM']) && html.includes('<th>Weakest</th>'), 'lowest first: the weakest');
  state.modir = 'desc'; state.mosort = 'h63';
  html = M.momentumView();
  ok(order(html, ['NVDA', 'XOM', 'MSFT']) && html.includes('Return over the last 1 quarter (63 trading days)'), 'the quarter');
  // last night's file without the two-week and quarter returns (the day the fields are added)
  const old = { fields: F.filter((f) => !/10|63/.test(f)), as_of: '2026-11-12' };
  old.rows = IX.rows.map((r) => r.filter((_, i) => !/10|63/.test(F[i])));
  global.mvData = () => ({ data: old });
  html = M.momentumView();
  ok(html.includes('come with the next nightly build') && html.includes('0 of 8 companies with daily closes'), 'not in the file yet: said so');
  state.mosort = 'h1';
  html = M.momentumView();
  ok(order(html, ['NVDA', 'XOM', 'MSFT', 'JPM', 'AAPL', 'OXY']) && !html.includes('come with the next nightly build'), 'the day is there');
  global.mvData = () => ({ err: 'HTTP 404' });
  ok(M.momentumView().includes('could not load (HTTP 404)'), 'the daily closes failing: said so');
  state.mosort = 'comp'; delete global.mvData;

  // a universe not published yet: says so, offers the sectors and a ticker's history
  delete FILES['data/etf/momentum-latest.json']; delete M.moStore.etfs;
  state.mou = 'etfs';
  M.momentumView(); await tick(); await tick();
  html = M.momentumView();
  ok(html.includes('not on file yet (not published yet)') && html.includes('data-mou="sectors"'), 'not published yet');
  ok(/readings are not published yet/.test(M.momentumNotice().text), 'the notice says so');

  // deep links and a ticker's history
  M.momentumDeepLink('etfs'); ok(state.mou === 'etfs' && state.mot === '', '#momentum/etfs: a universe');
  M.momentumDeepLink('Companies'); ok(state.mou === 'stocks', '#momentum/companies');
  M.momentumDeepLink('s%3Atechnology'); ok(state.mot === 's:technology', 'a site index');
  M.momentumDeepLink('NVDA'); ok(state.mot === 'NVDA', '#momentum/NVDA: a ticker');
  html = M.momentumView();
  ok(html.includes('id="mo-one" data-k="NVDA"') && html.includes('← The companies leaderboard'), 'the history and the way back');
  ok(M.momentumNotice() === null, 'no notice over a ticker');
  const calls = [];
  const real = MV.render;
  window.MomentumView.render = (el, opt) => { calls.push(opt); };
  const el = { dataset: { k: 'NVDA' } };
  global.$ = (id) => (id === 'mo-one' ? el : null);
  global.document = { querySelectorAll: () => [] };
  M.bindMomentum();
  M.bindMomentum();                                              // drawn once per ticker
  ok(calls.length === 1 && calls[0].ticker === 'NVDA' && calls[0].hub === '' && calls[0].here() === true, 'momentum-view.js draws the ticker');
  state.mot = 'AAPL';
  ok(calls[0].here() === false, 'another ticker since: the old drawing stops');
  window.MomentumView.render = real;
  console.log(`${n} momentum tab checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
