/* 4.8 Galaxy — the market as a universe. Data: data/market/history/galaxy.json (app/chaos_forecast.py, rotation-history).
   · Universe: SPY at the centre; every sector a galaxy placed by its weekly RRG point against SPY; its largest liquid
     companies are its stars, placed by their RRG point against the sector; style and asset ETFs (bonds, gold, oil, emerging
     markets, small caps…) are distant bodies. Click a galaxy to fly into it.
   · Galaxy: one sector's stars around its core, each with a comet tail of its last weeks.
   Angle = phase of the rotation (leading → weakening → lagging → improving, clockwise); distance = strength in typical
   spreads, compressed so the far ones fit. Next step: the gravity + tidal model's forecast of next week's price relative to
   the parent, drawn as the exact RRG step that price implies (the same formula as the chart).
   Uses market.js, rotation.js (rotPlayer, rotDraw, table helpers) and chaos.js (FC_MODES, fcOn). */
const GAL={zoom:1,anim:null,hits:[],stars:null};
const GAL_TAILS=[['0','No tails'],['4','4 weeks'],['8','8 weeks'],['13','13 weeks'],['26','26 weeks']];
const GAL_COLOR=[['quad','Rotation phase (quadrant)'],['fc','Next-week forecast (gravity + tidal)']];
const GAL_Q=['Leading','Weakening','Lagging','Improving'];
const GAL_CTR=[['mkt','The market of these companies (sectors equal-weighted)'],['spy','SPY (cap-weighted, led by the largest companies)']];
const galV=v=>v==null?null:100+v/100;                     // stored as round(100 × (value − 100))
const galQuad=(x,y)=>x>=100?(y>=100?0:1):(y<100?2:3);

function galPrep(d,ctr){
 d._preps=d._preps||{};if(d._preps[ctr])return d._preps[ctr];
 const W=d.weeks.length,arr=a=>(a||[]).map(galV),m=ctr==='mkt';
 const gal=Object.entries(d.galaxies||{}).map(([k,g])=>({id:k,name:g.name,members:g.members||0,x:arr(m&&g.xm?g.xm:g.x),y:arr(m&&g.ym?g.ym:g.y),fx:arr(m&&g.fxm?g.fxm:g.fx),fy:arr(m&&g.fym?g.fym:g.fy),stars:[]}));
 const gi=Object.fromEntries(gal.map(g=>[g.id,g]));
 const stars=(d.stars||[]).map(r=>({t:r[0],n:r[1],s:r[2],rev:r[3]||0,x:arr(r[4]),y:arr(r[5]),fx:arr(r[6]),fy:arr(r[7]),fr:r[8]||[],close:r[9]}));
 for(const s of stars)if(gi[s.s])gi[s.s].stars.push(s);
 const bodies=(d.bodies||[]).map(b=>({id:b[0],name:b[1],x:arr(m&&b[4]?b[4]:b[2]),y:arr(m&&b[5]?b[5]:b[3])}));
 const spread=list=>{const a=[];for(const e of list)for(let k=0;k<W;k++){const x=e.x[k],y=e.y[k];if(x!=null&&y!=null)a.push(Math.hypot(x-100,y-100))}a.sort((p,q)=>p-q);return Math.max(.5,quantile(a,.95)||1)};
 const maxRev=Math.max(1,...stars.map(s=>s.rev));
 // forecast brightness by rank within each week (weekly forecasts are a few basis points; their order is what carries)
 // ranked across every star (the universe) and within each galaxy (a sector's model terms are shared, so a whole galaxy can lean one way)
 const nfc=W-(d.fc_from||W),rankOf=list=>Array.from({length:nfc},(_,j)=>list.map(s=>s.fr[j]).filter(x=>x!=null).sort((a,b)=>a-b));
 const fcRank=rankOf(stars);for(const g of gal)g.fcRank=rankOf(g.stars);
 return d._preps[ctr]={W,gal,gi,stars,bodies,Du:spread([...gal,...bodies])*1.05,Ds:spread(stars),maxRev,fc0:d.fc_from||W,fcRank,ctr};
}
// polar compression: direction kept, distance in typical spreads mapped with a power so the far ones fit
function galComp(x,y,D){const dx=x-100,dy=y-100,d=Math.hypot(dx,dy);if(!d)return [0,0];const r=Math.pow(Math.min(1,d/D),.6);return [dx/d*r,dy/d*r]}

function galaxyView(){
 const g=marketGate('history/galaxy','The galaxy');
 if(!g.data)return `<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}</div><div class="explain">The galaxy is built with the long weekly history by the “Rotation history” workflow.</div>`+g.html;
 state.gctr=GAL_CTR.some(c=>c[0]===state.gctr)?state.gctr:'mkt';
 const G=galPrep(g.data,state.gctr),Q=g.data.weeks,ctrName=state.gctr==='spy'?'SPY':'the market of these companies';
 state.gsec=G.gi[state.gsec]?state.gsec:'';
 state.gcol=GAL_COLOR.some(c=>c[0]===state.gcol)?state.gcol:'quad';
 state.gtail=GAL_TAILS.some(c=>c[0]===state.gtail)?state.gtail:(state.gsec?'8':'4');
 state.gbody=state.gbody==='0'?'0':'1';
 state.rfc=FC_MODES.some(m=>m[0]===state.rfc)?state.rfc:'';
 const key='gal|'+Q.length;
 if(state.rfk!==key||!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length)){state.rf=Q.length-1;state.rfk=key}
 state.rfn=null;
 const secs=G.gal.slice().sort((a,b)=>a.name.localeCompare(b.name));
 let out=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${field('gsec','Zoom',[['','The universe — every sector'],...secs.map(s=>[s.id,s.name+' galaxy'])],state.gsec)}${field('gcol','Star colour',GAL_COLOR,state.gcol)}${field('gtail','Tails',GAL_TAILS,state.gtail)}${state.gsec?'':field('gctr','Centre of the universe',GAL_CTR,state.gctr)}${state.gsec?'':field('gbody','Distant bodies',[['1','Show bonds, gold, oil, world, styles'],['0','Hide']],state.gbody)}${field('rfc','Next step',FC_MODES,state.rfc)}</div>`;
 out+=`<div class="toolbar rot-display"><div class="field wide"><label for="rtk">Stars to point out (tickers)</label><input id="rtk" value="${esc(state.rtk||'')}" placeholder="e.g. NVDA, AAPL · Enter"></div></div>`;
 const o={G,Q,sec:state.gsec,tail:+state.gtail,picks:String(state.rtk||'').toUpperCase().split(/[\s,]+/).filter(Boolean).slice(0,6),
  P:{partial:new Set(),span:Q.length,unit:'weeks',ms:140,label:rrgDay}};
 GAL.o=o;
 const z=state.gsec?G.gi[state.gsec]:null;
 out+=`<div class="panel"><h3>${z?esc(z.name)+' — a galaxy of '+fmt(z.stars.length)+' stars':'The universe — sectors as galaxies, companies as stars'}</h3>`;
 out+=`<p class="sub">${z?`Its largest liquid companies placed by their weekly rotation against the ${esc(z.name)} index: direction = the phase (→ leading its sector, ↓ weakening, ← lagging, ↑ improving — clockwise), distance = how strong.`
  :`The centre is ${esc(ctrName)}. Each sector is a galaxy placed by its weekly rotation against it — direction = the phase (→ leading, ↓ weakening, ← lagging, ↑ improving; leadership turns clockwise), distance = how strong; its stars are its companies against the sector. Blue-white points are other bodies: bonds, gold, oil, the rest of the world and investment styles. Click a galaxy to fly in.`} Press play to watch ${fmt(Q.length)} weeks.</p>`;
 out+=rotPlayer(Q,o.P)+`<div class="gal-wrap"><canvas id="gal-canvas" class="gal-canvas" role="img" aria-label="Galaxy chart; the table below lists every value"></canvas>${z?'<button class="action gal-back" id="gback" type="button">← Back to the universe</button>':''}</div>`;
 out+=`<div class="mk-legend">${state.gcol==='quad'?GAL_Q.map((q,i)=>`<span><i class="mk-key gal-k${i}"></i>${q}${z?' its sector':''}</span>`).join(''):`<span><i class="mk-key gal-kup"></i>Forecast to beat its sector next week</span><span><i class="mk-key gal-kdn"></i>To lag</span><span class="muted">Brightness: rank of the forecast that week${z?' within the galaxy':' among all stars'}</span>`}<span class="muted">Star size: revenue</span>${fcOn()?'<span class="muted">Arrow: next week (gravity + tidal) · dotted: what happened</span>':''}</div></div>`;
 ROT.ctx={Q,P:o.P,paint:f=>galPaint(o,f)};
 out+=galTable(o);
 out+=`<details><summary>How the galaxy is built</summary><p>${esc(g.data.note||'')}</p><p class="sub">Positions are weekly RRG points (RS-Ratio and RS-Momentum, ${esc(g.data.n)}-week window, the same formula as the RRG chart) shown in polar form: the angle is the phase of the rotation, the distance from the centre is the strength in typical spreads, compressed (a power of 0.6) so the far ones still fit. Galaxies are placed against SPY, stars against their own sector, so a star far from its galaxy's core is moving differently from its sector. The galaxy's glow grows with the number of liquid companies in the sector.</p></details>`;
 return out;
}

function galColors(){
 const css=getComputedStyle(document.documentElement),g=n=>(css.getPropertyValue(n)||'').trim();
 return {q:[g('--flow-buy')||'#17734a',g('--rot-sun')||'#eda100',g('--flow-sell')||'#ea6a52',g('--rot-1')||'#2a78d6'],
  up:'#4fd18b',dn:'#ff7a66',body:'#cfe3ff',text:'#e9edf6',muted:'#9aa4b8',line:'rgba(160,175,205,.18)',core:'#ffd27a'};
}
function galHex(c,a){                                  // css colour → rgba with alpha (hex or rgb())
 if(c.startsWith('#')){const h=c.length===4?c.slice(1).split('').map(x=>x+x).join(''):c.slice(1,7);return `rgba(${parseInt(h.slice(0,2),16)},${parseInt(h.slice(2,4),16)},${parseInt(h.slice(4,6),16)},${a})`}
 const m=/rgba?\(([^)]+)\)/.exec(c);if(m){const p=m[1].split(',').map(s=>s.trim());return `rgba(${p[0]},${p[1]},${p[2]},${a})`}return c;
}
function galPaint(o,f){
 const cv=document.getElementById('gal-canvas');if(!cv||!cv.getContext)return;
 const ctx=cv.getContext('2d');if(!ctx)return;
 const cw=cv.clientWidth||900,ch=Math.round(Math.max(460,Math.min(820,cw*.7))),dpr=window.devicePixelRatio||1;
 if(cv.width!==Math.round(cw*dpr)||cv.height!==Math.round(ch*dpr)){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.height=ch+'px'}
 ctx.setTransform(dpr,0,0,dpr,0,0);
 const C=galColors(),{G,sec,tail}=o,font=getComputedStyle(document.body).fontFamily||'sans-serif';
 const c0x=cw/2,c0y=ch/2,R=Math.min(cw,ch)/2-30;
 // space
 const bg=ctx.createRadialGradient(c0x,c0y,0,c0x,c0y,Math.hypot(cw,ch)/1.6);bg.addColorStop(0,'#111a33');bg.addColorStop(.55,'#080d1d');bg.addColorStop(1,'#03050b');
 ctx.fillStyle=bg;ctx.fillRect(0,0,cw,ch);
 if(!GAL.stars||GAL.stars.w!==cw||GAL.stars.h!==ch){let s=1234567;const rnd=()=>(s=(s*16807)%2147483647)/2147483647;GAL.stars={w:cw,h:ch,p:Array.from({length:Math.round(cw*ch/2600)},()=>[rnd()*cw,rnd()*ch,rnd()*.9+.2,rnd()*.5+.15])}}
 for(const [x,y,r,a] of GAL.stars.p){ctx.globalAlpha=a;ctx.fillStyle='#dfe6ff';ctx.beginPath();ctx.arc(x,y,r*.6,0,Math.PI*2);ctx.fill()}
 ctx.globalAlpha=1;
 const z=sec?G.gi[sec]:null,hits=[],labels=[],bodyLabels=[];     // galaxy names win over the bodies' labels
 // the frame: faint rings and the four phase directions
 const D=z?G.Ds:G.Du;
 ctx.strokeStyle=C.line;ctx.lineWidth=1;
 for(const k of [1,2,4].filter(k=>k<D)){const r=Math.pow(k/D,.6)*R;ctx.beginPath();ctx.arc(c0x,c0y,r,0,Math.PI*2);ctx.stroke()}
 ctx.beginPath();ctx.moveTo(c0x-R,c0y);ctx.lineTo(c0x+R,c0y);ctx.moveTo(c0x,c0y-R);ctx.lineTo(c0x,c0y+R);ctx.stroke();
 ctx.font=`11px ${font}`;ctx.fillStyle=C.muted;
 ctx.textAlign='right';ctx.fillText('Leading →',cw-12,c0y-8);ctx.textAlign='left';ctx.fillText('← Lagging',12,c0y-8);
 ctx.textAlign='center';ctx.fillText('↑ Improving',c0x,18);ctx.fillText('↓ Weakening',c0x,ch-10);
 const pos=(x,y,Dd,Rr,cx=c0x,cy=c0y)=>{if(x==null||y==null)return null;const u=galComp(x,y,Dd);return [cx+u[0]*Rr,cy-u[1]*Rr]};
 const starCol=(s,k,alpha)=>{
  if(state.gcol==='fc'){const j=k-G.fc0,v=j>=0&&j<s.fr.length?s.fr[j]:null;if(v==null)return galHex('#8d96aa',alpha*.5);
   const a=(z?z.fcRank[j]:G.fcRank[j])||[];let lo=0,hi=a.length;while(lo<hi){const mid=(lo+hi)>>1;if(a[mid]<v)lo=mid+1;else hi=mid}
   const t=a.length?2*(lo/Math.max(1,a.length-1))-1:0;return galHex(t>=0?C.up:C.dn,alpha*(.25+.75*Math.abs(t)))}
  return galHex(C.q[galQuad(s.x[k],s.y[k])],alpha)};
 const glow=(x,y,r,col,a)=>{const gr=ctx.createRadialGradient(x,y,0,x,y,r);gr.addColorStop(0,galHex(col,a));gr.addColorStop(.35,galHex(col,a*.35));gr.addColorStop(1,galHex(col,0));ctx.fillStyle=gr;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()};
 const sizeOf=(s,lo,hi)=>lo+(hi-lo)*Math.sqrt(Math.max(0,s.rev)/G.maxRev);
 const picks=new Set(o.picks);
 const arrow=(p,q,col,w)=>{if(!p||!q)return;const L=Math.hypot(q[0]-p[0],q[1]-p[1]);ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=w;ctx.globalAlpha=.95;
  if(L<1.5){ctx.beginPath();ctx.arc(p[0],p[1],w*2,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;return}
  const a=Math.atan2(q[1]-p[1],q[0]-p[0]),hs=Math.min(7,2.5+L*.3);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0]-Math.cos(a)*hs*.6,q[1]-Math.sin(a)*hs*.6);ctx.stroke();
  ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(q[0]-hs*Math.cos(a-.45),q[1]-hs*Math.sin(a-.45));ctx.lineTo(q[0]-hs*Math.cos(a+.45),q[1]-hs*Math.sin(a+.45));ctx.closePath();ctx.fill();ctx.globalAlpha=1};
 const check=(p,e,k,P_)=>{if(state.rfc!=='check'||k+1>=G.W)return;const q=P_(e.x[k+1],e.y[k+1]);if(!p||!q)return;ctx.setLineDash([2,3]);ctx.strokeStyle='rgba(233,237,246,.7)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.setLineDash([]);ctx.beginPath();ctx.arc(q[0],q[1],3,0,Math.PI*2);ctx.stroke()};
 const tipStar=(s,k,parent)=>{const x=s.x[k],y=s.y[k],j=k-G.fc0,v=j>=0&&j<s.fr.length?s.fr[j]:null;
  return [[s.t+' · '+rrgDay(o.Q[k]),s.n||''],[GAL_Q[galQuad(x,y)],'against '+parent],[fmt(x,2)+' / '+fmt(y,2),'RS-Ratio / RS-Momentum'],...(v!=null?[[(v>=0?'+':'−')+fmt(Math.abs(v)/100,2)+'%','next week vs its sector (gravity + tidal)']]:[]),...(s.close!=null&&k===G.W-1?[['$'+fmt(s.close,2),'latest close']]:[])]};
 if(!z){
  // ---------------- the universe
  const Rg=g=>Math.min(R*.2,14+2.1*Math.sqrt(g.members||g.stars.length));
  if(state.gbody!=='0')for(const b of G.bodies){const p=pos(b.x[f],b.y[f],G.Du,R*.92);if(!p)continue;
   glow(p[0],p[1],9,C.body,.55);ctx.fillStyle=C.body;ctx.beginPath();ctx.arc(p[0],p[1],1.8,0,Math.PI*2);ctx.fill();
   bodyLabels.push({x:p[0]+6,y:p[1]+12,t:b.id,c:galHex(C.body,.85),f:'10.5px'});hits.push({x:p[0],y:p[1],r:6,rows:[[b.id+' · '+rrgDay(o.Q[f]),b.name],[GAL_Q[galQuad(b.x[f],b.y[f])],'against '+(G.ctr==='spy'?'SPY':'the market of these companies')],[fmt(b.x[f],2)+' / '+fmt(b.y[f],2),'RS-Ratio / RS-Momentum']]})}
  // market core
  const cn=G.ctr==='spy'?'Market (SPY)':'Market (these companies)';
  glow(c0x,c0y,46,C.core,.55);glow(c0x,c0y,16,'#fff4d6',.9);labels.push({x:c0x,y:c0y+30,t:cn,c:C.text,f:'600 12px',a:'center'});
  hits.push({x:c0x,y:c0y,r:14,rows:[[cn+' · '+rrgDay(o.Q[f]),'the centre of the universe']]});
  const order=G.gal.map(g=>({g,p:pos(g.x[f],g.y[f],G.Du,R*.82)})).filter(a=>a.p);
  for(const {g} of order)if(tail){ctx.strokeStyle='rgba(255,210,122,.22)';ctx.lineWidth=1;ctx.beginPath();let st=false;
   for(let k=Math.max(0,f-tail);k<=f;k++){const q=pos(g.x[k],g.y[k],G.Du,R*.82);if(!q)continue;st?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);st=true}ctx.stroke()}
  ctx.globalCompositeOperation='lighter';
  for(const {g,p} of order){const rg=Rg(g),col=C.q[galQuad(g.x[f],g.y[f])];
   glow(p[0],p[1],rg*1.25,col,.22);
   for(const s of g.stars){const sp=pos(s.x[f],s.y[f],G.Ds,rg,p[0],p[1]);if(!sp)continue;const r=sizeOf(s,.6,2.2);ctx.fillStyle=starCol(s,f,.85);ctx.beginPath();ctx.arc(sp[0],sp[1],r,0,Math.PI*2);ctx.fill();
    if(picks.has(s.t))labels.push({x:sp[0]+5,y:sp[1]-4,t:s.t,c:C.text,f:'600 11px'})}
   glow(p[0],p[1],7,'#fff2d0',.95)}
  ctx.globalCompositeOperation='source-over';
  for(const {g,p} of order){const rg=Rg(g);labels.push({x:p[0],y:p[1]-rg-4,t:g.name,c:C.text,f:'600 12px',a:'center'});
   hits.push({x:p[0],y:p[1],r:rg,gal:g.id,rows:[[g.name+' galaxy · '+rrgDay(o.Q[f]),fmt(g.members)+' liquid companies · click to fly in'],[GAL_Q[galQuad(g.x[f],g.y[f])],'against '+(G.ctr==='spy'?'SPY':'the market of these companies')],[fmt(g.x[f],2)+' / '+fmt(g.y[f],2),'RS-Ratio / RS-Momentum']]});
   if(fcOn()){const j=f-G.fc0;if(j>=0&&g.fx[j]!=null)arrow(p,pos(g.fx[j],g.fy[j],G.Du,R*.82),'rgba(255,236,190,.95)',1.8);check(p,g,f,(x,y)=>pos(x,y,G.Du,R*.82))}}
 }else{
  // ---------------- one galaxy
  glow(c0x,c0y,60,C.core,.45);glow(c0x,c0y,14,'#fff4d6',.95);labels.push({x:c0x,y:c0y+28,t:z.name+' index',c:C.text,f:'600 12px',a:'center'});
  const P_=(x,y)=>pos(x,y,G.Ds,R*.95);
  const live=z.stars.map(s=>({s,p:P_(s.x[f],s.y[f])})).filter(a=>a.p).sort((a,b)=>a.s.rev-b.s.rev);
  if(tail)for(const {s} of live){ctx.lineWidth=picks.has(s.t)?2:1;let prev=null;
   for(let k=Math.max(0,f-tail);k<=f;k++){const q=P_(s.x[k],s.y[k]);if(!q){prev=null;continue}if(prev){ctx.strokeStyle=starCol(s,k,picks.has(s.t)?.9:.08+.3*(k-f+tail)/tail);ctx.beginPath();ctx.moveTo(prev[0],prev[1]);ctx.lineTo(q[0],q[1]);ctx.stroke()}prev=q}}
  ctx.globalCompositeOperation='lighter';
  for(const {s,p} of live){const r=sizeOf(s,1.4,6.5),col=starCol(s,f,1);glow(p[0],p[1],r*3.2,col.replace(/[\d.]+\)$/,'1)'),.35);ctx.fillStyle=col;ctx.beginPath();ctx.arc(p[0],p[1],r,0,Math.PI*2);ctx.fill()}
  ctx.globalCompositeOperation='source-over';
  const top=new Set(live.slice().sort((a,b)=>b.s.rev-a.s.rev).slice(0,14).map(a=>a.s.t));
  for(const {s,p} of live){const r=sizeOf(s,1.4,6.5);hits.push({x:p[0],y:p[1],r:Math.max(5,r+2),rows:tipStar(s,f,z.name),t:s.t});
   if(top.has(s.t)||picks.has(s.t))labels.push({x:p[0]+r+3,y:p[1]-3,t:s.t,c:picks.has(s.t)?'#ffffff':C.text,f:picks.has(s.t)?'700 12px':'500 11px'});
   if(fcOn()){const j=f-G.fc0;if(j>=0&&s.fx[j]!=null)arrow(p,P_(s.fx[j],s.fy[j]),picks.has(s.t)?'#ffffff':'rgba(233,237,246,.75)',picks.has(s.t)?2:1);check(p,s,f,P_)}}
  if(fcOn()&&f<G.fc0)labels.push({x:12,y:ch-12,t:'Next-step arrows cover the last '+fmt(G.W-G.fc0)+' weeks; move the slider there.',c:C.muted,f:'11px',a:'left'});
 }
 // labels last, skipping overlaps
 const boxes=[];
 for(const l of [...labels,...bodyLabels]){ctx.font=`${l.f} ${font}`;const w=ctx.measureText(l.t).width,a=l.a||'left',x0=a==='center'?l.x-w/2:l.x,b=[x0,l.y-11,x0+w,l.y+2];
  if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))continue;boxes.push(b);
  ctx.textAlign=a;ctx.lineWidth=3;ctx.strokeStyle='rgba(3,5,11,.85)';ctx.strokeText(l.t,l.x,l.y);ctx.fillStyle=l.c;ctx.fillText(l.t,l.x,l.y)}
 ctx.font=`700 34px ${font}`;ctx.textAlign='right';ctx.fillStyle='rgba(233,237,246,.12)';ctx.fillText(rrgDay(o.Q[f]),cw-16,ch-20);
 GAL.hits=hits;
}
function galTable(o){
 const {G,Q}=o,f=state.rf,z=o.sec?G.gi[o.sec]:null;
 const dir=(x0,y0,x1,y1)=>x0==null||x1==null?'':['→','↗','↑','↖','←','↙','↓','↘'][((Math.round(Math.atan2(y1-y0,x1-x0)/(Math.PI/4))%8)+8)%8];
 if(!z){
  const rows=G.gal.filter(g=>g.x[f]!=null).sort((a,b)=>b.x[f]-a.x[f]);
  exported=rows.map(g=>({week:Q[f],sector:g.name,phase:GAL_Q[galQuad(g.x[f],g.y[f])],rs_ratio:+g.x[f].toFixed(2),rs_momentum:+g.y[f].toFixed(2),liquid_companies:g.members}));
  let out=`<div class="section-head"><h3>Galaxies · ${esc(rrgDay(Q[f]))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Sector galaxy','Phase vs '+(G.ctr==='spy'?'SPY':'the market'),'RS-Ratio','RS-Momentum','Heading','Liquid companies','Stars shown'],rows.map(g=>[`<button class="text-button" data-gsec="${esc(g.id)}"><b>${esc(g.name)}</b></button>`,esc(GAL_Q[galQuad(g.x[f],g.y[f])]),fmt(g.x[f],2),fmt(g.y[f],2),dir(g.x[f-1],g.y[f-1],g.x[f],g.y[f]),fmt(g.members),fmt(g.stars.length)]));
  return out;
 }
 const j=f-G.fc0,rows=z.stars.filter(s=>s.x[f]!=null).sort((a,b)=>b.rev-a.rev);
 exported=rows.map(s=>({week:Q[f],ticker:s.t,name:s.n,phase_vs_sector:GAL_Q[galQuad(s.x[f],s.y[f])],rs_ratio:+s.x[f].toFixed(2),rs_momentum:+s.y[f].toFixed(2),next_week_vs_sector_pct:j>=0&&s.fr[j]!=null?s.fr[j]/100:null}));
 let out=`<div class="section-head"><h3>${esc(z.name)} stars · ${esc(rrgDay(Q[f]))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Company','Phase vs its sector','RS-Ratio','RS-Momentum','Heading','Next week vs sector (forecast)'],rows.map(s=>{const v=j>=0?s.fr[j]:null;
  return [tkLink(s.t)+` <span class="muted">${esc(s.n||'')}</span>`,esc(GAL_Q[galQuad(s.x[f],s.y[f])]),fmt(s.x[f],2),fmt(s.y[f],2),dir(s.x[f-1],s.y[f-1],s.x[f],s.y[f]),
   v==null?'—':`<span class="${v>=0?'positive':'negative'}">${(v>=0?'+':'−')+fmt(Math.abs(v)/100,2)}%</span>`]}));
}
function bindGalaxy(){
 const cv=document.getElementById('gal-canvas');
 document.querySelectorAll('#workspace [data-gsec]').forEach(b=>b.onclick=()=>galFly(b.dataset.gsec));
 if($('gback'))$('gback').onclick=()=>galFly('');
 if(!cv||!cv.addEventListener)return;
 const find=e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=1e9;
  for(const h of GAL.hits){const d=Math.hypot(h.x-mx,h.y-my);if(d<=Math.max(h.r,6)&&d<bd){bd=d;best=h}}return best};
 cv.onpointermove=e=>{const h=find(e);rotTip(h?h.rows:null,e.clientX,e.clientY);cv.style.cursor=h&&h.gal?'pointer':'default'};
 cv.onpointerleave=()=>rotTip(null);
 cv.onclick=e=>{const h=find(e);if(h&&h.gal)galFly(h.gal);else if(h&&h.t&&!String(state.rtk||'').toUpperCase().split(/[\s,]+/).includes(h.t)){state.rtk=[...String(state.rtk||'').split(/[\s,]+/).filter(Boolean),h.t].slice(-6).join(', ');render()}};
 if(ROT.ctx&&ROT.ctx.paint)ROT.ctx.paint(state.rf);
}
function galFly(sec){                                   // a short zoom toward the galaxy, then the galaxy view
 rotStop();rotTip(null);
 const cv=document.getElementById('gal-canvas');
 if(!cv||rotReduced()||typeof requestAnimationFrame!=='function'){state.gsec=sec;state.gtail=sec?'8':'4';render();return}
 const h=GAL.hits.find(x=>x.gal===sec),t0=performance.now(),dur=420,cx=h?h.x:cv.clientWidth/2,cy=h?h.y:cv.clientHeight/2;
 const snap=document.createElement('canvas');snap.width=cv.width;snap.height=cv.height;snap.getContext('2d').drawImage(cv,0,0);
 const ctx=cv.getContext('2d'),dpr=window.devicePixelRatio||1;
 const step=now=>{const k=Math.min(1,(now-t0)/dur),s=sec?1+3*k*k:1/(1+3*k*k);ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#03050b';ctx.fillRect(0,0,cv.width,cv.height);
  ctx.globalAlpha=1-k*.85;ctx.setTransform(s,0,0,s,(1-s)*cx*dpr,(1-s)*cy*dpr);ctx.drawImage(snap,0,0);ctx.globalAlpha=1;
  if(k<1)requestAnimationFrame(step);else{state.gsec=sec;state.gtail=sec?'8':'4';render()}};
 requestAnimationFrame(step);
}
