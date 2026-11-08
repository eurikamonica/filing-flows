/* French and Spanish versions of the site (EN · FR · ES in the header).
   The pages are written in English; this translates what the reader sees after each render: the interface (menus,
   tabs, buttons, headings, tiles), the charts' line names, periods ("Q3 2026" → "T3 2026"), dates and amounts
   ("€10.3B" → "10,3 Md€" / "10,3 mil M€"). Long generated text (the analysis paragraphs, quotations from filings) stays
   in English. The language: ?lang=fr|es in the address, else the reader's last choice, else the browser's language.
   Phrases come from web/i18n-dict.js (FFI18N: [english, french, spanish]). */
(function (root) {
  'use strict';
  const LANGS = ['en', 'fr', 'es'];
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } } };

  function pick() {
    const q = (new URLSearchParams(root.location.search).get('lang') || '').toLowerCase();
    if (LANGS.includes(q)) { store.set('ff:lang', q); return q; }
    const saved = store.get('ff:lang');
    if (LANGS.includes(saved)) return saved;
    const nav = String((root.navigator && (root.navigator.language || '')) || '').slice(0, 2).toLowerCase();
    return nav === 'fr' || nav === 'es' ? nav : 'en';
  }
  const lang = pick();
  root.FFLang = lang;
  document.documentElement.lang = lang;

  // ------------------------------------------------------------------ the switch in the header
  function setLang(l) {
    store.set('ff:lang', l);
    const u = new URL(root.location.href);
    if (l === 'en') u.searchParams.delete('lang'); else u.searchParams.set('lang', l);
    root.location.replace(u.toString());               // a fresh page in the new language (every view re-renders)
  }
  // one small button (a globe and the language's code) that opens the three languages: it takes the room of one button
  const NAMES = { en: 'English', fr: 'Français', es: 'Español' };
  const GLOBE = '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.3"/>' +
    '<path d="M1.5 8h13M8 1.5c-2 2-2.8 4.1-2.8 6.5S6 12.5 8 14.5M8 1.5c2 2 2.8 4.1 2.8 6.5S10 12.5 8 14.5" fill="none" stroke="currentColor" stroke-width="1.1"/></svg>';
  function addSwitch() {
    const bar = document.querySelector('header.top .wrap');
    if (!bar || bar.querySelector('.lang-pick')) return;
    const box = document.createElement('div');
    box.className = 'lang-pick notranslate';
    box.innerHTML = `<button type="button" class="lang-btn" aria-haspopup="true" aria-expanded="false" title="Language · Langue · Idioma"` +
      ` aria-label="${{ en: 'Language', fr: 'Langue', es: 'Idioma' }[lang]}: ${NAMES[lang]}">${GLOBE}<span>${lang.toUpperCase()}</span></button>` +
      `<div class="lang-menu" role="menu" hidden>${LANGS.map((l) => `<button type="button" role="menuitemradio" aria-checked="${l === lang}"` +
      ` data-lang="${l}" lang="${l}"${l === lang ? ' class="on"' : ''}><span>${NAMES[l]}</span><span class="lang-code">${l.toUpperCase()}</span></button>`).join('')}</div>`;
    const btn = box.querySelector('.lang-btn'), menu = box.querySelector('.lang-menu');
    const show = (open) => { menu.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
    btn.addEventListener('click', (e) => { e.stopPropagation(); show(menu.hidden); if (!menu.hidden) menu.querySelector('.on').focus(); });
    menu.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-lang]');
      if (!b) return;
      show(false);
      if (b.dataset.lang !== lang) setLang(b.dataset.lang);
    });
    box.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { show(false); btn.focus(); }
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !menu.hidden) {
        const items = [...menu.querySelectorAll('button')], i = items.indexOf(document.activeElement);
        items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length].focus();
        e.preventDefault();
      }
    });
    document.addEventListener('click', (e) => { if (!box.contains(e.target)) show(false); });
    // the small buttons at the right of the header (⌘K, theme, Settings, language) stay together: when the header is too
    // narrow for one row they move to the next one as a group, at the right
    const theme = bar.querySelector('#theme');
    if (theme && theme.parentElement === bar) {
      const tools = document.createElement('div');
      tools.className = 'top-tools';
      theme.before(tools);
      ['#palette-btn', '#theme', '#ff-appearance-button'].forEach((q) => { const b = bar.querySelector(q); if (b && b.parentElement === bar) tools.appendChild(b); });
      tools.appendChild(box);
    } else if (theme) theme.after(box);
    else bar.appendChild(box);
  }
  // links inside the site keep the language (a shared link opens in it)
  function keepLang(a) {
    if (lang === 'en' || !a || !a.getAttribute) return;
    const h = a.getAttribute('href');
    if (!h || /^(https?:|mailto:|#|javascript:)/i.test(h) || /[?&]lang=/.test(h)) return;
    if (/\.(xml|csv|json|png|jpg|pdf|svg)(\?|#|$)/i.test(h)) return;
    const [path, hash] = h.split('#');
    a.setAttribute('href', `${path}${path.includes('?') ? '&' : '?'}lang=${lang}${hash !== undefined ? '#' + hash : ''}`);
  }

  // the phrases (web/i18n-dict.js) load only for a French or Spanish reader, and before the page's own scripts run (a
  // script written while the page is read runs next): the charts are laid out in the reader's language from the start
  const SRC = (document.currentScript && document.currentScript.src) || '';
  const DICT = SRC ? SRC.replace(/i18n\.js(\?.*)?$/, 'i18n-dict.js') : '';
  if (lang !== 'en' && !root.FFI18N && DICT && document.readyState === 'loading' && typeof document.write === 'function') {
    document.write(`<script src="${DICT}"><\/script>`);
  }

  if (lang === 'en') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addSwitch); else addSwitch();
    root.FFT = (s) => s;
    root.FFT.keep = (s) => s;
    return;
  }

  // ------------------------------------------------------------------ the phrases
  const L = lang === 'fr' ? 1 : 2;
  const EXACT = new Map();
  let PIECES = [], TEMPLATES = [], built = false;
  function build() {                                      // the phrase tables, once the phrases have loaded
    if (built || !root.FFI18N) return;
    built = true;
    root.FFI18N.forEach((row) => { if (row[L]) EXACT.set(norm(row[0]), row[L]); });
    PIECES = (root.FFI18N_PIECES || []).map(([re, fr, es]) => [new RegExp(re, 'g'), lang === 'fr' ? fr : es]);
    TEMPLATES = (root.FFI18N_TEMPLATES || []).map(([re, fr, es]) => [new RegExp(re), lang === 'fr' ? fr : es]);
    cache.clear();
  }
  function norm(s) { return String(s).replace(/\s+/g, ' ').replace(/&amp;/g, '&').trim(); }

  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const M_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  const M_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const MS_FR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  const MS_ES = ['ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.', 'jul.', 'ago.', 'sept.', 'oct.', 'nov.', 'dic.'];
  const NB = ' ', NNB = ' ';

  // amounts: "€10.3B" → "10,3 Md€" (fr) / "10,3 mil M€" (es); "$233.45" → "233,45 $"
  const UNIT = lang === 'fr' ? { K: 'k', M: 'M', B: 'Md', T: 'Bn' } : { K: 'mil', M: 'M', B: 'mil M', T: 'B' };
  const CUR = '(US\\$|C\\$|A\\$|NZ\\$|HK\\$|NT\\$|S\\$|R\\$|MX\\$|\\$|€|£|¥|₩|₹|₪|₺|฿|₱|CHF |SEK |DKK |NOK |RMB |ZAR |zł |RM |Rp )';
  function num(s) {                                      // "1,234.5" → "1 234,5" (fr) / "1.234,5" (es)
    const [i, d] = s.split('.');
    const int = i.replace(/,/g, lang === 'fr' ? NNB : '.');
    return d !== undefined ? `${int},${d}` : int;
  }
  function money(m, sign, cur, n, unit) {
    const c = cur.trim();
    const amt = num(n) + (unit ? `${NB}${UNIT[unit]}` : '');
    const glued = unit && c.length === 1 && !(lang === 'es' && unit === 'K');   // "10,3 Md€", "1,2 Md US$", "233,45 $", "25 mil $"
    return `${sign ? '−' : ''}${amt}${glued ? '' : NB}${c}`;
  }

  // periods, ratios and dates: "Q3 2026" → "T3 2026" (fr) / "3T 2026" (es); "Q1 FY27" → "T1 Ex.27" / "1T AF27"
  const FR = lang === 'fr';
  const qq = (q) => (FR ? `T${q}` : `${q}T`), hh = (h) => (FR ? `S${h}` : `${h}S`), fy = FR ? 'Ex.' : 'AF';
  const RULES = [
    [/\bQ([1-4]) FY(\d\d)\b/g, (m, q, y) => `${qq(q)} ${fy}${y}`],
    [/\bH([12]) FY(\d\d)\b/g, (m, h, y) => `${hh(h)} ${fy}${y}`],
    [/\bFY ?(\d{4})\b/g, (m, y) => `${fy} ${y}`],
    [/\bFY(\d\d)\b/g, (m, y) => `${fy}${y}`],
    [/\bQ([1-4]) (\d{4})\b/g, (m, q, y) => `${qq(q)} ${y}`],
    [/\bH([12]) (\d{4})\b/g, (m, h, y) => `${hh(h)} ${y}`],
    [/\bQ([1-4])(['’]\d\d)\b/g, (m, q, y) => `${qq(q)}${y}`],
    [/\bQ([1-4])\b(?![\/-]| ?[A-Z][a-z])/g, (m, q) => qq(q)],          // not "Q2 Holdings"
    [/\bH([12])\b(?![\/-]| ?[A-Z][a-z])/g, (m, h) => hh(h)],
    [/\bY\/Y\b/g, 'a/a'], [/\bQ\/Q\b/g, 't/t'], [/\bH\/H\b/g, 's/s'],
    [new RegExp(`\\b(${MONTHS.join('|')}) (\\d{1,2}), (\\d{4})\\b`, 'g'),
      (m, mo, d, y) => (FR ? `${d === '1' ? '1er' : d} ${M_FR[MONTHS.indexOf(mo)]} ${y}` : `${d} de ${M_ES[MONTHS.indexOf(mo)]} de ${y}`)],
    [new RegExp(`\\b(${MON.join('|')}) (\\d{1,2}), (\\d{4})\\b`, 'g'),
      (m, mo, d, y) => `${d} ${(FR ? MS_FR : MS_ES)[MON.indexOf(mo)]} ${y}`],
    [new RegExp(`\\b(${MONTHS.join('|')}) (\\d{4})\\b`, 'g'),
      (m, mo, y) => (FR ? `${M_FR[MONTHS.indexOf(mo)]} ${y}` : `${M_ES[MONTHS.indexOf(mo)]} de ${y}`)],
    [new RegExp(`\\b(${MON.join('|')}) (\\d{4})\\b`, 'g'),
      (m, mo, y) => `${(FR ? MS_FR : MS_ES)[MON.indexOf(mo)]} ${y}`],
    [new RegExp(`\\b(${MONTHS.join('|')}) (\\d{1,2}),?(?= |$)`, 'g'),
      (m, mo, d) => (FR ? `${d} ${M_FR[MONTHS.indexOf(mo)]}` : `${d} de ${M_ES[MONTHS.indexOf(mo)]}`)],
    [new RegExp(`\\b(${MON.join('|')}) (\\d{1,2})(?=[ ,·)]|$)`, 'g'),
      (m, mo, d) => `${d} ${(FR ? MS_FR : MS_ES)[MON.indexOf(mo)]}`],
  ];
  // the figures, in one pass (a converted figure is never read again): an amount "€10.3B", a figure "1,234.5" or "2.5",
  // a count with a unit "1.2B"; what comes before is kept; "25.3x" is a figure too
  const FIG = new RegExp(`(^|[^\\w.,])(?:([−-])?${CUR}(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?)([KMBT])?` +
    `|(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+\\.\\d+)([KMBT])?)(?![.,]\\d)(?=x\\b|×|[^\\w]|$)`, 'g');
  function figures(t) {
    return t.replace(FIG, (m, pre, sign, cur, n, unit, n2, unit2) => {
      if (cur !== undefined) return pre + money(m, sign, cur, n, unit);
      return pre + num(n2) + (unit2 ? `${NB}${UNIT[unit2]}` : '');
    });
  }
  const PCT = /(\d)%/g;

  // pieces of short labels: "22% of revenue", "€0.80B · 27% of pre-tax", "+13% Q/Q", "−9% from high"

  // sentences with a part that changes ("No 8-K from AAPL on file in the last four months."): the part is translated too

  // what is still an English sentence once the pieces are taken out (one of these words) stays English, figures and all
  const STOP = /\b(?:the|a|an|and|or|of|to|in|on|at|by|for|with|from|into|was|were|is|are|be|been|has|have|had|it|its|this|that|these|those|than|then|while|but|not|no|yet|as|after|before|over|under|rose|fell|grew|each|every|which|who|what|when|how|there|here|their|they|we|you|your|our|can|will|would|should|could|do|does|did|The|An|This|That|These|It|Its|No|Not|Each|Every|Which|What|When|How|Where|Who|There|Here|Their|They|We|You|Your|Our)\b/;   // "May" is a month

  // words that begin a phrase rather than name a line ("All 8 quarters", "Latest 32 quarters"): left to the pieces
  const GENERIC = new Set(['All', 'Any', 'Every', 'Top', 'Last', 'Next', 'Latest', 'First', 'Over', 'Under', 'Since', 'From', 'To', 'Now', 'Then']);
  // one string: a phrase of the dictionary; else its parts ("A · B"), a phrase with its figure ("Assets €10.3B",
  // "Cash: €1.2B"); else, when short, pieces, periods, dates and figures
  function trCore(core) {
    let out = EXACT.get(core);
    if (out !== undefined) return out;
    const k = core.replace(/[:：]$/, '');                      // "Period:" as "Period"
    if (k !== core && EXACT.has(k)) return EXACT.get(k) + (FR ? NB + ':' : ':');
    for (const [re, to] of TEMPLATES) {
      const t = core.match(re);
      if (t) return to.replace(/\$(\d)/g, (x, i) => trCore(t[+i] || ''));
    }
    if (core.length > 160) return core;                        // long generated text: as written
    if (core.includes(' · ')) return core.split(' · ').map(trCore).join(' · ');
    if (/^· ./.test(core)) return '· ' + trCore(core.slice(2));          // "· quarterly results release …" after a link
    if (/. ·$/.test(core)) return trCore(core.slice(0, -2)) + ' ·';
    // a phrase, then its figure or period: "Assets €10.3B", "Cash: €1.2B", "Operating income, Q4 FY25 → Q4 FY26"
    const m = core.match(/^([^\d:,]+?)(: |, | )((?:[−+-]?[^\s\d]{0,4}\d|Q[1-4]\b|H[12]\b|FY\d)[\s\S]*)$/);
    if (m && EXACT.has(m[1]) && !GENERIC.has(m[1])) return EXACT.get(m[1]) + (m[2] === ': ' && FR ? NB + ': ' : m[2]) + trCore(m[3]);
    if (core.length > 90) return core;
    let t = core, bare = core;
    for (const [re, to] of PIECES) { t = t.replace(re, to); bare = bare.replace(re, ' '); }
    if (STOP.test(bare)) return core;                          // an English sentence: as written
    for (const [re, to] of RULES) t = t.replace(re, to);
    return figures(t).replace(PCT, `$1${FR ? NNB : NB}%`);
  }
  const cache = new Map(), done = new Set();              // done: what this wrote (never translated twice)
  // act: the text of a button that does something ("Close" there is "Fermer"; in a table, the price "Clôture")
  function tr(s, act) {
    if (!built) build();
    if (!s || !/[A-Za-z0-9]/.test(s) || done.has(s)) return s;
    const key = act ? '\u0001' + s : s;
    if (cache.has(key)) return cache.get(key);
    const lead = s.match(/^\s*/)[0], tail = s.match(/\s*$/)[0], core = norm(s);
    const out = (act && EXACT.get('act:' + core)) || trCore(core);
    const r = out === core ? s : lead + out + tail;
    if (cache.size > 40000) { cache.clear(); done.clear(); }
    cache.set(key, r);
    if (r !== s) done.add(r);
    return r;
  }
  const ACT = 'button:not(.th-sort), [role="button"], a.btn';
  const acts = (el) => !!(el && el.closest && el.closest(ACT));
  tr.keep = (s) => { if (s) done.add(s); return s; };    // a piece of a translated text (a chart's wrapped line)
  root.FFT = tr;

  // ------------------------------------------------------------------ the page
  const SKIP = 'script,style,noscript,textarea,code,pre,.notranslate,[translate="no"]';
  const ATTRS = ['placeholder', 'title', 'aria-label'];
  function skip(el) { return !el || (el.closest && el.closest(SKIP)); }
  function doText(n) {
    const p = n.parentElement;
    if (skip(p)) return;
    const v = n.nodeValue, t = tr(v, acts(p));
    if (t !== v) n.nodeValue = t;
  }
  function doEl(el) {
    if (el.nodeType !== 1 || skip(el)) return;
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v) { const t = tr(v, acts(el)); if (t !== v) el.setAttribute(a, t); }
    }
    if (el.tagName === 'A') keepLang(el);
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) doText(n);
      else if (!skip(n)) {
        for (const a of ATTRS) {
          const v = n.getAttribute(a);
          if (v) { const t = tr(v, acts(n)); if (t !== v) n.setAttribute(a, t); }
        }
        if (n.tagName === 'A') keepLang(n);
      }
    }
  }
  let queued = new Set(), timer = null;
  function flush() {
    timer = null;
    const items = queued;
    queued = new Set();
    obs.disconnect();
    items.forEach((x) => { if (x.nodeType === 3) doText(x); else doEl(x); });
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  const obs = new MutationObserver((list) => {
    for (const m of list) {
      if (m.type === 'characterData') queued.add(m.target);
      else m.addedNodes.forEach((n) => queued.add(n));
    }
    if (!timer) timer = setTimeout(flush, 0);
  });
  function start() {
    addSwitch();
    if (!root.FFI18N && DICT) {                          // the phrases did not load with the page: load them now
      const sc = document.createElement('script');
      sc.src = DICT;
      sc.onload = () => { build(); doEl(document.body); };
      document.head.appendChild(sc);
    }
    doEl(document.body);
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
    document.title = tr(document.title);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  // the tab title the app sets later
  const t0 = Object.getOwnPropertyDescriptor(Document.prototype, 'title');
  if (t0 && t0.set) {
    Object.defineProperty(document, 'title', { configurable: true, get() { return t0.get.call(document); },
      set(v) { t0.set.call(document, tr(String(v))); } });
  }
})(window);
