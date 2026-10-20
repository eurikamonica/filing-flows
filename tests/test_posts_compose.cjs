// posts.js: the Today post and the composer (tick the angles, one post) on synthetic data — no browser.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const src = fs.readFileSync(path.join(__dirname, '..', 'disclosures', 'docs', 'posts.js'), 'utf8');
const ctx = { window: {}, fetch: () => Promise.resolve({ ok: false }), console, Date, Math, JSON, Object, Array, Number, String, RegExp, Map, Set, Promise, encodeURIComponent };
ctx.globalThis = ctx; vm.createContext(ctx); vm.runInContext(src, ctx);
const P = ctx.window.FFPosts;
const hist = []; let px = 100;
for (let i = 0; i < 40; i++) { px *= 1 + (i % 2 ? 0.004 : -0.003); hist.push([`2026-09-${String(1 + (i % 28)).padStart(2, '0')}`, +px.toFixed(2)]); }
hist[hist.length - 1][0] = '2026-10-16';
const B = {
  ticker: 'CRWV', cik: 1769628, name: 'CoreWeave',
  lad: { spot: 63.4, spot_time: '2026-10-19 15:00 UTC', hourly: [['2026-10-16T20', 61.0], ['2026-10-19T14', 62.1], ['2026-10-19T15', 63.4]] },
  options: { rows: [{ ticker: 'CRWV', history: hist.map(([d, v]) => [d, v * 0.61]) }, { ticker: 'SPY', history: [['2026-10-16', 600], ['2026-10-19', 603]] }] },
  opt: { iv30: 80 }, ext: { hi52: 140, lo52: 40, from_hi: -0.56, from_lo: 0.5, ytd: -0.4, new_lo: 0, new_hi: 0, dollar_vol: 3e9, asof: '2026-10-16' },
  cons: { analysts: { price: 61, targets: { mean: 70 }, rating: { mean: 2.7 } }, next_earnings: { date: '2026-10-23' }, beat_rate: 0.75,
          markets: [{ kind: 'beat', p: 0.52, eps_strike: 1.15, source: 'polymarket' }] },
  smart: { now: { S: 35, n: 12 } }, val: { price: 61, mc: { p_above: 0.62 }, pvgo: { growth_share: 0.7 }, bands: { pe: { pct: 0.2 } } },
  qual: { row: { f_score: 7, z_zone: 'grey' } },
  holders: { events8k: [{ filed: '2026-10-10', label: 'Material agreement', headline: 'CoreWeave signs a supply agreement' }],
             insiders: [{ code: 'P', insider: 'Intrator Michael', title: 'CEO', value: 3e6, price: 60, date: '2026-10-15' }] },
  debt: { analysis: { net_debt: 8e9, net_leverage: 3.1, cushion_score: 41, total_debt: 1e10, cash_and_investments: 2e9 } },
  site: { quarters: [{ label: 'Q2 FY2026', headline: { rev_fmt: '$2.6B', yoy: 112, ni_fmt: '−$44M', om: 5.2 }, analysis: [] }], profile: { tickers: ['CRWV'], name: 'CoreWeave' } },
};
const q = P.quote(B);
assert.equal(q.price, 63.4); assert.ok(Math.abs(q.prev - hist[hist.length - 1][1] * 0.61) < 1e-6 && q.prevDay === "2026-10-16"); assert.ok(q.live && q.dayHi === 63.4 && q.dayLo === 62.1);
const t = P.build('today', B);
assert.ok(t && t.kind === 'today' && /^\$CRWV \$63\.40 \(\+\d+\.\d%\) — Oct 19\./.test(t.post), t.post);
assert.ok(/52-week range \$40\.00–\$140\.00/.test(t.paras.join(' ')) && /Year to date −40%/.test(t.paras.join(' ')), t.paras);
assert.ok(/SPY \+0\.5%/.test(t.post) && P.xlen(t.post) <= 280, t.post);
const A = P.angles(B), ids = A.map((a) => a.id);
assert.equal(ids.join(), 'today,stance,8k,insiders,earnings,analysts,smart,range,debt,quarter');
const st = A.find((a) => a.id === 'stance').text;
assert.ok(/leans cheap: 62% of our DCF scenarios land above \$63\.40, 70% of the price is growth, P\/E at the 20th pct of its own range\.$/.test(st), st);
assert.ok(!/\b(buy|sell)\b/i.test(st));
assert.ok(/Reports Oct 23; Polymarket 52% it beats the \$1\.15 EPS line; beat 75%/.test(A.find((a) => a.id === 'earnings').text));
assert.ok(/mean target \$70\.00, consensus Hold \(2\.7\)/.test(A.find((a) => a.id === 'analysts').text));
assert.ok(A.find((a) => a.id === 'quarter').text.startsWith('Q2 FY2026: revenue $2.6B (+112% Y/Y), net −$44M, 5.2% operating margin.'));
assert.ok(A[0].on && A.slice(1).every((a) => !a.on));
A.find((a) => a.id === 'stance').on = true; A.find((a) => a.id === '8k').on = true;
const text = P.composeText(B, A, 'Opportunity or trap? 👇', true);
assert.ok(text.startsWith('$CRWV $63.40') && text.includes('leans cheap') && text.includes('8-K on Oct 10') && text.includes('Opportunity or trap?') && text.includes('#c-1769628'), text);
A.forEach((a) => { a.on = true; });
const all = P.composeText(B, A, '', false);
assert.ok(P.xlen(all) > 280 && all.startsWith('$CRWV $63.40') && all.includes('cushion score 41/100') && all.endsWith('operating margin.'), all);   // nothing dropped: the count goes red, the owner trims
assert.equal(P.composeText(B, A.map((a) => ({ ...a, on: false })), 'x', true), '');
assert.equal(P.build('today', { ticker: 'X', name: 'X' }), null);
console.log('posts compose: all checks passed');
