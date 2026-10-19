/* 4.16 All flows — one page for every disclosed decision maker: 13F managers, active ETFs, insiders (Form 4) and
   officials (House and Senate), side by side per stock, for the quarter whose 13F reports are arriving ("this quarter's
   filings"), the one before, both together, the calendar quarter to date and the last 90 days; where the groups agree
   and where they split; each group's most active names with their records; and Reddit's hottest stock right now, as a
   cashtag, against what those groups are doing in it.
   Data: data/smart/combined/{index,<period>}.json (app/smart.py, branch smart-history), data/market/reddit.json
   (app/reddit_hot.py, every half hour), data/smart/t/<TICKER>.json for the smart score. */
const afStore={};
function afData(path){
 const m=afStore[path]||(afStore[path]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/'+path+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const AF_VIEWS=[['stocks','Every stock, every group side by side'],['agree','Where the groups agree'],['split','Where they split'],['names','Most active names']];
const AF_SORT=[['net','Largest net dollars (the groups counted)'],['gbuy','Most groups net buying'],['gsell','Most groups net selling'],['actors','Most names trading'],['S','Skill-weighted score in the period'],['f13','13F managers: net dollars'],['ins','Insiders: net dollars'],['plan','Insider plan trades: net dollars'],['gov','Officials: net dollars'],['etf','Active ETFs: net dollars']];
// the groups, and which of them make up the total (state.afc: a comma list; insiders' 10b5-1 plan trades are their own group)
const AF_G=['f13','etf','ins','plan','gov'],AF_GN={f13:'13F managers',etf:'Active ETFs',ins:'Insiders',plan:'Insider plan trades (10b5-1)',gov:'Officials'};
function flowGroups(key,dflt){const v=state[key];const L=(v==null?dflt:String(v)).split(',').filter(g=>AF_G.includes(g));return L.length?L:['f13']}
function flowGroupBoxes(key,dflt,label){const on=new Set(flowGroups(key,dflt));
 return `<div class="field af-groups"><label>${esc(label||'Count in the total')}</label><span class="af-checks">${AF_G.map(g=>`<label><input type="checkbox" data-fg="${key}" value="${g}"${on.has(g)?' checked':''}> ${esc(AF_GN[g])}</label>`).join('')}</span></div>`}
function bindFlowGroups(){
 document.querySelectorAll('#workspace [data-fg]').forEach(b=>b.onchange=()=>{const key=b.dataset.fg;
  const on=[...document.querySelectorAll(`#workspace [data-fg="${key}"]`)].filter(x=>x.checked).map(x=>x.value);
  state[key]=(on.length?on:['f13']).join(',');state.page=0;render()});
}
const afMoney=v=>v==null||!Number.isFinite(+v)||Math.round(v)===0?'—':`<span class="${v>0?'positive':'negative'}">${v>0?'+':'−'}$${compact(Math.abs(v))}</span>`;
const afTk=t=>`<button class="text-button" data-aft="${esc(t)}"><b>${esc(t)}</b></button>`;
function afCell(r,g){const b=r[g+'_b'],s=r[g+'_s'];if(!b&&!s)return '<span class="muted">—</span>';return `<span class="positive">${fmt(b)}</span> · <span class="negative">${fmt(s)}</span><br>${afMoney(r[g+'_usd'])}`}
function afRows(d,groups){const F=d.fields,G=groups||AF_G;return (d.rows||[]).map(x=>{const o={};F.forEach((k,i)=>o[k]=x[i]);o.net=G.reduce((a,g)=>a+(o[g+'_usd']||0),0);return o})}
function afReddit(rows){
 const m=afData('market/reddit');
 if(m.err||!m.data||!m.data.hottest)return '';
 const d=m.data,h=d.hottest,t=h.ticker,row=(rows||[]).find(r=>r.ticker===t),sm=afData('smart/t/'+t.replace(/[^A-Za-z0-9-]/g,'_')),n=sm.data&&sm.data.now;
 const age=d.generated_at?Math.max(0,Math.round((Date.now()-Date.parse(d.generated_at))/60000)):null;
 const groups=row?AF_G.filter(g=>row[g+'_b']||row[g+'_s']).map(g=>`${AF_GN[g]} ${fmt(row[g+'_b'])} buying · ${fmt(row[g+'_s'])} selling (${afMoney(row[g+'_usd'])})`).join('; '):'';
 const th=(h.threads||[])[0];
 return `<div class="panel af-reddit"><div class="af-rh"><span class="af-tag">Reddit right now</span><b class="af-cash">${esc(h.cashtag||('$'+t))}</b><span>${esc(h.name||'')}</span></div>
  <p class="sub">${h.mentions!=null?`${fmt(h.mentions)} thread${h.mentions===1?'':'s'} naming it in the last 24 hours${h.mentions_prev!=null?` (${fmt(h.mentions_prev)} the day before)`:''} · `:''}heat ${fmt(h.heat,0)}${h.leading_since?` · on top since ${esc(new Date(h.leading_since).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}))}`:''} · ${d.source==='apewisdom'?'mention counts from ApeWisdom (Reddit refused the request)':`${fmt(d.threads_read)} threads read across r/${(d.subreddits||[]).join(', r/')}`}${age!=null?` · ${age<60?age+' min':Math.round(age/60)+' h'} ago`:''}</p>
  ${th?`<p class="af-thread">“${esc(th.title)}” <span class="muted">r/${esc(th.sub)} · ${fmt(th.score)} upvotes · ${fmt(th.comments)} comments</span> <a href="${esc(th.url)}" target="_blank" rel="noopener">thread ↗</a></p>`:''}
  <p><b>What the disclosed money did in ${esc(t)}:</b> ${groups||'no 13F manager, ETF, insider or official traded it in this period.'}${n&&n.S!=null?` · smart score now ${smScore(n.S)} from ${fmt(n.n)} votes`:''} · ${afTk(t)} <span class="muted">who is voting and their records</span></p>
  <div class="af-chips">${(d.rows||[]).slice(1,12).map(r=>`<button class="pill" data-aft="${esc(r.ticker)}" title="${esc((r.name||'')+' · heat '+fmt(r.heat,0)+(r.mentions!=null?' · '+r.mentions+' threads in 24 h':''))}">$${esc(r.ticker.replace(/-/g,'.'))}</button>`).join('')}</div>
  <p class="sub">${esc(d.note||'')}</p></div>`;
}
function allflowsView(){
 const ix=afData('smart/combined/index');
 let out='';
 if(ix.err)return afReddit([])+empty(`The combined flows could not load (${ix.err}). They are rebuilt with the smart-money scores every six hours.`);
 if(!ix.data)return empty('Loading all flows…');
 const P=ix.data.periods||[];
 state.afp=P.some(p=>p.key===state.afp)?state.afp:(P[0]||{}).key;
 state.afv=AF_VIEWS.some(v=>v[0]===state.afv)?state.afv:'stocks';
 const per=P.find(p=>p.key===state.afp)||{},pd=afData('smart/combined/'+state.afp);
 out+=`<div class="toolbar">${field('afp','Period',P.map(p=>[p.key,p.label]),state.afp,true)}${field('afv','View',AF_VIEWS,state.afv)}`;
 if(state.afv==='stocks')out+=field('afs','Sort',AF_SORT,state.afs||'net')+field('afg','Groups trading it',[['1','Any'],['2','2 or more'],['3','3 or more']],state.afg||'1')+`<div class="field"><label for="afq">Ticker or name</label><input id="afq" value="${esc(state.afq||'')}" placeholder="e.g. NVDA"></div>`;
 out+='</div>';
 if(state.afv!=='names')out+=`<div class="toolbar">${flowGroupBoxes('afc',AF_G.join(','))}</div>`;
 out+=`<div class="explain">Every disclosed decision maker on one page: <b>13F managers</b> (quarter-over-quarter position changes), <b>active ETFs</b> (N-PORT portfolios, net of their own creations and redemptions), <b>insiders</b> (Form 4 open-market purchases and sales, 10b5-1 plans left out) and <b>officials</b> (House and Senate reports). For each stock: how many of each group were net buyers · net sellers in the period, and their net dollars (13F: share change × the quarter-end close; officials: the middle of the disclosed ranges). Each name counts once per stock, all its trades in the period netted. Skill-weighted score: the same votes weighted by each name's record (Smart money tab). ${esc(per.note||'')} Not investment advice.</div>`;
 if(!pd.data)return out+afReddit([])+(pd.err?empty('Could not load this period ('+pd.err+').'):empty('Loading the period…'));
 const cnt=flowGroups('afc',AF_G.join(',')),rows=afRows(pd.data,cnt),G=per.groups||{};
 out=afReddit(rows)+out;
 out+=`<div class="metrics">${AF_G.filter(g=>g!=='plan'||G.plan).map(g=>{const x=G[g]||{};return kpi(AF_GN[g],x.actors?`${fmt(x.actors)} names`:'—',x.actors?`${fmt(x.trades)} trades in ${fmt(x.stocks)} stocks · bought $${compact(x.usd_buy||0)} · sold $${compact(x.usd_sell||0)}`:(g==='etf'?'active-ETF portfolios arrive with the next ETF run':state.afp==='qtd'&&(g==='f13'||g==='etf')?'reported after the quarter ends':'none in this period'))}).join('')}</div>`;
 if(state.afv==='names')return out+afNames(pd.data);
 let list=rows;
 if(state.afv==='agree')return out+afAgree(rows);
 if(state.afv==='split')return out+afSplit(rows);
 const q=String(state.afq||'').trim().toLowerCase();
 if(q)list=list.filter(r=>r.ticker.toLowerCase()===q||(r.name||'').toLowerCase().includes(q));
 const ming=+(state.afg||1);list=list.filter(r=>r.groups_buy+r.groups_sell>=ming);
 const s=state.afs||'net';
 const key={net:r=>Math.abs(r.net),gbuy:r=>r.groups_buy*1e15+r.net,gsell:r=>r.groups_sell*1e15-r.net,actors:r=>r.actors,S:r=>r.S==null?-1e9:r.S,f13:r=>r.f13_usd,ins:r=>r.ins_usd,plan:r=>-(r.plan_usd||0),gov:r=>r.gov_usd,etf:r=>r.etf_usd}[s]||(r=>Math.abs(r.net));
 list=list.slice().sort((a,b)=>key(b)-key(a));
 exported=list;
 out+=`<div class="section-head"><h3>${fmt(list.length)} stocks — ${esc(per.label||'')}</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Each group cell: net buyers · net sellers, then net dollars. Net = ${cnt.map(g=>AF_GN[g]).join(' + ')}. Insiders' 10b5-1 plan trades were set up months ahead: they move dollars but are not a decision taken that day, so they never count as a group buying or selling. Click a ticker for who traded it and how their past trades did.</p>`;
 return out+afTable(list.slice(0,600));
}
function afTable(list){
 const plan=list.some(r=>'plan_usd' in r);
 return table(['Stock','Net (counted)','13F managers','Active ETFs','Insiders',...(plan?['Insider plan trades']:[]),'Officials','Groups buying · selling','Skill-weighted (period)','Smart score now'],list.map(r=>[
  `${afTk(r.ticker)} <span class="muted">${esc((r.name||'').slice(0,34))}</span>`,afMoney(r.net),afCell(r,'f13'),afCell(r,'etf'),afCell(r,'ins'),...(plan?[afCell(r,'plan')]:[]),afCell(r,'gov'),
  `<span class="positive">${fmt(r.groups_buy)}</span> · <span class="negative">${fmt(r.groups_sell)}</span>`,smScore(r.S),smScore(r.S_now)]));
}
function afAgree(rows){
 const buy=rows.filter(r=>r.groups_buy>=2&&!r.groups_sell).sort((a,b)=>b.groups_buy-a.groups_buy||b.net-a.net);
 const sell=rows.filter(r=>r.groups_sell>=2&&!r.groups_buy).sort((a,b)=>b.groups_sell-a.groups_sell||a.net-b.net);
 exported=[...buy,...sell];
 return `<div class="section-head"><h3>Net bought by two groups or more, sold by none — ${fmt(buy.length)}</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">A group is a net buyer of a stock when more of its names bought than sold (ties: by net dollars). Three or four groups on the same side is rare.</p>`+afTable(buy.slice(0,150))+
  `<h3>Net sold by two groups or more, bought by none — ${fmt(sell.length)}</h3>`+afTable(sell.slice(0,150));
}
function afSplit(rows){
 const pick=(a,b)=>rows.filter(r=>(r[a+'_b']>r[a+'_s'])&&(r[b+'_s']>r[b+'_b'])).sort((x,y)=>(y[a+'_b']+y[b+'_s'])-(x[a+'_b']+x[b+'_s']));
 const sets=[['ins','f13','Insiders buying while 13F managers sell'],['f13','ins','13F managers buying while insiders sell'],['gov','f13','Officials buying while 13F managers sell'],['f13','gov','13F managers buying while officials sell'],['gov','ins','Officials buying while insiders sell']];
 exported=sets.flatMap(([a,b,l])=>pick(a,b).map(r=>({...r,split:l})));
 return `<div class="section-head"><h3>Where the groups take opposite sides</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">Insiders know the company, managers know the market, officials know Washington: when they disagree, the stock is worth a closer look. Each list: the first group's net buyers against the second's net sellers.</p>`+
  sets.map(([a,b,l])=>{const L=pick(a,b);return `<h3>${esc(l)} — ${fmt(L.length)}</h3>`+(L.length?afTable(L.slice(0,40)):empty('None in this period.'))}).join('');
}
function afNames(d){
 const A=d.actors||{},F=d.actor_fields||[];
 let out=`<div class="section-head"><h3>The most active names in the period</h3></div><p class="sub">By dollars traded (bought + sold). Record: how often their past trades were right (the stock's return against SPY over the next 63 trading days, shrunk toward their group's record) — click a name for every trade.</p>`;
 exported=[];
 for(const g of AF_G){
  const L=A[g]||[];if(!L.length)continue;
  const rows=L.map(x=>{const o={};F.forEach((k,i)=>o[k]=x[i]);return o});exported.push(...rows.map(r=>({group:g,...r,top:(r.top||[]).map(t=>t[0]+(t[1]>0?'+':'−')).join(' ')})));
  out+=`<h3>${esc(AF_GN[g])}</h3>`+table(['Name','Traded','Net','Trades · stocks','Record','Biggest moves'],rows.map(r=>[g==='plan'?`<b>${esc(r.name)}</b><br><span class="muted">${esc(r.sub||'')}</span>`:smWho(r.id,r.name,r.sub),'$'+compact(r.gross),afMoney(r.net),`${fmt(r.trades)} · ${fmt(r.stocks)}`,
   r.decisions?`<b>${pct(r.p,0)}</b> <span class="muted">(${fmt(r.decisions)} decisions)</span> ${smEdge(r.L)}`:`<span class="muted">${g==='plan'?'plan trades are not scored':'no record yet'}</span>`,
   (r.top||[]).map(t=>`<button class="text-button" data-aft="${esc(t[0])}">${esc(t[0])}</button> <span class="${t[1]>0?'positive':'negative'}">${t[1]>0?'bought':'sold'}</span> ${t[2]?'$'+compact(Math.abs(t[2])):''}`).join('<br>')]));
 }
 return out+'<div class="explain">Click a name for the record behind it: every scored trade, its accuracy on buys and on sales, and the running alpha.</div>';
}
function bindAllflows(){
 if(state.tab!=='allflows')return;
 for(const k of ['afp','afv','afs','afg'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 bindFlowGroups();
 if($('afq')){$('afq').onchange=e=>{state.afq=e.target.value;state.page=0;render()};$('afq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-aft]').forEach(b=>b.onclick=()=>{state.tab='smart';state.mview='stock';state.mst=b.dataset.aft;syncPills();try{history.replaceState(null,'','#smart/'+encodeURIComponent(b.dataset.aft))}catch(e){}render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-sma]').forEach(b=>b.onclick=()=>{state.tab='smart';state.mview='actor';state.maid=b.dataset.sma;state.maq=b.textContent.trim();syncPills();render();scrollTo({top:0,behavior:'smooth'})});
}
