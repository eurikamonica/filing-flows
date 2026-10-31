"""Japan: major customers (主要な販売先) and major suppliers (主要な仕入先) read from each company's annual report
(有価証券報告書) on EDINET, the FSA's filing system.

  list_reports  EDINET API v2 書類一覧API, one call per day (documents.json?date=YYYY-MM-DD&type=2): the annual reports
                (docTypeCode '120', 企業内容等の開示に関する内閣府令 = ordinanceCode '010', not funds, not withdrawn, with
                XBRL). Corrections (訂正有価証券報告書, '130') are skipped.
  read_report   書類取得API type=1 (提出本文書及び監査報告書, a ZIP): the inline-XBRL pages under XBRL/PublicDoc/
                (0000000_header_*.htm, 01xxxxx_honbun_*_ixbrl.htm) are joined and handed to parse().
  parse         The offline part. Works on inline-XBRL HTML, on an IR site's HTML, or on plain text (a PDF's text):
                  - 第2 事業の状況 / 生産、受注及び販売の実績: "主な相手先別の販売実績及び当該販売実績の総販売実績に対する
                    割合" — 相手先 | 前連結会計年度 (販売高, 割合) | 当連結会計年度 (販売高, 割合). Only the latest year is kept.
                  - the same kind of table for purchases (仕入先 | 仕入高 / 割合), wherever it sits (often 事業等のリスク).
                  - 主要な顧客ごとの情報 (segment note: 顧客の名称又は氏名 | 売上高 | 関連するセグメント名), used only when
                    the first table is absent; and the IFRS prose form ("…10%以上を占める顧客はA及びBであり…それぞれ
                    X百万円、Y百万円であります") when there is no table at all.
                Amounts are converted to yen (百万円 / 千円 / 億円 / 円), shares to fractions. A company with no customer at
                10% of sales says so ("…10%以上を占める相手先がないため、記載はありません") and gets no rows.
                Revenue: the consolidated 売上高 / 売上収益 / 営業収益 of 主要な経営指標等の推移 (ix:nonFraction with
                contextRef "CurrentYearDuration"), else None.

Network access only through the http object handed in: http.get(url, params=None, headers=None) -> bytes | None.
The API needs a Subscription-Key (env EDINET_API_KEY).

    EDINET_API_KEY=... python disclosures/app/asia_jp.py list 2026-06-26 2026-06-26
    EDINET_API_KEY=... python disclosures/app/asia_jp.py read S100YC4B
    python disclosures/app/asia_jp.py parse path/to/section.htm
"""
import datetime as dt
import io
import json
import re
import sys
import time
import unicodedata
import zipfile
from html.parser import HTMLParser

MARKET = 'jp'
CURRENCY = 'JPY'

API = 'https://api.edinet-fsa.go.jp/api/v2'
VIEWER = 'https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc}'
PDF = 'https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/{doc}.pdf'
PAUSE = 0.25  # seconds between API calls (<= 4 requests a second)

ANNUAL = '120'          # 有価証券報告書 (130 = 訂正有価証券報告書, skipped)
ORDINANCE = '010'       # 企業内容等の開示に関する内閣府令 (companies, not funds)

# 主要な経営指標等の推移, consolidated, current year: the first of these found is the revenue
REVENUE_ELEMENTS = (
    'NetSalesSummaryOfBusinessResults', 'RevenueIFRSSummaryOfBusinessResults', 'NetSalesIFRSSummaryOfBusinessResults',
    'RevenuesUSGAAPSummaryOfBusinessResults', 'NetSalesUSGAAPSummaryOfBusinessResults',
    'OperatingRevenue1SummaryOfBusinessResults', 'OperatingRevenue2SummaryOfBusinessResults',
    'OperatingRevenueIFRSSummaryOfBusinessResults', 'NetSalesOfCompletedConstructionContractsSummaryOfBusinessResults',
    'GrossOperatingRevenueSummaryOfBusinessResults', 'OrdinaryIncomeSummaryOfBusinessResults',
)
REVENUE_LOCAL = re.compile(r'^(NetSales|Revenue|Revenues|OperatingRevenue\d*|GrossOperatingRevenue)\w*SummaryOfBusinessResults$')

UNITS = (('百万円', 10 ** 6), ('千円', 10 ** 3), ('億円', 10 ** 8), ('円', 1))
DASH = set('-－―—−‐ｰ–')
COUNTERPARTY = re.compile(r'相手先|顧客の名称|顧客名|仕入先|販売先|取引先')
TOTAL_ROW = re.compile(r'^(合計|小計|総計|計|その他計)$|グループ計$|^(合計|小計)\b')
SHARE_HDR = re.compile(r'割合|構成比|比率|%')
NOT_SHARE = re.compile(r'前年同期比|前期比|増減|対前|年度比')
AMOUNT_HDR = re.compile(r'販売高|販売実績|金額|売上高|売上収益|仕入高|仕入実績|取引高|取引金額|円')
CJK = re.compile(r'[　-ヿ一-鿿＀-￯]')
OMITTED = re.compile(
    r'(10|１０|100分の10|十)\s*[%％]?\s*(以上[^。]{0,40}?(ない|ありません|おりません|いません|存在しません)|未満)[^。]{0,60}?'
    r'(記載|省略|ありません|おりません)')


def nfkc(s):
    return unicodedata.normalize('NFKC', s or '')


def squash(s):
    return re.sub(r'\s+', ' ', (s or '').replace('　', ' ')).strip()


# ---------------------------------------------------------------- HTML → blocks (paragraphs and tables) + ix facts
class _Doc(HTMLParser):
    BLOCK = {'p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'table', 'section'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []            # ('text', str) | ('table', [[cell dict]])
        self.facts = []             # {'name','context','scale','sign','text'}
        self.buf = []
        self.tables = []            # stack of {'rows': [], 'row': None, 'cell': None}
        self.skip = 0
        self.ix = []                # stack of open fact dicts (or None for ones not captured)

    # text sink: the open cell (lines) or the paragraph buffer
    def _sink(self, data):
        if self.tables and self.tables[-1]['cell'] is not None:
            self.tables[-1]['cell']['cur'].append(data)
        else:
            self.buf.append(data)
        for f in self.ix:
            if f is not None:
                f['text'].append(data)

    def _flush(self):
        t = squash(''.join(self.buf))
        self.buf = []
        if t:
            self.blocks.append(('text', t))

    def _cell_break(self):
        c = self.tables[-1]['cell']
        line = squash(''.join(c['cur']))
        c['cur'] = []
        if line:
            c['lines'].append(line)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
            return
        if tag in ('ix:nonfraction', 'ix:nonnumeric'):
            name = a.get('name') or ''
            if tag == 'ix:nonfraction' or name.startswith('jpdei_cor:'):
                self.ix.append({'name': name, 'context': a.get('contextref') or '', 'scale': a.get('scale') or '0',
                                'sign': a.get('sign') or '', 'tag': tag, 'text': []})
            else:
                self.ix.append(None)
            return
        if tag == 'table':
            self._flush()
            self.tables.append({'rows': [], 'row': None, 'cell': None})
            return
        if self.tables:
            t = self.tables[-1]
            if tag == 'tr':
                t['row'] = []
                t['rows'].append(t['row'])
            elif tag in ('td', 'th'):
                if t['row'] is None:
                    t['row'] = []
                    t['rows'].append(t['row'])
                t['cell'] = {'lines': [], 'cur': [], 'colspan': _int(a.get('colspan')), 'rowspan': _int(a.get('rowspan'))}
                t['row'].append(t['cell'])
            elif tag in self.BLOCK and t['cell'] is not None:
                self._cell_break()
            return
        if tag in self.BLOCK:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            if self.tables and self.tables[-1]['cell'] is not None:
                self._cell_break()
            else:
                self._flush()
        else:
            self.handle_starttag(tag, attrs)
            if tag not in ('br',):
                self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
            return
        if tag in ('ix:nonfraction', 'ix:nonnumeric'):
            if self.ix:
                f = self.ix.pop()
                if f is not None:
                    f['text'] = squash(''.join(f['text']))
                    self.facts.append(f)
            return
        if tag == 'table' and self.tables:
            t = self.tables.pop()
            if t['cell'] is not None:
                self._cell_break()
            rows = [[{'text': _cell_text(c), 'lines': c['lines'], 'colspan': c['colspan'], 'rowspan': c['rowspan']}
                     for c in r] for r in t['rows'] if r]
            if rows:
                self.blocks.append(('table', rows))
            return
        if self.tables:
            t = self.tables[-1]
            if tag in ('td', 'th') and t['cell'] is not None:
                self._cell_break()
                t['cell'] = None
            elif tag == 'tr':
                t['row'] = None
            elif tag in self.BLOCK and t['cell'] is not None:
                self._cell_break()
            return
        if tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self._sink(data)

    def close(self):
        super().close()
        while self.tables:
            self.handle_endtag('table')
        self._flush()


def _int(v):
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def _join_label(lines):
    s = ''
    for p in lines:
        p = p.strip()
        if not p:
            continue
        if s and not (CJK.search(s[-1]) or CJK.search(p[0])):
            s += ' '
        s += p
    return s


def _cell_text(c):
    lines = list(c['lines'])
    tail = squash(''.join(c['cur']))
    if tail:
        lines.append(tail)
    return _join_label(lines)


def _grid(rows):
    """Expand colspan / rowspan into a rectangular grid of strings (a spanned cell repeats its text)."""
    grid, pending = [], {}
    for r in rows:
        line, j, k = [], 0, 0
        while k < len(r) or j in pending:
            if j in pending:
                text, left = pending[j]
                line.append(text)
                if left > 1:
                    pending[j] = (text, left - 1)
                else:
                    del pending[j]
                j += 1
                continue
            c = r[k]
            k += 1
            for _ in range(c['colspan']):
                line.append(c['text'])
                if c['rowspan'] > 1:
                    pending[j] = (c['text'], c['rowspan'] - 1)
                j += 1
        grid.append(line)
    width = max((len(x) for x in grid), default=0)
    return [x + [''] * (width - len(x)) for x in grid]


# ---------------------------------------------------------------- numbers, units, periods
NUM = re.compile(r'^[△▲\-−]?\s*[\d,]+(?:\.\d+)?$')


def num(s):
    """'1,234' → 1234.0, '△10' → -10.0, '－' / '' / '※' → None. Footnote marks (※1, (注)2, *1) are dropped."""
    t = nfkc(s).strip()
    t = re.sub(r'(※|\*|\(注\)?)\s*\d*', '', t).strip()
    t = t.replace(' ', '')
    if not t or all(ch in DASH for ch in t):
        return None
    neg = t[0] in '△▲-−'
    t = t.lstrip('△▲-−')
    t = t.rstrip('%')
    if not re.fullmatch(r'[\d,]+(\.\d+)?', t):
        return None
    v = float(t.replace(',', ''))
    return -v if neg else v


def is_value(s):
    t = nfkc(s).strip()
    t = re.sub(r'(※|\*)\s*\d*', '', t).strip()
    return bool(t) and (bool(NUM.match(t.replace(' ', ''))) or all(ch in DASH for ch in t))


def unit_of(text):
    t = nfkc(text)
    for u, m in UNITS:
        if u in t:
            return m
    return None


PERIOD = re.compile(r'(当連結会計年度|前連結会計年度|当事業年度|前事業年度|当期|前期|(\d{4})\s*年\s*(\d{1,2})\s*月期|(\d{4})\s*年度)')


def period_rank(text, fy=None):
    """→ (rank, label) of the period a header names: current year 2, prior 1, (0, '') if none. Words (当/前連結会計年度)
    win over dates; a 'YYYY年M月期' / 'YYYY年度' label comes back as YYYYMM and is made relative per table (_relative)."""
    t = nfkc(text)
    words = [m.group(1) for m in PERIOD.finditer(t) if not m.group(2) and not m.group(4)]
    if words:
        g = words[-1]
        return (2 if g.startswith('当') else 1, g)
    best = (0, '')
    for m in PERIOD.finditer(t):
        ym = int(m.group(2)) * 100 + int(m.group(3)) if m.group(2) else int(m.group(4)) * 100 + 12
        if ym > best[0]:
            best = (ym, m.group(1))
    return best


def _relative(cols):
    """Year-month ranks (YYYYMM) inside one table → 2 for the latest, 1 for the others."""
    ym = [c['rank'] for c in cols if c['rank'] > 2]
    if ym:
        top = max(ym)
        for c in cols:
            if c['rank'] > 2:
                c['rank'] = 2 if c['rank'] == top else 1
    return cols


def context_period(ctx_blocks, fy=None):
    """The period named by the nearest preceding short paragraph that names one ('当連結会計年度(自…至…)')."""
    for t in reversed(ctx_blocks[-3:]):
        if len(nfkc(t)) < 80 and PERIOD.search(nfkc(t)):
            r = period_rank(t, fy)
            return (r[0] if r[0] <= 2 else 2, r[1])
    return (0, '')


# ---------------------------------------------------------------- one counterparty table → candidate rows
def _role(head, ctx, col0):
    c0 = nfkc(col0)
    if '仕入' in c0:
        return 'supplier'
    if '販売先' in c0 or '顧客' in c0:
        return 'customer'
    t = nfkc(' '.join(ctx[-3:]) + ' ' + head)
    ip = max(t.rfind('仕入'), t.rfind('購入'), t.rfind('調達'))
    isales = max(t.rfind('販売'), t.rfind('売上'))
    return 'supplier' if ip > isales else 'customer'


def _table_rows(grid, ctx):
    """A grid whose first column header names counterparties → {'role','kind','cols','rows'} or None."""
    if not grid or len(grid[0]) < 2:
        return None
    hdr = 0
    while hdr < len(grid) and not (grid[hdr][0] and not COUNTERPARTY.search(nfkc(grid[hdr][0]))
                                   and any(is_value(c) for c in grid[hdr][1:])):
        hdr += 1
        if hdr > 4:
            return None
    if hdr == 0 or hdr >= len(grid):
        return None
    col0 = ' '.join(grid[i][0] for i in range(hdr))
    if not COUNTERPARTY.search(nfkc(col0)) or 'セグメント' in nfkc(col0):
        return None
    head = ' '.join(c for i in range(hdr) for c in grid[i])
    kind = 'note' if '顧客の名称' in nfkc(col0) else 'table'
    if not _about_trade(head, ctx, kind):
        return None
    role = _role(head, ctx, col0)
    ctx_unit = next((unit_of(t) for t in reversed(ctx[-2:]) if '単位' in nfkc(t) and unit_of(t)), None)
    tbl_period = context_period(ctx)
    cols = []
    for j in range(1, len(grid[0])):
        label = squash(' '.join(dict.fromkeys(grid[i][j] for i in range(hdr) if grid[i][j])))
        n = nfkc(label)
        if NOT_SHARE.search(n) or 'セグメント' in n:
            k = None
        elif SHARE_HDR.search(n):
            k = 'share'
        elif AMOUNT_HDR.search(n) or (kind == 'note' and not n.strip()):
            k = 'amount'
        else:
            k = None
        pr = period_rank(label)
        if pr[0] == 0:
            pr = tbl_period
        cols.append({'j': j, 'kind': k, 'rank': pr[0], 'period': pr[1] or label, 'label': label,
                     'unit': unit_of(label) or unit_of(head) or ctx_unit})
    _relative(cols)
    if not any(c['kind'] for c in cols):
        # a bare two-column table (相手先 | 金額) whose unit sits above it
        if len(cols) == 1 and (ctx_unit or unit_of(head)):
            cols[0]['kind'] = 'amount'
        else:
            return None
    rows = []
    for r in grid[hdr:]:
        label = squash(r[0])
        if not label or TOTAL_ROW.search(nfkc(label)) or not any(is_value(c) for c in r[1:]):
            continue
        rows.append({'label': label, 'cells': r})
    return {'role': role, 'kind': kind, 'cols': cols, 'rows': rows, 'head': head}


BALANCE = re.compile(r'売掛金|受取手形|買掛金|支払手形|借入金|借入先|未払金|電子記録債権|電子記録債務|預金|貸付金|未収入金|前受金|リース債務|社債|債務保証')
TRADE = re.compile(r'相手先別|販売先|仕入先|販売実績|仕入実績|販売高|仕入高|割合|主要な顧客|主な顧客|顧客ごと')


def _about_trade(head, ctx, kind):
    """Sales/purchase tables only — not the 相手先別内訳 of receivables, payables or loans (主要な資産及び負債の内容)."""
    near = nfkc(' '.join(ctx[-2:]) + ' ' + head)
    if BALANCE.search(near) and not re.search(r'販売実績|仕入実績|主要な顧客|顧客ごと', near):
        return False
    return kind == 'note' or bool(TRADE.search(nfkc(' '.join(ctx[-3:]) + ' ' + head)))


def _pick(tables, fy):
    """Rows of the latest period across the tables of one role/kind."""
    out = []
    ranks = [c['rank'] for t in tables for c in t['cols'] if c['kind']]
    if not ranks:
        return out
    top = max(ranks)
    chosen = [t for t in tables if any(c['kind'] and c['rank'] == top for c in t['cols'])]
    if top == 0 and chosen:
        chosen = chosen[-1:]  # no period anywhere: the last table printed is the current year
    for t in chosen:
        cols = [c for c in t['cols'] if c['kind'] and c['rank'] == top]
        for r in t['rows']:
            amount = share = None
            parts = []
            for c in cols:
                v = num(r['cells'][c['j']])
                parts.append(f"{c['label']}: {r['cells'][c['j']]}")
                if v is None:
                    continue
                if c['kind'] == 'amount' and amount is None:
                    amount = v * (c['unit'] or 10 ** 6)
                elif c['kind'] == 'share' and share is None:
                    share = round(v / 100, 6)
            if amount is None and share is None:
                continue
            period = nfkc(cols[0]['period']) if cols and top else ''
            year = (fy or period) if top in (0, 2) else period
            sentence = (r['label'] + ' | ' + ' | '.join(parts))[:400]
            out.append({'role': t['role'], 'label': r['label'], 'amount': _round(amount), 'share': share,
                        'year': year, 'sentence': sentence})
    return out


def _round(v):
    if v is None:
        return None
    return int(round(v)) if abs(v - round(v)) < 1e-6 or abs(v) >= 1000 else v


# ---------------------------------------------------------------- plain text (a PDF's text, IR text)
ROW = re.compile(r'^(?:(?P<label>.*?[^\d,\s△▲])\s+)?(?P<vals>(?:[△▲]?\d[\d,]*(?:\.\d+)?|[-－―—−‐])(?:\s+(?:[△▲]?\d[\d,]*(?:\.\d+)?|[-－―—−‐]))*)\s*$')


def _text_tables(lines):
    """Counterparty tables in plain text: a header line naming 相手先/仕入先/顧客 then rows 'Name 1,234 12.3 …'."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        h = nfkc(lines[i]).strip()
        if not (COUNTERPARTY.match(h) or re.match(r'^(顧客の名称又は氏名|顧客の名称)', h)) or '。' in h or 'セグメント' in h:
            i += 1
            continue
        # header block: a few short lines before (periods / column titles) and after, up to the first data row
        top = i
        while top > 0 and i - top < 3 and _headerish(lines[top - 1]):
            top -= 1
        j = i + 1
        while j < n and j - i <= 4 and not _data_line(lines[j]) and _headerish(lines[j]):
            j += 1
        head_lines = lines[top:j]
        rows, k, pending = [], j, ''
        while k < n:
            raw = squash(lines[k])
            m = _data_line(raw)
            if m:
                label = (m.group('label') or '').strip()
                vals = m.group('vals').split()
                if not label and pending:
                    label = pending
                    # a wrapped name continues on the line after the numbers
                    if k + 1 < n and _continuation(lines[k + 1]):
                        label = _join_label([label, squash(lines[k + 1])])
                        k += 1
                elif pending and label:
                    label = _join_label([pending, label])
                pending = ''
                if label:
                    rows.append((label, vals, raw))
                k += 1
                continue
            if _continuation(raw) and not pending and k + 1 < n and _data_line(lines[k + 1]):
                pending = raw
                k += 1
                continue
            break
        if rows:
            out.append((head_lines, rows, lines[max(0, top - 4):top]))
        i = max(k, i + 1)
    return out


def _headerish(line):
    t = nfkc(line).strip()
    if not t or '。' in t or len(t) > 70:
        return False
    return bool(re.search(r'年度|割合|販売高|金額|売上|仕入|百万円|千円|自|至|\(%\)|%|月期|相手先|顧客', t))


def _data_line(line):
    t = nfkc(squash(line))
    m = ROW.match(t)
    if not m:
        return None
    label = (m.group('label') or '').strip()
    vals = m.group('vals').split()
    if not any(re.search(r'\d', v) for v in vals):
        return None
    if label and (re.search(r'[。、]$', label) or re.search(r'(年度|月期|割合|\(%\))$', label)):
        return None
    if label and re.fullmatch(r'[\d,.\s]+', label):
        return None
    # keep the label as written (not NFKC): cut the raw line at the same number of trailing value tokens
    raw = squash(line)
    rawm = ROW.match(raw)
    if rawm and len(rawm.group('vals').split()) == len(vals):
        return rawm
    return m


def _continuation(line):
    t = squash(line)
    if not t or len(t) > 45 or '。' in t:
        return False
    n = nfkc(t)
    if re.match(r'^(\(|（|※|\d+[.．]|[①-⑳]|[a-zａ-ｚ][.．])', n) or re.match(r'^\(?注', n):
        return False
    return not _data_line(t)


def _text_cols(head_lines, nvals, ctx):
    head = nfkc(' '.join(head_lines))
    kinds = [('share' if m.group(0) == '割合' else 'amount')
             for m in re.finditer(r'販売高|金額|売上高|売上収益|仕入高|割合', head)]
    periods = [m.group(0) for m in PERIOD.finditer(head) if not m.group(2) and not m.group(4)] or \
        [m.group(0) for m in PERIOD.finditer(head)]
    unit = unit_of(head) or next((unit_of(t) for t in reversed(ctx) if '単位' in nfkc(t)), None)
    if len(kinds) != nvals:
        if periods and nvals % max(1, len(periods)) == 0 and len(kinds) == nvals // len(periods):
            kinds = kinds * len(periods)
        elif nvals == 1:
            kinds = ['amount']
        else:
            return None
    per = []
    if len(periods) > 1 and nvals % len(periods) == 0:
        w = nvals // len(periods)
        per = [periods[i // w] for i in range(nvals)]
    else:
        p = periods[0] if periods else (context_period(ctx)[1] or '')
        per = [p] * nvals
    cols = []
    for i in range(nvals):
        pr = period_rank(per[i]) if per[i] else context_period(ctx)
        cols.append({'j': i + 1, 'kind': kinds[i], 'rank': pr[0], 'period': per[i], 'label': per[i] + ' ' + (
            '割合(%)' if kinds[i] == 'share' else '金額'), 'unit': unit})
    return _relative(cols)


# ---------------------------------------------------------------- prose (IFRS note: 主要な顧客に関する情報)
PROSE = re.compile(
    r'(?P<when>当連結会計年度|当事業年度|前連結会計年度|前事業年度)において、[^。]*?(?:10|１０)\s*[%％]以上を占める'
    r'(?:顧客|相手先)(?:グループ)?は(?P<names>[^。]+?)であり[^。]*。\s*(?P<rest>[^。]*?それぞれ(?P<amts>[^。]+?)であります|'
    r'[^。]*?(?P<amt1>[\d,，]+)\s*(?P<u1>百万円|千円|億円)であります)')


def _prose_rows(text, fy):
    rows = []
    best = 0
    found = []
    for m in PROSE.finditer(text):
        r = period_rank(m.group('when'))[0]
        names = [squash(x) for x in re.split(r'及び|および|並びに|、', m.group('names')) if squash(x)]
        if m.group('amts'):
            amts = re.findall(r'([\d,，]+)\s*(百万円|千円|億円)', m.group('amts'))
        else:
            amts = [(m.group('amt1'), m.group('u1'))]
        if len(amts) != len(names):
            continue
        found.append((r, names, amts, squash(m.group(0))))
        best = max(best, r)
    for r, names, amts, sent in found:
        if r != best:
            continue
        for name, (a, u) in zip(names, amts):
            rows.append({'role': 'customer', 'label': name, 'amount': int(float(nfkc(a).replace(',', '')) * unit_of(u)),
                         'share': None, 'year': fy or ('当連結会計年度' if best == 2 else ''), 'sentence': sent[:400]})
    return rows


# ---------------------------------------------------------------- facts: revenue, names, fiscal year
def _fact_value(f):
    v = num(f['text'])
    if v is None:
        return None
    try:
        v *= 10 ** int(f['scale'])
    except ValueError:
        pass
    return -v if f['sign'] == '-' else v


def _revenue(facts):
    cur = [f for f in facts if f['tag'] == 'ix:nonfraction' and f['context'] == 'CurrentYearDuration']
    by = {}
    for f in cur:
        local = f['name'].split(':')[-1]
        if REVENUE_LOCAL.match(local) and local not in by:
            v = _fact_value(f)
            if v is not None:
                by[local] = v
    for el in REVENUE_ELEMENTS:
        if el in by:
            return _round(by[el])
    return _round(next(iter(by.values()))) if by else None


def _dei(facts, name):
    for f in facts:
        if f['name'] == 'jpdei_cor:' + name and f['text']:
            return f['text']
    return None


def _cover(text, key):
    m = re.search(r'【' + key + r'】\s*([^\n【]+)', text)
    return squash(m.group(1)) if m else None


# ---------------------------------------------------------------- parse
def _decode(doc):
    if isinstance(doc, str):
        return doc
    for enc in ('utf-8', 'cp932', 'euc-jp'):
        try:
            return doc.decode(enc)
        except UnicodeDecodeError:
            continue
    return doc.decode('utf-8', 'replace')


def parse(doc, **meta):
    """doc: inline-XBRL / HTML / plain text (bytes or str). meta: code, name, name_en, fy (ISO) from the listing."""
    text = _decode(doc)
    is_html = bool(re.search(r'<(html|body|table|p|div|ix:)[\s>]', text[:200000], re.I))
    facts, blocks = [], []
    if is_html:
        d = _Doc()
        d.feed(text)
        d.close()
        facts, blocks = d.facts, d.blocks
    fy = meta.get('fy') or _dei(facts, 'CurrentFiscalYearEndDateDEI')
    plain = '\n'.join(b[1] for b in blocks if b[0] == 'text') if is_html else text

    tables = []
    if is_html:
        ctx = []
        for kind, b in blocks:
            if kind == 'text':
                ctx.append(b)
                ctx = ctx[-6:]
                continue
            t = _table_rows(_grid(b), ctx)
            if t:
                tables.append(t)
            ctx = ctx[-6:]
        # a table only in text form (some IR pages print the section as <pre> or loose lines)
        if not tables:
            tables += _tables_from_text(plain.split('\n'))
    else:
        tables += _tables_from_text(text.split('\n'))

    rows = []
    for role in ('customer', 'supplier'):
        main = [t for t in tables if t['role'] == role and t['kind'] == 'table']
        got = _pick(main, fy) if main else []
        if not got:
            notes = [t for t in tables if t['role'] == role and t['kind'] == 'note']
            got = _pick(notes, fy) if notes else []
        if not got and role == 'customer':
            got = _prose_rows(squash_lines(plain), fy)
        rows += got

    out = {
        'code': meta.get('code') or _dei(facts, 'EDINETCodeDEI'),
        'name': meta.get('name') or _dei(facts, 'FilerNameInJapaneseDEI') or _cover(plain, '会社名'),
        'name_en': meta.get('name_en') or _dei(facts, 'FilerNameInEnglishDEI') or _cover(plain, '英訳名'),
        'fy': fy,
        'currency': CURRENCY,
        'revenue': _revenue(facts),
        'rows': rows,
        'concentration': _concentration(rows, squash_lines(plain)),
    }
    if not rows:
        for sent in re.split(r'(?<=。)', squash_lines(plain)):
            if re.search(r'相手先|顧客|販売先|仕入先', sent) and OMITTED.search(sent):
                out['note'] = sent.strip()[:400]
                break
    return out


def squash_lines(text):
    """Plain text with PDF line wraps undone (Japanese lines join without a space)."""
    return _join_label([x for x in (text or '').split('\n')])


def _tables_from_text(lines):
    out = []
    for head_lines, rows, ctx in _text_tables(lines):
        nvals = max(len(v) for _, v, _ in rows)
        cols = _text_cols(head_lines, nvals, ctx)
        if not cols:
            continue
        col0 = next((h for h in head_lines if COUNTERPARTY.search(nfkc(h))), '')
        head = ' '.join(head_lines)
        trows = []
        for label, vals, raw in rows:
            if TOTAL_ROW.search(nfkc(label)) or len(vals) != nvals:
                continue
            trows.append({'label': label, 'cells': [label] + vals})
        kind = 'note' if '顧客の名称' in nfkc(col0) else 'table'
        out.append({'role': _role(head, [squash(c) for c in ctx], col0), 'kind': kind, 'cols': cols,
                    'rows': trows, 'head': head})
    return out


def _concentration(rows, text):
    c = {}
    for role, key in (('customer', 'sales'), ('supplier', 'purchases')):
        shares = [r['share'] for r in rows if r['role'] == role and r['share'] is not None]
        if shares:
            c['top1_' + key] = max(shares)
    s = text or ''
    for m in re.finditer(r'上位\s*([1-9１-９])\s*社', s):
        n = int(nfkc(m.group(1)))
        if n not in (1, 5):
            continue
        a = s.rfind('。', 0, m.start()) + 1
        e = s.find('。', m.end())
        sent = s[a:e if e > 0 else len(s)]
        tail = s[m.end():e if e > 0 else len(s)]
        cur = [x.end() for x in re.finditer(r'当連結会計年度|当事業年度|当期', tail)]
        pct = re.search(r'([\d.．]+)\s*[%％]', tail[cur[-1]:] if cur else tail)
        if not pct:
            continue
        key = 'purchases' if re.search(r'仕入|購入|調達', sent) else 'sales'
        c.setdefault(f'top{n}_{key}', round(float(nfkc(pct.group(1))) / 100, 6))
    return c


# ---------------------------------------------------------------- EDINET API
def _json(b):
    try:
        return json.loads(b.decode('utf-8'))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def _days(since, until):
    d, end = dt.date.fromisoformat(str(since)[:10]), dt.date.fromisoformat(str(until)[:10])
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def list_reports(http, since, until, key=None):
    """Annual reports (有価証券報告書) filed between since..until (ISO dates, inclusive), oldest first."""
    out, seen = [], set()
    first = True
    for day in _days(since, until):
        if not first:
            time.sleep(PAUSE)
        first = False
        params = {'date': day.isoformat(), 'type': 2}
        if key:
            params['Subscription-Key'] = key
        data = _json(http.get(f'{API}/documents.json', params=params) or b'')
        if not data:
            continue
        status = str((data.get('metadata') or {}).get('status') or data.get('StatusCode') or '200')
        if status != '200':
            continue
        for d in data.get('results') or []:
            rep = _listing_row(d)
            if rep and rep['id'] not in seen:
                seen.add(rep['id'])
                out.append(rep)
    out.sort(key=lambda r: (r['filed'], r['id']))
    return out


def _listing_row(d):
    if d.get('docTypeCode') != ANNUAL:
        return None
    if (d.get('ordinanceCode') or ORDINANCE) != ORDINANCE or d.get('fundCode'):
        return None
    if str(d.get('withdrawalStatus') or '0') != '0':      # 1 = 取下書, 2 = withdrawn
        return None
    if str(d.get('docInfoEditStatus') or '0') == '1':     # the "information was edited" notice, not the document
        return None
    if str(d.get('disclosureStatus') or '0') in ('1', '2'):  # not disclosed
        return None
    if str(d.get('xbrlFlag') or '0') != '1' or not d.get('docID') or not d.get('edinetCode'):
        return None
    sec = d.get('secCode') or None
    doc = d['docID']
    return {
        'id': doc,
        'code': d['edinetCode'],
        'sec_code': sec,
        'ticker': sec[:4] if sec and len(sec) == 5 and sec.endswith('0') else sec,
        'name': squash(d.get('filerName')),
        'name_en': None,   # not in the document list; read_report takes it from jpdei_cor:FilerNameInEnglishDEI
        'filed': (d.get('submitDateTime') or '')[:10],
        'fy': d.get('periodEnd'),
        'period_start': d.get('periodStart'),
        'url': VIEWER.format(doc=doc),
        'pdf': PDF.format(doc=doc) if str(d.get('pdfFlag')) == '1' else None,
        'description': d.get('docDescription'),
        'csv': str(d.get('csvFlag') or '0') == '1',
    }


def report_pages(zip_bytes):
    """The inline-XBRL (or HTML) pages of a type=1 ZIP, in document order: header first, then honbun."""
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return []
    names = [n for n in z.namelist() if re.search(r'\.(htm|html|xhtml)$', n, re.I)]
    pub = [n for n in names if re.search(r'(^|/)XBRL/PublicDoc/', n)]
    if not pub:
        pub = [n for n in names if re.search(r'(^|/)PublicDoc/', n)]
    pub.sort(key=lambda n: n.rsplit('/', 1)[-1])
    return [(n, z.read(n)) for n in pub]


def read_report(http, rep, key=None):
    params = {'type': 1}
    if key:
        params['Subscription-Key'] = key
    b = http.get(f"{API}/documents/{rep['id']}", params=params)
    if not b or not b.startswith(b'PK'):
        return None  # 404, or a JSON error body (the API answers errors as application/json)
    pages = report_pages(b)
    if not pages:
        return None
    doc = '\n'.join(_decode(x) for _, x in pages)
    out = parse(doc, code=rep.get('code'), name=rep.get('name'), name_en=rep.get('name_en'), fy=rep.get('fy'))
    out['id'] = rep['id']
    return out


# ---------------------------------------------------------------- manual use
class _UrllibHttp:
    """Stand-in for the site's http object (manual runs only)."""

    def get(self, url, params=None, headers=None):
        import urllib.error
        import urllib.parse
        import urllib.request
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=dict({'User-Agent': 'filing-flows/1.0'}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise


def main(argv):
    import os
    key = os.environ.get('EDINET_API_KEY')
    http = _UrllibHttp()
    if argv[:1] == ['list']:
        for r in list_reports(http, argv[1], argv[2] if len(argv) > 2 else argv[1], key):
            print(json.dumps(r, ensure_ascii=False))
    elif argv[:1] == ['read']:
        print(json.dumps(read_report(http, {'id': argv[1]}, key), ensure_ascii=False, indent=1))
    elif argv[:1] == ['parse']:
        with open(argv[1], 'rb') as f:
            print(json.dumps(parse(f.read()), ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
