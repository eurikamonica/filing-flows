/* Flo Published Pulse — in-page polls of a small first-party feed.
 * No SSE backend, no browser push permission, no live-price assertions.
 */
(function(root){
'use strict';
const doc=typeof document==='undefined'?null:document;
const script=doc&&doc.currentScript&&doc.currentScript.src||'';
const BASE=script?script.replace(/[^/]*$/,''):'';
const FEED=BASE+'disclosures/data/market/flo-alerts.json';
const KEY='ff:flo-pulse:v1',MS=120000,MAX_SEEN=320;
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const secureUrl=v=>/^https:\/\/(?:www\.)?(?:sec\.gov|prnewswire\.com|fda\.gov)\//i.test(String(v||''))?String(v):'';
const validTicker=v=>/^[A-Z][A-Z0-9.\-]{0,9}$/.test(String(v||''));
const zhen=()=>/^zh/i.test(root.navigator?.language||'');
const ms=t=>{const n=Date.parse(t);return Number.isFinite(n)?n:0;};
function valid(e){
 return !!e&&['8k','13f','news','price'].includes(e.kind)&&
 ['high','medium','info'].includes(e.priority)&&typeof e.id==='string'&&e.id.length<230&&
 ms(e.event_at)>0&&(!e.ticker||validTicker(e.ticker))&&
 (e.kind==='price'?(Number.isFinite(e.change_pct)&&!!e.price_asof):!!secureUrl(e.source_url));
}
function normalize(feed){
 if(!feed||feed.schema!==1||!Array.isArray(feed.events)||feed.events.length>300)throw Error('Invalid Flo feed');
 return feed.events.filter(valid).slice(0,150);
}
function compare(old,feed,options={}){
 const current=normalize(feed),known=new Set(old.seen||[]);
 if(!old.initialized)return {initialized:true,seen:current.map(x=>x.id).slice(-MAX_SEEN),latest:current,newEvents:[]};
 const at=options.now||Date.now();
 return {initialized:true,seen:Array.from(new Set([...(old.seen||[]),...current.map(x=>x.id)])).slice(-MAX_SEEN),
   latest:current,newEvents:current.filter(x=>!known.has(x.id)&&at-ms(x.event_at)<=72*3600e3&&ms(x.event_at)<=at+300000)};
}
function react(e){
 if(e.kind==='8k')return e.priority==='high'?'worried':'think';
 if(e.kind==='13f')return 'wave';
 if(e.kind==='price')return e.change_pct<0?'worried':'happy';
 return 'talk';
}
function explain(e,zh){
 const label=e.kind==='8k'?'SEC 8-K':e.kind==='13f'?'SEC 13F':e.kind==='price'?'Daily-close move':'News';
 const base={
  '8k':zh?'8-K 是公司向 SEC 提交的公告，不等于买入或卖出信号。需逐项核对事项、实际金额、完成状态、融资和盈利影响。':'An 8-K is a filing, not a trade recommendation. Inspect the event, scope, financing, cash flow and original text.',
  '13f':zh?'13F 显示季度末机构申报持仓。申报日并不是买卖日；分析应比较前后两期股数、权重及滞后。':'13F shows quarter-end positions, not the trade date. Compare shares and weights across quarters; disclosures are delayed.',
  'price':zh?'本信号使用延迟日收盘数据，并非实时股价。与同期 SEC 申报和成交量对照；不能仅凭涨跌推断新闻原因。':'A delayed daily-close observation, NOT live price action. Cross-check volume and dated filings; price movement alone does not prove a cause.',
  'news':zh?'本数据只是新闻原始标题，不保证标题内容已经证实。请查看来源与公司匹配，必要时与 SEC 文件交叉核对。':'A source headline, not independent factual verification. Read the article and cross-check issuer identification and SEC filings.'
 };
 let out='<b>'+esc(label)+' · '+esc(e.ticker||e.manager||'')+'</b>'+
 '<p><b>'+esc(e.title||'')+'</b></p><p>'+esc(e.detail||'')+'</p>'+
 '<p>'+esc(base[e.kind])+'</p>'+
 '<p class="flo-source">'+esc((e.event_at||'').slice(0,16))+' UTC · '+esc(e.source_label||'')+
 ' · '+esc(e.scope||'')+'</p>';
 const u=secureUrl(e.source_url);
 if(u)out+='<div class="flo-links"><a target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">'+
 (zh?'查看 SEC / 新闻原始证据':'Open original evidence')+'</a></div>';
 return out;
}
function watchSet(cfg){return String(cfg.watch||'').toUpperCase().split(/[\s,]+/).filter(Boolean);}
function shown(e,cfg){const names=watchSet(cfg);return !names.length||names.includes(e.ticker);}
let seen=[],initialized=false,settings={quiet:false,watch:''},items=[],page=null,bubble=null,list=null,badge=null,active=false,busy=false,timer=null,interval=MS,count=0,version='';
function store(){
 try{root.localStorage?.setItem(KEY,JSON.stringify({initialized,seen:seen.slice(-MAX_SEEN),settings}));}catch(_){}
}
function restore(){
 let p;try{p=JSON.parse(root.localStorage?.getItem(KEY)||'null')}catch(_){}
 if(!p)return;
 initialized=!!p.initialized;
 seen=Array.isArray(p.seen)?p.seen.filter(x=>typeof x==='string'&&x.length<230).slice(-MAX_SEEN):[];
 if(p.settings){settings.quiet=!!p.settings.quiet;settings.watch=String(p.settings.watch||'').toUpperCase().replace(/[^A-Z0-9.,\s-]/g,'').slice(0,90);}
}
function node(tag,cls,content){const e=doc.createElement(tag);if(cls)e.className=cls;if(content!==undefined)e.textContent=content;return e;}
function closeBubble(){if(bubble)bubble.hidden=true;}
function ask(e){closeBubble();if(list)list.hidden=true;
 if(root.FFMascot?.showSignal)root.FFMascot.showSignal(e,explain(e,zhen()));
 else if(secureUrl(e.source_url))root.open(secureUrl(e.source_url),'_blank','noopener');
}
function renderBubble(e,n){
 if(!bubble||settings.quiet)return;
 bubble.replaceChildren();bubble.dataset.kind=e.kind;
 const head=node('div','flo-pulse-head');head.append(node('b','',e.kind.toUpperCase()+' · '+(e.ticker||'Published')));
 const x=node('button','flo-pulse-x','×');x.setAttribute('aria-label','Dismiss signal');x.addEventListener('click',closeBubble);head.append(x);
 bubble.append(head,node('p','',e.title),node('small','',String(e.event_at).slice(0,16)+' UTC'));
 const action=node('div','flo-pulse-actions'),a=node('button','','Ask Flo'),b=node('button','','Inbox · '+n),c=node('button','','Mute');
 a.addEventListener('click',()=>ask(e));b.addEventListener('click',()=>showInbox(true));
 c.addEventListener('click',()=>{settings.quiet=true;store();closeBubble();showInbox(true)});
 action.append(a,b,c);bubble.append(action);bubble.hidden=false;
}
function showInbox(flag){if(!list)return;list.hidden=!flag;if(flag)drawInbox();}
function drawInbox(){
 if(!list)return;list.replaceChildren();
 const bar=node('div','flo-pulse-head'),title=node('b','',zhen()?'Flo 新扫描信号':'Flo Published Signals'),cross=node('button','','×');
 cross.setAttribute('aria-label','Close alerts');cross.addEventListener('click',()=>showInbox(false));bar.append(title,cross);list.append(bar);
 list.append(node('p','flo-pulse-note',zhen()?'首次访问不推送旧消息；仅检查新发布的数据。不代表实时交易行情。':'First visit establishes baseline; later published changes appear here. Not a live market feed.'));
 const controls=node('div','flo-pulse-actions'),label=node('label',''),quiet=node('input','');
 quiet.type='checkbox';quiet.checked=settings.quiet;quiet.addEventListener('change',()=>{settings.quiet=quiet.checked;store();if(settings.quiet)closeBubble()});
 label.append(quiet,doc.createTextNode(' Quiet popups'));const watch=node('input','');watch.type='text';watch.value=settings.watch;
 watch.placeholder='OKLO, IREN, CRWV';watch.setAttribute('aria-label','Ticker watch filter');
 watch.addEventListener('change',()=>{settings.watch=watch.value.toUpperCase().replace(/[^A-Z0-9.,\s-]/g,'').slice(0,90);store();drawInbox()});
 controls.append(label,watch);list.append(controls);
 const matches=items.filter(e=>shown(e,settings)).slice(0,45);
 if(!matches.length)list.append(node('p','',zhen()?'目前没有匹配信号。':'No published matching signals.'));
 matches.forEach(e=>{const r=node('div','flo-pulse-item'),a=node('button','',e.kind.toUpperCase()+' · '+e.title);
 a.addEventListener('click',()=>ask(e));r.append(a,node('small','',(e.ticker||'')+' · '+String(e.event_at).slice(0,16)+' UTC'));list.append(r)});
}
async function poll(){
 if(!active||busy||doc?.visibilityState==='hidden'||root.navigator?.onLine===false)return;
 busy=true;
 try{
  const r=await root.fetch(FEED+'?t='+Date.now(),{cache:'no-store',credentials:'same-origin'});
  if(!r.ok)throw Error('Published alert manifest HTTP '+r.status);
  const data=await r.json(),diff=compare({seen,initialized},data);
  initialized=diff.initialized;seen=diff.seen;items=diff.latest;
  if(version!==data.generated_at){version=data.generated_at;root.FFMascot?.refreshSignalData?.();}
  const incoming=diff.newEvents.filter(e=>shown(e,settings));
  if(incoming.length){
   count+=incoming.length;
   const importance={high:3,medium:2,info:1};
   incoming.sort((a,b)=>importance[b.priority]-importance[a.priority]||ms(b.event_at)-ms(a.event_at));
   const best=incoming[0];
   if(!settings.quiet)renderBubble(best,incoming.length);
   root.FFMascot?.signalReaction?.(react(best),best);
   badge.textContent='Flo · '+count+' new';
   if(!list.hidden)drawInbox();
  }
  interval=MS;store();
 }catch(_){interval=Math.min(interval*2,15*60000);}
 finally{busy=false;schedule();}
}
function schedule(){if(timer)clearTimeout(timer);if(active&&doc?.visibilityState!=='hidden')timer=setTimeout(poll,interval);}
function css(){
 const style=node('style');style.id='flo-pulse-style';
 style.textContent='.flo-pulse-toast,.flo-pulse-list{position:fixed;right:18px;bottom:112px;z-index:9005;width:min(345px,calc(100vw - 25px));background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ccc);border-radius:13px;padding:12px;box-shadow:0 11px 30px #0003;font:12px/1.5 Arial,sans-serif}.flo-pulse-toast[hidden],.flo-pulse-list[hidden]{display:none}.flo-pulse-toast{border-left:4px solid var(--accent,#17734a);animation:flo-pulse-arrive .3s ease-out}.flo-pulse-toast[data-kind="8k"]{border-left-color:#c66}.flo-pulse-toast[data-kind="13f"]{border-left-color:#5680cb}.flo-pulse-toast[data-kind="price"]{border-left-color:#dca13b}.flo-pulse-head,.flo-pulse-actions{display:flex;gap:7px;justify-content:space-between;align-items:center;flex-wrap:wrap}.flo-pulse-toast p{margin:7px 0}.flo-pulse-toast button,.flo-pulse-list button,.flo-pulse-pill{border:1px solid var(--line,#ccc);background:var(--surface,#fff);color:var(--ink,#222);padding:4px 8px;border-radius:7px;cursor:pointer;font:12px Arial,sans-serif}.flo-pulse-list{max-height:52vh;overflow:auto}.flo-pulse-list .flo-pulse-item{padding:6px 0;border-bottom:1px solid var(--line,#ccc)}.flo-pulse-list .flo-pulse-item button{text-align:left}.flo-pulse-list small{display:block;color:var(--muted,#777)}.flo-pulse-list input[type=text]{width:140px;max-width:100%;padding:5px;color:inherit;background:inherit;border:1px solid var(--line,#ccc);border-radius:6px}.flo-pulse-pill{position:fixed;right:110px;bottom:29px;z-index:9004;box-shadow:0 3px 10px #0002}.flo-pulse-note{font-size:11px;color:var(--muted,#777)}@keyframes flo-pulse-arrive{from{opacity:0;transform:translateY(13px) scale(.97)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.flo-pulse-toast{animation:none}}@media(max-width:560px){.flo-pulse-list,.flo-pulse-toast{right:8px;bottom:85px}.flo-pulse-pill{right:74px;bottom:14px}}';
 doc.head.append(style);
}
function start(){
 if(active||!doc||!root.fetch)return;
 active=true;restore();css();
 bubble=node('div','flo-pulse-toast');bubble.hidden=true;bubble.setAttribute('role','status');
 list=node('div','flo-pulse-list');list.hidden=true;list.setAttribute('role','region');list.setAttribute('aria-label','Flo signal inbox');
 badge=node('button','flo-pulse-pill',zhen()?'Flo · 已发布扫描':'Flo · Published');badge.type='button';badge.addEventListener('click',()=>showInbox(list.hidden));
 doc.body.append(bubble,list,badge);
 doc.addEventListener('visibilitychange',()=>{if(doc.visibilityState==='hidden'){if(timer)clearTimeout(timer)}else poll()});
 root.addEventListener('online',poll);poll();
}
root.FFFloAlerts={valid,normalize,compare,react,explain,start,poll,getState:()=>({initialized,seen:seen.slice(),settings:{...settings},events:items.slice()}),stop(){active=false;if(timer)clearTimeout(timer)}};
if(typeof module!=='undefined')module.exports=root.FFFloAlerts;
if(doc){if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',start);else start();}
})(typeof globalThis!=='undefined'?globalThis:this);
