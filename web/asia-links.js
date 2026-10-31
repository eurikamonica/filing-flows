/* Customers and suppliers named in annual reports of companies listed in Japan, Taiwan, Korea and Hong Kong
   (disclosures/app/asia.py → disclosures/data/research/asia/c/<cik>.json), on the company page's
   "Customers, suppliers & model" view: FFAsia.company(section, cik, name). */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  function usd(v) {
    if (!fin(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e12) return '$' + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B';
    if (a >= 1e6) return '$' + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M';
    return '$' + Math.round(a / 1e3) + 'K';
  }
  const SYM = { JPY: '¥', KRW: '₩', TWD: 'NT$', HKD: 'HK$', CNY: 'RMB ', RMB: 'RMB ', USD: '$' };
  function local(v, cur) {
    if (!fin(v)) return '';
    const a = Math.abs(v), s = SYM[cur] || cur + ' ';
    if (a >= 1e12) return s + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + (a / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return s + (a / 1e6).toFixed(0) + 'M';
    return s + Math.round(a).toLocaleString('en-US');
  }
  const FLAG = { jp: '🇯🇵 Japan', kr: '🇰🇷 Korea', tw: '🇹🇼 Taiwan', hk: '🇭🇰 Hong Kong' };
  const pct = (v) => (fin(v) ? (100 * v).toFixed(v < 0.1 ? 1 : 0) + '%' : '—');

  function table(rows, role, who) {
    const max = Math.max(...rows.map((r) => r.usd || 0), 1);
    return `<div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Listed in</th><th class="num">${role === 'suppliers' ? `Share of its sales to ${esc(who)}` : `Share of its purchases from ${esc(who)}`}</th><th class="num">Amount a year</th><th style="width:18%"></th><th>Year</th><th>As written</th></tr></thead><tbody>${
      rows.map((r) => {
        const nm = r.name_en || r.name;
        const link = r.self && r.self.cik ? `<a href="${global.FF_BASE || ''}#c-${esc(r.self.cik)}"><b>${esc(nm)}</b></a>` : `<b>${esc(nm)}</b>`;
        const amt = fin(r.usd) ? `${usd(r.usd)}${r.computed ? '*' : ''}<br><span class="muted small">${esc(local(r.amount, r.currency))}</span>` : '—';
        return `<tr><td>${link}${r.name_en && r.name && r.name !== r.name_en ? `<br><span class="muted small">${esc(r.name)}</span>` : ''}</td><td>${esc(FLAG[r.mk] || r.mk)}</td>` +
          `<td class="num">${pct(r.share)}</td><td class="num">${amt}</td><td>${fin(r.usd) ? `<div style="height:8px;border-radius:4px;background:#5d7fa3;width:${Math.max(2, 100 * r.usd / max).toFixed(1)}%"></div>` : ''}</td>` +
          `<td>${esc(String(r.year || r.fy || '').slice(0, 10))}</td><td class="small">“${esc(String(r.label || ''))}”${r.q && r.q !== r.label ? ` — <span class="muted">${esc(String(r.q).slice(0, 160))}</span>` : ''}${r.url ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener">report</a>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  }

  async function company(box, cik, name) {
    if (!box) return;
    let d = null;
    try {
      const r = await fetch(`${global.FF_BASE || ''}disclosures/data/research/asia/c/${parseInt(cik, 10)}.json`, { cache: 'no-cache' });
      d = r.ok ? await r.json() : null;
    } catch (e) { d = null; }
    if (!d || !((d.suppliers || []).length || (d.customers || []).length)) return;
    const who = name || 'this company';
    const S = d.suppliers || [], C = d.customers || [];
    const tot = S.reduce((a, r) => a + (r.usd || 0), 0);
    box.innerHTML = `<div class="section-head"><h2>Named in Asian annual reports</h2><span class="muted">Companies listed in Japan, Taiwan, Korea and Hong Kong that name ${esc(who)}</span></div>` +
      (S.length ? `<p>${S.length} ${S.length === 1 ? 'company names' : 'companies name'} ${esc(who)} as a major customer${tot ? ` — at least <b>${usd(tot)}</b> a year of their sales, as they report it` : ''}. These are ${esc(who)}’s suppliers, seen from their side.</p>${table(S, 'suppliers', who)}` : '') +
      (C.length ? `<h3>Named as a supplier</h3><p>${C.length} ${C.length === 1 ? 'company names' : 'companies name'} ${esc(who)} as a major supplier.</p>${table(C, 'customers', who)}` : '') +
      `<p class="muted small">From each company’s own annual report: Japan 有価証券報告書 (主要な販売先, customers above 10% of sales), Korea 사업보고서 (주요 매출처), Taiwan 年報 (主要進銷貨客戶), Hong Kong annual reports (major customers and suppliers). Names are matched to US-listed companies by their names in English, Japanese, Chinese and Korean. * amount computed as the stated share × the company’s revenue. ${esc(d.fx_note || '')}</p>`;
    box.hidden = false;
  }

  global.FFAsia = { company };
})(window);
