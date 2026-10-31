/* Move odds — the hub tab: how rare each asset's latest move is in its own history, and what followed moves like it.
   Views: the market and its sectors (a card each: the latest move and where it ranks; the one picked analysed below),
   industries (every SIC composite, the most extreme first), stocks today (the valued companies' most extreme moves either
   way, or the most unusual against their own volatility) and one ticker. The analysis is moves-view.js, shared with the
   company pages. Data: data/research/paths/moves/index.json and a/<KEY>.json (app/moves.py, branch research-paths).
   Deep links: #moves, #moves/industries, #moves/stocks, #moves/SPY, #moves/SIC-3674, #moves/NVDA. */
const mvStore={};
const MV_VIEWS=[['market','Market & sectors'],['industries','Industries'],['stocks','Stocks today'],['one','One ticker']];
const MV_SORTS=[['falls','Biggest falls for each stock'],['rises','Biggest rises for each stock'],['sigma','Most unusual against their own volatility']];
function mvData(){
 const m=mvStore.ix||(mvStore.ix={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='this browser cannot load data files';return m}
 m.loading=fetch('data/research/paths/moves/index.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
  .then(d=>{m.data=d;if(typeof render==='function')render()}).catch(e=>{m.err=e.message;if(typeof render==='function')render()});
 return m;
}
const mvRows=d=>(d.rows||[]).map(r=>Object.fromEntries(d.fields.map((f,i)=>[f,r[i]])));
const mvPct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(100*v).toFixed(d)+'%';
const mvRank=p=>p==null?'—':p>=50?`top ${(100-p)<1?(100-p).toFixed(2):(100-p).toFixed(1)}%`:`bottom ${p<1?p.toFixed(2):p.toFixed(1)}%`;
const mvTone=v=>v==null?'':v>0?'mv-up':v<0?'mv-down':'';
const mvEvery=v=>v==null?'—':'1 in '+(v<10?v.toFixed(1):Math.round(v).toLocaleString('en-US'));
const mvDay=e=>{const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(e||'');return m?`${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m[2]-1]} ${+m[3]}, ${m[1]}`:String(e||'')};
function mvCss(){
 if(typeof document==='undefined'||document.getElementById('mvh-css'))return;
 const s=document.createElement('style');s.id='mvh-css';
 s.textContent=`.mvh-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;margin:8px 0 14px}
.mvh-card{font:inherit;text-align:left;border:1px solid var(--line,#ddd);border-radius:12px;padding:9px 11px;background:var(--surface,#fff);color:var(--ink,#222);cursor:pointer;min-width:0}
.mvh-card.on{border-color:var(--ink,#222);box-shadow:inset 0 0 0 1px var(--ink,#222)}.mvh-card small{display:block;font-size:11.5px;color:var(--muted,#777);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mvh-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin:2px 0}.mvh-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.mvh-meter{height:6px;border-radius:3px;background:var(--line,#e5e5e5);position:relative;margin:6px 0 2px;overflow:hidden}.mvh-meter span{position:absolute;top:0;bottom:0;border-radius:3px}
.mvh-k{font:inherit;border:0;background:none;padding:0;color:var(--accent,#1f6f4a);cursor:pointer;text-decoration:underline;text-underline-offset:2px;text-align:left}
.mvh-note{font-size:12.5px;color:var(--muted,#777);max-width:900px;line-height:1.55}.mv-up{color:var(--mk-profit,#17734a)}.mv-down{color:var(--mk-cost,#c0392b)}
.mvh-h{margin:16px 0 4px;font-size:15px}`;
 document.head.appendChild(s);
}
function mvMeter(p){
 if(p==null)return '';
 const lo=Math.min(p,50),hi=Math.max(p,50),col=p>=50?'var(--mk-profit,#17734a)':'var(--mk-cost,#c0392b)';
 return `<div class="mvh-meter" title="percentile ${p.toFixed(1)}"><span style="left:${lo}%;width:${Math.max(hi-lo,1)}%;background:${col}"></span><span style="left:calc(50% - 1px);width:2px;background:var(--muted,#999)"></span></div>`;
}
function mvCard(r,on){
 return `<button type="button" class="mvh-card${on?' on':''}" data-mvk="${esc(r.key)}"><small>${esc(r.name)}</small><b class="${mvTone(r.move)}">${mvPct(r.move)}</b>${mvMeter(r.pct)}<i>${mvRank(r.pct)} day · ${esc(mvEvery(r.every))} days</i><i>after days like it, next month: <span class="${mvTone(r.sim21&&r.sim21[1])}">${r.sim21?mvPct(r.sim21[1]):'—'}</span>${r.sim21?` · ${Math.round(100*r.sim21[2])}% rose`:''}</i></button>`;
}
function mvAnalysis(key){return key?`<div id="mv-one" data-k="${esc(key)}" style="margin-top:10px"></div>`:''}
function mvMarket(rows,d){
 const pick=state.mvk&&rows.some(r=>r.key===state.mvk&&['market','index','sector','style'].includes(r.kind))?state.mvk:'SPY';
 const grp=(kind)=>rows.filter(r=>r.kind===kind);
 const order=['IDX-GSPC','SPY','QQQ','IDX-NDX','DIA','IDX-DJI','IWM','IDX-RUT','RSP','MDY','IDX-IXIC'];
 const mk=[...grp('market'),...grp('index')].sort((a,b)=>(order.indexOf(a.key)+1||99)-(order.indexOf(b.key)+1||99));
 const sec=grp('sector').sort((a,b)=>(a.pct??50)-(b.pct??50));
 const sty=grp('style');
 const b=d.breadth||{};
 let out=`<h3 class="mvh-h">The market</h3><div class="mvh-grid">${mk.map(r=>mvCard(r,r.key===pick)).join('')}</div>`;
 if(b.stocks)out+=`<p class="mvh-note">${esc(mvDay(d.as_of))}: of ${fmt(b.stocks)} valued companies with a close that day, <b class="mv-down">${(100*b.down5).toFixed(0)}%</b> had a bottom-5% day of their own history and <b class="mv-up">${(100*b.up5).toFixed(0)}%</b> a top-5% day (about 5% each on an ordinary day).</p>`;
 if(sec.length)out+=`<h3 class="mvh-h">Sectors — weakest to strongest</h3><div class="mvh-grid">${sec.map(r=>mvCard(r,r.key===pick)).join('')}</div>`;
 if(sty.length)out+=`<h3 class="mvh-h">Styles, rates, gold and oil</h3><div class="mvh-grid">${sty.map(r=>mvCard(r,r.key===pick)).join('')}</div>`;
 return out+mvAnalysis(pick);
}
function mvIndustries(rows,d){
 const ind=rows.filter(r=>r.kind==='industry').sort((a,b)=>Math.abs((b.pct??50)-50)-Math.abs((a.pct??50)-50));
 const pick=state.mvk&&ind.some(r=>r.key===state.mvk)?state.mvk:(ind[0]||{}).key;
 const t=table(['Industry','Companies','Last day','Move','Rank in its history','5-day move','After days like it: next month','Rose'],ind.map(r=>[
  `<button type="button" class="mvh-k" data-mvk="${esc(r.key)}">${esc(r.name)}</button>`,fmt(r.members),esc(mvDay(r.as_of)),`<span class="${mvTone(r.move)}">${mvPct(r.move)}</span>`,
  `${mvRank(r.pct)}`,`<span class="${mvTone(r.move5)}">${mvPct(r.move5)}</span>`,r.sim21?`<span class="${mvTone(r.sim21[1])}">${mvPct(r.sim21[1])}</span>`:'—',r.sim21?Math.round(100*r.sim21[2])+'%':'—']));
 return `<p class="mvh-note">Each SIC industry with five or more valued companies, equal-weighted (and each SIC major group, the first two digits), the most extreme move first. They hold today's companies only.</p>`+t+mvAnalysis(pick);
}
function mvStocks(rows,d){
 const st=rows.filter(r=>r.kind==='stock'&&r.as_of===d.as_of&&r.pct!=null);
 const sort=MV_SORTS.some(s=>s[0]===state.mvs)?state.mvs:'falls';
 const list=sort==='sigma'?st.filter(r=>r.z!=null).sort((a,b)=>Math.abs(b.z)-Math.abs(a.z)):sort==='rises'?st.sort((a,b)=>b.pct-a.pct):st.sort((a,b)=>a.pct-b.pct);
 const t=table(['Company','Sector','Move','Rank in its history','Against its volatility','How often','After days like it: next month','Rose','Days like it'],list.slice(0,200).map(r=>[
  `<button type="button" class="mvh-k" data-mvk="${esc(r.key)}" data-mvone="1">${esc(r.ticker)}</button> <span class="muted">${esc(r.name)}</span>`,esc(r.sector||''),
  `<span class="${mvTone(r.move)}">${mvPct(r.move)}</span>`,mvRank(r.pct),r.z==null?'—':(r.z>0?'+':'−')+Math.abs(r.z).toFixed(1)+'σ',esc(mvEvery(r.every)),
  r.sim21?`<span class="${mvTone(r.sim21[1])}">${mvPct(r.sim21[1])}</span>`:'—',r.sim21?Math.round(100*r.sim21[2])+'%':'—',r.sim21?fmt(r.sim21[0]):'—']));
 return `<p class="mvh-note">${esc(mvDay(d.as_of))}, the ${fmt(st.length)} valued companies with a close that day. "Rank in its history" compares each move with every day of the same stock since about ten years ago; "against its volatility" with the three months before the move. Pick a company to see the whole analysis.</p>`+t;
}
function movesView(){
 mvCss();
 state.mvv=MV_VIEWS.some(v=>v[0]===state.mvv)?state.mvv:'market';
 let out=head('Move odds','How rare the latest move is in each asset\'s own history — the market, its sectors and industries, every valued company — and what followed moves like it over the next day, week and month: the days that ranked about the same, the days at least as extreme, and every day.','PERCENTILES · WHAT CAME NEXT');
 out+=`<div class="toolbar">${field('mvv','View',MV_VIEWS,state.mvv)}`;
 if(state.mvv==='stocks')out+=field('mvs','Show',MV_SORTS,state.mvs||'falls',true);
 if(state.mvv==='one')out+=`<div class="field wide"><label for="mvt">Ticker</label><input id="mvt" value="${esc(state.mvt||'')}" placeholder="e.g. NVDA, SPY, XLK · Enter"></div>`;
 out+='</div>';
 if(state.mvv==='one'){const t=String(state.mvt||'').trim().toUpperCase().replace(/[./]/g,'-');return out+(t?mvAnalysis(t):empty('Type a ticker: a valued company, an ETF (SPY, QQQ, XLK …) or an index (IDX-GSPC).'))}
 const g=mvData();
 if(g.err)return out+empty(`The move odds could not load (${g.err}). They are rebuilt after every US close by .github/workflows/research-paths.yml (app/moves.py).`);
 if(!g.data)return out+empty('Loading the move odds…');
 const rows=mvRows(g.data);
 if(state.mvv==='industries')return out+mvIndustries(rows,g.data);
 if(state.mvv==='stocks')return out+mvStocks(rows,g.data);
 return out+mvMarket(rows,g.data);
}
function bindMoves(){
 if(state.tab!=='moves')return;
 if($('mvv'))$('mvv').onchange=e=>{state.mvv=e.target.value;state.page=0;render()};
 if($('mvs'))$('mvs').onchange=e=>{state.mvs=e.target.value;state.page=0;render()};
 if($('mvt')){$('mvt').onchange=e=>{state.mvt=e.target.value;render()};$('mvt').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-mvk]').forEach(b=>b.onclick=()=>{
  if(b.dataset.mvone){state.mvv='one';state.mvt=b.dataset.mvk}else state.mvk=b.dataset.mvk;
  render();const el=$('mv-one');if(el&&el.scrollIntoView)el.scrollIntoView({behavior:'smooth',block:'start'});
 });
 const one=$('mv-one');
 if(one&&window.MovesView&&one.dataset.drawn!==one.dataset.k){one.dataset.drawn=one.dataset.k;MovesView.render(one,{key:one.dataset.k,hub:''})}
}
function movesDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(MV_VIEWS.some(x=>x[0]===v)){state.mvv=v;return}
 const k=v.toUpperCase().replace(/[./]/g,'-');
 if(/^SIC-\d+$/.test(k)){state.mvv='industries';state.mvk=k;return}
 if(/^(SPY|QQQ|DIA|IWM|RSP|MDY|IDX-[A-Z]+|XL[A-Z]{1,2})$/.test(k)){state.mvv='market';state.mvk=k;return}
 state.mvv='one';state.mvt=k;
}
function movesNotice(){
 const s=mvData(),d=s.data;
 if(s.err)return {stale:true,text:'Official derived view · Move odds unavailable · '+s.err};
 if(!d)return {stale:false,text:'Official derived view · Move odds loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=50),text:`Official derived view · Move odds built ${d.generated_at} · closes to ${d.as_of} · ${fmt((d.rows||[]).length)} assets · rebuilt after every US close`+(age>50?' · stale':'')};
}
window.movesDeepLink=movesDeepLink;
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{moves:movesNotice});
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{moves:movesView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{moves:bindMoves});
if(typeof module!=='undefined')module.exports={mvMarket,mvIndustries,mvStocks,mvRows,mvRank,movesDeepLink};
