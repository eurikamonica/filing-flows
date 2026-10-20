/* Follow feed (#feed): one timeline of everything disclosed about the companies a reader follows — new 10-Q / 10-K /
   8-K earnings filings on the site, material 8-Ks, insider trades (Form 4), officials' trades (House, Senate),
   13F quarters, Schedules 13D / 13G, Form 144 notices, news, Polymarket's earnings odds and new 52-week highs / lows.
   Signed-in readers see the tickers they follow (the same list their e-mail alerts use); anyone can type tickers,
   kept in this browser only. Sources: data/index.json, disclosures/data/holders/<TICKER>.json (the hub's per-ticker
   join), consensus/c/<cik>.json, market/extremes.json. Newest first; filters by type. */
(function (root) {
  'use strict';
  const U = root.FFUx;
  const { esc, t, fin, num, money, usd, pct, day, fileT } = U;
  const TYPES = [['filing', 'Earnings filings'], ['8k', '8-Ks'], ['insider', 'Insider trades'], ['official', "Officials' trades"], ['13f', '13F'],
    ['stake', '13D / 13G'], ['f144', 'Form 144'], ['news', 'News'], ['market', 'Polymarket'], ['extreme', '52-week highs / lows']];
  const MAX_TICKERS = 40;

  const norm = (x) => String(x || '').toUpperCase().replace(/[./\s]+/g, '-').replace(/[^A-Z0-9-]/g, '');
  const amount = (lo, hi) => (lo == null && hi == null ? 'amount not disclosed' : hi == null ? `over ${usd(lo - 1, 0)}` : `${usd(lo, 0)}–${usd(hi, 0)}`);

  // the events of one ticker from the hub's per-ticker file (and the site's index row)
  function events(T, H, siteRow, cons, ext) {
    const out = [], co = siteRow ? `#c-${siteRow.cik}` : `#t-${T}`;
    const add = (date, type, title, detail, href) => { if (date) out.push({ date: String(date).slice(0, 10), type, ticker: T, title, detail: detail || '', href: href || co }); };
    if (siteRow && siteRow.filed) add(siteRow.filed, 'filing', `${siteRow.form} ${U.dec(siteRow.label || '')} filed`, [siteRow.rev ? `revenue ${siteRow.rev}` : '', fin(siteRow.yoy) ? `${siteRow.yoy >= 0 ? '+' : '−'}${num(Math.abs(siteRow.yoy), 0)}% Y/Y` : ''].filter(Boolean).join(' · '), `#c-${siteRow.cik}-${siteRow.end}`);
    if (!H) return out;
    for (const e of H.events8k || []) add(e.filed, '8k', `8-K: ${e.label || (e.items || []).join(', ')}`, e.headline || e.quote || '', e.url);
    for (const x of H.insiders || []) add(x.date, 'insider', `${x.insider} (${x.title || x.role || 'insider'}) ${x.code === 'P' ? 'bought' : x.code === 'S' ? 'sold' : 'traded'} ${num(x.shares)} shares${fin(x.price) ? ` at ${usd(x.price)}` : ''}`,
      [fin(x.value) ? money(x.value) : '', x.plan_10b5_1 ? '10b5-1 plan' : ''].filter(Boolean).join(' · '), x.url);
    for (const o of H.officials || []) add(o.date, 'official', `${o.person} — ${o.transaction_type || o.kind || 'transaction'}`, [amount(o.amount_min, o.amount_max), o.jurisdiction, o.filed_date ? `reported ${day(o.filed_date)}` : ''].filter(Boolean).join(' · '), o.source_url);
    for (const s of H.stakes || []) add(s.filed, 'stake', `Schedule ${s.form}: ${s.holder || s.filer || 'a holder'} ${fin(s.percent) ? `holds ${num(s.percent, 1)}%` : ''}`.trim(), s.label || '', s.url);
    for (const f of H.form144 || []) add(f.filed, 'f144', `Form 144: ${f.seller_name || f.seller || 'an insider'} plans to sell ${num(f.shares)} shares`, [fin(f.value) ? `≈ ${money(f.value)}` : '', f.relationship || ''].filter(Boolean).join(' · '), f.url);
    for (const n of H.news || []) add(n.published, 'news', n.title || 'News', n.source || '', n.url);
    if (H.flows && (H.institutional || []).length) {
      const filed = (H.institutional || []).map((x) => x.filed || '').sort().pop();
      const f = H.flows;
      add(filed, '13f', `13F: ${num(f.buyers)} managers bought, ${num(f.sellers)} sold (${f.label || 'latest quarter'})`, [fin(f.new) ? `${num(f.new)} new positions` : '', fin(f.exits) ? `${num(f.exits)} exits` : '', fin(f.usd_net) ? `net ${f.usd_net >= 0 ? '+' : '−'}${money(Math.abs(f.usd_net))}` : ''].filter(Boolean).join(' · '), 'disclosures/#flows');
    }
    const beat = ((cons && cons.markets) || []).find((m) => m.kind === 'beat' && !m.closed && fin(m.p));
    if (beat) {
      const seen = U.store.get('pm:' + T, null), moved = seen && seen.p != null ? beat.p - seen.p : null;
      add(((cons.analysts || {}).as_of) || new Date().toISOString().slice(0, 10), 'market', `Polymarket: ${pct(beat.p)} chance ${T} beats EPS${fin(beat.eps_strike) ? ` of ${usd(beat.eps_strike)}` : ''}`,
        [beat.end ? `resolves ${day(beat.end)}` : '', moved != null && Math.abs(moved) >= 0.005 ? `${moved > 0 ? '+' : '−'}${num(Math.abs(moved) * 100, 0)} pts since your last visit` : ''].filter(Boolean).join(' · '), siteRow ? `#c-${siteRow.cik}-consensus` : 'disclosures/#consensus');
    }
    if (ext && ext.row) {
      const r = ext.row;
      if (r.new_hi) add(ext.asof, 'extreme', `New 52-week high${r.ath ? ' (and an all-time high)' : ''}`, `close ${usd(r.close)} · high ${usd(r.day_hi)}`);
      if (r.new_lo) add(ext.asof, 'extreme', `New 52-week low${r.atl ? ' (and an all-time low)' : ''}`, `close ${usd(r.close)} · low ${usd(r.day_lo)}`);
    }
    return out;
  }

  async function gather(tickers) {
    const ix = await U.site('index.json');
    const byT = new Map(((ix && ix.companies) || []).filter((c) => c.ticker).map((c) => [norm(c.ticker), c]));
    const X = await U.hub('market/extremes.json');
    const xrows = new Map();
    if (X && X.fields) for (const r of X.rows || []) xrows.set(norm(r[0]), Object.fromEntries(X.fields.map((f, i) => [f, r[i]])));
    const all = await Promise.all(tickers.slice(0, MAX_TICKERS).map(async (T) => {
      const row = byT.get(T);
      const [H, cons] = await Promise.all([U.hub(`holders/${encodeURIComponent(T)}.json`), row ? U.hub(`consensus/c/${+row.cik}.json`) : null]);
      return events(T, H, row, cons, xrows.has(T) ? { asof: X.asof, row: xrows.get(T) } : null);
    }));
    return all.flat().sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker));
  }

  function remember(list) {                                  // Polymarket odds seen: the next visit shows the move
    for (const e of list) if (e.type === 'market') { const m = /^Polymarket: (\d+)%/.exec(e.title); if (m) U.store.set('pm:' + e.ticker, { p: +m[1] / 100, at: e.date }); }
  }

  async function render(app, A) {
    const here = A && A.here ? A.here : () => true;
    if (A && A.setNav) A.setNav('feed');
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Follow feed</div><h1>Everything disclosed about the companies you follow</h1>
      <p class="muted" style="max-width:72ch">Earnings filings, 8-Ks, insider and officials' trades, 13F quarters, 13D / 13G stakes, Form 144 notices, news, Polymarket's earnings odds and new 52-week highs and lows — newest first, from the site and the Disclosure Hub.</p></div>
      <div class="fx-feed"><div class="fx-feed-who" id="fx-who"><span class="muted">Reading your follows…</span></div>
      <div class="fx-chips" role="group" aria-label="Show">${TYPES.map(([k, l]) => `<label class="pill fx-chip"><input type="checkbox" data-ft="${k}" checked> ${esc(l)}</label>`).join('')}</div>
      <ol class="fx-timeline" id="fx-list"><li class="muted">Loading…</li></ol></div>`;
    let follows = null;
    try { follows = A && A.loadFollows ? await A.loadFollows() : null; } catch (e) { follows = null; }
    if (!here()) return;
    const typed = U.store.get('feed:tickers', []);
    const fromAcct = (follows && follows.tickers || []).map(norm).filter(Boolean);
    let tickers = [...new Set(fromAcct.length ? fromAcct : typed)];
    const who = app.querySelector('#fx-who');
    const drawWho = () => {
      who.innerHTML = `${fromAcct.length ? `<span>The ${num(fromAcct.length)} tickers you follow${fromAcct.length > MAX_TICKERS ? ` (the first ${MAX_TICKERS})` : ''} · <a href="#account">change in Alerts</a></span>`
        : `<span>${follows && follows.signedIn ? 'You follow no tickers yet (Alerts → Follow).' : '<a href="#account">Sign in</a> to use the tickers you follow, or type some here (kept in this browser only):'}</span>
          <form class="fx-feed-form"><input class="input mono" id="fx-add" placeholder="e.g. NVDA, AAPL, CRWV" aria-label="Tickers to follow here" autocomplete="off"><button class="btn" type="submit">Add</button></form>`}
        <span class="fx-tks">${tickers.map((x) => `<span class="tag mono">${esc(x)}${fromAcct.length ? '' : ` <button type="button" class="fx-x" data-rm="${esc(x)}" aria-label="Remove ${esc(x)}">×</button>`}</span>`).join(' ')}</span>`;
      const f = who.querySelector('form');
      if (f) f.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const add = who.querySelector('#fx-add').value.split(/[\s,;]+/).map(norm).filter((x) => /^[A-Z][A-Z0-9-]{0,9}$/.test(x));
        tickers = [...new Set(tickers.concat(add))].slice(0, MAX_TICKERS);
        U.store.set('feed:tickers', tickers);
        drawWho(); refresh();
      });
      who.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => {
        tickers = tickers.filter((x) => x !== b.dataset.rm); U.store.set('feed:tickers', tickers); drawWho(); refresh();
      }));
    };
    const off = new Set(U.store.get('feed:off', []));
    app.querySelectorAll('[data-ft]').forEach((c) => { c.checked = !off.has(c.dataset.ft); c.addEventListener('change', () => { c.checked ? off.delete(c.dataset.ft) : off.add(c.dataset.ft); U.store.set('feed:off', [...off]); draw(); }); });
    let list = [];
    const ul = app.querySelector('#fx-list');
    const draw = () => {
      const show = list.filter((e) => !off.has(e.type)).slice(0, 300);
      const label = Object.fromEntries(TYPES);
      ul.innerHTML = show.length ? show.map((e) => `<li class="fx-ev fx-${e.type}"><time>${day(e.date)}</time><span class="tag mono">${esc(e.ticker)}</span><span class="fx-ty">${esc(label[e.type] || e.type)}</span>
          <a href="${esc(e.href)}"${/^https?:/.test(e.href) ? ' target="_blank" rel="noopener"' : ''}>${t(e.title)}</a>${e.detail ? `<small class="muted">${t(String(e.detail).slice(0, 220))}</small>` : ''}</li>`).join('')
        : `<li class="muted">${tickers.length ? 'Nothing disclosed for these tickers in the files on hand.' : 'Follow or add tickers to fill the feed.'}</li>`;
    };
    const refresh = async () => {
      ul.innerHTML = '<li class="muted">Loading…</li>';
      list = tickers.length ? await gather(tickers) : [];
      if (!here()) return;
      draw();
      remember(list);
    };
    drawWho();
    refresh();
  }
  root.FFFeed = { render, events, gather, TYPES };
  if (typeof module !== 'undefined') module.exports = root.FFFeed;
})(typeof globalThis !== 'undefined' ? globalThis : this);
