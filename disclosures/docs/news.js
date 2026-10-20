/* 4.7 news views: 8-K events (every 8-K, classified: deals, CEO / CFO changes, restatements, guidance raised or lowered …)
   and News (PR Newswire, FDA and SEC releases matched to tickers: headline, time, link — no body text).
   Data: data/market/{events8k,news}.json, built by app/events8k.py and app/news.py; loaded on first use (marketGate,
   market.js). Each row has an Owner-only ✦ X (xpost.js). No dependencies. */
const TOPIC_TONE={bankruptcy:'error',restatement:'error',delisting:'error',cyber:'error',impairment:'error',control:'pending',deal:'ready',
 ceo:'pending',cfo:'pending',fda:'ready',offering:'pending',buyback:'ready',dividend:'ready',contract:'ready',guidance:'pending'};
const hm=s=>s&&s.length>=16?s.slice(11,16)+' ET':'';
const TOPIC_SHORT={deal:'M&A',ceo:'CEO change',cfo:'CFO change',restatement:'restatement',cyber:'cyber incident',delisting:'delisting notice',
 bankruptcy:'bankruptcy',buyback:'buyback',dividend:'dividend',offering:'offering',debt:'new debt',restructuring:'restructuring',
 impairment:'impairment',auditor:'auditor change',director:'board change',fda:'FDA',contract:'contract award',guidance:'guidance',control:'change in control',vote:'vote'};
function topicBadges(r,T){
 const b=(r.topics||[]).slice(0,3).map(t=>{const g=t==='guidance'&&r.guidance?`guidance ${r.guidance}`:(T[t]||t);
  const tone=t==='guidance'?(r.guidance==='raised'?'ready':r.guidance==='lowered'||r.guidance==='withdrawn'?'error':''):(TOPIC_TONE[t]||'');return `<span class="badge ${tone}">${esc(g)}</span>`});
 return b.join(' ')||`<span class="muted">${esc(r.label||'')}</span>`;
}

/* ---------- 8-K events ---------- */
function eventsView(){
 let out=head('8-K events','Every current report companies file with the SEC — deals, CEO and CFO changes, restatements, cyber incidents, delisting notices, offerings, buybacks, guidance raised or lowered — read once and sorted by what it says.','SEC / 8-K');
 const g=marketGate('events8k','8-K events');if(!g.data)return out+g.html;
 const d=g.data,all=d.rows||[],T=d.topics||{};
 out+=discDateControls('SEC filing date');
 const topics=Object.keys(T);state.etopic=topics.includes(state.etopic)||['material','graised','glowered'].includes(state.etopic)?state.etopic:'';
 state.ewho=['','listed','site'].includes(state.ewho)?state.ewho:'listed';
 out+=`<div class="toolbar">${field('etopic','What',[['','Everything'],['material','Material events only'],['graised','Guidance raised'],['glowered','Guidance lowered or withdrawn'],...topics.filter(t=>t!=='guidance').map(t=>[t,T[t][0].toUpperCase()+T[t].slice(1)])],state.etopic)}${field('ewho','Companies',[['listed','With a ticker'],['','All filers']],state.ewho)}${search('eq','Ticker, company or words','e.g. acquisition · Enter')}</div>`;
 const c=d.counts||{},day=all[0]?all[0].filed:'';
 out+=`<div class="metrics">${kpi('8-Ks on file',fmt(d.on_file),`Shown: the last ${fmt(d.days)} days`)}${kpi('Filed on '+(day||'—'),fmt(all.filter(r=>r.filed===day).length),'Newest filing day')}${kpi('Deals, 7 days',fmt(c.deal||0),'Mergers, acquisitions, tender offers')}${kpi('Guidance changes, 7 days',fmt(all.filter(r=>r.filed>=daysAgo(7)&&['raised','lowered','withdrawn'].includes(r.guidance)).length),'Raised, lowered or withdrawn')}</div>`;
 const top=Object.entries(c).filter(([k])=>k!=='earnings'&&k!=='vote').slice(0,12);
 out+=`<div class="panel"><h3>What companies reported, last 7 days</h3><p class="sub">8-Ks with a ticker, by topic (one filing can have several) · earnings releases left out of the chart</p>${top.length?divergingChart(top.map(([k,v])=>({label:TOPIC_SHORT[k]||k,value:v,tip:[[T[k]||k,`${fmt(v)} filings`]]})),{unit:'count',label:'8-K filings by topic',neutral:true}):empty('No 8-K on file yet — the collector reads the newest filings every half hour and works back through the daily indexes.')}</div>`;
 const q=(state.eq||'').trim().toLowerCase();
 const rows=all.filter(r=>(state.ewho!=='listed'||r.ticker)&&(!state.etopic||(state.etopic==='material'?(r.score||0)>=6:state.etopic==='graised'?r.guidance==='raised':state.etopic==='glowered'?['lowered','withdrawn'].includes(r.guidance):(r.topics||[]).includes(state.etopic)))
  &&(!q||[r.ticker,r.company,r.headline,r.quote,r.label].join(' ').toLowerCase().includes(q))&&discDateMatches(r,['filed']));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} filings</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one 8-K');
 out+=table([...(XPOST.on?['X']:[]),'Filed','Ticker','Company','Items','What','Key sentence','Source'],rows.map(r=>[
  ...(XPOST.on?[xBtn('post_8k',r.cik,r.accession,`${r.ticker||r.company}'s 8-K of ${r.filed}`)]:[]),`${esc(r.filed)}<br><span class="muted">${esc(hm(r.accepted))}</span>`,
  r.ticker?tkLink(r.ticker,r.cik):'—',coCell(r.company,r.ticker,r.cik),`${esc((r.items||[]).filter(x=>x!=='9.01').join(', ')||'9.01')}${r.form==='8-K/A'?' <span class="muted">amended</span>':''}`,
  topicBadges(r,T),`<span class="mk-asset" title="${esc(r.quote||'')}">${r.headline?`<b>${esc(r.headline.slice(0,120))}</b><br>`:''}${esc((r.guidance_quote||r.quote||'').slice(0,180))}${(r.guidance_quote||r.quote||'').length>180?'…':''}</span>`,
  link(r.url,(r.form||'8-K')+' ↗')]));
 return out;
}

/* ---------- News: wires and government releases ---------- */
const NEWS_KIND={release:'Press release',fda:'FDA',sec_action:'SEC enforcement',suspension:'SEC trading suspension',sec_release:'SEC press release'};
function newsView(){
 let out=head('News','Press releases from the wires and government releases — FDA approvals, SEC enforcement and trading suspensions — matched to the companies they name. Headline, time and link only: open the source for the text.','PR NEWSWIRE · FDA · SEC');
 const g=marketGate('news','News');if(!g.data)return out+g.html;
 const d=g.data,all=d.rows||[];
 out+=discDateControls('Publication date');
 state.nkind=['',...Object.keys(NEWS_KIND)].includes(state.nkind)?state.nkind:'';state.nwho=['','listed'].includes(state.nwho)?state.nwho:'listed';
 out+=`<div class="toolbar">${field('nkind','Source',[['','Everything'],...Object.entries(NEWS_KIND)],state.nkind)}${field('nwho','Companies',[['listed','Matched to a ticker'],['','Everything read']],state.nwho)}${search('nq','Ticker, company or words','e.g. LMT · Enter')}</div>`;
 const k=Object.fromEntries(Object.keys(NEWS_KIND).map(x=>[x,all.filter(r=>r.kind===x).length]));
 out+=`<div class="metrics">${kpi('Items on file',fmt(d.on_file),'Since '+(d.since||'—'))}${kpi('Matched to a ticker',fmt(all.filter(r=>(r.tickers||[]).length).length),'Issuer named in the release or the record')}${kpi('FDA',fmt(k.fda),'New drug and biologic approvals, FDA releases')}${kpi('SEC actions',fmt((k.sec_action||0)+(k.suspension||0)+(k.sec_release||0)),'Enforcement and trading suspensions')}</div>`;
 const q=(state.nq||'').trim().toLowerCase();
 const rows=all.filter(r=>(!state.nkind||r.kind===state.nkind)&&(state.nwho!=='listed'||(r.tickers||[]).length)&&(!q||[(r.tickers||[]).join(' '),r.company,r.title].join(' ').toLowerCase().includes(q))&&discDateMatches(r,['published']));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} items</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one news item');
 out+=table([...(XPOST.on?['X']:[]),'Published','Ticker','Company','Source','Headline','Link'],rows.map(r=>[
  ...(XPOST.on?[(r.tickers||[]).length?xBtn('post_news',0,[r.id],`${r.tickers[0]}: ${r.title}`):'—']:[]),`${esc((r.published||'').slice(0,10))}<br><span class="muted">${esc((r.published||'').slice(11,16))} UTC</span>`,
  (r.tickers||[]).map(t=>tkLink(t)).join(' ')||'—',esc(r.company||''),`<span class="badge">${esc(NEWS_KIND[r.kind]||r.kind)}</span><br><span class="muted">${esc(r.source||'')}</span>`,
  `<span class="mk-asset">${esc(r.title||'')}</span>${r.amount?`<br><span class="muted">${money(r.amount)}${r.agency?' · '+esc(r.agency):''}</span>`:''}`,link(r.url,'Source ↗')]));
 return out;
}

function bindNews(){
 for(const k of ['etopic','ewho','nkind','nwho'])bind(k,k);
 for(const k of ['eq','nq'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
}
