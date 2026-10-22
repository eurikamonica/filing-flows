/* Run: node --test research/test_scenario_elasticity.js */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {calculate} = require('../web/scenario-elasticity.js');

const fit = {
  stockBeta:1.5, industryBeta:0.8, sectorBeta:0.7,
  baseGrowth:0.2, baseRevenue:1.2e9
};
const neutral = {marketPP:0,industryPP:0,gdpPP:0,yieldBP:0,gdpCoef:0,yieldCoef:0};
function near(a,b) { assert.ok(Math.abs(a-b) < 1e-8, 'expected '+a+' ≈ '+b); }

test('zero shocks exactly reproduce fitted baseline', () => {
  const r = calculate(fit, neutral);
  near(r.growth, 0.2);
  near(r.revenue, 1.2e9);
  near(r.changePP,0);
});
test('market shock flows through sector -> SIC industry -> company', () => {
  const r = calculate(fit,{...neutral,marketPP:-5});
  near(r.components.market,-4.2);
  near(r.marketBeta,0.84);
  near(r.growth,0.158);
});
test('peer residual is separate from the market shock', () => {
  const r = calculate(fit,{...neutral,industryPP:-3});
  near(r.components.industry,-4.5);
  near(r.components.market,0);
});
test('user macro coefficients use pp per GDP pp and pp per 100bp', () => {
  const r = calculate(fit,{marketPP:-5,industryPP:-3,gdpPP:-1,
      yieldBP:100,gdpCoef:.4,yieldCoef:-.2});
  near(r.changePP,-9.3);
  near(r.growth,.107);
  near(r.revenue,1.107e9);
  near(r.deltaRevenue,-93e6);
});
test('missing sector beta refuses nonzero market shock', () => {
  assert.match(calculate({...fit,sectorBeta:null},{...neutral,marketPP:5}).error,/unavailable/);
});
test('missing market factor still allows independent industry scenarios', () => {
  const r = calculate({...fit,sectorBeta:null},{...neutral,industryPP:4});
  near(r.components.industry,6);
  assert.equal(r.marketBeta,null);
});
test('negative implied revenue is never reported as a dollar amount', () => {
  const r = calculate(fit,{...neutral,industryPP:-100});
  assert.ok(r.growth < -1);
  assert.equal(r.revenue,null);
});
test('nonfinite input does not silently turn into a forecast', () => {
  assert.match(calculate(fit,{...neutral,gdpCoef:NaN}).error,/numeric/);
});
