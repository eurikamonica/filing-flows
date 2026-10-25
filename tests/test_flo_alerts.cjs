'use strict';
const assert=require('node:assert/strict');
const Alert=require('../web/flo-alerts.js');
let n=0;
const ok=(v,m)=>{assert.ok(v,m);n++};
const eq=(v,x,m)=>{assert.equal(v,x,m);n++};
const NOW=Date.parse('2026-10-26T16:00:00Z');
const e=(id,kind,props={})=>({
 id,kind,priority:'high',ticker:'NVDA',event_at:'2026-10-26T15:57:00Z',
 title:'New report',detail:'Original filing',source_label:'SEC EDGAR',
 source_url:'https://www.sec.gov/Archives/edgar/data/1045810/example',...props
});
const k=e('8k:1','8k',{topics:['restatement']});
const manager=e('13f:1','13f',{ticker:'AAPL',period_end:'2026-09-30'});
const news=e('news:2','news',{title:'<img src=x onerror=alert(1)>',source_url:'https://www.prnewswire.com/news-releases/x.html'});
const price=e('price:IREN:2026-10-26','price',{ticker:'IREN',change_pct:-10.2,price_asof:'2026-10-26',source_url:''});
const fresh={schema:1,generated_at:'2026-10-26T16:00:00Z',events:[k,manager,news,price]};
ok(Alert.valid(k)&&Alert.valid(manager)&&Alert.valid(news)&&Alert.valid(price),'valid sourced records');
const first=Alert.compare({initialized:false,seen:[]},fresh,{now:NOW});
eq(first.newEvents.length,0,'initial page load never blasts historic events');
eq(first.seen.length,4,'first page load stores baseline');
const repeated=Alert.compare(first,fresh,{now:NOW});
eq(repeated.newEvents.length,0,'same scan never alerts again');
const k2=e('8k:2','8k',{priority:'medium',title:'Acquisition'});
const next=Alert.compare(first,{...fresh,events:[k2,...fresh.events]}, {now:NOW});
eq(next.newEvents.length,1,'new accession triggers one event');
eq(next.newEvents[0].id,'8k:2','new event identified');
const reload=Alert.compare({initialized:true,seen:next.seen},{...fresh,events:[k2,...fresh.events]}, {now:NOW});
eq(reload.newEvents.length,0,'refresh/cross-session deduplicated');
const old=e('8k:old','8k',{event_at:'2026-10-15T12:00:00Z'});
eq(Alert.compare(first,{...fresh,events:[old,...fresh.events]},{now:NOW}).newEvents.length,0,'stale backfill does not wake mascot');
const invalid=e('8k:spoof','8k',{source_url:'https://evil.example/redirect'});
eq(Alert.valid(invalid),false,'spoofed filing link rejected');
const malformed=e('price:no','price',{change_pct:NaN});
eq(Alert.valid(malformed),false,'price needs verified numeric daily change');
const escape=Alert.explain(news,true);
ok(escape.includes('&lt;img')&&!escape.includes('<img'),'untrusted news headlines escaped');
ok(escape.includes('标题')||escape.includes('新闻'),'Chinese evidence explanation');
ok(Alert.explain(manager,false).includes('quarter-end'),'13F does not imply filing-day trade');
ok(Alert.explain(price,false).includes('NOT live'),'end-of-day price explicitly labeled');
eq(Alert.react(k),'worried','high 8-K mascot worried');
eq(Alert.react(manager),'wave','13F mascot waves/spins');
eq(Alert.react(price),'worried','negative price mascot worried');
const upbeat=e('price:up','price',{source_url:'',price_asof:'2026-10-26',change_pct:8});
eq(Alert.react(upbeat),'happy','upward price mascot jumps');
const topics=e('8k:restatement','8k',{ticker:'CRWV',topics:['restatement','debt'],
  form:'8-K/A',filed:'2026-10-26'});
const explained=Alert.explain(topics,true);
ok(explained.includes('事项标签')&&explained.includes('重述')&&explained.includes('债务'),
  '8-K sourced topic labels and restatement analysis presented without inventing figures');
const managerUpdates=e('13f:changed','13f',{
  ticker:'AAPL',manager:'Berkshire Hathaway',symbols:['AAPL','NVDA','BAC'],
  period_end:'2026-09-30',filed:'2026-10-26',
  changes:{New:['AAPL'],Added:['NVDA'],Reduced:['BAC']}});
ok(Alert.shown(managerUpdates,{watch:'NVDA',kinds:{'13f':true}}),
  'watchlist matches added 13F tickers, not only first new position');
eq(Alert.shown(managerUpdates,{watch:'TSLA',kinds:{'13f':true}}),false,
  'unrelated ticker does not produce 13F alert');
eq(Alert.shown(managerUpdates,{watch:'NVDA',kinds:{'13f':false}}),false,
  'disabled type suppresses 13F notifications');
const related=Alert.explain(k,false,[price,e('news:NVDA','news',{source_url:'https://www.prnewswire.com/news-releases/example.html'})]);
ok(related.includes('Other observed same-ticker signals')&&related.includes('NOT causality')&&related.includes('Source'),
 'same-ticker independent signals explained without claiming causal attribution');
ok(Alert.intent('最近扫描有什么新消息')&&Alert.intent('What changed since the last scan?'),
 'explicit current scanner queries routed to Flo Pulse');
ok(!Alert.intent('NVDA valuation')&&!Alert.intent('AAPL latest SEC filings'),
 'ordinary finance filings remain on original handlers');
const brief=Alert.report('最近扫描有什么新消息',true);
ok(brief.html.includes('尚未取得')||brief.html.includes('已发布'),
 'standalone alert answer works without a validated feed');
const em=Alert.explain(managerUpdates,false);
ok(em.includes('Berkshire Hathaway')&&em.includes('2026-09-30')&&em.includes('NVDA')
 &&em.includes('NOT trades'),'13F explanation contains manager, period, updated ticker and filing lag caution');
const priceContext=Alert.explain(price,true);
ok(priceContext.includes('IREN')&&priceContext.includes('-10.20%')&&priceContext.includes('延迟日线'),
 'price explanation shows verified date, percent and non-intraday scope');
const malformedLink=e('news:phish','news',{source_url:'https://sec.gov.evil.example/path'});
eq(Alert.valid(malformedLink),false,'SEC lookalike domain refused');
eq(Alert.shown(k,{watch:'AAPL',kinds:{'8k':true}}),false,'issuer filter excludes other filings');
assert.throws(()=>Alert.normalize({schema:2,events:[]}),/Invalid/);n++;
assert.throws(()=>Alert.normalize({schema:1,events:Array(301).fill(k)}),/Invalid/);n++;
console.log(n+' Flo live pulse tests passed');
