// closecast.js: the Close forecast tab's numbers (normal quantiles, ranges at any confidence, P(close above a price)) and
// its page drawn from a real forecast (fixtures/closecast_sample.json: SPY and NVDA from app/closecast.py) with the
// hub's helpers stubbed — no browser, no network; a freeze kept and set against the live forecast.
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.head = (t, s, tag) => `<h2>${t}</h2><p>${s}</p><span>${tag}</span>`;
global.field = (id, l, items, v) => `<select id="${id}">${items.map(([a, b]) => `<option value="${a}"${a === v ? ' selected' : ''}>${b}</option>`).join('')}</select>`;
global.state = { tab: 'forecast' };
global.$ = () => null;
global.fetch = undefined;                       // no network: the closes and the record come from the store
global.window = { innerWidth: 1200 };
const store = {};
global.localStorage = { getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = String(v); } };
const V = require('../docs/closecast.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, tol, m) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };

// the normal quantile and cdf
near(V.cfInvN(0.975), 1.959964, 1e-5, 'z at 97.5%');
near(V.cfInvN(0.005), -2.575829, 1e-5, 'z at 0.5%');
near(V.cfN(1.2816), 0.9, 1e-4, 'cdf at 1.28');
// a forecast of log returns that is a normal of sd 1%: any confidence, and P(above)
const d = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'closecast_sample.json'), 'utf8'));
const zg = V.cfZ(d.pgrid), q = zg.map((z) => 0.01 * z);
const r80 = V.cfRange(q, 0.8, zg), r95 = V.cfRange(q, 0.95, zg), r60 = V.cfRange(q, 0.6, zg);
near(r80[2], 0.012816, 2e-5, '80% high');
near(r95[0], -0.0196, 2e-5, '95% low');
near(r60[2], 0.01 * V.cfInvN(0.8), 2e-4, '60% high (between the grid points)');
near(V.cfQ(q, 0.5, zg), 0, 1e-12, 'median');
near(1 - V.cfCdf(q, 0.01, zg), 0.1587, 2e-3, 'P(above +1 sd)');
ok(V.cfCdf(q, -1, zg) < 0.01 && V.cfCdf(q, 1, zg) > 0.99, 'beyond the grid: the tails');

// the page from a real forecast
V.cfStore.fc = { data: d, at: Date.now() };
for (const k of ['SPY', 'NVDA']) {
  state.cfa = k; state.cfc = 80; state.cft = ''; state.cfcmp = '';
  const html = V.cfBody(d);
  ok(html.includes('80% range'), `${k}: the range`);
  ok(!/NaN|undefined|Infinity/.test(html), `${k}: no broken numbers`);
  ok((html.match(/data-cft="/g) || []).length >= 2 * d.assets[k].targets.length, `${k}: every date in the chart and the table`);
  ok(html.includes('Sources ·'), `${k}: the sources`);
}
// another confidence moves the range; a price gives its probability
state.cfa = 'SPY'; state.cfc = 95; state.cfx = String(Math.round(d.assets.SPY.price));
const h95 = V.cfBody(d);
ok(h95.includes('95% range') && h95.includes(`P(above ${fmt(Math.round(d.assets.SPY.price), 2)})`), 'the 95% range and P(above the price typed)');
// a freeze, kept and set against the live forecast; a date that has closed scored against it
const id = V.cfFreezeNow(d, d.assets.SPY);
ok(V.cfMine().length === 1 && V.cfMine()[0].asset === 'SPY', 'the freeze is kept');
state.cfcmp = id; state.cfx = null;
const t0 = d.assets.SPY.targets[0];
V.cfStore.closes = { data: { SPY: { [t0.date]: d.assets.SPY.start } }, at: Date.now() };
const hf = V.cfBody(d);
ok(hf.includes('Frozen median') && hf.includes('Your freeze'), 'frozen against live');
ok(hf.includes('inside the frozen range'), 'the close scored against the frozen range');
ok(V.cfTargetLabel({ date: '2026-11-13', tags: ['expiry', 'week'] }, { phase: 'open' }).tags === 'options expiry · week end', 'labels');
console.log(`closecast view: ${n} checks passed`);
