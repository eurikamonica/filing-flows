/* Flo five-minute momentum — browser reads only a permitted Supabase projection.
 * The data is produced server-side with authenticated intraday minute candles.
 * Never fall back to yesterday's daily price changes or assume missing Russell
 * constituent lists are complete.
 */
(function(root){
'use strict';
const doc=typeof document==='undefined'?null:document;
const SITEBASE=doc&&doc.currentScript&&doc.currentScript.src?
  String(doc.currentScript.src).replace(/[^/]*$/,''):'';
const SCOPES=['sp500','russell1000','russell2000'];
const LABELS={sp500:'S&P 500',russell1000:'Russell 1000',russell2000:'Russell 2000'};
const TIMER=60000,STALE=12*60000,NOTIFY=5*60000;
const esc=x=>String(x==null?'':x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const valid=x=>typeof x==='number'&&Number.isFinite(x);
const symbol=x=>/^[A-Z][A-Z0-9.-]{0,9}$/.test(String(x||''));
const date=x=>/^\d{4}-\d\d-\d\d$/.test(String(x||''));
const stamp=x=>{const n=Date.parse(x);return Number.isFinite(n)?n:NaN;};
const configKey='ff:flo-5m-settings:v1';
const settings={universe:'sp500',minGain:0,minTurnover:0,minStreak:1,limit:20,quiet:false};
let feed=null,status='unconfigured',error='',panel=null,pill=null,toast=null,started=false,busy=false,timer=null;
let previousTop='',initialized=false,lastNotification=0,server=null;
function persist(){try{root.localStorage?.setItem(configKey,JSON.stringify(settings));}catch(_){}}
function restore(){try{const d=JSON.parse(root.localStorage?.getItem(configKey)||'{}');
 if(SCOPES.includes(d.universe))settings.universe=d.universe;
 if(valid(d.minGain)&&d.minGain>=0&&d.minGain<=100)settings.minGain=d.minGain;
 if(valid(d.minTurnover)&&d.minTurnover>=0&&d.minTurnover<=1e9)settings.minTurnover=d.minTurnover;
 if(Number.isInteger(d.minStreak)&&d.minStreak>=1&&d.minStreak<=20)settings.minStreak=d.minStreak;
 if(Number.isInteger(d.limit)&&d.limit>=5&&d.limit<=60)settings.limit=d.limit;
 settings.quiet=d.quiet===true;
 }catch(_){}}
function scopeInfo(data,scope){
 const s=data&&data.universes&&data.universes[scope];
 if(!s||!Array.isArray(s.leaders))return null;
 return s;
}
function classify(data,scope= settings.universe,now=Date.now()){
 if(!data||data.schema!==1||!SCOPES.includes(scope))return {ok:false,reason:'unavailable'};
 const age=now-stamp(data.generated_at);
 if(!Number.isFinite(age)||age< -5*60000||age>STALE)
   return {ok:false,reason:'stale',age:Number.isFinite(age)?age:null};
 const s=scopeInfo(data,scope);
 if(!s||s.membership_status==='unavailable'||!s.universe_size)
   return {ok:false,reason:'membership_unavailable'};
 const membershipAge=now-Date.parse(s.membership_asof+'T00:00:00Z');
 if(!date(s.membership_asof)||membershipAge< -86400000||membershipAge>111*86400000)
   return {ok:false,reason:'membership_stale'};
 return {ok:true,scope,age,partial:s.ranking_status!=='complete_enough',
   coverage:valid(s.coverage_pct)?s.coverage_pct:0};
}
function select(data,options={},now=Date.now()){
 const opt={...settings,...options},state=classify(data,opt.universe,now),s=scopeInfo(data,opt.universe);
 if(!state.ok)return {state,rows:[]};
 const rows=(s.leaders||[]).filter(x=>
   x&&symbol(x.ticker)&&valid(x.five_min_pct)&&valid(x.price)&&x.price>0&&
   valid(x.turnover_5m_usd)&&x.turnover_5m_usd>=0&&
   x.five_min_pct>=opt.minGain&&x.five_min_pct>0&&
   x.turnover_5m_usd>=opt.minTurnover&&
   (x.volume_complete||opt.minTurnover===0)&&
   Number.isInteger(x.streak)&&x.streak>=opt.minStreak&&
   stamp(x.asof)-stamp(x.prev_asof)===300000)
   .sort((a,b)=>b.five_min_pct-a.five_min_pct||b.turnover_5m_usd-a.turnover_5m_usd||a.ticker.localeCompare(b.ticker))
   .slice(0,Math.max(5,Math.min(60,opt.limit)));
 return {state,rows,scope:s};
}
function parseQuestion(q){
 const s=String(q||'');
 let universe=settings.universe;
 if(/russell\s*2000|rus\s*2000|罗素\s*2000|r2000/i.test(s))universe='russell2000';
 else if(/russell\s*1000|rus\s*1000|罗素\s*1000|r1000/i.test(s))universe='russell1000';
 else if(/s&p\s*500|sp\s*500|标普\s*500/i.test(s))universe='sp500';
 return universe;
}
function intent(q){return /(?:5|五)\s*分钟.{0,16}(?:涨幅|涨最多|上涨|异动|扫描|榜|排行)|(?:涨幅|异动).{0,16}(?:5|五)\s*分钟|(?:five.minute|5.minute|5m).{0,18}(?:mover|gainer|momentum|scan|stock|ranking)|(?:russell|rus\s*2000|罗素|s&p\s*500|标普).{0,16}(?:涨幅榜|涨最多|分钟扫描)|(?:接力扫描|接力榜单)/i.test(String(q||''));}
function describeServiceIssue(code,lang='zh'){
 const zh=lang==='zh';
 switch(String(code||'')){
 case 'schema_missing':return zh?
   '五分钟扫描数据库表尚未准备好。站点管理员需在正确的 Supabase 项目执行 db/flo-momentum.sql，并确认 PostgREST API 已识别该表。':
   'The 5m data table is not ready. An administrator must apply db/flo-momentum.sql to the correct Supabase project and confirm PostgREST sees it.';
 case 'endpoint_not_found':return zh?
   'Supabase 5m 数据接口返回 404：请核对站点连接的项目地址，以及 flo_momentum_scan 表是否已部署。':
   '5m endpoint returned 404. Verify the configured Supabase project and that flo_momentum_scan exists.';
 case 'unauthorized':return zh?
   '行情数据接口鉴权失败（401/403）。检查 Supabase 公共连接配置与表的 SELECT/RLS 策略；不要公开服务端密钥。':
   'Minute-feed authorization failed (401/403). Check the public client configuration and SELECT/RLS policies; never expose service credentials.';
 case 'no_public_row':return zh?
   '数据表已可访问，但目前没有获准公开的数据快照。检查五分钟生产任务、数据来源授权与 RLS is_public 状态。':
   'Feed is accessible but no publicly authorized snapshot exists. Check the producer, market-data license and is_public gate.';
 case 'site_config_missing':return zh?
   '网站尚未提供可用的 Supabase 公共连接配置；请检查站点构建时的 SUPABASE_URL 和 SUPABASE_ANON_KEY。':
   'Public Supabase configuration is missing from the site build.';
 case 'network_error':return zh?
   '分钟行情暂时无法连接；可能是网络、浏览器扩展或服务故障。':
   'Minute-feed connection failed. Check the network, browser extensions or provider status.';
 default:return zh?
   '当前没有可核实的五分钟行情数据，不会使用日线价格代替。':
   'No verified intraday data is available; daily prices will not be substituted.';
 }
}
function classifyHttpError(http,body){
 const code=body&&typeof body==='object'?String(body.code||''):'';
 if(http===404)return code==='PGRST205'||code==='42P01'?'schema_missing':'endpoint_not_found';
 if(http===401||http===403)return 'unauthorized';
 return 'network_error';
}
function explainState(state,lang){
 const zh=lang==='zh',r=state.reason;
 return r==='stale'?zh?'已发布的分钟级数据超过 12 分钟没有更新；为了防止误导，暂停显示当前涨幅榜。':'Minute bars are more than 12 minutes old; current ranking is unavailable.':
 r==='membership_unavailable'?zh?'该指数没有可靠的有效成分股名单。Russell 指数需要提供授权的当前名单。':'No validated current constituents for this index. Licensed Russell membership is required.':
 r==='membership_stale'?zh?'该指数成分股名单过期，不能声称当前成分股排名。':'The universe membership is stale; cannot call this a current index screen.':
 describeServiceIssue(status==='available'?'unavailable':status,lang);
}
function report(q,lang='zh',now=Date.now()){
 const universe=parseQuestion(q),v=select(feed,{universe},now),zh=lang==='zh',s=v.scope;
 let html='<section class="flo-five-analysis"><b>Flo · '+esc(LABELS[universe])+
   (zh?' 5 分钟涨幅接力榜':' 5-minute momentum relay')+'</b>';
 if(!v.state.ok){html+='<p>'+esc(explainState(v.state,lang))+'</p>';return {html:html+'</section>',facts:[],links:[],mood:'think',intents:['minute-movers-unavailable']};}
 html+='<p class="flo-five-disclaimer">'+esc((zh?'来源：':'Source: ')+(feed.provider||'')+
   ' '+(feed.feed||'')+' · '+feed.generated_at+' UTC · '+
   (zh?'有效成分匹配率 ':'Eligible-bar coverage ')+v.state.coverage+'% · '+String(feed.coverage_warning||''))+'</p>';
 if(v.state.partial)html+='<p>'+esc(zh?'该指数仅有部分公司具备有效分钟 K 线，此榜单是已覆盖股票中的排名，不是完整指数的最高涨幅。':
   'Incomplete minute-bar coverage: this is NOT a full-index top-gainers ranking.')+'</p>';
 html+='<table class="flo-five-table"><thead><tr><th>#</th><th>'+ (zh?'股票':'Ticker')+
 '</th><th>5m %</th><th>'+ (zh?'连续上榜':'Streak')+'</th><th>'+(zh?'成交额/美元':'Turnover $')+'</th></tr></thead><tbody>';
 for(let i=0;i<v.rows.length;i++){
   const x=v.rows[i];html+='<tr><td>'+(i+1)+'</td><td>'+esc(x.ticker)+'</td><td>+'+
    esc(x.five_min_pct.toFixed(2))+'%</td><td>'+esc(x.streak)+'</td><td>'+
    esc(x.volume_complete?(x.turnover_estimated?'≈ ':'')+Math.round(x.turnover_5m_usd).toLocaleString('en-US'):'incomplete')+'</td></tr>';
 }
 html+='</tbody></table>';
 if(!v.rows.length)html+='<p>'+esc(zh?'没有满足筛选条件的有效五分钟信号。':'No eligible exact five-minute change matched your filters.')+'</p>';
 html+='<p class="flo-five-disclaimer">'+esc(zh?
 '仅美国常规时段、精确 5 分钟间隔。IEX 只涵盖 IEX 交易所，SIP 依照供应商授权。Github 定时任务可能延误，不能承诺逐秒实时。':
 'Regular US session, exact 5-minute bar spacing only. IEX is single-exchange; SIP requires entitlement. Job schedules may lag.')+'</p></section>';
 return {html,links:[],facts:v.rows.slice(0,8).map(x=>x.ticker+' +'+x.five_min_pct.toFixed(2)+'% /5m'),
  mood:'talk',intents:['minute-movers'],scope:universe,rows:v.rows};
}
function node(t,txt,cls){const e=doc.createElement(t);e.textContent=txt;if(cls)e.className=cls;return e;}
function updateView(){
 if(!panel)return;
 panel.replaceChildren();
 const head=node('div','Flo · 5m Momentum Relay','flo-five-head');
 const close=node('button','×');close.setAttribute('aria-label','Close 5-minute scanner');
 close.addEventListener('click',()=>{panel.hidden=true;root.FFMascot?.openTool?.('chat');});
 head.append(close);panel.append(head);
 const selectors=node('div','','flo-five-controls');
 const pick=node('select','');pick.setAttribute('aria-label','Index universe');
 for(const k of SCOPES){const o=node('option',LABELS[k]);o.value=k;pick.append(o);}
 pick.value=settings.universe;pick.addEventListener('change',()=>{settings.universe=pick.value;persist();updateView();});
 selectors.append(pick);
 const numberBox=(label,value,step,onchange)=>{
  const wrap=node('label',label+' ');
  const i=node('input','');i.type='number';i.min='0';i.step=step;i.value=String(value);
  i.addEventListener('change',()=>{const n=Number(i.value);if(valid(n)&&n>=0){onchange(n);persist();updateView();}});
  wrap.append(i);selectors.append(wrap);
 };
 numberBox('Min +5m %',settings.minGain,'0.25',v=>{settings.minGain=Math.min(100,v)});
 numberBox('5m $ volume ≥',settings.minTurnover,'100000',v=>{settings.minTurnover=Math.min(1e9,v)});
 numberBox('Streak ≥',settings.minStreak,'1',v=>{settings.minStreak=Math.max(1,Math.min(20,Math.floor(v)))});
 const quiet=node('label','Quiet ');
 const check=node('input','');check.type='checkbox';check.checked=settings.quiet;
 check.addEventListener('change',()=>{settings.quiet=check.checked;persist();});
 quiet.append(check);selectors.append(quiet);panel.append(selectors);
 const screened=select(feed),meta=node('p','','flo-five-meta');
 const lang='zh';
 if(!screened.state.ok)meta.textContent=explainState(screened.state,lang);
 else meta.textContent=(screened.state.partial?'PARTIAL COVERAGE · ':'')+
   String(feed.feed||'').toUpperCase()+' · '+feed.generated_at+' · '+screened.state.coverage+
   '% coverage · membership '+(screened.scope.membership_asof||'unknown')+
   ' · last bar '+(screened.rows[0]?.asof||'not available')+' · '+String(feed.coverage_warning||'');
 panel.append(meta);
 const body=node('div','','flo-five-results');
 if(screened.state.ok){
   const list=node('ol','');
   for(const x of screened.rows){
     const row=node('li','');
     const trend=Number.isInteger(x.previous_rank)?
       (x.previous_rank>x.rank?' UP'+(x.previous_rank-x.rank):
        x.previous_rank<x.rank?' DOWN'+(x.rank-x.previous_rank):' SAME'):' NEW';
     const b=node('button','#'+x.rank+' '+x.ticker+'  +'+x.five_min_pct.toFixed(2)+'% · streak '+x.streak+trend);
     b.addEventListener('click',()=>{if(root.FFMascot&&root.FFMascot.showSignal)root.FFMascot.showSignal(
       {kind:'price',ticker:x.ticker,priority:'medium'},report('5分钟涨幅 '+LABELS[settings.universe],'zh').html);});
     row.append(b);list.append(row);
   }
   body.append(list);
   body.append(node('small','5m USD turnover uses bar VWAP when present; otherwise estimated close × volume. IEX is a single exchange.','flo-five-meta'));
   if(screened.state.partial)body.append(node('p','Minute-bar coverage is incomplete: only observed eligible symbols ranked.'));
 }
 panel.append(body);
 if(error)panel.append(node('small',error,'flo-five-meta'));
}
function scanForNotification(data,now=Date.now()){
 const v=select(data,{},now),top=v.rows[0];
 if(!v.state.ok||v.state.partial||!top||top.five_min_pct<Math.max(3,settings.minGain))return null;
 const fingerprint=settings.universe+':'+top.ticker;
 if(!initialized){initialized=true;previousTop=fingerprint;return null;}
 if(fingerprint===previousTop)return null;
 previousTop=fingerprint;
 if(settings.quiet||now-lastNotification<NOTIFY)return null;
 lastNotification=now;
 return top;
}
function notifyLeader(top){
 if(root.FFMascot?.notify){
   root.FFMascot.notify('momentum','5m · '+top.ticker+' +'+top.five_min_pct.toFixed(2)+'%');
   root.FFMascot.signalReaction?.('happy',{kind:'price',ticker:top.ticker});
   return;
 }
 if(!doc||!toast)return;
 toast.replaceChildren();const x=node('b','Flo · 新 5m 涨幅领跑 '+top.ticker);
 toast.append(x,node('p','+'+top.five_min_pct.toFixed(2)+'% · IEX/SIP source in scanner'));
 const b=node('button','查看接力榜');b.addEventListener('click',()=>{panel.hidden=false;toast.hidden=true;updateView();});
 toast.append(b);toast.hidden=false;
 if(root.FFMascot?.signalReaction)root.FFMascot.signalReaction('happy',{kind:'price',ticker:top.ticker});
}
async function loadServer(){
 if(server)return server;
 const res=await root.fetch(SITEBASE+'data/site.json',{cache:'no-store'});
 if(!res.ok){const e=Error('Site config missing');e.floIssue='site_config_missing';throw e;}
 const data=await res.json();
 if(!/^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(data.supabase_url||'')||!data.supabase_key)
   {const e=Error('Public Supabase connection is not configured');e.floIssue='site_config_missing';throw e;}
 server={url:data.supabase_url,key:data.supabase_key};return server;
}
async function poll(){
 if(!started||busy||(doc&&doc.visibilityState==='hidden'))return;
 busy=true;
 try{
   const cfg=await loadServer();
   const res=await root.fetch(cfg.url+'/rest/v1/flo_momentum_scan?name=eq.latest&select=payload',
    {cache:'no-store',headers:{apikey:cfg.key,Authorization:'Bearer '+cfg.key}});
   if(!res.ok){
     let body=null;
     try{body=await res.json();}catch(_){}
     const e=Error('Minute scanner feed HTTP '+res.status);
     e.floIssue=classifyHttpError(res.status,body);
     throw e;
   }
   const rows=await res.json();
   feed=Array.isArray(rows)&&rows.length&&rows[0].payload||null;
   status=feed?'available':'no_public_row';
   const top=scanForNotification(feed);
   if(top)notifyLeader(top);
   error='';
 }catch(e){status=e&&e.floIssue||'network_error';error=String(e.message||'Unavailable').slice(0,150);feed=null;}
 finally{busy=false;updateView();if(timer)clearTimeout(timer);if(started&&doc?.visibilityState!=='hidden')timer=setTimeout(poll,TIMER);}
}
function style(){
 const css='.flo-five-panel[hidden],.flo-five-toast[hidden]{display:none!important}.flo-five-launch{position:fixed;bottom:70px;right:12px;z-index:450;border:1px solid var(--line,#999);border-radius:22px;padding:8px 12px;background:var(--surface,#fff);color:inherit;font:600 12px system-ui;cursor:pointer;box-shadow:0 3px 14px #0002}.flo-five-panel{position:fixed;bottom:115px;right:12px;z-index:452;width:min(95vw,450px);max-height:65vh;overflow:auto;background:var(--surface,#fff);color:inherit;padding:12px;border:1px solid var(--line,#999);border-radius:13px;box-shadow:0 6px 25px #0003;font:12px system-ui}.flo-five-head{display:flex;justify-content:space-between;font-weight:700;font-size:15px}.flo-five-panel select,.flo-five-panel input{max-width:125px;border:1px solid var(--line,#aaa);border-radius:5px;background:transparent;color:inherit;padding:5px}.flo-five-controls{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0}.flo-five-controls label{font-size:10px;display:flex;gap:4px;align-items:center}.flo-five-controls input{max-width:85px}.flo-five-results ol{padding-left:22px}.flo-five-results li{margin:5px 0}.flo-five-results button{width:100%;text-align:left;border:1px solid var(--line,#ddd);background:transparent;color:inherit;border-radius:5px;padding:7px;cursor:pointer}.flo-five-meta,.flo-five-disclaimer{font-size:11px;color:var(--muted,#777)}.flo-five-toast{position:fixed;bottom:120px;right:12px;z-index:453;padding:12px;border:1px solid var(--line,#aaa);border-radius:9px;background:var(--surface,#fff);box-shadow:0 8px 20px #0002}.flo-five-table{width:100%;font-size:12px;border-collapse:collapse}.flo-five-table th,.flo-five-table td{border-bottom:1px solid var(--line,#ccc);padding:5px;text-align:right}.flo-five-table td:nth-child(2){font-weight:bold}.flo-five-table th:nth-child(2){text-align:left}';
 const e=doc.createElement('style');e.textContent=css;doc.head.append(e);
}
function openPanel(host){
 if(!panel)return null;
 if(host&&panel.parentNode!==host)host.append(panel);
 panel.hidden=false;updateView();return panel;
}
function start(){
 if(started||!doc||!root.fetch)return;
 started=true;restore();style();
 // The 5m scanner is a tab inside the ONE Flo assistant, not an extra
 // floating launcher/toast (which obstructs small-screen site content).
 pill=null;toast=null;
 panel=node('section','','flo-five-panel');panel.hidden=true;panel.setAttribute('aria-label','Flo five-minute momentum scanner');
 const host=root.FFMascot?.toolHost?.();
 (host||doc.body).append(panel);
 doc.addEventListener('visibilitychange',()=>{if(doc.visibilityState==='hidden'){if(timer)clearTimeout(timer);}else poll();});
 root.addEventListener?.('online',poll);
 poll();
}
root.FFFloMomentum={intent,parseQuestion,select,classify,report,describeServiceIssue,classifyHttpError,scanForNotification,getState:()=>({status,feed,settings:{...settings},error}),poll,start,openPanel,
 stop:()=>{started=false;if(timer)clearTimeout(timer);}};
if(typeof module!=='undefined')module.exports=root.FFFloMomentum;
if(doc){if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',start);else start();}
})(typeof globalThis!=='undefined'?globalThis:this);
