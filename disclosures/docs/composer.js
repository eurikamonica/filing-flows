/* Chart composer tab (Disclosure Hub): the charts of any ticker — a company on the site or an ETF — made into one picture,
   through composer-view.js (also a view of every company page). #composer/NVDA opens it on a ticker. */
function composerView(){
 const t=String(state.cmt||'').trim().toUpperCase().replace(/[./]/g,'-');
 let out=head('Chart composer','Pick charts of a stock or an ETF — its earnings Sankey, rotation (RRG), fair value, price paths, options, move odds, highs and lows … — and make one picture of them for a post or a report. Everything is drawn in your browser.','PICTURE');
 out+=`<div class="toolbar"><div class="field wide"><label for="cmt">Ticker</label><input id="cmt" value="${esc(state.cmt||'')}" placeholder="e.g. NVDA, AAPL, SPY, XLK · Enter"></div></div>`;
 return out+(t?`<div id="cm-one" data-k="${esc(t)}" style="margin-top:10px"></div>`:empty('Type a ticker: a company on the site (NVDA, AAPL …) or an ETF (SPY, QQQ, XLK, TLT …).'));
}
function bindComposer(){
 if(state.tab!=='composer')return;
 if($('cmt')){$('cmt').onchange=e=>{state.cmt=e.target.value;render()};$('cmt').onkeydown=e=>{if(e.key==='Enter')e.target.blur()}}
 const el=$('cm-one');
 if(el&&window.ComposerView&&!el.dataset.on){el.dataset.on='1';window.ComposerView.render(el,{ticker:el.dataset.k,hub:'',site:'../',here:()=>state.tab==='composer'})}
}
function composerDeepLink(arg){state.cmt=String(decodeURIComponent(arg||'')).toUpperCase()}
// a tool, not a source: each chart it reads keeps its own freshness line in its own tab (without this the fallback read
// "Official composer · Status STALE · unknown")
function composerNotice(){return {stale:false,text:'Chart composer · draws the charts of the other views in your browser; each view\'s data is as fresh as its own tab says'}}
window.HUB_NOTICES=Object.assign(window.HUB_NOTICES||{},{composer:composerNotice});
window.HUB_VIEWS=Object.assign(window.HUB_VIEWS||{},{composer:composerView});
window.HUB_BINDS=Object.assign(window.HUB_BINDS||{},{composer:bindComposer});
window.composerDeepLink=composerDeepLink;
