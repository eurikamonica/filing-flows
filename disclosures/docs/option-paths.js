/* Option-implied price paths — one underlying's option chain (app/options.py price_paths: per expiry the risk-neutral
   quantiles from Breeden-Litzenberger on a fitted IV smile, max pain, the call wall above spot and the put wall below)
   drawn as a fan of 50 / 80 / 95% ranges between expiries, 40 sample paths matched to those distributions, and the call
   wall ▼, put wall ▲ and max pain ◆ of every expiry; a table; an analysis and a post for X (chart-share.js when present).
   Between expiries the median and the spread per unit √time are interpolated in time; from today to the first expiry the
   spread grows with √time. Sample paths: one Brownian motion per path, mapped each day onto that day's quantile function
   (z = W(t)/√t), so at every expiry the paths have the distribution the options price.
   Shared: the hub's Options and ETF pages (options.js, etf.js) and every company page of the Sankey site (views.json:
   window.FFOptionPaths.render(el, {ticker, hub, here})). Data: data/market/options/<T>.json and data/market/options.json.
   No dependencies. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const fmt = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const px = (v) => (fin(v) ? '$' + fmt(v, v >= 100 ? 0 : 2) : '—');
  const ivp = (v) => (fin(v) ? fmt(v * 100, 1) + '%' : '—');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const md = (e) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(e || ''); return m ? MON[+m[2] - 1] + ' ' + (+m[3]) : String(e || ''); };
  const COL = { band: 'var(--rot-1, #2a78d6)', path: 'var(--muted, #888)', call: 'var(--neg, #b4432f)', put: 'var(--mk-profit, #17734a)', pain: 'var(--ink, #222)', surface: 'var(--surface, #fff)' };
  function ticks(lo, hi, n = 6) {
    const raw = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(raw || 1)), st = [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw);
    const out = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(6)); return out;
  }
  function css() {
    if (typeof document === 'undefined' || !document.head || document.getElementById('fop-css')) return;
    const s = document.createElement('style'); s.id = 'fop-css';
    s.textContent = `.fop svg{display:block;width:100%;height:auto}.fop .fop-g{stroke:var(--line,#e3e3e3);stroke-width:1}.fop .fop-ax{stroke:var(--muted,#888);stroke-width:1}
.fop .fop-t{fill:var(--muted,#777);font-size:11px}.fop .fop-l{fill:var(--ink,#222);font-size:11.5px;paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px}
.fop .fop-sub{color:var(--muted,#777);font-size:13px;line-height:1.5;margin:0 0 10px;max-width:90ch}.fop h3{margin:18px 0 4px;font-size:17px}
.fop-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.fop-legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.fop-wrap{overflow-x:auto}.fop-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.fop-tbl th,.fop-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;white-space:nowrap}
.fop-tbl .n{text-align:right;font-variant-numeric:tabular-nums}.fop-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.fop-tbl .m{color:var(--muted,#888);font-size:11.5px}
.fop-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin:6px 0 10px}.fop-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px}
.fop-card span{display:block;font-size:12px;color:var(--muted,#777)}.fop-card b{font-size:18px;font-variant-numeric:tabular-nums}.fop-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}`;
    document.head.appendChild(s);
  }

  function invN(p) {
    const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239],
      b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572],
      c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783],
      d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416], pl = 0.02425;
    if (p < pl) { const q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p > 1 - pl) { const q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    const q = p - 0.5, r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  function fan(c) {                                      // the quantile function of the price at any day up to the last expiry
    const P = (c.paths || []).filter((x) => x.days > 0 && (x.q || []).length >= 5), probs = c.path_probs || [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975];
    if (!P.length || !(c.spot > 0)) return null;
    const Z = probs.map(invN), mi = probs.indexOf(0.5) >= 0 ? probs.indexOf(0.5) : Math.floor(probs.length / 2);
    const nodes = P.map((x) => { const L = x.q.map(Math.log), t = x.days / 365, m = L[mi]; return { t, days: x.days, m, D: L.map((v) => (v - m) / Math.sqrt(t)), x }; });
    const at = (days, z) => {
      const t = Math.max(days, 1e-6) / 365, i = nodes.findIndex((n) => n.days >= days);
      let m, D;
      if (i < 0) { const n = nodes[nodes.length - 1]; m = n.m; D = n.D; } else if (i === 0) { const n = nodes[0], w = days / n.days; m = Math.log(c.spot) + (n.m - Math.log(c.spot)) * w; D = n.D; } else { const a = nodes[i - 1], b = nodes[i], w = (days - a.days) / (b.days - a.days); m = a.m + (b.m - a.m) * w; D = a.D.map((v, j) => v + (b.D[j] - v) * w); }
      let j = 1; while (j < Z.length - 1 && z > Z[j]) j++;
      const s = (D[j] - D[j - 1]) / (Z[j] - Z[j - 1]);
      return m + (D[j - 1] + s * (z - Z[j - 1])) * Math.sqrt(t);
    };
    return { nodes, probs, Z, at, end: nodes[nodes.length - 1].days };
  }
  function sim(F, n = 40, seed = 20261023) {            // seeded Brownian paths mapped through the fan
    let a = seed >>> 0;
    const rnd = () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
    const gauss = () => Math.sqrt(-2 * Math.log(rnd() || 1e-12)) * Math.cos(2 * Math.PI * rnd());
    const step = Math.max(1, Math.ceil(F.end / 120)), days = []; for (let d = step; d < F.end; d += step) days.push(d); days.push(F.end);
    const out = [];
    for (let k = 0; k < n; k++) { let W = 0, prev = 0; out.push(days.map((d) => { W += Math.sqrt((d - prev) / 365) * gauss(); prev = d; return [d, Math.exp(F.at(d, W / Math.sqrt(d / 365)))]; })); }
    return out;
  }
  let CLIP = 0;
  function svg(c, opt = {}) {
    const F = fan(c); if (!F) return '<p class="fop-sub">No expiry with enough quoted strikes for the price paths.</p>';
    const W = 720, H = 340, L = 60, R = 96, T = 16, B = 36, days = [];
    for (let d = 0; d <= F.end; d += Math.max(1, F.end / 160)) days.push(d); if (days[days.length - 1] < F.end) days.push(F.end);
    const sims = sim(F), band = (p) => days.map((d) => (d ? Math.exp(F.at(d, invN(p))) : c.spot));
    const lo = band(F.probs[0]), hi = band(F.probs[F.probs.length - 1]), mk = F.nodes.flatMap((n) => [n.x.max_pain, n.x.call_wall, n.x.put_wall]).filter((v) => v > 0);
    const ymin = Math.min(...lo, ...mk, c.spot) * 0.98, ymax = Math.max(...hi, ...mk, c.spot) * 1.02;
    const sx = (d) => L + d / F.end * (W - L - R), sy = (v) => T + (ymax - v) / (ymax - ymin) * (H - T - B), pt = (d, v) => sx(d).toFixed(1) + ',' + sy(v).toFixed(1);
    const poly = (a, b) => days.map((d, i) => pt(d, a[i])).join(' ') + ' ' + days.map((d, i) => pt(d, b[i])).reverse().join(' ');
    const clip = 'fop-clip-' + (++CLIP);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price paths the options imply, with their ranges, walls and max pain by expiry"><defs><clipPath id="${clip}"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath></defs>`;
    ticks(ymin, ymax).forEach((v) => { s += `<line class="fop-g" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="fop-t" x="${L - 8}" y="${sy(v) + 4}" text-anchor="end">${px(v)}</text>`; });
    [[0.025, 0.975, 0.10], [0.1, 0.9, 0.16], [0.25, 0.75, 0.24]].forEach(([a, b, o]) => { if (F.probs.includes(a) && F.probs.includes(b)) s += `<polygon points="${poly(band(a), band(b))}" style="fill:${COL.band};opacity:${o}"/>`; });
    s += `<g clip-path="url(#${clip})">`; sims.forEach((p) => { s += `<polyline points="${pt(0, c.spot)} ${p.map(([d, v]) => pt(d, v)).join(' ')}" style="fill:none;stroke:${COL.path};stroke-width:.7;opacity:.4"/>`; }); s += '</g>';
    s += `<polyline style="fill:none;stroke:${COL.band};stroke-width:2;stroke-dasharray:6 4" points="${days.map((d, i) => pt(d, band(0.5)[i])).join(' ')}"/>`;
    s += `<line class="fop-ax" x1="${L}" x2="${W - R}" y1="${sy(c.spot)}" y2="${sy(c.spot)}" style="stroke-dasharray:2 3"/><text class="fop-l" x="${W - R + 4}" y="${sy(c.spot) + 4}">spot ${px(c.spot)}</text>`;
    for (const [key, col] of [['call_wall', COL.call], ['put_wall', COL.put], ['max_pain', COL.pain]]) {
      const ns = F.nodes.filter((n) => n.x[key] > 0);
      if (ns.length > 1) s += `<polyline points="${ns.map((n) => pt(n.days, n.x[key])).join(' ')}" style="fill:none;stroke:${col};stroke-width:1.2;stroke-dasharray:3 3;opacity:.7"/>`;
    }
    let lastX = -1e9;
    F.nodes.forEach((n, i) => {
      const x = sx(n.days), q = n.x.q, k = (p) => q[F.probs.indexOf(p)], last = i === F.nodes.length - 1;
      s += `<line class="fop-g" x1="${x}" x2="${x}" y1="${T}" y2="${H - B}" style="opacity:.6"/>`;
      if (last ? x - lastX >= 30 : x - lastX >= 38 && sx(F.end) - x >= 38) { s += `<text class="fop-t" x="${x}" y="${H - B + 16}" text-anchor="middle">${esc(n.x.exp.slice(5))}</text>`; lastX = x; }
      const rows = [[esc(n.x.exp), `${fmt(n.days)} days · ATM IV ${ivp(n.x.atm_iv)}`], [`${px(k(0.025))} – ${px(k(0.975))}`, '95% of the implied distribution'], [`${px(k(0.1))} – ${px(k(0.9))}`, '80%'], [px(k(0.5)), 'median'],
        [n.x.call_wall > 0 ? px(n.x.call_wall) : '—', `call wall · ${fmt(n.x.call_wall_oi || 0)} calls open`], [n.x.put_wall > 0 ? px(n.x.put_wall) : '—', `put wall · ${fmt(n.x.put_wall_oi || 0)} puts open`], [n.x.max_pain > 0 ? px(n.x.max_pain) : '—', 'max pain (this expiry)']];
      const hint = opt.tip ? ` data-tip="${opt.tip(rows)}" tabindex="0" class="mk-hit"` : '';
      s += `<g${hint}>${opt.tip ? '' : `<title>${rows.map((r) => r[0] + ' — ' + r[1]).join('\n')}</title>`}<rect x="${x - 9}" y="${T}" width="18" height="${H - T - B}" fill="transparent"/>` +
        (n.x.call_wall > 0 ? `<path d="M${x - 6},${sy(n.x.call_wall) - 5}L${x + 6},${sy(n.x.call_wall) - 5}L${x},${sy(n.x.call_wall) + 5}Z" style="fill:${COL.call};stroke:${COL.surface};stroke-width:1"/>` : '') +
        (n.x.put_wall > 0 ? `<path d="M${x - 6},${sy(n.x.put_wall) + 5}L${x + 6},${sy(n.x.put_wall) + 5}L${x},${sy(n.x.put_wall) - 5}Z" style="fill:${COL.put};stroke:${COL.surface};stroke-width:1"/>` : '') +
        (n.x.max_pain > 0 ? `<path d="M${x},${sy(n.x.max_pain) - 6}L${x + 6},${sy(n.x.max_pain)}L${x},${sy(n.x.max_pain) + 6}L${x - 6},${sy(n.x.max_pain)}Z" style="fill:${COL.pain};stroke:${COL.surface};stroke-width:1.2"/>` : '') + '</g>';
    });
    const e = F.nodes[F.nodes.length - 1].x, qe = (p) => e.q[F.probs.indexOf(p)];
    [[0.975, '97.5%'], [0.9, '90%'], [0.5, 'median'], [0.1, '10%'], [0.025, '2.5%']].forEach(([p, l]) => { if (F.probs.includes(p)) s += `<text class="fop-l" x="${W - R + 4}" y="${sy(qe(p)) + 4}">${l} ${px(qe(p))}</text>`; });
    return s + `<text class="fop-t" x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">Expiry (month-day) · ${fmt(F.end)} days ahead at the last</text></svg>` +
      `<div class="fop-legend"><span><b style="background:${COL.band};opacity:.5"></b>50 / 80 / 95% of the implied distribution</span><span><b style="background:${COL.path}"></b>40 sample paths</span><span><b style="background:${COL.call}"></b>call wall by expiry (▼)</span><span><b style="background:${COL.put}"></b>put wall by expiry (▲)</span><span><b style="background:${COL.pain}"></b>max pain by expiry (◆)</span></div>`;
  }
  function table(c) {
    const P = c.paths || [], pr = c.path_probs || [], k = (x, p) => x.q[pr.indexOf(p)];
    const rel = (v) => (v > 0 && c.spot ? ` <span class="m">${(v >= c.spot ? '+' : '−') + fmt(Math.abs(v / c.spot - 1) * 100, 1)}%</span>` : '');
    return `<div class="fop-wrap"><table class="fop-tbl"><thead><tr><th>Expiry</th><th class="n">Days</th><th class="n">ATM IV</th><th class="n">95% range</th><th class="n">80% range</th><th class="n">Median</th><th class="n">Put wall</th><th class="n">Call wall</th><th class="n">Max pain</th><th class="n">Open interest</th></tr></thead><tbody>${P.map((x) => `<tr><td>${esc(x.exp)}${x.method === 'atm' ? ' <span class="m">(ATM IV only)</span>' : ''}</td><td class="n">${fmt(x.days)}</td><td class="n">${ivp(x.atm_iv)}</td><td class="n">${px(k(x, 0.025))} – ${px(k(x, 0.975))}</td><td class="n">${px(k(x, 0.1))} – ${px(k(x, 0.9))}</td><td class="n">${px(k(x, 0.5))}${rel(k(x, 0.5))}</td><td class="n">${x.put_wall > 0 ? px(x.put_wall) + rel(x.put_wall) : '—'}</td><td class="n">${x.call_wall > 0 ? px(x.call_wall) + rel(x.call_wall) : '—'}</td><td class="n">${x.max_pain > 0 ? px(x.max_pain) + rel(x.max_pain) : '—'}</td><td class="n">${fmt(x.oi)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function post(c, name) {                               // the analysis and the post for X, by rule from the chain's numbers
    const P = (c.paths || []).filter((x) => (x.q || []).length), pr = c.path_probs || [], k = (x, p) => x.q[pr.indexOf(p)], nm = name || c.ticker || '', tag = '$' + String(nm).replace(/-/g, '.');
    const pick = [7, 30, 90].map((d) => P.reduce((b, x) => (!b || Math.abs(x.days - d) < Math.abs(b.days - d) ? x : b), null)).filter((x, i, a) => x && a.indexOf(x) === i);
    const walls = (x) => [x.put_wall > 0 ? 'put wall ' + px(x.put_wall) : '', x.call_wall > 0 ? 'call wall ' + px(x.call_wall) : '', x.max_pain > 0 ? 'max pain ' + px(x.max_pain) : ''].filter(Boolean).join(', ');
    const paras = [`${nm} at ${px(c.spot)}: the price distribution its options imply (CBOE delayed quotes, Breeden-Litzenberger on the IV smile).`,
      ...pick.map((x) => `${md(x.exp)} (${x.days} days, ATM IV ${ivp(x.atm_iv)}): 80% between ${px(k(x, 0.1))} and ${px(k(x, 0.9))}, 95% between ${px(k(x, 0.025))} and ${px(k(x, 0.975))}, median ${px(k(x, 0.5))}${walls(x) ? '; ' + walls(x) : ''}.`),
      "Risk-neutral: the market's price of protection is in it (a fatter downside), not a forecast of direction; walls and max pain describe open interest."];
    const lines = [`${tag} ${px(c.spot)} — what the options price in:`, ...pick.map((x) => `${md(x.exp)}: 80% ${px(k(x, 0.1))}–${px(k(x, 0.9))}${x.max_pain > 0 ? ', max pain ' + px(x.max_pain) : ''}${x.put_wall > 0 && x.call_wall > 0 ? ', walls ' + px(x.put_wall) + ' / ' + px(x.call_wall) : ''}.`), 'Risk-neutral, not a forecast.'];
    return { title: `${nm}: the price paths its options imply`, paras, lines };
  }
  const ABOUT = "From today's option chain (CBOE, delayed): at each expiry the distribution of the price the option prices imply (Breeden-Litzenberger on the IV smile, the forward from put-call parity), the 50, 80 and 95% ranges between expiries, 40 sample paths drawn to match those distributions, and for every expiry its call wall and put wall (the strike above spot with the most call open interest and the one below spot with the most put open interest, within 30% of spot — often read as resistance and support) and its max pain — the price at which the open contracts would pay their holders least. Risk-neutral: it includes what the market pays for protection (a fatter downside) and is not a forecast of direction; walls and max pain describe where open interest sits, not prices the market has to respect.";
  function panel(c, name, opt = {}) {
    if (!c || !(c.paths || []).length) return '';
    css();
    const nm = name || c.ticker || '', key = String(nm || 'x') + '-option-paths', S = typeof window !== 'undefined' && window.FFShare;
    const bar = S ? S.bar({ key, title: `${nm}: price paths the options imply`, subtitle: `Spot ${px(c.spot)} · 50 / 80 / 95% of the risk-neutral distribution, 40 sample paths, call wall ▼, put wall ▲ and max pain ◆ by expiry`,
      source: 'CBOE delayed option quotes; Breeden-Litzenberger on a fitted IV smile, forward from put-call parity (Filing Flows). Risk-neutral, not a forecast.', post: () => post(c, nm) }) : '';
    return `<div class="fop ${opt.cls == null ? 'panel' : esc(opt.cls)}"><h3>Price paths the options imply — ${esc(nm)}</h3><p class="fop-sub sub">${ABOUT}</p>${bar}<div data-ffs-chart="${esc(key)}">${svg(c, opt)}</div>${table(c)}</div>`;
  }

  /* ---------- a company page of the Sankey site (views.json) ---------- */
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete store[u]; throw e; }));
  const SRC = ((typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || '').replace(/[^/]*$/, '');
  let shareP = null;
  const share = () => {
    if (typeof window === 'undefined' || typeof document === 'undefined' || !document.head) return Promise.resolve(null);
    if (window.FFShare) return Promise.resolve(window.FFShare);
    return shareP || (shareP = new Promise((res) => { const sc = document.createElement('script'); sc.src = SRC + 'chart-share.js'; sc.onload = () => res(window.FFShare || null); sc.onerror = () => res(null); document.head.appendChild(sc); setTimeout(() => res(window.FFShare || null), 8000); }));
  };
  async function render(el, ctx) {
    css();
    const hub = ctx && ctx.hub != null ? ctx.hub : '', T = String((ctx && ctx.ticker) || '').toUpperCase().replace(/\./g, '-');
    if (!T) { el.innerHTML = '<p class="muted">No ticker: options need a listed share.</p>'; return; }
    el.innerHTML = '<p class="muted">Loading the option chain…</p>';
    const [c, sum] = await Promise.all([get(hub + 'data/market/options/' + encodeURIComponent(T) + '.json').catch(() => null), get(hub + 'data/market/options.json').catch(() => null), share()]);
    if (ctx && ctx.here && !ctx.here()) return;
    const rows = (sum && sum.rows) || [], r = rows.find((x) => x.ticker === T) || c;
    if (!c) {
      el.innerHTML = `<div class="fop"><p class="fop-sub">No published CBOE option-chain snapshot for ${esc(T)} yet. Popular names are prioritized for supplemental weekday scans, with a full-universe scan after the close. A missing snapshot does not imply that no options trade.</p></div>`;
      return;
    }
    if (!(c.paths || []).length) {
      // Legacy CBOE summaries can contain IV, OI, smile and GEX without the
      // newer price-path field. Show the known facts instead of claiming that
      // the underlying chain was never collected.
      const last = String(c.as_of || c.generated_at || r?.as_of || 'not recorded');
      el.innerHTML = `<div class="fop"><h3>${esc(T)} · option-chain snapshot available</h3><p class="fop-sub">CBOE delayed source: ${esc(last)}. The price-path model has not been published for this snapshot; priority supplemental scans attempt to repair missing paths. No forecast is inferred from missing path data.</p><div class="fop-cards">
        <div class="fop-card"><span>Spot (source-date)</span><b>${px(c.spot)}</b></div>
        <div class="fop-card"><span>IV30</span><b>${fin(c.iv30) ? fmt(c.iv30, 1) + '%' : '—'}</b></div>
        <div class="fop-card"><span>Put / call OI</span><b>${fin(c.pc_oi) ? fmt(c.pc_oi, 2) : '—'}</b></div>
        <div class="fop-card"><span>Contracts in snapshot</span><b>${fin(c.contracts) ? fmt(c.contracts) : '—'}</b></div>
        </div></div>`;
      return;
    }
    const em = r && fin(r.iv30) && fin(r.spot) ? r.spot * r.iv30 / 100 * Math.sqrt(30 / 365) : null;
    const card = (l, v, n) => `<div class="fop-card"><span>${esc(l)}</span><b>${v}</b>${n ? `<i>${esc(n)}</i>` : ''}</div>`;
    el.innerHTML = `<div class="fop"><p class="fop-sub">What ${esc(T)}'s options price in, from CBOE's delayed quotes collected after the close${c.as_of ? ' (' + esc(String(c.as_of).slice(0, 16)) + ')' : ''}. History and models, not investment advice.</p>` +
      `<div class="fop-cards">${card('Spot', px(c.spot), '')}${card('IV30', r && fin(r.iv30) ? fmt(r.iv30, 1) + '%' : '—', r && fin(r.iv30_pct) ? fmt(r.iv30_pct * 100, 0) + 'th percentile of its history' : 'CBOE 30-day implied volatility')}` +
      `${card('Expected move, 30 days', em ? '±' + px(em) : '—', 'one standard deviation from IV30')}${card('Put / call open interest', r && fin(r.pc_oi) ? fmt(r.pc_oi, 2) : '—', '')}` +
      `${card('Max pain', px(c.max_pain), c.max_pain_exp ? 'nearest monthly ' + c.max_pain_exp : '')}${card('Put wall · call wall', `${px(c.put_wall)} · ${px(c.call_wall)}`, 'all expiries, most open interest')}</div>` +
      panel(c, T, { cls: '' }) + '</div>';
  }

  const api = { invN, fan, sim, svg, table, post, panel, render };
  if (typeof window !== 'undefined') window.FFOptionPaths = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
