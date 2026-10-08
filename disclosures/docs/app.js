'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:d});
const pct=(v,d=1)=>v==null?'—':fmt(v*100,d)+'%';
const signed=v=>v==null?'—':(v>0?'+':'')+fmt(v);
const compact=v=>v==null?'—':Math.abs(v)>=1e9?fmt(v/1e9,2)+'B':Math.abs(v)>=1e6?fmt(v/1e6,2)+'M':Math.abs(v)>=1e3?fmt(v/1e3,1)+'K':fmt(v,1);
const link=(url,label='Source ↗')=>/^https:\/\//.test(url||'')?`<a target="_blank" rel="noopener" href="${esc(url)}">${esc(label)}</a>`:'—';
const uniq=a=>[...new Set(a)];
const state={tab:'holdings',mode:'official',page:0,market:'',group:'',cert:'',filing:'',metric:'assets',date:'',base:'',from:'',to:'',query:'',direction:''};
let exported=[];
const data=()=>state.mode==='demo'?(window.DISCLOSURE_DEMO||{modules:{}}):(window.DISCLOSURE_LIVE||{modules:{}});
const moduleData=()=>data().modules[state.tab==='review'?'congress':state.tab==='directory'?'holdings':state.tab]||{};
function options(items,value){return items.map(x=>{const [v,l]=Array.isArray(x)?x:[x,x];return `<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`}).join('')}
function choose(current,values){return values.includes(String(current))?String(current):values[0]||''}
function field(id,label,items,value,wide=false){return `<div class="field ${wide?'wide':''}"><label for="${id}">${label}</label><select id="${id}">${options(items,value)}</select></div>`}
function kpi(label,value,caption=''){return `<div class="metric"><label>${esc(label)}</label><strong>${esc(value)}</strong><small>${esc(caption)}</small></div>`}
function head(title,subtitle,tag){return `<div class="section-head"><div><h2>${title}</h2><p class="sub">${subtitle}</p></div><span class="tag">${tag}</span></div>`}
function empty(text){return `<div class="empty">${esc(text)}</div>`}
function bind(id,key){if($(id))$(id).onchange=e=>{state[key]=e.target.value;state.page=0;render()}}
function baseRender(){
 const d=data(),m=moduleData();
 $('buildtime').textContent='Snapshot built: '+(d.generated_at||'Not generated');
 $('notice').className=state.mode==='demo'||['error','partial'].includes(m.status)?'warn':'';
 $('notice').textContent=state.mode==='demo'?'DEMO: All figures in this mode are fictional. Use only to explore the interface.':
   state.tab==='status'?'Sources run independently. Errors retain the previous valid data and never substitute demo figures.':
   `Official snapshot · Status ${m.status||'Not collected'} · Last success/partial completion ${m.updated_at||'—'} · Last attempt ${m.last_attempt||'—'}${m.error?' · '+m.error:''}`;
}
function lineChart(rows,key,unit){
 if(!rows.length)return empty('No data in this date range');
 const vals=rows.map(r=>r[key]).filter(v=>v!=null&&Number.isFinite(v));
 if(!vals.length)return empty('No valid values for this metric');
 const W=720,H=290,L=78,R=20,T=24,B=40;
 let lo=Math.min(0,...vals),hi=Math.max(0,...vals);if(lo===hi)hi=lo+1;
 const y=v=>T+(hi-v)/(hi-lo)*(H-T-B),x=i=>L+i/Math.max(rows.length-1,1)*(W-L-R);
 let s=`<svg class="plot" role="img" aria-label="${esc(unit)} trend; exact values are in the table" viewBox="0 0 ${W} ${H}">`;
 for(let i=0;i<=4;i++){let v=lo+(hi-lo)*i/4;s+=`<line class="gridline" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-10}" y="${y(v)+4}" text-anchor="end">${esc(compact(v))}</text>`}
 let path='',gap=true;
 rows.forEach((r,i)=>{if(r[key]==null){gap=true;return}path+=(gap?'M':'L')+x(i)+','+y(r[key])+' ';gap=false});
 s+=`<path class="chartline" d="${path}"/>`;
 rows.forEach((r,i)=>{if(r[key]!=null)s+=`<circle cx="${x(i)}" cy="${y(r[key])}" r="3.4" fill="var(--mk-profit)"><title>${esc(r.date)} · ${esc(fmt(r[key],2))} ${esc(unit)}</title></circle>`});
 [0,Math.floor((rows.length-1)/2),rows.length-1].filter((v,i,a)=>a.indexOf(v)===i).forEach(i=>s+=`<text class="axis" x="${x(i)}" y="${H-12}" text-anchor="${i===0?'start':i===rows.length-1?'end':'middle'}">${esc(rows[i].date)}</text>`);
 return s+'</svg>';
}
function bars(items,caption){
 const max=Math.max(1,...items.map(x=>Math.abs(x.value??0)));
 return items.map(x=>`<div class="bar-row"><div class="bar-label"><span>${esc(x.label)}</span><span>${esc(fmt(x.value,2))}${caption?' '+esc(caption):''}</span></div><div class="bar-track"><div class="bar-fill" style="width:${x.value==null?0:Math.abs(x.value)/max*100}%;background:${x.color||'var(--mk-profit)'}"></div></div></div>`).join('');
}
function table(headers,rows){
 const size=25,start=state.page*size,total=rows.length;
 if(start>=total)state.page=0;
 return `<div class="tablebox"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(state.page*size,state.page*size+size).map(c=>`<tr>${c.map((v,i)=>`<td class="${i?'num':''}">${v}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${headers.length}">No matching records</td></tr>`}</tbody></table></div><div class="pager"><span>${total} rows · ${state.page+1}/${Math.max(1,Math.ceil(total/size))} pages</span><button class="action" id="prev" ${state.page===0?'disabled':''}>Previous</button><button class="action" id="next" ${(state.page+1)*size>=total?'disabled':''}>Next</button></div>`;
}
function actions(){
 if($('prev'))$('prev').onclick=()=>{state.page--;render()};
 if($('next'))$('next').onclick=()=>{state.page++;render()};
 if($('csv'))$('csv').onclick=downloadCSV;
}
function dates(){return `<div class="field"><label for="from">From date</label><input id="from" type="date" value="${esc(state.from)}"></div><div class="field"><label for="to">To date</label><input id="to" type="date" value="${esc(state.to)}"></div>`}
function filteredDates(rows){return rows.filter(r=>(!state.from||r.date>=state.from)&&(!state.to||r.date<=state.to))}
function cot(){
 let all=moduleData().rows||[];const series=moduleData().series||[];
 let out=head('Futures positioning','Futures only. Net = long contracts minus short contracts. Classification families differ.','CFTC / WEEKLY')+coverageStrip('cot');
 if(series.length){state.market=choose(state.market,series.map(r=>r.dataset+'|'+r.code));const active=series.find(r=>r.dataset+'|'+r.code===state.market);if(!ensureShard(active))return out+loading(active);all=active.rows||[]}
 if(!all.length)return out+empty('No COT data yet. Run the collector or choose fictional demo.');
 const markets=series.length?series.map(r=>r.dataset+'|'+r.code):uniq(all.map(r=>r.dataset+'|'+r.code));state.market=choose(state.market,markets);
 const r=all.filter(x=>x.dataset+'|'+x.code===state.market),groups=uniq(r.map(x=>x.group));state.group=choose(state.group,groups);
 out+=`<div class="toolbar">${field('market','Market / contract code',markets.map(v=>[v,(series.find(r=>r.dataset+'|'+r.code===v)?.name||all.find(r=>r.dataset+'|'+r.code===v)?.market)+' · '+v.split('|')[1]]),state.market,true)}${field('group','Trader category',groups,state.group)}${dates()}</div>`;
 const rows=filteredDates(r.filter(x=>x.group===state.group)).sort((a,b)=>a.date.localeCompare(b.date));
 const days=rows.map(x=>x.date).reverse();state.date=choose(state.date,days);
 out+=`<div class="toolbar">${field('asof','Report date (not publication date)',days,state.date)}</div>`;
 const last=rows.find(x=>x.date===state.date);
 if(!last)return out+empty('No observations in this range. Adjust the dates.');
 out+=`<div class="metrics">${kpi('Net position / contracts',fmt(last.net),state.group)}${kpi('Weekly net change / contracts',signed(last.weekly_change),'Only for reports exactly seven days apart')}${kpi('Market open interest',fmt(last.open_interest),last.date)}${kpi('52-observation net-position index',fmt(last.index_52_observations,1),'0–100; requires 52 observations and nonzero range')}</div>`;
 out+=`<div class="charts"><div class="panel"><h3>Net position history</h3><p class="sub">${esc(state.group)} · Contracts, not dollars</p>${lineChart(rows,'net','contracts')}</div><div class="panel"><h3>Long and short</h3><p class="sub">${esc(last.date)} · ${esc(state.group)}</p>${bars([{label:'LONG',value:last.long},{label:'SHORT',value:last.short,color:'var(--mk-cost)'}],'contracts')}<div class="explain">Net excludes the separate spreading column. The index is a historical range position, not a percentile or trading signal.</div>${link(last.source_url)}</div></div>`;
 out+=`<div class="section-head"><div><h3>History</h3><p class="sub">Export all rows for the selected market, category and date range</p></div><button class="action" id="csv">Export CSV ↓</button></div>`;
 exported=rows;
 out+=table(['Report period','Long','Short','Net position','Weekly change','52-observation index'],[...rows].reverse().map(x=>[esc(x.date),fmt(x.long),fmt(x.short),fmt(x.net),signed(x.weekly_change),fmt(x.index_52_observations,1)]));
 return out;
}
const BANK_METRICS={assets:'Assets',deposits:'Deposits',loans_net:'Net loans',equity:'Equity',net_income_quarter:'Quarter net income',net_income_ytd:'Net income YTD'};
function banks(){
 let all=moduleData().rows||[];const series=moduleData().series||[];let out=head('Quarterly bank financials','BankFind metrics. Amounts in USD thousands. Bank entities differ from listed holding companies.','FDIC / QUARTERLY')+coverageStrip('banks');
 if(series.length){state.cert=choose(state.cert,series.map(r=>String(r.cert)));const active=series.find(r=>String(r.cert)===state.cert);if(!ensureShard(active))return out+loading(active);all=active.rows||[]}
 if(!all.length)return out+empty('No bank data yet. Run the collector or choose fictional demo.');
 const certs=series.length?series.map(r=>String(r.cert)):uniq(all.map(r=>String(r.cert)));state.cert=choose(state.cert,certs);
 const rows=all.filter(x=>String(x.cert)===state.cert).sort((a,b)=>a.date.localeCompare(b.date)),days=rows.map(x=>x.date).reverse();
 state.date=choose(state.date,days);state.base=choose(state.base,days.filter(x=>x<state.date));
 out+=`<div class="toolbar">${field('cert','Bank / FDIC CERT',certs.map(v=>[v,(series.find(r=>String(r.cert)===v)?.name||all.find(r=>String(r.cert)===v)?.name)+' · '+v]),state.cert,true)}${field('metric','History metric',Object.entries(BANK_METRICS),state.metric)}</div><div class="toolbar">${field('asof','Current quarter',days,state.date)}${field('base','Comparison quarter (earlier than current)',days.filter(x=>x<state.date),state.base)}</div>`;
 const last=rows.find(x=>x.date===state.date),base=rows.find(x=>x.date===state.base);
 const change=(k)=>last[k]!=null&&base?.[k]!=null&&base[k]!==0?pct((last[k]-base[k])/Math.abs(base[k])):'—';
 out+=`<div class="metrics">${kpi('Assets / USD thousands',compact(last.assets),'Change vs baseline '+change('assets'))}${kpi('Deposits / USD thousands',compact(last.deposits),'Change vs baseline '+change('deposits'))}${kpi('Quarter net income / USD thousands',compact(last.net_income_quarter),'Derived from same-year YTD values')}${kpi('Net loans / deposits',pct(last.loan_deposit_ratio),'Net-loan basis, not a capital adequacy ratio')}</div>`;
 out+=`<div class="charts"><div class="panel"><h3>${BANK_METRICS[state.metric]} history</h3><p class="sub">USD thousands. Missing values remain blank.</p>${lineChart(rows,state.metric,'USD thousands')}</div><div class="panel"><h3>Quarter-end balances</h3><p class="sub">${esc(last.date)} · Shown separately, not added together</p>${bars(['assets','deposits','loans_net','equity'].map(k=>({label:BANK_METRICS[k],value:last[k]})),'USD thousands')}${link(last.source_url)}</div></div>`;
 out+=`<div class="explain">NETINC is year-to-date: Q1 = Q1 YTD; Q2 = Q2 YTD − Q1 YTD, and so on. Missing preceding quarters remain unknown. Mergers and accounting changes affect comparability. Assets, deposits and loans are quarter-end balances.</div>`;
 out+=`<h3>Period comparison · ${esc(state.base||'No baseline')} → ${esc(state.date)}</h3><div class="tablebox"><table><thead><tr><th>Metric / USD thousands</th><th>Baseline</th><th>Current</th><th>Change</th><th>Change % (absolute baseline denominator)</th></tr></thead><tbody>${Object.keys(BANK_METRICS).map(k=>`<tr><td>${BANK_METRICS[k]}</td><td>${fmt(base?.[k])}</td><td>${fmt(last[k])}</td><td>${signed(last[k]!=null&&base?.[k]!=null?last[k]-base[k]:null)}</td><td>${change(k)}</td></tr>`).join('')}</tbody></table></div>`;
 exported=rows;
 out+=`<div class="section-head"><h3>Quarterly history</h3><button id="csv" class="action">Export CSV ↓</button></div>`+table(['Report period','Assets','Deposits','Net loans','Equity','Net income YTD','Quarter net income'],[...rows].reverse().map(r=>[esc(r.date),fmt(r.assets),fmt(r.deposits),fmt(r.loans_net),fmt(r.equity),fmt(r.net_income_ytd),fmt(r.net_income_quarter)]));
 return out;
}
function npx(){
 const all=moduleData().filings||[];let out=head('Fund and manager proxy votes','Analyze one filing at a time. Voting shares are not current holdings. Do not add shares across proposals.','SEC / ANNUAL')+coverageStrip('npx');
 if(!all.length)return out+empty('No N-PX filings yet. Run the collector or choose fictional demo.');
 const files=[...all].sort((a,b)=>(b.filing_date+b.accession).localeCompare(a.filing_date+a.accession));state.filing=choose(state.filing,files.map(f=>f.accession));
 const f=files.find(x=>x.accession===state.filing);if(!ensureShard(f))return out+loading(f);
 out+=`<div class="toolbar">${field('filing','Filer / filing / original or amendment',files.map(x=>[x.accession,`${x.filer} · ${x.filing_date} · ${x.form} · ${x.accession}`]),state.filing,true)}</div>`;
 out+=`<div class="explain">Report period: ${esc(f.report_date||'—')} · Filed: ${esc(f.filing_date)} · Parse status: ${esc(f.parse_status)} · ${link(f.source_url,'SEC filing index ↗')}<br>${esc(f.coverage_note||'')}${f.is_amendment?'<br><b>Amendment: only this document is shown. It is neither assumed to replace all original records nor added to them.</b>':''}${f.refresh_error?'<br>Refresh failed: '+esc(f.refresh_error):''}</div>`;
 if(f.vote_chunks)out+=`<div class="coverage-strip"><strong>${fmt(f.votes.length)} / ${fmt(f.vote_count)}</strong><span>vote rows loaded · search, charts and CSV use loaded rows</span><button class="action" id="npx-more" ${f._loadingMore||f._loaded_chunks>=f.vote_chunks.length?'disabled':''}>${f._loadingMore?'Loading…':'Load next 1,000 rows'}</button>${f._chunkError?`<span class="error-text">${esc(f._chunkError)}</span>`:''}</div>`;
 if(f.cover_fields)out+=`<details><summary>Report type, confidentiality and filer notes</summary><p>Report type: ${esc(f.cover_fields.reportType)}<br>Registrant type: ${esc(f.cover_fields.registrantType)}<br>Confidential treatment: ${esc(f.cover_fields.confidentialTreatment)}<br>Amendment type: ${esc(f.cover_fields.amendmentType)}<br>${esc(f.cover_fields.explanatoryNotes)}</p></details>`;
 out+=`<div class="toolbar"><div class="field wide"><label for="query">Issuer / CUSIP / proposal search (Enter to apply)</label><input id="query" value="${esc(state.query)}" placeholder="Issuer, security identifier or proposal keyword"></div>${field('direction','Vote direction',[['','All directions'],['FOR','FOR'],['AGAINST','AGAINST'],['ABSTAIN','ABSTAIN'],['WITHHOLD','WITHHOLD'],['1 YEAR','1 YEAR'],['2 YEARS','2 YEARS'],['3 YEARS','3 YEARS']],state.direction)}</div>`;
 const query=state.query.trim().toLowerCase();
 const rows=(f.votes||[]).filter(r=>(!query||[r.issuer,r.cusip,r.isin,r.description].join(' ').toLowerCase().includes(query))&&(!state.direction||r.votes.some(v=>v.how===state.direction)));
 const votes=rows.flatMap(r=>r.votes),counts={};votes.forEach(v=>counts[v.how||'Unspecified']=(counts[v.how||'Unspecified']||0)+1);
 const opposing=votes.filter(v=>v.management_alignment==='AGAINST').length;
 const comparable=votes.filter(v=>['FOR','AGAINST'].includes(v.management_alignment)).length;
 out+=`<div class="metrics">${kpi('Proposals / table rows',fmt(rows.length),'Rows may be split across series or managers')}${kpi('Issuer identifiers',fmt(uniq(rows.map(r=>r.cusip||r.isin||r.issuer)).length),'Deduplicated by CUSIP / ISIN / name')}${kpi('Vote segments',fmt(votes.length),'Split votes produce multiple segments')}${kpi('Against management / classified segments',comparable?pct(opposing/comparable):'—',`${opposing} / ${comparable} segments; not share-weighted`)}</div>`;
 out+=`<div class="charts"><div class="panel"><h3>Vote direction distribution</h3><p class="sub">Loaded vote segments in filtered proposals; not a share-weighted distribution</p>${bars(Object.entries(counts).map(([label,value])=>({label,value,color:label==='AGAINST'?'var(--mk-cost)':'var(--mk-profit)'})),'segments')||empty('No vote segments to summarize')}</div><div class="panel"><h3>How to read this</h3><div class="explain">FOR means a vote for the proposal. Management alignment uses a separate field; do not infer it from FOR/AGAINST.<br><br>Managers and registered funds have different N-PX coverage. Loaned shares are separate. Series IDs, manager references and original fields are retained in CSV.</div></div></div>`;
 exported=rows.map(r=>({...r,accession:f.accession,filer:f.filer,report_date:f.report_date,filing_date:f.filing_date}));
 out+=`<div class="section-head"><h3>Proposals and vote details</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Issuer / identifier','Meeting date','Proposal','Vote / shares / management alignment','Total voted shares','Loaned shares not recalled','Source'],rows.map(r=>[`${esc(r.issuer)}<br><span class="muted">${esc(r.cusip||r.isin)}</span>`,esc(r.meeting_date),`<span style="white-space:normal;display:block;min-width:220px;max-width:430px;line-height:1.7">${esc(r.description)}</span>`,r.votes.map(v=>`<span class="pill">${esc(v.how)} · ${fmt(v.shares,6)} · ${esc(v.management_alignment||'Unspecified')}</span>`).join('<br>')||'No vote segments',fmt(r.shares_voted,6),fmt(r.shares_on_loan,6),link(r.source_url,'XML ↗')]));
 return out;
}
function status(){return health()}
function render(){
 baseRender();exported=[];
 $('workspace').innerHTML=({cot,banks,npx,status,holdings,congress,review,directory}[state.tab])();
 bind('market','market');bind('group','group');bind('from','from');bind('to','to');bind('asof','date');bind('cert','cert');bind('metric','metric');bind('base','base');bind('filing','filing');bind('direction','direction');
 if($('query')){$('query').onchange=e=>{state.query=e.target.value;state.page=0;render()};$('query').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 actions();
 bindExtensions();
 bindDashboard();
}
function csvCell(v){let s=typeof v==='object'&&v!==null?JSON.stringify(v):String(v??'');if(/^[=+@\t\r]/.test(s)||(/^[-]/.test(s)&&!/^[-]\d+(\.\d+)?$/.test(s)))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'}
function downloadCSV(){if(!exported.length)return;const keys=uniq(exported.flatMap(Object.keys));const csv='\ufeff'+[keys.map(csvCell).join(','),...exported.map(r=>keys.map(k=>csvCell(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`disclosure-${state.tab}-${state.mode}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)}
$('mode').onchange=e=>{state.mode=e.target.value;state.page=0;state.date='';state.filing='';render()};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;state.page=0;state.date='';document.querySelectorAll('nav button').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b))});render()});
render();
