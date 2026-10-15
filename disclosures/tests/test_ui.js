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
for(const f of ['data/demo.js','dashboard.js','extensions.js','market.js','rotation.js','options.js','app.js'])vm.runInContext(fs.readFileSync(path.join(root,'docs',f),'utf8'),context,{filename:f});
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
  for(const [tab,name,expect] of [['signals','signals','Hype map'],['flows','flows','Net buying and selling'],['trades','officials-trades','Most bought by officials']]){
   vm.runInContext(`state.mode='official';state.tab='${tab}';state.page=0;state.sort=null;render()`,context);
   await vm.runInContext(`marketStore['${name}'].loading`,context);
   vm.runInContext(`render()`,context);
   const html=elements.get('workspace').innerHTML;
   assert.ok(html.includes(expect),`${tab} did not render its chart`);
   assert.ok(!html.includes('NaN')&&!html.includes('undefined'),`${tab} shows NaN/undefined`);
   assert.ok(html.includes('data-sort-col'),`${tab} table is not sortable`);n++;
   vm.runInContext(`state.sort={sig:state.tab+'|'+'x',col:1,dir:'asc'};render()`,context);n++;
  }
  if(fs.existsSync(path.join(mdir,'rotation.json'))){
   for(const freq of ['q','m'])for(const view of ['clock','solar','3d','scan'])for(const sec of ['','technology'])for(const tk of ['','NVDA, AMD'])for(const [x,y,z,scl,sm] of [['dom','rel','volz','raw','none'],['revg','vola','f13','log','ewma'],['rel','dom','__time','rank','ma'],['om','rel','revg','z','none']]){
    if(view==='scan'&&(freq==='m'||scl!=='raw'))continue;
    vm.runInContext(`state.tab='rotation';state.rfreq='${freq}';state.rview='${view}';state.rsec='${sec}';state.rtk='${tk}';state.rx='${x}';state.ry='${y}';state.rz='${z==='__time'?'':z}';state.rz3='${z}';state.rscl='${scl}';state.rsm='${sm}';state.rshow='';render()`,context);await vm.runInContext(`marketStore['rotation'].loading`,context);vm.runInContext(`render()`,context);
    if(freq==='m'&&fs.existsSync(path.join(mdir,'rotation-monthly.json'))){await vm.runInContext(`marketStore['rotation-monthly'].loading`,context);vm.runInContext(`render()`,context)}
    const h=elements.get('workspace').innerHTML;assert.ok(h.includes(view==='scan'?'Clearest cycles':view==='3d'?'rot-3d':'rot-plot'),`rotation ${view} did not render`);assert.ok(!h.includes('NaN')&&!h.includes('undefined')&&!h.includes('Infinity'),`rotation ${view} ${sec} ${tk} ${x}/${y} shows NaN/undefined`);n++}
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
})().catch(e=>{console.error(e);process.exitCode=1});
