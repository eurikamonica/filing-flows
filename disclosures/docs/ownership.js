/* 4.6 ownership views: Large holders (Schedules 13D / 13G), Form 144 (notices of proposed sales) and Short interest
   (FINRA, twice a month). Data: data/market/{stakes,form144,short-interest}.json, built by app/ownership.py and
   app/shorts.py; loaded on first use (marketGate, market.js). Each row has an Owner-only ✦ X (xpost.js). No dependencies. */
const pts=v=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),2)+' pts';
const pctv=(v,d=2)=>v==null||!Number.isFinite(+v)?'—':fmt(v,d)+'%';
const chg=v=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),1)+'%';
const coCell=(name,ticker,cik)=>cik?`<a class="tk" href="${esc(coHref(ticker,cik))}">${esc(name||'')}</a>`:esc(name||'');
const search=(id,label,ph)=>`<div class="field wide"><label for="${id}">${label}</label><input id="${id}" value="${esc(state[id]||'')}" placeholder="${esc(ph)}"></div>`;
const daysAgo=n=>{const d=new Date(Date.now()-n*864e5);return d.toISOString().slice(0,10)};

/* ---------- Large holders: Schedules 13D / 13G ---------- */
function stakesView(){
 let out=head('Large holders · 13D / 13G','Who owns more than 5% of a company: activists and strategic holders file a Schedule 13D (with their purpose), passive holders the short-form 13G — including when they drop below 5%.','SEC / 13D · 13G');
 const g=marketGate('stakes','13D / 13G filings');if(!g.data)return out+g.html;
 const d=g.data,all=d.latest||[];
 state.oform=['','13D','13G','new','exit','up','down'].includes(state.oform)?state.oform:'';
 out+=`<div class="toolbar">${field('oform','Filings',[['','All 13D and 13G'],['13D','13D and 13D/A (may seek influence)'],['13G','13G and 13G/A (passive)'],['new','New filings only'],['up','Raised stake'],['down','Cut stake'],['exit','Dropped below 5%']],state.oform)}${search('oq','Ticker, company or holder','e.g. activist name · Enter')}</div>`;
 const d30=daysAgo(30),last=all.filter(r=>(r.filed||'')>=d30);
 const new13d=last.filter(r=>r.form==='13D'),exits=last.filter(r=>r.label==='below 5%');
 out+=`<div class="metrics">${kpi('Filings on file',fmt(d.on_file),'Since '+(d.since||'—'))}${kpi('New 13Ds, 30 days',fmt(new13d.length),'Holders above 5% who may seek influence')}${kpi('13D amendments, 30 days',fmt(last.filter(r=>r.form==='13D/A').length),'Material changes, purpose updates')}${kpi('Dropped below 5%, 30 days',fmt(exits.length),'13G/A exits and 13D/A below 5%')}</div>`;
 const top=(d.summary||[]).filter(a=>a.d13).slice(0,14);
 out+=`<div class="panel"><h3>Most 13D activity, last 90 days</h3><p class="sub">13D and 13D/A filings per company · hover for who filed</p>${top.length?divergingChart(top.map(a=>({label:a.ticker,value:a.d13,tip:[[a.ticker,a.issuer||''],[`${a.d13} 13D filing${a.d13===1?'':'s'}`,a.new13d?`${a.new13d} new`:''],[a.filers.slice(0,4).join(', '),''],[`largest stake ${fmt(a.max_percent,2)}%`,'']]})),{unit:'count',label:'13D filings by company',neutral:true}):empty('No 13D filings on file yet — the collector reads the newest filings every half hour and works back through the daily indexes.')}</div>`;
 const q=(state.oq||'').trim().toLowerCase();
 const rows=all.filter(r=>(!state.oform||(state.oform==='new'?r.new:state.oform==='exit'?r.label==='below 5%':state.oform==='up'?r.change>0:state.oform==='down'?r.change<0:r.form.startsWith(state.oform)))
  &&(!q||[r.ticker,r.issuer,r.filer,r.person].join(' ').toLowerCase().includes(q)));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} filings</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one filing');
 out+=table([...(XPOST.on?['X']:[]),'Filed','Ticker','Company','Holder','Filing','Stake','Change','Event date','Purpose / type','Source'],rows.map(r=>[
  ...(XPOST.on?[xBtn('post_stake',r.issuer_cik,[r.accession],`${r.filer}'s ${r.form} on ${r.ticker||r.issuer}`)]:[]),esc(r.filed),r.ticker?tkLink(r.ticker,r.issuer_cik):'—',coCell(r.issuer,r.ticker,r.issuer_cik),
  (()=>{const nice=r.person&&r.person!==r.person.toUpperCase();return `<b>${esc(nice?r.person:r.filer)}</b>${r.persons>1?`<br><span class="muted">${fmt(r.persons)} reporting persons${nice?(r.filer!==r.person?' · filed by '+esc(r.filer):''):r.person&&r.person!==r.filer?' · largest: '+esc(r.person):''}</span>`:''}`})(),
  `${esc(r.form)} <span class="badge ${r.label==='below 5%'?'error':r.new?'ready':''}">${esc(r.label||'')}</span>`,
  `${pctv(r.percent)}<br><span class="muted">${compact(r.shares)} sh</span>`,
  `<span class="${r.change>0?'positive':r.change<0?'negative':''}">${pts(r.change)}</span>${r.prev_percent!=null?`<br><span class="muted">from ${pctv(r.prev_percent)}</span>`:''}`,
  esc(r.event_date||''),r.purpose?`<span class="mk-asset" title="${esc(r.purpose)}">${esc(r.purpose.slice(0,160))}${r.purpose.length>160?'…':''}</span>`:esc(r.rule||''),link(r.url,r.form+' ↗')]));
 return out;
}

/* ---------- Form 144: notices of proposed sales ---------- */
function form144View(){
 let out=head('Planned insider sales · Form 144','Officers, directors and other affiliates give notice before selling restricted or control shares: how many, their market value, the approximate sale date and how the shares were acquired. A notice is an intention; the sale itself follows on Form 4.','SEC / FORM 144');
 const g=marketGate('form144','Form 144 notices');if(!g.data)return out+g.html;
 const d=g.data,all=d.latest||[];
 state.frole=['','officer','director','other'].includes(state.frole)?state.frole:'';state.fmin=['100000','1000000','10000000'].includes(state.fmin)?state.fmin:'100000';
 out+=`<div class="toolbar">${field('frole','Who',[['','Everyone'],['officer','Officers'],['director','Directors'],['other','Other affiliates (10% owners, trusts …)']],state.frole)}${field('fmin','Market value',[['100000','$100K or more'],['1000000','$1M or more'],['10000000','$10M or more']],state.fmin)}${search('fq','Ticker, company or seller','e.g. NVDA · Enter')}</div>`;
 const d30=daysAgo(30),last=all.filter(r=>(r.filed||'')>=d30),big=last.slice().sort((a,b)=>(b.value||0)-(a.value||0))[0];
 out+=`<div class="metrics">${kpi('Notices on file',fmt(d.on_file),'Since '+(d.since||'—')+(d.small?` · ${fmt(d.small)} under $100K not listed`:''))}${kpi('Planned sales, 30 days',money(last.reduce((s,r)=>s+(r.value||0),0)),`${fmt(last.length)} notices of $100K or more`)}${kpi('Largest notice, 30 days',big?money(big.value):'—',big?`${big.ticker||big.issuer} · ${big.seller_name||big.seller}`:'')}${kpi('Under a 10b5-1 plan',last.length?pct(last.filter(r=>r.plan_date).length/last.length,0):'—','Notices naming a plan adoption date')}</div>`;
 const top=(d.summary||[]).slice(0,14);
 out+=`<div class="panel"><h3>Most planned selling, last 30 days</h3><p class="sub">Market value in Form 144 notices per company · hover for who gave notice</p>${top.length?divergingChart(top.map(a=>({label:a.ticker,value:-a.value,tip:[[a.ticker,a.issuer||''],[money(a.value),`in ${a.notices} notice${a.notices===1?'':'s'}`],[a.sellers.slice(0,4).join(', '),a.plan?`${a.plan} under a 10b5-1 plan`:'']]})),{label:'Planned sales by company',format:v=>money(Math.abs(v))}):empty('No Form 144 notices on file yet — the collector reads the newest filings every half hour.')}</div>`;
 const q=(state.fq||'').trim().toLowerCase(),min=+state.fmin;
 const rows=all.filter(r=>(r.value||0)>=min&&(!state.frole||(state.frole==='other'?!/officer|director/i.test(r.relationship||''):new RegExp(state.frole,'i').test(r.relationship||'')))
  &&(!q||[r.ticker,r.issuer,r.seller,r.seller_name].join(' ').toLowerCase().includes(q)));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} notices</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one notice');
 out+=table([...(XPOST.on?['X']:[]),'Filed','Ticker','Company','Seller','Relationship','Shares','Market value','Approx. sale date','Acquired by','10b5-1 plan','Source'],rows.map(r=>[
  ...(XPOST.on?[xBtn('post_f144',r.issuer_cik,[r.accession],`${r.seller}'s Form 144 on ${r.ticker||r.issuer}`)]:[]),esc(r.filed),r.ticker?tkLink(r.ticker,r.issuer_cik):'—',coCell(r.issuer,r.ticker,r.issuer_cik),
  `<b title="${esc('As filed: '+r.seller)}">${esc(r.seller_name||r.seller)}</b>`,esc(r.relationship||''),fmt(r.shares),money(r.value),esc(r.sale_date||''),`<span class="mk-asset">${esc(r.acquired||'—')}</span>`,esc(r.plan_date||'—'),link(r.url,'Form 144 ↗')]));
 return out;
}

/* ---------- Short interest (FINRA) ---------- */
function shortBars(hist){
 const v=(hist||[]).map(h=>h[1]);if(v.length<2)return '—';
 const W=78,H=24,max=Math.max(1,...v.map(x=>x||0)),bw=Math.max(2,Math.floor((W-2)/v.length)-2);
 return `<svg class="mk-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-label="shares short by settlement date: ${hist.map(h=>h[0]+' '+compact(h[1])).join(', ')}">${v.map((x,i)=>{const h=Math.max(1.5,(x||0)/max*(H-3));return `<rect x="${1+i*(bw+2)}" y="${H-h}" width="${bw}" height="${h}" rx="1" class="${i===v.length-1?'mk-buy':'mk-neutral'}"><title>${esc(hist[i][0])}: ${compact(x)} shares short</title></rect>`}).join('')}</svg>`;
}
function shortsView(){
 let out=head('Short interest','Shares sold short in each stock as of FINRA’s twice-monthly settlement dates — the consolidated figures brokers report for exchange-listed and OTC stocks, published about a week after each date.','FINRA / SHORT INTEREST');
 const g=marketGate('short-interest','Short interest');if(!g.data)return out+g.html;
 const d=g.data,all=d.rows||[],by=Object.fromEntries(all.map(r=>[r.ticker,r]));
 state.slist=['','rise','fall','dtc','largest'].includes(state.slist)?state.slist:'';
 out+=`<div class="toolbar">${field('slist','List',[['','Every stock shown'],['rise','Largest rises (2M+ shares short)'],['fall','Largest falls (2M+ shares short)'],['dtc','Most days to cover'],['largest','Largest positions']],state.slist)}${search('shq','Ticker or company','e.g. TSLA · Enter')}</div>`;
 const T=d.top||{},rise=(T.rise||[]).map(t=>by[t]).filter(Boolean),fall=(T.fall||[]).map(t=>by[t]).filter(Boolean),top=(T.dtc||[]).map(t=>by[t]).filter(Boolean)[0];
 out+=`<div class="metrics">${kpi('Settlement date',d.settlement_date||'—',d.previous_date?'Compared with '+d.previous_date:'')}${kpi('Stocks reported',fmt(d.stocks),`${fmt(d.shown)} with ${compact(d.min_short)}+ shares short shown`)}${kpi('Largest rise',rise[0]?chg(rise[0].change_pct):'—',rise[0]?`${rise[0].ticker} · ${compact(rise[0].short)} shares short`:'')}${kpi('Most days to cover',top?fmt(top.dtc,2):'—',top?`${top.ticker} · ${compact(top.short)} shares short`:'')}</div>`;
 const moves=[...rise.slice(0,7),...fall.slice(0,7)];
 out+=`<div class="panel"><h3>Biggest changes in short interest</h3><p class="sub">${esc(d.settlement_date||'')} vs ${esc(d.previous_date||'the prior date')} · stocks with 2M+ shares short and 200K+ average daily volume · hover for details</p>${moves.length?divergingChart(moves.map(r=>({label:r.ticker,value:r.change_pct,tip:[[r.ticker,r.name||''],[chg(r.change_pct),`to ${compact(r.short)} shares short`],[`${fmt(r.dtc,2)} days to cover`,`ADV ${compact(r.adv)}`]]})),{label:'Change in short interest, percent',format:chg,neutral:true}):empty('No settlement date on file yet — FINRA publishes about a week after the 15th and the month-end.')}</div>`;
 const q=(state.shq||'').trim().toLowerCase();
 let rows=state.slist?(T[state.slist]||[]).map(t=>by[t]).filter(Boolean):all;
 rows=rows.filter(r=>!q||(r.ticker+' '+(r.name||'')).toLowerCase().includes(q));
 exported=rows.map(({hist,...r})=>({...r,settlement_date:d.settlement_date}));
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} stocks</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one stock’s short interest');
 out+=table([...(XPOST.on?['X']:[]),'Ticker','Company','Market','Shares short','Change','Days to cover','Avg daily volume','Last dates','Note'],rows.map(r=>[
  ...(XPOST.on?[xBtn('post_short',0,[r.ticker,d.settlement_date],`short interest in ${r.ticker}`)]:[]),tkLink(r.ticker),esc(r.name||''),esc(r.market||''),compact(r.short),
  `${chg(r.change_pct)}<br><span class="muted">${r.change!=null?(r.change>0?'+':r.change<0?'−':'')+compact(Math.abs(r.change)):'—'}</span>`,
  fmt(r.dtc,2),compact(r.adv),shortBars(r.hist),[r.split?'stock split':'',r.revised?'revised':''].filter(Boolean).join(' · ')||'—']));
 return out;
}

function bindOwnership(){
 for(const k of ['oform','frole','fmin','slist'])bind(k,k);
 for(const k of ['oq','fq','shq'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
}
