'use strict';
// Browser-like smoke: site stays open, JSON snapshot updates, Flo reacts once.
// No actual browser, external network, timers, permissions or sound.
const assert = require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../web/flo-alerts.js'),'utf8');
let count=0;
const check=(v,msg)=>{assert.ok(v,msg);count++;};
class Element {
  constructor(tag) {
    this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.attributes={};
    this.hidden=false;this.className='';this.textContent='';this.style={};this.value='';
  }
  append(...x){this.children.push(...x)}
  replaceChildren(...x){this.children=x.slice()}
  addEventListener(event,fn){this.listeners[event]=fn}
  setAttribute(k,v){this.attributes[k]=String(v)}
  click(){this.listeners.click?.({target:this,currentTarget:this})}
}
const body=new Element('body'),head=new Element('head');
const doc={
  readyState:'loading',visibilityState:'visible',currentScript:{src:'https://filing-flows.com/flo-alerts.js'},
  body,head,events:{},
  createElement:tag=>new Element(tag),
  createTextNode:txt=>({textContent:txt}),
  addEventListener(event,fn){this.events[event]=fn}
};
const snapshots=[],store=new Map(),react=[],opened=[];
const env={
 document:doc,
 navigator:{language:'zh-CN',onLine:true},
 localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
 fetch:async()=>{
   if(!snapshots.length)throw Error('No queued response');
   const p=snapshots.shift();
   return {ok:true,json:async()=>p};
 },
 FFMascot:{
   refreshSignalData(){},
   signalReaction(kind,e){react.push({kind,event:e.id})},
   showSignal(e,html){opened.push({event:e.id,html})}
 },
 addEventListener(){},
 setTimeout(fn,ms){return 7},
 clearTimeout(){},
 console,
 module:{exports:{}}
};
vm.runInNewContext(script,env,{filename:'flo-alerts.js'});
const Alert=env.module.exports;
const date=new Date(Date.now()-120000).toISOString();
const base={schema:1,generated_at:date,events:[{
 id:'8k:original',kind:'8k',priority:'medium',ticker:'NVDA',title:'Previously published filing',
 detail:'Old item',event_at:date,form:'8-K',filed:'2026-10-25',source_label:'SEC',
 source_url:'https://www.sec.gov/Archives/edgar/data/1045810/old/'
}]};
const next={schema:1,generated_at:new Date(Date.now()-60000).toISOString(),events:[...base.events,{
 id:'8k:new',kind:'8k',priority:'high',ticker:'NVDA',title:'New SEC filing',detail:'Reported on SEC',
 event_at:new Date(Date.now()-30000).toISOString(),form:'8-K',filed:'2026-10-25',
 topics:['restatement'],source_label:'SEC',
 source_url:'https://www.sec.gov/Archives/edgar/data/1045810/new/'
}]};
(async()=>{
  snapshots.push(base);Alert.start();
  for(let i=0;i<8;i++)await Promise.resolve();
  check(react.length===0,'first open does not react to older filing');
  const toast=body.children.find(x=>x.className==='flo-pulse-toast');
  const inbox=body.children.find(x=>x.className==='flo-pulse-list');
  const pill=body.children.find(x=>x.className==='flo-pulse-pill');
  check(!!toast&&!!inbox&&!!pill,'alert elements mounted alongside existing Flo');
  check(toast.hidden,'no initial historic popup');
  snapshots.push(next);
  await Alert.poll();
  check(react.length===1&&react[0].kind==='worried','new material 8-K triggers alert animation with no reload');
  check(!toast.hidden,'new message opens compact popup');
  check(toast.children[1].textContent==='New SEC filing','pop-up uses new published title');
  const actions=toast.children[3];
  check(actions.children[0].textContent.includes('Flo'),'popup offers direct Flo analysis');
  actions.children[0].click();
  check(opened.length===1&&opened[0].event==='8k:new','click directly asks Flo to explain new SEC event');
  check(opened[0].html.includes('SEC')&&opened[0].html.includes('重述'),'answer includes SEC contextual risk evidence');
  snapshots.push(next);
  await Alert.poll();
  check(react.length===1,'same filing is never animated twice');
  pill.click();
  check(!inbox.hidden,'inbox can be opened without navigating');
  snapshots.push({...next,generated_at:new Date().toISOString(),events:[...next.events,{
    id:'13f:new',kind:'13f',priority:'medium',ticker:'NVDA',title:'New 13F from manager',
    manager:'Test Manager',event_at:new Date(Date.now()-10000).toISOString(),
    period_end:'2026-09-30',filed:'2026-10-25',source_label:'SEC',
    source_url:'https://www.sec.gov/Archives/edgar/data/1067983/new/'
  }]});
  Alert.getState().settings.quiet; // inspect but do not mutate copies
  // Mute through the real UI control, then verify future polls stay silent.
  const settingsLine=inbox.children.find(x=>x.className==='flo-pulse-actions');
  const mute=settingsLine.children[0].children[0];
  mute.checked=true;mute.listeners.change();
  await Alert.poll();
  check(react.length===1,'quiet mode suppresses Flo alert motions and popups');
  check(toast.hidden,'quiet mode closes old popup');
  check(Alert.getState().settings.quiet,'quiet choice saved to local settings');
  Alert.stop();
  console.log(count+' Flo open-tab live alert browser smoke checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
