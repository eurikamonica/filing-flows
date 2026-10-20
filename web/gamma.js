/* Gamma — every SEC SIC industry, descriptive growth conditions and evidenced
 * counterparties. Existing site data, no API key, no simulated consensus.
 */
(function (global) {
  'use strict';
  var STAGES = {unknown:'Insufficient history',expansion:'Expansion',
    deceleration:'Decelerating',mature:'Mature / stable',
    contraction:'Contraction',reacceleration:'Reaccelerating',
    transition:'Transition'};
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  }); };
  var num = function(x) { return x == null || !Number.isFinite(+x) ? '—' : (100*x >= 0 ? '+' : '')+(100*x).toFixed(1)+'%'; };
  var val = function(x) { return x == null || !Number.isFinite(+x) ? '—' : (100*x).toFixed(1)+'%'; };
  var money = function(x) { return x == null ? '—' : x>=1e12?'$'+(x/1e12).toFixed(2)+'T':x>=1e9?'$'+(x/1e9).toFixed(1)+'B':x>=1e6?'$'+(x/1e6).toFixed(0)+'M':'$'+Math.round(x).toLocaleString(); };
  var quant = function(a,p) {
    if (!a.length) return null;
    var b=a.slice().sort(function(x,y){return x-y;}), k=(b.length-1)*p, i=Math.floor(k), j=Math.ceil(k);
    return b[i]+(b[j]-b[i])*(k-i);
  };
  var stats = function(a) { return {n:a.length,p10:quant(a,.1),p25:quant(a,.25),median:quant(a,.5),p75:quant(a,.75),p90:quant(a,.9)}; };
  var safeGrowth = function(x) { return typeof x === 'number' && Number.isFinite(x); };
  var percentile = function(a,x) {
    return a.length ? 100*a.filter(function(v){return v<=x;}).length/a.length : null;
  };
  var COLORS = {expansion:'#17734a',reacceleration:'#207f9a',
    deceleration:'#b8860b',mature:'#64748b',contraction:'#b8432f',
    transition:'#8a4fbf',unknown:'#9a9893'};

  function histogram(data, expected, metric) {
    if (!data.length) return '<p class="muted">No comparable quarterly growth observations.</p>';
    var v=data.slice().sort(function(a,b){return a-b;});
    // Visual zoom only. Statistics below always use the untrimmed observations.
    var lo=Math.max(-1,quant(v,.02)-.04), hi=Math.min(5,quant(v,.98)+.04);
    if (hi-lo<.06) {lo-=.06;hi+=.06;}
    var bins=16, counts=new Array(bins).fill(0);
    v.forEach(function(x){counts[Math.max(0,Math.min(bins-1,Math.floor((x-lo)/(hi-lo)*bins)))]+=1;});
    var max=Math.max.apply(null,counts)||1, out='';
    counts.forEach(function(n,i){
      var x=42+i*34, h=112*n/max;
      out+='<rect x="'+x+'" y="'+(152-h).toFixed(1)+'" width="29" height="'+h.toFixed(1)+'" fill="#23765d" opacity=".78"><title>'+n+' observations</title></rect>';
    });
    var ticks=[lo,(lo+hi)/2,hi];
    ticks.forEach(function(n){
      var x=42+(n-lo)/(hi-lo)*bins*34;
      out+='<text x="'+x.toFixed(1)+'" y="173" text-anchor="middle" fill="currentColor" font-size="11">'+Math.round(100*n)+'%</text>';
    });
    if (safeGrowth(expected)) {
      var x=42+Math.max(0,Math.min(1,(expected-lo)/(hi-lo)))*bins*34;
      out+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="18" y2="152" stroke="#c4572e" stroke-width="3" stroke-dasharray="5 4"/>';
      out+='<text x="'+Math.max(72,Math.min(552,x)).toFixed(1)+'" y="15" text-anchor="middle" font-size="11" fill="#c4572e">Expected '+Math.round(100*expected)+'%</text>';
    }
    return '<svg class="gamma-hist" viewBox="0 0 628 188" role="img" aria-label="Distribution of observed '+esc(metric.toUpperCase())+' revenue growth"><line x1="42" x2="586" y1="152" y2="152" stroke="currentColor" opacity=".35"/>'+out+'</svg>';
  }

  async function index(app,ctx) {
    var here=ctx.live();
    ctx.setNav('gamma');
    app.innerHTML='<div class="loading">Loading SEC SIC industries…</div>';
    var d=await ctx.getJSON('gamma/index.json');
    if (!here()) return;
    var industries=d.industries||[], names=d.sector_names||{};
    app.innerHTML='<div class="page-head"><div class="eyebrow">Gamma / All industries</div>'+
      '<h1>Industry growth & supply–demand intelligence</h1>'+
      '<p class="intro">Browse every SIC sub-industry represented in Filing Flows SEC records. Company lifecycle is a transparent heuristic; industry distributions are historical descriptions, not analyst forecasts.</p>'+
      '<div class="meta"><span>'+industries.length+' SIC industries</span><span>'+d.universe+' companies with quarterly revenue</span><span>Data: '+esc((d.generated||'').slice(0,10))+'</span></div></div>'+
      '<div class="gamma-toolbar"><input id="gamma-query" type="search" placeholder="Find SIC, industry or company sector" aria-label="Filter industries">'+
      '<select id="gamma-sector" aria-label="Filter sector"><option value="">All sectors</option>'+
      Object.keys(names).map(function(k){return '<option value="'+esc(k)+'">'+esc(names[k])+'</option>';}).join('')+'</select></div>'+
      '<div id="gamma-list" class="gamma-list"></div>';
    function draw() {
      var q=document.getElementById('gamma-query').value.trim().toLowerCase();
      var sec=document.getElementById('gamma-sector').value;
      var rows=industries.filter(function(r){return (!sec||r.sector===sec) && (!q || (r.sic+' '+r.name+' '+(names[r.sector]||'')).toLowerCase().includes(q));});
      document.getElementById('gamma-list').innerHTML=rows.length ? rows.map(function(r){
        return '<a class="gamma-industry" href="#gamma-'+esc(r.sic)+'"><div class="gamma-name"><b>'+esc(r.name)+'</b>'+
          '<span>SIC '+esc(r.sic)+' · '+esc(names[r.sector]||r.sector)+'</span></div>'+
          '<div class="gamma-meta"><b>'+num(r.median_yoy)+'</b><span>Industry median YoY</span></div>'+
          '<div class="gamma-meta"><b>'+r.count+'</b><span>Companies · '+(r.observed||0)+' comparable</span></div></a>';
      }).join('') : '<p class="muted">No represented SIC industries match this filter.</p>';
    }
    document.getElementById('gamma-query').addEventListener('input',draw);
    document.getElementById('gamma-sector').addEventListener('change',draw);
    draw();
  }

  async function industry(app,sic,ctx) {
    var here=ctx.live();
    ctx.setNav('gamma');
    app.innerHTML='<div class="loading">Reading SIC '+esc(sic)+' growth distribution…</div>';
    var d=await ctx.getJSON('gamma/'+sic+'.json');
    if (!here()) return;
    var members=d.companies||[], stages=Object.keys(STAGES);
    app.innerHTML='<div class="page-head"><div class="crumbs"><a href="#gamma">Gamma</a><span>›</span>'+
      '<span>'+esc(d.sector)+'</span></div><div class="eyebrow">SEC SIC '+esc(d.sic)+'</div><h1>'+esc(d.name)+'</h1>'+
      '<div class="meta"><span>'+members.length+' companies</span><span>Comparable quarter: '+esc(d.period||'not available')+
      '</span><span>Growth based on filed quarterly revenue</span></div></div>'+
      '<section class="section"><div class="section-head"><h2>Conditional growth distribution</h2>'+
      '<span class="muted">Cross-sectional peers, not a fitted probability forecast</span></div>'+
      '<div class="gamma-toolbar"><label>Metric <select id="gmetric"><option value="yoy">Revenue YoY</option><option value="qoq">Revenue QoQ</option></select></label>'+
      '<label>Lifecycle <select id="gstage"><option value="">All stages</option>'+
      stages.map(function(k){return '<option value="'+esc(k)+'">'+esc(STAGES[k])+'</option>';}).join('')+'</select></label>'+
      '<label>Revenue size <select id="gsize"><option value="">All sizes</option><option value="small">Under $1B</option><option value="mid">$1B–$10B</option><option value="large">$10B+</option></select></label>'+
      '<label>Peer sample <select id="gsample"><option value="current">Comparable quarter</option><option value="historical">Historical pooled</option></select></label></div>'+
      '<div class="gamma-expect"><label for="gexpected">Expected growth (your scenario, %)</label><input type="number" id="gexpected" value="20" step="1" min="-100" max="1000">'+
      '<span class="muted small">Not analyst consensus. Enter the estimate you want to benchmark.</span></div>'+
      '<div id="gamma-stats"></div><div id="gamma-plot"></div><p class="muted small" id="gamma-method"></p></section>'+
      '<section class="section"><div class="section-head"><h2>Company growth & lifecycle</h2><span class="muted">Stage labels are rule-based diagnostics, not HMM estimates</span></div>'+
      '<div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Quarter end</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Q/Q</th><th>Stage</th></tr></thead><tbody id="gamma-companies"></tbody></table></div></section>'+
      '<section class="section"><div class="section-head"><h2>Reported supplier & customer relationships</h2>'+
      '<span class="muted">Only named links already recognized by Filing Flows Chains</span></div>'+
      '<div id="gamma-relations"></div></section>'+
      '<details class="section method-note"><summary>Methods, coverage and limitations</summary>'+
      '<p>Primary grouping: SEC SIC, not GICS or proprietary themes. Same-calendar-quarter observations and historical pooled observations are separate. Positive revenue denominators, approximately three-month and year-apart comparable periods are required. No assumption of normality.</p>'+
      '<p>Lifecycle is classified from revenue growth, relative industry growth and acceleration; financial quality, macro conditions and state transition probabilities are not yet estimated.</p>'+
      '<p>Peer percentile is empirical and does not give the likelihood of meeting expected revenue. Each company contributes several correlated observations to historical pooled samples.</p>'+
      '<p>Relationships are only those supported by named customers in Chains excerpts. Chains allocations may themselves be modeled; these are not verified invoices. Missing links mean not mapped, not absence of a commercial relationship. Broader networks require additional SEC text extraction and entity-resolution evidence.</p></details>';
    var get=function(id){return document.getElementById(id);};
    function matching(m) {
      var stage=get('gstage').value, size=get('gsize').value, rev=+m.revenue_usd;
      return (!stage||m.stage===stage) && (!size || (size==='small'&&rev<1e9) ||
        (size==='mid'&&rev>=1e9&&rev<1e10) || (size==='large'&&rev>=1e10));
    }
    function observations(m,metric,pool) {
      if (pool==='historical') return (m.history||[]).map(function(r){return r[metric];}).filter(safeGrowth);
      return m.current && safeGrowth(m.current[metric]) ? [m.current[metric]] : [];
    }
    function draw() {
      var metric=get('gmetric').value, pool=get('gsample').value;
      var chosen=members.filter(matching), all=chosen.flatMap(function(m){return observations(m,metric,pool);});
      var fallback='';
      if (all.length<5 && chosen.length<members.length) {
        all=members.flatMap(function(m){return observations(m,metric,pool);});
        fallback='Too few matching peers; showing the full SIC industry instead.';
      }
      var s=stats(all), expected=+get('gexpected').value/100;
      var ready=all.length>=5 && safeGrowth(expected);
      var rank=ready?percentile(all,expected):null;
      get('gamma-stats').innerHTML='<div class="gamma-cards">'+
        [['Observations',String(s.n)],['P10',val(s.p10)],['Median',val(s.median)],
          ['P90',val(s.p90)],['Expected percentile',rank==null?'Insufficient':rank.toFixed(1)+'%']].map(function(z){
            return '<div class="gamma-card"><span>'+z[0]+'</span><strong>'+z[1]+'</strong></div>';
          }).join('')+'</div>';
      get('gamma-plot').innerHTML=histogram(all,Number.isFinite(expected)?expected:null,metric);
      get('gamma-method').textContent=(fallback?fallback+' ':'')+
        (s.n<5?'Fewer than 5 observations: no percentile is reported. ':'')+
        (pool==='historical'?'Historical pooled observations are serially correlated, and do not constitute independent predictions. ':
          'One observation per company from the selected comparable calendar quarter. ')+
        (metric==='qoq'?'QoQ may reflect fiscal seasonality; compare similar quarter positions. ':'')+
        'Percentile is the share of observed peer growth rates at or below your entered scenario.';
      get('gamma-companies').innerHTML=members.filter(matching).map(function(m){
        var c=m.current||{};
        return '<tr><td><a href="#c-'+encodeURIComponent(m.cik)+'"><b>'+esc(m.ticker||m.name)+'</b></a> '+
          '<span class="muted small">'+esc(m.name)+'</span></td><td>'+esc(c.end||m.end||'—')+
          '</td><td class="num">'+money(m.revenue_usd)+'</td>'+
          '<td class="num">'+num(c.yoy)+'</td><td class="num">'+num(c.qoq)+
          '</td><td><span class="gamma-stage" style="border-color:'+COLORS[m.stage]+'">'+esc(STAGES[m.stage]||m.stage)+'</span></td></tr>';
      }).join('')||'<tr><td colspan="6">No companies match the selected filters.</td></tr>';
    }
    ['gmetric','gstage','gsize','gsample','gexpected'].forEach(function(id){
      get(id).addEventListener(id==='gexpected'?'input':'change',draw);
    });
    draw();
    var edges=d.relationships||[];
    get('gamma-relations').innerHTML=edges.length ?
      '<div class="gamma-network">'+edges.map(function(e){
        return '<div class="gamma-edge"><a href="#t-'+encodeURIComponent(e.supplier)+'">'+esc(e.supplier)+'</a>'+
          '<span class="gamma-arrow">supplies →</span>'+
          '<a href="#t-'+encodeURIComponent(e.customer)+'">'+esc(e.customer)+'</a>'+
          '<span class="muted small">'+esc(e.note||'Named customer')+
          ' · <a href="#chain-'+esc(e.chain)+'">Chain evidence ↗</a></span></div>';
      }).join('')+'</div>' :
      '<p class="muted">No named counterparty links currently mapped in the existing Chains records for this SIC. This is a disclosure-coverage gap, not proof that companies have no suppliers or customers.</p>';
  }
  global.FFGamma={index:index,industry:industry};
})(window);
