'use strict';
const assert=require('node:assert/strict');
const T=require('../web/flo-timeline.js');
const Alerts=require('../web/flo-alerts.js');
let n=0;
const eq=(a,b,m)=>{assert.equal(a,b,m);n++};
const ok=(a,m)=>{assert.ok(a,m);n++};
const NOW=Date.parse('2026-10-25T21:00:00Z');
const SEC='https://www.sec.gov/Archives/edgar/data/1045810/0000000001';
const e=(id,kind,ticker,date,more={})=>({
 id,kind,ticker,priority:'medium',title:'Observation '+id,event_at:date,
 source_url:kind==='price'?'':SEC,source_label:kind==='price'?'daily close':'SEC',...more
});
const filings=e('8k:n','8k','NVDA','2026-10-25T16:00:00Z',{title:'NVDA filed a material 8-K',topics:['offering'],filed:'2026-10-25'});
const prices=e('price:n','price','NVDA','2026-10-25T00:00:00Z',
 {price_asof:'2026-10-25',change_pct:-7.75,price:190.12});
const news=e('news:n','news','NVDA','2026-10-25T15:00:00Z',
 {source_url:'https://www.prnewswire.com/news-releases/issuer-notice.html',title:'<script>alert(1)</script>'});
const manager=e('13f:n','13f','AAPL','2026-10-24T00:00:00Z',
 {manager:'Example Fund',filed:'2026-10-24',period_end:'2026-09-30',symbols:['NVDA','AAPL'],title:'New 13F index from Example Fund'});
const other=e('8k:o','8k','TSLA','2026-10-25T12:00:00Z',{title:'Different issuer filing'});
const earlier=e('8k:old','8k','NVDA','2026-08-15T12:00:00Z',{title:'Very old filing'});
const malicious=e('news:evil','news','NVDA','2026-10-25T14:00:00Z',{source_url:'javascript:alert(1)',title:'<img src=x>'});
const future=e('8k:future','8k','NVDA','2026-11-25T12:00:00Z');
const all=[other,filings,prices,news,manager,earlier,malicious,future,filings];
ok(T.matches(manager,'NVDA'),'13F disclosed symbols associate target ticker');
ok(!T.matches(other,'NVDA'),'other company not associated');
eq(T.tickerFromQuery('$NVDA event timeline',all),'NVDA','extract cashtag');
eq(T.tickerFromQuery('NVDA 事件时间线',all),'NVDA','extract timeline symbol');
eq(T.tickerFromQuery('UNKNOWN 事件时间线',all),null,'unknown name not asserted to exist in feed');
eq(T.safeURL('https://www.sec.gov/edgar/browse/?CIK=1067983&owner=exclude'),
 'https://www.sec.gov/edgar/browse/?CIK=1067983&owner=exclude','official 13F indexed link');
eq(T.safeURL('https://www.sec.gov/edgar/browse/?CIK=bad&owner=exclude'),'','refuse invalid CIK');
eq(T.safeURL('https://sec.gov.evil.example/path'),'','refuse hostile lookalike');
eq(T.safeURL('javascript:alert(1)'),'','refuse script protocol');
ok(T.symbols(manager).includes('AAPL')&&T.symbols(manager).includes('NVDA'),'deduplicated symbol association');
eq(T.precision(manager).at,'2026-10-24','quarterly 13F uses date not inferred filing hour');
eq(T.precision(prices).at,'2026-10-25','close uses date not fake UTC midnight time');
eq(T.precision(filings).label,'timestamp','actual 8-K event has timestamp');
const hits=T.collect(all,'NVDA',{now:NOW,days:14,limit:30});
eq(hits.length,5,'select five target signals (includes untrusted-source headline but excludes old/other/future/repeat)');
eq(hits[0].id,'8k:n','descending time order');
eq(hits.filter(x=>x.id==='8k:n').length,1,'duplicate filing accession ignored');
ok(!hits.some(x=>x.ticker==='TSLA'),'no mixed issuer false positives');
ok(!hits.some(x=>x.id==='8k:old'||x.id==='8k:future'),'bounded lookback/future');
const counts=T.summarize(all,'NVDA',{now:NOW,days:14});
eq(counts.counts['8k'],1,'8K evidence count');
eq(counts.counts['13f'],1,'13F cross-symbol match');
eq(counts.counts.price,1,'single delayed price snapshot');
eq(counts.counts.news,2,'two published news headlines included even when link not allowed');
ok(counts.relatedWindows>=1,'temporal clustering detected');
ok(T.clusters(all,'NVDA',{now:NOW,days:14}).some(x=>x.crossSignal),
 'co-occurrence requires different types');
const output=T.render(all,'NVDA',true,{now:NOW,days:14});
ok(output.html.includes('跨来源')&&output.html.includes('不能')&&output.html.includes('13F'),'Chinese correlation warning');
ok(output.html.includes('2026-09-30')&&output.html.includes('申报日期不是交易日期'),'13F filing-vs-positions distinction');
ok(output.html.includes('−')===false||output.html.includes('收盘'),'do not infer intraday quotes');
ok(output.html.includes('-7.75%')&&output.html.includes('$190.12'),'grounded daily-close percentage and price');
ok(output.html.includes('&lt;script&gt;')&&!output.html.includes('<script>'),'third-party untrusted headline escaped');
ok(output.html.includes('&lt;img')&&!output.html.includes('<img'),'malicious HTML escaped');
ok(!output.html.includes('href="javascript:'),'no malicious link rendered');
ok(output.links.every(x=>x[0].startsWith('https://')),'safe sources only');
ok(!output.html.includes('news caused')&&!output.html.includes('新闻导致'),'no invented cause-effect conclusion');
eq(T.render(all,'TSLA',false,{now:NOW}).summary.total,1,'TSLA timeline isolated');
eq(T.render([], 'NVDA',false,{now:NOW}).summary.total,0,'empty feed describes limits without inventing events');
ok(Alerts.timelineIntent('NVDA 事件时间线'),'Chinese timeline route');
ok(Alerts.timelineIntent('NVDA event timeline'),'English timeline route');
ok(Alerts.intent('$NVDA filing timeline'),'general Flo alert router exposes ticker timeline');
ok(!Alerts.timelineIntent('NVDA valuation')&&!Alerts.timelineIntent('NVDA DCF'),'original research questions unaffected');
console.log(n+' Flo cross-signal timeline checks passed');
