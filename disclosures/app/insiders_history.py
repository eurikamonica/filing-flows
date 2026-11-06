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
            left stops reporting, and a trust wound up is not always reported at zero
  13F       counted once: an owner who files 13F (Berkshire in Occidental's Forms 4) and a holding of the same shares as
            one of the stock's 13F holders that quarter (Berkshire's shares in Warren Buffett's own Form 4) are left out;
            an indirect holding several owners report (a family company) counts once, for the owner with the most
  value     the shares at the quarter's 13F price (the stock's 13F value ÷ its 13F shares that quarter; Berkshire's
            class A as 1,500 class B, as the 13F side counts them)

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
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holders_history as HH  # noqa: E402  (the SEC fetch, the gz files, the share classes, the first 13F quarter)

PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'
BASE = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/'
FIRST = (2010, 1)               # sets read from 2010: the reports up to three years before the first 13F quarter
KEEP_DAYS = 730                 # a holding not reported again for two years is no longer counted
TOP = 10                        # insiders published per ticker and quarter
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


def nature(direct, text, fns, footnotes):
    """A holding's key: 'D', or 'I:' and its words ("by trust"); a line that only points at a footnote is keyed by the
    footnote's words, digits left out (the same trust, whatever its number of shares or its footnote's number)."""
    if str(direct or '').strip().upper().startswith('D'):
        return 'D'
    t = str(text or '').lower()
    if fns and (not re.sub(r'[^a-z]', '', t) or re.search(r'see\s+(foot)?notes?|footnote|explanation|remarks', t)):
        words = ' '.join(footnotes.get(f.strip(), '') for f in str(fns).split(',') if f.strip())
        if words.strip():
            t = words.lower()
    t = re.sub(r'[^a-z]+', ' ', t).strip()
    return 'I:' + t[:90] if t else 'I'


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
    first, owners = {}, {}
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
        cell = lambda h: r[ix[h]].strip() if h in ix and len(r) > ix[h] else ''
        owners[str(cik)] = [cell('RPTOWNERNAME'), cell('RPTOWNER_RELATIONSHIP'), cell('RPTOWNER_TITLE')]
    footnotes = defaultdict(dict)
    if 'FOOTNOTES' in m:
        rows = HH._rows(z, m['FOOTNOTES'])
        ix = {h: i for i, h in enumerate(next(rows))}
        for r in rows:
            if len(r) > ix['FOOTNOTE_TXT'] and r[ix['ACCESSION_NUMBER']] in sub:
                footnotes[r[ix['ACCESSION_NUMBER']]][r[ix['FOOTNOTE_ID']].strip()] = r[ix['FOOTNOTE_TXT']][:400]
    best = {}
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
            key = class_of(r[ix['SECURITY_TITLE']]) + '|' + nature(r[ix['DIRECT_INDIRECT_OWNERSHIP']], r[ix['NATURE_OF_OWNERSHIP']]
                                                                   if 'NATURE_OF_OWNERSHIP' in ix else '', fn, footnotes.get(acc, {}))
            order = (d, filed, int(r[ix[sk]]) if sk and r[ix[sk]].strip().isdigit() else 0)
            k = (iss, first[acc], key, quarter_end(d))
            b = best.get(k)
            if b is None or order > b[0]:
                best[k] = (order, sh)
    points = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for (iss, own, key, _), ((d, filed, _), sh) in best.items():
        points[str(iss)][str(own)][key].append([d, filed, int(round(sh))])
    used = {o for per in points.values() for o in per}
    return {'owners': {o: v for o, v in owners.items() if o in used}, 'points': points}


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
             'failed': failed, 'last_read': read[-1] if read else state.get('last_read')}
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
        return ' '.join(small.get(w, w) if entity and len(w) <= 3 else w[:1].upper() + w[1:].lower() for w in s.upper().split(' '))
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


def holdings_at(lines, q, keep_days):
    """{key: shares} of one owner's holdings on quarter-end q: each one's latest report on or before q, if within
    keep_days. lines: {key: (dates, rows)} sorted by (date, filed)."""
    qd = dt.date.fromisoformat(q)
    out = {}
    for key, (dates, rows) in lines.items():
        i = bisect.bisect_right(dates, q) - 1
        if i < 0:
            continue
        d, _, sh = rows[i]
        if sh > 0 and (qd - dt.date.fromisoformat(d)).days <= keep_days:
            out[key] = sh
    return out


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
    owners = {}
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    sets = sorted((root / 'cache' / 'insiders').glob('*_form345.json.gz'))
    for f in sets:
        d = HH.read_gz(f, {}) or {}
        owners.update(d.get('owners') or {})
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
    for iss, per in raw.items():
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
            who, widx, tops, tot = [], {}, [], []
            for i, q in enumerate(P):
                if not total[i] or not total[i][1]:
                    tops.append([])
                    tot.append(None)
                    continue
                price = total[i][2] / total[i][1]
                blocks = [sh for _, sh, _ in top13[i] if sh > 0]
                same13 = lambda s: any(abs(s - h) <= 0.01 * h for h in blocks)
                held = {}
                for o, ls in lines.items():
                    if int(o) in ciks13:
                        continue                   # a 13F filer itself: its shares are in its 13F
                    h = {k: s * ratio.get(k.split('|', 1)[0], 1) for k, s in holdings_at(ls, q, keep_days).items()}
                    h = {k: s for k, s in h.items() if not same13(s)}
                    if h and not same13(sum(h.values())):
                        held[o] = h
                # one indirect holding several owners report (a family company, a spouse's shares): the owner with the
                # most keeps it
                size = {o: sum(h.values()) for o, h in held.items()}
                byblock = defaultdict(list)
                for o, h in held.items():
                    for k, s in h.items():
                        if k.split('|', 1)[1].startswith('I'):
                            byblock[(k, round(s, -2))].append(o)
                for (k, _), os_ in byblock.items():
                    if len(os_) > 1:
                        keep = max(os_, key=lambda o: (size[o], o))
                        for o in os_:
                            if o != keep:
                                held[o].pop(k, None)
                sums = sorted(((sum(h.values()), o) for o, h in held.items() if h and sum(h.values()) > 0), reverse=True)
                row = []
                for sh, o in sums[:top]:
                    if o not in widx:
                        widx[o] = len(who)
                        nm, rel, ttl = (owners.get(o) or ['', '', ''])[:3]
                        who.append([int(o), person(nm), role(rel, ttl)])
                    row.append([widx[o], int(round(sh)), int(round(sh * price))])
                tops.append(row)
                s_all = sum(s for s, _ in sums)
                tot.append([len(sums), int(round(s_all)), int(round(s_all * price))] if sums else None)
            if not any(tot):
                continue
            out = {'ticker': t, 'name': doc.get('name'), 'issuer': int(iss), 'source': 'SEC Forms 3, 4 and 5 (insider transactions data sets)',
                   'generated_at': stamp, 'periods': P, 'fields': {'total': ['owners', 'shares', 'usd'], 'top': ['who', 'shares', 'usd'], 'who': ['cik', 'name', 'role']},
                   'keep_days': keep_days, 'total': tot, 'who': who, 'top': tops}
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
