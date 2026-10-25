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
  // the page loads the studio, the router and the menu know it
  const idx = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8'), app = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8'), nav = fs.readFileSync(path.join(__dirname, '..', 'web', 'nav.js'), 'utf8');
  ok(idx.includes('<script src="studio.js"></script>') && app.includes('window.FFStudio.render') && nav.includes("'#studio'"), 'the studio is not wired into the page');
  console.log(`Video studio: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exitCode = 1; });
