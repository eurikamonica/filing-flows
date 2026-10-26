'use strict';
const assert=require('node:assert/strict'), A=require('../web/actual-weights.js');
const out=()=>({notes:new Set(),series:[]});
const h={snapshots:[{date:'2026-06-30',positions:[['AAPL',.2],['MSFT',.3]]},{date:'2026-09-30',positions:[['AAPL',.1],['NVDA',.4]]}]};
const api={hub:'/',rankMeta:async()=>({cos:[['AAPL','Apple','technology']]}),json:async u=>u.includes('/weights/')?h:null};
(async()=>{
 const area=out();await A.build({aw:'etf',style:'companies'},area,api);
 assert.equal(area.kind,'sectors');assert.equal(area.group,'companies');
 for(let i=0;i<2;i++)assert(Math.abs(area.series.reduce((v,s)=>v+s.v[i],0)-1)<1e-9);
 assert.deepEqual(area.series.find(s=>s.key==='MSFT').v,[.3,0]);
 const changes=out();await A.build({aw:'etf',style:'changes'},changes,api);
 assert.equal(changes.grid.length,1);assert.equal(changes.order,'abs');
 assert.equal(changes.series.find(s=>s.key==='MSFT').v[0],-.3);
 assert.equal(changes.fmt(-.3),'-30.00 pp');
 const mapi={...api,json:async u=>u.endsWith('/1067983.json')?{name:'Manager',snapshots:[{period:'2026-06-30',filed:'2026-08-14',complete:true,total_usd:100,positions_shard:'positions.json'}]}:[{ticker:'AAPL',value_usd:20,put_call:'NONE'},{ticker:'AAPL',value_usd:50,put_call:'CALL'},{value_usd:30}]};
 const mgr=out();await A.build({aw:'13f',style:'stack'},mgr,mapi);
 assert.equal(mgr.series.find(s=>s.key==='other').v[0],.8);
 assert.equal(mgr.evidence[0].filed,'2026-08-14');
 assert.match(mgr.metric,/13F/);assert(!mgr.sub.includes('fund NAV'));
 const offapi={...api,json:async()=>({trades:[{person:'Official',date:'2026-06-12',ticker:'AAPL',amount_min:1001,amount_max:15000,type:'buy'},{person:'Official',date:'2026-06-13',ticker:'MSFT',amount_min:1001,amount_max:50000,type:'sell'}]})};
 const off=out();await A.build({aw:'official',ap:'Official',style:'companies'},off,offapi);
 assert.equal(off.series.find(s=>s.key==='AAPL').v[0],.5);
 assert.match(off.foot,/not actual holdings/);assert.equal(off.kind,'rank');
 const onlyBuy=await A.disclosedSource({aw:'official',ap:'Official',ao:'buy'},offapi);
 assert.deepEqual(onlyBuy.snapshots[0].positions,[['AAPL',1]]);

 const single=out();
 await A.build({aw:'etf',style:'changes',from:'2026-09-01'},single,api);
 assert.equal(single.kind,'rank','one disclosed date becomes a dated ranking card');
 assert.equal(single.grid.length,1,'single source date never interpolated');
 assert.equal(single.actual.fallback,'single-disclosure','explicit fallback metadata for UI');
 assert.equal(single.fmt(.1),'10.00%','no false percentage-point change');
 assert.match(single.title,/single dated company weight snapshot \(no changes\)/);
 assert.match(single.foot,/not a weight-change history/);
 assert.ok([...single.notes].some(x=>/No previous holdings were inferred/.test(x)));
 assert.equal(single.series.find(x=>x.key==='AAPL').v[0],.1,'uses real latest weight');
 const onlyCurrent={...api,json:async u=>u.includes('/weights/')?null:u.includes('/etf/e/')?
  {holdings:{date:'2026-10-25',date_basis:'observed',source:'sponsor holdings file'},
   weights:[['NVDA',.078],['AAPL',.077]]}:null};
 const sponsor=out();
 await A.build({aw:'etf',ah:'SPY',style:'changes'},sponsor,onlyCurrent);
 assert.equal(sponsor.actual.reports,1,'SPY detail-only published file works without new history feed');
 assert.equal(sponsor.actual.fallback,'single-disclosure');
 assert.equal(sponsor.series.find(x=>x.key==='NVDA').v[0],.078,'uses issuer sponsor disclosure');
 assert.ok([...sponsor.notes].some(x=>/retrieval OBSERVATIONS/.test(x)));
 const s13=out();
 await A.build({aw:'13f',style:'changes'},s13,mapi);
 assert.equal(s13.actual.fallback,'single-disclosure','one 13F quarter never implies a trade');
 assert.match(s13.foot,/NOT AUM/);
 await assert.rejects(A.build({aw:'etf',ah:'MISSING',style:'changes'},out(),
   {...api,json:async()=>null}),/no source-dated/);

 console.log('Disclosed weight views: company residuals, exits, changes, 13F options, official bounds passed');
})().catch(e=>{console.error(e);process.exitCode=1});
