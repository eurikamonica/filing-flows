/* Opportunity — the hub tab: for every stock and ETF, the chance the price is higher in 1 week, 1 month and 3 months,
   that a buy makes money after trading costs, that a short makes money after costs and the borrow fee, the likely range,
   the edge the signals add, the flag and the score; the walk-forward model card (calibration, edge deciles, flagged
   against all, the signals' weights, year by year) and the frozen weekly track record.
   Data: data/market/history/opportunity-stocks.json and opportunity-ledger-stocks.json (rotation-history),
   data/etf/opportunity-etfs.json and opportunity-ledger-etfs.json (etf-history); app/opportunity.py. One name is drawn by
   opportunity-view.js (shared with the company pages). Deep links: #opportunity/NVDA, #opportunity/etfs~QQQ,
   #opportunity/etfs, #opportunity/model, #opportunity/ledger. */
const opStore={};
const OP_PATH={stocks:'data/market/history/opportunity-stocks.json',etfs:'data/etf/opportunity-etfs.json',
 'ledger-stocks':'data/market/history/opportunity-ledger-stocks.json','ledger-etfs':'data/etf/opportunity-ledger-etfs.json'};
function opData(name){
 const m=opStore[name]||(opStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch(OP_PATH[name],{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const OP_VIEWS=[['all','Every name'],['one','One name'],['model','Model card'],['ledger','Track record']];
const OP_KIND=[['stocks','Stocks'],['etfs','ETFs']];
const OP_H=[['1w','1 week'],['1m','1 month'],['3m','3 months']];
const OP_HN={'1w':'1 week','1m':'1 month','3m':'3 months'};
const OP_SORT=[['score','Score (best edge)'],['p_up','Most likely higher'],['p_down','Most likely lower'],['p_buy','Best odds for a buy'],['p_short','Best odds for a short'],['edge','Largest edge at this horizon']];
const OP_SIDE=[['','Every name'],['flag','Flagged only'],['buy','Buy flags'],['short','Short flags'],['none','Not flagged']];
const OP_LIQ=[['','Any liquidity'],['5e6','$5M+ a week'],['5e7','$50M+ a week'],['5e8','$500M+ a week']];
function opP(v,d=0){return v==null?'—':fmt(v*100,d)+'%'}
function opS(v,d=1){return v==null?'—':`<span class="${v>=0?'positive':'negative'}">${v>=0?'+':'−'}${fmt(Math.abs(v*100),d)}%</span>`}
function opPts(v){return v==null?'—':`${v>=0?'+':'−'}${fmt(Math.abs(v*100),1)} pts`}
function opFlag(s,h){return s==='buy'?`<span class="tag" style="color:var(--mk-profit)">buy · ${esc(OP_HN[h]||h)}</span>`:s==='short'?`<span class="tag" style="color:var(--negative,#b42318)">short · ${esc(OP_HN[h]||h)}</span>`:'<span class="muted">—</span>'}
function opCostMax(liq){return liq==='5e8'?0.0011:liq==='5e7'?0.0031:liq==='5e6'?0.0081:9}
function opKind(){return state.opk==='etfs'?'etfs':'stocks'}
function opportunityView(){
 state.opv=OP_VIEWS.some(v=>v[0]===state.opv)?state.opv:'all';
 const kind=opKind();
 let out=head('Opportunity','For every stock and ETF: the chance the price is higher in a week, a month and three months, that buying makes money after trading costs and that shorting does after costs and the borrow fee — with the likely range, the signals behind it and a flag only where flags have made money out of sample. Odds that lean, not predictions; history and models, not investment advice.','WEEKLY · WALK-FORWARD · COSTS INCLUDED');
 out+=`<div class="toolbar">${field('opv','View',OP_VIEWS,state.opv)}`;
 if(state.opv!=='one')out+=field('opk','Universe',OP_KIND,kind);
 if(state.opv==='all'){
  out+=field('oph','Horizon',OP_H,state.oph||'1m')+field('ops','Sort',OP_SORT,state.ops||'score')+field('opf','Flags',OP_SIDE,state.opf||'');
  const g=opData(kind);
  const secs=g.data?[...new Set(g.data.rows.map(r=>r.s))].sort():[];
  out+=field('opsec',kind==='etfs'?'Category':'Sector',[['','All'],...secs.map(s=>[s,s])],state.opsec||'')+field('opl','Liquidity',OP_LIQ,state.opl==null?'5e6':state.opl);
  out+=`<div class="field"><label for="opq">Search</label><input id="opq" value="${esc(state.opq||'')}" placeholder="ticker or name"></div>`;
 }
 if(state.opv==='one')out+=field('opk','Universe',OP_KIND,kind)+`<div class="field wide"><label for="opt">Ticker</label><input id="opt" value="${esc(state.opt||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 if(state.opv==='model')out+=field('oph','Horizon',OP_H,state.oph||'1m');
 out+='</div>';
 if(state.opv==='model')return out+opModel(kind);
 if(state.opv==='ledger')return out+opLedger(kind);
 if(state.opv==='one'){
  const t=String(state.opt||'').trim().toUpperCase().replace(/\./g,'-');
  if(!t)return out+empty('Type a ticker to see its odds.');
  return out+`<div id="op-one" data-t="${esc(t)}" data-k="${esc(kind)}"></div>`;
 }
 const g=opData(kind);
 if(g.err)return out+empty(`The odds could not load (${g.err}). They are rebuilt by .github/workflows/${kind==='etfs'?'etf.yml':'rotation-history.yml'} (app/opportunity.py).`);
 if(!g.data)return out+empty('Loading the odds…');
 const d=g.data,F=d.fields_h,ix=k=>F.indexOf(k),hk=state.oph||'1m',k=state.ops||'score';
 const q=String(state.opq||'').trim().toLowerCase(),cmax=opCostMax(state.opl==null?'5e6':state.opl);
 const val=r=>{const h=r.h[hk];if(!h)return null;return k==='score'?(r.score==null?null:r.score+(h[ix('edge')]||0)/10):k==='p_down'?1-h[ix('p_up')]:k==='edge'?h[ix('edge')]:h[ix(k)]};
 let R=d.rows.filter(r=>r.h[hk]&&(!state.opsec||r.s===state.opsec)&&r.h[hk][ix('cost')]<=cmax
  &&(!q||String(r.t).toLowerCase().includes(q)||String(r.n||'').toLowerCase().includes(q)));
 const f=state.opf||'';
 if(f==='flag')R=R.filter(r=>r.side!=='none');else if(f)R=R.filter(r=>r.side===f);
 R=R.slice().sort((a,b)=>{const x=val(a),y=val(b);return x==null?1:y==null?-1:y-x});
 const med=a=>{a=a.filter(v=>v!=null).sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:null};
 const c=(d.cards||{})[hk]||{};
 const on=s=>((c[s]||{}).flag_ok);
 out+=`<div class="metrics">${kpi(kind==='etfs'?'ETFs':'Stocks',fmt(d.rows.length),'week ending '+(d.asof||''))}${kpi('Buy flags',fmt(d.rows.filter(r=>r.side==='buy').length),'any horizon')}${kpi('Short flags',fmt(d.rows.filter(r=>r.side==='short').length),'any horizon')}${kpi('Median chance higher',opP(med(d.rows.map(r=>r.h[hk]&&r.h[hk][ix('p_up')]))),OP_HN[hk])}${kpi('Direction AUC',c.up&&c.up.auc!=null?fmt(c.up.auc,3):'—','walk-forward, 0.5 = coin')}</div>`;
 out+=`<div class="explain">At ${esc(OP_HN[hk])}: buy flags <b>${on('buy')?'on':'off'}</b>, short flags <b>${on('short')?'on':'off'}</b> — a side is flagged only at horizons where, out of sample, its flagged trades made money more often than not, on the median and on average after costs, and beat the average name. ${on('short')?'':'Shorts are often right more than half the time but lose on average (a few big rallies outweigh the wins), so they stay unflagged. '}See the model card.</div>`;
 exported=R.map(r=>{const h=r.h[hk];return {ticker:r.t,name:r.n,sector:r.s,score:r.score,side:r.side,best_horizon:r.best_h,horizon:hk,p_up:h[ix('p_up')],p_buy:h[ix('p_buy')],p_short:h[ix('p_short')],r_p10:h[ix('r_p10')],r_p50:h[ix('r_p50')],r_p90:h[ix('r_p90')],round_trip_cost:h[ix('cost')],edge:h[ix('edge')],hard_to_borrow:!!r.htb}});
 out+=`<div class="section-head"><h3>${esc(fmt(R.length))} ${kind==='etfs'?'ETFs':'stocks'} · ${esc(OP_HN[hk])}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 const L=d.labels||{};
 return out+table(['Name','Score','Flag here','Higher','Buy makes money','Short makes money','Likely range (10–90%)','Edge','Cost','Main signal'],
  R.map(r=>{const h=r.h[hk],dr=(r.drivers||[])[0];return [`<button class="text-button" data-opt="${esc(r.t)}"><b>${esc(r.t)}</b></button> <span class="muted">${esc(r.n||'')}</span><br><span class="muted">${esc(r.s||'')}</span>`,
   r.score==null?'—':fmt(r.score,0),opFlag(h[ix('side')],hk)+(r.side!=='none'&&r.best_h!==hk?`<br><span class="muted">best: ${esc(r.side)} · ${esc(OP_HN[r.best_h]||r.best_h)}</span>`:''),
   `<b class="${h[ix('p_up')]>=0.5?'positive':'negative'}">${opP(h[ix('p_up')])}</b>`,opP(h[ix('p_buy')]),opP(h[ix('p_short')])+(r.htb?' <span class="muted" title="Under $5, under $5M a week or a leveraged / inverse fund: likely hard or costly to borrow — never flagged short">HTB</span>':''),
   `${opS(h[ix('r_p10')],0)} – ${opS(h[ix('r_p90')],0)}`,opPts(h[ix('edge')]),opP(h[ix('cost')],2),
   dr?`<span style="white-space:normal;display:inline-block;min-width:150px"><span class="${dr[1]>=0?'positive':'negative'}">${dr[1]>=0?'↑':'↓'}</span> ${esc(L[dr[0]]||dr[0])}</span>`:'—']}))
  +`<div class="explain">Higher: the chance the total return over the horizon is above zero. Buy / short makes money: after the round-trip cost (0.1% for names trading $500M+ a week, 0.3% for $50M+, 0.8% for $5M+, else 2%) and, for a short, a 0.5% a year borrow fee. Edge: how much the timing signals raise the better of the two, against the same name with its own volatility, cost and liquidity and no signal. A flag also needs the trade itself to be more likely than not to make money. Score: where that edge ranks among every name this week, at the best horizon whose flags have worked (— when none has). HTB: likely hard to borrow, never flagged short. ${kind==='stocks'?'Today\'s companies only: names delisted in the past are missing from what the model learned (survivorship).':'Cash-like funds (under 3% a year of volatility) are left out.'}</div>`;
}
function opModel(kind){
 const g=opData(kind);if(g.err)return empty(`The model card could not load (${g.err}).`);if(!g.data)return empty('Loading the model card…');
 const d=g.data,hk=state.oph||'1m',c=(d.cards||{})[hk];if(!c)return empty('No model at this horizon.');
 const L=d.labels||{};
 let out=`<div class="explain">${esc(OP_HN[hk])} model, ${esc(kind)}: every year ${esc((c.oos_years||[]).join('–'))} predicted only from the years before it (${fmt(c.n)} name-weeks). Rank correlation between the predicted and the actual move, week by week: ${fmt(c.ic_mean,3)} on average (t ${fmt(c.ic_t,1)}). Brier skill: how much better the probabilities score than always saying the base rate (0 = no better).</div>`;
 out+=`<div class="section-head"><h3>Scores</h3></div>`+table(['Question','Base rate','Brier skill','AUC','Top tenth of the odds: happened','Bottom tenth: happened','Flags','Flagged: made money','All names','Flagged median net','All median net'],
  [['up','Higher'],['buy','A buy makes money'],['short','A short makes money']].map(([k,l])=>{const x=c[k]||{},f=x.flagged||{};return [esc(l),opP(x.rate,1),opS(x.brier_skill,2),fmt(x.auc,3),opP(x.top_decile,1),opP(x.bottom_decile,1),
   k==='up'?'—':(x.flag_ok?'<b class="positive">on</b>':'off'),k==='up'?'—':opP(f.hit,1),k==='up'?'—':opP(f.all_hit,1),k==='up'?'—':opS(f.net_median,2),k==='up'?'—':opS(f.all_net_median,2)]}));
 for(const [k,l] of [['buy','Buys'],['short','Shorts']]){
  const D=(c[k]||{}).edge_deciles||[];
  out+=`<div class="section-head"><h3>${l}: does a larger edge pay? (each tenth of the edge, out of sample)</h3></div>`+table(['Edge from','to','Name-weeks','Predicted','Made money','Average net (extreme 1% capped)','Median net'],
   D.map(r=>[opPts(r[0]),opPts(r[1]),fmt(r[2]),opP(r[3],1),opP(r[4],1),opS(r[5],2),opS(r[6],2)]));
 }
 const cal=(c.up||{}).calibration||[];
 out+=`<div class="section-head"><h3>Calibration: when it said X%, how often was it higher?</h3></div>`+table(['Said','Name-weeks','Average said','Happened'],cal.map(r=>[`${fmt(r[0]*100)}–${fmt(r[1]*100)}%`,fmt(r[2]),opP(r[3],1),opP(r[4],1)]));
 const co=Object.entries(c.coef||{}).filter(([k])=>k!=='const').sort((a,b)=>Math.abs(b[1])-Math.abs(a[1]));
 out+=`<div class="section-head"><h3>The signals' weights (the model for this week)</h3></div>`+table(['Signal','Weight','Reads as'],co.map(([k,v])=>[esc(L[k]||k),fmt(v,3),v>=0?'<span class="positive">more of it → higher odds</span>':'<span class="negative">more of it → lower odds</span>']));
 const Y=Object.entries(c.by_year||{}).sort((a,b)=>b[0]-a[0]);
 out+=`<div class="section-head"><h3>Year by year (direction)</h3></div>`+table(['Year','Name-weeks','Share higher','Brier skill','AUC'],Y.map(([y,v])=>[esc(y),fmt(v.n),opP(v.up_rate,1),opS(v.brier_base?1-v.brier/v.brier_base:null,2),fmt(v.auc,3)]));
 return out+`<div class="explain" style="white-space:pre-wrap">${esc(d.method||'')}</div>`;
}
function opLedger(kind){
 const g=opData('ledger-'+kind);if(g.err)return empty(`The track record could not load (${g.err}). The first week is frozen once the model has run after a week closes.`);if(!g.data)return empty('Loading…');
 const d=g.data,T=d.totals||{};
 let out=`<div class="explain">Every week's odds are frozen once the week has closed (from Sunday) and never edited; each horizon is scored once its outcome is known. ${fmt(d.frozen)} week(s) frozen, ${fmt(d.scored)} with at least one horizon scored.</div>`;
 if(Object.keys(T).length)out+=table(['Horizon','Weeks scored','Name-weeks','Higher: said','Happened','Brier skill','Buy flags: made money','All buys','Short flags: made money','All shorts'],
  OP_H.filter(([h])=>T[h]).map(([h,l])=>{const x=T[h];return [esc(l),fmt(x.origins),fmt(x.n),opP(x.up.p_mean,1),opP(x.up.rate,1),opS(x.up.skill,2),x.flag_buy.n?`${opP(x.flag_buy.hit,1)} of ${fmt(x.flag_buy.n)}`:'—',opP(x.all_buy.hit,1),x.flag_short.n?`${opP(x.flag_short.hit,1)} of ${fmt(x.flag_short.n)}`:'—',opP(x.all_short.hit,1)]}));
 else out+=empty('No horizon has closed yet: the first 1-week scores appear about nine days after the first freeze.');
 return out+`<div class="section-head"><h3>Weeks</h3></div>`+table(['Week','Names','1 week: higher said / happened','1 month','3 months','Buy flags made money (1 m)'],
  (d.origins||[]).map(o=>{const r=o.res||{},cell=h=>r[h]?`${opP(r[h].up.p_mean)} / ${opP(r[h].up.rate)}`:'<span class="muted">pending</span>';const fb=(r['1m']||{}).flag_buy;return [esc(o.date),fmt(o.n),cell('1w'),cell('1m'),cell('3m'),fb&&fb.n?`${opP(fb.hit)} of ${fmt(fb.n)}`:'—']}));
}
function bindOpportunity(){
 if(state.tab!=='opportunity')return;
 for(const k of ['opv','opk','oph','ops','opf','opsec','opl'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;if(k==='opk')state.opsec='';render()};
 for(const k of ['opq','opt'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-opt]').forEach(b=>b.onclick=()=>{state.opv='one';state.opt=b.dataset.opt;render();scrollTo({top:0,behavior:'smooth'})});
 const one=$('op-one');
 if(one&&window.OpportunityView){const key=one.dataset.k+'|'+one.dataset.t;if(one.dataset.drawn!==key){one.dataset.drawn=key;OpportunityView.render(one,{ticker:one.dataset.t,kind:one.dataset.k,hub:''})}}
}
function opportunityDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(v==='etfs'||v==='stocks'){state.opv='all';state.opk=v;return}
 if(OP_VIEWS.some(x=>x[0]===v)){state.opv=v;return}
 const [a,b]=v.split('~');
 if(b){state.opk=a==='etfs'?'etfs':'stocks';state.opv='one';state.opt=b.toUpperCase()}else{state.opv='one';state.opt=a.toUpperCase()}
}
function opportunityNotice(){
 const s=opData(opKind()),d=s.data;
 if(s.err)return {stale:true,text:'Official derived view · Opportunity unavailable · '+s.err};
 if(!d)return {stale:false,text:'Official derived view · Opportunity loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=30),text:`Official derived view · Opportunity built ${d.generated_at} · ${fmt(d.rows.length)} ${d.kind} · week ending ${d.asof} · rebuilt with the ${d.kind==='etfs'?'ETF data every few hours':'weekly closes every three hours'}`+(age>30?' · stale':'')};
}
window.opportunityDeepLink=opportunityDeepLink;
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{opportunity:opportunityNotice});
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{opportunity:opportunityView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{opportunity:bindOpportunity});
