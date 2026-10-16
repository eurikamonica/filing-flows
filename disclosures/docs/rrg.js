/* 4.6 Relative Rotation Graph (RRG) on the long weekly history (branch rotation-history → data/market/history/).
   RS = 100 × close ÷ SPY, smoothed with a short EMA (4 weeks / 2 months). RS-Ratio: how far smoothed RS stands above or
   below its own n-period EMA trend (above 100: outperforming its trend). RS-Momentum: the change of that gap from one
   period to the next, smoothed the same way (above 100: the relative trend is gaining). Both are divided by their own
   typical size over the last year or more (in standard deviations around 100), so every line reads on one scale. An
   open approximation of the JdK RS-Ratio and RS-Momentum (the original formula is not published), computed here in the
   browser from weekly closes, so the window can change. Quadrants at 100 / 100 — Leading, Weakening, Lagging, Improving — and leadership
   rotates clockwise.
   Modes: 2-D (the standard chart); 3-D (time as depth: a rotation becomes a spiral, the slice at the front is the
   standard RRG of the date shown); 4-D (a third measure as depth and time played as the fourth dimension).
   Uses the helpers of market.js and rotation.js. */
const RRG={cache:new Map(),grid:null};
const RRG_COL=['#2a78d6','#eb6834','#1baf7a','#a24fd0','#c98a00','#d1397d','#3aa6b9','#7d8a1f','#b8522b','#5a6ad0','#8a8a84','#2f9e44'];
const RRG_MODES=[['2d','2-D — the standard RRG'],['3d','3-D — time as depth (spirals)'],['4d','4-D — a third measure as depth, time played']];
const RRG_Z=[['r52','12-month return vs SPY'],['hi52','Distance below the 52-week high'],['vrel','Volatility vs SPY (13 weeks)'],['volz','Volume vs its own year (13 weeks)']];
const RRG_ZINFO={r52:{label:'12-month return vs SPY',unit:'%'},hi52:{label:'Below the 52-week high',unit:'%'},vrel:{label:'Volatility vs SPY, 13 weeks',unit:'%'},volz:{label:'Volume, 13 weeks vs 52',unit:'%'},
 time:{label:'Time',unit:''}};
const RRG_Q=[['lead','Leading','RS-Ratio and RS-Momentum above 100: outperforming, and gaining'],['weak','Weakening','still above its trend, but losing speed'],
 ['lag','Lagging','under its trend and losing'],['imp','Improving','under its trend, but gaining speed']];
const rrgQuad=(x,y)=>x>=100?(y>=100?0:1):(y<100?2:3);
const rrgDay=s=>{const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s||''));return m?`${MONTH_NAMES[+m[2]-1]} ${+m[3]}, ${m[1]}`:qlabel(s)};

function rrgGrid(D){                                   // every Friday of the file, and the last Friday of each month
 if(RRG.grid&&RRG.grid.src===D)return RRG.grid;
 const t0=Date.parse(D.start+'T00:00:00Z'),n=Math.round((Date.parse(D.weeks+'T00:00:00Z')-t0)/6048e5)+1;
 const days=Array.from({length:n},(_,i)=>new Date(t0+i*6048e5).toISOString().slice(0,10));
 const mi=[];days.forEach((d,i)=>{if(i===n-1||days[i+1].slice(0,7)!==d.slice(0,7))mi.push(i)});
 return RRG.grid={src:D,t0,n,days,w:{idx:days.map((_,i)=>i),labels:days},m:{idx:mi,labels:mi.map(i=>days[i].slice(0,7))}};
}
function rrgFull(G,ent,key){                            // one series on the whole weekly grid
 const a=new Array(G.n).fill(null),src=ent[key]||[],o=Math.round((Date.parse(ent.start+'T00:00:00Z')-G.t0)/6048e5);
 for(let i=0;i<src.length;i++)if(o+i>=0&&o+i<G.n)a[o+i]=src[i];
 return a;
}
function rrgCalc(D,ent,freq,n){
 const key=`${ent.id}|${freq}|${n}`;if(RRG.cache.has(key))return RRG.cache.get(key);
 const G=rrgGrid(D),S=G[freq],C=rrgFull(G,ent,'c'),B=rrgFull(G,D.bench,'c'),V=ent.v?rrgFull(G,ent,'v'):null;
 const rs=S.idx.map(i=>C[i]!=null&&B[i]!=null&&B[i]>0?100*C[i]/B[i]:null);
 // RS smoothed (a short EMA), against its own n-period EMA trend → the relative trend; its one-period change, smoothed
 // the same way → the momentum; both in standard deviations of their own last year or so, so lines are comparable
 const L=rs.length,sh=freq==='w'?4:2,long=freq==='w'?Math.max(52,3*n):Math.max(24,3*n);
 const ema=(a,span)=>{const al=2/(span+1),o=new Array(a.length).fill(null);let m=null,c=0;for(let k=0;k<a.length;k++){if(a[k]==null){m=null;c=0;continue}m=m==null?a[k]:m+al*(a[k]-m);c++;o[k]=c>=Math.min(span,6)?m:null}return o};
 const s_=ema(rs,sh),t_=ema(s_,n),dev=s_.map((v,k)=>v!=null&&t_[k]?100*(v/t_[k]-1):null);
 const roc=ema(dev.map((v,k)=>k&&v!=null&&dev[k-1]!=null?v-dev[k-1]:null),sh);
 const norm=a=>a.map((v,k)=>{if(v==null)return null;let s2=0,m=0;for(let i=Math.max(0,k-long+1);i<=k;i++)if(a[i]!=null){s2+=a[i]*a[i];m++}
  return m>=Math.min(long,26)&&s2>0?100+v/Math.sqrt(s2/m):null});
 const x=norm(dev),y0=norm(roc),y=y0.map((v,k)=>x[k]==null?null:v);
 const lag=freq==='w'?52:12,wk=i=>i,lr=(A,i)=>A[i]!=null&&A[i-1]!=null&&A[i]>0&&A[i-1]>0?Math.log(A[i]/A[i-1]):null;
 const sd13=(A,i)=>{const r=[];for(let j=i-12;j<=i;j++){if(j<1)continue;const v=lr(A,j);if(v!=null)r.push(v)}if(r.length<10)return null;const mu=r.reduce((a,b)=>a+b,0)/r.length;return Math.sqrt(r.reduce((a,b)=>a+(b-mu)**2,0)/(r.length-1))};
 const z={r52:[],hi52:[],vrel:[],volz:[]};
 S.idx.forEach((gi,k)=>{
  z.r52.push(k>=lag&&rs[k]!=null&&rs[k-lag]!=null?100*(rs[k]/rs[k-lag]-1):null);
  let hi=null,cnt=0;for(let j=Math.max(0,gi-51);j<=gi;j++)if(C[j]!=null){cnt++;hi=hi==null?C[j]:Math.max(hi,C[j])}
  z.hi52.push(cnt>=45&&C[gi]!=null?100*(C[gi]/hi-1):null);
  const a=sd13(C,wk(gi)),b=sd13(B,wk(gi));z.vrel.push(a!=null&&b?100*(a/b-1):null);
  if(V){let s13=0,n13=0,s52=0,n52=0;for(let j=Math.max(0,gi-51);j<=gi;j++){if(V[j]==null)continue;s52+=V[j];n52++;if(j>gi-13){s13+=V[j];n13++}}
   z.volz.push(n13>=10&&n52>=40&&s52>0?100*((s13/n13)/(s52/n52)-1):null)}else z.volz.push(null);
 });
 const out={x,y,z,labels:S.labels};RRG.cache.set(key,out);return out;
}

/* ---------- which lines: the universe ---------- */
function rrgUniverses(D){
 const secs={},tk=D.tickers||{};for(const [t,m] of Object.entries(tk))if(m&&m.s)(secs[m.s]=secs[m.s]||[]).push(t);
 const names=Object.fromEntries((D.series||[]).filter(s=>s.group==='site-sector').map(s=>[s.sector,s.name.replace(/ · site companies$/,'')]));
 const nice=s=>names[s]||String(s).replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
 return [['sectors','Sector ETFs (SPDR)'],['styles','Style, size and asset ETFs'],['site','Site sectors (Sankey companies)'],
  ...Object.keys(secs).sort((a,b)=>nice(a).localeCompare(nice(b))).map(s=>['top:'+s,'Largest companies · '+nice(s)]),['tickers','Tickers you type']];
}
function rrgTicker(t){                                 // one company's weekly file, loaded when asked for
 const m=marketData('history/t/'+t);
 return m.data?{id:t,name:t,full:m.data.n||'',start:m.data.start,c:m.data.c,v:m.data.v}:m.err?{id:t,missing:true}:{id:t,loading:true};
}
function rrgEntities(D,uni,typed){
 const S=D.series||[],grp=g=>S.filter(s=>s.group===g).map(s=>({...s,full:s.name,name:s.id.startsWith('s:')?s.name.replace(/ · site companies$/,''):s.id}));
 if(uni==='sectors')return grp('sector-etf');
 if(uni==='styles')return grp('style-etf');
 if(uni==='site')return grp('site-sector');
 const ids=uni.startsWith('top:')?Object.entries(D.tickers||{}).filter(([,m])=>m&&m.s===uni.slice(4)).sort((a,b)=>(b[1].rev||0)-(a[1].rev||0)).slice(0,10).map(([t])=>t)
  :String(typed||'').toUpperCase().split(/[\s,;]+/).filter(Boolean).map(t=>t.replace('.','-')).slice(0,12);
 return ids.map(t=>{const s=S.find(x=>x.id===t);return s?{...s,name:s.id,full:s.name}:rrgTicker(t)});
}

/* ---------- the view ---------- */
function rrgView(){
 const g=marketGate('history/rrg','The long price history');
 if(!g.data)return `<div class="explain">The RRG uses the long weekly history (branch <span class="mono">rotation-history</span>, filled by the “Rotation history” workflow in batches). Until its first build is published there is nothing to draw.</div>`+g.html;
 const D=g.data;if(!D.bench)return empty('The benchmark (SPY) is not in the history yet; the next collection run fetches it first.');
 const unis=rrgUniverses(D);
 state.rrgu=unis.some(u=>u[0]===state.rrgu)?state.rrgu:'sectors';
 state.rrgf=state.rrgf==='m'?'m':'w';
 const W=state.rrgf==='w',wins=W?[['10','10 weeks (fast)'],['14','14 weeks'],['26','26 weeks'],['52','52 weeks (slow)']]:[['6','6 months'],['10','10 months'],['12','12 months'],['24','24 months']];
 state.rrgn=wins.some(x=>x[0]===state.rrgn)?state.rrgn:W?'14':'10';
 const tails=W?[['4','4 weeks'],['8','8 weeks'],['13','13 weeks'],['26','26 weeks'],['52','52 weeks']]:[['3','3 months'],['6','6 months'],['12','12 months'],['24','24 months']];
 state.rrgt=tails.some(x=>x[0]===state.rrgt)?state.rrgt:W?'8':'6';
 state.rrgm=RRG_MODES.some(m=>m[0]===state.rrgm)?state.rrgm:'2d';
 state.rrgz=RRG_Z.some(z=>z[0]===state.rrgz)?state.rrgz:'r52';
 let out=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${field('rrgu','Lines',unis,state.rrgu)}${field('rrgf','Frequency',[['w','Weekly (the standard)'],['m','Monthly (long cycles)']],state.rrgf)}${field('rrgm','Chart type',RRG_MODES,state.rrgm)}${state.rrgm==='4d'?field('rrgz','↗ Depth (third measure)',RRG_Z,state.rrgz):''}</div>`;
 out+=`<div class="toolbar rot-display">${field('rrgn','RS window',wins,state.rrgn)}${field('rrgt','Tail',tails,state.rrgt)}${state.rrgu==='tickers'?`<div class="field wide"><label for="rrgtk">Tickers (up to 12, any company or ETF on file)</label><input id="rrgtk" value="${esc(state.rrgtk||'')}" placeholder="e.g. NVDA, AMD, SMH · Enter"></div>`:''}</div>`;
 const ents=rrgEntities(D,state.rrgu,state.rrgtk),ok=ents.filter(e=>e.c),waiting=ents.filter(e=>e.loading),missing=ents.filter(e=>e.missing);
 if(state.rrgu==='tickers'&&!ents.length)return out+empty('Type tickers to compare, e.g. NVDA, AMD, SMH.');
 if(!ok.length)return out+(waiting.length?empty('Loading the weekly history…'):empty('Nothing on file for these yet. The collector takes the site’s companies largest first, a batch every few hours.'));
 const freq=state.rrgf,n=+state.rrgn,G=rrgGrid(D),S=G[freq],Q=S.labels;
 const lines=ok.map((e,i)=>({e,col:RRG_COL[i%RRG_COL.length],calc:rrgCalc(D,e,freq,n)}));
 const firstK=Math.min(...lines.map(l=>l.calc.y.findIndex(v=>v!=null)).filter(k=>k>=0));
 const key='rrg|'+freq+'|'+Q.length;
 if(state.rfk!==key||!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length)){state.rf=Q.length-1;state.rfk=key}
 if(state.rf<firstK)state.rf=firstK;
 state.rfn=null;                                       // the other charts reset their frame when they come back
 const o={D,lines,Q,freq,n,tail:+state.rrgt,mode:state.rrgm,zk:state.rrgm==='3d'?'time':state.rrgm==='4d'?state.rrgz:null,firstK,
  P:{partial:new Set(),span:Math.min(Q.length-firstK,W?260:120),unit:W?'weeks':'months',ms:W?110:300,label:rrgDay}};
 o.dom=rrgDomain(o);
 const head=state.rrgm==='2d'?'Relative Rotation Graph':state.rrgm==='3d'?'RRG in 3-D — time as depth':'RRG in 4-D — depth: '+RRG_ZINFO[o.zk].label+'; time played';
 out+=`<div class="panel"><h3>${esc(head)}</h3><p class="sub">→ JdK RS-Ratio (relative trend) · ↑ JdK RS-Momentum (its speed)${o.zk?' · ↗ '+esc(RRG_ZINFO[o.zk].label):''} · against ${esc(D.benchmark||'SPY')} · ${W?'weekly':'monthly'}, ${esc(n)}-${W?'week':'month'} window · tails ${esc(state.rrgt)} ${W?'weeks':'months'}. History since ${esc(rrgDay(D.start))}; drag the slider anywhere and press play.</p>`;
 out+=rotPlayer(Q,o.P);
 if(state.rrgm==='2d'){ROT.ctx={Q,P:o.P,draw:f=>rrgFrame(o,f)};out+=`<div id="rot-plot">${rrgFrame(o,state.rf)}</div>`}
 else{ROT.ctx={Q,P:o.P,paint:f=>rrgPaint3d(o,f)};
  out+=`<div class="rot-3d-wrap"><canvas id="rot-3d" class="rot-3d" role="img" aria-label="${esc(head)}; the table below lists every value"></canvas><div class="rot-3d-tools"><button class="action" id="rspin" type="button">${ROT.spin?'Stop turning':'Turn slowly'}</button><button class="action" id="rreset" type="button">Front view</button></div></div>`}
 out+=`<div class="mk-legend rrg-legend">${lines.map(l=>`<span><i class="mk-key" style="background:${l.col}"></i>${esc(l.e.name)} <span class="muted">${esc(rrgFull_(l.e))}</span></span>`).join('')}${RRG_Q.map(([k,name])=>`<span><i class="mk-key rrg-k-${k}"></i>${name}</span>`).join('')}</div>`;
 if(waiting.length||missing.length)out+=`<p class="sub">${waiting.length?'Loading '+esc(waiting.map(e=>e.id).join(', '))+'… ':''}${missing.length?'Not on file yet: '+esc(missing.map(e=>e.id).join(', '))+' (the collector fetches the site’s companies largest first; the workflow’s “tickers” input fetches any ticker now).':''}</p>`;
 out+='</div>'+rrgTable(o);
 out+=`<details><summary>How the RRG is computed</summary><p>RS = 100 × weekly close ÷ ${esc(D.benchmark||'SPY')} (both adjusted for splits and dividends), smoothed over ${W?'4 weeks':'2 months'}. RS-Ratio: how far RS stands above or below its own ${esc(n)}-${W?'week':'month'} trend (an exponential average); above 100 the line is outperforming its trend. RS-Momentum: how much that gap changed since the ${W?'week':'month'} before, smoothed the same way; above 100 the relative trend is gaining speed. Both are expressed in standard deviations of their own last ${W?'year or more':'two years or more'} around 100, so a quiet ETF and a volatile stock read on the same scale. This is an open approximation of the JdK RS-Ratio and RS-Momentum used by StockCharts (their formula is not published), so levels differ from theirs while the quadrants and the clockwise rotation read the same. Monthly lines sample the last weekly close of each month. 3-D puts time in depth, so each line becomes a spiral and the front slice is the standard chart for the date shown; 4-D puts a third measure in depth and plays time.</p><p class="sub">${esc(D.note||'')}</p></details>`;
 return out;
}
function rrgDomain(o){                                 // symmetric around 100, fixed for the whole history so play does not rescale
 const xs=[],ys=[],zs=[];
 for(const l of o.lines)for(let k=o.firstK;k<o.Q.length;k++){const x=l.calc.x[k],y=l.calc.y[k];if(x==null||y==null)continue;xs.push(Math.abs(x-100));ys.push(Math.abs(y-100));
  if(o.zk&&o.zk!=='time'){const z=l.calc.z[o.zk][k];if(z!=null)zs.push(z)}}
 const q=(a,p)=>{if(!a.length)return 1;const s=a.slice().sort((u,v)=>u-v);return s[Math.min(s.length-1,Math.floor(p*(s.length-1)))]};
 const mx=Math.max(1.2,q(xs,.985)*1.08),my=Math.max(1.2,q(ys,.985)*1.08);
 const zd=zs.length?[q(zs,.03),q(zs,.97)]:[0,1];if(zd[1]-zd[0]<1e-9)zd[1]=zd[0]+1;
 return {x:[100-mx,100+mx],y:[100-my,100+my],z:zd};
}
const rrgF=(v,d=2)=>v==null?'—':fmt(v,d);
const rrgFull_=e=>{const f=String(e.full||'').replace(/\s*\([A-Z.\-]+\)$/,'');return f===e.name?'':f};
function rrgTipRows(o,l,k){
 const c=l.calc,x=c.x[k],y=c.y[k],qd=RRG_Q[rrgQuad(x,y)];
 return [[l.e.name+' · '+rrgDay(o.Q[k]),rrgFull_(l.e)],[qd[1],qd[2]],[rrgF(x),'RS-Ratio'],[rrgF(y),'RS-Momentum'],
  ...Object.keys(RRG_ZINFO).filter(z=>z!=='time'&&c.z[z][k]!=null).map(z=>[vfmt({unit:'%',centred:true},c.z[z][k]),RRG_ZINFO[z].label])];
}
function rrgFrame(o,f){
 const [W,H]=rotSize(.62,420,700),Lm=58,R=18,T=16,B=44,{x:xd,y:yd}=o.dom;
 const cx=v=>Math.max(xd[0],Math.min(xd[1],v)),cy=v=>Math.max(yd[0],Math.min(yd[1],v));
 const sx=v=>Lm+(cx(v)-xd[0])/(xd[1]-xd[0])*(W-Lm-R),sy=v=>T+(yd[1]-cy(v))/(yd[1]-yd[0])*(H-T-B);
 const X0=sx(100),Y0=sy(100);
 let s=`<svg class="plot mk-plot rrg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Relative Rotation Graph for ${esc(rrgDay(o.Q[f]))}; the table below lists every value">`;
 s+=`<rect class="rrg-lead" x="${X0}" y="${T}" width="${W-R-X0}" height="${Y0-T}"/><rect class="rrg-weak" x="${X0}" y="${Y0}" width="${W-R-X0}" height="${H-B-Y0}"/>`;
 s+=`<rect class="rrg-lag" x="${Lm}" y="${Y0}" width="${X0-Lm}" height="${H-B-Y0}"/><rect class="rrg-imp" x="${Lm}" y="${T}" width="${X0-Lm}" height="${Y0-T}"/>`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-14}" text-anchor="end">${esc(rrgDay(o.Q[f]))}</text>`;
 niceTicks(yd[0],yd[1],6).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm-8}" y="${sy(v)+4}" text-anchor="end">${fmt(v,1)}</text>`});
 niceTicks(xd[0],xd[1],7).forEach(v=>{s+=`<line class="mk-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H-B}"/><text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${fmt(v,1)}</text>`});
 s+=`<line class="mk-axis" x1="${X0}" x2="${X0}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${Lm}" x2="${W-R}" y1="${Y0}" y2="${Y0}"/>`;
 s+=`<text class="rrg-qt rrg-t-lead" x="${W-R-8}" y="${T+16}" text-anchor="end">Leading</text><text class="rrg-qt rrg-t-weak" x="${W-R-8}" y="${H-B-10}" text-anchor="end">Weakening</text>`;
 s+=`<text class="rrg-qt rrg-t-lag" x="${Lm+8}" y="${H-B-10}">Lagging</text><text class="rrg-qt rrg-t-imp" x="${Lm+8}" y="${T+16}">Improving</text>`;
 s+=`<text class="axis" x="${(Lm+W-R)/2}" y="${H-8}" text-anchor="middle">JdK RS-Ratio → (relative trend vs ${esc(o.D.benchmark||'SPY')})</text>`;
 s+=`<text class="axis" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">JdK RS-Momentum →</text>`;
 const boxes=[];let marks='',labels='';
 for(const l of o.lines){
  const c=l.calc,ks=[];for(let k=Math.max(0,f-o.tail+1);k<=f;k++)if(c.x[k]!=null&&c.y[k]!=null)ks.push(k);
  if(!ks.length)continue;
  const pts=ks.map(k=>[sx(c.x[k]),sy(c.y[k])]);
  if(pts.length>1)marks+=`<path class="rot-line rrg-tail" style="stroke:${l.col}" d="${curve(pts,true)}"/>`;
  ks.forEach((k,i)=>{const hd=i===ks.length-1&&k===f,p=pts[i];
   marks+=`<g data-tip="${tip(rrgTipRows(o,l,k))}" tabindex="${hd?0:-1}" class="mk-hit"><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?10:6}" fill="transparent"/><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?6:2.4}" class="rot-dot" style="fill:${l.col};opacity:${hd?1:(.3+.6*i/Math.max(1,ks.length-1)).toFixed(2)}"/></g>`});
  const h=pts[pts.length-1],pv=pts.length>1?pts[pts.length-2]:null;
  if(pv&&ks[ks.length-1]===f){const a=Math.atan2(h[1]-pv[1],h[0]-pv[0]),tx=h[0]+Math.cos(a)*11,ty=h[1]+Math.sin(a)*11;
   marks+=`<path class="rrg-arrow" style="fill:${l.col}" d="M${tx.toFixed(1)},${ty.toFixed(1)} L${(tx-8*Math.cos(a-.45)).toFixed(1)},${(ty-8*Math.sin(a-.45)).toFixed(1)} L${(tx-8*Math.cos(a+.45)).toFixed(1)},${(ty-8*Math.sin(a+.45)).toFixed(1)} Z"/>`}
  const text=l.e.name+(ks[ks.length-1]===f?'':' '+rrgDay(o.Q[ks[ks.length-1]])),w=text.length*6.8,right=h[0]+12+w<W-R;
  const b=[right?h[0]+9:h[0]-9-w,h[1]-20,right?h[0]+9+w:h[0]-9,h[1]-6];
  if(!boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1])){boxes.push(b);labels+=`<text class="mk-label mk-halo" x="${right?h[0]+9:h[0]-9}" y="${h[1]-9}" text-anchor="${right?'start':'end'}">${esc(text)}</text>`}
 }
 return s+marks+labels+'</svg>';
}
function rrgTable(o){
 const f=state.rf,dir=a=>['→','↗','↑','↖','←','↙','↓','↘'][((Math.round(a/(Math.PI/4))%8)+8)%8];
 const rows=o.lines.map(l=>{const c=l.calc,x=c.x[f],y=c.y[f];if(x==null||y==null)return null;
  const qd=rrgQuad(x,y);let since=0;for(let k=f;k>=0&&c.x[k]!=null&&c.y[k]!=null&&rrgQuad(c.x[k],c.y[k])===qd;k--)since++;
  const k0=f-1,a=c.x[k0]!=null?Math.atan2(y-c.y[k0],x-c.x[k0]):null;
  return {l,x,y,qd,since,a,r52:c.z.r52[f],volz:c.z.volz[f]}}).filter(Boolean).sort((p,q)=>q.x-p.x);
 exported=rows.map(r=>({date:o.Q[f],line:r.l.e.name,name:r.l.e.full||'',quadrant:RRG_Q[r.qd][1],rs_ratio:+r.x.toFixed(3),rs_momentum:+r.y.toFixed(3),
  periods_in_quadrant:r.since,heading_deg:r.a==null?null:Math.round(r.a*180/Math.PI),return_12m_vs_benchmark_pct:r.r52==null?null:+r.r52.toFixed(2)}));
 const unit=o.freq==='w'?'weeks':'months';
 let out=`<div class="section-head"><h3>${fmt(rows.length)} lines · ${esc(rrgDay(o.Q[f]))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Line','Quadrant','RS-Ratio','RS-Momentum','Heading','In this quadrant','12 months vs '+(o.D.benchmark||'SPY')],rows.map(r=>[
  `<i class="mk-key" style="background:${r.l.col}"></i> <b>${esc(r.l.e.name)}</b> <span class="muted">${esc(rrgFull_(r.l.e))}</span>`,
  `<span class="badge rrg-b-${RRG_Q[r.qd][0]}">${RRG_Q[r.qd][1]}</span>`,fmt(r.x,2),fmt(r.y,2),r.a==null?'—':dir(r.a),`${r.since} ${unit}`,
  r.r52==null?'—':`<span class="${r.r52>=0?'positive':'negative'}">${vfmt({unit:'%',centred:true},r.r52)}</span>`]));
}

/* ---------- 3-D and 4-D (canvas; turned with the 3-D view's handlers in rotation.js) ---------- */
function rrgPaint3d(o,f){
 const cv=document.getElementById('rot-3d');if(!cv||!cv.getContext)return;
 const ctx=cv.getContext('2d');if(!ctx)return;
 const cw=cv.clientWidth||900,ch=Math.round(Math.max(380,Math.min(660,cw*.64))),dpr=window.devicePixelRatio||1;
 if(cv.width!==Math.round(cw*dpr)||cv.height!==Math.round(ch*dpr)){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.height=ch+'px'}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,cw,ch);
 const C=rotColors(),time=o.zk==='time',{x:xd,y:yd,z:zd}=o.dom,font=getComputedStyle(document.body).fontFamily||'sans-serif';
 const span=time?Math.max(3*o.tail,o.freq==='w'?26:12):o.tail,k0=Math.max(0,f-span+1);
 const nrm=(v,d)=>Math.max(-1.08,Math.min(1.08,(v-d[0])/(d[1]-d[0])*2-1));
 const zOf=(l,k)=>time?(span>1?(k-k0)/(span-1)*2-1:1):(l.calc.z[o.zk][k]==null?null:nrm(l.calc.z[o.zk][k],zd));
 const cy_=Math.cos(ROT.yaw),sy_=Math.sin(ROT.yaw),cp=Math.cos(ROT.pitch),sp=Math.sin(ROT.pitch),S=Math.min(cw*.9,ch)*.26,c0x=cw/2,c0y=ch/2-ch*.03,Dz=6.5;
 const proj=(X,Y,Z)=>{const x1=X*cy_-Z*sy_,z1=X*sy_+Z*cy_,y2=Y*cp-z1*sp,z2=Y*sp+z1*cp,k=Dz/(Dz-z2);return [c0x+x1*k*S,c0y-y2*k*S,z2,k]};
 const line=(a,b,col,w=1,alpha=1,dash)=>{const p=proj(...a),q=proj(...b);ctx.globalAlpha=alpha;ctx.strokeStyle=col;ctx.lineWidth=w;ctx.setLineDash(dash||[]);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1};
 const poly=(pts,col,alpha)=>{ctx.globalAlpha=alpha;ctx.fillStyle=col;ctx.beginPath();pts.map(p=>proj(...p)).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill();ctx.globalAlpha=1};
 const text=(pt,str,col,align='center',f_='11px')=>{const p=proj(...pt);ctx.fillStyle=col;ctx.font=`${f_} ${font}`;ctx.textAlign=align;ctx.fillText(str,p[0],p[1])};
 const X0=nrm(100,xd),Y0=nrm(100,yd),QC=[C.buy,C.sun,C.sell,C.series[0]];
 // the quadrants on the slice that is "now": the front in 3-D (time), the back wall in 4-D
 const zs=time?1:-1,quads=[[[X0,Y0],[1,1]],[[X0,-1],[1,Y0]],[[-1,-1],[X0,Y0]],[[-1,Y0],[X0,1]]];
 quads.forEach(([[a,b],[c,d]],i)=>poly([[a,b,zs],[c,b,zs],[c,d,zs],[a,d,zs]],QC[i],.09));
 const E=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
 for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]])line(E[a],E[b],C.line,1);
 for(let i=-1;i<=1;i+=.5){line([i,-1,-1],[i,-1,1],C.line,.7,.6);line([-1,-1,i],[1,-1,i],C.line,.7,.6)}
 line([X0,-1,-1],[X0,-1,1],C.muted,1,.7,[4,3]);line([-1,Y0,zs],[1,Y0,zs],C.muted,1,.8);line([X0,-1,zs],[X0,1,zs],C.muted,1,.8);
 line([X0,Y0,-1],[X0,Y0,1],C.muted,1,.5,[2,3]);                       // the 100 / 100 axis through the depth
 [['Leading',[1,1,zs],'right'],['Weakening',[1,-1,zs],'right'],['Lagging',[-1,-1,zs],'left'],['Improving',[-1,1,zs],'left']].forEach(([t_,p,al],i)=>{
  const q=[p[0]*.94,p[1]*.9-(p[1]>0?.02:-.06),p[2]];text(q,t_,QC[i],al,'600 11px')});
 const tk=(d,n)=>niceTicks(d[0],d[1],n),ends=t=>t.length>2?[t[0],t[t.length-1]]:t;
 for(const v of ends(tk(xd,6)))text([nrm(v,xd),-1.12,1.12],fmt(v,1),C.muted);
 for(const v of ends(tk(yd,6)))text([-1.12,nrm(v,yd),1.12],fmt(v,1),C.muted,'right');
 if(time){text([1.14,-1.12,-1],rrgDay(o.Q[k0]),C.muted,'left');text([1.14,-1.12,1],rrgDay(o.Q[f]),C.muted,'left')}
 else for(const v of ends(tk(zd,5)))text([1.14,-1.12,nrm(v,zd)],vfmt({unit:'%',centred:true},v),C.muted,'left');
 text([0,-1.3,1.12],'RS-Ratio →',C.ink,'center','600 12px');text([-1.18,1.12,1.0],'↑ RS-Momentum',C.ink,'right','600 12px');
 text([1.22,-1.28,0],time?'time →':RRG_ZINFO[o.zk].label+' →',C.ink,'left','600 12px');
 const dots=[];
 o.lines.forEach(l=>{
  const ks=[];for(let k=k0;k<=f;k++)if(l.calc.x[k]!=null&&l.calc.y[k]!=null&&zOf(l,k)!=null)ks.push(k);
  const tailK=time?ks:ks.slice(-o.tail);if(!tailK.length)return;
  const P3=tailK.map(k=>[nrm(l.calc.x[k],xd),nrm(l.calc.y[k],yd),zOf(l,k)]);
  ctx.strokeStyle=l.col;ctx.lineWidth=2;
  for(let i=1;i<P3.length;i++){const a=proj(...P3[i-1]),b=proj(...P3[i]);ctx.globalAlpha=.2+.75*i/P3.length;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}
  ctx.globalAlpha=1;
  tailK.forEach((k,i)=>{const pr=proj(...P3[i]),hd=k===f;
   if(hd||i%Math.max(1,Math.round(tailK.length/26))===0)dots.push({x:pr[0],y:pr[1],d:pr[2],r:(hd?6:2)*pr[3],col:l.col,alpha:hd?1:.3+.6*i/tailK.length,rows:rrgTipRows(o,l,k),stroke:hd})});
  const h=P3[P3.length-1];
  if(tailK[tailK.length-1]===f){line(h,[h[0],-1,h[2]],l.col,1,.45,[2,3]);const pr=proj(...h);dots.push({label:l.e.name,x:pr[0],y:pr[1],d:pr[2]+.001})}
 });
 dots.sort((a,b)=>a.d-b.d);
 const hits=[],boxes=[];
 for(const d of dots){
  if(d.label){ctx.font=`500 12px ${font}`;const w=ctx.measureText(d.label).width,b=[d.x+8,d.y-20,d.x+12+w,d.y-6];
   if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))continue;boxes.push(b);
   ctx.lineWidth=3;ctx.strokeStyle=C.surface;ctx.textAlign='left';ctx.strokeText(d.label,d.x+9,d.y-9);ctx.fillStyle=C.ink;ctx.fillText(d.label,d.x+9,d.y-9);continue}
  ctx.globalAlpha=d.alpha;ctx.fillStyle=d.col;ctx.beginPath();ctx.arc(d.x,d.y,Math.max(1,d.r),0,Math.PI*2);ctx.fill();
  if(d.stroke){ctx.globalAlpha=1;ctx.lineWidth=1.5;ctx.strokeStyle=C.surface;ctx.stroke()}
  ctx.globalAlpha=1;hits.push(d)}
 ctx.font=`700 40px ${font}`;ctx.textAlign='right';ctx.fillStyle=C.ink;ctx.globalAlpha=.08;ctx.fillText(rrgDay(o.Q[f]),cw-14,ch-14);ctx.globalAlpha=1;
 ROT.hits=hits;
}
