'use strict';
// The hub's chart players as video files (rot-video.js): the frame schedule (held first and last frames, one chart
// frame every `ms` at the speed chosen) and the frame layout, without a browser.
const assert = require('node:assert/strict');
const V = require('../docs/rot-video.js');
let n = 0;
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };

const S = V.schedule({ fps: 30, ms: 110, frames: 260, hold: [0.6, 2] });
eq([S.fps, S.n, S.N], [30, 260, Math.round((0.6 + 259 * 0.11 + 2) * 30)], 'frames of a 260-week play at 110 ms a week');
eq(S.at(0), 0, 'the first chart frame is held');
eq(S.at(Math.round(0.6 * 30) - 1), 0, 'held for the first 0.6 s');
eq(S.at(Math.ceil((0.6 + 0.11) * 30)), 1, 'the second week after 110 ms');
eq(S.at(S.N - 1), 259, 'the last chart frame is held to the end');
assert.ok([...Array(S.N).keys()].every((i, k, a) => k === 0 || S.at(i) >= S.at(a[k - 1])), 'the chart frames never go backwards'); n++;
const fast = V.schedule({ fps: 30, ms: 55, frames: 260, hold: [0.6, 2] });
assert.ok(fast.seconds < S.seconds && fast.at(fast.N - 1) === 259, 'twice the speed: half the time, the same frames'); n++;
eq(V.schedule({ fps: 30, ms: 110, frames: 1 }).at(5), 0, 'one frame: held');

// the layout: a measuring context that counts characters
const ctx = { font: '', measureText: (t) => ({ width: 7 * t.length }) };
const L = V.layout(ctx, { title: 'Relative Rotation Graph', subtitle: 'a '.repeat(400), source: 'Weekly closes' }, 1920, 1080);
eq(L.tl, ['Relative Rotation Graph'], 'the title on one line');
assert.ok(L.sl.length === 2 && L.fl.length === 2, 'the subtitle cut to two lines, the source and the date line'); n++;
assert.ok(L.top > L.pad && L.bottom > L.pad && L.top + L.bottom < 1080 / 2, 'the chart keeps most of the height'); n++;
const P = V.layout(ctx, { title: 'RRG' }, 1080, 1920);
assert.ok(P.ts === L.ts && P.top + P.bottom < 1920 / 3, 'a phone-shaped video: type sized by the short side, the chart keeps the height'); n++;
console.log(`rot-video: ${n} checks passed`);
