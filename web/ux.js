/* Filing Flows — shared helpers for the discovery & UX modules (search.js, overview.js, feed.js, charts.js, editor.js).
   No dependencies; window.FFUx. The modules read the site's own data (data/) and the Disclosure Hub's published files
   (disclosures/data/), and tolerate any of them being absent. */
(function (root) {
  'use strict';
  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = (s) => esc(dec(s));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  function money(v, cur) {
    if (!fin(v)) return '—';
    const c = cur == null ? '$' : cur, a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}${c}${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}${c}${(a / 1e9).toFixed(1)}B`;
    if (a >= 0.95e6) return `${s}${c}${(a / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `${s}${c}${(a / 1e3).toFixed(0)}K`;
    return `${s}${c}${a.toFixed(a >= 100 ? 0 : 2)}`;
  }
  const usd = (v, d = 2) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), d) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const day = (s) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
    return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }) : String(s || '');
  };
  const fileT = (tk) => String(tk || '').toUpperCase().replace(/\./g, '-');
  const SITE = root.FF_DATA || 'data/';
  const HUB = 'disclosures/data/';
  const memo = new Map();
  // a JSON file, fetched once per page load; null when it is missing or unreadable (never throws)
  function json(url) {
    if (!memo.has(url)) memo.set(url, fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return memo.get(url);
  }
  const site = (p) => json(SITE + p);
  const hub = (p) => json(HUB + p);
  const store = {
    get(k, d) { try { const v = localStorage.getItem('ffx:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ffx:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };
  function csvCell(v) {
    let s = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v == null ? '' : v);
    if (/^[=+@\t\r]/.test(s) || (/^-/.test(s) && !/^-\d+(\.\d+)?$/.test(s))) s = "'" + s;       // no spreadsheet formulas
    return '"' + s.replace(/"/g, '""') + '"';
  }
  // rows: array of objects (the union of keys is the header) → a CSV download
  function csv(rows, name) {
    if (!rows || !rows.length) return false;
    const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
    const text = '﻿' + [keys.map(csvCell).join(','), ...rows.map((r) => keys.map((k) => csvCell(r[k])).join(','))].join('\r\n');
    download(new Blob([text], { type: 'text/csv;charset=utf-8' }), name.endsWith('.csv') ? name : name + '.csv');
    return true;
  }
  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  // a categorical palette for series (colour-blind safe order); a series keeps its slot as others come and go
  const PALETTE = ['#2a78d6', '#d9822b', '#17734a', '#8a4fd6', '#c0392b', '#16a085', '#7a7974', '#b5446e'];
  // diluted weighted-average shares: the last fiscal year on file (Capital allocation data), else null
  function shares(c) {
    const R = (((c || {}).quality || {}).cap || {}).shares || [];
    for (let i = R.length - 1; i >= 0; i--) { const r = R[i]; const v = r.diluted || r.basic || r.out; if (fin(v) && v > 0) return { v: +v, label: r.label, basis: r.diluted ? 'diluted' : r.basic ? 'basic' : 'outstanding' }; }
    return null;
  }
  root.FFUx = { dec, esc, t, fin, num, money, usd, pct, spct, day, fileT, json, site, hub, store, csv, download, PALETTE, shares, HUB, SITE };
  if (typeof module !== 'undefined') module.exports = root.FFUx;
})(typeof globalThis !== 'undefined' ? globalThis : this);
