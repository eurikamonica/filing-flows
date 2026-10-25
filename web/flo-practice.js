/* Spin Sankey Flo Practice — private, browser-local, opt-in study progress.
 * No server writes; do not persist SEC report data. Hardened restoration.
 */
(function(root){
'use strict';
const key='ff:flo-practice:v1:';
const modes=['guided','practice','exam'];
const safeId=id=>/^[A-Za-z0-9_-]{1,40}$/.test(String(id||''));
const modelId=s=>String(s&&s.template?s.template.id:s.id||'');
const memory=s=>s.training||(s.training={mode:'guided',attempts:0,hints:0,quizzesCorrect:0,quizzesWrong:0,errors:{},lastGrade:null,drill:[]});
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function storage(provider) {
 if(provider)return provider;
 try{return root.localStorage||null;}catch(_){return null;}
}
function recordGrade(s,grade) {
 const t=memory(s);t.attempts++;
 if(grade&&Array.isArray(grade.bad))for(const miss of grade.bad){
   const ref=String(miss.ref||'');
   if(!/^[A-H][1-9][0-9]?$/.test(ref)||!Object.prototype.hasOwnProperty.call(s.answers||{},ref))continue;
   const old=t.errors[ref]||{count:0,why:''};
   t.errors[ref]={count:Math.min(999,old.count+1),why:String(miss.reason||'review formula').slice(0,120)};
 }
 t.lastGrade=grade?{correct:grade.correct,total:grade.total}:null;
 return t;
}
function recordQuiz(s,correct){const t=memory(s);if(correct)t.quizzesCorrect++;else t.quizzesWrong++;return t;}
function recordHint(s){const t=memory(s);t.hints++;return t;}
function changeMode(s,value){
 if(!modes.includes(value))throw Error('Unknown study difficulty');
 const t=memory(s);t.mode=value;return t;
}
function toughCells(s){
 const m=memory(s);
 return Object.entries(m.errors).filter(([r,x])=>s.answers&&Object.prototype.hasOwnProperty.call(s.answers,r))
  .sort((a,b)=>b[1].count-a[1].count||a[0].localeCompare(b[0]))
  .map(([ref,v])=>({ref,count:v.count,why:v.why}));
}
function review(s) {
 const bad=toughCells(s),unfinished=Object.keys(s.answers||{}).filter(r=>!String(s.cells[r]?.raw||'').trim());
 const next=bad[0]?.ref||unfinished[0]||null;
 if(next){s.selected=next;memory(s).drill=[next,...bad.slice(1,3).map(x=>x.ref)];}
 s.message=next?'Focus '+next+': '+(bad[0]?.why||s.cells[next]?.note||'Complete the next missing formula.'):
  'No errors or blanks recorded. Try a new scenario or Exam mode.';
 return next;
}
function payload(s){
 const t=memory(s),id=modelId(s),answerRefs=Object.keys(s.answers||{}),cells={};
 if(!safeId(id))throw Error('Invalid study identifier');
 for(const [ref,cell] of Object.entries(s.cells||{})){
  if(!/^[A-H][1-9][0-9]?$/.test(ref)||!['input','target'].includes(cell.type))continue;
  const value=String(cell.raw||'');
  if(value.length>220)continue;
  if(value===''||value.startsWith('=')||/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(value))cells[ref]=value;
 }
 return {version:1,id,source:s.source||null,mode:t.mode,cells,coachStep:s.coach&&Number.isInteger(s.coach.step)?s.coach.step:0,
   attempts:Math.min(9999,t.attempts),hints:Math.min(9999,t.hints),quizzesCorrect:Math.min(9999,t.quizzesCorrect),
   quizzesWrong:Math.min(9999,t.quizzesWrong),errors:toughCells(s).slice(0,64),answerRefs:answerRefs.slice(0,99)};
}
function save(s,provider){
 const store=storage(provider);if(!store||!store.setItem)throw Error('Local storage unavailable. Browser settings may block it.');
 const doc=payload(s);
 // Do not serialize SEC source JSON, report figures, or hidden answer key.
 doc.source=typeof s.source==='string'?s.source.slice(0,180):null;
 store.setItem(key+doc.id,JSON.stringify(doc));
 return doc;
}
function restore(s,provider){
 const store=storage(provider);if(!store||!store.getItem)throw Error('Local storage unavailable.');
 const raw=store.getItem(key+modelId(s));if(!raw)return {restored:0,reason:'No saved workbook for this course'};
 if(raw.length>30000)throw Error('Saved workbook exceeds size limit');
 let obj;try{obj=JSON.parse(raw);}catch(_){throw Error('Saved workbook is invalid JSON');}
 if(!obj||obj.version!==1||obj.id!==modelId(s)||!obj.cells||Array.isArray(obj.cells))throw Error('Workbook schema mismatch');
 // Do not transplant answers between a different SEC filing or edition of the case.
 const src=typeof s.source==='string'?s.source.slice(0,180):null;
 if(obj.source!==src)throw Error('Saved workbook is for a different SEC filing/source');
 let count=0;const answerRefs=new Set(Object.keys(s.answers||{}));
 for(const [ref,value] of Object.entries(obj.cells)){
  const c=s.cells&&s.cells[ref];
  if(!c||!['input','target'].includes(c.type)||typeof value!=='string'||value.length>220)continue;
  if(value&&!value.startsWith('=')&&!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(value))continue;
  // Only teacher-authorized formula exercises or user assumptions may be modified.
  if(c.type==='target'&&!answerRefs.has(ref))continue;
  c.raw=value;count++;
 }
 const t=memory(s);
 t.mode=modes.includes(obj.mode)?obj.mode:'guided';
 for(const field of ['attempts','hints','quizzesCorrect','quizzesWrong']){
   if(Number.isInteger(obj[field])&&obj[field]>=0&&obj[field]<=9999)t[field]=obj[field];
 }
 t.errors={};
 if(Array.isArray(obj.errors))for(const m of obj.errors.slice(0,64)){
  if(m&&answerRefs.has(m.ref)&&Number.isInteger(m.count)&&m.count>=0&&m.count<=999)
   t.errors[m.ref]={count:m.count,why:String(m.why||'').slice(0,120)};
 }
 if(Number.isInteger(obj.coachStep)&&obj.coachStep>=0&&obj.coachStep<40){
   if(!s.coach)s.coach={step:0,quiz:null,quizzesAnswered:0,quizIndex:0};
   s.coach.step=obj.coachStep;
 }
 s.grade=null;return {restored:count,reason:'Saved local formula practice restored'};
}
function erase(s,provider){
 const store=storage(provider);if(!store||!store.removeItem)throw Error('Local storage unavailable');
 store.removeItem(key+modelId(s));return true;
}
function panel(s,lang='en') {
 const zh=lang==='zh',t=memory(s),weak=toughCells(s).slice(0,3);
 const count=Object.keys(s.answers||{}).length,correct=t.lastGrade?.correct;
 return '<div class="flo-practice"><b>'+(zh?'Flo 练习档案':'Flo Practice Profile')+'</b>'+
  '<p class="flo-source">'+(zh?'仅保存在当前浏览器，必须点击「保存」。不上传到网站或云端。':'Local to this browser only; opt-in Save. Never uploaded to the site or cloud.')+'</p>'+
  '<div class="flo-wb-controls"><label>'+(zh?'训练难度':'Difficulty')+' <select data-practice-mode>'+
  modes.map(x=>'<option value="'+x+'" '+(x===t.mode?'selected':'')+'>'+esc(x)+'</option>').join('')+'</select></label></div>'+
  '<p>'+(zh?'检查次数':'Checks')+': '+t.attempts+' · '+(zh?'错题次数':'Wrong answers')+': '+t.quizzesWrong+
  ' · '+(zh?'已使用提示':'Hints used')+': '+t.hints+
  (correct===undefined?'':' · '+(zh?'最近评分':'Last grade')+': '+correct+'/'+count)+'</p>'+
  (weak.length?'<p>'+(zh?'优先复习':'Review first')+': '+weak.map(x=>'<code>'+esc(x.ref)+' ('+x.count+')</code>').join(' · ')+'</p>':'')+
  '<div class="flo-coach-controls"><button type="button" data-practice-review>'+(zh?'专项复习错题':'Review mistakes')+'</button>'+
  '<button type="button" data-practice-save>'+(zh?'保存进度':'Save locally')+'</button>'+
  '<button type="button" data-practice-restore>'+(zh?'恢复进度':'Restore')+'</button>'+
  '<button type="button" data-practice-clear>'+(zh?'清除本课程存档':'Clear course save')+'</button></div></div>';
}
function action(s,name,value,lang='en',provider){
 const t=memory(s),zh=lang==='zh';
 try{
  if(name==='mode'){changeMode(s,value);s.message=(zh?'训练难度：':'Difficulty: ')+value;}
  else if(name==='review')review(s);
  else if(name==='save'){const a=save(s,provider);s.message=(zh?'已在本地保存 ':'Saved locally ')+Object.keys(a.cells).length+' editable cells.';}
  else if(name==='restore'){const a=restore(s,provider);s.message=a.reason+' ('+a.restored+' cells)';}
  else if(name==='clear'){erase(s,provider);s.message=zh?'已清除本课程的本地存档':'Saved local course data cleared';}
  else return false;
  return true;
 }catch(e){s.message=e.message;return false;}
}
root.FFFloPractice={memory,recordGrade,recordQuiz,recordHint,changeMode,toughCells,review,payload,save,restore,erase,panel,action};
if(typeof module!=='undefined')module.exports=root.FFFloPractice;
})(typeof globalThis!=='undefined'?globalThis:this);
