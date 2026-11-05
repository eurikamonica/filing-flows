'use strict';
// Custom charts (web/charts.js): the history's fourth quarters (a 10-K's year less its first three quarters), the
// margin of every quarter, and dates under the axis that never crowd each other.
const assert = require('node:assert/strict');
globalThis.FFUx = { esc: (s) => String(s), t: (s) => String(s), fin: (v) => v != null && Number.isFinite(+v), num: (v, d) => (+v).toFixed(d), money: (v) => '$' + v, day: (s) => s, dec: (s) => s, PALETTE: ['#111', '#222', '#333'] };
const C = require('../web/charts.js');
const P = [['', '2021-03-31', 'q'], ['', '2021-06-30', 'q'], ['', '2021-09-30', 'q'], ['', '2021-12-31', 'fy'], ['', '2022-03-31', 'q']];
const v = (pi, x) => [pi, [[x, [1, '3m', []]]]];
const c = { quality: { hist: { periods: P, v: { revenue: [v(0, 100), v(1, 110), v(2, 120), v(3, 470), v(4, 130)], oi: [v(0, 10), v(1, 11), v(2, 12), v(3, 50), v(4, 14)] } } }, quarters: [] };
const { S } = C.seriesOf(c);
assert.equal(S['h:revenue'].get('2021-12-31'), 140);                         // 470 − (100 + 110 + 120)
assert.equal(S['h:oi'].get('2021-12-31'), 17);
assert.equal(S['h:om'].get('2021-12-31'), 100 * 17 / 140);                   // the margin of a history quarter
assert.equal(S['h:om'].get('2021-03-31'), 10);
const bad = { quality: { hist: { periods: P.slice(1), v: { revenue: [v(0, 110), v(1, 120), v(2, 470)] } } }, quarters: [] };
assert.equal(C.seriesOf(bad).S['h:revenue'].has('2021-12-31'), false);         // two quarters on file: no fourth derived
// 38 quarters: the last date and the one before it never overlap
const ends = []; for (let y = 2017; y <= 2026; y++) for (const m of ['03-31', '06-30', '09-30', '12-31']) ends.push(`${y}-${m}`);
const pts = ends.slice(0, 38).map((e, i) => [e, 100 + i]);
const out = C.svg([{ company: 'A', ticker: 'A', label: 'Revenue', unit: '$', pts }], 'line');
const xs = [...out.matchAll(/<text class="fx-ax" x="([\d.]+)" y="\d+" text-anchor="middle">/g)].map((m) => +m[1]).sort((a, b) => a - b);
assert(xs.length >= 5 && xs.every((x, i) => !i || x - xs[i - 1] >= 64), 'dates apart: ' + xs);
console.log('Custom charts: fourth quarters, margins and axis dates passed');
