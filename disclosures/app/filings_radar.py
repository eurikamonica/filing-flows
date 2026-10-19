"""Filings radar (research-filings): the filings that flag trouble or change the share count, and the money around them.

  red flags      NT 10-K / NT 10-Q (a late annual or quarterly report, with the company's reason), 8-K Item 4.01 (auditor
                 dismissed or resigned, disagreements, material weaknesses), Item 4.02 (earlier statements no longer to be
                 relied on: which periods, why), Item 3.01 (an exchange's deficiency or delisting notice: which rule, the deadline)
  SEC letters    CORRESP (the company's answers) and UPLOAD (the staff's letters): threads per company, the form reviewed,
                 topics (revenue recognition, non-GAAP, segments, impairment, going concern, crypto …). The SEC releases
                 them at least 20 business days after a review is closed, so every thread here is a finished review.
  capital        buyback authorizations (8-K: the amount, % of market cap), dividend declarations (amount, record and payable
                 dates — the ex-dividend date equals the record date since T+1 settlement, May 2024) and the last fiscal
                 year's repurchases and dividends from XBRL frames (as % of market cap)
  dilution       shelf registrations (S-3 / S-3ASR / F-3), takedowns and at-the-market programs (424B5: size, % of market
                 cap), and the change in shares outstanding over a year (XBRL CommonStockSharesOutstanding)
  IPOs           S-1 / F-1 registrations and 424B4 pricings (price, shares, raise, symbol, the lock-up and its expiry), the
                 return since pricing
  deals          merger agreements (8-K 1.01 / 8.01), merger proxies (DEFM14A / PREM14A), tender offers (SC TO-T, SC 14D9):
                 cash and stock terms per share, the spread to the target's price, the expected close, an annualized spread
  CEO pay        XBRL pay-versus-performance (ecd: PeoTotalCompAmt, PeoActuallyPaidCompAmt, TotalShareholderRtnAmt,
                 PeerGroupTotalShareholderRtnAmt): pay against the shareholder return
  contracts      USAspending.gov contract obligations by recipient (last 90 days, matched conservatively to listed companies)
  & lobbying     and the Senate LDA lobbying filings (in-house expenses + outside firms' income per quarter), against the
                 officials' trades the hub reads (House and Senate periodic transaction reports)

Discovery: EDGAR's daily form indexes (every filing of the forms above), the hub's 8-K events (app/events8k.py: items
and topics already split, so only the few 8-Ks that matter are read again here). Every source is optional: a failed one
keeps its previous data and is reported in status.json.

Root (the branch research-filings, one commit force-pushed by .github/workflows/research-filings.yml):
  state.json, cache/ (daily index rows, parsed filings, frames, contracts, lobbying, prices), public/ (published by
  scan.yml at disclosures/data/research/filings/): index.json, redflags.json, letters.json, capital.json, dilution.json,
  ipos.json, deals.json, paycomp.json, gov.json, c/<TICKER>.json, status.json.

    python disclosures/app/filings_radar.py all --root rf --events8k <dir of cache/events8k or market/events8k.json>
        --officials <officials-trades.json> --prices rh/public --minutes 40
"""
import argparse
import binascii
import datetime as dt
import gzip
import json
import math
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Client, read_json, write_json  # noqa: E402
import events8k as E  # noqa: E402

PARSER = 1                   # bump when a parser changes: the filings on file are read again
DAILY = 'https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx'
FOLDER = 'https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/'
TICKERS = 'https://www.sec.gov/files/company_tickers.json'
FRAME = 'https://data.sec.gov/api/xbrl/frames/{tax}/{concept}/{unit}/{period}.json'
CONCEPT = 'https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{tax}/{concept}.json'
CHART = 'https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d'
USA = 'https://api.usaspending.gov/api/v2/'
LDA = ['https://lda.senate.gov/api/v1/', 'https://lda.gov/api/v1/']

FORMS = {
    'NT 10-K': 'late', 'NT 10-K/A': 'late', 'NT 10-Q': 'late', 'NT 10-Q/A': 'late', 'NT 20-F': 'late',
    'CORRESP': 'letter', 'UPLOAD': 'letter',
    'S-1': 'ipo_reg', 'F-1': 'ipo_reg', '424B4': 'ipo_price',
    'S-3': 'shelf', 'S-3ASR': 'shelf', 'F-3': 'shelf', 'F-3ASR': 'shelf', '424B5': 'takedown',
    'DEFM14A': 'deal', 'PREM14A': 'deal', 'DEFM14C': 'deal', 'S-4': 'deal',
    'SC TO-T': 'tender', 'SCHEDULE TO-T': 'tender', 'SC 14D9': 'tender', 'SCHEDULE 14D9': 'tender',
}
KEEP_DAYS = {'redflags': 730, 'letters': 730, 'offerings': 400, 'ipos': 800, 'deals': 900, 'buybacks': 400, 'dividends': 400}
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                           'september', 'october', 'november', 'december'])}
DOT = r'(?:[^.]|\.(?=\d))'       # any character but a sentence's full stop (decimal points allowed)
DATE_RX = r'((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+\d{1,2},\s+\d{4})'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def parse_date(s):
    """'October 15, 2026' / 'Oct. 15, 2026' → '2026-10-15' (None when not a date)."""
    m = re.match(r'\s*([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})', s or '')
    if not m:
        return None
    name = m.group(1).lower()
    mon = MONTHS.get(name) or next((v for k, v in MONTHS.items() if k.startswith(name[:3])), None)
    try:
        return dt.date(int(m.group(3)), mon, int(m.group(2))).isoformat() if mon else None
    except ValueError:
        return None


def amount(num, unit=''):
    """'1.5', 'billion' → 1.5e9; '20,000,000', '' → 2e7."""
    try:
        v = float(str(num).replace(',', ''))
    except ValueError:
        return None
    u = (unit or '').lower()
    return v * (1e9 if u.startswith('b') else 1e6 if u.startswith('m') else 1e3 if u.startswith('t') and u != 'trillion' else 1e12 if u == 'trillion' else 1)


def text_of(doc):
    """A document (HTML or text) → one string of plain text (paragraphs joined by newlines)."""
    return '\n'.join(E.html_text(doc or ''))


# ------------------------------------------------------------------ the daily form index
LINE = re.compile(r'^(?P<form>\S+(?: \S+)*?)\s{2,}(?P<name>.+?)\s{2,}(?P<cik>\d+)\s+(?P<date>\d{8})\s+'
                  r'(?P<path>edgar/data/\d+/(?P<acc>\d{10}-\d{2}-\d{6})\.txt)\s*$')


def parse_form_index(text, forms=FORMS):
    """EDGAR's form.YYYYMMDD.idx → [(form, cik, company, filed, accession)] for the forms of interest (each filing once per
    company: a tender offer is listed under the bidder and the target)."""
    out, seen = [], set()
    for line in (text or '').splitlines():
        m = LINE.match(line.rstrip())
        if not m or m.group('form') not in forms:
            continue
        d = m.group('date')
        key = (m.group('acc'), m.group('cik'))
        if key in seen:
            continue
        seen.add(key)
        out.append((m.group('form'), int(m.group('cik')), m.group('name').strip(), f'{d[:4]}-{d[4:6]}-{d[6:]}', m.group('acc')))
    return out


def business_days(today, n):
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------ red flags
def parse_nt(text):
    """Form 12b-25 (NT 10-K / NT 10-Q): the company's reason (Part III) and whether it expects a significant change in results."""
    t = re.sub(r'\s+', ' ', text or '')
    m = re.search(r'(?i)part\s+iii\b.{0,40}?narrative(.*?)(?:part\s+iv\b|$)', t) or re.search(r'(?i)part\s+iii\b(.*?)(?:part\s+iv\b|$)', t)
    reason = m.group(1) if m else ''
    reason = re.sub(r'(?i)^.*?(?:could not be filed[^.]*period\.?|the prescribed time period\.?)', '', reason).strip(' .:-–—()')
    reason = re.sub(r'\s+', ' ', reason)
    if len(reason) > 420:
        cut = reason[:420]
        reason = cut[:cut.rfind('. ') + 1] if '. ' in cut[100:] else cut.rsplit(' ', 1)[0] + ' …'
    sig = None
    m = re.search(r'(?i)significant change in results of operations.{0,400}?(\[\s*[xX✓☒]\s*\]|☒|\byes\b)\s*yes|yes\s*(\[\s*[xX]\s*\]|☒)', t)
    if m:
        sig = True
    elif re.search(r'(?i)significant change in results of operations.{0,400}?(☒|\[\s*[xX]\s*\])\s*no', t):
        sig = False
    return {'reason': reason, 'significant_change': sig}


AUD_NAME = r'([A-Z][A-Za-z0-9&.\'’+\- ]{2,90}?(?:,\s*(?:LLP|LLC|PLLC|P\.C\.|P\.A\.|Ltd\.?|Inc\.?)(?![A-Za-z]))?)'


def _clean_firm(s):
    s = re.split(r'\b\d{4},?\s+', s or '')[-1]             # "… On October 13, 2026, Stephano Slack LLC" → the name
    s = re.sub(r'\s*\((?:the\s+)?[“"].*$', '', s).strip(' ,;')
    s = re.sub(r'\.$', '', s) if not re.search(r'\b[A-Z]\.[A-Z]\.?$', s) else s
    s = re.sub(r'^(?:the\s+(?:firm|accounting firm)\s+of\s+)', '', s, flags=re.I)
    return s if 2 < len(s) <= 90 else None


def parse_auditor_change(text):
    """8-K Item 4.01 → who left (dismissed / resigned / declined to stand), who was engaged, disagreements, reportable events."""
    t = re.sub(r'\s+', ' ', text or '')
    out = {'change': None, 'old': None, 'new': None, 'disagreements': None, 'material_weakness': False, 'going_concern': False}
    m = re.search(r'(?:dismissed|terminated the engagement of|approved the dismissal of)\s+' + AUD_NAME + r'\s*(?:\(|,|\s+as\s|\s+from\s)', t)
    if m:
        out.update(change='dismissed', old=_clean_firm(m.group(1)))
    m2 = re.search(AUD_NAME + r'\s*(?:\([^)]{0,80}\))?\s*,?\s*(?:resigned|notified the Company[^.]{0,80}?(?:resign|decline)|informed the Company[^.]{0,80}?(?:resign|decline)|declined to stand for re-?(?:election|appointment))', t)
    if m2 and not out['old']:
        firm = _clean_firm(m2.group(1))
        firm = re.sub(r'^(?:On [A-Z][a-z]+ \d{1,2}, \d{4},?\s*)', '', firm or '') or None
        out.update(change='declined' if re.search(r'declin', m2.group(0), re.I) else 'resigned', old=firm)
    m3 = re.search(r'(?:engaged|appointed|approved the engagement of|selected|retained|engagement of)\s+' + AUD_NAME
                   + r'\s*(?:\(|,|\s+as\s+(?:the\s+)?(?:Company|its|our)|\s+to\s+serve)', t)
    if m3:
        new = _clean_firm(m3.group(1))
        if new and new != out['old'] and not re.match(r'(?i)(?:the|its|a|an)\s', new):
            out['new'] = new
    if re.search(r'(?i)\bthere (?:were|have been) no (?:\(\w+\)\s*)?disagreements', t):
        out['disagreements'] = False
    if re.search(r'(?i)\b(?:there (?:was|were) (?:a |one or more )?disagreements?|except for the (?:disagreement|matter))', t):
        out['disagreements'] = True
    out['material_weakness'] = bool(re.search(r'(?i)material weakness', t))
    out['going_concern'] = bool(re.search(r'(?i)going concern|substantial doubt', t))
    return out


def parse_restatement(text):
    """8-K Item 4.02 → the periods that should no longer be relied on and the first sentence explaining why."""
    t = re.sub(r'\s+', ' ', text or '')
    periods = []
    for m in re.finditer(r'(?i)\bended\s+' + DATE_RX + r'((?:\s*,?\s*(?:and\s+)?' + DATE_RX + r')*)', t):
        for x in re.finditer(DATE_RX, m.group(0)):
            d = parse_date(x.group(1))
            if d and d not in periods:
                periods.append(d)
    why = ''
    for s in re.split(r'(?<=[.;])\s+(?=[A-Z])', t):
        if re.search(r'(?i)\b(error|errors|misstat|incorrect|improperly|miscalculat|restat|did not properly|overstat|understat)', s) and 40 <= len(s) <= 420:
            why = s.strip()
            break
    return {'periods': sorted(periods)[-6:], 'reason': why}


LISTING_REASONS = [
    ('bid_price', r'(?i)(minimum|closing) bid price|5550\(a\)\(2\)|5450\(a\)\(1\)|\$1\.00 per share', 'share price below $1'),
    ('filing', r'(?i)timely file|5250\(c\)|delinquent in filing|periodic report', 'a late periodic report'),
    ('equity', r'(?i)stockholders[’\']? equity|shareholders[’\']? equity|5550\(b\)\(1\)|5450\(b\)\(1\)', "shareholders' equity below the minimum"),
    ('market_value', r'(?i)market value of (?:listed securities|publicly held shares)|MVLS|MVPHS', 'market value below the minimum'),
    ('annual_meeting', r'(?i)annual meeting', 'no annual meeting held'),
    ('audit_committee', r'(?i)audit committee', 'audit committee requirements'),
    ('holders', r'(?i)round lot holders|publicly held shares|total holders', 'too few holders'),
]


def parse_listing_notice(text):
    """8-K Item 3.01 → the exchange, the rule broken (in plain words), the deadline to regain compliance, and whether the
    exchange has already decided to delist or suspend."""
    t = re.sub(r'\s+', ' ', text or '')
    ex = ('NYSE American' if re.search(r'NYSE American', t) else 'NYSE' if re.search(r'New York Stock Exchange|\bNYSE\b', t)
          else 'Nasdaq' if re.search(r'(?i)nasdaq', t) else None)
    key, label = next(((k, lab) for k, rx, lab in LISTING_REASONS if re.search(rx, t)), ('other', 'a listing rule'))
    m = re.search(r'(?i)(?:until|through|by|on or before)\s+' + DATE_RX + r'[^.]{0,60}?(?:regain|cure|evidence) compliance', t) \
        or re.search(r'(?i)regain compliance[^.]{0,120}?(?:until|through|by|on or before)\s+' + DATE_RX, t) \
        or re.search(r'(?i)(\d{2,3})(?:-| )(?:calendar )?days?[^.]{0,80}?regain compliance', t)
    deadline = None
    if m:
        deadline = parse_date(m.group(1)) if not m.group(1).isdigit() else None
    determination = bool(re.search(r'(?i)(staff )?(?:delisting )?determination|suspend(?:ed|sion)? (?:of )?trading|will be delisted|form 25|'
                                   r'decided to (?:delist|commence delisting)|delisting proceedings', t))
    return {'exchange': ex, 'reason_key': key, 'reason': label, 'deadline': deadline, 'determination': determination}


def severity(kind, d):
    """high / medium / low for a red flag."""
    if kind == 'late':
        return 'high' if d.get('form', '').startswith('NT 10-K') or d.get('significant_change') else 'medium'
    if kind == 'restatement':
        return 'high'
    if kind == 'auditor':
        return 'high' if d.get('change') in ('resigned', 'declined') or d.get('disagreements') else 'medium'
    if kind == 'listing':
        return 'high' if d.get('determination') else 'medium' if d.get('reason_key') in ('filing', 'equity') else 'low'
    return 'low'


FLAG_LABEL = {'late': 'late filing notice', 'auditor': 'auditor change', 'restatement': 'restatement (non-reliance)',
              'listing': 'exchange listing notice'}


# ------------------------------------------------------------------ SEC comment letters
LETTER_TOPICS = [
    ('revenue', r'(?i)revenue recognition|ASC 606|performance obligations?|principal versus agent|gross versus net|variable consideration', 'revenue recognition'),
    ('non_gaap', r'(?i)non-gaap|Item 10\(e\)|adjusted EBITDA|adjusted earnings', 'non-GAAP measures'),
    ('segments', r'(?i)\bsegments?\b|ASC 280|chief operating decision maker|CODM', 'segments'),
    ('impairment', r'(?i)impairment|goodwill', 'impairment / goodwill'),
    ('going_concern', r'(?i)going concern|substantial doubt', 'going concern'),
    ('crypto', r'(?i)crypto|digital assets?|bitcoin|ethereum|\btokens?\b|stablecoin', 'crypto assets'),
    ('liquidity', r'(?i)liquidity and capital resources|critical accounting estimates|known trends', 'MD&A / liquidity'),
    ('china', r'(?i)variable interest entit|\bVIEs?\b|\bPRC\b|Holding Foreign Companies Accountable|Hong Kong', 'China / VIE structure'),
    ('cyber', r'(?i)cybersecurity|Item 1C|Item 106', 'cybersecurity disclosure'),
    ('controls', r'(?i)internal control over financial reporting|material weakness|disclosure controls', 'internal controls'),
    ('tax', r'(?i)income taxes|valuation allowance|uncertain tax', 'income taxes'),
    ('related', r'(?i)related part(?:y|ies)', 'related parties'),
    ('acquisitions', r'(?i)business combination|purchase price allocation|ASC 805', 'acquisitions'),
    ('reserves', r'(?i)proved reserves|reserve estimates|Item 1202|S-K 1300|mineral resources', 'reserves'),
    ('climate', r'(?i)climate', 'climate'),
    ('ai', r'(?i)artificial intelligence|\bAI\b', 'AI disclosure'),
    ('leases', r'(?i)\bleases?\b|ASC 842', 'leases'),
    ('stock_comp', r'(?i)stock-based compensation|share-based compensation', 'stock compensation'),
    ('inventory', r'(?i)\binventor(?:y|ies)\b', 'inventory'),
]


def letter_topics(text, n=3):
    t = text or ''
    scored = []
    for key, rx, _ in LETTER_TOPICS:
        k = len(re.findall(rx, t))
        if k:
            scored.append((-k, key))
    return [k for _, k in sorted(scored)[:n]]


def letter_about(text):
    """'Form 10-K for the Fiscal Year Ended December 31, 2025' → ('10-K', '2025-12-31')."""
    t = re.sub(r'\s+', ' ', text or '')
    m = re.search(r'(?i)Form\s+(10-K|10-Q|20-F|40-F|8-K|S-1|S-4|F-1|S-3|10-K/A|20-F/A)\b[^.]{0,80}?(?:ended|dated|filed)\s+' + DATE_RX, t)
    if m:
        return m.group(1).upper(), parse_date(m.group(2))
    m = re.search(r'(?i)Form\s+(10-K|10-Q|20-F|40-F|8-K|S-1|S-4|F-1|S-3|DEF 14A)\b', t)
    return (m.group(1).upper(), None) if m else (None, None)


def letter_closing(text):
    return bool(re.search(r'(?i)we have completed our review|completed its review of your filing', text or ''))


def uudecode(block):
    """A uuencoded document (EDGAR PDFs in a submission .txt) → bytes."""
    out = bytearray()
    lines = block.splitlines()
    started = False
    for line in lines:
        if not started:
            started = line.startswith('begin ')
            continue
        if line.strip() in ('end', '`', ''):
            if line.strip() == 'end':
                break
            continue
        try:
            out += binascii.a2b_uu(line)
        except binascii.Error:
            try:
                n = (((ord(line[0]) - 32) & 63) * 4 + 5) // 3
                out += binascii.a2b_uu(line[:n])
            except (binascii.Error, IndexError):
                continue
    return bytes(out)


def pdf_text(data, limit=60000):
    try:
        from pypdf import PdfReader
        import io
        r = PdfReader(io.BytesIO(data))
        return '\n'.join((p.extract_text() or '') for p in r.pages[:20])[:limit]
    except Exception:
        return ''


def submission_text(txt, prefer=None):
    """A submission .txt → the plain text of its main document (HTML, text, or a uuencoded PDF when pypdf is installed)."""
    docs = E.documents(txt or '')
    if not docs:
        return text_of(txt)
    main = next((d for d in docs if prefer and d[0].startswith(prefer)), docs[0])
    body = main[2]
    if re.search(r'(?m)^begin \d{3} ', body[:2000]):
        return pdf_text(uudecode(body))
    return text_of(body)


# ------------------------------------------------------------------ buybacks, dividends
def parse_buyback(text):
    """A buyback authorization → {amount, shares, increase, expires} (the largest dollar figure near "repurchase")."""
    t = re.sub(r'\s+', ' ', text or '')
    best = None
    for m in re.finditer(r'(?i)(?:repurchase|buy ?back|share purchase)' + DOT + r'{0,160}?(?:up to|of up to|totaling|of)\s+(?:an aggregate of\s+)?\$\s?([\d,.]+)\s*(million|billion|thousand)?', t):
        v = amount(m.group(1), m.group(2))
        if v and (best is None or v > best):
            best = v
    for m in re.finditer(r'(?i)\$\s?([\d,.]+)\s*(million|billion)\s+(?:(?:share|stock|common stock)\s+)?(?:repurchase|buyback|buy-back)', t):
        v = amount(m.group(1), m.group(2))
        if v and (best is None or v > best):
            best = v
    shares = None
    m = re.search(r'(?i)(?:repurchase|buy ?back)' + DOT + r'{0,80}?up to\s+([\d,.]+)\s*(million)?\s+(?:shares|of its)', t)
    if m:
        shares = amount(m.group(1), m.group(2))
    inc = bool(re.search(r'(?i)(?:increase[sd]?|additional|expand(?:ed|s)?|add(?:ed|s)?)\s' + DOT + r'{0,60}(?:repurchase|buyback)|(?:repurchase|buyback)' + DOT + r'{0,80}\bincrease', t))
    exp = None
    m = re.search(r'(?i)(?:expires?|expiring|through|until)\s+(?:on\s+)?' + DATE_RX, t)
    if m:
        exp = parse_date(m.group(1))
    no_exp = bool(re.search(r'(?i)(?:no|does not have an?) (?:fixed )?expiration', t))
    return {'amount': best, 'shares': shares, 'increase': inc, 'expires': exp, 'no_expiration': no_exp}


def parse_dividend(text):
    """A dividend declaration → {amount, freq, record, payable, change}."""
    t = re.sub(r'\s+', ' ', text or '')
    m = re.search(r'(?i)(quarterly|monthly|semi-annual|annual|special|interim|final)?\s*(?:cash\s+)?dividends?\s+(?:of|in the amount of)\s+\$\s?(\d+\.\d+|\d+)\s+per\s+(?:common\s+|ordinary\s+)?(?:share|unit)', t) \
        or re.search(r'(?i)dividends?\s+(?:to|at|of)\s+\$\s?(\d+\.\d+|\d+)\s+per\s+(?:common\s+|ordinary\s+)?(?:share|unit)()', t) \
        or re.search(r'(?i)\$\s?(\d+\.\d+|\d+)\s+per\s+(?:common\s+|ordinary\s+)?(?:share|unit)' + DOT + r'{0,60}?(quarterly|monthly|semi-annual|annual|special)?\s*(?:cash\s+)?dividend', t)
    amt, freq = None, None
    if m:
        g = m.groups()
        if len(g) == 2 and g[1] and re.match(r'\d', g[1]):
            freq, amt = g[0], float(g[1])
        else:
            amt, freq = float(g[0]), (g[1] if len(g) > 1 else None)
    if not freq:
        f = re.search(r'(?i)\b(quarterly|monthly|semi-annual|annual|special)\b', t)
        freq = f.group(1) if f else None
    rec = re.search(r'(?i)(?:holders|shareholders|stockholders|unitholders) of record\s+(?:as of|at the close of business(?: on)?|on|of)?\s*(?:the close of business on\s+)?' + DATE_RX, t)
    pay = re.search(r'(?i)payable\s+(?:on\s+)?' + DATE_RX, t)
    change = ('suspend' if re.search(r'(?i)suspend(?:s|ed|ing)? (?:its |the )?(?:quarterly )?dividend', t)
              else 'initiate' if re.search(r'(?i)initiat(?:e|es|ed|ing|ion of) (?:a |its |the )?(?:first|inaugural|quarterly )?(?:cash )?dividend|first(?:-ever)? (?:quarterly )?dividend', t)
              else 'increase' if re.search(r'(?i)(?:increase[sd]?|rais(?:e|es|ed))\s' + DOT + r'{0,60}dividend|dividend' + DOT + r'{0,60}\bincrease', t)
              else 'decrease' if re.search(r'(?i)(?:reduc(?:e|es|ed)|lower(?:s|ed)?|cut(?:s)?)\s' + DOT + r'{0,60}dividend', t)
              else 'special' if (freq or '').lower() == 'special' else 'regular')
    return {'amount': amt, 'freq': (freq or '').lower() or None, 'record': parse_date(rec.group(1)) if rec else None,
            'payable': parse_date(pay.group(1)) if pay else None, 'change': change}


def per_year(freq):
    return {'quarterly': 4, 'monthly': 12, 'semi-annual': 2, 'annual': 1}.get(freq or '', None)


# ------------------------------------------------------------------ dilution, IPOs
def parse_offering(text, form):
    """424B5 / S-3 cover → {kind: atm | firm | shelf | debt | other, amount, shares, price}."""
    t = re.sub(r'\s+', ' ', (text or '')[:60000])
    head = t[:12000]
    debt = bool(re.search(r'(?i)\d+(?:\.\d+)?%\s+(?:senior\s+|subordinated\s+)?notes due|medium-term notes|debt securities offered', head)) \
        and not re.search(r'(?i)shares of (?:our |its )?(?:class [a-c] )?common stock', head[:4000])
    if form.startswith(('S-3', 'F-3')):
        m = re.search(r'(?i)(?:up to|aggregate (?:initial )?offering price of(?: up to)?)\s+\$\s?([\d,.]+)\s*(million|billion)?', head)
        return {'kind': 'shelf', 'amount': amount(m.group(1), m.group(2)) if m else None, 'shares': None, 'price': None,
                'automatic': form.endswith('ASR')}
    if debt:
        return {'kind': 'debt', 'amount': None, 'shares': None, 'price': None}
    atm = re.search(r'(?i)at[- ]the[- ]market|equity distribution agreement|sales agreement|open market sale agreement|equity offering sales agreement', head)
    m = re.search(r'(?i)(?:aggregate offering price of|having an aggregate (?:gross sales price|offering price) of|up to)\s+\$\s?([\d,.]+)\s*(million|billion)?', head)
    amt = amount(m.group(1), m.group(2)) if m else None
    if atm:
        return {'kind': 'atm', 'amount': amt, 'shares': None, 'price': None}
    sh = re.search(r'(?i)(?:we are offering|offering)\s+([\d,]+)\s+shares', head) or re.search(r'(?i)([\d,]{5,})\s+shares of (?:our )?(?:class [a-c] )?common stock', head)
    px = re.search(r'(?i)(?:public offering price|offering price)\s+(?:is|of)?\s*\$\s?(\d+(?:\.\d+)?)\s+per share', head) or re.search(r'(?i)\$\s?(\d+(?:\.\d+)?)\s+per share', head)
    shares = amount(sh.group(1)) if sh else None
    price = float(px.group(1)) if px else None
    if shares and price:
        return {'kind': 'firm', 'amount': shares * price, 'shares': shares, 'price': price}
    return {'kind': 'other' if not amt else 'firm', 'amount': amt, 'shares': shares, 'price': price}


def parse_ipo(text):
    """A 424B4 prospectus cover → {ipo, price, shares, symbol, exchange, lockup_days, date}."""
    t = re.sub(r'\s+', ' ', (text or '')[:200000])
    head = t[:15000]
    ipo = bool(re.search(r'(?i)initial public offering', head))
    px = re.search(r'(?i)initial public offering price (?:is|of)\s+\$\s?(\d+(?:\.\d+)?)', head) \
        or re.search(r'(?i)public offering price\s*(?:per (?:share|ADS))?\s*\$\s?(\d+(?:\.\d+)?)', head) \
        or re.search(r'(?i)\$\s?(\d+(?:\.\d+)?)\s+per (?:share|ADS|American Depositary Share)', head)
    sh = re.search(r'(?i)([\d,]{5,})\s+(?:shares|American Depositary Shares|ADSs|Class A (?:ordinary|common) shares|ordinary shares|units)', head)
    sym = re.search(r'(?i)under the (?:ticker )?symbol\s+[“"\'‘]?([A-Z]{1,5}(?:\.[A-Z])?)[”"\'’]?', head)
    exch = re.search(r'(?i)(Nasdaq (?:Global Select|Global|Capital) Market|New York Stock Exchange|NYSE American|Nasdaq)', head)
    lock = None
    for m in re.finditer(r'(?i)(\d{2,3})\s+days\s+(?:after|following|from) the date of this prospectus', t):
        ctx = t[max(0, m.start() - 600):m.end() + 100].lower()
        if 'lock' in ctx or 'not to' in ctx or 'without the prior written consent' in ctx:
            lock = int(m.group(1))
            break
    date = None
    m = re.search(r'(?i)(?:the date of this prospectus is|prospectus dated)\s+' + DATE_RX, t)
    if m:
        date = parse_date(m.group(1))
    return {'ipo': ipo, 'price': float(px.group(1)) if px else None, 'shares': amount(sh.group(1)) if sh else None,
            'symbol': sym.group(1).upper() if sym else None, 'exchange': exch.group(1) if exch else None,
            'lockup_days': lock or (180 if ipo else None), 'date': date}


# ------------------------------------------------------------------ deals
def close_date(phrase, announced):
    """'the first half of 2027' → '2027-06-30'; 'the fourth quarter of 2026' → '2026-12-31'; 'the end of the year' → Dec 31."""
    p = (phrase or '').lower()
    y = re.search(r'(20\d\d)', p)
    year = int(y.group(1)) if y else (dt.date.fromisoformat(announced).year if announced else None)
    if not year:
        return None
    if re.search(r'first half|1h|h1', p):
        return f'{year}-06-30'
    if re.search(r'second half|2h|h2|end of|year[- ]end|by the end|calendar year|during 20', p):
        return f'{year}-12-31'
    q = re.search(r'(first|second|third|fourth|1st|2nd|3rd|4th|q1|q2|q3|q4)\s*(?:calendar |fiscal )?(?:quarter)?', p)
    if q:
        n = {'first': 1, '1st': 1, 'q1': 1, 'second': 2, '2nd': 2, 'q2': 2, 'third': 3, '3rd': 3, 'q3': 3, 'fourth': 4, '4th': 4, 'q4': 4}[q.group(1)]
        return f'{year}-{3 * n:02d}-{[31, 30, 30, 31][n - 1]}'
    m = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', p)
    if m:
        mon = MONTHS[m.group(1)]
        last = (dt.date(year + (mon == 12), mon % 12 + 1, 1) - dt.timedelta(days=1)).day
        return f'{year}-{mon:02d}-{last:02d}'
    return f'{year}-12-31' if y else None


def parse_deal(text, filer_name=''):
    """A merger agreement / proxy / tender offer → {cash, ratio, acquirer, target, close_text, filer_is_target, tender_expires}."""
    t = re.sub(r'\s+', ' ', (text or '')[:150000])
    cash = None
    for rx in (r'(?i)right to receive(?:[^.$]|\.(?=\d)){0,120}?\$\s?(\d+(?:\.\d+)?)\s+(?:per share\s+)?in cash',
               r'(?i)\$\s?(\d+(?:\.\d+)?)\s+per share(?: of [^,.]{0,60})?,? (?:net to the seller )?in cash',
               r'(?i)entitled to receive \$\s?(\d+(?:\.\d+)?)\s+in cash',
               r'(?i)cash consideration of \$\s?(\d+(?:\.\d+)?)'):
        m = re.search(rx, t)
        if m:
            cash = float(m.group(1))
            break
    ratio, acq_stock = None, None
    m = re.search(r'(?i)(\d+\.\d+)\s+(?:shares?|of a share)\s+of\s+(?:common stock of\s+)?([A-Z][\w&.,\'’ -]{2,60}?)(?:’s|\'s)?\s+(?:class [a-c]\s+)?common (?:stock|shares)', t)
    if m:
        ratio, acq_stock = float(m.group(1)), m.group(2).strip(' ,')
    filer_is_target = bool(re.search(r'(?i)merge (?:with and )?into the Company|Company will (?:survive|continue as the surviving)|the Company as the surviving', t))
    acquirer = target = None
    m = re.search(r'(?i)(?:Agreement and Plan of Merger|Merger Agreement)[^.]{0,200}?\bwith\s+([A-Z][\w&.,\'’ -]{2,70}?)\s*(?:,\s*a\s|\(|“|"|(?=\.\s+[A-Z]))', t)
    other = m.group(1).strip(' ,') if m else None
    if other and re.search(r'\b(?:Inc|Corp|Co|Ltd|L\.P|N\.V|S\.A|Holdings Inc)$', other):
        other += '.'
    if other:
        if filer_is_target:
            acquirer = other
        else:
            target = other
    if acq_stock and not acquirer:
        acquirer = acq_stock
    close_text = None
    m = re.search(r'(?i)expected to (?:close|be completed|be consummated)\s+(?:in|during|by|at|before)\s+(?:the\s+)?([^.;()]{3,60})', t)
    if m:
        close_text = m.group(1).strip(' ,')
    tender = None
    m = re.search(r'(?i)(?:offer|tender offer)[^.]{0,120}?(?:will |is scheduled to )?expire.{0,100}?' + DATE_RX, t)
    if m:
        tender = parse_date(m.group(1))
    return {'cash': cash, 'ratio': ratio, 'acquirer': acquirer, 'target': target, 'close_text': close_text,
            'filer_is_target': filer_is_target, 'tender_expires': tender}


def deal_value(d, prices):
    """Consideration per target share at the acquirer's last price (cash + ratio × price), or None."""
    v = d.get('cash') or 0.0
    if d.get('ratio'):
        ap = prices.get(d.get('acquirer_ticker') or '')
        if not ap:
            return None
        v += d['ratio'] * ap
    return v or None


def spread(d, prices, today):
    """(spread, annualized spread, days to the expected close) for a pending deal."""
    px = prices.get(d.get('target_ticker') or '')
    val = deal_value(d, prices)
    if not px or not val:
        return None, None, None
    s = val / px - 1
    days = None
    if d.get('close_by'):
        days = (dt.date.fromisoformat(d['close_by']) - today).days
    ann = s * 365 / days if days and days > 14 else None
    return _r(s), _r(ann), days


# ------------------------------------------------------------------ CEO pay vs shareholder return
PVP = ['PeoTotalCompAmt', 'PeoActuallyPaidCompAmt', 'TotalShareholderRtnAmt', 'PeerGroupTotalShareholderRtnAmt']


def paycomp_rows(facts):
    """{concept: [(fiscal year end, value)]} → per-year rows and the alignment: the latest year's change in compensation
    actually paid against the change in the $100 TSR value, and the correlation of the two over the years on file."""
    years = sorted({e for k in PVP for e, _ in facts.get(k, [])})
    rows = []
    for y in years:
        r = {'fy_end': y}
        for k in PVP:
            v = next((val for e, val in facts.get(k, []) if e == y), None)
            r[k] = v
        rows.append(r)
    rows = [r for r in rows if r['PeoTotalCompAmt'] or r['PeoActuallyPaidCompAmt']][-5:]
    if not rows:
        return None
    last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
    out = {'years': rows, 'fy_end': last['fy_end'], 'total': last['PeoTotalCompAmt'], 'cap': last['PeoActuallyPaidCompAmt'],
           'tsr': last['TotalShareholderRtnAmt'], 'peer_tsr': last['PeerGroupTotalShareholderRtnAmt']}
    if prev:
        def chg(k):
            a, b = last.get(k), prev.get(k)
            return _r(a / b - 1) if a is not None and b not in (None, 0) and b > 0 else None
        out.update(total_chg=chg('PeoTotalCompAmt'), cap_chg=chg('PeoActuallyPaidCompAmt'), tsr_chg=chg('TotalShareholderRtnAmt'))
    xs = [(r['PeoActuallyPaidCompAmt'], r['TotalShareholderRtnAmt']) for r in rows if r['PeoActuallyPaidCompAmt'] is not None and r['TotalShareholderRtnAmt'] is not None]
    if len(xs) >= 3:
        a = [x for x, _ in xs]
        b = [y for _, y in xs]
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        sa = math.sqrt(sum((x - ma) ** 2 for x in a))
        sb = math.sqrt(sum((y - mb) ** 2 for y in b))
        out['corr'] = _r(sum((x - ma) * (y - mb) for x, y in xs) / (sa * sb)) if sa and sb else None
    tsr_from = rows[0]['TotalShareholderRtnAmt']
    out['tsr_years'] = len(rows)
    out['tsr_total'] = _r(last['TotalShareholderRtnAmt'] / 100 - 1) if last['TotalShareholderRtnAmt'] else None
    out['misaligned'] = bool(out.get('total_chg') is not None and out.get('tsr_chg') is not None
                             and out['total_chg'] >= 0.2 and out['tsr_chg'] <= -0.1)
    _ = tsr_from
    return out


# ------------------------------------------------------------------ contracts and lobbying
SUFFIX = re.compile(r'\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|LLC|L\.?L\.?C|LP|L\.?P|LTD|LIMITED|PLC|HOLDINGS?|GROUP|THE|N\.?V|S\.?A|AG|SE)\b\.?')
# recipient names on USAspending that are a listed company's subsidiary (conservative: only well-known, unambiguous ones)
ALIASES = {
    'RAYTHEON': 'RTX', 'RAYTHEON COMPANY': 'RTX', 'RTX': 'RTX', 'PRATT & WHITNEY': 'RTX', 'COLLINS AEROSPACE': 'RTX',
    'SIKORSKY AIRCRAFT': 'LMT', 'LOCKHEED MARTIN': 'LMT', 'ELECTRIC BOAT': 'GD', 'GENERAL DYNAMICS INFORMATION TECHNOLOGY': 'GD',
    'GENERAL DYNAMICS LAND SYSTEMS': 'GD', 'BATH IRON WORKS': 'GD', 'GULFSTREAM AEROSPACE': 'GD', 'NATIONAL STEEL AND SHIPBUILDING': 'GD',
    'NORTHROP GRUMMAN SYSTEMS': 'NOC', 'NORTHROP GRUMMAN': 'NOC', 'BOEING': 'BA', 'L3HARRIS TECHNOLOGIES': 'LHX', 'HARRIS': 'LHX',
    'HUNTINGTON INGALLS': 'HII', 'NEWPORT NEWS SHIPBUILDING': 'HII', 'LEIDOS': 'LDOS', 'BOOZ ALLEN HAMILTON': 'BAH',
    'SCIENCE APPLICATIONS INTERNATIONAL': 'SAIC', 'CACI': 'CACI', 'CACI INTERNATIONAL': 'CACI', 'PALANTIR USG': 'PLTR',
    'PALANTIR TECHNOLOGIES': 'PLTR', 'MCKESSON': 'MCK', 'PFIZER': 'PFE', 'HUMANA GOVERNMENT BUSINESS': 'HUM', 'HUMANA MILITARY HEALTHCARE SERVICES': 'HUM',
    'GE AEROSPACE': 'GE', 'GENERAL ELECTRIC': 'GE', 'HONEYWELL INTERNATIONAL': 'HON', 'TEXTRON': 'TXT', 'BELL TEXTRON': 'TXT',
    'OSHKOSH DEFENSE': 'OSK', 'KBR': 'KBR', 'KBR WYLE SERVICES': 'KBR', 'PARSONS GOVERNMENT SERVICES': 'PSN', 'JACOBS': 'J',
    'AMENTUM SERVICES': 'AMTM', 'V2X': 'VVX', 'MODERNA': 'MRNA', 'MODERNATX': 'MRNA', 'CENTENE': 'CNC', 'HEALTH NET FEDERAL SERVICES': 'CNC',
    'UNITEDHEALTH': 'UNH', 'OPTUM PUBLIC SECTOR SOLUTIONS': 'UNH', 'CARDINAL HEALTH': 'CAH', 'AMERISOURCEBERGEN': 'COR', 'CENCORA': 'COR',
    'MICROSOFT': 'MSFT', 'AMAZON WEB SERVICES': 'AMZN', 'ORACLE AMERICA': 'ORCL', 'IBM': 'IBM', 'INTERNATIONAL BUSINESS MACHINES': 'IBM',
    'ACCENTURE FEDERAL SERVICES': 'ACN', 'DELL FEDERAL SYSTEMS': 'DELL', 'HEWLETT PACKARD ENTERPRISE': 'HPE', 'MOTOROLA SOLUTIONS': 'MSI',
    'SPACE EXPLORATION TECHNOLOGIES': None, 'ANDURIL INDUSTRIES': None,         # private: never matched to a ticker
    'KRATOS DEFENSE & SECURITY SOLUTIONS': 'KTOS', 'AEROVIRONMENT': 'AVAV', 'CURTISS-WRIGHT': 'CW', 'MERCURY SYSTEMS': 'MRCY',
    'BWX TECHNOLOGIES': 'BWXT', 'BWXT NUCLEAR OPERATIONS GROUP': 'BWXT', 'FLUOR': 'FLR', 'AECOM': 'ACM', 'TETRA TECH': 'TTEK',
}


def norm_name(s):
    s = re.sub(r'[^A-Z0-9& ]+', ' ', (s or '').upper().replace('.', ''))
    s = SUFFIX.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def name_index(tickers):
    """{normalized company name: ticker} from the SEC's ticker list (one ticker per CIK: the first listed)."""
    out = {}
    for r in tickers:
        n = norm_name(r.get('title'))
        if len(n) >= 4 and n not in out:
            out[n] = r['ticker']
    return out


def match_recipient(name, names):
    """A recipient or client name → a ticker, or None. Exact normalized name, a known subsidiary alias, or the company's
    normalized name followed by a word that names a unit (… GOVERNMENT SERVICES, … FEDERAL, … DEFENSE)."""
    n = norm_name(name)
    if not n:
        return None
    for k, v in ALIASES.items():
        nk = norm_name(k)
        if n == nk or n.startswith(nk + ' '):
            return v
    if n in names:
        return names[n]
    words = n.split()
    for k in range(len(words) - 1, 0, -1):
        head = ' '.join(words[:k])
        rest = words[k:]
        if head in names and len(head) >= 6 and rest[0] in ('FEDERAL', 'GOVERNMENT', 'DEFENSE', 'SERVICES', 'SYSTEMS', 'TECHNOLOGIES', 'USA', 'US', 'AMERICA', 'NORTH'):
            return names[head]
    return None


def lobbying_quarters(results, client_name):
    """LDA filings for one client → {'2026Q3': amount} (in-house filers report expenses, outside firms income) and issues."""
    q = {}
    issues = {}
    me = norm_name(client_name)
    seen = set()
    for f in results or []:
        uid = f.get('filing_uuid') or (f.get('filing_year'), f.get('filing_period'), (f.get('registrant') or {}).get('name'),
                                       (f.get('client') or {}).get('name'), f.get('income'), f.get('expenses'))
        if uid in seen:
            continue
        seen.add(uid)
        if (f.get('filing_type') or '').upper().startswith(('RR', 'TERM')) and not (f.get('income') or f.get('expenses')):
            continue
        yr = f.get('filing_year')
        per = (f.get('filing_period') or '').lower()
        n = {'first_quarter': 1, 'second_quarter': 2, 'third_quarter': 3, 'fourth_quarter': 4, 'mid_year': 2, 'year_end': 4}.get(per)
        if not yr or not n:
            continue
        reg = norm_name((f.get('registrant') or {}).get('name'))
        cli = norm_name((f.get('client') or {}).get('name'))
        if me and cli and not (cli == me or cli.startswith(me + ' ') or me.startswith(cli + ' ')):
            continue
        self_filed = bool(reg and cli and (reg == cli or reg.startswith(cli) or cli.startswith(reg)))
        v = f.get('expenses') if self_filed else f.get('income')
        try:
            v = float(v) if v not in (None, '') else 0.0
        except (TypeError, ValueError):
            v = 0.0
        key = f'{yr}Q{n}'
        q[key] = q.get(key, 0.0) + v
        for a in f.get('lobbying_activities') or []:
            g = a.get('general_issue_code_display') or a.get('general_issue_code')
            if g:
                issues[g] = issues.get(g, 0) + 1
    return q, [k for k, _ in sorted(issues.items(), key=lambda kv: -kv[1])[:4]]


def trailing(quarters, n=4):
    ks = sorted(quarters)[-n:]
    return sum(quarters[k] for k in ks), (ks[-1] if ks else None)


# ------------------------------------------------------------------ the store
class Store:
    """cache/<name>.json = {key: row}, pruned by age (row['filed'])."""

    def __init__(self, root):
        self.root = Path(root)
        self.d = {}

    def get(self, name):
        if name not in self.d:
            self.d[name] = read_json(self.root / 'cache' / f'{name}.json', {}) or {}
        return self.d[name]

    def save(self, today):
        for name, rows in self.d.items():
            keep = KEEP_DAYS.get(name)
            if keep:
                cut = (today - dt.timedelta(days=keep)).isoformat()
                rows = {k: v for k, v in rows.items() if not isinstance(v, dict) or (v.get('filed') or v.get('announced') or '9') >= cut}
            write_json(self.root / 'cache' / f'{name}.json', rows)


def http_client():
    cfg = read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {}) or {}
    http = cfg.get('http', {})
    lda_key = os.environ.get('LDA_API_KEY')
    return Client(tempfile.mkdtemp(prefix='rf-raw-'),
                  {**http, 'extra_hosts': ['api.usaspending.gov', 'lda.senate.gov', 'lda.gov', 'efts.sec.gov'],
                   'host_intervals': {**http.get('host_intervals', {}), 'data.sec.gov': 0.13, 'www.sec.gov': 0.13,
                                      'query2.finance.yahoo.com': 0.4, 'api.usaspending.gov': 0.5,
                                      'lda.senate.gov': 0.7 if lda_key else 4.2, 'lda.gov': 0.7 if lda_key else 4.2},
                   'timeout': 60, 'max_response_mb': 40, 'retries': 3})


class Run:
    """One collection run: the client, the deadline, the store, the errors."""

    def __init__(self, root, minutes=40, client=None, today=None):
        self.root = Path(root)
        self.t0 = time.time()
        self.deadline = self.t0 + minutes * 60
        self.client = client
        self.today = today or dt.datetime.now(dt.timezone.utc).date()
        self.store = Store(root)
        self.state = read_json(self.root / 'state.json', {}) or {}
        self.errors = []
        self.counts = {}

    def left(self, reserve=0.0):
        """Seconds left before the share of the run kept for the later steps (reserve: a fraction of the whole run)."""
        return self.deadline - time.time() - reserve * (self.deadline - self.t0)

    def err(self, where, exc):
        msg = f'{where}: {str(exc)[:160]}'
        self.errors.append(msg)
        print('::warning::filings radar ' + msg, flush=True)

    def sec(self, url):
        return self.client.get(url, sec=True).decode('utf-8', 'replace')

    def sec_json(self, url):
        return json.loads(self.client.get(url, sec=True))

    def save(self):
        self.store.save(self.today)
        self.state['updated_at'] = now()
        write_json(self.root / 'state.json', self.state)


# ------------------------------------------------------------------ collection steps
def tickers(run, refresh_days=1):
    """The SEC's ticker list (cached): [{cik, ticker, title}]."""
    p = run.root / 'cache' / 'tickers.json'
    d = read_json(p, {}) or {}
    if run.client and (d.get('fetched') or '') < (run.today - dt.timedelta(days=refresh_days)).isoformat():
        try:
            raw = run.sec_json(TICKERS)
            rows = [{'cik': int(v['cik_str']), 'ticker': str(v['ticker']).upper().replace('.', '-'), 'title': v.get('title') or ''}
                    for v in (raw.values() if isinstance(raw, dict) else raw)]
            d = {'fetched': run.today.isoformat(), 'rows': rows}
            write_json(p, d)
        except Exception as exc:
            run.err('tickers', exc)
    return d.get('rows') or []


def read_indexes(run, days=7, backfill=60):
    """Read the daily form indexes not yet read (the last two business days always again), newest first."""
    seen = run.state.setdefault('index_days', {})
    want = business_days(run.today, max(days, backfill))
    recent = {d.isoformat() for d in business_days(run.today, 2)}
    n = 0
    for d in want:
        k = d.isoformat()
        if run.left(reserve=0.55) < 0:
            break
        if seen.get(k) in ('done', 'missing') and k not in recent:
            continue
        url = DAILY.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime('%Y%m%d'))
        try:
            text = run.sec(url)
        except Exception as exc:
            if 'HTTP 404' in str(exc) or 'HTTP 403' in str(exc):
                seen[k] = 'missing' if d < run.today - dt.timedelta(days=3) else 'pending'
                continue
            run.err(f'index {k}', exc)
            continue
        rows = parse_form_index(text)
        write_json(run.root / 'cache' / 'index' / f'{k}.json', {'rows': rows})
        seen[k] = 'done'
        n += 1
    cut = (run.today - dt.timedelta(days=400)).isoformat()
    run.state['index_days'] = {k: v for k, v in seen.items() if k >= cut}
    for p in (run.root / 'cache' / 'index').glob('*.json'):
        if p.stem < cut:
            p.unlink()
    run.counts['index_days_read'] = n


def index_rows(run, days=400):
    out = []
    cut = (run.today - dt.timedelta(days=days)).isoformat()
    for p in sorted((run.root / 'cache' / 'index').glob('*.json'), reverse=True):
        if p.stem < cut:
            continue
        out += [tuple(r) for r in (read_json(p, {}) or {}).get('rows', [])]
    return out


def folder(cik, acc):
    return FOLDER.format(cik=int(cik), nodash=acc.replace('-', ''))


def main_document(run, cik, acc, prefer_pdf=False):
    """The filing's main document (the largest HTML/text file that is not an exhibit or an index) → plain text."""
    idx = run.sec_json(folder(cik, acc) + 'index.json')
    items = (idx.get('directory') or {}).get('item') or []

    def size(i):
        try:
            return int(i.get('size') or 0)
        except ValueError:
            return 0
    docs = [i for i in items if re.search(r'\.(htm|html|txt)$', i.get('name', ''), re.I)
            and not re.search(r'-index(-headers)?\.html?$|^R\d+\.htm$|^FilingSummary|\.xml$', i['name'], re.I)
            and not re.search(r'(?i)(?:^|[_\-.])ex[-_]?\d|exhibit', i['name']) and i['name'] != f'{acc}.txt']
    pdfs = [i for i in items if i.get('name', '').lower().endswith('.pdf')]
    if docs and not prefer_pdf:
        best = max(docs, key=size)
        return text_of(run.sec(folder(cik, acc) + best['name']))
    if pdfs:
        data = run.client.get(folder(cik, acc) + pdfs[0]['name'], sec=True)
        t = pdf_text(data)
        if t:
            return t
    if docs:
        return text_of(run.sec(folder(cik, acc) + max(docs, key=size)['name']))
    return submission_text(run.sec(folder(cik, acc) + f'{acc}.txt'))


def process_filings(run, tick, limit=None):
    """Parse the index rows not parsed yet, by kind, newest first, within the time left."""
    by_cik = {r['cik']: r for r in tick}
    done = run.state.setdefault('parsed', {})
    rows = sorted(index_rows(run), key=lambda r: r[3], reverse=True)
    stores = {k: run.store.get(k) for k in ('redflags', 'letters', 'offerings', 'ipos', 'deals')}
    done_acc = {k.split(':')[0] for k, v in done.items() if v == PARSER}
    n = 0
    for form, cik, name, filed, acc in rows:
        kind = FORMS.get(form)
        key = f'{acc}:{cik}'
        if done.get(key) == PARSER or run.left(reserve=0.35) < 0:
            continue
        if limit is not None and n >= limit:
            break
        if acc in done_acc:                           # a filing listed under two companies (a tender offer): read once
            done[key] = PARSER
            continue
        t = by_cik.get(cik)
        listed = t is not None
        if kind in ('letter', 'shelf', 'takedown') and not listed:
            done[key] = PARSER                        # funds, trusts and private issuers: not on the radar
            continue
        if kind in ('deal', 'tender') and not listed and form not in ('SC TO-T', 'SCHEDULE TO-T'):
            done[key] = PARSER
            continue
        base = {'accession': acc, 'cik': cik, 'company': (t or {}).get('title') or name, 'ticker': (t or {}).get('ticker'),
                'form': form, 'filed': filed, 'url': folder(cik, acc)}
        try:
            if kind == 'late':
                d = parse_nt(submission_text(run.sec(folder(cik, acc) + f'{acc}.txt')))
                row = {**base, 'kind': 'late', **d}
                row['severity'] = severity('late', row)
                stores['redflags'][acc] = row
            elif kind == 'letter':
                text = main_document(run, cik, acc, prefer_pdf=(form == 'UPLOAD'))
                about = letter_about(text)
                stores['letters'][acc] = {**base, 'who': 'SEC staff' if form == 'UPLOAD' else 'company', 'topics': letter_topics(text),
                                          'about_form': about[0], 'about_period': about[1], 'closing': letter_closing(text),
                                          'excerpt': _excerpt(text, LETTER_TOPICS), 'read': bool(text)}
            elif kind in ('shelf', 'takedown'):
                d = parse_offering(main_document(run, cik, acc), form)
                if d['kind'] != 'debt':
                    stores['offerings'][acc] = {**base, **d}
            elif kind in ('ipo_reg', 'ipo_price'):
                text = main_document(run, cik, acc)
                d = parse_ipo(text)
                if kind == 'ipo_price' and not d['ipo']:
                    done[key] = PARSER                # a follow-on offering's final prospectus
                    continue
                stores['ipos'][acc] = {**base, 'stage': 'priced' if kind == 'ipo_price' else 'registered', **d}
            elif kind in ('deal', 'tender'):
                txt = run.sec(folder(cik, acc) + f'{acc}.txt')
                h = E.OWN.header(txt)
                subj = (h['roles'].get('SUBJECT COMPANY') or [{}])[0]
                filer = (h['roles'].get('FILED BY') or [{}])[0]
                d = parse_deal(submission_text(txt), name)
                add_deal(stores['deals'], base, d, subj, by_cik, tick, filer)
            n += 1
            done[key] = PARSER
            done_acc.add(acc)
        except Exception as exc:
            run.err(f'{form} {acc}', exc)
            done[key] = PARSER if 'HTTP 404' in str(exc) else done.get(key, 0)
    cut = (run.today - dt.timedelta(days=420)).isoformat()
    keep = {f'{r[4]}:{r[1]}' for r in rows if r[3] >= cut}
    run.state['parsed'] = {k: v for k, v in done.items() if k in keep or not re.match(r'\d{10}-', k)}
    run.counts['filings_parsed'] = n


def _excerpt(text, topics, limit=300):
    for s in re.split(r'(?<=[.?])\s+(?=[A-Z0-9])', re.sub(r'\s+', ' ', text or '')):
        if 60 <= len(s) <= 500 and any(re.search(rx, s) for _, rx, _ in topics) and re.search(r'(?i)\b(please|tell us|explain|revise|we note|in response)\b', s):
            return s[:limit]
    return ''


def add_deal(deals, base, d, subj, by_cik, tick, filer=None):
    """Merge one deal document into the deal it belongs to (keyed by the target's CIK, else its name)."""
    names = {norm_name(r['title']): r for r in tick}
    filer = filer or {}
    tgt_cik = None
    if subj.get('cik') and base['form'] in ('SC TO-T', 'SCHEDULE TO-T', 'SC 14D9', 'SCHEDULE 14D9'):
        tgt_cik = int(subj['cik'])
    elif d.get('filer_is_target') or base['form'] in ('DEFM14A', 'PREM14A', 'DEFM14C'):
        tgt_cik = base['cik']
    elif d.get('target'):
        hit = names.get(norm_name(d['target']))
        tgt_cik = hit['cik'] if hit else None
    acq = d.get('acquirer')
    ar = None
    if base['form'] in ('SC TO-T', 'SCHEDULE TO-T'):
        fc = int(filer['cik']) if str(filer.get('cik') or '').isdigit() else None
        if fc and fc != tgt_cik:
            acq = acq or filer.get('name')
            ar = by_cik.get(fc)
        elif base['cik'] != tgt_cik:
            acq = acq or base['company']
            ar = by_cik.get(base['cik'])
    if not d.get('filer_is_target') and base['form'] in ('8-K', 'S-4') and tgt_cik != base['cik']:
        acq = acq or base['company']
    key = str(tgt_cik) if tgt_cik else norm_name(d.get('target') or '')
    if not key:
        return
    tr = by_cik.get(tgt_cik) if tgt_cik else names.get(norm_name(d.get('target') or ''))
    ar = ar or (names.get(norm_name(acq or '')) if acq else None)
    cur = deals.get(key) or {'target_cik': tgt_cik, 'announced': base['filed'], 'docs': []}
    cur['target'] = (tr or {}).get('title') or cur.get('target') or d.get('target') or (subj or {}).get('name')
    cur['target_ticker'] = (tr or {}).get('ticker') or cur.get('target_ticker')
    if acq:
        cur['acquirer'] = cur.get('acquirer') or acq
        cur['acquirer_ticker'] = cur.get('acquirer_ticker') or (ar or {}).get('ticker')
    for k in ('cash', 'ratio', 'close_text', 'tender_expires'):
        if d.get(k) is not None:
            cur[k] = d[k]
    cur['announced'] = min(cur['announced'], base['filed'])
    if cur.get('close_text'):
        cur['close_by'] = close_date(cur['close_text'], cur['announced'])
    if cur.get('tender_expires') and not cur.get('close_by'):
        cur['close_by'] = cur['tender_expires']
    if not any(x['accession'] == base['accession'] for x in cur['docs']):
        cur['docs'].append({'form': base['form'], 'filed': base['filed'], 'accession': base['accession'], 'url': base['url']})
    cur['docs'] = sorted(cur['docs'], key=lambda x: x['filed'])[-12:]
    cur['filed'] = max(x['filed'] for x in cur['docs'])
    deals[key] = cur


def events_rows(run, src):
    """The hub's 8-K rows (app/events8k.py): a cache directory of <day>.json.gz shards, or a published events8k.json."""
    rows = []
    p = Path(src) if src else None
    if not p or not p.exists():
        return rows
    files = [p] if p.is_file() else sorted(p.glob('*.json.gz')) + sorted(p.glob('*.json'))
    for f in files:
        try:
            with (gzip.open(f, 'rt', encoding='utf-8') if f.name.endswith('.gz') else open(f, encoding='utf-8')) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        rs = d.get('rows') if isinstance(d, dict) else d
        if isinstance(rs, dict):
            rs = list(rs.values())
        rows += [r for r in rs or [] if isinstance(r, dict) and r.get('accession')]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r.get('filed') or '', reverse=True):
        if r['accession'] not in seen:
            seen.add(r['accession'])
            out.append(r)
    return out


def process_events(run, tick, src):
    """The 8-Ks that matter here (Items 4.01, 4.02, 3.01; buybacks; dividends; merger agreements): read once more."""
    by_cik = {r['cik']: r for r in tick}
    done = run.state.setdefault('events_parsed', {})
    flags, buys, divs, deals = (run.store.get(k) for k in ('redflags', 'buybacks', 'dividends', 'deals'))
    n = 0
    cut = (run.today - dt.timedelta(days=120)).isoformat()
    for r in events_rows(run, src):
        acc = r['accession']
        if done.get(acc) == PARSER or (r.get('filed') or '') < cut or run.left(reserve=0.28) < 0:
            continue
        items, topics = set(r.get('items') or []), set(r.get('topics') or [])
        want = []
        if items & {'4.01', '4.02', '3.01'}:
            want.append('flag')
        if 'buyback' in topics:
            want.append('buyback')
        if 'dividend' in topics or re.search(r'(?i)dividend', r.get('headline') or ''):
            want.append('dividend')
        if 'deal' in topics and ('1.01' in items or re.search(r'(?i)plan of merger|merger agreement', r.get('quote') or '')):
            want.append('deal')
        if not want:
            done[acc] = PARSER
            continue
        try:
            cik = int(r.get('cik') or 0)
            t = by_cik.get(cik) or {}
            txt = run.sec(r.get('url', folder(cik, acc)).rstrip('/') + f'/{acc}.txt') if run.client else ''
            docs = E.documents(txt)
            main = next((d for d in docs if d[0].startswith('8-K')), docs[0] if docs else ('', '', ''))
            paras = E.html_text(main[2])
            secs = E.item_sections(paras)
            rel = next((d for d in docs if d[0].startswith('EX-99')), None)
            rel_text = text_of(rel[2]) if rel else ''
            body = '\n'.join(paras)
            base = {'accession': acc, 'cik': cik, 'company': t.get('title') or r.get('company'), 'ticker': t.get('ticker') or r.get('ticker'),
                    'form': r.get('form') or '8-K', 'filed': r.get('filed'), 'url': r.get('url') or folder(cik, acc)}
            if 'flag' in want:
                for code, kind, fn in (('4.01', 'auditor', parse_auditor_change), ('4.02', 'restatement', parse_restatement),
                                       ('3.01', 'listing', parse_listing_notice)):
                    if code in items:
                        sec = '\n'.join(secs.get(code) or []) or body
                        d = fn(sec)
                        row = {**base, 'kind': kind, 'item': code, **d, 'quote': (r.get('quote') or '')[:300]}
                        row['severity'] = severity(kind, row)
                        flags[f'{acc}:{code}'] = row
            if 'buyback' in want:
                d = parse_buyback(rel_text + '\n' + body)
                if d['amount'] or d['shares']:
                    buys[acc] = {**base, **d, 'headline': r.get('headline') or ''}
            if 'dividend' in want:
                d = parse_dividend(rel_text + '\n' + body)
                if d['amount'] or d['change'] == 'suspend':
                    divs[acc] = {**base, **d, 'headline': r.get('headline') or ''}
            if 'deal' in want:
                d = parse_deal(body + '\n' + rel_text, base['company'])
                if d['cash'] or d['ratio']:
                    add_deal(deals, base, d, {}, by_cik, tick)
            done[acc] = PARSER
            n += 1
        except Exception as exc:
            run.err(f'8-K {acc}', exc)
    run.state['events_parsed'] = {k: v for k, v in done.items() if k[:10].isdigit()}
    if len(run.state['events_parsed']) > 20000:
        run.state['events_parsed'] = dict(list(run.state['events_parsed'].items())[-15000:])
    run.counts['events_parsed'] = n


def quarter_ends(today, n):
    """The last n calendar quarter ends at least 50 days old: ['2026-06-30', …] newest first."""
    out = []
    y, q = today.year, (today.month - 1) // 3 + 1
    while len(out) < n:
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        end = dt.date(y, 3 * q, [31, 30, 30, 31][q - 1])
        if (today - end).days >= 50:
            out.append(end)
    return out


def collect_frames(run, refresh_days=6):
    """XBRL frames: shares outstanding at the last five quarter ends; the last two calendar years' repurchases and dividends;
    pay versus performance (ecd) for the last two years when the frames API serves that taxonomy."""
    want = []
    for e in quarter_ends(run.today, 5):
        want.append(('us-gaap', 'CommonStockSharesOutstanding', 'shares', f'CY{e.year}Q{(e.month - 1) // 3 + 1}I'))
    y = run.today.year - 1
    for yr in (y, y - 1):
        for c in ('PaymentsForRepurchaseOfCommonStock', 'PaymentsOfDividendsCommonStock', 'PaymentsOfDividends'):
            want.append(('us-gaap', c, 'USD', f'CY{yr}'))
    for yr in (y, y - 1, y - 2):
        for c in PVP:
            want.append(('ecd', c, 'USD', f'CY{yr}'))
    meta = run.state.setdefault('frames', {})
    n = 0
    for tax, c, unit, per in want:
        k = f'{tax}:{c}:{per}'
        p = run.root / 'cache' / 'frames' / f'{tax}-{c}-{per}.json'
        if (meta.get(k) or '') >= (run.today - dt.timedelta(days=refresh_days)).isoformat() and (p.exists() or meta.get(k + ':missing')):
            continue
        if run.left(reserve=0.3) < 0 or not run.client:
            break
        try:
            d = run.sec_json(FRAME.format(tax=tax, concept=c, unit=unit, period=per))
            write_json(p, {str(x['cik']): [x['val'], x.get('end')] for x in d.get('data', []) if x.get('val') is not None})
            meta[k] = run.today.isoformat()
            meta.pop(k + ':missing', None)
            n += 1
        except Exception as exc:
            meta[k] = run.today.isoformat()
            if 'HTTP 404' in str(exc):
                meta[k + ':missing'] = True
            else:
                run.err(f'frame {k}', exc)
    run.counts['frames'] = n


def frame(root, tax, c, per):
    return read_json(Path(root) / 'cache' / 'frames' / f'{tax}-{c}-{per}.json', {}) or {}


def collect_paycomp(run, tick, top=None, refresh_days=45):
    """Pay versus performance from companyconcept for the largest companies when the ecd frames are not served."""
    have_frames = any((run.root / 'cache' / 'frames').glob('ecd-PeoTotalCompAmt-*.json'))
    store = run.store.get('paycomp')
    if have_frames or not run.client:
        return
    order = top or [r['cik'] for r in tick[:400]]
    n = 0
    for cik in order:
        rec = store.get(str(cik)) or {}
        if (rec.get('fetched') or '') >= (run.today - dt.timedelta(days=refresh_days)).isoformat():
            continue
        if run.left(reserve=0.35) < 0 or n >= 120:
            break
        facts = {}
        for c in PVP:
            try:
                d = run.sec_json(CONCEPT.format(cik=int(cik), tax='ecd', concept=c))
                vals = [(u.get('end'), u.get('val')) for u in (d.get('units') or {}).get('USD', []) if u.get('form', '').startswith('DEF 14A')
                        and u.get('val') is not None and not u.get('segment')]
                facts[c] = sorted({e: v for e, v in vals}.items())
            except Exception as exc:
                if 'HTTP 404' not in str(exc):
                    run.err(f'paycomp {cik}', exc)
                facts.setdefault(c, [])
        store[str(cik)] = {'fetched': run.today.isoformat(), 'facts': facts}
        n += 1
    run.counts['paycomp_companies'] = n


def collect_prices(run, want, refresh_hours=20):
    """Daily closes from Yahoo's chart endpoint for the tickers a deal or an IPO needs."""
    cache = run.store.get('prices')
    n = 0
    for t, rng in want.items():
        if not t:
            continue
        rec = cache.get(t) or {}
        if (rec.get('fetched') or '') >= (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=refresh_hours)).isoformat(timespec='seconds'):
            continue
        if run.left(reserve=0.12) < 0 or not run.client or n >= 250:
            break
        try:
            raw = json.loads(run.client.get(CHART.format(sym=t.replace('.', '-'), rng=rng)))
            res = (raw.get('chart') or {}).get('result') or []
            if not res:
                continue
            ts = res[0].get('timestamp') or []
            cl = ((res[0].get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
            rows = [[dt.datetime.fromtimestamp(a, dt.timezone.utc).date().isoformat(), _r(c, 4)] for a, c in zip(ts, cl) if c]
            cache[t] = {'fetched': now(), 'rows': rows[-400:]}
            n += 1
        except Exception as exc:
            if 'HTTP 404' not in str(exc):
                run.err(f'price {t}', exc)
            cache[t] = {'fetched': now(), 'rows': rec.get('rows') or []}
    run.counts['prices'] = n


def _post(run, url, payload):
    body = run.client.request(url, data=json.dumps(payload).encode('utf-8'),
                              headers={'Content-Type': 'application/json', 'Accept': 'application/json'})[0]
    return json.loads(body)


def collect_contracts(run, days=90, refresh_hours=20):
    """USAspending: contract obligations by recipient over the last `days` (top 500) and the largest new awards of the last 14."""
    gov = run.store.get('gov')
    if (gov.get('fetched') or '') >= (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=refresh_hours)).isoformat(timespec='seconds'):
        return
    if not run.client or run.left(reserve=0.2) < 0:
        return
    start = (run.today - dt.timedelta(days=days)).isoformat()
    end = run.today.isoformat()
    codes = ['A', 'B', 'C', 'D']
    rec = []
    try:
        for page in range(1, 6):
            d = _post(run, USA + 'search/spending_by_category/recipient/',
                      {'filters': {'time_period': [{'start_date': start, 'end_date': end}], 'award_type_codes': codes},
                       'category': 'recipient', 'limit': 100, 'page': page})
            rec += [{'name': x.get('name'), 'amount': x.get('amount'), 'id': x.get('recipient_id'), 'uei': x.get('uei') or x.get('code')}
                    for x in d.get('results') or []]
            if not (d.get('page_metadata') or {}).get('hasNext', True):
                break
    except Exception as exc:
        run.err('usaspending recipients', exc)
    awards = []
    s14 = (run.today - dt.timedelta(days=14)).isoformat()
    fields = ['Award ID', 'Recipient Name', 'Award Amount', 'Awarding Agency', 'Awarding Sub Agency', 'Start Date', 'Description', 'generated_internal_id']
    for period in ({'start_date': s14, 'end_date': end, 'date_type': 'new_awards_only'}, {'start_date': s14, 'end_date': end}):
        try:
            d = _post(run, USA + 'search/spending_by_award/',
                      {'filters': {'time_period': [period], 'award_type_codes': codes}, 'fields': fields,
                       'sort': 'Award Amount', 'order': 'desc', 'limit': 100, 'page': 1})
            awards = [{'id': x.get('Award ID'), 'recipient': x.get('Recipient Name'), 'amount': x.get('Award Amount'),
                       'agency': x.get('Awarding Agency'), 'sub_agency': x.get('Awarding Sub Agency'), 'start': x.get('Start Date'),
                       'description': (x.get('Description') or '')[:200], 'internal_id': x.get('generated_internal_id'),
                       'new_only': 'date_type' in period} for x in d.get('results') or []]
            break
        except Exception as exc:
            run.err('usaspending awards', exc)
    if rec or awards:
        gov.update({'fetched': now(), 'since': start, 'until': end, 'recipients': rec or gov.get('recipients') or [],
                    'awards': awards or gov.get('awards') or []})
    run.counts['contract_recipients'] = len(rec)


def collect_lobbying(run, wanted, refresh_days=30, limit=60):
    """Senate LDA filings per client (this year and last) for the companies that matter here."""
    store = run.store.get('lobby')
    key = os.environ.get('LDA_API_KEY')
    hdr = {'Authorization': f'Token {key}'} if key else {}
    n = 0
    years = (run.today.year, run.today.year - 1)
    base = run.state.get('lda_base') or LDA[0]
    for tk, name in wanted:
        rec = store.get(tk) or {}
        if (rec.get('fetched') or '') >= (run.today - dt.timedelta(days=refresh_days)).isoformat():
            continue
        if run.left(reserve=0.12) < 0 or n >= limit or not run.client:
            break
        q = norm_name(name).title()
        if len(q) < 3:
            continue
        results = []
        try:
            for yr in years:
                url = f'{base}filings/?client_name={_qs(q)}&filing_year={yr}&page_size=25'
                for _ in range(4):
                    raw = run.client.request(url, headers={'Accept': 'application/json', **hdr})[0]
                    d = json.loads(raw)
                    results += d.get('results') or []
                    url = d.get('next')
                    if not url or not url.startswith(base):
                        break
        except Exception as exc:
            msg = str(exc)
            if base == LDA[0] and ('HTTP 404' in msg or 'Unexpected redirect' in msg or 'HTTP 410' in msg):
                run.state['lda_base'] = base = LDA[1]
            run.err(f'lda {tk}', exc)
            continue
        quarters, issues = lobbying_quarters(results, name)
        store[tk] = {'fetched': run.today.isoformat(), 'client': name, 'quarters': quarters, 'issues': issues, 'filings': len(results)}
        n += 1
    run.counts['lobbying_clients'] = n


def _qs(s):
    from urllib.parse import quote
    return quote(s)


# ------------------------------------------------------------------ prices
def weekly_close(prices_dir, ticker):
    if not prices_dir or not ticker:
        return None
    p = Path(prices_dir) / 't' / f'{ticker.replace(".", "-")}.json'
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    c = [v for v in d.get('c') or [] if v is not None]
    return c[-1] if c else None


def last_prices(run, prices_dir, tickers_):
    """{ticker: latest close}: the daily cache first (deals, IPOs), else the weekly closes of rotation-history."""
    daily = run.store.get('prices')
    out = {}
    for t in tickers_:
        if not t:
            continue
        rows = (daily.get(t) or {}).get('rows') or []
        out[t] = rows[-1][1] if rows else weekly_close(prices_dir, t)
    return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------ build public/
def officials(path, today, days=120):
    d = read_json(path, {}) if path else {}
    cut = (today - dt.timedelta(days=days)).isoformat()
    out = []
    for t in (d or {}).get('trades') or []:
        if t.get('ticker_status') not in (None, 'listed') or t.get('name_check') == 'check' or t.get('asset_type') == 'OP':
            continue
        tk = (t.get('ticker_canon') or t.get('ticker') or '').upper().replace('.', '-')
        if tk and (t.get('date') or '') >= cut:
            out.append({**t, 'tk': tk})
    return out


def build(root, prices_dir=None, officials_path=None, today=None, run=None):
    root = Path(root)
    run = run or Run(root, minutes=10, client=None, today=today)
    today = run.today
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    tick = tickers(run)
    by_cik = {r['cik']: r for r in tick}
    by_tk = {r['ticker']: r for r in tick}
    S = run.store
    # shares and market caps
    qe = quarter_ends(today, 5)
    sh_frames = [frame(root, 'us-gaap', 'CommonStockSharesOutstanding', f'CY{e.year}Q{(e.month - 1) // 3 + 1}I') for e in qe]

    def shares(cik):
        for f in sh_frames:
            v = f.get(str(cik))
            if v and v[0]:
                return v[0]
        return None
    needed = set()
    for name in ('redflags', 'letters', 'offerings', 'buybacks', 'dividends'):
        needed |= {r.get('ticker') for r in S.get(name).values() if isinstance(r, dict)}
    for d in S.get('deals').values():
        needed |= {d.get('target_ticker'), d.get('acquirer_ticker')}
    needed |= {r.get('symbol') for r in S.get('ipos').values()}
    off = officials(officials_path, today)
    needed |= {t['tk'] for t in off}
    px = last_prices(run, prices_dir, [t for t in needed if t])

    def mcap(tk, cik=None):
        cik = cik or (by_tk.get(tk) or {}).get('cik')
        s, p = shares(cik) if cik else None, px.get(tk)
        return s * p if s and p else None

    def dated(rows, days):
        cut = (today - dt.timedelta(days=days)).isoformat()
        return sorted([dict(r) for r in rows if isinstance(r, dict) and (r.get('filed') or '') >= cut],
                      key=lambda r: (r.get('filed') or '', r.get('accession') or ''), reverse=True)

    # red flags
    flags = dated(list(S.get('redflags').values()), 365)
    for r in flags:
        r['mcap'] = _r(mcap(r.get('ticker'), r.get('cik')), 0) if r.get('ticker') else None
        r['label'] = FLAG_LABEL.get(r['kind'], r['kind'])
    sev_n = {s: sum(1 for r in flags if r['severity'] == s and r['filed'] >= (today - dt.timedelta(days=30)).isoformat()) for s in ('high', 'medium', 'low')}
    write_json(pub / 'redflags.json', {'generated_at': now(), 'rows': flags, 'last30': sev_n,
                                       'note': 'Late filing notices (Form 12b-25), auditor changes (8-K Item 4.01), restatements (Item 4.02) '
                                               'and exchange listing notices (Item 3.01). Severity is a rule of thumb, not a judgment of the company.'})
    # letters: threads per company
    letters = dated(list(S.get('letters').values()), 730)
    threads = {}
    for r in sorted(letters, key=lambda r: r['filed']):
        key = r['cik']
        th = threads.get(key)
        if th is None or (dt.date.fromisoformat(r['filed']) - dt.date.fromisoformat(th['last'])).days > 240:
            th = threads[key] = {'cik': r['cik'], 'ticker': r.get('ticker'), 'company': r.get('company'), 'first': r['filed'], 'last': r['filed'],
                                 'letters': [], 'topics': {}, 'about_form': None, 'about_period': None, 'closed': False}
            threads.setdefault('_all', []).append(th)
        th['letters'].append({k: r.get(k) for k in ('accession', 'form', 'who', 'filed', 'url', 'topics', 'closing', 'excerpt')})
        th['last'] = r['filed']
        for t in r.get('topics') or []:
            th['topics'][t] = th['topics'].get(t, 0) + 1
        th['about_form'] = th['about_form'] or r.get('about_form')
        th['about_period'] = th['about_period'] or r.get('about_period')
        th['closed'] = th['closed'] or bool(r.get('closing'))
    ths = []
    for th in threads.get('_all', []):
        th['topics'] = [k for k, _ in sorted(th['topics'].items(), key=lambda kv: -kv[1])[:4]]
        th['n'] = len(th['letters'])
        th['mcap'] = _r(mcap(th.get('ticker'), th['cik']), 0)
        ths.append(th)
    ths.sort(key=lambda t: t['last'], reverse=True)
    topic_n = {}
    for th in ths:
        if th['last'] >= (today - dt.timedelta(days=90)).isoformat():
            for t in th['topics']:
                topic_n[t] = topic_n.get(t, 0) + 1
    write_json(pub / 'letters.json', {'generated_at': now(), 'threads': ths[:1500], 'topics90': topic_n,
                                      'topic_names': {k: lab for k, _, lab in LETTER_TOPICS},
                                      'note': 'SEC comment letters (UPLOAD) and company responses (CORRESP). The SEC releases them at least '
                                              '20 business days after it completes a review, so these are finished reviews, not open investigations.'})
    # capital: buybacks, dividends, last fiscal year's returns
    buys = dated(list(S.get('buybacks').values()), 365)
    for r in buys:
        m = mcap(r.get('ticker'), r.get('cik'))
        r['mcap'] = _r(m, 0)
        r['pct_mcap'] = _r(r['amount'] / m) if r.get('amount') and m else None
    divs = dated(list(S.get('dividends').values()), 365)
    for r in divs:
        p = px.get(r.get('ticker') or '')
        k = per_year(r.get('freq'))
        r['price'] = p
        r['yield'] = _r(r['amount'] * k / p) if r.get('amount') and k and p else None
    upcoming = sorted([r for r in divs if (r.get('record') or '') >= today.isoformat()], key=lambda r: r['record'])
    y = today.year - 1
    rep = [frame(root, 'us-gaap', 'PaymentsForRepurchaseOfCommonStock', f'CY{yr}') for yr in (y, y - 1)]
    dvc = [frame(root, 'us-gaap', 'PaymentsOfDividendsCommonStock', f'CY{yr}') for yr in (y, y - 1)]
    dva = [frame(root, 'us-gaap', 'PaymentsOfDividends', f'CY{yr}') for yr in (y, y - 1)]
    returns = []
    for cik_s in set(rep[0]) | set(dvc[0]) | set(dva[0]):
        t = by_cik.get(int(cik_s))
        if not t:
            continue
        b = (rep[0].get(cik_s) or [None])[0]
        dv = (dvc[0].get(cik_s) or dva[0].get(cik_s) or [None])[0]
        m = mcap(t['ticker'], t['cik'])
        if not m or m < 1e9:
            continue
        returns.append({'ticker': t['ticker'], 'company': t['title'], 'cik': t['cik'], 'fy': f'CY{y}', 'buybacks': b, 'dividends': dv,
                        'buyback_yield': _r((b or 0) / m), 'dividend_yield': _r((dv or 0) / m), 'total_yield': _r(((b or 0) + (dv or 0)) / m),
                        'mcap': _r(m, 0), 'prev_buybacks': (rep[1].get(cik_s) or [None])[0]})
    returns.sort(key=lambda r: -(r['total_yield'] or 0))
    write_json(pub / 'capital.json', {'generated_at': now(), 'buybacks': buys, 'dividends': divs[:600], 'upcoming': upcoming[:400],
                                      'returns': returns[:800],
                                      'note': 'Buyback authorizations and dividend declarations from 8-Ks; the ex-dividend date equals the record date '
                                              '(T+1 settlement since May 28, 2024). Annual repurchases and dividends: XBRL frames for the last calendar '
                                              'year, against the market cap (shares outstanding × the latest close).'})
    # dilution
    offs = dated(list(S.get('offerings').values()), 365)
    for r in offs:
        m = mcap(r.get('ticker'), r.get('cik'))
        r['mcap'] = _r(m, 0)
        r['pct_mcap'] = _r(r['amount'] / m) if r.get('amount') and m else None
    growth = []
    if len(sh_frames) >= 5:
        newest, year_ago = sh_frames[0], sh_frames[4]
        for cik_s, v in newest.items():
            t = by_cik.get(int(cik_s))
            old = year_ago.get(cik_s)
            if not t or not old or not v[0] or not old[0] or old[0] <= 0:
                continue
            g = v[0] / old[0] - 1
            m = mcap(t['ticker'], t['cik'])
            if abs(g) > 5 or not m or m < 3e8:
                continue
            growth.append({'ticker': t['ticker'], 'company': t['title'], 'cik': t['cik'], 'shares': v[0], 'shares_year_ago': old[0],
                           'as_of': v[1], 'year_ago': old[1], 'change': _r(g), 'mcap': _r(m, 0)})
    growth.sort(key=lambda r: -r['change'])
    write_json(pub / 'dilution.json', {'generated_at': now(), 'offerings': offs[:800], 'share_growth': growth[:400],
                                       'share_shrink': sorted(growth, key=lambda r: r['change'])[:200],
                                       'note': 'Shelf registrations (S-3, F-3), takedowns and at-the-market programs (424B5, sizes as stated on the cover) '
                                               'and the change in shares outstanding over four quarters (XBRL CommonStockSharesOutstanding at quarter ends).'})
    # IPOs
    ipos = dated(list(S.get('ipos').values()), 800)
    daily = S.get('prices')
    for r in ipos:
        if r['stage'] != 'priced':
            continue
        d0 = r.get('date') or r['filed']
        r['lockup_ends'] = (dt.date.fromisoformat(d0) + dt.timedelta(days=r['lockup_days'] or 180)).isoformat()
        r['raised'] = r['price'] * r['shares'] if r.get('price') and r.get('shares') else None
        rows = (daily.get(r.get('symbol') or '') or {}).get('rows') or []
        if rows and r.get('price'):
            first = next((c for d, c in rows if d >= d0), None)
            r['first_close'] = first
            r['last_close'] = rows[-1][1]
            r['since_ipo'] = _r(rows[-1][1] / r['price'] - 1)
            r['first_day'] = _r(first / r['price'] - 1) if first else None
    priced = [r for r in ipos if r['stage'] == 'priced']
    lockups = sorted([r for r in priced if r.get('lockup_ends') and today.isoformat() <= r['lockup_ends'] <= (today + dt.timedelta(days=45)).isoformat()],
                     key=lambda r: r['lockup_ends'])
    write_json(pub / 'ipos.json', {'generated_at': now(), 'priced': priced[:400], 'registered': [r for r in ipos if r['stage'] == 'registered'][:300],
                                   'lockups': lockups,
                                   'note': 'IPO pricings from final prospectuses (424B4) and registrations (S-1, F-1). Lock-up expiry: the prospectus '
                                           'date plus the lock-up it states (180 days when none is found); early releases are not tracked.'})
    # deals
    deals = []
    for d in S.get('deals').values():
        if not (d.get('cash') or d.get('ratio')):
            continue
        tp = px.get(d.get('target_ticker') or '')
        s, ann, days = spread(d, px, today)
        status = 'pending'
        if d.get('close_by') and d['close_by'] < (today - dt.timedelta(days=45)).isoformat() and not tp:
            status = 'closed or delisted'
        elif d.get('completed'):
            status = 'completed'
        deals.append({**{k: v for k, v in d.items() if k != 'docs'}, 'docs': d.get('docs', [])[-6:], 'target_price': tp,
                      'acquirer_price': px.get(d.get('acquirer_ticker') or ''), 'value': _r(deal_value(d, px), 4),
                      'spread': s, 'annualized': ann, 'days_to_close': days, 'status': status})
    deals.sort(key=lambda d: (d['status'] != 'pending', -(d['annualized'] or -9)))
    write_json(pub / 'deals.json', {'generated_at': now(), 'deals': deals[:500],
                                    'note': 'Merger agreements (8-K), merger proxies (DEFM14A / PREM14A) and tender offers (SC TO-T, SC 14D9). Terms are read '
                                            'from the filing text (cash and exchange ratio per share); collars, CVRs and elections are not modelled. '
                                            'Spread = consideration at the acquirer\'s last close ÷ the target\'s last close − 1; annualized to the expected close.'})
    # CEO pay vs TSR
    pay = []
    facts_by = {}
    for yr in (y, y - 1, y - 2):
        for c in PVP:
            for cik_s, v in frame(root, 'ecd', c, f'CY{yr}').items():
                facts_by.setdefault(cik_s, {}).setdefault(c, []).append((v[1], v[0]))
    for cik_s, rec in S.get('paycomp').items():
        if cik_s not in facts_by:
            facts_by[cik_s] = {c: [tuple(x) for x in rec.get('facts', {}).get(c, [])] for c in PVP}
    for cik_s, facts in facts_by.items():
        t = by_cik.get(int(cik_s))
        if not t:
            continue
        pr = paycomp_rows({c: sorted(v) for c, v in facts.items()})
        if not pr:
            continue
        pay.append({'ticker': t['ticker'], 'company': t['title'], 'cik': t['cik'], **pr, 'mcap': _r(mcap(t['ticker'], t['cik']), 0)})
    pay.sort(key=lambda r: -(r.get('total') or 0))
    write_json(pub / 'paycomp.json', {'generated_at': now(), 'rows': pay[:1500],
                                      'note': 'Pay versus performance (Item 402(v), XBRL ecd taxonomy, from the proxy statement): total compensation in the '
                                              'Summary Compensation Table, compensation actually paid, and the value of $100 invested in the stock (TSR) '
                                              'and in the peer group. Misaligned: total pay up 20%+ while the TSR value fell 10%+ in the same year.'})
    # contracts, lobbying, officials
    gov = S.get('gov')
    names = name_index(tick)
    contracts = {}
    for r in gov.get('recipients') or []:
        tk = match_recipient(r.get('name'), names)
        if tk and r.get('amount'):
            c = contracts.setdefault(tk, {'ticker': tk, 'amount': 0.0, 'recipients': []})
            c['amount'] += float(r['amount'])
            c['recipients'].append(r.get('name'))
    awards = []
    for a in gov.get('awards') or []:
        tk = match_recipient(a.get('recipient'), names)
        awards.append({**a, 'ticker': tk})
    lob = S.get('lobby')
    lobbying = []
    for tk, rec in lob.items():
        tot, last = trailing(rec.get('quarters') or {})
        lobbying.append({'ticker': tk, 'client': rec.get('client'), 'trailing4': tot, 'last_quarter': last,
                         'last_amount': (rec.get('quarters') or {}).get(last) if last else None, 'issues': rec.get('issues') or []})
    lob_by = {r['ticker']: r for r in lobbying}
    overlap = []
    for t in off:
        tk = t['tk']
        c, lb = contracts.get(tk), lob_by.get(tk)
        if not ((c and c['amount'] >= 5e7) or (lb and (lb['trailing4'] or 0) >= 1e6)):
            continue
        overlap.append({'person': t.get('person'), 'chamber': 'Senate' if t.get('jurisdiction') == 'US Senate' else 'House', 'ticker': tk,
                        'type': t.get('type'), 'amount_min': t.get('amount_min'), 'amount_max': t.get('amount_max'), 'date': t.get('date'),
                        'filed': t.get('filed_date'), 'owner': t.get('owner'), 'source_url': t.get('source_url'),
                        'contracts_90d': _r(c['amount'], 0) if c else None, 'lobbying_4q': _r(lb['trailing4'], 0) if lb else None,
                        'lobbying_issues': (lb or {}).get('issues') or []})
    overlap.sort(key=lambda r: (r['date'] or '', r['contracts_90d'] or 0), reverse=True)
    cl = sorted(contracts.values(), key=lambda r: -r['amount'])
    for r in cl:
        r['amount'] = _r(r['amount'], 0)
        r['mcap'] = _r(mcap(r['ticker']), 0)
    write_json(pub / 'gov.json', {'generated_at': now(), 'since': gov.get('since'), 'until': gov.get('until'), 'contracts': cl[:300],
                                  'awards': awards[:100], 'lobbying': sorted(lobbying, key=lambda r: -(r['trailing4'] or 0))[:400],
                                  'overlap': overlap[:300],
                                  'note': 'Federal contract obligations by recipient (USAspending.gov, award types A–D, the last 90 days), matched to listed '
                                          'companies only by exact names or well-known subsidiaries; lobbying from the Senate LDA filings (in-house '
                                          'expenses plus outside firms\' income, four quarters). Officials\' trades: House and Senate periodic transaction '
                                          'reports in the last 120 days. A trade in a company with contracts or lobbying is a fact to note, not evidence of anything.'})
    # per company
    per = {}

    def add(tk, key, row):
        if tk:
            per.setdefault(tk, {}).setdefault(key, []).append(row)
    for r in flags:
        add(r.get('ticker'), 'redflags', r)
    for th in ths:
        add(th.get('ticker'), 'letters', th)
    for r in buys:
        add(r.get('ticker'), 'buybacks', r)
    for r in divs:
        add(r.get('ticker'), 'dividends', r)
    for r in offs:
        add(r.get('ticker'), 'offerings', r)
    for r in priced:
        add(r.get('symbol'), 'ipo', r)
    for d in deals:
        add(d.get('target_ticker'), 'deals', {**d, 'role': 'target'})
        add(d.get('acquirer_ticker'), 'deals', {**d, 'role': 'acquirer'})
    for r in pay:
        add(r['ticker'], 'paycomp', r)
    for r in returns:
        add(r['ticker'], 'returns', r)
    for r in growth:
        add(r['ticker'], 'shares', r)
    for r in cl:
        add(r['ticker'], 'contracts', r)
    for r in lobbying:
        add(r['ticker'], 'lobbying', r)
    for r in overlap:
        add(r['ticker'], 'officials', r)
    old = {p.stem for p in (pub / 'c').glob('*.json')}
    for tk, d in per.items():
        fn = re.sub(r'[^A-Z0-9-]', '_', tk.upper())
        write_json(pub / 'c' / f'{fn}.json', {'ticker': tk, 'generated_at': now(), **d})
        old.discard(fn)
    for stem in old:
        (pub / 'c' / f'{stem}.json').unlink()
    # summary
    ix = {'generated_at': now(), 'companies': len(per),
          'counts': {'redflags_30d': sum(sev_n.values()), 'redflags_high_30d': sev_n['high'], 'letter_threads_90d': sum(1 for t in ths if t['last'] >= (today - dt.timedelta(days=90)).isoformat()),
                     'buybacks_90d': sum(1 for r in buys if r['filed'] >= (today - dt.timedelta(days=90)).isoformat()),
                     'dividends_upcoming': len(upcoming), 'offerings_90d': sum(1 for r in offs if r['filed'] >= (today - dt.timedelta(days=90)).isoformat()),
                     'ipos_priced_365d': len(priced), 'lockups_45d': len(lockups), 'deals_pending': sum(1 for d in deals if d['status'] == 'pending'),
                     'paycomp': len(pay), 'contract_companies': len(cl), 'lobbying_companies': len(lobbying), 'official_overlaps': len(overlap)},
          'latest': {'redflags': flags[:12], 'buybacks': buys[:8], 'offerings': offs[:8], 'lockups': lockups[:8],
                     'deals': [d for d in deals if d['status'] == 'pending'][:8]}}
    write_json(pub / 'index.json', ix)
    status = {'built_at': now(), 'companies': len(per), **ix['counts'], 'errors': run.errors[:20], 'counts_run': run.counts}
    write_json(pub / 'status.json', status)
    return status


# ------------------------------------------------------------------ the run
def lobbying_targets(run, tick, officials_path):
    names = {r['ticker']: r['title'] for r in tick}
    want, seen = [], set()
    gov = run.store.get('gov')
    nidx = name_index(tick)
    for r in (gov.get('recipients') or [])[:150]:
        tk = match_recipient(r.get('name'), nidx)
        if tk and tk not in seen and tk in names:
            seen.add(tk)
            want.append((tk, names[tk]))
    for t in officials(officials_path, run.today):
        if t['tk'] in names and t['tk'] not in seen:
            seen.add(t['tk'])
            want.append((t['tk'], names[t['tk']]))
    return want


def run_all(root, events_src=None, officials_path=None, prices_dir=None, minutes=40, backfill=60, steps=None, client=None, today=None):
    run = Run(root, minutes=minutes, client=client or http_client(), today=today)
    steps = steps or ['index', 'filings', 'events', 'frames', 'paycomp', 'prices', 'contracts', 'lobbying']
    tick = tickers(run)
    for step in steps:
        if run.left(reserve=0.03) < 0:
            break
        try:
            if step == 'index':
                read_indexes(run, backfill=backfill if not run.state.get('index_days') else 10)
            elif step == 'filings':
                process_filings(run, tick)
            elif step == 'events':
                process_events(run, tick, events_src)
            elif step == 'frames':
                collect_frames(run)
            elif step == 'paycomp':
                collect_paycomp(run, tick)
            elif step == 'prices':
                want = {}
                for d in run.store.get('deals').values():
                    if d.get('announced', '') >= (run.today - dt.timedelta(days=500)).isoformat():
                        want[d.get('target_ticker')] = '6mo'
                        if d.get('ratio'):
                            want[d.get('acquirer_ticker')] = '6mo'
                for r in run.store.get('ipos').values():
                    if r.get('stage') == 'priced' and r.get('symbol'):
                        want[r['symbol']] = '2y'
                collect_prices(run, want)
            elif step == 'contracts':
                collect_contracts(run)
            elif step == 'lobbying':
                collect_lobbying(run, lobbying_targets(run, tick, officials_path))
        except Exception as exc:
            run.err(step, exc)
        run.save()
    status = build(root, prices_dir, officials_path, run=run)
    run.save()
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cmd', choices=['all', 'build'])
    ap.add_argument('--root', default='rf')
    ap.add_argument('--events8k', default=None, help="the hub's 8-K events: a cache/events8k directory or a published market/events8k.json")
    ap.add_argument('--officials', default=None, help="the hub's market/officials-trades.json")
    ap.add_argument('--prices', default=None, help='public/ of rotation-history (weekly closes in t/<TICKER>.json)')
    ap.add_argument('--minutes', type=float, default=40)
    ap.add_argument('--backfill', type=int, default=60, help='business days of daily indexes on the first run')
    ap.add_argument('--steps', default='', help='comma-separated subset: index, filings, events, frames, paycomp, prices, contracts, lobbying')
    a = ap.parse_args()
    if a.cmd == 'build':
        print(json.dumps(build(a.root, a.prices, a.officials)), flush=True)
    else:
        steps = [s.strip() for s in a.steps.split(',') if s.strip()] or None
        print(json.dumps(run_all(a.root, a.events8k, a.officials, a.prices, a.minutes, a.backfill, steps)), flush=True)


if __name__ == '__main__':
    main()
