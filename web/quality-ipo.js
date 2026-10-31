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
  // ---------- the company page ----------
  // One standard Sankey per prospectus period (pipeline/ipo_charts.py: the site's own format, Y/Y against the same
  // length of time a year earlier), the key figures, the rule-based analysis, the periods side by side, and the
  // prospectus itself (web/ipo-reader.js). Snapshots published before the charts existed keep the earlier view.
  const dec = (v) => String(v ?? '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? `${MON[+m[2] - 1]} ${+m[3]}, ${m[1]}` : String(s || ''); };
  function usd(v, like) {                       // like: a figure on the chart, so the comparison uses its unit
    if (!finite(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9 || (/B$/.test(like || '') && a >= 5e6)) return a >= 0.95e9 ? `${s}$${(a / 1e9).toFixed(1)}B` : `${s}$${(a / 1e9).toFixed(2)}B`;
    return a >= 0.95e6 ? `${s}$${(a / 1e6).toFixed(1)}M` : `${s}$${Math.round(a / 1e3).toLocaleString('en-US')}K`;
  }
  const growth = (a, b) => (finite(a) && finite(b) && a > 0 && b > 0 ? (a / b - 1) * 100 : null);
  const signed = (g, digits = 0) => (g == null ? 'n/m' : `${g > 0.05 ? '+' : g < -0.05 ? '−' : ''}${Math.abs(g).toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`);
  const margin = (m) => (finite(m) ? signed(m, Math.abs(m) < 100 ? 1 : 0).replace(/^\+/, '') : 'n/m');
  const GROUPS = [[12, 'Years'], [9, 'Nine months'], [6, 'Half years'], [3, 'Quarters']];
  function periodGroups(periods, current) {
    const out = [];
    for (const [m, name] of GROUPS) {
      const items = periods.filter((p) => p.months === m).sort((a, b) => (a.end < b.end ? 1 : -1));
      if (items.length) out.push({ months: m, name, items });
    }
    const other = periods.filter((p) => !GROUPS.some(([m]) => m === p.months));
    if (other.length) out.push({ months: 0, name: 'Other periods', items: other });
    const cur = out.findIndex((g) => g.items.some((p) => p.key === current));
    if (cur > 0) out.unshift(...out.splice(cur, 1));
    return out;
  }
  function tiles(p) {
    const h = p.headline || {}, pr = h.prior || {}, vs = p.vs;
    const was = (v, like) => (vs && finite(v) ? `${vs}: ${usd(v, like)}` : '');
    const cards = [
      ['Revenue', h.rev_fmt, vs ? `${signed(growth(h.revenue, pr.revenue))} vs ${vs}` : 'no earlier period of the same length'],
      [h.oi >= 0 ? 'Operating profit' : 'Operating loss', h.oi_fmt, `margin ${margin(h.om)}${was(pr.oi, h.oi_fmt) ? ' · ' + was(pr.oi, h.oi_fmt) : ''}`],
      [h.ni >= 0 ? 'Net income' : 'Net loss', h.ni_fmt, was(pr.ni, h.ni_fmt) || `margin ${margin(h.nm)}`],
      ['Operating cash flow', h.ocf_fmt || '—', was(pr.ocf, h.ocf_fmt) || (h.ocf_fmt ? '' : 'not in the statements read')],
      ['Free cash flow', h.fcf_fmt || '—', h.fcf_fmt ? 'operating cash flow − capital expenditures' : 'capital expenditures not read'],
    ];
    return cards.map(([l, v, sub]) => `<div class="qi-card"><span>${esc(l)}</span><strong>${esc(v || '—')}</strong>${sub ? `<small>${esc(sub)}</small>` : ''}</div>`).join('');
  }
  function ticks(max) {                          // 3–5 round steps from zero that cover the data
    const raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= raw) || mag * 10;
    const out = [];
    for (let v = 0; v <= max + step * 0.001; v += step) out.push(v);
    if (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
    return out;
  }
  const chrono = (list) => periodGroups(list).sort((a, b) => GROUPS.findIndex(([m]) => m === a.months) - GROUPS.findIndex(([m]) => m === b.months))
    .map((g) => ({ ...g, items: g.items.slice().reverse() }));
  const narrow = () => !!(root.matchMedia && root.matchMedia('(max-width: 600px)').matches);   // phones: a narrower drawing, legible text
  function revenueSVG(list, current) {
    const groups = chrono(list), n = groups.reduce((k, g) => k + g.items.length, 0) + groups.length - 1;
    const W = narrow() ? 360 : 560, H = 230, L = 52, R = 12, T = 26, B = 52, pw = W - L - R, ph = H - T - B;
    const max = Math.max(...list.map((p) => p.headline.revenue)), tk = ticks(max), top = tk[tk.length - 1];
    const slot = pw / Math.max(n, 1), bw = Math.min(24, slot * 0.55), y = (v) => T + ph - (v / top) * ph;
    let i = 0, out = '';
    const tickTxt = (v) => (!v ? '$0' : v >= 1e9 ? `$${+(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `$${+(v / 1e6).toFixed(2)}M` : `$${+(v / 1e3).toFixed(1)}K`);
    out += tk.map((v) => `<line class="ipo-grid" x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="ipo-tick" x="${L - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${tickTxt(v)}</text>`).join('');
    groups.forEach((g, gi) => {
      const x0 = L + i * slot;
      g.items.forEach((p) => {
        const cx = L + i * slot + slot / 2, v = p.headline.revenue, yt = y(v), yb = y(0), r = Math.min(4, (yb - yt) / 2), x = cx - bw / 2, on = p.key === current;
        out += `<g class="ipo-col${on ? ' on' : ''}" data-key="${esc(p.key)}" tabindex="0" role="button" aria-pressed="${on}" aria-label="${esc(`${p.label} revenue ${p.headline.rev_fmt}`)}">
          <title>${esc(`${p.label}: revenue ${p.headline.rev_fmt}${p.vs ? `, ${signed(growth(v, p.headline.prior && p.headline.prior.revenue))} vs ${p.vs}` : ''}`)}</title>
          <rect class="ipo-hit" x="${(cx - slot / 2).toFixed(1)}" y="${T}" width="${slot.toFixed(1)}" height="${ph + 22}" fill="transparent"/>
          <path d="M${x.toFixed(1)} ${yb.toFixed(1)}V${(yt + r).toFixed(1)}Q${x.toFixed(1)} ${yt.toFixed(1)} ${(x + r).toFixed(1)} ${yt.toFixed(1)}H${(x + bw - r).toFixed(1)}Q${(x + bw).toFixed(1)} ${yt.toFixed(1)} ${(x + bw).toFixed(1)} ${(yt + r).toFixed(1)}V${yb.toFixed(1)}Z"/>
          ${on ? `<text class="ipo-cap" x="${cx.toFixed(1)}" y="${(yt - 6).toFixed(1)}" text-anchor="middle">${esc(p.headline.rev_fmt)}</text>` : ''}
          <text class="ipo-xl" x="${cx.toFixed(1)}" y="${H - B + 16}" text-anchor="middle">${esc(p.label.replace(/^(FY|H1|H2|9M|Q\d) /, '$1 ’').replace(/’(\d\d)(\d\d)$/, '’$2'))}</text></g>`;
        i++;
      });
      const x1 = L + i * slot;
      out += `<text class="ipo-gl" x="${((x0 + x1) / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(g.name)}</text>`;
      if (gi < groups.length - 1) i++;
    });
    out += `<line class="ipo-axis" x1="${L}" x2="${W - R}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Revenue by period">${out}</svg>`;
  }
  function costParts(spec) {
    const ids = new Map(spec.nodes.map((x) => [x.id, x]));
    let parts = spec.nodes.filter((x) => x.id.startsWith('I:') || x.id === 'cor');
    if (!parts.length) parts = ['opcosts', 'costs', 'opex'].map((k) => ids.get(k)).filter(Boolean).slice(0, 1);
    const rev = (ids.get('revenue') || {}).v;
    return finite(rev) && rev > 0 ? parts.map((x) => ({ key: x.id.replace(/^I:/, ''), name: dec(x.name), v: x.v, per: x.v / rev })) : [];
  }
  function costSVG(list, current) {
    const rows = chrono(list).flatMap((g) => g.items).map((p) => ({ p, parts: costParts(p) })).filter((r) => r.parts.length);
    if (!rows.length) return null;
    const keys = [], names = {};
    rows.forEach((r) => r.parts.forEach((x) => { if (!keys.includes(x.key)) { keys.push(x.key); names[x.key] = x.name; } }));
    const slotOf = (k) => (keys.indexOf(k) % 6) + 1, total = (r) => r.parts.reduce((a, x) => a + x.per, 0);
    const maxT = Math.max(...rows.map(total)), cap = maxT > 3.2 ? 3 : Math.max(1.2, maxT * 1.08);
    const W = narrow() ? 360 : 560, L = 64, R = 52, T = 30, RH = 30, BH = 12, H = T + rows.length * RH + 26, pw = W - L - R, x = (v) => L + Math.min(v, cap) / cap * pw;
    let out = '';
    const step = cap > 2 ? 1 : 0.5;
    for (let v = 0; v <= cap + 1e-9; v += step) out += `<line class="ipo-grid" x1="${x(v).toFixed(1)}" x2="${x(v).toFixed(1)}" y1="${T - 6}" y2="${H - 22}"/><text class="ipo-tick" x="${x(v).toFixed(1)}" y="${H - 8}" text-anchor="middle">$${v.toFixed(v % 1 ? 2 : 0)}</text>`;
    rows.forEach((r, k) => {
      const yy = T + k * RH + (RH - BH) / 2, on = r.p.key === current, t = total(r);
      let at = 0;
      out += `<g class="ipo-crow${on ? ' on' : ''}" data-key="${esc(r.p.key)}" tabindex="0" role="button" aria-pressed="${on}" aria-label="${esc(`${r.p.label}: $${t.toFixed(2)} of operating costs per $1 of revenue`)}">
        <title>${esc(`${r.p.label}: $${t.toFixed(2)} of costs per $1 of revenue — ` + r.parts.map((x) => `${x.name} $${x.per.toFixed(2)}`).join(', '))}</title>
        <rect class="ipo-hit" x="0" y="${T + k * RH}" width="${W}" height="${RH}" fill="transparent"/>
        <text class="ipo-rl" x="${L - 8}" y="${yy + BH - 2}" text-anchor="end">${esc(r.p.label)}</text>`;
      r.parts.forEach((p) => {
        if (at >= cap) return;
        const a = x(at) + (at ? 1 : 0), b = x(at + p.per) - 1;
        at += p.per;
        if (b - a > 0.6) out += `<rect class="ipo-s${slotOf(p.key)}" x="${a.toFixed(1)}" y="${yy}" width="${(b - a).toFixed(1)}" height="${BH}" rx="2"/>`;
      });
      if (t > cap) out += `<path class="ipo-break" d="M${(x(cap) - 7).toFixed(1)} ${yy - 3}l5 ${BH + 6}M${(x(cap) - 2).toFixed(1)} ${yy - 3}l5 ${BH + 6}"/>`;
      out += `<text class="ipo-end${t > 1 ? ' over' : ''}" x="${(x(Math.min(t, cap)) + 6).toFixed(1)}" y="${yy + BH - 2}">$${t.toFixed(2)}</text></g>`;
    });
    out += `<line class="ipo-even" x1="${x(1).toFixed(1)}" x2="${x(1).toFixed(1)}" y1="${T - 14}" y2="${H - 22}"/><text class="ipo-evl" x="${(x(1) + 4).toFixed(1)}" y="${T - 16}">break-even: costs = revenue</text>`;
    const legend = `<ul class="ipo-legend">${keys.map((k) => `<li><i class="ipo-s${slotOf(k)}"></i>${esc(names[k])}</li>`).join('')}</ul>`;
    const tableView = `<details class="ipo-tview"><summary>Table</summary><div class="qi-table"><table><thead><tr><th>Period</th><th>Revenue</th>${keys.map((k) => `<th>${esc(names[k])}</th>`).join('')}<th>Costs per $1</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.p.label)}</td><td>${esc(r.p.headline.rev_fmt)}</td>${keys.map((k) => { const x0 = r.parts.find((x) => x.key === k); return `<td>${x0 ? `${usd(x0.v, r.p.headline.rev_fmt)} · $${x0.per.toFixed(2)}` : '—'}</td>`; }).join('')}<td>$${total(r).toFixed(2)}</td></tr>`).join('')}</tbody></table></div></details>`;
    return { svg: `<svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Operating costs per dollar of revenue by period">${out}</svg>`, legend, tableView, capped: maxT > cap };
  }
  function trendsHTML(list, current) {
    if (list.length < 2) return '';
    const cost = costSVG(list, current);
    return `<h2>Across the periods</h2><p class="muted">Click a period to open its chart. Years and half years are shown apart: they are different lengths of time.</p>
      <div class="ipo-trends"><figure class="ipo-fig"><figcaption><strong>Revenue</strong></figcaption>${revenueSVG(list, current)}</figure>
      ${cost ? `<figure class="ipo-fig"><figcaption><strong>Operating costs per $1 of revenue</strong><span class="muted">Each line of costs; past $1.00 the period lost money before interest and other items${cost.capped ? '. Bars past $3 are cut (the total is printed)' : ''}.</span></figcaption>${cost.legend}${cost.svg}${cost.tableView}</figure>` : ''}</div>`;
  }
  function filingFacts(d, p) {
    const u = source(p.doc_url || d.source_url), idx = source(p.index_url);
    return `<dl class="facts"><dt>Form</dt><dd><span class="mono">${esc(d.form)}</span> · registration statement${/\/A$/.test(d.form || '') ? ' (amendment)' : ''}</dd>
      <dt>Period</dt><dd>${esc(p.label)} · ${esc(dec(p.subtitle || '').split(' · ')[0])}</dd>
      <dt>Compared with</dt><dd>${p.vs ? esc(p.vs) + ' (the same length of time a year earlier)' : 'nothing: the filing has no earlier period of the same length'}</dd>
      <dt>Filed</dt><dd>${esc(day(d.filed))}</dd>
      <dt>Accession</dt><dd class="mono">${esc(d.accession)}</dd>
      <dt>Documents</dt><dd>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">Prospectus ↗</a>` : ''}${idx ? ` · <a href="${esc(idx)}" target="_blank" rel="noopener noreferrer">Filing index ↗</a>` : ''}</dd>
      <dt>Data</dt><dd>${d.method === 'reviewed_html_tables' ? 'The statement of operations and the statement of cash flows, read from the prospectus tables with a reviewed mapping that must add up' : 'The inline XBRL tags of the financial statements in the prospectus'}</dd></dl>`;
  }
  function drawChart(host, spec, d, list) {
    host.innerHTML = '';
    const FF = root.FFApp;
    if (FF && FF.chartUI) {                       // the site's own chart: standard / vs a year earlier, zoom, export, notes
      const same = list.filter((x) => x.months === spec.months);
      const unit = { 12: 'fiscal years', 9: 'nine-month periods', 6: 'half years', 3: 'quarters' }[spec.months] || 'periods';
      host.appendChild(FF.chartUI(spec, {
        company: dec(d.name), form: d.form, label: spec.label, docUrl: spec.doc_url, cik: d.cik,
        slug: `ipo-${Number(d.cik)}-${spec.label}`.replace(/\s+/g, '-'),
        trend: FF.trendSeries ? (id) => Object.assign(FF.trendSeries(same, spec, id, true), { unit }) : null,
      }));
      return;
    }
    const S = root.Sankey;                        // without the site's app: the same chart, static, with a PNG download
    if (!S) return;
    const box = document.createElement('article');
    box.className = 'qi-chart ipo-static';
    const scene = S.layout(spec, {});
    box.innerHTML = S.toSVG(scene, dec(spec.title));
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = 'Download PNG';
    b.onclick = async () => {
      b.disabled = true;
      try {
        const blob = await S.exportScene(scene, 'png'), url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = `ipo-${Number(d.cik)}-${spec.label.replace(/\s+/g, '-')}-sankey.png`; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } finally { b.disabled = false; }
    };
    box.appendChild(b);
    host.appendChild(box);
  }
  function inputsTable(p) {
    return `<div class="qi-table"><table><thead><tr><th>Field</th><th>Reported value</th><th>Source line, cell and unit</th></tr></thead><tbody>${Object.entries(p.values || {}).map(([k, v]) => {
      const e = (p.evidence || {})[k] || {};
      return `<tr><td>${esc(k)}</td><td>${esc(amount(v, p.unit))}</td><td>${esc(e.label || 'Calculated')}${e.cell ? ` · cell ${esc(e.cell)}` : ''}${e.scale ? ` · ×${esc(e.scale)}` : ''}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  function company(app, d, here, cik) {
    const u = source(d.source_url), C = d.charts || {}, list = (C.periods || []).filter((p) => !p.error && (p.nodes || []).length);
    const failed = (C.periods || []).filter((p) => p.error);
    const rd = d.reader || null, cover = (rd && rd.cover) || {}, R = root.FFIPOReader, M = root.FFIPOMarket;
    const lab = { ipo_language_identified: 'Initial public offering', resale_language_identified: 'Resale registration', registration_unclassified: 'Registration statement' };
    let current = list.some((p) => p.key === C.default) ? C.default : (list[0] || {}).key;
    const idx = d.accession ? source(`https://www.sec.gov/Archives/edgar/data/${Number(d.cik)}/${String(d.accession).replace(/-/g, '')}/${d.accession}-index.html`) : '';
    app.innerHTML = `<section class="section qi-section ipo-page">
      <a class="ipo-back" href="#ipo">← IPO market monitor</a>
      <header class="ipo-head">
        <div class="eyebrow">${esc(lab[d.classification] || 'Registration statement')} · ${esc(d.form)} filed ${esc(day(d.filed))}</div>
        <h1>${esc(d.name)}</h1>
        ${R ? R.chips(cover) : ''}
        <p class="ipo-links">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">Prospectus on SEC ↗</a>` : ''}${idx ? `<a href="${esc(idx)}" target="_blank" rel="noopener noreferrer">Filing index ↗</a>` : ''}<button type="button" class="ipo-linkish" data-goto="ipo-data">${(d.filings || []).length || 1} filing${(d.filings || []).length === 1 ? '' : 's'} · data status</button></p>
        ${d.scan && d.scan.state === 'failed' ? '<p class="qi-notice">The latest refresh failed. Showing the last successfully parsed filing; this may not be the latest amendment.</p>' : ''}
        ${d.latest_discovered && d.latest_discovered.accession && d.latest_discovered.accession !== d.accession ? `<p class="qi-notice">These figures are from the ${esc(d.form)} filed ${esc(day(d.filed))}; a later ${esc(d.latest_discovered.form)} (${esc(day(d.latest_discovered.filed))}) is not read yet.</p>` : ''}
      </header>
      <div class="ipo-periods" role="group" aria-label="Reporting period">${periodGroups(list, current).map((g) => `<div class="ipo-pgroup"><span class="eyebrow">${esc(g.name)}</span><div class="seg">${g.items.map((p) => `<button type="button" data-period="${esc(p.key)}" aria-pressed="${p.key === current}">${esc(p.label)}</button>`).join('')}</div></div>`).join('')}</div>
      <div class="qi-cards ipo-tiles" aria-live="polite"></div>
      <div class="ipo-chart"></div>
      <div class="cols ipo-cols"></div>
      ${failed.length ? `<p class="muted ipo-failed">No chart for ${failed.map((p) => esc(p.label)).join(', ')}: ${esc(failed[0].error)}</p>` : ''}
      <section class="ipo-trend-box"></section>
      <section class="ipo-read" aria-labelledby="ipo-read-h">${rd ? '<p class="muted" role="status">Loading the prospectus…</p>' : ''}</section>
      <section class="ipo-more">
        <details class="ipo-q"><summary>Quality measures</summary><div></div></details>
        <details class="ipo-recon"><summary>Statement reconciliations (four accounting equations)</summary><div class="qi-charts"></div></details>
        <details class="ipo-inputs"><summary>Reported inputs, units and evidence</summary><div></div></details>
        <details id="ipo-data"><summary>Filings and data status</summary><div class="ipo-status"></div></details>
        <details><summary>Coverage limits</summary><ul>${(d.limitations || []).map((x) => `<li>${esc(x)}</li>`).join('')}<li>Net loss is not cash burn: fair-value changes and stock compensation are non-cash. Interim periods are not annualized.</li></ul></details>
      </section></section>`;
    const $ = (sel) => app.querySelector(sel);
    $('.ipo-status').innerHTML = `${M ? M.detail(d) : ''}<p class="muted">${esc(d.accession)} · ${esc(d.method)}<br>Latest attempt: ${esc((d.scan && d.scan.last_attempt) || 'Not run')} · Latest success: ${esc((d.scan && d.scan.last_success) || 'Not run')} · Status: ${esc((d.scan && d.scan.state) || 'bundled_snapshot')}</p>`;
    const raw = (p) => (d.periods || []).find((x) => x.start === p.start && x.end === p.end);
    function draw(key, scroll) {
      current = key;
      const p = list.find((x) => x.key === key);
      app.querySelectorAll('[data-period]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.period === key)));
      $('.ipo-tiles').innerHTML = tiles(p);
      drawChart($('.ipo-chart'), p, d, list);
      $('.ipo-cols').innerHTML = `<div class="prose"><h2>Analysis</h2>${(p.analysis || []).map((x) => `<p>${esc(dec(x))}</p>`).join('')}
          ${p.compare_y && (p.compare_y.bullets || []).length ? `<h3>What changed vs ${esc(p.compare_y.vs)}</h3><ul class="ipo-changed">${p.compare_y.bullets.map((x) => `<li>${esc(dec(x))}</li>`).join('')}</ul>` : ''}
          <p class="note-rule">Written by fixed rules from the reported figures (no language model): growth, margins, the line that moved most and cash conversion.</p></div>
        <div class="prose"><h2>Filing</h2>${filingFacts(d, p)}</div>`;
      $('.ipo-trend-box').innerHTML = trendsHTML(list, key);
      app.querySelectorAll('.ipo-trend-box [data-key]').forEach((g) => {
        const go = () => draw(g.dataset.key, true);
        g.addEventListener('click', go);
        g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      });
      const rp = raw(p);
      $('.ipo-q > div').innerHTML = rp ? `<p class="muted">${esc(p.label)}.</p>${metricTable(rp.metrics || [])}` : '<p class="muted">No measures for this period.</p>';
      $('.ipo-inputs > div').innerHTML = rp ? inputsTable(rp) : '';
      if ($('.ipo-recon').open) recon();
      if (scroll) $('.ipo-periods').scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
    function recon() {
      const rp = raw(list.find((x) => x.key === current)), host = $('.ipo-recon .qi-charts');
      host.innerHTML = '';
      if (!rp || !root.Sankey) return;
      charts({ ...rp, company: d.name, source_url: u, accession: d.accession }).forEach((spec, k) => {
        const box = document.createElement('article');
        box.className = 'qi-chart';
        box.innerHTML = root.Sankey.toSVG(root.Sankey.layout(spec, {}), spec.title);
        host.appendChild(box);
      });
    }
    $('.ipo-recon').addEventListener('toggle', () => { if ($('.ipo-recon').open) recon(); });
    app.querySelectorAll('[data-period]').forEach((b) => b.addEventListener('click', () => draw(b.dataset.period)));
    app.querySelector('[data-goto]').addEventListener('click', () => {      // the hash is the route: no in-page anchors
      const box = $('#ipo-data');
      box.open = true;
      box.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
    draw(current);
    if (rd && R && M) {
      M.load(rd.path).then((r) => {
        if (!here() || !app.isConnected) return;
        R.render($('.ipo-read'), r, { url: rd.url || d.source_url, form: rd.form || d.form });
      }).catch(() => { if (here()) $('.ipo-read').innerHTML = '<p class="muted">The prospectus reading could not be loaded.</p>'; });
    }
    if (M) M.watch(app, here);
  }
  // a company whose statements are not read yet but whose prospectus is: the prospectus first, the rest folded
  function unparsed(app, d, here, u) {
    const rd = d.reader || null, R = root.FFIPOReader, M = root.FFIPOMarket;
    const lab = { ipo_language_identified: 'Initial public offering', resale_language_identified: 'Resale registration', registration_unclassified: 'Registration statement' };
    app.innerHTML = `<section class="section qi-section ipo-page"><a class="ipo-back" href="#ipo">← IPO market monitor</a>
      <header class="ipo-head"><div class="eyebrow">${esc(lab[d.classification] || 'Registration statement')} · ${esc(d.form)} filed ${esc(day(d.filed))}</div><h1>${esc(d.name)}</h1>${R && rd ? R.chips(rd.cover) : ''}
      <p class="ipo-links">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">Prospectus on SEC ↗</a>` : ''}</p>
      <p class="muted ipo-nofin">The financial statements of this filing are not read yet: no chart is drawn and no figure is guessed. Its prospectus is below.</p></header>
      <section class="ipo-read" aria-labelledby="ipo-read-h"><p class="muted" role="status">Loading the prospectus…</p></section>
      <section class="ipo-more">
        <details class="ipo-src"><summary>Source tables found in the filing</summary><div class="ipo-source"></div></details>
        <details id="ipo-data"><summary>Filings and data status</summary><div class="ipo-status"></div></details>
        <details><summary>Coverage limits</summary><ul>${(d.limitations || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details>
      </section></section>`;
    if (M) {
      app.querySelector('.ipo-source').innerHTML = M.sourceAnalysis(d);
      app.querySelector('.ipo-status').innerHTML = M.detail(d, { open: false });
      M.watch(app, here);
    }
    if (rd && R && M) {
      M.load(rd.path).then((r) => { if (here() && app.isConnected) R.render(app.querySelector('.ipo-read'), r, { url: rd.url || d.source_url, form: rd.form || d.form }); })
        .catch(() => { if (here()) app.querySelector('.ipo-read').innerHTML = '<p class="muted">The prospectus reading could not be loaded.</p>'; });
    }
  }
  async function ipo(app,here=()=>true,cik,accession) {
    app.innerHTML='<p role="status">Loading IPO filings…</p>';
    try {
      const path=accession?`filings/${accession}.json`:cik?`${cik}.json`:'index.json';if(cik&&!/^\d+$/.test(String(cik)))throw Error('Invalid CIK');
      let d;if(root.FFIPOMarket)d=await root.FFIPOMarket.load(path);else{const response=await fetch('data/ipo/'+path,{cache:'no-cache'});if(!response.ok)throw Error('No IPO snapshot published');d=await response.json();}if(!here())return;
      if(!cik&&root.FFIPOMarket)return root.FFIPOMarket.index(app,d,here);
      if(!cik){app.innerHTML=`<section class="section qi-section"><h1>IPO & prospectus analysis</h1><p>S-1, F-1, amendments and final prospectuses. Reviewed watchlist; coverage is not the full IPO market.</p>${(d.companies||[]).map(c=>`<article class="qi-card"><h2><a href="#ipo-${Number(c.cik)}">${esc(c.name)}</a></h2><p>${esc(c.form)} · Filed ${esc(c.filed)}</p><p>Operating costs · net income reconciliation · cash flow · quality measures</p></article>`).join('')||'<p>No reviewed filings available.</p>'}</section>`;return;}
      if(String(d.cik)!==String(cik))throw Error('Company mismatch');
      if(((d.charts||{}).periods||[]).some(p=>!p.error&&(p.nodes||[]).length))return company(app,d,here,cik);
      if(!(d.periods||[]).length&&d.reader)return unparsed(app,d,here,source(d.source_url));
      legacy(app,d,here,cik);
    }catch(e){if(here())app.innerHTML='<section class="section"><h1>IPO analysis unavailable</h1><p>The requested snapshot could not be loaded.</p><a href="#ipo">Return to IPO watchlist</a></section>';}
  }
  // the earlier view: a snapshot without charts (published before them), four reconciliation charts per period
  function legacy(app,d,here,cik) {
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
  }
  root.FFQualityIPO={quality,ipo,flow,charts,metricTable,_t:{tiles,periodGroups,costParts,costSVG,revenueSVG,ticks,usd,signed,growth}};
})(typeof window!=='undefined'?window:globalThis);
