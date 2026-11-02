/* 4.10 Macro — the long pendulum. Data: data/market/history/macro.json (app/macro_history.py on the rotation-history
   branch: FRED series placed at their publication dates) and rrg.json (sector closes, for returns by phase).
   The macro clock: growth momentum across, inflation momentum up (each a composite of z-scores, standardised with data
   up to that month only); the four phases of the investment clock; a walk-forward forecast of next month's point with
   its 80% box, drawn as the rotation charts draw theirs: last forecast dashed with its error, next forecast filled. */
const MAC_GROUPS=[['Growth','Growth'],['Inflation','Inflation'],['Rates','Rates and money'],['Risk','Risk and financial conditions'],['Markets','Dollar and oil']];
const MAC_TRAIL=[['12','12 months'],['24','24 months'],['48','48 months'],['999','Since 2010']];
const MAC_PH=['Recovery','Overheat','Stagflation','Reflation'];
const MAC_PH_COL=['var(--flow-buy)','var(--rot-sun)','var(--flow-sell)','var(--rot-1)'];

function macroView(){
 const g=marketGate('history/macro','The macro data');
 const bar=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}`;
 if(!g.data)return bar+`</div><div class="explain">The macro series are collected from FRED by the “Rotation history” workflow.</div>`+g.html;
 const M=g.data,C=M.clock,Q=C.months;
 state.mgrp=MAC_GROUPS.some(x=>x[0]===state.mgrp)?state.mgrp:'Growth';
 state.mtrail=MAC_TRAIL.some(x=>x[0]===state.mtrail)?state.mtrail:'24';state.mzoom=state.mzoom==='all'?'all':'fit';
 const key='mac|'+Q.length;
 if(state.rfk!==key||!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length)){state.rf=Q.length-1;state.rfk=key}
 state.rfn=null;
 if(!C._fc)C._fc=new Map((C.forecast||[]).map(r=>[r[0],r]));
 const o={M,C,Q,P:{partial:new Set(),span:Q.length,unit:'months',ms:260,label:qlabel}};
 ROT.ctx={Q,P:o.P,draw:f=>macClockFrame(o,f)};
 let out=bar+field('mtrail','Trail',MAC_TRAIL,state.mtrail)+field('mzoom','Scale',[['fit','Fit the trail (rescales while playing)'],['all','Whole history (fixed)']],state.mzoom)+field('mgrp','Series below',MAC_GROUPS,state.mgrp)+'</div>';
 const sc=C.score||{};
 out+=`<div class="explain">The economy has its own rotation. <b>Across</b>: growth momentum — the 6-month change of a growth composite (${esc(macParts(M,C.growth_parts))}); <b>up</b>: inflation momentum (${esc(macParts(M,C.inflation_parts))}). Each series is used only from the day it was published. The dashed box is last month's forecast for this month (80%), the line from its ◇ to the dot is the error (green inside the box, red outside), the filled box and arrow are the forecast for next month. Since ${esc(qlabel(sc.from||''))}: mean distance between forecast and actual ${fmt(sc.mean_point_error,2)} vs ${fmt(sc.standing_still_error,2)} for “stays where it is”, step direction right ${sc.step_direction_hit==null?'—':fmt(100*sc.step_direction_hit,0)+'%'}, inside the 80% box ${sc.inside80==null?'—':fmt(100*sc.inside80,0)+'%'}.</div>`;
 out+=`<div class="panel"><h3>Macro clock — growth × inflation</h3><p class="sub">Month by month since ${esc(qlabel(Q[0]))}; press play to watch the cycle turn. Phases of the investment clock: recovery (growth up, inflation down) → overheat → stagflation → reflation.</p>`;
 out+=rotPlayer(Q,o.P)+`<div id="rot-plot">${macClockFrame(o,state.rf)}</div><div class="mk-legend">${MAC_PH.map((p,i)=>`<span><i class="mk-key" style="background:${MAC_PH_COL[i]}"></i>${p}</span>`).join('')}<span><span class="fc-key fc-key-prev"></span>last forecast (80%)</span><span><span class="fc-key fc-key-in"></span>/<span class="fc-key fc-key-out"></span>error</span><span><span class="fc-key fc-key-next"></span>next forecast</span></div></div>`;
 out+=macPhaseTable(o);
 out+=macSeries(o);
 out+=`<p class="sub">${esc(M.note||'')} Source: ${esc(M.source||'FRED')}.</p>`;
 return out;
}
function macParts(M,keys){const L=Object.fromEntries((M.features||[]).map(f=>[f.key,f.label]));return (keys||[]).map(k=>(L[k]||k).replace(/, year on year/,' y/y')).join(', ')}
function macClockFrame(o,f){
 const {C,Q}=o,gx=C.growth_mom,gy=C.inflation_mom;
 const W=Math.min(760,Math.max(340,(document.getElementById('workspace')||{clientWidth:900}).clientWidth-40)),H=Math.round(W*.72),L=46,R=16,T=16,B=36;
 // a robust scale (the 2020 shock would squash every other year): 97th percentile of |value|; beyond it, drawn at the edge
 const n=+state.mtrail,i0=Math.max(0,f-n+1),rp=C._fc.get(f-1),r=C._fc.get(f);
 let m;
 if(state.mzoom==='all'){const av=[...gx,...gy].filter(v=>v!=null).map(Math.abs).sort((a,b)=>a-b);m=Math.max(1.2,av[Math.floor(.97*(av.length-1))]||1.2)*1.15}
 else{const vs=[];for(let i=i0;i<=f;i++){if(gx[i]!=null)vs.push(Math.abs(gx[i]));if(gy[i]!=null)vs.push(Math.abs(gy[i]))}
  for(const q of [rp,r])if(q)vs.push(...q.slice(1).map(Math.abs));m=Math.max(.5,...vs)*1.15}
 const cl=v=>Math.max(-m,Math.min(m,v)),sx=v=>L+(cl(v)+m)/(2*m)*(W-L-R),sy=v=>T+(m-cl(v))/(2*m)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Macro clock, ${esc(qlabel(Q[f]))}">`;
 const qd=[[0,-1,'Recovery'],[1,1,'Overheat'],[-1,1,'Stagflation'],[-1,-1,'Reflation']];
 qd.forEach(([a,b,t],i)=>{const x0=a>=0?sx(0):L,y0=b>=0?T:sy(0),w=(W-L-R)/2,h=(H-T-B)/2;s+=`<rect x="${x0}" y="${y0}" width="${w}" height="${h}" class="mac-q" style="fill:${MAC_PH_COL[i===0?0:i]}"/>`;
  s+=`<text class="mk-quad" x="${a>=0?W-R-6:L+6}" y="${b>=0?T+14:H-B-8}" text-anchor="${a>=0?'end':'start'}">${t}</text>`});
 niceTicks(-m,m,4).forEach(v=>{s+=`<text class="axis" x="${L-6}" y="${sy(v)+4}" text-anchor="end">${fmt(v,1)}</text><text class="axis" x="${sx(v)}" y="${H-B+15}" text-anchor="middle">${fmt(v,1)}</text>`});
 s+=`<line class="mk-axis" x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
 s+=`<text class="axis" x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle">growth momentum (z, 6-month change) →</text><text class="axis" transform="translate(12 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">inflation momentum →</text>`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-24}" text-anchor="end">${esc(qlabel(Q[f]))}</text>`;
 const pts=[];for(let i=i0;i<=f;i++)if(gx[i]!=null&&gy[i]!=null)pts.push([i,sx(gx[i]),sy(gy[i])]);
 for(let k=1;k<pts.length;k++){const a=pts[k-1],b=pts[k];s+=`<line x1="${a[1].toFixed(1)}" y1="${a[2].toFixed(1)}" x2="${b[1].toFixed(1)}" y2="${b[2].toFixed(1)}" class="mac-trail" style="opacity:${(.2+.75*k/pts.length).toFixed(2)}"/>`}
 pts.forEach(([i,x,y],k)=>{const ph=C.phase[i],head=i===f;
  s+=`<g data-tip="${tip([[qlabel(Q[i]),ph==null?'':MAC_PH[ph]],[fmt(gx[i],2),'growth momentum'],[fmt(gy[i],2),'inflation momentum'],[fmt(C.growth[i],2)+' / '+fmt(C.inflation[i],2),'growth / inflation level (z)']])}" tabindex="-1" class="mk-hit"><circle cx="${x}" cy="${y}" r="${head?9:6}" fill="transparent"/><circle cx="${x}" cy="${y}" r="${head?6:2.4}" style="fill:${ph==null?'var(--muted)':MAC_PH_COL[ph]}" class="${head?'mac-head':''}"/></g>`});
 // last month's forecast for this month, and the forecast for next month
 if(rp&&gx[f]!=null&&gy[f]!=null){const q0=[sx(rp[1]),sy(rp[2])],a=[sx(gx[f]),sy(gy[f])],inside=gx[f]>=rp[3]&&gx[f]<=rp[4]&&gy[f]>=rp[5]&&gy[f]<=rp[6],d=4.4;
  s+=`<g data-tip="${tip([['Forecast made '+qlabel(Q[f-1]),'for '+qlabel(Q[f])],[fmt(rp[1],2)+' / '+fmt(rp[2],2)+' → '+fmt(gx[f],2)+' / '+fmt(gy[f],2),'growth / inflation momentum: forecast → actual'],[fmt(Math.hypot(gx[f]-rp[1],gy[f]-rp[2]),2),'error (distance)'],[inside?'inside':'outside','the 80% box']])}" tabindex="-1" class="mk-hit">`
   +`<rect class="fc-prev" x="${sx(rp[3])}" y="${sy(rp[6])}" width="${Math.max(2,sx(rp[4])-sx(rp[3]))}" height="${Math.max(2,sy(rp[5])-sy(rp[6]))}"/>`
   +`<line class="fc-err ${inside?'fc-err-in':'fc-err-out'}" x1="${q0[0]}" y1="${q0[1]}" x2="${a[0]}" y2="${a[1]}"/><path class="fc-prev-dot" d="M${q0[0]},${q0[1]-d} l${d},${d} l${-d},${d} l${-d},${-d} z"/></g>`}
 if(r&&gx[f]!=null&&gy[f]!=null){const p=[sx(gx[f]),sy(gy[f])],q=[sx(r[1]),sy(r[2])],ph=C.phase[f];
  s+=`<rect class="fc-next-cone" style="fill:var(--ink-2)" x="${sx(r[3])}" y="${sy(r[6])}" width="${Math.max(2,sx(r[4])-sx(r[3]))}" height="${Math.max(2,sy(r[5])-sy(r[6]))}"/>`;
  s+=`<g data-tip="${tip([['Forecast for '+(Q[f+1]?qlabel(Q[f+1]):'next month'),'made '+qlabel(Q[f])],[fmt(r[1],2)+' / '+fmt(r[2],2),'growth / inflation momentum'],[fmt(r[3],2)+'…'+fmt(r[4],2)+' / '+fmt(r[5],2)+'…'+fmt(r[6],2),'80% box']])}" tabindex="-1" class="mk-hit">${fcArrowSvg(p,q,'var(--ink)',2.2)}</g>`}
 return s+'</svg>';
}
function macPhaseTable(o){                              // what each sector did vs SPY in the month after each phase reading
 const r=marketData('history/rrg');if(!r.data)return '';
 const D=r.data,C=o.C,grid0=Date.parse(D.start+'T00:00:00Z');
 const series=(D.series||[]).filter(s=>s.group==='sector-etf'||s.group==='site-sector');
 if(!series.length)return '';
 const at=(ent,ms)=>{const i=Math.floor((ms-Date.parse(ent.start+'T00:00:00Z'))/6048e5);if(i<0)return null;for(let k=Math.min(i,ent.c.length-1);k>=Math.max(0,i-2);k--)if(ent.c[k]!=null)return ent.c[k];return null};
 const end=m=>{const [y,mo]=m.split('-').map(Number);return Date.UTC(y,mo,0)};
 const rows=[],sums={};
 for(const s of series){const acc=[[],[],[],[]];
  for(let i=0;i+1<o.Q.length;i++){const ph=C.phase[i];if(ph==null)continue;const t0=end(o.Q[i]),t1=end(o.Q[i+1]);
   const a0=at(s,t0),a1=at(s,t1),b0=at(D.bench,t0),b1=at(D.bench,t1);if(!a0||!a1||!b0||!b1)continue;acc[ph].push(100*(Math.log(a1/a0)-Math.log(b1/b0)))}
  sums[s.id]=acc.map(a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null);rows.push([s,acc.map(a=>a.length)])}
 const etf=series.filter(s=>s.group==='sector-etf');
 const best=[0,1,2,3].map(ph=>{const v=etf.map(s=>[s,sums[s.id][ph]]).filter(a=>a[1]!=null).sort((a,b)=>b[1]-a[1]);return v.length?v[0][0].id:null});
 const now=C.phase[state.rf];
 const cell=(s,ph)=>{const v=sums[s.id][ph];return v==null?'—':`<span class="${v>=0?'positive':'negative'}${best[ph]===s.id?' mac-best':''}">${v>=0?'+':'−'}${fmt(Math.abs(v),2)}%</span>`};
 const counts=[0,1,2,3].map(ph=>C.phase.slice(0,-1).filter(p=>p===ph).length);
 return `<div class="panel"><h3>Sectors in each phase since ${esc(qlabel(o.Q[0]))}</h3><p class="sub">Average return vs SPY in the month <b>after</b> a month read as each phase (so the phase was known before the return). Best sector ETF per phase in bold.${now!=null?` Now (${esc(qlabel(o.Q[state.rf]))}): <b>${MAC_PH[now]}</b>.`:''} Few months per phase — read as tendencies, not rules.</p>`
  +`<div class="tablebox"><table><thead><tr><th>Sector</th>${MAC_PH.map((p,i)=>`<th class="${i===now?'mac-now':''}">${p} (${counts[i]} mo)</th>`).join('')}</tr></thead><tbody>${etf.map(s=>`<tr><td>${esc(s.name)}</td>${[0,1,2,3].map(ph=>`<td class="num ${ph===now?'mac-now':''}">${cell(s,ph)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
}
function macSeries(o){
 const M=o.M,F=(M.features||[]).filter(f=>f.group===state.mgrp),mo=M.monthly,k0=mo.months.indexOf(o.Q[0]),f=state.rf;
 if(!F.length||k0<0)return '';
 const panels=F.map(ft=>{const a=(mo.data[ft.key]||[]).slice(k0),pts=a.map((v,i)=>[i,v]).filter(p=>p[1]!=null);if(pts.length<3)return '';
  const sv=pts.map(p=>p[1]).sort((a,b)=>a-b),q=f=>sv[Math.floor(f*(sv.length-1))];   // 1st-99th percentile: one shock does not flatten the rest
  const W=360,H=150,L=40,R=8,T=10,B=20,n=a.length,lo=q(.01),hi=q(.99),pad=(hi-lo||1)*.08;
  const x=i=>L+i/Math.max(1,n-1)*(W-L-R),y=v=>T+(hi+pad-Math.max(lo-pad,Math.min(hi+pad,v)))/((hi-lo+2*pad)||1)*(H-T-B);
  let s=`<div class="panel mac-small"><h3>${esc(ft.label)}</h3><svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(ft.label)}">`;
  niceTicks(lo,hi,3).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-5}" y="${y(v)+4}" text-anchor="end">${fmt(v,Math.abs(hi-lo)<4?1:0)}</text>`});
  if(lo<0&&hi>0)s+=`<line class="mk-axis" x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}"/>`;
  s+=`<path class="rot-line" style="stroke:var(--rot-1);stroke-width:1.5" d="${pts.map(([i,v],k)=>(k?'L':'M')+x(i).toFixed(1)+','+y(v).toFixed(1)).join('')}"/>`;
  s+=`<line class="mac-cursor" x1="${x(f)}" x2="${x(f)}" y1="${T}" y2="${H-B}"/>`;
  const v=a[f];if(v!=null)s+=`<circle cx="${x(f)}" cy="${y(v)}" r="3.4" style="fill:var(--rot-1)"/><text class="mk-label mk-halo" x="${x(f)+(f>n*.75?-6:6)}" y="${y(v)-7}" text-anchor="${f>n*.75?'end':'start'}">${fmt(v,2)}${esc(ft.unit==='%'?'%':'')}</text>`;
  s+=`<text class="axis" x="${L}" y="${H-5}">${esc(o.Q[0].slice(0,4))}</text><text class="axis" x="${W-R}" y="${H-5}" text-anchor="end">${esc(o.Q[n-1].slice(0,4))}</text>`;
  return s+'</svg></div>'}).join('');
 return `<div class="rot-multiples mac-grid">${panels}</div>`;
}

/* ---------- Macro release calendar (Rotation → "Macro release calendar"). Data: data/market/history/macro-calendar.json
   (app/macro_calendar.py on the rotation-history branch): every US data release since 1995 with its clock time (ET), what
   it printed that day (before any revision), the day's change in the 2-year and 10-year Treasury yields and SPY's return;
   the FOMC's statements; the release days ahead; and how much each release's days move SPY against quiet days. ---------- */
const MCAL_SPAN=[['1','Last 12 months'],['3','Last 3 years'],['10','Last 10 years'],['all','Since 1995']];
const MCAL_MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function mcalDay(d){const t=new Date(d+'T12:00:00Z');return `${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][t.getUTCDay()]} ${MCAL_MON[t.getUTCMonth()]} ${t.getUTCDate()}, ${t.getUTCFullYear()}`}
function mcalPeriod(D,e){
 if(!e.period)return '';
 const s=(D.releases[e.release]||{}).series||[],freq=((D.series||{})[s[0]]||{}).freq,[y,m,d]=e.period.split('-').map(Number);
 return freq==='q'?`Q${Math.floor((m-1)/3)+1} ${y}`:freq==='w'?`week to ${MCAL_MON[m-1]} ${d}`:`${MCAL_MON[m-1]} ${y}`;
}
const mcalSign=(v,d)=>(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),d);
function mcalHead(D,e){
 const v=e.values||{};
 if(e.release==='fomc')return [v.kind&&v.kind!=='meeting'?v.kind:'statement',v.sep?'projections':'',v.presser?'press conference':'',v.minutes?'minutes out '+v.minutes:''].filter(Boolean).map(esc).join(' · ');
 const parts=Object.keys(v).map(sid=>{const S=(D.series||{})[sid]||{},h=v[sid][1],yoy=v[sid][4];if(h==null)return '';
  const name=esc(S.short||sid);
  if(S.headline==='pct')return `${name} ${mcalSign(h,1)}%${yoy!=null&&/CPI|PCE/.test(S.short||'')?` <span class="muted">(${fmt(yoy,1)}% y/y)</span>`:''}`;
  if(S.headline==='ann')return `${name} ${mcalSign(h,1)}% <span class="muted">annualized</span>`;
  if(S.headline==='chg')return `${name} ${mcalSign(h,0)}k`;
  return `${name} ${fmt(h,S.decimals||0)}${S.unit==='%'?'%':S.unit==='k'?'k':''}`}).filter(Boolean);
 return (e.kind==='revision'?'<span class="muted">revised:</span> ':'')+parts.join(' · ');
}
function mcalRevised(D,e){                             // the reported change as printed → the same change on today's data
 if(e.release==='fomc'||e.kind!=='first')return '';
 return Object.keys(e.values||{}).map(sid=>{const S=(D.series||{})[sid]||{},h=e.values[sid][1],n=e.values[sid][5];if(h==null||n==null)return '';
  const d=S.headline==='chg'?0:S.headline==='lvl'?(S.decimals||0):1,unit=S.headline==='chg'||S.unit==='k'?'k':S.headline==='lvl'?(S.unit==='%'?'%':''):'%';
  const f=v=>(S.headline==='lvl'?fmt(v,d):mcalSign(v,d))+unit;
  return Math.abs(n-h)<(S.headline==='chg'?0.5:S.headline==='lvl'?Math.pow(10,-d)/2:0.05)?'':`${esc(S.short||sid)} ${f(h)} → <b>${f(n)}</b>`}).filter(Boolean).join(' · ')||'<span class="muted">unchanged</span>';
}
const mcalBp=v=>v==null?'<span class="muted">—</span>':`<span class="${v>0?'positive':v<0?'negative':''}">${mcalSign(v,1)}</span>`;
const mcalSpy=v=>v==null?'<span class="muted">—</span>':`<span class="${v>0?'positive':v<0?'negative':''}">${mcalSign(100*Math.expm1(v/1e4),2)}%</span>`;
function macroCalendarView(){
 const bar=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}`;
 const g=marketGate('history/macro-calendar','The macro release calendar');
 if(!g.data)return bar+`</div><div class="explain">The calendar is built by the “Rotation history” workflow: first prints from ALFRED (it needs the repository secret FRED_API_KEY) and the FOMC’s statements from federalreserve.gov.</div>`+g.html;
 const D=g.data,F=D.fields||[];
 if(!D._ev)D._ev=(D.events||[]).map(r=>Object.fromEntries(F.map((f,i)=>[f,r[i]])));
 const rels=Object.keys(D.releases||{});
 state.mcrel=rels.includes(state.mcrel)?state.mcrel:'';
 state.mcspan=MCAL_SPAN.some(x=>x[0]===state.mcspan)?state.mcspan:'1';
 const name=k=>(D.releases[k]||{}).name||k;
 let out=bar+field('mcrel','Release',[['','Every release'],...rels.map(k=>[k,name(k)])],state.mcrel)+field('mcspan','Period',MCAL_SPAN,state.mcspan)+'</div>';
 const onFile=Object.values(D.series||{}).filter(s=>s.on_file).length;
 out+=`<div class="explain">When each US data release came out (Eastern time), what it <b>printed that day</b> — before the revisions that came later — and how the 2-year and 10-year Treasury yields and SPY moved that day; the FOMC’s statements too. The day’s moves are close to close: an 8:30 a.m. release comes before the open, so the day is its first full reaction. Release days are the days ALFRED first held each value, checked against the agencies’ release calendars.${onFile?'':' <b>First prints are not on file yet</b>: they come from the FRED API (repository secret FRED_API_KEY); the FOMC statements below do not need it.'}</div>`;
 const up=(D.upcoming||[]).filter(u=>!state.mcrel||u[2]===state.mcrel).slice(0,24);
 if(up.length)out+=`<div class="panel"><h3>Ahead</h3><p class="sub">Scheduled release days (FRED’s release calendar) and FOMC statements, the next ${up.length}.</p><div class="tablebox"><table><thead><tr><th>Day</th><th>Time (ET)</th><th>Release</th><th></th></tr></thead><tbody>${up.map(u=>`<tr><td>${esc(mcalDay(u[0]))}</td><td class="num">${esc(u[1]||'—')}</td><td>${esc(name(u[2]))}</td><td class="muted">${u[2]==='fomc'&&u[3]?esc([u[3].kind!=='meeting'?u[3].kind:'',u[3].sep?'with projections':''].filter(Boolean).join(' · ')):''}</td></tr>`).join('')}</tbody></table></div></div>`;
 const last=D._ev.length?D._ev[D._ev.length-1].date:'';
 const cut=state.mcspan==='all'||!last?'':(Number(last.slice(0,4))-Number(state.mcspan))+last.slice(4);
 const ev=D._ev.filter(e=>(!state.mcrel||e.release===state.mcrel)&&e.date>cut).slice().reverse();
 const shown=ev.slice(0,400);
 out+=`<div class="panel"><h3>Release days</h3><p class="sub">${fmt(ev.length)} release day${ev.length===1?'':'s'}${ev.length>shown.length?`, the latest ${shown.length} shown`:''}. Yields in basis points; SPY’s return that day.${D.markets&&D.markets.spy?'':' SPY is joined once the hub’s daily returns are published.'} Faded rows are not on the agency’s calendar (an archive date, not a release): leave them out of event studies.</p>`
  +`<div class="tablebox"><table><thead><tr><th>Day</th><th>Time (ET)</th><th>Release</th><th>Period</th><th>Printed that day</th><th>Same figure today</th><th>2-yr</th><th>10-yr</th><th>SPY</th></tr></thead><tbody>`
  +shown.map(e=>`<tr${e.cal===0?' style="opacity:.55"':''}><td>${esc(mcalDay(e.date))}</td><td class="num">${esc(e.time||'—')}</td><td>${esc(name(e.release))}</td><td>${esc(mcalPeriod(D,e))}</td><td>${mcalHead(D,e)}</td><td>${mcalRevised(D,e)}</td><td class="num">${mcalBp(e.y2)}</td><td class="num">${mcalBp(e.y10)}</td><td class="num">${mcalSpy(e.spy)}</td></tr>`).join('')
  +`</tbody></table></div></div>`;
 const st=D.stats||{},sk=Object.keys(st).filter(k=>!state.mcrel||k===state.mcrel);
 if(sk.length)out+=`<div class="panel"><h3>Do release days move the market?</h3><p class="sub">SPY’s and the 2-year yield’s average absolute move on each release’s days against the <b>quiet days</b> — trading days with no release and no FOMC statement — over the same years. A ratio above 1 means the release moves the market more than an ordinary day.</p><div class="tablebox"><table><thead><tr><th>Release</th><th>Days</th><th>Since</th><th>SPY |move|, its days</th><th>quiet days</th><th>Ratio</th><th>SPY average, its days</th><th>2-yr |move| (bp), its days</th><th>quiet days</th></tr></thead><tbody>`
  +sk.sort((a,b)=>(st[b].ratio||0)-(st[a].ratio||0)).map(k=>{const s=st[k],pc=v=>v==null?'—':fmt(v/100,2)+'%';return `<tr><td>${esc(name(k))}</td><td class="num">${fmt(s.days)}</td><td class="num">${esc((s.from||'').slice(0,4))}</td><td class="num">${pc(s.spy_abs)}</td><td class="num">${pc(s.spy_abs_quiet)}</td><td class="num"><b>${s.ratio==null?'—':fmt(s.ratio,2)+'×'}</b></td><td class="num">${s.spy_mean==null?'—':mcalSign(s.spy_mean/100,3)+'%'}</td><td class="num">${s.y2_abs==null?'—':fmt(s.y2_abs,1)}</td><td class="num">${s.y2_abs_quiet==null?'—':fmt(s.y2_abs_quiet,1)}</td></tr>`}).join('')
  +`</tbody></table></div></div>`;
 out+=`<p class="muted" style="font-size:12px">${esc(D.note||'')} ${esc((D.markets||{}).note||'')} Sources: ${esc(D.source||'')}. Built ${esc((D.generated_at||'').slice(0,16).replace('T',' '))} UTC. Download: <a href="data/market/history/macro-calendar.json">macro-calendar.json</a> · <a href="data/market/history/macro-firsts.json">macro-firsts.json</a> (every period’s first print, the day it was printed and today’s value).</p>`;
 return out;
}
