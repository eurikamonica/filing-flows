/* Flo Event Research — bounded, sourced, in-page cross-signal timelines.
 * Reads the already-published Flo Pulse manifest; NO new API calls, credentials,
 * fabricated stock prices, impact probabilities or causal inference.
 */
(function(root){
'use strict';
const escape=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tickerOK=s=>/^[A-Z][A-Z0-9.-]{0,9}$/.test(String(s||''));
const kinds=['8k','13f','news','price'];
const clock=v=>{const n=Date.parse(v);return Number.isFinite(n)?n:NaN;};
const SEC=/^https:\/\/(?:www\.)?sec\.gov\/(?:Archives\/|edgar\/browse\/\?CIK=\d+&owner=exclude$)/i;
const NEWS=/^https:\/\/(?:www\.)?(?:prnewswire\.com|fda\.gov)\//i;
function safeURL(value){
 const s=String(value||'');
 return SEC.test(s)||NEWS.test(s)?s:'';
}
function symbols(event){
 const raw=[event&&event.ticker,...(event&&Array.isArray(event.symbols)?event.symbols:[])];
 return [...new Set(raw.filter(tickerOK))].slice(0,50);
}
function matches(event,t){
 return tickerOK(t)&&symbols(event).includes(t);
}
function tickerFromQuery(question,events=[]){
 const q=String(question||''),upper=q.toUpperCase();
 const tagged=upper.match(/\$([A-Z][A-Z0-9.-]{0,9})\b/);
 if(tagged)return tagged[1];
 const universe=new Set((Array.isArray(events)?events:[]).flatMap(symbols));
 const chunks=upper.match(/\b[A-Z][A-Z0-9.-]{0,9}\b/g)||[];
 return chunks.find(t=>universe.has(t))||null;
}
function precision(event){
 if(event.kind==='price')return {at:String(event.price_asof||'').slice(0,10),label:'closing date'};
 if(event.kind==='13f')return {at:String(event.filed||event.event_at||'').slice(0,10),label:'filing date'};
 if(event.kind==='8k'&&!/[T ]\d\d:\d\d/.test(String(event.event_at||'')))
   return {at:String(event.filed||event.event_at||'').slice(0,10),label:'filing date'};
 if(event.kind==='news'&&!/[T ]\d\d:\d\d/.test(String(event.event_at||'')))
   return {at:String(event.event_at||'').slice(0,10),label:'publication date'};
 return {at:String(event.event_at||'').slice(0,16).replace('T',' ')+(String(event.event_at||'').includes('T')?' UTC':''),label:'timestamp'};
}
function eventNote(e,zh=false){
 if(e.kind==='13f')return zh?
   '注意：申报日期不是交易日期；13F 持仓截至 '+String(e.period_end||'季度末未提供')+'。':
   'Filing date is NOT the trade date; positions are as of '+String(e.period_end||'quarter end not provided')+'.';
 if(e.kind==='price')return zh?
   '价格数据为已发布的日收盘快照，不能当作实时价格，也没有验证盘中成交量。':
   'Published end-of-day price snapshot, not a live quote; intraday volume is not verified.';
 if(e.kind==='news')return zh?
   '新闻标题是第三方来源，尚未独立核实全文。':
   'External news headline; full article claims not independently verified.';
 return zh?'8-K 属于公司披露；需要阅读原文确认事项和影响。':'A company disclosure; read the source for actual impact and terms.';
}
function fingerprint(e){
 return String(e&&e.id||'')+'|'+String(e&&e.kind||'');
}
function collect(events,t,{limit=20,days=14,now=Date.now()}={}){
 if(!tickerOK(t)||!Array.isArray(events))return [];
 const seen=new Set(),cutoff=now-days*86400000,hi=now+300000;
 return events.filter(e=>{
   if(!e||!kinds.includes(e.kind)||!matches(e,t)||!Number.isFinite(clock(e.event_at)))return false;
   const v=clock(e.event_at),id=fingerprint(e);
   if(v<cutoff||v>hi||seen.has(id))return false;
   seen.add(id);return true;
 }).sort((a,b)=>clock(b.event_at)-clock(a.event_at)||
   kinds.indexOf(a.kind)-kinds.indexOf(b.kind)||
   fingerprint(a).localeCompare(fingerprint(b))).slice(0,Math.min(50,Math.max(1,limit)));
}
function clusters(events,t,opts={}){
 const data=collect(events,t,{limit:50,...opts});
 const blocks=[];
 for(const e of data){
   let linked=blocks.find(b=>Math.abs(clock(b[0].event_at)-clock(e.event_at))<=72*3600000);
   if(!linked){linked=[];blocks.push(linked);}
   linked.push(e);
 }
 return blocks.map(group=>({events:group,distinctKinds:[...new Set(group.map(x=>x.kind))],
   crossSignal:new Set(group.map(x=>x.kind)).size>=2,
   label:group.length>1?'Observed within 72h':'Single observed source'}));
}
function summarize(events,t,opts={}){
 const selected=collect(events,t,opts),counts={};
 for(const k of kinds)counts[k]=selected.filter(e=>e.kind===k).length;
 const related=clusters(selected,t,opts).filter(c=>c.crossSignal);
 return {ticker:t,total:selected.length,counts,relatedWindows:related.length,
   periods:related.map(c=>c.events.map(e=>e.kind)),
   earliest:selected.length?selected[selected.length-1].event_at:null,
   latest:selected.length?selected[0].event_at:null,
   sourceKinds:kinds.filter(k=>counts[k]>0)};
}
function render(events,t,zh=false,options={}){
 const selected=collect(events,t,options);
 const stats=summarize(events,t,options);
 let html='<section class="flo-event-timeline"><h3>'+
   escape(t)+' · '+(zh?'披露与行情研究时间线':'Filing & market research timeline')+
   '</h3><p class="flo-source">'+escape(zh?'基于本站最近已发布的数据，不代表实时行情或全部 SEC 申报。':'Limited to recently published site snapshots. Not live quotes or an exhaustive SEC search.')+
   '</p>';
 if(!selected.length)html+='<p>'+escape(zh?'本次摘要没有该股票的匹配记录；不能因此认定没有申报。':
   'No matching events in this limited manifest. That does not prove there were no filings.')+'</p>';
 else{
   html+='<p><b>'+selected.length+'</b> '+(zh?'条独立记录':'observations')+' · '+
     kinds.map(k=>k.toUpperCase()+': '+stats.counts[k]).join(' · ')+'</p>';
   const windows=clusters(selected,t,options).filter(g=>g.crossSignal);
   if(windows.length)html+='<p class="flo-timeline-note">'+escape(zh?
     '存在 '+windows.length+' 组 72 小时内的跨来源信号。这仅是时间接近，不说明股价由某事件导致，也不能把基金季末持仓当作当日交易。':
     windows.length+' windows contain different signal types within 72h. Time proximity is NOT causal evidence; 13F quarter-end positions are NOT filing-day trades.')+'</p>';
   html+='<ol class="flo-timeline-list">';
   for(const e of selected){
     const stamp=precision(e),src=safeURL(e.source_url);
     html+='<li class="flo-timeline-'+escape(e.kind)+'"><div><b>'+escape(e.kind.toUpperCase())+'</b> · '+
       escape(stamp.at)+' <small>('+escape(stamp.label)+')</small></div>'+
       '<p>'+escape(e.title||e.detail||'Published event')+'</p>';
     if(e.kind==='price'&&Number.isFinite(e.change_pct))
       html+='<p>'+escape((e.change_pct>=0?'+':'')+Number(e.change_pct).toFixed(2)+'%')+
         (Number.isFinite(e.price)?' · $'+escape(Number(e.price).toFixed(2)):'')+'</p>';
     if(e.kind==='13f'&&e.period_end)html+='<p>'+escape(zh?'持仓截至 ':'Positions as of ')+escape(e.period_end)+'</p>';
     html+='<p class="flo-source">'+escape(eventNote(e,zh))+'</p>';
     if(src)html+='<a target="_blank" rel="noopener noreferrer" href="'+escape(src)+'">'+
       (zh?'查看原始来源':'Read primary source')+'</a>';
     html+='</li>';
   }
   html+='</ol>';
 }
 html+='<p class="flo-timeline-note">'+escape(zh?
   '研究建议：先看各自的事件日期与申报/持仓期间，再核对 SEC 8-K 原文、13F 股数和行业行情。没有盘中行情、对照组或事件研究时，不推断因果或投资收益。':
   'Research steps: check publication time versus holding/price date, read 8-K terms, compare quarter-end 13F quantities, and use a proper event study before making any causal or trading claim.')+'</p></section>';
 const links=selected.filter(e=>safeURL(e.source_url)).slice(0,10).map(e=>
   [safeURL(e.source_url),e.kind.toUpperCase()+' · '+(e.ticker||e.manager||t)]);
 return {html,links,counts:stats.counts,facts:selected.map(e=>e.kind+' '+e.title+' '+precision(e).at),
   mood:selected.some(e=>e.kind==='8k'&&e.priority==='high')?'think':'talk',
   intents:['event-timeline'],summary:stats};
}
root.FFFloTimeline={safeURL,symbols,matches,tickerFromQuery,precision,eventNote,collect,clusters,summarize,render};
if(typeof module!=='undefined')module.exports=root.FFFloTimeline;
})(typeof globalThis!=='undefined'?globalThis:this);
