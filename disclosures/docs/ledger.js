/* 4.9 Forecast track record — every forecast the Rotation page published, frozen when it was first shown, then scored.
   Data: data/market/history/forecast-ledger.json (index and per-origin scores) and forecast-ledger-{q,m,w}.json (every
   company's forecast and outcome), built by app/forecast_ledger.py on the rotation-history branch. No dependencies. */
const LED_FREQ=[['q','Quarterly arrows (solar / clock)'],['m','Monthly arrows (solar / clock)'],['w','Weekly RRG arrows (14-week)']];
const LED_MET={
 cal:[['direction_hit','Direction right (up / down)'],['relative_hit','Right side of the median (beat / lag the others)'],['inside80','Actual inside the 80% range'],['mean_abs_gap','Mean gap |actual − forecast| (pts)'],['ic','Rank IC (forecast vs actual)']],
 w:[['step_hit','RRG step pointed the right way'],['direction_hit','Direction vs SPY right'],['relative_hit','Right side of the median'],['mean_point_gap','Distance forecast → actual point'],['ic','Rank IC (forecast vs actual)']]};
const LED_REF={direction_hit:50,relative_hit:50,step_hit:50,inside80:80,ic:0};
const ledPct=v=>v==null?'—':fmt(100*v,0)+'%';
const ledSgn=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),d);
const ledOk=b=>b==null?'<span class="muted">pending</span>':b?'<span class="led-ok">✓</span>':'<span class="led-no">✗</span>';
const ledLabel=(f,c)=>f==='w'?'week of '+rrgDay(c):qlabel(c);
function ledEnd(f,c){                                   // when the target period closes
 if(f==='w')return rrgDay(c);
 let m=/^CY(\d{4})Q(\d)$/.exec(c);if(m)return `${MONTH_NAMES[3*m[2]-1]} ${[31,30,30,31][m[2]-1]}, ${m[1]}`;
 m=/^(\d{4})-(\d{2})$/.exec(c);if(m){const y=+m[1],mo=+m[2],d=new Date(Date.UTC(y,mo,0)).getUTCDate();return `${MONTH_NAMES[mo-1]} ${d}, ${y}`}
 return c;
}
function ledMean(xs){xs=xs.filter(v=>v!=null&&Number.isFinite(+v));return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null}

function ledgerView(){
 const g=marketGate('history/forecast-ledger','The forecast track record');
 const bar=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}`;
 if(!g.data)return bar+`</div><div class="explain">The track record is kept by the “Rotation history” workflow: each forecast is frozen the first time it is published, then scored when its period closes.</div>`+g.html;
 const L=g.data;
 state.lfreq=L.freqs[state.lfreq]?state.lfreq:(L.freqs.q?'q':Object.keys(L.freqs)[0]);
 const f=state.lfreq,F=L.freqs[f],W=f==='w',mets=LED_MET[W?'w':'cal'];
 const d=marketGate('history/forecast-ledger-'+f,'The forecasts of this frequency');
 const O=F.origins;
 if(!O.find(o=>o.origin===state.lorig))state.lorig=(O.slice().reverse().find(o=>o.summary.resolved)||O[O.length-1]||{}).origin;
 state.lmet=mets.some(m=>m[0]===state.lmet)?state.lmet:mets[0][0];
 const secs=Object.entries(L.sectors||{}).sort((a,b)=>a[1].localeCompare(b[1]));
 state.lsec=L.sectors&&L.sectors[state.lsec]?state.lsec:'';
 let out=bar+field('lfreq','Forecasts',LED_FREQ.filter(x=>L.freqs[x[0]]),f)
  +field('lorig','Made at the end of',O.slice().reverse().map(o=>[o.origin,ledLabel(f,o.origin)+(o.source==='live'?' · live':' · backtest')+(o.summary.resolved?'':' · pending')]),state.lorig)
  +field('lsec','Sector',[['','All sectors'],...secs],state.lsec)+'</div>';
 out+=`<div class="toolbar rot-display">${field('lmet','Score',mets,state.lmet)}<div class="field wide"><label for="rtk">Companies to follow (tickers)</label><input id="rtk" value="${esc(state.rtk||'')}" placeholder="e.g. NVDA, AAPL · Enter"></div></div>`;
 const live=O.filter(o=>o.source==='live'),pend=O.filter(o=>!o.summary.resolved);
 out+=`<div class="explain">Every arrow and price the Rotation page publishes is <b>frozen</b> the first time it appears and never edited; when its period closes it gets the actual close and the gap. <b>Live</b> forecasts are the ones actually shown on the site (the ledger began with ${esc(ledLabel(f,F.started||'—'))}); <b>backtest</b> ones predate the ledger — the walk-forward forecasts made only with data public at the time, kept for comparison. ${pend.length?`Next to resolve: ${esc(ledLabel(f,pend[0].origin))}, when ${esc(ledEnd(f,pend[0].target))} closes.`:''}</div>`;
 out+=`<div class="panel"><h3>${esc(mets.find(m=>m[0]===state.lmet)[1])} — each ${W?'week':f==='m'?'month':'quarter'}'s forecasts</h3><p class="sub">Solid bars: live forecasts; pale: backtest; grey ticks: waiting for the period to close. ${state.lmet==='direction_hit'?'The dash on each bar is the share of companies that rose anyway — what calling “up” for everyone would have scored. ':''}Click a bar to open that ${W?'week':'period'}.</p>${ledBars(O,state.lmet,f)}</div>`;
 out+=ledSummary(O,W);
 if(!d.data)return out+d.html;
 const D=d.data,ix=Object.fromEntries(D.fields.map((k,i)=>[k,i])),rows=D.rows[state.lorig]||{},o=O.find(x=>x.origin===state.lorig);
 const meta=L.meta||{},inSec=t=>!state.lsec||(meta[t]&&meta[t][1]===state.lsec);
 const ids=Object.keys(rows).filter(inSec);
 out+=`<div class="rot-multiples">${o?`<div class="panel">${ledOrigin(o,f)}</div>`:''}<div class="panel">${ledScatter(ids,rows,ix,W,meta)}</div></div>`;
 const picks=String(state.rtk||'').toUpperCase().split(/[\s,]+/).filter(Boolean).slice(0,6);
 if(picks.length)out+=ledHistory(picks,D,ix,O,f,meta);
 out+=ledTable(ids,rows,ix,W,meta,o,f);
 return out;
}
function ledBars(O,met,f){
 const n=O.length;if(!n)return empty('No forecasts on file yet');
 const vals=O.map(o=>o.summary.resolved?o.summary[met]:null),pctM=met!=='mean_abs_gap'&&met!=='mean_point_gap'&&met!=='ic';
 const fin=vals.filter(v=>v!=null);
 let lo=pctM?0:Math.min(0,...fin),hi=pctM?1:Math.max(...fin,0.01);if(met==='ic'){const m=Math.max(.3,...fin.map(Math.abs));lo=-m;hi=m}
 const Wd=760,H=230,Lm=44,R=10,T=12,B=30,bw=(Wd-Lm-R)/n,x=i=>Lm+i*bw,y=v=>T+(hi-v)/((hi-lo)||1)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="Score per forecast period">`;
 niceTicks(lo,hi,4).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${Wd-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${Lm-6}" y="${y(v)+4}" text-anchor="end">${pctM?fmt(100*v)+'%':fmt(v,met==='ic'?2:1)}</text>`});
 const ref=LED_REF[met];if(ref!=null)s+=`<line class="mk-axis" x1="${Lm}" x2="${Wd-R}" y1="${y(pctM?ref/100:ref)}" y2="${y(pctM?ref/100:ref)}"/>`;
 O.forEach((o,i)=>{const v=vals[i],sel=o.origin===state.lorig,base=y(Math.max(lo,Math.min(hi,0))),sm=o.summary;
  const rows=[[ledLabel(f,o.origin),o.source==='live'?'live, made '+(o.made_at||'').slice(0,10):'backtest'],[sm.resolved?fmt(sm.resolved)+' of '+fmt(sm.n):'pending','forecasts scored']];
  if(v!=null)rows.push([pctM?ledPct(v):fmt(v,2),'this score']);
  if(sm.share_up!=null)rows.push([ledPct(sm.share_up),'rose anyway']);
  if(sm.inside80!=null)rows.push([ledPct(sm.inside80),'inside the 80% range']);
  let g=`<g data-tip="${tip(rows)}" data-lorig="${esc(o.origin)}" tabindex="-1" class="mk-hit led-bar"><rect x="${x(i)}" y="${T}" width="${bw}" height="${H-T-B}" fill="transparent"/>`;
  if(v==null)g+=`<rect x="${x(i)+bw*.2}" y="${base-3}" width="${Math.max(1,bw*.6)}" height="6" class="led-pend"/>`;
  else{const y0=Math.min(base,y(v)),h=Math.max(1,Math.abs(y(v)-base));
   g+=`<rect x="${x(i)+bw*.12}" y="${y0}" width="${Math.max(1,bw*.76)}" height="${h}" class="${o.source==='live'?'led-live':'led-bt'}${sel?' led-sel':''}"/>`;
   if(met==='direction_hit'&&sm.share_up!=null)g+=`<line class="led-up" x1="${x(i)}" x2="${x(i)+bw}" y1="${y(sm.share_up)}" y2="${y(sm.share_up)}"/>`}
  if(sel)g+=`<path class="led-mark" d="M${x(i)+bw/2},${H-B+3}l-4,7h8z"/>`;
  s+=g+'</g>'});
 const step=Math.max(1,Math.ceil(n/8));
 O.forEach((o,i)=>{if((i%step===0&&(n-1-i>=step*.6||i===0))||i===n-1)s+=`<text class="axis" x="${x(i)+bw/2}" y="${H-6}" text-anchor="middle">${esc(f==='w'?o.origin.slice(5):qlabel(o.origin).replace(/^(\w+) (\d{2})(\d{2})$/,'$1 ’$3'))}</text>`});
 return s+'</svg>';
}
function ledSummary(O,W){
 const grp=(name,os)=>{const r=os.filter(o=>o.summary.resolved),S=k=>ledMean(r.map(o=>o.summary[k]));
  return W?[name,fmt(r.length),fmt(r.reduce((a,o)=>a+o.summary.resolved,0)),ledPct(S('step_hit')),ledPct(S('direction_hit')),ledPct(S('relative_hit')),fmt(S('mean_point_gap'),2),fmt(S('mean_abs_gap'),2),fmt(S('ic'),3)]
   :[name,fmt(r.length),fmt(r.reduce((a,o)=>a+o.summary.resolved,0)),ledPct(S('direction_hit')),ledPct(S('share_up')),ledPct(S('relative_hit')),ledPct(S('inside80')),fmt(S('mean_abs_gap'),1),fmt(S('ic'),3)]};
 const live=O.filter(o=>o.source==='live'),bt=O.filter(o=>o.source!=='live');
 const head=W?['Forecasts','Periods scored','Lines scored','Step right','Direction right','Right of median','Point distance','Mean |gap| (pts)','Mean IC']
  :['Forecasts','Periods scored','Companies scored','Direction right','Rose anyway','Right of median','80% range held','Mean |gap| (pts)','Mean IC'];
 const rows=[grp('Live (published, frozen)',live),grp('Backtest (before the ledger)',bt),grp('All',O)];
 return `<div class="panel"><h3>Scorecard</h3><p class="sub">Averages over the periods already closed. ${W?'“Step right”: the forecast RRG step and the actual one pointed within 90° of each other. “Direction right”: the sign of next week’s return against SPY.':'Compare “Direction right” with “Rose anyway” — in a rising market calling everything up scores well; “Right of median” and the IC do not reward that.'}${live.filter(o=>o.summary.resolved).length?'':' No live forecast has closed yet, so the live row fills in as periods end.'}</p><div class="tablebox"><table><thead><tr>${head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((v,i)=>`<td class="${i?'num':''}">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
}
function ledOrigin(o,f){
 const s=o.summary,W=f==='w';
 const kv=[['Forecast made at the end of',ledLabel(f,o.origin)],['For',W?'the following week ('+rrgDay(o.target)+')':qlabel(o.target)+', closes '+ledEnd(f,o.target)],
  ['Kind',o.source==='live'?`live — frozen ${esc((o.made_at||'').replace('T',' ').replace('+00:00',' UTC'))}${o.code?' · code '+esc(o.code.slice(0,7)):''}${o.late?' · '+fmt(o.late)+' companies added later the same period':''}`:'backtest — walk-forward, data public at the time'],
  ['Scored',s.resolved?fmt(s.resolved)+' of '+fmt(s.n):'pending — '+fmt(s.n)+' forecasts waiting']];
 if(o.late){
  const lp=Object.values(o.late_published||{}),known=lp.filter(Boolean).sort();
  kv.push(['Added later',`${fmt(o.late)} compan${o.late===1?'y':'ies'} joined after the origin was frozen — each with its own first publication time${known.length?` (${esc(known[0].slice(0,10))}${known.length>1&&known[known.length-1].slice(0,10)!==known[0].slice(0,10)?' … '+esc(known[known.length-1].slice(0,10)):''}${known.length<lp.length?'; '+fmt(lp.length-known.length)+' from before row times were kept: time not recorded':''})`:' (frozen before row times were kept: time not recorded)'}; scored apart below`]);
  const ot=s.on_time||{},lt=s.late_rows||{},hit=x=>ledPct(x.direction_hit);
  if(ot.resolved||lt.resolved)kv.push(['Published with the origin · added later',`direction right ${hit(ot)} of ${fmt(ot.resolved||0)} · ${hit(lt)} of ${fmt(lt.resolved||0)}`]);
 }
 if(s.resolved){
  if(W)kv.push(['RRG step pointed the right way',ledPct(s.step_hit)],['Direction vs SPY right',ledPct(s.direction_hit)],['Right side of the median',ledPct(s.relative_hit)],['Distance forecast → actual point',fmt(s.mean_point_gap,2)],['Mean |gap| (pts of relative return)',fmt(s.mean_abs_gap,2)],['Rank IC',fmt(s.ic,3)]);
  else kv.push(['Direction right',ledPct(s.direction_hit)+` <span class="muted">(rose anyway: ${ledPct(s.share_up)})</span>`],['Right side of the median',ledPct(s.relative_hit)],['Actual inside the 80% range',ledPct(s.inside80)],['Average forecast / actual change',ledSgn(s.mean_forecast)+'% / '+ledSgn(s.mean_actual)+'%'],['Mean |gap| · median',fmt(s.mean_abs_gap,1)+' · '+fmt(s.median_abs_gap,1)+' pts'],['Rank IC',fmt(s.ic,3)]);
 }
 return `<h3>${esc(ledLabel(f,o.origin))} → ${esc(W?rrgDay(o.target):qlabel(o.target))}</h3><dl class="led-kv">${kv.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
}
function ledScatter(ids,rows,ix,W,meta){
 const fk=W?'forecast_rel_pct':'forecast_change_pct',ak=W?'actual_rel_pct':'actual_change_pct';
 const pts=ids.map(t=>[t,rows[t][ix[fk]],rows[t][ix[ak]]]).filter(p=>p[1]!=null&&p[2]!=null);
 const title=W?'Forecast vs actual return vs SPY, next week':'Forecast vs actual price change';
 if(pts.length<2)return `<h3>${esc(title)}</h3>${empty('Waiting for the period to close')}`;
 const q=(a,p)=>{const s=a.slice().sort((x,y)=>x-y);return s[Math.floor(p*(s.length-1))]};
 const ax=pts.map(p=>p[2]),fx=pts.map(p=>p[1]);
 const ylo=Math.min(q(ax,.02),0),yhi=Math.max(q(ax,.98),0),xlo=Math.min(q(fx,.01),0),xhi=Math.max(q(fx,.99),0);
 const xpad=(xhi-xlo||1)*.08,ypad=(yhi-ylo||1)*.06;
 const Wd=420,H=300,Lm=44,R=10,T=12,B=34,x=v=>Lm+(v-xlo+xpad)/((xhi-xlo+2*xpad)||1)*(Wd-Lm-R),y=v=>T+(yhi+ypad-v)/((yhi-ylo+2*ypad)||1)*(H-T-B);
 const cl=(v,a,b)=>Math.max(a,Math.min(b,v));
 let s=`<h3>${esc(title)}</h3><p class="sub">Each dot a company: across = the forecast, up = what happened (%). Points far above or below the flat zero line are the big surprises; a cloud tilted up to the right means the ranking held.</p><svg class="plot mk-plot" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="${esc(title)}">`;
 niceTicks(ylo,yhi,4).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${Wd-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${Lm-6}" y="${y(v)+4}" text-anchor="end">${fmt(v)}%</text>`});
 niceTicks(xlo,xhi,4).forEach(v=>{s+=`<text class="axis" x="${x(v)}" y="${H-B+14}" text-anchor="middle">${fmt(v,W?2:1)}%</text>`});
 s+=`<line class="mk-axis" x1="${Lm}" x2="${Wd-R}" y1="${y(0)}" y2="${y(0)}"/><line class="mk-axis" x1="${x(0)}" x2="${x(0)}" y1="${T}" y2="${H-B}"/>`;
 pts.forEach(([t,fv,av])=>{const hit=Math.sign(fv)===Math.sign(av),m=meta[t]||[];
  s+=`<g data-tip="${tip([[t,m[0]||''],[ledSgn(fv,W?2:1)+'%','forecast'],[ledSgn(av,W?2:1)+'%','actual'],[ledSgn(av-fv,W?2:1)+' pts','gap']])}" tabindex="-1" class="mk-hit"><circle cx="${cl(x(fv),Lm,Wd-R)}" cy="${cl(y(av),T,H-B)}" r="3.2" class="${hit?'led-dot-ok':'led-dot-no'}"/></g>`});
 s+=`<text class="axis" x="${Wd-R}" y="${H-4}" text-anchor="end">forecast →</text>`;
 return s+'</svg>';
}
function ledHistory(picks,D,ix,O,f,meta){
 // price levels: each target period's close, the frozen forecast for it (dashed 80% range, ◇) with the error, and the
 // pending forecast as a filled fan (chaos.js fcPriceSvg)
 const W=f==='w',N=W?26:f==='m'?36:80,u=W?'week':f==='m'?'month':'quarter';
 let out='<div class="rot-multiples">';
 for(const t of picks){
  const m=meta[t]||[];
  const ser=O.map(o=>{const r=(D.rows[o.origin]||{})[t];return r?{o,r}:null}).filter(Boolean).slice(-N);
  if(!ser.length){out+=`<div class="panel"><h3>${esc(t)}</h3>${empty('No forecasts for this ticker at this frequency')}</div>`;continue}
  const tl=o=>W?rrgDay(o.target):qlabel(o.target);
  const done=ser.filter(a=>a.r[ix.actual_close]!=null),pend=ser.filter(a=>a.r[ix.actual_close]==null);
  const pts=done.map(({o,r})=>({label:tl(o),close:r[ix.actual_close],prev:r[ix.close],live:o.source==='live',
   f:{p:W?r[ix.close_next]:r[ix.price],lo:W?null:r[ix.lo80],hi:W?null:r[ix.hi80]}}));
  if(ser.length)pts.unshift({label:W?rrgDay(ser[0].o.origin):qlabel(ser[0].o.origin),close:ser[0].r[ix.close],f:null});
  const nx=pend[pend.length-1],next=nx?{label:tl(nx.o),p:W?nx.r[ix.close_next]:nx.r[ix.price],lo:W?null:nx.r[ix.lo80],hi:W?null:nx.r[ix.hi80]}:null;
  out+=`<div class="panel"><h3>${esc(t)} <span class="muted">${esc(m[0]||'')}</span></h3><p class="sub">Each ${u}'s close (dots), the frozen forecast for it (dashed 80% range, ◇) and the error (green inside the range, red outside)${next?'; the filled fan: the forecast still waiting for '+esc(next.label):''}. ${esc(fcPriceStats(pts))}.</p>${fcPriceSvg(pts,next,{title:t+' forecasts vs actual'})}</div>`;
 }
 return out+'</div>';
}
function ledTable(ids,rows,ix,W,meta,o,f){
 const pend=o&&!o.summary.resolved;
 const name=t=>{const m=meta[t]||[];return (m[2]==='company'?tkLink(t):`<b>${esc(t)}</b>`)+` <span class="muted">${esc(shortName(m[0]||'')||'')}</span>`};
 const get=(t,k)=>rows[t][ix[k]];
 let head,body;
 if(W){
  head=['Line','Close then','Forecast next point (RS-Ratio, Momentum)','Actual next point','Forecast vs SPY','Actual vs SPY','Gap (pts)','Point distance','Step right','Direction right'];
  body=ids.map(t=>[name(t),fmt(get(t,'close'),2),`${fmt(get(t,'next_x'),2)}, ${fmt(get(t,'next_y'),2)}`,get(t,'actual_x')==null?'<span class="muted">pending</span>':`${fmt(get(t,'actual_x'),2)}, ${fmt(get(t,'actual_y'),2)}`,
   ledSgn(get(t,'forecast_rel_pct')??100*get(t,'rel_logret'),2)+'%',get(t,'actual_rel_pct')==null?'—':ledSgn(get(t,'actual_rel_pct'),2)+'%',ledSgn(get(t,'gap_pts'),2),fmt(get(t,'point_gap'),2),ledOk(get(t,'step_right')),ledOk(get(t,'direction_right'))]);
  exported=ids.map(t=>({origin:o&&o.origin,line:t,name:(meta[t]||[])[0],source:o&&o.source,...Object.fromEntries(Object.entries(ix).map(([k,i])=>[k,rows[t][i]]))}));
 }else{
  head=['Company','Close then','Forecast price','80% range','Actual close','Forecast change','Actual change','Gap (pts)','In range','Direction right'];
  body=ids.map(t=>[name(t),fmt(get(t,'close'),2),fmt(get(t,'price'),2),`${fmt(get(t,'lo80'),2)} – ${fmt(get(t,'hi80'),2)}`,get(t,'actual_close')==null?'<span class="muted">pending</span>':fmt(get(t,'actual_close'),2),
   ledSgn(get(t,'forecast_change_pct')??100*(get(t,'price')/get(t,'close')-1))+'%',get(t,'actual_change_pct')==null?'—':ledSgn(get(t,'actual_change_pct'))+'%',ledSgn(get(t,'gap_pts')),ledOk(get(t,'inside80')),ledOk(get(t,'direction_right'))]);
  exported=ids.map(t=>({origin:o&&o.origin,target:o&&o.target,ticker:t,name:(meta[t]||[])[0],sector:(meta[t]||[])[1],source:o&&o.source,...Object.fromEntries(Object.entries(ix).map(([k,i])=>[k,rows[t][i]]))}));
 }
 return `<div class="section-head"><h3>${esc(o?ledLabel(f,o.origin):'')} · ${fmt(ids.length)} ${W?'lines':'companies'}${pend?' · waiting for '+esc(ledEnd(f,o.target)):''}</h3><button class="action" id="csv">Export CSV ↓</button></div>`
  +`<p class="sub">Gap = actual change − forecast change, in percentage points (positive: it did better than forecast). Prices adjusted for splits and dividends. Click a column to sort.</p>`+table(head,body);
}
function bindLedger(){
 document.querySelectorAll('#workspace [data-lorig]').forEach(b=>b.onclick=()=>{state.lorig=b.dataset.lorig;state.page=0;render()});
}
