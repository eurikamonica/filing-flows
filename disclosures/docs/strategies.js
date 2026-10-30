/* Strategies — the hub tab: published trading rules run on the site's weekly history since 1995, with trading costs,
   cash and borrowing, results before and after each paper was published, the overfitting tests (PBO over each rule's
   nearby settings, the deflated Sharpe ratio over every setting tried) and the live paper ledger (each closed week's
   positions frozen and scored on later prices). Data: data/market/history/strategies.json and strategies-curves.json
   (rotation-history; app/strategies.py). Deep links: #strategies, #strategies/trend, #strategies/overfit. */
const stStore={};
const ST_PATH={rows:'data/market/history/strategies.json',curves:'data/market/history/strategies-curves.json'};
function stData(name){
 const m=stStore[name]||(stStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch(ST_PATH[name],{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const ST_VIEWS=[['all','Every rule'],['one','One rule'],['overfit','Overfitting tests']];
const ST_SORT=[['group','By kind'],['sharpe','Sharpe ratio'],['cagr','Annual return'],['maxdd','Smallest drawdown'],['dsr','Deflated Sharpe'],['post','Sharpe after publication']];
function stP(v,d=1){return v==null?'—':`${v<0?'−':''}${fmt(Math.abs(v*100),d)}%`}
function stS(v,d=1){return v==null?'—':`<span class="${v>=0?'positive':'negative'}">${v>=0?'+':'−'}${fmt(Math.abs(v*100),d)}%</span>`}
function stN(v,d=2){return v==null?'—':(v<0?'−':'')+fmt(Math.abs(v),d)}
function stProb(v){return v==null?'—':`<span class="${v>=0.95?'positive':v<0.5?'negative':''}">${fmt(v*100,0)}%</span>`}
function stPbo(p){return p==null?'—':`<span class="${p.pbo<=0.25?'positive':p.pbo>=0.5?'negative':''}">${fmt(p.pbo*100,0)}%</span>`}
function stDate(start,i){const d=new Date(Date.parse(start+'T00:00:00Z')+i*7*864e5);return d.toISOString().slice(0,10)}

/* a log-scale line chart of growth of $1: series [{name, i0, eq, color, dash}] on the weekly grid from `start` */
function stLines(series,start,opt={}){
 const W=opt.w||860,H=opt.h||260,L=54,R=10,T=12,B=26;
 const ser=series.filter(s=>s&&s.eq&&s.eq.length>1);
 if(!ser.length)return '';
 const lo=Math.min(...ser.map(s=>s.i0)),hi=Math.max(...ser.map(s=>s.i0+s.eq.length-1));
 let ymin=Infinity,ymax=-Infinity;
 ser.forEach(s=>s.eq.forEach(v=>{if(v>0){ymin=Math.min(ymin,v);ymax=Math.max(ymax,v)}}));
 const ly=v=>Math.log(Math.max(v,1e-6)),y0=ly(ymin),y1=ly(ymax)||y0+1;
 const X=i=>L+(i-lo)/Math.max(1,hi-lo)*(W-L-R),Y=v=>T+(1-(ly(v)-y0)/Math.max(1e-9,y1-y0))*(H-T-B);
 const step=Math.max(1,Math.ceil((hi-lo)/700));
 let g='';
 const ticks=[];for(let p=Math.floor(Math.log10(ymin)*3)/3;p<=Math.log10(ymax)+0.01;p+=1/3){const v=Math.pow(10,p);const n=+v.toPrecision(1);if(n>=ymin*0.98&&n<=ymax*1.02&&!ticks.includes(n))ticks.push(n)}
 ticks.forEach(v=>{g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${(Y(v)+4).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--muted)">$${v>=10?fmt(v,0):v}</text>`});
 const y0d=new Date(Date.parse(stDate(start,lo))).getUTCFullYear(),y1d=new Date(Date.parse(stDate(start,hi))).getUTCFullYear(),ys=Math.max(1,Math.ceil((y1d-y0d)/10));
 for(let y=y0d+1;y<=y1d;y+=ys){const i=lo+(Date.parse(y+'-01-01')-Date.parse(stDate(start,lo)))/(7*864e5);g+=`<text x="${X(i).toFixed(1)}" y="${H-8}" text-anchor="middle" font-size="10" fill="var(--muted)">${y}</text>`}
 ser.forEach(s=>{let d='';for(let k=0;k<s.eq.length;k+=step){d+=(d?'L':'M')+X(s.i0+k).toFixed(1)+','+Y(s.eq[k]).toFixed(1)}const k=s.eq.length-1;d+='L'+X(s.i0+k).toFixed(1)+','+Y(s.eq[k]).toFixed(1);
  g+=`<path d="${d}" fill="none" stroke="${s.color||'var(--accent)'}" stroke-width="${s.width||1.6}" ${s.dash?'stroke-dasharray="4 3"':''}><title>${esc(s.name)}</title></path>`});
 const leg=ser.map(s=>`<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px"><svg width="18" height="6"><line x1="0" x2="18" y1="3" y2="3" stroke="${s.color||'var(--accent)'}" stroke-width="2" ${s.dash?'stroke-dasharray="4 3"':''}/></svg>${esc(s.name)}</span>`).join('');
 return `<div style="overflow-x:auto"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:520px;height:auto" role="img" aria-label="${esc(opt.label||'Growth of $1')}">${g}</svg></div><div class="muted" style="font-size:.8rem">${leg}</div>`;
}
function stDrawdown(eq,i0,start,opt={}){
 if(!eq||eq.length<2)return '';
 const W=opt.w||860,H=opt.h||110,L=54,R=10,T=8,B=20;
 let pk=eq[0];const dd=eq.map(v=>{pk=Math.max(pk,v);return v/pk-1});
 const mn=Math.min(...dd,-0.01),X=k=>L+k/(eq.length-1)*(W-L-R),Y=v=>T+(v/mn)*(H-T-B),step=Math.max(1,Math.ceil(eq.length/700));
 let d=`M${L},${T}`;for(let k=0;k<dd.length;k+=step)d+='L'+X(k).toFixed(1)+','+Y(dd[k]).toFixed(1);d+=`L${X(dd.length-1).toFixed(1)},${T}Z`;
 let g=`<path d="${d}" fill="var(--neg-soft)" stroke="var(--neg)" stroke-width="1"/>`;
 [0.25,0.5,0.75].forEach(f=>{const v=mn*f;g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line)"/><text x="${L-6}" y="${(Y(v)+4).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--muted)">${fmt(v*100,0)}%</text>`});
 return `<div style="overflow-x:auto"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:520px;height:auto" role="img" aria-label="Drawdown from the previous peak">${g}<text x="${L}" y="${H-6}" font-size="10" fill="var(--muted)">${stDate(start,i0)}</text><text x="${W-R}" y="${H-6}" font-size="10" fill="var(--muted)" text-anchor="end">${stDate(start,i0+eq.length-1)}</text></svg></div>`;
}
function stYearBars(row,spy){
 const ys=Object.keys(row.yearly||{});if(!ys.length)return '';
 const sy=(spy&&spy.yearly)||{},vals=ys.flatMap(y=>[row.yearly[y],sy[y]]).filter(v=>v!=null);
 const mx=Math.max(0.05,...vals.map(Math.abs)),W=Math.max(520,ys.length*26),H=180,mid=H/2,bw=9;
 let g=`<line x1="0" x2="${W}" y1="${mid}" y2="${mid}" stroke="var(--line)"/>`;
 ys.forEach((y,k)=>{const x=k*26+4,a=row.yearly[y],b=sy[y];
  if(a!=null){const h=Math.abs(a)/mx*(mid-14);g+=`<rect x="${x}" y="${a>=0?mid-h:mid}" width="${bw}" height="${h.toFixed(1)}" fill="${a>=0?'var(--accent)':'var(--neg)'}"><title>${y}: ${stP(a)}</title></rect>`}
  if(b!=null&&row.id!=='spy'){const h=Math.abs(b)/mx*(mid-14);g+=`<rect x="${x+bw+1}" y="${b>=0?mid-h:mid}" width="${bw}" height="${h.toFixed(1)}" fill="var(--mk-rev)" opacity=".55"><title>${y} SPY: ${stP(b)}</title></rect>`}
  if(k%2===0)g+=`<text x="${x+bw}" y="${H-2}" font-size="9" text-anchor="middle" fill="var(--muted)">${y.slice(2)}</text>`});
 return `<div style="overflow-x:auto"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:${Math.min(W,700)}px;height:auto" role="img" aria-label="Return each year">${g}</svg></div><p class="muted" style="font-size:.8rem">Each year's return after costs (green / red), SPY beside it (grey). ${ys[0]} is a part year from the rule's start.</p>`;
}

function stRowsSorted(d){
 const k=state.sts||'group',rows=d.rows.slice();
 const key={sharpe:r=>r.full.sharpe,cagr:r=>r.full.cagr,maxdd:r=>r.full.maxdd,dsr:r=>r.dsr==null?-1:r.dsr,post:r=>r.post?r.post.sharpe:-9}[k];
 if(key)rows.sort((a,b)=>key(b)-key(a));
 return rows;
}
function stTable(d){
 const rows=stRowsSorted(d);exported=rows.map(r=>({id:r.id,name:r.name,group:r.group,paper:r.paper,from:r.full.from,cagr:r.full.cagr,vol:r.full.vol,sharpe:r.full.sharpe,maxdd:r.full.maxdd,
  sharpe_before:r.pre&&r.pre.sharpe,sharpe_after:r.post&&r.post.sharpe,dsr:r.dsr,pbo:r.pbo&&r.pbo.pbo,turnover:r.turnover,cost_drag:r.cost_drag,live_return:r.live&&r.live.ret}));
 let grp='';
 const body=rows.map(r=>{
  const f=r.full;let pre='';
  if((state.sts||'group')==='group'&&r.group!==grp){grp=r.group;pre=`<tr><td colspan="11" style="background:var(--bg);font-weight:600">${esc(grp)}</td></tr>`}
  const live=r.live?(r.live.weeks?stS(r.live.ret)+` <span class="muted">${r.live.weeks} wk</span>`:`<span class="muted" title="frozen from ${esc(r.live.since)}">started</span>`):'—';
  return pre+`<tr><td style="min-width:200px"><button class="text-button" style="text-align:left" data-stid="${esc(r.id)}"><b>${esc(r.name)}</b></button><br><span class="muted" style="font-size:.78rem">${esc(r.paper)}${r.site?' · site data':''}</span></td>
   <td class="mono">${esc((f.from||'').slice(0,4))}</td><td>${stS(f.cagr)}</td><td>${stP(f.vol,0)}</td><td><b>${stN(f.sharpe)}</b></td><td class="negative">${stP(f.maxdd,0)}</td>
   <td>${r.pre?stN(r.pre.sharpe):'—'} → ${r.post?stN(r.post.sharpe):'—'}</td><td>${r.bench?'<span class="muted">benchmark</span>':stProb(r.dsr)}</td><td>${stPbo(r.pbo)}</td><td>${r.cost_drag==null?'—':stP(r.cost_drag,2)}</td><td>${live}</td></tr>`}).join('');
 return `<div class="tablebox"><table><thead><tr><th>Rule</th><th>From</th><th>Return a year</th><th>Volatility</th><th>Sharpe</th><th>Worst drawdown</th><th>Sharpe before → after paper</th><th>Deflated Sharpe</th><th>PBO</th><th>Costs a year</th><th>Live</th></tr></thead><tbody>${body}</tbody></table></div>`;
}
const ST_COLORS=['var(--accent)','var(--slate)','var(--mk-cost)','var(--warn-ink)','#8b6bb8','#2a9d8f','#c06c84','#6c8a3c'];
function stAll(d,cv){
 const S=d.rows.filter(r=>!r.bench),best=S.slice().sort((a,b)=>(b.dsr||0)-(a.dsr||0))[0],live=S.filter(r=>r.live&&r.live.weeks).length;
 let out=`<div class="metrics">${kpi('Rules',fmt(S.length),'plus '+(d.rows.length-S.length)+' benchmarks')}${kpi('Settings tried',fmt(d.trials),'every one counted in the deflated Sharpe')}${kpi('Luck bar',stN(d.sr0_annual),'the Sharpe ratio the best of '+d.trials+' tries reaches by luck')}${kpi('Most credible',best?best.name.split(':')[0]:'—',best?'deflated Sharpe '+fmt((best.dsr||0)*100,0)+'%':'')}</div>`;
 out+=`<p class="muted" style="max-width:900px">Each rule exactly as its paper published it, tested on weekly closes from 1995 (or from when its funds or data begin) to the week ending ${esc(d.asof)}, after trading costs (${esc(d.assumptions.cost)}), with cash earning the ${esc(d.assumptions.cash)} and a ${fmt(d.assumptions.borrow*100,1)}% a year borrow fee on shorts. <b>Survivorship:</b> ${esc(d.survivorship)} The equal-weighted universe of the same survivors is the fair benchmark for stock rules. Not investment advice.</p>`;
 if(cv){const pick=['spy','trend','riskparity','lowvol','ensemble'].map((id,k)=>{const c=cv.curves[id],r=d.rows.find(x=>x.id===id);return c&&r?{name:r.name,i0:c.i0,eq:c.eq,color:ST_COLORS[k],dash:id==='spy'}:null});out+=`<div class="section-head"><h3>Growth of $1, a few rules</h3><span class="muted">log scale · open a rule for its own chart</span></div>`+stLines(pick,cv.start)}
 out+=`<div class="section-head"><h3>Every rule</h3><button class="action" id="csv">Export CSV ↓</button></div>`+stTable(d);
 out+=`<p class="muted" style="font-size:.8rem;max-width:900px"><b>Sharpe</b>: the return above cash per unit of volatility, a year. <b>Before → after paper</b>: the Sharpe ratio up to the end of the year the rule was published and after it — after is the out-of-sample test (published anomalies lose about a third, McLean and Pontiff 2016). <b>Deflated Sharpe</b>: the probability that the rule's true Sharpe ratio is above zero once the ${d.trials} settings tried here, skew and fat tails are allowed for (Bailey and López de Prado 2014); 95% or more is convincing. <b>PBO</b>: the probability that picking the best of the rule's nearby settings in one half of history picks one below the median in the other half (Bailey et al. 2017); low is good. <b>Live</b>: the return of the positions frozen each week since the rule went live on the site.</p>`;
 return out;
}
function stOne(d,cv,id){
 const r=d.rows.find(x=>x.id===id);if(!r)return empty('Pick a rule from the list.');
 const spy=d.rows.find(x=>x.id==='spy'),ew=d.rows.find(x=>x.id==='ew'),f=r.full,c=cv&&cv.curves[id];
 let out=`<div class="section-head"><div><h3>${esc(r.name)}</h3><p class="sub">${esc(r.paper)}${r.year?' · published '+r.year:''} · ${esc(r.group)}${r.site?' · uses the site\'s own data':''}</p></div><span class="tag">${esc((f.from||'').slice(0,10))} → ${esc(f.to||'')}</span></div>`;
 out+=`<p style="max-width:900px">${esc(r.rules)}</p>`;
 out+=`<div class="metrics">${kpi('Return a year',stP(f.cagr),'after costs; SPY same years '+stP(r.spy_same&&r.spy_same.cagr))}${kpi('Sharpe ratio',stN(f.sharpe),'SPY same years '+stN(r.spy_same&&r.spy_same.sharpe))}${kpi('Worst drawdown',stP(f.maxdd,0),'at '+(f.maxdd_at||'—')+'; SPY '+stP(r.spy_same&&r.spy_same.maxdd,0))}${kpi('Deflated Sharpe',r.dsr==null?'—':fmt(r.dsr*100,0)+'%','chance the edge is real after '+d.trials+' tries')}</div>`;
 if(c){
  const s=[{name:r.name,i0:c.i0,eq:c.eq,color:'var(--accent)',width:2}];
  const sc=cv.curves.spy;if(sc&&id!=='spy'){const k=c.i0-sc.i0;if(k>=0){const base=sc.eq[k];s.push({name:'SPY',i0:c.i0,eq:sc.eq.slice(k).map(v=>v/base),color:'var(--mk-rev)',dash:true})}}
  const ec=cv.curves.ew,stockRule=!r.bench&&/universe|stocks/i.test(r.rules);
  if(ec&&ew&&stockRule){const k=c.i0-ec.i0;if(k>=0){const base=ec.eq[k];s.push({name:'Equal-weighted survivors',i0:c.i0,eq:ec.eq.slice(k).map(v=>v/base),color:'var(--slate)',dash:true})}}
  out+=`<div class="section-head"><h3>Growth of $1</h3><span class="muted">log scale · after costs</span></div>`+stLines(s,cv.start)+`<div class="section-head"><h3>Drawdown</h3><span class="muted">below the previous peak</span></div>`+stDrawdown(c.eq,c.i0,cv.start);
 }
 out+=`<div class="section-head"><h3>Year by year</h3></div>`+stYearBars(r,spy);
 const per=[['Whole history',f],['Before publication (to '+(r.year||'—')+')',r.pre],['After publication',r.post],['Last five years',r.last5]];
 out+=`<div class="section-head"><h3>Out of sample</h3><span class="muted">the paper's rule, never refitted</span></div>`+table(['Period','From','Return a year','Volatility','Sharpe','Worst drawdown','Beta to SPY','Alpha a year','Chance Sharpe > 0'],per.filter(x=>x[1]).map(([l,m])=>[esc(l),esc((m.from||'').slice(0,7)),stS(m.cagr),stP(m.vol,0),`<b>${stN(m.sharpe)}</b>`,stP(m.maxdd,0),stN(m.beta),stS(m.alpha),stProb(m.psr)]));
 if(r.turnover!=null)out+=`<p class="muted">Trading: ${fmt(r.turnover,1)}× its capital a year · costs ${stP(r.cost_drag,2)} a year (before costs ${stP(r.gross_cagr)} a year) · average exposure ${fmt((r.exposure||0)*100,0)}% of capital.</p>`;
 if(r.pbo){const p=r.pbo,mx=Math.max(...p.variants.map(v=>Math.abs(v.sharpe||0)),0.1);
  out+=`<div class="section-head"><h3>Nearby settings</h3><span class="muted">PBO ${fmt(p.pbo*100,0)}% over ${p.splits} splits of ${esc(p.from.slice(0,4))}–${esc(p.to.slice(0,4))}</span></div>`;
  out+=table(['Setting','Sharpe',''],p.variants.map(v=>{const main=Object.entries(v.params).every(([k,x])=>r.params&&r.params[k]===x);return [esc(Object.entries(v.params).map(([k,x])=>k+' '+x).join(', '))+(main?' <span class="tag">the paper\'s</span>':''),stN(v.sharpe),`<span style="display:inline-block;height:8px;width:${Math.round(Math.abs(v.sharpe||0)/mx*160)}px;background:${(v.sharpe||0)>=0?'var(--accent)':'var(--neg)'}"></span>`]}));
  out+=`<p class="muted" style="font-size:.8rem">If the paper's setting stands out from its neighbours, its result may be luck; a flat row of similar Sharpe ratios is what a robust rule looks like. A PBO near 50% or above means choosing the best setting in one half of history did not pick a good one in the other.</p>`}
 if(r.holdings){out+=`<div class="section-head"><h3>What it holds now</h3><span class="muted">${fmt(r.n_holdings)} positions · cash ${stP(r.cash,0)} · for the week after ${esc(d.asof)}</span></div>`;
  out+=r.holdings.length?`<p style="line-height:2">${r.holdings.map(([t,w])=>`<span class="tag" style="margin-right:6px"><b>${esc(t)}</b> <span class="${w<0?'negative':''}">${stP(w,w>=0.1||w<=-0.1?0:2)}</span></span>`).join('')}${r.n_holdings>r.holdings.length?` <span class="muted">… and ${fmt(r.n_holdings-r.holdings.length)} more</span>`:''}</p>`:empty('Nothing: the rule is in cash this week.')}
 if(r.live){const L=r.live;out+=`<div class="section-head"><h3>Live paper record</h3><span class="muted">positions frozen each week since ${esc(L.since)}</span></div>`;
  out+=L.weeks?`<p>${L.weeks} week${L.weeks>1?'s':''} live: ${stS(L.ret)} (positions frozen when each week closed, scored on the next week's prices; never recomputed).</p>`+(L.curve&&L.curve.length>1?stLines([{name:'Live',i0:0,eq:[1,...L.curve.map(x=>x[1])],color:'var(--accent)'}],L.since,{h:160}):''):`<p class="muted">Frozen from ${esc(L.since)}; the first week is scored once the next week closes.</p>`}
 return out;
}
function stOverfit(d){
 const S=d.rows.filter(r=>!r.bench);
 let out=`<p style="max-width:900px">A backtest that tries many settings will find a good-looking one by luck. Here every setting tried is counted: <b>${d.trials}</b> — the rules as published and the nearby settings run only to test them. With that many tries, the best Sharpe ratio expected from pure luck is about <b>${stN(d.sr0_annual)}</b> a year (Bailey and López de Prado 2014); a rule has to beat that bar, not zero.</p>`;
 const mx=Math.max(...S.map(r=>Math.abs(r.full.sharpe)),d.sr0_annual,0.1);
 out+=table(['Rule','Sharpe','vs the luck bar','Deflated Sharpe','PBO','After publication'],S.slice().sort((a,b)=>(b.dsr||0)-(a.dsr||0)).map(r=>{const w=Math.round(Math.abs(r.full.sharpe)/mx*180),bar=Math.round(d.sr0_annual/mx*180);
  return [`<button class="text-button" data-stid="${esc(r.id)}">${esc(r.name)}</button>`,stN(r.full.sharpe),`<span style="position:relative;display:inline-block;width:190px;height:10px"><span style="position:absolute;left:0;top:1px;height:8px;width:${w}px;background:${r.full.sharpe>=d.sr0_annual?'var(--accent)':r.full.sharpe>=0?'var(--slate)':'var(--neg)'}"></span><span style="position:absolute;left:${bar}px;top:-2px;height:14px;border-left:2px dashed var(--ink)"></span></span>`,stProb(r.dsr),stPbo(r.pbo),r.post?stN(r.post.sharpe):'—']}));
 out+=`<p class="muted" style="font-size:.8rem">The dashed line is the luck bar. Deflated Sharpe: the probability that the true Sharpe ratio is above zero given the ${d.trials} tries, the weeks of history, skew and fat tails. PBO (probability of backtest overfitting): over 252 ways of splitting history into halves, how often the best of a rule's settings in one half falls below the median in the other.</p>`;
 return out;
}
function strategiesView(){
 state.stv=ST_VIEWS.some(v=>v[0]===state.stv)?state.stv:'all';
 let out=head('Strategies','Published trading rules — trend, momentum, mean reversion, seasonality, factors from the site\'s SEC and 13F data, pairs, sector rotation, volatility targeting and risk parity — run on weekly closes since 1995 with trading costs, cash and borrowing, judged before and after their papers were published, tested for overfitting, and followed live week by week.','BACKTESTS · OUT OF SAMPLE · LIVE');
 const g=stData('rows'),cv=stData('curves');
 out+=`<div class="toolbar">${field('stv','View',ST_VIEWS,state.stv)}`;
 if(state.stv==='all')out+=field('sts','Sort',ST_SORT,state.sts||'group');
 if(state.stv==='one'&&g.data)out+=field('stid','Rule',g.data.rows.map(r=>[r.id,r.name]),state.stid||'trend',true);
 out+='</div>';
 if(g.err)return out+empty(`The strategies could not load (${g.err}). They are rebuilt by .github/workflows/rotation-history.yml (app/strategies.py).`);
 if(!g.data)return out+empty('Loading the strategies…');
 if(state.stv==='overfit')return out+stOverfit(g.data);
 if(state.stv==='one')return out+stOne(g.data,cv.data,state.stid||'trend');
 return out+stAll(g.data,cv.data);
}
function bindStrategies(){
 if(state.tab!=='strategies')return;
 ['stv','sts','stid'].forEach(id=>{if($(id))$(id).onchange=e=>{state[id]=e.target.value;render()}});
 document.querySelectorAll('#workspace [data-stid]').forEach(b=>b.onclick=()=>{state.stv='one';state.stid=b.dataset.stid;render();scrollTo({top:0,behavior:'smooth'})});
}
function strategiesDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(ST_VIEWS.some(x=>x[0]===v)){state.stv=v;return}
 state.stv='one';state.stid=v;
}
function strategiesNotice(){
 const s=stData('rows'),d=s.data;
 if(s.err)return {stale:true,text:'Official derived view · Strategies unavailable · '+s.err};
 if(!d)return {stale:false,text:'Official derived view · Strategies loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=30),text:`Official derived view · Strategies built ${d.generated_at} · ${fmt(d.rows.length)} rules · week ending ${d.asof} · rebuilt with the weekly closes every three hours`+(age>30?' · stale':'')};
}
window.strategiesDeepLink=strategiesDeepLink;
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{strategies:strategiesNotice});
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{strategies:strategiesView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{strategies:bindStrategies});
if(typeof module!=='undefined')module.exports={stLines,stDrawdown,stYearBars,stTable,stAll,stOne,stOverfit};
