/* Owner only: "✦ X" on a row of Insider trades, Officials' trades and the 13F directory (and "Post this 13F" on a
   manager's page) queues one X post about that row in Buffer, through the same request table as the Sankey site's
   "Post to X" (Supabase send_requests; post-to-x.yml finds the row again in the published data and writes the post).
   Readers load nothing: the check runs only when this browser holds a signed-in session of the site (the Sankey site's
   sign-in, same origin), and the buttons appear only for an account on the site's owner list. No dependencies. */
const XPOST={on:false,client:null,sent:new Map()};          // sent: this visit's queued rows, so a re-render keeps "✓"
(function(){
 let signed=false;
 try{for(let i=0;i<localStorage.length;i++)if(/^sb-.+-auth-token$/.test(localStorage.key(i)||'')){signed=true;break}}catch(e){}
 const fake=typeof window!=='undefined'&&window.FF_SUPABASE;   // injected by tests
 if((!signed&&!fake)||typeof fetch!=='function')return;
 const JS=['cdn.jsdelivr.net/npm','fastly.jsdelivr.net/npm','unpkg.com'].map(h=>`https://${h}/@supabase/supabase-js@2.58.0/dist/umd/supabase.js`);
 const load=src=>new Promise((res,rej)=>{const el=document.createElement('script');const t=setTimeout(()=>{el.remove();rej(new Error('timeout'))},6000);
  el.src=src;el.onload=()=>{clearTimeout(t);res()};el.onerror=()=>{clearTimeout(t);el.remove();rej(new Error('blocked'))};document.head.appendChild(el)});
 fetch('../data/site.json').then(r=>r.ok?r.json():{}).then(async site=>{
  if(!fake&&(!site.supabase_url||!site.supabase_key))return;
  let c=fake||null;
  if(!c){
   for(const s of JS){if(window.supabase&&window.supabase.createClient)break;await load(s).catch(()=>{})}
   const lib=window.supabase;if(!lib||!lib.createClient)return;
   c=lib.createClient(site.supabase_url,site.supabase_key,{auth:lib.processLock?{lock:lib.processLock}:{}});
  }
  const s=await c.auth.getSession();if(!s||!s.data||!s.data.session)return;
  const r=await c.rpc('am_i_owner');if(r.error||r.data!==true)return;
  XPOST.client=c;XPOST.on=true;
  if(typeof render==='function')render();
 }).catch(()=>{});
})();
function xDraft(){try{return localStorage.getItem('ff:postDraft')!=='0'}catch(e){return true}}
/* the owner's bar above a table: what ✦ X does, and Buffer draft or queue (shared with the Sankey site's Post to X) */
function xBar(what,button){
 if(!XPOST.on)return '';
 return `<div class="xbar"><span><b>Owner</b> · ${button?button+' ':'✦ X '}queues one post about ${esc(what)} in Buffer, written from the published data.</span><label><input type="checkbox" id="xdraft" ${xDraft()?'checked':''}> Save as a Buffer draft (review first)</label><span id="xmsg" role="status"></span></div>`;
}
/* one row's button: kind = a send_requests kind; ref = the row's key (a list, sent as JSON) or an accession or null */
function xBtn(kind,cik,ref,what,label){
 if(!XPOST.on)return '';
 const r=ref==null?'':typeof ref==='string'?ref:JSON.stringify(ref),done=XPOST.sent.get(kind+'|'+(+cik||0)+'|'+r);
 return `<button type="button" class="text-button xpost${done?' done':''}" data-xkind="${esc(kind)}" data-xcik="${+cik||0}" data-xref="${esc(r)}" title="Post ${esc(what||'this row')} to X (Buffer)"${done?' disabled':''}>${esc(done||label||'✦ X')}</button>`;
}
function xSay(text){const m=document.getElementById('xmsg');if(m)m.textContent=text}
async function xSend(b){
 if(b.disabled||!XPOST.client)return;
 b.disabled=true;b.setAttribute('aria-busy','true');const was=b.textContent;b.textContent='…';
 const d=new Date(),day=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
 const draft=document.getElementById('xdraft')?document.getElementById('xdraft').checked:xDraft();
 const row={cik:+b.dataset.xcik||0,period_end:day,kind:b.dataset.xkind,ref:b.dataset.xref||null,draft};
 let r;try{r=await XPOST.client.from('send_requests').insert([row])}catch(e){r={error:{message:e&&e.message||'no answer'}}}
 b.removeAttribute('aria-busy');
 const e=r&&r.error;
 if(!e){b.textContent=draft?'✓ Draft':'✓ Queued';b.classList.add('done');XPOST.sent.set(row.kind+'|'+row.cik+'|'+(row.ref||''),b.textContent);
  xSay(draft?'Writing it now: it appears in Buffer → Drafts within a few minutes.':'Queued: it reaches Buffer within a few minutes, then follows your posting schedule.');return}
 b.disabled=false;b.textContent=was;
 xSay(e.code==='23505'?'Already on its way: this row is waiting to be posted.'
  :/check constraint|violates row-level|column|relation/i.test(e.message||'')?'The site owner has to update the database first (run supabase/schema.sql again).'
  :`Could not queue it: ${e.message}`);
}
if(typeof document!=='undefined'&&document.addEventListener){
 document.addEventListener('click',ev=>{const b=ev.target.closest&&ev.target.closest('[data-xkind]');if(b){ev.preventDefault();xSend(b)}});
 document.addEventListener('change',ev=>{if(ev.target&&ev.target.id==='xdraft'){try{localStorage.setItem('ff:postDraft',ev.target.checked?'1':'0')}catch(e){}}});
}
