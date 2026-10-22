/* Cross-holdings — who holds whom, from public filings: the US government's stakes, the President's 278-T trades, Congress's
   trades, the Trump Accounts' default fund, and the listed companies that file 13F (Alphabet, Nvidia, Amazon, Berkshire …)
   whose own stakes make chains like  Trump Accounts → NVIDIA → Intel ← US government.
   Views: the ownership map (holders → companies that also hold → companies held), one company's holders, the overlap matrix,
   and each holder's detail. Data: data/market/crossholdings.json (app/crossholdings.py, built with the market views).
   Deep links: #cross/INTC (a company), #cross/matrix, #cross/holders. */
const xhStore={};
function xhData(){
 const m=xhStore;
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/market/crossholdings.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;xhIndex(d);render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const XH_KINDS=[['gov','US government','#2f5fae'],['president','President Trump','#c46a1c'],['officials','Congress','#8a3f9a'],['ta','Trump Accounts','#17804f'],['corp','Companies that file 13F','#5d6774']];
const XH_COL=Object.fromEntries(XH_KINDS.map(k=>[k[0],k[2]]));
const XH_VIEWS=[['map','Ownership map'],['company','One company: who holds it'],['matrix','Overlap matrix'],['holders','Each holder in detail']];
const xhShort=n=>String(n||'').replace(/\/[A-Z]{2,4}\/?/g,'').replace(/,?\s*\b(Inc|INC|Corp|CORP|Corporation|CORPORATION|Co|CO|Ltd|LTD|plc|PLC|Group|GROUP|Holdings?|HOLDINGS?|N\.V|SA)\b\.?/g,'').replace(/[,&]\s*$/,'').replace(/\s+/g,' ').trim().slice(0,17);
const xhUsd=v=>v==null||!Number.isFinite(+v)?'—':(v<0?'−':'')+'$'+compact(Math.abs(v));
const xhPct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':fmt(v*100,d)+'%';
function xhIndex(d){
 d._co=Object.fromEntries((d.companies||[]).map(c=>[c.ticker,c]));
 d._hold=Object.fromEntries((d.holders||[]).map(h=>[h.id,h]));
 d._byTicker={};                                  // ticker → [[holder, edge]]
 (d.holders||[]).forEach(h=>(h.edges||[]).forEach(e=>{(d._byTicker[e.ticker]=d._byTicker[e.ticker]||[]).push([h,e])}));
 d._corpByTicker=Object.fromEntries((d.holders||[]).filter(h=>h.kind==='corp'&&h.ticker).map(h=>[h.ticker,h]));
}
function xhCSS(){
 if(document.getElementById('xh-css'))return;
 const s=document.createElement('style');s.id='xh-css';
 s.textContent=`.xh-svg{display:block;width:100%;height:auto;margin-top:8px}.xh-svg text{font:11px var(--sans);fill:var(--ink)}.xh-svg .xh-s{font-size:9.5px;fill:var(--muted)}
 .xh-svg .xh-node{cursor:pointer}.xh-svg .xh-node:hover rect,.xh-svg .xh-node:hover circle{stroke:var(--ink);stroke-width:1.5}.xh-svg path.xh-e{fill:none;stroke-linecap:round}
 .xh-svg path.xh-e:hover{stroke-opacity:.95!important}.xh-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px}.xh-chip{border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:12px;background:var(--surface);cursor:pointer;display:inline-flex;align-items:center;gap:6px;color:var(--ink)}
 .xh-chip i{width:10px;height:10px;border-radius:3px;background:var(--c)}.xh-chip.off{opacity:.45}.xh-chip.off i{background:transparent;border:1px solid var(--c)}
 .xh-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:12px 0}.xh-card{border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:10px 12px;background:var(--surface)}
 .xh-card h4{margin:0 0 4px;font-size:13px}.xh-card ul{margin:6px 0 0;padding-left:16px;font-size:12.5px}.xh-card li{margin:2px 0}.xh-card .sub{margin:0}
 .xh-mx{overflow:auto;max-width:100%}.xh-mx table{border-collapse:collapse;font-size:12px}.xh-mx th,.xh-mx td{border-bottom:1px solid var(--line);padding:4px 7px;text-align:right;white-space:nowrap}
 .xh-mx th:first-child,.xh-mx td:first-child{text-align:left;position:sticky;left:0;background:var(--surface)}.xh-mx thead th{font-weight:600;vertical-align:bottom}.xh-mx td.on{background:color-mix(in srgb,var(--c) 16%,transparent)}
 .xh-chain{font-size:12.5px;margin:3px 0}.xh-chain b{white-space:nowrap}.xh-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}.xh-scroll .xh-svg{min-width:900px}
 @media (max-width:640px){.xh-cards{grid-template-columns:1fr}}`;
 document.head.appendChild(s);
}
function xhKinds(){const on=(state.xhk==null?'gov,president,officials,ta,corp':state.xhk).split(',').filter(Boolean);return new Set(on)}
function xhChips(){
 const on=xhKinds();
 return `<div class="xh-chips">${XH_KINDS.map(([k,l,c])=>`<button type="button" class="xh-chip${on.has(k)?'':' off'}" style="--c:${c}" data-xhk="${k}" aria-pressed="${on.has(k)}"><i></i>${esc(l)}</button>`).join('')}</div>`;
}
function crossView(){
 xhCSS();
 const m=xhData();
 if(m.err)return empty('Cross-holdings could not load ('+m.err+'). The file is rebuilt with the market views every few hours.');
 if(!m.data)return empty('Loading cross-holdings…');
 const d=m.data;
 state.xhv=XH_VIEWS.some(v=>v[0]===state.xhv)?state.xhv:'map';
 if(!state.xht){const first=(d.companies||[]).find(c=>(d._byTicker[c.ticker]||[]).length>=3);state.xht=first?first.ticker:((d.companies||[])[0]||{}).ticker}
 const H=d._hold,gov=H.gov||{edges:[]},pres=H.president||{edges:[]},off=H.officials||{edges:[]},ta=H.ta||{edges:[]};
 const corps=(d.holders||[]).filter(h=>h.kind==='corp');
 const govVal=gov.edges.reduce((a,e)=>a+(e.usd||0),0);
 let out=`<div class="section-head"><div><h2>Cross-holdings: who holds whom</h2><p class="sub">The holders whose stakes are public — the US government, the President, Congress, the Trump Accounts — and the listed companies that file 13F and so hold each other. Built ${esc((d.generated_at||'').slice(0,16).replace('T',' '))} UTC · 13F quarter ${esc(d.quarter||'—')}.</p></div><span class="tag">Public filings</span></div>`;
 out+=`<div class="metrics">${kpi('US government',xhUsd(govVal),`${fmt(gov.edges.length)} listed companies + ${fmt((gov.private||[]).length)} private`)}${kpi('President Trump',pres.pending?'reading…':fmt(pres.trades)+' trades',pres.pending?'OGE 278-T scans, OCR in progress':`${fmt(pres.with_ticker)} with a listed ticker · ${esc((pres.span||[]).join(' – '))}`)}${kpi('Congress',fmt(off.edges.length)+' stocks',`net trades since ${esc(off.since||'—')}`)}${kpi('Trump Accounts',ta.pending?'—':esc(ta.fund||'SPYM'),ta.pending?'holdings file not read yet':`${fmt(ta.holdings)} holdings · default fund`)}${kpi('Companies that file 13F',fmt(corps.length),'operating companies investing their own money')}</div>`;
 out+=`<div class="toolbar">${field('xhv','View',XH_VIEWS,state.xhv,true)}${state.xhv==='company'?`<div class="field"><label for="xht">Company (ticker)</label><input id="xht" value="${esc(state.xht||'')}" list="xh-tickers"><datalist id="xh-tickers">${(d.companies||[]).map(c=>`<option value="${esc(c.ticker)}">${esc(c.name||'')}</option>`).join('')}</datalist></div>`:''}${state.xhv==='map'?field('xhn','Companies held',[['25','25 largest'],['40','40 largest'],['70','70 largest'],['120','120 largest']],String(state.xhn||40)):''}</div>`;
 if(state.xhv!=='company')out+=xhChips();
 out+=({map:xhMap,company:xhCompany,matrix:xhMatrix,holders:xhHolders}[state.xhv])(d);
 out+=`<div class="explain">${esc(d.note||'')}</div>`;
 return out;
}
// ---------------------------------------------------------------- the ownership map
function xhWidth(h,e,maxW){
 if(h.kind==='ta')return 1+9*Math.min(1,(e.weight||0)/(maxW||1));
 const v=Math.abs(e.usd||0);if(!v)return 1;
 return Math.max(1,Math.min(14,1+13*(Math.log10(v)-5)/6));
}
function xhMap(d){
 const on=xhKinds(),N=+(state.xhn||40);
 const top=(d.holders||[]).filter(h=>['gov','president','officials','ta'].includes(h.kind)&&on.has(h.kind)&&(h.edges||[]).length);
 const heldTop=new Set();(d.holders||[]).filter(h=>['gov','president','officials','ta'].includes(h.kind)&&on.has(h.kind)).forEach(h=>h.edges.slice(0,h.kind==='officials'?25:h.kind==='president'?30:h.kind==='ta'?15:40).forEach(e=>heldTop.add(e.ticker)));
 const corps=on.has('corp')?(d.holders||[]).filter(h=>h.kind==='corp'&&h.ticker&&(h.edges||[]).length&&(h.total>=3e8||heldTop.has(h.ticker))):[];
 const mid=new Set(corps.map(h=>h.ticker));
 // the companies held: weigh each edge by its share of the holder's largest edge, so a $1B stake and a $15K trade both count
 const sc={};
 const lim=h=>h.kind==='officials'?25:h.kind==='president'?30:h.kind==='ta'?15:h.kind==='gov'?40:12;
 [...top,...corps].forEach(h=>{const es=h.edges.slice(0,lim(h));const mx=Math.max(...es.map(e=>Math.abs(e.usd||e.weight||0)),1);es.forEach(e=>{if(mid.has(e.ticker))return;sc[e.ticker]=(sc[e.ticker]||0)+.35+Math.abs(e.usd||e.weight||0)/mx})});
 const right=Object.keys(sc).sort((a,b)=>sc[b]-sc[a]).slice(0,N);
 const R=new Set(right);
 if(!top.length&&!corps.length)return empty('Turn on at least one kind of holder.');
 const W=1000,rowR=19,rowM=24,y0=46;
 const midList=corps.slice().sort((a,b)=>b.total-a.total);
 const H=Math.max(y0+top.length*90,y0+midList.length*rowM,y0+right.length*rowR)+30;
 const xA=110,xB=470,xC=800;
 const yA={},yB={},yC={};
 top.forEach((h,i)=>{yA[h.id]=y0+(H-y0-30)*(i+.5)/top.length});
 // order the middle column by where its holders sit, the right column by where its holders sit
 const bary=(t,src)=>{let s=0,n=0;src.forEach(h=>{const e=h.edges.slice(0,lim(h)).find(x=>x.ticker===t);if(e){s+=(yA[h.id]!=null?yA[h.id]:yB[h.ticker]||0);n++}});return n?s/n:H/2};
 midList.sort((a,b)=>bary(a.ticker,top)-bary(b.ticker,top)||b.total-a.total).forEach((h,i)=>{yB[h.ticker]=y0+(H-y0-30)*(i+.5)/Math.max(1,midList.length)});
 const rsorted=right.slice().sort((a,b)=>bary(a,[...top,...midList])-bary(b,[...top,...midList]));
 rsorted.forEach((t,i)=>{yC[t]=y0+(H-y0-30)*(i+.5)/Math.max(1,rsorted.length)});
 const maxTA=Math.max(...((d._hold.ta||{}).edges||[]).map(e=>e.weight||0),1e-9);
 let s=`<svg class="xh-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ownership map: public holders, companies that also hold, companies held">`;
 s+=`<text x="${xA}" y="18" text-anchor="middle" class="xh-s">PUBLIC HOLDERS</text><text x="${xB}" y="18" text-anchor="middle" class="xh-s">COMPANIES THAT HOLD OTHERS (13F)</text><text x="${xC+10}" y="18" class="xh-s">COMPANIES HELD</text>`;
 const edge=(x1,y1,x2,y2,w,c,dash,tip)=>{const mx=(x1+x2)/2;return `<path class="xh-e" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" stroke="${c}" stroke-opacity=".38" stroke-width="${w.toFixed(1)}"${dash?' stroke-dasharray="4 3"':''}><title>${esc(tip)}</title></path>`};
 const tipOf=(h,e)=>h.kind==='ta'?`${h.label} → ${e.ticker}: ${xhPct(e.weight,2)} of the default fund ($${fmt(e.per_1000,2)} of every $1,000)`:
  h.kind==='gov'?`US government → ${e.ticker}: ${e.instrument||''} · ${e.pct||''} · ${xhUsd(e.usd)} (${e.basis||'—'}) · ${e.status}`:
  h.kind==='president'?`President → ${e.ticker}: ${fmt(e.buys)} purchases ${xhUsd(e.buy_mid)}, ${fmt(e.sells)} sales ${xhUsd(e.sell_mid)} (range midpoints), net ${xhUsd(e.usd)}`:
  h.kind==='officials'?`Congress → ${e.ticker}: net ${xhUsd(e.usd)} (${fmt(e.buyers)} buying, ${fmt(e.sellers)} selling members)`:
  `${h.label} → ${e.ticker}: ${xhUsd(e.usd)}${e.pct_out!=null?' · '+xhPct(e.pct_out,2)+' of shares':''} (13F ${h.as_of})`;
 // edges first, nodes on top
 top.forEach(h=>h.edges.slice(0,lim(h)).forEach(e=>{
  const y2=mid.has(e.ticker)?yB[e.ticker]:R.has(e.ticker)?yC[e.ticker]:null;if(y2==null)return;
  const x2=mid.has(e.ticker)?xB-78:xC;
  s+=edge(xA+62,yA[h.id],x2,y2,xhWidth(h,e,maxTA),XH_COL[h.kind],(e.usd||0)<0||['loi','conditional'].includes(e.status),tipOf(h,e));
 }));
 midList.forEach(h=>h.edges.slice(0,12).forEach(e=>{
  if(R.has(e.ticker))s+=edge(xB+78,yB[h.ticker],xC,yC[e.ticker],xhWidth(h,e),XH_COL.corp,false,tipOf(h,e));
  else if(mid.has(e.ticker)&&e.ticker!==h.ticker){const a=yB[h.ticker],b=yB[e.ticker],bend=xB+120+Math.min(120,Math.abs(a-b)/3);
   s+=`<path class="xh-e" d="M${xB+78},${a} C${bend},${a} ${bend},${b} ${xB+78},${b}" stroke="${XH_COL.corp}" stroke-opacity=".5" stroke-width="${xhWidth(h,e).toFixed(1)}"><title>${esc(tipOf(h,e))}</title></path>`}
 }));
 top.forEach(h=>{const y=yA[h.id],n=h.edges.length;
  s+=`<g class="xh-node" data-xhh="${esc(h.id)}"><rect x="${xA-62}" y="${y-22}" width="124" height="44" rx="8" fill="${XH_COL[h.kind]}" fill-opacity=".14" stroke="${XH_COL[h.kind]}"/><text x="${xA}" y="${y-3}" text-anchor="middle" style="font-weight:600">${esc(h.label.replace(' (net trades)',''))}</text><text x="${xA}" y="${y+12}" text-anchor="middle" class="xh-s">${h.kind==='ta'?esc(h.fund||'')+' · per $1,000':fmt(n)+' companies'}</text></g>`});
 midList.forEach(h=>{const y=yB[h.ticker],held=(d._byTicker[h.ticker]||[]).filter(([x])=>x.kind!=='corp'||x.ticker!==h.ticker).length;
  s+=`<g class="xh-node" data-xht="${esc(h.ticker)}"><rect x="${xB-78}" y="${y-9}" width="156" height="18" rx="5" fill="var(--surface)" stroke="${XH_COL.corp}"/><text x="${xB-72}" y="${y+4}"><tspan style="font-weight:600">${esc(h.ticker)}</tspan> <tspan class="xh-s">${esc(xhShort(h.label))}</tspan></text><title>${esc(h.label)} · 13F ${esc(h.as_of)}: ${xhUsd(h.total)} in ${fmt(h.positions)} positions · held by ${fmt(held)} of the public holders</title></g>`});
 rsorted.forEach(t=>{const y=yC[t],c=d._co[t]||{},k=(d._byTicker[t]||[]).filter(([h])=>on.has(h.kind)).length;
  s+=`<g class="xh-node" data-xht="${esc(t)}"><circle cx="${xC+4}" cy="${y}" r="${3+Math.min(5,k)}" fill="${k>=3?'var(--mk-profit,#17734a)':'var(--muted)'}" fill-opacity=".8"/><text x="${xC+14}" y="${y+4}"><tspan style="font-weight:600">${esc(t)}</tspan> <tspan class="xh-s">${esc((c.name||'').slice(0,28))}</tspan></text><title>${esc(t)} ${esc(c.name||'')}: ${fmt(k)} of the holders shown</title></g>`});
 s+='</svg>';
 let out=`<div class="panel"><h3>The ownership map</h3><p class="sub">Left: holders whose stakes are public. Middle: listed companies that file 13F — held by the left, holders themselves. Right: what they hold. Line width: dollars on a log scale (a $15K trade and a $30B stake both show); Trump Accounts: the fund weight. Dashed: net selling, or a stake not yet delivered. Click a company for its holders.</p><div class="xh-scroll">${s}</div></div>`;
 const both=midList.filter(h=>(d._byTicker[h.ticker]||[]).some(([x])=>x.ticker!==h.ticker&&on.has(x.kind)));
 const fx=(x,e)=>x.kind==='ta'?'$'+fmt(e.per_1000,1)+'/$1k':x.kind==='gov'?(e.pct||xhUsd(e.usd)):xhUsd(e.usd);
 if(both.length)out+=`<div class="panel"><h3>Held, and holding: the links in the chains (${fmt(both.length)})</h3><p class="sub">Each of these companies is held by the public holders shown and holds stakes of its own — the middle of chains like Trump Accounts → NVIDIA → Intel.</p>${table(['Company','Held by','Holds (its 13F)'],both.map(h=>[`<button class="text-button" data-xht="${esc(h.ticker)}"><b>${esc(h.ticker)}</b></button> <span class="muted">${esc(xhShort(h.label))}</span>`,
  (d._byTicker[h.ticker]||[]).filter(([x])=>x.ticker!==h.ticker&&on.has(x.kind)).map(([x,e])=>`<span style="color:${XH_COL[x.kind]}">${esc(x.kind==='corp'?x.ticker:x.label.replace(' (net trades)',''))}</span> ${esc(fx(x,e))}`).join(' · '),
  h.edges.slice(0,5).map(e=>`<b>${esc(e.ticker)}</b> ${xhUsd(e.usd)}${e.pct_out!=null?' ('+xhPct(e.pct_out,1)+')':''}`).join(' · ')]))}</div>`;
 return out;
}
// ---------------------------------------------------------------- one company
function xhCompany(d){
 const t=(state.xht||'').toUpperCase(),c=d._co[t];
 const hs=d._byTicker[t]||[],corp=d._corpByTicker[t];
 if(!c&&!hs.length&&!corp)return empty(`${t||'That ticker'} is not on the map. The map holds the companies the public holders and the 13F-filing companies hold.`);
 let out=`<div class="section-head"><div><h2>${esc(t)} <span class="muted">${esc((c||{}).name||'')}</span></h2><p class="sub">${c&&c.price?'Close $'+fmt(c.price,2)+' ('+esc(c.price_date||'')+')':''}${c&&c.mcap?' · market value '+xhUsd(c.mcap):''}${c&&c.shares_out?' · '+fmt(c.shares_out)+' shares outstanding (SEC cover page)':''}</p></div><span class="tag">${fmt(hs.length)} public holders</span></div>`;
 if(c)out+=`<div class="metrics">${kpi('13F managers holding it',fmt(c.f13_holders),'latest 13F of each manager')}${kpi('Their shares',c.f13_pct==null?xhUsd(c.f13_usd):xhPct(c.f13_pct,1)+' of shares',c.f13_pct==null?'value in their 13F':xhUsd(c.f13_usd))}${kpi('Public holders',fmt(hs.length),'government, President, Congress, Trump Accounts, companies')}${corp?kpi('It holds',fmt(corp.positions)+(corp.positions===1?' company':' companies'),xhUsd(corp.total)+' in its 13F'):''}</div>`;
 const card=(k,title,body)=>`<div class="xh-card" style="--c:${XH_COL[k]}"><h4>${esc(title)}</h4>${body}</div>`;
 const cards=[];
 hs.forEach(([h,e])=>{
  if(h.kind==='gov')cards.push(card('gov','US government · '+(e.agency||''),`<p class="sub">${esc(e.instrument||'')}</p><ul><li>Stake: <b>${esc(e.pct||'—')}</b> · status ${esc(e.status||'')}${e.scope?' ('+esc(e.scope)+')':''}</li><li>Value: <b>${xhUsd(e.usd)}</b> <span class="muted">${esc(e.basis||'')}</span>${e.cost_usd?' · invested '+xhUsd(e.cost_usd):''}</li><li>Announced ${esc(e.announced||'')}${e.source?` · <a href="${esc(e.source)}" target="_blank" rel="noopener">source ↗</a>`:''}</li>${e.how?`<li>${esc(e.how)}</li>`:''}</ul>`));
  else if(h.kind==='president')cards.push(card('president','President Trump · OGE 278-T',`<ul><li>${fmt(e.buys)} purchases ${xhUsd(e.buy_mid)} · ${fmt(e.sells)} sales ${xhUsd(e.sell_mid)}</li><li>Net <b>${xhUsd(e.usd)}</b> at range midpoints</li><li>${esc(e.first)} – ${esc(e.last)}</li></ul><p class="sub">Read by OCR from the scanned reports; amounts are ranges.</p>`));
  else if(h.kind==='officials')cards.push(card('officials','Congress · since '+(h.since||''),`<ul><li>Net <b>${xhUsd(e.usd)}</b> (bought ${xhUsd(e.buy_mid)}, sold ${xhUsd(e.sell_mid)})</li><li>${fmt(e.buyers)} buying, ${fmt(e.sellers)} selling · ${fmt(e.trades)} trades</li><li>${esc((e.people||[]).join(', '))}</li></ul>`));
  else if(h.kind==='ta')cards.push(card('ta','Trump Accounts · '+(h.fund||''),`<ul><li><b>${xhPct(e.weight,2)}</b> of the default fund</li><li>$${fmt(e.per_1000,2)} of every $1,000 in an account</li></ul>`));
  else cards.push(card('corp',h.label+' (13F '+h.as_of+')',`<ul><li><b>${xhUsd(e.usd)}</b> · ${fmt(e.shares)} shares${e.pct_out!=null?' · <b>'+xhPct(e.pct_out,2)+'</b> of shares':''}</li><li>${xhPct(e.weight,1)} of its 13F portfolio</li></ul><button class="text-button" data-xht="${esc(h.ticker)}">${esc(h.ticker)} →</button>`));
 });
 if(cards.length)out+=`<div class="xh-cards">${cards.join('')}</div>`;
 if(c&&(c.top_institutions||[]).length)out+=`<div class="panel"><h3>Largest 13F managers holding ${esc(t)}</h3>${table(['Manager','Value','Shares','% of shares','13F quarter'],c.top_institutions.map(r=>[esc(r.name)+(r.ticker?` <span class="muted">(${esc(r.ticker)})</span>`:''),xhUsd(r.usd),fmt(r.shares),xhPct(r.pct,2),esc(r.period)]))}</div>`;
 if(corp)out+=`<div class="panel"><h3>What ${esc(t)} holds (its own 13F, ${esc(corp.as_of)})</h3>${table(['Company','Value','Shares','% of shares','Weight'],corp.edges.slice(0,30).map(e=>[`<button class="text-button" data-xht="${esc(e.ticker)}"><b>${esc(e.ticker)}</b></button> <span class="muted">${esc(((d._co[e.ticker]||{}).name)||e.issuer||'')}</span>`,xhUsd(e.usd),fmt(e.shares),xhPct(e.pct_out,2),xhPct(e.weight,1)]))}</div>`;
 const ch=(d.chains||[]).filter(x=>x.via===t||x.to===t).slice(0,20);
 if(ch.length)out+=`<div class="panel"><h3>Chains through ${esc(t)}</h3>${ch.map(x=>`<div class="xh-chain">${esc((d._hold[x.from]||{}).label||x.from)} → <b>${esc(x.via)}</b> → <b>${esc(x.to)}</b> ${xhUsd(x.usd2)}</div>`).join('')}</div>`;
 return out;
}
// ---------------------------------------------------------------- overlap matrix
function xhMatrix(d){
 const on=xhKinds();
 const cols=(d.holders||[]).filter(h=>on.has(h.kind)&&(h.edges||[]).length);
 const lim=h=>h.kind==='ta'?50:h.kind==='officials'?80:h.kind==='president'?80:999;
 const rows={};
 cols.forEach((h,j)=>h.edges.slice(0,lim(h)).forEach(e=>{(rows[e.ticker]=rows[e.ticker]||{})[h.id]=e}));
 const list=Object.entries(rows).filter(([,r])=>Object.keys(r).length>=2).sort((a,b)=>Object.keys(b[1]).length-Object.keys(a[1]).length||a[0].localeCompare(b[0])).slice(0,80);
 const used=cols.filter(h=>list.some(([,r])=>r[h.id]));
 if(!list.length)return empty('No company is held by two of the holders shown.');
 const cell=(h,e)=>!e?'':h.kind==='ta'?'$'+fmt(e.per_1000,1):h.kind==='gov'?(e.pct||'✓'):xhUsd(e.usd);
 exported=list.map(([t,r])=>Object.fromEntries([['ticker',t],...used.map(h=>[h.label,r[h.id]?(r[h.id].usd??r[h.id].per_1000??''):''])]));
 return `<div class="panel"><h3>Companies held by two or more of them (${fmt(list.length)})</h3><p class="sub">Cells: dollars (13F value, government stake value, net trades at range midpoints); Trump Accounts: dollars per $1,000 in an account; government: the stake.</p><div class="xh-mx"><table><thead><tr><th>Company</th>${used.map(h=>`<th style="color:${XH_COL[h.kind]}">${esc(h.kind==='corp'?h.ticker||h.label:h.label.replace(' (net trades)',''))}</th>`).join('')}</tr></thead><tbody>${list.map(([t,r])=>`<tr><td><button class="text-button" data-xht="${esc(t)}"><b>${esc(t)}</b></button> <span class="muted">${esc(((d._co[t]||{}).name||'').slice(0,26))}</span></td>${used.map(h=>`<td class="${r[h.id]?'on':''}" style="--c:${XH_COL[h.kind]}">${cell(h,r[h.id])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
}
// ---------------------------------------------------------------- each holder
function xhHolders(d){
 const on=xhKinds(),H=d._hold;let out='';
 const tk=t=>`<button class="text-button" data-xht="${esc(t)}"><b>${esc(t)}</b></button>`;
 const gov=H.gov;
 if(gov&&on.has('gov'))out+=`<div class="panel"><h3 style="color:${XH_COL.gov}">US government (as of ${esc(gov.as_of||'')})</h3><p class="sub">${esc(gov.note||'')}</p>${table(['Company','Agency','What it holds','Stake','Value','Status','Announced','Source'],gov.edges.slice().sort((a,b)=>(b.usd||0)-(a.usd||0)).map(e=>[tk(e.ticker)+' <span class="muted">'+esc(e.name||'')+'</span>',esc(e.agency),esc(e.instrument),esc(e.pct||'—'),xhUsd(e.usd)+(e.basis?` <span class="muted">${esc(e.basis)}</span>`:''),esc(e.status)+(e.scope?' · '+esc(e.scope):''),esc(e.announced),e.source?`<a href="${esc(e.source)}" target="_blank" rel="noopener">filing ↗</a>`:'']))}${(gov.private||[]).length?`<h4>Private companies and joint ventures</h4>${table(['Company','Agency','What it holds','Amount','Status','Announced'],gov.private.map(e=>[esc(e.name),esc(e.agency),esc(e.instrument),xhUsd(e.cost_usd),esc(e.status),esc(e.announced)]))}`:''}</div>`;
 const p=H.president;
 if(p&&on.has('president'))out+=`<div class="panel"><h3 style="color:${XH_COL.president}">President Trump — OGE Form 278-T</h3><p class="sub">${esc(p.note||'')}</p>${table(['Report','Filed','Kind','Pages read','Rows','Rows read','PDF'],(p.filings||[]).map(f=>[esc(f.name),esc(f.filed||''),esc(f.kind),f.pages?fmt(f.pages_read)+' / '+fmt(f.pages)+(f.ocr_pages?` <span class="sub">(${fmt(f.ocr_pages)} by OCR)</span>`:''):'—',f.rows==null?'—':fmt(f.rows),f.coverage==null?'—':Math.round(f.coverage*100)+'%',`<a href="${esc(f.url)}" target="_blank" rel="noopener">OGE ↗</a>`]))}${p.edges.length?table(['Company','Purchases','Bought (mid)','Sales','Sold (mid)','Net','First','Last'],p.edges.slice(0,40).map(e=>[tk(e.ticker),fmt(e.buys),xhUsd(e.buy_mid),fmt(e.sells),xhUsd(e.sell_mid),xhUsd(e.usd),esc(e.first),esc(e.last)])):empty('The reports are being read (a page budget each run); trades appear here as they are parsed.')}</div>`;
 const o=H.officials;
 if(o&&on.has('officials'))out+=`<div class="panel"><h3 style="color:${XH_COL.officials}">Congress — net trades since ${esc(o.since||'')}</h3><div class="charts"><div>${table(['Company','Net','Bought','Sold','Members buying','Selling'],o.edges.slice(0,30).map(e=>[tk(e.ticker),xhUsd(e.usd),xhUsd(e.buy_mid),xhUsd(e.sell_mid),fmt(e.buyers),fmt(e.sellers)]))}</div><div>${table(['Most active','Bought','Sold','Largest nets'],(o.people||[]).map(r=>[esc(r.person)+` <span class="muted">${esc(r.jurisdiction||'')}</span>`,xhUsd(r.buy_mid),xhUsd(r.sell_mid),esc((r.top||[]).slice(0,3).map(x=>x[0]+' '+(x[1]<0?'−':'+')+'$'+compact(Math.abs(x[1]))).join(', '))]))}</div></div></div>`;
 const ta=H.ta;
 if(ta&&on.has('ta'))out+=`<div class="panel"><h3 style="color:${XH_COL.ta}">Trump Accounts</h3><p class="sub">${esc(ta.note||'')} Treasury's lineup (${esc(ta.lineup_date||'')}, <a href="${esc(ta.lineup_source||'#')}" target="_blank" rel="noopener">release ↗</a>): ${(ta.lineup||[]).map(f=>`<b>${esc(f[0])}</b> ${esc(f[1])}`).join(' · ')}.</p>${ta.edges.length?table(['Company','Weight','Per $1,000'],ta.edges.slice(0,30).map(e=>[tk(e.ticker),xhPct(e.weight,2),'$'+fmt(e.per_1000,2)])):empty('The default fund’s holdings file has not been read yet.')}<p class="sub">Holdings: ${esc(ta.fund||'—')} as of ${esc(ta.as_of||'—')}${ta.source?` (<a href="${esc(ta.source)}" target="_blank" rel="noopener">file ↗</a>)`:''}.</p></div>`;
 const corps=(d.holders||[]).filter(h=>h.kind==='corp');
 if(corps.length&&on.has('corp'))out+=`<div class="panel"><h3 style="color:${XH_COL.corp}">Companies that file 13F</h3><p class="sub">Listed operating companies (and Berkshire Hathaway, SoftBank) whose 13F reports their own stakes. Banks, insurers and asset managers that file 13F report clients' money and are counted among the 13F managers instead.</p>${table(['Company','Industry','13F quarter','13F value','Positions','Largest holdings'],corps.map(h=>[tk(h.ticker||'')+' '+esc(h.label),esc(h.sic_desc||''),esc(h.as_of),xhUsd(h.total),fmt(h.positions),esc(h.edges.slice(0,4).map(e=>e.ticker+' '+xhUsd(e.usd)).join(', '))]))}</div>`;
 if((d.institutions||[]).length)out+=`<div class="panel"><h3>The largest 13F managers (in each company's holder list)</h3>${table(['Manager','13F value','Quarter'],d.institutions.map(r=>[esc(r.name)+(r.ticker?` <span class="muted">(${esc(r.ticker)})</span>`:''),xhUsd(r.total),esc(r.period)]))}</div>`;
 return out||empty('Turn on at least one kind of holder.');
}
function bindCross(){
 if(state.tab!=='cross')return;
 if($('xhv'))$('xhv').onchange=e=>{state.xhv=e.target.value;render()};
 if($('xhn'))$('xhn').onchange=e=>{state.xhn=e.target.value;render()};
 if($('xht')){$('xht').onchange=e=>{state.xht=e.target.value.trim().toUpperCase();render()};$('xht').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-xhk]').forEach(b=>b.onclick=()=>{const on=xhKinds();on.has(b.dataset.xhk)?on.delete(b.dataset.xhk):on.add(b.dataset.xhk);state.xhk=[...on].join(',');render()});
 document.querySelectorAll('#workspace [data-xht]').forEach(b=>b.onclick=()=>{state.xht=b.dataset.xht;state.xhv='company';try{history.replaceState(null,'','#cross/'+encodeURIComponent(state.xht))}catch(e){}render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-xhh]').forEach(b=>b.onclick=()=>{state.xhk=b.dataset.xhh==='officials'?'officials':b.dataset.xhh;state.xhv='holders';render()});
}
/* deep links: disclosures/#cross/INTC, #cross/matrix, #cross/holders */
function crossDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(XH_VIEWS.some(x=>x[0]===v))state.xhv=v;else{state.xht=v.toUpperCase();state.xhv='company'}
}
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{cross:crossView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{cross:bindCross});
