/* Flo's newer abilities (web/mascot.js asks this file):
   - explain a chart node from the chart's own figures: value, share of its parent, change and what drove it
     (the inflows or outflows that moved most), and for operating cash flow how it compares with net earnings;
   - compare two companies ("NVDA vs AMD"): their latest quarters side by side from data/c/<cik>.json;
   - a watchlist kept in this browser ("follow AMD"): on the next visit Flo says what those companies filed since;
   - a page guide: a few steps that point at the parts of the page (company, home, Disclosures).
   Every figure comes from the site's files; Flo says what changed, never why: the filing's own text explains that. */
(function (root) {
  'use strict';
  const doc = typeof document !== 'undefined' ? document : null;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const L = (lg, en, zh) => (lg === 'zh' ? zh : en);
  function money(v) {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    return a >= 0.95e12 ? `${s}$${(a / 1e12).toFixed(2)}T` : a >= 0.95e9 ? `${s}$${(a / 1e9).toFixed(1)}B` : a >= 0.95e6 ? `${s}$${(a / 1e6).toFixed(0)}M` : `${s}$${Math.round(a).toLocaleString('en-US')}`;
  }
  const chg = (a, b) => (fin(a) && fin(b) && a > 0 && b > 0 ? `${a >= b ? '+' : '−'}${Math.round(Math.abs(a / b - 1) * 100)}%` : 'n/m');
  const share = (a, b) => (fin(a) && fin(b) && b > 0 ? (a / b * 100 < 10 ? (a / b * 100).toFixed(1) : Math.round(a / b * 100)) + '%' : '—');
  const lc = (x) => (/^[A-Z][a-z]/.test(x) ? x[0].toLowerCase() + x.slice(1) : x);   // "Gross profit" → "gross profit", never "OCF"
  const delta = (a, b) => (fin(a) && fin(b) ? `${a - b >= 0 ? '+' : '−'}${money(Math.abs(a - b))}` : '—');
  const store = {
    get(k, d) { try { const v = root.localStorage.getItem('ffx:flo-' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { root.localStorage.setItem('ffx:flo-' + k, JSON.stringify(v)); } catch (e) { /* no storage */ } },
  };

  /* ---------- explain a node of the chart on the page ---------- */
  // ctx: {id, nodes: [{id, name, v, q, y}], links: [{s, t, v, q, y}], period, company, docUrl, compare: 'q'|'y'}
  function explainFigures(ctx, lg) {
    const N = new Map((ctx.nodes || []).map((n) => [n.id, n])), n = N.get(ctx.id);
    if (!n || !fin(n.v)) return null;
    const name = dec(n.name), ins = (ctx.links || []).filter((l) => l.t === n.id), outs = (ctx.links || []).filter((l) => l.s === n.id);
    // the node it splits from (costs, profit) or, on the revenue side, the one it flows into
    const parentId = ins.length === 1 ? ins[0].s : outs.length === 1 ? outs[0].t : null, P = parentId && N.get(parentId);
    const p = [L(lg, `<b>${esc(name)}</b> was <b>${money(n.v)}</b> in ${esc(ctx.period || 'this period')}: ${chg(n.v, n.y)} year on year and ${chg(n.v, n.q)} on the quarter before (${money(n.q)}).`,
      `<b>${esc(name)}</b> 本期为 <b>${money(n.v)}</b>（${esc(ctx.period || '')}）：同比 ${chg(n.v, n.y)}，环比 ${chg(n.v, n.q)}（上季 ${money(n.q)}）。`)];
    const facts = [];
    if (P && fin(P.v) && P.v > 0) {
      const now = n.v / P.v, was = fin(P.q) && P.q > 0 && fin(n.q) ? n.q / P.q : null;
      p.push(L(lg, `That is ${share(n.v, P.v)} of ${esc(lc(dec(P.name)))}${was != null ? ` (${share(n.q, P.q)} a quarter earlier)` : ''}.`,
        `占${esc(dec(P.name))}的 ${share(n.v, P.v)}${was != null ? `（上季 ${share(n.q, P.q)}）` : ''}。`));
      facts.push([L(lg, `Share of ${lc(dec(P.name))}`, `占${dec(P.name)}`), `${share(n.v, P.v)}${was != null ? ` · was ${share(n.q, P.q)}` : ''}`]);
    }
    // what moved it: the inflow (or, for a node that splits, the outflow) whose change was largest
    const moved = (list, side) => list.filter((l) => fin(l.v) && fin(l.q)).map((l) => ({ l, d: l.v - l.q, other: N.get(side === 'in' ? l.s : l.t) })).sort((a, b) => Math.abs(b.d) - Math.abs(a.d));
    const dIn = ins.length > 1 ? moved(ins, 'in') : [], dOut = outs.length > 1 ? moved(outs, 'out') : [];
    if (dIn.length && fin(n.q) && Math.abs(n.v - n.q) > 0 && n.id !== 'ocf') {   // cash: the earnings comparison below says it
      const top = dIn[0], whole = n.v - n.q, part = whole !== 0 ? Math.round(top.d / whole * 100) : null;
      p.push(L(lg, `Of the ${delta(n.v, n.q)} change, <b>${esc(dec(top.other.name))}</b> accounted for ${delta(top.l.v, top.l.q)}${part != null && Math.abs(part) <= 300 ? ` (${part}%)` : ''}.`,
        `${delta(n.v, n.q)} 的变化中，<b>${esc(dec(top.other.name))}</b> 贡献了 ${delta(top.l.v, top.l.q)}${part != null && Math.abs(part) <= 300 ? `（${part}%）` : ''}。`));
    }
    if (dOut.length) {
      const top = dOut[0];
      p.push(L(lg, `Where it went: ${dOut.slice(0, 3).map((x) => `${esc(dec(x.other.name))} ${share(x.l.v, n.v)}`).join(', ')}. The biggest move was ${esc(lc(dec(top.other.name)))} (${delta(top.l.v, top.l.q)}).`,
        `去向：${dOut.slice(0, 3).map((x) => `${esc(dec(x.other.name))} ${share(x.l.v, n.v)}`).join('，')}。变化最大的是${esc(dec(top.other.name))}（${delta(top.l.v, top.l.q)}）。`));
    }
    // cash against earnings
    const net = N.get('net'), wc = N.get('wc_out') || N.get('wc_in'), R = N.get('revenue');
    if (/^(ocf|fcf)$/.test(n.id) && net && fin(net.v) && net.v > 0) {
      const conv = n.v / net.v, was = fin(net.q) && net.q > 0 && fin(n.q) ? n.q / net.q : null;
      p.push(L(lg, `Against earnings: ${Math.round(conv * 100)}% of net earnings (${money(net.v)}) arrived as ${n.id === 'ocf' ? 'operating cash flow' : 'free cash flow'}${was != null ? `, against ${Math.round(was * 100)}% a quarter earlier` : ''}.` +
        (wc && wc.id === 'wc_out' && fin(wc.v) ? ` Working capital &amp; other took ${money(wc.v)}${fin(wc.q) ? ` (${money(wc.q)} the quarter before)` : ''}.` : ''),
        `与利润相比：净利润（${money(net.v)}）的 ${Math.round(conv * 100)}% 转化为${n.id === 'ocf' ? '经营现金流' : '自由现金流'}${was != null ? `，上季为 ${Math.round(was * 100)}%` : ''}。` +
        (wc && wc.id === 'wc_out' && fin(wc.v) ? `营运资本及其他占用了 ${money(wc.v)}${fin(wc.q) ? `（上季 ${money(wc.q)}）` : ''}。` : '')));
      facts.push([L(lg, 'Share of net earnings', '占净利润'), `${Math.round(conv * 100)}%${was != null ? ` · was ${Math.round(was * 100)}%` : ''}`]);
    }
    // a margin: profit lines against revenue
    if (/^(gp|oi|net|pretax)$/.test(n.id) && R && fin(R.v) && R.v > 0) {
      const m = (a, b) => (fin(a) && fin(b) && b > 0 ? a / b * 100 : null), now = m(n.v, R.v), q = m(n.q, R.q), y = m(n.y, R.y);
      const pts = (a, b) => (a != null && b != null ? `${a - b >= 0 ? '+' : '−'}${Math.abs(a - b).toFixed(1)} pts` : 'n/m');
      facts.push([L(lg, 'Margin on revenue', '占营收'), `${now.toFixed(1)}% · ${pts(now, q)} Q/Q · ${pts(now, y)} Y/Y`]);
      if (fin(n.q) && fin(R.q) && R.v - R.q !== 0) {
        const inc = (n.v - n.q) / (R.v - R.q);
        if (Math.abs(inc) < 5) p.push(L(lg, `Each extra dollar of revenue added ${Math.round(inc * 100)}¢ here (the quarter before averaged ${q != null ? Math.round(q) : '—'}¢).`,
          `每多 1 美元营收，这里增加 ${Math.round(inc * 100)} 美分（上季平均 ${q != null ? Math.round(q) : '—'} 美分）。`));
      }
    }
    facts.unshift([L(lg, 'Year on year', '同比'), `${chg(n.v, n.y)} · from ${money(n.y)}`], [L(lg, 'Quarter on quarter', '环比'), `${chg(n.v, n.q)} · ${delta(n.v, n.q)}`]);
    const html = p.map((x) => `<p>${x}</p>`).join('') +
      `<ul class="flo-facts">${facts.map(([k, v]) => `<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('')}</ul>` +
      `<p class="flo-source">${L(lg, 'From the figures on this chart (as filed). They say what changed, not why: the filing’s own discussion explains the reasons.', '数字来自本图（按申报口径）。它们说明变化了什么，原因要看申报文件中的管理层讨论。')}</p>`;
    return { html, facts: facts.map(([k, v]) => `${k}: ${v}`), mood: 'talk', links: ctx.docUrl ? [[ctx.docUrl, L(lg, 'The filing', '申报原文')]] : [] };
  }

  /* ---------- compare two companies ---------- */
  const COMPARE = /\b(?:vs\.?|versus|compared?|comparison|side by side)\b|对比|比较|相比|PK/i;
  const isCompare = (q) => COMPARE.test(String(q || ''));
  const rx = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // up to two different companies named in the question
  function findCompanies(q, ix, findCompany, zhNames) {
    const a = findCompany(q, ix);
    if (!a) return [];
    let rest = String(q);
    if (a.ticker) rest = rest.replace(new RegExp('\\$?\\b' + rx(a.ticker) + '\\b', 'ig'), ' ');
    const w = String(a.name || '').match(/[A-Za-z]{4,}/);
    if (w) rest = rest.replace(new RegExp(rx(w[0]), 'ig'), ' ');
    Object.entries(zhNames || {}).forEach(([zh, t]) => { if (t === a.ticker) rest = rest.split(zh).join(' '); });
    const b = findCompany(rest, ix);
    return b && +b.cik !== +a.cik ? [a, b] : [a];
  }
  async function compare(cos, lg, load) {
    const C = await Promise.all(cos.map((c) => load(c).catch(() => null)));
    if (C.some((c) => !c || !(c.quarters || []).length)) return null;
    const Q = C.map((c) => c.quarters[0]), H = Q.map((q) => q.headline || {});
    const rows = [
      [L(lg, 'Revenue', '营收'), H.map((h) => h.revenue), money, 'rev'],
      [L(lg, 'Revenue growth, Y/Y', '营收同比'), H.map((h) => h.yoy), (v) => (fin(v) ? `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(0)}%` : '—'), 'rev'],
      [L(lg, 'Operating margin', '营业利润率'), H.map((h) => h.om), (v) => (fin(v) ? `${(+v).toFixed(1)}%` : '—'), 'profit'],
      [L(lg, 'Net earnings', '净利润'), H.map((h) => h.ni), money, 'profit'],
      [L(lg, 'Operating cash flow', '经营现金流'), H.map((h) => h.ocf), money, 'profit'],
    ];
    const col = { rev: 'var(--mk-rev, #7a7974)', profit: 'var(--mk-profit, #17734a)' };
    const table = `<table class="flo-cmp"><thead><tr><th>${L(lg, 'Latest quarter', '最新季度')}</th>${cos.map((c, i) => `<th><b>${esc(c.ticker)}</b><br>${esc(dec(Q[i].label))} · ${esc(Q[i].end)}</th>`).join('')}</tr></thead><tbody>` +
      rows.map(([k, v, f, role]) => {
        const m = Math.max(...v.filter(fin).map((x) => Math.abs(x)), 0);
        return `<tr><td>${esc(k)}</td>${v.map((x) => `<td>${esc(f(x))}${fin(x) && m > 0 ? `<span class="bar" style="width:${Math.max(2, Math.round(Math.abs(x) / m * 80))}px;background:${col[role]}"></span>` : ''}</td>`).join('')}</tr>`;
      }).join('') + '</tbody></table>';
    const [a, b] = H, p = [];
    if (fin(a.revenue) && fin(b.revenue) && b.revenue > 0 && a.revenue > 0) {
      const r = a.revenue / b.revenue;
      p.push(r >= 1 ? L(lg, `${esc(cos[0].ticker)}'s latest quarter brought in <b>${r.toFixed(1)}×</b> ${esc(cos[1].ticker)}'s revenue`, `${esc(cos[0].ticker)} 最新季度营收是 ${esc(cos[1].ticker)} 的 <b>${r.toFixed(1)} 倍</b>`)
        : L(lg, `${esc(cos[1].ticker)}'s latest quarter brought in <b>${(1 / r).toFixed(1)}×</b> ${esc(cos[0].ticker)}'s revenue`, `${esc(cos[1].ticker)} 最新季度营收是 ${esc(cos[0].ticker)} 的 <b>${(1 / r).toFixed(1)} 倍</b>`));
    }
    if (fin(a.om) && fin(b.om)) {
      const hi = a.om >= b.om ? 0 : 1;
      p.push(L(lg, `and ${esc(cos[hi].ticker)} kept more of each dollar as operating profit (${(+H[hi].om).toFixed(1)}% against ${(+H[1 - hi].om).toFixed(1)}%)`,
        `${esc(cos[hi].ticker)} 每 1 美元营收留下的经营利润更多（${(+H[hi].om).toFixed(1)}% 对 ${(+H[1 - hi].om).toFixed(1)}%）`));
    }
    const ends = Q.map((q) => Date.parse(q.end)), gap = Math.abs(ends[0] - ends[1]) / 864e5;
    const note = gap > 20 ? L(lg, ` The two quarters end ${Math.round(gap / 30)} month${Math.round(gap / 30) === 1 ? '' : 's'} apart (different fiscal years).`, ` 两个季度的结束日相差约 ${Math.round(gap / 30)} 个月（财年不同）。`) : '';
    return { html: `<p>${p.join(L(lg, ', ', '，'))}${L(lg, '.', '。')}${note}</p>${table}`, mood: 'talk',
      facts: rows.map(([k, v, f]) => `${k}: ${cos.map((c, i) => `${c.ticker} ${f(v[i])}`).join(', ')}`),
      links: cos.map((c) => [`#c-${c.cik}`, L(lg, `${c.ticker} chart`, `${c.ticker} 财报图`)]).concat([[`#chart/c=${cos.map((c) => c.cik).join(',')}&i=h:revenue&t=bar`, L(lg, 'Both over time', '历史对比图')]]) };
  }

  /* ---------- watchlist (this browser) ---------- */
  const WATCH = /\b(?:follow|watch)\b|\bunfollow\b|stop (?:following|watching)|关注|自选|取消关注/i;
  const DIGEST = /\b(?:my )?watch ?list\b|since (?:my )?last visit|what(?:'s| has)? changed (?:for|in|at) my|我的关注|关注列表|自选股/i;
  const watched = () => store.get('watch', []);
  function setWatch(list) { store.set('watch', [...new Set(list)].slice(0, 40)); }
  const isWatch = (q) => WATCH.test(String(q || '')) && !/\bfollow[- ]?up\b/i.test(q);
  const isDigest = (q) => DIGEST.test(String(q || ''));
  function watchAnswer(q, co, lg) {
    const off = /\bunfollow\b|stop (?:following|watching)|取消关注/i.test(q);
    if (!co) return { html: L(lg, 'Which company should I follow? For example “follow AMD”.', '要关注哪家公司？比如「关注 AMD」。'), mood: 'think', facts: [], links: [] };
    const list = watched().filter((t) => t !== co.ticker);
    if (!off) list.unshift(co.ticker);
    setWatch(list);
    return { html: off ? L(lg, `Stopped following <b>${esc(co.ticker)}</b>.`, `已取消关注 <b>${esc(co.ticker)}</b>。`)
      : L(lg, `Following <b>${esc(co.ticker)}</b> in this browser. Next time you open Flo I'll say what it filed since. For e-mail alerts use the ☆ Follow button on its page.`,
        `已在本浏览器关注 <b>${esc(co.ticker)}</b>。下次打开 Flo 时，我会告诉你它这期间发了什么。要邮件提醒，请用公司页上的 ☆ Follow。`) +
      (list.length ? `<p class="flo-source">${L(lg, 'Following', '关注中')}: ${list.map(esc).join(', ')}</p>` : ''), mood: off ? 'talk' : 'happy', facts: [], links: [[`#c-${co.cik}`, co.ticker]] };
  }
  // what the followed companies filed after `since` (ISO date), newest first; the rest: nothing new
  function digest(ix, list, since, lg) {
    const by = new Map(((ix && ix.companies) || []).map((c) => [String(c.ticker || '').toUpperCase(), c]));
    const rows = [], quiet = [];
    list.forEach((t) => {
      const c = by.get(String(t).toUpperCase());
      if (!c) return;
      const ev = [c].concat((c.also || []).map((a) => Object.assign({}, c, a))).filter((e) => e.filed && (!since || e.filed > since));
      if (ev.length) ev.forEach((e) => rows.push(e)); else quiet.push(c);
    });
    if (!rows.length && !quiet.length) return null;
    rows.sort((a, b) => (b.filed || '').localeCompare(a.filed || ''));
    const day = (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
    const html = (rows.length ? L(lg, `<b>Since your last visit${since ? ` on ${day(since)}` : ''}</b>, ${rows.length === 1 ? 'one filing' : rows.length + ' filings'} from the companies you follow:`,
      `<b>自你上次来${since ? `（${day(since)}）` : ''}</b>，你关注的公司有 ${rows.length} 份新申报：`) : L(lg, `<b>Nothing new</b> from the companies you follow${since ? ` since ${day(since)}` : ''}.`, `你关注的公司${since ? `自 ${day(since)} 起` : ''}<b>没有新申报</b>。`)) +
      rows.slice(0, 6).map((e) => `<div class="flo-watch-ev"><span class="tk">${esc(e.ticker)}</span><div><b>${esc(e.form)} · ${esc(dec(e.label))}</b>, ${L(lg, 'filed', '申报于')} ${day(e.filed)}${e.prelim || e.form === '8-K' ? ` · ${L(lg, 'preliminary', '初步')}` : ''}<br>` +
        `${L(lg, 'Revenue', '营收')} ${esc(e.rev || money(e.revenue))}${fin(e.yoy) ? `, ${e.yoy >= 0 ? '+' : '−'}${Math.abs(e.yoy).toFixed(1)}% Y/Y` : ''}${fin(e.om) ? ` · ${L(lg, 'operating margin', '营业利润率')} ${(+e.om).toFixed(1)}%` : ''}<br><a href="#c-${+e.cik}">${L(lg, 'Open the chart', '打开财报图')} →</a></div></div>`).join('') +
      (quiet.length ? `<p class="flo-source">${L(lg, 'Nothing new', '没有新申报')}: ${quiet.map((c) => esc(c.ticker)).join(', ')}</p>` : '');
    return { html, rows, quiet, mood: rows.length ? 'happy' : 'talk', facts: [], links: [] };
  }
  // once a day at most: the digest for the opening of Flo; remembers today as the last visit
  function visitDigest(ix, lg, today) {
    const list = watched();
    if (!list.length) return null;
    today = today || new Date().toISOString().slice(0, 10);
    const last = store.get('watch-seen', null);
    if (last === today) return null;
    store.set('watch-seen', today);
    return digest(ix, list, last, lg);
  }

  /* ---------- the page guide ---------- */
  const TOUR = /show me around|page guide|\btour\b|guide me|how (?:do i|to) (?:use|read) this page|导览|带我看看|怎么看这(?:一)?页|页面指南/i;
  const isTour = (q) => TOUR.test(String(q || ''));
  const STEPS = {
    company: [
      ['.co-tabs', ['Five ways to read a company', '五种读公司的方式'], ['Earnings: the Sankey and how it changed. Cash & capital: cash flow, buybacks, debt. Valuation: fair value, analysts, options. Holders & trades: 13F funds, insiders, officials. Relationships: customers, suppliers and shocks.',
        '财报：桑基图及变化。现金与资本：现金流、回购、债务。估值：合理价值、分析师、期权。持有人与交易：13F 基金、内部人、官员。关系：客户、供应商与冲击。']],
      ['#ff-overview', ['At a glance', '一眼看懂'], ['The latest quarter and what the Disclosure Hub knows. Lines show the last seven quarters; each tile opens its source.', '最新季度和 Disclosure Hub 的数据。小线条是最近 7 个季度；点卡片可查看来源。']],
      ['.co-period', ['Pick the period and the view', '选择期间和视图'], ['Any quarter, a full fiscal year or all quarters. "vs" turns the chart into a comparison with the quarter before or a year ago.', '任意季度、整个财年或全部季度。点「vs」变成与上季或去年同期的对比图。']],
      ['.stage, .sheet', ['The Sankey', '桑基图'], ['Revenue on the left flows to costs, profit and operating cash flow. Click any node for what the company wrote about that line, and ask me to explain the number.', '左边的营收流向成本、利润和经营现金流。点任一节点看公司对这一行的说明，也可以让我解释这个数字。']],
      ['.flo-launch, .flo-panel', ['Ask Flo', '问 Flo'], ['Ask about this company, compare it with another ("NVDA vs AMD"), or say "follow NVDA" and I will tell you what it filed next time.', '问这家公司、和另一家对比（「NVDA vs AMD」），或者说「关注 NVDA」，下次我会告诉你它发了什么。']],
    ],
    home: [
      ['#earnings-day', ['Earnings day', '财报日'], ['Pick a day: how each sector grew, growth against margin and the largest reporters. Click a dot or a row for its chart.', '选一天：各板块增长、增速与利润率、最大的报告公司。点点或行打开财报图。']],
      ['#rows', ['Every filing', '所有申报'], ['Newest first, with filters by name, sector and form.', '最新在前，可按名称、板块和表格类型筛选。']],
      ['.top .search, #q', ['Search', '搜索'], ['Type a ticker or name, or press ⌘K / Ctrl+K to search industries, themes, funds and officials too.', '输入代码或名称，或按 ⌘K / Ctrl+K 同时搜索行业、主题、基金和官员。']],
    ],
    hub: [
      ['nav.modules', ['Six groups of sections', '六组栏目'], ['Where the money is going, people\'s trades, filings and events, markets and options, company research, and the data sources themselves.', '资金去向、个人交易、申报与事件、市场与期权、公司研究，以及数据来源本身。']],
      ['#notice', ['How fresh it is', '数据新鲜度'], ['Each section says when its sources were last read. Amber means a source is behind.', '每个栏目说明其来源最近一次读取时间。']],
      ['#workspace', ['The section', '栏目内容'], ['Filters at the top, then the tables and charts. Rows link to the filings.', '上方是筛选，下面是表格和图表。每行都链接到申报原文。']],
    ],
  };
  let tour = null;
  function endTour() { if (!tour) return; tour.els.forEach((e) => e.remove()); root.removeEventListener('resize', tour.place); root.removeEventListener('keydown', tour.key); tour = null; }
  function startTour(kind, lg) {
    if (!doc) return false;
    const steps = (STEPS[kind] || []).map((s) => ({ el: s[0].split(',').map((x) => doc.querySelector(x.trim())).find((e) => e && e.getBoundingClientRect().width), s })).filter((x) => x.el);
    if (!steps.length) return false;
    endTour();
    store.set('tour-' + kind, 1);
    const hole = doc.createElement('div'), card = doc.createElement('section');
    hole.className = 'flo-tour-hole'; card.className = 'flo-tour-card';
    card.setAttribute('role', 'dialog'); card.setAttribute('aria-live', 'polite');
    doc.body.append(hole, card);
    tour = { els: [hole, card], i: 0 };
    const zh = lg === 'zh';
    tour.place = () => {
      const st = steps[tour.i], r = st.el.getBoundingClientRect(), pad = 6;
      Object.assign(hole.style, { left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + 2 * pad + 'px', height: Math.min(r.height, root.innerHeight * 0.6) + 2 * pad + 'px' });
      const below = r.top + Math.min(r.height, root.innerHeight * 0.6) + 18, h = card.offsetHeight || 200;
      const top = below + h < root.innerHeight ? below : Math.max(12, r.top - h - 18);
      card.style.top = top + 'px';
      card.style.left = Math.max(12, Math.min(r.left, root.innerWidth - card.offsetWidth - 12)) + 'px';
    };
    const show = () => {
      const st = steps[tour.i], [sel, title, text] = st.s, n = steps.length;
      card.setAttribute('aria-label', (zh ? '页面指南 ' : 'Page guide, step ') + (tour.i + 1) + ' / ' + n);
      card.innerHTML = `<div class="ft-step">${zh ? '页面指南' : 'Page guide'} · ${tour.i + 1} / ${n}</div><h3>${esc(title[zh ? 1 : 0])}</h3><p>${esc(text[zh ? 1 : 0])}</p>
        <div class="ft-row"><span class="ft-dots">${steps.map((_, i) => `<i class="${i === tour.i ? 'on' : ''}"></i>`).join('')}</span>
        <button type="button" class="ft-skip">${zh ? '跳过' : 'Skip'}</button>${tour.i ? `<button type="button" class="ft-back">${zh ? '上一步' : 'Back'}</button>` : ''}
        <button type="button" class="ft-next">${tour.i + 1 < n ? (zh ? '下一步' : 'Next') : (zh ? '完成' : 'Done')}</button></div>`;
      card.querySelector('.ft-skip').onclick = endTour;
      const back = card.querySelector('.ft-back'); if (back) back.onclick = () => { tour.i--; show(); };
      card.querySelector('.ft-next').onclick = () => { if (tour.i + 1 < n) { tour.i++; show(); } else endTour(); };
      const r = st.el.getBoundingClientRect();
      if (r.top < 70 || r.bottom > root.innerHeight - 40) st.el.scrollIntoView({ block: 'center' });
      setTimeout(tour.place, 30);
      card.querySelector('.ft-next').focus({ preventScroll: true });
    };
    tour.key = (e) => { if (e.key === 'Escape') endTour(); };
    root.addEventListener('resize', tour.place);
    root.addEventListener('keydown', tour.key);
    show();
    return true;
  }
  const tourKind = (ctx) => (ctx && ctx.kind === 'company' ? 'company' : ctx && (ctx.kind === 'hub' || ctx.kind === 'industry') ? 'hub' : ctx && ctx.kind === 'home' ? 'home' : null);
  const toured = (kind) => !!store.get('tour-' + kind, 0);

  root.FFFloFeatures = { explainFigures, isCompare, findCompanies, compare, isWatch, isDigest, watchAnswer, digest, visitDigest, watched, setWatch, isTour, startTour, endTour, tourKind, toured, STEPS };
  if (typeof module !== 'undefined') module.exports = root.FFFloFeatures;
})(typeof globalThis !== 'undefined' ? globalThis : this);
