/* Outlook & guidance (company page → Valuation & expectations): what the company says about the future, in one place.

   - the latest guidance (the earnings release's ranges, raised / lowered / reaffirmed …) — holders/<T>.json guidance;
   - the guidance record and hit rate: every guided period against what was then reported (web/guidance.js record()),
     from every release kept (holders → guidance_history) and the guided figures of the 10-Q / 10-K MD&A for the
     periods no release guided (data/outlook/<cik>.json, pipeline/outlook.py);
   - the forward-looking statements of the latest MD&A and earnings release: by topic, tone, hedged or not, and what is
     new, updated or no longer said since the filing before; the tone filing by filing;
   - the 8-K timeline: the latest current reports (results, guidance, deals, people …) — holders → events8k.

   merge(history, outlook) is shared with scripts/guidance_board.cjs (the hub's hit-rate board). */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TOPIC = { demand: 'Demand & revenue', margin: 'Margins & pricing', costs: 'Costs', capex: 'Capital spending', returns: 'Buybacks & dividends',
    financing: 'Financing', people: 'People & restructuring', deals: 'Deals', products: 'Products', legal: 'Regulation & legal', tax: 'Tax',
    backlog: 'Backlog & orders', ai: 'AI', other: 'Other' };
  const STATUS = { new: 'new', updated: 'updated', repeated: 'repeated', first: '' };
  const GUIDE = { raised: '▲ raised', lowered: '▼ lowered', narrowed: '→← narrowed', widened: '←→ widened', reaffirmed: '= reaffirmed',
    initiated: '✦ initiated', withdrawn: '✕ withdrawn', mixed: '▲▼ mixed', updated: 'updated' };
  const ITEM = { '1.01': 'agreement', '1.02': 'agreement ended', '2.01': 'acquisition or sale', '2.02': 'results', '2.03': 'new debt', '2.05': 'restructuring',
    '2.06': 'impairment', '3.01': 'listing notice', '3.02': 'share sale', '4.01': 'auditor change', '4.02': 'restatement', '5.02': 'officers or directors',
    '5.03': 'bylaws', '5.07': 'shareholder vote', '7.01': 'Reg FD', '8.01': 'other events' };
  const fdate = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+m[2] - 1]} ${+m[3]}, ${m[1]}` : (s || ''); };

  // the releases' guidance plus the MD&A's guided figures for what no release guided (same metric, basis, unit and period)
  function merge(history, outlook) {
    const rels = ((history && history.releases) || []).slice();
    const have = new Set();
    rels.forEach((r) => (r.items || []).forEach((it) => have.add([it.metric, it.basis || '', it.unit, it.period].join('|'))));
    ((outlook && outlook.docs) || []).filter((d) => d.kind === 'mdna' && (d.items || []).length).forEach((d) => {
      const items = d.items.filter((it) => !have.has([it.metric, it.basis || '', it.unit, it.period].join('|')));
      if (items.length) rels.push({ filed: d.filed, accession: d.accn, url: d.url, label: null, tags: [], items, src: d.form });
    });
    return rels.length ? { releases: rels, complete: !!(history && history.complete) } : null;
  }
  // one number for a company: periods met or beaten over periods judged, across metrics
  function hitRate(rec) {
    const ms = ((rec && rec.metrics) || []).filter((m) => m.hits && m.hits.n);
    const n = ms.reduce((a, m) => a + m.hits.n, 0), hit = ms.reduce((a, m) => a + m.hits.hitOrBeat, 0);
    const beat = ms.reduce((a, m) => a + (m.hits.better === 'higher' ? m.hits.above : m.hits.below), 0);
    const miss = ms.reduce((a, m) => a + (m.hits.better === 'higher' ? m.hits.below : m.hits.above), 0);
    return n ? { n, hit, beat, miss, rate: hit / n, metrics: ms.map((m) => [m.name, m.hits.hitOrBeat, m.hits.n]) } : null;
  }

  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.olv{display:grid;gap:14px}.olv .olv-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0;overflow:hidden}
.olv h3{margin:0 0 6px;font-size:1rem}.olv .muted{opacity:.75;font-size:.82rem}.olv .olv-kpis{display:flex;flex-wrap:wrap;gap:8px 18px;margin:6px 0}
.olv .olv-kpi b{display:block;font-size:1.35rem;font-weight:600}.olv .olv-kpi span{font-size:.8rem;opacity:.75}
.olv table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.85rem}.olv td,.olv th{padding:4px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:left;vertical-align:top;overflow-wrap:anywhere}
.olv th{white-space:nowrap;position:static}.olv td.d{white-space:nowrap}.olv td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.olv .tag{display:inline-block;font-size:.72rem;border-radius:999px;padding:0 7px;margin-right:4px;border:1px solid currentColor;opacity:.85;white-space:nowrap}
.olv .t-new{color:#1d4ed8}.olv .t-updated{color:#b54708}.olv .t-repeated{color:#667085}.olv .t-pos{color:#17734a}.olv .t-neg{color:#b42318}
.olv .up{color:#17734a}.olv .down{color:#b42318}.olv ul.fls{list-style:none;padding:0;margin:6px 0}.olv ul.fls li{padding:7px 0;border-bottom:1px solid var(--line,#e4e7ec);font-size:.9rem;line-height:1.45}
.olv ul.fls li .was{display:block;font-size:.8rem;opacity:.7;margin-top:2px}.olv .chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.olv .chips button{font:inherit;font-size:.78rem;border:1px solid var(--line,#d0d5dd);background:transparent;border-radius:999px;padding:2px 9px;cursor:pointer;color:inherit}
.olv .chips button[aria-pressed="true"]{background:var(--ink,#1d2939);color:var(--bg,#fff)}.olv details summary{cursor:pointer;font-size:.88rem}
.olv .tone{display:flex;gap:3px;align-items:flex-end;height:46px;margin:6px 0 2px}.olv .tone i{flex:1;max-width:26px;border-radius:2px 2px 0 0;background:#98a2b3}
.olv .tone i.p{background:#3a9d6a}.olv .tone i.n{background:#d9480f}.olv .guide-record{margin-top:4px}`;
    document.head.appendChild(s);
  }
  const loaders = {};
  const getJSON = (u) => (loaders[u] = loaders[u] || fetch(u, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const loadScript = (src) => new Promise((ok) => { const sc = document.createElement('script'); sc.src = src; sc.onload = ok; sc.onerror = ok; document.head.appendChild(sc); });

  function latestGuidance(g, G) {
    if (!g || !(g.items || []).length) return '';
    const rows = g.items.filter((it) => it.lo != null && !it.scope).slice(0, 12).map((it) => {
      const w = G && G.words ? G.words(it) : [];
      const cls = /raised/.test(w.join(' ')) ? 'up' : /lowered/.test(w.join(' ')) ? 'down' : '';
      return `<tr><td>${esc(it.name || it.metric)}${it.basis ? ` <span class="muted">${esc(it.basis)}</span>` : ''}</td><td class="d">${esc(it.period || '')}</td>
        <td class="n">${esc(G && G.range ? G.range(it) : `${it.lo}–${it.hi}`)}</td><td class="${cls}">${esc(w.join(' · '))}${it.prior && G && G.priorText ? `<br><span class="muted">${esc(G.priorText(it))}</span>` : ''}</td></tr>`;
    }).join('');
    return `<div class="olv-card"><h3>Latest guidance <span class="muted">${esc(g.headline && !/^for (?:immediate )?release/i.test(g.headline) ? g.headline : 'Earnings release')} · ${esc(fdate(g.filed))}</span></h3>
      ${g.label ? `<p><b class="${/raised/.test(g.label) ? 'up' : /lowered|withdrawn/.test(g.label) ? 'down' : ''}">${esc(GUIDE[g.label] || g.label)}</b>${g.phrase && g.phrase !== g.label ? ` — “${esc(g.phrase)}”` : ''}</p>` : ''}
      <div style="overflow-x:auto"><table><thead><tr><th>Metric</th><th>Period</th><th style="text-align:right">Guided</th><th>Change</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${g.quote ? `<p class="muted">“${esc(g.quote.length > 320 ? g.quote.slice(0, 318) + '…' : g.quote)}”</p>` : ''}
      ${g.url ? `<p class="muted"><a href="${esc(g.url)}" target="_blank" rel="noopener">The release on EDGAR ↗</a></p>` : ''}</div>`;
  }

  function flsCard(doc, title, older) {
    if (!doc) return '';
    const st = doc.statements || [], c = doc.counts || {};
    const topics = [...new Set(st.map((s) => s.topic))];
    const li = (s) => `<li data-topic="${esc(s.topic)}">${STATUS[s.status] ? `<span class="tag t-${esc(s.status)}">${esc(STATUS[s.status])}</span>` : ''}<span class="tag">${esc(TOPIC[s.topic] || s.topic)}</span>${s.tone !== 'neutral' ? `<span class="tag ${s.tone === 'positive' ? 't-pos' : 't-neg'}">${s.tone === 'positive' ? '▲' : '▼'}</span>` : ''}${s.hedge ? '<span class="tag t-repeated">hedged</span>' : ''}${s.when ? `<span class="muted">${esc(s.when)} · </span>` : ''}${esc(s.t)}${s.was ? `<span class="was">was: ${esc(s.was)}</span>` : ''}</li>`;
    const order = { new: 0, updated: 1, first: 2, repeated: 3 };
    const sorted = st.slice().sort((a, b) => (order[a.status] ?? 2) - (order[b.status] ?? 2));
    const tone = (older || []).slice(0, 8).reverse();
    return `<div class="olv-card" data-fls><h3>${esc(title)} <span class="muted">${esc(doc.form)} filed ${esc(fdate(doc.filed))}${doc.url ? ` · <a href="${esc(doc.url)}" target="_blank" rel="noopener">open ↗</a>` : ''}</span></h3>
      <div class="olv-kpis"><div class="olv-kpi"><b>${c.n || 0}</b><span>statements about the future</span></div>
        ${doc.vs ? `<div class="olv-kpi"><b class="t-new">${c.new || 0}</b><span>new</span></div><div class="olv-kpi"><b class="t-updated">${c.updated || 0}</b><span>updated</span></div><div class="olv-kpi"><b>${c.dropped || 0}</b><span>no longer said</span></div>` : ''}
        <div class="olv-kpi"><b class="${(c.tone || 0) > 0.1 ? 'up' : (c.tone || 0) < -0.1 ? 'down' : ''}">${c.tone == null ? '—' : (c.tone > 0 ? '+' : '') + Math.round(100 * c.tone)}</b><span>tone (−100 to +100)</span></div>
        <div class="olv-kpi"><b>${c.n ? Math.round(100 * (c.hedged || 0) / c.n) : 0}%</b><span>hedged</span></div></div>
      ${tone.length > 1 ? `<div class="tone" aria-label="Tone filing by filing">${tone.map((d) => { const t = (d.counts || {}).tone || 0; return `<i class="${t > 0.05 ? 'p' : t < -0.05 ? 'n' : ''}" style="height:${Math.max(4, Math.round(46 * Math.min(1, Math.abs(t) * 1.6 + 0.15)))}px" title="${esc(d.form + ' ' + d.filed)}: tone ${Math.round(100 * t)}"></i>`; }).join('')}</div><p class="muted">Tone of each ${doc.kind === 'mdna' ? 'MD&A' : 'release'}, oldest to newest: green leaning positive, orange negative.</p>` : ''}
      ${topics.length > 1 ? `<div class="chips"><button type="button" data-t="" aria-pressed="true">All</button>${topics.map((t) => `<button type="button" data-t="${esc(t)}" aria-pressed="false">${esc(TOPIC[t] || t)} ${st.filter((s) => s.topic === t).length}</button>`).join('')}</div>` : ''}
      <ul class="fls">${sorted.slice(0, 14).map(li).join('')}</ul>
      ${sorted.length > 14 ? `<details><summary>${sorted.length - 14} more</summary><ul class="fls">${sorted.slice(14).map(li).join('')}</ul></details>` : ''}
      ${(doc.dropped || []).length ? `<details><summary>No longer said (${doc.dropped.length}) — in the ${doc.kind === 'mdna' ? 'filing' : 'release'} before, not in this one</summary><ul class="fls">${doc.dropped.map((s) => `<li><span class="tag">${esc(TOPIC[s.topic] || s.topic)}</span>${esc(s.t)}</li>`).join('')}</ul></details>` : ''}</div>`;
  }

  function events(rows) {
    if (!(rows || []).length) return '';
    return `<div class="olv-card"><h3>8-K timeline <span class="muted">current reports, newest first</span></h3><div style="overflow-x:auto"><table><tbody>
      ${rows.slice(0, 12).map((r) => `<tr><td class="d">${esc(fdate(r.filed))}</td><td>${(r.items || []).map((i) => `<span class="tag">${esc(i)} ${esc(ITEM[i] || '')}</span>`).join('')}${r.guidance ? `<span class="tag ${/raised/.test(r.guidance) ? 't-pos' : /lowered|withdrawn/.test(r.guidance) ? 't-neg' : ''}">guidance ${esc(GUIDE[r.guidance] || r.guidance)}</span>` : ''}
        <br>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.headline || (r.topics || []).join(', ') || '8-K')}</a>` : esc(r.headline || '')}${r.quote && r.quote !== r.headline ? `<br><span class="muted">${esc(r.quote.length > 220 ? r.quote.slice(0, 218) + '…' : r.quote)}</span>` : ''}</td></tr>`).join('')}
      </tbody></table></div><p class="muted">8-Ks report material events within four business days: results (2.02), deals, officers leaving or joining, new debt, restatements… kept here for 120 days.</p></div>`;
  }

  function bind(el) {
    el.querySelectorAll('[data-fls]').forEach((card) => card.querySelectorAll('.chips button').forEach((b) => {
      b.onclick = () => {
        card.querySelectorAll('.chips button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        const t = b.dataset.t;
        card.querySelectorAll('ul.fls > li[data-topic]').forEach((li) => { li.style.display = !t || li.dataset.topic === t ? '' : 'none'; });
        const det = card.querySelector('details'); if (t && det && !det.open && det.querySelector(`li[data-topic="${t}"]`)) det.open = true;
      };
    }));
  }

  async function render(el, opt) {
    css();
    const o = opt || {}, hub = o.hub || '', cik = String(o.cik || '').replace(/^0+/, ''), T = String(o.ticker || '').toUpperCase();
    el.innerHTML = '<p class="muted">Reading the company’s outlook…</p>';
    if (!global.FFGuidance) await loadScript(`${hub}../guidance.js`);
    const G = global.FFGuidance || null;
    const [h, ol, comp] = await Promise.all([T ? getJSON(`${hub}data/holders/${encodeURIComponent(T)}.json`) : null, getJSON(`${hub}../data/outlook/${cik}.json`),
      o.company ? Promise.resolve(o.company) : getJSON(`${hub}../data/c/${cik}.json`)]);
    if ((o.here && !o.here()) || !el.isConnected) return;
    const docs = (ol && ol.docs) || [];
    const mdna = docs.filter((d) => d.kind === 'mdna'), rel = docs.filter((d) => d.kind === 'release');
    const merged = merge(h && h.guidance_history, ol);
    const rec = G && merged ? G.record(merged, comp || {}) : null;
    const hr = hitRate(rec);
    const g = h && h.guidance;
    const parts = [];
    const sum = [];
    if (hr) sum.push(`<div class="olv-kpi"><b class="${hr.rate >= 0.75 ? 'up' : hr.rate < 0.5 ? 'down' : ''}">${Math.round(100 * hr.rate)}%</b><span>guided periods met or beaten (${hr.hit} of ${hr.n})</span></div>`);
    if (g && g.label) sum.push(`<div class="olv-kpi"><b class="${/raised/.test(g.label) ? 'up' : /lowered|withdrawn/.test(g.label) ? 'down' : ''}">${esc(GUIDE[g.label] || g.label)}</b><span>latest guidance, ${esc(fdate(g.filed))}</span></div>`);
    if (mdna[0]) sum.push(`<div class="olv-kpi"><b>${(mdna[0].counts || {}).n || 0}</b><span>forward-looking statements in the ${esc(mdna[0].form)}${mdna[0].vs ? ` · ${(mdna[0].counts || {}).new || 0} new` : ''}</span></div>`);
    const ev = (h && h.events8k) || [];
    if (ev.length) sum.push(`<div class="olv-kpi"><b>${ev.length}</b><span>8-Ks in 120 days</span></div>`);
    parts.push(`<div class="olv-card"><h3>${esc((comp && comp.profile && comp.profile.name) || T)} <span class="muted">${esc(T)} · outlook & guidance</span></h3>
      ${sum.length ? `<div class="olv-kpis">${sum.join('')}</div>` : ''}
      <p class="muted">What the company says about the future, in its own words: the guidance of its earnings releases (8-K), how each guided period turned out, the forward-looking statements of its 10-Q / 10-K and releases, and its latest current reports. Read by fixed rules, no language model. ${hub ? `<a href="${hub}#guidance">Every company's hit rate →</a>` : ''}</p></div>`);
    parts.push(latestGuidance(g, G));
    if (rec && G && G.recordHTML) {
      const html = G.recordHTML(rec, esc);
      if (html) parts.push(`<div class="olv-card"><div class="guide-record">${html}</div>${merged.releases.some((r) => r.src) ? '<p class="muted">Includes figures guided in the 10-Q / 10-K MD&A for periods no earnings release guided.</p>' : ''}</div>`);
    }
    parts.push(flsCard(mdna[0], 'Forward-looking statements · MD&A', mdna));
    parts.push(flsCard(rel[0], 'Forward-looking statements · earnings release', rel));
    parts.push(events(ev));
    const body = parts.filter(Boolean);
    if (body.length === 1 && !g && !docs.length && !ev.length) {
      body.push('<div class="olv-card"><p class="muted">Nothing on file yet: no guidance in its earnings releases, no forward-looking statements read from its filings, no recent 8-Ks. Statements are read as each new 10-Q / 10-K is filed, and the older ones a few companies at a time.</p></div>');
    }
    el.innerHTML = `<div class="olv">${body.join('')}</div>`;
    bind(el);
  }

  const api = { render, merge, hitRate };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.OutlookView = api;
})(typeof window !== 'undefined' ? window : globalThis);
