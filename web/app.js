/* Filing Flows: hash-routed single page app over the static JSON written by pipeline/build.py. */
(function () {
  'use strict';
  const S = window.Sankey;
  const BASE = window.FF_DATA || 'data/';
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const app = $('#app');
  // every navigation gets a number: a page still loading when the reader moves on (a slow connection) draws nothing,
  // instead of drawing over the page they went to
  let view = 0;
  const live = () => { const mine = view; return () => mine === view; };

  // ---------- small utilities ----------
  const cache = new Map();
  const FRESH = new Set(['index.json', 'site.json']);          // small files that change: ask the server each time
  function getJSON(p, fresh) {
    if (fresh) cache.delete(p);
    if (!cache.has(p)) {
      const get = FRESH.has(p) || fresh ? fetch(BASE + p, { cache: 'no-cache' }).catch(() => fetch(BASE + p)) : fetch(BASE + p);
      const got = get.then((r) => {
        if (!r.ok) { const err = new Error(`${p}: HTTP ${r.status}`); err.status = r.status; throw err; }
        return r.json();
      });
      got.catch(() => cache.delete(p));                          // a failure is not kept: the next visit asks again
      cache.set(p, got);
    }
    return cache.get(p);
  }
  const prefs = {
    get(k, d) { try { const v = localStorage.getItem('ff:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ff:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };
  const savedCmp = prefs.get('compare', null);                       // 'q' | 'y' | null (older builds stored true)
  const state = { compare: savedCmp === true ? 'q' : savedCmp, zoom: prefs.get('zoom', 'fit'), decreases: prefs.get('decreases', false),
    fcf: fcfBasis(prefs.get('fcf', 'company')), dragZoom: prefs.get('drag-zoom', false) === true,
    linesUnmatched: prefs.get('lines-unmatched', false) === true, charts: [] };
  // Free cash flow as the reader chose in their alerts (pipeline/reported.py fcf_view does the same for e-mails):
  // 'company' draws the company's own figure where the pipeline could check it against SEC data, else the formula;
  // 'noted' also says, on a chart drawn by the formula, why there is no company figure ("fcf_note");
  // 'ocf' swaps in the quarter on operating cash flow − capex where the company's figure is drawn ("fcf_alt")
  function fcfBasis(v) { return v === 'ocf' || v === 'noted' ? v : 'company'; }
  function fcfView(q) {
    if (!q) return q;
    if (state.linesUnmatched && q.lines_alt) {      // revenue lines that match neither total: shown with the difference
      q = Object.assign({}, q, q.lines_alt, { lines_shown: true });
      delete q.lines_alt;
    }
    let out;
    if (state.fcf === 'ocf' && q.fcf_alt) out = Object.assign({}, q, q.fcf_alt);
    else if (state.fcf === 'noted' && q.fcf_note) {
      const n = q.fcf_note;
      out = Object.assign({}, q, {
        nodes: (q.nodes || []).map((x) => (x.id === n.node ? Object.assign({}, x, { lines: (x.lines || []).concat([['mut', n.line]]) }) : x)),
        checks: (q.checks || []).concat([n.check]), footer: (q.footer || []).concat([n.footer]),
      });
    } else return q;
    delete out.fcf_alt;
    delete out.fcf_note;
    out.fcf_basis = state.fcf;
    return out;
  }
  const t = (s) => S.esc(S.dec(s == null ? '' : s));
  const sign = (x) => (x > 0 ? '+' : x < 0 ? '−' : '');
  const pct = (x, d) => (x == null || isNaN(x) ? '—' : sign(+x.toFixed(d || 0)) + Math.abs(x).toFixed(d || 0) + '%');
  const margin = (x) => (x == null || isNaN(x) ? '—' : (x < 0 ? '\u2212' : '') + Math.abs(x).toFixed(1) + '%');
  const tone = (x) => (x == null ? '' : x > 0.05 ? 'pos' : x < -0.05 ? 'neg' : '');
  // A company that reports in another currency is shown in it (pipeline/fx.py), with the same charts in US dollars a
  // click away: CUR is the symbol of the currency on the page now.
  const CCY = { USD: '$', EUR: '€', GBP: '£', JPY: '¥', CNY: 'RMB ', TWD: 'NT$', KRW: '₩', INR: '₹', CAD: 'C$', AUD: 'A$', NZD: 'NZ$', CHF: 'CHF ',
    HKD: 'HK$', SGD: 'S$', BRL: 'R$', MXN: 'MX$', SEK: 'SEK ', DKK: 'DKK ', NOK: 'NOK ', ZAR: 'ZAR ', ILS: '₪', THB: '฿', PHP: '₱', IDR: 'Rp ',
    TRY: '₺', PLN: 'zł ', MYR: 'RM ' };
  const CCY_NAME = { EUR: 'euros', GBP: 'pounds sterling', JPY: 'Japanese yen', CNY: 'Chinese yuan (renminbi)', TWD: 'New Taiwan dollars',
    KRW: 'Korean won', INR: 'Indian rupees', CAD: 'Canadian dollars', AUD: 'Australian dollars', CHF: 'Swiss francs', HKD: 'Hong Kong dollars',
    BRL: 'Brazilian reais', MXN: 'Mexican pesos', SEK: 'Swedish kronor', DKK: 'Danish kroner', NOK: 'Norwegian kroner', ILS: 'Israeli shekels' };
  const symOf = (code) => CCY[code] || (code ? code + ' ' : '$');
  let CUR = '$';
  function money(v) {
    if (v == null) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}${CUR}${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}${CUR}${(a / 1e9).toFixed(1)}B`;
    if (a >= 0.95e6) return `${s}${CUR}${(a / 1e6).toFixed(1)}M`;
    return `${s}${CUR}${(a / 1e3).toFixed(0)}K`;
  }
  // "Latest filing: 10-Q for Q2 FY27, filed Aug 26, 2026 · site data updated Oct 21, 2026, 20:16 UTC"
  function freshLine(q, generated) {
    const parts = [];
    if (q && q.filed) parts.push(`Latest filing: <b>${t(q.form || '')} for ${t(q.label || '')}</b>, filed ${date(q.filed)}`);
    if (generated) parts.push(`site data updated ${updatedAt(generated)}`);
    return parts.length ? `<div class="fresh">${parts.join(' · ')}</div>` : '';
  }
  function updatedAt(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return t(String(iso).slice(0, 10));
    return `${date(d.toISOString().slice(0, 10))}, ${d.toISOString().slice(11, 16)} UTC`;
  }
  function date(s) {
    if (!s) return '—';
    const d = new Date(s.length <= 10 ? s + 'T00:00:00Z' : s);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }
  const calLabel = (cal) => (cal ? `Q${cal.slice(-1)} ${cal.slice(2, 6)}` : '');
  const accession = (url) => { const m = /(\d{10}-\d{2}-\d{6})-index/.exec(url || ''); return m ? m[1] : null; };
  const mdnaItem = (form) => (form === '10-K' ? 'Item 7' : 'Item 2');
  // where node notes come from: the MD&A of a 10-Q/10-K, or the press release of an 8-K
  const noteSource = (form) => (form === '8-K' ? 'the earnings release (8-K, Exhibit 99.1)' : form === '6-K' ? 'the results release (6-K exhibit)'
    : `the ${form} (${mdnaItem(form)}, Management’s Discussion and Analysis)`);
  const prelimTag = '<span class="tag prelim" title="Read from the 8-K earnings release; replaced by the 10-Q/10-K when filed">Preliminary · 8-K</span>';
  const finalTag = (rc) => `<span class="tag final" title="${t(releaseCheckText(rc))}">Final · ${rc.ok ? 'confirms' : 'revises'} the 8-K</span>`;
  const listJoin = (a) => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);
  function releaseCheckText(rc) {
    const ok = rc.fields.filter((f) => f.ok).map((f) => f.name.toLowerCase());
    const bad = rc.fields.filter((f) => !f.ok).map((f) => `${f.name.toLowerCase()} ${money(f.release)} in the release, ${money(f.final)} as filed`);
    let out = `Replaces the preliminary chart read from the 8-K earnings release filed ${date(rc.filed)}.`;
    if (ok.length) out += ` ${listJoin(ok).replace(/^./, (x) => x.toUpperCase())} ${bad.length ? 'match' : 'all match the filing'}.`;
    if (bad.length) out += ` Revised: ${bad.join('; ')}.`;
    return out;
  }

  let fontsP = null;
  function fontsReady() {
    if (!fontsP) {
      const loads = document.fonts
        ? ['400 15px "IBM Plex Sans"', '500 14px "IBM Plex Sans"', '600 18px "IBM Plex Sans"'].map((f) => document.fonts.load(f).catch(() => null))
        : [];
      fontsP = Promise.race([Promise.all(loads), new Promise((r) => setTimeout(r, 2500))]);
    }
    return fontsP;
  }
  if (document.fonts && document.fonts.addEventListener) {
    let timer = null;
    document.fonts.addEventListener('loadingdone', () => {
      clearTimeout(timer);
      timer = setTimeout(() => state.charts.forEach((c) => c.redraw()), 60);
    });
  }

  // ---------- export helpers ----------
  // Inside the claude.ai artifact viewer files go through its `downloads` capability (the viewer confirms);
  // everywhere else (GitHub Pages, local) a normal browser download.
  async function blobBase64(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let bin = '';
    for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    return btoa(bin);
  }
  const nativeApp = window.FilingFlowsApp || null;               // set when the page runs inside the Android app
  const canShare = !!(nativeApp && typeof nativeApp.shareFile === 'function');
  if (nativeApp) document.documentElement.classList.add('in-app');  // the app has its own tabs and toolbar
  async function saveBlob(blob, name) {
    const native = window.FilingFlowsApp;                       // the Android app saves files itself
    if (native && typeof native.saveFile === 'function') {
      native.saveFile(name, blob.type || 'application/octet-stream', await blobBase64(blob));
      return 'saved';
    }
    const host = window.claude;
    if (host && typeof host.use === 'function') {
      const dl = await host.use('downloads').catch(() => null);
      if (dl) {
        try { await dl.save({ filename: name, data: blob }); return 'saved'; } catch (e) { return e && e.code === 'declined' ? 'declined' : 'failed'; }
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 120000);
    return 'saved';
  }
  let toastEl = null;
  function toast(msg, action) {
    if (toastEl) toastEl.remove();
    toastEl = document.createElement('div');
    toastEl.className = 'toast';
    toastEl.setAttribute('role', 'status');
    toastEl.innerHTML = `<span>${t(msg)}</span>${action ? '<button type="button">Preview</button>' : ''}`;
    if (action) $('button', toastEl).addEventListener('click', action);
    document.body.appendChild(toastEl);
    const mine = toastEl;
    setTimeout(() => { if (mine === toastEl) { mine.remove(); toastEl = null; } }, 7000);
  }
  function previewDialog(blob, fmt, name, scene) {
    const src = fmt === 'pdf' ? S.toCanvas(scene, 1).toDataURL('image/png') : URL.createObjectURL(blob);
    const d = document.createElement('div');
    d.className = 'dialog';
    d.innerHTML = `<div class="box" role="dialog" aria-modal="true" aria-label="Exported file">
      <div class="row"><h3>${t(name)}</h3><span class="muted">${(blob.size / 1024).toFixed(0)} KB · ${scene.W * 2} × ${scene.H * 2} px</span></div>
      <img alt="Exported chart" src="${src}">
      <p class="muted">The export contains the chart only; notes from the filing stay on the page. If the download did not start, ${
        fmt === 'pdf' ? 'use the button below.' : 'right-click the image and choose “Save image as”.'}</p>
      <div class="row"><button class="btn primary" type="button" data-dl>Download ${fmt.toUpperCase()}</button><button class="btn" type="button" data-close>Close</button></div>
    </div>`;
    const close = () => { d.remove(); if (fmt !== 'pdf') URL.revokeObjectURL(src); };
    d.addEventListener('click', (e) => { if (e.target === d || e.target.hasAttribute('data-close')) close(); });
    $('[data-dl]', d).addEventListener('click', () => saveBlob(blob, name));
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } });
    document.body.appendChild(d);
  }

  // ---------- the chart component: Sankey + notes panel + view / zoom / export controls ----------
  function chartUI(spec, ctx) {
    const el = document.createElement('section');
    const has = (c) => !!(c && c.bullets && c.bullets.length);
    const cmpOf = (m) => (m === 'y' ? spec.compare_y : m === 'q' ? spec.compare : null);
    const yearly = spec.period === 'fy' && !ctx.custom;      // a full year has no "previous quarter"
    el.innerHTML = `
      <div class="controls">
        <div class="seg" role="group" aria-label="Chart view">
          <button type="button" data-view="std">Standard</button>
          <button type="button" data-view="q" ${yearly ? 'hidden' : ''} ${has(spec.compare) ? '' : 'disabled title="No previous quarter on file"'}>vs ${has(spec.compare) ? t(spec.compare.vs) : 'previous quarter'}</button>
          <button type="button" data-view="y" ${ctx.custom ? 'hidden' : ''} ${has(spec.compare_y) ? '' : `disabled title="No ${yearly ? 'earlier year' : 'year-ago quarter'} on file"`}>vs ${has(spec.compare_y) ? t(spec.compare_y.vs) : 'year ago'}</button>
        </div>
        <label class="dec-toggle" hidden title="Hatched areas with a dashed outline show what each line lost"><input type="checkbox" data-dec ${state.decreases ? 'checked' : ''}> Show decreases</label>
        ${ctx.guide ? `<button class="btn small guide-btn" type="button" data-guide aria-pressed="false" title="Draw the next period as the company guided it in its latest earnings release: guided lines in violet with their range, the rest at today's shares">◇ Show guidance</button>
        <div class="seg gseg" role="group" aria-label="Compare the guided period" hidden>
          <button type="button" data-gcmp="">As guided</button>
          <button type="button" data-gcmp="q">vs current</button>
          <button type="button" data-gcmp="y">vs year ago</button>
        </div>` : ''}
        <div class="seg" role="group" aria-label="Zoom">
          <button type="button" data-zoom="fit">Fit</button>
          <button type="button" data-zoom="full">100%</button>
        </div>
        <button class="btn small" type="button" data-reset hidden title="Show the whole chart again (or double-click an empty part of it)">Reset view</button>
        <div class="export" role="group" aria-label="Export chart"><span>Export</span>
          <button class="btn" type="button" data-x="png">PNG</button>
          <button class="btn" type="button" data-x="jpg">JPG</button>
          <button class="btn" type="button" data-x="pdf">PDF</button>
          ${canShare ? '<button class="btn" type="button" data-x="share">Share</button>' : ''}
        </div>
      </div>
      <div class="hintline">${ctx.group ? 'Click a company bar to open its own chart.' :
        '<span class="dot"></span><span>Click any node for what the company wrote about it in the filing. Exports show the chart only.</span>'}
        <span class="pz-hint" hidden>· Hold the left button on an empty part to drag the chart, use the wheel to zoom, double-click to reset.</span></div>
      <p class="guide-msg" hidden></p>
      <div class="stage">
        <div class="sheet"><div class="loading">Drawing…</div></div>
        <aside class="notes" aria-live="polite"></aside>
      </div>
      <section class="guide-record" hidden aria-label="Guidance record"></section>`;
    const sheet = $('.sheet', el), notes = $('.notes', el);
    const baseById = new Map(spec.nodes.map((n) => [n.id, n]));
    // "Show guidance" (web/guidance.js): the next period as guided; its own spec, nodes and notes while it is on
    const guide = { on: false, open: false, doc: undefined, spec: null, byId: null, cmp: '' };
    const futureOn = () => guide.on && guide.spec && !guide.spec.error;
    const byId = { get: (id) => (futureOn() ? guide.byId : baseById).get(id), has: (id) => (futureOn() ? guide.byId : baseById).has(id) };
    let scene = null, selected = null;
    let own = ctx.custom ? 'q' : undefined;                     // a requested comparison opens on its comparison
    const pick = () => (own !== undefined ? own : state.compare);
    const mode = () => (has(cmpOf(pick())) ? pick() : null);   // active comparison, if this chart has it
    if (acct.prefs && typeof acct.prefs.cmp_decreases === 'boolean') state.decreases = acct.prefs.cmp_decreases;
    const cmpOn = () => !!mode();

    // drag and zoom (Alerts → On company pages): hold the left mouse button on an empty part of the chart (not a node)
    // to move it, the pointer turning into a hand; the wheel zooms around the pointer; double-click or "Reset view" shows
    // it whole again. It changes the SVG's viewBox only: exports and the notes are unaffected.
    const MAX_ZOOM = 8;
    let vb = null, drag = null, dragged = false;              // vb: [x, y, w, h] of the chart in view; null = all of it
    function applyView() {
      const svg = $('svg', sheet);
      if (!svg || !scene) return;
      svg.setAttribute('viewBox', (vb || [0, 0, scene.W, scene.H]).map((x) => +x.toFixed(2)).join(' '));
      $('[data-reset]', el).hidden = !vb;
      sheet.classList.toggle('zoomed', !!vb);
    }
    function setView(v) {                                       // kept inside the chart, the chart's own proportions
      const W = scene.W, H = scene.H;
      const w = Math.min(W, Math.max(W / MAX_ZOOM, v[2])), h = w * H / W;
      vb = w >= W - 0.5 ? null : [Math.min(Math.max(0, v[0]), W - w), Math.min(Math.max(0, v[1]), H - h), w, h];
      applyView();
    }
    const blank = (target) => !(target.closest && target.closest('[data-node], .note-mark'));
    const at = (e) => {                                         // the pointer in chart coordinates
      const r = $('svg', sheet).getBoundingClientRect(), v = vb || [0, 0, scene.W, scene.H];
      return [v[0] + (e.clientX - r.left) / r.width * v[2], v[1] + (e.clientY - r.top) / r.height * v[3], r];
    };
    sheet.addEventListener('wheel', (e) => {
      if (!state.dragZoom || !scene || !$('svg', sheet)) return;
      const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1);
      if (dy > 0 && !vb) return;                                // whole chart already: the page scrolls on
      e.preventDefault();
      const [px, py] = at(e), v = vb || [0, 0, scene.W, scene.H];
      const k = Math.exp(Math.max(-300, Math.min(300, dy)) * 0.0015);   // > 1 zooms out
      const w = v[2] * k, h = v[3] * k;
      setView([px - (px - v[0]) * (w / v[2]), py - (py - v[1]) * (h / v[3]), w, h]);
    }, { passive: false });
    sheet.addEventListener('pointerdown', (e) => {
      if (!state.dragZoom || e.pointerType !== 'mouse' || e.button !== 0 || !scene || !blank(e.target)) return;
      e.preventDefault();                                       // no text selection while dragging
      drag = { x: e.clientX, y: e.clientY, vb: vb && vb.slice(), left: sheet.scrollLeft, id: e.pointerId, moved: false };
      sheet.classList.add('grabbing');
      try { sheet.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
    });
    sheet.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 3) return;
      drag.moved = true;
      if (drag.vb) {
        const r = $('svg', sheet).getBoundingClientRect();
        setView([drag.vb[0] - dx / r.width * drag.vb[2], drag.vb[1] - dy / r.height * drag.vb[3], drag.vb[2], drag.vb[3]]);
      } else {
        sheet.scrollLeft = drag.left - dx;                      // whole chart at 100%: the sheet scrolls sideways
      }
    });
    const endDrag = (e) => {
      if (!drag || (e && e.pointerId !== drag.id)) return;
      dragged = drag.moved;                                     // the click that ends a drag does not close the note
      drag = null;
      sheet.classList.remove('grabbing');
    };
    sheet.addEventListener('pointerup', endDrag);
    sheet.addEventListener('pointercancel', endDrag);
    sheet.addEventListener('dblclick', (e) => {
      if (state.dragZoom && blank(e.target) && vb) { vb = null; applyView(); }
    });

    function sync() {
      sheet.classList.toggle('panzoom', state.dragZoom);
      $('.pz-hint', el).hidden = !state.dragZoom;
      if (!state.dragZoom && vb) { vb = null; applyView(); }
      $$('[data-view]', el).forEach((b) => b.classList.toggle('on', !futureOn() && b.dataset.view === (mode() || 'std')));
      $('.dec-toggle', el).hidden = futureOn() ? !guide.cmp : !mode();
      const gb = $('[data-guide]', el);
      if (gb) { gb.classList.toggle('on', guide.open); gb.setAttribute('aria-pressed', guide.open ? 'true' : 'false'); }
      const gr = $('.guide-record', el);
      if (gr) {
        // the guidance record (web/guidance.js record): each guided period against what was reported, and the moves
        const rec = guide.open && guide.spec && guide.spec.record;
        gr.hidden = !rec;
        if (rec && gr.dataset.drawn !== '1') { gr.innerHTML = window.FFGuidance.recordHTML(rec, t); gr.dataset.drawn = '1'; }
      }
      const gs = $('.gseg', el);
      if (gs) {
        gs.hidden = !futureOn();
        if (futureOn()) {
          const gc = { q: guide.spec.compare, y: guide.spec.compare_y };
          $$('[data-gcmp]', gs).forEach((b) => {
            const k = b.dataset.gcmp;
            if (k) {
              b.hidden = !gc[k];
              if (gc[k]) b.textContent = `vs ${gc[k].vs}${k === 'y' ? ' (year ago)' : ' (current)'}`;
            }
            b.classList.toggle('on', k === (guide.cmp || ''));
          });
        }
      }
      sheet.classList.toggle('future', futureOn());
      $$('[data-zoom]', el).forEach((b) => b.classList.toggle('on', b.dataset.zoom === state.zoom));
      sheet.classList.toggle('fit', state.zoom === 'fit');
      if (scene) sheet.style.setProperty('--min-w', `${Math.round(scene.W * 0.5)}px`);   // never shrink below half size
    }
    function intro() {
      if (ctx.group) {
        return `<div class="eyebrow">How to read</div>
          <p class="hint"><span>Each grey bar on the left is one company. Click it to open that company’s own chart, with notes from its filing.</span></p>
          <p class="empty">Exports (PNG, JPG, PDF) contain the chart only.</p>`;
      }
      if (futureOn()) {
        return `<div class="eyebrow">Guidance view · ${t(guide.spec.period)}</div>
          <p class="hint"><span class="dot guide"></span><span>Violet lines are what ${t(ctx.company)} guided in its earnings release (bar = midpoint, dashed box = the range). Grey, green and red lines were not guided: they keep their standard colours and their ${t(guide.spec.base)} share, so the chart adds up. Compared with a reported quarter, the violet strip in a band is the increase; a decrease is hatched.</span></p>
          <p class="empty">▲ raised · ▼ lowered (midpoint) · →← narrowed · ←→ widened (range) · = reaffirmed · ✦ initiated — against the prior range in the release, else the company’s previous release. Click a line for the sentence it comes from.</p>`;
      }
      const withNotes = spec.nodes.filter((n) => n.notes).length;
      return `<div class="eyebrow">Notes from the filing</div>
        <p class="hint"><span class="dot"></span><span>Click any node to read what ${t(ctx.company)} wrote about it in this ${ctx.form === '8-K' ? 'earnings release' : ctx.form === '6-K' ? 'results release (6-K)' : t(ctx.form)}. A green dot marks the ${withNotes} line${withNotes === 1 ? '' : 's'} with their own passage in ${ctx.form === '8-K' || ctx.form === '6-K' ? 'the release' : 'the MD&amp;A'}.</span></p>
        <p class="empty">Notes stay on the page: exported PNG, JPG and PDF files show the chart only.</p>`;
    }
    function nodeNotes(n) {
      if (futureOn() && window.FFGuidance) {
        return `<div class="eyebrow">${t(ctx.company)} · ${t(guide.spec.period)} as guided</div>
          <div class="k">${t(n.name)}</div><div class="v">${(n.lines || []).slice(1).map((l) => `<div>${t(l[1])}</div>`).join('')}${
            [['q', n.cmp, guide.spec.compare], ['y', n.cmp_y, guide.spec.compare_y]].filter(([, c, sp]) => Array.isArray(c) && sp)
              .map(([, c, sp]) => `<div class="gchg ${c[0]}">${t(c[1])} <span class="muted">vs ${t(sp.vs)}</span></div>`).join('')}</div>
          ${window.FFGuidance.noteHTML(n, guide.doc && guide.doc.g, t, guide.spec.record)}
          <button class="btn" type="button" data-clear>Close note</button>`;
      }
      const lines = (n.lines || []).slice(1).map((l) => `<div>${t(l[1])}</div>`).join('') + (mode() && (mode() === 'y' ? n.cmp_y : n.cmp) ? `<div>${t(mode() === 'y' ? n.cmp_y : n.cmp)}</div>` : '');
      let body;
      const m = /^L:m(\d+)$/.exec(n.id);
      if (ctx.group && m && ctx.companies && ctx.companies[+m[1]]) {
        const co = ctx.companies[+m[1]];
        body = `<p><a href="#c-${co.cik}">Open the ${t(co.ticker)} chart →</a></p>`;
      } else if (ctx.group) {
        body = '<p class="empty">This line is a sum across the companies in the group; it has no filing text of its own.</p>';
      } else if (n.notes && n.notes.length) {
        const same = (h) => S.dec(h).trim().toLowerCase() === S.dec(n.name).trim().toLowerCase();
        body = n.notes.map((x) => `<blockquote>${x.heading && !same(x.heading) ? `<h4>${t(x.heading)}</h4>` : ''}${
          String(x.text).split(/\n\n+/).map((p) => `<p>${t(p)}</p>`).join('')}</blockquote>`).join('') +
          `<div class="src">Quoted verbatim from ${t(noteSource(ctx.form))}${
            ctx.docUrl ? ` · <a href="${t(ctx.docUrl)}" target="_blank" rel="noopener">open filing ↗</a>` : ''}</div>`;
      } else {
        body = `<p class="empty">${ctx.form === '8-K' || ctx.form === '6-K' ? 'The release has no passage about this line.' : `The ${t(ctx.form)} has no separate MD&amp;A passage about this line.`}</p>`;
      }
      const trend = ctx.trend ? trendBlock(ctx.trend(n.id), n) : '';
      const source = sourceBlock(n, spec.cite, ctx.cik);                    // where the figure was taken from
      // Ask the existing Spin Sankey Flo to explain the exact selected node,
      // with the current report period and source, without fabricating value.
      const flo = !ctx.group ? '<button class="btn primary" type="button" data-flo-node>Ask Flo what moved this number</button>' : '';
      return `<div class="eyebrow">${ctx.group ? t(ctx.groupName) : t(ctx.company)} · ${t(ctx.label)}</div>
        <div class="k">${t(n.name)}</div><div class="v">${lines}</div>${source}${trend}${body}${flo}
        <button class="btn" type="button" data-clear>Close note</button>`;
    }
    function select(id) {
      const svg = $('svg', sheet);
      if (!svg) return;
      $$('.node.sel', svg).forEach((g) => g.classList.remove('sel'));
      $$('.band.on', svg).forEach((p) => p.classList.remove('on'));
      selected = id;
      if (!id || !byId.has(id)) {
        selected = null;
        svg.classList.remove('has-sel');
        notes.classList.remove('open');
        notes.innerHTML = intro();
        return;
      }
      svg.classList.add('has-sel');
      $$('.node', svg).filter((g) => g.dataset.node === id).forEach((g) => g.classList.add('sel'));
      $$('.band', svg).filter((p) => p.dataset.s === id || p.dataset.t === id).forEach((p) => p.classList.add('on'));
      notes.innerHTML = nodeNotes(byId.get(id));
      wireTrend(notes);
      notes.classList.add('open');
      notes.scrollTop = 0;
      const clear = $('[data-clear]', notes);
      if (clear) clear.addEventListener('click', () => select(null));
      const floButton = $('[data-flo-node]', notes);
      if (floButton) floButton.addEventListener('click', () => {
        if (!window.FFMascot || !window.FFMascot.explain) return;
        const n = byId.get(id);
        window.FFMascot.explain({
          cik: ctx.cik, label: S.dec(n.name), period: ctx.label,
          display: n.lines && n.lines[1] ? S.dec(n.lines[1][1]) : '',
          docUrl: ctx.docUrl || null,
          // the chart's own figures, so Flo can say what moved this line (web/flo-features.js explainFigures)
          id: n.id, nodes: spec.nodes.map((x) => ({ id: x.id, name: x.name, v: x.v, q: x.q, y: x.y })),
          links: spec.links.map((l) => ({ s: l.s, t: l.t, v: l.v, q: l.q, y: l.y }))
        });
      });
    }
    async function draw() {
      await fontsReady();
      if (futureOn()) {
        const gc = guide.cmp === 'q' ? guide.spec.compare : guide.cmp === 'y' ? guide.spec.compare_y : null;
        scene = S.layout(guide.spec, { compare: gc ? guide.cmp : null, decreases: state.decreases });
        sheet.innerHTML = S.toSVG(scene, S.dec(gc ? gc.title : guide.spec.title));
      } else {
        scene = S.layout(spec, { compare: mode(), decreases: state.decreases });
        sheet.innerHTML = S.toSVG(scene, S.dec(mode() ? cmpOf(mode()).title : spec.title));
      }
      vb = null;                                                // another layout: shown whole
      applyView();
      $$('.node', sheet).forEach((g) => {
        const n = byId.get(g.dataset.node);
        g.setAttribute('tabindex', '0');
        g.setAttribute('role', 'button');
        g.setAttribute('aria-label', `${S.dec(n.name)}: ${S.dec((n.lines[1] || [])[1] || '')}`);
      });
      sync();
      select(selected);
    }
    sheet.addEventListener('click', (e) => {
      if (dragged) { dragged = false; return; }
      const g = e.target.closest('[data-node]');
      select(g ? g.dataset.node : null);
    });
    sheet.addEventListener('keydown', (e) => {
      const g = e.target.closest && e.target.closest('[data-node]');
      if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(g.dataset.node); }
    });
    const gmsg = $('.guide-msg', el);
    const gbtn = $('[data-guide]', el);
    if (gbtn) gbtn.addEventListener('click', async () => {
      if (guide.open) { guide.on = false; guide.open = false; gmsg.hidden = true; selected = null; draw(); return; }
      gbtn.disabled = true;
      try {
        if (guide.doc === undefined) guide.doc = await ctx.guide.load();
        guide.spec = ctx.guide.build(guide.doc);
      } catch (err) {
        guide.spec = { error: `Guidance could not be read (${err.message}).` };
      } finally { gbtn.disabled = false; }
      guide.on = true;
      guide.open = true;                          // the record shows even when the next period cannot be drawn
      if (guide.spec && !guide.spec.error) {
        guide.byId = new Map(guide.spec.nodes.map((n) => [n.id, n]));
        gmsg.hidden = true;
        selected = null;
      } else {
        gmsg.textContent = (guide.spec && guide.spec.error) || 'No guidance on file.';
        gmsg.hidden = false;
        guide.on = false;
      }
      draw();
    });
    $$('[data-gcmp]', el).forEach((b) => b.addEventListener('click', () => { guide.cmp = b.dataset.gcmp; draw(); }));
    $$('[data-view]', el).forEach((b) => b.addEventListener('click', () => {
      if (guide.on || guide.open) { guide.on = false; guide.open = false; gmsg.hidden = true; selected = null; }
      const v = b.dataset.view === 'std' ? null : b.dataset.view;
      if (ctx.custom) own = v;
      else { state.compare = v; prefs.set('compare', v); }
      draw();
      if (ctx.onView) ctx.onView(mode());
    }));
    $('[data-dec]', el).addEventListener('change', (ev) => {
      state.decreases = ev.target.checked;
      prefs.set('decreases', state.decreases);
      draw();
      if (acct.prefs && acct.prefs.cmp_decreases !== state.decreases) {   // signed in: e-mailed charts follow
        const on = state.decreases;
        savePrefs({ cmp_decreases: on })
          .then(() => toast(acct.flash || (on ? 'Your e-mailed comparison charts will show decreases too' : 'Your e-mailed comparison charts will not show decreases')))
          .catch(() => {})
          .finally(() => { acct.flash = null; });
      }
    });
    $$('[data-zoom]', el).forEach((b) => b.addEventListener('click', () => {
      state.zoom = b.dataset.zoom;
      prefs.set('zoom', state.zoom);
      sync();
    }));
    $('[data-reset]', el).addEventListener('click', () => { vb = null; applyView(); });
    $$('[data-x]', el).forEach((b) => b.addEventListener('click', async () => {
      if (!scene) return;
      const share = b.dataset.x === 'share';
      const fmt = share ? 'png' : b.dataset.x;
      b.disabled = true;
      try {
        const blob = await S.exportScene(scene, fmt);
        const name = `${ctx.slug}${futureOn() ? `-guidance${guide.cmp ? '-vs-' + (guide.cmp === 'y' ? 'year-ago' : 'current') : ''}` : ctx.custom ? (mode() ? `-vs-${ctx.vsSlug}` : '') : mode() === 'q' ? '-vs-prev-quarter' : mode() === 'y' ? (yearly ? '-vs-prior-year' : '-vs-year-ago') : ''}-sankey.${fmt}`;
        if (share) {                                               // Android share sheet (X, messages, mail …)
          nativeApp.shareFile(name, 'image/png', await blobBase64(blob));
          return;
        }
        const res = await saveBlob(blob, name);
        toast(res === 'declined' ? 'Export cancelled' : res === 'failed' ? 'Download unavailable here; use Preview to save the image'
          : `Exported ${name}`, () => previewDialog(blob, fmt, name, scene));
      } catch (err) {
        toast(`Export failed: ${err.message}`);
      } finally {
        b.disabled = false;
      }
    }));
    el.redraw = draw;
    el.sync = sync;
    el.cmpOn = cmpOn;
    el.mode = mode;
    el.className = 'chart-ui';
    el.getScene = () => scene;                       // used by tests/e2e.py to check exports
    state.charts.push(el);
    draw();
    return el;
  }

  // a static, non-interactive chart (thumbnails of earlier quarters)
  async function staticChart(host, spec) {
    await fontsReady();
    host.innerHTML = S.toSVG(S.layout(spec, {}), S.dec(spec.title));
    $$('.note-mark, .hit', host).forEach((x) => x.remove());
  }

  // ---------- pages ----------
  document.addEventListener('click', (ev) => {                  // the company description: "More" / "Less"
    const b = ev.target.closest && ev.target.closest('.intro-more');
    if (!b) return;
    const box = b.closest('.intro'), open = !box.classList.contains('open');
    box.classList.toggle('open', open);
    b.textContent = open ? 'Less' : 'More';
    b.setAttribute('aria-expanded', String(open));
  });
  function setNav(page) {
    $$('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === page));
    if (window.FFNav) window.FFNav.mark();                     // web/nav.js: the group of the current page
  }
  function row(href, cells) {
    return `<tr data-href="${href}">${cells.join('')}</tr>`;
  }
  function bindRows(root) {
    $$('tr[data-href]', root).forEach((tr) => tr.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      location.hash = tr.dataset.href;
    }));
  }
  function companyCell(c) {
    return `<td><span class="co"><span class="mono">${t(c.ticker || '')}</span><a class="name" href="#c-${c.cik}">${t(c.name)}</a></span></td>`;
  }

  async function home() {
    const here = live();
    setNav('home');
    const forms = new Set(prefs.get('forms', ['10-Q', '10-K', '8-K']));
    const formGroup = (f) => (f === '6-K' ? '10-Q' : /^(20|40)-F/.test(f || '') ? '10-K' : f);   // foreign filers' forms
    const ix = await getJSON('index.json');
    const site = await getJSON('site.json').catch(() => ({}));
    const sectors = ix.sector_names || {};
    const stars = ix.companies.filter((c) => c.starred);
    const groups = ix.sectors.length + ix.industries.length;
    if (!here()) return;
    app.innerHTML = `
      <div class="home-top">
      <section class="hero">
        <div class="eyebrow">SEC EDGAR · 10-Q, 10-K and 8-K earnings releases</div>
        <h1>Every new quarterly report, drawn as one flow from revenue to cash</h1>
        <p>EDGAR is scanned every 15 minutes for new 10-Q and 10-K filings and earnings releases (8-K); each is drawn from revenue to costs, profit and operating cash flow. Click any part of a chart for what the company wrote about that line.</p>
        ${ix.demo ? `<p class="note-rule">${t(ix.demo)}</p>` : ''}
        <div class="status"><span>Updated <b>${date(ix.generated)}</b> ${t((ix.generated || '').slice(11, 16))} UTC</span>
          <span><b>${ix.companies.length.toLocaleString('en-US')}</b> companies</span><span><b>${groups}</b> sector and industry charts</span></div>
      </section>
      <section class="cta" id="cta" hidden>
        <div><h2>New charts in your inbox</h2>
          <p class="muted">Pick companies or sectors. One e-mail at 8:00 your time with each new filing’s chart and analysis, or each chart as it is filed. No password: sign in with a code sent to your inbox.</p></div>
        <form class="cta-form" id="cta-form"><input type="email" required placeholder="you@example.com" aria-label="E-mail address" autocomplete="email">
          <button class="btn primary" type="submit">Get alerts</button></form>
      </section>
      </div>
      <section class="section" id="earnings-day"></section>
      ${stars.length ? `<section class="section">
        <div class="section-head"><h2>Starred</h2><span class="muted">Companies with their full multi-quarter history</span></div>
        <div class="cards">${stars.map((c) => `<a class="card" href="#c-${c.cik}">
          <div class="t"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span></div>
          <div class="big">${t(c.rev)}</div>
          <div class="n">${t(c.label)} revenue · <span class="${tone(c.yoy)}">${pct(c.yoy)} Y/Y</span> · ${margin(c.om)} op. margin</div></a>`).join('')}</div>
      </section>` : ''}
      <section class="section daily" id="daily" hidden></section>
      <section class="section">
        <div class="section-head"><h2>Latest filings</h2><span class="muted">Newest first</span></div>
        <div class="filters">
          <input id="f-text" type="search" placeholder="Filter by name" aria-label="Filter by name">
          <select id="f-sector" aria-label="Sector"><option value="">All sectors</option>${
            Object.entries(sectors).map(([k, v]) => `<option value="${k}">${t(v)}</option>`).join('')}</select>
          <fieldset class="checks" id="f-forms"><legend>Form</legend>${['10-Q', '10-K', '8-K'].map((f) =>
            `<label><input type="checkbox" value="${f}" ${forms.has(f) ? 'checked' : ''}> ${f}${f === '8-K' ? ' <span class="muted">earnings release</span>' : f === '10-Q' ? ' <span class="muted">· 6-K</span>' : f === '10-K' ? ' <span class="muted">· 20-F</span>' : ''}</label>`).join('')}</fieldset>
        </div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Filed</th><th>Company</th><th>Period</th><th>Form</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th>Sector</th></tr></thead>
          <tbody id="rows"></tbody></table></div>
        <div><button class="btn" id="more" type="button" hidden>Show more</button></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Sectors</h2><span class="muted">Combined Sankeys of every company that reported in the latest calendar quarter</span></div>
        <div class="cards">${ix.sectors.map((s) => `<a class="card" href="#s-${s.id}">
          <div class="t"><span>${t(s.name)}</span></div><div class="n">${s.count} companies · ${calLabel(s.cal)}</div></a>`).join('') ||
          '<p class="muted">Sector charts appear once two companies in a sector have reported for the same quarter.</p>'}</div>
      </section>`;
    $('#cta-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      prefs.set('signin-email', $('#cta-form input').value.trim());
      location.hash = 'account';
    });
    Promise.all([sb(), currentUser()]).then(([c, user]) => {        // only when accounts are switched on
      const box = $('#cta');
      if (!box || !c) return;
      if (user) {
        box.querySelector('h2').textContent = 'Your alerts';
        box.querySelector('p').textContent = `Signed in as ${user.email}. Choose companies, sectors and how often.`;
        box.querySelector('form').outerHTML = '<a class="btn primary" href="#account">Manage alerts</a>';
      }
      box.hidden = false;
    }).catch(() => {});
    if (window.FFEarningsDay) window.FFEarningsDay.mount($('#earnings-day'), ix, {           // web/earnings-day.js
      onAll: () => { const r = $('#rows'); if (r) r.closest('section').scrollIntoView({ behavior: 'smooth', block: 'start' }); },
      onDay: (iso) => { const b = $(`#daily [data-day="${iso}"]`); if (b && !b.disabled && !b.classList.contains('on')) b.click(); } });
    app.classList.add('has-ed');
    dailyPanel($('#daily'), ix).then(() => {
      const on = $('#earnings-day .day.on'), b = on && $(`#daily [data-day="${on.dataset.edDay}"]`);
      if (b && !b.disabled && !b.classList.contains('on')) b.click();
    }).catch((e) => console.warn('daily report panel:', e.message));
    let limit = 60;
    const draw = () => {
      const q = $('#f-text').value.trim().toLowerCase(), sec = $('#f-sector').value;
      const list = ix.companies.filter((c) => (!q || c.name.toLowerCase().includes(q) || (c.ticker || '').toLowerCase().startsWith(q)) &&
        (!sec || c.sector === sec) && forms.has(formGroup(c.form)));
      $('#rows').innerHTML = list.slice(0, limit).map((c) => row(`c-${c.cik}`, [
        `<td>${date(c.filed)}</td>`, companyCell(c), `<td>${t(c.label)}</td>`, `<td class="mono">${t(c.form)}${c.prelim ? ' <span class="tag prelim">prelim</span>' : ''}</td>`,
        `<td class="num">${t(c.rev)}</td>`, `<td class="num ${tone(c.yoy)}">${pct(c.yoy)}</td>`, `<td class="num">${margin(c.om)}</td>`,
        `<td>${t(sectors[c.sector] || '')}</td>`])).join('') || '<tr><td colspan="8" class="muted">No filings match.</td></tr>';
      $('#more').hidden = list.length <= limit;
      bindRows($('#rows'));
    };
    ['#f-text', '#f-sector'].forEach((s) => $(s).addEventListener('input', () => { limit = 60; draw(); }));
    $$('#f-forms input').forEach((box) => box.addEventListener('change', () => {
      forms.clear();
      $$('#f-forms input:checked').forEach((x) => forms.add(x.value));
      prefs.set('forms', [...forms]);
      limit = 60;
      draw();
    }));
    $('#more').addEventListener('click', () => { limit += 120; draw(); });
    draw();
  }

  // data checks about a figure the company reports differently from the arithmetic: they link to the choice in Alerts
  const FCF_CODES = new Set(['fcf_company', 'fcf_definition', 'fcf_formula', 'revenue_recon', 'revenue_calc', 'lines_hidden',
    'lines_unmatched']);
  async function company(cik, end, all, opt) {
    const here = live();
    opt = opt || {};
    setNav('');
    const [ix, site] = await Promise.all([getJSON('index.json'), getJSON('site.json').catch(() => ({})), loadExtViews()]);
    let c;
    try {
      c = await getJSON(`c/${cik}.json`);
    } catch (err) {
      if (err.status === 404) return here() ? missingCompany(cik) : null;   // found by the search, not drawn yet
      throw err;
    }
    if (!here()) return;
    const own = c.currency || 'USD';
    const inUsd = own !== 'USD' && !!c.usd && prefs.get('ccy', 'own') === 'usd';
    if (inUsd) c = Object.assign({}, c, { quarters: c.usd.quarters, years: c.usd.years });
    CUR = inUsd ? '$' : symOf(own);
    const p = c.profile, qs = c.quarters.map(fcfView), ys = (c.years || []).map(fcfView);
    const fy = !!opt.fy && ys.length > 0;                           // a full fiscal year (10-K)
    const cmpId = opt.cmp || null;                                  // a comparison this reader asked for
    if (cmpId) all = false;
    const q = fy ? (ys.find((x) => x.end === end) || ys[0]) : ((end && qs.find((x) => x.end === end)) || qs[0]);
    const sectors = ix.sector_names || {};
    const ticker = (p.tickers || [])[0] || '';
    const indSlug = String(p.sic || 'none');
    const hasInd = ix.industries.some((i) => i.id === indSlug);
    const hasSec = ix.sectors.some((s) => s.id === p.sector);
    const fye = p.fye ? new Date(Date.UTC(2001, +p.fye.slice(0, 2) - 1, +p.fye.slice(2))).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : null;
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a><span>/</span>${hasSec ? `<a href="#s-${p.sector}">${t(sectors[p.sector])}</a>` : `<span>${t(sectors[p.sector] || 'Other')}</span>`}
          <span>/</span>${hasInd ? `<a href="#i-${indSlug}">${t(p.industry)}</a>` : `<span>${t(p.industry || 'SIC ' + p.sic)}</span>`}</div>
        <div class="co-head">
          <div class="co-title"><h1>${t(p.name)}</h1>${ticker ? `<span class="tag mono">${t(ticker)}</span>` : ''}${(p.exchanges || []).filter(Boolean).slice(0, 1).map((x) => `<span class="muted">${t(x)}</span>`).join('')}</div>
          <div class="co-actions">
            ${ticker ? `<button class="btn follow primary" type="button" hidden data-follow="ticker:${t(ticker)}">☆ Follow</button>` : ''}
            ${cmpId ? '' : `<button class="btn send" type="button" hidden data-send="${p.cik}|${(all ? qs : [q]).map((x) => x.end).join(',')}|${fy ? 'fy' : 'q'}"
              title="Sent to the address you signed in with: chart, analysis and what changed">✉ Email me ${all ? `all ${qs.length} quarters` : t(q.label) + (fy ? ' full year' : '')}</button>`}
            ${ticker ? `<a class="btn" href="#studio/k=fund&amp;t=${encodeURIComponent(ticker)}&amp;m=revenue&amp;ttm=0" title="Animated videos of this company's figures and its share price (web/studio.js)">▶ <span class="co-long">Make a </span>video</a>` : ''}
          </div>
        </div>
        <div class="meta">
          ${c.starred ? '<span class="tag star">★ Starred · multi-quarter history</span>' : ''}${!all && !cmpId && q.form === '8-K' ? prelimTag : ''}${!all && !cmpId && q.release_check ? finalTag(q.release_check) : ''}
          <details class="co-codes"><summary>Company details</summary><span>CIK <span class="mono">${p.cik}</span></span><span>SIC <span class="mono">${t(p.sic)}</span> ${t(p.industry)}</span>${
            fye ? `<span>Fiscal year ends ${fye}</span>` : ''}${p.category ? `<span>${t(String(p.category).split(/\s*<br\s*\/?>\s*/i).filter(Boolean).join(' · '))}</span>` : ''}</details>
        </div>
        ${freshLine(qs[0], ix.generated)}
        <div class="meta co-chains" id="co-chains" hidden></div>
        <div class="meta co-index" id="co-index" hidden></div>
        ${introHTML(c.intro)}
        ${companyTabs(cik, '')}
      </div>
      <div class="pills co-period" id="co-period">
        <label class="co-period-pick"><span>Period</span><select id="co-period-sel" aria-label="Period">
          <optgroup label="Quarters">${qs.map((x) => `<option value="#c-${cik}-${x.end}" ${!all && !fy && !cmpId && x === q ? 'selected' : ''}>${t(x.label)}${x.form === '8-K' ? ' · 8-K' : ''} · ${t(x.end)}</option>`).join('')}</optgroup>
          ${ys.length ? `<optgroup label="Full years">${ys.map((x) => `<option value="#c-${cik}-fy-${x.end}" ${fy && x === q ? 'selected' : ''}>${t(x.label)} · full year</option>`).join('')}</optgroup>` : ''}
          ${qs.length > 1 ? `<optgroup label="History"><option value="#c-${cik}-all" ${all ? 'selected' : ''}>All ${qs.length} quarters</option></optgroup>` : ''}
          ${cmpId ? '<option value="" selected>A comparison you asked for</option>' : ''}
        </select></label>
        <button class="pill cmp ${cmpId ? 'on' : ''}" type="button" id="cmp-open" hidden aria-expanded="false" aria-controls="cmp-panel">⇄ Compare any two</button>
      </div>
      ${own !== 'USD' ? ccyBar(own, inUsd, !!c.usd, q) : ''}
      <section class="section cmp-panel" id="cmp-panel" hidden></section>
      <div id="ff-overview"></div>
      <div id="ff-company-disclosures"></div>
      <div id="body"></div>
      <p class="co-more muted" id="co-more"></p>`;
    $('#co-period-sel').addEventListener('change', (ev) => { if (ev.target.value) location.hash = ev.target.value.slice(1); });
    if (ticker) coChains($('#co-chains'), ticker);
    if (ticker) coIndex($('#co-index'), ticker);
    $('#co-more').innerHTML = `More on ${t(p.name)}: <a href="#c-${cik}-cash">profit &amp; cash</a> · <a href="#c-${cik}-x-fairvalue">fair value</a> · <a href="#c-${cik}-value">DCF calculator</a> · <a href="#c-${cik}-links">customers, suppliers &amp; growth model</a>`;
    const body = $('#body');
    if (window.FFCompanyDisclosures && !cmpId && !all) window.FFCompanyDisclosures.mount($('#ff-company-disclosures'), { cik: p.cik, here, compact: true });
    if (window.FFOverview && !cmpId && !all) window.FFOverview.mount($('#ff-overview'), { c, q, ticker, cik: p.cik, here });   // web/overview.js
    app.querySelectorAll('[data-ccy]').forEach((b) => { b.onclick = () => { prefs.set('ccy', b.dataset.ccy); route(); }; });
    initCompare(c, cik);
    if (cmpId) {
      showComparison(body, c, cmpId, ticker);
      return;
    }
    if (all) {
      body.innerHTML = `<div class="section"><div class="section-head"><h2>Trend</h2>
        <span class="muted">Revenue, operating profit, net earnings and operating cash flow; each row to its own scale</span></div>
        <div class="sheet fit" id="trend"></div></div>
        <div class="section"><div class="section-head"><h2>Quarter by quarter</h2>
        <span class="muted">Same format each quarter; open one for notes, comparison and export</span></div>
        <div class="thumbs">${qs.map((x, i) => `<a class="thumb" href="#c-${cik}-${x.end}"><div class="sheet fit" data-i="${i}"><div class="loading">Drawing…</div></div>
        <span><b>${t(x.label)}</b> <span class="muted">· ${t(x.form)} filed ${date(x.filed)} · revenue ${money(x.headline.revenue)} · net ${money(x.headline.ni)}</span></span></a>`).join('')}</div></div>
        ${historyTable(qs, cik)}`;
      fontsReady().then(() => {
        const h = $('#trend');
        if (!h) return;
        const sc = S.history(c);
        h.style.maxWidth = `${sc.W}px`;                          // a few quarters make a narrow chart: never blown up
        h.innerHTML = S.toSVG(sc, `${S.dec(p.name)} quarter by quarter`);
      });
      $$('.thumb .sheet', body).forEach((h) => staticChart(h, qs[+h.dataset.i]));
      bindRows(body);
      return;
    }
    const ui = chartUI(q, {
      company: S.dec(p.name), form: q.form, label: q.label, docUrl: q.doc_url,
      slug: `${(ticker || p.cik)}-${q.label}`.replace(/\s+/g, '-'),
      onView: () => renderChanges(),
      trend: (id) => trendSeries(fy ? ys : qs, q, id, fy), cik: p.cik,
      // "Show guidance": the latest period only, reported in dollars (web/guidance.js; holders/<ticker>.json → guidance)
      guide: window.FFGuidance && ticker && own === 'USD' && (q === qs[0] || (fy && q === ys[0])) ? {
        // the latest guidance and every earlier release's (the guidance record: hit rate and moves)
        load: () => fetch(`disclosures/data/holders/${encodeURIComponent(ticker)}.json`).then((r) => (r.ok ? r.json() : null))
          .then((h) => (h && (h.guidance || h.guidance_history) ? { g: h.guidance || null, hist: h.guidance_history || null } : null)).catch(() => null),
        build: (d) => window.FFGuidance.future(q, d && d.g, { company: c, name: S.dec(p.name), history: d && d.hist }),
      } : null,
    });
    body.appendChild(ui);
    const ctl = $('.controls', ui), per = $('#co-period');
    if (ctl && per) { per.classList.add('in-chart'); ctl.prepend(per); }   // the period sits on the chart it changes
    if (window.matchMedia && matchMedia('(max-width: 560px)').matches && $('#ff-overview')) ui.after($('#ff-overview'));   // phones: the chart first
    if (window.FFEditor && !fy && (own === 'USD' || inUsd)) window.FFEditor.mount(body, { q, c, ticker, slug: `${(ticker || p.cik)}-${q.label}`.replace(/\s+/g, '-') });   // web/editor.js: edit / what-if
    const acc = accession(q.index_url);
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose">
        <h2>Analysis</h2>
        ${(q.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        <div id="changes"></div>
        <p class="note-rule">Written by fixed rules from the reported figures (no language model): growth, margins, the line that drove the change, and cash conversion.</p>
      </div>
      <div class="prose">
        <h2>Filing</h2>
        <dl class="facts">
          <dt>Form</dt><dd><span class="mono">${t(q.form)}</span>${q.form === '8-K' ? ' · Item 2.02 earnings release, preliminary until the 10-Q/10-K is filed' : q.form === '6-K' ? ' · quarterly results release of a foreign private issuer (it files no 10-Q)' : /^(20|40)-F/.test(q.form) ? ' · annual report of a foreign private issuer' : ''}</dd>
          <dt>Period</dt><dd>${fy ? `${t(q.label)} · fiscal year ended ${date(q.end)}` : `${t(q.label)} · quarter ended ${date(q.end)} (calendar ${calLabel(q.cal)})`}</dd>
          <dt>Filed</dt><dd>${date(q.filed)}</dd>
          ${q.release_check ? `<dt>Earnings release</dt><dd>${t(releaseCheckText(q.release_check))}</dd>` : ''}
          ${acc ? `<dt>Accession</dt><dd class="mono">${acc}</dd>` : ''}
          <dt>Documents</dt><dd>${q.doc_url ? `<a href="${t(q.doc_url)}" target="_blank" rel="noopener">${q.form === '8-K' || q.form === '6-K' ? 'Press release' : 'Report'} ↗</a> · ` : ''}${
            q.index_url ? `<a href="${t(q.index_url)}" target="_blank" rel="noopener">Filing index ↗</a>` : `<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${p.cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">EDGAR filings ↗</a>`}</dd>
          <dt>Data</dt><dd>${q.form === '8-K' ? 'This quarter read from the tables in the press release (Exhibit 99.1); earlier quarters from XBRL company facts'
            : q.form === '6-K' ? 'This quarter read from the tables in the results release (6-K exhibit); full years from the 20-F (XBRL company facts)'
            : fy ? 'Full-year values as reported in the 10-K (XBRL company facts); revenue lines from the filing’s own XBRL instance'
            : 'XBRL company facts; revenue lines from the filing’s own XBRL instance'}</dd>
          ${(q.checks || []).length ? `<dt>Data checks</dt><dd><ul class="checks">${q.checks.map((x) => `<li class="${x.level === 'warn' ? 'warn' : ''}">${
            x.level === 'warn' ? '<b>Please verify:</b> ' : ''}${t(x.text)}${FCF_CODES.has(x.code) && (q.fcf_alt || q.fcf_basis === 'ocf' || x.code === 'fcf_formula' || /^lines_/.test(x.code))
            ? ` <a href="#account" class="fcf-pref" title="Alerts → Free cash flow: the company’s own figure or operating cash flow − capex">Change this in Alerts</a>` : ''}</li>`).join('')}</ul></dd>` : ''}
          <dt>Accuracy</dt><dd>Read automatically from the filing; errors are possible, so check the filing before relying on a figure.${
            site.repo ? ` <a href="https://github.com/${t(site.repo)}/issues/new?title=${encodeURIComponent(`Data error: ${ticker || p.cik} ${S.dec(q.label)}`)}&body=${
              encodeURIComponent(`Chart: ${location.href}\nWhich figure looks wrong, and what does the filing say?\n`)}" target="_blank" rel="noopener">Report an error ↗</a>` : ''}</dd>
        </dl>
      </div>`;
    body.appendChild(text);
    const disc = $('#ff-company-disclosures');                 // debt and disclosure signals: after the chart and its analysis
    if (disc) text.after(disc);
    // Created by ChatGPT (OpenAI): user-initiated loopback assistant, separate from rule-based analysis.
    // owner tool only (see #owner): it needs the Windows companion running on this computer
    if (window.LocalFilingModel && prefs.get('owner', false)) window.LocalFilingModel.mount(body, p, q);
    if (window.FFEPSResearch && !fy && ticker) window.FFEPSResearch.mount(body, {ticker, cik: p.cik, here});
    holdersSection(body, ticker, here);                     // who holds it: 13F managers and public officials (Disclosures)
    if (prefs.get('owner', false)) {                      // owner tool: re-read this company's stored figures
      ownerVerified().then(async (ok) => {
        const cl = await sb();
        const meta = $('.page-head .meta');
        if (!ok || !cl || !meta || !meta.isConnected) return;
        const b = document.createElement('button');
        b.className = 'btn';
        b.type = 'button';
        b.dataset.reread = p.cik;
        b.title = 'Owner: a short scan (owner fast lane) reads this company’s stored figures again from SEC';
        b.textContent = '↻ Re-read figures';
        meta.insertBefore(b, meta.querySelector('.tag.star, span:not(.tag)'));
        b.addEventListener('click', (ev) => withProgress(ev.currentTarget, toast, async () => {
          const r = await askReread([+p.cik]);
          return r.ok ? 'Re-read asked (owner fast lane): a short scan starts within a minute, usually done in 5–15 minutes' : r.msg;
        }));
      });
    }
    if (prefs.get('owner', false) && !fy) {               // owner tool (see #owner): only for the verified owner
      ownerVerified().then(async (ok) => {
        const osets = ok ? await ownerSettings() : null;
        const thread = ok && text.isConnected ? threadSection(q, p, site.repo, osets, c) : null;
        if (thread) text.after(thread);
      });
    }
    if (qs.length > 1) {
      const h = document.createElement('div');
      h.innerHTML = historyTable(qs, cik);
      body.appendChild(h);
      bindRows(h);
    }
    function renderChanges() {
      const box = $('#changes');
      if (!box) return;
      box.innerHTML = changesHTML(q);
    }
    renderChanges();
  }

  // the share count the valuation divides by: a filer's diluted count can be in millions (McDonald's tags 711.1) or
  // thousandths (Waters, 98.2 billion), stale, or from before a split (KLA) — checked against the cover page and the
  // price-to-sales it would imply (the same rules as disclosures/app/valuation.py settle_shares)
  function shareCount(V, price) {
    const d = V.diluted, o = V.outstanding, rev = V.revenue;
    const ok = (v) => v >= 1e4 && v <= 3e10 && (!(price > 0) || !(rev >= 1e8) || (price * v / rev >= 0.025 && price * v / rev <= 2000));
    if (d > 0 && o > 0 && (V.outstanding_at || '') > (V.diluted_end || '9') && o > 1.3 * d && ok(o))
      return { v: o, key: 'outstanding', note: 'cover page: more shares than the period\'s diluted count (a split or an issue since)' };
    if (d > 0 && ok(d)) return { v: d, key: 'diluted' };
    if (d > 0 && o > 0) for (const k of [1e3, 1e6, 1e-3, 1e-6]) {
      const w = d * k;
      if (ok(w) && w / o >= 0.67 && w / o <= 1.5) return { v: w, key: 'diluted', note: `filed as ${d.toLocaleString('en-US')} — a count in ${k > 1 ? (k === 1e3 ? 'thousands' : 'millions') : 'the wrong unit'}; read as ${(w / 1e6).toFixed(1)}M` };
    }
    if (o > 0 && ok(o)) return { v: o, key: 'outstanding', note: d > 0 ? `the filed diluted count (${d.toLocaleString('en-US')}) does not fit; cover page used` : '' };
    return { v: d || o || null, key: d ? 'diluted' : 'outstanding', note: d || o ? 'not checked: no price or revenue to test it against' : '' };
  }

  // ---------- holders: the Disclosures hub's 13F positions and officials' reviewed records for this ticker ----------
  const amountRange = (r) => (r.amount_max == null ? `over $${Math.round((r.amount_min || 1) - 1).toLocaleString('en-US')}`
    : `$${Math.round(r.amount_min).toLocaleString('en-US')}–$${Math.round(r.amount_max).toLocaleString('en-US')}`);
  const whole = (v) => (v == null ? '—' : Math.round(v).toLocaleString('en-US'));
  // ---------- company tabs: Earnings · Cash & quality · Valuation ----------
  // more company views from the Disclosure Hub: disclosures/views.json lists them ({id, label, script, global}); each script
  // is a shared view (like debt-view.js) exposing window[global].render(el, {cik, ticker, company, here, hub})
  let EXT_VIEWS = [], extViewsLoad = null;
  const SITE_TIME = {};
  const loadExtViews = () => extViewsLoad || (extViewsLoad = fetch('disclosures/views.json', { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : [])).catch(() => []).then((v) => { EXT_VIEWS = Array.isArray(v) ? v.filter((x) => x && /^[a-z0-9]+$/.test(x.id || '')) : []; return EXT_VIEWS; }));
  const extScripts = {};
  const loadExtScript = (src) => extScripts[src] || (extScripts[src] = new Promise((ok, bad) => {
    const sc = document.createElement('script');
    sc.src = 'disclosures/' + src;
    sc.onload = () => ok();
    sc.onerror = () => { delete extScripts[src]; bad(new Error(src + ' did not load')); };
    document.head.appendChild(sc);
  }));
  async function extView(body, id, c, ticker, here) {
    const v = EXT_VIEWS.find((x) => x.id === id);
    if (!v) { body.innerHTML = '<p class="muted">This view is not available.</p>'; return; }
    body.innerHTML = '<p class="muted">Loading…</p>';
    try {
      await loadExtScript(v.script);
      if (!here()) return;
      body.innerHTML = '';
      let target = body;
      if (id === 'quality' && window.FFQualityVisuals) {
        window.FFQualityVisuals.mount(body, c);
        const links = document.createElement('p');
        links.innerHTML = `<a href="#c-${c.profile.cik}-cash">Profit & cash: cash bridge, accruals and reserves →</a> · <a href="#c-${c.profile.cik}-debt">Debt & rates: maturities and coverage →</a>`;
        body.appendChild(links);
        target = document.createElement('div'); body.appendChild(target);
      }
      await window[v.global].render(target, { cik: c.profile.cik, ticker, company: c, here, hub: 'disclosures/' });
    } catch (err) {
      if (here()) body.innerHTML = `<p class="muted">${t(v.label)} could not load (${t(err.message)}).</p>`;
    }
  }
  // five groups of company views; the active group's views show as a second row (the routes stay #c-<cik>-<view>)
  const TAB_GROUPS = [
    ['Earnings', [['', 'Earnings'], ['x-charts'], ['eps', 'EPS forecast & preview'], ['x-filings'], ['x-events'], ['posts', 'Posts']]],
    ['Cash & capital', [['cash', 'Profit & cash'], ['dollar', 'Where each $1 goes'], ['capital', 'Capital allocation'], ['bs', 'Balance sheet'], ['debt', 'Debt & rates'], ['risk', 'Disclosures & risk'], ['x-notes'], ['x-quality'], ['x-workforce']]],
    // the Disclosure Hub's fair value (every method, its football field, sensitivity, credit) leads; the DCF you can edit next
    ['Valuation & expectations', [['x-fairvalue'], ['value', 'DCF calculator'], ['consensus', 'Consensus'], ['revisions', 'Revisions'], ['x-outlook'], ['x-lbo'], ['x-hype'], ['x-rotation'], ['x-options'], ['x-paths'], ['x-opportunity'], ['x-odds']]],
    ['Holders & trades', [['holders', '13F funds & officials'], ['x-insiders']]],
    ['Relationships & model', [['links', 'Customers, suppliers & model'], ['shock', 'Shock panel'], ['x-outside']]],
  ];
  function tabGroups() {
    const ext = new Map(EXT_VIEWS.map((v) => ['x-' + v.id, v.label]));
    const used = new Set(['x-earnings']);                   // the earnings preview lives inside the EPS forecast view
    const groups = TAB_GROUPS.map(([label, items]) => [label, items.map(([k, l]) => {
      if (k.startsWith('x-')) { if (!ext.has(k)) return null; used.add(k); return [k, l || ext.get(k)]; }
      return [k, l];
    }).filter(Boolean)]);
    ext.forEach((l, k) => { if (!used.has(k)) groups[groups.length - 1][1].push([k, l]); });   // a new Disclosure Hub view: the last group
    return groups;
  }
  const companyTabs = (cik, active) => {
    const groups = tabGroups();
    const cur = groups.find(([, items]) => items.some(([k]) => k === (active === 'x-earnings' ? 'eps' : active))) || groups[0];
    setTimeout(() => $$('.co-tabs a.on, .co-subtabs a.on').forEach((a) => {   // phones: the current tab in view
      const bar = a.parentElement;
      if (bar.scrollWidth > bar.clientWidth) bar.scrollLeft = Math.max(0, a.offsetLeft - bar.offsetLeft - 24);
    }), 0);
    const href = (k) => `#c-${cik}${k ? '-' + k : ''}`;
    return `<nav class="co-tabs" aria-label="Company views">${groups.map((g) => {
      const on = g === cur, first = on ? active : g[1][0][0];
      return `<a href="${href(first)}"${on ? ' class="on" aria-current="page"' : ''}>${g[0]}</a>`;
    }).join('')}</nav>${cur[1].length > 1 ? `<nav class="co-subtabs" aria-label="${t(cur[0])} views">${cur[1].map(([k, l]) =>
      `<a href="${href(k)}"${k === active ? ' class="on" aria-current="page"' : ''}>${t(l)}</a>`).join('')}</nav>` : ''}`;
  };

  function ccyBar(own, inUsd, hasUsd, q) {
    const nm = CCY_NAME[own] || own, fxq = q && q.fx;
    const btn = (k, label, on) => `<button type="button" class="pill${on ? ' on' : ''}" data-ccy="${k}" aria-pressed="${on}">${label}</button>`;
    const say = inUsd
      ? `In US dollars, converted from ${t(nm)} (${own})${fxq ? `: ${t(fxq.note)}${fxq.src === 'official' && fxq.text ? ` <span class="muted">— “${t(String(fxq.text).slice(0, 220))}”</span>` : ''}` : ''}. Each comparison period at its own rate, so changes include the currency’s move.`
      : `Amounts in ${t(nm)} (${own}), as the company reports them.${hasUsd ? ' The same charts in US dollars: at the company’s own convenience rate when its filing gives one, else the period’s average exchange rate.' : ' No exchange rate is available for a dollar version yet.'}`;
    return `<div class="ccy-bar" role="group" aria-label="Currency">${btn('own', `${symOf(own).trim()} ${own}`, !inUsd)}${hasUsd ? btn('usd', 'US$', inUsd) : ''}<span class="muted">${say}</span></div>`;
  }

  // customers & suppliers (web/network.js), the growth model (web/model.js) and the chains the company is in
  async function linksSection(body, c, ticker, here) {
    const cik = c.profile.cik;
    body.innerHTML = `<div class="section" id="co-links-chains" hidden></div>
      <section class="section" id="co-network" hidden></section>
      <section class="section" id="co-model" hidden></section>
      <p class="muted" id="co-links-none" hidden>No customer or supplier is named for ${t(S.dec(c.profile.name))} in the annual reports read so far, and the growth model has no fit for it yet: the scan reads a few dozen annual reports a run, largest companies first.</p>`;
    const jobs = [];
    if (window.FFNetwork) jobs.push(window.FFNetwork.company($('#co-network'), cik));
    if (window.FFModel) jobs.push(window.FFModel.company($('#co-model'), cik));
    if (ticker) {
      const box = $('#co-links-chains');
      jobs.push(getJSON('chains/index.json').then((ix) => {
        if (here && !here()) return;
        const T = String(ticker).toUpperCase();
        const mine = (ix.chains || []).map((ch) => {
          const L = (ch.layers || []).find((x) => (x.tickers || []).includes(T));
          return (ch.buyers || []).includes(T) ? [ch, 'buyer'] : L ? [ch, L.name] : null;
        }).filter(Boolean);
        if (!mine.length) return;
        box.innerHTML = `<div class="section-head"><h2>In the supply chains and themes</h2><span class="muted">Each chain’s page draws where its money flows</span></div><div class="pills">${mine.map(([ch, role]) => `<a class="pill" href="#chain-${t(ch.id)}">${t(ch.name)} · ${t(role)}</a>`).join('')}</div>`;
        box.hidden = false;
      }).catch(() => {}));
    }
    await Promise.all(jobs.map((j) => Promise.resolve(j).catch(() => {})));
    if (here && !here()) return;
    if (['#co-network', '#co-model', '#co-links-chains'].every((id) => !$(id) || $(id).hidden)) $('#co-links-none').hidden = false;
  }

  async function analysisPage(cik, which) {
    const here = live();
    setNav('');
    let c;
    try {
      c = await getJSON(`c/${cik}.json`);
    } catch (err) {
      if (err.status === 404) return here() ? missingCompany(cik) : null;
      throw err;
    }
    await loadExtViews();
    try { SITE_TIME.generated = (await getJSON('index.json')).generated; } catch (err) { /* the line just leaves the time out */ }
    if (!here()) return;
    const p = c.profile, ticker = (p.tickers || [])[0] || '';
    CUR = symOf(c.currency || 'USD');                       // these views are read from XBRL in the reported currency
    evReset(c);
    app.innerHTML = `<div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a><span>/</span><a href="#c-${cik}">${t(p.name)}</a></div>
        <h1>${t(p.name)}</h1>
        <div class="meta">${ticker ? `<span class="tag mono">${t(ticker)}</span>` : ''}<span>CIK <span class="mono">${p.cik}</span></span>${ticker ? `<a class="tag" href="#studio/k=growth&amp;t=${encodeURIComponent(ticker)},SPY&amp;from=${new Date(Date.now() - 5 * 365.25 * 864e5).toISOString().slice(0, 10)}">▶ Make a video</a>` : ''}${
          p.industry ? `<span>${t(p.industry)}</span>` : ''}</div>
        ${freshLine((c.quarters || [])[0], (SITE_TIME.generated || ''))}
        ${companyTabs(cik, which)}
      </div><div id="body"></div>`;
    const body = $('#body');
    if (which === 'shock') return window.FFShock.mount(body, {company:c, cik, ticker, here});
    if (which === 'risk') return window.FFCompanyDisclosures.mount(body, { cik: p.cik, here });
    if (which === 'debt') return debtSection(body, cik, here);
    if (which === 'consensus') return consensusSection(body, cik, here);
    if (which === 'eps') {                                     // web/eps-research.js, with the hub's earnings preview inside
      const preview = async (el) => {                          // only when a report is near (the hub has a document)
        const v = EXT_VIEWS.find((x) => x.id === 'earnings');
        if (!v || !ticker) return false;
        await loadExtScript(v.script);
        const P = window[v.global];
        const r = await fetch(`disclosures/data/research/earnings/c/${P.fname ? P.fname(ticker) : ticker}.json`, { cache: 'no-cache' }).catch(() => null);
        if (!r || !r.ok) return false;
        if (P.renderDoc) P.renderDoc(el, await r.json()); else await P.render(el, { cik: p.cik, ticker, company: c, here, hub: 'disclosures/' });
        return true;
      };
      if (window.FFEPSResearch) return window.FFEPSResearch.mount(body, { ticker, cik: p.cik, here, preview });
      body.innerHTML = '<p class="muted">The EPS forecast script did not load.</p>';
      return;
    }
    if (which === 'posts') return postsSection(body, c, ticker, here);
    if (which === 'holders') return ticker ? holdersSection(body, ticker, here) : (body.innerHTML = '<p class="muted">No ticker on file, so the 13F and officials\u2019 records cannot be matched to this company.</p>');
    if (which === 'links') return linksSection(body, c, ticker, here);
    if (which === 'dollar') return window.FFFlowLab ? window.FFFlowLab.company(body, { cik: p.cik, ticker, name: p.name, here }) : (body.innerHTML = '<p class="muted">The money flow script did not load.</p>');
    if (which.startsWith('x-')) return extView(body, which.slice(2), c, ticker, here);
    const D = c.quality;
    if (!D || !((D.q || []).length || (D.fy || []).length)) {
      body.innerHTML = `<p class="muted">The figures for this view have not been read for ${t(p.name)} yet: the scan reads a few dozen companies a run, largest first.</p>`;
      return;
    }
    if (c.currency && c.currency !== 'USD') {
      const note = document.createElement('p');
      note.className = 'muted ccy-bar';
      note.textContent = `Amounts in ${CCY_NAME[c.currency] || c.currency} (${c.currency}), as the company reports them.`;
      body.appendChild(note);
      if (which === 'value') {
        const v = document.createElement('p');
        v.className = 'muted';
        v.textContent = 'Valuation compares the share price in US dollars with the figures, so it is not drawn for a company that reports in another currency yet. The Earnings tab has the same charts in US dollars.';
        body.appendChild(v);
        return;
      }
    }
    if (which === 'cash') {
      if (window.FFQualityVisuals) window.FFQualityVisuals.mount(body, c);
      if (window.FFQualityIPO) window.FFQualityIPO.quality(body, {...c, cik});
      driversSection(body, c);
      qualitySection(body, c, (c.quarters || [])[0], false);
      cashSection(body, c);
    } else if (which === 'capital') { capitalSection(body, c, ticker); postBelow(body, 'capital', c, ticker, here); }
    else if (which === 'revisions') revisionsSection(body, c);
    else if (which === 'bs') reformSection(body, c);
    else valuationSection(body, c, ticker, here);
  }

  // ---------- posts for X: every chart family of a company as a ready-to-post text with its analysis (disclosures/posts.js) ----------
  let postsLoad = null;
  const loadPosts = () => postsLoad || (postsLoad = new Promise((ok) => {
    if (window.FFPosts) return ok();
    const sc = document.createElement('script');
    sc.src = 'disclosures/posts.js';
    sc.onload = () => ok();
    sc.onerror = () => { postsLoad = null; ok(); };
    document.head.appendChild(sc);
  }));
  async function postBelow(body, kind, c, ticker, here) {
    await loadPosts();
    if (!window.FFPosts || (here && !here())) return;
    const it = window.FFPosts.build(kind, { ticker, cik: c.profile.cik, name: S.dec(c.profile.name), site: c });
    if (!it) return;
    const box = document.createElement('div');
    box.className = 'section';
    box.innerHTML = window.FFPosts.box(it);
    body.appendChild(box);
    window.FFPosts.bind(box);
  }
  async function postsSection(body, c, ticker, here) {
    const name = S.dec(c.profile.name);
    body.innerHTML = `<div class="section"><div class="section-head"><h2>Posts for X</h2><span class="muted">Every chart family of ${t(name)}, written as a post</span></div>
      <p class="muted" style="max-width:72ch">Each post comes with a paragraph of analysis and a short narrative, written by fixed rules from the data on this site (no language model; every number is in the charts):
        the earnings Sankey, Polymarket and Kalshi against the options, the flows of 13F managers, ETFs, insiders (with their 10b5-1 plan trades) and officials,
        capital allocation, debt, and the company's place in every rotation chart (RRG 2-D / 3-D / 4-D, the momentum clock, the solar system, the galaxy). Edit, then copy or open in X.
        On top, <b>Compose</b>: today's quote first, then tick the angles you want — what the numbers lean to, the latest 8-K, insiders, the next report, analysts, smart money, the range, debt, the quarter — and one post is written from them.</p>
      <div id="posts-box"><p class="muted">Reading the data…</p></div></div>`;
    await loadPosts();
    if (!here() || !window.FFPosts) { if (here()) $('#posts-box').innerHTML = '<p class="muted">The posts could not load.</p>'; return; }
    const B = await window.FFPosts.load(ticker, c.profile.cik, ['compose']);   // every source: the composer ticks any angle
    B.site = c;
    if (!here()) return;
    const items = window.FFPosts.all(B), box = $('#posts-box');
    window.FFPosts.render(box, items);
    if (!items.length) box.innerHTML = '<p class="muted">No data for a post yet.</p>';
    if (window.FFPosts.composer) window.FFPosts.composer(box, B);                // on top: tick the angles, one post
  }

  // ---------- debt & rates: drawn by the Disclosure Hub's shared view (disclosures/debt-view.js, data from app/debt.py) ----------
  let debtViewLoad = null;
  const loadDebtView = () => debtViewLoad || (debtViewLoad = new Promise((ok, bad) => {
    if (window.DebtView) return ok();
    const sc = document.createElement('script');
    sc.src = 'disclosures/debt-view.js';
    sc.onload = () => ok();
    sc.onerror = () => { debtViewLoad = null; bad(new Error('debt view did not load')); };
    document.head.appendChild(sc);
  }));
  async function debtSection(body, cik, here) {
    body.innerHTML = `<div class="section"><p class="muted">Loading debt, rates and credit risk…</p></div>`;
    let d = null, err = null;
    try {
      const [r] = await Promise.all([fetch(`disclosures/data/debt/c/${cik}.json`), loadDebtView(), loadPosts()]);
      if (r.ok) d = await r.json();
      else if (r.status !== 404) err = 'HTTP ' + r.status;
    } catch (e) { err = e.message; }
    if (!here()) return;
    if (!d) {
      body.innerHTML = `<div class="section"><p class="muted">${err ? 'The debt data could not load (' + t(err) + ').'
        : 'The debt figures for this company have not been read yet: the collector reads a few hundred companies every two hours, largest first.'}</p>
        <p class="muted">Market rates, banks’ deposits and the screener of every company are in the <a href="disclosures/#debt">Disclosure Hub → Debt &amp; rates</a>.</p></div>`;
      return;
    }
    const box = document.createElement('div');
    box.className = 'section debt-section';
    body.innerHTML = '';
    body.appendChild(box);
    window.DebtView.render(box, d);
    const more = document.createElement('p');
    more.className = 'muted';
    more.innerHTML = `Compare with every company, market rates and banks’ CDs in the <a href="disclosures/#debt">Disclosure Hub → Debt &amp; rates</a>.`;
    body.appendChild(more);
  }

  // ---------- consensus: analysts, prediction markets and our model, drawn by the Hub's shared view (disclosures/consensus-view.js, app/consensus.py) ----------
  let consViewLoad = null;
  const loadConsView = () => consViewLoad || (consViewLoad = new Promise((ok, bad) => {
    if (window.ConsensusView) return ok();
    const sc = document.createElement('script');
    sc.src = 'disclosures/consensus-view.js';
    sc.onload = () => ok();
    sc.onerror = () => { consViewLoad = null; bad(new Error('consensus view did not load')); };
    document.head.appendChild(sc);
  }));
  async function consensusSection(body, cik, here) {
    body.innerHTML = `<div class="section"><p class="muted">Loading analysts' estimates and prediction markets…</p></div>`;
    let d = null, err = null;
    try {
      const [r] = await Promise.all([fetch(`disclosures/data/consensus/c/${cik}.json`), loadConsView()]);
      if (r.ok) d = await r.json();
      else if (r.status !== 404) err = 'HTTP ' + r.status;
    } catch (e) { err = e.message; }
    if (!here()) return;
    if (!d) {
      body.innerHTML = `<div class="section"><p class="muted">${err ? 'The consensus data could not load (' + t(err) + ').'
        : 'Analysts\u2019 estimates for this company have not been read yet: the collector reads every company over its first runs, largest first, then refreshes each daily.'}</p>
        <p class="muted">The earnings calendar, every open prediction market and the track record are in the <a href="disclosures/#consensus">Disclosure Hub → Consensus</a>.</p></div>`;
      return;
    }
    const box = document.createElement('div');
    box.className = 'section consensus-section';
    body.innerHTML = '';
    body.appendChild(box);
    window.ConsensusView.render(box, d);
    const more = document.createElement('p');
    more.className = 'muted';
    more.innerHTML = `The earnings calendar, every open prediction market and how they did are in the <a href="disclosures/#consensus">Disclosure Hub → Consensus</a>.`;
    body.appendChild(more);
  }

  // ---------- evidence drawer: where a figure comes from ----------
  // A reference from pipeline/fsa.py is [concept index, how, [filing indexes], balance date?] into quality.src.
  const HOW = {
    '3m': 'Three-month figure as filed.',
    ytd: 'Derived: the year-to-date figure minus the previous year-to-date figure of the same fiscal year (Q2 = H1 − Q1, Q3 = 9M − H1, Q4 = FY − 9M).',
    fy: 'Full fiscal year as filed.',
    ttm: 'Derived: trailing twelve months = the last full fiscal year + this fiscal year to date − the same period a year earlier (three filings).',
    bal: 'Balance sheet amount.',
  };
  const ev = { reg: new Map(), n: 0, c: null };
  function evReset(c) { ev.reg.clear(); ev.n = 0; ev.c = c; }
  // a figure the reader can open: payload = {title, value (formatted), period, ref} or {title, value, period, formula, inputs: [payload]}
  function evBtn(text, payload, cls) {
    if (!payload || (!payload.ref && !payload.formula)) return `<span class="${cls || ''}">${text}</span>`;
    const id = 'e' + (++ev.n);
    ev.reg.set(id, payload);
    return `<button type="button" class="ev ${cls || ''}" data-ev="${id}" title="Where this figure comes from">${text}</button>`;
  }
  function evRefHTML(ref) {
    const S = (ev.c && ev.c.quality && ev.c.quality.src) || { concepts: [], filings: [] };
    if (!ref) return '<p class="muted">No XBRL fact behind this figure.</p>';
    const [ci, how, fis, day] = ref, [concept, label] = S.concepts[ci] || ['?', ''];
    const cik = ev.c.profile.cik;
    const files = (fis || []).map((i) => S.filings[i]).filter(Boolean);
    return `<dl class="ev-dl"><dt>XBRL concept</dt><dd><span class="mono">us-gaap:${t(concept)}</span>${label && label !== concept ? `<br><span class="muted">${t(label)}</span>` : ''}</dd>
      <dt>How it was read</dt><dd>${t(HOW[how] || how)}${day ? ` ${date(day)}.` : ''}</dd>
      <dt>${files.length > 1 ? 'Filings' : 'Filing'}</dt><dd>${files.length ? files.map(([accn, form, filed]) => `<a href="https://www.sec.gov/Archives/edgar/data/${cik}/${String(accn).replace(/-/g, '')}/${t(accn)}-index.htm" target="_blank" rel="noopener">${t(form || 'Filing')} filed ${date(filed)} ↗</a> <span class="mono muted">${t(accn)}</span>`).join('<br>') : '—'}</dd></dl>`;
  }
  function evOpen(payload, opener) {
    let d = $('#ev-drawer');
    if (!d) {
      d = document.createElement('aside');
      d.id = 'ev-drawer';
      d.className = 'ev-drawer';
      d.setAttribute('role', 'dialog');
      d.setAttribute('aria-labelledby', 'ev-title');
      document.body.appendChild(d);
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && d.classList.contains('open')) evClose(); });
    }
    const kind = payload.kind || (payload.formula ? 'Derived' : 'Reported');
    d.innerHTML = `<div class="ev-head"><div><span class="eyebrow">${t(kind)}</span><h2 id="ev-title">${t(payload.title)}</h2>
        <p class="ev-val">${payload.value}${payload.period ? ` <span class="muted">· ${t(payload.period)}</span>` : ''}</p></div>
        <button type="button" class="btn small" id="ev-close" aria-label="Close">✕</button></div>
      ${payload.formula ? `<p class="ev-formula">${payload.formula}</p>` : ''}
      ${payload.note ? `<p class="muted">${payload.note}</p>` : ''}
      ${payload.ref ? evRefHTML(payload.ref) : ''}
      ${(payload.inputs || []).length ? `<h3>Inputs</h3>${payload.inputs.map((x) => `<div class="ev-input"><p><b>${t(x.title)}</b> ${x.value}${x.period ? ` <span class="muted">· ${t(x.period)}</span>` : ''}</p>${x.ref ? evRefHTML(x.ref) : `<p class="muted">${t(x.note || 'Not reported for this period.')}</p>`}</div>`).join('')}` : ''}`;
    d.classList.add('open');
    d._opener = opener;
    $('#ev-close', d).addEventListener('click', evClose);
    $('#ev-close', d).focus();
  }
  function evClose() {
    const d = $('#ev-drawer');
    if (!d) return;
    d.classList.remove('open');
    if (d._opener && d._opener.isConnected) d._opener.focus();
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-ev]');
    if (b && ev.reg.has(b.dataset.ev)) { e.preventDefault(); evOpen(ev.reg.get(b.dataset.ev), b); }
  });
  window.addEventListener('hashchange', evClose);

  // ---------- Cash & quality: net income → operating cash flow, and the cash conversion cycle ----------
  const BRIDGE = { da: 'Depreciation and amortization', sbc: 'Share-based compensation', dtax: 'Deferred income taxes',
    impair: 'Impairments', gain_inv: 'Gains on investments', gain_dis: 'Gains on disposals', other_nc: 'Other non-cash items',
    d_ar: 'Receivables', d_inv: 'Inventories', d_ap: 'Payables', d_accr: 'Accrued liabilities', d_emp: 'Employee-related liabilities',
    d_contract: 'Deferred revenue', d_casset: 'Contract assets', d_oassets: 'Prepaid and other assets', d_oliab: 'Other liabilities',
    d_tax: 'Income taxes payable', d_onet: 'Other operating capital' };
  const WC_KEYS = new Set(Object.keys(BRIDGE).filter((k) => k.startsWith('d_')));
  const days = (v) => (v == null ? '—' : `${Math.round(v)}`);

  function cashSection(body, c) {
    const D = c.quality, P = c.profile || {};
    const box = document.createElement('section');
    box.className = 'section cashq';
    box.setAttribute('aria-labelledby', 'cq-title');
    const financial = P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''));
    const st = { mode: (D.q || []).some((p) => p.bridge) ? 'q' : 'fy', end: null };
    const list = () => (st.mode === 'fy' ? D.fy : D.q).filter((p) => p.wc || p.bridge);
    if (!list().length && !(D.fy || []).some((p) => p.wc || p.bridge)) {
      box.innerHTML = `<div class="section-head"><h2 id="cq-title">Where the cash went</h2></div><p class="muted">Working capital and the cash-flow bridge are read on the next scans for this company.</p>`;
      body.appendChild(box);
      return;
    }
    if (!list().length) st.mode = 'fy';
    const ref = (p, k) => (p.ev || {})[k];
    const per = (p) => `${p.label}${st.mode === 'q' ? '' : ' (fiscal year)'}`;

    function bridgeHTML(p) {
      const b = p.bridge;
      if (!b) return `<p class="muted">${t(p.label)}: net income or operating cash flow is not tagged for this period.</p>`;
      const rows = [['Net income' + (b.basis === 'pl' ? ' (incl. noncontrolling interests)' : ''), b.start, 'base', b.ref && b.ref.start]];
      b.items.forEach(([k, v, r]) => rows.push([BRIDGE[k] || k, v, WC_KEYS.has(k) ? 'wc' : 'nc', r]));
      rows.push(['Not explained by the tags', b.residual, 'gap', null]);
      rows.push(['Operating cash flow', b.ocf, 'base', b.ref && b.ref.ocf]);
      let run = 0;
      const spans = rows.map(([, v, kind], i) => {
        if (kind === 'base') { const s = [0, v]; run = v; return s; }
        const s = [run, run + v]; run += v; return s;
      });
      const lo = Math.min(0, ...spans.flat()), hi = Math.max(0, ...spans.flat()), w = (hi - lo) || 1;
      const pos = (v) => ((v - lo) / w * 100).toFixed(2);
      const adj = b.items.reduce((s, x) => s + Math.abs(x[1]), 0);
      return `<div class="cq-bridge" role="table" aria-label="Net income to operating cash flow, ${t(p.label)}">${rows.map(([label, v, kind, r], i) => {
        const [a, z] = spans[i], left = pos(Math.min(a, z)), width = Math.max(0.4, Math.abs(pos(z) - pos(a))).toFixed(2);
        const pay = { title: label, value: money(v), period: per(p), ref: r, kind: kind === 'gap' ? 'Derived' : 'Reported',
          ...(kind === 'gap' ? { formula: `operating cash flow ${money(b.ocf)} − (net income ${money(b.start)} + tagged adjustments ${money(b.items.reduce((s, x) => s + x[1], 0))})`,
            note: 'Adjustments the company reports under its own (extension) tags, or combines with others, land here. Nothing is filled in to make the bridge balance.' } : {}),
          ...(kind !== 'base' && kind !== 'gap' ? { note: v < 0 ? 'Subtracted from net income: it lowered operating cash flow.' : 'Added to net income: it raised operating cash flow.' } : {}) };
        return `<div class="cq-row ${kind}" role="row"><span role="rowheader">${t(label)}</span>
          <span class="cq-track" role="cell"><i class="cq-bar ${kind}${kind === 'nc' || kind === 'wc' ? (v < 0 ? ' minus' : ' plus') : ''}" style="left:${left}%;width:${width}%"></i>${kind === 'base' ? '' : `<i class="cq-zero" style="left:${pos(0)}%"></i>`}</span>
          <span class="num" role="cell">${evBtn((kind === 'base' ? '' : v > 0 ? '+' : '') + money(v), pay)}</span></div>`;
      }).join('')}</div>
      <p class="q-sum">${t(p.label)}: the tagged adjustments move ${money(b.start)} of net income to ${money(b.start + b.items.reduce((s, x) => s + x[1], 0))}; the company reports ${money(b.ocf)} of operating cash flow.
        ${Math.abs(b.residual) <= 0.01 * Math.max(Math.abs(b.ocf), 1) ? '<span class="pos">The tags explain it fully.</span>' : `${money(Math.abs(b.residual))} is not explained by the standard tags (${adj ? Math.round(Math.abs(b.residual) / (adj + Math.abs(b.residual)) * 100) : 100}% of all adjustments), shown dashed.`}</p>`;
    }
    function daysChart(L, key, label, sel, note) {
      const vals = L.map((p) => (p.wc || {})[key]);
      const W = 300, H = 150, left = 34, top = 16, bottom = 24;
      const ax = qAxis(vals.filter((v) => v != null), H, top, bottom);
      const step = (W - left - 4) / L.length, bw = Math.min(22, step * 0.6);
      let g = ax.ticks.map((v) => `<line class="${v === 0 ? 'q-zero' : 'q-gl'}" x1="${left}" x2="${W - 2}" y1="${ax.y(v).toFixed(1)}" y2="${ax.y(v).toFixed(1)}"/><text class="q-tick" x="${left - 4}" y="${(ax.y(v) + 4).toFixed(1)}" text-anchor="end">${Math.round(v)}</text>`).join('');
      L.forEach((p, i) => {
        const x = left + i * step + (step - bw) / 2, v = vals[i];
        if (v != null) g += qRect(x, ax.y(0), ax.y(v), bw, `cq-d ${key}${p === sel ? ' on' : ''}`, `${p.label}: ${Math.round(v)} days`);
        else g += `<text class="q-na" x="${(x + bw / 2).toFixed(1)}" y="${(ax.y(0) - 4).toFixed(1)}" text-anchor="middle">–</text>`;
        if (i === 0 || i === Math.floor((L.length - 1) / 2) || i === L.length - 1)
          g += `<text class="q-x${p === sel ? ' on' : ''}" x="${(x + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${t(p.label.replace(/^FY/, ''))}</text>`;
      });
      const v = (sel.wc || {})[key];
      return `<article class="q-card cq-days"><div class="cq-days-head"><h3>${label}</h3><strong>${days(v)}<small> days</small></strong></div>
        <svg class="q-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${label} by period">${g}</svg>${note ? `<p class="muted q-small">${note}</p>` : ''}</article>`;
    }
    function dayPayload(p, key) {
      const w = p.wc || {}, R = (k) => ref(p, k);
      const inp = (title, v, k) => ({ title, value: money(v), period: per(p), ref: R(k), note: v == null ? 'Not tagged for this date.' : '' });
      const base = { title: { dso: 'Days sales outstanding', dio: 'Days inventory outstanding', dpo: 'Days payables outstanding', ccc: 'Cash conversion cycle' }[key],
        value: `${days(w[key])} days`, period: per(p), kind: 'Derived' };
      if (key === 'dso') return { ...base, formula: `average receivables (${money(w.ar_o)} + ${money(w.ar_c)}) ÷ 2 ÷ revenue ${money(w.rev)} × ${w.days} days`,
        note: 'Total revenue stands in for credit sales (a proxy).', inputs: [inp('Receivables, opening', w.ar_o, 'ar_o'), inp('Receivables, closing', w.ar_c, 'ar_c'), inp('Revenue', w.rev, 'rev')] };
      if (key === 'dio') return { ...base, formula: `average inventory (${money(w.inv_o)} + ${money(w.inv_c)}) ÷ 2 ÷ cost of revenue ${money(w.cor)} × ${w.days} days`,
        inputs: [inp('Inventory, opening', w.inv_o, 'inv_o'), inp('Inventory, closing', w.inv_c, 'inv_c'), inp('Cost of revenue', w.cor, 'cor')] };
      if (key === 'dpo') return { ...base, formula: `average payables (${money(w.ap_o)} + ${money(w.ap_c)}) ÷ 2 ÷ cost of revenue ${money(w.cor)} × ${w.days} days`,
        note: `Cost of revenue stands in for purchases (a proxy).${w.ap_proxy ? ' Payables include accrued liabilities: the company tags them together.' : ''}`,
        inputs: [inp('Payables, opening', w.ap_o, 'ap_o'), inp('Payables, closing', w.ap_c, 'ap_c'), inp('Cost of revenue', w.cor, 'cor')] };
      return { ...base, formula: `DSO ${days(w.dso)} + DIO ${w.has_inv ? days(w.dio) : '0 (no inventory reported)'} − DPO ${days(w.dpo)}`,
        inputs: [dayPayload(p, 'dso'), dayPayload(p, 'dio'), dayPayload(p, 'dpo')].map((x) => ({ ...x, ref: null, note: x.formula })) };
    }
    function tableHTML(L) {
      const cell = (p, k, v) => evBtn(money(v), { title: { rev: 'Revenue', cor: 'Cost of revenue', ar_c: 'Receivables', inv_c: 'Inventory', ap_c: 'Payables' }[k], value: money(v), period: per(p), ref: ref(p, k) });
      return `<div class="tbl-wrap"><table class="cq-table"><thead><tr><th>Period</th><th class="num">Revenue</th><th class="num">Cost of revenue</th><th class="num">Receivables</th><th class="num">Inventory</th><th class="num">Payables</th>
        <th class="num">DSO</th><th class="num">DIO</th><th class="num">DPO</th><th class="num">CCC</th></tr></thead><tbody>${L.slice().reverse().map((p) => {
          const w = p.wc || {};
          return `<tr><td>${t(p.label)}</td><td class="num">${cell(p, 'rev', w.rev)}</td><td class="num">${cell(p, 'cor', w.cor)}</td><td class="num">${cell(p, 'ar_c', w.ar_c)}</td>
            <td class="num">${w.has_inv ? cell(p, 'inv_c', w.inv_c) : '<span class="muted">none</span>'}</td><td class="num">${cell(p, 'ap_c', w.ap_c)}${w.ap_proxy ? '<sup>*</sup>' : ''}</td>
            ${['dso', 'dio', 'dpo', 'ccc'].map((k) => `<td class="num">${w[k] == null ? '—' : evBtn(days(w[k]), dayPayload(p, k))}</td>`).join('')}</tr>`;
        }).join('')}</tbody></table></div>
        <p class="muted q-small">Balances at period end; days use the average of the opening and closing balance and need both. ${L.some((p) => (p.wc || {}).ap_proxy) ? '* Payables tagged together with accrued liabilities. ' : ''}Select any figure to see the XBRL fact and filing it comes from.</p>`;
    }
    // ---- cash collected from customers against revenue (web/fsa.js FSA.collections): an estimate from the same tags
    const conceptOf = (r) => { const x = r && D.src && D.src.concepts[r[0]]; return x ? x[0] : ''; };
    const CL_PART = { d_ar: ['receivables rose', 'receivables fell'], d_casset: ['contract assets rose', 'contract assets fell'],
      d_contract: ['deferred revenue fell', 'deferred revenue rose'] };     // [cash effect < 0, cash effect > 0]
    const rate = (r) => `${Math.round(r * 100)}%`;
    function clPayload(p, x) {
      return { title: 'Cash collected from customers (estimate)', value: money(x.cash), period: per(p), kind: 'Derived',
        formula: `revenue ${money(x.rev)}${x.parts.map(([k, v]) => ` ${v < 0 ? '−' : '+'} ${money(Math.abs(v))} (${CL_PART[k][v < 0 ? 0 : 1]})`).join('')}`,
        note: 'The cash-flow statement’s changes in receivables, contract assets and deferred revenue, applied to revenue. Bad-debt write-offs, '
          + 'sold receivables and balances from acquisitions are not separated, so this is an estimate.'
          + (x.broad ? ' The company tags receivables together with other operating assets, which widens the estimate.' : ''),
        inputs: [{ title: 'Revenue', value: money(x.rev), period: per(p), ref: ref(p, 'rev') }]
          .concat(x.parts.map(([k, v, r]) => ({ title: `${BRIDGE[k]} (cash effect)`, value: money(v), period: per(p), ref: r }))) };
    }
    function collectChart(L, sel) {
      const xs = L.map((p) => FSA.collections(p, conceptOf));
      const W = 560, H = 230, left = 58, top = 22, bottom = 30;
      const ax = qAxis(xs.flatMap((x) => (x ? [x.rev, x.cash] : [])), H, top, bottom);
      const step = (W - left - 8) / L.length, bw = Math.min(22, step * 0.32);
      let g = qGrid(ax, W, left);
      L.forEach((p, i) => {
        const x = left + i * step, mid = x + step / 2, c = xs[i];
        if (p === sel) g += `<rect class="q-selcol" x="${(x + 2).toFixed(1)}" y="${top - 14}" width="${(step - 4).toFixed(1)}" height="${H - top - bottom + 18}" rx="6"/>`;
        if (c) {
          g += qRect(mid - bw - 1, ax.y(0), ax.y(c.rev), bw, 'cq-rev', `${p.label} revenue ${money(c.rev)}`);
          g += qRect(mid + 1, ax.y(0), ax.y(c.cash), bw, 'cq-col', `${p.label} cash collected (estimate) ${money(c.cash)}, ${rate(c.rate)} of revenue`);
          g += `<text class="q-val${c.rate < 0.9 ? ' cq-low' : ''}" x="${mid.toFixed(1)}" y="${(Math.min(ax.y(c.rev), ax.y(c.cash)) - 5).toFixed(1)}" text-anchor="middle">${rate(c.rate)}</text>`;
        } else g += `<text class="q-na" x="${mid.toFixed(1)}" y="${(ax.y(0) - 6).toFixed(1)}" text-anchor="middle">n/a</text>`;
        g += `<text class="q-x${p === sel ? ' on' : ''}" x="${mid.toFixed(1)}" y="${H - 10}" text-anchor="middle">${t(p.label)}</text>
          <rect class="q-hit" data-end="${t(p.end)}" x="${x.toFixed(1)}" y="0" width="${step.toFixed(1)}" height="${H}"><title>${t(p.label)}: select</title></rect>`;
      });
      return `<svg class="q-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue and estimated cash collected from customers by period">${g}</svg>`;
    }
    function collectHTML(L, sel) {
      if (financial || !L.some((p) => FSA.collections(p, conceptOf))) return '';
      const x = FSA.collections(sel, conceptOf);
      const last4 = st.mode === 'q' ? (D.q || []).filter((p) => p.end <= sel.end).slice(-4) : [];
      const y = last4.length === 4 ? FSA.collectionsSum(last4, conceptOf) : null;
      const kp = (label, val, note, cls) => `<div class="q-kpi"><small>${label}</small><strong class="${cls || ''}">${val}</strong>${note ? `<span>${note}</span>` : ''}</div>`;
      const said = !x ? `${t(sel.label)}: the change in receivables is not tagged for this period, so collections cannot be estimated.`
        : `${t(sel.label)}: revenue ${money(x.rev)}; an estimated ${money(x.cash)} came in from customers, ${rate(x.rate)} of revenue`
          + (x.parts.length ? ` (${x.parts.map(([k, v]) => `${CL_PART[k][v < 0 ? 0 : 1]} ${money(Math.abs(v))}`).join(', ')})` : '') + '. '
          + (x.rate < 0.9 ? '<span class="q-warmtext">More revenue was booked than collected: worth reading the receivables note and the customer concentration.</span>'
            : x.rate > 1.05 ? 'Customers paid more than the revenue booked: receivables shrank or payments came in ahead of revenue.'
              : 'Collections kept pace with revenue.');
      return `<article class="q-card cq-collect"><h3>Cash collected vs revenue, ${t(sel.label)}</h3>
          <p class="muted">Revenue is booked when it is earned; cash arrives when customers pay. Collected ≈ revenue − the rise in receivables and contract assets + the rise in deferred revenue.</p>
          <div class="q-kpis cq-kpis">
            ${kp('Revenue', x ? evBtn(money(x.rev), { title: 'Revenue', value: money(x.rev), period: per(sel), ref: ref(sel, 'rev') }) : '—', '')}
            ${kp('Cash collected', x ? evBtn(money(x.cash), clPayload(sel, x)) : '—', 'estimate')}
            ${kp('Collected ÷ revenue', x ? rate(x.rate) : '—', x ? (x.gap < 0 ? `${money(-x.gap)} not yet collected` : `${money(x.gap)} more than revenue`) : '', x && x.rate < 0.9 ? 'q-warm' : '')}
            ${st.mode === 'q' ? kp('Last four quarters', y ? rate(y.rate) : '—', y ? `${money(y.cash)} of ${money(y.rev)}` : 'needs four tagged quarters', y && y.rate < 0.9 ? 'q-warm' : '') : ''}
          </div>
          <div class="q-scroll">${collectChart(L, sel)}</div>
          <div class="q-legend"><span><i class="cq-rev"></i>Revenue</span><span><i class="cq-col"></i>Cash collected (estimate)</span><span>% = collected ÷ revenue</span></div>
          <p class="q-sum">${said}</p>
          <p class="muted q-small">Seasonal businesses swing quarter to quarter; the last four quarters smooth that out.${x && x.broad ? ' Receivables are tagged together with other operating assets here, so the estimate is broader.' : ''} Select a figure to see the facts behind it.</p>
        </article>`;
    }
    function render() {
      const L = list().slice(st.mode === 'fy' ? -5 : -8);
      const sel = L.find((p) => p.end === st.end) || L[L.length - 1];
      const w = sel.wc || {};
      box.innerHTML = `<div class="section-head"><h2 id="cq-title">Where the cash went</h2>
          <span class="muted">From net income to operating cash flow, and how long cash sits in receivables and inventory · the cash-flow statement and balance sheet, XBRL</span></div>
        <div class="q-bar"><div class="seg" role="group" aria-label="Period type">
            <button type="button" data-cm="q" class="${st.mode === 'q' ? 'on' : ''}" ${(D.q || []).some((p) => p.wc || p.bridge) ? '' : 'disabled'}>Quarters</button>
            <button type="button" data-cm="fy" class="${st.mode === 'fy' ? 'on' : ''}" ${(D.fy || []).some((p) => p.wc || p.bridge) ? '' : 'disabled'}>Fiscal years</button></div>
          <label class="q-pick">Period <select id="cq-period">${L.map((p) => `<option value="${t(p.end)}" ${p === sel ? 'selected' : ''}>${t(p.label)}</option>`).join('')}</select></label></div>
        ${financial ? '<p class="q-warn">For banks, insurers and brokers, operating cash flow includes lending, deposit and trading flows, and receivables, inventory and payables do not describe the business: read these figures with care.</p>' : ''}
        <article class="q-card"><h3>Net income → operating cash flow, ${t(sel.label)}</h3>
          <p class="muted">The adjustments the cash-flow statement discloses, in its order. A dashed bar is what the standard tags do not explain.</p>
          ${bridgeHTML(sel)}
          <div class="q-legend"><span><i class="cq-bar plus nc"></i>Non-cash charges and gains</span><span><i class="cq-bar plus wc"></i>Working capital</span><span><i class="cq-gap-key"></i>Not explained</span></div></article>
        ${collectHTML(L, sel)}
        <h3 class="cq-h3">Cash conversion cycle</h3>
        <div class="cq-grid">
          ${daysChart(L, 'dso', 'Receivables (DSO)', sel, 'Days of revenue not yet collected. Total revenue is a proxy for credit sales.')}
          ${daysChart(L, 'dio', 'Inventory (DIO)', sel, w.has_inv === false ? 'No inventory reported.' : 'Days of cost of revenue held as inventory.')}
          ${daysChart(L, 'dpo', 'Payables (DPO)', sel, 'Days of cost of revenue not yet paid. Cost of revenue is a proxy for purchases.')}
          ${daysChart(L, 'ccc', 'Cash cycle (CCC)', sel, 'DSO + DIO − DPO: days between paying suppliers and collecting from customers.')}
        </div>
        ${tableHTML(L)}`;
      $$('[data-cm]', box).forEach((b) => b.addEventListener('click', () => { st.mode = b.dataset.cm; st.end = null; render(); }));
      const ps = $('#cq-period', box);
      if (ps) ps.addEventListener('change', () => { st.end = ps.value; render(); });
      $$('.cq-collect .q-hit', box).forEach((h) => h.addEventListener('click', () => { st.end = h.dataset.end; render(); }));
      $$('.cq-collect .q-scroll', box).forEach((el) => { el.scrollLeft = el.scrollWidth; });   // phones: the latest period
    }
    render();
    body.appendChild(box);
    $$('.cq-collect .q-scroll', box).forEach((el) => { el.scrollLeft = el.scrollWidth; });     // now that it has a width
  }

  // ---------- Capital allocation: where the cash came from and went, the share count, debt maturities ----------
  // Figures from pipeline/capital.py: items are cash effects (+ in, − out); ev[key] = [[cash effect, ref], ...].
  const CAP = {
    ocf: ['Operating cash flow', 'Operating cash outflow'], borrow: ['Net borrowing', 'Debt repaid, net'],
    stock: ['Shares issued', 'Shares issued'], sales: ['Asset and business sales', 'Asset and business sales'],
    nci: ['From partners in subsidiaries', 'To partners in subsidiaries'], inv_other: ['Other investing, net', 'Other investing, net'],
    fin_other: ['Other financing, net', 'Other financing, net'], fx: ['Exchange-rate effect', 'Exchange-rate effect'],
    unrec: ['Not reconciled', 'Not reconciled'], cash: ['Drawn from cash on hand', 'Added to cash'],
    capex: ['Capital expenditures', 'Capital expenditures'], realestate: ['Real estate bought', 'Real estate bought'],
    acq: ['Acquisitions', 'Acquisitions'], buyback: ['Share buybacks', 'Share buybacks'], div: ['Dividends', 'Dividends'],
    withhold: ['Taxes paid on employee shares', 'Taxes paid on employee shares'],
  };
  const capName = (k, v) => (CAP[k] || [k, k])[v >= 0 ? 0 : 1];
  const CAP_ROW_NAME = { ocf: 'Operating cash flow', capex: 'Capital expenditures', realestate: 'Real estate bought', acq: 'Acquisitions',
    sales: 'Asset and business sales', inv_other: 'Other investing, net', buyback: 'Share buybacks', div: 'Dividends',
    withhold: 'Taxes paid on employee shares', stock: 'Shares issued', borrow: 'Borrowing, net of repayments', nci: 'Partners in subsidiaries, net',
    fin_other: 'Other financing, net', fx: 'Exchange-rate effect', unrec: 'Not reconciled', cash: 'Change in cash' };
  const CAP_ROWS = ['ocf', 'capex', 'realestate', 'acq', 'sales', 'inv_other', 'buyback', 'div', 'withhold', 'stock', 'borrow', 'nci', 'fin_other', 'fx', 'unrec', 'cash'];
  const CAP_SRC = ['ocf', 'borrow', 'stock', 'sales', 'nci', 'inv_other', 'fin_other', 'fx', 'unrec', 'cash'];
  const CAP_GROUPS = [['burn', null, ['ocf']], ['reinvest', 'Reinvested in the business', ['capex', 'realestate', 'acq']],
    ['returned', 'Returned to shareholders', ['buyback', 'div']], ['debt', null, ['borrow']],
    ['other', 'Other uses', ['withhold', 'nci', 'stock', 'sales', 'inv_other', 'fin_other', 'fx', 'unrec']]];
  const capShare = (v, tot) => { const s = tot ? Math.abs(v) / tot * 100 : 0; return `${s < 10 ? s.toFixed(1) : Math.round(s)}%`; };
  const fmtShares = (v) => (v == null ? '—' : v >= 0.95e9 ? `${(v / 1e9).toFixed(2)}B` : `${(v / 1e6).toFixed(1)}M`);

  function capitalSection(body, c, ticker) {
    const D = c.quality, K = D.cap, P = c.profile || {};
    const box = document.createElement('section');
    box.className = 'section capital';
    box.setAttribute('aria-labelledby', 'ca-title');
    const name = S.dec(P.name || '');
    if (!K || !((K.fy || []).length || (K.q || []).length || K.ttm || (K.shares || []).length || K.maturities)) {
      box.innerHTML = `<div class="section-head"><h2 id="ca-title">Capital allocation</h2></div><p class="muted">Capital allocation is read on the next scans for this company: a few dozen companies a run, largest first.</p>`;
      body.appendChild(box);
      return;
    }
    const financial = P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''));
    const yearly = (K.fy || []).concat(K.ttm ? [K.ttm] : []), quarterly = K.q || [];
    const periods = yearly.concat(quarterly);
    const st = { end: ((K.fy || []).length ? K.fy[K.fy.length - 1] : K.ttm || {}).end, scene: null };
    const table = { rows: yearly };                    // the table shows the kind of period picked: years or quarters
    const S0 = D.src || { concepts: [] };
    const per = (p) => `${p.label}${p.kind === 'ttm' ? ' (trailing twelve months)' : p.kind === 'q' ? ' (quarter)' : ' (fiscal year)'}`;
    const yearAgo = (p) => quarterly.find((x) => Math.abs((new Date(p.end) - new Date(x.end)) / 864e5 - 365) <= 12);
    const prevOf = (p) => (p.kind === 'fy' ? (K.fy || [])[(K.fy || []).indexOf(p) - 1]     // a quarter: the same quarter a
      : p.kind === 'q' ? yearAgo(p) || quarterly[quarterly.indexOf(p) - 1] : null);       // year earlier, else the one before
    const chgTag = (p, prev) => (p.kind === 'q' && prev && !yearAgo(p) ? (p.period === 'half' ? 'H/H' : 'Q/Q') : 'Y/Y');
    const label = (ref) => { const x = S0.concepts[ref[0]]; return x ? S.dec(x[1] || x[0]) : 'XBRL fact'; };

    // ---- the evidence for one line
    function partsPayload(p, k, parts, title) {
      if (parts.length === 1) return { title, value: money(parts[0][0]), period: per(p), ref: parts[0][1] };
      return { title, value: money(parts.reduce((s, x) => s + x[0], 0)), period: per(p), kind: 'Reported',
        formula: parts.map(([v]) => money(v)).join(' + ').replace(/\+ −/g, '− '),
        inputs: parts.map(([v, r]) => ({ title: label(r), value: money(v), period: per(p), ref: r })) };
    }
    function capPayload(p, k) {
      const it = p.items, v = it[k], ev1 = (key) => ((p.ev || {})[key] || [])[0];
      const title = capName(k, v);
      const total = (key, t2) => { const e = ev1(key); return { title: t2, value: money(e ? e[0] : null), period: per(p), ref: e && e[1] }; };
      if (k === 'inv_other' || k === 'fin_other') {
        const inv = k === 'inv_other', tot = inv ? p.inv : p.fin;
        const keys = (inv ? ['capex', 'realestate', 'acq', 'sales'] : ['buyback', 'div', 'withhold', 'stock', 'borrow', 'nci']).filter((x) => it[x] != null);
        return { title, value: money(v), period: per(p), kind: 'Derived',
          formula: `${inv ? 'investing' : 'financing'} cash flow ${money(tot)} − the lines shown ${money(keys.reduce((s, x) => s + it[x], 0))}`,
          note: inv ? 'Everything else in the investing section: usually purchases and sales of securities, and lines the company reports under tags of its own.'
            : 'Everything else in the financing section: lines the company reports under tags of its own or that are not split out here (for banks, deposits).',
          inputs: [total(inv ? 'inv' : 'fin', `Net cash from ${inv ? 'investing' : 'financing'} activities`)]
            .concat(keys.map((x) => ({ ...capPayload(p, x), note: 'A line shown separately.' }))) };
      }
      if (k === 'unrec') {
        return { title, value: money(v), period: per(p), kind: 'Derived',
          formula: `change in cash ${money(p.dcash)} − (operating ${money(it.ocf)} + investing ${money(p.inv)} + financing ${money(p.fin)}${it.fx != null ? ` + exchange rate ${money(it.fx)}` : ''})`,
          note: 'Usually cash flows of discontinued operations, reported outside the three sections. A large figure can also mean a tagging error in the filing: check the cash-flow statement.',
          inputs: [total('dcash', 'Change in cash and equivalents'), total('ocf', 'Operating cash flow'), total('inv', 'Investing cash flow'), total('fin', 'Financing cash flow')]
            .concat(it.fx != null ? [total('fx', 'Exchange-rate effect')] : []) };
      }
      if (k === 'cash') {
        const parts = (p.ev || {}).dcash || [];
        if (!parts.length) return { title, value: money(-v), period: per(p), kind: 'Derived', formula: 'operating + investing + financing cash flow + exchange-rate effect',
          note: 'The change in cash is not tagged for this period: it is what the sections add up to.' };
        return { ...partsPayload(p, k, parts, 'Change in cash and equivalents'), title,
          note: v > 0 ? 'Cash, cash equivalents and restricted cash fell by this much: the uses were larger than the inflows.' : 'Cash, cash equivalents and restricted cash grew by this much.' };
      }
      const parts = (p.ev || {})[k] || [];
      if (!parts.length) return { title, value: money(v), period: per(p), kind: 'Reported' };
      const pay = partsPayload(p, k, parts, title);
      const notes = [];
      if (k === 'borrow') {
        notes.push('Debt is shown net: everything borrowed minus everything repaid (positive figures are borrowing, negative repayments).');
        if (p.debt && p.debt.fit) notes.push('The company tags its cash-flow lines and their breakdown from the notes: the combination of debt tags that, with the other lines, adds up to the financing total is used.');
        if (p.debt && p.debt.withhold_inside) notes.push(`Taxes paid on employee shares (${money(p.debt.withhold_inside)}) are part of another line here, so they are not counted again.`);
      }
      if (k === 'capex' && parts.length === 1) notes.push('Payments for property, plant and equipment as tagged; where several capital-expenditure tags exist, the largest.');
      if (k === 'withhold') notes.push('Cash paid to tax authorities for employees instead of issuing them all their vested shares: it reduces the share count like a buyback.');
      if (k === 'nci') notes.push('Money from or to minority partners in subsidiaries (noncontrolling interests).');
      if (k === 'fx') notes.push('The change in the dollar value of cash held in other currencies.');
      return notes.length ? { ...pay, note: notes.join(' ') } : pay;
    }

    // ---- the Sankey: sources → cash to allocate → uses
    function spec(p) {
      const it = p.items, prev = prevOf(p);
      const total = Object.values(it).filter((v) => v > 0).reduce((s, v) => s + v, 0);
      const small = total * 0.012, nodes = [], links = [], pay = new Map();
      const yoy = (k, v) => {
        if (!prev) return null;
        const pv = (prev.items || {})[k];
        if (pv == null) return `none in ${prev.label}`;
        const tag = chgTag(p, prev);
        if (Math.sign(pv) !== Math.sign(v)) return `${tag} n/m · ${prev.label}: ${capName(k, pv).toLowerCase()} ${money(Math.abs(pv))}`;
        return `${tag} ${pct((Math.abs(v) / Math.abs(pv) - 1) * 100)}`;
      };
      const node = (id, col, color, nm, v, posn, k, payload) => {
        const lines = [['name', nm], ['val', `${money(Math.abs(v))} · ${capShare(v, total)} of the total`]];
        const y = k ? yoy(k, v) : null;
        if (y) lines.push(['mut', y]);
        nodes.push({ id, col, color, name: nm, pos: posn, v: Math.abs(v), lines });
        if (payload) pay.set(id, payload);
      };
      node('pool', 1, 'rev', 'Cash to allocate', total, 'above', null, { title: 'Cash to allocate', value: money(total), period: per(p), kind: 'Derived',
        formula: 'the inflows on the left = the uses on the right',
        note: 'Operating cash flow and every other inflow of the period, with cash drawn from the balance sheet when cash fell. Every band is cash; nothing is estimated.' });
      // sources
      let other = 0; const otherKeys = [];
      CAP_SRC.forEach((k) => {
        const v = it[k];
        if (!(v > 0)) return;
        if (v < small && k !== 'ocf') { other += v; otherKeys.push(k); return; }
        node('s_' + k, 0, k === 'ocf' ? 'profit' : 'noncash', capName(k, v), v, 'left', k, capPayload(p, k));
        links.push({ s: 's_' + k, t: 'pool', v, color: k === 'ocf' ? 'profit' : 'noncash' });
      });
      if (other > 0) {
        node('s_small', 0, 'noncash', 'Other inflows', other, 'left', null, { title: 'Other inflows', value: money(other), period: per(p), kind: 'Derived',
          formula: otherKeys.map((k) => `${capName(k, it[k])} ${money(it[k])}`).join(' + '), inputs: otherKeys.map((k) => capPayload(p, k)) });
        links.push({ s: 's_small', t: 'pool', v: other, color: 'noncash' });
      }
      // uses, grouped
      CAP_GROUPS.forEach(([g, gname, keys]) => {
        let leaves = keys.filter((k) => it[k] < 0).map((k) => [k, -it[k]]);
        if (g === 'other') {                                   // the small ones in one leaf
          const tiny = leaves.filter(([, v]) => v < small);
          leaves = leaves.filter(([, v]) => v >= small);
          if (tiny.length) leaves.push(['_tiny', tiny.reduce((s, [, v]) => s + v, 0), tiny]);
        }
        if (!leaves.length) return;
        const sum = leaves.reduce((s, [, v]) => s + v, 0);
        const leafPay = (k, v, tiny) => (k === '_tiny' ? { title: 'Smaller items', value: money(-v), period: per(p), kind: 'Derived',
          formula: tiny.map(([x, w]) => `${capName(x, -w)} ${money(-w)}`).join(' + '), inputs: tiny.map(([x]) => capPayload(p, x)) } : capPayload(p, k));
        const leafName = (k, v) => (k === '_tiny' ? 'Smaller items' : capName(k, -v));
        if (leaves.length === 1 || !gname) {
          leaves.forEach(([k, v, tiny]) => {
            node('u_' + k, 2, 'cost', leafName(k, v), -v, 'right', k === '_tiny' ? null : k, leafPay(k, v, tiny));
            links.push({ s: 'pool', t: 'u_' + k, v, color: 'cost' });
          });
          return;
        }
        node('g_' + g, 2, 'cost', gname, -sum, 'above', null, { title: gname, value: money(-sum), period: per(p), kind: 'Derived',
          formula: leaves.map(([k, v]) => `${leafName(k, v)} ${money(v)}`).join(' + '), inputs: leaves.map(([k, v, tiny]) => leafPay(k, v, tiny)) });
        links.push({ s: 'pool', t: 'g_' + g, v: sum, color: 'cost' });
        leaves.forEach(([k, v, tiny]) => {
          node('u_' + k, 3, 'cost', leafName(k, v), -v, 'right', k === '_tiny' ? null : k, leafPay(k, v, tiny));
          links.push({ s: 'g_' + g, t: 'u_' + k, v, color: 'cost' });
        });
      });
      if (it.cash < 0) {
        node('u_kept', 2, 'profit', 'Added to cash', it.cash, 'right', 'cash', capPayload(p, 'cash'));
        links.push({ s: 'pool', t: 'u_kept', v: -it.cash, color: 'profit' });
      }
      const flags = p.flags || [];
      return { pay, spec: {
        title: `${name}: where the cash went, ${p.kind === 'ttm' ? p.label.replace(/^TTM to /, 'twelve months to ') : p.label}`,
        subtitle: 'Cash-flow statement as tagged in SEC filings (XBRL) · inflows on the left, uses on the right · debt shown net',
        nodes, links,
        legend: [['profit', 'Operating cash flow · cash kept'], ['noncash', 'Borrowing, shares issued, other inflows'], ['rev', 'Cash to allocate'], ['cost', 'Uses of cash']],
        checks: flags.includes('unrec') ? [{ level: 'warn', text: `${money(Math.abs(it.unrec || 0))} of the change in cash is not explained by the operating, investing and financing totals (discontinued operations or a tagging error): see “Not reconciled”.` }] : [],
        footer: [`${p.kind === 'ttm' ? 'Trailing twelve months: the last fiscal year + this year to date − the same period a year earlier. ' : ''}` +
          '“Other investing” and “Other financing” are each section’s reported total minus the lines shown; debt is net of repayments; ' +
          'lines under 1.2% of the total are combined. Shares: % of the cash to allocate.'],
      } };
    }

    // ---- the summary in words
    function sentence(p) {
      const it = p.items, g = (k) => -(it[k] || 0);
      const reinvest = ['capex', 'realestate', 'acq'].reduce((s, k) => s + Math.max(0, g(k)), 0);
      const returned = Math.max(0, g('buyback')) + Math.max(0, g('div'));
      const out = [];
      out.push(it.ocf >= 0 ? `In ${p.label}, ${t(name)} generated ${money(it.ocf)} of operating cash flow.` : `In ${p.label}, ${t(name)}’s operations used ${money(-it.ocf)} of cash.`);
      if (it.capex != null) out.push(`Free cash flow (operating cash flow − capital expenditures) was ${money(it.ocf + it.capex)}.`);
      const bits = [];
      if (reinvest > 0) bits.push(`spent ${money(reinvest)} on its business (${['capex', 'realestate', 'acq'].filter((k) => g(k) > 0).map((k) => `${capName(k, -1).toLowerCase()} ${money(g(k))}`).join(', ')})`);
      if (returned > 0) bits.push(`returned ${money(returned)} to shareholders${it.ocf > 0 ? ` (${Math.round(returned / it.ocf * 100)}% of operating cash flow)` : ''}`);
      if (it.borrow) bits.push(it.borrow > 0 ? `borrowed a net ${money(it.borrow)}` : `repaid a net ${money(-it.borrow)} of debt`);
      if (it.stock > 0 && it.stock >= 0.05 * Math.abs(it.ocf)) bits.push(`raised ${money(it.stock)} by issuing shares`);
      if (bits.length) out.push(`It ${listJoin(bits)}.`);
      if (it.cash) out.push(it.cash < 0 ? `Cash on hand rose by ${money(-it.cash)}.` : `Cash on hand fell by ${money(it.cash)}.`);
      return out.join(' ');
    }

    // ---- every period, line by line
    function tableHTML() {
      const periods = table.rows;
      const rows = CAP_ROWS.filter((k) => periods.some((p) => p.items[k] != null));
      const fcf = (p) => (p.items.capex != null ? p.items.ocf + p.items.capex : null);
      const cell = (p, k) => { const v = p.items[k]; return v == null ? '<span class="muted">—</span>' : evBtn(money(k === 'cash' ? -v : v), capPayload(p, k)); };
      return `<div class="tbl-wrap"><table class="ca-table"><thead><tr><th>Cash flow</th>${periods.map((p) => `<th class="num">${t(p.label)}</th>`).join('')}</tr></thead><tbody>
        ${rows.map((k) => `<tr class="${k === 'ocf' || k === 'cash' ? 'ca-strong' : ''}"><td>${CAP_ROW_NAME[k] || k}</td>
          ${periods.map((p) => `<td class="num">${cell(p, k)}</td>`).join('')}</tr>`).join('')}
        <tr class="ca-derived"><td>Free cash flow <span class="muted">(operating − capex)</span></td>${periods.map((p) => {
          const v = fcf(p);
          return `<td class="num">${v == null ? '<span class="muted">—</span>' : evBtn(money(v), { title: 'Free cash flow', value: money(v), period: per(p), kind: 'Derived',
            formula: `operating cash flow ${money(p.items.ocf)} − capital expenditures ${money(-p.items.capex)}`, inputs: [capPayload(p, 'ocf'), capPayload(p, 'capex')] })}</td>`;
        }).join('')}</tr></tbody></table></div>
        <p class="muted q-small">+ = cash in, − = cash out. “Change in cash” is the reported change in cash, cash equivalents and restricted cash. Select any figure to see the XBRL facts and filings behind it.</p>`;
    }

    // ---- share count: dilution against buybacks
    function sharesHTML() {
      const R = (K.shares || []).filter((r) => r.diluted || r.basic);
      if (R.length < 2) return '';
      const cnt = (r) => r.diluted || r.basic, key = R.every((r) => r.diluted) ? 'diluted' : 'basic';
      const chg = R.map((r, i) => (i && cnt(R[i - 1]) && !(r.split || []).includes(key) && cnt(r) ? (cnt(r) / cnt(R[i - 1]) - 1) * 100 : null));
      const W = 520, H = 170, left = 40, top = 22, bottom = 26;
      const vals = chg.slice(1).filter((v) => v != null);
      const ax = qAxis(vals.length ? vals : [0, 1], H, top, bottom);
      const L = R.slice(1), step = (W - left - 6) / L.length, bw = Math.min(46, step * 0.55);
      let g = ax.ticks.map((v) => `<line class="${v === 0 ? 'q-zero' : 'q-gl'}" x1="${left}" x2="${W - 4}" y1="${ax.y(v).toFixed(1)}" y2="${ax.y(v).toFixed(1)}"/><text class="q-tick" x="${left - 5}" y="${(ax.y(v) + 4).toFixed(1)}" text-anchor="end">${v > 0 ? '+' : ''}${+v.toFixed(1)}%</text>`).join('');
      L.forEach((r, i) => {
        const x = left + i * step + (step - bw) / 2, v = chg[i + 1];
        if (v == null) g += `<text class="q-na" x="${(x + bw / 2).toFixed(1)}" y="${(ax.y(0) - 6).toFixed(1)}" text-anchor="middle">${(r.split || []).length ? 'split?' : '–'}</text>`;
        else {
          g += qRect(x, ax.y(0), ax.y(v), bw, `ca-sh ${v > 0 ? 'up' : 'down'}`, `${r.label}: ${pct(v, 1)} ${key} shares`);
          g += `<text class="q-val" x="${(x + bw / 2).toFixed(1)}" y="${(v >= 0 ? ax.y(v) - 5 : ax.y(v) + 13).toFixed(1)}" text-anchor="middle">${pct(v, 1)}</text>`;
        }
        g += `<text class="q-x" x="${(x + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${t(r.label)}</text>`;
      });
      const first = R.find((r) => cnt(r)), last = R[R.length - 1];
      const splitIn = R.some((r) => (r.split || []).includes(key));
      const tot = !splitIn && first !== last ? (cnt(last) / cnt(first) - 1) * 100 : null;
      const sum = (k) => R.slice(1).reduce((s, r) => s + (r[k] || 0), 0);
      const shPay = (r, k, title) => (r[k] == null ? '<span class="muted">—</span>' : evBtn(k === 'diluted' || k === 'basic' || k === 'out' ? fmtShares(r[k]) : money(r[k]),
        { title, value: k === 'diluted' || k === 'basic' || k === 'out' ? fmtShares(r[k]) + ' shares' : money(r[k]), period: `${r.label} (fiscal year)`, ref: (r.ev || {})[k] }));
      return `<article class="q-card"><h3>Share count</h3>
        <p class="q-sum">${tot == null ? `${splitIn ? 'A stock split (or listing) breaks the comparison across these years. ' : ''}` :
          `From ${t(first.label)} to ${t(last.label)} the ${key} share count ${tot < 0 ? 'fell' : 'rose'} ${Math.abs(tot).toFixed(1)}% (${fmtShares(cnt(first))} → ${fmtShares(cnt(last))}). `}
          ${sum('bb') || sum('sbc') ? `Over ${R.length - 1} years ${t(name)} spent ${money(sum('bb'))} on buybacks${sum('wh') ? ` and ${money(sum('wh'))} on taxes for employee shares` : ''}, against ${money(sum('sbc'))} of share-based compensation expense.` : ''}</p>
        <div class="ca-scroll"><svg class="q-chart ca-shchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Change in ${key} weighted-average shares by fiscal year">${g}</svg></div>
        <div class="tbl-wrap"><table class="ca-table"><thead><tr><th>Year</th><th class="num" title="Weighted-average ${key} shares for the year">${key === 'diluted' ? 'Diluted' : 'Basic'}, avg.</th><th class="num" title="Shares outstanding on the balance sheet date">Year end</th><th class="num" title="Share-based compensation expense">SBC</th><th class="num">Buybacks</th><th class="num" title="Taxes paid for employees on vested shares">Employee taxes</th></tr></thead>
        <tbody>${R.slice().reverse().map((r) => `<tr><td>${t(r.label)}${(r.split || []).length ? ' <span class="muted" title="The count changed by more than 80% from the year before: a split or a listing">*</span>' : ''}</td>
          <td class="num">${shPay(r, key, `${key === 'diluted' ? 'Diluted' : 'Basic'} weighted-average shares`)}</td><td class="num">${shPay(r, 'out', 'Shares outstanding at year end')}</td>
          <td class="num">${shPay(r, 'sbc', 'Share-based compensation expense')}</td><td class="num">${shPay(r, 'bb', 'Share buybacks')}</td><td class="num">${shPay(r, 'wh', 'Taxes paid on employee shares')}</td></tr>`).join('')}</tbody></table></div>
        <p class="muted q-small">Weighted-average shares from the income statement; red = more shares (dilution), green = fewer. Each 10-K restates its comparative years for a split; older years can still be on the old basis (*).</p></article>`;
    }

    // ---- when the long-term debt falls due
    function maturitiesHTML() {
      const m = K.maturities;
      if (!m) return '';
      const cal = /^FY\d{4}$/.test(m.label);
      const yl = (b) => (b === 6 ? 'Later' : cal ? `FY${m.fy + b}` : `FY${String(m.fy + b).slice(2)}`);
      const B = m.buckets, cashAll = (m.cash || 0) + (m.sti || 0), total = B.reduce((s, x) => s + x[1], 0);
      const W = 560, H = 190, left = 48, top = 18, bottom = 26;
      const ax = qAxis(B.map((x) => x[1]).concat(cashAll ? [cashAll] : []), H, top, bottom);
      const step = (W - left - 6) / B.length, bw = Math.min(52, step * 0.6);
      let g = qGrid(ax, W, left);
      B.forEach(([b, v], i) => {
        const x = left + i * step + (step - bw) / 2;
        g += qRect(x, ax.y(0), ax.y(v), bw, `ca-mat${b === 6 ? ' later' : ''}`, `${yl(b)}: ${money(v)}`);
        g += `<text class="q-val" x="${(x + bw / 2).toFixed(1)}" y="${(ax.y(v) - 5).toFixed(1)}" text-anchor="middle">${qm(v)}</text>`;
        g += `<text class="q-x" x="${(x + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${yl(b)}</text>`;
      });
      if (cashAll) g += `<line class="ca-cashline" x1="${left}" x2="${W - 4}" y1="${ax.y(cashAll).toFixed(1)}" y2="${ax.y(cashAll).toFixed(1)}"/><text class="ca-cashlab" x="${left + 4}" y="${(ax.y(cashAll) - 5).toFixed(1)}">cash and short-term investments ${money(cashAll)}</text>`;
      let run = 0, covered = 0;
      B.filter((x) => x[0] <= 5).forEach(([b, v]) => { run += v; if (run <= cashAll) covered = b; });
      const near = (B.find((x) => x[0] === 1) || [1, 0])[1];
      const pay = (b, v, r) => evBtn(money(v), { title: `Long-term debt due ${b === 6 ? 'after five years' : b === 1 ? 'within twelve months' : `in year ${b}`}`, value: money(v), period: `as of ${date(m.at)}`, ref: r,
        note: 'Principal of long-term debt falling due, from the debt note of the 10-K. Interest, leases and short-term borrowings are not included.' });
      const cashPay = () => evBtn(money(cashAll), { title: 'Cash and short-term investments', value: money(cashAll), period: `as of ${date(m.at)}`, kind: 'Derived',
        formula: `cash and equivalents ${money(m.cash)}${m.sti != null ? ` + short-term investments ${money(m.sti)}` : ''}`,
        inputs: [{ title: 'Cash and equivalents', value: money(m.cash), period: date(m.at), ref: (m.ev || {}).cash }].concat(m.sti != null ? [{ title: 'Short-term investments', value: money(m.sti), period: date(m.at), ref: (m.ev || {}).sti }] : []) });
      return `<article class="q-card"><h3>Debt maturities</h3>
        <p class="q-sum">As of ${date(m.at)}, ${t(name)} owed ${money(total)} of long-term debt principal on this schedule: ${money(near)} due in ${yl(1)}${B.some((x) => x[0] === 6) ? `, ${money((B.find((x) => x[0] === 6) || [0, 0])[1])} after five years` : ''}.
          ${cashAll ? `Cash and short-term investments of ${cashPay()} ${covered >= 5 ? 'exceed the next five years of maturities' : covered ? `cover the maturities through ${yl(covered)}` : near ? `cover ${Math.round(cashAll / near * 100)}% of the next year’s maturities` : ''}.` : ''}</p>
        <div class="ca-scroll"><svg class="q-chart ca-matchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Long-term debt principal due by fiscal year">${g}</svg></div>
        <div class="ca-mat-row">${B.map(([b, v, r]) => `<span><small>${yl(b)}</small>${pay(b, v, r)}</span>`).join('')}</div>
        <p class="muted q-small">From the 10-K debt note (${t(m.label)}), the latest that tags it. Principal only; operating leases, interest and short-term borrowings are not part of this schedule.</p></article>`;
    }

    function render() {
      const p = periods.find((x) => x.end === st.end && (x.kind === st.kind || !st.kind)) || yearly[yearly.length - 1] || periods[periods.length - 1];
      table.rows = p && p.kind === 'q' ? quarterly : yearly.length ? yearly : quarterly;
      const flags = (p && p.flags) || [];
      const opt = (x) => `<option value="${t(x.kind + '|' + x.end)}" ${x === p ? 'selected' : ''}>${t(x.label)}</option>`;
      box.innerHTML = `<div class="section-head"><h2 id="ca-title">Capital allocation</h2>
          <span class="muted">Where the cash came from and where it went, the share count, and when the debt falls due · the cash-flow statement, XBRL</span></div>
        ${periods.length ? `<div class="q-bar"><label class="q-pick">Period <select id="ca-period">${
          yearly.length && quarterly.length ? `<optgroup label="Fiscal years">${yearly.map(opt).join('')}</optgroup><optgroup label="Quarters">${quarterly.slice().reverse().map(opt).join('')}</optgroup>`
            : periods.map(opt).join('')}</select></label>
          <div class="export" role="group" aria-label="Export chart"><span>Export</span><button class="btn" type="button" data-cx="png">PNG</button><button class="btn" type="button" data-cx="jpg">JPG</button><button class="btn" type="button" data-cx="pdf">PDF</button></div></div>
        ${financial ? '<p class="q-warn">For banks, insurers and brokers, the cash-flow statement is dominated by lending, deposits and trading: “Other investing” and “Other financing” carry most of it, and the chart says little about capital allocation.</p>' : ''}
        ${flags.includes('unrec') ? `<p class="q-warn">${money(Math.abs(p.items.unrec || 0))} of the change in cash is not explained by the three section totals: usually discontinued operations, sometimes a tagging error. It is drawn as “Not reconciled”.</p>` : ''}
        <p class="q-sum">${sentence(p)}</p>
        <div class="hintline"><span class="dot"></span><span>Click any node for the XBRL facts and filings behind it.</span></div>
        <div class="sheet fit ca-sheet"><div class="loading">Drawing…</div></div>
        ${tableHTML()}` : ''}
        <div class="q-grid ca-grid">${sharesHTML()}${maturitiesHTML()}</div>`;
      const ps = $('#ca-period', box);
      if (ps) ps.addEventListener('change', () => { const [k, e] = ps.value.split('|'); st.kind = k; st.end = e; render(); });
      if (!p) return;
      const { spec: sp, pay } = spec(p);
      const sheet = $('.ca-sheet', box);
      fontsReady().then(() => {
        if (!sheet.isConnected) return;
        st.scene = S.layout(sp, {});
        sheet.innerHTML = S.toSVG(st.scene, S.dec(sp.title));
        $$('.note-mark', sheet).forEach((x) => x.remove());
        $$('.node', sheet).forEach((g) => {
          const n = sp.nodes.find((x) => x.id === g.dataset.node);
          g.setAttribute('tabindex', '0');
          g.setAttribute('role', 'button');
          if (n) g.setAttribute('aria-label', `${n.name}: ${n.lines[1][1]}`);
        });
      });
      const open = (g) => { if (g && pay.has(g.dataset.node)) evOpen(pay.get(g.dataset.node), g); };
      sheet.addEventListener('click', (e) => open(e.target.closest('[data-node]')));
      sheet.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { const g = e.target.closest && e.target.closest('[data-node]'); if (g) { e.preventDefault(); open(g); } } });
      $$('[data-cx]', box).forEach((b) => b.addEventListener('click', async () => {
        if (!st.scene) return;
        const fmt = b.dataset.cx, nm = `${(ticker || P.cik || 'company').toLowerCase()}-capital-allocation-${p.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.${fmt}`;
        b.disabled = true;
        try {
          const blob = await S.exportScene(st.scene, fmt);
          const res = await saveBlob(blob, nm);
          toast(res === 'declined' ? 'Export cancelled' : res === 'failed' ? 'Download unavailable here; use Preview to save the image' : `Exported ${nm}`, () => previewDialog(blob, fmt, nm, st.scene));
        } catch (err) {
          toast(`Export failed: ${err.message}`);
        } finally { b.disabled = false; }
      }));
    }
    render();
    body.appendChild(box);
  }

  // ---------- What moved profit: last year → this year, operating income and net income (pipeline/drivers.py) ----------
  const DRV = { rev: 'Revenue growth at last year’s gross margin', gm: 'Gross margin change', rd: 'Research and development',
    sga: 'Selling, general and administrative', sm: 'Selling and marketing', ga: 'General and administrative',
    other_op: 'Other operating items', rev_all: 'Revenue change', d_oi: 'Operating income change',
    nonop: 'Non-operating items', tax_rate: 'Tax rate change', tax_base: 'Tax on the change in pretax profit', tax: 'Income tax',
    after_tax: 'Below the tax line', shares: 'Share count (buybacks lift EPS, new shares dilute it)' };
  const DRV_IN = { revenue: 'Revenue', cor: 'Cost of revenue', gp: 'Gross profit', rd: 'Research and development', sga: 'Selling, general and administrative',
    sm: 'Selling and marketing', ga: 'General and administrative', oi: 'Operating income', pretax: 'Pretax income', tax: 'Income tax', ni: 'Net income' };

  function driversSection(body, c) {
    const D = (c.quality || {}).drivers, P = c.profile || {};
    if (!D || !(D.q || D.fy)) return;
    const box = document.createElement('section');
    box.className = 'section drivers';
    box.setAttribute('aria-labelledby', 'dv-title');
    const st = { mode: D.q ? 'q' : 'fy', end: null };
    const rate = (x, y) => (x != null && y ? `${(x / y * 100).toFixed(1)}%` : '—');
    function input(p, side, k) {
      const v = p[side][k], ref = (p.ev[side] || {})[k], lab = side === 'cur' ? p.label : p.prev_label;
      if (k === 'gp' && !ref && p[side].revenue != null && p[side].cor != null)
        return { title: `Gross profit, ${lab}`, value: money(v), period: lab, kind: 'Derived', formula: `revenue ${money(p[side].revenue)} − cost of revenue ${money(p[side].cor)}` };
      return { title: `${DRV_IN[k]}, ${lab}`, value: money(v), period: lab, ref, note: v == null ? 'Not tagged for this period.' : '' };
    }
    function payload(p, k, v) {
      const a = p.pri, b = p.cur, I = (side, ...ks) => ks.map((x) => input(p, side, x));
      const m0 = a.gp / a.revenue, m1 = b.gp / b.revenue;
      const base = { title: DRV[k] || k, value: money(v), period: `${p.label} vs ${p.prev_label}`, kind: 'Derived' };
      const F = {
        rev: [`(revenue ${money(b.revenue)} − ${money(a.revenue)}) × last year’s gross margin ${rate(a.gp, a.revenue)}`, I('cur', 'revenue').concat(I('pri', 'revenue', 'gp')),
          'Price, volume and product mix cannot be told apart from these figures: the company’s MD&A explains the revenue change in words.'],
        gm: [`revenue ${money(b.revenue)} × (gross margin ${rate(b.gp, b.revenue)} − ${rate(a.gp, a.revenue)})`, I('cur', 'revenue', 'gp').concat(I('pri', 'revenue', 'gp'))],
        rev_all: [`revenue ${money(b.revenue)} − ${money(a.revenue)}`, I('cur', 'revenue').concat(I('pri', 'revenue')), 'No cost of revenue is tagged: costs are taken together in “Other operating items”.'],
        other_op: [`operating income change ${money(b.oi - a.oi)} − the bars above`, I('cur', 'oi').concat(I('pri', 'oi')),
          'Operating costs without a tag of their own in both years (restructuring, impairments, amortization of acquired intangibles, other operating income), or lines tagged in only one of the two years.'],
        d_oi: [`operating income ${money(b.oi)} − ${money(a.oi)}`, I('cur', 'oi').concat(I('pri', 'oi'))],
        nonop: [`(pretax ${money(b.pretax)} − operating ${money(b.oi)}) − (pretax ${money(a.pretax)} − operating ${money(a.oi)})`, I('cur', 'pretax', 'oi').concat(I('pri', 'pretax', 'oi')),
          'Interest income and expense, investment gains and losses, and other income between operating income and pretax income.'],
        tax_rate: [`−pretax ${money(b.pretax)} × (tax rate ${rate(b.tax, b.pretax)} − ${rate(a.tax, a.pretax)})`, I('cur', 'tax', 'pretax').concat(I('pri', 'tax', 'pretax')),
          'What the change in the effective tax rate alone did to net income.'],
        tax_base: [`−(pretax ${money(b.pretax)} − ${money(a.pretax)}) × last year’s tax rate ${rate(a.tax, a.pretax)}`, I('cur', 'pretax').concat(I('pri', 'tax', 'pretax')),
          'The tax that would have come with the change in pretax profit at last year’s rate.'],
        tax: [`−(income tax ${money(b.tax)} − ${money(a.tax)})`, I('cur', 'tax').concat(I('pri', 'tax')), 'A pretax loss in one of the years: the tax change is shown whole.'],
        after_tax: [`(net income − (pretax − tax)) this year − last year`, I('cur', 'ni', 'pretax', 'tax').concat(I('pri', 'ni', 'pretax', 'tax')),
          'Discontinued operations, minority interests and equity-method results that sit below the tax line.'],
      };
      if (['rd', 'sga', 'sm', 'ga'].includes(k)) return { ...base, formula: `−(${DRV_IN[k].toLowerCase()} ${money(b[k])} − ${money(a[k])})`, inputs: I('cur', k).concat(I('pri', k)),
        note: v < 0 ? 'Higher spending lowered operating income.' : 'Lower spending raised operating income.' };
      const [formula, inputs, note] = F[k] || ['', []];
      return { ...base, formula, inputs, ...(note ? { note } : {}) };
    }
    function label(p, k, v) {
      const a = p.pri, b = p.cur;
      if (k === 'rev') return v < 0 && b.revenue < a.revenue ? 'Revenue decline at last year’s gross margin' : DRV.rev;
      if (k === 'gm') return `Gross margin ${rate(a.gp, a.revenue)} → ${rate(b.gp, b.revenue)}`;
      if (k === 'tax_rate') return `Tax rate ${rate(a.tax, a.pretax)} → ${rate(b.tax, b.pretax)}`;
      return DRV[k] || k;
    }
    function rowsHTML(p, start, startLab, bars, end, endLab, aria) {
      const rows = [[startLab, start, 'base', null]].concat(bars.map(([k, v]) => [label(p, k, v), v, k === 'other_op' || k === 'after_tax' ? 'gap' : 'step', k]), [[endLab, end, 'base', null]]);
      let run = 0;
      const spans = rows.map(([, v, kind]) => { if (kind === 'base') { run = v; return [0, v]; } const sp = [run, run + v]; run += v; return sp; });
      const lo = Math.min(0, ...spans.flat()), hi = Math.max(0, ...spans.flat()), w = (hi - lo) || 1;
      const pos = (v) => ((v - lo) / w * 100).toFixed(2);
      return `<div class="cq-bridge dv-bridge" role="table" aria-label="${t(aria)}">${rows.map(([lab, v, kind, k], i) => {
        const [x, z] = spans[i], left = pos(Math.min(x, z)), width = Math.max(0.4, Math.abs(pos(z) - pos(x))).toFixed(2);
        const pay = kind === 'base' ? { title: lab, value: money(v), period: lab, ref: (i === 0 ? p.ev.pri : p.ev.cur)[rows.length > 0 && aria.startsWith('Operating') ? 'oi' : 'ni'] } : payload(p, k, v);
        return `<div class="cq-row ${kind === 'gap' ? 'gap' : kind === 'base' ? 'base' : ''}" role="row"><span role="rowheader">${t(lab)}</span>
          <span class="cq-track" role="cell"><i class="cq-bar ${kind === 'base' ? 'base' : kind === 'gap' ? `dv-gap ${v < 0 ? 'minus' : 'plus'}` : `nc ${v < 0 ? 'minus' : 'plus'}`}" style="left:${left}%;width:${width}%"></i>${kind === 'base' ? '' : `<i class="cq-zero" style="left:${pos(0)}%"></i>`}</span>
          <span class="num" role="cell">${evBtn((kind === 'base' ? '' : v > 0 ? '+' : '') + money(v), pay)}</span></div>`;
      }).join('')}</div>`;
    }
    // EPS: the net income bars over last year's diluted shares, and the share count's own effect (pipeline/drivers.py)
    function epsRows(p) {
      const E = p.eps, ps = (v) => `${v < 0 ? '−' : ''}$${Math.abs(v).toFixed(2)}`;
      const rows = [[`Diluted EPS, ${p.prev_label}`, E.eps0, 'base', null]].concat(E.bars.filter(([, v]) => Math.abs(v) >= 0.005).map(([k, v]) => [label(p, k, v), v, k === 'other_op' || k === 'after_tax' ? 'gap' : 'step', k]), [[`Diluted EPS, ${p.label}`, E.eps1, 'base', null]]);
      let run = 0;
      const spans = rows.map(([, v, kind]) => { if (kind === 'base') { run = v; return [0, v]; } const sp = [run, run + v]; run += v; return sp; });
      const lo = Math.min(0, ...spans.flat()), hi = Math.max(0, ...spans.flat()), w = (hi - lo) || 1, pos = (v) => ((v - lo) / w * 100).toFixed(2);
      return `<div class="cq-bridge dv-bridge" role="table" aria-label="EPS bridge">${rows.map(([lab, v, kind, k], i) => {
        const [x, z] = spans[i], left = pos(Math.min(x, z)), width = Math.max(0.4, Math.abs(pos(z) - pos(x))).toFixed(2);
        return `<div class="cq-row ${kind === 'gap' ? 'gap' : kind === 'base' ? 'base' : ''}" role="row"><span role="rowheader">${t(lab)}</span>
          <span class="cq-track" role="cell"><i class="cq-bar ${kind === 'base' ? 'base' : kind === 'gap' ? `dv-gap ${v < 0 ? 'minus' : 'plus'}` : `nc ${v < 0 ? 'minus' : 'plus'}`}" style="left:${left}%;width:${width}%"></i>${kind === 'base' ? '' : `<i class="cq-zero" style="left:${pos(0)}%"></i>`}</span>
          <span class="num" role="cell">${kind === 'base' ? '' : v > 0 ? '+' : ''}${ps(v)}</span></div>`;
      }).join('')}</div><p class="muted q-small">Diluted shares ${(p.dil0 / 1e6).toLocaleString('en-US', { maximumFractionDigits: 0 })}M → ${(p.dil1 / 1e6).toLocaleString('en-US', { maximumFractionDigits: 0 })}M (${pct((p.dil1 / p.dil0 - 1) * 100)}). Each profit bar is divided by last year's shares; the last bar is what the change in the share count alone did. EPS here is net income ÷ diluted shares and can differ by a cent from the reported figure.</p>`;
    }
    function sentence(p) {
      const a = p.pri, b = p.cur, d = b.oi - a.oi, get = (k) => (p.op.find((x) => x[0] === k) || [k, 0])[1];
      const exp = p.op.filter(([k]) => ['rd', 'sga', 'sm', 'ga'].includes(k)).reduce((s, [, v]) => s + v, 0);
      const bits = [];
      if (get('rev')) bits.push(`${get('rev') >= 0 ? 'revenue growth added' : 'lower revenue took'} ${money(Math.abs(get('rev')))} at last year’s gross margin`);
      if (get('gm')) bits.push(`${get('gm') >= 0 ? 'a higher' : 'a lower'} gross margin ${get('gm') >= 0 ? 'added' : 'took'} ${money(Math.abs(get('gm')))}`);
      if (exp) bits.push(exp < 0 ? `higher operating expenses took ${money(-exp)}` : `lower operating expenses added ${money(exp)}`);
      if (Math.abs(get('other_op')) > 0.02 * Math.abs(d || 1)) bits.push(`other operating items ${get('other_op') < 0 ? 'took' : 'added'} ${money(Math.abs(get('other_op')))}`);
      let out = `Operating income ${d >= 0 ? 'rose' : 'fell'} ${money(Math.abs(d))} from ${t(p.prev_label)} to ${t(p.label)}${a.oi > 0 && b.oi > 0 ? ` (${pct((b.oi / a.oi - 1) * 100)})` : ''}${bits.length ? `: ${listJoin(bits)}` : ''}.`;
      if (p.below) {
        const tr = (p.below.find((x) => x[0] === 'tax_rate') || [0, 0])[1];
        out += ` Net income ${b.ni >= a.ni ? 'rose' : 'fell'} ${money(Math.abs(b.ni - a.ni))}${Math.abs(tr) > 0.1 * Math.abs(b.ni - a.ni || 1) ? `; the change in the tax rate alone ${tr > 0 ? 'added' : 'took'} ${money(Math.abs(tr))}` : ''}.`;
      }
      return out;
    }
    function render() {
      const L = (st.mode === 'fy' ? D.fy : D.q) || [];
      const p = L.find((x) => x.end === st.end) || L[L.length - 1];
      box.innerHTML = `<div class="section-head"><h2 id="dv-title">What moved profit</h2>
          <span class="muted">${st.mode === 'q' ? 'Each quarter against the same quarter a year earlier' : 'Each fiscal year against the one before'} · the income statement, XBRL</span></div>
        <div class="q-bar"><div class="seg" role="group" aria-label="Period type">
            <button type="button" data-dm="q" class="${st.mode === 'q' ? 'on' : ''}" ${D.q ? '' : 'disabled'}>Quarters, year over year</button>
            <button type="button" data-dm="fy" class="${st.mode === 'fy' ? 'on' : ''}" ${D.fy ? '' : 'disabled'}>Fiscal years</button></div>
          <label class="q-pick">Period <select id="dv-period">${L.map((x) => `<option value="${t(x.end)}" ${x === p ? 'selected' : ''}>${t(x.label)} vs ${t(x.prev_label)}</option>`).join('')}</select></label></div>
        <p class="q-sum">${sentence(p)}</p>
        <div class="q-grid dv-grid">
          <article class="q-card"><h3>Operating income, ${t(p.prev_label)} → ${t(p.label)}</h3>
            ${rowsHTML(p, p.pri.oi, `Operating income, ${p.prev_label}`, p.op, p.cur.oi, `Operating income, ${p.label}`, 'Operating income bridge')}</article>
          ${p.below ? `<article class="q-card"><h3>Net income, ${t(p.prev_label)} → ${t(p.label)}</h3>
            ${rowsHTML(p, p.pri.ni, `Net income, ${p.prev_label}`, p.below, p.cur.ni, `Net income, ${p.label}`, 'Net income bridge')}</article>` : ''}
          ${p.eps ? `<article class="q-card"><h3>Earnings per share, ${t(p.prev_label)} → ${t(p.label)}</h3>${epsRows(p)}</article>` : ''}
        </div>
        ${(p.mdna || []).length ? `<article class="q-card"><h3>Quantified by the company</h3><ul class="hv-items">${p.mdna.map((m) => `<li>${t(m.text)} <b>${money(m.amount)}</b>${m.src ? ` <span class="muted">· ${t(m.src)}</span>` : ''}</li>`).join('')}</ul></article>` : ''}
        <div class="q-legend"><span><i class="cq-bar plus nc"></i>Raised profit</span><span><i class="cq-bar minus nc"></i>Lowered profit</span><span><i class="cq-gap-key"></i>Lines without a tag of their own</span></div>
        <p class="muted q-small">Every bar is arithmetic on tagged figures and the bars add up exactly. The revenue bar cannot be split into price, volume and mix from these figures; the company’s MD&amp;A explains it in words. Select any figure for the formula and the XBRL facts behind it.</p>`;
      $$('[data-dm]', box).forEach((b) => b.addEventListener('click', () => { st.mode = b.dataset.dm; st.end = null; render(); }));
      $('#dv-period', box).addEventListener('change', (e) => { st.end = e.target.value; render(); });
    }
    render();
    body.appendChild(box);
  }

  // ---------- Balance sheet reformulated: operating vs financing, RNOA (pipeline/reform.py) ----------
  function reformSection(body, c) {
    const R = (c.quality || {}).reform, P = c.profile || {};
    const box = document.createElement('section');
    box.className = 'section reform';
    box.setAttribute('aria-labelledby', 'rf-title');
    if (!R || !(R.lines || []).length) {
      box.innerHTML = `<div class="section-head"><h2 id="rf-title">Balance sheet, reformulated</h2></div><p class="muted">The reformulated balance sheet is read on the next scans for this company: a few dozen companies a run, largest first.</p>`;
      body.appendChild(box);
      return;
    }
    const store = `ff-reform-${P.cik}`;
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(store) || '{}') || {}; } catch (e) { saved = {}; }
    const st = { i: R.ends.length - 1, tax: saved.tax != null ? saved.tax : R.tax_rate, cls: { ...(saved.cls || {}) } };
    const save = () => { try { localStorage.setItem(store, JSON.stringify({ cls: st.cls, tax: st.tax })); } catch (e) { /* private window */ } };
    const financial = P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''));
    const clsOf = (x) => st.cls[x.k] || x.cls;
    const T = (k, i) => ((R.totals || {})[k] || [])[i];
    const pctS = (v) => (v == null || !isFinite(v) ? 'n/m' : `${(v * 100).toFixed(1)}%`);
    function bal(i) {
      const sum = (side, cls) => R.lines.filter((x) => x.side === side && clsOf(x) === cls).reduce((s, x) => s + (x.v[i] || 0), 0);
      const oa = sum('a', 'op'), fa = sum('a', 'fin'), ol = sum('l', 'op'), fo = sum('l', 'fin');
      const cse = T('cse', i), nci = T('nci', i) || 0, temp = T('temp', i) || 0;
      const noa = oa - ol, nfo = fo - fa;
      return { oa, fa, ol, fo, noa, nfo, cse, nci, temp, eq: (cse || 0) + nci + temp, check: noa - nfo - ((cse || 0) + nci + temp) };
    }
    function rets(i) {
      if (i < 1) return null;
      const f = R.flows[i - 1] || {}, a = bal(i - 1), b = bal(i);
      const income = f.pl != null ? f.pl : f.ni;
      if (income == null) return null;
      const hasInt = f.int_exp != null || f.int_inc != null;
      const nfePre = hasInt ? Math.abs(f.int_exp || 0) - (f.int_inc || 0) : (f.pretax != null && f.oi != null ? -(f.pretax - f.oi) : 0);
      const nfe = nfePre * (1 - st.tax), oi = income + nfe;
      const avg = (k) => (a[k] + b[k]) / 2, noa = avg('noa'), nfo = avg('nfo'), eq = avg('eq');
      const rnoa = noa > 0 ? oi / noa : null, nbc = Math.abs(nfo) > 1e3 ? nfe / nfo : null, flev = eq > 0 ? nfo / eq : null;
      return { f, income, hasInt, nfePre, nfe, oi, noa, nfo, eq, rnoa, nbc, flev,
        roe: rnoa != null && flev != null && nbc != null ? rnoa + flev * (rnoa - nbc) : null, roeAct: eq > 0 ? income / eq : null,
        pm: f.revenue ? oi / f.revenue : null, ato: f.revenue && noa > 0 ? f.revenue / noa : null };
    }
    function amount(x, i) {
      const v = x.v[i], rs = (x.ev || [])[i] || [], per = R.labels[i];
      if (v == null) return '<span class="muted">—</span>';
      if (x.derived) {
        const tot = x.derived === 'assets' ? T('assets', i) : T('liab', i);
        const shown = R.lines.filter((y) => y.side === x.side && !y.derived).reduce((s, y) => s + (y.v[i] || 0), 0);
        return evBtn(money(v), { title: x.name, value: money(v), period: per, kind: 'Derived',
          formula: `total ${x.derived === 'assets' ? 'assets' : 'liabilities'} ${money(tot)} − the lines above ${money(shown)}`,
          note: v < 0 ? 'Negative: some lines above are already included in other lines of this balance sheet (taken twice), so this line takes them back out.' : x.why,
          inputs: [{ title: x.derived === 'assets' ? 'Total assets' : 'Total liabilities', value: money(tot), period: per, ref: ((R.ev_totals || {})[x.derived === 'assets' ? 'assets' : 'liab'] || [])[i],
            note: x.derived === 'liab' && !((R.ev_totals || {}).liab || [])[i] ? 'Not tagged: liabilities and equity minus equity.' : '' }] });
      }
      if (rs.length === 1) return evBtn(money(v), { title: x.name, value: money(v), period: per, ref: rs[0] });
      return evBtn(money(v), { title: x.name, value: money(v), period: per, kind: 'Reported', formula: 'sum of the tagged lines', inputs: rs.map((r) => ({ title: x.name, value: '', period: per, ref: r })) });
    }
    function sideHTML(side, i) {
      const L = R.lines.filter((x) => x.side === side && x.v[i] != null && (x.v[i] !== 0 || x.derived));
      const b = bal(i);
      const name = (x) => (x.derived && x.v[i] < 0 ? (side === 'a' ? 'Assets counted twice above' : 'Liabilities counted twice above') : x.name);
      return `<table class="ca-table rf-table"><thead><tr><th>${side === 'a' ? 'Assets' : 'Liabilities'}</th><th class="num">${t(R.labels[i])}</th><th>Class</th></tr></thead><tbody>
        ${L.map((x) => { const cl = clsOf(x), ed = st.cls[x.k] && st.cls[x.k] !== x.cls; return `<tr class="${ed ? 'rf-edited' : ''}">
          <td><span class="rf-name">${t(name(x))}</span><small class="rf-why">${t(x.why)}${x.suggest ? ` <b>Suggested from the notes: ${t(x.suggest.cls === 'fin' ? 'financing' : 'operating')}</b> — ${t(x.suggest.why || '')}` : ''}</small></td>
          <td class="num">${amount(x, i)}</td>
          <td><div class="seg rf-seg" role="group" aria-label="Class of ${t(x.name)}"><button type="button" data-rk="${x.k}" data-rc="op" class="${cl === 'op' ? 'on' : ''}">Operating</button><button type="button" data-rk="${x.k}" data-rc="fin" class="${cl === 'fin' ? 'on' : ''}">Financing</button></div>${ed ? '<small class="rf-ed">changed by you</small>' : ''}</td></tr>`; }).join('')}
        <tr class="ca-strong"><td>${side === 'a' ? 'Operating assets' : 'Operating liabilities'}</td><td class="num">${money(side === 'a' ? b.oa : b.ol)}</td><td></td></tr>
        <tr class="ca-strong"><td>${side === 'a' ? 'Financial assets' : 'Financial obligations'}</td><td class="num">${money(side === 'a' ? b.fa : b.fo)}</td><td></td></tr></tbody></table>`;
    }
    function render() {
      const i = st.i, b = bal(i), r = rets(i), edited = Object.keys(st.cls).some((k) => { const x = R.lines.find((y) => y.k === k); return x && st.cls[k] !== x.cls; });
      const kpi = (label, v, sub) => `<div class="q-kpi"><small>${label}</small><strong>${v}</strong><span>${sub}</span></div>`;
      const yrs = R.ends.map((e, j) => ({ j, r: rets(j) })).filter((x) => x.r);
      box.innerHTML = `<div class="section-head"><h2 id="rf-title">Balance sheet, reformulated</h2>
          <span class="muted">Operating against financing activities, and the return on net operating assets · the balance sheet and income statement, XBRL</span></div>
        <div class="q-bar rf-bar"><label class="q-pick">Fiscal year <select id="rf-year">${R.ends.map((e, j) => `<option value="${j}" ${j === i ? 'selected' : ''}>${t(R.labels[j])}</option>`).join('')}</select></label>
          <label class="q-pick">Tax rate on net interest <span class="v-in rf-tax"><input id="rf-tax" type="number" step="0.5" min="0" max="60" value="${(st.tax * 100).toFixed(1)}"><i>%</i></span></label>
          ${edited || saved.tax != null ? '<button class="btn small" type="button" id="rf-reset">Reset to the defaults</button>' : ''}</div>
        ${financial ? '<p class="q-warn">For banks and insurers, deposits, loans, policy reserves and investments are the business itself: the operating/financing split below says little.</p>' : ''}
        <div class="q-kpis rf-kpis">
          ${kpi('RNOA', pctS(r && r.rnoa), r ? `${pctS(r.pm)} margin × ${r.ato != null ? r.ato.toFixed(2) + '×' : 'n/m'} turnover` : 'needs the year before')}
          ${kpi('Net operating assets', money(b.noa), `operating assets ${money(b.oa)} − operating liabilities ${money(b.ol)}`)}
          ${kpi(b.nfo >= 0 ? 'Net financial obligations' : 'Net financial assets', money(Math.abs(b.nfo)), `financial obligations ${money(b.fo)} − financial assets ${money(b.fa)}`)}
          ${kpi(r && r.nfo < 0 ? 'Return on net financial assets' : 'Net borrowing cost', pctS(r && r.nfo < 0 && r.nbc != null ? -r.nbc : r && r.nbc),
            r ? `net financial ${r.nfePre >= 0 ? 'expense' : 'income'} ${money(Math.abs(r.nfePre))} before tax (${r.hasInt ? 'interest' : 'non-operating items'})` : '')}
          ${kpi('ROE', pctS(r && r.roeAct), r && r.flev != null ? `= RNOA + leverage (${r.flev.toFixed(2)}) × (RNOA − ${r.nfo >= 0 ? 'borrowing cost' : 'return on NFA'})` : '')}
        </div>
        <p class="q-sum">${r ? `${t(R.labels[i])}: operating income after tax ${money(r.oi)} on average net operating assets of ${money(r.noa)} is a ${pctS(r.rnoa)} return (RNOA)${r.rnoa != null && r.rnoa > 1 ? ' — very high because operating liabilities (supplier credit, deferred revenue, accruals) fund most of the operating assets' : r.rnoa == null ? ' — not meaningful: net operating assets are zero or negative' : ''}. ${r.nfo >= 0 ? `Net debt of ${money(r.nfo)} at an after-tax cost of ${pctS(r.nbc)}` : `Net financial assets of ${money(-r.nfo)} earning ${pctS(-r.nbc)} after tax`} take the return on equity to ${pctS(r.roeAct)}.` : 'Returns need the balance sheet of the year before.'}
          ${Math.abs(b.check) > Math.max(1e6, 0.002 * Math.abs(b.oa + b.fa)) ? `<span class="q-warmtext"> Balance check: net operating assets − net financial obligations differ from equity by ${money(b.check)} (equity or totals not tagged consistently).</span>` : ' <span class="pos">Balance check: net operating assets − net financial obligations = equity.</span>'}</p>
        <div class="q-grid rf-grid"><article class="q-card"><div class="tbl-wrap">${sideHTML('a', i)}</div></article><article class="q-card"><div class="tbl-wrap">${sideHTML('l', i)}</div>
          <p class="q-small muted">Equity: ${money(b.cse)}${b.nci ? ` · minority interests ${money(b.nci)}` : ''}${b.temp ? ` · redeemable / temporary equity ${money(b.temp)}` : ''}.</p></article></div>
        ${yrs.length ? `<h3 class="cq-h3">Returns by year</h3><div class="tbl-wrap"><table class="ca-table"><thead><tr><th>Fiscal year</th><th class="num">Operating income after tax</th><th class="num">Avg. NOA</th><th class="num">RNOA</th><th class="num">Margin</th><th class="num">Turnover</th><th class="num">Net borrowing cost</th><th class="num">Leverage</th><th class="num">ROE</th></tr></thead><tbody>
          ${yrs.slice().reverse().map(({ j, r: x }) => `<tr><td>${t(R.labels[j])}</td><td class="num">${evBtn(money(x.oi), { title: 'Operating income after tax', value: money(x.oi), period: R.labels[j], kind: 'Derived',
            formula: `net income ${money(x.income)} + net financial expense after tax ${money(x.nfe)} (${x.hasInt ? `net interest ${money(x.nfePre)}` : `non-operating items ${money(x.nfePre)}`} × (1 − ${(st.tax * 100).toFixed(1)}%))`,
            note: x.hasInt ? 'Interest expense minus interest income as tagged, after the tax it saves.' : 'No interest tags: every non-operating item (pretax income − operating income) is treated as financial.',
            inputs: ['pl', 'ni', 'int_exp', 'int_inc', 'pretax', 'oi'].filter((k) => x.f[k] != null).map((k) => ({ title: { pl: 'Net income incl. minority interests', ni: 'Net income', int_exp: 'Interest expense', int_inc: 'Interest income', pretax: 'Pretax income', oi: 'Operating income' }[k], value: money(x.f[k]), period: R.labels[j], ref: (x.f.ev || {})[k] })) })}</td>
            <td class="num">${money(x.noa)}</td><td class="num"><b>${pctS(x.rnoa)}</b></td><td class="num">${pctS(x.pm)}</td><td class="num">${x.ato != null ? x.ato.toFixed(2) + '×' : 'n/m'}</td><td class="num">${pctS(x.nbc)}${x.nfo < 0 ? '<sup>*</sup>' : ''}</td><td class="num">${x.flev != null ? x.flev.toFixed(2) : 'n/m'}</td><td class="num">${pctS(x.roeAct)}</td></tr>`).join('')}</tbody></table></div>` : ''}
        <p class="muted q-small">${yrs.some((x) => x.r.nfo < 0) ? '* Net financial assets: the net financial expense ÷ NFO is minus the return they earned. ' : ''}NOA = operating assets − operating liabilities; NFO = financial obligations − financial assets; RNOA = operating income after tax ÷ average NOA; net borrowing cost = net financial expense after tax ÷ average NFO; ROE = RNOA + leverage × (RNOA − net borrowing cost), leverage = average NFO ÷ average equity. Net income is not comprehensive income. Each line’s class is a default with its reason: change any of them, and every figure is recomputed; your choices stay in this browser.</p>`;
      $('#rf-year', box).addEventListener('change', (e) => { st.i = +e.target.value; render(); });
      $('#rf-tax', box).addEventListener('change', (e) => { const v = parseFloat(e.target.value); if (isFinite(v) && v >= 0 && v < 100) { st.tax = v / 100; save(); render(); } });
      $$('[data-rk]', box).forEach((btn) => btn.addEventListener('click', () => { st.cls[btn.dataset.rk] = btn.dataset.rc; save(); render(); }));
      const rs = $('#rf-reset', box);
      if (rs) rs.addEventListener('click', () => { st.cls = {}; st.tax = R.tax_rate; try { localStorage.removeItem(store); } catch (e) { /* ignore */ } saved = {}; render(); });
    }
    render();
    body.appendChild(box);
  }

  // ---------- Revisions, "As Known Then": every version of the headline figures (pipeline/history.py) ----------
  const HKEY = { revenue: 'Revenue', oi: 'Operating income', ni: 'Net income', ocf: 'Operating cash flow' };
  const HPAT = {
    amended: ['Amendment', 'The company filed an amended report (10-K/A or 10-Q/A) that replaced figures it had filed.'],
    results: ['Results changed', 'Net income changed: a restatement, a correction of an error, or an accounting change applied to earlier years (a new standard adopted retrospectively). The filing’s notes say which.'],
    presentation: ['Presentation changed', 'Revenue or operating income moved but net income did not: a reclassification, usually a business reported as discontinued operations (sold or spun off) or segments recast.'],
    'cash flow': ['Cash flow reclassified', 'Only operating cash flow changed: amounts moved between sections of the cash-flow statement, often after a new accounting standard.'],
  };
  // two amounts that would print the same are shown with one more digit ($1.41B → $1.43B, not $1.4B → $1.4B)
  function twoMoney(a, b) {
    if (money(a) !== money(b)) return [money(a), money(b)];
    const f = (v) => { const x = Math.abs(v), s = v < 0 ? '−' : ''; return x >= 0.95e9 ? `${s}${CUR}${(x / 1e9).toFixed(3)}B` : `${s}${CUR}${(x / 1e6).toFixed(2)}M`; };
    return [f(a), f(b)];
  }
  const filingUrl = (cik, accn) => `https://www.sec.gov/Archives/edgar/data/${cik}/${String(accn).replace(/-/g, '')}/${accn}-index.htm`;

  function revisionsSection(body, c) {
    const D = c.quality, H = D.hist, P = c.profile || {};
    const box = document.createElement('section');
    box.className = 'section revisions';
    box.setAttribute('aria-labelledby', 'hv-title');
    if (!H || !(H.periods || []).length) {
      box.innerHTML = `<div class="section-head"><h2 id="hv-title">As known then</h2></div><p class="muted">Every version of the headline figures is read on the next scans for this company: a few dozen companies a run, largest first.</p>`;
      body.appendChild(box);
      return;
    }
    const S0 = D.src || { concepts: [], filings: [] };
    const name = S.dec(P.name || '');
    const fil = (ref) => S0.filings[ref[2][0]] || ['', '', ''];          // [accn, form, filed]
    const hasQ = H.keys.some((k) => (H.v[k] || []).some(([i]) => H.periods[i][2] === 'q'));
    const st = { key: 'revenue', kind: 'fy', asof: 'first' };
    if (!(H.v.revenue || []).length) st.key = H.keys.find((k) => (H.v[k] || []).length) || 'ni';
    const rows = () => (H.v[st.key] || []).filter(([i]) => H.periods[i][2] === st.kind).map(([i, vs]) => ({ p: H.periods[i], vs }));
    // the version known before a date (a revising filing's day), or the first one
    const then = (vs) => (st.asof === 'first' ? vs[0] : vs.slice().reverse().find(([, r]) => fil(r)[2] < st.asof) || null);
    const vPay = (r, ver, title) => ({ title: `${HKEY[st.key]}, ${r.p[3]}`, value: money(ver[0]), period: `${title} · ${fil(ver[1])[1]} filed ${date(fil(ver[1])[2])}`, ref: ver[1] });

    function chartHTML(L) {
      const W = 760, H2 = 220, left = 52, top = 16, bottom = 28;
      const vals = L.flatMap((r) => { const a = then(r.vs), n = r.vs[r.vs.length - 1]; return [n[0]].concat(a ? [a[0]] : []); });
      const ax = qAxis(vals, H2, top, bottom);
      const step = (W - left - 6) / Math.max(1, L.length), bw = Math.min(26, step * 0.36);
      let g = qGrid(ax, W, left);
      L.forEach((r, i) => {
        const a = then(r.vs), n = r.vs[r.vs.length - 1], x = left + i * step + step / 2;
        const diff = a && a[0] !== n[0];
        if (diff) g += qRect(x - bw - 1, ax.y(0), ax.y(a[0]), bw, 'hv-then', `${r.p[3]}: ${money(a[0])} ${st.asof === 'first' ? 'as first reported' : 'as known then'}`);
        g += qRect(diff ? x + 1 : x - bw / 2, ax.y(0), ax.y(n[0]), bw, `hv-now${diff ? ' on' : ''}`, `${r.p[3]}: ${money(n[0])} now`);
        if (!a) g += `<text class="q-na" x="${(x - bw / 2).toFixed(1)}" y="${(ax.y(0) - 4).toFixed(1)}" text-anchor="middle">·</text>`;
        if (L.length <= 12 || i % 2 === L.length % 2 - 1 || i === L.length - 1)
          g += `<text class="q-x" x="${x.toFixed(1)}" y="${H2 - 8}" text-anchor="middle">${t(r.p[3].replace(/^FY/, st.kind === 'fy' ? 'FY' : ''))}</text>`;
      });
      return `<div class="ca-scroll"><svg class="q-chart hv-chart" viewBox="0 0 ${W} ${H2}" role="img" aria-label="${HKEY[st.key]}: then and now">${g}</svg></div>`;
    }
    function tableHTML(L) {
      return `<div class="tbl-wrap"><table class="ca-table hv-table"><thead><tr><th>Period</th><th class="num">${st.asof === 'first' ? 'First reported' : 'As known then'}</th><th class="num">Now</th><th class="num">Change</th><th>Versions</th></tr></thead><tbody>
        ${L.slice().reverse().map((r) => {
          const a = then(r.vs), n = r.vs[r.vs.length - 1], diff = a && a[0] !== n[0];
          const ch = diff ? (a[0] ? (n[0] / a[0] - 1) * 100 : null) : null;
          const [ta, tn] = diff ? twoMoney(a[0], n[0]) : [a ? money(a[0]) : '', money(n[0])];
          return `<tr class="${diff ? 'hv-diff' : ''}"><td>${t(r.p[3])}</td>
            <td class="num">${a ? evBtn(ta, vPay(r, a, st.asof === 'first' ? 'first reported' : 'as known then')) : '<span class="muted">not yet reported</span>'}</td>
            <td class="num">${evBtn(tn, vPay(r, n, 'now'))}</td>
            <td class="num">${diff ? `${money(n[0] - a[0]).replace(/^(?!−)/, '+')}${ch != null && a[0] > 0 && n[0] > 0 ? ` <span class="muted">(${pct(ch, 1)})</span>` : ''}` : '<span class="muted">—</span>'}</td>
            <td class="hv-vers">${r.vs.map((v, j) => `${j ? '→ ' : ''}<a href="${filingUrl(P.cik, fil(v[1])[0])}" target="_blank" rel="noopener" title="${t(money(v[0]))}">${t(fil(v[1])[1])} ${t(date(fil(v[1])[2]))}</a>`).join(' ')}</td></tr>`;
        }).join('')}</tbody></table></div>`;
    }
    function eventsHTML() {
      const E = H.events || [];
      if (!E.length) return `<p class="muted">No filing has changed a figure ${t(name)} first reported (revenue, operating income, net income, operating cash flow, last ten years).</p>`;
      const used = [...new Set(E.map((e) => e.pattern))];
      const legend = `<dl class="hv-pats">${Object.entries(HPAT).filter(([k]) => used.includes(k)).map(([k, [tag, expl]]) => `<dt><span class="v-tag hv-${k.replace(/\s/g, '-')}">${t(tag)}</span></dt><dd>${t(expl)}</dd>`).join('')}</dl>
        <p class="muted q-small">The kind of change is read from the numbers; the reason is in each filing’s notes (basis of presentation, or the explanatory note of an amendment).</p>`;
      return `${legend}<div class="hv-events">${E.map((e) => {
        const [accn, form, filed] = S0.filings[e.filing] || [];
        const [tag, expl] = HPAT[e.pattern] || [e.pattern, ''];
        const items = e.items.slice(0, 8).map(([k, i, a, b]) => { const [x, y] = twoMoney(a, b); return `<li>${t(H.periods[i][3])} ${t(HKEY[k].toLowerCase())}: <span class="nw">${x}</span> → <b class="nw">${y}</b>${a > 0 && b > 0 ? ` <span class="muted nw">(${pct((b / a - 1) * 100, 1)})</span>` : ''}</li>`; }).join('');
        return `<article class="q-card hv-event"><div class="hv-ev-head"><a href="${filingUrl(P.cik, accn)}" target="_blank" rel="noopener"><b>${t(form)}</b> filed ${date(filed)} ↗</a><span class="v-tag hv-${e.pattern.replace(/\s/g, '-')}" title="${t(expl)}">${t(tag)}</span></div>
          <ul class="hv-items">${items}${e.items.length > 8 ? `<li class="muted">and ${e.items.length - 8} more</li>` : ''}</ul>
          ${e.why ? `<blockquote class="hv-why">${t(e.why.text || e.why)}${e.why.src ? `<span class="muted"> · ${t(e.why.src)}</span>` : ''}</blockquote>` : ''}</article>`;
      }).join('')}</div>`;
    }
    function summary(L) {
      const ch = L.map((r) => ({ r, a: r.vs[0], n: r.vs[r.vs.length - 1] })).filter((x) => x.a[0] !== x.n[0]);
      const per = st.kind === 'fy' ? 'fiscal years' : 'quarters';
      if (!ch.length) return `${t(HKEY[st.key])}: none of the ${L.length} ${per} on file differs from what ${t(name)} first reported.`;
      const big = ch.reduce((m, x) => (Math.abs(x.n[0] - x.a[0]) > Math.abs(m.n[0] - m.a[0]) ? x : m));
      const by = big.r.vs.find((v, j) => j && v[0] === big.n[0]) || big.n;
      const [x, y] = twoMoney(big.a[0], big.n[0]);
      return `${t(HKEY[st.key])}: ${ch.length} of ${L.length} ${per} now differ from what ${t(name)} first reported. The largest change: ${t(big.r.p[3])}, ${x} first reported, ${y} now${big.a[0] > 0 && big.n[0] > 0 ? ` (${pct((big.n[0] / big.a[0] - 1) * 100, 1)})` : ''}, changed by the ${t(fil(by[1])[1])} filed ${date(fil(by[1])[2])}.`;
    }
    function render() {
      const L = rows();
      const dates = [...new Set((H.events || []).map((e) => (S0.filings[e.filing] || [])[2]).filter(Boolean))].sort().reverse();
      box.innerHTML = `<div class="section-head"><h2 id="hv-title">As known then</h2>
          <span class="muted">Every version of the headline figures, as each filing reported them · SEC company facts, XBRL</span></div>
        <div class="q-bar hv-bar">
          <div class="seg" role="group" aria-label="Figure">${H.keys.filter((k) => (H.v[k] || []).length).map((k) => `<button type="button" data-hk="${k}" class="${k === st.key ? 'on' : ''}">${HKEY[k]}</button>`).join('')}</div>
          <div class="seg" role="group" aria-label="Period type"><button type="button" data-hp="fy" class="${st.kind === 'fy' ? 'on' : ''}">Fiscal years</button><button type="button" data-hp="q" class="${st.kind === 'q' ? 'on' : ''}" ${hasQ ? '' : 'disabled'}>Quarters</button></div>
          <label class="q-pick">Compare now with <select id="hv-asof"><option value="first" ${st.asof === 'first' ? 'selected' : ''}>as first reported</option>${dates.map((d) => `<option value="${d}" ${st.asof === d ? 'selected' : ''}>as known before ${date(d)}</option>`).join('')}</select></label></div>
        <p class="q-sum">${summary(L)}</p>
        ${L.length ? chartHTML(L) : ''}
        <div class="q-legend"><span><i class="hv-key-then"></i>${st.asof === 'first' ? 'As first reported' : `As known before ${date(st.asof)}`} (only where it differs)</span><span><i class="hv-key-now"></i>As reported now</span></div>
        ${L.length ? tableHTML(L) : ''}
        <p class="muted q-small">“Versions” lists every filing that gave this figure a new value, oldest first. Quarters are three-month figures as tagged; a fourth quarter appears only where a filing tagged it on its own. Select a value to see the XBRL fact.</p>
        <h3 class="cq-h3">Filings that changed earlier figures</h3>
        ${eventsHTML()}`;
      $$('[data-hk]', box).forEach((b) => b.addEventListener('click', () => { st.key = b.dataset.hk; render(); }));
      $$('[data-hp]', box).forEach((b) => b.addEventListener('click', () => { st.kind = b.dataset.hp; render(); }));
      $('#hv-asof', box).addEventListener('change', (e) => { st.asof = e.target.value; render(); });
    }
    render();
    body.appendChild(box);
  }

  // ---------- Valuation: a forward FCFF DCF and what the price implies (web/fsa.js) ----------
  async function valuationSection(body, c, ticker, here) {
    const D = c.quality, V = D.val, P = c.profile || {};
    const box = document.createElement('section');
    box.className = 'section val';
    box.setAttribute('aria-labelledby', 'v-title');
    body.appendChild(box);
    const financial = P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''));
    if (!V || !V.revenue) {
      box.innerHTML = `<div class="section-head"><h2 id="v-title">Valuation</h2></div><p class="muted">${financial
        ? 'A free-cash-flow model does not describe banks, insurers or brokers, whose debt and cash flows are part of the business.'
        : 'Trailing revenue and the balance sheet are read on the next scans for this company.'}</p>`;
      return;
    }
    let px = null;
    try {
      const pr = await getJSON('prices.json');
      const k = String(ticker || '').toUpperCase().replace(/[./]/g, '-');
      if (pr && pr.p && pr.p[k]) px = { price: pr.p[k][0], mcap: pr.p[k][1], asof: pr.asof, source: pr.source };
    } catch (e) { /* no price list: the reader enters one */ }
    if (!here()) return;
    const R = V.refs || {};
    const SH = shareCount(V, px && px.price), rev = V.revenue, oi = V.oi, sh = SH.v;
    const tr = V.pretax > 0 && V.tax != null ? Math.min(0.35, Math.max(0, V.tax / V.pretax)) : 0.21;
    const qs = (D.q || []).filter((p) => p.wc && p.wc.rev != null);
    const prior = qs.length >= 8 ? qs.slice(-8, -4).reduce((s, p) => s + p.wc.rev, 0) : null;
    const g0 = prior > 0 ? Math.max(-0.2, Math.min(0.4, rev / prior - 1)) : 0.05;
    const defaults = {
      price: px ? px.price : null, shares: sh || null, years: 5,
      growth: +(g0 * 100).toFixed(1), margin: oi != null ? +(oi / rev * 100).toFixed(1) : 10, tax: +(tr * 100).toFixed(1),
      da: V.da != null ? +(V.da / rev * 100).toFixed(1) : 3, capex: V.capex != null ? +(V.capex / rev * 100).toFixed(1) : 4, wc: 10,
      wacc: 9, g: 2.5, terminal: 'roic', roic: 15, lossTax: 'none',
      debt: V.debt || 0, cash: V.cash_all || 0, claims: V.claims || 0, nonop: 0,
      solveFor: 'growth', lo: -20, hi: 40,
    };
    let A = { ...defaults };
    let CS = null;                         // consensus (disclosures/data/consensus/c/<cik>.json): loaded after the first draw
    const periodTxt = V.basis === 'ttm' ? `trailing four quarters to ${date(V.end)}` : `fiscal year to ${date(V.end)}`;
    const refsOf = (k) => (R[k] || []).filter(Boolean);
    const rep = (title, val, k, note) => ({ title, value: money(val), period: periodTxt, ref: refsOf(k).length === 1 ? refsOf(k)[0] : null,
      inputs: refsOf(k).length > 1 ? refsOf(k).map((r, i) => ({ title: `${title}, quarter ${i + 1} of 4`, value: '', ref: r })) : undefined,
      kind: refsOf(k).length > 1 ? 'Derived (sum of four quarters)' : 'Reported', note });
    const consPath = (g, m) => {                // the years analysts cover at their rates, then the reader's
      const F = consFigures(), n = F.growth != null ? Math.min(A.years, Math.max(1, Math.round(F.span))) : 0;
      const arr = (c, own) => (c == null || !n ? own : Array.from({ length: A.years }, (_, i) => (i < n ? c : own)));
      return { growth: arr(F.growth, g), margin: arr(F.margin, m), n, F };
    };
    const model = () => ({ rev0: rev, years: A.years, ...(A.cons && CS ? (({ growth, margin }) => ({ growth, margin }))(consPath(A.growth / 100, A.margin / 100))
      : { growth: A.growth / 100, margin: A.margin / 100 }), tax: A.tax / 100, da: A.da / 100,
      capex: A.capex / 100, wc: A.wc / 100, wacc: A.wacc / 100, g: A.g / 100, terminal: A.terminal, roic: A.roic / 100, lossTax: A.lossTax,
      debt: A.debt, cash: A.cash, claims: A.claims, nonop: A.nonop, shares: A.shares });
    const pct = (v, d) => `${v < 0 ? '−' : ''}${Math.abs(v).toFixed(d == null ? 1 : d)}%`;
    const usd = (v) => (v == null || !isFinite(v) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(v).toFixed(2)}`);
    const field = (k, label, unit, opt) => {
      const sc = (opt && opt.scale) || 1, v = A[k] == null ? '' : +(A[k] / sc).toFixed(sc > 1 ? 1 : 4);
      return `<label class="v-f"><span>${label}${opt && opt.tag ? ` <em class="v-tag ${opt.tag}">${opt.tag}</em>` : ''}</span>
      <span class="v-in"><input type="number" step="${opt && opt.step || 0.1}" data-k="${k}" data-scale="${sc}" value="${v}" ${opt && opt.min != null ? `min="${opt.min}"` : ''}>${unit ? `<i>${unit}</i>` : ''}</span></label>`;
    };

    function heat(grid, rows, cols, fmtR, fmtC, price, rl, cl, cap) {
      const W = 360, H = 30 + rows.length * 26, left = 56, top = 26, cw = (W - left) / cols.length;
      let g = '';
      cols.forEach((cv, j) => { g += `<text class="q-tick" x="${(left + j * cw + cw / 2).toFixed(1)}" y="16" text-anchor="middle">${fmtC(cv)}</text>`; });
      rows.forEach((rv, i) => {
        g += `<text class="q-tick" x="${left - 6}" y="${(top + i * 26 + 17).toFixed(1)}" text-anchor="end">${fmtR(rv)}</text>`;
        cols.forEach((cv, j) => {
          const v = grid[i][j], ratio = price > 0 && isFinite(v) ? v / price : null;
          const cls = ratio == null ? 'h-na' : ratio >= 1.2 ? 'h-up2' : ratio >= 1 ? 'h-up1' : ratio >= 0.8 ? 'h-dn1' : 'h-dn2';
          g += `<rect class="${cls}" x="${(left + j * cw + 1).toFixed(1)}" y="${top + i * 26}" width="${(cw - 2).toFixed(1)}" height="24" rx="3"><title>${rl} ${fmtR(rv)}, ${cl} ${fmtC(cv)}: ${usd(v)} a share</title></rect>
            <text class="h-txt" x="${(left + j * cw + cw / 2).toFixed(1)}" y="${(top + i * 26 + 16).toFixed(1)}" text-anchor="middle">${isFinite(v) ? (Math.abs(v) >= 1000 ? Math.round(v) : v.toFixed(0)) : '—'}</text>`;
        });
      });
      return `<p class="muted q-small">Rows: ${t(rl)} · columns: ${t(cl)}</p><div class="q-scroll"><svg class="q-chart v-heat" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(cap)}">${g}</svg></div>`;
    }

    function render() {
      const x = model(), r = FSA.dcf(x), price = A.price;
      let out = '';
      if (!r.ok) out = `<div class="q-warn">${r.errors.map(t).join('<br>')}</div>`;
      else {
        const up = price > 0 ? r.perShare / price - 1 : null;
        const steps = [['Enterprise value', r.ev, 'v-ev'], ['− Debt', -A.debt, 'v-minus'], ['− Minority and preferred', -A.claims, 'v-minus'],
          ['+ Cash and short-term investments', A.cash, 'v-plus'], ['+ Other nonoperating assets', A.nonop, 'v-plus'], ['= Equity value', r.equity, 'v-eq']].filter((s, i) => i === 0 || i === 5 || s[1]);
        const hi = Math.max(...steps.map((s) => Math.abs(s[1])), 1);
        out = `<div class="v-result"><div><small>Model value per share</small><strong>${usd(r.perShare)}</strong>
              <span class="muted">${price > 0 ? `${up >= 0 ? '+' : '−'}${Math.abs(up * 100).toFixed(0)}% vs the price ${usd(price)}` : 'enter a price to compare'}</span></div>
            <div><small>Enterprise value</small><strong>${money(r.ev)}</strong><span class="muted">terminal value ${r.ev > 0 ? Math.round(r.tvPv / r.ev * 100) + '%' : '—'} of it</span></div>
            <div><small>Equity value</small><strong>${money(r.equity)}</strong><span class="muted">÷ ${(A.shares / 1e6).toFixed(0)}M diluted shares</span></div></div>
          ${r.flags.length ? `<p class="q-warn">${r.flags.map((f) => t(f.charAt(0).toUpperCase() + f.slice(1))).join('. ')}. Treat this as a scenario to review, not an estimate.</p>` : ''}
          <div class="v-bridge">${steps.map(([l, v, cls]) => `<div class="v-step ${cls}"><span>${t(l)}</span><i style="width:${(Math.abs(v) / hi * 100).toFixed(1)}%"></i><b>${money(v)}</b></div>`).join('')}</div>
          <div class="tbl-wrap"><table class="v-table"><thead><tr><th>Year</th>${r.rows.map((x) => `<th class="num">+${x.t}</th>`).join('')}<th class="num">Terminal</th></tr></thead><tbody>
            <tr><td>Revenue</td>${r.rows.map((x) => `<td class="num">${money(x.rev)}</td>`).join('')}<td></td></tr>
            <tr><td>EBIT</td>${r.rows.map((x) => `<td class="num">${money(x.ebit)}</td>`).join('')}<td></td></tr>
            <tr><td>NOPAT</td>${r.rows.map((x) => `<td class="num">${money(x.nopat)}</td>`).join('')}<td></td></tr>
            <tr><td>+ D&amp;A − capex − Δ working capital</td>${r.rows.map((x) => `<td class="num">${money(x.da - x.capex - x.dwc)}</td>`).join('')}<td></td></tr>
            <tr class="v-strong"><td>Free cash flow to the firm</td>${r.rows.map((x) => `<td class="num">${money(x.fcff)}</td>`).join('')}<td class="num">${money(r.fcffNext)}</td></tr>
            <tr><td>Present value</td>${r.rows.map((x) => `<td class="num">${money(x.pv)}</td>`).join('')}<td class="num">${money(r.tvPv)}</td></tr>
          </tbody></table></div>`;
      }
      // reverse: what the price needs, one parameter at a time
      let revCard = '';
      if (r.ok && price > 0) {
        const P2 = { growth: ['Revenue growth (every forecast year)', '%'], margin: ['EBIT margin (every forecast year)', '%'], wacc: ['WACC', '%'] }[A.solveFor];
        const s = FSA.solve(x, A.solveFor, price, A.lo / 100, A.hi / 100);
        const msg = s.status === 'ok' ? `<p class="v-implied"><b>${pct(s.value * 100)}</b> ${t(P2[0].toLowerCase())} — with everything else as set — gives ${usd(price)} a share.
              <span class="muted">Check: the forward model at ${pct(s.value * 100, 3)} gives ${usd(s.check)} (difference ${Math.abs(s.residual) < 0.005 ? 'under half a cent' : usd(s.residual)}).</span></p>`
          : s.status === 'none' ? `<p class="q-warn">No ${t(P2[0].toLowerCase())} between ${A.lo}% and ${A.hi}% gives this price${s.range ? `: the model ranges from ${usd(s.range[0] + price)} to ${usd(s.range[1] + price)} a share` : ''}. Widen the range or change another assumption.</p>`
            : s.status === 'multiple' ? `<p class="q-warn">More than one ${t(P2[0].toLowerCase())} gives this price (${s.brackets.map(([a, b]) => `${pct(a * 100)}–${pct(b * 100)}`).join(', ')}): narrow the range to pick one.</p>`
              : '<p class="q-warn">The search did not converge in this range.</p>';
        const gs = [-0.05, 0, 0.05, 0.1, 0.15, 0.2, 0.25].map((v) => +(v).toFixed(2));
        const base = A.margin / 100, ms = [-0.1, -0.05, 0, 0.05, 0.1].map((d) => +(base + d).toFixed(3));
        const grid = FSA.grid(x, 'margin', ms, 'growth', gs);
        revCard = `<article class="q-card"><h3>What the price implies</h3>
            <p class="muted">Solve for one assumption at a time, holding the others. A price cannot pin down growth, margin and risk together; the map below shows which combinations reach it.</p>
            <div class="v-solve"><label class="q-pick">Solve for <select id="v-solve">${[['growth', 'Revenue growth'], ['margin', 'EBIT margin'], ['wacc', 'WACC']].map(([k, l]) => `<option value="${k}" ${A.solveFor === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
              ${field('lo', 'from', '%', { step: 1 })}${field('hi', 'to', '%', { step: 1 })}</div>
            ${msg}
            <h3 class="v-h3">Expectations map <span class="muted">· value per share at each growth × margin, against ${usd(price)}</span></h3>
            ${heat(grid, ms, gs, (v) => pct(v * 100, 0), (v) => pct(v * 100, 0), price, 'Margin', 'Growth', 'Value per share by revenue growth and EBIT margin')}
            <div class="q-legend"><span><i class="h-up2"></i>≥ 20% above the price</span><span><i class="h-up1"></i>0–20% above</span><span><i class="h-dn1"></i>0–20% below</span><span><i class="h-dn2"></i>more than 20% below</span></div>
          </article>`;
      }
      const consCard = r.ok ? consensusCard(x, price) : '';
      let sens = '';
      if (r.ok) {
        const ws = [-2, -1, 0, 1, 2].map((d) => +(A.wacc / 100 + d / 100).toFixed(4)), gsn = [-1, -0.5, 0, 0.5, 1].map((d) => +(A.g / 100 + d / 100).toFixed(4));
        sens = `<article class="q-card"><h3>Sensitivity: WACC × terminal growth</h3><p class="muted">Value per share; cells where WACC is not above growth are left blank.</p>
          ${heat(FSA.grid(x, 'wacc', ws, 'g', gsn), ws, gsn, (v) => pct(v * 100), (v) => pct(v * 100), price || r.perShare, 'WACC', 'g', 'Value per share by WACC and terminal growth')}</article>`;
      }
      box.innerHTML = `<div class="section-head"><h2 id="v-title">Valuation</h2>
          <span class="muted">A discounted cash flow model on the company’s reported figures. Reported figures start it; every forecast number is an assumption you can change. Not investment advice.</span></div>
        ${financial ? '<p class="q-warn">A free-cash-flow model does not fit banks, insurers or brokers well: their debt and cash flows are part of the business.</p>' : ''}
        <div class="v-grid">
          <article class="q-card v-inputs"><h3>Starting point <span class="muted">· ${periodTxt}</span></h3>
            <dl class="v-rep">
              <dt>Revenue</dt><dd>${evBtn(money(rev), rep('Revenue', rev, 'revenue'))}</dd>
              <dt>Operating income</dt><dd>${oi != null ? evBtn(money(oi), rep('Operating income', oi, 'oi')) : '—'} ${oi != null ? `<span class="muted">${pct(oi / rev * 100)} margin</span>` : ''}</dd>
              <dt>Income tax</dt><dd>${V.tax != null ? evBtn(money(V.tax), rep('Income tax', V.tax, 'tax')) : '—'} <span class="muted">${V.pretax > 0 ? `${pct(V.tax / V.pretax * 100)} of pretax ${money(V.pretax)}` : V.pretax != null ? 'pretax loss' : ''}</span></dd>
              <dt>D&amp;A · capex</dt><dd>${V.da != null ? evBtn(money(V.da), rep('Depreciation and amortization', V.da, 'da')) : '—'} · ${V.capex != null ? evBtn(money(V.capex), rep('Capital expenditures', V.capex, 'capex')) : '—'}</dd>
              <dt>Debt</dt><dd>${evBtn(money(V.debt), { title: 'Debt', value: money(V.debt), period: `latest balance (${(V.bal_dates || []).map(date).join(', ')})`, kind: 'Derived', formula: t(V.debt_how || ''),
                inputs: [['b_ltd', 'Long-term debt (incl. current)'], ['b_ltd_nc', 'Long-term debt, noncurrent'], ['b_ltd_c', 'Long-term debt, current'], ['b_debt_c', 'Debt, current'], ['b_stb', 'Short-term borrowings / commercial paper']]
                  .filter(([k]) => V[k] != null).map(([k, l]) => ({ title: l, value: money(V[k]), ref: (R[k] || [])[0] })),
                note: V.debt_how === 'no debt tagged' ? 'No standard debt tag was found: enter the debt from the balance sheet.' : 'Operating leases are not included.' })}${V.debt_how === 'no debt tagged' ? ' <span class="q-warmtext">not tagged: check</span>' : ''}</dd>
              <dt>Cash and short-term investments</dt><dd>${evBtn(money(V.cash_all), { title: 'Cash and short-term investments', value: money(V.cash_all), kind: 'Derived', formula: 'cash and cash equivalents + short-term investments',
                inputs: [['b_cash', 'Cash and cash equivalents'], ['b_sti', 'Short-term investments']].filter(([k]) => V[k] != null).map(([k, l]) => ({ title: l, value: money(V[k]), ref: (R[k] || [])[0] })) })}</dd>
              <dt>Diluted shares</dt><dd>${sh ? evBtn(`${(sh / 1e6).toFixed(1)}M`, { title: SH.key === 'diluted' ? 'Diluted weighted-average shares' : 'Shares outstanding (cover page)', value: `${(sh / 1e6).toFixed(1)}M`, ref: (R[SH.key] || [])[0] }) : '—'}${SH.note ? ` <span class="muted">${t(SH.note)}</span>` : ''}</dd>
              <dt>Price</dt><dd>${px ? `${usd(px.price)} <span class="muted">${t(px.source)}, ${date(px.asof)}</span>` : '<span class="muted">not available: enter one</span>'}</dd>
            </dl>
            <h3>Assumptions <span class="muted">· yours to change</span></h3>
            <div class="v-fields">
              ${field('price', 'Share price', '$', { step: 0.01, tag: px ? 'market' : 'enter' })}${field('shares', 'Diluted shares', 'M', { step: 1, scale: 1e6 })}
              ${A.cons && CS ? (() => { const cp = consPath(0, 0); return `<p class="v-consline">Year${cp.n > 1 ? 's 1–' + cp.n : ' 1'}: analysts’ consensus — revenue ${pct(cp.F.growth * 100)} a year${cp.F.margin != null ? `, EBIT margin ${pct(cp.F.margin * 100)}` : ''}. The fields below apply after that.</p>`; })() : ''}
              ${field('growth', A.cons && CS ? 'Revenue growth, later years' : 'Revenue growth', '%/yr', { tag: 'assumption' })}${field('margin', 'EBIT margin', '%', { tag: 'assumption' })}
              ${field('tax', 'Tax rate', '%', { tag: 'assumption' })}${field('da', 'D&A', '% rev')}${field('capex', 'Capex', '% rev')}
              ${field('wc', 'Working capital', '% of Δrev', { tag: 'assumption' })}${field('wacc', 'WACC', '%', { tag: 'assumption' })}${field('g', 'Terminal growth', '%', { tag: 'assumption' })}
              <label class="v-f"><span>Terminal method</span><span class="v-in"><select data-k="terminal"><option value="roic" ${A.terminal === 'roic' ? 'selected' : ''}>Reinvestment = g ÷ ROIC</option><option value="simple" ${A.terminal === 'simple' ? 'selected' : ''}>Last FCFF × (1 + g)</option></select></span></label>
              ${A.terminal === 'roic' ? field('roic', 'Terminal ROIC', '%', { tag: 'assumption' }) : ''}
              <label class="v-f"><span>Tax on losses</span><span class="v-in"><select data-k="lossTax"><option value="none" ${A.lossTax === 'none' ? 'selected' : ''}>No benefit</option><option value="symmetric" ${A.lossTax === 'symmetric' ? 'selected' : ''}>Benefit at the tax rate</option></select></span></label>
              ${field('debt', 'Debt', '$M', { step: 1, scale: 1e6 })}${field('cash', 'Cash + investments', '$M', { step: 1, scale: 1e6 })}${field('claims', 'Minority + preferred', '$M', { step: 1, scale: 1e6 })}${field('nonop', 'Other nonoperating assets', '$M', { step: 1, scale: 1e6 })}
            </div>
            <div class="v-actions"><button type="button" class="btn small" id="v-reset">Reset to the reported starting point</button><button type="button" class="btn small" id="v-export">Download scenario (JSON)</button></div>
            <p class="muted q-small">Defaults: growth from the last four quarters against the four before (capped at −20%…40%); margin, D&amp;A and capex as a share of trailing revenue; tax from trailing tax ÷ pretax income (capped at 35%). WACC 9%, terminal growth 2.5%, ROIC 15% and working capital 10% of each revenue increase are placeholders, not estimates.</p>
          </article>
          <div class="v-out"><article class="q-card"><h3>Model result</h3>${out}</article>${revCard}${consCard}${sens}</div>
        </div>`;
      bind();
    }
    // ---------- consensus, backed out: what each consensus price needs, and what the analysts' own estimates give ----------
    function consFigures() {
      const a = (CS && CS.analysts) || {}, per = (k) => (a.periods || []).find((p) => p.period === k) || {};
      const y0 = per('0y'), y1 = per('+1y'), sh = A.shares;
      const pick = [y1, y0].find((p) => p.rev && p.rev.avg > 0 && p.end && p.end > V.end);
      let growth = null, margin = null, span = null;
      if (pick) {
        span = (Date.parse(pick.end) - Date.parse(V.end)) / (365.25 * 864e5);
        if (span > 0.25) growth = Math.pow(pick.rev.avg / rev, 1 / span) - 1;
        if (pick.eps && pick.eps.avg != null && sh > 0 && A.tax < 100) margin = pick.eps.avg * sh / (1 - A.tax / 100) / pick.rev.avg;
      }
      return { a, pick, growth, margin, span };
    }
    function consPrices(price) {
      const out = [], a = (CS && CS.analysts) || {}, T = a.targets || {}, w = A.wacc / 100;
      const back = (v, d) => (v > 0 ? v / Math.pow(1 + w, Math.max(0, (Date.parse(d) - Date.now()) / (365.25 * 864e5))) : null);
      const in12 = new Date(Date.now() + 365.25 * 864e5).toISOString().slice(0, 10);
      if (price > 0) out.push({ label: 'Today’s price', note: px ? t(px.source) : 'entered', p: price, today: price });
      if (T.mean > 0) out.push({ label: 'Analysts’ mean target', note: `${T.n || '—'} analysts, 12 months`, p: T.mean, today: back(T.mean, in12), cls: 'an' });
      if (T.high > 0) out.push({ label: 'Analysts’ highest target', note: '12 months', p: T.high, today: back(T.high, in12), cls: 'an' });
      if (T.low > 0) out.push({ label: 'Analysts’ lowest target', note: '12 months', p: T.low, today: back(T.low, in12), cls: 'an' });
      const soon = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
      const pm = (CS.markets || []).filter((m) => !m.closed && m.implied_price && m.implied_price.median > 0 && m.end >= soon).sort((x2, y2) => String(x2.end).localeCompare(String(y2.end)));
      const m = pm.find((q) => q.kind === 'above') || pm[0];
      if (m) out.push({ label: 'Prediction market', note: `${m.source === 'kalshi' ? 'Kalshi' : 'Polymarket'} median for ${date(m.end)}`, p: m.implied_price.median, today: back(m.implied_price.median, m.end), cls: 'pm' });
      const o = (CS.ours || []).find((q) => q.horizon === 'next quarter') || (CS.ours || [])[0];
      if (o && o.price > 0) out.push({ label: 'Our model', note: `${t(o.horizon)} (${date(o.date)})`, p: o.price, today: back(o.price, o.date), cls: 'ours' });
      return out;
    }
    function consensusCard(x, price) {
      if (!CS) return CS === false ? '' : `<article class="q-card"><h3>Consensus, backed out</h3><p class="muted">Loading analysts’ estimates and prediction markets…</p></article>`;
      const F = consFigures(), rows = consPrices(price);
      if (!rows.length) return '';
      const BOUNDS = { growth: [-0.3, 0.8], margin: [-0.3, 0.95], wacc: [Math.max(A.g / 100 + 0.005, 0.02), 0.4] };
      const need = (param, target) => {
        const [lo, hi] = BOUNDS[param], s = FSA.solve(x, param, target, lo, hi);
        if (s.status === 'ok') return { v: s.value };
        if (s.status === 'none' && s.range) {
          const above = target > s.range[1] + target;       // range is model − target
          return { txt: param === 'wacc' ? (above ? `below ${pct(lo * 100, 0)}` : `above ${pct(hi * 100, 0)}`) : (above ? `above ${pct(hi * 100, 0)}` : `below ${pct(lo * 100, 0)}`) };
        }
        return { txt: s.status === 'multiple' ? 'two answers' : '—' };
      };
      const cell = (n, ref, higherIsMore) => {
        if (n.v == null) return `<td class="num muted">${n.txt}</td>`;
        const tone = ref == null ? '' : (higherIsMore ? n.v > ref + 0.005 : n.v < ref - 0.005) ? 'neg' : 'pos';
        return `<td class="num ${tone}">${pct(n.v * 100)}</td>`;
      };
      const body = rows.map((rw) => {
        const g = need('growth', rw.today), m = need('margin', rw.today), w = need('wacc', rw.today);
        return `<tr><td><span class="v-dot ${rw.cls || ''}"></span>${t(rw.label)}<br><span class="muted q-small">${rw.note}</span></td><td class="num">${usd(rw.p)}${rw.today !== rw.p ? `<br><span class="muted q-small">${usd(rw.today)} today</span>` : ''}</td>
          ${cell(g, F.growth, true)}${cell(m, F.margin, true)}${cell(w, null)}</tr>`;
      }).join('');
      let fwd = '';
      if (F.growth != null || F.margin != null) {
        const cp = consPath(A.growth / 100, F.margin != null ? F.margin : A.margin / 100);
        const xc = { ...x, growth: cp.growth, margin: F.margin != null ? Array(A.years).fill(F.margin) : cp.margin };
        const rc = FSA.dcf(xc), T = (F.a.targets || {});
        fwd = `<div class="v-cons"><div><small>Analysts’ revenue growth</small><strong>${F.growth != null ? pct(F.growth * 100) : '—'}</strong><span class="muted">a year, from ${money(rev)} to ${money(F.pick.rev.avg)} by ${date(F.pick.end)} (${F.pick.rev.numberOfAnalysts || '—'} analysts)</span></div>
            <div><small>EBIT margin in their EPS</small><strong>${F.margin != null ? pct(F.margin * 100) : '—'}</strong><span class="muted">EPS ${usd(F.pick.eps && F.pick.eps.avg)} × ${(A.shares / 1e6).toFixed(0)}M shares ÷ (1 − tax) ÷ revenue; net interest ignored</span></div>
            <div><small>Model value on their estimates</small><strong>${rc.ok ? usd(rc.perShare) : '—'}</strong><span class="muted">${T.mean > 0 && rc.ok ? `${rc.perShare >= T.mean ? 'above' : 'below'} their mean target ${usd(T.mean)} · ` : ''}year${cp.n > 1 ? 's 1–' + cp.n : ' 1'} at their growth, then yours (${pct(A.growth)}); their margin throughout; your WACC and terminal</span></div></div>
          <div class="v-actions">${A.cons ? '<button type="button" class="btn small" id="v-nocons">Back to one growth rate for every year</button>' : '<button type="button" class="btn small" id="v-usecons">Use the analysts’ estimates in the model</button>'}</div>`;
      }
      return `<article class="q-card"><h3>Consensus, backed out</h3>
          <p class="muted">What each consensus price needs from the model — one assumption at a time, the others as set: revenue growth or EBIT margin for every one of the ${A.years} forecast years, or the WACC that discounts your cash flows to that price. Prices in the future are discounted back to today at the WACC. Green: needs no more than the analysts’ own estimates; red: needs more.</p>
          <div class="tbl-wrap"><table class="v-table v-backout"><thead><tr><th>Consensus</th><th class="num">Price</th><th class="num">Growth needed</th><th class="num">Margin needed</th><th class="num">WACC</th></tr></thead><tbody>${body}</tbody></table></div>
          ${fwd}<p class="muted q-small">Analysts: Yahoo Finance consensus. Prediction markets: Polymarket / Kalshi. Our model: the Rotation forecast. All in the Consensus tab.</p></article>`;
    }
    function bind() {
      const uc = $('#v-usecons', box);
      if (uc) uc.addEventListener('click', () => {
        const F = consFigures();
        A.cons = F.growth != null;
        if (F.margin != null) A.margin = +(F.margin * 100).toFixed(1);
        render();
      });
      const nc = $('#v-nocons', box);
      if (nc) nc.addEventListener('click', () => { A.cons = false; render(); });
      $$('[data-k]', box).forEach((el) => el.addEventListener('change', () => {
        const k = el.dataset.k;
        A[k] = el.tagName === 'SELECT' ? el.value : (el.value === '' ? null : Number(el.value) * Number(el.dataset.scale || 1));
        render();
        const again = $(`[data-k="${k}"]`, box);
        if (again) again.focus();
      }));
      const sv = $('#v-solve', box);
      if (sv) sv.addEventListener('change', () => {
        A.solveFor = sv.value;
        [A.lo, A.hi] = { growth: [-20, 40], margin: [-20, 60], wacc: [Math.max(A.g + 0.5, 3), 25] }[sv.value];
        render();
      });
      $('#v-reset', box).addEventListener('click', () => { A = { ...defaults }; render(); });
      $('#v-export', box).addEventListener('click', () => {
        const scenario = { schema: 'filing-flows-valuation-1', company: P.name, cik: P.cik, ticker, created: new Date().toISOString(),
          starting_point: { basis: V.basis, end: V.end, revenue: rev, operating_income: oi, debt: V.debt, cash: V.cash_all, diluted_shares: sh, price: px },
          assumptions: A, result: FSA.dcf(model()) };
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(scenario, null, 2)], { type: 'application/json' }));
        a.download = `${(ticker || P.cik)}-dcf-scenario.json`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      });
    }
    render();
    fetch(`disclosures/data/consensus/c/${P.cik || c.cik}.json`).then((r) => (r.ok ? r.json() : false)).catch(() => false)
      .then((d) => { if (!here()) return; CS = d || false; if (box.isConnected) render(); });
  }

  // ---------- profit and cash: net income vs operating cash flow, accruals, reserve rollforwards ----------
  // Figures from pipeline/quality.py (SEC XBRL company facts). Definitions, waterfall and Crumb's transactions are
  // adapted from the Cash & Cookie Visual Lab prototype on the beta/fsa-chatgpt branch (created by ChatGPT (OpenAI)).
  const QM = {
    accrual: (p) => (p && p.ni != null && p.ocf != null ? p.ni - p.ocf : null),
    ratio(p) {
      const a = QM.accrual(p);
      return a != null && p.assets_open > 0 && p.assets_close > 0 ? a / ((p.assets_open + p.assets_close) / 2) : null;
    },
    conv: (p) => (p && p.ni > 0 && p.ocf != null ? p.ocf / p.ni : null),       // cash conversion: OCF ÷ net income
    transact(s, action, amount) {        // the teaching scenario: a liability provision expensed through profit, no tax
      if (!Number.isInteger(amount) || amount < 1 || amount > 100) throw Error('Choose a whole amount from 1 to 100.');
      if (action !== 'add' && amount > s.reserve) throw Error('Crumb cannot use or release more than the jar holds.');
      return { reserve: s.reserve + (action === 'add' ? amount : -amount),
        profit: s.profit + (action === 'add' ? -amount : action === 'release' ? amount : 0),
        cash: s.cash - (action === 'use' ? amount : 0) };
    },
  };
  function qTicks(lo, hi, n) {
    const span = hi - lo || 1, raw = span / (n || 4), mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const out = [], end = Math.ceil(hi / step - 1e-9) * step;
    for (let v = Math.floor(lo / step + 1e-9) * step; v <= end + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    return out;
  }
  function qAxis(vals, H, top, bottom) {           // y scale over the values and zero, with round gridlines
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const ticks = qTicks(lo, hi === lo ? lo + 1 : hi, 4), a = ticks[0], b = ticks[ticks.length - 1];
    return { ticks, y: (v) => top + (b - v) / (b - a || 1) * (H - top - bottom) };
  }
  function qGrid(ax, W, left) {
    return ax.ticks.map((v) => `<line class="${v === 0 ? 'q-zero' : 'q-gl'}" x1="${left}" x2="${W - 6}" y1="${ax.y(v).toFixed(1)}" y2="${ax.y(v).toFixed(1)}"/>
      <text class="q-tick" x="${left - 6}" y="${(ax.y(v) + 4).toFixed(1)}" text-anchor="end">${v === 0 ? '$0' : money(v).replace(/\.0(?=[BMK])/, '')}</text>`).join('');
  }
  const qm = (v) => (v === 0 ? '$0' : money(v));
  const qRect = (x, y0, y1, w, cls, tip) => `<rect class="${cls}" x="${x.toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${w.toFixed(1)}"
    height="${Math.max(1, Math.abs(y1 - y0)).toFixed(1)}" rx="2"><title>${t(tip)}</title></rect>`;

  function qualitySection(body, c, q, fy) {
    const D = c.quality;
    if (!D || !((D.q || []).length || (D.fy || []).length)) return;
    const P = c.profile || {};
    const financial = P.sector === 'financials' || /^6[0-7]/.test(String(P.sic || ''));
    const box = document.createElement('section');
    box.className = 'section quality';
    box.setAttribute('aria-labelledby', 'q-title');
    const st = { mode: fy && (D.fy || []).length ? 'fy' : (D.q || []).length ? 'q' : 'fy', end: q && q.end, fam: null, rEnd: null };
    const reserves = D.reserves || [];
    const fams = [...new Map(reserves.map((r) => [r.id, r.name])).entries()];
    st.fam = fams.length ? fams[0][0] : null;
    const list = () => (st.mode === 'fy' ? D.fy : D.q).slice(st.mode === 'fy' ? -5 : -8);
    const cur = () => { const L = list(); return L.find((p) => p.end === st.end) || L[L.length - 1]; };

    function compareChart(L, sel) {
      const W = 560, H = 230, left = 58, top = 14, bottom = 30;
      const ax = qAxis(L.flatMap((p) => [p.ni, p.ocf]).filter((v) => v != null), H, top, bottom);
      const step = (W - left - 8) / L.length, bw = Math.min(22, step * 0.32);
      let g = qGrid(ax, W, left);
      L.forEach((p, i) => {
        const x = left + i * step, mid = x + step / 2;
        if (p === sel) g += `<rect class="q-selcol" x="${(x + 2).toFixed(1)}" y="${top - 6}" width="${(step - 4).toFixed(1)}" height="${H - top - bottom + 10}" rx="6"/>`;
        if (p.ni != null) g += qRect(mid - bw - 1, ax.y(0), ax.y(p.ni), bw, 'q-ni', `${p.label} net income ${money(p.ni)}`);
        else g += `<text class="q-na" x="${(mid - bw / 2).toFixed(1)}" y="${(ax.y(0) - 6).toFixed(1)}" text-anchor="middle">n/a</text>`;
        if (p.ocf != null) g += qRect(mid + 1, ax.y(0), ax.y(p.ocf), bw, 'q-ocf', `${p.label} operating cash flow ${money(p.ocf)}`);
        else g += `<text class="q-na" x="${(mid + bw / 2).toFixed(1)}" y="${(ax.y(0) - 6).toFixed(1)}" text-anchor="middle">n/a</text>`;
        g += `<text class="q-x${p === sel ? ' on' : ''}" x="${mid.toFixed(1)}" y="${H - 10}" text-anchor="middle">${t(p.label)}</text>
          <rect class="q-hit" data-end="${t(p.end)}" x="${x.toFixed(1)}" y="0" width="${step.toFixed(1)}" height="${H}"><title>${t(p.label)}: select</title></rect>`;
      });
      return `<svg class="q-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Net income and operating cash flow by period">${g}</svg>`;
    }
    function accrualChart(L, sel) {
      const W = 560, H = 230, left = 58, top = 22, bottom = 30;
      const vals = L.map(QM.accrual);
      const ax = qAxis(vals.filter((v) => v != null), H, top, bottom);
      const step = (W - left - 8) / L.length, bw = Math.min(34, step * 0.5);
      let g = qGrid(ax, W, left);
      L.forEach((p, i) => {
        const x = left + i * step, mid = x + step / 2, v = vals[i], r = QM.ratio(p);
        if (p === sel) g += `<rect class="q-selcol" x="${(x + 2).toFixed(1)}" y="${top - 14}" width="${(step - 4).toFixed(1)}" height="${H - top - bottom + 18}" rx="6"/>`;
        if (v != null) {
          g += qRect(mid - bw / 2, ax.y(0), ax.y(v), bw, v >= 0 ? 'q-acc-pos' : 'q-acc-neg',
            `${p.label}: accruals ${money(v)}${r != null ? ` · ${(r * 100).toFixed(1)}% of average assets` : ''}`);
          if (r != null) g += `<text class="q-val" x="${mid.toFixed(1)}" y="${(v >= 0 ? ax.y(v) - 5 : ax.y(v) + 13).toFixed(1)}" text-anchor="middle">${sign(r)}${Math.abs(r * 100).toFixed(1)}%</text>`;
        } else g += `<text class="q-na" x="${mid.toFixed(1)}" y="${(ax.y(0) - 6).toFixed(1)}" text-anchor="middle">n/a</text>`;
        g += `<text class="q-x${p === sel ? ' on' : ''}" x="${mid.toFixed(1)}" y="${H - 10}" text-anchor="middle">${t(p.label)}</text>
          <rect class="q-hit" data-end="${t(p.end)}" x="${x.toFixed(1)}" y="0" width="${step.toFixed(1)}" height="${H}"><title>${t(p.label)}: select</title></rect>`;
      });
      return `<svg class="q-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Accruals (net income minus operating cash flow) by period">${g}</svg>`;
    }
    function waterfall(r) {
      const steps = [['Opening', 0, r.opening, 'w-bal', `Balance at ${date(r.start)}`]];
      let v = r.opening;
      const move = (label, d, cls, tip) => { if (d == null) return; steps.push([label, v, v + d, cls, tip]); v += d; };
      move('Added', r.additions, 'w-add', 'Charged to expense this year (new provisions)');
      move('Released', r.releases == null ? null : -r.releases, 'w-rel', r.release_in_income ? 'Estimates reversed: back to profit' : 'Reversed');
      move('Used', r.utilization == null ? null : -r.utilization, 'w-use', 'Paid out or written off: uses the reserve, no new expense');
      move('Other', r.other, 'w-oth', 'Currency, acquisitions, recoveries');
      if (!r.reconciled) move('Not tagged', r.diff, 'w-gap', 'Reported closing minus the tagged movements');
      steps.push(['Closing', 0, r.closing, 'w-bal', `Balance at ${date(r.end)}`]);
      const W = 640, H = 250, left = 58, top = 22, bottom = 30;
      const ax = qAxis(steps.flatMap((s) => [s[1], s[2]]), H, top, bottom);
      const step = (W - left - 8) / steps.length, bw = Math.min(56, step * 0.62);
      let g = qGrid(ax, W, left);
      steps.forEach(([label, a, b, cls, tip], i) => {
        const x = left + i * step + (step - bw) / 2, d = cls === 'w-bal' ? b : b - a;
        g += qRect(x, ax.y(a), ax.y(b), bw, cls, `${label}: ${money(d)} · ${tip}`);
        g += `<text class="q-val" x="${(x + bw / 2).toFixed(1)}" y="${(Math.min(ax.y(a), ax.y(b)) - 5).toFixed(1)}" text-anchor="middle">${cls === 'w-bal' ? qm(d) : (d > 0 ? '+' : '') + qm(d)}</text>
          <text class="q-x" x="${(x + bw / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle">${label}</text>`;
        if (i < steps.length - 1) g += `<line class="q-link" x1="${(x + bw).toFixed(1)}" x2="${(x + step).toFixed(1)}" y1="${ax.y(b).toFixed(1)}" y2="${ax.y(b).toFixed(1)}"/>`;
      });
      return `<svg class="q-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(r.name)} rollforward, ${t(r.label)}">${g}</svg>`;
    }
    function summary(p) {
      const a = QM.accrual(p), r = QM.ratio(p), pName = p.basis === 'pl' ? 'net income (including noncontrolling interests)' : 'net income';
      if (a == null) return `${t(p.label)}: ${p.ni == null ? 'no net income' : 'no operating cash flow'} figure tagged for this period.`;
      const gap = Math.abs(a), lead = a > 0 ? 'profit ran ahead of operating cash by' : a < 0 ? 'operating cash ran ahead of profit by' : 'profit and operating cash matched';
      return `${t(p.label)}: ${pName} ${money(p.ni)}, operating cash flow ${money(p.ocf)} — ${lead}${a ? ' ' + money(gap) : ''}${
        r != null ? ` (${sign(r)}${Math.abs(r * 100).toFixed(1)}% of average total assets)` : ''}.`;
    }
    function trailing() {
      const L = (D.q || []).slice(-4);
      if (st.mode !== 'q' || L.length < 4 || L.some((p) => p.ni == null || p.ocf == null)) return '';
      const ni = L.reduce((s, p) => s + p.ni, 0), ocf = L.reduce((s, p) => s + p.ocf, 0);
      return ` Last four quarters: net income ${money(ni)}, operating cash flow ${money(ocf)}${ni > 0 ? `, ${(ocf / ni).toFixed(2)}× cash conversion` : ''}.`;
    }
    const kpi = (label, val, note, cls) => `<div class="q-kpi"><small>${label}</small><strong class="${cls || ''}">${val}</strong>${note ? `<span>${note}</span>` : ''}</div>`;

    function render() {
      const L = list(), sel = cur(), a = QM.accrual(sel), r = QM.ratio(sel), cv = QM.conv(sel);
      const famRows = reserves.filter((x) => x.id === st.fam);
      const rr = famRows.find((x) => x.end === st.rEnd) || famRows[famRows.length - 1];
      box.innerHTML = `<div class="section-head"><h2 id="q-title">Profit and cash</h2>
          <span class="muted">Net income against operating cash flow, the accrual gap between them${reserves.length ? ', and where reserves went' : ''} · SEC XBRL company facts</span></div>
        <div class="q-bar">
          <div class="seg" role="group" aria-label="Period type">
            <button type="button" data-mode="q" class="${st.mode === 'q' ? 'on' : ''}" ${(D.q || []).length ? '' : 'disabled'}>Quarters</button>
            <button type="button" data-mode="fy" class="${st.mode === 'fy' ? 'on' : ''}" ${(D.fy || []).length ? '' : 'disabled'}>Fiscal years</button></div>
          <label class="q-pick">Period <select id="q-period">${L.map((p) => `<option value="${t(p.end)}" ${p === sel ? 'selected' : ''}>${t(p.label)}</option>`).join('')}</select></label>
        </div>
        <div class="q-kpis">
          ${kpi('Net income', evBtn(money(sel.ni), { title: 'Net income', value: money(sel.ni), period: sel.label, ref: (sel.ev || {}).ni }), sel.basis === 'pl' ? 'incl. noncontrolling interests' : '')}
          ${kpi('Operating cash flow', evBtn(money(sel.ocf), { title: 'Operating cash flow', value: money(sel.ocf), period: sel.label, ref: (sel.ev || {}).ocf }), '')}
          ${kpi('Accruals', a == null ? '—' : evBtn(money(a), { title: 'Accruals', value: money(a), period: sel.label, formula: `net income ${money(sel.ni)} − operating cash flow ${money(sel.ocf)}`,
            note: r == null ? '' : `Accrual ratio: accruals ÷ average total assets ((${money(sel.assets_open)} + ${money(sel.assets_close)}) ÷ 2).`,
            inputs: [{ title: 'Net income', value: money(sel.ni), ref: (sel.ev || {}).ni }, { title: 'Operating cash flow', value: money(sel.ocf), ref: (sel.ev || {}).ocf },
              ...(r == null ? [] : [{ title: 'Total assets, opening', value: money(sel.assets_open), ref: (sel.ev || {}).assets_open }, { title: 'Total assets, closing', value: money(sel.assets_close), ref: (sel.ev || {}).assets_close }])] }),
            'net income − operating cash flow', a == null ? '' : a > 0 ? 'q-warm' : 'q-cool')}
          ${kpi('Accrual ratio', r == null ? '—' : `${sign(r)}${Math.abs(r * 100).toFixed(1)}%`, r == null ? 'total assets not tagged' : 'of average total assets')}
          ${kpi('Cash conversion', cv == null ? '—' : `${cv < 0 ? '−' : ''}${Math.abs(cv).toFixed(2)}×`, cv == null ? (sel.ni != null && sel.ni <= 0 ? 'not meaningful at a loss' : '') : 'operating cash ÷ net income')}
        </div>
        <p class="q-sum">${summary(sel)}${trailing()}</p>
        ${financial ? '<p class="q-warn">For banks, insurers and brokers, operating cash flow includes lending, deposit and trading flows, so the gap between profit and cash says little about earnings quality here.</p>' : ''}
        <div class="q-grid">
          <article class="q-card"><h3>Profit vs operating cash</h3>
            <p class="muted">Same periods, same scale, a shared zero line. Select a period to read it above.</p>
            <div class="q-scroll">${compareChart(L, sel)}</div>
            <div class="q-legend"><span><i class="q-ni"></i>Net income</span><span><i class="q-ocf"></i>Operating cash flow</span></div></article>
          <article class="q-card"><h3>The accrual gap</h3>
            <p class="muted">Net income − operating cash flow; labels show it as a share of average total assets (for the period, not annualised).</p>
            <div class="q-scroll">${accrualChart(L, sel)}</div>
            <div class="q-legend"><span><i class="q-acc-pos"></i>Profit ahead of cash</span><span><i class="q-acc-neg"></i>Cash ahead of profit</span></div></article>
        </div>
        ${rr ? `<article class="q-card q-res"><div class="q-res-head"><h3>Where did the reserve go?</h3>
            <div class="q-bar">${fams.length > 1 ? `<div class="seg" role="group" aria-label="Reserve">${fams.map(([id, name]) => `<button type="button" data-fam="${t(id)}" class="${id === st.fam ? 'on' : ''}">${t(name.replace(/^Allowance for /, '').replace(/ reserve$/, '').replace(/^./, (x) => x.toUpperCase()))}</button>`).join('')}</div>` : ''}
            <label class="q-pick">Year <select id="q-ryear">${famRows.map((x) => `<option value="${t(x.end)}" ${x === rr ? 'selected' : ''}>${t(x.label)}</option>`).join('')}</select></label></div></div>
          <p class="muted"><b>${t(rr.name)}</b>: ${t(rr.what)}. Fiscal-year rollforward from the 10-K note.</p>
          <div class="q-scroll">${waterfall(rr)}</div>
          <div class="q-legend"><span><i class="w-add"></i>Charged to profit</span><span><i class="w-rel"></i>Released to profit</span><span><i class="w-use"></i>Used (paid or written off)</span><span><i class="w-oth"></i>Other</span>${rr.reconciled ? '' : '<span><i class="w-gap"></i>Not tagged</span>'}</div>
          <p class="q-sum">Opening ${qm(rr.opening)} + added ${qm(rr.additions)} − released ${qm(rr.releases)} − used ${qm(rr.utilization)}${rr.other != null ? ` ${rr.other < 0 ? '−' : '+'} other ${qm(Math.abs(rr.other))}` : ''} = ${qm(rr.calc)}; reported closing ${qm(rr.closing)}.
            ${rr.reconciled ? '<span class="pos">Reconciles.</span>' : `<span class="q-warmtext">${money(rr.diff)} the filing’s tags do not explain</span> (movements tagged elsewhere or not at all, such as acquisitions).`}
            ${rr.releases ? ` Released to profit: ${money(rr.releases)}${rr.opening > 0 ? `, ${(rr.releases / rr.opening * 100).toFixed(0)}% of the opening balance` : ''}.` : ''}</p>
          <p class="muted q-small">Tags: ${Object.entries(rr.tags).map(([k, v]) => `${k} <span class="mono">${t([].concat(v).join(' + '))}</span>`).join(' · ')}</p>
          ${signalsHTML(famRows, rr)}
        </article>` : ''}
        <details class="q-card q-crumb"><summary><b>What is a “cookie jar” reserve?</b> <span class="muted">Try it with Crumb, a reserve jar (made-up numbers)</span></summary>
          <div class="crumb">
            <div class="crumb-stage"><svg class="crumb-pet" id="crumb-pet" viewBox="0 0 160 190" role="img" aria-label="Crumb the reserve jar">
              <rect class="crumb-lid" x="26" y="8" width="108" height="20" rx="8"/>
              <path class="crumb-jar" d="M30 30 h100 v6 q14 10 14 34 v78 q0 30 -30 30 h-68 q-30 0 -30 -30 v-78 q0 -24 14 -34z"/>
              <g id="crumb-cookies"></g>
              <g class="crumb-face"><rect x="44" y="58" width="72" height="34" rx="17"/><circle cx="64" cy="72" r="4"/><circle cx="96" cy="72" r="4"/><path d="M72 80 q8 7 16 0" fill="none"/></g>
            </svg>
            <div class="crumb-bal"><span class="eyebrow">Reserve balance</span><strong id="crumb-bal">50</strong><span class="muted">made-up units · not cash</span></div></div>
            <div class="crumb-side">
              <div class="crumb-meters" id="crumb-meters"></div>
              <div class="crumb-actions"><label>Amount <input id="crumb-amt" type="number" value="10" min="1" max="100" step="1"></label>
                <button class="btn" type="button" data-crumb="add">+ Record a provision</button>
                <button class="btn" type="button" data-crumb="use">− Settle in cash</button>
                <button class="btn" type="button" data-crumb="release">− Reverse an estimate</button>
                <button class="btn small" type="button" id="crumb-reset">Reset</button>
                <button class="btn small" type="button" id="crumb-motion" aria-pressed="false">Pause animation</button></div>
              <p class="crumb-say" id="crumb-say" role="status" aria-live="polite"></p>
            </div>
          </div>
          <p class="muted q-small">“Cookie jar” accounting means building reserves too large in good years and releasing them later to smooth reported profit. A release or an ordinary settlement is not evidence of that by itself: judging whether a reserve was excessive needs the notes, the assumptions and the business context. Simplified scenario: a liability provision expensed through profit; no taxes or discounting.</p>
        </details>
        <p class="muted q-small">Accruals here are the cash-flow measure (net income − operating cash flow), a screening figure, not a verdict: growth, seasonality, working capital and non-cash items all move it. Figures are read automatically from XBRL; check the filing before relying on one.</p>`;
      bind();
      crumbDraw(false);
    }
    // Crumb: the reserve jar (made-up units, independent of the company's figures)
    let pet = { reserve: 50, profit: 100, cash: 100 }, paused = false;
    const SAY = {
      add: 'Provision recorded: an expense, so pretax profit falls and my jar fills up. No cash moves yet.',
      use: 'Obligation settled: cash goes out and the jar empties by the same amount. No new expense — it was charged when recorded.',
      release: 'Estimate reversed: the jar shrinks and pretax profit rises, with no cash at all. Worth asking what evidence supports the revision.',
    };
    function crumbDraw(prev) {
      const g = $('#crumb-cookies', box), bal = $('#crumb-bal', box), m = $('#crumb-meters', box);
      if (!g) return;
      const n = Math.min(15, Math.ceil(pet.reserve / 10));
      g.innerHTML = Array.from({ length: n }, (_, i) => `<g class="crumb-cookie" style="--d:${i * 30}ms"><circle cx="${42 + (i % 4) * 25 + (Math.floor(i / 4) % 2) * 12}" cy="${164 - Math.floor(i / 4) * 22}" r="11"/>
        <circle class="chip" cx="${39 + (i % 4) * 25 + (Math.floor(i / 4) % 2) * 12}" cy="${161 - Math.floor(i / 4) * 22}" r="1.8"/><circle class="chip" cx="${46 + (i % 4) * 25 + (Math.floor(i / 4) % 2) * 12}" cy="${167 - Math.floor(i / 4) * 22}" r="1.6"/></g>`).join('');
      bal.textContent = pet.reserve;
      $('#crumb-pet', box).setAttribute('aria-label', `Crumb the reserve jar: ${pet.reserve} units (cookies are decoration, capped at 15; the number is the balance)`);
      const row = (k, label, v, max) => {
        const d = prev ? v - prev[k] : 0;
        return `<div class="crumb-m"><span>${label}</span><div class="crumb-track"><div class="crumb-fill ${k}" style="width:${Math.max(0, Math.min(100, v / max * 100)).toFixed(1)}%"></div></div>
          <b>${v}</b><em class="${d ? 'show ' + (d > 0 ? 'up' : 'down') : ''}">${d ? (d > 0 ? '+' : '−') + Math.abs(d) : ''}</em></div>`;
      };
      m.innerHTML = row('reserve', 'Reserve', pet.reserve, 200) + row('profit', 'Pretax profit', pet.profit, 200) + row('cash', 'Cash', pet.cash, 200);
    }
    function crumbAct(action) {
      const prev = pet;
      try {
        pet = QM.transact(pet, action, Number($('#crumb-amt', box).value));
        $('#crumb-say', box).textContent = SAY[action];
        crumbDraw(prev);
        const el = $('#crumb-pet', box);
        if (!paused) { el.classList.remove('react'); void el.getBoundingClientRect(); el.classList.add('react'); }
      } catch (e) { $('#crumb-say', box).textContent = e.message; }
    }
    // the reserve across fiscal years, with the cookie-jar screens of web/fsa.js FSA.reserveTrend
    function signalsHTML(rows, cur) {
      const T = FSA.reserveTrend(rows, D.fy), F0 = FSA.RESERVE_FLAGS;
      if (T.length < 2) return '';
      const p1 = (v) => (v == null ? '—' : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`);
      const x2 = (v) => (v == null ? '—' : `${v.toFixed(2)}×`);
      const flagText = (f) => (f.kind === 'release' ? `Released ${p1(f.value)} of net income`
        : f.kind === 'drop' ? `${p1(f.from)} → ${p1(f.value)} of revenue`
          : `Charged ${x2(f.value)} of what was used`);
      const n = T.filter((x) => x.flags.length).length, isLoans = rows[0] && rows[0].id === 'loans';
      return `<h4 class="rs-h">Across the years</h4>
        <div class="tbl-wrap"><table class="cq-table rs-table"><thead><tr><th>Year</th><th class="num">Balance</th><th class="num">% of revenue</th><th class="num">Charged</th>
          <th class="num">Released</th><th class="num">Released ÷ net income</th><th class="num">Used</th><th class="num">Charged ÷ used</th><th>Screens</th></tr></thead>
        <tbody>${T.slice().reverse().map((x) => `<tr class="${x.flags.length ? 'flagged' : ''}${x.end === cur.end ? ' on' : ''}"><td>${t(x.label)}</td>
          <td class="num">${qm(x.closing)}</td><td class="num">${p1(x.ratio)}</td><td class="num">${x.additions == null ? '—' : qm(x.additions)}</td>
          <td class="num">${x.releases == null ? '—' : qm(x.releases)}</td><td class="num">${p1(x.relNi)}</td><td class="num">${x.utilization == null ? '—' : qm(x.utilization)}</td>
          <td class="num">${x2(x.cover)}</td><td class="flagcell">${x.flags.length ? x.flags.map((f) => `<span class="rs-flag">${flagText(f)}</span>`).join('') : '<span class="muted">—</span>'}</td></tr>`).join('')}</tbody></table></div>
        <p class="q-sum">${n ? `<span class="q-warmtext">Screens flag ${n} of ${T.length} years</span>: read the note for what changed in the estimates.` : `No screens flag the ${T.length} years shown.`}</p>
        <p class="muted q-small">Screens, not verdicts. Flagged when estimates released back to profit reach ${Math.round(F0.release * 100)}% of net income, when the balance
          falls by ${Math.round(F0.drop * 100)}% or more as a share of revenue in a year, or when less is charged than used (under ${F0.under}×) while the balance shrinks.
          ${isLoans ? 'Loan allowances follow the loan book, not sales, so no share of revenue is shown. ' : ''}Lower claims, a smaller business or a sale can explain each one.</p>`;
    }
    function bind() {
      $$('.q-scroll', box).forEach((el) => { el.scrollLeft = el.scrollWidth; });   // phones: start at the latest period
      $$('[data-mode]', box).forEach((b) => b.addEventListener('click', () => { st.mode = b.dataset.mode; render(); }));
      $$('.q-hit', box).forEach((r) => r.addEventListener('click', () => { st.end = r.dataset.end; render(); }));
      const ps = $('#q-period', box);
      if (ps) ps.addEventListener('change', () => { st.end = ps.value; render(); });
      $$('[data-fam]', box).forEach((b) => b.addEventListener('click', () => { st.fam = b.dataset.fam; st.rEnd = null; render(); }));
      const ry = $('#q-ryear', box);
      if (ry) ry.addEventListener('change', () => { st.rEnd = ry.value; render(); });
      const det = $('.q-crumb', box);
      if (det) {
        det.open = !!st.crumbOpen;
        det.addEventListener('toggle', () => { st.crumbOpen = det.open; });
        $$('[data-crumb]', det).forEach((b) => b.addEventListener('click', () => crumbAct(b.dataset.crumb)));
        $('#crumb-reset', det).addEventListener('click', () => { pet = { reserve: 50, profit: 100, cash: 100 }; crumbDraw(false); $('#crumb-say', det).textContent = 'Hi, I’m Crumb. My jar holds reserves, not cash. Try recording a provision.'; });
        const mo = $('#crumb-motion', det);
        mo.setAttribute('aria-pressed', String(paused)); mo.textContent = paused ? 'Resume animation' : 'Pause animation';
        det.classList.toggle('still', paused);
        mo.addEventListener('click', () => { paused = !paused; det.classList.toggle('still', paused); mo.setAttribute('aria-pressed', String(paused)); mo.textContent = paused ? 'Resume animation' : 'Pause animation'; });
        if (!$('#crumb-say', det).textContent) $('#crumb-say', det).textContent = 'Hi, I’m Crumb. My jar holds reserves, not cash. Try recording a provision.';
      }
    }
    render();
    body.appendChild(box);
  }

  // ---------- avatars: Congress portraits and the owner's pictures (disclosures/data/avatars.json, disclosures/automation/avatars.py);
  // anyone without one gets initials. Name keys match avatars.py person_key / org_key.
  let avLoad = null;
  const avData = () => avLoad || (avLoad = fetch('disclosures/data/avatars.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
  const AV_SKIP = new Set(['hon', 'honorable', 'dr', 'mr', 'mrs', 'ms', 'rep', 'sen', 'senator', 'representative', 'the', 'jr', 'sr', 'ii', 'iii', 'iv', 'md', 'phd', 'esq', 'cpa']);
  const avAscii = (x) => String(x || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
  function avKey(name) {
    let s = avAscii(name);
    if ((s.match(/,/g) || []).length === 1 && !/,\s*(jr|sr|ii|iii|iv)\b/.test(s)) { const [l, f] = s.split(','); s = f + ' ' + l; }
    const w = s.split(/[^a-z]+/).filter((x) => x && x.length > 1 && !AV_SKIP.has(x));
    return !w.length ? '' : w.length === 1 ? w[0] : w[0] + ' ' + w[w.length - 1];
  }
  const avOrg = (name) => avAscii(name).split(/[^a-z0-9]+/).filter(Boolean).join(' ');
  function avatar(av, name, cik) {
    av = av || {};
    const M = av.managers || {}, byName = (av.manager_names || {})[avOrg(name)];
    const img = ((cik != null && M[String(+cik)]) || (byName && M[byName]) || (av.people || {})[avKey(name)] || {}).image;
    const w = String(name || '?').replace(/[^A-Za-z0-9 ]+/g, ' ').trim().split(/\s+/).filter((x) => !/^(inc|llc|lp|ltd|co|corp|the|of|and|mr|mrs|ms|hon|dr)$/i.test(x));
    const ini = ((w[0] || '?')[0] + (w.length > 1 ? w[w.length - 1][0] : '')).toUpperCase();
    let hsh = 0;
    for (const ch of String(name || '')) hsh = (hsh * 31 + ch.charCodeAt(0)) % 360;
    const src = img ? (/^https:\/\//.test(img) ? img : 'disclosures/' + img) : '';
    return `<span class="av" style="--av-h:${hsh}" data-i="${t(ini)}" aria-hidden="true">${src ? `<img class="av-img" src="${t(src)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}</span>`;
  }
  document.addEventListener('error', (e) => { if (e.target && e.target.classList && e.target.classList.contains('av-img')) e.target.remove(); }, true);

  // ---------- who bought it: a donut of the 13F managers who bought in the latest quarter on file (by dollars bought), and
  // how every filer moved (new · added · unchanged · cut · sold out). From holders/<TICKER>.json (stage-public.py).
  function buyersPie(inst, exits, sym, av, selectedPeriod) {
    const per = {};
    inst.filter((x) => x.status !== 'BASE').forEach((x) => { per[x.period] = (per[x.period] || 0) + 1; });
    const top = Math.max(0, ...Object.values(per));
    const P = selectedPeriod || Object.keys(per).sort().reverse().find((k) => per[k] >= top * 0.5);
    if (!P) return '';
    const rows = inst.filter((x) => x.period === P), gone = (exits || []).filter((x) => x.period === P);
    const px = (x) => (x.shares ? (x.value_usd || 0) / x.shares : 0);
    const buys = rows.filter((x) => x.status === 'NEW' || x.status === 'INCREASE').map((x) => ({ ...x, usd: Math.max(0, x.delta_shares || 0) * px(x) }))
      .filter((x) => x.usd > 0).sort((a, b) => b.usd - a.usd);
    const n = { NEW: 0, INCREASE: 0, UNCHANGED: 0, DECREASE: 0, EXIT: gone.length };
    rows.forEach((x) => { if (n[x.status] != null) n[x.status]++; });
    const filers = n.NEW + n.INCREASE + n.UNCHANGED + n.DECREASE + n.EXIT;
    if (!buys.length || filers < 2) return selectedPeriod ? `<p class="muted">No comparable 13F buyers for ${t(sym)} in the selected quarter (${t(selectedPeriod)}). Other quarters may have better coverage.</p>` : '';
    const total = buys.reduce((a, x) => a + x.usd, 0), SL = 6;
    const slices = buys.slice(0, SL).map((x, i) => ({ label: x.manager, cik: x.cik, usd: x.usd, cls: `s${i + 1}`, isNew: x.status === 'NEW' }));
    if (buys.length > SL) slices.push({ label: `${buys.length - SL} other buyer${buys.length - SL === 1 ? '' : 's'}`, usd: buys.slice(SL).reduce((a, x) => a + x.usd, 0), cls: 'so', other: true });
    const R = 70, r0 = 44, C = 80;
    let a0 = -Math.PI / 2, arcs = '';
    const pt = (rad, a) => `${(C + rad * Math.cos(a)).toFixed(2)},${(C + rad * Math.sin(a)).toFixed(2)}`;
    for (const sl of slices) {
      const f = sl.usd / total, a1 = a0 + f * 2 * Math.PI, big = a1 - a0 > Math.PI ? 1 : 0;
      const d = f >= 0.9999 ? `M${pt(R, -Math.PI / 2)}A${R},${R} 0 1 1 ${pt(R, Math.PI * 1.4999)}A${R},${R} 0 1 1 ${pt(R, -Math.PI / 2)}M${pt(r0, -Math.PI / 2)}A${r0},${r0} 0 1 0 ${pt(r0, Math.PI * 1.4999)}A${r0},${r0} 0 1 0 ${pt(r0, -Math.PI / 2)}Z`
        : `M${pt(R, a0)}A${R},${R} 0 ${big} 1 ${pt(R, a1)}L${pt(r0, a1)}A${r0},${r0} 0 ${big} 0 ${pt(r0, a0)}Z`;
      arcs += `<path class="${sl.cls}" d="${d}" fill-rule="evenodd"><title>${t(sl.label)}: bought ≈ ${money(sl.usd)} (${(f * 100).toFixed(1)}% of all 13F buying)${sl.isNew ? ' · new position' : ''}</title></path>`;
      a0 = a1;
    }
    const svg = `<svg class="pie13-svg" viewBox="0 0 160 160" role="img" aria-label="Share of 13F buying in ${t(sym)}, ${t(P)}">${arcs}
      <text x="80" y="76" text-anchor="middle" class="pie13-big">${money(total).replace(/\.\d+/, '')}</text><text x="80" y="94" text-anchor="middle" class="pie13-small">bought by ${buys.length}</text></svg>`;
    const legend = slices.map((sl) => `<li><i class="${sl.cls}"></i>${sl.other ? '<span class="av av-none"></span>' : avatar(av, sl.label, sl.cik)}<span class="pie13-name">${t(sl.label)}${sl.isNew ? ' <span class="badge">new</span>' : ''}</span>
      <span class="num">${money(sl.usd)}</span><span class="num muted">${(sl.usd / total * 100).toFixed(1)}%</span></li>`).join('');
    const seg = [['NEW', 'new position', 'bn'], ['INCREASE', 'added', 'ba'], ['UNCHANGED', 'unchanged', 'bu'], ['DECREASE', 'cut', 'bc'], ['EXIT', 'sold out', 'bx']];
    const bar = seg.filter(([k]) => n[k]).map(([k, l, c]) => `<i class="${c}" style="flex:${n[k]}" title="${n[k]} ${l} (${(n[k] / filers * 100).toFixed(0)}% of ${filers} filers)"></i>`).join('');
    const bought = n.NEW + n.INCREASE;
    return `<div class="pie13"><h3>Who bought it (13F, quarter ended ${date(P)})</h3>
      <p class="muted">Of the ${filers} processed 13F filers with ${t(sym)} in this quarter's report or the one before, ${bought} bought (${(bought / filers * 100).toFixed(0)}%; ${n.NEW} new positions), ${n.DECREASE} cut, ${n.EXIT} sold out and ${n.UNCHANGED} held still. Dollars bought ≈ shares added × the quarter-end price each filer reported; the slices are the largest buyers.</p>
      <div class="pie13-row">${svg}<ol class="pie13-legend">${legend}</ol></div>
      <div class="pie13-bar" role="img" aria-label="${seg.filter(([k]) => n[k]).map(([k, l]) => `${n[k]} ${l}`).join(', ')}">${bar}</div>
      <div class="pie13-key">${seg.map(([k, l, c]) => `<span><i class="${c}"></i>${l} <b>${n[k]}</b></span>`).join('')}</div></div>`;
  }

  // ---------- 13F buying and selling beyond the donut: the same quarter as "Who bought it", seen four more ways ----------
  // flows13: per filer what it bought or sold in the latest well-filed quarter (dollars ≈ shares × each filer's own
  // quarter-end price), and the share bridge prior holdings → new / added / cut / sold out → holdings now.
  function flows13(inst, exits, selectedPeriod) {
    const per = {};
    inst.filter((x) => x.status !== 'BASE').forEach((x) => { per[x.period] = (per[x.period] || 0) + 1; });
    const top = Math.max(0, ...Object.values(per));
    const P = selectedPeriod || Object.keys(per).sort().reverse().find((k) => per[k] >= top * 0.5);
    if (!P) return null;
    const rows = inst.filter((x) => x.period === P && x.status !== 'BASE'), gone = (exits || []).filter((x) => x.period === P);
    const px = (x) => (x.shares ? (x.value_usd || 0) / x.shares : 0);
    const buys = rows.filter((x) => (x.status === 'NEW' || x.status === 'INCREASE') && (x.delta_shares || 0) > 0)
      .map((x) => ({ manager: x.manager, cik: x.cik, status: x.status, sh: x.delta_shares, usd: x.delta_shares * px(x) })).sort((a, b) => b.usd - a.usd);
    const sells = rows.filter((x) => x.status === 'DECREASE' && (x.delta_shares || 0) < 0)
      .map((x) => ({ manager: x.manager, cik: x.cik, status: 'DECREASE', sh: -x.delta_shares, usd: -x.delta_shares * px(x) }))
      .concat(gone.filter((x) => x.prior_shares > 0).map((x) => ({ manager: x.manager, cik: x.cik, status: 'EXIT', sh: x.prior_shares, usd: x.prior_value_usd || 0 })))
      .sort((a, b) => b.usd - a.usd);
    const sum = (a, f) => a.reduce((s, x) => s + (f(x) || 0), 0);
    const nowSh = sum(rows, (x) => x.shares), newSh = sum(buys.filter((x) => x.status === 'NEW'), (x) => x.sh), addSh = sum(buys.filter((x) => x.status === 'INCREASE'), (x) => x.sh);
    const cutSh = sum(sells.filter((x) => x.status === 'DECREASE'), (x) => x.sh), exitSh = sum(sells.filter((x) => x.status === 'EXIT'), (x) => x.sh);
    const priceAll = nowSh ? sum(rows, (x) => x.value_usd) / nowSh : 0;
    return { P, rows, buys, sells, filers: rows.length + gone.length, priceAll,
      bridge: { prior: nowSh - newSh - addSh + cutSh + exitSh, newSh, addSh, cutSh, exitSh, now: nowSh },
      bought: sum(buys, (x) => x.usd), sold: sum(sells, (x) => x.usd) };
  }
  const SHORT_NAME = (s, n) => { const x = String(s || ''); return x.length > n ? x.slice(0, n - 1) + '…' : x; };
  const STATUS13 = { NEW: ['bn', 'new position'], INCREASE: ['ba', 'added'], DECREASE: ['bc', 'cut'], EXIT: ['bx', 'sold out'] };
  const megaSh = (v) => { const a = Math.abs(v); return (a >= 1e9 ? (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : Math.round(a).toString()); };

  // 1 · buyers and sellers side by side, on one scale
  function butterfly13(f, sym, av) {
    if (!f.buys.length && !f.sells.length) return '';
    const N = 8, max = Math.max(f.buys[0] ? f.buys[0].usd : 0, f.sells[0] ? f.sells[0].usd : 0) || 1;
    const side = (list, total, word) => {
      const rows = list.slice(0, N).map((x) => {
        const [c, l] = STATUS13[x.status];
        return `<li title="${t(x.manager)}: ${t(l)}, ${megaSh(x.sh)} shares ≈ ${money(x.usd)}"><span class="bf13-name">${avatar(av, x.manager, x.cik)}<span>${t(SHORT_NAME(x.manager, 34))}</span>${x.status === 'NEW' ? ' <span class="badge">new</span>' : x.status === 'EXIT' ? ' <span class="badge">sold out</span>' : ''}</span>
          <span class="num">${money(x.usd)}</span><i class="bf13-bar ${c}" style="width:${Math.max(1.5, x.usd / max * 100).toFixed(1)}%"></i></li>`;
      }).join('');
      const rest = list.slice(N), more = rest.length ? `<li class="bf13-more muted">+ ${rest.length} more ${word === 'Bought' ? 'buyer' : 'seller'}${rest.length === 1 ? '' : 's'} · ${money(rest.reduce((a, x) => a + x.usd, 0))}</li>` : '';
      return `<div class="bf13-side"><div class="bf13-h">${word} <b>${money(total)}</b> <span class="muted">· ${list.length} manager${list.length === 1 ? '' : 's'}</span></div><ol>${rows || '<li class="muted">None</li>'}${more}</ol></div>`;
    };
    return `<h3>Buyers and sellers (13F, quarter ended ${date(f.P)})</h3>
      <p class="muted">The largest sellers on the left, the largest buyers on the right, on one scale: dollars ≈ shares added or sold × the quarter-end price each filer reported (sold out: the value it reported a quarter earlier). Net: <b class="${f.bought >= f.sold ? 'pos' : 'neg'}">${f.bought >= f.sold ? '+' : '−'}${money(Math.abs(f.bought - f.sold))}</b>.</p>
      <div class="bf13">${side(f.sells, f.sold, 'Sold')}${side(f.buys, f.bought, 'Bought')}</div>`;
  }

  // 2 · the share bridge: holdings a quarter earlier → new / added / cut / sold out → holdings now
  function bridge13(f, sym) {
    const b = f.bridge;
    if (!(b.prior > 0 || b.now > 0)) return '';
    const steps = [['prior', 'A quarter earlier', b.prior, 'bu'], ['new', 'New positions', b.newSh, 'bn'], ['add', 'Added', b.addSh, 'ba'],
      ['cut', 'Cut', -b.cutSh, 'bc'], ['exit', 'Sold out', -b.exitSh, 'bx'], ['now', `Quarter ended ${date(f.P).replace(/,? \d{4}$/, '')}`, b.now, 'bu']];
    let run = 0;
    const bars = steps.map(([k, l, v, c]) => {
      if (k === 'prior' || k === 'now') { run = v; return { k, l, v, c, y0: 0, y1: v, total: true }; }
      const y0 = run; run += v; return { k, l, v, c, y0, y1: run };
    });
    const hi = Math.max(...bars.map((x) => Math.max(x.y0, x.y1))), loMove = Math.min(...bars.filter((x) => !x.total).map((x) => Math.min(x.y0, x.y1)), b.prior, b.now);
    const span = hi - loMove || hi || 1, base = Math.max(0, loMove - span * 1.2);   // a broken axis when the moves are small next to the totals
    const W = 640, H = 230, top = 26, bot = 40, bw = 64, gap = (W - bars.length * bw) / (bars.length + 1);
    const Y = (v) => top + (H - top - bot) * (1 - (v - base) / (hi - base || 1));
    const out = bars.map((x, i) => {
      const xl = gap + i * (bw + gap), ya = Y(Math.max(x.y0, x.y1)), yb = x.total ? H - bot : Y(Math.min(x.y0, x.y1));
      const lab = x.total ? megaSh(x.v) : (x.v >= 0 ? '+' : '−') + megaSh(x.v);
      const tip = `${x.l}: ${x.total ? '' : x.v >= 0 ? '+' : '−'}${whole(Math.abs(x.v))} shares${f.priceAll ? ` (≈ ${money(Math.abs(x.v) * f.priceAll)})` : ''}`;
      const brk = x.total && base > 0 ? `<path class="br13-break" d="M${xl - 3},${H - bot - 14} l${bw / 4 + 3},-6 l${bw / 4},6 l${bw / 4},-6 l${bw / 4 + 3},6"/>` : '';
      return `<g><rect class="${x.c}" x="${xl.toFixed(1)}" y="${ya.toFixed(1)}" width="${bw}" height="${Math.max(1.5, yb - ya).toFixed(1)}" rx="3"><title>${t(tip)}</title></rect>${brk}
        <text class="br13-v" x="${(xl + bw / 2).toFixed(1)}" y="${(ya - 7).toFixed(1)}" text-anchor="middle">${lab}</text>
        <text class="br13-l" x="${(xl + bw / 2).toFixed(1)}" y="${H - bot + 16}" text-anchor="middle">${t(x.l.split(' ').slice(0, 2).join(' '))}</text>
        <text class="br13-l" x="${(xl + bw / 2).toFixed(1)}" y="${H - bot + 30}" text-anchor="middle">${t(x.l.split(' ').slice(2).join(' '))}</text></g>`;
    }).join('');
    const net = b.now - b.prior;
    return `<h3>Where the shares went (13F, quarter ended ${date(f.P)})</h3>
      <p class="muted">Shares of ${t(sym)} held by the ${f.filers} processed filers that reported it this quarter or the one before: a quarter earlier, then what new positions and additions brought and what cuts and exits took away. Net <b class="${net >= 0 ? 'pos' : 'neg'}">${net >= 0 ? '+' : '−'}${megaSh(net)} shares</b>${b.prior ? ` (${pct(net / b.prior * 100, 1)})` : ''}.${base > 0 ? ` The axis starts at ${megaSh(base)} shares (zigzag) so the changes show next to the totals.` : ''}</p>
      <svg class="br13" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(`Share bridge for ${sym}: ${steps.map((x) => `${x[1]} ${megaSh(x[2])}`).join(', ')}`)}"><line class="br13-axis" x1="0" x2="${W}" y1="${H - bot}" y2="${H - bot}"/>${out}</svg>`;
  }

  // 3 · a flow (Sankey): sellers → the stock → buyers, band width = dollars
  function sankey13(f, sym) {
    if (!f.buys.length && !f.sells.length) return '';
    const K6 = 6, group = (list, word) => {
      const g = list.slice(0, K6).map((x) => ({ ...x }));
      if (list.length > K6) g.push({ manager: `${list.length - K6} other ${word}${list.length - K6 === 1 ? '' : 's'}`, usd: list.slice(K6).reduce((a, x) => a + x.usd, 0), status: 'OTHER' });
      return g.filter((x) => x.usd > 0);
    };
    const L = group(f.sells, 'seller'), R = group(f.buys, 'buyer');
    const W = 680, gapN = 6, slot = 30, xl = 178, xr = 494, cx0 = 318, cx1 = 354, nw = 9, cy = 12;
    const K = 260 / Math.max(f.sold, f.bought, 1), cH = Math.max(f.sold, f.bought) * K;   // the stock's node: 260 px for the larger side
    const cls = (x) => (x.status === 'OTHER' ? 'bu' : STATUS13[x.status][0]);
    let yL = cy, yR = cy, cL = cy, cR = cy, out = '';
    const band = (x0, a0, a1, x1, b0, b1, c, tip) => `<path class="sk13-band ${c}" d="M${x0},${a0.toFixed(1)} C${(x0 + x1) / 2},${a0.toFixed(1)} ${(x0 + x1) / 2},${b0.toFixed(1)} ${x1},${b0.toFixed(1)} L${x1},${b1.toFixed(1)} C${(x0 + x1) / 2},${b1.toFixed(1)} ${(x0 + x1) / 2},${a1.toFixed(1)} ${x0},${a1.toFixed(1)} Z"><title>${t(tip)}</title></path>`;
    // each manager's node is as tall as its dollars, but its slot is at least `slot` px so the two label lines never collide
    const node = (x, y, h, left) => {
      const c = cls(x), ly = y + Math.max(h, slot) / 2, tx = left ? xl - 6 : xr + nw + 6, anchor = left ? ' text-anchor="end"' : '';
      const tail = x.status === 'EXIT' ? ' · sold out' : x.status === 'NEW' ? ' · new' : '';
      return `<rect class="${c}" x="${left ? xl : xr}" y="${y.toFixed(1)}" width="${nw}" height="${h.toFixed(1)}" rx="2"/>
        <text class="sk13-l" x="${tx}" y="${(ly - 2).toFixed(1)}"${anchor}>${t(SHORT_NAME(x.manager, 24))}</text>
        <text class="sk13-v" x="${tx}" y="${(ly + 11).toFixed(1)}"${anchor}>${money(x.usd)}${tail}</text>`;
    };
    for (const x of L) {
      const h = Math.max(1.5, x.usd * K);
      out += band(xl + nw, yL, yL + h, cx0, cL, cL + h, cls(x), `${x.manager}: sold ≈ ${money(x.usd)}`) + node(x, yL, h, true);
      yL += Math.max(h, slot) + gapN; cL += h;
    }
    for (const x of R) {
      const h = Math.max(1.5, x.usd * K);
      out += band(cx1, cR, cR + h, xr, yR, yR + h, cls(x), `${x.manager}: bought ≈ ${money(x.usd)}`) + node(x, yR, h, false);
      yR += Math.max(h, slot) + gapN; cR += h;
    }
    out += `<rect class="sk13-mid" x="${cx0}" y="${cy}" width="${cx1 - cx0}" height="${Math.max(2, cH).toFixed(1)}" rx="3"/>
      <text class="sk13-sym" x="${(cx0 + cx1) / 2}" y="${(cy + cH + 16).toFixed(1)}" text-anchor="middle">${t(sym)}</text>`;
    const H = Math.ceil(Math.max(yL, yR, cy + cH + 26) + 6);
    return `<h3>The quarter’s flow (13F, quarter ended ${date(f.P)})</h3>
      <p class="muted">Sellers on the left (${money(f.sold)}), buyers on the right (${money(f.bought)}); each band’s width is the dollars. Quarter-end disclosures do not say who traded with whom — the bands only show both sides of the same quarter.</p>
      <svg class="sk13" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(`13F flow for ${sym}: sold ${money(f.sold)}, bought ${money(f.bought)}`)}">${out}</svg>`;
  }

  // 4 · quarter by quarter: how many processed managers bought (up) and sold (down) in each quarter on file
  function quarters13(q, sym, fromPeriod, toPeriod) {
    if (!q || !(q.rows || []).length) return '';
    const cov = q.coverage || [], best = Math.max(...cov.map((c) => c || 0)) || 1;
    // a quarter's changes compare each manager with its previous filing: leave out quarters whose previous quarter has few
    // managers processed (the start of the history on file), where nearly every position would count as a first filing
    const idx = q.rows.map((r, i) => (r && i > 0 && (cov[i - 1] || 0) >= best * 0.6 ? i : -1)).filter((i) => i >= 0 && (!fromPeriod || q.periods[i] >= fromPeriod) && (!toPeriod || q.periods[i] <= toPeriod)).slice(-12);
    if (idx.length < 2) return '<p class="muted">Fewer than two comparable quarters in the chosen historical range. Expand the range or wait for more filings.</p>';
    const W = 640, H = 230, mid = 108, amp = 82, n = idx.length, bw = Math.min(36, (W - 40) / n - 14), step = (W - 40) / n;
    const max = Math.max(1, ...idx.map((i) => Math.max(q.rows[i][0], q.rows[i][1])));
    const ql = (p) => `Q${Math.floor((+p.slice(5, 7) - 1) / 3) + 1} ’${p.slice(2, 4)}`;
    const out = idx.map((i, k) => {
      const [b, s, usd, holders, nw, ex] = q.rows[i], x = 20 + k * step + (step - bw) / 2, early = k === n - 1 && (cov[i] || 0) < best * 0.6;
      const hb = b / max * amp, hs = s / max * amp, net = b - s;
      const tip = `Quarter ended ${date(q.periods[i])}: ${whole(b)} bought (${whole(nw)} new positions), ${whole(s)} sold (${whole(ex)} sold out) · net ${net >= 0 ? '+' : '−'}${whole(Math.abs(net))} managers · est. net ${money(usd)} · ${whole(holders)} holders among the ${whole(cov[i])} managers processed for that quarter${early ? ' (early filers only)' : ''}`;
      return `<g class="${early ? 'q13-early' : ''}"><title>${t(tip)}</title>
        <rect class="ba" x="${x.toFixed(1)}" y="${(mid - hb).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, hb).toFixed(1)}" rx="3"/>
        <rect class="bc" x="${x.toFixed(1)}" y="${mid}" width="${bw.toFixed(1)}" height="${Math.max(1, hs).toFixed(1)}" rx="3"/>
        <text class="q13-n ${net >= 0 ? 'pos' : 'neg'}" x="${(x + bw / 2).toFixed(1)}" y="${(mid - hb - 6).toFixed(1)}" text-anchor="middle">${net >= 0 ? '+' : '−'}${whole(Math.abs(net))}</text>
        <text class="q13-l" x="${(x + bw / 2).toFixed(1)}" y="${H - 22}" text-anchor="middle">${ql(q.periods[i])}</text>
        <text class="q13-l muted" x="${(x + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${early ? 'early' : !usd ? '$0' : money(usd).replace(/\.\d([BMK])/, '$1')}</text></g>`;
    }).join('');
    return `<h3>Quarter by quarter (13F)</h3>
      <p class="muted">Each quarter on file: processed managers that bought ${t(sym)} (up) and sold it (down), the net count above, and the estimated net dollars below. Pale: the newest quarter, which only early filers have reported so far. Older quarters fill in as the 13F history is processed, so compare the balance of each quarter rather than the heights.</p>
      <div class="pie13-key"><span><i class="ba"></i>bought</span><span><i class="bc"></i>sold</span></div>
      <svg class="q13" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(`Managers buying and selling ${sym} by quarter`)}"><line class="br13-axis" x1="10" x2="${W - 10}" y1="${mid}" y2="${mid}"/>${out}</svg>`;
  }

  // the five 13F views, one at a time (the choice is remembered)

  // Scope all five charts to one selectable reported quarter; history window affects the
  // time-series panel only. Choices persist per ticker and never fabricate missing quarters.
  function own13(inst, exits, sym, av, q) {
    const available = [...new Set(inst.filter((x) => x.status !== 'BASE').map((x) => x.period).concat((exits || []).map((x) => x.period)))].filter(Boolean).sort();
    const history = [...new Set((q && q.periods && q.periods.length ? q.periods : available))].filter(Boolean).sort();
    const stored = prefs.get('13f-selection:' + sym, {}) || {};
    const period = available.includes(stored.period) ? stored.period : '';
    const from = history.includes(stored.from) ? stored.from : (history[0] || '');
    const to = history.includes(stored.to) ? stored.to : (history[history.length - 1] || '');
    const options13 = (items, chosen) => items.map((p) => '<option value="' + t(p) + '"' + (p === chosen ? ' selected' : '') + '>' + t(p) + '</option>').join('');
    const f = flows13(inst, exits, period || undefined);
    const views = [['donut', 'Who bought', buyersPie(inst, exits, sym, av, period || undefined)],
      ['bf', 'Buyers vs sellers', f ? butterfly13(f, sym, av) : ''],
      ['bridge', 'Share bridge', f ? bridge13(f, sym) : ''],
      ['flow', 'Flow', f ? sankey13(f, sym) : ''],
      ['quarters', 'Quarter by quarter', quarters13(q, sym, from, to)]].filter((v) => v[2]);
    if (!views.length) return '';
    let on = prefs.get('own13', 'donut');
    if (!views.some((v) => v[0] === on)) on = views[0][0];
    const controls = '<div class="own13-periods" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:12px 0">' +
      (available.length ? '<label>13F report quarter <select data-own13-period aria-label="Choose 13F report quarter"><option value="">Latest well-covered</option>' + options13(available.slice().reverse(), period) + '</select></label>' : '') +
      (history.length ? '<label>History from <select data-own13-from aria-label="History starting quarter">' + options13(history, from) + '</select></label>' +
        '<label>Through <select data-own13-to aria-label="History ending quarter">' + options13(history, to) + '</select></label>' : '') +
      '</div>';
    return '<div class="own13 pie13">' + controls +
      (views.length > 1 ? '<div class="seg own13-seg" role="group" aria-label="13F view">' +
        views.map(([k, l]) => '<button type="button" data-own13="' + k + '" class="' + (k === on ? 'on' : '') + '" aria-pressed="' + (k === on) + '">' + l + '</button>').join('') + '</div>' : '') +
      views.map(([k, , html]) => '<div class="own13-view" data-view13="' + k + '"' + (k === on ? '' : ' hidden') + '>' + html + '</div>').join('') +
      '<p class="muted" style="font-size:12px">13F changes are quarter-end holdings comparisons, not verified trade executions. Historical results are limited to filings already processed.</p></div>';
  }
  function bindOwn13(box, sym, inst, exits, av, q) {
    box.querySelectorAll('[data-own13]').forEach((b) => b.addEventListener('click', () => {
      const k = b.dataset.own13;
      prefs.set('own13', k);
      box.querySelectorAll('[data-own13]').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', x === b); });
      box.querySelectorAll('[data-view13]').forEach((v) => { v.hidden = v.dataset.view13 !== k; });
    }));
    const selectors = [['[data-own13-period]', 'period'], ['[data-own13-from]', 'from'], ['[data-own13-to]', 'to']];
    selectors.forEach(([selector, key]) => {
      const node = box.querySelector(selector);
      if (!node) return;
      node.addEventListener('change', () => {
        const next = { ...(prefs.get('13f-selection:' + sym, {}) || {}), [key]: node.value };
        prefs.set('13f-selection:' + sym, next);
        const section = box.querySelector('.own13');
        if (section) section.outerHTML = own13(inst, exits, sym, av, q);
        bindOwn13(box, sym, inst, exits, av, q);
      });
    });
  }
  // ---------- smart money (data/smart/t/<TICKER>.json, app/smart.py): today's 13F, ETF, insider and officials' votes in
  // the stock, each weighted by how often that actor's past buys / sales were right (excess return over SPY, 63 trading days)
  async function smartBy(sym) {
    try {
      const r = await fetch(`disclosures/data/smart/t/${encodeURIComponent(sym.replace(/[^A-Za-z0-9-]/g, '_'))}.json`);
      if (r.ok) return await r.json();
    } catch (e) { /* not published yet */ }
    return null;
  }
  function smartBlock(d, sym, av) {
    if (!d || !d.now || d.now.S == null) return '';
    const n = d.now, S = n.S, w = Math.min(50, Math.abs(S) / 2), b = n.history_bucket;
    const G = { f13: '13F manager', etf: 'active ETF', ins: 'insider', gov: 'official' };
    const sg = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v))}`;
    const votes = (d.votes || []).slice(0, 6).map((v) => `<li>${avatar(av, v[1], /^f:\d+$/.test(v[0]) ? v[0].slice(2) : null)}<span><b>${t(v[1])}</b> <span class="muted">${G[v[2]] || ''}</span><br>
        <span class="${v[4] > 0 ? 'pos' : 'neg'}">${v[4] > 0 ? 'bought' : 'sold'}</span> · right ${v[7] != null ? Math.round(v[7] * 100) + '%' : '—'} on ${v[4] > 0 ? 'buys' : 'sales'} (${v[8]} scored) · weight ${v[6] > 0 ? '+' : ''}${Number(v[6]).toFixed(2)}</span></li>`).join('');
    return `<div class="smart13"><h3>Smart money: ${sg(S)} <span class="muted">of ±100</span></h3>
      <div class="sm13-line"><span class="sm13-gauge" role="img" aria-label="${t(`Smart score ${sg(S)} of plus or minus 100`)}"><b class="${S >= 0 ? 'up' : 'down'}" style="${S >= 0 ? 'left' : 'right'}:50%;width:${w.toFixed(1)}%"></b></span>
        <span>${n.n} vote${n.n === 1 ? '' : 's'} · everyone alike ${sg(n.raw)}${Object.entries(n.groups || {}).map(([g, x]) => ` · ${G[g] || g}s ${sg(x.S)}`).join('')}</span></div>
      ${votes ? `<ul class="sm13-votes">${votes}</ul>` : ''}
      <p class="muted">Every disclosed trade by 13F managers, active ETFs, insiders and officials is scored by the stock's return less SPY's over the next 63 trading days (a sale is right when the stock lagged); each vote now counts by that actor's record, so a buyer who is usually wrong counts against buying.${b && b[1] ? ` In the backtest, stocks scoring ${t(b[0])} averaged ${b[2] > 0 ? '+' : ''}${(b[2] * 100).toFixed(1)}% against SPY over the next 63 trading days (${b[1].toLocaleString('en-US')} stock-months).` : ''} <a href="disclosures/#smart/${encodeURIComponent(sym)}">Who is voting, and their records →</a></p></div>`;
  }

  // ---------- ETFs that hold it (data/etf/by/<TICKER>.json, app/etf.py): the largest by dollars, and the creations and
  // redemptions that passed through to the stock month by month (each ETF's N-PORT flows × the stock's weight in it)
  async function etfBy(sym) {
    for (const k of [...new Set([sym, sym.replace(/-/g, '.')])]) {
      try {
        const r = await fetch(`disclosures/data/etf/by/${encodeURIComponent(k)}.json`);
        if (r.ok) return await r.json();
      } catch (e) { /* not published yet */ }
    }
    return null;
  }
  function etfBlock(d, sym) {
    if (!d || !(d.rows || []).length) return '';
    // value held as reported; for the few portfolios without dollar values (sponsor files), weight × the ETF's assets
    const val = (r) => (r[3] != null ? r[3] : r[2] && r[4] ? r[2] * r[4] : null);
    const rows = d.rows.slice(0, 10), max = Math.max(...rows.map((r) => val(r) || 0)) || 1;
    const list = rows.map((r) => `<li title="${t(`${r[0]} ${r[1] || ''}: ${r[3] == null && val(r) ? '≈ ' : ''}${money(val(r))} of ${sym}, ${((r[2] || 0) * 100).toFixed(2)}% of the ETF${r[4] ? `, ETF assets ${money(r[4])}` : ''}`)}">
        <span class="etf13-name"><b>${t(r[0])}</b> <span class="muted">${t(SHORT_NAME(r[1] || '', 40))}</span></span>
        <span class="num">${r[3] == null && val(r) ? '≈ ' : ''}${money(val(r))}</span><span class="num muted">${((r[2] || 0) * 100).toFixed(r[2] >= 0.1 ? 1 : 2)}%</span>
        <i class="etf13-bar" style="width:${Math.max(1.5, (val(r) || 0) / max * 100).toFixed(1)}%"></i></li>`).join('');
    let flows = '';
    const fl = d.flows;
    if (fl && (fl.months || []).length >= 3) {
      const net = fl.months.map((m, i) => (fl.in[i] || 0) - (fl.out[i] || 0)), best = Math.max(...(fl.cov || []).map((x) => x || 0)) || 1;
      // the zero line sits where the months need it: low when money only came in, high when it only went out
      const up = Math.max(0, ...net), down = Math.max(0, ...net.map((v) => -v)), span = 150, top = 22;
      const W = 640, H = top + span + 48, mid = top + span * (up / ((up + down) || 1)), n = fl.months.length, step = (W - 40) / n, bw = Math.min(30, step - 10);
      const mx = (up + down) || 1, amp = span;
      const mon = (m) => new Date(m + '-15T00:00:00Z').toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' });
      const bars = fl.months.map((m, i) => {
        const v = net[i], h = Math.abs(v) / mx * amp, x = 20 + i * step + (step - bw) / 2, part = (fl.cov[i] || 0) < best * 0.6;
        const tip = `${m}: in ≈ ${money(fl.in[i])} (creations), out ≈ ${money(fl.out[i])} (redemptions), net ${money(v)} · ${fl.etfs[i]} ETFs${part ? ' — partial: not every ETF has reported this month yet' : ''}`;
        const vl = !Math.round(v / 1e6) ? '0' : `${v >= 0 ? '+' : '−'}${money(Math.abs(v)).replace(/\.\d([BMK])/, '$1')}`;
        return `<g class="${part ? 'q13-early' : ''}"><title>${t(tip)}</title><rect class="${v >= 0 ? 'etf13-in' : 'etf13-out'}" x="${x.toFixed(1)}" y="${(v >= 0 ? mid - h : mid).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" rx="3"/>
          <text class="q13-n ${v >= 0 ? 'pos' : 'neg'}" x="${(x + bw / 2).toFixed(1)}" y="${(v >= 0 ? mid - h - 5 : mid + h + 13).toFixed(1)}" text-anchor="middle">${vl}</text>
          <text class="q13-l" x="${(x + bw / 2).toFixed(1)}" y="${H - 22}" text-anchor="middle">${mon(m)}</text>
          ${i === 0 || m.endsWith('-01') ? `<text class="q13-l muted" x="${(x + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${m.slice(0, 4)}</text>` : ''}</g>`;
      }).join('');
      const tot = net.reduce((a, x) => a + x, 0);
      flows = `<h3>ETF money into ${t(sym)}, month by month</h3>
        <p class="muted">An estimate: each ETF’s creations and redemptions (N-PORT, monthly) × ${t(sym)}’s weight in its latest portfolio, summed over the ETFs that hold it (leveraged and inverse funds left out). ${fl.months.length} months: net <b class="${tot >= 0 ? 'pos' : 'neg'}">${money(tot)}</b>. Pale: months not every ETF has reported yet.</p>
        <svg class="q13" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(`Estimated ETF flows into ${sym} by month`)}"><line class="br13-axis" x1="10" x2="${W - 10}" y1="${mid}" y2="${mid}"/>${bars}</svg>`;
    }
    return `<h3>ETFs that hold it</h3>
      <p class="muted">${whole(d.etfs)} ETFs hold ${money(d.usd)} of ${t(sym)} in their latest N-PORT portfolios; the largest by dollars, with ${t(sym)}’s weight in each. <a href="disclosures/#etf">All ETFs →</a></p>
      <ol class="etf13">${list}</ol>${flows}`;
  }

  async function holdersSection(body, ticker, here) {
    const sym = normTicker(ticker);
    if (!sym) return;
    const box = document.createElement('div');
    box.className = 'section holders';
    box.innerHTML = `<div class="section-head"><h2>Holders and filings</h2><span class="muted">Loading 13F positions, filings and officials’ disclosures…</span></div>`;
    body.appendChild(box);
    let h = null;
    const avP = avData(), etfP = etfBy(sym), smP = smartBy(sym);
    try {
      const r = await fetch(`disclosures/data/holders/${encodeURIComponent(sym)}.json`);
      if (r.ok) h = await r.json();
    } catch (e) { /* the hub has not published yet */ }
    const av = await avP, etf = await etfP, sm = await smP;
    if (!here() || !box.isConnected) return;
    const inst = (h && h.institutional) || [], off = (h && h.officials) || [], ins = (h && h.insiders) || [];
    const stakes = (h && h.stakes) || [], f144 = (h && h.form144) || [], shortH = (h && h.short) || [];
    const ev8 = (h && h.events8k) || [], news = (h && h.news) || [];
    const SHOW = 12;
    const mega = (v) => (v == null ? '—' : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : whole(v));
    // short interest: one bar per settlement date (shares short), the latest date in words
    const shortBlock = () => {
      if (!shortH.length) return `<p class="muted">FINRA publishes no short position for ${t(sym)} in the dates on file.</p>`;
      const last = shortH[shortH.length - 1], max = Math.max(...shortH.map((x) => x[1] || 0)) || 1, W = 560, H = 90, bw = W / shortH.length;
      const bars = shortH.map((x, i) => {
        const hh = Math.max(1, ((x[1] || 0) / max) * (H - 14));
        return `<rect x="${(i * bw + 1).toFixed(1)}" y="${(H - hh).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${hh.toFixed(1)}" class="${i === shortH.length - 1 ? 'si-last' : 'si-bar'}"><title>${t(x[0])}: ${mega(x[1])} shares short${x[2] != null ? ` (${x[2] > 0 ? '+' : ''}${x[2]}%)` : ''}${x[3] != null ? ` · ${x[3]} days to cover` : ''}</title></rect>`;
      }).join('');
      return `<p class="holders-flow"><b>${date(last[0])}:</b> ${mega(last[1])} shares short${last[2] != null ? ` (${last[2] > 0 ? '+' : ''}${last[2]}% vs the prior date)` : ''}${
        last[3] != null ? ` · ${last[3]} days to cover` : ''}${last[4] ? ` · average daily volume ${mega(last[4])}` : ''}</p>
        <svg class="si-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Shares short in ${t(sym)}, ${t(shortH[0][0])} to ${t(last[0])}">${bars}</svg>
        <p class="muted">FINRA consolidated short interest, twice a month (${t(shortH[0][0])} – ${t(last[0])}): short positions brokers carry as of each settlement date, published about a week later. Days to cover = short position ÷ average daily volume.</p>`;
    };
    const instRows = (all) => (all ? inst : inst.slice(0, SHOW)).map((x) => `<tr><td><div class="av-row">${avatar(av, x.manager, x.cik)}<span><b>${t(x.manager)}</b><br><span class="muted mono">CIK ${t(x.cik)}</span></span></div></td>
        <td>${t(x.period)}<br><span class="muted">filed ${date(x.filed)}</span></td><td class="num">${whole(x.shares)}</td><td class="num">${money(x.value_usd)}</td>
        <td class="num">${x.weight == null ? '—' : (x.weight * 100).toFixed(1) + '%'}</td>
        <td class="num ${x.status === 'INCREASE' || x.status === 'NEW' ? 'pos' : x.status === 'DECREASE' ? 'neg' : ''}">${t(x.status === 'BASE' ? 'first filing' : x.status.toLowerCase())}${
          x.delta_shares ? `<br><span class="muted">${sign(x.delta_shares)}${whole(Math.abs(x.delta_shares))}</span>` : ''}</td>
        <td>${x.source_url ? `<a href="${t(x.source_url)}" target="_blank" rel="noopener">13F ↗</a>` : '—'}</td></tr>`).join('');
    box.innerHTML = `<div class="section-head"><h2>Holders and filings</h2>
        <span class="muted">${inst.length} institutional position${inst.length === 1 ? '' : 's'} · ${ins.length} insider trade${ins.length === 1 ? '' : 's'} · ${stakes.length} 13D / 13G · ${f144.length} Form 144 · ${off.length} record${off.length === 1 ? '' : 's'} by public officials
        · from <a href="disclosures/">Disclosures</a>${h && h.generated_at ? ` · snapshot ${date(h.generated_at.slice(0, 10))}` : ''}</span></div>
      ${h && (h.flows || h.signal) ? `<p class="holders-flow">${h.flows ? `<b>${t(h.flows.label || 'This quarter')}:</b> ${whole(h.flows.buyers)} managers added, ${whole(h.flows.sellers)} cut${h.flows.new ? ` (${whole(h.flows.new)} new positions)` : ''} · est. net ${h.flows.usd_net >= 0 ? '+' : '−'}${money(Math.abs(h.flows.usd_net))}` : ''}${
        h.signal && h.signal.tags && h.signal.tags.length ? ` · <a href="disclosures/#signals">Signals</a>: ${h.signal.tags.map((x) => `<span class="badge">${t(x.replace(/_/g, ' '))}</span>`).join(' ')}` : ''}</p>` : ''}
      ${own13(inst, (h && h.exits) || [], sym, av, h && h.q13f)}
      ${smartBlock(sm, sym, av)}
      <h3>Institutional investors (13F)</h3>
      ${inst.length ? `<div class="tbl-wrap"><table><thead><tr><th>Manager</th><th>Quarter</th><th class="num">Shares</th><th class="num">Value</th>
        <th class="num">Of its portfolio</th><th class="num">Change vs prior quarter</th><th>Source</th></tr></thead><tbody id="inst-rows">${instRows(false)}</tbody></table></div>
        ${inst.length > SHOW ? `<button class="btn" type="button" id="inst-more">Show all ${inst.length} managers</button>` : ''}
        <p class="muted">Quarter-end positions from 13F-HR filings of the managers processed so far (the hub works through SEC’s filer list in batches); not real-time holdings, and not every holder.</p>`
        : `<p class="muted">No processed 13F manager lists ${t(sym)} yet. Managers are processed in batches; prioritise one under Disclosures → Health.</p>`}
      ${etfBlock(etf, sym)}
      <h3>Insiders (Form 4)</h3>
      ${ins.length ? `<div class="tbl-wrap"><table><thead><tr><th>Insider</th><th>Trade</th><th class="num">Shares</th><th class="num">Price</th><th class="num">Value</th><th>Date</th><th>Source</th></tr></thead><tbody>
        ${ins.slice(0, 12).map((x) => `<tr><td><b>${t(x.insider)}</b><br><span class="muted">${t(x.title || x.role || '')}</span></td>
          <td class="${x.code === 'P' ? 'pos' : 'neg'}">${x.code === 'P' ? 'purchase' : 'sale'}${x.plan_10b5_1 ? ' <span class="muted">· 10b5-1 plan</span>' : ''}</td>
          <td class="num">${whole(x.shares)}</td><td class="num">${x.price != null ? '$' + Number(x.price).toFixed(2) : '—'}</td><td class="num">${x.value != null ? money(x.value) : '—'}</td>
          <td>${date(x.date)}</td><td>${x.url ? `<a href="${t(x.url)}" target="_blank" rel="noopener">Form 4 ↗</a>` : '—'}</td></tr>`).join('')}
        </tbody></table></div>
        <p class="muted">Open-market purchases and sales (of $100K or more) by officers, directors and 10% owners, filed with the SEC within two business days of the trade. Grants, option exercises and tax withholding are left out.</p>`
        : `<p class="muted">No open-market insider purchase or larger sale on file for ${t(sym)} in the last four months.</p>`}
      <h3>Recent 8-Ks</h3>
      ${ev8.length ? `<div class="tbl-wrap"><table><thead><tr><th>Filed</th><th>What</th><th>Key sentence</th><th>Source</th></tr></thead><tbody>
        ${ev8.slice(0, 8).map((x) => `<tr><td>${date(x.filed)}${x.accepted && x.accepted.length >= 16 ? `<br><span class="muted">${t(x.accepted.slice(11, 16))} ET</span>` : ''}</td>
          <td>${t(x.label || '')}<br><span class="muted">Item${(x.items || []).length > 1 ? 's' : ''} ${t((x.items || []).join(', '))}${x.form === '8-K/A' ? ' · amended' : ''}</span></td>
          <td class="wrap">${x.headline ? `<b>${t(x.headline.slice(0, 140))}</b><br>` : ''}<span class="muted">${t((x.quote || '').slice(0, 200))}${(x.quote || '').length > 200 ? '…' : ''}</span></td>
          <td>${x.url ? `<a href="${t(x.url)}" target="_blank" rel="noopener">${t(x.form || '8-K')} ↗</a>` : '—'}</td></tr>`).join('')}
        </tbody></table></div>
        <p class="muted">Current reports filed with the SEC within four business days of a material event; what each one is about comes from its items and its own words.</p>`
        : `<p class="muted">No 8-K from ${t(sym)} on file in the last four months.</p>`}
      ${news.length ? `<h3>News</h3><div class="tbl-wrap"><table><thead><tr><th>Published</th><th>Source</th><th>Headline</th></tr></thead><tbody>
        ${news.slice(0, 8).map((x) => `<tr><td>${date((x.published || '').slice(0, 10))}</td><td>${t(x.source || '')}</td>
          <td class="wrap">${x.url ? `<a href="${t(x.url)}" target="_blank" rel="noopener">${t(x.title || '')}</a>` : t(x.title || '')}</td></tr>`).join('')}
        </tbody></table></div><p class="muted">Headlines as the source published them (press-release wires, FDA, SEC) — open the link for the text.</p>` : ''}
      <h3>Holders above 5% (Schedules 13D / 13G)</h3>
      ${stakes.length ? `<div class="tbl-wrap"><table><thead><tr><th>Holder</th><th>Filing</th><th class="num">Stake</th><th class="num">Change</th><th>Filed</th><th>Source</th></tr></thead><tbody>
        ${stakes.slice(0, 12).map((x) => { const h = x.holder || x.filer || ''; return `<tr><td><b>${t(h)}</b>${
          x.persons > 1 ? `<br><span class="muted">${x.persons} reporting persons${h.toUpperCase() !== String(x.filer || '').toUpperCase() ? ` · filed by ${t(x.filer)}` : x.person && x.person.toUpperCase() !== h.toUpperCase() ? ` · largest: ${t(x.person)}` : ''}</span>` : ''}</td>
          <td class="wrap">${t(x.form)} <span class="muted">· ${t(x.label || '')}</span>${x.rule ? `<br><span class="muted">${t(x.rule)}</span>` : ''}${x.purpose ? `<br><span class="muted" title="${t(x.purpose)}">Purpose: ${t(x.purpose.slice(0, 140))}${x.purpose.length > 140 ? '…' : ''}</span>` : ''}</td>
          <td class="num">${x.percent != null ? x.percent + '%' : '—'}<br><span class="muted">${mega(x.shares)} sh</span></td>
          <td class="num ${x.change > 0 ? 'pos' : x.change < 0 ? 'neg' : ''}">${x.change != null ? `${x.change > 0 ? '+' : ''}${x.change.toFixed(2)} pts` : '—'}${x.prev_percent != null ? `<br><span class="muted">from ${x.prev_percent}%</span>` : ''}</td>
          <td>${date(x.filed)}${x.event_date ? `<br><span class="muted">event ${date(x.event_date)}</span>` : ''}</td><td>${x.url ? `<a href="${t(x.url)}" target="_blank" rel="noopener">${t(x.form)} ↗</a>` : '—'}</td></tr>`; }).join('')}
        </tbody></table></div>
        <p class="muted">Anyone above 5% of a class of shares files a Schedule 13D (with its purpose, Item 4) — or, if passive, the short-form 13G. The stake is the largest single reporting person’s; the change compares with the same filer’s previous filing on file.</p>`
        : `<p class="muted">No Schedule 13D or 13G on ${t(sym)} on file yet (filings since the collector started, back about four months).</p>`}
      <h3>Planned insider sales (Form 144)</h3>
      ${f144.length ? `<div class="tbl-wrap"><table><thead><tr><th>Seller</th><th class="num">Shares</th><th class="num">Market value</th><th>Approx. sale date</th><th>Acquired by</th><th>Source</th></tr></thead><tbody>
        ${f144.slice(0, 10).map((x) => `<tr><td><b>${t(x.seller_name || x.seller)}</b><br><span class="muted">${t(x.relationship || '')}</span></td><td class="num">${whole(x.shares)}</td>
          <td class="num">${x.value != null ? money(x.value) : '—'}</td><td>${date(x.sale_date)}<br><span class="muted">notice filed ${date(x.filed)}</span></td>
          <td>${t(x.acquired || '—')}${x.plan_date ? `<br><span class="muted">10b5-1 plan adopted ${date(x.plan_date)}</span>` : ''}</td><td>${x.url ? `<a href="${t(x.url)}" target="_blank" rel="noopener">Form 144 ↗</a>` : '—'}</td></tr>`).join('')}
        </tbody></table></div>
        <p class="muted">A Form 144 is a notice of an intended sale of restricted or control shares by an officer, director or other affiliate — not a trade. The sale, if made, follows on Form 4.</p>`
        : `<p class="muted">No Form 144 notice of $25K or more on ${t(sym)} on file.</p>`}
      <h3>Short interest (FINRA)</h3>
      ${shortBlock()}
      <h3>Public officials</h3>
      ${off.length ? `<div class="tbl-wrap"><table><thead><tr><th>Person</th><th>Jurisdiction</th><th>Record</th><th>Disclosed amount</th><th>Date</th><th>Source</th></tr></thead><tbody>
        ${off.map((r, i) => `<tr${i >= 10 ? ' class="off-more" hidden' : ''}><td><div class="av-row">${avatar(av, r.person)}<span><b>${t(r.person)}</b>${r.owner ? `<br><span class="muted">${t(r.owner)}</span>` : ''}</span></div></td><td>${t(r.jurisdiction)}</td>
          <td>${t(r.kind === 'transaction' ? (r.transaction_type || 'transaction') : 'asset')}${r.read === 'machine' ? ' <span class="muted" title="Read by machine from the official report; the ticker is the one the filer wrote. Open the page to confirm.">· auto-read</span>' : r.read === 'electronic' ? ' <span class="muted" title="From the Senate’s electronic report (eFD); the ticker is the one the filer entered.">· eFD</span>' : ''}<br><span class="muted">${t(r.asset)}</span></td>
          <td class="num">${t(amountRange(r))}${r.price_on_date ? `<br><span class="muted">≈ ${whole(r.est_shares_min)}${r.est_shares_max != null ? '–' + whole(r.est_shares_max) : '+'} sh at $${r.price_on_date.toFixed(2)} · est.</span>` : ''}</td>
          <td>${date(r.date)}</td><td>${r.source_url ? `<a href="${t(r.source_url)}${r.page ? '#page=' + r.page : ''}" target="_blank" rel="noopener">${r.page ? 'Page ' + r.page : r.read === 'electronic' ? 'Report' : 'Document'} ↗</a>` : '—'}</td></tr>`).join('')}
        </tbody></table></div>
        ${off.length > 10 ? `<button class="btn" type="button" id="off-more">Show all ${off.length} records</button>` : ''}
        <p class="muted">Disclosed value ranges from annual statements and transaction reports (US House, US Senate, New York, California, Canada, imports). Reviewed rows were checked against their source page; “auto-read” rows come straight from US House transaction reports and “eFD” rows from US Senate electronic reports, with the ticker the filer wrote. Ranges are not share counts.</p>`
        : `<p class="muted">No official’s disclosure names ${t(sym)} yet. US House and Senate transaction reports are read in batches; other jurisdictions appear once a disclosure is reviewed in Disclosures → PDF / OCR.</p>`}`;
    bindOwn13(box, sym, inst, (h && h.exits) || [], av, h && h.q13f);
    const more = $('#inst-more', box);
    if (more) more.addEventListener('click', () => { $('#inst-rows', box).innerHTML = instRows(true); more.remove(); });
    const offMore = $('#off-more', box);
    if (offMore) offMore.addEventListener('click', () => { box.querySelectorAll('tr.off-more').forEach((tr) => { tr.hidden = false; }); offMore.remove(); });
  }

  // the ready-to-post X thread for a quarter (the same text the e-mails carry): which filing, what each image shows (with
  // Save buttons), every post with its role and a Copy button, and "Email me this thread"
  const ROLES = { headline: 'Headline and charts', business: 'What the company does', about: 'The company in its own words',
    analysis: 'Analysis', quote: 'From the filing', source: 'Source' };
  function threadSection(q, p, repo, osets, c) {
    const posts = q.x_thread || [];
    if (!posts.length) return null;
    const ticker = (p.tickers || [])[0] || String(p.cik);
    const intent = 'https://x.com/intent/post?text=' + encodeURIComponent(posts[0].text);
    const direct = !!acct.client && (!osets || osets.thread_direct !== false);   // straight to the inbox (owner setting)
    let mail = '';
    if (direct) mail = '<button class="btn primary" type="button" id="thread-mail">✉ Email me this thread</button>';
    else if (repo) {
      const title = `Email thread: ${ticker} ${S.dec(q.label)} [${p.cik} ${q.end}]`;
      const bodyTxt = 'Sends this quarter’s X thread and its charts to the inbox in the MAIL_USERNAME (or MAIL_TO) secret. ' +
        'Press Create; the issue closes itself once the e-mail has gone out (about two minutes).';
      mail = `<a class="btn primary" target="_blank" rel="noopener" href="https://github.com/${t(repo)}/issues/new?title=${
        encodeURIComponent(title)}&body=${encodeURIComponent(bodyTxt)}">Email me this thread</a>`;
    }
    const acc = accession(q.index_url);
    const form = q.form === '8-K' ? 'Earnings release (8-K)' : q.form === '6-K' ? 'Results release (6-K)' : q.form;
    const vs = q.compare_y && q.compare_y.vs;
    const charts = [['std', 'Chart 1', `${S.dec(q.label)}: where the revenue went, from costs to profit and operating cash flow`]]
      .concat(vs ? [['y', 'Chart 2', `the same flows compared with ${S.dec(vs)}; a dark strip inside a band is growth`]] : []);
    const sec = document.createElement('section');
    sec.className = 'section';
    sec.id = 'thread';
    sec.innerHTML = `
      <div class="section-head"><h2>X thread</h2><span class="muted">Ready to post by hand · ${posts.length} posts · every post fits 280 characters</span></div>
      <dl class="facts thread-info">
        <dt>Filing</dt><dd>${t(form)} filed ${date(q.filed)} · quarter ended ${date(q.end)}${acc ? ` · <span class="mono">${acc}</span>` : ''}</dd>
        <dt>Images for post 1</dt><dd>${charts.map(([m, name, cap]) => `<div class="thread-img"><span><b>${name}</b> · ${t(cap)}</span>
          <button class="btn small" type="button" data-img="${m}">Save PNG</button></div>`).join('')}</dd>
      </dl>
      <div class="thread-actions">${mail}<a class="btn" target="_blank" rel="noopener" href="${t(intent)}">Open post 1 in X</a>
        <button class="btn" type="button" data-copy-all>Copy all</button>
        ${c ? '<button class="btn" type="button" id="thread-article" title="This report as an X Article: copy the text, then each chart, and paste them into X’s editor">✦ X Article</button>' : ''}</div>
      ${mail ? `<p class="note-rule" id="thread-mail-note">${direct ? 'Sends the thread with both chart PNGs attached to the address you signed in with, usually within two minutes.'
        : '“Email me” opens GitHub with the request filled in: press Create and the thread arrives with both charts attached. Change this in Owner tools.'}</p>` : ''}
      <ol class="thread">${posts.map((x, i) => `<li>
        <div class="thread-meta"><span>Post ${i + 1} of ${posts.length}${ROLES[x.role] ? ` · <b>${ROLES[x.role]}</b>` : ''} · ${x.len}/280${i ? ' · reply to the post above' : ' · attach the charts'}</span>
          <button class="btn small" type="button" data-copy="${i}">Copy</button></div>
        <pre>${t(x.text)}</pre></li>`).join('')}</ol>`;
    const copy = async (txt, btn) => {
      try {
        const native = window.FilingFlowsApp;
        if (native && typeof native.copyText === 'function') native.copyText(txt);
        else await navigator.clipboard.writeText(txt);
        btn.textContent = 'Copied';
      } catch (e) {
        const pre = btn.closest('li') ? $('pre', btn.closest('li')) : $('pre', sec);
        const r = document.createRange();
        r.selectNodeContents(pre);
        const sel = getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        btn.textContent = 'Selected: press Ctrl+C';
      }
      setTimeout(() => { btn.textContent = btn.hasAttribute('data-copy-all') ? 'Copy all' : 'Copy'; }, 1800);
    };
    $$('[data-copy]', sec).forEach((b) => b.addEventListener('click', () => copy(posts[+b.dataset.copy].text, b)));
    $('[data-copy-all]', sec).addEventListener('click', (ev) => copy(posts.map((x) => x.text).join('\n\n---\n\n'), ev.currentTarget));
    $$('[data-img]', sec).forEach((b) => b.addEventListener('click', async () => {
      const m = b.dataset.img === 'y' ? 'y' : null;
      b.disabled = true;
      try {
        await fontsReady();
        const blob = await S.exportScene(S.layout(q, { compare: m, decreases: state.decreases }), 'png');
        const name = `${ticker}-${S.dec(q.label)}-${m ? '2-vs-' + S.dec(vs) : '1-chart'}.png`.replace(/[^A-Za-z0-9.]+/g, '-');
        const res = await saveBlob(blob, name);
        toast(res === 'saved' ? `Saved ${name}` : 'Download unavailable here');
      } catch (err) {
        toast(`Could not save: ${err.message}`);
      } finally {
        b.disabled = false;
      }
    }));
    const art = $('#thread-article', sec);
    if (art) art.addEventListener('click', () => articlePanel(articleCompany(c, q), `${S.dec(p.name)} ${S.dec(q.label)}`));
    const btn = $('#thread-mail', sec);
    if (btn) btn.addEventListener('click', () => {
      if (btn.disabled) return;
      withProgress(btn, (text) => { if (text) toast(text); }, () => askFor({ cik: +p.cik, period_end: q.end, kind: 'thread' }, 'Thread'));
    });
    // Post to X now, through Buffer's queue (config/x.json mode "buffer"): the quarter's earnings post, or who bought it (13F)
    const bar = document.createElement('div');
    bar.className = 'controls';
    bar.innerHTML = `<span class="muted">Post to X via Buffer (written by the model from the filing, checked). The earnings post uses the quarter shown above — pick another quarter to post that 10-Q / 10-K:</span>
      ${draftToggle('post-draft')}
      <button class="btn" type="button" data-post="post">✦ Earnings post (${t(q.label)} ${t(q.form || '')})</button>
      <button class="btn" type="button" data-post="post_holders">✦ Who bought it (13F)</button>
      <button class="btn" type="button" data-post="post_gif" title="An animated flip-book of the last eight quarters' Sankeys, with a post on the two-year trend">✦ 8-quarter GIF</button>
      <span class="post-8k"><input class="input mono" id="post-8k-ref" placeholder="8-K accession or EDGAR link (blank = most material, 45 days)" aria-label="8-K accession number"><button class="btn" type="button" data-post="post_8k" title="A post about one 8-K: the accession you paste, or this company's most material 8-K of the last 45 days">✦ 8-K post</button></span>`;
    $$('[data-post]', bar).forEach((b) => b.addEventListener('click', () => withProgress(b, (text) => { if (text) toast(text); }, () => {
      const kind = b.dataset.post, draft = !!($('#post-draft') && $('#post-draft').checked);
      if (kind === 'post_8k') {
        const raw = ($('#post-8k-ref').value || '').trim(), m = raw.match(/(\d{10})-?(\d{2})-?(\d{6})/);
        if (raw && !m) return Promise.resolve('That does not look like an accession number (0001234567-26-000123) or an EDGAR filing link');
        return askFor({ cik: +p.cik, period_end: localISO(new Date()), kind, ref: m ? `${m[1]}-${m[2]}-${m[3]}` : null, draft }, '8-K post');
      }
      return askFor({ cik: +p.cik, period_end: q.end, kind, draft }, kind === 'post' ? 'Earnings post' : kind === 'post_gif' ? '8-quarter GIF post' : 'Holders post');
    })));
    setTimeout(() => bindDraft('post-draft'), 0);
    sec.appendChild(bar);
    return sec;
  }

  // ---------- X Article (owner): a company's report or a day's report as an X Article, copied and pasted by hand ----------
  // X's article editor (x.com/compose/articles) takes rich text from the clipboard, but a browser can hold only one image
  // at a time. So: one click copies the title, one the formatted text (headings, bold, lists, links), with an
  // "[Image n]" line wherever a chart goes; then each chart is copied in turn and pasted over its marker. Nothing is
  // posted from here: the article is written and published in X's own editor.
  const artSite = () => `${location.origin}${location.pathname}`;
  const artLine = (e, q) => {                       // "revenue $94.9B (+6% Y/Y), operating margin 31.2%, net earnings $23.4B"
    const h = (q && q.headline) || {};
    return [h.revenue != null ? `revenue ${money(h.revenue)}${h.yoy != null ? ` (${pct(h.yoy)} Y/Y)` : ''}` : '',
      h.om != null ? `operating margin ${margin(h.om)}` : '', h.ni != null ? `net earnings ${money(h.ni)}` : ''].filter(Boolean).join(', ');
  };
  const artForm = (q) => (q.form === '8-K' ? 'earnings release (8-K)' : q.form === '6-K' ? 'results release (6-K)' : q.form);
  const chartImage = (q, mode) => async () => {
    await fontsReady();
    return S.exportScene(S.layout(q, { compare: mode || null, decreases: state.decreases }), 'png');
  };
  // one company's quarter: the report the company page shows, in article form
  function articleCompany(c, q) {
    const p = c.profile, name = S.dec(p.name), tk = (p.tickers || [])[0] || '', who = tk ? `${name} ($${tk})` : name;
    const B = [], images = [], url = `${artSite()}#c-${p.cik}-${q.end}`;
    const img = (cap, make, file) => { images.push({ n: images.length + 1, cap, make, file }); B.push({ k: 'img', n: images.length, cap }); };
    const h = q.headline || {};
    B.push({ k: 'p', text: `${who} filed its ${artForm(q)} for ${S.dec(q.label)} (quarter ended ${date(q.end)}) on ${date(q.filed)}: ${artLine(null, q)}.`,
      bold: `${who} filed its ${artForm(q)}` });
    if (q.form === '8-K') B.push({ k: 'p', text: 'Preliminary: read from the earnings release; the 10-Q or 10-K replaces it when filed.', em: true });
    img(`${S.dec(q.label)}: where the revenue went — costs, profit and operating cash flow`, chartImage(q),
      `${tk || p.cik}-${S.dec(q.label)}-sankey.png`);
    const intro = c.intro && (typeof c.intro === 'string' ? c.intro : c.intro.text);
    if (intro) {
      B.push({ k: 'h2', text: 'What the company does' });
      const src = c.intro.source === '8-K' || c.intro.source === '6-K' ? 'earnings release' : c.intro.source === '10-Q' ? '10-Q' : '10-K, Item 1';
      B.push({ k: 'quote', text: S.dec(intro).slice(0, 600) + (S.dec(intro).length > 600 ? '…' : ''), src: `In its own words (${src})` });
    }
    if ((q.analysis || []).length) {
      B.push({ k: 'h2', text: `The quarter` });
      q.analysis.forEach((x) => B.push({ k: 'p', text: S.dec(x) }));
    }
    const cy = q.compare_y, cq = q.compare;
    if (cy && (cy.bullets || []).length) {
      B.push({ k: 'h2', text: `What changed vs ${S.dec(cy.vs)}` });
      B.push({ k: 'ul', items: cy.bullets.map((x) => S.dec(x)) });
      img(`${S.dec(q.label)} vs ${S.dec(cy.vs)}: the same flows; a dark strip inside a band is growth`, chartImage(q, 'y'),
        `${tk || p.cik}-${S.dec(q.label)}-vs-${S.dec(cy.vs)}.png`);
    } else if (cq && (cq.bullets || []).length) {
      B.push({ k: 'h2', text: `What changed vs ${S.dec(cq.vs)}` });
      B.push({ k: 'ul', items: cq.bullets.map((x) => S.dec(x)) });
    }
    B.push({ k: 'h2', text: 'Sources' });
    B.push({ k: 'ul', links: [[url, 'Interactive chart on Filing Flows'], [q.index_url, 'The filing on SEC EDGAR'],
      [q.doc_url, q.form === '8-K' || q.form === '6-K' ? 'The earnings release' : `The ${q.form}`]].filter((x) => x[0]) });
    B.push({ k: 'p', em: true, text: 'Figures are read automatically from SEC filings by fixed rules and can contain errors: check the filing before relying on them. Not investment advice.' });
    const title = `${name} ${S.dec(q.label)}: ${h.revenue != null ? money(h.revenue) + ' revenue' : 'the quarter'}${h.yoy != null ? `, ${pct(h.yoy)} Y/Y` : ''} — where it went`;
    return { title: title.slice(0, 100), blocks: B, images };
  }
  // ---------- the owner's X report: the daily report or chosen tickers, with the chart families ticked, as one X Article ----------
  const XR_KINDS = [['earnings', 'Earnings Sankey (with the chart)'], ['moves', 'Market move'], ['optmoves', 'Options move (IV, put/call, gamma, 13F options)'],
    ['markets', 'Polymarket · Kalshi · options'], ['events', '8-Ks and news'], ['insiders', 'Insiders (Form 4, 10b5-1)'], ['officials', 'Officials\' trades'],
    ['flows', 'Flows: 13F, ETFs, insiders, plan sales, officials'], ['capital', 'Capital allocation'], ['debt', 'Debt & rates'], ['rotation', 'Rotation: RRG 2-D / 3-D / 4-D, clock, solar system, galaxy'],
    ['chains', 'Supply chains & themes: its place in each money flow']];
  async function chainLines(tk) {                         // web/chains.js: the chains a company is part of
    if (!window.FFChains || !tk) return [];
    const ix = await getJSON('chains/index.json').catch(() => null);
    const T = String(tk).toUpperCase();
    const hits = ((ix && ix.chains) || []).filter((c) => (c.buyers || []).includes(T) || (c.layers || []).some((L) => (L.tickers || []).includes(T))).slice(0, 3);
    const docs = await Promise.all(hits.map((c) => getJSON(`chains/${c.id}.json`).catch(() => null)));
    return docs.filter(Boolean).flatMap((d) => window.FFChains.lines(d, T).map((text) => ({ text, link: `${artSite()}#chain-${d.id}`, name: d.name })));
  }
  function xrCik(ix, tk) {
    const want = String(tk || '').toUpperCase().replace(/\./g, '-');
    const e = ix.companies.find((c) => String(c.ticker || '').toUpperCase().replace(/\./g, '-') === want);
    return e ? e.cik : (/^\d+$/.test(tk) ? +tk : null);
  }
  async function xrEntries(ix, list, kinds, say) {
    await loadPosts();
    const other = kinds.filter((k) => k !== 'earnings' && k !== 'chains');
    let done = 0;
    return (await Promise.all(list.map(async (x) => {
      try {
        const cik = x.cik || xrCik(ix, x.ticker), c = cik ? await getJSON(`c/${cik}.json`).catch(() => null) : null;
        const qs = c ? c.quarters.map(fcfView) : [], q = x.end ? (qs.find((y) => y.end === x.end && (!x.form || y.form === x.form)) || qs.find((y) => y.end === x.end)) : qs[0];
        const tk = x.ticker || (c && (c.profile.tickers || [])[0]) || '';
        const B = window.FFPosts && other.length ? await window.FFPosts.load(tk, cik, other) : null;
        if (B && c) B.site = c;
        const items = B ? window.FFPosts.all(B, other) : [];
        const chains = kinds.includes('chains') ? await chainLines(tk) : [];
        say(`Reading ${++done} of ${list.length}…`);
        return (c || items.length || chains.length) ? { x, c, q, tk, cik, items, chains, name: c ? S.dec(c.profile.name) : (B && B.name) || tk } : null;
      } catch (e) { return null; }
    }))).filter(Boolean);
  }
  // the daily report's market-wide part: that day's 8-Ks, officials' reports, insider purchases, the biggest moves in the
  // stocks and in their options (hub data: market/events8k, officials-trades, insiders, options)
  async function xrMarketWide(day, kinds) {
    const get = (f) => fetch(`disclosures/data/market/${f}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const [ev, off, ins, opt] = await Promise.all([kinds.includes('events') ? get('events8k') : null, kinds.includes('officials') ? get('officials-trades') : null,
      kinds.includes('insiders') ? get('insiders') : null, kinds.includes('moves') || kinds.includes('optmoves') ? get('options') : null]);
    const B = [], tk = (x) => (x ? '$' + String(x).replace(/-/g, '.') : '');
    const E = ((ev && ev.rows) || []).filter((r) => r.filed === day && r.ticker).sort((a, b) => (b.score || 0) - (a.score || 0));
    if (E.length) {
      B.push({ k: 'h2', text: `8-Ks filed that day: ${E.length}` });
      B.push({ k: 'ul', items: E.slice(0, 12).map((r) => `${tk(r.ticker)} ${r.company || ''}: ${r.label || r.code || '8-K'}${r.headline ? ` — ${String(r.headline).slice(0, 120)}` : ''}`) });
    }
    const O = ((off && off.trades) || []).filter((r) => r.filed_date === day && r.ticker);
    if (O.length) {
      B.push({ k: 'h2', text: `Officials' trades reported that day: ${O.length}` });
      B.push({ k: 'ul', items: O.slice(0, 15).map((r) => `${r.person} (${String(r.jurisdiction || '').replace(/^US /, '')}): ${r.type} of ${tk(r.ticker)}, $${(r.amount_min || 0).toLocaleString('en-US')}${r.amount_max ? '–$' + r.amount_max.toLocaleString('en-US') : '+'}, traded ${date(r.date)}`) });
    }
    const I = ((ins && ins.latest) || []).filter((r) => r.code === 'P' && (r.filed || r.date) && String(r.filed || r.date).slice(0, 10) >= day).sort((a, b) => (b.value || 0) - (a.value || 0));
    if (I.length) {
      B.push({ k: 'h2', text: 'Insider purchases (Form 4)' });
      B.push({ k: 'ul', items: I.slice(0, 10).map((r) => `${tk(r.ticker)} ${r.insider} (${r.title || r.role}) bought ${money(r.value)}${r.price != null ? ` at $${(+r.price).toFixed(2)}` : ''} on ${date(r.date)}`) });
    }
    const R = ((opt && opt.rows) || []).filter((r) => !['SPX', 'NDX', 'VIX', 'RUT', 'XSP', 'DJX'].includes(r.ticker));
    if (kinds.includes('moves') && R.length) {
      const mv = R.map((r) => { const h = (r.history || []).filter((x) => x[1] != null); return h.length >= 2 ? [r.ticker, h[h.length - 1][1] / h[h.length - 2][1] - 1, h[h.length - 1][1], h[h.length - 1][0]] : null; })
        .filter(Boolean).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
      if (mv.length) {
        B.push({ k: 'h2', text: 'The biggest moves (end of day)' });
        B.push({ k: 'ul', items: mv.slice(0, 8).map(([t2, r, px, d]) => `${tk(t2)} ${pct(r * 100, 1)} to $${(+px).toFixed(2)} (${date(d)})`) });
      }
    }
    if (kinds.includes('optmoves') && R.length) {
      const iv = R.filter((r) => r.iv30_chg != null).sort((a, b) => Math.abs(b.iv30_chg) - Math.abs(a.iv30_chg));
      if (iv.length) {
        B.push({ k: 'h2', text: 'Options: the biggest moves in implied volatility' });
        B.push({ k: 'ul', items: iv.slice(0, 8).map((r) => `${tk(r.ticker)} 30-day IV ${r.iv30_chg > 0 ? '+' : '−'}${Math.abs(r.iv30_chg).toFixed(1)} pts to ${(+r.iv30).toFixed(1)}% · put/call OI ${r.pc_oi != null ? (+r.pc_oi).toFixed(2) : '—'} · walls $${r.put_wall} / $${r.call_wall}`) });
      }
    }
    return B;
  }
  function articleCustom(entries, kinds, head) {
    const B = [], images = [], K = Object.fromEntries(XR_KINDS);
    const tag = (e) => (e.tk ? `$${String(e.tk).replace(/-/g, '.')}` : e.name);
    B.push({ k: 'p', text: head.intro });
    if ((head.wide || []).length) B.push(...head.wide);
    if (entries.length) {
      B.push({ k: 'h2', text: 'In this report' });
      B.push({ k: 'ul', items: entries.slice(0, 30).map((e) => `${tag(e)} ${e.name}${e.q ? ` · ${S.dec(e.q.label)}: ${artLine(null, e.q)}` : ''}`) });
    }
    entries.forEach((e, i) => {
      if (i >= head.full) return;
      B.push({ k: 'h2', text: `${e.name}${e.tk ? ` (${String(e.tk).replace(/-/g, '.')})` : ''}${e.q && kinds.includes('earnings') ? ' · ' + S.dec(e.q.label) : ''}` });
      kinds.forEach((k) => {
        if (k === 'earnings') {
          if (!e.q) return;
          B.push({ k: 'p', text: `${artForm(e.q)} filed ${date(e.q.filed)}: ${artLine(null, e.q)}.`, bold: `${artForm(e.q)} filed ${date(e.q.filed)}` });
          images.push({ n: images.length + 1, cap: `${e.name} ${S.dec(e.q.label)}: where the revenue went`, make: chartImage(e.q), file: `${e.tk || e.cik}-${S.dec(e.q.label)}-sankey.png` });
          B.push({ k: 'img', n: images.length, cap: images[images.length - 1].cap });
          (e.q.analysis || []).slice(0, 2).forEach((x) => B.push({ k: 'p', text: S.dec(x) }));
          return;
        }
        if (k === 'chains') {
          if ((e.chains || []).length) {
            B.push({ k: 'p', text: 'Supply chains.', bold: 'Supply chains.' });
            e.chains.forEach((x) => B.push({ k: 'p', text: x.text }));
          }
          return;
        }
        const it = e.items.find((p) => p.kind === k);
        if (!it) return;
        B.push({ k: 'p', text: `${it.label}. ${it.story || ''}`.trim(), bold: it.label + '.' });
        it.paras.forEach((x) => B.push({ k: 'p', text: x }));
      });
      const links = [[`${artSite()}#c-${e.cik}`, `${e.name} on Filing Flows`]].concat(e.items.map((p) => [p.link, `${p.label} on Filing Flows`]))
        .concat((e.chains || []).map((x) => [x.link, `${x.name} on Filing Flows`]));
      if (e.cik) B.push({ k: 'ul', links: links.filter((l, j) => l[0] && links.findIndex((m) => m[0] === l[0]) === j).slice(0, 4) });
    });
    const rest = entries.slice(head.full);
    if (rest.length) {
      B.push({ k: 'h2', text: 'Also in the report' });
      B.push({ k: 'ul', items: rest.slice(0, 40).map((e) => `${tag(e)} ${e.name}${e.q ? ` · ${S.dec(e.q.label)}: ${artLine(null, e.q)}` : ''}`) });
    }
    B.push({ k: 'p', em: true, text: `What is inside: ${kinds.map((k) => K[k]).join('; ')}. All charts: ${artSite()} — figures read automatically from SEC filings, prediction markets and CBOE quotes by fixed rules; check the sources before relying on them. Not investment advice.` });
    return { title: head.title.slice(0, 100), blocks: B, images };
  }
  async function xReportPanel(box, ix, osets) {
    if (!box || !box.isConnected) return;
    const now = new Date(), minOwner = osets && osets.min_revenue != null ? +osets.min_revenue : 1e9, full = osets && osets.daily_scope === 'all';
    const days = [0, 1, 2, 3, 4, 5, 6].map((i) => { const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i), iso = localISO(d);
      return { iso, label: i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }), n: dayEntries(ix, iso).length }; });
    const first = days.find((d) => d.n) || days[0];
    const kSaved = prefs.get('xr-kinds', ['earnings', 'moves', 'optmoves', 'markets', 'events', 'insiders', 'officials', 'flows', 'debt']);
    box.innerHTML = `<div class="section-head"><h2>X report generator</h2><span class="muted">One X Article: the daily report by default, or the companies you choose, with the chart families you tick</span></div>
      <form id="xr-form" class="xr">
        <div class="xr-mode" role="radiogroup" aria-label="What the report covers">
          <label><input type="radio" name="xr-mode" value="day" checked> Daily report for
            <select id="xr-day" aria-label="Filing date">${days.map((d) => `<option value="${d.iso}" ${d === first ? 'selected' : ''}>${d.label} (${d.n} filing${d.n === 1 ? '' : 's'})</option>`).join('')}</select>
            <span class="muted small">${full ? 'every company that filed' : `companies with quarterly revenue of $${(minOwner / 1e9).toLocaleString('en-US', { maximumFractionDigits: 2 })}B or more`}, largest first</span></label>
          <label><input type="radio" name="xr-mode" value="tickers"> These companies:
            <input id="xr-tickers" placeholder="e.g. AAPL, NVDA, MSFT, TSLA" value="${t(prefs.get('xr-tickers', ''))}" style="min-width:min(22em,100%)" aria-label="Tickers"></label>
        </div>
        <fieldset class="xr-kinds"><legend>What goes in, for each company</legend>${XR_KINDS.map(([k, l]) => `<label><input type="checkbox" value="${k}" ${kSaved.includes(k) ? 'checked' : ''}> ${t(l)}</label>`).join('')}</fieldset>
        <div class="row"><label class="muted small">In full: <select id="xr-full">${[3, 6, 10, 15, 25].map((n) => `<option value="${n}" ${n === (+(osets && osets.article_full) || 6) ? 'selected' : ''}>${n} companies</option>`).join('')}</select> (the rest are listed)</label>
          <button class="btn primary" type="submit">✦ Build the X Article</button><button class="btn" type="button" id="xr-posts">Show each post</button><span class="muted small" id="xr-msg" role="status"></span></div>
      </form>
      <div id="xr-out"></div>`;
    const say = (x) => { const m = $('#xr-msg', box); if (m) m.textContent = x; };
    const read = () => {
      const kinds = $$('.xr-kinds input', box).filter((x) => x.checked).map((x) => x.value);
      const mode = ($('input[name="xr-mode"]:checked', box) || {}).value || 'day';
      prefs.set('xr-kinds', kinds);
      prefs.set('xr-tickers', $('#xr-tickers', box).value);
      return { kinds: kinds.length ? kinds : ['earnings'], mode, full: +$('#xr-full', box).value || 6 };
    };
    const pick = (o) => {
      if (o.mode === 'tickers') {
        const tks = [...new Set($('#xr-tickers', box).value.toUpperCase().split(/[\s,;]+/).filter(Boolean))].slice(0, 30);
        return { list: tks.map((tk) => ({ ticker: tk })), what: 'custom report', title: `${tks.slice(0, 4).map((x) => '$' + x).join(' ')}${tks.length > 4 ? ` +${tks.length - 4}` : ''}: ${o.kinds.length > 2 ? 'earnings, markets, flows and more' : o.kinds.map((k) => k).join(' & ')} — Filing Flows`,
          intro: `${tks.length} compan${tks.length === 1 ? 'y' : 'ies'}, read from SEC filings, Polymarket and Kalshi, CBOE options and the disclosed trades of funds, insiders and officials: ${tks.map((x) => '$' + x).join(' ')}.` };
      }
      const day = $('#xr-day', box).value, all = dayEntries(ix, day).filter((e) => full || (e.revenue || 0) >= minOwner).sort((x, y) => (y.revenue || 0) - (x.revenue || 0));
      const long = new Date(day + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
      const ticks = all.map((e) => e.ticker).filter(Boolean).slice(0, 4);
      return { day, list: all.slice(0, 60).map((e) => ({ ticker: e.ticker, cik: e.cik, end: e.end, form: e.form })), what: `daily report ${day}`,
        title: all.length ? `Earnings filed ${new Date(day + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}: ${ticks.join(', ')}${all.length > 4 ? ` and ${all.length - 4} more` : ''}`
          : `Filings, trades and moves: ${new Date(day + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
        intro: all.length ? `${all.length} compan${all.length === 1 ? 'y' : 'ies'} filed quarterly results with the SEC on ${long}. Each chart shows where the revenue went: costs, profit and operating cash flow.`
          : `No company in the report filed quarterly results on ${long}. The day in filings, trades and moves:` };
    };
    $('#xr-form', box).addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const o = read(), P = pick(o);
      if (!P.list.length && o.mode === 'tickers') { say('Type at least one ticker'); return; }
      say('Reading the companies…');
      const [entries, wide] = await Promise.all([xrEntries(ix, P.list, o.kinds, say), P.day ? xrMarketWide(P.day, o.kinds) : []]);
      if (!entries.length && !wide.length) { say('None of these could be read'); return; }
      say('');
      articlePanel(articleCustom(entries, o.kinds, { ...P, full: o.full, wide }), P.what);
    });
    $('#xr-posts', box).addEventListener('click', async () => {
      const o = read(), P = pick(o);
      if (!P.list.length) { say('Nothing to write about'); return; }
      say('Writing the posts…');
      const entries = await xrEntries(ix, P.list.slice(0, 12), o.kinds.filter((k) => k !== 'earnings'), say);
      const out = $('#xr-out', box);
      out.innerHTML = entries.map((e) => `<h3>${t(e.name)} <span class="muted">${t(e.tk || '')}</span></h3>${e.items.map((p) => window.FFPosts.box(p)).join('') || '<p class="muted">No data for these posts.</p>'}`).join('');
      if (window.FFPosts) window.FFPosts.bind(out);
      say(entries.length ? '' : 'None of these could be read');
    });
  }
  // a day's filings: the owner's daily report as one article (the largest companies in full, the rest listed)
  function articleDay(day, items, full) {
    const B = [], images = [], long = new Date(day + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    const shown = items.slice(0, full), rest = items.slice(full);
    const tag = (e, c) => { const tk = e.ticker || ((c.profile.tickers || [])[0]) || ''; return tk ? `$${tk}` : S.dec(c.profile.name); };
    B.push({ k: 'p', text: `${items.length} compan${items.length === 1 ? 'y' : 'ies'} filed quarterly results with the SEC on ${long}. Each chart shows where the revenue went: costs, profit and operating cash flow.` });
    B.push({ k: 'h2', text: 'In this report' });
    B.push({ k: 'ul', items: items.slice(0, 30).map(({ e, c, q }) => `${tag(e, c)} ${S.dec(c.profile.name)} · ${S.dec(q.label)}: ${artLine(e, q)}`)
      .concat(items.length > 30 ? [`and ${items.length - 30} more on Filing Flows`] : []) });
    shown.forEach(({ e, c, q }) => {
      const name = S.dec(c.profile.name), url = `${artSite()}#c-${c.profile.cik}-${q.end}`;
      B.push({ k: 'h2', text: `${name} (${tag(e, c).replace(/^\$/, '')}) · ${S.dec(q.label)}` });
      B.push({ k: 'p', text: `${artForm(q)} filed ${date(q.filed)}: ${artLine(e, q)}.`, bold: `${artForm(q)} filed ${date(q.filed)}` });
      images.push({ n: images.length + 1, cap: `${name} ${S.dec(q.label)}: where the revenue went`, make: chartImage(q),
        file: `${e.ticker || c.profile.cik}-${S.dec(q.label)}-sankey.png` });
      B.push({ k: 'img', n: images.length, cap: images[images.length - 1].cap });
      (q.analysis || []).slice(0, 2).forEach((x) => B.push({ k: 'p', text: S.dec(x) }));
      B.push({ k: 'ul', links: [[url, `${name} on Filing Flows: interactive chart and notes`]] });
    });
    if (rest.length) {
      B.push({ k: 'h2', text: 'Also filed' });
      B.push({ k: 'ul', items: rest.slice(0, 40).map(({ e, c, q }) => `${tag(e, c)} ${S.dec(c.profile.name)} · ${S.dec(q.label)}: ${artLine(e, q)}`) });
    }
    B.push({ k: 'p', em: true, text: `All charts: ${artSite()} — figures read automatically from SEC filings by fixed rules; check the filing before relying on them. Not investment advice.` });
    const ticks = items.map(({ e, c }) => tag(e, c).replace(/^\$/, '')).slice(0, 4);
    const title = `Earnings filed ${new Date(day + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}: ${ticks.join(', ')}${items.length > 4 ? ` and ${items.length - 4} more` : ''}`;
    return { title: title.slice(0, 100), blocks: B, images };
  }
  // the article as HTML (what the editor keeps) and as plain text (what it gets when it keeps nothing)
  function articleHTML(a) {
    const lk = ([u, l]) => `<a href="${t(u)}">${t(l)}</a>`;
    return a.blocks.map((b) => {
      if (b.k === 'h2') return `<h2>${t(b.text)}</h2>`;
      if (b.k === 'img') return `<p><b>[Image ${b.n}]</b> <i>${t(b.cap)}</i></p>`;
      if (b.k === 'quote') return `<blockquote>${t(b.text)}<br><i>${t(b.src)}</i></blockquote>`;
      if (b.k === 'ul') return `<ul>${(b.links ? b.links.map((x) => `<li>${lk(x)}</li>`) : b.items.map((x) => `<li>${t(x)}</li>`)).join('')}</ul>`;
      const body = b.bold && b.text.startsWith(b.bold) ? `<b>${t(b.bold)}</b>${t(b.text.slice(b.bold.length))}` : t(b.text);
      return `<p>${b.em ? `<i>${body}</i>` : body}</p>`;
    }).join('\n');
  }
  function articleText(a) {
    return a.blocks.map((b) => {
      if (b.k === 'h2') return b.text.toUpperCase();
      if (b.k === 'img') return `[Image ${b.n}] ${b.cap}`;
      if (b.k === 'quote') return `“${b.text}” — ${b.src}`;
      if (b.k === 'ul') return (b.links ? b.links.map(([u, l]) => `• ${l}: ${u}`) : b.items.map((x) => `• ${x}`)).join('\n');
      return b.text;
    }).join('\n\n');
  }
  async function copyRich(html, text) {
    if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }) })]);
        return 'rich';
      } catch (e) { /* plain text below */ }
    }
    const native = window.FilingFlowsApp;
    if (native && typeof native.copyText === 'function') native.copyText(text);
    else await navigator.clipboard.writeText(text);
    return 'plain';
  }
  function articlePanel(a, what) {
    let m = $('#art-modal');
    if (m) m.remove();
    m = document.createElement('div');
    m.id = 'art-modal';
    m.className = 'art-modal';
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    m.setAttribute('aria-labelledby', 'art-title');
    const canImg = !!(window.ClipboardItem && navigator.clipboard && navigator.clipboard.write);
    m.innerHTML = `<div class="art-box">
      <div class="art-head"><div><span class="eyebrow">X Article · ${t(what)}</span><h2 id="art-title">${t(a.title)}</h2></div>
        <button type="button" class="btn small" data-art-close aria-label="Close">✕</button></div>
      <ol class="art-steps">
        <li><a class="btn small" href="https://x.com/compose/articles" target="_blank" rel="noopener">Open X Articles ↗</a> and press <b>Write</b> (X Premium).</li>
        <li><button class="btn small primary" type="button" data-art="title">Copy title</button> paste it into the title field.</li>
        <li><button class="btn small primary" type="button" data-art="text">Copy article text</button> click into the body and paste: headings, bold, lists and links come along, and
          <b>[Image 1]</b>${a.images.length > 1 ? ` … <b>[Image ${a.images.length}]</b>` : ''} mark where the charts go.${a.images.length && canImg
            ? ` <span class="muted">Or try <button class="btn small" type="button" data-art="all">Copy text with images</button>: one paste, if X’s editor keeps pasted images.</span>` : ''}</li>
        <li>${a.images.length ? `For each image: select its <b>[Image n]</b> line in the editor, press <b>Copy image n</b> below, then paste (Ctrl/⌘ V).${canImg ? '' : ' This browser cannot copy images: use Save and drag the file in.'}` : 'No charts in this article.'}</li>
      </ol>
      <div class="art-imgs">${a.images.map((x) => `<figure class="art-img"><div class="art-thumb" data-thumb="${x.n}"><span class="muted">Drawing…</span></div>
        <figcaption><b>Image ${x.n}</b> · ${t(x.cap)}</figcaption>
        <div class="row"><button class="btn small primary" type="button" data-art-img="${x.n}" ${canImg ? '' : 'disabled'}>Copy image ${x.n}</button>
          <button class="btn small" type="button" data-art-save="${x.n}">Save</button></div></figure>`).join('')}</div>
      <details class="art-prev"><summary>Preview the text</summary><div class="prose">${articleHTML(a)}</div></details>
      <p class="muted small" id="art-msg" role="status">Nothing is posted from here: you publish in X’s editor. Image 1 also works as the article’s cover.</p>
    </div>`;
    document.body.appendChild(m);
    const say = (x) => { const e = $('#art-msg', m); if (e) e.textContent = x; };
    const close = () => { m.remove(); document.removeEventListener('keydown', esc); };
    const esc = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', esc);
    m.addEventListener('click', (e) => { if (e.target === m) close(); });
    $('[data-art-close]', m).addEventListener('click', close);
    const blobs = {};
    const blobOf = (x) => (blobs[x.n] = blobs[x.n] || x.make());
    a.images.forEach((x) => blobOf(x).then((b) => {          // thumbnails (the same PNG the copy button puts on the clipboard)
      const box = $(`[data-thumb="${x.n}"]`, m);
      if (box) box.innerHTML = `<img alt="Image ${x.n}: ${t(x.cap)}" src="${URL.createObjectURL(b)}">`;
    }).catch((err) => { const box = $(`[data-thumb="${x.n}"]`, m); if (box) box.textContent = `Could not draw: ${err.message}`; }));
    $('[data-art="title"]', m).addEventListener('click', async (ev) => {
      const btn = ev.currentTarget;
      try { await copyRich(t(a.title), a.title); btn.textContent = 'Title copied'; say('Title copied: paste it into the title field.'); }
      catch (e) { say(`Could not copy: ${e.message}`); }
    });
    const all = $('[data-art="all"]', m);                // the text with the charts inside, in one paste (if X keeps them)
    if (all) all.addEventListener('click', async () => {
      const dataUrl = (b) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(b); });
      const html = Promise.all(a.images.map((x) => blobOf(x).then(dataUrl))).then((urls) => new Blob([articleHTML(a).replace(
        /<p><b>\[Image (\d+)\]<\/b> <i>(.*?)<\/i><\/p>/g, (_, n, cap) => `<p><img src="${urls[+n - 1]}" alt="${cap}"></p><p><i>${cap}</i></p>`)], { type: 'text/html' }));
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'text/html': html, 'text/plain': new Blob([articleText(a)], { type: 'text/plain' }) })]);
        all.textContent = 'Copied with images';
        say('Copied with the charts inside: paste into the body. If X drops the images, paste them one by one below.');
      } catch (e) { say(`Could not copy with images (${e.message}): use Copy article text and the image buttons.`); }
    });
    $('[data-art="text"]', m).addEventListener('click', async (ev) => {
      const btn = ev.currentTarget;
      try {
        const how = await copyRich(articleHTML(a), articleText(a));
        btn.textContent = 'Text copied';
        say(how === 'rich' ? 'Text copied with its formatting: paste it into the body, then add the images.'
          : 'Copied as plain text (this browser does not copy formatting): headings are the lines in capitals.');
      } catch (e) { say(`Could not copy: ${e.message}`); }
    });
    $$('[data-art-img]', m).forEach((b) => b.addEventListener('click', async () => {
      const x = a.images[+b.dataset.artImg - 1];
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blobOf(x) })]);   // the promise keeps Safari's gesture
        b.textContent = `Image ${x.n} copied`;
        say(`Image ${x.n} copied: select the [Image ${x.n}] line in the editor and paste.`);
      } catch (e) { say(`Could not copy the image (${e.message}): use Save and drag the file in.`); }
    }));
    $$('[data-art-save]', m).forEach((b) => b.addEventListener('click', async () => {
      const x = a.images[+b.dataset.artSave - 1];
      try { const res = await saveBlob(await blobOf(x), x.file.replace(/[^A-Za-z0-9.-]+/g, '-')); say(res === 'saved' ? `Saved ${x.file}` : 'Download unavailable here'); }
      catch (e) { say(`Could not save: ${e.message}`); }
    }));
    $('[data-art="title"]', m).focus();
  }

  // "what changed" bullets vs the previous quarter and vs the year-ago quarter
  function changesHTML(q) {
    return [q.compare, q.compare_y].filter((c) => c && c.bullets && c.bullets.length)
      .map((c) => `<h3>What changed vs ${t(c.vs)}</h3><ul class="changes">${c.bullets.map((b) => `<li>${t(b)}</li>`).join('')}</ul>`).join('');
  }

  function introHTML(intro) {
    if (!intro) return '';
    const text = typeof intro === 'string' ? intro : intro.text;
    if (!text) return '';
    const url = intro.url, filed = intro.filed, when = filed ? ` filed ${date(filed)}` : '';
    const where = intro.source === '8-K' ? `earnings release (8-K)${when}, “About” section`
      : intro.source === '6-K' ? `results release (6-K)${when}, “About” section`
      : intro.source === '10-Q' ? `10-Q${when}, Note 1 to the financial statements (no 10-K on file yet)`
      : `10-K${when}, Item 1. Business`;
    const long = text.length > 220;                           // three lines, then "More": the chart comes first
    return `<div class="intro${long ? ' clamp' : ''}"><p class="intro-text">${t(text)}</p>${long ? '<button type="button" class="intro-more" aria-expanded="false">More</button>' : ''}<span class="src">Quoted verbatim from the company’s ${where}${
      url ? ` · <a href="${t(url)}" target="_blank" rel="noopener">open ↗</a>` : ''}</span></div>`;
  }

  function historyTable(qs, cik) {
    const max = Math.max(...qs.map((x) => x.headline.revenue || 0));
    const ocf = (x) => { const n = x.nodes.find((m) => m.id === 'ocf'); return n ? n.v : null; };
    return `<div class="section"><div class="section-head"><h2>History</h2><span class="muted">${qs.length} quarters on file</span></div>
      <div class="tbl-wrap"><table><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class="num">Revenue</th><th class="num">Y/Y</th>
      <th class="num">Op. margin</th><th class="num">Net earnings</th><th class="num">Operating cash flow</th></tr></thead><tbody>
      ${qs.map((x) => row(`c-${cik}-${x.end}`, [`<td><a href="#c-${cik}-${x.end}">${t(x.label)}</a></td>`, `<td class="mono">${t(x.form)}</td>`,
        `<td>${date(x.filed)}</td>`,
        `<td class="num"><span class="bar-cell"><i style="width:${Math.max(2, (x.headline.revenue / max) * 90).toFixed(0)}px"></i>${money(x.headline.revenue)}</span></td>`,
        `<td class="num ${tone(x.headline.yoy)}">${pct(x.headline.yoy)}</td>`, `<td class="num">${margin(x.headline.om)}</td>`,
        `<td class="num">${money(x.headline.ni)}</td>`, `<td class="num">${money(ocf(x))}</td>`])).join('')}
      </tbody></table></div></div>`;
  }

  // ---------- where a figure comes from: the line or calculation, the filing it is in, links to check it ----------
  function sourceBlock(n, cite, cik) {
    if (!n.source && !cite) return '';
    const links = [];
    if (cite && cite.doc) links.push([cite.doc, /Exhibit 99/.test(cite.text) ? 'Press release' : 'The filing']);
    if (cite && cite.ix) links.push([cite.ix, 'Inline XBRL viewer']);
    const tag = /^us-gaap:(\w+)$/.exec(n.tag || '');
    if (tag && cik) links.push([`https://data.sec.gov/api/xbrl/companyconcept/CIK${String(cik).padStart(10, '0')}/us-gaap/${tag[1]}.json`,
      `XBRL data for ${tag[1]}`]);
    if (cite && cite.index) links.push([cite.index, 'Filing index']);
    return `<div class="node-src"><div class="eyebrow">Source</div>
      ${n.source ? `<p>${t(n.source)}</p>` : ''}
      ${cite ? `<p class="cite">${t(cite.text)}.</p>` : ''}
      ${links.length ? `<p class="links">${links.map(([u, l]) => `<a href="${t(u)}" target="_blank" rel="noopener">${t(l)} ↗</a>`).join(' · ')}</p>` : ''}</div>`;
  }

  // ---------- a node's last five quarters (or fiscal years), in its note ----------
  // Two small panels on one time axis (never two scales on one axis): the amount as columns, and its change against a
  // year earlier as a line. The current period is drawn at full strength; a readout above names the hovered period.
  const TREND_N = 5;
  function nodeAt(spec, id) {
    const find = (k) => (spec.nodes || []).find((x) => x.id === k);
    const own = find(id);
    if (own) return { v: own.v, y: own.y, q: own.q, basis: own.basis || '' };
    if (id === 'fcf' || id === 'fcf_neg') {                       // free cash flow changes sides when it turns negative
      const o = find('ocf'), c = find('capex');
      if (!o || !c || o.v == null || c.v == null || c.basis) return null;
      const sg = id === 'fcf' ? 1 : -1, d = (k) => (o[k] != null && c[k] != null ? sg * (o[k] - c[k]) : null);
      return { v: sg * (o.v - c.v), y: d('y'), q: d('q') };
    }
    return null;
  }
  function trendSeries(specs, cur, id, years) {
    const keep = specs.filter((x) => x.end <= cur.end).slice(0, TREND_N).reverse();
    const chg = (v, b) => (v != null && b != null && v > 0 && b > 0 ? (v / b - 1) * 100 : null);   // n/m when ≤ 0
    // a company-reported figure (its own free cash flow definition) is only lined up with the same definition
    const basis = (nodeAt(cur, id) || {}).basis || '';
    const pts = keep.map((x) => {
      let a = nodeAt(x, id) || {};
      if ((a.basis || '') !== basis) a = {};
      return { label: x.label, end: x.end, cur: x.end === cur.end, v: a.v == null ? null : a.v,
        yoy: chg(a.v, a.y), qoq: years ? null : chg(a.v, a.q) };
    });
    return { years: !!years, pts: pts.filter((p) => p.v != null) };
  }
  const MARK_ROLE = { rev: 'rev', profit: 'profit', cost: 'cost', noncash: 'noncash' };
  function trendBlock(series, n) {
    const pts = series && series.pts;
    if (!pts || pts.length < 2) return '';
    const panels = [['yoy', series.years ? 'Change vs the year before' : 'Change vs a year earlier']]
      .concat(series.years ? [] : [['qoq', 'Change vs the previous quarter']]);
    const W = 320, PL = 6, PR = 40, TOP = 18, BH = 92, GAP = 22, LH = 58, XL = 18, SHORT = 20;   // PR: room for end labels
    const enough = (key) => pts.filter((p) => p[key] != null).length >= 2;
    const tops = [];                                          // where each change panel starts (a short note when empty)
    let yAt = TOP + BH + GAP;
    panels.forEach(([key]) => { tops.push(yAt); yAt += enough(key) ? LH + GAP : SHORT; });
    const H = yAt - GAP + XL + (enough(panels[panels.length - 1][0]) ? 0 : GAP);
    const role = MARK_ROLE[n.color] || 'rev';
    const band = (W - PL - PR) / pts.length, bw = Math.min(24, band * 0.5);
    const cx = (i) => PL + band * i + band / 2;
    const vals = pts.map((p) => p.v), vmax = Math.max(0, ...vals), vmin = Math.min(0, ...vals);
    const vy = (v) => TOP + (vmax - v) / ((vmax - vmin) || 1) * BH;
    const base = vy(0);
    const f = (x) => x.toFixed(1);
    const col = (p, i) => {                                         // 4px rounded data end, square at the baseline
      const x = cx(i) - bw / 2, top = vy(Math.max(p.v, 0)), bot = vy(Math.min(p.v, 0)), r = Math.min(4, Math.abs(bot - top) / 2);
      const d = p.v >= 0
        ? `M${f(x)} ${f(bot)}V${f(top + r)}Q${f(x)} ${f(top)} ${f(x + r)} ${f(top)}H${f(x + bw - r)}Q${f(x + bw)} ${f(top)} ${f(x + bw)} ${f(top + r)}V${f(bot)}Z`
        : `M${f(x)} ${f(top)}V${f(bot - r)}Q${f(x)} ${f(bot)} ${f(x + r)} ${f(bot)}H${f(x + bw - r)}Q${f(x + bw)} ${f(bot)} ${f(x + bw)} ${f(bot - r)}V${f(top)}Z`;
      return `<path class="tr-col${p.cur ? ' cur' : ''}" data-i="${i}" d="${d}" fill="var(--mk-${role})"/>`;
    };
    const last = pts.length - 1, lp = pts[last];
    const capY = lp.v >= 0 ? vy(lp.v) - 5 : vy(lp.v) + 13;
    // a change panel: its own zero line and scale (each panel reads on its own; never two scales on one axis)
    const linePanel = ([key, title], k) => {
      const y0 = tops[k];
      const vals = pts.map((p) => p[key]).filter((x) => x != null);
      const head = `<text class="tr-cap" x="${PL}" y="${y0 - 4}">${title}${vals.length < 2 ? ': not enough periods on file' : ''}</text>`;
      if (vals.length < 2) return head;
      const ymax = Math.max(0, ...vals), ymin = Math.min(0, ...vals), span = (ymax - ymin) || 1;
      const yy = (v) => y0 + 8 + (ymax - v) / span * (LH - 16);
      const segs = [];
      let run = [];
      pts.forEach((p, i) => { if (p[key] == null) { if (run.length) segs.push(run); run = []; } else run.push([cx(i), yy(p[key])]); });
      if (run.length) segs.push(run);
      const li = pts.map((p) => p[key] != null).lastIndexOf(true);
      const ly = yy(pts[li][key]);                                             // the value at the end of the line
      return head + `<line x1="${PL}" x2="${W - PR}" y1="${f(yy(0))}" y2="${f(yy(0))}" class="tr-axis"/>` +
        segs.map((sg) => `<polyline points="${sg.map(([x, y]) => `${f(x)},${f(y)}`).join(' ')}" class="tr-line"/>`).join('') +
        pts.map((p, i) => (p[key] == null ? '' : `<circle class="tr-dot${p.cur ? ' cur' : ''}" data-i="${i}" cx="${f(cx(i))}" cy="${f(yy(p[key]))}" r="4"/>`)).join('') +
        `<text class="tr-lab" x="${f(cx(li) + 9)}" y="${f(ly + 4)}" text-anchor="start">${pct(pts[li][key])}</text>`;
    };
    const line = panels.map(linePanel).join('');
    const chgs = (p) => [p.yoy != null ? `Y/Y ${pct(p.yoy)}` : null, p.qoq != null ? `${p.period === 'half' ? 'H/H' : 'Q/Q'} ${pct(p.qoq)}` : null].filter(Boolean);
    const hits = pts.map((p, i) => `<rect class="tr-hit" data-i="${i}" x="${f(PL + band * i)}" y="0" width="${f(band)}" height="${H - XL}" fill="transparent"><title>${t(p.label)}: ${[money(p.v)].concat(chgs(p)).join(' · ')}</title></rect>`).join('');
    const unit = series.years ? 'fiscal years' : 'quarters';
    const aria = `${S.dec(n.name)}, last ${pts.length} ${unit}: ` + pts.map((p) => `${S.dec(p.label)} ${money(p.v)}${chgs(p).length ? ` (${chgs(p).join(', ')})` : ''}`).join('; ');
    const data = t(JSON.stringify(pts.map((p) => [S.dec(p.label), money(p.v)].concat(chgs(p)))));
    return `<figure class="trend" data-pts="${data}">
      <figcaption><span class="tr-title">Last ${pts.length} ${unit}</span><span class="tr-read" aria-live="polite"></span></figcaption>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${t(aria)}">
        <text class="tr-cap" x="${PL}" y="11">Amount</text>
        <line x1="${PL}" x2="${W - PR}" y1="${f(base)}" y2="${f(base)}" class="tr-axis"/>
        ${pts.map(col).join('')}
        <text class="tr-lab" x="${f(cx(last))}" y="${f(capY)}" text-anchor="middle">${money(lp.v)}</text>
        ${line}
        ${pts.map((p, i) => `<text class="tr-x${p.cur ? ' cur' : ''}" x="${f(cx(i))}" y="${H - 4}" text-anchor="middle">${t(p.label)}</text>`).join('')}
        ${hits}
      </svg></figure>`;
  }
  function wireTrend(root) {
    const fig = $('.trend', root);
    if (!fig) return;
    const pts = JSON.parse(S.dec(fig.dataset.pts));
    const read = $('.tr-read', fig);
    const show = (i) => {
      read.textContent = pts[i].join(' · ');                    // "Q3 FY26 · $2.4B · Y/Y +15% · Q/Q +10%"
      $$('[data-i]', fig).forEach((el) => el.classList.toggle('on', +el.dataset.i === i));
    };
    show(pts.length - 1);
    $$('.tr-hit', fig).forEach((h) => {
      h.addEventListener('pointerenter', () => show(+h.dataset.i));
      h.addEventListener('click', () => show(+h.dataset.i));
    });
    $('svg', fig).addEventListener('pointerleave', () => show(pts.length - 1));
  }

  // ---------- "Compare any two periods" (readers who turned it on in their alerts) ----------
  // The page cannot read SEC itself (no CORS), so the request goes into Supabase; the GitHub workflow draws the
  // comparison from SEC data within a few minutes and writes it back into the reader's row; this page shows it.
  const monthYear = (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  function periodLabel(co, kind, end) {
    const x = ((co.periods || {})[kind] || []).find((y) => y.end === end) ||
      (kind === 'fy' ? (co.years || []) : co.quarters).find((y) => y.end === end);
    return x ? x.label : `${kind === 'fy' ? 'year' : 'quarter'} ended ${date(end)}`;
  }
  function tableMissing(err) {                       // supabase/schema.sql not run again since this feature arrived
    return !!err && (err.code === '42P01' || err.code === 'PGRST205' || err.code === 'PGRST204' || /does not exist|schema cache/i.test(err.message || ''));
  }
  const OWNER_UPDATE = 'The site owner has to update the database first (run supabase/schema.sql again)';

  async function initCompare(co, cik) {
    const btn = $('#cmp-open'), panel = $('#cmp-panel');
    if (!btn) return;
    const cl = await sb();
    if (!cl || !(await currentUser())) return;
    const pr = acct.prefs || await loadPrefs().catch(() => null);
    if (!pr || !pr.custom_compare || !btn.isConnected) return;
    btn.hidden = false;
    btn.addEventListener('click', () => {
      const open = panel.hidden;
      panel.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      btn.classList.toggle('open', open);
      if (open && !panel.dataset.ready) comparePanel(panel, co, cik, cl);
      if (open) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  }

  function comparePanel(panel, co, cik, cl) {
    panel.dataset.ready = '1';
    const per = co.periods || { q: [], fy: [] };
    const rows = new Map();                          // fiscal year -> { q: {1..4: period}, y: period }
    const row = (fy) => { if (!rows.has(fy)) rows.set(fy, { fy, q: {}, y: null }); return rows.get(fy); };
    (per.q || []).forEach((x) => { if (x.fy && x.q) row(x.fy).q[x.q] = x; });
    (per.fy || []).forEach((x) => { if (x.fy) row(x.fy).y = x; });
    const years = [...rows.values()].sort((a, b) => b.fy - a.fy);
    const calendar = !(per.q || []).some((x) => / FY\d/.test(x.label));
    const fyName = (fy) => (calendar ? String(fy) : `FY${String(fy).slice(2)}`);
    const cell = (x, kind) => (x ? `<td><label class="pick" title="${t(x.label)} · ${kind === 'fy' ? 'fiscal year' : 'quarter'} ended ${date(x.end)}">
      <input type="checkbox" data-end="${x.end}" data-kind="${kind}" data-label="${t(x.label)}"><span>${monthYear(x.end)}</span></label></td>` : '<td class="none">—</td>');
    panel.innerHTML = `
      <div class="section-head"><h2>Compare any two periods</h2><span class="muted">Tick two quarters, or two full fiscal years. Drawn from SEC data on request, usually within 1–3 minutes.</span></div>
      ${years.length ? `<div class="tbl-wrap"><table class="period-grid"><thead><tr><th>Fiscal year</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Full year</th></tr></thead><tbody>
        ${years.map((r) => `<tr><th>${fyName(r.fy)}</th>${[1, 2, 3, 4].map((n) => cell(r.q[n], 'q')).join('')}${cell(r.y, 'fy')}</tr>`).join('')}
        </tbody></table></div>
      <div class="cmp-bar"><span id="cmp-sum">Pick two periods</span>
        <button class="btn small" type="button" id="cmp-swap" disabled title="Which period is drawn, and which it is compared with">⇄ Swap</button>
        <button class="btn primary" type="button" id="cmp-go" disabled>Draw comparison</button></div>`
        : '<p class="muted">The list of this company’s periods arrives with its next update (each scan adds it for a few companies at a time).</p>'}
      <p class="muted small" id="cmp-msg" role="status"></p>
      <div id="cmp-recent"></div>`;
    let sel = [], swapped = false;
    const msg = (x) => { $('#cmp-msg', panel).textContent = x || ''; };
    const pair = () => {
      if (sel.length !== 2) return null;
      const [x, y] = sel.slice().sort((m, n) => (m.dataset.end < n.dataset.end ? 1 : -1));   // the later one is drawn
      return swapped ? [y, x] : [x, y];
    };
    const update = () => {
      const ab = pair();
      $('#cmp-sum', panel).innerHTML = ab ? `<b>${ab[0].dataset.label}</b> compared with <b>${ab[1].dataset.label}</b>`
        : sel.length === 1 ? `${sel[0].dataset.label} compared with …` : 'Pick two periods';
      $('#cmp-go', panel).disabled = !ab;
      $('#cmp-swap', panel).disabled = !ab;
    };
    $$('input[data-end]', panel).forEach((box) => box.addEventListener('change', () => {
      msg('');
      if (box.checked) {
        if (sel.length && sel[0].dataset.kind !== box.dataset.kind) {
          sel.forEach((x) => { x.checked = false; });
          sel = [];
          msg('Quarters are compared with quarters, fiscal years with fiscal years.');
        }
        sel.push(box);
        if (sel.length > 2) sel.shift().checked = false;
      } else {
        sel = sel.filter((x) => x !== box);
      }
      swapped = false;
      update();
    }));
    if (years.length) {
      $('#cmp-swap', panel).addEventListener('click', () => { swapped = !swapped; update(); });
      $('#cmp-go', panel).addEventListener('click', async (ev) => {
        const ab = pair(), go = ev.currentTarget;      // read before any await: the event forgets its target afterwards
        if (!ab) return;
        go.disabled = true;
        msg('Asking…');
        const r = await cl.from('chart_requests').insert({ cik: +cik, kind: ab[0].dataset.kind, a_end: ab[0].dataset.end, b_end: ab[1].dataset.end })
          .select('id').single();
        if (r.error) {
          go.disabled = false;
          msg(tableMissing(r.error) ? OWNER_UPDATE : /limit/i.test(r.error.message) ? 'Limit reached: 20 comparisons a day' : `Could not ask: ${r.error.message}`);
          return;
        }
        location.hash = `c-${cik}-cmp-${r.data.id}`;
      });
    }
    recentComparisons($('#cmp-recent', panel), co, cik, cl);
  }

  async function recentComparisons(box, co, cik, cl) {
    const r = await cl.from('chart_requests').select('id,kind,a_end,b_end,status,created_at').eq('cik', +cik)
      .order('created_at', { ascending: false }).limit(8);
    if (!box.isConnected || r.error || !r.data || !r.data.length) return;
    const word = { pending: 'waiting', working: 'drawing', done: 'ready', failed: 'failed' };
    box.innerHTML = `<h3>Your comparisons of this company</h3><ul class="cmp-list">${r.data.map((x) =>
      `<li><a href="#c-${cik}-cmp-${x.id}">${t(periodLabel(co, x.kind, x.a_end))} vs ${t(periodLabel(co, x.kind, x.b_end))}</a>
       <span class="muted">· ${word[x.status] || t(x.status)} · asked ${date(x.created_at)}</span></li>`).join('')}</ul>`;
  }

  async function showComparison(body, co, id, ticker) {
    body.innerHTML = '<div class="cmp-wait"><div class="loading">Loading your comparison…</div></div>';
    const cl = await sb();
    const user = cl ? await currentUser() : null;
    if (!cl || !user) {
      body.innerHTML = `<div class="cmp-wait"><h2>Sign in to see this comparison</h2><p class="muted">Comparisons you ask for are kept with your account.</p>
        <p><a class="btn primary" href="#account">Sign in</a></p></div>`;
      prefs.set('after-signin', location.hash.replace(/^#/, ''));
      return;
    }
    const started = Date.now();
    const poll = async () => {
      if (!body.isConnected) return;
      const r = await cl.from('chart_requests').select('*').eq('id', +id).maybeSingle();
      if (!body.isConnected) return;
      const row = r.data;
      if (r.error || !row) {
        body.innerHTML = `<div class="cmp-wait"><h2>This comparison is not available</h2><p class="muted">${r.error ? t(r.error.message) : 'It may belong to another account.'}</p></div>`;
        return;
      }
      const a = periodLabel(co, row.kind, row.a_end), b = periodLabel(co, row.kind, row.b_end);
      if (row.status === 'pending' || row.status === 'working') {
        const secs = Math.max(0, Math.round((Date.now() - new Date(row.created_at).getTime()) / 1000));
        body.innerHTML = `<div class="cmp-wait"><div class="spinner" aria-hidden="true"></div>
          <h2>${t(a)} compared with ${t(b)}</h2>
          <p>${row.status === 'working' ? 'Reading both filings from SEC and drawing the chart…' : 'Waiting for the next run of the request workflow…'}</p>
          <p class="muted">Usually 1–3 minutes (up to 10 when nothing wakes the workflow) · asked ${secs < 90 ? `${secs} s` : `${Math.round(secs / 60)} min`} ago.
            This page updates itself; you can also leave and find it later under ⇄ Compare any two.</p></div>`;
        setTimeout(poll, Date.now() - started < 30 * 60e3 ? 5000 : 30000);
        return;
      }
      if (row.status === 'failed') {
        body.innerHTML = `<div class="cmp-wait"><h2>Could not draw ${t(a)} compared with ${t(b)}</h2><p>${t(row.error || 'Unknown error')}</p>
          <p class="muted">Pick two other periods under ⇄ Compare any two.</p></div>`;
        return;
      }
      renderComparison(body, co, row, ticker);
    };
    poll();
  }

  function renderComparison(body, co, row, ticker) {
    const spec = row.result, cu = spec.custom || {}, p = co.profile, cik = p.cik;
    const slug = (x) => String(x || '').replace(/\s+/g, '-');
    body.innerHTML = `<div class="cmp-head"><div class="eyebrow">Your comparison · ${cu.kind === 'fy' ? 'fiscal years' : 'quarters'}</div>
      <h2>${t(cu.a_label)} compared with ${t(cu.b_label)}</h2>
      <p class="muted">Drawn on request from SEC data${row.done_at ? ` on ${date(row.done_at)}` : ''}. Band width is ${t(cu.a_label)}; a dark strip is the increase over ${t(cu.b_label)}.
        <a href="#c-${cik}">Back to the latest chart</a></p></div>`;
    const ui = chartUI(spec, {
      company: S.dec(p.name), form: spec.form, label: spec.label, docUrl: spec.doc_url, custom: true, cik: p.cik,
      slug: slug(`${ticker || cik}-${cu.a_label}`), vsSlug: slug(cu.b_label), onView: () => {},
    });
    body.appendChild(ui);
    const acc = accession(spec.index_url), accB = accession(cu.b_index_url);
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose"><h2>Analysis</h2>${(spec.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        ${changesHTML(spec)}
        <p class="note-rule">Written by fixed rules from the reported figures (no language model).</p></div>
      <div class="prose"><h2>Filings</h2>
        <dl class="facts">
          <dt>${t(cu.a_label)}</dt><dd><span class="mono">${t(spec.form)}</span> filed ${date(spec.filed)}${acc ? ` · <span class="mono">${acc}</span>` : ''}${
            spec.index_url ? ` · <a href="${t(spec.index_url)}" target="_blank" rel="noopener">filing ↗</a>` : ''}</dd>
          <dt>${t(cu.b_label)}</dt><dd>filed ${date(cu.b_filed)}${accB ? ` · <span class="mono">${accB}</span>` : ''}${
            cu.b_index_url ? ` · <a href="${t(cu.b_index_url)}" target="_blank" rel="noopener">filing ↗</a>` : ''}</dd>
          <dt>Data</dt><dd>${cu.kind === 'fy' ? 'Full-year values' : 'Quarterly values (fourth quarters and cash flows as year-to-date minus the prior year-to-date)'} from SEC’s XBRL company facts; revenue lines from the filings’ own XBRL instances when both report them the same way</dd>
        </dl></div>`;
    body.appendChild(text);
  }

  // ---------- a company the site has no chart for yet (found by the search) ----------
  let secList = null;
  function secCompanies() {                          // [cik, ticker, name] for every company on SEC's ticker list
    if (!secList) secList = getJSON('companies.json').then((d) => d.companies || []).catch(() => { secList = null; return []; });
    return secList;
  }
  async function cikForTicker(tk) {                  // BRK.B, BRK/B and BRK-B are the same ticker; SEC writes BRK-B
    const norm = (x) => String(x || '').toUpperCase().replace(/[./\s]+/g, '-');
    const want = norm(tk), all = await secCompanies();
    const hit = all.find((x) => norm(x[1]) === want) || all.find((x) => norm(x[1]).replace(/-/g, '') === want.replace(/-/g, ''));
    return hit ? hit[0] : null;
  }
  async function askForCompany(cik) {
    const cl = await sb();
    const r = await cl.from('company_requests').insert({ cik: +cik });
    if (r.error && r.error.code === '23505') return { ok: true, msg: 'Already asked: the next scan builds it' };
    if (r.error && tableMissing(r.error)) return { ok: false, msg: OWNER_UPDATE };
    if (r.error && /limit/i.test(r.error.message)) return { ok: false, msg: 'Limit reached: 10 companies a day' };
    if (r.error) return { ok: false, msg: `Could not ask: ${r.error.message}` };
    if (await ownerVerified().catch(() => false))   // the database marks the owner's requests: a short scan starts now (scan.yml)
      return { ok: true, msg: 'Asked (owner fast lane): a short scan starts within a minute and repeats until it is built, usually 10–20 minutes' };
    return { ok: true, msg: 'Asked: the next scan reads its filings from SEC' };
  }
  async function missingCompany(cik) {
    const here = live();
    setNav('');
    const all = await secCompanies();
    const hit = all.find((x) => x[0] === +cik);
    const name = hit ? hit[2] : `CIK ${cik}`, ticker = hit ? hit[1] : '';
    if (!here()) return;
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a></div>
        <h1>${t(name)}</h1>
        <div class="meta">${ticker ? `<span class="tag mono">${t(ticker)}</span>` : ''}<span>CIK <span class="mono">${+cik}</span></span>
          <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${+cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">EDGAR filings ↗</a></div>
      </div>
      <section class="build-box" id="build-box">
        <h2>No charts for this company yet</h2>
        <p>Companies are drawn when they file a 10-Q, 10-K or earnings release during the regular scan (every 15 minutes).
          <span id="build-how">Ask for it and the next scan reads its last five 10-Qs and two 10-Ks from SEC; this page fills in by itself (usually 10–30 minutes).</span></p>
        <div class="row"><button class="btn primary" id="build-go" type="button" hidden>Build its charts</button>
          <span class="muted" id="build-msg" role="status"></span></div>
      </section>`;
    const box = $('#build-box'), btn = $('#build-go'), msg = (x) => { $('#build-msg').textContent = x || ''; };
    const cl = await sb();
    if (!cl) {
      $('#build-how').textContent = 'Its charts appear here after its next filing.';
      return;
    }
    btn.hidden = false;
    let watching = false;
    const watch = async () => {                      // the scan publishes data/c/<cik>.json; the request row says how it went
      if (!box.isConnected) return;
      watching = true;
      btn.disabled = true;
      try {
        await getJSON(`c/${+cik}.json`, true);
        if (box.isConnected) { acct.flash = 'Its charts are ready'; route(); }
        return;
      } catch (e) { /* not published yet */ }
      const r = await cl.from('company_requests').select('status,error,created_at').eq('cik', +cik)
        .order('created_at', { ascending: false }).limit(1);
      const last = r.data && r.data[0];
      if (!box.isConnected) return;
      if (last && last.status === 'failed') {
        msg(`Not built: ${last.error || 'SEC has no 10-Q or 10-K figures for it'}`);
        btn.disabled = false;
        watching = false;
        return;
      }
      msg(last && last.status === 'done' ? 'Built: publishing the site…'
        : last && last.status === 'queued' ? 'The scan is reading its filings from SEC…' : 'Waiting for the next scan…');
      setTimeout(watch, 20000);
    };
    if (await currentUser()) {
      const r = await cl.from('company_requests').select('status').eq('cik', +cik).order('created_at', { ascending: false }).limit(1);
      if (r.data && r.data[0] && ['pending', 'queued', 'done'].includes(r.data[0].status)) watch();
    }
    btn.addEventListener('click', async () => {
      if (!(await currentUser())) {
        prefs.set('pending-build', String(+cik));
        prefs.set('after-signin', `c-${+cik}`);
        location.hash = 'account';
        return;
      }
      btn.disabled = true;
      const res = await askForCompany(cik);
      msg(res.msg);
      if (res.ok && !watching) setTimeout(watch, 3000);
      else btn.disabled = false;
    });
  }

  async function group(level, id, cal) {
    const here = live();
    setNav('sectors');
    const [ix, g] = await Promise.all([getJSON('index.json'), getJSON(`${level}/${id}.json`)]);
    const q = (cal && g.quarters.find((x) => x.cal === cal)) || g.quarters[0];
    const sectors = ix.sector_names || {};
    const byCik = new Map(ix.companies.map((c) => [String(c.cik), c]));
    const secId = level === 'i' ? (ix.industries.find((x) => x.id === id) || {}).sector : id;
    const inds = level === 's' ? ix.industries.filter((x) => x.sector === id) : [];
    const total = q.companies.reduce((s, c) => s + c.revenue, 0);
    if (!here()) return;
    app.innerHTML = `
      <div class="page-head">
        <div class="crumbs"><a href="#home">Latest</a><span>/</span><a href="#sectors">Sectors</a>${
          level === 'i' && secId ? `<span>/</span>${ix.sectors.some((s) => s.id === secId) ? `<a href="#s-${secId}">${t(sectors[secId])}</a>` : t(sectors[secId] || '')}` : ''}</div>
        <h1>${t(g.name)}${level === 's' ? ' sector' : ''}</h1>
        <div class="meta">${level === 's' ? `<button class="btn follow" type="button" hidden data-follow="sector:${t(id)}">☆ Follow</button>` : ''}
          <span class="tag">${level === 's' ? 'Sector' : 'Industry · SIC ' + t(g.id)}</span>
          <span>${q.count} companies</span><span>Fiscal quarters ending in calendar ${calLabel(q.cal)}</span></div>
        ${freshLine(null, ix.generated).replace('site data updated', `${q.count} companies’ filings for ${calLabel(q.cal)} · site data updated`)}
      </div>
      <div class="pills" aria-label="Calendar quarter">${g.quarters.map((x) => `<a class="pill ${x === q ? 'on' : ''}" href="#${level}-${id}-${x.cal}">${calLabel(x.cal)}</a>`).join('')}</div>
      <div id="body"></div>`;
    const body = $('#body');
    body.appendChild(chartUI(q, {
      group: true, groupName: S.dec(g.name), label: calLabel(q.cal), companies: q.companies,
      slug: `${id}-${q.cal}`, form: '',
    }));
    const text = document.createElement('div');
    text.className = 'cols';
    text.innerHTML = `
      <div class="prose"><h2>Analysis</h2>${(q.analysis || []).map((x) => `<p>${t(x)}</p>`).join('')}
        ${changesHTML(q)}
        <p class="note-rule">Sum of each company’s fiscal quarter that ends in this calendar quarter. Written by fixed rules from the reported figures.</p></div>
      <div class="prose">${inds.length ? `<h2>Industries</h2><div class="cards">${inds.map((x) => `<a class="card" href="#i-${x.id}"><div class="t"><span>${t(x.name)}</span></div>
        <div class="n">${x.count} companies · ${calLabel(x.cal)}</div></a>`).join('')}</div>` : ''}</div>`;
    body.appendChild(text);
    if (window.FFModel && level === 's') {                 // the sector's growth model (web/model.js)
      const mbox = document.createElement('section');
      mbox.className = 'section';
      mbox.hidden = true;
      body.appendChild(mbox);
      window.FFModel.sector(mbox, id);
    }
    const tbl = document.createElement('div');
    tbl.className = 'section';
    tbl.innerHTML = `<div class="section-head"><h2>Companies</h2><span class="muted">${calLabel(q.cal)} revenue</span></div>
      <div class="tbl-wrap"><table><thead><tr><th class="num">#</th><th>Company</th><th>Period</th><th class="num">Revenue</th><th class="num">Share</th><th class="num">Y/Y</th><th class="num">Op. margin</th></tr></thead><tbody>
      ${q.companies.map((m, i) => {
        const c = byCik.get(String(m.cik)) || { cik: m.cik, ticker: m.ticker, name: m.ticker };
        const latest = c.cal === q.cal;
        return row(`c-${m.cik}`, [`<td class="num muted">${i + 1}</td>`, companyCell(c), `<td>${latest ? t(c.label) : calLabel(q.cal)}</td>`,
          `<td class="num">${money(m.revenue)}</td>`, `<td class="num">${margin((m.revenue / total) * 100)}</td>`,
          `<td class="num ${latest ? tone(c.yoy) : ''}">${latest ? pct(c.yoy) : '—'}</td>`, `<td class="num">${latest ? margin(c.om) : '—'}</td>`]);
      }).join('')}</tbody></table></div>`;
    body.appendChild(tbl);
    bindRows(tbl);
  }

  async function sectorsPage() {
    const here = live();
    setNav('sectors');
    const ix = await getJSON('index.json');
    const names = ix.sector_names || {};
    const counts = {};
    ix.companies.forEach((c) => { counts[c.sector] = (counts[c.sector] || 0) + 1; });
    const have = new Map(ix.sectors.map((s) => [s.id, s]));
    if (!here()) return;
    app.innerHTML = `
      <div class="page-head"><div class="eyebrow">Sectors and industries</div><h1>Combined Sankeys by sector and industry</h1>
        <p class="muted" style="max-width:72ch">Companies are grouped by the SIC code on their EDGAR profile. A group chart adds up every company whose fiscal quarter ends in the same calendar quarter; the ten largest appear by name.</p></div>
      ${Object.entries(names).map(([id, name]) => {
        const s = have.get(id), inds = ix.industries.filter((x) => x.sector === id);
        if (!counts[id] && !s) return '';
        return `<section class="section"><div class="section-head"><h2>${s ? `<a href="#s-${id}">${t(name)}</a>` : t(name)}</h2>
          <span class="muted">${counts[id] || 0} companies with filings on record${s ? ` · combined chart for ${calLabel(s.cal)}` : ''}</span></div>
          ${inds.length ? `<div class="cards">${inds.map((x) => `<a class="card" href="#i-${x.id}"><div class="t"><span>${t(x.name)}</span></div>
          <div class="n">SIC ${t(x.id)} · ${x.count} companies · ${calLabel(x.cal)}</div></a>`).join('')}</div>` : ''}</section>`;
      }).join('')}`;
  }

  async function methodPage() {
    const here = live();
    setNav('method');
    const ix = await getJSON('index.json').catch(() => ({}));
    const au = ix.release_audit || { checked: 0, matched: 0, mismatches: [] };
    const names = { revenue: 'revenue', oi: 'operating profit', ni: 'net earnings', ocf: 'operating cash flow' };
    const auditHTML = `<h2>Checking the 8-K reader</h2>
        <p>Every quarter first drawn from an earnings release is compared with the company’s 10-Q or 10-K when it arrives (revenue, operating profit, net earnings and operating cash flow, within 0.5%).</p>
        <p><b>${au.checked}</b> release${au.checked === 1 ? '' : 's'} checked so far${au.checked ? `, <b>${au.matched}</b> matched (${(au.matched / au.checked * 100).toFixed(0)}%)` : ''}.</p>
        ${au.mismatches.length ? `<div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Quarter end</th><th>Line</th><th class="num">8-K</th><th class="num">10-Q/10-K</th></tr></thead><tbody>${
          au.mismatches.slice().reverse().flatMap((m) => Object.entries(m.fields).map(([k, [a, b]]) =>
            `<tr><td><a href="#c-${m.cik}">${t(m.ticker)}</a></td><td>${date(m.end)}</td><td>${names[k] || k}</td><td class="num">${money(a)}</td><td class="num">${money(b)}</td></tr>`)).join('')
        }</tbody></table></div>` : ''}`;
    if (!here()) return;
    app.innerHTML = `
      <div class="page-head"><div class="eyebrow">Method</div><h1>How each chart is built</h1></div>
      <div class="cols"><div class="prose">
        <h2>Scanning</h2>
        <p>Every 15 minutes a scheduled job reads EDGAR’s live feed of new 10-Q and 10-K filings (plus the daily index as a fallback). Each new filing is processed once its XBRL data appears in the SEC’s company-facts API, which can lag the filing by a few hours; until then it waits in a retry queue.</p>
        <h2>Earnings releases (8-K)</h2>
        <p>Most companies publish results in an 8-K press release days or weeks before the 10-Q or 10-K. The scan also reads 8-K filings with Item 2.02 (results of operations): the statements printed in the release are read by fixed rules. Before anything is drawn, one of the release’s earlier-period columns must equal the revenue and net earnings the company already filed in XBRL (this pins down the columns, the units and the period), the statement must reconcile, and the quarter must end at least a week before the release. These charts are marked preliminary and are replaced automatically when the 10-Q or 10-K arrives.</p>
        <h2>Numbers</h2>
        <p>All figures are GAAP values reported in XBRL. A quarter is taken directly when a three-month value exists; otherwise it is year-to-date minus the prior year-to-date, which is how fourth quarters (10-K) and all quarterly cash flows are derived. Revenue lines and segments come from the dimensional facts in the filing’s own XBRL instance and are used only when they add up to total revenue.</p>
        <h2>Layout</h2>
        <p>Revenue lines merge into revenue; profit stays on top and costs peel downward; operating profit plus other income becomes pre-tax earnings, which splits into tax, minority interests and net earnings; operating cash flow is bridged directly from net earnings and splits into capital expenditures and free cash flow (when capex exceeds operating cash flow, the gap enters as negative free cash flow). Each label shows the amount, its share of the node it splits from or flows into, and the change year over year and quarter over quarter. Loss-making quarters use a funding view: revenue, other income and the net loss together fund all costs.</p>
        <p>The comparison view keeps the same picture and marks the part of every band that grew since the previous quarter as a dark strip. Each label adds Δ = scale + mix: scale is the change explained by the parent node growing, mix the change in the item’s share of its parent.</p>
        <h2>Full years and any two periods</h2>
        <p>Each 10-K also gets a full-year chart from the year’s reported totals, compared with the year before. Signed-in readers who turn on “Compare any two periods” can pick any two quarters (or two fiscal years) that SEC’s XBRL data covers, back to 2009–2011; the comparison is drawn from SEC data on request by the same rules, the first period against the second.</p>
      </div><div class="prose">
        ${auditHTML}
        <h2>Text</h2>
        <p>No language model is used anywhere. Company descriptions are the opening paragraphs of Item 1 (Business) of the latest 10-K; for a company that has not filed a 10-K yet, the “About” paragraph of its earnings release, or else the description of business in Note 1 of its 10-Q. Node notes are the paragraphs under the matching heading in Management’s Discussion and Analysis of the same filing, quoted verbatim. Analysis paragraphs are sentences filled from the numbers by fixed rules.</p>
        <h2>Starred companies</h2>
        <p>Companies listed in <span class="mono">config/starred.txt</span> keep eight quarters and three fiscal years (others keep seven and two) and are back-filled from their filing history when first added.</p>
        <h2>Sectors</h2>
        <p>Sector and industry charts sum every company whose fiscal quarter ends in the same calendar quarter, grouped by SIC code. Detail lines appear only when every company reports them; comparisons need at least 90% of the revenue to have prior-period data.</p>
        <h2>Limits</h2>
        <p>Banks, insurers and other companies whose statements do not follow the revenue-to-net-income pattern may show coarse charts. Custom XBRL tags outside the standard taxonomy are grouped into “Other operating costs”.</p>
      </div></div>`;
  }

  // ---------- search ----------
  function setupSearch() {
    const input = $('#q'), box = $('#suggest');
    let hi = 0, items = [];
    const close = () => { box.hidden = true; };
    input.addEventListener('input', async () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { close(); return; }
      const ix = await getJSON('index.json');
      const exact = (c) => (c.ticker || '').toLowerCase() === q;
      const match = (c) => (c.ticker || '').toLowerCase().startsWith(q) || c.name.toLowerCase().includes(q);
      const here = ix.companies.filter(match).sort((a, b) => exact(b) - exact(a) || b.revenue - a.revenue);
      const draw = (list) => {
        items = list.slice(0, 8);
        hi = 0;
        const more = window.FFSearch ? window.FFSearch.moreHTML(q) : '';      // web/search.js: 13F managers, officials, ETFs
        box.innerHTML = (items.map((c, i) => `<a href="#c-${c.cik}" class="${i === hi ? 'hi' : ''}${c.off ? ' off' : ''}"><span class="mono">${t(c.ticker)}</span><span>${t(c.name)}</span>${
          c.off ? '<span class="tag">no chart yet</span>' : ''}</a>`).join('') || (more ? '' : '<div class="muted" style="padding:8px 10px">No company found</div>')) + more;
        box.hidden = false;
      };
      draw(here);
      const all = await secCompanies();                 // every SEC company with a ticker, also those not drawn yet
      if (input.value.trim().toLowerCase() !== q || !all.length) return;
      const have = new Set(ix.companies.map((c) => +c.cik));
      const there = [];
      for (const [cik, ticker, name] of all) {          // SEC lists the largest first
        if (have.has(cik)) continue;
        const c = { cik, ticker, name, off: true };
        if (match(c)) there.push(c);
        if (there.length >= 16) break;
      }
      if (!there.length) return;
      draw(here.filter(exact).concat(there.filter(exact), here.filter((c) => !exact(c)), there.filter((c) => !exact(c))));
    });
    input.addEventListener('keydown', (e) => {
      if (box.hidden || !items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        hi = (hi + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
        $$('a', box).forEach((a, i) => a.classList.toggle('hi', i === hi));
      } else if (e.key === 'Enter') {
        location.hash = `c-${items[hi].cik}`;
        input.value = '';
        close();
      } else if (e.key === 'Escape') close();
    });
    box.addEventListener('click', () => { input.value = ''; close(); });
    document.addEventListener('click', (e) => { if (!e.target.closest('.search')) close(); });
  }

  function setupTheme() {
    const saved = prefs.get('theme', null);
    if (saved) document.documentElement.setAttribute('data-theme', saved);
    $('#theme').addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme') ||
        (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      prefs.set('theme', next);
    });
  }

  // ---------- accounts: passwordless sign-in (a code by e-mail) and alert preferences, stored in Supabase ----------
  const SUPABASE_JS = ['cdn.jsdelivr.net/npm', 'fastly.jsdelivr.net/npm', 'unpkg.com']   // tried in turn (some networks block one)
    .map((h) => `https://${h}/@supabase/supabase-js@2.58.0/dist/umd/supabase.js`);
  const PREF_DEFAULTS = { tickers: [], sectors: [], all_above: false, min_revenue: 1e9, starred: false,
    frequency: 'daily', email_on: true, push_on: true, final_too: true };
  const MAIL_DEFAULTS = { chart_q: false, chart_y: false, chart_history: false, attach_images: 'png', attach_pdf: true, cmp_decreases: false,
    changes_detail: false, custom_compare: false, digest_hour: 8, tz: null, daily_scope: 'follows', fcf_basis: 'company', chart_drag_zoom: false,
    lines_unmatched: false };   // columns added after the first release (see savePrefs)
  const acct = { client: undefined, prefs: null, flash: null, owner: undefined, osets: undefined };
  function browserTZ() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch (e) { return null; }
  }
  const hourWords = (h) => `${+h}:00`;

  function loadScript(src, ms) {
    return new Promise((res, rej) => {
      const el = document.createElement('script');
      const fail = () => { clearTimeout(timer); el.remove(); rej(new Error('could not load ' + src)); };
      const timer = setTimeout(fail, ms || 6000);                // a blocked host can hang instead of failing
      el.src = src;
      el.onload = () => { clearTimeout(timer); res(); };
      el.onerror = fail;
      document.head.appendChild(el);
    });
  }
  // every request to the accounts service gives up after 20 seconds: a stalled connection (or a token refresh that never
  // answers) would otherwise leave buttons waiting forever with nothing on screen
  const NET_MS = 20000;
  function timedFetch(input, init) {
    init = init || {};
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), NET_MS);
    if (init.signal) {
      if (init.signal.aborted) ctl.abort();
      else init.signal.addEventListener('abort', () => ctl.abort(), { once: true });
    }
    return fetch(input, Object.assign({}, init, { signal: ctl.signal })).finally(() => clearTimeout(timer));
  }
  async function sb() {
    if (acct.client !== undefined) return acct.client;
    if (window.FF_SUPABASE) return (acct.client = window.FF_SUPABASE);          // injected by tests
    const site = await getJSON('site.json').catch(() => ({}));
    if (!site.supabase_url || !site.supabase_key) return (acct.client = null);
    try {
      for (const src of SUPABASE_JS) {
        if (window.supabase && window.supabase.createClient) break;
        await loadScript(src).catch((e) => console.warn(e.message));
      }
      const lib = window.supabase;
      // processLock: the sign-in lock is this tab's own. The default lock is shared by every tab of the site, and a
      // sleeping background tab that holds it makes the session check of this tab (and every button) wait forever.
      acct.client = lib.createClient(site.supabase_url, site.supabase_key, {
        auth: lib.processLock ? { lock: lib.processLock } : {},
        global: { fetch: timedFetch },
      });
    } catch (e) {
      console.warn('accounts are off on this page:', e.message);
      acct.client = null;
    }
    return acct.client;
  }
  async function currentUser() {
    const c = await sb();
    if (!c) return null;
    const { data } = await c.auth.getSession();
    return data && data.session ? data.session.user : null;
  }
  // for buttons: the signed-in user, or null when signed out; an error (not "signed out") when the service did not answer
  async function buttonUser() {
    const c = await sb();
    if (!c) return null;
    const { data, error } = await c.auth.getSession();
    if (data && data.session) return data.session.user;
    if (error && /fetch|network|abort|timed? ?out|load failed/i.test(`${error.name} ${error.message}`)) throw new Error(NO_ANSWER);
    return null;
  }
  const NO_ANSWER = 'No answer from the accounts service. Check your connection and try again';
  // a button's request with something on screen the whole time: "Sending…" at once, a note when it is slow, and the
  // answer when it comes (even after the button gave up waiting)
  function withProgress(btn, show, work) {
    let done = false;
    const free = () => { btn.disabled = false; btn.removeAttribute('aria-busy'); };
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    show('Sending…');
    const slow = setTimeout(() => { if (!done) show('Still waiting for the accounts service…'); }, 8000);
    const late = setTimeout(() => { if (!done) { show(NO_ANSWER); free(); } }, 45000);
    return Promise.resolve().then(work).catch((e) => (e && e.message === NO_ANSWER ? NO_ANSWER : `Could not send: ${e && e.message}`))
      .then((text) => {
        done = true;
        clearTimeout(slow);
        clearTimeout(late);
        free();
        if (text != null) show(text);
        return text;
      });
  }
  function syncApp() {                     // the Android app checks for new charts in the background with these
    const native = window.FilingFlowsApp;
    if (!native || typeof native.setFollows !== 'function') return;
    const p = acct.prefs;
    try {
      native.setFollows(JSON.stringify(p ? { tickers: p.tickers, sectors: p.sectors, all_above: p.all_above,
        min_revenue: p.min_revenue, starred: p.starred, push_on: p.push_on, final_too: p.final_too !== false } : null));
    } catch (e) { /* older app */ }
  }
  async function loadPrefs() {
    const c = await sb();
    const user = await currentUser();
    if (!c || !user) return null;
    const got = await c.from('subscriptions').select('*').eq('user_id', user.id).maybeSingle();
    if (got.error) throw new Error(got.error.message);
    let row = got.data;
    if (!row) {
      const base = Object.assign({ user_id: user.id, email: user.email }, PREF_DEFAULTS);
      let ins = await c.from('subscriptions').insert(Object.assign({ tz: browserTZ() }, base)).select().single();
      if (ins.error && ins.error.code === 'PGRST204') ins = await c.from('subscriptions').insert(base).select().single();   // older database
      if (ins.error) throw new Error(ins.error.message);
      row = ins.data;
    } else if ('tz' in row && !row.tz && browserTZ()) {          // the daily report's time zone: this browser's
      const up = await c.from('subscriptions').update({ tz: browserTZ() }).eq('user_id', user.id).select().single();
      if (!up.error && up.data) row = up.data;
    }
    acct.prefs = row;
    if (typeof row.cmp_decreases === 'boolean' && row.cmp_decreases !== state.decreases) {   // the account setting wins
      state.decreases = row.cmp_decreases;
      prefs.set('decreases', state.decreases);
      $$('[data-dec]').forEach((cb) => { cb.checked = state.decreases; });
      state.charts.forEach((c) => c.redraw && c.redraw());
    }
    if (typeof row.lines_unmatched === 'boolean' && row.lines_unmatched !== state.linesUnmatched) {   // unmatched lines
      state.linesUnmatched = row.lines_unmatched;
      prefs.set('lines-unmatched', state.linesUnmatched);
      if (/^#c-/.test(location.hash)) setTimeout(route, 0);
    }
    if (typeof row.chart_drag_zoom === 'boolean' && row.chart_drag_zoom !== state.dragZoom) {   // drag and zoom charts
      state.dragZoom = row.chart_drag_zoom;
      prefs.set('drag-zoom', state.dragZoom);
      state.charts.forEach((c) => c.sync && c.sync());
    }
    const fcf = fcfBasis(row.fcf_basis);
    if ('fcf_basis' in row && fcf !== state.fcf) {                       // the account setting wins here too
      state.fcf = fcf;
      prefs.set('fcf', fcf);
      if (/^#c-/.test(location.hash)) setTimeout(route, 0);              // a company page drawn on the other definition
    }
    syncApp();
    return row;
  }
  async function savePrefs(patch) {
    const c = await sb();
    const user = await currentUser();
    const row = Object.assign({}, PREF_DEFAULTS, acct.prefs || {}, patch, { user_id: user.id, email: user.email });
    if (browserTZ()) row.tz = browserTZ();                      // the daily report goes out at its hour in this time zone
    ['unsub_token', 'created_at', 'updated_at'].forEach((k) => delete row[k]);
    let up = await c.from('subscriptions').upsert(row).select().single();
    if (up.error && up.error.code === 'PGRST204' && Object.keys(MAIL_DEFAULTS).some((k) => k in row)) {
      // the database predates the e-mail content options (supabase/schema.sql not run again yet): save the rest
      Object.keys(MAIL_DEFAULTS).forEach((k) => delete row[k]);
      up = await c.from('subscriptions').upsert(row).select().single();
      if (!up.error) acct.flash = 'Saved, except the e-mail content options: the site owner has to update the database first';
    }
    if (up.error) throw new Error(up.error.message);
    acct.prefs = up.data;
    syncApp();
    return up.data;
  }

  // Follow / Following buttons on company and sector pages
  async function initFollowButtons() {
    const btns = $$('[data-follow]');
    if (!btns.length) return;
    const c = await sb();
    if (!c) return;                                   // accounts not switched on: the buttons stay hidden
    const user = await currentUser();
    const p = user ? (acct.prefs || await loadPrefs().catch(() => null)) : null;
    btns.forEach((b) => {
      const [kind, value] = b.dataset.follow.split(':');
      const list = kind === 'ticker' ? 'tickers' : 'sectors';
      const on = () => !!(acct.prefs && (acct.prefs[list] || []).includes(value));
      const paint = () => { b.textContent = on() ? '★ Following' : '☆ Follow'; b.classList.toggle('on', on()); };
      paint();
      b.hidden = false;
      if (b.dataset.wired) return;
      b.dataset.wired = '1';
      b.addEventListener('click', async () => {
        if (!(await currentUser())) {
          prefs.set('pending-follow', b.dataset.follow);
          prefs.set('after-signin', location.hash.replace(/^#/, ''));
          location.hash = 'account';
          return;
        }
        const cur = (acct.prefs && acct.prefs[list]) || [];
        b.disabled = true;
        try {
          await savePrefs({ [list]: on() ? cur.filter((x) => x !== value) : cur.concat([value]) });
          toast(on() ? `Following ${value}: new charts will be sent to you` : `Stopped following ${value}`);
        } catch (err) {
          toast(`Could not save: ${err.message}`);
        } finally {
          b.disabled = false;
          paint();
        }
      });
      if (!p) b.title = 'Sign in with your e-mail to follow';
    });
  }

  // "Email me this report": a queued request; the sender mails it to the signed-in address (any quarter on the site)
  async function requestReports(cik, ends, kind) {
    const c = await sb();
    const user = await currentUser();
    const rows = ends.map((end) => Object.assign({ cik: +cik, period_end: end }, kind === 'fy' ? { kind: 'fy' } : {}));
    let r = await c.from('send_requests').insert(rows);
    let dup = 0;
    if (r.error && r.error.code === '23505' && rows.length > 1) {     // some already on their way: add the rest
      r = { error: null };
      for (const row of rows) {
        const one = await c.from('send_requests').insert([row]);
        if (one.error && one.error.code === '23505') dup++;
        else if (one.error) { r = one; break; }
      }
    }
    if (r.error && r.error.code === '23505') return 'Already on its way to your inbox';
    if (r.error && /limit/i.test(r.error.message)) return 'Limit reached: 30 reports a day';
    if (r.error && kind === 'fy' && tableMissing(r.error)) return OWNER_UPDATE;
    if (r.error) return `Could not send: ${r.error.message}`;
    const n = rows.length - dup;
    if (!n) return 'Already on its way to your inbox';
    return `${n === 1 ? 'Report' : n + ' reports'} on the way to ${user.email}, usually within 10 minutes`;
  }
  // one queued e-mail of any kind (send_requests): a day's report, or the owner's X thread of a quarter
  // Owner tools: posts land in Buffer's drafts (review / edit there) unless "Queue directly" is chosen; remembered
  const draftOn = () => { try { return localStorage.getItem('ff:postDraft') !== '0'; } catch (e) { return true; } };
  const draftToggle = (id) => `<label class="check small" title="Draft: the post and its charts wait in Buffer's Drafts for you to read, edit and schedule. Off: straight into the posting queue."><input type="checkbox" id="${id}" ${draftOn() ? 'checked' : ''}> Save as a Buffer draft (review first)</label>`;
  const bindDraft = (id) => { const el = $('#' + id); if (el) el.addEventListener('change', () => { try { localStorage.setItem('ff:postDraft', el.checked ? '1' : '0'); } catch (e) { /* private mode */ } }); };
  async function askFor(row, what) {
    const c = await sb();
    const user = c ? await currentUser() : null;
    if (!user) return 'Sign in first';
    if (!acct.prefs) await loadPrefs().catch(() => null);      // the sender reads the address from the account's row
    const r = await c.from('send_requests').insert([row]);
    if (r.error && r.error.code === '23505') return `${what} already on its way to your inbox`;
    if (r.error && /limit/i.test(r.error.message)) return 'Limit reached: 30 e-mails a day';
    if (r.error && (tableMissing(r.error) || /check constraint|violates row-level|column/i.test(r.error.message))) return OWNER_UPDATE;
    if (r.error) return `Could not send: ${r.error.message}`;
    if (/post|engage/i.test(row.kind || '')) return row.draft ? `${what}: writing it now — it appears in Buffer → Drafts within a few minutes for you to review` : `${what} queued: it reaches Buffer within a few minutes, then follows your posting schedule`;
    return `${what} on the way to ${user.email}, usually within a few minutes`;
  }

  // ---------- the daily report of one filing date (home page and owner tools): today and the five days before ----------
  function localISO(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }
  function dayEntries(ix, day) {                       // the same filings pipeline/notify.py entries_for_day() picks
    const out = [], seen = new Set();
    ix.companies.forEach((e) => {
      const found = [];
      if (e.filed === day || e.after_release === day) found.push(e);
      (e.also || []).forEach((a) => { if (a.filed === day) found.push(Object.assign({}, e, a, { prelim: a.form === '8-K' })); });
      found.forEach((x) => { const k = `${x.cik}:${x.end}:${x.form}`; if (!seen.has(k)) { seen.add(k); out.push(x); } });
    });
    return out;
  }
  const normTicker = (x) => String(x || '').trim().toUpperCase().replace(/\./g, '-');
  const followsAny = (p) => !!(p && ((p.tickers || []).length || (p.sectors || []).length || p.all_above || p.starred));
  function followed(e, p) {                            // the same rules as pipeline/notify.py reasons()
    return (e.ticker && (p.tickers || []).map(normTicker).includes(normTicker(e.ticker))) || (p.sectors || []).includes(e.sector)
      || (p.all_above && (e.revenue || 0) >= (p.min_revenue || 0)) || (p.starred && e.starred);
  }
  async function dailyPanel(box, ix, opt) {
    opt = opt || {};
    const c = await sb();
    if (!c || !box.isConnected) return;
    const user = await currentUser();
    const p = user ? (acct.prefs || await loadPrefs().catch(() => null)) : null;
    const owner = user ? await ownerVerified() : false;
    const osets = owner ? await ownerSettings() : null;
    const minOwner = osets && osets.min_revenue != null ? +osets.min_revenue : 1e9;
    const full = owner ? !!osets && osets.daily_scope === 'all' : !!p && p.daily_scope === 'all';   // the full report
    const scope = full ? () => true : owner ? (e) => (e.revenue || 0) >= minOwner
      : followsAny(p) ? (e) => followed(e, p) : (e) => (e.revenue || 0) >= 1e9;
    const mineWord = owner ? 'in your report' : followsAny(p) ? 'you follow' : 'over $1B';
    const countWords = (d) => (full && owner ? 'all in your report' : full && !followsAny(p) ? 'all in your report'
      : `${full ? d.fol : d.mine} ${mineWord}`);
    const now = new Date();
    const days = [0, 1, 2, 3, 4, 5].map((i) => {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      const iso = localISO(d), all = dayEntries(ix, iso);
      const name = i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'short' });
      return { iso, i, name, short: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        long: d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }), all: all.length, mine: all.filter(scope).length,
        fol: p && followsAny(p) ? all.filter((e) => followed(e, p)).length : 0 };
    });
    const first = days.find((d) => d.mine) || days.find((d) => d.all) || days[1];
    let pick = first.iso;
    const hour = owner && osets ? osets.daily_hour : p && p.digest_hour != null ? p.digest_hour : 8;
    const auto = owner ? (osets && osets.daily_on === false ? 'Your scheduled owner report is off (Owner tools).'
      : `Your owner report also arrives by itself every morning at ${hourWords(hour)} ${t((osets && osets.tz) || 'Asia/Shanghai')} time.`)
      : p && p.email_on && p.frequency === 'daily' ? `The report of new filings also arrives by itself every morning at ${hourWords(hour)} your time (change it in <a href="#account">Alerts</a>).`
      : `Get it every morning by itself: choose “Daily report” in <a href="#account">${user ? 'your alerts' : 'Alerts'}</a>.`;
    const what = owner ? (full ? 'every company that filed that day (your full report), largest first, with the X threads'
        : `every company with quarterly revenue of $${(minOwner / 1e9).toLocaleString('en-US', { maximumFractionDigits: 2 })}B or more, with its X thread`)
        + (osets && osets.reader_copy ? '; the reader version as set in your <a href="#account">alerts</a> comes too' : '')
      : full ? `every company that filed that day (your full report)${followsAny(p) ? ', the ones you follow first' : ''}`
      : (followsAny(p) ? 'the companies you follow' : 'every company with quarterly revenue of $1B or more (follow companies to narrow it)')
        + (user ? '; for every company that filed, choose the full report in <a href="#account">your alerts</a>' : '');
    box.innerHTML = `<div class="section-head"><h2>${opt.title || 'Daily report'}</h2>
        <span class="muted">One e-mail for a day’s filings: what each company does, its chart and the analysis</span></div>
      <div class="days" role="radiogroup" aria-label="Filing date">${days.map((d) => `<button type="button" class="day${d.iso === pick ? ' on' : ''}"
          role="radio" aria-checked="${d.iso === pick}" data-day="${d.iso}" ${d.all ? '' : 'disabled'}>
          <b>${d.name}</b><span>${d.short}</span><span class="n">${d.all ? `${d.all} filing${d.all === 1 ? '' : 's'}${user ? ` · ${countWords(d)}` : ''}` : 'no filings'}</span></button>`).join('')}</div>
      <div class="row"><button class="btn primary" type="button" id="day-send"></button>${owner ? '<button class="btn" type="button" id="day-article" title="This day’s report as an X Article: copy the text, then each chart, and paste them into X’s editor">✦ X Article</button><a class="btn" href="#owner-xreport" title="Choose the companies and what goes in: Sankey, Polymarket · Kalshi · options, flows, capital allocation, debt, rotation">✦ Custom X report…</a>' : ''}<span class="muted small" id="day-msg" role="status"></span></div>
      <p class="muted small">Covers ${what}. Dates are filing dates on SEC EDGAR. ${auto}</p>`;
    const label = () => { const d = days.find((x) => x.iso === pick); $('#day-send', box).textContent = `✉ Email me the report for ${d.i < 2 ? d.name.toLowerCase() : d.long}`; };
    label();
    $$('[data-day]', box).forEach((b) => b.addEventListener('click', () => {
      pick = b.dataset.day;
      $$('[data-day]', box).forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); });
      label();
    }));
    const artBtn = $('#day-article', box);
    const msgBox = () => $('#day-msg', box);
    if (artBtn) artBtn.addEventListener('click', async () => {
      if (artBtn.disabled) return;
      artBtn.disabled = true;
      const say = (x) => { if (msgBox()) msgBox().textContent = x; };
      say(await (async () => {
      const day = pick, entries = dayEntries(ix, day).filter(scope).sort((x, y) => (y.revenue || 0) - (x.revenue || 0));
      if (!entries.length) return 'No filing in your report on that day';
      say(`Reading ${Math.min(60, entries.length)} compan${entries.length === 1 ? 'y' : 'ies'}…`);
      const items = (await Promise.all(entries.slice(0, 60).map(async (e) => {
        try {
          const c = await getJSON(`c/${e.cik}.json`), qs = c.quarters.map(fcfView);
          const q = qs.find((x) => x.end === e.end && x.form === e.form) || qs.find((x) => x.end === e.end);
          return q ? { e, c, q } : null;
        } catch (err) { return null; }
      }))).filter(Boolean);
      if (!items.length) return 'The companies of that day could not be read';
      articlePanel(articleDay(day, items, osets && osets.article_full ? +osets.article_full : 6), `daily report ${day}`);
      return '';
      })().catch((e) => `Could not build the article: ${e && e.message}`));
      artBtn.disabled = false;
    });
    $('#day-send', box).addEventListener('click', (ev) => {
      const btn = ev.currentTarget, day = pick, msg = $('#day-msg', box);
      if (btn.disabled) return;
      withProgress(btn, (text) => { msg.textContent = text; }, async () => {
        if (!(await buttonUser())) {
          prefs.set('pending-day', day);
          prefs.set('after-signin', location.hash.replace(/^#/, '') || 'home');
          location.hash = 'account';
          return '';
        }
        return askFor({ cik: 0, period_end: day, kind: 'day' }, 'Report');
      });
    });
    box.hidden = false;
  }

  async function initSendButtons() {
    const btns = $$('[data-send]');
    if (!btns.length) return;
    if (!(await sb())) return;
    btns.forEach((b) => {
      b.hidden = false;
      if (b.dataset.wired) return;
      b.dataset.wired = '1';
      b.addEventListener('click', () => {
        if (b.disabled) return;
        withProgress(b, (text) => { if (text) toast(text); }, async () => {
          if (!(await buttonUser())) {
            prefs.set('pending-send', b.dataset.send);
            prefs.set('after-signin', location.hash.replace(/^#/, ''));
            location.hash = 'account';
            return '';
          }
          const [cik, ends, kind] = b.dataset.send.split('|');
          return requestReports(cik, ends.split(','), kind);
        });
      });
    });
  }

  async function accountPage() {
    const here = live();
    setNav('account');
    const c = await sb();
    if (!here()) return;
    if (!c) {
      app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>E-mail alerts are not switched on yet</h1>
        <p class="muted" style="max-width:70ch">The site owner still has to connect the accounts service (see “Accounts and alerts” in the README).</p></div>`;
      return;
    }
    if (!(await currentUser())) return here() ? signInView(c) : null;
    const p = await loadPrefs();
    if (!here()) return;
    const pending = prefs.get('pending-follow', null), pendingSend = prefs.get('pending-send', null);
    const pendingBuild = prefs.get('pending-build', null), pendingOwner = prefs.get('pending-owner', false);
    const pendingDay = prefs.get('pending-day', null);
    if (pendingDay) {                                 // "Email me the report for …" from before signing in
      prefs.set('pending-day', null);
      acct.flash = await askFor({ cik: 0, period_end: pendingDay, kind: 'day' }, 'Report');
    }
    if (pending) {                                    // a Follow click from before signing in
      prefs.set('pending-follow', null);
      const [kind, value] = pending.split(':');
      const list = kind === 'ticker' ? 'tickers' : 'sectors';
      if (!(p[list] || []).includes(value)) await savePrefs({ [list]: (p[list] || []).concat([value]) });
      acct.flash = `Following ${value}`;
    }
    if (pendingSend) {                                // an "Email me" click from before signing in
      prefs.set('pending-send', null);
      const [cik, ends, kind] = pendingSend.split('|');
      acct.flash = await requestReports(cik, ends.split(','), kind);
    }
    if (pendingBuild) {                               // "Build its charts" from before signing in
      prefs.set('pending-build', null);
      acct.flash = (await askForCompany(pendingBuild)).msg;
    }
    if (pendingOwner) prefs.set('pending-owner', false);       // signing in from the owner tools page
    if (pending || pendingSend || pendingBuild || pendingOwner || pendingDay) {
      const back = prefs.get('after-signin', null);
      prefs.set('after-signin', null);
      if (back && back !== 'account') { location.hash = back; return; }
    }
    const user = await currentUser();
    if (here()) settingsView(c, user, acct.prefs);
  }

  function signInView(c) {
    const email0 = prefs.get('signin-email', '') || '';
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Sign in with your e-mail</h1>
        <p class="muted" style="max-width:68ch">No password. We send a sign-in code to your inbox; enter it here. New addresses get an account automatically.</p></div>
      <form class="auth" id="auth-email"><label>E-mail address<input type="email" required autocomplete="email" value="${t(email0)}"></label>
        <button class="btn primary" type="submit">Send code</button></form>
      <form class="auth" id="auth-code" hidden><label>Code from the e-mail<input inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,10}" required></label>
        <button class="btn primary" type="submit">Sign in</button> <button class="btn" type="button" id="auth-back">Use another address</button></form>
      <p class="auth-msg muted" id="auth-msg" role="status"></p>
      <p class="muted small">By signing up you agree to the <a href="terms.html">terms</a>; the <a href="privacy.html">privacy policy</a> lists exactly what is stored.</p>`;
    const msg = (x) => { $('#auth-msg').textContent = x; };
    let email = '';
    $('#auth-email').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      email = $('#auth-email input').value.trim();
      const btn = $('#auth-email button');
      btn.disabled = true;
      msg('Sending…');
      // emailRedirectTo: where a link in the e-mail lands if a template still sends one (without it Supabase uses the
      // browser's Referer, which is only the domain: https://you.github.io/ instead of the site)
      const r = await c.auth.signInWithOtp({ email, options: { shouldCreateUser: true, emailRedirectTo: location.origin + location.pathname } });
      btn.disabled = false;
      if (r.error) { msg(`Could not send the code: ${r.error.message}`); return; }
      prefs.set('signin-email', email);
      $('#auth-email').hidden = true;
      $('#auth-code').hidden = false;
      $('#auth-code input').focus();
      msg(`Code sent to ${email}. It can take a minute; check the spam folder too.`);
    });
    $('#auth-back').addEventListener('click', () => { $('#auth-code').hidden = true; $('#auth-email').hidden = false; msg(''); });
    $('#auth-code').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const token = $('#auth-code input').value.trim();
      msg('Checking…');
      const r = await c.auth.verifyOtp({ email, token, type: 'email' });
      if (r.error) { msg(`That code did not work: ${r.error.message}`); return; }
      prefs.set('signin-email', null);
      await accountPage();
    });
  }

  const SCOPE_NOTE = ' (picking one switches you to the daily report)';
  function settingsView(c, user, p) {
    const here = live();
    const ownerSets = ownerVerified().then((ok) => (ok ? ownerSettings(true).then((o) => o || {}) : null)).catch(() => null);
    Promise.all([getJSON('index.json'), getJSON('site.json').catch(() => ({})), ownerSets]).then(([ix, site, osets]) => {
      const inApp = !!window.FilingFlowsApp;
      const appLink = !inApp && site.repo ? ` · <a href="https://github.com/${t(site.repo)}/releases/tag/android" target="_blank" rel="noopener">get the app</a>` : '';
      const names = ix.sector_names || {};
      const tickers = ix.companies.map((x) => x.ticker).filter(Boolean).sort();
      const m = Object.assign({}, MAIL_DEFAULTS, p);
      if (!here()) return;
      app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Your alerts</h1>
          <div class="meta"><span>Signed in as <b>${t(user.email)}</b></span><button class="btn small" type="button" id="sign-out">Sign out</button></div></div>
        <form class="prefs" id="prefs-form">
          ${osets ? `<fieldset><legend>Site owner</legend>
            <p class="muted small">Your owner report with the X threads comes either way (<a href="#owner">Owner tools</a>). The settings on
              this page are the reader version.</p>
            ${'reader_copy' in osets ? `<label class="long"><input type="checkbox" id="reader-copy" ${osets.reader_copy ? 'checked' : ''}><span>Also send me
              the reader version: the e-mails these alert settings ask for, the same as any reader gets them</span></label>`
              : `<p class="muted small">${OWNER_UPDATE} to choose the reader version as well.</p>`}</fieldset>` : ''}
          <fieldset><legend>Companies</legend>
            <div class="chips" id="chips"></div>
            <div class="row"><input id="add-ticker" list="ticker-list" placeholder="Ticker, e.g. AAPL" autocomplete="off" aria-label="Add a company">
              <datalist id="ticker-list">${tickers.map((x) => `<option value="${t(x)}">`).join('')}</datalist>
              <button class="btn" type="button" id="add-btn">Add</button></div>
            <p class="muted small">Or use ☆ Follow on any company page.</p></fieldset>
          <fieldset><legend>Sectors</legend><p class="muted small">Every company in the sectors you tick.</p><div class="grid-checks">${Object.entries(names).map(([k, v]) =>
            `<label><input type="checkbox" name="sector" value="${k}" ${(p.sectors || []).includes(k) ? 'checked' : ''}> ${t(v)}</label>`).join('')}</div></fieldset>
          <fieldset><legend>Also</legend>
            <label><input type="checkbox" id="all-above" ${p.all_above ? 'checked' : ''}> Every company with quarterly revenue of at least
              $<input type="number" id="min-rev" min="0" step="0.1" value="${(p.min_revenue / 1e9).toFixed(1).replace(/\.0$/, '')}" style="width:5em"> billion</label>
            <label><input type="checkbox" id="starred" ${p.starred ? 'checked' : ''}> The site’s starred companies</label></fieldset>
          <fieldset><legend>When</legend>
            <label class="long"><input type="radio" name="freq" value="daily" ${p.frequency === 'daily' ? 'checked' : ''}><span>Daily report every morning at
              <select id="digest-hour" aria-label="Hour of the daily report">${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${+m.digest_hour === h ? 'selected' : ''}>${hourWords(h)}</option>`).join('')}</select>
              your time${browserTZ() ? ` (${t(browserTZ())})` : ''}: every new chart since the last report, with what each company does and the analysis, in one e-mail</span></label>
            <div class="sub-choice${p.frequency === 'daily' ? '' : ' off'}" id="scope-box" role="radiogroup" aria-label="What the daily report covers">
              <span class="muted small">The daily report covers<span id="scope-note">${p.frequency === 'daily' ? '' : SCOPE_NOTE}</span></span>
              <label class="long"><input type="radio" name="scope" value="follows" ${m.daily_scope !== 'all' ? 'checked' : ''}><span>The companies I follow (above)</span></label>
              <label class="long"><input type="radio" name="scope" value="all" ${m.daily_scope === 'all' ? 'checked' : ''}><span>Every company that filed: the full
                report, with the ones I follow first. The first 15 come in full (chart, what the company does, analysis); the rest are listed with links</span></label></div>
            <label><input type="radio" name="freq" value="instant" ${p.frequency !== 'daily' ? 'checked' : ''}> As soon as a chart is out (checked every 15 minutes)</label>
            <label class="long"><input type="checkbox" id="final-too" ${p.final_too !== false ? 'checked' : ''}><span>After a preliminary chart from an earnings release (8-K), also send the final one when the 10-Q/10-K is filed, marked as final and compared with the release</span></label></fieldset>
          <fieldset><legend>How</legend>
            <label><input type="checkbox" id="email-on" ${p.email_on ? 'checked' : ''}> E-mail to ${t(user.email)}: the chart, the analysis and what changed</label>
            <label><input type="checkbox" id="push-on" ${p.push_on ? 'checked' : ''}> Notifications in the Android app${appLink}</label></fieldset>
          <fieldset><legend>In each e-mail</legend>
            <p class="muted small">Every e-mail shows this quarter’s chart (tap it for the interactive one), the analysis and what changed. Also show:</p>
            <label><input type="checkbox" id="chart-q" ${m.chart_q ? 'checked' : ''}> The chart compared with the previous quarter</label>
            <label><input type="checkbox" id="chart-y" ${m.chart_y ? 'checked' : ''}> The chart compared with the same quarter a year earlier</label>
            <label class="long"><input type="checkbox" id="chart-history" ${m.chart_history ? 'checked' : ''}><span>History: revenue, operating profit, net earnings and operating cash flow for every quarter on file</span></label>
            <label class="long"><input type="checkbox" id="changes-detail" ${m.changes_detail ? 'checked' : ''}><span>Detail: every line of the chart with its change against a year earlier and the previous quarter (by default the e-mail lists the three main changes)</span></label>
            <label class="long"><input type="checkbox" id="cmp-decreases" ${m.cmp_decreases ? 'checked' : ''}><span>In comparison charts, also draw decreases as hatched areas with a dashed outline (the same as “Show decreases” on company pages)</span></label>
            <p class="muted small">Attached files</p>
            <div class="inline-radios" role="radiogroup" aria-label="Chart image files"><span>Chart images</span>${[['png', 'PNG'], ['jpg', 'JPG'], ['none', 'None']].map(([v, l]) =>
              `<label><input type="radio" name="attach" value="${v}" ${m.attach_images === v ? 'checked' : ''}> ${l}</label>`).join('')}</div>
            <label class="long"><input type="checkbox" id="attach-pdf" ${m.attach_pdf ? 'checked' : ''}><span>PDF report: company profile, the charts and the analysis</span></label></fieldset>
          <fieldset><legend>Company-reported or calculated figures</legend>
            <p class="muted small">Sometimes the company’s own figure and the arithmetic disagree. Free cash flow: Meta also subtracts
              finance-lease payments, Micron nets asset sales. Revenue: Vistra’s revenue lines add up to $4.40B of contract revenue,
              but hedging losses make total revenues $4.02B. On company pages and in your e-mails, show:</p>
              <label class="long"><input type="radio" name="fcf" value="noted" ${m.fcf_basis === 'noted' ? 'checked' : ''}><span><b>Company-reported.</b>
                The company’s own figures: its free cash flow when its earnings release reports one that matches SEC’s data, its total
                revenue with a line for the difference. Where it reports none, the chart says the figure is calculated and why</span></label>
              <label class="long"><input type="radio" name="fcf" value="company" ${fcfBasis(m.fcf_basis) === 'company' ? 'checked' : ''}><span><b>Company-reported
                first, then calculated</b> (default). The same, and where the company reports no figure the calculation stands in
                without a note</span></label>
              <label class="long"><input type="radio" name="fcf" value="ocf" ${m.fcf_basis === 'ocf' ? 'checked' : ''}><span><b>Calculated throughout.</b>
                One rule for every company: free cash flow = operating cash flow − capital expenditures, revenue = what the revenue
                lines add up to. The company’s own figures are named on the chart</span></label>
              <label class="long"><input type="checkbox" id="lines-unmatched" ${m.lines_unmatched ? 'checked' : ''}><span>When a filing’s revenue
                lines add up to neither total revenue nor contract revenue, show them anyway, with the difference as its own line.
                Off: the chart shows total revenue without them, and says why</span></label></fieldset>
          <fieldset><legend>On company pages</legend>
            <label class="long"><input type="checkbox" id="drag-zoom" ${m.chart_drag_zoom ? 'checked' : ''}><span>Drag and zoom charts with the mouse:
              hold the left button on an empty part of a chart to move it (the pointer turns into a hand), use the wheel to zoom in
              and out, double-click to see it whole again</span></label>
            <label class="long"><input type="checkbox" id="custom-compare" ${m.custom_compare ? 'checked' : ''}><span>Compare any two periods: company pages get a ⇄ Compare any two button. Tick any two quarters (or two fiscal years) back to 2009–2011, when SEC’s XBRL data starts, and the comparison Sankey is drawn from SEC data within a few minutes</span></label></fieldset>
          <div class="row"><button class="btn primary" type="submit">Save</button><span class="muted" id="save-msg" role="status"></span></div>
        </form>
        <section class="section" id="requests"></section>
        <p class="muted small" style="margin-top:28px">To stop everything, untick e-mail and notifications and save, or use the unsubscribe link in any alert e-mail.</p>
        <div class="row danger"><button class="btn small" type="button" id="del-acct">Delete my account</button>
          <span id="del-confirm" hidden><span class="small">This removes your address and settings for good.</span>
          <button class="btn small warn" type="button" id="del-yes">Delete</button> <button class="btn small" type="button" id="del-no">Keep it</button></span>
          <span class="muted small" id="del-msg" role="status"></span></div>`;
      showRequests(c, ix);
      // what the daily report covers: always on show; picking it (with alerts "as soon as a chart is out") switches to the daily report
      const syncScope = () => {
        const daily = $('input[name="freq"]:checked').value === 'daily';
        $('#scope-box').classList.toggle('off', !daily);
        $('#scope-note').textContent = daily ? '' : SCOPE_NOTE;
      };
      $$('input[name="freq"]').forEach((r) => r.addEventListener('change', syncScope));
      $$('input[name="scope"]').forEach((r) => r.addEventListener('click', () => {
        $('input[name="freq"][value="daily"]').checked = true;
        syncScope();
      }));
      let list = (p.tickers || []).slice();
      const chips = () => {
        $('#chips').innerHTML = list.length ? list.map((x) => `<span class="chip"><a href="#home" data-tk="${t(x)}">${t(x)}</a>
          <button type="button" aria-label="Remove ${t(x)}" data-rm="${t(x)}">×</button></span>`).join('') : '<span class="muted small">None yet</span>';
        $$('#chips [data-rm]').forEach((b) => b.addEventListener('click', () => { list = list.filter((x) => x !== b.dataset.rm); chips(); }));
        $$('#chips [data-tk]').forEach((a) => {
          const co = ix.companies.find((x) => x.ticker === a.dataset.tk);
          if (co) a.href = `#c-${co.cik}`;
        });
      };
      chips();
      const add = () => {
        const v = $('#add-ticker').value.trim().toUpperCase();
        if (v && !list.includes(v)) list.push(v);
        $('#add-ticker').value = '';
        chips();
      };
      $('#add-btn').addEventListener('click', add);
      $('#add-ticker').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
      $('#sign-out').addEventListener('click', async () => { await c.auth.signOut(); acct.prefs = null; acct.owner = undefined; acct.osets = undefined; syncApp(); location.hash = 'home'; });
      $('#del-acct').addEventListener('click', () => { $('#del-confirm').hidden = false; $('#del-acct').hidden = true; });
      $('#del-no').addEventListener('click', () => { $('#del-confirm').hidden = true; $('#del-acct').hidden = false; });
      $('#del-yes').addEventListener('click', async () => {
        const r = await c.rpc('delete_account');
        if (r.error || r.data !== true) { $('#del-msg').textContent = `Could not delete: ${(r.error && r.error.message) || 'try again'}`; return; }
        await c.auth.signOut();
        acct.prefs = null;
        syncApp();
        app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>Your account is deleted</h1>
          <p class="muted">Your address and settings are gone. You can sign up again at any time.</p><p><a href="#home">Back to the latest filings</a></p></div>`;
      });
      $('#prefs-form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        $('#save-msg').textContent = 'Saving…';
        try {
          await savePrefs({
            tickers: list, sectors: $$('input[name="sector"]:checked').map((x) => x.value),
            all_above: $('#all-above').checked, min_revenue: Math.round(Math.max(0, +$('#min-rev').value || 0) * 1e9),
            starred: $('#starred').checked, frequency: $('input[name="freq"]:checked').value, final_too: $('#final-too').checked,
            email_on: $('#email-on').checked, push_on: $('#push-on').checked,
            chart_q: $('#chart-q').checked, chart_y: $('#chart-y').checked, chart_history: $('#chart-history').checked,
            attach_images: ($('input[name="attach"]:checked') || {}).value || 'png', attach_pdf: $('#attach-pdf').checked,
            cmp_decreases: $('#cmp-decreases').checked, changes_detail: $('#changes-detail').checked,
            custom_compare: $('#custom-compare').checked, digest_hour: +$('#digest-hour').value,
            daily_scope: (($('input[name="scope"]:checked') || {}).value === 'all') ? 'all' : 'follows',
            fcf_basis: fcfBasis(($('input[name="fcf"]:checked') || {}).value), chart_drag_zoom: $('#drag-zoom').checked,
            lines_unmatched: $('#lines-unmatched').checked,
          });
          state.decreases = $('#cmp-decreases').checked;           // company pages follow the account setting
          prefs.set('decreases', state.decreases);
          state.fcf = fcfBasis(($('input[name="fcf"]:checked') || {}).value);
          state.dragZoom = $('#drag-zoom').checked;
          state.linesUnmatched = $('#lines-unmatched').checked;
          prefs.set('lines-unmatched', state.linesUnmatched);
          prefs.set('drag-zoom', state.dragZoom);
          prefs.set('fcf', state.fcf);
          let note = '';
          if ($('#reader-copy')) {                                   // the site owner: also the reader version?
            const r = await c.from('owner_settings').update({ reader_copy: $('#reader-copy').checked, updated_at: new Date().toISOString() })
              .eq('id', true).select().single();
            if (r.error) note = tableMissing(r.error) ? ` The reader-version switch was not saved: ${OWNER_UPDATE}.` : ` The reader-version switch was not saved: ${r.error.message}.`;
            else acct.osets = r.data;
          }
          $('#save-msg').textContent = (acct.flash || 'Saved.') + note;
          acct.flash = null;
        } catch (err) {
          $('#save-msg').textContent = `Could not save: ${err.message}`;
        }
      });
    });
  }

  async function showRequests(c, ix) {
    const box = $('#requests');
    const r = await c.from('send_requests').select('*')            // '*': with or without the newer kind column
      .order('created_at', { ascending: false }).limit(10);
    if (!box || !box.isConnected) return;
    const byCik = new Map(ix.companies.map((x) => [String(x.cik), x]));
    const state = (x) => (x.status === 'sent' ? `sent ${date(x.sent_at)}` : x.status === 'failed' ? `not sent: ${t(x.error || 'error')}` : 'on its way');
    const rows = (r.data || []).map((x) => {
      const co = byCik.get(String(x.cik));
      const fy = x.kind === 'fy';
      if (x.kind === 'day') return `<tr><td>Daily report</td><td>filings dated ${date(x.period_end)}</td><td class="muted">${state(x)}</td></tr>`;
      if (/^engage_/.test(x.kind || '')) return `<tr><td>X post (Buffer)</td><td>${t(x.kind.slice(7).replace(/_/g, ' '))} · asked ${date(x.created_at)}</td><td class="muted">${state(x)}</td></tr>`;
      return `<tr><td>${co ? `<a href="#c-${x.cik}-${fy ? 'fy-' : ''}${x.period_end}">${t(co.ticker || co.name)}</a>` : x.cik}</td>
        <td>${x.kind === 'thread' ? 'X thread · ' : x.kind === 'post' ? 'X post (Buffer) · ' : x.kind === 'post_holders' ? 'X post, holders (Buffer) · ' : x.kind === 'post_gif' ? 'X post, 8-quarter GIF (Buffer) · ' : ''}${fy ? 'fiscal year' : 'quarter'} ended ${date(x.period_end)}</td><td class="muted">${state(x)}</td></tr>`;
    }).join('');
    box.innerHTML = `<div class="section-head"><h2>Reports you asked for</h2><span class="muted">✉ Email me on any company page sends that quarter or fiscal year, old ones included</span></div>
      ${rows ? `<div class="tbl-wrap"><table><tbody>${rows}</tbody></table></div>` : '<p class="muted small">None yet.</p>'}`;
  }

  async function unsubscribePage(token) {
    const here = live();
    setNav('account');
    const c = await sb();
    let ok = false;
    if (c) {
      const r = await c.rpc('unsubscribe', { token });
      ok = !r.error && r.data === true;
    }
    if (!here()) return;
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Alerts</div><h1>${ok ? 'You are unsubscribed' : 'This link did not work'}</h1>
      <p class="muted" style="max-width:68ch">${ok ? 'No more alert e-mails will be sent. To turn them back on, sign in and tick “E-mail” in your alerts.'
        : 'The link may be old or already used. Sign in to change your alerts.'}</p><p><a href="#account">Manage alerts</a></p></div>`;
  }

  // ---------- owner tools: the X thread panel on company pages, for the site owner only ----------
  // With accounts switched on, only an account listed in Supabase's site_owners table (signed in) can use them; the
  // database answers "am I the owner?" without revealing the list. Without accounts, the switch is per browser only.
  async function ownerVerified() {
    const c = await sb();
    if (!c) return true;                                     // no accounts on this site: the browser switch decides
    if (!(await currentUser())) return false;
    if (acct.owner === undefined) {
      const r = await c.rpc('am_i_owner');
      acct.owner = !r.error && r.data === true;
    }
    return acct.owner;
  }
  async function ownerPage() {
    const here = live();
    setNav('');
    const c = await sb();
    const user = c ? await currentUser() : null;
    const head = '<div class="eyebrow">Site owner</div><h1>Owner tools</h1>';
    const back = '<p><a href="#home">Back to the latest filings</a></p>';
    if (!here()) return;
    if (c && !user) {
      app.innerHTML = `<div class="page-head">${head}
        <p class="muted" style="max-width:68ch">Sign in with the site owner’s e-mail address to use the owner tools.</p>
        <p><a class="btn primary" href="#account" id="owner-signin">Sign in</a></p>${back}</div>`;
      $('#owner-signin').addEventListener('click', () => { prefs.set('pending-owner', true); prefs.set('after-signin', 'owner'); });
      return;
    }
    if (c && !(await ownerVerified())) {
      if (!here()) return;
      prefs.set('owner', false);
      app.innerHTML = `<div class="page-head">${head}
        <p class="muted" style="max-width:68ch">Signed in as <b>${t(user.email)}</b>, which is not a site owner’s address.
          The owner adds their address once in Supabase (SQL Editor:
          <span class="mono">insert into public.site_owners (email) values ('…');</span>).</p>${back}</div>`;
      return;
    }
    const on = prefs.get('owner', false);
    const osets = c ? await ownerSettings(true) : null;
    const o = Object.assign({ thread_direct: true, daily_on: true, daily_hour: 8, tz: browserTZ() || 'Asia/Shanghai',
      min_revenue: 1e9, instant_threads: false, daily_scope: 'min_revenue', reader_copy: false }, osets || {});
    const newCols = !!osets && 'daily_scope' in osets;              // supabase/schema.sql run again since these arrived
    const hasX = !!osets && 'x_post' in osets;                      // the X post options' column (schema.sql run again)
    const xsite = c ? ((await getJSON('site.json').catch(() => ({}))).x || {}) : {};
    const xo = xOptions(xsite, hasX ? osets.x_post : null);
    const settingsHTML = !c ? `<p class="muted" style="max-width:68ch">Accounts are not switched on, so these settings come from
        <span class="mono">config/x.json</span> (keys daily_on, daily_hour, tz, min_revenue, instant_threads).</p>`
      : !osets ? `<p class="muted" style="max-width:68ch">${OWNER_UPDATE}: the owner settings table is new.</p>`
      : `<form class="prefs" id="owner-form">
        <fieldset><legend>“Email me this thread”</legend>
          <label class="long"><input type="radio" name="thread-mail" value="direct" ${o.thread_direct ? 'checked' : ''}><span>Send it straight to my inbox
            (${t(user.email)}), with both chart PNGs attached, usually within two minutes</span></label>
          <label class="long"><input type="radio" name="thread-mail" value="github" ${o.thread_direct ? '' : 'checked'}><span>Open a GitHub issue with the
            request filled in (the older way: press Create on GitHub)</span></label></fieldset>
        <fieldset><legend>Daily report</legend>
          <label class="long"><input type="checkbox" id="daily-on" ${o.daily_on ? 'checked' : ''}><span>Every morning at
            <select id="daily-hour" aria-label="Hour of the daily report">${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${+o.daily_hour === h ? 'selected' : ''}>${hourWords(h)}</option>`).join('')}</select>
            ${t(browserTZ() || o.tz)} time: every filing since the last report — what the company does, the charts, the analysis and the
            ready-to-post X thread — in one e-mail to ${t(user.email)}</span></label>
          <div class="sub-choice" role="radiogroup" aria-label="Which companies"><span class="muted small">Which companies</span>
            <label><input type="radio" name="owner-scope" value="min_revenue" ${o.daily_scope !== 'all' ? 'checked' : ''}> Companies with
              quarterly revenue of at least $<input type="number" id="daily-min" min="0" step="0.1"
              value="${(+o.min_revenue / 1e9).toFixed(2).replace(/\.?0+$/, '')}" style="width:5em"> billion</label>
            <label class="long"><input type="radio" name="owner-scope" value="all" ${o.daily_scope === 'all' ? 'checked' : ''} ${newCols ? '' : 'disabled'}><span>Every
              company that filed: the full report, largest first. The largest 20 come in full with the charts and X threads; the rest
              are listed with links${newCols ? '' : ` (${t(OWNER_UPDATE)})`}</span></label></div>
          <label class="long"><input type="checkbox" id="instant-threads" ${o.instant_threads ? 'checked' : ''}><span>Also e-mail the new X threads
            right after each scan (as before the daily report)</span></label>
          <p class="muted small" id="reader-copy-state">Reader version: ${o.reader_copy ? 'on. You also get the reader e-mails your'
            : 'off. You get only this report, not the reader e-mails your'} <a href="#account">alert settings</a> describe; change it there.</p>
        </fieldset>
        ${xFieldset(xo, xsite, hasX)}
        <div class="row"><button class="btn primary" type="submit">Save</button><span class="muted" id="owner-msg" role="status"></span></div>
      </form>`;
    if (!here()) return;
    app.innerHTML = `<div class="page-head">${head}
      <p class="muted" style="max-width:68ch">Readers never see these. ${c ? `Verified: signed in as <b>${t(user.email)}</b>.`
          : 'Accounts are not switched on for this site, so the switch below only stays in this browser.'}</p></div>
      <section class="section"><div class="section-head"><h2>X thread on company pages</h2></div>
        <p class="muted" style="max-width:68ch">Shows the ready-to-post thread under each quarter in this browser: the filing, what each image shows
          (with Save PNG), every post with Copy, and “Email me this thread”.</p>
        <p><button class="btn${on ? '' : ' primary'}" type="button" id="owner-toggle">${on ? 'Turn off in this browser' : 'Turn on in this browser'}</button></p>
        <p class="muted" id="owner-state">${on ? 'On: company pages show the X thread.' : 'Off: company pages look the same as for readers.'}</p></section>
      <section class="section"><div class="section-head"><h2>Settings</h2></div>${settingsHTML}</section>
      ${c ? `<section class="section" id="reread"><div class="section-head"><h2>Re-read stored figures</h2>
          <span class="muted">After a fix to how figures are read; otherwise the scan re-reads ${'a few dozen'} companies per run</span></div>
        <p class="muted" style="max-width:72ch">A short scan starts within a minute (owner fast lane; a regular scan that is running wraps up first) and reads these companies’ stored quarters and years again
          from SEC: D&amp;A, share-based compensation, revenue and its lines, and the latest quarter’s company-reported free cash flow.
          Then their charts and e-mails use the new figures.</p>
        <form class="row" id="reread-form"><input id="reread-list" placeholder="Tickers or CIKs, e.g. VST, ORCL, 1692819" style="min-width:min(28em,100%)"
            aria-label="Companies to re-read" autocomplete="off">
          <button class="btn primary" type="submit">Re-read now</button>
          <button class="btn" type="button" id="reread-all" title="Every stored company, a few dozen per scan">Re-read every company</button></form>
        <p class="muted small" id="reread-msg" role="status"></p>
        <div id="reread-list-box"></div></section>` : ''}
      ${c ? `<section class="section" id="engage"><div class="section-head"><h2>Engagement posts to X</h2>
          <span class="muted">Written by the model from the real charts, queued in Buffer. They also run on their own schedule
          (before the open: today’s filers + Reddit; after the close: question of the day; market hours: the biggest movers); these buttons write one now.</span></div>
        <div class="row">${draftToggle('engage-draft')}</div>
        <div class="row" id="engage-bar">
          <button class="btn" type="button" data-engage="engage_question" title="The most striking filing of the last day: one fact, 2–3 options to reply with">✦ Question of the day</button>
          <button class="btn" type="button" data-engage="engage_list" title="Every company that filed in the last day, as cashtags, with up to four charts">✦ Today’s filers</button>
          <button class="btn" type="button" data-engage="engage_reddit_question" title="The company trending hardest on investing subreddits">✦ Reddit question</button>
          <button class="btn" type="button" data-engage="engage_reddit_list" title="The three to five companies trending on Reddit">✦ Reddit list</button>
          <button class="btn" type="button" data-engage="engage_mover" title="The site company moving most right now (delayed quote): the move, its latest filing, “what’s happening?”">✦ Biggest mover now</button>
          <button class="btn" type="button" data-engage="engage_explain" title="The same move as a “someone explain $X” post">✦ Plz explain</button>
          <button class="btn" type="button" data-engage="engage_peers" title="The mover against its closest peers: price, today’s move, growth, margin, price/sales">✦ Mover vs peers</button>
          <button class="btn" type="button" data-engage="engage_insider" title="The largest recent open-market purchase by an officer or director (Form 4)">✦ Insider buy</button>
          <button class="btn" type="button" data-engage="engage_event8k" title="The most important 8-K filed in the last day by a company on the site: a deal, a CEO change, a bankruptcy, a buyback … BREAKING when material">✦ 8-K event</button>
          <button class="btn" type="button" data-engage="engage_ivmove" title="The biggest one-day jump in 30-day implied volatility among companies on the site (CBOE delayed quotes)">✦ Options IV move</button>
          <button class="btn" type="button" data-engage="engage_opt13f" title="The biggest change in disclosed 13F puts or calls on a company on the site">✦ 13F puts & calls</button>
          <button class="btn" type="button" data-engage="engage_rsleaders" title="Companies whose relative-strength rating jumped into the 90s over three months">✦ RS leaders</button>
          <button class="btn" type="button" data-engage="engage_reddit_hot" title="Reddit's hottest stock right now as a cashtag, against what insiders, 13F managers and officials are doing in it">✦ Reddit's hottest vs the filings</button>
          <button class="btn" type="button" data-engage="engage_smart_buys" title="The stocks the traders with the best records are net buying now (smart-money score)">✦ Smart-money buying</button>
          <button class="btn" type="button" data-engage="engage_smart_record" title="An official, insider or 13F manager with a strong, tested record who just traded">✦ Track record</button>
          <button class="btn" type="button" data-engage="engage_all_agree" title="A stock that every group trading it (13F, ETFs, insiders, officials) net-bought this quarter">✦ All groups agree</button>
          <button class="btn" type="button" data-engage="engage_qtd_flows" title="The quarter so far: insiders' and officials' biggest net purchases, the early 13F filers' top add">✦ Quarter so far</button>
          <button class="btn" type="button" data-engage="engage_pt_upside" title="Two Hold-rated stocks, one with several times the analysts' price-target upside">✦ Same rating, different upside</button>
          <button class="btn" type="button" data-engage="engage_versus" title="“$A or $B — which would you rather have?” for two names people are watching">✦ $A or $B?</button>
          <button class="btn" type="button" data-engage="engage_drawdown" title="Popular names far below their 52-week highs, “$RKLB $150 → $50”">✦ Off the highs</button>
          <button class="btn" type="button" data-engage="engage_setup" title="The most-watched stock going into the next session, in bullets">✦ Stock setup</button>
          <button class="btn" type="button" data-engage="engage_lows52" title="The best-known names at new 52-week lows in the last session">✦ New 52-week lows</button>
          <button class="btn" type="button" data-engage="engage_highs52" title="The best-known names at new 52-week highs in the last session">✦ New 52-week highs</button>
          <button class="btn" type="button" data-engage="engage_near_lows" title="Profitable large companies near their 52-week lows">✦ Quality near lows</button>
          <button class="btn" type="button" data-engage="engage_records" title="New all-time highs (or lows) in the last session">✦ All-time highs / lows</button>
          <button class="btn" type="button" data-engage="engage_polymarket" title="Polymarket's odds that this week's reporters beat the EPS line">✦ Polymarket earnings odds</button>
          ${(xsite.engage_more || []).map((b) => `<button class="btn" type="button" data-engage="${t(b.kind)}" title="${t(b.title || '')}">${t(b.label)}</button>`).join('')}
        </div>
        <p class="muted small" id="engage-msg" role="status"></p>
        <h3>A fund's 13F</h3>
        <form class="row" id="fund-form"><input class="input" id="fund-cik" list="fund-list" placeholder="Manager CIK or a watched fund's name" aria-label="13F manager" autocomplete="off" required>
          <datalist id="fund-list"></datalist>
          <input class="input mono" id="fund-ref" placeholder="13F accession (blank = latest)" aria-label="13F accession">
          <button class="btn" type="submit">✦ 13F post</button></form>
        <p class="muted small">Any manager the Disclosures hub has processed: new positions, largest additions and cuts, exits and top holdings, with the 13F link.</p></section>` : ''}
      <section class="section" id="xreport"></section>
      <section class="section daily" id="daily" hidden></section>
      ${back}`;
    $('#owner-toggle').addEventListener('click', () => { prefs.set('owner', !on); route(); });
    getJSON('index.json').then((ix) => xReportPanel($('#xreport'), ix, osets)).catch((e) => console.warn('X report panel:', e.message));
    $$('[data-engage]').forEach((b) => b.addEventListener('click', () => withProgress(b, (x) => { $('#engage-msg').textContent = x || ''; },
      () => askFor({ cik: 0, period_end: localISO(new Date()), kind: b.dataset.engage, draft: !!($('#engage-draft') && $('#engage-draft').checked) }, b.textContent.replace(/^✦\s*/, '')))));
    bindDraft('engage-draft');
    const funds = {};
    fetch('disclosures/data/market/watchlist.json').then((r) => r.ok ? r.json() : null).then((w) => {
      const dl = $('#fund-list'); if (!w || !dl) return;
      (w.funds || []).forEach((f) => { funds[f.name] = f.cik; const o2 = document.createElement('option'); o2.value = f.name; dl.appendChild(o2); });
    }).catch(() => {});
    const ff = $('#fund-form');
    if (ff) ff.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const v = $('#fund-cik').value.trim(), cik = /^\d+$/.test(v) ? +v : funds[v];
      const ref = ($('#fund-ref').value || '').trim().match(/(\d{10})-?(\d{2})-?(\d{6})/);
      const btn = ff.querySelector('button');
      if (!cik) { $('#engage-msg').textContent = 'Enter a manager CIK (e.g. 1067983 for Berkshire Hathaway) or pick a watched fund'; return; }
      withProgress(btn, (x) => { $('#engage-msg').textContent = x || ''; },
        () => askFor({ cik, period_end: localISO(new Date()), kind: 'post_13f', ref: ref ? `${ref[1]}-${ref[2]}-${ref[3]}` : null,
          draft: !!($('#engage-draft') && $('#engage-draft').checked) }, '13F post'));
    });
    const form = $('#owner-form');
    if (form) form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      $('#owner-msg').textContent = 'Saving…';
      const patch = { thread_direct: $('input[name="thread-mail"]:checked').value === 'direct', daily_on: $('#daily-on').checked,
        daily_hour: +$('#daily-hour').value, tz: browserTZ() || o.tz, min_revenue: Math.round(Math.max(0, +$('#daily-min').value || 0) * 1e9),
        instant_threads: $('#instant-threads').checked, updated_at: new Date().toISOString() };
      if (newCols) patch.daily_scope = $('input[name="owner-scope"]:checked').value === 'all' ? 'all' : 'min_revenue';
      if (hasX) patch.x_post = xRead();
      const r = await c.from('owner_settings').update(patch).eq('id', true).select().single();
      if (r.error) { $('#owner-msg').textContent = `Could not save: ${r.error.message}`; return; }
      acct.osets = r.data;
      $('#owner-msg').textContent = 'Saved.';
      getJSON('index.json').then((ix) => dailyPanel($('#daily'), ix, { title: 'Send a daily report now' })).catch(() => {});
    });
    if (c) getJSON('index.json').then((ix) => dailyPanel($('#daily'), ix, { title: 'Send a daily report now' })).catch(() => {});
    if ($('#x-post')) xBind(xsite);
    if (c && $('#reread-form')) {
      const msg = (x) => { $('#reread-msg').textContent = x; };
      const ask = async (ciks, words, btn) => withProgress(btn, msg, async () => {
        const r = await askReread(ciks);
        showRereads(c);
        return r.ok ? `${words}: a short scan starts within a minute (owner fast lane) and reads them again.` : r.msg;
      });
      $('#reread-form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const btn = ev.submitter || $('#reread-form button[type=submit]');
        const { ciks, unknown } = await rereadCiks($('#reread-list').value);
        if (!ciks.length) { msg(unknown.length ? `Not found: ${unknown.join(', ')}` : 'Enter tickers or CIKs first'); return; }
        await ask(ciks, `Asked for ${ciks.length} compan${ciks.length === 1 ? 'y' : 'ies'}` + (unknown.length ? ` (not found: ${unknown.join(', ')})` : ''), btn);
        $('#reread-list').value = '';
      });
      $('#reread-all').addEventListener('click', (ev) => ask([0], 'Every stored company is queued, a few dozen per scan', ev.currentTarget));
      showRereads(c);
    }
  }
  // ---------- owner tools: the X post options (owner_settings.x_post, read by pipeline/xprefs.py) ----------
  // Every post that goes to Buffer: the scan's threads, "Post to X", the engagement and movers posts. Until the owner
  // saves them, config/x.json decides (its values arrive in site.json "x"). Cashtags ($NVDA) are never touched.
  const X_PARTS = [['kind', 'Post kind', '#earnings, #13F, #8K, #InsiderBuying …'], ['topic', 'Event topic', '8-K events: #MergersAndAcquisitions, #deal …'],
    ['industry', 'Industry', 'from the SEC industry code: #semiconductors, #banks, #pharma …'], ['general', 'General', 'one from the pool below, taking turns']];
  const xTag = (w) => { const v = String(w || '').replace(/#/g, '').replace(/[^A-Za-z0-9_]/g, '').slice(0, 40); return v && !/^\d+$/.test(v) ? '#' + v : ''; };
  const xUniq = (tags) => tags.filter((x, i, a) => x && a.findIndex((y) => y.toLowerCase() === x.toLowerCase()) === i);
  function xOptions(site, saved) {
    const d = { links: false, gif: false, hashtags_max: 3, hashtags: ['#stocks', '#investing', '#StockMarket', '#markets', '#investors', '#finance'],
      headline_tag: '#earnings', tags: { kind: true, topic: true, industry: true, general: true } };
    const base = Object.assign({}, d, site || {});
    const x = Object.assign({}, base, saved || {});
    x.tags = Object.assign({}, d.tags, base.tags || {}, (saved && saved.tags) || {});
    return x;
  }
  function xFieldset(x, site, ok) {
    const pool = xUniq([...(site.candidates || []), ...(x.hashtags || [])].map(xTag));
    const on = new Set((x.hashtags || []).map((t) => xTag(t).toLowerCase()));
    const dis = ok ? '' : 'disabled';
    const kinds = site.kinds || {};
    return `<fieldset id="x-post"><legend>X posts</legend>
      <p class="muted small">Every post that goes to Buffer: the scan’s threads, the Post to X buttons, the engagement and movers posts.
        Cashtags ($NVDA) always stay.${ok ? '' : ` <b>Run <span class="mono">supabase/schema.sql</span> again</b> (Supabase → SQL Editor) to set
        these here; until then <span class="mono">config/x.json</span> decides
        (now: ${x.links ? 'links allowed' : 'no links'}, ${x.gif ? 'GIF allowed' : 'still images only'}, ${+x.hashtags_max} hashtags).`}</p>
      <div role="radiogroup" aria-label="Links in posts" style="display:grid;gap:6px"><span>Links</span>
        <label class="long"><input type="radio" name="x-links" value="off" ${x.links ? '' : 'checked'} ${dis}><span>None: text, cashtags, hashtags and the chart images only</span></label>
        <label class="long"><input type="radio" name="x-links" value="on" ${x.links ? 'checked' : ''} ${dis}><span>Allowed (the filing, the company page)</span></label></div>
      <p class="muted small">No links takes every web address out of every post, also <span class="mono">sec.gov/…</span> written without https; a reply that
        was only a link is left out. Readers find the site from your profile link, the pinned post and the name on each chart.</p>
      <label class="long"><input type="checkbox" id="x-gif" ${x.gif ? 'checked' : ''} ${dis}><span>Animated GIF charts too (the two-year trend posts).
        Off: still PNG / JPG charts only; a GIF request goes out with the still charts.</span></label>
      <div class="inline-radios"><span>Hashtags per post</span>
        <select id="x-max" aria-label="Hashtags per post" ${dis}>${[0, 1, 2, 3, 4, 5, 6].map((n) => `<option value="${n}" ${+x.hashtags_max === n ? 'selected' : ''}>${n === 0 ? 'none' : n}</option>`).join('')}</select>
        <span class="muted small">in this order:</span></div>
      <div class="sub-choice" aria-label="Which kinds of tag">${X_PARTS.map(([k, name, ex]) => `<label><input type="checkbox" data-xpart="${k}"
          ${x.tags[k] !== false ? 'checked' : ''} ${dis}> ${name} <span class="muted small">${t(ex)}</span></label>`).join('')}</div>
      <label>Earnings headline tag <input id="x-head" class="mono" value="${t(x.headline_tag || '')}" placeholder="none" style="width:10em" ${dis}
        aria-label="Earnings headline tag"><span class="muted small">first line of earnings posts: “$NVDA NVIDIA Q2 FY27 #earnings”</span></label>
      <div><span class="muted small">General pool: the ticked tags take turns, one per post</span>
        <div class="chips x-pool" id="x-pool">${pool.map((tg) => `<label class="x-chip"><input type="checkbox" value="${t(tg)}" ${on.has(tg.toLowerCase()) ? 'checked' : ''} ${dis}> ${t(tg)}</label>`).join('')}</div>
        <div class="row" style="margin-top:6px"><input id="x-add" class="input mono" placeholder="#another" aria-label="Add a general tag" style="width:12em" ${dis}>
          <button class="btn" type="button" id="x-add-btn" ${dis}>Add</button></div></div>
      <p class="small" id="x-example" aria-live="polite"></p>
      <details class="small"><summary>The other pools</summary>
        <p class="muted">Post kinds: ${Object.entries(kinds).map(([k, v]) => `<b>${t(k)}</b> ${t(v.join(' '))}`).join(' · ') || '—'}</p>
        <p class="muted">Industries: ${t((site.industry || []).join(' ')) || '—'}</p></details>
    </fieldset>`;
  }
  function xRead() {
    const tags = {};
    $$('[data-xpart]').forEach((b) => { tags[b.dataset.xpart] = b.checked; });
    return { links: ($('input[name="x-links"]:checked') || {}).value === 'on', gif: $('#x-gif').checked, hashtags_max: +$('#x-max').value,
      hashtags: $$('#x-pool input:checked').map((b) => b.value), headline_tag: xTag($('#x-head').value), tags };
  }
  function xExample(x) {                                   // as pipeline/hashtags.py pick(): kind, topic, industry, one general
    const one = (own, topic, industry) => xUniq([...(x.tags.kind ? own.slice(0, 1) : []), ...(x.tags.topic && topic ? [topic] : []),
      ...(x.tags.industry ? [industry] : []), ...(x.tags.general ? x.hashtags.slice(0, 1) : []), ...(x.tags.kind ? own.slice(1) : []),
      ...(x.tags.general ? x.hashtags.slice(1) : [])]).slice(0, x.hashtags_max).join(' ') || 'no hashtags';
    return `Example — NVIDIA earnings: <span class="mono">$NVDA … ${t(one(xUniq([x.headline_tag, '#earnings', '#EarningsSeason'].map(xTag)), null, '#semiconductors'))}</span>;
      a drug maker’s merger 8-K: <span class="mono">$XYZ … ${t(one(['#8K', '#SEC'], '#MergersAndAcquisitions', '#pharma'))}</span>. The general tag changes from post to post.`;
  }
  function xBind(site) {
    const show = () => { const el = $('#x-example'); if (el) el.innerHTML = xExample(xRead()); };
    $('#x-post').addEventListener('change', show);
    $('#x-post').addEventListener('input', show);
    const add = () => {
      const tg = xTag($('#x-add').value);
      if (!tg) return;
      const have = $$('#x-pool input').find((b) => b.value.toLowerCase() === tg.toLowerCase());
      if (have) have.checked = true;
      else $('#x-pool').insertAdjacentHTML('beforeend', `<label class="x-chip"><input type="checkbox" value="${t(tg)}" checked> ${t(tg)}</label>`);
      $('#x-add').value = '';
      show();
    };
    $('#x-add-btn').addEventListener('click', add);
    $('#x-add').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); add(); } });
    show();
  }

  // the owner's re-read requests (table reread_requests): tickers or CIKs -> CIKs; cik 0 = every stored company
  async function rereadCiks(text) {
    const words = String(text || '').split(/[\s,;]+/).map((w) => w.trim()).filter(Boolean);
    const ix = await getJSON('index.json').catch(() => ({ companies: [] }));
    const all = await secCompanies();
    const ciks = [], unknown = [];
    for (const w of words) {
      if (/^\d+$/.test(w) && +w > 0) { ciks.push(+w); continue; }
      const tk = w.toUpperCase().replace('.', '-');
      const hit = ix.companies.find((x) => (x.ticker || '').toUpperCase() === tk) || all.find((x) => String(x[1]).toUpperCase() === tk);
      if (hit) ciks.push(+(hit.cik || hit[0])); else unknown.push(w);
    }
    return { ciks: [...new Set(ciks)], unknown };
  }
  async function askReread(ciks) {
    const cl = await sb();
    const r = await cl.from('reread_requests').insert(ciks.map((cik) => ({ cik })));
    if (r.error && tableMissing(r.error)) return { ok: false, msg: OWNER_UPDATE };
    if (r.error && /limit/i.test(r.error.message)) return { ok: false, msg: 'Limit reached: 200 re-reads a day' };
    if (r.error) return { ok: false, msg: `Could not ask: ${r.error.message}` };
    return { ok: true };
  }
  async function showRereads(c) {
    const box = $('#reread-list-box');
    const r = await c.from('reread_requests').select('*').order('created_at', { ascending: false }).limit(12);
    if (!box || !box.isConnected || r.error || !(r.data || []).length) return;
    const ix = await getJSON('index.json').catch(() => ({ companies: [] }));
    const name = (cik) => (+cik === 0 ? 'Every stored company' : ((ix.companies.find((x) => +x.cik === +cik) || {}).ticker || `CIK ${cik}`));
    const st = (x) => (x.status === 'done' ? `done ${date(x.done_at)}` : x.status === 'queued' ? 'reading in this scan' : x.status === 'failed' ? `failed: ${t(x.error || '')}` : 'waiting: a short scan starts within a minute');
    box.innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Asked</th><th>State</th></tr></thead><tbody>${
      r.data.map((x) => `<tr><td>${+x.cik ? `<a href="#c-${+x.cik}">${t(name(x.cik))}</a>` : t(name(x.cik))}</td><td>${date(x.created_at)}</td><td class="muted">${st(x)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  async function ownerSettings(fresh) {
    const c = await sb();
    if (!c) return null;
    if (acct.osets !== undefined && !fresh) return acct.osets;
    const r = await c.from('owner_settings').select('*').maybeSingle();
    acct.osets = r.error ? null : (r.data || null);
    return acct.osets;
  }

  // a company's place in the supply chains and themes (web/chains.js), as links under its name
  // the indices a company belongs to, now and before (disclosures/app/index_members.py → data/etf/members.json)
  const IDX_NAMES = { sp500: 'S&P 500', ndx: 'Nasdaq-100', dji: 'Dow 30', sp400: 'S&P MidCap 400', sp600: 'S&P SmallCap 600', r1000: 'Russell 1000', r2000: 'Russell 2000', r3000: 'Russell 3000' };
  const IDX_ORDER = ['dji', 'sp500', 'ndx', 'sp400', 'sp600', 'r1000', 'r2000', 'r3000'];
  async function coIndex(box, tk) {
    let m = null;
    try { m = await fetch('disclosures/data/etf/members.json').then((r) => (r.ok ? r.json() : null)); } catch (e) { m = null; }
    if (!m || !box || !box.isConnected) return;
    const T = String(tk).toUpperCase().replace(/\./g, '-'), r = (m.rows || {})[T];
    if (!r) return;
    const yr = (d) => (d ? String(d).slice(0, 4) : '');
    const now = IDX_ORDER.filter((k) => (r.now || []).includes(k)).map((k) => {
      const since = (r.since || {})[k] || (((r.was || {})[k] || []).find((x) => x[1] == null) || [])[0];
      const broad = k === 'r3000';
      return `<span class="tag${broad ? ' muted' : ''}" title="${t(broad ? 'Member of the broad US market index (Russell 3000)' : 'Member of the ' + IDX_NAMES[k] + (since ? ' since ' + since : ''))}">${t(IDX_NAMES[k])}${since ? ' · since ' + yr(since) : ''}</span>`;
    });
    const was = IDX_ORDER.filter((k) => ((r.was || {})[k] || []).some((x) => x[1] != null)).map((k) => {
      const spans = r.was[k].filter((x) => x[1] != null), after = (r.left_after || {})[k];
      const txt = spans.map((x) => (x[0] ? yr(x[0]) : 'before ' + yr(x[1])) + '–' + (after && x[1] === after ? 'after ' + after.slice(0, 7) : yr(x[1]))).join(', ');
      return `<span class="tag muted" title="${t('Former member of the ' + IDX_NAMES[k] + ': ' + txt)}">Former ${t(IDX_NAMES[k])} · ${t(txt)}</span>`;
    });
    if (!now.length && !was.length) return;
    box.innerHTML = '<span>Indices:</span>' + now.join('') + was.join('');
    box.hidden = false;
  }
  async function coChains(box, tk) {
    const ix = await getJSON('chains/index.json').catch(() => null);
    if (!ix || !box || !box.isConnected) return;
    const T = String(tk).toUpperCase();
    const hits = (ix.chains || []).map((c) => {
      const L = (c.layers || []).find((x) => (x.tickers || []).includes(T));
      return (c.buyers || []).includes(T) ? [c, 'buyer'] : L ? [c, L.name] : null;
    }).filter(Boolean);
    if (!hits.length) return;
    box.innerHTML = '<span>In the chains:</span>' + hits.map(([c, role]) => `<a class="tag" href="#chain-${t(c.id)}" title="${t(c.name)}">${t(c.name)} · ${t(role)}</a>`).join('');
    box.hidden = false;
  }
  // the chains pages (web/chains.js) use the app's loaders and settings
  const chainCtx = () => ({ getJSON, setNav, live, prefs, fontsReady });

  // ---------- router ----------
  async function route() {
    const here = (view++, live());
    CUR = '$';
    state.charts = [];
    if (toastEl) { toastEl.remove(); toastEl = null; }
    let h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    if (/^(access_token|error)=/.test(h)) {               // back from a link in a sign-in e-mail (if a template sends links)
      const failed = h.startsWith('error=');
      const user = failed ? null : await currentUser().catch(() => null);   // Supabase reads the sign-in from the address
      acct.flash = failed ? 'That sign-in link has expired or was used already. Enter your e-mail for a new code.'
        : user ? 'Signed in' : null;
      history.replaceState(null, '', location.pathname + location.search + '#account');
      h = 'account';
    }
    let m;
    try {
      if ((m = /^t-(.+)$/.exec(h))) {                    // a ticker link from the disclosures hub: open that company's page
        const cik = await cikForTicker(m[1]);
        if (!here()) return;
        if (!cik) throw new Error(`No SEC-registered company has the ticker ${m[1].toUpperCase()}`);
        history.replaceState(null, '', location.pathname + location.search + '#c-' + cik);
        h = 'c-' + cik;
      }
      if ((m = /^c-(\d+)-(cash|dollar|capital|bs|value|revisions|debt|risk|consensus|eps|posts|links|shock|holders|x-[a-z0-9]+)$/.exec(h))) await analysisPage(m[1], m[2]);
      else if ((m = /^c-(\d+)-fy-(\d{4}-\d{2}-\d{2})$/.exec(h))) await company(m[1], m[2], false, { fy: true });
      else if ((m = /^c-(\d+)-cmp-(\d+)$/.exec(h))) await company(m[1], null, false, { cmp: m[2] });
      else if ((m = /^c-(\d+)(?:-(\d{4}-\d{2}-\d{2}|all))?$/.exec(h))) await company(m[1], m[2] !== 'all' ? m[2] : null, m[2] === 'all');
      else if ((m = /^([si])-([a-z0-9-]+?)(?:-(CY\d{4}Q\d))?$/.exec(h))) await group(m[1], m[2], m[3]);
      else if ((m = /^ipo(?:-(\d+)(?:\/(\d{10}-\d{2}-\d{6}))?)?$/.exec(h)) && window.FFQualityIPO) await window.FFQualityIPO.ipo(app, here, m[1], m[2]);
      else if (h === 'sectors') await sectorsPage();
      else if (h === 'feed' && window.FFFeed) await window.FFFeed.render(app, Object.assign({}, window.FFApp, { here }));
      else if ((m = /^chart(?:\/(.*))?$/.exec(h)) && window.FFCharts) await window.FFCharts.render(app, Object.assign({}, window.FFApp, { here }), m[1] || '');
      else if ((m = /^studio(?:\/([\s\S]*))?$/.exec(h)) && window.FFStudio) await window.FFStudio.render(app, Object.assign({}, window.FFApp, { here }), m[1] || '');
      else if (h === 'chains' && window.FFChains) await window.FFChains.index(app, chainCtx());
      else if (h === 'model' && window.FFModel) await window.FFModel.overview(app, chainCtx());
      else if (h === 'gamma' && window.FFGamma) await window.FFGamma.index(app, chainCtx());
      else if ((m = /^gamma-(\d{4})$/.exec(h)) && window.FFGamma) await window.FFGamma.industry(app, m[1], chainCtx());
      else if ((m = /^chain-([a-z0-9-]+)$/.exec(h)) && window.FFChains) await window.FFChains.page(app, m[1], chainCtx());
      else if (h === 'method') await methodPage();
      else if (h === 'account') await accountPage();
      else if (h === 'owner') await ownerPage();
      else if (h === 'owner-xreport') { await ownerPage(); const x = $('#xreport'); if (x) x.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      else if ((m = /^unsubscribe-([0-9a-f-]{36})$/.exec(h))) await unsubscribePage(m[1]);
      else await home();
      initFollowButtons();
      initSendButtons();
      if (acct.flash) { toast(acct.flash); acct.flash = null; }
    } catch (err) {
      if (!here()) return;
      app.innerHTML = `<div class="page-head"><h1>Not available</h1><p class="muted">${t(err.message)}. The data may not have been generated yet; the scan runs every 15 minutes.</p><p><a href="#home">Back to the latest filings</a></p></div>`;
    }
  }
  let lastPage = null;
  window.addEventListener('hashchange', () => {
    const page = location.hash.split('-').slice(0, 2).join('-');
    route().then(() => { if (page !== lastPage) window.scrollTo(0, 0); lastPage = page; });
  });
  // what the discovery & UX modules (web/feed.js, charts.js) need from the app
  window.FFApp = {
    getJSON, setNav, here: () => true,
    async loadFollows() {
      const user = await currentUser().catch(() => null);
      if (!user) return { signedIn: false, tickers: [] };
      const p = acct.prefs || await loadPrefs().catch(() => null);
      return { signedIn: true, tickers: (p && p.tickers) || [] };
    },
  };
  setupSearch();
  setupTheme();
  route();
  if (window.FilingFlowsApp) currentUser().then((u) => u && !acct.prefs && loadPrefs()).catch(() => {});   // the app's notifications use the follows
})();
