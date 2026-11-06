"""Insiders who hold a stock, quarter by quarter, for the holders video ("Who owns Tesla": Elon Musk beside Vanguard):
every officer's, director's and 10% owner's shares at each quarter-end since 2013 Q2, from their own Forms 3, 4 and 5
— the holders 13F leaves out (13F lists managers of $100M or more, not people).

  source    SEC's Insider Transactions Data Sets (DERA): every Form 3, 4 and 5 filed in a calendar quarter since 2006, one
            zip a quarter (2025q3_form345.zip, at the address the page links). SUBMISSION (the issuer's CIK, the form,
            the dates), REPORTINGOWNER (CIK, name, relationship, title) and the lines: NONDERIV_TRANS (each trade and the
            shares owned after it), NONDERIV_HOLDING (shares held, no trade), DERIV_TRANS and DERIV_HOLDING when the
            security is itself a class of common stock (Class B of Meta or Alphabet, convertible one for one). Options,
            units, warrants, notes and preferred stock are left out.
  reading   per issuer, owner and holding — direct, or each indirect one ("By Trust", "By Seven Hills Trust", a
            footnote's words when the line only says "See footnote") — the shares owned after its latest report, by the
            date reported for (a trade's date, a holding's period of report); a later filing first on the same day,
            the last line first in one filing. A joint filing is its first owner's. Kept per data set: each holding's
            last report in each calendar quarter.
  quarters  at each quarter-end: each holding's latest report on or before it, if within KEEP_DAYS — an insider who
            left stops reporting, and a trust wound up is not always reported at zero; a large holding (BIG of the stock's
            13F shares or more) within KEEP_BIG_DAYS; a founder's — a person who is a director or officer and a 10% owner,
            CONTROL of the stock or more — for as long as no report changes them (such an insider must report every
            change: Larry Page, who has not traded since 2021), each holding reported with their latest within two years
            of it (an old holding the founder no longer reports is not kept for ever)
  13F       counted once: an owner who files 13F (Berkshire in Occidental's Forms 4) and an indirect holding of the same
            shares as one of the stock's 13F holders that quarter, to 0.2% (Berkshire's shares in Warren Buffett's own
            Form 4) are left out — a holding of one's own is not a manager's, whatever its number
  blocks    one block of shares several owners report — a family company held directly by itself and indirectly by each
            member (Walton Enterprises), a fund by its general partners — counts once: holdings of the same number of
            shares (BLOCK or more, within 0.1%), one of them at least indirect, go to the one held directly, else to the
            owner with the most; an owner whose largest holding is another company's ("by Daimler North America")
            says so (who: its "via")
  value     the shares at the quarter's 13F price (the stock's 13F value ÷ its 13F shares that quarter; Berkshire's
            class A as 1,500 class B, as the 13F side counts them)
  splits    a holding last reported before a stock split counts its shares as split since: a split is a quarter in
            which the stock's largest 13F holders all hold n times the shares (n = 2, 3, 5, 10, 20 …, or 1/n) and its
            13F price is about 1/n of the quarter before (Tesla's 5 for 1 of 2020, 3 for 1 of 2022); a report inside
            that quarter is before it when its trade price is nearer the price of the quarter before

  cache/insiders/sets.json        the data sets read
  cache/insiders/<set>.json.gz    per data set: owners, and per issuer, owner and holding its last report a quarter
  public/i/<TICKER>.json          per ticker with 13F holders (public/c): the insiders each quarter, the largest first

    python app/insiders_history.py collect --root hh --minutes 25
    python app/insiders_history.py build --root hh --hub disclosures/docs/data
"""
import argparse
import bisect
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holders_history as HH  # noqa: E402  (the SEC fetch, the gz files, the share classes, the first 13F quarter)

PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'
BASE = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/'
FIRST = (2010, 1)               # sets read from 2010: the reports up to three years before the first 13F quarter
KEEP_DAYS = 730                 # a holding not reported again for two years is no longer counted
KEEP_BIG_DAYS = 1096            # … three years for a holding of BIG of the stock or more
BIG = 0.005                     # half a percent of the stock's 13F shares
CONTROL = 0.05                  # a founder's holdings (a person, director or officer and 10% owner) of this much of the
                                # stock's 13F shares or more: kept until reported otherwise (Larry Page: no trade since 2021)
BLOCK = 50_000                  # the same shares reported by several owners: one block from this many shares
CAP = 4                         # a holding of more than four times the stock's 13F shares is a slip of the pen
PERSONAL = re.compile(r'trust|spouse|wife|husband|child|\bsons?\b|daughter|famil|\bira\b|401|grat|gift|estate|custod|foundation|'
                      r'minor|ugma|utma|revocable|living|partnership for|\bself\b|retirement|pension|profit sharing|esop|savings', re.I)
TOP = 10                        # insiders published per ticker and quarter
VERSION = 2                     # cache/insiders layout: a new one reads every data set again (2: holdings' words, groups)
MON = {m: i + 1 for i, m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
ENTITY = re.compile(r'\b(LLC|L\.?L\.?C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LP|L\.?P|LTD|LIMITED|PLC|AG|SA|NV|SE|GMBH|'
                    r'TRUST|FUND|FUNDS|PARTNERS|PARTNERSHIP|CAPITAL|HOLDINGS?|MANAGEMENT|ADVISORS?|ADVISERS?|GROUP|'
                    r'FOUNDATION|BANK|INVESTMENTS?|VENTURES?|ASSOCIATES|ENTERPRISES|TELEKOM|AB|ASA|SPA|BV|KG)\b\.?', re.I)


def set_quarter(name):
    """(year, quarter) of a data set's file name (2025q3_form345.zip), or None."""
    m = re.match(r'(\d{4})q([1-4])_form345\.zip$', name.rsplit('/', 1)[-1].lower())
    return (int(m.group(1)), int(m.group(2))) if m else None


def listing(page_html, base=PAGE, first=FIRST):
    """[(url, name)] of every data set the page links from `first` on, oldest first (recent ones live at another
    address than the old ones: the page's own links are followed)."""
    out = {}
    for href in re.findall(r'href="([^"]+_form345\.zip)"', page_html, re.I):
        url = urllib.parse.urljoin(base, href)
        name = url.rsplit('/', 1)[-1].lower()
        q = set_quarter(name)
        if q and q >= first:
            out[name] = (q, url, name)
    return [(u, n) for _, u, n in sorted(out.values())]


def ddate(s):
    """'28-AUG-2025' (or '2025-08-28') → '2025-08-28'; None when not a date."""
    s = str(s or '').strip()
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})$', s)
    if m and m.group(2).upper() in MON:
        try:
            return dt.date(int(m.group(3)), MON[m.group(2).upper()], int(m.group(1))).isoformat()
        except ValueError:
            return None
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    return s[:10] if m else None


def quarter_end(d):
    y, m = int(d[:4]), int(d[5:7])
    q = (m - 1) // 3 + 1
    return (dt.date(y + (q == 4), (3 * q) % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


_NOT = re.compile(r'option|warrant|\bright|restricted stock unit|\brsus?\b|performance|phantom|deferred|\bnotes?\b|debenture|'
                  r'preferred|\bpref\b|swap|forward|depositary|\bads\b|\badr|\bput\b|\bcall\b|\bcvr\b|contingent|profits? interest|'
                  r'\bltip|\bopu\b', re.I)


def common(title, deriv=False):
    """Is this line's security the company's common stock — or, in the derivative table, a class of common stock itself
    (Class B, convertible one for one)? Options, units, warrants, notes and preferred stock are not."""
    t = str(title or '').lower()
    if not t or _NOT.search(t):
        return False
    if re.search(r'\bunits?\b', t) and not re.search(r'common units?', t):
        return False
    if deriv:
        return bool(re.search(r'\bclass\s+[a-z]\b', t)) and bool(re.search(r'common|ordinary', t))
    return bool(re.search(r'common|ordinary|capital stock|\bshares\b|restricted stock|\bstock\b', t))


def class_of(title):
    m = re.search(r'\bclass\s+([a-z])\b', str(title or '').lower())
    return m.group(1).upper() if m else ''


def words_of(t):
    return re.sub(r'[^a-z]+', ' ', str(t or '').lower()).strip()[:90]


def raw_of(t):
    return re.sub(r'\s+', ' ', str(t or '')).strip()[:120]


def nature(direct, text, fns, footnotes, rank=None):
    """(key, words) of a holding: ('D', ''), or ('I:' and its words, its words) — "by trust"; a line that only points at
    a footnote is 'I:fn#n', the n-th footnoted holding of its filing (a filer rewords and renumbers its footnotes from one
    report to the next, but keeps its holdings in the same order), with the footnote's words to name it. rank: the
    filing's {footnote ids: n}, filled as lines come."""
    if str(direct or '').strip().upper().startswith('D'):
        return 'D', ''
    t = str(text or '').lower()
    ids = tuple(sorted(f.strip() for f in str(fns or '').split(',') if f.strip()))
    if ids and (not re.sub(r'[^a-z]', '', t) or re.search(r'see\s+(foot)?notes?|footnote|explanation|remarks', t)):
        raw = raw_of(' '.join(footnotes.get(f, '') for f in ids))
        if rank is not None:
            n = rank.setdefault(ids, len(rank) + 1)
            return f'I:fn#{n}', raw
        w = words_of(raw)
        return ('I:' + w if w else 'I'), raw
    w = words_of(t)
    return ('I:' + w if w else 'I'), raw_of(text)


def read_set(path):
    """One data set → {'owners': {cik: [name, relationship, title]}, 'points': {issuer: {owner: {key: [[date, filed,
    shares]]}}}} — each holding's last report in each calendar quarter of the dates reported for."""
    z = zipfile.ZipFile(path)
    m = HH._members(z)
    sub = {}
    rows = HH._rows(z, m['SUBMISSION'])
    ix = {h: i for i, h in enumerate(next(rows))}
    for r in rows:
        try:
            acc, iss = r[ix['ACCESSION_NUMBER']], int(r[ix['ISSUERCIK']] or 0)
        except (IndexError, ValueError):
            continue
        filed = ddate(r[ix['FILING_DATE']])
        if iss and filed:
            sub[acc] = (iss, filed, ddate(r[ix['PERIOD_OF_REPORT']]) or filed)
    first, owners, joint = {}, {}, defaultdict(list)
    rows = HH._rows(z, m['REPORTINGOWNER'])
    ix = {h: i for i, h in enumerate(next(rows))}
    for r in rows:
        try:
            acc, cik = r[ix['ACCESSION_NUMBER']], int(r[ix['RPTOWNERCIK']] or 0)
        except (IndexError, ValueError):
            continue
        if acc not in sub or not cik:
            continue
        first.setdefault(acc, cik)
        if cik not in joint[acc]:
            joint[acc].append(cik)
        cell = lambda h: r[ix[h]].strip() if h in ix and len(r) > ix[h] else ''
        owners[str(cik)] = [cell('RPTOWNERNAME'), cell('RPTOWNER_RELATIONSHIP'), cell('RPTOWNER_TITLE')]
    footnotes = defaultdict(dict)
    if 'FOOTNOTES' in m:
        rows = HH._rows(z, m['FOOTNOTES'])
        ix = {h: i for i, h in enumerate(next(rows))}
        for r in rows:
            if len(r) > ix['FOOTNOTE_TXT'] and r[ix['ACCESSION_NUMBER']] in sub:
                footnotes[r[ix['ACCESSION_NUMBER']]][r[ix['FOOTNOTE_ID']].strip()] = r[ix['FOOTNOTE_TXT']][:400]
    best, prices, ranks = {}, defaultdict(list), defaultdict(dict)
    for table, deriv, dated in (('NONDERIV_TRANS', False, True), ('NONDERIV_HOLDING', False, False),
                                ('DERIV_TRANS', True, True), ('DERIV_HOLDING', True, False)):
        if table not in m:
            continue
        rows = HH._rows(z, m[table])
        ix = {h: i for i, h in enumerate(next(rows))}
        sk = next((h for h in ix if h.endswith('_SK')), None)
        need = max(ix['SHRS_OWND_FOLWNG_TRANS'], ix['DIRECT_INDIRECT_OWNERSHIP'], ix['SECURITY_TITLE'])
        for r in rows:
            if len(r) <= need:
                continue
            acc = r[ix['ACCESSION_NUMBER']]
            s = sub.get(acc)
            if not s or acc not in first or not common(r[ix['SECURITY_TITLE']], deriv):
                continue
            sh = HH._num(r[ix['SHRS_OWND_FOLWNG_TRANS']])
            if not sh == sh or sh < 0:
                continue
            iss, filed, period = s
            d = (ddate(r[ix['TRANS_DATE']]) if dated and 'TRANS_DATE' in ix else None) or period
            fn = r[ix['NATURE_OF_OWNERSHIP_FN']] if 'NATURE_OF_OWNERSHIP_FN' in ix and len(r) > ix['NATURE_OF_OWNERSHIP_FN'] else ''
            cls = class_of(r[ix['SECURITY_TITLE']])
            nk, words = nature(r[ix['DIRECT_INDIRECT_OWNERSHIP']], r[ix['NATURE_OF_OWNERSHIP']] if 'NATURE_OF_OWNERSHIP' in ix else '',
                               fn, footnotes.get(acc, {}), ranks[(acc, cls)])
            key = cls + '|' + nk
            if table == 'NONDERIV_TRANS' and r[ix['TRANS_CODE']].strip().upper() in ('P', 'S'):
                px = HH._num(r[ix['TRANS_PRICEPERSHARE']])
                if px == px and px > 0:
                    prices[acc].append(px)              # a trade in the market: the filing's price (splits)
            order = (d, filed, int(r[ix[sk]]) if sk and r[ix[sk]].strip().isdigit() else 0)
            k = (iss, first[acc], key, quarter_end(d))
            b = best.get(k)
            if b is None or order > b[0]:
                best[k] = (order, sh, acc, words)
    price_of = {a: sorted(v)[len(v) // 2] for a, v in prices.items()}
    points = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for (iss, own, key, _), ((d, filed, _), sh, acc, words) in best.items():
        points[str(iss)][str(own)][key].append([d, filed, int(round(sh)), round(price_of.get(acc, 0), 4), words])
    used = {o for per in points.values() for o in per}
    # joint filings: owners who report together (a fund, its general partner and managing members; a family company
    # and its members) — one group in the build, its blocks counted once
    groups = defaultdict(set)
    for acc, cs in joint.items():
        if len(cs) > 1 and acc in sub:
            groups[str(sub[acc][0])].add(tuple(sorted(cs)))
    return {'version': VERSION, 'owners': {o: v for o, v in owners.items() if o in used}, 'points': points,
            'groups': {i: sorted(list(g) for g in gs) for i, gs in groups.items()}}


def collect(root, minutes=25, ua=None, page_html=None, fetch=None):
    """Read the data sets not read yet, oldest first, within the minutes given. Returns the run's summary."""
    root = Path(root)
    ua = ua or os.environ.get('SEC_USER_AGENT') or ''
    if fetch is None and ('@' not in ua or 'example.com' in ua):
        raise SystemExit('Set SEC_USER_AGENT to the project name and a real contact e-mail (SEC requires it)')
    fetch = fetch or (lambda url, dest=None: HH.sec_get(url, ua, dest))
    cdir = root / 'cache' / 'insiders'
    cdir.mkdir(parents=True, exist_ok=True)
    sp = cdir / 'sets.json'
    state = json.loads(sp.read_text()) if sp.exists() else {}
    if state and state.get('version') != VERSION:
        print(f'insider data sets (layout {VERSION}): reading every set again', flush=True)
        state = dict(state, done=[])
    if page_html is None:
        page_html = fetch(PAGE).decode('utf-8', 'replace')
    sets = listing(page_html)
    if not sets:
        raise SystemExit('no Form 3/4/5 data sets listed on ' + PAGE)
    done, failed = set(state.get('done') or []), dict(state.get('failed') or {})
    # the newest set is read again each run: SEC may publish it before the quarter's last filings are in
    newest = sets[-1][1]
    done.discard(newest)
    t0, read = time.monotonic(), []
    for url, name in sets:
        if name in done:
            continue
        if read and time.monotonic() - t0 > minutes * 60:
            break
        tmp = Path(tempfile.mkdtemp()) / name
        t1 = time.monotonic()
        try:
            fetch(url, tmp)
            doc = read_set(tmp)
        except HH.Missing:
            print(f'{name}: not published (passed over)', flush=True)
            done.add(name)
            continue
        except Exception as exc:
            failed[name] = failed.get(name, 0) + 1
            print(f'::warning::{name}: {str(exc)[:300]} (attempt {failed[name]})', flush=True)
            if failed[name] >= 3:
                done.add(name)
            continue
        finally:
            try:
                tmp.unlink()
                tmp.parent.rmdir()
            except OSError:
                pass
        HH.write_gz(cdir / (name.replace('.zip', '') + '.json.gz'), doc)
        n = sum(len(k) for per in doc['points'].values() for k in per.values())
        print(f'{name}: {len(doc["points"]):,} issuers, {len(doc["owners"]):,} owners, {n:,} holdings, {time.monotonic() - t1:.0f} s', flush=True)
        read.append(name)
        done.add(name)
    state = {'updated_at': HH.now(), 'done': sorted(done), 'sets': len(sets), 'left': len([n for _, n in sets if n not in done]),
             'failed': failed, 'last_read': read[-1] if read else state.get('last_read'), 'version': VERSION}
    sp.write_text(json.dumps(state, indent=1))
    return {'read': read, 'left': state['left']}


# ------------------------------------------------------------------ build: one file per ticker

def person(name):
    """'Musk Elon' → 'Elon Musk', 'MURDOCH JAMES R' → 'James R Murdoch'; a company's name in title case."""
    n = re.sub(r'\s+', ' ', str(name or '')).strip()
    if not n:
        return n
    small = {'INC': 'Inc', 'THE': 'The', 'AND': 'and', 'OF': 'of', 'CO': 'Co', 'FOR': 'for'}
    def tc(s, entity=False):                       # all capitals (or all small letters) to title case; mixed case kept
        if not (s.isupper() or s.islower()):
            return s
        return ' '.join(small.get(w, w) if entity and len(w) <= 3 else w if entity and '.' in w.rstrip(',.') else w[:1].upper() + w[1:].lower()
                        for w in s.upper().split(' '))
    if ENTITY.search(n):
        return tc(n, True)
    parts = n.replace(',', ' ').split()
    suffix = [p for p in parts[1:] if p.rstrip('.').upper() in ('JR', 'SR', 'II', 'III', 'IV')]
    parts = [p for p in parts if p not in suffix]
    if len(parts) >= 2:
        parts = parts[1:] + parts[:1]
    return tc(' '.join(parts + suffix))


def role(rel, title):
    """'Director,Officer,TenPercentOwner', 'CEO' → 'CEO · director · 10% owner'."""
    r = str(rel or '')
    out = []
    t = str(title or '').strip()
    if 'Officer' in r:
        out.append(t if t else 'officer')
    if 'Director' in r:
        out.append('director')
    if 'TenPercent' in r:
        out.append('10% owner')
    if not out and 'Other' in r:
        out.append(t or 'other insider')
    return ' · '.join(out)


def safe(t):
    return re.sub(r'[^A-Z0-9-]', '_', t)


def holdings_at(lines, q, keep_days, big=None, keep_big=KEEP_BIG_DAYS, control=None):
    """{key: (shares, date, price, words)} of one owner's holdings on quarter-end q: each one's latest report on or
    before q, if within keep_days — within keep_big when it is `big` shares or more (price: the report's trade price, 0
    when it has none; words: what holds it, for an indirect one). lines: {key: (dates, rows)} sorted by (date, filed)."""
    qd = dt.date.fromisoformat(q)
    out = {}
    for key, (dates, rows) in lines.items():
        i = bisect.bisect_right(dates, q) - 1
        if i < 0:
            continue
        x = rows[i]
        d, sh, px, w = x[0], x[2], (x[3] if len(x) > 3 else 0), (x[4] if len(x) > 4 else '')
        age = (qd - dt.date.fromisoformat(d)).days
        if sh > 0 and (age <= keep_days or (big and sh >= big and age <= keep_big) or (control and sh >= control)):
            out[key] = (sh, d, px or 0, w)
    return out


def via(words):
    """The company an indirect holding is held through, from its words ("by daimler north america corporation" →
    'Daimler North America Corporation'); '' for a personal vehicle (a trust, a spouse, an IRA) or words that name
    none ("continued from footnote …", a bare "LLC")."""
    t = raw_of(words)
    if not t or PERSONAL.search(t):
        return ''
    m = re.search(r'\b(?:by|through|via|in)\s+(.+)', t, re.I)
    t = m.group(1) if m else t
    t = re.split(r'\s+(?:of which|for which|which|whose|and the reporting|the reporting|as\s)|[;()]', t, flags=re.I)[0].strip()
    ws = t.split()
    core = [w for w in ws if re.sub(r'[^a-z]', '', w.lower()) not in ('llc', 'lp', 'l', 'p', 'inc', 'corp', 'ltd', 'co', 'the', '')]
    if len([w for w in core if re.sub(r'[^a-z]', '', w.lower()) not in ('limited', 'liability', 'company', 'partnership',
                                                                         'corporation', 'trust', 'fund', 'entity', 'entities')]) < 1:
        return ''                                  # "By Limited Liability Company": no company named
    if len(core) < 2 or re.match(r'(continued|see|footnote|these|those|such|shares|the shares|represents|includes|consists|'
                                 r'reporting|securities|common|held|owned|directly|indirectly|a |an |each|all|amount|number|on|'
                                 r'this|explanation)\b', t, re.I):
        return ''
    out = ' '.join(ws[:7]).rstrip(',.;:')
    return person(out + ' LLC')[:-4] if out.isupper() or out.islower() else out     # capitals to title case, as a company's name


STEPS = (1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100)


def splits(doc):
    """{period index k: n} — the stock split n for 1 (or 1 for 1/n) between periods k-1 and k, from its 13F side: the
    largest holders held in both all hold about n times the shares (their median within 8% of n) and the 13F price
    moved by about 1/n (times a quarter's market move, between half and double)."""
    import math
    P, total, top = doc['periods'], doc['total'], doc['top']
    out = {}
    for k in range(1, len(P)):
        a, b = total[k - 1], total[k]
        if not a or not b or not a[1] or not b[1] or not a[2] or not b[2]:
            continue
        before = {w: sh for w, sh, _ in top[k - 1] if sh > 0}
        ratios = sorted(sh / before[w] for w, sh, _ in top[k] if sh > 0 and w in before)
        if len(ratios) < 3:
            continue
        med = ratios[len(ratios) // 2]
        if 0.6 < med < 1.4:
            continue
        cands = [n for n in STEPS] + [1 / n for n in STEPS]
        n = min(cands, key=lambda c: abs(math.log(med / c)))
        price = (b[2] / b[1]) / (a[2] / a[1])
        if abs(math.log(med / n)) <= math.log(1.08) and 0.5 <= price * n <= 2:
            out[k] = n
    return out


def split_factor(i, d, px, P, cuts, price13):
    """How many shares now for one reported on day d (at trade price px, 0 when none), at period i: the product of
    the splits since — those of a quarter wholly after the report, and that of the report's own quarter when the
    report came before it (its price nearer the quarter before; with no price, the first half of the quarter)."""
    import math
    f = 1.0
    for k, n in cuts.items():
        if k > i or d > P[k]:
            continue
        if d <= P[k - 1]:
            f *= n
            continue
        a, b = price13[k - 1], price13[k]
        if px and a and b:
            pre = abs(math.log(px / a)) < abs(math.log(px / b))
        else:
            mid = dt.date.fromisoformat(P[k - 1]) + (dt.date.fromisoformat(P[k]) - dt.date.fromisoformat(P[k - 1])) / 2
            pre = dt.date.fromisoformat(d) <= mid
        if pre:
            f *= n
    return f


def build(root, hub, keep_days=KEEP_DAYS, top=TOP):
    """public/i/<TICKER>.json for each ticker with 13F holders (public/c) whose issuer files Forms 3/4/5."""
    root, pub = Path(root), Path(root) / 'public'
    cdir = pub / 'c'
    have = {f.stem for f in cdir.glob('*.json')}
    tick = defaultdict(list)                        # issuer CIK → the tickers with a 13F history file
    try:
        rows = json.loads((Path(hub) / 'cache' / 'prices' / 'sec-tickers.json').read_text()).get('rows') or []
    except (OSError, ValueError):
        rows = []
    for r in rows:
        t = str(r.get('ticker') or '').upper().replace('/', '-').replace('.', '-')
        t = HH.CLASSES.get(t, (t, 1))[0]
        if t and safe(t) in have and r.get('cik') and t not in tick[int(r['cik'])]:
            tick[int(r['cik'])].append(t)
    owners, names = {}, defaultdict(Counter)       # the latest role; each name as written, a count a data set
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    joint = defaultdict(list)                      # issuer → the owners who filed together
    sets = sorted((root / 'cache' / 'insiders').glob('*_form345.json.gz'))
    for f in sets:
        d = HH.read_gz(f, {}) or {}
        for o, v in (d.get('owners') or {}).items():
            owners[o] = v
            if v and v[0]:
                names[o][v[0]] += 1
        for iss, gs in (d.get('groups') or {}).items():
            if int(iss) in tick:
                joint[iss].extend(gs)
        for iss, per in (d.get('points') or {}).items():
            if int(iss) not in tick:
                continue
            for o, keys in per.items():
                for k, lst in keys.items():
                    raw[iss][o][k].extend(lst)
    out_dir = pub / 'i'
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob('*.json'):
        f.unlink()
    made, stamp = 0, HH.now()
    name_of = lambda o: names[o].most_common(1)[0][0] if names[o] else ''
    for iss, per in raw.items():
        up = {}                                    # joint filers, one group each (union-find)
        def find(x):
            while up.get(x, x) != x:
                up[x] = up.get(up[x], up[x])
                x = up[x]
            return x
        for g in joint.get(iss, []):
            for c in g[1:]:
                a, b = find(str(g[0])), find(str(c))
                if a != b:
                    up[b] = a
        lines = {}
        for o, keys in per.items():
            lines[o] = {}
            for k, lst in keys.items():
                lst.sort(key=lambda x: (x[0], x[1]))
                lines[o][k] = ([x[0] for x in lst], lst)
        for t in tick[int(iss)]:
            doc = json.loads((cdir / f'{safe(t)}.json').read_text())
            P, total, top13, who13 = doc['periods'], doc['total'], doc['top'], doc['who']
            ciks13 = {int(c) for w in who13 for c in (w[3] or [])}
            ratio = {'A': HH.CLASSES['BRK-A'][1]} if t == 'BRK-B' else {}
            cuts = splits(doc)
            price13 = [(x[2] / x[1]) if x and x[1] else None for x in total]
            who, widx, tops, tot = [], {}, [], []
            for i, q in enumerate(P):
                if not total[i] or not total[i][1]:
                    tops.append([])
                    tot.append(None)
                    continue
                price = total[i][2] / total[i][1]
                blocks = [sh for _, sh, _ in top13[i] if sh > 0]
                same13 = lambda s: any(abs(s - h) <= 0.002 * h for h in blocks)
                big, cap, ctrl = BIG * total[i][1], CAP * total[i][1], CONTROL * total[i][1]
                held, words, ages = {}, {}, {}
                for o, ls in lines.items():
                    if int(o) in ciks13:
                        continue                   # a 13F filer itself: its shares are in its 13F
                    # each holding's latest report at any age, its shares as split since; then the ones still counted:
                    # within two years, five for a large one, and every one of a 10% owner whose holdings together are
                    # CONTROL of the stock or more (Larry Page's, unchanged since 2021, across a 20 for 1 split)
                    hs = holdings_at(ls, q, 10 ** 6)
                    adj = {k: (s * ratio.get(k.split('|', 1)[0], 1) * (split_factor(i, d, px, P, cuts, price13) if cuts else 1),
                               (dt.date.fromisoformat(q) - dt.date.fromisoformat(d)).days) for k, (s, d, px, _) in hs.items()}
                    rel = (owners.get(o) or ['', ''])[1]
                    ctl = ('TenPercent' in rel and ('Director' in rel or 'Officer' in rel) and not ENTITY.search(name_of(o))
                           and sum(v for v, _ in adj.values()) >= ctrl)
                    newest = min((age for _, age in adj.values()), default=0)
                    h = {k: v for k, (v, age) in adj.items()
                         if (ctl and age - newest <= keep_days) or age <= keep_days or (v >= big and age <= KEEP_BIG_DAYS)}
                    when = {k: adj[k][1] for k in h}
                    ind = lambda k: k.split('|', 1)[1].startswith('I')
                    h = {k: s for k, s in h.items() if s <= cap and not (ind(k) and same13(s))}   # a slip of the pen; 13F's own block
                    if h and not (all(ind(k) for k in h) and same13(sum(h.values()))):
                        held[o] = h
                        words[o] = {k: hs[k][3] for k in h}
                        ages[o] = when
                # joint filers: the one with the most counts in full, the others only an individual's own shares held
                # directly (a fund's general partner and managing members report the fund's shares, each of them)
                bygrp = defaultdict(list)
                for o in held:
                    bygrp[find(o)].append(o)
                for os_ in bygrp.values():
                    if len(os_) > 1:
                        keep = max(os_, key=lambda o: (sum(held[o].values()), o))
                        for o in os_:
                            if o != keep:
                                held[o] = {} if ENTITY.search(name_of(o)) else {k: s for k, s in held[o].items() if k.split('|', 1)[1] == 'D'}
                held = {o: h for o, h in held.items() if h}
                # one block several owners report (a family company by itself and by each member): the same shares,
                # one of them at least indirect — to the one who holds it directly, else to the owner with the most
                size = {o: sum(h.values()) for o, h in held.items()}
                ent = sorted((s, o, k) for o, h in held.items() for k, s in h.items() if s >= BLOCK)
                g = 0
                while g < len(ent):
                    e = g + 1
                    while e < len(ent) and ent[e][0] <= ent[g][0] * 1.001:
                        e += 1
                    grp = ent[g:e]
                    if len(grp) > 1 and any(k.split('|', 1)[1].startswith('I') for _, _, k in grp):
                        direct = [x for x in grp if x[2].split('|', 1)[1] == 'D']
                        keep = max(direct or grp, key=lambda x: (size[x[1]], x[1]))
                        for s_, o, k in grp:
                            if (o, k) == (keep[1], keep[2]):
                                continue
                            # another owner's report of it; or the same owner's under another wording in another
                            # report (Walton: "By Limited Liability Company", then no words at all) — not two holdings
                            # of the same size in one report (two trusts for two children)
                            if o != keep[1] or ages[o].get(k) != ages[o].get(keep[2]):
                                held[o].pop(k, None)
                    g = e
                held = {o: h for o, h in held.items() if h}
                sums = sorted(((sum(h.values()), o) for o, h in held.items() if h and sum(h.values()) > 0), reverse=True)
                row = []
                for sh, o in sums[:top]:
                    if o not in widx:
                        widx[o] = len(who)
                        _, rel, ttl = (owners.get(o) or ['', '', ''])[:3]
                        who.append([int(o), person(name_of(o)), role(rel, ttl), ''])
                    k_, s_ = max(held[o].items(), key=lambda x: x[1])
                    v_ = via(words[o].get(k_)) if k_.split('|', 1)[1].startswith('I') else ''
                    if s_ >= 0.5 * sh and v_:
                        who[widx[o]][3] = v_               # its largest holding another company's (the latest quarter's)
                    row.append([widx[o], int(round(sh)), int(round(sh * price))])
                tops.append(row)
                s_all = sum(s for s, _ in sums)
                tot.append([len(sums), int(round(s_all)), int(round(s_all * price))] if sums else None)
            if not any(tot):
                continue
            out = {'ticker': t, 'name': doc.get('name'), 'issuer': int(iss), 'source': 'SEC Forms 3, 4 and 5 (insider transactions data sets)',
                   'generated_at': stamp, 'periods': P, 'fields': {'total': ['owners', 'shares', 'usd'], 'top': ['who', 'shares', 'usd'], 'who': ['cik', 'name', 'role', 'via']},
                   'keep_days': keep_days, 'splits': {P[k]: n for k, n in sorted(cuts.items())}, 'total': tot, 'who': who, 'top': tops}
            (out_dir / f'{safe(t)}.json').write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
            made += 1
    sp = root / 'cache' / 'insiders' / 'sets.json'
    st = json.loads(sp.read_text()) if sp.exists() else {}
    status = {'built_at': stamp, 'tickers': made, 'sets_read': len(st.get('done') or []), 'sets_left': st.get('left')}
    (pub / 'insiders-status.json').write_text(json.dumps(status, indent=1), encoding='utf-8')
    return status


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--minutes', type=float, default=25)
    b = sp.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--hub', required=True)
    a = ap.parse_args()
    if a.cmd == 'collect':
        r = collect(a.root, a.minutes)
        print(json.dumps(r))
        gh = os.environ.get('GITHUB_OUTPUT')
        if gh:
            with open(gh, 'a') as f:
                f.write(f"left={r['left']}\n")
    else:
        print(json.dumps(build(a.root, a.hub)))


if __name__ == '__main__':
    main()
