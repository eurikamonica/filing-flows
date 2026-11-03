// fairvalue-view.js: the peer tiers table and the peer explorer (filters and windows over data/research/valuation/
// peers-list.json): the weighted quantile equals the plain percentile for equal weights, every filter leaves peers out
// with its reason, the 20% cap, the history window and the value per share, from a small list. No browser, no network.
const assert = require('node:assert/strict');
const path = require('node:path');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const FV = require(path.join(__dirname, '..', 'docs', 'fairvalue-view.js'));
const plain = (xs, q) => { const s = xs.slice().sort((a, b) => a - b), k = (s.length - 1) * q, lo = Math.floor(k), hi = Math.ceil(k); return s[lo] + (s[hi] - s[lo]) * (k - lo); };
for (const xs of [[3, 1, 2], [5, 9, 1, 7, 3, 8], [2.5, 4.1, 6.6, 1.2, 9.9, 3.3, 7.7, 5.5, 8.8]]) for (const q of [0, 0.25, 0.5, 0.75, 1]) ok(Math.abs(FV.wq(xs, xs.map(() => 1), q) - plain(xs, q)) < 1e-12, 'equal weights: the plain percentile');
ok(FV.wq([10, 20, 30], [0.1, 0.1, 10], 0.5) > 20, 'a heavy weight pulls the median');
const cw = FV.capW({ a: 90, b: 5, c: 2, d: 1, e: 1, f: 1, g: 1, h: 1, i: 1, j: 1 });
ok(Math.abs(Object.values(cw).reduce((s, v) => s + v, 0) - 1) < 1e-9 && cw.a <= 0.2 + 1e-9 && cw.b > cw.c, 'the cap');
const F = ['cik', 'ticker', 'name', 'sic', 'sector', 'kind', 'stage', 'mcap', 'ev', 'revenue', 'growth', 'margin', 'dvol', 'pe', 'ev_ebitda', 'ev_sales', 'p_ffo', 'date', 'pe_hist', 'evs_hist'];
const row = (cik, t, sic, stage, mcap, rev, g, m, evs, extra = {}) => F.map((f) => ({ cik, ticker: t, name: t + ' Inc', sic, sector: 'technology', kind: 'industrial', stage, mcap, ev: mcap, revenue: rev, growth: g, margin: m, dvol: mcap / 100, pe: 25, ev_ebitda: 18, ev_sales: evs, p_ffo: null, date: '2026-10-30', pe_hist: null, evs_hist: null, ...extra }[f]));
const D = { fields: F, ages: [0.5, 1.5], half_life: 1, as_of: '2026-11-02', rows: [
  row(1, 'OWN', '7372', 'growth', 50e9, 5e9, 0.12, 0.20, 9),
  row(2, 'BIG', '7372', 'growth', 3000e9, 200e9, 0.15, 0.40, 11, { evs_hist: [10, 6] }),
  row(3, 'MID', '7372', 'growth', 60e9, 6e9, 0.10, 0.18, 7), row(4, 'MID2', '7372', 'mature', 40e9, 4e9, 0.05, 0.25, 6),
  row(5, 'LOSS', '7372', 'pre_profit', 5e9, 1e9, 0.30, -0.2, 12), row(6, 'TINY', '7372', 'growth', 0.3e9, 0.1e9, 0.11, 0.15, 3),
  row(7, 'NOEV', '7372', 'growth', 20e9, 2e9, 0.12, 0.2, null), row(8, 'OTHER', '3571', 'growth', 100e9, 50e9, 0.1, 0.2, 2),
  row(9, 'S1', '7372', 'growth', 10e9, 3e9, 0.14, 0.22, 8), row(10, 'S2', '7372', 'growth', 8e9, 2.5e9, 0.13, 0.21, 7.5)] };
const d = { cik: 1, ticker: 'OWN', price: 100, peer_base: { revenue: 5e9, net_debt: 1e9, shares: 0.4e9, eps: 4, ebitda: 1.2e9, sic: '7372' }, peers: {} };
const base = { metric: 'ev_sales', group: 'sic4', stage: 'any', size: '0', growth: '0', margin: '0', hist: '0', weight: 'equal', trim: '0' };
let R = FV.pxRun(D, d, base);
ok(R.inc.length === 7 && !R.inc.some((r) => r.ticker === 'OWN' || r.ticker === 'OTHER'), 'the industry: its SIC, never itself');
ok(R.exc.length === 1 && /no EV\/Sales/.test(R.exc[0][1]), 'a peer without the multiple is listed as left out');
ok(Math.abs(R.p50 - plain([11, 7, 6, 12, 3, 8, 7.5], 0.5)) < 1e-12, 'every peer alike, today: the plain median');
R = FV.pxRun(D, d, { ...base, stage: 'same' });
ok(R.inc.every((r) => r.stage === 'growth') && R.exc.some(([r, why]) => r.ticker === 'LOSS' && /stage/.test(why)), 'same stage');
R = FV.pxRun(D, d, { ...base, stage: 'profit' });
ok(R.exc.some(([r, why]) => r.ticker === 'LOSS' && /loss-making/.test(why)), 'same side of break-even');
R = FV.pxRun(D, d, { ...base, size: '4' });
ok(R.exc.some(([r]) => r.ticker === 'BIG') && R.exc.some(([r]) => r.ticker === 'TINY') && R.inc.some((r) => r.ticker === 'MID'), 'the size window');
R = FV.pxRun(D, d, { ...base, growth: '0.05', margin: '0.05' });
ok(R.inc.every((r) => Math.abs(r.growth - 0.12) <= 0.05 + 1e-9 && Math.abs(r.margin - 0.2) <= 0.05 + 1e-9), 'growth and margin windows');
R = FV.pxRun(D, d, { ...base, weight: 'mcap' });
ok(Math.abs(R.sw[2] - 0.2) < 1e-9 && R.neff < R.inc.length, 'by market value, the giant capped at 20%');
R = FV.pxRun(D, d, { ...base, hist: '5' });
ok(R.n_obs === R.inc.length + 2, 'the history window adds the quarters on file');
const R1 = FV.pxRun(D, d, { ...base, hist: '1' });
ok(R1.n_obs === R1.inc.length + 1, 'the last year only');
R = FV.pxRun(D, d, base);
const h = FV.pxHtml(D, d, base);
ok(h.includes(`$${((R.p50 * 5e9 - 1e9) / 0.4e9).toFixed(2)}`) || h.includes(((R.p50 * 5e9 - 1e9) / 0.4e9).toFixed(2)), 'the value per share at the median');
ok(h.includes('this company') && h.includes('Left out by these filters') && !/NaN|undefined/.test(h), 'the explorer table');
// the tiers table
const P = { ev_sales: { group: 'sic7372', n: 7, p25: 6, p50: 7.5, p75: 10, own: 9, weighted: { p25: 7, p50: 9, p75: 11, n_eff: 3.2, n: 7, by: {}, top: [['BIG', 0.2]] },
  matched: { window: 'tight', n: 6, p25: 7, p50: 7.8, p75: 9, tried: [['tight', 6]], criteria: { key: 'tight', sic: 3, stage: 'same', size: 4, growth: 0.1, margin: 0.1 } },
  selected: { n: 2, comps: [['S1', 'similar', 8], ['S2', 'similar', 7.5]], missing: [] }, adjusted: { p25: 7, p50: 8.4, p75: 10, n: 14, r2: 0.6, per10: { growth: 0.2, margin: 0.15 }, x: { growth: 0.12, margin: 0.2 } } } };
const t = FV.tiersHtml({ ...d, peers: P });
ok(t.includes('four ways to pick') && t.includes('2 on file, needs 3') && t.includes('every 10 points of revenue growth +20%') && t.includes('Explore the peers') && !/NaN|undefined/.test(t), 'the tiers table');
ok(FV.scoresHtml({ snapshots: ['2026-11'], scores: [] }).includes('first scores come three months'), 'no track record yet');
const sc = FV.scoresHtml({ scores: [{ horizon_months: 3, ic_evs_matched_gap: 0.08, n_evs_matched_gap: 900 }, { horizon_months: 3, ic_evs_matched_gap: 0.04, n_evs_matched_gap: 900 }] });
ok(sc.includes('EV/Sales · Matched') && sc.includes('0.060'), 'the track record, averaged over months');
// each method against the price and the present value of growth in it
const dsp = { price: 100, growth_split: { no_growth: 40, basis: 'NOPAT ÷ WACC − net debt', rate: 0.09, earnings: 4e9, price: 100, price_pv_growth: 60, price_growth_share: 0.6, price_growth: 0.08, history_growth: 0.05, dcf: true },
  football: [{ method: 'DCF', low: 90, high: 140, point: 120, vs_price: 0.2, pv_growth: 80, pv_growth_share: 0.667, implied_growth: 0.11 },
    { method: 'EPV', low: 35, high: 45, point: 38, vs_price: -0.62, pv_growth: -2, pv_growth_share: -0.05, implied_growth: -0.04 }, { method: '52-week trading range', low: 80, high: 120 }] };
const sh = FV.splitHtml(dsp);
ok(sh.includes('how much of it is growth') && sh.includes('$40.00') && sh.includes('+11.0% a year') && sh.includes('none (below the no-growth value)') && sh.includes('+8.0% a year') && !/NaN|undefined/.test(sh), 'the price and growth table');
ok(sh.indexOf('>DCF<') < sh.indexOf('>EPV<') && sh.includes('<svg'), 'sorted by value, with the chart');
ok(FV.splitHtml({ price: 100, football: [] }) === '', 'nothing without the split');
console.log(`Peer explorer: ${n} checks passed`);
