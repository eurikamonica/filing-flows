"""Who holds a stock or an ETF, quarter by quarter (the video studio's "Major holders" video): at every quarter-end since
2013 Q2, each 13F manager's (or fund family's) shares and reported value, the largest holders, and every 13F holder
together.

  source    SEC's Form 13F data sets (DERA): every 13F filed as XML since May 2013 — one zip a calendar quarter of filing
            dates until 2024 (2013q2_form13f.zip), then one per three-month window (01dec2025-28feb2026_form13f.zip).
            SUBMISSION (filer, period, filing date, form), COVERPAGE (amendment type, manager name, report type) and
            INFOTABLE (each line: CUSIP, value, shares or principal, put/call). One request a data set, none per filing.
            The site's own 13F files (cache/holdings) keep the index giants only from Q4 2024, so they cannot give this.
  reading   13F holdings and combination reports (notices hold nothing); a manager's quarter is its latest original or
            restatement and the "new holdings" amendments after it — the rule of holdings13f.core.resolve; shares (SH)
            only, options and principal amounts left out; values ×1000 where the filing reported thousands (the rule
            until 2023, and any filing whose value per share reads as cents: holdings13f.core.in_thousands)
  families  the filers of one fund family count as one holder — Vanguard files as Vanguard Capital Management and
            Vanguard Portfolio Management from 2026, BlackRock under a new CIK from Q4 2024 (FAMILIES)
  quarters  a quarter is closed once the data set whose window starts CLOSE_DAYS after it is read (late filers and
            amendments are in by then); until then each run reads it again from the data sets that hold its filings
  tickers   CUSIP → ticker from the Hub's map (market/cusip-tickers.json); a CUSIP it lacks (an issuer outside the US,
            a CUSIP replaced in a merger or a new holding company) by its issuer's name when exactly one SEC listing
            carries that name; a few renamed ones by hand (FORMER); a company's share classes together (CLASSES)

  managers  the same pass keeps each filer's own quarter (the 13F holdings video of a manager, web/actual-weights.js):
            its long equity book (shares, ETFs), the number of lines, puts and calls (their underlying value), its
            MKEEP largest positions and the book by sector over every line (CUSIP → ticker → the site's sector) — for
            the filers the site's own 13F files keep only from Q4 2024 (more than GIANT positions: holdings13f/ranges.py)

  cache/sets.json                     the data sets read, the quarters closed
  cache/periods/<YYYY-MM-DD>.json.gz  per CUSIP: 13F holders, shares and value in all, the KEEP largest holders
  cache/managers/<YYYY-MM-DD>.json.gz per filer: its book (MANAGER_FIELDS); filers of MIN_BOOK lines or MIN_BOOK_USD
  public/c/<TICKER>.json              per ticker: the quarters, the 13F filers on file, all 13F holders, the TOP largest
  public/m/<CIK>.json                 per manager of more than GIANT positions: its books, quarter by quarter
  public/index.json, public/m/index.json, public/cusips.json (CUSIP → ticker), public/status.json

    python app/holders_history.py collect --root hh --minutes 40 [--hub disclosures/docs/data --sectors a.json b.json …]
    python app/holders_history.py build --root hh --hub disclosures/docs/data
"""
import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from array import array
from collections import Counter, defaultdict
from pathlib import Path

PAGE = 'https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets'
MIN_PERIOD = '2013-06-30'      # the first quarter filed as XML throughout (filings from May 20, 2013)
CLOSE_DAYS = 140                # a quarter is final once a data set starting this long after it has been read
KEEP = 30                       # largest holders kept per CUSIP and quarter (a family's smaller filers fall inside it)
TOP = 20                        # largest holders published per ticker and quarter
MIN_USD = 1_000_000             # a CUSIP's quarter below this in all is left out of the cache
MKEEP = 100                     # a manager's largest positions kept per quarter: the video's bands are the 12–20 largest on
                                # average, which a book of thousands of lines can hold below its 40th position some quarters
MIN_BOOK, MIN_BOOK_USD = 200, 1e9   # a filer's quarter kept in cache/managers: this many lines, or this much in all
GIANT = 500                     # managers published in public/m: more lines than this in some quarter (the site's own
                                # 13F files read the others back to 2013 or 2021, holdings13f/ranges.py tiers)
MANAGERS_VERSION = 2            # cache/managers' layout: a new one reads every data set again (sets.json "mversion")
                                # (2: the 100 largest positions, not 40)
WUNIT = 1e-5                    # public/m weights: hundred-thousandths of the long equity book
SECTORS = ('technology', 'communication', 'consumer-disc', 'consumer-staples', 'health', 'financials', 'real-estate',
           'energy', 'materials', 'industrials', 'utilities')
MANAGER_FIELDS = ['usd', 'lines', 'put', 'call', 'top', 'sectors']   # top: [[cusip, shares, usd]]; sectors: {key: usd}
csv.field_size_limit(1 << 30)

# fund families: one holder however many filers (CIKs) report for it — [name, short label, CIKs]
FAMILIES = {
    'vanguard': ['Vanguard', 'Vanguard', [102909, 2100119, 2100121, 933478, 1811242, 1680208, 1550100, 1767306, 1984256, 947529]],
    # until 2016 BlackRock reported through its trust company, fund advisors, UK group, advisors and investment managers
    'blackrock': ['BlackRock', 'BlackRock', [1364742, 2012383, 913414, 1006249, 1003283, 1086364, 1305227, 1085635]],
    'capital': ['Capital Group', 'Capital Group', [1422848, 1422849, 1562230, 895213, 1065349, 1065350, 314965]],
    'troweprice': ['T. Rowe Price', 'T. Rowe Price', [80255, 1897612]],
    'ubs': ['UBS', 'UBS', [1114446, 1610520, 861177, 1132716]],
    'schwab': ['Charles Schwab', 'Schwab', [884546, 1789219, 1501902]],
    'tiaa': ['TIAA / Nuveen', 'Nuveen (TIAA)', [887793, 939222, 1091559, 1711615, 1997405, 1521019, 1871926, 2124867, 315038]],
    'janus': ['Janus Henderson', 'Janus Henderson', [812295, 1274173]],
    'twosigma': ['Two Sigma', 'Two Sigma', [1478735, 1179392]],
    'cibc': ['CIBC', 'CIBC', [1421224, 1021926, 1056527, 1298088]],
    'mufg': ['Mitsubishi UFJ (MUFG)', 'MUFG', [67088, 1462160, 1466546, 1597694]],
}
FAMILY_OF = {cik: key for key, (_, _, ciks) in FAMILIES.items() for cik in ciks}
# the names filers report under, as people say them: [name, short label]
PRETTY = {
    315066: ['Fidelity (FMR)', 'Fidelity'], 93751: ['State Street', 'State Street'], 1214717: ['Geode Capital Management', 'Geode'],
    895421: ['Morgan Stanley', 'Morgan Stanley'], 886982: ['Goldman Sachs', 'Goldman Sachs'], 19617: ['JPMorgan Chase', 'JPMorgan'],
    70858: ['Bank of America', 'BofA'], 72971: ['Wells Fargo', 'Wells Fargo'], 73124: ['Northern Trust', 'Northern Trust'],
    1390777: ['BNY Mellon', 'BNY Mellon'], 1067983: ['Berkshire Hathaway', 'Berkshire'], 914208: ['Invesco', 'Invesco'],
    38777: ['Franklin Templeton', 'Franklin'], 354204: ['Dimensional Fund Advisors', 'Dimensional'],
    902219: ['Wellington Management', 'Wellington'], 764068: ['Legal & General', 'Legal & General'], 1330387: ['Amundi', 'Amundi'],
    820027: ['Ameriprise Financial', 'Ameriprise'], 948046: ['Deutsche Bank', 'Deutsche Bank'], 1374170: ['Norges Bank', 'Norges Bank'],
    1595888: ['Jane Street', 'Jane Street'], 1423053: ['Citadel Advisors', 'Citadel'], 1446194: ['Susquehanna', 'Susquehanna'],
    1009207: ['D. E. Shaw', 'D. E. Shaw'], 1871926: ['Nuveen', 'Nuveen'], 1350694: ['Bridgewater Associates', 'Bridgewater'],
}
# CUSIPs the Hub's map cannot name and whose issuer was renamed (so no name matches): CUSIP → ticker
FORMER = {'38259P508': 'GOOGL', '38259P706': 'GOOG', '74005P104': 'LIN', 'Y0486S104': 'AVGO', 'Y09827109': 'AVGO', '73935A104': 'QQQ'}
# a company's share classes in one file: class → (the ticker it joins, its shares in the other's: 1 class A = 1,500 B)
CLASSES = {'GOOG': ('GOOGL', 1), 'BRK-A': ('BRK-B', 1500), 'FOX': ('FOXA', 1), 'NWS': ('NWSA', 1)}
NOT_COMMON = re.compile(r'\b(PFD|PREF|PREFERRED|NOTE|NOTES|WT|WTS|WARRANT|WARRANTS|RIGHT|RIGHTS|UNIT|UNITS|DEB|DEBT|BOND|CONV|WHEN|WI|EXDISTRIB\w*|EX DISTRIB\w*|TRACKING)\b', re.I)
STOP = set('INC INCORPORATED CORP CORPORATION CO COMPANY LTD LIMITED PLC NEW DEL THE HLDGS HOLDINGS HOLDING GROUP SA NV AG SE LLC LP '
           'COM CL CLASS SHS ORD N V S A B C IRELAND BERMUDA SWITZERLAND NETHERLANDS JERSEY CAYMAN LUXEMBOURG UK NY MD DE'.split())
MON = {m: i + 1 for i, m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
# the short forms 13F issuer names use (cut to 28 characters): 'JOHNSON CTLS INTL PLC' is Johnson Controls International plc
ABBR = {'INTL': 'INTERNATIONAL', 'CTLS': 'CONTROLS', 'TECH': 'TECHNOLOGY', 'TECHNOLOGIES': 'TECHNOLOGY', 'MFG': 'MANUFACTURING',
        'SVCS': 'SERVICES', 'SVC': 'SERVICES', 'COS': 'COMPANIES', 'FINL': 'FINANCIAL', 'PHARMACEUTICALS': 'PHARMACEUTICAL',
        'PPTYS': 'PROPERTIES', 'RLTY': 'REALTY', 'INVT': 'INVESTMENT', 'MGMT': 'MANAGEMENT', 'COMMUNICATIONS': 'COMMUNICATION',
        'SYS': 'SYSTEMS', 'HLDNGS': '', 'HLDGS': '', 'HLDG': '', 'HOLDG': '', 'PL': '', 'LT': '', 'INDS': 'INDUSTRIES', 'BANCORPORATION': 'BANCORP'}


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def day(s):
    """'31-DEC-2023' or '12/31/2023' or '2023-12-31' → '2023-12-31'; '' when it is not a date."""
    s = (s or '').strip()
    m = re.fullmatch(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', s)
    if m and m.group(2).upper() in MON:
        return f'{m.group(3)}-{MON[m.group(2).upper()]:02d}-{int(m.group(1)):02d}'
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        return f'{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'
    return s[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s[:10]) else ''


def window(name):
    """A data set's filing-date window from its file name: (start, end) ISO dates, or None."""
    n = name.rsplit('/', 1)[-1].lower()
    m = re.match(r'(\d{4})q([1-4])_form13f\.zip$', n)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        end = dt.date(y, 3 * q, 1) + dt.timedelta(days=31)
        return dt.date(y, 3 * q - 2, 1).isoformat(), (end.replace(day=1) - dt.timedelta(days=1)).isoformat()
    m = re.match(r'(\d{2})([a-z]{3})(\d{4})-(\d{2})([a-z]{3})(\d{4})_form13f\.zip$', n)
    if m and m.group(2).upper() in MON and m.group(5).upper() in MON:
        a = dt.date(int(m.group(3)), MON[m.group(2).upper()], int(m.group(1)))
        b = dt.date(int(m.group(6)), MON[m.group(5).upper()], int(m.group(4)))
        return a.isoformat(), b.isoformat()
    return None


def listing(page_html, base=PAGE):
    """[(url, start, end)] of every data set the page links, oldest first."""
    out = {}
    for href in re.findall(r'href="([^"]+_form13f\.zip)"', page_html, re.I):
        url = urllib.parse.urljoin(base, href)
        w = window(url)
        if w:
            out[url.rsplit('/', 1)[-1].lower()] = (url, w[0], w[1])
    return sorted(out.values(), key=lambda x: x[1])


BASE = 'https://www.sec.gov/files/structureddata/data/form-13f-data-sets/'


def with_early(sets):
    """The listing, plus the calendar-quarter sets from 2013 Q2 up to its earliest window by their known address when
    the page lists only the recent ones (a set that is not there is skipped when read)."""
    if not sets or sets[0][1] <= '2013-06-30':
        return sets
    early, y, q = [], 2013, 2
    while True:
        name = f'{y}q{q}_form13f.zip'
        w = window(name)
        if w[1] >= sets[0][1]:
            break
        early.append((BASE + name, w[0], w[1]))
        q += 1
        if q > 4:
            y, q = y + 1, 1
    return early + sets


def closes(period, start):
    """True once a data set starting at `start` comes CLOSE_DAYS or more after the quarter `period`."""
    return start >= (dt.date.fromisoformat(period) + dt.timedelta(days=CLOSE_DAYS)).isoformat()


def name_key(s):
    """An issuer's name without its legal form, punctuation and country: 'MEDTRONIC PLC' and 'Medtronic plc' → 'MEDTRONIC'."""
    s = re.sub(r'/[A-Z]{2,4}/?', ' ', (s or '').upper())
    words = [ABBR.get(w, w) for w in re.sub(r'[^A-Z0-9 ]+', ' ', s.replace('&', ' AND ')).split() if w not in STOP]
    return ''.join(w for w in words if w)


def cusip_ok(c):
    """A real CUSIP: its ninth character is the check digit of the first eight (some filers type a SEDOL or an ISIN's
    middle instead, '00BTN1Y11')."""
    if not re.fullmatch(r'[0-9A-Z*@#]{8}[0-9]', c or ''):
        return False
    tot = 0
    for i, ch in enumerate(c[:8]):
        v = int(ch) if ch.isdigit() else ord(ch) - 55 if ch.isalpha() else 36 + '*@#'.index(ch)
        if i % 2:
            v *= 2
        tot += v // 10 + v % 10
    return (10 - tot % 10) % 10 == int(c[8])


def class_letter(s):
    m = re.search(r'\bCL(?:ASS)?\s*([A-Z])\b', (s or '').upper())
    return m.group(1) if m else ''


def pretty(name, cik=None):
    """[name, short label] for a filer: the families' and the best-known filers' own, else the name as filed, tidied."""
    if cik in PRETTY:
        return PRETTY[cik]
    s = re.sub(r'\s*/[A-Z]{2,4}/?\s*$', '', (name or '').strip()).rstrip('\\ ,.')
    for _ in range(3):
        s2 = re.sub(r'[\s,]+(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LLC|L\.L\.C|LP|L\.P|LLP|LTD|LIMITED|PLC|N\.A|NA|S\.A|SA|AG|SE|NV|N\.V)\.?$', '', s, flags=re.I)
        if s2 == s:
            break
        s = s2.rstrip(' ,.')
    if s.isupper():
        keep = {'FMR', 'UBS', 'BNY', 'AQR', 'DWS', 'RBC', 'BMO', 'TD', 'ING', 'AXA', 'HSBC', 'PNC', 'USAA', 'LPL', 'TIAA', 'CIBC', 'MUFG', 'BNP', 'II', 'III', 'IV'}
        small = {'OF', 'AND', 'THE', 'FOR', 'IN', 'AT', 'ON', 'DE', 'LA'}
        out = []
        for i, w in enumerate(s.split()):
            if w in keep or (len(w) <= 3 and not re.search(r'[AEIOUY]', w)):
                out.append(w)
            elif i and w in small:
                out.append(w.lower())
            else:
                out.append(re.sub(r"(^|[-'.&])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w.lower()))
        s = ' '.join(out)
    short = s
    for tail in (' Capital Management', ' Asset Management', ' Investment Management', ' Management', ' Advisors', ' Advisers',
                 ' Investments', ' Investment', ' Partners', ' Group', ' Holdings', ' Financial', ' Capital'):
        if short.endswith(tail) and len(short) > len(tail) + 2:
            short = short[:-len(tail)]
    if len(short) > 16:
        cut = short[:16].rsplit(' ', 1)[0]
        short = cut if len(cut) >= 4 else short[:16]
    return [s or (name or ''), short or s]


def holder_key(cik):
    fam = FAMILY_OF.get(cik)
    return 'f:' + fam if fam else 'c%d' % cik


# ------------------------------------------------------------------ reading one data set
def _members(z):
    """{'SUBMISSION': name, …} of a data set's tables, whatever folder or case they come in."""
    out = {}
    for n in z.namelist():
        base = n.rsplit('/', 1)[-1].upper()
        if base.endswith('.TSV'):
            out[base[:-4]] = n
    return out


def _rows(z, name):
    with z.open(name) as raw:
        rd = csv.reader(io.TextIOWrapper(raw, encoding='utf-8', errors='replace', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE)
        head = [h.strip().upper() for h in next(rd, [])]
        yield head
        for r in rd:
            yield r


def _num(s):
    try:
        return float(str(s).replace(',', '').strip() or 'nan')
    except ValueError:
        return float('nan')


class Book:
    """The filings of the open quarters, as compact arrays: period → cik → [(filed, accession, kind, cusip ids, shares,
    values)], with the CUSIPs and names seen."""

    def __init__(self, closed=(), sector_of=None):
        self.closed = set(closed)
        self.sector_of = sector_of or (lambda cusip: None)     # CUSIP → one of SECTORS (or None), for the managers' books
        self.cusip_id, self.cusips = {}, []
        self.issuer = {}                           # cusip id → Counter of (issuer, class)
        self.names = {}                            # cik → (filed, name)
        self.filings = defaultdict(lambda: defaultdict(list))
        self.seen = set()                          # accessions kept (a filing in two data sets counts once)
        self.stats = Counter()

    def cid(self, cusip):
        i = self.cusip_id.get(cusip)
        if i is None:
            i = self.cusip_id[cusip] = len(self.cusips)
            self.cusips.append(cusip)
        return i

    def read(self, path):
        """Every holdings report of an open quarter in one data set (a zip on disk)."""
        z = zipfile.ZipFile(path)
        T = _members(z)
        for need in ('SUBMISSION', 'COVERPAGE', 'INFOTABLE'):
            if need not in T:
                raise ValueError(f'{Path(path).name}: no {need} table ({", ".join(sorted(T))})')
        sub = {}
        it = _rows(z, T['SUBMISSION'])
        h = next(it)
        ix = {k: h.index(k) for k in ('ACCESSION_NUMBER', 'FILING_DATE', 'SUBMISSIONTYPE', 'CIK', 'PERIODOFREPORT') if k in h}
        for r in it:
            try:
                acc = r[ix['ACCESSION_NUMBER']].strip()
                form = r[ix['SUBMISSIONTYPE']].strip().upper()
                period, filed = day(r[ix['PERIODOFREPORT']]), day(r[ix['FILING_DATE']])
                cik = int(r[ix['CIK']])
            except (IndexError, KeyError, ValueError):
                continue
            if not form.startswith('13F-HR') or not period or not filed:
                continue                           # notices (13F-NT) hold nothing
            sub[acc] = [cik, period, filed, form.endswith('/A')]
        cov = {}
        it = _rows(z, T['COVERPAGE'])
        h = next(it)
        get = lambda r, k: (r[h.index(k)].strip() if k in h and h.index(k) < len(r) else '')
        for r in it:
            acc = get(r, 'ACCESSION_NUMBER')
            if acc in sub:
                cov[acc] = (get(r, 'AMENDMENTTYPE').upper(), get(r, 'FILINGMANAGER_NAME'), get(r, 'REPORTTYPE').upper())
        keep = {}
        for acc, (cik, period, filed, amended) in sub.items():
            atype, name, rtype = cov.get(acc, ('', '', ''))
            if 'NOTICE' in rtype:
                continue
            kind = ('RESTATEMENT' if 'RESTATE' in atype else 'NEW HOLDINGS' if 'NEW' in atype else None) if amended else 'ORIGINAL'
            if name and (cik not in self.names or filed >= self.names[cik][0]):
                self.names[cik] = (filed, name)
            if kind is None:
                self.stats['amendment of no known type'] += 1
                continue
            if period < MIN_PERIOD or period in self.closed or acc in self.seen:
                continue
            keep[acc] = (cik, period, filed, kind)
        lines = defaultdict(dict)                  # accession → cusip id → [shares, value]
        opts = defaultdict(lambda: [0.0, 0.0])     # accession → [puts, calls] (the value of the shares under them)
        it = _rows(z, T['INFOTABLE'])
        h = next(it)
        need = ('ACCESSION_NUMBER', 'NAMEOFISSUER', 'TITLEOFCLASS', 'CUSIP', 'VALUE', 'SSHPRNAMT', 'SSHPRNAMTTYPE', 'PUTCALL')
        I = {k: h.index(k) for k in need if k in h}
        n = len(h)
        for r in it:
            if len(r) < n:
                r = r + [''] * (n - len(r))
            acc = r[I['ACCESSION_NUMBER']].strip()
            if acc not in keep:
                continue
            pc = r[I['PUTCALL']].strip().upper() if 'PUTCALL' in I else ''
            if pc:                                 # an option: counted for its manager's book, not a holding
                v = _num(r[I['VALUE']])
                if v > 0:
                    opts[acc][0 if pc.startswith('P') else 1] += v
                continue
            if r[I['SSHPRNAMTTYPE']].strip().upper() != 'SH':
                continue
            cusip = r[I['CUSIP']].strip().upper()
            if not re.fullmatch(r'[0-9A-Z]{9}', cusip) or cusip == '000000000':
                continue
            sh, val = _num(r[I['SSHPRNAMT']]), _num(r[I['VALUE']])
            if not (sh > 0) or not (val >= 0):
                continue
            c = self.cid(cusip)
            nm = (r[I['NAMEOFISSUER']].strip(), r[I['TITLEOFCLASS']].strip())
            ctr = self.issuer.setdefault(c, Counter())
            if len(ctr) < 6 or nm in ctr:
                ctr[nm] += 1
            a = lines[acc].get(c)
            if a:
                a[0] += sh
                a[1] += val
            else:
                lines[acc][c] = [sh, val]
            self.stats['lines'] += 1
        for acc, d in lines.items():
            cik, period, filed, kind = keep[acc]
            per = sorted(v[1] / v[0] for v in d.values() if v[0] > 0 and v[1] > 0)
            med = per[len(per) // 2] if per else None
            k = 1000 if med is not None and med < (5 if filed < '2023-01-03' else 0.5) else 1     # reported in thousands
            ids, shs, vals = array('i'), array('d'), array('d')
            for c, (sh, val) in d.items():
                ids.append(c)
                shs.append(sh)
                vals.append(val * k)
            o = opts.get(acc, (0.0, 0.0))
            self.filings[period][cik].append((filed, acc, kind, ids, shs, vals, o[0] * k, o[1] * k))
            self.seen.add(acc)
            self.stats['filings'] += 1
        z.close()

    def close(self, period):
        """The quarter as one table: per CUSIP the holders, shares and value in all and the KEEP largest holders
        (families together); its filings dropped from memory."""
        import numpy as np
        by_cik = self.filings.pop(period, {})
        keys, kidx = [], {}
        C, K, S, V = [], [], [], []
        filers = 0
        books = []                                # (cik, cusip ids, shares, values, puts, calls): the managers' own quarters
        for cik, fs in by_cik.items():
            parts = []
            for f in sorted(fs, key=lambda f: (f[0], f[1])):
                if f[2] in ('ORIGINAL', 'RESTATEMENT'):
                    parts = [f]
                elif parts:                        # new holdings: added to the report they amend
                    parts.append(f)
            if not parts:
                continue
            filers += 1
            ids = np.concatenate([np.frombuffer(p[3], dtype=np.int32) for p in parts])
            sh = np.concatenate([np.frombuffer(p[4], dtype=np.float64) for p in parts])
            va = np.concatenate([np.frombuffer(p[5], dtype=np.float64) for p in parts])
            if len(parts) > 1:                     # a CUSIP in the original and an amendment: one position
                u, inv = np.unique(ids, return_inverse=True)
                ids, sh, va = u.astype(np.int32), np.bincount(inv, weights=sh), np.bincount(inv, weights=va)
            books.append((cik, ids, sh, va, sum(p[6] for p in parts if len(p) > 7), sum(p[7] for p in parts if len(p) > 7)))
            hk = holder_key(cik)
            if hk not in kidx:
                kidx[hk] = len(keys)
                keys.append(hk)
            C.append(ids)
            K.append(np.full(len(ids), kidx[hk], dtype=np.int64))
            S.append(sh)
            V.append(va)
        out = {'period': period, 'filers': filers, 'rows': {}, 'names': {}, 'issuers': {}}
        self.last_books = self.books(period, books)   # collect() writes it beside the quarter (cache/managers)
        if not C:
            return out
        c, k, s, v = np.concatenate(C).astype(np.int64), np.concatenate(K), np.concatenate(S), np.concatenate(V)
        n = int(c.max()) + 1
        holders = np.bincount(c, minlength=n)                  # filers holding each CUSIP
        tot_s, tot_v = np.bincount(c, weights=s, minlength=n), np.bincount(c, weights=v, minlength=n)
        key = c * len(keys) + k                                 # one row per CUSIP and holder (a family's filers summed)
        u, inv = np.unique(key, return_inverse=True)
        hs, hv = np.bincount(inv, weights=s), np.bincount(inv, weights=v)
        uc, uk = u // len(keys), u % len(keys)
        order = np.lexsort((-hs, uc))
        uc, uk, hs, hv = uc[order], uk[order], hs[order], hv[order]
        starts = np.flatnonzero(np.r_[True, uc[1:] != uc[:-1]])
        ends = np.r_[starts[1:], len(uc)]
        used = set()
        for a, b in zip(starts, ends):
            ci = int(uc[a])
            if tot_v[ci] < MIN_USD:
                continue
            top = [[keys[int(uk[j])], int(round(hs[j])), int(round(hv[j]))] for j in range(a, min(b, a + KEEP))]
            used.update(t[0] for t in top)
            cusip = self.cusips[ci]
            out['rows'][cusip] = [int(holders[ci]), int(round(tot_s[ci])), int(round(tot_v[ci])), top]
            ctr = self.issuer.get(ci)
            if ctr:
                out['issuers'][cusip] = list(ctr.most_common(1)[0][0])
        for hk in used:
            if hk.startswith('c'):
                cik = int(hk[1:])
                out['names'][hk] = (self.names.get(cik) or ('', ''))[1]
        return out

    def books(self, period, books):
        """Each filer's own quarter (cache/managers): [usd, lines, puts, calls, its MKEEP largest [cusip, shares, usd], its
        book by sector over every line {sector: usd}] for the filers of MIN_BOOK lines or MIN_BOOK_USD; the issuers of the
        CUSIPs kept and the filers' names."""
        import numpy as np
        out = {'period': period, 'fields': MANAGER_FIELDS, 'rows': {}, 'issuers': {}, 'names': {}}
        if not books:
            return out
        n = len(self.cusips)
        sec = getattr(self, '_sec', None)
        if sec is None or len(sec) < n:            # a sector index for every CUSIP seen (len(SECTORS): none known)
            old = 0 if sec is None else len(sec)
            add = np.array([SECTORS.index(x) if x in SECTORS else len(SECTORS)
                            for x in (self.sector_of(c) for c in self.cusips[old:n])], dtype=np.int64)
            sec = self._sec = add if sec is None else np.concatenate([sec, add])
        used = set()
        for cik, ids, sh, va, put, call in books:
            usd = float(va.sum())
            if len(ids) < MIN_BOOK and usd < MIN_BOOK_USD:
                continue
            order = np.argsort(-va, kind='stable')[:MKEEP]
            top = [[self.cusips[int(ids[j])], int(round(sh[j])), int(round(va[j]))] for j in order if va[j] > 0]
            used.update(t[0] for t in top)
            by = np.bincount(sec[ids.astype(np.int64)], weights=va, minlength=len(SECTORS) + 1)
            sectors = {SECTORS[i]: int(round(by[i])) for i in range(len(SECTORS)) if by[i] > 0}
            out['rows'][str(cik)] = [int(round(usd)), int(len(ids)), int(round(put)), int(round(call)), top, sectors]
            out['names'][str(cik)] = (self.names.get(cik) or ('', ''))[1]
        for cusip in used:
            ctr = self.issuer.get(self.cusip_id[cusip])
            if ctr:
                out['issuers'][cusip] = list(ctr.most_common(1)[0][0])
        return out


# ------------------------------------------------------------------ collect: the data sets, quarter by quarter
class Missing(Exception):
    """SEC has no such file (404): a data set guessed by its address that was never published."""


def sec_get(url, ua, dest=None, tries=4, timeout=600):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if dest is None:
                    return r.read()
                with open(dest, 'wb') as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                return dest
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise Missing(url)
            err = exc
            time.sleep(10 * (i + 1))
        except Exception as exc:                   # 403 / 429 / 5xx / a dropped connection: wait and try again
            err = exc
            time.sleep(10 * (i + 1))
    raise RuntimeError(f'{url}: {err}')


def write_gz(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
    os.replace(tmp, path)


def read_gz(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def ticker_sectors(paths):
    """Ticker → the site's sector from its files: the rank panel's meta ({cos: [[ticker, name, sector]]}), the ETF build's
    sectors ({sectors: {ticker: sector}}) and the site's index ({companies: [{ticker, sector}]}); the first file that
    names a ticker wins."""
    out = {}
    norm = lambda t: str(t or '').strip().upper().replace('.', '-').replace('/', '-')
    for path in paths or ():
        try:
            d = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        pairs = []
        if isinstance(d, dict) and isinstance(d.get('cos'), list):
            pairs = [(r[0], r[2]) for r in d['cos'] if isinstance(r, list) and len(r) > 2]
        elif isinstance(d, dict) and isinstance(d.get('sectors'), dict):
            pairs = list(d['sectors'].items())
        elif isinstance(d, dict) and isinstance(d.get('companies'), list):
            pairs = [(c.get('ticker'), c.get('sector')) for c in d['companies'] if isinstance(c, dict)]
        for t, sec in pairs:
            if norm(t) and sec in SECTORS:
                out.setdefault(norm(t), sec)
    return out


def sector_map(root, hub=None, sectors=()):
    """CUSIP → sector for the managers' books: CUSIP → ticker (the last build's public/cusips.json; else the Hub's map
    and the names of the quarters on file, ticker_map), then ticker → sector (ticker_sectors). Returns (function, how
    many CUSIPs and tickers it knows)."""
    root = Path(root)
    tick = ticker_sectors(sectors)
    cmap = {}
    if hub:                                        # the Hub's map, whole: CUSIPs no quarter on file has yet included
        try:
            cmap = {c.upper(): t.upper().replace('/', '-').replace('.', '-')
                    for c, t in json.loads((Path(hub) / 'market' / 'cusip-tickers.json').read_text()).items() if t}
        except (OSError, ValueError):
            pass
    try:
        cmap.update(json.loads((root / 'public' / 'cusips.json').read_text(encoding='utf-8')).get('cusips') or {})
    except (OSError, ValueError):                  # no build yet: the names of the quarters on file, as build() names them
        if hub:
            files = sorted((root / 'cache' / 'periods').glob('*.json.gz'))
            periods = [(f.name[:10], read_gz(f, {'rows': {}, 'issuers': {}})) for f in files]
            try:
                cmap.update(ticker_map(hub, periods)[0])
            except Exception:                      # noqa: BLE001 — the books go on with fewer sectors rather than stop
                pass
    def of(cusip):
        t = cmap.get(cusip) or FORMER.get(cusip)
        if t in CLASSES:
            t = CLASSES[t][0]
        return tick.get(t)
    return of, {'cusips': len(cmap), 'tickers': len(tick)}


def plan(sets, state):
    """The data sets this run reads: none when every listed set has been read (a set never changes, so the open
    quarters can only change with a new one); else from the first set that can hold filings of the earliest quarter
    not yet closed (its window ends after the quarter-end) to the newest — the sets read before are read again for
    those quarters, the closed quarters' lines in them passed over."""
    if not sets:
        return []
    closed, done = set(state.get('closed') or []), set(state.get('done') or [])
    names = [u.rsplit('/', 1)[-1].lower() for u, _, _ in sets]
    new = [i for i, n in enumerate(names) if n not in done]
    if not new:
        return []
    lo, read = new[0], [i for i, n in enumerate(names) if n in done]
    if read:
        last_end = max(sets[i][2] for i in read)
        for p in quarter_ends(MIN_PERIOD, last_end):
            if p in closed:
                continue
            j = next((i for i, x in enumerate(sets) if x[2] > p), None)
            if j is not None:
                lo = min(lo, j)
            break                                  # the earliest open quarter decides
    return list(sets[lo:])


def quarter_ends(a, b):
    """Every quarter-end from a to b (ISO dates), inclusive."""
    out = []
    y, m = int(a[:4]), int(a[5:7])
    m = ((m - 1) // 3 + 1) * 3
    while True:
        d = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        if d > b:
            break
        if d >= a:
            out.append(d)
        m += 3
        if m > 12:
            m -= 12
            y += 1
    return out


def collect(root, minutes=40, ua=None, page_html=None, fetch=None, early=True, hub=None, sectors=()):
    """Read the data sets the plan gives, closing quarters as their late filings come in; the open quarters are written
    too (and read again on the next run). hub, sectors: where the managers' books find each CUSIP's sector
    (sector_map). Returns the run's summary."""
    root = Path(root)
    ua = ua or os.environ.get('SEC_USER_AGENT') or ''
    if fetch is None and ('@' not in ua or 'example.com' in ua):
        raise SystemExit('Set SEC_USER_AGENT to the project name and a real contact e-mail (SEC requires it)')
    fetch = fetch or (lambda url, dest=None: sec_get(url, ua, dest))
    state = json.loads((root / 'cache' / 'sets.json').read_text()) if (root / 'cache' / 'sets.json').exists() else {}
    if state and state.get('mversion') != MANAGERS_VERSION:
        # the managers' books are new (or laid out anew): every data set read again, each quarter closed again — the
        # holders' quarters come out the same
        print(f"managers' books (version {MANAGERS_VERSION}): reading every data set again", flush=True)
        state = dict(state, done=[], closed=[])
    sector_of, known = sector_map(root, hub, sectors)
    print(f"sectors for the managers' books: {known['cusips']:,} CUSIPs with a ticker, {known['tickers']:,} tickers with a sector", flush=True)
    if page_html is None:
        page_html = fetch(PAGE).decode('utf-8', 'replace')
    sets = listing(page_html)
    if early:
        sets = with_early(sets)
    if not sets:
        raise SystemExit('no 13F data sets listed on ' + PAGE)
    todo = plan(sets, state)
    t0, budget = time.monotonic(), minutes * 60
    book = Book(state.get('closed') or [], sector_of)
    done, closed = set(state.get('done') or []), set(state.get('closed') or [])
    failed = dict(state.get('failed') or {})
    read, last_start = [], None
    for url, start, end in todo:
        if read and time.monotonic() - t0 > budget:
            break
        name = url.rsplit('/', 1)[-1].lower()
        tmp = Path(tempfile.mkdtemp()) / name
        t1 = time.monotonic()
        try:
            fetch(url, tmp)
            book.read(tmp)
        except Missing:
            print(f'{name}: not published (passed over)', flush=True)
            done.add(name)
            continue
        except Exception as exc:
            failed[name] = failed.get(name, 0) + 1
            print(f'::warning::{name}: {str(exc)[:300]} (attempt {failed[name]})', flush=True)
            if failed[name] < 3:
                break                              # its quarters stay open; the next run tries again
            done.add(name)                         # three times: passed over
            continue
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
            try:
                tmp.parent.rmdir()
            except OSError:
                pass
        read.append(name)
        done.add(name)
        last_start = start
        print(f'{name}: {book.stats["filings"]:,} filings so far, {time.monotonic() - t1:.0f} s', flush=True)
        for p in quarter_ends(MIN_PERIOD, start):  # every quarter this set comes long enough after (filed for or not)
            if p in closed or not closes(p, start):
                continue
            if p in book.filings:
                write_gz(root / 'cache' / 'periods' / f'{p}.json.gz', book.close(p))
                write_gz(root / 'cache' / 'managers' / f'{p}.json.gz', book.last_books)
                print(f'  {p} closed ({len(book.last_books["rows"]):,} managers\' books)', flush=True)
            closed.add(p)
            book.closed.add(p)
    for p in sorted(book.filings):                 # still open: written now, read again from its sets next time
        doc = book.close(p)
        doc['open'] = True
        write_gz(root / 'cache' / 'periods' / f'{p}.json.gz', doc)
        book.last_books['open'] = True
        write_gz(root / 'cache' / 'managers' / f'{p}.json.gz', book.last_books)
    left = [u for u, _, _ in sets if u.rsplit('/', 1)[-1].lower() not in done]
    state = {'updated_at': now(), 'done': sorted(done), 'closed': sorted(closed), 'sets': len(sets), 'left': len(left), 'failed': failed,
             'last_read': read[-1] if read else state.get('last_read'), 'stats': dict(book.stats), 'mversion': MANAGERS_VERSION}
    (root / 'cache').mkdir(parents=True, exist_ok=True)
    (root / 'cache' / 'sets.json').write_text(json.dumps(state, indent=1))
    return {'read': read, 'left': len(left), 'closed': len(closed), 'last_start': last_start}


# ------------------------------------------------------------------ build: one file per ticker
def ticker_map(hub, periods):
    """CUSIP → ticker: the Hub's map, then FORMER, then an issuer's name met by exactly one SEC listing (a common share,
    not a preferred or a note), never a CUSIP whose quarters overlap another of the same ticker's."""
    hub = Path(hub)
    cmap = {}
    try:
        cmap = {c.upper(): t.upper().replace('/', '-').replace('.', '-') for c, t in json.loads((hub / 'market' / 'cusip-tickers.json').read_text()).items() if t}
    except (OSError, ValueError):
        pass
    titles = defaultdict(set)
    names = {}
    try:
        for r in json.loads((hub / 'cache' / 'prices' / 'sec-tickers.json').read_text()).get('rows') or []:
            t = str(r.get('ticker') or '').upper().replace('/', '-').replace('.', '-')
            if t:
                names.setdefault(t, r.get('title') or '')
                k = name_key(r.get('title'))
                if k and len(k) >= 3:
                    titles[k].add(t)
    except (OSError, ValueError):
        pass
    per_q, issuers, size = defaultdict(dict), defaultdict(Counter), Counter()
    for p, doc in periods:
        for cusip, row in doc['rows'].items():
            per_q[cusip][p] = row[0]
            size[cusip] = max(size[cusip], row[0])
            nm = doc['issuers'].get(cusip)
            if nm:
                issuers[cusip][tuple(nm)] += 1
    span = {}
    for cusip, q in per_q.items():                 # the quarters with a tenth of its most holders: its own life
        main = sorted(p for p, h in q.items() if h >= max(3, 0.1 * size[cusip])) or sorted(q)
        span[cusip] = (main[0], main[-1])
    out, how = {}, Counter()
    for cusip in span:
        t = cmap.get(cusip) or FORMER.get(cusip)
        if t:
            out[cusip] = t
            how['map' if cusip in cmap else 'by hand'] += 1
    taken = defaultdict(list)
    for c, t in out.items():
        taken[t].append(span[c])
    by8 = defaultdict(list)                        # titles by their first letters, for a name cut short in a filing
    for k, ts in titles.items():
        by8[k[:10]].append((k, ts))
    cand = defaultdict(list)                       # ticker → the CUSIPs whose issuer is named like its listing
    for cusip, (a, b) in span.items():
        if cusip in out or size[cusip] < 3 or not issuers[cusip] or not cusip_ok(cusip):
            continue
        (issuer, cls), _ = issuers[cusip].most_common(1)[0]
        if NOT_COMMON.search(cls or '') or NOT_COMMON.search(issuer or ''):
            continue
        ik = name_key(issuer)
        ts = set(titles.get(ik, ()))
        if not ts and len(ik) >= 10:               # 'SEAGATE TECHNOLOGY HLDNGS PL…': a listing whose name starts the same
            ts = {t for k, tt in by8.get(ik[:10], ()) if (ik.startswith(k) or k.startswith(ik)) and min(len(k), len(ik)) >= 10 for t in tt}
        ts = {t for t in ts if '-' not in t} or ts
        letter = class_letter(cls)
        if len(ts) > 1 and letter:
            ts = {t for t in ts if t.endswith('-' + letter)} or ts
        if len(ts) == 1:
            cand[next(iter(ts))].append(cusip)
    for t, cs in cand.items():
        # the most held first, each quarter to one CUSIP: a company's own CUSIP before the odd identifiers some filers
        # type for it; then only those linked, quarter after quarter, to the ticker's own (a chain of replaced CUSIPs,
        # not another company of the same name years apart)
        own = {class_letter(issuers[c].most_common(1)[0][0][1]) for c, tt in out.items() if tt == t and issuers.get(c)} - {''}
        got = []
        for c in sorted(cs, key=lambda c: -size[c]):
            a, b = span[c]
            # a quarter shared only where one CUSIP ends and the next begins (and goes on past it); never a CUSIP
            # inside another's years
            if any(len(quarter_ends(max(a, x0), min(b, x1))) > (1 if (a >= x1 and b > x1) or (b <= x0 and a < x0) else 0)
                   for x0, x1 in taken[t] + [span[g] for g in got]):
                continue
            letter = class_letter(issuers[c].most_common(1)[0][0][1])
            if letter and own and letter not in own:
                continue                           # another class of share (Dell's class V tracking stock is not class C)
            got.append(c)
        seeds = list(taken[t]) or [span[max(got, key=lambda c: size[c])]] if got else list(taken[t])
        linked, grew = [], True
        while grew:
            grew = False
            for c in got:
                if c not in linked and any(gap(span[c], x) <= 4 for x in seeds):
                    linked.append(c)
                    seeds.append(span[c])
                    grew = True
        for c in linked:
            out[c] = t
            taken[t].append(span[c])
            how['by name'] += 1
    return out, names, issuers, dict(how)


def gap(u, v):
    """Quarter-ends from the end of one span to the start of the other (2: back to back; 0: they overlap)."""
    (a, b), (x0, x1) = u, v
    return len(quarter_ends(b, x0)) if b < x0 else len(quarter_ends(x1, a)) if x1 < a else 0


def tidy(row):
    """A ticker's quarter made consistent: [holders, shares, usd, {holder: [shares, usd]}] with each holder's shares and
    value put at the quarter's price (the median value per share among its largest holders) where a filing's two figures
    disagree more than five times (shares typed wrong, a value in thousands): the smaller of the two is kept, so a
    mistyped filing never makes a giant; and the totals: the lower of the value filed and the shares at that price."""
    px = sorted(v / s for s, v in row[3].values() if s > 0 and v > 0)
    if len(px) < 3:
        return row
    p = px[len(px) // 2]
    for k, (s, v) in list(row[3].items()):
        if s > 0 and v > 0 and not 0.2 <= v / (s * p) <= 5:
            size = min(v, s * p)
            row[3][k] = [size / p, size]
    if row[1] > 0 and row[2] > 0 and not 0.99 <= row[2] / (row[1] * p) <= 1.01:   # all holders together: the lower of
        usd = min(row[2], row[1] * p)                                               # the value filed and shares × price
        row[1], row[2] = usd / p, usd
    return row


def build_managers(root, pub, cmap, names, giant=None):
    """public/m/<CIK>.json for every manager of more than `giant` positions in some quarter: its books quarter by
    quarter — the long equity book in dollars, its lines, puts and calls, its book by sector, its largest positions by
    ticker (a company's share classes together; a CUSIP no ticker names, by its issuer: '~' and the CUSIP's first six
    characters) as weights of the book in hundred-thousandths (unit), with the names; public/m/index.json lists them."""
    root, out_dir = Path(root), Path(pub) / 'm'
    giant = GIANT if giant is None else giant
    files = sorted((root / 'cache' / 'managers').glob('*.json.gz'))
    docs = [(f.name[:10], read_gz(f, {'rows': {}})) for f in files]
    docs = [(p, d) for p, d in docs if p >= MIN_PERIOD]
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob('*.json'):
        f.unlink()
    P = [p for p, _ in docs]
    per, filer, iss = defaultdict(dict), {}, {}
    opn = {p for p, d in docs if d.get('open')}
    for i, (p, d) in enumerate(docs):
        for cik, row in (d.get('rows') or {}).items():
            per[cik][i] = row
            nm = (d.get('names') or {}).get(cik)
            if nm:
                filer[cik] = nm
        iss.update(d.get('issuers') or {})
    index = []
    for cik, rows in per.items():
        if max(r[1] for r in rows.values()) <= giant:
            continue
        first, last = min(rows), max(rows)
        usd, lines, opts, secs, tops, labels = [], [], [], [], [], {}
        for i in range(first, last + 1):
            r = rows.get(i)
            if not r:
                for a in (usd, lines, opts, secs):
                    a.append(None)
                tops.append([])
                continue
            u, n, put, call, top, sectors = r
            usd.append(u)
            lines.append(n)
            opts.append([put, call])
            secs.append(sectors)
            agg = {}
            for cusip, sh, v in top:
                t = cmap.get(cusip) or FORMER.get(cusip)
                if t in CLASSES:
                    t = CLASSES[t][0]
                key = t or '~' + cusip[:6]
                if key not in labels:
                    labels[key] = names.get(t) or t if t else pretty((iss.get(cusip) or [cusip])[0])[0]
                agg[key] = agg.get(key, 0) + v
            # each as its weight in the book, in hundred-thousandths (the file stays small: ~14 bytes a position)
            row = [[k, int(round(v / u / WUNIT))] for k, v in sorted(agg.items(), key=lambda kv: -kv[1]) if u > 0]
            tops.append([x for x in row if x[1] > 0])
        name = pretty(filer.get(cik) or '', int(cik))[0] or cik
        doc = {'cik': int(cik), 'name': name, 'filer': filer.get(cik) or '', 'source': 'SEC Form 13F data sets',
               'periods': P[first:last + 1], 'open': [P[i] for i in range(first, last + 1) if P[i] in opn],
               'fields': {'top': ['key', 'weight'], 'options': ['put', 'call']}, 'unit': WUNIT,
               'usd': usd, 'lines': lines, 'options': opts, 'sectors': secs, 'top': tops, 'names': labels}
        (out_dir / f'{int(cik)}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        index.append([int(cik), name, P[first], P[last], next((x for x in reversed(lines) if x is not None), None),
                      next((x for x in reversed(usd) if x is not None), None)])
    index.sort(key=lambda r: -(r[5] or 0))
    (out_dir / 'index.json').write_text(json.dumps({'generated_at': now(), 'periods': P, 'fields': ['cik', 'name', 'first', 'last', 'lines', 'usd'],
                                                    'rows': index}, separators=(',', ':')), encoding='utf-8')
    return {'managers': len(index), 'quarters': len(P), 'first': P[0] if P else None, 'last': P[-1] if P else None}


def build(root, hub, top=TOP, min_usd=20_000_000):
    root, pub = Path(root), Path(root) / 'public'
    files = sorted((root / 'cache' / 'periods').glob('*.json.gz'))
    periods = [(f.name[:10], read_gz(f, {'rows': {}, 'issuers': {}, 'names': {}, 'filers': 0})) for f in files]
    periods = [(p, d) for p, d in periods if p >= MIN_PERIOD]
    if not periods:
        raise SystemExit('no quarters read yet')
    P = [p for p, _ in periods]
    cmap, names, issuers, how = ticker_map(hub, periods)
    who_name = {}
    for p, doc in periods:                          # the latest name each filer reported under
        for hk, nm in (doc.get('names') or {}).items():
            if nm:
                who_name[hk] = nm
    per = defaultdict(dict)                          # ticker → period index → [holders, shares, usd, {holder: [shares, usd]}]
    cus, cls = defaultdict(set), defaultdict(set)
    for i, (p, doc) in enumerate(periods):
        for cusip, (holders, shares, usd, tops) in doc['rows'].items():
            t = cmap.get(cusip)
            if not t:
                continue
            ratio, own = 1, t
            if t in CLASSES:
                t, ratio = CLASSES[t]
            cus[t].add(cusip)
            cls[t].add(own)
            a = per[t].get(i)
            if a is None:
                a = per[t][i] = [0, 0, 0, {}]
            a[0] += holders
            a[1] += shares * ratio
            a[2] += usd
            for hk, sh, va in tops:
                if hk.startswith('c') and int(hk[1:]) in FAMILY_OF:
                    hk = 'f:' + FAMILY_OF[int(hk[1:])]
                b = a[3].get(hk)
                if b:
                    b[0] += sh * ratio
                    b[1] += va
                else:
                    a[3][hk] = [sh * ratio, va]
    out_dir = pub / 'c'
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob('*.json'):
        f.unlink()
    index, stamp = [], now()
    for t, rows in per.items():
        if max(r[2] for r in rows.values()) < min_usd or max(r[0] for r in rows.values()) < 3:
            continue
        for r in rows.values():
            tidy(r)
        # the first and last quarters a handful of filers still (or already) report a CUSIP in: not the ticker's history
        hmax = max(r[0] for r in rows.values())
        real = [i for i, r in rows.items() if r[0] >= (0.05 * hmax if hmax >= 60 else 1)]
        rows = {i: r for i, r in rows.items() if min(real) <= i <= max(real)}
        who, widx = [], {}
        tops, total = [], []
        for i in range(len(P)):
            r = rows.get(i)
            if not r:
                total.append(None)
                tops.append([])
                continue
            total.append([r[0], int(round(r[1])), int(round(r[2]))])
            best = sorted(r[3].items(), key=lambda x: -x[1][0])[:top]
            row = []
            for hk, (sh, va) in best:
                if hk not in widx:
                    widx[hk] = len(who)
                    if hk.startswith('f:'):
                        fam = FAMILIES[hk[2:]]
                        who.append([hk, fam[0], fam[1], fam[2]])
                    else:
                        cik = int(hk[1:])
                        nm, short = pretty(who_name.get(hk) or '', cik)
                        who.append([hk, nm, short, [cik]])
                row.append([widx[hk], int(round(sh)), int(va)])
            tops.append(row)
        first = next(i for i, x in enumerate(total) if x)
        last = max(i for i, x in enumerate(total) if x)
        iss = Counter()
        for c in cus[t]:
            iss.update(issuers.get(c) or {})
        name = names.get(t) or (pretty(iss.most_common(1)[0][0][0])[0] if iss else t)
        doc = {'ticker': t, 'name': name, 'source': 'SEC Form 13F data sets',
               'cusips': sorted(cus[t]), 'classes': sorted(cls[t]),
               'periods': P[first:last + 1], 'filers': [periods[i][1].get('filers', 0) for i in range(first, last + 1)],
               'open': [P[i] for i in range(first, last + 1) if periods[i][1].get('open')],
               'fields': {'total': ['holders', 'shares', 'usd'], 'top': ['who', 'shares', 'usd']},
               'total': total[first:last + 1], 'who': who, 'top': tops[first:last + 1]}
        safe = re.sub(r'[^A-Z0-9-]', '_', t)
        (out_dir / f'{safe}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        lt = total[last]
        index.append([t, name, P[first], P[last], lt[0], lt[2]])
    index.sort(key=lambda r: -(r[5] or 0))
    (pub / 'index.json').write_text(json.dumps({'generated_at': stamp, 'periods': P, 'fields': ['ticker', 'name', 'first', 'last', 'holders', 'usd'],
                                                'rows': index}, separators=(',', ':')), encoding='utf-8')
    # CUSIP → ticker as named here (the managers' books and the 13F weights video read it: web/actual-weights.js)
    (pub / 'cusips.json').write_text(json.dumps({'generated_at': stamp, 'cusips': dict(sorted(cmap.items()))}, separators=(',', ':')), encoding='utf-8')
    managers = build_managers(root, pub, cmap, names)
    state = json.loads((root / 'cache' / 'sets.json').read_text()) if (root / 'cache' / 'sets.json').exists() else {}
    status = {'built_at': stamp, 'tickers': len(index), 'quarters': len(P), 'first': P[0], 'last': P[-1], 'managers': managers,
              'open': [p for p, d in periods if d.get('open')], 'cusips_named': how, 'sets_read': len(state.get('done') or []),
              'sets_left': state.get('left'), 'families': {k: v[0] for k, v in FAMILIES.items()}}
    (pub / 'status.json').write_text(json.dumps(status, indent=1), encoding='utf-8')
    return status


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--hub', help="the Hub's data folder (market/cusip-tickers.json): CUSIP → ticker for the managers' books")
    c.add_argument('--sectors', nargs='*', default=[], help='ticker → sector files (rank meta, ETF sectors, the site index)')
    b = sp.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--hub', required=True)
    a = ap.parse_args()
    if a.cmd == 'collect':
        r = collect(a.root, a.minutes, hub=a.hub, sectors=a.sectors)
        print(json.dumps(r))
        gh = os.environ.get('GITHUB_OUTPUT')
        if gh:
            with open(gh, 'a') as f:
                f.write(f"left={r['left']}\nread={len(r['read'])}\n")
    else:
        print(json.dumps(build(a.root, a.hub)))


if __name__ == '__main__':
    main()
