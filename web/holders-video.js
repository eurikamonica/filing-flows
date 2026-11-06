/* Who holds a stock or an ETF, quarter by quarter: the largest 13F holders — fund families together (Vanguard's 2026
 * filers, BlackRock's new CIK of Q4 2024) — and their share of the company or the fund, from SEC's Form 13F data sets
 * since 2013 (disclosures/app/holders_history.py → the branch holders-history, read through the Hub's data/remote.json
 * "holders").
 * The share: a holder's reported 13F value ÷ the company's market value at that quarter-end (the site's month-by-month
 * market values, rank panel m-cap: the close as traded × the shares outstanding then, every share class), or ÷ an ETF's
 * net assets in its N-PORT report for that quarter (etf/weights/<SYM>.json, from Sep 2019). Without either, the share
 * of every share 13F managers reported (the institutions' holdings only, not the company).
 * Insiders (st.hi, on unless 'off'): officers, directors and 10% owners — Elon Musk at Tesla — from their own Forms 3, 4
 * and 5 (disclosures/app/insiders_history.py → i/<TICKER>.json beside c/): each one's shares at the quarter-end at the
 * quarter's 13F price, a holder beside the 13F managers (not with the share of 13F holdings, which is 13F's alone).
 * Styles: a bar race of the largest holders, their lines, the whole ownership as areas (the largest, the other 13F
 * holders, the other insiders and what neither reports: other individuals, managers under $100M, most of the world
 * outside the US), and the change from one quarter to the next in points.
 */
(function (root) {
  'use strict';
  const fin = (v) => v != null && Number.isFinite(+v);
  const norm = (s) => String(s || '').trim().toUpperCase().replace(/\./g, '-');
  const day = (d) => Date.parse(d + 'T00:00:00Z');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const qLabel = (d) => 'Q' + (Math.floor((+d.slice(5, 7) - 1) / 3) + 1) + ' ' + d.slice(0, 4);
  const pct = (v, dp) => (fin(v) ? (100 * v).toFixed(dp == null ? (Math.abs(v) < 0.01 ? 2 : 1) : dp) + '%' : '—');
  const pp = (v) => (fin(v) ? (v >= 0 ? '+' : '−') + Math.abs(100 * v).toFixed(2) + ' pp' : '—');
  const money = (v) => {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    return a >= 1e12 ? s + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? s + (a / 1e9).toFixed(a >= 1e11 ? 0 : 1) + 'B' : a >= 1e6 ? s + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M' : s + Math.round(a).toLocaleString('en-US');
  };
  const count = (v) => (fin(v) ? (Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : Math.round(v).toLocaleString('en-US')) : '—');
  const MEASURES = { pct: 'Share of the company or fund', share13: 'Share of all 13F holdings', usd: 'Value held' };

  // the files are read from the repository's branch (data/remote.json "holders"); a local build has them beside the Hub's
  async function base(api) {
    const cfg = await Promise.resolve(api.json(api.hub + 'remote.json')).catch(() => null);
    return cfg && typeof cfg.holders === 'string' && /^https:\/\//.test(cfg.holders) ? cfg.holders : api.hub + 'holders-history/';
  }
  // the month-end market value (dollars) of a company the site draws, by quarter-end: rank panel m-cap ($ millions)
  async function marketValues(sym, classes, api) {
    if (!api.rankMeta || !api.panel) return null;
    const meta = await Promise.resolve(api.rankMeta()).catch(() => null);
    if (!meta || !Array.isArray(meta.cos)) return null;
    const want = [sym].concat(classes || []).map(norm);
    const ci = meta.cos.findIndex((c) => want.includes(norm(c[0])));
    if (ci < 0) return null;
    const rows = await Promise.resolve(api.panel('m-cap')).catch(() => null), row = rows && rows[ci];
    if (!row || row.length < 2) return null;
    const m0 = meta._m0 || { y: +meta.months.start.slice(0, 4), m: +meta.months.start.slice(5, 7) - 1 };
    return { name: meta.cos[ci][1], sec: meta.cos[ci][2], at: (d) => {
      const i = (+d.slice(0, 4) - m0.y) * 12 + (+d.slice(5, 7) - 1) - m0.m, v = i >= row[0] && i < row[0] + row.length - 1 ? row[1 + i - row[0]] : null;
      return fin(v) && v > 0 ? v * 1e6 : null;
    } };
  }
  // an ETF's net assets at each quarter-end it reported (N-PORT, since Sep 2019)
  async function netAssets(sym, api) {
    const w = await Promise.resolve(api.json(api.hub + 'etf/weights/' + encodeURIComponent(sym) + '.json')).catch(() => null);
    const q = w && w.quarterly;
    if (!q || !Array.isArray(q.dates) || !Array.isArray(q.na)) return null;
    const m = new Map(q.dates.map((d, i) => [d, q.na[i]]).filter(([, v]) => fin(v) && v > 0));
    return m.size ? { name: w.name || sym, at: (d) => (m.has(d) ? +m.get(d) : null) } : null;
  }

  async function build(st, out, api) {
    const T = String(st.t || '').split(/[\s,;]+/).map(norm).filter(Boolean), sym = T[0];
    if (!sym) throw new Error('Type a ticker: a company (AAPL) or an ETF (SPY)');
    const B = await base(api);
    const doc = await Promise.resolve(api.json(B + 'c/' + encodeURIComponent(sym.replace(/[^A-Z0-9-]/g, '_')) + '.json')).catch(() => null);
    if (!doc || !Array.isArray(doc.periods) || !doc.periods.length) {
      const st2 = await Promise.resolve(api.json(B + 'status.json')).catch(() => null);
      throw new Error(st2 ? `No 13F holders on file for ${sym} (13F covers US-listed stocks and ETFs held by managers of $100M or more)` : 'The 13F holders history is still being built — try again in a few hours');
    }
    const P0 = doc.periods, who = (doc.who || []).slice();
    const lo = st.from || '', hi = st.to || '';
    const idx = P0.map((p, i) => i).filter((i) => (!lo || P0[i] >= lo) && (!hi || P0[i] <= hi) && doc.total[i]);
    if (!idx.length) throw new Error(`${sym}: no quarter on file between ${lo || 'the start'} and ${hi || 'now'} (on file: ${qLabel(P0[0])} → ${qLabel(P0[P0.length - 1])})`);
    // the denominator: the company's market value, or the fund's net assets
    const [mv, na] = await Promise.all([marketValues(sym, doc.classes, api), netAssets(sym, api)]);
    const den = mv ? { kind: 'company', ...mv } : na ? { kind: 'fund', ...na } : null;
    let hm = st.hm in MEASURES ? st.hm : 'pct';
    const denOk = den ? idx.filter((i) => fin(den.at(P0[i]))) : [];
    let use = idx;
    if (hm === 'pct') {
      if (!den || denOk.length < Math.min(2, idx.length)) {
        hm = 'share13';
        out.notes.add(den ? `${sym}: its ${den.kind === 'fund' ? 'net assets' : 'market value'} is on file for too few of these quarters — shown as the share of all 13F holdings instead.`
          : `${sym}: the site has no market value or fund net assets for it — shown as each holder's share of all the shares 13F managers reported, not of the company.`);
      } else if (denOk.length < idx.length) {
        use = denOk;
        out.notes.add(`${den.kind === 'fund' ? 'Net assets (SEC N-PORT) are on file from ' : 'Market values are on file from '}${qLabel(P0[denOk[0]])}${denOk[denOk.length - 1] !== idx[idx.length - 1] ? ' to ' + qLabel(P0[denOk[denOk.length - 1]]) : ''}: the quarters without one are left out (13F holders on file from ${qLabel(P0[idx[0]])}).`);
      }
    }
    const P = use.map((i) => P0[i]), L = P.length - 1;
    const tot = use.map((i) => doc.total[i]);
    const denom = use.map((i, j) => (hm === 'pct' ? den.at(P0[i]) : hm === 'share13' ? tot[j][1] : 1));
    const val = (row, j) => (!row ? null : hm === 'pct' ? row[2] / denom[j] : hm === 'share13' ? (denom[j] > 0 ? row[1] / denom[j] : null) : row[2]);
    // each holder's value in each quarter (null: not among the largest that quarter)
    const ser = new Map();
    const put = (w, j, sh, usd) => {
      let s = ser.get(w);
      if (!s) { s = { w, v: P.map(() => null), sh: P.map(() => null), usd: P.map(() => null) }; ser.set(w, s); }
      s.v[j] = val([w, sh, usd], j); s.sh[j] = sh; s.usd[j] = usd;
    };
    use.forEach((i, j) => (doc.top[i] || []).forEach(([w, sh, usd]) => put(w, j, sh, usd)));
    // insiders (Forms 3/4/5): holders beside the 13F managers, by the same quarters; their keys 'i:<CIK>'
    const ins = st.hi !== 'off' && hm !== 'share13' ? await Promise.resolve(api.json(B + 'i/' + encodeURIComponent(sym.replace(/[^A-Z0-9-]/g, '_')) + '.json')).catch(() => null) : null;
    const insTot = P.map(() => 0);
    let insN = 0;
    if (ins && Array.isArray(ins.periods) && Array.isArray(ins.who)) {
      const at = new Map(ins.periods.map((p, k) => [p, k])), base0 = who.length;
      ins.who.forEach(([cik, name, role]) => who.push(['i:' + cik, name + (role ? ' — ' + role : ''), name, [cik], role, true]));
      P.forEach((p, j) => {
        const k = at.get(p);
        if (k == null) return;
        (ins.top[k] || []).forEach(([w, sh, usd]) => put(base0 + w, j, sh, usd));
        const t = ins.total[k];
        if (t) { insTot[j] = val([0, t[1], t[2]], j) || 0; insN = Math.max(insN, t[0]); }
      });
    }
    const insider = (s) => !!(who[s.w] || [])[5];
    const n = Math.max(3, Math.min(20, +st.hn || 10));
    const peak = (s) => Math.max(...s.v.filter(fin).map(Math.abs), 0);
    const all = [...ser.values()].sort((a, b) => peak(b) - peak(a));
    all.forEach((s, k) => { s.pal = k; });                     // one colour a holder, whatever the style
    const label = (s) => (who[s.w] || [])[2] || (who[s.w] || [])[1] || 'Holder';
    const nameOf = (s) => {
      const x = who[s.w] || [];
      return (x[1] || '') + (x[0] && x[0].startsWith('f:') ? ' (its filers together)' : x[5] ? ' (insider: Forms 3/4/5)' : '');
    };
    const company = (den && den.name) || doc.name || sym, isFund = den ? den.kind === 'fund' : !mv && !!na;
    const subject = isFund || !den ? sym : company.replace(/,? (INC|CORP|CORPORATION|LTD|PLC|CO)\.?$/i, '').replace(/\.$/, ''), title = `Who owns ${subject}`;
    const metric = hm === 'pct' ? (isFund ? `Share of ${sym}'s net assets` : `Share of ${subject}`) : hm === 'share13' ? 'Share of all 13F holdings' : 'Value held (13F)';
    out.kind = 'holders'; out.grid = P.map(day); out.quarterly = true; out.unit = hm === 'usd' ? '$' : '%';
    out.fmt = hm === 'usd' ? money : (v) => pct(v); out.metric = metric; out.noLegend = true;
    out.title = title;
    const span = `${qLabel(P[0])} → ${qLabel(P[L])}`, what = hm === 'pct' ? (isFund ? '13F value ÷ the fund\'s net assets' : '13F value ÷ market value') : hm === 'share13' ? 'of every share 13F managers reported' : 'reported 13F value';
    const withIns = insN > 0;
    out.sub = `${span} · the largest ${withIns ? '13F holders and insiders' : '13F holders'}, fund families together · ${what} · SEC Form 13F${withIns ? ', Forms 3/4/5' : ''}`;
    out.foot = `13F holdings at each quarter-end · ${hm === 'pct' ? what : hm === 'share13' ? 'share of the institutions\' 13F shares' : 'reported value'} · fund families together`;
    const style = st.style;
    if (style === 'stack') {
      const top = all.slice(0, n), sumOf = (f) => P.map((_, j) => top.filter(f).reduce((a, s) => a + (fin(s.v[j]) ? s.v[j] : 0), 0));
      const sum = sumOf((s) => !insider(s)), sumI = sumOf(insider);
      const inst = P.map((_, j) => val(tot[j], j));
      out.series = top.map((s) => ({ key: who[s.w][0], label: label(s), name: nameOf(s), pal: s.pal, v: s.v.map((x) => (fin(x) ? x : 0)) }));
      out.series.push({ key: 'other', label: 'Other 13F holders', name: 'every other 13F manager', sec: 'other', v: P.map((_, j) => Math.max(0, (inst[j] || 0) - sum[j])) });
      const otherI = P.map((_, j) => Math.max(0, insTot[j] - sumI[j]));
      if (withIns && otherI.some((x) => x > 1e-6)) out.series.push({ key: 'insiders', label: 'Other insiders', name: 'every other officer, director and 10% owner (Forms 3/4/5)', col: '#8a7a5c', v: otherI });
      if (hm === 'pct') {
        let over = 0;
        const both = P.map((_, j) => (inst[j] || 0) + insTot[j]);
        const rest = both.map((x) => { over = Math.max(over, x); return Math.max(0, 1 - x); });
        out.series.push({ key: 'rest', label: withIns ? 'Not reported' : 'Not in 13F reports', name: withIns ? 'other individuals, smaller and non-US managers' : 'individuals, insiders, smaller and non-US managers', col: '#5c6675', v: rest });
        if (over > 1.001) {
          out.series.forEach((s) => { s.v = s.v.map((x, j) => (both[j] > 1 ? x / both[j] : x)); });
          out.notes.add(`${withIns ? '13F holdings and insiders\' shares' : '13F holdings'} add up to more than all of ${subject} in some quarters (up to ${pct(over)}: shares lent and borrowed are reported by both sides, and some managers report what they advise on): scaled to 100% there.`);
        }
      }
      out.kind = 'sectors'; out.stack = { share: hm !== 'usd', total: P.map((_, j) => (hm === 'usd' ? tot[j][2] + (withIns ? (insTot[j] || 0) : 0) : 1)) };
      out.notes.add(hm === 'pct' ? `Areas: the largest holders, every other 13F manager${withIns ? ', every other insider' : ''}, and what ${withIns ? 'neither reports — other individuals' : 'no 13F reports — individuals and insiders'}, managers with less than $100M in 13F securities, and most managers outside the US.` : `Areas: the largest holders${withIns ? ', every other insider' : ''} and every other 13F manager.`);
    } else if (style === 'line') {
      out.series = all.slice(0, n).map((s) => ({ key: who[s.w][0], label: label(s), name: nameOf(s), pal: s.pal, v: s.v }));
      out.palIdx = true;
    } else if (style === 'changes') {
      if (P.length < 2) throw new Error(`${sym}: one quarter only in this range — choose a wider one for the changes`);
      out.series = all.map((s) => ({ key: who[s.w][0], label: label(s), name: nameOf(s), pal: s.pal, v: s.v.slice(1).map((x, j) => (fin(x) && fin(s.v[j]) ? x - s.v[j] : null)) }));
      out.grid = out.grid.slice(1); out.kind = 'rank'; out.rankN = n; out.order = 'abs';
      out.fmt = hm === 'usd' ? (v) => (v >= 0 ? '+' : '−') + money(Math.abs(v)) : pp; out.metric = metric + ', change on the quarter before';
      out.notes.add('Changes: each holder against its own figure the quarter before, among the largest holders in both. A share moves with the price as well as with buying and selling.');
    } else {
      out.series = all.map((s) => ({ key: who[s.w][0], label: label(s), name: nameOf(s), pal: s.pal, v: s.v }));
      out.kind = 'rank'; out.rankN = n; out.order = 'desc';
    }
    // the results table: the holders of the last quarter, their share then and at the start, shares and value
    const ref = all.filter((s) => fin(s.v[L])).sort((a, b) => b.v[L] - a.v[L]).slice(0, n);
    out.holders = {
      sym, metric, first: P[0], last: P[L], measure: hm, kind: den ? den.kind : null,
      rows: ref.map((s) => { const j0 = s.v.findIndex(fin); return { key: who[s.w][0], label: label(s), name: nameOf(s), pal: s.pal, v0: s.v[j0], q0: P[j0], v: s.v[L], sh: s.sh[L], usd: s.usd[L], filers: (who[s.w] || [])[3] || [] }; }),
      inst: { v0: val(tot[0], 0), v: val(tot[L], L), holders0: tot[0][0], holders: tot[L][0], usd: tot[L][2] },
      filers: use.map((i) => (doc.filers || [])[i]),
    };
    // notes: the source, the families met here, the quarters still open, what 13F leaves out
    out.notes.add(`SEC Form 13F data sets: every 13F filed since May 2013 — what each manager with $100M or more in US-listed stocks and ETFs held at each quarter-end, filed within 45 days. ${span}.`);
    const fams = [...ser.values()].sort((a, b) => peak(b) - peak(a)).map((s) => who[s.w]).filter((x) => x && x[0].startsWith('f:'));
    if (fams.length) out.notes.add('Fund families as one holder, whichever of their companies filed: ' + fams.slice(0, 5).map((x) => x[1]).join(', ') + ' — BlackRock reported through its trust company, fund advisors and other arms until 2016, under a new CIK from Q4 2024; Vanguard through Vanguard Capital Management and Vanguard Portfolio Management from 2026.');
    if ((doc.classes || []).length > 1) out.notes.add(`${doc.classes.join(' and ')} together: every share class of the company (holders of both count once each class).`);
    const open = (doc.open || []).filter((p) => P.includes(p));
    if (open.length) out.notes.add(`${open.map(qLabel).join(', ')}: late amendments can still change ${open.length > 1 ? 'these quarters' : 'this quarter'} a little.`);
    const f = out.holders.filers.filter(fin);
    if (f.length > 1 && f[0] < 0.75 * Math.max(...f)) out.notes.add(`13F filers on file: ${f[0].toLocaleString('en-US')} in ${qLabel(P[0])}, ${f[f.length - 1].toLocaleString('en-US')} in ${qLabel(P[L])} — more managers crossed $100M over the years.`);
    if (hm === 'pct') out.notes.add(isFund ? `A holder's share of ${sym}: its reported 13F value ÷ the fund's net assets in its N-PORT report for the quarter.` : `A holder's share of ${subject}: its reported 13F value ÷ the company's market value at the quarter-end (the close × the shares outstanding then, every share class).`);
    out.notes.add('13F lists long positions in US-listed stocks and ETFs; options, short positions and holdings under $100M managers are not in it. A manager reports what it has discretion over, for its funds and its clients.');
    if (withIns) out.notes.add(`Insiders — officers, directors and 10% owners (${insN.toLocaleString('en-US')} at most in a quarter) — from their own Forms 3, 4 and 5 (SEC's insider transactions data sets): the shares each held after their last report on or before the quarter-end, directly and through trusts or companies (options and units left out), at the quarter's 13F price; a holding not reported again for two years is left out. A block a 13F manager also reports counts once, in 13F (Berkshire's shares in Warren Buffett's own Form 4), and one family company's shares once.`);
    else if (st.hi === 'off' && hm !== 'share13') out.notes.add('Insiders left out (Forms 3/4/5): 13F managers only.');
    out.notes.add(`Each quarter names its 20 largest holders; the rest${style === 'stack' ? ' are in Other 13F holders' : ' are not drawn that quarter'}.`);
    return out;
  }

  // the results table under the video (studio.js reportOf): the holders at the end, their share at the start and now
  function report(V, cell) {
    const H = V.holders, hm = H.measure, f = hm === 'usd' ? money : (v) => pct(v);
    const ch = (a, b) => (fin(a) && fin(b) ? (hm === 'usd' ? (b - a >= 0 ? '+' : '−') + money(Math.abs(b - a)) : pp(b - a)) : '');
    const cols = [['v0', qLabel(H.first), 'At the start (or its first quarter among the largest)'], ['v', qLabel(H.last), V.metric], ['chg', 'Change', hm === 'usd' ? 'In dollars' : 'In percentage points'],
      ['sh', 'Shares', 'Reported at ' + qLabel(H.last)], ['usd', 'Value', 'Reported 13F value at ' + qLabel(H.last)]];
    const rows = H.rows.map((r) => ({ k: r.pal, label: r.label, name: r.name, cells: {
      v0: cell(f(r.v0), r.q0 !== H.first ? 'from ' + qLabel(r.q0) : '', r.v0), v: cell(f(r.v), '', r.v), chg: cell(ch(r.v0, r.v), '', fin(r.v0) && fin(r.v) ? r.v - r.v0 : null),
      sh: cell(count(r.sh), '', r.sh), usd: cell(money(r.usd), r.key.startsWith('f:') ? 'fund family' : r.key.startsWith('i:') ? 'insider: Forms 3/4/5' : '', r.usd) } }));
    const I = H.inst;
    rows.push({ k: 0, label: 'Every 13F holder', strong: true, sec: 'other', cells: { v0: cell(f(I.v0), I.holders0.toLocaleString('en-US') + ' managers', I.v0), v: cell(f(I.v), I.holders.toLocaleString('en-US') + ' managers', I.v),
      chg: cell(ch(I.v0, I.v), '', fin(I.v0) && fin(I.v) ? I.v - I.v0 : null), sh: cell(''), usd: cell(money(I.usd), '', I.usd) } });
    return { cols, rows, foot: 'From SEC Form 13F data sets: each manager\'s holdings at the quarter-end as it reported them; fund families together. Insiders from their Forms 3, 4 and 5, at the quarter\'s 13F price. ' + (hm === 'pct' ? (H.kind === 'fund' ? 'Share: 13F value ÷ the fund\'s net assets (N-PORT).' : 'Share: 13F value ÷ the company\'s market value at the quarter-end.') : hm === 'share13' ? 'Share: of every share 13F managers reported.' : '') };
  }
  // the end card of the lines: each holder's share now and the change since the start
  function final(V) {
    const L = V.grid.length - 1, H = V.holders, hm = H.measure;
    V.final = V.series.map((s, k) => ({ s, k, v: s.v[L], v0: s.v.find(fin) })).filter((r) => fin(r.v)).sort((a, b) => b.v - a.v).slice(0, 8)
      .map((r, i) => ({ k: r.s.pal, label: `${i + 1}. ${r.s.label}`, value: V.fmt(r.v), change: fin(r.v0) ? (hm === 'usd' ? (r.v - r.v0 >= 0 ? '+' : '−') + money(Math.abs(r.v - r.v0)) : pp(r.v - r.v0)) : '', up: r.v >= (r.v0 || 0), v: r.v }));
    V.endTitle = `${V.metric} · ${qLabel(H.last)}`; V.endSub = `change since ${qLabel(H.first)}`;
    V.caption = `${V.title} (${qLabel(H.last)}): ` + V.final.map((r) => `${r.label} ${r.value}${r.change ? ' (' + r.change + ')' : ''}`).join(' · ');
  }
  root.FFHoldersVideo = { build, report, final, base, MEASURES, qLabel };
  if (typeof module !== 'undefined') module.exports = root.FFHoldersVideo;
})(typeof globalThis !== 'undefined' ? globalThis : this);
