/* 4.13 ETFs — a screener and research page for every US-listed ETF, read from its own filings (prospectus risk/return
   summary, N-PORT portfolio and flows, N-CEN census with authorized participants and service providers), the market,
   and the rest of the Hub (13F holders, officials' trades, short interest, N-PX, and the companies inside through the
   consensus, 13F flows, officials, insiders and debt data).
   Data: data/etf/{index,parties,status}.json, data/etf/e/<SYMBOL>.json, data/etf/by/<TICKER>.json (app/etf.py, branch etf-history). */
const etfStore={};
function etfData(name){
 const m=etfStore[name]||(etfStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/etf/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function etfGate(name,title){
 const m=etfData(name);
 if(m.err)return {html:empty(`${title} could not load (${m.err}). The ETF collector runs every few hours; the filings sets are read once a quarter.`)};
 if(!m.data)return {html:empty(`Loading ${title.toLowerCase()}…`)};
 return {data:m.data};
}
const ETF_VIEWS=[['screen','Screener — every US-listed ETF'],['one','One ETF'],['overlap','Compare two ETFs (overlap)'],['holds','Which ETFs hold a stock'],['parties','The parties behind ETFs']];
const ETF_AC=[['','All asset classes'],['Equity','Equity'],['Fixed income','Fixed income'],['Leveraged / inverse','Leveraged / inverse'],['Crypto','Crypto'],['Commodity','Commodities'],['Commodity: precious metals','Precious metals'],['Multi-asset / alternatives','Multi-asset / alternatives'],['Multi-asset (fund of funds)','Funds of funds'],['Volatility','Volatility'],['Currency','Currency'],['ETN','ETNs'],['Other','Not classified yet']];
const ETF_STRAT=[['','Passive and active'],['passive','Passive (index)'],['active','Active'],['options','Option income / buffer']];
const ETF_LEV=[['','Any'],['no','None (1×)'],['only','Leveraged or inverse'],['long','Leveraged (long)'],['inv','Inverse (short)'],['2','2×'],['3','3×'],['-1','−1×'],['-2','−2×'],['-3','−3×'],['single','Single-stock funds']];
// tags (data/etf/index.json tag_names: id → [label, group]); the row chips show these groups first
const ETF_TAG_SHOW=['Management','Leverage','Income','Alternatives'];
const ETF_TAG_QUICK=['div-high','div-growth','opt-income','pay-monthly','alt','alt-crypto','alt-commodity','alt-metals','bond-treasury','bond-cash','bond-hy','em','th-ai'];
const ETF_TAG_CLASS={Management:'g-man',Leverage:'g-lev',Income:'g-inc',Alternatives:'g-alt',Bonds:'g-bond',Region:'g-reg'};
function etfTagName(id,names){const n=(names||{})[id];return n?n[0]:id}
function etfChip(id,names,extra=''){const g=((names||{})[id]||[])[1]||'';return `<button class="tag etf-tag ${ETF_TAG_CLASS[g]||''}" data-etag="${esc(id)}" title="${esc(g)}">${esc(etfTagName(id,names))}${extra}</button>`}
function etfRowTags(r,names){
 const t=r.tags||[];if(!t.length)return '';
 const lev=t.find(x=>x.startsWith('lev:')),pick=t.filter(x=>ETF_TAG_SHOW.includes(((names||{})[x]||[])[1])&&!(lev&&(x==='lev'||x==='inv'))&&x!=='alt'||(x==='alt'&&!t.some(y=>y.startsWith('alt-'))));
 return `<div class="etf-tags">${pick.slice(0,5).map(x=>etfChip(x,names,x==='single'&&r.under?' · '+esc(r.under):'')).join('')}</div>`;
}
function etfTagField(data,rows){
 const names=data.tag_names||{},groups=(data.tag_groups||[]).filter(g=>!['Management','Leverage'].includes(g)),cnt={};
 for(const r of rows)for(const t of r.tags||[])cnt[t]=(cnt[t]||0)+1;
 const opts=groups.map(g=>{const ids=Object.keys(names).filter(id=>names[id][1]===g&&cnt[id]);return ids.length?`<optgroup label="${esc(g)}">${ids.map(id=>`<option value="${esc(id)}" ${state.etag===id?'selected':''}>${esc(names[id][0])} (${fmt(cnt[id])})</option>`).join('')}</optgroup>`:''}).join('');
 return `<div class="field"><label for="etag">Tag</label><select id="etag"><option value="">Any tag</option>${opts}</select></div>`;
}
const ETF_SORT=[['aum','Largest'],['flows_3m','Biggest inflows, 3 months'],['flows_3m_low','Biggest outflows, 3 months'],['expense','Cheapest'],['r1y','Best 1-year return'],['holders13f','Most 13F holders'],['lt_target','Analysts\' upside of the holdings'],['officials_1y','Most officials\' trades']];
const ETF_PARTY=[['aps','Authorized participants'],['custodians','Custodians'],['lending','Securities-lending agents'],['advisers','Advisers'],['subadvisers','Sub-advisers'],['auditors','Auditors'],['distributors','Distributors'],['administrators','Administrators'],['transfer','Transfer agents']];
const ASSET_NAMES={EC:'Common equity',EP:'Preferred equity',DBT:'Debt',  'ABS-MBS':'Mortgage-backed','ABS-O':'Other asset-backed','ABS-CBDO':'CDO / CLO','ABS-APCP':'Asset-backed CP',STIV:'Short-term vehicles',RA:'Repos',LON:'Loans',DCO:'Commodity derivatives',DCR:'Credit derivatives',DE:'Equity derivatives',DFE:'FX derivatives',DIR:'Rate derivatives',DO:'Other derivatives',COMM:'Commodities',RE:'Real estate',SN:'Structured notes',OTHER:'Other'};
const etfMoney=v=>v==null||!Number.isFinite(+v)?'—':(v<0?'−':'')+'$'+(Math.abs(v)>=1e12?fmt(Math.abs(v)/1e12,2)+'T':compact(Math.abs(v)));
const etfSpct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':`<span class="${v>0?'positive':v<0?'negative':''}">${(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)}%</span>`;
const etfPct=(v,d=2)=>v==null||!Number.isFinite(+v)?'—':fmt(v*100,d)+'%';
const etfTk=s=>`<button class="text-button" data-etf="${esc(s)}"><b>${esc(s)}</b></button>`;
function etfTbl(head,rows,num=[]){return `<div class="tablebox"><table><thead><tr>${head.map((h,i)=>`<th class="${num.includes(i)?'num':''}">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((c,i)=>`<td class="${num.includes(i)?'num':''}">${c}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${head.length}">None on file</td></tr>`}</tbody></table></div>`}
function etfView(){
 state.eview=ETF_VIEWS.some(v=>v[0]===state.eview)?state.eview:'screen';
 let out=`<div class="toolbar">${field('eview','View',ETF_VIEWS,state.eview)}`;
 if(state.eview==='screen')out+=field('eac','Asset class',ETF_AC,state.eac||'')+field('est','Management',ETF_STRAT,state.est||'')+field('esort','Sort',ETF_SORT,state.esort||'aum')+
  `<div class="field"><label for="eq">Name, ticker or issuer</label><input id="eq" value="${esc(state.eq||'')}" placeholder="e.g. dividend, covered call, iShares, QQQ"></div>`+field('eobj','Objective',[['','Hidden'],['1','Shown under each ETF']],state.eobj||'')+
  field('elev','Leverage',ETF_LEV,state.elev||'')+(etfStore.index&&etfStore.index.data&&etfStore.index.data.tag_names?etfTagField(etfStore.index.data,etfRows().rows||[]):'')+field('emin','Size',[['','Any size'],['1e8','Over $100M'],['1e9','Over $1B'],['1e10','Over $10B']],state.emin||'')+
  field('emax','Expense ratio',[['','Any'],['0.001','Up to 0.10%'],['0.002','Up to 0.20%'],['0.005','Up to 0.50%'],['0.01','Up to 1.00%']],state.emax||'');
 if(state.eview==='screen'&&etfStore.index&&etfStore.index.data&&etfStore.index.data.tag_names){const nm=etfStore.index.data.tag_names;out+=`</div><div class="etf-tags etf-quick"><span class="muted">Tags:</span>${ETF_TAG_QUICK.filter(t=>nm[t]).map(t=>etfChip(t,nm).replace('class="tag etf-tag','class="tag etf-tag'+(state.etag===t?' on':''))).join('')}${state.etag?`<button class="text-button" data-etag="">Clear “${esc(etfTagName(state.etag,nm))}” ×</button>`:''}`}
 if(state.eview==='one')out+=`<div class="field wide"><label for="esym">ETF (ticker)</label><input id="esym" value="${esc(state.esym||'')}" placeholder="e.g. SPY, QQQ, SCHD · Enter"></div>`;
 if(state.eview==='overlap')out+=`<div class="field"><label for="ea">First ETF</label><input id="ea" value="${esc(state.ea||'SPY')}"></div><div class="field"><label for="eb">Second ETF</label><input id="eb" value="${esc(state.eb||'QQQ')}"></div>`;
 if(state.eview==='holds')out+=`<div class="field wide"><label for="ehold">Company (ticker)</label><input id="ehold" value="${esc(state.ehold||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 if(state.eview==='parties')out+=field('eparty','Party',ETF_PARTY,state.eparty||'aps');
 out+='</div>';
 out+=`<div class="explain">Every US-listed ETF, read from its own filings: the <b>prospectus</b> (fees, benchmark, objective, strategy, principal risks — the SEC's risk/return data), <b>N-PORT</b> (the full portfolio, monthly flows and returns), <b>N-CEN</b> (index or active, tracking difference, securities lending, authorized participants and what each created and redeemed, adviser, custodian, auditor, distributor, board) — with the market (prices, net assets, premium) and the rest of the Hub: the <b>13F managers</b> who hold it, <b>officials' trades</b> in it, <b>short interest</b>, and the companies inside seen through the consensus, 13F flows, officials, insiders and debt. Not investment advice.</div>`;
 if(state.eview==='one')return out+etfOne();
 if(state.eview==='overlap')return out+etfOverlap();
 if(state.eview==='holds')return out+etfHolds();
 if(state.eview==='parties')return out+etfParties();
 return out+etfScreen();
}
function etfRows(){const g=etfGate('index','The ETF list');if(!g.data)return {html:g.html};const F=g.data.fields;return {rows:g.data.rows.map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o}),data:g.data}}
function etfScreen(){
 const R=etfRows();if(!R.rows)return R.html;
 let rows=R.rows;
 const q=String(state.eq||'').trim().toLowerCase();
 if(q)rows=rows.filter(r=>r.symbol.toLowerCase()===q||(r.name||'').toLowerCase().includes(q)||(r.issuer||'').toLowerCase().includes(q)||(r.category||'').toLowerCase().includes(q)||(r.objective||'').toLowerCase().includes(q));
 if(state.eac)rows=rows.filter(r=>r.asset_class===state.eac);
 const has=(r,t)=>(r.tags||[]).includes(t);
 const est={Index:'passive',Active:'active'}[state.est]||state.est;
 if(est==='options')rows=rows.filter(r=>r.tags?has(r,'opt-income')||has(r,'buffer'):/options/.test(r.strategy||''));
 else if(est)rows=rows.filter(r=>r.tags?has(r,est):(r.strategy||'').toLowerCase().startsWith(est==='passive'?'index':'active'));
 const lv=state.elev;
 if(lv==='no')rows=rows.filter(r=>!r.leveraged);else if(lv==='only')rows=rows.filter(r=>r.leveraged);
 else if(lv==='long')rows=rows.filter(r=>r.leveraged&&!r.inverse);else if(lv==='inv')rows=rows.filter(r=>r.inverse);
 else if(lv==='single')rows=rows.filter(r=>has(r,'single'));else if(lv)rows=rows.filter(r=>r.lev!=null&&Math.abs(r.lev-(+lv))<1e-9);
 if(state.etag)rows=rows.filter(r=>has(r,state.etag));
 if(state.emin)rows=rows.filter(r=>(r.aum||0)>=+state.emin);
 if(state.emax)rows=rows.filter(r=>r.expense!=null&&r.expense<=+state.emax);
 const s=state.esort||'aum',key=s.replace('_low',''),dir=s.endsWith('_low')||s==='expense'?1:-1;
 rows.sort((a,b)=>{const x=a[key],y=b[key];if(x==null&&y==null)return (b.aum||0)-(a.aum||0);if(x==null)return 1;if(y==null)return -1;return dir*(x-y)});
 exported=rows;
 const tot=rows.reduce((a,r)=>a+(r.aum||0),0),f3=rows.reduce((a,r)=>a+(r.flows_3m||0),0);
 let out=`<div class="section-head"><h3>${fmt(rows.length)} ETFs · ${etfMoney(tot)} in assets · ${etfMoney(f3)} net flows over the last 3 reported months</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=`<p class="sub">Click a ticker for everything about the ETF. Flows: sales + reinvestments − redemptions from the ETF's N-PORT reports. Tracking difference: the N-CEN figure, the fund's return less its index's over its fiscal year after fees (percentage points). "Holdings' upside": the analysts' price-target return of the companies inside, at their weights. Tags: passive or active from the fund's N-CEN (or its prospectus), the leverage multiple from the prospectus objective (else the name), income from the 12-month yield and the distributions of the last year, region from the countries in the portfolio — click one to filter.</p>`;
 out+=table(['ETF','Asset class','Expense','Assets','Flows, 3 months','1 year','Volatility','Holdings · top 10','Tracking diff.','13F holders','Officials, 1 year',"Holdings' upside"],rows.slice(0,1500).map(r=>[
  `${etfTk(r.symbol)} <span class="muted">${esc((r.name||'').slice(0,46))}</span>${r.issuer?`<br><span class="muted">${esc(r.issuer)}${r.strategy?' · '+esc(r.strategy):''}</span>`:''}${etfRowTags(r,R.data.tag_names)}${r.objective&&(q||state.eobj)?`<br><span class="muted etf-obj" title="${esc(r.objective)}">${esc(r.objective.slice(0,120))}${r.objective.length>120?'…':''}</span>`:''}`,
  `${esc(r.asset_class||'—')}${r.category?`<br><span class="muted">${esc(r.category)}</span>`:''}`,etfPct(r.expense),etfMoney(r.aum),
  r.flows_3m==null?'—':`<span class="${r.flows_3m>0?'positive':r.flows_3m<0?'negative':''}">${etfMoney(r.flows_3m)}</span>`,etfSpct(r.r1y),r.vol==null?'—':etfPct(r.vol,1),
  r.n_holdings==null?'—':`${fmt(r.n_holdings)} · ${etfPct(r.top10,0)}`,r.track_diff==null?'—':fmt(r.track_diff,2),
  r.holders13f==null?'—':`${fmt(r.holders13f)}${r.holders13f_chg?` <span class="muted">${r.holders13f_chg>0?'+':''}${fmt(r.holders13f_chg)}</span>`:''}`,r.officials_1y?fmt(r.officials_1y):'—',etfSpct(r.lt_target)]));
 return out;
}
// ---------- ten years of prices: as traded vs distributions reinvested, and the distributions (data/etf/px/<SYM>.json) ----------
function etfPxRows(px){                                          // [[date, close as traded, total-return close rebased]]
 const d0=Date.parse(px.d0+'T00:00:00Z'),k=px.c[0]/px.a[0];
 return px.t.map((t,i)=>[new Date(d0+t*864e5).toISOString().slice(0,10),px.c[i],px.a[i]*k]);
}
function etfPxPanel(sym,px){
 const R=etfPxRows(px);if(R.length<3)return '';
 const last=R[R.length-1],first=R[0],cut=new Date(Date.parse(last[0])-365*864e5).toISOString().slice(0,10);
 const ttm=(px.div||[]).filter(d=>d[0]>cut).reduce((a,d)=>a+d[1],0),allDiv=(px.div||[]).reduce((a,d)=>a+d[1],0);
 const yrs=(Date.parse(last[0])-Date.parse(first[0]))/(365.25*864e5),pr=last[1]/first[1]-1,tr=last[2]/first[2]-1;
 const W=820,H=240,L=56,Rm=12,T=10,B=24,xs=R.map(r=>Date.parse(r[0])),ys=R.flatMap(r=>[r[1],r[2]]);
 let y0=Math.min(...ys),y1=Math.max(...ys);const pad=(y1-y0)*.06||1;y0-=pad;y1+=pad;
 const X=t=>L+(t-xs[0])/((xs[xs.length-1]-xs[0])||1)*(W-L-Rm),Y=v=>T+(y1-v)/(y1-y0)*(H-T-B),fy=v=>'$'+fmt(v,v>=100?0:2);
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sym)}: price as traded and with distributions reinvested">`;
 for(let k=0;k<=3;k++){const v=y0+(y1-y0)*k/3;s+=`<line class="mk-grid" x1="${L}" x2="${W-Rm}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${L-6}" y="${Y(v)+4}" text-anchor="end">${fy(v)}</text>`}
 for(let y=new Date(xs[0]).getUTCFullYear()+1;y<=new Date(xs[xs.length-1]).getUTCFullYear();y++){const t=Date.UTC(y,0,1);s+=`<text class="axis" x="${X(t)}" y="${H-6}" text-anchor="middle">${y}</text>`}
 const path=j=>R.map((r,i)=>(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(r[j]).toFixed(1)).join('');
 s+=`<path d="${path(2)}" fill="none" stroke="var(--mk-profit)" stroke-width="2.2"/><path d="${path(1)}" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`;
 const step=Math.max(1,Math.floor(R.length/120));
 R.forEach((r,i)=>{if(i%step===0||i===R.length-1)s+=`<rect x="${X(xs[i])-3}" y="${T}" width="6" height="${H-T-B}" fill="transparent"><title>${esc(r[0])}: ${fy(r[1])} as traded · ${fy(r[2])} with distributions reinvested</title></rect>`});
 s+='</svg>';
 const recent=(px.div||[]).slice(-8).reverse();
 return `<h3>Price over ${fmt(yrs,1)} years — as traded and with distributions reinvested</h3>${s}<div class="mk-legend"><span><i class="mk-key" style="background:var(--ink)"></i>Price as traded ${etfSpct(pr)}</span><span><i class="mk-key" style="background:var(--mk-profit)"></i>Distributions reinvested ${etfSpct(tr)}</span><span class="muted">weekly closes since ${esc(first[0])}</span></div>`+
  etfCards([['Distributions, last 12 months','$'+fmt(ttm,2),last[1]?`${etfPct(ttm/last[1],2)} of the price`:''],['Distributions since '+first[0].slice(0,4),'$'+fmt(allDiv,2),`${fmt((px.div||[]).length)} payments`],
   ['From distributions',etfSpct(tr-pr),'total return − price return'],['Make a video',`<a href="../#studio/k=growth&t=${encodeURIComponent(sym)},SPY&div=split&from=${esc(first[0])}">Growth race ↗</a>`,'$10,000 in '+esc(sym)+' vs SPY, distributions split out']])+
  (recent.length?etfTbl(['Ex-date (week)','Distribution per share'],recent.map(d=>[esc(d[0]),'$'+fmt(d[1],4)]),[1]):'')+
  `<p class="sub">${esc(px.source||'')}. A distribution is dated to the week of its ex-date and estimated from the two closes, so it can differ from the declared amount by a few percent.</p>`;
}
// ---------- charts (single series; flows and returns diverge from zero in the site's profit / cost colours) ----------
function etfLine(pts,{h=200,label='',fmtY=v=>fmt(v,2)}={}){
 if(!pts||pts.length<3)return '';
 const W=820,H=h,L=56,R=12,T=10,B=24,xs=pts.map(p=>Date.parse(p[0])),ys=pts.map(p=>p[1]);
 let y0=Math.min(...ys),y1=Math.max(...ys);const pad=(y1-y0)*.06||1;y0-=pad;y1+=pad;
 const X=t=>L+(t-xs[0])/((xs[xs.length-1]-xs[0])||1)*(W-L-R),Y=v=>T+(y1-v)/(y1-y0)*(H-T-B);
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
 for(let k=0;k<=3;k++){const v=y0+(y1-y0)*k/3;s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${L-6}" y="${Y(v)+4}" text-anchor="end">${fmtY(v)}</text>`}
 const y0d=new Date(xs[0]).getUTCFullYear(),y1d=new Date(xs[xs.length-1]).getUTCFullYear();
 for(let y=y0d+1;y<=y1d;y++){const t=Date.UTC(y,0,1);s+=`<text class="axis" x="${X(t)}" y="${H-6}" text-anchor="middle">${y}</text>`}
 s+=`<path d="${pts.map((p,i)=>(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="var(--ink)" stroke-width="2"/>`;
 const step=Math.max(1,Math.floor(pts.length/120));
 pts.forEach((p,i)=>{if(i%step===0||i===pts.length-1)s+=`<rect x="${X(xs[i])-3}" y="${T}" width="6" height="${H-T-B}" fill="transparent"><title>${esc(p[0])}: ${fmtY(p[1])}</title></rect>`});
 return s+'</svg>';
}
function etfBars(items,{fmtV=etfMoney,label='',h=170}={}){         // [[label, value, title]] around zero
 if(!items||!items.length)return '';
 const W=820,H=h,L=56,R=12,T=10,B=26,vs=items.map(x=>x[1]||0),m=Math.max(1e-9,...vs.map(Math.abs)),lo=Math.min(0,...vs),hi=Math.max(0,...vs);
 const n=items.length,bw=Math.min(46,(W-L-R)/n*.7),X=i=>L+(i+.5)*(W-L-R)/n,Y=v=>T+(hi-v)/((hi-lo)||1)*(H-T-B);
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
 for(const v of [lo,0,hi]){s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${L-6}" y="${Y(v)+4}" text-anchor="end">${fmtV(v)}</text>`}
 items.forEach((x,i)=>{const v=x[1]||0,y=Math.min(Y(0),Y(v)),hh=Math.max(1,Math.abs(Y(v)-Y(0)));
  s+=`<rect x="${X(i)-bw/2}" y="${y}" width="${bw}" height="${hh}" rx="3" fill="${v>=0?'var(--mk-profit)':'var(--mk-cost)'}"><title>${esc(x[2]||x[0])}: ${fmtV(v)}</title></rect><text class="axis" x="${X(i)}" y="${H-8}" text-anchor="middle">${esc(x[0])}</text>`});
 return s+'</svg>';
}
function etfMix(obj,names,{n=10}={}){                               // horizontal shares, one hue
 const e=Object.entries(obj||{}).filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]).slice(0,n);
 if(!e.length)return '<p class="sub">Not on file.</p>';
 const m=Math.max(...e.map(x=>x[1]));
 return `<div class="etf-mix">${e.map(([k,v])=>`<div><span>${esc((names&&names[k])||k)}</span><i><b style="width:${(v/m*100).toFixed(1)}%"></b></i><em>${etfPct(v,1)}</em></div>`).join('')}</div>`;
}
function etfCards(cards){return `<div class="etf-cards">${cards.map(([l,v,n])=>`<div><small>${esc(l)}</small><strong>${v}</strong>${n?`<span class="muted">${n}</span>`:''}</div>`).join('')}</div>`}
function etfOne(){
 const sym=String(state.esym||'').trim().toUpperCase();
 if(!sym)return empty('Type a ticker (or click one in the screener).');
 const m=etfData('e/'+sym);
 if(m.err)return empty(`${sym} is not on file (${m.err}). The list covers every ETF Nasdaq's symbol directory flags as an ETF on a US exchange.`);
 if(!m.data)return empty('Loading '+sym+'…');
 const d=m.data,mk=d.market||{},p=d.prospectus||{},nc=d.ncen||{},h=d.holdings||{},fl=d.flows||{},lt=d.look_through,o13=d.holders13f;
 const fees=p.fees||{},exp=fees.net!=null?fees.net:fees.gross!=null?fees.gross:(nc.net_expenses!=null?nc.net_expenses/100:mk.y_expense);
 const f3=(fl.net||[]).slice(-3).reduce((a,x)=>a+x[1],0),f12=(fl.net||[]).reduce((a,x)=>a+x[1],0);
 let out=`<div class="panel"><div class="section-head"><div><h3>${esc(d.name||sym)} <span class="muted">${esc(sym)} · ${esc(d.exchange||'')}</span></h3>
  <p class="sub">${[d.issuer,d.asset_class,d.strategy,d.category,d.registrant?('Registrant: '+d.registrant):null,d.act==='33'?'1933-Act trust (files 10-Ks; no N-PORT)':d.act==='uit'?'Unit investment trust (no N-PORT: holdings from the sponsor)':d.act==='etn'?'Exchange-traded note — a bank\'s unsecured debt, not a fund':null].filter(Boolean).map(esc).join(' · ')}</p>
  ${(d.tags||[]).length?`<div class="etf-tags etf-page-tags">${(()=>{const nm=d.tag_names||{},by={};for(const t of d.tags){const g=(nm[t]||[])[1]||'Other';(by[g]=by[g]||[]).push(t)}return Object.entries(by).map(([g,ts])=>`<span class="etf-tg"><span class="muted">${esc(g)}</span> ${ts.filter(t=>!(t==='lev'||t==='inv')||!ts.some(x=>x.startsWith('lev:'))).map(t=>etfChip(t,nm,t==='single'&&d.under?' · '+esc(d.under):'')).join('')}</span>`).join('')})()}</div>`:''}</div>
  <div>${[['EDGAR filings',d.filings&&d.filings.edgar],['Prospectus',d.filings&&d.filings.prospectus],['N-PORT',d.filings&&d.filings.nport],['N-CEN',d.filings&&d.filings.ncen]].filter(x=>x[1]).map(([l,u])=>`<a class="action" href="${esc(u)}" target="_blank" rel="noopener">${l} ↗</a>`).join(' ')}</div></div>`;
 out+=etfCards([['Price',mk.price!=null?'$'+fmt(mk.price,2):'—',mk.premium!=null?`${etfSpct(mk.premium,2)} vs NAV $${fmt(mk.y_nav,2)}`:(mk.price_date||'')],
  ['Net assets',etfMoney(mk.y_assets||h.net_assets),h.date&&h.net_assets?`N-PORT ${esc(h.date)}: ${etfMoney(h.net_assets)}`:''],
  ['Net flows',fl.net&&fl.net.length?etfMoney(f3):'—',fl.net&&fl.net.length?`last 3 months · ${etfMoney(f12)} over ${fl.net.length}`:'N-PORT not on file'],
  ['Expense ratio',etfPct(exp),fees.waiver?`gross ${etfPct(fees.gross)}, waiver ${etfPct(fees.waiver)}`:(fees.management!=null?`management fee ${etfPct(fees.management)}`:'')],
  ['Holdings',h.n?fmt(h.n):'—',h.top10!=null?`top 10 = ${etfPct(h.top10,1)}`:''],
  ['Tracking difference',d.leveraged?'—':nc.track_diff!=null?fmt(nc.track_diff,2)+' pts':'—',d.leveraged?'a leveraged / inverse fund reports it against the unlevered index: not comparable':nc.track_err!=null?`tracking error ${fmt(nc.track_err,2)}`:(nc.index===false?'active fund':'')],
  ['13F holders',o13?fmt(o13.holders):'—',o13?`${etfMoney(o13.usd)} · ${o13.prev_holders!=null?(o13.holders-o13.prev_holders>=0?'+':'')+fmt(o13.holders-o13.prev_holders)+' managers':''}`:''],
  ['1-year return',etfSpct(mk.r1y),`YTD ${etfSpct(mk.ytd)} · vol ${mk.vol1y!=null?etfPct(mk.vol1y,1):'—'}`]]);
 if(d.series_classes>1)out+=`<p class="sub"><b>One share class of a larger fund.</b> ${esc(sym)} is the ETF class of a fund with ${fmt(d.series_classes)} share classes on file: N-PORT net assets, flows and holdings and the N-CEN figures cover the whole fund (all classes); price, premium and market net assets are the ETF's.</p>`;
 const pxm=etfData('px/'+sym);
 if(pxm.data)out+=etfPxPanel(sym,pxm.data);
 else if(!pxm.err)out+='<p class="sub">Loading ten years of prices and distributions…</p>';
 if(!pxm.data&&mk.weekly&&mk.weekly.length>4)out+=`<h3>Price, weekly (adjusted for distributions)</h3>${etfLine(mk.weekly,{label:sym+' weekly price',fmtY:v=>'$'+fmt(v,v>=100?0:2)})}
  <p class="sub">Returns: 1 month ${etfSpct(mk.r1m)} · 3 months ${etfSpct(mk.r3m)} · 3 years ${etfSpct(mk.r3y)} a year · 5 years ${etfSpct(mk.r5y)} a year · worst drawdown ${etfSpct(mk.max_dd)} · average daily value traded ${etfMoney(mk.dollar_vol)}${mk.y_yield!=null?` · yield ${etfPct(mk.y_yield)}`:''}${mk.y_duration!=null?` · duration ${fmt(mk.y_duration,1)} years`:''}.</p>`;
 if(fl.net&&fl.net.length)out+=`<h3>Money in and out (N-PORT)</h3><p class="sub">Each month's sales + reinvested distributions − redemptions, as the fund reports them. Creations and redemptions run through authorized participants (below).</p>${etfBars(fl.net.map(x=>[x[0].slice(2),x[1],x[0]]),{label:'Monthly net flows'})}`;
 out+=`</div>`;
 // the price paths, ranges and max pain its options imply (options.js; only the ETFs whose chains are collected)
 if(typeof optDetail==='function'&&typeof optPathsPanel==='function'){const om=optDetail(sym);if(om.data)out+=optPathsPanel(om.data,sym)}
 // prospectus
 if(d.prospectus){
  const yrs=Object.entries(p.annual||{}).sort();
  out+=`<div class="panel"><h3>From the prospectus <span class="muted">${esc(p.form||'')} filed ${esc(p.filed||'')}</span></h3>${p.benchmarks&&p.benchmarks.length?`<p><b>Benchmark:</b> ${p.benchmarks.map(esc).join(' · ')}</p>`:''}${p.objective?`<p><b>Objective.</b> ${esc(p.objective)}</p>`:''}`;
  out+=etfTbl(['Fee table','Share of assets a year'],[['Management fee',etfPct(fees.management)],['Distribution (12b-1)',etfPct(fees.b12)],['Other expenses',etfPct(fees.other)],['Acquired fund fees',etfPct(fees.acquired)],['Total, gross',etfPct(fees.gross)],['Fee waiver',fees.waiver!=null?etfPct(fees.waiver):'—'],['<b>Total, net</b>',`<b>${etfPct(fees.net!=null?fees.net:fees.gross)}</b>`],['Portfolio turnover (last fiscal year)',etfPct(fees.turnover,0)],['Cost of $10,000 over 1 / 10 years',fees.cost1!=null?`$${fmt(fees.cost1)} / $${fmt(fees.cost10)}`:'—']].filter(r=>r[1]!=='—'||/net|gross/.test(r[0])),[1]);
  if(yrs.length)out+=`<h3>Calendar-year returns (prospectus bar chart)</h3>${etfBars(yrs.map(([y,v])=>[y,v,y+' total return']),{fmtV:v=>(v>0?'+':'')+fmt(v*100,0)+'%',label:'Calendar-year returns'})}${fees.best_q!=null?`<p class="sub">Best quarter ${etfSpct(fees.best_q)} · worst quarter ${etfSpct(fees.worst_q)}.</p>`:''}`;
  if(p.strategy)out+=`<details><summary>Principal investment strategy</summary><p class="sub">${esc(p.strategy)}</p></details>`;
  if(p.risks&&p.risks.length)out+=`<details><summary>Principal risks (${p.risks.length})</summary>${p.risks.map(([n,t])=>`<p class="sub"><b>${esc(n)}.</b> ${esc(t)}</p>`).join('')}</details>`;
  else if(p.risk_narrative)out+=`<details><summary>Principal risks</summary><p class="sub">${esc(p.risk_narrative)}</p></details>`;
  out+=`</div>`;
 }
 // holdings
 if(d.holdings){
  out+=`<div class="panel"><h3>Portfolio <span class="muted">${h.source?esc(h.source):'N-PORT'} as of ${esc(h.date||'')} · ${fmt(h.n)} positions</span></h3><div class="etf-two"><div><b>By asset type</b>${etfMix(h.mix,ASSET_NAMES)}</div><div><b>By country</b>${etfMix(h.countries)}</div>${lt&&lt.sectors&&Object.keys(lt.sectors).length?`<div><b>By sector (companies on Filing Flows)</b>${etfMix(lt.sectors)}</div>`:''}</div>`;
  out+=etfTbl(['Holding','Ticker','Weight','Value','Type','Country'],(h.top||[]).slice(0,30).map(x=>[esc(x[0])+(x[1]&&x[1]!==x[0]?`<br><span class="muted">${esc(x[1])}</span>`:''),x[4]?`<button class="text-button" data-cco="${esc(x[4])}">${esc(x[4])}</button>`:esc(x[2]||''),etfPct(x[6],2),etfMoney(x[5]),esc(ASSET_NAMES[x[7]]||x[7]||''),esc(x[9]||'')]),[2,3]);
  if(h.derivatives)out+=`<p class="sub">Derivatives: ${etfPct(h.derivatives,1)} of net assets (gross, by reported value). ${h.on_loan?`Securities on loan: ${etfMoney(h.on_loan)}.`:''}</p>`;
  out+=`</div>`;
 }
 // look-through
 if(lt){
  out+=`<div class="panel"><h3>The companies inside, through the rest of the Hub</h3><p class="sub">Each figure is a weighted share of the portfolio (${etfPct(lt.covered,0)} of it is companies the Hub tracks).</p>`;
  out+=etfCards([["Analysts' upside",etfSpct(lt.target_ret),`mean rating ${lt.rating!=null?fmt(lt.rating,2):'—'} (1 = buy)`],['Our model (next quarter)',etfSpct(lt.ours_ret),'Rotation forecasts, weighted'],['EPS estimates, 30 days',`${etfPct(lt.eps_up,0)} up`,`${etfPct(lt.eps_down,0)} down`],['Reporting in 14 days',etfPct(lt.reporting_14d,0),'of the portfolio'],
   ['13F managers, last quarter',`${etfPct(lt.f13_buying,0)} net buying`,`${etfPct(lt.f13_selling,0)} net selling`],["Officials' trades, 90 days",`${etfPct(lt.officials_buying,0)} bought`,`${etfPct(lt.officials_selling,0)} sold · ${fmt(lt.officials_trades)} trades`],['Insider buying',etfPct(lt.insider_buying,0),'of the portfolio, recent Form 4 buys'],['Implied CDS',lt.cds_bps!=null?fmt(lt.cds_bps,0)+' bp':'—','5-year, weighted (Debt & rates)']]);
  if(lt.rows&&lt.rows.length)out+=etfTbl(['Company','Weight','Price',"Analysts' target",'Rating','Our model','Next report','13F net managers',"Officials' trades, 90d"],lt.rows.map(r=>[`<button class="text-button" data-cco="${esc(r[0])}"><b>${esc(r[0])}</b></button> <span class="muted">${esc((r[1]||'').slice(0,26))}</span>`,etfPct(r[2],2),r[3]!=null?'$'+fmt(r[3],2):'—',r[4]!=null?`$${fmt(r[4],2)} ${r[3]?etfSpct(r[4]/r[3]-1):''}`:'—',r[5]!=null?fmt(r[5],2):'—',r[6]!=null&&r[3]?etfSpct(r[6]/r[3]-1):'—',esc(r[7]||'—'),r[8]!=null?`<span class="${r[8]>0?'positive':r[8]<0?'negative':''}">${r[8]>0?'+':''}${fmt(r[8])}</span>`:'—',r[9]?fmt(r[9]):'—']),[1,2,3,4,5,7,8]);
  out+=`<p class="sub">Click a ticker for its consensus page (Consensus tab).</p></div>`;
 }
 // parties
 if(d.ncen||d.aps&&d.aps.length){
  const e=nc.etf||{},rg=nc.registrant||{};
  const list=(a,f=x=>esc(x[0])+(x[1]?' <span class="muted">(affiliated)</span>':''))=>a&&a.length?a.map(f).join('<br>'):'—';
  out+=`<div class="panel"><h3>The parties (N-CEN for the year to ${esc(nc.period||'')}, filed ${esc(nc.filed||'')})</h3>`;
  out+=etfTbl(['Role','Who'],[
   ['Adviser',list((nc.advisers||[]).filter(x=>!/sub/i.test(x[1]||'')),x=>esc(x[0])+(x[2]?` <span class="muted">CRD ${esc(x[2])}</span>`:''))],['Sub-advisers',list((nc.advisers||[]).filter(x=>/sub/i.test(x[1]||'')),x=>esc(x[0])+(x[3]?' <span class="muted">(affiliated)</span>':''))],
   ['Index',nc.index?`index fund${nc.index_affiliated?' · index provider affiliated with the fund':''}${nc.index_exclusive?' · index used exclusively by the fund':''}`:'actively managed'],
   ['Custodians',list((nc.custodians||[]).slice(0,6),x=>esc(x[0])+(x[1]?' <span class="muted">(sub-custodian)</span>':''))],['Administrator',list(nc.administrators)],['Transfer agent',list(nc.transfer_agents)],
   ['Securities lending',nc.lends?`${list(nc.lending_agents,x=>esc(x[0])+(x[1]?' <span class="muted">(affiliated)</span>':''))}<br><span class="muted">net income ${etfMoney(nc.lending_income)} · average on loan ${etfMoney(nc.avg_on_loan)}</span>`:(nc.lending_ok?'authorized, none lent':'not authorized')],
   ['Auditor',list((nc.accountant||[]).map(x=>[x]))],['Distributor',list(nc.distributor)],['Board',nc.board&&nc.board.length?`${nc.board.length} trustees, ${nc.board.filter(x=>!x[1]).length} independent: ${nc.board.map(x=>esc(x[0])).join(', ')}`:'—'],['Chief compliance officer',list((nc.cco||[]).map(x=>[x]))],
   ['Pricing services',list(nc.pricing)],['Brokers (commissions)',(nc.brokers||[]).slice(0,6).map(x=>`${esc(x[0])} <span class="muted">${etfMoney(x[1])}</span>`).join('<br>')||'—'],
   ['Creation unit',e.creation_unit?`${fmt(e.creation_unit)} shares · ${e.in_kind?'in-kind ETF':'cash '+fmt(e.cash_in,1)+'% in / '+fmt(e.cash_out,1)+'% out'} · fee $${fmt(e.fee_in)} in / $${fmt(e.fee_out)} out`:'—'],
   ['Flags',[rg.material_weakness?'material weakness noted by the auditor':null,rg.accountant_changed?'auditor changed':null,rg.legal_proceeding?'legal proceedings':null,nc.non_diversified?'non-diversified':null,nc.derivatives_rule?'uses derivatives (rule 18f-4)':null,nc.expense_cap?'expense cap':null].filter(Boolean).map(esc).join(' · ')||'—']]);
  if(d.aps&&d.aps.length){const act=d.aps.filter(a=>a[1]||a[2]);
   out+=`<h3>Authorized participants <span class="muted">${fmt(act.length)} active of ${fmt(d.aps_total)} on contract</span></h3><p class="sub">The dealers that create new shares (handing the fund the basket) and redeem them, and the value of what each did in the fiscal year.</p>`+
    etfTbl(['Dealer','Created','Redeemed'],act.slice(0,20).map(a=>[esc(a[0]),etfMoney(a[1]),etfMoney(a[2]==null?null:Math.abs(a[2]))]),[1,2])}
  out+=`</div>`;
 }
 // owners and traders
 out+=`<div class="panel"><h3>Who owns and trades it</h3>`;
 if(o13)out+=`<p class="sub">${fmt(o13.holders)} 13F managers held ${etfMoney(o13.usd)} at ${esc(o13.period)} (${o13.prev_holders!=null?`${fmt(o13.new)} new, ${fmt(o13.exits)} gone since the quarter before`:''}).</p>`+etfTbl(['Manager','Value','Shares','Change in shares'],(o13.top||[]).slice(0,15).map(x=>[esc(x[0]),etfMoney(x[1]),fmt(x[2]),x[3]==null?'<span class="muted">new</span>':`<span class="${x[3]>0?'positive':x[3]<0?'negative':''}">${x[3]>0?'+':''}${fmt(x[3])}</span>`]),[1,2,3]);
 else out+=`<p class="sub">No 13F manager holding on file for this ticker.</p>`;
 if(d.officials&&d.officials.length)out+=`<h3>Officials' trades</h3>`+etfTbl(['Date','Official','Trade','Amount','Owner'],d.officials.slice(0,15).map(x=>[esc(x.date||''),esc(x.person||'')+` <span class="muted">${esc(x.jurisdiction||'')}</span>`,esc(x.type||''),x.amount_min!=null?`$${compact(x.amount_min)}–$${compact(x.amount_max)}`:'—',esc(x.owner||'')]),[3]);
 if(d.short)out+=`<p class="sub"><b>Short interest</b> (FINRA, ${esc(d.short.settlement||'')}): ${fmt(d.short.short)} shares, ${d.short.change_pct!=null?(d.short.change_pct>0?'+':'')+fmt(d.short.change_pct,1)+'% since the previous report':''}, ${fmt(d.short.dtc,1)} days to cover.</p>`;
 if(d.npx)out+=`<p class="sub"><b>Proxy votes</b>: the trust files N-PX (${fmt(d.npx.filing_count)} on file, latest ${esc(d.npx.latest_filing||'')}) — every vote is in the N-PX tab.</p>`;
 out+=`</div>`;
 return out;
}
function etfOverlap(){
 const a=String(state.ea||'SPY').trim().toUpperCase(),b=String(state.eb||'QQQ').trim().toUpperCase();
 const A=etfData('e/'+a),B=etfData('e/'+b);
 if(A.err||B.err)return empty(`${A.err?a:b} is not on file.`);
 if(!A.data||!B.data)return empty('Loading…');
 const wa=new Map((A.data.weights||[]).map(x=>[x[0],x[1]])),wb=new Map((B.data.weights||[]).map(x=>[x[0],x[1]]));
 if(!wa.size||!wb.size)return empty('Both need a portfolio on file (N-PORT or the sponsor\'s file) to compare.');
 const common=[...wa.keys()].filter(k=>wb.has(k)).map(k=>[k,wa.get(k),wb.get(k),Math.min(wa.get(k),wb.get(k))]).sort((x,y)=>y[3]-x[3]);
 const ov=common.reduce((s,x)=>s+x[3],0);
 const st=(d,k)=>d.market&&d.market[k];
 let out=`<div class="panel"><h3>${esc(a)} and ${esc(b)} overlap by ${etfPct(ov,1)}</h3><p class="sub">The sum over the companies both hold of the smaller of the two weights (equity positions, up to 600 largest each): the share of either portfolio that is the same exposure. ${fmt(common.length)} companies in common.</p>`;
 out+=etfTbl(['',a,b],[['Name',esc(A.data.name||''),esc(B.data.name||'')],['Expense ratio',etfPct((A.data.prospectus||{}).fees&&((A.data.prospectus.fees.net!=null?A.data.prospectus.fees.net:A.data.prospectus.fees.gross))||st(A.data,'y_expense')),etfPct((B.data.prospectus||{}).fees&&((B.data.prospectus.fees.net!=null?B.data.prospectus.fees.net:B.data.prospectus.fees.gross))||st(B.data,'y_expense'))],
  ['Net assets',etfMoney(st(A.data,'y_assets')),etfMoney(st(B.data,'y_assets'))],['Holdings',fmt((A.data.holdings||{}).n),fmt((B.data.holdings||{}).n)],['1-year return',etfSpct(st(A.data,'r1y')),etfSpct(st(B.data,'r1y'))],['Volatility',etfPct(st(A.data,'vol1y'),1),etfPct(st(B.data,'vol1y'),1)]],[1,2]);
 out+=`<h3>The largest common positions</h3>`+etfTbl(['Company',`Weight in ${a}`,`Weight in ${b}`,'Overlap'],common.slice(0,30).map(x=>[`<button class="text-button" data-cco="${esc(x[0])}">${esc(x[0])}</button>`,etfPct(x[1],2),etfPct(x[2],2),etfPct(x[3],2)]),[1,2,3]);
 return out+'</div>';
}
function etfHolds(){
 const t=String(state.ehold||'').trim().toUpperCase();
 if(!t)return empty('Type a company ticker: every ETF that holds it, by dollars held and by weight.');
 const m=etfData('by/'+t);
 if(m.err)return empty(`No ETF portfolio on file holds ${t} (or the ticker is not on file).`);
 if(!m.data)return empty('Loading '+t+'…');
 const d=m.data;exported=d.rows.map(r=>({etf:r[0],name:r[1],weight:r[2],usd:r[3],etf_assets:r[4]}));
 return `<div class="section-head"><h3>${fmt(d.etfs)} ETFs hold ${esc(t)}${d.name?' <span class="muted">'+esc(d.name)+'</span>':''} — ${etfMoney(d.usd)} in all</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">From each ETF's latest N-PORT portfolio (dollars as reported; weights as a share of the ETF's net assets). Click an ETF for its page, or the ticker for the company's consensus.</p>`+
  table(['ETF','Weight','Value held','ETF assets'],d.rows.map(r=>[`${etfTk(r[0])} <span class="muted">${esc((r[1]||'').slice(0,50))}</span>`,etfPct(r[2],2),etfMoney(r[3]),etfMoney(r[4])]));
}
function etfParties(){
 const g=etfGate('parties','The parties');if(!g.data)return g.html;
 const k=state.eparty||'aps',T=(g.data.tables||{})[k]||[];exported=T.map(r=>({name:r[0],etfs:r[1],aum:r[2],x:r[3],y:r[4]}));
 const head=k==='aps'?['Dealer','ETFs served','Assets of those ETFs','Created','Redeemed']:k==='lending'?['Agent','ETFs','Assets of those ETFs','Lending income of those ETFs']:['Name','ETFs','Assets of those ETFs'];
 return `<div class="section-head"><h3>${esc((ETF_PARTY.find(x=>x[0]===k)||[])[1])} across all ETFs</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">From each ETF's latest N-CEN. ${k==='aps'?'An authorized participant creates ETF shares by delivering the basket to the fund and redeems them by taking it back; the values are what each did in the funds\' fiscal years.':'Assets are the current net assets of the ETFs each serves.'}</p>`+
  table(head,T.map(r=>[esc(r[0]),fmt(r[1]),etfMoney(r[2]),...(k==='aps'?[etfMoney(r[3]),etfMoney(r[4])]:k==='lending'?[etfMoney(r[3])]:[])]));
}
function bindEtf(){
 if(state.tab!=='etf')return;
 for(const k of ['eview','eac','est','esort','elev','emin','emax','eparty','eobj','etag'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 document.querySelectorAll('#workspace [data-etag]').forEach(b=>b.onclick=()=>{
  const t=b.dataset.etag;state.eview='screen';state.page=0;
  if(t==='passive'||t==='active')state.est=t;else if(t==='opt-income'||t==='buffer'){state.etag=t}
  else if(t.startsWith('lev:'))state.elev=String(+t.slice(4));else if(t==='lev')state.elev='long';else if(t==='inv')state.elev='inv';else if(t==='single')state.elev='single';
  else state.etag=state.etag===t?'':t;
  render();scrollTo({top:0,behavior:'smooth'})});
 for(const k of ['eq','esym','ea','eb','ehold'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-etf]').forEach(b=>b.onclick=()=>{state.eview='one';state.esym=b.dataset.etf;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-cco]').forEach(b=>b.onclick=()=>{state.tab='consensus';state.cview='company';state.cq=b.dataset.cco;syncPills();try{history.replaceState(null,'','#consensus')}catch(e){}render();scrollTo({top:0,behavior:'smooth'})});
}
