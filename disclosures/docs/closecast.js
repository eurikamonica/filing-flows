/* Close forecast — the hub tab: where an asset closes today, on each options expiry this week, at the end of the week,
   in two weeks, at the end of the month and of the quarter. Each date is a distribution pooled from the options, the
   prediction markets, the volatility indices, the asset's own history (analogs) and a simulation, each source first
   scaled so that its ranges held as often as they claim on its own record (app/closecast.py). The confidence slider
   picks the range shown; Freeze keeps the forecast as it is now (in this browser) to set against the live one and, once
   the date has closed, against the close. The site also freezes every forecast at 9:45, 12:00 and 15:00 New York and
   scores it (the record).
   Data: forecast.json and closes.json on the branch forecast-live (every five minutes through the session, by the
   intraday relay; once after the close), public/record.json on the branch forecast-ledger — read from
   raw.githubusercontent.com, the forecast again every minute while the tab shows.
   Deep links: #forecast, #forecast/SPY, #forecast/NVDA. */
(function(){
const CF_LIVE='https://raw.githubusercontent.com/eurikamonica/filing-flows/forecast-live/';
const CF_LEDGER='https://raw.githubusercontent.com/eurikamonica/filing-flows/forecast-ledger/public/record.json';
const CF_KEY='ff-closecast-freezes';
const cfStore={};
let cfMem=[];
const CF_TAG={first:'',expiry:'options expiry',week:'week end','2w':'two weeks',month:'month end',quarter:'quarter end'};
const CF_SRC=[
 ['options','Options','CBOE delayed quotes: P(close above each strike) from the expiry\'s smile'],
 ['markets','Prediction markets','Kalshi and Polymarket ladders on that day\'s close'],
 ['implied','Volatility indices','VIX1D, VIX9D, VIX, VIX3M, VIX6M (VXN, VXD): a log-normal'],
 ['analogs','History: analogs','the days most like now, and how they went on'],
 ['moves','History: Move odds','after days whose move was as rare as the last one'],
 ['regime','History: highs, lows & ranges','the 250 days most like it in the regime it is in now'],
 ['sim','History: simulation','4,000 paths of past returns at today\'s volatility']];
const CF_COL={options:'var(--cf-opt)',markets:'var(--cf-mkt)',implied:'var(--cf-imp)',analogs:'var(--cf-ana)',moves:'var(--cf-mov)',regime:'var(--cf-reg)',sim:'var(--cf-sim)'};

/* numbers */
function cfInvN(p){                       // the standard normal quantile (Acklam)
 const a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.357751867269,-30.66479806614716,2.506628277459239],
  b=[-54.47609879822406,161.5858368580409,-155.6989798598866,66.80131188771972,-13.28068155288572],
  c=[-0.007784894002430293,-0.3223964580411365,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783],
  d=[0.007784695709041462,0.3224671290700398,2.445134137142996,3.754408661907416];
 if(p<=0)return -8;if(p>=1)return 8;
 const pl=0.02425;let q,r;
 if(p<pl){q=Math.sqrt(-2*Math.log(p));return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)}
 if(p>1-pl){q=Math.sqrt(-2*Math.log(1-p));return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)}
 q=p-0.5;r=q*q;return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);
}
function cfN(x){                          // the standard normal cdf
 const t=1/(1+0.2316419*Math.abs(x)),y=t*(0.319381530+t*(-0.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));
 const p=1-Math.exp(-x*x/2)/Math.sqrt(2*Math.PI)*y;return x>=0?p:1-p;
}
function cfLin(x,xs,ys){
 if(x<=xs[0])return ys[0];if(x>=xs[xs.length-1])return ys[ys.length-1];
 let i=1;while(xs[i]<x)i++;const w=(x-xs[i-1])/((xs[i]-xs[i-1])||1);return ys[i-1]+w*(ys[i]-ys[i-1]);
}
const cfZ=pg=>pg.map(cfInvN);
function cfQ(q,p,zg){return cfLin(cfInvN(p),zg,q)}                          // a quantile of log returns
function cfCdf(q,y,zg){                                                     // P(X ≤ y)
 if(y<=q[0])return cfN(zg[0]-0.5*(q[0]-y>0?1:0));if(y>=q[q.length-1])return cfN(zg[zg.length-1]+0.5);
 return cfN(cfLin(y,q,zg));
}
function cfRange(q,c,zg){return [cfQ(q,(1-c)/2,zg),cfQ(q,0.5,zg),cfQ(q,(1+c)/2,zg)]}
/* the expected value of exp(X), X a log return given by its quantiles q at the normal scores zg: straight between them,
   beyond the ends along the last step (a normal's tail); summed over z from −6 to 6 in steps of 0.01. ×start = the
   expected close — the probability-weighted average, not the median: below it when the fall tail is the heavier, above
   it when the spread is wide (a price can rise further than it can fall) */
function cfMean(q,zg){
 const n=zg.length;if(!q||q.length!==n||n<2)return null;
 const s0=(q[1]-q[0])/((zg[1]-zg[0])||1),s1=(q[n-1]-q[n-2])/((zg[n-1]-zg[n-2])||1);
 let s=0,w=0,i=1;
 for(let k=-600;k<=600;k++){
  const z=k/100;let x;
  if(z<=zg[0])x=q[0]+(z-zg[0])*s0;else if(z>=zg[n-1])x=q[n-1]+(z-zg[n-1])*s1;
  else{while(zg[i]<z)i++;const f=(z-zg[i-1])/((zg[i]-zg[i-1])||1);x=q[i-1]+f*(q[i]-q[i-1])}
  const p=Math.exp(-z*z/2);s+=p*Math.exp(x);w+=p}
 return s/w}
/* the high and the low from now to a date's close (log returns from the start): its median and its range at c */
function cfHL(t,c,zg){const h=t.hilo||{};return {hi:h.high?cfRange(h.high,c,zg):null,lo:h.low?cfRange(h.low,c,zg):null,so:h.so_far||null,how:h.method}}
/* P(the price trades at x — at or above it when x is above now, at or below when under — before the date's close) */
function cfTouch(t,x,s0,zg){
 const h=t.hilo||{},y=Math.log(x/s0);
 if(h.so_far&&((y>=0&&h.so_far[0]>=y)||(y<0&&h.so_far[1]<=y)))return {p:1,done:true};
 if(y>=0)return h.high?{p:1-cfCdf(h.high,y,zg)}:null;
 return h.low?{p:cfCdf(h.low,y,zg)}:null;
}
const cfSign=(v,d=2)=>v==null||!Number.isFinite(v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)+'%';
/* the last close: yesterday's while the session trades, else the price (today's close, or the last session's) */
const cfLast=(d,a)=>a.last_close??((a.phase||d.phase)==='open'?a.prev:a.price);
const cfPc=(v,d=0)=>v==null||!Number.isFinite(v)?'—':(v<0.005&&v>0?'<1%':v>0.995&&v<1?'>99%':fmt(v*100,d)+'%');

/* data */
function cfFetch(name,url,every){
 const m=cfStore[name]||(cfStore[name]={});
 const due=!m.at||Date.now()-m.at>every;
 if(m.loading||(!due&&(m.data||m.err)))return m;
 if(typeof fetch!=='function'){m.err='this browser cannot load data files';return m}
 m.loading=fetch(url+(url.includes('?')?'&':'?')+'t='+Math.floor(Date.now()/30000),{cache:'no-cache'})
  .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
  .then(d=>{const changed=!m.data||JSON.stringify(m.data.generated_at)!==JSON.stringify(d.generated_at);m.data=d;m.err=null;m.at=Date.now();m.loading=null;if(changed)cfRefresh()})
  .catch(e=>{m.err=m.data?null:e.message;m.at=Date.now();m.loading=null;cfRefresh()});
 return m;
}
const cfData=()=>cfFetch('fc',CF_LIVE+'forecast.json',60000);
const cfCloses=()=>cfFetch('closes',CF_LIVE+'closes.json',300000);
const cfRecord=()=>cfFetch('record',CF_LEDGER,600000);
function cfRefresh(){
 if(state.tab!=='forecast'||typeof document==='undefined')return;
 const body=$('cf-body');
 const a=document.activeElement;
 if(body&&!(a&&body.contains(a)&&/INPUT|SELECT|TEXTAREA/.test(a.tagName))){cfPaint();return}
 if(!body&&typeof render==='function')render();
}

/* freezes of your own: in your account (Supabase forecast_freezes — every device you sign in on has them) when this
   browser holds a session of the site's sign-in (Alerts, e-mail only; the same origin), else in this browser */
const CF_ACCT={state:'unknown',client:null,user:null,rows:null,err:null};      // unknown | none | loading | on | off
const CF_JS=['cdn.jsdelivr.net/npm','fastly.jsdelivr.net/npm','unpkg.com'].map(h=>`https://${h}/@supabase/supabase-js@2.58.0/dist/umd/supabase.js`);
/* the site's sign-in as kept in this browser ('' when signed out): a change (signed in on #account, signed out, the token
   renewed) reads the account again; a check is never repeated for the same sign-in */
function cfSig(){try{for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i)||'';if(/^sb-.+-auth-token$/.test(k))return k+'='+(localStorage.getItem(k)||'')}}catch(e){}return ''}
const cfTimed=(u,o={})=>{const ab=new AbortController(),t=setTimeout(()=>ab.abort(),20000);
 if(o.signal){if(o.signal.aborted)ab.abort();else o.signal.addEventListener('abort',()=>ab.abort(),{once:true})}
 return fetch(u,Object.assign({},o,{signal:ab.signal})).finally(()=>clearTimeout(t))};
function cfLoadJs(src){return new Promise((res,rej)=>{const el=document.createElement('script');const t=setTimeout(()=>{el.remove();rej(Error('timeout'))},6000);
 el.src=src;el.onload=()=>{clearTimeout(t);res()};el.onerror=()=>{clearTimeout(t);el.remove();rej(Error('blocked'))};document.head.appendChild(el)})}
const cfDbErr=e=>/relation|does not exist|schema cache|column|policy/i.test((e&&e.message)||'')?'the site owner has to update the database first (run supabase/schema.sql again)':((e&&e.message)||'the account could not be reached');
function cfAccount(){
 const fake=typeof window!=='undefined'&&window.FF_SUPABASE;                  // injected by tests
 if(!fake&&CF_ACCT.state!=='unknown'&&CF_ACCT.state!=='loading'&&cfSig()!==CF_ACCT.sig)Object.assign(CF_ACCT,{state:'unknown',client:null,user:null,rows:null,err:null});
 if(CF_ACCT.state!=='unknown')return CF_ACCT;
 CF_ACCT.sig=fake?'':cfSig();
 if(!fake&&(!CF_ACCT.sig||typeof fetch!=='function')){CF_ACCT.state='none';return CF_ACCT}
 CF_ACCT.state='loading';
 CF_ACCT.ready=(async()=>{
  try{
   let c=fake||(typeof XPOST!=='undefined'&&XPOST.client)||(typeof window!=='undefined'&&window.FF_HUB_SUPA)||null;
   if(!c){
    const site=await cfTimed((globalThis.FF_SITE_ROOT??'../')+'data/site.json').then(r=>r.ok?r.json():{});
    if(!site.supabase_url||!site.supabase_key)throw Error('no sign-in on this site');
    for(const src of CF_JS){if(window.supabase&&window.supabase.createClient)break;await cfLoadJs(src).catch(()=>{})}
    const lib=window.supabase;if(!lib||!lib.createClient)throw Error('the sign-in library did not load');
    c=window.FF_HUB_SUPA=lib.createClient(site.supabase_url,site.supabase_key,{auth:lib.processLock?{lock:lib.processLock}:{},global:{fetch:cfTimed}});
   }
   const s=await c.auth.getSession(),user=s&&s.data&&s.data.session&&s.data.session.user;
   if(!user){CF_ACCT.state='none';return}
   CF_ACCT.client=c;CF_ACCT.user=user;
   const r=await c.from('forecast_freezes').select('id,asset,frozen_at,payload').order('created_at',{ascending:false}).limit(500);
   if(r.error){CF_ACCT.state='off';CF_ACCT.err=cfDbErr(r.error);return}
   CF_ACCT.rows=(r.data||[]).map(x=>Object.assign({},x.payload||{},{id:'a'+x.id,dbid:x.id,at:x.frozen_at,asset:x.asset,where:'account'}));
   CF_ACCT.state='on';
  }catch(e){CF_ACCT.state='off';CF_ACCT.err=e.message||String(e)}
  finally{cfRefresh()}
 })();
 return CF_ACCT;
}
function cfMine(){try{const v=JSON.parse(localStorage.getItem(CF_KEY)||'[]');return Array.isArray(v)?v:[]}catch(e){return cfMem}}
function cfKeep(list){list=list.slice(-120);try{localStorage.setItem(CF_KEY,JSON.stringify(list))}catch(e){cfMem=list}}
/* every freeze of yours, the account's and this browser's, newest first */
function cfAll(){
 const acc=CF_ACCT.state==='on'?(CF_ACCT.rows||[]):[];
 return acc.concat(cfMine().map(f=>Object.assign({where:'browser'},f))).sort((x,y)=>String(y.at).localeCompare(String(x.at)));
}
const cfShape=(d,a)=>({at:d.generated_at,asset:a.key,start:a.start,prev:a.prev,price:a.price,pgrid:d.pgrid,targets:a.targets.map(t=>({date:t.date,tags:t.tags,q:t.q}))});
function cfKeepHere(f){const list=cfMine(),row=Object.assign({id:'u'+Date.now()+Math.floor(Math.random()*1000),saved:new Date().toISOString()},f);list.push(row);cfKeep(list);return row.id}
async function cfToAccount(f){
 const {at,asset,...payload}=f;delete payload.id;delete payload.saved;delete payload.where;
 let r;try{r=await CF_ACCT.client.from('forecast_freezes').insert({asset,frozen_at:at,payload}).select('id').single()}catch(e){r={error:e}}
 if(r.error||!r.data)return {why:cfDbErr(r.error)};
 const row=Object.assign({},payload,{id:'a'+r.data.id,dbid:r.data.id,at,asset,where:'account'});
 CF_ACCT.rows=[row].concat(CF_ACCT.rows||[]);return {id:row.id};
}
/* freeze the forecast now: into the account when signed in (else, or when that fails, this browser) — {id, where, why} */
async function cfFreezeNow(d,a){
 const f=cfShape(d,a);
 if(CF_ACCT.state==='on'){const r=await cfToAccount(f);if(r.id)return {id:r.id,where:'account'};return {id:cfKeepHere(f),where:'browser',why:r.why}}
 return {id:cfKeepHere(f),where:'browser'};
}
async function cfDrop(id){
 if(id.startsWith('a')&&CF_ACCT.state==='on'){
  const f=(CF_ACCT.rows||[]).find(x=>x.id===id);if(!f)return;
  let r;try{r=await CF_ACCT.client.from('forecast_freezes').delete().eq('id',f.dbid)}catch(e){r={error:e}}
  if(r.error){cfStore.flash='The freeze could not be deleted: '+cfDbErr(r.error);return}
  CF_ACCT.rows=CF_ACCT.rows.filter(x=>x.id!==id);return;
 }
 cfKeep(cfMine().filter(f=>f.id!==id));
}
/* this browser's freezes into the account (each kept here until the account has it) */
async function cfMoveHere(){
 let moved=0,why='';
 for(const f of cfMine()){const r=await cfToAccount(f);if(r.id){moved++;cfKeep(cfMine().filter(x=>x.id!==f.id))}else{why=r.why;break}}
 return {moved,why};
}
/* the comparison: one of your freezes or an official one, as {label, at, targets: [{date, px: price quantiles}]} */
function cfFrozen(key,d){
 const id=state.cfcmp||'';if(!id)return null;
 if(id.startsWith('u')||id.startsWith('a')){
  const f=cfAll().find(x=>x.id===id&&x.asset===key);if(!f||!f.targets)return null;
  return {label:'Your freeze',at:f.at,start:f.start,targets:f.targets.map(t=>({date:t.date,tags:t.tags,px:t.q.map(v=>f.start*Math.exp(v))})),pgrid:f.pgrid||d.pgrid};
 }
 const r=cfRecord().data;if(!r)return null;
 const f=(r.latest||[]).find(x=>'o'+x.slot===id);const a=f&&f.assets&&f.assets[key];if(!a)return null;
 return {label:'Official freeze',at:f.at,start:a.start,targets:a.targets.map(t=>({date:t.date,tags:t.tags,px:t.q})),pgrid:f.pgrid||r.pgrid||d.pgrid};
}

/* labels */
function cfDay(iso){const d=new Date(iso+'T12:00:00Z');return d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',timeZone:'UTC'})}
function cfTargetLabel(t,d){
 const tags=t.tags.filter(x=>x!=='first').map(x=>CF_TAG[x]).filter(Boolean);
 const first=t.tags.includes('first');
 const name=first?(d.phase==='closed'?'Next close':'Today\'s close'):cfDay(t.date);
 return {name:first?`${name} · ${cfDay(t.date)}`:name,tags:tags.join(' · ')};
}
function cfTime(iso){if(!iso)return '—';const d=new Date(iso);return d.toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' ET'}
function cfAgo(iso){const m=(Date.now()-Date.parse(iso))/60000;return m<1?'just now':m<90?fmt(m)+' min ago':m<48*60?fmt(m/60,1)+' h ago':fmt(m/1440,1)+' days ago'}
function cfUnits(a){const ix=a.index&&a.index.ratio&&state.cfu==='index';return {k:ix?1/a.index.ratio:1,label:ix?a.index.name+' points':a.key,dec:ix?(a.index.price>5000?0:1):2}}
const cfPx=(v,u)=>v==null||!Number.isFinite(v)?'—':fmt(v*u.k,u.dec);
function cfWidth(){const el=$('cf-body')||$('workspace');const w=el&&el.clientWidth?el.clientWidth:((window.innerWidth||800)-32);return Math.max(300,Math.min(1120,w))}   // charts drawn at their real width: 11px text stays 11px

/* charts */
function cfTodayChart(a,t,d,c,fz,u,W){
 const nar=W<520,zg=cfZ(d.pgrid),H=nar?210:250,L=nar?44:52,R=nar?62:86,T=12,B=26;
 const open=d.phase==='open';
 const path=open?(a.path||[]).filter(p=>p[1]>0):[];                         // after the close the cone is the next session's
 const nowX=open&&path.length?path[path.length-1][0]:0;
 const s0=a.start||a.price;
 const lo=s0*Math.exp(cfQ(t.q,(1-c)/2,zg)),hi=s0*Math.exp(cfQ(t.q,(1+c)/2,zg));
 const fr=fz&&fz.targets.find(x=>x.date===t.date);
 const fzr=fr?[cfLin(cfInvN((1-c)/2),cfZ(fz.pgrid),fr.px),cfLin(cfInvN(0.5),cfZ(fz.pgrid),fr.px),cfLin(cfInvN((1+c)/2),cfZ(fz.pgrid),fr.px)]:null;
 const em=cfMean(t.q,zg),ev=em!=null?s0*em:null;
 const ys=[lo,hi,s0,...path.map(p=>p[1])].concat(ev!=null?[ev]:[]).concat(a.prev?[a.prev]:[]).concat(fzr||[]);
 let y0=Math.min(...ys),y1=Math.max(...ys);const pad=(y1-y0)*0.08||s0*0.002;y0-=pad;y1+=pad;
 const X=m=>L+m/390*(W-L-R),Y=v=>T+(1-(v-y0)/(y1-y0))*(H-T-B);
 let s=`<svg viewBox="0 0 ${W} ${H}" class="cf-svg" role="img" aria-label="Today's path and the forecast of the close">`;
 for(let i=0;i<=4;i++){const v=y0+(y1-y0)*i/4;s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" class="cf-grid"/><text x="${L-6}" y="${Y(v)+3}" text-anchor="end" class="cf-ax">${cfPx(v,u)}</text>`}
 (nar?[['9:30',0],['12:30',180],['4:00',390]]:[['9:30',0],['11:00',90],['12:30',180],['2:00',270],['4:00',390]]).forEach(([l,m])=>{s+=`<text x="${X(m)}" y="${H-8}" text-anchor="middle" class="cf-ax">${l}</text>`});
 if(a.prev)s+=`<line x1="${L}" x2="${W-R}" y1="${Y(a.prev)}" y2="${Y(a.prev)}" class="cf-prev"/><text x="${W-R+4}" y="${Y(a.prev)+3}" class="cf-ax">${nar?'':'prev '}${cfPx(a.prev,u)}</text>`;
 // the cone from now to 4 pm: the pooled quantiles at the close, spread growing with √time
 const steps=24,band=(cc)=>{const up=[],dn=[];for(let i=0;i<=steps;i++){const m=nowX+(390-nowX)*i/steps,f=Math.sqrt(i/steps);
   up.push(`${X(m).toFixed(1)},${Y(s0*Math.exp(f*cfQ(t.q,(1+cc)/2,zg)+ (1-f)*0)).toFixed(1)}`);dn.push(`${X(m).toFixed(1)},${Y(s0*Math.exp(f*cfQ(t.q,(1-cc)/2,zg))).toFixed(1)}`)}
  return up.concat(dn.reverse()).join(' ')};
 s+=`<polygon points="${band(c)}" class="cf-band-o"/><polygon points="${band(Math.min(0.5,c))}" class="cf-band-i"/>`;
 s+=`<line x1="${X(nowX)}" x2="${X(390)}" y1="${Y(s0)}" y2="${Y(s0*Math.exp(cfQ(t.q,0.5,zg)))}" class="cf-med"/>`;
 if(ev!=null){const ex=X(390),ey=Y(ev);s+=`<line x1="${X(nowX)}" x2="${ex}" y1="${Y(s0)}" y2="${ey}" class="cf-evl"/><path d="M${ex.toFixed(1)},${(ey-5).toFixed(1)}l5,5l-5,5l-5,-5z" class="cf-evd"/>`}
 if(fzr){const fx=X(390)+10;s+=`<line x1="${fx}" x2="${fx}" y1="${Y(fzr[0])}" y2="${Y(fzr[2])}" class="cf-fz"/><circle cx="${fx}" cy="${Y(fzr[1])}" r="3.5" class="cf-fzdot"/>${nar?'':`<text x="${fx+6}" y="${Y(fzr[1])+3}" class="cf-ax">frozen</text>`}`}
 if(path.length>1)s+=`<path d="${path.map((p,i)=>(i?'L':'M')+X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}" class="cf-path"/>`;
 if(open&&path.length)s+=`<circle cx="${X(nowX)}" cy="${Y(path[path.length-1][1])}" r="3.5" class="cf-now"/>`;
 s+=`<text x="${W-R+4}" y="${Y(hi)+3}" class="cf-ax">${nar?'':fmt(c*100)+'% '}${cfPx(hi,u)}</text><text x="${W-R+4}" y="${Y(lo)+3}" class="cf-ax">${cfPx(lo,u)}</text>`;
 return s+'</svg>';
}
function cfHorizonChart(a,d,c,fz,u,sel,W){
 const zg=cfZ(d.pgrid),nar=W/Math.max(1,a.targets.length)<90,H=nar?230:270,L=nar?44:52,R=nar?8:20,T=14,B=46,ts=a.targets,n=ts.length;if(!n)return '';
 const s0=a.start||a.price,rows=ts.map(t=>{const r=cfRange(t.q,c,zg),i50=cfRange(t.q,0.5,zg),m=cfMean(t.q,zg);return {t,lo:s0*Math.exp(r[0]),md:s0*Math.exp(r[1]),hi:s0*Math.exp(r[2]),l5:s0*Math.exp(i50[0]),h5:s0*Math.exp(i50[2]),ev:m!=null?s0*m:null}});
 const fzz=fz?ts.map(t=>{const f=fz.targets.find(x=>x.date===t.date);if(!f)return null;const zf=cfZ(fz.pgrid);return [cfLin(cfInvN((1-c)/2),zf,f.px),cfLin(0,zf,f.px),cfLin(cfInvN((1+c)/2),zf,f.px)]}):[];
 const ys=rows.flatMap(r=>[r.lo,r.hi]).concat([s0]).concat(rows.map(r=>r.ev).filter(v=>v!=null)).concat(fzz.filter(Boolean).flat());
 let y0=Math.min(...ys),y1=Math.max(...ys);const pad=(y1-y0)*0.06;y0-=pad;y1+=pad;
 const X=i=>L+(i+0.5)/n*(W-L-R),Y=v=>T+(1-(v-y0)/(y1-y0))*(H-T-B),bw=Math.min(46,(W-L-R)/n*0.42);
 let s=`<svg viewBox="0 0 ${W} ${H}" class="cf-svg" role="img" aria-label="The range forecast for each date">`;
 for(let i=0;i<=4;i++){const v=y0+(y1-y0)*i/4;s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" class="cf-grid"/><text x="${L-6}" y="${Y(v)+3}" text-anchor="end" class="cf-ax">${cfPx(v,u)}</text>`}
 s+=`<line x1="${L}" x2="${W-R}" y1="${Y(s0)}" y2="${Y(s0)}" class="cf-prev"/>`;
 const up=rows.map((r,i)=>`${X(i)},${Y(r.hi)}`),dn=rows.map((r,i)=>`${X(i)},${Y(r.lo)}`).reverse();
 if(n>1)s+=`<polygon points="${[`${L},${Y(s0)}`].concat(up).concat(dn).join(' ')}" class="cf-band-soft"/>`;
 rows.forEach((r,i)=>{
  const x=X(i),on=r.t.date===sel;
  s+=`<g class="cf-hbar${on?' on':''}" data-cft="${r.t.date}" tabindex="0" role="button" aria-label="${esc(cfTargetLabel(r.t,d).name)}"><rect x="${x-bw/2}" y="${T}" width="${bw}" height="${H-T-B}" class="cf-hit"/>`
   +`<line x1="${x}" x2="${x}" y1="${Y(r.hi)}" y2="${Y(r.lo)}" class="cf-whisk"/><rect x="${x-bw/4}" y="${Y(r.h5)}" width="${bw/2}" height="${Math.max(1,Y(r.l5)-Y(r.h5))}" class="cf-box"/>`
   +`<line x1="${x-bw/3}" x2="${x+bw/3}" y1="${Y(r.md)}" y2="${Y(r.md)}" class="cf-medl"/>`;
  const f=fzz[i];if(f)s+=`<line x1="${x+bw/2-2}" x2="${x+bw/2-2}" y1="${Y(f[2])}" y2="${Y(f[0])}" class="cf-fz"/><circle cx="${x+bw/2-2}" cy="${Y(f[1])}" r="3" class="cf-fzdot"/>`;
  const lab=cfTargetLabel(r.t,d),short={week:'wk',['2w']:'2w',month:'mo',quarter:'qtr',expiry:'exp'};
  const top=r.t.tags.includes('first')?(d.phase==='closed'?'next':'today'):nar?r.t.date.slice(5).replace('-','/'):cfDay(r.t.date).replace(/^\w+, /,'');
  const sub=nar?r.t.tags.filter(x=>x!=='first').map(x=>short[x]||x).join('·'):lab.tags.replace('options expiry','expiry');
  s+=`<text x="${x}" y="${H-B+14}" text-anchor="middle" class="cf-ax">${esc(top)}</text><text x="${x}" y="${H-B+27}" text-anchor="middle" class="cf-ax cf-ax2">${esc(sub)}</text></g>`;
 });
 const ev=rows.map((r,i)=>r.ev!=null?[X(i),Y(r.ev)]:null).filter(Boolean);
 if(ev.length){s+=`<polyline points="${[[L,Y(s0)]].concat(ev).map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}" class="cf-evl"/>`;
  ev.forEach(([x,y])=>{s+=`<path d="M${x.toFixed(1)},${(y-5).toFixed(1)}l5,5l-5,5l-5,-5z" class="cf-evd"/>`})}
 return s+'</svg>';
}
function cfSrcChart(t,a,d,c,u,Wa){
 const zg=cfZ(d.pgrid),s0=a.start||a.price,list=CF_SRC.filter(([k])=>t.src[k]&&t.src[k].q).map(([k,l])=>[k,l,t.src[k]]);
 const all=[['pool','Pooled',{q:t.q,w:1}]].concat(list);
 const rs=all.map(([k,l,s])=>{const r=cfRange(s.q,c,zg);return {k,l,s,lo:s0*Math.exp(r[0]),md:s0*Math.exp(r[1]),hi:s0*Math.exp(r[2])}});
 const xs=rs.flatMap(r=>[r.lo,r.hi]).concat([s0]);let x0=Math.min(...xs),x1=Math.max(...xs);const pd=(x1-x0)*0.05;x0-=pd;x1+=pd;
 const W=Math.min(Wa,960),nar=W<560,rowH=nar?42:30,L=nar?10:205,R=nar?10:130,H=rs.length*rowH+30,X=v=>L+(v-x0)/(x1-x0)*(W-L-R);
 let s=`<svg viewBox="0 0 ${W} ${H}" class="cf-svg" style="max-width:${W}px" role="img" aria-label="Each source's range and the pooled range">`;
 s+=`<line x1="${X(s0)}" x2="${X(s0)}" y1="4" y2="${H-22}" class="cf-prev"/><text x="${X(s0)}" y="${H-8}" text-anchor="middle" class="cf-ax">now ${cfPx(s0,u)}</text>`;
 rs.forEach((r,i)=>{const y=(nar?26:14)+i*rowH,col=r.k==='pool'?'var(--ink)':CF_COL[r.k];
  s+=nar?`<text x="${L}" y="${y-9}" class="cf-lab${r.k==='pool'?' b':''}">${esc(r.l)}</text><text x="${W-R}" y="${y-9}" text-anchor="end" class="cf-ax">${cfPx(r.lo,u)} – ${cfPx(r.hi,u)}</text>`
          :`<text x="${L-8}" y="${y+4}" text-anchor="end" class="cf-lab${r.k==='pool'?' b':''}">${esc(r.l)}</text><text x="${W-R+8}" y="${y+4}" class="cf-ax">${cfPx(r.lo,u)} – ${cfPx(r.hi,u)}</text>`;
  s+=`<line x1="${X(r.lo)}" x2="${X(r.hi)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="${r.k==='pool'?5:4}" stroke-linecap="round" opacity="${r.k==='pool'?0.9:0.75}"/>`
   +`<circle cx="${X(r.md)}" cy="${y}" r="4" fill="var(--surface)" stroke="${col}" stroke-width="2"/>`});
 return s+'</svg>';
}

/* the page */
function cfCss(){
 if(document.getElementById('cf-css'))return;
 const st=document.createElement('style');st.id='cf-css';
 st.textContent=`
:root{--cf-opt:#5b7fa6;--cf-mkt:#b07a1f;--cf-imp:#8a6fb0;--cf-ana:#17734a;--cf-mov:#b8577a;--cf-reg:#6f7d2a;--cf-sim:#3f8f9a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--cf-opt:#8fb0d6;--cf-mkt:#e0b060;--cf-imp:#b9a2dc;--cf-ana:#5fb88a;--cf-mov:#e594b2;--cf-reg:#bccb6e;--cf-sim:#7cc3cf}}
:root[data-theme="dark"]{--cf-opt:#8fb0d6;--cf-mkt:#e0b060;--cf-imp:#b9a2dc;--cf-ana:#5fb88a;--cf-mov:#e594b2;--cf-reg:#bccb6e;--cf-sim:#7cc3cf}
.cf-tools{display:flex;flex-wrap:wrap;gap:12px 18px;align-items:flex-end;margin:6px 0 14px}
.cf-tools .field{min-width:150px}
.cf-conf{display:flex;flex-direction:column;gap:4px;min-width:220px;flex:1 1 220px;max-width:360px}
.cf-conf label{font-size:.78rem;color:var(--muted)}
.cf-conf input[type=range]{width:100%;accent-color:var(--slate)}
.cf-conf b{font-variant-numeric:tabular-nums}
.cf-btn{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer}
.cf-btn:hover{border-color:var(--slate)}
.cf-btn.pri{background:var(--slate);border-color:var(--slate);color:#fff}
.cf-x{width:120px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);font:inherit}
.cf-hero{display:grid;grid-template-columns:minmax(220px,300px) 1fr;gap:16px;align-items:start;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.cf-hero h3{margin:0 0 4px;font-size:1rem}
.cf-big{font-size:1.9rem;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.15}
.cf-rng{font-size:1.05rem;font-variant-numeric:tabular-nums;margin:2px 0 8px}
.cf-kv{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:.84rem}
.cf-kv span:nth-child(odd){color:var(--muted)}
.cf-svg{width:100%;height:auto;display:block}
.cf-svg text{font-family:var(--sans);font-size:11px;fill:var(--muted)}
.cf-svg .cf-lab{fill:var(--ink-2);font-size:12px}.cf-svg .cf-lab.b{font-weight:600;fill:var(--ink)}
.cf-svg .cf-ax2{font-size:10px}
.cf-grid{stroke:var(--line);stroke-width:.6}
.cf-prev{stroke:var(--muted);stroke-dasharray:4 4;stroke-width:1}
.cf-path{fill:none;stroke:var(--ink);stroke-width:1.6}
.cf-now{fill:var(--ink)}
.cf-band-o{fill:var(--slate);opacity:.16}.cf-band-i{fill:var(--slate);opacity:.28}.cf-band-soft{fill:var(--slate);opacity:.08}
.cf-med,.cf-medl{stroke:var(--slate);stroke-width:2}
.cf-whisk{stroke:var(--slate);stroke-width:2}
.cf-box{fill:var(--slate);opacity:.45}
.cf-fz{stroke:var(--warn-ink);stroke-width:2.5;stroke-dasharray:3 2}
.cf-fzdot{fill:var(--warn-ink)}
.cf-evl{fill:none;stroke:var(--accent);stroke-width:1.6;stroke-dasharray:2 3;pointer-events:none}
.cf-evd{fill:var(--accent);stroke:var(--surface);stroke-width:1.5;pointer-events:none}
.cf-evk,.cf-kv span.cf-evk{color:var(--accent)}
.cf-hbar{cursor:pointer;outline:none}.cf-hbar .cf-hit{fill:transparent}.cf-hbar.on .cf-hit,.cf-hbar:hover .cf-hit,.cf-hbar:focus .cf-hit{fill:var(--slate-soft);opacity:.7}
.cf-tbl td,.cf-tbl th{white-space:nowrap}
.cf-tbl tr.on td{background:var(--slate-soft)}
.cf-tbl tr[data-cft]{cursor:pointer}
.cf-tag{display:inline-block;font-size:.72rem;color:var(--muted);margin-left:6px}
.cf-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.cf-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:10px 0 14px}
.cf-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:.84rem}
.cf-card h4{margin:0 0 6px;font-size:.86rem}
.cf-note{font-size:.82rem;color:var(--muted);max-width:940px}
.cf-in{color:var(--accent-ink)}.cf-out{color:var(--neg)}
.cf-flash{font-size:.82rem;color:var(--accent-ink)}
@media (max-width:720px){.cf-hero{grid-template-columns:1fr}.cf-big{font-size:1.6rem}.cf-tools .field{min-width:130px}}
`;
 document.head.appendChild(st);
}
function cfAssetPick(d){
 const keys=Object.keys(d.assets||{});
 if(!keys.includes(state.cfa))state.cfa=keys.includes('SPY')?'SPY':keys[0];
 return keys;
}
function cfView(){
 cfCss();
 let out=head('Close forecast','Where each asset closes today, on this week\'s option expiries, at the end of the week, in two weeks, at the end of the month and of the quarter: the options, the prediction markets, the volatility indices and the asset\'s own history, each scaled so its ranges held as often as they claim on its record, then pooled. Freeze a forecast to set it against the live one and the close.','Forecast');
 const g=cfData();
 if(g.err&&!g.data)return out+empty(`The forecast could not load (${g.err}). It is made every five minutes through the US session by the intraday relay (app/closecast.py) and published on the branch forecast-live.`);
 if(!g.data)return out+empty('Loading the forecast…');
 const d=g.data,keys=cfAssetPick(d),a=d.assets[state.cfa];
 if(state.cfc==null)state.cfc=80;
 const ixu=a&&a.index&&a.index.ratio;
 const A=cfAccount(),mine=cfAll().filter(f=>f.asset===state.cfa);
 const off=((cfRecord().data||{}).latest||[]).filter(f=>f.assets&&f.assets[state.cfa]).slice().reverse();
 const cmp=[['','Nothing']].concat(mine.map(f=>[f.id,'Your freeze · '+cfTime(f.at)+(A.state==='on'&&f.where==='browser'?' (this browser)':'')])).concat(off.map(f=>['o'+f.slot,'Official · '+f.slot.replace(/^\d{4}-/,'')]));
 if(state.cfcmp&&!cmp.some(x=>x[0]===state.cfcmp))state.cfcmp='';
 out+=`<div class="cf-tools">${field('cf-a','Asset',keys.map(k=>[k,d.assets[k].name]),state.cfa)}`
  +`<div class="cf-conf"><label for="cf-c">Confidence: <b id="cf-cv">${state.cfc}%</b> of closes inside the range</label><input id="cf-c" type="range" min="50" max="99" step="1" value="${state.cfc}" aria-label="Confidence level"></div>`
  +(ixu?field('cf-u','Units',[['etf',a.key+' price'],['index',a.index.name+' points']],state.cfu==='index'?'index':'etf'):'')
  +`<div class="field"><label for="cf-x">P(close above)</label><input id="cf-x" class="cf-x" type="number" step="any" inputmode="decimal" placeholder="a price" value="${state.cfx==null?'':esc(state.cfx)}"></div>`
  +field('cf-cmp','Compare with',cmp,state.cfcmp||'')
  +`<div class="field"><label>&nbsp;</label><button type="button" class="cf-btn pri" id="cf-freeze" title="${A.state==='on'?'Keep this forecast in your account (every device you sign in on)':'Keep this forecast in this browser'}">Freeze now</button></div></div>`;
 return out+`<div id="cf-body">${cfBody(d)}</div>`;
}
function cfBody(d){
 const a=d.assets[state.cfa];if(!a)return empty('No forecast for this asset in this run.');
 const c=(state.cfc||80)/100,zg=cfZ(d.pgrid),u=cfUnits(a),s0=a.start||a.price,fz=cfFrozen(a.key,d);
 const W=cfWidth(),wHero=W<720?W-34:Math.max(380,W-352);
 const ts=a.targets||[];if(!ts.length)return empty('No dates to forecast for this asset yet.');
 if(!ts.some(t=>t.date===state.cft))state.cft=ts[0].date;
 const t0=ts[0],sel=ts.find(t=>t.date===state.cft)||t0;
 const r0=cfRange(t0.q,c,zg),lab0=cfTargetLabel(t0,d);
 const X=state.cfx!=null&&state.cfx!==''&&Number.isFinite(+state.cfx)?(+state.cfx)/u.k:null;
 let out='';
 if(cfStore.flash)out+=`<p class="cf-flash" role="status">${esc(cfStore.flash)}</p>`;
 // today's close (or the next one)
 const left=d.phase==='open'&&t0.lead_h!=null?(t0.lead_h>=1?fmt(Math.floor(t0.lead_h))+' h '+fmt(Math.round((t0.lead_h%1)*60))+' min':fmt(Math.round(t0.lead_h*60))+' min')+' to the close':'';
 const mv=a.prev?a.price/a.prev-1:null,lc=cfLast(d,a),em0=cfMean(t0.q,zg),ev0=em0!=null?s0*em0:null;
 out+=`<div class="cf-hero"><div><h3>${esc(lab0.name)}${lab0.tags?`<span class="cf-tag">${esc(lab0.tags)}</span>`:''}</h3>`
  +`<div class="cf-big">${cfPx(s0*Math.exp(r0[1]),u)} <small class="muted" style="font-size:.8rem;font-weight:400">median</small></div><div class="cf-rng">${fmt(c*100)}% range <b>${cfPx(s0*Math.exp(r0[0]),u)} – ${cfPx(s0*Math.exp(r0[2]),u)}</b> <span class="muted">(${cfSign(Math.exp(r0[0])-1)} / ${cfSign(Math.exp(r0[2])-1)})</span></div>`
  +`<div class="cf-kv">${ev0!=null?`<span>Expected value <span class="cf-evk" aria-hidden="true">◆</span></span><span><b>${cfPx(ev0,u)}</b> <span class="muted">(${cfSign(ev0/(s0*Math.exp(r0[1]))-1)} from the median)</span></span>`:''}<span>Now</span><span>${cfPx(a.price,u)} ${mv!=null?`<span class="${mv>=0?'positive':'negative'}">${cfSign(mv)}</span>`:''} · ${esc(cfTime(a.time))}</span>`
  +(left?`<span>Left</span><span>${left}</span>`:'')
  +(a.start&&Math.abs(a.start/a.price-1)>1e-6?`<span>Starts at</span><span>${cfPx(a.start,u)} <span class="muted">(the ${esc((a.futures||{}).symbol||'future')}'s move since the close)</span></span>`:'')
  +(lc?`<span>Closes above the last close</span><span><b>${cfPc(1-cfCdf(t0.q,Math.log(lc/s0),zg))}</b> <span class="muted">(${cfPx(lc,u)})</span></span>`:'')
  +(X!=null?`<span>Closes above ${cfPx(X,u)}</span><span><b>${cfPc(1-cfCdf(t0.q,Math.log(X/s0),zg))}</b></span>`:'')
  +(()=>{const hl=cfHL(t0,c,zg),open=d.phase==='open';let h='';
    if(hl.hi)h+=`<span>${open?'High from now':'The session\'s high'}</span><span>${cfPx(s0*Math.exp(hl.hi[1]),u)} <span class="muted">(${fmt(c*100)}%: ${cfPx(s0*Math.exp(hl.hi[0]),u)} – ${cfPx(s0*Math.exp(hl.hi[2]),u)}${hl.so?` · so far ${cfPx(s0*Math.exp(hl.so[0]),u)}`:''})</span></span>`;
    if(hl.lo)h+=`<span>${open?'Low from now':'The session\'s low'}</span><span>${cfPx(s0*Math.exp(hl.lo[1]),u)} <span class="muted">(${fmt(c*100)}%: ${cfPx(s0*Math.exp(hl.lo[0]),u)} – ${cfPx(s0*Math.exp(hl.lo[2]),u)}${hl.so?` · so far ${cfPx(s0*Math.exp(hl.so[1]),u)}`:''})</span></span>`;
    if(X!=null){const tc=cfTouch(t0,X,s0,zg);if(tc)h+=`<span>Trades at ${cfPx(X,u)} by the close</span><span><b>${tc.done?'already today':cfPc(tc.p)}</b></span>`}
    return h})()
  +(fz?cfFzLine(t0,fz,c,u,s0,zg):'')
  +`</div></div><div>${cfTodayChart(a,t0,d,c,fz,u,wHero)}</div></div>`;
 // every date
 out+=`<h3>Every date <span class="muted" style="font-weight:400;font-size:.85rem">· the ${fmt(c*100)}% range (whisker), the middle half (box), the median (—) and the expected value (<span class="cf-evk">◆</span>) · tap a date for its sources</span></h3>`;
 out+=cfHorizonChart(a,d,c,fz,u,sel.date,W);
 const hdr=['Date','Sessions','Median','Expected',`${fmt(c*100)}% range`,'Half the range',`Above the last close${lc?' ('+cfPx(lc,u)+')':''}`,'High by then','Low by then'].concat(X!=null?[`Closes above ${cfPx(X,u)}`,`Trades at ${cfPx(X,u)}`]:[]).concat(fz?['Frozen median',`Frozen ${fmt(c*100)}%`,'Shift']:[]).concat(['Close']);
 const closes=((cfCloses().data||{})[a.key])||{};
 out+=`<div class="tablebox"><table class="cf-tbl"><thead><tr>${hdr.map((h,i)=>`<th class="${i?'num':''}">${esc(h)}</th>`).join('')}</tr></thead><tbody>`;
 for(const t of ts){
  const r=cfRange(t.q,c,zg),lab=cfTargetLabel(t,d),f=fz&&fz.targets.find(x=>x.date===t.date);
  let fzc=[];
  if(fz){if(f){const zf=cfZ(fz.pgrid),fm=cfLin(0,zf,f.px),flo=cfLin(cfInvN((1-c)/2),zf,f.px),fhi=cfLin(cfInvN((1+c)/2),zf,f.px);
    fzc=[cfPx(fm,u),`${cfPx(flo,u)} – ${cfPx(fhi,u)}`,cfSign(s0*Math.exp(r[1])/fm-1)]}else fzc=['—','—','—']}
  const y=closes[t.date];let cl='—';
  if(y){const pf=f?(()=>{const zf=cfZ(fz.pgrid);const lo=cfLin(cfInvN((1-c)/2),zf,f.px),hi=cfLin(cfInvN((1+c)/2),zf,f.px);return y>=lo&&y<=hi?' <span class="cf-in">inside the frozen range</span>':' <span class="cf-out">outside the frozen range</span>'})():'';cl=cfPx(y,u)+pf}
  out+=`<tr data-cft="${t.date}" class="${t.date===sel.date?'on':''}"><td><b>${esc(lab.name)}</b>${lab.tags?`<span class="cf-tag">${esc(lab.tags)}</span>`:''}</td>`
   +`<td class="num">${t.sessions===0?(d.phase==='open'?fmt((t.risk_sessions||0)*100)+'% of today':'1'):fmt(t.sessions+(d.phase==='open'?0:1))}</td>`
   +`<td class="num">${cfPx(s0*Math.exp(r[1]),u)}</td><td class="num">${(()=>{const m=cfMean(t.q,zg);return m!=null?cfPx(s0*m,u):'—'})()}</td><td class="num">${cfPx(s0*Math.exp(r[0]),u)} – ${cfPx(s0*Math.exp(r[2]),u)}</td>`
   +`<td class="num">±${fmt((Math.exp(r[2])-Math.exp(r[0]))/2*100,2)}%</td><td class="num">${lc?cfPc(1-cfCdf(t.q,Math.log(lc/s0),zg)):'—'}</td>`
   +(()=>{const hl=cfHL(t,c,zg);return `<td class="num" title="${fmt(c*100)}%: ${hl.hi?cfPx(s0*Math.exp(hl.hi[0]),u)+' – '+cfPx(s0*Math.exp(hl.hi[2]),u):''}">${hl.hi?cfPx(s0*Math.exp(hl.hi[1]),u):'—'}</td><td class="num" title="${fmt(c*100)}%: ${hl.lo?cfPx(s0*Math.exp(hl.lo[0]),u)+' – '+cfPx(s0*Math.exp(hl.lo[2]),u):''}">${hl.lo?cfPx(s0*Math.exp(hl.lo[1]),u):'—'}</td>`})()
   +(X!=null?`<td class="num"><b>${cfPc(1-cfCdf(t.q,Math.log(X/s0),zg))}</b></td><td class="num">${(()=>{const tc=cfTouch(t,X,s0,zg);return tc?(tc.done?'already':cfPc(tc.p)):'—'})()}</td>`:'')
   +fzc.map(v=>`<td class="num">${v}</td>`).join('')+`<td class="num">${cl}</td></tr>`;
 }
 out+='</tbody></table></div>';
 // the sources of the date picked
 const ls=cfTargetLabel(sel,d);
 out+=`<h3>Sources · ${esc(ls.name)}${ls.tags?` <span class="cf-tag">${esc(ls.tags)}</span>`:''}</h3>${cfSrcChart(sel,a,d,c,u,W)}`;
 const rows=CF_SRC.filter(([k])=>sel.src[k]).map(([k,l,desc])=>{const s=sel.src[k],r=cfRange(s.q,c,zg);
  return `<tr><td><span class="cf-dot" style="background:${CF_COL[k]}"></span><b>${esc(l)}</b><br><span class="muted" style="font-size:.78rem">${esc(desc)}</span></td>`
   +`<td class="num">${fmt((s.w||0)*100)}%</td><td class="num">${s.k==null?'—':'×'+fmt(s.k,2)}</td><td class="num">${s.raw_median==null?'—':cfPx(s0*Math.exp(s.raw_median),u)}</td>`
   +`<td class="num">${cfPx(s0*Math.exp(r[0]),u)} – ${cfPx(s0*Math.exp(r[2]),u)}</td><td style="white-space:normal;min-width:220px">${cfSrcNote(k,s,a,u)}</td></tr>`}).join('');
 out+=`<div class="tablebox"><table class="cf-tbl"><thead><tr><th>Source</th><th class="num">Weight</th><th class="num">Scale</th><th class="num">Its own median</th><th class="num">${fmt(c*100)}% range (scaled)</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table></div>`;
 out+=`<p class="cf-note">Scale: how much each source's spread was widened (×&gt;1) or narrowed (×&lt;1) so that its ranges held as often as they claim on its record. Pooled: the median starts at the price now${(()=>{const dr=a.drift;return dr&&dr.session!=null?` and rises ${cfSign(dr.session,3)} a session — the drift: ${esc(a.key)}'s own ${dr.own!=null?cfSign(dr.own,3)+' a session over ten years, ':''}pulled toward the market's long-run ${cfSign(dr.prior,3)}`:''})()}${(a.factors||{}).applied?'; today\'s moved by the factors':''}; the spread averages the scaled sources around their own medians, half to the market-implied ones (options, prediction markets, volatility indices), half to history (analogs, simulation); a source whose quotes are wide counts half.</p>`;
 out+=cfInputs(a,d,u);
 out+=cfFreezes(a,d,u,c);
 out+=cfRecordView(a);
 out+=cfMethod(a,d);
 return out;
}
function cfFzLine(t0,fz,c,u,s0,zg){
 const f=fz.targets.find(x=>x.date===t0.date);if(!f)return '';
 const zf=cfZ(fz.pgrid),fm=cfLin(0,zf,f.px),lo=cfLin(cfInvN((1-c)/2),zf,f.px),hi=cfLin(cfInvN((1+c)/2),zf,f.px);
 return `<span>${esc(fz.label)}</span><span>${cfPx(fm,u)} · ${cfPx(lo,u)} – ${cfPx(hi,u)} <span class="muted">(${esc(cfTime(fz.at))}; live median ${cfSign(s0*Math.exp(cfQ(t0.q,0.5,zg))/fm-1)})</span></span>`;
}
function cfSrcNote(k,s,a,u){
 if(k==='options')return `${s.exact?'expiry':'next expiry'} ${esc(cfDay(s.exp))} · near-the-money spread ${s.spread==null?'—':fmt(s.spread*100,1)+'%'}${s.max_pain?` · max pain ${cfPx(s.max_pain,u)}`:''}${s.put_wall?` · put wall ${cfPx(s.put_wall,u)}`:''}${s.call_wall?` · call wall ${cfPx(s.call_wall,u)}`:''}${s.as_of?` · quotes ${esc(s.as_of)} UTC`:''}`;
 if(k==='markets')return (s.ladders||[]).map(l=>`${l.url?`<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.source==='kalshi'?'Kalshi':'Polymarket')}</a>`:esc(l.source)}: ${esc(l.title||'')} <span class="muted">(${fmt(l.strikes)} strikes${l.overround?` · overround ${fmt(l.overround,2)}`:''}${l.age_h!=null?` · read ${l.age_h<1?fmt(l.age_h*60)+' min':fmt(l.age_h,1)+' h'} before`:''})</span>`).join('<br>');
 if(k==='implied')return `σ to the close ${fmt((s.sigma||0)*100,2)}% · ${(s.tenors||[]).map(x=>({1:'VIX1D',9:'VIX9D',30:'30-day',93:'VIX3M',186:'VIX6M'})[x]||x+'d').join(', ')}`;
 if(k==='analogs')return s.mark?`the ${fmt(s.n)} days whose move by ${esc(s.mark)} was nearest to today's: their move from then to the close`:`the ${fmt(s.n)} days whose volatility and trends were nearest: their next ${fmt(s.sessions)} session${s.sessions>1?'s':''}, rescaled to today's volatility`;
 if(k==='moves')return `the ${fmt(s.n)} days whose one-day move was within 2.5 percentile points of the last one (${fmt(s.pct,1)}th percentile${a.last_move?`: ${cfSign(a.last_move.move)} on ${esc(cfDay(a.last_move.date))}`:''}): their next ${fmt(s.sessions)} session${s.sessions>1?'s':''}`;
 if(k==='regime')return `${esc(s.label)}: the returns after its ${fmt(s.n)} most similar days in that regime, scaled to the date · not calibrated (counts half)`;
 if(k==='sim')return `${fmt(s.paths)} paths over ${fmt(s.sessions)} session${s.sessions>1?'s':''}, volatility updated along each`;
 return '';
}
function cfInputs(a,d,u){
 const b=a.book||{},fu=a.futures,fa=a.factors||{},vol=a.vol||{};
 let h='<div class="cf-cards">';
 if(b.bid||b.ask){const sp=b.ask&&b.bid?(b.ask-b.bid):null,im=b.bid_size&&b.ask_size?(b.bid_size-b.ask_size)/(b.bid_size+b.ask_size):null;
  h+=`<div class="cf-card"><h4>Order book (best bid and ask)</h4>${cfPx(b.bid,{k:1,dec:2})} × ${fmt(b.bid_size)} · ${cfPx(b.ask,{k:1,dec:2})} × ${fmt(b.ask_size)}<br>spread ${sp==null?'—':fmt(sp,2)} · size imbalance ${im==null?'—':cfSign(im,0)}<br><span class="muted">CBOE, ${esc(b.quote_time||'')} UTC (about 15 minutes late). Shown, not used: it says where the next trades go, not the close.</span></div>`}
 if(fu)h+=`<div class="cf-card"><h4>Futures · ${esc(fu.symbol)}</h4>${fmt(fu.price,2)} · ${cfSign(fu.move)} since the last close${fu.vs_asset!=null?`<br>against ${esc(a.key)}: ${cfSign(fu.vs_asset,2)}`:''}<br><span class="muted">${d.phase==='open'?'In the session the future and the fund move together: context only.':'Sets where the next session starts.'}</span></div>`;
 const vk=Object.keys(vol);if(vk.length)h+=`<div class="cf-card"><h4>Volatility indices</h4>${vk.map(k=>`${({1:'1-day',9:'9-day',30:'30-day',93:'3-month',186:'6-month'})[k]||k+'-day'} <b>${fmt(vol[k],1)}</b>`).join(' · ')}<br><span class="muted">Annualised implied volatility; the term structure sets the volatility source at each date.</span></div>`;
 h+=cfRegimeCard(a,u);
 if(fa&&fa.mark)h+=`<div class="cf-card"><h4>Factors at ${esc(fa.mark)}</h4>${fa.inputs?`move so far ${cfSign(fa.inputs.move,2)} · against VWAP ${cfSign(fa.inputs.vs_vwap,2)} · first hour ${cfSign(fa.inputs.first_hour,2)}<br>`:''}${fa.predicted!=null?`predicted to the close ${cfSign(fa.predicted,3)} · `:''}out-of-sample R² ${fa.r2_oos==null?'—':fmt(fa.r2_oos*100,2)+'%'}<br><span class="${fa.applied?'cf-in':'muted'}">${fa.applied?'Applied to the centre.':esc(fa.note||'Not applied.')}</span></div>`;
 return h+'</div>';
}
function cfRegimeCard(a,u){
 const lm=a.last_move,rs=a.regimes||[],P=(o,h)=>o&&o.p&&o.p[h]!=null?pct(o.p[h],0):'—',Q=(o,k='p50')=>o&&o[k]!=null?cfSign(o[k],1):'—';
 let h=`<div class="cf-card"><h4>Move odds · highs, lows &amp; ranges</h4>`;
 if(lm)h+=`Last move ${cfSign(lm.move)} on ${esc(cfDay(lm.date))}: the ${fmt(lm.pct,1)}th percentile of its days.<br>`;
 if(!rs.length)return h+`<span class="muted">Not at its highs, at a low or in a range now.</span></div>`;
 for(const r of rs){const A=r.analogues||{},S=r.state||{};
  h+=`<b>${esc(r.label.replace(/^./,x=>x.toUpperCase()))}</b>`;
  if(r.file==='highs')h+=`${S.age!=null?` · run ${fmt(S.age)} days old`:''}: in the ${fmt(A.days||250)} most similar days, a 5% pullback within a month ${P(A.t5,'21')}, three months ${P(A.t5,'63')}; 10%: ${P(A.t10,'21')} / ${P(A.t10,'63')}; 20%: ${P(A.t20,'21')} / ${P(A.t20,'63')}. Another new high ${A.more_highs!=null?pct(A.more_highs,0):'—'}; gain left in the run ${Q(A.gain_left)}; the largest fall within three months ${Q(A.mdd63)}; higher a month on ${A.fwd21&&A.fwd21.up!=null?pct(A.fwd21.up,0):'—'}.<br>`;
  else if(r.file==='lows')h+=`: in the ${fmt(A.days||250)} most similar days, another new low within a month ${P(A.next_low,'21')}; a 10% rebound within a month ${P(A.r10,'21')}, three months ${P(A.r10,'63')}; 20%: ${P(A.r20,'21')} / ${P(A.r20,'63')}; the further fall ${Q(A.fall)}, the bounce ${Q(A.bounce)}; higher three months on ${A.fwd63&&A.fwd63.up!=null?pct(A.fwd63.up,0):'—'}.<br>`;
  else h+=`${S.width!=null?` · ${fmt(S.width*100,1)}% wide`:''}${S.days_in!=null?`, ${fmt(S.days_in)} days`:''}: in the ${fmt(A.days||250)} most similar days, a breakout within a month ${P(A.breakout,'21')}, three months ${P(A.breakout,'63')}; up first ${A.up_first!=null?pct(A.up_first,0):'—'}; back into the range within a month after breaking up ${A.failed_up!=null?pct(A.failed_up,0):'—'}, down ${A.failed_down!=null?pct(A.failed_down,0):'—'}; higher three months on ${A.fwd63&&A.fwd63.up!=null?pct(A.fwd63.up,0):'—'}.<br>`;
 }
 void u;
 return h+`<span class="muted">Move odds → Highs, lows &amp; ranges; descriptive history.</span></div>`;
}
function cfFreezes(a,d,u,c){
 const A=cfAccount(),mine=cfAll().filter(f=>f.asset===a.key),here=cfMine().length;
 const signin=`<a href="${esc((globalThis.FF_SITE_ROOT??'../')+'#account')}">sign in</a>`;
 const where=A.state==='on'?`Kept in your account: every device you sign in on has them.${here?` <button type="button" class="cf-btn" id="cf-move">Move ${here===1?'1 freeze':fmt(here)+' freezes'} from this browser to your account</button>`:''}`
  :A.state==='loading'?'Reading your account\'s freezes…'
  :A.state==='off'?`Your account's freezes could not be read (${esc(A.err||'')}): these are kept in this browser meanwhile.`
  :`Kept in this browser only; ${signin} (Alerts, e-mail only, no password) to keep them in your account and see them on every device.`;
 let h=`<h3>Your freezes · ${esc(a.key)}</h3>`;
 if(!mine.length)return h+`<p class="cf-note">None yet. <b>Freeze now</b> keeps this forecast, every date; then pick it under <b>Compare with</b> to see how the live forecast has moved and, once a date has closed, where the close fell in the frozen range. ${where}</p>`;
 h+=`<div class="tablebox"><table class="cf-tbl"><thead><tr><th>Frozen</th><th class="num">Price then</th><th class="num">First date</th><th class="num">Its ${fmt(c*100)}% range</th><th>Kept</th><th></th></tr></thead><tbody>`;
 for(const f of mine.slice(0,20)){
  const t=(f.targets||[])[0];const r=t?cfRange(t.q,c,cfZ(f.pgrid||d.pgrid)):null;
  h+=`<tr><td>${esc(cfTime(f.at))}</td><td class="num">${cfPx(f.price||f.start,u)}</td><td class="num">${t?esc(cfDay(t.date)):'—'}</td><td class="num">${r?`${cfPx(f.start*Math.exp(r[0]),u)} – ${cfPx(f.start*Math.exp(r[2]),u)}`:'—'}</td>`
   +`<td>${f.where==='account'?'your account':'this browser'}</td><td><button type="button" class="cf-btn" data-cfuse="${esc(f.id)}">Compare</button> <button type="button" class="cf-btn" data-cfdel="${esc(f.id)}" aria-label="Delete this freeze">Delete</button></td></tr>`;
 }
 return h+`</tbody></table></div><p class="cf-note">${where}</p>`;
}
function cfRecordView(a){
 const r=cfRecord();
 let h='<h3>The record of the official freezes</h3>';
 if(!r.data)return h+`<p class="cf-note">${r.err?'The record is not published yet: the first official freeze is made at 9:45 New York on the next session, and scored once its dates have closed.':'Loading…'}</p>`;
 const d=r.data;
 if(!d.n)return h+`<p class="cf-note">Freezes are being filed (9:45, 12:00 and 15:00 New York each session); none of their dates has closed yet.</p>`;
 const row=(name,s)=>s?[esc(name),fmt(s.n),pct(s.inside['0.5'],0),pct(s.inside['0.8'],0),pct(s.inside['0.95'],0),fmt(s.mae*100,2)+'%']:null;
 const rows=[row('Every forecast',d.all)].concat(Object.entries(d.by_bucket||{}).map(([b,s])=>row(b,s))).concat(Object.entries(d.by_time||{}).map(([t,s])=>row('frozen at '+t,s))).concat([row(a.key+' only',(d.by_asset||{})[a.key])]).filter(Boolean);
 h+=`<div class="tablebox"><table class="cf-tbl"><thead><tr><th>Forecasts</th><th class="num">Scored</th><th class="num">Inside 50%</th><th class="num">Inside 80%</th><th class="num">Inside 95%</th><th class="num">Median's error</th></tr></thead><tbody>${rows.map(r=>`<tr>${r.map((v,i)=>`<td class="${i?'num':''}">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
 return h+`<p class="cf-note">A calibrated forecast's closes fall inside its 50, 80 and 95% ranges about 50, 80 and 95% of the time. Each freeze is scored on every date it forecast once that date has closed.</p>`;
}
function cfMethod(a,d){
 const cal=a.calibration||{},ia=cal.intraday_analogs,ii=cal.intraday_implied;
 const marks=['9:30','10:30','11:30','12:30','1:30','2:30','3:30'];
 let h='<details class="cf-note" style="margin-top:12px"><summary><b>How it is made, and how each source was scaled</b></summary>';
 h+='<p>Each source gives a distribution of the close; each is scaled around its own median by the factor (×) that made its 50, 80 and 95% ranges hold closest to 50, 80 and 95% of the time on its record: the intraday analogs and the 1-day implied volatility on two to three years of hourly bars, the daily analogs, the simulation and the volatility indices on ten years of daily closes (recomputed every day), the options and the prediction markets on every resolved price ladder (the ladder backtest). Then they are pooled. The median starts at the price now and rises by the asset\'s drift: its own mean daily move over ten years, pulled toward the market\'s long-run 0.03% a session, the more so the noisier it is. Left at the price now, the median was too low: from 2019 to 2026 the close ended above it 58% of the time two weeks on and 64% seven weeks on; above the drifted one 54% and 56%, and nearer on average (not in a falling year like 2022). The markets\' own expected value is not used: on every resolved ladder the price now was nearer the close. The expected value (◆) is the probability-weighted average of the close over the pooled distribution (its tails continued as a normal\'s), not the median: it sits below the median when the fall tail is the heavier one (index options price crashes), above it when the spread is wide (a volatile stock months out), since a price can rise further than it can fall. Risk-neutral sources (options, volatility indices) carry the market\'s price of risk: their ranges usually come out wide, and the scale narrows them.</p>';
 if(ia||ii)h+=`<p>Today's close, by hour — scale (80% range held before → after): ${marks.map((m,i)=>`${m}: ${ia&&ia[i]?`analogs ×${fmt(ia[i].k,2)} (${pct(ia[i].raw['0.8'],0)}→${pct(ia[i].fit['0.8'],0)})`:''}${ii&&ii[i]?` · implied ×${fmt(ii[i].k,2)} (${pct(ii[i].raw['0.8'],0)}→${pct(ii[i].fit['0.8'],0)})`:''}`).join('; ')}.</p>`;
 for(const [k,l] of [['daily_analogs','Daily analogs'],['daily_sim','Simulation'],['daily_implied','Volatility indices']]){const v=cal[k];if(v)h+=`<p>${l} — ${Object.entries(v).map(([n,x])=>`${n} session${n==='1'?'':'s'}: ×${fmt(x.k,2)} (${pct(x.raw['0.8'],0)}→${pct(x.fit['0.8'],0)}, ${fmt(x.n)} forecasts)`).join('; ')}.</p>`}
 if(cal.factors_r2)h+=`<p>Factors (move so far, gap to VWAP, first hour → move to the close), out-of-sample R² by hour: ${cal.factors_r2.map((x,i)=>x==null?null:`${marks[i]} ${fmt(x*100,2)}%`).filter(Boolean).join(', ')} — applied only above 0.5%.</p>`;
 h+=`<p>Built ${esc(cfTime(d.generated_at))}; calibration of ${esc((d.calibration||{}).refreshed||'—')}. Not investment advice: a description of the odds the sources give, scaled by their own record.</p></details>`;
 return h;
}
function cfPaint(){
 const body=$('cf-body'),g=cfStore.fc;if(!body||!g||!g.data)return;
 body.innerHTML=cfBody(g.data);cfBindBody();
 const cv=$('cf-cv');if(cv)cv.textContent=(state.cfc||80)+'%';
}
function cfBindBody(){
 document.querySelectorAll('#cf-body [data-cft]').forEach(el=>{
  const go=()=>{state.cft=el.dataset.cft;cfPaint()};
  el.onclick=go;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}};
 });
 document.querySelectorAll('#cf-body [data-cfdel]').forEach(b=>b.onclick=async()=>{b.disabled=true;await cfDrop(b.dataset.cfdel);if(state.cfcmp===b.dataset.cfdel)state.cfcmp='';render()});
 const mv=document.getElementById('cf-move');
 if(mv)mv.onclick=async()=>{mv.disabled=true;const r=await cfMoveHere();cfStore.flash=r.moved?`Moved ${r.moved} freeze${r.moved>1?'s':''} to your account.`+(r.why?` The rest stay here: ${r.why}.`:''):`Nothing moved: ${r.why}.`;render()};
 document.querySelectorAll('#cf-body [data-cfuse]').forEach(b=>b.onclick=()=>{state.cfcmp=b.dataset.cfuse;render()});
}
let cfTimer=null;
function cfBind(){
 if(state.tab!=='forecast')return;
 const g=cfStore.fc;if(!g||!g.data)return;
 if($('cf-a'))$('cf-a').onchange=e=>{state.cfa=e.target.value;state.cft='';state.cfcmp='';cfStore.flash='';render()};
 if($('cf-u'))$('cf-u').onchange=e=>{state.cfu=e.target.value;cfPaint()};
 if($('cf-c'))$('cf-c').oninput=e=>{state.cfc=+e.target.value;cfPaint()};
 if($('cf-x'))$('cf-x').oninput=e=>{const v=e.target.value.trim();clearTimeout(cfStore.xt);cfStore.xt=setTimeout(()=>{state.cfx=v===''?null:v;cfPaint()},250)};
 if($('cf-cmp'))$('cf-cmp').onchange=e=>{state.cfcmp=e.target.value;cfPaint()};
 if($('cf-freeze'))$('cf-freeze').onclick=async e=>{const d=cfStore.fc.data,a=d.assets[state.cfa];if(!a)return;e.target.disabled=true;
  try{
   if(CF_ACCT.state==='loading'&&CF_ACCT.ready)await CF_ACCT.ready;
   const r=await cfFreezeNow(d,a);state.cfcmp=r.id;
   cfStore.flash=`Frozen: ${a.key} as of ${cfTime(d.generated_at)}, kept in ${r.where==='account'?'your account':'this browser'}${r.why?` (${r.why})`:''} — now set against the live forecast (Compare with).`;
  }catch(err){cfStore.flash='Not frozen: '+((err&&err.message)||err)}
  finally{render()}};
 cfBindBody();
 if(!cfTimer){cfTimer=setInterval(()=>{if(state.tab==='forecast'&&document.visibilityState!=='hidden'){cfData();cfCloses();cfRecord()}},60000);
  let rz=null;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(state.tab==='forecast')cfPaint()},200)})}
}
function forecastDeepLink(arg){const v=decodeURIComponent(arg||'').trim().toUpperCase();if(/^[A-Z.\-]{1,6}$/.test(v))state.cfa=v.replace('.','-')}
function cfNotice(){
 const s=cfStore.fc||cfData(),d=s.data;
 if(s.err&&!d)return {stale:true,text:'Close forecast unavailable · '+s.err};
 if(!d)return {stale:false,text:'Close forecast loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/60000;
 const when=d.phase==='open'?'every five minutes through the session':'next update shortly before the open (9:10 New York)';
 return {stale:d.phase==='open'&&age>20,text:`Close forecast built ${cfTime(d.generated_at)} (${cfAgo(d.generated_at)}) · ${fmt(Object.keys(d.assets||{}).length)} assets · ${when}`};
}
if(typeof window!=='undefined'){
 window.forecastDeepLink=forecastDeepLink;
 window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{forecast:cfNotice});
 window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{forecast:cfView});
 window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{forecast:cfBind});
}
if(typeof module!=="undefined")module.exports={cfInvN,cfN,cfQ,cfCdf,cfRange,cfMean,cfZ,cfLin,cfTargetLabel,cfBody,cfStore,cfFreezeNow,cfMine,cfAll,cfAccount,cfDrop,cfMoveHere,CF_ACCT};
})();
