'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const file=n=>fs.readFileSync(path.join(__dirname,'../web/',n),'utf8');
const mascot=file('mascot.js'),momentum=file('flo-momentum.js'),alerts=file('flo-alerts.js');
let checks=0;const ok=(v,m)=>{assert.ok(v,m);checks++};
ok(mascot.includes('data-flo-tab="chat"')&&mascot.includes('data-flo-tab="pulse"')&&mascot.includes('data-flo-tab="momentum"'),'one Flo panel exposes Academy, SEC inbox and 5m tabs');
ok(mascot.includes('function openTool(')&&mascot.includes('function notify('),'one host owns tool switching and notifications');
ok(mascot.includes('ui.toolHost.querySelectorAll'),'switching tabs hides previous embedded tool');
ok(mascot.includes('function showSignal(')&&mascot.includes("openTool('chat')"),'SEC event deep dive returns to chat');
ok(!momentum.includes("pill=node('button','Flo · 5m'"),'5m creates no floating pill');
ok(!alerts.includes("pill=el('button','flo-pulse-pill'"),'SEC Pulse creates no floating pill');
ok(momentum.includes('const host=root.FFMascot?.toolHost?.()')&&alerts.includes('const host=root.FFMascot?.toolHost?.()'),'both scanners use mascot host');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.parentNode=null;this.className='';this.dataset={};this.attributes={};this.listeners={};this.style={};this.hidden=false;this.textContent='';this.value='';}
 append(...children){for(const c of children){if(c&&c.parentNode)c.parentNode.children=c.parentNode.children.filter(x=>x!==c);if(c)c.parentNode=this;this.children.push(c);}}
 replaceChildren(...children){this.children=[];this.append(...children)}
 addEventListener(e,f){this.listeners[e]=f}
 setAttribute(k,v){this.attributes[k]=String(v)}
 click(){this.listeners.click?.({target:this,currentTarget:this})}
}
const body=new Element('body'),head=new Element('head'),host=new Element('section'),notice=[],reaction=[],open=[];
const doc={readyState:'loading',visibilityState:'visible',body,head,events:{},createElement:x=>new Element(x),addEventListener(k,f){this.events[k]=f}};
const today=new Date().toISOString().slice(0,10);
const now=Date.now(),a=new Date(now-6*60000).toISOString(),b=new Date(now-1*60000).toISOString();
const payload=(ticker,price)=>({schema:1,generated_at:new Date().toISOString(),provider:'Alpaca',feed:'IEX',universes:{
 sp500:{membership_status:'verified',membership_asof:today,universe_size:500,ranking_status:'complete_enough',coverage_pct:99,
 leaders:[{ticker,five_min_pct:4.8,price,turnover_5m_usd:12500000,volume_complete:true,
 streak:2,rank:1,previous_rank:3,asof:b,prev_asof:a}]}
 }});
let active=payload('NVDA',100);
const env={document:doc,console,navigator:{language:'zh-CN',onLine:true},
 fetch:async url=>{
  if(String(url).includes('data/site.json'))return {ok:true,json:async()=>({supabase_url:'https://example.supabase.co',supabase_key:'public-key'})};
  return {ok:true,json:async()=>[{payload:active}]};
 },addEventListener(){},setTimeout(){return 1},clearTimeout(){},localStorage:{getItem(){return null},setItem(){}},
 FFMascot:{toolHost:()=>host,notify:(type,label)=>{notice.push({type,label})},signalReaction:(kind,event)=>reaction.push({kind,event}),showSignal:(event,html)=>open.push({event,html})},module:{exports:{}}};
vm.runInNewContext(momentum,env,{filename:'flo-momentum.js'});
const M=env.FFFloMomentum;
(async()=>{
 M.start();
 for(let i=0;i<30;i++)await Promise.resolve();
 ok(!body.children.some(x=>['flo-five-launch','flo-five-toast'].includes(x.className)),'5m creates NO floating button/toast in body');
 const panel=host.children.find(x=>x.className==='flo-five-panel');
 ok(panel&&panel.hidden,'5m panel is hidden in Flo host until selected');
 const opened=M.openPanel(host);ok(opened===panel&&!panel.hidden,'5m opens inside mascot host');
 ok(panel.children.some(x=>x.className==='flo-five-controls'),'index selector and min filters preserved');
 ok(panel.children.some(x=>x.className==='flo-five-results'),'ranked movers list preserved');
 ok(M.getState().status==='available','market producer verified data remains readable');
 ok(notice.length===0,'first ranking creates baseline but no historical notification');
 active=payload('MSFT',110);await M.poll();
 ok(notice.length===1&&notice[0].type==='momentum','new leader emits ONE mascot notification');
 ok(reaction.length===1&&reaction[0].event.ticker==='MSFT','mascot reacts to new 5m leader');
 ok(!body.children.some(x=>x.className==='flo-five-toast'),'no second floating toast on leader change');
 ok(panel.children.some(x=>x.className==='flo-five-results'),'updating market data keeps panel mounted');
 const unavailable=M.select(null);ok(!unavailable.state.ok&&unavailable.rows.length===0,'missing intraday feed not fabricated');
 M.stop();
 console.log(checks+' unified Flo dock and live five-minute scanner smoke checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
