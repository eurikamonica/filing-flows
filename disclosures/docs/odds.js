/* Odds — the hub tab: probability models, each with its record. The market (the chance of a US recession 12 months out
   from the yield curve, the stressed-regime probability of a two-state model of SPY), the leaders (likeliest S&P 500
   additions, dividend cuts, 20% falls and rises, lowest distance to default), one company (odds-view.js, shared with the
   company pages) and the track record: every model's walk-forward calibration and its live record from the frozen weekly
   odds. Data: data/market/history/odds.json and odds-stocks.json (rotation-history; app/odds.py).
   Deep links: #odds, #odds/leaders, #odds/record, #odds/NVDA. */
const odStore={};
function odData(name){
 const m=odStore[name]||(odStore[name]={});
 if(m.data||m.err||m.loading)return m;
 m.loading=fetch('data/market/history/'+name,{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const OD_VIEWS=[['market','Market'],['leaders','Leaders'],['one','One company'],['record','Track record']];
const OD_NAMES={recession:'US recession 12 months out (yield curve)',down13:'SPY lower in 13 weeks (regime model)',dn10_4:'Falls 10% within 4 weeks',up10_4:'Rises 10% within 4 weeks',dn20_13:'Falls 20% within 13 weeks',up20_13:'Rises 20% within 13 weeks',
 beat13:'Beats SPY over 13 weeks',beat52:'Beats SPY over 52 weeks',sp500_12m:'Added to the S&P 500 within a year',divcut_12m:'Cuts or skips its dividend within a year',merton_1y:'Default within a year (Merton)'};
function odP(v,d){return v==null?'—':(v>0&&v<0.001?'<0.1%':fmt(v*100,d==null?(v<0.1?1:0):d)+'%')}
function odRec(c){if(!c)return '—';return `AUC ${c.auc==null?'—':fmt(c.auc,2)} · skill ${c.skill==null?'—':(c.skill>=0?'+':'−')+fmt(Math.abs(c.skill*100),1)+'%'} · ${fmt(c.n)} cases`}

/* a line of probabilities over time, with shaded spans (recessions) */
function odLine(pts,opt={}){
 if(!pts||pts.length<2)return '';
 const W=opt.w||860,H=opt.h||170,L=40,R=8,T=10,B=22,n=pts.length;
 const X=k=>L+k/(n-1)*(W-L-R),Y=v=>T+(1-v)*(H-T-B);
 let g='';
 [0,0.25,0.5,0.75,1].forEach(v=>g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line)"/><text x="${L-5}" y="${(Y(v)+4).toFixed(1)}" font-size="10" text-anchor="end" fill="var(--muted)">${v*100}%</text>`);
 (opt.spans||[]).forEach(([a,b])=>{const i=pts.findIndex(p=>p[0]>=a),j=pts.findIndex(p=>p[0]>b);if(i<0)return;const jj=j<0?n-1:j;g+=`<rect x="${X(i).toFixed(1)}" y="${T}" width="${Math.max(2,X(jj)-X(i)).toFixed(1)}" height="${H-T-B}" fill="var(--neg-soft)" opacity=".8"><title>recession ${esc(a)} – ${esc(b)}</title></rect>`});
 const step=Math.max(1,Math.ceil(n/700));let d='';for(let k=0;k<n;k+=step)d+=(d?'L':'M')+X(k).toFixed(1)+','+Y(pts[k][1]).toFixed(1);d+='L'+X(n-1).toFixed(1)+','+Y(pts[n-1][1]).toFixed(1);
 g+=`<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="1.6"/>`;
 const y0=+String(pts[0][0]).slice(0,4),y1=+String(pts[n-1][0]).slice(0,4),ys=Math.max(1,Math.ceil((y1-y0)/9));
 for(let y=y0+1;y<=y1;y+=ys){const k=pts.findIndex(p=>+String(p[0]).slice(0,4)>=y);if(k>0)g+=`<text x="${X(k).toFixed(1)}" y="${H-6}" font-size="10" text-anchor="middle" fill="var(--muted)">${y}</text>`}
 return `<div style="overflow-x:auto"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:480px;height:auto" role="img" aria-label="${esc(opt.label||'Probability over time')}">${g}</svg></div>`;
}
/* calibration: predicted (x) against observed (y), one dot per bin sized by its cases, the diagonal is perfect */
function odCalib(c,opt={}){
 if(!c||!c.calib||!c.calib.length)return '<p class="muted">No record yet.</p>';
 const S=opt.s||200,P=26,mx=Math.min(1,Math.max(0.05,...c.calib.map(b=>Math.max(b[0],b[1])))*1.1),X=v=>P+v/mx*(S-P-8),Y=v=>S-P-v/mx*(S-P-8),nmax=Math.max(...c.calib.map(b=>b[2]));
 let g=`<line x1="${X(0)}" y1="${Y(0)}" x2="${X(mx)}" y2="${Y(mx)}" stroke="var(--line)" stroke-dasharray="4 3"/><line x1="${P}" x2="${S-8}" y1="${S-P}" y2="${S-P}" stroke="var(--muted)"/><line x1="${P}" x2="${P}" y1="8" y2="${S-P}" stroke="var(--muted)"/>`;
 g+=`<text x="${(S+P)/2}" y="${S-6}" font-size="9" text-anchor="middle" fill="var(--muted)">predicted (to ${fmt(mx*100,0)}%)</text><text x="9" y="${(S-P)/2}" font-size="9" text-anchor="middle" fill="var(--muted)" transform="rotate(-90 9 ${(S-P)/2})">observed</text>`;
 c.calib.forEach(b=>{g+=`<circle cx="${X(b[0]).toFixed(1)}" cy="${Y(b[1]).toFixed(1)}" r="${(2.5+5*Math.sqrt(b[2]/nmax)).toFixed(1)}" fill="var(--accent)" fill-opacity=".7"><title>predicted ${odP(b[0])} · observed ${odP(b[1])} · ${fmt(b[2])} cases</title></circle>`});
 return `<svg viewBox="0 0 ${S} ${S}" style="width:${S}px;max-width:100%;height:auto" role="img" aria-label="Calibration: predicted against observed">${g}</svg>`;
}
function odMarket(d){
 const R=d.market.recession,G=d.market.regime,spy=d.market.spy;
 let out='';
 if(R){out+=`<div class="section-head"><h3>US recession, 12 months out</h3><span class="muted">the New York Fed's yield-curve model</span></div>`;
  out+=`<div class="metrics">${kpi('Chance of recession in '+R.for_month,odP(R.p),'from the '+R.month+' 10-year less 3-month spread, '+(R.spread>=0?'+':'−')+fmt(Math.abs(R.spread),2)+' pts')}${kpi('Sahm rule',R.sahm==null?'—':fmt(R.sahm,2)+' pts','unemployment above its 12-month low; 0.50 has marked every recession since 1970')}${kpi('Record since 1990',R.card?'AUC '+fmt(R.card.auc,2):'—',R.card?'skill '+(R.card.skill>=0?'+':'−')+fmt(Math.abs(R.card.skill*100),0)+'% against the base rate, '+R.card.n+' months':'')}${kpi('Since 2006 (out of sample)',R.card_oos?'AUC '+fmt(R.card_oos.auc,2):'—',R.card_oos?'skill '+(R.card_oos.skill>=0?'+':'−')+fmt(Math.abs(R.card_oos.skill*100),0)+'%':'')}</div>`;
  const spans=[['1990-08','1991-03'],['2001-04','2001-11'],['2008-01','2009-06'],['2020-03','2020-04']];
  out+=odLine(R.history.map(h=>[h[0],h[1]]),{spans,label:'Recession probability by month'});
  out+=`<p class="muted" style="font-size:.8rem;max-width:900px">P = Φ(${R.coef[0]} ${R.coef[1]} × spread), the month's average 10-year less 3-month yield; coefficients estimated on 1959–2005 by Estrella and Trubin, so every month since 2006 is out of sample. Shaded: NBER recessions. Scored against the NBER months through ${esc(R.scored_to)} (12 months ahead, and NBER dates recessions about a year late). The inverted curve of 2022–24 gave high odds and no recession followed — that is in the record.</p>`}
 if(G){out+=`<div class="section-head"><h3>Market regime</h3><span class="muted">a two-state model of SPY's weekly returns</span></div>`;
  out+=`<div class="metrics">${kpi('Stressed regime now',odP(G.p_stress),'week ending '+G.week)}${kpi('SPY lower in 13 weeks',odP(G.p_down13),'from the regimes and their switching odds')}${kpi('Calm regime',fmt(G.states.calm.vol_a_year*100,0)+'% volatility',(G.states.calm.mean_a_year>=0?'+':'−')+fmt(Math.abs(G.states.calm.mean_a_year*100),0)+'% a year on average · stays '+fmt(G.states.calm.stay*100,0)+'% of weeks')}${kpi('Stressed regime',fmt(G.states.stressed.vol_a_year*100,0)+'% volatility',(G.states.stressed.mean_a_year>=0?'+':'−')+fmt(Math.abs(G.states.stressed.mean_a_year*100),0)+'% a year on average · stays '+fmt(G.states.stressed.stay*100,0)+'%')}</div>`;
  out+=odLine(G.history.map(h=>[h[0],h[1]]),{label:'Probability of the stressed regime by week'});
  out+=`<p class="muted" style="font-size:.8rem;max-width:900px">Refitted each year on the years before it (Hamilton 1989; two normal distributions and the chance of switching), read week by week from the closes to date only. The regime it finds is real — volatility clusters — but its forecast of SPY's direction has been ${G.card&&G.card.auc<0.53?'no better than a coin flip':'modest'}: ${esc(odRec(G.card))}.</p>`}
 if(spy){out+=`<div class="section-head"><h3>SPY's own odds</h3></div>`+table(['Move','Probability'],[['Falls 10% within 4 weeks',odP(spy.dn10_4)],['Rises 10% within 4 weeks',odP(spy.up10_4)],['Falls 20% within 13 weeks',odP(spy.dn20_13)],['Rises 20% within 13 weeks',odP(spy.up20_13)]])+`<p class="muted" style="font-size:.8rem">From SPY's own volatility (${odP(spy.vol,0)} a year) on weekly closes, recalibrated on the stocks' record; quiet markets give tiny odds, and quiet markets are when shocks surprise.</p>`}
 return out;
}
function odLeaders(d){
 const L=d.leaders||{},sec=(k,title,note)=>{const r=(L[k]||[]).slice(0,15),mx=Math.max(...r.map(x=>x[1]),0.01);
  return `<div class="tablebox" style="padding:10px 12px"><h4 style="margin:0 0 6px">${esc(title)}</h4>`+(r.length?r.map(([t,p])=>`<div style="display:grid;grid-template-columns:70px 1fr 52px;gap:8px;align-items:center;padding:3px 0;border-bottom:1px solid var(--line)"><button class="text-button" style="text-align:left" data-odco="${esc(t)}"><b>${esc(t)}</b></button><span style="height:8px;border-radius:4px;background:var(--accent);opacity:.75;width:${Math.max(2,Math.round(p/mx*100))}%"></span><span class="mono" style="text-align:right">${odP(p)}</span></div>`).join(''):empty('None yet.'))+`<p class="muted" style="font-size:.76rem;margin:6px 0 0">${esc(note)}</p></div>`};
 let out=`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px">`;
 out+=sec('sp500_12m','Likeliest S&P 500 additions (12 months)','Not in the index now. Foreign private issuers and partnerships are left out; the index committee also weighs domicile, float and sector balance, which the model does not see.');
 out+=sec('divcut_12m','Likeliest dividend cuts or skips (12 months)','Dividend payers now; a cut is a regular payment under 85% of the one before, or none by 1.5 times the usual interval plus 8 weeks.');
 out+=sec('dn20_13','Likeliest 20% falls (13 weeks)','On weekly closes; mostly the most volatile stocks.');
 out+=sec('up20_13','Likeliest 20% rises (13 weeks)','Volatility cuts both ways: these are largely the same names.');
 out+=sec('merton_1y','Highest default odds (Merton)','From Debt & rates\' distance to default (risk-neutral; readings below −0.5, which a positive share price contradicts, are left out).');
 return out+'</div>';
}
function odRecord(d){
 const M=d.models||{},live=(d.live&&d.live.cards)||{};
 let out=`<p class="muted" style="max-width:900px">Every model is judged on years it had not seen: each year predicted only from the years before it. <b>Calibration</b>: when it says 30%, does it happen about 30% of the time (dots on the dashed diagonal)? <b>AUC</b>: how well it ranks — 0.5 a coin flip, 1 perfect. <b>Skill</b>: how much its Brier score beats always saying the base rate the past years implied (0 = no better). The <b>live</b> record scores the odds frozen each week since ${esc((d.live&&d.live.since)||'—')}. ${esc(d.survivorship)}</p>`;
 const items=[['recession',d.market.recession&&d.market.recession.card,null],['down13',d.market.regime&&d.market.regime.card,live.down13],...Object.keys(M).map(k=>[k,M[k].card,live[k]])];
 out+=`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px">`+items.map(([k,c,lv])=>`<div class="tablebox" style="padding:10px 12px"><h4 style="margin:0 0 4px">${esc(OD_NAMES[k]||k)}</h4>${odCalib(c)}<p class="muted" style="font-size:.78rem;margin:4px 0">${esc(odRec(c))}${c?' · base rate '+odP(c.base):''}</p>${lv?`<p style="font-size:.78rem;margin:2px 0"><b>Live:</b> ${esc(odRec(lv))}</p>`:''}${M[k]&&M[k].features?`<p class="muted" style="font-size:.74rem;margin:2px 0">Inputs: ${esc(M[k].features.join(' · '))}</p>`:''}</div>`).join('')+'</div>';
 return out;
}
function oddsView(){
 state.odv=OD_VIEWS.some(v=>v[0]===state.odv)?state.odv:'market';
 let out=head('Odds','Probability models, each with its record: a US recession 12 months out from the yield curve, the market\'s regime, every stock\'s chance of a 10% or 20% move, of beating SPY, of joining the S&P 500 and of cutting its dividend, and Merton\'s default odds — each judged on years it had not seen and frozen weekly for a live record.','PROBABILITIES · CALIBRATED · LIVE');
 out+=`<div class="toolbar">${field('odv','View',OD_VIEWS,state.odv)}`;
 if(state.odv==='one')out+=`<div class="field wide"><label for="odt">Ticker</label><input id="odt" value="${esc(state.odt||'')}" placeholder="e.g. NVDA · Enter"></div>`;
 out+='</div>';
 if(state.odv==='one'){const t=String(state.odt||'').trim().toUpperCase().replace(/\./g,'-');return out+(t?`<div id="od-one" data-t="${esc(t)}"></div>`:empty('Type a ticker to see its odds.'))}
 const g=odData('odds.json');
 if(g.err)return out+empty(`The odds could not load (${g.err}). They are rebuilt by .github/workflows/rotation-history.yml (app/odds.py).`);
 if(!g.data)return out+empty('Loading the odds…');
 if(state.odv==='leaders')return out+odLeaders(g.data);
 if(state.odv==='record')return out+odRecord(g.data);
 return out+odMarket(g.data);
}
function bindOdds(){
 if(state.tab!=='odds')return;
 if($('odv'))$('odv').onchange=e=>{state.odv=e.target.value;render()};
 if($('odt')){$('odt').onchange=e=>{state.odt=e.target.value;render()};$('odt').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 document.querySelectorAll('#workspace [data-odco]').forEach(b=>b.onclick=()=>{state.odv='one';state.odt=b.dataset.odco;render();scrollTo({top:0,behavior:'smooth'})});
 const one=$('od-one');
 if(one&&window.OddsView&&one.dataset.drawn!==one.dataset.t){one.dataset.drawn=one.dataset.t;OddsView.render(one,{ticker:one.dataset.t,hub:''})}
}
function oddsDeepLink(arg){
 const v=decodeURIComponent(arg||'').trim();if(!v)return;
 if(OD_VIEWS.some(x=>x[0]===v)){state.odv=v;return}
 state.odv='one';state.odt=v.toUpperCase();
}
function oddsNotice(){
 const s=odData('odds.json'),d=s.data;
 if(s.err)return {stale:true,text:'Official derived view · Odds unavailable · '+s.err};
 if(!d)return {stale:false,text:'Official derived view · Odds loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=30),text:`Official derived view · Odds built ${d.generated_at} · ${fmt(d.counts.stocks)} stocks · week ending ${d.asof} · rebuilt with the weekly closes every three hours`+(age>30?' · stale':'')};
}
window.oddsDeepLink=oddsDeepLink;
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{odds:oddsNotice});
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{odds:oddsView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{odds:bindOdds});
if(typeof module!=='undefined')module.exports={odMarket,odLeaders,odRecord,odLine,odCalib};
