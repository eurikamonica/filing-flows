/* Notes & ties — the hub tab: every company's latest 10-K notes drawn and checked (勾稽), one company at a time, and the
   list of companies on file with how many of their ties hold. One company is drawn by notes-view.js (shared with the
   company pages). Data: notes-history branch, public/index.json and c/<TICKER>.json (app/notes.py), read from the
   repository's raw files. Deep links: #notes/NVDA, #notes/NVDA~checks. */
const ntStore={};
function ntIndex(){
 const m=ntStore.index||(ntStore.index={});
 if(m.data||m.err||m.loading)return m;
 const b=(window.FF_NOTES_BASE||'https://raw.githubusercontent.com/eurikamonica/filing-flows/notes-history/public/');
 m.loading=fetch(b+'index.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;render()}).catch(e=>{m.err=e.message;render()});
 return m;
}
const NT_SORT=[['revenue','Largest revenue first'],['gap','Most ties that do not hold'],['info','Most explained differences'],['checks','Most checks'],['filed','Latest filed']];
function notesView(){
 let out=head('Notes &amp; ties','Every note of a company\'s latest 10-K, drawn: each detail table as a chart (roll-forwards, schedules, compositions, splits by segment, market and region, the tax-rate bridge), and every tie recomputed from the company\'s own XBRL — its sums, roll-forwards, splits against totals, ties between the statements and the notes, and balance sheet changes against the cash flow statement (勾稽). Click a line to find the notes behind it.','10-K · XBRL · EVERY NOTE');
 out+=`<div class="toolbar"><div class="field wide"><label for="ntq">Company (ticker)</label><input id="ntq" value="${esc(state.ntq||'')}" placeholder="e.g. NVDA · Enter"></div>${field('nts','Sort',NT_SORT,state.nts||'revenue')}</div>`;
 const q=String(state.ntq||'').trim().toUpperCase().replace(/\./g,'-');
 if(q)return out+`<div id="nt-one" data-t="${esc(q)}" data-tab="${esc(state.nttab||'read')}"></div>`;
 const g=ntIndex();
 if(g.err)return out+empty(`The list of companies could not load (${g.err}). It is built by .github/workflows/notes.yml (app/notes.py), a batch of companies every few hours. Type a ticker above to open one company.`);
 if(!g.data)return out+empty('Loading the companies on file…');
 const F=g.data.fields||[],rows=(g.data.rows||[]).map(r=>{const o={};F.forEach((k,i)=>o[k]=r[i]);return o});
 const k=state.nts||'revenue';
 rows.sort((a,b)=>k==='filed'?String(b.filed).localeCompare(String(a.filed)):((b[k]||0)-(a[k]||0)));
 exported=rows;
 const tot=f=>rows.reduce((a,r)=>a+(r[f]||0),0);
 out+=`<div class="metrics">${kpi('Companies',fmt(rows.length),'latest 10-K read')}${kpi('Checks',fmt(tot('checks')),'recomputed from the facts')}${kpi('Tie',fmt(tot('tie')),'within the filing\'s rounding')}${kpi('Do not tie',fmt(tot('gap')),'worth a look')}</div>`;
 out+=`<div class="section-head"><h3>Companies on file</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
 return out+table(['Company','10-K','Filed','Notes','Detail tables','Checks','Tie','Explained','Do not tie'],rows.map(r=>[`<button class="text-button" data-ntco="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button> <span class="muted">${esc(r.name||'')}</span>`,esc(r.fy||''),esc(r.filed||''),fmt(r.notes),fmt(r.tables),fmt(r.checks),fmt(r.tie),fmt(r.info),r.gap?`<span class="negative">${fmt(r.gap)}</span>`:'0']));
}
function bindNotes(){
 if(state.tab!=='notes')return;
 if($('ntq')){$('ntq').onchange=e=>{state.ntq=e.target.value;render()};$('ntq').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 if($('nts'))$('nts').onchange=e=>{state.nts=e.target.value;state.page=0;render()};
 document.querySelectorAll('#workspace [data-ntco]').forEach(b=>b.onclick=()=>{state.ntq=b.dataset.ntco;render();scrollTo({top:0,behavior:'smooth'})});
 const one=$('nt-one');
 if(one&&window.NotesView&&one.dataset.drawn!==one.dataset.t){one.dataset.drawn=one.dataset.t;NotesView.render(one,{ticker:one.dataset.t,hub:'',tab:one.dataset.tab})}
}
function notesDeepLink(arg){const [t,tab]=decodeURIComponent(arg||'').split('~');if(t){state.ntq=t.toUpperCase();state.nttab=tab||'read'}}
window.notesDeepLink=notesDeepLink;
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{notes:notesNotice});
function notesNotice(){
 const g=ntIndex(),d=g.data;
 if(g.err)return {stale:false,text:'Official derived view · 10-K notes: the list of companies is not published yet ('+g.err+') — open one company by its ticker'};
 if(!d)return {stale:false,text:'Official derived view · 10-K notes loading…'};
 const age=(Date.now()-Date.parse(d.generated_at))/3600000;
 return {stale:!(age<=72),text:`Official derived view · 10-K notes built ${d.generated_at} · ${fmt((d.rows||[]).length)} companies · read from each company's XBRL, largest first, a batch every few hours`+(age>72?' · stale':'')};
}
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{notes:notesView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{notes:bindNotes});
