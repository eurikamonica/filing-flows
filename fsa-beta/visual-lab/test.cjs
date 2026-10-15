// Created by ChatGPT (OpenAI). Accounting edge cases and scenario integrity.
const assert=require('node:assert/strict'),m=require('./math.js');
assert.equal(m.accrual({net_income:130,ocf:85}),45);
assert.equal(m.accrual({net_income:0,ocf:10}),-10);
assert.equal(m.accrual({net_income:100}),null);
assert.equal(m.ratio({net_income:130,ocf:85,opening_assets:900,closing_assets:1000}),45/950);
assert.equal(m.ratio({net_income:10,ocf:5,opening_assets:0,closing_assets:100}),null);
assert.deepEqual(m.roll({opening:45,additions:28,releases:18,utilization:20,other:2,closing:37}),{expected:37,residual:0});
assert.equal(m.roll({opening:45}),null);
assert.equal(m.roll({opening:40,additions:0,releases:0,utilization:10,other:0,closing:35}).residual,5);
const s={reserve:50,profit:100,cash:100};
assert.deepEqual(m.transact(s,'add',10),{reserve:60,profit:90,cash:100});
assert.deepEqual(m.transact(s,'use',10),{reserve:40,profit:100,cash:90});
assert.deepEqual(m.transact(s,'release',10),{reserve:40,profit:110,cash:100});
assert.throws(()=>m.transact(s,'release',51));assert.throws(()=>m.transact(s,'add',NaN));assert.throws(()=>m.transact(s,'add',1.5));assert.equal(s.reserve,50);
const d={schema:'visual-lab-1',company:'Test',unit:'USD',demo:false,periods:[{label:'FY2025',net_income:null,ocf:0}]};
assert.equal(m.validate(d),d);assert.throws(()=>m.validate({...d,periods:[{label:'FY',ocf:'100'}]}));assert.throws(()=>m.validate({...d,periods:[{label:'FY',reserves:[{name:'R',releases:-1}]}]}));
console.log('18 accounting, missing-value, import and scenario assertions passed.');
