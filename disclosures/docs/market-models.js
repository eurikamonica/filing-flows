/* Market models — the hub tab: six forecasts of the market as a whole, each tested walk-forward against a simple benchmark
   and published only as far as it has worked out of sample before: volatility (HAR, with the VIX where it exists), the
   six index funds (SPY, QQQ, DIA, MDY, IWM, IJR) against their centre, the market's regime (a three-state hidden Markov
   model), the sector funds against SPY, spreads (ratios, credit and the curve) and SPY over cash.
   Data: data/market/history/market-models.json (rotation-history; app/market_models.py).
   Deep links: #mmodels, #mmodels/vol, #mmodels/indices, #mmodels/regime, #mmodels/sectors, #mmodels/spreads,
   #mmodels/market, #mmodels/record. */
(function(){
const mmStore={};
function mmData(){
 const m=mmStore.d||(mmStore.d={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/market/history/market-models.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const MM_VIEWS=[['overview','Overview'],['vol','Volatility'],['indices','Six indices'],['regime','Market regime'],['sectors','Sectors'],['spreads','Spreads'],['market','Market direction'],['record','Track record']];
const MM_STATE_COL=['#3f8f5f','#c99a2e','#c4524b'];
function mmP(v,d=0){return v==null?'—':fmt(v*100,d)+'%'}
function mmS(v,d=1){return v==null?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)+'%'}
function mmN(v,d=2){return v==null?'—':(v<0?'−':'')+fmt(Math.abs(v),d)}
function mmRet(v,d=1){return v==null?'—':mmS(Math.exp(v)-1,d)}
function mmSkill(s){
 if(s==null)return '<span class="muted">not enough outcomes</span>';
 const t=s>0.01?'better than the base rate':s<-0.01?'worse than the base rate':'no better than the base rate';
 return `${(s>=0?'+':'−')+fmt(Math.abs(s*100),1)}% <span class="muted">(${t})</span>`;
}
function mmGain(g){
 if(g==null)return '—';
 return `<span class="${g>0.02?'positive':g<-0.02?'negative':''}">${(g>=0?'+':'−')+fmt(Math.abs(g*100),0)}%</span>`;
}
function mmNote(t){return `<p class="muted" style="font-size:.82rem;max-width:920px">${t}</p>`}
function mmSec(t,sub){return `<div class="section-head"><h3>${t}</h3>${sub?`<span class="muted">${sub}</span>`:''}</div>`}

/* charts: stacked regime probabilities, a spread's line */
function mmStack(hist){
 const P=(hist&&hist.p)||[];if(P.length<10)return '';
 const W=900,H=150,L=4,R=4,T=6,B=20,n=P.length,X=i=>L+i/(n-1)*(W-L-R),Y=v=>T+(1-v)*(H-T-B);
 const start=new Date(hist.start+'T00:00:00Z');
 let s=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px" role="img" aria-label="Probability of each market state by week">`;
 const cum=P.map(r=>{const a=r.map(v=>v==null?0:v);return [a[0],a[0]+a[1],1]});
 for(let k=2;k>=0;k--){
  const top=cum.map((c,i)=>`${X(i).toFixed(1)},${Y(c[k]).toFixed(1)}`).join(' ');
  const bot=k?cum.map((c,i)=>`${X(i).toFixed(1)},${Y(c[k-1]).toFixed(1)}`).reverse().join(' '):`${X(n-1)},${Y(0)} ${X(0)},${Y(0)}`;
  s+=`<polygon points="${top} ${bot}" fill="${MM_STATE_COL[k]}" opacity="0.75"/>`;
 }
 for(let y=start.getUTCFullYear()+1;y<=new Date().getUTCFullYear();y+=2){
  const i=Math.round((Date.UTC(y,0,1)-start.getTime())/(7*864e5));if(i<0||i>=n)continue;
  s+=`<line x1="${X(i)}" x2="${X(i)}" y1="${T}" y2="${H-B}" stroke="var(--line,#ccc)" stroke-width="0.6"/><text x="${X(i)}" y="${H-6}" font-size="10" text-anchor="middle" fill="var(--muted,#777)">${y}</text>`;
 }
 return s+'</svg>';
}
function mmLine(h,unit){
 const xs=(h&&h.x)||[];const v=xs.filter(x=>x!=null);if(v.length<10)return '';
 const W=220,H=46,lo=Math.min(...v),hi=Math.max(...v),n=xs.length,X=i=>2+i/(n-1)*(W-4),Y=x=>3+(1-(x-lo)/((hi-lo)||1))*(H-6);
 let d='',pen=false;xs.forEach((x,i)=>{if(x==null){pen=false;return}d+=(pen?'L':'M')+X(i).toFixed(1)+','+Y(x).toFixed(1);pen=true});
 const mean=v.reduce((a,b)=>a+b,0)/v.length;
 return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Last ten years"><line x1="2" x2="${W-2}" y1="${Y(mean)}" y2="${Y(mean)}" stroke="var(--muted,#999)" stroke-dasharray="3 3" stroke-width="0.8"/><path d="${d}" fill="none" stroke="var(--accent,#2a78d6)" stroke-width="1.3"/></svg>`;
}

/* views */
function mmOverview(d){
 const V=(d.vol||{}),spy=(V.assets||[]).find(a=>a.id==='SPY')||{},vs=(V.scores||[]).find(s=>s.id==='SPY'&&s.h===4)||{};
 const G=d.regime||{},I=d.indices||{},S=d.sectors||{},M=(d.market||{}).h||{},m13=M['13']||{};
 const i13=(I.scores||{})['13']||{},s13=(S.scores||{})['13']||{};
 const sp=(d.spreads||[]);const mr=sp.filter(x=>(x.h13||{}).chosen==='ou').length;
 let out=`<div class="metrics">${kpi('SPY volatility, next 4 weeks',mmP((spy.h4||{}).vol,1),'VIX '+(V.vix==null?'—':fmt(V.vix,1))+' · last 26 weeks '+mmP((spy.h4||{}).hist_vol,1))}
  ${kpi('Market state now',G.now?MM_STATE_NAMES()[G.now.indexOf(Math.max(...G.now))]+' '+mmP(Math.max(...G.now)):'—','three-state model of SPY, the VIX and credit')}
  ${kpi('SPY over cash, next 13 weeks',mmS((m13.now||{}).excess),'chance SPY is higher '+mmP((m13.now||{}).p_up))}</div>`;
 const rows=[
  ['Volatility (HAR)',`QLIKE ${vs.gain_vs_hist_used==null?'—':(vs.gain_vs_hist_used>=0?'':'−')+fmt(Math.abs(vs.gain_vs_hist_used*100),0)+'% lower'} than the last 26 weeks' volatility on SPY; 80% ranges held ${mmP(vs.coverage80)}`,'Works: volatility clusters, so it can be forecast'],
  ['Market regime',`P(SPY falls 10% within 13 weeks): Brier skill ${mmSkill((G.score||{}).down10_13w_brier_skill)}`,'Describes risk well; does not time falls'],
  ['Six indices',`P(beats the centre in 13 weeks): ${mmSkill(i13.brier_skill)}; model's ranking: rank correlation ${mmN(i13.ic,3)}`,'No demonstrated skill: shown at the base rate'],
  ['Sectors',`P(beats SPY in 13 weeks): ${mmSkill(s13.brier_skill)}; ranking ${mmN(s13.ic,3)}, momentum alone ${mmN(s13.ic_momentum,3)}`,'No demonstrated skill since 2003'],
  ['Spreads',`${sp.length} spreads; ${mr} chosen as mean-reverting on 2000–2011, the rest a random walk`,'Mostly random walks'],
  ['Market direction',`13 weeks: out-of-sample R² ${mmS(((m13.score)||{}).r2_published,1)} against the past average; direction ${mmSkill(((m13.score)||{}).up_brier_skill)}`,'As the literature finds: hardly predictable']];
 out+=`<div class="mm-list" style="display:grid;gap:10px;margin:14px 0">${rows.map(r=>`<div style="border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 14px"><div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px"><b>${esc(r[0])}</b><span class="tag">${esc(r[2])}</span></div><div style="margin-top:4px;font-size:.9rem">${r[1]}</div></div>`).join('')}</div>`;
 out+=mmNote('Out-of-sample record since '+(d.first_test||2003)+'.');
 out+=mmNote('Every model is refitted once a year on the weeks whose outcome was known before 1 January and predicts the weeks of that year; the scores count only those predictions. A model is then used only as far as it has worked out of sample before (at least five years of record), so a model with no record or no skill shows the benchmark — no rotation, the base rate, the past average. Statistical models on public data, not investment advice.');
 return out;
}
function MM_STATE_NAMES(){return ['Calm','Normal','Stressed']}
function mmVol(d){
 const V=d.vol||{},sc=V.scores||[];
 const S=(id,h)=>sc.find(s=>s.id===id&&s.h===h)||{};
 let out=mmSec('Volatility forecasts','HAR on weekly returns; with the VIX, VXN, RVX or VXD where they exist');
 out+=`<div class="metrics">${kpi('VIX',V.vix==null?'—':fmt(V.vix,1),'30-day implied volatility of the S&P 500')}${kpi('VIX ÷ VIX 3-month',V.vix_term==null?'—':fmt(V.vix_term,2),V.vix_term==null?'the 3-month index is not on file yet':V.vix_term>1?'inverted: near-term fear above the 3-month':'normal: the 3-month above the near term')}</div>`;
 out+=table(['Fund','Next 4 weeks','Next 13 weeks','Last 26 weeks','Implied','Variance premium','4-week range (80%)','13-week range (80%)','Better than the 26-week (4w / 13w)','Range held'],
  (V.assets||[]).map(a=>{const h4=a.h4||{},h13=a.h13||{},s4=S(a.id,4),s13=S(a.id,13);
   return [`<b>${esc(a.id)}</b>${h4.uses_implied?' <span class="muted">+ implied</span>':''}`,mmP(h4.vol,1),mmP(h13.vol,1),mmP(h4.hist_vol,1),mmP(a.implied_vol,1),a.vrp==null?'—':(a.vrp>=0?'+':'−')+fmt(Math.abs(a.vrp*1e4),0)+' %²',
    h4.range?`${mmS(h4.range[0])} to ${mmS(h4.range[1])}`:'—',h13.range?`${mmS(h13.range[0])} to ${mmS(h13.range[1])}`:'—',`${mmGain(s4.gain_vs_hist_used)} / ${mmGain(s13.gain_vs_hist_used)}`,`${mmP(s4.coverage80)} / ${mmP(s13.coverage80)}`]}));
 out+=mmNote('Annualized. HAR (Corsi 2009): the log of the next weeks\' variance on the logs of the last 1, 4 and 26 weeks\' (and of the implied variance where one exists). "Better than the 26-week": how much lower its QLIKE loss was than the plain 26-week volatility\'s, out of sample since 2003 (QLIKE ranks variance forecasts consistently; Patton 2011). Ranges: the forecast volatility × the 10th and 90th percentiles of past standardized outcomes; "range held" is how often the actual return fell inside (80% is right). Variance premium: implied variance less the HAR forecast, annualized, in percent squared (16% implied against a 13% forecast is 16² − 13² = +87) — when high, the market has tended to earn more over the next quarter (Bollerslev, Tauchen and Zhou 2009).');
 return out;
}
function mmRot(d,key,label,base){
 const B=d[key]||{},sc=B.scores||{};
 let out=mmSec(label,`against ${base}; 4 and 13 weeks`);
 out+=table(['Fund','Name','P(beats '+base+', 13w)','P(best of all, 13w)','P(beats, 4w)','The model alone (13w)','Momentum 52−4','Last 13 weeks','Last 4 weeks'],
  (B.rows||[]).map(r=>[`<b>${esc(r.id)}</b>`,esc(r.name),mmP((r.h13||{}).p_beat),mmP((r.h13||{}).p_lead),mmP((r.h4||{}).p_beat),`<span class="muted">${mmRet((r.h13||{}).rel_model)}</span>`,mmRet((r.signals||{}).mom52_4),mmRet((r.signals||{}).mom13),mmRet((r.signals||{}).rev4)]));
 out+=mmSec('How it has done','out of sample, from '+(d.first_test||2003));
 out+=table(['Horizon','Origins (independent)','Rank correlation','… momentum alone','Best minus worst pick','… momentum alone','P(beats): Brier skill as published','… the model alone','Trust now (0–1)'],
  Object.values(sc).map(s=>[s.h+' weeks',fmt(s.origins),mmN(s.ic,3)+(s.ic_t==null?'':` <span class="muted">(t ${mmN(s.ic_t,1)})</span>`),mmN(s.ic_momentum,3),mmRet(s.best_minus_worst,2),mmRet(s.best_minus_worst_momentum,2),mmSkill(s.brier_skill),mmSkill(s.brier_skill_raw),mmN(s.beta_now,2)]));
 return out;
}
function mmIndices(d){
 const I=d.indices||{},F=I.fundamentals,C=I.conditions||{};
 let out=mmRot(d,'indices','The six indices','their equal-weight centre');
 if(F){out+=mmSec('What they hold now','today\'s members with SEC figures on this site');
  out+=table(['Fund','Members (covered)','Earnings yield','Revenue growth, year','Earnings growth, year','Members losing money'],
   Object.entries(F).map(([k,f])=>[`<b>${esc(k)}</b>`,`${fmt(f.members)} (${fmt(f.covered)})`,mmP(f.earnings_yield,1),mmS(f.revenue_growth),mmS(f.earnings_growth),mmP(f.loss_share)]));
  out+=mmNote('Σ trailing net income ÷ Σ market value of the members covered. The S&P SmallCap 600 admits only companies with positive earnings, the Russell 2000 does not: the gap in the share losing money is the "quality" difference between the two small-cap indices (Asness and others, 2018). Today\'s members only, so this is a description, not a model input.');}
 out+=mmNote(`Signals: each index's return against the centre over 52 weeks less the last 4, over 13 weeks and over the last 4, its volatility against the centre's (each ranked within the week), and market conditions with a coefficient per index — the 13-week change in the credit spread (now ${mmN(C.credit_13w,2)} pts), the yield curve (${mmN(C.curve,2)} pts), the variance premium and the stressed-regime probability (${mmP(C.stress)}). Ridge regression, refitted yearly. "Trust now" is how far the model's forecast is used: the slope of outcomes on its earlier out-of-sample forecasts, 0 to 1; at 0 the probabilities are the base rate and "the model alone" shows what it would have said.`);
 return out;
}
function mmSectors(d){
 let out=mmRot(d,'sectors','Sector funds','SPY');
 out+=mmNote('As the indices, plus the site\'s sector aggregates of the latest quarter on file (revenue growth against a year earlier, its acceleration and the operating margin against a year earlier, counted 46 days after the quarter). The benchmark "momentum alone" is Moskowitz and Grinblatt (1999); since 2003 it has not worked on the SPDR sectors either.');
 return out;
}
function mmRegime(d){
 const G=d.regime;if(!G)return empty('No regime model: the VIX or the credit spread is missing.');
 let out=mmSec('Market state','a three-state hidden Markov model of SPY\'s weekly return, the VIX and the 4-week change in the credit spread');
 out+=`<div class="metrics">${(G.now||[]).map((p,k)=>kpi(MM_STATE_NAMES()[k],mmP(p),'probability this week')).join('')}${kpi('SPY falls 10% within 13 weeks',mmP(G.p_down10_13w,1),'base rate '+mmP(G.base_down10_13w,1))}</div>`;
 out+=mmStack(G.history)+`<div class="muted" style="font-size:.8rem">${MM_STATE_NAMES().map((n,k)=>`<span style="display:inline-block;width:10px;height:10px;background:${MM_STATE_COL[k]};margin:0 4px 0 10px"></span>${n}`).join('')} · each week from the weeks up to it (filtered), refitted yearly</div>`;
 out+=table(['State','Return a year','Volatility a year','VIX','Credit spread, 4-week change','Chance of staying a week','Typical length'],
  (G.states||[]).map(s=>[`<b>${esc(s.name)}</b>`,mmS(s.ret_year),mmP(s.vol_year),mmN(s.vix,1),mmN(s.credit_4w,3)+' pts',mmP(s.stay,1),mmN(s.weeks,0)+' weeks']));
 out+=mmSec('What followed each state','out-of-sample weeks since '+(d.first_test||2003)+', the next 13 weeks');
 out+=table(['State','Weeks','SPY return','SPY volatility','Share with a 10% fall'],(G.by_state||[]).map(s=>[`<b>${esc(s.name)}</b>`,fmt(s.weeks),mmRet(s.spy_13w),mmP(s.spy_13w_vol),mmP(s.down10_share)]));
 const L=G.leaders_by_state||[];
 if(L.length)out+=table(['Fund','Kind','After calm weeks','After normal weeks','After stressed weeks'],L.map(r=>[`<b>${esc(r.id)}</b>`,esc(r.kind==='index'?'index vs centre':'sector vs SPY'),mmRet(r.Calm),mmRet(r.Normal),mmRet(r.Stressed)]));
 out+=mmNote(`The states describe risk: the next 13 weeks' volatility and the share of 10% falls differ a lot between them. Turning them into odds of a fall did ${(G.score||{}).down10_13w_brier_skill_raw<0?'worse than':'no better than'} the base rate out of sample (Brier skill ${mmSkill((G.score||{}).down10_13w_brier_skill_raw)} on ${fmt((G.score||{}).independent)} independent 13-week spans) — the model was calm going into 2008 — so the published odds stay near the base rate. The "who did best" table is averages, not a forecast; app/odds.py has a two-state model of SPY alone.`);
 return out;
}
function mmSpreads(d){
 const S=d.spreads||[];
 let out=mmSec('Spreads','ratios of fund prices (log) and two rates spreads (points)');
 out+=table(['Spread','Last 10 years','Now','vs its 3 years (z)','Follows','Next 13 weeks','Range (80%)','Half-life','R²: mean reversion / trend','Range held'],
  S.map(s=>{const h=s.h13||{},lg=s.kind==='log',f=v=>v==null?'—':lg?mmRet(v):mmN(v,2)+' pts';
   return [`<b>${esc(s.id)}</b><br><span class="muted">${esc(s.name)}</span>`,mmLine(s.history),lg?fmt(Math.exp(s.now),3):mmN(s.now,2),mmN(s.z_3y,2),esc({rw:'random walk',ou:'mean reversion',trend:'trend'}[h.chosen]||h.chosen||'—'),f(h.forecast),h.range?`${f(h.range[0])} to ${f(h.range[1])}`:'—',h.half_life_weeks==null?'—':fmt(h.half_life_weeks,0)+' weeks',`${mmS(h.r2_ou,1)} / ${mmS(h.r2_trend,1)}`,mmP(h.coverage80)]}));
 out+=mmNote('Three forecasts of each spread\'s change: none (a random walk), mean reversion (an AR(1) of the weekly level — Ornstein–Uhlenbeck in discrete time — refitted yearly) and trend (the last 13 weeks\' change). Which one a spread follows was chosen on 2000–2011 (it had to beat the random walk by 1%); R² is how much better than the random walk each did from 2012, out of sample. Most spreads are random walks: a stretched z-score is not, by itself, a reason to expect a reversal. Ranges: errors scaled by the spread\'s own volatility over the last 26 weeks.');
 return out;
}
function mmMarket(d){
 const M=d.market;if(!M)return empty('No market model.');
 let out=mmSec('SPY over cash','one regression per predictor, averaged (Rapach, Strauss and Zhou 2010)');
 out+=`<div class="metrics">${Object.entries(M.h).map(([h,b])=>kpi(h+' weeks: expected over cash',mmS(b.now.excess),'P(SPY higher) '+mmP(b.now.p_up)+' · base '+mmP(b.now.base_up))).join('')}</div>`;
 out+=table(['Horizon','Expected over cash','80% range','Past average','The average of the predictors','Out-of-sample R² (published)','… the average of the predictors','… with negative forecasts set to 0','Direction: Brier skill','Range held','Independent spans'],
  Object.entries(M.h).map(([h,b])=>{const s=b.score,n=b.now;return [h+' weeks',mmS(n.excess),n.range?`${mmS(n.range[0])} to ${mmS(n.range[1])}`:'—',mmS(n.history_mean),mmS(n.combination),mmS(s.r2_published,1),mmS(s.r2_combination,1),mmS(s.r2_combination_ct,1),mmSkill(s.up_brier_skill),mmP(s.coverage80),fmt(s.independent)]}));
 const h13=(M.h['13']||{}),each=(h13.now||{}).each||{},r2=((h13.score||{}).r2_each)||{};
 out+=table(['Predictor','Now','Its 13-week forecast','Its out-of-sample R²'],(M.predictors||[]).map(p=>[esc(p.name),p.now==null?'—':fmt(p.now,3),mmS(each[p.id]),mmS(r2[p.id],1)]));
 out+=mmNote('R² is against the past average (Goyal and Welch 2008: most predictors fail it out of sample); a few tenths of a percent would already be useful, and the restricted version (Campbell and Thompson 2008) is shown for reference. The published forecast is the past average plus the averaged forecast only as far as it has beaten the average before — at present not at all. Not investment advice.');
 return out;
}
function mmRecord(d){
 const L=d.ledger;if(!L)return empty('The ledger starts with the first closed week after this page went live.');
 const rows=[['Volatility',L.vol],['Six indices',L.index],['Sectors',L.sector],['Spreads',L.spread],['Market direction',L.market],['Regime: 10% fall',L.regime]];
 let out=mmSec('Frozen forecasts','each closed week\'s forecasts are written once and scored when the outcome is known');
 out+=table(['Model','Resolved','Waiting','Brier skill','Range held','Log error of volatility'],rows.map(([n,s])=>{s=s||{};return [esc(n),fmt(s.resolved||0),fmt(s.pending||0),s.skill==null?'—':mmSkill(s.skill),mmP(s.coverage80),s.log_mae==null?'—':fmt(s.log_mae,3)]}));
 return out;
}
function mmView(){
 state.mmv=MM_VIEWS.some(v=>v[0]===state.mmv)?state.mmv:'overview';
 let out=head('Market models','Volatility, the six index funds, the market\'s regime, sectors, spreads and the market\'s direction — each tested on the years before it was shown, and used only as far as it has worked.','Models');
 out+=`<div class="toolbar">${field('mmv','View',MM_VIEWS,state.mmv)}</div>`;
 const g=mmData();
 if(g.err)return out+empty(`The market models could not load (${g.err}). They are rebuilt by .github/workflows/rotation-history.yml (app/market_models.py).`);
 if(!g.data)return out+empty('Loading the market models…');
 const d=g.data,f={overview:mmOverview,vol:mmVol,indices:mmIndices,regime:mmRegime,sectors:mmSectors,spreads:mmSpreads,market:mmMarket,record:mmRecord}[state.mmv];
 return out+f(d);
}
function bindMm(){
 if(state.tab!=='mmodels')return;
 if($('mmv'))$('mmv').onchange=e=>{state.mmv=e.target.value;state.page=0;render()};
}
function mmodelsDeepLink(arg){const v=decodeURIComponent(arg||'').trim();if(MM_VIEWS.some(x=>x[0]===v))state.mmv=v}
function mmNotice(){
 const s=mmData(),d=s.data;
 if(s.err)return {stale:true,text:'Official derived view · Market models unavailable · '+s.err};
 if(!d)return {stale:false,text:'Official derived view · Market models loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=30),text:`Official derived view · Market models built ${d.generated_at} · week ending ${d.asof} · rebuilt with the weekly closes every three hours`+(age>30?' · stale':'')};
}
if(typeof window!=='undefined'){
 window.mmodelsDeepLink=mmodelsDeepLink;
 window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{mmodels:mmNotice});
 window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{mmodels:mmView});
 window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{mmodels:bindMm});
}
if(typeof module!=='undefined')module.exports={mmOverview,mmVol,mmIndices,mmRegime,mmSectors,mmSpreads,mmMarket,mmRecord,mmStack,mmLine};
})();
