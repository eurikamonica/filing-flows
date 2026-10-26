/* Flo SEC Evidence Worksheet — real reported 10-K facts + explicit assumptions
 * + historical SEC enforcement cases. Reuses the offline workbook formula engine.
 */
(function(root){
'use strict';
const scriptSource=(typeof document!=='undefined'&&document.currentScript&&document.currentScript.src)||'';
const BASE=scriptSource?scriptSource.replace(/[^/]*$/,''):'';
const data=()=>root.FFFloRealData||(typeof module!=='undefined'?require('./flo-real-data.js'):null);
const engine=()=>root.FFFloWorkbook||(typeof module!=='undefined'?require('./flo-workbook.js'):null);
const coach=()=>root.FFFloCoach||(typeof module!=='undefined'?require('./flo-coach.js'):null);
const practice=()=>root.FFFloPractice||(typeof module!=='undefined'?require('./flo-practice.js'):null);
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
  {id:'DELL',label:'Dell · Intel incentives case'},
  {id:'WORLDCOM',label:'WorldCom · capitalization case'},
  {id:'XEROX',label:'Xerox · revenue timing case'},
  {id:'WASTE',label:'Waste Management · depreciation case'},
  {id:'HEALTHSOUTH',label:'HealthSouth · reported vs actual earnings'},
  {id:'BRISTOL',label:'Bristol-Myers · channel stuffing + reserves'}
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
 }else if(id==='WORLDCOM'){
   mode='case';const c=actual.cases.worldcom;title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.overstated2001,'SEC alleged pretax income overstatement for FY2001, not amount capitalized.');
   add('B4','reported',c.figures.overstated2002Q1,'SEC alleged pretax overstatement for Q1 2002, different period.');
   add('C3','target','=B3+B4','Total SEC-ALLEGED overstatement ACROSS these two different periods, not a single FY.');
   add('C4','target','=B3/C3','Share of these two period allegations attributed to 2001; not fraud probability.');
   rows=[['B3','2001 alleged pre-tax overstatement ($M)'],['B4','Q1 2002 alleged pre-tax overstatement ($M)'],
     ['C3','Two-period alleged total ($M)'],['C4','2001 / two-period combined (ratio)']];
 }else if(id==='XEROX'){
   mode='case';const c=actual.cases.xerox;title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.acceleratedRevenueLowerBound,'SEC alleged MORE THAN this revenue amount, not exactly this number.');
   add('B4','reported',c.figures.approxPretaxIncomeIncrease,'Approximate pre-tax earnings impact across 1997–2000.');
   add('C3','target','=B3','Exercise: transfer strict revenue LOWER BOUND. The true amount is greater.');
   add('C4','target','=B4','Exercise: approximately reported pretax impact, NOT precision ratio.');
   rows=[['B3','Revenue acceleration strict lower bound ($M)'],['B4','Approximate pre-tax earnings impact ($M)'],
     ['C3','Lower-bound recognition amount ($M)'],['C4','Approximate pre-tax impact ($M)']];
 }else if(id==='HEALTHSOUTH'){
   mode='case';const c=actual.cases.healthsouth;
   title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.reported1999,'1999 SEC complaint: reported pretax income, annual.');
   add('B4','reported',c.figures.actual1999,'1999 SEC complaint: actual pretax income, negative.');
   add('B5','reported',c.figures.reported2000,'2000 SEC complaint: reported pretax income, annual.');
   add('B6','reported',c.figures.actual2000,'2000 SEC complaint: actual pretax income, annual.');
   add('B7','reported',c.figures.reported2001,'2001 SEC complaint: reported pretax income, annual.');
   add('B8','reported',c.figures.actual2001,'2001 SEC complaint: actual pretax income, annual.');
   add('B9','reported',c.figures.reportedH12002,'2002 H1 SEC complaint: SIX MONTHS ONLY, not full FY.');
   add('B10','reported',c.figures.actualH12002,'2002 H1 SEC complaint: SIX MONTHS ONLY, not full FY.');
   add('C3','target','=B3-B4','1999 SEC alleged income overstatement including the negative actual profit.');
   add('C4','target','=B5-B6','2000 SEC alleged income overstatement.');
   add('C5','target','=B7-B8','2001 SEC alleged income overstatement.');
   add('C6','target','=B9-B10','2002 first HALF SEC alleged income overstatement.');
   add('C7','target','=SUM(C3:C6)','Combine four separately labeled periods; NOT one fiscal year and not the full scope of the case.');
   rows=[['B3','FY1999 reported pretax ($M)'],['B4','FY1999 actual pretax ($M)'],
     ['B5','FY2000 reported pretax ($M)'],['B6','FY2000 actual pretax ($M)'],
     ['B7','FY2001 reported pretax ($M)'],['B8','FY2001 actual pretax ($M)'],
     ['B9','H1 2002 reported pretax ($M)'],['B10','H1 2002 actual pretax ($M)'],
     ['C3','FY1999 overstatement ($M)'],['C4','FY2000 overstatement ($M)'],
     ['C5','FY2001 overstatement ($M)'],['C6','H1 2002 overstatement ($M)'],
     ['C7','Four-period total ($M; mixed FY/H1 periods)']];
 }else if(id==='BRISTOL'){
   mode='case';const c=actual.cases.bristol;
   title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.improperRevenueApprox,
      'SEC approximate $1.5B improperly recognized CONSIGNMENT-LIKE revenue across 2000–2001.');
   add('B4','reported',c.figures.civilSettlementPenalty,
      'SEC $150M settlement penalty, NOT a sales correction or revenue charge.');
   add('B5','input',2500,
      'Illustrative revenue baseline, invented ONLY to practice revenue reversal; not BMS actual sales.');
   add('C3','target','=B3/1000','Convert $1,500M SEC allegation to approximately $1.5B.');
   add('C4','target','=B5-B3',
      'Hypothetical correctly recognized revenue IF the entire disputed amount was embedded in the invented $2,500M baseline.');
   add('C5','target','=B3/B5',
      'Hypothetical quality ratio; no claim this is historic channel-stuffing as a percent of sales.');
   rows=[['B3','SEC approx improper sales ($M)'],['B4','SEC settlement penalty ($M) — NOT sales'],
     ['B5','Training-only reported sales baseline ($M)'],
     ['C3','SEC disputed sales ($B, approximate)'],['C4','Hypothetical adjusted sales ($M)'],
     ['C5','Disputed sales / hypothetical sales (not actual issuer ratio)']];
 }else if(id==='WASTE'){
   mode='case';const c=actual.cases.waste;title=c.company;description=c.exercise;source=c.citation;period=c.dates;
   add('B3','reported',c.figures.cumulativePretaxMisstatement,'1992–third quarter 1997 combined approximate amount, not single-year.');
   add('B4','input',1000,'HYPOTHETICAL asset purchase cost ($M), NOT from SEC Waste Management.');
   add('B5','input',5,'HYPOTHETICAL original straight-line useful life in years.');
   add('B6','input',10,'HYPOTHETICAL revised longer straight-line useful life in years.');
   add('C3','target','=B3','Read SEC multi-year allegation figure with correct time scope.');
   add('C4','target','=B4/B5','Annual depreciation assuming no salvage value at first useful life.');
   add('C5','target','=B4/B6','Annual depreciation with longer useful life.');
   add('C6','target','=C4-C5','Illustrative annual PRETAX profit lift from extending life; not SEC actual misstatement.');
   rows=[['B3','1992–Q3 1997 cumulative pretax misstatement ($M)'],
     ['B4','Illustrative asset value ($M) — ASSUMPTION'],
     ['B5','Illustrative original years — ASSUMPTION'],
     ['B6','Illustrative extended years — ASSUMPTION'],
     ['C3','SEC multi-year case total ($M)'],
     ['C4','Hypothetical yearly depreciation at old life ($M)'],
     ['C5','Hypothetical yearly depreciation at new life ($M)'],
     ['C6','Hypothetical annual pretax profit uplift ($M)']];
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
 (s.siteCik?'<button type="button" class="flo-local" data-real-live>'+(zh?'使用本网站最新已处理完整 10-K':'Use latest fully processed 10-K from this site')+'</button>':'')+
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
 (coach()?coach().panel(s,lang)+(s.mode==='case'?coach().simulatorHTML(lang):''):'')+
 '<p class="flo-source">'+(zh?'灰色 SEC 事实不可修改。蓝色表示预测或计算假设。紫色为练习公式；不可将 OCF−CapEx 当作 FCFF。':
 'SEC facts are locked; assumption cells are editable; formula tasks are graded. OCF−CapEx must not be called FCFF.')+'</p>';
}
function route(q){
 const s=String(q||'').toLowerCase();
 return /real|真实|年报|sec |10-k|sunbeam|dell|worldcom|xerox|waste management|healthsouth|bristol|bmy|company data|actual/i.test(s)&&
   /excel|workbook|spreadsheet|表格|练习|建模|case|案例|lab|模型/i.test(s);
}
function chosen(q,co){
 const s=String(q||'').toLowerCase();
 if(/sunbeam/.test(s))return 'SUNBEAM';
 if(/healthsouth|health.?south|康复医疗舞弊/.test(s))return 'HEALTHSOUTH';
 if(/bristol|bmy|百时美/.test(s))return 'BRISTOL';
 if(/worldcom|世通/.test(s))return 'WORLDCOM';
 if(/xerox|施乐/.test(s))return 'XEROX';
 if(/waste management|waste accounting|废物管理/.test(s))return 'WASTE';
 if(/dell/.test(s))return 'DELL';
 if(/\bmsft\b|microsoft|微软/i.test(s))return 'MSFT';
 if(/\baapl\b|apple|苹果/i.test(s))return 'AAPL';
 if(/\bnvda\b|nvidia|英伟达/i.test(s))return 'NVDA';
 const t=co&&co.ticker?String(co.ticker).toUpperCase():null;
 return t&&data().snapshots[t]?t:'NVDA';
}
function launch(q,co){
 const id=chosen(q,co),cik=co&&Number.isSafeInteger(+co.cik)&&+co.cik>0?String(+co.cik):'';
 return {html:'<div class="flo-workbook flo-real" data-real-case="'+esc(id)+'" data-real-cik="'+esc(cik)+'"></div>',
    realWorkbook:true,wide:true,facts:[],links:[],mood:'talk',intents:['real-workbook']};
}
function mountAll(host,lang){
 for(const elem of host.querySelectorAll('.flo-real[data-real-case]'))mount(elem,lang);
}
function mount(wrapper,lang){
 let session=make(wrapper.dataset.realCase||'NVDA');
 const siteCik=wrapper.dataset.realCik||'';
 const identity=()=>{
   session.siteCik=siteCik;
   return session;
 };
 identity();
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
  if(b.hasAttribute('data-coach-prev')){coach().prev(session);paint();return;}
  if(b.hasAttribute('data-coach-next')){coach().next(session);paint();return;}
  if(b.hasAttribute('data-coach-focus')){
    const item=coach().current(session);if(item)session.selected=item[0];paint();return;
  }
  if(b.hasAttribute('data-coach-hint')){session.message=coach().hint(session,lang);paint();return;}
  if(b.hasAttribute('data-coach-quiz')){
    coach().answerQuiz(session,Number(b.dataset.coachQuiz),lang);paint();return;
  }
  for(const [attr,action] of [['data-practice-review','review'],['data-practice-save','save'],['data-practice-restore','restore'],['data-practice-clear','clear']]){
    if(b.hasAttribute(attr)){practice().action(session,action,null,lang);paint();return;}
  }
  if(b.hasAttribute('data-flo-sim-run')){
    const kind=wrapper.querySelector('[data-flo-sim-kind]').value;
    const amount=wrapper.querySelector('[data-flo-sim-amount]').value;
    const life=wrapper.querySelector('[data-flo-sim-life]').value;
    try{const report=coach().simulate({kind,amount,life});
      wrapper.querySelector('.flo-sim-results').innerHTML=coach().renderSimResult(report);
    }catch(e){wrapper.querySelector('.flo-sim-results').textContent=e.message;}
    return;
  }
  if(b.hasAttribute('data-real-live')){
    if(!siteCik || !/^[1-9][0-9]{0,9}$/.test(siteCik)){session.message='No valid company CIK on current page';paint();return;}
    b.disabled=true;b.textContent='Reading published annual 10-K…';
    fetch(BASE+'data/c/'+siteCik+'.json',{credentials:'same-origin'})
     .then(r=>{if(!r.ok)throw Error('Processed company JSON not available (HTTP '+r.status+')');return r.json();})
     .then(payload=>{
       const parsed=data().fromPublished(payload,+siteCik);
       if(!parsed)throw Error('No sourced USD 10-K with verified revenue and operating profit on this site. Quarter, foreign currency and incomplete data are NOT substituted.');
       session=make(parsed.ticker||'NVDA',parsed);session.siteCik=siteCik;
       session.message='Loaded '+parsed.fy+' from original SEC-linked site annual JSON (not live stock market or forecast).';
       paint();
     })
     .catch(err=>{session.message=err.message;paint();});
    return;
  }
  if(b.hasAttribute('data-real-next')){
   const ref=Object.keys(session.answers).find(k=>!session.cells[k].raw.trim());
   session.message=ref?'Next: '+ref:'All formula cells filled. Use Grade.';
   if(ref)session.selected=ref;paint();return;
  }
  if(b.hasAttribute('data-real-check')){const score=check(session);session.grade=score;
   practice().recordGrade(session,score);
   session.message='SEC evidence exercise '+score.correct+'/'+score.total+
     (score.bad.length?' — '+score.bad[0].ref+' '+score.bad[0].reason:' — all formulas reconcile');
   paint();return;}
  if(b.hasAttribute('data-real-hint')){
    if(practice().memory(session).mode==='exam'){session.message='Exam mode: no hints until after submission.';paint();return;}
    practice().recordHint(session);session.message=session.cells[session.selected]?.note||'Click a formula cell';paint();return;
  }
  if(b.hasAttribute('data-real-answer')){
   if(practice().memory(session).mode==='exam'){session.message='Instructor formulas are locked during exam mode.';paint();return;}
   Object.entries(session.answers).forEach(([k,v])=>session.cells[k].raw=v);
   session.message='Instructor formulas shown; data source remains historical SEC';paint();return;}
  if(b.hasAttribute('data-real-reset')){session=make(session.id);identity();paint();}
 });
 wrapper.addEventListener('change',evt=>{if(evt.target.matches('[data-practice-mode]')){
  practice().action(session,'mode',evt.target.value,lang);paint();
 }else if(evt.target.matches('[data-real-case]')){
  session=make(evt.target.value);identity();paint();
 }});
 wrapper.addEventListener('keydown',evt=>{if(evt.key==='Enter'&&evt.target.matches('[data-real-formula]')){
  evt.preventDefault();write();
 }});
 paint();
}
root.FFFloRealWorkbook={route,chosen,launch,make,set,check,get,present,mountAll,total};
if(typeof module!=='undefined')module.exports=root.FFFloRealWorkbook;
})(typeof globalThis!=='undefined'?globalThis:this);
