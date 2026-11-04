/* Rotation → Hybrid RRG: the RRG blended with the signals it leaves out — momentum, reversal, volatility and volume —
   weighted by how well each has ranked the lines that went on to beat SPY, tested walk-forward against the classic RRG
   since 2012 and frozen every week. Data: data/market/history/rrg-hybrid.json and rrg-hybrid-companies.json
   (app/rrg_hybrid.py, branch rotation-history). The chart's x is the 13-week forecast and y the 4-week forecast, each
   ranked within the week (100 + z), so the quadrants keep the RRG's names but read as forecasts. */
(function(){
const H={d:null,err:null,loading:null,co:null,coErr:null,coLoading:null,mode:'hybrid',q:'',panel:'funds',h:'13'};
const HQ=[['Leading','#1baf7a'],['Weakening','#c98a00'],['Lagging','#d1495b'],['Improving','#2a78d6']];
const HB={rrg:'RRG geometry',momentum:'Momentum & volatility',volume:'Volume'};
const base='data/market/history/';
function get(name,ok,fail){if(typeof fetch!=='function'){fail('no fetch');return}fetch(base+name,{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(ok).catch(e=>fail(e.message))}
function load(){
 if(H.d||H.err||H.loading)return;
 H.loading=true;get('rrg-hybrid.json',d=>{H.d=d;H.loading=false;typeof render==='function'&&render()},e=>{H.err=e;H.loading=false;typeof render==='function'&&render()});
}
function loadCo(){
 if(H.co||H.coErr||H.coLoading)return;
 H.coLoading=true;get('rrg-hybrid-companies.json',d=>{H.co=d;H.coLoading=false;typeof render==='function'&&render()},e=>{H.coErr=e;H.coLoading=false;typeof render==='function'&&render()});
}
const e_=s=>typeof esc==='function'?esc(s):String(s==null?'':s);
const f_=(v,d=0)=>v==null?'—':(typeof fmt==='function'?fmt(v,d):Number(v).toFixed(d));
const pct=(v,d=0)=>v==null?'—':f_(v*100,d)+'%';
const spct=(v,d=1)=>v==null?'—':(v>0?'+':v<0?'−':'')+f_(Math.abs(v*100),d)+'%';
const rel=(v,d=1)=>v==null?'—':spct(Math.exp(v)-1,d);
const quad=(x,y)=>x==null||y==null?-1:x>=100?(y>=100?0:1):(y>=100?3:2);
const qtag=(k)=>k<0?'—':`<span style="color:${HQ[k][1]};font-weight:600">${HQ[k][0]}</span>`;
const tbl=(h,rows)=>typeof table==='function'?table(h,rows):`<table><tr>${h.map(x=>`<th>${x}</th>`).join('')}</tr>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
const note=t=>`<p class="muted" style="font-size:.82rem;max-width:940px">${t}</p>`;
const sec=(t,sub)=>`<div class="section-head"><h3>${t}</h3>${sub?`<span class="muted">${sub}</span>`:''}</div>`;
const icTxt=s=>s?`${f_(s.ic,3)} <span class="muted">(t ${f_(s.t,1)})</span>`:'—';

/* the chart: funds on the hybrid (or classic) RRG with their 8-week tails */
function chart(rows,mode){
 const W=640,Hh=520,L=46,R=14,T=14,B=38,lo=96,hi=104;
 const X=v=>L+(Math.max(lo,Math.min(hi,v))-lo)/(hi-lo)*(W-L-R),Y=v=>T+(1-(Math.max(lo,Math.min(hi,v))-lo)/(hi-lo))*(Hh-T-B);
 const col=['#2a78d6','#eb6834','#1baf7a','#a24fd0','#c98a00','#d1397d','#3aa6b9','#7d8a1f','#b8522b','#5a6ad0','#8a8a84','#2f9e44'];
 let s=`<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;max-width:${W}px" role="img" aria-label="${mode==='hybrid'?'Hybrid':'Classic'} RRG of the sector and style funds">`;
 const bg=[[100,hi,100,hi,0],[100,hi,lo,100,1],[lo,100,lo,100,2],[lo,100,100,hi,3]];
 for(const [x0,x1,y0,y1,k] of bg)s+=`<rect x="${X(x0)}" y="${Y(y1)}" width="${X(x1)-X(x0)}" height="${Y(y0)-Y(y1)}" fill="${HQ[k][1]}" opacity="0.07"/>`;
 s+=`<line x1="${X(100)}" x2="${X(100)}" y1="${T}" y2="${Hh-B}" stroke="var(--muted,#999)" stroke-width="0.8"/><line x1="${L}" x2="${W-R}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--muted,#999)" stroke-width="0.8"/>`;
 for(let v=97;v<=103;v++){s+=`<text x="${X(v)}" y="${Hh-B+14}" font-size="10" text-anchor="middle" fill="var(--muted,#777)">${v}</text><text x="${L-6}" y="${Y(v)+3}" font-size="10" text-anchor="end" fill="var(--muted,#777)">${v}</text>`}
 s+=`<text x="${X(hi)-4}" y="${T+14}" font-size="12" text-anchor="end" fill="${HQ[0][1]}" font-weight="600">Leading</text><text x="${X(hi)-4}" y="${Hh-B-6}" font-size="12" text-anchor="end" fill="${HQ[1][1]}" font-weight="600">Weakening</text>`;
 s+=`<text x="${L+4}" y="${Hh-B-6}" font-size="12" fill="${HQ[2][1]}" font-weight="600">Lagging</text><text x="${L+4}" y="${T+14}" font-size="12" fill="${HQ[3][1]}" font-weight="600">Improving</text>`;
 s+=`<text x="${(L+W-R)/2}" y="${Hh-6}" font-size="11" text-anchor="middle" fill="var(--muted,#777)">${mode==='hybrid'?'13-week forecast vs SPY, ranked (100 = the funds\' average) →':'JdK RS-Ratio (14 weeks) →'}</text>`;
 s+=`<text x="12" y="${(T+Hh-B)/2}" font-size="11" text-anchor="middle" fill="var(--muted,#777)" transform="rotate(-90 12 ${(T+Hh-B)/2})">${mode==='hybrid'?'4-week forecast, ranked →':'JdK RS-Momentum →'}</text>`;
 rows.forEach((r,i)=>{
  const tl=(r.tail||{})[mode];if(!tl)return;const c=col[i%col.length];
  const pts=tl[0].map((x,j)=>x!=null&&tl[1][j]!=null?[X(x),Y(tl[1][j])]:null).filter(Boolean);
  if(pts.length>1)s+=`<polyline points="${pts.map(p=>p.map(v=>v.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="${c}" stroke-width="1.4" opacity="0.6"/>`;
  const last=pts[pts.length-1];if(!last)return;
  const spike=r.volume_x!=null&&r.volume_x>=2;
  s+=`<circle cx="${last[0]}" cy="${last[1]}" r="5" fill="${c}"${spike?' stroke="#111" stroke-width="2"':''}><title>${e_(r.id)} — ${e_(r.name)}: 13-week ${rel((r.h13||{}).rel)} vs SPY, P(beat) ${pct((r.h13||{}).p)}${spike?' · volume in the '+vweek()+': '+f_(r.volume_x,1)+'× its 13-week average':''}</title></circle>`;
  s+=`<text x="${last[0]+7}" y="${last[1]+4}" font-size="11" fill="${c}">${e_(r.id)}</text>`;
 });
 return s+'</svg>';
}
function rowCells(r){
 const h13=r.h13||{},h4=r.h4||{},h1=r.h1||{},hq=quad(r.hybrid[0],r.hybrid[1]),cq=quad(r.classic[0],r.classic[1]);
 const mix=r.mix13||{},m=Object.entries(mix).filter(x=>x[1]!=null).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1]))[0];
 return [`<b>${e_(r.id)}</b><br><span class="muted">${e_(r.name||'')}</span>`,qtag(hq),qtag(cq),rel(h13.rel),pct(h13.p),
  h13.price_lo!=null?`$${f_(h13.price_lo,2)} – $${f_(h13.price_hi,2)}`:'—',rel(h4.rel),pct(h4.p),pct(h1.p),
  r.volume_x==null?'—':(r.volume_x>=2?`<b>${f_(r.volume_x,1)}×</b>`:r.volume_x<=0.6?`${f_(r.volume_x,1)}× (quiet)`:`${f_(r.volume_x,1)}×`),
  m?`${e_(HB[m[0]]||m[0])} ${rel(m[1],1)}`:'—'];
}
const vweek=()=>H.d&&H.d.volume_week?`week ending ${e_(H.d.volume_week)}`:'last full week';   // volume runs a week behind the prices, as in the tests
const rowHead=()=>['Line','Hybrid','Classic','13 weeks vs SPY','P(beat), 13w','13-week price, 80%','4 weeks vs SPY','P(beat), 4w','P(beat), 1w',`Volume, ${vweek()}`,'Biggest driver (13w)'];

function scoreTable(P){
 const S=P.scores||{};
 const rows=Object.values(S).map(s=>{const I=s.ic||{},b=s.best_minus_worst,bv=s.best_minus_worst_vol_neutral,bc=s.best_minus_worst_classic,t=s.top_fifth_vs_spy;
  return [s.h+(s.h===1?' week':' weeks'),icTxt(I.hybrid),icTxt(I.classic),icTxt(I.momentum_12_1),icTxt(I.rrg),icTxt(I.momentum),icTxt(I.volume),
   b?`${spct(b.mean,2)} <span class="muted">(t ${f_(b.t,1)}; ${pct(b.hit)} of periods)</span>`:'—',bv?`${spct(bv.mean,2)} <span class="muted">(t ${f_(bv.t,1)})</span>`:'—',bc?spct(bc.mean,2):'—',
   t?`${spct(t.mean,2)} <span class="muted">(${pct(t.share_beating)} beat SPY)</span>`:'—',
   s.beat_spy&&s.beat_spy.brier_skill!=null?`${s.beat_spy.brier_skill>=0?'+':'−'}${f_(Math.abs(s.beat_spy.brier_skill*100),2)}%`:'—',pct(s.range80)]});
 return tbl(['Horizon','Rank corr.: hybrid','… classic RRG','… 12-1 momentum alone','… RRG block','… momentum block','… volume block','Best − worst fifth, net','… within volatility fifths','… classic RRG','Top fifth vs SPY, net','P(beat): Brier skill','80% range held'],rows);
}
function bars(vals,labels,fmtv,title){
 if(!vals.length)return '';
 const W=Math.max(260,vals.length*44),Hh=150,T=14,B=26,mx=Math.max(...vals.map(v=>Math.abs(v||0)),1e-9),bw=(W-20)/vals.length,Y0=T+(Hh-T-B)/2;
 let s=`<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;max-width:${W}px" role="img" aria-label="${e_(title)}"><line x1="10" x2="${W-10}" y1="${Y0}" y2="${Y0}" stroke="var(--muted,#999)" stroke-width="0.8"/>`;
 vals.forEach((v,i)=>{if(v==null)return;const h=Math.abs(v)/mx*((Hh-T-B)/2),x=10+i*bw+3;
  s+=`<rect x="${x}" y="${v>=0?Y0-h:Y0}" width="${bw-6}" height="${h}" fill="${v>=0?'#1baf7a':'#d1495b'}" opacity="0.8"><title>${e_(labels[i])}: ${fmtv(v)}</title></rect><text x="${x+(bw-6)/2}" y="${Hh-8}" font-size="10" text-anchor="middle" fill="var(--muted,#777)">${e_(labels[i])}</text>`});
 return s+'</svg>';
}
function describeTable(P,kind){
 const D=(P.describe||[]).filter(r=>r.kind===kind||(kind==='quadrant'&&r.kind==='quadrant_volume'));
 const names=[...new Set(D.map(r=>r.group))];
 return tbl(['After …','1 week','4 weeks','13 weeks',`13 weeks, ${EARLY_TXT}`,'Share of line-weeks'],names.map(n=>{const g=h=>D.find(r=>r.group===n&&r.h===h);
  const c=h=>{const r=g(h);return r?`<span class="${r.rel>0?'positive':r.rel<0?'negative':''}">${spct(r.rel,2)}</span> <span class="muted">(t ${f_(r.t,1)})</span>`:'—'};
  const ce=()=>{const r=(g(13)||{}).early;return r?`<span class="${r.rel>0?'positive':r.rel<0?'negative':''}">${spct(r.rel,2)}</span> <span class="muted">(t ${f_(r.t,1)})</span>`:'—'};
  const sh=(g(1)||g(4)||g(13)||{}).share_of_weeks;return [e_(n),c(1),c(4),c(13),ce(),sh==null?'—':pct(sh,1)]}));
}
const EARLY_TXT='2004–2011';
function earlyLine(C){                                    // did the patterns hold before the years they were found in?
 const E=(C.describe||[]).filter(r=>r.h===13&&r.early);
 if(!E.length)return '';
 const big=E.filter(r=>Math.abs(r.early.t)>=2).length,same=E.filter(r=>Math.sign(r.early.rel)===Math.sign(r.rel)).length;
 return `The ${EARLY_TXT} column is the years before: ${big?`${big} of the ${E.length} reached a t of 2 there`:'none reached a t of 2 there'}, and ${same} of ${E.length} pointed the same way — read these as what recent years have done more than as a rule.`;
}
function ledgerTable(Lg){
 if(!Lg)return note('The ledger starts with the first closed week after this page went live.');
 return tbl(['Panel · horizon','Weeks resolved','Waiting','Rank corr.','Best − worst fifth','P(beat): Brier skill'],Object.entries(Lg).map(([k,s])=>[e_(k.replace(':',' · ')+' weeks'),f_(s.resolved_weeks),f_(s.pending_weeks),s.ic==null?'—':f_(s.ic,3),s.best_minus_worst==null?'—':spct(s.best_minus_worst,2),s.brier_skill==null?'—':f_(s.brier_skill,3)]));
}

function moneyLine(C){                                   // a better ranking is not yet money: say what a basket made
 const s=((C||{}).scores||{})['13']||{},b=s.best_minus_worst,bc=s.best_minus_worst_classic,d1=(s.deciles||[])[0];
 if(!b)return '';
 return `Ranking is not the same as money: buying the companies it ranked in the best fifth and selling the worst fifth, 13 weeks at a time, made ${spct(b.mean,2)} a quarter after trading costs${b.gross!=null?` (${spct(b.gross,2)} before)`:''}${bc?`; the classic RRG's own basket made ${spct(bc.mean,2)} (t ${f_(bc.t,1)})${Math.abs(bc.t)<2&&Math.abs(b.t)<2?' — neither is reliable':''}`:''}. The wild names it ranks lowest usually trail, but the few that rebound rebound hard${d1?`: the tenth it ranked lowest trailed SPY by ${f_(Math.abs(d1.rel*100),1)}% a quarter on average and still beat it ${pct(d1.beat)} of the time`:''}. `;
}
function html(){
 const d=H.d,F=(d.panels||{}).funds||{},C=(d.panels||{}).companies||{};
 const fs=((F.scores||{})['13']||{}).ic||{},cs=((C.scores||{})['13']||{}).ic||{};
 let out=`<div class="explain">The classic RRG shows where a line stands against SPY and which way it is turning; it was not built to say which lines will beat SPY next — and tested on that since ${d.test_from}, it barely does: ranking companies by it gave a rank correlation with the next 13 weeks of ${f_((cs.classic||{}).ic,3)} (funds ${f_((fs.classic||{}).ic,3)}). The hybrid blends the RRG with momentum, reversal, volatility and volume, each block weighted by how well it ranked the lines in earlier years: ${f_((cs.hybrid||{}).ic,3)} for companies (funds ${f_((fs.hybrid||{}).ic,3)}). ${moneyLine(C)}Every number below is out of sample, each year predicted by fits on the years before it, after trading costs. History and models, not investment advice.</div>`;
 out+=`<div class="toolbar"><div class="field"><label for="hyb-mode">Chart</label><select id="hyb-mode"><option value="hybrid"${H.mode==='hybrid'?' selected':''}>Hybrid RRG (forecasts)</option><option value="classic"${H.mode==='classic'?' selected':''}>Classic RRG (14 weeks)</option></select></div></div>`;
 out+=sec('Sector and style funds',`week ending ${e_(d.asof)} · tails: 8 weeks · ringed: volume in the ${vweek()} at least twice its 13-week average`);
 out+=chart(F.rows||[],H.mode);
 out+=tbl(rowHead(),(F.rows||[]).slice().sort((a,b)=>((b.h13||{}).rel||-9)-((a.h13||{}).rel||-9)).map(rowCells));
 out+=note(`Price ranges add SPY's average weekly return of the last ten years (${spct(F.spy_drift_week,2)} a week) to the relative forecast; the market's own direction is not forecast here. "Biggest driver": the block contributing most to the 13-week forecast. The return vs SPY is the panel's average of the last five years plus the hybrid; the chance of beating SPY and the 80% range come from the hybrid's errors in those years (for companies, the errors of lines in the same volatility fifth). Volume is read a week behind the prices, as in the tests. Hybrid quadrants read as forecasts: Leading — both the quarter and the month ahead of the funds' average; Weakening — the quarter ahead, the month behind; Improving — the month ahead, the quarter behind.`);
 out+=sec('Companies',`${f_(C.now)} liquid companies this week · the 25 best and worst by the 13-week forecast, or type a ticker`);
 out+=`<div class="toolbar"><div class="field wide"><label for="hyb-q">Ticker</label><input id="hyb-q" value="${e_(H.q)}" placeholder="e.g. NVDA, BAC · Enter"></div></div>`;
 let crow=C.rows||[];
 if(H.q){loadCo();const qs=H.q.toUpperCase().split(/[\s,]+/).filter(Boolean);
  if(H.co)crow=(H.co.rows||[]).filter(r=>qs.includes(String(r.id).toUpperCase()));
  else if(H.coErr)out+=note('The full company list could not load ('+e_(H.coErr)+').');else out+=note('Loading every company…')}
 out+=crow.length?tbl(rowHead(),crow.map(rowCells)):note(H.q?'No liquid company with that ticker this week (≥ $3 and ≥ $10M traded a week).':'');
 out+=sec('How it has done','out of sample from '+d.test_from+', after trading costs');
 for(const [k,P,lab] of [['funds',F,'Funds'],['companies',C,'Companies']]){
  if(!P.scores)continue;
  out+=`<h4 style="margin:12px 0 4px;font-size:14px">${lab} (${f_(P.lines)} lines)</h4>`+scoreTable(P);
  const s13=(P.scores||{})['13']||{},dec=s13.deciles||[],yr=s13.ic_by_year||{};
  out+=`<div class="fv-two" style="display:flex;flex-wrap:wrap;gap:16px"><div style="flex:1;min-width:260px"><div class="muted" style="font-size:.8rem">13 weeks: return vs SPY by decile of the hybrid forecast (1 = lowest), average per period, simple returns before costs</div>${bars(dec.map(x=>x.rel),dec.map(x=>String(x.decile)),v=>spct(v,2),'Deciles')}</div>`;
  out+=`<div style="flex:1;min-width:260px"><div class="muted" style="font-size:.8rem">Rank correlation with the next 13 weeks, by year: hybrid (bars)${''}</div>${bars(Object.values(yr).map(v=>v[0]),Object.keys(yr).map(y=>y.slice(2)),v=>f_(v,3),'By year')}</div></div>`;
  const bv=s13.range80_by_vol||[],bs=(s13.beat_spy||{}).bias,cal=P.calibration||{};
  if(bv.length)out+=note(`13 weeks: the 80% range held ${bv.map(v=>pct(v)).join(' · ')} of the time from the calmest fifth of ${k==='funds'?'funds':'companies'} by volatility to the wildest${bs!=null?`; P(beat SPY) averaged ${f_(Math.abs(bs*100),1)} points ${bs>=0?'above':'below'} the share that did`:''}. Both are set from the last ${f_(cal.years||5)} years of out-of-sample errors${cal.vol_groups>1?', kept apart by volatility fifth':''}.`);
  const wn=P.weights_now||{};out+=note(`Block weights now (stacked on earlier out-of-sample forecasts; 1 = the block's own forecast taken as it is): `+Object.entries(wn).map(([h,w])=>`${h} weeks — `+Object.entries(w).map(([b,v])=>`${e_(HB[b]||b)} ${f_(v,2)}`).join(', ')).join(' · ')+'.');
 }
 out+=note(`Rank correlation: between the forecast and the next return vs SPY across the panel, every week, averaged (t over non-overlapping weeks). Best − worst fifth: buy the fifth with the highest forecast, sell the lowest fifth, hold for the horizon, on non-overlapping periods ("within volatility fifths": the same inside each fifth of companies by volatility, so calm names are bought against calm ones and wild against wild); costs one way by weekly dollar volume (${(d.costs_bp||[]).map(c=>`${f_(c[1])} bp above $${f_(c[0]/1e6)}M`).join(', ')}). Returns of baskets are simple returns (what an equal-weighted basket earns), not log returns, which would count a volatile line's swings as a loss; no borrow fee is charged for the sold fifth (small, volatile names can cost far more to borrow). Today's companies only: delisted names are missing.`);
 out+=sec('What the classic quadrants and volume have been followed by','companies; simple return vs the average company that week, '+d.test_from+' on');
 out+=describeTable(C,'quadrant')+describeTable(C,'volume');
 out+=note('An RRG is usually read as: buy Improving, sell Weakening. Since '+d.test_from+' the quadrants have read the other way round over 13 weeks, and a week of unusually heavy volume — up or down — has been followed by lagging returns (counted from the week after it), more so in the Improving and Leading quadrants; so has an unusually quiet week. Spikes include earnings, mergers (a target\'s price then stops moving), offerings and index changes. '+earlyLine(C));
 out+=sec('Frozen record','each closed week\'s forecasts written once, scored when the outcome is known');
 out+=ledgerTable(d.ledger);
 return out;
}
function render_(el){
 load();
 if(H.err){el.innerHTML=(typeof empty==='function'?empty:(t=>t))(`The Hybrid RRG could not load (${H.err}). It is rebuilt with the weekly closes by .github/workflows/rotation-history.yml (app/rrg_hybrid.py).`);return}
 if(!H.d){el.innerHTML=(typeof empty==='function'?empty:(t=>t))('Loading the Hybrid RRG…');return}
 el.innerHTML=html();
 const m=el.querySelector('#hyb-mode');if(m)m.onchange=e=>{H.mode=e.target.value;render_(el)};
 const q=el.querySelector('#hyb-q');if(q){q.onchange=e=>{H.q=e.target.value.trim();render_(el)};q.onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
}
const api={render:render_,_html:html,_chart:chart,_state:H};
if(typeof window!=='undefined')window.RRGHybrid=api;
if(typeof module!=='undefined')module.exports=api;
})();
