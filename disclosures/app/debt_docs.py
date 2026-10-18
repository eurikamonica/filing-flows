"""Parsers for the debt module: pricing term sheets (FWP), prospectus covers (424B2/424B5), credit agreements and the
dimensional debt facts of a 10-K / 10-Q XBRL instance. Pure functions on text / bytes; debt.py fetches the documents.

Every parser is deliberately conservative: it returns only what it can read with a label next to it, and marks what it
read from (field names, the sentence of a covenant), so the page can show the evidence.
"""
import datetime as dt
import html as _html
import re
import xml.etree.ElementTree as ET

MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
                                           'october', 'november', 'december'])}
MON3 = {m[:3]: i for m, i in MONTHS.items()}


# ------------------------------------------------------------------ text
def to_text(raw, limit=None):
    """HTML / text exhibit -> plain text with ' | ' between table cells and newlines between blocks."""
    s = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    if limit:
        s = s[:limit]
    s = re.sub(r'(?is)<(script|style|head)\b.*?</\1>', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>', '\n', s)
    s = re.sub(r'(?i)</t[dh]>', ' | ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = _html.unescape(s)
    s = re.sub(r'[ \t\xa0​  ]+', ' ', s)
    s = re.sub(r'(\s*\|\s*)+', ' | ', s)
    s = re.sub(r'\n\s*\|?\s*\n+', '\n', s)
    s = re.sub(r'\n\s*\|\s*', ' | ', s)
    return s.strip()


def parse_date(s):
    if not s:
        return None
    m = re.search(r'\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})', s)
    if m and m.group(1).lower()[:3] in MON3:
        try:
            return dt.date(int(m.group(3)), MON3[m.group(1).lower()[:3]], int(m.group(2))).isoformat()
        except ValueError:
            return None
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', s)
    if m:
        return m.group(0)
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return None
    return None


def money(s):
    """First amount in a string, in units of its currency: '$1,500,000,000' -> 1.5e9, '$4.47 billion' -> 4.47e9."""
    if not s:
        return None
    m = re.search(r'(?:U\.S\.\s?)?[$€£]\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?', s, re.I)
    if not m:
        m = re.search(r'\b([\d]{1,3}(?:,\d{3}){2,}(?:\.\d+)?)\b', s)
        if not m:
            return None
        return float(m.group(1).replace(',', ''))
    v = float(m.group(1).replace(',', ''))
    mult = {'billion': 1e9, 'million': 1e6, 'thousand': 1e3}.get((m.group(2) or '').lower(), 1)
    return v * mult


def currency(s):
    if '€' in s or re.search(r'\bEUR\b|euro', s, re.I):
        return 'EUR'
    if '£' in s or re.search(r'\bGBP\b|sterling', s, re.I):
        return 'GBP'
    if re.search(r'\bCHF\b|Swiss franc', s, re.I):
        return 'CHF'
    if re.search(r'\bJPY\b|\byen\b|¥', s, re.I):
        return 'JPY'
    if re.search(r'\bC\$|\bCAD\b', s):
        return 'CAD'
    return 'USD'


def pct(s):
    m = re.search(r'(-?\d{1,3}(?:\.\d+)?)\s*%', s or '')
    return float(m.group(1)) if m else None


def bps(s):
    """'25 basis points', '+75 bps', 'T+85', 'UST + 1.25%' -> basis points."""
    if not s:
        return None
    m = re.search(r'([+-]?\s?\d+(?:\.\d+)?)\s*(?:basis\s+points|bps?\b)', s, re.I)
    if m:
        return float(m.group(1).replace(' ', ''))
    m = re.search(r'T\s?\+\s?(\d+(?:\.\d+)?)', s)
    if m:
        return float(m.group(1))
    m = re.search(r'\+\s?(\d+(?:\.\d+)?)\s*%', s)
    if m:
        return float(m.group(1)) * 100
    return None


# ------------------------------------------------------------------ pricing term sheets
TITLE = re.compile(r'(?:(?:U\.S\.)?\s?[$€£]\s?[\d,.]+\s*(?:billion|million)?\s+(?:aggregate principal amount of\s+)?(?:of\s+)?)?'
                   r'(Floating\s+Rate|Fixed[- ]to[- ]Fixed\s+Reset\s+Rate|Fixed[- ]to[- ]Floating\s+Rate|\d{1,2}(?:\.\d{1,4})?\s?%)\s+'
                   r'((?:[A-Za-z\-]+\s+){0,6}?)(Notes|Debentures|Bonds|Debt\s+Securities)\s+due\s+(\d{4})', re.I)
LABELS = [  # (field, regex on the label)
    ('principal', r'^(aggregate\s+)?principal\s+amount|^size\b|^amount\b|^issue\s+size|^aggregate\s+principal|principal\s+amount\s+offered'),
    ('coupon', r'^coupon|^interest\s+rate|^rate\b|^annual\s+interest'),
    ('price', r'price\s+to\s+(the\s+)?public|^issue\s+price|^public\s+offering\s+price|^offering\s+price|^re-?offer\s+price'),
    ('bench_yield', r'benchmark\s+treasury\s+(price\s*(and|/|&)\s*)?yield|treasury\s+price\s*/\s*yield|^treasury\s+yield|benchmark\s+yield'),
    ('benchmark', r'^benchmark(\s+treasury)?$|^treasury\s+benchmark|^benchmark\s+security|^reference\s+treasury'),
    ('spread', r'spread\s+to\s+(benchmark\s+)?(treasury|ust|benchmark)|re-?offer\s+spread|^spread$|^spread\s+to\s+t'),
    ('yld', r'yield\s+to\s+maturity|re-?offer\s+yield|^yield\b|^yield\s+to'),
    ('maturity', r'maturity'),
    ('trade_date', r'trade\s+date|pricing\s+date'),
    ('ratings', r'ratings?'),
    ('conv_price', r'conversion\s+price'),
    ('conv_rate', r'conversion\s+rate'),
    ('conv_premium', r'conversion\s+premium'),
    ('cusip', r'cusip'),
]


def _tokens(text):
    return [t.strip() for t in re.split(r'\s*\|\s*|\n', text) if t.strip()]


def _label_of(tok):
    t = tok.strip().rstrip(':*').strip()
    if len(t) > 60 or len(t) < 3:
        return None
    low = re.sub(r'\s*\(.*?\)\s*', ' ', t.lower()).strip()
    low = re.sub(r'[\d¹²³⁴]+$', '', low).strip()
    for field, rx in LABELS:
        if re.search(rx, low):
            return field
    return None


def parse_term_sheet(raw, filed=None):
    """[{title, coupon, floating, margin, principal, currency, maturity, price, yield, benchmark, bench_yield, spread_bps,
    trade_date, ratings, conv_price, conv_rate, convertible}] — one per tranche found; [] if this is not a debt term sheet."""
    text = to_text(raw)
    head = text[:6000]
    if re.search(r'Structured\s+Investments|Contingent\s+Interest|Underlying[s]?:|Auto[- ]?Callable|Buffered|Market[- ]Linked', head, re.I):
        return []
    if not re.search(r'term\s+sheet|final\s+terms|pricing\s+supplement|summary\s+of\s+(final\s+)?terms|pricing\s+terms', head, re.I):
        return []
    toks = _tokens(text)
    tranches, cur = [], None
    for i, tok in enumerate(toks):
        m = TITLE.search(tok)
        if m and len(tok) < 220 and not _label_of(tok):
            title = re.sub(r'\s+', ' ', m.group(0)).strip()
            key = (m.group(1).lower().replace(' ', ''), m.group(4))
            if cur is None or (cur['_key'] != key and cur.get('_fields')):
                cur = {'title': title, '_key': key, '_fields': {}}
                tranches.append(cur)
            continue
        f = _label_of(tok)
        if f and i + 1 < len(toks):
            val = toks[i + 1]
            if _label_of(val) and f != 'ratings':
                continue
            extra = []                                     # values for several tranches, one per line (lines may wrap)
            for j in range(i + 2, min(len(toks), i + 16)):
                if _label_of(toks[j]) or TITLE.search(toks[j]):
                    break
                extra.append(toks[j])
            joined = re.sub(r'\s+', ' ', val + ' ' + ' '.join(extra))
            if len(re.findall(r'for\s+the\s+\d{4}\s+Notes', joined, re.I)) > 1:
                last = list(re.finditer(r'for\s+the\s+\d{4}\s+Notes', joined, re.I))[-1]
                val = joined[:last.end()]
            if cur is None:
                cur = {'title': None, '_key': None, '_fields': {}}
                tranches.append(cur)
            cur['_fields'].setdefault(f, val)
    # one table for several tranches, titles listed above it: one tranche per title, values picked "for the YYYY Notes"
    heads = []
    for m in TITLE.finditer(text[:5000]):
        k = (m.group(1).lower().replace(' ', ''), m.group(4))
        if k not in [h[1] for h in heads]:
            heads.append((re.sub(r'\s+', ' ', m.group(0)).strip(), k))
    allF = {}
    for t in tranches:
        for f, v in t['_fields'].items():
            allF.setdefault(f, v)
    if len(heads) > 1 and len([t for t in tranches if t['_fields']]) < len(heads) and any(re.search(r'for\s+the\s+\d{4}\s+Notes', v or '', re.I) for v in allF.values()):
        tranches = [{'title': h, '_key': k, '_fields': allF} for h, k in heads]
    out = []
    years = [t['_key'][1] for t in tranches if t.get('_key')]
    for t in tranches:
        F = t['_fields']
        if not F:
            continue
        # one table for several tranches: "4.750% per annum for the 2033 Notes 5.250% per annum for the 2036 Notes"
        yr = t['_key'][1] if t.get('_key') else None
        def pick(v):
            if v and yr and len(years) > 1 and re.search(r'for\s+the\s+\d{4}\s+Notes', v, re.I):
                m = re.search(r'([^|]*?)\s*for\s+the\s+' + yr + r'\s+Notes', v, re.I)
                if m:
                    parts = re.split(r'for\s+the\s+\d{4}\s+Notes', m.group(0))
                    return parts[-2] if len(parts) >= 2 else m.group(1)
            return v
        rec = {'title': t['title']}
        cpn = pick(F.get('coupon'))
        title = t['title'] or ''
        floating = bool(re.search(r'floating|SOFR|LIBOR|EURIBOR|SONIA', (cpn or '') + title, re.I))
        rec['floating'] = floating
        rec['coupon'] = None if floating else (pct(cpn) if cpn else pct(title))
        if floating:
            rec['margin_bps'] = bps(cpn) or (pct(re.sub(r'.*(?:plus|\+)', '', cpn)) * 100 if cpn and re.search(r'plus|\+', cpn) and pct(re.sub(r'.*(?:plus|\+)', '', cpn)) is not None else None)
            rec['reference'] = (re.search(r'SOFR|LIBOR|EURIBOR|SONIA|Treasury', cpn or '', re.I) or [None])[0]
        pr = pick(F.get('principal')) or title
        rec['principal'] = money(pr) or money(title)
        rec['currency'] = currency(pr + ' ' + title)
        rec['maturity'] = parse_date(pick(F.get('maturity')) or '')
        if not rec['maturity'] and yr:
            rec['maturity_year'] = int(yr)
        rec['price'] = pct(pick(F.get('price')))
        rec['yield'] = pct(pick(F.get('yld')))
        rec['benchmark'] = (pick(F.get('benchmark')) or '')[:80] or None
        by = pick(F.get('bench_yield'))
        rec['bench_yield'] = pct(by.split('/')[-1]) if by else None
        sp = pick(F.get('spread'))
        rec['spread_bps'] = bps(sp) if sp and rec['currency'] == 'USD' else None
        if rec['spread_bps'] is None and rec['yield'] is not None and rec['bench_yield'] is not None:
            rec['spread_bps'] = round((rec['yield'] - rec['bench_yield']) * 100, 1)
        rec['trade_date'] = parse_date(F.get('trade_date') or '') or filed
        rg = re.sub(r'\s+', ' ', F.get('ratings') or '')
        rec['ratings'] = rg[:140] if re.search(r'\b(Aaa|Aa[123]|A[123]|Baa[123]|Ba[123]|B[123]|Caa[123]|AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?)\b', rg) else None
        cp = F.get('conv_price')
        rec['convertible'] = bool(re.search(r'convertible', title + ' ' + head[:3000], re.I) and (cp or F.get('conv_rate')))
        if rec['convertible']:
            rec['conv_price'] = money(cp) if cp else None
            m = re.search(r'([\d.]+)\s+shares', F.get('conv_rate') or '')
            rec['conv_rate'] = float(m.group(1)) if m else None
            rec['conv_premium'] = pct(F.get('conv_premium'))
        rec['cusip'] = (re.search(r'\b[0-9A-Z]{6}\s?[0-9A-Z]{2}\s?[0-9]\b', F.get('cusip') or '') or [None])[0]
        if rec['coupon'] is None and not floating:
            continue
        if rec['principal'] is None and rec['maturity'] is None and rec.get('maturity_year') is None:
            continue
        out.append({k: v for k, v in rec.items() if v is not None})
    # drop duplicates of the same tranche (title repeated in a header list and in the table)
    seen, uniq = set(), []
    for r in out:
        k = (r.get('coupon'), r.get('maturity') or r.get('maturity_year'), r.get('floating'), r.get('currency'))
        if k in seen:
            for u in uniq:
                if (u.get('coupon'), u.get('maturity') or u.get('maturity_year'), u.get('floating'), u.get('currency')) == k:
                    for kk, vv in r.items():
                        u.setdefault(kk, vv)
            continue
        seen.add(k); uniq.append(r)
    return uniq


def parse_prospectus_cover(raw, filed=None):
    """Tranches named on a 424B2 / 424B5 cover: '$1,000,000,000 4.375% Notes due 2030' (+ the public offering price)."""
    text = to_text(raw, limit=60000)[:20000]
    if re.search(r'Structured|Contingent|Underlying|Auto[- ]?Callable|Buffered|Market[- ]Linked|Leveraged', text[:5000], re.I):
        return []
    out, seen = [], set()
    for m in re.finditer(r'((?:U\.S\.)?\s?[$€£]\s?[\d,]+(?:\.\d+)?(?:\s*(?:billion|million))?)\s+(?:aggregate\s+principal\s+amount\s+of\s+(?:its\s+|our\s+)?)?'
                         r'(Floating\s+Rate|\d{1,2}(?:\.\d{1,4})?\s?%)\s+((?:[A-Za-z\-]+\s+){0,6}?)(Notes|Debentures|Bonds)\s+due\s+(\d{4})', text, re.I):
        amt = money(m.group(1)); fl = m.group(2).lower().startswith('floating')
        key = (m.group(2).replace(' ', '').lower(), m.group(5))
        if key in seen or not amt or amt < 1e6:
            continue
        seen.add(key)
        out.append({k: v for k, v in {'title': re.sub(r'\s+', ' ', m.group(0)).strip(), 'principal': amt, 'currency': currency(m.group(1)),
                                      'coupon': None if fl else pct(m.group(2)), 'floating': fl, 'maturity_year': int(m.group(5)),
                                      'convertible': bool(re.search(r'convertible', m.group(3) or '', re.I)), 'trade_date': filed,
                                      'source_kind': 'prospectus cover'}.items() if v is not None})
    return out


# ------------------------------------------------------------------ credit agreements
COV_TYPES = [('leverage', r'(?:Consolidated\s+)?(?:Total\s+|Net\s+|Senior\s+|Secured\s+|First\s+Lien\s+)*(?:Net\s+)?Leverage\s+Ratio'),
             ('interest_coverage', r'(?:Consolidated\s+)?(?:Net\s+)?(?:Cash\s+)?Interest\s+(?:Expense\s+)?Coverage\s+Ratio|EBITDA\s+to\s+(?:Consolidated\s+)?Interest'),
             ('fixed_charge', r'Fixed\s+Charge\s+Coverage\s+Ratio'),
             ('debt_to_cap', r'(?:Debt|Indebtedness)\s+to\s+(?:Total\s+)?Capital(?:ization)?\s+Ratio|Capitalization\s+Ratio'),
             ('liquidity', r'(?:Minimum\s+|Available\s+|Consolidated\s+)?Liquidity'),
             ('net_worth', r'(?:Tangible\s+|Consolidated\s+)*Net\s+Worth'),
             ('collateral_coverage', r'Collateral\s+Coverage\s+Ratio')]


def classify_agreement(text):
    h = re.sub(r'\s+', ' ', text[:3000]).upper()
    if 'INDENTURE' in h[:1500] and 'CREDIT AGREEMENT' not in h[:1500]:
        return 'indenture'
    if re.search(r'AMENDMENT\b.{0,80}(CREDIT|LOAN)', h):
        return 'amendment'
    if re.search(r'(CREDIT|LOAN)( AND GUARANTY| AND GUARANTEE)? AGREEMENT|LOAN ARRANGEMENT|FACILITY AGREEMENT|TERM LOAN', h):
        return 'credit_agreement'
    if re.search(r'SALES AGREEMENT|EQUITY DISTRIBUTION|UNDERWRITING', h):
        return 'other'
    return 'other'


def parse_credit_agreement(raw, filed=None):
    text = to_text(raw)
    kind = classify_agreement(text)
    if kind in ('indenture', 'other'):
        return {'kind': kind}
    flat = re.sub(r'\s+', ' ', text)
    out = {'kind': kind}
    head = flat[:2500]
    m = re.search(r'dated\s+as\s+of\s+([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', head, re.I) or re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', head)
    out['dated'] = parse_date(m.group(1)) if m else filed
    m = re.search(r'((?:U\.S\.\s?)?\$\s?[\d,]{9,}(?:\.\d+)?)\s+(?:[A-Z][A-Za-z\-]+\s+){0,6}(?:CREDIT|LOAN|FACILITY|TERM)', head, re.I)
    if m:
        out['size'] = money(m.group(1))
    else:
        m = re.search(r'aggregate\s+(?:amount\s+of\s+the\s+)?(?:Revolving\s+)?Commitments?[^.$]{0,120}?(\$\s?[\d,]{9,})', flat[:400000], re.I)
        if m:
            out['size'] = money(m.group(1))
    m = re.search(r'([^.]{0,40}(?:BORROWER|COMPANY|ISSUER)[^.]{0,40})', head)
    t = re.search(r'((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH|\w+TH)?\s*(?:AMENDMENT[^.]{0,40}TO\s+)?'
                  r'(?:(?:SECOND\s+|THIRD\s+)?AMENDED\s+AND\s+RESTATED\s+)?(?:[A-Z\-]+\s+){0,4}(?:CREDIT|LOAN)(?:\s+AND\s+GUARANTY)?\s+AGREEMENT)', head)
    out['title'] = re.sub(r'\s+', ' ', t.group(1)).strip().title() if t else None
    out['facility'] = ('term loan' if re.search(r'TERM\s+LOAN', head, re.I) and not re.search(r'REVOLVING', head, re.I)
                       else 'revolving' if re.search(r'REVOLVING|Revolving\s+Credit', flat[:60000]) else 'loan')
    ref = [r for r in ('Term SOFR', 'Daily Simple SOFR', 'SOFR', 'LIBOR', 'Eurodollar', 'EURIBOR', 'SONIA', 'Base Rate', 'Prime Rate')
           if re.search(re.escape(r), flat[:300000])]
    out['benchmarks'] = ref[:4]
    # the margin: the "Applicable Margin / Rate / Spread" definition and its pricing grid
    m = re.search(r'[“"]\s?Applicable\s+(?:Margin|Rate|Spread|Percentage)\s?[”"]\s*(?::|means|shall\s+mean)(.{0,3500})', flat, re.I)
    if m:
        win = m.group(1)
        stop = re.search(r'[“"]\s?[A-Z][A-Za-z\- ]{2,40}\s?[”"]\s*(?::|means|shall mean)', win[40:])
        if stop:
            win = win[:40 + stop.start()]
        vals = [float(x) for x in re.findall(r'(\d{1,2}\.\d{1,4})\s*%', win) if 0.0 < float(x) < 15]
        vals += [float(x) / 100 for x in re.findall(r'(\d{1,4}(?:\.\d+)?)\s*(?:basis points|bps)', win, re.I) if 0 < float(x) < 1500]
        if re.search(r'Base\s+Rate|ABR|Prime', win) and len(vals) > 1:   # base-rate margins sit 1.00% below the SOFR ones
            sofr = [v for v in vals if not any(abs(v + 1.0 - w) < 0.011 for w in vals)]
            vals = sofr or vals
        if vals:
            out['margin_pct'] = [min(vals), max(vals)]
            out['margin_text'] = win[:600]
            out['grid_by'] = ('ratings' if re.search(r'Rating|Moody|S&P|Fitch|Index Debt', win, re.I)
                              else 'leverage' if re.search(r'Leverage', win, re.I) else None)
    m = re.search(r'(?:Commitment|Facility|Unused)\s+Fee(?:\s+Rate)?[^.]{0,300}?(\d\.\d{2,4})\s*%', flat, re.I)
    if m:
        out['fee_pct'] = float(m.group(1))
    m = re.search(r'[“"]\s?Floor\s?[”"]\s*(?:means|shall mean)[^.]{0,200}?(\d{1,2}(?:\.\d+)?)\s*%', flat, re.I)
    if m:
        out['floor_pct'] = float(m.group(1))
    m = re.search(r'[“"]\s?(?:Maturity|Termination)\s+Date\s?[”"]\s*(?::|means|shall mean)([^“"]{0,400})', flat, re.I)
    if m:
        d = parse_date(m.group(1))
        if d:
            out['maturity'] = d
    covs = []
    for typ, rx in COV_TYPES:
        for mm in re.finditer('(?:' + rx + r')(?:(?!Ratio\b)[^.;]){0,180}?(?P<dir>not\s+(?:to\s+)?exceed|(?:be\s+)?(?:less|greater|more)\s+than|at\s+least|no\s+(?:less|greater|more)\s+than|minimum\s+of|maximum\s+of)[^.;]{0,90}?'
                              r'(?P<val>\d{1,2}(?:\.\d{1,2})?\s*(?:to|:)\s*1(?:\.0{1,2})?|\$\s?[\d,]{6,}(?:\.\d+)?|[A-Z][a-z]+\s+(?:Billion|Million)\s+Dollars\s+\(\$[\d,]+\))', flat, re.I):
            ps = [x.end() for x in re.finditer(r'\.\s+(?=[A-Z(“"])', flat[max(0, mm.start() - 600):mm.start()])]
            sent_s = max(0, mm.start() - 600) + ps[-1] if ps else max(0, mm.start() - 300)
            nx = re.search(r'\.\s+(?=[A-Z(“"])|;', flat[mm.end():mm.end() + 400])
            sentence = flat[sent_s:mm.end() + (nx.start() + 1 if nx else 200)]
            if re.search(r'Pro\s+Forma\s+Basis|Incur|incurrence|permitted\s+(?:to|if)|Restricted\s+Payment|may\s+make', sentence, re.I):
                maint = False
            else:
                maint = bool(re.search(r'last\s+day\s+of\s+(?:any|each)\s+(?:fiscal\s+)?quarter|at\s+any\s+time|as\s+of\s+the\s+end\s+of|shall\s+not\s+permit|will\s+not\s+(?:at\s+any\s+time\s+)?permit|shall\s+(?:ensure|maintain)', sentence, re.I))
            v = mm.group('val')
            if '$' in v:
                val, unit = money(v), 'usd'
            else:
                val, unit = float(re.match(r'(\d{1,2}(?:\.\d{1,2})?)', v).group(1)), 'x'
            dw = mm.group('dir')
            direction = 'max' if re.search(r'exceed|greater|more\s+than|maximum', dw, re.I) and not re.search(r'no\s+(?:greater|more)', dw, re.I) else 'min'
            if re.search(r'no\s+(?:greater|more)\s+than', dw, re.I):
                direction = 'max'
            covs.append({'type': typ, 'limit': val, 'unit': unit, 'direction': direction, 'maintenance': maint,
                         'text': sentence[:420].strip()})
            if len(covs) > 24:
                break
    # keep the maintenance covenants first and one per (type, direction)
    covs.sort(key=lambda c: (not c['maintenance'],))
    seen, keep = set(), []
    for c in covs:
        k = (c['type'], c['direction'], c['maintenance'])
        if k in seen:
            continue
        seen.add(k); keep.append(c)
    out['covenants'] = keep[:8]
    return {k: v for k, v in out.items() if v not in (None, [], '')}


# ------------------------------------------------------------------ XBRL instance (dimensional debt facts)
AXES = ('DebtInstrumentAxis', 'LongtermDebtTypeAxis', 'ShortTermDebtTypeAxis', 'LineOfCreditFacilityAxis', 'CreditFacilityAxis')
INST_CONCEPTS = {
    'DebtInstrumentInterestRateStatedPercentage': 'coupon', 'DebtInstrumentFaceAmount': 'face', 'DebtInstrumentCarryingAmount': 'carrying',
    'LongTermDebt': 'carrying', 'LongTermDebtNoncurrent': 'carrying', 'DebtInstrumentMaturityDate': 'maturity',
    'DebtInstrumentMaturityDateRangeEnd': 'maturity', 'DebtInstrumentBasisSpreadOnVariableRate1': 'spread',
    'DebtInstrumentInterestRateEffectivePercentage': 'effective', 'LineOfCreditFacilityMaximumBorrowingCapacity': 'capacity',
    'LineOfCreditFacilityRemainingBorrowingCapacity': 'available', 'LineOfCredit': 'drawn', 'LongTermLineOfCredit': 'drawn',
    'LineOfCreditFacilityCommitmentFeePercentage': 'fee', 'DebtInstrumentConvertibleConversionPrice1': 'conv_price',
    'DebtInstrumentConvertibleConversionRatio1': 'conv_ratio', 'DebtInstrumentFairValue': 'fair_value', 'LongTermDebtFairValue': 'fair_value',
    'ShortTermBorrowings': 'carrying', 'CommercialPaper': 'carrying', 'LineOfCreditFacilityInterestRateAtPeriodEnd': 'rate_now',
    'DebtInstrumentInterestRateStatedPercentageRateRangeMinimum': 'coupon_min', 'DebtInstrumentInterestRateStatedPercentageRateRangeMaximum': 'coupon_max',
    'ShortTermDebtWeightedAverageInterestRate': 'rate_now', 'DebtWeightedAverageInterestRate': 'rate_now',
}


def humanize(member):
    name = member.split(':')[-1]
    name = re.sub(r'Member$', '', name)
    words = {'Zero': '0', 'One': '1', 'Two': '2', 'Three': '3', 'Four': '4', 'Five': '5', 'Six': '6', 'Seven': '7', 'Eight': '8', 'Nine': '9'}
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', name)
    s = re.sub(r'Twenty (Twenty|Thirty|Forty|Fifty|Sixty)\s*(\w+)?', lambda m: '20' + {'Twenty': '2', 'Thirty': '3', 'Forty': '4', 'Fifty': '5', 'Sixty': '6'}[m.group(1)]
               + (words.get(m.group(2), '0') if m.group(2) in words else '0' + (' ' + m.group(2) if m.group(2) else '')), s)
    s = re.sub(r'\bA(\d)', r'\1', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_labels(raw):
    """{local member name: label} from a label linkbase (_lab.xml)."""
    out = {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    X = '{http://www.w3.org/1999/xlink}'
    for link in root.iter():
        if not link.tag.endswith('labelLink'):
            continue
        locs, labs, arcs = {}, {}, []
        for e in link:
            t = e.tag.split('}')[-1]
            if t == 'loc':
                locs[e.get(X + 'label')] = (e.get(X + 'href') or '').split('#')[-1]
            elif t == 'label':
                role = e.get(X + 'role') or ''
                if role.endswith('/label') or role.endswith('terseLabel'):
                    labs.setdefault(e.get(X + 'label'), (e.text or '').strip())
            elif t == 'labelArc':
                arcs.append((e.get(X + 'from'), e.get(X + 'to')))
        for f, t in arcs:
            if f in locs and t in labs:
                name = re.sub(r'^[a-z\-]+_', '', locs[f])
                out.setdefault(name, labs[t])
    return out


def classify_instrument(label):
    l = label.lower()
    if 'convertible' in l:
        return 'convertible'
    if 'commercial paper' in l:
        return 'commercial_paper'
    if re.search(r'revolv|line of credit|credit facilit|credit agreement', l):
        return 'revolver'
    if 'term loan' in l or re.search(r'\bloan\b', l):
        return 'loan'
    if re.search(r'asset[- ]backed|securitiz|receivable|warehouse|abs\b|conduit', l):
        return 'abs'
    if re.search(r'finance lease|capital lease', l):
        return 'lease'
    if re.search(r'mortgage', l):
        return 'mortgage'
    if re.search(r'note|debenture|bond|senior|subordinated|debt', l):
        return 'notes'
    return 'other'


def parse_instance(raw, labels=None, max_age_days=400):
    """Debt instruments in one XBRL instance: grouped by the DebtInstrumentAxis member (else the debt-type / facility
    member), values at the latest date each was reported; RangeAxis min/max kept as ranges; the variable-rate benchmark
    member (SOFR, LIBOR...) as the reference rate."""
    labels = labels or {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    ctx = {}
    for c in root.iter():
        if not c.tag.endswith('}context'):
            continue
        mem, end = {}, None
        for e in c.iter():
            if e.tag.endswith('explicitMember'):
                mem[e.get('dimension').split(':')[-1]] = e.text.strip()
            elif e.tag.endswith('}instant') or e.tag.endswith('}endDate'):
                end = e.text.strip()
        ctx[c.get('id')] = (mem, end)
    groups = {}
    latest_any = None
    for e in root:
        name = e.tag.split('}')[-1]
        field = INST_CONCEPTS.get(name)
        if not field or e.get('contextRef') not in ctx:
            continue
        mem, end = ctx[e.get('contextRef')]
        if not end:
            continue
        key = next((mem[a] for a in AXES if a in mem), None)
        if key is None:
            continue
        if set(mem) - set(AXES) - {'RangeAxis', 'VariableRateAxis', 'ConsolidatedEntitiesAxis', 'LegalEntityAxis', 'DebtInstrumentConvertibleAxis'}:
            continue                                     # by segment, geography, currency... — not one instrument
        txt = (e.text or '').strip()
        if not txt:
            continue
        rng = mem.get('RangeAxis', '').split(':')[-1]
        if rng.startswith('Minimum'):
            field = field + '_min' if not field.endswith('_min') else field
        elif rng.startswith('Maximum'):
            field = field + '_max' if not field.endswith('_max') else field
        g = groups.setdefault(key, {'member': key, 'types': set(), 'fields': {}})
        for a in ('LongtermDebtTypeAxis', 'ShortTermDebtTypeAxis'):
            if a in mem and mem[a] != key:
                g['types'].add(mem[a])
        if 'VariableRateAxis' in mem:
            g['reference'] = humanize(mem['VariableRateAxis']).replace('Secured Overnight Financing Rate Sofr', 'SOFR')
        prev = g['fields'].get(field)
        if prev is None or end > prev[0]:
            g['fields'][field] = (end, txt)
        latest_any = max(latest_any or end, end)
    out = []
    for key, g in groups.items():
        F = g['fields']
        last = max(v[0] for v in F.values())
        if latest_any and (dt.date.fromisoformat(latest_any[:10]) - dt.date.fromisoformat(last[:10])).days > max_age_days:
            continue                                     # an instrument only in the comparative year: repaid
        local = key.split(':')[-1]
        label = labels.get(local) or humanize(key)
        label = re.sub(r'\s*\[Member\]\s*$', '', label)
        types = ' '.join(labels.get(t.split(':')[-1]) or humanize(t) for t in g['types'])
        rec = {'name': label, 'kind': classify_instrument(label + ' ' + types), 'as_of': last}
        for f, (end, v) in F.items():
            try:
                val = float(v)
            except ValueError:
                val = v[:10] if re.match(r'\d{4}-\d{2}-\d{2}', v) else None
            if val is None:
                continue
            if f in ('carrying', 'face', 'capacity', 'available', 'drawn', 'fair_value') and end != last:
                continue                                 # balances only at the instrument's latest date
            rec[f] = val
        if g.get('reference'):
            rec['reference'] = g['reference']
        m = re.search(r'(\d{1,2}(?:\.\d{1,4})?)\s?%', label) or re.search(r'(\d)\s?Point\s?(\d+)\s?Percent', local)
        if 'coupon' not in rec and m:
            rec['coupon'] = float(m.group(1)) / 100 if m.lastindex == 1 else float(f'{m.group(1)}.{m.group(2)}') / 100
        m = re.search(r'(?:due|Due)\s*(?:\w+\s+)?(20\d\d|19\d\d)', label)
        if 'maturity' not in rec and m:
            rec['maturity_year'] = int(m.group(1))
        rec['floating'] = bool(rec.get('reference') or 'spread' in rec or re.search(r'floating|variable|sofr|libor|term loan|revolv|commercial paper', label, re.I))
        out.append(rec)
    merged = {}                                          # the same instrument under two members (type axis / instrument axis)
    for r in out:
        k = r['name'].lower()
        if k in merged:
            for f, v in r.items():
                if merged[k].get(f) in (None, False):
                    merged[k][f] = v
        else:
            merged[k] = r
    out = list(merged.values())
    out.sort(key=lambda r: -(r.get('carrying') or r.get('face') or r.get('capacity') or 0))
    return out
