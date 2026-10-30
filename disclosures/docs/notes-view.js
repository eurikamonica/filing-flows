/* Notes & ties — every note of a company's latest 10-K drawn and checked (shared by the Disclosure Hub's Notes tab and the
   "Notes & ties" view of each company page on the Sankey site, listed in views.json):
     Read        a written reading where there is one, the threads that run across notes, and the linkage map (which
                 statement lines each note explains; click a note to open it)
     Statements  the four statements with, on each line, the notes that explain it and the ties it is part of
     Notes       each note: what changed (written by rules from the numbers), a chart per detail table (roll-forward
                 waterfalls, schedules by year, compositions, splits by segment / market / region, the tax-rate bridge),
                 the table itself, the note's text, the lines it explains and its checks
     Checks      勾稽 — every tie recomputed from the facts: the company's own sums, every roll-forward, splits against their
                 totals, ties across statements and notes, balance sheet changes against the cash flow statement
   Data: notes-history branch, public/c/<TICKER>.json (app/notes.py), read from the repository's raw files.
   window.NotesView.render(el, {ticker, hub}) — hub: the path to the hub ('disclosures/' on the Sankey site, '' inside it). */
(function () {
  const RAW = 'https://raw.githubusercontent.com/eurikamonica/filing-flows/notes-history/public/';
  const base = () => (typeof window !== 'undefined' && window.FF_NOTES_BASE) || RAW;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const tk = (t) => String(t || '').trim().toUpperCase().replace(/\./g, '-');
  const ST_NAME = { is: 'Income statement', bs: 'Balance sheet', cf: 'Cash flows', eq: 'Equity', oci: 'Comprehensive income', other: 'Other' };
  const ST_ORDER = ['is', 'oci', 'bs', 'cf', 'eq', 'other'];
  const STATUS = { tie: ['✓', 'Ties', 'nv-ok'], round: ['≈', 'Within rounding', 'nv-round'], info: ['Δ', 'Explained difference', 'nv-info'], gap: ['✗', 'Does not tie', 'nv-bad'] };
  const SCOPES = [['', 'All checks'], ['statement-note', 'Statement ↔ note'], ['note', 'Within a note'], ['note-note', 'Note ↔ note'], ['statement', 'Between statements'], ['cf-bs', 'Cash flow vs balance sheet']];
  const KINDS = { sum: 'Sum', rollfwd: 'Roll-forward', members: 'Split', tie: 'Tie', cf_bs: 'Cash flow vs balance sheet', dup: 'Duplicate' };
  const cache = {};
  let styled = false;

  function money(v, unit) {
    if (!fin(v)) return '—';
    if (unit === 'pure') return (v * 100).toFixed(1) + '%';
    if (unit === 'shares') { const a = Math.abs(v); return (v < 0 ? '−' : '') + (a >= 1e9 ? (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M' : Math.round(a).toLocaleString('en-US')) + ' sh'; }
    if (unit && /\//.test(unit)) return (+v).toFixed(2);
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (unit && !/^USD/.test(unit)) return s + (a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a.toLocaleString('en-US', { maximumFractionDigits: 3 }));
    return s + (a >= 1e9 ? '$' + (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : a >= 1e3 ? '$' + (a / 1e3).toFixed(0) + 'K' : '$' + a.toFixed(0));
  }
  const pts = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v * 100).toFixed(1) + ' pts' : '—');
  const year = (e) => (e ? String(e).slice(0, 4) : '');
  const FY = (e) => { if (!e) return ''; const d = new Date(e + 'T00:00:00Z'); return 'FY' + (d.getUTCMonth() >= 6 ? d.getUTCFullYear() : d.getUTCFullYear()); };

  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.nv{display:grid;gap:12px;--nv-up:var(--mk-profit,#17734a);--nv-dn:var(--mk-cost,#ea6a52);--nv-base:var(--mk-noncash,#5b7fa6);--nv-prev:color-mix(in srgb,var(--mk-rev,#7a7974) 45%,transparent)}
.nv .nv-card{border:1px solid var(--line,#dedcd5);border-radius:10px;padding:12px 14px;background:var(--surface,#fff);min-width:0}
.nv h3{margin:0 0 6px;font-size:1.02rem}.nv h4{margin:12px 0 6px;font-size:.92rem}.nv p{margin:5px 0;line-height:1.5}.nv .muted{color:var(--muted,#6b6a66)}
.nv .nv-pills{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.nv .nv-pill{border:1px solid var(--line,#dedcd5);border-radius:999px;padding:2px 9px;font-size:.8rem;white-space:nowrap}
.nv .nv-ok{color:var(--nv-up)}.nv .nv-round{color:var(--accent,#17734a)}.nv .nv-info{color:var(--q-warm,#b7792f)}.nv .nv-bad{color:var(--nv-dn)}
.nv .nv-seg{display:flex;flex-wrap:wrap;gap:6px;position:sticky;top:0;z-index:2;background:var(--bg,#f7f6f2);padding:6px 0}
.nv .nv-seg button,.nv .nv-chip,.nv .nv-btn{font:inherit;font-size:.84rem;border:1px solid var(--line,#ccc);background:var(--surface,#fff);color:inherit;border-radius:999px;padding:4px 11px;cursor:pointer}
.nv .nv-seg button[aria-pressed=true],.nv .nv-chip[aria-pressed=true]{border-color:var(--accent,#17734a);background:color-mix(in srgb,var(--accent,#17734a) 13%,var(--surface,#fff));font-weight:600}
.nv .nv-chip{padding:1px 8px;font-size:.76rem;margin:1px 2px}.nv .nv-chip.nv-n{border-color:color-mix(in srgb,var(--accent,#17734a) 55%,var(--line,#ccc))}
.nv table{border-collapse:collapse;width:100%;font-size:.84rem;min-width:0!important}.nv th{position:static;font-weight:600;text-align:right;white-space:nowrap}
.nv td,.nv th{padding:4px 6px;border-bottom:1px solid var(--line,#e8e6e0);vertical-align:top}.nv td.n,.nv th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.nv th:first-child{text-align:left}
.nv .nv-wrap{overflow-x:auto;max-width:100%}.nv .nv-tot td{font-weight:600}.nv .nv-abs td{color:var(--muted,#6b6a66);font-size:.78rem;text-transform:none}
.nv .nv-note{border:1px solid var(--line,#dedcd5);border-radius:10px;background:var(--surface,#fff)}.nv .nv-note>summary{cursor:pointer;padding:10px 14px;list-style:none;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:baseline}
.nv .nv-note>summary::-webkit-details-marker{display:none}.nv .nv-note[open]>summary{border-bottom:1px solid var(--line,#dedcd5)}.nv .nv-note .nv-body{padding:10px 14px;display:grid;gap:10px}
.nv .nv-num{font-weight:700;color:var(--accent,#17734a);min-width:52px}.nv .nv-ttl{font-weight:600;flex:1;min-width:180px}
.nv ul.nv-an{margin:4px 0;padding-left:18px}.nv ul.nv-an li{margin:3px 0;line-height:1.45}
.nv .nv-read{border-left:3px solid var(--accent,#17734a);padding:4px 10px;background:color-mix(in srgb,var(--accent,#17734a) 6%,transparent);border-radius:0 8px 8px 0}
.nv .nv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:12px}.nv .nv-chart{border:1px solid var(--line,#e8e6e0);border-radius:8px;padding:8px 10px;min-width:0}
.nv .nv-chart svg{width:100%;height:auto;display:block}.nv .nv-chart .ttl{font-size:.82rem;font-weight:600;margin-bottom:4px}
.nv svg text{fill:var(--ink,#1d1d1b);font-size:11px;font-family:inherit}.nv svg .mut{fill:var(--muted,#6b6a66)}.nv svg .ax{stroke:var(--line,#dedcd5)}
.nv .nv-text{font-size:.86rem;color:var(--ink-2,#3b3a37);max-height:260px;overflow:auto;border:1px dashed var(--line,#dedcd5);border-radius:8px;padding:6px 10px}
.nv .nv-check{border-bottom:1px solid var(--line,#e8e6e0);padding:6px 0}.nv .nv-check>summary::-webkit-details-marker{display:none}.nv .nv-check:last-child{border-bottom:0}.nv .nv-check .hd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.nv .nv-check .st{font-weight:700;min-width:18px}.nv .nv-formula{font-size:.82rem;margin:4px 0 0 26px;display:grid;grid-template-columns:auto 1fr;gap:1px 12px;max-width:640px}
.nv .nv-formula .v{text-align:right;font-variant-numeric:tabular-nums}.nv .nv-formula .eq{border-top:1px solid var(--line,#ccc);padding-top:2px}
.nv .nv-flash{animation:nvflash 1.6s ease-out}@keyframes nvflash{0%{box-shadow:0 0 0 3px var(--accent,#17734a)}100%{box-shadow:0 0 0 0 transparent}}
.nv .nv-map svg{width:100%;max-width:860px;height:auto}.nv .nv-map .lk{fill:none;stroke:var(--line,#ccc);stroke-width:1.2;opacity:.9}.nv .nv-map .lk.on{stroke:var(--accent,#17734a);stroke-width:2.2;opacity:1}
.nv .nv-map .nd{cursor:pointer}.nv .nv-map .nd rect{fill:var(--surface,#fff);stroke:var(--line,#ccc)}.nv .nv-map .nd.on rect{stroke:var(--accent,#17734a);stroke-width:2}
.nv .nv-thread{border:1px solid var(--line,#e8e6e0);border-radius:8px;padding:8px 12px}.nv .nv-thread h4{margin:0 0 4px}
@media (max-width:560px){.nv .nv-formula{margin-left:0}.nv .nv-card{padding:10px}.nv .nv-map{display:none}}`;
    document.head.appendChild(s);
  }

  async function load(t) {
    const url = base() + 'c/' + encodeURIComponent(t) + '.json';
    if (!cache[url]) cache[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw Error(r.status === 404 ? 'not built yet' : 'HTTP ' + r.status); return r.json(); })
      .catch((e) => { delete cache[url]; throw e; });
    return cache[url];
  }

  /* ---------------- charts (inline SVG) ---------------- */
  const W = 640;
  function hbars(rows, unit, opt) {
    // rows: [{label, vals:[cur, prev], depth, bold}] — grouped horizontal bars, current solid, previous light
    const LW = 210, RW = 90, x0 = LW, x1 = W - RW, rh = opt && opt.two ? 26 : 20;
    const all = rows.flatMap((r) => r.vals.filter(fin));
    const mx = Math.max(0, ...all), mn = Math.min(0, ...all), span = mx - mn || 1;
    const X = (v) => x0 + ((v - mn) / span) * (x1 - x0);
    let y = 6, out = '';
    for (const r of rows) {
      const cur = r.vals[0], prev = r.vals[1];
      out += `<text x="${4 + 10 * (r.depth || 0)}" y="${y + 12}" ${r.bold ? 'font-weight="700"' : ''}>${esc(short(r.label, 34 - 2 * (r.depth || 0)))}<title>${esc(r.label)}</title></text>`;
      if (fin(cur)) out += `<rect x="${Math.min(X(0), X(cur))}" y="${y + 2}" width="${Math.max(1, Math.abs(X(cur) - X(0)))}" height="${opt && opt.two ? 10 : 13}" fill="${cur < 0 ? 'var(--nv-dn)' : r.bold ? 'var(--nv-base)' : 'var(--nv-up)'}"/>`;
      if (opt && opt.two && fin(prev)) out += `<rect x="${Math.min(X(0), X(prev))}" y="${y + 13}" width="${Math.max(1, Math.abs(X(prev) - X(0)))}" height="8" fill="var(--nv-prev)"/>`;
      out += `<text x="${W - 4}" y="${y + 12}" text-anchor="end">${esc(money(cur, unit))}</text>`;
      if (opt && opt.two && fin(cur) && (!fin(prev) || Math.abs(prev) < 0.02 * Math.abs(cur)) && cur) out += `<text x="${W - 4}" y="${y + 23}" text-anchor="end" class="mut" font-size="9">new</text>`;
      else if (opt && opt.two && fin(prev) && fin(cur) && prev) out += `<text x="${W - 4}" y="${y + 23}" text-anchor="end" class="mut" font-size="9">${esc((cur / prev - 1 >= 0 ? '+' : '') + Math.round((cur / prev - 1) * 100) + '%')}</text>`;
      y += rh;
    }
    if (mn < 0) out = `<line class="ax" x1="${X(0)}" x2="${X(0)}" y1="2" y2="${y}"/>` + out;
    return `<svg viewBox="0 0 ${W} ${y + 4}" role="img">${out}</svg>`;
  }
  function short(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function waterfall(ch) {
    const unit = ch.unit;
    const rows = [[ch.start[0], 0, ch.start[1], 'b']];
    let run = ch.start[1];
    for (const [l, v] of ch.steps) { rows.push([l, run, run + v, v >= 0 ? 'u' : 'd', v]); run += v; }
    rows.push([ch.end[0], 0, ch.end[1], 'b']);
    const LW = 220, RW = 92, x0 = LW, x1 = W - RW, rh = 20;
    const vals = rows.flatMap((r) => [r[1], r[2]]);
    const mx = Math.max(...vals), mn = Math.min(0, ...vals), span = mx - mn || 1;
    const X = (v) => x0 + ((v - mn) / span) * (x1 - x0);
    let y = 4, out = '';
    rows.forEach((r, k) => {
      const [l, a, b, t, v] = r;
      out += `<text x="4" y="${y + 13}" ${t === 'b' ? 'font-weight="700"' : ''}>${esc(short(l, 36))}<title>${esc(l)}</title></text>`;
      out += `<rect x="${Math.min(X(a), X(b))}" y="${y + 3}" width="${Math.max(1.5, Math.abs(X(b) - X(a)))}" height="13" rx="2" fill="${t === 'b' ? 'var(--nv-base)' : t === 'u' ? 'var(--nv-up)' : 'var(--nv-dn)'}"/>`;
      if (k < rows.length - 1) out += `<line x1="${X(b)}" x2="${X(b)}" y1="${y + 16}" y2="${y + rh + 3}" stroke="var(--muted,#999)" stroke-dasharray="2,2" opacity=".6"/>`;
      out += `<text x="${W - 4}" y="${y + 13}" text-anchor="end">${esc(t === 'b' ? money(b, unit) : unit === 'pure' ? pts(v) : (v >= 0 ? '+' : '') + money(v, unit))}</text>`;
      y += rh;
    });
    return `<svg viewBox="0 0 ${W} ${y + 4}" role="img">${out}</svg>`;
  }
  function vbars(series, unit) {
    const s = series[0], vals = s.values.map((x) => x[1]), mx = Math.max(...vals, 0) || 1;
    const n = vals.length, H = 150, bw = Math.min(70, (W - 40) / n - 10);
    let out = '';
    s.values.forEach(([l, v], k) => {
      const x = 20 + k * ((W - 40) / n) + ((W - 40) / n - bw) / 2, h = (Math.max(0, v) / mx) * (H - 40);
      out += `<rect x="${x}" y="${H - 22 - h}" width="${bw}" height="${h}" rx="2" fill="var(--nv-base)"/><text x="${x + bw / 2}" y="${H - 26 - h}" text-anchor="middle" font-size="10">${esc(money(v, unit))}</text>`;
      out += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" class="mut" font-size="10">${esc(short(String(l).replace(/^Fiscal (year )?/i, ''), 16))}<title>${esc(l)}</title></text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" role="img">${out}</svg>`;
  }
  function chartHTML(ch) {
    if (!ch) return '';
    let ttl = '', body = '';
    if (ch.type === 'waterfall') {
      ttl = (ch.rate ? 'Statutory → effective tax rate' : ch.bridge ? ch.title : (ch.title || 'Roll-forward') + ' — roll-forward') + (ch.member ? ` · ${ch.member}` : '') + ` · ${FY(ch.period)}`;
      body = waterfall(ch);
    } else if (ch.type === 'schedule') {
      ttl = `By year${ch.series[0].name && ch.series[0].name !== 'Total' ? ' · ' + ch.series[0].name : ''} (as of ${ch.period})`;
      body = vbars(ch.series, ch.unit);
    } else if (ch.type === 'composition') {
      ttl = `${ch.total} — parts, ${ch.periods.map(FY).join(' vs ')}`;
      body = hbars([...ch.parts.map(([l, v]) => ({ label: l, vals: v })), { label: ch.total, vals: ch.totals, bold: 1 }], ch.unit, { two: ch.periods.length > 1 });
    } else if (ch.type === 'members') {
      ttl = `${ch.row} by ${ch.axis}, ${ch.periods.map(FY).join(' vs ')}`;
      body = hbars(ch.members.map(([l, v, dep]) => ({ label: l, vals: v, depth: dep })).concat(fin(ch.total) ? [{ label: 'Total', vals: [ch.total], bold: 1 }] : []), ch.unit, { two: ch.periods.length > 1 });
    } else if (ch.type === 'figures') {
      ttl = 'Key figures';
      body = `<table>${ch.figures.map(([l, v, u, e]) => `<tr><td>${esc(l)}</td><td class="n">${esc(money(v, u))}</td><td class="n muted">${esc(e || '')}</td></tr>`).join('')}</table>`;
    }
    const legend = (ch.type === 'composition' || ch.type === 'members') && ch.periods && ch.periods.length > 1 ? `<div class="muted" style="font-size:.74rem">Dark: ${FY(ch.periods[0])} · light: ${FY(ch.periods[1])}</div>` : '';
    return `<div class="nv-chart"><div class="ttl">${esc(ttl)}</div>${body}${legend}</div>`;
  }

  /* ---------------- tables ---------------- */
  function tableHTML(T, opt) {
    opt = opt || {};
    const cols = T.cols.map((c, j) => ({ c, j })).slice(0, opt.maxCols || 8);
    const head = `<tr><th></th>${cols.map(({ c }) => `<th class="n">${esc(c.label ? c.label + ' · ' : '')}${esc(c.s ? FY(c.e) : c.e)}</th>`).join('')}${opt.lines ? '<th>Notes · ties</th>' : ''}</tr>`;
    const body = T.rows.map((r, i) => {
      const vals = T.cells[i] || [];
      if (r.abstract) return vals.some((v) => v != null) ? '' : `<tr class="nv-abs"><td style="padding-left:${6 + 12 * r.d}px" colspan="${cols.length + 1 + (opt.lines ? 1 : 0)}">${esc(r.label)}</td></tr>`;
      const ln = opt.lines ? opt.lines[i] : null;
      return `<tr class="${r.pref === 'total' ? 'nv-tot' : ''}" data-c="${esc(r.c || '')}"><td style="padding-left:${6 + 12 * r.d}px">${esc(r.label)}</td>${cols.map(({ j }) => `<td class="n">${esc(money(vals[j], r.u || 'USD'))}</td>`).join('')}${
        opt.lines ? `<td>${(ln.notes || []).map((n) => `<button class="nv-chip nv-n" data-nv-note="${n}">${esc(opt.noteLabel(n))}</button>`).join('')}${ln.checks && ln.checks.length ? ` <button class="nv-chip" data-nv-checks="${esc(ln.checks.join(','))}">${esc(opt.checkBadge(ln.checks))}</button>` : ''}</td>` : ''}</tr>`;
    }).join('');
    return `<div class="nv-wrap"><table>${head}${body}</table></div>`;
  }

  /* ---------------- checks ---------------- */
  function checkHTML(c, noteLabel) {
    const [ic, name, cls] = STATUS[c.status] || STATUS.gap;
    const u = c.u || 'USD';
    const f = (v) => (u === 'pure' ? (fin(v) ? (v * 100).toFixed(2) + '%' : '—') : /\//.test(u) ? (fin(v) ? '$' + (+v).toFixed(3) : '—') : money(v, u));
    const rows = c.parts.map(([l, v, s], k) => `<span>${k ? (s > 0 ? '+ ' : '− ') : (s < 0 ? '− ' : '')}${esc(l)}</span><span class="v">${esc(f(v))}</span>`).join('');
    return `<details class="nv-check" data-nv-check="${c.id}" ${c.status !== 'tie' ? 'open' : ''}><summary class="hd" style="cursor:pointer;list-style:none"><span class="st ${cls}" title="${esc(name)}">${ic}</span><b>${esc(c.title)}</b><span class="muted">${esc(f(c.result[1]))}${c.status !== 'tie' ? ' · Δ ' + esc(f(c.diff)) : ''} · ${esc(KINDS[c.kind] || c.kind)} · ${esc(c.period || '')}</span>${(c.notes || []).map((n) => `<button class="nv-chip nv-n" data-nv-note="${n}">${esc(noteLabel(n))}</button>`).join('')}</summary>
<div class="nv-formula">${rows}<span class="eq">= computed</span><span class="v eq">${esc(f(c.calc))}</span><span>${esc(c.result[0])} (filed)</span><span class="v">${esc(f(c.result[1]))}</span>${c.status !== 'tie' ? `<span class="${cls}">Difference</span><span class="v ${cls}">${esc(f(c.diff))}</span>` : ''}</div>
${c.explain ? `<p class="muted" style="margin:4px 0 0 26px;font-size:.8rem">${esc(c.explain)}</p>` : ''}</details>`;
  }

  /* ---------------- the linkage map ---------------- */
  function mapHTML(d, noteLabel) {
    const lines = [];
    for (const s of d.statements.slice().sort((a, b) => ST_ORDER.indexOf(a.kind) - ST_ORDER.indexOf(b.kind))) {
      if (!['is', 'bs', 'cf'].includes(s.kind)) continue;
      const got = s.table.rows.map((r, i) => ({ r, ln: s.lines[i] })).filter((x) => !x.r.abstract && x.ln.notes.length);
      const seen = new Set();
      const uniq = got.filter((x) => (seen.has(x.r.label) ? false : seen.add(x.r.label)));
      if (uniq.length) lines.push({ head: ST_NAME[s.kind] }, ...uniq.slice(0, 18).map((x) => ({ label: x.r.label, notes: x.ln.notes })));
    }
    const notes = d.notes.filter((n) => n.num != null || n.tables.length);
    if (!lines.length || !notes.length) return '';
    const rh = 17, H = Math.max(lines.length, notes.length * 1.6) * rh + 20;
    const ly = (k) => 14 + k * ((H - 24) / Math.max(1, lines.length - 1 || 1)), ny = (k) => 14 + k * ((H - 24) / Math.max(1, notes.length - 1));
    const npos = {};
    notes.forEach((n, k) => (npos[n.id] = ny(k)));
    let links = '', left = '', right = '';
    lines.forEach((l, k) => {
      const y = ly(k);
      if (l.head) { left += `<text x="4" y="${y + 4}" font-weight="700" class="mut">${esc(l.head)}</text>`; return; }
      left += `<g class="nd nv-ml" data-nv-line="${k}" data-notes="${l.notes.join(',')}"><text x="14" y="${y + 4}">${esc(short(l.label, 34))}<title>${esc(l.label)}</title></text></g>`;
      for (const n of l.notes) if (npos[n] != null) links += `<path class="lk" data-n="${n}" data-l="${k}" d="M232 ${y} C 330 ${y}, 330 ${npos[n]}, 408 ${npos[n]}"/>`;
    });
    notes.forEach((n) => {
      const y = npos[n.id];
      right += `<g class="nd nv-mn" data-nv-note="${n.id}" data-n="${n.id}"><rect x="408" y="${y - 9}" width="228" height="18" rx="9"/><text x="418" y="${y + 4}">${esc(short(n.num != null ? noteLabel(n.id) + ' ' + n.title : n.title, 36))}<title>${esc(n.title)}</title></text></g>`;
    });
    return `<div class="nv-card nv-map"><h3>Linkage map</h3><p class="muted">Each statement line on the left runs to the notes that explain it. Hover a line or a note to light up its links; click a note to open it.</p><svg viewBox="0 0 ${W} ${H}">${links}${left}${right}</svg></div>`;
  }

  /* ---------------- render ---------------- */
  function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', t = tk(opt && opt.ticker);
    if (!t) { el.innerHTML = '<p class="muted">No ticker for this company.</p>'; return; }
    el.innerHTML = '<p class="muted">Reading the notes of the latest 10-K…</p>';
    return load(t).then((d) => {
      if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
      draw(el, d, { hub, tab: (opt && opt.tab) || 'read', focus: opt && opt.note });
    }).catch((e) => {
      if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
      el.innerHTML = `<div class="nv"><div class="nv-card"><h3>Notes & ties · ${esc(t)}</h3><p class="muted">${esc(/not built/.test(e.message) ? `${t}'s 10-K notes are not built yet: the notes are read company by company, largest first, a batch every few hours.` : 'The notes could not load (' + e.message + ').')}</p></div></div>`;
    });
  }

  function draw(el, d, st) {
    const noteById = Object.fromEntries(d.notes.map((n) => [n.id, n]));
    const checkById = Object.fromEntries(d.checks.map((c) => [c.id, c]));
    const noteLabel = (id) => { const n = noteById[id]; return n ? (n.num != null ? 'Note ' + n.num : short(n.title, 18)) : id; };
    const checkBadge = (ids) => {
      const cs = ids.map((i) => checkById[i]).filter(Boolean);
      const worst = ['gap', 'info', 'round', 'tie'].find((s) => cs.some((c) => c.status === s)) || 'tie';
      return `${STATUS[worst][0]} ${cs.length} tie${cs.length > 1 ? 's' : ''}`;
    };
    const S = d.summary || {};
    const head = `<div class="nv-card"><h3>Notes & ties · ${esc(d.name || d.ticker)} <span class="muted">${esc(d.ticker)}</span></h3>
<p class="muted">${esc(d.form || '10-K')} for ${esc(d.fy || '')} (year ended ${esc(d.fy_end || '')}), filed ${esc(d.filed || '')} · <a href="${esc(d.url || '#')}" target="_blank" rel="noopener">the filing on EDGAR ↗</a></p>
<div class="nv-pills"><span class="nv-pill">${d.notes.length} notes</span><span class="nv-pill">${d.notes.reduce((a, n) => a + n.tables.length, 0)} detail tables</span><span class="nv-pill">${S.all || d.checks.length} checks</span><span class="nv-pill nv-ok">✓ ${S.tie || 0} tie</span>${S.round ? `<span class="nv-pill nv-round">≈ ${S.round} within rounding</span>` : ''}${S.info ? `<span class="nv-pill nv-info">Δ ${S.info} explained</span>` : ''}${S.gap ? `<span class="nv-pill nv-bad">✗ ${S.gap} do not tie</span>` : ''}</div>
<p class="muted" style="font-size:.8rem">Every number is the company's own XBRL. Each check recomputes a total, a roll-forward or a tie across statements and notes from those facts; ✓ means it agrees to the rounding the filing uses.</p></div>`;
    const seg = `<div class="nv-seg">${[['read', 'Read & map'], ['statements', 'Statements'], ['notes', 'Notes'], ['checks', 'Checks (勾稽)'], ['io', 'Inputs & outputs (投入产出)']].map(([k, l]) => `<button data-nv-tab="${k}" aria-pressed="${st.tab === k}">${l}</button>`).join('')}</div>`;
    el.innerHTML = `<div class="nv">${head}${seg}<div class="nv-pane"></div></div>`;
    const pane = el.querySelector('.nv-pane');

    function paneRead() {
      const R = d.read;
      let out = '';
      if (R) {
        out += `<div class="nv-card"><h3>The reading</h3>${R.summary.map((p) => `<p>${esc(p)}</p>`).join('')}<p class="muted" style="font-size:.78rem">${esc(R.by || '')}</p></div>`;
        out += `<div class="nv-card"><h3>Threads across the notes</h3><div class="nv-grid">${R.threads.map((th) => `<div class="nv-thread"><h4>${esc(th.title)}</h4><p style="font-size:.88rem">${esc(th.text)}</p><div>${(th.notes || []).map((n) => `<button class="nv-chip nv-n" data-nv-note="${n}">${esc(noteById[n] && noteById[n].num != null ? noteLabel(n) + ' ' + short(noteById[n].title, 26) : short(noteById[n] ? noteById[n].title : n, 34))}</button>`).join('')}${(th.statements || []).map((s) => `<span class="nv-pill" style="font-size:.72rem">${esc(ST_NAME[s] || s)}</span>`).join(' ')}</div></div>`).join('')}</div></div>`;
      } else {
        const an = d.notes.filter((n) => n.analysis.length).slice(0, 8);
        out += `<div class="nv-card"><h3>What changed</h3><ul class="nv-an">${an.map((n) => `<li><button class="nv-chip nv-n" data-nv-note="${n.id}">${esc(noteLabel(n.id))}</button> ${esc(n.analysis[0])}</li>`).join('')}</ul></div>`;
      }
      const odd = d.checks.filter((c) => c.status !== 'tie');
      if (odd.length) out += `<div class="nv-card"><h3>Ties that need a second look</h3>${odd.slice(0, 12).map((c) => checkHTML(c, noteLabel)).join('')}</div>`;
      out += mapHTML(d, noteLabel);
      return out;
    }
    function paneStatements() {
      const sts = d.statements.slice().sort((a, b) => ST_ORDER.indexOf(a.kind) - ST_ORDER.indexOf(b.kind));
      const cur = st.stmt && sts.find((s) => s.id === st.stmt) || sts[0];
      if (!cur) return '<p class="muted">No statements.</p>';
      return `<div class="nv-pills">${sts.map((s) => `<button class="nv-chip" data-nv-stmt="${s.id}" aria-pressed="${s.id === cur.id}">${esc(ST_NAME[s.kind] || s.title)}</button>`).join('')}</div>
<div class="nv-card"><h3>${esc(cur.title)}</h3>${tableHTML(cur.table, { lines: cur.lines, noteLabel, checkBadge, maxCols: cur.kind === 'eq' ? 3 : 3 })}<div class="nv-inline-checks"></div></div>`;
    }
    function noteHTML(n) {
      const R = d.read && d.read.notes && d.read.notes[n.id];
      const cs = n.checks.map((i) => checkById[i]).filter(Boolean);
      const cnt = (s) => cs.filter((c) => c.status === s).length;
      const badge = cs.length ? `<span class="nv-pill"><span class="nv-ok">✓ ${cnt('tie')}</span>${cnt('round') ? ` <span class="nv-round">≈ ${cnt('round')}</span>` : ''}${cnt('info') ? ` <span class="nv-info">Δ ${cnt('info')}</span>` : ''}${cnt('gap') ? ` <span class="nv-bad">✗ ${cnt('gap')}</span>` : ''}</span>` : '';
      return `<details class="nv-note" id="nv-${n.id}" data-nv-nid="${n.id}" ${st.focus === n.id ? 'open' : ''}><summary><span class="nv-num">${esc(n.num != null ? 'Note ' + n.num : '—')}</span><span class="nv-ttl">${esc(n.title)}</span><span class="muted">${n.tables.length} table${n.tables.length === 1 ? '' : 's'}</span>${badge}</summary><div class="nv-body" data-nv-body="${n.id}"></div></details>`;
    }
    function noteBody(n) {
      const R = d.read && d.read.notes && d.read.notes[n.id];
      const cs = n.checks.map((i) => checkById[i]).filter(Boolean);
      let out = '';
      if (R) out += `<div class="nv-read">${esc(R)}</div>`;
      if (n.analysis.length) out += `<ul class="nv-an">${n.analysis.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>`;
      const charts = n.tables.flatMap((t) => t.charts.filter((c) => c.type !== 'figures').map((c) => ({ c, t })));
      if (charts.length) out += `<div class="nv-grid">${charts.map((x) => chartHTML(x.c)).join('')}</div>`;
      if (n.tables.length) out += `<details><summary class="muted" style="cursor:pointer">The ${n.tables.length} table${n.tables.length > 1 ? 's' : ''} as filed</summary>${n.tables.map((t) => `<h4>${esc(t.title)}</h4>${t.charts.filter((c) => c.type === 'figures').map(chartHTML).join('')}${tableHTML(t.table, { maxCols: 10 })}`).join('')}</details>`;
      if (n.lines.length) out += `<div><b style="font-size:.84rem">Explains</b> ${n.lines.map(([sid, l]) => { const s = d.statements.find((x) => x.id === sid); return `<button class="nv-chip" data-nv-stmt-go="${sid}">${esc((s ? ST_NAME[s.kind] : '') + ': ' + short(l, 40))}</button>`; }).join('')}</div>`;
      if (cs.length) out += `<div><b style="font-size:.84rem">${cs.length} check${cs.length > 1 ? 's' : ''}</b> <span class="muted" style="font-size:.8rem">(click one for its arithmetic)</span>${cs.slice().sort((a, b) => (a.status === 'tie') - (b.status === 'tie')).map((c) => checkHTML(c, noteLabel)).join('')}</div>`;
      if (n.text && n.text.length) out += `<details><summary class="muted" style="cursor:pointer">The note's text${n.text_len > 2400 ? ' (the first part)' : ''}</summary><div class="nv-text">${n.text.map((p) => `<p>${esc(p)}</p>`).join('')}</div></details>`;
      if (n.policies && n.policies.length) out += `<p class="muted" style="font-size:.8rem">Policies: ${esc(n.policies.join(' · '))}</p>`;
      return out || '<p class="muted">Text only — no figures tagged in this note.</p>';
    }
    function paneNotes() { return d.notes.map(noteHTML).join(''); }
    function paneChecks() {
      const sc = st.scope || '', ss = st.status || '';
      const list = d.checks.filter((c) => (!sc || c.scope === sc) && (!ss || c.status === ss));
      const cnt = (f) => d.checks.filter(f).length;
      return `<div class="nv-card"><p class="muted">Every check is recomputed from the filing's facts for the latest year (ties and roll-forwards for the year before too). ✓ agrees within the rounding of the figures · ≈ within three times that · Δ a difference the two figures are allowed to have, with the usual reasons · ✗ does not tie.${(d.summary || {}).all > d.checks.length ? ` Listed: ${d.checks.length} of the ${(d.summary || {}).all} checks — every one that does not tie and every tie across statements and notes; the rest of the company's own sums and splits all tie and are counted above.` : ''}</p>
<div class="nv-pills">${SCOPES.map(([k, l]) => `<button class="nv-chip" data-nv-scope="${k}" aria-pressed="${sc === k}">${esc(l)} (${cnt((c) => !k || c.scope === k)})</button>`).join('')}</div>
<div class="nv-pills">${[['', 'Any result'], ['tie', '✓ Ties'], ['round', '≈ Rounding'], ['info', 'Δ Explained'], ['gap', '✗ Does not tie']].map(([k, l]) => `<button class="nv-chip" data-nv-status="${k}" aria-pressed="${ss === k}">${esc(l)} (${cnt((c) => (!sc || c.scope === sc) && (!k || c.status === k))})</button>`).join('')}</div>
${list.slice(0, 400).map((c) => checkHTML(c, noteLabel)).join('') || '<p class="muted">None.</p>'}</div>`;
    }
    function show() {
      el.querySelectorAll('[data-nv-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.nvTab === st.tab)));
      pane.innerHTML = st.tab === 'statements' ? paneStatements() : st.tab === 'notes' ? paneNotes() : st.tab === 'checks' ? paneChecks() : st.tab === 'io' ? ioHTML(d.io, noteLabel) : paneRead();
      if (st.tab === 'notes') {
        pane.querySelectorAll('details.nv-note').forEach((det) => {
          const fill = () => { const b = det.querySelector('[data-nv-body]'); if (b && !b.dataset.done) { b.dataset.done = 1; b.innerHTML = noteBody(noteById[det.dataset.nvNid]); } };
          if (det.open) fill();
          det.addEventListener('toggle', () => det.open && fill());
        });
        if (st.focus) { const t = el.querySelector('#nv-' + st.focus); if (t) { t.open = true; t.scrollIntoView({ behavior: 'smooth', block: 'start' }); t.classList.add('nv-flash'); } st.focus = null; }
      }
      const map = pane.querySelector('.nv-map svg');
      if (map) {
        const on = (sel, v) => map.querySelectorAll(sel).forEach((x) => x.classList.toggle('on', v));
        map.addEventListener('mouseover', (e) => {
          const g = e.target.closest('.nd'); map.querySelectorAll('.on').forEach((x) => x.classList.remove('on'));
          if (!g) return;
          if (g.dataset.n) { on(`path[data-n="${g.dataset.n}"]`, true); g.classList.add('on'); }
          if (g.dataset.nvLine != null) { on(`path[data-l="${g.dataset.nvLine}"]`, true); (g.dataset.notes || '').split(',').forEach((n) => { const r = map.querySelector(`.nv-mn[data-n="${n}"]`); if (r) r.classList.add('on'); }); }
        });
      }
    }
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button, .nd');
      if (!b || !el.contains(b)) return;
      if (b.dataset.nvTab) { st.tab = b.dataset.nvTab; show(); return; }
      if (b.dataset.nvNote) { st.tab = 'notes'; st.focus = b.dataset.nvNote; show(); return; }
      if (b.dataset.nvStmt) { st.stmt = b.dataset.nvStmt; show(); return; }
      if (b.dataset.nvStmtGo) { st.tab = 'statements'; st.stmt = b.dataset.nvStmtGo; show(); return; }
      if (b.dataset.nvScope != null) { st.scope = b.dataset.nvScope; show(); return; }
      if (b.dataset.nvStatus != null) { st.status = b.dataset.nvStatus; show(); return; }
      if (b.dataset.nvChecks) {
        const box = b.closest('.nv-card').querySelector('.nv-inline-checks');
        if (box) { box.innerHTML = `<h4>Ties for this line</h4>` + b.dataset.nvChecks.split(',').map((i) => checkById[i]).filter(Boolean).map((c) => checkHTML(c, noteLabel)).join(''); box.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      }
    });
    show();
  }


  /* ---------------- the input-output account (io_table.py) ---------------- */
  const IO_COL = { out: 'var(--mk-rev,#7a7974)', goods: 'var(--mk-cost,#ea6a52)', resale: 'var(--mk-cost,#ea6a52)', services: '#f0a28f', other: '#f0a28f', all: 'var(--mk-cost,#ea6a52)',
    fin: '#c98b6b', comp: 'var(--slate,#5b7fa6)', taxp: 'var(--warn-ink,#8a4b00)', da: 'var(--mk-noncash,#5b7fa6)', interest: '#9a8fb8', inctax: '#c9a227',
    ni: 'var(--mk-profit,#17734a)', impair: '#b9b4cf', dinv: '#8fc7a9', gos_rest: 'var(--line,#ccc)', gains: '#8fc7a9' };
  function sankey3(left, mid, right) {
    const SW = 860, LAB = 15, H = Math.max(300, (LAB + 4) * Math.max(left.length, right.length) + 60), T = 22, B = 12, gap = 4;
    const tot = Math.max(left.reduce((a, n) => a + n.v, 0), right.reduce((a, n) => a + n.v, 0)) || 1;
    const avail = (n) => H - T - B - (gap + LAB) * Math.max(0, n);
    const k = Math.max(0.1, Math.min(avail(left.length), avail(right.length))) / tot;
    const xl = 200, xm = 400, xr = 560, bw = 12;
    // each node at least a label's height apart, so small ones stay readable
    const place = (nodes) => { let y = T; return nodes.map((n) => { const h = Math.max(1.5, n.v * k), o = { ...n, y, h }; y += Math.max(h, LAB) + gap; return o; }); };
    const L = place(left), R = place(right), mh = tot * k, my = T + (H - T - B - mh) / 2;
    const rib = (x0, y0, h0, x1, y1, col) => { const c = (x0 + x1) / 2; return `<path d="M${x0},${y0}C${c},${y0} ${c},${y1} ${x1},${y1}L${x1},${y1 + h0}C${c},${y1 + h0} ${c},${y0 + h0} ${x0},${y0 + h0}Z" fill="${col}" opacity=".32"/>`; };
    let g = '', ym = my;
    for (const n of L) { g += rib(xl + bw, n.y, n.h, xm, ym, n.col); ym += n.h; }
    ym = my;
    for (const n of R) { g += rib(xm + bw, ym, n.h, xr, n.y, n.col); ym += n.h; }
    for (const n of L) g += `<rect x="${xl}" y="${n.y.toFixed(1)}" width="${bw}" height="${n.h.toFixed(1)}" fill="${n.col}"/><text x="${xl - 6}" y="${(n.y + Math.max(n.h, 11) / 2 + 4).toFixed(1)}" text-anchor="end" font-size="11">${esc(short(n.label, 26))} <tspan class="mut">${esc(money(n.v))}</tspan><title>${esc(n.label)}</title></text>`;
    g += `<rect x="${xm}" y="${my.toFixed(1)}" width="${bw}" height="${mh.toFixed(1)}" fill="var(--ink,#333)"/><text x="${xm + bw / 2}" y="${(my - 4).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700">${esc(mid)}</text>`;
    for (const n of R) g += `<rect x="${xr}" y="${n.y.toFixed(1)}" width="${bw}" height="${n.h.toFixed(1)}" fill="${n.col}"/><text x="${xr + bw + 6}" y="${(n.y + Math.max(n.h, 11) / 2 + 4).toFixed(1)}" font-size="11">${esc(short(n.label, 34))} <tspan class="mut">${esc(money(n.v))} · ${(n.v / tot * 100).toFixed(n.v / tot < 0.1 ? 1 : 0)}%</tspan><title>${esc(n.label)}</title></text>`;
    const used = Math.max(my + mh, ...L.map((n) => n.y + Math.max(n.h, LAB)), ...R.map((n) => n.y + Math.max(n.h, LAB))) + B;
    return `<div style="overflow-x:auto"><svg viewBox="0 0 ${SW} ${Math.ceil(used)}" style="min-width:640px" role="img" aria-label="Where the output came from and where it went">${g}</svg></div>`;
  }
  function ioHTML(io, noteLabel) {
    if (!io) return '<div class="nv-card"><p class="muted">No input-output account for this filing (no revenue or operating income tagged).</p></div>';
    if (io.error) return `<div class="nv-card"><p class="muted">The input-output account could not be built (${esc(io.error)}).</p></div>`;
    const Lk = {}; io.lines.forEach((l) => { Lk[l.k + (l.g === 'gos' && l.k === 'dinv' ? '_kept' : '')] = l; });
    const v = (k) => (Lk[k] ? Lk[k].v : 0), R = io.ratios || {}, pct = (x, d) => (fin(x) ? (x * 100).toFixed(d == null ? 0 : d) + '%' : '—');
    const out = v('output') || v('revenue');
    let h = `<div class="nv-card"><h3>Inputs & outputs · ${esc(io.fy)}</h3><p class="muted" style="font-size:.84rem">The company as one producer in an input-output table: what it produced and for whom, what it bought and from which industries, and how the value it added was paid to its factors — employees, capital, the state, lenders and owners. Lines from the 10-K link to their note; purchases by supplying industry are estimates from BEA's input-output table for its industry${io.industry && io.industry.length ? ' (' + io.industry.map((x) => esc(x[1])).join('; ') + ')' : ''}.</p>
<div class="nv-pills"><span class="nv-pill">Gross output ${esc(money(out))}</span><span class="nv-pill">Value added ${esc(money(v('va')))} · ${pct(R.va_share)} of output</span><span class="nv-pill">Purchases ${pct(R.inter_share)} of output</span><span class="nv-pill">Employees' share of value added ${pct(R.labor_share)}</span><span class="nv-pill">Capital's share ${pct(R.capital_share)}</span>${io.labor ? `<span class="nv-pill">${Number(io.labor.employees).toLocaleString('en-US')} employees · ${esc(money(io.labor.va_per))} value added each</span>` : ''}</div></div>`;
    // the flow: sources → output → uses
    const sp = io.splits || {}, src = sp.segment || sp.product || sp.region;
    let left = src && src.length ? src.map(([l, x]) => ({ label: l, v: x, col: IO_COL.out })) : [{ label: 'Revenue', v: v('revenue'), col: IO_COL.out }];
    const ssum = left.reduce((a, n) => a + n.v, 0);
    if (src && v('revenue') - ssum > 0.01 * v('revenue')) left.push({ label: 'Other / eliminations', v: v('revenue') - ssum, col: IO_COL.out });
    if (src && ssum > v('revenue') * 1.001) { const f = v('revenue') / ssum; left = left.map((n) => ({ ...n, v: n.v * f })); }
    if (Lk.dinv && Lk.dinv.v > 0) left.push({ label: 'Inventory build', v: Lk.dinv.v, col: IO_COL.dinv });
    const rest = Lk.gos_rest ? Lk.gos_rest.v : 0;
    if (rest < 0) left.push({ label: 'Non-operating gains', v: -rest, col: IO_COL.gains });
    const right = [];
    (io.inputs && io.inputs.length ? io.inputs : [{ k: 'all', name: 'Purchased goods and services', v: v('inter') }]).forEach((gp) => { if (gp.v > 0) right.push({ label: gp.name, v: gp.v, col: IO_COL[gp.k] || IO_COL.all }); });
    [['finc', io.fin_label || 'Financial inputs'], ['comp', 'Employees (pay)'], ['taxp', 'Taxes on production'], ['da', 'Depreciation & amortization'], ['impair', 'Write-downs'], ['interest', 'Interest to lenders'], ['inctax', 'Income tax'], ['ni', 'Net income'], ['dinv_kept', 'Kept as inventory'], ['gos_rest', 'Other non-operating costs']]
      .forEach(([k, l]) => { const x = Lk[k]; if (x && x.v > 0) right.push({ label: l, v: x.v, col: IO_COL[k.replace('_kept', '')] || IO_COL.gos_rest }); });
    const gapLR = right.reduce((a, n) => a + n.v, 0) - left.reduce((a, n) => a + n.v, 0);
    if (gapLR > 0.005 * out) left.push({ label: 'Loss: spent beyond output', v: gapLR, col: 'var(--neg,#b4432f)' });
    h += `<div class="nv-card"><h3>From output to the factors</h3>${sankey3(left, 'Gross output', right)}<p class="muted" style="font-size:.78rem">Left: revenue by ${sp.segment ? 'segment' : sp.product ? 'product or service' : sp.region ? 'region' : 'its total'} (the revenue note)${rest < 0 ? ', and non-operating gains that added to net income' : ''}. Right: purchases, then value added — employees, taxes on production, and the operating surplus to capital (depreciation), lenders, the state and owners.</p></div>`;
    // the account
    const chip = (l) => (l.notes || []).map((n) => `<button class="nv-chip nv-n" style="white-space:nowrap" data-nv-note="${n}">${esc(noteLabel(n))}</button>`).join(' ');
    const tag = (l) => (l.src === '10-K' ? '<span class="nv-pill nv-ok" style="font-size:.72rem">10-K</span>' : l.src === 'estimate' ? '<span class="nv-pill nv-info" style="font-size:.72rem">estimate</span>' : '<span class="nv-pill" style="font-size:.72rem">derived</span>');
    const GN = { output: 'Output', inter: 'Inputs bought', fin: 'Financial inputs', va: 'Value added (primary inputs)', gos: 'Operating surplus: who received it' };
    let rows = '', grp = '';
    for (const l of io.lines) {
      if (l.g !== grp) { grp = l.g; rows += `<tr><td colspan="6" style="font-weight:700;background:var(--bg,#f6f5f1)">${esc(GN[grp] || grp)}</td></tr>`; }
      const bold = ['output', 'va', 'gos', 'inter'].includes(l.k);
      rows += `<tr><td style="padding-left:${bold ? 6 : 16}px;${bold ? 'font-weight:600' : ''}">${esc(l.label)}${l.note ? `<br><span class="mut" style="font-size:.76rem">${esc(l.note)}</span>` : ''}</td><td class="n">${esc(money(l.v))}</td><td class="n mut">${esc(money(l.v0))}</td><td class="n">${fin(l.pct) ? (l.pct * 100).toFixed(1) + '%' : ''}</td><td>${tag(l)}</td><td>${chip(l)}</td></tr>`;
    }
    h += `<div class="nv-card"><h3>The account</h3><div class="nv-wrap"><table><tr><th></th><th class="n">${esc(io.fy)}</th><th class="n">${esc(io.fy_prev || 'Year before')}</th><th class="n">% of output</th><th>From</th><th>Note</th></tr>${rows}</table></div>
<p class="muted" style="font-size:.78rem">Purchases = operating spending (revenue less operating income and depreciation) less pay and taxes on production; value added = output less purchases${io.financial ? ' and financial inputs' : ''} = pay + taxes on production + operating surplus. ${io.comp_how === 'disclosed' ? 'Pay is as the 10-K states it.' : io.comp_how === 'headcount' ? 'Pay is estimated from the 10-K\'s headcount and its industry\'s average pay per employee (BEA), plus stock-based pay.' : 'Pay is estimated at its industry\'s share of operating spending (BEA): the 10-K gives neither pay nor a headcount the site could read.'}${(io.notes || []).length ? ' ' + io.notes.map(esc).join(' ') : ''}</p></div>`;
    // inputs by supplying industry
    if (io.inputs && io.inputs.length) {
      h += `<div class="nv-card"><h3>Inputs by supplying industry <span class="muted" style="font-weight:400">· estimated</span></h3>`;
      for (const gp of io.inputs) {
        h += `<h4 style="margin:10px 0 2px">${esc(gp.name)} · ${esc(money(gp.v))}</h4>${gp.note ? `<p class="mut" style="font-size:.78rem;margin:0 0 4px">${esc(gp.note)}</p>` : ''}`;
        const r = (gp.suppliers || []).map(([n, x]) => ({ label: n, vals: [x] }));
        if (gp.imports) r.push({ label: 'Imports', vals: [gp.imports], bold: true });
        if (r.length) h += hbars(r, 'USD');
      }
      h += `<p class="muted" style="font-size:.78rem">Each group spread over the industries its industry buys from in BEA's input-output table (2017 detail, the Use and Make tables; the imported share of each commodity goes to imports). The table describes US establishments of its industry: a company that has its products made abroad buys more from abroad than this shows.</p></div>`;
    }
    // output in detail
    const sec = [['segment', 'By segment'], ['product', 'By product or service'], ['region', 'By region']].filter(([k]) => (sp[k] || []).length);
    if (sec.length || (io.customers || []).length) {
      h += `<div class="nv-card"><h3>Output: what and for whom</h3>`;
      for (const [k, t] of sec) h += `<h4 style="margin:8px 0 2px">${t}</h4>` + hbars(sp[k].map(([l, x]) => ({ label: l, vals: [x] })), 'USD');
      if ((io.customers || []).length) h += `<h4 style="margin:8px 0 2px">Customers named in the concentration note</h4>` + hbars(io.customers.map(([l, x]) => ({ label: l, vals: [x] })), 'pure');
      h += '</div>';
    }
    // capital and labour
    const cap = (io.capital || []).map((l) => `<tr><td>${esc(l.label)}</td><td class="n">${esc(money(l.v))}</td><td class="n mut">${esc(money(l.v0))}</td><td>${chip(l)}</td></tr>`).join('');
    const ratio = [['Purchases ÷ output', pct(R.inter_share)], ['Value added ÷ output', pct(R.va_share)], ["Employees' share of value added", pct(R.labor_share)], ["Capital's share (operating surplus ÷ value added)", pct(R.capital_share)],
      ['Taxes (production and income) ÷ value added', pct(R.tax_share)], ['Depreciation ÷ value added', pct(R.da_share)], ['Property, plant and equipment ÷ revenue', fin(R.capital_output) ? R.capital_output.toFixed(2) + '×' : '—'],
      ['Capital spending ÷ depreciation', fin(R.capex_to_da) ? R.capex_to_da.toFixed(2) + '×' : '—'], ['R&D ÷ revenue', pct(R.rnd_intensity, 1)], ['Import content of purchases and investment (estimated)', pct(R.import_content)]];
    if (io.labor) ratio.push(['Employees (the 10-K)', Number(io.labor.employees).toLocaleString('en-US')], ['Revenue per employee', money(io.labor.revenue_per)], ['Value added per employee', money(io.labor.va_per)], ['Pay per employee', money(io.labor.pay_per)], ['Property, plant and equipment per employee', money(io.labor.ppe_per)]);
    h += `<div class="nv-grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))"><div class="nv-card"><h3>Capital</h3>${cap ? `<div class="nv-wrap"><table><tr><th></th><th class="n">${esc(io.fy)}</th><th class="n">${esc(io.fy_prev || '')}</th><th>Note</th></tr>${cap}</table></div>` : '<p class="muted">No capital figures tagged.</p>'}
${(io.capex_suppliers || []).length ? `<h4 style="margin:10px 0 2px">Capital spending by supplying industry <span class="mut" style="font-weight:400">· estimated (BEA fixed assets)</span></h4>` + hbars([...io.capex_suppliers.map(([n, x]) => ({ label: n, vals: [x] })), ...(io.capex_imports ? [{ label: 'Imports', vals: [io.capex_imports], bold: true }] : [])], 'USD') : ''}</div>
<div class="nv-card"><h3>Factor ratios</h3><div class="nv-wrap"><table>${ratio.map(([a, b]) => `<tr><td>${esc(a)}</td><td class="n">${esc(b)}</td></tr>`).join('')}</table></div></div></div>`;
    return h;
  }

  const api = { render, _draw: draw, _money: money, _chart: chartHTML, _io: ioHTML };
  if (typeof window !== 'undefined') window.NotesView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
