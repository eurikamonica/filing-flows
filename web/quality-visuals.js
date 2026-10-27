/* Company quality trends. Reuses published company facts; no peer scores or synthetic data. */
(function (root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const fmt = v => fin(v) ? v.toLocaleString('en-US', {maximumFractionDigits:2}) : 'Not available';
  const colors = ['#367fc1','#bf7134','#8862b5','#288c83'];
  const SALES = [['rev','Revenue'],['ar_c','Receivables · closing'],['inv_c','Inventory · closing']];
  const DAYS = [['dso','DSO'],['dio','DIO'],['dpo','DPO']];
  function periods(c, mode) {
    return [...((c.quality || {})[mode] || [])].filter(p => /^\d{4}-\d{2}-\d{2}$/.test(p.end || '')).sort((a,b) => a.end.localeCompare(b.end));
  }
  function series(rows, keys) {
    return keys.map(([key,label],i) => ({key,label,color:colors[i],values:rows.map(p => fin(p.wc?.[key]) ? p.wc[key] : null)}));
  }
  function indexed(rows, keys) {
    const raw = series(rows, keys);
    const start = rows.findIndex((_,i) => raw.length && raw.every(s => fin(s.values[i]) && s.values[i] > 0));
    if (start < 0) return {rows:[],series:[],base:null};
    return {rows:rows.slice(start),base:rows[start].end,series:raw.map(s => ({...s,values:s.values.slice(start).map(v => fin(v) ? 100*v/s.values[start] : null)}))};
  }
  function chart(rows, lines, title, suffix='') {
    const values=lines.flatMap(s=>s.values.filter(fin));
    if (!values.length) return '<p class="qvis-empty">No comparable observations are available. Missing values are not zero.</p>';
    const W=640,H=260,L=66,R=18,T=18,B=46;
    let lo=Math.min(0,...values),hi=Math.max(0,...values);if(hi===lo)hi=lo+1;
    const pad=(hi-lo)*.08;lo=lo<0?lo-pad:0;hi=hi>0?hi+pad:0;
    const X=i=>L+i/Math.max(1,rows.length-1)*(W-L-R),Y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
    let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>`;
    for(let i=0;i<5;i++) {const v=lo+(hi-lo)*i/4,y=Y(v);svg+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" class="qvis-grid"/><text x="${L-9}" y="${y+4}" text-anchor="end">${esc(Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(v))}${esc(suffix)}</text>`;}
    const stride=Math.max(1,Math.ceil(rows.length/4));
    rows.forEach((p,i)=>{if(i%stride===0||i===rows.length-1)svg+=`<text class="qvis-x ${i>0&&i<rows.length-1?'qvis-x-mid':''}" x="${X(i)}" y="${H-19}" text-anchor="${i===0?'start':i===rows.length-1?'end':'middle'}">${esc(p.end)}</text>`;});
    lines.forEach((s,k)=>{
      let path='',connected=false;
      s.values.forEach((v,i)=>{if(!fin(v)){connected=false;return;}const gap=i>0&&(Date.parse(rows[i].end)-Date.parse(rows[i-1].end)> (rows[i]._mode==='q'?130:430)*864e5);path+=`${connected&&!gap?'L':'M'}${X(i)},${Y(v)} `;connected=true;});
      svg+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.5" ${k?`stroke-dasharray="${k===1?'7 3':'2 3'}"`:''}/>`;
      s.values.forEach((v,i)=>{if(fin(v))svg+=`<circle cx="${X(i)}" cy="${Y(v)}" r="4" fill="${s.color}"><title>${esc(s.label)} · ${esc(rows[i].end)}: ${esc(fmt(v))}${esc(suffix)}</title></circle>`;});
    });
    return svg+'</svg><div class="qvis-legend">'+lines.map((s,k)=>`<span><i style="background:${s.color}"></i>${esc(s.label)}${k?' · dashed':''} (${s.values.filter(fin).length}/${rows.length})</span>`).join('')+'</div>';
  }
  function table(rows, lines, suffix='') {
    return `<details class="qvis-data"><summary>Chart data · accessible table</summary><div class="qvis-scroll" tabindex="0"><table><thead><tr><th>Period end</th>${lines.map(s=>`<th>${esc(s.label)}</th>`).join('')}</tr></thead><tbody>${rows.map((p,i)=>`<tr><th>${esc(p.end)}</th>${lines.map(s=>`<td>${esc(fmt(s.values[i]))}${fin(s.values[i])?esc(suffix):''}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
  }
  function evidence(c,p) {
    const src=c.quality?.src || {}, cik=String(c.profile?.cik || c.cik || ''), h=p.health || {};
    const inputs=[...SALES.map(([k,label])=>({label,value:p.wc?.[k],ref:p.ev?.[k]})),...Object.entries(h.inputs||{}).map(([k,value])=>({label:k,value,ref:h.ev?.[k]}))];
    return `<details class="qvis-data"><summary>Source inputs · ${esc(p.end)} · ${esc(c.quality?.unit || c.currency || 'reporting currency')}</summary><p>Revenue is a period flow; receivables and inventory are closing balances. Indexed lines compare growth, not cash flows or additive amounts.</p>${inputs.map(x=>{
      const ref=x.ref,concept=ref?src.concepts?.[ref[0]]:null;
      const links=(ref?.[2]||[]).map(i=>{const f=src.filings?.[i];if(!f||!/^\d{10}-\d{2}-\d{6}$/.test(f[0])||!/^\d{1,10}$/.test(cik))return '';return `<a href="https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${f[0].replaceAll('-','')}/${f[0]}-index.html" target="_blank" rel="noopener noreferrer">${esc(f[1])} · ${esc(f[2])}</a>`;}).filter(Boolean).join(' · ');
      return `<p><strong>${esc(x.label)}</strong>: ${esc(fmt(x.value))}<br><small>${esc(concept?.[0] || 'No source fact published')}${ref?.[3]?' · Balance '+esc(ref[3]):''} ${links}</small></p>`;
    }).join('')}</details>`;
  }
  function mount(parent,c) {
    const section=document.createElement('section');section.className='section qvis';parent.appendChild(section);
    let mode=periods(c,'fy').length?'fy':'q',metric='ocf_margin',selectedEnd=null;
    section.innerHTML='<div class="qvis-head"><div><p class="qvis-eyebrow">Company quality · visual review</p><h2>Sales, collections & quality trends</h2></div><label>Period basis <select data-basis aria-label="Quality trend period basis"><option value="fy">Fiscal years</option><option value="q">Quarters</option></select></label></div><div data-visuals></div>';
    const basis=section.querySelector('[data-basis]');basis.value=mode;
    for(const o of basis.options)o.disabled=!periods(c,o.value).length;
    function draw(){
      const rows=periods(c,mode).map(p=>({...p,_mode:mode})),out=section.querySelector('[data-visuals]');
      if(!rows.length){out.innerHTML='<p>No company quality periods have been published.</p>';return;}
      const financial=c.profile?.sector==='financials'||/^6[0-7]/.test(String(c.profile?.sic||''));
      const available=SALES.filter(([k])=>rows.some(p=>fin(p.wc?.[k])&&p.wc[k]>0));
      const ix=indexed(rows,available),daySeries=series(rows,DAYS);
      const metrics=new Map();rows.forEach(p=>(p.health?.metrics||[]).forEach(m=>metrics.set(m.id,m)));
      if(!metrics.has(metric))metric=metrics.keys().next().value;
      const m=metrics.get(metric),mline=m?[{label:m.label,color:colors[0],values:rows.map(p=>{const v=p.health?.metrics?.find(x=>x.id===metric)?.value;return fin(v)?v*(m.format==='multiple'?1:100):null;})}]:[];
      if(!rows.some(p=>p.end===selectedEnd))selectedEnd=rows[rows.length-1].end;
      const p=rows.find(p=>p.end===selectedEnd),covered=SALES.filter(([k])=>fin(p.wc?.[k])).length;
      const subtitle=`${mode==='q'?'Quarterly observations; seasonal patterns and quarter length affect comparisons.':'Fiscal-year observations; compare consistent fiscal lengths.'} Gaps stay visible. These are reported-data trends, not peer rankings or a fraud score.`;
      out.innerHTML=`<p class="muted">${esc(subtitle)}</p>${financial?'<p class="qvis-notice">Financial-sector company: industrial working-capital and cash-conversion measures may not be meaningful. Read lending, deposit and trading disclosures separately.</p>':''}<div class="qvis-toolbar"><label>Inspect source period <select data-end aria-label="Quality evidence period">${rows.map(r=>`<option value="${r.end}" ${r.end===selectedEnd?'selected':''}>${esc(r.label)} · ${r.end}</option>`).join('')}</select></label><span>${covered}/3 sales & balance inputs available for this period</span></div><div class="qvis-panels"><article class="qvis-card"><h3>Sales vs receivables & inventory</h3><p class="muted">${ix.base?'Shared base '+esc(ix.base)+' = 100. All shown series use the same positive base.':'No shared positive base is available.'} ${SALES.filter(([k])=>!available.some(a=>a[0]===k)).map(x=>esc(x[1])+' unavailable.').join(' ')}</p>${chart(ix.rows,ix.series,'Revenue, receivables and inventory indexed to a common base')}${table(ix.rows,ix.series)}</article><article class="qvis-card"><h3>Collection & payment days</h3><p class="muted">DSO uses revenue as a credit-sales proxy; DIO and DPO use cost of revenue. Payables may include accrued liabilities. Days are not a risk rating.</p>${chart(rows,daySeries,'DSO DIO and DPO by reporting period','d')}${table(rows,daySeries,' days')}</article><article class="qvis-card qvis-wide"><div class="qvis-head"><h3>Quality measure history</h3><label>Measure <select data-metric aria-label="Quality trend measure">${[...metrics.values()].map(v=>`<option value="${esc(v.id)}" ${v.id===metric?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label></div>${m?`<p class="muted">${esc(m.formula)}. ${mline[0].values.filter(fin).length}/${rows.length} observations available. Quarterly ROA and accrual ratios are not annualized.</p>${chart(rows,mline,m.label+' history',m.format==='multiple'?'×':'%')}${table(rows,mline,m.format==='multiple'?'×':'%')}`:'<p>Extended quality measures have not been published for these periods. Available sales and working-capital data remain above.</p>'}</article></div>${evidence(c,p)}<p class="muted">Company-file coverage only: no industry distribution or discretionary-accrual model is inferred from missing data.</p>`;
      out.querySelector('[data-end]').onchange=e=>{selectedEnd=e.target.value;draw();section.querySelector('[data-end]').focus();};
      out.querySelector('[data-metric]').onchange=e=>{metric=e.target.value;draw();section.querySelector('[data-metric]').focus();};
    }
    basis.onchange=()=>{mode=basis.value;selectedEnd=null;draw();};draw();return section;
  }
  root.FFQualityVisuals={mount,periods,indexed,chart,table,evidence};
})(typeof window==='undefined'?globalThis:window);
