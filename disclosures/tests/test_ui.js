// Lightweight template/logic tests in Node; NOT a browser or visual QA test.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const elements=new Map();
const doc={getElementById(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',className:'',value:'',setAttribute(){},classList:{toggle(){}}});return elements.get(id)},querySelectorAll(){return []}};
const context=vm.createContext({document:doc,window:{},console,setTimeout,URL,Blob,location:{hash:''},history:{replaceState(){}},addEventListener(){},innerWidth:1200});
const live=JSON.parse(fs.readFileSync(path.join(root,'docs/data/live.json'),'utf8'));
for(const [key,field] of [['holdings','managers'],['congress','reports']])for(let i=0;i<(live.modules[key]?.[field]||[]).length;i++){const r=live.modules[key][field][i];if(r.shard)live.modules[key][field][i]=JSON.parse(fs.readFileSync(path.join(root,'docs/data',r.shard),'utf8'))}
for(const m of live.modules.holdings?.managers||[])for(const s of m.snapshots||[])if(s.positions_shard)s.positions=JSON.parse(fs.readFileSync(path.join(root,'docs/data',s.positions_shard),'utf8'));
for(const key of ['cot','banks'])for(let i=0;i<(live.modules[key]?.series||[]).length;i++){const r=live.modules[key].series[i];if(r.shard)live.modules[key].series[i]=JSON.parse(fs.readFileSync(path.join(root,'docs/data',r.shard),'utf8'))}
for(let i=0;i<(live.modules.npx?.filings||[]).length;i++){let f=live.modules.npx.filings[i];if(f.shard){f=JSON.parse(fs.readFileSync(path.join(root,'docs/data',f.shard),'utf8'));f.votes=f.vote_chunks?.length?JSON.parse(fs.readFileSync(path.join(root,'docs/data',f.vote_chunks[0]),'utf8')):[];f._loaded_chunks=f.vote_chunks?.length?1:0;live.modules.npx.filings[i]=f}}
for(const m of Object.values(live.modules))if(m.directory_shard)m.directory=JSON.parse(fs.readFileSync(path.join(root,'docs/data',m.directory_shard),'utf8'));
context.window.DISCLOSURE_LIVE=live;
// the page's own scripts, in its order (docs/index.html), so a new view is tested as soon as the page loads it
const PAGE_SCRIPTS=[...fs.readFileSync(path.join(root,'docs','index.html'),'utf8').matchAll(/<script src="([^"]+)"/g)].map(m=>m[1]).filter(f=>f!=='data/live.js');
for(const f of PAGE_SCRIPTS)vm.runInContext(fs.readFileSync(path.join(root,'docs',f),'utf8'),context,{filename:f});
let checks=0;
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
})().catch(e=>{console.error(e);process.exitCode=1});
