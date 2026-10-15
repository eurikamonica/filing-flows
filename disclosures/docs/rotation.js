/* 4.4 rotation views. Data: data/market/rotation.json (app/rotation.py, built at publish). Uses the helpers of market.js.
   · Momentum clock — any two variables as x and y (a third as dot size), every company's path quarter by quarter,
     played as an animation over 16 quarters with trails.
   · Solar system — the market average at the centre, every sector a sun orbiting it (with its trail), each sector's
     companies as moons; pick a sector to see its companies as planets around their sun.
   · Find the best axes — every pair of variables scanned for the clearest cycle, and every single, pair and triple
     scanned for how well it sorted the next quarter's stock moves (with a split-half check and the chance level). */
const ROT_SERIES=['var(--rot-1)','var(--rot-2)','var(--rot-3)'];
const ROT_TRAIL=[['4','4 quarters'],['8','8 quarters'],['12','12 quarters'],['16','16 quarters']];
const ROT_VIEWS=[['clock','Momentum clock'],['solar','Solar system'],['scan','Find the best axes']];
const ROT_SHORT={dom:'Op. margin Δ',om:'Op. margin',dgm:'Gross margin Δ',gm:'Gross margin',dnm:'Net margin Δ',nm:'Net margin',revg:'Revenue growth',reva:'Growth acceleration',rel:'Stock vs S&P',rel6:'Stock vs S&P, 6 mo',ret:'Stock return',vola:'Volatility',volz:'Volume',f13:'13F net managers',gov:'Officials net buys'};
const ROT_DEFAULT_VARS=[{key:'dom',label:'Operating margin vs a year earlier',unit:'pts',centred:true,group:'Profitability'},{key:'rel',label:'Stock vs the S&P 500, the quarter',unit:'%',centred:true,group:'Price'},{key:'volz',label:'Trading volume vs its own average',unit:'%',centred:true,group:'Trading'}];
const ROT={timer:null,ctx:null};
// when a variable is public: price-based ones at the quarter's last close; figures from 10-Q / 10-K, 13F and officials'
// reports only weeks after the quarter ends — so the scan compares those with the stock two quarters later, not the next
const ROT_PRICE=new Set(['rel','rel6','ret','vola','volz']);
const ROT_SCAN_SKIP=new Set(['ret']);           // the raw return duplicates the return against the S&P 500 in a scan
const qlabel=c=>String(c||'').replace(/^CY(\d{4})Q(\d)$/,'Q$2 $1');
function niceTicks(lo,hi,n=5){const raw=(hi-lo)/n,p=10**Math.floor(Math.log10(raw||1)),st=[1,2,2.5,5,10].map(m=>m*p).find(x=>x>=raw);const out=[];for(let v=Math.ceil(lo/st)*st;v<=hi+1e-9;v+=st)out.push(+v.toFixed(6));return out}
const pp=v=>v==null?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),1)+' pts';
const vshort=v=>v?(ROT_SHORT[v.key]||v.label):'';
function vfmt(v,x){
 if(x==null||!Number.isFinite(+x))return '—';
 const u=v&&v.unit,s=x>0?'+':x<0?'−':'',a=Math.abs(x);
 if(u==='pts')return s+fmt(a,1)+' pts';
 if(u==='%')return v.centred?s+fmt(a,1)+'%':(x<0?'−':'')+fmt(a,1)+'%';
 if(u==='managers'||u==='trades')return s+fmt(a,0);
 return fmt(x,1);
}
const quantile=(xs,q)=>xs.length?xs[Math.min(xs.length-1,Math.max(0,Math.floor(q*(xs.length-1))))]:null;

/* ---------- data: columnar rows → objects, once per file ---------- */
function rotPrep(d){
 if(d._prep)return d._prep;
 const F=d.fields,SF=d.sun_fields,row=(fields,r)=>{const o={};fields.forEach((k,i)=>{o[k]=r[i]});return o};
 const fix=p=>({...p,rel:p.rel==null?null:p.rel*100,ret:p.ret==null?null:p.ret*100,volz:p.volz==null?null:p.volz*100});   // first file format
 const cos=(d.companies||[]).map(c=>{const pts=F?(c.p||[]).map(r=>row(F,r)):(c.pts||[]).map(fix);return {...c,pts,by:new Map(pts.map(p=>[p.cal,p]))}});
 const suns={};
 for(const [k,v] of Object.entries(d.sectors||{})){const pts=SF?(v.p||[]).map(r=>row(SF,r)):(v.pts||[]).map(fix);if(pts.length)suns[k]={id:k,name:v.name,pts,by:new Map(pts.map(p=>[p.cal,p]))}}
 const vars=(d.vars&&d.vars.length?d.vars:ROT_DEFAULT_VARS).map(v=>({...v}));
 for(const v of vars){                               // older files carry no bounds: derive them
  const xs=cos.flatMap(c=>c.pts.map(p=>p[v.key])).filter(x=>x!=null&&Number.isFinite(x)).sort((a,b)=>a-b);
  if(v.n==null)v.n=xs.length;
  if(v.lo==null&&xs.length){v.lo=quantile(xs,.03);v.hi=quantile(xs,.97);v.median=quantile(xs,.5)}
  if(!v.scale&&xs.length){const s=(quantile(xs,.75)-quantile(xs,.25))/1.349;v.scale=s>0?s:((v.hi-v.lo)/4||1)}
 }
 const V=Object.fromEntries(vars.map(v=>[v.key,v]));
 const quarters=d.quarters&&d.quarters.length?d.quarters:[...new Set(cos.flatMap(c=>c.pts.map(p=>p.cal)))].sort();
 let market;
 if(d.market&&SF)market={id:'market',name:'Market',pts:(d.market.p||[]).map(r=>row(SF,r))};
 else market={id:'market',name:'Market',pts:quarters.map(cal=>{const ps=cos.map(c=>c.by.get(cal)).filter(Boolean),o={cal,n:ps.length};
  for(const v of vars){const xs=ps.map(p=>p[v.key]).filter(x=>x!=null).map(x=>Math.max(v.lo,Math.min(v.hi,x)));o[v.key]=xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null}return o}).filter(p=>p.n>=3)};
 market.by=new Map(market.pts.map(p=>[p.cal,p]));
 // the newest quarters are only partly reported (10-Qs arrive over six weeks): start on the last well-covered one
 const most=Math.max(0,...market.pts.map(p=>p.n||0)),partial=new Set(quarters.filter(c=>((market.by.get(c)||{}).n||0)<.5*most));
 let full=quarters.length-1;while(full>0&&partial.has(quarters[full]))full--;
 return d._prep={cos,suns,market,vars,V,quarters,partial,full,byT:new Map(cos.map(c=>[c.t,c])),cache:{}};
}
const rotClip=(v,x)=>x==null?null:Math.max(v.lo,Math.min(v.hi,x));
function rotSize(ratio,minH,maxH){            // the drawing follows the page width so text stays near its real size
 const ws=document.getElementById('workspace'),cw=ws&&ws.clientWidth?ws.clientWidth:900;
 const W=Math.round(Math.max(320,Math.min(1080,cw-44)));return [W,Math.min(maxH||9999,Math.max(Math.min(minH,W),Math.round(W*ratio)))];
}

/* ---------- the page ---------- */
function rotationView(){
 let out=head('Rotation','How companies move through several cycles at once — profitability, growth, the stock, trading and ownership — quarter by quarter. Pick any two variables for the axes and a third for dot size, press play to watch 16 quarters, or let the scan find the pairs with the clearest cycle.','XBRL · PRICES · 13F');
 const g=marketGate('rotation','Rotation charts');if(!g.data)return out+g.html;
 const P=rotPrep(g.data),Q=P.quarters,avail=P.vars.filter(v=>v.n>0);
 if(!P.cos.length||!Q.length)return out+empty('No company has enough quarters yet. The figures arrive with the collector’s XBRL frames run (module market).');
 const secs=Object.values(P.suns).sort((a,b)=>a.name.localeCompare(b.name));
 state.rview=ROT_VIEWS.some(v=>v[0]===state.rview)?state.rview:state.rview==='orbits'?'solar':'clock';
 state.rsec=P.suns[state.rsec]?state.rsec:'';
 const has=k=>avail.some(v=>v.key===k);
 state.rx=has(state.rx)?state.rx:has('dom')?'dom':avail[0].key;
 state.ry=has(state.ry)&&state.ry!==state.rx?state.ry:has('rel')&&state.rx!=='rel'?'rel':avail.find(v=>v.key!==state.rx).key;
 state.rz=state.rz===''||has(state.rz)?state.rz:has('volz')?'volz':'';
 state.rq=['4','8','12','16'].includes(state.rq)?state.rq:'4';
 state.rshow=['','avg','all'].includes(state.rshow)?state.rshow:'';
 state.rf=Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length?state.rf:P.full;
 const groups=[...new Set(avail.map(v=>v.group))];
 const varField=(id,label,value,blank)=>`<div class="field"><label for="${id}">${label}</label><select id="${id}">${blank?`<option value="" ${value===''?'selected':''}>${esc(blank)}</option>`:''}${groups.map(gname=>`<optgroup label="${esc(gname)}">${options(avail.filter(v=>v.group===gname).map(v=>[v.key,v.label]),value)}</optgroup>`).join('')}</select></div>`;
 out+=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${field('rsec','Sector',[['','All sectors'],...secs.map(s=>[s.id,s.name])],state.rsec)}`;
 if(state.rview!=='scan')out+=`${varField('rx','→ Horizontal (x)',state.rx)}${varField('ry','↑ Vertical (y)',state.ry)}${varField('rz','Dot size (z)',state.rz,'Revenue')}${field('rq','Trail',ROT_TRAIL,state.rq)}${state.rview==='clock'?field('rshow','Dots',[['','Automatic'],['avg','Averages and traced only'],['all','Every company too']],state.rshow):''}`;
 out+=`<div class="field wide"><label for="rtk">Companies to trace (up to three tickers)</label><input id="rtk" value="${esc(state.rtk||'')}" placeholder="e.g. NVDA, AMD, INTC · Enter"></div></div>`;
 const picks=String(state.rtk||'').toUpperCase().split(/[\s,]+/).filter(Boolean).slice(0,3).map(t=>P.byT.get(t)||P.byT.get(t.replace('.','-'))||P.byT.get(t.replace('-','.'))).filter(Boolean);
 const o={P,Q,x:P.V[state.rx],y:P.V[state.ry],z:state.rz?P.V[state.rz]:null,trail:+state.rq,picks,sec:state.rsec};
 if(state.rview==='scan')out+=scanView(P,state.rsec);
 else out+=state.rview==='solar'?solarView(o):clockView(o);
 out+=`<details><summary>How these charts are built</summary><p>${esc(g.data.note||'')}</p><p class="sub">A path that circles clockwise means the vertical variable turns first and the horizontal one follows a quarter or two later; counter-clockwise, the reverse. With the default axes, clockwise = the stock turned before profit momentum (the market anticipating); counter-clockwise = profits turned first and the price caught up. A pattern, not a forecast.</p></details>`;
 return out;
}
const rotFlabel=(P,cal)=>qlabel(cal)+(P&&P.partial.has(cal)?' · early filers':'');
function rotPlayer(Q,P){
 return `<div class="rot-player"><button class="action" id="rplay" type="button">${ROT.timer?'❚❚ Pause':`▶ Play ${Math.min(16,Q.length)} quarters`}</button><input type="range" id="rframe" min="0" max="${Q.length-1}" step="1" value="${state.rf}" aria-label="Quarter shown"><span id="rflabel" class="rot-flabel">${esc(rotFlabel(P,Q[state.rf]))}</span></div>`;
}
const rotScope=(P,sec)=>P.cos.filter(c=>!sec||c.s===sec);
function trailOf(pts,cal,n,x,y){const t=pts.filter(p=>p.cal<=cal&&p[x.key]!=null&&p[y.key]!=null);return t.slice(-n)}

/* ---------- momentum clock ---------- */
function clockView(o){
 const {P,Q,x,y,z,picks,sec}=o;
 const scope=rotScope(P,sec);
 const ref=picks.length?P.suns[picks[0].s]:null;
 o.cloud=state.rshow==='all'||(state.rshow===''&&!!sec&&!picks.length);
 o.layers={
  picks:picks.map((c,i)=>({name:c.t,full:c.n,color:ROT_SERIES[i],pts:c.pts,co:c})),
  ref:ref?{name:ref.name+' average',pts:ref.pts}:null,
  sun:!picks.length&&sec?{name:P.suns[sec].name+' average',pts:P.suns[sec].pts}:null,
  suns:!picks.length&&!sec?Object.values(P.suns).map(s=>({name:s.name,pts:s.pts,id:s.id})):[],
  market:!picks.length?{name:'Market average',pts:P.market.pts}:null,
  cloud:o.cloud?scope:[]};
 o.dom=clockDomain(o);
 ROT.ctx={Q,P,draw:f=>clockFrame(o,f)};
 const legend=[...o.layers.picks.map(t=>`<span><i class="mk-key" style="background:${t.color}"></i>${esc(t.name)} <span class="muted">${esc(t.full||'')}</span></span>`),
  ref?`<span><i class="mk-key" style="background:var(--flow-dot)"></i>${esc(ref.name)} sector average</span>`:'',
  o.layers.sun?`<span><i class="mk-key" style="background:var(--rot-1)"></i>${esc(o.layers.sun.name)}</span>`:'',
  o.layers.market?`<span><i class="mk-key" style="background:var(--rot-sun)"></i>Market average</span>`:'',
  o.layers.suns.length?'<span><i class="mk-key" style="background:var(--flow-dot)"></i>Sector averages</span>':'',
  o.cloud?`<span class="muted">Small dots: every company${sec?' in the sector':''} that quarter (hollow: off the scale, drawn at the edge) · size: ${esc(z?vshort(z):'revenue')}</span>`:''].filter(Boolean).join('');
 let out=`<div class="panel"><h3>Momentum clock</h3><p class="sub">→ ${esc(x.label)} · ↑ ${esc(y.label)} · each dot one quarter, the large dot the quarter shown · drag the slider or press play</p>`;
 out+=rotPlayer(Q,P)+`<div id="rot-plot">${clockFrame(o,state.rf)}</div><div class="mk-legend">${legend}</div></div>`;
 if(picks.length)out+=`<div class="rot-multiples">${picks.map((c,i)=>planar(c,Q,ROT_SERIES[i],[x,y,...(z?[z]:[])])).join('')}</div>`;
 const cal=Q[state.rf];
 const rows=scope.map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p);
 exported=rows.map(({c,p})=>({ticker:c.t,name:c.n,sector:c.s,quarter:p.cal,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
 out+=`<div class="section-head"><h3>${fmt(rows.length)} companies · ${esc(qlabel(cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 const xc=centreOf(x,P,cal),yc=centreOf(y,P,cal);
 const quad=p=>p[x.key]==null||p[y.key]==null?'—':`${vshort(x)} ${p[x.key]>=xc?'↑':'↓'} · ${vshort(y)} ${p[y.key]>=yc?'↑':'↓'}`;
 out+=table(['Company',vshort(x),vshort(y),z?vshort(z):'Revenue','Quadrant','13F net managers'],rows.map(({c,p})=>[
  `<b>${esc(c.t)}</b> <span class="muted">${esc(c.n)}</span>`,vcell(x,p[x.key]),vcell(y,p[y.key]),z?vcell(z,p[z.key]):money(p.rev),esc(quad(p)),p.f13!=null?signed(p.f13):c.net13f==null?'—':signed(c.net13f)]));
 return out;
}
const vcell=(v,x)=>x==null?'—':v.centred?`<span class="${x>=0?'positive':'negative'}">${vfmt(v,x)}</span>`:vfmt(v,x);
function centreOf(v,P,cal){if(v.centred)return 0;const m=P.market.by.get(cal);return m&&m[v.key]!=null?m[v.key]:(v.median||0)}
function clockDomain(o){
 const {x,y,layers}=o,L=layers,span=[];
 const lines=[...L.picks,...(L.ref?[L.ref]:[]),...(L.sun?[L.sun]:[]),...L.suns,...(L.market?[L.market]:[])];
 const dom=v=>{const pad=(v.hi-v.lo)*.25;let xs=lines.flatMap(t=>t.pts.map(p=>p[v.key])).filter(a=>a!=null).map(a=>Math.max(v.lo-pad,Math.min(v.hi+pad,a)));
  if(L.cloud.length)xs.push(v.lo,v.hi);
  if(!xs.length)xs=[v.lo??-1,v.hi??1];
  let lo=Math.min(...xs),hi=Math.max(...xs);if(v.centred){lo=Math.min(lo,0);hi=Math.max(hi,0)}
  const p=(hi-lo)*.06||1;return [lo-p,hi+p]};
 span.push(dom(x),dom(y));
 return span;
}
function clockFrame(o,f){
 const {P,Q,x,y,z,trail,layers:L}=o,cal=Q[f],[xd,yd]=o.dom;
 const [W,H]=rotSize(.56,400,620),Lm=64,R=20,T=18,B=46;
 const cx=v=>Math.max(xd[0],Math.min(xd[1],v)),cy=v=>Math.max(yd[0],Math.min(yd[1],v));
 const sx=v=>Lm+(cx(v)-xd[0])/(xd[1]-xd[0])*(W-Lm-R),sy=v=>T+(yd[1]-cy(v))/(yd[1]-yd[0])*(H-T-B);
 const zr=(p,lo=2,hi=7)=>{if(z){const t=p[z.key]==null?null:(rotClip(z,p[z.key])-z.lo)/((z.hi-z.lo)||1);return t==null?lo:lo+(hi-lo)*t}const t=Math.log10(Math.max(1e7,p.rev||1e7));return lo+(hi-lo)*Math.min(1,Math.max(0,(t-7)/4.5))};
 const tipRows=(name,full,p)=>[[name+' · '+qlabel(p.cal),full||''],[vfmt(x,p[x.key]),x.label],[vfmt(y,p[y.key]),y.label],...(z?[[vfmt(z,p[z.key]),z.label]]:[]),...(p.rev?[[money(p.rev),'quarterly revenue']]:[])];
 let s=`<svg class="plot mk-plot rot-clock" viewBox="0 0 ${W} ${H}" role="img" aria-label="Momentum clock for ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-14}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 niceTicks(yd[0],yd[1],6).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm-8}" y="${sy(v)+4}" text-anchor="end">${esc(vfmt(y,v))}</text>`});
 niceTicks(xd[0],xd[1],7).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${esc(vfmt(x,v))}</text>`});
 const x0=centreOf(x,P,cal),y0=centreOf(y,P,cal);
 s+=`<line class="mk-axis" x1="${sx(x0)}" x2="${sx(x0)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${Lm}" x2="${W-R}" y1="${sy(y0)}" y2="${sy(y0)}"/>`;
 const def=x.key==='dom'&&y.key==='rel',xs=vshort(x),ys=vshort(y);
 const narrow=W<600;
 const q=def?(narrow?['Profits ↑ · beating','Profits ↑ · lagging','Profits ↓ · beating','Profits ↓ · lagging']:['Profits ↑ · beating the market','Profits ↑ · lagging','Profits ↓ · beating the market','Profits ↓ · lagging'])
  :narrow?['x ↑ · y ↑','x ↑ · y ↓','x ↓ · y ↑','x ↓ · y ↓']:[`${xs} ↑ · ${ys} ↑`,`${xs} ↑ · ${ys} ↓`,`${xs} ↓ · ${ys} ↑`,`${xs} ↓ · ${ys} ↓`];
 s+=`<text class="mk-quad" x="${W-R-4}" y="${T+12}" text-anchor="end">${esc(q[0])}</text><text class="mk-quad" x="${W-R-4}" y="${H-B-8}" text-anchor="end">${esc(q[1])}</text><text class="mk-quad" x="${Lm+6}" y="${T+12}">${esc(q[2])}</text><text class="mk-quad" x="${Lm+6}" y="${H-B-8}">${esc(q[3])}</text>`;
 s+=`<text class="axis" x="${(Lm+W-R)/2}" y="${H-8}" text-anchor="middle">${esc(x.label)} →${!x.centred?' (lines: the market average)':''}</text>`;
 s+=`<text class="axis" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">${esc(y.label)} →</text>`;
 // every company that quarter
 for(const c of L.cloud){const p=c.by.get(cal);if(!p||p[x.key]==null||p[y.key]==null)continue;
  const out=p[x.key]<xd[0]||p[x.key]>xd[1]||p[y.key]<yd[0]||p[y.key]>yd[1];      // off the scale: drawn at the edge, hollow
  s+=`<g data-tip="${tip(tipRows(c.t,c.n,p))}" tabindex="-1" class="mk-hit"><circle cx="${sx(p[x.key]).toFixed(1)}" cy="${sy(p[y.key]).toFixed(1)}" r="${zr(p,1.6,6).toFixed(1)}" class="rot-cloud${out?' rot-out':''}"/></g>`}
 const path=(pts,cls,style='')=>pts.length>1?`<polyline class="${cls}" style="${style}" points="${pts.map(p=>sx(p[x.key]).toFixed(1)+','+sy(p[y.key]).toFixed(1)).join(' ')}"/>`:'';
 const boxes=[],label=(px_,py_,text,cls='mk-label mk-halo')=>{const w=text.length*6.8,right=px_+10+w<W-R;let lx=right?px_+9:px_-9;const b=[right?lx:lx-w,py_-20,right?lx+w:lx,py_-6];
  if(boxes.some(o=>b[0]<o[2]&&b[2]>o[0]&&b[1]<o[3]&&b[3]>o[1]))return '';boxes.push(b);return `<text class="${cls}" x="${lx}" y="${py_-9}" text-anchor="${right?'start':'end'}">${esc(text)}</text>`};
 let labels='';
 for(const t of L.suns){const tr=trailOf(t.pts,cal,trail,x,y);s+=path(tr,'rot-ctx');const h=tr[tr.length-1];if(h&&h.cal===cal){
  s+=`<g data-tip="${tip(tipRows(t.name,'sector average · '+fmt(h.n)+' companies',h))}" tabindex="0" class="mk-hit" data-rsec="${esc(t.id)}"><circle cx="${sx(h[x.key])}" cy="${sy(h[y.key])}" r="10" fill="transparent"/><circle cx="${sx(h[x.key])}" cy="${sy(h[y.key])}" r="4" class="mk-dot"/></g>`;labels+=label(sx(h[x.key]),sy(h[y.key]),t.name)}}
 for(const [t,cls,col] of [[L.ref,'rot-ref',''],[L.market,'rot-line','stroke:var(--rot-sun)'],[L.sun,'rot-line','stroke:var(--rot-1)']]){if(!t)continue;
  const tr=trailOf(t.pts,cal,trail,x,y);s+=path(tr,cls,col);
  tr.forEach((p,i)=>{const head=i===tr.length-1&&p.cal===cal;s+=`<g data-tip="${tip(tipRows(t.name,fmt(p.n)+' companies',p))}" tabindex="0" class="mk-hit"><circle cx="${sx(p[x.key])}" cy="${sy(p[y.key])}" r="${head?11:8}" fill="transparent"/><circle cx="${sx(p[x.key])}" cy="${sy(p[y.key])}" r="${head?(t===L.market?7:6):2.5}" class="${t===L.ref?'mk-dot':'rot-dot'}" style="${t===L.ref?'':'fill:'+(t===L.market?'var(--rot-sun)':'var(--rot-1)')};opacity:${head?1:.35+.5*i/Math.max(1,tr.length-1)}"/></g>`});
  const h=tr[tr.length-1];if(h&&h.cal===cal&&t!==L.ref)labels+=label(sx(h[x.key]),sy(h[y.key]),t.name)}
 for(const t of L.picks){const tr=trailOf(t.pts,cal,trail,x,y);s+=path(tr,'rot-line','stroke:'+t.color);
  tr.forEach((p,i)=>{const head=i===tr.length-1;s+=`<g data-tip="${tip(tipRows(t.name,t.full,p))}" tabindex="0" class="mk-hit"><circle cx="${sx(p[x.key])}" cy="${sy(p[y.key])}" r="11" fill="transparent"/><circle cx="${sx(p[x.key])}" cy="${sy(p[y.key])}" r="${(head?zr(p,5,9):zr(p,2,5)).toFixed(1)}" class="rot-dot" style="fill:${t.color};opacity:${head?1:(.3+.55*i/Math.max(1,tr.length-1)).toFixed(2)}"/></g>`});
  const h=tr[tr.length-1];if(h)labels+=label(sx(h[x.key]),sy(h[y.key]),`${t.name} ${h.cal===cal?'':qlabel(h.cal)}`.trim())}
 if(!L.picks.length&&!L.suns.length&&!L.sun&&!L.cloud.length)return empty('Pick a sector or type tickers to trace.');
 return s+labels+'</svg>';
}
function planar(c,Q,color,vars){                      // the clock split into plain charts, one per variable
 const pts=c.pts,W=300,H=120,L=44,R=8,T=10,B=22,n=pts.length,x=i=>L+i/Math.max(1,n-1)*(W-L-R);
 const at=f=>`<text class="axis" x="${L}" y="${H-6}">${esc(qlabel(pts[0].cal))}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(qlabel(pts[n-1].cal))}</text>`;
 const one=v=>{const vals=pts.map(p=>p[v.key]);const ok=vals.filter(a=>a!=null);if(ok.length<2)return `<div class="rot-mini"><h4>${esc(v.label)}</h4><p class="sub">Not enough quarters with this figure.</p></div>`;
  if(!v.centred){const lo=Math.min(...ok),hi=Math.max(...ok),pad=(hi-lo)*.15||1,y=a=>T+(hi+pad-a)/((hi-lo)+2*pad)*(H-T-B);
   return `<div class="rot-mini"><h4>${esc(v.label)}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot">${[lo,hi].map(a=>`<text class="axis" x="${L-6}" y="${y(a)+4}" text-anchor="end">${esc(vfmt(v,a))}</text><line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(a)}" y2="${y(a)}"/>`).join('')}<polyline class="rot-line" style="stroke:${color}" points="${vals.map((a,i)=>a==null?'':x(i).toFixed(1)+','+y(a).toFixed(1)).filter(Boolean).join(' ')}"/>${vals.map((a,i)=>a==null?'':`<circle cx="${x(i)}" cy="${y(a)}" r="${i===n-1?4.5:2.5}" style="fill:${color}"><title>${esc(qlabel(pts[i].cal))}: ${esc(vfmt(v,a))}</title></circle>`).join('')}${at()}</svg></div>`}
  const m=Math.max(.01,...ok.map(Math.abs)),mid=T+(H-T-B)/2,bw=Math.max(4,(W-L-R)/n-4);
  return `<div class="rot-mini"><h4>${esc(v.label)}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot"><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${mid}" y2="${mid}"/><text class="axis" x="${L-6}" y="${T+6}" text-anchor="end">${esc(vfmt(v,m))}</text><text class="axis" x="${L-6}" y="${H-B}" text-anchor="end">${esc(vfmt(v,-m))}</text>${vals.map((a,i)=>{if(a==null)return '';const h=Math.abs(a)/m*((H-T-B)/2);return `<rect x="${x(i)-bw/2}" y="${a>=0?mid-h:mid}" width="${bw}" height="${Math.max(1,h)}" rx="2" class="${a>=0?'mk-buy':'mk-sell'}"><title>${esc(qlabel(pts[i].cal))}: ${esc(vfmt(v,a))}</title></rect>`}).join('')}${at()}</svg></div>`};
 return `<div class="panel rot-card"><h3><span class="mk-key" style="background:${color}"></span> ${esc(c.t)} <span class="muted">${esc(c.n)}</span></h3>${vars.map(one).join('')}${c.net13f!=null?`<p class="sub">13F this quarter: ${signed(c.net13f)} net managers · est. ${smoney(c.usd13f)}</p>`:''}</div>`;
}

/* ---------- solar system ---------- */
function solarView(o){
 const {P,Q,x,y,sec}=o;
 o.scale=solarScale(o);
 ROT.ctx={Q,P,draw:f=>sec?sectorFrame(o,f):marketFrame(o,f)};
 let out=`<div class="panel"><h3>${sec?esc(P.suns[sec].name)+' — the sun and its planets':'Solar system — every sector orbiting the market'}</h3>`;
 out+=sec?`<p class="sub">The sun is the ${esc(P.suns[sec].name)} average for the quarter shown; each company is a planet. Direction: how it differs from its sector (→ higher ${esc(vshort(x))}, ↑ higher ${esc(vshort(y))}); distance: by how much, in typical company spreads (compressed so the far ones fit). Planet colour: that quarter's 13F crowding (green more managers added, red more cut).</p>`
  :`<p class="sub">The market average sits at the centre. Each sector is a sun placed by how far its average is from the market's (→ higher ${esc(vshort(x))}, ↑ higher ${esc(vshort(y))}) with a tail of its last quarters; its companies are moons around it. Press play to watch the suns orbit. Click a sun to open its sector.</p>`;
 out+=rotPlayer(Q,P)+`<div id="rot-plot">${ROT.ctx.draw(state.rf)}</div>`;
 out+=`<div class="mk-legend"><span><i class="mk-key" style="background:var(--rot-sun)"></i>${sec?'Sector average':`Sector suns, with tails of their last ${o.trail} quarters · the centre is the market`}</span><span><i class="mk-key mk-hot"></i>More 13F managers added</span><span><i class="mk-key" style="background:var(--flow-sell)"></i>More cut</span><span><i class="mk-key mk-dot"></i>No 13F change on file</span>${o.picks.map((c,i)=>`<span><i class="mk-key" style="background:${ROT_SERIES[i]}"></i>${esc(c.t)}</span>`).join('')}</div></div>`;
 const cal=Q[state.rf],m=P.market.by.get(cal);
 if(!sec){
  const rows=Object.values(P.suns).map(s=>({s,p:s.by.get(cal)})).filter(r=>r.p);
  exported=rows.map(({s,p})=>({sector:s.name,quarter:cal,companies:p.n,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
  out+=`<div class="section-head"><h3>Sector suns · ${esc(qlabel(cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Sector','Companies',vshort(x),'vs the market ('+vshort(x)+')',vshort(y),'vs the market ('+vshort(y)+')'],rows.map(({s,p})=>[`<button class="text-button" data-rsec="${esc(s.id)}"><b>${esc(s.name)}</b></button>`,fmt(p.n),vfmt(x,p[x.key]),m?vcell({...x,centred:true},p[x.key]==null||m[x.key]==null?null:p[x.key]-m[x.key]):'—',vfmt(y,p[y.key]),m?vcell({...y,centred:true},p[y.key]==null||m[y.key]==null?null:p[y.key]-m[y.key]):'—']));
 }else{
  const sp=P.suns[sec].by.get(cal),rows=rotScope(P,sec).map(c=>({c,p:c.by.get(cal)})).filter(r=>r.p);
  exported=rows.map(({c,p})=>({ticker:c.t,name:c.n,quarter:cal,...Object.fromEntries(P.vars.map(v=>[v.key,p[v.key]]))}));
  out+=`<div class="section-head"><h3>${fmt(rows.length)} companies · ${esc(qlabel(cal))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Company',vshort(x),'vs the sector ('+vshort(x)+')',vshort(y),'vs the sector ('+vshort(y)+')','13F net managers'],rows.map(({c,p})=>[`<b>${esc(c.t)}</b> <span class="muted">${esc(c.n)}</span>`,vfmt(x,p[x.key]),sp?vcell({...x,centred:true},p[x.key]==null||sp[x.key]==null?null:p[x.key]-sp[x.key]):'—',vfmt(y,p[y.key]),sp?vcell({...y,centred:true},p[y.key]==null||sp[y.key]==null?null:p[y.key]-sp[y.key]):'—',p.f13!=null?signed(p.f13):'—']));
 }
 return out;
}
function solarScale(o){                               // fixed across quarters so the animation does not rescale
 const {P,x,y,sec}=o,key=['solar',x.key,y.key,sec].join('|');
 if(P.cache[key])return P.cache[key];
 const rs=a=>{const s=a.slice().sort((p,q)=>p-q);const v=(quantile(s,.75)-quantile(s,.25))/1.349;return v>0?v:(Math.max(...s.map(Math.abs))||1)};
 let out;
 if(!sec){
  const dx=[],dy=[];
  for(const s of Object.values(P.suns))for(const p of s.pts){const m=P.market.by.get(p.cal);if(m&&p[x.key]!=null&&p[y.key]!=null&&m[x.key]!=null&&m[y.key]!=null){dx.push(p[x.key]-m[x.key]);dy.push(p[y.key]-m[y.key])}}
  const kx=dx.length?rs(dx):1,ky=dy.length?rs(dy):1;
  const D=Math.max(1,...dx.map((v,i)=>Math.hypot(v/kx,dy[i]/ky)))*1.05;
  const mx=[],my=[];
  for(const c of P.cos){const s=P.suns[c.s];if(!s)continue;for(const p of c.pts){const q=s.by.get(p.cal);if(q&&p[x.key]!=null&&p[y.key]!=null&&q[x.key]!=null&&q[y.key]!=null){mx.push(Math.abs(p[x.key]-q[x.key])/x.scale);my.push(Math.abs(p[y.key]-q[y.key])/y.scale)}}}
  const Dm=Math.max(.5,quantile(mx.map((v,i)=>Math.hypot(v,my[i])).sort((a,b)=>a-b),.95)||1);
  out={kx,ky,D,Dm};
 }else{
  const s=P.suns[sec],ds=[];
  for(const c of rotScope(P,sec))for(const p of c.pts){const q=s.by.get(p.cal);if(q&&p[x.key]!=null&&p[y.key]!=null&&q[x.key]!=null&&q[y.key]!=null)ds.push(Math.hypot((p[x.key]-q[x.key])/x.scale,(p[y.key]-q[y.key])/y.scale))}
  out={D:Math.max(.5,quantile(ds.sort((a,b)=>a-b),.95)||1)};
 }
 return P.cache[key]=out;
}
function compass(W,c0x,c0y,R,x,y){
 return `<text class="mk-quad" x="${W-4}" y="${c0y-6}" text-anchor="end">higher ${esc(vshort(x))} →</text><text class="mk-quad" x="4" y="${c0y-6}">← lower</text><text class="mk-quad" x="${c0x}" y="${c0y-R-14}" text-anchor="middle">↑ higher ${esc(vshort(y))}</text><text class="mk-quad" x="${c0x}" y="${c0y+R+24}" text-anchor="middle">lower ↓</text>`;
}
function moonColor(c,p){const n=p&&p.f13!=null?p.f13:c.net13f;return n>0?'mk-hot':n<0?'rot-sell':'mk-dot'}
function marketFrame(o,f){
 const {P,Q,x,y,trail,picks}=o,cal=Q[f],{kx,ky,D,Dm}=o.scale;
 const [W,H]=rotSize(.68,520,720),c0x=W/2,c0y=H/2+6,R=Math.min(W,H)/2-58,Rm=R*.13;
 const m0=P.market.by.get(cal);
 const posAt=(s,c)=>{const p=s.by.get(c),m=P.market.by.get(c);if(!p||!m||p[x.key]==null||p[y.key]==null||m[x.key]==null||m[y.key]==null)return null;const dx=(p[x.key]-m[x.key])/kx,dy=(p[y.key]-m[y.key])/ky,d=Math.hypot(dx,dy),r=Math.pow(Math.min(1,d/D),.6)*R;return d?[c0x+dx/d*r,c0y-dy/d*r]:[c0x,c0y]};
 const moonAt=(c,s,ca)=>{const sp=posAt(s,ca),p=c.by.get(ca),q=s.by.get(ca);if(!sp||!p||!q||p[x.key]==null||p[y.key]==null)return null;const dx=(p[x.key]-q[x.key])/x.scale,dy=(p[y.key]-q[y.key])/y.scale,d=Math.hypot(dx,dy);if(!d)return sp;const r=Rm*Math.min(1,Math.sqrt(d/Dm));return [sp[0]+dx/d*r,sp[1]-dy/d*r]};
 let s=`<svg class="plot mk-plot rot-solar" viewBox="0 0 ${W} ${H}" role="img" aria-label="Sector suns around the market average, ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-16}" y="${H-16}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 [1,2,4].filter(k=>k<D).forEach(k=>{const r=Math.pow(k/D,.6)*R;s+=`<circle cx="${c0x}" cy="${c0y}" r="${r}" class="rot-ring"/><text class="axis rot-ringlabel" x="${c0x+r*.866+3}" y="${c0y+r*.5+12}">${k===1?'typical gap':k+'× typical'}</text>`});
 s+=`<line class="mk-grid" x1="${c0x-R}" x2="${c0x+R}" y1="${c0y}" y2="${c0y}"/><line class="mk-grid" x1="${c0x}" x2="${c0x}" y1="${c0y-R}" y2="${c0y+R}"/>`;
 s+=compass(W,c0x,c0y,R,x,y);
 const suns=Object.values(P.suns);
 // tails: the sun's last quarters, fading
 for(const sn of suns){const ps=Q.slice(Math.max(0,f-trail+1),f+1).map(c=>posAt(sn,c)).filter(Boolean);
  for(let i=1;i<ps.length;i++)s+=`<line x1="${ps[i-1][0].toFixed(1)}" y1="${ps[i-1][1].toFixed(1)}" x2="${ps[i][0].toFixed(1)}" y2="${ps[i][1].toFixed(1)}" class="rot-tail" style="opacity:${(.15+.6*i/ps.length).toFixed(2)}"/>`}
 // moons
 for(const c of P.cos){const sn=P.suns[c.s];if(!sn)continue;const mp=moonAt(c,sn,cal);if(!mp)continue;const p=c.by.get(cal);
  s+=`<g data-tip="${tip([[c.t,c.n||''],[vfmt(x,p[x.key]),x.label],[vfmt(y,p[y.key]),y.label],[p.f13==null?'—':signed(p.f13),'net 13F managers that quarter']])}" tabindex="-1" class="mk-hit"><circle cx="${mp[0].toFixed(1)}" cy="${mp[1].toFixed(1)}" r="1.9" class="${moonColor(c,p)} rot-moon"/></g>`}
 // picks: their path through the system
 picks.forEach((c,i)=>{const sn=P.suns[c.s];if(!sn)return;const ps=Q.slice(Math.max(0,f-trail+1),f+1).map(ca=>moonAt(c,sn,ca)).filter(Boolean);
  if(ps.length>1)s+=`<polyline class="rot-line" style="stroke:${ROT_SERIES[i]}" points="${ps.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}"/>`;
  const h=moonAt(c,sn,cal);if(h)s+=`<circle cx="${h[0]}" cy="${h[1]}" r="5" class="rot-dot" style="fill:${ROT_SERIES[i]}"/><text class="mk-label mk-halo" x="${h[0]+8}" y="${h[1]-6}">${esc(c.t)}</text>`});
 // suns and their names
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
 const {P,Q,x,y,z,trail,picks,sec}=o,cal=Q[f],sun=P.suns[sec],last=sun.by.get(cal),{D}=o.scale;
 const [W,H]=rotSize(.68,520,720),c0x=W/2,c0y=H/2,R=Math.min(W,H)/2-64;
 if(!last)return empty(`No ${sun.name} average for ${qlabel(cal)} (fewer than three companies).`);
 const cos=rotScope(P,sec);
 const posAt=(c,ca)=>{const p=c.by.get(ca),q=sun.by.get(ca);if(!p||!q||p[x.key]==null||p[y.key]==null||q[x.key]==null||q[y.key]==null)return null;const dx=(p[x.key]-q[x.key])/x.scale,dy=(p[y.key]-q[y.key])/y.scale,d=Math.hypot(dx,dy);if(!d)return [c0x,c0y];const r=R*Math.pow(Math.min(1,d/D),.6);return [c0x+dx/d*r,c0y-dy/d*r,d>D]};
 const revs=cos.map(c=>(c.by.get(cal)||{}).rev||0),maxRev=Math.max(1,...revs);
 const size=p=>z?(()=>{const t=p[z.key]==null?.3:(rotClip(z,p[z.key])-z.lo)/((z.hi-z.lo)||1);return 3+9*t})():3+10*Math.sqrt((p.rev||0)/maxRev);
 let s=`<svg class="plot mk-plot rot-solar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sun.name)} companies around the sector average, ${esc(qlabel(cal))}; the table below lists every value">`;
 s+=`<text class="rot-watermark" x="${W-16}" y="${H-16}" text-anchor="end">${esc(qlabel(cal))}</text>`;
 [.5,1,2,4].filter(k=>k<D).forEach(k=>{const r=R*Math.pow(k/D,.6);s+=`<circle cx="${c0x}" cy="${c0y}" r="${r}" class="rot-ring"/><text class="axis rot-ringlabel" x="${c0x+r*.866+3}" y="${c0y+r*.5+12}">${k===1?'typical spread':k+'×'}</text>`});
 s+=`<line class="mk-grid" x1="${c0x-R}" x2="${c0x+R}" y1="${c0y}" y2="${c0y}"/><line class="mk-grid" x1="${c0x}" x2="${c0x}" y1="${c0y-R}" y2="${c0y+R}"/>`;
 s+=compass(W,c0x,c0y,R,x,y);
 const planets=cos.map(c=>({c,p:c.by.get(cal),xy:posAt(c,cal)})).filter(a=>a.p&&a.xy).sort((a,b)=>(a.p.rev||0)-(b.p.rev||0));
 picks.forEach((c,i)=>{if(c.s!==sec)return;const ps=Q.slice(Math.max(0,f-trail+1),f+1).map(ca=>posAt(c,ca)).filter(Boolean);if(ps.length>1)s+=`<polyline class="rot-line" style="stroke:${ROT_SERIES[i]}" points="${ps.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}"/>`});
 for(const a of planets){const {c,p,xy}=a,pi=picks.indexOf(c);
  s+=`<g data-tip="${tip([[c.t,c.n||''],[vfmt(x,p[x.key]),x.label+' (sector '+vfmt(x,last[x.key])+')'],[vfmt(y,p[y.key]),y.label+' (sector '+vfmt(y,last[y.key])+')'],...(z?[[vfmt(z,p[z.key]),z.label]]:[]),[p.f13==null?'—':signed(p.f13),'net 13F managers that quarter'],[money(p.rev),'quarterly revenue']])}" tabindex="0" class="mk-hit"><circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${Math.max(9,size(p)+3)}" fill="transparent"/><circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${size(p).toFixed(1)}" class="${pi>=0?'rot-dot':moonColor(c,p)}" style="${pi>=0?'fill:'+ROT_SERIES[pi]:''}${xy[2]?';stroke-dasharray:2 2':''}"/></g>`}
 const named=new Set([...picks.map(c=>c.t),...planets.slice().sort((a,b)=>(b.p.rev||0)-(a.p.rev||0)).slice(0,10).map(a=>a.c.t)]),boxes=[];
 planets.filter(a=>named.has(a.c.t)).sort((a,b)=>(b.p.rev||0)-(a.p.rev||0)).forEach(a=>{const r=size(a.p),w=a.c.t.length*7.4;let lx=a.xy[0]+r+3,anchor='start';if(lx+w>W-2){lx=a.xy[0]-r-3;anchor='end'}
  const b=anchor==='start'?[lx,a.xy[1]-14,lx+w,a.xy[1]]:[lx-w,a.xy[1]-14,lx,a.xy[1]];if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))return;boxes.push(b);
  s+=`<text class="mk-label mk-halo" x="${lx}" y="${a.xy[1]-3}" text-anchor="${anchor}">${esc(a.c.t)}</text>`});
 const m=P.market.by.get(cal);
 s+=`<g data-tip="${tip([[sun.name+' average',qlabel(cal)+' · '+fmt(last.n)+' companies'],[vfmt(x,last[x.key]),x.label+(m?' (market '+vfmt(x,m[x.key])+')':'')],[vfmt(y,last[y.key]),y.label+(m?' (market '+vfmt(y,m[y.key])+')':'')]])}" tabindex="0" class="mk-hit"><circle cx="${c0x}" cy="${c0y}" r="13" class="rot-sun"/></g>`;
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
const ROT_FAMILY={om:'om',dom:'om',gm:'gm',dgm:'gm',nm:'nm',dnm:'nm',revg:'rev',reva:'rev',rel:'px',rel6:'px',ret:'px'};
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
 const c=ROT.ctx;if(!c||!document.getElementById('rot-plot'))return;
 $('rot-plot').innerHTML=c.draw(state.rf);
 if($('rframe'))$('rframe').value=state.rf;
 if($('rflabel'))$('rflabel').textContent=rotFlabel(c.P,c.Q[state.rf]);
 if($('rplay'))$('rplay').textContent=ROT.timer?'❚❚ Pause':`▶ Play ${Math.min(16,c.Q.length)} quarters`;
 bindTips();bindRotSuns();
}
function rotStop(){if(ROT.timer){clearInterval(ROT.timer);ROT.timer=null}}
function rotToggle(){
 if(ROT.timer){rotStop();render();return}
 const n=ROT.ctx?ROT.ctx.Q.length:0;if(!n)return;
 if(state.rf>=n-1)state.rf=Math.max(0,n-16);
 ROT.timer=setInterval(()=>{
  if(state.tab!=='rotation'||!document.getElementById('rot-plot')){rotStop();return}
  if(state.rf>=n-1){rotStop();render();return}
  state.rf++;rotDraw()},850);
 rotDraw();
}
function bindRotSuns(){document.querySelectorAll('#workspace [data-rsec]').forEach(b=>b.onclick=()=>{rotStop();state.rsec=b.dataset.rsec;state.rview=state.rview==='scan'?'solar':state.rview;render()})}
function bindRotation(){
 for(const k of ['rview','rsec','rx','ry','rz','rq','rshow'])if($(k))$(k).onchange=e=>{rotStop();state[k]=e.target.value;if(k==='rx'&&state.ry===state.rx)state.ry='';render()};
 if($('rtk')){$('rtk').onchange=e=>{state.rtk=e.target.value;render()};$('rtk').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 if($('rplay'))$('rplay').onclick=rotToggle;
 if($('rframe')){$('rframe').oninput=e=>{rotStop();state.rf=+e.target.value;rotDraw()};$('rframe').onchange=e=>{state.rf=+e.target.value;render()}}
 document.querySelectorAll('#workspace [data-raxes]').forEach(b=>b.onclick=()=>{const [x,y,z]=b.dataset.raxes.split('|');state.rview='clock';state.rx=x;state.ry=y;state.rz=z||state.rz;render();scrollTo({top:0,behavior:'smooth'})});
 bindRotSuns();
}
