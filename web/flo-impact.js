/* Flo Evidence-to-Model Research Cards.
 * Bounded research prompts, NOT causal price impact or investment signals.
 * Facts only from already-published event manifest and an OPTIONAL same-date
 * SPY/QQQ/IWM daily-close row in its staged price snapshot.
 */
(function(root){
'use strict';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const T=()=>root.FFFloTimeline||(typeof module!=='undefined'?require('./flo-timeline.js'):null);
const number=v=>typeof v==='number'&&Number.isFinite(v);
const date=v=>/^\d{4}-\d{2}-\d{2}$/.test(String(v||''))&&Number.isFinite(Date.parse(String(v)+'T00:00:00Z'));
const safeTag=s=>/^[a-z][a-z0-9_-]{0,35}$/.test(String(s||''));
const lessons={
 restatement:{
  en:'Restatement is not a cash outflow by itself. Compare original/revised periods, net income, equity, debt covenant impact and audit opinion.',
  zh:'重述本身不等于现金流出。核对原报与重述期间、净利润、权益、债务契约以及审计师意见。',
  formulas:['Restated EPS = restated net income / diluted shares','Change in equity = corrected assets − corrected liabilities']
 },
 offering:{
  en:'Identify announced vs issued shares, gross/net proceeds, underwriting expenses and dilution on a fully diluted basis.',
  zh:'区分拟发行与已实际发行股份、募集总额和净额、承销费用以及稀释后股本。',
  formulas:['Pro forma shares = existing diluted shares + actual newly issued shares','Dilution % = new shares / pro forma diluted shares']
 },
 debt:{
  en:'Compare contractual debt principal, coupon, issuance proceeds, maturity ladder, covenants and actual operating cash coverage.',
  zh:'检查债务本金、票息、实际募集额、到期梯队、限制性条款及经营现金流覆盖。',
  formulas:['Interest coverage = EBIT / contractual interest expense','Net debt = interest-bearing debt − eligible cash']
 },
 deal:{
  en:'Confirm closing status, purchase price, financing, goodwill assumptions, synergies and integration expenses.',
  zh:'核对是否完成交易、对价、融资来源、商誉、协同效应及整合费用。',
  formulas:['Purchase price allocation residual = consideration − identifiable net assets']
 },
 guidance:{
  en:'Compare old/new guidance on the same fiscal period, and reconcile GAAP versus adjusted definitions.',
  zh:'在同一财年或季度比较新旧指引，并核对 GAAP 与调整后指标口径。',
  formulas:['Guidance midpoint change = new midpoint − old midpoint']
 },
 impairment:{
  en:'Identify asset type, recoverability test, noncash impairment charge, tax impacts and any debt covenant consequences.',
  zh:'确认减值资产、测试假设、非现金损失、税务影响及潜在债务契约变化。',
  formulas:['Impairment charge = carrying amount − recoverable amount (under applicable GAAP)']
 },
 buyback:{
  en:'Authorization is not execution. Verify actual dollars spent, shares retired and funding.',
  zh:'董事会授权回购不等于已经回购。核对实际现金支付、回购股数与资金来源。',
  formulas:['Actual shares repurchased = cash spent / volume-weighted executed price']
 },
 cyber:{
  en:'Identify affected systems, materiality determination and verified costs; avoid inventing the breach loss.',
  zh:'核对受影响系统、重大性认定及已确定的费用；不要自行估算未知损失。',
  formulas:[]
 },
 auditor:{
  en:'Inspect Item 4.01 for auditor termination/appointment, disagreements and the former auditor letter.',
  zh:'阅读 Item 4.01，核对审计师聘任/解聘、分歧和前任审计师函件。',
  formulas:[]
 }
};
const defaultGuide={
 '8k':{
  en:'Read the actual SEC 8-K, item number, accepted timestamp, and exhibits. A topic tag is only a scanner classification.',
  zh:'阅读 SEC 8-K 原文、Item 编号、实际受理时间及附件。主题标签只是扫描分类，不等于事实结论。',
  formulas:[]
 },
 '13f':{
  en:'Compare positions across filed quarters using share counts (split adjusted) and portfolio weights; 13F is not an exact execution ledger.',
  zh:'比较两期 13F 的股数（拆股调整后）和组合权重；13F 不是逐笔交易流水。',
  formulas:['Position change (shares) = new quarter shares − prior quarter adjusted shares']
 },
 news:{
  en:'Verify the source headline against the actual announcement or SEC filing; press coverage does not confirm accounting impact.',
  zh:'用公司原始公告或 SEC 申报核对新闻标题；报道本身不能验证财务影响。',
  formulas:[]
 },
 price:{
  en:'Check the as-of close, market and sector return, liquidity and volatility. A one-day relative return is NOT a causal event study.',
  zh:'核对收盘数据日期、市场和行业收益、流动性及波动率。单日相对涨跌幅不是因果事件研究。',
  formulas:['Same-day relative change (pp) = stock daily % change − benchmark daily % change']
 }
};
function source(event){
 return T().safeURL(event&&event.source_url);
}
function checklist(e,zh=false){
 if(!e||!['8k','13f','news','price'].includes(e.kind))return [];
 const base=defaultGuide[e.kind];
 const out=[{topic:e.kind,explanation:base[zh?'zh':'en'],formulas:base.formulas}];
 if(e.kind==='8k'&&Array.isArray(e.topics)){
   const present=[...new Set(e.topics.filter(safeTag))].slice(0,12);
   for(const tag of present){
     if(!lessons[tag])continue;
     const l=lessons[tag];
     out.push({topic:tag,explanation:l[zh?'zh':'en'],formulas:l.formulas});
   }
 }
 return out;
}
function benchmarks(feed){
 const raw=feed&&feed.benchmarks&&typeof feed.benchmarks==='object'?feed.benchmarks:{};
 const result={};
 for(const symbol of ['SPY','QQQ','IWM']){
   const row=raw[symbol];
   if(!row||!date(row.asof)||!number(row.change_pct)||!number(row.close))continue;
   if(!(row.change_pct>-100&&row.change_pct<=500&&row.close>0&&row.close<1e8))continue;
   result[symbol]={asof:row.asof,change_pct:row.change_pct,close:row.close};
 }
 return result;
}
function relativeMove(event,feed,symbol='SPY'){
 if(!event||event.kind!=='price'||!['SPY','QQQ','IWM'].includes(symbol))
   return {ok:false,reason:'not_same_day_equity_vs_index'};
 const b=benchmarks(feed)[symbol];
 if(!b)return {ok:false,reason:'missing_published_index_close'};
 if(!date(event.price_asof)||event.price_asof!==b.asof)
   return {ok:false,reason:'date_mismatch'};
 if(!number(event.change_pct)||event.change_pct<=-100||event.change_pct>500)
   return {ok:false,reason:'invalid_stock_daily_change'};
 return {ok:true,symbol,asof:event.price_asof,stockPct:event.change_pct,benchmarkPct:b.change_pct,
   diffPP:Number((event.change_pct-b.change_pct).toFixed(3)),context:'same_day_close_only_not_caused_by_event'};
}
function evidence(e,feed){
 if(!e)return {sourceVerified:false,scanFresh:false,sourceReason:'no event'};
 const now=Date.now(),created=Date.parse(feed&&feed.generated_at||'');
 const scanFresh=Number.isFinite(created)&&created<=now+300000&&now-created<=6*3600000;
 const sourceVerified=!!source(e);
 return {sourceVerified,scanFresh,
   sourceReason:!sourceVerified?(e.kind==='price'?'site published delayed close (no direct SEC article)':'no allowlisted original source'):'source URL available (content not fact-checked)',
   asof:e.kind==='price'?e.price_asof:e.kind==='13f'?e.period_end:e.filed||e.event_at,
   observation:e.event_at||'',publishedAt:feed&&feed.generated_at||''};
}
function render(e,feed,zh=false){
 if(!e||!['8k','13f','news','price'].includes(e.kind))return null;
 const study=evidence(e,feed),lesson=checklist(e,zh);
 let html='<section class="flo-impact"><h3>'+esc(e.kind.toUpperCase())+' · '+
  esc(zh?'证据核对与建模研究':'Evidence review & modeling research')+'</h3>'+
  '<p><b>'+esc(e.title||'Published event')+'</b></p>'+
  '<p class="flo-source">'+esc((e.ticker||e.manager||'')+' · '+(e.event_at||'').slice(0,16)+' UTC')+'</p>'+
  '<p class="flo-source">'+esc(zh?'数据来源状态：':'Data provenance: ')+
    esc(study.sourceReason)+'; '+esc(zh?'最近扫描构建：':'Manifest build: ')+esc(study.publishedAt||'unknown')+
    (!study.scanFresh?esc(zh?'（过期或时间未知）':' (stale/unknown timestamp)'):'')+'</p>';
 if(e.kind==='13f')html+='<p>'+esc(zh?'持仓截至 '+String(e.period_end||'未知')+'，不同于 '+String(e.filed||'未知')+' 的申报日。':
  'Positions as of '+String(e.period_end||'unknown')+'; filing date '+String(e.filed||'unknown')+' is not the trade date.')+'</p>';
 html+='<ol class="flo-impact-lessons">';
 for(const l of lesson){
   html+='<li><b>'+esc(l.topic.toUpperCase())+'</b><p>'+esc(l.explanation)+'</p>';
   if(l.formulas.length)html+='<ul>'+l.formulas.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
   html+='</li>';
 }
 html+='</ol>';
 if(e.kind==='price'){
   const results=['SPY','QQQ','IWM'].map(s=>relativeMove(e,feed,s));
   const available=results.filter(r=>r.ok);
   if(available.length){
     html+='<section class="flo-impact-market"><b>'+esc(zh?'相同收盘日的市场相对变动':'Same-close-date market-relative moves')+'</b><ul>';
     for(const r of available)
       html+='<li>'+esc(r.symbol)+': '+esc((r.diffPP>=0?'+':'')+r.diffPP.toFixed(3))+
         ' '+esc(zh?'个百分点':'percentage points')+
         ' ('+esc(e.ticker||'Stock')+' '+esc((r.stockPct>=0?'+':'')+r.stockPct.toFixed(2))+'%, '+
         esc(r.symbol)+' '+esc((r.benchmarkPct>=0?'+':'')+r.benchmarkPct.toFixed(2))+'%)</li>';
     html+='</ul></section>';
   }else html+='<p>'+esc(zh?
     '该收盘日没有经过核对的同日期指数基准，无法计算相对涨跌幅。':
     'No verified same-date index benchmark was published; relative daily move unavailable.')+'</p>';
 }
 const safe=source(e);
 if(safe)html+='<p><a target="_blank" rel="noopener noreferrer" href="'+esc(safe)+'">'+
   (zh?'阅读原始来源':'Open original evidence')+'</a></p>';
 html+='<p class="flo-timeline-note">'+esc(zh?
   '这是一份检查清单而非完整财务模型或事件因果检验。材料中的事项、实际金额及披露时间需要原文复核；不能据此推测价格方向。':
   'This is a research checklist, NOT a causal event study, verified issuer impact, or price forecast. Confirm actual terms, figures, and timestamps from primary materials.')+'</p></section>';
 return {html,links:safe?[[safe,e.kind.toUpperCase()+' original source']]:[],
   facts:[e.kind+' '+(e.ticker||e.manager||'')+' '+String(e.event_at||'')],
   mood:e.kind==='8k'&&e.priority==='high'?'think':'talk',
   intents:['impact-research'],evidence:study};
}
root.FFFloImpact={source,checklist,benchmarks,relativeMove,evidence,render};
if(typeof module!=='undefined')module.exports=root.FFFloImpact;
})(typeof globalThis!=='undefined'?globalThis:this);
