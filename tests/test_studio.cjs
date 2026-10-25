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
  // the page loads the studio, the router and the menu know it
  const idx = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8'), app = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8'), nav = fs.readFileSync(path.join(__dirname, '..', 'web', 'nav.js'), 'utf8');
  ok(idx.includes('<script src="studio.js"></script>') && app.includes('window.FFStudio.render') && nav.includes("'#studio'"), 'the studio is not wired into the page');
  console.log(`Video studio: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exitCode = 1; });
