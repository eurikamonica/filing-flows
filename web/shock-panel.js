/* Company shock laboratory. Descriptive multivariate associations, never identified causal shocks. */
(function(root){
'use strict';
const DAY=86400000, WEEK=7*DAY, fin=x=>typeof x==='number'&&Number.isFinite(x);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const iso=t=>new Date(t).toISOString().slice(0,10), time=s=>Date.parse(s+'T00:00:00Z');
const FACTORS=[['rates','10Y Treasury','bp',100,'DGS10'],['fx','Broad USD appreciation','%',1,'DTWEXBGS'],['jobs','Unemployment rate','pp',1,'UNRATE'],['peers','Peer revenue YoY growth','pp',1,null]];
const TARGETS={revenue:'Revenue YoY growth',om:'Operating margin',nm:'Net margin',ocfm:'Operating cash margin',fcfm:'Free cash flow margin',stock:'Stock total return',stockPrice:'Stock price return (ex-dividends)'};
const mean=a=>a.reduce((s,x)=>s+x,0)/a.length;
const median=a=>{a=a.slice().sort((x,y)=>x-y);return a.length?(a[(a.length-1)>>1]+a[a.length>>1])/2:null;};
function near(rows,t,days=12){let best=null;for(const r of rows)if(r.t<=t&&t-r.t<=days*DAY&&(!best||r.t>best.t))best=r;return best;}
function financials(c){
 const out=new Map(), H=c.quality?.hist, src=c.quality?.src;
 function put(end,k,v,meta={}){if(!fin(v)||!fin(time(end)))return;let p=out.get(end)||{end,t:time(end),values:{},sources:{}};p.values[k]=v;p.sources[k]=meta;out.set(end,p);}
 if(H?.periods&&H.v) for(const [k,rs] of Object.entries(H.v)){
  const annual=[];
  for(const [pi,vs] of rs){const p=H.periods[pi],v=vs?.[vs.length-1];if(!p||!v)continue;
   const meta={start:p[0],ref:v[1],filings:(v[1]?.[2]||[]).map(i=>src?.filings?.[i]).filter(Boolean)};
   if(p[2]==='q')put(p[1],k,v[0],meta);else if(p[2]==='fy')annual.push([p,v[0],meta]);
  }
  for(const [p,v,m] of annual){if(fin(out.get(p[1])?.values[k]))continue;
   const q=[...out.values()].filter(x=>x.t>=time(p[0])&&x.t<time(p[1])-45*DAY&&fin(x.values[k])).sort((a,b)=>a.t-b.t);
   if(q.length===3&&q.every((x,i)=>i===0||x.t-q[i-1].t>=70*DAY&&x.t-q[i-1].t<=110*DAY)&&time(p[1])-q[2].t>=70*DAY&&time(p[1])-q[2].t<=110*DAY)put(p[1],k,v-q.reduce((s,x)=>s+x.values[k],0),{...m,derived:'FY less Q1–Q3; latest reported versions'});
  }
 }
 for(const q of c.quarters||[])for(const [k,v] of Object.entries(q.headline||{}))if(['revenue','oi','ni','ocf','capex'].includes(k))put(q.end,k,v,{url:q.doc_url,filed:q.filed});
 for(const q of c.quality?.q||[])for(const [k,v] of Object.entries(q.health?.inputs||{}))put(q.end,k,v,{ref:q.health?.ev?.[k]});
 return [...out.values()].sort((a,b)=>a.t-b.t);
}
function metrics(rows){return rows.map(p=>{
 const v=p.values, prior=rows.find(x=>Math.abs(p.t-x.t-364*DAY)<=20*DAY),r=v.revenue;
 return {...p,revenue:r>0&&prior?.values.revenue>0?100*(r/prior.values.revenue-1):null,
  om:r>0&&fin(v.oi)?100*v.oi/r:null,nm:r>0&&fin(v.ni)?100*v.ni/r:null,
  ocfm:r>0&&fin(v.ocf)?100*v.ocf/r:null,fcfm:r>0&&fin(v.ocf)&&fin(v.capex)&&v.capex>=0?100*(v.ocf-v.capex)/r:null,yearAgoRevenue:prior?.values.revenue};
 });}
function weekly(doc,key){const d=doc?.weekly?.data?.[key],start=time(doc?.weekly?.start||'');return Array.isArray(d)&&fin(start)?d.map((v,i)=>({t:start+i*WEEK,v})).filter(x=>fin(x.v)):[];}
function prices(d,key='c'){const start=time(d?.start||'');return fin(start)&&Array.isArray(d?.[key])?d[key].map((v,i)=>({t:start+i*WEEK,v})).filter(x=>fin(x.v)&&x.v>0):[];}
function change(rows,t,pct=false,span=13*WEEK){const a=near(rows,t),b=near(rows,t-span);return a&&b&&(!pct||b.v>0)?pct?100*(a.v/b.v-1):a.v-b.v:null;}
function factorRows(macro,peers){
 const rates=weekly(macro,'y10'),fx=weekly(macro,'usd'),jobs=weekly(macro,'unrate');
 const times=[...new Set([...rates,...fx,...jobs].map(x=>x.t))].sort((a,b)=>a-b);
 return times.map(t=>{const ps=peers.map(p=>near(p,t,120)).filter(p=>fin(p?.revenue));return {t,rates:change(rates,t),fx:change(fx,t,true),jobs:change(jobs,t),peers:median(ps.map(p=>p.revenue)),peerCount:ps.length};});
}
function dataset(c,macro,peerCompanies,stock,market,lag=0){
 const f=factorRows(macro,peerCompanies.map(p=>metrics(financials(p)))),qs=metrics(financials(c));
 const attach=(t,y)=>{const z=near(f,t-lag*13*WEEK);return z?{...z,t,y,market:change(prices(market),t,true)}:null;};
 const rows={};for(const k of Object.keys(TARGETS).filter(k=>!k.startsWith('stock')))rows[k]=qs.filter(q=>fin(q[k])).map(q=>attach(q.t,q[k])).filter(Boolean);
 // Non-overlapping calendar quarters: no weekly overlapping 13-week returns masquerading as independent observations.
 const sp=prices(stock),today=Date.now(),ends=[];if(sp.length)for(let y=new Date(sp[0].t).getUTCFullYear();y<=new Date(today).getUTCFullYear();y++)for(const m of [3,6,9,12]){const t=Date.UTC(y,m,0);if(t<=today&&t>=sp[0].t)ends.push(t);}
 for(const [target,field] of [['stock','c'],['stockPrice','p']]){const values=prices(stock,field);rows[target]=ends.map((t,i)=>{if(!i)return null;const a=near(values,t),b=near(values,ends[i-1]);if(!a||!b)return null;const r=attach(t,100*(a.v/b.v-1));if(r){const mp=prices(market),ma=near(mp,t),mb=near(mp,ends[i-1]);r.market=ma&&mb?100*(ma.v/mb.v-1):null;}return r;}).filter(Boolean);}
 return {rows,quarters:qs,factors:f};
}
function inverse(A){const n=A.length,a=A.map((r,i)=>[...r,...Array.from({length:n},(_,j)=>+(i===j))]);
 for(let k=0;k<n;k++){let p=k;for(let i=k+1;i<n;i++)if(Math.abs(a[i][k])>Math.abs(a[p][k]))p=i;if(Math.abs(a[p][k])<1e-9)return null;[a[p],a[k]]=[a[k],a[p]];const z=a[k][k];a[k]=a[k].map(v=>v/z);for(let i=0;i<n;i++)if(i!==k){const b=a[i][k];a[i]=a[i].map((v,j)=>v-b*a[k][j]);}}
 return a.map(r=>r.slice(n));}
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
function ols(rows,keys,min=24){
 const r=rows.filter(x=>fin(x.y)&&keys.every(k=>fin(x[k]))).sort((a,b)=>a.t-b.t),n=r.length,p=keys.length+1;
 if(n<Math.max(min,p*5))return {error:`Insufficient complete quarters (${n}; need ${Math.max(min,p*5)})`,n,keys};
 const means=keys.map(k=>mean(r.map(x=>x[k]))),sd=keys.map((k,j)=>Math.sqrt(mean(r.map(x=>(x[k]-means[j])**2))));
 if(sd.some(s=>s<1e-8))return {error:'A factor has no usable variation',n,keys};
 const X=r.map(x=>[1,...keys.map((k,j)=>(x[k]-means[j])/sd[j])]),y=r.map(x=>x.y);
 const xx=Array.from({length:p},(_,i)=>Array.from({length:p},(_,j)=>X.reduce((s,x)=>s+x[i]*x[j],0))),inv=inverse(xx);
 if(!inv)return {error:'Collinear factors: deselect a factor',n,keys};
 const condition=Math.max(...xx.map(a=>a.reduce((s,x)=>s+Math.abs(x),0)))*Math.max(...inv.map(a=>a.reduce((s,x)=>s+Math.abs(x),0)));
 if(condition>1e5)return {error:'Unstable factor matrix: deselect a factor',n,keys};
 const xy=Array.from({length:p},(_,i)=>X.reduce((s,x,j)=>s+x[i]*y[j],0)),b=inv.map(x=>dot(x,xy)),pred=X.map(x=>dot(x,b)),e=y.map((v,i)=>v-pred[i]);
 // Newey-West/Bartlett, four quarterly lags; normal-approximation intervals, descriptive only.
 const S=Array.from({length:p},()=>Array(p).fill(0));
 for(let i=0;i<p;i++)for(let j=0;j<p;j++){
  for(let t=0;t<n;t++)S[i][j]+=e[t]**2*X[t][i]*X[t][j];
  for(let l=1;l<=Math.min(4,n-1);l++)for(let t=l;t<n;t++)S[i][j]+=(1-l/5)*e[t]*e[t-l]*(X[t][i]*X[t-l][j]+X[t-l][i]*X[t][j]);
 }
 const covariance=inv.map(a=>inv.map(z=>a.reduce((s,x,i)=>s+x*dot(S[i],z),0)*n/(n-p)));
 const beta=Object.fromEntries(keys.map((k,j)=>[k,b[j+1]/sd[j]])),se=Object.fromEntries(keys.map((k,j)=>[k,Math.sqrt(Math.max(0,covariance[j+1][j+1]))/sd[j]]));
 const sst=y.reduce((s,v)=>s+(v-mean(y))**2,0),sse=e.reduce((s,v)=>s+v*v,0);
 return {n,keys,beta,se,intercept:b[0]-dot(keys.map(k=>beta[k]),means),covariance,sd,r2:sst>0?1-sse/sst:null,rmse:Math.sqrt(sse/n),condition,rows:r,pred,first:iso(r[0].t),last:iso(r[n-1].t)};
}
function fit(rows,keys){const m=ols(rows,keys);if(m.error)return m;
 const cut=Math.floor(m.rows.length*.75),train=ols(m.rows.slice(0,cut),keys),test=m.rows.slice(cut);
 if(!train.error&&test.length>=6){const avg=mean(train.rows.map(r=>r.y));m.holdout={n:test.length,rmse:Math.sqrt(mean(test.map(r=>(r.y-train.intercept-keys.reduce((s,k)=>s+train.beta[k]*r[k],0))**2))),naive:Math.sqrt(mean(test.map(r=>(r.y-avg)**2)))};}
 return m;}
function impact(model,shocks){
 if(model.error)return {error:model.error};
 const entries=FACTORS.map(([k,,unit,scale])=>[k,shocks[k]/scale]);
 if(entries.some(([,v])=>!fin(v)))return {error:'Enter finite shock values'};
 const active=entries.filter(([,v])=>v!==0);
 if(active.some(([k])=>!fin(model.beta?.[k])))return {error:'A nonzero shock has no coefficient. Fit that factor or enter an explicit assumption.'};
 const contributions=Object.fromEntries(entries.map(([k,x])=>[k,x===0?0:model.beta[k]*x])),delta=Object.values(contributions).reduce((s,x)=>s+x,0);
 if(!fin(delta))return {error:'Scenario exceeds numeric range'};
 let band=null;if(model.covariance){const z=[0,...model.keys.map((k,j)=>(entries.find(x=>x[0]===k)?.[1]||0)/model.sd[j])];band=1.96*Math.sqrt(Math.max(0,z.reduce((s,x,i)=>s+x*dot(model.covariance[i],z),0)));}
 const extrapolation=active.filter(([k,x])=>model.rows&&Math.abs(x)>Math.max(...model.rows.map(r=>Math.abs(r[k])))).map(x=>x[0]);
 return {delta,contributions,band,extrapolation};
}
function projections(q,k,delta){
 if(!q||!fin(delta))return [];
 const v=q.values,rev=v.revenue,ccy=x=>fin(x)?x:null;
 if(k==='revenue'&&q.yearAgoRevenue>0&&fin(rev))return [['Reference revenue',rev],['Scenario revenue',rev+q.yearAgoRevenue*delta/100>=0?ccy(rev+q.yearAgoRevenue*delta/100):null]];
 const key={om:'oi',nm:'ni',ocfm:'ocf',fcfm:'fcf'}[k],base=key==='fcf'&&fin(v.ocf)&&fin(v.capex)?v.ocf-v.capex:v[key];
 return key&&fin(base)&&rev>0?[['Reference '+TARGETS[k],q[k]],['Scenario '+TARGETS[k],q[k]+delta],['Change in amount at fixed revenue',rev*delta/100]]:[];
}
async function json(url){const r=await fetch(url,{cache:'no-cache',signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
function plot(m){if(m.error)return '';const ps=m.rows.map((r,i)=>[m.pred[i],r.y,iso(r.t)]),lo=Math.min(...ps.flatMap(p=>p.slice(0,2))),hi=Math.max(...ps.flatMap(p=>p.slice(0,2))),span=hi-lo||1,x=v=>38+300*(v-lo)/span,y=v=>222-190*(v-lo)/span;
 return `<svg viewBox="0 0 380 260" role="img" aria-label="Fitted versus observed, in sample"><line x1="38" y1="222" x2="338" y2="32" stroke="currentColor" opacity=".4"/>${ps.map(p=>`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3" fill="var(--accent,#3974ac)"><title>${p[2]} · fitted ${p[0].toFixed(2)} · observed ${p[1].toFixed(2)}</title></circle>`).join('')}<text x="110" y="250" fill="currentColor">Fitted (pp / %)</text><text x="10" y="18" fill="currentColor">Observed (pp / %)</text><text x="38" y="235" fill="currentColor">${lo.toFixed(1)}</text><text x="310" y="235" fill="currentColor">${hi.toFixed(1)}</text></svg>`;}
function csv(rows){const quote=v=>'"'+String(v??'').replace(/"/g,'""').replace(/^[=+@]/,x=>"'"+x)+'"';return rows.map(r=>r.map(quote).join(',')).join('\r\n');}
function download(name,data,type){const a=document.createElement('a'),u=URL.createObjectURL(new Blob([data],{type}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
async function mount(box,{company:c,cik,ticker,here=()=>true}){
 const site=root.FF_DATA||'data/',hub='disclosures/data/market/history/';
 box.innerHTML='<p role="status">Loading shock panel: company statements, macro history and market returns…</p>';
 const urls={macro:hub+'macro.json',stock:hub+'t/'+encodeURIComponent(ticker)+'.json',market:hub+'t/SPY.json',index:site+'index.json'};
 const loaded=await Promise.allSettled(Object.values(urls).map(json));if(!here())return;
 const data={},status=[];Object.keys(urls).forEach((k,i)=>{if(loaded[i].status==='fulfilled')data[k]=loaded[i].value;else status.push(k+': '+loaded[i].reason.message);});
 const choices=(data.index?.companies||[]).filter(p=>String(p.cik)!==String(cik)&&String(p.sic)===String(c.profile?.sic)&&p.ticker).sort((a,b)=>(b.revenue||0)-(a.revenue||0)).slice(0,30);
 const selected=new Set(choices.slice(0,5).map(p=>String(p.cik)));
 box.innerHTML=`<section class="section shock-panel"><div class="section-head"><h2>Shock panel</h2><span class="tag">Historical association · scenario laboratory</span></div>
 <p>Rates, exchange rates, employment and peer performance → operating outcomes and stock returns. A change is not an identified exogenous surprise; this panel does not establish causality.</p>
 <div class="shock-controls"><label>Outcome<select data-target>${Object.entries(TARGETS).map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><label>Factor timing<select data-lag><option value="0">Same quarter</option><option value="1">Previous quarter</option><option value="2">Two quarters earlier</option></select></label><label>Coefficients<select data-mode><option value="fit">Historical multivariate fit</option><option value="manual">My explicit assumptions</option></select></label></div>
 <div class="shock-inputs">${FACTORS.map(([k,l,u])=>`<label><span>${esc(l)}</span><input type="number" data-shock="${k}" value="0" step="${k==='rates'?25:0.5}" aria-label="${esc(l)} shock">${u}${k==='fx'?'<small>Positive = stronger USD</small>':''}</label>`).join('')}</div>
 <p class="muted small">Inputs are changes relative to a reference scenario. +100 bp = +1 percentage point in the Treasury yield. Employment uses the unemployment rate; +1 pp means weaker employment. Peer input is a change in revenue growth, not an earnings surprise.</p>
 <div class="pills"><button type="button" data-preset="tight">Tighter conditions</button><button type="button" data-preset="weak">Demand slowdown</button><button type="button" data-preset="zero">Reset shocks</button></div>
 <details open><summary>Factors and peer basket</summary><div class="shock-controls">${FACTORS.map(([k,l])=>`<label><input type="checkbox" data-factor="${k}" checked> ${esc(l)}</label>`).join('')}</div><p class="small">Joint fit controls for the selected factors; stock-return fit additionally controls for SPY total return, held unchanged in scenarios. Deselect a factor to inspect a smaller model; a nonzero shock for an omitted factor cannot be calculated.</p><div class="shock-peers">${choices.map(p=>`<label><input type="checkbox" data-peer="${p.cik}" ${selected.has(String(p.cik))?'checked':''}>${esc(p.ticker)} · ${esc(p.name)}</label>`).join('')||'<p>No same-SIC peer companies available. Deselect the peer factor or use explicit assumptions.</p>'}</div><button type="button" data-refit>Load selected peers & refit (maximum 5)</button><p data-load aria-live="polite"></p></details>
 <div data-manual hidden><h3>Explicit coefficient assumptions</h3><p>Blank means unknown. Enter an explicit 0 only when you intend to assume no effect. Units: outcome pp per +100 bp rates, +1% USD, +1 pp unemployment or peer growth.</p><div class="shock-inputs">${FACTORS.map(([k,l])=>`<label>${esc(l)}<input type="number" data-beta="${k}" step="0.1" aria-label="${esc(l)} assumed coefficient"></label>`).join('')}</div></div>
 <div data-result aria-live="polite"></div><div class="pills"><button type="button" data-export>Export scenario JSON</button><button type="button" data-csv>Export fitted sample CSV</button></div>
 <details class="method-note"><summary>Sources, timing and interpretation</summary><p>Macro snapshot: ${esc(data.macro?.generated_at||'unavailable')}. Company snapshot: ${esc(data.index?.generated||'unavailable')}. Rates and USD use 13-week changes; unemployment uses the 13-week change in U-3. Positive USD means broad-dollar appreciation, not an individual bilateral exchange rate.</p><ul>${FACTORS.filter(x=>x[4]).map(([,,u,,id])=>`<li><a href="https://fred.stlouisfed.org/series/${id}" target="_blank" rel="noopener">${id}</a> · source observation through ${esc(data.macro?.series?.[id]?.last||'unavailable')}</li>`).join('')}</ul><p>Operating outcomes: revenue YoY growth, or quarterly profit/cash margin levels. Stock outcomes: non-overlapping calendar-quarter total return (dividends included) and split-adjusted price return (dividends excluded). Price return requires the separate price series; total returns are never substituted. Neither is a price target. Factor timing is relative to the outcome quarter. Peer factor: median of selected companies’ latest quarter ending on or before the factor date, no more than 120 days old; varying membership and fiscal dates affect comparability. Target company is excluded.</p><p>Financial history uses latest reported versions; a missing Q4 can be annual less three consecutive quarters. Macro data use approximate publication lags and current revised vintages. Peer alignment is by period end, not filing availability. This is retrospective explanatory analysis, NOT a point-in-time trading backtest or causal estimate. Chronological holdout, when shown, still uses revised data.</p><p>OLS with intercept; minimum max(24, 5 × parameter count) complete quarters, standardized-factor conditioning check. Coefficient intervals use Newey–West covariance (4 quarterly lags) and a 1.96 normal approximation. The scenario interval covers coefficient uncertainty only, not future residuals, shock uncertainty or model uncertainty. Do not add operating and stock effects: the stock model is separate and may already reflect the operating channel. Banks and insurers require industry-specific interpretation of cash margins. Margin scenarios hold revenue fixed; revenue scenarios hold other outcomes unmodeled.</p><p class="shock-warning">${esc(status.length?status.join(' · '):'Data requests succeeded. Inspect each source date; snapshot generation does not imply fresh underlying observations.')}</p><p><a href="#c-${cik}-revisions">Company filing versions & evidence</a> · <a href="#c-${cik}-cash">Company quality & cash measures</a></p></details></section>`;
 const section=box.querySelector('.shock-panel');let peers=[],fits={},D,last={},seq=0;
 const get=k=>section.querySelector(k),all=k=>[...section.querySelectorAll(k)];
 const read=sel=>Object.fromEntries(all(sel).map(e=>[e.dataset.shock||e.dataset.beta,e.value.trim()===''?null:Number(e.value)]));
 function draw(){
  const key=get('[data-target]').value,mode=get('[data-mode]').value,shocks=read('[data-shock]'),m=mode==='fit'?fits[key]||{error:'No fitted model'}:{beta:read('[data-beta]'),keys:FACTORS.map(x=>x[0])};
  get('[data-manual]').hidden=mode!=='manual';const r=impact(m,shocks),q=[...(D?.quarters||[])].reverse().find(x=>fin(x[key])),rows=projections(q,key,r.delta),f=v=>fin(v)?v.toFixed(2):'—';
  last={schema:1,company:{cik,ticker,currency:c.currency||'USD'},created_at:new Date().toISOString(),outcome:key,mode,lag_quarters:+get('[data-lag]').value,shocks,coefficient_units:'outcome pp per +100bp rates / +1% USD / +1pp unemployment / +1pp peer growth',coefficients:m.beta||null,sample:{n:m.n,first:m.first,last:m.last},data_sources:{...urls,macro_generated:data.macro?.generated_at,company_generated:data.index?.generated,peers:peers.map(p=>p.profile?.cik)},reference_period:q?.end,result:r,limitations:'Descriptive association; revised vintages; no causal identification or point-in-time backtest; Stock returns are historical conditional changes, not price targets; stockPrice excludes dividends.'};
  const max=Math.max(1,...Object.values(r.contributions||{}).map(Math.abs));
  get('[data-result]').innerHTML=`<h3>${esc(TARGETS[key])}</h3>${m.error&&mode==='fit'?`<p class="shock-warning">${esc(m.error)}. Add history, deselect factors, or use explicit assumptions.</p>`:''}${r.error?`<p class="shock-warning">${esc(r.error)}</p>`:`<div class="shock-cards"><article><span>Conditional change vs reference</span><strong>${f(r.delta)} pp</strong><small>${mode==='manual'?'User assumptions':'Historical fitted association'}${key.startsWith('stock')?' · market return held fixed':''}</small></article><article><span>Coefficient-only 95% interval</span><strong>${fin(r.band)?f(r.delta-r.band)+' to '+f(r.delta+r.band):'Not available'}</strong><small>Not a future-outcome prediction interval</small></article></div><div class="shock-bars">${FACTORS.map(([k,l])=>`<div><span>${esc(l)}</span><span class="shock-track"><i style="width:${Math.abs(r.contributions[k])/max*100}%;background:${r.contributions[k]<0?'#b65348':'#237e79'}"></i></span><b>${f(r.contributions[k])} pp</b></div>`).join('')}</div>${r.extrapolation?.length?'<p class="shock-warning">Shock magnitude exceeds observed factor levels: '+esc(r.extrapolation.join(', '))+'. Extrapolation can be unreliable.</p>':''}${rows.length?`<p>Illustrative reference: ${esc(q.end)} · actual reported quarter, not a next-quarter forecast. ${rows.map(([l,v])=>esc(l)+': <b>'+esc(!fin(v)?'Not meaningful':l.includes('margin')?f(v)+'%':new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(v)+' '+(c.currency||'USD'))+'</b>').join(' · ')}</p>`:''}`}
  ${mode==='fit'&&!m.error?`<div class="shock-grid"><div><h4>Fitted sample</h4><p>${m.n} quarters · ${m.first} → ${m.last}<br>R² ${f(m.r2)} · RMSE ${f(m.rmse)} pp</p>${m.holdout?`<p>Chronological holdout (${m.holdout.n} quarters): RMSE ${f(m.holdout.rmse)} vs training-mean baseline ${f(m.holdout.naive)} pp. Revised-vintage diagnostic only.</p>`:'<p>Not enough history for a separate holdout.</p>'}<div class="tbl-wrap"><table><thead><tr><th>Factor</th><th>Coefficient</th><th>Approx. 95% interval</th></tr></thead><tbody>${m.keys.map(k=>`<tr><td>${esc(FACTORS.find(x=>x[0]===k)?.[1]||'SPY return control')}</td><td>${f(m.beta[k])}</td><td>${f(m.beta[k]-1.96*m.se[k])} to ${f(m.beta[k]+1.96*m.se[k])}</td></tr>`).join('')}</tbody></table></div></div><div>${plot(m)}<p class="small">In-sample observed vs fitted. Hover a point for its date.</p></div></div>`:''}`;
 }
 function refit(){D=dataset(c,data.macro,peers,data.stock,data.market,+get('[data-lag]').value);const keys=all('[data-factor]:checked').map(e=>e.dataset.factor);fits=Object.fromEntries(Object.keys(TARGETS).map(k=>[k,keys.length?fit(D.rows[k],k.startsWith('stock')?[...keys,'market']:keys):{error:'Select at least one factor'}]));draw();}
 async function loadPeers(){const ids=all('[data-peer]:checked').map(e=>e.dataset.peer);if(ids.length>5){get('[data-load]').textContent='Select at most 5 peers.';return;}const request=++seq;get('[data-load]').textContent='Loading peer statements…';const rs=await Promise.allSettled(ids.map(id=>json(site+'c/'+id+'.json')));if(!here()||request!==seq)return;peers=rs.filter(r=>r.status==='fulfilled').map(r=>r.value);get('[data-load]').textContent=`${peers.length}/${ids.length} peer statements loaded. ${rs.some(r=>r.status==='rejected')?'Some requests failed; the fitted basket is smaller.':''}`;refit();}
 all('[data-shock],[data-beta]').forEach(e=>e.addEventListener('input',draw));get('[data-target]').addEventListener('change',()=>{all('[data-beta]').forEach(e=>e.value='');draw();});get('[data-mode]').addEventListener('change',draw);all('[data-lag],[data-factor]').forEach(e=>e.addEventListener('change',refit));get('[data-refit]').onclick=loadPeers;
 all('[data-preset]').forEach(b=>b.onclick=()=>{const presets={tight:[100,5,0.5,-5],weak:[-100,-3,1,-10],zero:[0,0,0,0]},v=presets[b.dataset.preset];FACTORS.forEach(([k],i)=>get(`[data-shock="${k}"]`).value=v[i]);draw();});
 get('[data-export]').onclick=()=>download(`shock-${cik}.json`,JSON.stringify(last,null,2),'application/json');
 get('[data-csv]').onclick=()=>{const m=fits[get('[data-target]').value];if(!m?.rows){get('[data-load]').textContent='No complete fitted sample to export.';return;}download(`shock-${cik}-sample.csv`,csv([['period_end','observed','fitted',...m.keys],...m.rows.map((r,i)=>[iso(r.t),r.y,m.pred[i],...m.keys.map(k=>r[k])])]),'text/csv');};
 refit();await loadPeers();
}
const api={financials,metrics,weekly,prices,change,dataset,ols,fit,impact,projections,csv,mount};root.FFShock=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?{}:window);
