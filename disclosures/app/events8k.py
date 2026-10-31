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
  guidance   raised / lowered / narrowed / widened / initiated / reaffirmed / withdrawn / mixed / updated — from the press
             release's words (app/guidance.py: "lifts", "trims", "tightens", "raising the low end" …) and its numbers;
             guidance_tags every change found, guidance_items the guided ranges per metric (with the prior range when stated)
  headline   the press release's title; quote: the key sentences of the most material item (or of the release)

Cache:   cache/events8k/<YYYY-MM-DD>.json.gz (one file per filing day: a run rewrites only the days it touched),
         seen.json (read, nothing kept), state.json (daily indexes read, the backfill queue)
Publish: market/events8k.json — the last days' 8-Ks with tickers, newest first, and topic counts; used by the hub's
         8-K events table (✦ X per row), the company pages (holders index: events8k), the X posts (pipeline/engage.py
         event8k / post_8k) and the movers' "what is known today" (pipeline/context.py).
"""
from retry_queue import RetryQueue
import datetime as dt
import html
import re
from collections import Counter
from pathlib import Path

from core import Shards, localname, now, parse_xml, read_json, write_json
import guidance as G
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
# the items' official titles, as filers repeat them after "Item 5.02" (stripped from the quoted text)
FULL_TITLES = [
    ('Entry into a Material Definitive Agreement', '1.01'), ('Termination of a Material Definitive Agreement', '1.02'),
    ('Bankruptcy or Receivership', '1.03'), ('Material Cybersecurity Incidents', '1.05'),
    ('Completion of Acquisition or Disposition of Assets', '2.01'), ('Results of Operations and Financial Condition', '2.02'),
    ('Creation of a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement of a Registrant', '2.03'),
    ('Triggering Events That Accelerate or Increase a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement', '2.04'),
    ('Costs Associated with Exit or Disposal Activities', '2.05'), ('Material Impairments', '2.06'),
    ('Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing', '3.01'),
    ('Unregistered Sales of Equity Securities', '3.02'), ('Material Modification to Rights of Security Holders', '3.03'),
    ("Changes in Registrant's Certifying Accountant", '4.01'),
    ('Non-Reliance on Previously Issued Financial Statements or a Related Audit Report or Completed Interim Review', '4.02'),
    ('Changes in Control of Registrant', '5.01'),
    ('Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements of Certain Officers', '5.02'),
    ('Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year', '5.03'),
    ('Submission of Matters to a Vote of Security Holders', '5.07'), ('Regulation FD Disclosure', '7.01'), ('Other Events', '8.01'),
    ('Financial Statements and Exhibits', '9.01'),
]
# topics: (name, label, weight, items that suggest it, pattern one sentence of those items' text or of the press release
# must match to confirm it — None: the item alone is enough); checked in this order
ROLE_CHANGE = (r'\b(appoint|named|names|name[sd]? as|elect|resign|retire|depart|step(s|ped)? down|stepping down|succeed|successor|'
               r'terminat|transition|separation|will serve as|promot)')
TOPICS = [
    ('bankruptcy', 'bankruptcy', 10, {'1.03'}, None),
    ('restatement', 'a restatement', 9, {'4.02'}, None),
    ('control', 'a change in control', 9, {'5.01'}, None),
    ('cyber', 'a cybersecurity incident', 8, {'1.05'}, None),
    ('deal', 'a merger or acquisition', 8, {'1.01', '2.01', '7.01', '8.01'},
     r'agreement and plan of merger|\bmerger agreement\b|definitive (merger |purchase |acquisition )?agreement[^.]{0,80}\b(acquire|acquisition|merge|purchase)|'
     r'\b(to|will|agreed to) acquire\b[^.]{0,140}\$\s?[\d.,]+\s*(per share|million|billion)|\btender offer\b|\bper share in cash\b|'
     r'business combination agreement|\bcompleted (the|its) (previously announced )?(acquisition|merger|sale of)|completion of (the|its) (acquisition|merger)'),
    ('delisting', 'a delisting notice', 7, {'3.01'}, None),
    ('ceo', 'a CEO change', 7, {'5.02'}, (r'chief executive officer|\bCEO\b', ROLE_CHANGE)),
    ('cfo', 'a CFO change', 6, {'5.02'}, (r'chief financial officer|\bCFO\b', ROLE_CHANGE)),
    ('fda', 'an FDA decision', 7, {'7.01', '8.01'},
     r'\bFDA\b[^.]{0,80}\b(approv|accept|clear|complete response|breakthrough|priority review|fast track|grant)|'
     r'complete response letter|\bPDUFA\b|marketing authori[sz]ation'),
    ('impairment', 'an impairment', 6, {'2.06'}, None),
    ('restructuring', 'layoffs or restructuring', 6, {'2.05'}, None),
    ('offering', 'a share offering (dilution)', 5, {'3.02', '1.01', '8.01', '7.01'},
     {'any': r'\b(priced|pricing of|closed|closing of|announced|entered into|launch(ed|es)?|commenc(ed|es)|upsiz(ed|es))\b[^.]{0,100}\b'
             r'(underwritten |registered direct |public |private |at-the-market |equity |follow-on )(offering|placement)|'
             r'securities purchase agreement|at-the-market (offering|sales agreement|program)|equity distribution agreement',
      'not': r'\b(notes|debentures|bonds|principal amount|credit agreement|term loan)\b',
      'unless': r'\b(common stock|ordinary shares|shares of|warrants|units|ADSs?|American depositary|preferred stock)\b'}),
    ('buyback', 'a share buyback', 5, {'8.01', '7.01', '1.01'},
     r'(repurchase|buyback) (program|authori[sz]ation)|authori[sz]ed[^.]{0,60}\b(repurchase|buyback)|new share repurchase'),
    ('dividend', 'a dividend change', 4, {'8.01', '7.01'},
     r'\b(increas|rais|cut|suspend|reduc|initiat|reinstat|eliminat)\w*[^.]{0,60}\b(quarterly |special |cash |annual )*dividend|\bspecial (cash )?dividend'),
    ('contract', 'a contract award', 4, {'8.01', '7.01', '1.01'}, r'\bawarded (a|an|the)\b[^.]{0,60}\bcontract|\bcontract award|\btask order'),
    ('debt', 'new debt', 3, {'2.03'}, None),
    ('auditor', 'an auditor change', 4, {'4.01'}, None),
    ('director', 'a board change', 3, {'5.02'}, (r'\bdirectors?\b|\bboard\b', ROLE_CHANGE)),
    ('earnings', 'earnings', 3, {'2.02'}, None),
    ('vote', 'shareholder vote results', 1, {'5.07'}, None),
]
TOPIC_LABEL = {t[0]: t[1] for t in TOPICS}
TOPIC_WEIGHT = {t[0]: t[2] for t in TOPICS}
_NOUN = r'(?:guidance|outlook|forecast|financial targets?)'
_MOD = (r'(?:\s+(?:its|the|our|full[- ]year|fiscal(?:\s+year)?|annual|\d{4}|fy\s?\d{2,4}|revenue|sales|earnings|eps|adjusted|ebitda|'
        r'non-gaap|gaap|net|operating|margin|income|per\s+share|and|,|range|for|year|quarter|fourth[- ]quarter|second[- ]half)){0,8}')
GUIDE = re.compile(_NOUN, re.I)
UP = re.compile(rf'\b(rais(es|ed|ing)|increas(es|ed|ing)|lift(s|ed|ing)|boost(s|ed)|upgrad(es|ed))\b{_MOD}\s+{_NOUN}|{_NOUN}\s+(is\s+|was\s+|has\s+been\s+)?(raised|increased|lifted)\b', re.I)
DOWN = re.compile(rf'\b(lower(s|ed|ing)|reduc(es|ed|ing)|cut(s|ting)?|trim(s|med)|downgrad(es|ed))\b{_MOD}\s+{_NOUN}|{_NOUN}\s+(is\s+|was\s+|has\s+been\s+)?(lowered|reduced|cut)\b', re.I)
WITHDRAW = re.compile(rf'\b(withdr(aws|ew|awn|awing)|suspend(s|ed|ing)|no longer (provides|providing))\b{_MOD}\s+{_NOUN}', re.I)
KEEP = re.compile(rf'\b(reaffirm(s|ed|ing)?|reiterat(es|ed|ing)|maintain(s|ed|ing)|confirm(s|ed|ing))\b{_MOD}\s+{_NOUN}', re.I)
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
            title = next((t for t, c in FULL_TITLES if c == cur), None)
            cut = re.sub(r'(?i)^' + r'[\s,;:.\-–—]*'.join(map(re.escape, title.split())) + r'[\s.:;\-–—]*', '', rest) if title else rest
            if len(cut) > (20 if cut != rest else 80):     # heading and text on one line
                out[cur].append(cut)
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


WIRE = re.compile(r'/PRNewswire/|\((?:GLOBE NEWSWIRE|BUSINESS WIRE|ACCESSWIRE|ACCESS Newswire|Newsfile Corp\.?|EQS[- ]Newswire|PRNewswire|'
                  r'MARKETWIRE|Canada NewsWire|CNW)\)|^[A-Z][A-Za-z .,\'&-]{2,50}\s*(?:[,–—-]+\s*\(?|\()[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4}\)?\s*[–—-]+|'
                  r'\b(today|this morning) (announced|reported|reports|announces)\b')
CONTACT = re.compile(r'(?i)@|\bcontacts?\b|\binvestor relations\b|\bmedia\b:|\(\d{3}\)\s?\d{3}|\d{3}[-.]\d{3}[-.]\d{4}|^exhibit|^ex-\d|'
                     r'for immediate release|^(press|news) release$|^page \d|\b\d{5}(-\d{4})?\s*$|'
                     r'^\d+\s+[A-Za-z .]+\b(street|st\.|avenue|ave\.?|road|rd\.|court|suite|blvd|boulevard|drive|parkway|way)\b')


HEADVERB = re.compile(r'(?i)\b(announc|report|appoint|nam|complet|receiv|launch|enter|sign|declar|clos|pric|expand|provid|achiev|'
                      r'deliver|post|record|win|wins|won|award|acquir|agree|updat|reaffirm|rais|lower|issu|present|host|schedul|elect|'
                      r'promot|initiat|begin|file|obtain|secur|unveil|introduc|partner|select|join|retir|resign|transition|grant|'
                      r'approv|meet|reach|exceed|surpass|releas|publish|confirm|withdraw|suspend|terminat|settl|regain|transfer|'
                      r'chang|increas|decreas|cut|pay|distribut|strengthen|extend|open|sell|sold|buy|purchas|merg|combin|'
                      r'spin|divest|start|expect|forecast|reiterat|introduc)(e|es|ed|ing|s|d)?\b')


def dateline(paras):
    """Index of the release's dateline paragraph ("SAN JOSE, Calif., Oct. 16, 2026 (GLOBE NEWSWIRE) -- …"), or None
    when the exhibit is not a press release."""
    for i, p in enumerate(paras[:60]):              # highlights can come first: Cisco's dateline is its 37th paragraph
        if WIRE.search(p):
            return i
    return None


def headline(paras, line=None):
    """The press release's title: the first line before the dateline that reads like one (5–40 words, no contact
    details)."""
    line = dateline(paras) if line is None else line
    if line is None:
        return ''
    for p in paras[:line] if line > 0 else []:
        words = len(p.split())
        if 4 <= words <= 40 and not CONTACT.search(p) and (HEADVERB.search(p) or re.search(r'[$%]|\d', p)):
            return p
    return ''


def _sentences_of(paras):
    for p in paras:
        for x in re.split(r'(?<=[.!?])\s+(?=[A-Z“"])', p):
            if not re.match(r'(?i)\s*as previously (reported|disclosed|announced)', x):
                yield x


def _says(pat, sentence):
    """A topic pattern against one sentence: one regex; a pair that must both match; or {'any': regex, 'not': regex that
    rules the sentence out, 'unless': regex that rules it back in} (an offering of notes is debt, not dilution)."""
    if isinstance(pat, dict):
        if not re.search(pat['any'], sentence, re.I):
            return False
        return not (pat.get('not') and re.search(pat['not'], sentence, re.I) and not (pat.get('unless') and re.search(pat['unless'], sentence, re.I)))
    if isinstance(pat, tuple):
        return all(re.search(p, sentence, re.I) for p in pat)
    return bool(re.search(pat, sentence, re.I))


def guidance(paras):
    """(raised | lowered | narrowed | widened | initiated | reaffirmed | withdrawn | mixed | updated, the sentence) of a
    release's guidance (app/guidance.py reads the words and the ranges)."""
    r = G.read(paras)
    return (r['label'], r['quote'] or None) if r['label'] else (None, None)


def parse_8k(txt, accession, folder):
    """One 8-K submission → its row."""
    h = header(txt)
    docs = documents(txt)
    main = next((d for d in docs if d[0].startswith('8-K')), docs[0] if docs else ('', '', ''))
    body = html_text(main[2])
    secs = item_sections(body)
    items = h['items'] or [c for c in secs if c in ITEMS]
    release = next((d for d in docs if re.match(r'EX-99(\.0?1)?$', d[0])), None) or next((d for d in docs if d[0].startswith('EX-99')), None)
    full = html_text(release[2]) if release else []
    rel = full[:600]
    line = dateline(rel)
    is_release = line is not None                     # a press release, not a consent, a presentation or financial statements
    topics = []
    for name, _, _, its, pat in TOPICS:
        hit_item = bool(set(items) & its)
        if not hit_item:
            continue
        if pat is None:
            ok = True
        else:
            scope = sum((secs.get(i, []) for i in its if i in secs), []) + (rel[:60] if is_release else [])
            ok = any(_says(pat, x) for x in _sentences_of(scope))
        if ok and name not in topics:
            topics.append(name)
    if 'ceo' in topics or 'cfo' in topics:
        topics = [t for t in topics if t != 'director']
    gr = G.read(full, filed=h.get('filed')) if is_release else {'label': None, 'quote': '', 'tags': [], 'items': []}
    g, gq = gr['label'], gr['quote']
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
    score = max([TOPIC_WEIGHT.get(t, 0) for t in topics] + [2 if g in ('raised', 'lowered', 'withdrawn', 'mixed') else 0] + [0])
    if 'guidance' in topics and g in ('raised', 'lowered', 'withdrawn', 'mixed', 'narrowed', 'widened'):
        score = max(score, 6)
    return {'v': PARSER, 'gv': G.VERSION, 'accession': accession, 'url': folder, 'form': h['form'] or '8-K', 'filed': h['filed'], 'accepted': h['accepted'],
            'period': h['period'], 'cik': (company.get('cik') or '').lstrip('0'), 'company': company.get('name', ''),
            'items': items, 'code': code or '', 'topics': topics, 'guidance': g, 'guidance_quote': (gq or '')[:300],
            **({'guidance_tags': gr['tags']} if gr['tags'] else {}),
            **({'guidance_reported': gr.get('reported')} if gr.get('reported') and gr['items'] else {}),
            **({'guidance_items': [dict(it, quote=(it.get('quote') or '')[:220]) for it in gr['items'][:30]]} if gr['items'] else {}),
            'headline': headline(rel, line)[:200] if is_release else '', 'quote': quote, 'quote_src': src, 'score': score}


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


PARSER = 8          # bump when parse_8k changes: the filings on file are read again (newest first) and their rows replaced
                    # 8: guidance.VERSION 4 (outlook tables with their column titles on lines of their own)
                    # 6: the guided period no longer taken from a comparison base (guidance.py VERSION 2)


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
    retry = RetryQueue(cdir)
    errors, read, kept = 0, 0, 0
    todo = []
    try:
        if retry.due('feed'):
            todo = [(a, f) for a, f in feed_entries(client, int(cfg.get('feed_pages', 5))) if a not in seen]
            retry.succeeded('feed')
    except Exception as exc:
        errors += 1
        retry.failed('feed', exc)
        print(f'8-K feed: {exc}', flush=True)
    queue = [tuple(x) for x in state.get('queue', [])]
    done_days = set(state.get('index_days', []))
    left = int(cfg.get('index_days_per_run', 3))
    for d in OWN.business_days(today - dt.timedelta(days=1), int(cfg.get('backfill_days', 30))):
        if left <= 0:
            break
        ymd = d.strftime('%Y%m%d')
        if ymd in done_days or not retry.due('index:' + ymd):
            continue
        left -= 1
        try:
            text = client.get(DAILY.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=ymd), sec=True).decode('latin-1')
            queue.extend(x for x in parse_daily_index(text) if x[0] not in seen)
            done_days.add(ymd)
            retry.succeeded('index:' + ymd)
        except RuntimeError as exc:
            if 'HTTP 404' in str(exc):
                if (today - d).days > 3:
                    done_days.add(ymd)
            else:
                retry.failed('index:' + ymd, exc)
                errors += 1
                print(f'daily index {ymd}: {exc}', flush=True)
    queue = [x for x in dict.fromkeys(todo + queue) if x[0] not in seen]
    # a better parser: the filings on file are read again, newest first, a share of each run's batch
    if state.get('parser') != PARSER and not state.get('reparse'):
        # guidance is read from earnings releases: only those are read again (items 2.02 / 7.01, or guidance found before)
        state['reparse'] = [[r['accession'], r['url']] for r in shards.all()
                            if set(r.get('items') or []) & {'2.02', '7.01'} or r.get('guidance')]
    redo = [tuple(x) for x in state.get('reparse') or []]
    batch = int(cfg.get('batch', 300))
    pending = [x for x in queue if retry.due(x[0])]
    reparsing = [x for x in redo if retry.due(x[0])][:max(batch // 4, batch - len(pending))]
    work = list(dict.fromkeys(pending[:batch-len(reparsing)] + reparsing))[:batch]
    redone = set()
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
            redone.add(acc)
            retry.succeeded(acc)
        except Exception as exc:
            errors += 1
            retry.failed(acc, exc)
            print(f'8-K {acc}: {exc}', flush=True)
            if errors > 25:
                break
    queue = [x for x in queue if x[0] not in seen]
    redo = [x for x in redo if x[0] not in redone]
    shards.save(keep=(today - dt.timedelta(days=int(cfg.get('keep_days', 120)))).isoformat())
    window = {d.strftime('%Y%m%d') for d in OWN.business_days(today, int(cfg.get('backfill_days', 30)) + 10)}
    write_json(cdir / 'state.json', {'index_days': sorted(done_days & window), 'queue': [list(x) for x in queue],
                                     'parser': PARSER if not redo else state.get('parser'), 'reparse': [list(x) for x in redo],
                                     'updated_at': now()})
    write_json(cdir / 'seen.json', sorted(empty))
    retry.save()
    # every release's guidance kept for good, and a few older releases read per run (app/guidance_history.py)
    gh = None
    if (cfg.get('guidance_history') or {}).get('enabled', True):
        try:
            import guidance_history as GH
            gh = GH.collect(client, root, cfg.get('guidance_history'), today)
        except Exception as exc:
            gh = {'status': 'error', 'error': str(exc)[:200]}
            print(f'::warning::guidance history: {str(exc)[:200]}', flush=True)
    return {'status': 'partial' if errors or retry.rows or queue or redo else 'ok', **retry.summary(), 'read': read, 'kept': kept, 'waiting': len(queue), 'reparse_left': len(redo),
            **({'guidance_history': gh} if gh else {}),
            'errors': errors, 'latest_filing_date': max((r.get('filed', '') for r in shards.all()), default=None),
            'on_file': len(shards.uids()), 'index_days': len(done_days & window), 'updated_at': now()}


# ------------------------------------------------------------------ publish
def label(r):
    """'a CEO change', 'guidance raised', 'earnings' … — the plainest name for what the 8-K reports."""
    t = r.get('topics') or []
    if 'guidance' in t and r.get('guidance') in G.PRIORITY and r.get('guidance') != 'updated' and t[0] == 'guidance':
        return f"guidance {G.phrase(r.get('guidance_tags') or [r['guidance']]) or r['guidance']}"
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
        rows.append({**{k: v for k, v in r.items() if (k != 'guidance_quote' or v) and k != 'guidance_items'}, 'ticker': t, 'label': label(r),
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


def guidance_by_ticker(root, today=None, days=120):
    """ticker → the latest earnings release's guidance (company pages, the Sankey's "Show guidance"): its ranges per
    metric, each against the release's own prior range or else the same metric in the company's earlier release on file,
    so a range that moved without a word about it is still marked raised / lowered / narrowed / widened."""
    today = today or dt.date.today()
    tickers = OWN.cik_tickers(root)
    since = (today - dt.timedelta(days=days)).isoformat()
    per = {}
    for r in store(root).all():                       # newest first
        if (r.get('filed') or '') < since:
            break
        if r.get('guidance_items') and r.get('cik'):
            per.setdefault(r['cik'], []).append(r)
    out = {}
    for cik, rows in per.items():
        t = tickers.get(cik)
        if not t:
            continue
        top = rows[0]
        earlier = [(x.get('filed'), x['guidance_items']) for x in rows[1:] if x.get('accession') != top.get('accession')]
        try:                                          # older releases (beyond the 120 days) from the guidance history
            import guidance_history as GH
            seen = {x.get('accession') for x in rows}
            earlier += [(f, items) for f, items, acc in GH.earlier(root, cik, top.get('accession'), top.get('filed')) if acc not in seen]
            earlier.sort(key=lambda x: x[0] or '', reverse=True)
        except Exception as exc:
            print(f'guidance history {cik}: {exc}', flush=True)
        items = G.diff(top['guidance_items'], earlier)
        tags = G.tags_of(items, top.get('guidance_tags') or [])
        out[t] = {'filed': top.get('filed'), 'accession': top.get('accession'), 'url': top.get('url'), 'form': top.get('form'),
                  **({'reported': top['guidance_reported']} if top.get('guidance_reported') else {}),
                  'headline': top.get('headline'), 'label': G._primary(tags), 'tags': tags, 'phrase': G.phrase(tags),
                  'quote': top.get('guidance_quote') or '', 'items': items,
                  'earlier': [{'filed': x.get('filed'), 'label': x.get('guidance'), 'tags': x.get('guidance_tags') or []} for x in rows[1:4]]}
    return out
