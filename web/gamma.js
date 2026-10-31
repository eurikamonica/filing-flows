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
  // PNG / JPG / post bar under a chart (disclosures/chart-share.js, loaded once on demand)
  var shareP=null;
  function withShare(fn){
    if(global.FFShare){fn(global.FFShare);return;}
    if(!shareP)shareP=new Promise(function(res){var sc=document.createElement('script');sc.src='disclosures/chart-share.js';sc.onload=function(){res(global.FFShare||null);};sc.onerror=function(){res(null);};document.head.appendChild(sc);});
    shareP.then(function(S){if(S)fn(S);});
  }
  var pctOf = function(v,t){return t?Math.round(100*v/t)+'%':'—';};
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


  // Relationship visualizations share Gamma's existing SIC members and Chains edges.
  // No relationship width is inferred from revenue: only explicit value_usd is weighted.
  function relationshipExplorer(root, edges, members, sicCode) {
    var byId={}, byName={};
    members.forEach(function(m){
      if(m.cik) byId[String(m.cik)]=m;
      if(m.name) byName[m.name.toLowerCase()]=m;
    });
    function label(e,role) { return String(e[role]||e[role+'_cik']||'Unknown'); }
    function key(e,role) { return String(e[role+'_cik']||label(e,role).toLowerCase()); }
    function company(k,name) { return byId[k]||byName[String(name||'').toLowerCase()]; }
    function nodeLink(k) { return /^\\d+$/.test(k) ? '#c-'+encodeURIComponent(k) : null; }
    function evidence(e) {
      var s=String(e.evidence_level|| (e.chain?'Chains mapping':'Reported relationship'));
      return s;
    }
    var toolbar='<div class="gamma-toolbar" role="group" aria-label="Relationship visualization">'+
      '<button type="button" class="gamma-view-btn" data-view="network">Network Graph</button>'+
      '<button type="button" class="gamma-view-btn" data-view="flow">Money Flow</button>'+
      '<button type="button" class="gamma-view-btn" data-view="industry">Industry Map</button></div>'+
      '<p class="muted small" id="gamma-relationship-caption"></p><div id="gamma-relationship-canvas"></div>';
    root.innerHTML=toolbar;
    var canvas=root.querySelector('#gamma-relationship-canvas'), caption=root.querySelector('#gamma-relationship-caption');
    var controls=Array.from(root.querySelectorAll('.gamma-view-btn'));
    var svgEsc=esc;
    function wrapSVG(inner,h) {
      return '<div style="overflow-x:auto"><svg viewBox="0 0 960 '+h+'" width="100%" style="min-width:520px;max-height:740px;background:var(--card-bg,#fff);border:1px solid var(--border,#ddd);border-radius:12px" role="img" aria-label="Gamma relationship visualization">'+inner+'</svg></div>';
    }
    function network(){
      if(!edges.length){
        caption.textContent='No mapped counterparties for this SIC. Missing edges are a coverage gap, not evidence of no relationship.';
        canvas.innerHTML='<p class="muted">No named supplier/customer links are available. Switch to Industry Map to explore SEC industry members.</p>';
        return;
      }
      var nodes=new Map();
      edges.forEach(function(e){
        [['supplier','#2563a6'],['customer','#147d62']].forEach(function(d){
          var k=key(e,d[0]);if(!nodes.has(k))nodes.set(k,{key:k,name:label(e,d[0]),color:d[1]});
        });
      });
      var suppliers=new Set(edges.map(function(e){return key(e,'supplier');}));
      var customers=new Set(edges.map(function(e){return key(e,'customer');}));
      var left=[],mid=[],right=[];
      nodes.forEach(function(n){(suppliers.has(n.key)&&customers.has(n.key)?mid:suppliers.has(n.key)?left:right).push(n);});
      [left,mid,right].forEach(function(a){a.sort(function(x,y){return x.name.localeCompare(y.name);});});
      var maxRows=Math.max(left.length,mid.length,right.length,1),height=Math.max(320,maxRows*62+85);
      var positions={};
      [left,mid,right].forEach(function(group,col){
        group.forEach(function(n,i){positions[n.key]={x:[40,355,670][col],y:56+i*(height-110)/Math.max(1,group.length-1)};});
      });
      var html='<defs><marker id="gamma-rel-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#8090a0" stroke-width="1.5"/></marker></defs>';
      edges.forEach(function(e){
        var a=positions[key(e,'supplier')],b=positions[key(e,'customer')]; if(!a||!b)return;
        var x1=a.x+245,x2=b.x,y1=a.y+17,y2=b.y+17;
        var same=x2<=x1;
        var path=same?'M'+x1+' '+y1+' C'+(x1+55)+' '+(y1-45)+' '+(x2-55)+' '+(y2-45)+' '+x2+' '+y2:
          'M'+x1+' '+y1+' C'+(x1+Math.max(20,(x2-x1)/2))+' '+y1+' '+(x2-Math.max(20,(x2-x1)/2))+' '+y2+' '+x2+' '+y2;
        html+='<path d="'+path+'" fill="none" stroke="#8a9bac" stroke-width="1.8" opacity=".62" marker-end="url(#gamma-rel-arrow)"><title>'+svgEsc(label(e,'supplier')+' → '+label(e,'customer')+' | '+evidence(e)+(e.note?' | '+e.note:''))+'</title></path>';
      });
      nodes.forEach(function(n){
        var p=positions[n.key], url=nodeLink(n.key);
        var card='<rect width="245" height="35" rx="7" fill="'+n.color+'" fill-opacity=".12" stroke="'+n.color+'" stroke-opacity=".5"/>'+
          '<text x="12" y="22" fill="currentColor" font-size="13" font-weight="600">'+svgEsc(n.name.length>30?n.name.slice(0,28)+'…':n.name)+'</text><title>'+svgEsc(n.name)+'</title>';
        html+='<g transform="translate('+p.x+' '+p.y+')">'+(url?'<a href="'+url+'">'+card+'</a>':card)+'</g>';
      });
      caption.textContent=edges.length+' mapped relationships · '+nodes.size+' entities · Arrow indicates supplier → customer. Edge width is deliberately not monetary. Hover edges for evidence.';
      canvas.innerHTML=wrapSVG(html,height)+references();
    }
    function references() {
      return '<details class="method-note"><summary>Mapped relationships & evidence ('+edges.length+')</summary>'+
        '<div class="gamma-network">'+edges.map(function(e){
          var src=e.source_url && /^https:\/\//i.test(e.source_url)?' · <a target="_blank" rel="noopener noreferrer" href="'+esc(e.source_url)+'">Source ↗</a>':
            e.chain?' · <a href="#chain-'+encodeURIComponent(e.chain)+'">Chains ↗</a>':'';
          return '<div class="gamma-edge">'+esc(label(e,'supplier'))+' <span class="gamma-arrow">supplies →</span> '+
          esc(label(e,'customer'))+' <span class="muted small">'+esc(evidence(e))+
          (e.note?' · '+esc(e.note):'')+src+'</span></div>';
        }).join('')+'</div></details>';
    }
    function flow() {
      var weighted=edges.filter(function(e){return Number.isFinite(+e.value_usd)&&+e.value_usd>0 && e.value_usd!==null && e.value_usd!=='';});
      if(!weighted.length){
        caption.textContent='No verified or explicitly estimated relationship amounts in the current Gamma data.';
        canvas.innerHTML='<p class="muted">Money Flow is unavailable for this SIC: existing supplier/customer links do not provide usable USD transaction amounts. No synthetic widths are drawn.</p>'+references();
        return;
      }
      if(global.FFChains&&global.Sankey){                  // a real money flow: suppliers -> customers, widths in dollars
        var top=weighted.slice().sort(function(a,b){return (+b.value_usd)-(+a.value_usd);}).slice(0,40);
        var nd=new Map(), lk=[], inSic=function(k){return !!byId[k];};
        top.forEach(function(e){
          var a='s:'+key(e,'supplier'), b='c:'+key(e,'customer');
          if(!nd.has(a))nd.set(a,{id:a,col:0,label:label(e,'supplier'),v:0,color:inSic(String(e.supplier_cik||''))?'#2f6db0':'#7d93ab',cik:e.supplier_cik});
          if(!nd.has(b))nd.set(b,{id:b,col:1,label:label(e,'customer'),v:0,color:inSic(String(e.customer_cik||''))?'#1f8a5b':'#7fae96',cik:e.customer_cik});
          nd.get(a).v+=+e.value_usd; nd.get(b).v+=+e.value_usd;
          lk.push({s:a,t:b,v:+e.value_usd,k:1});
        });
        var total=top.reduce(function(x,e){return x+(+e.value_usd);},0);
        var scene=global.FFChains.layout({cols:[{id:'s',name:'Suppliers'},{id:'c',name:'Customers'}],nodes:Array.from(nd.values()),links:lk},{
          title:'Who pays whom — named customers',subtitle:money(total)+' across '+top.length+' stated links'+(weighted.length>top.length?' (largest '+top.length+' of '+weighted.length+')':''),
          footer:['Source: SEC EDGAR annual reports. Each band = the share of the supplier’s revenue its filing says came from the customer × that revenue. Darker: companies in this SIC.',
            'Figures are read automatically and can contain errors; check the filings before relying on them. Not investment advice.']});
        caption.textContent='Dollars stated (share × revenue) in the suppliers’ annual reports; only customers above the ~10% disclosure threshold appear.';
        canvas.innerHTML='<div class="gamma-share"></div><div class="net-chart">'+global.Sankey.toSVG(scene,'SIC money flow')+'</div>'+references();
        var named=top.slice(0,5);
        withShare(function(S){var el=canvas.querySelector('.gamma-share');if(!el)return;
          el.innerHTML=S.bar({key:'sic-'+(sicCode||'x')+'-named-flow',title:'Who pays whom — named customers',scene:function(){return scene;},post:function(){
            var pairs=named.map(function(e){return label(e,'supplier')+' → '+label(e,'customer')+' '+money(+e.value_usd);});
            return {title:'Who pays whom — named customers'+(sicCode?' (SIC '+sicCode+')':''),
              paras:[money(total)+' of stated customer revenue across '+top.length+' links, read from the suppliers\u2019 annual reports (each band = the customer\u2019s share of revenue × that revenue).',
                'Largest: '+pairs.join('; ')+'.','Only customers above the ~10% disclosure threshold appear; figures are read automatically from SEC filings.'],
              lines:['Who pays whom'+(sicCode?' in SIC '+sicCode:'')+': '+money(total)+' of stated customer revenue.'].concat(named.slice(0,3).map(function(e){return label(e,'supplier')+' → '+label(e,'customer')+': '+money(+e.value_usd)+'.';})).concat(['From 10-K customer disclosures.'])};}});});
        return;
      }
      var rows=weighted.slice().sort(function(a,b){return (+b.value_usd)-(+a.value_usd);}).slice(0,25);
      var max=Math.max.apply(null,rows.map(function(e){return +e.value_usd;}));
      var height=Math.max(280,rows.length*43+65);
      var html='<text x="20" y="28" font-size="14" fill="currentColor">Supplier</text><text x="690" y="28" font-size="14" fill="currentColor">Customer</text>';
      rows.forEach(function(e,i){
        var y=54+i*43,w=2+20*Math.sqrt(+e.value_usd/max);
        var estimate=/estimat|model|assum|infer/i.test(e.evidence_level||e.value_type||'');
        html+='<path d="M250 '+y+' C400 '+y+' 565 '+y+' 695 '+y+'" fill="none" stroke="'+(estimate?'#d18c47':'#25866c')+'" stroke-width="'+w.toFixed(2)+'" opacity=".57"><title>'+svgEsc(evidence(e)+' · '+money(+e.value_usd))+'</title></path>'+
          '<text x="20" y="'+(y+4)+'" font-size="12" fill="currentColor">'+svgEsc(label(e,'supplier').slice(0,31))+'</text>'+
          '<text x="710" y="'+(y+4)+'" font-size="12" fill="currentColor">'+svgEsc(label(e,'customer').slice(0,28))+'</text>';
      });
      caption.textContent='USD values from mapped relationships only. Green = reported/identified; amber = estimated/model-based. Width ∝ square root of supplied value (visual scaling); not a conservation-balanced Sankey.';
      canvas.innerHTML=wrapSVG(html,height)+references();
    }
    function industryMap(){
      var rows=members.slice().sort(function(a,b){return (+b.revenue_usd||0)-(+a.revenue_usd||0);}).slice(0,80);
      if(!rows.length){canvas.innerHTML='<p class="muted">No mapped SEC companies in this SIC.</p>';return;}
      var total=rows.reduce(function(s,m){return s+Math.max(0,+m.revenue_usd||0);},0);
      var max=Math.max.apply(null,rows.map(function(m){return +m.revenue_usd||0;}))||1;
      var h=rows.length*38+54,svg='<text x="18" y="25" font-size="14" fill="currentColor">Companies by reported quarterly revenue · same SIC (not supply-chain transaction size)</text>';
      rows.forEach(function(m,i){
        var y=44+i*38,w=+m.revenue_usd>0?Math.max(4,600*(+m.revenue_usd)/max):0;
        var link=m.cik?'#c-'+encodeURIComponent(m.cik):null;
        var r='<rect x="266" y="'+y+'" width="'+w+'" height="24" rx="4" fill="'+(COLORS[m.stage]||COLORS.unknown)+'" opacity=".79"/>'+
          '<text x="14" y="'+(y+17)+'" font-size="13" fill="currentColor">'+svgEsc(String(m.ticker||m.name||'Unknown').slice(0,28))+'</text>'+
          '<text x="'+Math.min(880,282+w)+'" y="'+(y+17)+'" font-size="12" fill="currentColor">'+svgEsc(money(m.revenue_usd))+'</text>';
        svg+=link?'<a href="'+link+'">'+r+'</a>':r;
      });
      caption.textContent='SIC peer companies ordered by available quarterly revenue. Bars are scaled to the largest company; fiscal reporting dates may differ. Colors denote Gamma lifecycle heuristics.';
      canvas.innerHTML=wrapSVG(svg,h);
    }
    var views={network:network,flow:flow,industry:industryMap};
    function select(v) {
      controls.forEach(function(b){var active=b.dataset.view===v;b.setAttribute('aria-pressed',String(active));b.style.cssText='cursor:pointer;padding:8px 12px;border:1px solid #a7b2bc;border-radius:7px;background:'+(active?'#184a68':'transparent')+';color:'+(active?'white':'inherit');});
      views[v]();
    }
    controls.forEach(function(btn){btn.addEventListener('click',function(){select(btn.dataset.view);});});
    select(edges.length?'network':'industry');
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
      '<p class="muted">Each industry page has an <b>estimated money flow</b> (BEA input-output): where the industry\u2019s money comes from, what it buys, from which industries and listed companies.</p>'+
      '<p class="muted"><a href="supplier-revenue/">Supplier Revenue Forecast &rarr;</a> &nbsp;&middot;&nbsp; <a href="integration-health/">Collection and publication health &rarr;</a></p>'+
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
      '</span><span>Growth based on filed quarterly revenue</span></div>'+
      '<div class="fresh">Latest comparable quarter: <b>'+esc(d.period||'not available')+'</b> · industry data rebuilt '+esc((d.generated||'').slice(0,10))+(d.generated&&d.generated.length>15?', '+esc(d.generated.slice(11,16))+' UTC':'')+'</div></div>'+
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
      '<section class="section" id="gamma-model" hidden></section>'+
      '<section class="section"><div class="section-head"><h2>Estimated money flow (BEA input-output)</h2>'+
      '<span class="muted">Every number an estimate at industry-average precision</span></div><div id="gamma-io"></div></section>'+
      '<section class="section"><div class="section-head"><h2>Money flow lab <span class="fl-beta">Beta</span></h2>'+
      '<span class="muted">Experimental: the chart above corrected, the filed cash flow, pay followed to households, two tiers of suppliers, capital spending by asset</span></div><div id="gamma-lab"></div></section>'+
      '<section class="section"><div class="section-head"><h2>Reported supplier & customer relationships</h2>'+
      '<span class="muted">Customers and suppliers named in annual reports (10-K, 20-F)</span></div>'+
      '<div id="gamma-relations"></div></section>'+
      '<details class="section method-note"><summary>Methods, coverage and limitations</summary>'+
      '<p>Primary grouping: SEC SIC, not GICS or proprietary themes. Same-calendar-quarter observations and historical pooled observations are separate. Positive revenue denominators, approximately three-month and year-apart comparable periods are required. No assumption of normality.</p>'+
      '<p>Lifecycle is classified from revenue growth, relative industry growth and acceleration; financial quality, macro conditions and state transition probabilities are not yet estimated.</p>'+
      '<p>Peer percentile is empirical and does not give the likelihood of meeting expected revenue. Each company contributes several correlated observations to historical pooled samples.</p>'+
      '<p>Relationships are customers and suppliers a company names in its annual report (a sentence such as “Walmart accounted for 16% of net sales”, a customer table, or XBRL concentration facts), matched to SEC registrants by exact name. Money Flow widths are the stated share × the supplier’s revenue for that year. Companies disclose customers above about 10% of revenue, so coverage is partial: a missing link means not disclosed or not matched, not the absence of a relationship.</p></details>';
    if(global.FFModel)global.FFModel.industry(document.getElementById('gamma-model'),sic);
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
      var peerCount=chosen.filter(function(m){return observations(m,metric,pool).length>0;}).length;
      var fallback='';
      if (peerCount<5 && chosen.length<members.length) {
        all=members.flatMap(function(m){return observations(m,metric,pool);});
        peerCount=members.filter(function(m){return observations(m,metric,pool).length>0;}).length;
        fallback='Fewer than five matching companies; showing the full SIC industry instead.';
      }
      var s=stats(all), expected=+get('gexpected').value/100;
      var ready=all.length>=5 && peerCount>=5 && safeGrowth(expected);
      var rank=ready?percentile(all,expected):null;
      get('gamma-stats').innerHTML='<div class="gamma-cards">'+
        [['Observations',String(s.n)],['P10',val(s.p10)],['Median',val(s.median)],
          ['P90',val(s.p90)],['Expected percentile',rank==null?'Insufficient':rank.toFixed(1)+'%']].map(function(z){
            return '<div class="gamma-card"><span>'+z[0]+'</span><strong>'+z[1]+'</strong></div>';
          }).join('')+'</div>';
      get('gamma-plot').innerHTML=histogram(all,Number.isFinite(expected)?expected:null,metric);
      get('gamma-method').textContent=(fallback?fallback+' ':'')+
        (s.n<5||peerCount<5?'Fewer than five contributing companies or observations: no percentile is reported. ':'')+
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
    relationshipExplorer(get('gamma-relations'),d.relationships||[],members,d.sic);
    ioFlow(get('gamma-io'),ctx,here,d.sic,d.sector);
    if(global.FFFlowLab)global.FFFlowLab.industry(get('gamma-lab'),{sic:d.sic,sector:d.sector,here:here});
  }

  // Estimated money flow: where the industry's money comes from, what it spends it on, which industries supply it and
  // which listed companies are in those industries — BEA's input-output tables applied to the members' reported figures
  // (pipeline/ioflow.py; data gamma/io/<sic | sic2-NN | sector-id>.json)
  function ioPost(d,inV){                                // the estimated flow as an analysis and a post for X
    var T=d.totals||{},rev=d.revenue||0;
    var sup=d.nodes.filter(function(n){return n.col===3&&n.cik;}).map(function(n){return [n.label,inV[n.id]||0];}).sort(function(a,b){return b[1]-a[1];}).slice(0,4);
    var bea=(d.bea||[]).slice(0,3).map(function(b){return b[1]+' '+Math.round(100*b[2])+'%';});
    var uses=[['purchased inputs',T.purchases],['employees',T.employees],['capital spending',T.capex],['imports (of these)',T.imports],['operating cash left',(T.left||0)+(T.finleft||0)]].filter(function(z){return z[1]>0;});
    return {title:'Estimated money flow — '+d.title,
      paras:[d.title+': '+money(rev)+' of revenue over the last four quarters across '+d.companies+' companies.',
        'Where it goes (estimated): '+uses.map(function(z){return z[0]+' '+money(z[1])+' ('+pctOf(z[1],rev)+')';}).join(', ')+'.',
        bea.length?'Industry mix behind the split: '+bea.join(', ')+'.':'',
        sup.length?'Largest listed suppliers by estimated share of this spending: '+sup.map(function(z){return z[0]+' '+money(z[1]);}).join(', ')+' — industry averages, not any company\u2019s actual purchases.':'',
        'Spending split by BEA input-output ('+d.source.io_year+' Use table, scaled to '+d.source.scale_year+'); revenue and operating figures from SEC filings.'],
      lines:['Where '+d.title+'\u2019s '+money(rev)+' goes (4Q, est.):'].concat(uses.slice(0,3).map(function(z){return z[0]+' '+money(z[1])+' ('+pctOf(z[1],rev)+')';}).join(' · '))
        .concat(sup.length?['Top listed suppliers (est.): '+sup.slice(0,3).map(function(z){return z[0];}).join(', ')+'.']:[]).concat(['BEA input-output estimate.'])};
  }
  function ioFlow(root,ctx,here,sic,sector){
    if(!root)return;
    var levels=[['industry','This industry (SIC '+sic+')',sic],['major','Major group (SIC '+String(sic).slice(0,2)+')','sic2-'+String(sic).slice(0,2)]];
    if(sector)levels.push(['sector','Sector','sector-'+sector]);
    root.innerHTML='<div class="gamma-toolbar" role="group" aria-label="Level">'+levels.map(function(l){
      return '<button type="button" class="gamma-view-btn" data-io="'+esc(l[2])+'">'+esc(l[1])+'</button>';}).join('')+'</div>'+
      '<p class="muted small" id="gamma-io-cap"></p><div id="gamma-io-share"></div><div id="gamma-io-chart"></div><div id="gamma-io-more"></div>';
    var btns=Array.from(root.querySelectorAll('[data-io]')), chart=root.querySelector('#gamma-io-chart'),
      cap=root.querySelector('#gamma-io-cap'), more=root.querySelector('#gamma-io-more');
    async function show(key){
      btns.forEach(function(b){var on=b.dataset.io===key;b.setAttribute('aria-pressed',String(on));
        b.style.cssText='cursor:pointer;padding:8px 12px;border:1px solid #a7b2bc;border-radius:7px;background:'+(on?'#184a68':'transparent')+';color:'+(on?'white':'inherit');});
      chart.innerHTML='<p class="muted">Loading the estimate…</p>';more.innerHTML='';cap.textContent='';
      var d;
      try{d=await ctx.getJSON('gamma/io/'+key+'.json');}catch(e){d=null;}
      if(!here())return;
      if(!d||!(d.links||[]).length){chart.innerHTML='<p class="muted">No estimate for this level: its companies do not yet have four quarters of revenue and operating income, or their SIC code has no BEA industry.</p>';return;}
      var inV={},outV={};
      d.links.forEach(function(l){outV[l[0]]=(outV[l[0]]||0)+l[2];inV[l[1]]=(inV[l[1]]||0)+l[2];});
      var nodes=d.nodes.map(function(n){return {id:n.id,col:n.col,label:n.label,t:n.label,v:Math.max(inV[n.id]||0,outV[n.id]||0),color:n.color,cik:n.cik};})
        .filter(function(n){return n.v>0;});
      var links=d.links.map(function(l){return {s:l[0],t:l[1],v:l[2],k:0.22};});
      var T=d.totals||{};
      if(global.FFChains&&global.Sankey){
        var scene=global.FFChains.layout({cols:d.cols.map(function(c,i){return {id:'c'+i,name:c};}),nodes:nodes,links:links},{
          title:'Estimated money flow — '+d.title,
          subtitle:money(d.revenue)+' revenue over the last four quarters · '+d.companies+' companies · all figures estimated',
          footer:['Estimate. Spending split by BEA input-output ('+d.source.io_year+' Use table, scaled to '+d.source.scale_year+') and capital spending by BEA fixed assets; listed suppliers by revenue share of their industry.',
            'Industry averages, not any company\u2019s actual purchases. Figures are read automatically from SEC filings; not investment advice.']});
        chart.innerHTML='<div class="net-chart gamma-io-est">'+global.Sankey.toSVG(scene,'Estimated money flow')+'</div>';
        withShare(function(S){var el=root.querySelector('#gamma-io-share');if(!el||!here())return;
          el.innerHTML=S.bar({key:'io-'+key,title:'Estimated money flow — '+d.title,scene:function(){return scene;},post:function(){return ioPost(d,inV);}});});
      } else chart.innerHTML='<p class="muted">The chart library did not load.</p>';
      cap.textContent='Light colours: estimated. Columns: member companies\u2019 revenue (and borrowing where they spent more) → what they spend it on → the industries that supply it (BEA) → listed companies in those industries.';
      var sup=d.nodes.filter(function(n){return n.col===3&&n.cik;}).map(function(n){return [n,inV[n.id]||0];}).sort(function(a,b){return b[1]-a[1];});
      var bea=(d.bea||[]).map(function(b){return esc(b[1])+' '+Math.round(100*b[2])+'%';}).join(' · ');
      var notes=[];
      if(d.financial&&d.financial.length)notes.push('Lenders and insurers: '+d.financial.map(esc).join('; ')+' (their revenue less income is mostly interest or claims paid, not purchases).');
      if(d.partial_n)notes.push(d.partial_n+' of '+d.companies+' companies with a gap: '+d.partial.map(esc).join(', ')+'.');
      more.innerHTML='<div class="gamma-cards">'+[['Purchased inputs',T.purchases],['Capital spending',T.capex],['Employees',T.employees],['Imports (of the above)',T.imports],['Operating cash left',(T.left||0)+(T.finleft||0)]]
        .map(function(z){return '<div class="gamma-card"><span>'+z[0]+'</span><strong>'+money(z[1])+'</strong></div>';}).join('')+'</div>'+
        (sup.length?'<div class="tbl-wrap"><table><thead><tr><th>Listed supplier (estimated)</th><th class="num">Share of this spending</th></tr></thead><tbody>'+
          sup.map(function(r){return '<tr><td><a href="#c-'+encodeURIComponent(r[0].cik)+'"><b>'+esc(r[0].label)+'</b></a></td><td class="num">'+money(r[1])+'</td></tr>';}).join('')+'</tbody></table></div>':'')+
        '<details class="method-note"><summary>How this is estimated</summary>'+
        '<p><b>Industry mix:</b> '+bea+'. Each company\u2019s SIC code is matched to BEA\u2019s detail industries (1987 SIC → 2017 NAICS → BEA).</p>'+
        '<p><b>Spending:</b> revenue − operating income − D&amp;A over the last four quarters, split into purchased inputs, employees and taxes on production as BEA\u2019s Use table splits the industry\u2019s spending; purchased inputs go to the supplying industries in the industry\u2019s input mix, the imported share of each product to Imports. Capital spending follows the industry\u2019s own asset mix ('+esc(d.source.capex||'BEA fixed assets')+').</p>'+
        '<p><b>Listed suppliers:</b> within a supplying industry, each listed company mapped to it gets its revenue ÷ the industry\u2019s US gross output; when listed companies\u2019 revenue is larger (much of it is sold abroad) the industry\u2019s share is split among them by revenue alone; the rest is Unlisted &amp; private.</p>'+
        (notes.length?'<p>'+notes.join(' ')+'</p>':'')+
        '<p>Sources: <a href="https://www.bea.gov/industry/input-output-accounts-data" target="_blank" rel="noopener">BEA input-output accounts</a>, <a href="https://apps.bea.gov/national/FA2004/Details/Index.htm" target="_blank" rel="noopener">BEA fixed assets</a>, Census SIC/NAICS concordances, SEC filings.</p></details>';
    }
    btns.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.io);});});
    show(levels[0][2]);
  }
  global.FFGamma={index:index,industry:industry};
})(window);
