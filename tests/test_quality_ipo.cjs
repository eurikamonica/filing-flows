const assert=require('node:assert/strict');
const fs=require('node:fs');
require('../web/quality-ipo.js');
const q=globalThis.FFQualityIPO;
const data=JSON.parse(fs.readFileSync('pipeline/data/ipo/2130357.json','utf8'));
for(const p of data.periods) {
  const specs=q.charts(p);assert.equal(specs.length,4);
  for(const s of specs) {
    assert(s.links.every(l=>Number.isFinite(l.v)&&l.v>0));
    const incoming=s.links.filter(l=>l.t==='pool').reduce((v,l)=>v+l.v,0);
    const outgoing=s.links.filter(l=>l.s==='pool').reduce((v,l)=>v+l.v,0);
    assert(Math.abs(incoming-outgoing)<1);
  }
}
assert.equal(q.flow('bad',[['A',10]],50,'result',{}),null);
assert.equal(q.flow('missing',[['A',null]],0,'result',{}),null);
assert.equal(q.charts({values:{revenue:100,oi:10},label:'FY'}).length,1);
assert(!q.metricTable([{label:'<img src=x>',value:null,formula:'<script>'}]).includes('<img'));
console.log('IPO signed-flow conservation, missing data and escaping checks passed');
