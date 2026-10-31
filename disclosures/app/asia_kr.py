"""Korea (DART): major customers and suppliers from annual business reports (사업보고서).

Korean annual reports name their main customers (주요 매출처 / 주요 고객) and their main suppliers (주요 매입처 /
원재료 매입처) in "II. 사업의 내용" (business section) — usually under "매출 및 수주상황" (sales) and
"원재료 및 생산설비" / "주요 원재료 등의 현황" (raw materials). This module finds those reports, reads those sections and
turns them into rows: one per counterparty, with the amount or share of sales when the report states it.

Sources
  OpenDART (key: crtfc_key, env DART_API_KEY in production; https://opendart.fss.or.kr/guide)
    list.json      공시검색: bgn_de, end_de (YYYYMMDD; without corp_code a window may span at most 3 months),
                   pblntf_ty='A', pblntf_detail_ty='A001' (사업보고서), last_reprt_at='Y', corp_cls, page_no,
                   page_count (≤100). Answer: status ('000' ok, '013' nothing found), total_page, list[] of
                   corp_code, corp_name, stock_code, corp_cls, report_nm, rcept_no, flr_nm, rcept_dt, rm.
    document.xml   공시서류원본파일: rcept_no → a zip of the filing's dart4 XML (the report itself is <rcept_no>.xml,
                   attachments such as the audit report are <rcept_no>_<n>.xml).
    corpCode.xml   고유번호: a zip of CORPCODE.xml, <list> of corp_code, corp_name, corp_eng_name, stock_code,
                   modify_date — used for English names.
  The public DART viewer (no key), used when there is no key or the API fails:
    dsab007/detailSearch.ax   the public search (publicType=A001, startDate, endDate, currentPage, maxResults)
    dsaf001/main.do?rcpNo=    the viewer page, whose script lists the table of contents (node text, rcpNo, dcmNo,
                              eleId, offset, length, dtd)
    report/viewer.do?rcpNo=&dcmNo=&eleId=&offset=&length=&dtd=   one section rendered as HTML

Both the dart4 XML (<SECTION-n>, <TITLE>, <P>, <TABLE>, <TD>/<TH>/<TE>/<TU>) and the viewer HTML are normalised to
the same blocks (paragraph lines, headings, tables expanded over rowspan/colspan) before anything is read.

What is read
  customers  "주요 매출처는 A, B, C 등입니다" sentences; "각각 39.4%, 35.8%" shares and "각각 …백만원" amounts paired in order;
             a single named customer's share ("해당 거래처에 대한 매출 비중은 … 약 27%"); customer tables (외부고객1 | 88%,
             A사 | 매출액 | 매출비중). Customers the report hides behind letters ("가"사, A사, 외부고객1) are kept, flagged
             anonymous=True, so a reader can still follow their size year to year.
  suppliers  raw-material tables with a 매입처 / 구매처 / 업체명 column (one row per supplier, with the item, its purchase
             amount and its share of segment purchases under 'items' — the amount is the item's, not the supplier's, so
             the row's own 'amount'/'share' stay None), and "… 등을 A, B 등에서 공급받고" / "공급사는 A, B입니다" sentences.
  concentration  "주요 5대 매출처 … 약 15%" → top5_sales; "상위 10개 고객 … 92%" → top10_sales; a single unnamed
             customer's amount ("10% 이상을 차지하는 단일 고객에 대한 매출은 …백만원") → top1_sales_amount (and top1_sales
             against revenue); otherwise top1_sales is the largest stated customer share.
  revenue    매출액 (or 영업수익) of the latest year in 요약연결재무정보 (consolidated summary), else 요약재무정보.

Missing is not zero: a section that describes customers without naming them gives no rows.

    python disclosures/app/asia_kr.py list 2026-03-01 2026-03-31
    python disclosures/app/asia_kr.py read 20260310002820
    python disclosures/app/asia_kr.py parse path/to/section.html
"""
import html
import io
import json
import os
import re
import sys
import time
import zipfile
from html.parser import HTMLParser

MARKET = 'kr'
CURRENCY = 'KRW'

API = 'https://opendart.fss.or.kr/api'
DART = 'https://dart.fss.or.kr'
MIN_INTERVAL = 0.2  # ≤5 requests a second
_last = [0.0]
_corp_cache = {}


# ----------------------------------------------------------------------------------------------- polite fetching

def _get(http, url, params=None):
    wait = _last[0] + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    try:
        return http.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0 (filing-flows)'})
    finally:
        _last[0] = time.monotonic()


def _ymd(iso):
    return str(iso).replace('-', '')[:8]


def _iso(ymd):
    s = re.sub(r'\D', '', str(ymd or ''))
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}' if len(s) >= 8 else None


def _month_end(y, m):
    import calendar
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def fy_from_title(report_nm):
    """'사업보고서 (2025.12)' → '2025-12-31'."""
    m = re.search(r'\((\d{4})\.(\d{1,2})\)', report_nm or '')
    return _month_end(int(m.group(1)), int(m.group(2))) if m else None


def _windows(since, until, days=89):
    import datetime as dt
    a, b = dt.date.fromisoformat(since[:10]), dt.date.fromisoformat(until[:10])
    while a <= b:
        e = min(b, a + dt.timedelta(days=days))
        yield a.isoformat(), e.isoformat()
        a = e + dt.timedelta(days=1)


# ----------------------------------------------------------------------------------------------- listing reports

def corp_codes(http, key):
    """corp_code → {'name','name_en','stock_code'} from corpCode.xml (cached per key)."""
    if key in _corp_cache:
        return _corp_cache[key]
    out = {}
    raw = _get(http, f'{API}/corpCode.xml', {'crtfc_key': key})
    if raw and raw[:2] == b'PK':
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            text = _decode(z.read(z.namelist()[0]))
            out = parse_corp_codes(text)
        except (zipfile.BadZipFile, KeyError, IndexError):
            out = {}
    _corp_cache[key] = out
    return out


def parse_corp_codes(text):
    out = {}
    for blk in re.findall(r'<list>(.*?)</list>', text, re.S):
        f = {k: html.unescape(v.strip()) for k, v in re.findall(r'<(\w+)>(.*?)</\1>', blk, re.S)}
        if f.get('corp_code'):
            out[f['corp_code']] = {'name': f.get('corp_name') or None, 'name_en': f.get('corp_eng_name') or None,
                                   'stock_code': (f.get('stock_code') or '').strip() or None}
    return out


def parse_list_json(data, names=None):
    """One list.json answer → (reports, total_page, status)."""
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    names = names or {}
    out = []
    for it in data.get('list') or []:
        nm = it.get('report_nm') or ''
        if '사업보고서' not in nm:
            continue
        rc = it.get('rcept_no')
        code = it.get('corp_code')
        en = (names.get(code) or {}).get('name_en')
        out.append({'id': rc, 'code': code, 'name': (it.get('corp_name') or '').strip(), 'name_en': en,
                    'filed': _iso(it.get('rcept_dt')), 'fy': fy_from_title(nm),
                    'url': f'{DART}/dsaf001/main.do?rcpNo={rc}',
                    'stock_code': (it.get('stock_code') or '').strip() or None, 'corp_cls': it.get('corp_cls'),
                    'report_nm': re.sub(r'\s+', ' ', nm).strip(), 'amended': nm.strip().startswith('['),
                    'filer': it.get('flr_nm'), 'remark': it.get('rm') or ''})
    try:
        total = int(data.get('total_page') or 1)
    except ValueError:
        total = 1
    return out, total, data.get('status')


_CLS = {'kospi': 'Y', 'kosdaq': 'K', 'konex': 'N', 'etc': 'E'}


def parse_search_html(text):
    """The public search (dsab007/detailSearch.ax) → (reports, total_pages)."""
    out = []
    for tr in re.findall(r'<tr>(.*?)</tr>', text, re.S):
        rc = re.search(r'rcpNo=(\d{14})', tr)
        code = re.search(r"openCorpInfoNew\('(\d+)'", tr)
        if not rc or not code:
            continue
        name = re.search(r"openCorpInfoNew\([^>]*>\s*(.*?)\s*</a>", tr, re.S)
        title = re.search(r'id="r_\d+"[^>]*>(.*?)</a>', tr, re.S)
        nm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', title.group(1))).strip() if title else ''
        if '사업보고서' not in nm:
            continue
        date = re.findall(r'<td>\s*(\d{4}\.\d{2}\.\d{2})\s*</td>', tr)
        cls = re.search(r'tagCom_(kospi|kosdaq|konex|etc)\b', tr)
        filer = re.search(r'<td class="tL ellipsis" title="([^"]*)"', tr)
        out.append({'id': rc.group(1), 'code': code.group(1), 'name': html.unescape(name.group(1)) if name else '',
                    'name_en': None, 'filed': _iso(date[0]) if date else None, 'fy': fy_from_title(nm),
                    'url': f'{DART}/dsaf001/main.do?rcpNo={rc.group(1)}', 'stock_code': None,
                    'corp_cls': _CLS.get(cls.group(1)) if cls else None, 'report_nm': nm,
                    'amended': nm.startswith('['), 'filer': html.unescape(filer.group(1)) if filer else None,
                    'consolidated': 'tagCom_yeon' in tr})
    m = re.search(r'pageInfo">\s*\[(\d+)/(\d+)\]', text)
    return out, int(m.group(2)) if m else 1


def list_reports(http, since, until, key=None, corp_cls=None):
    """Annual reports (사업보고서) filed between two ISO dates, newest first as DART gives them."""
    key = key if key is not None else os.environ.get('DART_API_KEY')
    seen, out = set(), []
    if key:
        names = corp_codes(http, key)
        ok = True
        for a, b in _windows(since, until):
            page, total = 1, 1
            while page <= total:
                params = {'crtfc_key': key, 'bgn_de': _ymd(a), 'end_de': _ymd(b), 'pblntf_ty': 'A',
                          'pblntf_detail_ty': 'A001', 'last_reprt_at': 'Y', 'page_no': str(page), 'page_count': '100'}
                if corp_cls:
                    params['corp_cls'] = corp_cls
                raw = _get(http, f'{API}/list.json', params)
                if not raw:
                    ok = False
                    break
                try:
                    reps, total, status = parse_list_json(raw, names)
                except ValueError:
                    ok = False
                    break
                if status == '013':
                    break
                if status != '000':
                    print(f'asia_kr: list.json status {status}', file=sys.stderr)
                    ok = False
                    break
                for r in reps:
                    if r['id'] not in seen:
                        seen.add(r['id'])
                        out.append(r)
                page += 1
            if not ok:
                break
        if ok:
            return out
    # no key (or the API refused): the public search
    for a, b in _windows(since, until, days=30):
        page, total = 1, 1
        while page <= total and page <= 200:
            raw = _get(http, f'{DART}/dsab007/detailSearch.ax',
                       {'currentPage': str(page), 'maxResults': '100', 'publicType': 'A001',
                        'startDate': _ymd(a), 'endDate': _ymd(b)})
            if not raw:
                break
            reps, total = parse_search_html(_decode(raw))
            for r in reps:
                if r['id'] not in seen and (not corp_cls or r['corp_cls'] == corp_cls):
                    seen.add(r['id'])
                    out.append(r)
            page += 1
    return out


# ----------------------------------------------------------------------------------------------- reading a report

def viewer_nodes(text):
    """The table of contents in a dsaf001/main.do page → [{'text','rcpNo','dcmNo','eleId','offset','length','dtd'}]."""
    out = []
    for m in re.finditer(r"node\d+\['text'\]\s*=\s*\"(.*?)\";(.*?)(?=node\d+\['text'\]|$)", text, re.S):
        body = m.group(2)
        f = dict(re.findall(r"\['(rcpNo|dcmNo|eleId|offset|length|dtd)'\]\s*=\s*\"([^\"]*)\"", body))
        if f.get('dcmNo') and f.get('eleId'):
            f['text'] = html.unescape(m.group(1)).strip()
            out.append(f)
    return out


def pick_nodes(nodes):
    """The sections worth reading: everything under 'II. 사업의 내용' and the summary financial information."""
    pick, inside = [], False
    for n in nodes:
        t = re.sub(r'\s+', ' ', n['text'])
        if re.match(r'^II\.\s*사업', t):
            inside = True
            pick.append(n)
            continue
        if re.match(r'^(III|IV|V|VI|VII|VIII|IX|X|XI|XII)\.', t):
            inside = False
        if (inside and not re.search(r'위험관리|파생거래', t)) or '요약재무' in t or '요약 재무' in t:
            pick.append(n)
    # read the children of II rather than II itself when it has them (the parent's text holds them all)
    if len(pick) > 1 and re.match(r'^II\.', pick[0]['text']):
        kids = [n for n in pick[1:] if not ('요약재무' in n['text'] or '요약 재무' in n['text'])]
        if kids:
            pick = pick[1:]
    return pick


def _read_viewer(http, rcept_no):
    page = _get(http, f'{DART}/dsaf001/main.do', {'rcpNo': rcept_no})
    if not page:
        return None
    parts, page = [], _decode(page)
    title = re.search(r'<title>\s*([^/<]+?)\s*/', page)
    for n in pick_nodes(viewer_nodes(page)):
        h = _get(http, f'{DART}/report/viewer.do', {'rcpNo': n.get('rcpNo') or rcept_no, 'dcmNo': n['dcmNo'],
                                                    'eleId': n['eleId'], 'offset': n.get('offset', ''),
                                                    'length': n.get('length', ''), 'dtd': n.get('dtd') or 'dart4.xsd'})
        if h:
            t = _decode(h)
            m = re.search(r'(?is)<body[^>]*>(.*)</body>', t)
            parts.append(m.group(1) if m else t)
    if not parts:
        return None
    name = f'<company-name>{html.escape(title.group(1))}</company-name>\n' if title else ''
    return '<html><body>\n' + name + '\n'.join(parts) + '\n</body></html>'


def read_report(http, rep, key=None):
    key = key if key is not None else os.environ.get('DART_API_KEY')
    rc = rep.get('id') or rep.get('rcept_no')
    if not rc:
        return None
    meta = {k: rep.get(k) for k in ('code', 'name', 'name_en', 'fy')}
    meta['rcept_no'] = rc
    doc = None
    if key:
        raw = _get(http, f'{API}/document.xml', {'crtfc_key': key, 'rcept_no': rc})
        if raw and raw[:2] == b'PK':
            doc = raw
    if doc is None:
        doc = _read_viewer(http, rc)
    if not doc:
        return None
    out = parse(doc, **meta)
    out['id'] = rc
    out['url'] = rep.get('url') or f'{DART}/dsaf001/main.do?rcpNo={rc}'
    return out


# ----------------------------------------------------------------------------------------------- normalising

def _decode(b):
    if isinstance(b, str):
        return b
    head = b[:400].decode('ascii', 'replace')
    m = re.search(r'''(?:encoding|charset)\s*=\s*["']?([\w-]+)''', head, re.I)
    enc = (m.group(1).lower() if m else 'utf-8').replace('ks_c_5601-1987', 'cp949').replace('euc-kr', 'cp949')
    for e in (enc, 'utf-8', 'cp949'):
        try:
            return b.decode(e)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode('utf-8', 'replace')


def _unzip(b, rcept_no=None):
    z = zipfile.ZipFile(io.BytesIO(b))
    xs = [n for n in z.namelist() if n.lower().endswith('.xml')] or z.namelist()
    main = [n for n in xs if rcept_no and os.path.basename(n) == f'{rcept_no}.xml']
    main = main or [n for n in xs if '_' not in os.path.basename(n)]
    name = main[0] if main else max(xs, key=lambda n: z.getinfo(n).file_size)
    return _decode(z.read(name))


def _clean(s):
    s = s.replace('\xa0', ' ').replace('　', ' ').replace('​', '')
    s = re.sub(r'<[^>]+>', ' ', s)  # markup that arrived as text (RCDATA titles)
    return re.sub(r'\s+', ' ', s).strip()


_BREAK = {'p', 'br', 'div', 'li', 'pgbrk', 'section-1', 'section-2', 'section-3', 'h1', 'h2', 'h3', 'h4',
          'cover-title', 'part', 'library', 'document-name', 'company-name'}
_CELL = {'td', 'th', 'te', 'tu'}


class _Norm(HTMLParser):
    """Viewer HTML or dart4 XML → blocks: ('h', line) headings, ('p', [lines]) paragraphs, ('table', grid)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.meta = [], {}
        self.lines, self.buf = [], []
        self.depth = 0  # table nesting
        self.rows = None
        self.cell = None
        self.title = None
        self.skip = 0
        self.grab = None

    # paragraphs
    def _flush_line(self):
        t = _clean(''.join(self.buf))
        self.buf = []
        if t:
            self.lines.append(t)

    def _flush_par(self):
        self._flush_line()
        if self.lines:
            self.blocks.append(('p', self.lines))
        self.lines = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag in ('script', 'style'):
            self.skip += 1
            return
        if tag == 'company-name':
            self.grab = 'name'
            if a.get('aregcik'):
                self.meta['code'] = a['aregcik']
        if tag == 'table':
            if self.depth == 0:
                self._flush_par()
                self.rows = []
            self.depth += 1
            return
        if self.depth:
            if self.depth == 1 and tag == 'tr':
                self.rows.append([])
            elif self.depth == 1 and tag in _CELL:
                if not self.rows:
                    self.rows.append([])
                self.cell = {'t': [], 'r': _int(a.get('rowspan')), 'c': _int(a.get('colspan')), 'h': tag == 'th'}
            elif tag in ('br', 'p') and self.cell is not None:
                self.cell['t'].append(' ')
            return
        if tag == 'title':
            self._flush_par()
            self.title = []
            return
        if tag in _BREAK:
            if tag == 'br':
                self._flush_line()
            else:
                self._flush_par()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('br', 'pgbrk', 'col', 'img', 'image'):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
            return
        if tag == 'company-name':
            self.grab = None
        if tag == 'table' and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self._end_cell()
                grid = _expand(self.rows)
                if grid:
                    self.blocks.append(('table', grid))
                self.rows = None
            return
        if self.depth:
            if self.depth == 1 and tag in _CELL:
                self._end_cell()
            return
        if tag == 'title' and self.title is not None:
            t = _clean(''.join(self.title))
            self.title = None
            if t:
                self.blocks.append(('h', t))
            return
        if tag in _BREAK and tag != 'br':
            self._flush_par()

    def _end_cell(self):
        if self.cell is not None and self.rows is not None:
            c = self.cell
            self.rows[-1].append((_clean(''.join(c['t'])), c['r'], c['c'], c['h']))
        self.cell = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.grab == 'name':
            self.meta['name'] = (self.meta.get('name', '') + data).strip()
        if self.depth:
            if self.cell is not None:
                self.cell['t'].append(data)
            return
        if self.title is not None:
            self.title.append(data)
            return
        self.buf.append(data)

    def close(self):
        super().close()
        self._flush_par()


def _int(v):
    try:
        return max(1, min(100, int(str(v).strip())))
    except (TypeError, ValueError):
        return 1


def _expand(rows):
    """Rows of (text, rowspan, colspan, is_header) → a rectangular grid of {'t','h'} with spans repeated."""
    grid, pend = [], {}
    for row in rows:
        out, col = [], 0
        cells = list(row)
        while cells or pend.get(col):
            if pend.get(col):
                t, h, left = pend[col]
                out.append({'t': t, 'h': h})
                pend[col] = (t, h, left - 1) if left > 1 else None
                col += 1
                continue
            t, r, c, h = cells.pop(0)
            for _ in range(c):
                out.append({'t': t, 'h': h})
                if r > 1:
                    pend[col] = (t, h, r - 1)
                col += 1
        if any(x['t'] for x in out):
            grid.append(out)
    w = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend({'t': '', 'h': False} for _ in range(w - len(r)))
    return grid


def normalise(doc, rcept_no=None):
    """Bytes or text (viewer HTML, dart4 XML, or the document.xml zip) → (blocks, meta)."""
    if isinstance(doc, (bytes, bytearray)):
        doc = _unzip(bytes(doc), rcept_no) if doc[:2] == b'PK' else _decode(bytes(doc))
    p = _Norm()
    p.feed(doc)
    p.close()
    return p.blocks, p.meta


# ----------------------------------------------------------------------------------------------- numbers

_UNIT = {'조원': 1e12, '억원': 1e8, '백만원': 1e6, '천원': 1e3, '원': 1.0}


def unit_of(text):
    m = re.search(r'단위\s*[:：]?\s*(?:US\$|USD)?\s*(조\s*원|억\s*원|백만\s*원|천\s*원|원)', text or '')
    return _UNIT[m.group(1).replace(' ', '')] if m else None


def num(s):
    """'1,024,285' → 1024285.0; '(1,234)' / '△1,234' → negative; anything else → None."""
    t = (s or '').strip().replace(' ', '')
    m = re.fullmatch(r'([\(△▲-]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?', t)
    if not m:
        return None
    v = float(m.group(2).replace(',', '') + (m.group(3) or ''))
    return -v if m.group(1) in ('(', '△', '-') else v


def pct(s):
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*%\s*', s or '')
    return float(m.group(1)) / 100 if m else None


def money(s):
    """'14,835,862백만원' → 1.4835862e13; '333조 6,059억원' → 3.336059e14."""
    s = (s or '').replace(' ', '')
    m = re.fullmatch(r'(?:(\d[\d,]*)조)?(?:(\d[\d,]*(?:\.\d+)?)(억원|백만원|천원|원|억))?', s)
    if not m or not (m.group(1) or m.group(2)):
        return None
    v = float(m.group(1).replace(',', '')) * 1e12 if m.group(1) else 0.0
    if m.group(2):
        u = m.group(3) if m.group(3) != '억' else '억원'
        v += float(m.group(2).replace(',', '')) * _UNIT[u]
    return v


# ----------------------------------------------------------------------------------------------- names

_GENERIC = re.compile(
    r'업체|업계|기업|회사들|고객|매출|매입|비중|수준|제조사|제조업|국내외|글로벌|다수|각국|등지|관련|완성차|공급사|공급업체|'
    r'거래선|거래처|대리점|소비자|정부|당사|연결회사|종속회사|계열사|개사|수요처|판매처|매출처|구매처|시장|제품|부품|원재료|'
    r'세계|유수|최종|기타|합\s*계|소\s*계|^계$|^총|^-+$|^구\s*분$|해당|각각|대한|있습니다|있으며|하여|하고|이며|입니다|^등$|'
    r'^(?:국내|해외|미국|중국|일본|한국|유럽|독일|대만|동남아)$|^OEM$|자동차\s*OEM|Set\s*업체|않습니다|없습니다|존재|'
    r'측면|안정성|관점|경우|과정|공장|국가|제\s*\d+\s*기|\d{4}\s*년|^\[.*\]$|자산|부채|자본|이익|손실')
_ANON = re.compile(r'^(?:외부\s*고객|고객|고객사|거래처|매출처|매입처)\s*[0-9A-Za-z가-하]{1,2}$|'
                   r'^["“”\'‘’]?[A-Z가-하]["“”\'‘’]?\s*사(?:\s*\(社\))?$')
_CORP = re.compile(r'㈜|\(주\)|\(株\)|주식회사|\(유\)|유한회사')


def clean_label(t):
    t = re.sub(r'\(\s*\*+\s*\)|\*+|주\s*\d+\)|\[\s*\d+\s*\]', '', t)
    t = re.sub(r'\(\s*["“][^)]*\)', '', t)          # ("BMW") aliases
    t = re.sub(r'\((?:알파벳|가나다|abc)?\s*순\)', '', t)
    t = _CORP.sub('', t)
    t = re.sub(r'\s+', ' ', t).strip(' ,.;:·ㆍ-')
    return t


def is_name(t):
    if not t or len(t) > 60 or len(t) < 2 and not re.match(r'[A-Z]', t or ''):
        return False
    if _ANON.match(t):
        return True
    if re.search(r'\d+(?:\.\d+)?\s*%|\d+\s*개|^\d[\d,\.]*$|\([^()]*,[^()]*\)', t):
        return False
    if _GENERIC.search(t):
        return False
    if len(t.split()) > 6:
        return False
    return True


_PROTECT = re.compile(r'(?i),\s*(?=(?:inc|ltd|llc|limited|corp|co\.|s\.a|ag|gmbh|n\.v|plc|pte)\b)')


def split_names(seg):
    """'Qualcomm, 삼성전기㈜ 등' → ['Qualcomm', '삼성전기']."""
    seg = re.sub(r'\s*(?:와|과|및)\s*그\s*(?:종속|계열)\s*회사(?:들)?', '', seg)
    seg = re.sub(r'\((?:알파벳|가나다|abc)?\s*순\)', '', seg)
    seg = re.sub(r'\(\s*["“][^)]*\)', '', seg)
    seg = re.sub(r'(?i)\bco\.\s*,\s*ltd', 'Co.@ Ltd', seg)
    seg = _PROTECT.sub('@ ', seg)
    seg = re.sub(r'\([^()]*\)', lambda m: m.group(0).replace(',', '@').replace(' ', '\x02'), seg)
    parts = re.split(r'\s*[,、;ㆍ·]\s*|\s+및\s+|\s+또는\s+|\s+등\s*(?=\S)|\s*등\s*$|(?<=업체|기업|회사|고객)(?:와|과|들과|들와)\s+', seg)
    out = []
    for p in parts:
        p = (p or '').replace('@', ',').replace('\x02', ' ').strip()
        p = re.sub(r'^(?:또한|그리고|및)\s+', '', p)
        p = re.sub(r'\s*등$', '', p)
        p = clean_label(p)
        if is_name(p) and p not in out:
            out.append(p)
    return out


def _key(label):
    return re.sub(r'[\s\.\,㈜]', '', re.sub(r'\([^()]*\)', '', label)).lower()


# ----------------------------------------------------------------------------------------------- the reader

_SENT = re.compile(r'(?<=[다요음함됨임])\.\s+|(?<=[다요음함됨임])\.$')
_HEAD = re.compile(r'^\s*(?:[IVX]+\.|\d+(?:-\d+)*\.|[가-하]\.|\(\d+\)|\d+\)|[①-⑳]|\([가-하]\)|[가-하]\))\s*\S')
_CUST = re.compile(r'주요\s*(?:매출처|고객사?|판매처|수요처)|주요\s*거래처')
_SUP_VERB = re.compile(r'공급받|매입하|매입을|구매하|구입하|조달하|수입하|매입하고|공급\s*받')


def _strip_paren(s):
    """Drop prior-year asides like '(2024년: 14,281,844백만원)' that would muddle in-order pairing."""
    return re.sub(r'\([^()]*(?:\d{4}\s*년|전기|전년)[^()]*\)', '', s)


def _row(role, label, sentence, year, amount=None, share=None, **extra):
    share = round(share, 6) if share is not None else None
    r = {'role': role, 'label': label, 'amount': amount, 'share': share, 'year': year,
         'sentence': (sentence or '')[:400]}
    if _ANON.match(label):
        r['anonymous'] = True
    r.update({k: v for k, v in extra.items() if v is not None})
    return r


class _Reader:
    def __init__(self, blocks, year):
        self.blocks, self.year = blocks, year
        self.rows, self.conc = [], {}

    # ---- concentration
    def concentration(self, s):
        t = _strip_paren(s)
        for m in re.finditer(r'(?:주요|상위)\s*(\d+)\s*(?:대|개)\s*(?:사\s*)?(매출처|고객|거래처|판매처|매입처|공급\s*(?:사|업체)|구매처)'
                             r'[^%]*?(\d+(?:\.\d+)?)\s*%(?!\s*(?:이상|이하|미만|초과))', t):
            n, word, v = int(m.group(1)), m.group(2), float(m.group(3)) / 100
            role = 'purchases' if re.search(r'매입|공급|구매', word) else 'sales'
            if word == '거래처' and self.ctx == 'materials':
                role = 'purchases'
            self.conc.setdefault(f'top{n}_{role}', v)
        m = re.search(r'단일\s*(?:고객|거래처|매출처)[^.]*?(\d[\d,]*(?:\.\d+)?\s*(?:조\s*\d[\d,]*\s*)?(?:억원|백만원|천원|원))', t)
        if m:
            self.conc.setdefault('top1_sales_amount', money(m.group(1)))

    # ---- customers from a sentence
    def customers(self, s, ctx):
        t = _strip_paren(s)
        names = []
        m = re.search(r'주요\s*(?:매출처|고객사?|판매처|수요처|거래처)(?:로는|으로는|는|은|로|으로)\s+(.+)', t)
        if m and not ('거래처' in m.group(0) and ctx == 'materials'):
            seg = m.group(1)
            seg = re.sub(r'^.*?(?:업체|기업|회사|고객사?)(?:로서|로|이며|인)\s+(?=\S)', '', seg, count=1) \
                if re.match(r'^[^,]*?(?:업체|기업|회사|고객사?)(?:로서|로|이며|인)\s', seg) else seg
            end = re.search(r'\s*(?:등\s*)?(?:(?:이|가)\s*있(?:으며|습니다|고)|입니다|이며|이고|이다|으로\s|로\s|을|를|에\s|에게|\.|$)', seg)
            names = split_names(seg[:end.start()] if end else seg)
        anon = []
        for a in re.finditer(r'["“”]([가-하A-Z])["“”]\s*사(?:\s*\(社\))?', t):
            lab = f'"{a.group(1)}"사'
            if lab not in anon:
                anon.append(lab)
        if anon and not names and re.search(r'고객|매출처|거래처', t):
            names = anon
        if not names:
            return
        amounts, shares = [], []
        k = t.find('각각')
        if k >= 0:
            tail = t[k:]
            amounts = [money(x) for x in re.findall(r'\d[\d,]*(?:\.\d+)?\s*(?:억원|백만원|천원|조원)', tail)]
            shares = [float(x) / 100 for x in re.findall(r'(\d+(?:\.\d+)?)\s*%(?!\s*(?:이상|이하|미만|초과))', tail)]
        elif len(names) == 1:
            rest = t[m.end(1) - len(m.group(1)):] if m else t
            ps = [x for x in re.finditer(r'(\d+(?:\.\d+)?)\s*%(?!\s*(?:이상|이하|미만|초과))', rest)
                  if not re.search(r'(?:주요|상위)\s*\d+\s*(?:대|개)', rest[:x.start()])]
            if ps:
                shares = [float(ps[0].group(1)) / 100]
        elif len(names) > 1 and not re.search(r'(?:주요|상위)\s*\d+\s*(?:대|개)', t):
            ps = re.findall(r'(?:매출\s*)?비중은?[^%]*?(\d+(?:\.\d+)?)\s*%(?!\s*(?:이상|이하|미만|초과))', t)
            if ps:
                self.conc.setdefault('named_sales', float(ps[0]) / 100)
        for i, n in enumerate(names):
            amt = amounts[i] if len(amounts) == len(names) else None
            sh = shares[i] if len(shares) == len(names) else None
            self.add(_row('customer', n, s, self.year, amt, sh))

    # ---- suppliers from a sentence
    def suppliers(self, s, ctx):
        t = _strip_paren(s)
        found = []
        if _SUP_VERB.search(t):
            for m in re.finditer(r'\s*(?:등\s*)?(?:에서|으로부터|로부터)(?=[\s,]|$)', t):
                after = t[m.end():m.end() + 40]
                if not (_SUP_VERB.search(after) or after.startswith(',')):
                    continue        # '…로부터 책임을 위임받아', '측면에서 차질이' — not a purchase
                pre = t[:m.start()]
                cut = max([x.end() for x in re.finditer(r'(?:[을를은는]\s|또한\s|으며,?\s|하고,?\s|하며,?\s|'
                                                        r'(?<=[가-힣A-Za-z\)])(?:으로|로)\s|, (?=[A-Z가-힣]+\s*(?:부문|사업)))', pre)] or [0])
                seg = pre[cut:]
                last = re.split(r'\s*[,、;ㆍ·]\s*|\s+및\s+|\s+등\s+', seg)[-1]
                if not is_name(clean_label(last)):
                    continue        # '… 등 완성차 업체로부터', '주요 공급사로부터' — the list ends in a description
                found += split_names(seg)
        pat = r'(?:공급사|공급업체|매입처|구매처|공급처)(?:는|은|로는|으로는)\s+(.+?)(?:\s*등)?(?:이\s*있|가\s*있|입니다|이며|이고|으로|\.|$)'
        if ctx == 'materials':
            pat = pat.replace('공급처)', '공급처|거래처)')
        else:
            pat = r'(?:주요|당사의|회사의)\s*' + pat     # elsewhere 'FPCB 공급업체로는 …' lists the industry, not our suppliers
        for m in re.finditer(pat, t):
            found += split_names(m.group(1))
        for n in found:
            self.add(_row('supplier', n, s, self.year))

    # ---- tables
    def table(self, grid, unit, ctx, zone):
        hdr_n = 0
        for r in grid:
            if any(num(c['t']) is not None or pct(c['t']) is not None or
                   re.fullmatch(r'\s*[\d,\.]+\s*\(\s*[\d\.]+\s*%\s*\)\s*', c['t']) for c in r):
                break
            hdr_n += 1
        th = 0
        while th < len(grid) and all(c['h'] for c in grid[th]):
            th += 1
        if th and th < len(grid):
            hdr_n = min(hdr_n, th) if hdr_n else th     # <TH> rows are the header when the body has no plain numbers
        if hdr_n == 0 or hdr_n >= len(grid):
            return
        heads = [' '.join(dict.fromkeys(grid[i][j]['t'] for i in range(hdr_n)
                                        if grid[i][j]['t'] and not (unit_of(grid[i][j]['t']) and len(grid[i][j]['t']) < 40)))
                 for j in range(len(grid[0]))]
        all_head = ' '.join(heads)
        unit = unit_of(' '.join(c['t'] for i in range(hdr_n) for c in grid[i])) or unit
        unit = unit_of(all_head) or unit
        sup_col = next((j for j, h in enumerate(heads) if re.search(r'매입처|구매처|공급처|공급업체|공급사|업체명', h)), None)
        if sup_col is None and re.search(r'매입', all_head):
            sup_col = next((j for j, h in enumerate(heads) if re.fullmatch(r'비\s*고', h)), None)
        if sup_col is not None and (ctx == 'materials' or re.search(r'매입|구매', all_head)):
            return self.supplier_table(grid, hdr_n, heads, sup_col, unit)
        firsts = [r[0]['t'] for r in grid[hdr_n:]]
        if zone and ctx != 'materials' and (re.search(r'매출처|고객|거래처|매출\s*비중|비중', all_head)
                                            or any(_ANON.match(x) for x in firsts + heads)):
            return self.customer_table(grid, hdr_n, heads, unit)

    def supplier_table(self, grid, hdr_n, heads, sup_col, unit):
        def col(p):
            return next((j for j, h in enumerate(heads) if re.search(p, h) and j != sup_col), None)
        item_c = col(r'품\s*목|원재료|품\s*명')
        seg_c = col(r'사업\s*부문|^부\s*문|부\s*문$')
        amt_c = col(r'매입액|매입\s*금액|투입액|금액')
        sh_c = col(r'비\s*중|비\s*율')
        for r in grid[hdr_n:]:
            cells = [c['t'] for c in r]
            names = split_names(cells[sup_col])
            if not names:
                continue
            amt = sh = None
            if amt_c is not None:
                raw = cells[amt_c]
                mm = re.match(r'\s*([\d,\.]+)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)', raw)
                if mm:
                    amt, sh = num(mm.group(1)), float(mm.group(2)) / 100
                else:
                    amt = num(raw)
                if amt is not None and unit:
                    amt *= unit
                elif amt is not None:
                    amt = None
            if sh is None and sh_c is not None:
                sh = pct(cells[sh_c])
            sh = round(sh, 6) if sh is not None else None
            item = {'item': cells[item_c] if item_c is not None else None,
                    'segment': cells[seg_c] if seg_c is not None and seg_c != item_c else None,
                    'amount': amt, 'share': sh}
            item = {k: v for k, v in item.items() if v not in (None, '')}
            sent = ' | '.join(dict.fromkeys(c for c in cells if c))
            for n in names:
                self.add(_row('supplier', n, sent, self.year, items=[item] if item else None))

    def customer_table(self, grid, hdr_n, heads, unit):
        body = grid[hdr_n:]
        first = [r[0]['t'] for r in body]
        if any(re.search(r'매출액|비중|비율|금액', x) for x in first):      # customers across the columns
            names = [(j, heads[j]) for j in range(1, len(heads))]
            for j, h in names:
                lab = clean_label(h.split(' ')[-1] if _ANON.match(h.split(' ')[-1]) else h)
                if not is_name(lab):
                    continue
                amt = sh = None
                for r in body:
                    v = r[j]['t']
                    if re.search(r'비중|비율', r[0]['t']):
                        sh = pct(v) if sh is None else sh
                    elif re.search(r'매출|금액', r[0]['t']):
                        a = num(v)
                        amt = a * unit if a is not None and unit and amt is None else amt
                self.add(_row('customer', lab, ' | '.join([h] + [f"{r[0]['t']} {r[j]['t']}" for r in body]),
                              self.year, amt, sh))
            return
        amt_c = next((j for j, h in enumerate(heads) if j and re.search(r'매출액|금액', h)), None)
        for r in body:
            lab = clean_label(r[0]['t'])
            if not is_name(lab):
                continue
            cells = [c['t'] for c in r]
            sh = next((pct(c) for c in cells[1:] if pct(c) is not None), None)
            amt = None
            if amt_c is not None and num(cells[amt_c]) is not None and unit:
                amt = num(cells[amt_c]) * unit
            elif unit and sh is None:
                v = next((num(c) for c in cells[1:] if num(c) is not None), None)
                amt = v * unit if v is not None else None
            self.add(_row('customer', lab, ' | '.join(c for c in cells if c), self.year, amt, sh))

    # ---- merge
    def add(self, row):
        k = (row['role'], _key(row['label']))
        for r in self.rows:
            if (r['role'], _key(r['label'])) == k:
                for f in ('amount', 'share'):
                    if r[f] is None and row[f] is not None:
                        r[f] = row[f]
                if row.get('items'):
                    r.setdefault('items', [])
                    r['items'] += [i for i in row['items'] if i not in r['items']]
                return
        self.rows.append(row)

    # ---- walk
    def run(self):
        self.ctx, zone, unit, unit_age, active = None, 0, None, 0, True
        for kind, val in self.blocks:
            lines = [val] if kind == 'h' else val if kind == 'p' else []
            if kind == 'table':
                text = ' '.join(c['t'] for r in val for c in r)
                if len(val) <= 2 and len(text) < 80 and unit_of(text):
                    unit, unit_age = unit_of(text), 0
                    continue
                if active:
                    self.table(val, unit if unit_age < 4 else None, self.ctx, zone > 0)
                zone = max(0, zone - 1)
                unit_age += 1
                continue
            chunk = []
            for ln in lines + [None]:
                if ln is not None:
                    if unit_of(ln) and len(ln) < 60:
                        unit, unit_age = unit_of(ln), 0
                    if re.match(r'^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\.\s*\S', ln):
                        active = bool(re.match(r'^(?:I|II)\.', ln))
                    is_head = kind == 'h' or (_HEAD.match(ln) and len(ln) <= 60)
                    if not is_head:
                        chunk.append(ln)
                        continue
                # a heading (or the end of the paragraph): read the text gathered so far, then the heading
                if chunk and active:
                    zone = self.text(' '.join(chunk), zone)
                chunk = []
                if ln is None:
                    break
                if re.search(r'원재료|매입|구매', ln):
                    self.ctx = 'materials'
                elif re.search(r'매출|판매|고객|수주', ln):
                    self.ctx = 'sales'
                elif re.search(r'생산|설비|가동|위험|파생|연구|계약|재무|투자|기타|개요|제품|요약', ln):
                    self.ctx = None
                zone = 3 if self.ctx == 'sales' and re.search(r'매출처|고객|거래처', ln) else 0
                if len(ln) > 30 and kind != 'h' and active:   # a heading-like line that carries a sentence
                    zone = self.text(ln, zone)
        return self

    def text(self, t, zone):
        if self.ctx != 'materials' and (_CUST.search(t) or re.search(r'외부\s*고객', t)):
            zone = 3
        for s in [x.strip() for x in _SENT.split(t) if x and x.strip()]:
            self.concentration(s)
            if self.ctx != 'materials' and (_CUST.search(s) or (self.ctx == 'sales' and re.search(r'["“”][가-하A-Z]["“”]\s*사', s))):
                self.customers(s, self.ctx)
            elif _SUP_VERB.search(s) or re.search(r'(?:공급사|공급업체|매입처|구매처)(?:는|은|로는)', s) or \
                    (self.ctx == 'materials' and re.search(r'거래처(?:는|로는)', s)):
                self.suppliers(s, self.ctx)
        return zone


def _table_fy(grid):
    """The latest period end named in a table's cells ('2025년 12월말', '2025년 1월~12월', '2025.12.31')."""
    ends = []
    for r in grid:
        for c in r:
            t = c['t']
            for m in re.finditer(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*말', t):
                ends.append((int(m.group(1)), int(m.group(2))))
            for m in re.finditer(r'(\d{4})\s*년\s*\d{1,2}\s*월?\s*[~∼-]\s*(?:\d{4}\s*년\s*)?(\d{1,2})\s*월', t):
                ends.append((int(m.group(1)), int(m.group(2))))
            for m in re.finditer(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', t):
                ends.append((int(m.group(1)), int(m.group(2))))
    ends = [e for e in ends if 1 <= e[1] <= 12]
    return _month_end(*max(ends)) if ends else None


def revenue_from(blocks):
    """매출액 (or 영업수익) of the latest year from 요약연결재무정보, else 요약재무정보 → (won, fy ISO or None)."""
    best = {}
    mode, unit, last_fy = None, None, None
    for kind, val in blocks:
        if kind in ('p', 'h'):
            for ln in ([val] if kind == 'h' else val):
                if re.search(r'요약\s*연결\s*재무', ln):
                    mode = 'cons'
                elif re.search(r'요약\s*(?:별도\s*)?재무', ln):
                    mode = 'sep'
                if unit_of(ln):
                    unit = unit_of(ln)
            continue
        text = ' '.join(c['t'] for r in val for c in r)
        if unit_of(text) and len(val) <= 2 and len(text) < 80:
            unit = unit_of(text)
            continue
        if not mode or mode in best:
            continue
        u = unit_of(text[:200]) or unit
        fy = _table_fy(val) or last_fy
        last_fy = fy
        for r in val:
            lab = re.sub(r'[\sㆍ·\.\-\[\]]', '', r[0]['t'])
            if re.fullmatch(r'(?:매출액|영업수익|수익\(매출액\)|매출|매출액\(영업수익\)|영업수익\(매출액\))', lab):
                v = next((num(c['t']) for c in r[1:] if num(c['t']) is not None), None)
                if v is not None and u:
                    best[mode] = (v * u, fy)
                break
    return best.get('cons') or best.get('sep') or (None, None)


def parse(doc, **meta):
    """Viewer HTML / dart4 XML / document.xml zip → {'code','name','name_en','fy','currency','revenue','rows','concentration'}."""
    blocks, found = normalise(doc, meta.get('rcept_no'))
    revenue, fy_doc = revenue_from(blocks)
    fy = meta.get('fy') or fy_doc
    year = int(fy[:4]) if fy else None
    rd = _Reader(blocks, year).run()
    conc = {'top1_sales': None, 'top5_sales': None, 'top1_purchases': None, 'top5_purchases': None}
    conc.update(rd.conc)
    cust_shares = [r['share'] for r in rd.rows if r['role'] == 'customer' and r['share'] is not None]
    if conc.get('top1_sales') is None and cust_shares:
        conc['top1_sales'] = max(cust_shares)
    if revenue:
        for r in rd.rows:
            if r['role'] == 'customer' and r['amount'] and r['share'] is None:
                r['share'] = round(r['amount'] / revenue, 4)
                r['share_derived'] = True
        if conc.get('top1_sales') is None and conc.get('top1_sales_amount'):
            conc['top1_sales'] = round(conc['top1_sales_amount'] / revenue, 4)
        if conc.get('top1_sales') is None:
            amts = [r['share'] for r in rd.rows if r['role'] == 'customer' and r.get('share_derived')]
            if amts:
                conc['top1_sales'] = max(amts)
    conc = {k: (round(v, 6) if isinstance(v, float) and v < 10 else v) for k, v in conc.items()}
    return {'code': meta.get('code') or found.get('code'), 'name': meta.get('name') or found.get('name'),
            'name_en': meta.get('name_en'), 'fy': fy, 'currency': CURRENCY, 'revenue': revenue,
            'rows': rd.rows, 'concentration': conc}


# ----------------------------------------------------------------------------------------------- command line

class _Http:
    def get(self, url, params=None, headers=None):
        import urllib.parse
        import urllib.request
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f'asia_kr: {url[:120]}: {e}', file=sys.stderr)
            return None


def main(argv):
    if len(argv) >= 3 and argv[0] == 'list':
        print(json.dumps(list_reports(_Http(), argv[1], argv[2]), ensure_ascii=False, indent=1))
    elif len(argv) >= 2 and argv[0] == 'read':
        print(json.dumps(read_report(_Http(), {'id': argv[1]}), ensure_ascii=False, indent=1))
    elif len(argv) >= 2 and argv[0] == 'parse':
        with open(argv[1], 'rb') as f:
            print(json.dumps(parse(f.read()), ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
