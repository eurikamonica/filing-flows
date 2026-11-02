/* At the highs — how long runs of new all-time highs last and how deep the pullback is that ends them (app/highs.py,
   built with the move odds after every US close: data/research/paths/moves/highs.json, and each asset's block in
   a/<KEY>.json → highs). One asset (the company page's "At the highs" tab and the hub's Move odds → At the highs):
   where it stands against its high and its run, its state (above its 200-day average, momentum, volatility, P/E,
   volume — each against its own history), what followed the most similar high days of the same kind of asset, and its
   own past runs. The hub view adds every asset at its highs now and the research tables by each state variable.
   Descriptive history, not a forecast. window.HighsView = {render(el, {ticker | key, hub}), hub(doc, opts), …}. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const sp = (v, d = 1) => { if (!fin(v)) return '—'; const a = Math.abs(100 * v); return (a < 0.05 ? '' : v > 0 ? '+' : '−') + num(a, d) + '%'; };
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
  function kmChart(lines, grid) {
    const W = 720, H = 250, L = 44, R = 14, T = 12, B = 34, gx = grid[grid.length - 1];
    const sx = (d) => L + (d / gx) * (W - L - R), sy = (v) => T + (1 - v) * (H - T - B);
    let s = `<svg class="hv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Survival curves: the share of high days not yet followed by each pullback">`;
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { s += `<line class="hv-g" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${pc(v)}</text>`; });
    [0, 21, 63, 126, 189, 252].filter((d) => d <= gx).forEach((d) => { s += `<text x="${sx(d)}" y="${H - 14}" text-anchor="middle">${d === 0 ? 'now' : d === 21 ? '1 mo' : d === 63 ? '3 mo' : d === 126 ? '6 mo' : d === 189 ? '9 mo' : '12 mo'}</text>`; });
    for (const l of lines) {
      if (!l.curve) continue;
      const pts = l.curve.map((v, i) => (fin(v) ? `${sx(grid[i]).toFixed(1)},${sy(v).toFixed(1)}` : null)).filter(Boolean);
      s += `<polyline class="${l.dash ? 'hv-b' : 'hv-l'}" points="${pts.join(' ')}" style="stroke:${l.col}"/>`;
    }
    s += `<text x="${(L + W - R) / 2}" y="${H - 1}" text-anchor="middle">trading days after the high day</text></svg>`;
    return s + `<div class="hv-key">${lines.filter((l) => l.curve && !l.dash).map((l) => `<span><i style="background:${l.col}"></i>${esc(l.label)}</span>`).join('')}<span><i style="background:var(--muted,#999);height:1px"></i>dashed: every high day of ${esc(lines.find((l) => l.dash) ? lines.find((l) => l.dash).who : 'the group')}</span></div>`;
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

  async function render(el, ctx) {
    if (!el) return;
    css();
    ctx = ctx || {};
    const hub_ = ctx.hub != null ? ctx.hub : '';
    const key = String(ctx.key || ctx.ticker || '').toUpperCase().replace(/[./]/g, '-');
    const here = typeof ctx.here === 'function' ? ctx.here : () => true;
    if (!key) { el.innerHTML = '<p class="hv-sub">No ticker.</p>'; return; }
    el.innerHTML = '<p class="hv-sub">Loading…</p>';
    let doc, all = null;
    try { doc = await get(`${hub_}data/research/paths/moves/a/${encodeURIComponent(key)}.json`); } catch (e) {
      if (here()) el.innerHTML = `<p class="hv-sub">No daily history for ${esc(key)} yet (the move odds' files: the valued companies, the market, its sectors and the ETFs).</p>`;
      return;
    }
    try { all = await get(`${hub_}data/research/paths/moves/highs.json`); } catch (e) { all = null; }
    if (!here()) return;
    const H = doc.highs;
    if (!H) { el.innerHTML = `<p class="hv-sub">${esc(doc.name || key)}: the highs research is built with the move odds after the next US close.</p>`; return; }
    const gk = { stock: 'companies', index: 'indices' }[doc.kind] || 'funds', base = all && all.groups && all.groups[gk] ? all.groups[gk].base : null;
    el.innerHTML = `<div class="hv">${ctx.title === false ? '' : `<h3 style="margin-top:4px">At the highs — how long runs last, how deep the pullback</h3>`}${block(H, doc.kind === 'stock' ? `${doc.ticker || key} (${doc.name || ''})` : doc.name || key, doc.kind, base, gk, { params: all && all.params })}</div>`;
  }

  const api = { render, hub, block, bucketTable, kmChart, facts, tiles, headline, css };
  if (typeof window !== 'undefined') window.HighsView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
