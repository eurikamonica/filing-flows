"""Schedules 13D / 13G and Form 144 (4.6): who owns more than 5% of a company, and which insiders gave notice of a sale.

Schedule 13D   anyone who acquires more than 5% of a class of a listed company's voting shares with a view to influence
               it (an activist, a strategic buyer, a large founder) files within five business days; amendments (13D/A)
               report material changes, with "Item 4 — Purpose of transaction" saying what the filer intends.
Schedule 13G   the short form for passive holders: institutions (Rule 13d-1(b)), passive investors (13d-1(c)) and exempt
               holders (13d-1(d)); 13G/A amendments report changes and the drop below 5% (Item 5).
Form 144       an officer, director or other affiliate who intends to sell restricted or control shares files a notice by
               the time of the sale order: shares, market value, broker, approximate sale date and how the shares were
               acquired. A notice is an intention, not a trade; the trade itself follows on Form 4.

Since December 2024 (13D / 13G) and April 2023 (Form 144) these are structured XML on EDGAR. Each run reads EDGAR's
"current filings" feed for each form (newest first), then works back through the daily form indexes (`backfill_days`)
so the history fills in over a few runs; every accession is read once (the full submission .txt).

Cache:   cache/ownership/{stakes,form144}/<YYYY-MM>.json.gz (one file per filing month, so a run rewrites only the
         current months; rolling `keep_days`), seen.json (accessions read with nothing to keep), state.json (daily
         indexes read, backfill queue)
Publish: market/stakes.json and market/form144.json — the latest filings with tickers, the change from the same filer's
         previous filing on the company, per-ticker summaries; used by the hub tables (✦ X per row), the company pages
         (holders index) and the X posts (pipeline/engage.py kinds "stake" and "form144").
"""
from retry_queue import RetryQueue
import datetime as dt
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from core import Shards, localname, now, parse_xml, read_gz, read_json, text_of, write_json

FEED = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb=&owner=include'
        '&start={start}&count=100&output=atom')
DAILY = 'https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx'
FEEDS = {'stakes': ('SCHEDULE 13D', 'SCHEDULE 13G'), 'form144': ('144',)}
INDEX_FORMS = {'SCHEDULE 13D': 'stakes', 'SCHEDULE 13D/A': 'stakes', 'SCHEDULE 13G': 'stakes', 'SCHEDULE 13G/A': 'stakes',
               '144': 'form144', '144/A': 'form144'}
RULES = {'13d-1(b)': 'institution', '13d-1(c)': 'passive investor', '13d-1(d)': 'exempt holder'}
PERSON_TYPES = {'IA': 'investment adviser', 'IN': 'individual', 'PN': 'partnership', 'CO': 'corporation', 'OO': 'other entity',
                'HC': 'parent holding company', 'BD': 'broker-dealer', 'BK': 'bank', 'IC': 'insurance company',
                'IV': 'investment company', 'EP': 'employee benefit plan', 'FI': 'non-US institution', 'SA': 'savings association',
                'CP': 'church plan'}


BOILER = re.compile(r'(?is)^\s*(?:item\s*4\b[^:]{0,200}:\s*)?'
                    r'(?:the (?:information|responses?).{0,200}?incorporated (?:herein )?by reference[^.]{0,40}\.\s*)?')


def _num(v):
    try:
        return float(str(v).replace(',', '').replace('%', '').strip())
    except (TypeError, ValueError):
        return None


def _iso(mdy):
    """'10/14/2026' → '2026-10-14' (EDGAR's XML dates); '' when it is not a date."""
    m = re.fullmatch(r'\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*', mdy or '')
    if not m:
        m2 = re.fullmatch(r'\s*(\d{4})-(\d{2})-(\d{2})\s*', mdy or '')
        return '-'.join(m2.groups()) if m2 else ''
    try:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
    except ValueError:
        return ''


ENTITY = re.compile(r'(?i)\b(LLC|L\.L\.C|LP|L\.P|LLP|TRUST|TR|INC|CORP|CO|COMPANY|FUND|HOLDINGS?|PARTNERS|PARTNERSHIP|CAPITAL|MANAGEMENT|'
                    r'FOUNDATION|ESTATE|GROUP|LTD|LIMITED|BANK|ADVISORS?|INVESTMENTS?|VENTURES)\b|&')


def natural_name(name, conformed):
    """EDGAR's conformed names put an individual's last name first ("Nemati Marc A."); the reader's order is
    "Marc A. Nemati". Only names known to be conformed (they equal the filer's EDGAR name) are turned round."""
    w = (name or '').split()
    if not conformed or ENTITY.search(name or '') or not 2 <= len(w) <= 4:
        return name
    return ' '.join(w[1:] + w[:1])


def _clip(s, n):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n - 1].rsplit(' ', 1)[0] + '…'


# ------------------------------------------------------------------ the submission
def header(txt):
    """The SGML header of a submission .txt: form, filed date and the companies by role (SUBJECT COMPANY, FILED BY,
    REPORTING-OWNER, ISSUER …) → {'form', 'filed', 'roles': {role: [{'name', 'cik'}]}}."""
    head = txt[:txt.find('</SEC-HEADER>')] if '</SEC-HEADER>' in txt else txt[:20000]
    out = {'form': '', 'filed': '', 'roles': defaultdict(list)}
    m = re.search(r'CONFORMED SUBMISSION TYPE:\s*(.+)', head)
    out['form'] = m.group(1).strip() if m else ''
    m = re.search(r'FILED AS OF DATE:\s*(\d{4})(\d{2})(\d{2})', head)
    out['filed'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''
    role = None
    for line in head.splitlines():
        r = re.fullmatch(r'([A-Z][A-Z -]+):\s*', line)
        if r and not line.startswith('\t'):
            role = r.group(1).strip()
            continue
        if role:
            n = re.match(r'\s+COMPANY CONFORMED NAME:\s*(.+)', line)
            if n:
                out['roles'][role].append({'name': n.group(1).strip(), 'cik': ''})
            c = re.match(r'\s+CENTRAL INDEX KEY:\s*(\d+)', line)
            if c and out['roles'][role]:
                out['roles'][role][-1]['cik'] = c.group(1).lstrip('0')
    out['roles'] = dict(out['roles'])
    return out


def xml_from_submission(txt):
    m = re.search(r'<XML>\s*(.*?)\s*</XML>', txt, re.S | re.I)
    return m.group(1).encode('utf-8') if m else None


def _children(node, name):
    return [e for e in node.iter() if localname(e.tag) == name] if node is not None else []


def parse_stake(xml_bytes, accession, folder, head=None):
    """One Schedule 13D or 13G (or amendment) → a row. The cover pages give, per reporting person, the shares and the
    percent of the class; members of a group report overlapping holdings, so the filing's stake is the largest single
    one (not the sum)."""
    root = parse_xml(xml_bytes)
    if localname(root.tag) != 'edgarSubmission':
        return None
    sub = text_of(root, 'submissionType').upper()
    g = 'G' if '13G' in sub else 'D' if '13D' in sub else ''
    if not g:
        return None
    form = ('13G' if g == 'G' else '13D') + ('/A' if sub.endswith('/A') else '')
    persons = []
    blocks = _children(root, 'coverPageHeaderReportingPersonDetails' if g == 'G' else 'reportingPersonInfo')
    for b in blocks:
        if g == 'G':
            shares = _num(text_of(b, 'reportingPersonBeneficiallyOwnedAggregateNumberOfShares'))
            pct = _num(text_of(b, 'classPercent'))
        else:
            shares = _num(text_of(b, 'aggregateAmountOwned'))
            pct = _num(text_of(b, 'percentOfClass'))
        persons.append({'name': text_of(b, 'reportingPersonName'), 'cik': text_of(b, 'reportingPersonCIK').lstrip('0'),
                        'shares': shares, 'percent': pct, 'type': text_of(b, 'typeOfReportingPerson')})
    if not persons:
        return None
    top = max(persons, key=lambda p: ((p['percent'] or 0), (p['shares'] or 0)))
    cover = next(iter(_children(root, 'coverPageHeader')), root)
    issuer = next(iter(_children(cover, 'issuerInfo')), cover)
    head = head or {}
    roles = head.get('roles') or {}
    filed_by = (roles.get('FILED BY') or [{}])[0]
    subject = (roles.get('SUBJECT COMPANY') or [{}])[0]
    row = {'accession': accession, 'url': folder, 'form': form, 'filed': head.get('filed', ''),
           'amendment': int(_num(text_of(cover, 'amendmentNo')) or 0) if form.endswith('/A') else 0,
           'event_date': _iso(text_of(cover, 'dateOfEvent') or text_of(cover, 'eventDateRequiresFilingThisStatement')),
           'issuer_cik': (text_of(issuer, 'issuerCIK') or text_of(issuer, 'issuerCik') or subject.get('cik', '')).lstrip('0'),
           'issuer': text_of(issuer, 'issuerName') or subject.get('name', ''),
           'cusip': text_of(issuer, 'issuerCusipNumber'), 'class': _clip(text_of(cover, 'securitiesClassTitle'), 80),
           'filer': filed_by.get('name') or top['name'], 'filer_cik': filed_by.get('cik') or top['cik'],
           'person': top['name'], 'person_type': top['type'], 'persons': len(persons),
           'shares': top['shares'], 'percent': top['percent']}
    if g == 'G':
        rule = text_of(root, 'designateRulePursuantThisScheduleFiled')
        row['rule'] = next((v for k, v in RULES.items() if k in rule.replace(' ', '')), rule[:40])
        item5 = next(iter(_children(root, 'item5')), None)
        row['exit'] = text_of(item5, 'classOwnership5PercentOrLess') == 'Y' if item5 is not None else False
    else:
        row['purpose'] = _clip(BOILER.sub('', text_of(root, 'transactionPurpose').strip()), 600)
        row['funds'] = text_of(blocks[0], 'fundType') if blocks else ''
    return row


def parse_form144(xml_bytes, accession, folder, head=None):
    """One Form 144 notice → a row: who intends to sell, how many shares and their market value, when, through which
    broker, how the shares were acquired, and the 10b5-1 plan date when one is given."""
    root = parse_xml(xml_bytes)
    if localname(root.tag) != 'edgarSubmission':
        return None
    issuer = next(iter(_children(root, 'issuerInfo')), None)
    if issuer is None:
        return None
    info = _children(root, 'securitiesInformation')
    shares = sum(_num(text_of(s, 'noOfUnitsSold')) or 0 for s in info)
    value = sum(_num(text_of(s, 'aggregateMarketValue')) or 0 for s in info)
    dates = sorted(d for d in (_iso(text_of(s, 'approxSaleDate')) for s in info) if d)
    acquired = _children(root, 'securitiesToBeSold')
    sold = _children(root, 'securitiesSoldInPast3Months')
    plans = sorted(d for d in (_iso(''.join(e.itertext())) for e in _children(root, 'planAdoptionDate')) if d)
    rel = [''.join(e.itertext()).strip() for e in _children(issuer, 'relationshipToIssuer')]
    head = head or {}
    seller = text_of(issuer, 'nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold')
    owner = ((head.get('roles') or {}).get('REPORTING-OWNER') or [{}])[0].get('name', '')
    words = set(re.findall(r'[a-z]+', seller.lower()))
    natural = next((n for n in (text_of(s, 'name') for s in sold) if len(n.split()) >= 2 and set(re.findall(r'[a-z]+', n.lower())) <= words), '')
    return {'accession': accession, 'url': folder, 'form': (head.get('form') or text_of(root, 'submissionType') or '144').upper(),
            'filed': head.get('filed', ''), 'issuer_cik': text_of(issuer, 'issuerCik').lstrip('0'), 'issuer': text_of(issuer, 'issuerName'),
            'seller': seller, 'seller_name': natural or natural_name(seller, bool(owner) and owner.upper() == seller.upper()),
            'relationship': ', '.join(dict.fromkeys(r for r in rel if r)), 'class': _clip(text_of(info[0], 'securitiesClassTitle'), 60) if info else '',
            'shares': shares or None, 'value': round(value) if value else None,
            'outstanding': _num(text_of(info[0], 'noOfUnitsOutstanding')) if info else None,
            'sale_date': dates[0] if dates else '', 'exchange': text_of(info[0], 'securitiesExchangeName') if info else '',
            'broker': text_of(info[0], 'name') if info else '',
            'acquired': _clip(text_of(acquired[0], 'natureOfAcquisitionTransaction'), 60) if acquired else '',
            'plan_date': plans[-1] if plans else '',
            'sold_3m': round(sum(_num(text_of(s, 'grossProceeds')) or 0 for s in sold)) or None}


# ------------------------------------------------------------------ discovery
def feed_entries(client, form, pages=3):
    """[(accession, folder URL)] from the current-filings feed of one form type (its amendments included)."""
    out, seen = [], set()
    for page in range(pages):
        root = parse_xml(client.get(FEED.format(form=form.replace(' ', '+'), start=page * 100), sec=True))
        n = 0
        for entry in (e for e in root.iter() if localname(e.tag) == 'entry'):
            n += 1
            href = next((l.get('href') for l in entry.iter() if localname(l.tag) == 'link' and l.get('href')), '')
            m = re.search(r'/Archives/edgar/data/(\d+)/(\d{18})/(\d{10}-\d{2}-\d{6})-index\.html?', href)
            if m and m.group(3) not in seen:
                seen.add(m.group(3))
                out.append((m.group(3), f'https://www.sec.gov/Archives/edgar/data/{m.group(1)}/{m.group(2)}/'))
        if n < 100:
            break
    return out


def parse_daily_index(text):
    """EDGAR's daily form index → [(kind, accession, folder URL)] for the forms collected here (each filing is listed
    once per company on it — subject and filer — and kept once)."""
    out, seen = [], set()
    for line in text.splitlines():
        m = re.match(r'(SCHEDULE 13[DG](?:/A)?|144(?:/A)?)(?=\s)', line)
        f = re.search(r'edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt\s*$', line) if m else None
        if not f or f.group(2) in seen:
            continue
        seen.add(f.group(2))
        acc = f.group(2)
        out.append((INDEX_FORMS[m.group(1)], acc, f'https://www.sec.gov/Archives/edgar/data/{f.group(1)}/{acc.replace("-", "")}/'))
    return out


def business_days(today, days):
    d, out = today, []
    while (today - d).days <= days:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------ collect
def stores(cdir):
    """The two shard stores (one file per filing month); a single-file cache from the first version is split into them."""
    out = {k: Shards(Path(cdir) / k, date='filed', uid='accession', size=7) for k in FEEDS}
    for k, st in out.items():
        old = Path(cdir) / f'{k}.json.gz'
        if old.exists():
            for r in read_gz(old, []):
                st.add(r)
            st.save()
            old.unlink()
    return out


def _load(cdir, kind):
    return stores(cdir)[kind].all()


def collect(client, root, cfg=None, today=None):
    cfg = cfg or {}
    today = today or dt.date.today()
    cdir = Path(root) / 'cache' / 'ownership'
    cdir.mkdir(parents=True, exist_ok=True)
    shards = stores(cdir)
    empty = set(read_json(cdir / 'seen.json', []))           # read, but nothing to keep (not XML, not a 13D / 13G / 144)
    seen = empty | shards['stakes'].uids() | shards['form144'].uids()
    state = read_json(cdir / 'state.json', {})
    retry = RetryQueue(cdir)
    errors, read, found = 0, defaultdict(int), defaultdict(int)
    # 1. the newest filings of each form, from the current-filings feed
    todo = []
    for kind, forms in FEEDS.items():
        for form in forms:
            if not retry.due('feed:' + form):
                continue
            try:
                for acc, folder in feed_entries(client, form, int(cfg.get('feed_pages', 3))):
                    if acc not in seen:
                        todo.append((kind, acc, folder))
                retry.succeeded('feed:' + form)
            except Exception as exc:
                errors += 1
                retry.failed('feed:' + form, exc)
                print(f'{form} feed: {exc}', flush=True)
    # 2. back through the daily form indexes (newest day first), a few days per run, into a queue
    queue = [tuple(x) for x in state.get('queue', [])]
    done_days = set(state.get('index_days', []))
    left = int(cfg.get('index_days_per_run', 4))
    for d in business_days(today - dt.timedelta(days=1), int(cfg.get('backfill_days', 120))):
        if left <= 0:
            break
        ymd = d.strftime('%Y%m%d')
        if ymd in done_days or not retry.due('index:' + ymd):
            continue
        left -= 1
        try:
            text = client.get(DAILY.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=ymd), sec=True).decode('latin-1')
            queue.extend(x for x in parse_daily_index(text) if x[1] not in seen)
            done_days.add(ymd)
            retry.succeeded('index:' + ymd)
        except RuntimeError as exc:
            if 'HTTP 404' in str(exc):     # a holiday (no index), or not published yet
                if (today - d).days > 3:
                    done_days.add(ymd)
            else:
                retry.failed('index:' + ymd, exc)
                errors += 1
                print(f'daily index {ymd}: {exc}', flush=True)
    queue = [x for x in dict.fromkeys(todo + queue) if x[1] not in seen]
    batch = int(cfg.get('batch', 300))
    work = [x for x in queue if retry.due(x[1])][:batch]
    for kind, acc, folder in work:
        try:
            txt = client.get(folder + acc + '.txt', sec=True).decode('utf-8', 'replace')
            head = header(txt)
            form = head['form'].upper()
            kind = 'form144' if form.startswith('144') else 'stakes' if '13D' in form or '13G' in form else kind
            xml = xml_from_submission(txt)
            row = (parse_form144 if kind == 'form144' else parse_stake)(xml, acc, folder, head) if xml else None
            if row:
                shards[kind].add(row)
                found[kind] += 1
            else:
                empty.add(acc)
            seen.add(acc)
            read[kind] += 1
            retry.succeeded(acc)
        except Exception as exc:
            errors += 1
            retry.failed(acc, exc)
            print(f'{kind} {acc}: {exc}', flush=True)
            if errors > 25:
                break
    done = {a for _, a, _ in work if a in seen}
    queue = [x for x in queue if x[1] not in done]
    keep_days = {'stakes': 730, 'form144': 400, **(cfg.get('keep_days') or {})}
    for kind, st in shards.items():
        st.save(keep=(today - dt.timedelta(days=int(keep_days[kind]))).isoformat())
    window = {d.strftime('%Y%m%d') for d in business_days(today, int(cfg.get('backfill_days', 120)) + 10)}
    write_json(cdir / 'state.json', {'index_days': sorted(done_days & window), 'queue': [list(x) for x in queue], 'updated_at': now()})
    write_json(cdir / 'seen.json', sorted(empty))
    retry.save()
    return {'status': 'partial' if errors or retry.rows or queue else 'ok', **retry.summary(), 'read': dict(read), 'found': dict(found), 'waiting': len(queue),
            'latest_filing_date': max((r.get('filed', '') for st in shards.values() for r in st.all()), default=None), 'errors': errors, 'stakes': len(shards['stakes'].uids()), 'form144': len(shards['form144'].uids()),
            'index_days': len(done_days & window), 'updated_at': now()}


# ------------------------------------------------------------------ publish
def cik_tickers(root):
    """issuer CIK → its first ticker in SEC's company list (the list is ordered by size, so the main share class)."""
    out = {}
    for r in (read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
        if r.get('cik') and r.get('ticker'):
            out.setdefault(str(r['cik']).lstrip('0'), str(r['ticker']).upper())
    return out


def holder_of(r):
    """Who to name for a 13D / 13G: the largest reporting person, in reading order ("David James Donnalley", not EDGAR's
    conformed "Donnalley David James"), or the filer when the person's name is in EDGAR's upper case."""
    p, f = (r.get('person') or '').strip(), (r.get('filer') or '').strip()
    if p and r.get('person_type') == 'IN' and p.upper() == f.upper():
        return natural_name(p, True)
    return p if p and p != p.upper() else f or p


def with_changes(stakes, tickers):
    """Tickers, and each filing's change against the same filer's previous filing on the same company (oldest first)."""
    prev = {}
    out = []
    for r in sorted(stakes, key=lambda r: (r.get('filed') or '', r['accession'])):
        r = {**r, 'ticker': tickers.get(r.get('issuer_cik') or '', ''), 'holder': holder_of(r)}
        k = (r.get('filer_cik') or r.get('filer'), r.get('issuer_cik'))
        p = prev.get(k)
        if p:
            r['prev_percent'], r['prev_filed'] = p.get('percent'), p.get('filed')
            if r.get('percent') is not None and p.get('percent') is not None:
                r['change'] = round(r['percent'] - p['percent'], 2)
        r['new'] = not r['form'].endswith('/A')
        prev[k] = r
        out.append(r)
    return out[::-1]


def stake_label(r):
    """What a filing says, in a few words: 'new 13D', '13D/A: 9.8% → 12.1%', 'below 5% (13G/A)'."""
    if r.get('exit') or (r.get('form', '').endswith('/A') and r.get('percent') is not None and r['percent'] < 5):
        return 'below 5%'
    if r.get('new'):
        return 'new ' + r['form']
    if r.get('change'):
        return 'raised' if r['change'] > 0 else 'cut'
    return 'amended'


def stakes_summary(rows, today):
    d90 = (today - dt.timedelta(days=90)).isoformat()
    by = {}
    for r in rows:
        if not r.get('ticker') or (r.get('filed') or '') < d90:
            continue
        a = by.setdefault(r['ticker'], {'ticker': r['ticker'], 'issuer': r['issuer'], 'cik': r['issuer_cik'], 'filings': 0, 'd13': 0,
                                        'new13d': 0, 'filers': set(), 'max_percent': 0, 'last': ''})
        a['filings'] += 1
        a['d13'] += r['form'].startswith('13D')
        a['new13d'] += r['form'] == '13D'
        a['filers'].add(r.get('filer'))
        a['max_percent'] = max(a['max_percent'], r.get('percent') or 0)
        a['last'] = max(a['last'], r.get('filed') or '')
    return sorted(({**a, 'filers': sorted(f for f in a['filers'] if f)[:8]} for a in by.values()),
                  key=lambda a: (-a['new13d'], -a['d13'], -a['filings']))


def form144_summary(rows, today):
    d30 = (today - dt.timedelta(days=30)).isoformat()
    by = {}
    for r in rows:
        if not r.get('ticker') or (r.get('filed') or '') < d30:
            continue
        a = by.setdefault(r['ticker'], {'ticker': r['ticker'], 'issuer': r['issuer'], 'cik': r['issuer_cik'], 'notices': 0, 'value': 0,
                                        'sellers': set(), 'plan': 0, 'last': ''})
        a['notices'] += 1
        a['value'] += r.get('value') or 0
        a['sellers'].add(r.get('seller'))
        a['plan'] += bool(r.get('plan_date'))
        a['last'] = max(a['last'], r.get('filed') or '')
    return sorted(({**a, 'sellers': sorted(s for s in a['sellers'] if s)[:8]} for a in by.values()), key=lambda a: -a['value'])


def _short(r):
    return {**r, 'purpose': _clip(r['purpose'], 400)} if r.get('purpose') else r


def publish(root, out_dir, today=None):
    root, today = Path(root), today or dt.date.today()
    cdir = root / 'cache' / 'ownership'
    if not cdir.exists():
        return None
    shards = stores(cdir)
    tickers = cik_tickers(root)
    stakes = with_changes(shards['stakes'].all(), tickers)
    for r in stakes:
        r['label'] = stake_label(r)
    f144 = [{**r, 'ticker': tickers.get(r.get('issuer_cik') or '', '')} for r in shards['form144'].all()]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recent = (today - dt.timedelta(days=14)).isoformat()
    st = {'generated_at': now(), 'on_file': len(stakes), 'since': min((r['filed'] for r in stakes if r.get('filed')), default=None),
          'note': ('Schedules 13D and 13G as filed with the SEC. A 13D is filed by anyone above 5% of a class who may seek to '
                   'influence the company (Item 4 gives the purpose); a 13G by passive holders — institutions, passive '
                   'investors, exempt holders. The stake shown is the largest single reporting person’s (a group’s members '
                   'report overlapping holdings). “Change” compares with the same filer’s previous filing on file.'),
          'latest': [_short(r) for r in stakes if r.get('ticker') or (r.get('filed') or '') >= recent][:2000],
          'summary': stakes_summary(stakes, today)[:400]}
    _write(out_dir / 'stakes.json', st)
    big = [r for r in f144 if (r.get('value') or 0) >= 100_000]
    fm = {'generated_at': now(), 'on_file': len(f144), 'since': min((r['filed'] for r in f144 if r.get('filed')), default=None),
          'note': ('Form 144 notices of proposed sales of restricted or control shares by officers, directors and other '
                   'affiliates, as filed with the SEC (by the time of the sale order). A notice is an intention, not a trade: '
                   'the sale, if made, follows on Form 4. Values are the market value the filer gives. “10b5-1” shows the '
                   'date a pre-arranged trading plan was adopted, when one is named.'),
          'latest': [r for r in big if r.get('ticker') or (r.get('filed') or '') >= recent][:2500], 'small': len(f144) - len(big), 'summary': form144_summary(f144, today)[:400]}
    _write(out_dir / 'form144.json', fm)
    return {'stakes': len(st['latest']), 'form144': len(fm['latest'])}


def _write(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)
