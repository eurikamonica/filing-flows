// Lightweight template/logic tests in Node; NOT a browser or visual QA test.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const elements=new Map();
const doc={getElementById(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',className:'',value:'',setAttribute(){},classList:{toggle(){}}});return elements.get(id)},querySelectorAll(){return []}};
const context=vm.createContext({document:doc,window:{},console,setTimeout,URL,Blob,location:{hash:''},history:{replaceState(){}},addEventListener(){},innerWidth:1200,fetch:()=>Promise.resolve({ok:false,json:async()=>({})})});
const live=JSON.parse(fs.readFileSync(path.join(root,'docs/data/live.json'),'utf8'));
// a module's checkout leaves some shards out (the officials and light runs skip shards/holdings and shards/npx);
// rows whose shard is absent are dropped so the views render what is on disk instead of reaching for the network
const shard=p=>{const f=path.join(root,'docs/data',p);return fs.existsSync(f)?JSON.parse(fs.readFileSync(f,'utf8')):null};
const inline=(rows,load)=>{const out=[];for(const r of rows||[]){const v=load(r);if(v)out.push(v)}return out};
if(live.modules.holdings)live.modules.holdings.managers=inline(live.modules.holdings.managers,r=>{const m=r.shard?shard(r.shard):r;if(!m)return null;
 m.snapshots=inline(m.snapshots,s=>{if(!s.positions_shard)return s;const p=shard(s.positions_shard);if(!p)return null;s.positions=p;return s});return m});
if(live.modules.congress)live.modules.congress.reports=inline(live.modules.congress.reports,r=>r.shard?shard(r.shard):r);
for(const key of ['cot','banks'])if(live.modules[key])live.modules[key].series=inline(live.modules[key].series,r=>r.shard?shard(r.shard):r);
if(live.modules.npx)live.modules.npx.filings=inline(live.modules.npx.filings,r=>{if(!r.shard)return r;const f=shard(r.shard);if(!f)return null;
 f.votes=f.vote_chunks?.length?(shard(f.vote_chunks[0])||[]):[];f._loaded_chunks=f.vote_chunks?.length?1:0;return f});
for(const m of Object.values(live.modules))if(m.directory_shard){const d=shard(m.directory_shard);if(d)m.directory=d;else{m.directory=[];delete m.directory_shard}}
context.window.DISCLOSURE_LIVE=live;
// the page's own scripts, in its order (docs/index.html), so a new view is tested as soon as the page loads it
const PAGE_SCRIPTS=[...fs.readFileSync(path.join(root,'docs','index.html'),'utf8').matchAll(/<script src="([^"]+)"/g)].map(m=>m[1]).filter(f=>f!=='data/live.js'&&!f.startsWith('../'));   // ../nav.js: the site's shared menu, not part of the hub
for(const f of PAGE_SCRIPTS)vm.runInContext(fs.readFileSync(path.join(root,'docs',f),'utf8'),context,{filename:f});
let checks=0;
const derivedFresh=vm.runInContext("derivedMarketNotice('signals',{holdings:{updated_at:'2026-10-18T21:32:54Z'},congress:{updated_at:'2026-10-20T01:00:00Z'}},{signals:{data:{generated_at:'2026-10-21T04:15:47Z'}}},Date.parse('2026-10-21T04:41:00Z'))",context);
assert.equal(derivedFresh.stale,false);
assert.ok(derivedFresh.text.includes('Generated 2026-10-21T04:15:47Z'));
assert.ok(derivedFresh.text.includes('13F source: 2026-10-18T21:32:54Z'));
checks+=3;
const derivedOld=vm.runInContext("derivedMarketNotice('signals',{holdings:{updated_at:'2026-10-20T00:00:00Z'}},{signals:{data:{generated_at:'2026-10-18T21:32:54Z'}}},Date.parse('2026-10-21T04:41:00Z'))",context);
assert.equal(derivedOld.stale,true);
assert.equal(vm.runInContext("derivedMarketNotice('holdings',{holdings:{updated_at:'2026-10-18'}},{},0)",context),null);
checks+=2;

for(const mode of ['official','demo'])for(const tab of ['holdings','congress','review','cot','banks','npx','status','directory']){
 vm.runInContext(`state.mode='${mode}';state.tab='${tab}';state.date='';state.page=0;render();`,context);
 const html=elements.get('workspace').innerHTML;
 assert.ok(html.length>150,`${mode}/${tab} did not render`);
 assert.ok(!html.includes('NaN'),'Non-finite number displayed');checks++;
}
for(const mode of ['official','demo'])for(const kind of ['holdings','congress','cot','banks','npx']){
 vm.runInContext(`state.mode='${mode}';state.tab='directory';state.dtype='${kind}';state.dq='';state.dstatus='';render()`,context);
 assert.ok(elements.get('workspace').innerHTML.includes('Search results'));checks++;
}
assert.equal(vm.runInContext(`esc('<img src=x onerror="bad">')`,context),'&lt;img src=x onerror=&quot;bad&quot;&gt;');checks++;
assert.equal(vm.runInContext(`csvCell('=HYPERLINK("bad")')`,context),'"\'=HYPERLINK(""bad"")"');checks++;
assert.equal(vm.runInContext(`link('javascript:alert(1)')`,context),'—');checks++;
assert.equal(vm.runInContext(`fmt(null)`,context),'—');checks++;
vm.runInContext("state.discFrom='2026-01-01';state.discTo='2026-03-31'",context);
assert.equal(vm.runInContext("discDateMatches({date:'2026-03-31'},['date'])",context),true);checks++;
assert.equal(vm.runInContext("discDateMatches({date:'2026-04-01'},['date'])",context),false);checks++;
assert.equal(vm.runInContext("discDateMatches({filed:'2026-01-01'},['filed'])",context),true);checks++;
assert.equal(vm.runInContext("discDateMatches({no_date:true},['filed'])",context),false);checks++;
vm.runInContext("state.discFrom='';state.discTo=''",context);
assert.equal(vm.runInContext("discDateMatches({no_date:true},['filed'])",context),true);checks++;

// 4.19 cross-holdings: each view renders from a small fixture (the map, one company, the matrix, the holders)
vm.runInContext(`xhStore.data={generated_at:'2026-10-22T00:00:00Z',quarter:'2026-06-30',note:'n',managers:3,
 holders:[{id:'gov',kind:'gov',label:'US government',as_of:'2026-10-21',edges:[{ticker:'INTC',usd:6e10,pct:'9.9%',status:'held',agency:'Commerce',instrument:'Common stock',basis:'shares × close',announced:'2025-08-22',source:'https://www.sec.gov/x'}],private:[{name:'xLight',agency:'Commerce',instrument:'Equity',cost_usd:15e7,status:'held',announced:'2025-12-01'}]},
  {id:'president',kind:'president',label:'President Trump',pending:false,trades:10,with_ticker:8,span:['2026-01-06','2026-07-31'],filings:[{name:'r.pdf',url:'https://extapps2.oge.gov/x.pdf',filed:'2026-09-08',kind:'278T',pages:37,pages_read:37,rows:1156}],edges:[{ticker:'NVDA',usd:-5e5,buy_mid:1e5,sell_mid:6e5,buys:1,sells:2,first:'2026-01-06',last:'2026-02-10'}]},
  {id:'officials',kind:'officials',label:'Congress (net trades)',since:'2025-10-22',edges:[{ticker:'INTC',usd:41e5,buy_mid:415e4,sell_mid:5e4,buyers:3,sellers:1,trades:9,people:['A B']}],people:[{person:'A B',jurisdiction:'US House',buy_mid:1e5,sell_mid:0,trades:2,top:[['INTC',1e5]]}]},
  {id:'ta',kind:'ta',label:'Trump Accounts',fund:'SPYM',holdings:503,lineup:[['SPYM','default']],edges:[{ticker:'NVDA',weight:.08,per_1000:80}]},
  {id:'corp:1045810',kind:'corp',label:'NVIDIA CORP',ticker:'NVDA',total:6e10,positions:1,as_of:'2026-06-30',sic_desc:'Semiconductors',edges:[{ticker:'INTC',usd:3e10,shares:2e8,weight:.5,pct_out:.046}]}],
 companies:[{ticker:'INTC',name:'Intel',price:140,shares_out:4.4e9,mcap:6.2e11,f13_holders:3000,f13_usd:2e11,f13_pct:.62,top_institutions:[{cik:1,name:'V',usd:1e10,shares:7e7,pct:.016,period:'2026-06-30'}],is_holder:null},
  {ticker:'NVDA',name:'NVIDIA',f13_holders:4000,f13_usd:3e12,top_institutions:[],is_holder:'corp:1045810'}],
 chains:[{from:'ta',via:'NVDA',to:'INTC',w1:80,usd2:3e10,pct2:.046}],mutual:[],institutions:[{cik:1,name:'V',total:7e12,period:'2026-06-30'}]};xhIndex(xhStore.data);`,context);
for(const v of ['map','company','matrix','holders']){
 vm.runInContext(`state.tab='cross';state.xhv='${v}';state.xht='INTC';render()`,context);
 const html=elements.get('workspace').innerHTML;
 assert.ok(html.includes('Cross-holdings')&&!html.includes('NaN')&&!html.includes('undefined'),'cross-holdings '+v+' did not render cleanly');checks++;
}
assert.ok(elements.get('workspace').innerHTML.includes('Commerce'));checks++;
vm.runInContext(`crossDeepLink('NVDA')`,context);assert.equal(vm.runInContext('state.xhv+state.xht',context),'companyNVDA');checks++;
console.log(`${checks} UI template/logic checks passed; no browser rendering checked.`);
(async()=>{
 context.fetch=async url=>({ok:true,json:async()=>url.endsWith('123.json')?{snapshots:[{period:'2025-12-31',positions_shard:'shards/holdings/123-2025-12-31.json'}]}:[{issuer:'TEST',shares:1}]});
 vm.runInContext(`globalThis.sampleShard={shard:'shards/holdings/123.json'};ensureShard(sampleShard)`,context);
 await vm.runInContext(`inflight.get(sampleShard.shard)`,context);
 assert.equal(vm.runInContext(`sampleShard._loaded`,context),true);
 assert.equal(vm.runInContext(`sampleShard.snapshots[0].positions[0].issuer`,context),'TEST');
 context.fetch=async()=>({ok:false,status:404});
 vm.runInContext(`globalThis.brokenShard={shard:'shards/holdings/404.json'};ensureShard(brokenShard)`,context);
 await vm.runInContext(`inflight.get(brokenShard.shard)`,context);
 assert.match(vm.runInContext(`brokenShard._loadError`,context),/404/);
 context.fetch=async url=>({ok:true,json:async()=>url.endsWith('999.json')?{vote_count:2,vote_chunks:['shards/npx/999-00000.json','shards/npx/999-00001.json']}:url.endsWith('00000.json')?[{issuer:'FIRST'}]:[{issuer:'SECOND'}]});
 vm.runInContext(`globalThis.npxSample={shard:'shards/npx/999.json'};ensureShard(npxSample)`,context);
 await vm.runInContext(`inflight.get(npxSample.shard)`,context);
 assert.equal(vm.runInContext(`npxSample.votes.length`,context),1);
 assert.equal(vm.runInContext(`npxSample._loaded_chunks`,context),1);
 await vm.runInContext(`loadMoreVotes(npxSample)`,context);
 assert.equal(vm.runInContext(`npxSample.votes.length`,context),2);
 assert.equal(vm.runInContext(`npxSample.votes[1].issuer`,context),'SECOND');
 vm.runInContext(`state.mode='official';data().modules.banks.directory_shard='catalogs/banks.json';delete data().modules.banks.directory;`,context);
 context.fetch=async()=>({ok:true,json:async()=>[{id:'14',name:'CATALOG TEST',cert:14}]});
 vm.runInContext(`ensureCatalog('banks')`,context);
 await vm.runInContext(`inflight.get('catalogs/banks.json')`,context);
 assert.equal(vm.runInContext(`data().modules.banks.directory[0].name`,context),'CATALOG TEST');
 console.log('8 asynchronous shard/loading checks passed.');
 // 4.3 market views: signals, flows and officials' trades from data/market/*.json (when built)
 const mdir=path.join(root,'docs/data/market');
 if(fs.existsSync(path.join(mdir,'signals.json'))){
  vm.runInContext(`for(const k of Object.keys(marketStore))delete marketStore[k]`,context);
  context.fetch=async url=>{const f=path.join(root,'docs',url);return fs.existsSync(f)?{ok:true,json:async()=>JSON.parse(fs.readFileSync(f,'utf8'))}:{ok:false,status:404}};
  let n=0;
  const views=[['signals','signals','Hype map'],['flows','flows','Net buying and selling'],['trades','officials-trades','Most bought by officials'],['insiders','insiders','Most insider buying'],
   ['events','events8k','What companies reported'],['news','news','Matched to a ticker'],['stakes','stakes','Most 13D activity'],['form144','form144','Most planned selling'],['shorts','short-interest','Biggest changes in short interest']].filter(v=>fs.existsSync(path.join(mdir,v[1]+'.json')));
  for(const [tab,name,expect] of views){
   vm.runInContext(`state.mode='official';state.tab='${tab}';state.page=0;state.sort=null;render()`,context);
   await vm.runInContext(`marketStore['${name}'].loading`,context);
   vm.runInContext(`render()`,context);
   const html=elements.get('workspace').innerHTML;
   assert.ok(html.includes(expect),`${tab} did not render its chart`);
   assert.ok(!html.includes('NaN')&&!html.includes('undefined'),`${tab} shows NaN/undefined`);
   assert.ok(html.includes('data-sort-col'),`${tab} table is not sortable`);n++;
   if(tab==='insiders')assert.ok(/class="tk" href="\.\.\/#c-\d+"/.test(html),'insider tickers do not link to the company page');
   if(tab==='trades')assert.ok(/class="tk" href="\.\.\/#t-[A-Z]/.test(html),'officials tickers do not link to the main site');
   vm.runInContext(`state.sort={sig:state.tab+'|'+'x',col:1,dir:'asc'};render()`,context);n++;
  }
  if(fs.existsSync(path.join(mdir,'rotation.json'))){
   for(const freq of ['q','m'])for(const view of ['clock','solar','3d','rs','map','heat','breadth','corr','scan'])for(const sec of ['','technology'])for(const tk of ['','NVDA, AMD'])for(const [x,y,z,scl,sm] of [['dom','rel','volz','raw','none'],['revg','vola','f13','log','ewma'],['rel','dom','__time','rank','ma'],['om','rel','revg','z','none']]){
    if(view==='scan'&&(freq==='m'||scl!=='raw'))continue;
    vm.runInContext(`state.tab='rotation';state.rfreq='${freq}';state.rview='${view}';state.rsec='${sec}';state.rtk='${tk}';state.rx='${x}';state.ry='${y}';state.rz='${z==='__time'?'':z}';state.rz3='${z}';state.rscl='${scl}';state.rsm='${sm}';state.rshow='';render()`,context);await vm.runInContext(`marketStore['rotation'].loading`,context);vm.runInContext(`render()`,context);
    if(freq==='m'&&fs.existsSync(path.join(mdir,'rotation-monthly.json'))){await vm.runInContext(`marketStore['rotation-monthly'].loading`,context);vm.runInContext(`render()`,context)}
    const h=elements.get('workspace').innerHTML;assert.ok(h.includes(view==='scan'?'Clearest cycles':view==='3d'?'rot-3d':view==='rs'?'RS rating':view==='heat'?'Sector heatmap':view==='breadth'?'Market breadth':view==='corr'?'move together':'rot-plot'),`rotation ${view} did not render`);assert.ok(!h.includes('NaN')&&!h.includes('undefined')&&!h.includes('Infinity'),`rotation ${view} ${sec} ${tk} ${x}/${y} shows NaN/undefined`);n++}
   for(let f=0;f<4;f++){vm.runInContext(`state.rfreq='q';state.rview='clock';state.rsec='';state.rf=${f};render();ROT.ctx.draw(${f})`,context);assert.ok(!elements.get('workspace').innerHTML.includes('NaN'));n++}
  }
  if(fs.existsSync(path.join(mdir,'options13f.json'))){
   for(const [list,univ,one] of [['under','stocks',false],['under','all',false],['moves','stocks',false],['books','stocks',false],['under','stocks',true]]){
    vm.runInContext(`state.tab='options';state.omode='13f';state.o13l='${list}';state.o13u='${univ}';state.o13='';render()`,context);await vm.runInContext(`marketStore['options13f'].loading`,context);
    if(one)vm.runInContext(`state.o13=marketStore['options13f'].data.rows[0].cusip`,context);vm.runInContext(`render()`,context);
    const h=elements.get('workspace').innerHTML;assert.ok(h.includes(one?'Largest holders':'Calls and puts disclosed'),`13F options ${list} did not render`);assert.ok(!h.includes('NaN')&&!h.includes('undefined'),`13F options ${list} shows NaN/undefined`);n++}
   vm.runInContext(`state.omode='chains';state.o13=''`,context);
  }
  for(const list of ['net_sell','first_on_file','retired','most_sellers']){vm.runInContext(`state.tab='flows';state.flist='${list}';render()`,context);assert.ok(!elements.get('workspace').innerHTML.includes('NaN'));n++}
  for(const win of ['ytd','early']){vm.runInContext(`state.tab='flows';state.fwin='${win}';render()`,context);assert.ok(!elements.get('workspace').innerHTML.includes('NaN'));n++}
  vm.runInContext(`state.mode='demo';state.tab='signals';render()`,context);assert.ok(elements.get('workspace').innerHTML.includes('official snapshot'));n++;
  console.log(`${n} market-view checks passed.`);
 }
 // sortable tables: numbers, money and dashes
 assert.equal(vm.runInContext(`JSON.stringify(sortKey('−$25.1B'))`,context),'[0,-25100000000]');
 assert.equal(vm.runInContext(`JSON.stringify(sortKey('—'))`,context),'[2,0]');
 vm.runInContext(`state.tab='t';state.sort={sig:'t|A',col:0,dir:'desc'}`,context);
 assert.deepEqual(JSON.parse(vm.runInContext(`JSON.stringify(sortRows('t|A',[['$1M'],['—'],['$3B'],['$20K']]).map(r=>r[0]))`,context)),['$3B','$1M','$20K','—']);
 // 4.14 smart money: every view from trimmed fixtures (tests/fixtures/smart, cut from a real build)
 {
  const fx=path.join(__dirname,'fixtures','smart'),map={'data/smart/index.json':'index.json','data/smart/actors.json':'actors.json','data/smart/t/KTOS.json':'t-KTOS.json','data/smart/a/gov/55.json':'a-gov.json'};
  context.fetch=async url=>map[url]?{ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(fx,map[url]),'utf8'))}:{ok:false,status:404};
  assert.equal(vm.runInContext(`smBucket('g:NANCY PELOSI')`,context),'55');                 // = smart.py bucket()
  let n=0;
  for(const [setup,key,expect] of [[`state.mview='stocks'`,'index','Skilled net buying'],[`state.mview='stocks';state.msort='sell';state.mgrp='f13'`,'index','Skilled net selling'],
    [`state.mview='leaders';state.mlg='gov'`,'index','The best records'],[`state.mview='leaders';state.mlg='f13';state.mlw='worst'`,'index','The worst records'],
    [`state.mview='method'`,'index','How the score has done'],[`state.mview='stock';state.mst='KTOS'`,'t/KTOS','Who is voting now'],
    [`state.mview='actor';state.maid='g:NANCY PELOSI'`,'a/gov/55','Every trade'],[`state.mview='actor';state.maid='';state.maq='pelosi'`,'actors','Every trade']]){
   vm.runInContext(`state.tab='smart';state.mode='official';state.page=0;${setup};render()`,context);
   await vm.runInContext(`smStore['${key}'].loading`,context);
   vm.runInContext(`render()`,context);
   const html=elements.get('workspace').innerHTML;
   assert.ok(html.includes(expect),`smart money ${setup} did not render "${expect}"`);
   assert.ok(!/NaN|undefined|Infinity/.test(html),`smart money ${setup} shows NaN/undefined`);n++;
  }
  // All flows: every group side by side, the agreement and split lists, the names, Reddit's hottest on top
  Object.assign(map,{'data/smart/combined/index.json':'combined-index.json','data/smart/combined/prev.json':'combined-prev.json','data/smart/combined/both.json':'combined-both.json','data/market/reddit.json':'reddit.json'});
  vm.runInContext(`for(const k of Object.keys(afStore))delete afStore[k]`,context);      // the smart-money views asked for the windows before they existed here
  for(const [setup,key,expect] of [[`state.afv='stocks';state.afp='prev'`,'smart/combined/prev','stocks —'],[`state.afv='agree';state.afp='both'`,'smart/combined/both','Net bought by two groups or more'],
    [`state.afv='split'`,'smart/combined/both','Where the groups take opposite sides'],[`state.afv='names'`,'smart/combined/both','The most active names'],[`state.afv='stocks';state.afs='gbuy';state.afg='2'`,'smart/combined/both','stocks —']]){
   vm.runInContext(`state.tab='allflows';state.page=0;${setup};render()`,context);
   await vm.runInContext(`afStore['smart/combined/index'].loading`,context);vm.runInContext(`render()`,context);
   await vm.runInContext(`(afStore['${key}']||{}).loading`,context);await vm.runInContext(`(afStore['market/reddit']||{}).loading`,context);vm.runInContext(`render()`,context);
   const html=elements.get('workspace').innerHTML;
   assert.ok(html.includes(expect),`all flows ${setup} did not render "${expect}"`);
   assert.ok(html.includes('Reddit right now')&&html.includes('$KTOS'),`all flows ${setup}: no Reddit banner`);
   assert.ok(!/NaN|undefined|Infinity/.test(html),`all flows ${setup} shows NaN/undefined`);n++;
  }
  // the groups that make up the total, and the smart score inside a window (this quarter's filings, the quarter before …)
  vm.runInContext(`state.tab='allflows';state.afv='stocks';state.afp='prev';state.afs='net';state.afg='1';state.afc='f13,ins';render()`,context);
  await vm.runInContext(`(afStore['smart/combined/prev']||{}).loading`,context);vm.runInContext(`render()`,context);
  {const html=elements.get('workspace').innerHTML;assert.ok(html.includes('Net = 13F managers + Insiders')&&html.includes('data-fg="afc"'),'all flows: the groups counted are not shown');
   assert.ok(!/NaN|undefined|Infinity/.test(html),'all flows with chosen groups shows NaN/undefined');n++}
  vm.runInContext(`state.tab='smart';state.mview='stocks';state.mper='prev';state.mgrp='';state.msort='buy';state.mmin='1';state.mq='';render()`,context);
  await vm.runInContext(`(afStore['smart/combined/index']||{}).loading`,context);await vm.runInContext(`(afStore['smart/combined/prev']||{}).loading`,context);vm.runInContext(`render()`,context);
  {const html=elements.get('workspace').innerHTML;assert.ok(html.includes('Smart score (window)')&&html.includes('id="mper"'),'smart money: the window is not drawn');
   assert.ok(!/NaN|undefined|Infinity/.test(html),'smart money window shows NaN/undefined');n++}
  vm.runInContext(`state.mper='now'`,context);
  vm.runInContext(`state.tab='signals';smartDeepLink('g%3ANANCY%20PELOSI')`,context);
  assert.equal(vm.runInContext(`state.mview+'|'+state.maid`,context),'actor|g:NANCY PELOSI');
  console.log(`${n} smart-money and all-flows checks passed.`);
 }
 // 4.6b RRG quadrant odds and paths (rrg-odds.js) from a small model: the chain, the row each line reads, the panel, the chart layer
 {
  const P1=Array.from({length:16},(_,i)=>Array.from({length:16},(_,j)=>j===i?.7:.3/15));
  const head=(n,label='calibrated')=>({counts:Array.from({length:n},()=>[5,3,1,1]),P:Array.from({length:n},(_,i)=>[.5,.3,.1+i/1000,.1-i/1000]),label,
   eval:{origins:60,predictions:3000,brier_skill_vs_stay:[.05,.03,.07],brier_skill_vs_freq:[.04,.02,.06],ece:.01}});
  const grp=(primary,joint)=>({primary,lines:10,from:'2002-01-04',heads:{q:{1:head(4),4:head(4),13:head(4,'experimental')},...(primary==='iq'?{iq:{1:head(16),4:head(16),13:head(16,'descriptive_only')}}:{})},
   chain:{joint,P1,labels:{1:'calibrated',4:'experimental',13:'experimental'},eval:{1:{origins:700,predictions:9000,brier_skill_vs_stay:[.1,.09,.11],brier_skill_vs_freq:[.4,.39,.41],ece:.01,label:'calibrated'}}}});
  const M={generated_at:'t',test_from:'2012-01-06',note:'n',groups:{etf_vs_market:grp('q',false),company_vs_market:grp('q',false),company_vs_industry:grp('iq',true)}};
  vm.runInContext(`marketStore['history/rrg-transition-model']={data:${JSON.stringify(M)}};RRGO.paths.clear()`,context);
  const run=c=>JSON.parse(vm.runInContext(`JSON.stringify(${c})`,context)),Md=`marketStore['history/rrg-transition-model'].data`;
  const ch=run(`rrgoChain(${Md},'etf_vs_market',{q:2,hd:1,iq:-1})`);
  assert.equal(ch.marg.length,13);ch.marg.forEach(q=>assert.ok(Math.abs(q.reduce((a,b)=>a+b,0)-1)<1e-9,'chain marginals are not distributions'));
  assert.ok(ch.paths.length===5&&ch.paths.every(p=>p.q[0]===2)&&ch.paths[0].p>=ch.paths[4].p,'paths do not start from the line\'s quadrant');
  assert.deepEqual(ch.labels.slice(0,5),['calibrated','experimental','experimental','experimental','experimental']);
  vm.runInContext(`RRGO.paths.clear()`,context);
  assert.deepEqual(run(`rrgoChain(${Md},'etf_vs_market',{q:2,hd:1,iq:-1}).paths`),ch.paths,'seeded paths change between runs');
  assert.equal(run(`rrgoChain(${Md},'etf_vs_market',{q:2,hd:-1,iq:-1})`),null);          // no last step: no chain state
  const od=run(`rrgoOdds(${Md},'company_vs_industry',{q:1,hd:0,iq:3},'13')`);
  assert.equal(od.head,'iq');assert.equal(od.label,'descriptive_only');assert.equal(od.p[2],.1+13/1000);   // row 4 × industry + company
  assert.equal(run(`rrgoOdds(${Md},'company_vs_industry',{q:1,hd:0,iq:-1},'4')`).head,'q');   // no industry point: the quadrant matrix
  // a sector ETF and a company on a 120-week grid: the panel and the chart layer at the last week
  const N=120,xs=Array.from({length:N},(_,k)=>100+Math.sin(k/9)),ys=Array.from({length:N},(_,k)=>100+Math.cos(k/9));
  vm.runInContext(`(()=>{const D={start:'2024-01-05',weeks:'2026-04-17',series:[{id:'XLK',name:'Tech',group:'sector-etf',start:'2024-01-05',c:[]}],tickers:{NVDA:{n:'NVIDIA',s:'technology'}}};
   const G=rrgGrid(D),calc={x:${JSON.stringify(xs)},y:${JSON.stringify(ys)},z:{}};
   const lines=[{e:{id:'XLK',name:'XLK'},col:'#123',calc},{e:{id:'NVDA',name:'NVDA',start:'2024-01-05',c:new Array(${N}).fill(50),v:new Array(${N}).fill(1000)},col:'#456',calc},{e:{id:'th:x',name:'Basket'},col:'#789',calc}];
   globalThis.__o={D,lines,Q:G.w.labels,freq:'w',n:14,lastK:${N-1},dom:{x:[97,103],y:[97,103]}}})()`,context);
  vm.runInContext(`state.rf=${N-1};state.rrgp='XLK';state.rrgh='4'`,context);
  let html=vm.runInContext(`rrgOdds(__o)`,context);
  assert.ok(html.includes('Quadrant odds and paths')&&html.includes('Most common paths')&&html.includes('How the odds were checked'),'the odds panel is incomplete');
  assert.ok(html.includes('Quadrant · companies')&&html.includes('no model for this kind of line'),'the company or the basket row is wrong');
  assert.ok(!/NaN|undefined|Infinity/.test(html),'the odds panel shows NaN/undefined');
  const layer=vm.runInContext(`rrgOddsLayer(__o,${N-1},v=>v,v=>v)`,context);
  assert.ok(layer.includes('rrgo-path')&&layer.includes('XLK 50%'),'the selected line is not drawn on the chart');
  assert.equal(vm.runInContext(`rrgOddsLayer(__o,${N-2},v=>v,v=>v)`,context),'');               // an earlier week: nothing drawn
  vm.runInContext(`state.rf=${N-2}`,context);
  assert.ok(vm.runInContext(`rrgOdds(__o)`,context).includes('latest week only'));
  vm.runInContext(`__o.n=26`,context);assert.ok(vm.runInContext(`rrgOdds(__o)`,context).includes('14-week window'));
  vm.runInContext(`state.rrgp='';state.rrgh='';delete globalThis.__o`,context);
  console.log('RRG quadrant odds checks passed.');
 }
 // the price paths an option chain implies (options.js optFan / optPathsPanel): exact at every expiry, no NaN
 {
  const probs=[.025,.05,.1,.25,.5,.75,.9,.95,.975],ln=(t,iv,p)=>100*Math.exp(-0.5*iv*iv*t+iv*Math.sqrt(t)*vm.runInContext(`optInvN(${p})`,context));
  const paths=[[9,.22],[37,.25],[100,.28],[365,.3]].map(([d,iv],i)=>({exp:`2026-1${i}-1${i}`.replace('2026-13','2027-01'),days:d,fwd:100,atm_iv:iv,method:'smile',strikes:20,q:probs.map(p=>ln(d/365,iv,p)),max_pain:95+3*i,call_wall:110+5*i,call_wall_oi:900,put_wall:90-5*i,put_wall_oi:800,oi:1000*(i+1)}));
  context.__c={ticker:'XYZ',spot:100,paths,path_probs:probs};
  for(const [i,j] of [[0,0],[1,4],[2,8],[3,2]]){const v=vm.runInContext(`(()=>{const F=optFan(__c);return Math.exp(F.at(${paths[i].days},optInvN(${probs[j]})))})()`,context);assert.ok(Math.abs(v-paths[i].q[j])<1e-6*v,`the fan is not exact at expiry ${i}, quantile ${j}`)}
  const mid=vm.runInContext(`(()=>{const F=optFan(__c);return [Math.exp(F.at(4.5,optInvN(.975))),Math.exp(F.at(4.5,optInvN(.025)))]})()`,context);
  assert.ok(mid[0]>100&&mid[0]<paths[0].q[8]&&mid[1]<100&&mid[1]>paths[0].q[0],'the fan does not open from spot to the first expiry');
  const sims=vm.runInContext(`optSim(optFan(__c),400).map(p=>p[p.length-1][1])`,context).sort((a,b)=>a-b);
  assert.ok(Math.abs(sims[200]-paths[3].q[4])/paths[3].q[4]<.06,'the sample paths do not end on the implied median');
  const h=vm.runInContext(`optPathsPanel(__c,'XYZ')`,context);
  for(const want of ['Price paths the options imply','max pain','95% range','2027-01-13','Call wall','Put wall','call wall by expiry'])assert.ok(h.includes(want),`the price paths panel lacks “${want}”`);
  assert.ok(!/NaN|undefined|Infinity/.test(h),'the price paths panel shows NaN/undefined');
  assert.equal(vm.runInContext(`optPathsPanel({spot:100,paths:[]},'X')`,context),'');
  // the share bar and the post for X (chart-share.js): on the panel, and a post that fits in 280 characters
  assert.ok(h.includes('Save or post this chart')&&h.includes('data-ffs-chart="XYZ-option-paths"'),'the price paths panel has no share bar');
  const op=vm.runInContext(`(()=>{const a=window.FFShare.analysis('XYZ-option-paths');return a})()`,context);
  assert.ok(op&&op.post.startsWith('$XYZ $100')&&vm.runInContext(`window.FFShare.xlen(${JSON.stringify(op.post)})`,context)<=280&&op.paras.length>=3,'the options post is missing or too long');
  assert.equal(vm.runInContext(`window.FFShare.fit(['a'.repeat(200),'b'.repeat(100),'c'],'https://x.co/y')`,context),'a'.repeat(200)+' https://x.co/y','fit does not drop lines from the end');
  // the company page view (views.json → option-paths.js): cards and the panel from the files, a note without a chain
  {const files={'data/market/options/XYZ.json':Object.assign({},context.__c,{max_pain:96,max_pain_exp:'2026-11-20',put_wall:90,call_wall:110}),'data/market/options.json':{rows:[{ticker:'XYZ',spot:100,iv30:25,pc_oi:1.2}]}};
   const keep=context.fetch;context.fetch=async u=>files[u]?{ok:true,json:async()=>files[u]}:{ok:false,status:404};
   const el={innerHTML:''};await vm.runInContext('window.FFOptionPaths.render',context)(el,{ticker:'XYZ',hub:''});
   for(const want of ['Expected move, 30 days','±$7.17','Max pain','Price paths the options imply — XYZ','95% range'])assert.ok(el.innerHTML.includes(want),`the company options view lacks “${want}”`);
   assert.ok(!/NaN|undefined|Infinity/.test(el.innerHTML),'the company options view shows NaN/undefined');
   await vm.runInContext('window.FFOptionPaths.render',context)(el,{ticker:'NOPE',hub:''});assert.ok(el.innerHTML.includes('not collected yet'));
   context.fetch=keep;checks+=3}
  checks+=11;console.log('option price paths checks passed.');
 }
 // the company page's Rotation (RRG) view (rrg-company-view.js, loaded by the main site through views.json)
 {
  const RV=require(path.join(root,'docs','rrg-company-view.js'))._t;
  const N=260,rs=Array.from({length:N},(_,i)=>100*Math.exp(0.002*i+0.04*Math.sin(i/7)+0.02*Math.cos(i/3)));
  const S=RV.states(rs);let k=N-14;
  const P=[[...Array(13)].map((_,j)=>Math.log(rs[k+1+j]/rs[k+j]))],r=RV.stepPaths(S,rs,k,P)[0];
  for(let j=0;j<13;j++){assert.ok(Math.abs(r.x[j]-S.x[k+1+j])<1e-9&&Math.abs(r.y[j]-S.y[k+1+j])<1e-9,'stepping the real moves does not reproduce the chart')}
  k=N-1;const th=RV.thresholds(S,rs,k);
  assert.ok(Math.abs(RV.stepPaths(S,rs,k,[[Math.log(th.mx)]])[0].x[0]-100)<1e-9,'RS-Ratio threshold is not where x crosses 100');
  assert.ok(Math.abs(RV.stepPaths(S,rs,k,[[Math.log(th.my)]])[0].y[0]-100)<1e-9,'RS-Momentum threshold is not where y crosses 100');
  assert.equal(RV.replay(S,rs,k).length,144);                                        // every 13-week run of the last 156 weeks
  checks+=4;
  // the chain converted to a path: odds equal to the replays' own shares give back their plain mean; odds on one
  // quadrant put the path on the replays in it
  {const A={paths:RV.replay(S,rs,k)},n=[0,0,0,0];A.paths.forEach(p=>n[RV.quad(p.x[3],p.y[3])]++);
   const N=A.paths.length,marg=Array.from({length:13},(_,j)=>{const m=[0,0,0,0];A.paths.forEach(p=>m[RV.quad(p.x[j],p.y[j])]++);return m.map(v=>v/N)});
   const mp=RV.markovPath(A,{marg}),mx=A.paths.reduce((a,p)=>a+p.x[3],0)/N;
   assert.ok(Math.abs(mp[3].x-mx)<1e-9&&Math.abs(mp[3].cover-1)<1e-9,'equal odds do not give the plain mean');
   const q=n.indexOf(Math.max(...n)),one=RV.markovPath(A,{marg:marg.map(()=>[0,1,2,3].map(j=>j===q?1:0))});
   assert.equal(RV.quad(one[3].x,one[3].y),q,'odds on one quadrant do not put the path there');checks+=2}
  // the RRG and price posts: every number from the section, the post's lines in order
  {const C=rs.map((v,i)=>v*(400+i)/100),B=Array.from({length:N},(_,i)=>400+i),G={days:Array.from({length:N},(_,i)=>'d'+i)};
   const A=RV.analyse(G,C,null,B,{always:true}),o={name:'TEST',tag:'$TEST',bench:'SPY',h:4,title:'TEST against the S&P 500',odds:{label:'calibrated',p:[.4,.3,.2,.1],hist:[.4,.3,.2,.1]}};
   const r=RV.rrgPost(A,o),pp=RV.pricePost(A,o);
   assert.ok(r.lines[0].startsWith('$TEST vs SPY on the RRG:')&&r.lines.join(' ').includes('Leading 40%')&&r.paras.length>=4,'the RRG post is missing its lines');
   assert.ok(pp.lines[0].startsWith('$TEST:')&&/Replays: 4 wk \$/.test(pp.lines[1]),'the price post is missing its lines');
   assert.ok(!/NaN|undefined/.test(JSON.stringify([r,pp])),'a post shows NaN/undefined');checks+=3}
  // the whole view from small files: two sections, the ladder, the ranges, the matrix and the chain, no NaN
  const D={start:'2021-01-01',weeks:'2025-12-26',bench:{start:'2021-01-01',c:Array.from({length:N},(_,i)=>400+i)}};
  const tf={t:'TEST',n:'Test Co',start:'2021-01-01',c:rs.map((v,i)=>v*(400+i)/100),v:Array(N).fill(500),bl:'SIC 1234 · Things',bn:9,bx:Array.from({length:N},(_,i)=>50+0.05*i+Math.sin(i/11)),bi:Array.from({length:N},(_,i)=>50+0.06*i)};
  const head=(n,l)=>({counts:Array.from({length:n},()=>[5,3,1,1]),P:Array.from({length:n},()=>[.4,.3,.2,.1]),label:l,eval:{brier_skill_vs_stay:[.1,.09,.11],brier_skill_vs_freq:[.12,.1,.14],ece:.01}});
  const P1=Array.from({length:16},(_,i)=>Array.from({length:16},(_,j)=>j===i?.7:.3/15));
  const grp=(primary,joint)=>({primary,heads:{q:{1:head(4,'calibrated'),4:head(4,'calibrated'),13:head(4,'experimental')},...(primary==='iq'?{iq:{1:head(16,'calibrated'),4:head(16,'calibrated'),13:head(16,'calibrated')}}:{})},
   chain:{joint,P1,labels:{1:'calibrated',4:'experimental',13:'experimental'}},bands:{1:{label:'calibrated',coverage:{p80:.8,p50:.5}},4:{label:'calibrated',coverage:{p80:.78,p50:.49}},13:{label:'experimental',coverage:{p80:.74,p50:.46}}}});
  const M={note:'n',replay:{method:'m',labels:'l'},groups:{company_vs_market:grp('q',false),company_vs_industry:grp('iq',true),industry_vs_market:grp('q',false)}};
  tf.bid='sic4:1234';
  const IND={note:'industries',rows:[{id:'sic4:1234',level:'sic4',code:'1234',label:'SIC 1234 · Things',ind:'Things',members:9,tickers:['TEST','NONE'],start:'2021-01-01',c:tf.bi},
   {id:'sic3:567',level:'sic3',code:'567',label:'SIC 567',ind:'Widgets',members:12,tickers:['W1'],start:'2021-01-01',c:Array.from({length:N},(_,i)=>80+0.02*i+3*Math.sin(i/9))}]};
  const files={'data/market/history/rrg.json':D,'data/market/history/t/TEST.json':tf,'data/market/history/rrg-transition-model.json':M,'data/market/history/industries.json':IND};
  const keep=global.fetch;global.fetch=async(u)=>files[u]?{ok:true,json:async()=>files[u]}:{ok:false,status:404};
  const V=require(path.join(root,'docs','rrg-company-view.js'));
  const el={innerHTML:'',clientWidth:700,querySelectorAll:()=>[]};
  await V.render(el,{ticker:'TEST',hub:''});
  for(const want of ['TEST against the S&amp;P 500','TEST against its industry','close that puts it in each quadrant','Replayed ranges','Markov matrix','Dynamic transition model','Most common paths','The chain converted to a path','dotted: the Markov chain','On the price — the last 26 weeks and the next 13'])
   assert.ok(el.innerHTML.includes(want),`the RRG view lacks “${want}”`);
  assert.ok(!/NaN|undefined|Infinity/.test(el.innerHTML),'the RRG view shows NaN/undefined');
  for(const want of ['S&amp;P 500 — the industry','index level that puts it in each quadrant','moved exactly with its industry','#rotation/ind~sic4:1234'])
   assert.ok(el.innerHTML.includes(want),`the industry section lacks “${want}”`);
  // every industry (hub → Rotation → Industry RRG): the list, then one industry with its largest companies' prices
  const ei={innerHTML:'',clientWidth:700,querySelectorAll:()=>[]};
  await V.renderIndustries(ei,{hub:''});
  for(const want of ['SIC 1234 · Things','SIC 567 (mostly Widgets)','Into Leading next week','Most likely in 4 wk','Replayed 4 wk'])
   assert.ok(ei.innerHTML.includes(want),`the industry list lacks “${want}”`);
  assert.ok(!/NaN|undefined|Infinity/.test(ei.innerHTML),'the industry list shows NaN/undefined');
  const ej={innerHTML:'',clientWidth:700,querySelectorAll:()=>[]};
  await V.renderIndustries(ej,{hub:'',id:'sic4:1234'});
  for(const want of ['Every industry','SIC 1234 · Things against the S&amp;P 500','index level that puts it in each quadrant','largest members','Markov matrix','On the index — the last 26 weeks'])
   assert.ok(ej.innerHTML.includes(want),`the industry page lacks “${want}”`);
  assert.ok(!/NaN|undefined|Infinity/.test(ej.innerHTML),'the industry page shows NaN/undefined');
  checks+=4;
  await V.render(el,{ticker:'NONE',hub:''});assert.ok(el.innerHTML.includes('not in the weekly rotation history yet'));
  global.fetch=keep;checks+=9;
  console.log('company RRG view checks passed.');
 }
})().catch(e=>{console.error(e);process.exitCode=1});
