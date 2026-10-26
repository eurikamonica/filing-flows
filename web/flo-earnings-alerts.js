/* Flo: notify only on newly verified official IR calls, not SEC 8-K or link candidates.
   5-minute foreground check; works across the main site and the Disclosures hub.
   A first visit initializes a baseline, so historical backfills do not spam users.
*/
(function (root) {
  'use strict';
  const KEY = 'ff:earnings-calls-seen-v1';
  const MAIN = 'https://raw.githubusercontent.com/eurikamonica/filing-flows/main/disclosures/docs/data/earnings-calls/index.json';
  const LOCAL = new URL('disclosures/data/earnings-calls/index.json',
    (document.currentScript && document.currentScript.src || root.location.href).replace(/[^/]*$/, '')).href;
  let memorySeen = null;
  function verifiedRows(data) {
    return ((data && data.rows) || []).filter(r =>
      r && r.kind === 'official_ir_transcript' && r.transcript_status === 'verified_official_link' &&
      /^ir:[A-Z0-9.-]+:\d{4}-\d{2}-\d{2}$/.test(r.id || '') &&
      /^https:\/\//.test(r.ir_url || ''));
  }
  function decide(rows, prior, nowMs) {
    if (!prior) return [];
    const old = new Set(prior);
    return rows.filter(r => !old.has(r.id) &&
      Date.parse(r.verified_at || '') > nowMs - 14 * 86400000 &&
      Date.parse((r.date || '') + 'T00:00:00Z') > nowMs - 30 * 86400000);
  }
  function priorSeen() {
    try { return JSON.parse(root.localStorage.getItem(KEY) || 'null'); }
    catch (e) { return memorySeen; }
  }
  function remember(ids) {
    memorySeen = ids;
    try { root.localStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) {/* private mode */}
  }
  function toast(record) {
    if (document.getElementById('ff-earnings-toast')) return;
    const style = document.createElement('style');
    style.textContent = '#ff-earnings-toast{position:fixed;bottom:112px;right:18px;z-index:9030;' +
      'max-width:min(300px,calc(100vw - 36px));padding:12px 14px;background:var(--surface,#fff);' +
      'color:var(--ink,#222);border:2px solid var(--accent,#17734a);border-radius:14px;' +
      'box-shadow:0 8px 26px #0002;font:13px/1.45 inherit}' +
      '#ff-earnings-toast button,#ff-earnings-toast a{font:inherit;cursor:pointer;margin:5px 7px 0 0}' +
      '#ff-earnings-toast a{color:var(--accent,#17734a)}';
    document.head.appendChild(style);
    const n = document.createElement('aside');
    n.id = 'ff-earnings-toast'; n.setAttribute('role', 'status');
    const title = document.createElement('strong');
    title.textContent = 'Flo found a verified earnings call: ' + record.ticker;
    const detail = document.createElement('p');
    detail.textContent = record.date + ' · Management guidance and Q&A research available. Company-stated numbers may need SEC reconciliation.';
    const open = document.createElement('button');
    open.type = 'button'; open.textContent = 'Ask Flo';
    open.addEventListener('click', () => {root.FFMascot?.open(); n.remove();});
    const view = document.createElement('a');
    view.href = new URL('disclosures/#calls', root.location.origin + '/').href;
    view.textContent = 'Review source';
    const close = document.createElement('button');
    close.type = 'button'; close.textContent = 'Dismiss';
    close.setAttribute('aria-label','Dismiss earnings call alert');
    close.addEventListener('click', () => n.remove());
    n.append(title, detail, open, view, close);
    document.body.appendChild(n);
  }
  async function getIndex() {
    for (const url of [MAIN, LOCAL]) {
      try {
        const r = await fetch(url + (url.includes('?') ? '&' : '?') + 'v=' + Math.floor(Date.now() / 300000),
          {cache: 'no-store'});
        if (r.ok) return await r.json();
      } catch (e) { /* network fail: use the other published source */ }
    }
    return null;
  }
  let busy = false;
  async function poll() {
    if (busy || document.visibilityState === 'hidden') return;
    busy = true;
    try {
      const data = await getIndex();
      if (!data || (data.version || 0) < 2) return;
      const rows = verifiedRows(data), prior = priorSeen();
      // Keep latest history bounded. A new official source must have a new event ID.
      const ids = rows.map(x => x.id).slice(0, 300);
      const fresh = decide(rows, prior, Date.now());
      remember([...new Set([...ids, ...(prior || [])])].slice(0, 350));
      if (fresh.length) {
        const first = fresh[0];
        root.FFMascot?.notifyEarnings(first);
        toast(first);
      }
    } finally { busy = false; }
  }
  root.FFEarningsAlerts = {decide, verifiedRows, poll};
  function start() {
    poll().catch(() => {});
    root.setInterval(() => poll().catch(() => {}), 300000);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') poll().catch(() => {});
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})(typeof globalThis !== 'undefined' ? globalThis : this);
