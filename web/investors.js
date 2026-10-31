/* Corporate investors (pipeline/investments.py → data/investors/*): what listed companies invest in — the investment
 * balances and gains they tag in XBRL, the companies their own 10-Qs and 10-Ks name as investees (Amazon: Anthropic and
 * OpenAI; Alphabet: SpaceX; Microsoft: OpenAI), and, from the Disclosures hub, the listed stakes in their own 13F
 * (disclosures/data/market/crossholdings.json). A 13F lists 13(f) securities only, so a private stake never appears in
 * one: the 10-Q/10-K notes are where it is.
 *   #investors          the ranking, the most-named investees, "who invested in …", the companies' own 13F stakes
 *   #investee-<key>     one investee: the listed companies that name it, and the companies whose 13F holds it
 *   #c-<cik>-invest     one company's investments (the company page's "Investments" tab)
 */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const usd = (v, sign) => {
    if (v == null || !Number.isFinite(+v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : sign && v > 0 ? '+' : '';
    if (a >= 0.95e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}$${(a / 1e9).toFixed(a >= 100e9 ? 0 : 1)}B`;
    if (a >= 0.95e6) return `${s}$${(a / 1e6).toFixed(a >= 100e6 ? 0 : 1)}M`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
    return `${s}$${a.toFixed(0)}`;
  };
  const pct = (x, d = 0) => (x == null || !Number.isFinite(+x) ? '—' : `${(100 * x).toFixed(d)}%`);
  const fdate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).slice(0, 10) + 'T00:00:00Z');
    return Number.isNaN(+d) ? String(s) : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  };
  const hubCache = new Map();
  const hub = (p) => {                                    // the Disclosures hub's data (13F managers, cross-holdings)
    if (!hubCache.has(p)) hubCache.set(p, fetch('disclosures/data/' + p).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return hubCache.get(p);
  };
  const own = (getJSON, p) => getJSON(p).catch(() => null);
  const ROLE = { nm: 'Non-marketable equity', em: 'Equity-method investments', fv: 'Marketable equity (fair value)', lt: 'Long-term investments (as tagged)' };
  const ROLE_SHORT = { nm: 'Non-marketable', em: 'Equity method', fv: 'Marketable', lt: 'Long-term (as tagged)' };
  const KIND = { value: 'Carrying value', invested: 'Invested', commit: 'Committed', gain: 'Gain', loss: 'Loss', fact: 'Tagged', other: '' };
  const enc = (k) => encodeURIComponent(k);
  const SUFFIX = new Set('inc incorporated corp corporation co company ltd limited llc lp l p plc pbc sa ag nv se gmbh bv holdings holding group global the spa kk ab asa oyj sas srl pte pty member'.split(' '));
  const keyOf = (s) => {                                 // as pipeline/investments.py key_of: 'Anthropic, PBC' -> 'anthropic'
    const w = String(s || '').toLowerCase().replace(/&/g, ' and ').replace(/’/g, "'").replace(/'s\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);
    while (w.length > 1 && SUFFIX.has(w[w.length - 1])) w.pop();
    while (w.length > 1 && w[0] === 'the') w.shift();
    return w.join(' ');
  };

  function css() {
    if (document.getElementById('iv-css')) return;
    const s = document.createElement('style');
    s.id = 'iv-css';
    s.textContent = `
.iv{--iv-nm:#2a78d6;--iv-em:#eb6834;--iv-fv:#1baf7a;--iv-lt:#8f8d86;--iv-g:#2a78d6;--iv-pt:#c4c2ba;--iv-grid:var(--line)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .iv{--iv-nm:#3987e5;--iv-em:#d95926;--iv-fv:#199e70;--iv-lt:#7c7a73;--iv-g:#3987e5;--iv-pt:#55534e}}
:root[data-theme="dark"] .iv{--iv-nm:#3987e5;--iv-em:#d95926;--iv-fv:#199e70;--iv-lt:#7c7a73;--iv-g:#3987e5;--iv-pt:#55534e}
.iv-kpis{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}
.iv-kpi{padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--surface);display:grid;gap:2px;min-width:0}
.iv-kpi .l{font-size:12.5px;color:var(--muted)}.iv-kpi .v{font-size:21px;font-weight:600;font-variant-numeric:tabular-nums}
.iv-kpi .d{font-size:12.5px;color:var(--muted)}.iv-kpi .d b{color:var(--ink-2);font-weight:600}
.iv-chart{border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:12px 12px 8px;position:relative;display:grid;gap:8px}
.iv-chart h3{margin:0;font-size:15px}.iv-chart .sub{font-size:12.5px;color:var(--muted);margin:-4px 0 0}
.iv-chart svg{display:block;width:100%;height:auto;overflow:visible;touch-action:pan-y}
.iv-chart svg text{font:11px var(--sans);fill:var(--muted)}.iv-chart svg .iv-val{fill:var(--ink-2);font-weight:600}
.iv-legend{display:flex;gap:6px 16px;flex-wrap:wrap;font-size:12.5px;color:var(--ink-2)}
.iv-legend span{display:inline-flex;align-items:center;gap:6px}.iv-legend i{display:inline-block;width:10px;height:10px;border-radius:3px}
.iv-tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:7px 10px;
 font-size:12.5px;line-height:1.45;box-shadow:0 6px 18px rgba(0,0,0,.14);z-index:5;min-width:170px}
.iv-tip b{font-weight:600}.iv-tip .r{display:flex;justify-content:space-between;gap:14px}.iv-tip .r span:last-child{font-variant-numeric:tabular-nums}
.iv-tip i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
.iv-grid2{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))}
.iv-q{margin:6px 0 0;padding:6px 10px;border-left:3px solid var(--line);color:var(--ink-2);font-size:13px;white-space:normal;max-width:72ch}
.iv-q b{color:var(--ink);font-weight:600}
.iv-ev summary{cursor:pointer;color:var(--accent-ink);font-size:13px}
.iv-ev ul{margin:6px 0 0;padding-left:18px;font-size:12.5px;white-space:normal}
td.iv-wrap{white-space:normal;min-width:240px;max-width:520px}
.iv-search{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.iv-search input{font:inherit;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);min-width:min(100%,320px);flex:1 1 260px}
.iv-search button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);cursor:pointer}
.iv-chips{display:flex;flex-wrap:wrap;gap:8px}
.iv-chip{display:inline-flex;gap:6px;align-items:baseline;padding:5px 11px;border:1px solid var(--line);border-radius:999px;background:var(--surface);font-size:13.5px;color:var(--ink);text-decoration:none}
.iv-chip:hover{border-color:var(--muted)}.iv-chip .n{color:var(--muted);font-size:12px}
.iv-bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.iv-h{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.iv-mini{display:flex;gap:4px 10px;flex-wrap:wrap;font-size:12.5px;white-space:normal}
.iv-mini a{color:var(--ink)}.iv-mini.muted a{color:var(--ink-2)}
.iv-rank td.iv-wrap{min-width:260px;max-width:440px}.iv-rank .co{flex-wrap:wrap}.iv-ph{display:none;margin-top:4px}
@media (max-width:640px){.iv-rank th:nth-child(n+3),.iv-rank td:nth-child(n+3){display:none}.iv-rank td.iv-wrap{min-width:0}.iv-ph{display:block}}
@media (max-width:640px){.iv-kpi .v{font-size:19px}td.iv-wrap{min-width:200px}}`;
    document.head.appendChild(s);
  }

  // ------------------------------------------------------------------ charts (inline SVG, one y-axis each)
  function ticks(lo, hi, n = 4) {
    const span = hi - lo || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
    const out = [];                                       // from below the lowest value to above the highest
    for (let v = Math.floor(lo / step + 1e-9) * step; v < hi + step - 1e-6 * step; v += step) out.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return out;
  }
  const shortQ = (r) => String(r.label || r.end || '').replace(/^Q(\d) (\d{2})(\d{2})$/, 'Q$1 ’$3');
  const colPath = (x, y0, y1, w, r) => {                // a column with a rounded data end, square at the baseline
    const top = Math.min(y0, y1), bot = Math.max(y0, y1), h = bot - top, rr = Math.min(r, h, w / 2);
    if (h <= 0.5) return '';
    if (y1 <= y0) return `M${x},${bot}V${top + rr}Q${x},${top} ${x + rr},${top}H${x + w - rr}Q${x + w},${top} ${x + w},${top + rr}V${bot}Z`;
    return `M${x},${top}V${bot - rr}Q${x},${bot} ${x + rr},${bot}H${x + w - rr}Q${x + w},${bot} ${x + w},${bot - rr}V${top}Z`;
  };

  /* columns: rows = quarters; groups = [[series, ...]] — each group is one column (its series stacked), groups side by
     side. tip(i) gives a quarter's tooltip. Returns the SVG and a binder for hover. */
  function columns(rows, groups, opts) {
    const W = opts.narrow ? 380 : 720, H = opts.h || (opts.narrow ? 210 : 230), L = opts.narrow ? 44 : 52, R = 8, T = 14, B = 26;
    const n = rows.length, pw = W - L - R, ph = H - T - B;
    let lo = 0, hi = 0;
    rows.forEach((r) => groups.forEach((g) => {
      let pos = 0, neg = 0;
      g.forEach((s) => { const v = r[s.k]; if (v > 0) pos += v; else if (v < 0) neg += v; });
      hi = Math.max(hi, pos); lo = Math.min(lo, neg);
    }));
    if (hi === lo) hi = lo + 1;
    const tk = ticks(lo, hi);
    lo = Math.min(lo, tk[0]); hi = Math.max(hi, tk[tk.length - 1]);
    const y = (v) => T + ph * (1 - (v - lo) / (hi - lo));
    const band = pw / n, gw = Math.min(24, (band * 0.62) / groups.length), gap = groups.length > 1 ? 3 : 0;
    let out = tk.map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--iv-grid)" stroke-width="1"${v === 0 ? '' : ' opacity=".7"'}/>
      <text x="${L - 6}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end">${esc(usd(v))}</text>`).join('');
    const every = opts.narrow ? Math.max(1, Math.ceil(n / 5)) : n > 14 ? 2 : 1;
    rows.forEach((r, i) => {
      const cx = L + band * (i + 0.5), total = groups.length * gw + (groups.length - 1) * gap;
      groups.forEach((g, gi) => {
        const x = cx - total / 2 + gi * (gw + gap);
        let pos = 0, neg = 0;
        const segs = g.filter((s) => r[s.k]);
        const lastPos = segs.filter((s) => r[s.k] > 0).pop(), lastNeg = segs.filter((s) => r[s.k] < 0).pop();
        segs.forEach((s) => {
          const v = r[s.k];
          const a = v > 0 ? pos : neg, b = a + v;
          if (v > 0) pos = b; else neg = b;
          const ya = y(a), yb = y(b);
          const end = s === (v > 0 ? lastPos : lastNeg);
          const inner = a !== 0 ? (v > 0 ? -2 : 2) : 0;          // a 2px surface gap between stacked segments
          const d = end ? colPath(x, ya + inner, yb, gw, 4) : colPath(x, ya + inner, yb, gw, 0);
          if (d) out += `<path d="${d}" fill="var(${s.c})"/>`;
        });
      });
      if ((n - 1 - i) % every === 0) out += `<text x="${cx.toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(shortQ(r))}</text>`;
      out += `<rect data-i="${i}" x="${(L + band * i).toFixed(1)}" y="${T}" width="${band.toFixed(1)}" height="${ph}" fill="transparent"/>`;
    });
    if (opts.label) {                                     // the latest column's total, at its end
      const r = rows[n - 1], v = opts.label(r);
      if (v != null) {
        const cx = L + band * (n - 0.5);
        out += `<text class="iv-val" x="${cx.toFixed(1)}" y="${(y(Math.max(v, 0)) - 5).toFixed(1)}" text-anchor="end">${esc(usd(v))}</text>`;
      }
    }
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.aria || '')}">${out}</svg>`;
  }
  function bindTips(box, tip) {
    const svg = box.querySelector('svg');
    if (!svg) return;
    let el = null;
    const hide = () => { if (el) { el.remove(); el = null; } };
    const show = (e) => {
      const t = e.target.closest('rect[data-i]');
      if (!t) return hide();
      const html = tip(+t.dataset.i);
      if (!html) return hide();
      if (!el) { el = document.createElement('div'); el.className = 'iv-tip'; box.appendChild(el); }
      el.innerHTML = html;
      const bb = box.getBoundingClientRect(), rb = t.getBoundingClientRect();
      const x = rb.left - bb.left + rb.width / 2, w = el.offsetWidth;
      el.style.left = Math.max(4, Math.min(bb.width - w - 4, x - w / 2)) + 'px';
      el.style.top = Math.max(4, (e.clientY || rb.top + 20) - bb.top - el.offsetHeight - 14) + 'px';
    };
    svg.addEventListener('pointermove', show);
    svg.addEventListener('pointerdown', show);
    svg.addEventListener('pointerleave', hide);
  }
  const legend = (series) => `<div class="iv-legend">${series.map((s) => `<span><i style="background:var(${s.c})"></i>${esc(s.l)}</span>`).join('')}</div>`;
  const tipRows = (title, items) => `<b>${esc(title)}</b>${items.filter((x) => x[2] != null).map(([c, l, v]) =>
    `<div class="r"><span>${c ? `<i style="background:var(${c})"></i>` : ''}${esc(l)}</span><span>${esc(v)}</span></div>`).join('')}`;

  // ------------------------------------------------------------------ one company (#c-<cik>-invest)
  const BAL_SERIES = [{ k: 'nm', c: '--iv-nm', l: ROLE.nm }, { k: 'em', c: '--iv-em', l: ROLE.em }, { k: 'fv', c: '--iv-fv', l: ROLE.fv }, { k: 'lt', c: '--iv-lt', l: ROLE.lt }];
  const total = (r) => ['nm', 'em', 'fv', 'lt'].reduce((a, k) => a + (r[k] || 0), 0);
  function yearAgo(q, k) {
    const last = q[q.length - 1];
    if (!last || last[k] == null) return null;
    const e0 = Date.parse(last.end);
    const r = q.find((x) => x[k] != null && Math.abs((e0 - Date.parse(x.end)) / 864e5 - 365) <= 25);
    return r ? r[k] : null;
  }
  const bold = (s) => esc(s).replace(/\$\s?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand)?/gi, (m) => `<b>${m}</b>`);
  function bestCell(b) {
    if (!b) return '<span class="muted">named, no amount</span>';
    const when = b.at ? ` <span class="muted">${b.from ? `${esc(fdate(b.from))} – ` : 'at '}${esc(fdate(b.at))}</span>` : '';
    const how = b.how === 'xbrl' ? `<span class="muted small">tagged: ${esc(b.l || '')}</span>` : '<span class="muted small">stated in the text</span>';
    return `<b>${esc(usd(b.usd))}</b> <span class="muted">${esc((KIND[b.k] || '').toLowerCase())}</span>${when}<br>${how}`;
  }
  function factList(x) {
    if (!x || !x.length) return '';
    return `<ul>${x.slice(0, 8).map((f) => {
      const v = f[5] === 'USD' ? usd(f[4]) : f[5] === 'pure' ? pct(f[4], 1) : f[5] === 'shares' ? `${(f[4] / 1e6).toFixed(f[4] >= 1e8 ? 0 : 1)}M shares` : `${f[4]} ${f[5]}`;
      return `<li>${esc(f[1] || f[0])}: <b>${esc(v)}</b> <span class="muted">${f[2] ? `${esc(fdate(f[2]))} – ` : ''}${esc(fdate(f[3]))}</span></li>`;
    }).join('')}</ul>`;
  }
  function evidence(n) {
    const sents = (n.s || []).map((s) => `<blockquote class="iv-q">${bold(s.t)}${s.url ? ` <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.form || '')} ${esc(fdate(s.filed))} ↗</a>` : ''}</blockquote>`).join('');
    const facts = n.x && n.x.length ? `<div class="small" style="margin-top:6px">Tagged on “${esc(n.name)}” in the filing’s XBRL:</div>${factList(n.x)}` : '';
    if (!sents && !facts) return '';
    return `<details class="iv-ev"><summary>What the filing says</summary>${facts}${sents}</details>`;
  }
  function namedTable(list, me) {
    if (!list.length) return '';
    return `<div class="tbl-wrap"><table class="small"><thead><tr><th>Investee</th><th>Amount the filing gives</th><th>Source</th><th>Evidence</th></tr></thead><tbody>
      ${list.map((n) => `<tr><td><div class="iv-h"><a href="#investee-${enc(n.key)}"><b>${esc(n.name)}</b></a>${n.cik ? ` <a class="tag mono" href="#c-${n.cik}" title="An SEC registrant with this ticker: listed, or filed to list">${esc(n.t || 'registrant')}</a>` : ' <span class="tag" title="No SEC registrant goes by this name">private</span>'}</div>
        <div class="muted small">${(n.via || []).map((v) => (v === 'xbrl' ? 'XBRL member' : 'named in the text')).join(' · ')}</div></td>
        <td>${bestCell(n.best)}</td>
        <td>${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.form || 'filing')} ↗</a>` : esc(n.form || '')}<div class="muted small">filed ${esc(fdate(n.filed))}</div></td>
        <td class="iv-wrap">${evidence(n)}</td></tr>`).join('')}
      </tbody></table></div>`;
  }
  function f13Block(holder, mgr, name) {
    if (!holder || !(holder.edges || []).length) return '';
    const top = holder.edges.slice(0, 10);
    const link = mgr ? `<a href="disclosures/#people/m-${esc(holder.cik)}">Every quarter of its 13F →</a>` : `<a href="disclosures/#cross/holders">Cross-holdings →</a>`;
    return `<section class="section"><div class="section-head"><h2>Listed stakes in its own 13F</h2><span class="muted">${esc(name)} files a 13F for its own portfolio · quarter ended ${esc(fdate(holder.as_of))}, filed ${esc(fdate(holder.filed))} · ${link}</span></div>
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Stock</th><th>Issuer</th><th class="num">Value</th><th class="num">Of the 13F</th><th class="num">Of its shares</th></tr></thead><tbody>
      ${top.map((e) => `<tr><td><a class="mono" href="#t-${esc(e.ticker)}">${esc(e.ticker)}</a></td><td>${esc(e.issuer || '')}</td><td class="num">${esc(usd(e.usd))}</td><td class="num">${esc(pct(e.weight, 1))}</td><td class="num">${e.pct_out != null ? esc(pct(e.pct_out, 1)) : '—'}</td></tr>`).join('')}
      </tbody></table></div>
      <p class="muted small">A 13F lists only 13(f) securities — listed shares, ETFs and some options — so stakes in private companies never appear in it; they are in the 10-Q and 10-K notes above. ${holder.positions > top.length ? `${holder.positions} positions in all, ${esc(usd(holder.total))}.` : ''}</p></section>`;
  }

  async function company(body, c, ctx) {
    css();
    const cik = +c.profile.cik, me = (c.profile.tickers || [])[0] || c.profile.name;
    const [d, cross, mgrs] = await Promise.all([own(ctx.getJSON, `investors/c/${cik}.json`), hub('market/crossholdings.json'), hub('research/people/managers.json')]);
    if (ctx.here && !ctx.here()) return;
    const holder = cross && (cross.holders || []).find((h) => h.kind === 'corp' && +h.cik === cik);
    const mgr = mgrs && (mgrs.rows || []).some((r) => +r[0] === cik);
    const wrap = document.createElement('div');
    wrap.className = 'iv';
    body.appendChild(wrap);
    if (!d) {
      wrap.innerHTML = `<p class="muted">No investment balance, investment gain or named investee has been read for ${esc(c.profile.name)} yet. The scan reads a few dozen companies’ figures and filings a run, the largest investors first.</p>${f13Block(holder, mgr, me)}`;
      return;
    }
    const q = d.q || [], last = q[q.length - 1] || {}, ttm = d.ttm || {};
    const used = BAL_SERIES.filter((s) => q.some((r) => r[s.k]));
    const kpi = (l, v, sub) => `<div class="iv-kpi"><span class="l">${esc(l)}</span><span class="v">${v}</span><span class="d">${sub || ''}</span></div>`;
    const chg = (k) => { const a = yearAgo(q, k); return a ? `${last[k] >= a ? '+' : '−'}${esc(usd(Math.abs(last[k] - a)))} in a year` : ''; };
    const share = ttm.g != null && ttm.pti > 0 ? ttm.g / ttm.pti : null;
    const kpis = used.map((s) => kpi(ROLE_SHORT[s.k], esc(usd(last[s.k])), last[s.k] != null ? `${chg(s.k)}${(last.filled || []).includes(s.k) ? ' · from the filing’s XBRL' : ''}` : 'not tagged this quarter'))
      .concat(ttm.g != null ? [kpi('Investment gains, last 12 months', esc(usd(ttm.g, true)), share != null ? `<b>${esc(pct(share))}</b> of pretax income (${esc(usd(ttm.pti))})` : ttm.pti != null ? `pretax income ${esc(usd(ttm.pti))}` : '')] : [])
      .concat(ttm.emi != null ? [kpi('Equity-method income, 12 months', esc(usd(ttm.emi, true)), 'its share of investees’ profit')] : []);
    const narrow = (body.clientWidth || 800) < 560;
    const balRows = q.filter((r) => used.some((s) => r[s.k] != null));
    const gRows = q.filter((r) => r.g != null || r.pti != null);
    const named = d.named || [];
    const srcLine = Object.entries(d.src || {}).filter(([k]) => ROLE[k] || k === 'g').map(([k, v]) => `${ROLE[k] || 'Gains'}: ${esc(v[1] || v[0])}`).join(' · ');
    wrap.innerHTML = `<section class="section"><div class="section-head"><h2>Investments</h2><span class="muted">What ${esc(me)} holds in other companies, as its own filings tag and name it · latest quarter ended ${esc(fdate(last.end))}</span></div>
      ${kpis.length ? `<div class="iv-kpis">${kpis.join('')}</div>` : ''}
      <div class="iv-grid2">
        ${balRows.length ? `<div class="iv-chart" id="iv-bal"><h3>Investment balances by quarter</h3><p class="sub">Quarter-end carrying values, stacked</p>${legend(used)}${columns(balRows, [used], { narrow, aria: `${me}: investment balances by quarter`, label: total })}</div>` : ''}
        ${gRows.some((r) => r.g != null) ? `<div class="iv-chart" id="iv-gain"><h3>Investment gains against pretax income</h3><p class="sub">Each quarter: pretax income, and the gains (losses) on investments inside it</p>${legend([{ c: '--iv-pt', l: 'Pretax income' }, { c: '--iv-g', l: 'Gains (losses) on investments' }])}${columns(gRows, [[{ k: 'pti', c: '--iv-pt' }], [{ k: 'g', c: '--iv-g' }]], { narrow, aria: `${me}: investment gains and pretax income by quarter` })}</div>` : ''}
      </div>
      <details class="iv-ev"><summary>The figures, quarter by quarter</summary><div class="tbl-wrap" style="margin-top:8px"><table class="small"><thead><tr><th>Quarter</th>${used.map((s) => `<th class="num">${esc(ROLE_SHORT[s.k])}</th>`).join('')}<th class="num">Gains</th><th class="num">Pretax income</th><th class="num">Gains ÷ pretax</th>${q.some((r) => r.emi != null) ? '<th class="num">Equity-method income</th>' : ''}</tr></thead><tbody>
        ${q.slice().reverse().map((r) => `<tr><td>${esc(r.label || r.end)} <span class="muted">${esc(fdate(r.end))}</span></td>${used.map((s) => `<td class="num">${esc(usd(r[s.k]))}</td>`).join('')}<td class="num">${esc(usd(r.g, true))}</td><td class="num">${esc(usd(r.pti))}</td><td class="num">${r.g != null && r.pti > 0 ? esc(pct(r.g / r.pti)) : '—'}</td>${q.some((x) => x.emi != null) ? `<td class="num">${esc(usd(r.emi, true))}</td>` : ''}</tr>`).join('')}
      </tbody></table></div><p class="muted small">Tags read: ${srcLine || '—'}. Gains are the company’s own total (gain or loss on investments) where it tags one, else gains on equity securities at fair value plus the upward adjustments, less the downward adjustments and impairments, of non-marketable equity.</p></details>
      </section>
      <section class="section"><div class="section-head"><h2>Companies it names as investees</h2><span class="muted">${named.length ? `${named.length} named in its latest 10-Q and 10-K` : 'none named in the filings read'}</span></div>
        ${named.length ? namedTable(named, me) : `<p class="muted">${esc(me)}’s latest filings put no company name in an investment phrase and tag none on an investee axis${(d.read || []).length ? ` (read: ${(d.read || []).map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.form)} ${esc(fdate(r.filed))}</a>`).join(', ')})` : ''}. Many companies report the balance without naming the companies in it.</p>`}
      </section>
      ${f13Block(holder, mgr, me)}
      <p class="muted small">Non-marketable equity: stakes without a readily determinable fair value — most private companies — carried at cost less impairment, adjusted only when a comparable financing round gives an observable price, so the balance can jump in one quarter. Equity method: a share of an investee’s profit, usually for 20–50% stakes. Carrying values are neither cost nor market value. A company is named only where its filing tags it on an investee axis or a sentence puts it in an investment phrase (“invested $5.0 billion in …”, “our investment in …”); a name that appears only as a customer, lessor or guarantee counterparty is left out. Read automatically from SEC filings; check the filing before relying on a figure. <a href="#investors">All corporate investors →</a></p>`;
    const bal = wrap.querySelector('#iv-bal');
    if (bal) bindTips(bal, (i) => { const r = balRows[i]; return tipRows(`${r.label || r.end} · ${fdate(r.end)}`, used.map((s) => [s.c, ROLE_SHORT[s.k], r[s.k] != null ? usd(r[s.k]) : null]).concat([[null, 'Total', usd(total(r))]])); });
    const gain = wrap.querySelector('#iv-gain');
    if (gain) bindTips(gain, (i) => { const r = gRows[i]; return tipRows(`${r.label || r.end} · ${fdate(r.end)}`, [['--iv-pt', 'Pretax income', r.pti != null ? usd(r.pti) : null], ['--iv-g', 'Investment gains', r.g != null ? usd(r.g, true) : null], [null, 'Gains ÷ pretax', r.g != null && r.pti > 0 ? pct(r.g / r.pti) : null]]); });
  }

  // ------------------------------------------------------------------ the index (#investors)
  const F = (ix) => Object.fromEntries((ix.fields || []).map((f, i) => [f, i]));
  async function index(app, ctx) {
    css();
    const here = ctx.here || (() => true);
    if (ctx.setNav) ctx.setNav('investors');
    const [ix, cross, mgrs] = await Promise.all([own(ctx.getJSON, 'investors/index.json'), hub('market/crossholdings.json'), hub('research/people/managers.json')]);
    if (!here()) return;
    if (!ix) { app.innerHTML = '<div class="page-head"><h1>Corporate investors</h1><p class="muted">The investment figures have not been generated yet; the scan builds them every 15 minutes.</p></div>'; return; }
    const f = F(ix), mset = new Set(((mgrs && mgrs.rows) || []).map((r) => +r[0]));
    const corp = new Map(((cross && cross.holders) || []).filter((h) => h.kind === 'corp').map((h) => [+h.cik, h]));
    const st = { fin: false, sort: 'total', all: false };
    const sorts = [['total', 'Total'], ['nm', 'Non-marketable'], ['em', 'Equity method'], ['fv', 'Marketable'], ['g_share', 'Gains ÷ pretax'], ['named', 'Named investees']];
    const chip = (x, i) => `<a class="iv-chip"${i >= 10 ? ' data-more hidden' : ''} href="#investee-${enc(x.key)}">${esc(x.name)}<span class="n">${x.n} listed investor${x.n === 1 ? '' : 's'}${x.t ? ' · ' + esc(x.t) : ''}</span></a>`;
    const tops = (ix.investees || []).slice(0, 30);
    const chips = tops.map(chip).join('') + (tops.length > 10 ? `<button type="button" class="pill" id="iv-more">+${tops.length - 10} more</button>` : '');
    const fin = (h) => +h.sic >= 6000 && +h.sic < 6800 && ![1067983, 1065521].includes(+h.cik);   // a broker's book is no corporate stake
    const corpRows = Array.from(corp.values()).filter((h) => !fin(h)).sort((a, b) => (b.total || 0) - (a.total || 0)).slice(0, 14);
    app.innerHTML = `<div class="page-head iv"><div class="eyebrow">Corporate investors</div>
      <h1>What listed companies invest in</h1>
      <p class="muted">Every company’s investment balances and gains as it tags them in its 10-Q and 10-K — non-marketable stakes (where private companies such as Anthropic or OpenAI sit), equity-method investments, marketable shares — the companies its filings name as investees, and the listed stakes in the 13F some of them file for their own portfolio. ${ix.companies} companies with an investment balance or a named investee; ${ix.read} with their latest filings read so far.</p></div>
      <section class="section iv"><div class="section-head"><h2>Who invested in …?</h2><span class="muted">A private company, or a listed one held through a 13F</span></div>
        <form class="iv-search" id="iv-find"><input id="iv-q" list="iv-list" placeholder="Anthropic, OpenAI, SpaceX, Intel…" autocomplete="off" aria-label="Investee name or ticker"><button type="submit">Find</button></form>
        <datalist id="iv-list"></datalist><div id="iv-found"></div>
        ${chips ? `<div class="iv-chips">${chips}</div>` : ''}</section>
      <section class="section iv"><div class="section-head"><h2>The largest corporate investors</h2><span class="muted">Latest quarter on file, as tagged in XBRL</span></div>
        <div class="iv-bar"><div class="seg" role="group" aria-label="Which companies"><button type="button" data-fin="0" class="on">Operating companies</button><button type="button" data-fin="1">With banks, insurers and funds</button></div>
        <label class="small">Sort by <select id="iv-sort">${sorts.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join('')}</select></label></div>
        <div id="iv-table"></div></section>
      ${corpRows.length ? `<section class="section iv"><div class="section-head"><h2>Listed stakes in companies’ own 13F</h2><span class="muted">Operating companies that file a 13F for their own portfolio · the largest positions in the latest one</span></div>
        <div class="tbl-wrap"><table class="small"><thead><tr><th>Company</th><th class="num">13F total</th><th>Largest positions</th><th>Quarter</th></tr></thead><tbody>
        ${corpRows.map((h) => `<tr><td><span class="co"><a class="mono" href="#c-${h.cik}-invest">${esc(h.ticker || '')}</a> <span>${esc(h.label)}</span></span></td><td class="num">${esc(usd(h.total))}</td>
          <td class="iv-wrap"><div class="iv-mini">${(h.edges || []).slice(0, 5).map((e) => `<span><a class="mono" href="#t-${esc(e.ticker)}">${esc(e.ticker)}</a> ${esc(usd(e.usd))}</span>`).join('')}</div></td>
          <td>${mset.has(+h.cik) ? `<a href="disclosures/#people/m-${h.cik}">${esc(fdate(h.as_of))} ↗</a>` : esc(fdate(h.as_of))}</td></tr>`).join('')}
        </tbody></table></div><p class="muted small">From the Disclosures hub’s <a href="disclosures/#cross">cross-holdings</a>. A 13F lists listed shares only: SpaceX entered Alphabet’s and NVIDIA’s 13F once it listed; their private stakes are in the table above.</p></section>` : ''}
      <p class="muted small iv">Read from SEC filings by fixed rules: balances from SEC’s company facts (us-gaap tags), investees from each company’s latest 10-Q and 10-K (members of investee axes in its XBRL, and sentences such as “we invested $5.0 billion in …”). Carrying values are neither cost nor market value; non-marketable stakes are revalued only when a financing round gives an observable price. Updated ${esc(fdate(ix.generated))}. Not investment advice.</p>`;
    const draw = () => {
      let rows = (ix.rows || []).filter((r) => st.fin || !r[f.fin]);
      const key = st.sort, k = f[key];
      rows = rows.slice().sort((a, b) => (Math.abs(b[k] || 0) - Math.abs(a[k] || 0)) || ((b[f.total] || 0) - (a[f.total] || 0)));
      if (key === 'g_share') rows = rows.filter((r) => r[f.g_share] != null);
      const shown = st.all ? rows : rows.slice(0, 40);
      document.getElementById('iv-table').innerHTML = `<div class="tbl-wrap"><table class="small iv-rank"><thead><tr><th>#</th><th>Company · named investees</th><th class="num">Non-marketable</th><th class="num">Equity method</th><th class="num">Marketable</th><th class="num">Total</th><th class="num">1-year change</th><th class="num">Gains, 12 months<br><span class="muted">of pretax income</span></th></tr></thead><tbody>
        ${shown.map((r, i) => {
          const ch = r[f.total] != null && r[f.total_ya] ? r[f.total] - r[f.total_ya] : null;
          const tops = r[f.top] || [];
          const top = tops.map(([n, t, kk]) => `<a href="#investee-${enc(kk || keyOf(n))}">${esc(n)}</a>`).join(' · ');
          const f13 = corp.has(+r[f.cik]) ? ` <a class="tag" href="${mset.has(+r[f.cik]) ? `disclosures/#people/m-${r[f.cik]}` : 'disclosures/#cross/holders'}" title="Files a 13F for its own portfolio">13F</a>` : '';
          return `<tr><td class="muted">${i + 1}</td><td class="iv-wrap"><span class="co"><span class="mono">${esc(r[f.t] || '')}</span><a href="#c-${r[f.cik]}-invest"><b>${esc(r[f.name])}</b></a>${f13}</span>
            ${top ? `<div class="iv-mini muted">${top}${r[f.named] > tops.length ? ` <span>+${r[f.named] - tops.length} more</span>` : ''}</div>` : ''}
            <div class="iv-ph small">Total <b>${esc(usd(r[f.total]))}</b>${ch == null ? '' : ` <span class="muted">(${esc(usd(ch, true))} in a year)</span>`}${r[f.g_ttm] != null ? ` · gains ${esc(usd(r[f.g_ttm], true))}${r[f.g_share] != null ? ` <span class="muted">(${esc(pct(r[f.g_share]))} of pretax)</span>` : ''}` : ''}</div></td>
          <td class="num">${esc(usd(r[f.nm]))}</td><td class="num">${esc(usd(r[f.em]))}</td><td class="num">${esc(usd(r[f.fv]))}</td><td class="num"><b>${esc(usd(r[f.total]))}</b></td>
          <td class="num">${ch == null ? '—' : esc(usd(ch, true))}</td><td class="num">${esc(usd(r[f.g_ttm], true))}${r[f.g_share] != null ? `<br><span class="muted">${esc(pct(r[f.g_share]))}</span>` : ''}</td></tr>`;
        }).join('')}</tbody></table></div>
        ${rows.length > shown.length ? `<p><button type="button" class="pill" id="iv-all">Show all ${rows.length}</button></p>` : ''}`;
      const all = document.getElementById('iv-all');
      if (all) all.onclick = () => { st.all = true; draw(); };
    };
    draw();
    const more = document.getElementById('iv-more');
    if (more) more.onclick = () => { app.querySelectorAll('.iv-chip[data-more]').forEach((x) => { x.hidden = false; }); more.remove(); };
    app.querySelectorAll('[data-fin]').forEach((b) => b.onclick = () => { st.fin = b.dataset.fin === '1'; app.querySelectorAll('[data-fin]').forEach((x) => x.classList.toggle('on', x === b)); draw(); });
    document.getElementById('iv-sort').onchange = (e) => { st.sort = e.target.value; draw(); };
    finder(app, ctx, cross);
  }

  // "who invested in …": investees named in filings, and listed stocks the corporate 13F filers hold
  async function finder(app, ctx, cross) {
    const inv = await own(ctx.getJSON, 'investors/investees.json');
    const list = document.getElementById('iv-list'), form = document.getElementById('iv-find');
    if (!form) return;
    const rows = (inv && inv.rows) || [];
    const held = new Map();
    ((cross && cross.holders) || []).filter((h) => h.kind === 'corp').forEach((h) => (h.edges || []).forEach((e) => {
      if (!held.has(e.ticker)) held.set(e.ticker, { t: e.ticker, issuer: e.issuer, by: [] });
      held.get(e.ticker).by.push(h.label);
    }));
    if (list) list.innerHTML = rows.slice(0, 400).map((r) => `<option value="${esc(r.name)}">`).join('') + Array.from(held.values()).slice(0, 300).map((h) => `<option value="${esc(h.t)}">${esc(h.issuer || '')}</option>`).join('');
    form.onsubmit = (e) => {
      e.preventDefault();
      const q = document.getElementById('iv-q').value.trim();
      if (!q) return;
      const k = keyOf(q);
      const exact = rows.find((r) => r.key === k || r.name.toLowerCase() === q.toLowerCase() || (r.t && r.t.toLowerCase() === q.toLowerCase()));
      if (exact) { location.hash = '#investee-' + enc(exact.key); return; }
      if (held.has(q.toUpperCase())) { location.hash = '#investee-' + enc(q.toLowerCase()); return; }
      const near = rows.filter((r) => r.key.includes(k) || k.includes(r.key)).slice(0, 12);
      document.getElementById('iv-found').innerHTML = near.length ? `<div class="iv-chips">${near.map((r) => `<a class="iv-chip" href="#investee-${enc(r.key)}">${esc(r.name)}<span class="n">${r.n}</span></a>`).join('')}</div>`
        : `<p class="muted">No listed company names “${esc(q)}” as an investee in the filings read so far, and no corporate 13F holds it. Many companies report their private stakes without naming them.</p>`;
    };
  }

  // ------------------------------------------------------------------ one investee (#investee-<key>)
  async function investee(app, key, ctx) {
    css();
    const here = ctx.here || (() => true);
    if (ctx.setNav) ctx.setNav('investors');
    const k = decodeURIComponent(key);
    const [inv, cross] = await Promise.all([own(ctx.getJSON, 'investors/investees.json'), hub('market/crossholdings.json')]);
    if (!here()) return;
    const row = ((inv && inv.rows) || []).find((r) => r.key === k);
    const ticker = (row && row.t) || (k.length <= 6 ? k.toUpperCase() : null);
    const holders = [];
    ((cross && cross.holders) || []).filter((h) => h.kind === 'corp').forEach((h) => (h.edges || []).forEach((e) => { if (ticker && e.ticker === ticker) holders.push([h, e]); }));
    holders.sort((a, b) => (b[1].usd || 0) - (a[1].usd || 0));
    const name = (row && row.name) || (holders[0] && holders[0][1].issuer) || k;
    if (!row && !holders.length) {
      app.innerHTML = `<div class="page-head iv"><div class="crumbs"><a href="#investors">Corporate investors</a></div><h1>${esc(name)}</h1><p class="muted">No listed company names “${esc(name)}” as an investee in the filings read so far, and no corporate 13F holds it.</p></div>`;
      return;
    }
    const by = (row && row.inv) || [];
    const status = row && row.cik ? `An SEC registrant · <a class="mono" href="#c-${row.cik}">${esc(row.t || 'its filings')}</a> (on SEC’s ticker list: listed, or filed to list)` : holders.length ? `Listed · <span class="mono">${esc(ticker)}</span>` : 'Private, as far as SEC’s list of registrants goes: no registrant by this name';
    app.innerHTML = `<div class="page-head iv"><div class="crumbs"><a href="#investors">Corporate investors</a><span>/</span><span>${esc(name)}</span></div>
      <h1>Who invested in ${esc(name)}</h1>
      <p class="muted">${status}. ${by.length ? `${row.n} listed compan${row.n === 1 ? 'y names' : 'ies name'} it as an investee in their latest 10-Q or 10-K.` : ''} ${holders.length ? `${holders.length} operating compan${holders.length === 1 ? 'y holds' : 'ies hold'} its shares in their own 13F.` : ''}</p></div>
      ${by.length ? `<section class="section iv"><div class="section-head"><h2>Named in their filings</h2><span class="muted">The amount each filing gives, with the sentence it was read from</span></div>
        <div class="tbl-wrap"><table class="small"><thead><tr><th>Investor</th><th>Amount the filing gives</th><th>Source</th><th>Evidence</th></tr></thead><tbody>
        ${by.map((x) => `<tr><td><span class="co"><span class="mono">${esc(x.t || '')}</span><a class="name" href="#c-${x.cik}-invest">${esc(x.name)}</a></span><div class="muted small">${(x.via || []).map((v) => (v === 'xbrl' ? 'XBRL member' : 'named in the text')).join(' · ')}${x.fin ? ' · financial company' : ''}</div></td>
          <td>${bestCell(x.best)}</td><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.form || 'filing')} ↗</a>` : ''}<div class="muted small">filed ${esc(fdate(x.filed))}</div></td>
          <td class="iv-wrap">${x.q ? `<blockquote class="iv-q">${bold(x.q)}${x.q.length >= 420 ? '…' : ''}</blockquote>` : ''}</td></tr>`).join('')}
        </tbody></table></div></section>` : ''}
      ${holders.length ? `<section class="section iv"><div class="section-head"><h2>In companies’ own 13F</h2><span class="muted">Operating companies that file a 13F, latest quarter</span></div>
        <div class="tbl-wrap"><table class="small"><thead><tr><th>Holder</th><th class="num">Value</th><th class="num">Of its 13F</th><th class="num">Of the shares</th><th>Quarter</th></tr></thead><tbody>
        ${holders.map(([h, e]) => `<tr><td><span class="co"><span class="mono">${esc(h.ticker || '')}</span><a class="name" href="#c-${h.cik}-invest">${esc(h.label)}</a></span></td><td class="num">${esc(usd(e.usd))}</td><td class="num">${esc(pct(e.weight, 1))}</td><td class="num">${e.pct_out != null ? esc(pct(e.pct_out, 1)) : '—'}</td><td>${esc(fdate(h.as_of))}</td></tr>`).join('')}
        </tbody></table></div><p class="muted small">All 13F holders, funds included: <a href="disclosures/#cross/${esc(ticker)}">cross-holdings for ${esc(ticker)} →</a></p></section>` : ''}
      <p class="muted small iv">An amount is the one the filing gives for this investee: a balance tagged on it in XBRL where there is one, else the value, investment or commitment its sentences state — the largest one stated, not a sum, so stakes bought in several rounds can be larger. A filing that reports the stake inside a total without naming it is not counted. Read automatically from SEC filings; check the filing before relying on a figure. Not investment advice.</p>`;
  }

  global.FFInvestors = { index, investee, company, _t: { usd, pct, ticks, columns, colPath, shortQ, yearAgo, bestCell, keyOf } };
})(window);
