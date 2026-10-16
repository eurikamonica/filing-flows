// Created by ChatGPT (OpenAI). Edge-case tests for financial and journal handling.
const assert=require('node:assert/strict'),E=require('./engine.js');
const p={label:'FY2024',kind:'annual',start:'2024-01-01',end:'2024-12-31',net_income:10,ocf:20,revenue:100,operating_income:20,reserve_release:0,source:'Fictional',excerpt:'Illustrative example'};
const d={schema:'story-desk-1',demo:true,preliminary:false,company:'Example',ticker:'DEMO',unit:'USD',previous:p,current:{...p,label:'FY2025',start:'2025-01-01',end:'2025-12-31',net_income:20,ocf:10,operating_income:10,reserve_release:5}};
let checks=0;function test(name,fn){fn();checks++;console.log('PASS '+name);}
test('Divergence ranked first',()=>{const c=E.candidates(E.validate(d));assert.equal(c[0].id,'cash');assert.equal(c[0].priority,1);assert.equal(c.length,3);});
test('Margin percentage points',()=>{const c=E.candidates(d).find(c=>c.id==='margin');assert.equal(c.before[0],20);assert.equal(c.after[0],10);assert.match(c.fact,/-10 percentage points/);});
test('Missing OCF is not zero',()=>assert(!E.candidates({...d,current:{...d.current,ocf:null}}).some(c=>c.id==='cash')));
test('Zero OCF remains valid',()=>assert(E.candidates({...d,current:{...d.current,ocf:0}}).some(c=>c.id==='cash')));
test('Zero revenue blocks margin',()=>assert(!E.candidates({...d,current:{...d.current,revenue:0}}).some(c=>c.id==='margin')));
test('Losses retained',()=>assert.equal(E.candidates({...d,current:{...d.current,net_income:-20}}).find(c=>c.id==='cash').after[0],-20));
test('Unknown release income treatment',()=>assert.match(E.candidates(d).find(c=>c.id==='reserve').detail,/not established/));
test('Every demo draft labeled',()=>assert(E.drafts(d,E.candidates(d)[0]).every(x=>x.text.startsWith('ILLUSTRATIVE EXAMPLE'))));
test('Every preliminary draft labeled',()=>assert(E.drafts({...d,demo:false,preliminary:true},E.candidates(d)[0]).every(x=>x.text.startsWith('PRELIMINARY'))));
test('Overlapping periods rejected',()=>assert.throws(()=>E.validate({...d,current:{...d.current,start:p.start,end:p.end}})));
test('YTD-length quarter rejected',()=>assert.throws(()=>E.validate({...d,current:{...d.current,kind:'quarter',start:'2025-01-01',end:'2025-06-30'}})));
test('String amounts rejected',()=>assert.throws(()=>E.validate({...d,current:{...d.current,ocf:'10'}})));
test('Negative releases rejected',()=>assert.throws(()=>E.validate({...d,current:{...d.current,reserve_release:-1}})));
test('Source required',()=>assert.throws(()=>E.validate({...d,current:{...d.current,source:''}})));
const row={url:'https://x.com/example/status/1',published:'2026-10-15T09:00:00-04:00',format:'News',window:'24h',views:100,clicks:null,visits:0};
test('Unknown metrics retained',()=>assert.equal(E.validateJournal([row])[0].clicks,null));
test('Fractional metrics rejected',()=>assert.throws(()=>E.validateJournal([{...row,views:1.5}])));
test('Timezone required',()=>assert.throws(()=>E.validateJournal([{...row,published:'2026-10-15T09:00:00'}])));
test('Unsafe URL rejected',()=>assert.throws(()=>E.validateJournal([{...row,url:'javascript:alert(1)'}])));
console.log(`${checks} tests passed.`);
