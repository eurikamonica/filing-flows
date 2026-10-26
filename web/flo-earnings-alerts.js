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
