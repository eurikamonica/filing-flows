/* Prospectus reader: a registration statement's own words, read by pipeline/ipo_reader.py — the contents with a link
   into the SEC copy for every section, each section's opening text and headings, the risk factors (the summary's
   bullets and every risk heading by category, filterable), the notes to the financial statements, the principal
   stockholders table and the share-class rights. Text is cut from the document, never rewritten. */
(function (root) {
  'use strict';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function sec(url) {
    try { const u = new URL(url); return u.protocol === 'https:' && u.hostname === 'www.sec.gov' && !u.username && !u.password ? u.href.split('#')[0] : ''; } catch (_) { return ''; }
  }
  const at = (url, anchor) => (url && anchor && /^[\w.:-]{1,120}$/.test(anchor) ? `${url}#${anchor}` : url);
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

  // a table as the reader keeps it: a cell is its text, or [text, columns] when it spans columns
  const txt = (c) => (Array.isArray(c) ? String(c[0] ?? '') : String(c ?? ''));
  const span = (c) => (Array.isArray(c) ? Math.max(1, Math.min(40, +c[1] || 1)) : 1);
  const numeric = (t) => /^[\d,.$()%*†‡—–-]+$/.test(t.replace(/\s+/g, ''));
  function table(rows) {
    if (!rows || !rows.length) return '';
    const width = Math.max(...rows.map((r) => r.reduce((a, c) => a + span(c), 0)));
    let h = 0;                                   // heading rows: the first few, words only, at least two cells filled
    while (h < Math.min(3, rows.length - 1) && rows[h].filter((c) => txt(c)).length >= 2 && !rows[h].some((c) => txt(c) && numeric(txt(c)) && txt(c).length > 2)) h++;
    const cell = (c, tag, i) => `<${tag}${span(c) > 1 ? ` colspan="${span(c)}"` : ''}${i && tag === 'td' && numeric(txt(c)) ? ' class="num"' : ''}>${esc(txt(c))}</${tag}>`;
    const group = (r) => r.filter((c) => txt(c)).length === 1 && txt(r[0]) && !numeric(txt(r[0]));
    return `<div class="qi-table ipo-rtable"><table>${h ? `<thead>${rows.slice(0, h).map((r) => `<tr>${r.map((c) => cell(c, 'th')).join('')}</tr>`).join('')}</thead>` : ''}
      <tbody>${rows.slice(h).map((r) => (group(r) ? `<tr class="ipo-rgroup"><td colspan="${width}">${esc(txt(r[0]))}</td></tr>`
        : `<tr>${r.map((c, i) => cell(c, 'td', i)).join('')}</tr>`)).join('')}</tbody></table></div>`;
  }

  function sectionView(s, url) {
    const link = url ? `<a href="${esc(at(url, s.anchor))}" target="_blank" rel="noopener noreferrer">Open in the SEC copy ↗</a>` : '';
    const more = s.words > 400 ? `<p class="muted ipo-cut">The opening of a ${s.words.toLocaleString('en-US')}-word section. ${link ? 'The rest is in the SEC copy.' : ''}</p>` : '';
    return `<header><h3>${esc(s.title)}</h3><p class="muted">${s.page ? `Page ${esc(s.page)} · ` : ''}${plural(s.words || 0, 'word')}${link ? ` · ${link}` : ''}</p></header>
      ${(s.text || []).map((t) => `<p${/^• /.test(t) ? ' class="ipo-bullet"' : ''}>${esc(t.replace(/^• /, ''))}</p>`).join('') || '<p class="muted">This section is a table or a heading only.</p>'}
      ${more}
      ${(s.heads || []).length ? `<h4>In this section</h4><ul class="ipo-heads">${s.heads.map((h) => `<li>${esc(h)}</li>`).join('')}</ul>` : ''}`;
  }

  function render(host, r, opts) {
    opts = opts || {};
    const url = sec(r.url || opts.url);
    const risks = r.risks || {}, groups = risks.groups || [], notes = r.notes || [];
    const tabs = [['sections', `Contents · ${r.sections.length}`]];
    if (groups.length || (risks.summary || []).length) tabs.push(['risks', `Risk factors · ${risks.count || (risks.summary || []).length}`]);
    if (notes.length) tabs.push(['notes', `Notes to the financials · ${notes.length}`]);
    if ((r.holders || []).length) tabs.push(['owners', 'Ownership']);
    if ((r.classes || []).length) tabs.push(['classes', 'Share classes']);
    const form = esc(r.form || opts.form || 'prospectus');
    host.innerHTML = `<div class="ipo-rhead"><h2 id="ipo-read-h">Read the prospectus</h2>
        <p class="muted">The ${form}’s own words: its contents, risk factors and notes, cut from the document and never rewritten.${url ? ` Each section links to the same place in the <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">SEC copy ↗</a>.` : ''}</p></div>
      <div class="ipo-rtabs" role="tablist" aria-label="Prospectus parts">${tabs.map(([k, l], i) => `<button type="button" role="tab" id="ipo-rt-${k}" aria-controls="ipo-rp-${k}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}" data-rtab="${k}">${esc(l)}</button>`).join('')}</div>
      <div class="ipo-rpanel ipo-rsec" role="tabpanel" id="ipo-rp-sections" aria-labelledby="ipo-rt-sections">
        <label class="ipo-rpick">Section <select aria-label="Prospectus section">${r.sections.map((s, i) => `<option value="${i}">${esc(s.title)}</option>`).join('')}</select></label>
        <ol class="ipo-toc">${r.sections.map((s, i) => `<li><button type="button" data-sec="${i}" aria-current="${i === 0}"><span>${esc(s.title)}</span><small>${s.page ? esc(s.page) : ''}</small></button></li>`).join('')}</ol>
        <article class="ipo-sec" aria-live="polite"></article>
      </div>
      ${tabs.some(([k]) => k === 'risks') ? `<div class="ipo-rpanel" role="tabpanel" id="ipo-rp-risks" aria-labelledby="ipo-rt-risks" hidden>
        ${(risks.summary || []).length ? `<h3>In brief</h3><p class="muted">The summary of risk factors at the front of the prospectus.</p><ul class="ipo-rsum">${risks.summary.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}
        ${groups.length ? `<div class="ipo-rfilter"><h3>Every risk factor, by category</h3><label>Filter <input type="search" data-rfilter placeholder="e.g. compute, export, dual class" autocomplete="off"></label><span class="muted" data-rcount></span></div>
        ${groups.map((g, gi) => `<details class="ipo-rgrp"${gi === 0 ? ' open' : ''}><summary><span>${esc(g.group)}</span><small>${g.items.length}</small></summary><ol>${g.items.map((t) => `<li>${esc(t)}</li>`).join('')}</ol></details>`).join('')}
        <p class="muted">The headings of the risk factors; the explanation under each is in the ${url ? `<a href="${esc(at(url, (r.sections.find((s) => /^risk factors/i.test(s.title)) || {}).anchor))}" target="_blank" rel="noopener noreferrer">SEC copy ↗</a>` : 'document'}.</p>` : ''}
      </div>` : ''}
      ${notes.length ? `<div class="ipo-rpanel" role="tabpanel" id="ipo-rp-notes" aria-labelledby="ipo-rt-notes" hidden>
        <p class="muted">The notes to the audited financial statements, in order: what each note covers and how it begins.</p>
        ${notes.map((n) => `<details class="ipo-note"><summary><span class="ipo-nn">Note ${esc(n.n)}</span><span>${esc(n.title)}</span>${(n.topics || []).length ? `<small>${plural(n.topics.length, 'topic')}</small>` : ''}</summary>
          ${(n.topics || []).length ? `<ul class="ipo-chips">${n.topics.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}
          ${(n.text || []).map((t) => `<p>${esc(t)}</p>`).join('') || '<p class="muted">This note opens with a table.</p>'}</details>`).join('')}
      </div>` : ''}
      ${(r.holders || []).length ? `<div class="ipo-rpanel" role="tabpanel" id="ipo-rp-owners" aria-labelledby="ipo-rt-owners" hidden>
        <p class="muted">The principal stockholders table as printed: who owns the shares before and after the offering.</p>${table(r.holders)}</div>` : ''}
      ${(r.classes || []).length ? `<div class="ipo-rpanel" role="tabpanel" id="ipo-rp-classes" aria-labelledby="ipo-rt-classes" hidden>
        <p class="muted">The share classes and their votes, from the description of capital stock.</p>${table(r.classes)}</div>` : ''}`;

    const article = host.querySelector('.ipo-sec'), pick = host.querySelector('.ipo-rpick select');
    const show = (i) => {
      article.innerHTML = sectionView(r.sections[i], url);
      host.querySelectorAll('[data-sec]').forEach((b) => b.setAttribute('aria-current', String(+b.dataset.sec === i)));
      pick.value = String(i);
    };
    host.querySelectorAll('[data-sec]').forEach((b) => b.addEventListener('click', () => { show(+b.dataset.sec); if (opts.onSection) opts.onSection(+b.dataset.sec); }));
    pick.addEventListener('change', () => show(+pick.value));
    const first = r.sections.findIndex((s) => /prospectus summary|^summary/i.test(s.title));
    show(first >= 0 ? first : 0);

    const tabBtns = [...host.querySelectorAll('[data-rtab]')];
    const select = (b, focus) => {
      tabBtns.forEach((x) => { const on = x === b; x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; host.querySelector('#ipo-rp-' + x.dataset.rtab).hidden = !on; });
      if (focus) b.focus();
    };
    tabBtns.forEach((b, i) => {
      b.addEventListener('click', () => select(b));
      b.addEventListener('keydown', (e) => {                          // arrow keys move between tabs
        const k = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (k) { e.preventDefault(); select(tabBtns[(i + k + tabBtns.length) % tabBtns.length], true); }
      });
    });

    const filter = host.querySelector('[data-rfilter]');
    if (filter) {
      const count = host.querySelector('[data-rcount]');
      const run = () => {
        const words = filter.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
        let shown = 0;
        host.querySelectorAll('.ipo-rgrp').forEach((g) => {
          let n = 0;
          g.querySelectorAll('li').forEach((li) => {
            const ok = !words.length || words.every((w) => li.textContent.toLowerCase().includes(w));
            li.hidden = !ok; if (ok) n++;
          });
          g.hidden = !n; if (words.length && n) g.open = true;
          g.querySelector('small').textContent = words.length ? `${n} of ${g.querySelectorAll('li').length}` : String(n);
          shown += n;
        });
        count.textContent = words.length ? `${plural(shown, 'risk factor')} match` : '';
      };
      filter.addEventListener('input', run);
    }
  }

  // the cover facts as short chips: the proposed ticker, the exchange, the price range and the issuer's status
  function chips(cover) {
    const c = cover || {}, out = [];
    if (c.symbol) out.push(`<li class="ipo-sym"><b>${esc(c.symbol)}</b> proposed ticker</li>`);
    if (c.exchange) out.push(`<li>${esc(c.exchange)}</li>`);
    const usd = (v) => '$' + Number(v).toFixed(2);
    if (Array.isArray(c.range) && c.range.length === 2 && c.range.every(Number.isFinite)) out.push(`<li>${usd(c.range[0])}–${usd(c.range[1])} per share</li>`);
    if (Number.isFinite(c.shares)) out.push(`<li>${c.shares.toLocaleString('en-US')} shares offered</li>`);
    const words = { 'emerging growth company': 'Emerging growth company', 'public benefit corporation': 'Public benefit corporation',
      'controlled company': 'Controlled company', 'multiple share classes': 'Multiple share classes', 'blank check company (SPAC)': 'Blank check company (SPAC)' };
    (c.flags || []).forEach((f) => out.push(`<li>${esc(words[f] || f)}</li>`));
    return out.length ? `<ul class="ipo-chips ipo-cover">${out.join('')}</ul>` : '';
  }

  root.FFIPOReader = { render, chips, _t: { table, sectionView, at, sec } };
})(typeof window !== 'undefined' ? window : globalThis);
