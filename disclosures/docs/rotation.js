/* 4.4 rotation views. Data: data/market/rotation.json and rotation-monthly.json (app/rotation.py, built at publish).
   Uses the helpers of market.js.
   · Momentum clock — any two variables as x and y (a third as dot size), every company's path period by period,
     played as an animation over 16 quarters or 48 months with trails.
   · 3-D — three variables (or two and time) in a box you can turn; with time as depth a rotation becomes a spiral.
   · Solar system — the market average at the centre, every sector a sun orbiting it (with its tail), each sector's
     companies as moons; pick a sector to see its companies as planets around their sun.
   · Find the best axes — every pair of variables scanned for the clearest cycle, and every single, pair and triple
     scanned for how well it sorted the stock's later moves (with a split-half check and the chance level).
   Every chart reads its coordinates through one pipeline: scale (as reported, signed log, rank or standard score
   within the period) → smoothing (exponential or moving average, using past values only) → drawing (curved trails). */
const ROT_SERIES=['var(--rot-1)','var(--rot-2)','var(--rot-3)'];
const ROT_TRAIL=[['4','4 quarters'],['8','8 quarters'],['12','12 quarters'],['16','16 quarters']];
const ROT_TRAIL_M=[['6','6 months'],['12','12 months'],['24','24 months'],['48','48 months']];
const ROT_VIEWS=[['clock','Momentum clock'],['3d','3-D (drag to turn)'],['solar','Solar system'],['map','Market map (treemap)'],['heat','Sector heatmap'],['rs','Relative strength ranking'],['breadth','Breadth and dispersion'],['corr','How the variables move together'],['scan','Find the best axes']];
const ROT_SIMPLE=new Set(['rs','scan','map','heat','breadth','corr']);     // views without the x / y / z, scale and smoothing controls
const ROT_SCALES=[['raw','As reported'],['log','Signed log (tames outliers)'],['rank','Rank within the period (0–100)'],['z','Standard score within the period']];
const ROT_SMOOTH=[['none','None'],['ewma','Exponential (recent weighs more)'],['ma','Moving average'],['holt','Holt (level + trend)'],['kalman','Kalman (noise-filtered level)'],['median','Rolling median (ignores spikes)']];
const ROT_FILL=[['line','Straight line between quarter-ends'],['step','Last reported, from the quarter-end'],['avail','Last reported, from about the filing date'],['points','Quarter-end months only']];
const ROT_SHORT={rs:'RS rating',mom121:'12–1 momentum',hi52:'From 52-wk high',pc13:'13F put/call',iv30:'IV30',pcoi:'Put/call OI',dom:'Op. margin Δ',om:'Op. margin',dgm:'Gross margin Δ',gm:'Gross margin',dnm:'Net margin Δ',nm:'Net margin',revg:'Revenue growth',reva:'Growth acceleration',rel:'Stock vs S&P',rel3:'Stock vs S&P, 3 mo',rel6:'Stock vs S&P, 6 mo',ret:'Stock return',vola:'Volatility',volz:'Volume',f13:'13F net managers',gov:'Officials net buys',__time:'Time'};
const ROT_DEFAULT_VARS=[{key:'dom',label:'Operating margin vs a year earlier',unit:'pts',centred:true,group:'Profitability'},{key:'rel',label:'Stock vs the S&P 500, the quarter',unit:'%',centred:true,group:'Price'},{key:'volz',label:'Trading volume vs its own average',unit:'%',centred:true,group:'Trading'}];
const ROT_MONTH_LABELS={rel:'Stock vs the S&P 500, the month',ret:'Stock return, the month',rel3:'Stock vs the S&P 500, three months',rel6:'Stock vs the S&P 500, six months',vola:'Realised volatility in the month (annualised)',volz:'Trading volume vs its own average (month)'};
const ROT_TIME={key:'__time',label:'Time',unit:'',centred:false,group:'Time'};
const ROT={timer:null,ctx:null,yaw:-.75,pitch:.38,spin:false,hits:[]};
// when a variable is public: price-based ones at the period's last close; figures from 10-Q / 10-K, 13F and officials'
// reports only weeks after the quarter ends — so the scan compares those with the stock two quarters later, not the next
const ROT_PRICE=new Set(['rel','rel3','rel6','ret','vola','volz','rs','mom121','hi52','iv30','pcoi']);
const ROT_SCAN_SKIP=new Set(['ret']);           // the raw return duplicates the return against the S&P 500 in a scan
const MONTH_NAMES=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const qlabel=c=>{c=String(c||'');let m=/^CY(\d{4})Q(\d)$/.exec(c);if(m)return `Q${m[2]} ${m[1]}`;m=/^(\d{4})-(\d{2})$/.exec(c);return m?`${MONTH_NAMES[+m[2]-1]} ${m[1]}`:c};
function niceTicks(lo,hi,n=5){const raw=(hi-lo)/n,p=10**Math.floor(Math.log10(raw||1)),st=[1,2,2.5,5,10].map(m=>m*p).find(x=>x>=raw);const out=[];for(let v=Math.ceil(lo/st)*st;v<=hi+1e-9;v+=st)out.push(+v.toFixed(6));return out}
const pp=v=>v==null?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),1)+' pts';
const vshort=v=>v?(ROT_SHORT[v.key]||v.label):'';
function vfmt(v,x){
 if(x==null||!Number.isFinite(+x))return '—';
 const u=v&&v.unit,s=x>0?'+':x<0?'−':'',a=Math.abs(x);
 if(u==='pts')return s+fmt(a,1)+' pts';
 if(u==='%')return v.centred?s+fmt(a,1)+'%':(x<0?'−':'')+fmt(a,1)+'%';
 if(u==='managers'||u==='trades')return s+fmt(a,0);
 if(u==='rank')return fmt(x,0);
 if(u==='x')return fmt(x,2)+'×';
 return fmt(x,1);
}
const quantile=(xs,q)=>xs.length?xs[Math.min(xs.length-1,Math.max(0,Math.floor(q*(xs.length-1))))]:null;
const fin=x=>x!=null&&Number.isFinite(x);

/* ---------- data: columnar rows → objects, once per file ---------- */
function rotFinish(cos,suns,market,vars,quarters){
 for(const v of vars){                               // bounds where the file carries none
  const xs=cos.flatMap(c=>c.pts.map(p=>p[v.key])).filter(fin).sort((a,b)=>a-b);
  if(v.n==null)v.n=xs.length;
  if(v.lo==null&&xs.length){v.lo=quantile(xs,.03);v.hi=quantile(xs,.97);v.median=quantile(xs,.5)}
  if(!v.scale&&xs.length){const s=(quantile(xs,.75)-quantile(xs,.25))/1.349;v.scale=s>0?s:((v.hi-v.lo)/4||1)}
 }
 for(const c of cos){c.id='t:'+c.t;c.by=new Map(c.pts.map(p=>[p.cal,p]))}
 for(const s of Object.values(suns)){s.id=s.id||s.key;s.by=new Map(s.pts.map(p=>[p.cal,p]))}
 market.by=new Map(market.pts.map(p=>[p.cal,p]));market.id='market';
 const most=Math.max(0,...market.pts.map(p=>p.n||0)),partial=new Set(quarters.filter(c=>((market.by.get(c)||{}).n||0)<.5*most));
 let full=quarters.length-1;while(full>0&&partial.has(quarters[full]))full--;
 const V=Object.fromEntries(vars.map(v=>[v.key,v]));
 return {cos,suns,market,vars,V,quarters,partial,full,byT:new Map(cos.map(c=>[c.t,c])),cache:{ser:new Map(),stats:new Map()}};
}
function rotAverage(cos,vars,cals){                   // log-revenue-weighted mean, each variable clipped to its 3rd–97th percentile
 return cals.map(cal=>{const o={cal,n:0},acc={};
  for(const c of cos){const p=c.by?c.by.get(cal):c.pts.find(q=>q.cal===cal);if(!p)continue;o.n++;const w=Math.log10(Math.max(1e6,p.rev||c.rev||1e6));
   for(const v of vars){const x=p[v.key];if(!fin(x)||v.lo==null)continue;const a=acc[v.key]||(acc[v.key]=[0,0]);a[0]+=w*Math.max(v.lo,Math.min(v.hi,x));a[1]+=w}}
  for(const v of vars)o[v.key]=acc[v.key]&&acc[v.key][1]?acc[v.key][0]/acc[v.key][1]:null;return o}).filter(p=>p.n>=3);
}
function rotPrep(d){
 if(d._prep)return d._prep;
 const F=d.fields,SF=d.sun_fields,row=(fields,r)=>{const o={};fields.forEach((k,i)=>{o[k]=r[i]});return o};
 const fix=p=>({...p,rel:p.rel==null?null:p.rel*100,ret:p.ret==null?null:p.ret*100,volz:p.volz==null?null:p.volz*100});   // first file format
 const cos=(d.companies||[]).map(c=>({...c,pts:F?(c.p||[]).map(r=>row(F,r)):(c.pts||[]).map(fix)}));
 const suns={};
 for(const [k,v] of Object.entries(d.sectors||{})){const pts=SF?(v.p||[]).map(r=>row(SF,r)):(v.pts||[]).map(fix);if(pts.length)suns[k]={id:k,name:v.name,pts}}
 const vars=(d.vars&&d.vars.length?d.vars:ROT_DEFAULT_VARS).map(v=>({...v}));
 const quarters=d.quarters&&d.quarters.length?d.quarters:[...new Set(cos.flatMap(c=>c.pts.map(p=>p.cal)))].sort();
 for(const c of cos)c.by=new Map(c.pts.map(p=>[p.cal,p]));
 rotFinish(cos,{},{pts:[]},vars,quarters);            // bounds first: the averages below clip with them
 const market={name:'Market',pts:d.market&&SF?(d.market.p||[]).map(r=>row(SF,r)):rotAverage(cos,vars,quarters)};
 return d._prep=rotFinish(cos,suns,market,vars,quarters);
}
function rotPrepMonthly(Pq,dm,fill='line'){            // prices month by month; quarterly figures drawn through the months
 dm._preps=dm._preps||{};if(dm._preps[fill])return dm._preps[fill];
 const M=dm.months||[],MF=dm.fields||[],mnum=s=>{const m=/^(\d{4})-(\d{2})$/.exec(s);return m?+m[1]*12+(+m[2]-1):null};
 const qnum=cal=>{const m=/^CY(\d{4})Q(\d)$/.exec(cal);return m?+m[1]*12+3*+m[2]-1:null};
 const fund=Pq.vars.map(v=>v.key).filter(k=>!MF.includes(k)).concat(['rev']);
 const cos=[];
 for(const c of Pq.cos){const rows=(dm.companies||{})[c.t];if(!rows)continue;
  const anchors={};for(const k of fund)anchors[k]=c.pts.map(p=>[qnum(p.cal),p[k]]).filter(a=>a[0]!=null&&fin(a[1])).sort((a,b)=>a[0]-b[0]);
  // how a quarterly figure fills the months: a line between quarter-ends, the last reported value (from the quarter-end
  // or from about when the 10-Q / 10-K is public, ~2 months later), or only the quarter-end month
  const lag=fill==='avail'?2:0;
  const at=(k,n)=>{const a=anchors[k];n-=lag;if(!a.length||n<a[0][0])return [null,false];
   if(fill==='points'){const h=a.find(x=>x[0]===n);return h?[h[1],false]:[null,false]}
   for(let i=0;i<a.length;i++){if(a[i][0]===n)return [a[i][1],false];
    if(a[i][0]>n){const [n0,v0]=a[i-1],[n1,v1]=a[i];return fill==='line'?[v0+(v1-v0)*(n-n0)/(n1-n0),true]:[v0,true]}}
   return n-a[a.length-1][0]<=6?[a[a.length-1][1],true]:[null,false]};   // after the latest quarter: the latest reported, for six months
  const pts=M.map((ym,i)=>{const p={cal:ym,_fill:[]},n=mnum(ym);MF.forEach((k,j)=>{p[k]=rows[i]?rows[i][j]:null});
   for(const k of fund){const [v,f]=at(k,n);p[k]=v;if(f&&v!=null)p._fill.push(k)}return p});
  cos.push({...c,pts});
 }
 const vars=[...Pq.vars.map(({lo,hi,median,scale,n,...v})=>({...v,label:ROT_MONTH_LABELS[v.key]||v.label})),
  ...(MF.includes('rel3')&&!Pq.V.rel3?[{key:'rel3',label:ROT_MONTH_LABELS.rel3,unit:'%',centred:true,group:'Price'}]:[])];
 const GO=['Profitability','Growth','Price','Trading','Ownership','Options'];vars.sort((a,b)=>GO.indexOf(a.group)-GO.indexOf(b.group));
 for(const c of cos)c.by=new Map(c.pts.map(p=>[p.cal,p]));
 rotFinish(cos,{},{pts:[]},vars,M);
 const suns={};
 for(const [k,s] of Object.entries(Pq.suns)){const mine=cos.filter(c=>c.s===k);if(mine.length)suns[k]={id:k,name:s.name,pts:rotAverage(mine,vars,M)}}
 const P=rotFinish(cos,suns,{name:'Market',pts:rotAverage(cos,vars,M)},vars,M);
 P.monthly=true;P.fill=fill;
 return dm._preps[fill]=P;
}

/* ---------- the value pipeline: scale → smoothing ---------- */
function crossStats(P,k,cal){                         // one period's cross-section of a variable
 const key=k+'|'+cal;if(P.cache.stats.has(key))return P.cache.stats.get(key);
 const xs=[];for(const c of P.cos){const p=c.by.get(cal);if(p&&fin(p[k]))xs.push(p[k])}
 xs.sort((a,b)=>a-b);
 const st=xs.length>=5?{xs,med:quantile(xs,.5),sc:((quantile(xs,.75)-quantile(xs,.25))/1.349)||1}:null;
 P.cache.stats.set(key,st);return st;
}
function rotT(o,v,x,cal){
 if(!fin(x))return null;
 if(o.scl==='log'){const c=v.centred?0:(v.median||0),k=v.scale||1;return c+k*Math.asinh((x-c)/k)}
 if(o.scl==='rank'||o.scl==='z'){const st=crossStats(o.P,v.key,cal);if(!st)return null;
  if(o.scl==='z')return Math.max(-5,Math.min(5,(x-st.med)/st.sc));
  let lo=0,hi=st.xs.length;while(lo<hi){const m=(lo+hi)>>1;if(st.xs[m]<x)lo=m+1;else hi=m}let eq=lo;while(eq<st.xs.length&&st.xs[eq]===x)eq++;
  return 100*(lo+(eq-lo)/2)/st.xs.length}
 return x;
}
function rotInv(o,v,u){if(o.scl!=='log')return u;const c=v.centred?0:(v.median||0),k=v.scale||1;return c+k*Math.sinh((u-c)/k)}
function rotSer(o,ent,k){                              // Map period → coordinate, for one company / sun / the market
 const key=o.sig+'|'+ent.id+'|'+k,C=o.P.cache.ser;if(C.has(key))return C.get(key);
 const v=o.P.V[k],raw=o.Q.map(cal=>{const p=ent.by.get(cal);return p?rotT(o,v,p[k],cal):null});
 let out=raw;
 if(o.sm==='ewma'){const a=1-Math.pow(.5,1/(o.P.monthly?3:1));let prev=null;out=raw.map(x=>{if(x==null){prev=null;return null}prev=prev==null?x:prev+a*(x-prev);return prev})}
 else if(o.sm==='ma'){const w=o.P.monthly?3:2;out=raw.map((x,i)=>{if(x==null)return null;let s=0,n=0;for(let j=Math.max(0,i-w+1);j<=i;j++)if(raw[j]!=null){s+=raw[j];n++}return s/n})}
 else if(o.sm==='median'){const w=3;out=raw.map((x,i)=>{if(x==null)return null;const win=raw.slice(Math.max(0,i-w+1),i+1).filter(v=>v!=null).sort((a,b)=>a-b);return win[(win.length-1)>>1]})}
 else if(o.sm==='holt'){const a=o.P.monthly?.35:.5,b=.3;let L=null,T=0;out=raw.map(x=>{if(x==null){L=null;T=0;return null}if(L==null){L=x;T=0;return x}const L0=L;L=a*x+(1-a)*(L+T);T=b*(L-L0)+(1-b)*T;return L})}
 else if(o.sm==='kalman'){                          // local-level model; noise variances from this series' own changes
  const d=[];for(let i=1;i<raw.length;i++)if(raw[i]!=null&&raw[i-1]!=null)d.push(raw[i]-raw[i-1]);
  const vd=d.length>2?d.reduce((s,v)=>s+v*v,0)/d.length:1,R=vd/2||1,Qn=R*(o.P.monthly?.15:.3);let m=null,Pv=0;
  out=raw.map(x=>{if(x==null){m=null;return null}if(m==null){m=x;Pv=R;return x}Pv+=Qn;const K=Pv/(Pv+R);m+=K*(x-m);Pv*=(1-K);return m})}
 const m=new Map(o.Q.map((cal,i)=>[cal,out[i]]));C.set(key,m);return m;
}
function val(o,ent,v,cal){if(!v)return null;if(v.key==='__time')return o.qi.get(cal)??null;const x=rotSer(o,ent,v.key).get(cal);return x==null?null:x}
function centreOf(o,v,cal){
 if(v.key==='__time')return o.qi.get(cal);
 if(o.scl==='rank')return 50;if(o.scl==='z')return 0;
 if(v.centred)return 0;const m=val(o,o.P.market,v,cal);return m==null?rotT(o,v,v.median||0,cal):m;
}
function axisDomain(o,v,ents,cloud){                   // fixed over every period so the animation does not rescale
 if(v.key==='__time')return [-.5,o.Q.length-.5];
 if(o.scl==='rank')return [-4,104];
 const T=x=>o.scl==='z'?x:rotT(o,v,x,null),lo0=o.scl==='z'?-2.5:T(v.lo),hi0=o.scl==='z'?2.5:T(v.hi),pad=(hi0-lo0)*.25;
 let xs=[];for(const e of ents)for(const cal of o.Q){const x=val(o,e,v,cal);if(x!=null)xs.push(Math.max(lo0-pad,Math.min(hi0+pad,x)))}
 if(cloud||!xs.length)xs.push(lo0,hi0);
 let lo=Math.min(...xs),hi=Math.max(...xs);if(v.centred||o.scl==='z'){lo=Math.min(lo,0);hi=Math.max(hi,0)}
 const p=(hi-lo)*.06||1;return [lo-p,hi+p];
}
function axisTicks(o,v,lo,hi,len){
 if(v.key==='__time'){const step=Math.max(1,Math.ceil(o.Q.length/Math.max(2,len/80)));const n=o.Q.length;return o.Q.map((c,i)=>[i,qlabel(c)]).filter(t=>t[0]===n-1||(t[0]%step===0&&n-1-t[0]>=step/2))}
 if(o.scl==='rank')return [0,25,50,75,100].filter(t=>t>=lo&&t<=hi).map(t=>[t,t===50?'median':fmt(t)+'th']);
 if(o.scl==='z')return niceTicks(lo,hi,6).map(t=>[t,(t>0?'+':t<0?'−':'')+fmt(Math.abs(t),1)+'σ']);
 if(o.scl==='log'){
  const c=v.centred?0:(v.median||0),k=v.scale||1,nice=x=>{if(!x)return 0;const p=10**Math.floor(Math.log10(Math.abs(x))-1);return Math.round(x/p)*p};
  const cand=[c,...[1,3,10,30,100,300,1000].flatMap(m=>[c+k*m,c-k*m])].map(nice);
  const gap=(hi-lo)*(34/Math.max(1,len)),out=[];
  for(const r of [...new Set(cand)].map(r=>[rotT(o,v,r,null),r]).filter(t=>t[0]>=lo&&t[0]<=hi).sort((a,b)=>a[0]-b[0]))if(!out.length||r[0]-out[out.length-1][0]>=gap)out.push(r);
  return out.map(([t,r])=>[t,vfmt(v,r)]);
 }
 return niceTicks(lo,hi,Math.max(3,Math.round(len/90))).map(t=>[t,vfmt(v,t)]);
}
const scaleNote=o=>({raw:'',log:' (signed log)',rank:' (rank within the period)',z:' (standard score)'}[o.scl]||'');
function trailCals(o,ent,cal,n,ks){                   // the periods up to cal where every coordinate exists, the last n
 const out=[];for(let i=o.qi.get(cal);i>=0&&out.length<n;i--){const c=o.Q[i];if(ks.every(v=>val(o,ent,v,c)!=null))out.unshift(c)}return out;
}
function curve(pts,smooth){                           // straight segments, or a Catmull-Rom curve through the points
 if(pts.length<2)return '';
 const f=p=>p[0].toFixed(1)+','+p[1].toFixed(1);
 if(!smooth||pts.length<3)return 'M'+pts.map(f).join('L');
 let d='M'+f(pts[0]);
 for(let i=0;i<pts.length-1;i++){const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||p2;
  d+=`C${(p1[0]+(p2[0]-p0[0])/6).toFixed(1)},${(p1[1]+(p2[1]-p0[1])/6).toFixed(1)} ${(p2[0]-(p3[0]-p1[0])/6).toFixed(1)},${(p2[1]-(p3[1]-p1[1])/6).toFixed(1)} ${f(p2)}`}
 return d;
}

function rotSize(ratio,minH,maxH){            // the drawing follows the page width so text stays near its real size
 const ws=document.getElementById('workspace'),cw=ws&&ws.clientWidth?ws.clientWidth:900;
 const W=Math.round(Math.max(320,Math.min(1080,cw-44)));return [W,Math.min(maxH||9999,Math.max(Math.min(minH,W),Math.round(W*ratio)))];
}
const rotScope=(P,sec)=>P.cos.filter(c=>!sec||c.s===sec);
const rotFlabel=(P,cal)=>qlabel(cal)+(P&&P.partial.has(cal)?' · early filers':'');

/* ---------- the page ---------- */
function rotationView(){
 let out=head('Rotation','How companies move through several cycles at once — profitability, growth, the stock, trading and ownership. Pick any variables for the axes, turn the 3-D box, press play to watch 16 quarters or 48 months, or let the scan find the pairs with the clearest cycle.','XBRL · PRICES · 13F');
 const g=marketGate('rotation','Rotation charts');if(!g.data)return out+g.html;
 const Pq=rotPrep(g.data);
 if(!Pq.cos.length||!Pq.quarters.length)return out+empty('No company has enough quarters yet. The figures arrive with the collector’s XBRL frames run (module market).');
 state.rview=ROT_VIEWS.some(v=>v[0]===state.rview)?state.rview:state.rview==='orbits'?'solar':'clock';
 if(state.rview==='rs'&&!state.rsSeen){state.rsSeen=1;state.rfreq='m'}       // the ranking is fresher monthly
 state.rfreq=state.rfreq==='m'&&state.rview!=='scan'?'m':'q';
 let P=Pq,mnote='';
 state.rfill=ROT_FILL.some(f=>f[0]===state.rfill)?state.rfill:'line';
 if(state.rfreq==='m'){const gm=marketGate('rotation-monthly','Monthly rotation data');
  if(gm.data){P=rotPrepMonthly(Pq,gm.data,state.rfill);if(!P.cos.length){P=Pq;state.rfreq='q';mnote=empty('No monthly prices yet; showing quarters.')}}
  else{P=Pq;mnote=gm.html}}
 const Q=P.quarters,avail=P.vars.filter(v=>v.n>0);
 const secs=Object.values(P.suns).sort((a,b)=>a.name.localeCompare(b.name));
 state.rsec=P.suns[state.rsec]?state.rsec:'';
 const has=k=>avail.some(v=>v.key===k);
 state.rx=has(state.rx)?state.rx:has('dom')?'dom':avail[0].key;
 state.ry=has(state.ry)&&state.ry!==state.rx?state.ry:has('rel')&&state.rx!=='rel'?'rel':avail.find(v=>v.key!==state.rx).key;
 state.rz=state.rz===''||has(state.rz)?state.rz:has('volz')?'volz':'';
 state.rz3=state.rz3==='__time'||(has(state.rz3)&&state.rz3!==state.rx&&state.rz3!==state.ry)?state.rz3:'__time';
 const tk=P.monthly?'rqm':'rq',trails=P.monthly?ROT_TRAIL_M:ROT_TRAIL;
 state[tk]=trails.some(t=>t[0]===state[tk])?state[tk]:P.monthly?'12':'4';
 state.rshow=['','avg','all'].includes(state.rshow)?state.rshow:'';
 state.rscl=ROT_SCALES.some(s=>s[0]===state.rscl)?state.rscl:'raw';
 state.rsm=ROT_SMOOTH.some(s=>s[0]===state.rsm)?state.rsm:'none';
 if(!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length)||state.rfn!==Q.length){state.rf=P.full;state.rfn=Q.length}
 const groups=[...new Set(avail.map(v=>v.group))];
 const varField=(id,label,value,extra=[])=>`<div class="field"><label for="${id}">${label}</label><select id="${id}">${extra.map(([k,l])=>`<option value="${esc(k)}" ${value===k?'selected':''}>${esc(l)}</option>`).join('')}${groups.map(gname=>`<optgroup label="${esc(gname)}">${options(avail.filter(v=>v.group===gname).map(v=>[v.key,v.label]),value)}</optgroup>`).join('')}</select></div>`;
 const three=state.rview==='3d';
 out+=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${state.rview==='scan'?'':field('rfreq','Frequency',[['q','Quarterly (16 quarters)'],['m','Monthly (48 months)']],state.rfreq)}${field('rsec','Sector',[['','All sectors'],...secs.map(s=>[s.id,s.name])],state.rsec)}`;
 if(['map','heat'].includes(state.rview)){state.rcol=has(state.rcol)?state.rcol:has('rel')?'rel':avail[0].key;out+=varField('rcol','Colour by',state.rcol)}
 if(!ROT_SIMPLE.has(state.rview))out+=`${varField('rx','→ Horizontal (x)',state.rx)}${varField('ry','↑ Vertical (y)',state.ry)}${three?varField('rz3','↗ Depth (z)',state.rz3,[['__time','Time — rotations become spirals']]):varField('rz','Dot size',state.rz,[['','Revenue']])}`;
 out+=`<div class="field wide"><label for="rtk">Companies to trace (up to three tickers)</label><input id="rtk" value="${esc(state.rtk||'')}" placeholder="e.g. NVDA, AMD, INTC · Enter"></div></div>`;
 if(!ROT_SIMPLE.has(state.rview))out+=`<div class="toolbar rot-display">${field('rscl','Scale',ROT_SCALES,state.rscl)}${field('rsm','Smoothing',ROT_SMOOTH,state.rsm)}${field(tk,'Trail',trails,state[tk])}${state.rview==='solar'?'':field('rshow','Dots',[['','Automatic'],['avg','Averages and traced only'],['all','Every company too']],state.rshow)}${P.monthly?field('rfill','Quarterly figures in months',ROT_FILL,state.rfill):''}</div>`;
 out+=mnote;
 const picks=String(state.rtk||'').toUpperCase().split(/[\s,]+/).filter(Boolean).slice(0,3).map(t=>P.byT.get(t)||P.byT.get(t.replace('.','-'))||P.byT.get(t.replace('-','.'))).filter(Boolean);
 const o={P,Q,qi:new Map(Q.map((c,i)=>[c,i])),x:P.V[state.rx],y:P.V[state.ry],z:three?(state.rz3==='__time'?ROT_TIME:P.V[state.rz3]):(state.rz?P.V[state.rz]:null),
  trail:+state[tk],picks,sec:state.rsec,scl:state.rscl,sm:state.rsm,sig:[P.monthly?'m':'q',state.rscl,state.rsm].join('|')};
 if(state.rview==='scan')out+=scanView(Pq,state.rsec);
 else if(state.rview==='rs')out+=rsView(P,state.rsec,picks);
 else if(state.rview==='map')out+=mapView(o);
 else if(state.rview==='heat')out+=heatView(o);
 else if(state.rview==='breadth')out+=breadthView(P,state.rsec);
 else if(state.rview==='corr')out+=corrView(Pq,state.rsec);
 else out+=state.rview==='solar'?solarView(o):three?view3d(o):clockView(o);
 out+=`<details><summary>How these charts are built</summary><p>${esc(g.data.note||'')}</p><p class="sub">Scales: “signed log” keeps small values as they are and compresses large ones (k·asinh(x/k), k = the variable's typical spread), so one outlier no longer flattens everyone else; “rank” and “standard score” place each company against all companies in the same period, which also removes market-wide swings. Smoothing uses past values only (exponential: half-life one quarter or three months; moving average: two quarters or three months), so a smoothed path never knows the future. In the monthly view the stock, volatility and volume are monthly; the quarterly figures (margins, growth, 13F, officials) are drawn in a straight line between quarter-ends — that is a drawing, not new information.</p><p class="sub">A path that circles clockwise means the vertical variable turns first and the horizontal one follows; counter-clockwise, the reverse. With the default axes, clockwise = the stock turned before profit momentum (the market anticipating). A pattern, not a forecast.</p></details>`;
 return out;
}
function rotPlayer(Q,P){
 const unit=P&&P.monthly?'months':'quarters';
 return `<div class="rot-player"><button class="action" id="rplay" type="button">${ROT.timer?'❚❚ Pause':`▶ Play ${Math.min(P&&P.monthly?48:16,Q.length)} ${unit}`}</button><input type="range" id="rframe" min="0" max="${Q.length-1}" step="1" value="${state.rf}" aria-label="Period shown"><span id="rflabel" class="rot-flabel">${esc(rotFlabel(P,Q[state.rf]))}</span></div>`;
}
function rotLayers(o){                                 // what the clock and the 3-D box draw
 const {P,picks,sec}=o,ref=picks.length?P.suns[picks[0].s]:null;
 o.cloud=state.rshow==='all'||(state.rshow===''&&!!sec&&!picks.length);
 o.layers={picks:picks.map((c,i)=>({ent:c,name:c.t,full:c.n,color:ROT_SERIES[i]})),
  ref:ref?{ent:ref,name:ref.name+' average'}:null,
  sun:!picks.length&&sec?{ent:P.suns[sec],name:P.suns[sec].name+' average'}:null,
  suns:!picks.length&&!sec?Object.values(P.suns).map(s=>({ent:s,name:s.name,id:s.id})):[],
  market:!picks.length?{ent:P.market,name:'Market average'}:null,
  cloud:o.cloud?rotScope(P,sec):[]};
 const L=o.layers;o.lines=[...L.picks,...(L.ref?[L.ref]:[]),...(L.sun?[L.sun]:[]),...L.suns,...(L.market?[L.market]:[])].map(t=>t.ent);
 return ref;
}
function rotLegend(o,ref){
 const L=o.layers,z=o.z;
 return [...L.picks.map(t=>`<span><i class="mk-key" style="background:${t.color}"></i>${esc(t.name)} <span class="muted">${esc(t.full||'')}</span></span>`),
  ref?`<span><i class="mk-key" style="background:var(--flow-dot)"></i>${esc(ref.name)} sector average</span>`:'',
  L.sun?`<span><i class="mk-key" style="background:var(--rot-1)"></i>${esc(L.sun.name)}</span>`:'',
  L.market?`<span><i class="mk-key" style="background:var(--rot-sun)"></i>Market average</span>`:'',
  L.suns.length?'<span><i class="mk-key" style="background:var(--flow-dot)"></i>Sector averages</span>':'',
  o.cloud?`<span class="muted">Small dots: every company${o.sec?' in the sector':''} that period${state.rview==='3d'?'':' (hollow: off the scale, drawn at the edge) · size: '+esc(z?vshort(z):'revenue')}</span>`:''].filter(Boolean).join('');
}
function rotTable(o){
 const {P,Q,x,y,z}=o,cal=Q[state.rf],scope=rotScope(P,o.sec);
 const rows=scope.map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p);
 exported=rows.map(({c,p})=>({ticker:c.t,name:c.n,sector:c.s,period:p.cal,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
 const zv=z&&z.key!=='__time'?z:null,xc=centreOf(o,x,cal),yc=centreOf(o,y,cal);
 const quad=c=>{const a=val(o,c,x,cal),b=val(o,c,y,cal);return a==null||b==null?'—':`${vshort(x)} ${a>=xc?'↑':'↓'} · ${vshort(y)} ${b>=yc?'↑':'↓'}`};
 let out=`<div class="section-head"><h3>${fmt(rows.length)} companies · ${esc(rotFlabel(P,cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Company',vshort(x),vshort(y),zv?vshort(zv):'Revenue','Quadrant','13F net managers'],rows.map(({c,p})=>[
  coLink(c),vcell(x,p[x.key]),vcell(y,p[y.key]),zv?vcell(zv,p[zv.key]):money(p.rev),esc(quad(c)),p.f13!=null?signed(Math.round(p.f13)):c.net13f==null?'—':signed(c.net13f)]));
}
const vcell=(v,x)=>x==null?'—':v.centred?`<span class="${x>=0?'positive':'negative'}">${vfmt(v,x)}</span>`:vfmt(v,x);

/* ---------- momentum clock ---------- */
function clockView(o){
 const ref=rotLayers(o);
 o.dom=[axisDomain(o,o.x,o.lines,o.cloud),axisDomain(o,o.y,o.lines,o.cloud)];
 ROT.ctx={Q:o.Q,P:o.P,draw:f=>clockFrame(o,f)};
 let out=`<div class="panel"><h3>Momentum clock</h3><p class="sub">→ ${esc(o.x.label)} · ↑ ${esc(o.y.label)}${esc(scaleNote(o))}${o.sm!=='none'?' · smoothed':''} · each dot one ${o.P.monthly?'month':'quarter'}, the large dot the period shown · drag the slider or press play</p>`;
 out+=rotPlayer(o.Q,o.P)+`<div id="rot-plot">${clockFrame(o,state.rf)}</div><div class="mk-legend">${rotLegend(o,ref)}</div></div>`;
 if(o.picks.length)out+=`<div class="rot-multiples">${o.picks.map((c,i)=>planar(o,c,ROT_SERIES[i],[o.x,o.y,...(o.z&&o.z.key!=='__time'?[o.z]:[])])).join('')}</div>`;
 return out+rotTable(o);
}
function clockFrame(o,f){
 const {P,Q,x,y,z,trail,layers:L}=o,cal=Q[f],[xd,yd]=o.dom,smooth=o.sm!=='none';
 const [W,H]=rotSize(.56,400,620),Lm=64,R=20,T=18,B=46;
 const cx=v=>Math.max(xd[0],Math.min(xd[1],v)),cy=v=>Math.max(yd[0],Math.min(yd[1],v));
 const sx=v=>Lm+(cx(v)-xd[0])/(xd[1]-xd[0])*(W-Lm-R),sy=v=>T+(yd[1]-cy(v))/(yd[1]-yd[0])*(H-T-B);
 const XY=(e,c)=>{const a=val(o,e,x,c),b=val(o,e,y,c);return a==null||b==null?null:[sx(a),sy(b),a,b]};
 const zr=(p,lo=2,hi=7)=>{if(z){const t=p[z.key]==null?null:(Math.max(z.lo,Math.min(z.hi,p[z.key]))-z.lo)/((z.hi-z.lo)||1);return t==null?lo:lo+(hi-lo)*t}const t=Math.log10(Math.max(1e7,p.rev||1e7));return lo+(hi-lo)*Math.min(1,Math.max(0,(t-7)/4.5))};
 const fl=(p,k)=>p._fill&&p._fill.includes(k)?(o.P.fill==='line'?' · drawn between quarter-ends':' · last reported quarter'):'';
 const tipRows=(name,full,p)=>[[name+' · '+qlabel(p.cal),full||''],[vfmt(x,p[x.key]),x.label+fl(p,x.key)],[vfmt(y,p[y.key]),y.label+fl(p,y.key)],...(z?[[vfmt(z,p[z.key]),z.label+fl(p,z.key)]]:[]),...(p.rev?[[money(p.rev),'quarterly revenue']]:[])];
 let s=`<svg class="plot mk-plot rot-clock" viewBox="0 0 ${W} ${H}" role="img" aria-label="Momentum clock for ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-14}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 axisTicks(o,y,yd[0],yd[1],H-T-B).forEach(([v,l])=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm-8}" y="${sy(v)+4}" text-anchor="end">${esc(l)}</text>`});
 axisTicks(o,x,xd[0],xd[1],W-Lm-R).forEach(([v,l])=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${esc(l)}</text>`});
 const x0=centreOf(o,x,cal),y0=centreOf(o,y,cal);
 s+=`<line class="mk-axis" x1="${sx(x0)}" x2="${sx(x0)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${Lm}" x2="${W-R}" y1="${sy(y0)}" y2="${sy(y0)}"/>`;
 const def=x.key==='dom'&&y.key==='rel',xs=vshort(x),ys=vshort(y),narrow=W<600;
 const q=def?(narrow?['Profits ↑ · beating','Profits ↑ · lagging','Profits ↓ · beating','Profits ↓ · lagging']:['Profits ↑ · beating the market','Profits ↑ · lagging','Profits ↓ · beating the market','Profits ↓ · lagging'])
  :narrow?['x ↑ · y ↑','x ↑ · y ↓','x ↓ · y ↑','x ↓ · y ↓']:[`${xs} ↑ · ${ys} ↑`,`${xs} ↑ · ${ys} ↓`,`${xs} ↓ · ${ys} ↑`,`${xs} ↓ · ${ys} ↓`];
 s+=`<text class="mk-quad" x="${W-R-4}" y="${T+12}" text-anchor="end">${esc(q[0])}</text><text class="mk-quad" x="${W-R-4}" y="${H-B-8}" text-anchor="end">${esc(q[1])}</text><text class="mk-quad" x="${Lm+6}" y="${T+12}">${esc(q[2])}</text><text class="mk-quad" x="${Lm+6}" y="${H-B-8}">${esc(q[3])}</text>`;
 const mid=o.scl==='rank'?' (lines: the median company)':o.scl==='z'?' (lines: the median company)':'';
 s+=`<text class="axis" x="${(Lm+W-R)/2}" y="${H-8}" text-anchor="middle">${esc(x.label+scaleNote(o))} →${!x.centred&&!mid&&o.scl!=='z'?' (lines: the market average)':mid}</text>`;
 s+=`<text class="axis" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">${esc(y.label+scaleNote(o))} →</text>`;
 for(const c of L.cloud){const p=c.by.get(cal),xy=p&&XY(c,cal);if(!xy)continue;
  const out=xy[2]<xd[0]||xy[2]>xd[1]||xy[3]<yd[0]||xy[3]>yd[1];            // off the scale: drawn at the edge, hollow
  s+=`<g data-tip="${tip(tipRows(c.t,c.n,p))}" tabindex="-1" class="mk-hit"><circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${zr(p,1.6,6).toFixed(1)}" class="rot-cloud${out?' rot-out':''}"/></g>`}
 const path=(cals,e,cls,style='')=>{const pts=cals.map(c=>XY(e,c)).filter(Boolean);return pts.length>1?`<path class="${cls}" style="${style}" d="${curve(pts,smooth)}"/>`:''};
 const boxes=[],label=(px_,py_,text,cls='mk-label mk-halo')=>{const w=text.length*6.8,right=px_+10+w<W-R;let lx=right?px_+9:px_-9;const b=[right?lx:lx-w,py_-20,right?lx+w:lx,py_-6];
  if(boxes.some(o=>b[0]<o[2]&&b[2]>o[0]&&b[1]<o[3]&&b[3]>o[1]))return '';boxes.push(b);return `<text class="${cls}" x="${lx}" y="${py_-9}" text-anchor="${right?'start':'end'}">${esc(text)}</text>`};
 let labels='';
 for(const t of L.suns){const tr=trailCals(o,t.ent,cal,trail,[x,y]);s+=path(tr,t.ent,'rot-ctx');const h=tr[tr.length-1],xy=h===cal&&XY(t.ent,h);if(xy){const p=t.ent.by.get(h);
  s+=`<g data-tip="${tip(tipRows(t.name,'sector average · '+fmt(p.n)+' companies',p))}" tabindex="0" class="mk-hit" data-rsec="${esc(t.id)}"><circle cx="${xy[0]}" cy="${xy[1]}" r="10" fill="transparent"/><circle cx="${xy[0]}" cy="${xy[1]}" r="4" class="mk-dot"/></g>`;labels+=label(xy[0],xy[1],t.name)}}
 for(const [t,cls,col] of [[L.ref,'rot-ref',''],[L.market,'rot-line','stroke:var(--rot-sun)'],[L.sun,'rot-line','stroke:var(--rot-1)']]){if(!t)continue;
  const tr=trailCals(o,t.ent,cal,trail,[x,y]);s+=path(tr,t.ent,cls,col);
  tr.forEach((c,i)=>{const head=i===tr.length-1&&c===cal,xy=XY(t.ent,c),p=t.ent.by.get(c);s+=`<g data-tip="${tip(tipRows(t.name,fmt(p.n)+' companies',p))}" tabindex="0" class="mk-hit"><circle cx="${xy[0]}" cy="${xy[1]}" r="${head?11:8}" fill="transparent"/><circle cx="${xy[0]}" cy="${xy[1]}" r="${head?(t===L.market?7:6):2.5}" class="${t===L.ref?'mk-dot':'rot-dot'}" style="${t===L.ref?'':'fill:'+(t===L.market?'var(--rot-sun)':'var(--rot-1)')};opacity:${head?1:(.35+.5*i/Math.max(1,tr.length-1)).toFixed(2)}"/></g>`});
  const h=tr[tr.length-1];if(h===cal&&t!==L.ref){const xy=XY(t.ent,h);labels+=label(xy[0],xy[1],t.name)}}
 for(const t of L.picks){const tr=trailCals(o,t.ent,cal,trail,[x,y]);s+=path(tr,t.ent,'rot-line','stroke:'+t.color);
  tr.forEach((c,i)=>{const head=i===tr.length-1,xy=XY(t.ent,c),p=t.ent.by.get(c);s+=`<g data-tip="${tip(tipRows(t.name,t.full,p))}" tabindex="0" class="mk-hit"><circle cx="${xy[0]}" cy="${xy[1]}" r="11" fill="transparent"/><circle cx="${xy[0]}" cy="${xy[1]}" r="${(head?zr(p,5,9):zr(p,2,5)).toFixed(1)}" class="rot-dot" style="fill:${t.color};opacity:${head?1:(.3+.55*i/Math.max(1,tr.length-1)).toFixed(2)}"/></g>`});
  const h=tr[tr.length-1];if(h){const xy=XY(t.ent,h);labels+=label(xy[0],xy[1],`${t.name} ${h===cal?'':qlabel(h)}`.trim())}}
 if(!L.picks.length&&!L.suns.length&&!L.sun&&!L.cloud.length)return empty('Pick a sector or type tickers to trace.');
 return s+labels+'</svg>';
}
function planar(o,c,color,vars){                      // the clock split into plain charts, one per variable (as reported)
 const pts=c.pts,W=300,H=120,L=44,R=8,T=10,B=22,n=pts.length,x=i=>L+i/Math.max(1,n-1)*(W-L-R);
 const at=()=>`<text class="axis" x="${L}" y="${H-6}">${esc(qlabel(pts[0].cal))}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(qlabel(pts[n-1].cal))}</text>`;
 const one=v=>{const vals=pts.map(p=>p[v.key]);const ok=vals.filter(fin);if(ok.length<2)return `<div class="rot-mini"><h4>${esc(v.label)}</h4><p class="sub">Not enough periods with this figure.</p></div>`;
  if(!v.centred||n>20){const lo=Math.min(...ok),hi=Math.max(...ok),pad=(hi-lo)*.15||1,y=a=>T+(hi+pad-a)/((hi-lo)+2*pad)*(H-T-B),pt=vals.map((a,i)=>fin(a)?[x(i),y(a)]:null).filter(Boolean);
   return `<div class="rot-mini"><h4>${esc(v.label)}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot">${[lo,hi].map(a=>`<text class="axis" x="${L-6}" y="${y(a)+4}" text-anchor="end">${esc(vfmt(v,a))}</text><line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(a)}" y2="${y(a)}"/>`).join('')}${v.centred&&lo<0&&hi>0?`<line class="mk-axis" x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}"/>`:''}<path class="rot-line" style="stroke:${color}" d="${curve(pt,o.sm!=='none')}"/>${vals.map((a,i)=>!fin(a)?'':`<circle cx="${x(i)}" cy="${y(a)}" r="${i===n-1?4.5:n>20?1.6:2.5}" style="fill:${color}"><title>${esc(qlabel(pts[i].cal))}: ${esc(vfmt(v,a))}</title></circle>`).join('')}${at()}</svg></div>`}
  const m=Math.max(.01,...ok.map(Math.abs)),mid=T+(H-T-B)/2,bw=Math.max(4,(W-L-R)/n-4);
  return `<div class="rot-mini"><h4>${esc(v.label)}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot"><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${mid}" y2="${mid}"/><text class="axis" x="${L-6}" y="${T+6}" text-anchor="end">${esc(vfmt(v,m))}</text><text class="axis" x="${L-6}" y="${H-B}" text-anchor="end">${esc(vfmt(v,-m))}</text>${vals.map((a,i)=>{if(!fin(a))return '';const h=Math.abs(a)/m*((H-T-B)/2);return `<rect x="${x(i)-bw/2}" y="${a>=0?mid-h:mid}" width="${bw}" height="${Math.max(1,h)}" rx="2" class="${a>=0?'mk-buy':'mk-sell'}"><title>${esc(qlabel(pts[i].cal))}: ${esc(vfmt(v,a))}</title></rect>`}).join('')}${at()}</svg></div>`};
 return `<div class="panel rot-card"><h3><span class="mk-key" style="background:${color}"></span> ${esc(c.t)} <span class="muted">${esc(c.n)}</span></h3>${vars.map(one).join('')}${c.net13f!=null?`<p class="sub">13F this quarter: ${signed(c.net13f)} net managers · est. ${smoney(c.usd13f)}</p>`:''}</div>`;
}

/* ---------- solar system ---------- */
function solarView(o){
 const {P,Q,x,y,sec}=o;
 o.scale=solarScale(o);
 ROT.ctx={Q,P,draw:f=>sec?sectorFrame(o,f):marketFrame(o,f)};
 let out=`<div class="panel"><h3>${sec?esc(P.suns[sec].name)+' — the sun and its planets':'Solar system — every sector orbiting the market'}</h3>`;
 out+=sec?`<p class="sub">The sun is the ${esc(P.suns[sec].name)} average for the period shown; each company is a planet. Direction: how it differs from its sector (→ higher ${esc(vshort(x))}, ↑ higher ${esc(vshort(y))})${esc(scaleNote(o))}; distance: by how much, in typical company spreads (compressed so the far ones fit). Planet colour: 13F crowding that quarter (green more managers added, red more cut).</p>`
  :`<p class="sub">The market average sits at the centre. Each sector is a sun placed by how far its average is from the market's (→ higher ${esc(vshort(x))}, ↑ higher ${esc(vshort(y))})${esc(scaleNote(o))} with a tail of its last ${fmt(o.trail)} ${P.monthly?'months':'quarters'}; its companies are moons around it. Press play to watch the suns orbit. Click a sun to open its sector.</p>`;
 out+=rotPlayer(Q,P)+`<div id="rot-plot">${ROT.ctx.draw(state.rf)}</div>`;
 out+=`<div class="mk-legend"><span><i class="mk-key" style="background:var(--rot-sun)"></i>${sec?'Sector average':'Sector suns, with their tails · the centre is the market'}</span><span><i class="mk-key mk-hot"></i>More 13F managers added</span><span><i class="mk-key" style="background:var(--flow-sell)"></i>More cut</span><span><i class="mk-key mk-dot"></i>No 13F change on file</span>${o.picks.map((c,i)=>`<span><i class="mk-key" style="background:${ROT_SERIES[i]}"></i>${esc(c.t)}</span>`).join('')}</div></div>`;
 const cal=Q[state.rf],m=P.market.by.get(cal);
 if(!sec){
  const rows=Object.values(P.suns).map(s=>({s,p:s.by.get(cal)})).filter(r=>r.p);
  exported=rows.map(({s,p})=>({sector:s.name,period:cal,companies:p.n,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
  out+=`<div class="section-head"><h3>Sector suns · ${esc(rotFlabel(P,cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Sector','Companies',vshort(x),'vs the market ('+vshort(x)+')',vshort(y),'vs the market ('+vshort(y)+')'],rows.map(({s,p})=>[`<button class="text-button" data-rsec="${esc(s.id)}"><b>${esc(s.name)}</b></button>`,fmt(p.n),vfmt(x,p[x.key]),m?vcell({...x,centred:true},p[x.key]==null||m[x.key]==null?null:p[x.key]-m[x.key]):'—',vfmt(y,p[y.key]),m?vcell({...y,centred:true},p[y.key]==null||m[y.key]==null?null:p[y.key]-m[y.key]):'—']));
 }else{
  const sp=P.suns[sec].by.get(cal),rows=rotScope(P,sec).map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p);
  exported=rows.map(({c,p})=>({ticker:c.t,name:c.n,period:cal,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
  out+=`<div class="section-head"><h3>${fmt(rows.length)} companies · ${esc(rotFlabel(P,cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Company',vshort(x),'vs the sector ('+vshort(x)+')',vshort(y),'vs the sector ('+vshort(y)+')','13F net managers'],rows.map(({c,p})=>[`<b>${esc(c.t)}</b> <span class="muted">${esc(c.n)}</span>`,vfmt(x,p[x.key]),sp?vcell({...x,centred:true},p[x.key]==null||sp[x.key]==null?null:p[x.key]-sp[x.key]):'—',vfmt(y,p[y.key]),sp?vcell({...y,centred:true},p[y.key]==null||sp[y.key]==null?null:p[y.key]-sp[y.key]):'—',p.f13!=null?signed(Math.round(p.f13)):'—']));
 }
 return out;
}
function robustSpread(a){const s=a.slice().sort((p,q)=>p-q);const v=(quantile(s,.75)-quantile(s,.25))/1.349;return v>0?v:(Math.max(...s.map(Math.abs))||1)}
function solarScale(o){                               // fixed across periods so the animation does not rescale
 const {P,Q,x,y,sec}=o,key=['solar',o.sig,x.key,y.key,sec].join('|');
 if(P.cache[key])return P.cache[key];
 const dev=(a,b,cal)=>{const ax=val(o,a,x,cal),ay=val(o,a,y,cal),bx=val(o,b,x,cal),by=val(o,b,y,cal);return ax==null||ay==null||bx==null||by==null?null:[ax-bx,ay-by]};
 let out;
 if(!sec){
  const d=[];for(const s of Object.values(P.suns))for(const cal of Q){const v=dev(s,P.market,cal);if(v)d.push(v)}
  const kx=d.length?robustSpread(d.map(v=>v[0])):1,ky=d.length?robustSpread(d.map(v=>v[1])):1;
  const D=Math.max(1,...d.map(v=>Math.hypot(v[0]/kx,v[1]/ky)))*1.05;
  const m=[];for(const c of P.cos){const s=P.suns[c.s];if(!s)continue;for(const cal of Q){const v=dev(c,s,cal);if(v)m.push(v)}}
  const mx=m.length?robustSpread(m.map(v=>v[0])):1,my=m.length?robustSpread(m.map(v=>v[1])):1;
  const Dm=Math.max(.5,quantile(m.map(v=>Math.hypot(v[0]/mx,v[1]/my)).sort((a,b)=>a-b),.95)||1);
  out={kx,ky,D,mx,my,Dm};
 }else{
  const s=P.suns[sec],m=[];for(const c of rotScope(P,sec))for(const cal of Q){const v=dev(c,s,cal);if(v)m.push(v)}
  const mx=m.length?robustSpread(m.map(v=>v[0])):1,my=m.length?robustSpread(m.map(v=>v[1])):1;
  out={mx,my,D:Math.max(.5,quantile(m.map(v=>Math.hypot(v[0]/mx,v[1]/my)).sort((a,b)=>a-b),.95)||1)};
 }
 return P.cache[key]=out;
}
function compass(W,c0x,c0y,R,x,y){
 return `<text class="mk-quad" x="${W-4}" y="${c0y-6}" text-anchor="end">higher ${esc(vshort(x))} →</text><text class="mk-quad" x="4" y="${c0y-6}">← lower</text><text class="mk-quad" x="${c0x}" y="${c0y-R-14}" text-anchor="middle">↑ higher ${esc(vshort(y))}</text><text class="mk-quad" x="${c0x}" y="${c0y+R+24}" text-anchor="middle">lower ↓</text>`;
}
function moonColor(c,p){const n=p&&p.f13!=null?p.f13:c.net13f;return n>0.5?'mk-hot':n<-0.5?'rot-sell':'mk-dot'}
function tailPath(pts,smooth,cls,style=''){return pts.length>1?`<path class="${cls}" style="${style}" d="${curve(pts,smooth)}"/>`:''}
function marketFrame(o,f){
 const {P,Q,x,y,trail,picks}=o,cal=Q[f],{kx,ky,D,mx,my,Dm}=o.scale,smooth=o.sm!=='none';
 const [W,H]=rotSize(.68,520,720),c0x=W/2,c0y=H/2+6,R=Math.min(W,H)/2-58,Rm=R*.13;
 const m0=P.market.by.get(cal);
 const posAt=(s,c)=>{const sx=val(o,s,x,c),sy=val(o,s,y,c),mx_=val(o,P.market,x,c),my_=val(o,P.market,y,c);if(sx==null||sy==null||mx_==null||my_==null)return null;
  const dx=(sx-mx_)/kx,dy=(sy-my_)/ky,d=Math.hypot(dx,dy),r=Math.pow(Math.min(1,d/D),.6)*R;return d?[c0x+dx/d*r,c0y-dy/d*r]:[c0x,c0y]};
 const moonAt=(c,s,ca)=>{const sp=posAt(s,ca),a=val(o,c,x,ca),b=val(o,c,y,ca),qa=val(o,s,x,ca),qb=val(o,s,y,ca);if(!sp||a==null||b==null||qa==null||qb==null)return null;
  const dx=(a-qa)/mx,dy=(b-qb)/my,d=Math.hypot(dx,dy);if(!d)return sp;const r=Rm*Math.min(1,Math.sqrt(d/Dm));return [sp[0]+dx/d*r,sp[1]-dy/d*r]};
 const span=Q.slice(Math.max(0,f-trail+1),f+1);
 let s=`<svg class="plot mk-plot rot-solar" viewBox="0 0 ${W} ${H}" role="img" aria-label="Sector suns around the market average, ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-16}" y="${H-16}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 [1,2,4].filter(k=>k<D).forEach(k=>{const r=Math.pow(k/D,.6)*R;s+=`<circle cx="${c0x}" cy="${c0y}" r="${r}" class="rot-ring"/><text class="axis rot-ringlabel" x="${c0x+r*.866+3}" y="${c0y+r*.5+12}">${k===1?'typical gap':k+'× typical'}</text>`});
 s+=`<line class="mk-grid" x1="${c0x-R}" x2="${c0x+R}" y1="${c0y}" y2="${c0y}"/><line class="mk-grid" x1="${c0x}" x2="${c0x}" y1="${c0y-R}" y2="${c0y+R}"/>`+compass(W,c0x,c0y,R,x,y);
 const suns=Object.values(P.suns);
 for(const sn of suns){const ps=span.map(c=>posAt(sn,c)).filter(Boolean);
  if(smooth)s+=tailPath(ps,true,'rot-tailpath');
  else for(let i=1;i<ps.length;i++)s+=`<line x1="${ps[i-1][0].toFixed(1)}" y1="${ps[i-1][1].toFixed(1)}" x2="${ps[i][0].toFixed(1)}" y2="${ps[i][1].toFixed(1)}" class="rot-tail" style="opacity:${(.15+.6*i/ps.length).toFixed(2)}"/>`}
 for(const c of P.cos){const sn=P.suns[c.s];if(!sn)continue;const mp=moonAt(c,sn,cal);if(!mp)continue;const p=c.by.get(cal);
  s+=`<g data-tip="${tip([[c.t,c.n||''],[vfmt(x,p[x.key]),x.label],[vfmt(y,p[y.key]),y.label],[p.f13==null?'—':signed(Math.round(p.f13)),'net 13F managers that quarter']])}" tabindex="-1" class="mk-hit"><circle cx="${mp[0].toFixed(1)}" cy="${mp[1].toFixed(1)}" r="1.9" class="${moonColor(c,p)} rot-moon"/></g>`}
 picks.forEach((c,i)=>{const sn=P.suns[c.s];if(!sn)return;const ps=span.map(ca=>moonAt(c,sn,ca)).filter(Boolean);
  s+=tailPath(ps,smooth,'rot-line','stroke:'+ROT_SERIES[i]);
  const h=moonAt(c,sn,cal);if(h)s+=`<circle cx="${h[0]}" cy="${h[1]}" r="5" class="rot-dot" style="fill:${ROT_SERIES[i]}"/><text class="mk-label mk-halo" x="${h[0]+8}" y="${h[1]-6}">${esc(c.t)}</text>`});
 const boxes=[];let labels='';
 const sized=n=>5+Math.min(7,Math.sqrt(n||1)*.9);
 for(const sn of suns){const sp=posAt(sn,cal);if(!sp)continue;const p=sn.by.get(cal),r=sized(p.n);
  s+=`<g data-tip="${tip([[sn.name,'sector average · '+fmt(p.n)+' companies · click to open'],[vfmt(x,p[x.key]),x.label+(m0?' (market '+vfmt(x,m0[x.key])+')':'')],[vfmt(y,p[y.key]),y.label+(m0?' (market '+vfmt(y,m0[y.key])+')':'')]])}" tabindex="0" class="mk-hit rot-click" data-rsec="${esc(sn.id)}"><circle cx="${sp[0]}" cy="${sp[1]}" r="${r+6}" fill="transparent"/><circle cx="${sp[0]}" cy="${sp[1]}" r="${r}" class="rot-sun"/></g>`;
  const t=sn.name.replace(/ (Services|Discretionary)$/,m=>m===' Discretionary'?' Disc.':''),w=t.length*6.6;
  for(const [lx,ly,anchor] of [[sp[0]+r+4,sp[1]-r+2,'start'],[sp[0]-r-4,sp[1]-r+2,'end'],[sp[0],sp[1]-r-5,'middle'],[sp[0],sp[1]+r+13,'middle']]){
   const x0=anchor==='start'?lx:anchor==='end'?lx-w:lx-w/2,b=[x0,ly-11,x0+w,ly+2];
   if(b[0]<2||b[2]>W-2||boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))continue;
   boxes.push(b);labels+=`<text class="mk-label mk-halo" style="font-size:11.5px" x="${lx}" y="${ly}" text-anchor="${anchor}">${esc(t)}</text>`;break}}
 s+=`<g data-tip="${tip([['Market average',qlabel(cal)+(m0?' · '+fmt(m0.n)+' companies':'')],...(m0?[[vfmt(x,m0[x.key]),x.label],[vfmt(y,m0[y.key]),y.label]]:[])])}" tabindex="0" class="mk-hit"><circle cx="${c0x}" cy="${c0y}" r="16" class="rot-sun rot-core"/></g><text class="mk-label mk-halo" x="${c0x}" y="${c0y+31}" text-anchor="middle">Market</text>`;
 return s+labels+'</svg>';
}
function sectorFrame(o,f){
 const {P,Q,x,y,z,trail,picks,sec}=o,cal=Q[f],sun=P.suns[sec],last=sun.by.get(cal),{D,mx,my}=o.scale,smooth=o.sm!=='none';
 const [W,H]=rotSize(.68,520,720),c0x=W/2,c0y=H/2,R=Math.min(W,H)/2-64;
 if(!last)return empty(`No ${sun.name} average for ${qlabel(cal)} (fewer than three companies).`);
 const cos=rotScope(P,sec);
 const posAt=(c,ca)=>{const a=val(o,c,x,ca),b=val(o,c,y,ca),qa=val(o,sun,x,ca),qb=val(o,sun,y,ca);if(a==null||b==null||qa==null||qb==null)return null;
  const dx=(a-qa)/mx,dy=(b-qb)/my,d=Math.hypot(dx,dy);if(!d)return [c0x,c0y];const r=R*Math.pow(Math.min(1,d/D),.6);return [c0x+dx/d*r,c0y-dy/d*r,d>D]};
 const revs=cos.map(c=>(c.by.get(cal)||{}).rev||0),maxRev=Math.max(1,...revs);
 const size=p=>z?(()=>{const t=p[z.key]==null?.3:(Math.max(z.lo,Math.min(z.hi,p[z.key]))-z.lo)/((z.hi-z.lo)||1);return 3+9*t})():3+10*Math.sqrt((p.rev||0)/maxRev);
 let s=`<svg class="plot mk-plot rot-solar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sun.name)} companies around the sector average, ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-16}" y="${H-16}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 [.5,1,2,4].filter(k=>k<D).forEach(k=>{const r=R*Math.pow(k/D,.6);s+=`<circle cx="${c0x}" cy="${c0y}" r="${r}" class="rot-ring"/><text class="axis rot-ringlabel" x="${c0x+r*.866+3}" y="${c0y+r*.5+12}">${k===1?'typical spread':k+'×'}</text>`});
 s+=`<line class="mk-grid" x1="${c0x-R}" x2="${c0x+R}" y1="${c0y}" y2="${c0y}"/><line class="mk-grid" x1="${c0x}" x2="${c0x}" y1="${c0y-R}" y2="${c0y+R}"/>`+compass(W,c0x,c0y,R,x,y);
 const planets=cos.map(c=>({c,p:c.by.get(cal),xy:posAt(c,cal)})).filter(a=>a.p&&a.xy).sort((a,b)=>(a.p.rev||0)-(b.p.rev||0));
 picks.forEach((c,i)=>{if(c.s!==sec)return;s+=tailPath(Q.slice(Math.max(0,f-trail+1),f+1).map(ca=>posAt(c,ca)).filter(Boolean),smooth,'rot-line','stroke:'+ROT_SERIES[i])});
 const zv=z&&z.key!=='__time'?z:null;
 for(const a of planets){const {c,p,xy}=a,pi=picks.indexOf(c);
  s+=`<g data-tip="${tip([[c.t,c.n||''],[vfmt(x,p[x.key]),x.label+' (sector '+vfmt(x,last[x.key])+')'],[vfmt(y,p[y.key]),y.label+' (sector '+vfmt(y,last[y.key])+')'],...(zv?[[vfmt(zv,p[zv.key]),zv.label]]:[]),[p.f13==null?'—':signed(Math.round(p.f13)),'net 13F managers that quarter'],[money(p.rev),'quarterly revenue']])}" tabindex="0" class="mk-hit"><circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${Math.max(9,size(p)+3)}" fill="transparent"/><circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${size(p).toFixed(1)}" class="${pi>=0?'rot-dot':moonColor(c,p)}" style="${pi>=0?'fill:'+ROT_SERIES[pi]:''}${xy[2]?';stroke-dasharray:2 2':''}"/></g>`}
 const named=new Set([...picks.map(c=>c.t),...planets.slice().sort((a,b)=>(b.p.rev||0)-(a.p.rev||0)).slice(0,10).map(a=>a.c.t)]),boxes=[];
 planets.filter(a=>named.has(a.c.t)).sort((a,b)=>(b.p.rev||0)-(a.p.rev||0)).forEach(a=>{const r=size(a.p),w=a.c.t.length*7.4;let lx=a.xy[0]+r+3,anchor='start';if(lx+w>W-2){lx=a.xy[0]-r-3;anchor='end'}
  const b=anchor==='start'?[lx,a.xy[1]-14,lx+w,a.xy[1]]:[lx-w,a.xy[1]-14,lx,a.xy[1]];if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))return;boxes.push(b);
  s+=`<text class="mk-label mk-halo" x="${lx}" y="${a.xy[1]-3}" text-anchor="${anchor}">${esc(a.c.t)}</text>`});
 const m=P.market.by.get(cal);
 s+=`<g data-tip="${tip([[sun.name+' average',qlabel(cal)+' · '+fmt(last.n)+' companies'],[vfmt(x,last[x.key]),x.label+(m?' (market '+vfmt(x,m[x.key])+')':'')],[vfmt(y,last[y.key]),y.label+(m?' (market '+vfmt(y,m[y.key])+')':'')]])}" tabindex="0" class="mk-hit"><circle cx="${c0x}" cy="${c0y}" r="13" class="rot-sun"/></g>`;
 return s+'</svg>';
}

/* ---------- 3-D: a box you can turn (canvas) ---------- */
function view3d(o){
 const ref=rotLayers(o);
 o.dom=[axisDomain(o,o.x,o.lines,o.cloud),axisDomain(o,o.y,o.lines,o.cloud),axisDomain(o,o.z,o.lines,o.cloud)];
 ROT.ctx={Q:o.Q,P:o.P,paint:f=>paint3d(o,f)};
 const time=o.z.key==='__time';
 let out=`<div class="panel"><h3>3-D${time?' — time as depth':''}</h3><p class="sub">→ ${esc(o.x.label)} · ↑ ${esc(o.y.label)} · ↗ ${esc(time?(o.P.monthly?'months':'quarters')+', oldest at the back':o.z.label)}${esc(scaleNote(o))}${o.sm!=='none'?' · smoothed':''}. ${time?'A company that keeps rotating through the same cycle draws a spiral along time. ':''}Drag to turn, hover a dot for its numbers.</p>`;
 out+=rotPlayer(o.Q,o.P)+`<div class="rot-3d-wrap"><canvas id="rot-3d" class="rot-3d" role="img" aria-label="3-D chart of ${esc(o.x.label)}, ${esc(o.y.label)} and ${esc(o.z.label)}; the table below lists every value"></canvas><div class="rot-3d-tools"><button class="action" id="rspin" type="button">${ROT.spin?'Stop turning':'Turn slowly'}</button><button class="action" id="rreset" type="button">Front view</button></div></div><div class="mk-legend">${rotLegend(o,ref)}<span class="muted">Thin lines drop each traced dot to the floor so its depth is readable</span></div></div>`;
 if(o.picks.length)out+=`<div class="rot-multiples">${o.picks.map((c,i)=>planar(o,c,ROT_SERIES[i],[o.x,o.y,...(time?[]:[o.z])])).join('')}</div>`;
 return out+rotTable(o);
}
function rotColors(){
 const css=getComputedStyle(document.documentElement),g=n=>(css.getPropertyValue(n)||'').trim();
 return {ink:g('--ink-2')||'#3d3c39',muted:g('--muted')||'#6b6a66',line:g('--line')||'#dedcd5',dot:g('--flow-dot')||'#9b9a94',sun:g('--rot-sun')||'#eda100',
  buy:g('--flow-buy')||'#17734a',sell:g('--flow-sell')||'#ea6a52',surface:g('--surface')||'#fcfcfb',series:[g('--rot-1')||'#2a78d6',g('--rot-2')||'#eb6834',g('--rot-3')||'#1baf7a']};
}
function paint3d(o,f){
 const cv=document.getElementById('rot-3d');if(!cv||!cv.getContext)return;
 const ctx=cv.getContext('2d');if(!ctx)return;
 const cw=cv.clientWidth||900,ch=Math.round(Math.max(360,Math.min(640,cw*.62))),dpr=window.devicePixelRatio||1;
 if(cv.width!==Math.round(cw*dpr)||cv.height!==Math.round(ch*dpr)){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.height=ch+'px'}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,cw,ch);
 const C=rotColors(),{P,Q,x,y,z,trail,layers:L}=o,cal=Q[f],time=z.key==='__time',[xd,yd,zd]=o.dom;
 const nrm=(v,d)=>Math.max(-1.08,Math.min(1.08,(v-d[0])/(d[1]-d[0])*2-1));
 const cy_=Math.cos(ROT.yaw),sy_=Math.sin(ROT.yaw),cp=Math.cos(ROT.pitch),sp=Math.sin(ROT.pitch),S=Math.min(cw*.9,ch)*.26,c0x=cw/2,c0y=ch/2-ch*.03,Dz=6.5;
 const proj=(X,Y,Z)=>{const x1=X*cy_-Z*sy_,z1=X*sy_+Z*cy_,y2=Y*cp-z1*sp,z2=Y*sp+z1*cp,k=Dz/(Dz-z2);return [c0x+x1*k*S,c0y-y2*k*S,z2,k]};
 const XYZ=(e,c)=>{const a=val(o,e,x,c),b=val(o,e,y,c),d=val(o,e,z,c);return a==null||b==null||d==null?null:[nrm(a,xd),nrm(b,yd),nrm(d,zd)]};
 const line=(a,b,col,w=1,alpha=1,dash)=>{const p=proj(...a),q=proj(...b);ctx.globalAlpha=alpha;ctx.strokeStyle=col;ctx.lineWidth=w;ctx.setLineDash(dash||[]);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1};
 const text=(pt,str,col,align='center',font='11px')=>{const p=proj(...pt);ctx.fillStyle=col;ctx.font=`${font} ${getComputedStyle(document.body).fontFamily||'sans-serif'}`;ctx.textAlign=align;ctx.fillText(str,p[0],p[1])};
 // the box, the floor grid and the axes through the centre lines
 const E=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
 for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]])line(E[a],E[b],C.line,1);
 for(let i=-1;i<=1;i+=.5){line([i,-1,-1],[i,-1,1],C.line,.7,.7);line([-1,-1,i],[1,-1,i],C.line,.7,.7)}
 const x0=nrm(centreOf(o,x,cal),xd),y0=nrm(centreOf(o,y,cal),yd),z0=time?nrm(o.qi.get(cal),zd):nrm(centreOf(o,z,cal),zd);
 line([-1,y0,z0],[1,y0,z0],C.muted,1,.6);line([x0,-1,z0],[x0,1,z0],C.muted,1,.6);if(!time)line([x0,y0,-1],[x0,y0,1],C.muted,1,.6);
 if(time){const sl=[[-1,-1,z0],[1,-1,z0],[1,1,z0],[-1,1,z0]];for(let i=0;i<4;i++)line(sl[i],sl[(i+1)%4],C.sun,1.2,.55,[4,3])}
 const tx=axisTicks(o,x,xd[0],xd[1],S*2),ty=axisTicks(o,y,yd[0],yd[1],S*2),tz=axisTicks(o,z,zd[0],zd[1],S*2);
 const ends=t=>t.length>2?[t[0],t[t.length-1]]:t;
 for(const [v,l] of ends(tx))text([nrm(v,xd),-1.12,1.12],l,C.muted);
 for(const [v,l] of ends(ty))text([-1.12,nrm(v,yd),1.12],l,C.muted,'right');
 for(const [v,l] of ends(tz))text([1.14,-1.12,nrm(v,zd)],l,C.muted,'left');
 text([0,-1.3,1.12],vshort(x)+' →',C.ink,'center','600 12px');text([-1.18,1.12,1.0],'↑ '+vshort(y),C.ink,'right','600 12px');text([1.22,-1.28,0],time?'time →':vshort(z)+' →',C.ink,'left','600 12px');
 // the marks: trails first, then dots far to near
 const hits=[],dots=[];
 const sizeOf=p=>{const t=Math.log10(Math.max(1e7,(p&&p.rev)||1e7));return 1.6+3.4*Math.min(1,Math.max(0,(t-7)/4.5))};
 const tipFor=(name,full,p)=>[[name+' · '+qlabel(p.cal),full||''],[vfmt(x,p[x.key]),x.label],[vfmt(y,p[y.key]),y.label],...(time?[]:[[vfmt(z,p[z.key]),z.label]])];
 const n=time?Math.max(trail,Q.length):trail;
 const trace=(e,col,w,name,full,head,drop)=>{const cals=trailCals(o,e,cal,n,[x,y,z]);if(!cals.length)return;
  const pts=cals.map(c=>XYZ(e,c));ctx.strokeStyle=col;ctx.lineWidth=w;
  for(let i=1;i<pts.length;i++){const a=proj(...pts[i-1]),b=proj(...pts[i]);ctx.globalAlpha=.25+.7*i/pts.length;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}
  ctx.globalAlpha=1;
  cals.forEach((c,i)=>{const pr=proj(...pts[i]),isHead=i===cals.length-1&&c===cal,p=e.by.get(c);dots.push({x:pr[0],y:pr[1],d:pr[2],r:(isHead?head:2)*pr[3],col,alpha:isHead?1:.35+.5*i/cals.length,rows:tipFor(name,full,p),stroke:isHead})});
  const h=pts[pts.length-1];if(drop&&cals[cals.length-1]===cal)line(h,[h[0],-1,h[2]],col,1,.5,[2,3]);
  if(cals[cals.length-1]===cal){const pr=proj(...h);dots.push({label:name,x:pr[0],y:pr[1],d:pr[2]+.001,col})}};
 for(const c of L.cloud){const p=c.by.get(cal),q=p&&XYZ(c,cal);if(!q)continue;const pr=proj(...q);dots.push({x:pr[0],y:pr[1],d:pr[2],r:sizeOf(p)*pr[3],col:C.dot,alpha:.5,rows:tipFor(c.t,c.n,p)})}
 for(const t of L.suns)trace(t.ent,L.cloud.length?C.muted:C.dot,1.2,t.name,'sector average',4,false);
 if(L.ref)trace(L.ref.ent,C.dot,1.5,L.ref.name,'',4,false);
 if(L.market)trace(L.market.ent,C.sun,2.2,'Market','average',7,true);
 if(L.sun)trace(L.sun.ent,C.series[0],2.2,L.sun.name,'',6,true);
 L.picks.forEach((t,i)=>trace(t.ent,C.series[i],2.2,t.name,t.full,6,true));
 dots.sort((a,b)=>a.d-b.d);
 const boxes=[];
 for(const d of dots){
  if(d.label){ctx.font=`500 12px ${getComputedStyle(document.body).fontFamily||'sans-serif'}`;const w=ctx.measureText(d.label).width,b=[d.x+8,d.y-20,d.x+12+w,d.y-6];
   if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))continue;boxes.push(b);
   ctx.lineWidth=3;ctx.strokeStyle=C.surface;ctx.textAlign='left';ctx.strokeText(d.label,d.x+9,d.y-9);ctx.fillStyle=C.ink;ctx.fillText(d.label,d.x+9,d.y-9);continue}
  ctx.globalAlpha=d.alpha;ctx.fillStyle=d.col;ctx.beginPath();ctx.arc(d.x,d.y,Math.max(1,d.r),0,Math.PI*2);ctx.fill();
  if(d.stroke){ctx.globalAlpha=1;ctx.lineWidth=1.5;ctx.strokeStyle=C.surface;ctx.stroke()}
  ctx.globalAlpha=1;hits.push(d)}
 ctx.font=`700 40px ${getComputedStyle(document.body).fontFamily||'sans-serif'}`;ctx.textAlign='right';ctx.fillStyle=C.ink;ctx.globalAlpha=.08;ctx.fillText(qlabel(cal),cw-14,ch-14);ctx.globalAlpha=1;
 ROT.hits=hits;
}
function rotTip(rows,x,y){
 let el=document.getElementById('mk-tip');
 if(!el){el=document.createElement('div');el.id='mk-tip';el.className='mk-tip';el.setAttribute('role','tooltip');document.body.appendChild(el)}
 if(!rows){el.style.display='none';return}
 el.replaceChildren(...rows.map(([v,l],i)=>{const d=document.createElement('div');d.className=i?'tt-row':'tt-head';const s=document.createElement('strong');s.textContent=v;d.appendChild(s);if(l){const sp=document.createElement('span');sp.textContent=' '+l;d.appendChild(sp)}return d}));
 el.style.display='block';const w=el.offsetWidth,h=el.offsetHeight;el.style.left=Math.max(8,Math.min(innerWidth-w-8,x+14))+'px';el.style.top=Math.max(8,y-h-12)+'px';
}
function bind3d(){
 const cv=document.getElementById('rot-3d');if(!cv||!cv.addEventListener)return;
 let drag=null;
 const repaint=()=>ROT.ctx&&ROT.ctx.paint&&ROT.ctx.paint(state.rf);
 cv.onpointerdown=e=>{drag=[e.clientX,e.clientY,ROT.yaw,ROT.pitch];cv.setPointerCapture&&cv.setPointerCapture(e.pointerId);rotTip(null)};
 cv.onpointerup=cv.onpointercancel=()=>{drag=null};
 cv.onpointermove=e=>{
  if(drag){ROT.yaw=drag[2]+(e.clientX-drag[0])*.01;ROT.pitch=Math.max(-1.4,Math.min(1.4,drag[3]+(e.clientY-drag[1])*.01));repaint();return}
  const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=12;
  for(const h of ROT.hits){const d=Math.hypot(h.x-mx,h.y-my)-h.r;if(d<bd){bd=d;best=h}}
  rotTip(best?best.rows:null,e.clientX,e.clientY)};
 cv.onpointerleave=()=>rotTip(null);
 if($('rspin'))$('rspin').onclick=()=>{ROT.spin=!ROT.spin;$('rspin').textContent=ROT.spin?'Stop turning':'Turn slowly';if(ROT.spin)spin()};
 if($('rreset'))$('rreset').onclick=()=>{ROT.yaw=-.75;ROT.pitch=.38;repaint()};
 repaint();
 if(ROT.spin)spin();
}
const rotReduced=()=>typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function spin(){
 if(rotReduced()){ROT.spin=false;ROT.yaw+=Math.PI/8;ROT.ctx&&ROT.ctx.paint&&ROT.ctx.paint(state.rf);if($('rspin'))$('rspin').textContent='Turn 22°';return}   // reduced motion: one step per click
 if(ROT.spinning)return;ROT.spinning=true;
 const step=()=>{if(!ROT.spin||state.tab!=='rotation'||!document.getElementById('rot-3d')||!ROT.ctx||!ROT.ctx.paint){ROT.spinning=false;return}
  ROT.yaw+=.006;ROT.ctx.paint(state.rf);requestAnimationFrame(step)};
 requestAnimationFrame(step);
}
const coLink=c=>`<a href="../#c-${esc(c.cik)}" title="Earnings Sankey and filings"><b>${esc(c.t)}</b></a> <span class="muted">${esc(c.n)}</span>`;

/* ---------- diverging colour (blue = higher / better, red = lower, grey = middle), five steps per arm ---------- */
function divColor(t){                                    // t in [-1, 1]
 if(t==null||!Number.isFinite(t))return 'var(--div-none)';
 const k=Math.round(Math.max(-1,Math.min(1,t))*5);if(!k)return 'var(--div-mid)';
 return `color-mix(in oklab, var(${k>0?'--div-pos':'--div-neg'}) ${Math.abs(k)*18+8}%, var(--div-mid))`;
}
function divT(v,x,cal,P){                              // a value → [-1, 1]: centred variables against zero, levels against the period's median
 if(x==null)return null;
 if(v.key==='rs')return (x-50)/40;
 if(v.key==='hi52')return Math.max(-1,x/25+0.6);
 const st=v.centred?null:crossStats(P,v.key,cal),c=v.centred?0:(st?st.med:v.median||0),k=(v.scale||1)*1.5;
 return (x-c)/k;
}
function divLegend(v){
 const lo=v.key==='rs'?'weak':v.centred?'below zero':'below the median',hi=v.key==='rs'?'strong':v.centred?'above zero':'above the median';
 return `<div class="mk-legend rot-divlegend"><span class="muted">${esc(lo)}</span>${[-1,-.6,-.2,0,.2,.6,1].map(t=>`<i class="mk-key" style="background:${divColor(t)}"></i>`).join('')}<span class="muted">${esc(hi)}</span><span class="muted">· grey: no figure</span></div>`;
}

/* ---------- market map: a treemap of every company, grouped by sector, sized by revenue ---------- */
function squarify(items,x,y,w,h){                      // items [{v,...}] sorted desc → rects (Bruls et al.)
 const out=[],total=items.reduce((s,i)=>s+i.v,0);if(!total||w<=0||h<=0)return out;
 const scale=w*h/total;let rest=items.map(i=>({...i,a:i.v*scale}));
 while(rest.length){
  const short=Math.min(w,h);let row=[],best=Infinity;
  for(const it of rest){const r=[...row,it],s=r.reduce((a,b)=>a+b.a,0),mx=Math.max(...r.map(q=>q.a)),mn=Math.min(...r.map(q=>q.a));
   const worst=Math.max(short*short*mx/(s*s),(s*s)/(short*short*mn));if(worst>best)break;best=worst;row=r}
  const s=row.reduce((a,b)=>a+b.a,0);
  if(w>=h){const cw=s/h;let cy=y;for(const it of row){const ch=it.a/cw;out.push({...it,x,y:cy,w:cw,h:ch});cy+=ch}x+=cw;w-=cw}
  else{const ch=s/w;let cx=x;for(const it of row){const cw2=it.a/ch;out.push({...it,x:cx,y,w:cw2,h:ch});cx+=cw2}y+=ch;h-=ch}
  rest=rest.slice(row.length);
 }
 return out;
}
function mapView(o){
 const {P,Q}=o,v=P.V[state.rcol];
 ROT.ctx={Q,P,draw:f=>mapFrame(o,v,f)};
 let out=`<div class="panel"><h3>Market map</h3><p class="sub">Every company as a tile, grouped by sector; tile size = quarterly revenue, colour = ${esc(v.label)} for the period shown. Press play to watch the map change.</p>`;
 out+=rotPlayer(Q,P)+`<div id="rot-plot">${mapFrame(o,v,state.rf)}</div>${divLegend(v)}</div>`;
 const cal=Q[state.rf],rows=rotScope(P,o.sec).map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p&&r.p.rev);
 exported=rows.map(({c,p})=>({ticker:c.t,name:c.n,sector:c.s,period:cal,revenue:p.rev,[v.key]:p[v.key]}));
 return out+`<div class="section-head"><h3>${fmt(rows.length)} companies · ${esc(rotFlabel(P,cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`
  +table(['Company','Sector','Revenue (quarter)',vshort(v)],rows.sort((a,b)=>b.p.rev-a.p.rev).map(({c,p})=>[coLink(c),esc((P.suns[c.s]||{}).name||c.s),money(p.rev),vcell(v,p[v.key])]));
}
function mapFrame(o,v,f){
 const {P,Q,sec}=o,cal=Q[f],[W,H]=rotSize(.6,420,640);
 const groups=Object.values(P.suns).filter(s=>!sec||s.id===sec).map(s=>{const kids=rotScope(P,s.id).map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p&&r.p.rev>0).map(r=>({...r,v:Math.sqrt(r.p.rev)}));
  return {s,kids:kids.sort((a,b)=>b.v-a.v),v:kids.reduce((a,b)=>a+b.v,0)}}).filter(g=>g.v>0).sort((a,b)=>b.v-a.v);
 if(!groups.length)return empty('No company has revenue for this period.');
 let s=`<svg class="plot mk-plot rot-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Market map for ${esc(qlabel(cal))}; the table below lists every value">`;
 for(const g of squarify(groups,0,0,W,H)){
  const hdr=g.h>40&&g.w>60?16:0;
  for(const k of squarify(g.kids,g.x+1,g.y+1+hdr,g.w-2,g.h-2-hdr)){const x=k.p[v.key],t=divT(v,x,cal,P);
   s+=`<g data-tip="${tip([[k.c.t,k.c.n||''],[vfmt(v,x),v.label],[money(k.p.rev),'quarterly revenue · '+g.s.name]])}" tabindex="-1" class="mk-hit"><rect x="${(k.x+.5).toFixed(1)}" y="${(k.y+.5).toFixed(1)}" width="${Math.max(0,k.w-1).toFixed(1)}" height="${Math.max(0,k.h-1).toFixed(1)}" rx="2" style="fill:${divColor(t)}" class="rot-tile"/>`;
   if(k.w>34&&k.h>16){const fs=Math.max(9,Math.min(16,Math.sqrt(k.w*k.h)/5));s+=`<text class="rot-tile-label" x="${(k.x+k.w/2).toFixed(1)}" y="${(k.y+k.h/2+fs*.35-(k.h>fs*3?fs*.55:0)).toFixed(1)}" text-anchor="middle" style="font-size:${fs.toFixed(1)}px">${esc(k.c.t)}</text>`;
    if(k.h>fs*3&&k.w>44)s+=`<text class="rot-tile-value" x="${(k.x+k.w/2).toFixed(1)}" y="${(k.y+k.h/2+fs*.95).toFixed(1)}" text-anchor="middle" style="font-size:${(fs*.72).toFixed(1)}px">${esc(vfmt(v,x))}</text>`}
   s+='</g>'}
  s+=`<rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" class="rot-group"/>`;
  if(hdr)s+=`<text class="rot-group-label" x="${g.x+5}" y="${g.y+12}">${esc(g.s.name.length*6.5>g.w-10?g.s.name.slice(0,Math.max(3,Math.floor((g.w-10)/6.5)))+'…':g.s.name)}</text>`;
 }
 return s+`<text class="rot-watermark" x="${W-12}" y="${H-12}" text-anchor="end">${esc(qlabel(cal))}</text></svg>`;
}

/* ---------- sector heatmap: sectors × periods ---------- */
function heatView(o){
 const {P,Q}=o,v=P.V[state.rcol],cols=Q.slice(-(P.monthly?24:16)),secs=Object.values(P.suns).sort((a,b)=>a.name.localeCompare(b.name));
 const rel=v.centred?null:'market';
 const W=Math.max(560,rotSize(.5,300)[0]),L=150,R=10,T=26,rowH=26,H=T+(secs.length+1)*rowH+8,cw=(W-L-R)/cols.length;
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(v.label)} by sector and period; the table below lists every value">`;
 const step=Math.ceil(cols.length/(W>700?12:6));
 cols.forEach((c,i)=>{if(i%step===0||i===cols.length-1)s+=`<text class="axis" x="${L+cw*i+cw/2}" y="${T-8}" text-anchor="middle">${esc(qlabel(c).replace(/^(\w{3}) (\d{2})(\d{2})$/,'$1 $3').replace(/^Q(\d) (\d{2})(\d{2})$/,'Q$1 $3'))}</text>`});
 const rowsData=[...secs.map(sn=>({name:sn.name,id:sn.id,ent:sn})),{name:'Market',id:'',ent:P.market}];
 rowsData.forEach((r,j)=>{const y=T+j*rowH+(r.id===''?6:0);
  s+=`<text class="mk-label" x="${L-8}" y="${y+rowH/2+4}" text-anchor="end"${r.id?` data-rsec="${esc(r.id)}" style="cursor:pointer"`:''}>${esc(r.name.length>22?r.name.slice(0,21)+'…':r.name)}</text>`;
  cols.forEach((c,i)=>{const p=r.ent.by.get(c),x=p?p[v.key]:null,t=x==null?null:divT(v,x,c,P);
   s+=`<g data-tip="${tip([[r.name+' · '+qlabel(c),r.id?'sector average':'all companies'],[vfmt(v,x),v.label],...(p&&p.n?[[fmt(p.n),'companies']]:[])])}" tabindex="-1" class="mk-hit"><rect x="${(L+cw*i+1).toFixed(1)}" y="${y+1}" width="${Math.max(1,cw-2).toFixed(1)}" height="${rowH-2}" rx="2" style="fill:${divColor(t)}"/>${cw>=38?`<text class="rot-cell" x="${(L+cw*i+cw/2).toFixed(1)}" y="${y+rowH/2+4}" text-anchor="middle">${esc(x==null?'':vfmt(v,x).replace(' pts',''))}</text>`:''}</g>`})});
 s+='</svg>';
 const last=cols[cols.length-1];
 exported=rowsData.flatMap(r=>cols.map(c=>({sector:r.name,period:c,[v.key]:(r.ent.by.get(c)||{})[v.key]??null})));
 return `<div class="panel"><h3>Sector heatmap — ${esc(v.label)}</h3><p class="sub">Each cell is a sector's average for the period (revenue-weighted, outliers clipped); the bottom row is every company. Blue: ${v.centred?'above zero':'above the period\'s median company'}, red: below. Click a sector name to open it in the solar system.</p>${s}${divLegend(v)}</div>`
  +`<div class="section-head"><h3>Every cell</h3><button class="action" id="csv">Export CSV ↓</button></div>`
  +table(['Sector',...cols.slice(-6).map(qlabel)],rowsData.map(r=>[esc(r.name),...cols.slice(-6).map(c=>vcell(v,(r.ent.by.get(c)||{})[v.key]??null))]));
}

/* ---------- breadth and dispersion ---------- */
function breadthView(P,sec){
 const Q=P.quarters,cos=rotScope(P,sec),unit=P.monthly?'month':'quarter';
 const share=(test)=>Q.map(c=>{let n=0,k=0;for(const co of cos){const p=co.by.get(c);if(!p)continue;const r=test(p);if(r==null)continue;n++;if(r)k++}return n>=20?[c,100*k/n,n]:[c,null,n]});
 const iqr=Q.map(c=>{const xs=cos.map(co=>(co.by.get(c)||{}).rel).filter(fin).sort((a,b)=>a-b);return [c,xs.length>=20?quantile(xs,.75)-quantile(xs,.25):null,xs.length]});
 const series=[
  ['Share of companies beating the S&P 500 that '+unit,share(p=>p.rel==null?null:p.rel>0),'%','Above 50%: most stocks did better than the index — a broad market; below: a few large stocks carried it.'],
  ['Share within 10% of their 52-week high',share(p=>p.hi52==null?null:p.hi52>=-10),'%','How many stocks are near their highs.'],
  ['Share with positive 12–1 momentum',share(p=>p.mom121==null?null:p.mom121>0),'%','Stocks that beat the S&P 500 over the year, leaving out the last month.'],
  ['Dispersion: spread between the 25th and 75th percentile company',iqr,'pts','High: stocks went very different ways (a stock-picker’s market); low: everything moved together.']];
 exported=Q.map((c,i)=>({period:c,beating_sp500:series[0][1][i][1],near_high:series[1][1][i][1],positive_momentum:series[2][1][i][1],dispersion:series[3][1][i][1]}));
 return `<div class="explain">Market breadth across the ${fmt(cos.length)} companies${sec?' in '+esc(P.suns[sec].name):''} on Filing Flows, ${unit} by ${unit}. Breadth says how many stocks take part in a move; dispersion how differently they move.</div><div class="rot-multiples rot-breadth">${series.map(([t,d,u,note])=>`<div class="panel">${bigLine(d,t,u,note)}</div>`).join('')}</div><div class="section-head"><h3>Every ${unit}</h3><button class="action" id="csv">Export CSV ↓</button></div>`
  +table(['Period','Beating the S&P 500','Near 52-week high','Positive 12–1 momentum','Dispersion (pts)'],exported.slice().reverse().map(r=>[esc(qlabel(r.period)),r.beating_sp500==null?'—':fmt(r.beating_sp500,0)+'%',r.near_high==null?'—':fmt(r.near_high,0)+'%',r.positive_momentum==null?'—':fmt(r.positive_momentum,0)+'%',r.dispersion==null?'—':fmt(r.dispersion,1)]));
}
function bigLine(d,title,unit,note){
 const pts=d.filter(x=>x[1]!=null);if(pts.length<2)return `<h3>${esc(title)}</h3>${empty('Not enough periods yet')}`;
 const W=520,H=220,L=40,R=12,T=14,B=28,n=d.length,lo=unit==='%'?0:Math.min(...pts.map(p=>p[1]))*.9,hi=unit==='%'?100:Math.max(...pts.map(p=>p[1]))*1.08;
 const x=i=>L+i/Math.max(1,n-1)*(W-L-R),y=v=>T+(hi-v)/((hi-lo)||1)*(H-T-B);
 let s=`<h3>${esc(title)}</h3><p class="sub">${esc(note)}</p><svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">`;
 niceTicks(lo,hi,4).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-6}" y="${y(v)+4}" text-anchor="end">${fmt(v)}${unit==='%'?'%':''}</text>`});
 if(unit==='%')s+=`<line class="mk-axis" x1="${L}" x2="${W-R}" y1="${y(50)}" y2="${y(50)}"/>`;
 const idx=d.map((p,i)=>[i,p]).filter(a=>a[1][1]!=null);
 s+=`<path class="rot-line" style="stroke:var(--rot-1)" d="${curve(idx.map(([i,p])=>[x(i),y(p[1])]),false)}"/>`;
 idx.forEach(([i,p],k)=>{s+=`<g data-tip="${tip([[fmt(p[1],1)+(unit==='%'?'%':' pts'),qlabel(p[0])],[fmt(p[2]),'companies with the figure']])}" tabindex="-1" class="mk-hit"><circle cx="${x(i)}" cy="${y(p[1])}" r="9" fill="transparent"/><circle cx="${x(i)}" cy="${y(p[1])}" r="${k===idx.length-1?4.5:2.2}" style="fill:var(--rot-1)"/></g>`});
 const lastP=idx[idx.length-1];
 s+=`<text class="mk-label mk-halo" x="${x(lastP[0])-6}" y="${y(lastP[1][1])-9}" text-anchor="end">${fmt(lastP[1][1],0)}${unit==='%'?'%':' pts'}</text>`;
 s+=`<text class="axis" x="${L}" y="${H-6}">${esc(qlabel(d[0][0]))}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(qlabel(d[n-1][0]))}</text>`;
 return s+'</svg>';
}

/* ---------- how the variables move together: rank correlations ---------- */
function corrView(P,sec){
 const key='corr|'+sec;
 if(!P.cache[key]){const {qs,vars}=rotRanks(P,sec),k=vars.length,acc=Array.from({length:k},()=>Array.from({length:k},()=>[0,0,0,0,0,0]));
  for(const q of qs)for(let a=0;a<k;a++){const ra=q.r[vars[a].key];for(let b=a;b<k;b++){const rb=q.r[vars[b].key],m=acc[a][b];
   for(let i=0;i<ra.length;i++){const u=ra[i],w=rb[i];if(u==null||w==null)continue;m[0]++;m[1]+=u;m[2]+=w;m[3]+=u*u;m[4]+=w*w;m[5]+=u*w}}}
  const corr=acc.map(row=>row.map(m=>{const n=m[0];if(n<50)return null;const cv=m[5]/n-m[1]/n*m[2]/n,va=m[3]/n-(m[1]/n)**2,vb=m[4]/n-(m[2]/n)**2;return va>0&&vb>0?cv/Math.sqrt(va*vb):null}));
  for(let a=0;a<k;a++)for(let b=0;b<a;b++)corr[a][b]=corr[b][a];
  P.cache[key]={vars,corr}}
 const {vars,corr}=P.cache[key],k=vars.length,cell=Math.max(26,Math.min(44,Math.floor((rotSize(.5,300)[0]-170)/k))),L=170,T=150,W=L+k*cell+90,H=T+k*cell+10;
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Rank correlation between every pair of variables; values in the tooltips and the table">`;
 vars.forEach((v,i)=>{s+=`<text class="mk-label" x="${L-8}" y="${T+i*cell+cell/2+4}" text-anchor="end">${esc(vshort(v))}</text><text class="mk-label" transform="translate(${L+i*cell+cell/2+4} ${T-8}) rotate(-55)">${esc(vshort(v))}</text>`});
 for(let a=0;a<k;a++)for(let b=0;b<k;b++){const r=corr[a][b];
  s+=`<g data-tip="${tip([[r==null?'—':fmt(r,2),'rank correlation'],[vshort(vars[a])+' × '+vshort(vars[b]),a===b?'itself':'click to put this pair on the momentum clock']])}" tabindex="-1" class="mk-hit"${a!==b?` data-raxes="${esc(vars[b].key)}|${esc(vars[a].key)}|"`:''} style="cursor:${a!==b?'pointer':'default'}"><rect x="${L+b*cell+1}" y="${T+a*cell+1}" width="${cell-2}" height="${cell-2}" rx="2" style="fill:${a===b?'var(--div-none)':divColor(r==null?null:r/0.6)}"/>${cell>=30&&a!==b&&r!=null&&Math.abs(r)>=.05?`<text class="rot-cell" x="${L+b*cell+cell/2}" y="${T+a*cell+cell/2+4}" text-anchor="middle">${fmt(r,1).replace(/^0/,'').replace(/^-0/,'−')}</text>`:''}</g>`}
 s+='</svg>';
 const pairs=[];for(let a=0;a<k;a++)for(let b=a+1;b<k;b++)if(corr[a][b]!=null)pairs.push([vars[a],vars[b],corr[a][b]]);
 pairs.sort((p,q)=>Math.abs(q[2])-Math.abs(p[2]));
 exported=pairs.map(([a,b,r])=>({a:a.key,b:b.key,rank_correlation:r}));
 return `<div class="panel"><h3>How the variables move together</h3><p class="sub">Rank correlation of every pair, pooled over all companies and quarters (each variable ranked within its quarter). Blue: high together; red: one high when the other is low; grey: unrelated. Pairs that move together tell the same story twice — for the clock pick pairs that do not. Click a cell to plot that pair.</p>${s}${divLegend({key:'corr',centred:true})}</div>`
  +`<div class="section-head"><h3>Strongest pairs</h3><button class="action" id="csv">Export CSV ↓</button></div>`
  +table(['Variable','Variable','Rank correlation'],pairs.slice(0,25).map(([a,b,r])=>[esc(a.label),esc(b.label),`<span class="${r>=0?'positive':'negative'}">${fmt(r,2)}</span>`]));
}

/* ---------- relative strength ranking ---------- */
function rsView(P,sec,picks){
 const Q=P.quarters,f=P.full,cal=Q[f],back=P.monthly?1:1,cal0=Q[Math.max(0,f-back)],cal3=Q[Math.max(0,f-(P.monthly?3:1))];
 if(!P.V.rs||!P.V.rs.n)return empty('The relative-strength rating arrives with the next publish (it needs a year of daily closes per company).');
 const scope=rotScope(P,sec),rows=[];
 for(const c of scope){const p=c.by.get(cal);if(!p||p.rs==null)continue;const p0=c.by.get(cal0),p3=c.by.get(cal3);
  rows.push({c,p,rs:p.rs,d1:p0&&p0.rs!=null?p.rs-p0.rs:null,d3:p3&&p3.rs!=null?p.rs-p3.rs:null,f13:c.net13f,hist:Q.slice(Math.max(0,f-11),f+1).map(q=>{const x=c.by.get(q);return x?x.rs:null})})}
 state.rsort=['rs','d3','f13'].includes(state.rsort)?state.rsort:'rs';
 const key={rs:r=>-r.rs,d3:r=>-(r.d3??-999),f13:r=>-(r.f13??-999)}[state.rsort];
 rows.sort((a,b)=>key(a)-key(b)||b.rs-a.rs);
 const unit=P.monthly?'month':'quarter';
 let out=`<div class="explain">Relative strength (RS) rating: each company's stock return over the last 3, 6, 9 and 12 months (the last 3 months counting double), ranked against every company here — 99 is the strongest, 1 the weakest — as of the end of ${esc(qlabel(cal))}. It describes what the price did, not what it will do.${P.monthly?'':' Switch Frequency to monthly for a fresher rating.'}</div>`;
 out+=`<div class="toolbar">${field('rsort','Sort',[['rs','Highest rating'],['d3','Biggest rise in 3 '+(P.monthly?'months':'quarters').replace('3 quarters','a quarter')],['f13','Most 13F managers adding']],state.rsort)}</div>`;
 // sectors
 const secRows=Object.values(P.suns).map(sn=>{const xs=rotScope(P,sn.id).map(c=>(c.by.get(cal)||{}).rs).filter(v=>v!=null),x0=rotScope(P,sn.id).map(c=>(c.by.get(cal3)||{}).rs).filter(v=>v!=null);
  const avg=xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null,avg0=x0.length?x0.reduce((a,b)=>a+b,0)/x0.length:null;return {sn,avg,d:avg!=null&&avg0!=null?avg-avg0:null,n:xs.length}}).filter(r=>r.avg!=null&&r.n>=3).sort((a,b)=>b.avg-a.avg);
 out+=`<div class="charts even"><div class="panel"><h3>Sectors by average RS rating</h3><p class="sub">Bars from the middle (50): right of it, the sector's stocks have been stronger than most · ${esc(qlabel(cal))}</p>${divergingChart(secRows.map(r=>({label:r.sn.name.replace(/ (Services|Discretionary)$/,m=>m===' Discretionary'?' Disc.':''),value:r.avg-50,tip:[[r.sn.name,fmt(r.n)+' companies'],[fmt(r.avg,0),'average RS rating'],[r.d==null?'—':(r.d>=0?'+':'−')+fmt(Math.abs(r.d),0),'change since '+qlabel(cal3)]]})),{unit:'count',label:'Average RS rating by sector',format:v=>fmt(v+50,0)})}</div>`;
 out+=`<div class="panel"><h3>Strength and 13F buying</h3><p class="sub">→ RS rating · ↑ net 13F managers in the latest quarter on file (buyers − sellers) · the top-right are strong stocks institutions were adding</p>${rsScatter(rows,picks)}</div></div>`;
 exported=rows.map(r=>({ticker:r.c.t,name:r.c.n,sector:r.c.s,rs:r.rs,rs_change_1:r.d1,rs_change_3:r.d3,rel3:r.p.rel3??r.p.rel,mom121:r.p.mom121,hi52:r.p.hi52,net13f:r.f13}));
 out+=`<div class="section-head"><h3>${fmt(rows.length)} companies ranked · ${esc(qlabel(cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 const chg=v=>v==null?'—':`<span class="${v>=0?'positive':'negative'}">${v>0?'+':v<0?'−':''}${fmt(Math.abs(v),0)}</span>`;
 const rv=P.V.rel3||P.V.rel;
 out+=table(['#','Company','Sector','RS rating','RS change, 1 '+unit,...(P.monthly?['RS change, 3 months']:[]),vshort(rv),'12–1 momentum','From 52-week high','13F net managers','RS, last 12 '+unit+'s'],rows.map((r,i)=>[
  String(i+1),coLink(r.c),esc((P.suns[r.c.s]||{}).name||r.c.s),`<b>${fmt(r.rs,0)}</b>`,chg(r.d1),...(P.monthly?[chg(r.d3)]:[]),vcell(rv,r.p[rv.key]),vcell(P.V.mom121||rv,r.p.mom121),r.p.hi52==null?'—':vfmt(P.V.hi52,r.p.hi52),r.f13==null?'—':signed(r.f13),rsSpark(r.hist)]));
 return out;
}
function rsSpark(h){
 const v=h.map((x,i)=>[i,x]).filter(a=>a[1]!=null);if(v.length<2)return '—';
 const W=96,H=24,x=i=>2+i/(h.length-1)*(W-4),y=r=>H-2-(r-1)/98*(H-4);
 return `<svg class="mk-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-label="RS rating from ${v[0][1]} to ${v[v.length-1][1]}"><line x1="0" x2="${W}" y1="${y(50)}" y2="${y(50)}" class="mk-axis"/><polyline points="${v.map(([i,r])=>x(i).toFixed(1)+','+y(r).toFixed(1)).join(' ')}" class="mk-spark-line"/><circle cx="${x(v[v.length-1][0])}" cy="${y(v[v.length-1][1])}" r="2.6" class="${v[v.length-1][1]>=50?'mk-buy':'mk-sell'}"/></svg>`;
}
function rsScatter(rows,picks){
 const pts=rows.filter(r=>r.f13!=null);if(pts.length<5)return empty('No 13F changes on file for these companies yet.');
 const W=720,H=360,L=48,R=16,T=14,B=36,ys=pts.map(r=>r.f13).sort((a,b)=>a-b),lo=Math.min(-5,quantile(ys,.02)),hi=Math.max(5,quantile(ys,.98));
 const sx=v=>L+(v-1)/98*(W-L-R),sy=v=>T+(hi-Math.max(lo,Math.min(hi,v)))/(hi-lo)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="RS rating against net 13F managers; the table below lists every value">`;
 niceTicks(lo,hi,5).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-6}" y="${sy(v)+4}" text-anchor="end">${v>0?'+':''}${fmt(v)}</text>`});
 [1,25,50,75,99].forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${v}</text>`});
 s+=`<line class="mk-axis" x1="${sx(50)}" x2="${sx(50)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
 s+=`<text class="mk-quad" x="${W-R-4}" y="${T+12}" text-anchor="end">Strong · being bought</text><text class="mk-quad" x="${L+6}" y="${T+12}">Weak · being bought</text><text class="mk-quad" x="${W-R-4}" y="${H-B-8}" text-anchor="end">Strong · being sold</text><text class="mk-quad" x="${L+6}" y="${H-B-8}">Weak · being sold</text><text class="axis" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">RS rating →</text>`;
 const pk=new Set(picks.map(c=>c.t)),lab=new Set(pts.filter(r=>r.f13>0).sort((a,b)=>(b.rs*1+b.f13)-(a.rs*1+a.f13)).slice(0,8).map(r=>r.c.t));
 pts.forEach(r=>{const i=picks.findIndex(c=>c.t===r.c.t),x=sx(r.rs),y=sy(r.f13);
  s+=`<g data-tip="${tip([[r.c.t,r.c.n||''],[fmt(r.rs,0),'RS rating'],[signed(r.f13),'net 13F managers'],...(r.d3!=null?[[(r.d3>=0?'+':'−')+fmt(Math.abs(r.d3),0),'RS change']]:[])])}" tabindex="-1" class="mk-hit"><circle cx="${x}" cy="${y}" r="9" fill="transparent"/><circle cx="${x}" cy="${y}" r="${i>=0?5.5:3}" class="${i>=0?'rot-dot':r.rs>=50&&r.f13>0?'mk-hot':'rot-cloud'}" style="${i>=0?'fill:'+ROT_SERIES[i]:''}"/></g>`;
  if(i>=0||lab.has(r.c.t)){const left=x>W-R-60;s+=`<text class="mk-label mk-halo" x="${left?x-7:x+7}" y="${y-6}" text-anchor="${left?'end':'start'}">${esc(r.c.t)}</text>`}});
 return s+'</svg>';
}

/* ---------- find the best axes: an exhaustive scan ---------- */
function rotRanks(P,sec){                            // per quarter: centred percentile ranks of every variable, and next quarter's stock vs S&P
 const key='ranks|'+sec;if(P.cache[key])return P.cache[key];
 const Q=P.quarters,cos=rotScope(P,sec),vars=P.vars.filter(v=>v.n>0&&!ROT_SCAN_SKIP.has(v.key));
 const rank=vals=>{const idx=vals.map((v,i)=>[v,i]).filter(a=>a[0]!=null&&Number.isFinite(a[0])).sort((a,b)=>a[0]-b[0]),out=new Array(vals.length).fill(null),n=idx.length;
  for(let i=0;i<n;){let j=i;while(j+1<n&&idx[j+1][0]===idx[i][0])j++;const r=n>1?((i+j)/2)/(n-1)-.5:0;for(let k=i;k<=j;k++)out[idx[k][1]]=r;i=j+1}return out};
 const qs=[];
 for(let qi=0;qi<Q.length;qi++){
  const pts=cos.map(c=>c.by.get(Q[qi])),r={};
  for(const v of vars)r[v.key]=rank(pts.map(p=>p?p[v.key]:null));
  const ahead=k=>{if(qi+k>=Q.length)return null;const nx=cos.map(c=>c.by.get(Q[qi+k]));const t=nx.map((p,i)=>pts[i]&&p?p.rel:null);return {tgt:t,tr:rank(t)}};
  qs.push({cal:Q[qi],r,t1:ahead(1),t2:ahead(2)});
 }
 return P.cache[key]={qs,vars,n:cos.length};
}
function scanSorters(P,sec){
 const key='sort|'+sec;if(P.cache[key])return P.cache[key];
 const {qs,vars}=rotRanks(P,sec);
 const ic=(comp,q)=>{let n=0,sx=0,sy=0,sxx=0,syy=0,sxy=0;for(let i=0;i<comp.length;i++){const a=comp[i],b=q.tr[i];if(a==null||b==null)continue;n++;sx+=a;sy+=b;sxx+=a*a;syy+=b*b;sxy+=a*b}
  if(n<20)return null;const cv=sxy/n-sx/n*sy/n,vx=sxx/n-(sx/n)**2,vy=syy/n-(sy/n)**2;return vx>0&&vy>0?cv/Math.sqrt(vx*vy):null};
 const spread=(comp,q)=>{const a=comp.map((v,i)=>[v,q.tgt[i]]).filter(p=>p[0]!=null&&p[1]!=null).sort((p,r)=>p[0]-r[0]);if(a.length<25)return null;const k=Math.floor(a.length/5),m=s=>s.reduce((t,p)=>t+p[1],0)/s.length;return m(a.slice(-k))-m(a.slice(0,k))};
 const evalCombo=(keys,signs,withSpread=false)=>{const ics=[],sps=[],lag=keys.every(k=>ROT_PRICE.has(k))?'t1':'t2';
  for(const q0 of qs){const q=q0[lag]&&{r:q0.r,...q0[lag]};if(!q)continue;const rs=keys.map(k=>q.r[k]);const comp=rs[0].map((_,i)=>{let t=0;for(let j=0;j<rs.length;j++){const v=rs[j][i];if(v==null)return null;t+=signs[j]*v}return t});
   const c=ic(comp,q);if(c!=null){ics.push(c);if(withSpread)sps.push(spread(comp,q))}}
  if(ics.length<4)return null;
  const n=ics.length,mean=ics.reduce((a,b)=>a+b,0)/n,sd=Math.sqrt(ics.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,n-1)),h=Math.floor(n/2);
  const avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null,sp=sps.filter(v=>v!=null);
  return {keys,signs,n,lag,ic:mean,t:sd>0?mean/(sd/Math.sqrt(n)):0,hit:ics.filter(v=>v>0).length/n,early:avg(ics.slice(0,h)),late:avg(ics.slice(h)),spread:avg(sp)}};
 const singles=vars.map(v=>evalCombo([v.key],[1])).filter(Boolean);
 const sign=Object.fromEntries(singles.map(r=>[r.keys[0],r.ic>=0?1:-1]));
 const ks=singles.map(r=>r.keys[0]),rows=singles.map(r=>({...r,signs:[sign[r.keys[0]]],ic:Math.abs(r.ic),t:Math.abs(r.t),early:r.early*sign[r.keys[0]],late:r.late*sign[r.keys[0]],spread:r.spread==null?null:r.spread*sign[r.keys[0]],hit:sign[r.keys[0]]>0?r.hit:1-r.hit}));
 for(let i=0;i<ks.length;i++)for(let j=i+1;j<ks.length;j++){const r=evalCombo([ks[i],ks[j]],[sign[ks[i]],sign[ks[j]]]);if(r)rows.push(r);
  for(let k=j+1;k<ks.length;k++){const r3=evalCombo([ks[i],ks[j],ks[k]],[sign[ks[i]],sign[ks[j]],sign[ks[k]]]);if(r3)rows.push(r3)}}
 rows.sort((a,b)=>b.t-a.t);
 for(const r of rows.slice(0,25))r.spread=(evalCombo(r.keys,r.signs,true)||{}).spread;   // top − bottom fifth: only for the rows shown
 return P.cache[key]={rows,tested:rows.length,quarters:Math.max(0,...rows.map(r=>r.n))};
}
const ROT_FAMILY={om:'om',dom:'om',gm:'gm',dgm:'gm',nm:'nm',dnm:'nm',revg:'rev',reva:'rev',rel:'px',rel3:'px',rel6:'px',ret:'px',rs:'px',mom121:'px',hi52:'px'};
const sameFamily=(a,b)=>ROT_FAMILY[a]&&ROT_FAMILY[a]===ROT_FAMILY[b];   // one is built from the other: they circle by construction
function scanCycles(P,sec){
 const key='cyc|'+sec;if(P.cache[key])return P.cache[key];
 const {qs,vars}=rotRanks(P,sec),n=rotScope(P,sec).length,rows=[];
 for(let a=0;a<vars.length;a++)for(let b=a+1;b<vars.length;b++){
  const X=vars[a].key,Y=vars[b].key;if(sameFamily(X,Y))continue;let cw=0,ccw=0;const lead=[[],[],[],[]];   // x_t, y_t+1, y_t, x_t+1
  for(let i=0;i<n;i++){
   const path=[];for(const q of qs){const xv=q.r[X][i],yv=q.r[Y][i];path.push(xv!=null&&yv!=null?[xv,yv]:null)}
   const ok=path.filter(Boolean);if(ok.length<6)continue;
   const mx=ok.reduce((s,p)=>s+p[0],0)/ok.length,my=ok.reduce((s,p)=>s+p[1],0)/ok.length;let A=0;
   for(let t=0;t+1<path.length;t++){const p=path[t],q=path[t+1];if(!p||!q)continue;A+=(p[0]-mx)*(q[1]-my)-(q[0]-mx)*(p[1]-my);
    lead[0].push(p[0]-mx);lead[1].push(q[1]-my);lead[2].push(p[1]-my);lead[3].push(q[0]-mx)}
   if(A<0)cw++;else if(A>0)ccw++}
  const tot=cw+ccw;if(tot<10)continue;
  const corr=(u,v)=>{const k=u.length;if(k<10)return null;let su=0,sv=0,suu=0,svv=0,suv=0;for(let i=0;i<k;i++){su+=u[i];sv+=v[i];suu+=u[i]*u[i];svv+=v[i]*v[i];suv+=u[i]*v[i]}const c=suv/k-su/k*sv/k,vu=suu/k-(su/k)**2,vv=svv/k-(sv/k)**2;return vu>0&&vv>0?c/Math.sqrt(vu*vv):null};
  const xy=corr(lead[0],lead[1]),yx=corr(lead[2],lead[3]);
  // orient so the majority circles clockwise: then the vertical variable is the one that turns first
  const flip=ccw>cw;rows.push({x:flip?Y:X,y:flip?X:Y,cw:flip?ccw:cw,ccw:flip?cw:ccw,share:Math.max(cw,ccw)/tot,z:Math.abs(cw-ccw)/Math.sqrt(tot),
   first:flip?X:Y,lead_first:flip?xy:yx,lead_second:flip?yx:xy,companies:tot})}
 rows.sort((a,b)=>b.z-a.z);
 return P.cache[key]={rows,tested:rows.length};
}
function scanView(P,sec){
 const V=P.V,chance=n=>Math.sqrt(2*Math.log(Math.max(2,n)));
 const cyc=scanCycles(P,sec),srt=scanSorters(P,sec),cc=chance(cyc.tested),cs=chance(srt.tested);
 const name=k=>esc(vshort(V[k]));
 let out=`<div class="explain">Every combination of the ${fmt(P.vars.filter(v=>v.n>0).length)} variables was tried on ${fmt(rotScope(P,sec).length)} companies${sec?' in '+esc(P.suns[sec].name):''} over ${fmt(P.quarters.length)} quarters. Each variable is first turned into its rank among the companies that quarter, so units and market-wide swings do not matter (the raw stock return is left out: it duplicates the return against the S&P 500). <b>With this many tries the best result looks good by chance alone</b>: rows are marked “worth a look” only when they clear the chance level and hold in both halves of the period. The companies are today's largest by revenue, so firms that shrank or disappeared are missing — that flatters growth-type rankings. Past patterns, not forecasts.</div>`;
 out+=`<div class="panel"><h3>Clearest cycles — pairs for the momentum clock</h3><p class="sub">How many companies' paths circle the same way. Each pair is oriented so most paths go clockwise: the vertical variable turns first, the horizontal one follows. z: how far the clockwise count is from a coin toss (${fmt(cyc.tested)} pairs tested; chance alone reaches about ${fmt(cc,1)}; companies in one sector move together, so treat z as generous). Lead: the correlation of the vertical variable with the next quarter's horizontal one, against the other way round. Pairs where one variable is built from the other (a margin and its change, growth and its acceleration, one- and two-quarter returns) circle by construction and are left out.</p>`;
 out+=table(['Horizontal (x)','Vertical (y) — turns first','Clockwise','z','Lead y → next x','Lead x → next y','Verdict',''],cyc.rows.slice(0,20).map(r=>[name(r.x),name(r.y),`${fmt(r.share*100,0)}% of ${fmt(r.companies)}`,fmt(r.z,1),
  r.lead_first==null?'—':fmt(Math.abs(r.lead_first)<.005?0:r.lead_first,2),r.lead_second==null?'—':fmt(Math.abs(r.lead_second)<.005?0:r.lead_second,2),
  r.z>=cc?'<span class="badge ready">Worth a look</span>':'<span class="badge">Could be chance</span>',
  `<button class="text-button" data-raxes="${esc(r.x)}|${esc(r.y)}|">Show</button>`]))+'</div>';
 const dir=(k,s)=>`${s>0?'high':'low'} ${name(k)}`;
 const worth=r=>r.t>=cs&&r.early>0&&r.late>0;
 out+=`<div class="panel"><h3>Best sorters of the next quarter</h3><p class="sub">Companies ranked by one, two or three variables (equal weights, each pointing the way it worked over the whole period), then compared with how their stock did against the S&P 500 <b>once the figures were public</b>: filings, 13F and officials' reports come out weeks after a quarter ends, so a ranking on them is compared with the stock two quarters later (comparing with the very next quarter would count the earnings reaction itself); a ranking only on prices, volatility and volume is compared with the next quarter. Rank IC: the correlation between the two rankings, averaged over up to ${fmt(srt.quarters)} quarters (0 = no link; 0.05 is already notable). Top − bottom: the best-ranked fifth's return minus the worst fifth's in that quarter. ${fmt(srt.tested)} combinations tested; chance alone reaches t ≈ ${fmt(cs,1)}.</p>`;
 out+=table(['Ranked by','Compared with','Rank IC','t','Quarters right','Early half','Later half','Top − bottom fifth','Verdict',''],srt.rows.slice(0,25).map(r=>[
  r.keys.map((k,i)=>dir(k,r.signs[i])).join(' + '),r.lag==='t1'?'next quarter':'two quarters on',fmt(r.ic,3),fmt(r.t,1),`${fmt(r.hit*100,0)}%`,
  `<span class="${r.early>0?'positive':'negative'}">${fmt(r.early,3)}</span>`,`<span class="${r.late>0?'positive':'negative'}">${fmt(r.late,3)}</span>`,
  r.spread==null?'—':pp(r.spread),worth(r)?'<span class="badge ready">Worth a look</span>':'<span class="badge">Could be chance</span>',
  `<button class="text-button" data-raxes="${esc(r.keys[0])}|${esc(r.keys[1]||(r.keys[0]==='rel'?'dom':'rel'))}|${esc(r.keys[2]||'')}">Show</button>`]))+'</div>';
 exported=srt.rows.map(r=>({variables:r.keys.join('+'),directions:r.signs.join(','),compared_with:r.lag==='t1'?'next quarter':'two quarters on',quarters:r.n,rank_ic:r.ic,t:r.t,hit:r.hit,early:r.early,late:r.late,top_minus_bottom:r.spread}));
 out+=`<div class="section-head"><h3>Export</h3><button class="action" id="csv">Export every combination (CSV) ↓</button></div>`;
 return out;
}

/* ---------- events ---------- */
function rotDraw(){
 const c=ROT.ctx;if(!c)return;
 if(c.paint){if(!document.getElementById('rot-3d'))return;c.paint(state.rf)}
 else{if(!document.getElementById('rot-plot'))return;$('rot-plot').innerHTML=c.draw(state.rf)}
 if($('rframe'))$('rframe').value=state.rf;
 if($('rflabel'))$('rflabel').textContent=rotFlabel(c.P,c.Q[state.rf]);
 if($('rplay'))$('rplay').textContent=ROT.timer?'❚❚ Pause':`▶ Play ${Math.min(c.P&&c.P.monthly?48:16,c.Q.length)} ${c.P&&c.P.monthly?'months':'quarters'}`;
 if(!c.paint){bindTips();bindRotSuns()}
}
function rotStop(){if(ROT.timer){clearInterval(ROT.timer);ROT.timer=null}}
function rotToggle(){
 if(ROT.timer){rotStop();render();return}
 const c=ROT.ctx,n=c?c.Q.length:0;if(!n)return;
 const span=c.P&&c.P.monthly?48:16;
 if(state.rf>=n-1)state.rf=Math.max(0,n-span);
 ROT.timer=setInterval(()=>{
  if(state.tab!=='rotation'||!(document.getElementById('rot-plot')||document.getElementById('rot-3d'))){rotStop();return}
  if(state.rf>=n-1){rotStop();render();return}
  state.rf++;rotDraw()},(c.P&&c.P.monthly?380:850)*(rotReduced()?2.5:1));
 rotDraw();
}
function bindRotSuns(){document.querySelectorAll('#workspace [data-rsec]').forEach(b=>b.onclick=()=>{rotStop();state.rsec=b.dataset.rsec;state.rview=state.rview==='scan'?'solar':state.rview;render()})}
function bindRotation(){
 for(const k of ['rview','rsec','rx','ry','rz','rz3','rq','rqm','rshow','rscl','rsm','rfreq','rfill','rsort','rcol'])if($(k))$(k).onchange=e=>{rotStop();state[k]=e.target.value;if(k==='rx'&&state.ry===state.rx)state.ry='';render()};
 if($('rtk')){$('rtk').onchange=e=>{state.rtk=e.target.value;render()};$('rtk').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 if($('rplay'))$('rplay').onclick=rotToggle;
 if($('rframe')){$('rframe').oninput=e=>{rotStop();state.rf=+e.target.value;rotDraw()};$('rframe').onchange=e=>{state.rf=+e.target.value;render()}}
 document.querySelectorAll('#workspace [data-raxes]').forEach(b=>b.onclick=()=>{const [x,y,z]=b.dataset.raxes.split('|');state.rview='clock';state.rx=x;state.ry=y;state.rz=z||state.rz;render();scrollTo({top:0,behavior:'smooth'})});
 bindRotSuns();
 if(state.tab==='rotation')bind3d();
}
