/* Price paths & patterns — the hub tab: every company's 13-week risk from seven correlated path models and their
   ensemble, analogs and correlated-asset historical simulation, rule-based price action with pooled out-of-sample
   evidence, portfolios of 13F managers and officials, the models' scorecard and the frozen-forecast ledger.
   Data: data/research/paths/{index,models,rules,ledger,status}.json, c/<cik>.json, portfolios/… (app/paths.py, branch
   research-paths). One company and one portfolio are drawn by paths-view.js (shared with the main site's company page).
   Deep links: #paths/<TICKER>, #paths/m-<cik>, #paths/o-<slug>. */
const pvStore={};
function pvData(name){
 const m=pvStore[name]||(pvStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/paths/'+name+'.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const PV_VIEWS=[['all','Every company'],['company','One company'],['rules','Price-action rules & evidence'],['models','Model scorecard'],['portfolios','13F & officials\' portfolios'],['ledger','Track record']];
const PV_SORT=[['p_down10','Highest chance of a 10% fall'],['p_up10','Highest chance of a 10% rise'],['vol','Most volatile'],['crash_market','Falls most with the market'],['self_up','Analogs most positive'],['bull_signals','Most bullish signals with evidence'],['bear_signals','Most bearish signals with evidence']];
const PV_FAM=[['','All families'],['candlestick','Candlesticks'],['brooks','Al Brooks'],['structure','Market structure'],['pattern','Chart patterns'],['wyckoff','Wyckoff'],['vsa','Volume spread analysis'],['profile','Volume profile'],['levels','Support / resistance'],['ict','ICT / smart money'],['elliott','Elliott wave'],['quant','Quantitative']];
function pvRows(d,fk='fields',rk='rows'){const F=d[fk]||[];return (d[rk]||[]).map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o})}
function pvP(v){return v==null?'—':fmt(v*100,0)+'%'}
function pvS(v){return v==null?'—':`<span class="${v>=0?'positive':'negative'}">${v>=0?'+':'−'}${fmt(Math.abs(v*100),1)}%</span>`}
function pvEv(e){const g=e||'none';return `<span class="tag" style="${g==='strong'?'color:var(--mk-profit)':g==='moderate'?'color:var(--accent)':g==='weak'?'color:var(--q-warm)':''}">${esc(g)}</span>`}
function pathsView(){
 state.pvv=PV_VIEWS.some(v=>v[0]===state.pvv)?state.pvv:'all';
 let out=head('Price paths &amp; patterns','How wide the next 13 weeks could be when a stock moves with the market, its sector and its peers (seven models), what followed the most similar moments in history, and what rule-based price action says — every method scored out of sample. A description of risk, not a forecast to trade on.','DAILY BARS · 7 PATH MODELS · ANALOGS · PRICE ACTION');
 out+=`<div class="toolbar">${field('pvv','View',PV_VIEWS,state.pvv)}`;
 if(state.pvv==='all')out+=field('pvs','Sort',PV_SORT,state.pvs||'p_down10');
 if(state.pvv==='rules')out+=field('pvf','Family',PV_FAM,state.pvf||'');
 if(state.pvv==='company')out+=`<div class="field wide"><label for="pvq">Company (ticker)</label><input id="pvq" value="${esc(state.pvq||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 out+='</div>';
 if(state.pvv==='rules')return out+pvRules();
 if(state.pvv==='models')return out+pvModels();
 if(state.pvv==='portfolios')return out+pvPortfolios();
 if(state.pvv==='ledger')return out+pvLedger();
 const g=pvData('index');
 if(g.err)return out+empty(`The price paths could not load (${g.err}). They are built every day after the close by .github/workflows/research-paths.yml; the first runs fetch ten years of daily bars.`);
 if(!g.data)return out+empty('Loading the price paths…');
 const rows=pvRows(g.data);
 if(state.pvv==='company'){
  const q=String(state.pvq||'').trim().toUpperCase();
  if(!q)return out+empty('Type a ticker to see its price paths, analogs and price-action readings.');
  const r=rows.find(x=>String(x.ticker||'').toUpperCase()===q||String(x.cik)===q);
  if(!r)return out+empty(`No price paths for ${q}: the build covers the companies on the valuation page once their daily bars are on file.`);
  return out+`<div class="panel"><h3>${esc(r.ticker)} <span class="muted">${esc(r.name||'')}</span></h3><div id="pv-one" data-cik="${esc(r.cik)}"></div></div>`;
 }
 const k=state.pvs||'p_down10';
 const R=rows.slice().sort((a,b)=>{const x=a[k],y=b[k];return x==null?1:y==null?-1:y-x});
 exported=R;
 const med=a=>{a=a.filter(v=>v!=null).sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:null};
 out+=`<div class="metrics">${kpi('Companies',fmt(rows.length),'with daily bars and paths')}${kpi('Median chance of a 10% fall',pvP(med(rows.map(r=>r.p_down10))),'in 13 weeks, ensemble')}${kpi('Median chance of a 10% rise',pvP(med(rows.map(r=>r.p_up10))),'in 13 weeks, ensemble')}${kpi('Median volatility',pvP(med(rows.map(r=>r.vol))),'annualized')}</div>`;
 out+=`<div class="section-head"><h3>Every company</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Company','Price','Median in 13 weeks','80% range','P(−10%)','P(+10%)','Volatility','Falls with the market','Analogs: share that rose','Always in','Structure','Signals with evidence','Moves most with'],
  R.slice(0,400).map(r=>[`<button class="text-button" data-pvco="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button> <span class="muted">${esc(r.name||'')}</span>`,fmt(r.price,2),pvS(r.p50),`${pvS(r.p10)} – ${pvS(r.p90)}`,pvP(r.p_down10),pvP(r.p_up10),pvP(r.vol),pvP(r.crash_market),pvP(r.self_up),esc(r.always_in||'—'),esc(r.structure||'—'),`<span class="positive">${fmt(r.bull_signals||0)}↑</span> <span class="negative">${fmt(r.bear_signals||0)}↓</span>`,esc(r.top_peer||'—')]))
  +`<div class="explain">Ensemble of seven path models (joint and block bootstrap, filtered historical simulation, factor model, Cholesky, t-copula, DCC-GARCH) on three years of daily returns of the stock, the S&P 500 ETF, its sector ETF and its two most correlated peers. "Falls with the market": the chance the stock ends 10% lower in the paths where the market does. Signals: price-action signals of the last ten days whose rule has moderate or strong out-of-sample evidence.</div>`;
}
function pvRules(){
 const g=pvData('rules');if(g.err)return empty(`The rules could not load (${g.err}).`);if(!g.data)return empty('Loading the rules…');
 const R=(g.data.rules||[]).filter(r=>!state.pvf||r.family===state.pvf);
 const H=['5','20','60'];
 const st=(r,h)=>{const s=(r.stats||{});const o=(s.oos||{})[h]||(s[h]||{}).oos||{};return o};
 const evd=(r,h)=>{const e=(r.stats||{}).evidence;return e&&typeof e==='object'?e[h]:e};
 const cnt={strong:0,moderate:0,weak:0,none:0};(g.data.rules||[]).forEach(r=>{const e=evd(r,'20')||'none';cnt[e]=(cnt[e]||0)+1});
 let out=`<div class="metrics">${kpi('Rules tested',fmt((g.data.rules||[]).length),`${fmt(g.data.tickers)} stocks, daily bars`)}${kpi('Strong evidence (20 days)',fmt(cnt.strong),'significant out of sample after correction')}${kpi('Moderate',fmt(cnt.moderate),'p < 5% out of sample')}${kpi('None',fmt(cnt.none),'no reliable effect')}</div>`;
 out+=`<div class="explain">Each rule run on every stock with no look-ahead; the return over the next 5, 20 and 60 trading days compared with the stock's own average, signed by the rule's direction (positive = the rule worked). In sample before ${esc(g.data.split||'2021-01-01')}, out of sample after; standard errors clustered by month; out-of-sample p-values corrected with the Benjamini–Hochberg procedure (false discovery rate 10%). Subjective schools (ICT, Elliott, Wyckoff, Al Brooks) are rule-based approximations.</div>`;
 exported=R.map(r=>({id:r.id,name:r.name,family:r.family,evidence_20d:evd(r,'20')}));
 return out+table(['Rule','Family','Signals (in / out of sample)','Out of sample, 5 days','20 days','60 days','Hit rate (20 days)','Evidence 5 · 20 · 60'],
  R.map(r=>{const s=r.stats||{};return [`<b>${esc(r.name)}</b>${r.subjective?' <span class="muted">(subjective)</span>':''}<br><span class="muted" style="white-space:normal;display:block;max-width:420px">${esc(r.what||'')}</span>`,esc(r.family),`${fmt(s.n_is)} / ${fmt(s.n_oos)}`,
   ...H.map(h=>{const o=st(r,h);return o.mean==null?'—':`${pvS(o.mean)} <span class="muted">t ${fmt(o.t,1)}</span>`}),pvP((st(r,'20')||{}).hit),H.map(h=>pvEv(evd(r,h))).join(' ')]}));
}
function pvModels(){
 const g=pvData('models');if(g.err)return empty(`The scorecard could not load (${g.err}).`);if(!g.data)return empty('Loading the scorecard…');
 const M=g.data,P=M.paths||{},A=M.analogs||{};
 const nm=k=>((M.info||{}).paths||{})[k]?.name||k;
 let out=`<div class="explain">Each method run at past dates (every ${fmt(126)} trading days) on a fixed sample of ${fmt((M.tickers||[]).length)} companies, using only data available before each date, against what happened over the next ${fmt(M.horizon||63)} trading days. A well-calibrated 80% range holds the outcome about 80% of the time; the pinball loss scores the whole distribution (lower is better); skill is the improvement over the naive baseline. Built ${esc((M.built_at||'').slice(0,10))}.</div>`;
 out+=`<div class="section-head"><h3>Path models</h3></div>`+table(['Model','Forecasts','80% range held','50% range held','Mean width of the 80% range','Pinball loss','Skill vs naive'],
  Object.entries(P).map(([k,r])=>[esc(nm(k)),fmt(r.n),pvP(r.cover80),pvP(r.cover50),pvP(r.width80),fmt(r.pinball,4),r.skill==null?'—':pvS(r.skill)]));
 out+=`<div class="section-head"><h3>Analog methods</h3></div>`+table(['Method','Forecasts','80% range held','50% range held','Pinball loss','Rank correlation with the outcome'],
  Object.entries(A).map(([k,r])=>[esc(k),fmt(r.n),pvP(r.cover80),pvP(r.cover50),fmt(r.pinball,4),fmt(r.ic,3)]));
 return out;
}
function pvPortfolios(){
 if(state.pvport){const [kind,id]=state.pvport.split(':');return `<p><button class="text-button" data-pvpback="1">← All portfolios</button></p><div class="panel"><div id="pv-port" data-kind="${esc(kind)}" data-id="${esc(id)}"></div></div>`}
 const g=pvData('portfolios/index');if(g.err)return empty(`The portfolios could not load (${g.err}).`);if(!g.data)return empty('Loading the portfolios…');
 const M=pvRows(g.data,'managers_fields','managers'),O=pvRows(g.data,'officials_fields','officials');
 let out=`<div class="explain">Each 13F manager's latest disclosed portfolio (weights by value), and each official's disclosed purchases minus sales over two years at the midpoint of each range (an approximation: officials report transactions, not positions), simulated with the S&P 500 ETF by the same seven models.</div>`;
 out+=`<div class="section-head"><h3>13F managers</h3></div>`+table(['Manager','Covered weight','P(−10%) in 13 weeks','Typical worst drawdown'],M.map(r=>[`<button class="text-button" data-pvport="m:${esc(r.cik)}"><b>${esc(r.name)}</b></button>`,pvP(r.coverage),pvP(r.p_down10),pvP(r.mdd50)]));
 out+=`<div class="section-head"><h3>Officials</h3></div>`+table(['Official','Covered weight','P(−10%) in 13 weeks','Typical worst drawdown'],O.map(r=>[`<button class="text-button" data-pvport="o:${esc(r.slug)}"><b>${esc(r.name)}</b></button>`,pvP(r.coverage),pvP(r.p_down10),pvP(r.mdd50)]));
 return out;
}
function pvLedger(){
 const g=pvData('ledger');if(g.err)return empty(`The track record could not load (${g.err}).`);if(!g.data)return empty('Loading…');
 const W=(g.data.weeks||[]).slice().reverse();
 let out=`<div class="explain">Every Friday's forecasts are frozen when first published (the 10 / 25 / 50 / 75 / 90% points of each model's 63-day range for every company) and scored once 63 trading days have passed: the share of actual closes inside the 80% and 50% ranges, and the typical gap between the median and the outcome.</div>`;
 const res=W.filter(w=>w.resolved);
 if(!res.length)out+=empty(`${fmt(W.length)} week(s) frozen; the first scores appear 63 trading days after the first freeze.`);
 return out+table(['Week','Companies','Scored','Ensemble: 80% held','50% held','Median gap','Best-calibrated model'],W.map(w=>{const m=w.models||{},e=m.ensemble||{};
  const best=Object.entries(m).filter(([k])=>k!=='ensemble').sort((a,b)=>Math.abs(a[1].cover80-0.8)-Math.abs(b[1].cover80-0.8))[0];
  return [esc(w.week),fmt(w.n),w.resolved?'yes':'not yet',pvP(e.cover80),pvP(e.cover50),e.mae_log==null?'—':fmt(e.mae_log*100,1)+'%',best?esc(best[0])+' '+pvP(best[1].cover80):'—']}));
}
function bindPaths(){
 if(state.tab!=='paths')return;
 for(const k of ['pvv','pvs','pvf'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;if(k==='pvv')state.pvport='';render()};
 if($('pvq')){$('pvq').onchange=e=>{state.pvq=e.target.value;render()};$('pvq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-pvco]').forEach(b=>b.onclick=()=>{state.pvv='company';state.pvq=b.dataset.pvco;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-pvport]').forEach(b=>b.onclick=()=>{state.pvport=b.dataset.pvport;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-pvpback]').forEach(b=>b.onclick=()=>{state.pvport='';render()});
 const one=$('pv-one');
 if(one&&window.PathsView&&one.dataset.drawn!==one.dataset.cik){one.dataset.drawn=one.dataset.cik;PathsView.render(one,{cik:one.dataset.cik,hub:''})}
 const port=$('pv-port');
 if(port&&window.PathsView&&PathsView.portfolio&&!port.dataset.drawn){port.dataset.drawn='1';PathsView.portfolio(port,{kind:port.dataset.kind,id:port.dataset.id,hub:''})}
}
function pathsDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(/^[mo]-/.test(v)){state.pvv='portfolios';state.pvport=v[0]+':'+v.slice(2)}
 else if(PV_VIEWS.some(x=>x[0]===v)){state.pvv=v}
 else{state.pvv='company';state.pvq=v.toUpperCase()}
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { paths: pathsView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { paths: bindPaths });
