// Lightweight template/logic tests in Node; NOT a browser or visual QA test.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const elements=new Map();
const doc={getElementById(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',className:'',value:'',setAttribute(){},classList:{toggle(){}}});return elements.get(id)},querySelectorAll(){return []}};
const context=vm.createContext({document:doc,window:{},console,setTimeout,URL,Blob});
const live=JSON.parse(fs.readFileSync(path.join(root,'docs/data/live.json'),'utf8'));
for(const [key,field] of [['holdings','managers'],['congress','reports']])for(let i=0;i<(live.modules[key]?.[field]||[]).length;i++){const r=live.modules[key][field][i];if(r.shard)live.modules[key][field][i]=JSON.parse(fs.readFileSync(path.join(root,'docs/data',r.shard),'utf8'))}
for(const m of live.modules.holdings?.managers||[])for(const s of m.snapshots||[])if(s.positions_shard)s.positions=JSON.parse(fs.readFileSync(path.join(root,'docs/data',s.positions_shard),'utf8'));
for(const key of ['cot','banks'])for(let i=0;i<(live.modules[key]?.series||[]).length;i++){const r=live.modules[key].series[i];if(r.shard)live.modules[key].series[i]=JSON.parse(fs.readFileSync(path.join(root,'docs/data',r.shard),'utf8'))}
for(let i=0;i<(live.modules.npx?.filings||[]).length;i++){let f=live.modules.npx.filings[i];if(f.shard){f=JSON.parse(fs.readFileSync(path.join(root,'docs/data',f.shard),'utf8'));f.votes=f.vote_chunks?.length?JSON.parse(fs.readFileSync(path.join(root,'docs/data',f.vote_chunks[0]),'utf8')):[];f._loaded_chunks=f.vote_chunks?.length?1:0;live.modules.npx.filings[i]=f}}
for(const m of Object.values(live.modules))if(m.directory_shard)m.directory=JSON.parse(fs.readFileSync(path.join(root,'docs/data',m.directory_shard),'utf8'));
context.window.DISCLOSURE_LIVE=live;
for(const f of ['data/demo.js','dashboard.js','extensions.js','app.js'])vm.runInContext(fs.readFileSync(path.join(root,'docs',f),'utf8'),context,{filename:f});
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
})().catch(e=>{console.error(e);process.exitCode=1});
