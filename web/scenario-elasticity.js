/* Scenario elasticity: revenue growth, not stock-return beta or a price target.
 * All inputs are deviations from the existing one-quarter model forecast.
 */
(function (global) {
  'use strict';

  function finite(x) { return typeof x === 'number' && Number.isFinite(x); }
  function calc(f, s) {
    if (!finite(f.stockBeta) || !finite(f.baseGrowth) || f.baseGrowth <= -1) return {error:'Company growth model unavailable'};
    var marketOK = finite(f.industryBeta) && finite(f.sectorBeta);
    if (!marketOK && s.marketPP !== 0) return {error:'Market transmission is unavailable for this company'};
    var out = {
      market: marketOK ? f.stockBeta * f.industryBeta * f.sectorBeta * s.marketPP : 0,
      industry: f.stockBeta * s.industryPP,
      gdp: s.gdpPP * s.gdpCoef,
      yield: s.yieldBP / 100 * s.yieldCoef
    };
    if (!Object.keys(out).every(function(k){return finite(out[k]);})) return {error:'Check numeric inputs'};
    var changePP = out.market + out.industry + out.gdp + out.yield;
    var newGrowth = f.baseGrowth + changePP / 100;
    var baseRevenue = finite(f.baseRevenue) && f.baseRevenue > 0 ? f.baseRevenue : null;
    var newRevenue = baseRevenue !== null && newGrowth > -1 ?
      baseRevenue * (1 + newGrowth) / (1 + f.baseGrowth) : null;
    return {components:out, changePP:changePP, growth:newGrowth,
      baseGrowth:f.baseGrowth, baseRevenue:baseRevenue,
      revenue:newRevenue, deltaRevenue:newRevenue === null ? null : newRevenue - baseRevenue,
      marketBeta:marketOK ? f.stockBeta * f.industryBeta * f.sectorBeta : null};
  }
  function esc(x) {
    return String(x == null ? '' : x).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function pp(x) { return (x >= 0 ? '+' : '') + x.toFixed(2) + ' pp'; }
  function pct(x) { return (100*x).toFixed(2) + '%'; }
  function usd(x) {
    if (!finite(x)) return '—';
    var a = Math.abs(x), sign = x < 0 ? '−' : '';
    if (a >= 1e12) return sign + '$' + (a/1e12).toFixed(2) + 'T';
    if (a >= 1e9) return sign + '$' + (a/1e9).toFixed(2) + 'B';
    if (a >= 1e6) return sign + '$' + (a/1e6).toFixed(1) + 'M';
    return sign + '$' + Math.round(a).toLocaleString('en-US');
  }
  function control(key, title, unit, initial, step, note) {
    return '<label style="display:flex;flex-direction:column;gap:4px;min-width:135px;flex:1">' +
      '<span class="small">' + esc(title) + '</span><span><input type="number" data-scenario="' + key +
      '" value="' + initial + '" step="' + step + '" style="max-width:115px"> ' + esc(unit) + '</span>' +
      (note ? '<span class="muted small">' + esc(note) + '</span>' : '') + '</label>';
  }
  function company(box, d, get) {
    if (!box || !d || !d.model || !(d.fc && d.fc[0])) return;
    var f0 = d.fc[0], stockBeta = d.model.gamma;
    if (!finite(stockBeta) || !finite(f0[1])) return;
    Promise.resolve(get('model/index.json')).then(function(ix) {
      if (!box.isConnected) return;
      var sector = ix && (ix.sectors || []).find(function(x){return x.id === d.sector;});
      var f = {stockBeta:stockBeta,
        industryBeta:d.industry_model && d.industry_model.gamma,
        sectorBeta:sector && sector.model && sector.model.gamma,
        baseGrowth:f0[1], baseRevenue:f0[2]};
      var marketReady = finite(f.industryBeta) && finite(f.sectorBeta);
      var root = document.createElement('section');
      root.className = 'section';
      root.setAttribute('aria-label','Stock revenue scenario and elasticity');
      root.innerHTML =
        '<div class="section-head"><h2>Stock revenue scenario &amp; elasticity</h2>' +
        '<span class="muted">Next fiscal quarter · revenue model only</span></div>' +
        '<p class="small">Historical transmission: company / industry <b>' + stockBeta.toFixed(2) +
        '</b> pp/pp (±' + (finite(d.model.gamma_sd) ? d.model.gamma_sd.toFixed(2) : '—') +
        '); industry / sector <b>' + (finite(f.industryBeta) ? f.industryBeta.toFixed(2) : '—') +
        '</b>; sector / aggregate market <b>' + (finite(f.sectorBeta) ? f.sectorBeta.toFixed(2) : '—') +
        '</b>. ' + (d.model.own ? 'Company coefficient fitted with own quarterly history.' :
        'Company coefficient is a peer-based prior (insufficient own history).') + '</p>' +
        '<p class="muted small">Shocks are <b>changes in year-over-year revenue growth</b> relative to the model baseline, not stock-market returns. Industry shock means the industry-specific move after the sector effect; do not also include it in the market shock.</p>' +
        '<div class="gamma-toolbar" style="flex-wrap:wrap;align-items:flex-start">' +
        control('marketPP','Aggregate-market revenue growth','pp',0,1,'Propagated through sector and industry') +
        control('industryPP','Same-industry peer residual','pp',0,1,'After market/sector transmission') +
        control('gdpPP','Real GDP growth surprise','pp',0,0.5,'Direct company effect only') +
        control('yieldBP','10Y Treasury yield surprise','bp',0,25,'Direct company effect only') +
        '</div><details><summary>Macro elasticity assumptions (user-supplied)</summary>' +
        '<div class="gamma-toolbar" style="flex-wrap:wrap">' +
        control('gdpCoef','GDP growth sensitivity','pp per +1 pp',0,0.1,'0 = no estimated direct effect') +
        control('yieldCoef','10Y yield sensitivity','pp per +100 bp',0,0.1,'0 = no estimated direct effect') +
        '</div><p class="muted small">Macro coefficients are NOT fitted by Filing Flows; edit them to run assumptions. Setting a nonzero coefficient is not evidence of a causal effect.</p></details>' +
        '<div class="gamma-toolbar" style="margin:12px 0"><span class="muted small">Illustrative presets:</span>' +
        '<button type="button" data-preset="bear">Downside</button>' +
        '<button type="button" data-preset="base">Baseline</button>' +
        '<button type="button" data-preset="bull">Upside</button></div>' +
        '<div data-scenario-result aria-live="polite"></div>' +
        '<details class="method-note"><summary>Definitions and limitations</summary>' +
        '<p>Model: Δg_company = β_company,industry × (β_industry,sector × β_sector,market × Δg_market + Δg_industry_residual) + assumed β_GDP × ΔGDP + assumed β_yield × Δyield/100bp. β coefficients are historical regression slopes (or shrinkage priors) in growth percentage points per percentage point, not causal elasticities. This is a deterministic conditional scenario, not a probability distribution or stock-price forecast.</p>' +
        '<p>For a given year-ago revenue base, the local level elasticity of company revenue relative to market revenue is approximately β_chain × (1 + g_market)/(1 + g_company), if both growth rates are available. GDP and rates may affect sector/market factors too; do not count the same economic shock twice. Price-return beta requires a separate adjusted-price/total-return model.</p>' +
        '</details>';
      box.appendChild(root);
      var inputs = {};
      root.querySelectorAll('[data-scenario]').forEach(function(el) {
        inputs[el.getAttribute('data-scenario')] = el;
      });
      if (!marketReady) {
        inputs.marketPP.disabled = true;
        inputs.marketPP.title = 'Market-to-sector/industry model unavailable';
      }
      function read() {
        var values = {};
        Object.keys(inputs).forEach(function(k){
          var s = inputs[k].value.trim();
          values[k] = s === '' ? NaN : Number(s);
        });
        return values;
      }
      function render() {
        var v = read(), r = calc(f,v);
        var target = root.querySelector('[data-scenario-result]');
        if (r.error) {
          target.innerHTML = '<p class="muted">' + esc(r.error) + '</p>';
          return;
        }
        var rows = [
          ['Aggregate market transmission',r.components.market],
          ['Same-industry residual',r.components.industry],
          ['GDP direct assumption',r.components.gdp],
          ['10Y yield direct assumption',r.components.yield]
        ];
        var mktFc = ix && ix.market && ix.market.fc && ix.market.fc[0];
        var localE = r.marketBeta != null && mktFc && finite(mktFc[1]) &&
          f.baseGrowth > -1 ? r.marketBeta * (1 + mktFc[1]) / (1 + f.baseGrowth) : null;
        target.innerHTML =
          '<div class="gamma-cards">' +
          '<div class="gamma-card"><span>Baseline YoY growth</span><strong>' + pct(r.baseGrowth) + '</strong></div>' +
          '<div class="gamma-card"><span>Scenario YoY growth</span><strong>' + (r.growth > -1 ? pct(r.growth) : 'Not meaningful') + '</strong></div>' +
          '<div class="gamma-card"><span>Change vs baseline</span><strong>' + pp(r.changePP) + '</strong></div>' +
          '<div class="gamma-card"><span>Scenario revenue</span><strong>' + usd(r.revenue) + '</strong></div>' +
          '</div><div class="tbl-wrap"><table class="small"><thead><tr>' +
          '<th>Source of change</th><th class="num">Contribution to company YoY growth</th></tr></thead><tbody>' +
          rows.map(function(z){return '<tr><td>' + esc(z[0]) + '</td><td class="num">' + pp(z[1]) + '</td></tr>';}).join('') +
          '<tr><td><b>Total</b></td><td class="num"><b>' + pp(r.changePP) + '</b></td></tr></tbody></table></div>' +
          '<p class="muted small">Baseline revenue: ' + usd(r.baseRevenue) +
          ' · scenario difference: ' + usd(r.deltaRevenue) +
          ' · implied growth transmission, aggregate market → company: ' +
          (r.marketBeta === null ? 'unavailable' : r.marketBeta.toFixed(2) + ' pp/pp') +
          ' · local revenue-level elasticity: ' +
          (localE === null ? 'unavailable' : localE.toFixed(2)) +
          '. Calculations hold all other modeled factors fixed; coefficients and input assumptions have uncertainty.</p>';
      }
      root.querySelectorAll('[data-scenario]').forEach(function(el){
        el.addEventListener('input',render);
      });
      var presets = {
        bear:{marketPP:-5,industryPP:-3,gdpPP:-1,yieldBP:100},
        base:{marketPP:0,industryPP:0,gdpPP:0,yieldBP:0},
        bull:{marketPP:5,industryPP:3,gdpPP:1,yieldBP:-100}
      };
      root.querySelectorAll('[data-preset]').forEach(function(b){
        b.addEventListener('click',function(){
          var p = presets[b.getAttribute('data-preset')];
          Object.keys(p).forEach(function(k){inputs[k].value = inputs[k].disabled ? 0 : p[k];});
          render();
        });
      });
      render();
    }).catch(function(){ /* The regular growth model remains useful without scenario metadata. */ });
  }

  global.FFElasticity = {company:company, calculate:calc};
  if (typeof module !== 'undefined' && module.exports) module.exports = {calculate:calc};
})(typeof window === 'undefined' ? {} : window);