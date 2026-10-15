/* 4.4 rotation views: the momentum clock (each company's path through profit momentum × price momentum, quarter by
   quarter) and the sector orbits (each sector a sun at its average, its companies as planets around it).
   Data: data/market/rotation.json (app/rotation.py, built at publish). Uses the helpers of market.js. */
const ROT_SERIES=['var(--rot-1)','var(--rot-2)','var(--rot-3)'];
const ROT_Q=[['8','Last 8 quarters'],['12','Last 12 quarters'],['16','Last 16 quarters']];
const pp=v=>v==null?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v),1)+' pts';
const qlabel=c=>String(c||'').replace(/^CY(\d{4})Q(\d)$/,'Q$2 $1');
function niceTicks(lo,hi,n=5){const raw=(hi-lo)/n,p=10**Math.floor(Math.log10(raw||1)),st=[1,2,2.5,5,10].map(m=>m*p).find(x=>x>=raw);const out=[];for(let v=Math.ceil(lo/st)*st;v<=hi+1e-9;v+=st)out.push(+v.toFixed(6));return out}

function rotationView(){
 let out=head('Rotation','How each company moves through two cycles at once: profitability (operating margin against the same quarter a year earlier) and the stock (its quarter against the S&P 500). Healthy cycles tend to circle clockwise through the four quadrants.','XBRL · PRICES · 13F');
 const g=marketGate('rotation','Rotation charts');if(!g.data)return out+g.html;
 const d=g.data,cos=d.companies||[],suns=d.sectors||{};
 const secs=Object.entries(suns).filter(([,v])=>v.pts&&v.pts.length).sort((a,b)=>a[1].name.localeCompare(b[1].name));
 state.rview=state.rview==='orbits'?'orbits':'clock';state.rsec=suns[state.rsec]?state.rsec:'';state.rq=['8','12','16'].includes(state.rq)?state.rq:'12';
 out+=`<div class="toolbar">${field('rview','Chart',[['clock','Momentum clock'],['orbits','Sector orbits (solar system)']],state.rview)}${field('rsec','Sector',[['','All sectors'],...secs.map(([k,v])=>[k,v.name])],state.rsec)}${state.rview==='clock'?field('rq','Trail',ROT_Q,state.rq):''}<div class="field wide"><label for="rtk">Companies to trace (up to three tickers)</label><input id="rtk" value="${esc(state.rtk||'')}" placeholder="e.g. NVDA, AMD, INTC · Enter"></div></div>`;
 const picks=String(state.rtk||'').toUpperCase().split(/[\s,]+/).filter(Boolean).slice(0,3).map(t=>cos.find(c=>c.t===t||c.t===t.replace('.','-'))).filter(Boolean);
 if(state.rview==='orbits')out+=orbitsView(d,secs,picks);else out+=clockView(d,secs,picks);
 out+=`<details><summary>How these charts are built</summary><p>${esc(d.note||'')}</p><p class="sub">Calendar quarters (SEC frames align fiscal quarters to the nearest calendar quarter); returns run from one calendar quarter-end close to the next. A clockwise path means profit momentum turned before the price did — a pattern, not a forecast.</p></details>`;
 return out;
}

/* ---------- momentum clock ---------- */
function clockView(d,secs,picks){
 const n=+state.rq,suns=d.sectors||{};
 const traces=picks.length?picks.map((c,i)=>({name:c.t,full:c.n,color:ROT_SERIES[i],pts:c.pts.slice(-n),co:c}))
  :state.rsec?[{name:suns[state.rsec].name,full:'Sector average',color:ROT_SERIES[0],pts:suns[state.rsec].pts.slice(-n)}]
  :[];
 const ref=picks.length?suns[picks[0].s]:null;
 const context=!picks.length&&!state.rsec?secs.map(([k,v])=>({name:v.name,pts:v.pts.slice(-n)})):[];
 let out=`<div class="panel"><h3>Momentum clock</h3><p class="sub">→ operating margin vs a year earlier (points) · ↑ the stock's quarter minus the S&P 500 · each dot one quarter, the large dot the latest${picks.length?' · dot size: trading volume vs the company’s average':''}</p>`;
 out+=clockSVG(traces,ref?{name:ref.name+' (sector)',pts:ref.pts.slice(-n)}:null,context);
 out+=`<div class="mk-legend">${traces.map(t=>`<span><i class="mk-key" style="background:${t.color}"></i>${esc(t.name)}${t.full&&t.full!==t.name?' <span class="muted">'+esc(t.full)+'</span>':''}</span>`).join('')}${ref?`<span><i class="mk-key" style="background:var(--flow-dot)"></i>${esc(ref.name)} sector average</span>`:''}${context.length?'<span class="muted">Every sector’s average path; pick a sector or type tickers to trace companies</span>':''}</div></div>`;
 if(picks.length)out+=`<div class="rot-multiples">${picks.map((c,i)=>planar(c,n,ROT_SERIES[i])).join('')}</div>`;
 // the table: latest quarter of every company in scope
 const scope=(d.companies||[]).filter(c=>!state.rsec||c.s===state.rsec);
 const quad=p=>p.dom>=0?(p.rel>=0?'Profits ↑ · beating the market':'Profits ↑ · lagging the market'):(p.rel>=0?'Profits ↓ · beating the market':'Profits ↓ · lagging the market');
 exported=scope.map(c=>({ticker:c.t,name:c.n,sector:c.s,...c.pts[c.pts.length-1]}));
 out+=`<div class="section-head"><h3>${fmt(scope.length)} companies · latest quarter</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=table(['Company','Quarter','Operating margin','Margin vs a year earlier','Stock vs S&P 500','Volume vs average','Quadrant','13F net managers'],scope.map(c=>{const p=c.pts[c.pts.length-1];return [
  `<b>${esc(c.t)}</b> <span class="muted">${esc(c.n)}</span>`,esc(qlabel(p.cal)),fmt(p.om,1)+'%',`<span class="${p.dom>=0?'positive':'negative'}">${pp(p.dom)}</span>`,
  `<span class="${p.rel>=0?'positive':'negative'}">${spct(p.rel)}</span>`,p.volz==null?'—':spct(p.volz,0),esc(quad(p)),c.net13f==null?'—':signed(c.net13f)]}));
 return out;
}
function clockSVG(traces,ref,context){
 const W=720,H=440,L=56,R=20,T=20,B=44;
 const all=[...traces.flatMap(t=>t.pts),...(ref?ref.pts:[]),...context.flatMap(t=>t.pts)];
 if(!all.length)return empty('Pick a sector or type tickers to trace.');
 const xc=v=>Math.max(-30,Math.min(30,v)),yc=v=>Math.max(-.6,Math.min(.6,v));
 const xm=Math.max(2,...all.map(p=>Math.abs(xc(p.dom))))*1.1,ym=Math.max(.05,...all.map(p=>Math.abs(yc(p.rel))))*1.1;
 const sx=v=>L+(xc(v)+xm)/(2*xm)*(W-L-R),sy=v=>T+(ym-yc(v))/(2*ym)*(H-T-B);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Momentum clock; the table below lists every value">`;
 niceTicks(-ym,ym,6).forEach(v=>{s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${spct(v,0)}</text>`});
 niceTicks(-xm,xm,6).forEach(v=>{s+=`<text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${v>0?'+':''}${fmt(v,0)}</text>`});
 s+=`<line class="mk-axis" x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
 s+=`<text class="mk-quad" x="${W-R-4}" y="${T+12}" text-anchor="end">Profits ↑ · beating the market</text><text class="mk-quad" x="${W-R-4}" y="${H-B-8}" text-anchor="end">Profits ↑ · lagging</text><text class="mk-quad" x="${L+6}" y="${T+12}">Profits ↓ · beating the market</text><text class="mk-quad" x="${L+6}" y="${H-B-8}">Profits ↓ · lagging</text>`;
 s+=`<text class="axis" x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle">Operating margin vs a year earlier (points) →</text>`;
 const path=(pts,cls,stroke)=>pts.length>1?`<polyline class="${cls}" style="${stroke?'stroke:'+stroke:''}" points="${pts.map(p=>sx(p.dom).toFixed(1)+','+sy(p.rel).toFixed(1)).join(' ')}"/>`:'';
 context.forEach(t=>{s+=path(t.pts,'rot-ctx');const h=t.pts[t.pts.length-1];if(h)s+=`<g data-tip="${tip([[t.name,'sector average, '+qlabel(h.cal)],[pp(h.dom),'operating margin vs a year earlier'],[spct(h.rel),'vs the S&P 500']])}" tabindex="0" class="mk-hit"><circle cx="${sx(h.dom)}" cy="${sy(h.rel)}" r="10" fill="transparent"/><circle cx="${sx(h.dom)}" cy="${sy(h.rel)}" r="4" class="mk-dot"/></g><text class="mk-label mk-halo" x="${sx(h.dom)+7}" y="${sy(h.rel)-6}">${esc(t.name)}</text>`});
 if(ref){s+=path(ref.pts,'rot-ref');}
 traces.forEach(t=>{
  s+=path(t.pts,'rot-line',t.color);
  t.pts.forEach((p,i)=>{const head=i===t.pts.length-1,op=.35+.65*(i/Math.max(1,t.pts.length-1)),r=head?7:3+Math.max(0,Math.min(3,(p.volz||0)*3));
   s+=`<g data-tip="${tip([[t.name+' · '+qlabel(p.cal),t.full||''],[pp(p.dom),'operating margin vs a year earlier ('+fmt(p.om,1)+'% now)'],[spct(p.rel),'stock vs the S&P 500 ('+spct(p.ret)+' absolute)'],...(p.volz!=null?[[spct(p.volz,0),'trading volume vs its average']]:[])])}" tabindex="0" class="mk-hit"><circle cx="${sx(p.dom)}" cy="${sy(p.rel)}" r="11" fill="transparent"/><circle cx="${sx(p.dom)}" cy="${sy(p.rel)}" r="${r}" style="fill:${t.color};opacity:${op.toFixed(2)}" class="rot-dot"/></g>`});
  const h=t.pts[t.pts.length-1];if(h){const lbl=`${t.name} ${qlabel(h.cal)}`,x=sx(h.dom),left=x+10+lbl.length*7.2>W-R;
   s+=`<text class="mk-label mk-halo" x="${left?x-10:x+10}" y="${sy(h.rel)-9}" text-anchor="${left?'end':'start'}">${esc(lbl)}</text>`}
 });
 return s+'</svg>';
}
function planar(c,n,color){                          // the clock split into three plain charts
 const pts=c.pts.slice(-n),W=300,H=120,L=36,R=8,T=10,B=22,x=i=>L+i/Math.max(1,pts.length-1)*(W-L-R);
 const line=(vals,fmtv,label)=>{const lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo)*.15||1,y=v=>T+(hi+pad-v)/((hi-lo)+2*pad)*(H-T-B);
  return `<div class="rot-mini"><h4>${label}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot">${[lo,hi].map(v=>`<text class="axis" x="${L-6}" y="${y(v)+4}" text-anchor="end">${fmtv(v)}</text><line class="mk-grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/>`).join('')}<polyline class="rot-line" style="stroke:${color}" points="${vals.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ')}"/>${vals.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="${i===vals.length-1?4.5:2.5}" style="fill:${color}"><title>${esc(qlabel(pts[i].cal))}: ${esc(fmtv(v))}</title></circle>`).join('')}<text class="axis" x="${L}" y="${H-6}">${esc(qlabel(pts[0].cal))}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(qlabel(pts[pts.length-1].cal))}</text></svg></div>`};
 const bars=(vals,fmtv,label)=>{const m=Math.max(.01,...vals.map(v=>Math.abs(v||0))),mid=T+(H-T-B)/2,bw=Math.max(4,(W-L-R)/vals.length-4);
  return `<div class="rot-mini"><h4>${label}</h4><svg viewBox="0 0 ${W} ${H}" class="plot mk-plot"><line class="mk-axis" x1="${L}" x2="${W-R}" y1="${mid}" y2="${mid}"/><text class="axis" x="${L-6}" y="${T+6}" text-anchor="end">${fmtv(m)}</text><text class="axis" x="${L-6}" y="${H-B}" text-anchor="end">${fmtv(-m)}</text>${vals.map((v,i)=>{if(v==null)return '';const h=Math.abs(v)/m*((H-T-B)/2),X=x(i)-bw/2;return `<rect x="${X}" y="${v>=0?mid-h:mid}" width="${bw}" height="${Math.max(1,h)}" rx="2" class="${v>=0?'mk-buy':'mk-sell'}"><title>${esc(qlabel(pts[i].cal))}: ${esc(fmtv(v))}</title></rect>`}).join('')}<text class="axis" x="${L}" y="${H-6}">${esc(qlabel(pts[0].cal))}</text><text class="axis" x="${W-R}" y="${H-6}" text-anchor="end">${esc(qlabel(pts[pts.length-1].cal))}</text></svg></div>`};
 return `<div class="panel rot-card"><h3><span class="mk-key" style="background:${color}"></span> ${esc(c.t)} <span class="muted">${esc(c.n)}</span></h3>${line(pts.map(p=>p.om),v=>fmt(v,0)+'%','Operating margin')}${bars(pts.map(p=>p.rel),v=>spct(v,0),'Quarter vs the S&P 500')}${pts.some(p=>p.volz!=null)?bars(pts.map(p=>p.volz),v=>spct(v,0),'Trading volume vs its average'):`<p class="sub">Trading volume appears as the price files are refreshed with volume.</p>`}${c.net13f!=null?`<p class="sub">13F this quarter: ${signed(c.net13f)} net managers · est. ${smoney(c.usd13f)}</p>`:''}</div>`;
}

/* ---------- sector orbits ---------- */
function orbitsView(d,secs,picks){
 const one=state.rsec?[[state.rsec,d.sectors[state.rsec]]]:secs;
 let out=`<div class="panel"><h3>Sector orbits</h3><p class="sub">Each sector is a sun at its average for the latest quarter; its companies orbit it. Direction = how a company differs from its sector (→ better profit momentum, ↑ better stock), distance = by how much (log scale), planet size = revenue, colour = this quarter's 13F crowding (green more managers added, red more cut).</p>`;
 out+=state.rsec?orbitSVG(d,state.rsec,d.sectors[state.rsec],680,picks):`<div class="rot-grid">${one.map(([k,v])=>`<div class="rot-orbit"><h4>${esc(v.name)}</h4>${orbitSVG(d,k,v,300,picks,true)}</div>`).join('')}</div>`;
 out+=`<div class="mk-legend"><span><i class="mk-key mk-hot"></i>More 13F managers added</span><span><i class="mk-key" style="background:var(--flow-sell)"></i>More cut</span><span><i class="mk-key mk-dot"></i>No 13F change on file</span><span class="muted">Hover a planet for its numbers</span></div></div>`;
 return out;
}
function orbitSVG(d,sid,sun,W,picks,mini){
 const H=W,c0=W/2,R=W/2-(mini?16:70),last=sun.pts[sun.pts.length-1];
 if(!last)return empty('No quarter with three or more companies yet');
 const planets=(d.companies||[]).filter(c=>c.s===sid).map(c=>({c,p:c.pts.find(p=>p.cal===last.cal)})).filter(x=>x.p);
 if(!planets.length)return empty('No companies with this quarter');
 const dx=x=>(x.p.dom-last.dom),dy=x=>(x.p.rel-last.rel)*100;              // both in points
 const dist=x=>Math.hypot(dx(x),dy(x)),maxD=Math.max(1,...planets.map(dist)),rad=x=>Math.log1p(dist(x))/Math.log1p(maxD)*R;
 const maxRev=Math.max(...planets.map(x=>x.c.rev||1)),size=x=>(mini?2:3)+(mini?5:10)*Math.sqrt((x.c.rev||0)/maxRev);
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sun.name)} sector orbit">`;
 [1,5,20,60].filter(v=>v<maxD*1.05).forEach(v=>{const r=Math.log1p(v)/Math.log1p(maxD)*R;s+=`<circle cx="${c0}" cy="${c0}" r="${r}" class="rot-ring"/>${mini?'':`<text class="axis" x="${c0+r*.7071+3}" y="${c0-r*.7071-3}">${v} pt${v===1?'':'s'}</text>`}`});
 s+=`<line class="mk-grid" x1="${c0-R}" x2="${c0+R}" y1="${c0}" y2="${c0}"/><line class="mk-grid" x1="${c0}" x2="${c0}" y1="${c0-R}" y2="${c0+R}"/>`;
 if(!mini)s+=`<text class="mk-quad" x="${W-4}" y="${c0-8}" text-anchor="end">profit</text><text class="mk-quad" x="${W-4}" y="${c0+16}" text-anchor="end">momentum →</text><text class="mk-quad" x="${c0}" y="16" text-anchor="middle">↑ stock vs sector</text><text class="mk-quad" x="4" y="${c0-8}">← profit</text><text class="mk-quad" x="4" y="${c0+16}">momentum</text><text class="mk-quad" x="${c0}" y="${H-6}" text-anchor="middle">↓ stock vs sector</text>`;
 const named=new Set([...picks.map(c=>c.t),...planets.slice().sort((a,b)=>(b.c.rev||0)-(a.c.rev||0)).slice(0,mini?3:10).map(x=>x.c.t)]);
 planets.sort((a,b)=>(a.c.rev||0)-(b.c.rev||0)).forEach(x=>{const a=Math.atan2(dy(x),dx(x)),r=rad(x),px=c0+r*Math.cos(a),py=c0-r*Math.sin(a),n=x.c.net13f,cls=n>0?'mk-hot':n<0?'rot-sell':'mk-dot';
  s+=`<g data-tip="${tip([[x.c.t,x.c.n||''],[pp(x.p.dom),'operating margin vs a year earlier (sector '+pp(last.dom)+')'],[spct(x.p.rel),'stock vs the S&P 500 (sector '+spct(last.rel)+')'],[n==null?'—':signed(n),'net 13F managers this quarter'],[money(x.c.rev),'quarterly revenue']])}" tabindex="0" class="mk-hit"><circle cx="${px}" cy="${py}" r="${Math.max(9,size(x)+3)}" fill="transparent"/><circle cx="${px}" cy="${py}" r="${size(x)}" class="${cls}"/></g>`});
 const boxes=[],fs=mini?10:12;
 planets.filter(x=>named.has(x.c.t)).sort((a,b)=>(b.c.rev||0)-(a.c.rev||0)).forEach(x=>{const a=Math.atan2(dy(x),dx(x)),r=rad(x),px=c0+r*Math.cos(a),py=c0-r*Math.sin(a),w=x.c.t.length*fs*.62;
  let lx=px+size(x)+3,anchor='start';if(lx+w>W-2){lx=px-size(x)-3;anchor='end'}
  const b=anchor==='start'?[lx,py-fs-2,lx+w,py]:[lx-w,py-fs-2,lx,py];if(boxes.some(o=>b[0]<o[2]&&b[2]>o[0]&&b[1]<o[3]&&b[3]>o[1]))return;boxes.push(b);
  s+=`<text class="mk-label mk-halo" style="font-size:${fs}px" x="${lx}" y="${py-3}" text-anchor="${anchor}">${esc(x.c.t)}</text>`});
 s+=`<circle cx="${c0}" cy="${c0}" r="${mini?7:12}" class="rot-sun"/>`;
 return s+'</svg>'+(mini?`<p class="sub rot-cap">${esc(qlabel(last.cal))} · margin ${pp(last.dom)} · stock ${spct(last.rel,0)}</p>`:`<p class="sub">The sun: ${esc(sun.name)} average for ${esc(qlabel(last.cal))} — operating margin ${pp(last.dom)} vs a year earlier, stock ${spct(last.rel)} vs the S&P 500 (${fmt(last.n)} companies).</p>`);
}
function bindRotation(){
 for(const k of ['rview','rsec','rq'])bind(k,k);
 if($('rtk')){$('rtk').onchange=e=>{state.rtk=e.target.value;render()};$('rtk').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
}
