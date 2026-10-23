/* 4.6b Quadrant odds and future paths on the weekly RRG (research spec v5 §4.4, §8.3–§8.4, §11; app/transition_rrg.py →
   data/market/history/rrg-transition-model.json, rebuilt with the RRG forecasts on the branch rotation-history).
   · Odds: where a line stands 1, 4 and 13 weeks later, from smoothed empirical transition matrices of every pair whose
     outcome is known. The matrix each line reads was fixed before any test: sectors / ETFs and companies against SPY
     read the quadrant-only matrix; companies against their industry (the dual RRG) read the matrix conditioned on where
     the industry stands against SPY.
   · Paths: the weekly chain over (quadrant, direction of the last step) — (industry quadrant, company quadrant) in the
     dual RRG — stepped week by week: each quadrant's probability for weeks 1–13 and the most common routes (seeded
     simulation, so the same week always gives the same routes).
   · Every head and horizon carries the label it earned walk-forward from 2012 against staying put and the overall
     quadrant frequencies; probabilities are shown only where it is Calibrated or Experimental, the rest as history.
   Shown for the latest week only: the matrices are fitted on the whole history, so on an earlier week they would know
   what came after it. Uses market.js, rotation.js and rrg.js. */
const RRGO_H=[['1','1 week'],['4','4 weeks'],['13','13 weeks']];
const RRGO_L={calibrated:['Calibrated','ready','beat staying put and the overall quadrant frequencies out of sample, both 95% intervals above zero, calibration error at most 2 points'],
 experimental:['Experimental','pending','beat both baselines out of sample, but an interval touches zero or the calibration error is above 2 points'],
 descriptive_only:['History only','','did not beat a baseline out of sample: the shares are history, not a forecast'],
 insufficient_data:['Too little data','','fewer than 50 test origins or 2,000 test predictions: history only']};
const RRGO_G={etf_vs_market:'Sectors / ETFs vs the S&P 500 · quadrant matrix',company_vs_market:'Companies vs the S&P 500 · quadrant matrix',
 company_vs_industry:'Companies vs their industry · matrix by the industry\'s quadrant'};
const RRGO_GS={etf_vs_market:'Quadrant · ETFs',company_vs_market:'Quadrant · companies',company_vs_industry:'Industry × quadrant'};
const RRGO_HEAD={q:'Quadrant matrix',qh:'Quadrant + direction of the last step (research only)',iq:'By the industry\'s quadrant'};
const RRGO_K=['lead','weak','lag','imp'],RRGO_N=['Leading','Weakening','Lagging','Improving'];
const RRGO={paths:new Map()};
const rrgoShown=l=>l==='calibrated'||l==='experimental';
const rrgoH=()=>RRGO_H.some(h=>h[0]===state.rrgh)?state.rrgh:'4';
const rrgoPc=v=>v==null?'—':fmt(100*v,0)+'%';
const rrgoBadge=l=>{const L=RRGO_L[l]||['—','',''];return `<span class="badge ${L[1]}" title="${esc(L[2])}">${esc(L[0])}</span>`};
function rrgoModel(){const m=marketData('history/rrg-transition-model');return m}

// which matrix a chart line reads (fixed in transition_rrg.PRIMARY): null = no model for this kind of line
function rrgoGroup(o,l){
 if(o.freq!=='w'||o.n!==14)return null;
 const e=l.e;
 if(e.benchC)return e.bx&&e.bi?'company_vs_industry':null;
 if(String(e.id).startsWith('ind:'))return null;            // an industry index (dual RRG): not one of the tested kinds
 const s=(o.D.series||[]).find(x=>x.id===e.id);
 if(s)return ['sector-etf','style-etf','site-sector'].includes(s.group)?'etf_vs_market':null;
 return o.D.tickers&&o.D.tickers[e.id]&&e.c?'company_vs_market':null;
}
// companies count only while liquid (transition_rrg.liquid): close ≥ $3 and ≥ $10M a week on average over 13 weeks
function rrgoLiquid(o,e,k){
 if(!e.v)return false;
 const G=rrgGrid(o.D),C=rrgFull(G,e,'c'),V=rrgFull(G,e,'v'),gi=G.w.idx[k];
 if(C[gi]==null||C[gi]<3)return false;
 let s=0,n=0;for(let j=Math.max(0,gi-12);j<=gi;j++)if(C[j]!=null&&V[j]!=null){s+=C[j]*V[j]*1000;n++}
 return n>=10&&s/n>=10e6;
}
// the line's state at week f: quadrant, heading of the last weekly step, the industry's quadrant (dual RRG)
function rrgoState(o,l,g,f){
 const c=l.calc,x=c.x[f],y=c.y[f];if(x==null||y==null)return null;
 const q=rrgQuad(x,y);let hd=-1,iq=-1;
 if(f>0&&c.x[f-1]!=null&&c.y[f-1]!=null){const dx=x-c.x[f-1],dy=y-c.y[f-1];hd=dx>=0?(dy>=0?0:1):(dy<0?2:3)}
 if(g==='company_vs_industry'){const e=l.e,ic=rrgCalc(o.D,{id:e.id+'|ind',start:e.start,c:e.bi},'w',14);if(ic.x[f]!=null&&ic.y[f]!=null)iq=rrgQuad(ic.x[f],ic.y[f])}
 return {q,hd,iq};
}
// the probabilities h weeks on: the group's primary head, its label, and the history behind the row
function rrgoOdds(M,g,st,h){
 const G=M.groups&&M.groups[g];if(!G||!st)return null;
 const head=G.primary==='iq'&&st.iq>=0?'iq':'q',H=(G.heads[head]||{})[h];if(!H)return null;
 const row=head==='iq'?4*st.iq+st.q:st.q,cnt=H.counts[row]||[],n=cnt.reduce((a,b)=>a+b,0);
 return {head,label:H.label,eval:H.eval,p:H.P[row],hist:n?cnt.map(v=>v/n):null,n};
}
// the weekly chain from the line's state: each quadrant's probability for weeks 1–13 and the five most common routes
function rrgoRng(seed){let a=seed>>>0;return ()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296}}
function rrgoChain(M,g,st,sims=20000){
 const G=M.groups&&M.groups[g];if(!G||!G.chain||!st)return null;
 const joint=G.chain.joint,s0=joint?(st.iq>=0?4*st.iq+st.q:-1):(st.hd>=0?4*st.q+st.hd:-1);if(s0<0)return null;
 const key=(M.generated_at||'')+'|'+g+'|'+s0;if(RRGO.paths.has(key))return RRGO.paths.get(key);
 const P=G.chain.P1.map(r=>{const t=r.reduce((a,b)=>a+b,0);return r.map(v=>v/t)}),qof=s=>joint?s%4:Math.floor(s/4);
 let v=new Array(16).fill(0);v[s0]=1;const marg=[];
 for(let k=1;k<=13;k++){const w=new Array(16).fill(0);for(let i=0;i<16;i++)if(v[i])for(let j=0;j<16;j++)w[j]+=v[i]*P[i][j];v=w;
  const q=[0,0,0,0];w.forEach((p,j)=>{q[qof(j)]+=p});marg.push(q)}
 const cum=P.map(r=>{let c=0;return r.map(p=>c+=p)}),rnd=rrgoRng(20261023+s0),cnt=new Map();
 for(let n=0;n<sims;n++){let s=s0;const seq=[qof(s)];
  for(let k=0;k<13;k++){const u=rnd(),c=cum[s];let j=0;while(j<15&&u>c[j])j++;s=j;if(qof(s)!==seq[seq.length-1])seq.push(qof(s))}
  const k=seq.join('');cnt.set(k,(cnt.get(k)||0)+1)}
 const paths=[...cnt.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([k,c])=>({q:[...k].map(Number),p:c/sims}));
 const lab=k=>G.chain.labels[k<=1?'1':k<=4?'4':'13'];
 const out={marg,paths,labels:marg.map((_,i)=>lab(i+1)),pathLabel:lab(13)};RRGO.paths.set(key,out);return out;
}
const rrgoPath=q=>q.map(i=>RRGO_N[i]).join(' → ')+(q.length===1?' (stays)':'');

// every chart line at the latest week: its model, state and odds (null for a line without one)
function rrgoRows(o,M){
 return o.lines.map(l=>{const g=rrgoGroup(o,l),c=l.calc;
  // the line's own last point: weekly files are refreshed in batches, so a line may end a week before the latest one
  let k=o.lastK;while(k>=0&&k>o.lastK-3&&(c.x[k]==null||c.y[k]==null))k--;
  const st=g&&k>o.lastK-3&&k>=0?rrgoState(o,l,g,k):null;
  const why=!g?(String(l.e.id).startsWith('ind:')?'industry index: not a tested kind of line':'no model for this kind of line'):!st?'no recent point':
   g!=='etf_vs_market'&&!rrgoLiquid(o,l.e,k)?'below the liquidity floor ($3, $10M a week)':(g==='company_vs_industry'&&st.iq<0?'no industry point that week':'');
  return {l,g,k,st,why,odds:why?null:Object.fromEntries(RRGO_H.map(([h])=>[h,rrgoOdds(M,g,st,h)]))}});
}

/* the panel under the chart */
function rrgOdds(o){
 if(o.freq!=='w'||o.n!==14)return '<div class="explain">Quadrant odds and paths are fitted for the weekly chart with the 14-week window.</div>';
 const m=rrgoModel();if(m.err)return '';if(!m.data)return '<div class="explain">Loading the quadrant odds…</div>';
 const M=m.data,h=rrgoH(),rows=rrgoRows(o,M),hl=RRGO_H.find(x=>x[0]===h)[1];
 const pick=rows.filter(r=>r.odds),sel=pick.find(r=>r.l.e.id===state.rrgp);
 let out=`<div class="panel"><h3>Quadrant odds and paths — ${esc(rrgDay(o.Q[o.lastK]))}</h3><p class="sub">Where each line stands ${esc(hl)} on, from how lines in the same spot moved before (weekly 14-week RRG, pairs since ${esc(rrgDay(((M.groups||{}).company_vs_market||(M.groups||{}).etf_vs_market||{}).from||'2002-01-04'))}). Each label was earned out of sample from ${esc(rrgDay(M.test_from))}: the odds had to beat “stays in its quadrant” and “the usual quadrant shares”. The matrix knows only where a line stands (and, in the dual RRG, where its industry stands), so lines in the same spot get the same odds. Lines marked History only or Too little data show past shares in grey, not a forecast. Rotation history, not investment advice.</p>`;
 out+=`<div class="toolbar">${field('rrgp','Draw on the chart',[['','Off'],...pick.map(r=>[r.l.e.id,r.l.e.name])],sel?state.rrgp:'')}${field('rrgh','Horizon',RRGO_H,h)}</div>`;
 if(state.rf!==o.lastK)out+=`<p class="sub">The odds are for the latest week only (the matrices are fitted on the whole history, so on an earlier week they would know what came after). The chart shows ${esc(rrgDay(o.Q[state.rf]))}; drag the slider to the end to see them drawn.</p>`;
 out+=table(['Line','Now','Model',...RRGO_N,'Check'],rows.map(r=>{const st=r.st,nm=`<i class="mk-key" style="background:${r.l.col}"></i> <b>${esc(r.l.e.name)}</b>`,
  now=st?`<span class="badge rrg-b-${RRGO_K[st.q]}">${RRGO_N[st.q]}</span>${st.iq>=0&&r.g==='company_vs_industry'?`<br><span class="muted">industry ${esc(RRGO_N[st.iq])}</span>`:''}${r.k<o.lastK?`<br><span class="muted">as of ${esc(rrgDay(o.Q[r.k]))}</span>`:''}`:'—';
  if(!r.odds)return [nm,now,`<span class="muted">${esc(r.why)}</span>`,'—','—','—','—','—'];
  const d=r.odds[h];if(!d)return [nm,now,esc(RRGO_GS[r.g]),'—','—','—','—','—'];
  const show=rrgoShown(d.label),v=show?d.p:d.hist,top=v?v.indexOf(Math.max(...v)):-1;
  return [nm,now,`<span title="${esc(RRGO_G[r.g])}">${esc(RRGO_GS[r.g])}</span>`,
   ...[0,1,2,3].map(j=>!v?'—':show?(j===top?`<b>${rrgoPc(v[j])}</b>`:rrgoPc(v[j])):`<span class="muted" title="history: ${esc(fmt(d.n))} line-weeks, not a forecast">${rrgoPc(v[j])}</span>`),rrgoBadge(d.label)]}));
 if(sel)out+=rrgoDetail(o,M,sel);
 else if(pick.length)out+=`<p class="sub">Pick a line in “Draw on the chart” for its odds at 1, 4 and 13 weeks, the week-by-week probabilities and its most common paths, drawn on the RRG.</p>`;
 return out+rrgoCheck(M)+'</div>';
}
function rrgoDetail(o,M,r){
 const name=r.l.e.name,G=M.groups[r.g],ch=rrgoChain(M,r.g,r.st);
 let out=`<h4>${esc(name)} — next quadrant (${esc(RRGO_G[r.g])})</h4>`;
 out+=table(['Horizon',...RRGO_N,'Check','Beats “stays put” by','Beats “usual shares” by','Calibration error'],RRGO_H.map(([h,hl])=>{const d=r.odds[h];if(!d)return [hl,'—','—','—','—','—','—','—','—'];
  const show=rrgoShown(d.label),v=show?d.p:d.hist,e=d.eval||{},sk=a=>Array.isArray(a)?`${fmt(100*a[0],1)}% <span class="muted">[${fmt(100*a[1],1)}, ${fmt(100*a[2],1)}]</span>`:'—';
  return [hl,...[0,1,2,3].map(j=>!v?'—':show?rrgoPc(v[j]):`<span class="muted">${rrgoPc(v[j])}</span>`),rrgoBadge(d.label),sk(e.brier_skill_vs_stay),sk(e.brier_skill_vs_freq),e.ece==null?'—':fmt(100*e.ece,1)+' pts']}));
 out+=`<p class="sub">“Beats … by”: the Brier score's improvement out of sample, with its 95% interval over ${esc(fmt(((r.odds['4']||{}).eval||{}).origins))} non-overlapping four-week origins (1 week: every week; 13 weeks: every 13). The matrix row behind these odds: ${esc(fmt((r.odds[rrgoH()]||{}).n))} past line-weeks in the same spot.</p>`;
 if(!ch)return out+'<p class="sub">No week-by-week path for this line this week (its last step or its industry point is missing).</p>';
 // week by week: stacked bars from the chain, weeks whose chain check failed left empty
 const Wd=Math.min(680,rotSize(.3,160,220)[0]),Ht=170,L=34,R=8,T=10,B=26,bw=(Wd-L-R)/13;
 let s=`<svg class="plot mk-plot" viewBox="0 0 ${Wd} ${Ht}" style="max-width:${Wd}px" role="img" aria-label="Each quadrant's probability for weeks 1 to 13 for ${esc(name)}">`;
 [0,.5,1].forEach(v=>{const y=T+(1-v)*(Ht-T-B);s+=`<line class="mk-grid" x1="${L}" x2="${Wd-R}" y1="${y}" y2="${y}"/><text class="axis" x="${L-6}" y="${y+4}" text-anchor="end">${fmt(100*v,0)}%</text>`});
 ch.marg.forEach((q,i)=>{const x=L+i*bw+2,shown=rrgoShown(ch.labels[i]);let y=Ht-B;
  if(shown)q.forEach((p,j)=>{const hh=p*(Ht-T-B);y-=hh;s+=`<g data-tip="${tip([[name+' · week '+(i+1),RRGO_L[ch.labels[i]][0]],...q.map((v,jj)=>[rrgoPc(v),RRGO_N[jj]])])}" class="mk-hit"><rect class="rrg-t-${RRGO_K[j]}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw-4).toFixed(1)}" height="${Math.max(0,hh).toFixed(1)}" opacity=".78"/></g>`});
  else s+=`<rect class="mk-grid" x="${x.toFixed(1)}" y="${T}" width="${(bw-4).toFixed(1)}" height="${Ht-T-B}" fill="none" stroke-dasharray="3 3"/>`;
  s+=`<text class="axis" x="${(x+bw/2-2).toFixed(1)}" y="${Ht-8}" text-anchor="middle">${i+1}</text>`});
 out+=`<h4>Week by week — each quadrant's probability (the weekly chain)</h4>${s}</svg><div class="mk-legend">${RRGO_N.map((n,j)=>`<span><i class="mk-key rrg-k-${RRGO_K[j]}"></i>${n}</span>`).join('')}<span class="muted">weeks ahead → · check: week 1 ${esc(RRGO_L[ch.labels[0]][0])}, 2–4 ${esc(RRGO_L[ch.labels[3]][0])}, 5–13 ${esc(RRGO_L[ch.labels[12]][0])}</span></div>`;
 out+=`<p class="sub">The chain steps one week at a time from ${G.chain.joint?'where the company and its industry stand together':'the quadrant and the direction of the last weekly step'}. At 1, 4 and 13 weeks the direct matrix above was checked on its own and is the number to use; the chain fills the weeks between and gives the routes.</p>`;
 if(rrgoShown(ch.pathLabel))out+=`<h4>Most common paths over the next 13 weeks</h4>`+table(['Path (quadrants in the order visited)','Share of 20,000 simulated paths'],ch.paths.map(p=>[esc(rrgoPath(p.q)),rrgoPc(p.p)]))+`<p class="sub">Simulated from the weekly chain (check at 13 weeks: ${esc(RRGO_L[ch.pathLabel][0])}). The three most common are drawn on the chart.</p>`;
 else out+=`<p class="sub">Paths are not shown: the weekly chain did not pass its check at 13 weeks (${esc(RRGO_L[ch.pathLabel][0])}).</p>`;
 return out;
}
// how each head did out of sample, every group and horizon
function rrgoCheck(M){
 const sk=a=>Array.isArray(a)?`${fmt(100*a[0],1)}% <span class="muted">[${fmt(100*a[1],1)}, ${fmt(100*a[2],1)}]</span>`:'—',rows=[];
 for(const [g,G] of Object.entries(M.groups||{})){
  for(const [hd,byH] of Object.entries(G.heads||{}))for(const [h,x] of Object.entries(byH)){const e=x.eval||{};
   rows.push([esc(RRGO_G[g]||g),esc(RRGO_HEAD[hd]||hd)+(hd===G.primary?' <b>(used)</b>':''),h,fmt(e.origins),fmt(e.predictions),sk(e.brier_skill_vs_stay),sk(e.brier_skill_vs_freq),e.ece==null?'—':fmt(100*e.ece,1)+' pts',rrgoBadge(x.label)])}
  for(const [h,e] of Object.entries((G.chain||{}).eval||{}))rows.push([esc(RRGO_G[g]||g),'Weekly chain (paths)',h,fmt(e.origins),fmt(e.predictions),sk(e.brier_skill_vs_stay),sk(e.brier_skill_vs_freq),e.ece==null?'—':fmt(100*e.ece,1)+' pts',rrgoBadge(e.label)]);
 }
 return `<details class="fc-score"><summary>How the odds were checked (walk-forward from ${esc(rrgDay(M.test_from))})</summary><p class="sub">At each test week only pairs whose outcome was already known counted; test weeks are spaced by the horizon so no two overlap. Score: the multiclass Brier score against two baselines from the same history — the line stays in its quadrant, and the usual quadrant shares — with a 95% bootstrap interval over test weeks; calibration error: how far stated probabilities sat from what happened (average over the four quadrants, 10 bins). Labels fixed before the results: Calibrated = beats both, intervals above zero, error ≤ 2 points; Experimental = beats both but not all of that; History only = loses to one; Too little data = under 50 test weeks or 2,000 predictions. ${esc(M.note||'')}</p>`+
  table(['Lines','Model','Weeks ahead','Test weeks','Predictions','Beats “stays put” by','Beats “usual shares” by','Calibration error','Label'],rows)+'</details>';
}

/* on the chart: the selected line's odds in each quadrant's corner and its three most common paths */
function rrgOddsLayer(o,f,sx,sy){
 if(!state.rrgp||f!==o.lastK||o.freq!=='w'||o.n!==14)return '';
 const m=rrgoModel();if(!m.data)return '';
 const M=m.data,r=rrgoRows(o,M).find(x=>x.l.e.id===state.rrgp&&x.odds);if(!r)return '';
 const h=rrgoH(),d=r.odds[h],c=r.l.calc,p0=[sx(c.x[r.k]),sy(c.y[r.k])],{x:xd,y:yd}=o.dom,hl=RRGO_H.find(x=>x[0]===h)[1];
 let s='';
 if(d&&rrgoShown(d.label)){
  const at=[[sx(xd[1])-8,sy(yd[1])+34,'end'],[sx(xd[1])-8,sy(yd[0])-28,'end'],[sx(xd[0])+8,sy(yd[0])-28,'start'],[sx(xd[0])+8,sy(yd[1])+34,'start']];
  d.p.forEach((p,j)=>{const [x,y,an]=at[j];s+=`<g data-tip="${tip([[r.l.e.name+' · '+hl+' on',RRGO_L[d.label][0]],[rrgoPc(p),'in '+RRGO_N[j]]])}" class="mk-hit"><text class="rrg-qt rrg-t-${RRGO_K[j]}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${an}">${esc(r.l.e.name)} ${rrgoPc(p)}</text></g>`});
  s+=`<text class="axis" x="${(sx(xd[1])-8).toFixed(1)}" y="${(sy(yd[1])+50).toFixed(1)}" text-anchor="end">${esc(hl)} on · ${esc(RRGO_L[d.label][0])}</text>`;
 }
 const ch=rrgoChain(M,r.g,r.st);
 if(ch&&rrgoShown(ch.pathLabel)){
  const mid=j=>[100+(j===0||j===1?.5:-.5)*(xd[1]-100),100+(j===0||j===3?.5:-.5)*(yd[1]-100)];
  ch.paths.slice(0,3).forEach((pt,i)=>{if(pt.q.length<2)return;const off=(i-1)*14;
   const pts=[p0,...pt.q.slice(1).map(j=>{const [x,y]=mid(j);return [sx(x)+off,sy(y)+off]})],e=pts[pts.length-1],b=pts[pts.length-2],a=Math.atan2(e[1]-b[1],e[0]-b[0]),w=1.2+6*pt.p;
   s+=`<g data-tip="${tip([[r.l.e.name+' · path '+(i+1)+' of the next 13 weeks',RRGO_L[ch.pathLabel][0]],[rrgoPath(pt.q),rrgoPc(pt.p)+' of simulated paths']])}" class="mk-hit"><path class="rot-line rrgo-path" d="${curve(pts,true)}" style="stroke:${r.l.col};stroke-width:${w.toFixed(1)}"/>`+
    `<path style="fill:${r.l.col}" d="M${e[0].toFixed(1)},${e[1].toFixed(1)} L${(e[0]-9*Math.cos(a-.45)).toFixed(1)},${(e[1]-9*Math.sin(a-.45)).toFixed(1)} L${(e[0]-9*Math.cos(a+.45)).toFixed(1)},${(e[1]-9*Math.sin(a+.45)).toFixed(1)} Z"/>`+
    `<text class="mk-label mk-halo" x="${(e[0]+6).toFixed(1)}" y="${(e[1]-6).toFixed(1)}">${i+1}: ${rrgoPc(pt.p)}</text></g>`});
 }
 return s;
}
