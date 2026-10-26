'use strict';
const assert=require('node:assert/strict');
const F=require('../web/flo-momentum.js');
let n=0;
const ok=(v,m)=>{assert.ok(v,m);n++};
const eq=(a,b,m)=>{assert.equal(a,b,m);n++};
const NOW=Date.parse('2026-10-26T15:00:00Z');
const asof=new Date(NOW-60000).toISOString(),prev=new Date(NOW-6*60000).toISOString();
const member={
 label:'S&P 500',membership_asof:'2026-10-26',membership_source:'Wikipedia, timestamped',
 membership_status:'current_snapshot_unofficial',universe_size:500,
 symbols_with_exact_5m_bars:475,coverage_pct:95,ranking_status:'complete_enough',
 leaders:[
  {ticker:'NVDA',price:211.34,five_min_pct:6.25,turnover_5m_usd:3500000,
   volume_complete:true,rank:1,streak:3,asof,prev_asof:prev},
  {ticker:'TSLA',price:401,five_min_pct:3.22,turnover_5m_usd:450000,
   volume_complete:true,rank:2,streak:1,asof,prev_asof:prev},
  {ticker:'AAPL',price:280,five_min_pct:-0.5,turnover_5m_usd:1000000,
   volume_complete:true,rank:3,streak:1,asof,prev_asof:prev},
  {ticker:'BAD',price:9,five_min_pct:55,turnover_5m_usd:10000,
   volume_complete:true,rank:4,streak:2,asof,prev_asof:new Date(NOW-8*60000).toISOString()},
  {ticker:'CRWV',price:170,five_min_pct:9,turnover_5m_usd:50000,
   volume_complete:false,rank:5,streak:1,asof,prev_asof:prev}
 ]};
const feed={
 schema:1,generated_at:new Date(NOW).toISOString(),provider:'alpaca',feed:'iex',
 universes:{sp500:member,russell1000:{...member,label:'Russell 1000',universe_size:1000,
 ranking_status:'partial',coverage_pct:18},russell2000:{
 label:'Russell 2000',membership_status:'unavailable',membership_asof:null,
 universe_size:0,ranking_status:'unavailable',leaders:[],coverage_pct:0}}
};
eq(F.parseQuestion('罗素2000最近5分钟涨幅榜'),'russell2000','Russian universe direct text');
eq(F.parseQuestion('Russell 1000 five-minute scanner'),'russell1000','Russell 1000');
eq(F.parseQuestion('S&P 500 五分钟上涨最多'),'sp500','S&P 500');
ok(F.intent('标普500最近5分钟涨幅榜'),'Chinese index scanner question');
ok(F.intent('Russell 2000 5m gainers'),'English ticker scanner question');
ok(F.intent('5分钟涨幅接力榜'),'five-minute relay intent');
ok(!F.intent('NVIDIA 5-year DCF valuation'),'ordinary valuation not intercepted');
ok(F.classify(feed,'sp500',NOW).ok,'valid fresh source with current membership');
eq(F.classify(feed,'russell2000',NOW).reason,'membership_unavailable','unverified Russell denied');
eq(F.classify(feed,'russell1000',NOW).partial,true,'IEX Russell partial coverage labeled');
eq(F.classify(feed,'sp500',NOW+13*60000).reason,'stale','hard stale cutoff');
eq(F.classify({...feed,schema:999},'sp500',NOW).reason,'unavailable','unknown schema');
eq(F.classify({...feed,universes:{sp500:{...member,membership_asof:'2024-06-01'}}},'sp500',NOW).reason,'membership_stale','historical 2024 membership rejected');
const gainers=F.select(feed,{universe:'sp500',minGain:2,minTurnover:200000,minStreak:1,limit:20},NOW);
eq(gainers.rows.length,2,'minimum turnover & positive gain remove invalid interval');
eq(gainers.rows[0].ticker,'NVDA','highest verified liquid gainer');
eq(gainers.rows[1].ticker,'TSLA','second valid winner');
eq(F.select(feed,{universe:'sp500',minStreak:2},NOW).rows.length,1,'consecutive scan filter only persisted leaders');
eq(F.select(feed,{universe:'sp500',minTurnover:500000},NOW).rows.length,1,'min volume filter excludes partial and small');
ok(!gainers.rows.some(x=>x.ticker==='BAD'),'fake eight-minute comparison excluded');
eq(F.select(feed,{universe:'russell2000'},NOW).rows.length,0,'no fake Russell leaders');
const analysis=F.report('S&P 500 五分钟涨幅榜','zh',NOW);
// report() reads only live feed state; without polling it must refuse invented data.
ok(analysis.html.includes('当前没有可核实')&&analysis.facts.length===0,'unconfigured source explicitly refuses fake report');
eq(F.scanForNotification(feed,NOW),null,'first open establishes baseline, no stale alerts');
eq(F.scanForNotification(feed,NOW+500),null,'same top mover never repeats');
const moved={...feed,generated_at:new Date(NOW+5*60000).toISOString(),
 universes:{...feed.universes,sp500:{...member,leaders:[
  {...member.leaders[1],rank:1,five_min_pct:8.4,asof:new Date(NOW+4*60000).toISOString(),
     prev_asof:new Date(NOW-60000).toISOString()},
  {...member.leaders[0],rank:2}]}}};
eq(F.scanForNotification(moved,NOW+5*60000)?.ticker,'TSLA','new leader gets one alert');
eq(F.scanForNotification(moved,NOW+5*60000+250)?.ticker,undefined,'new leader not animated twice');
eq(F.classifyHttpError(404,{code:'PGRST205'}),'schema_missing','PGRST205 means missing/unexposed table');
eq(F.classifyHttpError(404,{}),'endpoint_not_found','unknown 404 reports missing endpoint');
eq(F.classifyHttpError(403,{}),'unauthorized','403 distinguishes denied access');
eq(F.classifyHttpError(401,{}),'unauthorized','401 distinguishes denied access');
ok(F.describeServiceIssue('schema_missing','zh').includes('db/flo-momentum.sql'),'Chinese setup instructions link actual SQL');
ok(F.describeServiceIssue('no_public_row','zh').includes('公开'),'no authorized row separate from 404');
ok(F.describeServiceIssue('unauthorized','zh').includes('密钥'),'access failure does not give false prices');
console.log(n+' Flo five-minute universe / gainers / relay guardrail tests passed');
