"""8-K current reports (4.7): every 8-K and 8-K/A filed with the SEC, read once, classified and kept for 120 days.

A company files an 8-K within four business days of a material event; the report lists the events as numbered items
(1.01 a material agreement, 2.02 results, 5.02 an officer leaving or joining …) and usually attaches a press release
(Exhibit 99.1). Each run reads EDGAR's "current filings" feed for 8-K (newest first), then works back through the daily
form indexes (`backfill_days`), so nothing filed in between two runs is missed; each submission .txt (the 8-K and its
exhibits in one file) is read once and turned into a row:

  items      the item numbers (from the SGML header's ITEM INFORMATION lines, else the "Item 2.02" headings)
  topics     what it is about, in plain words: a merger or acquisition, a CEO or CFO change, a restatement, a cyber
             incident, a delisting notice, bankruptcy, a buyback, a dividend change, an offering (dilution), new debt,
             layoffs or restructuring, an impairment, an auditor change, earnings, an FDA decision, a contract award …
  guidance   raised / lowered / withdrawn / reaffirmed / mixed — when the press release says so, with the sentence
  headline   the press release's title; quote: the key sentences of the most material item (or of the release)

Cache:   cache/events8k/<YYYY-MM-DD>.json.gz (one file per filing day: a run rewrites only the days it touched),
         seen.json (read, nothing kept), state.json (daily indexes read, the backfill queue)
Publish: market/events8k.json — the last days' 8-Ks with tickers, newest first, and topic counts; used by the hub's
         8-K events table (✦ X per row), the company pages (holders index: events8k), the X posts (pipeline/engage.py
         event8k / post_8k) and the movers' "what is known today" (pipeline/context.py).
"""
import datetime as dt
import html
import re
from collections import Counter
from pathlib import Path

from core import Shards, localname, now, parse_xml, read_json, write_json
import ownership as OWN

FEED = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include'
        '&start={start}&count=100&output=atom')
DAILY = OWN.DAILY
ITEMS = {
    '1.01': 'entered into a material agreement', '1.02': 'ended a material agreement', '1.03': 'bankruptcy or receivership',
    '1.04': 'a mine safety shutdown', '1.05': 'a material cybersecurity incident', '2.01': 'completed an acquisition or disposition',
    '2.02': 'results of operations (earnings)', '2.03': 'a new financial obligation', '2.04': 'a triggering event on debt',
    '2.05': 'exit or restructuring costs', '2.06': 'a material impairment', '3.01': 'a delisting or listing-rule notice',
    '3.02': 'an unregistered sale of shares', '3.03': "changes to shareholders' rights", '4.01': 'a change of auditor',
    '4.02': 'a restatement: earlier financial statements should no longer be relied on', '5.01': 'a change in control',
    '5.02': 'a director or officer leaving, joining or changing pay', '5.03': 'bylaw or fiscal-year changes',
    '5.04': 'a blackout of the employee benefit plans', '5.05': 'a code of ethics change or waiver', '5.06': 'a change in shell company status',
    '5.07': 'shareholder vote results', '5.08': 'shareholder nominations', '7.01': 'a Regulation FD disclosure',
    '8.01': 'other events', '9.01': 'financial statements and exhibits',
}
# the SGML header names items by their titles ("ITEM INFORMATION: Results of Operations and Financial Condition")
TITLES = [
    (r'entry into a material definitive', '1.01'), (r'termination of a material definitive', '1.02'), (r'bankruptcy or receivership', '1.03'),
    (r'mine safety', '1.04'), (r'cybersecurity', '1.05'), (r'completion of acquisition or disposition', '2.01'),
    (r'results of operations and financial condition', '2.02'), (r'creation of a direct financial obligation', '2.03'),
    (r'triggering events', '2.04'), (r'costs associated with exit or disposal', '2.05'), (r'material impairments?', '2.06'),
    (r'notice of delisting|continued listing rule', '3.01'), (r'unregistered sales? of equity', '3.02'),
    (r'material modifications? to rights of security holders', '3.03'), (r'changes? in registrant.?s certifying accountant', '4.01'),
    (r'non-reliance on previously issued', '4.02'), (r'changes? in control of registrant', '5.01'),
    (r'departure of directors|election of directors|appointment of certain officers', '5.02'),
    (r'amendments? to articles of incorporation|change in fiscal year', '5.03'), (r'temporary suspension of trading', '5.04'),
    (r'code of ethics', '5.05'), (r'shell company status', '5.06'), (r'submission of matters to a vote', '5.07'),
    (r'shareholder (director )?nominations', '5.08'), (r'regulation fd disclosure', '7.01'), (r'^other events', '8.01'),
    (r'financial statements and exhibits', '9.01'),
]
# topics: (name, label, weight, items that suggest it, pattern in the text that confirms it); checked in this order
TOPICS = [
    ('bankruptcy', 'bankruptcy', 10, {'1.03'}, r'chapter 11|bankruptcy|receivership'),
    ('restatement', 'a restatement', 9, {'4.02'}, None),
    ('control', 'a change in control', 9, {'5.01'}, None),
    ('cyber', 'a cybersecurity incident', 8, {'1.05'}, None),
    ('deal', 'a merger or acquisition', 8, {'1.01', '2.01', '7.01', '8.01'},
     r'\bmerger agreement\b|agreement and plan of merger|\bto acquire\b|\bto be acquired\b|\bacquisition of\b|\bwill acquire\b|'
     r'\bcompleted (the|its) acquisition\b|\btender offer\b|\bper share in cash\b|\bbusiness combination\b'),
    ('delisting', 'a delisting notice', 7, {'3.01'}, None),
    ('ceo', 'a CEO change', 7, {'5.02'}, r'chief executive officer|\bCEO\b'),
    ('cfo', 'a CFO change', 6, {'5.02'}, r'chief financial officer|\bCFO\b'),
    ('fda', 'an FDA decision', 7, {'7.01', '8.01'},
     r'\bFDA\b[^.]{0,80}\b(approv|accept|clear|complete response|breakthrough|priority review|fast track|grant)|'
     r'complete response letter|\bPDUFA\b|marketing authori[sz]ation'),
    ('impairment', 'an impairment', 6, {'2.06'}, None),
    ('restructuring', 'layoffs or restructuring', 6, {'2.05'}, r'restructur|workforce reduction|reduction in force|layoff|exit|dispos'),
    ('offering', 'a share offering (dilution)', 5, {'3.02', '1.01', '8.01', '7.01'},
     r'public offering|registered direct offering|at-the-market|\bATM\b offering|private placement|equity offering|'
     r'pre-funded warrants|securities purchase agreement'),
    ('buyback', 'a share buyback', 5, {'8.01', '7.01', '1.01'}, r'repurchase (program|authori[sz]ation|plan)|buyback|share repurchase'),
    ('dividend', 'a dividend change', 4, {'8.01', '7.01'},
     r'(increase[sd]?|raise[sd]?|cut|suspend(s|ed)?|reduce[sd]?|special|initiat(es|ed))[^.]{0,40}\bdividend'),
    ('contract', 'a contract award', 4, {'8.01', '7.01', '1.01'}, r'awarded (a|an|the)[^.]{0,60}contract|contract award|task order'),
    ('debt', 'new debt', 3, {'2.03'}, None),
    ('auditor', 'an auditor change', 4, {'4.01'}, None),
    ('director', 'a board change', 3, {'5.02'}, r'director'),
    ('earnings', 'earnings', 3, {'2.02'}, None),
    ('vote', 'shareholder vote results', 1, {'5.07'}, None),
]
TOPIC_LABEL = {t[0]: t[1] for t in TOPICS}
TOPIC_WEIGHT = {t[0]: t[2] for t in TOPICS}
GUIDE = re.compile(r'\b(guidance|outlook|forecast|full[- ]year expectations?)\b', re.I)
UP = re.compile(r'\b(rais(e|es|ed|ing)|increas(e|es|ed|ing)|lift(s|ed)?|boost(s|ed)?|upgrad(e|es|ed)|improv(es|ed))\b', re.I)
DOWN = re.compile(r'\b(lower(s|ed|ing)?|reduc(e|es|ed|ing)|cut(s|ting)?|trim(s|med)?|downgrad(e|es|ed)|revis(es|ed) down(ward)?)\b', re.I)
WITHDRAW = re.compile(r'\b(withdr(aw|aws|ew|awn)|suspend(s|ed)?|no longer provid)', re.I)
KEEP = re.compile(r'\b(reaffirm(s|ed)?|reiterat(e|es|ed)|maintain(s|ed)?|confirm(s|ed)?)\b', re.I)
BOILER = re.compile(r'(?i)^(the information (in|contained in|furnished)|this current report|pursuant to the requirements|'
                    r'forward[- ]looking statements|exhibit (no|number)|signatures?$|item \d\.\d\d|\(d\) exhibits|cautionary)')


# ------------------------------------------------------------------ the submission
def html_text(s):
    """HTML (or plain text) → paragraphs of plain text."""
    s = re.sub(r'(?is)<(script|style|head)\b.*?</\1>', ' ', s)
    if re.search(r'(?i)<(p|div|br|tr|table)\b', s):      # HTML: source line breaks are only spaces
        s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table|center)>', '\n', s)
    s = re.sub(r'(?i)</t[dh]>', ' ', s)
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s)).replace('\xa0', ' ')
    out = []
    for line in s.split('\n'):
        t = re.sub(r'\s+', ' ', line).strip()
        if t:
            out.append(t)
    return out


def documents(txt):
    """The submission's documents: [(type, filename, text)] (TYPE 8-K, EX-99.1 …)."""
    out = []
    for m in re.finditer(r'(?is)<DOCUMENT>(.*?)</DOCUMENT>', txt):
        d = m.group(1)
        typ = (re.search(r'<TYPE>([^\n<]+)', d) or [None, ''])[1].strip().upper()
        name = (re.search(r'<FILENAME>([^\n<]+)', d) or [None, ''])[1].strip()
        body = re.search(r'(?is)<TEXT>(.*?)</TEXT>', d)
        out.append((typ, name, body.group(1) if body else ''))
    return out


def header(txt):
    head = txt[:txt.find('</SEC-HEADER>')] if '</SEC-HEADER>' in txt else txt[:20000]
    h = OWN.header(txt)
    titles = re.findall(r'ITEM INFORMATION:\s*(.+)', head)
    items = []
    for t in titles:
        code = next((c for p, c in TITLES if re.search(p, t.strip(), re.I)), None)
        if code and code not in items:
            items.append(code)
    acc = re.search(r'<ACCEPTANCE-DATETIME>(\d{14})', txt[:3000])
    per = re.search(r'CONFORMED PERIOD OF REPORT:\s*(\d{8})', head)
    a = acc.group(1) if acc else ''
    h.update({'items': items, 'accepted': f'{a[:4]}-{a[4:6]}-{a[6:8]}T{a[8:10]}:{a[10:12]}' if a else '',
              'period': f'{per.group(1)[:4]}-{per.group(1)[4:6]}-{per.group(1)[6:]}' if per else ''})
    return h


def item_sections(paras):
    """{item code: [paragraphs]} from the 8-K body's "Item 2.02 …" headings."""
    out, cur = {}, None
    for p in paras:
        m = re.match(r'(?i)^item\s*(\d)\s*\.\s*(\d\d)\b', p)
        if m:
            cur = f'{m.group(1)}.{m.group(2)}'
            out.setdefault(cur, [])
            rest = p[m.end():].strip(' .:-–—')
            if len(rest) > 120:                     # heading and text on one line
                out[cur].append(rest)
            continue
        if cur:
            out[cur].append(p)
    return out


def sentences(paras, n=2, limit=420):
    out = []
    for p in paras:
        if len(p) < 50 or BOILER.search(p):
            continue
        p = re.sub(r'^[A-Z][A-Za-z .,\']{2,60}\s*[–—-]+\s*\(?[A-Z][A-Za-z .,]{2,40}\)?\s*[–—-]+\s*', '', p)   # "CITY, ST — (WIRE) —"
        p = re.sub(r'^.{0,120}?\((GLOBE NEWSWIRE|BUSINESS WIRE|PR NEWSWIRE|ACCESSWIRE|ACCESS Newswire|Newsfile Corp\.?)\)\s*[-–—]*\s*', '', p, flags=re.I)
        for s in re.split(r'(?<=[.!?])\s+(?=[A-Z“"])', p):
            s = s.strip()
            if len(s) > 30 and not re.search(r'(?i)forward-looking|safe harbor', s):
                out.append(s)
            if len(out) >= n:
                break
        if len(out) >= n:
            break
    t = ' '.join(out)
    return t if len(t) <= limit else t[:limit].rsplit(' ', 1)[0] + '…'


def headline(paras):
    """The press release's title: an early line of 25–220 characters that reads like a headline."""
    for p in paras[:14]:
        if not 25 <= len(p) <= 220 or re.search(r'(?i)^(exhibit|ex-|for immediate release|press release|news release|contact|investor|media)', p):
            continue
        if re.search(r'\d{4}\s*[–—-]\s*\(?[A-Z ]*WIRE', p) or p.endswith(':'):
            continue
        if re.search(r'[A-Za-z]', p) and not re.match(r'^[\d\s,().-]+$', p):
            return p
    return ''


def guidance(paras):
    """(raised | lowered | withdrawn | reaffirmed | mixed, the sentence) from the release's sentences about guidance; a
    sentence with figures is preferred to one without (the title says "raises outlook", the body gives the range)."""
    found = {'up': [], 'down': [], 'keep': [], 'withdrawn': []}
    for p in paras[:400]:
        for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])', p):
            if len(s) > 400 or not GUIDE.search(s) or re.search(r'(?i)forward-looking|safe harbor|no assurance|undertakes no', s):
                continue
            if WITHDRAW.search(s):
                found['withdrawn'].append(s)
            elif UP.search(s) and not DOWN.search(s):
                found['up'].append(s)
            elif DOWN.search(s) and not UP.search(s):
                found['down'].append(s)
            elif KEEP.search(s):
                found['keep'].append(s)
    best = lambda xs: next((x for x in xs if re.search(r'\d', x)), xs[0]) if xs else None
    up, down, keep, withdrawn = best(found['up']), best(found['down']), best(found['keep']), best(found['withdrawn'])
    if withdrawn:
        return 'withdrawn', withdrawn
    if up and down:
        return 'mixed', up
    if up:
        return 'raised', up
    if down:
        return 'lowered', down
    if keep:
        return 'reaffirmed', keep
    return None, None


def parse_8k(txt, accession, folder):
    """One 8-K submission → its row."""
    h = header(txt)
    docs = documents(txt)
    main = next((d for d in docs if d[0].startswith('8-K')), docs[0] if docs else ('', '', ''))
    body = html_text(main[2])
    secs = item_sections(body)
    items = h['items'] or [c for c in secs if c in ITEMS]
    release = next((d for d in docs if re.match(r'EX-99(\.0?1)?$', d[0])), None) or next((d for d in docs if d[0].startswith('EX-99')), None)
    rel = html_text(release[2])[:600] if release else []
    allt = ' '.join(body[:300] + rel[:300])
    topics = []
    for name, _, _, its, pat in TOPICS:
        hit_item = bool(set(items) & its)
        if pat is None:
            ok = hit_item
        else:
            scope = ' '.join(sum((secs.get(i, []) for i in its if i in secs), [])) + ' ' + ' '.join(rel[:80]) if hit_item else ''
            ok = bool(scope and re.search(pat, scope, re.I))
            if name in ('fda', 'deal', 'contract', 'offering', 'buyback', 'dividend') and not ok and not hit_item:
                ok = False
        if ok and name not in topics:
            topics.append(name)
    if 'ceo' in topics or 'cfo' in topics:
        topics = [t for t in topics if t != 'director']
    g, gq = guidance(rel) if rel else (None, None)
    if g and 'guidance' not in topics:
        topics.insert(0 if g in ('raised', 'lowered', 'withdrawn') else len(topics), 'guidance')
    material = [c for c in items if c not in ('9.01',)] or items
    code = min(material, key=lambda c: _rank(c)) if material else None
    quote, src = '', ''
    if code and code not in ('2.02', '7.01', '8.01') and secs.get(code):
        quote, src = sentences(secs[code]), f'Item {code}'
    if not quote and rel:
        quote, src = sentences(rel[1:] if len(rel) > 1 else rel), (release[0].replace('EX-', 'Exhibit ') if release else '')
    if not quote and code and secs.get(code):
        quote, src = sentences(secs[code]), f'Item {code}'
    company = ((h['roles'].get('FILER') or h['roles'].get('SUBJECT COMPANY') or [{}])[0])
    score = max([TOPIC_WEIGHT.get(t, 0) for t in topics] + [2 if g in ('raised', 'lowered', 'withdrawn') else 0] + [0])
    if 'guidance' in topics and g in ('raised', 'lowered', 'withdrawn'):
        score = max(score, 6)
    return {'accession': accession, 'url': folder, 'form': h['form'] or '8-K', 'filed': h['filed'], 'accepted': h['accepted'],
            'period': h['period'], 'cik': (company.get('cik') or '').lstrip('0'), 'company': company.get('name', ''),
            'items': items, 'code': code or '', 'topics': topics, 'guidance': g, 'guidance_quote': (gq or '')[:300],
            'headline': headline(rel)[:200] if rel else '', 'quote': quote, 'quote_src': src, 'score': score}


def _rank(code):
    order = ['1.03', '4.02', '5.01', '1.05', '2.01', '1.01', '2.02', '5.02', '2.06', '2.05', '3.01', '4.01', '2.04', '3.02', '7.01',
             '8.01', '1.02', '2.03', '3.03', '5.07', '5.03', '5.05', '5.04', '5.06', '5.08', '1.04']
    return order.index(code) if code in order else 99


# ------------------------------------------------------------------ discovery and collection
def feed_entries(client, pages=5):
    out, seen = [], set()
    for page in range(pages):
        root = parse_xml(client.get(FEED.format(start=page * 100), sec=True))
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
    out, seen = [], set()
    for line in text.splitlines():
        if not re.match(r'8-K(/A)?(?=\s)', line):
            continue
        f = re.search(r'edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt\s*$', line)
        if not f or f.group(2) in seen:
            continue
        seen.add(f.group(2))
        out.append((f.group(2), f'https://www.sec.gov/Archives/edgar/data/{f.group(1)}/{f.group(2).replace("-", "")}/'))
    return out


def store(root):
    return Shards(Path(root) / 'cache' / 'events8k', date='filed', uid='accession', size=10)


def collect(client, root, cfg=None, today=None):
    cfg = cfg or {}
    today = today or dt.date.today()
    cdir = Path(root) / 'cache' / 'events8k'
    shards = store(root)
    empty = set(read_json(cdir / 'seen.json', []))
    seen = empty | shards.uids()
    state = read_json(cdir / 'state.json', {})
    errors, read, kept = 0, 0, 0
    todo = []
    try:
        todo = [(a, f) for a, f in feed_entries(client, int(cfg.get('feed_pages', 5))) if a not in seen]
    except Exception as exc:
        errors += 1
        print(f'8-K feed: {exc}', flush=True)
    queue = [tuple(x) for x in state.get('queue', [])]
    done_days = set(state.get('index_days', []))
    left = int(cfg.get('index_days_per_run', 3))
    for d in OWN.business_days(today - dt.timedelta(days=1), int(cfg.get('backfill_days', 30))):
        if left <= 0:
            break
        ymd = d.strftime('%Y%m%d')
        if ymd in done_days:
            continue
        left -= 1
        try:
            text = client.get(DAILY.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=ymd), sec=True).decode('latin-1')
            queue.extend(x for x in parse_daily_index(text) if x[0] not in seen)
            done_days.add(ymd)
        except RuntimeError as exc:
            if 'HTTP 404' in str(exc) or 'HTTP 403' in str(exc):
                if (today - d).days > 3:
                    done_days.add(ymd)
            else:
                errors += 1
                print(f'daily index {ymd}: {exc}', flush=True)
    new = {a for a, _ in todo}
    queue = [x for x in dict.fromkeys(queue) if x[0] not in seen and x[0] not in new]
    work = (todo + queue)[:int(cfg.get('batch', 300))]
    for acc, folder in work:
        try:
            txt = client.get(folder + acc + '.txt', sec=True).decode('utf-8', 'replace')
            row = parse_8k(txt, acc, folder)
            if row.get('filed'):
                shards.add(row)
                kept += 1
            else:
                empty.add(acc)
            seen.add(acc)
            read += 1
        except Exception as exc:
            errors += 1
            print(f'8-K {acc}: {exc}', flush=True)
            if errors > 25:
                break
    queue = [x for x in queue if x[0] not in seen]
    shards.save(keep=(today - dt.timedelta(days=int(cfg.get('keep_days', 120)))).isoformat())
    window = {d.strftime('%Y%m%d') for d in OWN.business_days(today, int(cfg.get('backfill_days', 30)) + 10)}
    write_json(cdir / 'state.json', {'index_days': sorted(done_days & window), 'queue': [list(x) for x in queue[:30000]], 'updated_at': now()})
    write_json(cdir / 'seen.json', sorted(empty))
    return {'status': 'ok' if errors <= 25 else 'partial', 'read': read, 'kept': kept, 'waiting': len(queue), 'errors': errors,
            'on_file': len(shards.uids()), 'index_days': len(done_days & window), 'updated_at': now()}


# ------------------------------------------------------------------ publish
def label(r):
    """'a CEO change', 'guidance raised', 'earnings' … — the plainest name for what the 8-K reports."""
    t = r.get('topics') or []
    if 'guidance' in t and r.get('guidance') in ('raised', 'lowered', 'withdrawn') and t[0] == 'guidance':
        return f"guidance {r['guidance']}"
    if t:
        return TOPIC_LABEL.get(t[0], t[0])
    return ITEMS.get(r.get('code') or '', 'a current report')


def publish(root, out_dir, today=None, days=10):
    today = today or dt.date.today()
    shards = store(root)
    if not shards.rows:
        return None
    tickers = OWN.cik_tickers(root)
    since = (today - dt.timedelta(days=days)).isoformat()
    rows = []
    for r in shards.all():
        if (r.get('filed') or '') < since:
            break
        t = tickers.get(r.get('cik') or '', '')
        if not t and (r.get('filed') or '') < (today - dt.timedelta(days=3)).isoformat():
            continue
        rows.append({**{k: v for k, v in r.items() if k != 'guidance_quote' or v}, 'ticker': t, 'label': label(r),
                     'quote': (r.get('quote') or '')[:320]})
    week = (today - dt.timedelta(days=7)).isoformat()
    counts = Counter(t for r in rows if r['filed'] >= week and r.get('ticker') for t in r.get('topics') or [])
    data = {'generated_at': now(), 'on_file': len(shards.uids()), 'since': since, 'days': days,
            'note': ('Every 8-K and 8-K/A as filed with the SEC, read once: the items reported, what they are about (from the '
                     'items and the filing’s own words), guidance raised or lowered when the press release says so, and the '
                     'key sentences. A company files an 8-K within four business days of the event.'),
            'topics': {k: TOPIC_LABEL.get(k, k) for k in [t[0] for t in TOPICS] + ['guidance']},
            'counts': dict(counts.most_common()),
            'rows': rows[:int(3000)]}
    path = Path(out_dir) / 'events8k.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    import json
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)
    return {'rows': len(data['rows']), 'with_ticker': sum(1 for r in rows if r['ticker'])}


def by_ticker(root, today=None, n=15, days=120):
    """ticker → its latest 8-Ks (company pages)."""
    today = today or dt.date.today()
    tickers = OWN.cik_tickers(root)
    out = {}
    for r in store(root).all():
        t = tickers.get(r.get('cik') or '')
        if not t or len(out.get(t, [])) >= n:
            continue
        out.setdefault(t, []).append({k: r.get(k) for k in ('filed', 'accepted', 'form', 'items', 'topics', 'guidance', 'headline', 'quote',
                                                            'quote_src', 'url', 'accession') if r.get(k) not in (None, '', [])}
                                     | {'label': label(r), 'quote': (r.get('quote') or '')[:240]})
    return out
