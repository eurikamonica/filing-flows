"""Hong Kong: the "Major customers and suppliers" disclosure in annual reports on HKEXnews.

Listing Rules Appendix D2 para 31 makes every Main Board / GEM issuer state, in the directors'
report, the share of purchases from its largest supplier and its five largest suppliers combined,
and the share of sales to its largest customer and its five largest customers combined (or that
each is under 30%). Names are optional and rarely given, so for Hong Kong the main output is
`concentration`; `rows` holds a counterparty only when the report names it.

Sources (no key needed):
  * title search  https://www1.hkexnews.hk/search/titleSearchServlet.do  (the JSON behind
    https://www1.hkexnews.hk/search/titlesearch.xhtml), headline category t1code=40000
    "Financial Statements/ESG Information", t2code=40100 "Annual Report"; lang=E for English
    titles and lang=ZH for the same list with Chinese stock names;
  * stock-code to stockId  https://www1.hkexnews.hk/search/prefix.do (JSONP);
  * the PDF itself, turned into text with the `pdftotext` CLI (-layout first, plain reading order
    as the fallback for two-column pages).

Interface shared by the market modules:
    list_reports(http, since, until, key=None) -> [{'id','code','name','name_en','filed','fy','url', ...}]
    read_report(http, rep, key=None) -> {'code','name','name_en','fy','currency','revenue','rows','concentration'} | None
    parse(text, **meta) -> same dict, offline, from pdftotext output
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime, timedelta

MARKET = 'hk'
CURRENCY = 'HKD'

BASE = 'https://www1.hkexnews.hk'
SEARCH_URL = BASE + '/search/titleSearchServlet.do'
PREFIX_URL = BASE + '/search/prefix.do'
HEADERS = {'User-Agent': 'Mozilla/5.0 (filing-flows disclosures reader)',
           'Referer': BASE + '/search/titlesearch.xhtml?lang=en',
           'Accept': 'application/json, text/javascript, */*'}
MIN_INTERVAL = 0.5          # at most two requests a second
CHUNK_DAYS = 31             # one title search per month window (a peak April returns ~2,000 rows)
ROW_RANGE = 5000

_last = [0.0]


def _polite():
    wait = MIN_INTERVAL - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def _get(http, url, params=None):
    _polite()
    try:
        return http.get(url, params=params, headers=HEADERS)
    except Exception:
        return None


# ----------------------------------------------------------------------------- listing

def _search_params(since, until, lang='E', stock_id=-1):
    return {'sortDir': '0', 'sortByOptions': 'DateTime', 'category': '0', 'market': 'SEHK',
            'stockId': str(stock_id), 'documentType': '-1',
            'fromDate': since.strftime('%Y%m%d'), 'toDate': until.strftime('%Y%m%d'),
            'title': '', 'searchType': '1', 't1code': '40000', 't2Gcode': '-2', 't2code': '40100',
            'rowRange': str(ROW_RANGE), 'lang': lang}


def parse_search(raw):
    """The rows of one titleSearchServlet.do answer: {'result': '<json string of a list>', ...}."""
    if not raw:
        return []
    try:
        doc = json.loads(raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw)
        res = doc.get('result')
        rows = json.loads(res) if isinstance(res, str) else (res or [])
    except (ValueError, AttributeError):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<br\s*/?>', ' | ', s or ''))).strip()


SKIP_TITLE = re.compile(r'interim|half[- ]year|quarterly|audited accounts|separate (annual report|financial)|'
                        r'chinese version|[一-鿿]|notification|notice of|letter to|request form|'
                        r'corporate communication', re.I)
ESG_TITLE = re.compile(r'environmental|\besg\b|sustainab', re.I)   # skipped unless the title also says annual report


def _fy_from_title(title, filed):
    """'Annual Report 2025' -> 2025; '2025/26 Annual Report' -> 2026; no year -> the year before filing (Jan-Jun)."""
    t = html.unescape(title or '')
    m = re.search(r'(20\d\d)\s*/\s*(20)?(\d\d)\b', t)
    if m:
        return 2000 + int(m.group(3))
    years = [int(y) for y in re.findall(r'\b(20\d\d)\b', t)]
    if years:
        return max(years)
    if filed:
        y, mth = int(filed[:4]), int(filed[5:7])
        return y - 1 if mth <= 6 else y
    return None


def row_to_report(r, zh_names=None):
    """One search row -> the shared report dict, or None for rows that are not an annual report."""
    title = _clean(r.get('TITLE'))
    link = r.get('FILE_LINK') or ''
    if not link.lower().endswith('.pdf') or link.lower().endswith('_c.pdf') or SKIP_TITLE.search(title):
        return None
    if ESG_TITLE.search(title) and not re.search(r'annual\s+report', title, re.I):
        return None
    if not re.search(r'annual|financial report|consolidated report|年報', title, re.I):
        return None
    code = (r.get('STOCK_CODE') or '').split('<')[0].strip()
    if not code.isdigit():
        return None
    code = code.zfill(5)
    names = [n.strip() for n in re.split(r'<br\s*/?>', html.unescape(r.get('STOCK_NAME') or '')) if n.strip()]
    try:
        filed = datetime.strptime(r.get('DATE_TIME', '')[:10], '%d/%m/%Y').date().isoformat()
    except ValueError:
        filed = None
    name_en = names[0] if names else ''
    return {'id': str(r.get('NEWS_ID') or link), 'code': code,
            'name': (zh_names or {}).get(code) or name_en, 'name_en': name_en,
            'filed': filed, 'fy': _fy_from_title(title, filed),
            'url': BASE + link if link.startswith('/') else link,
            'title': title, 'size': r.get('FILE_INFO'), 'market': MARKET}


def _windows(since, until):
    d = since
    while d <= until:
        e = min(until, d + timedelta(days=CHUNK_DAYS - 1))
        yield d, e
        d = e + timedelta(days=1)


def _as_date(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


def stock_id(http, code):
    """HKEX internal stockId for a 5-digit code (the search filters by it), or None."""
    code = str(code).zfill(5)
    raw = _get(http, PREFIX_URL, {'callback': 'callback', 'lang': 'EN', 'type': 'A', 'name': code, 'market': 'SEHK'})
    if not raw:
        return None
    t = raw.decode('utf-8', 'replace')
    try:
        doc = json.loads(t[t.index('(') + 1:t.rindex(')')])
    except ValueError:
        return None
    for s in doc.get('stockInfo') or []:
        if s.get('code') == code:
            return s.get('stockId')
    return None


def list_reports(http, since, until, key=None, codes=None):
    """Annual reports filed between two ISO dates (inclusive). HKEXnews needs no key; `key` is ignored.
    codes: optional list of stock codes to restrict the search (one stockId lookup each)."""
    since, until = _as_date(since), _as_date(until)
    ids = [-1]
    if codes:
        ids = [i for i in (stock_id(http, c) for c in codes) if i]
        if not ids:
            return []
    out, seen = [], set()
    for sid in ids:
        for a, b in _windows(since, until):
            rows = parse_search(_get(http, SEARCH_URL, _search_params(a, b, 'E', sid)))
            if not rows:
                continue
            zh = {}
            zh_rows = parse_search(_get(http, SEARCH_URL, _search_params(a, b, 'ZH', sid)))
            for z in zh_rows:
                c = (z.get('STOCK_CODE') or '').split('<')[0].strip()
                n = re.split(r'<br\s*/?>', html.unescape(z.get('STOCK_NAME') or ''))[0].strip()
                if c.isdigit() and n:
                    zh[c.zfill(5)] = n
            for r in rows:
                rep = row_to_report(r, zh)
                if rep and rep['id'] not in seen:
                    seen.add(rep['id'])
                    out.append(rep)
    out.sort(key=lambda r: (r['filed'] or '', r['code']))
    return out


# ----------------------------------------------------------------------------- PDF -> text

def pdf_to_text(data, layout=True, timeout=180):
    """pdftotext on a temp file; '' when the CLI is missing or fails."""
    exe = shutil.which('pdftotext')
    if not exe or not data:
        return ''
    d = tempfile.mkdtemp(prefix='hkpdf')
    try:
        src, dst = os.path.join(d, 'a.pdf'), os.path.join(d, 'a.txt')
        with open(src, 'wb') as f:
            f.write(data)
        cmd = [exe, '-q'] + (['-layout'] if layout else []) + ['-enc', 'UTF-8', src, dst]
        try:
            subprocess.run(cmd, timeout=timeout, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError):
            return ''
        if not os.path.exists(dst):
            return ''
        with open(dst, encoding='utf-8', errors='replace') as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------------------------------- the section

HEADING = re.compile(r'major\s+(?:customers?\s+and\s+(?:major\s+)?suppliers?|suppliers?\s+and\s+(?:major\s+)?customers?)'
                     r'|customers?\s+and\s+suppliers?\b|主要客戶及供應商', re.I)
PCT = r'(\d{1,3}(?:\.\d+)?)\s?(?:%|per\s?cent\b|percent\b)'
PCT_RE = re.compile(PCT, re.I)
# order matters: the combined and "five largest" forms are tried before the bare "largest" ones
_C = r"(?:customers?|clients?)(?:\s+groups?)?"
_S = r"suppliers?(?:\s+groups?)?"
_FIVE = r"(?:(?:top|largest)\s+)?(?:five|5)\s+(?:largest\s+|biggest\s+|major\s+|top\s+)?(?:(?!and\b|or\b)[a-z]+\s+(?:and\s+)?){0,3}?"
_ONE = r"(?:single\s+)?(?:largest|biggest)\s+"
_JOIN = r"\s*(?:and|/|&)\s*(?:the\s+)?"
ENTITY_RE = re.compile(
    r"(?P<both5>" + _FIVE + _C + _JOIN + r"(?:" + _FIVE + r")?" + _S + r")"
    r"|(?P<both5r>" + _FIVE + _S + _JOIN + r"(?:" + _FIVE + r")?" + _C + r")"
    r"|(?P<both1>" + _ONE + r"(?:customer|client)" + _JOIN + r"(?:largest\s+)?supplier(?!s))"
    r"|(?P<both1r>" + _ONE + r"supplier" + _JOIN + r"(?:largest\s+)?(?:customer|client)(?!s))"
    r"|(?P<c15>" + _ONE + r"(?:(?:customer|client)s?\s+)?(?:and|&)\s+(?:the\s+|its\s+)?" + _FIVE + _C + r")"
    r"|(?P<s15>" + _ONE + r"(?:suppliers?\s+)?(?:and|&)\s+(?:the\s+|its\s+)?" + _FIVE + _S + r")"
    r"|(?P<c5>" + _FIVE + _C + r")"
    r"|(?P<s5>" + _FIVE + _S + r")"
    r"|(?P<c1>" + _ONE + r"(?:customer|client)(?:\s+group)?(?!s))"
    r"|(?P<s1>" + _ONE + r"supplier(?:\s+group)?(?!s))", re.I)
KEYS = {'c1': ['top1_sales'], 'c5': ['top5_sales'], 's1': ['top1_purchases'], 's5': ['top5_purchases'],
        'both5': ['top5_sales', 'top5_purchases'], 'both5r': ['top5_purchases', 'top5_sales'],
        'both1': ['top1_sales', 'top1_purchases'], 'both1r': ['top1_purchases', 'top1_sales'],
        'c15': ['top1_sales', 'top5_sales'], 's15': ['top1_purchases', 'top5_purchases']}
FIELDS = ('top1_sales', 'top5_sales', 'top1_purchases', 'top5_purchases')
LT_RE = re.compile(r'(?:less\s+than|below|under|lower\s+than|not\s+more\s+than|no\s+more\s+than|not\s+exceed(?:ing)?|'
                   r'did\s+not\s+exceed|does\s+not\s+exceed|do\s+not\s+exceed|not\s+exceeding|up\s+to)\s*(?:approximately\s+|about\s+)?$', re.I)
GT_RE = re.compile(r'(?:more\s+than|over|exceed(?:ed|ing|s)?|at\s+least|above)\s*(?:approximately\s+|about\s+)?$', re.I)
SKIP_SENTENCE = re.compile(r'share\s+capital|issued\s+(?:shares|capital|share)|number\s+of\s+(?:the\s+)?issued|'
                           r'close\s+associates|their\s+(?:respective\s+)?associates|had\s+(?:any\s+)?(?:beneficial\s+)?interests?\s+in|'
                           r'has\s+any\s+interest|receivable', re.I)
ABBR = r'(?:Inc|Ltd|Co|Corp|No|approx|Mr|Ms|Mrs|Dr|St|i\.e|e\.g|vs|Pte|Bhd|Nos|S\.A|N\.V|U\.S|Jr)'


def _segments(line):
    """[(offset, text)] pieces of a layout line separated by runs of 3+ spaces."""
    out = []
    for m in re.finditer(r'\S+(?: {1,2}\S+)*', line):
        out.append((m.start(), m.group(0)))
    return out


def _is_noise(seg):
    """Chart call-outs, page numbers and the Chinese half of a bilingual page."""
    s = seg.strip()
    return (not re.search(r'[A-Za-z]{2}', s)) or bool(re.search(r'[一-鿿]', s)) and not re.search(r'[A-Za-z]{4}', s)


LIST_MARK = re.compile(r'\s*(?:[•·▪●■◦]|[–—\-*](?=\s)|\(\d{1,2}\)|\d{1,2}\)|\d{1,2}\.(?=\s)|\([ivx]{1,4}\)|[ivx]{1,4}\)|\([a-h]\)|[a-h]\))\s+')
TABLE_VERBS = re.compile(r'represent|account|attribut|\bwere\b|\bwas\b|\bis\b|\bare\b|of\s+the\s+group|\bcomprised\b|\bamount', re.I)


def _is_figure(seg):
    return bool(re.fullmatch(r'(?:\(?\d{1,3}(?:\.\d+)?\s?%?\)?\s*)+|[-–—]|N/?A|Nil', seg.strip(), re.I))


def _table_label(first):
    """A row label naming the largest / five largest, e.g. 'Five largest customers in aggregate'."""
    if len(first) > 110 or '%' in first or TABLE_VERBS.search(first) or first.rstrip().endswith('.') \
            or re.search(r'\b(?:sold|purchased|its|their|our|during)\b', first, re.I):
        return False
    return bool(ENTITY_RE.search(first) or re.match(
        r"(?:(?:total|aggregate|sum)\s+(?:of\s+)?(?:the\s+)?)?(?:the\s+)?(?:group['’]s\s+)?(?:single\s+)?(?:largest|biggest|five|top|5)\b",
        first, re.I))


_CTRL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def _column_lines(lines, col):
    """The text of each line from character `col` on (a right-hand column), segment-aligned.
    A line with text only in the left-hand column is dropped rather than read as a paragraph break."""
    out = []
    for ln in lines:
        segs = _segments(ln)
        right = [(o, s) for o, s in segs if o >= col - 3]
        if segs and not right:
            continue
        out.append(' ' * col + '   '.join(s for _, s in right))
    return out


def _window(lines, i, n=55):
    """Lines of the section whose heading is on line i: (prose lines, table rows)."""
    ln = lines[i].replace('\t', ' ')
    m = HEADING.search(ln)
    col = 0
    if m:
        # a right-hand column: the heading starts its own segment and other text sits to its left
        seg = next(((o, t) for o, t in _segments(ln) if o <= m.start() < o + len(t)), None)
        if seg and seg[0] > 20 and re.match(r'(?:\(?\w{1,3}[.)]\s*)?' + HEADING.pattern, seg[1], re.I):
            nxt = [l for l in lines[i + 1:i + 14] if l.strip()][:8]
            aligned = sum(1 for l in nxt if any(abs(o - seg[0]) <= 12 for o, _ in _segments(l)))
            if ln[:seg[0]].strip() or aligned >= 2:
                col = seg[0]
    body = [_CTRL.sub(' ', l.replace('\t', ' ')) for l in lines[i + 1:i + 1 + n]]
    if col > 20:
        body = _column_lines(body, col)
        col_used = True
    else:
        col_used = False
    prose, table = [], []
    k, in_item = 0, False
    # a two-column page with the section on the left: many lines carry a second block of words far right
    right_col = sum(1 for l in body[:30] if len([x for o, x in _segments(l) if o >= 40 and re.search(r'[a-z]{3,}\s+[a-z]{3,}', x)]) > 0) >= 4
    while k < len(body):
        raw = body[k]
        k += 1
        bullet = LIST_MARK.match(raw)
        if bullet:
            raw = ' ' * bullet.end() + raw[bullet.end():]
            in_item = True
        segs = _segments(raw)
        if segs and not col_used and segs[0][0] >= 40 and right_col:
            continue                                  # right-hand column only, the section is on the left
        if not segs:
            prose.append(';' if in_item else '')     # a blank line closes a list item
            in_item = False
            continue
        first = segs[0][1]
        rest = segs[1:]
        if _table_label(first):
            # a label wrapped onto the next line: 'Total purchases from the top 5 suppliers as a percentage of the' / 'year   40.35%'
            if not rest and k < len(body):
                nsegs = _segments(body[k])
                if len(nsegs) >= 2 and len(nsegs[0][1]) < 50 and all(_is_figure(x) for _, x in nsegs[1:]):
                    first, rest, raw = first + ' ' + nsegs[0][1], nsegs[1:], raw + '\n' + body[k]
                    k += 1
            if rest and any(_is_figure(x) and re.search(r'\d', x) for _, x in rest) and all(_is_figure(x) for _, x in rest):
                table.append((first, rest, raw))
                prose.append('')
                continue
        if col_used:
            text = ' '.join(x for _, x in segs if not _is_noise(x))
        elif len(segs) == 1 and re.fullmatch(r'\(?\d{1,3}(?:\.\d+)?\s?%\)?[.,;]?', first):
            text = first                      # the tail of a wrapped sentence: 'approximately' / '45.0%.'
        else:
            # the rest of a layout line is a chart call-out or the Chinese translation: dropped
            text = first if not _is_noise(first) else ''
        prose.append(('; ' if bullet and text else '') + text)
    return prose, table


def _sentences(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'(\w)- (\w)', r'\1-\2', text)
    parts = re.split(r'(?<=[.;])\s+(?=[A-Z(“"\d])|(?<=:)\s+(?=[A-Z(“"])|(?<=;)\s+', text)
    out = []
    for p in parts:
        if out and re.search(r'\b' + ABBR + r'\.$', out[-1]):
            out[-1] += ' ' + p
        else:
            out.append(p)
    return [p.strip() for p in out if p and p.strip()]


def _strip_prior(s, fy=None):
    """Drop comparative figures: '(2024: 46.2%)', 'as compared to 15.8% of last year', '... in 2024'."""
    s = re.sub(r'\((?:[^()]*?(?:19|20)\d\d|[^()]*?(?:last|previous|prior|preceding)\s+(?:financial\s+)?(?:year|period)|\s*FY\s?\d{2,4})[^()]*\)', ' ', s)
    s = re.sub(r',?\s*(?:as\s+)?(?:compared|as\s+against|versus|vs\.?)\s+(?:to|with)?\s*(?:approximately\s+|about\s+)?\d{1,3}(?:\.\d+)?\s?%'
               r'(?:\s+(?:of|in|for)\s+(?:the\s+)?(?:last|previous|prior|preceding|corresponding)\s+(?:financial\s+)?(?:year|period)|\s+(?:in|for)\s+(?:the\s+year\s+)?(?:FY)?\d{4})?', ' ', s, flags=re.I)
    if fy:
        def drop(m):
            return ' ' if int(m.group(2)) < int(fy) else m.group(0)
        s = re.sub(r'(\d{1,3}(?:\.\d+)?\s?%)\s+(?:in|for)\s+(?:the\s+(?:financial\s+)?year\s+)?(?:(?:ended|ending)\s+[\w ]{0,20}?)?(?:FY)?((?:19|20)\d\d)\b', drop, s)
    return s


def _assign(sentence, fy=None):
    """[(field, value_or_None, bound)] read from one sentence; bound is '<' / '>' / None."""
    s = _strip_prior(sentence, fy)
    ents = []
    for m in ENTITY_RE.finditer(s):
        kind = next(k for k, v in m.groupdict().items() if v)
        ents.append((m.start(), KEYS[kind]))
    pcts = []
    for m in PCT_RE.finditer(s):
        v = float(m.group(1))
        if v > 100:
            continue
        before = s[max(0, m.start() - 40):m.start()]
        bound = '<' if LT_RE.search(before) else ('>' if GT_RE.search(before) else None)
        pcts.append((m.start(), round(v / 100.0, 6), bound))
    if not ents or not pcts:
        return []
    out = []
    if len(pcts) == 1:
        for _, keys in ents:
            for k in keys:
                out.append((k,) + pcts[0][1:])
        return out
    flat = [(p, k) for p, keys in ents for k in keys]
    if len(flat) == len(pcts):
        return [(k,) + pc[1:] for (_, k), pc in zip(flat, pcts)]
    if len(ents) == len(pcts):
        return [(k,) + pc[1:] for (_, keys), pc in zip(ents, pcts) for k in keys]
    # otherwise each entity takes the next unused figure after it (or the nearest before)
    used = set()
    for pos, keys in ents:
        cand = [j for j, pc in enumerate(pcts) if pc[0] > pos and j not in used] or \
               [j for j, pc in enumerate(pcts) if j not in used]
        if not cand:
            break
        j = min(cand, key=lambda j: abs(pcts[j][0] - pos))
        used.add(j)
        for k in keys:
            out.append((k,) + pcts[j][1:])
    return out


def _table_values(table, prose_lines):
    """Rows like 'Five largest customers in aggregate   7.3%   7.3%' -> [(field, value, bound, text)]."""
    out = []
    head = ' '.join(prose_lines[:12])
    years = [int(y) for y in re.findall(r'\b(20\d\d)\b', head)]
    ascending = len(years) >= 2 and years[0] < years[-1]
    for label, segs, raw in table:
        m = ENTITY_RE.search(label)
        if m:
            keys = KEYS[next(k for k, v in m.groupdict().items() if v)]
        else:                                  # 'The largest' under 'Sales  Purchases' columns
            five = bool(re.search(r'five|5|top', label, re.I))
            keys = ['top5_sales', 'top5_purchases'] if five else ['top1_sales', 'top1_purchases']
            ps, ss = re.search(r'purchas|procure', head, re.I), re.search(r'\bsales\b|revenue|turnover', head, re.I)
            if ps and ss and ps.start() < ss.start():
                keys = keys[::-1]
        vals = []
        for _, s in segs:
            for t in re.findall(r'\d{1,3}(?:\.\d+)?', s):
                v = float(t)
                if v <= 100:
                    vals.append(round(v / 100.0, 6))
        if not vals:
            continue
        bound = '<' if re.search(r'less than|below|under', label, re.I) else None
        if len(keys) == 1:
            out.append((keys[0], vals[-1] if ascending else vals[0], bound, raw.strip()))
        elif len(vals) >= 2 and not ascending:
            out.append((keys[0], vals[0], bound, raw.strip()))
            out.append((keys[1], vals[1], bound, raw.strip()))
        elif len(vals) == 1 and bound:          # 'Five largest customers and suppliers: less than 30%'
            out += [(k, vals[0], bound, raw.strip()) for k in keys]
    return out


# ----------------------------------------------------------------------------- names

_TOK = r"[A-Z][\w&.'’\-]*"
ORG = (r"(?P<name>" + _TOK + r"(?:[ ,]+(?:(?:of|and|&|de|du|la|the|für)\s+)?" + _TOK + r"){0,8}"
       r"(?:,?\s+(?:Inc\.?|Ltd\.?|Limited|Corporation|Corp\.?|Company|Co\.,?\s?Ltd\.?|plc|PLC|LLC|L\.L\.C\.|AG|SE|"
       r"S\.A\.|N\.V\.|Holdings|Group|GmbH|Pte\.?\s?Ltd\.?|Bhd)\b\.?)?)")
NAME_BAD = re.compile(r"^(?:the|our|its|during|for|in|as|none|save|except|to|at|of|this|these|such|all|each|both|"
                      r"directors?|company|group|reporting|year|we|it|there|approximately|save|whilst|while|and|"
                      r"saved|further|further,|also|however|accordingly|purchases?|sales|revenue|turnover)\b"
                      r"|\b(?:Year|Period|Review|Reporting|Directors?|Board|Shareholders?|Group['’]s|Company['’]s)\b", re.I)
CORPORATE = re.compile(r"\b(?:Inc|Ltd|Limited|Corporation|Corp|Company|Co|plc|PLC|LLC|AG|SE|S\.A|N\.V|Holdings|GmbH|Bhd)\b\.?$"
                       r"|^[A-Z][A-Z0-9&\-]{1,7}$")
NAME_PATTERNS = [
    # "Apple Inc., the Group's largest customer" / "Apple (being the largest customer)"
    re.compile(ORG + r"\s*,?\s*\(?\s*(?:which\s+is\s+|who\s+is\s+|being\s+|is\s+|was\s+)?(?:also\s+)?(?:the|our|its)\s+"
               r"(?:Group['’]s\s+|Company['’]s\s+)?(?P<rank>(?:single\s+)?largest|biggest)\s+(?P<role>customer|client|supplier)\b"),
    # "BYD is ... one of the top five largest customers and suppliers"
    re.compile(r"^" + ORG + r"\s+(?:is|was|are|were|,)\b(?:[^.;]|\.(?=\d)){0,240}?\bone\s+of\s+(?:the\s+|our\s+|its\s+)?(?:Group['’]s\s+)?"
               r"(?P<rank>(?:top\s+)?(?:five|5)\s+(?:largest\s+)?)(?P<role>customers?|clients?|suppliers?)(?P<also>\s+and\s+suppliers?)?"),
    # "the largest customer, Apple Inc.," / "the largest customer (Apple Inc.)" / "largest customer is X"
    re.compile(r"(?P<rank>(?:single\s+)?largest|biggest)\s+(?P<role>customer|client|supplier)(?:\s+of\s+the\s+(?:Group|Company))?\s*"
               r"(?:,\s*(?:namely\s+|being\s+|i\.e\.,?\s+)?|\(\s*(?:namely\s+|being\s+|i\.e\.,?\s+)?|\s+(?:namely|being|was|is)\s+)" + ORG),
]


def _names(sentences, conc, fy, strict=False):
    """Named counterparties. strict (used outside the section): only corporate-looking names, top-1 patterns."""
    rows, seen = [], set()
    for s in sentences:
        for k, pat in enumerate(NAME_PATTERNS):
            if strict and k == 1:
                continue
            for m in pat.finditer(s):
                gd = m.groupdict()
                name = (gd['name'] or '').strip(' ,(')
                name = re.sub(r'^the\s+', '', name, flags=re.I).strip()
                if len(name) < 2 or NAME_BAD.search(name):
                    continue
                if strict and not CORPORATE.search(name):
                    continue
                roles = ['customer' if gd['role'].lower().startswith(('customer', 'client')) else 'supplier']
                if gd.get('also'):
                    roles.append('supplier')
                top1 = 'five' not in gd['rank'].lower() and '5' not in gd['rank']
                for role in roles:
                    if (role, name) in seen:
                        continue
                    seen.add((role, name))
                    share = conc.get('top1_sales' if role == 'customer' else 'top1_purchases') if top1 else None
                    amt = None
                    a = re.search(r'(?:HK\$|US\$|RMB|USD|HKD)\s?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?', s)
                    if a:
                        amt = float(a.group(1).replace(',', '')) * {'million': 1e6, 'billion': 1e9, 'thousand': 1e3}.get((a.group(2) or '').lower(), 1)
                    rows.append({'role': role, 'label': name, 'amount': amt, 'share': share,
                                 'rank': 1 if top1 else 5, 'year': fy, 'sentence': s[:400]})
    return rows


# ----------------------------------------------------------------------------- currency, revenue, year

_CUR = r"(RMB|Renminbi|CNY|HK\$|HKD|US\$|USD|S\$|SGD|MYR|RM|EUR|€|GBP|£|JPY|A\$|AUD|C\$|CAD|NT\$|TWD|MOP)"
CUR_RE = re.compile(_CUR + r"\s?['’‘]?\s?(000|thousand|million|mn|m\b|bn|billion)", re.I)
CUR_MAP = {'rmb': 'CNY', 'renminbi': 'CNY', 'cny': 'CNY', 'hk$': 'HKD', 'hkd': 'HKD', 'us$': 'USD', 'usd': 'USD',
           's$': 'SGD', 'sgd': 'SGD', 'myr': 'MYR', 'rm': 'MYR', 'eur': 'EUR', '€': 'EUR', 'gbp': 'GBP', '£': 'GBP',
           'jpy': 'JPY', 'a$': 'AUD', 'aud': 'AUD', 'c$': 'CAD', 'cad': 'CAD', 'nt$': 'TWD', 'twd': 'TWD', 'mop': 'MOP'}
UNIT_MAP = {'000': 1e3, 'thousand': 1e3, 'thousands': 1e3, 'million': 1e6, 'millions': 1e6, 'mn': 1e6, 'm': 1e6,
            'bn': 1e9, 'billion': 1e9, 'billions': 1e9}


def detect_currency(text):
    counts = {}
    for m in CUR_RE.finditer(text):
        c = CUR_MAP[m.group(1).lower()]
        counts[c] = counts.get(c, 0) + 1
    if not counts:
        for pat, c in ((r'RMB\s?[\d.]', 'CNY'), (r'HK\$\s?[\d.]', 'HKD'), (r'US\$\s?[\d.]', 'USD')):
            n = len(re.findall(pat, text))
            if n:
                counts[c] = n
    return max(counts, key=counts.get) if counts else None


NUM_TOKEN = re.compile(r'\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?-?\d+\.\d+\)?|\(?-?\d{4,}\)?')


def _num(tok):
    neg = tok.startswith('(') or tok.startswith('-')
    v = float(tok.strip('()-').replace(',', ''))
    return -v if neg else v


UNIT_LINE = re.compile(r"(RMB|Renminbi|CNY|HK\$|HKD|US\$|USD|S\$|SGD|MYR|RM|EUR|€|GBP|£|JPY|A\$|AUD|C\$|CAD|NT\$|TWD|MOP|\$)"
                       r"(?:\s?['’‘]?\s?|\s+in\s+)(000|thousands?|millions?|mn|m|bn|billions?)\b", re.I)
EXPRESSED = re.compile(r"expressed\s+in\s+(?:(thousands|millions)\s+of\s+)?(Hong\s+Kong\s+dollars?|HK\$|Renminbi|RMB|"
                       r"United\s+States?\s+dollars?|US\s+dollars?|US\$)", re.I)
EXPRESSED_CUR = (('hong', 'HKD'), ('hk', 'HKD'), ('renminbi', 'CNY'), ('rmb', 'CNY'), ('united', 'USD'), ('us', 'USD'))
REVENUE_ROW = re.compile(r'\s*(?:\(?[\d,]+\)?\s+)?(?:[\u3000-\u9fff（）、]+\s+)?(?:[IVX]{1,3}\.\s*)?'
                         r'(Revenues?|Turnover|(?:Total|Net)\s+revenues?|(?:Total\s+)?operating\s+(?:revenues?|income))\b(.*)$', re.I)
YUAN = re.compile(r'Unit\s*:\s*(?:Yuan|RMB)\b(?!\s*[\'’]?\s*(?:000|thousand|million))|denominated\s+in\s+(?:CNY|RMB|Renminbi)\s+unless', re.I)
NOTE_HDR = re.compile(r'(?:^|\s{2})(?:Notes?|NOTES?)(?:\s{2}|\s*$)')


def _expressed(lines):
    for h in lines[::-1]:
        m = EXPRESSED.search(h)
        if m:
            cur = next(c for k, c in EXPRESSED_CUR if m.group(2).lower().startswith(k))
            return cur, {'thousands': 1e3, 'millions': 1e6}.get((m.group(1) or '').lower(), 1)
    return None, None


def find_revenue(text):
    """(amount in report currency, currency) from the consolidated income statement, or (None, None).
    The statement is the first 'Revenue(s)/Turnover' row with a 'Note' column header and a unit a few lines up."""
    lines = text.splitlines()
    doc_cur = None
    for i, ln in enumerate(lines):
        m = REVENUE_ROW.match(ln)
        if not m or re.search(r'[a-z]{3,}', m.group(2)[:30] or '') and not re.match(r'\s*\(', m.group(2)):
            continue
        head = lines[max(0, i - 14):i]
        if not any(NOTE_HDR.search(h) for h in head):
            continue
        cur = mult = None
        for h in head[::-1]:
            units = list(UNIT_LINE.finditer(h))
            if units:
                u = units[-1]
                mult = UNIT_MAP.get(u.group(2).lower(), 1)
                cur = CUR_MAP.get(u.group(1).lower())
                if cur is None:                  # a bare "$'000": the currency is named in "(Expressed in ...)"
                    cur = _expressed(lines[max(0, i - 30):i])[0]
                    if cur is None:
                        doc_cur = doc_cur or detect_currency(text)
                        cur = doc_cur
                break
        if mult is None and any(YUAN.search(h) for h in lines[max(0, i - 12):i]):
            cur, mult = 'CNY', 1
        if mult is None:
            cur, mult = _expressed(lines[max(0, i - 30):i])
            if mult == 1:
                mult = None
        if mult is None and re.search(r'\d{1,3}(?:,\d{3}){2,}\.\d\d\b', m.group(2)):
            # PRC-format statements in yuan (two decimals) often carry no unit line at all
            cur, mult = cur or _expressed(lines[max(0, i - 30):i])[0] or detect_currency(text) or 'CNY', 1
        if not cur or not mult:
            continue
        years = [int(y) for y in re.findall(r'\b(20\d\d)\b', ' '.join(head))]
        later = len(years) >= 2 and years[0] < years[-1]

        def pick(row):
            nums = [t for t in NUM_TOKEN.findall(row) if not re.fullmatch(r'\d{1,2}(\.\d)?', t)]
            return (_num(nums[-1] if later and len(nums) >= 2 else nums[0])) if nums else None

        v = pick(m.group(2))
        if v is None:                    # 'Revenue(s)' heading over its parts: the unlabelled total, else the parts
            parts, total = [], None
            for nxt in lines[i + 1:i + 12]:
                if re.match(r'\s*(?:cost\s+of|gross|other\s+(?:income|gains|net|operating|expenses)|operating\s+(?:profit|expenses|costs)|'
                            r'selling|profit|loss|expenses|finance|share\s+of)', nxt, re.I):
                    break
                x = pick(nxt) if NUM_TOKEN.search(nxt) else None
                if x is None:
                    continue
                if not re.search(r'[A-Za-z]{3}', nxt) or re.match(r'\s*total\b', nxt, re.I):
                    total = x
                    break
                parts.append(x)
            v = total if total is not None else (sum(parts) if parts else None)
        if v is None:
            continue
        if v <= 0:
            continue
        return v * mult, cur
    return None, None


def detect_fy(text):
    """The financial year: the most cited 'year ended ... 2025' (latest of the near-ties), else the most cited year-end date."""
    head = text[:400000]
    yrs = re.findall(r'(?:year|period)\s+ended\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+\w+|\w+\s+\d{1,2}(?:st|nd|rd|th)?),?\s+((?:19|20)\d\d)', head, re.I)
    if not yrs:
        yrs = re.findall(r'(?:3[01](?:st|th)?\s+(?:December|March|June|September)|(?:December|March|June|September)\s+3[01]),?\s+((?:19|20)\d\d)', head)
    if not yrs:
        return None
    counts = {}
    for y in yrs:
        counts[y] = counts.get(y, 0) + 1
    top = max(counts.values())
    return max(int(y) for y, n in counts.items() if n >= top * 0.5)


# ----------------------------------------------------------------------------- parse

def _read_window(prose, table, fy):
    conc, bounds, sents = {}, {}, []
    for f, v, b, raw in _table_values(table, prose):
        if f in conc or f in bounds:
            continue
        if b:
            bounds[f] = (b, v)
            conc[f] = None
        else:
            conc[f] = v
        raw = re.sub(r'\s+', ' ', raw).strip()
        if raw not in sents:
            sents.append(raw)
    sentences = _sentences(' '.join(prose))
    for s in sentences:
        if SKIP_SENTENCE.search(s) or (len(s) > 120 and not re.search(
                r'sales|revenue|turnover|purchase|income|supplies|sold|bought|procure|attributable|accounted', s, re.I)):
            continue
        got = _assign(s, fy)
        used = False
        for f, v, b in got:
            if f in conc and (conc[f] is not None or f in bounds):
                continue
            used = True
            if b == '<':
                bounds[f] = ('<', v)
                conc[f] = None
            elif b == '>':
                bounds[f] = ('>', v)
                conc[f] = None
            else:
                conc[f] = v
        if used:
            sents.append(s[:400])
    return conc, bounds, sents, sentences


TOP1_MENTION = re.compile(r'(?:largest|biggest)\s+(?:customer|client|supplier)\b(?!s)', re.I)


def _names_elsewhere(lines, conc, fy, have):
    """A largest customer / supplier named outside the section (risk factors, the credit-risk or segment note)."""
    hits = [k for k, l in enumerate(lines) if TOP1_MENTION.search(l)]
    if not hits:
        return []
    keep = set()
    for k in hits:
        keep.update(range(max(0, k - 3), min(len(lines), k + 4)))
    chunks, prev = [], -2
    for k in sorted(keep):
        if k != prev + 1:
            chunks.append([])
        chunks[-1].append(re.sub(r'\s{3,}.*$', '', lines[k].strip()))
        prev = k
    sentences = [s for c in chunks for s in _sentences(' '.join(c)) if TOP1_MENTION.search(s)
                 and not re.search(r'\bnot\b|\bno\b|none\s+of', s[:60], re.I)]
    return [r for r in _names(sentences, conc, fy, strict=True) if (r['role'], r['label'].lower()) not in have]


def _dedupe_names(rows):
    """'General Motors Company ... (GM)' and 'GM' are one counterparty: keep the long form."""
    out = []
    for r in rows:
        dup = any(o is not r and o['role'] == r['role'] and (
            o['label'].lower() == r['label'].lower() and rows.index(o) < rows.index(r)
            or len(o['label']) > len(r['label']) and '(' + r['label'] + ')' in o['sentence'])
            for o in rows)
        if not dup:
            out.append(r)
    return out


def parse(text, **meta):
    """Read one annual report's pdftotext output (layout or plain). meta may carry code, name, name_en, fy, currency."""
    lines = text.splitlines()
    fy = meta.get('fy') or detect_fy(text)
    best = None
    cands = [i for i, l in enumerate(lines) if HEADING.search(l)
             and not re.search(r'section\s+headed|refer\s+to|set\s+out\s+in|page\s+\d', l, re.I)]
    for i in cands:
        prose, table = _window(lines, i)
        conc, bounds, sents, sentences = _read_window(prose, table, fy)
        score = sum(1 for f in FIELDS if f in conc)
        if best is None or score > best[0]:
            best = (score, conc, bounds, sents, sentences, i)
    if best is None or best[0] == 0:
        # no heading (or nothing under it): any sentence in the body that states the figures
        prose = [re.sub(r'\s{3,}.*$', '', l.strip()) for l in lines]
        sentences = [s for s in _sentences(' '.join(prose)) if ENTITY_RE.search(s) and PCT_RE.search(s)
                     and not re.search(r'credit\s+risk|receivable|concentration', s, re.I)]
        conc, bounds, sents, _ = _read_window(['. '.join(sentences)], [], fy)
        if best is None or sum(1 for f in FIELDS if f in conc) > 0:
            best = (sum(1 for f in FIELDS if f in conc), conc, bounds, sents, sentences, None)
    score, conc, bounds, sents, sentences, at = best
    concentration = {f: conc.get(f) for f in FIELDS}
    if bounds:
        concentration['bounds'] = {f: {'op': op, 'value': v} for f, (op, v) in bounds.items()}
    concentration['sentences'] = sents
    rows = _names(sentences, concentration, fy) if sentences else []
    rows += _names_elsewhere(lines, concentration, fy, {(r['role'], r['label'].lower()) for r in rows})
    rows = _dedupe_names(rows)
    rev, rev_cur = find_revenue(text)
    currency = meta.get('currency') or rev_cur or detect_currency(text) or CURRENCY
    return {'code': meta.get('code'), 'name': meta.get('name'), 'name_en': meta.get('name_en'),
            'fy': fy, 'currency': currency, 'revenue': rev if (rev_cur in (None, currency)) else None,
            'rows': rows, 'concentration': concentration, 'found': score > 0}


def _merge(a, b):
    """Fill the gaps of parse result a from parse result b (the plain reading-order text)."""
    ca, cb = a['concentration'], b['concentration']
    for f in FIELDS:
        if ca.get(f) is None and cb.get(f) is not None and f not in ca.get('bounds', {}):
            ca[f] = cb[f]
            ca['sentences'] = ca.get('sentences', []) + [s for s in cb.get('sentences', []) if s not in ca.get('sentences', [])]
        if ca.get(f) is None and f in cb.get('bounds', {}) and f not in ca.get('bounds', {}):
            ca.setdefault('bounds', {})[f] = cb['bounds'][f]
    have = {(r['role'], r['label']) for r in a['rows']}
    a['rows'] += [r for r in b['rows'] if (r['role'], r['label']) not in have]
    a['revenue'] = a['revenue'] if a['revenue'] is not None else b['revenue']
    a['found'] = a['found'] or b['found']
    return a


def _complete(res):
    """All four figures read, or the section was found and states its figures as bounds ('less than 30%'),
    which lets an issuer leave the top-1 shares out."""
    c = res['concentration']
    if all(c.get(f) is not None or f in c.get('bounds', {}) for f in FIELDS):
        return True
    have = lambda fs: any(c.get(f) is not None or f in c.get('bounds', {}) for f in fs)
    return bool(c.get('bounds')) and have(('top1_sales', 'top5_sales')) and have(('top1_purchases', 'top5_purchases'))


def read_report(http, rep, key=None):
    """Download one annual report PDF and read it. None when the PDF cannot be fetched or turned into text."""
    _polite()
    try:
        data = http.get(rep['url'], headers=HEADERS)
    except Exception:
        data = None
    if not data or not data[:5].startswith(b'%PDF'):
        return None
    meta = {k: rep.get(k) for k in ('code', 'name', 'name_en', 'fy')}
    text = pdf_to_text(data, layout=True)
    if not text.strip():
        return None
    res = parse(text, **meta)
    if not _complete(res):
        plain = pdf_to_text(data, layout=False)
        if plain.strip():
            res = _merge(res, parse(plain, **meta))
    res['url'] = rep.get('url')
    res['id'] = rep.get('id')
    return res
