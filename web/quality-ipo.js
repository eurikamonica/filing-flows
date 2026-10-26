/* Transparent company quality and public prospectus analysis. */
(function(root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const amount = (v,unit='USD') => finite(v) ? unit+' '+Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(v) : 'Not available';
  function source(url) { try { const u=new URL(url); return u.protocol==='https:' && u.hostname==='www.sec.gov' && !u.username && !u.password ? u.href : ''; } catch (_) { return ''; } }
  function metricTable(metrics) {
    const available=metrics.filter(m=>finite(m.value)).length;
    return `<p class="muted">${available}/${metrics.length} measures available. Missing data is not zero. These are diagnostic measures, not an investment rating or an industry-adjusted score.</p><div class="qi-table"><table><thead><tr><th>Measure</th><th>Value</th><th>Formula / interpretation</th></tr></thead><tbody>${metrics.map(m=>`<tr><td>${esc(m.label)}</td><td>${finite(m.value) ? esc(m.format==='multiple' ? m.value.toFixed(2)+'×' : (m.value*100).toFixed(2)+'%') : 'Not available'}</td><td>${esc(m.formula)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function quality(body,c) {
    const d=c.quality||{}, periods=[...(d.fy||[]).map(p=>({...p,mode:'FY'})),...(d.q||[]).map(p=>({...p,mode:'Quarter'}))].filter(p=>p.health);
    if(!periods.length) return;
    const section=document.createElement('section'); section.className='section qi-section'; body.appendChild(section);
    section.innerHTML='<h2>Company quality measures</h2><p>Profitability, cash conversion, reinvestment and liquidity — with explicit formulas and filing evidence.</p><label>Reporting period <select aria-label="Quality reporting period"></select></label><div class="qi-result"></div>';
    const select=section.querySelector('select'); periods.forEach((p,i)=>select.add(new Option(`${p.mode} · ${p.label} · ${p.end}`,i)));
    select.value=String(periods.length-1);
    const draw=()=>{
      const p=periods[Number(select.value)], h=p.health, src=d.src||{}, financial=c.profile?.sector==='financials'||/^6[0-7]/.test(String(c.profile?.sic||''));
      section.querySelector('.qi-result').innerHTML=`${financial?'<p class="qi-notice">Financial-sector company: lending, deposit and trading flows make cash-flow ratios difficult to compare with industrial companies. No quality score is assigned.</p>':''}${metricTable(h.metrics||[])}<details><summary>Inputs & SEC evidence</summary>${Object.entries(h.inputs||{}).map(([k,v])=>{
        const ref=h.ev?.[k], concept=ref ? src.concepts?.[ref[0]]?.[0] : null;
        const links=(ref?.[2]||[]).map(i=>{const f=src.filings?.[i]; if(!f||!/^\d{10}-\d{2}-\d{6}$/.test(f[0])||!/^\d+$/.test(String(c.cik)))return ''; const u=`https://www.sec.gov/Archives/edgar/data/${Number(c.cik)}/${f[0].replaceAll('-','')}/${f[0]}-index.html`;return `<a href="${u}" target="_blank" rel="noopener noreferrer">${esc(f[1])} · ${esc(f[2])}</a>`;}).join(' · ');
        return `<p><strong>${esc(k)}</strong>: ${esc(amount(v,d.unit||'USD'))} · ${esc(concept||'No source fact')} ${links}</p>`;
      }).join('')}</details>`;
    };select.onchange=draw;draw();
  }
  // Signed accounting equation sum(terms) = result. Loss sources are balancing amounts, never cash funding.
  function flow(title,terms,result,resultLabel,period) {
    if(!finite(result)||terms.some(t=>!finite(t[1]))) return null;
    const sum=terms.reduce((s,t)=>s+t[1],0), residual=result-sum;
    if(Math.abs(residual)>Math.max(1,Math.abs(result),...terms.map(t=>Math.abs(t[1])))*0.000001) return null;
    const sources=terms.filter(t=>t[1]>0), uses=terms.filter(t=>t[1]<0).map(t=>[t[0]+' (−)',-t[1],t[2]]);
    if(result<0)sources.push([resultLabel+' · balancing loss / decrease',-result,'cost']);
    if(result>0)uses.push([resultLabel,result,'profit']);
    // Rounding reconciliation is explicit, never attributed to an undisclosed cost.
    if(residual>0)sources.push(['Rounding reconciliation',residual,'noncash']);
    if(residual<0)uses.push(['Rounding reconciliation',-residual,'noncash']);
    const total=sources.reduce((s,t)=>s+t[1],0); if(!(total>0))return null;
    const nodes=[],links=[], unit=period.unit||'USD';
    const node=(id,col,name,v,color)=>nodes.push({id,col,name,v,color,pos:col===0?'left':col===2?'right':'above',lines:[['name',name],['val',amount(v,unit)]]});
    node('pool',1,'Accounting reconciliation',total,'rev');
    sources.forEach(([label,v,color],i)=>{node('s'+i,0,label,v,color||'profit');links.push({s:'s'+i,t:'pool',v,color:color||'profit'});});
    uses.forEach(([label,v,color],i)=>{node('u'+i,2,label,v,color||'cost');links.push({s:'pool',t:'u'+i,v,color:color||'cost'});});
    return {title,subtitle:`${period.company ? period.company+' · ' : ''}${period.label} · ${unit} · ${period.start} to ${period.end}`,nodes,links,
      footer:['Positive-width flows reconcile the stated accounting equation. A balancing loss is not a source of cash.','Negative terms are marked (−). Noncash adjustments are not cash receipts.'],
      ...(period.source_url ? {footer:['Positive-width flows reconcile the stated equation; a balancing loss is not cash funding.', 'Negative terms are marked (−). Noncash adjustments are not cash receipts.', 'SEC '+(period.accession||'')+' · '+period.source_url]} : {}),
      legend:[['profit','Income / cash inflows'],['cost','Expenses / cash outflows / balancing loss'],['noncash','Adjustments']]};
  }
  function charts(p) {
    const v=p.values, op=[['Revenue',v.revenue,'rev'],['Compute & infrastructure',-v.compute],['Personnel',-v.personnel],['Settlement',-v.settlement],['Sales, marketing & partnerships',-v.selling],['Other operating costs',-v.other_operating]];
    const cashKeys=[['sbc','Stock compensation'],['da','Depreciation & amortization'],['fair_value_addback','Financing fair-value addback'],['donation','Donation liability'],['other_instruments','Other financial instruments'],['other_adjustments','Other adjustments'],['receivables','Receivables'],['prepaid','Prepaid / other assets'],['payables','Payables / accruals'],['lease_change','Lease liabilities'],['deferred_revenue','Deferred revenue']];
    const result = [
      flow('Revenue and operating expenses',op,v.oi,'Operating result',p),
      flow('Operating result to net income',[['Operating result',v.oi],['Interest income',v.interest_income],['Financing fair-value change',v.fair_value,'noncash'],['Other income / expense',v.other_income],['Income tax',-v.tax]],v.ni,'Net result',p),
      flow('Net income to operating cash',[['Net income',v.ni],...cashKeys.map(([k,l])=>[l,v[k],'noncash'])],v.ocf,'Operating cash flow',p),
      flow('Operating, investing and financing cash',[['Operating cash',v.ocf],['Investing cash',v.icf],['Financing cash',v.financing],['Exchange-rate effect',v.fx]],v.cash_change,'Change in cash incl. restricted cash',p)
    ].filter(Boolean);
    if (!result.length && finite(v.revenue) && finite(v.oi) && v.revenue-v.oi >= 0) {
      const spec=flow('Revenue and total operating costs', [['Revenue',v.revenue,'rev'],['Total operating costs · revenue less operating result',-(v.revenue-v.oi)]],v.oi,'Operating result',p);
      if(spec) result.push(spec);
    }
    if (!finite(v.compute) && finite(v.ocf) && finite(v.capex) && v.capex>=0) {
      const cf=flow('Operating cash to free cash flow',[['Operating cash flow',v.ocf],['Cash capital expenditure',-v.capex]],v.ocf-v.capex,'Free cash flow',p);if(cf)result.push(cf);
    }
    return result;
  }
  async function ipo(app,here=()=>true,cik,accession) {
    app.innerHTML='<p role="status">Loading IPO filings…</p>';
    try {
      const path=accession?`filings/${accession}.json`:cik?`${cik}.json`:'index.json';if(cik&&!/^\d+$/.test(String(cik)))throw Error('Invalid CIK');
      let d;if(root.FFIPOMarket)d=await root.FFIPOMarket.load(path);else{const response=await fetch('data/ipo/'+path,{cache:'no-cache'});if(!response.ok)throw Error('No IPO snapshot published');d=await response.json();}if(!here())return;
      if(!cik&&root.FFIPOMarket)return root.FFIPOMarket.index(app,d,here);
      if(!cik){app.innerHTML=`<section class="section qi-section"><h1>IPO & prospectus analysis</h1><p>S-1, F-1, amendments and final prospectuses. Reviewed watchlist; coverage is not the full IPO market.</p>${(d.companies||[]).map(c=>`<article class="qi-card"><h2><a href="#ipo-${Number(c.cik)}">${esc(c.name)}</a></h2><p>${esc(c.form)} · Filed ${esc(c.filed)}</p><p>Operating costs · net income reconciliation · cash flow · quality measures</p></article>`).join('')||'<p>No reviewed filings available.</p>'}</section>`;return;}
      if(String(d.cik)!==String(cik))throw Error('Company mismatch');
      const u=source(d.source_url);
      app.innerHTML=`<section class="section qi-section"><a href="#ipo">← IPO market monitor</a><h1>${esc(d.name)} · IPO analysis</h1><p>${esc(d.form)} · Filed ${esc(d.filed)} · ${u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">SEC prospectus</a>`:''}</p><p class="muted">${esc(d.accession)} · ${esc(d.method)}<br>Latest attempt: ${esc(d.scan?.last_attempt||'Not run')} · Latest success: ${esc(d.scan?.last_success||'Not run')} · Status: ${esc(d.scan?.state||'bundled_snapshot')}</p>${d.scan?.state==='failed'?'<p class="qi-notice">The latest refresh failed. Showing the last successfully parsed filing; this may not be the latest amendment.</p>':''}${root.FFIPOMarket?root.FFIPOMarket.detail(d):''}<label>Period <select id="ipo-period" aria-label="IPO reporting period"></select></label><div id="ipo-body"></div><h2>Coverage limits</h2><ul>${(d.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>`;
      const select=app.querySelector('#ipo-period');
      if(root.FFIPOMarket){app.querySelector('.qi-section').insertAdjacentHTML('beforeend',root.FFIPOMarket.sourceAnalysis(d));root.FFIPOMarket.watch(app,here);}
      if(!(d.periods||[]).length){select.closest('label').hidden=true;return;}
      d.periods.forEach((p,i)=>select.add(new Option(`${p.label} · ${p.start} to ${p.end}`,i)));select.value=String(d.periods.length-1);
      const draw=()=>{
        const p=d.periods[Number(select.value)],v=p.values, panel=app.querySelector('#ipo-body'), specs=charts({...p,company:d.name,source_url:u,accession:d.accession});
        panel.innerHTML=`<div class="qi-cards">${[['Revenue',v.revenue],['Operating income / loss',v.oi],['Net income / loss',v.ni],['Operating cash flow',v.ocf],['FCF · OCF less cash CapEx',finite(v.ocf)&&finite(v.capex)?v.ocf-v.capex:null]].map(([label,value])=>`<div class="qi-card"><span>${esc(label)}</span><strong>${esc(amount(value,p.unit))}</strong></div>`).join('')}</div><p class="qi-notice">Net loss is not cash burn. Fair-value changes and stock compensation can be noncash. Interim periods are not annualized; cash balances and multiyear commitments are not mixed into income flows.</p><h2>Statement Sankeys</h2>${specs.length?'':'<p>Supported data is incomplete; no reconciled chart is drawn.</p>'}<div class="qi-charts"></div><h2>Quality measures</h2>${metricTable(p.metrics||[])}<details><summary>Reported inputs, units & evidence</summary><div class="qi-table"><table><thead><tr><th>Line</th><th>Amount</th><th>Evidence</th></tr></thead><tbody>${Object.entries(p.evidence||{}).map(([k,e])=>`<tr><td>${esc(e.label)}</td><td>${esc(amount(v[k],p.unit))}</td><td>${esc(e.statement||'XBRL')} ${e.table_index!=null?'· table '+(e.table_index+1):''} · ${esc(e.cell||'')} ${e.scale?'× '+e.scale:''}</td></tr>`).join('')}</tbody></table></div></details>`;
        const host=panel.querySelector('.qi-charts');specs.forEach(spec=>{const box=document.createElement('article');box.className='qi-chart';const scene=root.Sankey.layout(spec,{});box.innerHTML=root.Sankey.toSVG(scene,spec.title);const b=document.createElement('button');b.type='button';b.textContent='Download PNG';b.onclick=async()=>{b.disabled=true;try{const blob=await root.Sankey.exportScene(scene,'png');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`ipo-${cik}-${p.end}-${specs.indexOf(spec)+1}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}finally{b.disabled=false;}};box.appendChild(b);host.appendChild(box);});
      };select.onchange=draw;draw();
    }catch(e){if(here())app.innerHTML='<section class="section"><h1>IPO analysis unavailable</h1><p>The requested snapshot could not be loaded.</p><a href="#ipo">Return to IPO watchlist</a></section>';}
  }
  root.FFQualityIPO={quality,ipo,flow,charts,metricTable};
})(typeof window!=='undefined'?window:globalThis);
