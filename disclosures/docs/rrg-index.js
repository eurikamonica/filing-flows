/* 4.6c The four index ETFs around their own centre (app/index_rrg.py → data/market/history/index-rrg.json, rebuilt with the
   RRG forecasts on the branch rotation-history; its frozen weekly forecasts: index-ledger.json).
   Lines → “The four indices around their centre”: QQQ, SPY, IWM and DIA against the centre of the four (the
   volatility-weighted geometric mean, unless the comparison fixed in advance picked another), and the centre against
   cash. Below the chart: where each stands, its quadrant odds at 1, 4 and 13 weeks (by its own quadrant and the
   centre's quadrant against cash), the weekly chain's most common paths, the close next week that puts it in each
   quadrant (its own weight in the centre taken out), the replayed 13-week price ranges, which index leads next, the
   comparison of centres and the replay check, and the ledger of what was published. Uses rrg.js and rrg-odds.js. */
function rrgIndexData(){return marketData('history/index-rrg')}

// the chart's lines: each index with the centre as its benchmark, and the centre against cash
function rrgIndexEntities(D){
 const m=rrgIndexData();
 if(!m.data)return m.err?[{id:'ix',missing:true}]:[{id:'ix',loading:true}];
 const X=m.data,G=rrgGrid(D),c0=X.centre,L=X.levels||{},off=Math.round((Date.parse(X.start+'T00:00:00Z')-G.t0)/6048e5);
 const pad=a=>{const out=new Array(G.n).fill(null);(a||[]).forEach((v,i)=>{if(off+i>=0&&off+i<G.n)out[off+i]=v});return out};
 const cen=pad(L[c0]),cash=pad(L.cash),by=Object.fromEntries((D.series||[]).map(s=>[s.id,s])),cn=(X.centre_names||{})[c0]||'centre';
 const ents=X.tickers.map(t=>{const src=t==='SPY'?D.bench:by[t];if(!src)return {id:'ix:'+t,missing:true};
  return {id:'ix:'+t,name:t+' ▸ centre',full:((X.names||{})[t]||t)+' against the '+cn.toLowerCase(),start:G.days[0],c:rrgFull(G,src,'c'),benchC:cen}});
 if(c0!=='cash'&&cash.some(v=>v!=null))ents.push({id:'ix:centre',name:'Centre ▸ cash',full:cn+' against cash (the 3-month Treasury bill)',start:G.days[0],c:cen,benchC:cash});
 return ents;
}

const rrgIxQ=q=>q==null||q<0?'—':`<span class="badge rrg-b-${RRGO_K[q]}">${RRGO_N[q]}</span>`;
const rrgIxUsd=v=>v==null?'—':'$'+fmt(v,v>=1000?0:2);
// the quadrants a close next week can reach, as price ranges
function rrgIxRanges(nw){
 if(!nw||!nw.ranges)return '<span class="muted">—</span>';
 return nw.ranges.map(([q,lo,hi])=>{const k=RRGO_N.findIndex(n=>n.toLowerCase()===q);
  const r=lo==null&&hi==null?'any close':lo==null?'below '+rrgIxUsd(hi):hi==null?'above '+rrgIxUsd(lo):rrgIxUsd(lo)+'–'+rrgIxUsd(hi);
  return `<span class="badge rrg-b-${RRGO_K[k]}">${RRGO_N[k]}</span> ${esc(r)}`}).join('<br>');
}
// a fan of replayed prices: 80% and 50% ranges and the median, weeks 0–13
function rrgIxFan(t,r){
 const f=r.fan;if(!f)return '';
 const W=250,H=130,L=46,R=8,T=10,B=20,n=f.q50.length,lo=Math.min(r.close,...f.q10),hi=Math.max(r.close,...f.q90),pad=(hi-lo)*.06||1;
 const X=i=>L+i/n*(W-L-R),Y=v=>T+(hi+pad-v)/(hi-lo+2*pad)*(H-T-B);
 const band=(a,b)=>[`${X(0)},${Y(r.close)}`,...a.map((v,i)=>`${X(i+1).toFixed(1)},${Y(v).toFixed(1)}`),...b.slice().reverse().map((v,i)=>`${X(n-i).toFixed(1)},${Y(v).toFixed(1)}`)].join(' ');
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="${esc(t)}: replayed price ranges for the next 13 weeks">`;
 [lo,(lo+hi)/2,hi].forEach(v=>{const y=Y(v);s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"/><text class="axis" x="${L-4}" y="${(y+4).toFixed(1)}" text-anchor="end">${fmt(v,0)}</text>`});
 s+=`<polygon points="${band(f.q10,f.q90)}" fill="var(--rot-1)" opacity=".16"/><polygon points="${band(f.q25,f.q75)}" fill="var(--rot-1)" opacity=".28"/>`;
 s+=`<polyline points="${[[0,r.close],...f.q50.map((v,i)=>[i+1,v])].map(([i,v])=>`${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--rot-1)" stroke-width="2"/>`;
 s+=`<circle cx="${X(0)}" cy="${Y(r.close).toFixed(1)}" r="3.5" fill="var(--ink)"/>`;
 [0,4,13].forEach(i=>{s+=`<text class="axis" x="${X(i).toFixed(1)}" y="${H-5}" text-anchor="middle">${i?i+'w':'now'}</text>`});
 return s+`</svg>`;
}
function rrgIxSkill(a){return Array.isArray(a)?`${fmt(100*a[0],1)}% <span class="muted">[${fmt(100*a[1],1)}, ${fmt(100*a[2],1)}]</span>`:'—'}

function rrgIndexPanel(o){
 const m=rrgIndexData(),X=m.data;if(!X)return '';
 const lg=marketData('history/index-ledger').data,M=X.model||{},head=M.primary||'q',Hs=['1','4','13'],cn=X.centre_names||{};
 const lab=h=>((M.heads||{})[head]||{})[h]?.label||'insufficient_data';
 const hh=RRGO_H.some(x=>x[0]===state.rrgh)?state.rrgh:'4';
 let out=`<div class="panel"><h3>The four indices around their centre — ${esc(rrgDay(X.week))}</h3>`;
 out+=`<p class="sub">SPY overlaps the other three, so against SPY the chart only says “more tech or more value than the S&P”. Here each index is measured against the <b>${esc((cn[X.centre]||X.centre).toLowerCase())}</b> of the four${X.centre==='vol'?' — weights ∝ 1 ÷ each index\'s volatility over the last 26 weeks, so the volatile Nasdaq-100 and Russell 2000 cannot drag it alone':''}. The weighted relative moves add up to zero: one leading means others lagging. The centre itself is drawn against cash (the 3-month Treasury bill): is the market as a whole strong. Price = cash × (centre ÷ cash) × (index ÷ centre).${(()=>{const cmp=X.compare||{},best=Math.max(...Object.values(cmp).map(v=>(v.select||{}).score??-1)),near=Object.entries(cmp).filter(([,v])=>best-((v.select||{}).score??-9)<=0.002).map(([c])=>cn[c]||c);
  return near.length>1?` In the comparison fixed in advance, ${esc(near.join(', '))} predicted quadrants about equally well; the centre is used because all four can be drawn around it and their relative moves add up to zero, not because it forecasts better.`:''})()}</p>`;
 if(state.rf!==o.lastK)out+=`<p class="sub">The odds, ranges and next week's prices are for the latest week; the chart shows ${esc(rrgDay(o.Q[state.rf]))}.</p>`;
 if(o.freq!=='w'||o.n!==14)out+=`<p class="sub">The model below is fitted on the weekly chart with the 14-week window (the chart now uses another).</p>`;
 const C=X.centre_now;
 if(C)out+=`<p>Centre against cash: ${rrgIxQ(C.quad)} <span class="muted">(RS-Ratio ${fmt(C.x,2)}, RS-Momentum ${fmt(C.y,2)}${C.box?` · 80% box in 13 weeks: ratio ${fmt(C.box['13'][0],1)}–${fmt(C.box['13'][1],1)}, momentum ${fmt(C.box['13'][2],1)}–${fmt(C.box['13'][3],1)}`:''})</span></p>`;
 out+=`<div class="toolbar">${field('rrgh','Odds horizon',RRGO_H,hh)}</div>`;
 const show=rrgoShown(lab(hh));
 out+=table(['Index','Now','Weight in the centre',...RRGO_N.map(n=>n+' in '+(hh==='1'?'1 week':hh+' weeks')),'Check','Next week\'s close for each quadrant','In 13 weeks (80% of replays)'],X.tickers.map(t=>{const r=X.now[t]||{};
  const v=r.odds&&r.odds[hh],top=v?v.indexOf(Math.max(...v)):-1;
  return [`<b>${esc(t)}</b><br><span class="muted">${esc(((X.names||{})[t]||'').replace(/ \(.*\)$/,''))} · ${rrgIxUsd(r.close)}</span>`,rrgIxQ(r.quad),r.weight==null?'—':fmt(100*r.weight,0)+'%',
   ...[0,1,2,3].map(j=>!v?'—':show?(j===top?`<b>${rrgoPc(v[j])}</b>`:rrgoPc(v[j])):`<span class="muted" title="history, not a forecast">${rrgoPc(v[j])}</span>`),rrgoBadge(lab(hh)),
   rrgIxRanges(r.next_week),r.fan?`${rrgIxUsd(r.fan.q10[12])} – ${rrgIxUsd(r.fan.q90[12])}<br><span class="muted">median ${rrgIxUsd(r.fan.q50[12])}</span>`:'—']}));
 out+=`<p class="sub">Odds: ${esc(head==='iq'?'the matrix by the index\'s quadrant and the centre\'s quadrant against cash (16 states, fixed in advance)':'the quadrant matrix')}, pooled over the four lines since 2002; each label earned on weekly origins from 2012 (blocks of h weeks in the bootstrap, so overlapping weeks are not counted as independent). Indices in the same spot get the same odds. Next week's close: the other three and the bill held where they are, the index's own weight in the centre taken out (rising 10% with a 30% weight moves it about 7% against the centre). Ranges: every 13-week run of the four together (${X.replay==='vol'?'up to ten years, scaled to today\'s volatility':'the last three years'}), replayed from today. Rotation history, not investment advice.</p>`;
 // fans and the most common paths
 out+=`<h4>Replayed prices and the most common paths</h4><div class="ix-cards">`+X.tickers.map(t=>{const r=X.now[t]||{};
  const paths=(r.paths||[]).slice(0,3).map(([q,p])=>`${esc(rrgoPath(q))} <span class="muted">${rrgoPc(p)}</span>`);
  const ch=X.chain&&X.chain.labels?X.chain.labels['13']:null;
  return `<div><b>${esc(t)}</b> ${rrgIxQ(r.quad)}${rrgIxFan(t,r)}${paths.length?`<div class="sub">${rrgoShown(ch)?'Most common 13-week paths':'Paths (history only: the chain did not pass its 13-week check)'}:<br>${paths.join('<br>')}</div>`:''}</div>`}).join('')+`</div>`;
 // which index leads next
 const LN=X.leader_now,LE=(X.leader||{}).labels||{};
 if(LN)out+=`<h4>Which index has the highest RS-Ratio next</h4><p>Order now: ${LN.order.map(esc).join(' › ')}.</p>`+table(['Horizon',...X.tickers,'Check'],Hs.map(h=>{const d=(LN.odds||{})[h],sh=rrgoShown(LE[h]);return [h==='1'?'1 week':h+' weeks',...X.tickers.map(t=>!d?'—':sh?rrgoPc(d[t]):`<span class="muted">${rrgoPc(d[t])}</span>`),rrgoBadge(LE[h])]}))
  +`<p class="sub">From the order of the four by RS-Ratio (24 orders) to the leader h weeks later. ${Object.values(LE).every(l=>!rrgoShown(l))?'It did not beat “the leader stays” out of sample, so these are history, not a forecast.':''}</p>`;
 // how the odds did
 out+=`<details><summary>How the odds did out of sample (from 2012)</summary>`+table(['Head','Horizon','Check','Beats “stays put” by','Beats “usual shares” by','Calibration error','Predictions'],
  Object.entries(M.heads||{}).flatMap(([k,v])=>Hs.map(h=>{const e=(v[h]||{}).eval||{};return [k==='iq'?'Index quadrant × centre vs cash':'Index quadrant',h==='1'?'1 week':h+' weeks',rrgoBadge(e.label),rrgIxSkill(e.brier_skill_vs_stay),rrgIxSkill(e.brier_skill_vs_freq),e.ece==null?'—':fmt(100*e.ece,1)+' pts',fmt(e.predictions)]}))
  .concat(X.chain?Hs.map(h=>{const e=X.chain.eval[h]||{};return ['Weekly chain (paths)',h==='1'?'1 week':h+' weeks',rrgoBadge(e.label),rrgIxSkill(e.brier_skill_vs_stay),rrgIxSkill(e.brier_skill_vs_freq),e.ece==null?'—':fmt(100*e.ece,1)+' pts',fmt(e.predictions)]}):[]))+`</details>`;
 // the comparison of centres, fixed in advance
 const cmp=X.compare||{};
 out+=`<details><summary>Which centre — the comparison fixed in advance</summary><p class="sub">${esc(X.rule||'')}</p>`+table(['Centre','Lines','2003–2011 score','2003–2011 momentum → 4-week return','From 2012: score','From 2012: momentum → 4-week return'],
  Object.entries(cmp).map(([c,v])=>{const ic=a=>Array.isArray(a)?`${fmt(a[0],3)} <span class="muted">[${fmt(a[1],3)}, ${fmt(a[2],3)}]</span>`:'—';
   return [`${c===X.centre?'<b>':''}${esc(cn[c]||c)}${c===X.centre?'</b> ✓':''}`,fmt(v.lines),v.select&&v.select.score!=null?fmt(100*v.select.score,2)+'%':'—',ic(v.select&&v.select.ic4),v.test&&v.test.score!=null?fmt(100*v.test.score,2)+'%':'—',ic(v.test&&v.test.ic4)]}))
  +`<p class="sub">Score: the quadrant matrix's Brier skill against the weaker of “stays put” and “the usual shares”, averaged over 1, 4 and 13 weeks. Momentum: the Spearman correlation of RS-Momentum − 100 with the next four weeks' return against the centre (pooled; 95% interval from a block bootstrap) — near zero for every centre.</p></details>`;
 const cov=X.coverage||{},cl=(c,k)=>{const x=c&&c[k];return x&&x.c80!=null?`${fmt(100*x.c80,0)}% / ${fmt(100*x.c50,0)}%`:'—'};
 out+=`<details><summary>Price ranges — how often the 80% and 50% ranges held</summary>`+table(['Replay','2003–2011: 4 weeks','2003–2011: 13 weeks','From 2012: 1 week','From 2012: 4 weeks','From 2012: 13 weeks'],
  [['plain','The last three years'],['vol','Up to ten years, scaled to today\'s volatility']].map(([k,n])=>[`${k===X.replay?'<b>':''}${esc(n)}${k===X.replay?'</b> ✓':''}`,cl((cov[k]||{}).select,'4'),cl((cov[k]||{}).select,'13'),cl((cov[k]||{}).test,'1'),cl((cov[k]||{}).test,'4'),cl((cov[k]||{}).test,'13')]))
  +`<p class="sub">Origins every 13 weeks; nominal 80% / 50%. The method with the smaller gap on 2003–2011 is used (fixed in advance), whatever the later years show.</p></details>`;
 if(lg&&lg.summary)out+=`<details><summary>Ledger — the forecasts as published, then scored (${esc(fmt(lg.origins))} weeks since ${esc(rrgDay(lg.first))})</summary>`+table(['Horizon','Resolved','Brier score','Inside the 80% range','Inside the 50% range'],Hs.map(h=>{const s=lg.summary[h]||{};return [h==='1'?'1 week':h+' weeks',fmt(s.resolved),s.brier==null?'—':fmt(s.brier,3),s.inside80==null?'—':fmt(100*s.inside80,0)+'%',s.inside50==null?'—':fmt(100*s.inside50,0)+'%']}))+`<p class="sub">Each week's odds and ranges are frozen the first time they are published and never changed; scored when their week arrives.</p></details>`;
 return out+`<p class="sub">${esc(X.note||'')}</p></div>`;
}
