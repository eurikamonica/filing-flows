/* Market consensus — one company's page, shared by the Disclosure Hub (Consensus tab) and the main site's company page
   ("Consensus" tab). Self-contained: window.ConsensusView.render(element, doc) draws everything from
   data/consensus/c/<cik>.json (app/consensus.py): analysts' estimates (Yahoo Finance consensus), prediction markets
   (Polymarket, Kalshi) and our own model's forecast, side by side, with how each did before. CSS prefix cv-. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const usd = (v, d = 2) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), d) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const unitFmt = (v, u) => (!fin(v) ? '—' : u === '$' ? (Math.abs(v) >= 1e6 ? big(v) : usd(v)) : u === '%' ? num(v, Math.abs(v) < 10 ? 1 : 0) + '%' : num(v, Math.abs(v) < 100 ? 2 : 0) + (u ? ' ' + u : ''));
  const pts = (v) => (fin(v) ? num(v, Math.abs(v) >= 1000 ? 0 : 2) : '—');
  let PX = usd;                                            // the unit of the fan chart: dollars a share, or index points
  const mfmt = (m) => (m.kind === 'mcap' ? big : m.index && m.points ? pts : (v) => usd(v));
  const day = (s) => (s ? String(s).slice(0, 10) : '—');
  const ts = (s) => Date.parse(String(s).slice(0, 10) + 'T00:00:00Z');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)',
    an: '#d9822b', pm: '#8a4fd6', ours: '#2a78d6', ks: '#16a085', mp: '#e08a1e', cmb: '#3b6fd8' };
  const KIND = { beat: 'Beat earnings?', above: 'Price ladder', bracket: 'Closing-price brackets', mcap: 'Market cap', hit: 'High / low touch', metric: 'Reported metric (revenue, segments, KPIs)', updown: 'Up or down', kpi: 'Company KPI', mention: 'Earnings-call mentions', other: 'Other events' };
  const PERIOD = { '0q': 'This quarter', '+1q': 'Next quarter', '0y': 'This fiscal year', '+1y': 'Next fiscal year' };

  function css() {
    if (document.getElementById('cv-css')) return;
    const s = document.createElement('style'); s.id = 'cv-css';
    s.textContent = `.cv h3{margin:22px 0 6px;font-size:16px}.cv .cv-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45}
.cv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin:8px 0 6px}
.cv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px;border-top:3px solid var(--k,var(--line,#ddd))}
.cv-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}.cv-card span{font-size:12px;color:var(--muted,#777)}
.cv-card i{display:block;font-style:normal;font-size:12px;margin-top:2px;color:var(--muted,#777)}
.cv-good{color:${C.good}}.cv-bad{color:${C.bad}}
.cv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.cv-tbl th,.cv-tbl td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.cv-tbl td.n,.cv-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.cv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}
.cv-wrap{overflow-x:auto}.cv svg{display:block;width:100%;max-width:860px;height:auto;overflow:visible}.cv svg text{font-size:11px;fill:var(--muted,#777)}
.cv .cv-grid{stroke:var(--line,#e3e3e3)}.cv-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
.cv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:14px}.cv-tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line,#ddd);margin-left:6px;color:var(--muted,#777)}
.cv-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted,#777);margin:2px 0 6px}.cv-legend span::before{content:'';display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;background:var(--k)}
.cv-mk{border:1px solid var(--line,#e3e3e3);border-radius:10px;padding:10px 12px;margin:8px 0}.cv-mk h4{margin:0 0 4px;font-size:14px;font-weight:600}.cv-mk h4 a{color:inherit}
.cv-mk .cv-meta{font-size:12px;color:var(--muted,#777);margin-bottom:6px}
.cv-pbar{display:grid;grid-template-columns:minmax(90px,38%) 1fr 48px;gap:8px;align-items:center;font-size:12.5px;margin:3px 0}
.cv-pbar s{display:block;height:8px;border-radius:5px;background:var(--line,#e8e8e8);position:relative;text-decoration:none}.cv-pbar s i{position:absolute;left:0;top:0;bottom:0;border-radius:5px;background:var(--k,${C.pm})}
.cv-pbar em{font-style:normal;text-align:right;font-variant-numeric:tabular-nums}
.cv-rating{display:flex;height:14px;border-radius:7px;overflow:hidden;margin:6px 0 4px;max-width:520px}.cv-rating i{display:block;height:100%}
.cv-tabs{margin:4px 0}.cv-show.on{background:var(--accent,#2a78d6);color:#fff;border-color:var(--accent,#2a78d6)}
.cv-show{margin:2px 0 8px;font:inherit;font-size:13px;color:var(--accent,#2a78d6);background:none;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 10px;cursor:pointer}`;
    document.head.appendChild(s);
  }
  const card = (label, value, note = '', k = '', cls = '') => `<div class="cv-card" style="${k ? '--k:' + k : ''}"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;
  const link = (u, t) => (u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>` : esc(t));
  const tbl = (head, rows, numeric = []) => `<div class="cv-wrap"><table class="cv-tbl"><thead><tr>${head.map((h, i) => `<th class="${numeric.includes(i) ? 'n' : ''}">${h}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${numeric.includes(i) ? 'n' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const pbar = (label, p, k) => `<div class="cv-pbar"><span>${esc(label)}</span><s><i style="width:${fin(p) ? Math.max(0, Math.min(100, 100 * p)) : 0}%;${k ? '--k:' + k : ''}"></i></s><em>${pct(p)}</em></div>`;

  // ---------- the consensus fan: weekly price, then every forecast's range at its date ----------
  function fan(doc, a) {
    const px = (doc.prices || []).map(([d, v]) => [ts(d), v]).filter((p) => fin(p[1]));
    if (px.length < 4) return '';
    const last = px[px.length - 1][0], horizon = last + 400 * 864e5;
    const bars = [];
    const T = a.targets || {};
    if (fin(T.mean)) bars.push({ t: last + 365 * 864e5, lo: doc.unit === 'pts' ? null : T.low, mid: T.mean, hi: doc.unit === 'pts' ? null : T.high, col: C.an, label: doc.unit === 'pts' ? `Analysts, added up from ${num(T.n)} companies' 12-month targets: ${PX(T.mean)}, weighted lows–highs ${PX(T.low)}–${PX(T.high)}` : `Analysts' 12-month price target (${num(T.n)} analysts): mean ${usd(T.mean)}, ${usd(T.low)}–${usd(T.high)}` });
    const byEnd = {};
    for (const m of doc.markets || []) {                      // one market a date (a ladder before brackets), none ending within 3 days
      if (m.closed || !m.implied_price || !fin(m.implied_price.median) || !m.end || ts(m.end) < Date.now() + 3 * 864e5) continue;
      const k = m.end + (doc.unit === 'pts' ? m.source : '');
      if (!byEnd[k] || (m.kind === 'above' && byEnd[k].kind !== 'above')) byEnd[k] = m;
    }
    for (const m of Object.values(byEnd)) {
      const t = ts(m.end); if (t > horizon) continue;
      const ip = m.implied_price;
      bars.push({ t, lo: ip.q10, mid: ip.median, hi: ip.q90, col: m.source === 'kalshi' ? C.ks : C.pm, w: 5, label: `${m.title} — ${m.source === 'kalshi' ? 'Kalshi' : 'Polymarket'}-implied median ${PX(ip.median)}, 80% ${PX(ip.q10)}–${PX(ip.q90)}${m.index && !m.points ? ` (traded in ${m.underlying} dollars, shown in index points)` : ''}${m.implied_bounds && (m.implied_bounds.q10 || m.implied_bounds.q90) ? ' (an end of the range lies past the listed strikes)' : ''}` });
    }
    for (const o of doc.ours || []) if (fin(o.price)) bars.push({ t: ts(o.date), lo: o.lo80, mid: o.price, hi: o.hi80, col: C.ours, label: `Our model (${o.model}, ${o.horizon}, made ${day(o.from)}): ${PX(o.price)}, 80% ${PX(o.lo80)}–${PX(o.hi80)}` });
    const ys = px.map((p) => p[1]).concat(bars.flatMap((b) => [b.lo, b.mid, b.hi].filter(fin)));
    let y0 = Math.min(...ys), y1 = Math.max(...ys); const pad = (y1 - y0) * 0.06 || 1; y0 = Math.max(0, y0 - pad); y1 += pad;
    const x0 = px[0][0], x1 = Math.max(last + 30 * 864e5, ...bars.map((b) => b.t + 12 * 864e5));
    const W = 820, H = 300, L = 54, R = 16, Tp = 12, B = 26;
    const X = (v) => L + (v - x0) / (x1 - x0) * (W - L - R), Y = (v) => Tp + (y1 - v) / (y1 - y0) * (H - Tp - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price and the consensus ranges">`;
    for (let k = 0; k <= 4; k++) { const v = y0 + (y1 - y0) * k / 4; s += `<line class="cv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${PX === usd ? usd(v, v >= 100 ? 0 : 2) : PX(v)}</text>`; }
    for (let y = new Date(x0).getUTCFullYear(); y <= new Date(x1).getUTCFullYear(); y++) {
      for (const m of [0, 3, 6, 9]) {
        const t = Date.UTC(y, m, 1); if (t < x0 || t > x1) continue;
        s += `<text x="${X(t)}" y="${H - 6}" text-anchor="middle">${m === 0 ? y : ['Jan', 'Apr', 'Jul', 'Oct'][m / 3]}</text>`;
      }
    }
    s += `<line x1="${X(last)}" x2="${X(last)}" y1="${Tp}" y2="${H - B}" stroke="${C.mute}" stroke-dasharray="3 3"/>`;
    s += `<path d="${px.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${C.ink}" stroke-width="1.6"/>`;
    s += `<circle cx="${X(last)}" cy="${Y(px[px.length - 1][1])}" r="3" fill="${C.ink}"><title>Last weekly close ${PX(px[px.length - 1][1])} (${new Date(last).toISOString().slice(0, 10)})</title></circle>`;
    const same = {};
    for (const b of bars) { const k = Math.round(X(b.t)); b.off = (same[k] = (same[k] || 0) + 1) - 1; }
    for (const b of bars) {
      const n = bars.filter((o) => Math.round(X(o.t)) === Math.round(X(b.t))).length;
      const x = X(b.t) + (b.off - (n - 1) / 2) * 11, w = b.w || 7;
      s += `<g><title>${esc(b.label)}</title>`;
      if (fin(b.lo) && fin(b.hi)) s += `<rect x="${x - w / 2}" y="${Y(b.hi)}" width="${w}" height="${Math.max(1, Y(b.lo) - Y(b.hi))}" rx="2" fill="${b.col}" fill-opacity="0.22" stroke="${b.col}" stroke-width="1"/>`;
      s += `<line x1="${x - w}" x2="${x + w}" y1="${Y(b.mid)}" y2="${Y(b.mid)}" stroke="${b.col}" stroke-width="2.4"/>`;
      s += `<line x1="${X(last)}" x2="${x}" y1="${Y(px[px.length - 1][1])}" y2="${Y(b.mid)}" stroke="${b.col}" stroke-width="1" stroke-dasharray="2 3" opacity="0.6"/></g>`;
    }
    s += `<text x="${X(last) + 4}" y="${Tp + 10}">today</text></svg>`;
    return `<h3>Where the ${doc.unit === 'pts' ? 'index' : 'price'} is expected to go</h3>
      <p class="cv-sub">Weekly closes, then each forecast's middle (thick tick) and range (box) at its date. Hover a box for the details.</p>
      <div class="cv-legend"><span style="--k:${C.an}">${doc.unit === 'pts' ? "Analysts, bottom-up 12-month target" : "Analysts' 12-month target (low – mean – high)"}</span><span style="--k:${C.pm}">Polymarket: implied median and 80% range</span>${doc.unit === 'pts' ? `<span style="--k:${C.ks}">Kalshi: implied median and 80% range</span>` : ''}<span style="--k:#2a78d6">Our model: forecast and 80% range</span></div>${s}`;
  }

  // ---------- analysts ----------
  function estimates(a) {
    const P = a.periods || [];
    if (!P.length) return '';
    const rows = P.map((p) => {
      const e = p.eps || {}, r = p.rev || {}, tr = p.eps_trend || {}, rv = p.revisions || {};
      const ch = fin(tr.current) && fin(tr['90daysAgo']) && tr['90daysAgo'] ? tr.current / tr['90daysAgo'] - 1 : null;
      return [`<b>${esc(PERIOD[p.period] || p.period)}</b><br><span class="cv-sub">ends ${day(p.end)}</span>`, usd(e.avg), `${usd(e.low)} – ${usd(e.high)}`, num(e.numberOfAnalysts),
        `<span class="${fin(e.growth) ? (e.growth >= 0 ? 'cv-good' : 'cv-bad') : ''}">${spct(e.growth)}</span>`, big(r.avg), `${big(r.low)} – ${big(r.high)}`,
        `<span class="${fin(r.growth) ? (r.growth >= 0 ? 'cv-good' : 'cv-bad') : ''}">${spct(r.growth)}</span>`,
        `<span class="${fin(ch) ? (ch >= 0 ? 'cv-good' : 'cv-bad') : ''}">${spct(ch)}</span>`, `${num(rv.upLast30days)} ↑ · ${num(rv.downLast30days)} ↓`];
    });
    return `<h3>Analysts' estimates</h3><p class="cv-sub">Consensus of the analysts covering the company (Yahoo Finance). Growth is against the same period a year earlier; the EPS change is the consensus now against 90 days ago.</p>` +
      tbl(['Period', 'EPS', 'EPS range', 'Analysts', 'EPS growth', 'Revenue', 'Revenue range', 'Revenue growth', 'EPS change, 90 days', 'Revisions, 30 days'], rows, [1, 2, 3, 4, 5, 6, 7, 8]);
  }
  function trendChart(doc, a) {
    // the last 90 days from Yahoo's EPS trend, and our own daily snapshots once they accumulate
    const q = (a.periods || []).find((p) => p.period === '0q'), y = (a.periods || []).find((p) => p.period === '0y');
    const snaps = (doc.snapshots || []).map(([d, r]) => ({ t: ts(d), q: r[1], y: r[3], tgt: r[5], qe: r[0] }));
    const now = Date.now();
    const series = [];
    for (const [p, col, lab] of [[q, C.an, 'This quarter'], [y, '#3a63c4', 'This fiscal year']]) {
      if (!p || !p.eps_trend) continue;
      const tr = p.eps_trend, pts = [[90, tr['90daysAgo']], [60, tr['60daysAgo']], [30, tr['30daysAgo']], [7, tr['7daysAgo']], [0, tr.current]].filter((x) => fin(x[1])).map(([d, v]) => [now - d * 864e5, v]);
      const key = lab === 'This quarter' ? 'q' : 'y';
      const extra = snaps.filter((sn) => fin(sn[key]) && (key === 'y' || sn.qe === p.end) && sn.t < now - 95 * 864e5).map((sn) => [sn.t, sn[key]]);
      const all = extra.concat(pts).sort((u, v) => u[0] - v[0]);
      if (all.length >= 2) series.push({ pts: all, col, lab: `${lab} EPS (${day(p.end)})` });
    }
    if (!series.length) return '';
    const W = 400, H = 170, L = 46, R = 10, T = 10, B = 22;
    const out = series.map((sr) => {
      const xs = sr.pts.map((p) => p[0]), vs = sr.pts.map((p) => p[1]);
      let v0 = Math.min(...vs), v1 = Math.max(...vs); if (v1 - v0 < Math.abs(v1) * 0.01) { v0 -= Math.abs(v1) * 0.02 + 0.01; v1 += Math.abs(v1) * 0.02 + 0.01; }
      const X = (t) => L + (t - xs[0]) / ((xs[xs.length - 1] - xs[0]) || 1) * (W - L - R), Y = (v) => T + (v1 - v) / (v1 - v0) * (H - T - B);
      let s = `<div><b style="font-size:13px">${esc(sr.lab)}</b><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sr.lab)}">`;
      for (let k = 0; k <= 3; k++) { const v = v0 + (v1 - v0) * k / 3; s += `<line class="cv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end">${usd(v)}</text>`; }
      s += `<path d="${sr.pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${sr.col}" stroke-width="2"/>`;
      sr.pts.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="2.6" fill="${sr.col}"><title>${new Date(p[0]).toISOString().slice(0, 10)}: ${usd(p[1], 3)}</title></circle>`; });
      s += `<text x="${L}" y="${H - 5}">${new Date(xs[0]).toISOString().slice(0, 10)}</text><text x="${W - R}" y="${H - 5}" text-anchor="end">now</text></svg></div>`;
      return s;
    });
    return `<h3>How the EPS consensus moved</h3><p class="cv-sub">The consensus now, 7, 30, 60 and 90 days ago${snaps.length > 1 ? ', with our daily snapshots before that' : ''}. Rising estimates into a report are usually read as a good sign.</p><div class="cv-two">${out.join('')}</div>`;
  }
  function surprises(doc) {
    const S = (doc.surprises || []).filter((s) => fin(s.eps_est) && fin(s.eps_act));
    if (!S.length) return '';
    const W = 820, H = 170, L = 46, R = 10, T = 10, B = 34, n = S.length;
    const vs = S.map((s) => s.surprise).filter(fin), m = Math.max(0.02, ...vs.map(Math.abs));
    const bw = Math.min(48, (W - L - R) / n * 0.7), X = (i) => L + (i + 0.5) * (W - L - R) / n, Y = (v) => T + (m - v) / (2 * m) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Earnings surprises">`;
    for (const v of [-m, -m / 2, 0, m / 2, m]) s += `<line class="cv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end">${spct(v, 0)}</text>`;
    S.forEach((x, i) => {
      const v = fin(x.surprise) ? x.surprise : 0, col = v >= 0 ? C.good : C.bad;
      s += `<rect x="${X(i) - bw / 2}" y="${Math.min(Y(0), Y(v))}" width="${bw}" height="${Math.max(1, Math.abs(Y(v) - Y(0)))}" rx="2" fill="${col}"><title>Quarter ending ${x.quarter}${x.reported ? ', reported ' + x.reported : ''}: estimate ${usd(x.eps_est)}, actual ${usd(x.eps_act)} (${spct(x.surprise)})</title></rect>`;
      s += `<text x="${X(i)}" y="${H - 18}" text-anchor="middle">${esc(x.quarter.slice(2, 7))}</text>`;
    });
    s += '</svg>';
    const beat = S.filter((x) => x.eps_act > x.eps_est).length;
    return `<h3>Estimate vs actual</h3><p class="cv-sub">Reported EPS against the consensus just before each report: beat ${beat} of the last ${S.length} quarters${fin(doc.beat_rate) ? ` (last eight: ${pct(doc.beat_rate)})` : ''}. Companies beat about three times in four on average — guidance is set to be beaten — so the size of the beat matters more than the beat.</p>${s}` +
      `<details><summary>Table</summary>${tbl(['Quarter ending', 'Reported', 'Consensus EPS', 'Actual EPS', 'Surprise'], S.slice().reverse().map((x) => [esc(x.quarter), esc(x.reported || '—'), usd(x.eps_est, 3), usd(x.eps_act, 3), `<span class="${x.surprise >= 0 ? 'cv-good' : 'cv-bad'}">${spct(x.surprise)}</span>`]), [2, 3, 4])}</details>`;
  }
  function ratings(a) {
    const r = a.rating || {}, tr = (r.trend || [])[0];
    let s = '';
    if (tr) {
      const [, sb, b, h, se, ss] = tr, tot = (sb || 0) + (b || 0) + (h || 0) + (se || 0) + (ss || 0);
      if (tot) {
        const cols = [['Strong buy', sb, '#1e8449'], ['Buy', b, '#58b26a'], ['Hold', h, '#c9b037'], ['Sell', se, '#e07b39'], ['Strong sell', ss, '#c0392b']];
        s += `<div class="cv-rating">${cols.filter((c) => c[1]).map((c) => `<i style="width:${100 * c[1] / tot}%;background:${c[2]}" title="${c[0]}: ${c[1]}"></i>`).join('')}</div>
          <div class="cv-legend">${cols.map((c) => `<span style="--k:${c[2]}">${c[0]} ${c[1] || 0}</span>`).join('')}</div>`;
      }
    }
    const A = (a.actions || []).slice(0, 10);
    if (A.length) s += tbl(['Date', 'Firm', 'Rating', 'Price target'], A.map((x) => [esc(x.date), esc(x.firm), `${x.from && x.from !== x.to ? esc(x.from) + ' → ' : ''}<b>${esc(x.to || '')}</b> <span class="cv-tag">${esc(x.action || '')}</span>`,
      fin(x.target) ? `${fin(x.prior) && x.prior !== x.target ? usd(x.prior, 0) + ' → ' : ''}${usd(x.target, 0)}` : '—']), [3]);
    return s ? `<h3>Ratings and recent analyst actions</h3><p class="cv-sub">Mean rating ${fin(r.mean) ? num(r.mean, 2) : '—'} on a 1 (strong buy) – 5 (strong sell) scale${r.key ? ' · ' + esc(String(r.key).replace('_', ' ')) : ''}.</p>${s}` : '';
  }

  // ---------- prediction markets ----------
  function ladderSvg(st, unit, x) {
    if (x && x.strikes && x.p) {                              // the hourly reading (app/ladders.py) is fresher than the 3-hourly one
      const K2 = [], P2 = [];
      x.strikes.forEach((k, i) => { if (fin(x.p[i])) { K2.push(k); P2.push(x.p[i]); } });
      if (K2.length >= 2) st = { strikes: K2, p_above: P2, median: { value: x.median } };
    }
    if (!st || !st.strikes || st.strikes.length < 2) return '';
    const K = st.strikes, P = st.p_above, W = 380, H = x ? 150 : 120, L = 40, R = 8, T = 8, B = x ? 44 : 20;
    const o = (x && x.options) || {}, cb = (x && x.combined) || {};
    const span = K[K.length - 1] - K[0] || 1;
    const near = (v) => fin(v) && v >= K[0] - span * 0.6 && v <= K[K.length - 1] + span * 0.6;
    const ext = x ? [x.spot, x.ev, o.max_pain, o.put_wall, o.call_wall, cb.lo, cb.hi].filter(near) : [];
    const k0 = Math.min(K[0], ...ext), k1 = Math.max(K[K.length - 1], ...ext);
    const X = (k) => L + (k - k0) / ((k1 - k0) || 1) * (W - L - R), Y = (p) => T + (1 - p) * (H - T - B);
    const f = unit === 'mcap' ? big : unit === 'pts' ? pts : (v) => usd(v, 0), f2 = unit === 'pts' ? pts : (v) => usd(v);
    let s = `<svg viewBox="0 0 ${W} ${H}" style="max-width:400px" role="img" aria-label="Probability the value ends above each level">`;
    for (const p of [0, 0.5, 1]) s += `<line class="cv-grid" x1="${L}" x2="${W - R}" y1="${Y(p)}" y2="${Y(p)}"/><text x="${L - 4}" y="${Y(p) + 4}" text-anchor="end">${pct(p)}</text>`;
    if (x && near(cb.lo) && near(cb.hi)) s += `<rect x="${X(cb.lo)}" y="${T}" width="${Math.max(1, X(cb.hi) - X(cb.lo))}" height="${H - T - B}" fill="${C.cmb}" fill-opacity="0.09"><title>Combined 80% range ${f2(cb.lo)} – ${f2(cb.hi)}</title></rect>`;
    if (x && x.op) {
      const pts2 = x.strikes.map((k, i) => [k, x.op[i]]).filter((q) => fin(q[1]));
      if (pts2.length >= 2) s += `<path d="${pts2.map((q, i) => (i ? 'L' : 'M') + X(q[0]).toFixed(1) + ',' + Y(q[1]).toFixed(1)).join('')}" fill="none" stroke="${C.ks}" stroke-width="1.6" stroke-dasharray="4 3"><title>Options-implied P(close above K)${o.exp ? ' — ' + o.exp + ' expiry' : ''}</title></path>`;
    }
    s += `<path d="${K.map((k, i) => (i ? 'L' : 'M') + X(k).toFixed(1) + ',' + Y(P[i]).toFixed(1)).join('')}" fill="none" stroke="${C.pm}" stroke-width="2"/>`;
    K.forEach((k, i) => { s += `<circle cx="${X(k)}" cy="${Y(P[i])}" r="2.6" fill="${C.pm}"><title>P(above ${f(k)}) = ${pct(P[i], 1)}${x && x.op && fin(x.op[x.strikes.indexOf(k)]) ? ' · options ' + pct(x.op[x.strikes.indexOf(k)], 1) : ''}</title></circle>`; });
    if (st.median && fin(st.median.value)) s += `<line x1="${X(st.median.value)}" x2="${X(st.median.value)}" y1="${T}" y2="${H - B}" stroke="${C.pm}" stroke-dasharray="3 3"><title>Median ${f2(st.median.value)}</title></line>`;
    if (x) {
      const vline = (v, col, label, dash, w = 1.4) => (near(v) ? `<line x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H - B}" stroke="${col}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''}><title>${esc(label)} ${f2(v)}</title></line>` : '');
      s += vline(x.ev, C.pm, 'Expected value', '', 2.4) + vline(x.spot, C.ink, 'Price now', '1 2') + vline(o.max_pain, C.mp, 'Max pain (' + (o.exp || '') + ')', '5 3');
      const tick = (v, col, label, up) => (near(v) ? `<path d="M${X(v) - 5},${H - B + (up ? 12 : 4)} L${X(v) + 5},${H - B + (up ? 12 : 4)} L${X(v)},${H - B + (up ? 4 : 12)} Z" fill="${col}"><title>${esc(label)} ${f2(v)}</title></path>` : '');
      s += tick(o.put_wall, C.good, 'Put wall', true) + tick(o.call_wall, C.bad, 'Call wall', false);
      s += `<text x="${L}" y="${H - 5}">${f(k0)}</text><text x="${W - R}" y="${H - 5}" text-anchor="end">${f(k1)}</text></svg>`;
      s += `<div class="cv-legend" style="margin-top:0"><span style="--k:${C.pm}">ladder · expected value (solid) · median (dashed)</span>${x.op ? `<span style="--k:${C.ks}">options-implied</span>` : ''}<span style="--k:${C.ink}">price now</span>${fin(o.max_pain) ? `<span style="--k:${C.mp}">max pain</span>` : ''}${fin(o.put_wall) ? `<span style="--k:${C.good}">put wall ▲</span><span style="--k:${C.bad}">call wall ▼</span>` : ''}${fin(cb.lo) ? `<span style="--k:${C.cmb}">combined 80% range</span>` : ''}</div>`;
      return s;
    }
    s += `<text x="${L}" y="${H - 5}">${f(K[0])}</text><text x="${W - R}" y="${H - 5}" text-anchor="end">${f(K[K.length - 1])}</text></svg>`;
    return s;
  }
  function ladOf(lad, m) {
    if (!lad || !lad.open) return null;
    return lad.open.find((x) => x.url === m.url && (m.source !== 'kalshi' || (x.end === m.end && x.kind === m.kind))) || null;
  }
  function marketBox(m, a, lad) {
    const src = m.source === 'kalshi' ? 'Kalshi' : 'Polymarket', col = m.source === 'kalshi' ? C.ks : C.pm;
    const meta = [src, KIND[m.kind] || m.kind, m.end ? (m.closed ? 'ended ' : 'ends ') + day(m.end) : '', fin(m.volume) && m.volume > 0 ? 'volume ' + big(m.volume).replace('$', m.source === 'kalshi' ? '' : '$') : ''].filter(Boolean).join(' · ');
    let body = '';
    if (m.kind === 'beat') {
      const q0 = (a.periods || []).find((p) => p.period === '0q') || {};
      body = pbar('Beats', m.p, col) + `<div class="cv-sub">Beat = ${m.basis === 'gaap' ? 'GAAP' : 'adjusted (non-GAAP)'} EPS above ${usd(m.eps_strike)} — the Street consensus when the market opened${fin((q0.eps || {}).avg) ? `; today's consensus is ${usd(q0.eps.avg)}` : ''}. Report expected ${day(m.report_date)}.${m.resolved != null ? ` <b class="${m.resolved ? 'cv-good' : 'cv-bad'}">Resolved: ${m.resolved ? 'beat' : 'missed'}</b>` : ''}</div>`;
    } else if (m.kind === 'above' || m.kind === 'bracket' || m.kind === 'mcap') {
      const st = m.stats, ip = m.implied_price;
      const f = mfmt(m);
      if (m.closed && m.actual) body = `<div class="cv-sub">Ended between ${f(m.actual[0])} and ${m.actual[1] == null ? 'above' : f(m.actual[1])}.</div>`;
      else if (st) {
        const bound = (q) => (q && q.bound === 'below' ? '≤ ' : q && q.bound === 'above' ? '≥ ' : '');
        const x = m.kind !== 'mcap' ? ladOf(lad, m) : null, ev = x ? x.ev : st.mean && st.mean.value;
        body = `<div class="cv-sub">${fin(ev) ? `Expected value <b>${f(ev)}</b>${x && fin(x.spot) ? ` (${spct(ev / x.spot - 1)} from ${f(x.spot)})` : ''} · ` : ''}Implied median <b>${bound(st.median)}${f(st.median && st.median.value)}</b> · 80% range ${bound(st.q10)}${f(st.q10 && st.q10.value)} – ${bound(st.q90)}${f(st.q90 && st.q90.value)}${m.kind === 'mcap' && ip && fin(ip.median) ? ` · per share ≈ ${usd(ip.median)}` : ''}${m.index && !m.points && ip && fin(ip.median) ? ` · in index points ≈ ${pts(ip.median)}` : ''}${st.overround && st.overround > 1.05 ? ` · prices sum to ${pct(st.overround)}, normalised` : ''}${x && x.options && fin(x.options.max_pain) ? ` · options ${x.options.exact ? '' : '(next expiry ' + day(x.options.exp) + ') '}max pain ${f(x.options.max_pain)}, put wall ${f(x.options.put_wall)}, call wall ${f(x.options.call_wall)}` : ''}${x && x.combined && fin(x.combined.lo) ? ` · combined 80% range <b>${f(x.combined.lo)} – ${f(x.combined.hi)}</b>` : ''}${x ? ` · read ${esc(String(x.as_of).slice(5).replace('T', ' '))}:00 UTC` : ''}</div>` + ladderSvg(st, m.kind === 'mcap' ? 'mcap' : m.index && m.points ? 'pts' : 'usd', x);
      }
    } else if (m.kind === 'metric') {
      const st = m.stats, u = m.unit || '';
      const q0 = (a.periods || []).find((p) => p.period === '0q') || {};
      if (m.closed && m.actual) body = `<div class="cv-sub">Ended between ${unitFmt(m.actual[0], u)} and ${m.actual[1] == null ? 'above' : unitFmt(m.actual[1], u)}.</div>`;
      else if (st && st.median) {
        const bound = (q) => (q && q.bound === 'below' ? '≤ ' : q && q.bound === 'above' ? '≥ ' : '');
        body = `<div class="cv-sub">Implied median <b>${bound(st.median)}${unitFmt(st.median.value, u)}</b>${st.q10 ? ` · 80% range ${bound(st.q10)}${unitFmt(st.q10.value, u)} – ${bound(st.q90)}${unitFmt(st.q90.value, u)}` : ''}${/total (operating )?revenue|net sales/i.test(m.title || '') && fin((q0.rev || {}).avg) ? ` · analysts' revenue consensus for the quarter ${big(q0.rev.avg)}` : ''}</div>`;
      }
      body += (m.outcomes || []).filter((o) => fin(o.p)).slice(0, 10).map((o) => pbar(o.q, o.p, col)).join('');
    } else if (m.kind === 'updown') {
      body = pbar('Closes up', m.p, col) + (m.resolved != null ? `<div class="cv-sub">Resolved: ${m.resolved ? 'up' : 'down'}</div>` : '');
    } else if (m.kind === 'hit') {
      const hi = m.stats_high && m.stats_high.median, lo = m.stats_low && m.stats_low.median;
      const f = mfmt(m);
      body = `<div class="cv-sub">Even odds of touching ${hi && fin(hi.value) ? f(hi.value) : '—'} on the way up${lo || !m.index ? ` and ${lo && fin(lo.value) ? f(lo.value) : '—'} on the way down` : ''} before the end.</div>`;
      const O = (m.outcomes || []).filter((o) => fin(o.p) && o.p > 0.02 && o.p < 0.98);
      body += O.slice(0, 10).map((o) => pbar(o.q, o.p, col)).join('');
    } else if (m.kind === 'kpi' && m.stats && m.stats.median) {
      body = `<div class="cv-sub">Implied median ${num(m.stats.median.value, 2)}${m.stats.q10 ? ` · 80% range ${num(m.stats.q10.value, 2)} – ${num(m.stats.q90.value, 2)}` : ''}</div>` + (m.outcomes || []).slice(0, 8).map((o) => pbar(o.q, o.p, col)).join('');
    } else {
      body = (m.outcomes || []).slice(0, 8).map((o) => pbar(o.q, o.p, col) + (o.resolved != null ? `<div class="cv-sub">Resolved ${o.resolved ? 'yes' : 'no'}</div>` : '')).join('');
    }
    return `<div class="cv-mk"><h4>${link(m.url, m.title || '')}${m.subtitle ? ` <span class="cv-tag">${esc(m.subtitle)}</span>` : ''}</h4><div class="cv-meta">${esc(meta)}</div>${body}</div>`;
  }
  function markets(doc, a, lad) {
    const M = doc.markets || [];
    if (!M.length && doc.unit === 'pts') return `<h3>Prediction markets</h3><p class="cv-sub">No Polymarket or Kalshi market about this index is open right now.</p>`;
    if (!M.length) return `<h3>Prediction markets</h3><p class="cv-sub">No Polymarket or Kalshi market about this company is open. They list markets for the most-traded names (earnings beats for a few hundred companies each season; price ladders and market caps for the largest; KPIs such as deliveries or subscribers for some).</p>`;
    const order = ['beat', 'metric', 'above', 'bracket', 'mcap', 'hit', 'kpi', 'mention', 'updown', 'other'];
    const yd = new Date(Date.now() - 864e5).toISOString().slice(0, 10);
    const isLive = (m) => !m.closed && (!m.end || m.end >= yd);
    const live = M.filter(isLive).sort((x, y) => order.indexOf(x.kind) - order.indexOf(y.kind) || String(x.end).localeCompare(String(y.end)));
    const done = M.filter((m) => !isLive(m));
    const head = `<h3>Prediction markets <span class="cv-tag">${live.length} open</span></h3><p class="cv-sub">Prices on Polymarket and Kalshi are what traders pay for a contract that pays $1 if the event happens — a crowd probability. Ladders of "closes above $K" contracts give a whole distribution of the price; we fit the probabilities to fall with the strike and read the median and the 80% range from it.${doc.unit === 'pts' ? ' Kalshi lists ranges for the close of the day, the week, the month and the year; Polymarket some ladders in ETF dollars (SPY, QQQ), which we turn into index points at today\'s ratio of the two.' : ''}</p>`;
    const first = live.slice(0, 8).map((m) => marketBox(m, a, lad)).join('');
    const rest = live.slice(8).map((m) => marketBox(m, a, lad)).join('');
    return head + first + (rest ? `<details><summary>${live.length - 8} more open markets</summary>${rest}</details>` : '') +
      (done.length ? `<details><summary>Recently resolved (${done.length})</summary>${done.slice(0, 20).map((m) => marketBox(m, a, lad)).join('')}</details>` : '');
  }
  function track(doc) {
    const out = [];
    const cal = (doc.calibration || []).filter((c) => fin(c.p_day_before) && c.yes != null);
    if (cal.length) out.push(tbl(['Report', 'EPS line', 'Beat price a day before', 'Result'], cal.slice().reverse().map((c) => [esc(c.report_date || '—'), usd(c.eps_strike), pct(c.p_day_before), `<b class="${c.yes ? 'cv-good' : 'cv-bad'}">${c.yes ? 'beat' : 'missed'}</b>`]), [1, 2]));
    const pt = (doc.price_track || []);
    if (pt.length) out.push(tbl(['Market', 'Date', 'Implied median (last before the date)', '80% range', 'Ended', 'Error'], pt.map((r) => {
      const f = r.kind === 'mcap' ? big : r.kind === 'metric' ? (v) => unitFmt(v, r.unit) : (v) => usd(v);
      return [esc(r.title), esc(r.end), f(r.median), `${f(r.q10)} – ${f(r.q90)}`, `${f(r.actual[0])} – ${r.actual[1] == null ? '…' : f(r.actual[1])}`, `<span class="${r.inside80 ? 'cv-good' : 'cv-bad'}">${spct(r.err_pct / 100)}${r.inside80 ? ' · inside' : ' · outside'}</span>`];
    }), [2, 3, 4, 5]));
    const S = (doc.surprises || []).filter((s) => fin(s.surprise));
    if (!out.length && !S.length) return '';
    return `<h3>How the forecasts did</h3><p class="cv-sub">Every prediction market's last price before the result is kept, then scored when it resolves. The track record of all companies is in the Disclosure Hub → Consensus → Track record.</p>${out.join('') || '<p class="cv-sub">No market about this company has resolved since tracking began.</p>'}`;
  }

  // ---------- closing-price ladders, read every hour (app/ladders.py): expected value, the options' view, the combined
  // range by date, the hourly history and the backtest. Read from the branch ladder-history (data/remote.json → ladders)
  // so the page is at most an hour old; data/ladders/ (the last site build) when that is not reachable. ----------
  const BASE = ((typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || '').replace(/[^/]*$/, '');
  let remoteP = null;
  const remoteCfg = () => remoteP || (remoteP = fetch(BASE + 'data/remote.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
  const ladFile = (path) => remoteCfg().then((cfg) => {
    const local = () => fetch(BASE + 'data/ladders/' + path).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (!cfg || !cfg.ladders) return local();
    return fetch(cfg.ladders + path).then((r) => (r.ok ? r.json() : local())).catch(local);
  });
  const LAD = {};
  function ladFor(el, doc, key, draw) {
    if (!key) return null;
    if (LAD[key] !== undefined) return LAD[key] || null;
    LAD[key] = null;
    ladFile('t/' + String(key).replace(/\./g, '-') + '.json').then((d) => {
      LAD[key] = d || false;
      if (d && el.isConnected !== false && el.__cv === doc) draw(el, doc);
    });
    return null;
  }
  const PERIOD_L = { day: 'day', week: 'week', month: 'month', year: 'year', other: '' };
  // the post (posts.js, loaded once from the same folder): Polymarket vs Kalshi vs the options, for X
  let postsP = null;
  const needPosts = (el, doc, draw) => {
    if (window.FFPosts || typeof document === 'undefined') return;
    if (!postsP) postsP = new Promise((ok) => { const sc = document.createElement('script'); sc.src = BASE + 'posts.js'; sc.onload = ok; sc.onerror = ok; document.head.appendChild(sc); });
    postsP.then(() => { if (window.FFPosts && el.isConnected !== false && el.__cv === doc) draw(el, doc); });
  };
  function postBox(el, doc, lad, draw, ticker) {
    if (!window.FFPosts) { needPosts(el, doc, draw); return ''; }
    const it = window.FFPosts.build('markets', { ticker: ticker || doc.ticker || doc.short, cik: doc.cik, name: doc.name || doc.short || doc.ticker, cons: doc, lad: lad || null, opt: null });
    return it ? window.FFPosts.box(it) : '';
  }
  const fp = (v) => (fin(v) ? num(v, Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const hts = (k) => Date.parse(k + ':00:00Z');
  const niceTicks = (a, b, n) => {
    const raw = (b - a) / n, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), st = [1, 2, 2.5, 5, 10].map((x) => x * mag).find((x) => x >= raw) || raw;
    const out = []; for (let v = Math.ceil(a / st) * st; v <= b + 1e-9; v += st) out.push(+v.toFixed(10));
    return out;
  };

  function termSvg(L, f, conv) {
    const O = L.open.filter((m) => fin(conv(m, m.ev)));
    const H0 = (L.hourly || []).map(([k, v]) => [hts(k), v]).filter((p) => fin(p[1]));
    if (!O.length) return '';
    const now = Date.now(), spot = fin(L.spot) ? L.spot : (H0.length ? H0[H0.length - 1][1] : null);
    const past = H0.filter((p) => p[0] >= now - 5 * 864e5);
    const ends = [...new Set(O.map((m) => m.end))].sort();
    const tEnd = (e) => Date.parse(e + 'T20:00:00Z');
    const tmax = Math.max(...ends.map(tEnd)) + 864e5 / 2, t0 = past.length ? past[0][0] : now - 864e5;
    const W = 820, Hh = 320, Lm = 58, R = 16, T = 14, B = 34, WP = (W - Lm - R) * 0.26;
    const X = (t) => (t <= now ? Lm + (t - t0) / ((now - t0) || 1) * WP : Lm + WP + Math.sqrt((t - now) / ((tmax - now) || 1)) * (W - Lm - R - WP));
    const vals = past.map((p) => p[1]).concat([spot]);
    for (const m of O) {
      const o = m.options || {}, c = m.combined || {};
      vals.push(...[m.ev, m.q10, m.q90, o.q10, o.q90, o.max_pain, o.put_wall, o.call_wall, c.lo, c.hi].map((v) => conv(m, v)));
    }
    const vs = vals.filter(fin);
    const med = vs.slice().sort((a, b) => a - b)[Math.floor(vs.length / 2)];
    const ok = vs.filter((v) => Math.abs(v / med - 1) < 0.35);    // a wall far away does not squash the chart
    let y0 = Math.min(...ok), y1 = Math.max(...ok); const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
    const Y = (v) => T + (y1 - v) / (y1 - y0) * (Hh - T - B), inY = (v) => fin(v) && v >= y0 && v <= y1;
    let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Expected close by date">`;
    for (const v of niceTicks(y0, y1, 5)) s += `<line class="cv-grid" x1="${Lm}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${Lm - 6}" y="${Y(v) + 4}" text-anchor="end">${f(v)}</text>`;
    s += `<line x1="${X(now)}" x2="${X(now)}" y1="${T}" y2="${Hh - B}" stroke="${C.mute}" stroke-dasharray="3 3"/><text x="${X(now) + 4}" y="${T + 10}">now</text>`;
    if (past.length >= 2) s += `<path d="${past.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${C.ink}" stroke-width="1.5"><title>Hourly price, last 5 days</title></path>`;
    const byEnd = ends.map((e) => O.filter((m) => m.end === e));
    const pick = (ms) => ms.find((m) => m.kind === 'above') || ms[0];
    // the combined cone: from the price now through each date's combined range
    const cone = byEnd.map((ms) => { const m = pick(ms), c = m.combined || {}; return [tEnd(m.end), conv(m, c.lo), conv(m, c.center), conv(m, c.hi)]; }).filter((q) => fin(q[1]) && fin(q[3]));
    if (cone.length && fin(spot)) {
      const up = [[now, spot]].concat(cone.map((q) => [q[0], q[3]])), dn = [[now, spot]].concat(cone.map((q) => [q[0], q[1]]));
      s += `<path d="${up.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(Math.min(y1, Math.max(y0, p[1]))).toFixed(1)).join('')}${dn.slice().reverse().map((p) => 'L' + X(p[0]).toFixed(1) + ',' + Y(Math.min(y1, Math.max(y0, p[1]))).toFixed(1)).join('')}Z" fill="${C.cmb}" fill-opacity="0.10" stroke="none"><title>Combined 80% range: price, expected value, max pain and walls</title></path>`;
      s += `<path d="${[[now, spot]].concat(cone.map((q) => [q[0], q[2]])).map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${C.cmb}" stroke-width="1.4" stroke-dasharray="5 3"><title>Combined centre</title></path>`;
    }
    const line = (pts2, col, w, dash, label) => (pts2.length >= 1 ? `<path d="${pts2.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${col}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''}><title>${esc(label)}</title></path>` : '');
    const evp = [[now, spot]].concat(byEnd.map((ms) => { const m = pick(ms); return [tEnd(m.end), conv(m, m.ev)]; })).filter((p) => fin(p[1]));
    const mpp = byEnd.map((ms) => { const m = pick(ms); return [tEnd(m.end), conv(m, (m.options || {}).max_pain)]; }).filter((p) => inY(p[1]));
    const cwp = byEnd.map((ms) => { const m = pick(ms); return [tEnd(m.end), conv(m, (m.options || {}).call_wall)]; }).filter((p) => inY(p[1]));
    const pwp = byEnd.map((ms) => { const m = pick(ms); return [tEnd(m.end), conv(m, (m.options || {}).put_wall)]; }).filter((p) => inY(p[1]));
    s += line(cwp, C.bad, 1.2, '2 3', 'Call wall by expiry') + line(pwp, C.good, 1.2, '2 3', 'Put wall by expiry') + line(mpp, C.mp, 1.4, '5 3', 'Max pain by expiry') + line(evp, C.pm, 2.2, '', 'Expected value by date');
    byEnd.forEach((ms) => {
      ms.forEach((m, j) => {
        const t = tEnd(m.end), x = X(t) + (j - (ms.length - 1) / 2) * 9, o = m.options || {}, c = m.combined || {};
        const lo = conv(m, m.q10), hi = conv(m, m.q90), ev = conv(m, m.ev);
        const tip = `${m.title} — expected value ${f(ev)}, median ${f(conv(m, m.median))}, ladder 80% ${f(lo)} – ${f(hi)}${fin(o.q10) ? `; options 80% ${f(conv(m, o.q10))} – ${f(conv(m, o.q90))}` : ''}${fin(o.max_pain) ? `; max pain ${f(conv(m, o.max_pain))}, put wall ${f(conv(m, o.put_wall))}, call wall ${f(conv(m, o.call_wall))} (${o.exact ? '' : 'next expiry '}${o.exp})` : ''}${fin(c.lo) ? `; combined ${f(conv(m, c.lo))} – ${f(conv(m, c.hi))}` : ''}`;
        s += `<g><title>${esc(tip)}</title>`;
        if (fin(lo) && fin(hi)) s += `<rect x="${x - 3}" y="${Y(Math.min(y1, hi))}" width="6" height="${Math.max(1, Y(Math.max(y0, lo)) - Y(Math.min(y1, hi)))}" rx="2" fill="${C.pm}" fill-opacity="0.2" stroke="${C.pm}" stroke-width="0.8"/>`;
        if (fin(o.q10) && fin(o.q90)) { const a = conv(m, o.q10), b = conv(m, o.q90); s += `<rect x="${x + 4}" y="${Y(Math.min(y1, b))}" width="4" height="${Math.max(1, Y(Math.max(y0, a)) - Y(Math.min(y1, b)))}" rx="1.5" fill="${C.ks}" fill-opacity="0.25" stroke="${C.ks}" stroke-width="0.8"/>`; }
        if (fin(ev)) s += `<circle cx="${x}" cy="${Y(ev)}" r="4" fill="${C.pm}" stroke="#fff" stroke-width="1"/>`;
        if (inY(conv(m, o.max_pain))) s += `<path d="M${x},${Y(conv(m, o.max_pain)) - 5} L${x + 5},${Y(conv(m, o.max_pain))} L${x},${Y(conv(m, o.max_pain)) + 5} L${x - 5},${Y(conv(m, o.max_pain))} Z" fill="${C.mp}"/>`;
        s += '</g>';
      });
      const m0 = pick(ms);
      s += `<text x="${X(tEnd(m0.end))}" y="${Hh - 18}" text-anchor="middle">${esc(m0.end.slice(5))}</text><text x="${X(tEnd(m0.end))}" y="${Hh - 6}" text-anchor="middle" style="font-size:10px">${esc(PERIOD_L[m0.period] || '')}</text>`;
    });
    if (fin(spot)) s += `<circle cx="${X(now)}" cy="${Y(spot)}" r="3.5" fill="${C.ink}"><title>Price now ${f(spot)}</title></circle>`;
    return s + '</svg>';
  }

  function hourSvg(m, f) {
    const R0 = (m.history || []).filter((r) => fin(r[1]) || fin(r[2]));
    if (R0.length < 2) return `<p class="cv-sub">One reading so far (${esc(String(m.as_of).replace('T', ' '))}:00 UTC) — a line appears after the next hours.</p>`;
    const t = R0.map((r) => hts(r[0])), W = 820, H = 230, L = 58, Rr = 16, T = 10, B = 24;
    const all = R0.flatMap((r) => [r[1], r[2], r[4], r[5], r[10], r[11]]).filter(fin);
    const med = all.slice().sort((a, b) => a - b)[Math.floor(all.length / 2)];
    const ok = all.concat(R0.flatMap((r) => [r[6], r[7], r[8]]).filter((v) => fin(v) && Math.abs(v / med - 1) < 0.12));
    let y0 = Math.min(...ok), y1 = Math.max(...ok); const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
    const X = (v) => L + (v - t[0]) / ((t[t.length - 1] - t[0]) || 1) * (W - L - Rr), Y = (v) => T + (y1 - v) / (y1 - y0) * (H - T - B);
    const path = (i, col, w, dash, label) => {
      let d = '', on = false;
      R0.forEach((r, j) => { if (fin(r[i]) && r[i] >= y0 && r[i] <= y1) { d += (on ? 'L' : 'M') + X(t[j]).toFixed(1) + ',' + Y(r[i]).toFixed(1); on = true; } else on = false; });
      return d ? `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''}><title>${esc(label)}</title></path>` : '';
    };
    const band = (a, b, col, op, label) => {
      const ix = R0.map((r, j) => j).filter((j) => fin(R0[j][a]) && fin(R0[j][b]));
      if (ix.length < 2) return '';
      const cl = (v) => Math.min(y1, Math.max(y0, v));
      return `<path d="${ix.map((j, k) => (k ? 'L' : 'M') + X(t[j]).toFixed(1) + ',' + Y(cl(R0[j][b])).toFixed(1)).join('')}${ix.slice().reverse().map((j) => 'L' + X(t[j]).toFixed(1) + ',' + Y(cl(R0[j][a])).toFixed(1)).join('')}Z" fill="${col}" fill-opacity="${op}"><title>${esc(label)}</title></path>`;
    };
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="The ladder hour by hour">`;
    for (const v of niceTicks(y0, y1, 4)) s += `<line class="cv-grid" x1="${L}" x2="${W - Rr}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${f(v)}</text>`;
    s += band(10, 11, C.cmb, 0.10, 'Combined 80% range') + band(4, 5, C.pm, 0.13, 'Ladder 80% range');
    s += path(7, C.bad, 1, '2 3', 'Call wall') + path(8, C.good, 1, '2 3', 'Put wall') + path(6, C.mp, 1.3, '5 3', 'Max pain') + path(3, C.pm, 1.1, '3 3', 'Ladder median') + path(9, C.cmb, 1.2, '5 3', 'Combined centre') + path(2, C.pm, 2.2, '', 'Expected value') + path(1, C.ink, 1.5, '', 'Price');
    const dayTicks = [...new Set(R0.map((r) => r[0].slice(0, 10)))];
    const every = Math.max(1, Math.ceil(dayTicks.length / 8));
    dayTicks.forEach((d, i) => { if (i % every) return; const tt = Date.parse(d + 'T00:00:00Z'); if (tt >= t[0]) s += `<text x="${X(tt)}" y="${H - 6}" text-anchor="middle">${esc(d.slice(5))}</text>`; });
    const lastR = R0[R0.length - 1];
    s += `<circle cx="${X(t[t.length - 1])}" cy="${Y(lastR[2] != null ? lastR[2] : lastR[1])}" r="3" fill="${C.pm}"/></svg>`;
    return s;
  }

  function btTable(rows, f) {
    const R = (rows || []).filter((r) => r.markets);
    if (!R.length) return '';
    const e = (v) => (fin(v) ? num(100 * v, 2) + '%' : '—'), c = (v) => (fin(v) ? pct(v) : '—'), b = (v) => (fin(v) ? num(v, 3) : '—');
    const t = tbl(['Before the close', 'Ladders', 'Error: price now', 'exp. value', 'median', 'max pain', 'combined', 'Inside 80%: ladder', 'options', 'walls', 'combined', 'Brier L · O'],
      R.map((r) => {
        const M = r.mae || {}, I = r.inside80 || {}, Bs = r.brier || {}, oo = r.oos;
        const best = Math.min(...['price', 'ev', 'median', 'max_pain', 'combined'].map((k) => M[k]).filter(fin));
        const cell = (k) => `<span class="${M[k] === best ? 'cv-good' : ''}">${e(M[k])}</span>`;
        return [esc(r.bucket), num(r.markets), cell('price'), cell('ev'), cell('median'), cell('max_pain'),
          cell('combined') + (oo ? `<br><span class="cv-sub">out of sample ${e(oo.mae && oo.mae.combined)}</span>` : ''),
          c(I.ladder), c(I.options), c(I.walls), c(I.combined) + (oo ? `<br><span class="cv-sub">out of sample ${c(oo.inside80)}</span>` : ''),
          `<span title="Brier score of P(close above K): ladder · options (on the readings where both had a view; the ladder alone when the options had none)">${b(fin(Bs.ladder) ? Bs.ladder : Bs.ladder_all)} · ${b(Bs.options)}</span>`];
      }), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    const mdl = R.map((r) => { const P = r.model || {}; return `<b>${esc(r.bucket)}</b>: centre = price + ${num(P.w_ev, 1)} × (exp. value − price) + ${num(P.w_mp, 1)} × (max pain − price), width × ${num(P.k, 2)} <span class="cv-sub">(${P.basis === 'backtest' ? 'fitted on ' + num(P.n) + ' ladders' : 'prior until ' + 20 + ' ladders resolve'})</span>`; });
    return t + `<p class="cv-sub" style="line-height:1.7">Combined model by horizon — ${mdl.join(' · ')}</p>`;
  }

  function ladPanel(L, f, page) {
    if (!L || (!(L.open || []).length && !(L.resolved || []).length)) return '';
    const conv = (m, v) => (fin(v) && fin(m.to_page) ? v * m.to_page : null);
    const O = L.open || [];
    let h = `<h3>Where the close is expected, by date <span class="cv-tag">read hourly</span></h3><p class="cv-sub">Every open "closes above ___" ladder and closing-price bracket on Polymarket and Kalshi for ${esc(page)}, read every hour. <b>Expected value</b> is the mean of the distribution the ladder implies (strikes fitted to fall with the price; the mass between two strikes at their middle, the tails from a log-normal fitted to the ladder). Beside it the options for the same date (CBOE, about 15 minutes late; the next expiry when none falls on the date): <b>max pain</b>, the <b>put wall</b> and <b>call wall</b> (the strikes with the most put and call open interest) and the options-implied 80% range. The <b>combined range</b> blends the price, the expected value and max pain for the centre and the ladder's, the options' and the walls' ranges for the width, with the weights fitted on every ladder that has resolved at the same horizon (the backtest below).${L.generated_at ? ` Updated ${esc(String(L.generated_at).slice(0, 16).replace('T', ' '))} UTC.` : ''}</p>`;
    if (O.length) {
      h += termSvg(L, f, conv);
      h += `<div class="cv-legend"><span style="--k:${C.ink}">price, last 5 days</span><span style="--k:${C.pm}">expected value (line) · ladder 80% (box)</span><span style="--k:${C.ks}">options 80%</span><span style="--k:${C.mp}">max pain ◆</span><span style="--k:${C.good}">put wall</span><span style="--k:${C.bad}">call wall</span><span style="--k:${C.cmb}">combined 80% range (cone) and centre</span></div>`;
      h += tbl(['Close on', 'Expected value', 'Ladder: median · 80%', 'Options: 80% · expiry', 'Max pain', 'Put – call wall', 'Combined 80%'], O.map((m) => {
        const o = m.options || {}, c = m.combined || {}, sp = L.spot;
        const vs = (v) => (fin(v) && fin(sp) ? ` <span class="cv-sub">${spct(v / sp - 1)}</span>` : '');
        return [`<a href="${esc(m.url)}" target="_blank" rel="noopener" title="${esc(m.title || '')}"><b>${day(m.end).slice(5)}</b></a> <span class="cv-tag">${esc(PERIOD_L[m.period] || m.kind)}${m.kind === 'bracket' ? ' · brackets' : ''}</span><br><span class="cv-sub">${m.source === 'kalshi' ? 'Kalshi' : 'Polymarket'} · ${num(m.readings)} h</span>`,
          `<b>${f(conv(m, m.ev))}</b>${vs(conv(m, m.ev))}`, `${f(conv(m, m.median))}<br><span class="cv-sub">${f(conv(m, m.q10))} – ${f(conv(m, m.q90))}</span>`,
          fin(o.q10) ? `${f(conv(m, o.q10))} – ${f(conv(m, o.q90))}<br><span class="cv-sub">${esc((o.exp || '').slice(5))}${o.exact ? '' : ' (next)'}${fin(o.atm_iv) ? ' · IV ' + pct(o.atm_iv) : ''}</span>` : '<span class="cv-sub">no chain</span>',
          `${f(conv(m, o.max_pain))}${vs(conv(m, o.max_pain))}`, fin(o.put_wall) ? `${f(conv(m, o.put_wall))} – ${f(conv(m, o.call_wall))}` : '—',
          fin(c.lo) ? `<b>${f(conv(m, c.lo))} – ${f(conv(m, c.hi))}</b><br><span class="cv-sub">centre ${f(conv(m, c.center))} · ${c.basis === 'backtest' ? 'fitted' : 'prior'}</span>` : '—'];
      }), [1, 2, 3, 4, 5, 6]);
      h += `<h3>Hour by hour</h3><p class="cv-sub">Each ladder since it was listed: the price, the expected value and median, the ladder's 80% range (shaded), the combined range, max pain and the walls. Hours before we began reading are rebuilt from Polymarket's price history (without the options).</p>`;
      h += `<div class="cv-tabs">${O.map((m, i) => `<button class="cv-show${i ? '' : ' on'}" data-ladh="${i}">${esc(day(m.end).slice(5))} ${esc(PERIOD_L[m.period] || '')}${m.kind === 'bracket' ? ' (brackets)' : ''}</button>`).join(' ')}</div>`;
      h += O.map((m, i) => `<div class="cv-ladh" data-ladh-box="${i}"${i ? ' hidden' : ''}>${hourSvg(m, m.to_page === 1 || !m.to_page ? f : (v) => (fin(v) ? fp(v) : '—'))}</div>`).join('');
      h += `<div class="cv-legend"><span style="--k:${C.ink}">price</span><span style="--k:${C.pm}">expected value · median (dashed) · ladder 80%</span><span style="--k:${C.cmb}">combined</span><span style="--k:${C.mp}">max pain</span><span style="--k:${C.good}">put wall</span><span style="--k:${C.bad}">call wall</span></div>`;
    }
    const D = L.resolved || [];
    if (D.length) {
      h += `<h3>Resolved ladders</h3>` + tbl(['Date', 'Ladder', 'Close', 'Expected value a day before', 'Last reading', 'Inside the ladder\'s 80%?'], D.slice(0, 15).map((r) => {
        const er = (v) => (fin(v) && fin(r.actual) ? `<span class="${Math.abs(v / r.actual - 1) < 0.01 ? 'cv-good' : ''}">${spct(v / r.actual - 1)}</span>` : '');
        const d1 = r.day_before || {}, l = r.last || {};
        const inside = fin(l.q10) && fin(l.q90) ? (r.actual >= l.q10 && r.actual <= l.q90) : null;
        return [day(r.end), link(r.url, r.title || ''), `<b>${f(r.actual)}</b>`, fin(d1.ev) ? `${f(d1.ev)} ${er(d1.ev)}` : '—', fin(l.ev) ? `${f(l.ev)} ${er(l.ev)}` : '—', inside == null ? '—' : `<b class="${inside ? 'cv-good' : 'cv-bad'}">${inside ? 'yes' : 'no'}</b>`];
      }), [2, 3, 4]);
    }
    if ((L.backtest_all || []).length || (L.backtest || []).length) {
      h += `<h3>Backtest: how each forecast of the close did</h3><p class="cv-sub">Every hourly reading of every resolved ladder against the official close, grouped by how long before the close it was read. Error = |forecast ÷ close − 1|, each ladder counted once; the best in each row in green. "Inside 80%" should be near 80%. Brier = the squared miss of P(close above K) over the strikes, where the options had a view too (lower is better). The combined model's weights and width come from these rows; out of sample = fitted on the earliest 70% of ladders, scored on the latest 30%.</p>`;
      if ((L.backtest_all || []).length) h += `<p class="cv-sub"><b>All ladders</b> (${num(L.resolved_all)} resolved)</p>` + btTable(L.backtest_all, f);
      if ((L.backtest || []).length) h += `<p class="cv-sub"><b>${esc(page)}</b> (${num(L.resolved_n)} resolved), scored with the model fitted on all ladders</p>` + btTable(L.backtest, f);
    } else if (O.length) h += `<p class="cv-sub">The backtest fills in as ladders resolve: each one is scored after its close.</p>`;
    return h;
  }
  function bindLad(el) {
    el.querySelectorAll && el.querySelectorAll('[data-ladh]').forEach((b) => {
      b.onclick = () => {
        el.querySelectorAll('[data-ladh]').forEach((x) => x.classList.toggle('on', x === b));
        el.querySelectorAll('[data-ladh-box]').forEach((x) => { x.hidden = x.dataset.ladhBox !== b.dataset.ladh; });
      };
    });
  }
  function ladderTrack(el) {
    ladFile('index.json').then((d) => {
      if (!d || !(d.backtest || []).length) { el.innerHTML = `<p class="cv-sub">${d ? 'No closing-price ladder read hourly has resolved yet.' : ''}</p>`; return; }
      el.innerHTML = `<div class="cv"><h3>Closing-price ladders, read hourly — ${num(d.resolved)} resolved</h3><p class="cv-sub">${esc(d.note || '')}</p>${btTable(d.backtest, usd)}</div>`;
    });
  }

  function render(el, doc) {
    css();
    PX = usd;
    el.__cv = doc;
    const lad = ladFor(el, doc, doc.ticker, render);
    const a = doc.analysts || {};
    const q0 = (a.periods || []).find((p) => p.period === '0q') || {};
    const nx = a.next_earnings || {};
    const price = fin(a.price) ? a.price : (doc.prices && doc.prices.length ? doc.prices[doc.prices.length - 1][1] : null);
    const T = a.targets || {};
    const beat = (doc.markets || []).find((m) => m.kind === 'beat' && !m.closed);
    const today = new Date().toISOString().slice(0, 10);
    const pm = (doc.markets || []).filter((m) => !m.closed && m.implied_price && fin(m.implied_price.median) && m.end >= today).sort((x, y) => String(x.end).localeCompare(String(y.end)));
    const pmPick = pm.find((m) => (Date.parse(m.end) - Date.now()) > 5 * 864e5 && m.kind === 'above') || pm.find((m) => (Date.parse(m.end) - Date.now()) > 5 * 864e5) || pm[0];
    const ourQ = (doc.ours || []).find((o) => o.horizon === 'next quarter') || (doc.ours || [])[0];
    const up = (v) => (fin(v) && fin(price) && price ? `${spct(v / price - 1)} from ${usd(price)}` : '');
    let h = `<div class="cv"><div class="cv-cards">` +
      card('Price', usd(price), a.as_of ? 'as of ' + esc(a.as_of) : '') +
      card("Analysts' target", usd(T.mean), [up(T.mean), fin(T.n) ? num(T.n) + ' analysts' : ''].filter(Boolean).join(' · '), C.an) +
      card('Next report', esc(nx.date || '—'), fin((q0.eps || {}).avg) ? `EPS est. ${usd(q0.eps.avg)} (${usd(q0.eps.low)}–${usd(q0.eps.high)}, ${num(q0.eps.numberOfAnalysts)})` : (nx.estimate ? 'date estimated' : ''), C.an) +
      card('Market: beats?', beat ? pct(beat.p) : '—', beat ? `Polymarket, line ${usd(beat.eps_strike)}` : 'no beat market open', C.pm) +
      card('Market-implied price', pmPick ? usd(pmPick.implied_price.median) : '—', pmPick ? `median for ${day(pmPick.end)}${up(pmPick.implied_price.median) ? ' · ' + up(pmPick.implied_price.median) : ''}` : 'no price market open', C.pm) +
      card('Our model', ourQ ? usd(ourQ.price) : '—', ourQ ? `${esc(ourQ.horizon)} (${day(ourQ.date)}) · 80% ${usd(ourQ.lo80, 0)}–${usd(ourQ.hi80, 0)}` : 'not forecast', '#2a78d6') +
      `</div>`;
    h += fan(doc, a) + ladPanel(lad, (v) => usd(v), doc.ticker || '') + postBox(el, doc, lad, render) + estimates(a) + trendChart(doc, a) + markets(doc, a, lad) + surprises(doc) + ratings(a) + track(doc);
    h += `<p class="cv-note">Analysts: Yahoo Finance consensus (estimates, targets, ratings and actions as published there), read daily. Prediction markets: Polymarket and Kalshi public APIs, read every few hours (closing-price ladders every hour) — prices are probabilities of a crowd with money on it, thin markets can be off. Options: CBOE delayed quotes; max pain and the walls are where open interest sits, not a forecast. Our model: the gravity / analogue forecast of the Rotation tab, frozen in its ledger. Nothing here is investment advice.</p></div>`;
    el.innerHTML = h;
    bindLad(el);
    if (window.FFPosts) window.FFPosts.bind(el);
  }

  // ---------- one index: the market ----------
  function bottomUpPanel(doc) {
    const B = doc.bottom_up;
    if (!B) return doc.id === 'vix' ? '' : `<h3>Analysts, added up</h3><p class="cv-sub">No member list for this index this week${doc.members_errors ? ' (' + esc(doc.members_errors.join('; ')) + ')' : ''}, so no bottom-up consensus.</p>`;
    const r = B.revisions_30d || {}, se = B.season || {};
    const rows = [
      ["12-month price-target return", `<b class="${B.target_ret >= 0 ? 'cv-good' : 'cv-bad'}">${spct(B.target_ret)}</b> <span class="cv-sub">weighted lows ${spct(B.target_low_ret)} · highs ${spct(B.target_high_ret)}</span>`, `${num(B.target_n)} companies, ${pct(B.target_coverage)} of the index`],
      ['Earnings growth, this fiscal year', spct(B.eps_growth_this_fy), `index earnings = Σ shares × consensus EPS · ${num(B.eps_n)} companies profitable in both years`],
      ['Earnings growth, next fiscal year', spct(B.eps_growth_next_fy), ''],
      ['P/E on this year · next year (forward)', `${fin(B.pe_this_fy) ? num(B.pe_this_fy, 1) : '—'} · <b>${fin(B.fwd_pe) ? num(B.fwd_pe, 1) : '—'}</b>`, 'market value ÷ consensus earnings of the same companies'],
      ['Mean rating', fin(B.rating_mean) ? num(B.rating_mean, 2) : '—', '1 strong buy – 5 strong sell, weighted'],
      ['Estimates over 30 days (this fiscal year)', `<span class="cv-good">${num(r.up)} raised</span> · <span class="cv-bad">${num(r.down)} cut</span>`, `${pct(r.w_up)} of the index raised, ${pct(r.w_down)} cut`],
      ['Reporting season, last 45 days', se.reported ? `${num(se.beat)} of ${num(se.reported)} beat (${pct(se.beat / se.reported)})` : '—', se.reported ? `${pct(se.w_reported)} of the index has reported · median surprise ${spct(se.median_surprise)}` : ''],
    ];
    let h = `<h3>Analysts, added up from the companies</h3><p class="cv-sub">The Yahoo Finance consensus of every member at its weight in the index (${B.weighting === 'price' ? 'price-weighted, as the Dow is' : 'market-value weights'}). Members: ${esc(doc.members_source || '—')} — ${num(B.members)} listed, ${num(B.matched)} with analysts' data.</p>` +
      tbl(['', 'Consensus', 'Basis'], rows.map((x) => [esc(x[0]), x[1], `<span class="cv-sub">${x[2]}</span>`]));
    const cm = B.coming || [];
    if (cm.length) h += `<h3>Reporting in the next 7 days</h3><p class="cv-sub">The largest members first; the Polymarket price of "beats" where a market is open.</p>` +
      tbl(['Company', 'Date', 'Weight', 'EPS estimate', 'Market: beats?'], cm.map((c) => [`<button class="text-button" data-cco="${esc(c.ticker)}"><b>${esc(c.ticker)}</b></button> <span class="cv-sub">${esc((c.name || '').slice(0, 34))}</span>`, esc(c.date), pct(c.weight, 1), usd(c.eps), fin(c.beat_prob) ? `<b>${pct(c.beat_prob)}</b>` : '—']), [2, 3, 4]);
    return h;
  }
  function oursPanel(doc) {
    const O = doc.ours || [];
    if (!O.length) return doc.id === 'vix' ? '' : `<h3>Our model</h3><p class="cv-sub">Our model forecasts the largest companies with a long history; none of this index's members are among them yet.</p>`;
    const dv = O[0].diversification;
    return `<h3>Our model, added up from the companies</h3><p class="cv-sub">Each member's gravity / analogue forecast (Rotation tab) from the forecast's base date, at its weight, over the members the model covers. The 80% range adds the members' ranges${fin(dv) ? `, narrowed to ${pct(dv)} because over the past year the index swung that much less than its members on average (diversification)` : ' as if they all moved together — an upper bound'}.</p>` +
      tbl(['Horizon', 'Made on', 'Index then', 'Forecast', 'Change', '80% range', 'Covered'], O.map((o) => [`<b>${esc(o.horizon)}</b> (${day(o.date)})`, day(o.from), pts(o.close_then), `<b>${pts(o.price)}</b>`,
        `<span class="${o.ret >= 0 ? 'cv-good' : 'cv-bad'}">${spct(o.ret)}</span>`, `${pts(o.lo80)} – ${pts(o.hi80)}`, `${num(o.n)} companies, ${pct(o.coverage)}`]), [2, 3, 4, 5]);
  }
  function contribPanel(doc) {
    const R = doc.contributors || [];
    if (!R.length) return '';
    return `<h3>The largest members</h3><p class="cv-sub">What each consensus says about the companies that move the index most. Click a ticker for its consensus page.</p>` +
      tbl(['Company', 'Weight', 'Price', "Analysts' target", 'Our model, next month', 'Our model, next quarter', 'Next report', 'Market: beats?'], R.map((c) => [
        `<button class="text-button" data-cco="${esc(c.ticker)}"><b>${esc(c.ticker)}</b></button> <span class="cv-sub">${esc((c.name || '').slice(0, 30))}</span>`, pct(c.weight, 1), usd(c.price),
        `<span class="${fin(c.target_ret) ? (c.target_ret >= 0 ? 'cv-good' : 'cv-bad') : ''}">${spct(c.target_ret)}</span>`, spct(c.ours_m), spct(c.ours_q), esc(c.next_earnings || '—'), fin(c.beat_prob) ? pct(c.beat_prob) : '—']), [1, 2, 3, 4, 5, 7]);
  }
  function historyPanel(doc) {
    const Hs = (doc.history || []).map(([d, r]) => ({ t: ts(d), lv: r[0], an: r[1], ou: r[2], pm: r[3] })).filter((x) => fin(x.lv));
    if (Hs.length < 3) return '';
    const ser = [['lv', 'Index', C.ink], ['an', "Analysts' bottom-up target", C.an], ['pm', 'Market, farthest date', C.pm], ['ou', 'Our model, next quarter', C.ours]]
      .map(([k, l, c]) => ({ l, c, p: Hs.filter((x) => fin(x[k])).map((x) => [x.t, x[k]]) })).filter((s) => s.p.length >= 2);
    const all = ser.flatMap((s) => s.p.map((p) => p[1])), t0 = Hs[0].t, t1 = Hs[Hs.length - 1].t;
    let y0 = Math.min(...all), y1 = Math.max(...all); const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
    const W = 820, H = 200, L = 54, R = 12, Tp = 10, B = 22, X = (t) => L + (t - t0) / ((t1 - t0) || 1) * (W - L - R), Y = (v) => Tp + (y1 - v) / (y1 - y0) * (H - Tp - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="How the consensus moved">`;
    for (let k = 0; k <= 3; k++) { const v = y0 + (y1 - y0) * k / 3; s += `<line class="cv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${pts(v)}</text>`; }
    for (const sr of ser) s += `<path d="${sr.p.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${sr.c}" stroke-width="1.8"><title>${esc(sr.l)}</title></path>`;
    s += `<text x="${L}" y="${H - 5}">${new Date(t0).toISOString().slice(0, 10)}</text><text x="${W - R}" y="${H - 5}" text-anchor="end">${new Date(t1).toISOString().slice(0, 10)}</text></svg>`;
    return `<h3>How the consensus moved</h3><p class="cv-sub">One reading a day since tracking began.</p><div class="cv-legend">${ser.map((sr) => `<span style="--k:${sr.c}">${esc(sr.l)}</span>`).join('')}</div>${s}`;
  }
  function renderIndex(el, doc) {
    css();
    PX = pts;
    el.__cv = doc;
    const lad = ladFor(el, doc, doc.short, renderIndex);
    const a = doc.analysts || {}, T = a.targets || {}, lv = doc.level;
    const up = (v) => (fin(v) && fin(lv) && lv ? `${spct(v / lv - 1)} from today` : '');
    const yd = new Date(Date.now() - 864e5).toISOString().slice(0, 10), soon = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
    const live = (doc.markets || []).filter((m) => !m.closed && (!m.end || m.end >= yd));
    const pm = live.filter((m) => m.implied_price && fin(m.implied_price.median) && m.end >= soon).sort((x, y) => String(x.end).localeCompare(String(y.end)));
    const near = pm[0], far = pm.length > 1 ? pm[pm.length - 1] : null;
    const ud = live.filter((m) => m.kind === 'updown' && fin(m.p)).sort((x, y) => String(x.end).localeCompare(String(y.end)))[0];
    const oq = (doc.ours || []).find((o) => o.horizon === 'next quarter'), om = (doc.ours || []).find((o) => o.horizon === 'next month');
    const src = (m) => (m.source === 'kalshi' ? 'Kalshi' : 'Polymarket');
    let h = `<div class="cv"><div class="cv-cards">` +
      card(doc.short + ' level', pts(lv), doc.as_of ? 'as of ' + esc(doc.as_of) + (doc.etf ? ` · ${esc(doc.etf)} × ${fin(doc.ratio) ? num(doc.ratio, 2) : '—'}` : '') : '') +
      card("Analysts, bottom-up", fin(T.mean) ? pts(T.mean) : '—', fin(T.mean) ? `12 months · ${up(T.mean)}` : 'no member data', C.an) +
      card('Market-implied, ' + (near ? day(near.end) : 'next'), near ? pts(near.implied_price.median) : '—', near ? `${src(near)} median · ${up(near.implied_price.median)}` : 'no ladder open', near && near.source === 'kalshi' ? C.ks : C.pm) +
      (far ? card('Market-implied, ' + day(far.end), pts(far.implied_price.median), `${src(far)} · 80% ${pts(far.implied_price.q10)}–${pts(far.implied_price.q90)}`, far.source === 'kalshi' ? C.ks : C.pm) : '') +
      (ud ? card('Market: up?', pct(ud.p), `${src(ud)} · ${esc(ud.title).slice(0, 48)}`, ud.source === 'kalshi' ? C.ks : C.pm) : '') +
      card('Our model', oq ? pts(oq.price) : om ? pts(om.price) : '—', oq ? `next quarter (${day(oq.date)}) · ${spct(oq.ret)} from ${day(oq.from)}` : om ? `next month · ${spct(om.ret)}` : 'not covered', C.ours) +
      `</div>`;
    h += fan(doc, a) + ladPanel(lad, pts, doc.name || doc.short || '') + postBox(el, doc, lad, renderIndex, doc.short) + bottomUpPanel(doc) + oursPanel(doc) + markets(doc, a, lad) + contribPanel(doc) + historyPanel(doc) + track(doc);
    h += `<p class="cv-note">Index levels: Yahoo Finance (daily closes; weekly shown). Analysts: Yahoo Finance consensus of each member, added up at index weights — not a strategist's index target. Prediction markets: Polymarket and Kalshi public APIs, read every few hours. Our model: the Rotation tab's company forecasts added up. Nothing here is investment advice.</p></div>`;
    el.innerHTML = h;
    bindLad(el);
    if (window.FFPosts) window.FFPosts.bind(el);
  }

  window.ConsensusView = { render, renderIndex, ladderTrack, fmt: { usd, big, pct, spct, num, day, unitFmt }, KIND };
})();
