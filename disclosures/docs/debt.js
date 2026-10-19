/* 4.11 Debt & rates — what every company borrows, what it pays and how much room it has; market rates; banks' deposits
   and CDs. Data: data/debt/{index,rates,banks,calibration}.json and data/debt/c/<cik>.json (app/debt.py, branch
   debt-history). The company page itself is drawn by debt-view.js (shared with the main site's company page). */
const debtStore={};
function debtData(name){
 const m=debtStore[name]||(debtStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/debt/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function debtGate(name,title){
 const m=debtData(name);
 if(m.err)return {html:empty(`${title} could not load (${m.err}). The debt collector runs every two hours and reads a few hundred companies a run, largest first.`)};
 if(!m.data)return {html:empty(`Loading ${title.toLowerCase()}…`)};
 return {data:m.data};
}
const DEBT_VIEWS=[['screen','Screener — every company'],['company','One company'],['rates','Market rates'],['banks','Banks: deposits and CDs']];
const DEBT_BANDS=['AAA','AA','A','BBB','BB','B','CCC'];
function debtView(){
 state.dview=DEBT_VIEWS.some(v=>v[0]===state.dview)?state.dview:'screen';
 let out=`<div class="toolbar">${field('dview','View',DEBT_VIEWS,state.dview)}`;
 if(state.dview==='company')out+=`<div class="field wide"><label for="dq">Company (ticker)</label><input id="dq" value="${esc(state.dq||'')}" placeholder="e.g. ORCL · Enter"></div>`;
 if(state.dview==='screen')out+=field('dband','Implied rating',[['','All'],...DEBT_BANDS.map(b=>[b,b+' or similar'])],state.dband||'')+field('dflt','Show',[['','All companies with debt'],['conv','With convertibles'],['itm','Convertibles in the money'],['cov','With covenants read'],['thin','Thin cushion (score < 40)'],['iss','Priced bonds on file']],state.dflt||'');
 out+='</div>';
 out+=`<div class="explain">From each company's own filings: XBRL balances and every tagged instrument, pricing term sheets of the bonds it sold (coupon and spread over Treasuries), credit agreements (SOFR margin, fees, covenants) and 8-K financing events; FDIC call reports for banks' deposits and CDs. The implied 5-year CDS is estimated from the stock (Merton model) and calibrated on real bond pricing — there are no free CDS quotes. Not investment advice.</div>`;
 if(state.dview==='rates')return out+debtRates();
 if(state.dview==='banks')return out+debtBanks();
 if(state.dview==='company')return out+debtCompany();
 return out+debtScreen();
}
function debtRow(F,r){const o={};F.forEach((k,i)=>o[k]=r[i]);return o}
function debtScreen(){
 const g=debtGate('index','The debt data');if(!g.data)return g.html;
 const D=g.data,F=D.fields;let rows=D.rows.map(r=>debtRow(F,r)).filter(r=>r.total_debt>0||r.deposit_cost!=null);
 if(state.dband)rows=rows.filter(r=>r.rating_band===state.dband);
 const f=state.dflt;
 if(f==='conv')rows=rows.filter(r=>r.convertible_face>0);else if(f==='itm')rows=rows.filter(r=>r.convertible_itm_face>0);
 else if(f==='cov')rows=rows.filter(r=>r.min_covenant_cushion!=null);else if(f==='thin')rows=rows.filter(r=>r.cushion_score!=null&&r.cushion_score<40);
 else if(f==='iss')rows=rows.filter(r=>r.issues>0);
 rows.sort((a,b)=>(b.total_debt||0)-(a.total_debt||0));
 exported=rows;
 const cal=D.calibration,mk=D.market||{};
 const B=DebtView;
 const tone=(v,lo,hi,goodHigh)=>v==null?'':goodHigh?(v>=hi?'positive':v<=lo?'negative':''):(v<=lo?'positive':v>=hi?'negative':'');
 let out=`<div class="panel"><h3>${fmt(rows.length)} companies</h3><p class="sub">Treasury 1-year ${B.pct(mk.treasury_1y,2)}, 5-year ${B.pct(mk.treasury_5y,2)}, SOFR ${B.pct(mk.sofr,2)}.${cal?` Implied CDS calibration: ${fmt(cal.n)} bonds priced in term sheets, R² ${fmt(cal.r2,2)} (log spread on distance to default and maturity).`:' The implied CDS is the raw Merton spread until enough priced bonds are on file to calibrate it.'} Click a ticker for the company.</p></div>`;
 out+=`<div class="section-head"><h3>Debt screener</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Company','Sector','Debt','Net debt ÷ EBITDA','EBIT ÷ interest','Liquidity ÷ 12m maturities','Rate paid','Floating','Implied CDS','Band','Cushion','Covenant cushion','Convertibles','Last bond spread'],
  rows.map(r=>[`<button class="text-button" data-dco="${esc(r.ticker||r.cik)}"><b>${esc(r.ticker||'')}</b></button> <span class="muted">${esc(shortName(r.name||''))}</span>`,esc(r.sector||''),B.big(r.total_debt),
   `<span class="${tone(r.net_leverage,2,4,false)}">${B.x(r.net_leverage)}</span>`,`<span class="${tone(r.interest_coverage,2,6,true)}">${B.x(r.interest_coverage)}</span>`,`<span class="${tone(r.liquidity_to_due12,1,2.5,true)}">${B.x(r.liquidity_to_due12)}</span>`,
   B.pct(r.effective_rate,2),B.pct(r.floating_share,0),`<span class="${tone(r.implied_cds_5y_bps,120,400,false)}">${B.bp(r.implied_cds_5y_bps)}</span>`,esc(r.rating_band||'—'),r.cushion_score==null?'—':`<span class="${tone(r.cushion_score,40,70,true)}">${r.cushion_score}</span>`,
   r.min_covenant_cushion==null?'—':B.pct(r.min_covenant_cushion,0),r.convertible_face?B.big(r.convertible_face)+(r.convertible_itm_face?' <span class="positive">ITM</span>':''):'—',r.last_issue_spread_bps==null?'—':B.bp(r.last_issue_spread_bps)+` <span class="muted">${esc((r.last_issue_date||'').slice(0,7))}</span>`]));
 return out;
}
function debtCompany(){
 const g=debtGate('index','The debt data');if(!g.data)return g.html;
 const D=g.data,F=D.fields,q=String(state.dq||'').trim().toUpperCase();
 if(!q)return empty('Type a ticker (or pick one in the screener).');
 const r=D.rows.map(x=>debtRow(F,x)).find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
 if(!r)return empty(`${q} is not in the debt data yet — the collector reads a few hundred companies a run, largest first.`);
 const c=debtData('c/'+r.cik);
 if(c.err)return empty('Could not load '+q+' ('+c.err+')');
 if(!c.data)return empty('Loading '+q+'…');
 return `<div class="panel"><h3>${esc(c.data.name||q)} <span class="muted">${esc(r.ticker||'')} · ${esc(c.data.sic_description||'')}</span> <a class="tk" href="../#c-${r.cik}-debt">open on the company page →</a></h3><div id="debt-view"></div></div>`;
}
function bindDebt(){
 if(state.tab!=='debt')return;
 for(const k of ['dview','dband','dflt'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 if($('dq')){$('dq').onchange=e=>{state.dq=e.target.value;render()};$('dq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-dco]').forEach(b=>b.onclick=()=>{state.dview='company';state.dq=b.dataset.dco;render();scrollTo({top:0,behavior:'smooth'})});
 const el=$('debt-view');
 if(el){const g=debtData('index');const q=String(state.dq||'').trim().toUpperCase();const r=g.data&&g.data.rows.map(x=>debtRow(g.data.fields,x)).find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
  const c=r&&debtData('c/'+r.cik);if(c&&c.data&&window.DebtView)DebtView.render(el,c.data)}
 document.querySelectorAll('#workspace [data-dbank]').forEach(b=>b.onclick=()=>{state.dbank=b.dataset.dbank;render()});
}
function debtRates(){
 const g=debtGate('rates','Market rates');if(!g.data)return g.html;
 const R=g.data,S=R.series||{},L=R.labels||{};
 const line=(ids,title,unit='%')=>{const ser=ids.filter(i=>S[i]&&S[i].monthly.length).map((i,k)=>({i,pts:S[i].monthly,col:['var(--rot-1)','var(--rot-sun)','var(--flow-sell)','var(--flow-buy)','var(--muted)','#8a4fd6','#3a63c4'][k%7]}));
  if(!ser.length)return '';
  const all=ser.flatMap(s=>s.pts.map(p=>p[1])),lo=Math.min(0,...all),hi=Math.max(...all)*1.08,n=Math.max(...ser.map(s=>s.pts.length));
  const months=[...new Set(ser.flatMap(s=>s.pts.map(p=>p[0])))].sort(),ix=new Map(months.map((m,i)=>[m,i]));
  const W=620,H=220,Lm=40,Rm=10,T=12,B=24,X=i=>Lm+i/Math.max(1,months.length-1)*(W-Lm-Rm),Y=v=>T+(hi-v)/((hi-lo)||1)*(H-T-B);
  let s=`<div class="panel"><h3>${esc(title)}</h3><div class="mk-legend">${ser.map(z=>`<span><i class="mk-key" style="background:${z.col}"></i>${esc(L[z.i]||z.i)} ${z.pts.length?'· '+fmt(S[z.i].last?S[z.i].last[1]:null,2)+unit:''}</span>`).join('')}</div><svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">`;
  niceTicks(lo,hi,4).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-Rm}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${Lm-5}" y="${Y(v)+4}" text-anchor="end">${fmt(v,1)}</text>`});
  for(const z of ser)s+=`<path class="rot-line" style="stroke:${z.col};stroke-width:1.6" d="${z.pts.map((p,k)=>(k?'L':'M')+X(ix.get(p[0])).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}"/>`;
  const yrs=months.filter(m=>m.endsWith('-01'));const step=Math.max(1,Math.ceil(yrs.length/9));yrs.forEach((m,k)=>{if(k%step===0)s+=`<text class="axis" x="${X(ix.get(m))}" y="${H-6}" text-anchor="middle">${m.slice(0,4)}</text>`});
  return s+'</svg></div>'};
 const curve=()=>{const T=R.curve_tenors||[],N=R.curve_now||[],P=R.curve_year_ago||[];const all=[...N,...P].filter(v=>v!=null);if(!all.length)return '';
  const W=620,H=220,Lm=40,Rm=10,Tm=12,B=26,lx=v=>Math.log(v*12),x0=lx(T[0]),x1=lx(T[T.length-1]),X=v=>Lm+(lx(v)-x0)/(x1-x0)*(W-Lm-Rm),lo=Math.min(0,...all),hi=Math.max(...all)*1.1,Y=v=>Tm+(hi-v)/(hi-lo)*(H-Tm-B);
  let s=`<div class="panel"><h3>Treasury yield curve</h3><div class="mk-legend"><span><i class="mk-key" style="background:var(--rot-1)"></i>now</span><span><i class="mk-key" style="background:var(--muted)"></i>a year ago</span></div><svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Yield curve">`;
  niceTicks(lo,hi,4).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-Rm}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${Lm-5}" y="${Y(v)+4}" text-anchor="end">${fmt(v,1)}%</text>`});
  const lab=['1m','3m','6m','1y','2y','3y','5y','7y','10y','20y','30y'];T.forEach((v,i)=>{s+=`<text class="axis" x="${X(v)}" y="${H-8}" text-anchor="middle">${lab[i]}</text>`});
  for(const [arr,col,dash] of [[P,'var(--muted)','4 3'],[N,'var(--rot-1)','']]){const pts=T.map((v,i)=>[v,arr[i]]).filter(p=>p[1]!=null);s+=`<path class="rot-line" style="stroke:${col};stroke-width:2${dash?';stroke-dasharray:'+dash:''}" d="${pts.map((p,k)=>(k?'L':'M')+X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}"/>`;pts.forEach(p=>{s+=`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3" style="fill:${col}"><title>${fmt(p[1],2)}%</title></circle>`})}
  return s+'</svg></div>'};
 const nat=R.fdic_national||{},months=Object.keys(nat).sort(),last=months.length?nat[months[months.length-1]]:null;
 let cds='';
 if(last){cds=`<div class="panel"><h3>Deposit rates paid by banks — FDIC national rates (${esc(months[months.length-1])})</h3><p class="sub">Average rates all insured banks and credit unions pay, weighted by deposits; the rate cap is the most a less-than-well-capitalised bank may pay.</p>`+table(['Product','National rate','Rate cap'],Object.entries(last).map(([p,v])=>[esc(p),fmt(v.national,2)+'%',v.cap==null?'—':fmt(v.cap,2)+'%']));
  if(months.length>2){const ser=['12 month CD','60 month CD','Money Market','Savings'];const W=620,H=200,Lm=40,Rm=10,T=12,B=24,vals=months.flatMap(m=>ser.map(p=>nat[m][p]&&nat[m][p].national)).filter(v=>v!=null),hi=Math.max(...vals,1)*1.1,X=i=>Lm+i/Math.max(1,months.length-1)*(W-Lm-Rm),Y=v=>T+(hi-v)/hi*(H-T-B);
   cds+=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="National deposit rates">`;niceTicks(0,hi,4).forEach(v=>{cds+=`<line class="mk-grid" x1="${Lm}" x2="${W-Rm}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${Lm-5}" y="${Y(v)+4}" text-anchor="end">${fmt(v,1)}%</text>`});
   ser.forEach((p,k)=>{const col=['var(--rot-1)','#3a63c4','var(--flow-buy)','var(--muted)'][k];const pts=months.map((m,i)=>[i,nat[m][p]&&nat[m][p].national]).filter(q=>q[1]!=null);cds+=`<path class="rot-line" style="stroke:${col};stroke-width:1.6" d="${pts.map((q,j)=>(j?'L':'M')+X(q[0]).toFixed(1)+','+Y(q[1]).toFixed(1)).join('')}"/><text class="axis" x="${W-Rm}" y="${pts.length?Y(pts[pts.length-1][1])-4:0}" text-anchor="end" style="fill:${col}">${esc(p)}</text>`});
   cds+=`<text class="axis" x="${Lm}" y="${H-6}">${esc(months[0])}</text><text class="axis" x="${W-Rm}" y="${H-6}" text-anchor="end">${esc(months[months.length-1])}</text></svg>`}
  cds+='</div>'}
 return `<div class="rot-multiples">${curve()}${line(['SOFR','DFF','DPRIME','DGS3MO'],'Short rates: SOFR, fed funds, prime, 3-month bill')}${line(['DCPN30','RIFSPPFAAD30NB','RIFSPPNA2P2D30NB','DGS1MO'],'Commercial paper (30 days) vs the 1-month bill')}${line(['DAAA','DBAA','DGS10'],"Corporate yields: Moody's Aaa and Baa vs the 10-year Treasury")}${line(['BAMLC0A1CAAA','BAMLC0A3CA','BAMLC0A4CBBB','BAMLH0A1HYBB','BAMLH0A2HYB','BAMLH0A3HYC'],'Credit spreads by rating (ICE BofA, last three years)')}${line(['MORTGAGE30US','TERMCBAUTO48NS','DGS10'],'Household borrowing: 30-year mortgage and 48-month car loan')}</div>${cds}`;
}
function debtBanks(){
 const g=debtGate('banks','Bank deposits');if(!g.data)return g.html;
 const F=g.data.fields,rows=g.data.rows.map(r=>debtRow(F,r)).sort((a,b)=>(b.deposits||0)-(a.deposits||0));
 exported=rows;const B=DebtView;
 return `<div class="section-head"><h3>Banks on Filing Flows: deposits, CDs and what they pay — ${fmt(rows.length)} banks</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">The largest bank of each listed holding company (FDIC call reports). CDs = time deposits; deposit cost = interest on domestic deposits (quarter, annualised) ÷ domestic deposits. Click for the company page.</p>`+
  table(['Company','Bank','Quarter','Deposits','CDs share','Large CDs (> $250k)','Uninsured','Brokered','Deposit cost','Cost of funds','Net interest margin'],rows.map(r=>[`<button class="text-button" data-dco="${esc(r.ticker||r.cik)}"><b>${esc(r.ticker||'')}</b></button> <span class="muted">${esc(shortName(r.name||''))}</span>`,esc(r.bank||''),esc(r.date||''),B.big(r.deposits),B.pct(r.cd_share,1),B.big(r.time_over_250k),B.pct(r.uninsured_share,0),B.big(r.brokered),B.pct(r.deposit_cost,2),B.pct(r.cost_of_funds,2),B.pct(r.nim,2)]));
}
