// crowding.js: the 13F crowding view's arithmetic — sector shares, scores and the tilt against the market, each quarter's
// order, a 13F report named through the CUSIP map — and the videos it builds (score race, changes, sector areas, tilt;
// one portfolio's holdings). The hub's helpers and fetch stubbed; no browser, no network.
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.compact = (v) => String(v);
global.kpi = (l, v, c) => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.field = (id, label, items, v) => `<select id="${id}">${items.map((x) => `<option${String(x[0]) === String(v) ? ' selected' : ''}>${x[0]}</option>`).join('')}</select>`;
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.choose = (cur, vals) => (vals.includes(String(cur)) ? String(cur) : vals[0] || '');
global.lineChart = (rows) => `<svg data-points="${rows.filter((r) => r.value != null).length}"></svg>`;
global.state = {};
global.window = {};
global.exported = [];
let renders = 0;
global.render = () => { renders++; };
const slots = {};
global.HubVideo = { slot: (key, spec) => { slots[key] = spec; return `<div data-hv="${key}"></div>`; } };

const P = ['2025-12-31', '2026-03-31', '2026-06-30'];
const DOC = {
  generated_at: 't1', periods: P, managers: [100, 100, 100], managers_big: [80, 80, 80], stock_usd: [1000, 1000, 1200],
  fields: ['holders', 'top10', 'usd_m', 'score', 'conviction'],
  rows: {
    NVDA: [[80, 85, 90], [40, 45, 50], [300, 350, 420], [63.2, 68.7, 75.0], [0.6, 0.62, 0.65]],
    AAPL: [[90, 88, 86], [50, 45, 40], [320, 300, 280], [74.5, 70.4, 65.6], [0.7, 0.6, 0.55]],
    XOM: [[40, 45, 60], [5, 8, 12], [100, 110, 150], [15.8, 21.2, 30.0], [0.15, 0.2, 0.25]],
    JPM: [[50, 50, 50], [10, 10, 10], [150, 150, 150], [25.0, 25.0, 25.0], [0.2, 0.2, 0.2]],
    TINY: [[12, 11, null], [0, 0, null], [5, 5, null], [null, null, null], [null, null, null]],
  },
  names: { NVDA: 'NVIDIA', AAPL: '', XOM: 'Exxon Mobil', JPM: 'JPMorgan', TINY: 'Tiny Co' },
  params: { min_holders: 20, top: 10, min_book: 20 }, note: 'method note',
};
const SECTORS = { sectors: { NVDA: 'technology', AAPL: 'technology', XOM: 'energy', JPM: 'financials' } };
const META = { cos: [['AAPL', 'Apple Inc.', 'technology'], ['TINY', 'Tiny', 'industrials']] };
const VTI = { quarterly: { unit: 1e-5, dates: ['2026-03-31', '2026-06-30'], sectors: ['technology', 'energy', 'financials', 'other'],
  sw: [[50000, 20000, 30000, 1000], [60000, 15000, 25000, 500]] } };
const FILES = { 'data/market/crowding.json': DOC, 'data/etf/sectors.json': SECTORS, 'data/market/history/rank/meta.json': META,
  'data/etf/weights/VTI.json': VTI, 'data/market/cusip-tickers.json': { '037833100': 'AAPL', '30231G102': 'XOM' } };
global.fetch = (u) => Promise.resolve(FILES[u] ? { ok: true, json: async () => FILES[u] } : { ok: false, status: 404, json: async () => null });

const C = require('../docs/crowding.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const tick = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  ok(/Loading/.test(C.cwView()), 'loading first');
  await tick(); await tick();
  ok(renders > 0, 'a render when the files arrive');
  const g = C.cwGate();
  ok(g.model, 'the model once everything loaded');
  const M = g.model;
  // sectors: shares of all the stock value filed, scores weighted by the value held, the tilt against the market
  near(M.sectors.technology.share[2], (420 + 280) / 1200, 'technology share of the stock value filed');
  near(M.sectors.other.share[2], 1 - (420 + 280 + 150 + 150) / 1200, 'Other: the rest of the value filed');
  near(M.sectors.technology.score[2], (420 * 75 + 280 * 65.6) / 700, 'score weighted by value');
  near(M.sectors.technology.cshare[2], 700 / 1000, 'share of the value with a sector');
  near(M.mkt[2].technology, 0.6, 'the market: VTI\'s sector weights without Other');
  near(M.sectors.technology.tilt[2], 0.7 - 0.6, 'tilt = 13F share − market share');
  ok(M.mkt[0] === null && M.sectors.energy.tilt[0] === null, 'no market weights for that quarter: no tilt');
  assert.deepEqual(M.by.get('NVDA').rank, [2, 2, 1]); n++;
  assert.deepEqual(M.by.get('AAPL').rank, [1, 1, 2]); n++;
  ok(M.by.get('TINY').rank === undefined, 'never scored: no rank');
  ok(M.by.get('AAPL').name === 'Apple Inc.', 'a name from the leaderboard\'s company list');
  ok(M.by.get('TINY').sec === 'industrials', 'a sector from the company list when the ETF map lacks it');

  // the view: the latest quarter, stocks by score, the CSV rows
  const html = C.cwView();
  ok(html.includes('Sectors, Q2 2026') && html.includes('Stocks, Q2 2026'), 'the latest quarter');
  ok(html.indexOf('data-cwt="NVDA"') < html.indexOf('data-cwt="AAPL"'), 'NVDA first on score in Q2 2026');
  ok(exported[0].ticker === 'NVDA' && exported[0].rank === 1 && exported[0].score_change === 75.0 - 68.7, 'CSV rows');
  ok(slots['crowd:all'] && slots['crowd:all'].styles.length === 6, 'the crowding video slot');
  state.cwsec = 'energy';
  C.cwView();
  ok(exported.length === 1 && exported[0].ticker === 'XOM', 'a sector filter');
  state.cwsec = '';

  // the videos
  const race = C.cwBuildAll('score', 2);
  ok(race.kind === 'rank' && race.rankN === 2 && race.quarterly, 'a quarterly rank race');
  assert.deepEqual(race.series.map((s) => s.key).sort(), ['AAPL', 'NVDA']); n++;   // the top two in some quarter, no one else
  ok(race.grid.length === 3 && race.fmt(68.66) === '68.7', 'three quarters, one decimal');
  const delta = C.cwBuildAll('delta', 3);
  ok(delta.grid.length === 2 && delta.order === 'abs' && /^Q1 2026 → Q2 2026/.test(delta.sub), 'changes: from the second quarter, by size');
  near(delta.series.find((s) => s.key === 'XOM').v[1], 30.0 - 21.2, 'XOM\'s rise', 1e-9);
  ok(delta.fmt(-4.84) === '−4.8', 'signed change');
  const areas = C.cwBuildAll('sshare', 12);
  ok(areas.kind === 'sectors' && areas.stack.share, 'sector areas');
  near(areas.series.reduce((a, s) => a + s.v[2], 0), 1, 'areas add to 100%');
  ok(areas.series[areas.series.length - 1].key === 'other', 'Other at the top of the stack');
  const tilt = C.cwBuildAll('tilt', 12);
  ok(tilt.grid.length === 2 && /Q1 2026/.test(tilt.sub), 'the tilt from the first quarter with market weights');
  ok(tilt.series.find((s) => s.key === 'technology').label === 'Technology' && tilt.series.find((s) => s.key === 'consumer-staples') === undefined, 'short labels; sectors with no values left out');
  const ss = C.cwBuildAll('sscore', 12);
  ok(ss.rankN === 11, 'at most the eleven sectors');
  assert.throws(() => C.cwBuildAll('nope', 5), /Unknown view/); n++;

  // one portfolio: today's weights through the quarters
  const hold = C.cwBuildHoldings('XLK', [['NVDA', 0.15], ['AAPL', 0.13], ['ZZZZ', 0.01]], 'hscore', 5);
  assert.deepEqual(hold.series.map((s) => s.key).sort(), ['AAPL', 'NVDA']); n++;
  assert.throws(() => C.cwBuildHoldings('X', [['ZZZZ', 1]], 'hscore', 5), /none of its holdings/); n++;
  const panel = C.cwPortfolio('etf:XLK', 'XLK', [['NVDA', 0.15], ['AAPL', 0.13], ['XOM', 0.02]], 'note');
  ok(/Weighted crowding score/.test(panel) && slots['crowd:etf:XLK'], 'the portfolio panel and its video slot');
  ok(panel.includes(fmt((0.15 * 75 + 0.13 * 65.6 + 0.02 * 30) / 0.30, 1)), 'weighted score of the holdings');
  ok(panel.includes('data-points="3"'), 'one point a quarter');

  // a 13F report without tickers: named through the CUSIP map; options and other quantity types left out
  const snap = { total_usd: 100, positions: [{ cusip: '037833100', put_call: 'NONE', share_type: 'SH', value_usd: 60 },
    { cusip: '30231G102', ticker: 'XOM', put_call: 'NONE', share_type: 'SH', value_usd: 20 },
    { cusip: '037833100', put_call: 'CALL', share_type: 'SH', value_usd: 15 }, { cusip: '999999999', put_call: 'NONE', share_type: 'PRN', value_usd: 5 }] };
  ok(C.cwBook(snap) === null, 'null while the CUSIP map loads');
  await tick(); await tick();
  assert.deepEqual(C.cwBook(snap), [['AAPL', 0.6], ['XOM', 0.2]]); n++;
  console.log(`Crowding view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
