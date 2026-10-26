const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const code = fs.readFileSync('web/company-disclosures.js','utf8');
function setup(fetch) {
  const window = {};
  vm.runInNewContext(code,{window,fetch,URL,AbortController,setTimeout,clearTimeout,Intl});
  const button = {};
  const el = {isConnected:true,innerHTML:'',classList:{add(){}},querySelector:()=>button};
  return {el,button,mount:window.FFCompanyDisclosures.mount};
}
const doc = {cik:'123',snapshot:{balance_date:'2025-12-31',latest_period:'2026-03-31'},analysis:{total_debt:0,leverage:null},hidden_leverage:{as_of:'2025-12-31',categories:[{label:'Purchase commitments <script>',amount_usd:100,source_url:'javascript:alert(1)',class:'operating_commitment',evidence:[]}]},revenue_quality:{status:'screened',periods:['2025-12-31','2024-12-31'],metrics:{dsri:0},risk_flags:[]}};
test('company-specific fetch, dates, zero versus missing, escaped evidence and no invented total',async()=>{
  let url; const x=setup(async u=>(url=u,{ok:true,json:async()=>doc}));
  await x.mount(x.el,{cik:'0000000123'});
  assert.equal(url,'disclosures/data/debt/c/123.json');
  for(const s of ['USD 0','Not available','2025-12-31','2026-03-31','2024-12-31','&lt;script&gt;','not a total hidden-debt figure','not an assurance']) assert.ok(x.el.innerHTML.includes(s),s);
  assert.ok(!x.el.innerHTML.includes('javascript:'));
});
test('mismatched company data is never displayed; retry is available',async()=>{
  const x=setup(async()=>({ok:true,json:async()=>({...doc,cik:'999'})}));
  await x.mount(x.el,{cik:123}); assert.match(x.el.innerHTML,/temporarily unavailable/);assert.equal(typeof x.button.onclick,'function');assert.doesNotMatch(x.el.innerHTML,/Purchase commitments/);
});
test('404 is uncollected, not zero debt',async()=>{
  const x=setup(async()=>({status:404}));await x.mount(x.el,{cik:123});assert.match(x.el.innerHTML,/No debt or disclosure snapshot/);assert.doesNotMatch(x.el.innerHTML,/USD 0/);
});
test('stale response cannot replace a newer company',async()=>{
  let resolve;let count=0;const x=setup(()=>++count===1?new Promise(r=>resolve=r):Promise.resolve({ok:true,json:async()=>({...doc,cik:'456'})}));
  const first=x.mount(x.el,{cik:123});await x.mount(x.el,{cik:456});resolve({ok:true,json:async()=>doc});await first;assert.match(x.el.innerHTML,/#c-456-debt/);assert.doesNotMatch(x.el.innerHTML,/#c-123-debt/);
});
test('navigation invalidation prevents rendering',async()=>{
  const x=setup(async()=>({ok:true,json:async()=>doc}));await x.mount(x.el,{cik:123,here:()=>false});assert.match(x.el.innerHTML,/Loading/);
});
test('SEC evidence links retained and compact summary has detail route',async()=>{
 const d=structuredClone(doc);d.hidden_leverage.categories[0].source_url='https://www.sec.gov/Archives/example.htm';const x=setup(async()=>({ok:true,json:async()=>d}));await x.mount(x.el,{cik:123,compact:true});assert.match(x.el.innerHTML,/https:\/\/www.sec.gov\/Archives\/example.htm/);assert.match(x.el.innerHTML,/#c-123-risk/);
});
test('company disclosure navigation, dispatcher and deep link remain wired',()=>{
 const app=fs.readFileSync('web/app.js','utf8');
 assert.match(app,/\['risk', 'Disclosures & risk'\]/);
 assert.match(app,/which === 'risk'\) return window.FFCompanyDisclosures.mount/);
 const route=app.split('\n').find(l=>l.includes('await analysisPage(m[1], m[2])'));
 assert.ok(route.includes('|risk|'));
 assert.match(fs.readFileSync('web/index.html','utf8'),/src="company-disclosures.js"/);
});
test('Quality missing file retries and exposes independent company evidence without guessing exclusion',async()=>{
 const code=fs.readFileSync('disclosures/docs/quality-view.js','utf8');let attempts=0,mounted=0;const button={};
 const el={isConnected:true,innerHTML:'',querySelector:()=>button,appendChild(){}};
 const window={FFCompanyDisclosures:{mount:async(panel,opt)=>{assert.equal(opt.cik,1769628);mounted++;}}};
 const document={head:{appendChild(){}},createElement:()=>({})};
 vm.runInNewContext(code,{window,document,fetch:async()=>{attempts++;return {ok:false,status:404};}});
 await window.QualityView.render(el,{ticker:'CRWV',cik:1769628,here:()=>true});
 assert.match(el.innerHTML,/reason is not reported/);assert.doesNotMatch(el.innerHTML,/under \$300M/);assert.equal(mounted,1);
 await button.onclick();assert.equal(attempts,2);assert.equal(mounted,2);
 await window.QualityView.render(el,{ticker:'CRWV',cik:1769628,here:()=>false});assert.equal(mounted,2);
});
