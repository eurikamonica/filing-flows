/* Valuation — fair value & credit for every company: WACC, DCF and reverse DCF, Monte Carlo, the price paid for growth
   (PVGO), peer multiples, residual income, bank / insurer / REIT models, valuation bands and a distress probability.
   Data: data/research/valuation/{index,banks,insurers,ledger,models,base_rates,status}.json and c/<cik>.json
   (app/valuation.py + app/base_rates.py, branch research-valuation). One company is drawn by fairvalue-view.js (shared with
   the main site's company page). The "Outside view" lists every company's stage and the base-rate probability of what its
   price, the Street and Polymarket require; "Model scores" shows each model out of sample against a naive baseline. */
const valStore={};
function valData(name){
 const m=valStore[name]||(valStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/valuation/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const VAL_VIEWS=[['all','Every company'],['outside','Outside view (base rates)'],['company','One company'],['fits','Banks & insurers'],['track','Track record'],['models','Model scores']];
const VAL_STAGE=[['','All stages'],['pre_profit','Pre-profit'],['high_growth','High growth'],['growth','Growth'],['mature','Mature'],['cyclical','Cyclical'],['decline','Decline / turnaround'],['financial','Financials'],['reit','REITs']];
const VAL_STAGE_LABEL=Object.fromEntries(VAL_STAGE.filter(x=>x[0]));
const VAL_OSORT=[['p_implied','Lowest base rate of the implied growth'],['ov_gap','Outside-view expected value vs price'],['p_street_eps','Lowest base rate of the Street EPS'],['pm_edge','Polymarket vs base rate (EPS)'],['mcap','Market value']];
const VAL_SHOW=[['','All companies'],['large','Market value ≥ $10B'],['above','DCF above the price'],['below','DCF below the price'],['growth','Price mostly growth (PVGO ≥ 70%)'],['distress','Distress ≥ 2%'],['cheap','P/E in the bottom 10% of its range'],['rich','P/E in the top 10% of its range']];
const VAL_KIND=[['','All kinds'],['industrial','Operating companies'],['bank','Banks'],['insurer','Insurers'],['reit','REITs']];
function valRows(d){const F=d.fields;return (d.rows||[]).map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o})}
function valMoney(v){return v==null?'—':(v<0?'−$':'$')+fmt(Math.abs(v),Math.abs(v)>=1000?0:2)}
function valPct(v,d=0){return v==null?'—':fmt(v*100,d)+'%'}
function valP(v){return v==null?'—':v>0&&v<0.005?'<1%':v<1&&v>0.995?'>99%':fmt(v*100,0)+'%'}
function valSpct(v){return v==null?'—':`<span class="${v>=0?'positive':'negative'}">${v>=0?'+':'−'}${fmt(Math.abs(v*100),0)}%</span>`}
function valView(){
 state.vview=VAL_VIEWS.some(v=>v[0]===state.vview)?state.vview:'all';
 let out=head('Fair value &amp; credit','Many valuation methods side by side, each company\'s own cost of capital, the share of the price paid for growth, valuation bands and a blended distress probability. Every assumption is shown; not investment advice.','SEC XBRL · PRICES · DEBT · CONSENSUS');
 out+=`<div class="toolbar">${field('vview','View',VAL_VIEWS,state.vview)}`;
 if(state.vview==='all')out+=field('vshow','Show',VAL_SHOW,state.vshow||'')+field('vkind','Kind',VAL_KIND,state.vkind||'');
 if(state.vview==='company')out+=`<div class="field wide"><label for="vq">Company (ticker)</label><input id="vq" value="${esc(state.vq||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 out+='</div>';
 const g=valData('index');
 if(g.err)return out+empty(`The valuation data could not load (${g.err}). It is built every weekday after the close by .github/workflows/research-valuation.yml.`);
 if(!g.data)return out+empty('Loading the valuations…');
 const rows=valRows(g.data),A=g.data.assumptions||{};
 if(state.vview==='company'){
  const q=String(state.vq||'').trim().toUpperCase();
  if(!q)return out+empty('Type a ticker to see its valuation football field, Monte Carlo, cost of capital, bands and credit.');
  const r=rows.find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
  if(!r)return out+empty(`No valuation for ${q}: the build covers companies with a share price and filed figures.`);
  return out+`<div class="panel"><h3>${esc(r.ticker)} <span class="muted">${esc(r.name||'')}</span></h3><div id="val-one" data-cik="${esc(r.cik)}"></div></div>`;
 }
 if(state.vview==='fits')return out+`<div class="charts"><div class="panel"><h3>Banks: P/TBV against ROTCE</h3><div id="val-fit-bank"></div></div><div class="panel"><h3>Insurers: P/B against ROE</h3><div id="val-fit-ins"></div></div></div><div class="explain">Each dot is one company; the line is the least-squares fit across them. A bank priced above the line trades at a richer multiple of tangible book than its return on it would suggest, and the reverse. Tangible book = equity − goodwill − other intangibles (XBRL).</div>`;
 if(state.vview==='track'){
  const L=valData('ledger');if(L.err)return out+empty('No track record yet ('+L.err+').');if(!L.data)return out+empty('Loading…');
  const sc=L.data.scores||[];
  out+=`<div class="explain">${esc(L.data.note||'')} Snapshots so far: ${esc((L.data.snapshots||[]).join(', ')||'none')}. IC = Spearman rank correlation between the measure and the return that followed (0 = no information).</div>`;
  if(!sc.length)return out+empty('No snapshot is old enough to score yet: the first scores appear three months after the first snapshot.');
  exported=sc;
  return out+`<div class="section-head"><h3>Scores</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Snapshot','Horizon','Companies','IC: P(value > price)','IC: DCF gap','Price moved toward the DCF value','Share that rose (naive)','IC: analysts\' target','IC: Polymarket','IC: outside view','Combined error vs no change'],sc.map(s=>[esc(s.month),s.horizon_months+' months',fmt(s.n),fmt(s.ic_p_above,3),fmt(s.ic_dcf_gap,3),valPct(s.direction_hit_rate),valPct(s.share_up),fmt(s.ic_target_gap,3),fmt(s.ic_pm_gap,3),fmt(s.ic_outside_gap,3),s.mae_combined==null?'—':valPct(s.mae_combined,1)+' vs '+valPct(s.mae_no_change,1)]));
 }
 if(state.vview==='models')return out+valModels();
 if(state.vview==='outside'){
  out+=`<div class="toolbar">${field('vstage','Stage',VAL_STAGE,state.vstage||'')}${field('vosort','Sort',VAL_OSORT,state.vosort||'p_implied')}</div>`;
  let R=rows.filter(r=>r.stage&&(!state.vstage||r.stage===state.vstage));
  const k=state.vosort||'p_implied',key={p_implied:r=>r.p_implied,ov_gap:r=>r.ov_mean!=null&&r.price?-(r.ov_mean/r.price-1):null,p_street_eps:r=>r.p_street_eps,pm_edge:r=>r.pm_beat_prob!=null&&r.p_pm_eps_base!=null?-(r.pm_beat_prob-r.p_pm_eps_base):null,mcap:r=>-(r.mcap||0)}[k];
  R=R.slice().sort((a,b)=>{const x=key(a),y=key(b);return x==null?1:y==null?-1:x-y});
  const cnt={};rows.forEach(r=>{if(r.stage)cnt[r.stage]=(cnt[r.stage]||0)+1});
  const med=a=>{a=a.filter(v=>v!=null).sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:null};
  out+=`<div class="metrics">${kpi('Companies with a stage',fmt(rows.filter(r=>r.stage).length),Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([s,n])=>`${esc(VAL_STAGE_LABEL[s]||s)} ${fmt(n)}`).join(' · '))}${kpi('Median base rate of the implied growth',valP(med(rows.map(r=>r.p_implied))),'share of peers whose 5-year revenue CAGR reached what the price needs')}${kpi('Median base rate of the Street EPS',valP(med(rows.map(r=>r.p_street_eps))),'share of peer quarters at or above the consensus growth')}${kpi('Expected (outside) above the price',valP(rows.filter(r=>r.ov_mean!=null).length?rows.filter(r=>r.ov_mean!=null&&r.ov_mean>r.price).length/rows.filter(r=>r.ov_mean!=null).length:null),'companies whose peers\' base rates give more than the price')}</div>`;
  exported=R;
  out+=`<div class="section-head"><h3>${fmt(R.length)} companies</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">The outside view: every input read from what peers (same SIC industry and size; widened until 40 observations from 5 companies) actually did. Implied growth: the 5-year revenue CAGR today's price needs (reverse DCF); its base rate is the share of peer 5-year windows since 2010 that grew at least that fast. Street EPS: the analysts' next-quarter EPS against the year-ago quarter, and how often peer quarters since 2020 grew that much. Polymarket: the market's probability of the EPS line beside the base rate of the growth that line needs. Expected: the mean of 1,000 DCFs with growth, margin, WACC and terminal growth drawn from peers. Combined: the walk-forward 3-month forecast (see Model scores).</p>`;
  out+=table(['Company','Stage','Price','Implied growth','Base rate','Peer group','Street EPS growth','Base rate','Polymarket line','Market / base rate','Expected (outside)','80% range','P(value > price)','Combined 3m','Main driver'],R.map(r=>[
   `<button class="text-button" data-vco="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button> <span class="muted">${esc((r.name||'').slice(0,24))}</span>`,
   esc(VAL_STAGE_LABEL[r.stage]||r.stage||'—'),valMoney(r.price),valPct(r.implied_growth,1),`<b>${valP(r.p_implied)}</b>`,`<span class="muted">${esc(String(r.peer_group||'').slice(0,40))}${r.peer_n?' · '+fmt(r.peer_n):''}</span>`,
   r.req_eps_g==null?'—':valSpct(r.req_eps_g),valP(r.p_street_eps),r.pm_eps_strike==null?'—':valMoney(r.pm_eps_strike),r.pm_beat_prob==null?'—':valP(r.pm_beat_prob)+' / '+valP(r.p_pm_eps_base),
   valMoney(r.ov_mean),r.ov_p10==null?'—':valMoney(r.ov_p10)+'–'+valMoney(r.ov_p90),valP(r.ov_p_above),r.comb_ret==null?'—':valSpct(r.comb_ret),esc(r.sens_driver||'—')]));
  return out;
 }
 const big=10e9;
 let R=rows.filter(r=>!state.vkind||r.kind===state.vkind);
 const show=state.vshow||'';
 R=R.filter(r=>show===''||(show==='large'&&r.mcap>=big)||(show==='above'&&r.dcf_gap>0)||(show==='below'&&r.dcf_gap<0)||(show==='growth'&&r.pvgo_share>=0.7)||(show==='distress'&&r.distress_pd>=0.02)||(show==='cheap'&&r.pe_pct!=null&&r.pe_pct<=0.1)||(show==='rich'&&r.pe_pct!=null&&r.pe_pct>=0.9));
 const withDcf=rows.filter(r=>r.dcf_value!=null),med=a=>{a=a.filter(v=>v!=null).sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:null};
 out+=`<div class="metrics">${kpi('Companies valued',fmt(rows.length),fmt(withDcf.length)+' with a DCF')}${kpi('Median WACC',valPct(med(rows.map(r=>r.wacc)),1),'ERP '+valPct(A.erp,1)+' · 10-year Treasury '+(A.treasury_10y==null?'—':fmt(A.treasury_10y,2)+'%'))}${kpi('Median price paid for growth',valPct(med(rows.map(r=>r.pvgo_share))),'PVGO share of market value')}${kpi('Median P(value > price)',valPct(med(withDcf.map(r=>r.mc_p_above))),'Monte Carlo DCF, '+fmt(A.mc_scenarios)+' scenarios')}</div>`;
 exported=R;
 out+=`<div class="section-head"><h3>${fmt(R.length)} companies</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Click a ticker for its football field. DCF gap: the base-case DCF value against the price. Implied growth: the yearly revenue growth today's price needs (reverse DCF). P/E position: where today's P/E sits in its own range since mid-2022. Distress: a blend of Merton, the bond-calibrated spread, Altman Z and the debt cushion — a ranking, not calibrated to realized defaults.</p>`;
 out+=table(['Company','Price','WACC','DCF value','DCF gap','P(value > price)','Implied growth','Growth last 4Q','Price for growth','P/E','P/E position','Distress','DD'],R.map(r=>[
  `<button class="text-button" data-vco="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button> <span class="muted">${esc((r.name||'').slice(0,28))}</span>${r.kind!=='industrial'?` <span class="tag">${esc(r.kind)}</span>`:''}`,
  valMoney(r.price),valPct(r.wacc,1),valMoney(r.dcf_value),valSpct(r.dcf_gap),valPct(r.mc_p_above),valPct(r.implied_growth,1),valPct(r.history_growth,1),valPct(r.pvgo_share),fmt(r.pe,1),r.pe_pct==null?'—':fmt(r.pe_pct*100)+'th pct',valPct(r.distress_pd,r.distress_pd!=null&&r.distress_pd<0.01?2:1),fmt(r.distance_to_default,1)]));
 return out;
}
function valModels(){
 const g=valData('models');
 if(g.err)return empty('No model scores yet ('+g.err+').');
 if(!g.data)return empty('Loading the model scores…');
 const M=g.data,c=M.combined||{},H=c.horizons||{};
 let out=`<div class="explain">${(M.verdict||[]).map(esc).join('<br>')}</div>`;
 const rowsOf=(h)=>{const S=(H[h]||{}).scores||{};return [['Combined (walk-forward ridge)','combined'],['No change (random walk)','zero'],['Training-mean drift','drift']].filter(x=>S[x[1]]).map(([l,k])=>{const s=S[k];return [esc(l),fmt(s.n),fmt(s.origins),valPct(s.mae,1),valPct(s.coverage80),valPct(s.width80),s.direction_hit==null?'—':valPct(s.direction_hit),valPct(s.share_up),s.ic_mean==null?'—':fmt(s.ic_mean,3)]})};
 for(const h of ['3m','12m']){
  if(!H[h])continue;
  const W=H[h].weights||{},FI=H[h].feature_ic||{};
  out+=`<div class="section-head"><h3>Combined forecast — ${h==='3m'?'3 months':'12 months'}</h3></div><p class="sub">${fmt(H[h].n_rows)} company-quarters with an outcome over ${fmt(H[h].origins)} quarters. Each quarter is forecast by a model fitted only on outcomes known by then; the 80% range comes from ${esc(H[h].interval_from||'earlier out-of-sample errors')} (split conformal). The quarters are the independent sample, not the rows.</p>`;
  out+=table(['Model','Forecasts','Quarters','Mean abs. error','80% coverage','80% width','Direction right','Share that rose','Rank IC'],rowsOf(h));
  out+=table(['Signal','What it is','Mean rank IC','Quarters','Rows','Weight (per σ)'],Object.keys(c.features||{}).map(k=>[esc(k),esc((c.features||{})[k]),FI[k]?fmt(FI[k].ic_mean,3):'—',FI[k]?fmt(FI[k].origins):'0',FI[k]?fmt(FI[k].n):'0',W[k]==null?'—':fmt(W[k]*100,2)+'%']));
 }
 const R=M.rotation;
 if(R){out+=`<div class="section-head"><h3>Rotation forecasts (forecast ledger)</h3></div>`;
  const rr=[];for(const [hz,by] of Object.entries(R))for(const [src,s] of Object.entries(by||{}))rr.push([esc(hz),esc(src),fmt(s.n),fmt(s.mae_pts,2)+' pts',fmt(s.naive_mae_pts,2)+' pts',s.beats_naive?'yes':'no',valPct(s.coverage80),valPct(s.direction_hit),valPct(s.share_up)]);
  out+=table(['Horizon','Origins','Resolved','Error','No-change error','Beats no change','80% coverage','Direction right','Share that rose'],rr);}
 const P=M.paired_with_rotation||c.paired_with_rotation;
 if(P&&P.n)out+=`<p class="sub">Paired on ${fmt(P.n)} company-quarters: combined ${valPct(P.mae_combined,1)} vs Rotation ${valPct(P.mae_rotation,1)} mean absolute error.</p>`;
 if(M.hier){out+=`<div class="section-head"><h3>Revenue growth model (pipeline/hier.py)</h3></div><p class="sub">${esc(M.hier.note)}</p>`;
  out+=table(['Level','Entities','Model (given parent)','Model (forecast parent)','Naive','Prior only','80% coverage','Beats naive'],Object.entries(M.hier.levels||{}).filter(x=>x[1]).map(([k,s])=>[esc(k),fmt(s.entities),fmt(s.cond,4),fmt(s.uncond,4),fmt(s.naive,4),fmt(s.prior_only,4),valPct(s.cover80),fmt(s.beats_naive)+' of '+fmt(s.entities)]));}
 if(M.polymarket_prices)out+=`<div class="section-head"><h3>Polymarket implied prices</h3></div><p class="sub">${esc(M.polymarket_prices.note)} Resolved: ${fmt(M.polymarket_prices.n)} · mean abs. error ${M.polymarket_prices.mean_abs_err_pct==null?'—':fmt(M.polymarket_prices.mean_abs_err_pct,1)+'%'} · inside the 10–90% range ${valPct(M.polymarket_prices.inside80)}.</p>`;
 const L=(M.valuation_ledger||{}).scores||[];
 out+=`<div class="section-head"><h3>Valuation ledger</h3></div><p class="sub">${L.length?fmt(L.length)+' scored snapshot-horizons: see Track record.':'Monthly snapshots are frozen and scored 3, 6 and 12 months later; none is old enough yet.'}</p>`;
 out+=`<div class="explain">${(M.notes||[]).map(esc).join('<br>')}</div>`;
 return out;
}
function valScatter(el,fit,xl,yl){
 const P=(fit&&fit.points)||[];if(P.length<5){el.innerHTML=empty('Not enough companies for a fit yet.');return}
 if(window.FairValueView&&FairValueView.draw){const tmp=document.createElement('div');el.innerHTML='';
  const W=520,H=300,L=46,R=12,T=12,B=32,xs=P.map(p=>p[0]),ys=P.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(0,...ys),y1=Math.max(...ys);
  const X=v=>L+(v-x0)/((x1-x0)||1)*(W-L-R),Y=v=>T+(y1-v)/((y1-y0)||1)*(H-T-B);
  let s=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:560px" role="img" aria-label="${esc(yl)} against ${esc(xl)}">`;
  P.forEach(p=>{s+=`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3.2" fill="var(--muted,#888)" opacity="0.65"><title>${esc(p[2])}: ${esc(xl)} ${fmt(p[0]*100,1)}%, ${esc(yl)} ${fmt(p[1],2)}×</title></circle>`});
  s+=`<line x1="${X(x0)}" x2="${X(x1)}" y1="${Y(fit.a+fit.b*x0)}" y2="${Y(fit.a+fit.b*x1)}" stroke="var(--accent,#2a78d6)" stroke-width="1.6"/>`;
  s+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" font-size="11" fill="var(--muted,#777)">${esc(xl)}</text><text x="8" y="${T+10}" font-size="11" fill="var(--muted,#777)">${esc(yl)}</text></svg>`;
  el.innerHTML=s+`<p class="sub">${fmt(fit.n)} companies · ${esc(yl)} = ${fmt(fit.a,2)} + ${fmt(fit.b,2)} × ${esc(xl)} · r² ${fmt(fit.r2,2)}</p>`;
 }
}
function bindValuation(){
 if(state.tab!=='valuation')return;
 for(const k of ['vview','vshow','vkind','vstage','vosort'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 if($('vq')){$('vq').onchange=e=>{state.vq=e.target.value;render()};$('vq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-vco]').forEach(b=>b.onclick=()=>{state.vview='company';state.vq=b.dataset.vco;render();scrollTo({top:0,behavior:'smooth'})});
 const one=$('val-one');
 if(one&&window.FairValueView&&one.dataset.drawn!==one.dataset.cik){one.dataset.drawn=one.dataset.cik;FairValueView.render(one,{cik:one.dataset.cik,hub:''})}
 const fb=$('val-fit-bank'),fi=$('val-fit-ins');
 if(fb){const b=valData('banks');if(b.data)valScatter(fb,b.data.fit,'ROTCE','P/TBV');else fb.innerHTML=empty(b.err?'Not available ('+b.err+').':'Loading…')}
 if(fi){const b=valData('insurers');if(b.data)valScatter(fi,b.data.fit,'ROE','P/B');else fi.innerHTML=empty(b.err?'Not available ('+b.err+').':'Loading…')}
}
