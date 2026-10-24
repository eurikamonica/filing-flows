/* 4.5 Options, two sources:
   · Option chains — CBOE delayed quotes summarised daily (app/options.py): the cross-section of one underlying (IV smile,
     open interest and dealer gamma by strike, term structure) and a table of every underlying covered.
     Data: data/market/options.json and data/market/options/<TICKER>.json.
   · Disclosed in 13F — the long put and call positions managers report each quarter (app/market.py options13f):
     per underlying, by manager, and the largest changes. Data: data/market/options13f.json.
   Uses the helpers of market.js / rotation.js. */
const optStore={};
function optDetail(t){
 const m=optStore[t]||(optStore[t]={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='cannot load';return m}
 m.loading=fetch('data/market/options/'+encodeURIComponent(t)+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const ivp=v=>v==null?'—':fmt(v*100,1)+'%';
const iv30=v=>v==null?'—':fmt(v,1)+'%';                 // CBOE's iv30 is already in percent
const px=v=>v==null?'—':'$'+fmt(v,v>=100?0:2);
const emove=r=>r&&r.iv30!=null&&r.spot?r.spot*r.iv30/100*Math.sqrt(30/365):null;   // one standard deviation over 30 days, from IV30

function optionsView(){
 state.omode=state.omode==='13f'?'13f':'chains';
 let out=head('Options',state.omode==='13f'?'The put and call positions investment managers disclose in their quarterly 13F reports: who holds them, on which underlyings, and what changed since the quarter before.':'The cross-section of option chains: where open interest and dealer gamma sit by strike, the implied-volatility smile and term structure. CBOE delayed quotes, summarised daily after the close.',state.omode==='13f'?'SEC 13F · QUARTERLY':'CBOE · DAILY');
 const src=field('omode','Source',[['chains','Option chains (CBOE, daily)'],['13f','Disclosed in 13F (managers, quarterly)']],state.omode);
 if(state.omode==='13f')return out+options13fView(src);
 const g=marketGate('options','Option chains');if(!g.data)return out+`<div class="toolbar">${src}</div>`+g.html;
 const d=g.data,rows=d.rows||[];
 if(!rows.length)return out+`<div class="toolbar">${src}</div>`+empty('No option chains collected yet — the collector runs each weekday after the close (Actions → Collect disclosures → module options).');
 state.oq=rows.some(r=>r.ticker===state.oq)?state.oq:'';
 out+=`<div class="toolbar">${src}${field('oq','Underlying',[['','Every underlying (table)'],...rows.map(r=>[r.ticker,`${r.ticker} · ${px(r.spot)} · IV30 ${iv30(r.iv30)}`])],state.oq,true)}</div>`;
 if(!state.oq)return out+optionsTable(d,rows);
 return out+optionsOne(rows.find(r=>r.ticker===state.oq),d);
}

function optionsTable(d,rows){
 const hi=rows.filter(r=>r.iv30!=null).sort((a,b)=>b.iv30-a.iv30),put=rows.filter(r=>r.pc_oi!=null).sort((a,b)=>b.pc_oi-a.pc_oi);
 let out=`<div class="metrics">${kpi('Underlyings',fmt(rows.length),'Indexes, ETFs and the most-held stocks')}${kpi('Highest IV30',hi[0]?`${hi[0].ticker} ${iv30(hi[0].iv30)}`:'—','30-day implied volatility')}${kpi('Most put-heavy',put[0]?`${put[0].ticker} ${fmt(put[0].pc_oi,2)}`:'—','Put / call open interest')}${kpi('Negative net GEX',fmt(rows.filter(r=>r.net_gex<0).length),'Dealers short gamma (model): moves can extend')}</div>`;
 out+=`<div class="charts even"><div class="panel"><h3>Highest implied volatility</h3><p class="sub">IV30, the 12 highest</p>${divergingChart(hi.slice(0,12).map(r=>({label:r.ticker,value:r.iv30,tip:[[r.ticker,'IV30 '+iv30(r.iv30)],[r.iv30_chg==null?'—':(r.iv30_chg>0?'+':'')+fmt(r.iv30_chg,1)+' pts','change on the day'],[r.iv30_pct==null?'—':fmt(r.iv30_pct*100,0)+'th','percentile of its own history']]})),{unit:'count',label:'IV30 by underlying',format:v=>fmt(v,1)+'%',neutral:true})}</div>`;
 out+=`<div class="panel"><h3>Put / call open interest</h3><p class="sub">Above 1: more puts open than calls · the 12 most put-heavy</p>${divergingChart(put.slice(0,12).map(r=>({label:r.ticker,value:r.pc_oi,tip:[[r.ticker,''],[fmt(r.pc_oi,2),'put / call open interest'],[fmt(r.oi_put),'puts open'],[fmt(r.oi_call),'calls open']]})),{unit:'count',label:'Put / call ratio',format:v=>fmt(v,2),neutral:true})}</div></div>`;
 exported=rows.map(({history,...r})=>r);
 out+=`<div class="explain">${esc(d.note||'')}</div><div class="section-head"><h3>Every underlying</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out=out.replace('<div class="explain">',`<div class="panel"><h3>Implied volatility against put/call open interest</h3><p class="sub">→ IV30 · ↑ puts open per call · each dot one underlying; the top-right are names where options price big moves and puts dominate</p>${ivMap(rows)}</div><div class="explain">`);
 out+=table(['Underlying','Spot','IV30','Expected move, 30 days','IV30 change','IV30 percentile','Put/call OI','25Δ skew','Net GEX (per 1%)','Call wall','Put wall','Gamma flip','Max pain'],rows.map(r=>[
  `<button class="text-button" data-opt="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button>`,px(r.spot),iv30(r.iv30),emove(r)==null?'—':`±${px(emove(r))} <span class="muted">(±${fmt(r.iv30*Math.sqrt(30/365),1)}%)</span>`,r.iv30_chg==null?'—':(r.iv30_chg>0?'+':'')+fmt(r.iv30_chg,1),r.iv30_pct==null?'—':fmt(r.iv30_pct*100,0)+'%',
  r.pc_oi==null?'—':fmt(r.pc_oi,2),r.skew25==null?'—':ivp(r.skew25),`<span class="${r.net_gex>=0?'positive':'negative'}">${smoney(r.net_gex)}</span>`,px(r.call_wall),px(r.put_wall),px(r.gamma_flip),
  r.max_pain==null?'—':`${px(r.max_pain)} <span class="muted">${esc(r.max_pain_exp||'')}</span>`]));
 return out;
}

function optionsOne(r,d){
 const m=optDetail(r.ticker);
 let out=`<div class="metrics">${kpi('Spot',px(r.spot),`as of ${esc(d.generated_at||'')}`)}${kpi('IV30',iv30(r.iv30),r.iv30_chg==null?'':`${r.iv30_chg>0?'+':''}${fmt(r.iv30_chg,1)} pts on the day${r.iv30_pct!=null?' · '+fmt(r.iv30_pct*100,0)+'th percentile':''}`)}${kpi('Put / call open interest',r.pc_oi==null?'—':fmt(r.pc_oi,2),`${fmt(r.oi_put)} puts · ${fmt(r.oi_call)} calls`)}${kpi('Net dealer gamma',smoney(r.net_gex),'Per 1% move, model: calls +, puts −')}</div>`;
 out+=`<div class="metrics">${kpi('Expected move, 30 days',emove(r)==null?'—':'±'+px(emove(r)),r.iv30!=null?`one standard deviation from IV30: ±${fmt(r.iv30*Math.sqrt(30/365),1)}% (about two months in three stay inside)`:'')}</div>`;
 out+=`<div class="metrics">${kpi('Call wall',px(r.call_wall),'Strike with the most call open interest')}${kpi('Put wall',px(r.put_wall),'Strike with the most put open interest')}${kpi('Gamma flip (approx.)',px(r.gamma_flip),'Where cumulative GEX by strike changes sign')}${kpi('Max pain',px(r.max_pain),r.max_pain_exp?'Expiry '+r.max_pain_exp:'')}</div>`;
 if(m.err)return out+empty('Chain details could not load ('+m.err+').');
 if(!m.data)return out+empty('Loading the chain…');
 const c=m.data;
 out+=`<div class="charts even"><div class="panel"><h3>Implied volatility smile</h3><p class="sub">Out-of-the-money IV by strike (puts below spot, calls above) · up to three expiries</p>${smileSVG(c)}</div>`;
 out+=`<div class="panel"><h3>Term structure</h3><p class="sub">At-the-money IV by expiry</p>${termSVG(c)}</div></div>`;
 out+=optPathsPanel(c,r.ticker);
 out+=`<div class="charts even"><div class="panel"><h3>Open interest by strike</h3><p class="sub">Calls above the line, puts below · strikes within 30% of spot · all expiries</p>${strikeSVG(c.oi.map(([k,cl,pu])=>[k,cl,-pu]),c,'contracts',v=>(v>=0?'calls ':'puts ')+fmt(Math.abs(v)))}</div>`;
 out+=`<div class="panel"><h3>Dealer gamma exposure by strike</h3><p class="sub">GEX per 1% move (model: dealers long calls, short puts) · above zero dampens moves, below amplifies</p>${strikeSVG(c.gex.map(([k,v])=>[k,v]),c,'usd',v=>smoney(v))}</div></div>`;
 const o13=marketData('options13f').data,h13=o13&&(o13.rows||[]).find(x=>x.ticker===r.ticker);
 if(h13)out+=`<div class="panel"><h3>Disclosed in 13F — ${esc(h13.ticker)} options held by managers</h3><p class="sub">Quarter ended ${esc(o13.quarter)}: ${money(h13.call_usd)} of calls (${fmt(h13.call_mgrs)} managers) and ${money(h13.put_usd)} of puts (${fmt(h13.put_mgrs)}), valued at the underlying shares · change since the quarter before: calls ${smoney(h13.d_call_usd)}, puts ${smoney(h13.d_put_usd)}</p>${o13Bars(h13.hist)}<p class="sub"><button class="text-button" data-o13="${esc(h13.cusip)}">Every holder and the history →</button></p></div>`;
 if((r.history||[]).length>=2){const h=r.history;out+=`<div class="panel"><h3>History</h3><p class="sub">IV30 and put/call open interest, one point per collection day</p><div class="rot-multiples">${miniLine(h.map(x=>[x[0],x[2]]),'IV30',v=>fmt(v,1)+'%')}${miniLine(h.map(x=>[x[0],x[3]]),'Put / call OI',v=>fmt(v,2))}</div></div>`}
 out+=`<div class="explain">${esc(d.note||'')} Strikes with no open interest and stale quotes are left out of the smile.</div>`;
 return out;
}

function ivMap(rows){
 const pts=rows.filter(r=>r.iv30!=null&&r.pc_oi!=null);if(pts.length<5)return empty('Not enough underlyings yet');
 const W=1000,H=400,L=48,R=16,T=14,B=36,xs=pts.map(r=>r.iv30).sort((a,b)=>a-b),ys=pts.map(r=>Math.log2(Math.max(.05,r.pc_oi))).sort((a,b)=>a-b);
 const x0=0,x1=Math.max(40,quantile(xs,.98)*1.1),y0=Math.max(-3,Math.min(-1.5,quantile(ys,.02)-.3)),y1=Math.min(3,Math.max(1.5,quantile(ys,.98)+.3));
 const sx=v=>L+(Math.min(v,x1)-x0)/(x1-x0)*(W-L-R),sy=v=>T+(y1-Math.max(y0,Math.min(y1,Math.log2(Math.max(.05,v)))))/(y1-y0)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="IV30 against put/call open interest; values in the table below">`;
 [.25,.5,1,2,4].filter(v=>Math.log2(v)>=y0&&Math.log2(v)<=y1).forEach(v=>{s+=`<line class="${v===1?'mk-axis':'mk-grid'}" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-6}" y="${sy(v)+4}" text-anchor="end">${fmt(v,2)}</text>`});
 niceTicks(x0,x1,6).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${fmt(v)}%</text>`});
 s+=`<text class="axis" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">IV30 →</text>`;
 const lab=new Set([...pts].sort((a,b)=>b.iv30-a.iv30).slice(0,6).map(r=>r.ticker).concat([...pts].sort((a,b)=>b.pc_oi-a.pc_oi).slice(0,4).map(r=>r.ticker)));
 pts.forEach(r=>{const x=sx(r.iv30),y=sy(r.pc_oi);s+=`<g data-tip="${tip([[r.ticker,''],[iv30(r.iv30),'IV30'],[fmt(r.pc_oi,2),'put/call open interest'],[emove(r)==null?'—':'±'+px(emove(r)),'expected move, 30 days']])}" tabindex="0" class="mk-hit" data-opt="${esc(r.ticker)}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="9" fill="transparent"/><circle cx="${x}" cy="${y}" r="4" class="mk-dot"/></g>`;
  if(lab.has(r.ticker)){const left=x>W-R-50;s+=`<text class="mk-label mk-halo" x="${left?x-7:x+7}" y="${y-6}" text-anchor="${left?'end':'start'}">${esc(r.ticker)}</text>`}});
 return s+'</svg>';
}
/* ---------- the price paths the options imply (app/options.py price_paths) ----------
   Per expiry the risk-neutral quantiles (Breeden-Litzenberger from the smile) and max pain. Between expiries the median
   and the spread per unit √time are interpolated in time; from today to the first expiry the spread grows with √time.
   Sample paths: one Brownian motion per path, mapped each day onto that day's quantile function (z = W(t)/√t), so at
   every expiry the paths have the distribution the options price. */
function optInvN(p){const a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.357751867269,-30.66479806614716,2.506628277459239],b=[-54.47609879822406,161.5858368580409,-155.6989798598866,66.80131188771972,-13.28068155288572],c=[-.007784894002430293,-.3223964580411365,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783],d=[.007784695709041462,.3224671290700398,2.445134137142996,3.754408661907416],pl=.02425;
 if(p<pl){const q=Math.sqrt(-2*Math.log(p));return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)}
 if(p>1-pl){const q=Math.sqrt(-2*Math.log(1-p));return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)}
 const q=p-.5,r=q*q;return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)}
function optFan(c){                                    // the quantile function of the price at any day up to the last expiry
 const P=(c.paths||[]).filter(x=>x.days>0&&(x.q||[]).length>=5),probs=c.path_probs||[.025,.05,.1,.25,.5,.75,.9,.95,.975];
 if(!P.length||!(c.spot>0))return null;
 const Z=probs.map(optInvN),mi=probs.indexOf(.5)>=0?probs.indexOf(.5):Math.floor(probs.length/2);
 const nodes=P.map(x=>{const L=x.q.map(Math.log),t=x.days/365,m=L[mi];return {t,days:x.days,m,D:L.map(v=>(v-m)/Math.sqrt(t)),x}});
 const at=(days,z)=>{                                  // log price at quantile z on a day
  const t=Math.max(days,1e-6)/365;let i=nodes.findIndex(n=>n.days>=days);
  let m,D;if(i<0){const n=nodes[nodes.length-1];m=n.m;D=n.D}
  else if(i===0){const n=nodes[0],w=days/n.days;m=Math.log(c.spot)+(n.m-Math.log(c.spot))*w;D=n.D}
  else{const a=nodes[i-1],b=nodes[i],w=(days-a.days)/(b.days-a.days);m=a.m+(b.m-a.m)*w;D=a.D.map((v,j)=>v+(b.D[j]-v)*w)}
  let j=1;while(j<Z.length-1&&z>Z[j])j++;const s=(D[j]-D[j-1])/(Z[j]-Z[j-1]);
  return m+(D[j-1]+s*(z-Z[j-1]))*Math.sqrt(t)};
 return {nodes,probs,Z,at,end:nodes[nodes.length-1].days}}
function optSim(F,n=40,seed=20261023){                  // seeded Brownian paths mapped through the fan
 let a=seed>>>0;const rnd=()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296};
 const gauss=()=>Math.sqrt(-2*Math.log(rnd()||1e-12))*Math.cos(2*Math.PI*rnd());
 const step=Math.max(1,Math.ceil(F.end/120)),days=[];for(let d=step;d<F.end;d+=step)days.push(d);days.push(F.end);
 const out=[];for(let k=0;k<n;k++){let W=0,prev=0;out.push(days.map(d=>{W+=Math.sqrt((d-prev)/365)*gauss();prev=d;return [d,Math.exp(F.at(d,W/Math.sqrt(d/365)))]}))}
 return out}
function optPathsSVG(c){
 const F=optFan(c);if(!F)return empty('No expiry with enough quoted strikes for the price paths');
 const W=720,H=340,L=60,R=96,T=16,B=36,days=[];for(let d=0;d<=F.end;d+=Math.max(1,F.end/160))days.push(d);if(days[days.length-1]<F.end)days.push(F.end);
 const sims=optSim(F),band=(p)=>days.map(d=>d?Math.exp(F.at(d,optInvN(p))):c.spot);
 const lo=band(F.probs[0]),hi=band(F.probs[F.probs.length-1]),mp=F.nodes.map(n=>n.x.max_pain).filter(v=>v>0);
 const ymin=Math.min(...lo,...mp,c.spot)*.98,ymax=Math.max(...hi,...mp,c.spot)*1.02;
 const sx=d=>L+d/F.end*(W-L-R),sy=v=>T+(ymax-v)/(ymax-ymin)*(H-T-B),pt=(d,v)=>sx(d).toFixed(1)+','+sy(v).toFixed(1);
 const poly=(a,b)=>days.map((d,i)=>pt(d,a[i])).join(' ')+' '+days.map((d,i)=>pt(d,b[i])).reverse().join(' ');
 const clip='opt-clip-'+(optPathsSVG.n=(optPathsSVG.n||0)+1);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Price paths the options imply, with their ranges and max pain by expiry"><defs><clipPath id="${clip}"><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}"/></clipPath></defs>`;
 niceTicks(ymin,ymax,6).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${px(v)}</text>`});
 [[.025,.975,.10],[.1,.9,.16],[.25,.75,.24]].forEach(([a,b,o])=>{if(F.probs.includes(a)&&F.probs.includes(b))s+=`<polygon points="${poly(band(a),band(b))}" style="fill:var(--rot-1);opacity:${o}"/>`});
 s+=`<g clip-path="url(#${clip})">`;sims.forEach(p=>{s+=`<polyline points="${pt(0,c.spot)} ${p.map(([d,v])=>pt(d,v)).join(' ')}" style="fill:none;stroke:var(--muted);stroke-width:.7;opacity:.4"/>`});s+='</g>';
 s+=`<polyline class="rot-line" style="stroke:var(--rot-1);stroke-dasharray:6 4" points="${days.map((d,i)=>pt(d,band(.5)[i])).join(' ')}"/>`;
 s+=`<line class="mk-axis" x1="${L}" x2="${W-R}" y1="${sy(c.spot)}" y2="${sy(c.spot)}" style="stroke-dasharray:2 3"/><text class="axis mk-halo" x="${W-R+4}" y="${sy(c.spot)+4}">spot ${px(c.spot)}</text>`;
 const pain=F.nodes.filter(n=>n.x.max_pain>0);let lastX=-1e9;
 if(pain.length>1)s+=`<polyline points="${pain.map(n=>pt(n.days,n.x.max_pain)).join(' ')}" style="fill:none;stroke:var(--mk-cost);stroke-width:1.4;stroke-dasharray:3 3"/>`;
 F.nodes.forEach((n,i)=>{const x=sx(n.days),q=n.x.q,k=(p)=>q[F.probs.indexOf(p)];
  s+=`<line class="mk-grid" x1="${x}" x2="${x}" y1="${T}" y2="${H-B}" style="opacity:.6"/>`;
  const last=i===F.nodes.length-1;if(last?x-lastX>=30:x-lastX>=38&&sx(F.end)-x>=38){s+=`<text class="axis" x="${x}" y="${H-B+16}" text-anchor="middle">${esc(n.x.exp.slice(5))}</text>`;lastX=x}
  s+=`<g data-tip="${tip([[esc(n.x.exp),`${fmt(n.days)} days · ATM IV ${ivp(n.x.atm_iv)}`],[`${px(k(.025))} – ${px(k(.975))}`,'95% of the implied distribution'],[`${px(k(.1))} – ${px(k(.9))}`,'80%'],[px(k(.5)),'median'],[n.x.max_pain>0?px(n.x.max_pain):'—','max pain (this expiry)']])}" tabindex="0" class="mk-hit"><rect x="${x-9}" y="${T}" width="18" height="${H-T-B}" fill="transparent"/>`+
   (n.x.max_pain>0?`<path d="M${x},${sy(n.x.max_pain)-6}L${x+6},${sy(n.x.max_pain)}L${x},${sy(n.x.max_pain)+6}L${x-6},${sy(n.x.max_pain)}Z" style="fill:var(--mk-cost);stroke:var(--surface,#fff);stroke-width:1.2"/>`:'')+`</g>`});
 const e=F.nodes[F.nodes.length-1].x,qe=(p)=>e.q[F.probs.indexOf(p)];
 [[.975,'97.5%'],[.9,'90%'],[.5,'median'],[.1,'10%'],[.025,'2.5%']].forEach(([p,l])=>{if(F.probs.includes(p))s+=`<text class="axis mk-halo" x="${W-R+4}" y="${sy(qe(p))+4}">${l} ${px(qe(p))}</text>`});
 return s+`<text class="axis" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">Expiry (month-day) · ${fmt(F.end)} days ahead at the last</text></svg>`+
  `<div class="mk-legend"><span><i class="mk-key" style="background:var(--rot-1);opacity:.5"></i>50 / 80 / 95% of the implied distribution</span><span><i class="mk-key" style="background:var(--muted)"></i>40 sample paths</span><span><i class="mk-key" style="background:var(--mk-cost)"></i>max pain by expiry (◆)</span></div>`}
function optPathsTable(c){
 const P=(c.paths||[]),pr=c.path_probs||[],k=(x,p)=>x.q[pr.indexOf(p)],rel=v=>v>0&&c.spot?` <span class="muted">${(v>=c.spot?'+':'−')+fmt(Math.abs(v/c.spot-1)*100,1)}%</span>`:'';
 return `<div class="tablebox"><table><thead><tr><th>Expiry</th><th class="num">Days</th><th class="num">ATM IV</th><th class="num">95% range</th><th class="num">80% range</th><th class="num">Median</th><th class="num">Max pain</th><th class="num">Open interest</th></tr></thead><tbody>${P.map(x=>`<tr><td>${esc(x.exp)}${x.method==='atm'?' <span class="muted">(ATM IV only)</span>':''}</td><td class="num">${fmt(x.days)}</td><td class="num">${ivp(x.atm_iv)}</td><td class="num">${px(k(x,.025))} – ${px(k(x,.975))}</td><td class="num">${px(k(x,.1))} – ${px(k(x,.9))}</td><td class="num">${px(k(x,.5))}${rel(k(x,.5))}</td><td class="num">${x.max_pain>0?px(x.max_pain)+rel(x.max_pain):'—'}</td><td class="num">${fmt(x.oi)}</td></tr>`).join('')}</tbody></table></div>`}
function optPathsPanel(c,name){
 if(!c||!(c.paths||[]).length)return '';
 return `<div class="panel"><h3>Price paths the options imply — ${esc(name||c.ticker||'')}</h3><p class="sub">From today's option chain (CBOE, delayed): at each expiry the distribution of the price the option prices imply (Breeden-Litzenberger on the IV smile, the forward from put-call parity), the 50, 80 and 95% ranges between expiries, 40 sample paths drawn to match those distributions, and the max pain of every expiry — the price at which the open contracts would pay their holders least. Risk-neutral: it includes what the market pays for protection (a fatter downside) and is not a forecast of direction; max pain is a description of open interest, not a target.</p>${optPathsSVG(c)}${optPathsTable(c)}</div>`}
function smileSVG(c){
 const sm=(c.smiles||[]).slice(0,3);if(!sm.length)return empty('No smile with enough quoted strikes');
 const W=720,H=320,L=52,R=110,T=16,B=36,all=sm.flatMap(s=>s.pts);
 const kx=[Math.min(...all.map(p=>p[0])),Math.max(...all.map(p=>p[0]))],iy=[Math.min(...all.map(p=>p[1])),Math.max(...all.map(p=>p[1]))],pad=(iy[1]-iy[0])*.1||.02;
 const sx=k=>L+(k-kx[0])/((kx[1]-kx[0])||1)*(W-L-R),sy=v=>T+(iy[1]+pad-v)/((iy[1]-iy[0])+2*pad)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Implied volatility smile">`;
 niceTicks(iy[0]-pad,iy[1]+pad,5).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${ivp(v)}</text>`});
 niceTicks(kx[0],kx[1],6).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${px(v)}</text>`});
 if(c.spot>=kx[0]&&c.spot<=kx[1])s+=`<line class="mk-axis" x1="${sx(c.spot)}" x2="${sx(c.spot)}" y1="${T}" y2="${H-B}"/><text class="axis" x="${sx(c.spot)+4}" y="${T+10}">spot ${px(c.spot)}</text>`;
 sm.forEach((m,i)=>{const col=ROT_SERIES[i];s+=`<polyline class="rot-line" style="stroke:${col}" points="${m.pts.map(p=>sx(p[0]).toFixed(1)+','+sy(p[1]).toFixed(1)).join(' ')}"/>`;
  m.pts.forEach(p=>{s+=`<g data-tip="${tip([[ivp(p[1]),'implied volatility'],[px(p[0]),`strike · ${m.exp} (${m.days} days)`]])}" tabindex="0" class="mk-hit"><circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="8" fill="transparent"/><circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="2.5" style="fill:${col}"/></g>`});
  const e=m.pts[m.pts.length-1];s+=`<text class="mk-label mk-halo" x="${sx(e[0])+8}" y="${sy(e[1])+4+i*2}">${esc(m.exp.slice(5))} · ${m.days}d</text>`});
 return s+'</svg>'+`<div class="mk-legend">${sm.map((m,i)=>`<span><i class="mk-key" style="background:${ROT_SERIES[i]}"></i>${esc(m.exp)} (${m.days} days)</span>`).join('')}</div>`;
}
function termSVG(c){
 const t=(c.term||[]).map(([e,v])=>[Math.max(0,(new Date(e)-new Date())/864e5),v,e]).filter(x=>x[1]>0);
 if(t.length<2)return empty('Not enough expiries');
 const W=720,H=320,L=52,R=20,T=16,B=36,xm=Math.max(...t.map(x=>x[0])),lo=Math.min(...t.map(x=>x[1])),hi=Math.max(...t.map(x=>x[1])),pad=(hi-lo)*.15||.02;
 const sx=v=>L+v/xm*(W-L-R),sy=v=>T+(hi+pad-v)/((hi-lo)+2*pad)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="IV term structure">`;
 niceTicks(lo-pad,hi+pad,5).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${ivp(v)}</text>`});
 niceTicks(0,xm,6).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${fmt(v)}d</text>`});
 s+=`<polyline class="rot-line" style="stroke:var(--rot-1)" points="${t.map(x=>sx(x[0]).toFixed(1)+','+sy(x[1]).toFixed(1)).join(' ')}"/>`;
 t.forEach(x=>{s+=`<g data-tip="${tip([[ivp(x[1]),'at-the-money IV'],[x[2],fmt(x[0])+' days']])}" tabindex="0" class="mk-hit"><circle cx="${sx(x[0])}" cy="${sy(x[1])}" r="9" fill="transparent"/><circle cx="${sx(x[0])}" cy="${sy(x[1])}" r="3" style="fill:var(--rot-1)"/></g>`});
 return s+`<text class="axis" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">Days to expiry</text></svg>`;
}
function strikeSVG(rows,c,unit,f){                    // signed columns by strike with spot, walls and flip marked
 rows=rows.filter(r=>r[1]||r[2]);if(!rows.length)return empty('No open interest in range');
 const W=720,H=300,L=96,R=16,T=18,B=36,ks=rows.map(r=>r[0]),k0=Math.min(...ks),k1=Math.max(...ks);
 const vals=rows.flatMap(r=>r.slice(1).filter(v=>v!=null)),m=Math.max(1,...vals.map(Math.abs));
 const sx=k=>L+(k-k0)/((k1-k0)||1)*(W-L-R),mid=T+(H-T-B)/2,sh=v=>Math.abs(v)/m*((H-T-B)/2-4);
 const gap=Math.min(...ks.slice(1).map((k,i)=>k-ks[i]).filter(x=>x>0),k1-k0||1),bw=Math.max(1.5,Math.min(14,gap/((k1-k0)||1)*(W-L-R)-2));
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="By strike; values in the tooltips">`;
 s+=`<line class="mk-axis" x1="${L}" x2="${W-R}" y1="${mid}" y2="${mid}"/><text class="axis" x="${L-8}" y="${T+8}" text-anchor="end">${esc(f(m))}</text><text class="axis" x="${L-8}" y="${H-B}" text-anchor="end">${esc(f(-m))}</text>`;
 niceTicks(k0,k1,7).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${px(v)}</text>`});
 let slot=0;
 const mark=(k,label,cls)=>{if(k==null||k<k0||k>k1)return '';const x=sx(k),right=x+4+label.length*6<W-R,y=H-B-6-(slot++%3)*12;
  return `<line class="${cls}" x1="${x}" x2="${x}" y1="${T}" y2="${H-B}"/><text class="axis mk-halo" x="${right?x+4:x-4}" y="${y}" text-anchor="${right?'start':'end'}">${esc(label)} ${px(k)}</text>`};
 s+=mark(c.spot,'spot','mk-axis')+mark(unit==='usd'?c.gamma_flip:null,'flip','opt-mark');
 rows.forEach(r=>{for(const v of r.slice(1)){if(!v)continue;const h=sh(v);s+=`<g data-tip="${tip([[f(v),unit==='usd'?(v>=0?'positive gamma':'negative gamma'):(v>=0?'calls open':'puts open')],[px(r[0]),'strike']])}" tabindex="0" class="mk-hit"><rect x="${sx(r[0])-bw/2-2}" y="${T}" width="${bw+4}" height="${H-T-B}" fill="transparent"/><rect x="${sx(r[0])-bw/2}" y="${v>=0?mid-h:mid}" width="${bw}" height="${Math.max(1,h)}" rx="1.5" class="${v>=0?'mk-buy':'mk-sell'}"/></g>`}});
 if(unit!=='usd'){s+=mark(c.call_wall,'call wall','opt-mark');s+=mark(c.put_wall,'put wall','opt-mark')}
 return s+'</svg>';
}
function miniLine(pts,label,f){
 pts=pts.filter(p=>p[1]!=null);if(pts.length<2)return '';
 const W=300,H=120,L=40,R=8,T=10,B=22,lo=Math.min(...pts.map(p=>p[1])),hi=Math.max(...pts.map(p=>p[1])),pad=(hi-lo)*.15||1,x=i=>L+i/(pts.length-1)*(W-L-R),y=v=>T+(hi+pad-v)/((hi-lo)+2*pad)*(H-T-B);
 return `<div class="rot-mini"><h4>${esc(label)}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot"><text class="axis" x="${L-6}" y="${y(hi)+4}" text-anchor="end">${esc(f(hi))}</text><text class="axis" x="${L-6}" y="${y(lo)+4}" text-anchor="end">${esc(f(lo))}</text><polyline class="rot-line" style="stroke:var(--rot-1)" points="${pts.map((p,i)=>x(i).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}"/><text class="axis" x="${L}" y="${H-6}">${esc(pts[0][0])}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(pts[pts.length-1][0])}</text></svg></div>`;
}
/* ---------- disclosed in 13F ---------- */
const O13_LISTS=[['under','By underlying'],['moves','Largest position changes'],['books','Largest option books (managers)']];
function o13Bars(hist){                               // calls and puts disclosed per quarter, side by side
 const h=(hist||[]).filter(x=>x[1]||x[2]);if(!h.length)return empty('No quarter on file');
 const W=900,H=220,L=70,R=16,T=14,B=34,max=Math.max(1,...h.flatMap(x=>[x[1],x[2]])),gw=(W-L-R)/h.length,bw=Math.min(28,gw/2-6);
 const y=v=>T+(1-v/max)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Disclosed calls and puts per quarter; values in the tooltips">`;
 niceTicks(0,max,4).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-8}" y="${y(v)+4}" text-anchor="end">${esc(money(v))}</text>`});
 h.forEach((x,i)=>{const cx=L+gw*i+gw/2;
  [[x[1],0,'calls',x[3]],[x[2],1,'puts',x[4]]].forEach(([v,k,word,n])=>{const X=cx+(k?2:-bw-2),top=y(v);
   s+=`<g data-tip="${tip([[money(v),word+' disclosed · quarter ended '+x[0]],...(n!=null?[[fmt(n),'managers holding '+word]]:[])])}" tabindex="0" class="mk-hit"><rect x="${X-2}" y="${T}" width="${bw+4}" height="${H-T-B}" fill="transparent"/><rect x="${X}" y="${top}" width="${bw}" height="${Math.max(1,H-B-top)}" rx="2" style="fill:${ROT_SERIES[k]}"/></g>`});
  s+=`<text class="axis" x="${cx}" y="${H-B+16}" text-anchor="middle">${esc(x[0].slice(0,7))}</text>`});
 return s+`</svg><div class="mk-legend"><span><i class="mk-key" style="background:${ROT_SERIES[0]}"></i>Calls</span><span><i class="mk-key" style="background:${ROT_SERIES[1]}"></i>Puts</span><span class="muted">Valued at the underlying shares at quarter-end</span></div>`;
}
function options13fView(src){
 const g=marketGate('options13f','13F option positions');
 if(!g.data)return `<div class="toolbar">${src}</div>`+g.html;
 const d=g.data,all=d.rows||[];
 state.o13u=state.o13u==='all'?'all':'stocks';
 state.o13l=O13_LISTS.some(x=>x[0]===state.o13l)?state.o13l:'under';
 const one=state.o13?all.find(r=>r.cusip===state.o13):null;
 let out=`<div class="toolbar">${src}${one?'':field('o13l','List',O13_LISTS,state.o13l)}${one||state.o13l!=='under'?'':field('o13u','Underlyings',[['stocks','Stocks'],['all','Stocks, ETFs and funds']],state.o13u)}${one?'':`<div class="field wide"><label for="o13q">Find an underlying or manager</label><input id="o13q" value="${esc(state.o13q||'')}" placeholder="e.g. NVDA, SPY, Citadel · Enter"></div>`}</div>`;
 const t=d.totals||{},bp=t.by_period||[];
 if(one)return out+o13One(one,d);
 out+=`<div class="metrics">${kpi('Quarter',d.quarter||'—',`${fmt(d.managers)} managers disclosed options`)}${kpi('Calls disclosed',money(t.call_usd),'Long calls, valued at the underlying shares')}${kpi('Puts disclosed',money(t.put_usd),'Long puts, valued at the underlying shares')}${kpi('Put / call by value',t.call_usd?fmt(t.put_usd/t.call_usd,2):'—',bp.length>1&&bp[bp.length-2][1]?`${fmt(bp[bp.length-2][2]/bp[bp.length-2][1],2)} the quarter before`:'')}</div>`;
 const rows=all.filter(r=>state.o13u==='all'||!r.fund);
 const dc=rows.filter(r=>r.d_call_usd).sort((a,b)=>Math.abs(b.d_call_usd)-Math.abs(a.d_call_usd)).slice(0,10),dp=rows.filter(r=>r.d_put_usd).sort((a,b)=>Math.abs(b.d_put_usd)-Math.abs(a.d_put_usd)).slice(0,10);
 const it=(r,k,word)=>({label:r.ticker||shortName(r.issuer),value:r[k],tip:[[r.ticker||r.issuer,r.name||r.issuer||''],[smoney(r[k]),'change in '+word+' disclosed'],[money(r[word==='calls'?'call_usd':'put_usd']),word+' now · '+fmt(r[word==='calls'?'call_mgrs':'put_mgrs'])+' managers']]});
 out+=`<div class="panel"><h3>Calls and puts disclosed, by quarter</h3><p class="sub">Every manager on file; coverage grows as more managers are processed, so compare the shape more than the level</p>${o13Bars(bp.map(x=>[x[0],x[1],x[2],null,null]))}</div>`;
 out+=`<div class="charts even"><div class="panel"><h3>Biggest changes in calls</h3><p class="sub">Change in disclosed calls since each holder's previous quarter</p>${divergingChart(dc.map(r=>it(r,'d_call_usd','calls')),{label:'Change in disclosed calls'})}</div>`;
 out+=`<div class="panel"><h3>Biggest changes in puts</h3><p class="sub">Change in disclosed puts since each holder's previous quarter</p>${divergingChart(dp.map(r=>it(r,'d_put_usd','puts')),{label:'Change in disclosed puts'})}</div></div>`;
 out+=`<div class="explain">${esc(d.note||'')}</div>`;
 const q=String(state.o13q||'').trim().toUpperCase();
 const match=(...xs)=>!q||xs.some(x=>String(x||'').toUpperCase().includes(q));
 if(state.o13l==='moves'){
  const ms=(d.moves||[]).filter(m=>match(m.ticker,m.issuer,m.manager));
  exported=ms;
  out+=`<div class="section-head"><h3>Largest position changes · ${fmt(ms.length)}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  return out+table(['Manager','Underlying','Option','Change','Change (est. $)','Position now'],ms.map(m=>[esc(m.manager),`${tkLink(m.ticker)} <span class="muted">${esc(m.issuer||'')}</span>`,m.pc==='PUT'?'Put':'Call',{new:'Opened',added:'Added',cut:'Cut',closed:'Closed'}[m.kind]||esc(m.kind),`<span class="${m.chg_usd>=0?'positive':'negative'}">${smoney(m.chg_usd)}</span>`,money(m.usd)]));
 }
 if(state.o13l==='books'){
  const bs=(d.books||[]).filter(b=>match(b.manager,...b.top.map(x=>x.ticker)));
  exported=bs.map(b=>({...b,top:b.top.map(x=>`${x.ticker||x.issuer} ${x.pc} ${x.usd}`).join('; ')}));
  out+=`<div class="section-head"><h3>Largest option books · ${fmt(bs.length)} managers</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  return out+table(['Manager','Calls','Puts','Positions','Largest'],bs.map(b=>[esc(b.manager),money(b.call_usd),money(b.put_usd),fmt(b.positions),b.top.slice(0,3).map(x=>`${esc(x.ticker||shortName(x.issuer))} ${x.pc==='PUT'?'puts':'calls'} ${money(x.usd)}`).join(' · ')]));
 }
 const list=rows.filter(r=>match(r.ticker,r.issuer,r.name,...(r.top||[]).map(x=>x.manager)));
 exported=list.map(({top,hist,...r})=>({...r,largest:(top||[]).map(x=>`${x.manager} ${x.pc} ${x.usd}`).join('; ')}));
 out+=`<div class="section-head"><h3>By underlying · ${fmt(list.length)}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Underlying','Calls (managers)','Puts (managers)','Put / call','Calls change','Puts change','New holders (calls / puts)','Largest holder'],list.map(r=>[
  `<button class="text-button" data-o13="${esc(r.cusip)}"><b>${esc(r.ticker||'—')}</b></button> <span class="muted">${esc(r.name||r.issuer||'')}</span>`,`${money(r.call_usd)} <span class="muted">(${fmt(r.call_mgrs)})</span>`,`${money(r.put_usd)} <span class="muted">(${fmt(r.put_mgrs)})</span>`,
  r.pc_usd==null?'—':fmt(r.pc_usd,2),`<span class="${r.d_call_usd>=0?'positive':'negative'}">${smoney(r.d_call_usd)}</span>`,`<span class="${r.d_put_usd>=0?'positive':'negative'}">${smoney(r.d_put_usd)}</span>`,`${fmt(r.new_call)} / ${fmt(r.new_put)}`,
  r.top&&r.top[0]?`${esc(shortName(r.top[0].manager))} <span class="muted">${r.top[0].pc==='PUT'?'puts':'calls'} ${money(r.top[0].usd)}</span>`:'—']));
}
function o13One(r,d){
 let out=`<p><button class="text-button" data-o13="">← Every underlying</button></p>`;
 out+=`<div class="metrics">${kpi('Underlying',r.ticker||'—',`${r.name||r.issuer||''} · CUSIP ${r.cusip} · quarter ended ${d.quarter}`)}${kpi('Calls disclosed',money(r.call_usd),`${fmt(r.call_mgrs)} managers · ${smoney(r.d_call_usd)} vs the quarter before`)}${kpi('Puts disclosed',money(r.put_usd),`${fmt(r.put_mgrs)} managers · ${smoney(r.d_put_usd)} vs the quarter before`)}${kpi('Put / call by value',r.pc_usd==null?'—':fmt(r.pc_usd,2),`New holders: ${fmt(r.new_call)} calls, ${fmt(r.new_put)} puts · closed: ${fmt(r.closed_call)} / ${fmt(r.closed_put)}`)}</div>`;
 out+=`<div class="panel"><h3>Calls and puts disclosed, by quarter</h3><p class="sub">Managers holding each in the tooltips</p>${o13Bars(r.hist)}</div>`;
 const tops=r.top||[];
 exported=tops.map(x=>({underlying:r.ticker||r.issuer,...x}));
 out+=`<div class="section-head"><h3>Largest holders</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Manager','Option','Position (underlying value)','Change in contracts’ shares'],tops.map(x=>[esc(x.manager),x.pc==='PUT'?'Put':'Call',money(x.usd),x.chg_sh==null?'— (no prior quarter on file)':`<span class="${x.chg_sh>=0?'positive':'negative'}">${x.chg_sh>0?'+':''}${fmt(x.chg_sh)}</span>`]));
 if(r.ticker&&((marketStore.options||{}).data?.rows||[]).some(x=>x.ticker===r.ticker))out+=`<p><button class="text-button" data-optchain="${esc(r.ticker)}">${esc(r.ticker)} option chain: smile, open interest and gamma by strike →</button></p>`;
 return out+`<div class="explain">${esc(d.note||'')}</div>`;
}
function bindOptions(){
 bind('oq','oq');bind('omode','omode');bind('o13l','o13l');bind('o13u','o13u');
 if($('o13q')){$('o13q').onchange=e=>{state.o13q=e.target.value;state.page=0;render()};$('o13q').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('[data-o13]').forEach(b=>b.onclick=()=>{state.omode='13f';state.o13=b.dataset.o13;state.page=0;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('[data-optchain]').forEach(b=>b.onclick=()=>{state.omode='chains';state.oq=b.dataset.optchain;state.o13='';state.page=0;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('[data-opt]').forEach(b=>b.onclick=()=>{state.oq=b.dataset.opt;state.page=0;render();scrollTo({top:0,behavior:'smooth'})});
}
