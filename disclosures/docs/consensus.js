/* 4.12 Consensus — what analysts, prediction markets and our model expect, for every company, and how each did.
   Data: data/consensus/{index,calendar,markets,calibration,status}.json and data/consensus/c/<cik>.json (app/consensus.py,
   branch consensus-history). The company page is drawn by consensus-view.js (shared with the main site's company page). */
const consStore={};
function consData(name){
 const m=consStore[name]||(consStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/consensus/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function consGate(name,title){
 const m=consData(name);
 if(m.err)return {html:empty(`${title} could not load (${m.err}). The consensus collector runs every three hours.`)};
 if(!m.data)return {html:empty(`Loading ${title.toLowerCase()}…`)};
 return {data:m.data};
}
const CONS_VIEWS=[['market','The market — indices'],['calendar','Earnings calendar'],['screen','Every company'],['markets','Prediction markets'],['track','Track record'],['company','One company']];
const CONS_KINDS=[['','All kinds'],['beat','Beat earnings?'],['above','Price ladders'],['bracket','Closing-price brackets'],['mcap','Market caps'],['hit','High / low touch'],['metric','Reported metrics (revenue, segments)'],['kpi','Company KPIs'],['mention','Earnings-call mentions'],['updown','Up or down'],['other','Other events']];
const CONS_IX=[['spx','S&P 500'],['ndx','Nasdaq-100'],['dji','Dow Jones'],['rut','Russell 2000'],['vix','VIX']];
function consView(){
 state.cview=CONS_VIEWS.some(v=>v[0]===state.cview)?state.cview:'market';
 let out=`<div class="toolbar">${field('cview','View',CONS_VIEWS,state.cview)}`;
 if(state.cview==='company')out+=`<div class="field wide"><label for="cq">Company (ticker)</label><input id="cq" value="${esc(state.cq||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 if(state.cview==='market')out+=field('cidx','Index',CONS_IX,state.cidx||'spx');
 if(state.cview==='markets')out+=field('cabout','About',[['','Companies and indices'],['co','Companies'],['ix','Indices']],state.cabout||'')+field('ckind','Kind',CONS_KINDS,state.ckind||'')+field('csrc','Source',[['','Polymarket and Kalshi'],['polymarket','Polymarket'],['kalshi','Kalshi']],state.csrc||'')+field('cprob','YES probability',[['','All'],['low','Under 25%'],['mid','25–75%'],['high','Above 75%']],state.cprob||'')+field('cvol','Minimum reported volume',[['','Any'],['1000','$1K+'],['10000','$10K+'],['100000','$100K+'],['1000000','$1M+']],state.cvol||'')+'<div class="field"><label for="cdatefrom">Ends from</label><input type="date" id="cdatefrom" value="'+esc(state.cdatefrom||'')+'"></div><div class="field"><label for="cdateto">Ends through</label><input type="date" id="cdateto" value="'+esc(state.cdateto||'')+'"></div>';
 if(state.cview==='screen')out+=field('cflt','Show',[['','All companies with estimates'],['pm','With prediction markets'],['up','EPS estimates rising (30 days)'],['down','EPS estimates falling (30 days)'],['soon','Reporting in the next 14 days']],state.cflt||'');
 out+='</div>';
 out+=`<div class="explain">Three kinds of consensus side by side: <b>analysts</b> (EPS and revenue estimates, price targets and ratings — Yahoo Finance consensus), <b>prediction markets</b> (Polymarket and Kalshi: the price of a contract paying $1 if the company beats, if the stock closes above a level, if deliveries pass a number… is a crowd probability) and <b>our own model</b> (the Rotation tab's forecast). Each is kept and scored when the result is known. Not investment advice.</div>`;
 if(state.cview==='screen')return out+consScreen();
 if(state.cview==='markets')return out+consMarkets();
 if(state.cview==='track')return out+consTrack();
 if(state.cview==='company')return out+consCompany();
 if(state.cview==='market')return out+consMarket();
 return out+consCalendar();
}
function consRow(F,r){const o={};F.forEach((k,i)=>o[k]=r[i]);return o}
function consTk(t,ix){return ix?`<button class="text-button" data-cix="${esc(ix)}"><b>${esc(t)}</b></button>`:`<button class="text-button" data-cco="${esc(t)}"><b>${esc(t)}</b></button>`}
function consMarket(){
 const g=consGate('market','The market');if(!g.data)return g.html;
 const V=ConsensusView.fmt,P=v=>v==null?'—':fmt(v,Math.abs(v)>=1000?0:2),R=g.data.indices||[];
 const id=CONS_IX.some(x=>x[0]===state.cidx)?state.cidx:'spx';
 const rel=(v,l)=>v==null||!l?'':` <span class="${v>=l?'positive':'negative'}">${V.spct(v/l-1)}</span>`;
 const spark=a=>{if(!a||a.length<3)return '';const lo=Math.min(...a),hi=Math.max(...a),W=90,H=24;return `<svg viewBox="0 0 ${W} ${H}" style="width:90px;height:24px;vertical-align:middle"><path d="${a.map((v,i)=>(i?'L':'M')+(i*W/(a.length-1)).toFixed(1)+','+(H-2-(v-lo)/((hi-lo)||1)*(H-4)).toFixed(1)).join('')}" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>`};
 exported=R.map(r=>({index:r.name,level:r.level,as_of:r.as_of,chg_1w:r.chg_1w,chg_ytd:r.chg_ytd,analysts_target:r.target,target_return:r.target_ret,fwd_pe:r.fwd_pe,eps_growth_next_fy:r.eps_growth_next_fy,
  market_near:r.pm_near&&r.pm_near.median,market_near_date:r.pm_near&&r.pm_near.end,market_far:r.pm_far&&r.pm_far.median,market_far_date:r.pm_far&&r.pm_far.end,market_up:r.pm_up&&r.pm_up.p,
  ours_month:(r.ours.find(o=>o.horizon==='next month')||{}).price,ours_quarter:(r.ours.find(o=>o.horizon==='next quarter')||{}).price,open_markets:r.markets}));
 let out=`<div class="section-head"><h3>The indices — analysts, prediction markets and our model</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Analysts: the consensus price targets and earnings of each index's members added up at their weights. Markets: the median Polymarket / Kalshi traders imply for the nearest date more than five days out, and for the farthest. Our model: the Rotation forecasts of the members added up. Click an index for everything about it.</p>`;
 out+=table(['Index','Level','1 week','This year','26 weeks','Analysts (12 months)','Forward P/E','Market, nearest','Market, farthest','Market: up?','Our model (next quarter)','Open markets'],R.map(r=>{const oq=r.ours.find(o=>o.horizon==='next quarter')||r.ours[0];return [
  `${consTk(r.short,r.id)} <span class="muted">${esc(r.name)}</span>`,P(r.level),r.chg_1w==null?'—':`<span class="${r.chg_1w>=0?'positive':'negative'}">${V.spct(r.chg_1w)}</span>`,r.chg_ytd==null?'—':`<span class="${r.chg_ytd>=0?'positive':'negative'}">${V.spct(r.chg_ytd)}</span>`,spark(r.spark),
  r.target==null?'—':`${P(r.target)}${rel(r.target,r.level)}`,r.fwd_pe==null?'—':fmt(r.fwd_pe,1),
  r.pm_near?`${P(r.pm_near.median)}${rel(r.pm_near.median,r.level)} <span class="muted">${esc(r.pm_near.end.slice(5))}</span>`:'—',
  r.pm_far?`${P(r.pm_far.median)}${rel(r.pm_far.median,r.level)} <span class="muted">${esc(r.pm_far.end)}</span>`:'—',r.pm_up?`<b>${V.pct(r.pm_up.p)}</b> <span class="muted">${esc((r.pm_up.end||'').slice(5))}</span>`:'—',
  oq?`${P(oq.price)} <span class="${oq.ret>=0?'positive':'negative'}">${V.spct(oq.ret)}</span> <span class="muted">from ${esc(oq.from.slice(5))}</span>`:'—',fmt(r.markets)]}));
 const c=consData('ix/'+id);
 const name=(CONS_IX.find(x=>x[0]===id)||[])[1];
 if(c.err)return out+empty(`Could not load ${name} (${c.err}).`);
 if(!c.data)return out+empty(`Loading ${name}…`);
 return out+`<div class="panel"><h3>${esc(c.data.name)} <span class="muted">${esc(c.data.short)}${c.data.etf?' · '+esc(c.data.etf):''}</span></h3><div id="cons-ix"></div></div>`;
}
function consCalendar(){
 const g=consGate('calendar','The earnings calendar');if(!g.data)return g.html;
 const V=ConsensusView.fmt,rows=g.data.rows;exported=rows;
 if(!rows.length)return empty('No report on file in the next 45 days yet — the analysts\' data fills in over the first runs, largest companies first.');
 rows.sort((a,b)=>a.date.localeCompare(b.date)||(b.rev||0)-(a.rev||0));
 const wd=d=>new Date(d+'T12:00:00Z').toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',timeZone:'UTC'});
 let out=`<div class="section-head"><h3>Reports in the next 45 days — ${fmt(rows.length)} companies</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Consensus EPS with the range of estimates and the number of analysts; the EPS change over 30 days; the Polymarket price of "beats" with its line (the Street estimate when the market opened); and how often the company beat in its last eight reports. Largest companies first within a day.</p>`;
 out+=table(['Date','Company','EPS estimate','Range','Analysts','Revenue estimate','EPS change, 30 days','Market: beats?','Beat rate, last 8'],rows.map(r=>[`${esc(wd(r.date))}${r.estimated_date?' <span class="muted">(est.)</span>':''}`,`${consTk(r.ticker)} <span class="muted">${esc(shortName(r.name||''))}</span>`,V.usd(r.eps),`${V.usd(r.eps_low)} – ${V.usd(r.eps_high)}`,fmt(r.n),V.big(r.rev),
   r.eps_rev_30d==null?'—':`<span class="${r.eps_rev_30d>0?'positive':r.eps_rev_30d<0?'negative':''}">${V.spct(r.eps_rev_30d)}</span>`,r.beat_prob==null?'—':`<b>${V.pct(r.beat_prob)}</b> <span class="muted">line ${V.usd(r.pm_strike)}</span>`,r.beat_rate==null?'—':V.pct(r.beat_rate)]));
 return out;
}
function consScreen(){
 const g=consGate('index','The consensus data');if(!g.data)return g.html;
 const V=ConsensusView.fmt,F=g.data.fields;let rows=g.data.rows.map(r=>consRow(F,r)).filter(r=>r.eps_q!=null||r.poly_markets||r.kalshi_events);
 const f=state.cflt,today=new Date().toISOString().slice(0,10),soon=new Date(Date.now()+14*864e5).toISOString().slice(0,10);
 if(f==='pm')rows=rows.filter(r=>r.poly_markets||r.kalshi_events);else if(f==='up')rows=rows.filter(r=>r.eps_rev_30d>0.005);else if(f==='down')rows=rows.filter(r=>r.eps_rev_30d<-0.005);
 else if(f==='soon')rows=rows.filter(r=>r.next_earnings&&r.next_earnings>=today&&r.next_earnings<=soon);
 rows.sort((a,b)=>(b.poly_markets+b.kalshi_events)-(a.poly_markets+a.kalshi_events)||(b.rev_q||0)-(a.rev_q||0));
 exported=rows;
 const up=(v,p)=>v==null||!p?'':`<span class="${v>p?'positive':'negative'}">${V.spct(v/p-1)}</span>`;
 return `<div class="section-head"><h3>${fmt(rows.length)} companies</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Price targets, market-implied prices and our forecast are shown with the move they imply from today's price. Click a ticker for the company.</p>`+
  table(['Company','Price','Next report','EPS est. (quarter)','EPS change, 30d','Analysts\' target','Rating (1 = buy)','Market: beats?','Market-implied price','Our model','Beat rate','Markets'],rows.slice(0,600).map(r=>[`${consTk(r.ticker)} <span class="muted">${esc(shortName(r.name||''))}</span>`,V.usd(r.price),esc(r.next_earnings||'—'),r.eps_q==null?'—':`${V.usd(r.eps_q)} <span class="muted">${fmt(r.eps_q_n)}</span>`,
   r.eps_rev_30d==null?'—':`<span class="${r.eps_rev_30d>0?'positive':r.eps_rev_30d<0?'negative':''}">${V.spct(r.eps_rev_30d)}</span>`,r.target_mean==null?'—':`${V.usd(r.target_mean)} ${up(r.target_mean,r.price)}`,r.rating_mean==null?'—':fmt(r.rating_mean,1),
   r.pm_beat_prob==null?'—':`<b>${V.pct(r.pm_beat_prob)}</b> <span class="muted">${V.usd(r.pm_eps_strike)}</span>`,r.pm_implied_price==null?'—':`${V.usd(r.pm_implied_price)} ${up(r.pm_implied_price,r.price)} <span class="muted">${esc((r.pm_price_date||'').slice(5))}</span>`,
   r.our_price==null?'—':`${V.usd(r.our_price)} ${up(r.our_price,r.price)}`,r.beat_rate==null?'—':V.pct(r.beat_rate),(r.poly_markets||r.kalshi_events)?`${r.poly_markets?r.poly_markets+' P':''}${r.poly_markets&&r.kalshi_events?' · ':''}${r.kalshi_events?r.kalshi_events+' K':''}`:'—']));
}
function consMarkets(){
 const g=consGate('markets','The prediction markets');if(!g.data)return g.html;
 const V=ConsensusView.fmt,K=ConsensusView.KIND;const yd=new Date(Date.now()-864e5).toISOString().slice(0,10);let rows=g.data.rows.filter(m=>!m.closed&&(!m.end||m.end>=yd));
 if(state.cabout==='co')rows=rows.filter(m=>!m.index);else if(state.cabout==='ix')rows=rows.filter(m=>m.index);
 if(state.ckind)rows=rows.filter(m=>m.kind===state.ckind);if(state.csrc)rows=rows.filter(m=>m.source===state.csrc);
 if(state.cprob)rows=rows.filter(m=>Number.isFinite(+m.p)&&m.p!==null&&(state.cprob==='low'?+m.p<.25:state.cprob==='high'?+m.p>.75:+m.p>=.25&&+m.p<=.75));
 if(+state.cvol>0)rows=rows.filter(m=>m.volume!=null&&Number.isFinite(+m.volume)&&+m.volume>=+state.cvol);
 if(state.cdatefrom)rows=rows.filter(m=>m.end&&m.end.slice(0,10)>=state.cdatefrom);
 if(state.cdateto)rows=rows.filter(m=>m.end&&m.end.slice(0,10)<=state.cdateto);
 rows.sort((a,b)=>String(a.end).localeCompare(String(b.end))||(b.volume||0)-(a.volume||0));
 exported=rows.map(m=>({source:m.source,kind:m.kind,ticker:m.ticker,title:m.title,end:m.end,p:m.p,volume:m.volume,eps_line:m.eps_strike,median:m.median,url:m.url}));
 const what=m=>{if(m.kind==='beat')return `<b>${V.pct(m.p)}</b> beat <span class="muted">line ${V.usd(m.eps_strike)} · report ${esc(m.report_date||'')}</span>`;
  if(m.kind==='mcap')return m.median==null?'—':`median ${V.big(m.median)}${m.implied_price&&m.implied_price.median?` <span class="muted">≈ ${V.usd(m.implied_price.median)} a share</span>`:''}`;
  const pf=v=>v==null?'—':fmt(v,Math.abs(v)>=1000?0:2);
  if((m.kind==='above'||m.kind==='bracket')&&m.index)return m.median==null?'—':`median ${m.points?pf(m.median):`${V.usd(m.median)} ${m.implied_price?'≈ '+pf(m.implied_price.median):''}`}${m.implied_price&&m.implied_price.q10!=null?` <span class="muted">80% ${pf(m.implied_price.q10)}–${pf(m.implied_price.q90)} pts</span>`:''}`;
  if(m.kind==='above'||m.kind==='bracket')return m.median==null?'—':`median ${V.usd(m.median)}${m.implied_price&&m.implied_price.q10!=null?` <span class="muted">80% ${V.usd(m.implied_price.q10)}–${V.usd(m.implied_price.q90)}</span>`:''}`;
  if(m.kind==='metric')return m.median==null?'—':`median ${V.unitFmt(m.median,m.unit)}`;
  if(m.kind==='updown')return `up <b>${V.pct(m.p)}</b>`;
  if(m.kind==='hit')return m.index&&m.points?`even odds: high ${fmt(m.high,0)}${m.low!=null?', low '+fmt(m.low,0):''}`:`even odds: high ${V.usd(m.high)}, low ${V.usd(m.low)}`;
  if(m.kind==='kpi'&&m.median!=null)return `median ${fmt(m.median,2)}`;
  return (m.top||[]).map(o=>`${esc(String(o.q||'').slice(0,40))} <b>${V.pct(o.p)}</b>`).join(' · ')||'—'};
 return `<div class="section-head"><h3>${fmt(rows.length)} open markets about listed companies and the indices</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Every open Polymarket and Kalshi market we could tie to a company on Filing Flows or to an index (S&P 500, Nasdaq-100, Dow, Russell 2000, VIX), soonest first.</p>`+
  table(['Ends','About','Market','Kind','Consensus','Volume','Source'],rows.slice(0,800).map(m=>[esc(m.end||''),consTk(m.ticker,m.index),`<a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title||'')}</a>${m.subtitle?` <span class="muted">${esc(m.subtitle)}</span>`:''}`,esc(K[m.kind]||m.kind),what(m),m.volume==null?'—':V.big(m.volume),m.source==='kalshi'?'Kalshi':'Polymarket']));
}
function consTrack(){
 const g=consGate('calibration','The track record');if(!g.data)return g.html;
 const V=ConsensusView.fmt,D=g.data,P=D.price||{};
 let out='';
 if(D.n){
  const W=320,H=260,L=40,R=10,T=10,B=32,X=v=>L+v*(W-L-R),Y=v=>T+(1-v)*(H-T-B);
  let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" style="max-width:360px" role="img" aria-label="Reliability of Polymarket beat prices"><line class="mk-grid" x1="${X(0)}" y1="${Y(0)}" x2="${X(1)}" y2="${Y(1)}" stroke-dasharray="4 3"/>`;
  [0,.25,.5,.75,1].forEach(v=>{s+=`<text class="axis" x="${L-5}" y="${Y(v)+4}" text-anchor="end">${V.pct(v)}</text><text class="axis" x="${X(v)}" y="${H-16}" text-anchor="middle">${V.pct(v)}</text>`});
  s+=`<text class="axis" x="${(L+W-R)/2}" y="${H-2}" text-anchor="middle">price of "beats" a day before</text>`;
  (D.bins||[]).forEach(([c,mp,hit,n])=>{s+=`<circle cx="${X(mp)}" cy="${Y(hit)}" r="${3+Math.sqrt(n)}" style="fill:#8a4fd6;fill-opacity:.55;stroke:#8a4fd6"><title>${n} markets priced ${V.pct(mp)} on average: ${V.pct(hit)} beat</title></circle>`});
  s+='</svg>';
  out+=`<div class="panel"><h3>Polymarket "beat quarterly earnings" — ${fmt(D.n)} resolved markets</h3><p class="sub">The price 24 hours before the market closed against what happened. Brier score ${fmt(D.brier,3)} (lower is better; always saying the base rate of ${V.pct(D.base_rate)} would score ${fmt(D.brier_base_rate,3)}); the side above 50% was right ${V.pct(D.hit_rate)} of the time. Points on the dashed line are perfectly calibrated.</p>${s}</div>`;
 }else out+=empty('No resolved earnings market has been scored yet — each closed Polymarket earnings market is read once, with its price a day before the result.');
 if(P.n){
  const rows=D.price_rows||[];exported=rows;
  out+=`<div class="panel"><h3>Price, market-cap and reported-metric ladders — ${fmt(P.n)} resolved</h3><p class="sub">The last implied median we saw before the date against where the price ended (the middle of the resolved bracket). Mean absolute error ${fmt(P.mean_abs_err_pct,1)}%; the end fell inside the 80% range ${V.pct(P.inside80)} of the time (80% would be right).</p>`+
   table(['Date','Company','Market','Implied median','80% range','Ended','Error'],rows.slice(0,100).map(r=>{const f=r.kind==='mcap'?V.big:r.kind==='metric'?v=>V.unitFmt(v,r.unit):v=>V.usd(v);return [esc(r.end),consTk(r.ticker),`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`,f(r.median),`${f(r.q10)} – ${f(r.q90)}`,`${f(r.actual[0])} – ${r.actual[1]==null?'…':f(r.actual[1])}`,`<span class="${r.inside80?'positive':'negative'}">${V.spct(r.err_pct/100)}</span>`]}))+'</div>';
 }else out+=empty('No price ladder has resolved since tracking began: the last implied median before each date is kept, then scored when the market resolves.');
 out+=`<div class="panel" id="cons-lad-track"><p class="sub">Loading the hourly closing-price ladders…</p></div>`;
 out+=`<p class="sub">Analysts' record: each company page shows the consensus against the reported EPS for every quarter on file. Our model's record is in the Rotation tab → Track record.</p>`;
 return out;
}
function consCompany(){
 const g=consGate('index','The consensus data');if(!g.data)return g.html;
 const F=g.data.fields,q=String(state.cq||'').trim().toUpperCase();
 if(!q)return empty('Type a ticker (or click one in the other views).');
 const r=g.data.rows.map(x=>consRow(F,x)).find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
 if(!r)return empty(`${q} has no consensus data yet — analysts' estimates are read for every company over the first runs, largest first.`);
 const c=consData('c/'+r.cik);
 if(c.err)return empty('Could not load '+q+' ('+c.err+')');
 if(!c.data)return empty('Loading '+q+'…');
 return `<div class="panel"><h3>${esc(c.data.name||q)} <span class="muted">${esc(r.ticker||'')}</span> <a class="tk" href="../#c-${r.cik}-consensus">open on the company page →</a></h3><div id="cons-view"></div></div>`;
}
function bindConsensus(){
 if(state.tab!=='consensus')return;
 for(const k of ['cview','ckind','csrc','cprob','cvol','cflt','cidx','cabout'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 for(const k of ['cdatefrom','cdateto'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 if($('cq')){$('cq').onchange=e=>{state.cq=e.target.value;render()};$('cq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-cco]').forEach(b=>b.onclick=()=>{state.cview='company';state.cq=b.dataset.cco;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-cix]').forEach(b=>b.onclick=()=>{state.cview='market';state.cidx=b.dataset.cix;render();scrollTo({top:0,behavior:'smooth'})});
 const lt=$('cons-lad-track');if(lt&&window.ConsensusView&&ConsensusView.ladderTrack)ConsensusView.ladderTrack(lt);
 const ie=$('cons-ix');
 if(ie){const c=consData('ix/'+(state.cidx||'spx'));if(c.data&&window.ConsensusView)ConsensusView.renderIndex(ie,c.data)}
 const el=$('cons-view');
 if(el){const g=consData('index');const q=String(state.cq||'').trim().toUpperCase();const r=g.data&&g.data.rows.map(x=>consRow(g.data.fields,x)).find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
  const c=r&&consData('c/'+r.cik);if(c&&c.data&&window.ConsensusView)ConsensusView.render(el,c.data)}
}
