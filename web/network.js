/* Customers and suppliers as stated in annual reports (pipeline/custnet.py → data/network/c/<cik>.json): on a company
 * page, a money-flow chart — the listed suppliers that name the company as a customer → the company → the customers it
 * names, the share of revenue each is stated to be, and the rest — and the sentences each link was read from. */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const usd = (v) => {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v);
    if (a >= 0.95e12) return `$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `$${(a / 1e9).toFixed(a >= 100e9 ? 0 : 1)}B`;
    if (a >= 0.95e6) return `$${(a / 1e6).toFixed(a >= 100e6 ? 0 : 1)}M`;
    return `$${(a / 1e3).toFixed(0)}K`;
  };
  const upct = (x) => (x == null || isNaN(x) ? '—' : `${(100 * x).toFixed(x < 0.1 ? 1 : 0)}%`);
  const cache = new Map();
  function get(path) {
    if (!cache.has(path)) cache.set(path, fetch((global.FF_DATA || 'data/') + path).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return cache.get(path);
  }
  const SUP = '#2f6db0', CUS = '#1f8a5b', ME = '#44505a', REST = '#9a9893';
  const nameOf = (x) => x.t || x.name || x.label || 'Unnamed customer';
  const shortName = (x) => (x.t ? x.t : (x.name || x.label || '').replace(/,?\s+(Inc|Corp|Corporation|Co|Ltd|plc|LLC|Limited|Holdings)\.?$/i, '')) || 'Unnamed customer';

  function view(d) {
    const me = d.me, rev = d.revenue || 0;
    const sup = (d.suppliers || []).filter((s) => s.usd > 0 && s.by === 'other').slice(0, 14);
    const cus = (d.customers || []).filter((c) => c.usd > 0).slice(0, 14);
    const nodes = [], links = [];
    const meId = 'me';
    sup.forEach((s, i) => {
      nodes.push({ id: 's' + i, col: 0, label: shortName(s), v: s.usd, color: SUP, sub: s.name, cik: s.cik, t: s.t });
      links.push({ s: 's' + i, t: meId, v: s.usd, k: 1, why: `${nameOf(s)}'s ${s.form || 'annual report'}: ${upct(s.pct)} of its revenue` });
    });
    let named = 0;
    cus.forEach((c, i) => {
      named += c.usd;
      nodes.push({ id: 'c' + i, col: sup.length ? 2 : 1, label: c.label ? shortName(c) : `Unnamed customer`, v: c.usd, color: CUS, sub: c.name, cik: c.cik, t: c.t });
      links.push({ s: meId, t: 'c' + i, v: c.usd, k: 1, why: `${upct(c.pct)} of revenue (${c.how})` });
    });
    const rest = Math.max(rev - named, 0);
    if (cus.length && rest > 0) {
      nodes.push({ id: 'rest', col: sup.length ? 2 : 1, label: 'Other customers', v: rest, color: REST, est: true });
      links.push({ s: meId, t: 'rest', v: rest, k: 0, why: 'revenue not attributed to a named customer' });
    }
    const bought = sup.reduce((a, s) => a + s.usd, 0);
    // with customers the company's bar is its revenue; with suppliers only, what it buys from them (a $400B bar
    // would make the bands invisible)
    nodes.push({ id: meId, col: sup.length ? 1 : 0, label: me.t || me.name, v: cus.length ? Math.max(rev, bought, named) : bought,
      color: ME, t: me.t, sub: me.name });
    const cols = sup.length ? [{ id: 's', name: 'Suppliers' }, { id: 'm', name: cus.length ? 'Revenue' : 'Bought' }].concat(cus.length ? [{ id: 'c', name: 'Customers' }] : [])
      : [{ id: 'm', name: 'Revenue' }, { id: 'c', name: 'Customers' }];
    return (sup.length || cus.length) ? { cols, nodes, links } : null;
  }

  function rowsTable(rows, side, me) {
    if (!rows.length) return '';
    return `<div class="tbl-wrap"><table class="small net-tbl"><thead><tr><th>${side === 'c' ? 'Customer' : 'Supplier'}</th><th class="num">Share</th><th class="num">Dollars</th><th>Stated in</th></tr></thead><tbody>
      ${rows.map((r) => {
        const who = r.label || r.name ? (r.cik && !(r.t == null && r.name == null) ? `<a href="#c-${r.cik}"><b>${esc(r.t || r.name)}</b></a> <span class="muted">${esc(r.name && r.t ? r.name : '')}</span>` : `<b>${esc(r.label || r.name)}</b>`) : '<span class="muted">Unnamed customer</span>';
        const share = r.share_of_revenue != null ? `${upct(r.share_of_revenue)} <span class="muted">of ${esc(me)}’s revenue from its products</span>` :
          r.min ? '<span class="muted">10% or more of revenue</span>' : r.pct != null ? `${upct(r.pct)} <span class="muted">of ${side === 'c' || r.by === 'other' ? (r.by === 'other' ? 'its' : '') + ' revenue' : 'purchases'}</span>` : r.combined ? `<span class="muted">${upct(r.combined)} together with others</span>` : '<span class="muted">not stated</span>';
        const src = r.by === 'other' ? `${esc(r.t || r.name || r.label)}’s ${esc(r.form || 'annual report')}` : `${esc(me)}’s ${esc(r.form || 'annual report')}`;
        const link = r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${src} ↗</a>` : src;
        return `<tr><td>${who}${r.seg ? ` <span class="muted">· ${esc(r.seg)}${r.seg && !r.usd && r.pct != null ? ' (share of that unit)' : ''}</span>` : ''}</td><td class="num">${share}</td><td class="num">${r.usd ? usd(r.usd) : '—'}</td>
          <td>${link} <span class="muted">${esc((r.fy || '').slice(0, 4))}${r.how ? ' · ' + esc(r.how) : ''}</span>${r.q ? `<details class="net-q"><summary>the sentence</summary><q>${esc(r.q)}</q></details>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  }

  async function company(box, cik) {
    const d = await get(`network/c/${cik}.json`);
    if (!d || !box || !box.isConnected) return;
    const me = d.me.t || d.me.name;
    const cus = d.customers || [];
    const supOther = (d.suppliers || []).filter((s) => s.by === 'other');
    const supSelf = (d.suppliers || []).filter((s) => s.by === 'self');
    const v = view(d);
    box.innerHTML = `<div class="section-head"><h2>Customers &amp; suppliers</h2><span class="muted">As stated in annual reports — its own and its suppliers’</span></div>
      ${v ? '<div class="net-chart" id="net-chart"></div>' : ''}
      ${cus.length ? `<h3>Customers ${esc(me)} names</h3>${rowsTable(cus, 'c', me)}` : ''}
      ${supOther.length ? `<h3>Companies that name ${esc(me)} as a customer</h3>${rowsTable(supOther, 's', me)}` : ''}
      ${supSelf.length ? `<h3>Suppliers ${esc(me)} names</h3>${rowsTable(supSelf, 's', me)}` : ''}
      <p class="muted small">A link is drawn only where a filing names the company and, for dollars, states its share: dollars = that share × the reporting company’s revenue for the year. Companies disclose customers above about 10% of revenue, so most relationships are not here; a missing link is not evidence of none. Read automatically; check the filing before relying on it.</p>`;
    box.hidden = false;
    if (v && global.FFChains && global.Sankey) {
      const scene = global.FFChains.layout(v, {
        title: `${me} — who pays whom`,
        subtitle: [`Fiscal ${(d.fy || '').slice(0, 4)} revenue ${usd(d.revenue)}`, cus.some((c) => c.usd) ? `${cus.filter((c) => c.usd).length} customers with a stated share` : '', supOther.some((s) => s.usd) ? `${supOther.filter((s) => s.usd).length} listed suppliers name it as a customer (their sales to it)` : ''].filter(Boolean).join(' · '),
        footer: ['Source: SEC EDGAR annual reports (10-K, 20-F), read by fixed rules. Dark bands: shares stated in the filings × revenue; grey: the rest of revenue.',
          'Figures are read automatically and can contain errors; check the filings before relying on them. Not investment advice.'],
      });
      document.getElementById('net-chart').innerHTML = global.Sankey.toSVG(scene, `${me}: customers and suppliers`);
    }
  }

  // ---------------------------------------------------------------- a chain or theme as a basket
  function conceptView(d) {
    const key = (x) => (x.cik ? 'k' + x.cik : 'n' + String(x.name || 'unnamed').toLowerCase());
    const mem = new Map(d.members.filter((m) => m.linked).map((m) => ['k' + m.cik, m]));
    const nodes = new Map(), links = [];
    const add = (id, col, x, color, extra) => { if (!nodes.has(id)) nodes.set(id, { id, col, label: x.t || x.name || 'Unnamed customer', v: 0, color, cik: x.cik, t: x.t, sub: x.name, ...extra }); return nodes.get(id); };
    let named = new Map();
    d.links.forEach((l) => {
      if (l.kind === 'in') {
        const a = add('s:' + key(l.s), 0, l.s, SUP), b = add('m:' + key(l.c), 1, l.c, ME);
        a.v += l.usd; links.push({ s: a.id, t: b.id, v: l.usd, k: 1, why: `${l.s.t || l.s.name}: ${upct(l.pct)} of its revenue` });
      } else {
        const a = add('m:' + key(l.s), 1, l.s, ME), b = add('c:' + key(l.c), 2, l.c, l.kind === 'inside' ? '#7a5aa6' : CUS, l.kind === 'inside' ? { label: `${l.c.t || l.c.name} (member)` } : {});
        b.v += l.usd; links.push({ s: a.id, t: b.id, v: l.usd, k: 1, why: `${upct(l.pct)} of ${l.s.t || l.s.name}'s revenue` });
        named.set(a.id, (named.get(a.id) || 0) + l.usd);
      }
    });
    let rest = 0;
    nodes.forEach((n) => {
      if (n.col !== 1) return;
      const m = mem.get(n.id.slice(2)) || {};
      const inV = links.filter((l) => l.t === n.id).reduce((a, l) => a + l.v, 0), outV = named.get(n.id) || 0;
      n.v = outV ? Math.max(m.revenue || 0, outV, inV) : inV;
      if (outV && (m.revenue || 0) > outV) { links.push({ s: n.id, t: 'rest', v: m.revenue - outV, k: 0, why: 'revenue not attributed to a named customer' }); rest += m.revenue - outV; }
    });
    if (rest > 0) nodes.set('rest', { id: 'rest', col: 2, label: 'Other customers', v: rest, color: REST, est: true });
    const hasIn = d.links.some((l) => l.kind === 'in');
    let ns = Array.from(nodes.values());
    if (!hasIn) ns = ns.map((n) => ({ ...n, col: n.col - 1 }));
    const cols = hasIn ? [{ id: 's', name: 'Suppliers' }, { id: 'm', name: 'Members' }, { id: 'c', name: 'Customers' }] : [{ id: 'm', name: 'Members' }, { id: 'c', name: 'Customers' }];
    return { cols, nodes: ns, links };
  }

  async function concept(box, id) {
    const d = await get(`network/x/${id}.json`);
    if (!d || !box || !box.isConnected || !d.links || !d.links.length) return;
    const out = d.links.filter((l) => l.kind !== 'in'), inn = d.links.filter((l) => l.kind === 'in');
    const custs = new Set(out.map((l) => l.c.cik || l.c.name));
    box.innerHTML = `<div class="section-head"><h2>Who pays the members</h2><span class="muted">Customers and suppliers the members’ annual reports name, with the stated shares</span></div>
      <div class="net-chart" id="cnet-chart"></div>
      <div class="tbl-wrap"><table class="small net-tbl"><thead><tr><th>From</th><th>To</th><th class="num">Share</th><th class="num">Dollars</th><th>Stated in</th></tr></thead><tbody>
      ${d.links.slice().sort((a, b) => b.usd - a.usd).map((l) => `<tr><td>${l.s.cik ? `<a href="#c-${l.s.cik}">${esc(l.s.t || l.s.name)}</a>` : esc(l.s.name)}</td>
        <td>${l.c.cik ? `<a href="#c-${l.c.cik}">${esc(l.c.t || l.c.name)}</a>` : esc(l.c.name || 'Unnamed customer')}</td>
        <td class="num">${upct(l.pct)} <span class="muted">of ${esc(l.kind === 'in' ? l.s.t || l.s.name : l.s.t || l.s.name)}’s revenue</span></td><td class="num">${usd(l.usd)}</td>
        <td>${l.url ? `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.s.t || l.s.name)} ${esc((l.fy || '').slice(0, 4))} ↗</a>` : ''}${l.q ? `<details class="net-q"><summary>the sentence</summary><q>${esc(l.q)}</q></details>` : ''}</td></tr>`).join('')}</tbody></table></div>
      <p class="muted small">${out.length} stated customer links from ${new Set(out.map((l) => l.s.cik)).size} members to ${custs.size} customers${inn.length ? `; ${inn.length} listed suppliers name a member as a customer` : ''}. Only customers above about 10% of a member’s revenue are disclosed; the grey band is the rest of those members’ revenue.</p>`;
    box.hidden = false;
    if (global.FFChains && global.Sankey) {
      const scene = global.FFChains.layout(conceptView(d), {
        title: `${d.name} — who pays the members`,
        subtitle: `Stated in the members’ (and their suppliers’) latest annual reports · ${usd(out.reduce((a, l) => a + l.usd, 0))} to named customers`,
        footer: ['Source: SEC EDGAR annual reports (10-K, 20-F), read by fixed rules. Dark bands: stated shares × the seller’s revenue; grey: the rest of those members’ revenue.',
          'Figures are read automatically and can contain errors; check the filings before relying on them. Not investment advice.'],
      });
      document.getElementById('cnet-chart').innerHTML = global.Sankey.toSVG(scene, `${d.name}: who pays the members`);
    }
  }

  global.FFNetwork = { company, view, concept, conceptView };
})(window);
