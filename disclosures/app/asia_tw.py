"""Taiwan: major customers and suppliers from the annual report (股東會年報).

Every TWSE / TPEx company's annual report has, in 營運概況, the mandated table
「最近二年度任一年度中曾占進(銷)貨總額百分之十以上之客戶名稱及其進(銷)貨金額與比例」:
one block for sales (customers) and one for purchases (suppliers), each with a column
group per year (名稱 / 金額 / 占全年度銷貨淨額比率 / 與發行人之關係), usually the last two full
years plus, in many reports, the current year to date.  No MOPS JSON or XBRL field carries
it (the IFRS note 「重要客戶資訊」 has only customers, anonymised, without suppliers), so the
path is: the annual-report PDF from doc.twse.com.tw (t57sb01, mtype=F, 股東會年報 F04)
→ ``pdftotext -layout`` → the table parser below.

Interface (shared by the four Asian market modules):
    list_reports(http, since, until, key=None) -> [{'id','code','name','name_en','filed','fy','url', ...}]
    read_report(http, rep, key=None) -> {'code','name','name_en','fy','currency','revenue','rows','concentration'} | None
    parse(doc_bytes_or_text, **meta) -> same dict (offline)

Amounts are converted to TWD from the table's 單位 (元 / 千元 / 仟元 / 萬元 / 百萬元 / 佰萬元);
shares are fractions; only the latest full fiscal year is kept (year-to-date columns such
as 「115 年度截至第一季止」 are skipped).  ``revenue`` is the 銷貨淨額 / 合計 row of the sales
table for that year (the consolidated net sales the percentages are computed on), else None.
"""
import html as _html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date
from urllib.parse import urlencode

MARKET = 'tw'
CURRENCY = 'TWD'

TWSE_LIST = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'      # 上市公司基本資料 (英文簡稱)
TPEX_LIST = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'   # 上櫃公司基本資料 (Symbol)
DOC = 'https://doc.twse.com.tw/server-java/t57sb01'
DOC_ROOT = 'https://doc.twse.com.tw'

MIN_INTERVAL = 0.34          # <= 3 requests / second
SLEEP = time.sleep           # tests replace it
_last = [0.0]

# ---------------------------------------------------------------- polite fetching

_BLOCK_MARKS = ('FOR SECURITY REASONS', '因為安全性考量', '查詢過於頻繁', '查詢過量', 'Overrun',
                '頁面無法執行', 'THE PAGE CANNOT BE ACCESSED', '請稍後再試')


def blocked(body):
    """True when MOPS / doc.twse answered with its throttle or WAF page instead of data."""
    if not body:
        return False
    head = body[:4000] if isinstance(body, (bytes, bytearray)) else body[:4000].encode('utf-8', 'ignore')
    txt = _decode(head)
    return any(m in txt for m in _BLOCK_MARKS)


def _fetch(http, url, data=None, tries=4):
    """GET (or POST when data is given) with <=3 req/s, retries on failures/5xx (http returns None)
    and an exponential back-off when the throttle page comes back."""
    for attempt in range(tries):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            SLEEP(wait)
        _last[0] = time.monotonic()
        try:
            if data is not None:
                form = urlencode(data).encode('ascii') if isinstance(data, dict) else data
                body = http.post(url, data=form, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            else:
                body = http.get(url)
        except Exception:      # noqa: BLE001 - a client may raise on 5xx instead of returning None
            body = None
        if body and not blocked(body):
            return body
        if attempt < tries - 1:
            SLEEP((10 if body else 2) * 2 ** attempt)   # throttle page: 10, 20, 40 s; error: 2, 4, 8 s
    return None


def _decode(b):
    if isinstance(b, str):
        return b
    for enc in ('utf-8', 'cp950', 'big5hkscs'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode('cp950', 'replace')


# ---------------------------------------------------------------- the universe

def latest_fy(until):
    """Annual reports for fiscal year Y are uploaded before the AGM (by end of June Y+1)."""
    d = date.fromisoformat(str(until)[:10])
    return d.year - 1 if (d.month, d.day) >= (6, 30) else d.year - 2


def companies(http):
    """All TWSE-listed and TPEx-listed companies: [{'code','name','name_full','name_en','board'}]."""
    out, seen = [], set()
    for url, board in ((TWSE_LIST, 'TWSE'), (TPEX_LIST, 'TPEx')):
        body = _fetch(http, url)
        try:
            rows = json.loads(_decode(body)) if body else []
        except ValueError:
            rows = []
        for r in rows:
            code = str(r.get('公司代號') or r.get('SecuritiesCompanyCode') or '').strip()
            if not re.fullmatch(r'\d{4}', code) or code in seen:
                continue
            seen.add(code)
            out.append({'code': code,
                        'name': (r.get('公司簡稱') or r.get('CompanyAbbreviation') or '').strip(),
                        'name_full': (r.get('公司名稱') or r.get('CompanyName') or '').strip(),
                        'name_en': (r.get('英文簡稱') or r.get('Symbol') or '').replace('　', ' ').strip(),
                        'board': board, 'capital': _capital(r)})
    return out


def _capital(r):
    """Paid-in capital (實收資本額, TWD): the reading order, largest companies first."""
    try:
        return float(str(r.get('實收資本額') or r.get('Paidin.Capital.NTDollars') or r.get('PaidInCapital') or 0).replace(',', ''))
    except ValueError:
        return 0.0


def listing_url(code, fy):
    return f'{DOC}?step=1&colorchg=1&co_id={code}&year={fy - 1911}&mtype=F&dtype=F04&'


def list_reports(http, since, until, key=None):
    """One report per listed company for the latest fiscal year whose annual report is due by
    ``until``.  The source is not date-indexed (doc.twse lists files per company), so ``filed``
    is None here and set by read_report from the upload date; ``since`` is not used."""
    fy = latest_fy(until)
    return [{'id': f'tw-{c["code"]}-{fy}', 'code': c['code'], 'name': c['name'], 'name_en': c['name_en'],
             'name_full': c['name_full'], 'board': c['board'], 'filed': None, 'fy': fy,
             'url': listing_url(c['code'], fy), 'prio': c.get('capital') or 0} for c in companies(http)]


# ---------------------------------------------------------------- doc.twse.com.tw

_READFILE = re.compile(r"""readfile2?\(\s*["']([A-Z])["']\s*,\s*["'](\w+)["']\s*,\s*["']([^"']+\.(?:pdf|PDF|doc|docx|zip))["']""")


def roc_date(s):
    """'115/05/22' or '1150522' or '2026/05/22' → '2026-05-22'."""
    m = re.search(r'(\d{2,4})[/\-.]?(\d{1,2})[/\-.]?(\d{1,2})', s or '')
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 1911 if y < 1911 else y
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def annual_files(listing_html):
    """The annual-report files in a t57sb01 step=1 answer:
    [{'kind','file','desc','uploaded','f04'}], 股東會年報 (F04) first, English versions dropped."""
    page = _decode(listing_html)
    out = []
    for tr in re.split(r'(?i)<tr', page):
        m = _READFILE.search(tr)
        if not m:
            continue
        text = re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', '<tr' + tr))).strip()
        fn = m.group(3)
        if re.search(r'英文|English', text) or re.search(r'F1[0-9]\.', fn) and '年報' not in text:
            continue
        f04 = bool(re.search(r'F04', fn)) or '股東會年報' in text
        if not (f04 or '年報' in text):
            continue
        dates = re.findall(r'\d{3,4}/\d{1,2}/\d{1,2}', text)
        out.append({'kind': m.group(1), 'file': fn, 'desc': text[:200], 'f04': f04,
                    'uploaded': roc_date(dates[-1]) if dates else None})
    out.sort(key=lambda f: (not f['f04'], '營運概況' not in f['desc'], f['file']))
    return out


def pdf_link(step9_html):
    page = _decode(step9_html)
    m = re.search(r"""href\s*=\s*["']?(/pdf/[^"'\s>]+\.pdf)""", page, re.I)
    return DOC_ROOT + m.group(1) if m else None


def read_report(http, rep, key=None):
    """Find the annual report on doc.twse.com.tw, download it and parse the table.
    None when the report is not there / the site keeps refusing."""
    code, fy = rep['code'], int(rep['fy'])
    body = _fetch(http, DOC, data={'step': '1', 'colorchg': '1', 'co_id': code, 'year': str(fy - 1911),
                                   'mtype': 'F', 'dtype': 'F04', 'seamon': ''})
    files = annual_files(body) if body else []
    if not files and body:
        body = _fetch(http, DOC, data={'step': '1', 'colorchg': '1', 'co_id': code, 'year': str(fy - 1911),
                                       'mtype': 'F', 'dtype': '', 'seamon': ''})
        files = annual_files(body) if body else []
    best = None
    for f in files[:6]:     # whole report, or the 營運概況 chapter when it is uploaded in parts
        page = _fetch(http, DOC, data={'step': '9', 'kind': f['kind'], 'co_id': code, 'filename': f['file']})
        link = pdf_link(page) if page else None
        pdf = _fetch(http, link) if link else None
        if not pdf:
            continue
        out = parse(pdf, code=code, name=rep.get('name'), name_en=rep.get('name_en'), fy=fy)
        out['filed'] = f['uploaded']
        out['url'] = link
        if out.get('found'):
            return out
        best = best or out
    return best


# ---------------------------------------------------------------- PDF → text

def pdf_text(pdf_bytes):
    exe = shutil.which('pdftotext')
    if not exe:
        raise RuntimeError('pdftotext (poppler-utils) is needed to read Taiwanese annual reports')
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, 'r.pdf'), os.path.join(d, 'r.txt')
        with open(src, 'wb') as fh:
            fh.write(pdf_bytes)
        subprocess.run([exe, '-layout', '-enc', 'UTF-8', src, dst], check=False, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(dst):
            return ''
        with open(dst, encoding='utf-8', errors='replace') as fh:
            return fh.read()


# ---------------------------------------------------------------- the table parser

UNITS = [(r'百萬|佰萬', 1_000_000), (r'千|仟', 1_000), (r'萬', 10_000), (r'元', 1)]
_START = re.compile(r'(?:曾|會)?\s*[占佔]\s*進\s*[\(（]\s*銷\s*[\)）]\s*貨|主要進銷貨|進\s*[\(（]\s*銷\s*[\)）]\s*貨\s*總額')
_SUB = re.compile(r'[占佔]\s*(?:合併)?\s*(?:進|銷)貨總額|主要(?:銷貨|進貨|銷售|採購)?\s*(?:客戶|供應商|廠商)|主要(?:銷貨|進貨)')
_END = re.compile(r'從業員工|環保支出|環境保護支出|^\s*[（(]\s*[五六七八九十]\s*[)）]\s*最近二年度生產')
_YEAR = re.compile(r'(?<![\d/])(?:民國\s*)?(1[0-4]\d|20[0-4]\d)\s*年(?:度)?')
_PARTIAL = re.compile(r'截至|截止|止|第[一二三四1-4]\s*季|前一季|1\s*月\s*1\s*日至|\d+\s*月\s*\d+\s*日')
_NA = {'-', '－', '—', '–', '--', '---', '─', '不適用', 'N/A', 'NA', 'n/a', '無', '—', '‐', '註', '(註)', '（註）'}
_REL = re.compile(r'關係|子公司|母公司|關聯|聯屬|董事|股東|轉投資|集團|同一|註\d*|^無$|^非$|實質')
_TOTAL = re.compile(r'^(?:合計|總計|總額|小計|銷貨淨額|進貨淨額|銷售淨額|營業收入淨?額?|銷貨收入淨額|銷貨總額|進貨總額|淨額|銷貨|進貨|全年度合計|合\s*計)$')
_OTHER = re.compile(r'^(?:其他|其它|其餘|其他客戶|其他供應商|其他廠商)$')
_TOKEN = re.compile(r'\S+')
_ANON = re.compile(
    r'^(?:[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥]|[A-Za-z]\d{0,2}|\d{1,8}|第[一二三四五六七八九十\d]+名?)\s*'
    r'(?:客戶|公司|廠商|供應商|集團|企業)?$'
    r'|^[A-Za-z]{2}\d{0,2}\s*(?:客戶|公司|廠商|供應商)$'
    r'|^(?:客戶|廠商|供應商|公司|Customer|Supplier|Vendor|Client)\s*[-_]?\s*(?:[A-Za-z]{1,2}\d{0,2}|[甲乙丙丁戊己庚辛壬癸]|\d{1,3})$'
    r'|^[A-Z]\d?\s*(?:Company|Co\.?|Customer|Supplier|客戶|公司|廠商|供應商)$', re.I)


def _num(tok):
    t = tok.replace(',', '').replace('，', '').strip('()（）$')
    try:
        return float(t)
    except ValueError:
        return None


def _kind(tok):
    """A: comma number, N: bare number, P: number with %, X: n/a mark, R: relation word, T: text."""
    t = tok.strip()
    if t in _NA:
        return 'X'
    if re.fullmatch(r'[\(（]?\d{1,3}(?:,\d{3})+(?:\.\d+)?[\)）]?', t):
        return 'A'
    if re.fullmatch(r'[\(（]?\d+(?:\.\d+)?\s*%[\)）]?', t):
        return 'P'
    if re.fullmatch(r'[\(（]?\d+(?:\.\d+)?[\)）]?', t):
        return 'N'
    if _REL.search(t) and not _TOTAL.match(t):
        return 'R'
    return 'T'


def _groups(line):
    """Split one table line into (start_col, name, amount_tok, pct_tok, rel, end_col) groups.
    Returns [] when the line holds no amount."""
    toks = [(m.start(), m.group()) for m in _TOKEN.finditer(line)]
    kinds = [_kind(t) for _, t in toks]
    n = len(toks)
    i = 0
    # 項目 serial number in the first column: "1 甲客戶 ..." / "1 653021 18,035,001 30"
    if n > 3 and kinds[0] == 'N' and len(toks[0][1]) <= 2 and kinds[1] in 'TNR':
        i = 1
    out = []
    while i < n:
        start = toks[i][0]
        name = []
        while i < n and kinds[i] in 'TR':
            name.append(toks[i][1])
            i += 1
        # a bare-number name (codes such as Largan's 653021) when an amount follows it
        if not name and i + 1 < n and kinds[i] == 'N' and kinds[i + 1] in 'AX' and \
                (i + 2 >= n or kinds[i + 2] in 'NPX'):
            if not (kinds[i + 1] == 'X' and kinds[i] == 'N' and _num(toks[i][1]) is not None and len(toks[i][1]) <= 3):
                name.append(toks[i][1])
                i += 1
        if i >= n:
            if name and out:                        # trailing words = remark/relation of the previous group
                out[-1]['rel'] = (out[-1]['rel'] + ' ' + ' '.join(name)).strip()
            break
        if kinds[i] not in 'ANX':
            i += 1
            continue
        amt = toks[i][1]
        i += 1
        pct = None
        if i < n and (kinds[i] in 'PX' or (kinds[i] == 'N' and (_num(toks[i][1]) or 0) <= 100)):
            pct = toks[i][1]
            i += 1
        if pct is None and _kind(amt) != 'A':
            continue                                  # a lone dash, or "3 月" in a header
        rel = []
        while i < n and (kinds[i] in 'RX') and len(rel) < 3:
            rel.append(toks[i][1])
            i += 1
        out.append({'col': start, 'name': ' '.join(name), 'amount': amt, 'pct': pct, 'rel': ' '.join(rel),
                    'end': toks[i - 1][0] + len(toks[i - 1][1])})
    if not any(_kind(g['amount']) in 'AN' for g in out):
        if not any(g['name'] and (_kind(g['amount']) == 'X') for g in out):
            return []
    return out


def _clean_label(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    # "客戶 A" → "客戶A", "L 廠商" → "L廠商"; keep "Apple Inc." as written
    s = re.sub(r'(?<=[㐀-鿿]) (?=[A-Za-z0-9㐀-鿿])|(?<=[A-Za-z0-9]) (?=[㐀-鿿])', '', s)
    return s


def anonymous(label):
    return bool(_ANON.match(_clean_label(label)))


def _unit(text):
    m = re.search(r'單\s*位\s*[:：]?\s*(?:新\s*[台臺]\s*幣|NT\$|NTD|TWD)?\s*([^\s)）]{0,6})', text)
    if not m:
        return None
    u = m.group(0)
    if re.search(r'美元|美金|USD|US\$|人民幣|RMB', u):
        return 'foreign'
    for pat, mult in UNITS:
        if re.search(pat, u):
            return mult
    return None


def _role(line):
    if re.search(r'進\s*[\(（]\s*銷|銷\s*[\(（]\s*進', line):
        return None
    if re.search(r'銷貨|銷售|客戶', line) and not re.search(r'進貨|供應商|採購', line):
        return 'customer'
    if re.search(r'進貨|供應商|採購|廠商', line) and not re.search(r'銷貨|客戶', line):
        return 'supplier'
    return None


def _year_cols(line):
    """Year column headers on a line: [(col, year, partial)]."""
    out = []
    ms = list(_YEAR.finditer(line))
    for k, m in enumerate(ms):
        y = int(m.group(1))
        y = y + 1911 if y < 1911 else y
        tail = line[m.end(): ms[k + 1].start() if k + 1 < len(ms) else len(line)]
        partial = bool(_PARTIAL.search(tail[:24]))
        out.append((m.start(), y, partial))
    return out


def _assign(groups, anchors):
    """Map each group of a line to a column index, by count when complete, else by position."""
    if len(groups) == len(anchors):
        return list(range(len(anchors)))
    idx, lo = [], 0
    for g in groups:
        best = min(range(lo, len(anchors)), key=lambda k: abs(anchors[k] - g['col'])) if lo < len(anchors) else len(anchors) - 1
        idx.append(best)
        lo = best + 1
    return idx


def section(text):
    """The lines of the 主要進銷貨客戶 section (from its heading to the next heading)."""
    lines = text.splitlines()
    starts = [k for k, ln in enumerate(lines) if _START.search(ln) and not re.search(r'\.{6,}|…{3,}', ln)]
    for s in starts:
        seg = []
        for ln in lines[s: s + 260]:
            if seg and _END.search(ln):
                break
            seg.append(ln)
        if any(_groups(ln) for ln in seg) or re.search(r'未達|並無|均無|無單一|無任一|沒有', ' '.join(seg)):
            return seg
    return []


def _sentence(*lines):
    s = re.sub(r'\s+', ' ', ' '.join(x for x in lines if x)).strip()
    return s[:400]


def parse_table(lines):
    """Rows for every year: [{'role','label','amount_raw','pct_raw','rel','year','partial','kind','line'}]
    plus the unit multiplier per role and 'no 10% counterparty' statements."""
    rows, units, none = [], {}, {}
    role, unit, cols = None, None, []
    last_data = None
    pending = []                        # text-only lines after the last data line
    for k, ln in enumerate(lines):
        if not ln.strip():
            continue
        yc = _year_cols(ln)
        g = _groups(_YEAR.sub(lambda m: ' ' * len(m.group()), ln) if yc else ln)
        if not g:
            r = _role(ln) if (_SUB.search(ln) or re.search(r'最近二年度|百分之十|10\s*%', ln)) else None
            if r:
                role, cols, last_data, pending = r, [], None, []
            u = _unit(ln)
            if u:
                unit = u
                if role:
                    units[role] = u
            if re.search(r'未達|並無|均無|無單一|無任一|沒有任一|無占|無佔', ln) and re.search(r'10\s*%|百分之十|10％', ln + ' '.join(lines[k + 1:k + 2])):
                rr = role or _role(ln)
                for x in ([rr] if rr else ['customer', 'supplier']):
                    none[x] = True
            if yc and len(yc) >= 1 and not re.search(r'原因|主要係|增減', ln):
                cols = yc
                last_data, pending = None, []
                continue
            if last_data is not None and not re.search(r'原因|[：:]|註', ln):
                pending.append(ln)
            elif re.search(r'原因|註', ln):
                last_data, pending = None, []
            continue
        if role is None:
            continue
        if role not in units and unit:
            units[role] = unit
        # a leading year label ("114年度 甲客戶 ...") overrides the column year
        lead = _YEAR.match(ln.strip())
        anchors = [c for c, _, _ in cols]
        idx = _assign(g, anchors) if anchors else [0] * len(g)
        # words of wrapped names found between two data lines → suffix of the previous line's names
        if pending and last_data is not None:
            for pl in pending:
                for m in re.finditer(r'\S+(?: \S+)*', pl):
                    frag = m.group()
                    if _TOTAL.match(frag.replace(' ', '')):
                        continue
                    tgt = min(last_data, key=lambda r: abs(r['col'] - m.start()))
                    if abs(tgt['col'] - m.start()) <= 8 and tgt['label']:
                        tgt['label'] += frag
                        tgt['line'] = _sentence(tgt['line'], pl)
        pending = []
        cur = []
        for gi, ci in zip(g, idx):
            if lead and len(g) == 1:
                yr, partial = int(lead.group(1)), False
                yr = yr + 1911 if yr < 1911 else yr
            elif cols:
                _, yr, partial = cols[min(ci, len(cols) - 1)]
            else:
                yr, partial = None, False
            label = gi['name']
            if lead and label.startswith(lead.group(0).strip()):
                label = label[len(lead.group(0).strip()):].strip()
            lab = _clean_label(label)
            kind = 'total' if (not lab or _TOTAL.match(lab.replace(' ', ''))) else 'other' if _OTHER.match(lab) else 'row'
            row = {'role': role, 'label': lab, 'amount_raw': gi['amount'], 'pct_raw': gi['pct'],
                   'rel': gi['rel'], 'year': yr, 'partial': partial, 'kind': kind, 'col': gi['col'],
                   'line': _sentence(ln)}
            rows.append(row)
            cur.append(row)
        last_data = [r for r in cur if r['kind'] == 'row'] or None
    return rows, units, none


def _pct(tok):
    if tok is None or _kind(tok) == 'X':
        return None
    v = _num(tok.replace('%', '').strip())
    if v is None or v < 0 or v > 100:
        return None
    return round(v / 100.0, 6)


def parse(doc, **meta):
    """Offline part: annual-report PDF bytes or its ``pdftotext -layout`` text → the result dict."""
    if isinstance(doc, (bytes, bytearray)) and bytes(doc[:5]) == b'%PDF-':
        text = pdf_text(bytes(doc))
    else:
        text = _decode(doc)
    seg = section(text)
    raw, units, none = parse_table(seg)
    full_years = sorted({r['year'] for r in raw if r['year'] and not r['partial']})
    if full_years:
        fy = full_years[-1]
    else:                               # "民國113年度及民國114年度…均未達10%": the years named in the prose
        named = [y for ln in seg for _, y, part in _year_cols(ln) if not part]
        fy = meta.get('fy') or (max(named) if named else None)
    out = {'code': meta.get('code'), 'name': meta.get('name'), 'name_en': meta.get('name_en'), 'fy': fy,
           'currency': CURRENCY, 'revenue': None, 'rows': [], 'concentration': {}, 'found': bool(seg),
           'unit': {k: v for k, v in units.items()}}
    totals = {}
    for r in raw:
        if r['year'] != fy or r['partial']:
            continue
        mult = units.get(r['role'])
        amt = _num(r['amount_raw']) if _kind(r['amount_raw']) in 'AN' else None
        twd = amt * mult if (amt is not None and isinstance(mult, int)) else None
        share = _pct(r['pct_raw'])
        if r['kind'] == 'total':
            if twd is not None:
                totals[r['role']] = twd
            continue
        if r['kind'] == 'other' or (twd is None and share is None):
            continue
        row = {'role': r['role'], 'label': r['label'], 'amount': twd, 'share': share, 'year': fy,
               'sentence': r['line'][:400], 'anonymous': anonymous(r['label'])}
        if r['rel'] and _kind(r['rel'].split()[0]) != 'X':
            row['relation'] = r['rel']
        if mult == 'foreign' and amt is not None:
            row['amount_reported'] = amt
        out['rows'].append(row)
    for row in out['rows']:                       # share from the total when the cell is blank
        if row['share'] is None and row['amount'] and totals.get(row['role']):
            row['share'] = round(row['amount'] / totals[row['role']], 6)
    out['revenue'] = totals.get('customer')
    if totals.get('supplier'):
        out['purchases'] = totals['supplier']
    conc = {}
    for role, key in (('customer', 'sales'), ('supplier', 'purchases')):
        rs = sorted([r for r in out['rows'] if r['role'] == role and r['share'] is not None],
                    key=lambda r: -r['share'])
        if rs:
            conc[f'top1_{key}'] = rs[0]['share']
            conc[f'top1_{key}_label'] = rs[0]['label']
            conc[f'n_10pct_{key}'] = sum(1 for r in rs if r['share'] >= 0.1)
            conc[f'listed_{key}_share'] = round(sum(r['share'] for r in rs), 6)
        elif none.get(role):
            conc[f'top1_{key}'] = None
            conc[f'none_over_10pct_{key}'] = True
    out['concentration'] = conc
    return out
