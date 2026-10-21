/* Run with node tests/test_eps_research.cjs. No network or production mocks. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('web/eps-research.js', 'utf8');
const ctx = {window:{}, console, Date, Math, Number, String, Map, Set, Promise, encodeURIComponent};
vm.runInNewContext(source, ctx, {filename: 'eps-research.js'});
const M = ctx.window.FFEPSResearch;
assert.equal(typeof M.mount,'function');
const doc={analysts:{as_of:'2026-10-20',periods:[{period:'0q',end:'2026-09-30',
  eps:{avg:2,yearAgoEps:1.5,numberOfAnalysts:12},
  revisions:{upLast30days:2,downLast30days:1}}],
  surprises:[
    {quarter:'2025-09-30',reported:'2025-10-30',eps_est:1,eps_act:1.2},
    {quarter:'2025-12-31',reported:'2026-01-30',eps_est:1,eps_act:.9},
    {quarter:'2026-03-31',reported:'2026-04-30',eps_est:1,eps_act:1.3},
    {quarter:'2026-06-30',reported:'2026-07-30',eps_est:1,eps_act:1.1}
  ],actions:[{date:'2026-10-20',action:'down'},{date:'2026-10-19',action:'up'}]}};
assert.equal(M.forecast(doc,'2026-10-19'),null,'future analyst snapshot must not leak');
const f=M.forecast(doc,'2026-10-20');
assert.ok(f.median>2,'historical positive surprise bias updates');
assert.equal(f.past_n,4);
assert.equal(f.interval_calibrated,false,'never label uncalibrated intervals as P10/P90');
const test=M.trailingTest(doc,'2026-10-20');
assert.equal(test.tests.length,2);
assert.ok(Number.isFinite(test.mae));
const s=M.metrics(doc,{generated_at:'2026-10-21T00:00:00Z',now:{S:80}},{},'2026-10-20');
assert.equal(s.smart,undefined,'no future Smart Money snapshot');
assert.equal(s.ratings.upgrades,1);
assert.equal(s.ratings.downgrades,1);
const ix={companies:[{ticker:'AAA',cik:1,sector:'technology',sic:'3571'},
 {ticker:'BBB',cik:2,sector:'technology',sic:'3571'},
 {ticker:'CCC',cik:3,sector:'technology',sic:'3674'}],
 chains:[{buyers:['AAA'],layers:[{tickers:['BBB']}]}]};
const peer={analysts:{surprises:[{quarter:'2026-09-30',reported:'2026-10-19',
 eps_est:1,eps_act:1.2}]}};
const result=M.peerSignals('2026-09-30','2026-10-20',ix,'AAA',{BBB:peer});
assert.equal(result.upstream.count,1);
assert.ok(Math.abs(result.upstream.mean_surprise-.2)<1e-10);
assert.equal(result.downstream.count,0);
assert.equal(result.subindustry.count,1);
const early=M.peerSignals('2026-09-30','2026-10-19',ix,'AAA',{BBB:peer});
assert.equal(early.upstream.count,0,'report day is not presumed public at pre-market cutoff');

const contract={...doc,generated_at:'2026-10-20T08:00:00Z',
  markets:[{kind:'beat',source:'polymarket',closed:false,end:'2026-10-28',
    p:.95,history:[['2026-10-19',.64],['2026-10-20',.70],['2026-10-21',.77]],url:'https://polymarket.com/event/test',basis:'gaap'},
    {kind:'kpi',source:'kalshi',closed:false,end:'2027-01-01',
      title:'Demand',outcomes:[{q:'Above 10',p:.65}]}],
  analysts:{...doc.analysts,next_earnings:{date:'2026-10-28'}}};
const mk=M.metrics(contract,null,null,'2026-10-20');
assert.equal(mk.polymarket.p,.70,'latest as-of market.p, not outcomes');
assert.equal(mk.kalshi.length,1);
assert.equal(mk.kalshi[0].outcomes[0].p,.65);
const oldMk=M.metrics(contract,null,null,'2026-10-19');
assert.equal(oldMk.polymarket.p,.64,'future market price must not leak');
assert.equal(M.bias([],4),0);

console.log('EPS company research: 18 assertions passed');
