/* Flo Published Pulse — live in-page discovery of new, already-published snapshots.
 * Polls ONLY small same-origin site JSON, not EDGAR/stock APIs. No push,
 * notifications permission, remote tracking, forced page reload or auto-trading.
 */
(function(root){
'use strict';
const doc=typeof document==='undefined'?null:document;
const script=doc&&doc.currentScript&&doc.currentScript.src||'';
const BASE=script?script.replace(/[^/]*$/,''):'';
const FEED=BASE+'disclosures/data/market/flo-alerts.json';
const KEY='ff:flo-pulse:v2',INTERVAL=120000,MAX_SEEN=1000;
const KINDS=['8k','13f','news','price'];
const priority={high:3,medium:2,info:1};
const escape=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const url=v=>/^https:\/\/(?:www\.)?(?:sec\.gov|prnewswire\.com|fda\.gov)\//i.test(String(v||''))?String(v):'';
const ticker=v=>/^[A-Z][A-Z0-9.\-]{0,9}$/.test(String(v||''));
const isZH=()=>/^zh/i.test(root.navigator&&root.navigator.language||'');
const time=v=>{const x=Date.parse(v);return Number.isFinite(x)?x:0;};
const valid=e=>!!e&&KINDS.includes(e.kind)&&['high','medium','info'].includes(e.priority)
  &&typeof e.id==='string'&&e.id.length>0&&e.id.length<230
  &&time(e.event_at)>0&&(!e.ticker||ticker(e.ticker))
  &&(e.kind==='price'?(Number.isFinite(e.change_pct)&&!!e.price_asof):!!url(e.source_url));
function normalize(feed){
 if(!feed||feed.schema!==1||!Array.isArray(feed.events)||feed.events.length>300)throw Error('Invalid Flo feed');
 return feed.events.filter(valid).slice(0,150);
}
function compare(previous,feed,options={}){
 const events=normalize(feed),prior=new Set(previous&&previous.seen||[]);
 if(!previous||!previous.initialized)return {initialized:true,seen:events.map(e=>e.id).slice(-MAX_SEEN),latest:events,newEvents:[]};
 const now=options.now||Date.now();
 return {initialized:true,seen:Array.from(new Set([...(previous.seen||[]),...events.map(e=>e.id)])).slice(-MAX_SEEN),
   latest:events,newEvents:events.filter(e=>!prior.has(e.id)&&now-time(e.event_at)>=-300000&&now-time(e.event_at)<=72*3600000)};
}
function react(e){
 if(e.kind==='8k')return e.priority==='high'?'worried':'think';
 if(e.kind==='13f')return 'wave';
 if(e.kind==='price')return e.change_pct<0?'worried':'happy';
 return 'talk';
}
function watchSet(config){
 return String(config.watch||'').toUpperCase().split(/[\s,]+/).filter(ticker);
}
function shown(e,config={}){
 if(config.kinds&&config.kinds[e.kind]===false)return false;
 const watch=watchSet(config);
 return !watch.length||watch.some(t=>t===e.ticker||Array.isArray(e.symbols)&&e.symbols.includes(t));
}
function explain(e,zh=false,related=[]){
 const label=e.kind==='8k'?'SEC Form 8-K':e.kind==='13f'?'SEC Form 13F':e.kind==='price'?'Daily price change':'Published news';
 const name=e.kind==='13f'?(e.manager||'Institution'):(e.ticker||e.source_label||'');
 const data=[],notes=[];
 if(e.kind==='8k'){
   if(e.form)data.push((zh?'表单类型：':'Form: ')+escape(e.form));
   if(e.filed)data.push((zh?'SEC 提交日：':'Filed: ')+escape(e.filed));
   const tags=Array.isArray(e.topics)?e.topics.filter(x=>typeof x==='string').slice(0,6):[];
   if(tags.length)data.push((zh?'事项标签：':'Event tags: ')+tags.map(escape).join(', '));
   if(tags.includes('restatement'))notes.push(zh?'核对重述期间、涉及的财报科目和审计师说明；不要将重述等同于现金损失。':'Identify restated periods, affected statements and auditor language; a restatement is not automatically a cash loss.');
   if(tags.includes('offering'))notes.push(zh?'核对新增股份、价格、募资用途和潜在稀释；仅凭发行公告无法知道最终融资额。':'Check shares, offering terms, use of proceeds and possible dilution; an announcement need not equal completed financing.');
   if(tags.includes('debt'))notes.push(zh?'核对利率、债务到期日和融资限制条款，评估偿付现金流。':'Compare rates, debt maturities, covenants and operating cash coverage.');
   if(tags.includes('deal'))notes.push(zh?'检查交易是否已经完成、对价结构、商誉和未来整合成本。':'Check whether the transaction closed, consideration, goodwill and integration costs.');
   if(tags.includes('cyber'))notes.push(zh?'评估披露所述已知影响及未知事项，不能自行推断财务损失金额。':'Distinguish disclosed known impacts from unquantified risks; do not invent damages.');
   if(tags.includes('auditor'))notes.push(zh?'核对审计师变更原因、是否有会计分歧及 Item 4.01 所载函件，不应自动推断舞弊。':'Inspect Item 4.01 for reason, disagreements and the former auditor letter; do not presume fraud.');
   if(tags.includes('ceo')||tags.includes('cfo'))notes.push(zh?'核对高管更替生效日、临时安排和激励方案，不要假定公司战略已改变。':'Check effective date, interim appointments and incentive terms; executive changes do not prove strategy changed.');
   if(tags.includes('buyback'))notes.push(zh?'授权回购不是已执行回购，需区分授权额度、实际购买股数和融资安排。':'A buyback authorization is not execution; distinguish authorization, actual repurchases and funding.');
   if(tags.includes('guidance'))notes.push(zh?'核对新旧指引口径、GAAP 与非 GAAP、覆盖期间及管理层前瞻性声明。':'Compare old/new guidance, GAAP vs non-GAAP, covered periods and forward-looking caveats.');
   if(tags.includes('bankruptcy'))notes.push(zh?'检查破产程序类型、债务优先顺序、流动性与普通股剩余权益，不能仅凭 8-K 算清偿率。':'Check insolvency proceedings, claim priority, liquidity and residual equity; the 8-K alone does not compute recovery.');
   if(tags.includes('impairment'))notes.push(zh?'确认减值科目、税前税后影响及是否为非现金费用；减值本身不等于当期现金流出。':'Identify impaired assets, pre/post-tax effect and whether it is noncash; impairment itself is not necessarily a current cash outflow.');
   notes.push(zh?'8-K 是披露，不是投资建议；重大性标签代表筛查优先级，不代表舞弊结论。':'8-K is a disclosure, not a recommendation. Event priority is a screening category, not a fraud verdict.');
 }else if(e.kind==='13f'){
   if(e.manager)data.push((zh?'管理机构：':'Manager: ')+escape(e.manager));
   if(e.period_end)data.push((zh?'季度末持仓日期：':'Holdings as of: ')+escape(e.period_end));
   if(e.filed)data.push((zh?'申报日期：':'Filing date: ')+escape(e.filed));
   if(e.changes&&typeof e.changes==='object'){
     for(const [k,v] of Object.entries(e.changes)){
       if(!['New','Added','Reduced','Exited'].includes(k)||!Array.isArray(v))continue;
       const symbols=v.filter(ticker).slice(0,4);
       if(symbols.length)data.push(escape(k)+': '+symbols.map(escape).join(', '));
     }
   }
   notes.push(zh?'这些是季度末申报持仓，不是申报当日买卖。要判断真实变化，应比较两期股数、权重及拆股，并注意披露滞后。':'These are quarter-end reported positions, NOT trades on filing day. Compare quantities and weights across quarters, account for splits and disclosure lag.');
 }else if(e.kind==='price'){
   if(Number.isFinite(e.price))data.push((zh?'发布的日收盘价：':'Published close: ')+'$'+escape(Number(e.price).toFixed(2)));
   if(Number.isFinite(e.change_pct))data.push((zh?'单日变化：':'Daily change: ')+escape((e.change_pct>=0?'+':'')+e.change_pct.toFixed(2)+'%'));
   data.push((zh?'收盘日期：':'As of close: ')+escape(e.price_asof||''));
   notes.push(zh?'这是延迟日线信号，并非盘中实时异动；本数据没有因果分析和成交量验证。不能声称股价因某条新闻上涨或下跌。':'Delayed daily-close data, NOT live or intraday. This feed has no verified causal attribution or volume comparison; do not assert a headline caused the move.');
 }else{
   notes.push(zh?'仅呈现新闻源的标题及其来源；标题与发行人匹配不等于全文内容已核实，应结合 SEC 申报确认。':'The headline comes from a source feed, not an independent fact check. Issuer matching does not verify the article; cross-check primary SEC documents.');
 }
 const evidence=url(e.source_url);
 let out='<b>'+escape(label)+' · '+escape(name)+'</b><p><b>'+escape(e.title||'')+'</b></p>';
 if(e.detail)out+='<p>'+escape(e.detail)+'</p>';
 if(data.length)out+='<div class="flo-signal-facts"><b>'+(zh?'原始证据信息':'Published snapshot details')+'</b><ul>'+data.map(x=>'<li>'+x+'</li>').join('')+'</ul></div>';
 out+=notes.map(x=>'<p>'+escape(x)+'</p>').join('');
 // Other genuinely observed same-ticker signals, not an implied cause-effect link.
 const associated=(Array.isArray(related)?related:[]).filter(r=>valid(r)&&r.id!==e.id&&r.ticker&&r.ticker===e.ticker)
  .filter(r=>Math.abs(time(r.event_at)-time(e.event_at))<=3*86400000).slice(0,3);
 if(associated.length){
   out+='<div class="flo-signal-facts"><b>'+(zh?'同公司其他独立信号':'Other observed same-ticker signals')+'</b><ul>';
   for(const r of associated){
     out+='<li>'+escape(r.kind.toUpperCase())+' · '+escape(r.title||r.detail||'Event')+
          ' · '+escape((r.event_at||'').slice(0,16))+' UTC';
     if(url(r.source_url))out+=' · <a target="_blank" rel="noopener noreferrer" href="'+escape(url(r.source_url))+'">'+(zh?'原始来源':'Source')+'</a>';
     out+='</li>';
   }
   out+='</ul><p>'+escape(zh?'事件同时出现不代表因果关系，仍需检查披露时间、盘前盘后与市场其他因素。':
     'Co-occurrence is NOT causality. Check filing times, market hours and other drivers.')+'</p></div>';
 }
 out+='<p class="flo-source">'+escape(e.event_at.slice(0,16))+' UTC · '+escape(e.source_label||'')+' · '+escape(e.scope||'')+'</p>';
 if(evidence)out+='<div class="flo-links"><a target="_blank" rel="noopener noreferrer" href="'+escape(evidence)+'">'+
  (zh?'查看原始 SEC / 新闻资料':'Read original SEC / news source')+'</a></div>';
 return out;
}
let seen=[],initialized=false,settings={quiet:false,watch:'',kinds:{'8k':true,'13f':true,news:true,price:true}};
let items=[],bubble=null,inbox=null,pill=null,active=false,busy=false,timer=null,wait=INTERVAL,version='',unread=0,lastError='',latestBuild='',lastPopupAt=0,scanHealth={};
function storage(){
 try{root.localStorage&&root.localStorage.setItem(KEY,JSON.stringify({initialized,seen:seen.slice(-MAX_SEEN),settings,lastPopupAt}));}catch(_){}
}
function restore(){
 try{
   const d=JSON.parse(root.localStorage&&root.localStorage.getItem(KEY)||'null');
   if(!d)return;
   initialized=!!d.initialized;
   lastPopupAt=Number.isFinite(d.lastPopupAt)&&d.lastPopupAt>0?d.lastPopupAt:0;
   seen=Array.isArray(d.seen)?d.seen.filter(x=>typeof x==='string'&&x.length<230).slice(-MAX_SEEN):[];
   if(d.settings){
     settings.quiet=!!d.settings.quiet;
     settings.watch=String(d.settings.watch||'').toUpperCase().replace(/[^A-Z0-9.,\s-]/g,'').slice(0,90);
     if(d.settings.kinds)KINDS.forEach(k=>{settings.kinds[k]=d.settings.kinds[k]!==false;});
   }
 }catch(_){}
}
function el(tag,cls,text){
 const n=doc.createElement(tag);
 if(cls)n.className=cls;
 if(text!==undefined)n.textContent=text;
 return n;
}
function closeToast(){if(bubble)bubble.hidden=true;}
function openEvent(event){
 closeToast();if(inbox)inbox.hidden=true;
 if(root.FFMascot&&root.FFMascot.showSignal)root.FFMascot.showSignal(event,explain(event,isZH(),items));
 else if(url(event.source_url))root.open(url(event.source_url),'_blank','noopener');
}
function toast(event,count){
 if(!bubble||settings.quiet)return;
 bubble.replaceChildren();bubble.dataset.kind=event.kind;
 const head=el('div','flo-pulse-head'),label=el('b','',event.kind.toUpperCase()+' · '+(event.ticker||event.manager||'Filing'));
 const dismiss=el('button','','×');dismiss.type='button';dismiss.setAttribute('aria-label','Dismiss alert');
 dismiss.addEventListener('click',closeToast);head.append(label,dismiss);
 const buttons=el('div','flo-pulse-actions'),detail=el('button','',isZH()?'让 Flo 分析':'Ask Flo'),all=el('button','',isZH()?'所有提示 · ':'Inbox · '+count),mute=el('button','',isZH()?'静音':'Mute');
 detail.addEventListener('click',()=>openEvent(event));
 all.addEventListener('click',()=>showInbox(true));
 mute.addEventListener('click',()=>{settings.quiet=true;storage();closeToast();showInbox(true);});
 buttons.append(detail,all,mute);
 bubble.append(head,el('p','',event.title||'New published event'),el('small','',event.event_at.slice(0,16)+' UTC'),buttons);
 bubble.hidden=false;
}
function showInbox(show){if(!inbox)return;inbox.hidden=!show;if(show)renderInbox();}
function renderInbox(){
 if(!inbox)return;
 inbox.replaceChildren();
 const head=el('div','flo-pulse-head'),name=el('b','',isZH()?'Flo 新扫描收件箱':'Flo Published Pulse'),dismiss=el('button','','×');
 dismiss.setAttribute('aria-label','Close alerts');dismiss.addEventListener('click',()=>showInbox(false));
 head.append(name,dismiss);
 inbox.append(head,el('p','flo-pulse-note',isZH()?'首次访问不弹旧提醒；之后只检测新发布内容。静音和过滤设置保存在当前浏览器。':'First visit records a baseline. Only later newly published events trigger alerts. Settings are browser-local.'));
 if(lastError)inbox.append(el('p','flo-pulse-note',(isZH()?'数据不可用：':'Feed unavailable: ')+lastError));
 else if(latestBuild)inbox.append(el('p','flo-pulse-note',(isZH()?'最近网站数据构建：':'Latest site build: ')+latestBuild+' UTC'));
 for(const kind of KINDS){
   const h=scanHealth[kind];
   if(!h||typeof h!=='object')continue;
   const status=String(h.status||'unknown').slice(0,20),date=String(h.latest_filing_date||'').slice(0,12);
   const attempt=String(h.last_attempt||'').slice(0,16),success=String(h.last_success||'').slice(0,16);
   inbox.append(el('p','flo-pulse-note',kind.toUpperCase()+' · '+status+
     (date?(isZH()?' · 最新申报 ':' · latest filed ')+date:'')+
     (attempt?(isZH()?' · 尝试 ':' · attempt ')+attempt:'')+
     (success?(isZH()?' · 成功/部分成功 ':' · success/partial ')+success:'')+
     (h.failed_queue?(isZH()?' · 待重试 ':' · retry queue ')+h.failed_queue:'')));
 }
 const controls=el('div','flo-pulse-actions'),muteLabel=el('label',''),quiet=el('input');
 quiet.type='checkbox';quiet.checked=settings.quiet;quiet.addEventListener('change',()=>{settings.quiet=quiet.checked;storage();if(settings.quiet)closeToast();});
 muteLabel.append(quiet,doc.createTextNode(isZH()?' 安静模式':' Quiet mode'));
 const watch=el('input');watch.type='text';watch.value=settings.watch;watch.placeholder='OKLO, IREN, CRWV';watch.setAttribute('aria-label','Ticker watch filter');
 watch.addEventListener('change',()=>{settings.watch=watch.value.toUpperCase().replace(/[^A-Z0-9.,\s-]/g,'').slice(0,90);storage();renderInbox()});
 controls.append(muteLabel,watch);
 const types=el('div','flo-pulse-types');
 for(const k of KINDS){
   const label=el('label',''),box=el('input');box.type='checkbox';box.checked=settings.kinds[k]!==false;
   box.addEventListener('change',()=>{settings.kinds[k]=box.checked;storage();renderInbox()});
   label.append(box,doc.createTextNode(' '+(k==='8k'?'8-K':k==='13f'?'13F':k==='news'?'News':'Daily close')));
   types.append(label);
 }
 inbox.append(controls,types);
 const matches=items.filter(e=>shown(e,settings)).slice(0,45);
 if(!matches.length)inbox.append(el('p','',isZH()?'没有匹配的新发布数据。':'No matching published events.'));
 for(const e of matches){
   const row=el('div','flo-pulse-item'),button=el('button','',e.kind.toUpperCase()+' · '+(e.title||'Untitled'));
   button.addEventListener('click',()=>openEvent(e));
   row.append(button,el('small','',(e.ticker||e.manager||'')+' · '+e.event_at.slice(0,16)+' UTC'));
   inbox.append(row);
 }
}
function schedule(){
 if(timer)clearTimeout(timer);
 if(active&&doc&&doc.visibilityState!=='hidden')timer=setTimeout(poll,wait);
}
async function poll(){
 if(!active||busy||(doc&&doc.visibilityState==='hidden')||(root.navigator&&root.navigator.onLine===false))return;
 busy=true;
 try{
   const response=await root.fetch(FEED+'?t='+Math.floor(Date.now()/INTERVAL),{cache:'no-store',credentials:'same-origin'});
   if(!response.ok)throw Error('HTTP '+response.status);
   const feed=await response.json();
   const diff=compare({seen,initialized},feed);
   initialized=diff.initialized;seen=diff.seen;items=diff.latest;
   if(version!==feed.generated_at){version=feed.generated_at;root.FFMascot&&root.FFMascot.refreshSignalData&&root.FFMascot.refreshSignalData();}
   latestBuild=feed.generated_at||'';
   scanHealth=feed.scan_health&&typeof feed.scan_health==='object'?feed.scan_health:{};
   const arrivals=diff.newEvents.filter(e=>shown(e,settings));
   if(arrivals.length){
     unread+=arrivals.length;
     arrivals.sort((a,b)=>priority[b.priority]-priority[a.priority]||time(b.event_at)-time(a.event_at));
     const top=arrivals[0];
     // Rate-limit visual interruption to once per 5 minutes across page loads.
     // Unseen events still go to the inbox and its counter.
     if(!settings.quiet&&Date.now()-lastPopupAt>=300000){
       toast(top,arrivals.length);
       if(root.FFMascot&&root.FFMascot.signalReaction)root.FFMascot.signalReaction(react(top),top);
       lastPopupAt=Date.now();
     }
     if(pill)pill.textContent=(isZH()?'Flo · 新事件 ':'Flo · New ')+unread;
     if(inbox&&!inbox.hidden)renderInbox();
   }
   lastError='';wait=INTERVAL;storage();
 }catch(e){
   lastError=String(e.message||'Unavailable').slice(0,80);
   wait=Math.min(wait*2,15*60000);
   if(inbox&&!inbox.hidden)renderInbox();
 }finally{busy=false;schedule();}
}
function style(){
 const s=el('style');s.id='flo-pulse-style';
 s.textContent='.flo-pulse-toast,.flo-pulse-list{position:fixed;right:18px;bottom:112px;z-index:9005;width:min(355px,calc(100vw - 25px));background:var(--surface,#fff);color:var(--ink,#222);border:1px solid var(--line,#ccc);border-radius:13px;padding:12px;box-shadow:0 11px 30px #0003;font:12px/1.5 Arial,sans-serif}.flo-pulse-toast[hidden],.flo-pulse-list[hidden]{display:none}.flo-pulse-toast{border-left:4px solid var(--accent,#17734a);animation:flo-pulse-arrive .3s ease-out}.flo-pulse-toast[data-kind="8k"]{border-left-color:#cf5a57}.flo-pulse-toast[data-kind="13f"]{border-left-color:#5680cb}.flo-pulse-toast[data-kind="price"]{border-left-color:#dca13b}.flo-pulse-head,.flo-pulse-actions{display:flex;gap:7px;justify-content:space-between;align-items:center;flex-wrap:wrap}.flo-pulse-toast p{margin:7px 0}.flo-pulse-toast button,.flo-pulse-list button,.flo-pulse-pill{border:1px solid var(--line,#ccc);background:var(--surface,#fff);color:var(--ink,#222);padding:4px 8px;border-radius:7px;cursor:pointer;font:12px Arial,sans-serif}.flo-pulse-list{max-height:55vh;overflow:auto}.flo-pulse-list .flo-pulse-item{padding:6px 0;border-bottom:1px solid var(--line,#ccc)}.flo-pulse-list .flo-pulse-item button{text-align:left}.flo-pulse-list small{display:block;color:var(--muted,#777)}.flo-pulse-types{display:flex;gap:7px;flex-wrap:wrap;margin:8px 0}.flo-pulse-types label{white-space:nowrap;font-size:11px}.flo-pulse-list input[type=text]{width:140px;max-width:100%;padding:5px;color:inherit;background:inherit;border:1px solid var(--line,#ccc);border-radius:6px}.flo-pulse-pill{position:fixed;right:110px;bottom:29px;z-index:9004;box-shadow:0 3px 10px #0002}.flo-pulse-note{font-size:11px;color:var(--muted,#777)}.flo-signal-facts ul{padding-left:18px;margin:4px 0 7px}.flo-signal-facts li{margin:3px 0}@keyframes flo-pulse-arrive{from{opacity:0;transform:translateY(13px) scale(.97)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.flo-pulse-toast{animation:none}}@media(max-width:560px){.flo-pulse-list,.flo-pulse-toast{right:8px;bottom:85px}.flo-pulse-pill{right:74px;bottom:14px}}';
 doc.head.append(s);
}
function intent(q){
 return /最近.{0,9}(?:扫描|提醒|新消息|事件|8.?k|13f)|有什么新(?:披露|新闻|扫描|提醒|8.?k|13f)|新扫描.{0,14}(?:什么|有哪些|结果)|(?:what(?:'s| is) new|new alerts|recent alerts|what changed since|recent scanner|latest published pulse|show notifications|alert inbox)/i.test(String(q||''));
}
function report(q,zh=false){
 const query=String(q||''),upper=query.toUpperCase();
 const matched=upper.match(/\$([A-Z]{1,7})\b/)||upper.match(/\b(?:NVDA|AAPL|MSFT|OKLO|IREN|CRWV|TSLA|META|AMZN)\b/);
 const tickerQuery=matched?matched[1]||matched[0]:null;
 const type=/8.?k/i.test(query)?'8k':/13f/i.test(query)?'13f':/异动|价格|price|move/i.test(query)?'price':null;
 const list=items.filter(e=>(!type||e.kind===type)&&(!tickerQuery||e.ticker===tickerQuery||(e.symbols||[]).includes(tickerQuery))).slice(0,7);
 let html='<b>'+escape(zh?'Flo 最近发布的扫描信息':'Flo latest published observations')+'</b><p>'+
   escape(zh?'内容来自网站已经发布的扫描数据；不是实时 SEC 推送或盘中行情。':'These are already published site snapshots, not realtime SEC pushes or intraday quotes.')+'</p>';
 if(!initialized)html+='<p>'+escape(zh?'尚未取得可靠事件摘要。':'No validated alert snapshot yet.')+'</p>';
 else if(!list.length)html+='<p>'+escape(zh?'当前摘要没有匹配记录；不能据此断定没有新申报。':'No matching observation in this bounded feed; it does not prove no new filings.')+'</p>';
 const links=[];
 for(const e of list){
   html+='<p><b>'+escape(e.kind.toUpperCase()+' · '+(e.ticker||e.manager||''))+'</b> · '+
     escape(e.title||'')+' <small>'+escape(e.event_at.slice(0,16))+' UTC</small></p>';
   if(url(e.source_url))links.push([url(e.source_url),e.kind.toUpperCase()+' · '+(e.ticker||e.manager||'')]);
 }
 if(latestBuild)html+='<p class="flo-source">'+escape(zh?'摘要构建时间：':'Manifest built: ')+escape(latestBuild)+' UTC</p>';
 if(lastError)html+='<p>'+escape(zh?'最近获取失败：':'Last fetch issue: ')+escape(lastError)+'</p>';
 return {html,links,facts:list.map(e=>e.kind+' '+(e.ticker||e.manager||'')+' '+e.title+' '+e.event_at),
  mood:list.some(e=>e.kind==='8k'&&e.priority==='high')?'think':'talk',intents:['published-pulse']};
}
function start(){
 if(active||!doc||!root.fetch)return;
 active=true;restore();style();
 bubble=el('div','flo-pulse-toast');bubble.hidden=true;bubble.setAttribute('role','status');
 inbox=el('div','flo-pulse-list');inbox.hidden=true;inbox.setAttribute('role','region');inbox.setAttribute('aria-label','Flo alerts');
 pill=el('button','flo-pulse-pill',isZH()?'Flo · 已发布扫描':'Flo · Published');
 pill.type='button';pill.addEventListener('click',()=>{unread=0;showInbox(inbox.hidden);if(inbox&&!inbox.hidden)pill.textContent=isZH()?'Flo · 已发布扫描':'Flo · Published'});
 doc.body.append(bubble,inbox,pill);
 doc.addEventListener('visibilitychange',()=>{if(doc.visibilityState==='hidden'){if(timer)clearTimeout(timer)}else poll()});
 root.addEventListener('online',poll);
 poll();
}
root.FFFloAlerts={valid,normalize,compare,react,shown,explain,intent,report,start,poll,
 getState:()=>({initialized,seen:seen.slice(),settings:JSON.parse(JSON.stringify(settings)),events:items.slice(),lastError,latestBuild,scanHealth}),
 stop(){active=false;if(timer)clearTimeout(timer);}};
if(typeof module!=='undefined')module.exports=root.FFFloAlerts;
if(doc){if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',start);else start();}
})(typeof globalThis!=='undefined'?globalThis:this);
