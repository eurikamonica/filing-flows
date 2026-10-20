/* Valuation — fair value & credit for every company: WACC, DCF and reverse DCF, Monte Carlo, the price paid for growth
   (PVGO), peer multiples, residual income, bank / insurer / REIT models, valuation bands and a distress probability.
   Data: data/research/valuation/{index,banks,insurers,ledger,status}.json and c/<cik>.json (app/valuation.py, branch
   research-valuation). One company is drawn by fairvalue-view.js (shared with the main site's company page). */
const valStore={};
function valData(name){
 const m=valStore[name]||(valStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/valuation/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const VAL_VIEWS=[['all','Every company'],['company','One company'],['fits','Banks & insurers'],['track','Track record']];
const VAL_SHOW=[['','All companies'],['large','Market value ≥ $10B'],['above','DCF above the price'],['below','DCF below the price'],['growth','Price mostly growth (PVGO ≥ 70%)'],['distress','Distress ≥ 2%'],['cheap','P/E in the bottom 10% of its range'],['rich','P/E in the top 10% of its range']];
const VAL_KIND=[['','All kinds'],['industrial','Operating companies'],['bank','Banks'],['insurer','Insurers'],['reit','REITs']];
function valRows(d){const F=d.fields;return (d.rows||[]).map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o})}
function valMoney(v){return v==null?'—':(v<0?'−$':'$')+fmt(Math.abs(v),Math.abs(v)>=1000?0:2)}
function valPct(v,d=0){return v==null?'—':fmt(v*100,d)+'%'}
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
  return out+`<div class="section-head"><h3>Scores</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Snapshot','Horizon','Companies','IC: P(value > price)','IC: DCF gap','Price moved toward the DCF value'],sc.map(s=>[esc(s.month),s.horizon_months+' months',fmt(s.n),fmt(s.ic_p_above,3),fmt(s.ic_dcf_gap,3),valPct(s.direction_hit_rate)]));
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
 for(const k of ['vview','vshow','vkind'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 if($('vq')){$('vq').onchange=e=>{state.vq=e.target.value;render()};$('vq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-vco]').forEach(b=>b.onclick=()=>{state.vview='company';state.vq=b.dataset.vco;render();scrollTo({top:0,behavior:'smooth'})});
 const one=$('val-one');
 if(one&&window.FairValueView&&one.dataset.drawn!==one.dataset.cik){one.dataset.drawn=one.dataset.cik;FairValueView.render(one,{cik:one.dataset.cik,hub:''})}
 const fb=$('val-fit-bank'),fi=$('val-fit-ins');
 if(fb){const b=valData('banks');if(b.data)valScatter(fb,b.data.fit,'ROTCE','P/TBV');else fb.innerHTML=empty(b.err?'Not available ('+b.err+').':'Loading…')}
 if(fi){const b=valData('insurers');if(b.data)valScatter(fi,b.data.fit,'ROE','P/B');else fi.innerHTML=empty(b.err?'Not available ('+b.err+').':'Loading…')}
}
