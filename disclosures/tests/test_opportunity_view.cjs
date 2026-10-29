// opportunity-view.js: one name's odds card renders from a shard row (no DOM, no network).
const assert = require('node:assert/strict');
const V = require('../docs/opportunity-view.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const F = ['p_up', 'p_buy', 'p_short', 'r_p10', 'r_p50', 'r_p90', 'cost', 'edge', 'side', 'strength'];
const flags = (on) => ({ buy: { on, hit: 0.56, all_hit: 0.5, net_median: 0.016, all_net_median: 0.002 }, short: { on: false, hit: 0.57, all_hit: 0.45, net_median: 0.06, all_net_median: -0.02 } });
const d = {
  asof: '2026-10-23', horizons: { '1w': 1, '1m': 4, '3m': 13 }, fields_h: F, labels: { mom13: 'momentum, 13 weeks', hi52: 'distance from the 52-week high' },
  cards: { '1w': { years: [2006, 2026], up: { auc: 0.54, skill: 0.007 }, flags: flags(false) }, '1m': { years: [2006, 2026], up: { auc: 0.55, skill: 0.012 }, flags: flags(true) },
    '3m': { years: [2006, 2026], up: { auc: 0.565, skill: 0.02 }, flags: flags(true) } },
};
const r = { t: 'NVDA', n: 'NVIDIA CORP', s: 'technology', score: 89, side: 'buy', best_h: '1m', drivers: [['hi52', 0.08], ['mom13', -0.02]],
  h: { '1w': [0.55, 0.55, 0.42, -0.054, 0.005, 0.067, 0.001, 0.015, 'none', null], '1m': [0.6, 0.58, 0.42, -0.1, 0.016, 0.14, 0.001, 0.024, 'buy', 0.95],
    '3m': [0.66, 0.65, 0.35, -0.17, 0.055, 0.3, 0.001, 0.043, 'buy', 0.97] } };
const h = V._html('NVDA', d, r, 'stocks', 'disclosures/');
ok(/Buy flag · 1 month/.test(h), 'the flag and its horizon');
ok(/>89</.test(h), 'the score');
ok(/60%/.test(h) && /66%/.test(h), 'the odds of a rise');
ok(/−10\.0% to \+14\.0%/.test(h), 'the likely range');
ok(/pushes up/.test(h) && /pushes down/.test(h), 'the drivers, both ways');
ok(/buy flags on: they made money 56%/.test(h) && /short flags off/.test(h), 'the record, with flags on and off');
ok(/href="disclosures\/#opportunity\/NVDA"/.test(h), 'link to the hub');
const e = V._html('QQQ', d, { ...r, t: 'QQQ', side: 'none', score: null, htb: 1 }, 'etfs', '');
ok(/No clear opportunity/.test(e) && /no horizon where flags have worked/.test(e), 'no flag, no score');
ok(/hard to borrow/.test(e) && /#opportunity\/etfs~QQQ/.test(e), 'ETF: hard to borrow and the ETF link');
ok(V._shard('BRK-B') === 'B' && V._shard('^X') === '_', 'shards by first character');
console.log(`opportunity-view: ${n} checks passed`);
