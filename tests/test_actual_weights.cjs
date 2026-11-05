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
  // an index before its tracking fund's first report: reconstructed (studio.js reconstructIndex), marked, and only for a
  // start chosen before that report; a fund's own disclosures are never reconstructed
  const tech = {MSFT:'Information Technology',AAPL:'Information Technology'};
  const qhist = {symbol:'QQQ', snapshots:[snap('2019-09-30',[row('MSFT',.12),row('AAPL',.11)],tech), snap('2019-12-31',[row('MSFT',.12),row('AAPL',.12)],tech)]};
  const calls = [];
  const rapi = {hub:'disclosures/data/', rankMeta:async()=>({cos:[['MSFT','Microsoft','technology'],['AAPL','Apple','technology'],['CSCO','Cisco','technology']]}),
    json:async(url)=>url.endsWith('/weights/QQQ.json')?qhist:null,
    reconstruct:async(idx,from,to)=>{calls.push([idx,from,to]); return {how:'ndx', history:false, since:'2026-10-25', size:100, thin:null, snaps:[
      {date:'1999-12-31', positions:[['MSFT',.4],['CSCO',.35],['INTC',.25]], sector_weights:{technology:1}, on_file:3, members:99},
      {date:'2019-06-30', positions:[['MSFT',.5],['AAPL',.5]], sector_weights:{technology:1}, on_file:2, members:99},
      {date:'2019-09-30', positions:[['MSFT',1]], sector_weights:{technology:1}, on_file:1, members:99}]};}};
  const rs = {notes:new Set(),series:[]};
  await A.build({aw:'index',at:'ndx',style:'stack',an:'5',from:'1999-12-31',to:''}, rs, rapi);
  assert.deepEqual(calls[0], ['ndx','1999-12-31','2019-09-30']);
  assert.deepEqual(rs.grid, ['1999-12-31','2019-06-30','2019-09-30','2019-12-31'].map(d=>Date.parse(d+'T00:00:00Z')));   // a report's own date is never a reconstruction
  assert.equal(rs.kind,'sectors');
  assert.equal(rs.actual.reconTo, Date.parse('2019-09-30T00:00:00Z'));
  assert.equal(rs.actual.recon, 2); assert.equal(rs.actual.reports, 2);
  assert.equal(rs.series.find(s=>s.key==='technology').v[0], 1);
  assert(Math.abs(rs.series.find(s=>s.key==='technology').v[2]-.23)<1e-9);
  const rnotes = [...rs.notes].join(' ');
  assert.match(rnotes, /1999-12-31 to 2019-06-30: RECONSTRUCTED, not the fund's holdings/);
  assert.match(rnotes, /today's members are used/);
  assert.match(rnotes, /Reported source dates: 2019-09-30 to 2019-12-31/);
  assert.doesNotMatch(rnotes, /No synthetic history/);
  assert.match(rs.sub, /reconstructed to 2019-06-30, then QQQ's reports/);
  assert.match(rs.foot, /^Before 2019-09-30: reconstructed/);
  const rc = {notes:new Set(),series:[]};
  await A.build({aw:'index',at:'ndx',style:'companies',an:'5',from:'1999-12-31',to:''}, rc, rapi);
  assert(rc.series.some(s=>s.key==='CSCO') && rc.series.find(s=>s.key==='CSCO').v[0]===.35 && rc.series.find(s=>s.key==='CSCO').v[3]===0);
  const rb = {notes:new Set(),series:[]};
  await A.build({aw:'index',at:'ndx',style:'bars',an:'5',from:'2019-01-01',to:''}, rb, rapi);
  assert.equal(rb.kind,'rank'); assert.equal(rb.grid.length,3); assert.equal(rb.actual.recon,1);
  const plain = {notes:new Set(),series:[]};
  await A.build({aw:'index',at:'ndx',style:'stack',an:'5',from:'',to:''}, plain, rapi);
  assert.equal(plain.grid.length,2); assert.equal(plain.actual.recon,undefined); assert.match([...plain.notes].join(' '), /No synthetic history/);
  const etf = {notes:new Set(),series:[]};
  await A.build({aw:'etf',ah:'QQQ',style:'stack',an:'5',from:'1999-12-31',to:''}, etf, rapi);
  assert.equal(etf.grid.length,2); assert.equal(etf.actual.recon,undefined);
  const off = {notes:new Set(),series:[]};
  await A.build({aw:'index',at:'ndx',style:'stack',an:'5',from:'1999-12-31',to:'',recon:'0'}, off, rapi);
  assert.equal(off.grid.length,2);
  assert.equal(calls.length,3);   // the reconstruction is asked only for an index with an earlier start
  console.log('Actual ETF/index weights offline tests passed');
})().catch(e=>{console.error(e); process.exitCode=1;});
