/* Market maps — where the disclosed money moved (a Sankey of groups → sectors → stocks), the watched 13F managers'
   portfolios by sector and their holdings race, the market as a heatmap, who is crowded into what (an ownership network
   with a crowding index), the corporate debt maturity wall, and two gauges of the whole market: valuation (Buffett
   indicator, Shiller CAPE, excess CAPE yield, forward P/E) and net liquidity (Fed balance sheet − TGA − reverse repo).
   Data: data/research/market/*.json (app/market_maps.py, branch research-market, rebuilt after each session). */
const mmStore={};
function mmData(name){
 const m=mmStore[name]||(mmStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/research/market/'+name+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const MM_VIEWS=[['flows','Money flows: groups → sectors → stocks'],['manager','A manager’s portfolio by sector'],['race','Holdings race'],['heatmap','Market heatmap'],['network','Ownership network & crowding'],['maturity','Debt maturity wall'],['thermo','Valuation thermometer'],['liquidity','Net liquidity']];
const MM_PAL=['#17734a','#345ca0','#c47828','#824696','#288c96','#aa3c50','#5a7832','#7a7974','#966e46','#3c6ec8','#c8508c','#6ea05a'];
const mmUSD=v=>v==null||!Number.isFinite(+v)?'—':(v<0?'−':'')+'$'+compact(Math.abs(v));
const mmSUSD=v=>v==null||!Number.isFinite(+v)?'—':(v>0?'+':v<0?'−':'')+'$'+compact(Math.abs(v));
const mmPct=(v,d=0)=>v==null||!Number.isFinite(+v)?'—':fmt(v*100,d)+'%';
function mmCSS(){
 if(document.getElementById('mm-css'))return;
 const s=document.createElement('style');s.id='mm-css';
 s.textContent=`.mm-svg{display:block;width:100%;height:auto;margin-top:10px}.mm-svg text{font:11px var(--sans);fill:var(--ink)}.mm-svg .mm-small{font-size:9px}.mm-svg .mm-muted{fill:var(--muted)}
 .mm-gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:14px 0}.mm-gauge{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--surface)}
 .mm-gauge strong{font-size:26px;display:block;margin:4px 0}.mm-bar{position:relative;height:8px;border-radius:4px;background:linear-gradient(90deg,var(--mk-profit),var(--line),var(--mk-cost));margin:8px 0 4px}
 .mm-bar i{position:absolute;top:-4px;width:3px;height:16px;background:var(--ink);border-radius:2px}.mm-legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:6px}
 .mm-legend span:before{content:'';display:inline-block;width:10px;height:10px;margin-right:4px;border-radius:2px;background:var(--c)}`;
 document.head.appendChild(s);
}

// ---------------------------------------------------------------- a small Sankey (columns by depth, bands by value)
function mmSankey(links,opt={}){
 const W=opt.width||980,H=opt.height||560,NW=12,PAD=8,top=opt.labelTop||14;
 const nodes={},order=[];
 const node=n=>nodes[n]||(order.push(n),nodes[n]={id:n,inV:0,outV:0,ins:[],outs:[]});
 links.filter(l=>l.v>0).forEach(l=>{const a=node(l.from),b=node(l.to);a.outV+=l.v;b.inV+=l.v;a.outs.push(l);b.ins.push(l)});
 const ids=order;if(!ids.length)return empty('Nothing to draw for this selection.');
 const depth={};ids.forEach(n=>{if(!nodes[n].ins.length)depth[n]=0});
 let changed=true,guard=0;while(changed&&guard++<20){changed=false;links.forEach(l=>{if(depth[l.from]!=null&&(depth[l.to]==null||depth[l.to]<depth[l.from]+1)){depth[l.to]=depth[l.from]+1;changed=true}})}
 const cols=[];ids.forEach(n=>{const d=depth[n]||0;(cols[d]=cols[d]||[]).push(n)});
 const val=n=>Math.max(nodes[n].inV,nodes[n].outV);
 const scale=Math.min(...cols.map(c=>(H-top-PAD*(c.length-1))/c.reduce((a,n)=>a+val(n),0)));
 const xOf=d=>d*(W-NW-(opt.rightLabel||150))/Math.max(cols.length-1,1);
 cols.forEach((c,d)=>{c.sort((a,b)=>val(b)-val(a));let y=top;c.forEach(n=>{const o=nodes[n];o.x=xOf(d);o.y=y;o.h=Math.max(1,val(n)*scale);o.d=d;y+=o.h+PAD;o.oy=o.y;o.iy=o.y})});
 const colour=opt.colour||(()=>'#7a7974');
 let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label||'Sankey diagram')}">`;
 const L=[...links].filter(l=>l.v>0).sort((a,b)=>nodes[a.from].y-nodes[b.from].y||nodes[a.to].y-nodes[b.to].y);
 L.forEach(l=>{const a=nodes[l.from],b=nodes[l.to],w=l.v*scale,x0=a.x+NW,x1=b.x,y0=a.oy+w/2,y1=b.iy+w/2,mx=(x0+x1)/2;a.oy+=w;b.iy+=w;
  s+=`<path d="M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}" stroke="${colour(l.to,l)}" stroke-opacity=".35" stroke-width="${Math.max(1,w)}" fill="none"><title>${esc(l.from)} → ${esc(l.to)}: ${esc(opt.fmt?opt.fmt(l.v):fmt(l.v))}</title></path>`});
 ids.forEach(n=>{const o=nodes[n],c=colour(n);s+=`<rect x="${o.x}" y="${o.y}" width="${NW}" height="${o.h}" fill="${c}"><title>${esc(n)}: ${esc(opt.fmt?opt.fmt(val(n)):fmt(val(n)))}</title></rect>`;
  if(o.h>=9||o.d===cols.length-1){const right=o.d<cols.length-1,tx=right?o.x+NW+4:o.x+NW+4;s+=`<text x="${tx}" y="${o.y+Math.min(o.h/2,10)+4}">${esc(n)} <tspan class="mm-muted">${esc(opt.fmt?opt.fmt(val(n)):fmt(val(n)))}</tspan></text>`}});
 return s+'</svg>';
}

// ---------------------------------------------------------------- views
function mmFlows(){
 const m=mmData('flows');if(m.err)return empty('The money-flow map could not load ('+m.err+').');if(!m.data)return empty('Loading the money flows…');
 const P=m.data.periods||[];if(!P.length)return empty('No flows yet.');
 state.mmp=P.some(p=>p.key===state.mmp)?state.mmp:P[0].key;state.mmside=state.mmside==='sell'?'sell':'buy';
 const p=P.find(x=>x.key===state.mmp),side=p[state.mmside]||{links:[]};
 const gcol={'13F managers':'#345ca0','Active ETFs':'#288c96','Insiders':'#c47828',"Insiders' 10b5-1 plans":'#966e46','Officials':'#824696'};
 const secs={};let si=0;
 let out=`<div class="toolbar">${field('mmp','Period',P.map(x=>[x.key,x.label]),state.mmp,true)}${field('mmside','Show',[['buy','Net buying'],['sell','Net selling']],state.mmside)}</div>`;
 out+=`<div class="metrics">${(p.groups||[]).map(g=>kpi(g.label,mmSUSD(g.net),`bought ${mmUSD(g.buy)} · sold ${mmUSD(g.sell)}`)).join('')}</div>`;
 out+=`<div class="panel"><h3>${state.mmside==='buy'?'Net buying':'Net selling'}: ${mmUSD(side.total)} · ${esc(p.label||'')}</h3><p class="sub">Each name's trades netted per stock, then summed by group, sector and stock (the ${state.mmside==='buy'?'largest buys':'largest sales'} named; the rest per sector as "Other …"). Hover a band for its dollars.</p>`;
 out+=mmSankey(side.links,{fmt:mmUSD,label:'Money-flow Sankey',colour:(n,l)=>gcol[n]||(n.startsWith('$')?(state.mmside==='buy'?'var(--mk-profit)':'var(--mk-cost)'):n.startsWith('Other')?'#b8b6b0':(secs[n]||(secs[n]=MM_PAL[si++%MM_PAL.length])))})+'</div>';
 out+=`<div class="charts even"><div class="panel"><h3>Sectors, net</h3>${table(['Sector','Net dollars'],(p.sectors||[]).map(s=>[esc(s.label),afMoneyMM(s.net)]))}</div><div class="panel"><h3>Most net-bought · net-sold</h3>${table(['Stock','Net'],[...(p.top_in||[]).slice(0,6),...(p.top_out||[]).slice(0,6)].map(r=>[`<b>${esc(r.ticker)}</b> <span class="muted">${esc(r.name||'')}</span>`,afMoneyMM(r.net)]))}</div></div>`;
 out+=`<div class="explain">${esc(p.note||'')} Groups: 13F managers (quarter-over-quarter changes × the quarter-end close), active ETFs (N-PORT), insiders (Form 4 open-market trades; their 10b5-1 plan trades apart when published), officials (House and Senate, the middle of each range). Source: the Smart money tab's combined flows. Not investment advice.</div>`;
 return out;
}
const afMoneyMM=v=>v==null?'—':`<span class="${v>0?'positive':v<0?'negative':''}">${mmSUSD(v)}</span>`;
function mmManager(){
 const m=mmData('managers');if(m.err)return empty('The managers could not load ('+m.err+').');if(!m.data)return empty('Loading the portfolios…');
 const M=m.data.managers||[];if(!M.length)return empty('No 13F portfolios yet.');
 state.mmm=M.some(x=>x.cik===state.mmm)?state.mmm:M[0].cik;
 const x=M.find(y=>y.cik===state.mmm),links=[],stat={new:'#17734a',added:'#5aa77c',cut:'#ea6a52',exited:'#b04a3a',same:'#9a9893',held:'#9a9893'};
 const scol={};let i=0;
 (x.sectors||[]).forEach(s=>{if(s.usd<=0)return;links.push({from:'Portfolio',to:s.label,v:s.usd});const named=s.positions.filter(p=>p.usd>0).slice(0,6),rest=s.usd-named.reduce((a,p)=>a+p.usd,0);
  named.forEach(p=>links.push({from:s.label,to:(p.ticker||p.issuer||'?').slice(0,22),v:p.usd,st:p.status}));if(rest>s.usd*0.02)links.push({from:s.label,to:'Other '+s.label.toLowerCase(),v:rest})});
 const stOf={};links.forEach(l=>{if(l.st)stOf[l.to]=l.st});
 let out=`<div class="toolbar">${field('mmm','Manager (the hub’s 13F watchlist)',M.map(y=>[y.cik,`${y.name} · ${y.period}`]),state.mmm,true)}</div>`;
 out+=`<div class="metrics">${kpi('Long stock positions',mmUSD(x.total),`${fmt(x.positions)} positions · quarter ended ${x.period}`)}${kpi('Quarter before',mmUSD(x.prev_total),x.prev_period||'—')}${kpi('Options (puts and calls)',mmUSD(x.options_usd),'reported value, left out above')}${kpi('Filed',x.filed||'—','13F: quarter-end holdings, weeks later')}</div>`;
 out+=`<div class="panel"><h3>${esc(x.name)}: portfolio → sectors → positions</h3><p class="sub">Positions coloured by what changed since ${esc(x.prev_period||'the quarter before')}.</p>${mmSankey(links,{fmt:mmUSD,label:'Portfolio Sankey',colour:n=>n==='Portfolio'?'#7a7974':stOf[n]?stat[stOf[n]]:n.startsWith('Other')?'#b8b6b0':(scol[n]||(scol[n]=MM_PAL[i++%MM_PAL.length]))})}
  <div class="mm-legend">${Object.entries({new:'New',added:'Added',cut:'Cut',same:'Unchanged'}).map(([k,l])=>`<span style="--c:${stat[k]}">${l}</span>`).join('')}</div></div>`;
 out+=`<div class="panel"><h3>Sector weights, this quarter against the one before</h3>${table(['Sector','Weight','Before','Change','Largest positions'],(x.sectors||[]).map(s=>[esc(s.label),mmPct(s.w,1),mmPct(s.prev_w,1),s.w!=null&&s.prev_w!=null?`<span class="${s.w>=s.prev_w?'positive':'negative'}">${(s.w-s.prev_w>=0?'+':'−')+fmt(Math.abs(s.w-s.prev_w)*100,1)} pts</span>`:'—',s.positions.slice(0,4).map(p=>`${esc(p.ticker||p.issuer)} <span class="muted">${esc(p.status)}</span>`).join(', ')]))}</div>`;
 return out+`<div class="explain">From the manager's 13F reports (long stock positions; options listed apart). Sectors from the Consensus / Debt modules' classification, else Nasdaq's; ETFs and unmapped securities under "Other". Not investment advice.</div>`;
}
function mmRace(){
 const m=mmData('managers');if(m.err)return empty('The managers could not load ('+m.err+').');if(!m.data)return empty('Loading…');
 const M=m.data.managers||[],opts=[['all','All watched managers combined'],...M.map(x=>[x.cik,x.name])];
 state.mmr=opts.some(o=>o[0]===state.mmr)?state.mmr:'all';
 const race=state.mmr==='all'?(m.data.combined_race||[]):((M.find(x=>x.cik===state.mmr)||{}).race||[]);
 if(!race.length)return empty('No quarters to race yet.');
 state.mmq=Math.min(race.length-1,Math.max(0,state.mmq==null?race.length-1:+state.mmq));
 const q=race[state.mmq],vmax=Math.max(...race.flatMap(r=>r.top.slice(0,12).map(t=>t[1])),1),col={};let ci=0;
 race.forEach(r=>r.top.forEach(t=>{if(!col[t[0]])col[t[0]]=MM_PAL[ci++%MM_PAL.length]}));
 const W=900,rowH=30,H=24+12*rowH;
 let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Largest holdings, quarter ended ${esc(q.period)}">`;
 q.top.slice(0,12).forEach((t,i)=>{const y=8+i*rowH,w=Math.max(2,(W-260)*t[1]/vmax);s+=`<text x="0" y="${y+18}" font-weight="600">${esc(t[0])}</text><rect x="80" y="${y}" width="${w}" height="${rowH-8}" rx="3" fill="${col[t[0]]}"/><text x="${88+w}" y="${y+16}">${mmUSD(t[1])}${t[2]?' · '+mmPct(t[2],1):''}</text>`});
 s+='</svg>';
 const img=state.mmr==='all'?'race-all.gif':`race-${state.mmr}.gif`;
 return `<div class="toolbar">${field('mmr','Portfolio',opts,state.mmr,true)}<div class="field wide"><label for="mmq">Quarter ended ${esc(q.period)} (${state.mmq+1} of ${race.length})</label><input type="range" id="mmq" min="0" max="${race.length-1}" value="${state.mmq}"></div><div class="field"><label>&nbsp;</label><button class="action" id="mmplay">▶ Play</button></div></div>
 <div class="panel"><h3>Largest holdings · quarter ended ${esc(q.period)} · ${mmUSD(q.total)}${q.managers?` · ${fmt(q.managers)} managers`:''}</h3>${s}<p class="sub">The animated version for X: <a href="data/research/market/img/${esc(img)}" target="_blank" rel="noopener">${esc(img)} ↗</a> (rebuilt after each session for the largest portfolios).</p></div>
 <div class="explain">13F long positions at each quarter's end; the same colour follows a stock across quarters. Combined: all watched managers' positions summed, for quarters most of them have filed.</div>`;
}
function mmColor(v,kind,span){
 if(v==null||!Number.isFinite(+v))return '#cfcdc7';
 let x=kind==='diverging-mid'?(v-span)/span:kind==='diverging-inv'?-v/span:v/span;x=Math.max(-1,Math.min(1,x));
 const g=[190,188,182],e=x>0?[23,115,74]:[234,106,82],a=Math.abs(x);return `rgb(${g.map((c,i)=>Math.round(c+(e[i]-c)*a)).join(',')})`;
}
function mmHeatmap(){
 const m=mmData('heatmap');if(m.err)return empty('The heatmap could not load ('+m.err+').');if(!m.data)return empty('Loading the market map…');
 const d=m.data,F=d.fields,M=d.metrics||[];state.mmc=M.some(x=>x[0]===state.mmc)?state.mmc:'chg';
 const met=M.find(x=>x[0]===state.mmc),ix=F.indexOf(state.mmc),ir=F.indexOf('rect'),it=F.indexOf('ticker'),inm=F.indexOf('name'),imc=F.indexOf('mcap');
 const [W,H]=d.box;let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Market heatmap coloured by ${esc(met[1])}">`;
 d.cells.forEach(c=>{const [x,y,w,h]=c[ir],v=c[ix];const val=state.mmc==='chg'?(v==null?'—':(v>0?'+':'')+fmt(v,2)+'%'):state.mmc==='smart'?fmt(v,0):state.mmc==='si_chg'?(v==null?'—':(v>0?'+':'')+fmt(v,1)+'%'):mmPct(v,0);
  s+=`<g><rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${mmColor(v,met[2],met[3])}" stroke="var(--bg)" stroke-width=".6"><title>${esc(c[it])} · ${esc(c[inm])} · ${mmUSD(c[imc])} · ${esc(met[1])}: ${esc(val)}</title></rect>${w>34&&h>16?`<text x="${x+3}" y="${y+12}" fill="#fff" style="fill:#fff;font-size:${Math.max(8,Math.min(14,w/5))}px;font-weight:600">${esc(c[it])}</text>`:''}${w>40&&h>30?`<text x="${x+3}" y="${y+25}" style="fill:#fff;font-size:9px">${esc(val)}</text>`:''}</g>`});
 d.sectors.forEach(sec=>{const [x,y,w,h]=sec.rect;s+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="var(--ink)" stroke-width="1.2"/>${w>80&&h>30?`<text x="${x+3}" y="${y+11}" class="mm-small" style="font-weight:600">${esc(sec.label.toUpperCase())}${sec.chg!=null?' '+(sec.chg>0?'+':'')+fmt(sec.chg,1)+'%':''}</text>`:''}`});
 s+='</svg>';
 return `<div class="toolbar">${field('mmc','Colour by',M.map(x=>[x[0],x[1]]),state.mmc,true)}</div><div class="panel"><h3>Market map · ${esc(d.asof||'')} · ${fmt(d.cells.length)} largest stocks</h3>${s}<div class="mm-legend"><span style="--c:rgb(234,106,82)">${state.mmc==='si_chg'?'shorts up':'low / down'}</span><span style="--c:rgb(190,188,182)">neutral</span><span style="--c:rgb(23,115,74)">${state.mmc==='si_chg'?'shorts down':'high / up'}</span><span style="--c:#cfcdc7">no data</span></div></div><div class="explain">${esc(d.note||'')}</div>`;
}
function mmNetwork(){
 const m=mmData('network');if(m.err)return empty('The network could not load ('+m.err+').');if(!m.data)return empty('Loading the ownership network…');
 const d=m.data,W=980,H=620,N=d.nodes,mx=Math.max(...N.filter(n=>n.kind==='stock').map(n=>n.size),1),mm=Math.max(...N.filter(n=>n.kind==='manager').map(n=>n.size),1);
 const X=n=>30+n.x*(W-60),Y=n=>20+n.y*(H-40);
 let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ownership network of the watched 13F managers">`;
 d.edges.forEach(([i,j,w])=>{s+=`<line x1="${X(N[i])}" y1="${Y(N[i])}" x2="${X(N[j])}" y2="${Y(N[j])}" stroke="var(--muted)" stroke-opacity="${Math.min(.6,.08+w*3)}" stroke-width="${Math.min(4,.5+w*20)}"/>`});
 N.forEach(n=>{if(n.kind==='manager'){const r=5+10*Math.sqrt(n.size/mm);s+=`<rect x="${X(n)-r}" y="${Y(n)-r}" width="${2*r}" height="${2*r}" rx="3" fill="#345ca0"><title>${esc(n.label)} · ${mmUSD(n.size)}</title></rect><text x="${X(n)+r+3}" y="${Y(n)+4}" class="mm-small">${esc(n.label.split(' (')[0])}</text>`}
  else{const r=4+12*Math.sqrt(n.size/mx);s+=`<circle cx="${X(n)}" cy="${Y(n)}" r="${r}" fill="${mmColor((n.index-50)/50,'diverging',1)}" stroke="var(--bg)"><title>${esc(n.label)}: held by ${n.holders} · crowding ${fmt(n.index,0)} · ${mmUSD(n.size)}</title></circle>${n.holders>=4?`<text x="${X(n)}" y="${Y(n)+3}" text-anchor="middle" class="mm-small" style="font-weight:600">${esc(n.label)}</text>`:''}`}});
 s+='</svg>';
 const c=d.check||{},Q=c.quarters||[];
 return `<div class="panel"><h3>Watched 13F managers and the stocks they share (${fmt(d.managers)} managers)</h3><p class="sub">Squares: managers (size = portfolio). Circles: stocks at least two of them hold (size = their combined dollars, colour = crowding index, green = more crowded).</p>${s}</div>
 <div class="charts even"><div class="panel"><h3>Most crowded</h3>${table(['Stock','Holders','Crowding (0–100)','Summed weight','New holders'],(d.crowding||[]).slice(0,25).map(r=>[`<b>${esc(r.ticker)}</b>`,fmt(r.holders),fmt(r.index,0),mmPct(r.weight_sum,1),fmt(r.new_holders)]))}</div>
 <div class="panel"><h3>Walk-forward: crowded against single-holder names</h3><p class="sub">${Q.length?`Mean spread ${c.mean_spread>=0?'+':'−'}${fmt(Math.abs(c.mean_spread)*100,1)} pts over ${Q.length} quarters; crowded ahead in ${mmPct(c.hit_rate,0)} of them.`:'Not enough priced quarters yet.'}</p>${table(['Quarter','From','Crowded (n)','Single (n)','Spread'],Q.map(q=>[esc(q.period),esc(q.from),`${mmPct(q.crowded_ret,1)} (${q.crowded_n})`,`${mmPct(q.single_ret,1)} (${q.single_n})`,afMoneyPts(q.spread)]))}<p class="sub">${esc(c.note||'')}</p></div></div>
 <div class="explain">${esc(d.note||'')}</div>`;
}
const afMoneyPts=v=>v==null?'—':`<span class="${v>0?'positive':'negative'}">${v>0?'+':'−'}${fmt(Math.abs(v)*100,1)} pts</span>`;
function mmStack(labels,series,colors,fmtV){
 const W=980,H=360,L=70,B=46,T=14,tot=labels.map((_,i)=>series.reduce((a,s)=>a+(s.v[i]||0),0)),hi=Math.max(...tot,1),bw=(W-L-10)/labels.length;
 let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Stacked bars">`;
 for(let k=0;k<=4;k++){const v=hi*k/4,y=H-B-(H-B-T)*k/4;s+=`<line class="gridline" x1="${L}" x2="${W}" y1="${y}" y2="${y}"/><text x="${L-6}" y="${y+4}" text-anchor="end" class="mm-small">${esc(fmtV(v))}</text>`}
 labels.forEach((lab,i)=>{let y=H-B;series.forEach((sr,j)=>{const v=sr.v[i]||0,h=(H-B-T)*v/hi;if(h>0){s+=`<rect x="${L+i*bw+3}" y="${y-h}" width="${bw-6}" height="${h}" fill="${colors[j]}"><title>${esc(lab)} · ${esc(sr.name)}: ${esc(fmtV(v))}</title></rect>`;y-=h}});
  s+=`<text x="${L+i*bw+bw/2}" y="${H-B+14}" text-anchor="middle" class="mm-small">${esc(lab.replace(' (incl. past due)','*'))}</text><text x="${L+i*bw+bw/2}" y="${H-B-(H-B-T)*tot[i]/hi-4}" text-anchor="middle" class="mm-small">${esc(fmtV(tot[i]))}</text>`});
 return s+'</svg>';
}
function mmMaturity(){
 const m=mmData('maturity');if(m.err)return empty('The maturity wall could not load ('+m.err+').');if(!m.data)return empty('Loading the maturity wall…');
 const d=m.data,cols=['#17734a','#3f8f63','#6aa97f','#9cc3a6','#e0b26a','#e08a5a','#c0473a','#9a9893'];
 let out=`<div class="metrics">${kpi('Companies read',fmt(d.companies),'debt instruments from 10-K / 10-Q')}${kpi('Due in '+(d.asof_year+1),mmUSD(d.totals[1]),'face, else carrying value')}${kpi('Due in '+(d.asof_year+2),mmUSD(d.totals[2]),'')}${kpi('BB or lower, '+(d.asof_year+1),mmUSD(['BB','B','CCC'].reduce((a,b)=>a+((d.wall[b]||[])[1]||0),0)),'by the issuer’s rating band')}</div>`;
 out+=`<div class="panel"><h3>The maturity wall, by rating band</h3>${mmStack(d.labels,d.bands.map(b=>({name:b,v:d.wall[b]||[]})),cols,mmUSD)}<div class="mm-legend">${d.bands.map((b,i)=>`<span style="--c:${cols[i]}">${b}</span>`).join('')}</div></div>`;
 const q=(state.mmt||'').toUpperCase().replace(/\./g,'-'),co=q&&d.by_company?d.by_company[q]:null;
 out+=`<div class="toolbar"><div class="field"><label for="mmt">A company's own wall (ticker)</label><input id="mmt" value="${esc(state.mmt||'')}" placeholder="e.g. F"></div></div>`;
 if(q)out+=co?`<div class="panel"><h3>${esc(co.name||q)} · ${esc(co.band)}</h3>${mmStack(co.wall.map(w=>String(w[0])),[{name:q,v:co.wall.map(w=>w[1])}],['#345ca0'],mmUSD)}</div>`:empty('No debt instruments read for '+q+' yet.');
 out+=`<div class="panel"><h3>Largest maturities in ${d.asof_year+1}</h3>${table(['Company','Band','Due'],(d.next_year_top||[]).map(r=>[`<b>${esc(r.ticker)}</b> <span class="muted">${esc(r.name||'')}</span>`,esc(r.band),mmUSD(r.usd)]))}</div>`;
 return out+`<div class="explain">${esc(d.note||'')}</div>`;
}
function mmSpark(series,W=240,H=46){
 const v=(series||[]).map(x=>x[1]).filter(x=>x!=null);if(v.length<2)return '';
 const lo=Math.min(...v),hi=Math.max(...v),pts=v.map((y,i)=>`${(i/(v.length-1)*W).toFixed(1)},${(H-2-(y-lo)/((hi-lo)||1)*(H-4)).toFixed(1)}`).join(' ');
 return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px"><polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.6"/></svg>`;
}
function mmThermo(){
 const m=mmData('thermometer');if(m.err)return empty('The thermometer could not load ('+m.err+').');if(!m.data)return empty('Loading the gauges…');
 const G=m.data.gauges||{},show=(k,g)=>{const v=g.unit==='%'?mmPct(g.value,2):g.unit==='x'?fmt(g.value,2)+'x':fmt(g.value,1);const f=g.fit;
  return `<div class="mm-gauge"><label class="muted">${esc(g.label)}</label><strong>${esc(v)}</strong><div class="mm-bar" title="percentile against its own history"><i style="left:calc(${(g.percentile||0)*100}% - 1px)"></i></div>
   <small>${g.percentile!=null?mmPct(g.percentile,0)+' percentile':''} · history since ${esc((g.history_from||'').slice(0,7))} (${fmt(g.history_n)} points) · median ${esc(g.unit==='%'?mmPct(g.median,2):fmt(g.median,2))}${g.asof?' · as of '+esc(g.asof):''}</small>${mmSpark(g.series)}
   ${f?`<p class="sub">Next ten years' real return, fitted from similar levels: <b>${mmPct(f.next10y_real,1)}</b> a year (80% range ${mmPct(f.lo80,1)} to ${mmPct(f.hi80,1)}; r² ${fmt(f.r2,2)}, ${fmt(f.n)} months).</p>`:''}<p class="sub">${esc(g.note||'')}</p></div>`};
 return `<div class="mm-gauges">${['buffett','cape','ecy','fwd_pe'].filter(k=>G[k]).map(k=>show(k,G[k])).join('')||empty('No gauges yet.')}</div><div class="explain">${esc(m.data.note||'')}</div>`;
}
function mmLiquidity(){
 const m=mmData('liquidity');if(m.err)return empty('The liquidity series could not load ('+m.err+').');if(!m.data)return empty('Loading net liquidity…');
 const d=m.data,L=d.latest||{},F=d.fields,rows=d.rows.map(r=>Object.fromEntries(F.map((k,i)=>[k,r[i]])));
 const b=v=>v==null?'—':(v<0?'−':'')+'$'+fmt(Math.abs(v)/1000,2)+'T',sb=v=>v==null?'—':(v>0?'+':v<0?'−':'')+'$'+fmt(Math.abs(v),0)+'B';
 const W=980,H=320,Lm=64,R=64,T=14,B=30,n=rows.length,x=i=>Lm+i/(n-1)*(W-Lm-R);
 const nv=rows.map(r=>r.net),sv=rows.map(r=>r.spx).filter(v=>v!=null),nlo=Math.min(...nv),nhi=Math.max(...nv),slo=Math.min(...sv),shi=Math.max(...sv);
 const yN=v=>T+(nhi-v)/((nhi-nlo)||1)*(H-T-B),yS=v=>T+(shi-v)/((shi-slo)||1)*(H-T-B);
 let s=`<svg class="mm-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Net liquidity and the S&P 500">`;
 for(let k=0;k<=4;k++){const v=nlo+(nhi-nlo)*k/4;s+=`<line class="gridline" x1="${Lm}" x2="${W-R}" y1="${yN(v)}" y2="${yN(v)}"/><text x="${Lm-6}" y="${yN(v)+4}" text-anchor="end" class="mm-small">${esc(b(v))}</text>`}
 s+=`<polyline points="${rows.map((r,i)=>`${x(i).toFixed(1)},${yN(r.net).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
 if(sv.length)s+=`<polyline points="${rows.map((r,i)=>r.spx==null?'':`${x(i).toFixed(1)},${yS(r.spx).toFixed(1)}`).filter(Boolean).join(' ')}" fill="none" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="4 3"/><text x="${W-R+4}" y="${yS(sv[sv.length-1])+4}" class="mm-small mm-muted">S&amp;P 500</text>`;
 [0,Math.floor(n/2),n-1].forEach(i=>{s+=`<text x="${x(i)}" y="${H-10}" text-anchor="middle" class="mm-small">${esc(rows[i].week)}</text>`});
 s+='</svg>';
 return `<div class="metrics">${kpi('Net liquidity',b(L.net),'week of '+(L.week||'—'))}${kpi('1 week',sb(L.chg_1w),'4 weeks '+sb(L.chg_4w))}${kpi('13 weeks',sb(L.chg_13w),'52 weeks '+sb(L.chg_52w))}${kpi('High-yield spread',L.hy_spread==null?'—':fmt(L.hy_spread,2)+'%',L.hy_chg_4w==null?'':(L.hy_chg_4w>0?'+':'')+fmt(L.hy_chg_4w,2)+' in 4 weeks')}${kpi('10y − 2y',L.curve==null?'—':(L.curve>0?'+':'')+fmt(L.curve,2),'Treasury curve, pts')}</div>
 <div class="panel"><h3>Net liquidity (Fed balance sheet − TGA − reverse repo) and the S&amp;P 500</h3>${s}<p class="sub">Fed ${b(L.fed)} − TGA ${b(L.tga)} − reverse repo ${b(L.rrp)}.${d.corr_13w_spx!=null?` Correlation of 13-week changes with the S&amp;P 500 since 2015: ${fmt(d.corr_13w_spx,2)}.`:''}</p></div><div class="explain">${esc(d.note||'')}</div>`;
}
function mapsView(){
 mmCSS();state.mmv=MM_VIEWS.some(v=>v[0]===state.mmv)?state.mmv:'flows';
 const st=mmData('status');
 let out=head('Market maps','Where the disclosed money moved, the best-known 13F portfolios, the market as a heatmap, crowding, the debt maturity wall, valuation and liquidity gauges.','RESEARCH / DAILY');
 out+=`<div class="toolbar">${field('mmv','View',MM_VIEWS,state.mmv,true)}</div>`;
 if(st.data&&st.data.built_at)out+=`<p class="sub">Built ${esc(st.data.built_at)} (app/market_maps.py).</p>`;
 out+=({flows:mmFlows,manager:mmManager,race:mmRace,heatmap:mmHeatmap,network:mmNetwork,maturity:mmMaturity,thermo:mmThermo,liquidity:mmLiquidity}[state.mmv])();
 return out;
}
let mmTimer=null;
function bindMaps(){
 if(state.tab!=='maps')return;
 [['mmv','mmv'],['mmp','mmp'],['mmside','mmside'],['mmm','mmm'],['mmr','mmr'],['mmc','mmc']].forEach(([id,k])=>{if($(id))$(id).onchange=e=>{state[k]=e.target.value;if(k==='mmr')state.mmq=null;render()}});
 if($('mmq'))$('mmq').oninput=e=>{state.mmq=+e.target.value;render()};
 if($('mmt'))$('mmt').onchange=e=>{state.mmt=e.target.value.trim();render()};
 if($('mmplay'))$('mmplay').onclick=()=>{clearInterval(mmTimer);const max=+$('mmq').max;state.mmq=0;render();mmTimer=setInterval(()=>{if(state.tab!=='maps'||state.mmv!=='race'||state.mmq>=max){clearInterval(mmTimer);return}state.mmq++;render()},900)};
}
