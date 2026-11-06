/* Highs, lows & ranges — how long an asset's regime lasts and what follows it, built with the move odds after every US
   close (data/research/paths/moves/: highs.json from app/highs.py, lows.json and ranges.json from app/regimes.py, and
   each asset's blocks in a/<KEY>.json → highs, lows, ranges).
   At the highs: how long runs of new all-time highs last and how deep the pullback is that ends them.
   At the lows (an all-time, a 52-week or a 3-month low): how long until the next new low, the rebound and how far.
   In a range (sideways for 3 months, narrow or wide): how long until the breakout, which way, and whether it holds.
   One asset (the company page's tab and the hub's Move odds → Highs, lows & ranges): where it stands, its state (each
   variable against its own history where marked), what followed the most similar days of the same kind of asset, and
   for the highs its own past runs; the spread of what followed (the fan of the return over the next year, the histograms
   of the returns 1, 3 and 12 months on and of the regime's own falls and rises, against every day of the regime), the
   odds given each of its conditions alone and all together, and the walk-forward test of the similar-days odds
   (app/regime_odds.py: Brier skill, AUC, calibration, the top − bottom fifth, by year). The hub adds every asset in the
   regime now, the spread and the test of every day, and the research tables by each state variable. Descriptive
   history, not a forecast.
   window.HighsView = {render(el, {ticker | key, hub, regime}), hub(doc, opts), lowsHub(doc, reg, opts), rangesHub(…), …}. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const sp = (v, d = 1) => { if (!fin(v)) return '—'; const a = Math.abs(100 * v); return (Number(a.toFixed(d)) === 0 ? '' : v > 0 ? '+' : '−') + num(a, d) + '%'; };
  const money = (v, lvl) => (fin(v) ? (lvl ? '' : '$') + num(v, v >= 1000 ? 0 : 2) : '—');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mdy = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? `${MON[+m[2] - 1]} ${+m[3]}, ${m[1]}` : String(s || ''); };
  const md = (s) => mdy(s).replace(/, \d{4}$/, '');
  const ord = (p) => { if (!fin(p)) return '—'; if (p < 0.5) return 'lowest'; const n = Math.round(p); const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th'; return n + s; };
  const td = (n) => (fin(n) ? `${num(n)} trading day${+n === 1 ? '' : 's'}` : '—');
  const GROUP = { companies: 'companies', funds: 'ETFs', indices: 'indices' };
  const HZW = { 21: '1 month', 63: '3 months', 126: '6 months', 252: '12 months' };
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete store[u]; throw e; }));

  function css() {
    if (typeof document === 'undefined' || document.getElementById('hv-css')) return;
    const s = document.createElement('style');
    s.id = 'hv-css';
    s.textContent = `.hv{max-width:1100px}.hv-head{font-size:16px;line-height:1.55;margin:4px 0 10px}.hv-sub{font-size:12.5px;color:var(--muted,#777);line-height:1.55;max-width:900px}
.hv-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin:8px 0 14px}.hv-tile{border:1px solid var(--line,#ddd);border-radius:12px;padding:9px 11px;background:var(--surface,#fff)}
.hv-tile small{display:block;font-size:11.5px;color:var(--muted,#777)}.hv-tile b{display:block;font-size:19px;font-variant-numeric:tabular-nums;margin:2px 0}.hv-tile i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.hv-meter{height:6px;border-radius:3px;background:var(--line,#e5e5e5);position:relative;margin:6px 0 2px;overflow:hidden}.hv-meter span{position:absolute;top:0;bottom:0;left:0;border-radius:3px;background:var(--q-warm,#d9822b)}
.hv-facts{margin:6px 0 12px 18px;padding:0;line-height:1.6;font-size:14px}.hv-facts li{margin:2px 0}.hv h3{margin:18px 0 6px;font-size:15px}.hv h4{margin:14px 0 4px;font-size:13.5px}
.hv-chart{width:100%;max-width:760px;height:auto;display:block}.hv-chart text{font-size:11px;fill:var(--muted,#777)}.hv-chart .hv-l{fill:none;stroke-width:2.2}.hv-chart .hv-b{fill:none;stroke-width:1.4;stroke-dasharray:5 4;opacity:.75}
.hv-chart .hv-g{stroke:var(--line,#e5e5e5)}.hv-key{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.hv-key i{display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
.hv-t{border-collapse:collapse;font-size:13px;margin:4px 0 10px;width:100%;max-width:1000px}.hv-t th,.hv-t td{padding:6px 9px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.hv-t th{font-size:11.5px;font-weight:500;color:var(--muted,#777);background:var(--surface-2,#f3f2ee);white-space:normal;position:static}.hv-t td.n{font-variant-numeric:tabular-nums}.hv-wrap{overflow-x:auto}.hv-t .m{color:var(--muted,#777)}
.hv-k{font:inherit;border:0;background:none;padding:0;color:var(--accent,#1f6f4a);cursor:pointer;text-decoration:underline;text-underline-offset:2px;text-align:left}
.hv-more summary{cursor:pointer;font-size:13px;color:var(--accent,#1f6f4a);margin:4px 0 8px}.hv-chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 10px}.hv-chip{font:inherit;font-size:12.5px;border:1px solid var(--line,#ddd);border-radius:999px;padding:4px 11px;background:var(--surface,#fff);color:inherit;cursor:pointer}
.hv-chip.on{background:var(--accent,#1f6f4a);border-color:var(--accent,#1f6f4a);color:#fff}.hv-chip small{opacity:.75;margin-left:4px}
.hv-bar{display:inline-block;height:9px;border-radius:2px;background:var(--mk-cost,#c0392b);opacity:.7;vertical-align:middle;margin-right:6px}.hv-up{color:var(--mk-profit,#17734a)}.hv-down{color:var(--mk-cost,#c0392b)}
.hv-hists{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:10px 18px;margin:6px 0 10px;max-width:1080px}.hv-hbox{min-width:0}.hv-htitle{font-size:12.5px;line-height:1.45;margin:0 0 2px}.hv-htitle span{color:var(--muted,#777)}
.hv-hist{max-width:420px}.hv-chart .hv-lv{font-size:11.5px;font-weight:600;paint-order:stroke;stroke:var(--bg,#f3f2ee);stroke-width:4px;stroke-linejoin:round}.hv-chart .hv-end{fill:var(--ink,#222);font-size:12.5px}
.hv-hit rect{fill:transparent}.hv-hit:hover rect{fill:var(--ink,#222);fill-opacity:.05}.hv-hit .hv-x{stroke:var(--muted,#888);stroke-width:1;opacity:0}.hv-hit:hover .hv-x{opacity:.7}.hv-standbox{margin:2px 0 10px}.hv-stand{max-width:900px}
.hv-png{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px;margin:4px 0 12px;padding:8px 10px;border:1px dashed var(--line,#ddd);border-radius:10px;max-width:1000px}.hv-png-l{font-weight:600}
.hv-png label{display:inline-flex;gap:4px;align-items:center;cursor:pointer}.hv-png-out img{display:block;max-width:min(100%,900px);height:auto;border:1px solid var(--line,#ddd);border-radius:10px;margin:6px 0}
.hv-png-out .hv-png-acts{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 14px}.hv-png-out a,.hv-png-out button{font:inherit;font-size:13px;padding:4px 12px;border-radius:8px;border:1px solid var(--line,#ccc);background:var(--surface,#fff);color:var(--ink,#222);cursor:pointer;text-decoration:none}.hv-dd{font-size:11.5px;margin-left:4px;font-variant-numeric:tabular-nums}.hv-t tr.hv-base td{background:var(--surface-2,#f3f2ee)}`;
    document.head.appendChild(s);
  }
  const tone = (v) => (!fin(v) ? '' : v > 0 ? 'hv-up' : v < 0 ? 'hv-down' : '');
  const table = (h, rows, cls = []) => `<div class="hv-wrap"><table class="hv-t"><thead><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i && !cls.includes(i) ? ' class="n"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const meter = (p) => (fin(p) ? `<div class="hv-meter" title="${ord(p)} percentile"><span style="width:${Math.max(1, Math.min(100, p))}%"></span></div>` : '');

  /* ---------- the state now ---------- */
  function tiles(S, kind) {
    const T = [];
    const add = (lab, val, p, note) => T.push(`<div class="hv-tile"><small>${esc(lab)}</small><b>${val}</b>${meter(p)}<i>${note}</i></div>`);
    add('Under its all-time high', fin(S.dd) ? (S.dd === 0 ? 'at it' : sp(S.dd)) : '—', null, S.ath_date ? `high ${money(S.ath, false)} on ${esc(md(S.ath_date))}` : '');
    add('This run of highs', fin(S.age) && S.age >= 0 ? td(S.age) : '—', null, S.run_start ? `since ${esc(mdy(S.run_start))} · ${num(S.run_highs)} new highs · ${sp(S.run_gain)}` : 'no run: under a 10% drawdown');
    add('New highs, last 63 days', num(S.highs63), fin(S.highs63) ? Math.min(100, 100 * S.highs63 / 63) : null, 'of 63 trading days');
    add('Above its 200-day average', sp(S.ext200), S.ext_pct, fin(S.ext_pct) ? `${ord(S.ext_pct)} percentile of its own history` : 'under three years of history');
    add('12-1 month momentum', sp(S.mom, 0), S.mom_pct, (fin(S.mom_pct) ? `${ord(S.mom_pct)} pct. of its own` : '') + (fin(S.mom_xs) ? ` · ${ord(S.mom_xs)} among companies` : ''));
    add('Volatility, 21 days', fin(S.vol) ? pc(S.vol) + ' a year' : '—', S.vol_pct, fin(S.vol_pct) ? `${ord(S.vol_pct)} percentile (${S.vol_pct < 20 ? 'calm' : S.vol_pct > 80 ? 'stormy' : 'usual'})` : '');
    if (kind === 'stock' || fin(S.pe)) add('Trailing P/E', fin(S.pe) ? num(S.pe, 1) : '—', S.pe_pct, fin(S.pe_pct) ? `${ord(S.pe_pct)} percentile of its own` : fin(S.pe) ? 'under three years of P/E' : 'no positive four-quarter EPS on file');
    add('Volume, 3 months vs 12', fin(S.volu) ? num(S.volu, 2) + '×' : '—', null, fin(S.volu) ? (S.volu > 1.2 ? 'heavier than its year' : S.volu < 0.85 ? 'lighter than its year' : 'about its year') : 'no volume on file');
    return `<div class="hv-tiles">${T.join('')}</div>`;
  }
  function headline(name, S, kind) {
    const lvl = kind === 'index' || kind === 'industry';
    let h = `<b>${esc(name)}</b> closed at <b>${money(S.close, lvl)}</b> on ${esc(mdy(S.date))}`;
    if (fin(S.dd)) h += S.dd === 0 ? ' — <b>a new all-time high</b>' : ` — <b>${sp(S.dd)}</b> from its all-time high of ${money(S.ath, lvl)} (${esc(md(S.ath_date))})`;
    h += S.run_start && S.high ? `. Its run of highs began ${esc(mdy(S.run_start))}: ${td(S.age)}, ${num(S.run_highs)} new highs, ${sp(S.run_gain)} since.` : S.high ? '.' : '. It is not running at its highs now (within 5% of the high with a new one in the last month).';
    return `<p class="hv-head">${h}</p>`;
  }

  /* ---------- where it stands: the close over the last year (back to the start of a long run or slide, three years at
     most) with the regime's levels — the all-time high and 10% under it; the low and 10% and 20% above it; the range and
     its edges — its new highs or lows marked and this run, slide or range shaded. The page draws it as an SVG, the
     picture on a canvas, both from standModel(). ---------- */
  function series(doc) {
    if (!doc || !Array.isArray(doc.r) || !doc.r.length || !doc.d0 || !fin(doc.last)) return null;
    const days = [doc.d0];
    let t = Date.parse(doc.d0 + 'T00:00:00Z');
    for (const ch of String(doc.gaps || '')) { t += parseInt(ch, 36) * 864e5; days.push(new Date(t).toISOString().slice(0, 10)); }
    const n = Math.min(days.length, doc.r.length + 1);
    if (n < 30) return null;
    const c = new Float64Array(n);
    for (let i = 1; i < n; i++) c[i] = c[i - 1] + (+doc.r[i - 1] || 0) / 1e4;
    return { days: days.slice(0, n), close: Array.from(c, (v) => doc.last * Math.exp(v - c[n - 1])) };
  }
  const atDay = (days, d) => { let lo = 0, hi = days.length; while (lo < hi) { const m = (lo + hi) >> 1; if (days[m] < d) lo = m + 1; else hi = m; } return lo; };
  function standModel(doc, reg, S) {
    const P = series(doc);
    if (!P || !S) return null;
    const kind = kindOf(reg), N = P.days.length, C = P.close, lvl = doc.kind === 'index' || doc.kind === 'industry';
    let from = kind === 'ranges' ? N - 127 : N - 253;
    if (kind === 'highs' && S.high && S.run_start) from = Math.min(from, atDay(P.days, S.run_start) - 21);
    if (kind === 'lows' && S.since) from = Math.min(from, atDay(P.days, S.since) - 10);
    from = Math.max(0, from, N - 757);
    const lv = [], mark = new Array(N).fill(false);
    let shade = null, label = null, markWhat = '';
    if (kind === 'highs') {
      let mx = C[0];
      for (let i = 1; i < N; i++) { if (C[i] >= mx * (1 - 1e-9)) mark[i] = true; if (C[i] > mx) mx = C[i]; }
      const ath = fin(S.ath) ? S.ath : mx;
      lv.push({ v: ath, col: 'ink', dash: '6 4', text: `all-time high ${money(ath, lvl)}${S.ath_date ? ` (${md(S.ath_date)})` : ''}`, short: `high ${money(ath, lvl)}` });
      lv.push({ v: ath * 0.9, col: 'down', dash: '2 4', text: '10% under it: the pullback that ends a run', short: '−10%' });
      if (S.high && S.run_start) { const i0 = atDay(P.days, S.run_start); if (i0 < N) shade = { i0: Math.max(i0, from), col: 'up', text: `this run of highs, since ${md(S.run_start)}` }; }
      label = fin(S.dd) ? (S.dd > -0.0005 ? ['a new', 'all-time high'] : [sp(S.dd), 'from its high']) : null;
      markWhat = 'a new all-time high';
    } else if (kind === 'lows') {
      const span = reg === 'atl' ? 0 : reg === '52w' ? 252 : 63;
      if (!span) { let mn = C[0]; for (let i = 1; i < N; i++) { if (C[i] <= mn * (1 + 1e-9)) mark[i] = true; if (C[i] < mn) mn = C[i]; } }
      else {
        const dq = [];                                            // the lowest of the span before each day (a sliding minimum)
        for (let i = 0; i < N; i++) {
          while (dq.length && dq[0] < i - span) dq.shift();
          if (i >= span && dq.length && C[i] <= C[dq[0]] * (1 + 1e-9)) mark[i] = true;
          while (dq.length && C[dq[dq.length - 1]] >= C[i]) dq.pop();
          dq.push(i);
        }
      }
      let low = fin(S.low) ? S.low : Infinity;
      if (!fin(low)) for (let i = from; i < N; i++) low = Math.min(low, C[i]);
      lv.push({ v: low, col: 'down', dash: '6 4', text: `${SPAN[reg]} low ${money(low, lvl)}${S.low_date ? ` (${md(S.low_date)})` : ''}`, short: `low ${money(low, lvl)}` });
      lv.push({ v: low * 1.1, col: 'up', dash: '2 4', text: '10% above it: a rebound', short: '+10%' });
      lv.push({ v: low * 1.2, col: 'up', dash: '2 4', text: '20% above', short: '+20%' });
      if (S.since) { const i0 = atDay(P.days, S.since); if (i0 < N) shade = { i0: Math.max(i0, from), col: 'down', text: i0 >= from ? `the slide since ${reg === 'atl' ? 'its all-time high' : `its last ${SPAN[reg]} high`}, ${mdy(S.since)}` : `the slide (since ${mdy(S.since)})` }; }
      label = fin(S.dist) ? (S.dist < 0.0005 ? ['a new', `${SPAN[reg]} low`] : [sp(S.dist), 'above its low']) : null;
      markWhat = `a new ${SPAN[reg]} low`;
    } else {
      const i0 = Math.max(from, N - 63);
      if (fin(S.lo) && fin(S.hi)) {
        shade = { i0, col: 'accent', box: [S.lo, S.hi], text: 'the range: the last 63 trading days' };
        lv.push({ v: S.hi, col: 'accent', dash: '6 4', text: `top ${money(S.hi, lvl)}: a close above breaks out up`, short: `top ${money(S.hi, lvl)}`, i0 });
        lv.push({ v: S.lo, col: 'accent', dash: '6 4', text: `bottom ${money(S.lo, lvl)}: a close under breaks out down`, short: `bottom ${money(S.lo, lvl)}`, i0, below: true });
      }
      label = fin(S.pos) ? [pc(S.pos), 'of the way up'] : null;
    }
    let lo = Infinity, hi = -Infinity, clip = false;
    if (kind === 'ranges' && fin(S.lo) && fin(S.hi)) {            // the range fills the middle; earlier closes outside it are cut
      const w = Math.max(S.hi - S.lo, S.hi * 0.01);
      lo = S.lo - 0.75 * w; hi = S.hi + 0.75 * w;
      for (let i = Math.max(from, N - 63); i < N; i++) { lo = Math.min(lo, C[i]); hi = Math.max(hi, C[i]); }
      for (let i = from; i < N; i++) if (C[i] < lo || C[i] > hi) clip = true;
    } else {
      for (let i = from; i < N; i++) { lo = Math.min(lo, C[i]); hi = Math.max(hi, C[i]); }
      for (const l of lv) if (fin(l.v) && l.v < hi * 3 && l.v > lo / 3) { lo = Math.min(lo, l.v); hi = Math.max(hi, l.v); }
    }
    const log = !clip && hi / lo > 2.2;
    if (log) { lo /= 1.04; hi *= 1.04; } else if (!clip) { const pad = (hi - lo) * 0.06 || hi * 0.02; lo -= pad; hi += pad; }
    const marks = [];
    for (let i = from; i < N; i++) if (mark[i]) marks.push(i);
    return { days: P.days, close: C, from, N, lv, marks, markWhat, shade, label, kind, reg, lvl, lo, hi, log, clip, last: C[N - 1], date: P.days[N - 1] };
  }
  /* price ticks: a nice step (linear) or 1, 2, 5 × a power of ten (a log scale, with 1.5, 3, 7 when too few) */
  function priceTicks(lo, hi, log) {
    if (!log) { const st = niceStep(hi - lo), out = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toPrecision(12)); return out; }
    const pick = (ms) => { const out = []; for (let k = Math.floor(Math.log10(lo)) - 1; k <= Math.ceil(Math.log10(hi)); k++) for (const m of ms) { const v = m * Math.pow(10, k); if (v >= lo && v <= hi) out.push(+v.toPrecision(12)); } return out; };
    const t = pick([1, 2, 5]);
    return t.length >= 3 ? t : pick([1, 1.5, 2, 3, 5, 7]);
  }
  const axisMoney = (v, lvl) => (lvl ? '' : '$') + num(v, v >= 100 ? 0 : v >= 10 ? 1 : 2);
  /* the first trading day of every month (every 2nd, 3rd … so that at most `max` show), labelled with the year at January */
  function monthTicks(days, from, N, max = 7) {
    const all = [];
    for (let i = from + 1; i < N; i++) if (days[i].slice(0, 7) !== days[i - 1].slice(0, 7)) all.push(i);
    const every = Math.max(1, Math.ceil(all.length / max));
    let yr = '';
    return all.filter((_, k) => (all.length - 1 - k) % every === 0).map((i) => { const y = days[i].slice(0, 4), t = `${MON[+days[i].slice(5, 7) - 1]}${y !== yr ? ' ' + y : ''}`; yr = y; return { i, text: t }; });
  }
  const HCOL = { ink: 'var(--ink,#222)', up: 'var(--mk-profit,#17734a)', down: 'var(--mk-cost,#c0392b)', accent: 'var(--accent,#1f6f4a)', muted: 'var(--muted,#888)', line: 'var(--line,#e5e5e5)' };
  /* the levels' words: the most important first, the rest only where they do not run into one already placed */
  function levelWords(M, sy, top, bottom) {
    const out = [];
    for (const l of M.lv) {
      if (!fin(l.v) || l.v < M.lo || l.v > M.hi) continue;
      const fits = (y) => y >= top + 8 && y <= bottom - 2 && !out.some((o) => Math.abs(o.y - y) < 14);
      const a = l.below ? sy(l.v) + 14 : sy(l.v) - 5, b = l.below ? sy(l.v) - 5 : sy(l.v) + 14;   // its side of the line, else the other
      const y = fits(a) ? a : fits(b) ? b : null;
      if (y != null) out.push({ l, y });
    }
    return out;
  }
  function standChart(M, width) {
    if (!M) return '';
    const W = Math.round(Math.max(320, Math.min(900, width || 720))), narrow = W < 560, H = narrow ? 250 : 280, L = narrow ? 46 : 56, Rr = narrow ? 92 : 132, T = 14, B = 30, span = Math.max(1, M.N - 1 - M.from);
    const sx = (i) => L + ((i - M.from) / span) * (W - L - Rr);
    const sy = M.log ? (v) => T + ((Math.log(M.hi) - Math.log(v)) / (Math.log(M.hi) - Math.log(M.lo))) * (H - T - B) : (v) => T + ((M.hi - v) / (M.hi - M.lo)) * (H - T - B);
    const f1 = (v) => v.toFixed(1), y0 = T, y1 = H - B, xR = W - Rr, cid = `hvc${Math.round(M.last * 1000) % 100000}${M.N}`;
    let s = `<svg class="hv-chart hv-stand" viewBox="0 0 ${W} ${H}" role="img" aria-label="The close over ${M.N - M.from > 300 ? 'the last years' : 'the last year'}, with ${M.kind === 'highs' ? 'the all-time high' : M.kind === 'lows' ? 'the low' : 'the range'} marked">`;
    if (M.clip) s += `<defs><clipPath id="${cid}"><rect x="${L}" y="${y0}" width="${xR - L + 6}" height="${y1 - y0}"/></clipPath></defs>`;
    if (M.shade) {
      const x0 = sx(M.shade.i0), col = HCOL[M.shade.col];
      s += M.shade.box ? `<rect x="${f1(x0)}" y="${f1(sy(M.shade.box[1]))}" width="${f1(xR - x0)}" height="${f1(Math.max(1, sy(M.shade.box[0]) - sy(M.shade.box[1])))}" style="fill:${col};opacity:.1"/>`
        : `<rect x="${f1(x0)}" y="${y0}" width="${f1(xR - x0)}" height="${y1 - y0}" style="fill:${col};opacity:.07"/>`;
    }
    for (const v of priceTicks(M.lo, M.hi, M.log)) s += `<line class="hv-g" x1="${L}" x2="${xR}" y1="${f1(sy(v))}" y2="${f1(sy(v))}"/><text x="${L - 6}" y="${f1(sy(v) + 4)}" text-anchor="end">${esc(axisMoney(v, M.lvl))}</text>`;
    for (const t of monthTicks(M.days, M.from, M.N, narrow ? 4 : 7)) s += `<line class="hv-g" x1="${f1(sx(t.i))}" x2="${f1(sx(t.i))}" y1="${y1}" y2="${y1 + 4}"/><text x="${f1(sx(t.i))}" y="${H - 10}" text-anchor="middle">${esc(t.text)}</text>`;
    for (const l of M.lv) {
      if (!fin(l.v) || l.v < M.lo || l.v > M.hi) continue;
      s += `<line x1="${f1(l.i0 != null ? sx(l.i0) : L)}" x2="${xR}" y1="${f1(sy(l.v))}" y2="${f1(sy(l.v))}" style="stroke:${HCOL[l.col]};stroke-width:1.4;stroke-dasharray:${l.dash}"/>`;
    }
    const pts = [], step = Math.max(1, Math.floor(span / 900));
    for (let i = M.from; i < M.N; i += step) pts.push(`${f1(sx(i))},${f1(sy(M.close[i]))}`);
    if ((M.N - 1 - M.from) % step) pts.push(`${f1(sx(M.N - 1))},${f1(sy(M.last))}`);
    s += `<polyline class="hv-l" points="${pts.join(' ')}"${M.clip ? ` clip-path="url(#${cid})"` : ''} style="stroke:var(--ink,#222);stroke-width:1.8;stroke-linejoin:round"/>`;
    const mc = M.kind === 'highs' ? HCOL.up : HCOL.down;
    for (const i of M.marks) s += `<circle cx="${f1(sx(i))}" cy="${f1(sy(M.close[i]))}" r="2.6" style="fill:${mc}"/>`;
    for (const { l, y } of levelWords(M, sy, y0, y1)) s += `<text class="hv-lv" x="${f1((l.i0 != null ? sx(l.i0) : L) + 6)}" y="${f1(y)}" style="fill:${HCOL[l.col]}">${esc(narrow ? l.short || l.text : l.text)}</text>`;
    const xe = sx(M.N - 1), ye = sy(M.last);
    s += `<circle cx="${f1(xe)}" cy="${f1(ye)}" r="4.5" style="fill:var(--ink,#222);stroke:var(--bg,#f3f2ee);stroke-width:2"/>`;
    const ly = Math.min(Math.max(ye, y0 + 12), y1 - (M.label ? 30 : 4));   // the last close in words, right of its dot
    s += `<text class="hv-lv hv-end" x="${f1(xe + 10)}" y="${f1(ly + 4)}">${esc(money(M.last, M.lvl))}</text>`;
    if (M.label) s += `<text class="hv-lv" x="${f1(xe + 10)}" y="${f1(ly + 19)}" style="fill:var(--ink,#222)">${esc(M.label[0])}</text><text class="hv-lv" x="${f1(xe + 10)}" y="${f1(ly + 33)}" style="fill:var(--muted,#777);font-weight:500">${esc(M.label[1])}</text>`;
    const dx = (xR - L) / span;
    for (let i = M.from; i < M.N; i += 5) {                       // hover: a week a column, its last close
      const j = Math.min(M.N - 1, i + 4), isM = M.marks.some((k) => k >= i && k <= j);
      s += `<g class="hv-hit"><rect x="${f1(sx(i) - dx / 2)}" y="${y0}" width="${f1((j - i + 1) * dx)}" height="${y1 - y0}"/><line class="hv-x" x1="${f1(sx(j))}" x2="${f1(sx(j))}" y1="${y0}" y2="${y1}"/><title>${esc(`${mdy(M.days[j])}: ${money(M.close[j], M.lvl)}${isM && M.markWhat ? ` · ${M.markWhat} that week` : ''}`)}</title></g>`;
    }
    s += '</svg>';
    const keys = [`<span><i style="background:var(--ink,#222)"></i>the close, adjusted for dividends and splits</span>`];
    if (M.marks.length && M.markWhat) keys.push(`<span><i style="background:${mc};width:7px;height:7px;border-radius:50%"></i>${esc(M.markWhat)}</span>`);
    if (M.shade) keys.push(`<span><i style="background:${HCOL[M.shade.col]};opacity:.3;height:9px"></i>${esc(M.shade.text)}</span>`);
    if (M.clip) {
      let a = Infinity, b = -Infinity;
      for (let i = M.from; i < M.N; i++) if (M.close[i] < M.lo || M.close[i] > M.hi) { a = Math.min(a, M.close[i]); b = Math.max(b, M.close[i]); }
      keys.push(`<span>earlier closes off the scale: ${b < M.lo ? `as low as ${esc(money(a, M.lvl))}` : a > M.hi ? `as high as ${esc(money(b, M.lvl))}` : `${esc(money(a, M.lvl))} to ${esc(money(b, M.lvl))}`}</span>`);
    }
    return `<div class="hv-standbox">${s}<div class="hv-key">${keys.join('')}</div></div>`;
  }
  /* ---------- what followed ---------- */
  /* a bar with a rounded data end (3px), square at the baseline */
  function bar(x, w, y, y0, fill, op) {
    const hh = y0 - y;
    if (!(hh > 0.2) || !(w > 0)) return '';
    const r = Math.min(3, w / 2, hh), f = (v) => v.toFixed(1);
    return `<path d="M${f(x)},${f(y0)}V${f(y + r)}Q${f(x)},${f(y)} ${f(x + r)},${f(y)}H${f(x + w - r)}Q${f(x + w)},${f(y)} ${f(x + w)},${f(y + r)}V${f(y0)}Z" style="fill:${fill}"${op != null ? ` opacity="${op}"` : ''}/>`;
  }
  const dayWords = (d) => (d === 0 ? 'the day' : `${d} trading days on (about ${d < 21 ? `${Math.max(1, Math.round(d / 5))} week${Math.round(d / 5) > 1 ? 's' : ''}` : `${num(d / 21, d % 21 ? 1 : 0)} month${d === 21 ? '' : 's'}`})`);
  /* the first grid day at which a survival curve is at or under 50% (between two grid days: the straight line between) */
  function half(curve, grid) {
    for (let i = 1; i < curve.length; i++) if (fin(curve[i]) && fin(curve[i - 1]) && curve[i] <= 0.5 && curve[i - 1] > 0.5) return grid[i - 1] + (grid[i] - grid[i - 1]) * (curve[i - 1] - 0.5) / (curve[i - 1] - curve[i]);
    return null;
  }
  function kmChart(lines, grid, xl = 'trading days after the high day', aria = 'Survival curves: the share of high days not yet followed by each pullback') {
    const W = 720, H = 268, L = 46, R = 24, T = 14, B = 48, gx = grid[grid.length - 1], f1 = (v) => v.toFixed(1);
    const sx = (d) => L + (d / gx) * (W - L - R), sy = (v) => T + (1 - v) * (H - T - B);
    let s = `<svg class="hv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">`;
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { s += `<line class="hv-g" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"${v === 0.5 ? ' style="stroke:var(--muted,#999);stroke-dasharray:2 3"' : ''}/><text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${pc(v)}</text>`; });
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { s += `<text x="${sx(d)}" y="${H - 28}" text-anchor="middle">${d === 0 ? 'the day' : d === 21 ? '1 mo' : d === 63 ? '3 mo' : d === 126 ? '6 mo' : d === 189 ? '9 mo' : '12 mo'}</text>`; });
    const drawn = lines.filter((l) => l.curve);
    for (const l of drawn) {
      const pts = l.curve.map((v, i) => (fin(v) ? `${f1(sx(grid[i]))},${f1(sy(v))}` : null)).filter(Boolean);
      s += `<polyline class="${l.dash ? 'hv-b' : 'hv-l'}" points="${pts.join(' ')}" style="stroke:${l.col};stroke-linejoin:round"/>`;
    }
    for (const l of drawn) {                                      // where each solid curve crosses 50%: the median wait
      const m = l.dash ? null : half(l.curve, grid);
      if (m != null) s += `<circle cx="${f1(sx(m))}" cy="${f1(sy(0.5))}" r="4" style="fill:${l.col};stroke:var(--bg,#fcfcfb);stroke-width:2"><title>${esc(`${l.label}: half the days by about ${num(m)} trading days`)}</title></circle>`;
    }
    grid.forEach((g, i) => {                                      // hover: a column a week, every curve's share then
      const x0 = i ? (sx(grid[i - 1]) + sx(g)) / 2 : sx(g), x1 = i < grid.length - 1 ? (sx(g) + sx(grid[i + 1])) / 2 : sx(g);
      const tip = [dayWords(g), ...drawn.map((l) => `${pc(l.curve[i])} ${l.label || ''}${l.dash ? ` — every ${l.what || 'high day'} of ${l.who || 'the group'}` : ''}`)].join('\n');
      s += `<g class="hv-hit"><rect x="${f1(x0)}" y="${T}" width="${f1(Math.max(1, x1 - x0))}" height="${H - T - B}"/><line class="hv-x" x1="${f1(sx(g))}" x2="${f1(sx(g))}" y1="${T}" y2="${H - B}"/><title>${esc(tip)}</title></g>`;
    });
    s += `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">${esc(xl)}</text></svg>`;
    const dl = lines.find((l) => l.dash && l.curve);
    return s + `<div class="hv-key">${drawn.filter((l) => !l.dash).map((l) => `<span><i style="background:${l.col}"></i>${esc(l.label)}</span>`).join('')}${dl ? `<span><i style="background:var(--muted,#999);height:1px"></i>dashed: every ${esc(dl.what || 'high day')} of ${esc(dl.who || 'the group')}</span>` : ''}<span><i style="background:var(--ink,#222);width:8px;height:8px;border-radius:50%"></i>the dot: half of them by then (the median)</span></div>`;
  }
  function facts(A, lvl) {
    const t5 = A.t5 || {}, t10 = A.t10 || {}, t20 = A.t20 || {}, rl = A.run_left || {}, p = (k, h) => ((k || {}).p || {})[h];
    const G = A.gain_left || {}, P = A.pullback || {}, B = A.days_back || {}, f3 = A.fwd63 || {}, f12 = A.fwd252 || {};
    const L = [];
    L.push(`<b>A 5% pullback</b> from the high: median <b>${td(t5.median)}</b> away — ${pc(p(t5, '21'))} within a month, ${pc(p(t5, '63'))} within 3 months.`);
    L.push(`<b>A 10% pullback</b>: median <b>${td(t10.median)}</b> — ${pc(p(t10, '21'))} within 1 month, ${pc(p(t10, '63'))} within 3, ${pc(p(t10, '126'))} within 6, ${pc(p(t10, '252'))} within 12.`);
    L.push(`<b>A 20% pullback</b>: ${pc(p(t20, '63'))} within 3 months, ${pc(p(t20, '252'))} within 12${t20.median ? ` (median ${td(t20.median)})` : ''}.`);
    L.push(`<b>The run went on</b>: ${pc(A.more_highs)} made at least one more new high (median ${num((A.highs_left || {}).p50)} more); its peak came a median <b>${td(rl.median)}</b> later, <b>${sp(G.p50)}</b> further up (25–75%: ${sp(G.p25)} to ${sp(G.p75)}).`);
    L.push(`<b>The pullback that ended the run</b> (10% or more by definition): median <b>${sp(P.p50)}</b> from the run's peak; a quarter of them ${sp(P.p25)} or worse, a tenth ${sp(P.p10)} or worse${fin(A.pullback_open) && A.pullback_open > 0 ? ` (${pc(A.pullback_open)} still open at their depth so far)` : ''}. Back to the peak in a median ${td(B.p50)}.`);
    L.push(`<b>Returns</b>: 3 months <span class="${tone(f3.p50)}">${sp(f3.p50)}</span> median (${pc(f3.up)} up); 12 months <span class="${tone(f12.p50)}">${sp(f12.p50)}</span> median (${pc(f12.up)} up; 10–90%: ${sp(f12.p10)} to ${sp(f12.p90)}).`);
    return `<ul class="hv-facts">${L.map((x) => `<li>${x}</li>`).join('')}</ul>`;
  }
  function oddsTable(A, B) {
    const row = (lab, a, b) => [lab, ...['21', '63', '126', '252'].map((h) => `${pc(((a || {}).p || {})[h])}${b ? ` <span style="color:var(--muted,#777)">· ${pc(((b || {}).p || {})[h])}</span>` : ''}`), `${td((a || {}).median)}${b ? ` <span style="color:var(--muted,#777)">· ${num((b || {}).median)}</span>` : ''}`];
    return table(['Within', ...Object.values(HZW), 'Median'], [row('A 5% pullback', A.t5, B && B.t5), row('A 10% pullback', A.t10, B && B.t10), row('A 20% pullback', A.t20, B && B.t20),
      row('The run’s peak passed (its last high before a 10% pullback)', A.run_left, B && B.run_left)], [0]);
  }
  const FEAT = { age: 'run age', highs63: 'new highs in 63 days', dd: 'distance from the high', ext_pct: 'above the 200-day average (own percentile)', mom_pct: 'momentum (own percentile)',
    vol_pct: 'volatility (own percentile)', pe_pct: 'P/E (own percentile)', volu: 'volume vs its year' };
  function block(H, name, kind, base, groupKey, opts = {}) {
    const S = H.state || {}, A = H.analogues, O = H.own || {}, lvl = kind === 'index' || kind === 'industry';
    let h = headline(name, S, kind) + tiles(S, kind) + (opts.stand || '');
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar high days</h3><p class="hv-sub">High days of ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} runs) nearest on ${esc(A.features.map((f) => FEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year. A pullback counts from the all-time high; the days are trading days.${base ? ' After the dot: every high day of the group, for comparison.' : ''}</p>`;
      h += facts(A, lvl);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'no 5% pullback yet', curve: (A.t5 || {}).curve, col: 'var(--q-warm,#d9822b)' }, { label: 'no 10% pullback yet', curve: (A.t10 || {}).curve, col: 'var(--mk-cost,#c0392b)' },
        { label: 'the run still ahead of its peak', curve: (A.run_left || {}).curve, col: 'var(--mk-profit,#17734a)' },
        ...(base ? [{ dash: true, label: 'no 10% pullback yet', curve: (base.t10 || {}).curve, col: 'var(--mk-cost,#c0392b)', who: GROUP[groupKey] }, { dash: true, label: 'no 5% pullback yet', curve: (base.t5 || {}).curve, col: 'var(--q-warm,#d9822b)', who: GROUP[groupKey] }] : [])], g);
      h += oddsTable(A, base);
      h += spreadBlock(A, opts.group, opts.params, 'high day', ['mdd63', 'gain_left']);
      h += condBlock(S, A, opts.group, 'highs', 'high day', GROUP[groupKey] || 'its kind');
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'Run age', 'Highs in 63 d', 'To its peak', 'To a 10% pullback', 'The pullback after', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), td(e.age), num(e.highs63), e.run_left == null ? 'not yet' : td(e.run_left), e.t10 == null ? 'not yet' : td(e.t10), sp(e.pullback), `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
      h += backtestBlock((opts.group || {}).backtest, 'highs', 'high day', GROUP[groupKey] || 'its kind');
    } else if (S.high) h += `<p class="hv-sub">Too few similar high days with every state variable on file to compare.</p>`;
    if (O.runs) {
      h += `<h3>Its own runs</h3><p class="hv-sub">${esc(name)}'s ${num(O.runs)} completed runs of highs (from the first ATH after a 10% drawdown to the last one before the next): median <b>${td((O.run_days || {}).p50)}</b> from first high to peak (25–75%: ${num((O.run_days || {}).p25)}–${num((O.run_days || {}).p75)}); the pullback after them median <b>${sp((O.pullback || {}).p50)}</b> (25–75%: ${sp((O.pullback || {}).p25)} to ${sp((O.pullback || {}).p75)}); back to the peak in a median ${td((O.days_back || {}).p50)}.</p>`;
      h += table(['Run began', 'Peak', 'Days to the peak', 'The pullback after', 'Back to the peak'], (O.last || []).slice().reverse().map((r) => [esc(mdy(r.start)), esc(mdy(r.peak)), num(r.days), `<span class="hv-down">${sp(r.pullback)}</span>`, r.days_back == null ? 'not yet' : td(r.days_back)]), [0, 1]);
    }
    h += `<p class="hv-sub">Adjusted closes (dividends reinvested), so an all-time high is a total-return high; P/E: price ÷ the last four first-filed quarterly diluted EPS (SEC), positive only. Companies are today's (survivors), which flatters what came after their highs. History, not a forecast.</p>`;
    return h;
  }

  /* ---------- the spread of what followed, one condition at a time, the walk-forward test (app/regime_odds.py) ---------- */
  const DLAB = { fwd21: '1 month on', fwd63: '3 months on', fwd252: '12 months on', fall63: 'Lowest close of the next 3 months', bounce: 'The rebound from the low before a 10% rebound',
    rise63: 'Highest close of the next 3 months', mdd63: 'Largest fall within 3 months', gain_left: 'The gain left to the run’s peak' };
  const pct0 = (v) => (fin(v) ? (v < 0 ? '−' : v > 0 ? '+' : '') + num(Math.abs(100 * v)) + '%' : '');
  const binLabel = (E, i) => (i === 0 ? `under ${pct0(E[0])}` : i === E.length ? `${pct0(E[E.length - 1])} or more` : `${pct0(E[i - 1])} to ${pct0(E[i])}`);
  const FALLS = ['fall63', 'mdd63'], RISES = ['bounce', 'rise63', 'gain_left'];
  const plural = (w) => String(w).replace(/^(high )?day\b/, (m) => m + 's');
  /* bars: the share of the similar days in each band (rounded data ends); the outline: the share of every day of the
     regime; the dashed line: their median, placed inside its band */
  function histChart(counts, E, base, title, sub, key, med) {
    const n = (counts || []).reduce((a, b) => a + b, 0);
    if (!n || !E || counts.length !== E.length + 1) return '';
    const nb = (base || []).reduce((a, b) => a + b, 0), k = counts.length, W = 340, H = 172, L = 6, R = 6, T = 22, B = 26, bw = (W - L - R) / k, f1 = (v) => v.toFixed(1);
    const sh = counts.map((c) => c / n), shb = nb && base.length === k ? base.map((c) => c / nb) : null, mx = Math.max(0.05, ...sh, ...(shb || []));
    const y = (v) => T + (1 - v / mx) * (H - T - B);
    let s = `<svg class="hv-chart hv-hist" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}: the share of days in each band"><line class="hv-g" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
    counts.forEach((c, i) => {
      const lo = i === 0 ? null : E[i - 1], hi = i === k - 1 ? null : E[i], mid = lo == null ? hi - 1 : hi == null ? lo + 1 : (lo + hi) / 2;
      const down = FALLS.includes(key) ? true : RISES.includes(key) ? false : mid < 0;
      s += bar(L + i * bw + 1.5, bw - 3, y(sh[i]), y(0), down ? HCOL.down : HCOL.up, 0.62);
    });
    if (shb) s += `<path d="${shb.map((v, i) => `${i ? 'L' : 'M'}${f1(L + i * bw)},${f1(y(v))}L${f1(L + (i + 1) * bw)},${f1(y(v))}`).join('')}" style="fill:none;stroke:var(--ink,#222);stroke-width:1.4;stroke-linejoin:round"/>`;
    if (fin(med)) {
      let b = 0;
      while (b < E.length && E[b] <= med) b++;
      const fr = b === 0 || b === E.length ? 0.5 : (med - E[b - 1]) / (E[b] - E[b - 1]), xm = L + (b + fr) * bw;
      s += `<line x1="${f1(xm)}" x2="${f1(xm)}" y1="${T - 4}" y2="${f1(y(0))}" style="stroke:var(--ink,#222);stroke-width:1.3;stroke-dasharray:4 3"/>`;
      s += `<text class="hv-lv" x="${f1(Math.min(Math.max(xm, L + 44), W - R - 44))}" y="${T - 8}" text-anchor="middle" style="fill:var(--ink,#222)">median ${esc(pct0(med) || '0%')}</text>`;
    }
    const every = k > 8 ? 2 : 1, z = E.findIndex((e) => e === 0), off = z >= 0 ? z % every : every - 1;   // every other edge when crowded, 0 kept
    E.forEach((e, i) => { if (i % every === off) s += `<text x="${f1(L + (i + 1) * bw)}" y="${H - 9}" text-anchor="middle">${pct0(e) || '0'}</text>`; });
    counts.forEach((c, i) => { s += `<g class="hv-hit"><rect x="${f1(L + i * bw)}" y="${T}" width="${f1(bw)}" height="${f1(y(0) - T)}"/><title>${esc(`${binLabel(E, i)}: ${pc(sh[i])} of these days (${num(c)})${shb ? ` · ${pc(shb[i])} of every day` : ''}`)}</title></g>`; });
    return `<div class="hv-hbox"><div class="hv-htitle"><b>${esc(title)}</b>${sub ? ` <span>· ${sub}</span>` : ''}</div>${s}</svg></div>`;
  }
  function niceStep(span) { const raw = span / 4, p = Math.pow(10, Math.floor(Math.log10(raw))); return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw) || raw; }
  /* the fan: the return from the day at each week to a year — the middle half, eight in ten, the median; dashed: the median of every day */
  function fanChart(F, Fb, grid, what) {
    if (!F || !F.p50) return '';
    grid = grid && grid.length === F.p50.length ? grid : F.p50.map((_, i) => i * 7);
    const vals = [...F.p10, ...F.p90, ...((Fb && Fb.p50) || [])].filter(fin);
    if (vals.length < 4) return '';
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const W = 720, H = 258, L = 50, R = 70, T = 12, B = 32, gx = grid[grid.length - 1], f1 = (v) => v.toFixed(1);
    const sx = (d) => L + (d / gx) * (W - L - R), sy = (v) => T + ((hi - v) / (hi - lo)) * (H - T - B);
    const band = (a, b, op) => { const up = [], dn = []; grid.forEach((g, i) => { if (fin(a[i]) && fin(b[i])) { up.push(`${f1(sx(g))},${f1(sy(b[i]))}`); dn.unshift(`${f1(sx(g))},${f1(sy(a[i]))}`); } });
      return up.length > 1 ? `<polygon points="${up.concat(dn).join(' ')}" fill="var(--accent,#1f6f4a)" opacity="${op}"/>` : ''; };
    const line = (a) => grid.map((g, i) => (fin(a[i]) ? `${f1(sx(g))},${f1(sy(a[i]))}` : null)).filter(Boolean).join(' ');
    let s = `<svg class="hv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="The spread of the return from the day over the next year">`;
    const st = niceStep(hi - lo);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) s += `<line class="hv-g" x1="${L}" x2="${W - R}" y1="${f1(sy(v))}" y2="${f1(sy(v))}"${Math.abs(v) < 1e-9 ? ' style="stroke:var(--muted,#999)"' : ''}/><text x="${L - 6}" y="${f1(sy(v) + 4)}" text-anchor="end">${pct0(Math.abs(v) < 1e-9 ? 0 : v) || '0%'}</text>`;
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { s += `<text x="${f1(sx(d))}" y="${H - 12}" text-anchor="middle">${d === 0 ? 'the day' : d === 21 ? '1 mo' : d === 63 ? '3 mo' : d === 126 ? '6 mo' : d === 189 ? '9 mo' : '12 mo'}</text>`; });
    s += band(F.p10, F.p90, 0.12) + band(F.p25, F.p75, 0.24) + `<polyline class="hv-l" points="${line(F.p50)}" style="stroke:var(--accent,#1f6f4a);stroke-linejoin:round"/>`;
    if (Fb && Fb.p50) s += `<polyline class="hv-b" points="${line(Fb.p50)}" style="stroke:var(--ink,#444)"/>`;
    const e = F.p50.length - 1;                                    // the year's end: the median and the middle half, in words
    if (fin(F.p50[e])) s += `<text class="hv-lv" x="${f1(sx(grid[e]) + 6)}" y="${f1(sy(F.p50[e]) + 4)}" style="fill:var(--accent,#1f6f4a)">${esc(pct0(F.p50[e]) || '0%')}</text>`;
    if (fin(F.p75[e])) s += `<text x="${f1(sx(grid[e]) + 6)}" y="${f1(sy(F.p75[e]) + 4)}">${esc(pct0(F.p75[e]))}</text>`;
    if (fin(F.p25[e])) s += `<text x="${f1(sx(grid[e]) + 6)}" y="${f1(sy(F.p25[e]) + 4)}">${esc(pct0(F.p25[e]))}</text>`;
    grid.forEach((g, i) => {
      const x0 = i ? (sx(grid[i - 1]) + sx(g)) / 2 : sx(g), x1 = i < grid.length - 1 ? (sx(g) + sx(grid[i + 1])) / 2 : sx(g);
      const tip = `${dayWords(g)}\nmedian ${pct0(F.p50[i]) || '0%'}\nthe middle half ${pct0(F.p25[i]) || '0%'} to ${pct0(F.p75[i]) || '0%'}\neight in ten ${pct0(F.p10[i]) || '0%'} to ${pct0(F.p90[i]) || '0%'}${Fb && Fb.p50 && fin(Fb.p50[i]) ? `\nevery ${what || 'day'}: median ${pct0(Fb.p50[i]) || '0%'}` : ''}`;
      s += `<g class="hv-hit"><rect x="${f1(x0)}" y="${T}" width="${f1(Math.max(1, x1 - x0))}" height="${H - T - B}"/><line class="hv-x" x1="${f1(sx(g))}" x2="${f1(sx(g))}" y1="${T}" y2="${H - B}"/><title>${esc(tip)}</title></g>`;
    });
    s += '</svg>';
    return s + `<div class="hv-key"><span><i style="background:var(--accent,#1f6f4a);opacity:.5;height:8px"></i>the middle half (25–75%)</span><span><i style="background:var(--accent,#1f6f4a);opacity:.2;height:8px"></i>eight in ten (10–90%)</span><span><i style="background:var(--accent,#1f6f4a)"></i>the median</span>${Fb && Fb.p50 ? `<span><i style="background:var(--ink,#444);height:1px"></i>dashed: the median of every ${esc(what || 'day')}</span>` : ''}</div>`;
  }
  /* the fan and the histograms of what followed (the similar days, with every day of the regime beside them) */
  function spreadBlock(A, G, params, what, extra) {
    if (!A || !A.dist) return '';
    const E = (params && params.edges) || {}, D = A.dist, Db = (G && G.dist) || {}, q_ = (k) => A[k] || {};
    const fan = fanChart(A.fan, G && G.fan, params && params.fan_grid, what);
    const sub = (k) => (fin(q_(k).p50) ? `median <span class="${tone(q_(k).p50)}">${pct0(q_(k).p50)}</span>${fin(q_(k).up) && k.startsWith('fwd') ? `, ${pc(q_(k).up)} up` : ''}` : '');
    const H = ['fwd21', 'fwd63', 'fwd252', ...extra].filter((k) => D[k] && E[k]).map((k) => histChart(D[k], E[k], Db[k], DLAB[k] || k, sub(k), k, q_(k).p50)).join('');
    if (!fan && !H) return '';
    const cmp = G && G.dist ? ` — the bars are these days, the outline every ${esc(what)} of the group, on the same bands; the dashed line is their median. Hover a band for its shares` : '';
    return `<h3>The spread of what followed</h3><p class="hv-sub">Not just the median: the return from the day over the next year at every week (the fan), and how the returns and ${extra.map((k) => 'the ' + (DLAB[k] || k).replace(/^the /i, '').replace(/^./, (c) => c.toLowerCase())).join(' and ')} spread out${cmp}.</p>${fan}<div class="hv-hists">${H}</div>`;
  }
  const OUT = {
    lows: [['fwd63_up', '3 months on: up', (x) => (x.fwd63 || {}).up], ['fwd252_up', '12 months on: up', (x) => (x.fwd252 || {}).up],
      ['next_low_p63', 'A new low within 3 months', (x) => p_(x.next_low, '63')], ['r10_p63', 'A 10% rebound within 3 months', (x) => p_(x.r10, '63')]],
    ranges: [['fwd63_up', '3 months on: up', (x) => (x.fwd63 || {}).up], ['fwd252_up', '12 months on: up', (x) => (x.fwd252 || {}).up],
      ['breakout_p63', 'A breakout within 3 months', (x) => p_(x.breakout, '63')], ['up_first', 'Up first', (x) => x.up_first]],
    highs: [['fwd63_up', '3 months on: up', (x) => (x.fwd63 || {}).up], ['fwd252_up', '12 months on: up', (x) => (x.fwd252 || {}).up],
      ['t10_p63', 'A 10% pullback within 3 months', (x) => p_(x.t10, '63')], ['more_highs', 'Another new high', (x) => x.more_highs]],
  };
  const PCTF = ['mom_pct', 'mom_xs', 'vol_pct', 'pe_pct', 'ext_pct', 'width_pct'];
  function valOf(f, v) {
    if (!fin(v)) return '—';
    if (PCTF.includes(f)) return `the ${ord(v)} percentile`;
    if (f === 'dd_ath' || f === 'ext200') return sp(v, 0);
    if (f === 'age') return td(v);
    if (f === 'pe') return num(v, 1);
    if (f === 'volu') return num(v, 2) + '×';
    if (f === 'width') return pc(v, 1);
    if (f === 'pos') return pc(v);
    return num(v);
  }
  const delta = (v, b) => (fin(v) && fin(b) ? `<span class="hv-dd ${v - b > 0.005 ? 'hv-up' : v - b < -0.005 ? 'hv-down' : 'm'}">${v - b >= 0 ? '+' : '−'}${num(Math.abs(100 * (v - b)))} pts</span>` : '');
  /* the odds given each of its conditions alone (every day of the group in the same band), against every day, and all together (the similar days) */
  function condBlock(S, A, G, kind, what, who) {
    if (!G || !G.buckets || !G.base) return '';
    const O = OUT[kind], B = G.base, rows = [];
    for (const [f, b] of Object.entries(G.buckets)) {
      const v = S[f], E = b.edges;
      if (!fin(v) || !E) continue;
      const i = E.findIndex((e, j) => j < E.length - 1 && v >= e && v < E[j + 1]);
      const r = i >= 0 ? b.rows[i] : null;
      if (!r || !r.days || r.days < 100) continue;
      rows.push({ f, title: b.title, label: r.label, v, r, d: fin(r[O[0][0]]) && fin(O[0][2](B)) ? Math.abs(r[O[0][0]] - O[0][2](B)) : 0 });
    }
    if (!rows.length) return '';
    rows.sort((a, b) => b.d - a.d);
    const cells = (get) => O.map(([k, , g]) => { const v = get(k, g), b = g(B); return `${pc(v)}${get === base_ ? '' : delta(v, b)}`; });
    const base_ = (k, g) => g(B);
    const head = ['Given', 'Days', ...O.map((o) => o[1])];
    const T = [[`<b>Every ${esc(what)}</b> of ${esc(who)}`, num(B.days), ...cells(base_)]];
    if (A && A.days) T.push([`<b>All its conditions together</b>: the ${num(A.days)} most similar days`, num(A.days), ...cells((k, g) => g(A))]);
    for (const x of rows) T.push([`${esc(x.title)}: <b>${esc(x.label)}</b> <span class="m">(it: ${esc(valOf(x.f, x.v))})</span>`, num(x.r.days), ...cells((k) => x.r[k])]);
    const tb = table(head, T, [0]).replace('<tbody><tr>', '<tbody><tr class="hv-base">');
    return `<h3>The odds given its conditions — one at a time, and all together</h3><p class="hv-sub">Conditional probabilities from every ${esc(what)} of ${esc(who)}: each row keeps only the days in the same band as ${'its'} state on that one condition, the points against every day beside it; the second row puts every condition together (the most similar days above). Sorted by how much the condition moves the 3-month odds. Overlapping days and today's companies only: a guide to which conditions matter, not a forecast.</p>${tb}`;
  }
  const ONAME = { up63: 'Higher 3 months later', up252: 'Higher 12 months later', low63: 'A new low within 3 months', r10_63: 'A 10% rebound within 3 months',
    brk63: 'A breakout within 3 months', upfirst: 'Up first (of the breakouts)', pull63: 'A 10% pullback within 3 months' };
  const VERD = { useful: ['useful', 'hv-up'], small: ['small', ''], none: ['none: no better than the base rate', 'hv-down'] };
  function calibChart(s, title) {
    if (!s || !(s.calibration || []).length) return '';
    const W = 300, H = 230, L = 40, R = 20, T = 10, B = 34, pts = s.calibration.filter((c) => fin(c[0]) && fin(c[1]));
    const all = pts.flatMap((c) => [c[0], c[1]]), lo = Math.max(0, Math.floor(10 * Math.min(...all)) / 10), hi = Math.min(1, Math.ceil(10 * Math.max(...all)) / 10 || 1);
    const sx = (v) => L + ((v - lo) / Math.max(0.05, hi - lo)) * (W - L - R), sy = (v) => T + (1 - (v - lo) / Math.max(0.05, hi - lo)) * (H - T - B);
    let g = `<svg class="hv-chart hv-hist" viewBox="0 0 ${W} ${H}" role="img" aria-label="Calibration: said against happened, by tenth of the odds">`;
    for (let v = lo; v <= hi + 1e-9; v += 0.1) g += `<line class="hv-g" x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/><text x="${L - 5}" y="${(sy(v) + 4).toFixed(1)}" text-anchor="end">${pc(v)}</text><text x="${sx(v).toFixed(1)}" y="${H - 18}" text-anchor="middle">${pc(v)}</text>`;
    g += `<line x1="${sx(lo)}" y1="${sy(lo)}" x2="${sx(hi)}" y2="${sy(hi)}" stroke="var(--muted,#999)" stroke-dasharray="4 4"/>`;
    for (const c of pts) g += `<circle cx="${sx(c[0]).toFixed(1)}" cy="${sy(c[1]).toFixed(1)}" r="4.5" fill="var(--accent,#1f6f4a)"><title>said ${pc(c[0], 1)}, happened ${pc(c[1], 1)} (${num(c[2])} days)</title></circle>`;
    g += `<text x="${(L + W - R) / 2}" y="${H - 3}" text-anchor="middle">said (the similar days' odds)</text></svg>`;
    return `<div class="hv-hbox"><div class="hv-htitle"><b>${esc(title)}</b> <span>· happened (up) against said (across), by tenth</span></div>${g}</div>`;
  }
  function yearBars(by) {
    const v = (by || []).filter((r) => fin(r[2]));
    if (v.length < 5) return '';
    const W = 720, H = 140, L = 44, R = 10, T = 10, B = 26, mx = Math.max(0.02, ...v.map((r) => Math.abs(r[2]))), bw = (W - L - R) / v.length;
    const sy = (x) => T + ((mx - x) / (2 * mx)) * (H - T - B);
    let s = `<svg class="hv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Brier skill by year"><line class="hv-g" x1="${L}" x2="${W - R}" y1="${sy(0)}" y2="${sy(0)}" style="stroke:var(--muted,#999)"/>`;
    s += `<text x="${L - 5}" y="${(sy(mx) + 4).toFixed(1)}" text-anchor="end">+${num(100 * mx, 1)}%</text><text x="${L - 5}" y="${(sy(-mx) + 4).toFixed(1)}" text-anchor="end">−${num(100 * mx, 1)}%</text>`;
    v.forEach((r, i) => { const x = L + i * bw, y0 = sy(0), y1 = sy(r[2]); s += `<rect x="${(x + 1).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${Math.abs(y1 - y0).toFixed(1)}" fill="${r[2] >= 0 ? 'var(--mk-profit,#17734a)' : 'var(--mk-cost,#c0392b)'}" opacity=".8"><title>${r[0]}: skill ${num(100 * r[2], 1)}% (${num(r[1])} days; happened ${pc(r[3])})</title></rect>`;
      if (i % Math.max(1, Math.round(v.length / 8)) === 0) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 9}" text-anchor="middle">${r[0]}</text>`; });
    return s + '</svg>';
  }
  /* the walk-forward test of the similar-days odds for this regime and kind of asset */
  function backtestBlock(bt, kind, what, who) {
    if (!bt || !bt.outcomes || !Object.keys(bt.outcomes).length) return '';
    const O = bt.outcomes, sp_ = bt.spread, other = { lows: 'low63', ranges: 'brk63', highs: 'pull63' }[kind];
    let h = `<h3>Has it worked? The similar-days odds, tested year by year</h3><p class="hv-sub">A historical backtest without look-ahead: each year from ${esc(bt.years[0])} to ${esc(bt.years[1])}, up to ${num(bt.per_year)} ${esc(plural(what))} of ${esc(who)} (one per asset in any 21 trading days) were given the odds of their ${num(bt.k)} nearest days — the same rule as above, but found only among days whose 12-month outcome was known before that year began — and checked against what then happened: ${num(bt.days)} days in all. Brier skill: how much better those odds scored than always saying the base rate (0 = no better, negative = worse); AUC: how often they ranked a day that happened above one that didn't (0.5 = a coin toss).</p>`;
    h += table(['Outcome', 'Days', 'Happened', 'Brier skill', 'AUC', 'Verdict'], Object.entries(O).map(([k, s]) => [esc(ONAME[k] || k), num(s.n), pc(s.rate), fin(s.skill) ? `${s.skill >= 0 ? '+' : '−'}${num(Math.abs(100 * s.skill), 1)}%` : '—', num(s.auc, 3),
      `<span class="${(VERD[s.verdict] || [])[1] || ''}">${esc((VERD[s.verdict] || [s.verdict || '—'])[0])}</span>`]), [0, 5]);
    h += `<div class="hv-hists">${calibChart(O.up63, ONAME.up63)}${other && O[other] ? calibChart(O[other], ONAME[other]) : ''}</div>`;
    if (sp_) h += `<p class="hv-head">Sorted by those odds within each year, the fifth with the best 3-month odds rose <b class="${tone(sp_.top)}">${pct0(sp_.top)}</b> on average over the next 3 months and the worst fifth <b class="${tone(sp_.bottom)}">${pct0(sp_.bottom)}</b> (every tested day ${pct0(sp_.all)}): <b>${sp(sp_.diff, 1)}</b> between them (t ${num(sp_.t, 1)} over ${num(sp_.years)} years, ahead in ${pc(sp_.pos)} of them), before trading costs.</p>`;
    if (O.up63 && O.up63.by_year) h += `<h4>Brier skill of the 3-month odds, year by year</h4>${yearBars(O.up63.by_year)}`;
    return h;
  }

  /* ---------- the research tables (hub) ---------- */
  function bucketTable(G, f) {
    const b = G.buckets && G.buckets[f];
    if (!b) return '';
    const mx = Math.max(1, ...b.rows.map((r) => r.t10_median || 0));
    return `<h4>${esc(b.title)}</h4>` + table(['', 'High days · runs', 'Median days to a 5% · 10% pullback', '10% pullback within 3 · 12 months', 'To the run’s peak (median) · another high', 'The pullback after the run (median)', '12 months: median · up'],
      b.rows.map((r) => !r.days ? [esc(r.label), '—', '', '', '', '', ''] : [esc(r.label), `${num(r.days)} · ${num(r.runs)}`,
        `${num(r.t5_median)} · <span class="hv-bar" style="width:${(50 * (r.t10_median || 0) / mx).toFixed(0)}px;background:var(--mk-profit,#17734a)"></span>${num(r.t10_median)}`, `${pc(r.t10_p63)} · ${pc(r.t10_p252)}`,
        `${num(r.run_left_median)} d · ${pc(r.more_highs)}`, `<span class="hv-down">${sp(r.pullback_median)}</span>`, `<span class="${tone(r.fwd252)}">${sp(r.fwd252)}</span> · ${pc(r.fwd252_up)}`]), [0]);
  }
  function hub(doc, o) {
    const st = o.state || {}, gs = Object.keys(doc.groups || {});
    const grp = gs.includes(st.mvhg) ? st.mvhg : gs[0] || 'companies', G = (doc.groups || {})[grp] || {};
    const sorts = [['highs63', 'Most new highs in 63 days'], ['age', 'Oldest runs'], ['ext200', 'Furthest above the 200-day average'], ['pe_pct', 'Highest P/E against its own'], ['risk', 'Most likely to fall 10% within 3 months'], ['dd', 'Closest to the high']];
    const sort = sorts.some((s) => s[0] === st.mvhs) ? st.mvhs : 'highs63';
    const field = o.field || ((id, lab, items, v) => `<label>${lab} <select id="${id}">${items.map(([k, l]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`);
    const now = (doc.now || []).filter((r) => r.group === grp);
    const risk = (r) => ((((r.analogues || {}).t10) || {}).p || {})['63'];
    const key = { highs63: (r) => -(r.state.highs63 || 0), age: (r) => -(r.state.age || 0), ext200: (r) => -(r.state.ext200 || 0), pe_pct: (r) => -(r.state.pe_pct ?? -1), risk: (r) => -(risk(r) ?? -1), dd: (r) => -(r.state.dd ?? -1) }[sort];
    now.sort((a, b) => key(a) - key(b) || String(a.key).localeCompare(String(b.key)));
    const B = G.base || {};
    let h = `<div class="hv"><p class="hv-sub">An asset runs at its highs when it closes within 5% of its all-time high with a new high in the last 21 trading days. Every such day since the data begins is counted (the S&amp;P 500 index since 1928, companies since their first day on file), with the state the asset was in — the run's age, new highs in the last quarter, how far above its 200-day average, momentum, volatility, P/E and volume — and what followed: the days to the first 5%, 10% and 20% pullback from the high, the rest of the run (to its last high before a 10% pullback) and the depth of the pullback that ended it. ${esc(doc.note || '')}</p>`;
    h += `<div class="toolbar">${field('mvhg', 'Assets', gs.map((g) => [g, (doc.groups[g] || {}).label || g]), grp)}${field('mvhs', 'Sort', sorts, sort)}</div>`;
    if (B.days) h += `<p class="hv-head">All ${esc(GROUP[grp])}: ${num(B.days)} high days in ${num(B.runs)} runs of ${num(B.assets)} assets since ${esc(String(G.from || '').slice(0, 4))}. From a high day, the first 5% pullback came a median <b>${td((B.t5 || {}).median)}</b> later and the first 10% a median <b>${td((B.t10 || {}).median)}</b> later (${pc(((B.t10 || {}).p || {})['63'])} within 3 months, ${pc(((B.t10 || {}).p || {})['252'])} within 12); the run's peak came a median ${td((B.run_left || {}).median)} later, and the pullback that ended it was a median <b>${sp((B.pullback || {}).p50)}</b> (a quarter ${sp((B.pullback || {}).p25)} or worse).</p>`;
    o.exported = now.map((r) => ({ key: r.key, name: r.name, date: r.state.date, close: r.state.close, from_high: r.state.dd, run_start: r.state.run_start, run_days: r.state.age, highs63: r.state.highs63,
      above_200d: r.state.ext200, above_200d_pct: r.state.ext_pct, momentum: r.state.mom, momentum_pct: r.state.mom_pct, momentum_vs_companies: r.state.mom_xs, volatility_pct: r.state.vol_pct, pe: r.state.pe, pe_pct: r.state.pe_pct,
      volume_ratio: r.state.volu, analog_days_to_10pct: ((r.analogues || {}).t10 || {}).median, analog_10pct_within_3m: risk(r), analog_10pct_within_12m: ((((r.analogues || {}).t10) || {}).p || {})['252'],
      analog_days_to_peak: ((r.analogues || {}).run_left || {}).median, analog_pullback_median: ((r.analogues || {}).pullback || {}).p50 }));
    h += `<div class="section-head"><h3>At their highs now — ${num(now.length)} ${esc(GROUP[grp])}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
    const pct = (v, txt) => (fin(v) ? `<br><span class="m">${txt ? txt(v) : ord(v) + ' pct.'}</span>` : '');
    h += now.length ? table(['Asset', 'From the high · run', 'Highs, 63 days', 'Above 200-day', 'Momentum (own · all companies)', 'Volatility pct.', 'P/E', 'Volume', 'Similar days: 10% pullback (median) · within 3 · 12 months', 'To the run’s peak · the pullback after'],
      now.map((r) => { const S = r.state, A = r.analogues || {};
        return [`<button type="button" class="hv-k" data-hvk="${esc(r.key)}">${esc(r.key)}</button> <span class="m">${esc(String(r.name || '').slice(0, 30))}</span>`, `${S.dd === 0 ? 'at it' : sp(S.dd)}${S.run_start ? `<br><span class="m">${num(S.age)} d since ${esc(md(S.run_start))}</span>` : ''}`, num(S.highs63),
          `${sp(S.ext200, 0)}${pct(S.ext_pct)}`, `${sp(S.mom, 0)}${fin(S.mom_pct) || fin(S.mom_xs) ? `<br><span class="m">${ord(S.mom_pct)}${fin(S.mom_xs) ? ' · ' + ord(S.mom_xs) : ''}</span>` : ''}`, ord(S.vol_pct),
          fin(S.pe) ? `${num(S.pe, 1)}${pct(S.pe_pct)}` : '—', fin(S.volu) ? num(S.volu, 2) + '×' : '—',
          `${td((A.t10 || {}).median)}<br><span class="m">${pc(((A.t10 || {}).p || {})['63'])} · ${pc(((A.t10 || {}).p || {})['252'])}</span>`,
          `${td((A.run_left || {}).median)}<br><span class="hv-down">${sp((A.pullback || {}).p50)}</span>`];
      }), [0]) : '<p class="hv-sub">None at their highs on the last day.</p>';
    h += `<div id="hv-one" data-k="${esc(o.pick || '')}"></div>`;
    const fs = Object.keys(G.buckets || {});
    h += groupOdds(G, doc.params, 'highs', 'high day', GROUP[grp], ['mdd63', 'gain_left']);
    h += `<h3>By the state at the high — every high day of ${esc(GROUP[grp])}</h3><p class="hv-sub">Each row: the high days with the state in that range, how long until the first 5% and 10% pullback (Kaplan–Meier medians: the ones still waiting at the end of the data count for as long as they were watched), the rest of the run, the pullback that ended it and the next 12 months. The bar is the median days to a 10% pullback.</p>`;
    h += fs.map((f) => bucketTable(G, f)).join('');
    return h + '</div>';
  }

  /* ---------- at the lows and in a range (app/regimes.py) ---------- */
  const REG = { highs: 'At the highs', atl: 'At an all-time low', '52w': 'At a 52-week low', '3m': 'At a 3-month low', narrow: 'In a narrow range', wide: 'In a wide range' };
  const SPAN = { atl: 'all-time', '52w': '52-week', '3m': '3-month' };
  const A_N = (reg) => (reg === 'atl' ? 'an all-time' : 'a ' + SPAN[reg]);
  const LOWS = ['atl', '52w', '3m'], RANGES = ['narrow', 'wide'];
  const kindOf = (r) => (LOWS.includes(r) ? 'lows' : RANGES.includes(r) ? 'ranges' : 'highs');
  const p_ = (k, h) => ((k || {}).p || {})[h];
  const LFEAT = { age: 'the slide’s age', lows63: 'new lows in 63 days', dist: 'distance above the low', dd_ath: 'distance under the all-time high', ext_pct: 'against the 200-day average (own percentile)',
    mom_pct: 'momentum (own percentile)', vol_pct: 'volatility (own percentile)', pe_pct: 'P/E (own percentile)', volu: 'volume vs its year' };
  const RFEAT = { width: 'the range’s width', width_pct: 'its width against its own history', age: 'days in the range', pos: 'where the price sits in it', dd_ath: 'distance under the all-time high',
    ext200: 'against the 200-day average', vol_pct: 'volatility (own percentile)', pe_pct: 'P/E (own percentile)', volu: 'volume vs its year' };
  const common = (S, kind, add) => {
    add('Against its 200-day average', sp(S.ext200), S.ext_pct, fin(S.ext_pct) ? `${ord(S.ext_pct)} percentile of its own history` : 'under three years of history');
    add('12-1 month momentum', sp(S.mom, 0), S.mom_pct, (fin(S.mom_pct) ? `${ord(S.mom_pct)} pct. of its own` : '') + (fin(S.mom_xs) ? ` · ${ord(S.mom_xs)} among companies` : ''));
    add('Volatility, 21 days', fin(S.vol) ? pc(S.vol) + ' a year' : '—', S.vol_pct, fin(S.vol_pct) ? `${ord(S.vol_pct)} percentile (${S.vol_pct < 20 ? 'calm' : S.vol_pct > 80 ? 'stormy' : 'usual'})` : '');
    if (kind === 'stock' || fin(S.pe)) add('Trailing P/E', fin(S.pe) ? num(S.pe, 1) : '—', S.pe_pct, fin(S.pe_pct) ? `${ord(S.pe_pct)} percentile of its own` : fin(S.pe) ? 'under three years of P/E' : 'no positive four-quarter EPS on file');
    add('Volume, 3 months vs 12', fin(S.volu) ? num(S.volu, 2) + '×' : '—', null, fin(S.volu) ? (S.volu > 1.2 ? 'heavier than its year' : S.volu < 0.85 ? 'lighter than its year' : 'about its year') : 'no volume on file');
  };
  function lowTiles(S, kind, reg) {
    const T = [], add = (lab, val, p, note) => T.push(`<div class="hv-tile"><small>${esc(lab)}</small><b>${val}</b>${meter(p)}<i>${note}</i></div>`), lvl = kind === 'index' || kind === 'industry';
    add(`Above its ${SPAN[reg]} low`, fin(S.dist) ? (S.dist < 0.0005 ? 'at it' : sp(S.dist)) : '—', null, fin(S.low) ? `low ${money(S.low, lvl)}${S.low_date ? ' on ' + esc(md(S.low_date)) : ''}` : '');
    add(reg === 'atl' ? 'Since its all-time high' : `Since its last ${SPAN[reg]} high`, fin(S.age) ? td(S.age) : '—', null, S.since ? `${esc(mdy(S.since))}: the slide's age` : '');
    add(`New ${SPAN[reg]} lows, last 63 days`, num(S.lows63), fin(S.lows63) ? Math.min(100, 100 * S.lows63 / 63) : null, 'of 63 trading days');
    if (reg !== 'atl') add('Under its all-time high', sp(S.dd_ath, 0), null, '');
    common(S, kind, add);
    return `<div class="hv-tiles">${T.join('')}</div>`;
  }
  function rangeTiles(S, kind) {
    const T = [], add = (lab, val, p, note) => T.push(`<div class="hv-tile"><small>${esc(lab)}</small><b>${val}</b>${meter(p)}<i>${note}</i></div>`), lvl = kind === 'index' || kind === 'industry';
    add('The range’s width (63 days)', pc(S.width, 1), S.width_pct, fin(S.width_pct) ? `${ord(S.width_pct)} percentile of its own 63-day widths` : '');
    add('Between', `${money(S.lo, lvl)}–${money(S.hi, lvl)}`, null, 'the lowest and highest close');
    add('Where it sits in the range', fin(S.pos) ? pc(S.pos) : '—', fin(S.pos) ? 100 * S.pos : null, fin(S.pos) ? (S.pos < 1 / 3 ? 'the bottom third' : S.pos > 2 / 3 ? 'the top third' : 'the middle third') : '');
    add('In this range', td(S.age), null, S.since ? `since ${esc(mdy(S.since))}${fin(S.days_in) && S.days_in < S.age ? ` · ${num(S.days_in)} of them in the state` : ''}` : '');
    add('Under its all-time high', fin(S.dd_ath) ? (S.dd_ath > -0.0005 ? 'at it' : sp(S.dd_ath, 0)) : '—', null, '');
    common(S, kind, add);
    return `<div class="hv-tiles">${T.join('')}</div>`;
  }
  function lowHeadline(name, S, kind, reg) {
    const lvl = kind === 'index' || kind === 'industry';
    let h = `<b>${esc(name)}</b> closed at <b>${money(S.close, lvl)}</b> on ${esc(mdy(S.date))} — `;
    h += fin(S.dist) && S.dist < 0.0005 ? `<b>a new ${SPAN[reg]} low</b>` : `<b>${sp(S.dist)}</b> above its ${SPAN[reg]} low of ${money(S.low, lvl)}${S.low_date ? ` (${esc(md(S.low_date))})` : ''}`;
    if (reg !== 'atl' && fin(S.dd_ath)) h += `, ${pc(-S.dd_ath)} under its all-time high`;
    h += `. ${num(S.lows63)} new ${SPAN[reg]} low${S.lows63 === 1 ? '' : 's'} in the last 63 trading days; ${reg === 'atl' ? 'its all-time high' : `its last ${SPAN[reg]} high`} was ${S.since ? esc(mdy(S.since)) : 'long ago'} (${td(S.age)}).`;
    return `<p class="hv-head">${h}</p>`;
  }
  function rangeHeadline(name, S, kind, reg) {
    const lvl = kind === 'index' || kind === 'industry';
    return `<p class="hv-head"><b>${esc(name)}</b> closed at <b>${money(S.close, lvl)}</b> on ${esc(mdy(S.date))} — <b>${reg === 'narrow' ? 'in a narrow range' : 'in a wide range'}</b>: the last 63 trading days between ${money(S.lo, lvl)} and ${money(S.hi, lvl)} (${pc(S.width, 1)} wide, the ${ord(S.width_pct)} percentile of its own 63-day widths) with little net move, ${td(S.age)} in this state${S.since ? ` since ${esc(mdy(S.since))}` : ''}; it sits ${fin(S.pos) ? (S.pos < 1 / 3 ? 'in the bottom third' : S.pos > 2 / 3 ? 'in the top third' : 'in the middle third') : ''} of it.</p>`;
  }
  function lowFacts(A, reg) {
    const nl = A.next_low || {}, r10 = A.r10 || {}, r20 = A.r20 || {}, F = A.fall || {}, TD = A.trough_days || {}, B = A.bounce || {}, f3 = A.fwd63 || {}, f12 = A.fwd252 || {}, d3 = A.fall63 || {}, d12 = A.fall252 || {};
    const L = [];
    L.push(`<b>The next new ${SPAN[reg]} low</b>: median <b>${nl.median != null ? td(nl.median) : 'over a year'}</b> away — ${pc(p_(nl, '21'))} within a month, ${pc(p_(nl, '63'))} within 3 months, ${pc(p_(nl, '126'))} within 6, ${pc(p_(nl, '252'))} within 12.`);
    L.push(`<b>A 10% rebound</b> from the lowest close from that day on: median <b>${td(r10.median)}</b> (${pc(p_(r10, '21'))} within a month, ${pc(p_(r10, '63'))} within 3); <b>a 20% rebound</b>: median <b>${r20.median != null ? td(r20.median) : 'over a year'}</b> (${pc(p_(r20, '63'))} within 3 months, ${pc(p_(r20, '252'))} within 12).`);
    L.push(`<b>The low before the 10% rebound</b> came a median ${td(TD.p50)} later and <b>${sp(F.p50)}</b> from that day (a quarter ${sp(F.p25)} or worse, a tenth ${sp(F.p10)} or worse); ${pc(A.more_lows)} made another new ${SPAN[reg]} low on the way.`);
    L.push(`<b>The rebound from that low</b>, until the next new low or a year: median <b>${sp(B.p50)}</b> (25–75%: ${sp(B.p25)} to ${sp(B.p75)})${fin(A.bounce_open) && A.bounce_open > 0 ? `; ${pc(A.bounce_open)} had made no new low by then` : ''}.`);
    L.push(`<b>Returns</b>: 3 months <span class="${tone(f3.p50)}">${sp(f3.p50)}</span> median (${pc(f3.up)} up); 12 months <span class="${tone(f12.p50)}">${sp(f12.p50)}</span> median (${pc(f12.up)} up; 10–90%: ${sp(f12.p10)} to ${sp(f12.p90)}).`);
    L.push(`<b>The further fall</b>: the lowest close of the next 3 months a median <span class="hv-down">${sp(d3.p50)}</span> below that day's; of the next 12 months <span class="hv-down">${sp(d12.p50)}</span> (a quarter ${sp(d12.p25)} or worse).`);
    return `<ul class="hv-facts">${L.map((x) => `<li>${x}</li>`).join('')}</ul>`;
  }
  function rangeFacts(A) {
    const b = A.breakout || {}, f3 = A.fwd63 || {}, f12 = A.fwd252 || {}, w = (h) => A['within' + h] || {};
    const au = A.after63_up || {}, ad = A.after63_down || {}, au1 = A.after21_up || {}, ad1 = A.after21_down || {};
    const L = [];
    L.push(`<b>The breakout</b> (the first close above the range's high or under its low): median <b>${b.median != null ? td(b.median) : 'over a year'}</b> — ${pc(p_(b, '21'))} within a month, ${pc(p_(b, '63'))} within 3 months, ${pc(p_(b, '252'))} within 12.`);
    L.push(`<b>Which way</b>: <b>${pc(A.up_first)} up first</b>. Within a month ${pc(w(21).up)} had broken out up and ${pc(w(21).down)} down; within 3 months ${pc(w(63).up)} up, ${pc(w(63).down)} down.`);
    L.push(`<b>After an up-breakout</b>: 1 month <span class="${tone(au1.p50)}">${sp(au1.p50)}</span>, 3 months <span class="${tone(au.p50)}">${sp(au.p50)}</span> median; ${pc(A.failed_up)} fell back into the lower half of the range within a month (a false breakout).`);
    L.push(`<b>After a down-breakout</b>: 1 month <span class="${tone(ad1.p50)}">${sp(ad1.p50)}</span>, 3 months <span class="${tone(ad.p50)}">${sp(ad.p50)}</span> median; ${pc(A.failed_down)} climbed back into the upper half within a month.`);
    L.push(`<b>Returns</b>: 3 months <span class="${tone(f3.p50)}">${sp(f3.p50)}</span> median (${pc(f3.up)} up); 12 months <span class="${tone(f12.p50)}">${sp(f12.p50)}</span> (${pc(f12.up)} up; 10–90%: ${sp(f12.p10)} to ${sp(f12.p90)}). The highest close of the next 3 months a median ${sp((A.rise63 || {}).p50)} above, the lowest ${sp((A.fall63 || {}).p50)} below.`);
    return `<ul class="hv-facts">${L.map((x) => `<li>${x}</li>`).join('')}</ul>`;
  }
  const oddsRow = (lab, a, b) => [lab, ...['21', '63', '126', '252'].map((h) => `${pc(p_(a, h))}${b ? ` <span class="m">· ${pc(p_(b, h))}</span>` : ''}`), `${(a || {}).median != null ? td(a.median) : 'over a year'}${b ? ` <span class="m">· ${(b || {}).median != null ? num(b.median) : '—'}</span>` : ''}`];
  const NOTE = 'Adjusted closes (dividends reinvested). P/E: price ÷ the last four first-filed quarterly diluted EPS (SEC), positive only. Companies are today\'s (survivors), which flatters what came after their lows. Days in a regime overlap (one slide gives many low days), so the episodes and assets are given beside them. History, not a forecast.';
  function lowBlock(B, name, kind, base, groupKey, reg, opts = {}) {
    const S = B.state || {}, A = B.analogues;
    let h = lowHeadline(name, S, kind, reg) + lowTiles(S, kind, reg) + (opts.stand || '');
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar days at ${A_N(reg)} low</h3><p class="hv-sub">Low days (within 15% of the ${SPAN[reg]} low with a new one in the last 63 trading days) of ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} slides) nearest on ${esc((A.features || []).map((f) => LFEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year.${base ? ' After the dot: every low day of the group, for comparison.' : ''}</p>`;
      h += lowFacts(A, reg);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'no new low yet', curve: (A.next_low || {}).curve, col: 'var(--mk-cost,#c0392b)' }, { label: 'no 10% rebound yet', curve: (A.r10 || {}).curve, col: 'var(--mk-profit,#17734a)' },
        { label: 'no 20% rebound yet', curve: (A.r20 || {}).curve, col: 'var(--q-warm,#d9822b)' },
        ...(base ? [{ dash: true, label: 'no new low yet', curve: (base.next_low || {}).curve, col: 'var(--mk-cost,#c0392b)', who: GROUP[groupKey], what: 'low day' }, { dash: true, label: 'no 20% rebound yet', curve: (base.r20 || {}).curve, col: 'var(--q-warm,#d9822b)', who: GROUP[groupKey], what: 'low day' }] : [])],
      g, 'trading days after the low day', 'Survival curves: the share of low days not yet followed by a new low or a rebound');
      h += table(['Within', ...Object.values(HZW), 'Median'], [oddsRow(`A new ${SPAN[reg]} low`, A.next_low, base && base.next_low), oddsRow('A 10% rebound', A.r10, base && base.r10), oddsRow('A 20% rebound', A.r20, base && base.r20)], [0]);
      h += spreadBlock(A, opts.group, opts.params, `day at ${A_N(reg)} low`, ['fall63', 'bounce']);
      h += condBlock(S, A, opts.group, 'lows', `day at ${A_N(reg)} low`, GROUP[groupKey] || 'its kind');
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'The slide’s age', 'Under its high', 'To a 10% rebound', 'The low before it', 'The rebound after', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), td(e.age), sp(e.dd_ath, 0), e.r10 == null ? (e.seen >= 252 ? 'none in a year' : 'not yet') : td(e.r10), `<span class="${tone(e.fall)}">${sp(e.fall)}</span>`, `<span class="${tone(e.bounce)}">${sp(e.bounce)}</span>`, `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
      h += backtestBlock((opts.group || {}).backtest, 'lows', `day at ${A_N(reg)} low`, GROUP[groupKey] || 'its kind');
    } else h += `<p class="hv-sub">Too few similar low days with every state variable on file to compare.</p>`;
    return h + `<p class="hv-sub">${NOTE}</p>`;
  }
  function rangeBlock(B, name, kind, base, groupKey, reg, opts = {}) {
    const S = B.state || {}, A = B.analogues;
    let h = rangeHeadline(name, S, kind, reg) + rangeTiles(S, kind) + (opts.stand || '');
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar days in a ${reg} range</h3><p class="hv-sub">Days sideways over 63 trading days (the net move under a quarter of the range's width) with the width ${reg === 'narrow' ? 'in the bottom 15%' : 'in the top 30%'} of the asset's own, among ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} ranges), nearest on ${esc((A.features || []).map((f) => RFEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year.${base ? ' After the dot: every such day of the group.' : ''}</p>`;
      h += rangeFacts(A);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'still in the range (no breakout yet)', curve: (A.breakout || {}).curve, col: 'var(--accent,#1f6f4a)' },
        ...(base ? [{ dash: true, label: 'still in the range', curve: (base.breakout || {}).curve, col: 'var(--accent,#1f6f4a)', who: GROUP[groupKey], what: `day in a ${reg} range` }] : [])],
      g, 'trading days after the day in the range', 'Survival curve: the share of days in a range not yet followed by a breakout');
      const w = (X, h, d) => pc(((X || {})['within' + h] || {})[d]);
      h += table(['Within', ...Object.values(HZW), 'Median'], [oddsRow('A breakout, either way', A.breakout, base && base.breakout),
        ['Up first', ...['21', '63', '126', '252'].map((x) => `${w(A, x, 'up')}${base ? ` <span class="m">· ${w(base, x, 'up')}</span>` : ''}`), ''],
        ['Down first', ...['21', '63', '126', '252'].map((x) => `${w(A, x, 'down')}${base ? ` <span class="m">· ${w(base, x, 'down')}</span>` : ''}`), '']], [0]);
      h += spreadBlock(A, opts.group, opts.params, `day in a ${reg} range`, ['fall63', 'rise63']);
      h += condBlock(S, A, opts.group, 'ranges', `day in a ${reg} range`, GROUP[groupKey] || 'its kind');
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'Width', 'Days in it', 'Breakout', 'Which way', '3 months after it', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), pc(e.width, 1), num(e.age), e.brk == null ? (e.seen >= 252 ? 'none in a year' : 'not yet') : td(e.brk), e.up == null ? '—' : e.up ? '<span class="hv-up">up</span>' : '<span class="hv-down">down</span>',
        `<span class="${tone(e.after63)}">${sp(e.after63)}</span>`, `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
      h += backtestBlock((opts.group || {}).backtest, 'ranges', `day in a ${reg} range`, GROUP[groupKey] || 'its kind');
    } else h += `<p class="hv-sub">Too few similar days with every state variable on file to compare.</p>`;
    return h + `<p class="hv-sub">${NOTE.replace('after their lows', 'after these days').replace(' (one slide gives many low days)', '')}</p>`;
  }
  function lowBucket(G, f) {
    const b = G.buckets && G.buckets[f];
    if (!b) return '';
    const mx = Math.max(1, ...b.rows.map((r) => r.next_low_median || 0));
    return `<h4>${esc(b.title)}</h4>` + table(['', 'Low days · slides', 'Next new low: median days · within 3 months', '10% rebound: median days · within 3 months', '20% rebound (median days)', 'The low before the rebound · the rebound from it', '12 months: median · up', 'Lowest close of the 12 months'],
      b.rows.map((r) => !r.days ? [esc(r.label), '—', '', '', '', '', '', ''] : [esc(r.label), `${num(r.days)} · ${num(r.runs)}`,
        `<span class="hv-bar" style="width:${(50 * (r.next_low_median || 0) / mx).toFixed(0)}px"></span>${r.next_low_median == null ? '252+' : num(r.next_low_median)} · ${pc(r.next_low_p63)}`, `${num(r.r10_median)} · ${pc(r.r10_p63)}`, r.r20_median == null ? '252+' : num(r.r20_median),
        `<span class="hv-down">${sp(r.fall_median)}</span> · <span class="hv-up">${sp(r.bounce_median)}</span>`, `<span class="${tone(r.fwd252)}">${sp(r.fwd252)}</span> · ${pc(r.fwd252_up)}`, `<span class="hv-down">${sp(r.fall252)}</span>`]), [0]);
  }
  function rangeBucket(G, f) {
    const b = G.buckets && G.buckets[f];
    if (!b) return '';
    const mx = Math.max(1, ...b.rows.map((r) => r.breakout_median || 0));
    return `<h4>${esc(b.title)}</h4>` + table(['', 'Days · ranges', 'Breakout: median days · within 3 months', 'Up first', '3 months after an up · a down breakout', 'False breakouts: up · down', '12 months: median · up'],
      b.rows.map((r) => !r.days ? [esc(r.label), '—', '', '', '', '', ''] : [esc(r.label), `${num(r.days)} · ${num(r.runs)}`,
        `<span class="hv-bar" style="width:${(50 * (r.breakout_median || 0) / mx).toFixed(0)}px;background:var(--accent,#1f6f4a)"></span>${r.breakout_median == null ? '252+' : num(r.breakout_median)} · ${pc(r.breakout_p63)}`, pc(r.up_first),
        `<span class="${tone(r.after63_up)}">${sp(r.after63_up)}</span> · <span class="${tone(r.after63_down)}">${sp(r.after63_down)}</span>`, `${pc(r.failed_up)} · ${pc(r.failed_down)}`, `<span class="${tone(r.fwd252)}">${sp(r.fwd252)}</span> · ${pc(r.fwd252_up)}`]), [0]);
  }
  /* the hub: every day of the regime — its spread and the walk-forward test */
  function groupOdds(G, params, kind, what, who, extra) {
    if (!G || !G.base) return '';
    const A = Object.assign({}, G.base, { dist: G.dist, fan: G.fan });
    return spreadBlock(A, null, params, what, extra) + backtestBlock(G.backtest, kind, what, who);
  }
  const LIST_CAP = 50;
  const capped = (head, rows, cls, what) => (rows.length <= LIST_CAP + 10 ? table(head, rows, cls)
    : table(head, rows.slice(0, LIST_CAP), cls) + `<details class="hv-more"><summary>The other ${num(rows.length - LIST_CAP)} ${esc(what)}</summary>${table(head, rows.slice(LIST_CAP), cls)}</details>`);
  const fieldOf = (o) => o.field || ((id, lab, items, v) => `<label>${lab} <select id="${id}">${items.map(([k, l]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`);
  const assetCell = (r) => `<button type="button" class="hv-k" data-hvk="${esc(r.key)}">${esc(r.key)}</button> <span class="m">${esc(String(r.name || '').slice(0, 30))}</span>`;
  function lowsHub(doc, reg, o) {
    const R = ((doc.regimes || {})[reg]) || {}, st = o.state || {}, gs = Object.keys(R.groups || {});
    const grp = gs.includes(st.mvhg) ? st.mvhg : gs[0] || 'companies', G = (R.groups || {})[grp] || {}, B = G.base || {}, field = fieldOf(o);
    const sorts = [['dd_ath', 'Furthest under the all-time high'], ['dist', 'Closest to the low'], ['lows63', 'Most new lows in 63 days'], ['age', 'The longest slides'], ['mom_xs', 'Weakest momentum among companies'],
      ['pe_pct', 'Cheapest P/E against its own'], ['r20', 'Most likely to rebound 20% within 3 months'], ['next', 'Least likely to make a new low within 3 months']];
    const sort = sorts.some((s) => s[0] === st.mvhs) ? st.mvhs : 'dd_ath';
    const A_ = (r) => r.analogues || {};
    const key = { dd_ath: (r) => r.state.dd_ath ?? 0, dist: (r) => r.state.dist ?? 9, lows63: (r) => -(r.state.lows63 || 0), age: (r) => -(r.state.age || 0), mom_xs: (r) => r.state.mom_xs ?? 999, pe_pct: (r) => r.state.pe_pct ?? 999,
      r20: (r) => -(p_(A_(r).r20, '63') ?? -1), next: (r) => p_(A_(r).next_low, '63') ?? 9 }[sort];
    const now = ((doc.now || {})[reg] || []).filter((r) => r.group === grp).sort((a, b) => key(a) - key(b) || String(a.key).localeCompare(String(b.key)));
    let h = `<div class="hv"><p class="hv-sub">An asset runs at its ${SPAN[reg]} low when it closes within 15% of that low with a new one in the last 63 trading days${reg === '3m' ? ' (the bottom of its recent range)' : ''}. Every such day since the data begins is counted with the state the asset was in — the slide's age (since its last ${reg === 'atl' ? 'all-time' : SPAN[reg]} high), new lows in the last quarter, how far under its all-time high and its 200-day average, momentum, volatility, P/E and volume — and what followed: the days to the next new low, to a 10% and a 20% rebound, the low before the rebound, how far the rebound went and the next 12 months. ${esc(doc.note || '')}</p>`;
    h += `<div class="toolbar">${field('mvhg', 'Assets', gs.map((g) => [g, (R.groups[g] || {}).label || g]), grp)}${field('mvhs', 'Sort', sorts, sort)}</div>`;
    if (B.days) h += `<p class="hv-head">All ${esc(GROUP[grp])}: ${num(B.days)} days at ${A_N(reg)} low in ${num(B.runs)} slides of ${num(B.assets)} assets. The next new low came a median <b>${(B.next_low || {}).median != null ? td(B.next_low.median) : 'over a year'}</b> later (${pc(p_(B.next_low, '63'))} within 3 months); a 10% rebound a median <b>${td((B.r10 || {}).median)}</b> later, a 20% one ${(B.r20 || {}).median != null ? td(B.r20.median) : 'over a year'} later; the rebound from the low before it a median <b>${sp((B.bounce || {}).p50)}</b>; 12 months later a median <span class="${tone((B.fwd252 || {}).p50)}">${sp((B.fwd252 || {}).p50)}</span> (${pc((B.fwd252 || {}).up)} up), the lowest close of the year a median ${sp((B.fall252 || {}).p50)} below.</p>`;
    o.exported = now.map((r) => ({ key: r.key, name: r.name, date: r.state.date, close: r.state.close, above_low: r.state.dist, low: r.state.low, low_date: r.state.low_date, since_high: r.state.since, slide_days: r.state.age, lows63: r.state.lows63,
      under_ath: r.state.dd_ath, vs_200d: r.state.ext200, momentum: r.state.mom, momentum_pct: r.state.mom_pct, momentum_vs_companies: r.state.mom_xs, volatility_pct: r.state.vol_pct, pe: r.state.pe, pe_pct: r.state.pe_pct, volume_ratio: r.state.volu,
      analog_days_to_new_low: (A_(r).next_low || {}).median, analog_new_low_within_3m: p_(A_(r).next_low, '63'), analog_days_to_20pct_rebound: (A_(r).r20 || {}).median, analog_20pct_within_3m: p_(A_(r).r20, '63'),
      analog_rebound_median: (A_(r).bounce || {}).p50, analog_12m_median: (A_(r).fwd252 || {}).p50, analog_12m_up: (A_(r).fwd252 || {}).up }));
    h += `<div class="section-head"><h3>At ${A_N(reg)} low now — ${num(now.length)} ${esc(GROUP[grp])}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
    const pct = (v) => (fin(v) ? `<br><span class="m">${ord(v)} pct.</span>` : '');
    h += now.length ? capped(['Asset', 'Above the low · its day', 'Under its high · the slide', 'Lows, 63 days', 'Momentum (own · all companies)', 'P/E', 'Similar days: next new low (median) · within 3 months', '20% rebound (median) · the rebound', '12 months: median · up'],
      now.map((r) => { const S = r.state, A = A_(r);
        return [assetCell(r), `${S.dist < 0.0005 ? 'at it' : sp(S.dist)}${S.low_date ? `<br><span class="m">${esc(md(S.low_date))}</span>` : ''}`, `${sp(S.dd_ath, 0)}<br><span class="m">${num(S.age)} d</span>`, num(S.lows63),
          `${sp(S.mom, 0)}${fin(S.mom_pct) || fin(S.mom_xs) ? `<br><span class="m">${ord(S.mom_pct)}${fin(S.mom_xs) ? ' · ' + ord(S.mom_xs) : ''}</span>` : ''}`, fin(S.pe) ? `${num(S.pe, 1)}${pct(S.pe_pct)}` : '—',
          `${(A.next_low || {}).median != null ? td(A.next_low.median) : A.next_low ? 'over a year' : '—'}<br><span class="m">${pc(p_(A.next_low, '63'))}</span>`, `${(A.r20 || {}).median != null ? td(A.r20.median) : '—'}<br><span class="hv-up">${sp((A.bounce || {}).p50)}</span>`,
          `<span class="${tone((A.fwd252 || {}).p50)}">${sp((A.fwd252 || {}).p50)}</span><br><span class="m">${pc((A.fwd252 || {}).up)}</span>`];
      }), [0], GROUP[grp]) : `<p class="hv-sub">None at ${A_N(reg)} low on the last day.</p>`;
    h += `<div id="hv-one" data-k="${esc(o.pick || '')}" data-r="${esc(reg)}"></div>`;
    h += groupOdds(G, doc.params, 'lows', `day at ${A_N(reg)} low`, GROUP[grp], ['fall63', 'bounce']);
    h += `<h3>By the state at the low — every day at ${A_N(reg)} low of ${esc(GROUP[grp])}</h3><p class="hv-sub">Each row: the low days with the state in that range, how long until the next new low and a 10% and 20% rebound (Kaplan–Meier medians: the ones still waiting at the end of the data count for as long as they were watched; 252+ = over a year), the low before the rebound and the rebound from it, and the next 12 months. The bar is the median days to the next new low.</p>`;
    return h + Object.keys(G.buckets || {}).map((f) => lowBucket(G, f)).join('') + '</div>';
  }
  function rangesHub(doc, reg, o) {
    const R = ((doc.regimes || {})[reg]) || {}, st = o.state || {}, gs = Object.keys(R.groups || {});
    const grp = gs.includes(st.mvhg) ? st.mvhg : gs[0] || 'companies', G = (R.groups || {})[grp] || {}, B = G.base || {}, field = fieldOf(o);
    const sorts = [['width', reg === 'narrow' ? 'The narrowest' : 'The widest'], ['width_pct', 'Most extreme width against its own'], ['age', 'Longest in the range'], ['pos', 'Nearest the top of the range'], ['low', 'Nearest the bottom of the range'],
      ['brk', 'Soonest breakout (similar days)'], ['up', 'Most often up first (similar days)']];
    const sort = sorts.some((s) => s[0] === st.mvhs) ? st.mvhs : 'width';
    const A_ = (r) => r.analogues || {};
    const key = { width: (r) => (r.state.width ?? 9) * (reg === 'narrow' ? 1 : -1), width_pct: (r) => (reg === 'narrow' ? r.state.width_pct ?? 999 : -(r.state.width_pct ?? -1)), age: (r) => -(r.state.age || 0), pos: (r) => -(r.state.pos ?? -1), low: (r) => r.state.pos ?? 9,
      brk: (r) => (A_(r).breakout || {}).median ?? 999, up: (r) => -(A_(r).up_first ?? -1) }[sort];
    const now = ((doc.now || {})[reg] || []).filter((r) => r.group === grp).sort((a, b) => key(a) - key(b) || String(a.key).localeCompare(String(b.key)));
    let h = `<div class="hv"><p class="hv-sub">An asset is in a ${reg} range when its last 63 trading days went sideways (the net move under a quarter of the range's width, high ÷ low) and that width is ${reg === 'narrow' ? 'in the bottom 15% of its own 63-day widths — a tight coil' : 'in the top 30% of its own — wide swings that go nowhere'}. Every such day is counted with the state the asset was in and what followed: the days to the first close outside the range (the breakout), which way, the move 1 and 3 months after it, how often it fell back into the range (a false breakout) and the next 12 months. ${esc(doc.note || '')}</p>`;
    h += `<div class="toolbar">${field('mvhg', 'Assets', gs.map((g) => [g, (R.groups[g] || {}).label || g]), grp)}${field('mvhs', 'Sort', sorts, sort)}</div>`;
    if (B.days) h += `<p class="hv-head">All ${esc(GROUP[grp])}: ${num(B.days)} days in a ${reg} range in ${num(B.runs)} ranges of ${num(B.assets)} assets. The breakout came a median <b>${(B.breakout || {}).median != null ? td(B.breakout.median) : 'over a year'}</b> later (${pc(p_(B.breakout, '21'))} within a month, ${pc(p_(B.breakout, '63'))} within 3); <b>${pc(B.up_first)} broke out up first</b>. 3 months after an up-breakout a median <span class="${tone((B.after63_up || {}).p50)}">${sp((B.after63_up || {}).p50)}</span>, after a down-breakout <span class="${tone((B.after63_down || {}).p50)}">${sp((B.after63_down || {}).p50)}</span>; false breakouts ${pc(B.failed_up)} up, ${pc(B.failed_down)} down.</p>`;
    o.exported = now.map((r) => ({ key: r.key, name: r.name, date: r.state.date, close: r.state.close, range_low: r.state.lo, range_high: r.state.hi, width: r.state.width, width_pct: r.state.width_pct, position: r.state.pos, days_in_range: r.state.age,
      under_ath: r.state.dd_ath, vs_200d: r.state.ext200, volatility_pct: r.state.vol_pct, pe: r.state.pe, pe_pct: r.state.pe_pct, volume_ratio: r.state.volu, analog_days_to_breakout: (A_(r).breakout || {}).median,
      analog_breakout_within_3m: p_(A_(r).breakout, '63'), analog_up_first: A_(r).up_first, analog_3m_after_up: (A_(r).after63_up || {}).p50, analog_3m_after_down: (A_(r).after63_down || {}).p50, analog_12m_median: (A_(r).fwd252 || {}).p50 }));
    h += `<div class="section-head"><h3>In a ${reg} range now — ${num(now.length)} ${esc(GROUP[grp])}</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
    h += now.length ? capped(['Asset', 'Width · own pct.', 'The range', 'Where it sits', 'Days in it', 'Under its high', 'Similar days: breakout (median) · within 3 months', 'Up first', '3 months after up · down', '12 months: median · up'],
      now.map((r) => { const S = r.state, A = A_(r), lvl = r.kind === 'index' || r.kind === 'industry';
        return [assetCell(r), `${pc(S.width, 1)}<br><span class="m">${ord(S.width_pct)}</span>`, `${money(S.lo, lvl)}–${money(S.hi, lvl)}`, fin(S.pos) ? pc(S.pos) : '—', num(S.age), fin(S.dd_ath) ? sp(S.dd_ath, 0) : '—',
          `${(A.breakout || {}).median != null ? td(A.breakout.median) : A.breakout ? 'over a year' : '—'}<br><span class="m">${pc(p_(A.breakout, '63'))}</span>`, pc(A.up_first),
          `<span class="${tone((A.after63_up || {}).p50)}">${sp((A.after63_up || {}).p50)}</span> · <span class="${tone((A.after63_down || {}).p50)}">${sp((A.after63_down || {}).p50)}</span>`,
          `<span class="${tone((A.fwd252 || {}).p50)}">${sp((A.fwd252 || {}).p50)}</span><br><span class="m">${pc((A.fwd252 || {}).up)}</span>`];
      }), [0], GROUP[grp]) : `<p class="hv-sub">None in a ${reg} range on the last day.</p>`;
    h += `<div id="hv-one" data-k="${esc(o.pick || '')}" data-r="${esc(reg)}"></div>`;
    h += groupOdds(G, doc.params, 'ranges', `day in a ${reg} range`, GROUP[grp], ['fall63', 'rise63']);
    h += `<h3>By the state in the range — every day in a ${reg} range of ${esc(GROUP[grp])}</h3><p class="hv-sub">Each row: the days with the state in that range, how long until the breakout (a Kaplan–Meier median; 252+ = over a year), which way it went first, the move 3 months after it, how often it failed (back into the other half of the range within a month) and the next 12 months. The bar is the median days to the breakout.</p>`;
    return h + Object.keys(G.buckets || {}).map((f) => rangeBucket(G, f)).join('') + '</div>';
  }
  /* the regimes an asset's file has now: highs always (its runs), the lows and ranges it is in */
  function regimesOf(doc) {
    const out = [];
    if (doc.highs) out.push('highs');
    for (const r of LOWS) if (doc.lows && doc.lows[r]) out.push(r);
    for (const r of RANGES) if (doc.ranges && doc.ranges[r]) out.push(r);
    return out;
  }
  function pickRegime(doc, want) {
    const rs = regimesOf(doc);
    if (want && rs.includes(want)) return want;
    if (doc.highs && (doc.highs.state || {}).high) return 'highs';
    return rs.find((r) => r !== 'highs') || rs[0] || 'highs';
  }
  function chips(doc, reg) {
    const rs = regimesOf(doc);
    if (rs.length < 2) return '';
    return `<div class="hv-chips" role="tablist">${rs.map((r) => `<button type="button" class="hv-chip${r === reg ? ' on' : ''}" data-hvr="${r}" role="tab" aria-selected="${r === reg}">${esc(REG[r])}${r === 'highs' && !((doc.highs || {}).state || {}).high ? '<small>not now: its runs</small>' : ''}</button>`).join('')}</div>`;
  }

  /* ---------- a picture to share: the chosen panels in one PNG, drawn as the Move odds picture is (cards on a light
     page, a title and a line on what was compared, the source and the site at the foot) ---------- */
  const PIC = {
    highs: [['now', 'Where it stands'], ['odds', 'How long the run lasts'], ['fan', 'The next year'], ['fwd21', '1 month on'], ['fwd63', '3 months on'], ['fwd252', '12 months on'], ['mdd63', 'Largest fall in 3 months'], ['gain_left', 'Gain left to the peak'], ['own', 'Its own runs']],
    lows: [['now', 'Where it stands'], ['odds', 'New low or rebound'], ['fan', 'The next year'], ['fwd21', '1 month on'], ['fwd63', '3 months on'], ['fwd252', '12 months on'], ['fall63', 'Lowest close in 3 months'], ['bounce', 'The rebound']],
    ranges: [['now', 'Where it stands'], ['odds', 'When it breaks out'], ['fan', 'The next year'], ['fwd21', '1 month on'], ['fwd63', '3 months on'], ['fwd252', '12 months on'], ['fall63', 'Lowest close in 3 months'], ['rise63', 'Highest close in 3 months']],
  };
  const PIC_WIDE = ['now', 'odds', 'fan'], PIC_DEFAULT = ['now', 'odds', 'fwd63', 'fwd252'], PICKS = {};
  const PCv = { bg: '#fcfcfb', card: '#ffffff', ink: '#1d1d1b', ink2: '#3d3c39', muted: '#6b6a66', line: '#e3e1dc', up: '#17734a', down: '#c0392b', warn: '#d9822b', accent: '#1f6f4a', grey: '#9a9893' };
  const PCOL = { ink: PCv.ink, up: PCv.up, down: PCv.down, accent: PCv.accent, muted: PCv.muted };
  function oddsLines(P) {
    const A = P.A || {}, B = P.base || {};
    if (P.kind === 'highs') return [{ label: 'no 5% pullback yet', q: A.t5, b: B.t5, col: PCv.warn }, { label: 'no 10% pullback yet', q: A.t10, b: B.t10, col: PCv.down }, { label: 'the run still ahead of its peak', q: A.run_left, col: PCv.up }];
    if (P.kind === 'lows') return [{ label: `no new ${SPAN[P.reg]} low yet`, q: A.next_low, b: B.next_low, col: PCv.down }, { label: 'no 10% rebound yet', q: A.r10, b: B.r10, col: PCv.up }, { label: 'no 20% rebound yet', q: A.r20, b: B.r20, col: PCv.warn }];
    return [{ label: 'still in the range (no breakout yet)', q: A.breakout, b: B.breakout, col: PCv.accent }];
  }
  const picWhat = (P) => (P.kind === 'highs' ? 'high day' : P.kind === 'lows' ? `day at ${A_N(P.reg)} low` : `day in a ${P.reg} range`);
  function canPic(P, k) {
    const A = P.A || {}, E = (P.params || {}).edges || {};
    if (k === 'now') return !!P.M;
    if (k === 'odds') return !!(A.days && oddsLines(P).some((l) => l.q && l.q.curve));
    if (k === 'fan') return !!(A.fan && A.fan.p50);
    if (k === 'own') return P.kind === 'highs' && !!(P.own && (P.own.last || []).length);
    return !!(A.dist && A.dist[k] && E[k]);
  }
  /* rows: the wide panels alone, in order; the rest two to a row */
  function picRows(P, picks) {
    const order = PIC[P.kind].map(([k]) => k).filter((k) => picks.includes(k) && canPic(P, k));
    const rows = [], rest = [];
    for (const k of order) (PIC_WIDE.includes(k) ? rows : rest).push(k);
    const out = rows.map((k) => [k]);
    for (let i = 0; i < rest.length; i += 2) out.push(rest.slice(i, i + 2));
    return out;
  }
  function picTitle(P) {
    const S = P.S || {}, tk = P.doc.kind === 'stock' ? P.doc.ticker || P.doc.key : P.doc.name || P.doc.key;
    if (P.kind === 'highs') {
      if (!S.high) return `${tk}: ${sp(S.dd)} from its all-time high of ${md(S.ath_date)}`;
      return S.dd > -0.0005 ? `${tk} at an all-time high: ${num(S.age)} trading days into a run, ${num(S.run_highs)} new highs`
        : `${tk} ${sp(S.dd).replace('−', '')} under its all-time high, ${num(S.age)} trading days into a run of highs`;
    }
    if (P.kind === 'lows') return S.dist < 0.0005 ? `${tk} at a new ${SPAN[P.reg]} low — ${num(S.lows63)} in the last 63 trading days`
      : `${tk} ${sp(S.dist).replace('+', '')} above its ${SPAN[P.reg]} low, ${num(S.lows63)} new lows in 63 days`;
    return `${tk} in a ${P.reg} range: ${pc(S.width, 1)} wide over 63 trading days, ${S.pos < 1 / 3 ? 'in the bottom third' : S.pos > 2 / 3 ? 'in the top third' : 'in the middle'} of it`;
  }
  function picSub(P) {
    const S = P.S || {}, A = P.A || {}, who = GROUP[P.gk] || 'its kind', lvl = P.doc.kind === 'index' || P.doc.kind === 'industry';
    return `${P.doc.name || P.doc.key} · closed ${money(S.close, lvl)} on ${mdy(S.date)}${A.days ? ` · what followed the ${num(A.days)} most similar ${plural(picWhat(P))} of ${who} (${num(A.assets)} assets), beside every ${picWhat(P)} of them` : ''}`;
  }
  function pFont(px, wt) { return `${wt || 400} ${px}px "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif`; }
  function pRect(x, X, Y, w, h, r) { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); }
  function pCard(x, X, Y, w, h, title, sub) {
    x.fillStyle = PCv.card; pRect(x, X, Y, w, h, 12); x.fill(); x.strokeStyle = PCv.line; x.lineWidth = 1; x.stroke();
    x.fillStyle = PCv.ink; x.font = pFont(17, 600); x.textBaseline = 'alphabetic'; x.textAlign = 'left'; x.fillText(title, X + 16, Y + 28);
    if (sub) { x.fillStyle = PCv.muted; x.font = pFont(12.5); x.fillText(fitText(x, sub, w - 32), X + 16, Y + 47); }
    return { x: X + 16, y: Y + (sub ? 62 : 46), w: w - 32, h: h - (sub ? 62 : 46) - 14 };
  }
  function fitText(x, t, w) { if (x.measureText(t).width <= w) return t; let s = t; while (s.length > 4 && x.measureText(s + '…').width > w) s = s.slice(0, -1); return s.replace(/[\s·,;:]+$/, '') + '…'; }
  function pLabel(x, text, X, Y, col, font, align) {
    x.font = font || pFont(13, 600); x.textAlign = align || 'left'; x.lineWidth = 4; x.strokeStyle = PCv.card; x.lineJoin = 'round';
    x.strokeText(text, X, Y); x.fillStyle = col || PCv.ink; x.fillText(text, X, Y); x.textAlign = 'left';
  }
  function pLine(x, pts, col, lw, dash) { if (pts.length < 2) return; x.save(); x.strokeStyle = col; x.lineWidth = lw || 2; x.lineJoin = 'round'; x.lineCap = 'round'; if (dash) x.setLineDash(dash); x.beginPath(); pts.forEach(([a, b], i) => (i ? x.lineTo(a, b) : x.moveTo(a, b))); x.stroke(); x.restore(); }
  function pHline(x, X0, X1, Y, col, dash, lw) { pLine(x, [[X0, Y], [X1, Y]], col, lw || 1, dash); }
  /* a legend line at the top of a card: a swatch, the words in ink, more in grey */
  function pKey(x, P0, y, col, t1, t2, dash) {
    x.save(); x.strokeStyle = col; x.lineWidth = dash ? 2 : 4; if (dash) x.setLineDash([4, 3]); x.beginPath(); x.moveTo(P0.x, y - 7); x.lineTo(P0.x + 14, y - 7); x.stroke(); x.restore();
    x.font = pFont(13, 600); x.fillStyle = PCv.ink; x.fillText(t1, P0.x + 20, y - 3);
    if (t2) { const w1 = x.measureText(t1).width; x.font = pFont(13); x.fillStyle = PCv.ink2; x.fillText(fitText(x, t2, P0.w - w1 - 28), P0.x + 26 + w1, y - 3); }
  }
  function drawStand(x, box, P) {
    const M = P.M, yrs = (M.N - M.from) / 252, over = yrs > 2.5 ? 'the last three years' : yrs > 1.5 ? 'the last two years' : yrs > 0.75 ? 'the last year' : 'the last six months';
    const R0 = pCard(x, box.x, box.y, box.w, box.h, `Where it stands: the close over ${over}`, M.kind === 'highs' ? 'dashed: the all-time high · dotted: 10% under it, where a pullback ends a run · dots: new all-time highs · shaded: this run'
      : M.kind === 'lows' ? `dashed: the ${SPAN[M.reg]} low · dotted: 10% and 20% above it (a rebound) · dots: new ${SPAN[M.reg]} lows · shaded: the slide` : 'shaded: the range of the last 63 trading days · a close above its top or under its bottom: the breakout');
    const L = R0.x + 62, Rr = R0.x + R0.w - 128, T = R0.y + 8, B = R0.y + R0.h - 24, span = Math.max(1, M.N - 1 - M.from);
    const sx = (i) => L + ((i - M.from) / span) * (Rr - L);
    const sy = M.log ? (v) => T + ((Math.log(M.hi) - Math.log(v)) / (Math.log(M.hi) - Math.log(M.lo))) * (B - T) : (v) => T + ((M.hi - v) / (M.hi - M.lo)) * (B - T);
    if (M.shade) {
      x.save(); x.fillStyle = PCOL[M.shade.col]; x.globalAlpha = M.shade.box ? 0.1 : 0.07;
      const x0 = sx(M.shade.i0);
      if (M.shade.box) x.fillRect(x0, sy(M.shade.box[1]), Rr - x0, Math.max(1, sy(M.shade.box[0]) - sy(M.shade.box[1]))); else x.fillRect(x0, T, Rr - x0, B - T);
      x.restore();
    }
    x.font = pFont(12); x.fillStyle = PCv.muted; x.textAlign = 'right';
    for (const v of priceTicks(M.lo, M.hi, M.log)) { pHline(x, L, Rr, sy(v), PCv.line); x.fillStyle = PCv.muted; x.font = pFont(12); x.textAlign = 'right'; x.fillText(axisMoney(v, M.lvl), L - 8, sy(v) + 4); }
    x.textAlign = 'center';
    for (const t of monthTicks(M.days, M.from, M.N, 9)) { x.fillStyle = PCv.muted; x.font = pFont(12); x.fillText(t.text, sx(t.i), B + 18); }
    x.textAlign = 'left';
    for (const l of M.lv) if (fin(l.v) && l.v >= M.lo && l.v <= M.hi) pHline(x, l.i0 != null ? sx(l.i0) : L, Rr, sy(l.v), PCOL[l.col], l.dash.split(' ').map(Number), 1.5);
    x.save(); x.beginPath(); x.rect(L, T, Rr - L + 6, B - T); x.clip();
    const pts = [];
    for (let i = M.from; i < M.N; i++) pts.push([sx(i), sy(M.close[i])]);
    pLine(x, pts, PCv.ink, 2);
    x.restore();
    const mc = M.kind === 'highs' ? PCv.up : PCv.down;
    for (const i of M.marks) { x.fillStyle = mc; x.beginPath(); x.arc(sx(i), sy(M.close[i]), 3, 0, 7); x.fill(); }
    for (const { l, y } of levelWords(M, sy, T, B)) pLabel(x, l.text, (l.i0 != null ? sx(l.i0) : L) + 8, y, PCOL[l.col], pFont(12.5, 600));
    const xe = sx(M.N - 1), ye = sy(M.last), ly = Math.min(Math.max(ye, T + 12), B - (M.label ? 34 : 4));
    x.fillStyle = PCv.ink; x.beginPath(); x.arc(xe, ye, 5, 0, 7); x.fill(); x.strokeStyle = PCv.card; x.lineWidth = 2; x.stroke();
    x.fillStyle = PCv.ink; x.font = pFont(16, 700); x.fillText(money(M.last, M.lvl), xe + 12, ly + 5);
    if (M.label) { x.font = pFont(13.5, 600); x.fillText(M.label[0], xe + 12, ly + 22); x.fillStyle = PCv.muted; x.font = pFont(13); x.fillText(M.label[1], xe + 12, ly + 38); }
  }
  function drawOdds(x, box, P) {
    const A = P.A || {}, who = GROUP[P.gk] || 'its kind', lines = oddsLines(P).filter((l) => l.q && l.q.curve), grid = ((P.params || {}).grid) || Array.from({ length: 37 }, (_, i) => i * 7);
    const title = P.kind === 'highs' ? 'How long the run lasts: the share of days not yet followed by…' : P.kind === 'lows' ? 'A new low or a rebound: the share of days not yet followed by…' : 'When it breaks out: the share of days still in the range';
    const R0 = pCard(x, box.x, box.y, box.w, box.h, title, `the ${num(A.days)} most similar ${plural(picWhat(P))} of ${who} · dashed: every ${picWhat(P)} of them · the dot: half of them by then`);
    let ky = R0.y + 14;
    for (const l of lines) {
      const q = l.q, w = (h) => pc(((q.p || {})[h]));
      pKey(x, R0, ky, l.col, `${l.label}: ${q.median != null ? `median ${num(q.median)} trading days` : 'most not within a year'}`, `· ${w('21')} within a month · ${w('63')} within 3 · ${w('252')} within 12${l.b && l.b.median != null ? ` · every day: median ${num(l.b.median)}` : ''}`);
      ky += 20;
    }
    const L = R0.x + 44, Rr = R0.x + R0.w - 10, T = ky + 4, B = R0.y + R0.h - 22, gx = grid[grid.length - 1];
    const sx = (d) => L + (d / gx) * (Rr - L), sy = (v) => T + (1 - v) * (B - T);
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { pHline(x, L, Rr, sy(v), v === 0.5 ? PCv.grey : PCv.line, v === 0.5 ? [2, 3] : null); x.fillStyle = PCv.muted; x.font = pFont(12); x.textAlign = 'right'; x.fillText(pc(v), L - 8, sy(v) + 4); x.textAlign = 'left'; });
    x.textAlign = 'center';
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { x.fillStyle = PCv.muted; x.font = pFont(12); x.textAlign = d === 0 ? 'left' : d === gx ? 'right' : 'center'; x.fillText(d === 0 ? 'the day' : d === 21 ? '1 month' : d === 63 ? '3 months' : d === 126 ? '6 months' : d === 189 ? '9 months' : '12 months', sx(d), B + 18); });
    x.textAlign = 'left';
    for (const l of lines) if (l.b && l.b.curve) pLine(x, l.b.curve.map((v, i) => (fin(v) ? [sx(grid[i]), sy(v)] : null)).filter(Boolean), l.col, 1.4, [5, 4]);
    for (const l of lines) pLine(x, l.q.curve.map((v, i) => (fin(v) ? [sx(grid[i]), sy(v)] : null)).filter(Boolean), l.col, 2.6);
    for (const l of lines) { const m = half(l.q.curve, grid); if (m != null) { x.fillStyle = l.col; x.beginPath(); x.arc(sx(m), sy(0.5), 5, 0, 7); x.fill(); x.strokeStyle = PCv.card; x.lineWidth = 2; x.stroke(); } }
  }
  function drawFan(x, box, P) {
    const A = P.A || {}, F = A.fan, Fb = (P.G || {}).fan, grid = ((P.params || {}).fan_grid && P.params.fan_grid.length === F.p50.length) ? P.params.fan_grid : F.p50.map((_, i) => i * 7);
    const R0 = pCard(x, box.x, box.y, box.w, box.h, 'The next year: the return from the day', `the ${num(A.days)} most similar ${plural(picWhat(P))}: the middle half, eight in ten and the median · dashed: the median of every ${picWhat(P)}`);
    const vals = [...F.p10, ...F.p90, ...((Fb && Fb.p50) || [])].filter(fin);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals); const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const L = R0.x + 50, Rr = R0.x + R0.w - 70, T = R0.y + 6, B = R0.y + R0.h - 22, gx = grid[grid.length - 1];
    const sx = (d) => L + (d / gx) * (Rr - L), sy = (v) => T + ((hi - v) / (hi - lo)) * (B - T);
    const st = niceStep(hi - lo);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) { pHline(x, L, Rr, sy(v), Math.abs(v) < 1e-9 ? PCv.grey : PCv.line); x.fillStyle = PCv.muted; x.font = pFont(12); x.textAlign = 'right'; x.fillText(pct0(Math.abs(v) < 1e-9 ? 0 : v) || '0%', L - 8, sy(v) + 4); x.textAlign = 'left'; }
    x.textAlign = 'center';
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { x.fillStyle = PCv.muted; x.font = pFont(12); x.fillText(d === 0 ? 'the day' : d === 21 ? '1 month' : d === 63 ? '3 months' : d === 126 ? '6 months' : d === 189 ? '9 months' : '12 months', sx(d), B + 18); });
    x.textAlign = 'left';
    const band = (a, b, op) => { const up = [], dn = []; grid.forEach((g, i) => { if (fin(a[i]) && fin(b[i])) { up.push([sx(g), sy(b[i])]); dn.unshift([sx(g), sy(a[i])]); } }); if (up.length < 2) return;
      x.save(); x.globalAlpha = op; x.fillStyle = PCv.accent; x.beginPath(); up.concat(dn).forEach(([a1, b1], i) => (i ? x.lineTo(a1, b1) : x.moveTo(a1, b1))); x.closePath(); x.fill(); x.restore(); };
    band(F.p10, F.p90, 0.12); band(F.p25, F.p75, 0.24);
    if (Fb && Fb.p50) pLine(x, grid.map((g, i) => (fin(Fb.p50[i]) ? [sx(g), sy(Fb.p50[i])] : null)).filter(Boolean), PCv.ink2, 1.5, [5, 4]);
    pLine(x, grid.map((g, i) => (fin(F.p50[i]) ? [sx(g), sy(F.p50[i])] : null)).filter(Boolean), PCv.accent, 2.6);
    const e = F.p50.length - 1;
    if (fin(F.p50[e])) pLabel(x, `median ${pct0(F.p50[e]) || '0%'}`, sx(grid[e]) + 8, sy(F.p50[e]) + 4, PCv.accent, pFont(13, 650));
    if (fin(F.p75[e])) pLabel(x, pct0(F.p75[e]), sx(grid[e]) + 8, sy(F.p75[e]) + 4, PCv.muted, pFont(12));
    if (fin(F.p25[e])) pLabel(x, pct0(F.p25[e]), sx(grid[e]) + 8, sy(F.p25[e]) + 4, PCv.muted, pFont(12));
  }
  function drawHist(x, box, P, k) {
    const A = P.A || {}, E = P.params.edges[k], counts = A.dist[k], base = ((P.G || {}).dist || {})[k], q = A[k] || {};
    const n = counts.reduce((a, b) => a + b, 0), nb = (base || []).reduce((a, b) => a + b, 0), K = counts.length;
    const sub = `${fin(q.p50) ? `median ${pct0(q.p50) || '0%'}` : ''}${fin(q.up) && k.startsWith('fwd') ? ` · ${pc(q.up)} up` : ''}${nb ? ` · the outline: every ${picWhat(P)}` : ''}`;
    const R0 = pCard(x, box.x, box.y, box.w, box.h, DLAB[k] || k, sub);
    if (!n || counts.length !== E.length + 1) return;
    const sh = counts.map((c) => c / n), shb = nb && base.length === K ? base.map((c) => c / nb) : null, mx = Math.max(0.05, ...sh, ...(shb || []));
    const L = R0.x, Rr = R0.x + R0.w, T = R0.y + 22, B = R0.y + R0.h - 22, bw = (Rr - L) / K, y = (v) => T + (1 - v / mx) * (B - T);
    sh.forEach((v, i) => {
      const lo = i === 0 ? null : E[i - 1], hi = i === K - 1 ? null : E[i], mid = lo == null ? hi - 1 : hi == null ? lo + 1 : (lo + hi) / 2;
      const down = FALLS.includes(k) ? true : RISES.includes(k) ? false : mid < 0, ww = Math.min(bw - 4, 46), xx = L + i * bw + (bw - ww) / 2, hh = B - y(v);
      if (hh < 0.3) return;
      x.save(); x.globalAlpha = 0.62; x.fillStyle = down ? PCv.down : PCv.up; pRect(x, xx, y(v), ww, hh + 3, Math.min(3, ww / 2, hh)); x.fill(); x.restore();
      x.fillStyle = PCv.card; x.fillRect(xx - 1, B, ww + 2, 4);
    });
    pHline(x, L, Rr, B, PCv.line);
    if (shb) { const pts = []; shb.forEach((v, i) => { pts.push([L + i * bw, y(v)]); pts.push([L + (i + 1) * bw, y(v)]); }); pLine(x, pts, PCv.ink, 1.5); }
    if (fin(q.p50)) {
      let b = 0; while (b < E.length && E[b] <= q.p50) b++;
      const fr = b === 0 || b === E.length ? 0.5 : (q.p50 - E[b - 1]) / (E[b] - E[b - 1]), xm = L + (b + fr) * bw;
      pLine(x, [[xm, T - 6], [xm, B]], PCv.ink, 1.4, [4, 3]);
      pLabel(x, `median ${pct0(q.p50) || '0%'}`, Math.min(Math.max(xm, L + 50), Rr - 50), T - 10, PCv.ink, pFont(12.5, 650), 'center');
    }
    x.textAlign = 'center'; x.fillStyle = PCv.muted; x.font = pFont(11.5);
    E.forEach((e, i) => { if (K <= 10 || i % 2 === 1) { x.fillStyle = PCv.muted; x.fillText(pct0(e) || '0', L + (i + 1) * bw, B + 16); } });
    x.textAlign = 'left';
  }
  function drawOwn(x, box, P) {
    const O = P.own || {}, runs = (O.last || []).slice(-7).reverse();
    const R0 = pCard(x, box.x, box.y, box.w, box.h, `Its own runs of highs: ${num(O.runs)} so far`, `median ${num((O.run_days || {}).p50)} trading days to the peak; the pullback after: median ${sp((O.pullback || {}).p50)}`);
    const rowH = Math.min(28, (R0.h - 6) / Math.max(1, runs.length)), mx = Math.max(0.2, ...runs.map((r) => Math.abs(r.pullback || 0)));
    const LX = R0.x + 196, W = R0.w - 196 - 150;
    runs.forEach((r, i) => {
      const y = R0.y + 4 + i * rowH;
      x.fillStyle = PCv.ink; x.font = pFont(12.5, 600); x.fillText(`${md(r.start)} – ${mdy(r.peak)}`, R0.x, y + rowH / 2 + 4);
      x.fillStyle = PCv.muted; x.font = pFont(12); x.fillText(`${num(r.days)} d`, R0.x + 160, y + rowH / 2 + 4);
      const w = W * Math.abs(r.pullback || 0) / mx;
      x.save(); x.globalAlpha = 0.62; x.fillStyle = PCv.down; pRect(x, LX, y + rowH * 0.2, Math.max(2, w), rowH * 0.6, 3); x.fill(); x.restore();
      x.fillStyle = PCv.ink; x.font = pFont(12.5, 600); x.fillText(sp(r.pullback), LX + w + 6, y + rowH / 2 + 4);
      const vw = x.measureText(sp(r.pullback)).width;
      x.fillStyle = PCv.muted; x.font = pFont(12); x.fillText(r.days_back == null ? 'not back yet' : `back in ${num(r.days_back)} d`, LX + w + 14 + vw, y + rowH / 2 + 4);
    });
  }
  async function picture(P, picks, hub) {
    if (typeof document === 'undefined') return null;
    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) { /* the fonts at hand */ } }
    const rows = picRows(P, picks);
    if (!rows.length) return null;
    const Wd = 1200, M0 = 32, G = 22, full = Wd - 2 * M0, halfW = (full - G) / 2;
    const PH = { now: 340, odds: 360, fan: 300, own: 270 }, ph = (row) => Math.max(...row.map((k) => PH[k] || 270));
    const headH = 104, footH = 64, Hh = headH + rows.reduce((a, r) => a + ph(r) + G, 0) + footH;
    const c = document.createElement('canvas'), sc = 2; c.width = Wd * sc; c.height = Hh * sc;
    const x = c.getContext('2d'); x.scale(sc, sc);
    x.fillStyle = PCv.bg; x.fillRect(0, 0, Wd, Hh);
    x.fillStyle = PCv.ink; x.font = pFont(27, 650); x.fillText(fitText(x, picTitle(P), full), M0, 46);
    x.fillStyle = PCv.muted; x.font = pFont(14.5); x.fillText(fitText(x, picSub(P), full), M0, 74);
    let y = headH;
    for (const row of rows) {
      const h = ph(row);
      row.forEach((k, i) => {
        const box = { x: M0 + i * (halfW + G), y, w: PIC_WIDE.includes(k) ? full : halfW, h };   // a lone histogram stays half wide
        if (k === 'now') drawStand(x, box, P);
        else if (k === 'odds') drawOdds(x, box, P);
        else if (k === 'fan') drawFan(x, box, P);
        else if (k === 'own') drawOwn(x, box, P);
        else drawHist(x, box, P, k);
      });
      y += h + G;
    }
    x.strokeStyle = PCv.line; x.lineWidth = 1; x.beginPath(); x.moveTo(M0, Hh - footH + 8); x.lineTo(Wd - M0, Hh - footH + 8); x.stroke();
    const first = P.M ? P.M.days[0] : null;
    x.fillStyle = PCv.muted; x.font = pFont(12.5);
    x.fillText(fitText(x, `Highs, lows & ranges · daily closes${first ? ` ${mdy(first)} – ${mdy((P.S || {}).date)}` : ''}, adjusted for dividends and splits · trading days · ${P.doc.kind === 'stock' ? "today's companies (survivors)" : 'the days of the group'}`, full - 220), M0, Hh - footH + 32);
    x.fillText('What followed the most similar days in the past — history, not a forecast. Not investment advice.', M0, Hh - footH + 50);
    const lx = Wd - M0;
    x.textAlign = 'right'; x.fillStyle = PCv.ink; x.font = pFont(19, 700); x.fillText('Filing Flows', lx, Hh - footH + 36);
    const ww = x.measureText('Filing Flows').width; x.fillStyle = PCv.muted; x.font = pFont(12.5); x.fillText('filing-flows.com', lx, Hh - footH + 53); x.textAlign = 'left';
    try {
      const img = await new Promise((ok, bad) => { const im = new Image(); im.onload = () => ok(im); im.onerror = bad; im.src = (hub || '') + '../favicon.svg'; setTimeout(bad, 2500); });
      x.drawImage(img, lx - ww - 34, Hh - footH + 16, 26, 26);
    } catch (e) { /* the wordmark alone */ }
    return c;
  }
  function pngBar(P) {
    const picks = PICKS[P.kind] || PIC_DEFAULT, items = PIC[P.kind].filter(([k]) => canPic(P, k));
    if (!items.length) return '';
    return `<div class="hv-png"><span class="hv-png-l">Picture to share (PNG):</span>${items.map(([k, l]) => `<label><input type="checkbox" data-hvp="${k}"${picks.includes(k) ? ' checked' : ''}> ${esc(l)}</label>`).join('')}`
      + `<button type="button" class="hv-chip on" data-hvpng="1">Make the picture</button><span class="hv-sub" data-hvmsg style="margin:0"></span></div><div class="hv-png-out"></div>`;
  }
  function bindPng(el, P, hub) {
    if (!el || !el.querySelectorAll) return;
    el.querySelectorAll('[data-hvp]').forEach((cb) => { cb.onchange = () => { const cur = PICKS[P.kind] || PIC_DEFAULT.slice(); PICKS[P.kind] = PIC[P.kind].map(([q]) => q).filter((q) => (q === cb.dataset.hvp ? cb.checked : cur.includes(q))); }; });
    const mk = el.querySelector('[data-hvpng]'), out = el.querySelector('.hv-png-out'), msg = el.querySelector('[data-hvmsg]');
    if (!mk || !out) return;
    mk.onclick = async () => {
      const picks = PICKS[P.kind] || PIC_DEFAULT;
      if (!picRows(P, picks).length) { if (msg) msg.textContent = 'Pick at least one panel.'; return; }
      if (msg) msg.textContent = 'Drawing…';
      try {
        const c = await picture(P, picks, hub);
        const blob = c && await new Promise((res) => c.toBlob(res, 'image/png'));
        if (!blob) throw new Error('the picture could not be made');
        const href = URL.createObjectURL(blob), fn = `filing-flows-${P.kind}-${String(P.doc.key).toLowerCase()}-${(P.S || {}).date || 'today'}.png`;
        out.innerHTML = `<img alt="${esc(picTitle(P))}" src="${href}"><div class="hv-png-acts"><a href="${href}" download="${esc(fn)}">Download PNG</a>${typeof ClipboardItem !== 'undefined' && navigator.clipboard && navigator.clipboard.write ? '<button type="button" data-hvcopy>Copy image</button>' : ''}<button type="button" data-hvclose>Close</button></div>`;
        if (msg) msg.textContent = '';
        const cp = out.querySelector('[data-hvcopy]');
        if (cp) cp.onclick = async () => { try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]); cp.textContent = 'Copied'; } catch (e) { cp.textContent = 'Copy failed'; } };
        out.querySelector('[data-hvclose]').onclick = () => { out.innerHTML = ''; };
      } catch (e) { if (msg) msg.textContent = 'Could not draw the picture (' + e.message + ').'; }
    };
  }
  /* the stand chart with its heading and words, for the asset's page */
  function standBlock(M, width) {
    if (!M) return '';
    const yrs = (M.N - M.from) / 252, over = yrs > 2.5 ? 'the last three years' : yrs > 1.5 ? 'the last two years' : yrs > 0.75 ? 'the last year' : 'the last six months';
    const span = SPAN[M.reg];
    const what = M.kind === 'highs' ? `the dashed line is its all-time high and the dotted one 10% under it (a close there ends a run of highs); the dots are new all-time highs${M.shade ? '; shaded, this run' : ''}`
      : M.kind === 'lows' ? `the dashed line is its ${span} low and the dotted ones 10% and 20% above it (a rebound); the dots are new ${span} lows${M.shade ? `; shaded, the slide since its ${M.reg === 'atl' ? 'all-time' : 'last ' + span} high` : ''}`
      : 'shaded, the range of the last 63 trading days: a close above its top or under its bottom is the breakout';
    return `<h3>Where it stands</h3><p class="hv-sub">The close over ${over}, adjusted for dividends and splits: ${what}. Hover for a week's close.</p>${standChart(M, width)}`;
  }

  async function render(el, ctx) {
    if (!el) return;
    css();
    ctx = ctx || {};
    const hub_ = ctx.hub != null ? ctx.hub : '';
    const key = String(ctx.key || ctx.ticker || '').toUpperCase().replace(/[./]/g, '-');
    const here = typeof ctx.here === 'function' ? ctx.here : () => true;
    if (!key) { el.innerHTML = '<p class="hv-sub">No ticker.</p>'; return; }
    el.innerHTML = '<p class="hv-sub">Loading…</p>';
    let doc;
    try { doc = await get(`${hub_}data/research/paths/moves/a/${encodeURIComponent(key)}.json`); } catch (e) {
      if (here()) el.innerHTML = `<p class="hv-sub">No daily history for ${esc(key)} yet (the move odds' files: the valued companies, the market, its sectors and the ETFs).</p>`;
      return;
    }
    if (!here()) return;
    if (!doc.highs && !doc.lows && !doc.ranges) { el.innerHTML = `<p class="hv-sub">${esc(doc.name || key)}: the highs, lows and ranges research is built with the move odds after the next US close.</p>`; return; }
    const reg = pickRegime(doc, ctx.regime), kind = kindOf(reg);
    let all = null;
    try { all = await get(`${hub_}data/research/paths/moves/${kind}.json`); } catch (e) { all = null; }
    if (!here()) return;
    const gk = { stock: 'companies', index: 'indices' }[doc.kind] || 'funds', name = doc.kind === 'stock' ? `${doc.ticker || key} (${doc.name || ''})` : doc.name || key;
    const grpOf = (x) => (x && x.groups && x.groups[gk] ? x.groups[gk] : null), grp = (x) => (grpOf(x) || {}).base || null;
    const R_ = all && all.regimes && all.regimes[reg], o_ = { params: all && all.params, group: kind === 'highs' ? grpOf(all) : grpOf(R_) };
    const blk = kind === 'highs' ? doc.highs : kind === 'lows' ? doc.lows[reg] : doc.ranges[reg];
    let M = null;
    try { M = standModel(doc, reg, (blk || {}).state); } catch (e) { M = null; }
    const PX = { doc, reg, kind, gk, S: (blk || {}).state || {}, A: (blk || {}).analogues || null, own: kind === 'highs' ? (doc.highs || {}).own : null, base: kind === 'highs' ? grp(all) : grp(R_), G: o_.group, params: (all && all.params) || {}, M };
    o_.stand = standBlock(M, el.clientWidth || 0) + pngBar(PX);
    let body;
    if (kind === 'highs') body = block(doc.highs, name, doc.kind, grp(all), gk, o_);
    else if (kind === 'lows') body = lowBlock(doc.lows[reg], name, doc.kind, grp(R_), gk, reg, o_);
    else body = rangeBlock(doc.ranges[reg], name, doc.kind, grp(R_), gk, reg, o_);
    const title = { highs: 'At the highs — how long runs last, how deep the pullback', lows: `${REG[reg]} — how long until the next low, how far the rebound`, ranges: `${REG[reg]} — when it breaks out, which way` }[kind];
    const none = regimesOf(doc).length === 1 && kind === 'highs' && !(doc.highs.state || {}).high ? `<p class="hv-sub">Not at its highs, at its lows or in a sideways range on the last close; below, where it stands against its high and its own past runs.</p>` : '';
    el.innerHTML = `<div class="hv">${ctx.title === false ? '' : `<h3 style="margin-top:4px">${esc(title)}</h3>`}${chips(doc, reg)}${none}${body}</div>`;
    if (el.querySelectorAll) el.querySelectorAll('[data-hvr]').forEach((b) => { b.onclick = () => { if (typeof ctx.onRegime === 'function') ctx.onRegime(b.dataset.hvr); render(el, Object.assign({}, ctx, { regime: b.dataset.hvr })); }; });
    bindPng(el, PX, hub_);
  }

  const api = { render, hub, block, bucketTable, kmChart, facts, tiles, headline, css, lowsHub, rangesHub, lowBlock, rangeBlock, lowBucket, rangeBucket, regimesOf, pickRegime, REG,
    histChart, fanChart, spreadBlock, condBlock, backtestBlock, calibChart, groupOdds, series, standModel, standChart, standBlock, picture, picRows, picTitle, picSub, canPic, pngBar, PIC };
  if (typeof window !== 'undefined') window.HighsView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
