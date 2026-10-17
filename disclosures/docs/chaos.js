/* 4.7 Next-step forecasts and the 3-D / 4-D solar system. Uses market.js, rotation.js (and rrg.js for the RRG arrows).
   Data: data/market/history/chaos-forecast.json (quarters), chaos-forecast-monthly.json (months), chaos-rrg.json (the RRG,
   weekly) — built by app/chaos_forecast.py on the rotation-history branch.
   · An arrow from a dot: where it lands next period on average among the most similar past states (method of analogues in
     delay-embedded solar coordinates), shrunk toward "stay put" or "back to the sun" by how well such arrows did before.
     The dashed ellipse: the analogues' 80% spread. Origins before the latest are out-of-sample backtest forecasts made
     with data public at the time, so "+ what happened" shows each arrow against the actual next dot.
   · Price: on the quarterly / monthly charts "stock vs the S&P 500" is a price coordinate (next close = close ×
     (1 + forecast + the S&P's past average)); on the RRG the next point is an exact function of next week's close, so
     the forecast point is mapped back to the close whose point is nearest.
   · Solar 3-D / 4-D: the solar system with a third coordinate as depth (4-D: time played) or time as depth (3-D: every
     orbit becomes a spiral along the time axis); in a sector every company keeps its trail. */
const FC_MODES=[['','Off'],['next','Next step — analogues (arrows + price)'],['check','Next step + what happened (backtest)']];
const fcOn=()=>state.rfc==='next'||state.rfc==='check';

function fcLoad(P){                                     // the forecast file for this frequency, indexed once
 const name=P&&P.monthly?'history/chaos-forecast-monthly':'history/chaos-forecast';
 const m=marketData(name);
 if(!m.data)return {err:m.err||null,loading:!m.err};
 const d=m.data;
 if(!d._prep){
  const by=rows=>{const mm=new Map();for(const r of rows||[])mm.set(d.origins[r[0]],r);return mm};
  d._prep={vi:Object.fromEntries((d.vars||[]).map((v,i)=>[v,i])),cos:new Map(Object.entries(d.companies||{}).map(([t,r])=>[t,by(r)])),
   suns:new Map(Object.entries(d.suns||{}).map(([k,r])=>[k,by(r)])),market:by(d.market)};
 }
 return {data:d};
}
function fcRow(o,ent,cal){
 if(!o.fc||!ent)return null;const p=o.fc._prep;
 const m=ent.id==='market'?p.market:ent.t?p.cos.get(ent.t):p.suns.get(ent.id);
 return m?m.get(cal)||null:null;
}
const fcHas=(o,v)=>!!(o.fc&&v&&(v.key==='__time'||o.fc._prep.vi[v.key]!=null));
// the forecast next value of v on the chart's own scale and smoothing: the dot moves by the forecast's change on that scale
function fcNext(o,ent,v,cal,row){
 if(!row||!v)return null;
 if(v.key==='__time'){const i=o.qi.get(cal);return i==null?null:i+1}
 const j=o.fc._prep.vi[v.key];if(j==null)return null;
 const nx=row[1][j],p=ent.by.get(cal),raw=p?p[v.key]:null,now=val(o,ent,v,cal);
 if(nx==null||raw==null||now==null)return null;
 const a=rotT(o,v,nx,cal),b=rotT(o,v,raw,cal);return a==null||b==null?null:now+(a-b);
}
function fcHalf(o,ent,v,cal,row){                       // 80% half-width on the chart's scale
 if(!row||!v||v.key==='__time')return 0;
 const j=o.fc._prep.vi[v.key];if(j==null||!row[2])return 0;const nx=row[1][j],h=row[2][j];if(nx==null||h==null)return 0;
 const a=rotT(o,v,nx+h,cal),b=rotT(o,v,nx-h,cal);return a==null||b==null?0:Math.abs(a-b)/2;
}
function fcActual(o,ent,v,cal){                         // where the dot actually went (the next period on file)
 const i=o.qi.get(cal);if(i==null||i+1>=o.Q.length)return null;
 if(v.key==='__time')return i+1;return val(o,ent,v,o.Q[i+1]);
}
function fcArrowSvg(p,q,col,w,cls='fc-arrow'){
 const L=Math.hypot(q[0]-p[0],q[1]-p[1]);
 if(L<2)return `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${(w*2.2).toFixed(1)}" class="fc-still" style="stroke:${col}"/>`;
 const a=Math.atan2(q[1]-p[1],q[0]-p[0]),hs=Math.min(8,3+L*.3)*(w>1.4?1.1:.8);
 const e=[q[0]-Math.cos(a)*hs*.6,q[1]-Math.sin(a)*hs*.6];
 return `<line class="${cls}" x1="${p[0].toFixed(1)}" y1="${p[1].toFixed(1)}" x2="${e[0].toFixed(1)}" y2="${e[1].toFixed(1)}" style="stroke:${col};stroke-width:${w}"/>`+
  `<path class="${cls}-head" style="fill:${col}" d="M${q[0].toFixed(1)},${q[1].toFixed(1)} L${(q[0]-hs*Math.cos(a-.42)).toFixed(1)},${(q[1]-hs*Math.sin(a-.42)).toFixed(1)} L${(q[0]-hs*Math.cos(a+.42)).toFixed(1)},${(q[1]-hs*Math.sin(a+.42)).toFixed(1)} Z"/>`;
}
const fcCheckSvg=(p,q,col)=>`<line class="fc-actual" x1="${p[0].toFixed(1)}" y1="${p[1].toFixed(1)}" x2="${q[0].toFixed(1)}" y2="${q[1].toFixed(1)}" style="stroke:${col}"/><circle class="fc-actual-dot" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="4" style="stroke:${col}"/>`;
function fcTipRows(o,ent,name,cal,row){
 const out=[[name+' · next '+(o.P.monthly?'month':'quarter'),'forecast made '+qlabel(cal)]];
 for(const v of [o.x,o.y,...(o.z&&o.z.key!=='__time'?[o.z]:[])]){const j=o.fc._prep.vi[v.key];if(j==null)continue;
  out.push([vfmt(v,row[1][j])+(row[2]&&row[2][j]!=null?' ± '+vfmt({...v,centred:false},row[2][j]).replace(/^−/,''):''),v.label])}
 if(row[3]!=null)out.push([fmt(row[3],2),'local divergence of the analogues (higher = they fan out)']);
 if(row[5]!=null)out.push(['$'+fmt(row[5],2)+(row[6]!=null?` (80%: $${fmt(row[6],2)}–$${fmt(row[7],2)})`:''),`price next ${o.P.monthly?'month':'quarter'}-end · now $${fmt(row[4],2)}`]);
 return out;
}

/* ---------- arrows on the momentum clock (SVG) ---------- */
function fcClockLayer(o,cal,px,L){
 if(!fcOn()||!o.fc)return '';
 if(!fcHas(o,o.x)||!fcHas(o,o.y))return '';
 let s='';const check=state.rfc==='check';
 const one=(ent,name,col,w,cone)=>{const row=fcRow(o,ent,cal);if(!row)return;
  const a=val(o,ent,o.x,cal),b=val(o,ent,o.y,cal),na=fcNext(o,ent,o.x,cal,row),nb=fcNext(o,ent,o.y,cal,row);
  if(a==null||b==null||na==null||nb==null)return;
  const p=px(a,b),q=px(na,nb);
  if(cone){const hx=fcHalf(o,ent,o.x,cal,row),hy=fcHalf(o,ent,o.y,cal,row),e1=px(na+hx,nb+hy);
   s+=`<ellipse class="fc-cone" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" rx="${Math.abs(e1[0]-q[0]).toFixed(1)}" ry="${Math.abs(e1[1]-q[1]).toFixed(1)}" style="stroke:${col}"/>`}
  if(check){const xa=fcActual(o,ent,o.x,cal),ya=fcActual(o,ent,o.y,cal);if(xa!=null&&ya!=null)s+=fcCheckSvg(p,px(xa,ya),col)}
  s+=`<g data-tip="${tip(fcTipRows(o,ent,name,cal,row))}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,col,w)}</g>`};
 for(const c of L.cloud)if(!L.picks.some(t=>t.ent===c))one(c,c.t,'var(--flow-dot)',.9,false);
 for(const t of L.suns)one(t.ent,t.name,'var(--muted)',1.4,false);
 if(L.market)one(L.market.ent,'Market','var(--rot-sun)',2,true);
 if(L.sun)one(L.sun.ent,L.sun.name,'var(--rot-1)',2,true);
 L.picks.forEach(t=>one(t.ent,t.name,t.color,2.2,true));
 return s;
}

/* ---------- arrows on the 2-D solar system: suns around the market, planets around their sun ---------- */
function fcSolarMarket(o,cal,posXY){                   // posXY(sunX, sunY, mkX, mkY) -> px; suns only (moons are too close)
 if(!fcOn()||!o.fc||!fcHas(o,o.x)||!fcHas(o,o.y))return '';
 const M=o.P.market,mr=fcRow(o,M,cal);if(!mr)return '';
 const mx=fcNext(o,M,o.x,cal,mr),my=fcNext(o,M,o.y,cal,mr),mx0=val(o,M,o.x,cal),my0=val(o,M,o.y,cal);if(mx==null||my==null)return '';
 let s='';
 for(const sn of Object.values(o.P.suns)){const r=fcRow(o,sn,cal);if(!r)continue;
  const a=val(o,sn,o.x,cal),b=val(o,sn,o.y,cal),na=fcNext(o,sn,o.x,cal,r),nb=fcNext(o,sn,o.y,cal,r);if(a==null||b==null||na==null||nb==null)continue;
  const p=posXY(a,b,mx0,my0),q=posXY(na,nb,mx,my);if(!p||!q)continue;
  if(state.rfc==='check'){const xa=fcActual(o,sn,o.x,cal),ya=fcActual(o,sn,o.y,cal),ma=fcActual(o,M,o.x,cal),mb=fcActual(o,M,o.y,cal);if(xa!=null&&ya!=null&&ma!=null&&mb!=null){const qa=posXY(xa,ya,ma,mb);if(qa)s+=fcCheckSvg(p,qa,'var(--rot-sun)')}}
  s+=`<g data-tip="${tip(fcTipRows(o,sn,sn.name,cal,r))}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,'var(--rot-sun)',1.8)}</g>`}
 return s;
}
function fcSolarSector(o,cal,sun,posXY){              // posXY(cx, cy, sunX, sunY) -> px
 if(!fcOn()||!o.fc||!fcHas(o,o.x)||!fcHas(o,o.y))return '';
 const sr=fcRow(o,sun,cal);if(!sr)return '';
 const sx=fcNext(o,sun,o.x,cal,sr),sy=fcNext(o,sun,o.y,cal,sr),sx0=val(o,sun,o.x,cal),sy0=val(o,sun,o.y,cal);if(sx==null||sy==null)return '';
 let s='';const check=state.rfc==='check';
 for(const c of rotScope(o.P,o.sec)){const r=fcRow(o,c,cal);if(!r)continue;
  const a=val(o,c,o.x,cal),b=val(o,c,o.y,cal),na=fcNext(o,c,o.x,cal,r),nb=fcNext(o,c,o.y,cal,r);if(a==null||b==null||na==null||nb==null)continue;
  const p=posXY(a,b,sx0,sy0),q=posXY(na,nb,sx,sy);if(!p||!q)continue;
  const pi=o.picks.indexOf(c),col=pi>=0?ROT_SERIES[pi]:'var(--ink-2)';
  if(check){const xa=fcActual(o,c,o.x,cal),ya=fcActual(o,c,o.y,cal),ua=fcActual(o,sun,o.x,cal),va=fcActual(o,sun,o.y,cal);if(xa!=null&&ya!=null&&ua!=null&&va!=null){const qa=posXY(xa,ya,ua,va);if(qa)s+=fcCheckSvg(p,qa,col)}}
  s+=`<g data-tip="${tip(fcTipRows(o,c,c.t,cal,r))}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,col,pi>=0?2.2:1.1)}</g>`}
 return s;
}

/* ---------- arrows in the 3-D box (canvas) ---------- */
function fcPaint3d(o,cal,ctx,proj,XYZ,ents,C){
 if(!fcOn()||!o.fc||!fcHas(o,o.x)||!fcHas(o,o.y)||!fcHas(o,o.z))return;
 for(const [ent,col,w] of ents){const row=fcRow(o,ent,cal);if(!row)continue;
  const now=XYZ(ent,cal);if(!now)continue;
  const nx=[fcNext(o,ent,o.x,cal,row),fcNext(o,ent,o.y,cal,row),fcNext(o,ent,o.z,cal,row)];if(nx.some(v=>v==null))continue;
  const q=XYZ(ent,cal,nx);fcArrow3d(ctx,proj(...now),proj(...q),col,w);
  if(state.rfc==='check'){const i=o.qi.get(cal);if(i+1<o.Q.length){const a=XYZ(ent,o.Q[i+1]);if(a){const pa=proj(...a),p0=proj(...now);ctx.setLineDash([2,3]);ctx.strokeStyle=col;ctx.globalAlpha=.7;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(p0[0],p0[1]);ctx.lineTo(pa[0],pa[1]);ctx.stroke();ctx.setLineDash([]);ctx.beginPath();ctx.arc(pa[0],pa[1],3.5,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1}}}
 }
}
function fcArrow3d(ctx,p,q,col,w){
 const L=Math.hypot(q[0]-p[0],q[1]-p[1]);ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=w;ctx.globalAlpha=.95;
 if(L<2){ctx.beginPath();ctx.arc(p[0],p[1],w*2.2,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;return}
 const a=Math.atan2(q[1]-p[1],q[0]-p[0]),hs=Math.min(8,3+L*.3);
 ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0]-Math.cos(a)*hs*.6,q[1]-Math.sin(a)*hs*.6);ctx.stroke();
 ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(q[0]-hs*Math.cos(a-.42),q[1]-hs*Math.sin(a-.42));ctx.lineTo(q[0]-hs*Math.cos(a+.42),q[1]-hs*Math.sin(a+.42));ctx.closePath();ctx.fill();ctx.globalAlpha=1;
}

/* ---------- the 3-D / 4-D solar system (canvas) ---------- */
function solar3dScale(o){                              // spreads fixed over every period (the animation never rescales)
 const {P,Q,x,y,z,sec}=o,time=z.key==='__time',vs=time?[x,y]:[x,y,z],key=['solar3',o.sig,...vs.map(v=>v.key),sec].join('|');
 if(P.cache[key])return P.cache[key];
 const dev=(a,b,cal)=>{const r=vs.map(v=>{const p=val(o,a,v,cal),q=val(o,b,v,cal);return p==null||q==null?null:p-q});return r.some(v=>v==null)?null:r};
 const spread=d=>vs.map((_,i)=>d.length?robustSpread(d.map(v=>v[i])):1);
 const far=(d,k)=>Math.max(.5,quantile(d.map(v=>Math.hypot(...v.map((u,i)=>u/k[i]))).sort((a,b)=>a-b),.95)||1);
 let out;
 if(!sec){const d=[];for(const s of Object.values(P.suns))for(const cal of Q){const v=dev(s,P.market,cal);if(v)d.push(v)}
  const k=spread(d),m=[];for(const c of P.cos){const s=P.suns[c.s];if(!s)continue;for(const cal of Q){const v=dev(c,s,cal);if(v)m.push(v)}}
  const mk=spread(m);out={k,D:far(d,k)*1.05,mk,Dm:far(m,mk)};
 }else{const s=P.suns[sec],m=[];for(const c of rotScope(P,sec))for(const cal of Q){const v=dev(c,s,cal);if(v)m.push(v)}
  const k=spread(m);out={k,D:far(m,k)};}
 return P.cache[key]=out;
}
function solar3dView(o){
 const time=o.z.key==='__time',sec=o.sec;
 o.scale3=solar3dScale(o);
 ROT.ctx={Q:o.Q,P:o.P,paint:f=>paintSolar3d(o,f)};
 const what=sec?`${esc(o.P.suns[sec].name)} — its companies around the sector sun`:'Every sector sun around the market, companies as moons';
 let out=`<div class="panel"><h3>${time?'Solar system in 3-D — time as depth':'Solar system in 4-D — three coordinates in space, time played'}: ${what}</h3>`;
 out+=`<p class="sub">Direction from the centre: → higher ${esc(vshort(o.x))}, ↑ higher ${esc(vshort(o.y))}${time?', ↗ time (oldest at the back) — an orbit becomes a spiral along the time axis':', ↗ higher '+esc(vshort(o.z))}${esc(scaleNote(o))}; distance: in typical spreads, compressed so the far ones fit. ${sec?'Every company keeps its trail of the last '+fmt(time?Math.max(o.trail,o.P.monthly?24:12):o.trail)+' '+rotUnit(o.P)+'.':'Pick a sector above to open its planets.'} Drag to turn, hover a dot for its numbers${fcOn()?'; arrows: the next step (see the table)':''}.</p>`;
 out+=rotPlayer(o.Q,o.P)+`<div class="rot-3d-wrap"><canvas id="rot-3d" class="rot-3d" role="img" aria-label="3-D solar system; the table below lists every value"></canvas><div class="rot-3d-tools"><button class="action" id="rspin" type="button">${ROT.spin?'Stop turning':'Turn slowly'}</button><button class="action" id="rreset" type="button">Front view</button></div></div>`;
 out+=`<div class="mk-legend"><span><i class="mk-key" style="background:var(--rot-sun)"></i>${sec?'Sector sun (centre)':'Market (centre axis) and sector suns'}</span><span><i class="mk-key mk-hot"></i>More 13F managers added</span><span><i class="mk-key" style="background:var(--flow-sell)"></i>More cut</span>${o.picks.map((c,i)=>`<span><i class="mk-key" style="background:${ROT_SERIES[i]}"></i>${esc(c.t)}</span>`).join('')}${fcOn()?'<span class="muted">Arrow: forecast next step · dotted: what happened</span>':''}</div></div>`;
 return out;
}
function paintSolar3d(o,f){
 const cv=document.getElementById('rot-3d');if(!cv||!cv.getContext)return;
 const ctx=cv.getContext('2d');if(!ctx)return;
 const cw=cv.clientWidth||900,ch=Math.round(Math.max(380,Math.min(680,cw*.66))),dpr=window.devicePixelRatio||1;
 if(cv.width!==Math.round(cw*dpr)||cv.height!==Math.round(ch*dpr)){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.height=ch+'px'}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,cw,ch);
 const C=rotColors(),{P,Q,x,y,z,trail,sec,picks}=o,cal=Q[f],time=z.key==='__time',S=o.scale3,font=getComputedStyle(document.body).fontFamily||'sans-serif';
 const cy_=Math.cos(ROT.yaw),sy_=Math.sin(ROT.yaw),cp=Math.cos(ROT.pitch),sp=Math.sin(ROT.pitch),Sc=Math.min(cw*.9,ch)*.3,c0x=cw/2,c0y=ch/2,Dz=6.5;
 const proj=(X,Y,Z)=>{const x1=X*cy_-Z*sy_,z1=X*sy_+Z*cy_,y2=Y*cp-z1*sp,z2=Y*sp+z1*cp,k=Dz/(Dz-z2);return [c0x+x1*k*Sc,c0y-y2*k*Sc,z2,k]};
 const vs=time?[x,y]:[x,y,z],n=Math.max(2,Math.min(time?Math.max(trail,P.monthly?24:12):trail,f+1)),f0=f-n+1;   // a spiral needs a longer window
 const tz=c=>{const i=o.qi.get(c);return i==null?null:-1+2*(i-f0)/Math.max(1,n-1)};
 const comp=(v,D,R=1)=>{const d=Math.hypot(...v);if(!d)return v.map(()=>0);const r=Math.pow(Math.min(1,d/D),.6)*R;return v.map(u=>u/d*r)};
 // a coordinate triple for an entity relative to a parent; ov = forecast values for the entity (and pv for the parent)
 const devOf=(e,par,c,k,ov,pv)=>{const r=vs.map((v,i)=>{const a=ov?ov[i]:val(o,e,v,c),b=pv?pv[i]:val(o,par,v,c);return a==null||b==null?null:(a-b)/k[i]});return r.some(v=>v==null)?null:r};
 const place=(v,zc,D,R=1,base=[0,0,0])=>{const u=comp(v,D,R);return time?[base[0]+u[0],base[1]+u[1],zc]:[base[0]+u[0],base[1]+u[1],base[2]+u[2]]};
 // the frame: box, the centre axis (time) or cross, rings of 1x / 2x the typical spread in the current slice
 const line=(a,b,col,w=1,al=1,dash)=>{const p=proj(...a),q=proj(...b);ctx.globalAlpha=al;ctx.strokeStyle=col;ctx.lineWidth=w;ctx.setLineDash(dash||[]);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1};
 const E=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
 for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]])line(E[a],E[b],C.line,1,.8);
 const zNow=time?1:0;
 if(time)line([0,0,-1],[0,0,1.12],C.sun,2,.7);else{line([-1,0,0],[1,0,0],C.muted,1,.5);line([0,-1,0],[0,1,0],C.muted,1,.5);line([0,0,-1],[0,0,1],C.muted,1,.5)}
 for(const k of [1,2,4].filter(k=>k<S.D)){const r=Math.pow(k/S.D,.6);ctx.beginPath();for(let i=0;i<=64;i++){const a=i/64*Math.PI*2,p=proj(r*Math.cos(a),r*Math.sin(a),zNow);i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])}ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.globalAlpha=.9;ctx.stroke();ctx.globalAlpha=1}
 const text=(pt,str,col,align='center',f_='11px')=>{const p=proj(...pt);ctx.fillStyle=col;ctx.font=`${f_} ${font}`;ctx.textAlign=align;ctx.fillText(str,p[0],p[1])};
 text([1.16,0,zNow],vshort(x)+' →',C.ink,'left','600 12px');text([0,1.14,zNow],'↑ '+vshort(y),C.ink,'center','600 12px');
 text(time?[0,-1.16,1.1]:[0,-1.12,1.18],time?'time → (front: '+qlabel(cal)+')':vshort(z)+' →',C.ink,'center','600 12px');
 if(time&&n>2)text([-1.05,-1.12,-1],qlabel(Q[f0]),C.muted,'left');
 const dots=[],hits=[],trails=[];
 const tipRows=(name,full,p)=>[[name+' · '+qlabel(p.cal),full||''],...vs.map(v=>[vfmt(v,p[v.key]),v.label])];
 const trace=(cals,posFn)=>cals.map(c=>posFn(c)).filter(Boolean);
 const fcEnts=[];
 if(!sec){
  const M=P.market;
  const sunAt=(s,c,ov,pv)=>{const d=devOf(s,M,c,S.k,ov,pv);return d?place(d,time?tz(c):0,S.D):null};
  const moonAt=(co,s,c)=>{const b=sunAt(s,c);if(!b)return null;const d=devOf(co,s,c,S.mk);if(!d)return null;const u=comp(d,S.Dm,.17);return time?[b[0]+u[0],b[1]+u[1],b[2]]:[b[0]+u[0],b[1]+u[1],b[2]+u[2]]};
  for(const sn of Object.values(P.suns)){const cals=Q.slice(Math.max(0,f0),f+1);const pts=trace(cals,c=>sunAt(sn,c));trails.push({pts,col:C.sun,w:1.6});
   const h=sunAt(sn,cal);if(h){const p=sn.by.get(cal);const pr=proj(...h);dots.push({x:pr[0],y:pr[1],d:pr[2],r:6*pr[3],col:C.sun,alpha:1,stroke:true,rows:tipRows(sn.name,'sector sun · '+fmt(p.n)+' companies',p),label:sn.name.replace(/ (Services)$/,'')})}
   fcEnts.push([sn,M])}
  for(const c of P.cos){const sn=P.suns[c.s];if(!sn)continue;const pi=picks.indexOf(c);const h=moonAt(c,sn,cal);if(!h)continue;const p=c.by.get(cal),pr=proj(...h);
   const n13=p&&p.f13!=null?p.f13:c.net13f,col=pi>=0?C.series[pi]:n13>0.5?C.buy:n13<-0.5?C.sell:C.dot;
   dots.push({x:pr[0],y:pr[1],d:pr[2],r:(pi>=0?4.5:1.8)*pr[3],col,alpha:pi>=0?1:.75,rows:tipRows(c.t,c.n,p),label:pi>=0?c.t:null,stroke:pi>=0});
   if(pi>=0)trails.push({pts:trace(Q.slice(Math.max(0,f0),f+1),cc=>moonAt(c,sn,cc)),col:C.series[pi],w:2})}
  const axisPts=time?[[0,0,-1],[0,0,1]]:[[0,0,0]];const mp=proj(...axisPts[axisPts.length-1]);
  dots.push({x:mp[0],y:mp[1],d:mp[2],r:10*mp[3],col:C.sun,alpha:1,stroke:true,rows:[['Market','centre · '+qlabel(cal)]],label:'Market'});
  // forecast arrows: each sun's next position around the market's next position
  if(fcOn()&&o.fc&&vs.every(v=>fcHas(o,v))){const mr=fcRow(o,M,cal),mv=mr&&vs.map(v=>fcNext(o,M,v,cal,mr));
   if(mv&&!mv.some(v=>v==null))for(const [sn] of fcEnts){const r=fcRow(o,sn,cal);if(!r)continue;const sv=vs.map(v=>fcNext(o,sn,v,cal,r));if(sv.some(v=>v==null))continue;
    const a=sunAt(sn,cal),b=time?(()=>{const d=devOf(sn,M,cal,S.k,sv,mv);return d?place(d,1.15,S.D):null})():sunAt(sn,cal,sv,mv);
    if(a&&b)dots.push({arrow:[proj(...a),proj(...b)],col:C.ink,w:1.6,d:proj(...b)[2]+.002})}}
 }else{
  const sun=P.suns[sec];
  const at=(c,cc,ov,pv)=>{const d=devOf(c,sun,cc,S.k,ov,pv);return d?place(d,time?tz(cc):0,S.D):null};
  const cos=rotScope(P,sec);
  for(const c of cos){const pi=picks.indexOf(c);const cals=Q.slice(Math.max(0,f0),f+1);const pts=trace(cals,cc=>at(c,cc));
   trails.push({pts,col:pi>=0?C.series[pi]:C.dot,w:pi>=0?2.2:1,al:pi>=0?1:.45});
   const h=at(c,cal);if(!h)continue;const p=c.by.get(cal),pr=proj(...h);const n13=p&&p.f13!=null?p.f13:c.net13f;
   const col=pi>=0?C.series[pi]:n13>0.5?C.buy:n13<-0.5?C.sell:C.dot,size=3+6*Math.sqrt(Math.max(0,(p.rev||0))/Math.max(1,...cos.map(q=>(q.by.get(cal)||{}).rev||0)));
   dots.push({x:pr[0],y:pr[1],d:pr[2],r:size*pr[3],col,alpha:1,stroke:true,rows:tipRows(c.t,c.n,p),label:pi>=0||size>6.5?c.t:null})}
  const cp_=proj(0,0,zNow);dots.push({x:cp_[0],y:cp_[1],d:cp_[2],r:9*cp_[3],col:C.sun,alpha:1,stroke:true,rows:[[sun.name+' average',qlabel(cal)]],label:null});
  if(fcOn()&&o.fc&&vs.every(v=>fcHas(o,v))){const sr=fcRow(o,sun,cal),sv=sr&&vs.map(v=>fcNext(o,sun,v,cal,sr));
   if(sv&&!sv.some(v=>v==null))for(const c of cos){const r=fcRow(o,c,cal);if(!r)continue;const cv_=vs.map(v=>fcNext(o,c,v,cal,r));if(cv_.some(v=>v==null))continue;
    const a=at(c,cal),pi=picks.indexOf(c);
    const b=(()=>{const d=devOf(c,sun,cal,S.k,cv_,sv);return d?place(d,time?1.15:0,S.D):null})();
    if(a&&b){dots.push({arrow:[proj(...a),proj(...b)],col:pi>=0?C.series[pi]:C.ink,w:pi>=0?2.2:1,d:proj(...b)[2]+.002});
     if(state.rfc==='check'){const i=o.qi.get(cal);if(i+1<Q.length){const q2=at(c,Q[i+1]);if(q2)dots.push({check:[proj(...a),proj(...q2)],col:pi>=0?C.series[pi]:C.muted,d:proj(...q2)[2]+.001})}}}}}
 }
 for(const t of trails){if(t.pts.length<2)continue;ctx.strokeStyle=t.col;ctx.lineWidth=t.w;
  for(let i=1;i<t.pts.length;i++){const a=proj(...t.pts[i-1]),b=proj(...t.pts[i]);ctx.globalAlpha=(t.al||1)*(.18+.7*i/t.pts.length);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}ctx.globalAlpha=1}
 dots.sort((a,b)=>a.d-b.d);const boxes=[];
 for(const d of dots){
  if(d.arrow){fcArrow3d(ctx,d.arrow[0],d.arrow[1],d.col,d.w);continue}
  if(d.check){ctx.setLineDash([2,3]);ctx.strokeStyle=d.col;ctx.lineWidth=1;ctx.globalAlpha=.75;ctx.beginPath();ctx.moveTo(d.check[0][0],d.check[0][1]);ctx.lineTo(d.check[1][0],d.check[1][1]);ctx.stroke();ctx.setLineDash([]);ctx.beginPath();ctx.arc(d.check[1][0],d.check[1][1],3.2,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;continue}
  ctx.globalAlpha=d.alpha;ctx.fillStyle=d.col;ctx.beginPath();ctx.arc(d.x,d.y,Math.max(1,d.r),0,Math.PI*2);ctx.fill();
  if(d.stroke){ctx.globalAlpha=1;ctx.lineWidth=1.4;ctx.strokeStyle=C.surface;ctx.stroke()}ctx.globalAlpha=1;hits.push(d);
  if(d.label){ctx.font=`500 12px ${font}`;const w=ctx.measureText(d.label).width,b=[d.x+8,d.y-20,d.x+12+w,d.y-6];
   if(!boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1])){boxes.push(b);ctx.lineWidth=3;ctx.strokeStyle=C.surface;ctx.textAlign='left';ctx.strokeText(d.label,d.x+9,d.y-9);ctx.fillStyle=C.ink;ctx.fillText(d.label,d.x+9,d.y-9)}}}
 ctx.font=`700 40px ${font}`;ctx.textAlign='right';ctx.fillStyle=C.ink;ctx.globalAlpha=.08;ctx.fillText(qlabel(cal),cw-14,ch-14);ctx.globalAlpha=1;
 ROT.hits=hits;
}

/* ---------- the table: every dot's next step and the price read from it; the backtest scorecard ---------- */
function fcNotice(o){
 if(!fcOn())return '';
 if(!o.fc)return o.fcErr?empty('The forecasts could not load ('+esc(o.fcErr)+'). They are built with the long history by the “Rotation history” workflow.'):empty('Loading the next-step forecasts…');
 const miss=[o.x,o.y,...(o.z?[o.z]:[])].filter(v=>v&&!fcHas(o,v));
 return miss.length?`<div class="explain">No forecast for ${esc(miss.map(v=>v.label).join(', '))}${o.P.monthly?' in the monthly view (only price-based coordinates are forecast month by month)':''} — pick ${esc(o.fc.vars.map(k=>(o.P.V[k]||{label:k}).label).slice(0,6).join(', '))}… for the axes to see arrows.</div>`:'';
}
function fcTable(o){
 if(!fcOn()||!o.fc)return '';
 const {P,Q}=o,cal=Q[state.rf],next=Q[state.rf+1],u=P.monthly?'month':'quarter',check=state.rfc==='check'&&next;
 // at the live origin a company that has not filed yet has no dot, but its price coordinates (from monthly closes) were forecast
 const rows=rotScope(P,o.sec).map(c=>({c,r:fcRow(o,c,cal),p:c.by.get(cal)||{},pn:next?c.by.get(next):null})).filter(a=>a.r);
 const j=o.fc._prep.vi;
 const ex=[];
 const body=rows.sort((a,b)=>((b.r[5]||0)/(b.r[4]||1))-((a.r[5]||0)/(a.r[4]||1))).map(({c,r,p,pn})=>{
  const ret=r[4]&&r[5]!=null?100*(r[5]/r[4]-1):null,act=check&&pn&&pn.ret!=null?pn.ret:null;
  const dx=fcHas(o,o.x)&&o.x.key!=='__time'?r[1][j[o.x.key]]:null,dy=fcHas(o,o.y)&&o.y.key!=='__time'?r[1][j[o.y.key]]:null;
  ex.push({ticker:c.t,origin:cal,target:next||o.fc.targets[o.fc.origins.indexOf(cal)]||'',close:r[4],price_forecast:r[5],price_lo80:r[6],price_hi80:r[7],
   [o.x.key+'_next']:dx,[o.y.key+'_next']:dy,local_divergence:r[3],...(check?{actual_return_pct:act}:{})});
  return [coLink(c),r[4]!=null?'$'+fmt(r[4],2):'—',r[5]!=null?'$'+fmt(r[5],2):'—',ret==null?'—':`<span class="${ret>=0?'positive':'negative'}">${(ret>=0?'+':'−')+fmt(Math.abs(ret),1)}%</span>`,
   r[6]!=null?'$'+fmt(r[6],2)+' – $'+fmt(r[7],2):'—',dx==null?'—':(p[o.x.key]==null?'':vfmt(o.x,p[o.x.key])+' → ')+vfmt(o.x,dx),dy==null?'—':(p[o.y.key]==null?'':vfmt(o.y,p[o.y.key])+' → ')+vfmt(o.y,dy),r[3]==null?'—':fmt(Math.abs(r[3])<.005?0:r[3],2),
   ...(check?[act==null?'—':`<span class="${act>=0?'positive':'negative'}">${(act>=0?'+':'−')+fmt(Math.abs(act),1)}%</span>${ret!=null&&act!=null?(Math.sign(ret)===Math.sign(act)?' ✓':' ✗'):''}`]:[])]});
 exported=ex;
 const live=cal===o.fc.origins[o.fc.origins.length-1];
 let out=`<div class="section-head"><h3>Next ${u} · ${fmt(rows.length)} companies · forecast made ${esc(qlabel(cal))}${live?' (live)':' (out-of-sample backtest)'}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Company','Close','Forecast price','Change','80% range',vshort(o.x)+' now → next',vshort(o.y)+' now → next','Divergence',...(check?['What happened']:[])],body);
 return out+fcScore(o);
}
function fcScore(o){
 const b=o.fc.backtest||{},st=(b.state||{}),pr=b.price||{},a=st.analog_cal||{},s=st.sun||{},l=st.linear||{},sur=st.surrogate||{};
 const ci=v=>Array.isArray(v)&&v[0]!=null?`${fmt(v[0],3)} [${fmt(v[1],3)}, ${fmt(v[2],3)}]`:'—';
 const pc=v=>v==null?'—':fmt(100*v,1)+'%';
 return `<details class="fc-score" open><summary>How these arrows did out of sample (${esc(o.P.monthly?'months':'quarters')}, walk-forward)</summary>
 <p class="sub">Every arrow before the latest was made with data public at the time and checked against the next dot. “Back to the sun” is the naive rule that every dot returns to its sector average; the placebo uses the same analogues with their next steps shuffled.</p>
 ${table(['','Arrow points the right way','Price coordinate: landing vs “back to the sun”','Cross-sectional IC of the price coordinate (95% CI)','Top − bottom fifth, next return (pts)'],[
  ['Analogues, calibrated (shown)',pc(a.arrow_hit),a.rel_landing_vs_sun==null?'—':fmt(100*a.rel_landing_vs_sun,1)+'%',ci(a.rel_landing_ic_ci),ci(a.rel_quintile_spread_ci)],
  ['Linear phase-space map (damped rotation)',pc(l.arrow_hit),l.rel_landing_vs_sun==null?'—':fmt(100*l.rel_landing_vs_sun,1)+'%',ci(l.rel_landing_ic_ci),ci(l.rel_quintile_spread_ci)],
  ['Back to the sun',pc(s.arrow_hit),'0%','—','—'],
  ['Placebo (shuffled analogues)',pc(sur.arrow_hit),sur.rel_landing_vs_sun==null?'—':fmt(100*sur.rel_landing_vs_sun,1)+'%',ci(sur.rel_landing_ic_ci),ci(sur.rel_quintile_spread_ci)]])}
 <p class="sub">Price read from the arrows: ${fmt(pr.n||0)} forecasts over ${fmt(pr.periods||0)} periods; direction right ${pc(pr.price_direction_hit)} against ${pc(pr.share_of_up_moves)} of moves that were up anyway; 80% range held ${pc(pr.coverage80)}, 95% range ${pc(pr.coverage95)}; IC ${ci(pr.ic_calibrated_ci)}. The arrows describe how dots move — mostly back toward their sun, and slow coordinates (volatility, momentum, distance from the high, margins) better than naive rules — but the price coordinate itself has shown no reliable edge: read the price column as a range, not a call.</p></details>`;
}

/* ---------- the RRG: arrows on the weekly 14-week chart, price mapped back from the next point ---------- */
function rrgFcLoad(){const m=marketData('history/chaos-rrg');if(!m.data)return null;const d=m.data;
 if(!d._by){d._by=new Map(Object.entries(d.lines||{}).map(([id,rows])=>[id,new Map(rows.map(r=>[d.weeks[r[0]],r]))]))}return d}
function rrgFcLayer(o,f,sx,sy){
 if(!fcOn()||o.freq!=='w'||o.n!==14)return '';
 const d=rrgFcLoad();if(!d)return '';
 let s='';const day=o.Q[f];
 for(const l of o.lines){const m=d._by.get(l.e.id);const r=m&&m.get(day);if(!r)continue;const c=l.calc;if(c.x[f]==null||c.y[f]==null)continue;
  const p=[sx(c.x[f]),sy(c.y[f])],q=[sx(r[3]),sy(r[4])];
  if(state.rfc==='check'&&c.x[f+1]!=null)s+=fcCheckSvg(p,[sx(c.x[f+1]),sy(c.y[f+1])],l.col);
  const rows=[[l.e.name+' · next week','forecast made '+rrgDay(day)],[fmt(r[3],2)+' / '+fmt(r[4],2),'RS-Ratio / RS-Momentum next'],
   [(r[5]>=0?'+':'−')+fmt(Math.abs(100*r[5]),2)+'%','vs '+(o.D.benchmark||'SPY')+', read back from the point'],...(r[7]!=null?[['$'+fmt(r[7],2),'close implied (now $'+fmt(r[6],2)+')']]:[])];
  s+=`<g data-tip="${tip(rows)}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,l.col,2)}</g>`}
 return s;
}
function rrgFcNote(o){
 if(!fcOn())return '';
 if(o.freq!=='w'||o.n!==14)return '<div class="explain">Next-step arrows on the RRG are computed for the weekly chart with the 14-week window.</div>';
 const d=rrgFcLoad();if(!d)return '<div class="explain">Loading the RRG forecasts…</div>';
 const b=d.backtest||{},a=b.analog||{},r=b.rotation||{},pi=b.price_inversion||{};
 const pc=v=>v==null?'—':fmt(100*v,1)+'%',ci=v=>Array.isArray(v)&&v[0]!=null?`${fmt(v[0],3)} [${fmt(v[1],3)}, ${fmt(v[2],3)}]`:'—';
 return `<details class="fc-score"><summary>How the RRG arrows did out of sample (weekly, ${esc(b.from||'')} – ${esc(b.to||'')})</summary><p class="sub">Arrow points the right way: analogues ${pc(a.direction_hit)}, “keep rotating at the same speed” ${pc(r.direction_hit)}. Step skill vs standing still: analogues ${pc(a.step_skill_vs_persist)}, rotation ${pc(r.step_skill_vs_persist)}. Next week's return read back from the forecast point: IC ${ci(pi.ic_inverted_ci)}, sign right ${pc(pi.sign_hit_inverted)}. The rotation is smooth by construction (both coordinates are averages of the past), so where the dot goes next is easy; what the price does next is not.</p></details>`;
}
