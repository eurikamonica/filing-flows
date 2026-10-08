/* Integrated 13F and congressional disclosure views. No external JS dependencies. */
function positionChanges(prior,current){
 if(!prior?.complete||!current?.complete)return current?.positions.map(r=>({...r,status:'BASE',delta_shares:null,delta_pct:null,delta_weight_pp:null}))||[];
 const a=new Map(prior.positions.map(r=>[r.id,r])),b=new Map(current.positions.map(r=>[r.id,r]));
 return [...new Set([...a.keys(),...b.keys()])].map(id=>{const p=a.get(id),q=b.get(id),n=p?.shares||0,m=q?.shares||0;return {...(q||p),shares:m,value_usd:q?.value_usd||0,weight:q?.weight||0,delta_shares:m-n,delta_pct:n?(m/n-1)*100:null,delta_weight_pp:((q?.weight||0)-(p?.weight||0))*100,status:!p?'NEW':!q?'NOT DISCLOSED':m>n?'INCREASE':m<n?'DECREASE':'UNCHANGED'}});
}
function treemap(positions,total){
 const all=positions.filter(r=>r.value_usd>0).sort((a,b)=>b.value_usd-a.value_usd).slice(0,22),rest=total-all.reduce((s,r)=>s+r.value_usd,0);
 if(rest>0)all.push({issuer:'Other disclosed positions',value_usd:rest,id:''});
 if(!all.length)return empty('No positive disclosed values');let content='';
 function partition(items,x,y,w,h){
  if(items.length===1){const r=items[0],color=['#3658d4','#5774df','#768de5','#329896','#687aab'][all.indexOf(r)%5];content+=`<g data-security="${esc(r.id)}" tabindex="0" role="button" aria-label="${esc(r.issuer)}"><title>${esc(r.issuer)} · $${fmt(r.value_usd)} · ${pct(r.value_usd/total)}</title><rect x="${x+1}" y="${y+1}" width="${Math.max(0,w-2)}" height="${Math.max(0,h-2)}" fill="${color}" rx="5"/>${w>75&&h>40?`<text x="${x+8}" y="${y+22}" fill="white" font-size="11">${esc(r.issuer.slice(0,Math.max(1,Math.floor(w/7)-2)))}</text><text x="${x+8}" y="${y+39}" fill="#dfeee6" font-size="10">${pct(r.value_usd/total)}</text>`:''}</g>`;return}
  const sum=items.reduce((s,r)=>s+r.value_usd,0);let i=1,a=items[0].value_usd;while(i<items.length-1&&a<sum/2)a+=items[i++].value_usd;const f=a/sum;
  if(w>h){partition(items.slice(0,i),x,y,w*f,h);partition(items.slice(i),x+w*f,y,w*(1-f),h)}else{partition(items.slice(0,i),x,y,w,h*f);partition(items.slice(i),x,y+h*f,w,h*(1-f))}
 }
 partition(all,0,0,720,320);return `<svg class="plot" role="img" aria-label="Reported holdings by disclosed value" viewBox="0 0 720 320">${content}</svg>`;
}
function signedBars(rows){
 const top=[...rows].filter(r=>r.delta_weight_pp!=null).sort((a,b)=>Math.abs(b.delta_weight_pp)-Math.abs(a.delta_weight_pp)).slice(0,8),max=Math.max(.01,...top.map(r=>Math.abs(r.delta_weight_pp)));
 return top.map(r=>`<div class="delta-row"><div class="bar-label"><span title="${esc(r.issuer)}">${esc(r.issuer)}</span><b class="${r.delta_weight_pp>=0?'positive':'negative'}">${r.delta_weight_pp>=0?'+':''}${fmt(r.delta_weight_pp,2)} pp</b></div><div class="diverging-track"><span class="zero-line"></span><i style="left:${r.delta_weight_pp<0?50-Math.abs(r.delta_weight_pp)/max*50:50}%;width:${Math.abs(r.delta_weight_pp)/max*50}%;background:${r.delta_weight_pp>=0?'var(--green)':'var(--orange)'}"></i></div></div>`).join('')||empty('Select a valid baseline');
}
function holdings(){
 const m=moduleData(),managers=m.managers||[];
 let out=head('Institutional holdings','13F public positions at quarter-end. Filing updates are not real-time trades.','SEC / 13F')+coverageStrip('holdings');
 if(!managers.length)return out+empty('No 13F data yet. Run the holdings collector or choose demo.');
 state.manager=choose(state.manager,managers.map(x=>x.cik));const manager=managers.find(x=>x.cik===state.manager);if(!ensureShard(manager))return out+loading(manager);const snaps=manager.snapshots||[];
 out+=`<div class="toolbar">${field('manager','Manager / CIK',managers.map(x=>[x.cik,(x.label||x.name)+' · '+x.cik]),state.manager,true)}</div>`;
 if(!snaps.length)return out+empty('No supported holdings tables. A 13F-NT notice does not mean zero positions.');
 state.hperiod=choose(state.hperiod,snaps.map(s=>s.period).reverse());const current=snaps.find(s=>s.period===state.hperiod),prior=snaps.filter(s=>s.period<current.period).reverse();
 state.hbase=choose(state.hbase,prior.map(s=>s.period));const baseline=prior.find(s=>s.period===state.hbase);
 out+=`<div class="toolbar">${field('hperiod','Current report period',snaps.map(s=>s.period).reverse(),state.hperiod)}${field('hbase','Compare with earlier period',prior.map(s=>s.period),state.hbase)}${field('hasset','Security type',[['','All types'],['NONE','Equity / no Put-Call flag'],['PUT','Put'],['CALL','Call']],state.hasset||'')}</div>`;
 const changes=positionChanges(baseline,current),usable=current.complete&&baseline?.complete;
 const warnings=[manager.stale?'Refresh failed: last valid snapshot retained.':'',current.confidential?'Confidential positions were omitted.':'',...(current.warnings||[])].filter(Boolean).join(' ');
 out+=`<div class="explain">As of ${esc(current.period)} · Filing date ${esc(current.filed)} · Last successful collection ${esc(manager.last_success||'demo')}<br>${esc(warnings)} ${current.sources.map(s=>link(s.url,`${s.amendment} ${s.accession}`)).join(' / ')}<br>Changes compare disclosed quantities, not verified transactions. Splits, transfers and confidential treatment can affect comparisons.</div>`;
 out+=`<div class="metrics">${kpi('Disclosed value / USD','$'+compact(current.total_usd),'Not total assets under management')}${kpi('Security positions',fmt(current.positions.length),'CUSIP + class + option flag + quantity type')}${kpi('New / no longer disclosed',usable?changes.filter(x=>x.status==='NEW').length+' / '+changes.filter(x=>x.status==='NOT DISCLOSED').length:'—','Changes in disclosure, not trade execution')}${kpi('Increased / decreased',usable?changes.filter(x=>x.status==='INCREASE').length+' / '+changes.filter(x=>x.status==='DECREASE').length:'—','Quantity comparison')}</div>`;
 out+=`<div class="charts"><div class="panel"><h3>Reported position weights</h3><p class="sub">All disclosed types · hover for exact value</p>${treemap(current.positions,current.total_usd)}</div><div class="panel"><h3>Largest weight changes</h3><p class="sub">Percentage points · all disclosed types</p>${signedBars(changes)}</div></div>`;
 const securityMap=new Map();for(const snap of snaps)for(const position of snap.positions)if(!securityMap.has(position.id))securityMap.set(position.id,position);
 const secids=[...securityMap.keys()];state.security=choose(state.security,secids);
 const security=securityMap.get(state.security);
 out+=`<div class="toolbar">${field('security','Security history',secids.map(id=>{const r=securityMap.get(id);return[id,`${r.issuer} · ${r.cusip} · ${r.put_call} / ${r.share_type}`]}),state.security,true)}</div>`;
 out+=`<div class="charts"><div class="panel"><h3>Disclosed value history</h3>${lineChart(snaps.map(s=>({date:s.period,value:s.complete?s.total_usd:null})),'value','USD')}</div><div class="panel"><h3>Selected quantity history</h3><p class="sub">${esc(security?.share_type||'')} · not disclosed = gap, not zero</p>${lineChart(snaps.map(s=>({date:s.period,value:s.positions.find(p=>p.id===state.security)?.shares??null})),'value',security?.share_type||'')}</div></div>`;
 out+=`<div class="toolbar"><div class="field wide"><label for="hq">Issuer / CUSIP search</label><input id="hq" value="${esc(state.hq||'')}" placeholder="Issuer or CUSIP; Enter to apply"></div>${field('hstatus','Change filter',[['','All changes'],...['NEW','NOT DISCLOSED','INCREASE','DECREASE','UNCHANGED','BASE']],state.hstatus||'')}${field('hsort','Sort positions',[['value','Disclosed value'],['change','Largest weight change'],['issuer','Issuer A–Z']],state.hsort||'value')}</div>`;
 const rows=changes.filter(r=>(!state.hasset||r.put_call===state.hasset)&&(!state.hstatus||r.status===state.hstatus)&&(!state.hq||(r.issuer+' '+r.cusip).toLowerCase().includes(state.hq.toLowerCase()))).sort((a,b)=>state.hsort==='change'?Math.abs(b.delta_weight_pp||0)-Math.abs(a.delta_weight_pp||0):state.hsort==='issuer'?a.issuer.localeCompare(b.issuer):b.value_usd-a.value_usd);exported=rows;
 out+=`<div class="section-head"><h3>Disclosed positions and changes</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Issuer / CUSIP','Class / option / quantity type','Change','Quantity','Quantity change','Quantity change %','Value USD','Weight','Weight change pp'],rows.map(r=>[esc(r.issuer)+'<br>'+esc(r.cusip),esc(`${r.class} / ${r.put_call} / ${r.share_type}`),esc(r.status),fmt(r.shares,6),signed(r.delta_shares),r.delta_pct==null?'—':fmt(r.delta_pct,2)+'%',fmt(r.value_usd),pct(r.weight),fmt(r.delta_weight_pp,2)]));return out;
}
function amountLabel(r){return r.amount_max==null?'Over $'+fmt(r.amount_min-1):'$'+fmt(r.amount_min)+'–$'+fmt(r.amount_max)}
function intervalChart(rows){
 const picked=[...rows].sort((a,b)=>(b.amount_max??b.amount_min)-(a.amount_max??a.amount_min)).slice(0,12);
 if(!picked.length)return empty('No reviewed asset ranges in this selection. Open PDF / OCR to review source records.');
 const max=Math.max(1,...picked.map(r=>r.amount_max??r.amount_min*1.2));
 return `<div class="interval-list">${picked.map((r,i)=>`<div class="interval-row"><div class="asset-rank">${String(i+1).padStart(2,'0')}</div><div class="asset-name"><strong>${esc(r.asset)}</strong><small>${esc(r.owner||'Owner unspecified')}${r.ticker?' · '+esc(r.ticker):''}</small></div><div class="asset-interval"><div class="interval-track"><i style="left:${r.amount_min/max*100}%;width:${Math.max(.25,((r.amount_max??max)-r.amount_min)/max*100)}%" class="${r.amount_max==null?'open-ended':''}"></i></div><span>${esc(amountLabel(r))}${r.amount_max==null?' →':''}</span></div></div>`).join('')}<div class="interval-axis"><span>Disclosed value · linear scale</span><span>$0 — $${esc(compact(max))}</span></div></div>`;
}
function congress(){
 const m=moduleData(),reports=m.reports||[],records=m.records||[];
 let out=head('Congressional disclosures','Reviewed annual asset ranges and reported transactions. This is not a reconstructed current portfolio.','HOUSE + IMPORTS')+coverageStrip('congress');
 if(!reports.length)return out+empty('No reports yet. Collect the House watchlist or add PDF imports.');
 state.person=choose(state.person,uniq(reports.map(r=>r.person)));const pr=reports.filter(r=>r.person===state.person).sort((a,b)=>b.filed_date.localeCompare(a.filed_date));
 state.ckind=state.ckind||'asset';if(!pr.some(r=>r.report_id===state.creport))state.creport=(pr.find(r=>r.report_type===(state.ckind==='asset'?'Annual':'PTR'))||pr[0]).report_id;
 const report=pr.find(r=>r.report_id===state.creport);if(!ensureShard(report))return out+loading(report);
 out+=`<div class="toolbar">${field('person','Filer',uniq(reports.map(r=>r.person)),state.person,true)}${field('creport','Disclosure document',pr.map(r=>[r.report_id,`${r.filed_date} · ${r.report_type} · ${r.report_id}`]),state.creport,true)}${field('ckind','Reviewed records',[['asset','Disclosed asset ranges'],['transaction','Reported transactions']],state.ckind)}</div>`;
 out+=`<div class="explain">${esc(report.jurisdiction)} · ${esc(report.report_type)} · Filed ${esc(report.filed_date)} · ${link(report.source_url,'Official document ↗')}<br>${esc(m.coverage_note||'')}<br>Document status: ${esc(report.status)}${report.stale?' · STALE':''}. Only source-checked rows appear below; empty results mean no reviewed rows, not no assets.</div>`;
 const rows=records.filter(r=>r.report_id===state.creport&&r.kind===state.ckind),assets=rows.filter(r=>r.kind==='asset');
 const persons=reports.filter(r=>r.person===state.person);
 out+=`<div class="metrics">${kpi('Documents for this filer',persons.length,'Only the configured / imported coverage')}${kpi('Reviewed rows in this view',rows.length,'Partial excerpts, not a complete portfolio')}${kpi('Unreviewed candidates in report',(report.candidates||[]).filter(c=>!records.some(r=>r.id===c.id)).length,'See PDF / OCR review desk')}${kpi('Report filed',report.filed_date,'Transactions have separate event dates')}</div>`;
 out+=`<div class="panel"><h3>${state.ckind==='asset'?'Disclosed asset intervals':'Reported transaction timeline'}</h3><p class="sub">${state.ckind==='asset'?'No midpoint estimates; first 12 rows shown.':'Count of reviewed transactions by event date, not trade value.'}</p>${state.ckind==='asset'?intervalChart(assets):lineChart(Object.entries(rows.reduce((a,r)=>{a[r.transaction_date]=(a[r.transaction_date]||0)+1;return a},{})).sort().map(([date,value])=>({date,value})),'value','reviewed transactions')}</div>`;
 const oldReports=pr.filter(r=>r.report_type==='Annual'&&r.filed_date<report.filed_date);state.cbase=choose(state.cbase,oldReports.map(r=>r.report_id));
 if(state.ckind==='asset'&&report.report_type==='Annual'){
  out+=`<div class="toolbar">${field('cbase','Compare reviewed asset excerpts with earlier annual report',oldReports.map(r=>[r.report_id,r.filed_date+' · '+r.report_id]),state.cbase,true)}</div>`;
  const previous=records.filter(r=>r.report_id===state.cbase&&r.kind==='asset');
  if(previous.length&&assets.length){
   const id=r=>[r.asset,r.owner].join('|'),a=new Map(previous.map(r=>[id(r),r])),b=new Map(assets.map(r=>[id(r),r]));
   if(a.size!==previous.length||b.size!==assets.length)out+=`<div class="explain">Comparison withheld: duplicate asset/owner labels need distinct account or class identifiers in the reviewed records.</div>`;
   else out+=`<div class="explain">Comparison covers reviewed excerpts only. New/missing rows can reflect review coverage or disclosure changes; they are not purchase/sale confirmations.</div><div class="tablebox"><table><thead><tr><th>Asset / owner</th><th>Earlier disclosed range</th><th>Selected disclosed range</th></tr></thead><tbody>${uniq([...a.keys(),...b.keys()]).map(k=>`<tr><td>${esc(k)}</td><td>${a.has(k)?amountLabel(a.get(k)):'Not in reviewed excerpts'}</td><td>${b.has(k)?amountLabel(b.get(k)):'Not in reviewed excerpts'}</td></tr>`).join('')}</tbody></table></div>`;
  }
 }
 exported=rows;out+=`<div class="section-head"><h3>Reviewed source records</h3><button id="csv" class="action">Export CSV ↓</button></div>`+table(['Asset / ticker','Owner','Disclosed amount USD','Event / valuation date','Basis / transaction','Source / reviewer'],rows.map(r=>[esc(r.asset)+'<br>'+esc(r.ticker),esc(r.owner),esc(amountLabel(r)),esc(r.transaction_date||r.valuation_date||'See valuation basis'),esc(r.kind==='asset'?r.valuation_basis:r.transaction_type),link(r.source_url+'#page='+r.page,'Page '+r.page)+'<br>'+esc(r.reviewer)]));
 return out;
}
const reviewFields=['id','report_id','source_sha256','page','kind','asset','ticker','owner','transaction_type','transaction_date','amount_min','amount_max','valuation_date','valuation_basis','reviewer','reviewed_at','notes'];
const reviewDrafts={};
function draft(){if(!reviewDrafts[state.mode])reviewDrafts[state.mode]=new Map((data().modules.congress?.records||[]).map(r=>[r.id,{...r}]));return reviewDrafts[state.mode]}
function review(){
 const reports=data().modules.congress?.reports||[];let out=head('PDF / OCR review desk','Check the official page, correct fields, then export reviewed CSV for the next build. Edits remain in this browser session.','HUMAN REVIEW');
 if(!reports.length)return out+empty('Collect or import reports first.');
 state.rreport=choose(state.rreport,reports.map(r=>r.report_id));const report=reports.find(r=>r.report_id===state.rreport);if(!ensureShard(report))return out+loading(report);const candidates=report.candidates||[];state.candidate=choose(state.candidate,candidates.map(r=>r.id));const source=candidates.find(r=>r.id===state.candidate);
 out+=`<div class="toolbar">${field('rreport','Document',reports.map(r=>[r.report_id,`${r.person} · ${r.report_type} · ${r.filed_date}`]),state.rreport,true)}${field('candidate','Candidate interval',candidates.map((c,i)=>[c.id,`${i+1} · page ${c.page} · ${c.amount_text} · ${c.method}`]),state.candidate,true)}</div>`;
 out+=`<div class="explain">${link(report.source_url,'Open original PDF ↗')} · Extraction status ${esc(report.status)} · ${report.page_count||0} pages.<br>OCR confidence is a word-recognition score, not financial-field accuracy. Candidates may be income, liabilities or strike prices. Do not approve them as assets without checking the column and context.</div>`;
 if(!source)return out+empty('No amount-range candidates detected. Check the raw PDF and use the reviewed CSV template for manual entries.');
 const c=draft().get(source.id)||source;
 const input=(k,label,type='text')=>`<div class="field"><label for="r_${k}">${label}</label><input id="r_${k}" type="${type}" value="${esc(c[k]??'')}" /></div>`;
 out+=`<div class="panel"><h3>Page ${source.page} · ${esc(source.method)} · ${source.mean_word_confidence==null?'text layer':'mean OCR confidence '+fmt(source.mean_word_confidence,1)}</h3><pre style="white-space:pre-wrap;line-height:1.8;overflow-wrap:anywhere">${esc(source.excerpt)}</pre>${link(report.source_url+'#page='+source.page,'Check this source page ↗')}</div>`;
 out+=`<div class="toolbar">${field('r_kind','Record kind',[['unclassified','Unclassified — do not publish'],['asset','Disclosed asset'],['transaction','Transaction']],c.kind)}${input('asset','Asset name / class')}${input('ticker','Ticker (only if explicit / verified)')}${input('owner','Owner: Self / SP / JT / DC / original label')}</div><div class="toolbar">${input('amount_min','Amount lower bound USD','number')}${input('amount_max','Amount upper bound USD (blank = open-ended)','number')}${field('r_transaction_type','Transaction type',[['','Not a transaction'],['purchase','Purchase'],['sale','Sale'],['exchange','Exchange'],['other','Other']],c.transaction_type)}${input('transaction_date','Transaction date','date')}</div><div class="toolbar">${input('valuation_date','Valuation date if stated','date')}${input('valuation_basis','Valuation basis / reporting-period wording')}${input('reviewer','Reviewer')}${input('reviewed_at','Review date','date')}${input('notes','Notes / correction explanation')}</div><p id="review-message" role="status"></p><div class="toolbar"><button class="action" id="approve">Keep as reviewed in this session</button><button class="action" id="remove-review">Remove this reviewed row</button><button class="action" id="export-review">Export reviewed-disclosures.csv (${draft().size} rows)</button></div><div class="explain">Export preserves the existing reviewed records plus your session edits. Save it as config/reviewed-disclosures.csv, commit it to your repository, and run the collection workflow. The server validates the source hash and required fields. This page does not write to GitHub.</div>`;
 return out;
}
function bindExtensions(){
 for(const k of ['manager','hperiod','hbase','hasset','hstatus','security','person','creport','ckind','cbase','rreport','candidate'])bind(k,k);
 if($('ckind'))$('ckind').onchange=e=>{state.ckind=e.target.value;state.creport='';state.page=0;render()};
 if($('hq'))$('hq').onchange=e=>{state.hq=e.target.value;state.page=0;render()};
 if(state.tab!=='review')return;
 const reports=data().modules.congress?.reports||[],report=reports.find(r=>r.report_id===state.rreport),source=report?.candidates?.find(c=>c.id===state.candidate);
 if(!source)return;
 if($('r_reviewer')&&!$('r_reviewer').value)$('r_reviewer').value='Eurika';
 if($('r_reviewed_at')&&!$('r_reviewed_at').value)$('r_reviewed_at').value=new Date().toISOString().slice(0,10);
 $('approve').onclick=()=>{
  const rec={id:source.id,report_id:source.report_id,source_sha256:source.source_sha256,page:source.page};
  reviewFields.filter(k=>!Object.hasOwn(rec,k)).forEach(k=>rec[k]=$('r_'+k)?.value||'');
  if(!['asset','transaction'].includes(rec.kind)||!rec.asset.trim()||!rec.reviewer.trim()||!rec.reviewed_at||rec.amount_min===''){ $('review-message').textContent='Record kind, asset, lower bound, reviewer and review date are required.';return;}
  if(Number(rec.amount_min)<0||(rec.amount_max!==''&&Number(rec.amount_max)<Number(rec.amount_min))){$('review-message').textContent='Invalid amount interval.';return;}
  if(rec.kind==='asset'&&!rec.valuation_basis.trim()||rec.kind==='transaction'&&(!rec.transaction_date||!rec.transaction_type)){$('review-message').textContent='Assets require a valuation basis. Transactions require type and date.';return;}
  draft().set(rec.id,rec);render();$('review-message').textContent='Kept in this session. Export the CSV to persist your review.';
 };
 $('remove-review').onclick=()=>{draft().delete(source.id);render()};
 $('export-review').onclick=()=>{const content='\ufeff'+[reviewFields.map(csvCell).join(','),...[...draft().values()].map(r=>reviewFields.map(k=>csvCell(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=state.mode==='demo'?'DEMO-reviewed-disclosures.csv':'reviewed-disclosures.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)};
}
