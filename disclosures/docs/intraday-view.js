/* Move odds, intraday — the hub's Market & sectors while the US session is on. Each card leads with the asset's move so
   far today, where it ranks among its own days at that time of day, and where the days most like it went by 4 pm; the
   card's last line keeps the last close. The asset's panel: today's path with the similar days' fan to 4 pm, every
   day's move by that time (today's band marked), the similar days' move to the close against every day's, and the days
   after. After 4 pm the cards lead with today's close until the overnight update has it.
   Data: live.json on the branch intraday-live (app/intraday.py, every five minutes through the session by the relay
   .github/workflows/intraday.yml), read from raw.githubusercontent.com every minute while the tab shows it; filled in
   place (no redraw of the tab). History, not a forecast.
   window.IntradayView = {start(root), paint(root), load(), get(), set(doc), status(doc, now), cardHtml(a, doc), detailHtml(a, doc), …} */
(function () {
  'use strict';
  const SRC = 'https://raw.githubusercontent.com/eurikamonica/filing-flows/intraday-live/live.json';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const sp = (v, d = 2) => { if (!fin(v)) return '—'; const a = Math.abs(100 * v); return (Number(a.toFixed(d)) === 0 ? '' : v > 0 ? '+' : '−') + num(a, d) + '%'; };
  const tone = (v) => (!fin(v) ? '' : v > 0 ? 'iv-up' : v < 0 ? 'iv-down' : '');
  const rank = (p) => { if (!fin(p)) return '—'; const x = p >= 50 ? 100 - p : +p; return `${p >= 50 ? 'top' : 'bottom'} ${x < 1 ? x.toFixed(2) : x.toFixed(1)}%`; };
  const money = (v) => (fin(v) ? num(v, v >= 1000 ? 0 : 2) : '—');
  const hm = (iso) => { const m = /T(\d{2}):(\d{2})/.exec(iso || ''); return m ? `${+m[1] > 12 ? +m[1] - 12 : +m[1]}:${m[2]} ${+m[1] >= 12 ? 'pm' : 'am'}` : ''; };
  const etHm = (iso) => { const t = Date.parse(iso); return Number.isFinite(t) ? hm(new Date(t).toLocaleString('sv-SE', { timeZone: 'America/New_York' }).replace(' ', 'T')) : ''; };
  const etDay = (t) => new Date(t).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
  const day = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+m[2] - 1]} ${+m[3]}, ${m[1]}` : ''; };
  const markLabel = (mark) => (mark === '09:30' ? 'the open' : mark === '16:00' ? '4 pm' : hm('T' + mark));
  const band = (e) => (e === 0 ? '0' : sp(e, Math.abs(Math.round(e * 10000)) % 10 ? 2 : 1));
  const MARKMIN = [0, 60, 120, 180, 240, 300, 360, 390];
  const SHOWN = { live: 1, stale: 1, closed: 1 };
  let doc = null, err = null, pending = null, timer = null, lastLoad = 0;

  function css() {
    if (typeof document === 'undefined' || document.getElementById('iv-css')) return;
    const s = document.createElement('style');
    s.id = 'iv-css';
    s.textContent = `.iv-up{color:var(--mk-profit,#17734a)}.iv-down{color:var(--mk-cost,#c0392b)}
.iv-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--mk-cost,#c0392b);margin-right:5px;vertical-align:1px;animation:ivp 2s infinite}@keyframes ivp{50%{opacity:.3}}@media (prefers-reduced-motion:reduce){.iv-dot{animation:none}}
.iv-banner{font-size:12.5px;color:var(--ink-2,#444);margin:2px 0 8px;line-height:1.5;max-width:960px}.iv-banner[hidden]{display:none}
.iv-panel{border:1px solid var(--line,#ddd);border-radius:12px;padding:10px 14px 12px;margin:10px 0;background:var(--surface,#fff)}
.iv-panel h3{margin:2px 0 4px;font-size:15px;line-height:1.4}.iv-panel h4{margin:8px 0 4px;font-size:13.5px}.iv-panel p{margin:4px 0;font-size:13px;line-height:1.55}
.iv-chart{width:100%;height:auto;display:block}.iv-wide{max-width:780px}.iv-chart text{font-size:11px;fill:var(--muted,#777)}
.iv-panel .iv-sub,.iv-sub{font-size:12px;color:var(--muted,#777);line-height:1.5}
.iv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:4px 24px;margin-top:4px}
.iv-at{font-size:11.5px;font-weight:400;color:var(--muted,#777);margin-left:7px;vertical-align:3px;white-space:nowrap}
.iv-grid>div{min-width:0}.iv-tbl{overflow-x:auto}.iv-days{border-collapse:collapse;font-size:12.5px;width:100%;min-width:0;margin:4px 0;font-variant-numeric:tabular-nums}
.iv-days th,.iv-days td{padding:5px 6px;border-bottom:1px solid var(--line,#e5e5e5);text-align:right;white-space:nowrap;background:none}.iv-days th{font-weight:600;color:var(--muted,#777);font-size:11.5px;text-transform:none;letter-spacing:0;white-space:normal}
.iv-days th:first-child,.iv-days td:first-child{text-align:left;min-width:0;font-weight:500}.iv-days small{display:block;color:var(--muted,#777);font-size:11px}
.iv-key{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px;margin:0 4px 0 0}.iv-key+.iv-key,.iv-sub .iv-key:not(:first-child){margin-left:10px}`;
    document.head.appendChild(s);
  }

  function load() {
    if (pending || typeof fetch !== 'function') return pending;
    pending = fetch(`${SRC}?stamp=${Math.floor(Date.now() / 60000)}`, { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then((d) => { doc = d; err = null; })
      .catch((e) => { err = String((e && e.message) || e); })
      .finally(() => { pending = null; if (typeof document !== 'undefined') paint(document); });
    return pending;
  }
  /* a reading from today's session (before the open Yahoo still shows the last close) */
  function isToday(a, d) {
    if (!a || !fin(a.move) || !d || !d.session) return false;
    if (a.today != null) return !!a.today;
    return Date.parse(a.time) >= Date.parse(d.session.start);
  }
  /* 'live' while the session is on and the file is under 15 minutes old, 'stale' up to 90 minutes, 'down' after;
     'closed' once that day's session is over (and the relay read the close); null with no reading of today */
  function status(d, now) {
    if (!d || !d.session || !d.assets) return null;
    if (!Object.values(d.assets).some((a) => isToday(a, d))) return null;
    now = now || Date.now();
    const gen = Date.parse(d.generated_at), start = Date.parse(d.session.start), end = Date.parse(d.session.end);
    if (now >= end) return etDay(now) === d.session.date && gen >= end - 10 * 60000 ? 'closed' : null;
    if (now < start) return null;
    const age = (now - gen) / 60000;
    return age <= 15 ? 'live' : age <= 90 ? 'stale' : 'down';
  }
  /* the card's percentile meter, as moves.js draws the last close's (its .mvh-meter style) */
  function meter(p) {
    if (!fin(p)) return '';
    const lo = Math.min(p, 50), hi = Math.max(p, 50), col = p >= 50 ? 'var(--mk-profit,#17734a)' : 'var(--mk-cost,#c0392b)';
    return `<div class="mvh-meter" title="percentile ${(+p).toFixed(1)} among its days at this time"><span style="left:${lo}%;width:${Math.max(hi - lo, 1)}%;background:${col}"></span><span style="left:calc(50% - 1px);width:2px;background:var(--muted,#999)"></span></div>`;
  }
  /* the card's lead: today's move so far, its rank at this time of day, the days most like it to 4 pm */
  function cardHtml(a, d) {
    if (!a || !fin(a.move)) return '';
    const st = status(d), o = a.odds, S = o && o.similar, short = !!(d && d.session && d.session.short);
    const at = st === 'closed' ? 'at the close' : `${st === 'live' ? '<span class="iv-dot"></span>' : ''}${esc(hm(a.time).replace(/ [ap]m$/, ''))}${st === 'stale' ? ' (delayed)' : ''}`;
    let h = `<b class="${tone(a.move)}">${sp(a.move)}<span class="iv-at">${at}</span></b>${o && !(short && st === 'closed') ? meter(o.pct) : ''}`;
    if (st === 'closed') {
      const n1 = S && S.next && S.next['1'];
      if (o && !short) h += `<i>${rank(o.pct)} day</i>`;
      if (n1 && fin(n1.p50) && !short) h += `<i>the day after days like it: <span class="${tone(n1.p50)}">${sp(n1.p50)}</span> · ${pc(n1.up)} rose</i>`;
      return h;
    }
    if (o) h += `<i>${rank(o.pct)} so far</i>`;
    if (S && S.rest && !short && o.j < 7) h += `<i>to 4 pm, ${num(S.n)} days like it: <span class="${tone(S.rest.p50)}">${sp(S.rest.p50)}</span> · ${pc(S.above)} higher</i>`;
    return h;
  }
  /* today's path from the previous close, with the similar days' fan from now to 4 pm */
  function chart(a, fanOn, width) {
    const P = a.path || [], o = a.odds, S = o && o.similar;
    if (P.length < 2) return '';
    const W = Math.round(Math.max(300, Math.min(780, width || 720))), H = W < 520 ? 200 : 230, L = 44, R = 14, T = 12, B = 28, narrow = W < 560;
    const fan = fanOn && S && S.fan ? S.fan.map((r) => [MARKMIN[r[0]], ...r.slice(1).map((v) => (fin(v) ? (1 + a.move) * (1 + v) - 1 : null))]) : [];
    const vals = [0, ...P.map((p) => p[1]), ...fan.flatMap((r) => r.slice(1))].filter(fin);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = Math.max(0.001, (hi - lo) * 0.08); lo -= pad; hi += pad;
    const sx = (m) => L + (m / 390) * (W - L - R), sy = (v) => T + ((hi - v) / (hi - lo)) * (H - T - B);
    let s = `<svg class="iv-chart iv-wide" viewBox="0 0 ${W} ${H}" role="img" aria-label="Today's move from the previous close${fan.length ? ', and where the most similar days went from here to the close' : ''}">`;
    const step = [0.0025, 0.005, 0.01, 0.02, 0.05].find((x) => (hi - lo) / x <= 6) || 0.1;
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-12; v += step) s += `<line x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}" stroke="var(--line,#e5e5e5)"${Math.abs(v) < 1e-12 ? ' style="stroke:var(--muted,#999)"' : ''}/><text x="${L - 6}" y="${(sy(v) + 4).toFixed(1)}" text-anchor="end">${Math.abs(v) < 1e-12 ? '0%' : sp(v, step < 0.005 ? 2 : 1)}</text>`;
    MARKMIN.forEach((m, i) => { if (!narrow || i % 2 === 0 || i === 7) if (!(narrow && i === 6)) s += `<text x="${sx(m).toFixed(1)}" y="${H - 10}" text-anchor="${i === 7 ? 'end' : i ? 'middle' : 'start'}">${['9:30', '10:30', '11:30', '12:30', '1:30', '2:30', '3:30', '4 pm'][i]}</text>`; });
    if (fan.length > 1) {
      const area = (i, j, op) => { const up = fan.map((r) => `${sx(r[0]).toFixed(1)},${sy(r[j]).toFixed(1)}`), dn = fan.slice().reverse().map((r) => `${sx(r[0]).toFixed(1)},${sy(r[i]).toFixed(1)}`); return `<polygon points="${up.concat(dn).join(' ')}" fill="var(--accent,#1f6f4a)" opacity="${op}"/>`; };
      s += area(1, 5, 0.13) + area(2, 4, 0.26) + `<polyline points="${fan.map((r) => `${sx(r[0]).toFixed(1)},${sy(r[3]).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--accent,#1f6f4a)" stroke-width="2" stroke-dasharray="5 4"/>`;
    }
    s += `<polyline points="${[[0, 0], ...P].map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--ink,#222)" stroke-width="2"/>`;
    const last = P[P.length - 1];
    s += `<circle cx="${sx(last[0]).toFixed(1)}" cy="${sy(a.move).toFixed(1)}" r="4" fill="${a.move >= 0 ? 'var(--mk-profit,#17734a)' : 'var(--mk-cost,#c0392b)'}"/></svg>`;
    return s + `<p class="iv-sub">${fan.length > 1 ? `Solid: today, every five minutes, from the previous close. Shaded: where the ${num(S.n)} days most like it went from ${esc(markLabel(o.mark))} to 4 pm — the middle half and eight in ten; dashed: their median.` : 'Today, every five minutes, from the previous close.'}</p>`;
  }
  /* every day's move by this time of day (fixed bands), today's band dark */
  function distChart(o, edges, move) {
    if (!o || !o.dist || !edges) return '';
    const n = o.dist.reduce((x, y) => x + y, 0), k = o.dist.length, W = 340, H = 156, L = 6, R = 6, T = 18, B = 24, bw = (W - L - R) / k;
    if (!n) return '';
    const mx = Math.max(...o.dist.map((c) => c / n)), y = (v) => T + (1 - v / mx) * (H - T - B);
    const here = edges.findIndex((e) => e > move), bin = here < 0 ? k - 1 : here;
    let s = `<svg class="iv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Every day's move by this time, and today's">`;
    o.dist.forEach((c, i) => { const x = L + i * bw; s += `<rect x="${(x + 2).toFixed(1)}" y="${y(c / n).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${(y(0) - y(c / n)).toFixed(1)}" fill="${i === bin ? 'var(--ink,#222)' : i < k / 2 ? 'var(--mk-cost,#c0392b)' : 'var(--mk-profit,#17734a)'}" opacity="${i === bin ? 0.85 : 0.5}"/>`; });
    s += `<text x="${(L + bin * bw + bw / 2).toFixed(1)}" y="${(y(o.dist[bin] / n) - 5).toFixed(1)}" text-anchor="middle" style="fill:var(--ink,#222);font-weight:600">today</text>`;
    edges.forEach((e, i) => { if (i % 2 === 0) s += `<text x="${(L + (i + 1) * bw).toFixed(1)}" y="${H - 8}" text-anchor="middle">${e === 0 ? '0' : sp(e, 1)}</text>`; });
    return s + '</svg>';
  }
  /* the move from now to 4 pm: the days most like today (bars) against every day (ticks) */
  function restChart(o) {
    const E = o && o.rest_edges, S = (o && o.similar) || {}, B = (o && o.base) || {};
    if (!E || !S.rest_dist || !B.rest_dist) return '';
    const ns = S.rest_dist.reduce((x, y) => x + y, 0), nb = B.rest_dist.reduce((x, y) => x + y, 0);
    if (!ns || !nb) return '';
    const k = S.rest_dist.length, W = 340, H = 150, L = 6, R = 6, T = 8, Bm = 24, bw = (W - L - R) / k;
    const sh = S.rest_dist.map((c) => c / ns), bh = B.rest_dist.map((c) => c / nb), mx = Math.max(...sh, ...bh);
    const y = (v) => T + (1 - v / mx) * (H - T - Bm);
    let s = `<svg class="iv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="The move from now to 4 pm: the days most like today against every day">`;
    for (let i = 0; i < k; i++) {
      const x = L + i * bw;
      s += `<rect x="${(x + 2).toFixed(1)}" y="${y(sh[i]).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${(y(0) - y(sh[i])).toFixed(1)}" fill="var(--accent,#1f6f4a)" opacity="0.7"/>`;
      s += `<line x1="${(x + 1).toFixed(1)}" x2="${(x + bw - 1).toFixed(1)}" y1="${y(bh[i]).toFixed(1)}" y2="${y(bh[i]).toFixed(1)}" stroke="var(--ink,#222)" stroke-width="2"/>`;
    }
    E.forEach((e, i) => { if (i % 2 === 0) s += `<text x="${(L + (i + 1) * bw).toFixed(1)}" y="${H - 8}" text-anchor="middle">${band(e)}</text>`; });
    return s + `</svg><p class="iv-sub"><span class="iv-key" style="background:var(--accent,#1f6f4a);opacity:.7"></span>the ${num(S.n)} days like it <span class="iv-key" style="background:var(--ink,#222);height:2px;vertical-align:3px"></span>every day — the move from ${esc(markLabel(o.mark))} to 4 pm, bands of ${band(E[1] - E[0]).replace('+', '')}</p>`;
  }
  /* the next day, week and month after the days most like today, and after every day */
  function daysTable(S, B) {
    const cell = (q) => (q && fin(q.p50) ? `<span class="${tone(q.p50)}">${sp(q.p50)}</span> · ${pc(q.up)} rose<small>${sp(q.p10, 1)} to ${sp(q.p90, 1)}</small>` : '—');
    const nx = (X, s) => ((X || {}).next || {})[s];
    return `<div class="iv-tbl"><table class="iv-days"><thead><tr><th></th><th>The ${num(S.n)} days like it</th><th>Every day</th></tr></thead><tbody>${[['1', 'Next day'], ['5', '5 days'], ['21', '21 days']].map(([s, lab]) => `<tr><td>${lab}</td><td>${cell(nx(S, s))}</td><td>${cell(nx(B, s))}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function detailHtml(a, d, width) {
    if (!a || !fin(a.move)) return '';
    d = d || {};
    const o = a.odds, S = o && o.similar, B = (o && o.base) || {}, st = status(d), short = !!(d.session && d.session.short), closed = st === 'closed';
    const by = o ? markLabel(o.mark) : '', toClose = !!(S && S.rest && !short && o.j < 7 && !closed);
    const when = closed ? `closed at ${money(a.price)}, <b class="${tone(a.move)}">${sp(a.move)}</b> on the day` : `<b class="${tone(a.move)}">${sp(a.move)}</b> at ${esc(hm(a.time))} New York time${st === 'stale' ? ' (the feed is behind)' : ''}`;
    let h = `<div class="iv-panel"><h3>${st === 'live' ? '<span class="iv-dot"></span>' : ''}${esc(a.name)} today: ${when}</h3>`;
    h += `<p class="iv-sub">${money(a.price)}, the previous close ${money(a.prev)}; today's high ${sp(a.hi)}, low ${sp(a.lo)}. ${esc(d.source || '')}, read every five minutes${d.generated_at ? `, last at ${esc(etHm(d.generated_at))}` : ''}.${short ? ` Today's session closes early, at ${esc(etHm(d.session.end))}: the odds to 4 pm of full days don't apply.` : ''}</p>`;
    h += chart(a, toClose, width);
    if (!o) return h + `<p class="iv-sub">Its history at this time of day is not on file yet.</p></div>`;
    const fall = o.pct < 50, cols = [];
    cols.push(`<div><h4>${closed ? 'The day' : 'So far'}</h4><p>${sp(a.move)} ${closed ? 'on the day' : `by about ${esc(by)}`}: in the <b>${rank(o.pct)}</b> of its ${num(o.days)} days since ${esc(day(o.from))}${closed ? '' : ' at that time of day'}; a ${fall ? 'fall' : 'rise'} this far${closed ? '' : ' by then'} comes about once in ${num(o.every, 1)} days.</p>${distChart(o, d.edges, a.move)}${d.edges && d.edges.length > 1 ? `<p class="iv-sub">Every day's move by ${esc(by)} from the previous close, in bands of ${band(d.edges[1] - d.edges[0]).replace('+', '')}.</p>` : ''}</div>`);
    if (toClose) {
      const mb = S.moves_by_then || [], r = S.rest;
      cols.push(`<div><h4>To the close</h4><p>The ${num(S.n)} days nearest to this move by ${esc(by)} (${sp(mb[0])} to ${sp(mb[1])} by then) went a median <b class="${tone(r.p50)}">${sp(r.p50)}</b> further by 4 pm (10–90%: ${sp(r.p10)} to ${sp(r.p90)}); <b>${pc(S.above)}</b> closed above that price and ${pc(S.green)} above the previous close${S.close ? ` — a close near <b>${money(S.close[1])}</b> (10–90%: ${money(S.close[0])}–${money(S.close[2])})` : ''}. Every day from ${esc(by)}: a median ${sp(B.rest && B.rest.p50)}, ${pc(B.above)} higher.</p>${restChart(o)}</div>`);
    }
    if (S) cols.push(`<div><h4>The days after</h4>${daysTable(S, B)}<p class="iv-sub">From the 4 pm close of the ${num(S.n)} days most like today by ${esc(by)}, and of every day: the median move, the share that rose and, below, the range of eight in ten.</p></div>`);
    h += `<div class="iv-grid">${cols.join('')}</div>`;
    h += `<p class="iv-sub">From Yahoo's hourly bars of the last two years (${num(o.days)} full sessions; the price at a mark is the close of that hourly bar, the previous close the 4 pm price before); now is read at the nearest mark, ${esc(by)}. History, not a forecast.</p>`;
    return h + '</div>';
  }
  function banner(d, e, asof) {
    const st = status(d), at = d && d.generated_at ? esc(etHm(d.generated_at)) : '';
    if (st === 'live') return `<span class="iv-dot"></span><b>Live</b>, ${at} New York time: each card leads with the move so far today, its rank among its own days at that time and where the ${num(d.k || 60)} days most like it went by 4 pm (Yahoo Finance, every five minutes; some prices may be delayed). Its last line is the last close. Pick a card for the path, the spread and the days after.`;
    if (st === 'stale') return `The live feed is behind: the cards show its last reading, at ${at} New York time${e ? ` (${esc(e)})` : ''}.`;
    if (st === 'down') return `The live feed stopped at ${at} New York time: the cards show the last close.`;
    if (st === 'closed' && asof && asof < d.session.date) return `Today's session is over: the cards lead with today's close from the live feed (Yahoo Finance) until tonight's update; the card's last line is the close before.`;
    return '';
  }
  /* the asset to paint into a slot, or null: shown while live, stale or closed; after the close only until the
     overnight update (the slot's data-asof, the page's last close) reaches today */
  function pick(key, asof) {
    const st = status(doc);
    if (!SHOWN[st]) return null;
    const a = ((doc && doc.assets) || {})[key];
    if (!isToday(a, doc)) return null;
    if (st === 'closed' && !(asof && asof < doc.session.date)) return null;
    return a;
  }
  /* fill every card, the banner and the asset's panel under root from the last file read */
  function paint(root) {
    if (!root || !root.querySelectorAll) return;
    css();
    root.querySelectorAll('[data-ivb]').forEach((el) => { const h = banner(doc, err, el.dataset.asof); el.innerHTML = h; el.hidden = !h; });
    root.querySelectorAll('[data-ivc]').forEach((el) => {
      const a = pick(el.dataset.ivc, el.dataset.asof), card = el.closest ? el.closest('.mvh-card') : null;
      el.innerHTML = a ? cardHtml(a, doc) : '';
      if (card && card.classList) card.classList.toggle('iv-on', !!a);
    });
    root.querySelectorAll('[data-ivd]').forEach((el) => { const a = pick(el.dataset.ivd, el.dataset.asof); el.innerHTML = a ? detailHtml(a, doc, el.clientWidth ? el.clientWidth - 30 : 0) : ''; });
  }
  /* read now and every minute while a card, the banner or a panel is on the page (not while the tab is hidden) */
  function start(root) {
    paint(root);
    if (Date.now() - lastLoad > 55000) { lastLoad = Date.now(); load(); }
    if (timer || typeof setInterval !== 'function') return;
    timer = setInterval(() => {
      if (typeof document === 'undefined' || !document.querySelector('[data-ivc],[data-ivd],[data-ivb]')) { clearInterval(timer); timer = null; return; }
      if (document.hidden) return;
      lastLoad = Date.now();
      load();
    }, 60000);
  }
  const api = { start, paint, load, status, isToday, cardHtml, detailHtml, chart, banner, get: () => doc, set: (d) => { doc = d; }, SRC };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.IntradayView = api;
})();
