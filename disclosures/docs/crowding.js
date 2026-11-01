/* Holdings crowding from every 13F manager (app/crowding.py → data/market/crowding.json): which stocks — and, added up
   here by the site's sectors, which sectors — the most managers own and make one of their ten biggest stock bets, quarter
   by quarter. The Crowding view of the 13F holdings tab; the crowding of one ETF's holdings (ETF scanner) and of one
   manager's (13F holdings); videos of all of it through hub-video.js.
   Sectors: data/etf/sectors.json (app/etf.py: the consensus data's sector, else the issuer's other share class, else the
   sector ETFs that hold it), else the leaderboard's company list (data/market/history/rank/meta.json). The market's own
   sector weights, for the tilt: the quarter-end N-PORT report of Vanguard Total Stock Market (data/etf/weights/VTI.json). */
const CW_SECTORS={technology:'Technology',communication:'Communication','consumer-disc':'Consumer discretionary','consumer-staples':'Consumer staples',health:'Health care',financials:'Financials','real-estate':'Real estate',energy:'Energy',materials:'Materials',industrials:'Industrials',utilities:'Utilities',other:'Other / unclassified'};
const CW_SHORT={technology:'Technology',communication:'Comm. services','consumer-disc':'Discretionary','consumer-staples':'Staples',health:'Health care',financials:'Financials','real-estate':'Real estate',energy:'Energy',materials:'Materials',industrials:'Industrials',utilities:'Utilities',other:'Other'};
const cwFiles={};
function cwFile(path,quiet){
 const m=cwFiles[path]||(cwFiles[path]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/'+path).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;if(!quiet||m.wanted)render()}).catch(e=>{m.err=e.message;if(!quiet||m.wanted)render()});
 return m;
}
const cwQ=p=>{const m=/^(\d{4})-(\d{2})/.exec(p||'');return m?`Q${Math.floor((+m[2]-1)/3)+1} ${m[1]}`:String(p||'')};
const cwNum=v=>v!=null&&Number.isFinite(+v);
// percentile-free summaries of one quarter, from the published rows (crowding.py fields)
function cwModel(doc,secDoc,meta,vti){
 const P=doc.periods||[],K=P.length,F=doc.fields||[],ix=k=>F.indexOf(k);
 const iH=ix('holders'),iT=ix('top10'),iU=ix('usd_m'),iS=ix('score'),iC=ix('conviction');
 const secOf={};
 for(const r of (meta&&meta.cos)||[])if(r&&r[0]&&r[2])secOf[String(r[0]).toUpperCase().replace(/\./g,'-')]=r[2];
 Object.assign(secOf,(secDoc&&secDoc.sectors)||{});
 const names={};for(const r of (meta&&meta.cos)||[])if(r&&r[0])names[String(r[0]).toUpperCase().replace(/\./g,'-')]=r[1];
 Object.assign(names,Object.fromEntries(Object.entries(doc.names||{}).filter(([,n])=>n)));
 const rows=Object.entries(doc.rows||{}).map(([t,a])=>({t,name:names[t]||'',sec:CW_SECTORS[secOf[t]]?secOf[t]:'other',h:a[iH]||[],top:a[iT]||[],u:a[iU]||[],s:a[iS]||[],c:iC>=0?a[iC]||[]:[]}));
 const mgr=doc.managers||[],usd=doc.stock_usd||[];
 // the market's sector mix on the same quarter-ends (VTI's quarterly block), classified sectors only
 const mkt=P.map(()=>null);
 const q=vti&&vti.quarterly;
 if(q&&Array.isArray(q.dates)){const u=+q.unit||1e-5;P.forEach((p,k)=>{const i=q.dates.indexOf(p);if(i<0)return;const o={};let tot=0;(q.sectors||[]).forEach((s,j)=>{if(s==='other'||!CW_SECTORS[s])return;const v=((q.sw||[])[i]||[])[j]*u;if(v>0){o[s]=v;tot+=v}});if(tot>0){for(const s in o)o[s]/=tot;mkt[k]=o}})}
 const sectors={};
 for(const s of Object.keys(CW_SECTORS))sectors[s]={key:s,u:P.map(()=>0),su:P.map(()=>0),us:P.map(()=>0),n:P.map(()=>0)};
 for(const r of rows)for(let k=0;k<K;k++){const u=+r.u[k]||0;if(!(u>0))continue;const S=sectors[r.sec];S.u[k]+=u;S.n[k]++;if(cwNum(r.s[k])){S.su[k]+=u*r.s[k];S.us[k]+=u}}
 for(const S of Object.values(sectors)){
  S.share=P.map((p,k)=>usd[k]>0?S.u[k]/usd[k]:null);
  S.score=P.map((p,k)=>S.us[k]>0?S.su[k]/S.us[k]:null);
 }
 // each quarter's order by score (1 = the most crowded)
 for(let k=0;k<K;k++)rows.filter(r=>cwNum(r.s[k])).sort((a,b)=>b.s[k]-a.s[k]).forEach((r,i)=>{(r.rank=r.rank||P.map(()=>null))[k]=i+1});
 // the rest of the stock value filed (stocks too thinly held to publish, no ticker, no sector) stays Other
 const known=P.map((p,k)=>Object.values(sectors).reduce((a,S)=>a+(S.key==='other'?0:S.u[k]),0));
 sectors.other.share=P.map((p,k)=>usd[k]>0?Math.max(0,1-known[k]/usd[k]):null);
 for(const S of Object.values(sectors)){
  S.cshare=P.map((p,k)=>S.key==='other'||!(known[k]>0)?null:S.u[k]/known[k]);     // of the stock value with a sector
  S.tilt=P.map((p,k)=>S.cshare[k]==null||!mkt[k]||(!(S.u[k]>0)&&!(mkt[k][S.key]>0))?null:S.cshare[k]-(mkt[k][S.key]||0));
 }
 return {P,K,rows,by:new Map(rows.map(r=>[r.t,r])),sectors,mgr,usd,mkt,doc,secOf};
}
let cwCache=null;
function cwGate(){
 const c=cwFile('market/crowding.json');
 if(c.err)return {html:empty(`The crowding data could not load (${c.err}). It is built with the 13F market views every few hours (app/crowding.py).`)};
 const s=cwFile('etf/sectors.json',true),m=cwFile('market/history/rank/meta.json',true),v=cwFile('etf/weights/VTI.json',true);
 s.wanted=m.wanted=v.wanted=true;
 if(!c.data||(!s.data&&!s.err)||(!m.data&&!m.err)||(!v.data&&!v.err))return {html:empty('Loading the 13F crowding data…')};
 const key=[c.data.generated_at,!!s.data,!!m.data,!!v.data].join('|');
 if(!cwCache||cwCache.key!==key)cwCache={key,model:cwModel(c.data,s.data,m.data,v.data)};
 return {model:cwCache.model};
}
const cwScore=v=>cwNum(v)?fmt(v,1):'—';
const cwDelta=(a,b)=>cwNum(a)&&cwNum(b)?a-b:null;
const cwSigned=(v,d=0,u='')=>{if(v==null)return '—';const r=+(+v).toFixed(d);return r===0?'0'+u:`<span class="${r>0?'positive':'negative'}">${r>0?'+':'−'}${fmt(Math.abs(r),d)}${u}</span>`};
const cwPp=v=>v==null?'—':cwSigned(v*100,1,' pp');

/* ---------- videos (hub-video.js builds V for the Video Studio's renderers) ---------- */
const CW_STYLES=[['score','Most crowded stocks — score race'],['delta','Biggest crowding changes'],['holders','Most widely held — managers'],['sscore','Sector crowding score'],['sshare','Sector share of 13F stock holdings (areas)'],['tilt','Sector tilt against the market (pp)']];
const CW_HOLD_STYLES=[['hscore','Its holdings by crowding score'],['hdelta','Its holdings: crowding changes'],['hholders','Its holdings by managers holding']];
function cwGrid(P){return P.map(p=>Date.parse(p+'T00:00:00Z'))}
function cwRank(C,rows,val,{n,order,fmt:f,metric,title,sub,from}){
 const k0=from||0,P=C.P.slice(k0);
 const ser=rows.map(r=>({key:r.t||r.key,label:r.label||r.t,name:r.name||'',sec:r.sec,v:C.P.map((p,k)=>val(r,k)).slice(k0)}));
 // the names that make the top n in some quarter, so the race has everyone it needs and no one else
 const keep=new Set();
 P.forEach((p,k)=>{ser.filter(s=>cwNum(s.v[k])).sort((a,b)=>order==='abs'?Math.abs(b.v[k])-Math.abs(a.v[k]):b.v[k]-a.v[k]).slice(0,n).forEach(s=>keep.add(s.key))});
 const series=ser.filter(s=>keep.has(s.key));
 if(P.length<2)throw new Error('Crowding needs two or more quarters on file');
 if(!series.length)throw new Error('Nothing to rank in these quarters');
 return {kind:'rank',style:'bars',series,grid:cwGrid(P),rankN:n,order:order||'desc',fmt:f,metric,title,sub,unit:'',notes:new Set([C.doc.note||'']),quarterly:true,
  foot:'13F quarter-end holdings of every manager that filed · not trades · Filing Flows'};
}
function cwStack(C,title){
 const keys=Object.keys(CW_SECTORS).filter(s=>s!=='other'),P=C.P;
 const series=[...keys,'other'].map(s=>({key:s,label:CW_SECTORS[s],name:CW_SECTORS[s],sec:s,v:C.sectors[s].share.map(v=>cwNum(v)?v:0)}));
 series.sort((a,b)=>(a.key==='other')-(b.key==='other')||b.v[b.v.length-1]-a.v[a.v.length-1]);
 if(P.length<2)throw new Error('Crowding needs two or more quarters on file');
 return {kind:'sectors',style:'stack',series,grid:cwGrid(P),stack:{share:true,total:P.map(()=>1)},group:'sectors',fmt:v=>(100*v).toFixed(1)+'%',
  metric:'Share of the stock value 13F managers filed',title,sub:`${cwQ(P[0])} → ${cwQ(P[P.length-1])} · every 13F manager · common stock`,unit:'%',notes:new Set([C.doc.note||'','Other: stocks too thinly held to list, and holdings without a ticker or sector.']),quarterly:true,
  foot:'13F quarter-end holdings · sector of each stock: the site\'s sector map'};
}
function cwBuildAll(style,n){
 const g=cwGate();if(!g.model)throw new Error('The crowding data is still loading');
 const C=g.model,P=C.P,last=cwQ(P[P.length-1]),span=`${cwQ(P[0])} → ${last}`;
 const scored=C.rows.filter(r=>r.s.some(cwNum));
 if(style==='score')return cwRank(C,scored,(r,k)=>r.s[k],{n,fmt:v=>v.toFixed(1),metric:'Crowding score (0–100)',title:'The most crowded stocks among 13F managers',sub:span+' · score = √(share of managers holding × share with it in their top ten)'});
 if(style==='delta')return cwRank(C,scored,(r,k)=>k?cwDelta(r.s[k],r.s[k-1]):null,{n,order:'abs',from:1,fmt:v=>(v>=0?'+':'−')+Math.abs(v).toFixed(1),metric:'Change in crowding score vs the quarter before',title:'Where 13F crowding rose and fell',sub:span+' · score points, quarter on quarter'});
 if(style==='holders')return cwRank(C,C.rows,(r,k)=>r.h[k],{n,fmt:v=>Math.round(v).toLocaleString('en-US'),metric:'Managers holding',title:'The most widely held stocks in 13F',sub:span+' · managers that filed a position'});
 const secRows=Object.values(C.sectors).filter(S=>S.key!=='other').map(S=>({key:S.key,label:CW_SHORT[S.key],name:CW_SHORT[S.key]===CW_SECTORS[S.key]?'':CW_SECTORS[S.key],sec:S.key,S}));
 if(style==='sscore')return cwRank(C,secRows,(r,k)=>r.S.score[k],{n:Math.min(11,n),fmt:v=>v.toFixed(1),metric:'Sector crowding score (value-weighted)',title:'Which sectors 13F managers crowd into',sub:span+' · each stock\'s score weighted by the value held'});
 if(style==='sshare')return cwStack(C,'Where 13F managers\' stock money sits, by sector');
 if(style==='tilt'){
  const k0=C.mkt.findIndex(Boolean);
  if(k0<0||C.mkt.filter(Boolean).length<2)throw new Error('The market\'s quarter-end sector weights (Vanguard Total Stock Market, N-PORT) are not on file for two of these quarters yet');
  return cwRank(C,secRows,(r,k)=>r.S.tilt[k],{n:Math.min(11,n),from:k0,fmt:v=>(v>=0?'+':'−')+Math.abs(100*v).toFixed(1)+' pp',metric:'13F share minus the market\'s share',title:'Sectors 13F managers hold more (and less) of than the market',sub:`${cwQ(P[k0])} → ${last} · against Vanguard Total Stock Market's quarter-end N-PORT weights`});
 }
 throw new Error('Unknown view');
}
// one portfolio's holdings (ETF or manager): weights today, crowding through the quarters
function cwBuildHoldings(label,weights,style,n){
 const g=cwGate();if(!g.model)throw new Error('The crowding data is still loading');
 const C=g.model,P=C.P,span=`${cwQ(P[0])} → ${cwQ(P[P.length-1])}`;
 const held=weights.map(([t,w])=>{const r=C.by.get(t);return r?{...r,w}:null}).filter(Boolean);
 if(!held.length)throw new Error(label+': none of its holdings is in the 13F crowding data');
 if(style==='hscore')return cwRank(C,held.filter(r=>r.s.some(cwNum)),(r,k)=>r.s[k],{n,fmt:v=>v.toFixed(1),metric:'Crowding score (0–100)',title:`${label}: how crowded its holdings are`,sub:span+' · its current holdings · score = √(share of managers holding × share with it in their top ten)'});
 if(style==='hdelta')return cwRank(C,held.filter(r=>r.s.some(cwNum)),(r,k)=>k?cwDelta(r.s[k],r.s[k-1]):null,{n,order:'abs',from:1,fmt:v=>(v>=0?'+':'−')+Math.abs(v).toFixed(1),metric:'Change in crowding score vs the quarter before',title:`${label}: crowding changes in its holdings`,sub:span+' · score points, quarter on quarter'});
 return cwRank(C,held,(r,k)=>r.h[k],{n,fmt:v=>Math.round(v).toLocaleString('en-US'),metric:'Managers holding',title:`${label}: its holdings by 13F managers holding`,sub:span});
}

/* ---------- the Crowding view (13F holdings tab) ---------- */
const CW_SORT=[['score','Crowding score'],['delta','Change vs the quarter before'],['holders','Managers holding'],['conv','Top-ten share of holders'],['usd','Value held']];
function cwView(){
 const g=cwGate();if(g.html)return g.html;
 const C=g.model,P=C.P;
 if(!P.length)return empty('No quarter has enough 13F filings to score yet.');
 state.cwp=choose(state.cwp,P.slice().reverse());const k=P.indexOf(state.cwp);
 state.cws=CW_SORT.some(x=>x[0]===state.cws)?state.cws:'score';
 const secKeys=Object.keys(CW_SECTORS);state.cwsec=secKeys.includes(state.cwsec)?state.cwsec:'';
 let out=`<div class="toolbar">${field('cwp','Quarter',P.slice().reverse().map(p=>[p,`${cwQ(p)} · ${p}`]),state.cwp)}${field('cws','Sort stocks by',CW_SORT,state.cws)}${field('cwsec','Sector',[['','All sectors'],...secKeys.map(s=>[s,CW_SECTORS[s]])],state.cwsec)}</div>`;
 const scored=C.rows.filter(r=>cwNum(r.s[k]));
 const top=scored.slice().sort((a,b)=>b.s[k]-a.s[k])[0];
 const secs=Object.values(C.sectors).filter(S=>S.key!=='other'&&cwNum(S.score[k])).sort((a,b)=>b.score[k]-a.score[k]);
 out+=`<div class="metrics">${kpi('Managers that filed',fmt(C.mgr[k]),cwQ(P[k])+' 13F reports on file')}${kpi('Stocks scored',fmt(scored.length),`held by ${fmt((C.doc.params||{}).min_holders||20)}+ managers`)}${kpi('Most crowded stock',top?top.t:'—',top?`score ${cwScore(top.s[k])} · ${fmt(top.h[k])} managers`:'')}${kpi('Most crowded sector',secs[0]?CW_SECTORS[secs[0].key]:'—',secs[0]?`score ${fmt(secs[0].score[k],1)}`:'')}</div>`;
 out+=`<div class="explain"><b>How crowded is a stock?</b> Each quarter, among the stocks at least ${fmt((C.doc.params||{}).min_holders||20)} managers hold: <b>breadth</b> — the share of all 13F managers that hold it — and <b>top-ten share</b> — the share of the managers with ${fmt((C.doc.params||{}).min_book||20)}+ stock positions for whom it is one of their ten biggest (the table also shows that share among its own holders). The <b>score</b> = 100 × √(breadth × top-ten share of all those managers): 0–100, where 100 would mean every manager holds it as a top-ten position. It is an absolute level, so a rise means more managers piled in, not that other stocks fell back. <b>Sectors</b> weight each stock's score by the value held; <b>tilt</b> = the sector's share of the managers' stock value with a sector minus its share of the US market (Vanguard Total Stock Market's quarter-end N-PORT weights, the same quarter-end). Every manager that filed is counted (the Market maps' crowding index covers the watched managers only). Quarter-end positions as filed — not trades, and 13F leaves out shorts.</div>`;
 // sectors
 const srows=Object.values(C.sectors).filter(S=>S.key!=='other').sort((a,b)=>(b.score[k]??-1)-(a.score[k]??-1)).map(S=>[`<b>${esc(CW_SECTORS[S.key])}</b>`,pct(S.cshare[k],1),C.mkt[k]?pct(C.mkt[k][S.key]||0,1):'—',cwPp(S.tilt[k]),cwNum(S.score[k])?fmt(S.score[k],1):'—',k?cwSigned(cwDelta(S.score[k],S.score[k-1]),1):'—',fmt(S.n[k])]);
 out+=`<div class="panel"><h3>Sectors, ${esc(cwQ(P[k]))}</h3><p class="sub">13F share: of the stock value managers filed in stocks with a sector (${pct(C.sectors.other.share[k],1)} of it — thinly held stocks, no ticker or no sector — is left out). Market: Vanguard Total Stock Market's quarter-end N-PORT report, the same quarter-end${C.mkt[k]?'':' (not on file for this quarter yet)'}. Tilt = the two shares' difference.</p>${table(['Sector','13F share','Market share','Tilt','Crowding score','Change','Stocks'],srows)}</div>`;
 // stocks
 let rows=C.rows.filter(r=>cwNum(r.h[k])&&(!state.cwsec||r.sec===state.cwsec));
 const key={score:r=>r.s[k]??-1,delta:r=>Math.abs(cwDelta(r.s[k],k?r.s[k-1]:null)??-1),holders:r=>r.h[k]??-1,conv:r=>r.c[k]??-1,usd:r=>r.u[k]??-1}[state.cws];
 rows=rows.sort((a,b)=>key(b)-key(a));
 exported=rows.map(r=>({quarter:P[k],ticker:r.t,name:r.name,sector:CW_SECTORS[r.sec],rank:r.rank?r.rank[k]:null,score:r.s[k],score_change:k?cwDelta(r.s[k],r.s[k-1]):null,managers_holding:r.h[k],breadth:C.mgr[k]?r.h[k]/C.mgr[k]:null,top10_holders:r.top[k],top10_of_its_holders:r.c[k],value_held_usd_m:r.u[k]}));
 out+=`<div class="section-head"><h3>Stocks, ${esc(cwQ(P[k]))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`+table(['Stock','Sector','Rank','Score','Change','Managers holding','Breadth','Top-ten holders','Top ten of its holders','Value held'],rows.map(r=>[`<button class="text-button" data-cwt="${esc(r.t)}"><b>${esc(r.t)}</b></button> <span class="muted">${esc((r.name||'').slice(0,28))}</span>`,esc(CW_SECTORS[r.sec]),r.rank&&r.rank[k]?fmt(r.rank[k]):'—',cwScore(r.s[k]),k?cwSigned(cwDelta(r.s[k],r.s[k-1]),1):'—',fmt(r.h[k]),C.mgr[k]?pct(r.h[k]/C.mgr[k],1):'—',fmt(r.top[k]),cwNum(r.c[k])?pct(r.c[k],0):'—',cwNum(r.u[k])?'$'+compact(r.u[k]*1e6):'—']));
 out+=`<div class="panel"><h3>Crowding videos</h3><p class="sub">The most crowded stocks and sectors quarter by quarter, the biggest changes, and the sector tilt against the market — play here or export an MP4.</p>${HubVideo.slot('crowd:all',{title:'13F crowding',file:'13f-crowding',styles:CW_STYLES,unit:'quarters',version:C.doc.generated_at,build:({style,n})=>cwBuildAll(style,n)})}</div>`;
 return out;
}
// a 13F report as [[ticker, share of the reported value]]: common shares only; positions the report does not name by
// ticker through the Hub's CUSIP map (market/cusip-tickers.json); null while that map loads
function cwBook(snap){
 const need=(snap.positions||[]).some(r=>!r.ticker&&r.cusip);
 const m=need?cwFile('market/cusip-tickers.json',true):null;
 if(m){m.wanted=true;if(!m.data&&!m.err)return null}
 const map=(m&&m.data)||{},book=new Map();
 for(const r of snap.positions||[]){
  if(r.put_call!=='NONE'||r.share_type!=='SH'||!(r.value_usd>0))continue;
  const t=String(r.ticker||map[r.cusip]||'').toUpperCase().replace(/\./g,'-');
  if(t)book.set(t,(book.get(t)||0)+r.value_usd/snap.total_usd);
 }
 return [...book];
}
// one portfolio's crowding (an ETF's holdings, a manager's): today's weights through the quarters' scores
function cwPortfolio(key,label,weights,note){
 const g=cwGate();if(g.html)return `<div class="panel"><h3>How crowded are its holdings?</h3>${g.html}</div>`;
 const C=g.model,P=C.P,K=P.length,k=K-1;
 const w=weights.filter(([t,x])=>t&&x>0),tot=w.reduce((a,[,x])=>a+x,0)||1;
 const per=P.map((p,j)=>{let s=0,c=0;for(const [t,x] of w){const r=C.by.get(t);if(r&&cwNum(r.s[j])){s+=x*r.s[j];c+=x}}return c>0?{score:s/c,cov:c/tot}:null});
 const hot=w.reduce((a,[t,x])=>{const r=C.by.get(t);return a+(r&&r.rank&&r.rank[k]&&r.rank[k]<=50?x:0)},0);
 const cur=per[k];
 let out=`<div class="panel"><h3>How crowded are its holdings? <span class="muted">13F, ${esc(cwQ(P[k]))}</span></h3><p class="sub">${esc(note||'')} Each holding's crowding score (0–100 = 100 × √(share of all 13F managers holding it × share with it in their top ten); see 13F holdings → Crowding), weighted by its weight in the portfolio today.</p>`;
 out+=`<div class="metrics">${kpi('Weighted crowding score',cur?fmt(cur.score,1):'—',cur?`${pct(cur.cov,0)} of the portfolio scored`:'no holding scored')}${kpi('In the 50 most crowded stocks',pct(hot/tot,0),'of the portfolio, by weight')}${kpi('Change on the quarter',cur&&per[k-1]?(cur.score-per[k-1].score>=0?'+':'−')+fmt(Math.abs(cur.score-per[k-1].score),1):'—','weighted score, same holdings')}</div>`;
 out+=lineChart(P.map((p,j)=>({date:p,value:per[j]?Math.round(per[j].score*10)/10:null})),'value','score');
 const rows=w.slice().sort((a,b)=>b[1]-a[1]).slice(0,15).map(([t,x])=>{const r=C.by.get(t);return [`<b>${esc(t)}</b> <span class="muted">${esc(((r&&r.name)||'').slice(0,24))}</span>`,pct(x,2),r?cwScore(r.s[k]):'—',r&&r.rank&&r.rank[k]?fmt(r.rank[k]):'—',r&&k?cwSigned(cwDelta(r.s[k],r.s[k-1]),1):'—',r?fmt(r.h[k]):'—',r&&cwNum(r.c[k])?pct(r.c[k],0):'—']});
 out+=table(['Holding','Weight','Crowding score','Rank','Change','Managers holding','Top ten of its holders'],rows);
 out+=HubVideo.slot('crowd:'+key,{title:label+' crowding',file:key.replace(/[:/]/g,'-')+'-crowding',styles:CW_HOLD_STYLES,unit:'quarters',version:C.doc.generated_at+'|'+w.length,build:({style,n})=>cwBuildHoldings(label,w,style,n)});
 return out+'</div>';
}
window.HUB_BINDS=window.HUB_BINDS||{};
window.HUB_BINDS.crowding=()=>{
 for(const k of ['cwp','cws','cwsec','hview'])if($(k))$(k).onchange=e=>{state[k]=e.target.value;state.page=0;render()};
 document.querySelectorAll('#workspace [data-cwt]').forEach(b=>b.onclick=()=>{state.tab='consensus';state.cview='company';state.cq=b.dataset.cwt;if(typeof syncPills==='function')syncPills();try{history.replaceState(null,'','#consensus')}catch(e){}render();scrollTo({top:0,behavior:'smooth'})});
};
if(typeof module!=='undefined')module.exports={cwModel,cwGate,cwBuildAll,cwBuildHoldings,cwBook,cwView,cwPortfolio,cwFiles,CW_SECTORS};
