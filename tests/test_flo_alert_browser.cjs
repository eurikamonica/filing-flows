'use strict';
// In-page Flo unified alert smoke: new SEC item after baseline, no secondary
// floating entry, one mascot notice + its embedded SEC inbox.
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/flo-alerts.js'),'utf8');
const timeline=fs.readFileSync(path.join(__dirname,'../web/flo-timeline.js'),'utf8');
const impact=fs.readFileSync(path.join(__dirname,'../web/flo-impact.js'),'utf8');
let checks=0;const ok=(v,msg)=>{assert.ok(v,msg);checks++};
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.hidden=false;this.className='';this.textContent='';this.style={};this.value='';this.parentNode=null;}
 append(...children){for(const child of children){if(child&&child.parentNode){child.parentNode.children=child.parentNode.children.filter(x=>x!==child);}if(child)child.parentNode=this;this.children.push(child);}}
 replaceChildren(...children){this.children=[];this.append(...children);}
 addEventListener(e,fn){this.listeners[e]=fn;}
 setAttribute(k,v){this.attributes[k]=String(v);}
 click(){this.listeners.click?.({target:this,currentTarget:this});}
}
const body=new Element('body'),head=new Element('head'),toolHost=new Element('section');
const doc={readyState:'loading',visibilityState:'visible',currentScript:{src:'https://filing-flows.com/flo-alerts.js'},body,head,events:{},
 createElement:t=>new Element(t),createTextNode:x=>({textContent:x}),addEventListener(k,f){this.events[k]=f}};
const snapshots=[],store=new Map(),reactions=[],notices=[],opened=[],tabSwitch=[];
const mascot={
 toolHost:()=>toolHost,
 notify:(kind,txt)=>{notices.push({kind,txt});return true;},
 signalReaction:(kind,e)=>reactions.push({kind,event:e.id}),
 showSignal:(e,html)=>opened.push({event:e.id,html}),
 openTool:(kind)=>tabSwitch.push(kind),
 refreshSignalData(){}
};
const env={document:doc,navigator:{language:'zh-CN',onLine:true},localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
 fetch:async()=>{if(!snapshots.length)throw Error('No queued response');return {ok:true,json:async()=>snapshots.shift()};},
 FFMascot:mascot,addEventListener(){},setTimeout(){return 7},clearTimeout(){},console,module:{exports:{}}};
vm.runInNewContext(timeline,env,{filename:'flo-timeline.js'});
vm.runInNewContext(impact,env,{filename:'flo-impact.js'});
vm.runInNewContext(source,env,{filename:'flo-alerts.js'});
const Alert=env.FFFloAlerts;
const date=new Date(Date.now()-120000).toISOString();
const base={schema:1,generated_at:date,events:[{id:'8k:original',kind:'8k',priority:'medium',ticker:'NVDA',title:'Previously published filing',event_at:date,form:'8-K',filed:'2026-10-25',source_label:'SEC',source_url:'https://www.sec.gov/Archives/edgar/data/1045810/old/'}]};
const next={schema:1,generated_at:new Date(Date.now()-60000).toISOString(),events:[...base.events,{
 id:'8k:new',kind:'8k',priority:'high',ticker:'NVDA',title:'New SEC filing',detail:'Filed on SEC',
 event_at:new Date(Date.now()-30000).toISOString(),form:'8-K',filed:'2026-10-25',topics:['restatement'],source_label:'SEC',source_url:'https://www.sec.gov/Archives/edgar/data/1045810/new/'}]};
(async()=>{
 snapshots.push(base);Alert.start();
 for(let i=0;i<20;i++)await Promise.resolve();
 ok(reactions.length===0,'first visit creates historical baseline without animation');
 ok(notices.length===0,'no alert bubble on initial baseline');
 ok(!body.children.some(x=>x.className==='flo-pulse-pill'||x.className==='flo-pulse-toast'),'NO separate pulse pill or toast in body');
 const inbox=toolHost.children.find(x=>x.className==='flo-pulse-list');
 ok(inbox&&inbox.hidden,'SEC inbox pre-mounted in Flo tool host, hidden by default');
 snapshots.push(next);await Alert.poll();
 ok(reactions.length===1&&reactions[0].kind==='worried','new 8-K triggers unique mascot action with page open');
 ok(notices.length===1&&notices[0].kind==='pulse','new SEC event uses the ONE Flo mascot speech bubble');
 ok(notices[0].txt.includes('New SEC filing'),'mascot shows real source title');
 Alert.openPanel(toolHost);
 ok(!inbox.hidden&&inbox.parentNode===toolHost,'Flo SEC tab opens embedded inbox');
 const row=inbox.children.find(x=>x.className==='flo-pulse-item'&&x.children[0]?.textContent.includes('New SEC'));
 ok(!!row,'new filing is listed in the embedded inbox');
 row.children[0].click();
 ok(opened.length===1&&opened[0].html.includes('SEC'),'SEC item explains original published evidence in Flo');
 Alert.openPanel(toolHost);
 const timelineAction=row.children.find(x=>x.className==='flo-pulse-timeline-action');timelineAction.click();
 ok(opened.length===2&&opened[1].html.includes('研究时间线'),'same ticker timeline opens in Flo conversation');
 Alert.openPanel(toolHost);
 const researchAction=row.children.find(x=>x.className==='flo-pulse-research-action');researchAction.click();
 ok(opened.length===3&&opened[2].html.includes('证据核对与建模研究'),'source-backed accounting checklist opens from embedded alert');
 const analysis=Alert.report('NVDA 8-K 影响分析',true);
 ok(analysis.intents.includes('impact-research'),'plain-language Flo event study still works');
 snapshots.push(next);await Alert.poll();
 ok(notices.length===1&&reactions.length===1,'same filing never generates a duplicate mascot alert');
 Alert.openPanel(toolHost);
 const controls=inbox.children.find(x=>x.className==='flo-pulse-actions');
 const quiet=controls.children[0].children[0];quiet.checked=true;quiet.listeners.change();
 snapshots.push({...next,generated_at:new Date().toISOString(),events:[...next.events,{id:'13f:new',kind:'13f',priority:'medium',ticker:'NVDA',manager:'Example Manager',title:'Filed new 13F',event_at:new Date(Date.now()-10000).toISOString(),period_end:'2026-09-30',filed:'2026-10-25',source_url:'https://www.sec.gov/Archives/edgar/data/1067983/new/'}]});
 await Alert.poll();
 ok(notices.length===1&&reactions.length===1,'quiet suppresses new mascot notices/motions');
 ok(Alert.getState().settings.quiet,'quiet setting still persists');
 Alert.stop();
 console.log(checks+' unified Flo SEC inbox browser smoke checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
