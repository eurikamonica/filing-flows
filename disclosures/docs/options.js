/* 4.5 Options: CBOE delayed option chains summarised daily (app/options.py) — the cross-section of one underlying
   (IV smile, open interest and dealer gamma by strike, term structure) and a table of every underlying covered.
   Data: data/market/options.json and data/market/options/<TICKER>.json. Uses the helpers of market.js / rotation.js. */
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

function optionsView(){
 let out=head('Options','The cross-section of option chains: where open interest and dealer gamma sit by strike, the implied-volatility smile and term structure. CBOE delayed quotes, summarised daily after the close.','CBOE · DAILY');
 const g=marketGate('options','Option chains');if(!g.data)return out+g.html;
 const d=g.data,rows=d.rows||[];
 if(!rows.length)return out+empty('No option chains collected yet — the collector runs each weekday after the close (Actions → Collect disclosures → module options).');
 state.oq=rows.some(r=>r.ticker===state.oq)?state.oq:'';
 out+=`<div class="toolbar">${field('oq','Underlying',[['','Every underlying (table)'],...rows.map(r=>[r.ticker,`${r.ticker} · ${px(r.spot)} · IV30 ${iv30(r.iv30)}`])],state.oq,true)}</div>`;
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
 out+=table(['Underlying','Spot','IV30','IV30 change','IV30 percentile','Put/call OI','25Δ skew','Net GEX (per 1%)','Call wall','Put wall','Gamma flip','Max pain'],rows.map(r=>[
  `<button class="text-button" data-opt="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button>`,px(r.spot),iv30(r.iv30),r.iv30_chg==null?'—':(r.iv30_chg>0?'+':'')+fmt(r.iv30_chg,1),r.iv30_pct==null?'—':fmt(r.iv30_pct*100,0)+'%',
  r.pc_oi==null?'—':fmt(r.pc_oi,2),r.skew25==null?'—':ivp(r.skew25),`<span class="${r.net_gex>=0?'positive':'negative'}">${smoney(r.net_gex)}</span>`,px(r.call_wall),px(r.put_wall),px(r.gamma_flip),
  r.max_pain==null?'—':`${px(r.max_pain)} <span class="muted">${esc(r.max_pain_exp||'')}</span>`]));
 return out;
}

function optionsOne(r,d){
 const m=optDetail(r.ticker);
 let out=`<div class="metrics">${kpi('Spot',px(r.spot),`as of ${esc(d.generated_at||'')}`)}${kpi('IV30',iv30(r.iv30),r.iv30_chg==null?'':`${r.iv30_chg>0?'+':''}${fmt(r.iv30_chg,1)} pts on the day${r.iv30_pct!=null?' · '+fmt(r.iv30_pct*100,0)+'th percentile':''}`)}${kpi('Put / call open interest',r.pc_oi==null?'—':fmt(r.pc_oi,2),`${fmt(r.oi_put)} puts · ${fmt(r.oi_call)} calls`)}${kpi('Net dealer gamma',smoney(r.net_gex),'Per 1% move, model: calls +, puts −')}</div>`;
 out+=`<div class="metrics">${kpi('Call wall',px(r.call_wall),'Strike with the most call open interest')}${kpi('Put wall',px(r.put_wall),'Strike with the most put open interest')}${kpi('Gamma flip (approx.)',px(r.gamma_flip),'Where cumulative GEX by strike changes sign')}${kpi('Max pain',px(r.max_pain),r.max_pain_exp?'Expiry '+r.max_pain_exp:'')}</div>`;
 if(m.err)return out+empty('Chain details could not load ('+m.err+').');
 if(!m.data)return out+empty('Loading the chain…');
 const c=m.data;
 out+=`<div class="charts even"><div class="panel"><h3>Implied volatility smile</h3><p class="sub">Out-of-the-money IV by strike (puts below spot, calls above) · up to three expiries</p>${smileSVG(c)}</div>`;
 out+=`<div class="panel"><h3>Term structure</h3><p class="sub">At-the-money IV by expiry</p>${termSVG(c)}</div></div>`;
 out+=`<div class="charts even"><div class="panel"><h3>Open interest by strike</h3><p class="sub">Calls above the line, puts below · strikes within 30% of spot · all expiries</p>${strikeSVG(c.oi.map(([k,cl,pu])=>[k,cl,-pu]),c,'contracts',v=>(v>=0?'calls ':'puts ')+fmt(Math.abs(v)))}</div>`;
 out+=`<div class="panel"><h3>Dealer gamma exposure by strike</h3><p class="sub">GEX per 1% move (model: dealers long calls, short puts) · above zero dampens moves, below amplifies</p>${strikeSVG(c.gex.map(([k,v])=>[k,v]),c,'usd',v=>smoney(v))}</div></div>`;
 if((r.history||[]).length>=2){const h=r.history;out+=`<div class="panel"><h3>History</h3><p class="sub">IV30 and put/call open interest, one point per collection day</p><div class="rot-multiples">${miniLine(h.map(x=>[x[0],x[2]]),'IV30',v=>fmt(v,1)+'%')}${miniLine(h.map(x=>[x[0],x[3]]),'Put / call OI',v=>fmt(v,2))}</div></div>`}
 out+=`<div class="explain">${esc(d.note||'')} Strikes with no open interest and stale quotes are left out of the smile.</div>`;
 return out;
}

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
function bindOptions(){
 bind('oq','oq');
 document.querySelectorAll('[data-opt]').forEach(b=>b.onclick=()=>{state.oq=b.dataset.opt;state.page=0;render();scrollTo({top:0,behavior:'smooth'})});
}
