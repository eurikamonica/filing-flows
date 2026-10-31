"""中文搜索页面 (Chinese pages for search engines): one page per company in Chinese — the latest results, how it makes
money (revenue by segment), the next earnings date and the analysts' estimates — for people who search US stocks in
Chinese ("英伟达财报", "苹果收入构成", "特斯拉财报日期"). Same figures as the English pages, written in Chinese, linked
both ways with hreflang so search engines show each reader their language.

    zh/c/<slug>/   zh/ (the list)   sitemap-zh.xml (robots.txt, IndexNow); an hreflang link added to each English c/<slug>/

    python scripts/seo_zh.py --site _site --site-url https://filing-flows.com
"""
import argparse
import datetime as dt
import html as H
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402
from seo_history import sankey_figure  # noqa: E402

e, display_name, slug_for = seo.e, seo.display_name, seo.slug_for
# the names Chinese readers search by (well-known US-listed companies); the rest keep their English name
ZH = {
    'AAPL': '苹果', 'MSFT': '微软', 'NVDA': '英伟达', 'AMZN': '亚马逊', 'GOOGL': '谷歌', 'GOOG': '谷歌', 'META': 'Meta（脸书）', 'TSLA': '特斯拉',
    'BRK-B': '伯克希尔·哈撒韦', 'BRK-A': '伯克希尔·哈撒韦', 'AVGO': '博通', 'LLY': '礼来', 'JPM': '摩根大通', 'V': 'Visa（维萨）', 'MA': '万事达',
    'UNH': '联合健康', 'XOM': '埃克森美孚', 'WMT': '沃尔玛', 'JNJ': '强生', 'PG': '宝洁', 'HD': '家得宝', 'COST': '好市多（开市客）', 'ORCL': '甲骨文',
    'CVX': '雪佛龙', 'MRK': '默沙东', 'ABBV': '艾伯维', 'KO': '可口可乐', 'PEP': '百事', 'BAC': '美国银行', 'NFLX': '奈飞', 'AMD': 'AMD（超威半导体）',
    'ADBE': 'Adobe（奥多比）', 'CRM': 'Salesforce（赛富时）', 'TMO': '赛默飞世尔', 'CSCO': '思科', 'MCD': '麦当劳', 'ABT': '雅培', 'INTC': '英特尔',
    'QCOM': '高通', 'TXN': '德州仪器', 'DIS': '迪士尼', 'WFC': '富国银行', 'PFE': '辉瑞', 'IBM': 'IBM', 'GE': '通用电气', 'CAT': '卡特彼勒', 'AMGN': '安进',
    'NKE': '耐克', 'BA': '波音', 'GS': '高盛', 'MS': '摩根士丹利', 'C': '花旗', 'SBUX': '星巴克', 'UBER': '优步', 'ABNB': '爱彼迎', 'PYPL': 'PayPal（贝宝）',
    'INTU': '财捷', 'MU': '美光', 'AMAT': '应用材料', 'LRCX': '泛林集团', 'KLAC': '科磊', 'GM': '通用汽车', 'F': '福特', 'T': 'AT&T', 'VZ': '威瑞森',
    'TMUS': 'T-Mobile', 'CMCSA': '康卡斯特', 'UPS': '联合包裹', 'FDX': '联邦快递', 'LMT': '洛克希德·马丁', 'RTX': '雷神（RTX）', 'HON': '霍尼韦尔',
    'MMM': '3M', 'DE': '迪尔', 'LOW': '劳氏', 'TGT': '塔吉特', 'SPGI': '标普全球', 'BLK': '贝莱德', 'AXP': '美国运通', 'SCHW': '嘉信理财',
    'PLTR': 'Palantir', 'SNOW': 'Snowflake', 'COIN': 'Coinbase', 'MSTR': '微策略（Strategy）', 'SMCI': '超微电脑', 'DELL': '戴尔', 'HPQ': '惠普',
    'CVS': 'CVS健康', 'GILD': '吉利德', 'BMY': '百时美施贵宝', 'MRNA': 'Moderna（莫德纳）', 'REGN': '再生元', 'VRTX': '福泰制药', 'ISRG': '直觉外科',
    'MDT': '美敦力', 'DHR': '丹纳赫', 'NOW': 'ServiceNow', 'PANW': 'Palo Alto（派拓网络）', 'CRWD': 'CrowdStrike', 'ANET': 'Arista', 'MRVL': '迈威尔',
    'ON': '安森美', 'ADI': '亚德诺', 'NXPI': '恩智浦', 'WEN': '温蒂汉堡', 'CMG': 'Chipotle', 'YUM': '百胜餐饮', 'YUMC': '百胜中国', 'LULU': 'Lululemon（露露乐檬）',
    'EL': '雅诗兰黛', 'BKNG': 'Booking（缤客）', 'EBAY': 'eBay（易贝）', 'RBLX': 'Roblox', 'EA': '艺电', 'TTWO': 'Take-Two', 'WBD': '华纳兄弟探索',
    'DASH': 'DoorDash', 'CART': 'Instacart', 'HOOD': 'Robinhood', 'SOFI': 'SoFi', 'RIVN': 'Rivian', 'LCID': 'Lucid', 'NEE': '新纪元能源', 'DUK': '杜克能源',
    'SO': '南方公司', 'COP': '康菲石油', 'OXY': '西方石油', 'SLB': '斯伦贝谢', 'KMI': '金德摩根', 'LIN': '林德', 'DOW': '陶氏', 'DD': '杜邦', 'NUE': '纽柯钢铁',
    'FCX': '自由港麦克莫兰', 'NEM': '纽蒙特', 'MO': '奥驰亚', 'PM': '菲利普莫里斯', 'KHC': '卡夫亨氏', 'MDLZ': '亿滋', 'GIS': '通用磨坊', 'CL': '高露洁',
    'KMB': '金佰利', 'ADP': 'ADP（自动数据处理）', 'ACN': '埃森哲', 'ARM': 'Arm（安谋）', 'LYFT': 'Lyft', 'SNAP': 'Snap', 'ZM': 'Zoom', 'SHOP': 'Shopify',
    'DAL': '达美航空', 'UAL': '联合航空', 'AAL': '美国航空', 'MAR': '万豪', 'HLT': '希尔顿', 'LVS': '金沙集团', 'WYNN': '永利', 'MGM': '美高梅',
    'GME': '游戏驿站', 'AMC': 'AMC院线', 'BABA': '阿里巴巴', 'PDD': '拼多多', 'JD': '京东', 'BIDU': '百度', 'NIO': '蔚来', 'XPEV': '小鹏汽车', 'LI': '理想汽车',
    'TSM': '台积电', 'ASML': '阿斯麦', 'SONY': '索尼', 'TM': '丰田', 'NVO': '诺和诺德', 'AZN': '阿斯利康', 'SAP': 'SAP', 'UNP': '联合太平洋', 'CSX': 'CSX',
    'PGR': '前进保险', 'CB': '安达保险', 'MET': '大都会人寿', 'AIG': '美国国际集团', 'ICE': '洲际交易所', 'CME': '芝商所', 'NDAQ': '纳斯达克', 'SPOT': 'Spotify',
}
SEASON = {'1': '第一季度', '2': '第二季度', '3': '第三季度', '4': '第四季度'}


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def yuan(v):
    """US dollars in Chinese units: 962 亿美元, 530 万美元."""
    if v is None:
        return '—'
    s, a = ('-' if v < 0 else ''), abs(v)
    if a >= 1e12:
        return f'{s}{a / 1e12:.2f} 万亿美元'
    if a >= 1e8:
        return f'{s}{a / 1e8:,.1f} 亿美元'.replace('.0 亿', ' 亿')
    if a >= 1e4:
        return f'{s}{a / 1e4:,.0f} 万美元'
    return f'{s}{a:,.0f} 美元'


def zpct(v, signed=True):
    return '—' if v is None else (f'{"+" if v >= 0 and signed else ""}{v:.0f}%' if signed else f'{v:.1f}%')


def period(label):
    """'Q2 2026' → '2026年第二季度', 'Q2 FY27' → '2027财年第二季度', 'FY2025' → '2025财年'."""
    m = re.fullmatch(r'Q([1-4])\s+(FY)?(\d{2}|\d{4})', (label or '').strip())
    if m:
        y = m[3] if len(m[3]) == 4 else '20' + m[3]
        return f"{y}{'财年' if m[2] else '年'}{SEASON[m[1]]}"
    m = re.fullmatch(r'FY\s?(\d{2}|\d{4})', (label or '').strip())
    return f"{m[1] if len(m[1]) == 4 else '20' + m[1]}财年" if m else (label or '')


def zdate(s):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
        return f'{d.year}年{d.month}月{d.day}日'
    except ValueError:
        return s or ''


def zpage(title, desc, url, en_url, body, image):
    alt = (f'<link rel="alternate" hreflang="zh-Hans" href="{e(url)}"><link rel="alternate" hreflang="en" href="{e(en_url)}">'
           f'<link rel="alternate" hreflang="x-default" href="{e(en_url)}">')
    doc = seo.page(title, desc, url, body, 3, image)
    return doc.replace('<html lang="en">', '<html lang="zh-Hans">', 1).replace('<link rel="canonical"', alt + '<link rel="canonical"', 1)


def company(r, c, er, cons, base, en_has):
    qs = (c or {}).get('quarters') or []
    if not qs:
        return None
    q = qs[0]
    h = q.get('headline') or {}
    if not h.get('revenue'):
        return None
    t = r['ticker']
    zh = ZH.get(t)
    en = display_name(r.get('name'))
    if zh and '（' in zh:                                   # 'AMD（超威半导体）' → '超威半导体（AMD）'; 'Visa（维萨）' → 'Visa（维萨，V）'
        main, inner = zh.rstrip('）').split('（', 1)
        who = f"{inner}（{t}）" if main == t else f"{main}（{inner}，{t}）"
        zh = inner if main == t else main
    else:
        who = f"{zh}（{t}）" if zh else f"{en}（{t}）"
    per = period(q.get('label'))
    rev = h['revenue']
    lead = f"{who}{per}营收 {yuan(rev)}" + (f"，同比{'增长' if h['yoy'] >= 0 else '下降'} {abs(h['yoy']):.0f}%" if h.get('yoy') is not None else '')
    if h.get('om') is not None:
        lead += f"，营业利润率 {h['om']:.1f}%"
    if h.get('ni') is not None:
        lead += f"，净利润 {yuan(h['ni'])}"
    lead += f"（{q.get('form')}，{zdate(q.get('filed'))}提交）。"
    # revenue by segment
    lab = {n['id']: H.unescape(n.get('label') or n.get('name') or n['id']) for n in q.get('nodes') or []}
    into, segs = {}, {}
    for ln in q.get('links') or []:
        into[ln['t']] = into.get(ln['t'], 0) + (ln.get('v') or 0)
        if ln['t'] == 'revenue':
            k = lab.get(ln['s'], ln['s'])
            a = segs.setdefault(k, [0.0, 0.0])
            a[0] += ln.get('v') or 0
            a[1] += ln.get('y') or 0
    segs = sorted(segs.items(), key=lambda x: -x[1][0])
    if len(segs) > 1:
        lead += '收入构成：' + '；'.join(f"{k} {yuan(v[0])}（{100 * v[0] / rev:.0f}%）" for k, v in segs[:3]) + '。'
    net = into.get('net')
    if into.get('gp') or net:
        lead += '每 1 美元收入中，' + '，'.join(x for x in (f"毛利 {100 * into['gp'] / rev:.0f} 美分" if into.get('gp') else '',
                                                    f"净利润 {100 * net / rev:.0f} 美分" if net else '') if x) + '。'
    # next report
    nxt = ''
    if er and er.get('report_date'):
        try:
            days = (dt.date.fromisoformat(er['report_date']) - dt.date.today()).days
        except ValueError:
            days = -1
        cs = er.get('consensus') or {}
        if days >= 0:
            nxt = (f"下一次财报预计在 {zdate(er['report_date'])}{'（预估日期）' if er.get('date_estimated') else ''}公布，还有 {days} 天。"
                   + (f"分析师预期每股收益（EPS）{cs['eps']:.2f} 美元" + (f"、营收 {yuan(cs['rev'])}" if cs.get('rev') else '')
                      + (f"，去年同期为 {cs['year_ago_eps']:.2f} 美元" if cs.get('year_ago_eps') is not None else '') + '。' if cs.get('eps') is not None else ''))
    beat = (cons or {}).get('beat_rate')
    if beat is not None:
        nxt += f"历史上有 {round(100 * beat)}% 的季度 EPS 超出市场预期。"
    seg_rows = ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(yuan(v[0]))}</td><td class='num'>{100 * v[0] / rev:.1f}%</td>"
                       f"<td class='num'>{e(zpct((v[0] / v[1] - 1) * 100) if v[1] else '—')}</td></tr>" for k, v in segs[:12])
    hist = ''.join(f"<tr><td>{e(period(x.get('label')))}</td><td class='num'>{e(yuan((x.get('headline') or {}).get('revenue')))}</td>"
                   f"<td class='num'>{e(zpct((x.get('headline') or {}).get('yoy')))}</td><td class='num'>{e(zpct((x.get('headline') or {}).get('om'), False))}</td>"
                   f"<td class='num'>{e(yuan((x.get('headline') or {}).get('ni')))}</td></tr>" for x in qs[:8])
    hq = [(x.get('label'), x.get('headline') or {}) for x in reversed(qs[:8])]
    charts = (SV.bars([(l, h2.get('revenue')) for l, h2 in hq], yuan, f'{zh or en}季度营收')
              + SV.bars([(l, h2.get('ni')) for l, h2 in hq], yuan, f'{zh or en}季度净利润', color=None)
              + (SV.hbars([(k, v[0]) for k, v in segs], yuan, f'{zh or en}收入构成（{per}）') if len(segs) > 1 else ''))
    slug = slug_for(r)
    url, en_url = f'{base}/zh/c/{slug}/', f'{base}/c/{slug}/'
    name_for_q = zh or en
    qa = [(f"{name_for_q}最新财报怎么样？", lead.split('收入构成')[0])]
    if len(segs) > 1:
        qa.append((f"{name_for_q}靠什么赚钱？", '收入构成：' + '；'.join(f"{k} {yuan(v[0])}，占 {100 * v[0] / rev:.0f}%" for k, v in segs[:4]) + '。'))
    if nxt:
        qa.append((f"{name_for_q}什么时候发布财报？", nxt))
    tiles = ''.join(f"<div class='seo-tile'><span>{k}</span><b>{e(v)}</b></div>" for k, v in (
        ('营收', yuan(rev)), ('同比', zpct(h.get('yoy'))), ('营业利润率', zpct(h.get('om'), False)), ('净利润', yuan(h.get('ni'))), ('经营现金流', yuan(h.get('ocf')))))
    more = ' · '.join(f"<a href='../../../c/{slug}/{k}/' hreflang='en'>{lbl}</a>" for k, lbl in (
        ('revenue', '收入构成（英文）'), ('earnings-date', '财报日期（英文）'), ('stock-forecast', '目标价与估值（英文）'), ('who-owns', '机构持仓（英文）'),
        ('guidance', '业绩指引（英文）')) if k in en_has)
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows 中文</a> › {e(who)}</p>"
            f"<h1>{e(who)}{e(per)}财报</h1><p class='lead'>{e(lead)}</p><div class='seo-tiles'>{tiles}</div>"
            + sankey_figure(r['cik'], q.get('label'), f'{who}{per}收入、利润与现金流 Sankey 图')
            + charts
            + (f"<p>{e(nxt)}</p>" if nxt else '')
            + (f"<h2>{e(name_for_q)}收入构成（{e(per)}）</h2><div class='tbl-wrap'><table><thead><tr><th>业务</th><th class='num'>收入</th><th class='num'>占比</th><th class='num'>同比</th></tr></thead><tbody>{seg_rows}</tbody></table></div>" if len(segs) > 1 else '')
            + f"<h2>近期季度业绩</h2><div class='tbl-wrap'><table><thead><tr><th>季度</th><th class='num'>营收</th><th class='num'>同比</th><th class='num'>营业利润率</th><th class='num'>净利润</th></tr></thead><tbody>{hist}</tbody></table></div>"
            + '<h2>常见问题</h2>' + ''.join(f'<h3>{e(x)}</h3><p>{e(y)}</p>' for x, y in qa)
            + f"<p><a class='seo-cta' href='../../../#c-{r['cik']}'>打开交互式 Sankey 图 →</a> <a href='../../../c/{slug}/' hreflang='en'>English</a></p>"
            + (f"<p class='muted'>更多：{more}</p>" if more else '')
            + f"<p class='muted'>数据自动读取自 {e(en)} 向美国证监会（SEC）提交的 {e(q.get('form'))} 文件，可能存在误差，不构成投资建议。</p>")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'WebPage', 'name': f"{who}{per}财报", 'url': url, 'inLanguage': 'zh-Hans', 'dateModified': (q.get('filed') or '')[:10],
         'about': {'@type': 'Corporation', 'name': en, 'alternateName': zh or None, 'tickerSymbol': t}},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': x, 'acceptedAnswer': {'@type': 'Answer', 'text': y}} for x, y in qa]}]}
    title = f"{who}{per}财报：营收 {yuan(rev)}" + (f"，同比 {zpct(h.get('yoy'))}" if h.get('yoy') is not None else '') + '，收入构成与财报日期 | Filing Flows'
    doc = zpage(title, lead[:200], url, en_url, body, base + '/og.png')
    doc = doc.replace('</head>', f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head>', 1)
    return url, en_url, (q.get('filed') or '')[:10] or None, doc, who, rev


def write(site, base):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    latest = {}
    for r in (ix.get('companies') if isinstance(ix, dict) else ix) or []:
        if r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or ''):
            latest[r['cik']] = r
    hub = os.path.join(site, 'disclosures', 'data')
    urls, listed = [], []
    for cik, r in latest.items():
        if not r.get('ticker'):
            continue
        slug = slug_for(r)
        en_dir = os.path.join(site, 'c', slug)
        en_has = {d for d in ('revenue', 'earnings-date', 'stock-forecast', 'who-owns', 'guidance') if os.path.exists(os.path.join(en_dir, d, 'index.html'))}
        out = company(r, read(os.path.join(site, 'data', 'c', f'{cik}.json')), read(os.path.join(hub, 'research', 'earnings', 'c', f"{r['ticker']}.json")),
                      read(os.path.join(hub, 'consensus', 'c', f'{cik}.json')), base, en_has)
        if not out:
            continue
        url, en_url, mod, doc, who, rev = out
        d = os.path.join(site, 'zh', 'c', slug)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
        urls.append((url, mod))
        listed.append((who, slug, rev, r['ticker'] in ZH))
        main = os.path.join(en_dir, 'index.html')                         # the English page names its Chinese twin
        try:
            txt = open(main, encoding='utf-8').read()
            if 'hreflang="zh-Hans"' not in txt and '<link rel="canonical"' in txt:
                alt = (f'<link rel="alternate" hreflang="en" href="{e(en_url)}"><link rel="alternate" hreflang="zh-Hans" href="{e(url)}">'
                       f'<link rel="alternate" hreflang="x-default" href="{e(en_url)}">')
                txt = txt.replace('<link rel="canonical"', alt + '<link rel="canonical"', 1)
                txt = txt.replace('</main>', f"<p class='muted'><a href='../../zh/c/{slug}/' hreflang='zh-Hans'>中文版：{e(who)}财报</a></p></main>", 1)
                open(main, 'w', encoding='utf-8').write(txt)
        except OSError:
            pass
    if listed:
        famous = sorted((x for x in listed if x[3]), key=lambda x: -x[2])
        rest = sorted((x for x in listed if not x[3]), key=lambda x: -x[2])
        lis = lambda L: ''.join(f"<li><a href='c/{s}/'>{e(w)}财报</a></li>" for w, s, _, _ in L)   # noqa: E731
        body = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › 中文</p><h1>美股财报：{len(listed):,} 家美国上市公司的最新财报</h1>"
                "<p class='lead'>每家公司的最新季度营收、增长、利润率、净利润和收入构成，以及下一次财报日期和分析师预期，全部自动读取自美国证监会（SEC）文件，每天更新。</p>"
                f"<h2>热门公司</h2><ul class='seo-list'>{lis(famous)}</ul><h2>全部公司（按营收）</h2><ul class='seo-list'>{lis(rest)}</ul>")
        idx = seo.page('美股财报：美国上市公司最新财报、收入构成与财报日期 | Filing Flows',
                       f'{len(listed):,} 家美国上市公司的最新财报：营收、增长、利润率、收入构成与下一次财报日期，读取自 SEC 文件。', base + '/zh/', body, 1, base + '/og.png')
        os.makedirs(os.path.join(site, 'zh'), exist_ok=True)
        open(os.path.join(site, 'zh', 'index.html'), 'w', encoding='utf-8').write(idx.replace('<html lang="en">', '<html lang="zh-Hans">', 1))
        urls.insert(0, (base + '/zh/', None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{m}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-zh.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-zh.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-zh.xml\n')
    return len(listed)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print(f'中文页面 / Chinese pages: {write(a.site, m.group(0) if m else "https://filing-flows.com")}')
