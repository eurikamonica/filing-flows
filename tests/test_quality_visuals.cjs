const {test}=require('node:test'),assert=require('node:assert/strict');
require('../web/quality-visuals.js');const V=globalThis.FFQualityVisuals;
test('all indexed series use a common strictly positive base; missing values stay null',()=>{
 const rows=[{end:'2023-12-31',wc:{rev:100,ar_c:null}},{end:'2024-12-31',wc:{rev:200,ar_c:20}},{end:'2025-12-31',wc:{rev:300,ar_c:0}},{end:'2026-12-31',wc:{rev:400,ar_c:null}}];
 const x=V.indexed(rows,[['rev','Revenue'],['ar_c','AR']]);assert.equal(x.base,'2024-12-31');assert.deepEqual(x.series[0].values,[100,150,200]);assert.deepEqual(x.series[1].values,[100,0,null]);
 assert.equal(V.indexed(rows,[['inv_c','Inventory']]).base,null);
});
test('period bases remain separated and sorted',()=>{
 const c={quality:{q:[{end:'2025-06-30'},{end:'2025-03-31'}],fy:[{end:'2024-12-31'}]}};
 assert.deepEqual(V.periods(c,'q').map(x=>x.end),['2025-03-31','2025-06-30']);assert.equal(V.periods(c,'fy').length,1);
});
test('missing observations and missing quarters break lines instead of interpolating',()=>{
 const rows=['2024-03-31','2024-06-30','2024-09-30','2025-06-30'].map(end=>({end,_mode:'q'}));
 const html=V.chart(rows,[{label:'AR',color:'#123456',values:[10,null,20,30]}],'AR');
 const d=html.match(/<path d="([^"]*)"/)[1];assert.equal((d.match(/M/g)||[]).length,3);assert.equal((d.match(/L/g)||[]).length,0);assert.doesNotMatch(html,/NaN|Infinity/);
});
test('negative measures remain negative; no observations show unavailable',()=>{
 const rows=[{end:'2024-12-31'},{end:'2025-12-31'}];
 const s=[{label:'FCF margin',color:'#123456',values:[-141.3,0]}];assert.match(V.chart(rows,s,'FCF','%'),/-141.3%/);assert.match(V.chart(rows,[{...s[0],values:[null,null]}],'FCF'),/Missing values are not zero/);
});
test('evidence escapes input, validates accession and keeps fact-specific balance date',()=>{
 const c={profile:{cik:320193},quality:{unit:'USD',src:{concepts:[['AccountsReceivableNetCurrent']],filings:[['0000320193-25-000001','10-K','2025-10-01']]}}};
 const p={end:'2025-09-27',wc:{ar_c:0},ev:{ar_c:[0,'bal',[0],'2025-09-27']},health:{inputs:{'<script>':1}}};
 const h=V.evidence(c,p);assert.match(h,/&lt;script&gt;/);assert.match(h,/Balance 2025-09-27/);assert.match(h,/https:\/\/www.sec.gov\/Archives/);assert.doesNotMatch(h,/<script>/);
});
test('chart table exposes missing data and chart values',()=>{
 const h=V.table([{end:'2025-01-01'}],[{label:'<AR>',values:[null]}]);assert.match(h,/Not available/);assert.match(h,/&lt;AR&gt;/);
});
test('both company routes mount trends and keep research in a separate container',()=>{
 const fs=require('fs'),app=fs.readFileSync('web/app.js','utf8'),index=fs.readFileSync('web/index.html','utf8');
 assert.match(app,/id === 'quality' && window.FFQualityVisuals/);assert.equal((app.match(/FFQualityVisuals.mount\(body, c\)/g)||[]).length,2);assert.match(app,/\.render\(target,/);assert.match(index,/src="quality-visuals.js"/);assert.match(index,/href="quality-visuals.css"/);
});
