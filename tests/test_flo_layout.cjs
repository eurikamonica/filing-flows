'use strict';
// Flo responsive layout regression: real mascot script in a DOM-shaped sandbox.
// No external APIs, dependencies, network, browser permissions or screenshots.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/mascot.js'),'utf8');
const match=source.match(/const CSS = \`([\s\S]*?)\`;/);
assert.ok(match,'Flo inline stylesheet found');
const css=match[1];
let checks=0;
const ok=(v,m)=>{assert.ok(v,m);checks++};
const eq=(a,b,m)=>{assert.equal(a,b,m);checks++};
for(const [re,label] of [
 [/\.flo-panel\{right:20px;bottom:18px;width:min\(490px,/,'desktop 490px reading panel'],
 [/height:min\(730px,calc\(100dvh - 36px\)\)/,'viewport-aware height'],
 [/\.flo-panel\.flo-wide\{width:min\(880px,/,'Excel workbook extra width'],
 [/\.flo-panel\.flo-expanded,.flo-panel\.flo-expanded\.flo-wide\{/,'expand and workbook coexist'],
 [/\.flo-modes-main\{display:flex;flex-wrap:nowrap/,'short primary toolbar'],
 [/\.flo-chip-extra\[hidden\]\{display:none\}/,'more tools initially hidden'],
 [/\.flo-log\{flex:1 1 auto;min-height:0;overflow-y:auto/,'answer scrolls independently'],
 [/\.flo-form\{flex:0 0 auto;min-height:59px/,'composer never squeezed'],
 [/@media\(max-width:560px\)/,'mobile size rules'],
 [/height:82dvh;max-height:82dvh/,'mobile bottom sheet'],
 [/height:100dvh;max-height:100dvh/,'mobile fullscreen mode'],
 [/env\(safe-area-inset-bottom\)/,'phone home indicator safe area'],
 [/\.flo-head-controls\{display:flex/,'head action group']
])ok(re.test(css),label);
new vm.Script(source,{filename:'mascot.js'});checks++;

class FakeClassList{
 constructor(){this.s=new Set();}
 contains(v){return this.s.has(v)}
 add(v){this.s.add(v)}
 remove(v){this.s.delete(v)}
 toggle(v,on){const yes=arguments.length===2?!!on:!this.s.has(v);
   if(yes)this.s.add(v);else this.s.delete(v);return yes;}
}
class FakeNode{
 constructor(name='div'){
  this.name=name;this.style={};this.dataset={};this.attributes={};this.listeners={};
  this.classList=new FakeClassList();this.hidden=false;this.children=[];
  this._innerHTML='';this.textContent='';this.value='';this.childElementCount=0;
  this._query={};
 }
 set innerHTML(v){this._innerHTML=String(v);if(this.name==='chips'){
   this._query={};const find=(cls)=>{
     const rx=new RegExp('<button[^>]*class="'+cls+'"[^>]*>([\\s\\S]*?)<\\/button>','g'),found=[];
     for(const m of this._innerHTML.matchAll(rx)){
       const el=new FakeNode(cls);el.textContent=m[1].replace(/<[^>]*>/g,'');
       const attr=m[0].match(/data-flo-q="([^"]*)"/);
       if(attr)el.dataset.floQ=attr[1];
       found.push(el);
     }
     return found;
   };
   for(const c of ['flo-mode','flo-question','flo-more','flo-tools-toggle'])
     this._query[c]=find(c);
 }}
 get innerHTML(){return this._innerHTML;}
 addEventListener(type,cb){this.listeners[type]=cb;}
 click(){if(this.listeners.click)this.listeners.click({target:this,currentTarget:this,
    preventDefault(){},stopPropagation(){}});}
 setAttribute(k,v){this.attributes[k]=String(v);}
 getAttribute(k){return this.attributes[k]||null;}
 appendChild(x){this.children.push(x);this.childElementCount=this.children.length;return x;}
 append(...x){for(const v of x)this.appendChild(v);}
 querySelectorAll(selector){if(this.name==='chips')return this._query[selector.replace('.','')]||[];
   return [];}
 querySelector(selector){
  if(this.name==='chips')return (this.querySelectorAll(selector)||[])[0]||null;
  if(!this._query[selector])this._query[selector]=new FakeNode(selector);
  const node=this._query[selector];
  if(selector==='.flo-panel')node.hidden=true;
  return node;
 }
 getBoundingClientRect(){
  if(this.name==='.flo-panel'){
   const ex=this.classList.contains('flo-expanded');
   return ex?{left:130,top:20,right:1210,bottom:750,width:1080,height:730}:
     {left:770,top:50,right:1260,bottom:780,width:490,height:730};
  }
  return {left:0,top:0,right:60,bottom:60,width:60,height:60};
 }
 focus(){}
}
const listeners={},stored=new Map();
const rootEl=new FakeNode('root');
const document={
 readyState:'loading',body:new FakeNode('body'),head:new FakeNode('head'),
 currentScript:{src:'https://filing-flows.com/mascot.js'},
 createElement:kind=>new FakeNode(kind),getElementById:()=>null,
 addEventListener:(event,cb)=>{listeners[event]=cb}
};
document.body.appendChild=function(node){this.children.push(node);this.childElementCount=this.children.length;};
const globals={
 document,console,navigator:{language:'en-US'},innerWidth:1280,innerHeight:800,
 localStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)},
 location:{pathname:'/',hash:''},performance:{now:()=>100},matchMedia:()=>({matches:false}),
 addEventListener:(event,cb)=>{listeners['window:'+event]=cb},
 dispatchEvent:()=>{},
 CustomEvent:class CustomEvent{constructor(name){this.type=name}},
 requestAnimationFrame:()=>0,
 setTimeout:()=>0,clearTimeout:()=>{},
 fetch:async()=>({ok:false,status:404,json:async()=>null}),
 module:{exports:{}}
};
document.createElement=kind=>{
 if(kind==='div'&&!document._rootProvided){document._rootProvided=true;return rootEl;}
 return new FakeNode(kind);
};
vm.runInNewContext(source,globals,{filename:'mascot.js'});
ok(typeof listeners.DOMContentLoaded==='function','Flo mounts on document ready');
listeners.DOMContentLoaded();
const panel=rootEl.querySelector('.flo-panel'),chips=rootEl.querySelector('.flo-chips'),
 expand=rootEl.querySelector('.flo-resize'),launch=rootEl.querySelector('.flo-btn');
eq(panel.hidden,true,'panel starts closed');
launch.click();
eq(panel.hidden,false,'mascot launches workspace');
ok(chips.innerHTML.includes('More tools ▼'),'tools folded by default');
ok(chips.innerHTML.includes('id="flo-extra-tools" hidden'),'extra mode group collapsed');
eq(chips.querySelectorAll('.flo-mode').length,11,'all 11 existing Flo tools still in DOM');
eq((chips.innerHTML.match(/flo-mode" data-flo-q=/g)||[]).length,11,
 'existing tool actions preserved under collapsible menu');
const toggle=chips.querySelector('.flo-tools-toggle');toggle.click();
ok(chips.innerHTML.includes('id="flo-extra-tools">'),'expansion reveals secondary tools');
ok(chips.innerHTML.includes('Hide tools ▲'),'expanded state accessible');
chips.querySelector('.flo-tools-toggle').click();
ok(chips.innerHTML.includes('More tools ▼'),'secondary tools re-collapse');
eq(panel.classList.contains('flo-expanded'),false,'normal width default');
expand.click();
eq(panel.classList.contains('flo-expanded'),true,'maximize toggles panel class');
eq(expand.getAttribute('aria-pressed'),'true','maximize accessibility state');
eq(expand.getAttribute('aria-label'),'Restore Flo window size','maximize button label');
expand.click();
eq(panel.classList.contains('flo-expanded'),false,'restore previous mode');
eq(expand.getAttribute('aria-label'),'Expand Flo window','restore button label');
const controls=rootEl.querySelector('.flo-head-controls');
ok(!!controls,'titlebar grouped expand and close');
rootEl.querySelector('.flo-x').click();
eq(panel.hidden,true,'close still works');
console.log(checks+' Flo responsive layout and interaction checks passed');
