/* Filings radar — the filings that flag trouble or change the share count, and the money around them:
     Red flags      late filing notices (NT 10-K / NT 10-Q), auditor changes (8-K 4.01), restatements (4.02), listing notices (3.01)
     SEC letters    comment letter threads (UPLOAD / CORRESP), the form reviewed and the topics
     Capital        buyback authorizations, upcoming dividends (record = ex-date), last year's buybacks + dividends vs market cap
     Dilution       shelf registrations, takedowns and at-the-market programs, the change in shares outstanding over a year
     IPOs           pricings, lock-ups ending soon, registrations in the pipeline
     Deals          pending mergers and tender offers: terms per share, spread, expected close, annualized spread
     CEO pay        pay versus performance (XBRL): pay against the shareholder return
     Contracts      federal contract obligations, lobbying, and officials' trades in those companies
     One company    everything above for one ticker (filings-view.js, also the main site's "Filings radar" company view)
   Data: data/research/filings/*.json (app/filings_radar.py, branch research-filings, every six hours). */
const frStore={};
function frData(name){
 const m=frStore[name]||(frStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/filings/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const FR_VIEWS=[['flags','Red flags'],['letters','SEC comment letters'],['capital','Buybacks & dividends'],['dilution','Dilution & offerings'],['ipos','IPOs & lock-ups'],['deals','Merger arbitrage'],['pay','CEO pay vs return'],['gov','Contracts, lobbying & officials'],['company','One company']];
const FR_FILE={flags:'redflags',letters:'letters',capital:'capital',dilution:'dilution',ipos:'ipos',deals:'deals',pay:'paycomp',gov:'gov'};
const frMoney=v=>v==null||!Number.isFinite(+v)?'—':(v<0?'−$':'$')+compact(Math.abs(v));
const frPct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)+'%';
const frCo=(r,tk,name)=>{const t=tk||r.ticker,n=name||r.company||'';return `${t?`<b>${esc(String(t).replace(/-/g,'.'))}</b> `:''}<span class="muted">${esc(n)}</span>${r.cik?` <a class="muted" href="../#c-${esc(r.cik)}" title="Company page">↗</a>`:''}`};
const frLink=(u,l)=>/^https:\/\//.test(u||'')?`<a target="_blank" rel="noopener" href="${esc(u)}">${esc(l||'Filing ↗')}</a>`:'—';
const frSev=s=>`<span class="pill" style="${s==='high'?'color:var(--mk-cost);border-color:var(--mk-cost)':s==='medium'?'color:var(--q-warm,#d9822b)':''}">${esc(s||'—')}</span>`;
function frQ(rows,keys){const q=(state.frq||'').trim().toLowerCase();return q?rows.filter(r=>keys.some(k=>String(r[k]||'').toLowerCase().includes(q))):rows}
function frSmall(head,rows,n=12){if(!rows.length)return '';return `<div class="tablebox"><table><thead><tr>${head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,n).map(c=>`<tr>${c.map((v,i)=>`<td class="${i?'num':''}">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function filingsView(){
 state.frv=FR_VIEWS.some(v=>v[0]===state.frv)?state.frv:'flags';
 const v=state.frv;
 let out=head('Filings radar','Red flags, SEC comment letters, buybacks and dividends, dilution, IPOs, deals, CEO pay, federal contracts and lobbying — read from SEC EDGAR, USAspending.gov and the Senate\'s lobbying filings every six hours','SEC / RADAR');
 out+=`<div class="toolbar">${field('frv','View',FR_VIEWS,v,true)}`;
 if(v==='flags')out+=field('frk','Kind',[['','All'],['late','Late filing notices'],['auditor','Auditor changes'],['restatement','Restatements'],['listing','Listing notices']],state.frk||'')+field('frs','Severity',[['','All'],['high','High'],['medium','Medium and high']],state.frs||'');
 if(v==='capital')out+=field('frc','Show',[['buybacks','Buyback authorizations'],['dividends','Upcoming dividends (record = ex-date)'],['returns','Last year: buybacks + dividends ÷ market cap']],state.frc||'buybacks');
 if(v==='dilution')out+=field('frd','Show',[['offerings','Offerings and ATM programs'],['growth','Most new shares in a year'],['shrink','Fewest shares (buybacks)']],state.frd||'offerings');
 if(v==='pay')out+=field('frp','Show',[['all','All'],['mis','Pay up 20%+ while TSR fell 10%+']],state.frp||'all');
 if(v==='gov')out+=field('frg','Show',[['overlap','Officials who traded these companies'],['contracts','Contracts by company (90 days)'],['awards','Largest new awards (14 days)'],['lobbying','Lobbying (4 quarters)']],state.frg||'overlap');
 if(v==='letters'){const lt=frData('letters');const T=(lt.data&&lt.data.topic_names)||{};out+=field('frt','Topic',[['','All topics'],...Object.entries(T)],state.frt||'')}
 out+=`<div class="field"><label for="frq">${v==='company'?'Ticker':'Ticker or name'}</label><input id="frq" value="${esc(state.frq||'')}" placeholder="${v==='company'?'e.g. AAPL':'filter'}"></div></div>`;
 if(v==='company'){
  const tk=(state.frq||'').trim().toUpperCase();
  return out+(tk?`<div id="fr-company" data-tk="${esc(tk)}"><p class="sub">Loading ${esc(tk)}…</p></div>`:empty('Type a ticker to see its red flags, SEC letters, buybacks, dividends, offerings, deals, CEO pay, contracts and lobbying.'));
 }
 const m=frData(FR_FILE[v]);
 if(m.err)return out+empty(`The filings radar could not load (${m.err}). It is built every six hours by the research-filings workflow; the first run reads two months of EDGAR indexes.`);
 if(!m.data)return out+empty('Loading…');
 const d=m.data;
 out+=`<div class="explain">${esc(d.note||'')} Not investment advice.</div>`;
 if(v==='flags'){
  let rows=(d.rows||[]).filter(r=>(!state.frk||r.kind===state.frk)&&(!state.frs||(state.frs==='high'?r.severity==='high':r.severity!=='low')));
  rows=frQ(rows,['ticker','company']);
  const L=d.last30||{};
  out+=`<div class="metrics">${kpi('High severity, 30 days',fmt(L.high),'auditor resignations, restatements, late 10-Ks …')}${kpi('Medium, 30 days',fmt(L.medium),'')}${kpi('Low, 30 days',fmt(L.low),'e.g. bid-price notices')}${kpi('On file',fmt((d.rows||[]).length),'last 12 months')}</div>`;
  exported=rows;
  out+=`<div class="section-head"><h3>Red flags, newest first</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Filed','Company','What','Severity','Market cap','Source'],rows.map(r=>[esc(r.filed),frCo(r),`<span style="white-space:normal;display:block;max-width:520px">${window.FilingsRadarView?window.FilingsRadarView.flagLine(r):esc(r.label)}</span>`,frSev(r.severity),frMoney(r.mcap),frLink(r.url)]));
  return out;
 }
 if(v==='letters'){
  const T=d.topic_names||{};
  let rows=(d.threads||[]).filter(t=>!state.frt||(t.topics||[]).includes(state.frt));
  rows=frQ(rows,['ticker','company']);
  const top=Object.entries(d.topics90||{}).sort((a,b)=>b[1]-a[1]).slice(0,4);
  out+=`<div class="metrics">${top.map(([k,n])=>kpi(T[k]||k,fmt(n),'threads, last 90 days')).join('')||kpi('Threads','0','')}</div>`;
  exported=rows.map(t=>({...t,letters:(t.letters||[]).length}));
  out+=`<div class="section-head"><h3>Comment letter threads</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out+=table(['Last letter','Company','Letters','Review of','Topics','What the staff asked','Source'],rows.map(t=>{const last=(t.letters||[]).slice(-1)[0]||{};const ex=(t.letters||[]).map(x=>x.excerpt).find(Boolean)||'';
   return [esc(t.last),frCo(t),fmt(t.n),esc((t.about_form||'—')+(t.about_period?' · '+t.about_period:'')),(t.topics||[]).map(k=>esc(T[k]||k)).join(', ')||'—',`<span style="white-space:normal;display:block;max-width:420px" class="muted">${esc(ex)}</span>`,frLink(last.url,'Letter ↗')]}));
  return out;
 }
 if(v==='capital'){
  const c=state.frc||'buybacks';
  if(c==='buybacks'){const rows=frQ(d.buybacks||[],['ticker','company']);exported=rows;
   out+=`<div class="section-head"><h3>Buyback authorizations (8-K)</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Filed','Company','Amount','% of market cap','Expires','Source'],rows.map(r=>[esc(r.filed),frCo(r),frMoney(r.amount)+(r.increase?' <span class="muted">added</span>':''),r.pct_mcap==null?'—':fmt(r.pct_mcap*100,1)+'%',r.no_expiration?'no expiration':esc(r.expires||'—'),frLink(r.url)]))}
  else if(c==='dividends'){const rows=frQ(d.upcoming||[],['ticker','company']);exported=rows;
   out+=`<div class="section-head"><h3>Upcoming dividends</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Record = ex-date','Company','Per share','Frequency','Payable','Change','Yield','Source'],rows.map(r=>[esc(r.record),frCo(r),'$'+fmt(r.amount,4),esc(r.freq||'—'),esc(r.payable||'—'),esc(r.change||'—'),r.yield==null?'—':fmt(r.yield*100,2)+'%',frLink(r.url)]))}
  else{const rows=frQ(d.returns||[],['ticker','company']);exported=rows;
   out+=`<div class="section-head"><h3>Last calendar year: buybacks + dividends ÷ market cap (XBRL)</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Company','Buybacks','Dividends','Buyback yield','Dividend yield','Total','Market cap'],rows.map(r=>[frCo(r),frMoney(r.buybacks),frMoney(r.dividends),fmt((r.buyback_yield||0)*100,1)+'%',fmt((r.dividend_yield||0)*100,1)+'%',fmt((r.total_yield||0)*100,1)+'%',frMoney(r.mcap)]))}
  return out;
 }
 if(v==='dilution'){
  const c=state.frd||'offerings';
  if(c==='offerings'){const rows=frQ(d.offerings||[],['ticker','company']);exported=rows;
   out+=`<div class="section-head"><h3>Shelf registrations, takedowns and at-the-market programs</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Filed','Company','Form','Kind','Size','% of market cap','Source'],rows.map(r=>[esc(r.filed),frCo(r),esc(r.form),esc({atm:'at-the-market',firm:'offering',shelf:r.automatic?'automatic shelf':'shelf',other:'other'}[r.kind]||r.kind),frMoney(r.amount),r.pct_mcap==null?'—':fmt(r.pct_mcap*100,1)+'%',frLink(r.url)]))}
  else{const rows=frQ(c==='growth'?(d.share_growth||[]):(d.share_shrink||[]),['ticker','company']);exported=rows;
   out+=`<div class="section-head"><h3>${c==='growth'?'Most new shares':'Fewest shares'} over four quarters</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Company','Shares a year ago','Shares now','Change','As of','Market cap'],rows.map(r=>[frCo(r),fmt(r.shares_year_ago),fmt(r.shares),frPct(r.change),esc(r.as_of||'—'),frMoney(r.mcap)]))}
  return out;
 }
 if(v==='ipos'){
  const lk=d.lockups||[];
  out+=lk.length?`<h3>Lock-ups ending in the next 45 days</h3>`+frSmall(['Lock-up ends','Company','IPO price','Last close','Since IPO','Raised'],lk.map(r=>[esc(r.lockup_ends),frCo(r,r.symbol),'$'+fmt(r.price,2),r.last_close==null?'—':'$'+fmt(r.last_close,2),frPct(r.since_ipo),frMoney(r.raised)]),20):'';
  const rows=frQ(d.priced||[],['symbol','company']);exported=rows;
  out+=`<div class="section-head"><h3>IPO pricings (424B4)</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Priced','Company','Price','Shares','Raised','Exchange','First day','Since IPO','Lock-up ends'],rows.map(r=>[esc(r.date||r.filed),frCo(r,r.symbol),'$'+fmt(r.price,2),fmt(r.shares),frMoney(r.raised),esc(r.exchange||'—'),frPct(r.first_day),frPct(r.since_ipo),esc(r.lockup_ends||'—')]));
  const reg=d.registered||[];
  if(reg.length)out+=`<h3>Registered, not priced yet (S-1 / F-1)</h3>`+frSmall(['Filed','Company','Form','Proposed symbol'],reg.map(r=>[esc(r.filed),frCo(r,r.symbol),esc(r.form),esc(r.symbol||'—')]),15);
  return out;
 }
 if(v==='deals'){
  const rows=frQ(d.deals||[],['target_ticker','target','acquirer','acquirer_ticker']);exported=rows;
  out+=`<div class="section-head"><h3>Mergers and tender offers</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Announced','Target','Acquirer','Terms per share','Target close','Value','Spread','Annualized','Expected close','Status'],rows.map(x=>[esc(x.announced),frCo({cik:x.target_cik,company:x.target},x.target_ticker,x.target),`${esc(x.acquirer||'—')}${x.acquirer_ticker?` <b>${esc(x.acquirer_ticker)}</b>`:''}`,[x.cash?'$'+fmt(x.cash,2)+' cash':'',x.ratio?fmt(x.ratio,4)+' shares':''].filter(Boolean).join(' + ')||'—',x.target_price==null?'—':'$'+fmt(x.target_price,2),x.value==null?'—':'$'+fmt(x.value,2),frPct(x.spread),frPct(x.annualized),esc(x.close_by||x.close_text||'—'),esc(x.status)]));
  return out;
 }
 if(v==='pay'){
  let rows=(d.rows||[]).filter(r=>state.frp!=='mis'||r.misaligned);rows=frQ(rows,['ticker','company']);exported=rows.map(r=>({...r,years:undefined}));
  out+=`<div class="section-head"><h3>CEO pay against the shareholder return</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Company','Fiscal year','Total pay','Change','Actually paid','TSR ($100)','TSR change','Peer TSR','Pay–TSR correlation'],rows.map(r=>[frCo(r),esc(r.fy_end),frMoney(r.total),frPct(r.total_chg),frMoney(r.cap),fmt(r.tsr,0),frPct(r.tsr_chg),fmt(r.peer_tsr,0),r.corr==null?'—':fmt(r.corr,2)]));
  return out;
 }
 if(v==='gov'){
  const c=state.frg||'overlap';
  if(c==='overlap'){const rows=frQ(d.overlap||[],['ticker','person']);exported=rows;
   out+=`<div class="section-head"><h3>Officials who traded companies with large contracts or lobbying</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Trade date','Official','Company','Trade','Amount','Contracts (90 days)','Lobbying (4 quarters)','Report'],rows.map(r=>[esc(r.date),`${esc(r.person)} <span class="muted">${esc(r.chamber)}</span>`,`<b>${esc(r.ticker)}</b>`,esc(r.type),r.amount_max?`${frMoney(r.amount_min)}–${frMoney(r.amount_max)}`:`over ${frMoney(r.amount_min)}`,frMoney(r.contracts_90d),frMoney(r.lobbying_4q)+((r.lobbying_issues||[]).length?` <span class="muted">${esc(r.lobbying_issues.slice(0,2).join(', '))}</span>`:''),frLink(r.source_url,'Report ↗')]))}
  else if(c==='contracts'){const rows=frQ(d.contracts||[],['ticker']);exported=rows;
   out+=`<div class="section-head"><h3>Federal contract obligations, ${esc(d.since||'')} – ${esc(d.until||'')}</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Company','Obligations','Market cap','Recipients matched'],rows.map(r=>[`<b>${esc(r.ticker)}</b>`,frMoney(r.amount),frMoney(r.mcap),`<span class="muted">${esc((r.recipients||[]).slice(0,3).join('; '))}</span>`]))}
  else if(c==='awards'){const rows=frQ(d.awards||[],['ticker','recipient']);exported=rows;
   out+=`<div class="section-head"><h3>Largest contract awards, last 14 days</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Start','Recipient','Company','Amount','Agency','Description'],rows.map(r=>[esc(r.start||'—'),esc(r.recipient),r.ticker?`<b>${esc(r.ticker)}</b>`:'—',frMoney(r.amount),esc(r.agency||'—'),`<span class="muted" style="white-space:normal;display:block;max-width:380px">${esc(r.description||'')}</span>`]))}
  else{const rows=frQ(d.lobbying||[],['ticker','client']);exported=rows;
   out+=`<div class="section-head"><h3>Lobbying, last four quarters (Senate LDA)</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Company','Client name','Four quarters','Last quarter','Issues'],rows.map(r=>[`<b>${esc(r.ticker)}</b>`,esc(r.client),frMoney(r.trailing4),`${esc(r.last_quarter||'—')} ${frMoney(r.last_amount)}`,esc((r.issues||[]).join(', '))]))}
  return out;
 }
 return out;
}
function bindFilings(){
 if(state.tab!=='filings')return;
 for(const k of ['frv','frk','frs','frc','frd','frp','frg','frt'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 if($('frq')){$('frq').onchange=e=>{state.frq=e.target.value;state.page=0;render()};$('frq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 const box=$('fr-company');
 if(box&&window.FilingsRadarView)window.FilingsRadarView.render(box,{ticker:box.dataset.tk,hub:''});
}
