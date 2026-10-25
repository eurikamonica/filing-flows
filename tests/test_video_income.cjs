/* SEC-sourced holdings + Dividend Snowball inverse income regression, no web. */
'use strict';
const assert = require('node:assert/strict');
const files = {};
globalThis.FFUx = { json: async u => files[u] || null };
const Studio = require('../web/studio.js')._t;
const Holdings = require('../web/holdings-video.js');
const DAY = 864e5, WEEK = 7*DAY;
const date = x => new Date(x).toISOString().slice(0,10);
const t0 = Date.UTC(2023,0,6), n=175;
files['disclosures/data/etf/px/TST.json'] = {
  d0:date(t0), name:'Fixture Dividend Stock',
  t:Array.from({length:n}, (_,i)=>i*7),
  c:Array(n).fill(100), a:Array(n).fill(100),
  div:Array.from({length:12},(_,i)=>[date(t0+(5+i*13)*WEEK),1])
};
const common={ k:'snowball', t:'TST', from:'2023-01-06',to:'2025-12-31',
  amt:'10000', rec:'0', ri:'1',ru:'m', scf:'monthly' };
(async ()=>{
  const base=await Studio.build({...Studio.parseState(''),...common});
  Studio.finish(base,{...Studio.parseState(''),...common});
  const row=base.snowballSummary[0];
  assert.ok(row.monthlyIncome>0, 'base dividends must be positive');
  assert.ok(Math.abs(row.initial_shares-100)<1e-5,'10000/100 initial shares');
  assert.ok(row.final_shares>row.initial_shares, 'DRIP must add shares');
  assert.ok(row.monthly_cashflow_usd && Object.keys(row.monthly_cashflow_usd).length>12);
  const annualGoal=row.annualIncome*1.65;
  const inverse=await Studio.build({...Studio.parseState(''),...common,
    sgoal:String(annualGoal),sunit:'annual',ssolve:'lump'});
  Studio.finish(inverse,{...Studio.parseState(''),...common});
  assert.ok(Math.abs(inverse.series[0].initialCash-16500)<.1,'capital scales linearly through reinvestment');
  assert.ok(Math.abs(inverse.series[0].annualIncome-annualGoal)<.01,'inverse hits terminal annual goal');
  assert.ok(inverse.snowGoal && inverse.snowballSummary[0].investment.includes('Required start'));
  const rec=await Studio.build({...Studio.parseState(''),...common,
    amt:'3000',rec:'0', sgoal:'120',sunit:'monthly',ssolve:'rec'});
  assert.ok(rec.series[0].perBuy>0 && rec.series[0].initialCash===3000,'solve scheduled buys, hold principal fixed');
  assert.ok(Math.abs(rec.series[0].monthlyIncome-120)<.05,'scheduled buys meet terminal monthly target');
  const overshoot=await Studio.build({...Studio.parseState(''),...common,
    rec:'200',sgoal:'1',sunit:'monthly',ssolve:'lump'});
  assert.equal(overshoot.series[0].initialCash,0,'nonnegative solution when fixed buys exceed goal');
  const short=Studio.parseState('k=snowball&t=TST&from=2025-01-01&to=2025-10-01&sgoal=100');
  await assert.rejects(()=>Studio.build(short),/52 weekly observations/,'cannot infer full-year dividends from short interval');
  assert.equal(Studio.parseState(Studio.serialize({...Studio.parseState(''),...common,sgoal:'1000',sunit:'monthly',ssolve:'rec'}).slice(7)).sgoal,'1000');
  const mg={
    name:'Fixture Manager',period:'2026-06-30',filed:'2026-08-14',aum:1000,
    holdings:[['AAA','AAA Inc',.4,400],['BBB','BBB Inc',.2,200]]};
  const p=Holdings.managerPositions(mg,{cos:[['AAA','AAA Inc','technology'],['BBB','BBB Inc','health']]});
  assert.ok(Math.abs(p.covered-.6)<1e-9 && Math.abs(p.unshown-.4)<1e-9,'missing 13F remainder not reweighted');
  const sectors=Holdings.groupSectors(p.positions,p.unshown);
  assert.equal(sectors.find(x=>x.ticker==='unshown').weight,.4);
  const off={recent:[['2026-08-08','AAA','Purchase',1001,15000],['2026-08-09','BBB','Sale',15001,50000],['2026-08-10','AAA','Purchase',50001,null]]};
  const transactions=Holdings.officialTransactions(off,{cos:[['AAA','AAA Inc','technology'],['BBB','BBB Inc','health']]});
  assert.equal(transactions.ignored,1);
  assert.ok(Math.abs(transactions.positions.reduce((a,x)=>a+x.weight,0)-1)<1e-10);
  assert.match(transactions.denom,/NOT a portfolio/);
  console.log('Video income and actual/disclosed holdings: 15 fixture assertions passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
