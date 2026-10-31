// Corporate investors (web/investors.js): number formats, the chart drawing (one y-axis, stacked and grouped columns,
// a hit area per quarter), the investee keys the pages link with (the same as pipeline/investments.py key_of), and the
// amount cell. The pages themselves are checked in a browser.
const assert = require('node:assert/strict');
globalThis.window = globalThis;
require('../web/investors.js');
const T = globalThis.FFInvestors._t;
let n = 0;
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };
const ok = (c, m) => { assert.ok(c, m); n++; };

// money and shares
eq(T.usd(143.7e9), '$144B');
eq(T.usd(12.4e9), '$12.4B');
eq(T.usd(-5e8), '−$500M');
eq(T.usd(63.9e9, true), '+$63.9B');
eq(T.usd(null), '—');
eq(T.usd(2.1e12), '$2.10T');
eq(T.pct(0.4489), '45%');
eq(T.pct(null), '—');

// keys: as the pipeline writes them, so a link from a name lands on its investee page
eq(T.keyOf('Anthropic, PBC'), 'anthropic');
eq(T.keyOf('OpenAI Global LLC'), 'openai');
eq(T.keyOf('The Coca-Cola Company'), 'coca cola');
eq(T.keyOf('OpenAI’s'), 'openai');
eq(T.keyOf('Crux AI'), 'crux ai');

// axis ticks: round steps that cover the data
eq(T.ticks(0, 143.7e9), [0, 50e9, 100e9, 150e9]);
eq(T.ticks(-2e9, 9e9), [-5e9, 0, 5e9, 10e9]);
ok(T.ticks(0, 1).length >= 2, 'a flat series still gets an axis');

// quarter labels
eq(T.shortQ({ label: 'Q3 2026' }), 'Q3 ’26');
eq(T.shortQ({ label: 'Q2 FY27' }), 'Q2 FY27');

// a year ago: the balance about 365 days before the latest one
const q = [{ end: '2025-09-30', nm: 16e9 }, { end: '2026-06-30', nm: 122.3e9 }, { end: '2026-09-30', nm: 143.7e9 }];
eq(T.yearAgo(q, 'nm'), 16e9);
eq(T.yearAgo(q, 'em'), null);

// columns: stacked balances, then pretax income beside gains (with a loss below zero)
const rows = [{ end: '2026-03-31', label: 'Q1 2026', nm: 48.1e9, em: 0.9e9 }, { end: '2026-06-30', label: 'Q2 2026', nm: 122.3e9, em: 0.4e9 },
  { end: '2026-09-30', label: 'Q3 2026', nm: 143.7e9, em: 0.4e9 }];
const svg = T.columns(rows, [[{ k: 'nm', c: '--iv-nm' }, { k: 'em', c: '--iv-em' }]], { aria: 'balances', label: (r) => r.nm + r.em });
ok(!/NaN|undefined/.test(svg), 'no NaN in the drawing');
eq((svg.match(/<rect data-i=/g) || []).length, 3, 'one hover area per quarter');
eq((svg.match(/<path /g) || []).length, 6, 'two stacked segments per quarter');
ok(svg.includes('$144B'), 'the latest total at the end of its column');
ok(svg.includes('Q3 ’26'), 'quarter labels');
const g = T.columns([{ end: 'a', label: 'Q1 2026', pti: 39.8e9, g: 11.4e9 }, { end: 'b', label: 'Q2 2026', pti: 26.9e9, g: -0.6e9 }],
  [[{ k: 'pti', c: '--iv-pt' }], [{ k: 'g', c: '--iv-g' }]], { aria: 'gains' });
ok(!/NaN/.test(g) && (g.match(/<path /g) || []).length === 4, 'grouped columns, a loss drawn below zero');
const narrow = T.columns(rows, [[{ k: 'nm', c: '--iv-nm' }]], { narrow: true });
ok(/viewBox="0 0 380 /.test(narrow), 'a narrower drawing on a phone, so its text stays legible');

// column ends: rounded at the data end, square at the baseline
const up = T.colPath(10, 100, 40, 20, 4), down = T.colPath(10, 100, 160, 20, 4);
ok(up.startsWith('M10,100') && up.includes('Q10,40'), 'a positive column rounds its top');
ok(down.startsWith('M10,100') && down.includes('Q10,160'), 'a negative column rounds its bottom');
eq(T.colPath(0, 50, 50, 10, 4), '', 'nothing drawn for zero');

// the amount cell says what the number is and where it came from
const cell = T.bestCell({ k: 'value', usd: 75.2e9, at: '2026-09-30', how: 'xbrl', l: 'Marketable equity securities' });
ok(cell.includes('$75.2B') && cell.includes('carrying value') && cell.includes('Sep 30, 2026') && cell.includes('tagged: Marketable'), cell);
ok(T.bestCell({ k: 'invested', usd: 5e10, how: 'text' }).includes('stated in the text'));
ok(T.bestCell(null).includes('no amount'));

console.log(`investors: ${n} checks passed`);
