/* Live market catalog. Public branch is independent of the slower site build. */
(function(root){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let configPromise,timer,activeGeneration;
const labels={parsed:'Financial data parsed',needs_review:'Source tables · mapping required',queued:'Document queued',download_failed:'Download retry pending',document_only:'Lifecycle document',ipo_language_identified:'IPO language identified',resale_language_identified:'Resale language identified',registration_unclassified:'Registration · unclassified',unclassified:'Unclassified'};
function url(s){try{const u=new URL(s);return u.protocol==='https:'&&u.hostname==='www.sec.gov'&&!u.username&&!u.password?u.href:'';}catch(_){return '';}}
function link(r){const u=url(r.source_url||r.index_url);return u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">SEC source ↗</a>`:'';}
async function json(path){const c=new AbortController(),t=setTimeout(()=>c.abort(),12000);try{const r=await fetch(path,{cache:'no-cache',signal:c.signal});if(!r.ok)throw Error('HTTP '+r.status);return await r.json();}finally{clearTimeout(t);}}
async function config(){if(!configPromise)configPromise=json('data/ipo/source.json').catch(()=>({}));return configPromise;}
async function load(path){
 if(!/^(?:index|status|\d+|filings\/\d{10}-\d{2}-\d{6})\.json$/.test(path))throw Error('Invalid IPO path');
 const c=await config();let remoteError=false;
 if(/^https:\/\/raw\.githubusercontent\.com\/[\w.-]+\/[\w.-]+\/ipo-data\/public\/$/.test(c.live_base||'')){
   try{const d=await json(c.live_base+path+'?v='+Math.floor(Date.now()/60000));return {...d,_transport:'live_branch'};}catch(_){remoteError=true;}
 }
 const d=await json('data/ipo/'+path);return {...d,_transport:remoteError?'cached_fallback':'site_snapshot'};
}
function health(s,transport){
 const stamp=s.feed_last_success, age=stamp?(Date.now()-Date.parse(stamp))/60000:Infinity;
 const stale=!Number.isFinite(age)||age>20;
 return `<div class="qi-notice" role="status"><strong>${stale?'Monitor stale / not yet running':s.feed_state==='ok'?'Latest feed pass completed':'Discovery incomplete'}</strong> · Target: every 5 minutes; SEC and scheduler delays apply.<br>Last attempt: ${esc(s.last_attempt||'Not run')} · Last successful feed pass: ${esc(stamp||'Not run')}<br>Snapshot generated: ${esc(s.generated_at||'Unknown')} · ${transport==='cached_fallback'?'Live source unavailable; showing site snapshot.':transport==='live_branch'?'Live public data branch':'Site snapshot'}</div>`;
}
function watch(app,here,generation){
 activeGeneration=generation;clearTimeout(timer);const cycle=async()=>{
  if(!here()||!app.isConnected)return;
  if(document.visibilityState!=='hidden')try{
    const s=await load('status.json');if(!here())return;
    app.querySelector('[data-ipo-network]')?.remove();
    if(!activeGeneration)activeGeneration=s.generation;
    const healthBox=app.querySelector('[data-ipo-health]');if(healthBox)healthBox.innerHTML=health(s,s._transport);
    if(activeGeneration&&s.generation!==activeGeneration){
      let banner=app.querySelector('[data-ipo-update]');if(!banner){banner=document.createElement('p');banner.className='qi-notice';banner.dataset.ipoUpdate='1';app.prepend(banner);}
      banner.innerHTML='New filings or analysis results are available. <button type="button">Load updates</button>';
      banner.querySelector('button').onclick=()=>root.dispatchEvent(new Event('hashchange'));
    }
  }catch(_){
    if(here()&&!app.querySelector('[data-ipo-network]')){const notice=document.createElement('p');notice.dataset.ipoNetwork='1';notice.className='qi-notice';notice.textContent='Live update check unavailable. The displayed snapshot is retained; monitor freshness is unverified.';app.prepend(notice);}
  }
  if(here())timer=setTimeout(cycle,60000);
 };timer=setTimeout(cycle,60000);
}
function index(app,d,here){
 activeGeneration=d.generation;
 const rows=d.companies||[],s=d.status||{};
 app.innerHTML=`<section class="section qi-section"><h1>IPO & registration monitor</h1><p>All issuers in SEC public registration and prospectus feeds. S-1/F-1 filings include resales and other offerings; a registration is not proof of an IPO or listing.</p><div data-ipo-health>${health(s,d._transport)}</div><div class="qi-cards"><div class="qi-card"><span>Issuers discovered</span><strong>${rows.length}</strong></div><div class="qi-card"><span>Filings discovered</span><strong>${s.filing_count??'—'}</strong></div><div class="qi-card"><span>History quarters checked</span><strong>${s.quarters_completed??0}/${s.quarters_total??'—'}</strong><small>From ${esc(s.coverage_start||'2024-01-01')}</small></div><div class="qi-card"><span>Queued / retrying</span><strong>${(s.states?.queued||0)+(s.states?.download_failed||0)}</strong></div></div><div class="ipo-controls"><label>Search company or CIK <input type="search" id="ipo-search" placeholder="Name or CIK"></label><label>Analysis <select id="ipo-state"><option value="">All states</option>${['parsed','needs_review','queued','download_failed'].map(x=>`<option value="${x}">${labels[x]}</option>`).join('')}</select></label><label>Offering <select id="ipo-kind"><option value="">All registrations</option>${['ipo_language_identified','resale_language_identified','registration_unclassified'].map(x=>`<option value="${x}">${labels[x]}</option>`).join('')}</select></label><label>Form <select id="ipo-form"><option value="">All forms</option>${[...new Set(rows.map(r=>r.form))].sort().map(x=>`<option>${esc(x)}</option>`).join('')}</select></label></div><p id="ipo-count" aria-live="polite"></p><div class="qi-table" id="ipo-results"></div><button id="ipo-more" type="button">Show more</button><details><summary>Coverage, failures and monitoring sources</summary><p>${esc(s.scope||d.scope)} Publicly released DRS files are included; confidential drafts cannot be observed.</p><p>Unfinished quarters: ${esc((s.backfill_pending||[]).join(', ')||'None recorded')}</p>${(s.sources||[]).filter(r=>r.state!=='ok').map(r=>`<p>${esc(r.kind)} · ${esc(r.period)} · ${esc(r.state)} · ${esc(r.error)}</p>`).join('')||'<p>No recorded source failures.</p>'}</details></section>`;
 let limit=60;
 function draw(){const term=app.querySelector('#ipo-search').value.trim().toLowerCase(),state=app.querySelector('#ipo-state').value,kind=app.querySelector('#ipo-kind').value,form=app.querySelector('#ipo-form').value;
 const selected=rows.filter(r=>(!term||`${r.name} ${r.cik}`.toLowerCase().includes(term))&&(!state||r.state===state)&&(!kind||r.classification===kind)&&(!form||r.form===form));
 app.querySelector('#ipo-count').textContent=`${selected.length} issuers match · showing ${Math.min(limit,selected.length)}`;
 app.querySelector('#ipo-results').innerHTML=`<table><thead><tr><th>Company</th><th>Latest filing</th><th>Offering language</th><th>Analysis</th><th>Documents</th></tr></thead><tbody>${selected.slice(0,limit).map(r=>`<tr><td><a href="#ipo-${Number(r.cik)}">${esc(r.name)}</a><br><small>CIK ${Number(r.cik)}</small></td><td>${esc(r.form)}<br>${esc(r.filed)}</td><td>${esc(labels[r.classification]||r.classification)}</td><td>${esc(labels[r.state]||r.state)}${r.analysis_accession&&r.analysis_accession!==r.accession?'<br><small>Prior parsed financials retained</small>':''}</td><td>${r.filing_count||1} · ${link(r)}</td></tr>`).join('')}</tbody></table>`;
 app.querySelector('#ipo-more').hidden=selected.length<=limit;
 }
 for(const id of ['ipo-search','ipo-state','ipo-kind','ipo-form'])app.querySelector('#'+id).addEventListener('input',()=>{limit=60;draw();});
 app.querySelector('#ipo-more').onclick=()=>{limit+=60;draw();};draw();watch(app,here,d.generation);
}
function detail(d){
 const latest=d.latest_discovered||d,rows=d.filings||[];
 return `<div class="qi-notice"><strong>${esc(labels[latest.classification]||latest.classification||'Public filing')}</strong> · ${esc(labels[latest.state]||d.analysis_state||'Snapshot')}<br>Latest discovered: ${esc(latest.form)} ${esc(latest.filed)} · ${esc(latest.accession)}<br>Selected analysis: ${esc(d.form)} ${esc(d.filed)} · ${esc(d.accession)}${latest.accession!==d.accession?'<br>These figures belong to an earlier or explicitly selected filing, not the latest amendment.':''}${d.lifecycle?'<br>Same SEC file-number lifecycle: '+esc(d.lifecycle)+' (not proof of exchange listing).':''}</div><details open><summary>Filing and amendment history (${rows.length})</summary><div class="qi-table"><table><thead><tr><th>Filed / accepted</th><th>Form / accession</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.filed)}<br><small>${esc(r.accepted||'Acceptance time not read')}</small></td><td>${esc(r.form)}<br>${esc(r.accession)}<br><small>SEC file ${esc(r.file_number||'unknown')}</small></td><td>${esc(labels[r.state]||r.state)}</td><td>${link(r)}${['parsed','needs_review','document_only'].includes(r.state)?` · <a href="#ipo-${Number(r.cik)}/${esc(r.accession)}">Inspect version</a>`:''}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function sourceAnalysis(d){
 return `<h2>Prospectus analysis & source evidence</h2>${!(d.periods||[]).length?'<p class="qi-notice">Financial values are not yet mapped with reliable period and unit evidence. Review the source sections/tables below; no financial figures or Sankey flows are invented.</p>':''}${d.parse_error?`<p class="muted">Mapping status: ${esc(d.parse_error)}</p>`:''}${(d.sections||[]).map(s=>`<details><summary>${esc(s.title)}</summary><p>${esc(s.excerpt)}</p><p class="muted">Source excerpt; not an automated risk conclusion. ${link(d)}</p></details>`).join('')}${(d.source_tables||[]).map(t=>`<details><summary>Financial source table ${t.table_index+1} · mapping requires review</summary><p>${esc(t.note)}</p><div class="qi-table"><table><tbody>${t.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${link(d)}</details>`).join('')}`;
}
root.FFIPOMarket={load,index,detail,sourceAnalysis,watch,health};
})(typeof window!=='undefined'?window:globalThis);
