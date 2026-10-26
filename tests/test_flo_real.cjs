'use strict';
const assert=require('node:assert/strict');
const X=require('../web/flo-real-data.js');
const W=require('../web/flo-real-workbook.js');
const Mascot=require('../web/mascot.js');
let checks=0;
const ok=(v,msg)=>{assert.ok(v,msg);checks++};
const eq=(v,w,msg)=>{assert.equal(v,w,msg);checks++};
const near=(a,b,msg)=>{assert.ok(Math.abs(a-b)<1e-6*Math.max(1,Math.abs(b)),msg+' got '+a);checks++;};

const expected={
 NVDA:{revenue:215938,oi:130387,netIncome:120067,da:2843,capex:6042,ocf:102718,fcf:96676},
 AAPL:{revenue:416161,oi:133050,netIncome:112010,da:11698,capex:12715,ocf:111482,fcf:98767},
 MSFT:{revenue:331839,oi:155237,netIncome:133749,da:null,capex:115948,ocf:182935,fcf:66987}
};
for(const [id,wanted] of Object.entries(expected)){
 const d=X.verifiedCopy(id);
 ok(X.linkOK(d.source)&&d.source.startsWith('https://www.sec.gov/'),id+' source is official SEC');
 for(const key of ['revenue','oi','netIncome','da','capex','ocf'])eq(d[key],wanted[key],id+' '+key);
 eq(X.fcfBridge(d),wanted.fcf,id+' OCF - spending exact');
 const s=W.make(id);
 eq(W.get(s,'B3'),wanted.revenue,id+' workbook historical revenue');
 eq(W.get(s,'B4'),wanted.oi,id+' workbook EBIT proxy');
 const fact=s.cells['B3'];eq(fact.type,'reported',id+' SEC data locked');
 assert.throws(()=>W.set(s,'B3','=1+2'),/read-only/i);checks++;
 const score=W.check(s);
 ok(score.total>=3&&score.correct===0,id+' starts with blank formulas');
 for(const [r,form] of Object.entries(s.answers))W.set(s,r,form);
 eq(W.check(s).correct,Object.keys(s.answers).length,id+' formulas reconcile');
 near(W.get(s,'C4'),wanted.fcf,id+' historical cash flow derived');
 const note=s.cells['C7'];eq(note.type,'input',id+' tax assumption not SEC fact');
 if(id==='MSFT'){
   eq(s.cells['B6'].type,'heading','MSFT D&A must be missing');
   ok(!s.answers.C9,'MSFT no fabricated company FCFF');
 }else{
   near(W.get(s,'C9'),d.oi*(1-.21)+d.da-d.capex,id+' scenario FCFF with ΔNWC=0');
   W.set(s,'C8','5000');
   near(W.get(s,'C9'),d.oi*(1-.21)+d.da-d.capex-5000,id+' what-if ΔNWC');
 }
 ok(W.present(s,'en').includes('SEC primary source')&&!W.present(s,'en').includes('HYPOTHETICAL DATA ONLY'),id+' SEC vs scenario badges');
}
const s=W.make('SUNBEAM');
eq(s.cells.B3.raw,'189','Sunbeam FY1997 reported income original');
eq(s.cells.B4.raw,'93','Sunbeam restatement');
for(const [r,form] of Object.entries(s.answers))W.set(s,r,form);
eq(W.get(s,'C3'),96,'Sunbeam net restatement dollars');
near(W.get(s,'C4'),96/189,'Sunbeam percent');
ok(s.source.includes('sec.gov'),'Sunbeam SEC primary order');
const d=W.make('DELL');
for(const [r,formula] of Object.entries(d.answers))W.set(d,r,formula);
near(W.get(d,'C3'),66,'Dell FY2003 to FY2007 Q1 +66pp');
near(W.get(d,'C4'),38,'Dell FY2006 to Q1 FY2007 +38pp');
eq(d.cells.B5.raw,'0.76','Dell 76% is ratio, not amount');
assert.throws(()=>W.set(d,'B5','200000'),/read-only/);checks++;
ok(W.route('real NVDA excel modeling lab'),'route specific real SEC case');
ok(W.route('Sunbeam SEC case spreadsheet'),'route enforcement case');
ok(!W.route('open Excel modeling lab'),'generic worksheet stays original');
eq(W.chosen('real AAPL Excel',null),'AAPL','Apple routing');
eq(W.chosen('real Excel', {ticker:'MSFT'}),'MSFT','company context routing');
eq(W.chosen('real Excel',null),'NVDA','safe default');
const annual={
 profile:{name:'NVIDIA Corporation',tickers:['NVDA']},
 years:[{label:'FY2026',end:'2026-01-25',form:'10-K',doc_url:X.snapshots.NVDA.source,
  headline:{revenue:215938e6,oi:130387e6,ocf:102718e6},
  nodes:[{id:'rev',name:'Revenue',v:215938e6},{id:'oi',name:'Operating income',v:130387e6},
   {id:'ocf',name:'Operating cash flow',v:102718e6},
   {id:'da',name:'Depreciation and amortization',v:2843e6},
   {id:'capex',name:'Capital expenditures',v:6042e6}]}]};
const parsed=X.fromPublished(annual,1045810);
ok(!!parsed,'annual 10-K annual nodes imported only from known SEC source');
eq(parsed.revenue,215938,'published annual values converted dollars to USD M');
eq(parsed.capex,6042,'published annual capex');
const bad=JSON.parse(JSON.stringify(annual));bad.years[0].form='10-Q';
eq(X.fromPublished(bad,1045810),null,'no annual-quart mix');
const bad2=JSON.parse(JSON.stringify(annual));bad2.years[0].doc_url='https://example.com';
eq(X.fromPublished(bad2,1045810),null,'no arbitrary citation domain');
const bad3=JSON.parse(JSON.stringify(annual));bad3.currency='EUR';
eq(X.fromPublished(bad3,1045810),null,'no mixed currency');
const bad4=JSON.parse(JSON.stringify(annual));bad4.years[0].nodes[3].name='Depreciation';
eq(X.fromPublished(bad4,1045810).da,null,'no inferred amortization');
(async()=>{
 const ix={companies:[{cik:1045810,ticker:'NVDA',name:'NVIDIA Corporation'}]};
 const reply=await Mascot.ask('real NVDA Excel modeling lab',ix);
 ok(reply.realWorkbook&&reply.html.includes('flo-real'),'same Flo routes to SEC worksheet');
 const reply2=await Mascot.ask('Sunbeam SEC case spreadsheet',ix);
 ok(reply2.realWorkbook&&reply2.html.includes('data-real-case="SUNBEAM"'),'same Flo routes to SEC enforcement');
 console.log(checks+' Flo real-data case workbook checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
