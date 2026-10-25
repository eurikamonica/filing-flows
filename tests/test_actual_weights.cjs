'use strict';
// Offline regression tests: actual weights cannot be substituted with market cap,
// or silently filled back from the only currently known portfolio.
const assert = require('node:assert/strict');
const A = require('../web/actual-weights.js');

function row(ticker, weight) { return [ticker, weight]; }
const snap = (date, p, sectors = {}) => ({ date, positions:p, sectors, source:'sponsor holdings file' });
const history = {symbol:'DIA', snapshots:[
  snap('2026-09-22', [row('MSFT', .20),row('GS', .10)], {MSFT:'Information Technology',GS:'Financials'}),
  snap('2026-10-23', [row('MSFT', .19),row('GS', .12)], {MSFT:'Information Technology',GS:'Financials'})
]};
const file = {name:'DIA', holdings:{date:'2026-10-23',source:'sponsor holdings file'},
  weights:[row('MSFT', .19),row('GS', .12)]};
const meta = {cos:[['MSFT','Microsoft','technology'],['GS','Goldman Sachs','financials']]};
const fetcher = {hub:'disclosures/data/', rankMeta:async()=>meta, json:async(url)=>url.endsWith('/weights/DIA.json')?history:url.endsWith('/e/DIA.json')?file:null};

assert.deepEqual(A.sortedPositions([['AAPL',.2],['AAPL',.1],['BRK.B',.3],['????',.8],['GS',-1]]),
  [['AAPL',.30000000000000004], ['BRK-B',.3]]);
assert.equal(A.snapshots(history,file).length, 2);
assert.equal(A.snapshots(history,file,'2026-10-01').length,1);
assert.equal(A.snapshots(history,file,'2016-01-01','2016-12-31').length,0);

(async()=>{
  const st = {aw:'index',at:'dji',style:'bars',an:'5',from:'',to:''};
  const out = {notes:new Set(),series:[]};
  await A.build(st,out,fetcher);
  assert.equal(out.kind,'rank');
  assert.equal(out.grid.length,2);
  assert.equal(out.series.find(s=>s.key==='MSFT').v[1],.19);
  assert.equal(out.actual.fund,'DIA');
  assert.match([...out.notes].join(' '), /PRICE-weighted/);
  assert.match(out.sub,/price-weighted index proxy/);
  const sectors = {notes:new Set(),series:[]};
  await A.build({...st,style:'stack'},sectors,fetcher);
  assert.equal(sectors.kind,'sectors');
  assert.equal(sectors.series.find(s=>s.key==='technology').v[1],.19);
  assert.equal(sectors.series.find(s=>s.key==='financials').v[1],.12);
  assert(Math.abs(sectors.series.reduce((sum,s)=>sum+s.v[1],0)-1)<1e-9);
  const only = {notes:new Set(),series:[]};
  await A.build({...st,style:'stack',from:'2026-10-01'},only,fetcher);
  assert.equal(only.kind,'rank'); // no fake evolving sectors from one published date
  assert.equal(only.grid.length,1);
  await assert.rejects(A.build({...st,from:'2017-01-01',to:'2017-12-31'},{notes:new Set(),series:[]},fetcher), /no source-dated/);
  console.log('Actual ETF/index weights offline tests passed');
})().catch(e=>{console.error(e); process.exitCode=1;});
