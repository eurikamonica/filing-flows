/* Flo SEC Evidence Worksheet — real reported 10-K facts + explicit assumptions
 * + historical SEC enforcement cases. Reuses the offline workbook formula engine.
 */
(function(root){
'use strict';
const data=()=>root.FFFloRealData||(typeof module!=='undefined'?require('./flo-real-data.js'):null);
const engine=()=>root.FFFloWorkbook||(typeof module!=='undefined'?require('./flo-workbook.js'):null);
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ready=v=>typeof v==='number'&&Number.isFinite(v);
const item=(type,value,note='')=>({type,raw:value===null||value===undefined?'':String(value),note});
const report=(v,note)=>v===null||v===undefined?item('heading','N/A — not disclosed as standalone figure',note):item('reported',v,note);
const goal=(formula,note)=>({type:'target',raw:'',note,teacher:formula});
const assumed=(val,note)=>item('input',val,note+' (USER ASSUMPTION, NOT SEC)');
const fmt=(v)=>Number(v).toLocaleString('en-US',{maximumFractionDigits:3});
const choices=[
  {id:'NVDA',label:'NVIDIA FY2026 · 10-K'},
  {id:'AAPL',label:'Apple FY2025 · 10-K'},
  {id:'MSFT',label:'Microsoft FY2026 · 10-K'},
  {id:'SUNBEAM',label:'Sunbeam · SEC fraud case'},
  {id:'DELL',label:'Dell · Intel incentives case'}
];
function make(id,published){
 const actual=data();
 let d,mode='company',cells={},answers={},rows=[],title,description,source,period,unit='USD millions';
 const add=(ref,type,raw,note='')=>{
   cells[ref]=type==='target'?goal(raw,note):type==='reported'?report(raw,note):assumed(raw,note);
   if(type==='target'&&cells[ref].type==='target')answers[ref]=raw;
 };
 if(id==='SUNBEAM'){
   mode='case';const c=actual.cases.sunbeam;
   title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.reported1997,'Originally reported FY1997 income ($M).');
   add('B4','reported',c.figures.restated1997,'SEC-restated FY1997 income ($M).');
   add('B5','reported',c.figures.improperReserves,'Improper 1996 reserve set-aside, not the whole 1997 restatement.');
   add('B6','reported',c.figures.supplierRebatesQ2,'Premature supplier rebates in Q2 1997 ($M).');
   add('C3','target','=B3-B4','Compute originally reported minus restated income ($M).');
   add('C4','target','=C3/B3','What proportion of originally reported income was overstated?');
   add('C5','target','=B5/B3','Separate the 1996 reserve mechanism from overall FY1997 restatement.');
   rows=[['B3','Originally reported income'],['B4','Restated income'],['B5','Improper 1996 reserves'],['B6','Premature Q2 rebates'],
     ['C3','Restatement gap ($M)'],['C4','Restatement gap / original'],['C5','Reserve amount / original (non-additive illustration)']];
 }else if(id==='DELL'){
   mode='case';const c=actual.cases.dell;title=c.company;description=c.exercise;source=c.citation;period=c.dates;unit='percentage of operating income';
   add('B3','reported',c.figures.intelShareOperatingFY2003,'FY2003 Intel incentives as a ratio of operating profit.');
   add('B4','reported',c.figures.intelShareOperatingFY2006,'FY2006 Intel incentives as a ratio of operating profit.');
   add('B5','reported',c.figures.intelShareOperatingFY2007Q1,'FY2007 Q1 Intel incentives as a ratio.');
   add('C3','target','=(B5-B3)*100','Percentage-point increase from FY2003 to FY2007 Q1.');
   add('C4','target','=(B5-B4)*100','Percentage-point change from FY2006 to FY2007 Q1.');
   rows=[['B3','FY2003 Intel / operating income'],['B4','FY2006 Intel / operating income'],
     ['B5','FY2007 Q1 Intel / operating income'],['C3','Change FY2003 → FY2007 Q1 (pp)'],
     ['C4','Change FY2006 → FY2007 Q1 (pp)']];
 }else{
   d=published?actual.verify(published):actual.verifiedCopy(id);
   if(!d)throw Error('No verified company data for '+id);
   title=d.name;description=d.context;source=d.source;period=d.fy+' · '+d.end;
   add('B3','reported',d.revenue,'SEC reported full-year revenue.');
   add('B4','reported',d.oi,'SEC operating income, a conditional EBIT proxy.');
   add('B5','reported',d.netIncome,'SEC net income (not EBITDA).');
   add('B6','reported',d.da,'D&A cash flow; missing if issuer combines D&A with other.');
   add('B7','reported',d.capex,d.netCapexLabel||'SEC cash investing line, not total CFI.');
   add('B8','reported',d.ocf,'SEC net cash from operations; NOT FCFF.');
   add('C3','target','=B4/B3','Operating income divided by full-year revenue.');
   if(ready(d.capex)&&ready(d.ocf)){
     add('C4','target','=B8-B7','Cash from operations minus capital expenditures (simple FCF, NOT FCFF).');
     add('C5','target','=C4/B3','Simple FCF divided by revenue.');
     add('C6','target','=B7/B3','CapEx divided by revenue.');
   }
   add('C7','input',.21,'Illustrative normalized cash tax for FCFF exercise.');
   add('C8','input',0,'Illustrative Δoperating NWC; zero is NOT a reported fact.');
   if(ready(d.da)&&ready(d.capex))add('C9','target','=B4*(1-C7)+B6-B7-C8','Illustrative FCFF ≠ reported FCF. Adjust normalization and operating NWC.');
   rows=[['B3','Revenue ($M)'],['B4','Operating income / EBIT proxy ($M)'],['B5','Net income ($M)'],
     ['B6','D&A ($M), only when separately tagged'],['B7','CapEx cash spending ($M)'],['B8','Operating cash flow ($M)'],
     ['C3','Historical operating margin'],['C4','Historical OCF less CapEx ($M)'],['C5','Historical FCF margin'],
     ['C6','Historical CapEx / sales'],['C7','Tax rate (ASSUMPTION)'],['C8','ΔOp. NWC (ASSUMPTION)'],
     ['C9','Illustrative FCFF ($M, NOT SEC)']];
 }
 return {id,title,description,source,period,unit,mode,cells,answers,rows,selected:Object.keys(answers)[0],message:'',grade:null};
}
function set(s,ref,raw){
 if(!s.cells[ref]||!['input','target'].includes(s.cells[ref].type))throw Error('SEC facts are read-only. Choose an assumption or formula cell.');
 engine().setCell(s,ref,raw);
}
function check(s){return engine().score(s);}
function total(s){return Object.keys(s.answers).length;}
function get(s,ref){return engine().evaluate(s.cells,ref);}
function present(s,lang){
 const zh=lang==='zh';
 const options=choices.map(o=>'<option value="'+o.id+'" '+(s.id===o.id?'selected':'')+'>'+esc(o.label)+'</option>').join('');
 let table='<tr><th>Cell</th><th>'+(zh?'指标':'Metric')+'</th><th>'+(zh?'值 / 输入':'Value / formula')+'</th><th>'+(zh?'性质':'Status')+'</th></tr>';
 for(const [ref,label] of s.rows){
  const c=s.cells[ref],select=s.selected===ref,where=c?.type==='reported'?'SEC':c?.type==='input'?'ASSUMPTION':c?.type==='target'?'EXERCISE':'UNAVAILABLE';
  let val='N/A';
  if(c){try{val=c.type==='heading'?'Not available':fmt(get(s,ref));}
    catch(e){val=e.message==='#BLANK!'?'□':e.message;}}
  table+='<tr><td>'+esc(ref)+'</td><td>'+esc(label)+'</td><td class="flo-wb-'+(c?.type==='reported'?'reported':c?.type==='input'?'input':'formula')+'">'+
    (c&&['target','input'].includes(c.type)?'<button type="button" data-real-ref="'+esc(ref)+'">'+esc(val)+'</button>':esc(val))+'</td><td>'+esc(where)+'</td></tr>';
 }
 const ci=s.cells[s.selected];
 return '<div class="flo-wb-head"><b>'+(zh?'Flo · SEC 真实案例实验室':'Flo · SEC Evidence Lab')+'</b><small>'+esc(s.title)+'</small></div>'+
 '<p class="flo-source"><b>'+(zh?'真实公司历史报告或 SEC 执法案例 · 非实时行情':'Historical SEC filing / enforcement — NOT a live quote')+
 '</b> · '+esc(s.period)+' · '+esc(s.unit)+'</p>'+
 '<p>'+esc(s.description)+'</p>'+
 '<div class="flo-wb-evidence"><a href="'+esc(s.source)+'" target="_blank" rel="noopener noreferrer">'+
 (zh?'查看 SEC 原始证据 ↗':'Open original SEC primary source')+'</a></div>'+
 '<label>'+(zh?'切换真实公司 / 案例':'Choose issuer / case')+' <select data-real-case>'+options+'</select></label>'+
 '<div class="flo-wb-toolbar"><button type="button" data-real-next>'+(zh?'下一题':'Next missing formula')+'</button>'+
 '<button type="button" data-real-check>'+(zh?'批改':'Grade')+'</button>'+
 '<button type="button" data-real-hint>'+(zh?'提示':'Hint')+'</button>'+
 '<button type="button" data-real-answer>'+(zh?'参考公式':'Show formulas')+'</button>'+
 '<button type="button" data-real-reset>'+(zh?'重新练习':'Reset')+'</button></div>'+
 '<div class="flo-wb-formula"><span>'+esc(s.selected||'')+'</span><input data-real-formula spellcheck="false" value="'+esc(ci?.raw||'')+
 '" placeholder="=B8-B7" '+(!ci?'disabled':'')+'/><button type="button" data-real-apply>'+(zh?'计算':'Apply')+'</button></div>'+
 '<p class="flo-wb-help">'+esc(ci?.note||'Select a purple formula or a blue user assumption.')+'</p>'+
 '<div class="flo-wb-scroll" role="region" tabindex="0"><table class="flo-wb-table"><tbody>'+table+'</tbody></table></div>'+
 '<p class="flo-wb-feedback" aria-live="polite">'+esc(s.message||'')+'</p>'+
 '<p class="flo-source">'+(zh?'灰色 SEC 事实不可修改。蓝色表示预测或计算假设。紫色为练习公式；不可将 OCF−CapEx 当作 FCFF。':
 'SEC facts are locked; assumption cells are editable; formula tasks are graded. OCF−CapEx must not be called FCFF.')+'</p>';
}
function route(q){
 const s=String(q||'').toLowerCase();
 return /real|真实|年报|sec |10-k|sunbeam|dell|company data|actual/i.test(s)&&
   /excel|workbook|spreadsheet|表格|练习|建模|case|案例|lab|模型/i.test(s);
}
function chosen(q,co){
 const s=String(q||'').toLowerCase();
 if(/sunbeam/.test(s))return 'SUNBEAM';
 if(/dell/.test(s))return 'DELL';
 if(/\bmsft\b|microsoft|微软/i.test(s))return 'MSFT';
 if(/\baapl\b|apple|苹果/i.test(s))return 'AAPL';
 if(/\bnvda\b|nvidia|英伟达/i.test(s))return 'NVDA';
 const t=co&&co.ticker?String(co.ticker).toUpperCase():null;
 return t&&data().snapshots[t]?t:'NVDA';
}
function launch(q,co){
 const id=chosen(q,co);
 return {html:'<div class="flo-workbook flo-real" data-real-case="'+esc(id)+'"></div>',
    realWorkbook:true,wide:true,facts:[],links:[],mood:'talk',intents:['real-workbook']};
}
function mountAll(host,lang){
 for(const elem of host.querySelectorAll('.flo-real[data-real-case]'))mount(elem,lang);
}
function mount(wrapper,lang){
 let session=make(wrapper.dataset.realCase||'NVDA');
 const paint=()=>wrapper.innerHTML=present(session,lang);
 const write=()=>{
  try{set(session,session.selected,wrapper.querySelector('[data-real-formula]').value);
    session.message=lang==='zh'?'已重新计算':'Recalculated';}catch(e){session.message=e.message;}
  paint();
 };
 wrapper.addEventListener('click',evt=>{
  const b=evt.target.closest('button');if(!b||!wrapper.contains(b))return;
  if(b.dataset.realRef){session.selected=b.dataset.realRef;paint();return;}
  if(b.hasAttribute('data-real-apply'))return write();
  if(b.hasAttribute('data-real-next')){
   const ref=Object.keys(session.answers).find(k=>!session.cells[k].raw.trim());
   session.message=ref?'Next: '+ref:'All formula cells filled. Use Grade.';
   if(ref)session.selected=ref;paint();return;
  }
  if(b.hasAttribute('data-real-check')){const score=check(session);session.grade=score;
   session.message='SEC evidence exercise '+score.correct+'/'+score.total+
     (score.bad.length?' — '+score.bad[0].ref+' '+score.bad[0].reason:' — all formulas reconcile');
   paint();return;}
  if(b.hasAttribute('data-real-hint')){session.message=session.cells[session.selected]?.note||'Click a formula cell';paint();return;}
  if(b.hasAttribute('data-real-answer')){
   Object.entries(session.answers).forEach(([k,v])=>session.cells[k].raw=v);
   session.message='Instructor formulas shown; data source remains historical SEC';paint();return;}
  if(b.hasAttribute('data-real-reset')){session=make(session.id);paint();}
 });
 wrapper.addEventListener('change',evt=>{if(evt.target.matches('[data-real-case]')){
  session=make(evt.target.value);paint();
 }});
 wrapper.addEventListener('keydown',evt=>{if(evt.key==='Enter'&&evt.target.matches('[data-real-formula]')){
  evt.preventDefault();write();
 }});
 paint();
}
root.FFFloRealWorkbook={route,chosen,launch,make,set,check,get,present,mountAll,total};
if(typeof module!=='undefined')module.exports=root.FFFloRealWorkbook;
})(typeof globalThis!=='undefined'?globalThis:this);
