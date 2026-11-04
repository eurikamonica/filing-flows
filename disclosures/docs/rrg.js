/* 4.6 Relative Rotation Graph (RRG) on the long weekly history (branch rotation-history → data/market/history/).
   RS = 100 × close ÷ SPY, smoothed with a short EMA (4 weeks / 2 months). RS-Ratio: how far smoothed RS stands above or
   below its own n-period EMA trend (above 100: outperforming its trend). RS-Momentum: the change of that gap from one
   period to the next, smoothed the same way (above 100: the relative trend is gaining). Both are divided by their own
   typical size over the last year or more (in standard deviations around 100), so every line reads on one scale. An
   open approximation of the JdK RS-Ratio and RS-Momentum (the original formula is not published), computed here in the
   browser from weekly closes, so the window can change. Quadrants at 100 / 100 — Leading, Weakening, Lagging, Improving — and leadership
   rotates clockwise.
   Modes: 2-D (the standard chart); 3-D (time as depth: a rotation becomes a spiral, the slice at the front is the
   standard RRG of the date shown); 4-D (a third measure as depth and time played as the fourth dimension).
   Uses the helpers of market.js and rotation.js. */
const RRG={cache:new Map(),grid:null};
const RRG_COL=['#2a78d6','#eb6834','#1baf7a','#a24fd0','#c98a00','#d1397d','#3aa6b9','#7d8a1f','#b8522b','#5a6ad0','#8a8a84','#2f9e44'];
const RRG_MODES=[['2d','2-D — the standard RRG'],['3d','3-D — time as depth (spirals)'],['4d','4-D — a third measure as depth, time played']];
const RRG_Z=[['r52','12-month return vs SPY'],['hi52','Distance below the 52-week high'],['vrel','Volatility vs SPY (13 weeks)'],['volz','Volume vs its own year (13 weeks)']];
const RRG_ZINFO={r52:{label:'12-month return vs SPY',unit:'%'},hi52:{label:'Below the 52-week high',unit:'%'},vrel:{label:'Volatility vs SPY, 13 weeks',unit:'%'},volz:{label:'Volume, 13 weeks vs 52',unit:'%'},
 time:{label:'Time',unit:''}};
const RRG_Q=[['lead','Leading','RS-Ratio and RS-Momentum above 100: outperforming, and gaining'],['weak','Weakening','still above its trend, but losing speed'],
 ['lag','Lagging','under its trend and losing'],['imp','Improving','under its trend, but gaining speed']];
const RRG_FQ={w:{word:'weekly',wins:[['10','10 weeks (fast)'],['14','14 weeks'],['26','26 weeks'],['52','52 weeks (slow)']],n:'14',tails:[['4','4 weeks'],['8','8 weeks'],['13','13 weeks'],['26','26 weeks'],['52','52 weeks']],t:'8',span:260,ms:110},
 m:{word:'monthly',wins:[['6','6 months'],['10','10 months'],['12','12 months'],['24','24 months']],n:'10',tails:[['3','3 months'],['6','6 months'],['12','12 months'],['24','24 months']],t:'6',span:120,ms:300},
 d:{word:'daily',wins:[['10','10 days (fast)'],['14','14 days'],['21','21 days (a month)'],['42','42 days'],['63','63 days (a quarter, slow)']],n:'21',tails:[['5','5 days'],['10','10 days'],['21','21 days'],['42','42 days'],['63','63 days']],t:'10',span:252,ms:70}};
const rrgQuad=(x,y)=>x>=100?(y>=100?0:1):(y<100?2:3);
const rrgDay=s=>{const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s||''));return m?`${MONTH_NAMES[+m[2]-1]} ${+m[3]}, ${m[1]}`:qlabel(s)};

function rrgGrid(D){                                   // every Friday of the file, and the last Friday of each month
 if(RRG.grid&&RRG.grid.src===D)return RRG.grid;
 const t0=Date.parse(D.start+'T00:00:00Z'),n=Math.round((Date.parse(D.weeks+'T00:00:00Z')-t0)/6048e5)+1;
 const days=Array.from({length:n},(_,i)=>new Date(t0+i*6048e5).toISOString().slice(0,10));
 const mi=[];days.forEach((d,i)=>{if(i===n-1||days[i+1].slice(0,7)!==d.slice(0,7))mi.push(i)});
 return RRG.grid={src:D,t0,n,days,w:{idx:days.map((_,i)=>i),labels:days},m:{idx:mi,labels:mi.map(i=>days[i].slice(0,7))}};
}
function rrgFull(G,ent,key){                            // one series on the whole weekly grid
 const a=new Array(G.n).fill(null),src=ent[key]||[],o=Math.round((Date.parse(ent.start+'T00:00:00Z')-G.t0)/6048e5);
 for(let i=0;i<src.length;i++)if(o+i>=0&&o+i<G.n)a[o+i]=src[i];
 return a;
}
function rrgCalc(D,ent,freq,n){
 const key=`${ent.id}|${freq}|${n}`;if(RRG.cache.has(key))return RRG.cache.get(key);
 // weekly and monthly on the weekly grid; daily on SPY's trading days (rrg-lab.js: the move-odds files)
 const dly=freq==='d',GD=dly?RRGL.grid:null,G=dly?null:rrgGrid(D),S=dly?{idx:GD.idx,labels:GD.days}:G[freq];
 const C=dly?ent.dc:rrgFull(G,ent,'c'),B=dly?GD.spy:ent.benchC?rrgFull(G,{start:ent.start,c:ent.benchC},'c'):rrgFull(G,D.bench,'c'),V=!dly&&ent.v?rrgFull(G,ent,'v'):null;
 const rs=S.idx.map(i=>C[i]!=null&&B[i]!=null&&B[i]>0?100*C[i]/B[i]:null);
 // RS smoothed (a short EMA), against its own n-period EMA trend → the relative trend; its one-period change, smoothed
 // the same way → the momentum; both in standard deviations of their own last year or so, so lines are comparable
 const PR=RRGLab.PAR[freq],St=RRGLab.states(rs,PR.sh,n,PR.long(n),PR.minNorm),x=St.x,y=St.y;
 const lag=PR.lag,lr=(A,i)=>A[i]!=null&&A[i-1]!=null&&A[i]>0&&A[i-1]>0?Math.log(A[i]/A[i-1]):null;
 const sdN=(A,i)=>{const r=[];for(let j=i-PR.vN+1;j<=i;j++){if(j<1)continue;const v=lr(A,j);if(v!=null)r.push(v)}if(r.length<PR.vMin)return null;const mu=r.reduce((a,b)=>a+b,0)/r.length;return Math.sqrt(r.reduce((a,b)=>a+(b-mu)**2,0)/(r.length-1))};
 const z={r52:[],hi52:[],vrel:[],volz:[]};
 S.idx.forEach((gi,k)=>{
  z.r52.push(k>=lag&&rs[k]!=null&&rs[k-lag]!=null?100*(rs[k]/rs[k-lag]-1):null);
  let hi=null,cnt=0;for(let j=Math.max(0,gi-PR.hiN+1);j<=gi;j++)if(C[j]!=null){cnt++;hi=hi==null?C[j]:Math.max(hi,C[j])}
  z.hi52.push(cnt>=PR.hiMin&&C[gi]!=null?100*(C[gi]/hi-1):null);
  const a=sdN(C,gi),b=sdN(B,gi);z.vrel.push(a!=null&&b?100*(a/b-1):null);
  if(V){let s13=0,n13=0,s52=0,n52=0;for(let j=Math.max(0,gi-51);j<=gi;j++){if(V[j]==null)continue;s52+=V[j];n52++;if(j>gi-13){s13+=V[j];n13++}}
   z.volz.push(n13>=10&&n52>=40&&s52>0?100*((s13/n13)/(s52/n52)-1):null)}else z.volz.push(null);
 });
 const out={x,y,z,labels:S.labels,rs,c:S.idx.map(i=>C[i]),b:S.idx.map(i=>B[i]),s:St.s,t:St.t,dev:St.dev,roc:St.roc,sh:St.sh,n,long:St.long,minNorm:St.minNorm,freq};
 RRG.cache.set(key,out);return out;
}

/* ---------- which lines: the universe ---------- */
// the site's supply chains and themes (data/chains/index.json of the main site, pipeline/chains.py): each layer of a
// chain, or each whole chain, as an equal-weight basket of its stocks (weekly returns averaged, chained into an index)
const RRG_CH={m:null};
function rrgChains(){
 const m=RRG_CH.m||(RRG_CH.m={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='no fetch';return m}
 m.loading=fetch('../data/chains/index.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
function rrgBasket(D,id,name,tickers){
 const ents=tickers.map(t=>rrgTicker(String(t).replace('.','-')));
 if(ents.some(e=>e.loading))return {id,name,loading:true};
 const ok=ents.filter(e=>e.c);
 if(!ok.length)return {id,name,missing:true};
 const G=rrgGrid(D),S=ok.map(e=>rrgFull(G,e,'c')),idx=new Array(G.n).fill(null);
 for(let i=0;i<G.n;i++){
  let s=0,k=0;for(const a of S)if(i>0&&a[i]!=null&&a[i-1]!=null&&a[i-1]>0){s+=a[i]/a[i-1];k++}
  if(idx[i-1]!=null&&k)idx[i]=idx[i-1]*s/k;
  else if(idx[i-1]!=null)idx[i]=idx[i-1];
  else if(S.some(a=>a[i]!=null))idx[i]=100;
 }
 return {id,name,full:`equal-weight basket: ${ok.map(e=>e.id).join(', ')}${ok.length<tickers.length?` (not on file: ${tickers.filter(t=>!ok.some(e=>e.id===String(t).replace('.','-'))).join(', ')})`:''}`,start:G.days[0],c:idx};
}
function rrgUniverses(D){
 const ch=rrgChains(),cl=(ch.data&&ch.data.chains)||[];
 const extra=cl.length?[['themes','Hot themes (one basket per chain)'],...cl.map(c=>['chain:'+c.id,'Chain layers · '+c.name])]:[];
 return rrgUniverses0(D).concat(extra);
}
function rrgUniverses0(D){
 const secs={},tk=D.tickers||{};for(const [t,m] of Object.entries(tk))if(m&&m.s)(secs[m.s]=secs[m.s]||[]).push(t);
 const names=Object.fromEntries((D.series||[]).filter(s=>s.group==='site-sector').map(s=>[s.sector,s.name.replace(/ · site companies$/,'')]));
 const nice=s=>names[s]||String(s).replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
 return [['sectors','Sector ETFs (SPDR)'],['styles','Style, size and asset ETFs'],['indices','The four indices around their centre (QQQ · SPY · IWM · DIA)'],...Object.entries(typeof RRGL_UNI==='object'?RRGL_UNI:{}).map(([k,v])=>[k,v[0]]),['site','Site sectors (Sankey companies)'],
  ...Object.keys(secs).sort((a,b)=>nice(a).localeCompare(nice(b))).map(s=>['top:'+s,'Largest companies · '+nice(s)]),['tickers','Tickers you type']];
}
function rrgTicker(t){                                 // one company's weekly file, loaded when asked for
 const m=marketData('history/t/'+t);
 return m.data?{id:t,name:t,full:m.data.n||'',start:m.data.start,c:m.data.c,v:m.data.v,bx:m.data.bx,bi:m.data.bi,bl:m.data.bl,bn:m.data.bn,blevel:m.data.blevel,bcode:m.data.bcode}:m.err?{id:t,missing:true}:{id:t,loading:true};
}
function rrgIds(D,uni,typed){                        // the companies of a "largest" universe, or the tickers typed
 return uni.startsWith('top:')?Object.entries(D.tickers||{}).filter(([,m])=>m&&m.s===uni.slice(4)).sort((a,b)=>(b[1].rev||0)-(a[1].rev||0)).slice(0,10).map(([t])=>t)
  :String(typed||'').toUpperCase().split(/[\s,;]+/).filter(Boolean).map(t=>t.replace('.','-')).slice(0,12);
}
function rrgEntities(D,uni,typed){
 if(typeof rrglUniverse==='function'){const lab=rrglUniverse(D,uni,'w');if(lab)return lab}
 const S=D.series||[],grp=g=>S.filter(s=>s.group===g).map(s=>({...s,full:s.name,name:s.id.startsWith('s:')?s.name.replace(/ · site companies$/,''):s.id}));
 if(uni==='themes'||uni.startsWith('chain:')){
  const cl=((rrgChains().data||{}).chains)||[];
  if(uni==='themes')return cl.slice(0,12).map(c=>rrgBasket(D,'th:'+c.id,c.name.replace(/ \(.*\)$/,'').slice(0,28),[...new Set((c.layers||[]).flatMap(L=>L.tickers||[]))]));
  const c=cl.find(x=>'chain:'+x.id===uni);
  return c?(c.layers||[]).filter(L=>(L.tickers||[]).length).slice(0,12).map(L=>rrgBasket(D,'ch:'+c.id+':'+L.id,L.name.slice(0,28),L.tickers)):[];
 }
 if(uni==='indices')return typeof rrgIndexEntities==='function'?rrgIndexEntities(D):[];
 if(uni==='sectors')return grp('sector-etf');
 if(uni==='styles')return grp('style-etf');
 if(uni==='site')return grp('site-sector');
 // a ticker with no weekly file (an ETF, a country, a bond fund): its daily file, as weekly closes
 return rrgIds(D,uni,typed).map(t=>{const s=S.find(x=>x.id===t);if(s)return {...s,name:s.id,full:s.name};const e=rrgTicker(t);return e.missing&&typeof rrglEnt==='function'?rrglEnt(D,t,'w'):e});
}

function rrgDailyEntities(D,uni,typed){              // the daily chart: each line's daily file against SPY's
 const S=D.series||[];
 if(uni==='indices')uni='idxetf';
 const lab=rrglUniverse(D,uni,'d');if(lab)return lab;
 if(uni==='sectors'||uni==='styles')return S.filter(s=>s.group===(uni==='sectors'?'sector-etf':'style-etf')).map(s=>rrglEnt(D,s.id,'d',{name:s.id,full:s.name}));
 return rrgIds(D,uni,typed).map(t=>rrglEnt(D,t,'d'));
}

/* the dual RRG (research spec v5 §4, §15.4): each company against its industry without itself (SIC4, else SIC3 / SIC2 /
   the site sector, chosen and built by rotation_history.industry_benchmarks), and each of those industries against SPY */
function rrgDual(ents){
 const out=[],seen=new Set();
 for(const e of ents){
  if(!e.c||!e.bx){out.push(e);continue}
  const ik='ind:'+e.blevel+':'+e.bcode;
  if(!seen.has(ik)&&e.bi){seen.add(ik);out.push({id:ik,name:(e.blevel==='sector'?'':'SIC ')+e.bcode+' ▸ S&P',full:(e.bl||'')+' — all '+(e.bn||'')+' companies, against SPY',start:e.start,c:e.bi})}
  out.push({...e,id:e.id+'|ix',name:e.name+' ▸ ind.',full:(e.full||e.name)+' against '+(e.bl||'its industry')+' without itself (up to '+((e.bn||1)-1)+' companies, each counted while liquid)',benchC:e.bx});
 }
 return out;
}

/* ---------- the view ---------- */
function rrgView(){
 const g=marketGate('history/rrg','The long price history');
 if(!g.data)return `<div class="explain">The RRG uses the long weekly history (branch <span class="mono">rotation-history</span>, filled by the “Rotation history” workflow in batches). Until its first build is published there is nothing to draw.</div>`+g.html;
 const D=g.data;if(!D.bench)return empty('The benchmark (SPY) is not in the history yet; the next collection run fetches it first.');
 const unis=rrgUniverses(D);
 const chLoading=/^(themes|chain:)/.test(state.rrgu||'')&&!(RRG_CH.m&&(RRG_CH.m.data||RRG_CH.m.err));   // a deep link while the chains load
 state.rrgu=unis.some(u=>u[0]===state.rrgu)||chLoading?state.rrgu:'sectors';
 state.rrgf=['w','m','d'].includes(state.rrgf)?state.rrgf:'w';
 const W=state.rrgf==='w',Dy=state.rrgf==='d',FQ=RRG_FQ[state.rrgf],wins=FQ.wins,tails=FQ.tails,PR=RRGLab.PAR[state.rrgf];
 if(RRG.fq!==state.rrgf){if(RRG.fq)state.rrgn=state.rrgt=null;RRG.fq=state.rrgf}   // a new frequency: its own window and tail
 state.rrgn=wins.some(x=>x[0]===state.rrgn)?state.rrgn:FQ.n;
 state.rrgt=tails.some(x=>x[0]===state.rrgt)?state.rrgt:FQ.t;
 state.rrgm=RRG_MODES.some(m=>m[0]===state.rrgm)?state.rrgm:'2d';
 state.rrgz=RRG_Z.some(z=>z[0]===state.rrgz)?state.rrgz:'r52';
 const rrgCos=state.rrgu==='tickers'||String(state.rrgu).startsWith('top:');
 state.rrgb=state.rrgb==='industry'&&!Dy?'industry':'spy';
 let out=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${field('rrgu','Lines',unis,state.rrgu)}${field('rrgf','Frequency',[['w','Weekly (the standard)'],['d','Daily (every trading day)'],['m','Monthly (long cycles)']],state.rrgf)}${field('rrgm','Chart type',RRG_MODES,state.rrgm)}${state.rrgm==='4d'?field('rrgz','↗ Depth (third measure)',RRG_Z,state.rrgz):''}${state.rrgm==='2d'&&W?field('rfc','Next step',FC_MODES,(state.rfc=fcDefault())):''}</div>`;
 out+=`<div class="toolbar rot-display">${field('rrgn','RS window',wins,state.rrgn)}${field('rrgt','Tail',tails,state.rrgt)}${state.rrgu==='tickers'?`<div class="field wide"><label for="rrgtk">Tickers (up to 12, any company or ETF on file)</label><input id="rrgtk" value="${esc(state.rrgtk||'')}" placeholder="e.g. NVDA, AMD, SMH · Enter"></div>`:''}${rrgCos&&!Dy?field('rrgb','Companies against',[['spy','The S&P 500 (SPY)'],['industry','Their industry without themselves (dual RRG)']],state.rrgb):''}__FP__</div>`;
 if(Dy&&!RRGL_DAILY_OK(state.rrgu))return out.replace('__FP__','')+`<div class="explain">Daily lines come from the move-odds files (each asset's adjusted daily closes): the sector and style ETFs, the index ETFs, the countries, bonds, commodities and industry ETFs, the largest companies of a sector and tickers you type. Site sectors, themes and chain baskets are weekly only — pick other lines or the weekly chart.</div>`;
 const GD=Dy?rrglGrid():null;
 if(Dy&&!GD.grid)return out.replace('__FP__','')+(GD.err?empty('The daily history could not load ('+GD.err+'). It is published with the move odds every trading day; refresh to retry.'):empty('Loading the daily history…'));
 const ents0=Dy?rrgDailyEntities(D,state.rrgu,state.rrgtk):rrgEntities(D,state.rrgu,state.rrgtk),dual=rrgCos&&state.rrgb==='industry'&&!Dy;
 const ents=dual?rrgDual(ents0):ents0,ok=ents.filter(e=>e.c),waiting=ents.filter(e=>e.loading),missing=ents.filter(e=>e.missing);
 if(state.rrgu==='tickers'&&!ents.length)return out.replace('__FP__','')+empty('Type tickers to compare, e.g. NVDA, AMD, SMH.');
 if(!ok.length)return out.replace('__FP__','')+(waiting.length?empty(Dy?'Loading the daily history…':'Loading the weekly history…'):empty('Nothing on file for these yet. The collector takes the site’s companies largest first, a batch every few hours.'));
 const freq=state.rrgf,n=+state.rrgn,Q=Dy?GD.grid.days:rrgGrid(D)[freq].labels;
 const lines=ok.map((e,i)=>({e,col:RRG_COL[i%RRG_COL.length],calc:rrgCalc(D,e,freq,n)}));
 const firstK=Math.min(...lines.map(l=>l.calc.y.findIndex(v=>v!=null)).filter(k=>k>=0));
 // the last week any line has a close: the grid runs to this week's Friday, which has no close until it ends, and the
 // forecast arrows start from the last close — so the chart opens there and never past it
 const lastK=Math.max(...lines.map(l=>{for(let k=l.calc.y.length-1;k>=0;k--)if(l.calc.y[k]!=null)return k;return -1}));
 const key='rrg|'+freq+'|'+Q.length;
 if(state.rfk!==key||!(Number.isInteger(state.rf)&&state.rf>=0&&state.rf<Q.length)){state.rf=lastK>=0?lastK:Q.length-1;state.rfk=key}
 if(lastK>=0&&state.rf>lastK)state.rf=lastK;
 if(state.rf<firstK)state.rf=firstK;
 state.rfn=null;                                       // the other charts reset their frame when they come back
 const o={D,lines,Q,freq,n,dual,ix:state.rrgu==='indices'&&!Dy,tail:+state.rrgt,mode:state.rrgm,zk:state.rrgm==='3d'?'time':state.rrgm==='4d'?state.rrgz:null,firstK,lastK,
  P:{partial:new Set(),span:Math.min(Q.length-firstK,FQ.span),unit:PR.many,ms:FQ.ms,label:rrgDay}};
 o.dom=rrgDomain(o);
 // one line alone (a stock, a sector ETF): the others leave the chart; the forecast path then shows its dates and ranges
 state.rrgsolo=lines.some(l=>l.e.id===state.rrgsolo)?state.rrgsolo:'';
 o.solo=state.rrgsolo;
 out=out.replace('__FP__',(state.rrgm==='2d'?field('rrgfp','Forecast path (dates, prices)',RRGL_FP(o),rrglFpState(o)):'')+field('rrgsolo','Show',[['','All lines'],...lines.map(l=>[l.e.id,l.e.name+' only'])],state.rrgsolo));
 const head=state.rrgm==='2d'?'Relative Rotation Graph':state.rrgm==='3d'?'RRG in 3-D — time as depth':'RRG in 4-D — depth: '+RRG_ZINFO[o.zk].label+'; time played';
 out+=`<div class="panel"><h3>${esc(head)}</h3><p class="sub">→ JdK RS-Ratio (relative trend) · ↑ JdK RS-Momentum (its speed)${o.zk?' · ↗ '+esc(RRG_ZINFO[o.zk].label):''} · against ${o.ix?'the centre of the four (the centre against cash)':dual?'their industry without themselves (companies) · the industries against '+esc(D.benchmark||'SPY'):esc(D.benchmark||'SPY')} · ${esc(FQ.word)}, ${esc(n)}-${esc(PR.one)} window · tails ${esc(state.rrgt)} ${esc(PR.many)}. History since ${esc(rrgDay(Q[Math.max(0,firstK)]))}${Dy&&state.rrgu==='indices'?' · daily: the index ETFs against SPY (the centre model is weekly)':''}; drag the slider anywhere and press play.${state.rrgm==='2d'&&state.rrgfp?' Dashed: the forecast path — the median position each '+esc(PR.one)+' of every run of the line’s own and the benchmark’s moves in its last '+esc(fmt(PR.window))+' '+esc(PR.many)+', replayed through the formula, drawn smoothed over three '+esc(PR.many)+'; a small dot each '+esc(PR.one)+', larger ones at +'+PR.marks.join(' / +')+' '+esc(PR.many)+' with the date and the median replayed close (hover for the ranges and the quadrant shares). Play, the speed and “Export MP4” write the same play as a video.':''}</p>`;
 const Qp=lastK>=0?Q.slice(0,lastK+1):Q;               // slider and play stop at the last close
 out+=rotPlayer(Qp,o.P);
 const soloL=o.solo?lines.find(l=>l.e.id===o.solo):null,shown=soloL?[soloL]:lines;
 if(window.FFShare)out+=window.FFShare.bar({key:'hub-rrg-'+state.rrgm,title:head+(soloL?' · '+soloL.e.name+(rrgFull_(soloL.e)?' ('+rrgFull_(soloL.e)+')':''):'')+' — '+rrgDay(Qp[Math.min(state.rf,Qp.length-1)]),subtitle:`→ RS-Ratio · ↑ RS-Momentum · against ${dual?'their industry (companies) / '+(D.benchmark||'SPY'):(D.benchmark||'SPY')} · ${FQ.word}, ${n}-${PR.one} window · ${shown.map(l=>l.e.name).slice(0,10).join(', ')}${shown.length>10?' …':''}`,
  source:(Dy?'Daily':'Weekly')+' closes (Yahoo Finance / Stooq), adjusted; RRG computed in the browser (Filing Flows).',post:()=>rrgHubPost(o,Math.min(state.rf,Qp.length-1),head)});
 if(state.rrgm==='2d'){ROT.ctx={Q:Qp,P:o.P,draw:f=>rrgFrame(o,f),key:'hub-rrg-2d'};out+=`<div id="rot-plot" data-ffs-chart="hub-rrg-2d">${rrgFrame(o,state.rf)}</div>`}
 else{ROT.ctx={Q:Qp,P:o.P,paint:f=>rrgPaint3d(o,f),key:'hub-rrg-'+state.rrgm};
  out+=`<div class="rot-3d-wrap"><canvas id="rot-3d" data-ffs-chart="hub-rrg-${state.rrgm}" class="rot-3d" role="img" aria-label="${esc(head)}; the table below lists every value"></canvas><div class="rot-3d-tools"><button class="action" id="rspin" type="button">${ROT.spin?'Stop turning':'Turn slowly'}</button><button class="action" id="rreset" type="button">Front view</button></div></div>`}
 out+=`<div class="mk-legend rrg-legend">${lines.map(l=>{const k0=l.calc.y.findIndex(v=>v!=null),late=k0<0||k0>state.rf,off=o.solo&&l.e.id!==o.solo;
  return `<span${late||off?' class="muted"':''}><i class="mk-key" style="background:${l.col}${off?';opacity:.35':''}"></i>${esc(l.e.name)} <span class="muted">${esc(rrgFull_(l.e))}${late&&k0>=0?' · from '+esc(rrgDay(Q[k0])):''}${off?' · hidden':''}</span></span>`}).join('')}${RRG_Q.map(([k,name])=>`<span><i class="mk-key rrg-k-${k}"></i>${name}</span>`).join('')}</div>`;
 if(waiting.length||missing.length)out+=`<p class="sub">${waiting.length?'Loading '+esc(waiting.map(e=>e.id).join(', '))+'… ':''}${missing.length?'Not on file yet: '+esc(missing.map(e=>e.id).join(', '))+' (the collector fetches the site’s companies largest first; the workflow’s “tickers” input fetches any ticker now).':''}</p>`;
 const ix=o.ix;                                       // the indices around their centre: their own model, not the SPY one
 out+='</div>'+(ix?(typeof rrgIndexPanel==='function'?rrgIndexPanel(o):''):(state.rrgm==='2d'&&W?rrgFcNote(o):'')+(state.rrgm==='2d'&&W&&typeof rrgOdds==='function'?rrgOdds(o):''))+rrgTable(o)+(state.rrgm==='2d'&&typeof rrglPanel==='function'?rrglPanel(o):'')+(!ix&&state.rrgm==='2d'&&W&&typeof rrgTransitions==='function'?rrgTransitions(o):'');
 out+=`<details><summary>How the RRG is computed</summary><p>RS = 100 × ${Dy?'daily':'weekly'} close ÷ ${esc(D.benchmark||'SPY')} (both adjusted for splits and dividends), smoothed over ${W?'4 weeks':Dy?'5 trading days':'2 months'}. RS-Ratio: how far RS stands above or below its own ${esc(n)}-${esc(PR.one)} trend (an exponential average); above 100 the line is outperforming its trend. RS-Momentum: how much that gap changed since the ${esc(PR.one)} before, smoothed the same way; above 100 the relative trend is gaining speed. Both are expressed in standard deviations of their own last ${W?'year or more':Dy?'252 trading days (126 at least)':'two years or more'} around 100, so a quiet ETF and a volatile stock read on the same scale. This is an open approximation of the JdK RS-Ratio and RS-Momentum used by StockCharts (their formula is not published), so levels differ from theirs while the quadrants and the clockwise rotation read the same. Monthly lines sample the last weekly close of each month; daily lines are the move-odds files (each asset's adjusted daily closes) on SPY's trading days, and the ETF groups the weekly history does not carry (countries, regions, bonds, commodities, industry ETFs) take the last daily close of each week on the weekly chart. Prices are adjusted closes (dividends reinvested), so older ones sit below what was quoted then. 3-D puts time in depth, so each line becomes a spiral and the front slice is the standard chart for the date shown; 4-D puts a third measure in depth and plays time.</p><p class="sub">${esc(D.note||'')}</p></details>`;
 if(window.FFPosts&&ok.length){const tk=ok.filter(e=>/^[A-Z][A-Z0-9-]{0,6}$/.test(String(e.id))&&!(D.series||[]).some(x=>x.id===e.id&&x.group!=='ticker')).slice(0,3);
  if(tk.length)out+=`<h3>Posts for X</h3>`+tk.map(e=>`<div class="hub-post" data-post-t="${esc(e.id)}" data-post-k="rotation"></div>`).join('');}
 return out;
}
function rrgHubPost(o,f,head){                        // every line's quadrant at the frame shown, as an analysis and a post
 const at=o.lines.map(l=>{const x=l.calc.x[f],y=l.calc.y[f],x0=f>0?l.calc.x[f-1]:null,y0=f>0?l.calc.y[f-1]:null;
  return x==null||y==null?null:{n:l.e.name,x,y,q:rrgQuad(x,y),dx:x0==null?null:x-x0,dy:y0==null?null:y-y0}}).filter(Boolean);
 const by=[0,1,2,3].map(q=>at.filter(a=>a.q===q).sort((a,b)=>Math.hypot(b.x-100,b.y-100)-Math.hypot(a.x-100,a.y-100)));
 const moved=at.filter(a=>a.dx!=null).map(a=>{const q0=rrgQuad(a.x-a.dx,a.y-a.dy);return q0!==a.q?`${a.n} ${RRG_Q[q0][1]} → ${RRG_Q[a.q][1]}`:null}).filter(Boolean);
 const day=rrgDay(o.Q[f]),bench=o.D.benchmark||'SPY';
 const one=o.freq==='w'?'week':o.freq==='d'?'trading day':'month';
 const paras=[`Relative Rotation Graph for the ${one} of ${day}, against ${bench}: ${at.length} lines.`,
  ...by.map((L,q)=>L.length?`${RRG_Q[q][1]} (${RRG_Q[q][2]}): ${L.map(a=>`${a.n} (${rrgF(a.x,1)} / ${rrgF(a.y,1)})`).join(', ')}.`:''),
  moved.length?`Changed quadrant since the ${one} before: ${moved.join('; ')}.`:''];
 const lines=[`RRG vs ${bench}, ${day}:`,...by.map((L,q)=>L.length?`${RRG_Q[q][1]}: ${L.slice(0,6).map(a=>a.n).join(', ')}${L.length>6?' +'+(L.length-6):''}.`:''),moved.length?`Rotated: ${moved.slice(0,3).join('; ')}.`:''];
 return {title:head+' — '+day,paras,lines}}
function rrgDomain(o){                                 // symmetric around 100, fixed for the whole history so play does not rescale
 const xs=[],ys=[],zs=[];
 for(const l of o.lines)for(let k=o.firstK;k<o.Q.length;k++){const x=l.calc.x[k],y=l.calc.y[k];if(x==null||y==null)continue;xs.push(Math.abs(x-100));ys.push(Math.abs(y-100));
  if(o.zk&&o.zk!=='time'){const z=l.calc.z[o.zk][k];if(z!=null)zs.push(z)}}
 const q=(a,p)=>{if(!a.length)return 1;const s=a.slice().sort((u,v)=>u-v);return s[Math.min(s.length-1,Math.floor(p*(s.length-1)))]};
 const mx=Math.max(1.2,q(xs,.985)*1.08),my=Math.max(1.2,q(ys,.985)*1.08);
 const zd=zs.length?[q(zs,.03),q(zs,.97)]:[0,1];if(zd[1]-zd[0]<1e-9)zd[1]=zd[0]+1;
 return {x:[100-mx,100+mx],y:[100-my,100+my],z:zd};
}
const rrgF=(v,d=2)=>v==null?'—':fmt(v,d);
const rrgFull_=e=>{const f=String(e.full||'').replace(/\s*\([A-Z.\-]+\)$/,'');return f===e.name?'':f};
function rrgTipRows(o,l,k){
 const c=l.calc,x=c.x[k],y=c.y[k],qd=RRG_Q[rrgQuad(x,y)];
 const px=c.c&&c.c[k]!=null?[[rrglMoney(l.e,c.c[k]),rrglIsPrice(l.e)?'close (adjusted)':'index level']]:[];
 return [[l.e.name+' · '+rrgDay(o.Q[k]),rrgFull_(l.e)],[qd[1],qd[2]],...px,[rrgF(x),'RS-Ratio'],[rrgF(y),'RS-Momentum'],
  ...Object.keys(RRG_ZINFO).filter(z=>z!=='time'&&c.z[z][k]!=null).map(z=>[vfmt({unit:'%',centred:true},c.z[z][k]),RRG_ZINFO[z].label])];
}
function rrgFrame(o,f){
 const [W,H]=rotSize(.62,420,700),Lm=58,R=18,T=16,B=44,{x:xd,y:yd}=o.dom;
 const cx=v=>Math.max(xd[0],Math.min(xd[1],v)),cy=v=>Math.max(yd[0],Math.min(yd[1],v));
 const sx=v=>Lm+(cx(v)-xd[0])/(xd[1]-xd[0])*(W-Lm-R),sy=v=>T+(yd[1]-cy(v))/(yd[1]-yd[0])*(H-T-B);
 const X0=sx(100),Y0=sy(100);
 let s=`<svg class="plot mk-plot rrg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Relative Rotation Graph for ${esc(rrgDay(o.Q[f]))}; the table below lists every value">`;
 s+=`<rect class="rrg-lead" x="${X0}" y="${T}" width="${W-R-X0}" height="${Y0-T}"/><rect class="rrg-weak" x="${X0}" y="${Y0}" width="${W-R-X0}" height="${H-B-Y0}"/>`;
 s+=`<rect class="rrg-lag" x="${Lm}" y="${Y0}" width="${X0-Lm}" height="${H-B-Y0}"/><rect class="rrg-imp" x="${Lm}" y="${T}" width="${X0-Lm}" height="${Y0-T}"/>`;
 s+=`<text class="rot-watermark" x="${W-R-10}" y="${H-B-14}" text-anchor="end">${esc(rrgDay(o.Q[f]))}</text>`;
 niceTicks(yd[0],yd[1],6).forEach(v=>{s+=`<line class="mk-grid" x1="${Lm}" x2="${W-R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm-8}" y="${sy(v)+4}" text-anchor="end">${fmt(v,1)}</text>`});
 niceTicks(xd[0],xd[1],7).forEach(v=>{s+=`<line class="mk-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H-B}"/><text class="axis" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${fmt(v,1)}</text>`});
 s+=`<line class="mk-axis" x1="${X0}" x2="${X0}" y1="${T}" y2="${H-B}"/><line class="mk-axis" x1="${Lm}" x2="${W-R}" y1="${Y0}" y2="${Y0}"/>`;
 s+=`<text class="rrg-qt rrg-t-lead" x="${W-R-8}" y="${T+16}" text-anchor="end">Leading</text><text class="rrg-qt rrg-t-weak" x="${W-R-8}" y="${H-B-10}" text-anchor="end">Weakening</text>`;
 s+=`<text class="rrg-qt rrg-t-lag" x="${Lm+8}" y="${H-B-10}">Lagging</text><text class="rrg-qt rrg-t-imp" x="${Lm+8}" y="${T+16}">Improving</text>`;
 s+=`<text class="axis" x="${(Lm+W-R)/2}" y="${H-8}" text-anchor="middle">JdK RS-Ratio → (relative trend vs ${o.dual||o.ix?'each line\'s benchmark':esc(o.D.benchmark||'SPY')})</text>`;
 s+=`<text class="axis" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">JdK RS-Momentum →</text>`;
 const boxes=[];let marks='',labels='';
 for(const l of o.lines){
  if(o.solo&&l.e.id!==o.solo)continue;                  // one line alone
  const c=l.calc,ks=[];for(let k=Math.max(0,f-o.tail+1);k<=f;k++)if(c.x[k]!=null&&c.y[k]!=null)ks.push(k);
  if(!ks.length)continue;
  const pts=ks.map(k=>[sx(c.x[k]),sy(c.y[k])]);
  if(pts.length>1)marks+=`<path class="rot-line rrg-tail" style="stroke:${l.col}" d="${curve(pts,true)}"/>`;
  ks.forEach((k,i)=>{const hd=i===ks.length-1&&k===f,p=pts[i];
   marks+=`<g data-tip="${tip(rrgTipRows(o,l,k))}" tabindex="${hd?0:-1}" class="mk-hit"><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?10:6}" fill="transparent"/><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${hd?6:2.4}" class="rot-dot" style="fill:${l.col};opacity:${hd?1:(.3+.6*i/Math.max(1,ks.length-1)).toFixed(2)}"/></g>`});
  const h=pts[pts.length-1],pv=pts.length>1?pts[pts.length-2]:null;
  if(pv&&ks[ks.length-1]===f&&!(fcOn()&&o.freq==='w'&&o.n===14)){const a=Math.atan2(h[1]-pv[1],h[0]-pv[0]),tx=h[0]+Math.cos(a)*11,ty=h[1]+Math.sin(a)*11;
   marks+=`<path class="rrg-arrow" style="fill:${l.col}" d="M${tx.toFixed(1)},${ty.toFixed(1)} L${(tx-8*Math.cos(a-.45)).toFixed(1)},${(ty-8*Math.sin(a-.45)).toFixed(1)} L${(tx-8*Math.cos(a+.45)).toFixed(1)},${(ty-8*Math.sin(a+.45)).toFixed(1)} Z"/>`}
  const kl=ks[ks.length-1],text=l.e.name+(c.c&&c.c[kl]!=null?' '+rrglMoney(l.e,c.c[kl]):'')+(kl===f?'':' '+rrgDay(o.Q[kl])),w=text.length*6.8,right=h[0]+12+w<W-R,low=h[1]-22<T,ly=low?h[1]+18:h[1]-9;
  const b=[right?h[0]+9:h[0]-9-w,ly-11,right?h[0]+9+w:h[0]-9,ly+3];
  if(!boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1])){boxes.push(b);labels+=`<text class="mk-label mk-halo" x="${right?h[0]+9:h[0]-9}" y="${ly}" text-anchor="${right?'start':'end'}">${esc(text)}</text>`}
 }
 // the forecast paths of every line are left out while the chart plays or is exported (a replay per line per frame); the
 // path of one line — shown alone, or picked in "Forecast path" — moves with the play and is in the video
 const oneLine=!!(o.solo||(state.rrgfp&&state.rrgfp!=='all'));
 const still=typeof ROT==='undefined'||oneLine||!(ROT.timer||ROT.exporting);
 marks+=rrgFcLayer(o,f,sx,sy)+(typeof rrgOddsLayer==='function'?rrgOddsLayer(o,f,sx,sy):'')+(typeof rrglLayer==='function'&&still?rrglLayer(o,f,sx,sy):'');
 return s+marks+labels+'</svg>';
}
function rrgTable(o){
 const f=state.rf,dir=a=>['→','↗','↑','↖','←','↙','↓','↘'][((Math.round(a/(Math.PI/4))%8)+8)%8];
 const lab=typeof RRGLab==='object',PR=lab?RRGLab.PAR[o.freq]:null,mk=PR?PR.marks[PR.marks.length-1]:0;
 const rows=o.lines.map(l=>{const c=l.calc,x=c.x[f],y=c.y[f];if(x==null||y==null)return null;
  const qd=rrgQuad(x,y);let since=0;for(let k=f;k>=0&&c.x[k]!=null&&c.y[k]!=null&&rrgQuad(c.x[k],c.y[k])===qd;k--)since++;
  const k0=f-1,a=c.x[k0]!=null?Math.atan2(y-c.y[k0],x-c.x[k0]):null;
  const close=c.c?c.c[f]:null,L=lab&&close!=null&&c.rs?RRGLab.ladder(close,RRGLab.thresholds(c,c.rs,f)):null,F=lab&&c.c&&c.b?rrglFc(o,l,f):null,st=F&&F.steps[mk-1];
  return {l,x,y,qd,since,a,r52:c.z.r52[f],volz:c.z.volz[f],close,L,st}}).filter(Boolean).sort((p,q)=>q.x-p.x);
 exported=rows.map(r=>({date:o.Q[f],line:r.l.e.name,name:r.l.e.full||'',close:r.close==null?null:+r.close.toFixed(4),quadrant:RRG_Q[r.qd][1],rs_ratio:+r.x.toFixed(3),rs_momentum:+r.y.toFixed(3),
  periods_in_quadrant:r.since,heading_deg:r.a==null?null:Math.round(r.a*180/Math.PI),return_12m_vs_benchmark_pct:r.r52==null?null:+r.r52.toFixed(2),
  next_close_rs_ratio_100:r.L?+r.L.ratio.toFixed(4):null,next_close_rs_momentum_100:r.L?+r.L.momentum.toFixed(4):null,
  ...(r.st?{['path_date_'+mk]:r.st.date,['path_close_median_'+mk]:+r.st.p50.toFixed(4),['path_close_p10_'+mk]:+r.st.p10.toFixed(4),['path_close_p90_'+mk]:+r.st.p90.toFixed(4),
   ['path_rs_ratio_'+mk]:+r.st.x50.toFixed(3),['path_rs_momentum_'+mk]:+r.st.y50.toFixed(3)}:{})}));
 const unit=PR?PR.many:o.freq==='w'?'weeks':'months',one=PR?PR.one:'period';
 let out=`<div class="section-head"><h3>${fmt(rows.length)} lines · ${esc(rrgDay(o.Q[f]))}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Line','Close','Quadrant','RS-Ratio · RS-Momentum','12 months vs '+(o.ix?'its benchmark':o.D.benchmark||'SPY'),`Next ${one}: closes for RS-Ratio · RS-Momentum 100`,`Forecast path, +${mk} ${unit}`],rows.map(r=>[
  `<i class="mk-key" style="background:${r.l.col}"></i> <b>${esc(r.l.e.name)}</b> <span class="muted">${esc(rrgFull_(r.l.e))}</span>`,r.close==null?'—':rrglMoney(r.l.e,r.close),
  `<span class="badge rrg-b-${RRG_Q[r.qd][0]}">${RRG_Q[r.qd][1]}</span><br><span class="muted">${r.since} ${unit}</span>`,`${fmt(r.x,2)} · ${fmt(r.y,2)} ${r.a==null?'':dir(r.a)}`,
  r.r52==null?'—':`<span class="${r.r52>=0?'positive':'negative'}">${vfmt({unit:'%',centred:true},r.r52)}</span>`,
  r.L?`${rrglMoney(r.l.e,r.L.ratio)} · ${rrglMoney(r.l.e,r.L.momentum)}`:'—',
  r.st?`${esc(rrgDay(r.st.date))}: ${rrglMoney(r.l.e,r.st.p50)}<br><span class="muted">80%: ${rrglMoney(r.l.e,r.st.p10)}–${rrglMoney(r.l.e,r.st.p90)} · ${r.st.q.map((v,i)=>RRG_Q[i][1][0]+' '+rrglSh(v)).join(' ')}</span>`:'—']));
}

/* ---------- 3-D and 4-D (canvas; turned with the 3-D view's handlers in rotation.js) ---------- */
function rrgPaint3d(o,f){
 const cv=document.getElementById('rot-3d');if(!cv||!cv.getContext)return;
 const ctx=cv.getContext('2d');if(!ctx)return;
 const cw=cv.clientWidth||900,ch=Math.round(Math.max(380,Math.min(660,cw*.64))),dpr=window.devicePixelRatio||1;
 if(cv.width!==Math.round(cw*dpr)||cv.height!==Math.round(ch*dpr)){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.height=ch+'px'}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,cw,ch);
 const C=rotColors(),time=o.zk==='time',{x:xd,y:yd,z:zd}=o.dom,font=getComputedStyle(document.body).fontFamily||'sans-serif';
 const span=time?Math.max(3*o.tail,o.freq==='w'?26:12):o.tail,k0=Math.max(0,f-span+1);
 const nrm=(v,d)=>Math.max(-1.08,Math.min(1.08,(v-d[0])/(d[1]-d[0])*2-1));
 const zOf=(l,k)=>time?(span>1?(k-k0)/(span-1)*2-1:1):(l.calc.z[o.zk][k]==null?null:nrm(l.calc.z[o.zk][k],zd));
 const cy_=Math.cos(ROT.yaw),sy_=Math.sin(ROT.yaw),cp=Math.cos(ROT.pitch),sp=Math.sin(ROT.pitch),S=Math.min(cw*.9,ch)*.26,c0x=cw/2,c0y=ch/2-ch*.03,Dz=6.5;
 const proj=(X,Y,Z)=>{const x1=X*cy_-Z*sy_,z1=X*sy_+Z*cy_,y2=Y*cp-z1*sp,z2=Y*sp+z1*cp,k=Dz/(Dz-z2);return [c0x+x1*k*S,c0y-y2*k*S,z2,k]};
 const line=(a,b,col,w=1,alpha=1,dash)=>{const p=proj(...a),q=proj(...b);ctx.globalAlpha=alpha;ctx.strokeStyle=col;ctx.lineWidth=w;ctx.setLineDash(dash||[]);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1};
 const poly=(pts,col,alpha)=>{ctx.globalAlpha=alpha;ctx.fillStyle=col;ctx.beginPath();pts.map(p=>proj(...p)).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill();ctx.globalAlpha=1};
 const text=(pt,str,col,align='center',f_='11px')=>{const p=proj(...pt);ctx.fillStyle=col;ctx.font=`${f_} ${font}`;ctx.textAlign=align;ctx.fillText(str,p[0],p[1])};
 const X0=nrm(100,xd),Y0=nrm(100,yd),QC=[C.buy,C.sun,C.sell,C.series[0]];
 // the quadrants on the slice that is "now": the front in 3-D (time), the back wall in 4-D
 const zs=time?1:-1,quads=[[[X0,Y0],[1,1]],[[X0,-1],[1,Y0]],[[-1,-1],[X0,Y0]],[[-1,Y0],[X0,1]]];
 quads.forEach(([[a,b],[c,d]],i)=>poly([[a,b,zs],[c,b,zs],[c,d,zs],[a,d,zs]],QC[i],.09));
 const E=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
 for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]])line(E[a],E[b],C.line,1);
 for(let i=-1;i<=1;i+=.5){line([i,-1,-1],[i,-1,1],C.line,.7,.6);line([-1,-1,i],[1,-1,i],C.line,.7,.6)}
 line([X0,-1,-1],[X0,-1,1],C.muted,1,.7,[4,3]);line([-1,Y0,zs],[1,Y0,zs],C.muted,1,.8);line([X0,-1,zs],[X0,1,zs],C.muted,1,.8);
 line([X0,Y0,-1],[X0,Y0,1],C.muted,1,.5,[2,3]);                       // the 100 / 100 axis through the depth
 [['Leading',[1,1,zs],'right'],['Weakening',[1,-1,zs],'right'],['Lagging',[-1,-1,zs],'left'],['Improving',[-1,1,zs],'left']].forEach(([t_,p,al],i)=>{
  const q=[p[0]*.94,p[1]*.9-(p[1]>0?.02:-.06),p[2]];text(q,t_,QC[i],al,'600 11px')});
 const tk=(d,n)=>niceTicks(d[0],d[1],n),ends=t=>t.length>2?[t[0],t[t.length-1]]:t;
 for(const v of ends(tk(xd,6)))text([nrm(v,xd),-1.12,1.12],fmt(v,1),C.muted);
 for(const v of ends(tk(yd,6)))text([-1.12,nrm(v,yd),1.12],fmt(v,1),C.muted,'right');
 if(time){text([1.14,-1.12,-1],rrgDay(o.Q[k0]),C.muted,'left');text([1.14,-1.12,1],rrgDay(o.Q[f]),C.muted,'left')}
 else for(const v of ends(tk(zd,5)))text([1.14,-1.12,nrm(v,zd)],vfmt({unit:'%',centred:true},v),C.muted,'left');
 text([0,-1.3,1.12],'RS-Ratio →',C.ink,'center','600 12px');text([-1.18,1.12,1.0],'↑ RS-Momentum',C.ink,'right','600 12px');
 text([1.22,-1.28,0],time?'time →':RRG_ZINFO[o.zk].label+' →',C.ink,'left','600 12px');
 const dots=[];
 o.lines.forEach(l=>{
  if(o.solo&&l.e.id!==o.solo)return;                   // one line alone
  const ks=[];for(let k=k0;k<=f;k++)if(l.calc.x[k]!=null&&l.calc.y[k]!=null&&zOf(l,k)!=null)ks.push(k);
  const tailK=time?ks:ks.slice(-o.tail);if(!tailK.length)return;
  const P3=tailK.map(k=>[nrm(l.calc.x[k],xd),nrm(l.calc.y[k],yd),zOf(l,k)]);
  ctx.strokeStyle=l.col;ctx.lineWidth=2;
  for(let i=1;i<P3.length;i++){const a=proj(...P3[i-1]),b=proj(...P3[i]);ctx.globalAlpha=.2+.75*i/P3.length;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}
  ctx.globalAlpha=1;
  tailK.forEach((k,i)=>{const pr=proj(...P3[i]),hd=k===f;
   if(hd||i%Math.max(1,Math.round(tailK.length/26))===0)dots.push({x:pr[0],y:pr[1],d:pr[2],r:(hd?6:2)*pr[3],col:l.col,alpha:hd?1:.3+.6*i/tailK.length,rows:rrgTipRows(o,l,k),stroke:hd})});
  const h=P3[P3.length-1];
  if(tailK[tailK.length-1]===f){line(h,[h[0],-1,h[2]],l.col,1,.45,[2,3]);const pr=proj(...h);dots.push({label:l.e.name,x:pr[0],y:pr[1],d:pr[2]+.001})}
 });
 dots.sort((a,b)=>a.d-b.d);
 const hits=[],boxes=[];
 for(const d of dots){
  if(d.label){ctx.font=`500 12px ${font}`;const w=ctx.measureText(d.label).width,b=[d.x+8,d.y-20,d.x+12+w,d.y-6];
   if(boxes.some(q=>b[0]<q[2]&&b[2]>q[0]&&b[1]<q[3]&&b[3]>q[1]))continue;boxes.push(b);
   ctx.lineWidth=3;ctx.strokeStyle=C.surface;ctx.textAlign='left';ctx.strokeText(d.label,d.x+9,d.y-9);ctx.fillStyle=C.ink;ctx.fillText(d.label,d.x+9,d.y-9);continue}
  ctx.globalAlpha=d.alpha;ctx.fillStyle=d.col;ctx.beginPath();ctx.arc(d.x,d.y,Math.max(1,d.r),0,Math.PI*2);ctx.fill();
  if(d.stroke){ctx.globalAlpha=1;ctx.lineWidth=1.5;ctx.strokeStyle=C.surface;ctx.stroke()}
  ctx.globalAlpha=1;hits.push(d)}
 ctx.font=`700 40px ${font}`;ctx.textAlign='right';ctx.fillStyle=C.ink;ctx.globalAlpha=.08;ctx.fillText(rrgDay(o.Q[f]),cw-14,ch-14);ctx.globalAlpha=1;
 ROT.hits=hits;
}
