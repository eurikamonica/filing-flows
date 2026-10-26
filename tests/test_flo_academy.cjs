// Flo Academy: company-aware SEC evidence + safe deterministic finance education.
'use strict';
const assert = require('node:assert/strict');
const A = require('../web/flo-academy.js');
const M = require('../web/mascot.js');
let count = 0;
const ok = (a, b) => { assert.ok(a,b); count++; };
const ix = {companies:[{cik:1045810,ticker:'NVDA',name:'NVIDIA Corporation'}, {cik:320193,ticker:'AAPL',name:'Apple Inc.'}]};
const company = {
  quarters:[{end:'2026-07-31',label:'FY2027 Q2',form:'10-Q',filed:'2026-09-01',
    headline:{oi:12e9,ocf:14e9},doc_url:'https://www.sec.gov/Archives/edgar/data/1045810/example'}],
  quality:{reserves:[
    {id:'warranty',name:'Product warranty reserve',end:'2025-01-31',
     opening:50e6,closing:30e6,releases:20e6,reconciled:true},
    {id:'loans',name:'Credit losses reserve',end:'2025-01-31',
     opening:10e6,closing:9e6,releases:0,reconciled:false}
  ]}
};
const load = async c => c.ticker==='NVDA' ? company : null;
ok(A.match('teach NVDA DCF step by step')==='lesson','stepwise learning routed');
ok(A.match('supplier rebate exercise')==='rebate','rebate routed');
ok(A.match('NVDA cookie jar')==='detective','reserve detective routed');
ok(A.match('cookie jar simulation')==='reserve_demo','reserve simulation routed');
ok(A.match('Sunbeam case study')==='case','case study routed');
ok(A.match('next step')===null,'no lesson step outside active session');
ok(A.fcff({ebit:100,tax:20,da:8,capex:12,nwc:5})===71,'FCFF arithmetic');
assert.throws(()=>A.fcff({ebit:100,tax:120,da:8,capex:12,nwc:5}),/Tax/); count++;
const r=A.rebate({purchased:1000,sold:400,rebate:10});
ok(r.total===10000&&r.cogs===4000&&r.inventory===6000,'COGS vs inventory split');
assert.throws(()=>A.rebate({purchased:10,sold:11,rebate:5}),/Require whole units/);count++;
const prov=A.reserveScenario({balance:50,profit:100,bank:100,amount:20,action:'add'});
const release=A.reserveScenario({balance:50,profit:100,bank:100,amount:20,action:'release'});
const usage=A.reserveScenario({balance:50,profit:100,bank:100,amount:20,action:'use'});
ok(prov.profit===80&&prov.reserve===70&&prov.cash===100,'provision expense no cash');
ok(release.profit===120&&release.reserve===30&&release.cash===100,'release no cash');
ok(usage.profit===100&&usage.reserve===30&&usage.cash===80,'settlement uses cash');
assert.throws(()=>A.reserveScenario({balance:10,profit:100,bank:100,amount:20,action:'release'}),/Invalid/);count++;
(async()=>{
  const lesson=await A.handle('teach NVDA DCF step by step',ix.companies[0],'zh',load);
  ok(lesson.html.includes('1/7')&&lesson.html.includes('12,000,000,000')&&lesson.links.some(x=>x[0].includes('sec.gov')),'sourced FY data and SEC URL');
  const step=await A.handle('下一步',null,'zh',load);
  ok(step.html.includes('2/7')&&step.html.includes('FCFF')&&step.html.includes('14,000,000,000'),'step 2 retains filer and tutorial');
  ok(step.html.includes('data-flo-calc="fcff"'),'guided computation form');
  const back=await A.handle('上一步',null,'zh',load);
  ok(back.html.includes('1/7'),'previous step works');
  const done=await A.handle('结束课程',null,'zh',load);
  ok(/已结束/.test(done.html)&&A.match('下一步')===null,'lesson ends');
  const detective=await A.handle('NVDA cookie jar',ix.companies[0],'zh',load);
  ok(detective.html.includes('Product warranty reserve')&&detective.html.includes('40.00%'),'real tagged reserves, not invented');
  ok(/不是舞弊识别器/.test(detective.html)&&deterc(detective.links),'flags are not fraud claims');
  const unknown=await A.handle('AAPL cookie jar',ix.companies[1],'en',load);
  ok(/Insufficient sourced reserve/.test(unknown.html),'missing disclosure is not zero');
  const demo=await A.handle('cookie jar simulation',null,'zh',load);
  ok(demo.html.includes('data-flo-calc="reserve"'),'reserve simulation interactive');
  const cases=await A.handle('Sunbeam case study',null,'en',load);
  ok(cases.links.every(x=>x[0].startsWith('https://www.sec.gov/'))&&cases.html.includes('1996'),'SEC-only historical primary evidence');
  const link=A.explain(ix.companies[0],'en',{label:'<img src=x>',docUrl:'https://evil.example/steal',amount:30});
  ok(!link.html.includes('<img src=x>')&&!link.links.some(x=>x[0].includes('evil.example')),'HTML escaping and safe SEC URL');
  const inM=await M.ask('teach NVDA DCF step by step',ix);
  ok(inM.html.includes('1/7')&&inM.company.ticker==='NVDA','mascot academic routing');
  const follow=await M.ask('下一步',ix);
  ok(follow.html.includes('2/7'),'mascot session continuation without company');
  const old=await M.ask('NVDA valuation',ix);
  ok(!old.html.includes('Flo Academy'),'ordinary valuation route unaffected');
  console.log(count+' Flo Academy tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
function deterc(links){return links.some(x=>x[0].includes('#c-1045810-cash'));}
