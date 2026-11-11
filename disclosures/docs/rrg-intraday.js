/* 4.6d Intraday RRG and the money-inflow screen (Rotation → Intraday RRG; also the RRG's Frequency "Intraday").
   Data: rotation.json on the branch intraday-live (app/intraday_rotation.py, written by the relay with live.json every
   five minutes through the session), read from raw.githubusercontent.com every minute while the view shows.
   · The RRG of today's five-minute bars against SPY, with the weekly and daily charts' formula (RRGLab.states: RS
     smoothed over 15 minutes, its trend over the window chosen, the gap and its change, in standard units of the six
     sessions on the grid): every line's path through the session, played bar by bar, each head ringed by its money
     flow since the open (green in, red out).
   · Where the money flows: the lines of the chart by today's inflow share (bars), and the screen — every line of every
     group, or one group: today's net money inflow (Chaikin's, from the five-minute bars), its share of the dollars
     traded, the last hour and 30 minutes, the dollars against the 20 sessions before by the same time, how today's
     inflow ranks against theirs, the price against VWAP and the RRG quadrant now; filtered and sorted as asked.
   Prices as Yahoo publishes them (some may be delayed); the flow is an estimate from bars, not a count of buyers.
   Pure functions are exported for Node (tests); the hub's helpers (state, esc, fmt, field, table, tip, curve, rotSize,
   niceTicks, rotPlayer, RRG_COL, RRG_Q, rrgQuad, RRGLab…) are used by the view functions only. */
const RRGI={store:null,timer:null,lastK:null,dec:null,src:'https://raw.githubusercontent.com/eurikamonica/filing-flows/intraday-live/rotation.json'};
const RRGI_FREQ=[['w','Weekly (the standard)'],['d','Daily (every trading day)'],['m','Monthly (long cycles)'],['i','Intraday (today, five-minute bars)']];
const RRGI_WINS=[['12','1 hour (fast)'],['24','2 hours'],['39','Half a session'],['78','A whole session (slow)']];
const RRGI_TAILS=[['6','30 minutes'],['12','1 hour'],['24','2 hours'],['78','The whole session']];
const RRGI_FLOW=[['rings','Each head ringed by its money flow since the open'],['off','Off']];
const RRGI_GAP=[['out','Left out: each session from its open'],['in','Counted: the move since the close before']];
const RRGI_PAR={sh:3,long:n=>Math.max(390,3*n),minNorm:156};   // 15-minute smoothing; standard units over five sessions or more
const RRGI_SG=[['all','Every line (all groups)'],['chart','The lines on the chart']];
const RRGI_SORT=[['share','Inflow share of the dollars traded: most in first'],['shareasc','Inflow share: most out first'],
 ['net','Net inflow in dollars: most in first'],['netasc','Net outflow in dollars: most out first'],
 ['unusual','Most unusual inflow for this time (vs 20 sessions)'],['unusualasc','Most unusual outflow for this time'],
 ['rvol','Heaviest volume against the usual'],['h1','Last hour: most in first'],['h1asc','Last hour: most out first'],
 ['rs','Move against SPY: best first'],['rsasc','Move against SPY: worst first']];
const RRGI_FILTER=[['all','Every line'],['in','Money flowing in'],['out','Money flowing out'],
 ['unusual','Unusual inflow (top 10% of the last 20 sessions by this time)'],['unusualout','Unusual outflow (bottom 10%)'],
 ['heavy','Heavy volume (1.5× the usual or more)'],['inweak','Buying into weakness (money in, the price down today)'],
 ['outstrong','Selling into strength (money out, the price up today)'],['lead','Leading or Improving on the RRG, with money in']];

/* ---------- pure: the file decoded, the RRG, the screen ---------- */
// bar k closes at 9:30 + 5k minutes
function rrgiHm(k){const m=570+5*k,h=Math.floor(m/60),mm=m%60;return `${h>12?h-12:h}:${String(mm).padStart(2,'0')} ${h>=12?'pm':'am'}`}
function rrgiDay(day){const M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(day||''));
 if(!m)return String(day||'');const wd=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date(Date.UTC(+m[1],+m[2]-1,+m[3])).getUTCDay()];return `${wd}, ${M[+m[2]-1]} ${+m[3]}`}
// the closes (log moves in tenths of a basis point, delta-coded) and today's flow added up bar by bar ($ thousands)
function rrgiDecode(d){
 const N=d.slots.reduce((a,b)=>a+b,0),off=N-d.slots[d.slots.length-1],C={},F={};
 for(const [t,a] of Object.entries(d.assets||{})){
  let q=0;C[t]=(a.c||[]).map(x=>{q+=x;return a.c0*Math.exp(q/1e5)});
  let s=0,n=0;F[t]={dv:(a.dv||[]).map(x=>s+=x),nf:(a.nf||[]).map(x=>n+=x)};
 }
 return {src:d,N,off,C,F,calc:new Map()};
}
// a line's closes chained without the gaps overnight: each session from its opening price (the first bar: its close over
// the open); a session with no opening price on file keeps its gap
function rrgiSeries(D,t,gap){
 const C=D.C[t];if(!C||gap==='in')return C;
 const o=(D.src.assets[t]||{}).o||[],sl=D.src.slots,out=new Array(C.length);
 let i=0,v=C[0];
 for(let s=0;s<sl.length;s++)for(let k=0;k<sl[s];k++,i++){
  if(i>0)v*=k===0&&o[s]>0?C[i]/o[s]:C[i]/C[i-1];
  out[i]=v;
 }
 return out;
}
// one line's RS against the benchmark on the grid, and its RS-Ratio and RS-Momentum (window n bars)
function rrgiCalc(D,t,n,states,gap){
 const key=t+'|'+n+'|'+(gap||'out');if(D.calc.has(key))return D.calc.get(key);
 const C=rrgiSeries(D,t,gap),B=rrgiSeries(D,D.src.bench||'SPY',gap);
 if(!C||!B||C.length!==B.length)return null;
 const rs=C.map((c,i)=>c!=null&&B[i]>0?100*c/B[i]:null);
 const St=(states||RRGLab.states)(rs,RRGI_PAR.sh,n,RRGI_PAR.long(n),RRGI_PAR.minNorm);
 const out={x:St.x,y:St.y,c:D.C[t],rs};D.calc.set(key,out);return out;
}
const rrgiQuad=(x,y)=>x>=100?(y>=100?0:1):(y<100?2:3);
// every line of the screen at the last full bar: the reading the server made (now) and the RRG at that bar
function rrgiRows(d,D,n,ids,states,gap){
 const B=d.assets[d.bench||'SPY'],bm=B&&B.prev?B.price/B.prev-1:null,g=D.off+Math.max(1,(d.session||{}).kf||1)-1;
 const gOf={};(d.groups||[]).forEach(([id,,ts])=>ts.forEach(t=>{(gOf[t]=gOf[t]||[]).push(id)}));
 return ids.filter(t=>d.assets[t]).map(t=>{
  const a=d.assets[t],w=a.now||{},mv=a.prev&&a.price?a.price/a.prev-1:null,rs=t===(d.bench||'SPY')||mv==null||bm==null?null:mv-bm;
  const c=t===(d.bench||'SPY')?null:rrgiCalc(D,t,n,states,gap),x=c?c.x[g]:null,y=c?c.y[g]:null;
  return {t,name:a.name||t,groups:gOf[t]||[],price:a.price,move:mv,rs,net:w.net,dv:w.dv,share:w.share,h1:w.h1,m30:w.m30,rvol:w.rvol,rank:w.rank,z:w.z,n:w.n,
   vw:w.vwap&&a.price?a.price/w.vwap-1:null,x,y,q:x!=null&&y!=null?rrgiQuad(x,y):null};
 });
}
const rrgiNum=v=>v!=null&&Number.isFinite(v);
function rrgiFilter(rows,f){
 const P={in:r=>r.share>0,out:r=>r.share<0,unusual:r=>rrgiNum(r.rank)&&r.rank>=0.9&&r.share>0,unusualout:r=>rrgiNum(r.rank)&&r.rank<=0.1&&r.share<0,
  heavy:r=>rrgiNum(r.rvol)&&r.rvol>=1.5,inweak:r=>r.share>0&&rrgiNum(r.move)&&r.move<0,outstrong:r=>r.share<0&&rrgiNum(r.move)&&r.move>0,lead:r=>(r.q===0||r.q===3)&&r.share>0}[f];
 return P?rows.filter(r=>rrgiNum(r.share)&&P(r)):rows.slice();
}
function rrgiSort(rows,s){
 const asc=/asc$/.test(s),k=s.replace(/asc$/,''),key={share:'share',net:'net',unusual:'z',rvol:'rvol',h1:'h1',rs:'rs'}[k]||'share';
 const v=r=>rrgiNum(r[key])?r[key]:k==='unusual'&&rrgiNum(r.rank)?(r.rank-.5)*4:null;   // a line without a z: its rank
 return rows.slice().sort((a,b)=>{const p=v(a),q=v(b);if(p==null&&q==null)return 0;if(p==null)return 1;if(q==null)return -1;return asc?p-q:q-p});
}
// the flags: unusual against the line's own last 20 sessions and stronger than the market's flow (SPY's share: m), so a
// day when everything closes near its highs does not flag every line; money in while the price falls, out while it rises
function rrgiTags(r,m){
 const t=[],mk=rrgiNum(m)?m:0;
 if(rrgiNum(r.rank)&&r.rank>=0.95&&r.share>0&&r.share>mk)t.push(['in','Unusual inflow']);
 if(rrgiNum(r.rank)&&r.rank<=0.05&&r.share<0&&r.share<mk)t.push(['out','Unusual outflow']);
 if(r.share>0&&rrgiNum(r.move)&&r.move<0)t.push(['in','Buying into weakness']);
 if(r.share<0&&rrgiNum(r.move)&&r.move>0)t.push(['out','Selling into strength']);
 if(rrgiNum(r.rvol)&&r.rvol>=2)t.push(['vol','Heavy volume']);
 return t;
}

/* ---------- loading ---------- */
function rrgiLoad(force){                               // the page is drawn again only when a new file has come
 const m=RRGI.store||(RRGI.store={});
 if(m.loading)return m;
 if(!force&&(m.data||m.err))return m;
 if(typeof fetch!=='function'){m.err='no fetch';return m}
 let fresh=false;
 m.loading=fetch(RRGI.src,{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{
  if(!d||d.schema!=='intraday-rotation.v1'||!d.assets)throw Error('an unexpected file');
  fresh=!m.data||m.data.generated_at!==d.generated_at;
  if(fresh){m.data=d;RRGI.dec=null}m.err=null;
 }).catch(e=>{if(!m.data){m.err=e.message;fresh=true}}).finally(()=>{m.loading=null;m.at=Date.now();if(fresh)rrgiRefresh()});
 return m;
}
const rrgiShown=()=>typeof state==='object'&&state.tab==='rotation'&&state.rview==='rrgi';
function rrgiRefresh(){if(rrgiShown()&&!(typeof ROT==='object'&&(ROT.timer||ROT.exporting||ROT.drag))&&typeof render==='function')render()}
function rrgiTimer(){                                    // again every minute while the view shows (not while the tab is hidden)
 if(RRGI.timer||typeof setInterval!=='function')return;
 RRGI.timer=setInterval(()=>{
  if(!rrgiShown()||typeof document==='undefined'||!document.getElementById('rrgi-root')){clearInterval(RRGI.timer);RRGI.timer=null;return}
  if(!document.hidden)rrgiLoad(true)},60000);
}

/* ---------- the view ---------- */
function rrgIntradayView(){
 const m=rrgiLoad(false);rrgiTimer();
 const bar=(groups,uni)=>`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${groups?field('rrgu','Lines',groups,uni):''}${field('rrgif','Frequency',RRGI_FREQ,'i')}</div>`;
 if(!m.data)return bar(null,'')+`<div id="rrgi-root">${m.err?empty('Today’s rotation could not load ('+m.err+'). It is published every five minutes through the session; refresh to retry.'):empty('Loading today’s five-minute bars…')}</div>`;
 const d=m.data,D=RRGI.dec&&RRGI.dec.src===d?RRGI.dec:(RRGI.dec=rrgiDecode(d)),bench=d.bench||'SPY',S=d.session||{};
 const groups=(d.groups||[]).filter(g=>g[2]&&g[2].length).map(g=>[g[0],g[1]]);
 const has=u=>groups.some(g=>g[0]===u),uni=has(state.rrgu)?state.rrgu:state.rrgu==='indices'&&has('idxetf')?'idxetf':has('sectors')?'sectors':(groups[0]||[''])[0];
 state.rrgin=RRGI_WINS.some(x=>x[0]===state.rrgin)?state.rrgin:'24';
 state.rrgit=RRGI_TAILS.some(x=>x[0]===state.rrgit)?state.rrgit:'12';
 state.rrgiflow=RRGI_FLOW.some(x=>x[0]===state.rrgiflow)?state.rrgiflow:'rings';
 state.rrgigap=RRGI_GAP.some(x=>x[0]===state.rrgigap)?state.rrgigap:'out';
 const n=+state.rrgin,ids=((d.groups||[]).find(g=>g[0]===uni)||[0,0,[]])[2].filter(t=>t!==bench&&D.C[t]);
 const lines=ids.map((t,i)=>({e:{id:t,name:t,full:(d.assets[t]||{}).name||t},col:RRG_COL[i%RRG_COL.length],calc:rrgiCalc(D,t,n,null,state.rrgigap)})).filter(l=>l.calc);
 const K=d.slots[d.slots.length-1],Q=Array.from({length:K},(_,k)=>k+1);
 const key='rrgi|'+S.date;
 if(state.rfk!==key||!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<K)){state.rf=K-1;state.rfk=key}
 else if(RRGI.lastK!=null&&state.rf===RRGI.lastK-1&&K>RRGI.lastK)state.rf=K-1;   // at the latest bar: follow the new one
 RRGI.lastK=K;
 const pick=String(state.rrgsolo||'').split(',').filter((id,i,a)=>id&&a.indexOf(id)===i&&lines.some(l=>l.e.id===id));
 const o={d,D,lines,Q,n,gap:state.rrgigap,tail:+state.rrgit,pick:new Set(pick),flow:state.rrgiflow==='rings',bench,day:S.date,
  P:{span:K,unit:'five-minute bars',ms:140,label:k=>`${rrgiDay(S.date)} · ${rrgiHm(k)} ET`}};
 o.dom=rrgiDomain(o);
 let out=bar(groups,uni)+`<div id="rrgi-root">`;
 out+=`<div class="toolbar rot-display">${field('rrgin','RS window',RRGI_WINS,state.rrgin)}${field('rrgit','Tail',RRGI_TAILS,state.rrgit)}${field('rrgigap','Overnight gaps',RRGI_GAP,state.rrgigap)}${field('rrgiflow','Money flow on the chart',RRGI_FLOW,state.rrgiflow)}`
  +`<div class="field wide" style="flex-basis:100%"><label>Show <span class="muted">(tap to pick one or more)</span></label><div class="pills rrg-pick" role="group" aria-label="Lines on the chart"><button type="button" class="pill" data-rrgpick="" aria-pressed="${pick.length?'false':'true'}">All lines</button>${lines.map(l=>`<button type="button" class="pill" data-rrgpick="${esc(l.e.id)}" aria-pressed="${o.pick.has(l.e.id)?'true':'false'}"><i class="mk-key" style="background:${l.col}"></i>${esc(l.e.name)}</button>`).join('')}</div></div></div>`;
 const ago=Math.max(0,Math.round((Date.now()-Date.parse(d.generated_at))/60000));
 out+=`<p class="sub">${S.open?'<span class="rrgi-dot" aria-hidden="true"></span>Live: ':''}${esc(rrgiDay(S.date))}, five-minute bars to ${esc(rrgiHm(K))} ET${S.open?'':' (the session is over'+(S.short?'; an early close':'')+')'} · built ${ago<1?'just now':ago+' min ago'}${S.open?', again every five minutes':''} · ${esc(d.source||'')}</p>`;
 out+=`<div class="panel"><h3>Intraday Relative Rotation Graph</h3><p class="sub">→ JdK RS-Ratio (relative trend over ${esc(RRGI_WINS.find(x=>x[0]===state.rrgin)[1].replace(/ \(.*\)$/,''))}) · ↑ JdK RS-Momentum (its speed) · against ${esc(bench)}, five-minute bars${o.flow?' · ring: money flow since the open (green in, red out; wider = a larger share of the dollars traded)':''}</p>`;
 out+=rotPlayer(Q,o.P);
 if(window.FFShare)out+=window.FFShare.bar({key:'hub-rrgi',title:'Intraday RRG · '+(groups.find(g=>g[0]===uni)||[0,''])[1]+' — '+rrgiDay(S.date)+' '+rrgiHm(Math.min(state.rf+1,K))+' ET',
  subtitle:'→ RS-Ratio · ↑ RS-Momentum against '+bench+', five-minute bars',source:'Five-minute bars (Yahoo Finance); RRG computed in the browser (Filing Flows).'});
 ROT.ctx={Q,P:o.P,draw:f=>rrgiFrame(o,f),key:'hub-rrgi'};
 out+=`<div id="rot-plot" data-ffs-chart="hub-rrgi">${rrgiFrame(o,state.rf)}</div>`;
 out+=`<div class="mk-legend rrg-legend">${lines.map(l=>{const off=o.pick.size&&!o.pick.has(l.e.id);return `<span${off?' class="muted"':''}><i class="mk-key" style="background:${l.col}${off?';opacity:.35':''}"></i>${esc(l.e.name)} <span class="muted">${esc(l.e.full)}${off?' · hidden':''}</span></span>`}).join('')}${RRG_Q.map(([k,name])=>`<span><i class="mk-key rrg-k-${k}"></i>${esc(name)}</span>`).join('')}${o.flow?'<span><i class="mk-key rrgi-key-in"></i>Money in</span><span><i class="mk-key rrgi-key-out"></i>Money out</span>':''}</div>`;
 out+='</div>';
 out+=rrgiBars(o)+rrgiScreen(o);
 out+=`<details><summary>How the intraday RRG and the money flow are computed</summary><p>RS = 100 × each line's five-minute close ÷ ${esc(bench)}'s, on every bar of the five sessions before today and today's (a bar with no trade keeps the close before). The gaps overnight are left out unless you count them: each session is chained from its opening price, so the chart shows how the lines move against each other during the session; counted, a line that opens far from its last close leaps away at the open and comes back as its trend catches up. Smoothed over 15 minutes (3 bars), RS-Ratio is how far it stands above or below its own trend over the window chosen (an exponential average), and RS-Momentum the change of that gap from one bar to the next, smoothed the same way; both in standard deviations of their own last five sessions around 100 — the formula of the weekly and daily charts, on five-minute bars. Leadership rotates clockwise: Improving → Leading → Weakening → Lagging.</p><p>Money flow: Chaikin's measure on every five-minute bar, as on the weekly chart — the bar's dollars (volume × the typical price) weighted by where it closed in its range: +1 at its high, −1 at its low. The net inflow is the sum since the open, its share is that sum over the dollars traded; "vs 20 sessions" ranks today's share against those sessions' by the same bar, and "volume vs usual" divides today's dollars by their median by the same bar. US markets publish no large-order ("main force") figures, so this is an estimate from the bars, not a count of buyers and sellers; prices as Yahoo Finance publishes them (some may be delayed). History, not investment advice.</p></details>`;
 return out+'</div>';
}
function rrgiDomain(o){                                  // symmetric around 100, fixed for the day so play does not rescale
 const xs=[],ys=[],k0=Math.max(0,o.D.off-o.tail);
 for(const l of o.lines)for(let k=k0;k<o.D.N;k++){const x=l.calc.x[k],y=l.calc.y[k];if(x==null||y==null)continue;xs.push(Math.abs(x-100));ys.push(Math.abs(y-100))}
 const q=(a,p)=>{if(!a.length)return 1;const s=a.slice().sort((u,v)=>u-v);return s[Math.min(s.length-1,Math.floor(p*(s.length-1)))]};
 const mx=Math.max(1.2,q(xs,.985)*1.08),my=Math.max(1.2,q(ys,.985)*1.08);
 return {x:[100-mx,100+mx],y:[100-my,100+my]};
}
function rrgiFrame(o,f){
 const [W,H]=rotSize(.62,420,700),Lm=58,R=18,T=16,B=44,{x:xd,y:yd}=o.dom,g=o.D.off+f;
 const cx=v=>Math.max(xd[0],Math.min(xd[1],v)),cy=v=>Math.max(yd[0],Math.min(yd[1],v));
 const sx=v=>Lm+(cx(v)-xd[0])/(xd[1]-xd[0])*(W-Lm-R),sy=v=>T+(yd[1]-cy(v))/(yd[1]-yd[0])*(H-T-B);
 const X0=sx(100),Y0=sy(100),when=o.P.label(f+1);
 let s=`<svg class="plot mk-plot rrg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Intraday Relative Rotation Graph, ${esc(when)}; the screen below lists every value">`;
 s+=`<rect class="rrg-lead" x="${X0}" y="${T}" width="${W-R-X0}" height="${Y0-T}"/><rect class="rrg-weak" x="${X0}" y="${Y0}" width="${W-R-X0}" height="${H-B-Y0}"/>`;
 s+=`<rect class="rrg-lag" x="${Lm}" y="${Y0}" width="${X0-Lm}" height="${H-B-Y0}"/><rect class="rrg-imp" x="${Lm}" y="${T}" width="${X0-Lm}" height="${Y0-T}"/>`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-14}" text-anchor="end">${esc(rrgiHm(f+1))}</text>`;
 niceTicks(yd[0],yd[1],6).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm-8}" y="${sy(v)+4}" text-anchor="end">${fmt(v,1)}</text>`});
 niceTicks(xd[0],xd[1],7).forEach(v=>{s+=`<line class="mk-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H-B}"/><text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${fmt(v,1)}</text>`});
 s+=`<line class="mk-axis" x1="${X0}" x2="${X0}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${Lm}" x2="${W-R}" y1="${Y0}" y2="${Y0}"/>`;
 s+=`<text class="rrg-qt rrg-t-lead" x="${W-R-8}" y="${T+16}" text-anchor="end">Leading</text><text class="rrg-qt rrg-t-weak" x="${W-R-8}" y="${H-B-10}" text-anchor="end">Weakening</text>`;
 s+=`<text class="rrg-qt rrg-t-lag" x="${Lm+8}" y="${H-B-10}">Lagging</text><text class="rrg-qt rrg-t-imp" x="${Lm+8}" y="${T+16}">Improving</text>`;
 s+=`<text class="axis" x="${(Lm+W-R)/2}" y="${H-8}" text-anchor="middle">JdK RS-Ratio → (relative trend vs ${esc(o.bench)})</text>`;
 s+=`<text class="axis" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">JdK RS-Momentum →</text>`;
 const boxes=[];let rings='',marks='',labels='';
 for(const l of o.lines){
  if(o.pick.size&&!o.pick.has(l.e.id))continue;
  const c=l.calc,ks=[];for(let k=Math.max(0,g-o.tail+1);k<=g;k++)if(c.x[k]!=null&&c.y[k]!=null)ks.push(k);
  if(!ks.length)continue;
  const pts=ks.map(k=>[sx(c.x[k]),sy(c.y[k])]),h=pts[pts.length-1],F=o.D.F[l.e.id];
  if(pts.length>1)marks+=`<path class="rot-line rrg-tail" style="stroke:${l.col}" d="${curve(pts,true)}"/>`;
  const sh=F&&F.dv[f]>0?F.nf[f]/F.dv[f]:null;
  ks.forEach((k,i)=>{const hd=i===ks.length-1&&k===g,p=pts[i];
   marks+=`<g data-tip="${tip(rrgiTip(o,l,k,hd?sh:null))}" tabindex="${hd?0:-1}" class="mk-hit"><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?10:6}" fill="transparent"/><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?6:2.2}" class="rot-dot" style="fill:${l.col};opacity:${hd?1:(.3+.6*i/Math.max(1,ks.length-1)).toFixed(2)}"/></g>`});
  if(o.flow&&sh!=null&&ks[ks.length-1]===g){const r=8.5+9*Math.min(1,Math.abs(sh)/0.5);
   rings+=`<circle class="rrgi-ring ${sh>=0?'rrgi-in':'rrgi-out'}" cx="${h[0].toFixed(1)}" cy="${h[1].toFixed(1)}" r="${r.toFixed(1)}" style="stroke-width:${(1.6+2.4*Math.min(1,Math.abs(sh)/0.5)).toFixed(1)}"/>`}
  const pv=pts.length>1?pts[pts.length-2]:null;
  if(pv&&ks[ks.length-1]===g){const a=Math.atan2(h[1]-pv[1],h[0]-pv[0]),tx=h[0]+Math.cos(a)*11,ty=h[1]+Math.sin(a)*11;
   marks+=`<path class="rrg-arrow" style="fill:${l.col}" d="M${tx.toFixed(1)},${ty.toFixed(1)} L${(tx-8*Math.cos(a-.45)).toFixed(1)},${(ty-8*Math.sin(a-.45)).toFixed(1)} L${(tx-8*Math.cos(a+.45)).toFixed(1)},${(ty-8*Math.sin(a+.45)).toFixed(1)} Z"/>`}
  const kl=ks[ks.length-1],text=l.e.name+(c.c[kl]!=null?' $'+fmt(c.c[kl],c.c[kl]>=1000?0:2):''),w=text.length*6.8,right=h[0]+12+w<W-R,low=h[1]-22<T,ly=low?h[1]+18:h[1]-9;
  const b=[right?h[0]+9:h[0]-9-w,ly-11,right?h[0]+9+w:h[0]-9,ly+3];
  if(!boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1])){boxes.push(b);labels+=`<text class="mk-label mk-halo" x="${right?h[0]+9:h[0]-9}" y="${ly}" text-anchor="${right?'start':'end'}">${esc(text)}</text>`}
 }
 return s+rings+marks+labels+'</svg>';
}
function rrgiTip(o,l,k,sh){
 const c=l.calc,x=c.x[k],y=c.y[k],qd=RRG_Q[rrgiQuad(x,y)],d=o.d;
 let at=k-o.D.off,day=o.day;
 if(at<0){let j=d.slots.length-2,kk=k;for(let i=0;i<d.slots.length-1;i++){if(kk<d.slots[i]){j=i;break}kk-=d.slots[i]}at=kk;day=d.days[j]}
 const rows=[[l.e.name+' · '+rrgiDay(day)+' '+rrgiHm(at+1),l.e.full],[qd[1],qd[2]],['$'+fmt(c.c[k],c.c[k]>=1000?0:2),'close of the bar'],[fmt(x,2),'RS-Ratio'],[fmt(y,2),'RS-Momentum']];
 if(sh!=null)rows.push([(sh>0?'+':sh<0?'−':'')+fmt(Math.abs(100*sh),1)+'%','money flow since the open, share of the dollars traded']);
 return rows;
}
const rrgiPc=(v,d=1)=>!rrgiNum(v)?'—':`<span class="${v>0?'positive':v<0?'negative':''}">${v>0?'+':v<0?'−':''}${fmt(Math.abs(100*v),d)}%</span>`;
const rrgiMoney=v=>!rrgiNum(v)||Math.round(v)===0?'—':`<span class="${v>0?'positive':'negative'}">${v>0?'+':'−'}$${compact(Math.abs(v))}</span>`;
const rrgiRank=r=>!rrgiNum(r)?'—':r>=0.5?`top ${fmt(Math.max(5,Math.round(100*(1-r))),0)}%`:`bottom ${fmt(Math.max(5,Math.round(100*r)),0)}%`;
// the lines of the chart by today's inflow share: diverging bars, most in at the top
function rrgiBars(o){
 const d=o.d,rows=rrgiSort(rrgiRows(d,o.D,o.n,o.lines.map(l=>l.e.id),null,o.gap).filter(r=>rrgiNum(r.share)),'share');
 if(!rows.length)return '';
 const [W]=rotSize(.62,420,700),narrow=W<560,rh=22,T=8,H=T+rows.length*rh+20,lw=narrow?58:Math.min(190,Math.round(W*.3)),rw=narrow?0:Math.min(150,Math.round(W*.24)),x0=lw+(W-lw-rw)/2,half=Math.max(30,(W-lw-rw)/2-56);   // room for the value beside the longest bar; a phone: the volume and rank in the tips
 const mx=Math.max(.1,...rows.map(r=>Math.abs(r.share))),sx=v=>x0+v/mx*half,col=new Map(o.lines.map(l=>[l.e.id,l.col]));
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Money flow since the open, share of the dollars traded, line by line; the screen below lists every value">`;
 s+=`<line class="mk-axis" x1="${x0}" x2="${x0}" y1="${T-4}" y2="${H-18}"/>`;
 rows.forEach((r,i)=>{const y=T+i*rh,v=r.share,x=sx(v),bw=Math.max(2,Math.abs(x-x0));
  s+=`<g data-tip="${tip([[r.t+' · since the open',r.name],[(v>0?'+':v<0?'−':'')+fmt(Math.abs(100*v),1)+'%','money flow, share of the dollars traded'],['$'+compact(Math.abs(r.net||0)),(r.net>=0?'net inflow':'net outflow')],[rrgiNum(r.rvol)?fmt(r.rvol,2)+'×':'—','dollars traded vs the usual by now'],[rrgiRank(r.rank),'inflow vs the last 20 sessions by now']])}" class="mk-hit">`
   +`<rect x="${(v>=0?x0:x0-bw).toFixed(1)}" y="${y+4}" width="${bw.toFixed(1)}" height="${rh-8}" rx="3" class="${v>=0?'rrgi-bin':'rrgi-bout'}"/>`
   +`<text class="axis" x="${lw-8}" y="${y+rh/2+4}" text-anchor="end"><tspan style="fill:${col.get(r.t)||'currentColor'}">■</tspan> ${esc(r.t)}</text>`
   +`<text class="axis" x="${(v>=0?x0+bw+5:x0-bw-5).toFixed(1)}" y="${y+rh/2+4}" text-anchor="${v>=0?'start':'end'}">${v>0?'+':v<0?'−':''}${fmt(Math.abs(100*v),1)}%</text>`
   +(narrow?'':`<text class="axis rrgi-muted" x="${W-rw+6}" y="${y+rh/2+4}">${rrgiNum(r.rvol)?fmt(r.rvol,1)+'× vol':''}${rrgiNum(r.rank)?' · '+rrgiRank(r.rank):''}</text>`)+'</g>'});
 s+=`<text class="axis" x="${x0}" y="${H-4}" text-anchor="middle">${narrow?'← money out · money in →':'← money out · share of the dollars traded since the open · money in →'}</text></svg>`;
 return `<div class="panel"><h3>Where the money flows today · the lines of the chart</h3><p class="sub">Net money inflow since the open as a share of the dollars traded (Chaikin's, five-minute bars), to the last full bar, ${esc(rrgiHm((d.session||{}).kf||1))} ET · ${narrow?'tap a bar for':'beside it:'} the dollars traded against the usual by this time, and today's inflow ranked against the last 20 sessions by this time</p>${s}</div>`;
}
// the screen: every line (or one group), filtered and sorted
function rrgiScreen(o){
 const d=o.d,groups=(d.groups||[]).filter(g=>g[2]&&g[2].length);
 const SG=RRGI_SG.concat(groups.map(g=>[g[0],g[1]]));
 state.rrgisg=SG.some(x=>x[0]===state.rrgisg)?state.rrgisg:'all';
 state.rrgiss=RRGI_SORT.some(x=>x[0]===state.rrgiss)?state.rrgiss:'share';
 state.rrgisf=RRGI_FILTER.some(x=>x[0]===state.rrgisf)?state.rrgisf:'all';
 const all=Object.keys(d.assets),ids=state.rrgisg==='all'?all:state.rrgisg==='chart'?o.lines.map(l=>l.e.id):((groups.find(g=>g[0]===state.rrgisg)||[0,0,[]])[2]);
 const rows0=rrgiRows(d,o.D,o.n,ids,null,o.gap),rows=rrgiSort(rrgiFilter(rows0,state.rrgisf),state.rrgiss);
 const gname=Object.fromEntries(groups.map(g=>[g[0],g[1].replace(/ \(.*\)$/,'')]));
 const nin=rows0.filter(r=>r.share>0).length,nout=rows0.filter(r=>r.share<0).length,mk=((d.assets[d.bench||'SPY']||{}).now||{}).share;
 exported=rows.map(r=>({session:d.session.date,bar_close_et:rrgiHm(d.session.kf||1),line:r.t,name:r.name,groups:r.groups.join(' '),price:r.price,move_pct:rrgiNum(r.move)?+(100*r.move).toFixed(3):null,
  vs_spy_pct:rrgiNum(r.rs)?+(100*r.rs).toFixed(3):null,net_inflow_usd:r.net,dollars_traded_usd:r.dv,inflow_share_pct:rrgiNum(r.share)?+(100*r.share).toFixed(2):null,
  last_hour_share_pct:rrgiNum(r.h1)?+(100*r.h1).toFixed(2):null,last_30min_share_pct:rrgiNum(r.m30)?+(100*r.m30).toFixed(2):null,volume_vs_usual:r.rvol,
  inflow_rank_vs_20_sessions:r.rank,inflow_z_vs_20_sessions:r.z,sessions_compared:r.n,vs_vwap_pct:rrgiNum(r.vw)?+(100*r.vw).toFixed(3):null,
  rrg_quadrant:r.q==null?null:RRG_Q[r.q][1],rs_ratio:rrgiNum(r.x)?+r.x.toFixed(3):null,rs_momentum:rrgiNum(r.y)?+r.y.toFixed(3):null}));
 let out=`<div class="panel" id="rrgi-screen"><div class="section-head"><h3>Money-inflow screen · ${fmt(rows.length)} of ${fmt(rows0.length)} lines</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=`<p class="sub">To the last full bar, ${esc(rrgiHm(d.session.kf||1))} ET: money flowing in on ${fmt(nin)} of ${fmt(rows0.length)} lines, out on ${fmt(nout)}${rrgiNum(mk)?`; the market's (${esc(d.bench||'SPY')}) share ${mk>0?'+':mk<0?'−':''}${fmt(Math.abs(100*mk),1)}%`:''}. Flagged: unusual inflow or outflow (beyond 19 of the last 20 sessions by this time, and stronger than the market's), money in while the price falls today or out while it rises, volume twice the usual. The RRG quadrant with the window above.</p>`;
 out+=`<div class="toolbar">${field('rrgisg','Lines',SG,state.rrgisg)}${field('rrgisf','Show',RRGI_FILTER,state.rrgisf,true)}${field('rrgiss','Sort',RRGI_SORT,state.rrgiss,true)}</div>`;
 out+=table(['Line','Price · today','vs SPY','Net inflow','Share of $ traded','Last hour · 30 min','Volume vs usual','Inflow vs 20 sessions','vs VWAP','RRG now'],rows.map(r=>[
  `<b>${esc(r.t)}</b> ${esc(r.name)}${state.rrgisg==='all'&&r.groups.length?`<br><span class="muted">${esc(r.groups.map(g=>gname[g]||g).join(', '))}</span>`:''}${(tg=>tg.length?'<br>'+tg.map(([k,t])=>`<span class="badge rrgi-t-${k}">${esc(t)}</span>`).join(' '):'')(rrgiTags(r,mk))}`,
  `${rrgiNum(r.price)?'$'+fmt(r.price,r.price>=1000?0:2):'—'}<br>${rrgiPc(r.move,2)}`,rrgiPc(r.rs,2),rrgiMoney(r.net)+(rrgiNum(r.dv)?`<br><span class="muted">of $${compact(r.dv)}</span>`:''),
  rrgiPc(r.share),`${rrgiPc(r.h1)} · ${rrgiPc(r.m30)}`,rrgiNum(r.rvol)?fmt(r.rvol,2)+'×':'—',
  rrgiNum(r.rank)?`${rrgiRank(r.rank)}${rrgiNum(r.z)?`<br><span class="muted">${r.z>0?'+':r.z<0?'−':''}${fmt(Math.abs(r.z),1)} sd</span>`:''}`:'—',rrgiPc(r.vw,2),
  r.q==null?'—':`<span class="badge rrg-b-${RRG_Q[r.q][0]}">${RRG_Q[r.q][1]}</span>`]));
 return out+'</div>';
}
if(typeof document!=='undefined'&&!document.getElementById('rrgi-css')){const st=document.createElement('style');st.id='rrgi-css';
 st.textContent=`.rrgi-ring{fill:none;opacity:.8}.rrgi-in{stroke:var(--flow-buy)}.rrgi-out{stroke:var(--flow-sell)}.rrgi-bin{fill:var(--flow-buy)}.rrgi-bout{fill:var(--flow-sell)}
.rrgi-muted{fill:var(--muted)}.rrgi-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--flow-sell);margin-right:5px;vertical-align:1px;animation:rrgip 2s infinite}@keyframes rrgip{50%{opacity:.3}}@media (prefers-reduced-motion:reduce){.rrgi-dot{animation:none}}.mk-key.rrgi-key-in{background:transparent;border:2px solid var(--flow-buy);border-radius:50%}.mk-key.rrgi-key-out{background:transparent;border:2px solid var(--flow-sell);border-radius:50%}
.badge.rrgi-t-in{background:color-mix(in srgb,var(--flow-buy) 16%,transparent);color:var(--flow-buy)}.badge.rrgi-t-out{background:color-mix(in srgb,var(--flow-sell) 16%,transparent);color:var(--flow-sell)}.badge.rrgi-t-vol{background:color-mix(in srgb,var(--muted) 16%,transparent);color:var(--ink)}`;
 document.head.appendChild(st)}
if(typeof module!=='undefined'&&module.exports)module.exports={rrgiDecode,rrgiSeries,rrgiCalc,rrgiRows,rrgiFilter,rrgiSort,rrgiTags,rrgiHm,rrgiDay,rrgiQuad,rrgIntradayView,RRGI,RRGI_PAR,RRGI_SORT,RRGI_FILTER};
