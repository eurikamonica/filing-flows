"""The President's securities trades (4.19): OGE Form 278-T periodic transaction reports, read by OCR.

The President's reports are posted by the Office of Government Ethics as scanned PDFs (extapps2.oge.gov, the
"Presiden.nsf / PAS Index" collection). Each 278-T row is: number · description · type (Purchase / Sale / Exchange)
· transaction date · whether notification came more than 30 days later · amount range (one of OGE's fixed brackets).

  discover   OGE's disclosure search (the JSON endpoint behind oge.gov's Officials' Individual Disclosures Search
             Collection), filtered to Donald J. Trump as President, plus a seed list of known report URLs from config
  collect    downloads each 278-T and takes its text layer (most were run through Acrobat's Paper Capture before posting;
             Poppler pdftotext); a page with no text is rasterised (pdftoppm) and read with Tesseract (psm 4, row by row),
             a page budget per run so a long plain scan spreads over a few runs. The lines are kept
             (cache/president/ocr/<id>.json.gz) so the parser can be improved and re-run without reading the PDFs again
  parse      rows from the lines: a transaction type matched loosely (the scans' text has "lourchaso" for "Purchase" and
             "salo" for "Sale"), a date ("717/2026" is 7/7/2026), an amount snapped to OGE's brackets ("$1 000 001 - $5 000 000");
             a row split over two or three lines (the number, then the figures) is joined back
  publish    market/president.json: the reports, the parsed trades with a ticker where the description names a listed
             company (SEC's company list; exact name, then a close match on names sharing the first letters), and per
             ticker the purchases, sales and the net at range midpoints

Read by machine from scans: descriptions can be misread and amounts are ranges. Every row keeps its report and page so
it can be checked against the PDF. The annual reports (278e) are listed, not read (their asset tables need a reviewer).
"""
import bisect
import datetime as dt
import difflib
import gzip
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

from core import now, read_json, write_json

BASE = 'https://extapps2.oge.gov/201/Presiden.nsf/'
# the search behind oge.gov's "Officials' Individual Disclosures Search Collection" (a DataTables server endpoint)
API = BASE + 'API.xsp/v3/rest?draw=1&start=0&length=500&search%5Bvalue%5D=Trump%2C%20Donald'
LISTINGS = ('PAS+Index?OpenView&Count=1000',)
PDF_LINK = re.compile(r'(?:https?://extapps2\.oge\.gov)?/?201/Presiden\.nsf/PAS\+Index/([0-9A-Fa-f]{32})/\$FILE/([^"\'<>]+?\.pdf)', re.I)
DOC_LINK = re.compile(r'PAS\+Index/([0-9A-Fa-f]{32})(?:\?OpenDocument)?', re.I)

# OGE's amount brackets (Form 278-T, Part 2)
BRACKETS = [(1001, 15000), (15001, 50000), (50001, 100000), (100001, 250000), (250001, 500000), (500001, 1000000),
            (1000001, 5000000), (5000001, 25000000), (25000001, 50000000), (50000001, 100000000)]
# OGE writes $1,000,001 - $5,000,000; the scans' text has the commas as spaces, dots or nothing ($1 000 001, $100001-$250 000)
# and the dash as · • : ~ or a dot
MONEY = r'(?<![\d/])[\$S5]?\s?(\d{1,3}(?:\s?[,.;]?\s?\d{3})+)(?!\d)'
AMOUNT = re.compile(MONEY + r'\s*(?:[-–—~·•:=_.,]|to){1,3}\s*' + MONEY)
LOW_ONLY = re.compile(MONEY + r'\s*[-–—~·•:]\s*[\$S]?\d{0,2}\s*$')          # the column cut at the page edge: "$50 001 - $"
LOWS = {lo: (lo, hi) for lo, hi in BRACKETS}
DIGITISH = str.maketrans('OoDQIlsS;', '00001155,')
# a figure as the scans' text writes it, at the start of a word: "ssoo.ooo" is $500,000, "s1.ooo.001" $1,000,001
MONEYISH = re.compile(r'(?<![^\s\-–—•·:~])[\$Ss]\s?(?:[\dOoDQIlsS,.;]|\s(?=[\dOoDQIlsS]))+(?![A-Za-z])')
OVER = re.compile(r'(?:over|more than)\s*[\$S5]?\s?(\d{1,3}(?:\s?[,.]?\s?\d{3})+)', re.I)
BOND = re.compile(r'\d+(?:\.\d+)?\s?%|\b(?:DUE|BDS?|BOND|NOTES?|NTS|MUNI\w*|CPN|SR|SUB|REV|GO|TXBL|CTFS?)\b|\b20[3-9]\d\b', re.I)


# ------------------------------------------------------------------ discovery
def report_meta(url, kind=None, posted=None):
    """{'id', 'url', 'name', 'filed', 'kind', 'posted'} from a report URL (the filing date and kind are in the file
    name: Donald-J-Trump-09.8.2026-278T.pdf, Donald J. Trump 9.3.25 278-T.pdf)."""
    m = PDF_LINK.search(url)
    if not m:
        return None
    unid, name = m.group(1).upper(), unquote(m.group(2))
    low = name.lower()
    if 'trump' not in low or 'donald' not in low:
        return None
    kind = kind or ('278T' if re.search(r'278[\s-]*t', low) else 'annual' if 'annual' in low else 'termination' if 'termination' in low else 'other')
    d = re.search(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2}|\d{2})(?!\d)', name)
    filed = None
    if d:
        y = int(d.group(3)) + (2000 if len(d.group(3)) == 2 else 0)
        try:
            filed = dt.date(y, int(d.group(1)), int(d.group(2))).isoformat()
        except ValueError:
            filed = None
    y = re.search(r'(20\d{2})\s*-?\s*(?:278\s*)?Annual|Annual\s*\(?(20\d{2})', name, re.I) or re.search(r'(20\d{2})-?278ANNUAL', name, re.I)
    if not filed and y:
        filed = f'{y.group(1) or y.group(2)}-05-15'
    if not filed and posted:
        filed = posted
    return {'id': unid, 'unid': unid, 'url': BASE + 'PAS+Index/' + unid + '/$FILE/' + quote(name, safe=',()'),
            'name': name, 'filed': filed, 'kind': kind, 'posted': posted}


def api_reports(client):
    """The President's reports from OGE's disclosure search (Trump, Donald J · President): [report_meta, …]."""
    body = json.loads(client.get(API).decode('utf-8', 'replace'))
    out = []
    for row in body.get('data') or []:
        if not str(row.get('name', '')).startswith('Trump, Donald') or 'President' not in str(row.get('title', '')):
            continue
        typ = re.sub(r'<[^>]+>', ' ', str(row.get('type', '')))
        kind = '278T' if re.search(r'278 Transaction', typ) else 'annual' if 'Annual' in typ else 'termination' if 'Termination' in typ else 'other'
        posted = str(row.get('docDate') or '')[:10] or None
        for href in re.findall(r"href='([^']+)'", str(row.get('type', ''))):
            r = report_meta(href.replace('\\/', '/'), kind, posted)
            if r:
                out.append(r)
    return out


def discover(client, cfg):
    """Report URLs from OGE's disclosure search and the configured seeds (the collection's own listing as a fallback),
    newest first; (reports, notes)."""
    found, notes = {}, []
    for u in cfg.get('seed_urls') or []:
        r = report_meta(u)
        if r:
            found[r['id']] = r
    try:
        rows = api_reports(client)
        for r in rows:
            found[r['id']] = {**found.get(r['id'], {}), **r}
        notes.append(f'search: {len(rows)} reports')
        listings = ()
    except Exception as exc:
        notes.append(f'search: {str(exc)[:120]}')
        listings = LISTINGS
    for path in listings:
        try:
            body = client.get(BASE + path).decode('utf-8', 'replace')
        except Exception as exc:
            notes.append(f'listing {path}: {str(exc)[:120]}')
            continue
        n0 = len(found)
        for m in PDF_LINK.finditer(body.replace('\\/', '/')):
            r = report_meta('https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/' + m.group(1) + '/$FILE/' + m.group(2))
            if r:
                found.setdefault(r['id'], r)
        notes.append(f'listing {path}: {len(found) - n0} new')
    return sorted(found.values(), key=lambda r: (r['filed'] or '', r['id']), reverse=True), notes


# ------------------------------------------------------------------ OCR
def ocr_pages(pdf_path, first, last, dpi=300):
    """[{'page', 'conf', 'lines': [[text, x0, x1, top], …]}] for pages first..last (Tesseract TSV, words grouped into lines
    by their block / paragraph / line ids, each line's words left to right)."""
    import csv
    if not shutil.which('pdftoppm') or not shutil.which('tesseract'):
        raise RuntimeError('OCR needs Poppler pdftoppm and Tesseract on PATH')
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(first, last + 1):
            prefix = str(Path(tmp) / f'p{i}')
            subprocess.run(['pdftoppm', '-f', str(i), '-l', str(i), '-singlefile', '-r', str(dpi), '-gray', '-png', str(pdf_path), prefix],
                           check=True, capture_output=True, timeout=180)
            raw = subprocess.run(['tesseract', prefix + '.png', 'stdout', '-l', 'eng', '--psm', '4', 'tsv'], check=True,
                                 capture_output=True, timeout=240).stdout.decode('utf-8', 'replace')
            lines, confs = {}, []
            for w in csv.DictReader(io.StringIO(raw), delimiter='\t', quoting=csv.QUOTE_NONE):
                t = (w.get('text') or '').strip()
                if not t:
                    continue
                key = (int(w['block_num']), int(w['par_num']), int(w['line_num']))
                x0, top = int(w['left']), int(w['top'])
                lines.setdefault(key, []).append((x0, x0 + int(w['width']), top, t))
                c = float(w.get('conf') or -1)
                if c >= 0:
                    confs.append(c)
            rows = []
            for ws in lines.values():
                ws.sort()
                rows.append([' '.join(w[3] for w in ws), ws[0][0], ws[-1][1], min(w[2] for w in ws), [[w[3], w[0]] for w in ws]])
            rows.sort(key=lambda r: (r[3], r[1]))
            out.append({'page': i, 'source': 'ocr', 'conf': round(sum(confs) / len(confs), 1) if confs else None, 'lines': rows})
    return out


def text_pages(pdf_path):
    """The PDF's own text layer, page by page ({page: [[line], …]}); most of the reports were run through Acrobat's
    Paper Capture before posting, which reads the boxed table better than Tesseract does. Pages with next to no
    text (a plain scan) are left out, for OCR."""
    if not shutil.which('pdftotext'):
        return {}
    try:
        raw = subprocess.run(['pdftotext', '-layout', str(pdf_path), '-'], capture_output=True, timeout=180).stdout.decode('utf-8', 'replace')
    except Exception:
        return {}
    out = {}
    for i, body in enumerate(raw.split('\f'), 1):
        if len(re.findall(r'[A-Za-z]', body)) >= 200:
            out[i] = [[ln.strip()] for ln in body.splitlines() if ln.strip()]
    return out


def pdf_pages(pdf_path):
    try:
        info = subprocess.run(['pdfinfo', str(pdf_path)], capture_output=True, timeout=60).stdout.decode('utf-8', 'replace')
        m = re.search(r'Pages:\s+(\d+)', info)
        return int(m.group(1)) if m else None
    except Exception:
        return None


# ------------------------------------------------------------------ parsing
def _alpha(tok):
    return re.sub(r'[^a-z]', '', tok.lower().replace('0', 'o').replace('1', 'l').replace('5', 's').replace('$', 's').replace('|', 'l'))


def tx_type(tok):
    """'P' / 'S' / 'E' when an OCR token reads as Purchase / Sale / Exchange, else None."""
    a = _alpha(tok)
    if len(a) < 3:
        return None
    if difflib.SequenceMatcher(None, a, 'purchase').ratio() >= 0.62:
        return 'P'
    # "lourchaso", "ourcliao", "c,urchoso", "oun:halo" (rch read as n:h), "lpurcl\\uo": the type column is written in
    # lower case, so a word in capitals (CHURCH, RESEARCH) is a name, not a garbled "purchase"
    if (re.search(r'[a-z]', tok) or re.search(r'[^A-Za-z]', tok)) and not re.fullmatch(r'[A-Z][a-z]+', tok) \
            and any(k in a for k in ('urch', 'rch', 'unha', 'urcl')):
        return 'P'
    if a in ('sale', 'sal', 'sales', 'saie', 'sele', 'sa', 'salep', 'salepartial') or (len(a) <= 6 and difflib.SequenceMatcher(None, a, 'sale').ratio() >= 0.75) \
            or a.startswith('salepart'):
        return 'S'
    # "sato", "5:llo", "s:,lo", "sa\\o": a short lower-case or garbled word that starts like "s" and ends like "e"/"o"
    if 3 <= len(tok) <= 6 and tok[0] in 'sS5$' and tok[-1] in 'oOeE0' and (tok[0] in 's5$' or re.search(r"[^A-Za-z]", tok)):
        return 'S'
    if 'xchan' in a or difflib.SequenceMatcher(None, a, 'exchange').ratio() >= 0.7:
        return 'E'
    return None


def _num(s):
    s = re.sub(r'[^\d]', '', s)
    return int(s) if s else None


def snap_amount(lo, hi):
    """The OGE bracket an OCR-read range most likely is (log distance of both ends), or None when nothing is close."""
    best = None
    for b in BRACKETS:
        d = 0.0
        for v, ref in ((lo, b[0]), (hi, b[1])):
            if v is None or v <= 0:
                d += 3
            else:
                d += abs(math.log10(v) - math.log10(ref))
        if best is None or d < best[0]:
            best = (d, b)
    return best[1] if best and best[0] <= 0.35 else None


def parse_amount(text):
    """((min, max), position) of the amount: the first range that snaps to an OGE bracket. The digits after a "$" are
    read with O/D/Q as 0 and I/l as 1, "SS00,001" as "$500,001"; a range whose upper end the scan cut off counts when
    its lower end is exactly a bracket's."""
    text = MONEYISH.sub(lambda m: '$' + m.group()[1:].translate(DIGITISH) if len(re.findall(r'[\doO]', m.group()[1:])) >= 3 else m.group(), text)
    m = OVER.search(text)
    if m:
        v = _num(m.group(1))
        if v and v >= 40_000_000:
            return (50000001, None), m.start()
    pos = 0
    while True:
        m = AMOUNT.search(text, pos)
        if not m:
            break
        b = snap_amount(_num(m.group(1)), _num(m.group(2)))
        if b:
            return b, m.start()
        pos = m.start() + 1
    m = LOW_ONLY.search(text)
    if m and _num(m.group(1)) in LOWS:
        return LOWS[_num(m.group(1))], m.start()
    return None, None


DATE_TOKEN = re.compile(r'(?<![\w/\\|])[\dlI|\\/][\dlI|\\/.]{3,10}[\dlI|\\/](?![\w/\\|])')
GLUE = re.compile(r'(?<=[\d/]) (?=[\d/])')


def _date(mo, d, y, latest, earliest):
    mo, d, y = int(mo), int(d), int(y)
    if y < 100:
        y += 2000
    try:
        iso = dt.date(y, mo, d).isoformat()
    except ValueError:
        return None
    if (latest and iso > latest) or (earliest and iso < earliest):
        return None
    return iso


def read_date(tok, latest=None, earliest=None):
    """A transaction date from one token as the scans' text writes it: 7/17/2026, but also 717/2026 and 2/1012026 (a
    slash read as 1), 2l20l2026 (as l), 1/612028 (and the year's 6 as 8). The reading with the fewest changes that is a
    real date inside the report's window wins."""
    import itertools
    t = re.sub(r'[lI|\\]', '/', tok).replace('.', '')         # 8/1.9/2025
    best = None
    for y_fix in (False, True):
        k = t.count('/')
        ones = [i for i, c in enumerate(t) if c == '1']
        need = 2 - k
        if need < 0 or need > 2:
            return None
        for pos in itertools.combinations(ones, need):
            c = ''.join('/' if i in pos else ch for i, ch in enumerate(t))
            m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(20\d{2})', c)
            if not m:
                continue
            y = m.group(3)
            if y_fix:
                if y[-1] != '8':
                    continue
                y = y[:-1] + '6'
            iso = _date(m.group(1), m.group(2), y, latest, earliest)
            if iso and (best is None or need < best[0]):
                best = (need, iso)
        if best:
            return best[1]
    return None


def parse_date(text, latest=None, earliest=None):
    """(date, position) of the last transaction date in the text within [earliest, latest] (a bond's maturity in the
    description is written out, or later than the filing, and is skipped)."""
    hit = None
    for m in DATE_TOKEN.finditer(text):
        iso = read_date(m.group(), latest, earliest)
        if iso:
            hit = (iso, m.start())
    return hit or (None, None)


SKIP = re.compile(r'(?i)page\s*\d|descri|transac|notifica|amount|filer|received|^\W*$|oge form|days a|instruction|public form')
LEAD = re.compile(r'\s*(\d{1,4})[.,)]?(?:\s+(\S.*))?$')


def parse_lines(pages, filed=None, report_id=None):
    """Transaction rows from a report's pages ([{'page', 'lines': [[text, …], …]}], the PDF's text layer or OCR).

    A row is numbered and has a date and a bracketed amount. The scans' text often splits one: the number alone or with
    the description on one line and the type, date and amount on the next one or two, so a numbered line without its
    figures is held and joined to what follows until they appear (at most three lines). The description is the text
    before the type word (or the date), less the number; a stray line with no figures continues the row above."""
    latest = filed
    earliest = (dt.date.fromisoformat(filed) - dt.timedelta(days=500)).isoformat() if filed else None
    rows = []

    def row(text, page):
        text = GLUE.sub('', text)                  # "7/1 7/2026", "$1 000 001": one token each
        amount, apos = parse_amount(text)
        if not amount:
            return None
        day, dpos = parse_date(text[:apos], latest, earliest)
        if not day:
            # the date column unreadable ("8n•no26", "R/31/?026"): still a row when it is numbered and its type reads;
            # the date is taken from the rows around it (marked)
            head = text[:apos].split()
            if not (head and re.fullmatch(r'\d{1,4}[.,)·•]?', head[0]) and any(tx_type(w) for w in head[-4:])):
                return None
            dpos = apos
        words = text[:min(dpos, apos)].split()
        kind, cut = None, len(words)
        for k in range(len(words) - 1, max(-1, len(words) - 4), -1):      # the type column sits just before the date
            t = tx_type(words[k])
            if t:
                kind, cut = t, k
                break
        desc_words = words[:cut]
        if kind is None and desc_words:            # an unreadable type word ("aalo", "oun:huo", "lcurt:haso") is not a name
            w = desc_words[-1]
            a = _alpha(w)
            if 3 <= len(w) <= 12 and not re.fullmatch(r"[A-Z0-9&.'\-]+|[A-Z][a-z]+\.?", w) and (re.search(r'[a-z]', w) or re.search(r"[^A-Za-z0-9&.'\-]", w)):
                desc_words = desc_words[:-1]
                kind = 'P' if len(a) >= 6 or re.search(r'[hn]', a) else 'S' if len(a) <= 5 and a[-1:] in ('o', 'e') else None
        if kind is None:                           # "DU-", "l)U-"
            while desc_words and len(desc_words[-1]) <= 6 and re.search(r"[^A-Za-z0-9&.']", desc_words[-1]):
                desc_words = desc_words[:-1]
        num = None
        if desc_words and re.fullmatch(r'\d{1,4}[.,)·•]?', desc_words[0]):
            num = int(re.sub(r'\D', '', desc_words[0]))
            desc_words = desc_words[1:]
        while desc_words and re.fullmatch(r'(?i)n/?a|yes|no|[-–—|•·,.\'"]+|\(?\w\)?', desc_words[-1]):
            desc_words = desc_words[:-1]
        if kind is None:                           # the type may sit after the date in a skewed scan
            for w in text[dpos:].split():
                kind = tx_type(w)
                if kind:
                    break
        return {'n': num, 'description': ' '.join(desc_words), 'type': {'P': 'purchase', 'S': 'sale', 'E': 'exchange'}.get(kind, 'unknown'),
                'date': day, 'amount_min': amount[0], 'amount_max': amount[1], 'page': page, 'report': report_id}

    for p in pages:
        prev, pending = None, None                 # pending: [text so far, lines joined]
        for ln in p['lines']:
            text = ln[0].strip().lstrip('\'"‘’`.,-–•·:;~_[]|(){}')   # a speck or a table rule in front of the row number
            if not text:
                continue
            lead = LEAD.match(text)
            # "1 purchase 7/8/2026 …": an "l" read as 1 in front of the type word, not a row number
            starts_row = bool(lead) and not (lead.group(2) and tx_type(lead.group(2).split()[0]))
            if pending is not None and not starts_row:
                joined = pending[0] + ' ' + text
                r = row(joined, p['page'])
                if r:
                    rows.append(r)
                    prev, pending = r, None
                elif pending[1] >= 3:
                    pending = None
                else:
                    pending = [joined, pending[1] + 1]
                continue
            r = row(text, p['page'])
            if r:
                if r['n'] is None and prev is not None and prev.get('n') is not None and not r['description']:
                    r['n'] = None                  # figures with no description: kept, unnumbered
                rows.append(r)
                prev, pending = r, None
                continue
            if SKIP.search(text) or len(' '.join(text.split())) >= 160:
                continue
            if starts_row:
                pending = [text, 1]
            elif prev is not None and not prev.get('_closed') and re.fullmatch(r"[A-Z0-9&.,'/%@\- ]{3,90}", text) \
                    and not re.search(r'\b(?:INC|CORP|CO|LTD|PLC|ETF|LLC|LP|TRUST|FUND|SHARES|CLASS [A-C])$', prev['description']):
                prev['description'] = (prev['description'] + ' ' + text).strip()     # a long name wrapped onto a second line
                prev['_closed'] = True
    dated = [i for i, r in enumerate(rows) if r['date']]
    for i, r in enumerate(rows):
        if not r['date'] and dated:                # the nearest row above with a date (the reports run in date blocks)
            j = bisect.bisect(dated, i)
            r['date'], r['date_estimated'] = rows[dated[j - 1] if j else dated[0]]['date'], True
    rows[:] = [r for r in rows if r['date']]
    known = [i for i, r in enumerate(rows) if r['type'] != 'unknown']
    for i, r in enumerate(rows):
        r.pop('_closed', None)
        r['description'] = re.sub(r'\s+', ' ', r['description']).strip(' -|.,•·\'"')
        if r['type'] == 'unknown' and known:
            j = bisect.bisect(known, i)
            before, after = (rows[known[j - 1]]['type'] if j else None), (rows[known[j]]['type'] if j < len(known) else None)
            if before and before == after:
                r['type'], r['type_inferred'] = before, True
    return rows


# ------------------------------------------------------------------ tickers
CLEAN = re.compile(r'\b(?:COM(?:MON)?(?:\s+STOCK)?|CL(?:ASS)?\s+[A-C]|SHS?|NEW|ORD|SPONSORED|SPON|ADR|ADS|REIT|ETF|UNITS?|PAR\s+\$?[\d.]+|'
                   r'USD|VTG|NON[- ]VTG|CAP(?:ITAL)?\s+STK|STK)\b', re.I)


ABBREV = {'INSTRS': 'INSTRUMENTS', 'WHSL': 'WHOLESALE', 'WHOLESAL': 'WHOLESALE', 'INTL': 'INTERNATIONAL', 'SYS': 'SYSTEMS',
          'SVCS': 'SERVICES', 'SVC': 'SERVICE', 'FINL': 'FINANCIAL', 'MGMT': 'MANAGEMENT', 'COMMUNICATNS': 'COMMUNICATIONS',
          'COMMS': 'COMMUNICATIONS', 'TECHNOLOGI': 'TECHNOLOGIES', 'PHARMACEUTICA': 'PHARMACEUTICALS', 'PPTYS': 'PROPERTIES',
          'RLTY': 'REALTY', 'ENTMT': 'ENTERTAINMENT', 'SCIENTIFC': 'SCIENTIFIC', 'LABS': 'LABORATORIES', 'MTRS': 'MOTORS',
          'HLDG': 'HOLDING', 'AMER': 'AMERICA', 'NATL': 'NATIONAL', 'SOLUTNS': 'SOLUTIONS', 'BANCORPORATION': 'BANCORP',
          'RES': 'RESOURCES', 'PMTS': 'PAYMENTS', 'CHEM': 'CHEMICAL', 'MTG': 'MORTGAGE', 'CMNTYS': 'COMMUNITIES', 'INDS': 'INDUSTRIES',
          'MED': 'MEDICAL', 'PAC': 'PACIFIC', 'INFORMATIO': 'INFORMATION', 'CAP': 'CAPITAL', 'ASSOC': 'ASSOCIATES', 'COS': 'COMPANIES',
          'MATLS': 'MATERIALS', 'ELEC': 'ELECTRIC', 'TECH': 'TECHNOLOGY', 'TECHS': 'TECHNOLOGIES', 'SOL': 'SOLUTIONS', 'INVTS': 'INVESTMENTS',
          'INVT': 'INVESTMENT', 'PPTY': 'PROPERTY', 'HLTH': 'HEALTH', 'HLTHCARE': 'HEALTHCARE', 'MFG': 'MANUFACTURING', 'TR': 'TRUST',
          'SVSC': 'SERVICES', 'ENGY': 'ENERGY', 'PETE': 'PETROLEUM', 'SEMICONDUCTR': 'SEMICONDUCTOR', 'BRANDS': 'BRANDS', 'GRP': 'GROUP',
          'CORPORATIO': 'CORPORATION', 'COMMUNICATIO': 'COMMUNICATIONS', 'ENTERPRISE': 'ENTERPRISES', 'EXCHANG': 'EXCHANGE'}
# brokers' names for a few companies listed under another (SEC's titles)
ALIAS = {'IBM': 'IBM', 'GE AEROSPACE': 'GE', 'O REILLY AUTOMOTIVE': 'ORLY', 'META PLATFORMS': 'META'}
NOISE = re.compile(r'\b(?:UN)?SOLICITED\b|\bEQUITY\b|\bCOM\b|\b(?:CL(?:ASS)?\s+)+(?=[A-C]\b)|\bCLASS\b(?!\s+[A-C]\b)|\bF\b(?=\s+CL)|'
                   r'\b(?:F|DEL|MASS|MD|PA|VA|NJ|NY|WIS|MINN|IND|OHIO|IA|NEV|TEX|CALIF|ORE|COLO|IRELAND|JERSEY|BERMUDA|N\s?V|S\s?A)\s*$')


FUND = re.compile(r'(?i)\b(?:ETF|FUNDS?|MONEY MARKET|INDEX|SPDR|ISHARES|PORTFOLIO|TREASURY|CASH)\b')


def ocr_fix(desc, expand=True):
    """Undo OCR's usual letter swaps inside upper-case words (NVIDlA → NVIDIA, C0RP → CORP, 0 REILLY → O REILLY,
    INTIJIT → INTUIT, METI.IFE → METLIFE), split a suffix glued to the name (NETFLIXINC → NETFLIX INC, AMCORPLCF →
    AMCOR PLC) and, with expand, spell out broker abbreviations (TEXAS INSTRS → TEXAS INSTRUMENTS)."""
    out = []
    desc = re.sub(r'(?i)\bc[l1i]\.?ass\b', 'CLASS', desc or '')
    for w in desc.split():
        if re.fullmatch(r'[A-Z0-9l|&.\-]+', w) and re.search(r'[A-Z]{2}', w):
            w = re.sub(r'I\.(?=[A-Z])', 'L', w).replace('IJ', 'U')
            w = w.replace('l', 'I').replace('|', 'I')
            if re.search(r'[A-Z]0|0[A-Z]', w):
                w = re.sub(r'(?<=[A-Z])0|0(?=[A-Z])', 'O', w)
        w = {'CORO': 'CORP', 'Coro': 'Corp', 'GROUO': 'GROUP', 'Grouo': 'Group'}.get(w, w)
        if w == '0' and not out:
            w = 'O'
        m = re.fullmatch(r'([A-Z&]{2,}?)(INC|CORP|HLDGS|LTD|PLC|INDS|SYS)(DEL|F|CL)?', w)
        if m and m.group(1) not in ('Z', 'ZINC', 'MAG'):
            out += [ABBREV.get(m.group(1), m.group(1)) if expand else m.group(1), ABBREV.get(m.group(2), m.group(2)) if expand else m.group(2)]
            continue
        out.append(ABBREV.get(w.upper().strip('.,'), w) if expand else w)
    return ' '.join(out)


class Tickers:
    """Description → (ticker, how) using the listed companies' names (market.Universe)."""

    def __init__(self, universe):
        from collections import defaultdict
        from market import norm_name
        self.u, self.norm = universe, norm_name
        self.by_name = defaultdict(set)            # SEC's titles without their state tags (WHIRLPOOL CORP /DE/)
        for t, n in universe.names.items():
            k = norm_name(re.sub(r'/[A-Z]{2,5}/?', ' ', n or ''))
            if k:
                self.by_name[k].add(t)
        self.prefix = {}
        for name in self.by_name:
            self.prefix.setdefault(name[:3], []).append(name)
        self.memo = {}

    def pick(self, cands, desc):
        """One ticker for a company name several listings share: the traded common line (a price file), not a preferred
        or note line (BRK-B for 'CL B'; Alphabet's class A is GOOGL, class C GOOG)."""
        cands = sorted(cands, key=lambda t: (('prices' not in self.u.sources.get(t, ())), '-' in t, len(t), t))
        common = [t for t in cands if 'prices' in self.u.sources.get(t, ())] or cands
        m = re.search(r'\bCL(?:ASS)?\s*([A-C])\b', desc or '', re.I)
        if m and len(common) > 1:
            k = m.group(1).upper()
            hy = [t for t in common if t.endswith('-' + k)]
            if hy:
                return hy[0]
            pre = [(a, b) for a in common for b in common if a != b and b.startswith(a)]
            if pre:
                return pre[0][1] if k == 'A' else pre[0][0]
        return common[0]

    def _lookup(self, text, fixed):
        k = self.norm(text)
        if not k:
            return None
        exact = self.by_name.get(k)
        if exact:
            return self.pick(exact, fixed), 'high'
        if k in ALIAS and self.u.known(ALIAS[k]):
            return ALIAS[k], 'alias'
        if len(k) >= 4:                            # the listed name runs on (NEWMONT → NEWMONT CORP): one company, any line
            hits = {t for n in self.prefix.get(k[:3], []) if n.startswith(k + ' ') for t in self.by_name[n]}
            if hits and len({t.split('-')[0] for t in hits}) == 1:
                return self.pick(hits, fixed), 'medium'
        t, conf = self.u.suggest(text)
        if t:
            return t, conf
        return None

    def __call__(self, desc):
        if desc in self.memo:
            return self.memo[desc]
        out = (None, None)
        paren = re.search(r'\(([A-Z][A-Z.\-]{0,5})\)', desc or '')
        fixed = ocr_fix(desc)
        if paren and self.u.known(paren.group(1)) and self.u.name_check(paren.group(1), desc) != 'check':
            out = (paren.group(1).replace('.', '-'), 'stated')
        elif fixed and not BOND.search(fixed) and not FUND.search(fixed):
            hit = None
            for f in dict.fromkeys((ocr_fix(desc, expand=False), fixed)):       # as written (ASTERA LABS), then spelt out
                text = NOISE.sub(' ', NOISE.sub(' ', CLEAN.sub(' ', f)))
                words = self.norm(text).split()
                hit = self._lookup(text, f)
                if not hit and len(words) >= 2:      # DISNEY WALT CO, GALLAGHER ARTHUR J & CO: the surname first
                    for n in (1, 2):
                        hit = self._lookup(' '.join(words[1:1 + n] + words[:1] + words[1 + n:]), f)
                        if hit:
                            hit = (hit[0], 'close')
                            break
                if not hit and len(words) == 1 and self.u.known(words[0]):
                    hit = (words[0], 'stated' if self.u.name_check(words[0], words[0]) == 'matches' else 'close')   # RTX CORP, IBM CORP
                k = ' '.join(words)
                if not hit and len(k) >= 5:
                    best = difflib.get_close_matches(k, self.prefix.get(k[:3], []), n=1, cutoff=0.86)
                    if best:
                        hit = (self.pick(self.by_name[best[0]], f), 'close')
                if hit:
                    break
            out = hit or out
        self.memo[desc] = out
        return out


def asset_kind(desc):
    """'bond' (a coupon, a maturity, a municipal issuer), 'fund' (an ETF, an index or money-market fund) or 'stock'."""
    f = ocr_fix(desc)
    return 'bond' if BOND.search(f) else 'fund' if FUND.search(f) else 'stock'


# ------------------------------------------------------------------ collect and publish
def _gz_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'))


def _gz_read(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def collect(client, root, cfg):
    """Discover reports, then read the 278-T pages not read yet: the PDF's text layer where it has one (all its pages
    at once), Tesseract for the plain scans, at most cfg['pages_per_run'] OCR pages a run."""
    root = Path(root)
    base = root / 'cache' / 'president'
    if not (shutil.which('pdftotext') and shutil.which('pdfinfo')):
        # the quick polls skip the system tools; the PDFs wait for a run that has them (nothing is downloaded)
        return {'status': 'skipped', 'reason': 'Poppler (pdftotext, pdfinfo) is not installed on this run'}
    state = read_json(base / 'state.json', {}) or {}
    reports, notes = discover(client, cfg)
    known = state.setdefault('reports', {})
    for r in reports:
        known.setdefault(r['id'], {**r, 'pages': None, 'pages_done': 0})
        known[r['id']].update({k: r.get(k) for k in ('url', 'name', 'filed', 'kind', 'posted')})
    budget = int(cfg.get('pages_per_run', 40)) if shutil.which('pdftoppm') and shutil.which('tesseract') else 0
    dpi = int(cfg.get('ocr_dpi', 300))
    read_now, ocr_now, errors = 0, 0, []
    for rid, r in sorted(known.items(), key=lambda kv: kv[1].get('filed') or '', reverse=True):
        if r['kind'] != '278T' or (r.get('pages') and r['pages_done'] >= r['pages']):
            continue
        store = _gz_read(base / 'ocr' / f'{rid}.json.gz', {'pages': []})
        have = {p['page'] for p in store['pages']}
        if r.get('pages') and budget <= 0:            # its text layer is in; what is left needs OCR, next run
            continue
        pdf = None
        try:
            body = client.get(r['url'])
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                f.write(body)
                pdf = f.name
            r['pages'] = r.get('pages') or pdf_pages(pdf)
            if not r['pages']:
                raise ValueError('not a readable PDF')
            layer = text_pages(pdf)
            for i, lines in layer.items():
                if i not in have:
                    store['pages'].append({'page': i, 'source': 'text', 'conf': None, 'lines': lines})
                    have.add(i)
                    read_now += 1
            ocrd = {p['page'] for p in store['pages'] if p.get('source', 'ocr') == 'ocr'}
            weak = [p['page'] for p in store['pages'] if p.get('source') == 'text' and p['page'] not in ocrd and weak_page(p, r['pages'])]
            todo = [i for i in range(1, r['pages'] + 1) if i not in have] + weak
            for i in todo[:max(0, budget)]:
                store['pages'] += ocr_pages(pdf, i, i, dpi)
                have.add(i)
                ocrd.add(i)
                budget -= 1
                read_now += 1
                ocr_now += 1
            store['pages'].sort(key=lambda p: p['page'])
            store.update({'id': rid, 'url': r['url'], 'dpi': dpi, 'read_at': now()})
            _gz_write(base / 'ocr' / f'{rid}.json.gz', store)
            r['pages_done'] = len(have) - len([i for i in weak if i not in ocrd])     # a noisy text page counts once it is OCR'd
            r['text_pages'] = sum(1 for p in store['pages'] if p.get('source') == 'text')
            r.pop('error', None)
        except Exception as exc:
            errors.append(f"{r['name']}: {str(exc)[:160]}")
            r['error'] = str(exc)[:200]
        finally:
            if pdf:
                Path(pdf).unlink(missing_ok=True)
    state.update({'checked_at': now(), 'notes': notes, 'errors': errors})
    write_json(base / 'state.json', state)
    return {'status': 'ok' if not errors else 'partial', 'reports': len(known), 'pages_read': read_now, 'ocr_pages': ocr_now,
            'pending_pages': sum(max(0, (r.get('pages') or 0) - r['pages_done']) for r in known.values() if r['kind'] == '278T'),
            'errors': errors[:5], 'discovery': notes}


def weak_page(page, n_pages):
    """A text-layer page that reads as noise: a transactions page (figures on it, not the cover or the closing
    boilerplate) from which next to no rows parse."""
    if page['page'] in (1, n_pages):
        return False
    figures = sum(1 for ln in page['lines'] if re.search(r'[\$S]\s?\d', ln[0]))
    return figures >= 5 and len(parse_lines([page])) < max(3, figures // 3)


def best_pages(pages):
    """One reading per page: the text layer, or the OCR where that gives more rows."""
    by = {}
    for p in pages:
        by.setdefault(p['page'], []).append(p)
    out = []
    for n in sorted(by):
        cands = by[n]
        out.append(cands[0] if len(cands) == 1 else max(cands, key=lambda p: (len(parse_lines([p])), p.get('source') == 'text')))
    return out


def mid(r):
    return (r['amount_min'] + (r['amount_max'] or r['amount_min'] * 2)) / 2


def publish(root, out_dir, universe=None):
    """market/president.json from the cached OCR pages (re-parsed every time, so parser fixes apply to old scans)."""
    root, out_dir = Path(root), Path(out_dir)
    base = root / 'cache' / 'president'
    state = read_json(base / 'state.json', {}) or {}
    reports = state.get('reports') or {}
    if universe is None:
        from market import Universe
        universe = Universe(root)
    tick = Tickers(universe)
    trades, filings = [], []
    for rid, r in sorted(reports.items(), key=lambda kv: kv[1].get('filed') or '', reverse=True):
        row = {'id': rid, 'name': r.get('name'), 'url': r.get('url'), 'filed': r.get('filed'), 'posted': r.get('posted'), 'kind': r.get('kind'),
               'pages': r.get('pages'), 'pages_read': r.get('pages_done', 0)}
        if r.get('kind') == '278T':
            store = _gz_read(base / 'ocr' / f'{rid}.json.gz', {'pages': []})
            pages = best_pages(store['pages'])
            rows = parse_lines(pages, max(filter(None, (r.get('filed'), r.get('posted'))), default=None), rid)
            for x in rows:
                x['asset'] = asset_kind(x['description'])
                x['ticker'], x['match'] = tick(x['description']) if x['asset'] == 'stock' else (None, None)
            nums = {x['n'] for x in rows if x['n']}
            last = max((n for n in nums if n - 1 in nums or n + 1 in nums), default=None)
            row.update({'rows': len(rows), 'with_ticker': sum(1 for x in rows if x['ticker']), 'last_row_number': last,
                        'coverage': round(min(1.0, len(rows) / last), 3) if last else None,
                        'text_pages': sum(1 for p in pages if p.get('source') == 'text'),
                        'ocr_pages': sum(1 for p in pages if p.get('source', 'ocr') == 'ocr'), 'date_estimated': sum(1 for x in rows if x.get('date_estimated')),
                        'ocr_conf': (lambda c: round(sum(c) / len(c), 1) if c else None)([p['conf'] for p in store['pages'] if p.get('conf') is not None]),
                        'span': [min((x['date'] for x in rows), default=None), max((x['date'] for x in rows), default=None)]})
            trades += rows
        filings.append(row)
    by = {}
    for x in trades:
        if not x['ticker'] or x['type'] not in ('purchase', 'sale'):
            continue
        a = by.setdefault(x['ticker'], {'ticker': x['ticker'], 'name': universe.name(x['ticker']), 'buys': 0, 'sells': 0, 'buy_min': 0, 'buy_max': 0,
                                        'sell_min': 0, 'sell_max': 0, 'buy_mid': 0.0, 'sell_mid': 0.0, 'first': x['date'], 'last': x['date']})
        side = 'buy' if x['type'] == 'purchase' else 'sell'
        a[side + 's'] += 1
        a[side + '_min'] += x['amount_min']
        a[side + '_max'] += x['amount_max'] or x['amount_min'] * 2
        a[side + '_mid'] += mid(x)
        a['first'], a['last'] = min(a['first'], x['date']), max(a['last'], x['date'])
    for a in by.values():
        a['net_mid'] = round(a['buy_mid'] - a['sell_mid'])
        a['buy_mid'], a['sell_mid'] = round(a['buy_mid']), round(a['sell_mid'])
    summary = sorted(by.values(), key=lambda a: -(a['buy_mid'] + a['sell_mid']))
    doc = {'generated_at': now(), 'checked_at': state.get('checked_at'), 'discovery': state.get('notes'), 'errors': state.get('errors'),
           'filings': filings, 'tickers': summary,
           'stats': {'trades': len(trades), 'with_ticker': sum(1 for x in trades if x['ticker']), 'purchases': sum(1 for x in trades if x['type'] == 'purchase'),
                     'stocks': sum(1 for x in trades if x['asset'] == 'stock'), 'bonds': sum(1 for x in trades if x['asset'] == 'bond'),
                     'funds': sum(1 for x in trades if x['asset'] == 'fund'), 'type_inferred': sum(1 for x in trades if x.get('type_inferred')),
                     'date_estimated': sum(1 for x in trades if x.get('date_estimated')),
                     'sales': sum(1 for x in trades if x['type'] == 'sale'), 'unknown_type': sum(1 for x in trades if x['type'] == 'unknown'),
                     'span': [min((x['date'] for x in trades), default=None), max((x['date'] for x in trades), default=None)]},
           'trades': sorted(trades, key=lambda x: (x['date'], x['report'] or '', x['n'] or 0), reverse=True)[:6000],
           'note': ("The President's periodic transaction reports (OGE Form 278-T) are posted as scanned PDFs; these rows are "
                    "read by machine from the PDFs' text layer, or by OCR where a scan has none. Descriptions can be misread, a "
                    "few rows in a hundred are not read (each report shows its coverage), a type that could not be read is taken "
                    "from the rows around it (marked), so is a date that could not be read (marked), and amounts are OGE's ranges (net = purchases − sales at range midpoints, "
                    "a rough guide, not a position). Each row links to its report and page. Assets the reports exclude "
                    "(Treasuries, mutual funds, money market) are not here; the annual reports (278e) are listed, not read.")}
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / 'president.json', doc)
    return {'trades': len(trades), 'tickers': len(summary), 'filings': len(filings)}
