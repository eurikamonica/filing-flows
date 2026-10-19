/* 4.14 Smart money — who has been right before, and what they are buying and selling now. Every disclosed trade by 13F
   managers, active ETFs, insiders (Form 4) and officials (House and Senate) is scored by the stock's return less SPY's over
   the next 63 trading days (a sale is right when the stock lagged); each actor gets a weighted accuracy on buys and on
   sales, shrunk toward their group's record until they have one; every stock gets a net buying / selling score in which
   each actor's vote counts by that skill — with a walk-forward backtest of the score.
   Data: data/smart/index.json, actors.json, t/<TICKER>.json, a/<group>/<bucket>.json (app/smart.py, branch smart-history). */
const smStore={};
function smData(name){
 const m=smStore[name]||(smStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/smart/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function smGate(name,title){
 const m=smData(name);
 if(m.err)return {html:empty(`${title} could not load (${m.err}). The smart-money job runs every six hours.`)};
 if(!m.data)return {html:empty(`Loading ${title.toLowerCase()}…`)};
 return {data:m.data};
}
const SM_VIEWS=[['stocks','Net buying now, weighted by skill'],['leaders','Who has been right'],['stock','One stock'],['actor','One manager, fund, insider or official'],['method','How it is scored, and how the score has done']];
const SM_G={f13:'13F managers',etf:'Active ETFs',ins:'Insiders',gov:'Officials'};
const SM_GO=[['','All four groups'],['f13','13F managers'],['etf','Active ETFs'],['ins','Insiders (Form 4)'],['gov','Officials (Congress)']];
const SM_SORT=[['buy','Strongest skilled buying'],['sell','Strongest skilled selling'],['votes','Most votes'],['split','Skilled vs everyone disagree']];
function smFnv(s){const u=unescape(encodeURIComponent(s));let h=0x811c9dc5;for(let i=0;i<u.length;i++)h=Math.imul(h^u.charCodeAt(i),0x01000193)>>>0;return h}   // FNV-1a of the UTF-8 bytes = smart.py fnv()
const smBucket=id=>(smFnv(id)%128).toString(16).padStart(2,'0');
const smGroupOf=id=>({f:'f13',e:'etf',i:'ins',g:'gov'})[String(id||'')[0]];
const smPct=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':fmt(v*100,d)+'%';
const smSp=(v,d=1)=>v==null||!Number.isFinite(+v)?'—':`<span class="${v>0?'positive':v<0?'negative':''}">${(v>0?'+':v<0?'−':'')+fmt(Math.abs(v*100),d)}%</span>`;
function smScore(S,big){
 if(S==null||!Number.isFinite(+S))return '<span class="muted">—</span>';
 const w=Math.min(50,Math.abs(S)/2);
 return `<span class="sm-score${big?' big':''}" title="${S>0?'Skilled net buying':S<0?'Skilled net selling':'Balanced'}: ${fmt(S,0)} of ±100"><i class="sm-bar"><b class="${S>=0?'up':'down'}" style="${S>=0?'left:50%':'right:50%'};width:${w.toFixed(1)}%"></b></i><em class="${S>0?'positive':S<0?'negative':''}">${S>0?'+':S<0?'−':''}${fmt(Math.abs(S),0)}</em></span>`;
}
const smSide=d=>d>0?'<span class="positive">buy</span>':'<span class="negative">sale</span>';
function smSize(g,v){if(v==null)return '—';return g==='f13'||g==='etf'?smPct(v,2)+' <span class="muted">of portfolio</span>':'$'+compact(v)}
const smTk=t=>`<button class="text-button" data-smt="${esc(t)}"><b>${esc(t)}</b></button>`;
const smWho=(id,name,sub)=>`<span class="sm-who">${typeof hubAvatar==='function'?hubAvatar(name,/^f:\d+$/.test(id)?id.slice(2):null):''}<span><button class="text-button" data-sma="${esc(id)}"><b>${esc(name)}</b></button>${sub?`<br><span class="muted">${esc(sub)}</span>`:''}</span></span>`;
function smP(p,n){return p==null?'—':`<b>${smPct(p,0)}</b>${n!=null?` <span class="muted">(${fmt(n)})</span>`:''}`}
function smEdge(L){if(L==null)return '—';return `<span class="${L>0.05?'positive':L<-0.05?'negative':'muted'}">${L>0?'+':L<0?'−':''}${fmt(Math.abs(L),2)}</span>`}

function smartView(){
 state.mview=SM_VIEWS.some(v=>v[0]===state.mview)?state.mview:'stocks';
 let out=`<div class="toolbar">${field('mview','View',SM_VIEWS,state.mview)}`;
 if(state.mview==='stocks')out+=smPeriodField()+field('mgrp','Whose trades',SM_GO,state.mgrp||'')+field('msort','Sort',SM_SORT,state.msort||'buy')+field('mmin','Votes',[['1','Any'],['3','3 or more'],['5','5 or more'],['10','10 or more']],state.mmin||'1')+
  `<div class="field"><label for="mq">Ticker or name</label><input id="mq" value="${esc(state.mq||'')}" placeholder="e.g. NVDA"></div>`;
 if(state.mview==='leaders')out+=field('mlg','Group',SM_GO.slice(1),state.mlg||'f13')+field('mlw','Show',[['best','Best record'],['worst','Worst record']],state.mlw||'best')+
  `<div class="field"><label for="mlq">Name</label><input id="mlq" value="${esc(state.mlq||'')}" placeholder="e.g. Pelosi, Berkshire"></div>`;
 if(state.mview==='stock')out+=`<div class="field wide"><label for="mst">Stock (ticker)</label><input id="mst" value="${esc(state.mst||'')}" placeholder="e.g. NVDA, KTOS · Enter"></div>`;
 if(state.mview==='actor')out+=`<div class="field wide"><label for="maq">Name (any group)</label><input id="maq" value="${esc(state.maq||'')}" placeholder="e.g. Nancy Pelosi, Berkshire Hathaway, Jensen Huang · Enter"></div>`;
 out+='</div>';
 out+=`<div class="explain">Every disclosed trade by <b>13F managers</b> (quarter-over-quarter position changes), <b>active ETFs</b> (their N-PORT portfolios, quarter over quarter, net of their own creations and redemptions), <b>insiders</b> (Form 4 open-market purchases and sales; pre-arranged 10b5-1 trades left out) and <b>officials</b> (House and Senate transaction reports) is scored by what the stock did next: its return less SPY's over the next 63 trading days (about three months). A buy is right when the stock beat SPY, a <b>sale is right when it lagged</b>. Each actor's <b>weighted accuracy</b> counts bigger bets and bigger moves more and is shrunk toward their group's record until they have one; the <b>smart score</b> of a stock adds up who is buying and selling it now, each vote weighted by that skill. Disclosures arrive late, past accuracy is no promise, and none of this is investment advice.</div>`;
 if(state.mview==='leaders')return out+smLeaders();
 if(state.mview==='stock')return out+smStock();
 if(state.mview==='actor')return out+smActor();
 if(state.mview==='method')return out+smMethod();
 return out+smStocks();
}
/* The period of the score: now (each actor's latest quarter / last 90 days), or one of the All flows windows — this quarter's
   filings (13F still arriving), the quarter before, both, the calendar quarter to date, the year so far … (smart/combined/) */
function smPeriodField(){
 const ix=typeof afData==='function'?afData('smart/combined/index'):null,P=(ix&&ix.data&&ix.data.periods)||[];
 return field('mper','Period',[['now','Now — the latest votes'],...P.map(p=>[p.key,p.label])],state.mper||'now',true);
}
function smPeriod(){
 const ix=afData('smart/combined/index'),per=((ix.data||{}).periods||[]).find(p=>p.key===state.mper);
 if(!per)return ix.err?empty('The windows could not load ('+ix.err+').'):empty('Loading the windows…');
 const pd=afData('smart/combined/'+per.key);
 if(pd.err)return empty('Could not load the window ('+pd.err+').');
 if(!pd.data)return empty('Loading the window…');
 const grp=state.mgrp||'',q=String(state.mq||'').trim().toLowerCase();
 let rows=afRows(pd.data,['f13','etf','ins','gov']).filter(r=>r.S!=null&&(!grp||r[grp+'_b']||r[grp+'_s'])&&(r.actors||0)>=+(state.mmin||1));
 if(q)rows=rows.filter(r=>r.ticker.toLowerCase()===q||(r.name||'').toLowerCase().includes(q));
 const s=state.msort||'buy';
 rows.sort((a,b)=>s==='sell'?a.S-b.S:s==='votes'?b.actors-a.actors:s==='split'?Math.abs(b.S-(b.raw||0))-Math.abs(a.S-(a.raw||0)):b.S-a.S);
 exported=rows;
 let out=`<div class="metrics">${['f13','etf','ins','gov'].map(g=>{const x=(per.groups||{})[g]||{};return kpi(SM_G[g],x.actors?fmt(x.actors)+' names':'—',x.actors?`${fmt(x.trades)} trades in ${fmt(x.stocks)} stocks`:'none in this window')}).join('')}</div>`;
 out+=`<div class="section-head"><h3>${s==='sell'?'Skilled net selling':s==='votes'?'Most traded':'Skilled net buying'} — ${esc(per.label)}</h3><button class="action" id="csv">Export CSV ↓</button></div><p class="sub">The same skill weights, counting only the trades inside the window (each name's trades in a stock netted). ${esc(per.note||'')}</p>`;
 out+=table(['Stock','Smart score (window)','Everyone alike','13F','ETFs','Insiders','Officials','Names trading','Smart score now'],rows.slice(0,800).map(r=>[
  `${smTk(r.ticker)} <span class="muted">${esc((r.name||'').slice(0,40))}</span>`,smScore(r.S),smScore(r.raw),
  ...['f13','etf','ins','gov'].map(g=>r[g+'_b']||r[g+'_s']?`<span class="positive">${fmt(r[g+'_b'])}</span> · <span class="negative">${fmt(r[g+'_s'])}</span>`:'<span class="muted">—</span>'),
  fmt(r.actors),smScore(r.S_now)]));
 return out;
}
function smStocks(){
 if(state.mper&&state.mper!=='now'&&typeof afData==='function')return smPeriod();
 const g=smGate('index','The smart-money scores');if(!g.data)return g.html;
 const d=g.data,F=d.stock_fields,grp=state.mgrp||'',sk=grp?'S_'+grp:'S';
 let rows=d.stocks.map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o}).filter(r=>r[sk]!=null&&(r.votes||0)>=+(state.mmin||1));
 const q=String(state.mq||'').trim().toLowerCase();
 if(q)rows=rows.filter(r=>r.ticker.toLowerCase()===q||(r.name||'').toLowerCase().includes(q));
 const s=state.msort||'buy';
 rows.sort((a,b)=>s==='sell'?a[sk]-b[sk]:s==='votes'?b.votes-a.votes:s==='split'?Math.abs(b[sk]-(b.raw||0))-Math.abs(a[sk]-(a.raw||0)):b[sk]-a[sk]);
 exported=rows;
 const bt=(d.backtest||{}).all||{},sm=bt.smart||{},rw=bt.raw||{};
 let out=`<div class="metrics">${kpi('Stocks with a vote now',fmt(rows.length),grp?SM_G[grp]+' only':'all four groups')}${kpi('Trades scored',fmt(Object.values(d.counts||{}).reduce((a,c)=>a+(c.scored||0),0)),'of '+fmt(Object.values(d.counts||{}).reduce((a,c)=>a+(c.trades||0),0))+' on file')}${kpi('Backtest: right side, weighted',sm.whit!=null?pct(sm.whit):'—',`everyone alike: ${rw.whit!=null?pct(rw.whit):'—'} · ${fmt(sm.n)} stock-months`)}${kpi('A random pick beats SPY',d.backtest&&d.backtest.reference!=null?pct(d.backtest.reference,0):'—','of the time, weighted — the bar each buy is measured against')}</div>`;
 out+=`<div class="section-head"><h3>${s==='sell'?'Skilled net selling':s==='votes'?'Most traded by the groups':s==='split'?'Where the skilled and everyone else disagree':'Skilled net buying'} — ${grp?SM_G[grp]:'all four groups'}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=`<p class="sub">Smart score: −100 (the actors with the best records are net sellers) to +100 (net buyers). Everyone alike: the same votes counted equally. Votes: 13F managers' and ETFs' latest quarter on file, insiders' and officials' last 90 days, each actor's net trade in the stock. Click a ticker for who is voting and how they have done; click a name for their record.</p>`;
 out+=table(['Stock','Smart score','Everyone alike','13F','ETFs','Insiders','Officials','Votes','Skilled buyers · sellers','Latest'],rows.slice(0,800).map(r=>[
  `${smTk(r.ticker)} <span class="muted">${esc((r.name||'').slice(0,40))}</span>`,smScore(r[sk]),smScore(grp?null:r.raw),smScore(r.S_f13),smScore(r.S_etf),smScore(r.S_ins),smScore(r.S_gov),
  fmt(r.votes),`<span class="positive">${fmt(r.skilled_buyers)}</span> · <span class="negative">${fmt(r.skilled_sellers)}</span>`,esc(r.last||'')]));
 return out;
}
function smLeaders(){
 const g=smGate('index','The records');if(!g.data)return g.html;
 const d=g.data,grp=state.mlg||'f13',F=d.leader_fields,c=(d.counts||{})[grp]||{};
 let rows=((state.mlw==='worst'?d.worst:d.leaders)||{})[grp]||[];
 rows=rows.map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o});
 const q=String(state.mlq||'').trim().toLowerCase();
 if(q)rows=rows.filter(r=>(r.name||'').toLowerCase().includes(q));
 exported=rows;
 let out=`<div class="metrics">${kpi(SM_G[grp]+' with a record',fmt(c.ranked),`5+ scored decisions · ${fmt(c.actors)} on file`)}${kpi('Trades scored',fmt(c.scored),`${fmt(c.trades)} on file · ${fmt(c.pending)} waiting for 63 days`)}${kpi('Group record: buys',c.base_buy!=null?pct(c.base_buy):'—',`right, weighted · a random buy: ${c.ref_buy!=null?pct(c.ref_buy):'—'}`)}${kpi('Group record: sales',c.base_sell!=null?pct(c.base_sell):'—',`right, weighted · a random sale: ${c.ref_sell!=null?pct(c.ref_sell):'—'}`)}</div>`;
 out+=`<div class="section-head"><h3>${state.mlw==='worst'?'The worst records':'The best records'} — ${esc(SM_G[grp])}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=`<p class="sub">A record needs five separate decisions (trades in the same stock on the same side within a month count as one). Ranked by skill weight (the edge): how far their weighted accuracy, shrunk toward the group's, sits above a random pick on the side they took, in log-odds — the weight their next vote gets. Hit rate: trades that were right, counted alike. Weighted accuracy: the share of the absolute excess return that was on the right side, bigger bets counting more. Alpha: the average excess return in the direction they traded; follow: the same from the day after the disclosure, what copying them would have given.</p>`;
 out+=table(['#','Name','Scored','Hit rate','Weighted accuracy','Skill (shrunk)','Edge','Buys','Sales','Alpha / trade','Follow','Latest'],rows.map((r,i)=>[
  fmt(i+1),smWho(r.id,r.name,r.sub),`${fmt(r.scored)} <span class="muted">of ${fmt(r.n)}</span>${r.decisions!=null&&r.decisions!==r.scored?`<br><span class="muted">${fmt(r.decisions)} decisions</span>`:''}`,smPct(r.hit,0),smPct(r.acc,0),`<b>${smPct(r.p,0)}</b>`,smEdge(r.L),smP(r.buy_p,r.buy_n),smP(r.sell_p,r.sell_n),smSp(r.alpha),smSp(r.follow),esc(r.last||'')]));
 return out;
}
function smLine(pts,{h=190,label='',fmtY=v=>fmt(v,0),lo=null,hi=null,zero=true}={}){   // [[date, value, note, good?]]
 if(!pts||pts.length<2)return '';
 const W=820,H=h,L=56,R=12,T=10,B=24,xs=pts.map(p=>Date.parse(p[0])),ys=pts.map(p=>p[1]);
 let y0=lo!=null?lo:Math.min(0,...ys),y1=hi!=null?hi:Math.max(0,...ys);if(y1===y0){y1+=1;y0-=1}
 const raw=(y1-y0)/4,mag=Math.pow(10,Math.floor(Math.log10(raw))),step=[1,2,2.5,5,10].map(m=>m*mag).find(x=>x>=raw)||raw;
 if(lo==null)y0=Math.floor(y0/step)*step;if(hi==null)y1=Math.ceil(y1/step)*step;
 const X=t=>L+(t-xs[0])/((xs[xs.length-1]-xs[0])||1)*(W-L-R),Y=v=>T+(y1-v)/(y1-y0)*(H-T-B);
 let s=`<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
 for(let v=y0;v<=y1+step/1e6;v+=step){s+=`<line class="mk-grid" x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${L-6}" y="${Y(v)+4}" text-anchor="end">${fmtY(Math.abs(v)<step/1e6?0:v)}</text>`}
 if(zero&&y0<0&&y1>0)s+=`<line x1="${L}" x2="${W-R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--muted)" stroke-width="1"/>`;
 const months=new Set();pts.forEach((p,i)=>{const m=p[0].slice(0,7);if(!months.has(m)&&(p[0].slice(5,7)==='01'||i===0)){months.add(m);s+=`<text class="axis" x="${X(xs[i])}" y="${H-6}" text-anchor="middle">${esc(p[0].slice(0,p[0].slice(5,7)==='01'?4:7))}</text>`}});
 s+=`<path d="${pts.map((p,i)=>(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="var(--ink)" stroke-width="2"/>`;
 pts.forEach((p,i)=>{s+=`<circle cx="${X(xs[i]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="${pts.length>60?1.5:3}" fill="${(p[3]!=null?p[3]:p[1]>=0)?'var(--mk-profit)':'var(--mk-cost)'}"><title>${esc(p[0])}: ${fmtY(p[1])}${p[2]!=null?' · '+esc(p[2]):''}</title></circle>`});
 return s+'</svg>';
}
function smStock(){
 const t=String(state.mst||'').trim().toUpperCase();
 if(!t)return empty('Type a ticker (or click one in the other views).');
 const m=smData('t/'+t.replace(/[^A-Za-z0-9-]/g,'_'));
 if(m.err)return empty(`No scored trade in ${t} is on file (${m.err}).`);
 if(!m.data)return empty('Loading '+t+'…');
 const d=m.data,n=d.now,bt=n&&n.history_bucket,hist=(d.history||[]).map(h=>[h[0],h[1],`everyone alike ${fmt(h[2],0)} · ${h[3]} votes`]);
 let out=`<div class="panel"><div class="section-head"><div><h3>${esc(d.name||t)} <span class="muted">${esc(t)}</span></h3><p class="sub">${typeof tkLink==='function'?tkLink(t)+' earnings and filings · ':''}scored ${esc((d.generated_at||'').slice(0,10))}</p></div></div>`;
 if(n){
  out+=`<div class="sm-now">${smScore(n.S,true)}<div><b>Smart score ${n.S>0?'+':''}${fmt(n.S,0)}</b> from ${fmt(n.n)} votes · everyone alike ${n.raw>0?'+':''}${fmt(n.raw,0)}<br>${Object.entries(n.groups||{}).map(([g,x])=>`${esc(SM_G[g])}: ${x.S>0?'+':''}${fmt(x.S,0)} <span class="muted">(${fmt(x.n)})</span>`).join(' · ')}</div></div>`;
  if(bt&&bt[1])out+=`<p class="sub">In the backtest, stocks scoring <b>${esc(bt[0])}</b> averaged ${smSp(bt[2])} against SPY over the next 63 trading days, beat SPY ${smPct(bt[3],0)} and the typical stock ${bt[4]!=null?smPct(bt[4],0):'—'} of the time (${fmt(bt[1])} stock-months).</p>`;
 }else out+=`<p class="sub">No vote in the current window: none of the groups traded ${esc(t)} in the last 90 days (insiders, officials) or in their latest quarter (13F, ETFs).</p>`;
 if(hist.length>1)out+=`<h3>Smart score at each month end</h3>${smLine(hist,{lo:-100,hi:100,label:'Smart score history of '+t,fmtY:v=>(v>0?'+':'')+fmt(v,0)})}`;
 out+='</div>';
 if(window.FFPosts)out+=`<div class="hub-post" data-post-t="${esc(t)}" data-post-k="flows"></div>`;
 const V=d.votes||[];
 if(V.length){
  out+=`<h3>Who is voting now — ${fmt(n&&n.buyers!=null?n.buyers:V.filter(v=>v[4]>0).length)} buyers, ${fmt(n&&n.sellers!=null?n.sellers:V.filter(v=>v[4]<0).length)} sellers${d.more_votes?` <span class="muted">(the ${fmt(V.length)} largest weights; ${fmt(d.more_votes)} smaller votes not listed)</span>`:''}</h3><p class="sub">Each actor's net trade in the window. Weight: conviction (their net size against their usual, up to 3) × skill weight on that side; a negative skill weight (worse than a random pick) counts against the side they took.</p>`;
  out+=table(['Name','Group','Side','Conviction','Skill on that side','Weight','Traded'],V.map(v=>[smWho(v[0],v[1],v[3]),esc(SM_G[v[2]]||v[2]),smSide(v[4]),fmt(v[5],2),smP(v[7],v[8]),smEdge(v[6]),esc(v[9]||'')]));
 }
 const TR=d.trades||[];
 if(TR.length){
  out+=`<h3>Trades in ${esc(t)}, newest first, and how each one did</h3><p class="sub">Excess: the stock's return less SPY's over 63 trading days from the trade (the quarter end for 13F and ETFs); signed in the direction of the trade, so + means the trade was right. Follow: from the day after it was disclosed.</p>`;
  exported=TR.map(r=>Object.fromEntries((d.trade_fields||[]).map((k,i)=>[k,r[i]])));
  out+=`<div class="section-head"><span></span><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Date','Name','Group','Side','Size','Score (63 days)','126 days','Follow','Disclosed'],TR.slice(0,200).map(r=>[esc(r[0]),smWho(r[1],r[2],''),esc(SM_G[r[3]]||r[3]),smSide(r[4]),smSize(r[3],r[5]),r[6]==null?'<span class="muted">waiting</span>':smSp(r[4]*r[6]),r[7]==null?'—':smSp(r[4]*r[7]),r[8]==null?'—':smSp(r[4]*r[8]),esc(r[9]||'')]));
 }
 return out;
}
function smActorFind(){
 if(state.maid)return state.maid;
 const q=String(state.maq||'').trim();
 if(!q)return null;
 if(/^[fegi]:/.test(q))return q;
 const g=smData('actors');
 if(!g.data)return g.err?'!':undefined;
 const F=g.data.fields,low=q.toLowerCase();
 const hits=g.data.rows.filter(r=>(r[1]||'').toLowerCase().includes(low));
 return hits.length?hits:[];
}
function smActor(){
 const f=smActorFind();
 if(f===null)return empty('Type a name, or click one in the records or on a stock.');
 if(f===undefined)return empty('Loading the directory of names…');
 if(f==='!')return empty('The directory of names could not load.');
 if(Array.isArray(f)){
  if(!f.length)return empty(`No one named “${state.maq}” has a trade on file.`);
  if(f.length>1)return `<h3>${fmt(f.length)} names match — pick one</h3>`+table(['Name','Group','Trades','Scored','Edge'],f.slice(0,60).map(r=>[smWho(r[0],r[1],r[2]),esc(SM_G[smGroupOf(r[0])]||''),fmt(r[3]),fmt(r[4]),smEdge(r[5])]));
  return smActorPage(f[0][0]);
 }
 return smActorPage(f);
}
function smActorPage(id){
 const g=smGroupOf(id),b=smData('a/'+g+'/'+smBucket(id));
 if(b.err)return empty('Could not load the record ('+b.err+').');
 if(!b.data)return empty('Loading the record…');
 const a=(b.data.actors||{})[id];
 if(!a)return empty('No record on file for '+id+'.');
 const s=a.stats||{},F=b.data.fields,T=a.trades||[],sc=T.filter(r=>r[5]!=null).slice().reverse();
 let cum=0;const pts=sc.map(r=>{cum+=r[2]*Math.max(-1,Math.min(1,r[5]));return [r[0],cum*100,`${r[1]} ${r[2]>0?'buy':'sale'}: ${(r[2]*r[5]*100).toFixed(1)}%`,r[2]*r[5]>0]});
 let out=`<div class="panel"><div class="section-head"><div><h3>${typeof hubAvatar==='function'?hubAvatar(a.name,/^f:\d+$/.test(id)?id.slice(2):null):''}${esc(a.name)} <span class="muted">${esc(SM_G[g]||g)}${a.sub?' · '+esc(a.sub):''}</span></h3>
  <p class="sub">${fmt(s.n)} trades on file, ${fmt(s.scored)} scored (63 trading days passed)${s.decisions!=null?` in ${fmt(s.decisions)} decisions (same stock, same side, same month = one)`:''} · latest ${esc(s.last||'—')}${/^f:\d+$/.test(id)?` · <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${esc(id.slice(2))}&type=13F" target="_blank" rel="noopener">13F filings ↗</a>`:''}</p></div></div>`;
 out+=`<div class="metrics">${kpi('Hit rate',s.hit!=null?pct(s.hit,0):'—',`${fmt(s.scored)} scored trades, counted alike`)}${kpi('Weighted accuracy',s.acc!=null?pct(s.acc,0):'—','bigger bets and bigger moves count more')}${kpi('Skill (shrunk)',s.p!=null?pct(s.p,0):'—',`evidence ≈ ${fmt(s.neff,1)} decisions · edge ${s.L!=null?(s.L>0?'+':'')+fmt(s.L,2):'—'}`)}${kpi('Alpha per trade',s.alpha!=null?(s.alpha>0?'+':'')+pct(s.alpha,1):'—',`follow (from disclosure): ${s.follow!=null?(s.follow>0?'+':'')+pct(s.follow,1):'—'}`)}</div>`;
 const side=(x,l)=>`<div><small>${l}</small><strong>${x&&x.p!=null?pct(x.p,0):'—'}</strong><span class="muted">${fmt(x&&x.n)} scored · hit ${x&&x.hit!=null?pct(x.hit,0):'—'} · weighted ${x&&x.acc!=null?pct(x.acc,0):'—'} · alpha ${x&&x.alpha!=null?(x.alpha>0?'+':'')+pct(x.alpha,1):'—'} · weight ${x&&x.L!=null?(x.L>0?'+':'')+fmt(x.L,2):'—'}</span></div>`;
 out+=`<div class="etf-cards sm-sides">${side(s.buy,'Buys: skill (shrunk)')}${side(s.sell,'Sales: skill (shrunk)')}</div>`;
 if(pts.length>1)out+=`<h3>Running alpha — each scored trade's excess return in the direction traded, added up</h3><p class="sub">A green dot is a trade that was right, a red one a trade that was wrong.</p>${smLine(pts,{label:'Running alpha of '+a.name,fmtY:v=>(v>0?'+':'')+fmt(v,0)+'%'})}`;
 out+='</div>';
 exported=T.map(r=>Object.fromEntries(F.map((k,i)=>[k,r[i]])));
 out+=`<div class="section-head"><h3>Every trade${a.more?` (the newest ${fmt(T.length)}; ${fmt(a.more)} older not shown)`:''}, and its score</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=`<p class="sub">Score: the stock's excess return over SPY in 63 trading days from the ${g==='f13'||g==='etf'?'quarter end':'trade'}, signed in the direction of the trade (+ right, − wrong). Conviction: the size against their usual (0.25–3).</p>`;
 out+=table(['Date','Stock','Side','Size','Conviction','Score (63 days)','126 days','Follow','Right?','Disclosed',g==='ins'?'Company':g==='gov'?'Owner':'Note'],T.map(r=>[esc(r[0]),smTk(r[1]),smSide(r[2]),smSize(g,r[3]),fmt(r[4],2),r[5]==null?'<span class="muted">waiting</span>':smSp(r[2]*r[5]),r[6]==null?'—':smSp(r[2]*r[6]),r[7]==null?'—':smSp(r[2]*r[7]),r[8]==null?'—':r[8]?'<span class="positive">✓</span>':'<span class="negative">✗</span>',esc(r[9]||''),esc(r[10]==='n'?'new position':r[10]==='x'?'exit':r[10]||'')]));
 return out;
}
function smMethod(){
 const g=smGate('index','The backtest');if(!g.data)return g.html;
 const d=g.data,bt=d.backtest||{},rows=[];
 for(const k of ['all',...(d.groups||[])]){const x=bt[k];if(!x)continue;for(const v of ['smart','raw']){const m=x[v]||{};rows.push([`${k==='all'?'All four groups':esc(SM_G[k])}${v==='raw'?' <span class="muted">— everyone alike</span>':' — <b>smart</b>'}`,fmt(m.n),m.hit!=null?pct(m.hit):'—',m.whit!=null?`<b>${pct(m.whit)}</b>`:'—',m.ic!=null?`${fmt(m.ic,3)}${m.ic_t!=null?` <span class="muted">(t ${fmt(m.ic_t,1)})</span>`:''}`:'—',m.spread!=null?smSp(m.spread,2):'—'])}}
 const bk=state.mbk||'all',B=((bt[bk]||{}).smart||{}).buckets||[];
 let out=`<div class="panel"><h3>How each trade, each actor and each stock is scored</h3><div class="explain">
  <b>A trade.</b> The stock's return less SPY's from the decision date — the trade date for insiders and officials, the quarter end for 13F managers and ETFs — over the next ${fmt(d.horizon_days)} trading days (126 days is shown too). A buy is right when the stock beat SPY, a sale when it lagged. <b>Follow</b> measures the same from the first close after the disclosure: what copying the trade could have earned.<br><br>
  <b>An actor.</b> Trades in the same stock on the same side within a month are one decision (an insider selling a little every day is one bet, not twenty). Each scored trade weighs its conviction (the size against the actor's usual: share of the portfolio for 13F and ETFs, dollars for insiders, the middle of the disclosed range for officials; 0.25–3) times the size of the move. Weighted accuracy = the weighted share that was on the right side, kept separately for buys and sales. It is shrunk toward the group's own record on that side (as if every actor started with ${fmt(d.k_prior)} trades at the group's rate), so one lucky trade does not make a genius. The <b>edge</b> is how far that shrunk accuracy sits above a random pick — most stocks lag the index, so a random buy beats SPY only ${d.backtest&&d.backtest.reference!=null?pct(d.backtest.reference,0):'about half'} of the time (weighted) and a random sale is right the rest — in log-odds: the weight of an independent voter.<br><br>
  <b>A stock.</b> Every actor with a net trade in it in the window (13F and ETFs: their latest quarter on file, counted for ${fmt(d.quarter_window_days)} days after its end; insiders and officials: ${fmt(d.window_days)} days) casts a vote: side × conviction × edge on that side. Smart score = 100 × the sum ÷ (the sum of the absolute weights + ${fmt(d.lambda,1)}), from −100 to +100; the constant keeps one voter from reaching the ends. Everyone alike counts the same votes with equal weight.<br><br>
  <b>Walk-forward.</b> The backtest recomputes everything at each month end from what was known then: skills only from trades whose 63 days had passed, votes only from trades already disclosed. Hit rates are against the typical stock (that month's median), because against SPY alone most stocks lose and a pile of sales would look clever.</div></div>`;
 out+=`<h3>How the score has done — ${fmt((bt.dates||[]).length)} month ends, ${esc((bt.dates||[])[0]||'')} to ${esc((bt.dates||[]).slice(-1)[0]||'')}</h3><p class="sub">Stock-months with a score of at least ±10. Right side: the score's sign against the stock's next 63 days relative to the typical stock; weighted: by the size of the score. IC: the rank correlation of score and next excess return, averaged over months (t: its mean over its standard error). Long-short: stocks at +20 or more minus those at −20 or less, per 63 days, averaged over months. Excess returns are capped at ±100% in the averages so that a handful of extreme moves do not decide them.</p>`;
 out+=table(['Score','Stock-months','Right side','Right side, weighted','IC','Long-short'],rows);
 out+=`<div class="toolbar">${field('mbk','Score buckets for',[['all','All four groups'],...(d.groups||[]).filter(k=>bt[k]).map(k=>[k,SM_G[k]])],bk)}</div>`;
 out+=table(['Smart score','Stock-months','Average excess over SPY','Beat SPY','Beat the typical stock'],B.map(b=>[esc(b[0]),fmt(b[1]),b[2]==null?'—':smSp(b[2],2),b[3]==null?'—':smPct(b[3],0),b[4]==null?'—':smPct(b[4],0)]));
 const C=d.counts||{};
 out+=`<h3>What is on file</h3>`+table(['Group','Actors','With a record','Trades','Scored','Waiting','Buys right (group)','Sales right (group)'],(d.groups||[]).map(k=>{const c=C[k]||{};return [esc(SM_G[k]),fmt(c.actors),fmt(c.ranked),fmt(c.trades),fmt(c.scored),fmt(c.pending),c.base_buy!=null?pct(c.base_buy):'—',c.base_sell!=null?pct(c.base_sell):'—']}));
 out+=`<p class="sub">${esc(d.note||'')}</p>`;
 return out;
}
function bindSmart(){
 if(state.tab!=='smart')return;
 for(const k of ['mview','mper','mgrp','msort','mmin','mlg','mlw','mbk'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 for(const k of ['mq','mlq','mst','maq'])if($(k)){$(k).onchange=e=>{state[k]=e.target.value;if(k==='maq')state.maid='';state.page=0;render()};$(k).onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-smt]').forEach(b=>b.onclick=()=>{state.mview='stock';state.mst=b.dataset.smt;render();scrollTo({top:0,behavior:'smooth'})});
 document.querySelectorAll('#workspace [data-sma]').forEach(b=>b.onclick=()=>{state.mview='actor';state.maid=b.dataset.sma;state.maq=b.textContent.trim();render();scrollTo({top:0,behavior:'smooth'})});
}
/* deep links: disclosures/#smart/NVDA (a stock) and disclosures/#smart/g:NANCY%20PELOSI (an actor's record) */
function smartDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(/^[fegi]:/.test(v)){state.mview='actor';state.maid=v;state.maq=''}else{state.mview='stock';state.mst=v.toUpperCase()}
}
