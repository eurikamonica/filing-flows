/* Highs, lows & ranges — how long an asset's regime lasts and what follows it, built with the move odds after every US
   close (data/research/paths/moves/: highs.json from app/highs.py, lows.json and ranges.json from app/regimes.py, and
   each asset's blocks in a/<KEY>.json → highs, lows, ranges).
   At the highs: how long runs of new all-time highs last and how deep the pullback is that ends them.
   At the lows (an all-time, a 52-week or a 3-month low): how long until the next new low, the rebound and how far.
   In a range (sideways for 3 months, narrow or wide): how long until the breakout, which way, and whether it holds.
   One asset (the company page's tab and the hub's Move odds → Highs, lows & ranges): where it stands, its state (each
   variable against its own history where marked), what followed the most similar days of the same kind of asset, and
   for the highs its own past runs. The hub adds every asset in the regime now and the research tables by each state
   variable. Descriptive history, not a forecast.
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
.hv-bar{display:inline-block;height:9px;border-radius:2px;background:var(--mk-cost,#c0392b);opacity:.7;vertical-align:middle;margin-right:6px}.hv-up{color:var(--mk-profit,#17734a)}.hv-down{color:var(--mk-cost,#c0392b)}`;
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

  /* ---------- what followed ---------- */
  function kmChart(lines, grid, xl = 'trading days after the high day', aria = 'Survival curves: the share of high days not yet followed by each pullback') {
    const W = 720, H = 250, L = 44, R = 24, T = 12, B = 34, gx = grid[grid.length - 1];
    const sx = (d) => L + (d / gx) * (W - L - R), sy = (v) => T + (1 - v) * (H - T - B);
    let s = `<svg class="hv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">`;
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { s += `<line class="hv-g" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${pc(v)}</text>`; });
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { s += `<text x="${sx(d)}" y="${H - 14}" text-anchor="middle">${d === 0 ? 'now' : d === 21 ? '1 mo' : d === 63 ? '3 mo' : d === 126 ? '6 mo' : d === 189 ? '9 mo' : '12 mo'}</text>`; });
    for (const l of lines) {
      if (!l.curve) continue;
      const pts = l.curve.map((v, i) => (fin(v) ? `${sx(grid[i]).toFixed(1)},${sy(v).toFixed(1)}` : null)).filter(Boolean);
      s += `<polyline class="${l.dash ? 'hv-b' : 'hv-l'}" points="${pts.join(' ')}" style="stroke:${l.col}"/>`;
    }
    s += `<text x="${(L + W - R) / 2}" y="${H - 1}" text-anchor="middle">${esc(xl)}</text></svg>`;
    const dl = lines.find((l) => l.dash && l.curve);
    return s + `<div class="hv-key">${lines.filter((l) => l.curve && !l.dash).map((l) => `<span><i style="background:${l.col}"></i>${esc(l.label)}</span>`).join('')}${dl ? `<span><i style="background:var(--muted,#999);height:1px"></i>dashed: every ${esc(dl.what || 'high day')} of ${esc(dl.who || 'the group')}</span>` : ''}</div>`;
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
    let h = headline(name, S, kind) + tiles(S, kind);
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar high days</h3><p class="hv-sub">High days of ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} runs) nearest on ${esc(A.features.map((f) => FEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year. A pullback counts from the all-time high; the days are trading days.${base ? ' After the dot: every high day of the group, for comparison.' : ''}</p>`;
      h += facts(A, lvl);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'no 5% pullback yet', curve: (A.t5 || {}).curve, col: 'var(--q-warm,#d9822b)' }, { label: 'no 10% pullback yet', curve: (A.t10 || {}).curve, col: 'var(--mk-cost,#c0392b)' },
        { label: 'the run still ahead of its peak', curve: (A.run_left || {}).curve, col: 'var(--mk-profit,#17734a)' },
        ...(base ? [{ dash: true, curve: (base.t10 || {}).curve, col: 'var(--mk-cost,#c0392b)', who: GROUP[groupKey] }, { dash: true, curve: (base.t5 || {}).curve, col: 'var(--q-warm,#d9822b)', who: GROUP[groupKey] }] : [])], g);
      h += oddsTable(A, base);
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'Run age', 'Highs in 63 d', 'To its peak', 'To a 10% pullback', 'The pullback after', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), td(e.age), num(e.highs63), e.run_left == null ? 'not yet' : td(e.run_left), e.t10 == null ? 'not yet' : td(e.t10), sp(e.pullback), `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
    } else if (S.high) h += `<p class="hv-sub">Too few similar high days with every state variable on file to compare.</p>`;
    if (O.runs) {
      h += `<h3>Its own runs</h3><p class="hv-sub">${esc(name)}'s ${num(O.runs)} completed runs of highs (from the first ATH after a 10% drawdown to the last one before the next): median <b>${td((O.run_days || {}).p50)}</b> from first high to peak (25–75%: ${num((O.run_days || {}).p25)}–${num((O.run_days || {}).p75)}); the pullback after them median <b>${sp((O.pullback || {}).p50)}</b> (25–75%: ${sp((O.pullback || {}).p25)} to ${sp((O.pullback || {}).p75)}); back to the peak in a median ${td((O.days_back || {}).p50)}.</p>`;
      h += table(['Run began', 'Peak', 'Days to the peak', 'The pullback after', 'Back to the peak'], (O.last || []).slice().reverse().map((r) => [esc(mdy(r.start)), esc(mdy(r.peak)), num(r.days), `<span class="hv-down">${sp(r.pullback)}</span>`, r.days_back == null ? 'not yet' : td(r.days_back)]), [0, 1]);
    }
    h += `<p class="hv-sub">Adjusted closes (dividends reinvested), so an all-time high is a total-return high; P/E: price ÷ the last four first-filed quarterly diluted EPS (SEC), positive only. Companies are today's (survivors), which flatters what came after their highs. History, not a forecast.</p>`;
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
    let h = lowHeadline(name, S, kind, reg) + lowTiles(S, kind, reg);
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar days at ${A_N(reg)} low</h3><p class="hv-sub">Low days (within 15% of the ${SPAN[reg]} low with a new one in the last 63 trading days) of ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} slides) nearest on ${esc((A.features || []).map((f) => LFEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year.${base ? ' After the dot: every low day of the group, for comparison.' : ''}</p>`;
      h += lowFacts(A, reg);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'no new low yet', curve: (A.next_low || {}).curve, col: 'var(--mk-cost,#c0392b)' }, { label: 'no 10% rebound yet', curve: (A.r10 || {}).curve, col: 'var(--mk-profit,#17734a)' },
        { label: 'no 20% rebound yet', curve: (A.r20 || {}).curve, col: 'var(--q-warm,#d9822b)' },
        ...(base ? [{ dash: true, curve: (base.next_low || {}).curve, col: 'var(--mk-cost,#c0392b)', who: GROUP[groupKey], what: 'low day' }, { dash: true, curve: (base.r20 || {}).curve, col: 'var(--q-warm,#d9822b)', who: GROUP[groupKey], what: 'low day' }] : [])],
      g, 'trading days after the low day', 'Survival curves: the share of low days not yet followed by a new low or a rebound');
      h += table(['Within', ...Object.values(HZW), 'Median'], [oddsRow(`A new ${SPAN[reg]} low`, A.next_low, base && base.next_low), oddsRow('A 10% rebound', A.r10, base && base.r10), oddsRow('A 20% rebound', A.r20, base && base.r20)], [0]);
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'The slide’s age', 'Under its high', 'To a 10% rebound', 'The low before it', 'The rebound after', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), td(e.age), sp(e.dd_ath, 0), e.r10 == null ? (e.seen >= 252 ? 'none in a year' : 'not yet') : td(e.r10), `<span class="${tone(e.fall)}">${sp(e.fall)}</span>`, `<span class="${tone(e.bounce)}">${sp(e.bounce)}</span>`, `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
    } else h += `<p class="hv-sub">Too few similar low days with every state variable on file to compare.</p>`;
    return h + `<p class="hv-sub">${NOTE}</p>`;
  }
  function rangeBlock(B, name, kind, base, groupKey, reg, opts = {}) {
    const S = B.state || {}, A = B.analogues;
    let h = rangeHeadline(name, S, kind, reg) + rangeTiles(S, kind);
    if (A && A.days) {
      h += `<h3>What followed the ${num(A.days)} most similar days in a ${reg} range</h3><p class="hv-sub">Days sideways over 63 trading days (the net move under a quarter of the range's width) with the width ${reg === 'narrow' ? 'in the bottom 15%' : 'in the top 30%'} of the asset's own, among ${esc(GROUP[groupKey] || 'its kind')} (${num(A.assets)} assets, ${num(A.runs)} ranges), nearest on ${esc((A.features || []).map((f) => RFEAT[f] || f).join(', '))}: at most one per asset in any 21 days, none of its own from the last year.${base ? ' After the dot: every such day of the group.' : ''}</p>`;
      h += rangeFacts(A);
      const g = (opts.params && opts.params.grid) || Array.from({ length: 37 }, (_, i) => i * 7);
      h += kmChart([{ label: 'still in the range (no breakout yet)', curve: (A.breakout || {}).curve, col: 'var(--accent,#1f6f4a)' },
        ...(base ? [{ dash: true, curve: (base.breakout || {}).curve, col: 'var(--accent,#1f6f4a)', who: GROUP[groupKey], what: `day in a ${reg} range` }] : [])],
      g, 'trading days after the day in the range', 'Survival curve: the share of days in a range not yet followed by a breakout');
      const w = (X, h, d) => pc(((X || {})['within' + h] || {})[d]);
      h += table(['Within', ...Object.values(HZW), 'Median'], [oddsRow('A breakout, either way', A.breakout, base && base.breakout),
        ['Up first', ...['21', '63', '126', '252'].map((x) => `${w(A, x, 'up')}${base ? ` <span class="m">· ${w(base, x, 'up')}</span>` : ''}`), ''],
        ['Down first', ...['21', '63', '126', '252'].map((x) => `${w(A, x, 'down')}${base ? ` <span class="m">· ${w(base, x, 'down')}</span>` : ''}`), '']], [0]);
      if ((A.nearest || []).length) h += `<h4>The nearest of them</h4>` + table(['Asset', 'Day', 'Width', 'Days in it', 'Breakout', 'Which way', '3 months after it', '12 months'], A.nearest.map((e) => [
        esc(e.key), esc(mdy(e.date)), pc(e.width, 1), num(e.age), e.brk == null ? (e.seen >= 252 ? 'none in a year' : 'not yet') : td(e.brk), e.up == null ? '—' : e.up ? '<span class="hv-up">up</span>' : '<span class="hv-down">down</span>',
        `<span class="${tone(e.after63)}">${sp(e.after63)}</span>`, `<span class="${tone(e.fwd252)}">${sp(e.fwd252)}</span>`]), [0, 1]);
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
    const grp = (x) => (x && x.groups && x.groups[gk] ? x.groups[gk].base : null);
    let body;
    if (kind === 'highs') body = block(doc.highs, name, doc.kind, grp(all), gk, { params: all && all.params });
    else if (kind === 'lows') body = lowBlock(doc.lows[reg], name, doc.kind, grp(all && all.regimes && all.regimes[reg]), gk, reg, { params: all && all.params });
    else body = rangeBlock(doc.ranges[reg], name, doc.kind, grp(all && all.regimes && all.regimes[reg]), gk, reg, { params: all && all.params });
    const title = { highs: 'At the highs — how long runs last, how deep the pullback', lows: `${REG[reg]} — how long until the next low, how far the rebound`, ranges: `${REG[reg]} — when it breaks out, which way` }[kind];
    const none = regimesOf(doc).length === 1 && kind === 'highs' && !(doc.highs.state || {}).high ? `<p class="hv-sub">Not at its highs, at its lows or in a sideways range on the last close; below, where it stands against its high and its own past runs.</p>` : '';
    el.innerHTML = `<div class="hv">${ctx.title === false ? '' : `<h3 style="margin-top:4px">${esc(title)}</h3>`}${chips(doc, reg)}${none}${body}</div>`;
    if (el.querySelectorAll) el.querySelectorAll('[data-hvr]').forEach((b) => { b.onclick = () => { if (typeof ctx.onRegime === 'function') ctx.onRegime(b.dataset.hvr); render(el, Object.assign({}, ctx, { regime: b.dataset.hvr })); }; });
  }

  const api = { render, hub, block, bucketTable, kmChart, facts, tiles, headline, css, lowsHub, rangesHub, lowBlock, rangeBlock, lowBucket, rangeBucket, regimesOf, pickRegime, REG };
  if (typeof window !== 'undefined') window.HighsView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
