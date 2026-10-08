/* v3 directory, demand-loaded records and explicit coverage metrics. */
const inflight=new Map();
function ensureShard(row){
 if(!row?.shard||row._loaded)return true;
 if(!inflight.has(row.shard)&&!row._loadError){
  const path=row.shard;
  if(!/^shards\/(holdings|congress|cot|banks|npx)\/[A-Za-z0-9_+-]+\.json$/.test(path)){row._loadError='Invalid data path';return false}
  inflight.set(path,fetch('data/'+path).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(async payload=>{await Promise.all((payload.snapshots||[]).map(async s=>{if(!s.positions_shard)return;if(!/^shards\/holdings\/[A-Za-z0-9_+-]+\.json$/.test(s.positions_shard))throw Error('Invalid quarter path');const r=await fetch('data/'+s.positions_shard);if(!r.ok)throw Error('Quarter HTTP '+r.status);s.positions=await r.json()}));if(payload.vote_chunks){payload.votes=[];payload._loaded_chunks=0;if(payload.vote_chunks.length){payload.votes=await fetchVoteChunk(payload.vote_chunks[0]);payload._loaded_chunks=1}}Object.assign(row,payload,{_loaded:true});render()}).catch(e=>{row._loadError='Could not load this data file: '+e.message;render()}).finally(()=>inflight.delete(path)));
 }
 return false;
}
function loading(row){return `<div class="empty">${esc(row._loadError||'Loading the selected disclosure…')}${row._loadError?'<br>Refresh this page to retry. Use a local HTTP server rather than opening index.html directly.':''}</div>`}
async function fetchVoteChunk(path){if(!/^shards\/npx\/[A-Za-z0-9_+-]+\.json$/.test(path))throw Error('Invalid vote-chunk path');const r=await fetch('data/'+path);if(!r.ok)throw Error('Vote chunk HTTP '+r.status);const rows=await r.json();if(!Array.isArray(rows))throw Error('Invalid vote records');return rows}
async function loadMoreVotes(f){
 if(f._loadingMore||!f.vote_chunks||f._loaded_chunks>=f.vote_chunks.length)return;
 f._loadingMore=true;f._chunkError='';render();
 try{const rows=await fetchVoteChunk(f.vote_chunks[f._loaded_chunks]);f.votes.push(...rows);f._loaded_chunks++}catch(e){f._chunkError=e.message}finally{f._loadingMore=false;render()}
}
function ensureCatalog(kind){
 const m=data().modules[kind]||{};
 if(!m.directory_shard||Array.isArray(m.directory))return true;
 const path=m.directory_shard;
 if(path!==`catalogs/${kind}.json`){m._catalogError='Invalid catalog path';return false}
 if(!inflight.has(path)&&!m._catalogError){inflight.set(path,fetch('data/'+path).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(rows=>{if(!Array.isArray(rows))throw Error('Invalid catalog');m.directory=rows;render()}).catch(e=>{m._catalogError=e.message;render()}).finally(()=>inflight.delete(path)))}
 return false;
}
function coverageStrip(kind){
 const m=data().modules[kind]||{},c=m.counts;if(!c)return '';
 const mapping={holdings:[c.processed_managers,c.discovered_managers,c.pending_managers,'managers processed'],congress:[c.extracted_reports,c.discovered_reports,c.pending_reports,'reports extracted'],cot:[c.processed,c.discovered,c.pending,'market histories'],banks:[c.processed,c.discovered,c.pending,'bank histories'],npx:[c.available_filers,c.discovered_filers,c.pending_filers,'filers with documents']};
 const [done,total,pending,label]=mapping[kind];
 return `<div class="coverage-strip"><span class="live-dot"></span><strong>${fmt(done)} / ${fmt(total)}</strong><span>${label}</span><div class="progress"><i style="width:${total?Math.min(100,done/total*100):0}%"></i></div><span>${fmt(pending)} ${kind==='npx'?'filers awaiting scan':'queued'}</span><button class="text-button" data-directory-kind="${kind}">Explore directory ↗</button></div>`;
}
function directory(){
 const modules=data().modules,h=modules.holdings||{},c=modules.congress||{};
 let out=head('Explore the disclosure universe','Search discovered entities and reports. Availability refers to processed data, not complete historical coverage.','DIRECTORY');
 state.dtype=state.dtype||'holdings';
 out+=`<div class="toolbar searchbar">${field('dtype','Directory',[['holdings','13F managers'],['congress',"Officials' reports"],['cot','COT markets'],['banks','FDIC banks'],['npx','N-PX filers']],state.dtype)}<div class="field wide"><label for="dq">Name, identifier, district or state</label><input id="dq" value="${esc(state.dq||'')}" placeholder="Search the catalog · Enter to apply"></div>${field('dstatus','Processing status',[['','Any status'],['ready','Available'],['pending','Queued'],['error','Error'],['unsupported','Unsupported']],state.dstatus||'')}</div>`;
 let list=[];const m=modules[state.dtype]||{};
 if(!ensureCatalog(state.dtype))return out+empty(m._catalogError?'Catalog load failed: '+m._catalogError+' · Refresh to retry.':'Loading this source catalog…');
 if(state.dtype==='holdings')list=(h.directory||h.managers||[]).map(r=>({...r,key:r.cik,label:r.name||r.label,detail:'CIK '+r.cik,status:r.error?'error':r.processed||h.managers?.some(m=>m.cik===r.cik)?'ready':'pending',date:r.latest_filing||'',kind:'holdings'}));
 else if(state.dtype==='congress')list=(c.directory||c.reports||[]).map(r=>({...r,key:r.report_id,label:r.person,detail:[r.jurisdiction||'US House',r.office,r.report_type,r.report_id].filter(Boolean).join(' · '),status:r.status==='extracted'?'ready':r.status||'pending',date:r.filed_date||(r.index_year?String(r.index_year):''),kind:'congress'}));
 else if(state.dtype==='npx')list=(m.directory||h.npx_directory||[]).map(r=>({...r,key:r.cik,label:r.name,detail:'CIK '+r.cik,status:r.error?'error':r.processed?'ready':'pending',date:r.latest_filing||'',kind:'npx'}));
 else list=(m.directory||m.series||[]).map(r=>({...r,key:r.id,label:r.name,detail:state.dtype==='banks'?[`CERT ${r.cert}`,r.city,r.state].filter(Boolean).join(' · '):`${r.family} · ${r.dataset} · ${r.code}`,status:r.error?'error':r.processed||m.series?.some(s=>s.id===r.id)?'ready':'pending',date:r.latest_report||m.series?.find(s=>s.id===r.id)?.latest_date||'',kind:state.dtype}));
 const q=(state.dq||'').trim().toLowerCase();const rows=list.filter(r=>(!q||[r.label,r.detail,r.key].join(' ').toLowerCase().includes(q))&&(!state.dstatus||r.status===state.dstatus)).sort((a,b)=>a.label.localeCompare(b.label));
 out+=`<div class="metrics">${kpi('Catalog entries',fmt(list.length),'Within the defined source scope')}${kpi('Available',fmt(list.filter(r=>r.status==='ready').length),'Processed data or disclosure documents')}${kpi('Queued',fmt(list.filter(r=>r.status==='pending').length),'Incremental processing')}${kpi('Search results',fmt(rows.length),'Filters cover the entire catalog')}</div>`;
 const help={holdings:'Prioritize a manager: Actions → Run workflow → holdings → manager_cik. Notice-only filers may have no public positions.',congress:'US House (index names include candidates and former members), New York State (COELIG statements), California (FPPC portal, filings since 2025) and Canada (federal public registry) are discovered automatically; Texas and SEDI are imports. Names are not verified unique person IDs. Prioritize a report with module congress and report_id.',npx:'N-PX filers and their documents have separate queues. Prioritize with module npx and manager_cik. Downloaded notices or unsupported legacy files are not zero holdings.',banks:'Directory covers FDIC active institutions plus retained/explicit banks. These are bank entities, not listed holding companies. Prioritize with module banks and bank_cert.',cot:'Markets span the configured Disaggregated and TFF futures-only datasets, including historical/inactive codes. Prioritize with module cot and market_id (dataset-code).'};
 out+=`<div class="explain">${esc(help[state.dtype])} Website clicks do not start authenticated GitHub jobs.</div>`;
 exported=rows.map(({key,label,detail,status,date})=>({identifier:key,name:label,detail,status,latest_report_or_filing:date}));
 out+=`<div class="section-head"><h3>${fmt(rows.length)} results</h3><button id="csv" class="action">Export directory ↓</button></div>`;
 return out+table(['Entity / filer','Identifier / disclosure','Latest report / filing','Status','Explore'],rows.map(r=>[esc(r.label),esc(r.detail),esc(r.date),`<span class="badge ${r.status}">${esc(r.status==='pending'?'Queued':r.status)}</span>`,r.status==='ready'?`<button class="text-button" data-open-kind="${r.kind}" data-open-id="${esc(r.key)}">View →</button>`:r.source_url?link(r.source_url,'Source ↗'):'Actions → Run workflow']));
}
function health(){
 const d=data();let out=head('Coverage & collection','Operational health and data completeness are separate measures. A successful run can still have a processing backlog.','SOURCE MONITOR');
 out+='<div class="health-list">';
 for(const key of ['holdings','congress','cot','banks','npx','prices']){
  const m=d.modules[key]||{},c=m.counts||{};let facts=[];
  if(key==='holdings')facts=[['Discovered managers',c.discovered_managers??m.managers?.length],['Processed managers',c.processed_managers??m.managers?.length],['Queued managers',c.pending_managers??0]];
  if(key==='congress')facts=[['Discovered reports',c.discovered_reports??m.reports?.length],['Extracted reports',c.extracted_reports??m.reports?.length],['Reviewed rows',m.records?.length||0],['Queued / unsupported',`${c.pending_reports||0} / ${c.unsupported_reports||0}`]];
  if(key==='prices')facts=[['CUSIPs mapped / seen',`${c.cusips_mapped??0} / ${c.cusips_seen??0}`],['Positions priced',c.positions_priced??0],['Transactions priced',c.records_priced??0],['Tickers fetched this run',c.tickers_fetched_this_run??0]];
  if(key==='cot')facts=[['Discovered markets',c.discovered??uniq((m.rows||[]).map(r=>r.dataset+'|'+r.code)).length],['Processed markets',c.processed??0],['Queued markets',c.pending??0],['Category observations',(m.series||[]).reduce((a,r)=>a+(r.row_count??r.rows?.length??0),0)||m.rows?.length||0]];
  if(key==='banks')facts=[['Discovered banks',c.discovered??uniq((m.rows||[]).map(r=>r.cert)).length],['Processed banks',c.processed??0],['Queued banks',c.pending??0],['Bank-quarter rows',(m.series||[]).reduce((a,r)=>a+(r.row_count??r.rows?.length??0),0)||m.rows?.length||0]];
  if(key==='npx')facts=[['Discovered filers',c.discovered_filers??0],['Scanned filers',c.scanned_filers??0],['Downloaded filings',m.filings?.length||0],['Vote rows',(m.filings||[]).reduce((s,f)=>s+(f.vote_count??f.votes?.length??0),0)]];
  const byJ=key==='congress'&&c.by_jurisdiction?`<div class="tablebox"><table><thead><tr><th>Jurisdiction</th><th>Discovered</th><th>Extracted</th><th>Queued</th><th>Error</th></tr></thead><tbody>${Object.entries(c.by_jurisdiction).map(([j,v])=>`<tr><td>${esc(j)}</td><td class="num">${fmt(v.discovered)}</td><td class="num">${fmt(v.extracted)}</td><td class="num">${fmt(v.pending)}</td><td class="num">${fmt(v.error)}</td></tr>`).join('')}</tbody></table></div>${m.jurisdiction_notes?.sedi?`<p class="sub">Canada SEDI: <span class="badge ${m.jurisdiction_notes.sedi.status==='reachable'?'ready':'error'}">${esc(m.jurisdiction_notes.sedi.status)}</span> ${esc(m.jurisdiction_notes.sedi.detail||'')}</p>`:''}${m.jurisdiction_notes?.tx?`<p class="sub">Texas: ${esc(m.jurisdiction_notes.tx)}</p>`:''}`:'';
  out+=`<article class="health-card"><div class="health-title"><h3>${{holdings:'Institutional holdings',congress:"Officials' disclosures",cot:'Futures positioning',banks:'Bank financials',npx:'Proxy votes',prices:'Price-based estimates (optional)'}[key]}</h3><span class="badge ${m.status==='ok'?'ready':'error'}">${esc(m.status||'Not collected')}</span></div><div class="health-facts">${facts.map(([label,value])=>`<div><strong>${typeof value==='number'?fmt(value):esc(value??'—')}</strong><span>${label}</span></div>`).join('')}</div>${byJ}<p class="sub">Last attempt ${esc(m.last_attempt||'—')} · Updated ${esc(m.updated_at||'—')}</p>${m.error?`<p class="error-text">${esc(m.error)}</p>`:''}<details><summary>Source scope and technical details</summary><p>${esc(m.coverage_note|| (typeof m.coverage==='string'?m.coverage:'See index coverage below'))}</p><pre>${esc(JSON.stringify({coverage:m.coverage,errors:m.errors||[]},null,2))}</pre></details></article>`;
 }
 return out+'</div>';
}
function bindDashboard(){
 for(const k of ['dtype','dstatus','hsort'])bind(k,k);
 if($('dq'))$('dq').onchange=e=>{state.dq=e.target.value;state.page=0;render()};
 document.querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>navigate(b.dataset.jump));
 document.querySelectorAll('[data-directory-kind]').forEach(b=>b.onclick=()=>{state.dtype=b.dataset.directoryKind;state.dq='';state.dstatus='';navigate('directory')});
 document.querySelectorAll('[data-open-kind]').forEach(b=>b.onclick=()=>{
  const kind=b.dataset.openKind,id=b.dataset.openId;
  if(kind==='holdings')state.manager=id;
  else if(kind==='congress'){state.creport=id;const r=data().modules.congress.reports.find(r=>r.report_id===id);state.person=r?.person;state.ckind=r?.report_type==='PTR'?'transaction':'asset'}
  else if(kind==='banks'){state.cert=id;state.date=''}
  else if(kind==='cot'){const r=data().modules.cot.series.find(r=>r.id===id);state.market=r.dataset+'|'+r.code;state.date='';state.from='';state.to=''}
  else if(kind==='npx'){state.filing=data().modules.npx.filings.find(f=>Number(f.cik)===Number(id))?.accession||'';state.query='';state.direction=''}
  navigate(kind);
 });
 if($('npx-more'))$('npx-more').onclick=()=>loadMoreVotes(data().modules.npx.filings.find(f=>f.accession===state.filing));
 document.querySelectorAll('[data-security]').forEach(b=>{b.onclick=()=>{state.security=b.dataset.security;render();$('security')?.scrollIntoView?.({block:'center',behavior:'smooth'})};b.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();b.onclick()}}});
}
function navigate(tab){state.tab=tab;state.page=0;document.querySelectorAll('nav button').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-pressed',String(b.dataset.tab===tab))});render()}
