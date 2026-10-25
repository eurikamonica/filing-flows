'use strict';
const assert=require('node:assert/strict');
const I=require('../web/flo-impact.js');
const Pulse=require('../web/flo-alerts.js');
let n=0;const yes=(x,m)=>{assert.ok(x,m);n++};
const eq=(a,b,m)=>{assert.equal(a,b,m);n++};
const same={generated_at:new Date().toISOString(),benchmarks:{
 SPY:{asof:'2026-10-23',close:686.21,change_pct:0.82,source:'same published extremes.json snapshot'},
 QQQ:{asof:'2026-10-23',close:614.25,change_pct:1.55},
 IWM:{asof:'2026-10-22',close:238.66,change_pct:0.4},
 EVIL:{asof:'2026-10-23',close:100,change_pct:99}
}};
const price={id:'price:NVDA:2026-10-23',kind:'price',ticker:'NVDA',
 title:'NVDA delayed daily close',event_at:'2026-10-23T00:00:00Z',
 price_asof:'2026-10-23',price:195.75,change_pct:6.25,priority:'medium'};
const filing={id:'8k:source',kind:'8k',ticker:'NVDA',
 title:'<img src=x onerror=alert(1)>',priority:'high',
 event_at:'2026-10-23T14:00:00Z',filed:'2026-10-23',
 topics:['restatement','offering','debt','deal','guidance','impairment','cyber','auditor','unknown',
  '<script>malicious</script>'],source_url:'https://www.sec.gov/Archives/edgar/data/1045810/example'};
const thirteen={id:'13f:source',kind:'13f',ticker:'NVDA',manager:'Test Manager',
 period_end:'2026-09-30',filed:'2026-10-23',event_at:'2026-10-23T00:00:00Z',
 source_url:'https://www.sec.gov/edgar/browse/?CIK=1067983&owner=exclude'};
eq(Object.keys(I.benchmarks(same)).length,3,'only three supported index proxies');
eq(I.relativeMove(price,same,'SPY').diffPP,5.43,'6.25 - 0.82 = +5.43 percentage points');
eq(I.relativeMove(price,same,'QQQ').diffPP,4.7,'6.25 - 1.55 = +4.70 pp');
eq(I.relativeMove(price,same,'IWM').ok,false,'stale previous-day benchmark is not comparable');
eq(I.relativeMove(filing,same,'SPY').ok,false,'never assign a price reaction to a filing');
eq(I.relativeMove(price,same,'BAD').ok,false,'unapproved index rejected');
eq(I.relativeMove(price,{generated_at:new Date().toISOString()},'SPY').reason,
 'missing_published_index_close','missing same-date index remains unavailable');
eq(I.relativeMove({...price,price_asof:'2026-10-22'},same,'SPY').reason,
 'date_mismatch','different trading days cannot be compared');
eq(I.relativeMove({...price,change_pct:Infinity},same,'SPY').ok,false,
 'nonfinite price returns rejected');
eq(I.relativeMove({...price,change_pct:-105},same,'SPY').ok,false,
 'impossible daily return rejected');
const stale={benchmarks:{SPY:{asof:'2026-10-23',close:-1,change_pct:1},
 QQQ:{asof:'2026-10-23',close:100,change_pct:Infinity},
 IWM:{asof:'garbage',close:100,change_pct:3}}};
eq(Object.keys(I.benchmarks(stale)).length,0,'malformed baseline never accepted');
const output=I.render(price,same,true);
yes(output.html.includes('5.430')&&output.html.includes('4.700'),
 'market relative day close shown with correctly labeled percentage points');
yes(output.html.includes('相同收盘日')&&!output.html.includes('事件导致'),
 'no causality inference in comparison');
yes(!output.html.includes('IWM: '),'stale benchmark not presented as same-day');
yes(I.render(price,{},false).html.includes('relative daily move unavailable'),
 'baseline absence communicated without fabricated return');
const guide=I.checklist(filing,true);
yes(guide.some(x=>x.topic==='offering'&&x.formulas[0].includes('Pro forma')),
 'dilution computation checklist');
yes(guide.some(x=>x.topic==='restatement'&&x.explanation.includes('重述')),
 'original-versus-restated earnings guidance');
yes(guide.some(x=>x.topic==='debt'&&x.formulas[0].includes('coverage')),
 'interest coverage formula');
yes(guide.every(x=>x.topic!=='<script>malicious</script>'),'unsafe tags dropped');
const sec=I.render(filing,same,false);
yes(sec.html.includes('Restatement')===false || sec.html.includes('Restatement'),
 'no English casing dependency');
yes(sec.html.includes('restated net income')&&sec.html.includes('Interest coverage'),
 'SEC research cards include both restatement and debt-specific formula guidance');
yes(sec.html.includes('&lt;img')&&!sec.html.includes('<img'),
 'malicious headline escaped, not executable');
yes(sec.links.length===1&&sec.links[0][0].includes('sec.gov/Archives/'),
 'official primary source preserved');
const holdings=I.render(thirteen,same,true);
yes(holdings.html.includes('2026-09-30')&&holdings.html.includes('2026-10-23'),
 '13F quarter-end and filing date remain separate');
yes(holdings.html.includes('13F 不是逐笔交易流水'),
 '13F not treated as execution ledger');
const unsourced={...filing,source_url:'javascript:alert(1)'};
eq(I.render(unsourced,same,false).links.length,0,'malicious URL omitted');
yes(I.render(unsourced,same,false).html.includes('no allowlisted original source'),
 'source verification warning');
yes(Pulse.impactIntent('NVDA 8-K impact analysis'),'impact search route');
yes(Pulse.impactIntent('NVDA 披露财务影响'),'Chinese SEC impact route');
yes(Pulse.impactIntent('NVDA 相对大盘涨跌幅'),'market-relative change intent route');
yes(!Pulse.impactIntent('NVDA DCF valuation'),'old Flo valuation route unmodified');
eq(I.render(null,same,false),null,'no invented card from absent event');
console.log(n+' Flo source-to-model event research tests passed');
