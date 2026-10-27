const test=require('node:test'),assert=require('node:assert/strict'),S=require('../web/shock-panel.js');
const day=86400000;
function sample(n=80){return Array.from({length:n},(_,i)=>{const rates=Math.sin(i*1.71),fx=Math.cos(i*.97),jobs=Math.sin(i*.31),peers=Math.cos(i*.53);return {t:Date.UTC(2000,0,1)+i*91*day,rates,fx,jobs,peers,y:3+2*rates-4*fx+jobs*.3+peers*.8+Math.sin(i*2.23)*.05};});}
test('joint OLS recovers known coefficients and separate chronological holdout',()=>{const m=S.fit(sample(),['rates','fx','jobs','peers']);assert(!m.error);assert(Math.abs(m.beta.rates-2)<.02);assert(Math.abs(m.beta.fx+4)<.02);assert(m.holdout.n===20);assert(m.holdout.rmse<m.holdout.naive);assert(m.r2>.99);assert(m.se.rates>0);});
test('100 bp is one pp; contribution sums and covariance uncertainty',()=>{const m=S.fit(sample(),['rates','fx','jobs','peers']),r=S.impact(m,{rates:100,fx:2,jobs:1,peers:-1});assert(Math.abs(r.contributions.rates-m.beta.rates)<1e-10);assert(Math.abs(r.delta-Object.values(r.contributions).reduce((a,b)=>a+b,0))<1e-10);assert(r.band>0);const z=S.impact(m,{rates:0,fx:0,jobs:0,peers:0});assert.equal(z.delta,0);assert.equal(z.band,0);});
test('missing values, insufficient sample and collinearity do not manufacture coefficients',()=>{assert(S.fit(sample(10),['rates']).error);const m=S.fit(sample().map(x=>({...x,fx:x.rates})),['rates','fx']);assert(m.error);assert(S.fit(sample().map(x=>({...x,jobs:null})),['jobs']).error);assert(S.impact({beta:{rates:2}},{rates:0,fx:2,jobs:0,peers:0}).error);assert(S.impact({error:'No history'},{rates:0,fx:0,jobs:0,peers:0}).error);assert(S.impact({beta:{}},{rates:NaN,fx:0,jobs:0,peers:0}).error);});
test('quarter metrics permit losses, require positive revenue and year-ago match',()=>{const rows=[{end:'2024-03-30',t:Date.parse('2024-03-30'),values:{revenue:100,oi:-10}},{end:'2025-03-29',t:Date.parse('2025-03-29'),values:{revenue:110,oi:-5,ocf:30,capex:5}}];const q=S.metrics(rows)[1];assert(Math.abs(q.revenue-10)<1e-9);assert(q.om<0);assert.equal(S.projections(q,'revenue',5)[1][1],115);assert.equal(S.projections(q,'revenue',-200)[1][1],null);assert.equal(q.fcfm,100*25/110);});
test('latest financial versions and Q4 derivation; missing quarter prevents subtraction',()=>{const c={quality:{hist:{periods:[['2024-01-01','2024-03-31','q'],['2024-04-01','2024-06-30','q'],['2024-07-01','2024-09-30','q'],['2024-01-01','2024-12-31','fy']],v:{revenue:[[0,[[10],[11]]],[1,[[20]]],[2,[[30]]],[3,[[100]]]]}}}};const r=S.financials(c);assert.equal(r[0].values.revenue,11);assert.equal(r[3].values.revenue,39);c.quality.hist.v.revenue.splice(1,1);assert(!S.financials(c).some(x=>x.end==='2024-12-31'));});
test('macro and price endpoints never fill from future or stale values',()=>{const rows=[{t:Date.parse('2025-01-03'),v:100},{t:Date.parse('2025-04-04'),v:105}];assert.equal(S.change(rows,Date.parse('2025-04-04'),true),5.000000000000004);assert.equal(S.change(rows,Date.parse('2025-04-03'),true),null);assert.equal(S.change(rows,Date.parse('2025-05-04'),true),null);});
test('stock sample uses non-overlapping quarter returns, controls aligned to same dates',()=>{const start='2005-01-07',n=1100,p={start,c:Array.from({length:n},(_,i)=>100+i)},macro={weekly:{start,data:{y10:Array.from({length:n},(_,i)=>3+Math.sin(i)),usd:Array.from({length:n},(_,i)=>90+i/100),unrate:Array.from({length:n},(_,i)=>5+Math.cos(i))}}};const d=S.dataset({},macro,[],p,p);assert(d.rows.stock.length>40&&d.rows.stock.length<100);assert(d.rows.stock.every(x=>Math.abs(x.y-x.market)<1e-10));assert(d.rows.stock.every((x,i)=>!i||x.t-d.rows.stock[i-1].t>80*day));assert(d.rows.stock.every(x=>x.peers===null));});
test('CSV quotes data and escapes formula markers',()=>{assert.equal(S.csv([['a"b','=SUM(A1)','x,y']]),'"a""b","\'=SUM(A1)","x,y"');});

test('price-return channel requires separate split-adjusted prices; never substitutes total return',()=>{const start='2005-01-07',n=1100,p={start,c:Array.from({length:n},(_,i)=>100+i),p:Array.from({length:n},(_,i)=>100+i/2)},macro={weekly:{start,data:{y10:Array.from({length:n},(_,i)=>3+Math.sin(i))}}};let d=S.dataset({},macro,[],p,p);assert(d.rows.stockPrice.length>40);assert.notEqual(d.rows.stock[0].y,d.rows.stockPrice[0].y);delete p.p;d=S.dataset({},macro,[],p,p);assert.equal(d.rows.stockPrice.length,0);assert(d.rows.stock.length>40);});

test('expanded registry: sixteen factors, twenty outputs, proper units and missing inputs',()=>{
 assert.equal(S.FACTORS.length,16);assert.equal(Object.keys(S.TARGETS).length,20);
 assert.equal(S.unit('ccc'),'days');assert.equal(S.unit('currentratio'),'×');
 assert(S.impact({beta:{rates:1}},{rates:null}).error);
 const r=S.impact({beta:{credit:2,market:.5}},{credit:100,market:-10});assert.equal(r.delta,-3);
});
test('Ridge handles collinear factors, shrinks standardized slopes, with no fabricated interval',()=>{
 const rows=sample().map(x=>({...x,duplicate:x.rates})),m=S.fit(rows,['rates','duplicate','fx'],{model:'ridge',alpha:10});
 assert(!m.error);assert(Math.abs(m.beta.rates-m.beta.duplicate)<1e-9);assert.equal(m.covariance,undefined);
 const a=S.fit(sample(),['rates','fx'],{model:'ridge',alpha:1}),b=S.fit(sample(),['rates','fx'],{model:'ridge',alpha:1000});assert(Math.abs(b.beta.rates)<Math.abs(a.beta.rates));
 assert.equal(S.impact(m,{rates:100}).band,null);assert(S.fit(rows,['rates'],{model:'ridge',alpha:-1}).error);
});
test('Huber reduces sensitivity to isolated response outliers and reports convergence',()=>{
 const rows=sample(120);rows[20].y+=150;rows[50].y-=200;
 const a=S.fit(rows,['rates','fx','jobs','peers']),b=S.fit(rows,['rates','fx','jobs','peers'],{model:'huber'});
 assert(!b.error,b.error);assert(Math.abs(b.beta.rates-2)<Math.abs(a.beta.rates-2));assert(Math.abs(b.beta.fx+4)<.1);assert(b.downweighted>0);assert.equal(b.covariance,undefined);
});
test('ARX uses consecutive past outcomes, one-period shock persistence, blocks unstable paths',()=>{
 const rows=sample(120);let prev=0;for(const r of rows){r.y=.65*prev+2*r.rates+.1*Math.cos(r.t);prev=r.y;}
 const m=S.fit(rows,['rates'],{model:'arx'});assert(!m.error,m.error);assert(Math.abs(m.persistence-.65)<.03);
 const p=S.responsePath(m,2);assert.equal(p.points[0],2);assert(Math.abs(p.points[1]-2*m.persistence)<1e-10);
 assert(S.responsePath({persistence:1.1},2).error);assert.equal(S.lagged([{t:0,y:1},{t:300*day,y:2}])[1].ownLag,null);
});
test('model comparisons use identical eligible train/test dates and counts',()=>{
 const rows=sample(120),c=S.compareModels(rows,['rates','fx']);assert.equal(c.length,4);assert(c.every(m=>!m.error),JSON.stringify(c));assert.equal(new Set(c.map(x=>x.first)).size,1);assert.equal(new Set(c.map(x=>x.test_n)).size,1);assert.equal(new Set(c.map(x=>x.n)).size,1);
 const cut=Math.floor((rows.length-1)*.75),before=S.fit(rows.slice(1,cut+1),['rates'],{model:'ridge'});
 rows.at(-1).y+=10000;const after=S.fit(rows.slice(1,cut+1),['rates'],{model:'ridge'});assert.deepEqual(before.beta,after.beta);
});
test('expanded financial outcomes preserve losses and use prior revenue instead of dividing by negative earnings',()=>{
 const rows=[{end:'2024-03-31',t:Date.parse('2024-03-31'),values:{revenue:100,oi:-20}},{end:'2025-03-31',t:Date.parse('2025-03-31'),values:{revenue:120,oi:-10,gp:60,rd:12,capex:6,sbc:3,ni:-5,ocf:10,assets_open:90,assets_close:110,current_assets:40,current_liabilities:20,dso:30,ccc:-12}}];
 const q=S.metrics(rows)[1];assert.equal(q.oiChange,10);assert.equal(q.gm,50);assert.equal(q.rdm,10);assert.equal(q.capexm,5);assert.equal(q.accrual,-15);assert.equal(q.currentratio,2);assert.equal(S.projections(q,'ccc',5)[1][1],-7);assert.equal(S.projections(q,'currentratio',.2)[1][2],'×');
});
test('additional macro transforms keep bp, percent, levels and point changes distinct',()=>{
 const n=30,a=Array.from({length:n},(_,i)=>i),macro={weekly:{start:'2020-01-03',data:{y2:a,real10:a,curve2:a,credit:a,cpi:a,vix:a,oil:a.map(x=>100+x),payrolls:a,retail:a,ip:a}}};const d=S.dataset({},macro,[],{},{}),r=d.factors.at(-1);assert.equal(r.rates2,13);assert.equal(r.inflation,13);assert.equal(r.vix,13);assert.equal(r.payrolls,29);assert(Math.abs(r.oil-100*(129/116-1))<1e-9);assert.equal(r.fx,null);
});
test('valuation bridges compound EPS and multiple, enforce perpetuity denominator and missing data',()=>{
 const v={eps:5,pe:20,epsPct:10,pePct:-10,fcf:100,wacc:10,g:2,waccBP:100,gBP:0,fcfPct:0},r=S.valuation(v);assert.equal(r.pe.base,100);assert.equal(r.pe.scenario,99);assert.equal(r.dcf.base,1250);assert(Math.abs(r.dcf.scenario-100/.09)<1e-10);assert(S.valuation({...v,waccBP:-900}).dcf.error);assert(S.valuation({...v,eps:-1}).pe.error);assert(S.valuation({...v,eps:null}).pe.error);
});

test('supplemental history fills gaps without replacing current values or mixing identities/currencies',()=>{
 const c={profile:{cik:1},quarters:[{end:'2025-03-31',headline:{revenue:100}}],shock_history:{v:1,cik:1,unit:'USD',rows:[{end:'2010-03-31',values:{revenue:50,ocf:10}},{end:'2025-03-31',values:{revenue:999,capex:3}}]}};
 let r=S.financials(c);assert.equal(r.length,2);assert.equal(r[1].values.revenue,100);assert.equal(r[1].values.capex,3);
 c.shock_history.cik=2;assert.equal(S.financials(c).length,1);c.shock_history.cik=1;c.currency='EUR';assert.equal(S.financials(c).length,1);
});
test('coverage defaults remove short peers, preserve minimum sample and avoid outcome-based tuning',()=>{
 const rs=sample(40).map((r,i)=>({...r,peers:i<20?null:r.peers}));
 const d=S.defaults(rs);assert(!d.error);assert.deepEqual(d.keys,['rates','fx','jobs']);assert.equal(d.n,40);
 assert.deepEqual(S.defaults(rs.map(r=>({...r,y:r.y*500+600}))).keys,d.keys);
 assert(S.defaults(sample(20)).error);const cv=S.coverage(rs,['rates','fx','jobs','peers']);assert.equal(cv.n,20);assert.equal(cv.need,25);assert.equal(cv.missing,5);
});
test('recommendation excludes final test from model and penalty selection',()=>{
 const rs=sample(80),a=S.recommend(rs,['rates','fx','jobs']);assert(a.chosen);assert(a.qualified);
 const b=S.recommend(rs.map(r=>({...r,y:r.t>=Date.parse(a.test.first)?r.y+100000:r.y})),['rates','fx','jobs']);
 assert.deepEqual(a.chosen,b.chosen);assert.deepEqual(a.ranking,b.ranking);assert(b.test.rmse>a.test.rmse*100);assert(a.validation.last<a.test.first);assert.equal(a.validation.n,8);assert.equal(a.test.n,16);
 assert(S.recommend(sample(30),['rates','fx','jobs']).error);
});
test('coverage and observed trends survive macro outage without manufacturing inputs',()=>{
 const c={quarters:[{end:'2024-03-31',headline:{revenue:100,oi:20}},{end:'2025-03-31',headline:{revenue:110,oi:22}}]};
 const d=S.dataset(c,null,[],null,null);assert.equal(d.rows.revenue.length,1);assert.equal(d.rows.om.length,2);assert.equal(d.rows.om[0].rates,undefined);assert.equal(S.coverage(d.rows.om,['rates']).n,0);assert.match(S.timePlot(d.rows.om),/Actual quarterly history/);
});
