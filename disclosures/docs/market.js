/* 4.3 market views: Signals (where money, officials and price line up), Market flows (13F money flows across every
   processed manager) and Officials' trades (machine-read House transaction reports with ticker checks).
   Data: data/market/{signals,flows,officials-trades}.json, built by app/market.py; loaded on first use. No dependencies. */
const marketStore={};
function marketData(name){
 const m=marketStore[name]||(marketStore[name]={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='this browser cannot load data files';return m}
 m.loading=fetch('data/market/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
  .then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function marketGate(name,title){
 if(state.mode==='demo')return {html:empty(title+' use the official snapshot only. Switch Data to “Official snapshot”.')};
 const m=marketData(name);
 if(m.err)return {html:empty(`${title} could not load (${m.err}). They are built by the collector every few hours; refresh to retry.`)};
 if(!m.data)return {html:empty(`Loading ${title.toLowerCase()}…`)};
 return {data:m.data};
}
const big=v=>v>=1e12?fmt(v/1e12,2)+'T':compact(v);
const money=v=>v==null||!Number.isFinite(+v)?'—':(v<0?'−':'')+'$'+big(Math.abs(v));
const smoney=v=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+'$'+big(Math.abs(v));
const shortName=s=>{const w=String(s||'').replace(/\b(INC|CORP|CORPORATION|CO|LTD|PLC|HLDGS?|HOLDINGS?|GROUP|THE|N\.?V|S\.?A)\b\.?/gi,'').trim().split(/\s+/);let o=w[0]||'';for(const x of w.slice(1)){if((o+' '+x).length>13)break;o+=' '+x}return o.slice(0,13)};
const spct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)+'%';
/* A ticker opens its company page on the main site: by CIK when the row has one, otherwise the main site looks the ticker up (#t-…). */
const coHref=(ticker,cik)=>cik?`../#c-${String(cik).replace(/^0+/,'')}`:`../#t-${encodeURIComponent(ticker)}`;
const tkLink=(ticker,cik)=>ticker?`<a class="tk" href="${esc(coHref(ticker,cik))}" title="${esc(ticker)} — earnings Sankey and filings on Filing Flows"><b>${esc(ticker)}</b></a>`:'';
const tick=r=>tkLink(r.ticker,r.cik||r.earn?.cik);

/* ---------- tooltip: one floating element; content set with textContent (labels are data) ---------- */
const tipData=[];
function tip(rows){tipData.push(rows);return tipData.length-1}
function bindTips(){
 let el=document.getElementById('mk-tip');
 if(!el){el=document.createElement('div');el.id='mk-tip';el.className='mk-tip';el.setAttribute('role','tooltip');document.body.appendChild(el)}
 const show=(t,x,y)=>{const rows=tipData[+t.dataset.tip];if(!rows)return;el.replaceChildren(...rows.map(([v,l],i)=>{const d=document.createElement('div');d.className=i?'tt-row':'tt-head';const s=document.createElement('strong');s.textContent=v;d.appendChild(s);if(l){const sp=document.createElement('span');sp.textContent=' '+l;d.appendChild(sp)}return d}));
  el.style.display='block';const w=el.offsetWidth,h=el.offsetHeight;el.style.left=Math.max(8,Math.min(innerWidth-w-8,x+14))+'px';el.style.top=Math.max(8,y-h-12)+'px'};
 document.querySelectorAll('#workspace [data-tip]').forEach(t=>{
  t.onpointermove=e=>show(t,e.clientX,e.clientY);t.onpointerleave=()=>{el.style.display='none'};
  t.onfocus=()=>{const r=t.getBoundingClientRect();show(t,r.left+r.width/2,r.top)};t.onblur=()=>{el.style.display='none'};
 });
}

/* ---------- charts (SVG, text in text tokens, marks in data tokens) ---------- */
function barPath(x0,x1,y,h,r=4){                    // rounded at the data end (x1), square at the baseline (x0)
 const dir=x1>=x0?1:-1,len=Math.abs(x1-x0);r=Math.min(r,len,h/2);
 if(len<.5)return '';
 const xe=x1-dir*r;
 return `M${x0},${y}H${xe}Q${x1},${y} ${x1},${y+r}V${y+h-r}Q${x1},${y+h} ${xe},${y+h}H${x0}Z`;
}
function divergingChart(items,{unit='usd',label='Estimated net flow',format=null,neutral=false}={}){
 if(!items.length)return empty('Nothing to chart');
 const W=720,row=26,bar=14,L=120,R=22,T=10,H=T+items.length*row+26,valW=70;
 const max=Math.max(1,...items.map(x=>Math.abs(x.value))),hasNeg=items.some(x=>x.value<0),hasPos=items.some(x=>x.value>0);
 const x0=hasNeg&&hasPos?L+valW+(W-L-R-2*valW)/2:hasNeg?W-R:L+4;
 const span=hasNeg&&hasPos?(W-L-R-2*valW)/2:hasNeg?W-R-L-valW:W-R-valW-L-4;
 const sx=v=>x0+v/max*span;
 const f=format||(unit==='usd'?smoney:v=>fmt(v));
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}; values are in the table below">`;
 s+=`<line class="mk-axis" x1="${x0}" x2="${x0}" y1="${T-4}" y2="${H-22}"/>`;
 items.forEach((x,i)=>{const y=T+i*row+(row-bar)/2,x1=sx(x.value),neg=x.value<0;
  s+=`<g data-tip="${tip(x.tip)}" tabindex="0" class="mk-hit"><rect x="0" y="${T+i*row}" width="${W}" height="${row}" fill="transparent"/>`;
  s+=`<text class="mk-label" x="${L-10}" y="${y+bar-3}" text-anchor="end">${esc(x.label.slice(0,16))}</text>`;
  s+=`<path d="${barPath(x0,x1,y,bar)}" class="${neutral?'mk-neutral':neg?'mk-sell':'mk-buy'}"/>`;
  s+=`<text class="mk-value" x="${neg?x1-6:x1+6}" y="${y+bar-3}" text-anchor="${neg?'end':'start'}">${esc(f(x.value))}</text></g>`});
 s+=`<text class="axis" x="${x0}" y="${H-6}" text-anchor="middle">0</text>`;
 return s+'</svg>';
}
function butterfly(items){                          // sellers to the left, buyers to the right (manager counts)
 if(!items.length)return empty('Nothing to chart');
 const W=720,row=26,bar=12,L=120,R=40,T=22,H=T+items.length*row+10,mid=L+(W-L-R)/2,half=(W-L-R)/2-34;
 const max=Math.max(1,...items.flatMap(x=>[x.buyers,x.sellers]));
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Managers who added versus cut; values are in the table below">`;
 s+=`<text class="axis" x="${mid-8}" y="12" text-anchor="end">◀ cut or exited</text><text class="axis" x="${mid+8}" y="12">added or opened ▶</text>`;
 s+=`<line class="mk-axis" x1="${mid}" x2="${mid}" y1="${T-4}" y2="${H-6}"/>`;
 items.forEach((x,i)=>{const y=T+i*row+(row-bar)/2,b=x.buyers/max*half,se=x.sellers/max*half;
  s+=`<g data-tip="${tip(x.tip)}" tabindex="0" class="mk-hit"><rect x="0" y="${T+i*row}" width="${W}" height="${row}" fill="transparent"/>`;
  s+=`<text class="mk-label" x="${L-10}" y="${y+bar-2}" text-anchor="end">${esc(x.label.slice(0,16))}</text>`;
  s+=`<path d="${barPath(mid-1,mid-1-se,y,bar)}" class="mk-sell"/><path d="${barPath(mid+1,mid+1+b,y,bar)}" class="mk-buy"/>`;
  s+=`<text class="mk-value" x="${mid-se-8}" y="${y+bar-2}" text-anchor="end">${fmt(x.sellers)}</text><text class="mk-value" x="${mid+b+8}" y="${y+bar-2}">${fmt(x.buyers)}</text></g>`});
 return s+'</svg>';
}
function spark(values){                             // weekly closes, last six months
 const v=(values||[]).filter(x=>x!=null);if(v.length<3)return '—';
 const W=86,H=24,lo=Math.min(...v),hi=Math.max(...v),y=x=>H-3-(x-lo)/((hi-lo)||1)*(H-6),xs=i=>2+i/(v.length-1)*(W-6);
 const up=v[v.length-1]>=v[0];
 return `<svg class="mk-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-label="six-month price trend ${up?'up':'down'}"><polyline points="${v.map((p,i)=>xs(i).toFixed(1)+','+y(p).toFixed(1)).join(' ')}" class="mk-spark-line"/><circle cx="${xs(v.length-1)}" cy="${y(v[v.length-1])}" r="2.6" class="${up?'mk-buy':'mk-sell'}"/></svg>`;
}
function columns(hist){                              // net managers per quarter, above / below a baseline
 const v=(hist||[]).map(h=>h[1]);if(!v.some(x=>x))return '—';
 const W=78,H=24,mid=H/2,max=Math.max(1,...v.map(x=>Math.abs(x||0))),bw=Math.floor((W-4)/v.length)-2;
 return `<svg class="mk-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-label="net managers per quarter: ${v.map(x=>x==null?'n/a':x).join(', ')}"><line x1="0" x2="${W}" y1="${mid}" y2="${mid}" class="mk-axis"/>${v.map((x,i)=>{if(!x)return '';const h=Math.max(1.5,Math.abs(x)/max*(mid-2)),X=2+i*(bw+2);return `<rect x="${X}" y="${x>0?mid-h:mid}" width="${bw}" height="${h}" rx="1.5" class="${x>0?'mk-buy':'mk-sell'}"><title>${esc(hist[i][0])}: ${x>0?'+':''}${x} managers</title></rect>`}).join('')}</svg>`;
}
function hypeMap(rows){
 const pts=rows.filter(r=>r.f13&&r.price&&r.price.r3m!=null);
 if(pts.length<3)return empty('Not enough priced securities with 13F changes to map yet.');
 const W=720,H=380,L=52,R=18,T=18,B=40;
 const xv=r=>r.f13.buyers-r.f13.sellers,yv=r=>Math.max(-.6,Math.min(1.2,r.price.r3m));
 const xmax=Math.max(10,...pts.map(r=>Math.abs(xv(r)))),ylo=Math.min(-.2,...pts.map(yv)),yhi=Math.max(.2,...pts.map(yv));
 const sx=v=>L+(v+xmax)/(2*xmax)*(W-L-R),sy=v=>T+(yhi-v)/(yhi-ylo)*(H-T-B);
 let s=`<svg class="plot mk-plot mk-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Hype map: net 13F managers against three-month price change; details are in the table below">`;
 const nice=(lo,hi,n=5)=>{const raw=(hi-lo)/n,p=10**Math.floor(Math.log10(raw)),st=[1,2,2.5,5,10].map(m=>m*p).find(x=>x>=raw);const out=[];for(let v=Math.ceil(lo/st)*st;v<=hi+1e-9;v+=st)out.push(+v.toFixed(6));return out};
 nice(ylo,yhi).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${spct(v,0)}</text>`});
 nice(-xmax,xmax,6).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${v>0?'+':''}${fmt(v)}</text>`});
 s+=`<line class="mk-axis" x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
 s+=`<text class="mk-quad" x="${W-R-4}" y="${T+12}" text-anchor="end">Bought and rising</text><text class="mk-quad" x="${W-R-4}" y="${H-B-8}" text-anchor="end">Bought while falling</text><text class="mk-quad" x="${L+6}" y="${T+12}">Sold while rising</text><text class="mk-quad" x="${L+6}" y="${H-B-8}">Sold and falling</text>`;
 s+=`<text class="axis" x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle">Net 13F managers this quarter (added − cut)</text>`;
 const hot=pts.filter(r=>r.heat>=3).sort((a,b)=>b.heat-a.heat||Math.abs(xv(b))-Math.abs(xv(a)));
 const boxes=[],labelled=new Set();            // label the hottest first; skip a label that would overlap one already placed
 for(const r of hot){if(labelled.size>=14)break;const x=sx(xv(r))+8,y=sy(yv(r))-7,w=r.ticker.length*7.4+4,b=[x,y-11,x+w,y+3];
  if(b[2]>W-R||boxes.some(o=>b[0]<o[2]&&b[2]>o[0]&&b[1]<o[3]&&b[3]>o[1]))continue;boxes.push(b);labelled.add(r.ticker)}
 [...pts.filter(r=>r.heat<3),...hot].forEach(r=>{const x=sx(xv(r)),y=sy(yv(r)),h=r.heat>=3;
  s+=`<g data-tip="${tip(pointTip(r))}" tabindex="0" class="mk-hit"><circle cx="${x}" cy="${y}" r="12" fill="transparent"/><circle cx="${x}" cy="${y}" r="${h?5:4}" class="${h?'mk-hot':'mk-dot'}"/></g>`});
 hot.filter(r=>labelled.has(r.ticker)).forEach(r=>{s+=`<text class="mk-label mk-halo" x="${sx(xv(r))+8}" y="${sy(yv(r))-7}">${esc(r.ticker)}</text>`});   // labels above every dot
 s+='</svg>';
 return s+`<div class="mk-legend"><span><i class="mk-key mk-hot"></i>Heat 3 or more (hottest labelled)</span><span><i class="mk-key mk-dot"></i>Other flagged securities</span><span class="muted">Price change clipped to −60% … +120%</span></div>`;
}
function pointTip(r){
 const t=[[r.ticker,r.name||'']];
 if(r.f13)t.push([`${fmt(r.f13.buyers)} added · ${fmt(r.f13.sellers)} cut`,`· est. net ${smoney(r.f13.usd_net)}`]);
 if(r.price)t.push([spct(r.price.r3m),'over three months'+(r.price.from_high!=null?` · ${spct(r.price.from_high)} from 52-week high`:'')]);
 if(r.officials)t.push([`${r.officials.y_buys} buys / ${r.officials.y_sells} sales`,'by officials, last 12 months']);
 if(r.insiders&&r.insiders.buys)t.push([money(r.insiders.buy_value),`bought by insiders in 90 days (${r.insiders.buyers.slice(0,2).join(', ')})`]);
 if(r.earn)t.push([`${r.earn.label}: revenue ${r.earn.rev||'—'}`,r.earn.yoy!=null?`${r.earn.yoy>0?'+':''}${fmt(r.earn.yoy,0)}% Y/Y`:'']);
 t.push([`Heat ${r.heat}`,r.tags.map(tagWord).join(', ')]);
 return t;
}

/* ---------- Signals ---------- */
const TAG_WORDS={crowded_buy:'Crowded buy',new_money:'New money',big_inflow:'Big inflow',crowded_exit:'Crowded exit',big_outflow:'Big outflow',officials_buying:'Officials buying',officials_cluster:'Officials cluster',officials_selling:'Officials selling',near_high:'Near 52-week high',momentum:'Momentum',drawdown:'Drawdown',buying_the_dip:'Buying the dip',revenue_surge:'Revenue surge',profitable_growth:'Profitable growth',insider_buying:'Insider buying',insider_cluster:'Insider cluster',insider_selling:'Insider selling'};
const tagWord=t=>TAG_WORDS[t]||t;
const BAD=new Set(['crowded_exit','big_outflow','officials_selling','drawdown','insider_selling']);
const tagBadges=tags=>tags.map(t=>`<span class="badge ${BAD.has(t)?'error':'ready'}">${esc(tagWord(t))}</span>`).join(' ');
function signals(){
 let out=head('Signals','Where institutional money, public officials and the price line up — computed from 13F disclosures, officials’ transaction reports and daily closes. Descriptive flags, not predictions or advice.','13F · OFFICIALS · PRICES');
 const g=marketGate('signals','Signals');if(!g.data)return out+g.html;
 const d=g.data,all=d.rows||[];
 const tags=Object.keys(d.tags||TAG_WORDS).filter(t=>all.some(r=>r.tags.includes(t)));
 state.stag=tags.includes(state.stag)?state.stag:'';
 out+=`<div class="toolbar">${field('stag','Signal',[['','Every flagged security'],...tags.map(t=>[t,tagWord(t)+' ('+all.filter(r=>r.tags.includes(t)).length+')'])],state.stag,true)}${field('ssort','Order',[['heat','Heat (most signals first)'],['pressure','Pressure (selling signals first)'],['flow','Estimated net 13F dollars'],['r3m','Three-month price change']],state.ssort||'heat')}<div class="field wide"><label for="sq">Ticker or name</label><input id="sq" value="${esc(state.sq||'')}" placeholder="e.g. NVDA · Enter to apply"></div></div>`;
 const q=(state.sq||'').trim().toLowerCase();
 const rows=all.filter(r=>(!state.stag||r.tags.includes(state.stag))&&(!q||(r.ticker+' '+r.name).toLowerCase().includes(q)))
  .sort((a,b)=>({pressure:b.pressure-a.pressure||a.heat-b.heat,flow:((b.f13||{}).usd_net||0)-((a.f13||{}).usd_net||0),r3m:((b.price||{}).r3m??-9)-((a.price||{}).r3m??-9)}[state.ssort]??(b.heat-a.heat||((b.f13||{}).usd_net||0)-((a.f13||{}).usd_net||0))));
 const n=t=>all.filter(r=>r.tags.includes(t)).length;
 out+=`<div class="metrics">${kpi('Heat 3 or more',fmt(all.filter(r=>r.heat>=3).length),'Three or more buying-side signals at once')}${kpi('Crowded buys',fmt(n('crowded_buy')),d.quarter||'')}${kpi('Insider clusters',fmt(n('insider_cluster')),'3+ insiders bought within 30 days (Form 4)')}${kpi('Officials buying',fmt(n('officials_buying')),'Purchases reported in the last 90 days')}</div>`;
 out+=`<div class="panel"><h3>Hype map</h3><p class="sub">Each dot is a flagged stock: how many more 13F managers added than cut it in ${esc(d.quarter||'the latest quarter')} (→), against its price move over the last three months (↑). Top-right: money and price agree. Bottom-right: managers buying into a fall.</p>${hypeMap(rows)}</div>`;
 out+=`<details><summary>What each signal means and how heat is scored</summary><p>${Object.entries(d.tags||{}).map(([k,v])=>`<b>${esc(tagWord(k))}</b> — ${esc(v.split(': ').slice(1).join(': ')||v)}`).join('<br>')}<br><br>Heat = 2 × crowded buy + 2 × officials buying + 2 × insider cluster + one each for new money, big inflow, officials cluster, insider buying, near 52-week high, momentum and revenue surge. Pressure = 2 × crowded exit + big outflow + officials selling + insider selling + drawdown. Thresholds this quarter: crowded = ${fmt(d.thresholds?.crowd_net_managers)} net managers; big flow = ${money(d.thresholds?.inflow_usd)}.</p><p class="sub">${esc(d.note||'')}</p></details>`;
 exported=rows.map(r=>({ticker:r.ticker,name:r.name,heat:r.heat,pressure:r.pressure,tags:r.tags.join(' '),...(r.f13||{}),insider_buy_value_90d:r.insiders?.buy_value,insider_sell_value_90d:r.insiders?.sell_value,officials_buys_12m:r.officials?.y_buys,officials_sales_12m:r.officials?.y_sells,officials_people:(r.officials?.people_buy||[]).join('; '),r1m:r.price?.r1m,r3m:r.price?.r3m,from_52w_high:r.price?.from_high,earnings_label:r.earn?.label,revenue_yoy_pct:r.earn?.yoy,operating_margin_pct:r.earn?.om}));
 out+=`<div class="section-head"><h3>${fmt(rows.length)} flagged securities</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Security','Heat','Signals','Net managers','Est. net 13F $','New positions','Officials 12m (buys / sales)','Insiders 90d (Form 4)','3-month price','From 52w high','6-month trend','Latest earnings'],rows.map(r=>[
  `${tick(r)} <span class="muted">${esc(r.name)}</span>${r.earn?.cik?`<br><a href="../#c-${esc(r.earn.cik)}">Earnings chart ↗</a>`:''}`,
  `<b>${r.heat}</b>${r.pressure?` <span class="muted">/ −${r.pressure}</span>`:''}`,`<span class="mk-badges">${tagBadges(r.tags)}</span>`,
  r.f13?`${signed(r.f13.buyers-r.f13.sellers)} <span class="muted">(${fmt(r.f13.buyers)}↑ ${fmt(r.f13.sellers)}↓)</span>`:'—',
  r.f13?`<span class="${r.f13.usd_net>=0?'positive':'negative'}">${smoney(r.f13.usd_net)}</span>`:'—',r.f13?fmt(r.f13.new):'—',
  r.officials?`${r.officials.y_buys} / ${r.officials.y_sells}${r.officials.people_buy.length?`<br><span class="muted">${esc(r.officials.people_buy.slice(0,2).join(', '))}${r.officials.people_buy.length>2?' +'+(r.officials.people_buy.length-2):''}</span>`:''}`:'—',
  r.insiders&&(r.insiders.buys||r.insiders.sells)?`${r.insiders.buys?`<span class="positive">${money(r.insiders.buy_value)} bought</span>`:''}${r.insiders.buys&&r.insiders.sells?'<br>':''}${r.insiders.sells?`<span class="muted">${money(r.insiders.sell_value)} sold</span>`:''}`:'—',
  r.price?`<span class="${r.price.r3m>=0?'positive':'negative'}">${spct(r.price.r3m)}</span>`:'—',r.price?spct(r.price.from_high):'—',
  r.price?spark(r.price.spark):'—',
  r.earn?`${esc(r.earn.label)} · ${esc(r.earn.rev||'')}${r.earn.yoy!=null?` · ${r.earn.yoy>0?'+':''}${fmt(r.earn.yoy,0)}% Y/Y`:''}`:'—']));
 return out;
}

/* ---------- Market flows ---------- */
const FLOW_LISTS=[['net_buy','Net buying (estimated $)'],['net_sell','Net selling (estimated $)'],['most_buyers','Most managers adding'],['most_sellers','Most managers cutting'],['new_positions','Most new positions'],['added','Most dollars added'],['sold','Most dollars sold'],['first_on_file','First on file: IPOs, spin-offs, new CUSIPs'],['retired','Retired lines: mergers, conversions, delistings']];
function flowsView(){
 let out=head('Market flows','What the processed 13F managers added, sold and net-bought this quarter and this year — the whole universe at once. Quarter-end disclosures, not trades.','SEC / 13F · ALL MANAGERS');
 const g=marketGate('flows','Market flows');if(!g.data)return out+g.html;
 const d=g.data,wins=Object.keys(d.windows||{});
 state.fwin=wins.includes(state.fwin)?state.fwin:wins[0];state.funiv=state.funiv==='all'?'all':'stocks';state.flist=FLOW_LISTS.some(x=>x[0]===state.flist)?state.flist:'net_buy';
 const w=d.windows[state.fwin],lists=w.lists[state.funiv];
 out+=`<div class="toolbar">${field('fwin','Period',wins.map(k=>[k,d.windows[k].label]),state.fwin,true)}${field('funiv','Securities',[['stocks','Stocks only'],['all','Stocks, ETFs and funds']],state.funiv)}${field('flist','Ranking',FLOW_LISTS,state.flist,true)}</div>`;
 out+=`<div class="metrics">${kpi('Managers reporting',fmt(w.managers),(w.periods||[]).join(' · '))}${kpi('Estimated $ added',money(w.totals.usd_add),'Stocks; quantity added × quarter-end price')}${kpi('Estimated $ sold',money(w.totals.usd_sold),'Stocks; quantity cut × quarter-end price')}${kpi('Net',smoney(w.totals.usd_add-w.totals.usd_sold),`${fmt(w.securities)} securities changed · ${fmt(w.splits)} splits adjusted`)}</div>`;
 const nm=r=>r.ticker||shortName(r.name||r.issuer)||r.cusip,full=r=>[r.ticker,r.name||r.issuer].filter(Boolean).join(' · ');
 const ftip=r=>[[full(r),''],[smoney(r.usd_net),'estimated net'],[`${money(r.usd_add)} added · ${money(r.usd_sold)} sold`,''],[`${fmt(r.buyers)} added · ${fmt(r.sellers)} cut`,`· ${fmt(r.new)} new · ${fmt(r.exits)} exits`],...(r.top_buy[0]?[[r.top_buy[0].manager,'largest buyer · '+money(r.top_buy[0].usd)]]:[])];
 const top=[...lists.net_buy.slice(0,10),...lists.net_sell.slice(0,10).reverse()];
 out+=`<div class="charts even"><div class="panel"><h3>Net buying and selling</h3><p class="sub">Top 10 each way · estimated dollars · ${esc(w.label)}</p>${divergingChart(top.map(r=>({label:nm(r),value:r.usd_net,tip:ftip(r)})))}</div>`;
 out+=`<div class="panel"><h3>Who is crowding in</h3><p class="sub">Managers that added vs cut · the 12 with the widest margin of adders</p>${butterfly(lists.most_buyers.slice(0,12).map(r=>({label:nm(r),buyers:r.buyers,sellers:r.sellers,tip:ftip(r)})))}</div></div>`;
 out+=`<div class="explain">${esc(d.note||'')} ${state.fwin==='early'?'<b>Early filers only:</b> most managers file in the last two weeks before the 45-day deadline, so this window shows the first movers, not the consensus.':''}</div>`;
 const rows=lists[state.flist]||[],hp=d.history_periods||[];
 exported=rows.map(r=>({ticker:r.ticker,issuer:r.issuer,name:r.name,cusip:r.cusip,type:r.type,usd_net:r.usd_net,usd_add:r.usd_add,usd_sold:r.usd_sold,shares_net:r.sh_net,buyers:r.buyers,sellers:r.sellers,new_positions:r.new,exits:r.exits,holders:r.holders,price:r.price,split_adjusted:r.split,converted:r.converted?JSON.stringify(r.converted):'',top_buyer:r.top_buy[0]?.manager,top_seller:r.top_sell[0]?.manager}));
 out+=`<div class="section-head"><div><h3>${esc(FLOW_LISTS.find(x=>x[0]===state.flist)[1])}</h3><p class="sub">Top ${rows.length} · trend column: net managers per quarter, ${esc(hp[0]||'')} → ${esc(hp[hp.length-1]||'')}</p></div><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Security','Est. net $','Added $','Sold $','Managers added','Managers cut','New','Exits','Holders','Trend','Largest buyer','Notes'],rows.map(r=>[
  `${tick(r)} <span class="muted">${esc(r.name||r.issuer)}</span>`,`<span class="${r.usd_net>=0?'positive':'negative'}">${smoney(r.usd_net)}</span>`,money(r.usd_add),money(r.usd_sold),
  fmt(r.buyers),fmt(r.sellers),fmt(r.new),fmt(r.exits),fmt(r.holders),columns(d.history?.[r.cusip]),
  r.top_buy[0]?`${esc(r.top_buy[0].manager)}<br><span class="muted">${money(r.top_buy[0].usd)}</span>`:'—',
  [r.split?`split ${r.split>=1?fmt(r.split,2)+'-for-1':'1-for-'+fmt(1/r.split,0)} adjusted`:'',r.converted?.from?'converted from another CUSIP':r.converted?.to?'converted to a new CUSIP':'',r.fund?esc(r.type||'fund'):''].filter(Boolean).join('<br>')||'—']));
 return out;
}

/* ---------- Officials' trades ---------- */
function latestReports(d){                            // the newest House PTRs and whether the collector is keeping up
 const L=d.latest_reports||[],m=d.monitor||{};if(!L.length)return '';
 const behind=(m.lag_days||0)>3||(m.ptr_pending||0)>40;
 let out=`<div class="${behind?'warn-box':'explain'}">${behind?'<b>Catching up.</b> ':''}Newest House transaction report filed ${esc(m.newest_ptr_filed||'—')}; newest one read ${esc(m.newest_ptr_read||'—')}${m.ptr_pending!=null?` · ${fmt(m.ptr_pending)} waiting to be read (newest first)`:''}${m.ptr_last_30_days!=null?` · last 30 days: ${fmt(m.ptr_last_30_days_read)} of ${fmt(m.ptr_last_30_days)} read`:''}. Reports arrive up to 45 days after a trade.</div>`;
 out+=`<details class="panel" ${state.tlatest?'open':''} id="tlatest"><summary><b>Latest reports filed</b> <span class="muted">— the ${fmt(L.length)} newest periodic transaction reports, read or waiting</span></summary>`;
 out+=`<div class="tablebox"><table><thead><tr><th>Filed</th><th>Official</th><th>Status</th><th class="num">Trades read</th><th>Tickers</th><th>Source</th></tr></thead><tbody>${L.map(r=>`<tr><td>${esc(r.filed_date||'')}</td><td>${esc(r.person||'')} <span class="muted">${esc(r.office||'')}</span></td><td><span class="badge ${r.status==='read'?'ready':r.status==='error'?'error':''}">${r.status==='read'?'Read':r.status==='error'?'Failed — retrying':'Waiting'}</span></td><td class="num">${r.status==='read'?`${fmt(r.trades)} <span class="muted">(${fmt(r.buys)} buys · ${fmt(r.sells)} sales)</span>`:'—'}</td><td>${r.tickers.map(t=>tkLink(t)).join(' ')||'—'}</td><td>${link(r.source_url,'PDF ↗')}</td></tr>`).join('')}</tbody></table></div></details>`;
 return out;
}
function tradesView(){
 let out=head("Officials' trades",'Transactions in US House periodic transaction reports, read by machine with the ticker the filer wrote, plus reviewed rows from any jurisdiction. Each ticker is checked against SEC listings.','HOUSE PTR · AUTO-READ');
 const g=marketGate('officials-trades',"Officials' trades");if(!g.data)return out+g.html;
 const d=g.data,all=d.trades||[];
 out+=latestReports(d);
 const people=Object.entries(all.reduce((a,t)=>{a[t.person]=(a[t.person]||0)+1;return a},{})).sort((a,b)=>b[1]-a[1]);
 state.tperson=people.some(p=>p[0]===state.tperson)?state.tperson:'';state.twin=state.twin==='ytd'?'ytd':'d90';
 out+=`<div class="toolbar">${field('tperson','Official',[['','Everyone'],...people.map(([p,n])=>[p,`${p} (${n})`])],state.tperson,true)}${field('ttype','Transaction',[['','All'],['purchase','Purchases'],['sale','Sales (full or partial)'],['exchange','Exchanges']],state.ttype||'')}${field('tcheck','Ticker check',[['','All rows'],['listed','Listed ticker'],['unlisted','Not in listings'],['name','Name differs — check'],['suggested','Has a suggested ticker']],state.tcheck||'')}<div class="field"><label for="tq">Ticker or asset</label><input id="tq" value="${esc(state.tq||'')}" placeholder="e.g. NVDA · Enter"></div></div>`;
 const st=d.stats||{};
 out+=`<div class="metrics">${kpi('Transactions read',fmt(st.trades),`${fmt(st.tickers)} tickers · bonds and private funds left out (${fmt(st['no ticker (bonds, funds, private)'])})`)}${kpi('Ticker listed',st.trades?pct(st.listed/st.trades,1):'—','Found in SEC listings / CUSIP map / price feeds')}${kpi('Name check flagged',fmt(st['name check']),'Listed name and filer’s description differ')}${kpi('Duplicates removed',fmt(st['duplicate (amendment / repeated row)']),'Amendments and repeated rows')}</div>`;
 const sum=(d.summary||{})[state.twin]||[];
 out+=`<div class="panel"><div class="section-head" style="margin:0"><div><h3>Most bought by officials</h3><p class="sub">Officials reporting a purchase, ${state.twin==='ytd'?'this year':'last 90 days'} · options excluded</p></div>${field('twin','Window',[['d90','Last 90 days'],['ytd','Year to date']],state.twin)}</div>${sum.length?divergingChart(sum.slice(0,14).map(r=>({label:r.ticker,value:r.people_buy.length,tip:[[r.ticker,r.name||''],[`${r.buys} purchases`,`by ${r.people_buy.length} official${r.people_buy.length===1?'':'s'}`],[r.people_buy.slice(0,4).join(', '),''],[`${r.sells} sales`,r.people_sell.length?'by '+r.people_sell.slice(0,3).join(', '):'']]})),{unit:'count',label:'Officials reporting purchases by ticker'}):empty('No purchases in this window yet — House reports are read in batches; see Health.')}</div>`;
 const q=(state.tq||'').trim().toLowerCase();
 const rows=all.filter(t=>(!state.tperson||t.person===state.tperson)&&(!state.ttype||(state.ttype==='sale'?/sale/.test(t.type):t.type===state.ttype))
  &&(!state.tcheck||(state.tcheck==='listed'?t.ticker_status==='listed':state.tcheck==='unlisted'?t.ticker_status!=='listed':state.tcheck==='name'?t.name_check==='check':!!t.suggested))
  &&(!q||((t.ticker||'')+' '+(t.asset_raw||'')+' '+(t.listed_name||'')).toLowerCase().includes(q)));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')} Machine-read rows are not reviewed: open the page to confirm. A “name differs” flag means the listed company name does not appear in the filer’s description — often a share class or a renamed company, sometimes a wrong ticker.</div>`;
 out+=`<div class="section-head"><h3>${fmt(rows.length)} transactions</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one transaction');
 out+=table([...(XPOST.on?['X']:[]),'Transaction date','Official','Ticker','Ticker check','Asset as filed','Type','Amount (disclosed range)','Owner','Report filed','Source'],rows.map(t=>[
  ...(XPOST.on?[xBtn('post_official',0,[t.report_id,t.date,t.ticker||'',t.type,t.amount_min??null,t.amount_max??null,t.owner||''],`${t.person}'s ${t.type} of ${t.ticker||'this asset'}`)]:[]),
  esc(t.date),esc(t.person),t.ticker?`${tkLink(t.ticker)}${t.asset_type==='OP'?' <span class="muted">options</span>':''}`:'—',
  `<span class="badge ${t.ticker_status==='listed'?(t.name_check==='check'?'pending':'ready'):'error'}">${esc(t.ticker_status==='listed'?(t.name_check==='check'?'listed · name differs':'listed'):(t.ticker_status||'no ticker'))}</span>${t.listed_name?`<br><span class="muted">${esc(t.listed_name)}</span>`:''}${t.suggested?`<br>Suggested: <b>${esc(t.suggested)}</b> <span class="muted">(${esc(t.confidence)})</span>`:''}`,
  `<span class="mk-asset">${esc(t.asset_raw)}</span>`,`<span class="${t.type==='purchase'?'positive':/sale/.test(t.type)?'negative':''}">${esc(t.type)}</span>`,
  esc(amountLabel(t)),esc(t.owner),esc(t.filed_date||''),link(t.source_url+(t.page?'#page='+t.page:''),(t.read==='reviewed'?'Reviewed · ':'')+'Page '+(t.page||1)+' ↗')]));
 return out;
}

/* ---------- Insider trades (Form 4) ---------- */
function insidersView(){
 let out=head('Insider trades','Open-market purchases and sales by officers, directors and 10% owners, from Form 4 filings (due two business days after the trade) — the most current ownership data the SEC publishes.','SEC / FORM 4');
 const g=marketGate('insiders','Insider trades');if(!g.data)return out+g.html;
 const d=g.data,all=d.latest||[],sum=d.summary||[];
 state.itype=['','P','S'].includes(state.itype)?state.itype:'';state.irole=state.irole||'';
 out+=`<div class="toolbar">${field('itype','Trades',[['','Purchases and sales'],['P','Purchases only'],['S','Sales only']],state.itype)}${field('irole','Who',[['','Everyone'],['ceo','CEO / CFO / President / Chair'],['officer','Any officer'],['Director','Directors'],['10% owner','10% owners']],state.irole)}<div class="field wide"><label for="iq">Ticker, company or insider</label><input id="iq" value="${esc(state.iq||'')}" placeholder="e.g. NVDA · Enter"></div></div>`;
 const buys90=sum.filter(a=>a.buys),cl=sum.filter(a=>a.cluster),big=all.filter(t=>t.code==='P').sort((a,b)=>(b.value||0)-(a.value||0))[0];
 out+=`<div class="metrics">${kpi('Trades on file',fmt(d.trades_on_file),'Since '+(d.since||'—'))}${kpi('Companies with insider buying',fmt(buys90.length),'Open-market purchases, last 90 days')}${kpi('Cluster buys',fmt(cl.length),'3+ insiders bought within 30 days')}${kpi('Largest recent purchase',big?money(big.value):'—',big?`${big.ticker} · ${big.insider} (${big.role}) · ${big.date}`:'')}</div>`;
 const top=buys90.slice().sort((a,b)=>b.buy_value-a.buy_value).slice(0,14);
 out+=`<div class="panel"><h3>Most insider buying, last 90 days</h3><p class="sub">Dollars bought in the open market by officers and directors · hover for who bought</p>${top.length?divergingChart(top.map(a=>({label:a.ticker,value:a.buy_value,tip:[[a.ticker,a.issuer||''],[money(a.buy_value),`bought in ${a.buys} trade${a.buys===1?'':'s'}`],[a.buyers.slice(0,4).join(', '),a.cluster?'cluster buy':'']]}))):empty('No purchases on file yet — the collector reads the newest Form 4 filings every half hour.')}</div>`;
 const q=(state.iq||'').trim().toLowerCase(),CEO=new Set(['CEO','CFO','President','Chair']),OFF=new Set(['CEO','CFO','President','COO','Chair','Officer']);
 const rows=all.filter(t=>(!state.itype||t.code===state.itype)&&(!state.irole||(state.irole==='ceo'?CEO.has(t.role):state.irole==='officer'?OFF.has(t.role):t.role===state.irole))&&(!q||[t.ticker,t.issuer,t.insider].join(' ').toLowerCase().includes(q)));
 exported=rows;
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>${fmt(rows.length)} recent trades</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=xBar('one trade');
 out+=table([...(XPOST.on?['X']:[]),'Trade date','Ticker','Company','Insider','Role','Trade','Shares','Price','Value','Held after','Source'],rows.map(t=>[
  ...(XPOST.on?[xBtn('post_insider',t.issuer_cik,[t.accession,t.date,t.code,t.shares??null,t.price??null],`${t.insider}'s ${t.code==='P'?'purchase':'sale'} of ${t.ticker||t.issuer}`)]:[]),esc(t.date),t.ticker?tkLink(t.ticker,t.issuer_cik):'—',t.issuer_cik?`<a class="tk" href="${esc(coHref(t.ticker,t.issuer_cik))}">${esc(t.issuer)}</a>`:esc(t.issuer),esc(t.insider),esc(t.title||t.role),
  `<span class="${t.code==='P'?'positive':'negative'}">${t.code==='P'?'Purchase':'Sale'}</span>${t.plan_10b5_1?' <span class="muted">10b5-1</span>':''}`,fmt(t.shares),t.price!=null?'$'+fmt(t.price,2):'—',money(t.value),fmt(t.after),link(t.url,'Form 4 ↗')]));
 return out;
}

function bindMarket(){
 for(const k of ['stag','ssort','fwin','funiv','flist','tperson','ttype','tcheck','twin','itype','irole'])bind(k,k);
 for(const k of ['sq','tq','iq'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 bindTips();
}
