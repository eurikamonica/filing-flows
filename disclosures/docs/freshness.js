/* Source health is independent of the payload a view uses for calculations. */
const sourceHealthStore={};
const SOURCE_TABS={holdings:'holdings',congress:'congress',review:'congress',trades:'congress',
 insiders:'insiders',events:'events8k',news:'news',stakes:'ownership',form144:'ownership',
 shorts:'shorts',options:'options',cot:'cot',banks:'banks',npx:'npx',directory:'holdings'};
function sourceHealth(key){
 const cached=sourceHealthStore[key]||(sourceHealthStore[key]={});
 if(!cached.pending&&(!cached.checkedAt||Date.now()-cached.checkedAt>120000)&&typeof fetch==='function'){
  cached.checkedAt=Date.now();cached.pending=true;
  fetch('data/'+key+'-status.json',{cache:'no-store'})
   .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
   .then(d=>{cached.data=d;cached.error=null;cached.pending=false;baseRender()}).catch(e=>{cached.error=e.message;cached.pending=false;baseRender()});
 }
 return cached;
}
function healthText(key,s={},published,nowMs=Date.now()){
 const completion=[s.last_success,s.last_partial_success,s.updated_at].filter(Boolean).sort().pop();
 const age=(nowMs-Date.parse(completion))/3600000;
 const limit=({holdings:8,congress:8,cot:36,banks:36,npx:36,options:96})[key]||8;
 const stale=!Number.isFinite(age)||age>limit;
 const errors=Array.isArray(s.errors)?s.errors.length:Number(s.errors)||0;
 const bad=['error','partial','blocked'].includes(s.status)||errors>0||s.failed_queue>0;
 const label=(stale?'STALE · ':'')+(bad?(s.status==='ok'?'partial':s.status||'partial'):s.status||'unknown');
 return {stale:stale||bad,text:'Official '+key+' · Status '+label+
  ' · Last attempt '+(s.last_attempt||'unknown')+
  ' · Last successful scan '+(s.last_success||'unknown')+
  ' · Last partial completion '+(s.last_partial_success||'unknown')+
  (!s.last_success&&!s.last_partial_success&&s.updated_at?' · Legacy completion '+s.updated_at:'')+
  ' · Latest filing date '+(s.latest_filing_date||'unknown')+
  ' · Site published '+(published||'unknown')+
  (s.error?' · '+s.error:'')+(errors?' · Errors '+errors:'')+
  (s.failed_queue?' · Failed queue '+s.failed_queue:'')+
  (s.next_retry_at?' · Next retry '+s.next_retry_at:'')};
}
function sourceNotice(tab,modules,published){
 const key=tab==='directory'?(state.dtype||'holdings'):SOURCE_TABS[tab];
 if(!key)return null;
 const own=sourceHealth(key);
 const result=healthText(key,own.data||modules[key]||{},published);
 if(own.error){result.text+=' · Status file unavailable ('+own.error+')';result.stale=true;}
 if(tab==='trades'||tab==='congress'){
  const senate=sourceHealth('senate');
  if(senate.data){const note=healthText('senate',senate.data,published);result.text+=' | '+note.text;result.stale ||= note.stale;}
 }
 return result;
}
function rotationNotice(report={},published,nowMs=Date.now()){
 const d=report.data||{},age=(nowMs-Date.parse(d.generated_at))/3600000;
 const sources=d.source_timestamps||{};
 const sourceOld=Object.values(sources).some(s=>!s||!Number.isFinite(Date.parse(s))||(nowMs-Date.parse(s))/3600000>96);
 return {stale:!Number.isFinite(age)||age>8||sourceOld||!!report.err||!Object.keys(sources).length,
  text:'Rotation · Built '+(d.generated_at||'unknown')+' · Site published '+(published||'unknown')+
   ' · Inputs at build: '+(Object.keys(sources).length?Object.entries(sources).map(([k,v])=>k+' '+(v||'unknown')).join(' / '):'unknown; rebuild required')+
   (sourceOld?' · Stale or unknown input timestamps':'')+(report.err?' · '+report.err:'')};
}

function activeRotationReport(markets){
 const key=({galaxy:'history/galaxy',macro:'history/macro',track:'history/forecast-ledger'})[state.rview]
  ||(state.rhist==='long'&&markets['history/rotation-long']?.data?'history/rotation-long':'rotation');
 return markets[key]||{};
}
