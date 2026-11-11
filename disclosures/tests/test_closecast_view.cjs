// closecast.js: the Close forecast tab's numbers (normal quantiles, ranges at any confidence, P(close above a price)) and
// its page drawn from a real forecast (fixtures/closecast_sample.json: SPY and AAPL from app/closecast.py) with the
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
global.localStorage = { getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = String(v); }, key: (i) => Object.keys(store)[i] ?? null, get length() { return Object.keys(store).length; } };
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
// the expected value: of a normal log return (μ 1%, σ 10%) exp(μ + σ²/2) — above the median exp(μ); a heavier fall tail pulls it under
near(V.cfMean(zg.map((z) => 0.01 + 0.1 * z), zg), Math.exp(0.01 + 0.005), 2e-4, 'the mean of a lognormal');
ok(V.cfMean(zg.map((z) => 0.01 * z + (z < 0 ? 0.01 * z : 0)), zg) < 1, 'skewed to the downside: the mean under the median');
near(1 - V.cfCdf(q, 0.01, zg), 0.1587, 2e-3, 'P(above +1 sd)');
ok(V.cfCdf(q, -1, zg) < 0.01 && V.cfCdf(q, 1, zg) > 0.99, 'beyond the grid: the tails');

// the page from a real forecast
V.cfStore.fc = { data: d, at: Date.now() };
for (const k of ['SPY', 'AAPL']) {
  state.cfa = k; state.cfc = 80; state.cft = ''; state.cfcmp = '';
  const html = V.cfBody(d);
  ok(html.includes('80% range'), `${k}: the range`);
  ok(!/NaN|undefined|Infinity/.test(html), `${k}: no broken numbers`);
  ok((html.match(/data-cft="/g) || []).length >= 2 * d.assets[k].targets.length, `${k}: every date in the chart and the table`);
  ok(html.includes('Sources ·'), `${k}: the sources`);
  ok(html.includes('Expected value') && html.includes('<th class="num">Expected</th>') && (html.match(/class="cf-evd"/g) || []).length >= d.assets[k].targets.length + 1, `${k}: the expected value in the hero, the table and on both charts`);
}
// another confidence moves the range; a price gives its probability
state.cfa = 'SPY'; state.cfc = 95; state.cfx = String(Math.round(d.assets.SPY.price));
const h95 = V.cfBody(d);
const X = fmt(Math.round(d.assets.SPY.price), 2);
ok(h95.includes('95% range') && h95.includes(`Closes above ${X}`) && h95.includes(`Trades at ${X}`), 'the 95% range, closing above and trading at the price typed');
ok(h95.includes('High by then') && h95.includes('Low by then') && h95.includes('High from now'), 'the highs and lows');
state.cfa = 'AAPL'; state.cfx = null; state.cft = d.assets.AAPL.targets.find((t) => t.tags.includes('month')).date;   // its month-end: every source
const ha = V.cfBody(d);
ok(ha.includes('At its highs') && ha.includes('pullback within a month'), 'the regime card: AAPL at its highs');
ok(ha.includes('History: highs, lows &amp; ranges') && ha.includes('History: Move odds'), 'the regime and the Move odds among the sources');
state.cfa = 'SPY';
// a freeze, kept and set against the live forecast; a date that has closed scored against it
(async () => {
  // not signed in: this browser
  ok(V.cfAccount().state === 'none', 'no session here: no account');
  const r = await V.cfFreezeNow(d, d.assets.SPY);
  ok(r.where === 'browser' && V.cfMine().length === 1 && V.cfMine()[0].asset === 'SPY', 'the freeze is kept in this browser');
  state.cfcmp = r.id; state.cfx = null;
  const t0 = d.assets.SPY.targets[0];
  V.cfStore.closes = { data: { SPY: { [t0.date]: d.assets.SPY.start } }, at: Date.now() };
  const hf = V.cfBody(d);
  ok(hf.includes('Frozen median') && hf.includes('Your freeze'), 'frozen against live');
  ok(hf.includes('inside the frozen range'), 'the close scored against the frozen range');
  ok(hf.includes('Kept in this browser only') && hf.includes('#account'), 'not signed in: kept here, with the way to sign in');
  // signed in on #account since (the same page): the account is looked at again — once per sign-in, not on every draw
  store['sb-x-auth-token'] = '{"access_token":"t1"}';
  V.cfAccount();
  ok(V.CF_ACCT.sig === 'sb-x-auth-token={"access_token":"t1"}', 'a new sign-in: the account checked again');
  const sig = V.CF_ACCT.sig; V.cfAccount();
  ok(V.CF_ACCT.sig === sig, 'the same sign-in: not checked again');
  delete store['sb-x-auth-token'];
  ok(V.cfAccount().state === 'none' && V.CF_ACCT.sig === '', 'signed out: this browser');

  // signed in: the account (Supabase forecast_freezes, every device), this browser's moved into it
  const db = [{ id: 'old', asset: 'SPY', frozen_at: '2026-11-09T19:00:00+00:00', payload: { start: 750, prev: 748, price: 750, pgrid: d.pgrid, targets: [{ date: t0.date, tags: ['first'], q: t0.q }] } }];
  const calls = [];
  window.FF_SUPABASE = {
    auth: { getSession: async () => ({ data: { session: { user: { id: 'me' } } } }) },
    from: (t) => {
      calls.push(t);
      return {
        select: () => ({ order: () => ({ limit: async () => ({ data: db.slice().reverse(), error: null }) }) }),
        insert: (row) => ({ select: () => ({ single: async () => { const id = 'n' + db.length; db.push({ id, ...row }); return { data: { id }, error: null }; } }) }),
        delete: () => ({ eq: async (k, v) => { const i = db.findIndex((x) => x.id === v); if (i >= 0) db.splice(i, 1); return { error: null }; } }),
      };
    },
  };
  V.CF_ACCT.state = 'unknown';
  V.cfAccount(); await V.CF_ACCT.ready;
  ok(V.CF_ACCT.state === 'on' && V.cfAll().some((f) => f.id === 'aold' && f.where === 'account'), 'the account\'s freezes are read');
  ok(calls.every((t) => t === 'forecast_freezes'), 'one table');
  const r2 = await V.cfFreezeNow(d, d.assets.SPY);
  ok(r2.where === 'account' && db.length === 2 && db[1].asset === 'SPY' && db[1].payload.targets.length === d.assets.SPY.targets.length, 'a new freeze goes to the account');
  ok(!('at' in db[1].payload) && db[1].frozen_at === d.generated_at, 'its time in its own column');
  state.cfcmp = r2.id;
  const ha2 = V.cfBody(d);
  ok(ha2.includes('Kept in your account') && ha2.includes('Move 1 freeze from this browser to your account'), 'signed in: kept in the account; this browser\'s can move');
  const mv = await V.cfMoveHere();
  ok(mv.moved === 1 && V.cfMine().length === 0 && db.length === 3, 'this browser\'s freeze moved into the account');
  await V.cfDrop('aold');
  ok(!db.some((x) => x.id === 'old') && !V.cfAll().some((f) => f.id === 'aold'), 'deleted from the account');
  // the table not made yet: the freeze stays here, with the reason
  window.FF_SUPABASE.from = () => ({ insert: () => ({ select: () => ({ single: async () => ({ data: null, error: { message: 'relation "public.forecast_freezes" does not exist' } }) }) }) });
  const r3 = await V.cfFreezeNow(d, d.assets.SPY);
  ok(r3.where === 'browser' && /schema\.sql/.test(r3.why), 'no table yet: kept in this browser, and why');
  ok(V.cfTargetLabel({ date: '2026-11-13', tags: ['expiry', 'week'] }, { phase: 'open' }).tags === 'options expiry · week end', 'labels');
  console.log(`closecast view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
