"""News (4.7): press releases from the wires and government releases, matched to the listed companies they name.

Only the headline, the time and the link are kept — never the body text: the row says what was announced and where to
read it. Sources (each read every run; a source that fails is reported in news-status.json and skipped):

  PR Newswire     the public RSS feeds (all releases and the financial, earnings, health, technology, business and
                  energy lists; 20 newest each). The issuer is the feed's dc:contributor; the ticker is the exchange tag
                  the release gives ("(NYSE: TFC)"), kept when the tag's listed company matches the issuer, else the
                  issuer's name matched to SEC's company list. Law-firm class-action notices and non-English releases are
                  left out.
  FDA             openFDA's Drugs@FDA: approvals of new drugs and biologics (NDA / BLA, original applications) in the
                  last days, by sponsor; and the FDA press-release feed (headlines only, no ticker unless a company's
                  name is in it).
  SEC             press releases (charges and settlements name the company in the headline), litigation releases,
                  administrative proceedings and trading suspensions (the respondents' names) — matched by exact
                  company name only.

(War.gov's daily contract announcements and GlobeNewswire answer GitHub's runners with "access denied" (403); GDELT
rate-limits them. They are not collected.)

Cache:   cache/news/<YYYY-MM-DD>.json.gz (one file per publication day), state.json (per source: last ok, items)
Publish: market/news.json — the last days' items, newest first; the hub's News table (✦ X per row with a ticker), the
         company pages (holders index: news) and the movers' "what is known today" (pipeline/context.py).
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
from pathlib import Path

from core import Shards, localname, now, parse_xml, read_json, write_json
import market as M

PRN = [
    'https://www.prnewswire.com/rss/news-releases-list.rss',
    'https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss',
    'https://www.prnewswire.com/rss/financial-services-latest-news/earnings-list.rss',
    'https://www.prnewswire.com/rss/health-latest-news/health-latest-news-list.rss',
    'https://www.prnewswire.com/rss/consumer-technology-latest-news/consumer-technology-latest-news-list.rss',
    'https://www.prnewswire.com/rss/business-technology-latest-news/business-technology-latest-news-list.rss',
    'https://www.prnewswire.com/rss/energy-latest-news/energy-latest-news-list.rss',
]
FDA_PRESS = 'https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml'
OPENFDA = ('https://api.fda.gov/drug/drugsfda.json?search=submissions.submission_status:AP+AND+'
           'submissions.submission_status_date:[{a}+TO+{b}]&limit=100')
SEC_FEEDS = [('sec_release', 'https://www.sec.gov/news/pressreleases.rss'),
             ('sec_action', 'https://www.sec.gov/enforcement-litigation/litigation-releases/rss'),
             ('sec_action', 'https://www.sec.gov/enforcement-litigation/administrative-proceedings/rss'),
             ('suspension', 'https://www.sec.gov/enforcement-litigation/trading-suspensions/rss')]
TAG = re.compile(r'\((?:NYSE American|NYSE MKT|NYSE Arca|NYSE|NASDAQ|Nasdaq|NasdaqGS|NasdaqGM|NasdaqCM|Cboe|CBOE|OTCQX|OTCQB|OTC)'
                 r'(?:\s*[A-Z]{0,3})?\s*:\s*([A-Z]{1,5}(?:[.-][A-Z]{1,2})?)\s*(?:[;,][^)]*)?\)')
LAWFIRM = re.compile(r'(?i)class action|securities fraud|investors? (who|have|with)\b.{0,40}(loss|opportunity)|shareholder alert|'
                     r'\bdeadline\b|lead plaintiff|investigation (of|on behalf)|law firm|attorneys? at law|reminds (investors|shareholders)')


def _text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _when(s):
    """RSS pubDate → ISO UTC ('2026-10-17T21:43')."""
    try:
        d = email.utils.parsedate_to_datetime(s.strip())
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M')
    except (TypeError, ValueError, IndexError):
        return ''


def uid(url):
    return hashlib.sha1(url.strip().encode()).hexdigest()[:16]


def rss_items(body):
    """[{title, link, published, description, contributor, subject, industry, language}] from an RSS 2.0 feed."""
    root = parse_xml(body)
    out = []
    for item in (e for e in root.iter() if localname(e.tag) == 'item'):
        f = {}
        for c in item:
            k = localname(c.tag)
            if k not in f:
                f[k] = ''.join(c.itertext()).strip()
        out.append({'title': _text(f.get('title')), 'link': (f.get('link') or '').strip(), 'published': _when(f.get('pubDate', '')),
                    'description': _text(f.get('description'))[:600], 'contributor': _text(f.get('contributor')),
                    'subject': f.get('subject', ''), 'industry': f.get('industry', ''), 'language': f.get('language', ''),
                    'creator': _text(f.get('creator'))})
    return out


class Names:
    """SEC's listed companies: ticker → name, and exact normalised name → ticker (the main share class)."""

    def __init__(self, root):
        self.name, self.by_name = {}, {}
        for r in (read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
            t = M.canon(r.get('ticker'))
            if not t:
                continue
            self.name.setdefault(t, r.get('title') or '')
            self.by_name.setdefault(M.norm_name(r.get('title') or ''), t)

    def listed(self, t):
        return M.canon(t) in self.name

    def lookup(self, company):
        k = M.norm_name(company or '')
        return self.by_name.get(k) if k and len(k) >= 3 else None

    def same(self, ticker, company):
        """True when the issuer's name and the ticker's listed name share their first word."""
        a, b = M.norm_name(self.name.get(M.canon(ticker), '')).split(), M.norm_name(company or '').split()
        return bool(a and b) and (a[0] == b[0] or (len(a[0]) >= 4 and b[0].startswith(a[0][:4])))


def prn_rows(items, names):
    out, skipped = [], {'law firm': 0, 'not English': 0}
    for it in items:
        if not it['link'] or not it['title']:
            continue
        if it['language'] and not it['language'].lower().startswith('en'):
            skipped['not English'] += 1
            continue
        if it['subject'] == 'ATY' or it['industry'] == 'LGL' or LAWFIRM.search(it['title']) or LAWFIRM.search(it['contributor']):
            skipped['law firm'] += 1
            continue
        company = it['contributor']
        tags = [M.canon(t) for t in TAG.findall(it['title'] + ' ' + it['description'])]
        tickers = [t for t in dict.fromkeys(tags) if t and names.listed(t) and names.same(t, company)]
        how = 'exchange tag' if tickers else ''
        if not tickers:
            t = names.lookup(company)
            if t:
                tickers, how = [t], 'issuer name'
        out.append({'id': uid(it['link']), 'source': 'PR Newswire', 'kind': 'release', 'title': it['title'][:240], 'url': it['link'],
                    'published': it['published'], 'company': company, 'tickers': tickers, 'match': how})
    return out, skipped


def fda_rows(payload, names, since):
    """New drug and biologic approvals (NDA / BLA originals) from openFDA's Drugs@FDA."""
    out = []
    for r in payload.get('results') or []:
        appl = r.get('application_number') or ''
        if not re.match(r'(NDA|BLA)\d', appl):
            continue
        sub = [s for s in r.get('submissions') or [] if s.get('submission_status') == 'AP' and (s.get('submission_status_date') or '') >= since
               and s.get('submission_type') == 'ORIG']
        if not sub:
            continue
        s = max(sub, key=lambda s: s.get('submission_status_date') or '')
        d = s['submission_status_date']
        prod = (r.get('products') or [{}])[0]
        brand = (prod.get('brand_name') or '').title()
        generic = ', '.join(sorted({(a.get('name') or '').lower() for a in prod.get('active_ingredients') or [] if a.get('name')}))[:80]
        sponsor = r.get('sponsor_name') or ''
        t = names.lookup(sponsor)
        url = f'https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={re.sub(r"[^0-9]", "", appl)}'
        out.append({'id': uid(url + d), 'source': 'FDA (Drugs@FDA)', 'kind': 'fda', 'url': url, 'published': f'{d[:4]}-{d[4:6]}-{d[6:8]}T12:00',
                    'title': f"FDA approved {brand or appl}" + (f" ({generic})" if generic and generic.lower() != brand.lower() else '')
                             + f" — {appl[:3]} {appl[3:]}, sponsor {sponsor.title()}",
                    'company': sponsor.title(), 'tickers': [t] if t else [], 'match': 'sponsor name' if t else '', 'drug': brand, 'application': appl})
    return out


def named_companies(title):
    """Companies a headline names: "SEC Charges Acme Corp. with …" → ['Acme Corp.']; "A and B Holdings, LLC" → both."""
    m = re.search(r'(?i)\b(?:charges|sues|settles with|obtains (?:final )?judgment against|bars|suspends trading in)\s+(.+?)'
                  r'(?:\s+(?:for|with|in|over|to|after|of)\b|[,:;]|$)', title)
    parts = [m.group(1)] if m else re.split(r',\s*|\s+and\s+', title)
    return [p.strip(' .') for p in parts if len(p.strip()) >= 3][:4]


def sec_rows(kind, items, names):
    out = []
    for it in items:
        if not it['link']:
            continue
        cos = named_companies(it['title'])
        tickers = [t for t in dict.fromkeys(names.lookup(c) for c in cos) if t]
        if kind == 'sec_release' and not re.search(r'(?i)charg|settl|judgment|fraud|bars|penalt|suspend|enforcement', it['title']):
            continue                                       # rule proposals, meetings: not company news
        out.append({'id': uid(it['link']), 'source': 'SEC', 'kind': kind, 'title': it['title'][:240], 'url': it['link'],
                    'published': it['published'], 'company': ', '.join(cos)[:120] if tickers else '', 'tickers': tickers,
                    'match': 'company name' if tickers else '', 'release': it.get('creator', '')})
    return out


def fda_press_rows(items, names):
    out = []
    for it in items:
        if not it['link'] or not re.search(r'(?i)approv|authoriz|clear|recall|warning', it['title']):
            continue
        t = [x for x in dict.fromkeys(names.lookup(c) for c in re.findall(r"\b([A-Z][A-Za-z&.'-]+(?: [A-Z][A-Za-z&.'-]+){0,3})(?:'s)?\b", it['title'])) if x]
        out.append({'id': uid(it['link']), 'source': 'FDA', 'kind': 'fda', 'title': it['title'][:240], 'url': it['link'],
                    'published': it['published'], 'company': '', 'tickers': t[:2], 'match': 'company name' if t else ''})
    return out


def store(root):
    return Shards(Path(root) / 'cache' / 'news', date='published', uid='id', size=10)


def collect(client, root, cfg=None, today=None):
    cfg = cfg or {}
    today = today or dt.date.today()
    names = Names(root)
    shards = store(root)
    have = shards.uids()
    state = read_json(Path(root) / 'cache' / 'news' / 'state.json', {})
    src, added, skipped = {}, 0, {}
    oldest = (today - dt.timedelta(days=int(cfg.get('keep_days', 60)))).isoformat()

    def keep(rows, label):
        nonlocal added
        n = 0
        for r in rows:
            if r['published'] and r['published'] >= oldest and r['id'] not in have:
                shards.add(r)
                have.add(r['id'])
                n += 1
        added += n
        src[label] = {'ok': now(), 'items': len(rows), 'new': n}

    for url in PRN:
        label = 'PR Newswire ' + url.rsplit('/', 1)[-1].replace('-list.rss', '').replace('.rss', '')
        try:
            rows, sk = prn_rows(rss_items(client.get(url, headers={'Accept': 'application/rss+xml, application/xml'})), names)
            for k, v in sk.items():
                skipped[k] = skipped.get(k, 0) + v
            keep(rows, label)
        except Exception as exc:
            src[label] = {**state.get('sources', {}).get(label, {}), 'error': str(exc)[:160], 'tried': now()}
    a = (today - dt.timedelta(days=int(cfg.get('fda_days', 10)))).strftime('%Y%m%d')
    try:
        keep(fda_rows(client.json(OPENFDA.format(a=a, b=today.strftime('%Y%m%d'))), names, a), 'openFDA approvals')
    except Exception as exc:
        src['openFDA approvals'] = {'error': str(exc)[:160], 'tried': now()}
    try:
        keep(fda_press_rows(rss_items(client.get(FDA_PRESS)), names), 'FDA press releases')
    except Exception as exc:
        src['FDA press releases'] = {'error': str(exc)[:160], 'tried': now()}
    for kind, url in SEC_FEEDS:
        label = 'SEC ' + url.split('/')[-2 if url.endswith('/rss') else -1].replace('.rss', '')
        try:
            keep(sec_rows(kind, rss_items(client.get(url, sec=True)), names), label)
        except Exception as exc:
            src[label] = {'error': str(exc)[:160], 'tried': now()}
    shards.save(keep=oldest)
    write_json(Path(root) / 'cache' / 'news' / 'state.json', {'sources': src, 'skipped': skipped, 'updated_at': now()})
    errors = [k for k, v in src.items() if v.get('error')]
    return {'status': 'ok' if not errors else 'partial', 'added': added, 'on_file': len(have), 'failed_sources': errors,
            'skipped': skipped, 'updated_at': now()}


def publish(root, out_dir, today=None, days=7):
    today = today or dt.date.today()
    shards = store(root)
    if not shards.rows:
        return None
    since = (today - dt.timedelta(days=days)).isoformat()
    rows = [r for r in shards.all() if (r.get('published') or '') >= since][:3000]
    data = {'generated_at': now(), 'on_file': len(shards.uids()), 'since': since,
            'note': ('Headlines with their time and link, from PR Newswire, openFDA (new drug and biologic approvals), the FDA '
                     'press releases and the SEC (enforcement, trading suspensions). Tickers come from the exchange tag in a '
                     'release whose issuer matches the listed company, or from an exact company-name match. A headline is the '
                     'source’s own words, not a verified fact; open the link for the text. Law-firm class-action notices are left out.'),
            'rows': rows}
    path = Path(out_dir) / 'news.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)
    return {'rows': len(rows), 'with_ticker': sum(1 for r in rows if r.get('tickers'))}


def by_ticker(root, n=10):
    out = {}
    for r in store(root).all():
        for t in r.get('tickers') or []:
            if len(out.setdefault(t, [])) < n:
                out[t].append({k: r.get(k) for k in ('published', 'source', 'kind', 'title', 'url') if r.get(k)})
    return out
