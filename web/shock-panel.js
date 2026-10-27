/* Company shock laboratory. Descriptive multivariate associations, never identified causal shocks. */
(function(root){
'use strict';
const DAY=86400000, WEEK=7*DAY, fin=x=>typeof x==='number'&&Number.isFinite(x);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const iso=t=>new Date(t).toISOString().slice(0,10), time=s=>Date.parse(s+'T00:00:00Z');
const FACTORS=[
 ['rates','10Y Treasury','bp',100,'DGS10'],['fx','Broad USD appreciation','%',1,'DTWEXBGS'],
 ['jobs','Unemployment rate','pp',1,'UNRATE'],['peers','Peer revenue YoY growth','pp',1,null],
 ['rates2','2Y Treasury','bp',100,'DGS2'],['real','10Y real yield','bp',100,'DFII10'],
 ['curve','10Y–2Y yield curve','bp',100,'T10Y2Y'],['credit','Baa credit spread','bp',100,'BAA10Y'],
 ['inflation','CPI YoY inflation change','pp',1,'CPIAUCSL'],['oil','WTI oil price change','%',1,'DCOILWTICO'],
 ['vix','VIX change','points',1,'VIXCLS'],['payrolls','Payroll YoY growth','pp',1,'PAYEMS'],
 ['retail','Retail-sales YoY growth','pp',1,'RSAFS'],['ip','Industrial-production YoY growth','pp',1,'INDPRO'],
 ['peerom','Peer operating margin','pp',1,null],['market','SPY total return','%',1,null]
];
const TARGETS={revenue:'Revenue YoY growth',om:'Operating margin',nm:'Net margin',ocfm:'Operating cash margin',fcfm:'Free cash flow margin',stock:'Stock total return',stockPrice:'Stock price return (ex-dividends)',gm:'Gross margin',revqoq:'Revenue QoQ growth (not seasonally adjusted)',oiChange:'YoY operating-profit change / prior-year revenue',niChange:'YoY net-income change / prior-year revenue',ocfChange:'YoY OCF change / prior-year revenue',capexm:'Cash CapEx / revenue',rdm:'R&D / revenue',sbcm:'Stock compensation / revenue',accrual:'Accruals / average assets',roa:'Net income / average assets (quarterly)',currentratio:'Current ratio',dso:'Days sales outstanding',ccc:'Cash conversion cycle'};
const unit=k=>['dso','ccc'].includes(k)?'days':k==='currentratio'?'×':'pp';
const MODEL_NAMES={ols:'OLS + HAC',ridge:'Ridge (L2)',huber:'Huber robust IRLS',arx:'ARX(1) + HAC'};
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
 for(const q of c.quality?.q||[]){for(const k of ['dso','ccc'])put(q.end,k,q.wc?.[k],{source:'quarter working-capital schedule'});}
 for(const q of c.quality?.q||[])for(const [k,v] of Object.entries(q.health?.inputs||{}))put(q.end,k,v,{ref:q.health?.ev?.[k]});
 // Supplemental history fills missing cells only; never mix currencies or issuers.
 const extra=c.shock_history;
 if(extra?.v===1&&String(extra.cik)===String(c.profile?.cik)&&extra.unit===(c.currency||'USD'))
  for(const q of extra.rows||[])for(const [k,v] of Object.entries(q.values||{}))
   if(!fin(out.get(q.end)?.values[k]))put(q.end,k,v,{source:'SEC extended history',ref:q.sources?.[k],snapshot:extra.generated_at});
 return [...out.values()].sort((a,b)=>a.t-b.t);
}
function metrics(rows){return rows.map(p=>{
 const v=p.values, prev=rows.find(x=>p.t-x.t>=75*DAY&&p.t-x.t<=110*DAY), prior=rows.find(x=>Math.abs(p.t-x.t-364*DAY)<=20*DAY),r=v.revenue;
 const ratio=(a,b)=>fin(a)&&fin(b)&&b>0?a/b:null, pct=(a,b)=>fin(ratio(a,b))?100*ratio(a,b):null, avg=fin(v.assets_open)&&v.assets_open>0&&fin(v.assets_close)&&v.assets_close>0?(v.assets_open+v.assets_close)/2:null;
 const dy=k=>fin(v[k])&&fin(prior?.values[k])?pct(v[k]-prior.values[k],prior.values.revenue):null;
 return {...p,gm:pct(v.gp,r),revqoq:r>0&&prev?.values.revenue>0?100*(r/prev.values.revenue-1):null,oiChange:dy('oi'),niChange:dy('ni'),ocfChange:dy('ocf'),capexm:v.capex>=0?pct(v.capex,r):null,rdm:pct(v.rd,r),sbcm:pct(v.sbc,r),accrual:fin(v.ni)&&fin(v.ocf)?pct(v.ni-v.ocf,avg):null,roa:pct(v.ni,avg),currentratio:ratio(v.current_assets,v.current_liabilities),dso:v.dso,ccc:v.ccc,previousRevenue:prev?.values.revenue,revenue:r>0&&prior?.values.revenue>0?100*(r/prior.values.revenue-1):null,
  om:r>0&&fin(v.oi)?100*v.oi/r:null,nm:r>0&&fin(v.ni)?100*v.ni/r:null,
  ocfm:r>0&&fin(v.ocf)?100*v.ocf/r:null,fcfm:r>0&&fin(v.ocf)&&fin(v.capex)&&v.capex>=0?100*(v.ocf-v.capex)/r:null,yearAgoRevenue:prior?.values.revenue};
 });}
function weekly(doc,key){const d=doc?.weekly?.data?.[key],start=time(doc?.weekly?.start||'');return Array.isArray(d)&&fin(start)?d.map((v,i)=>({t:start+i*WEEK,v})).filter(x=>fin(x.v)):[];}
function prices(d,key='c'){const start=time(d?.start||'');return fin(start)&&Array.isArray(d?.[key])?d[key].map((v,i)=>({t:start+i*WEEK,v})).filter(x=>fin(x.v)&&x.v>0):[];}
function change(rows,t,pct=false,span=13*WEEK){const a=near(rows,t),b=near(rows,t-span);return a&&b&&(!pct||b.v>0)?pct?100*(a.v/b.v-1):a.v-b.v:null;}
function factorRows(macro,peers){
 const specs={rates:['y10','change'],fx:['usd','percent'],jobs:['unrate','change'],rates2:['y2','change'],real:['real10','change'],curve:['curve2','change'],credit:['credit','change'],inflation:['cpi','change'],oil:['oil','percent'],vix:['vix','change'],payrolls:['payrolls','level'],retail:['retail','level'],ip:['ip','level']};
 const series=Object.fromEntries(Object.entries(specs).map(([k,[feature]])=>[k,weekly(macro,feature)]));
 const times=[...new Set(Object.values(series).flatMap(rs=>rs.map(x=>x.t)))].sort((a,b)=>a-b);
 return times.map(t=>{const ps=peers.map(p=>near(p,t,120)).filter(Boolean),out={t,peers:median(ps.filter(p=>fin(p.revenue)).map(p=>p.revenue)),peerom:median(ps.filter(p=>fin(p.om)).map(p=>p.om)),peerCount:ps.filter(p=>fin(p.revenue)).length};
  for(const [k,[,how]] of Object.entries(specs))out[k]=how==='level'?near(series[k],t)?.v??null:change(series[k],t,how==='percent');return out;});
}
function dataset(c,macro,peerCompanies,stock,market,lag=0){
 const f=factorRows(macro,peerCompanies.map(p=>metrics(financials(p)))),qs=metrics(financials(c));
 const attach=(t,y)=>{const z=near(f,t-lag*13*WEEK);return {...(z||{}),t,y,market:change(prices(market),t-lag*13*WEEK,true)};};
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
 if(sd.some(s=>!fin(s)||s<1e-8))return {error:'A factor has no usable variation',n,keys};
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
function fit(rows,keys,options={}){if(options.model&&options.model!=='ols')return advancedFit(rows,keys,options);const m=ols(rows,keys);if(m.error)return m;
 const cut=Math.floor(m.rows.length*.75),train=ols(m.rows.slice(0,cut),keys),test=m.rows.slice(cut);
 if(!train.error&&test.length>=6){const avg=mean(train.rows.map(r=>r.y));m.holdout={n:test.length,rmse:Math.sqrt(mean(test.map(r=>(r.y-train.intercept-keys.reduce((s,k)=>s+train.beta[k]*r[k],0))**2))),naive:Math.sqrt(mean(test.map(r=>(r.y-avg)**2)))};}
 return m;}
function lagged(rows){const a=rows.slice().sort((x,y)=>x.t-y.t);return a.map((r,i)=>({...r,ownLag:i&&r.t-a[i-1].t>=75*DAY&&r.t-a[i-1].t<=110*DAY?a[i-1].y:null}));}
function penalized(rows,keys,{model='ridge',alpha=10,epsilon=1.35}={}){
 const r=rows.filter(x=>fin(x.y)&&keys.every(k=>fin(x[k]))).sort((a,b)=>a.t-b.t),n=r.length,p=keys.length+1;
 if(!['ridge','huber'].includes(model)||(model==='ridge'&&(!fin(alpha)||alpha<=0||alpha>10000))||!fin(epsilon)||epsilon<=0)return {error:'Invalid model settings',n,keys};
 if(n<Math.max(24,5*p))return {error:`Insufficient complete quarters (${n}; need ${Math.max(24,5*p)})`,n,keys};
 const means=keys.map(k=>mean(r.map(x=>x[k]))),sd=keys.map((k,j)=>Math.sqrt(mean(r.map(x=>(x[k]-means[j])**2))));
 if(sd.some(x=>!fin(x)||x<1e-8))return {error:'A factor has no usable variation',n,keys};
 const X=r.map(x=>[1,...keys.map((k,j)=>(x[k]-means[j])/sd[j])]),y=r.map(x=>x.y);
 let w=Array(n).fill(1),b=null,iterations=0,converged=model==='ridge',downweighted=0;
 const solve=weights=>{const A=Array.from({length:p},(_,i)=>Array.from({length:p},(_,j)=>X.reduce((s,x,t)=>s+weights[t]*x[i]*x[j],0)+(model==='ridge'&&i===j&&i>0?alpha:0))),inv=inverse(A);if(!inv)return null;const xy=Array.from({length:p},(_,i)=>X.reduce((s,x,t)=>s+weights[t]*x[i]*y[t],0));return inv.map(x=>dot(x,xy));};
 b=solve(w);if(!b)return {error:'Collinear factors: deselect a factor or use Ridge',n,keys};
 for(let it=0;model==='huber'&&it<100;it++){
  const e=y.map((v,i)=>v-dot(X[i],b)),center=median(e),scale=1.4826*median(e.map(v=>Math.abs(v-center)));
  if(scale<1e-10){if(Math.max(...e.map(Math.abs))<1e-7){converged=true;break;}return {error:'Degenerate robust scale: choose another model',n,keys};}
  w=e.map(v=>Math.abs(v)<=epsilon*scale?1:epsilon*scale/Math.abs(v));downweighted=w.filter(v=>v<.999).length;
  const next=solve(w);if(!next)return {error:'Robust weighted design is singular',n,keys};iterations=it+1;
  converged=Math.max(...next.map((v,j)=>Math.abs(v-b[j])))<1e-7*(1+Math.max(...b.map(Math.abs)));b=next;if(converged)break;
 }
 if(!converged)return {error:'Huber IRLS did not converge; coefficients withheld',n,keys};
 const beta=Object.fromEntries(keys.map((k,j)=>[k,b[j+1]/sd[j]])),pred=X.map(x=>dot(x,b)),sst=y.reduce((s,v)=>s+(v-mean(y))**2,0),sse=y.reduce((s,v,i)=>s+(v-pred[i])**2,0);
 return {model,n,keys,beta,se:{},intercept:b[0]-dot(keys.map(k=>beta[k]),means),sd,r2:sst>0?1-sse/sst:null,rmse:Math.sqrt(sse/n),rows:r,pred,first:iso(r[0].t),last:iso(r[n-1].t),iterations,downweighted,alpha:model==='ridge'?alpha:null,interval_note:'No coefficient interval implemented for this estimator'};
}
function advancedFit(rows,keys,options){
 const ar=options.model==='arx',data=ar?lagged(rows):rows,ks=ar?[...keys,'ownLag']:keys,estimate=r=>ar?ols(r,ks):penalized(r,ks,options),m=estimate(data);if(m.error)return m;
 m.model=options.model;if(ar)m.persistence=m.beta.ownLag;
 const cut=Math.floor(m.rows.length*.75),train=estimate(m.rows.slice(0,cut)),test=m.rows.slice(cut);
 if(!train.error&&test.length>=6){const avg=mean(train.rows.map(r=>r.y));m.holdout={n:test.length,first:iso(test[0].t),last:iso(test.at(-1).t),rmse:Math.sqrt(mean(test.map(r=>(r.y-train.intercept-ks.reduce((s,k)=>s+train.beta[k]*r[k],0))**2))),naive:Math.sqrt(mean(test.map(r=>(r.y-avg)**2))),note:ar?'One-step conditional evaluation uses observed lagged outcomes':'Fixed chronological holdout'};}
 return m;
}
function compareModels(rows,keys,alpha=10){
 // Same eligible rows and split for all estimators; ownLag is only a regressor in ARX.
 const common=lagged(rows).filter(r=>fin(r.ownLag)&&fin(r.y)&&keys.every(k=>fin(r[k]))),cut=Math.floor(common.length*.75),train=common.slice(0,cut),test=common.slice(cut),avg=train.length?mean(train.map(r=>r.y)):null;
 return Object.keys(MODEL_NAMES).map(model=>{const ks=model==='arx'?[...keys,'ownLag']:keys,m=model==='ols'||model==='arx'?ols(train,ks):penalized(train,ks,{model,alpha});if(m.error||test.length<6)return {model,error:m.error||'Need at least 6 holdout quarters',n:train.length,test_n:test.length};const errors=test.map(r=>r.y-m.intercept-ks.reduce((s,k)=>s+m.beta[k]*r[k],0));return {model,n:train.length,test_n:test.length,first:iso(test[0].t),last:iso(test.at(-1).t),rmse:Math.sqrt(mean(errors.map(e=>e*e))),mae:mean(errors.map(Math.abs)),naive:Math.sqrt(mean(test.map(r=>(r.y-avg)**2)))};});
}
function coverage(rows,keys,model='ols'){
 if(model==='arx'){rows=lagged(rows);keys=[...new Set([...keys,'ownLag'])];}
 const complete=rows.filter(r=>fin(r.y)&&keys.every(k=>fin(r[k]))),need=Math.max(24,5*(keys.length+1));
 return {total:rows.length,n:complete.length,need,missing:Math.max(0,need-complete.length),
  first:complete.length?iso(complete[0].t):null,last:complete.length?iso(complete.at(-1).t):null,
  factors:FACTORS.map(([key,label])=>({key,label,n:rows.filter(r=>fin(r[key])).length})),
  periods:rows.map(r=>({t:r.t,complete:fin(r.y)&&keys.every(k=>fin(r[k]))}))};
}
function defaults(rows,stock=false){
 // Choose coverage and factor variation, never in-sample R² or test outcomes.
 const priority=['rates','fx','jobs','peers','credit','payrolls','retail','ip'];
 const sets=[...priority.map(k=>[k]),['rates','fx'],['rates','jobs'],['fx','jobs'],['rates','fx','jobs'],['rates','fx','peers']];
 const candidates=sets.map((s,i)=>{const keys=[...new Set(stock?[...s,'market']:s)],m=ols(rows,keys);return {keys,n:m.n,rank:i,error:m.error};}).filter(c=>!c.error);
 // Prefer the compact three-factor core when its coverage is within 10% of the maximum.
 const max=Math.max(0,...candidates.map(c=>c.n)),near=candidates.filter(c=>c.n>=max*.9);
 near.sort((a,b)=>b.keys.length-a.keys.length||a.rank-b.rank);
 return near[0]||{keys:stock?['rates','market']:['rates'],error:'No reliable fit yet. Historical observations remain visible; additional SEC history is collected in the background.'};
}
function recommend(rows,keys){
 // Fixed specification. All candidates share dates. Two expanding validation
 // blocks precede an untouched final test; no final-test score selects a model.
 const common=lagged(rows).filter(r=>fin(r.y)&&fin(r.ownLag)&&keys.every(k=>fin(r[k]))),testN=Math.max(6,Math.ceil(common.length*.2)),dev=common.slice(0,-testN),test=common.slice(-testN);
 const block=4,first=dev.length-block*2;
 if(first<Math.max(24,5*(keys.length+1)))return {error:'Need more history for train / validation / test separation. Keep the coverage-based default; no optimal model is claimed.',n:common.length};
 const specs=[{model:'ols'},...[1,10,100].map(alpha=>({model:'ridge',alpha})),{model:'huber'},{model:'arx'}];
 const estimate=(rs,s)=>s.model==='ols'||s.model==='arx'?ols(rs,s.model==='arx'?[...keys,'ownLag']:keys):penalized(rs,keys,s);
 const predict=(m,r)=>m.intercept+m.keys.reduce((s,k)=>s+m.beta[k]*r[k],0);
 const baseline=[];
 for(let i=0;i<2;i++){const cut=first+i*block,avg=mean(dev.slice(0,cut).map(r=>r.y));baseline.push(...dev.slice(cut,cut+block).map(r=>(r.y-avg)**2));}
 const ranking=specs.map(s=>{const errors=[];for(let i=0;i<2;i++){const cut=first+i*block,m=estimate(dev.slice(0,cut),s);if(m.error)return {...s,error:m.error};errors.push(...dev.slice(cut,cut+block).map(r=>(r.y-predict(m,r))**2));}return {...s,rmse:Math.sqrt(mean(errors)),n:errors.length};});
 const valid=ranking.filter(x=>fin(x.rmse)).sort((a,b)=>a.rmse-b.rmse),chosen=valid[0],naive=Math.sqrt(mean(baseline));
 if(!chosen)return {error:'No candidate passed both chronological validation blocks.',ranking};
 const train=estimate(dev,chosen);if(train.error)return {error:train.error,ranking};
 const avg=mean(dev.map(r=>r.y)),points=test.map(r=>({t:r.t,y:r.y,pred:predict(train,r),baseline:avg}));
 return {chosen,ranking,validation:{first:iso(dev[first].t),last:iso(dev.at(-1).t),n:8,naive},
  test:{n:test.length,first:iso(test[0].t),last:iso(test.at(-1).t),rmse:Math.sqrt(mean(points.map(p=>(p.y-p.pred)**2))),naive:Math.sqrt(mean(points.map(p=>(p.y-p.baseline)**2))),points},
  qualified:chosen.rmse<naive,keys,selection:'Lowest two-block expanding validation RMSE; final test excluded from selection. Fixed factors, lag and window.'};
}
function timePlot(rows,pred=[],units='pp',title='Actual quarterly history'){
 if(!rows.length)return '<p>No observations for this output yet.</p>';
 const values=rows.map(r=>r.y).concat(pred.filter(fin)),lo=Math.min(...values),hi=Math.max(...values),span=hi-lo||1;
 const x=t=>52+598*(t-rows[0].t)/(rows.at(-1).t-rows[0].t||1),y=v=>208-160*(v-lo)/span;
 const line=vs=>vs.map((v,i)=>`${i&&rows[i].t-rows[i-1].t<=110*DAY?'L':'M'}${x(rows[i].t).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
 return `<svg viewBox="0 0 700 260" role="img" aria-label="${esc(title)}"><text x="12" y="22" fill="currentColor">${esc(title)} (${esc(units)})</text>${[0,.5,1].map(z=>`<line x1="52" x2="650" y1="${y(lo+span*z)}" y2="${y(lo+span*z)}" stroke="currentColor" opacity=".12"/><text x="2" y="${y(lo+span*z)+4}" fill="currentColor" font-size="12">${(lo+span*z).toFixed(1)}</text>`).join('')}<path d="${line(rows.map(r=>r.y))}" fill="none" stroke="#237e79" stroke-width="2.5"/>${pred.length===rows.length?`<path d="${line(pred)}" fill="none" stroke="#bb7943" stroke-width="2" stroke-dasharray="5 4"/>`:''}${rows.map((r,i)=>`<circle cx="${x(r.t)}" cy="${y(r.y)}" r="3" fill="#237e79"><title>${iso(r.t)} · actual ${r.y.toFixed(2)}${fin(pred[i])?' · model '+pred[i].toFixed(2):''}</title></circle>`).join('')}<text x="52" y="236" fill="currentColor" font-size="12">${iso(rows[0].t)}</text><text x="575" y="236" fill="currentColor" font-size="12">${iso(rows.at(-1).t)}</text></svg><p class="small">Teal: observed${pred.length?' · dashed amber: model':''}. Dates and values appear on hover.</p>`;
}
function recommendationView(r,units){
 if(!r)return '';
 if(r.error)return `<p class="shock-warning">${esc(r.error)}</p>`;
 const fmt=x=>fin(x)?x.toFixed(2):'—',max=Math.max(1,...r.ranking.map(x=>x.rmse||0));
 return `<h3>Validation recommendation</h3><p>${r.qualified?'Applied':'Not applied: validation did not beat the mean baseline.'} · ${esc(MODEL_NAMES[r.chosen.model])}${r.chosen.alpha?' · α '+r.chosen.alpha:''}. Selected with 8 validation quarters (${r.validation.first} → ${r.validation.last}); final ${r.test.n} test quarters were held aside.</p><div class="shock-scores">${r.ranking.map(x=>`<article><span>${esc(MODEL_NAMES[x.model])}${x.alpha?' · '+x.alpha:''}</span><b>${x.error?'Unavailable':fmt(x.rmse)+' '+esc(units)}</b>${!x.error?`<meter min="0" max="${max}" value="${x.rmse}"></meter>`:''}</article>`).join('')}</div><p>Validation mean baseline: ${fmt(r.validation.naive)} ${esc(units)}. Untouched final-test RMSE: ${fmt(r.test.rmse)} vs mean baseline ${fmt(r.test.naive)} ${esc(units)}. Lower error is better. This is a retrospective diagnostic, not guaranteed future performance.</p>${timePlot(r.test.points,r.test.points.map(x=>x.pred),units,'Final test · excluded from selection')}`;
}
function responsePath(model,delta,horizon=4,persistent=false){if(!fin(delta)||!fin(model.persistence))return {error:'ARX persistence required'};if(Math.abs(model.persistence)>=1)return {error:'Unstable persistence (|phi| >= 1); recursive path withheld'};let y=0;return {points:Array.from({length:horizon},(_,i)=>{y=model.persistence*y+(i===0||persistent?delta:0);return y;})};}
function valuation({eps,pe,epsPct,pePct,fcf,wacc,g,waccBP,gBP,fcfPct}){
 const out={};if([eps,pe,epsPct,pePct].every(fin)&&eps>0&&pe>0&&epsPct>-100&&pePct>-100){out.pe={base:eps*pe,scenario:eps*(1+epsPct/100)*pe*(1+pePct/100)};out.pe.change=100*(out.pe.scenario/out.pe.base-1);}else out.pe={error:'P/E bridge requires positive EPS and P/E, with valid changes'};
 if([fcf,wacc,g,waccBP,gBP,fcfPct].every(fin)&&fcf>0&&fcfPct>-100&&g>-100&&g+gBP/100>-100&&wacc>g&&wacc+waccBP/100>g+gBP/100&&wacc>0&&wacc+waccBP/100>0){out.dcf={base:fcf/((wacc-g)/100),scenario:fcf*(1+fcfPct/100)/((wacc+waccBP/100-g-gBP/100)/100)};out.dcf.change=100*(out.dcf.scenario/out.dcf.base-1);}else out.dcf={error:'Perpetuity requires positive next-year FCFF and WACC > g in both scenarios'};
 return out;
}
function impact(model,shocks){
 if(model.error)return {error:model.error};
 const entries=FACTORS.map(([k,,,scale])=>{const v=Object.prototype.hasOwnProperty.call(shocks,k)?shocks[k]:0;return [k,fin(v)?v/scale:NaN];});
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
 if(k==='revqoq'&&q.previousRevenue>0&&fin(rev))return [['Reference revenue',rev],['Scenario revenue',rev+q.previousRevenue*delta/100>=0?rev+q.previousRevenue*delta/100:null]];
 if(['dso','ccc','currentratio','accrual','roa','oiChange','niChange','ocfChange'].includes(k))return fin(q[k])?[['Reference '+TARGETS[k],q[k],unit(k)],['Scenario '+TARGETS[k],q[k]+delta,unit(k)]]:[];
 const key={om:'oi',nm:'ni',ocfm:'ocf',fcfm:'fcf',gm:'gp',capexm:'capex',rdm:'rd',sbcm:'sbc'}[k],base=key==='fcf'&&fin(v.ocf)&&fin(v.capex)?v.ocf-v.capex:v[key];
 return key&&fin(base)&&rev>0?[['Reference '+TARGETS[k],q[k],'%'],['Scenario '+TARGETS[k],q[k]+delta,'%'],['Change in amount at fixed revenue',rev*delta/100]]:[];
}
async function supplemental(base,local,path){try{return await json(base+path);}catch(e){try{return await json(local+path);}catch(_){throw e;}}}
async function json(url){const r=await fetch(url,{cache:'no-cache',signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
function plot(m,units='pp'){if(m.error)return '';const ps=m.rows.map((r,i)=>[m.pred[i],r.y,iso(r.t)]),lo=Math.min(...ps.flatMap(p=>p.slice(0,2))),hi=Math.max(...ps.flatMap(p=>p.slice(0,2))),span=hi-lo||1,x=v=>38+300*(v-lo)/span,y=v=>222-190*(v-lo)/span;
 return `<svg viewBox="0 0 380 260" role="img" aria-label="Fitted versus observed, in sample"><line x1="38" y1="222" x2="338" y2="32" stroke="currentColor" opacity=".4"/>${ps.map(p=>`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3" fill="var(--accent,#3974ac)"><title>${p[2]} · fitted ${p[0].toFixed(2)} · observed ${p[1].toFixed(2)}</title></circle>`).join('')}<text x="110" y="250" fill="currentColor">Fitted (${esc(units)})</text><text x="10" y="18" fill="currentColor">Observed (${esc(units)})</text><text x="38" y="235" fill="currentColor">${lo.toFixed(1)}</text><text x="310" y="235" fill="currentColor">${hi.toFixed(1)}</text></svg>`;}
function csv(rows){const quote=v=>'"'+String(v??'').replace(/"/g,'""').replace(/^[=+@]/,x=>"'"+x)+'"';return rows.map(r=>r.map(quote).join(',')).join('\r\n');}
function download(name,data,type){const a=document.createElement('a'),u=URL.createObjectURL(new Blob([data],{type}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
async function mount(box,{company:c,cik,ticker,here=()=>true,restore=null}){
 const site=root.FF_DATA||'data/',hub='disclosures/data/market/history/',history=root.FF_SHOCK_HISTORY||'https://raw.githubusercontent.com/eurikamonica/filing-flows/shock-history/public/';
 box.innerHTML='<p role="status">Loading shock panel: company statements, macro history and market returns…</p>';
 const urls={macro:hub+'macro.json',stock:hub+'t/'+encodeURIComponent(ticker)+'.json',market:hub+'t/SPY.json',index:site+'index.json'};
 urls.history=history+'c/'+encodeURIComponent(cik)+'.json';urls.backfill=history+'status.json';
 const loaded=await Promise.allSettled(Object.entries(urls).map(([k,url])=>['history','backfill'].includes(k)?supplemental(history,site+'shock-history/',k==='history'?'c/'+encodeURIComponent(cik)+'.json':'status.json'):json(url)));if(!here())return;
 const data={},status=[];Object.keys(urls).forEach((k,i)=>{if(loaded[i].status==='fulfilled')data[k]=loaded[i].value;else if(!['history','backfill'].includes(k))status.push(k+': '+loaded[i].reason.message);});
 c={...c,profile:{...c.profile,cik:c.profile?.cik??cik},shock_history:data.history};
 const choices=(data.index?.companies||[]).filter(p=>/^\d+$/.test(String(p.cik))&&String(p.cik)!==String(cik)&&String(p.sic)===String(c.profile?.sic)&&p.ticker).sort((a,b)=>(b.revenue||0)-(a.revenue||0)).slice(0,30);
 const selected=new Set(choices.slice(0,5).map(p=>String(p.cik)));
 box.innerHTML=`<section class="section shock-panel"><div class="section-head"><h2>Shock panel</h2><span class="tag">Historical association · scenario laboratory</span></div>
 <p>Rates, exchange rates, employment and peer performance → operating outcomes and stock returns. A change is not an identified exogenous surprise; this panel does not establish causality.</p>${status.length?`<p class="shock-warning" role="status">Data source unavailable: ${esc(status.join(' · '))}. Available data remain usable; missing values are not zero.</p>`:''}
 <div class="shock-start"><div><h3>Start with usable data</h3><p>Defaults choose a compact model by coverage. Model recommendations use chronological validation with a separate final test.</p></div><div class="pills"><button type="button" data-defaults>Use reliable defaults</button><button type="button" data-recommend>Recommend model</button><button type="button" data-refresh>Refresh data</button></div><p data-default-note aria-live="polite"></p></div><div data-health></div>
 <div class="shock-controls"><label>Outcome<select data-target>${Object.entries(TARGETS).map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><label>Factor timing<select data-lag><option value="0">Same quarter</option><option value="1">Previous quarter</option><option value="2">Two quarters earlier</option><option value="4">Four quarters earlier</option></select></label><label>Coefficients<select data-mode><option value="fit">Historical multivariate fit</option><option value="manual">My explicit assumptions</option></select></label></div>
 <div class="shock-controls"><label>Estimator<select data-estimator>${Object.entries(MODEL_NAMES).map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><label>Ridge penalty α<input type="number" data-alpha min="0.01" max="10000" value="10" step="1"></label><label>Historical window<select data-window><option value="0">All available</option><option value="32">Latest 32 quarters</option><option value="40">Latest 40 quarters</option><option value="60">Latest 60 quarters</option></select></label></div><details><summary>Additional factors (all inputs below are editable)</summary><p>Rates / curve / credit use 13-week changes; oil and USD use 13-week percent changes; VIX uses index-point changes; CPI uses the 13-week change in its YoY rate. Payrolls, retail sales and industrial production use YoY growth levels. Peer operating margin is a median level. Overlapping rate factors can be collinear: select a compact set.</p></details><div class="shock-inputs">${FACTORS.slice(0,4).map(([k,l,u])=>`<label><span>${esc(l)}</span><input type="number" data-shock="${k}" value="0" step="${u==='bp'?25:0.5}" aria-label="${esc(l)} shock">${u}${k==='fx'?'<small>Positive = stronger USD</small>':''}</label>`).join('')}</div><details data-extra-inputs><summary>12 additional shock inputs</summary><div class="shock-inputs">${FACTORS.slice(4).map(([k,l,u])=>`<label><span>${esc(l)}</span><input type="number" data-shock="${k}" value="0" step="${u==='bp'?25:0.5}" aria-label="${esc(l)} shock">${u}${k==='fx'?'<small>Positive = stronger USD</small>':''}</label>`).join('')}</div></details>
 <p class="muted small">Inputs are changes relative to a reference scenario. +100 bp = +1 percentage point in the Treasury yield. Employment uses the unemployment rate; +1 pp means weaker employment. Peer input is a change in revenue growth, not an earnings surprise.</p>
 <div class="pills"><button type="button" data-preset="tight">Tighter conditions</button><button type="button" data-preset="weak">Demand slowdown</button><button type="button" data-preset="zero">Reset shocks</button></div>
 <details data-factor-settings><summary>Factors and peer basket · advanced settings</summary><div class="shock-controls">${FACTORS.map(([k,l])=>`<label><input type="checkbox" data-factor="${k}" ${['rates','fx','jobs','peers'].includes(k)?'checked':''}> ${esc(l)}</label>`).join('')}</div><p class="small">Joint fit controls for the selected factors; stock-return fits always include SPY total return. This market control stays contemporaneous even when other factors are lagged. The SPY input can now shock this control; 0 holds it unchanged. Operating models include SPY only when selected. Deselect a factor to inspect a smaller model; a nonzero shock for an omitted factor cannot be calculated.</p><div class="shock-peers">${choices.map(p=>`<label><input type="checkbox" data-peer="${p.cik}" ${selected.has(String(p.cik))?'checked':''}>${esc(p.ticker)} · ${esc(p.name)}</label>`).join('')||'<p>No same-SIC peer companies available. Deselect the peer factor or use explicit assumptions.</p>'}</div><button type="button" data-refit>Load selected peers & refit (maximum 5)</button><p data-load aria-live="polite"></p></details>
 <div data-manual hidden><h3>Explicit coefficient assumptions</h3><p>Blank means unknown. Enter an explicit 0 only when you intend to assume no effect. Units: selected output units per +100 bp for yield/spread inputs, or per +1 displayed unit for other inputs. Blank means unknown, not zero.</p><div class="shock-inputs">${FACTORS.map(([k,l])=>`<label>${esc(l)}<input type="number" data-beta="${k}" step="0.1" aria-label="${esc(l)} assumed coefficient"></label>`).join('')}</div></div>
 <div data-result aria-live="polite"></div><div data-history-chart></div><div data-recommendation></div><div data-comparison></div><div data-valuation></div><div class="pills"><button type="button" data-export>Export scenario JSON</button><button type="button" data-csv>Export fitted sample CSV</button></div>
 <details class="method-note"><summary>Sources, timing and interpretation</summary><p>Macro snapshot: ${esc(data.macro?.generated_at||'unavailable')}. Company snapshot: ${esc(data.index?.generated||'unavailable')}. Rates and USD use 13-week changes; unemployment uses the 13-week change in U-3. Positive USD means broad-dollar appreciation, not an individual bilateral exchange rate.</p><ul>${FACTORS.filter(x=>x[4]).map(([,,u,,id])=>`<li><a href="https://fred.stlouisfed.org/series/${id}" target="_blank" rel="noopener">${id}</a> · source observation through ${esc(data.macro?.series?.[id]?.last||'unavailable')}</li>`).join('')}</ul><p>Operating outcomes: revenue YoY growth, or quarterly profit/cash margin levels. Stock outcomes: non-overlapping calendar-quarter total return (dividends included) and split-adjusted price return (dividends excluded). Price return requires the separate price series; total returns are never substituted. Neither is a price target. Factor timing is relative to the outcome quarter. Peer factor: median of selected companies’ latest quarter ending on or before the factor date, no more than 120 days old; varying membership and fiscal dates affect comparability. Target company is excluded.</p><p>Financial history uses latest reported versions; a missing Q4 can be annual less three consecutive quarters. Macro data use approximate publication lags and current revised vintages. Peer alignment is by period end, not filing availability. This is retrospective explanatory analysis, NOT a point-in-time trading backtest or causal estimate. Chronological holdout, when shown, still uses revised data.</p><p>Ridge minimizes SSE + α × squared standardized slopes (unpenalized intercept); α is user-set or chosen among 1 / 10 / 100 using two expanding validation blocks, excluding the final test. Huber uses IRLS, epsilon 1.35 and MAD scale; its estimates are withheld if iteration fails to converge. ARX adds the previous observed outcome only across consecutive quarters; no future outcome enters a regressor. No coefficient intervals are provided for Ridge/Huber. OLS with intercept; minimum max(24, 5 × parameter count) complete quarters, standardized-factor conditioning check. Coefficient intervals use Newey–West covariance (4 quarterly lags) and a 1.96 normal approximation. The scenario interval covers coefficient uncertainty only, not future residuals, shock uncertainty or model uncertainty. Do not add operating and stock effects: the stock model is separate and may already reflect the operating channel. Banks and insurers require industry-specific interpretation of cash margins. Margin scenarios hold revenue fixed; revenue scenarios hold other outcomes unmodeled.</p><p class="shock-warning">${esc(status.length?status.join(' · '):'Data requests succeeded. Inspect each source date; snapshot generation does not imply fresh underlying observations.')}</p><p><a href="#c-${cik}-revisions">Company filing versions & evidence</a> · <a href="#c-${cik}-cash">Company quality & cash measures</a></p></details></section>`;
 const section=box.querySelector('.shock-panel');let peers=[],fits={},D,last={},seq=0,modelRows={},modelKeys=[],recommendation=null,dsCache=new Map(),peerCache=new Map();
 const get=k=>section.querySelector(k),all=k=>[...section.querySelectorAll(k)];
 const read=sel=>Object.fromEntries(all(sel).map(e=>[e.dataset.shock||e.dataset.beta,e.value.trim()===''?null:Number(e.value)]));
 function draw(){
  const key=get('[data-target]').value,units=unit(key),mode=get('[data-mode]').value,shocks=read('[data-shock]'),m=mode==='fit'?fits[key]||{error:'No fitted model'}:{beta:read('[data-beta]'),keys:FACTORS.map(x=>x[0])};
  get('[data-manual]').hidden=mode!=='manual';const r=impact(m,shocks),q=[...(D?.quarters||[])].reverse().find(x=>fin(x[key])),rows=projections(q,key,r.delta),f=v=>fin(v)?v.toFixed(2):'—';
  last={schema:3,recommendation,coverage:coverage(modelRows[key]||[],keysFor(key),get('[data-estimator]').value),extended_history:{generated_at:data.history?.generated_at,coverage:data.history?.coverage,source:urls.history},backfill:data.backfill,estimator:get('[data-estimator]').value,ridge_alpha:+get('[data-alpha]').value,window_quarters:+get('[data-window]').value,output_unit:units,company:{cik,ticker,currency:c.currency||'USD'},created_at:new Date().toISOString(),outcome:key,mode,lag_quarters:+get('[data-lag]').value,shocks,coefficient_units:FACTORS.map(([id,label,inputUnit,scale])=>({id,label,inputUnit,scale,outputUnit:units})),coefficients:m.beta||null,sample:{n:m.n,first:m.first,last:m.last},data_sources:{...urls,macro_generated:data.macro?.generated_at,company_generated:data.index?.generated,peers:peers.map(p=>p.profile?.cik)},reference_period:q?.end,result:r,limitations:'Descriptive association; revised vintages; no causal identification or point-in-time backtest; Stock returns are historical conditional changes, not price targets; stockPrice excludes dividends.'};
  const max=Math.max(1,...Object.values(r.contributions||{}).map(Math.abs));
  drawHealth(key,m);
  get('[data-history-chart]').innerHTML='<h3>Quarterly trend</h3>'+timePlot(m.rows||modelRows[key]||[],m.pred||[],units,m.pred?'Observed and fitted · in sample':'Actual quarterly history');
  get('[data-recommendation]').innerHTML=recommendationView(recommendation,units);
  get('[data-result]').innerHTML=`<h3>${esc(TARGETS[key])}</h3>${r.error?`<p class="shock-warning">${esc(r.error)}${m.error?' · Use reliable defaults or inspect coverage above. Historical observations remain available below.':''}</p>`:`<div class="shock-cards"><article><span>Conditional change vs reference</span><strong>${f(r.delta)} ${esc(units)}</strong><small>${mode==='manual'?'User assumptions':'Historical fitted association'}${key.startsWith('stock')?' · SPY shock '+shocks.market+'%':''}</small></article><article><span>Coefficient-only 95% interval</span><strong>${fin(r.band)?f(r.delta-r.band)+' to '+f(r.delta+r.band):'Not available'}</strong><small>Not a future-outcome prediction interval</small></article></div><div class="shock-bars">${FACTORS.filter(([k])=>r.contributions[k]!==0||m.keys?.includes(k)).map(([k,l])=>`<div><span>${esc(l)}</span><span class="shock-track"><i style="width:${Math.abs(r.contributions[k])/max*100}%;background:${r.contributions[k]<0?'#b65348':'#237e79'}"></i></span><b>${f(r.contributions[k])} ${esc(units)}</b></div>`).join('')}</div>${r.extrapolation?.length?'<p class="shock-warning">Shock magnitude exceeds observed factor levels: '+esc(r.extrapolation.join(', '))+'. Extrapolation can be unreliable.</p>':''}${rows.length?`<p>Illustrative reference: ${esc(q.end)} · actual reported quarter, not a next-quarter forecast. ${rows.map(([l,v,u])=>esc(l)+': <b>'+esc(!fin(v)?'Not meaningful':u?f(v)+' '+esc(u):l.includes('margin')?f(v)+'%':new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(v)+' '+(c.currency||'USD'))+'</b>').join(' · ')}</p>`:''}`}
  ${mode==='fit'&&!m.error?`<div class="shock-grid"><div><h4>Fitted sample · ${esc(MODEL_NAMES[get('[data-estimator]').value])}</h4><p>${m.n} quarters · ${m.first} → ${m.last}<br>R² ${f(m.r2)} · RMSE ${f(m.rmse)} ${esc(units)}</p>${m.holdout?`<p>Chronological holdout (${m.holdout.n} quarters): RMSE ${f(m.holdout.rmse)} vs training-mean baseline ${f(m.holdout.naive)} ${esc(units)}. Revised-vintage diagnostic only.</p>`:'<p>Not enough history for a separate holdout.</p>'}<div class="tbl-wrap"><table><thead><tr><th>Factor</th><th>Coefficient</th><th>Approx. 95% interval</th></tr></thead><tbody>${m.keys.map(k=>`<tr><td>${esc(FACTORS.find(x=>x[0]===k)?.[1]||(k==='ownLag'?'Own outcome · previous quarter':'SPY return control'))}</td><td>${f(m.beta[k])}</td><td>${f(m.beta[k]-1.96*m.se?.[k])} to ${f(m.beta[k]+1.96*m.se?.[k])}</td></tr>`).join('')}</tbody></table></div></div><div>${plot(m,units)}<p class="small">In-sample observed vs fitted. Hover a point for its date.</p></div></div>`:''}`;
  const comp=mode==='fit'&&modelKeys.length?compareModels(modelRows[key]||[],key.startsWith('stock')?[...new Set([...modelKeys,'market'])]:modelKeys,+get('[data-alpha]').value):[];
  last.model_comparison=comp;
  const path=mode==='fit'&&m.model==='arx'&&!r.error?responsePath(m,r.delta):null;
  const successful=comp.filter(x=>!x.error);
  get('[data-comparison]').innerHTML=(path?`<h3>ARX response to a one-quarter pulse</h3><p>${path.error?esc(path.error):path.points.map((v,i)=>'Q+'+(i+1)+': '+f(v)+' '+units).join(' · ')}</p><p class="muted small">Conditional point sensitivities, no causal identification or path interval.</p>`:'')+(comp.length?`<details><summary>Model comparison · same chronological sample</summary><p class="small">Same eligible rows and 75%/25% split for all estimators. Descriptive comparison only; the recommendation above uses its own separate validation and final test. ARX uses known prior outcomes for one-step testing.</p>${successful.length?`<div class="shock-scores">${comp.map(x=>`<article><b>${esc(MODEL_NAMES[x.model])}</b><span>${x.n} train / ${x.test_n} test</span><strong>${x.error?'Unavailable':f(x.rmse)+' '+esc(units)}</strong><small>${x.error?esc(x.error):'RMSE · mean baseline '+f(x.naive)+' · MAE '+f(x.mae)}</small></article>`).join('')}</div>`:'<p>Not enough complete training history for a comparable holdout. See the coverage timeline above; source observations are still plotted.</p>'}</details>`:'');

 }
 function keysFor(key){return key.startsWith('stock')?[...new Set([...modelKeys,'market'])]:modelKeys;}
 function drawHealth(key,m){
  const cv=coverage(modelRows[key]||[],keysFor(key),get('[data-estimator]').value),b=data.backfill,source=D.quarters,metric=source.filter(q=>fin(q[key])).length;
  const last=source.at(-1)?.end||'unavailable',stale=source.length&&Date.now()-source.at(-1).t>200*DAY;
  get('[data-health]').innerHTML=`<div class="shock-health"><article><span>Source quarters</span><strong>${key.startsWith('stock')?modelRows[key].length:metric}</strong><small>Latest company period ${esc(last)}</small></article><article><span>Complete for selected factors</span><strong>${cv.n} / ${cv.total}</strong><small>${cv.need} needed for ${esc(MODEL_NAMES[get('[data-estimator]').value])}${get('[data-estimator]').value==='arx'?' · AR lag may remove more rows':''}</small></article><article><span>History collection</span><strong>${b?b.processed+' / '+b.total:'Pending snapshot'}</strong><small>${b?b.pending+' companies pending · '+b.failed+' retries':'Existing statements remain usable'}</small></article></div>${stale?'<p class="shock-warning">The latest available company period is over 200 days old.</p>':''}<p class="small">${data.history?'Extended SEC history checked '+esc(data.history.generated_at):'Extended company history is not available yet.'}${b?' · Collector snapshot '+esc(b.generated_at):''}. Missing observations remain missing. Refresh retrieves the latest published batch.</p><details><summary>Data coverage · see missing factors and quarters</summary><div class="shock-coverage">${cv.factors.map(x=>`<div><span>${esc(x.label)}</span><meter value="${x.n}" min="0" max="${Math.max(1,cv.total)}"></meter><b>${x.n}/${cv.total}</b></div>`).join('')}</div><div class="shock-timeline" aria-label="Complete and missing quarterly observations">${cv.periods.map(p=>`<span class="${p.complete?'complete':'missing'}" title="${iso(p.t)} · ${p.complete?'complete':'selected factor missing'}" role="img" aria-label="${iso(p.t)} ${p.complete?'complete':'missing'}"></span>`).join('')}</div><p class="small">Teal: complete for selected factors · amber: one or more selected factors missing. Dates on hover. No interpolation, forward-fill or minimum-sample relaxation.</p></details>`;
 }
 function refit(){
  const lag=+get('[data-lag]').value;
  if(!dsCache.has(lag))dsCache.set(lag,dataset(c,data.macro,peers,data.stock,data.market,lag));
  D=dsCache.get(lag);modelKeys=all('[data-factor]:checked').map(e=>e.dataset.factor);
  const window=+get('[data-window]').value,options={model:get('[data-estimator]').value,alpha:+get('[data-alpha]').value},key=get('[data-target]').value;
  modelRows=Object.fromEntries(Object.keys(TARGETS).map(k=>[k,window?D.rows[k].slice(-window):D.rows[k]]));
  all('[data-target] option').forEach(o=>o.textContent=TARGETS[o.value]+' · '+D.rows[o.value].length+' observed quarters');
  fits={[key]:modelKeys.length?fit(modelRows[key],keysFor(key),options):{error:'Select at least one factor'}};draw();
 }
 function useDefaults(){
  get('[data-lag]').value='0';get('[data-window]').value='0';get('[data-mode]').value='fit';get('[data-estimator]').value='ols';get('[data-alpha]').value='10';recommendation=null;
  refit();const key=get('[data-target]').value,d=defaults(D.rows[key]||[],key.startsWith('stock'));
  all('[data-factor]').forEach(e=>e.checked=d.keys.includes(e.dataset.factor));
  all('[data-shock]').forEach(e=>e.value='0');
  if(!d.error){const k=d.keys.includes('rates')?'rates':d.keys[0],r=(D.rows[key]||[]).filter(r=>fin(r[k])),sd=Math.sqrt(mean(r.map(x=>(x[k]-mean(r.map(y=>y[k])))**2))),scale=FACTORS.find(x=>x[0]===k)?.[3]||1;get(`[data-shock="${k}"]`).value=k==='rates'?'100':(sd*scale).toFixed(2);}
  get('[data-default-note]').textContent=d.error||`Coverage default: ${d.keys.map(k=>FACTORS.find(x=>x[0]===k)?.[1]).join(', ')} · ${d.n} complete quarters · all history. Initial shock is an illustrative +100 bp rate move (or one historical standard deviation for the first available factor).`;
  refit();
 }
 async function loadPeers(){
  const ids=all('[data-peer]:checked').map(e=>e.dataset.peer);if(ids.length>5){get('[data-load]').textContent='Select at most 5 peers.';return;}
  const request=++seq;get('[data-load]').textContent='Loading peer statements…';
  const rs=await Promise.allSettled(ids.map(id=>{if(!peerCache.has(id))peerCache.set(id,(async()=>{const [base,extra]=await Promise.allSettled([json(site+'c/'+id+'.json'),supplemental(history,site+'shock-history/','c/'+id+'.json')]);if(base.status!=='fulfilled')throw base.reason;return {...base.value,shock_history:extra.status==='fulfilled'?extra.value:null};})().catch(e=>{peerCache.delete(id);throw e;}));return peerCache.get(id);}));
  if(!here()||request!==seq)return;peers=rs.filter(r=>r.status==='fulfilled').map(r=>r.value);dsCache.clear();recommendation=null;
  get('[data-load]').textContent=`${peers.length}/${ids.length} peer statements loaded. ${rs.some(r=>r.status==='rejected')?'Some requests failed; the fitted basket is smaller.':''}`;refit();
 }
 all('[data-shock],[data-beta]').forEach(e=>e.addEventListener('input',draw));
 get('[data-target]').addEventListener('change',()=>{all('[data-beta]').forEach(e=>e.value='');recommendation=null;refit();});get('[data-mode]').addEventListener('change',draw);
 all('[data-lag],[data-factor],[data-estimator],[data-alpha],[data-window]').forEach(e=>e.addEventListener('change',()=>{recommendation=null;get('[data-default-note]').textContent='Custom settings · use reliable defaults to restore a compact specification.';refit();}));get('[data-refit]').onclick=loadPeers;
 get('[data-defaults]').onclick=useDefaults;
 get('[data-recommend]').onclick=()=>{const key=get('[data-target]').value;recommendation=recommend(modelRows[key]||[],keysFor(key));if(recommendation.qualified){get('[data-estimator]').value=recommendation.chosen.model;get('[data-alpha]').value=recommendation.chosen.alpha||10;get('[data-mode]').value='fit';}refit();};
 get('[data-refresh]').onclick=()=>{const saved=all('input,select').filter(e=>Object.keys(e.dataset).length).map(e=>({attr:Object.keys(e.dataset)[0],key:Object.values(e.dataset)[0],value:e.value,checked:e.checked}));return mount(box,{company:c,cik,ticker,here,restore:saved});};
 all('[data-preset]').forEach(b=>b.onclick=()=>{const presets={tight:[100,5,0.5,-5],weak:[-100,-3,1,-10],zero:[0,0,0,0]},v=presets[b.dataset.preset];FACTORS.forEach(([k],i)=>get(`[data-shock="${k}"]`).value=v[i]??0);draw();});
 get('[data-export]').onclick=()=>{drawVal();download(`shock-${cik}.json`,JSON.stringify(last,null,2),'application/json');};
 get('[data-csv]').onclick=()=>{const m=fits[get('[data-target]').value];if(!m?.rows){get('[data-load]').textContent='No complete fitted sample to export.';return;}download(`shock-${cik}-sample.csv`,csv([['period_end','observed','fitted',...m.keys],...m.rows.map((r,i)=>[iso(r.t),r.y,m.pred[i],...m.keys.map(k=>r[k])])]),'text/csv');};
 const vbox=get('[data-valuation]');
 vbox.innerHTML=`<details><summary>Valuation assumption lab · separate from regression</summary><p>No company valuation inputs are inferred. Fill in your own consistent annual EPS or next-year FCFF assumptions. Macro beta and valuation effects are not added together.</p><div class="shock-controls">${[['eps','Annual EPS'],['pe','P/E multiple'],['epsPct','EPS change (%)'],['pePct','P/E change (%)'],['fcf','Next-year FCFF (currency units)'],['wacc','WACC (%)'],['g','Perpetual growth (%)'],['waccBP','WACC change (bp)'],['gBP','Growth change (bp)'],['fcfPct','FCFF change (%)']].map(([k,l])=>`<label>${l}<input type="number" data-val="${k}" step="any" value="${k.endsWith('Pct')||k.endsWith('BP')?'0':''}"></label>`).join('')}</div><div data-val-result aria-live="polite"></div><p class="small">P = annual EPS × P/E. EV = next-year FCFF / (WACC − g), a one-stage perpetuity, not a complete DCF. EV is before net debt and other claims; not equity value or a price target. Positive earnings/cash flow and WACC > g are required.</p></details>`;
 function drawVal(){const v=Object.fromEntries(all('[data-val]').map(e=>[e.dataset.val,e.value.trim()===''?null:Number(e.value)])),r=valuation(v);last.valuation={assumptions:v,result:r};get('[data-val-result]').innerHTML=Object.entries(r).map(([k,x])=>`<p>${k==='pe'?'EPS × P/E implied price':'Perpetuity enterprise value'}: ${x.error?esc(x.error):'reference '+x.base.toFixed(2)+' → scenario '+x.scenario.toFixed(2)+' ('+x.change.toFixed(2)+'%)'}</p>`).join('');}
 all('[data-val]').forEach(e=>e.addEventListener('input',drawVal));
 if(restore){for(const x of restore){const attr='data-'+x.attr.replace(/[A-Z]/g,l=>'-'+l.toLowerCase()),e=all('['+attr+']').find(e=>e.getAttribute(attr)===x.key);if(e){if(e.type==='checkbox')e.checked=x.checked;else e.value=x.value;}}get('[data-default-note]').textContent='Data refreshed; your inputs and model settings are preserved.';refit();}else useDefaults();
 await loadPeers();drawVal();
}
const api={FACTORS,TARGETS,unit,coverage,defaults,recommend,timePlot,penalized,lagged,compareModels,responsePath,valuation,financials,metrics,weekly,prices,change,dataset,ols,fit,impact,projections,csv,mount};root.FFShock=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?{}:window);
