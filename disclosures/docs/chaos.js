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
const FC_MODES=[['','Off'],['next','Next step — analogues (arrows + price)'],['track','Last forecast (dashed range) + next forecast + error'],['check','Next step + what happened (backtest)']];
const fcOn=()=>state.rfc==='next'||state.rfc==='check'||state.rfc==='track';
const fcTrack=()=>state.rfc==='track';
/* "track": the forecast made one period earlier for the period shown — its 80% range as a dashed outline in the
   last-forecast colour, a hollow diamond at its centre and the error line to where the dot actually is (green: inside the
   range, red: outside); the forecast for the next period as a solid arrow ending in a filled, undashed range. */
function fcPrevSvg(q,rx,ry,a,tipRows,label){
 const inside=rx>0&&ry>0?((a[0]-q[0])/rx)**2+((a[1]-q[1])/ry)**2<=1:Math.hypot(a[0]-q[0],a[1]-q[1])<3;
 const d=4.2,dm=`M${q[0].toFixed(1)},${(q[1]-d).toFixed(1)} l${d},${d} l${-d},${d} l${-d},${-d} z`;
 let s=`<g data-tip="${tip(tipRows.concat([[inside?'inside':'outside','the 80% range of that forecast']]))}" tabindex="-1" class="mk-hit">`;
 if(rx>0&&ry>0)s+=`<ellipse class="fc-prev" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" rx="${Math.max(2,rx).toFixed(1)}" ry="${Math.max(2,ry).toFixed(1)}"/>`;
 s+=`<line class="fc-err ${inside?'fc-err-in':'fc-err-out'}" x1="${q[0].toFixed(1)}" y1="${q[1].toFixed(1)}" x2="${a[0].toFixed(1)}" y2="${a[1].toFixed(1)}"/><path class="fc-prev-dot" d="${dm}"/>`;
 if(label)s+=`<text class="fc-err-label mk-halo" x="${((q[0]+a[0])/2+6).toFixed(1)}" y="${((q[1]+a[1])/2-4).toFixed(1)}">${esc(label)}</text>`;
 return s+'</g>';
}
const fcNextCone=(q,rx,ry,col)=>rx>0&&ry>0?`<ellipse class="fc-next-cone" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" rx="${Math.max(2,rx).toFixed(1)}" ry="${Math.max(2,ry).toFixed(1)}" style="fill:${col}"/>`:'';
function fcErrLabel(o,ent,prev,cal,rowp){           // short error label: the price error when there is a price, else ✓ / ✗
 const r=fcRow(o,ent,cal);
 if(rowp[5]!=null&&r&&r[4]!=null){const e=100*(r[4]/rowp[5]-1);return 'err '+(e>=0?'+':'−')+fmt(Math.abs(e),1)+'%'}
 return '';
}
function fcPrevTip(o,ent,name,prev,cal,rowp){       // what the last forecast said, what happened, the error
 const out=[[name+' · forecast made '+qlabel(prev),'for '+qlabel(cal)]];
 for(const v of [o.x,o.y]){if(!fcHas(o,v)||v.key==='__time')continue;const j=o.fc._prep.vi[v.key],p=ent.by.get(cal);
  const f=rowp[1][j],h=rowp[2]&&rowp[2][j],a=p?p[v.key]:null;
  out.push([vfmt(v,f)+(h!=null?' ± '+vfmt({...v,centred:false},h).replace(/^−/,''):'')+' → '+vfmt(v,a)+(a!=null&&f!=null?'  (error '+vfmt({...v,centred:true},a-f)+')':''),v.label+': forecast → actual'])}
 const r=fcRow(o,ent,cal);
 if(rowp[5]!=null&&r&&r[4]!=null)out.push(['$'+fmt(rowp[5],2)+' → $'+fmt(r[4],2)+'  (error '+(r[4]>=rowp[5]?'+':'−')+fmt(Math.abs(100*(r[4]/rowp[5]-1)),1)+'%)',`price forecast → actual${rowp[6]!=null?` · 80% range $${fmt(rowp[6],2)}–$${fmt(rowp[7],2)}`:''}`]);
 return out;
}

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
 if(row[5]!=null)out.push(['$'+fmt(row[5],2)+(row[6]!=null?` (80%: $${fmt(row[6],2)}–$${fmt(row[7],2)})`:''),`price next ${o.P.monthly?'month':'quarter'}-end · now $${fmt(row[4],2)} · ${row[8]===1?'gravity + tidal model':'analogues'}`]);
 return out;
}

/* ---------- arrows on the momentum clock (SVG) ---------- */
function fcClockLayer(o,cal,px,L){
 if(!fcOn()||!o.fc)return '';
 if(!fcHas(o,o.x)||!fcHas(o,o.y))return '';
 let s='';const check=state.rfc==='check',track=fcTrack(),i0=o.qi.get(cal),prev=i0>0?o.Q[i0-1]:null;
 const one=(ent,name,col,w,cone)=>{const row=fcRow(o,ent,cal);
  const a=val(o,ent,o.x,cal),b=val(o,ent,o.y,cal);if(a==null||b==null)return;
  if(track&&cone&&prev){const rp=fcRow(o,ent,prev),pa=rp&&fcNext(o,ent,o.x,prev,rp),pb=rp&&fcNext(o,ent,o.y,prev,rp);
   if(pa!=null&&pb!=null){const hx=fcHalf(o,ent,o.x,prev,rp),hy=fcHalf(o,ent,o.y,prev,rp),q0=px(pa,pb),e0=px(pa+hx,pb+hy),ac=px(a,b);
    s+=fcPrevSvg(q0,Math.abs(e0[0]-q0[0]),Math.abs(e0[1]-q0[1]),ac,fcPrevTip(o,ent,name,prev,cal,rp),w>=2?fcErrLabel(o,ent,prev,cal,rp):'')}}
  if(!row)return;
  const na=fcNext(o,ent,o.x,cal,row),nb=fcNext(o,ent,o.y,cal,row);
  if(na==null||nb==null)return;
  const p=px(a,b),q=px(na,nb);
  if(cone){const hx=fcHalf(o,ent,o.x,cal,row),hy=fcHalf(o,ent,o.y,cal,row),e1=px(na+hx,nb+hy);
   s+=track?fcNextCone(q,Math.abs(e1[0]-q[0]),Math.abs(e1[1]-q[1]),col):`<ellipse class="fc-cone" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" rx="${Math.abs(e1[0]-q[0]).toFixed(1)}" ry="${Math.abs(e1[1]-q[1]).toFixed(1)}" style="stroke:${col}"/>`}
  if(check){const xa=fcActual(o,ent,o.x,cal),ya=fcActual(o,ent,o.y,cal);if(xa!=null&&ya!=null)s+=fcCheckSvg(p,px(xa,ya),col)}
  s+=`<g data-tip="${tip(fcTipRows(o,ent,name,cal,row))}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,col,w)}</g>`};
 for(const c of L.cloud)if(!L.picks.some(t=>t.ent===c))one(c,c.t,'var(--flow-dot)',.9,false);
 for(const t of L.suns)one(t.ent,t.name,'var(--muted)',1.4,track);
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
 let s='';const track=fcTrack(),i0=o.qi.get(cal),prev=i0>0?o.Q[i0-1]:null,mrp=prev&&fcRow(o,M,prev);
 const mpx=mrp&&fcNext(o,M,o.x,prev,mrp),mpy=mrp&&fcNext(o,M,o.y,prev,mrp);
 for(const sn of Object.values(o.P.suns)){const r=fcRow(o,sn,cal);if(!r)continue;
  const a=val(o,sn,o.x,cal),b=val(o,sn,o.y,cal),na=fcNext(o,sn,o.x,cal,r),nb=fcNext(o,sn,o.y,cal,r);if(a==null||b==null||na==null||nb==null)continue;
  const p=posXY(a,b,mx0,my0),q=posXY(na,nb,mx,my);if(!p||!q)continue;
  if(track){const rp=fcRow(o,sn,prev),pa=rp&&fcNext(o,sn,o.x,prev,rp),pb=rp&&fcNext(o,sn,o.y,prev,rp);
   if(pa!=null&&pb!=null&&mpx!=null&&mpy!=null){const hx=fcHalf(o,sn,o.x,prev,rp),hy=fcHalf(o,sn,o.y,prev,rp),q0=posXY(pa,pb,mpx,mpy),e0=posXY(pa+hx,pb+hy,mpx,mpy);
    s+=fcPrevSvg(q0,Math.abs(e0[0]-q0[0]),Math.abs(e0[1]-q0[1]),p,fcPrevTip(o,sn,sn.name,prev,cal,rp),'')}
   const hx=fcHalf(o,sn,o.x,cal,r),hy=fcHalf(o,sn,o.y,cal,r),e1=posXY(na+hx,nb+hy,mx,my);s+=fcNextCone(q,Math.abs(e1[0]-q[0]),Math.abs(e1[1]-q[1]),'var(--rot-sun)')}
  if(state.rfc==='check'){const xa=fcActual(o,sn,o.x,cal),ya=fcActual(o,sn,o.y,cal),ma=fcActual(o,M,o.x,cal),mb=fcActual(o,M,o.y,cal);if(xa!=null&&ya!=null&&ma!=null&&mb!=null){const qa=posXY(xa,ya,ma,mb);if(qa)s+=fcCheckSvg(p,qa,'var(--rot-sun)')}}
  s+=`<g data-tip="${tip(fcTipRows(o,sn,sn.name,cal,r))}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,'var(--rot-sun)',1.8)}</g>`}
 return s;
}
function fcSolarSector(o,cal,sun,posXY){              // posXY(cx, cy, sunX, sunY) -> px
 if(!fcOn()||!o.fc||!fcHas(o,o.x)||!fcHas(o,o.y))return '';
 const sr=fcRow(o,sun,cal);if(!sr)return '';
 const sx=fcNext(o,sun,o.x,cal,sr),sy=fcNext(o,sun,o.y,cal,sr),sx0=val(o,sun,o.x,cal),sy0=val(o,sun,o.y,cal);if(sx==null||sy==null)return '';
 let s='';const check=state.rfc==='check',track=fcTrack(),i0=o.qi.get(cal),prev=i0>0?o.Q[i0-1]:null,srp=prev&&fcRow(o,sun,prev);
 const spx=srp&&fcNext(o,sun,o.x,prev,srp),spy=srp&&fcNext(o,sun,o.y,prev,srp);
 const cos=rotScope(o.P,o.sec),big=new Set(cos.slice().sort((a,b)=>((b.by.get(cal)||{}).rev||0)-((a.by.get(cal)||{}).rev||0)).slice(0,6));
 for(const c of cos){const r=fcRow(o,c,cal);if(!r)continue;
  const a=val(o,c,o.x,cal),b=val(o,c,o.y,cal),na=fcNext(o,c,o.x,cal,r),nb=fcNext(o,c,o.y,cal,r);if(a==null||b==null||na==null||nb==null)continue;
  const p=posXY(a,b,sx0,sy0),q=posXY(na,nb,sx,sy);if(!p||!q)continue;
  const pi=o.picks.indexOf(c),col=pi>=0?ROT_SERIES[pi]:'var(--ink-2)';
  if(track&&(pi>=0||(!o.picks.length&&big.has(c)))){const rp=fcRow(o,c,prev),pa=rp&&fcNext(o,c,o.x,prev,rp),pb=rp&&fcNext(o,c,o.y,prev,rp);
   if(pa!=null&&pb!=null&&spx!=null&&spy!=null){const hx=fcHalf(o,c,o.x,prev,rp),hy=fcHalf(o,c,o.y,prev,rp),q0=posXY(pa,pb,spx,spy),e0=posXY(pa+hx,pb+hy,spx,spy);
    s+=fcPrevSvg(q0,Math.abs(e0[0]-q0[0]),Math.abs(e0[1]-q0[1]),p,fcPrevTip(o,c,c.t,prev,cal,rp),pi>=0?fcErrLabel(o,c,prev,cal,rp):'')}
   const hx=fcHalf(o,c,o.x,cal,r),hy=fcHalf(o,c,o.y,cal,r),e1=posXY(na+hx,nb+hy,sx,sy);s+=fcNextCone(q,Math.abs(e1[0]-q[0]),Math.abs(e1[1]-q[1]),col)}
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
 const {P,Q}=o,cal=Q[state.rf],next=Q[state.rf+1],u=P.monthly?'month':'quarter',check=state.rfc==='check'&&next,prev=state.rf>0?Q[state.rf-1]:null,track=fcTrack()&&prev;
 // at the live origin a company that has not filed yet has no dot, but its price coordinates (from monthly closes) were forecast
 const rows=rotScope(P,o.sec).map(c=>({c,r:fcRow(o,c,cal),p:c.by.get(cal)||{},pn:next?c.by.get(next):null})).filter(a=>a.r);
 const j=o.fc._prep.vi;
 const ex=[];
 const body=rows.sort((a,b)=>((b.r[5]||0)/(b.r[4]||1))-((a.r[5]||0)/(a.r[4]||1))).map(({c,r,p,pn})=>{
  const ret=r[4]&&r[5]!=null?100*(r[5]/r[4]-1):null,act=check&&pn&&pn.ret!=null?pn.ret:null;
  const rp=track?fcRow(o,c,prev):null,pe=rp&&rp[5]!=null&&r[4]!=null?100*(r[4]/rp[5]-1):null,pin=rp&&rp[6]!=null&&r[4]!=null?r[4]>=rp[6]&&r[4]<=rp[7]:null;
  const dx=fcHas(o,o.x)&&o.x.key!=='__time'?r[1][j[o.x.key]]:null,dy=fcHas(o,o.y)&&o.y.key!=='__time'?r[1][j[o.y.key]]:null;
  ex.push({ticker:c.t,origin:cal,target:next||o.fc.targets[o.fc.origins.indexOf(cal)]||'',close:r[4],price_forecast:r[5],price_lo80:r[6],price_hi80:r[7],
   [o.x.key+'_next']:dx,[o.y.key+'_next']:dy,local_divergence:r[3],price_model:r[8]===1?'gravity':'analogues',...(check?{actual_return_pct:act}:{}),
   ...(track?{last_forecast_made:prev,last_forecast_price:rp?rp[5]:null,last_lo80:rp?rp[6]:null,last_hi80:rp?rp[7]:null,actual_close:r[4],last_error_pct:pe,last_inside80:pin}:{})});
  return [coLink(c),r[4]!=null?'$'+fmt(r[4],2):'—',r[5]!=null?'$'+fmt(r[5],2)+(r[8]===1?'':' <span class="muted" title="price from the analogues (the gravity model does not cover this company)">ᴬ</span>'):'—',ret==null?'—':`<span class="${ret>=0?'positive':'negative'}">${(ret>=0?'+':'−')+fmt(Math.abs(ret),1)}%</span>`,
   r[6]!=null?'$'+fmt(r[6],2)+' – $'+fmt(r[7],2):'—',dx==null?'—':(p[o.x.key]==null?'':vfmt(o.x,p[o.x.key])+' → ')+vfmt(o.x,dx),dy==null?'—':(p[o.y.key]==null?'':vfmt(o.y,p[o.y.key])+' → ')+vfmt(o.y,dy),...(track?[]:[r[3]==null?'—':fmt(Math.abs(r[3])<.005?0:r[3],2)]),
   ...(check?[act==null?'—':`<span class="${act>=0?'positive':'negative'}">${(act>=0?'+':'−')+fmt(Math.abs(act),1)}%</span>${ret!=null&&act!=null?(Math.sign(ret)===Math.sign(act)?' ✓':' ✗'):''}`]:[]),
   ...(track?[rp&&rp[5]!=null?'$'+fmt(rp[5],2)+` <span class="muted">${'$'+fmt(rp[6],2)+'–'+fmt(rp[7],2)}</span>`:'—',pe==null?'—':`<span class="${pin?'led-ok':'led-no'}">${(pe>=0?'+':'−')+fmt(Math.abs(pe),1)}% ${pin?'✓':'✗'}</span>`]:[])]});
 exported=ex;
 const live=cal===o.fc.origins[o.fc.origins.length-1];
 const warm=!live&&o.fc.test_from&&cal<o.fc.test_from;
 let out=`<div class="section-head"><h3>Next ${u} · ${fmt(rows.length)} companies · forecast made ${esc(qlabel(cal))}${live?' (live)':warm?' (in-sample warm-up)':' (out-of-sample backtest)'}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Company','Close','Forecast price','Change','80% range',vshort(o.x)+' now → next',vshort(o.y)+' now → next',...(track?[]:['Divergence']),...(check?['What happened']:[]),...(track?['Last forecast for '+qlabel(cal)+' (80%)','Error vs close']:[])],body);
 return (track?fcLastSummary(o,rows.map(a=>a.c),prev,cal):'')+fcPriceTrack(o)+out+fcScore(o);
}
function fcLastSummary(o,cos,prev,cal){              // how last period's forecasts did for the period shown
 const e=[],inside=[],dir=[];
 for(const c of cos){const rp=fcRow(o,c,prev),r=fcRow(o,c,cal);if(!rp||!r||rp[5]==null||r[4]==null||!rp[4])continue;
  e.push(100*(r[4]/rp[5]-1));if(rp[6]!=null)inside.push(r[4]>=rp[6]&&r[4]<=rp[7]);dir.push(Math.sign(rp[5]-rp[4])===Math.sign(r[4]-rp[4]))}
 if(!e.length)return '';
 const m=a=>a.reduce((x,y)=>x+y,0)/a.length,abs=e.map(Math.abs).sort((a,b)=>a-b);
 return `<div class="explain fc-last"><b>Last forecast vs what happened</b> — made at ${esc(qlabel(prev))} for ${esc(qlabel(cal))}, ${fmt(e.length)} companies: average error (actual − forecast) ${fmt(m(e),1)}% (median miss ${fmt(abs[Math.floor(abs.length/2)],1)}%), ${fmt(100*m(inside.map(Number)),0)}% closed inside the 80% range, direction right ${fmt(100*m(dir.map(Number)),0)}%. On the chart: <span class="fc-key fc-key-prev"></span> the last forecast's 80% range (dashed) and centre ◇, <span class="fc-key fc-key-in"></span>/<span class="fc-key fc-key-out"></span> the error to where the dot is (inside / outside the range), <span class="fc-key fc-key-next"></span> the next forecast (arrow and filled range).</div>`;
}
/* Price track: each period's close, the forecast made one period earlier for it (dashed 80% range, hollow diamond) with
   the error, and the forecast for the next period (filled fan and solid diamond). Shared by the Next-step table and the
   track record (ledger.js). pts: [{label, close, f:{p,lo,hi}|null, live}] oldest first; next: {label, p, lo, hi} | null */
function fcPriceSvg(pts,next,opt={}){
 const W=opt.w||460,H=opt.h||210,L=50,R=next?58:12,T=12,B=26,n=pts.length+(next?1:0);
 const vals=[];pts.forEach(p=>{if(p.close!=null)vals.push(p.close);if(p.f){vals.push(p.f.p);if(p.f.lo!=null)vals.push(p.f.lo,p.f.hi)}});if(next){vals.push(next.p);if(next.lo!=null)vals.push(next.lo,next.hi)}
 const fin=vals.filter(v=>v!=null&&Number.isFinite(v)&&v>0);if(fin.length<2)return empty('Not enough forecasts yet');
 const cl=pts.map(p=>p.close).filter(v=>v>0),cmin=Math.min(...cl),cmax=Math.max(...cl);
 let lo=Math.max(Math.min(...fin),cmin/2.2),hi=Math.min(Math.max(...fin),cmax*2.2);const pad=(Math.log(hi)-Math.log(lo))*.06||.05;lo*=Math.exp(-pad);hi*=Math.exp(pad);
 const x=i=>L+(n<2?.5:i/(n-1))*(W-L-R),y=v=>T+(Math.log(hi)-Math.log(Math.max(lo,Math.min(hi,v))))/(Math.log(hi)-Math.log(lo))*(H-T-B);
 let s=`<svg class="plot mk-plot fc-price" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.title||'Price forecasts')}">`;
 const lt=[];for(let e=Math.floor(Math.log10(lo));e<=Math.ceil(Math.log10(hi));e++)for(const m of (Math.log10(hi/lo)<.6?[1,1.5,2,2.5,3,4,5,6,8]:[1,2,5]))lt.push(m*10**e);
 let lastY=1e9;lt.filter(v=>v>lo&&v<hi).forEach(v=>{if(Math.abs(y(v)-lastY)<20)return;lastY=y(v);s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-6}" y="${y(v)+4}" text-anchor="end">$${fmt(v,v<10?2:0)}</text>`});
 const act=pts.map((p,i)=>[i,p]).filter(a=>a[1].close!=null);
 pts.forEach((p,i)=>{if(!p.f||p.f.p==null)return;const X=x(i),d=4;
  const inside=p.close!=null&&p.f.lo!=null?p.close>=p.f.lo&&p.close<=p.f.hi:null,err=p.close!=null?100*(p.close/p.f.p-1):null;
  const rows=[[p.label,'forecast made the period before'+(p.live?' (live)':'')],['$'+fmt(p.f.p,2)+(p.f.lo!=null?` (80%: $${fmt(p.f.lo,2)}–$${fmt(p.f.hi,2)})`:''),'forecast'],[p.close==null?'pending':'$'+fmt(p.close,2),'actual close'],...(err!=null?[[(err>=0?'+':'−')+fmt(Math.abs(err),1)+'%'+(inside==null?'':inside?' · inside':' · outside'),'error (actual vs forecast)']]:[])];
  s+=`<g data-tip="${tip(rows)}" tabindex="-1" class="mk-hit"><rect x="${X-7}" y="${T}" width="14" height="${H-T-B}" fill="transparent"/>`;
  if(p.f.lo!=null)s+=`<line class="fc-prev-range" x1="${X}" x2="${X}" y1="${y(p.f.hi)}" y2="${y(p.f.lo)}"/><line class="fc-prev-cap" x1="${X-4}" x2="${X+4}" y1="${y(p.f.hi)}" y2="${y(p.f.hi)}"/><line class="fc-prev-cap" x1="${X-4}" x2="${X+4}" y1="${y(p.f.lo)}" y2="${y(p.f.lo)}"/>`;
  if(p.close!=null)s+=`<line class="fc-err ${inside===false?'fc-err-out':'fc-err-in'}" x1="${X+3}" x2="${X+3}" y1="${y(p.f.p)}" y2="${y(p.close)}"/>`;
  s+=`<path class="fc-prev-dot" d="M${X},${y(p.f.p)-d} l${d},${d} l${-d},${d} l${-d},${-d} z"/></g>`});
 if(act.length>1)s+=`<path class="fc-price-line" d="${act.map(([i,p],k)=>(k?'L':'M')+x(i).toFixed(1)+','+y(p.close).toFixed(1)).join('')}"/>`;
 act.forEach(([i,p])=>{s+=`<circle class="fc-price-dot" cx="${x(i)}" cy="${y(p.close)}" r="2.6"/>`});
 if(next&&next.p!=null&&act.length){const [li,lp]=act[act.length-1],X0=x(li),X1=x(n-1),d=4.6;
  if(next.lo!=null)s+=`<path class="fc-next-fan" style="fill:${opt.col||'var(--rot-1)'}" d="M${X0},${y(lp.close)} L${X1},${y(next.hi)} L${X1},${y(next.lo)} Z"/>`;
  s+=`<line class="fc-next-line" style="stroke:${opt.col||'var(--rot-1)'}" x1="${X0}" y1="${y(lp.close)}" x2="${X1}" y2="${y(next.p)}"/>`;
  s+=`<g data-tip="${tip([[next.label,'next forecast'],['$'+fmt(next.p,2)+(next.lo!=null?` (80%: $${fmt(next.lo,2)}–$${fmt(next.hi,2)})`:''),'forecast close'],[(next.p>=lp.close?'+':'−')+fmt(Math.abs(100*(next.p/lp.close-1)),1)+'%','vs the last close']])}" tabindex="-1" class="mk-hit"><path class="fc-next-dot" style="fill:${opt.col||'var(--rot-1)'}" d="M${X1},${y(next.p)-d} l${d},${d} l${-d},${d} l${-d},${-d} z"/></g>`;
  s+=`<text class="axis" x="${X1+7}" y="${y(next.p)+4}">$${fmt(next.p,next.p<10?2:0)}</text>`}
 s+=`<text class="axis" x="${L}" y="${H-6}">${esc(pts[0].label)}</text><text class="axis" x="${x(n-1)}" y="${H-6}" text-anchor="end">${esc(next?next.label:pts[pts.length-1].label)}</text>`;
 return s+'</svg>';
}
function fcPriceStats(pts){                           // mean |error|, share inside the range, direction right
 const r=pts.filter(p=>p.f&&p.f.p!=null&&p.close!=null);if(!r.length)return '';
 const ae=r.map(p=>Math.abs(100*(p.close/p.f.p-1))),ins=r.filter(p=>p.f.lo!=null),hit=r.filter(p=>p.prev!=null);
 return `${fmt(r.length)} forecasts: mean miss ${fmt(ae.reduce((a,b)=>a+b,0)/ae.length,1)}%`+(ins.length?`, ${fmt(100*ins.filter(p=>p.close>=p.f.lo&&p.close<=p.f.hi).length/ins.length,0)}% inside the 80% range`:'')
  +(hit.length?`, direction right ${fmt(100*hit.filter(p=>Math.sign(p.f.p-p.prev)===Math.sign(p.close-p.prev)).length/hit.length,0)}%`:'');
}
function fcPriceTrack(o){                             // the picked companies (or the sector's largest) on the Next-step charts
 if(!o.fc)return '';
 const f=state.rf,N=o.P.monthly?24:16,cals=o.Q.slice(Math.max(0,f-N+1),f+1),u=o.P.monthly?'month':'quarter';
 let cos=o.picks.filter(c=>c.t);
 if(!cos.length)cos=rotScope(o.P,o.sec).slice().sort((a,b)=>((b.by.get(o.Q[f])||{}).rev||0)-((a.by.get(o.Q[f])||{}).rev||0)).slice(0,3);
 const panels=cos.slice(0,4).map((c,ci)=>{const col=o.picks.length?ROT_SERIES[o.picks.indexOf(c)]:'var(--rot-1)';
  const live=o.fc.origins[o.fc.origins.length-1];
  const pts=cals.map((cal,k)=>{const r=fcRow(o,c,cal),gi=o.qi.get(cal),pc=gi>0?o.Q[gi-1]:null,rp=pc&&fcRow(o,c,pc);
   return {label:qlabel(cal),close:r&&r[4]!=null?r[4]:null,prev:rp&&rp[4]!=null?rp[4]:null,f:rp&&rp[5]!=null?{p:rp[5],lo:rp[6],hi:rp[7]}:null,live:pc===live}});
  const r=fcRow(o,c,o.Q[f]),tgt=o.fc.targets[o.fc.origins.indexOf(o.Q[f])];
  const next=r&&r[5]!=null?{label:qlabel(tgt||'next'),p:r[5],lo:r[6],hi:r[7]}:null;
  return `<div class="panel"><h3>${esc(c.t)} <span class="muted">${esc(c.n||'')}</span></h3><p class="sub">Each ${u}'s close (dots), the forecast made the ${u} before (dashed 80% range, ◇) and its error (green inside the range, red outside); the filled fan is the forecast for ${esc(next?next.label:'the next '+u)}. ${esc(fcPriceStats(pts))}.</p>${fcPriceSvg(pts,next,{col,title:c.t+' price forecasts'})}</div>`});
 return panels.length?`<div class="rot-multiples">${panels.join('')}</div>`:'';
}
function fcScore(o){
 const b=o.fc.backtest||{},st=(b.state||{}),pr=b.price||{},pa=b.price_analog||{},a=st.analog_cal||{},s=st.sun||{},l=st.linear||{},sur=st.surrogate||{};
 const ci=v=>Array.isArray(v)&&v[0]!=null?`${fmt(v[0],3)} [${fmt(v[1],3)}, ${fmt(v[2],3)}]`:'—';
 const pc=v=>v==null?'—':fmt(100*v,1)+'%',grav=b.price_model==='gravity',u=o.P.monthly?'months':'quarters';
 const edge=Array.isArray(pr.ic_calibrated_ci)&&pr.ic_calibrated_ci[1]>0;
 const verdict=edge?`The price column has shown a small but real edge here (its interval excludes zero); it is still a forecast with a wide range, not a certainty.`
  :`On this site's ${fmt(pr.n?Math.round(pr.n/Math.max(1,pr.periods)):0)} or so companies per ${u.slice(0,-1)} the price column's edge is not yet distinguishable from zero${grav?' — the same gravity model is significant on the broad test of about 1,230 companies a week (IC ≈ 0.02–0.03; disclosures/notes/gravity-pendulum)':''}; read the price as a calibrated range.`;
 return `<details class="fc-score" open><summary>How these arrows did out of sample (${esc(u)}, walk-forward)</summary>
 <p class="sub">Every arrow before the latest was made walk-forward — its library held only steps public at the time (the caveats below say what is still retrospective) — and checked against the next dot. “Back to the sun” is the naive rule that every dot returns to its sector average; the placebo uses the same analogues with their next steps shuffled.${grav?' The price coordinate (stock vs the S&amp;P) and the price come from the gravity + tidal model: the short pendulum pulls a company back toward its sector, the long one pushes (momentum), and the sector\'s own motion carries to its companies. The other coordinates come from the analogues.':''}</p>
 ${table(['Arrows (direction of the move)','Points the right way','Placebo','Back to the sun'],[['Analogues, calibrated',pc(a.arrow_hit),pc(sur.arrow_hit),pc(s.arrow_hit)],['Linear phase-space map',pc(l.arrow_hit),'—','—']])}
 ${table(['Price of the next '+u.slice(0,-1),'Forecasts','Cross-sectional IC (95% CI)','Direction right','Up anyway','80% range held','95% range held'],[
  ...(grav?[['Gravity + tidal (shown)',fmt(pr.n||0),ci(pr.ic_calibrated_ci),pc(pr.price_direction_hit),pc(pr.share_of_up_moves),pc(pr.coverage80),pc(pr.coverage95)]]:[]),
  [grav?'Analogues (for comparison)':'Analogues (shown)',fmt((grav?pa:pr).n||0),ci((grav?pa:pr).ic_calibrated_ci),pc((grav?pa:pr).price_direction_hit),pc((grav?pa:pr).share_of_up_moves),pc((grav?pa:pr).coverage80),pc((grav?pa:pr).coverage95)]])}
 <p class="sub">${verdict} The arrows' direction is reliable mostly because dots fall back toward their sun. Survivorship: today's companies only, which flatters every model.</p>${(o.fc.caveats||[]).map(c=>`<p class="sub">${esc(c)}</p>`).join('')}</details>`;
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
  if(fcTrack()){const rp=f>0&&m.get(o.Q[f-1]);
   if(rp&&rp[3]!=null){const q0=[sx(rp[3]),sy(rp[4])],rx=rp[9]!=null?Math.abs(sx(rp[3]+rp[9])-q0[0]):0,ry=rp[10]!=null?Math.abs(sy(rp[4]+rp[10])-q0[1]):0;
    const ex=c.x[f]-rp[3],ey=c.y[f]-rp[4],pe=rp[7]!=null&&r[6]!=null?100*(r[6]/rp[7]-1):null;
    s+=fcPrevSvg(q0,rx,ry,p,[[l.e.name+' · forecast made '+rrgDay(o.Q[f-1]),'for '+rrgDay(day)],[fmt(rp[3],2)+' / '+fmt(rp[4],2)+' → '+fmt(c.x[f],2)+' / '+fmt(c.y[f],2),'RS-Ratio / RS-Momentum: forecast → actual'],
     [(ex>=0?'+':'−')+fmt(Math.abs(ex),2)+' / '+(ey>=0?'+':'−')+fmt(Math.abs(ey),2)+'  (distance '+fmt(Math.hypot(ex,ey),2)+')','error'],...(pe!=null?[['$'+fmt(rp[7],2)+' → $'+fmt(r[6],2)+' ('+(pe>=0?'+':'−')+fmt(Math.abs(pe),1)+'%)','close: forecast → actual']]:[])],'')}
   if(r[9]!=null)s+=fcNextCone(q,Math.abs(sx(r[3]+r[9])-q[0]),Math.abs(sy(r[4]+r[10])-q[1]),l.col)}
  const rows=[[l.e.name+' · next week','forecast made '+rrgDay(day)],[fmt(r[3],2)+' / '+fmt(r[4],2),'RS-Ratio / RS-Momentum next'],
   [(r[5]>=0?'+':'−')+fmt(Math.abs(100*r[5]),2)+'%','vs '+(o.D.benchmark||'SPY')+(r[8]===1?', gravity + tidal forecast (the point follows from it)':', read back from the point')],...(r[7]!=null?[['$'+fmt(r[7],2),'close implied (now $'+fmt(r[6],2)+')']]:[])];
  s+=`<g data-tip="${tip(rows)}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,l.col,2)}</g>`}
 return s;
}
function rrgFcNote(o){
 if(!fcOn())return '';
 if(o.freq!=='w'||o.n!==14)return '<div class="explain">Next-step arrows on the RRG are computed for the weekly chart with the 14-week window.</div>';
 const d=rrgFcLoad();if(!d)return '<div class="explain">Loading the RRG forecasts…</div>';
 const b=d.backtest||{},a=b.analog||{},r=b.rotation||{},pi=b.price_inversion||{},g=b.gravity||{};
 const pc=v=>v==null?'—':fmt(100*v,1)+'%',ci=v=>Array.isArray(v)&&v[0]!=null?`${fmt(v[0],3)} [${fmt(v[1],3)}, ${fmt(v[2],3)}]`:'—';
 return `<details class="fc-score"><summary>How the RRG arrows did out of sample (weekly, ${esc(b.from||'')} – ${esc(b.to||'')})</summary><p class="sub">Arrow points the right way: analogues ${pc(a.direction_hit)}, “keep rotating at the same speed” ${pc(r.direction_hit)}. Step skill vs standing still: analogues ${pc(a.step_skill_vs_persist)}, rotation ${pc(r.step_skill_vs_persist)}. Next week's return read back from the forecast point: IC ${ci(pi.ic_inverted_ci)}, sign right ${pc(pi.sign_hit_inverted)}.${g.weeks?` Lines marked by the gravity + tidal model forecast next week's price first and draw the RRG step that price implies (exact formula): step right ${pc(g.step_direction_hit)}, price IC ${ci(g.ic_ci)} over ${fmt(g.weeks)} weeks.`:''} The rotation is smooth by construction (both coordinates are averages of the past), so where the dot goes next is easy; what the price does next is not.</p></details>`;
}
