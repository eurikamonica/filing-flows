/* 4.18 People & index — the people behind the disclosures, and the index and the analysts:
     managers     the largest 13F managers: latest portfolio, adds and cuts, and what copying each 13F the day after it was
                  filed would have returned against SPY (clone backtest)
     officials    members of Congress: disclosed trades scored against SPY, their committees, trades in sectors under those
                  committees ("potential overlap" — a fact pattern, not a finding)
     insiders     every new Form 4 trade beside the history of similar trades (event study: side, role, size, cluster)
     preview      the next 13F, estimated from what the manager already filed in the quarter; frozen and scored later
     sp500        S&P 500 rule screen: who meets the published criteria and is not a member yet; earlier calls scored
     targets      analysts' price targets: reached within 12 months or not (counting from the consensus snapshots on file)
   Data: data/research/people/*.json (app/people.py, branch research-people). Deep links: #people/m-<cik>, #people/o-<slug>. */
const peStore={};
function peData(path){
 const m=peStore[path]||(peStore[path]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/people/'+path+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const PE_VIEWS=[['managers','13F managers: copy-the-13F backtests'],['officials','Officials: trades, committees, overlaps'],['insiders','Insider trades in context'],['preview','Next 13F preview'],['sp500','S&P 500 candidates'],['targets','Analysts\' price targets: hit rate']];
const peRows=d=>(d.rows||[]).map(r=>{const o={};(d.fields||[]).forEach((k,i)=>o[k]=r[i]);return o});
const peSp=v=>v==null?'—':`<span class="${v>0?'positive':v<0?'negative':''}">${v>0?'+':v<0?'−':''}${fmt(Math.abs(v)*100,1)}%</span>`;
const peUsd=v=>v==null?'—':'$'+compact(v);
const peAmt=(lo,hi)=>lo==null?'—':hi?`$${fmt(lo)}–$${fmt(hi)}`:`over $${fmt(lo)}`;
function peLine(rows){
 const pts=(rows||[]).filter(r=>r[1]!=null&&r[2]!=null);if(pts.length<2)return '';
 const W=720,H=240,L=48,R=16,T=18,B=30;let lo=Math.min(1,...pts.map(r=>Math.min(r[1],r[2]))),hi=Math.max(1,...pts.map(r=>Math.max(r[1],r[2])));const pad=(hi-lo)*.08||.05;lo-=pad;hi+=pad;
 const x=i=>L+i*(W-L-R)/(pts.length-1),y=v=>T+(hi-v)*(H-T-B)/(hi-lo),path=k=>pts.map((r,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(r[k]).toFixed(1)).join(' ');
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Clone portfolio and SPY, both starting at 1">`;
 for(let i=0;i<=3;i++){const v=lo+(hi-lo)*i/3;s+=`<line class="gridline" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L-6}" y="${y(v)+4}" text-anchor="end">${fmt(v,2)}</text>`}
 s+=`<path d="${path(2)}" fill="none" stroke="var(--muted,#8a8f98)" stroke-width="2"/><path d="${path(1)}" fill="none" stroke="var(--mk-profit,#17734a)" stroke-width="2.5"/>`;
 pts.forEach((r,i)=>{if(i%Math.max(1,Math.floor(pts.length/6))===0||i===pts.length-1)s+=`<text class="axis" x="${x(i)}" y="${H-8}" text-anchor="middle">${esc(r[0])}</text>`});
 return s+`<text class="axis" x="${L+4}" y="12" fill="var(--mk-profit,#17734a)">clone</text><text class="axis" x="${L+52}" y="12">SPY</text></svg>`;
}
function peopleView(){
 state.pev=PE_VIEWS.some(v=>v[0]===state.pev)?state.pev:'managers';
 let out=`<div class="toolbar">${field('pev','View',PE_VIEWS,state.pev,true)}`;
 if(['managers','officials','sp500','targets'].includes(state.pev))out+=`<div class="field"><label for="peq">Name or ticker</label><input id="peq" value="${esc(state.peq||'')}" placeholder="filter"></div>`;
 out+='</div>';
 const fn={managers:peManagers,officials:peOfficials,insiders:peInsiders,preview:pePreview,sp500:peSp500,targets:peTargets}[state.pev];
 return out+fn();
}
function peFilter(rows,keys){const q=(state.peq||'').trim().toLowerCase();return q?rows.filter(r=>keys.some(k=>String(r[k]||'').toLowerCase().includes(q))):rows}
function peManagers(){
 if(state.pem)return peManager(state.pem);
 const d=peData('managers');if(d.err)return empty(`The managers could not load (${d.err}). They are rebuilt daily (research-people).`);if(!d.data)return empty('Loading the managers…');
 const rows=peFilter(peRows(d.data),['name','cik']);
 exported=rows;
 return `<div class="explain">${esc(d.data.note||'')}</div>`+table(['Manager','13F assets','Quarter','Positions','Clone since','Clone return','SPY, same days','Difference','Clone max drawdown','Priced share','Record (right side of SPY)'],
  rows.map(r=>[`<button class="text-button" data-pem="${esc(r.cik)}"><b>${esc(r.name)}</b></button>${r.corporate?' <span class="tag" title="A listed company filing a 13F for its own portfolio">company</span>':''}`,peUsd(r.aum),esc(r.period),fmt(r.positions),esc(r.clone_start||'—'),peSp(r.clone_total),peSp(r.spy_total),peSp(r.excess),peSp(r.max_dd),pct(r.coverage,0),r.hit==null?'—':`${pct(r.hit,0)} of ${fmt(r.decisions)}`]));
}
function peManager(cik){
 const d=peData('m/'+cik);if(d.err)return empty('This manager could not load ('+d.err+').');if(!d.data)return empty('Loading…');
 const m=d.data,c=m.clone||{};
 let out=`<p><button class="text-button" data-peback="1">← All managers</button> · <a href="../m/${esc(m.slug)}/">page for search engines ↗</a></p>`;
 out+=`<div class="section-head"><div><h2>${esc(m.name)}</h2><p class="sub">13F for the quarter ended ${esc(m.period)}, filed ${esc(m.filed)} · CIK ${esc(m.cik)}</p></div><span class="tag">13F</span></div>`;
 if(m.corporate)out+=`<div class="explain">${esc(m.name)} is a listed company investing its own capital. A 13F lists listed shares only; its stakes in private companies are in its 10-Q and 10-K: <a href="../#c-${esc(m.cik)}-invest">its investments, and the companies it names as investees →</a></div>`;
 out+=`<div class="metrics">${kpi('13F assets',peUsd(m.aum),'all reported positions')}${kpi('Positions',fmt(m.positions),'common shares')}${kpi('Clone return',c.total==null?'—':(c.total>0?'+':'')+fmt(c.total*100,1)+'%',c.start?`${c.start} → ${c.end}`:'')}${kpi('SPY, same days',c.spy_total==null?'—':(c.spy_total>0?'+':'')+fmt(c.spy_total*100,1)+'%',`max drawdown ${c.max_dd==null?'—':fmt(c.max_dd*100,1)+'%'} vs ${c.spy_max_dd==null?'—':fmt(c.spy_max_dd*100,1)+'%'}`)}</div>`;
 out+=`<div class="panel"><h3>Copying each 13F the day after it was filed</h3>${peLine(c.monthly)||empty('Not enough priced history yet.')}<p class="sub">Value-weighted over the common-share positions with a price (${pct(c.coverage,0)} of the portfolio on average), held until the next 13F; ${fmt(c.filings)} filings since ${esc(c.first_filing||'—')}. Price returns, no dividends or costs, for the clone and SPY alike.</p></div>`;
 out+=table(['Ticker','Company','Weight','Value','Change in the quarter'],(m.holdings||[]).filter(h=>h[0]).map(h=>[`<b>${esc(h[0])}</b>`,esc(h[1]),pct(h[2]),peUsd(h[3]),esc((h[4]||'unchanged').toLowerCase())+(h[5]!=null&&['INCREASE','DECREASE'].includes(h[4])?' '+peSp(h[5]/100):'')]));
 const li=xs=>(xs||[]).map(a=>`<li><b>${esc(a[0])}</b> <span class="muted">${esc((a[1]||'').toLowerCase())}${a[2]!=null&&!['NEW','EXIT'].includes(a[1])?' '+fmt(a[2],1)+'%':''}</span></li>`).join('')||'<li class="muted">none</li>';
 out+=`<div class="charts"><div class="panel"><h3>Biggest adds</h3><ul>${li(m.adds)}</ul></div><div class="panel"><h3>Biggest cuts</h3><ul>${li(m.cuts)}</ul></div></div>`;
 out+=`<div class="panel"><div data-pvport="m:${esc(m.cik)}"></div></div>`;
 if(m.record&&m.record.scored)out+=`<div class="explain">Record (Smart money): ${fmt(m.record.scored)} position changes scored in ${fmt(m.record.decisions)} decisions; ${pct(m.record.hit,0)} on the right side of SPY three months later.</div>`;
 return out;
}
function peOfficials(){
 if(state.peo)return peOfficial(state.peo);
 const d=peData('officials');if(d.err)return empty(`The officials could not load (${d.err}).`);if(!d.data)return empty('Loading the officials…');
 const rows=peFilter(peRows(d.data),['name','state','party']);exported=rows;
 return `<div class="explain">${esc(d.data.note||'')}</div>`+table(['Name','Chamber','Party · state','Committees','Trades','Scored','After disclosure vs SPY','From the trade date','Right side of SPY','Potential overlaps','Last trade'],
  rows.map(r=>[`<button class="text-button" data-peo="${esc(r.slug)}"><b>${esc(r.name)}</b></button>`,esc(r.chamber),esc([r.party,r.state].filter(Boolean).join(' · ')||'—'),fmt(r.committees),fmt(r.trades),fmt(r.scored),peSp(r.follow),peSp(r.trade),pct(r.hit,0),r.overlaps?`<b>${fmt(r.overlaps)}</b>`:'0',esc(r.last||'—')]));
}
function peOfficial(slug){
 const d=peData('o/'+slug);if(d.err)return empty('Could not load ('+d.err+').');if(!d.data)return empty('Loading…');
 const o=d.data,p=o.performance||{};
 let out=`<p><button class="text-button" data-peback="1">← All officials</button> · <a href="../o/${esc(o.slug)}/">page for search engines ↗</a> · <button class="text-button" data-pesm="${esc(o.id)}">record in Smart money</button></p>`;
 out+=`<div class="section-head"><div><h2>${esc(o.name)}</h2><p class="sub">${esc([o.chamber,o.party,o.state].filter(Boolean).join(' · '))}</p></div><span class="tag">OFFICIAL</span></div>`;
 out+=`<div class="metrics">${kpi('Trades on file',fmt(p.n),p.first?`${p.first} → ${p.last}`:'')}${kpi('Scored',fmt(p.scored),'63 trading days after')}${kpi('After disclosure vs SPY',p.follow==null?'—':(p.follow>0?'+':'')+fmt(p.follow*100,1)+'%','midpoint-weighted')}${kpi('Right side of SPY',pct(p.hit,0),'from the trade date')}</div>`;
 if((o.committees||[]).length)out+=`<div class="panel"><h3>Committees</h3><ul>${o.committees.map(c=>`<li>${esc(c[1])}${c[2]?' — '+esc(c[2]):''}</li>`).join('')}</ul></div>`;
 if((o.overlaps||[]).length)out+=`<div class="explain"><b>Potential overlap</b>: trades in a sector that one of the member's committees oversees (config/people.json lists the map). A fact pattern from public disclosures, not a finding of wrongdoing.</div>`+
  table(['Date','Ticker','Type','Amount','Committee','Area','Filed','Report'],o.overlaps.map(x=>[esc(x.date),`<b>${esc(x.ticker)}</b>`,esc(x.type),peAmt(x.amount_min,x.amount_max),esc(x.committee),esc(x.area),esc(x.filed||''),link(x.source_url,'PDF ↗')]));
 out+=`<div class="panel"><div data-pvport="o:${esc(o.slug)}"></div></div>`;
 if((o.recent||[]).length)out+=`<h3>Recent disclosed trades</h3>`+table(['Date','Ticker','Type','Amount','Owner','Filed','Report'],o.recent.map(t=>[esc(t[0]),`<b>${esc(t[1])}</b>`,esc(t[2]),peAmt(t[3],t[4]),esc(t[5]||''),esc(t[6]||''),link(t[7],'PDF ↗')]));
 return out;
}
function peCell(c){return c?esc(c.replace(/\|/g,' · ')):'—'}
function peInsiders(){
 const d=peData('insider_context');if(d.err)return empty(`Could not load (${d.err}).`);if(!d.data)return empty('Loading…');
 const D=d.data;exported=D.recent||[];
 let out=`<div class="explain">${esc(D.note||'')} ${fmt(D.trades)} scored trades, ${esc((D.window||[])[0]||'')} to ${esc((D.window||[])[1]||'')}; a row needs ${fmt(D.min_cell)} decisions, else the broader row is used.</div>`;
 out+=`<h3>The latest Form 4 trades and their history</h3>`+table(['Date','Ticker','Insider','Role','Side','Value','Others the same way','Similar trades: stock vs SPY, 3 months after','95% interval','n'],
  (D.recent||[]).map(t=>{const x=t.expected;return [esc(t.date),`<b>${esc(t.ticker)}</b>`,esc(t.insider),esc(t.role),esc(t.side),peUsd(t.value),t.cluster?'yes':'—',t.plan?'<span class="muted">10b5-1 plan: not scored</span>':x?`${peSp(x.mean)} <span class="muted">(${peCell(t.cell)})</span>`:'—',x?`${peSp(x.lo)} to ${peSp(x.hi)}`:'—',x?fmt(x.n):'—']}));
 const F=D.table_fields||[],rows=(D.table||[]).map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o});
 out+=`<h3>The event study</h3>`+table(['Side · role · size · others','Decisions','Mean','95% low','95% high','Median','Share beating SPY','Months'],rows.map(r=>[peCell(r.cell),fmt(r.n),peSp(r.mean),peSp(r.lo),peSp(r.hi),peSp(r.median),pct(r.hit,0),fmt(r.months)]));
 return out;
}
function pePreview(){
 const d=peData('preview13f');if(d.err)return empty(`Could not load (${d.err}).`);if(!d.data)return empty('Loading…');
 const D=d.data;let out=`<div class="explain">${esc(D.note||'')}${D.predictions_scored?` Scored so far: ${fmt(D.predictions_scored)} predictions, ${pct(D.hit_rate,0)} right.`:' Nothing scored yet: the first previews are scored when their 13Fs arrive.'}</div>`;
 if(!(D.previews||[]).length)out+=empty('No early filings by the tracked managers in the current quarter yet.');
 for(const p of D.previews||[])out+=`<div class="panel"><h3>${esc(p.name)} <span class="muted">— quarter ending ${esc(p.quarter)}, 13F due ${esc(p.due)}</span></h3><p class="sub">first estimated ${esc((p.first_made||'').slice(0,10))} · last 13F ${esc(p.base_period)}</p><ul>${(p.predictions||[]).map(x=>`<li><b>${esc(x.ticker)}</b> ${x.d>0?'<span class="positive">likely added</span>':x.d<0?'<span class="negative">likely cut</span>':'mixed'} <span class="muted">weight at the last 13F ${pct(x.weight_last)} · drifted ${pct(x.weight_drift)}</span><br><span class="muted">${(x.evidence||[]).map(e=>esc(`${e.source} ${e.date}: ${e.detail}`)).join(' · ')}</span></li>`).join('')}</ul></div>`;
 if((D.scored||[]).length)out+=`<h3>Scored previews</h3>`+table(['Manager','Quarter','Made','13F filed','Predictions','Right','Weight error (top 25)'],D.scored.map(s=>[esc(s[0]),esc(s[2]),esc((s[3]||'').slice(0,10)),esc(s[4]),fmt(s[5]),fmt(s[6]),s[7]==null?'—':pct(s[7],2)]));
 return out;
}
function peSp500(){
 const d=peData('sp500');if(d.err)return empty(`Could not load (${d.err}).`);if(!d.data)return empty('Loading…');
 const D=d.data,rows=peFilter(peRows(D),['ticker','name']);exported=rows;
 let out=`<div class="explain">${esc(D.note||'')} Threshold ${peUsd(D.threshold)}; ${fmt(D.members)} members on file (${esc(D.members_source||'—')}). Earlier calls: ${fmt(D.joined_within_year)} of ${fmt(D.resolved)} resolved ones joined within a year.</div>`;
 out+=table(['Ticker','Company','Market cap','Net income, 4 quarters','Latest quarter','Traded value / cap','Shares a month','Earnings rule','Liquidity rule','First flagged'],
  rows.map(r=>[`<b>${esc(r.ticker)}</b>`,esc(r.name),peUsd(r.mcap),peUsd(r.ni_4q),peUsd(r.ni_last),r.turnover==null?'—':fmt(r.turnover,2)+'×',compact(r.monthly_shares),r.eligible_earnings?'✓':'—',r.eligible_liquidity?'✓':'—',esc(r.first_flagged||'—')]));
 if((D.history||[]).length)out+=`<h3>Every call so far</h3>`+table(['Ticker','First flagged','Last flagged','Joined the index','Rank when first flagged'],D.history.map(h=>[`<b>${esc(h[0])}</b>`,esc(h[1]),esc(h[2]||'—'),h[3]?`<span class="positive">${esc(h[3])}</span>`:'—',fmt(h[4])]));
 return out;
}
function peTargets(){
 const d=peData('pt_hits');if(d.err)return empty(`Could not load (${d.err}).`);if(!d.data)return empty('Loading…');
 const D=d.data,rows=peFilter(peRows(D),['ticker','name','sector']);exported=rows;
 const S=(D.sectors||[]).map(r=>{const o={};(D.sector_fields||[]).forEach((k,i)=>o[k]=r[i]);return o});
 let out=`<div class="explain">${esc(D.note||'')} Tracking since ${esc(D.tracking_since||'—')}; the first full 12-month results arrive ${esc(D.first_full_results||'—')}.</div>`;
 out+=table(['Sector','Targets','Resolved','Reached','Hit rate','Still open','Touched so far','Price vs target 12 months on'],S.map(s=>[esc(s.sector),fmt(s.targets),fmt(s.resolved),fmt(s.hits),pct(s.hit_rate,0),fmt(s.pending),fmt(s.touched_so_far),peSp(s.median_error_12m)]));
 out+=table(['Ticker','Company','Sector','Targets','Resolved','Reached','Hit rate','Still open','Touched so far','Price vs target 12 months on'],rows.map(r=>[`<b>${esc(r.ticker)}</b>`,esc(r.name),esc(r.sector),fmt(r.targets),fmt(r.resolved),fmt(r.hits),pct(r.hit_rate,0),fmt(r.pending),fmt(r.touched_so_far),peSp(r.median_error_12m)]));
 return out;
}
function bindPeople(){
 if(state.tab!=='people')return;
 if($('pev'))$('pev').onchange=e=>{state.pev=e.target.value;state.pem='';state.peo='';state.page=0;render()};
 if($('peq')){$('peq').onchange=e=>{state.peq=e.target.value;state.page=0;render()};$('peq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-pem]').forEach(b=>b.onclick=()=>{state.pem=b.dataset.pem;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-peo]').forEach(b=>b.onclick=()=>{state.peo=b.dataset.peo;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-peback]').forEach(b=>b.onclick=()=>{state.pem='';state.peo='';render()});
 document.querySelectorAll('#workspace div[data-pvport]').forEach(el=>{if(window.PathsView&&PathsView.portfolio&&!el.dataset.drawn){el.dataset.drawn='1';const [k,id]=el.dataset.pvport.split(':');PathsView.portfolio(el,{kind:k,id,hub:'',compact:true})}});
 document.querySelectorAll('#workspace [data-pesm]').forEach(b=>b.onclick=()=>{state.tab='smart';if(typeof smartDeepLink==='function')smartDeepLink(b.dataset.pesm);if(typeof syncPills==='function')syncPills();render()});
}
/* deep links: disclosures/#people/m-1067983 (a manager), #people/o-nancy-pelosi (an official), #people/sp500 … */
function peopleDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(v.startsWith('m-')){state.pev='managers';state.pem=v.slice(2);state.peo=''}
 else if(v.startsWith('o-')){state.pev='officials';state.peo=v.slice(2);state.pem=''}
 else if(PE_VIEWS.some(x=>x[0]===v)){state.pev=v;state.pem='';state.peo=''}
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { people: peopleView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { people: bindPeople });
