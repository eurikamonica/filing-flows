// The video studio (web/studio.js): formulas, the series behind each kind of video, the address, and every style drawn
// on a stand-in canvas from small files (no browser; the real export is checked by hand in a browser).
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const files = {};
globalThis.FFUx = { json: async (u) => (u in files ? JSON.parse(JSON.stringify(files[u])) : null) };
const S = require('../web/studio.js')._t;
let n = 0;
const ok = (c, m) => { assert.ok(c, m); n++; };

// formulas: precedence, unary minus, power, functions, labels
const env = new Map([['AAA.tr', [1, 2, 4, 8]], ['BBB.tr', [2, 2, 2, 2]], ['BBB.price', [1, 1, 2, 2]]]);
const ev = (src) => S.evaluate(S.parse(src), env, 4);
assert.deepEqual(ev('AAA/BBB'), [0.5, 1, 2, 4]); n++;
assert.deepEqual(ev('1+2*3^2'), [19, 19, 19, 19]); n++;
assert.deepEqual(ev('-AAA+10'), [9, 8, 6, 2]); n++;
assert.deepEqual(ev('2^-1*AAA'), [0.5, 1, 2, 4]); n++;
assert.deepEqual(ev('rebase(AAA)'), [100, 200, 400, 800]); n++;
assert.deepEqual(ev('pct(AAA,1)'), [null, 100, 100, 100]); n++;
assert.deepEqual(ev('ma(AAA,2)'), [null, 1.5, 3, 6]); n++;
assert.deepEqual(ev('lag(AAA,2)'), [null, null, 1, 2]); n++;
assert.deepEqual(ev('BBB.price × 3 ÷ 3'), [1, 1, 2, 2]); n++;
assert.deepEqual(ev('log(AAA)').map((v) => +v.toFixed(6)), [0, 0.693147, 1.386294, 2.079442]); n++;
assert.deepEqual(S.ids(S.parse('rebase(QQQ/SPY)+NVDA.revenue_ttm')).map((x) => x.id + '.' + x.field), ['QQQ.tr', 'SPY.tr', 'NVDA.revenue_ttm']); n++;
assert.deepEqual(S.formulas('Growth: rebase(IWF/IWD)\nQQQ/SPY'), [{ label: 'Growth', src: 'rebase(IWF/IWD)' }, { label: 'QQQ/SPY', src: 'QQQ/SPY' }]); n++;
for (const bad of ['QQQ/', 'rebase(', 'ma(QQQ)', 'QQQ # SPY']) assert.throws(() => S.parse(bad)), n++;

// the address keeps every setting, a formula with % and & included
const st = S.parseState('k=formula&expr=' + encodeURIComponent('Nasdaq ÷ S&P: rebase(QQQ/SPY)\nyield %: SCHD.yield*100') + '&theme=clean');
ok(st.k === 'formula' && st.expr.includes('S&P') && st.expr.includes('yield %') && st.theme === 'clean' && st.style === 'line', 'formula address not parsed');
ok(S.parseState('k=momentum').style === 'bars', 'a kind without a style takes its first style');
ok(S.parseState(S.serialize(st).slice('studio/'.length)).expr === st.expr, 'the address does not round-trip');

// distributions: the fund's usual number a year, so a late payment is not missed
const d0 = Date.UTC(2020, 0, 3), W = 7 * 864e5, P = { px: { t: [], c: [], a: [], div: [] } };
for (let i = 0; i < 52 * 5; i++) { P.px.t.push(d0 + i * W); P.px.c.push(100); P.px.a.push(100); }
for (let q = 0; q < 20; q++) P.px.div.push([d0 + (13 * q + 6 + (q === 13 ? 2 : 0)) * W, 1]);   // quarterly, one paid two weeks late
const ttm = P.px.t.slice(160).map((g) => S.divTTM(P, g));
ok(ttm.every((v) => v === 4), 'trailing distributions dip when a payment is late: ' + [...new Set(ttm)]);

// a company's figures: trailing four quarters, margins, growth
const C = { q: { revenue: new Map([['2025-03-31', 10], ['2025-06-30', 10], ['2025-09-30', 10], ['2025-12-31', 10], ['2026-03-31', 20]]), oi: new Map([['2025-03-31', 2], ['2025-06-30', 2], ['2025-09-30', 2], ['2025-12-31', 2], ['2026-03-31', 4]]) } };
assert.deepEqual(S.figure(C, 'revenue', true).map((r) => r[1]), [40, 50]); n++;
assert.deepEqual(S.figure(C, 'om', true).map((r) => r[1]), [0.2, 0.2]); n++;

// whole videos from small files, every style drawn on a stand-in canvas
const weeks = 300, start = '2020-01-03';
const px = (sym, g, y) => ({ symbol: sym, name: sym + ' Fund', d0: '2019-12-30', t: Array.from({ length: weeks }, (_, i) => 7 * i), c: Array.from({ length: weeks }, (_, i) => 50 * Math.exp(g * i + 0.05 * Math.sin(i / 9))), a: Array.from({ length: weeks }, (_, i) => 50 * Math.exp((g + y) * i + 0.05 * Math.sin(i / 9))), div: Array.from({ length: Math.floor(weeks / 13) }, (_, q) => [new Date(Date.UTC(2019, 11, 30) + (13 * q + 10) * 7 * 864e5).toISOString().slice(0, 10), 0.4]) });
files['disclosures/data/etf/px/AAA.json'] = px('AAA', 0.004, 0.0004);
files['disclosures/data/etf/px/BBB.json'] = px('BBB', 0.002, 0.0008);
files['disclosures/data/etf/px/SPY.json'] = px('SPY', 0.003, 0.0003);
files['data/index.json'] = { companies: [{ ticker: 'ZZZ', cik: 9, name: 'Zed Corp', revenue: 1 }] };
const hist = { periods: [], v: { revenue: [], oi: [], ni: [], ocf: [] } };
for (let i = 0; i < 20; i++) { const e = new Date(Date.UTC(2021, 2 + 3 * i, 31)).toISOString().slice(0, 10); hist.periods.push(['', e, 'q', 'Q']); for (const k of Object.keys(hist.v)) hist.v[k].push([i, [[(k === 'revenue' ? 100 : 20) * (1 + i / 10), [0, '3m', []]]]]); }
files['data/c/9.json'] = { profile: { name: 'Zed Corp' }, quality: { hist }, quarters: [] };
const ctx = new Proxy({ canvas: { width: 1920, height: 1080 } }, {
  get(o, k) {
    if (k in o) return o[k];
    if (k === 'measureText') return (s) => ({ width: String(s).length * 12 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({ addColorStop() {} });
    return () => {};
  },
  set(o, k, v) { o[k] = v; return true; },
});
(async () => {
  const cases = [
    ['growth', { k: 'growth', t: 'AAA,BBB', from: start, div: 'tr' }, ['line', 'bars', 'area', 'tiles']],
    ['growth split', { k: 'growth', t: 'AAA,BBB', from: start, div: 'split' }, ['line', 'area']],
    ['momentum', { k: 'momentum', t: 'AAA,BBB', from: start, bench: 'SPY', lb: '26' }, ['bars', 'line']],
    ['rrg', { k: 'rrg', t: 'AAA,BBB', from: '2022-01-07', bench: 'SPY', tail: '8', n: '14' }, ['rrg']],
    ['formula', { k: 'formula', expr: 'r: rebase(AAA/BBB)\ny: AAA.yield*100', from: start }, ['line', 'area', 'tiles', 'bars']],
    ['fund', { k: 'fund', t: 'ZZZ', m: 'om', ttm: '1' }, ['columns', 'line', 'bars', 'tiles']],
  ];
  for (const [name, s0, styles] of cases) {
    const st0 = Object.assign(S.parseState(''), s0);
    const V = await S.build(st0);
    ok(V.series.length >= 1 && V.grid.length > 3, name + ': nothing built');
    if (name === 'growth') { const last = V.series.map((s) => s.v[s.v.length - 1]); ok(last[0] > last[1] && Math.abs(V.series[0].v.find((x) => x != null) - 10000) < 1e-6, 'growth values wrong'); }
    if (name === 'growth split') { const s = V.series[0], L = s.v.length - 1; ok(s.cash[L] > 0 && Math.abs(s.v[L] - s.price[L] - s.cash[L]) < 1e-6, 'split = price + cash'); }
    if (name === 'formula') ok(V.panels === undefined || typeof V.panels === 'boolean', 'panels flag');
    for (const style of styles) for (const ar of [[1920, 1080], [1080, 1920], [1080, 1080]]) {
      V.style = style; V.endCard = true; S.finish(V, st0);
      const opt = { theme: 'bull', ar: '16x9', dur: 12 };
      for (const t of [0, 0.3, 4, 8, 11.9]) S.draw(ctx, ar[0], ar[1], V, opt, t);
      n++;
    }
    ok(typeof V.caption === 'string' && V.caption.length > 3, name + ': no caption');
  }
  // recurring buys: the schedule, the money put in, the money-weighted yearly return
  {
    const G = Array.from({ length: 60 }, (_, i) => Date.UTC(2020, 0, 3) + i * W);
    const m = S.buySchedule(G, 100, 1, 'm', Date.UTC(2020, 0, 3)), w2 = S.buySchedule(G, 100, 2, 'w'), d1 = S.buySchedule(G, 10, 1, 'd'), d3 = S.buySchedule(G, 10, 3, 'd');
    ok(m.filter((x) => x > 0).length === 14 && m[0] === 100, 'monthly buys: ' + m.filter((x) => x > 0).length);
    ok(w2.filter((x) => x > 0).length === 30 && d1.every((x) => x === 50), 'weekly / daily buys');
    ok(Math.abs(d3.reduce((a, x) => a + x, 0) - 10 * Math.ceil(300 / 3)) < 1e-9, 'every third trading day: ' + d3.reduce((a, x) => a + x, 0));
    const r = S.xirr([[Date.UTC(2020, 0, 1), -100], [Date.UTC(2021, 0, 1), 110]]);
    ok(Math.abs(r - 0.1) < 0.002, 'xirr of +10% in a year: ' + r);
    ok(Math.abs(S.xirr([[0, -100], [365.25 * 864e5, -100], [2 * 365.25 * 864e5, 231]]) - 0.1) < 0.002, 'xirr of two payments');
    const V = await S.build(Object.assign(S.parseState(''), { k: 'growth', t: 'AAA,BBB', from: start, amt: '0', rec: '100', ri: '1', ru: 'm' }));
    const L = V.grid.length - 1, put = V.contrib[L];
    ok(V.dca && put > 6000 && put === V.dca.put && V.base == null && V.series.every((x) => x.v[L] > 0), 'monthly buys build: ' + put);
    V.style = 'line'; V.endCard = true; S.finish(V, V);
    ok(/put in/.test(V.endTitle) && /%\/yr/.test(V.final[0].label), 'end card names the money put in and the yearly return: ' + V.endTitle + ' / ' + V.final[0].label);
    for (const style of ['line', 'bars', 'area', 'tiles']) { V.style = style; for (const t of [0, 3, 8, 11.9]) S.draw(ctx, 1920, 1080, V, { theme: 'bull', dur: 12 }, t); n++; }
    // pace and the pause at the end
    const tm = S.timing(V, { dur: 20, hold: '0', pace: 'finale' });
    ok(tm.hold === 0 && tm.run > 18 && S.frameIndex(V, tm, tm.intro + tm.run / 2) > L * 0.6, 'slow-motion finish runs ahead early');
    ok(Math.abs(S.frameIndex(V, S.timing(V, { dur: 20, pace: 'linear' }), 0.8 + S.timing(V, { dur: 20, pace: 'linear' }).run / 2) - L / 2) < 1e-6, 'an even pace');
  }
  // a stock's dividends from its weekly history: the price as traded rebuilt from the adjusted closes
  {
    const th = { start: '2024-01-05', c: [9.5, 9.6, 10, 10.2], d: [[2, 0.5]] };
    const hp = S.historyPx(th);
    ok(Math.abs(hp.c[1] - (9.6 + 0.5)) < 1e-9 && Math.abs(hp.c[3] - 10.2) < 1e-9 && Math.abs(hp.c[0] - 9.5 * (10.1 / 9.6)) < 1e-9, 'price rebuilt: ' + hp.c);
    ok(hp.div.length === 1 && hp.div[0][1] === 0.5, 'dividend dates');
    ok(S.historyPx({ start: '2024-01-05', c: [9, 10], p: [9.5, 10], d: [] }).c[0] === 9.5, 'the close as traded when published');
    files['disclosures/data/market/history/t/KO.json'] = { t: 'KO', n: 'Coca-Cola', start: '2019-12-27', c: Array.from({ length: 300 }, (_, i) => 40 * Math.exp(0.002 * i)), d: Array.from({ length: 22 }, (_, q) => [13 * q + 5, 0.4]) };
    const V = await S.build(Object.assign(S.parseState(''), { k: 'growth', t: 'KO,AAA', from: start, div: 'split' }));
    const ko = V.series.find((x) => x.key === 'KO'), L = ko.v.length - 1;
    ok(ko.cash && ko.cash[L] > 0 && Math.abs(ko.v[L] - ko.price[L] - ko.cash[L]) < 1e-6, 'a stock\'s dividends on their own line');
  }
  // leaderboards, the spread of returns: a small panel
  {
    const months = 140, cos = [['AAA', 'A Corp', 'technology'], ['BBB', 'B Corp', 'energy'], ['CCC', 'C Corp', 'technology'], ['DDD', 'D Corp', 'health']];
    const R = 'disclosures/data/market/history/rank/';
    const quarters = []; for (let y = 2009; y <= 2020; y++) for (let q = 1; q <= 4; q++) quarters.push(y + 'Q' + q);
    files[R + 'meta.json'] = { months: { start: '2010-01', n: months }, quarters, cos, cap_now: [500e3, 50e3, 5e3, 900e3], approx_cap: ['DDD'] };
    const mrow = (f) => [0, ...Array.from({ length: months }, (_, i) => f(i))];
    files[R + 'm-cap.json'] = { rows: [mrow((i) => 1e5 * (1 + i / 20)), mrow((i) => 3e5 - 1e3 * i), [60, ...Array.from({ length: 80 }, (_, i) => 5e4 + 5e3 * i)], mrow(() => 2e5)] };
    files[R + 'm-px.json'] = { rows: [mrow((i) => 10 * Math.exp(0.02 * i)), mrow((i) => 10 * Math.exp(-0.01 * i)), mrow((i) => 10 + Math.sin(i)), mrow((i) => 10 * Math.exp(0.005 * i))] };
    files[R + 'm-dv.json'] = { rows: [mrow((i) => 100 + i), mrow(() => 50), mrow(() => 10), mrow(() => 300)] };
    const qrow = (f) => [0, ...quarters.map((_, i) => f(i))];
    files[R + 'q-rev.json'] = { rows: [qrow((i) => 100 + 5 * i), qrow(() => 300), qrow((i) => 10 * (i + 1)), []] };
    files[R + 'q-ni.json'] = { rows: [qrow(() => 20), qrow(() => -5), qrow(() => 1), []] };
    files[R + 'q-oi.json'] = { rows: [qrow(() => 30), qrow(() => 10), qrow(() => 2), []] };
    let V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', from: '2010-06-30', to: '2020-12-31' }));
    ok(V.kind === 'rank' && V.rankN === 3 && V.grid.length > 100 && V.series.length >= 3, 'market value leaderboard');
    S.finish(V, V); ok(V.final.length === 3 && /^1\. /.test(V.final[0].label), 'leaderboard end card');
    const first = V.final[0].label;
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', ord: 'asc', from: '2010-06-30', to: '2020-12-31' }));
    S.finish(V, V); ok(V.final[0].label !== first, 'lowest first');
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', sec: 'technology', from: '2010-06-30' }));
    ok(V.series.every((x) => x.sec === 'technology'), 'one sector');
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', cmin: '100', capby: 'now', from: '2010-06-30' }));
    ok(V.series.map((x) => x.key).sort().join() === 'AAA,DDD', 'a market-value range (today)');
    ok([...V.notes].some((x) => /DDD/.test(x)), 'approximate market values are named');
    files['disclosures/data/etf/members.json'] = { history: { others: 'from 2026-10-25' }, rows: { AAA: { now: ['sp500'], was: { sp500: [['2015-01-01', null]] } }, DDD: { now: ['sp500'] }, BBB: { now: [], was: { sp500: [[null, '2013-06-01']] } } } };
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', idx: 'sp500', from: '2010-06-30', to: '2020-12-31' }));
    const at = (key, d) => V.series.find((x) => x.key === key)?.v[V.grid.findIndex((g) => g >= Date.parse(d))];
    ok(at('AAA', '2014-06-30') == null && at('AAA', '2016-06-30') != null && at('BBB', '2012-06-30') != null && at('BBB', '2014-06-30') == null && !V.series.some((x) => x.key === 'CCC'), 'S&P 500 members at each step');
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'cap', top: '3', idx: 'sp500', idxw: 'now', from: '2010-06-30', to: '2020-12-31' }));
    ok(V.series.map((x) => x.key).sort().join() === 'AAA,DDD' && /S&P 500 members/.test(V.title), "today's S&P 500 members: " + V.series.map((x) => x.key));
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'pe', top: '3', from: '2011-06-30', to: '2019-12-31', step: 'q' }));
    ok(V.quarterly && V.series.every((x) => x.key !== 'BBB'), 'P/E leaves losses out');
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'growth', top: '2', minrev: '0', from: '2012-01-31', to: '2019-12-31' }));
    ok(V.series.some((x) => x.key === 'CCC'), 'revenue growth');
    V = await S.build(Object.assign(S.parseState('k=rank'), { rm: 'ret', win: '12', top: '2', from: '2012-01-31', to: '2019-12-31' }));
    S.finish(V, V); ok(V.final[0].label === '1. AAA', '12-month return');
    for (const t of [0, 2, 6, 11.9]) for (const ar of [[1920, 1080], [1080, 1920]]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: 'clean', dur: 12 }, t); n++; }
    await assert.rejects(S.build(Object.assign(S.parseState('k=dist'), { from: '2011-01-01' })), /twenty|enough/); n++;
    // forty companies: the spread of each year's returns
    S.resetPanel();
    const many = Array.from({ length: 40 }, (_, j) => ['T' + j, 'T' + j + ' Inc', j % 2 ? 'energy' : 'technology']);
    files[R + 'meta.json'] = { months: { start: '2010-01', n: months }, quarters, cos: many, cap_now: many.map(() => 1e4) };
    files[R + 'm-px.json'] = { rows: many.map((_, j) => mrow((i) => 10 * Math.exp((j - 20) * 0.002 * i + 0.05 * Math.sin(i + j)))) };
    V = await S.build(Object.assign(S.parseState('k=dist'), { from: '2011-01-01' }));
    S.finish(V, V);
    ok(V.kind === 'dist' && V.hist.yrs.length >= 8 && V.final.length >= 2 && Math.abs(V.hist.yrs[2].shares.reduce((a, x) => a + x, 0) - 1) < 1e-9, 'the spread of returns');
    V.style = 'hist'; V.endCard = true; for (const ar of [[1920, 1080], [1080, 1920]]) for (const t of [0, 5, 11.9]) S.draw(ctx, ar[0], ar[1], V, { theme: 'bull', dur: 12 }, t);
    n++;
  }
  // drawdowns and monthly returns
  {
    let V = await S.build(Object.assign(S.parseState('k=drawdown'), { t: 'AAA,BBB', from: start }));
    ok(V.series.every((x) => x.v.every((v) => v == null || v <= 1e-12)) && V.series.some((x) => x.v.some((v) => v < -0.01)), 'drawdowns are at or below zero');
    S.finish(V, V);
    for (const style of ['area', 'line', 'bars', 'tiles']) { V.style = style; V.endCard = true; for (const t of [0, 5, 11.9]) S.draw(ctx, 1920, 1080, V, { theme: 'bull', dur: 12 }, t); n++; }
    V = await S.build(Object.assign(S.parseState('k=calendar'), { t: 'AAA', from: '2021-01-01' }));
    ok(V.cal.years.length >= 3 && V.cal.cells.filter((c) => c[2] != null).length > 30, 'monthly returns');
    S.finish(V, V); ok(V.final.length >= 4 && /in all/.test(V.endTitle), 'monthly returns end card');
    V.style = 'heat'; V.endCard = true; for (const ar of [[1920, 1080], [1080, 1920], [1080, 1080]]) for (const t of [0, 5, 11.9]) S.draw(ctx, ar[0], ar[1], V, { theme: 'clean', dur: 12 }, t);
    n++;
  }
  // six more: bubbles, the market as a map, sector weights, the earnings flow, the dividend snowball, timing
  {
    S.resetPanel();
    const months = 140, R = 'disclosures/data/market/history/rank/';
    const quarters = []; for (let y = 2009; y <= 2020; y++) for (let q = 1; q <= 4; q++) quarters.push(y + 'Q' + q);
    const cos = [['AAA', 'A Corp', 'technology'], ['BBB', 'B Corp', 'energy'], ['CCC', 'C Corp', 'technology'], ['DDD', 'D Corp', 'health'], ['EEE', 'E Corp', 'energy'], ['FFF', 'F Corp', 'financials']];
    files[R + 'meta.json'] = { months: { start: '2010-01', n: months }, quarters, cos, cap_now: [5e5, 5e4, 5e3, 9e5, 2e4, 1e5] };
    const mrow = (f) => [0, ...Array.from({ length: months }, (_, i) => f(i))], qrow = (f) => [0, ...quarters.map((_, i) => f(i))];
    files[R + 'm-cap.json'] = { rows: [mrow((i) => 1e5 * (1 + i / 20)), mrow((i) => 3e5 - 1e3 * i), mrow((i) => 5e4 + 500 * i), mrow(() => 2e5), mrow((i) => 1e4 + 100 * i), mrow((i) => 8e4 + 200 * i)] };
    files[R + 'm-px.json'] = { rows: cos.map((_, j) => mrow((i) => 10 * Math.exp((0.004 * (j - 2)) * i + 0.03 * Math.sin(i / 3 + j)))) };
    files[R + 'm-dv.json'] = { rows: cos.map((_, j) => mrow(() => 100 * (j + 1))) };
    files[R + 'q-rev.json'] = { rows: cos.map((_, j) => qrow((i) => 1e4 * (j + 1) * (1 + 0.0025 * (j + 1) * i))) };
    files[R + 'q-ni.json'] = { rows: cos.map((_, j) => qrow(() => 500 * (j + 1))) };
    files[R + 'q-oi.json'] = { rows: cos.map((_, j) => qrow(() => 800 * (j + 1))) };
    // bubbles
    let V = await S.build(Object.assign(S.parseState('k=bubble'), { bn: '5', from: '2012-01-31', to: '2020-12-31' }));
    ok(V.kind === 'bubble' && V.series.length === 5 && !V.series.some((x) => x.key === 'EEE') && V.series.every((x) => x.x.length === V.grid.length && x.s.length === V.grid.length), 'bubbles: the five largest at the end');
    ok(V.bub.kx === 'growth' && V.bub.ky === 'ret' && V.bub.dx[0] < V.bub.dx[1] && V.bub.smax > 0, 'bubble axes');
    S.finish(V, V); ok(V.final.length === 5 && V.final[0].label === 'AAA' && /·/.test(V.final[0].value), 'bubble end card: ' + V.final.map((r) => r.label));
    for (const t of [0, 4, 11.9]) for (const ar of [[1920, 1080], [1080, 1920]]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: 'bull', dur: 12 }, t); } n++;
    V = await S.build(Object.assign(S.parseState('k=bubble'), { bt: 'AAA, CCC', bx: 'pe', by: 'growth', bs: 'rev', from: '2012-01-31', to: '2020-12-31' }));
    ok(V.series.map((x) => x.key).join() === 'AAA,CCC' && V.bub.logx && V.metric === 'Revenue, last 12 months', 'bubbles for typed companies, P/E on a log axis');
    S.draw(ctx, 1920, 1080, V, { theme: 'clean', dur: 12 }, 6); n++;
    // the market as a map
    const sq = S.squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 600, 400), area = sq.reduce((a, r) => a + r[2] * r[3], 0);
    ok(Math.abs(area - 240000) < 1e-6 && sq.every((r) => r[0] >= -1e-9 && r[1] >= -1e-9 && r[0] + r[2] <= 600 + 1e-6 && r[1] + r[3] <= 400 + 1e-6) && Math.abs(sq[0][2] * sq[0][3] / (sq[6][2] * sq[6][3]) - 6) < 1e-6, 'squarified rectangles fill the box in proportion');
    V = await S.build(Object.assign(S.parseState('k=treemap'), { tn: '10', from: '2011-01-31', to: '2020-12-31' }));
    ok(V.kind === 'treemap' && V.grid.every((_, j) => V.series.filter((x) => x.v[j] > 0).length <= 10), 'the map keeps the top N each month');
    V = await S.build(Object.assign(S.parseState('k=treemap'), { tn: '10', sec: 'energy', from: '2011-01-31', to: '2020-12-31' }));
    ok(V.series.every((x) => x.sec === 'energy') && V.series.length === 2, 'the map, one sector');
    V = await S.build(Object.assign(S.parseState('k=treemap'), { tn: '10', from: '2011-01-31', to: '2020-12-31' }));
    const aaa = V.series.find((x) => x.key === 'AAA'), L = V.grid.length - 1;
    ok(Math.abs(aaa.r[L] - (Math.exp(0.004 * -2 * 12) * Math.exp(0.03 * Math.sin(131 / 3) - 0.03 * Math.sin(119 / 3)) - 1)) < 1e-9, 'the map colours by the 12-month return');
    S.finish(V, V); ok(V.final.length === 6 && /^1\. AAA/.test(V.final[0].label), 'map end card');
    for (const tc of ['ret', 'sector']) { V.tm.color = tc; for (const ar of [[1920, 1080], [1080, 1920]]) for (const t of [0, 6, 11.9]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: tc === 'ret' ? 'bull' : 'clean', dur: 12 }, t); } n++; }
    // sector weights
    V = await S.build(Object.assign(S.parseState('k=sectors'), { from: '2011-01-31', to: '2020-12-31' }));
    ok(V.kind === 'sectors' && V.grid.every((_, j) => Math.abs(V.series.reduce((a, x) => a + (x.v[j] || 0), 0) - 1) < 1e-9), 'sector shares add to 100%');
    ok(V.series[0].key === 'health' || V.series[0].key === 'technology', 'the largest sector first');
    S.finish(V, V); ok(V.final.length === 4 && / pts$/.test(V.final[0].change), 'sector end card in points');
    for (const ar of [[1920, 1080], [1080, 1920]]) for (const t of [0, 6, 11.9]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: 'clean', dur: 12 }, t); } n++;
    V = await S.build(Object.assign(S.parseState('k=sectors'), { sa: 'abs', from: '2011-01-31', to: '2020-12-31' }));
    ok(!V.stack.share && V.series.find((x) => x.key === 'health').v[0] === 2e5 * 1e6, 'sector market value in dollars');
    S.finish(V, V); S.draw(ctx, 1920, 1080, V, { theme: 'bull', dur: 12 }, 6); n++;
  }
  {
    // the earnings flow: the detailed quarters when there are two or more, else ten years of revenue → profit → earnings
    const ix = files['data/index.json']; ix.companies.push({ ticker: 'YYY', cik: 8, name: 'Why Inc', revenue: 1 });
    const qtr = (end, label, rev, gp, oi) => ({ end, label, headline: { revenue: rev, oi, ni: oi * 0.8, yoy: 12 },
      nodes: [{ id: 'revenue', col: 0, color: 'rev', name: 'Revenue', v: rev, lines: [['name', 'Revenue'], ['val', '$' + rev + ' &amp; more']] }, { id: 'gp', col: 1, color: 'profit', name: 'Gross profit', v: gp }, { id: 'cogs', col: 1, color: 'cost', name: 'Cost of revenue', v: rev - gp }, { id: 'oi', col: 2, color: 'profit', name: 'Operating profit', v: oi }, { id: 'opex', col: 2, color: 'cost', name: 'Operating expenses', v: gp - oi }],
      links: [{ s: 'revenue', t: 'gp', v: gp, color: 'profit' }, { s: 'revenue', t: 'cogs', v: rev - gp, color: 'cost' }, { s: 'gp', t: 'oi', v: oi, color: 'profit' }, { s: 'gp', t: 'opex', v: gp - oi, color: 'cost' }] });
    const q3 = qtr('2024-09-30', 'Q3 2024', 120, 70, 30); delete q3.nodes[4]; q3.nodes = q3.nodes.filter(Boolean); q3.links = q3.links.slice(0, 3);
    files['data/c/8.json'] = { profile: { name: 'Why Inc' }, quarters: [qtr('2024-06-30', 'Q2 2024', 100, 60, 20), qtr('2024-03-31', 'Q1 2024', 90, 50, 15), q3, { end: '2024-12-31', label: 'FY 2024', nodes: [], links: [] }] };
    let V = await S.build(Object.assign(S.parseState('k=sankey'), { t: 'YYY' }));
    ok(V.kind === 'sankey' && !V.sk.simple && V.sk.frames.map((f) => f.label).join() === 'Q1 2024,Q2 2024,Q3 2024' && V.sk.max === 120, 'the detailed flow, quarters in order, annual left out');
    S.finish(V, V); ok(V.final[0].label === 'Revenue' && V.final[0].value === S.money(120) && V.final[0].change === '+33%' && V.final.some((r) => r.label === 'Operating margin'), 'flow end card');
    for (const ar of [[1920, 1080], [1080, 1920]]) for (const t of [0, 3.3, 6.5, 11.9]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: 'clean', dur: 12 }, t); } n++;
    V = await S.build(Object.assign(S.parseState('k=sankey'), { t: 'ZZZ' }));
    ok(V.sk.simple && V.sk.frames.length === 20 && [...V.notes].some((x) => /ten years/.test(x)), 'ten years of quarters when there are no detailed ones');
    const f0 = V.sk.frames[0], sum = (id) => f0.links.filter((l) => l.s === id).reduce((a, l) => a + l.v, 0);
    ok(Math.abs(sum('revenue') - f0.head.revenue) < 1e-9 && Math.abs(sum('oi') - f0.head.oi) < 1e-9, 'what flows out of revenue and profit adds up');
    S.finish(V, V); for (const t of [0, 6, 11.9]) S.draw(ctx, 1920, 1080, V, { theme: 'bull', dur: 12 }, t); n++;
    await assert.rejects(S.build(Object.assign(S.parseState('k=sankey'), { t: 'NOPE' })), /No company/); n++;
    // the dividend snowball
    V = await S.build(Object.assign(S.parseState('k=snowball'), { t: 'AAA,BBB', amt: '10000', from: start }));
    const a = V.series.find((x) => x.key === 'AAA'), La = a.v.length - 1;
    ok(a.fromDiv > 0 && Math.abs(a.sh[La] - a.bought - a.fromDiv) < 1e-9 && Math.abs(a.bought - a.sh0) < 1e-9 && a.sh[La] > a.sh0, 'dividends buy shares on top of those paid for');
    const paid = a.paid.reduce((s, x) => s + x, 0), yearly = Object.values(a.yearly).reduce((s, x) => s + x, 0);
    ok(Math.abs(paid - yearly) < 1e-6 && paid > 0 && V.contrib[La] === 10000, 'each year\'s dividends add up to all paid');
    ok(a.sh.every((v, i) => !i || v == null || a.sh[i - 1] == null || v >= a.sh[i - 1] - 1e-12), 'the share count only grows');
    S.finish(V, V); ok(V.final.length >= 2 && /shares/.test(V.final[0].label) && /^\+\d+% shares$/.test(V.final[0].change), 'snowball end card');
    for (const ar of [[1920, 1080], [1080, 1920]]) for (const t of [0, 5, 11.9]) { V.endCard = true; S.draw(ctx, ar[0], ar[1], V, { theme: 'bull', dur: 12 }, t); } n++;
    V = await S.build(Object.assign(S.parseState('k=snowball'), { t: 'AAA', amt: '0', rec: '100', ri: '1', ru: 'm', from: start }));
    ok(V.series[0].bought > 0 && V.contrib[V.contrib.length - 1] > 5000, 'the snowball with monthly buying');
    // timing
    V = await S.build(Object.assign(S.parseState('k=timing'), { t: 'AAA', yb: '2000', from: '2020-01-01' }));
    const end = (k) => V.series.find((x) => x.key === k).v[V.grid.length - 1];
    ok(V.kind === 'timing' && V.series.length === 4 && V.timing.years === 5 && V.contrib[V.grid.length - 1] === 10000, 'four strategies, the same money each year: ' + V.timing.years);
    ok(['first', 'monthly', 'worst'].every((k) => end('best') >= end(k) - 1e-9) && ['best', 'first', 'monthly'].every((k) => end('worst') <= end(k) + 1e-9), 'the bottom beats everything, the top loses to everything');
    ok(V.series.every((s) => Math.abs(-s.flows.reduce((x, f) => x + f[1], 0) - 10000) < 1e-6), 'every plan puts in the same money');
    ok(V.series.every((s) => s.v.every((v, i) => i === 0 || v != null)), 'cash waiting for the buy counts in the value');
    S.finish(V, V); ok(V.final.length === 4 && V.final[0].name === 'Bought at the bottom' && V.final[3].name === 'Bought at the top' && /%\/yr/.test(V.final[0].label) && /^Worst timing/.test(V.endTitle), 'timing end card');
    for (const style of ['line', 'bars', 'tiles']) { V.style = style; for (const t of [0, 5, 11.9]) { V.endCard = true; S.draw(ctx, 1920, 1080, V, { theme: 'sunset', dur: 12 }, t); } n++; }
    // the templates all parse and each new kind has one
    ok(['bubble', 'treemap', 'sectors', 'sankey', 'snowball', 'timing'].every((k) => S.TEMPLATES.some((t) => t.s.k === k)), 'a template for each new kind');
    const tl = S.TEMPLATES.find((t) => t.s.k === 'timing');
    ok(S.parseState(S.serialize(Object.assign(S.parseState(''), tl.s)).slice(7)).yb === '2000', 'the timing address keeps the yearly amount');
  }
  // the page loads the studio, the router and the menu know it
  const idx = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8'), app = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8'), nav = fs.readFileSync(path.join(__dirname, '..', 'web', 'nav.js'), 'utf8');
  ok(idx.includes('<script src="studio.js"></script>') && app.includes('window.FFStudio.render') && nav.includes("'#studio'"), 'the studio is not wired into the page');
  console.log(`Video studio: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exitCode = 1; });
