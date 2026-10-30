"""Beyond the filings: what free public data says about a company outside its 10-Q and 10-K (Disclosures → Beyond the
filings, and the "Beyond the filings" view of each company page). Kept on the branch "research-outside" by
.github/workflows/research-outside.yml; scan.yml publishes its public/ at disclosures/data/research/outside/.

  trials     ClinicalTrials.gov (API v2, no key): the studies a drug, biotech or device company sponsors — the pipeline by
             phase, what is recruiting, the primary completions due (catalysts), conditions.
  recalls    openFDA enforcement reports (drugs, devices, food), CPSC consumer-product recalls (saferproducts.gov) and
             NHTSA vehicle recalls (data.transportation.gov), matched to companies by name.
  fedreg     the Federal Register (no key): rules, proposed rules and notices that name the company, by agency.
  fec        OpenFEC (an api.data.gov key, DATA_GOV_API_KEY): the company's political action committee — money raised and
             spent this cycle and the one before, the largest recipients.
  complaints CFPB consumer complaint database (no key): complaints filed against banks, card issuers, lenders, servicers
             and fintechs — five trailing years, products, issues, how the company responded, relief given.
  environment EPA ECHO exporter (weekly bulk file, no key): the company's active regulated facilities, matched by name —
             significant violators, facilities in violation, inspections, formal enforcement actions and penalties over five
             years, greenhouse-gas (CO2e) and toxic (TRI) releases.
  wiki       Wikipedia page views (Wikimedia REST, no key; the article from Wikidata's SEC CIK property P5531): attention.
  costs      cost shocks (FRED: oil, natural gas, diesel, jet fuel, electricity, wages, steel, copper): how each sector's
             and company's margins have moved with each input, year on year, and what a shock would do.

Names are matched conservatively (whole words, a company's distinctive name; a short list of known subsidiaries and
brands), and every match keeps the source's own name so a reader can check it. Missing is not zero: a company with no
match shows nothing, not "no recalls".

    python disclosures/app/outside.py collect --root ro --site-index site/index.json --minutes 40
    python disclosures/app/outside.py build --root ro --site-index site/index.json --frames-root disclosures/docs/data
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402

UA = 'FilingFlows/1.0 (https://filing-flows.com; filingflows@gmail.com) public-data research'
PHARMA_SIC = set(range(2833, 2837)) | set(range(3841, 3846)) | {8731, 5122}
FDA_SIC = PHARMA_SIC | set(range(2000, 2100)) | set(range(2840, 2845)) | {5912, 5141, 5149, 2086, 2111}
VEHICLE_SIC = {3711, 3713, 3714, 3715, 3716, 3751, 3799, 5012, 5013, 3519, 3531}
TRIAL_ACTIVE = {'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'NOT_YET_RECRUITING', 'ENROLLING_BY_INVITATION'}
PHASES = ['EARLY_PHASE1', 'PHASE1', 'PHASE2', 'PHASE3', 'PHASE4']
SUFFIX = r'\b(the|inc|incorporated|corp|corporation|company|co|plc|ltd|limited|group|holdings?|n ?v|s ?a|ag|se|lp|llc|class [a-z]|common stock|new|de|the)\b'
# brands and subsidiaries that recall under their own name: source name key → ticker
ALIASES = {
    'chrysler': 'STLA', 'fca us': 'STLA', 'stellantis': 'STLA', 'jeep': 'STLA', 'ram trucks': 'STLA', 'jayco': 'THO', 'airstream': 'THO',
    'keystone rv': 'THO', 'heartland recreational vehicles': 'THO', 'dutchmen': 'THO', 'kenworth': 'PCAR', 'peterbilt': 'PCAR',
    'gmc': 'GM', 'chevrolet': 'GM', 'cadillac': 'GM', 'buick': 'GM', 'general motors': 'GM', 'ford motor': 'F', 'lincoln motor': 'F',
    'tesla': 'TSLA', 'rivian': 'RIVN', 'lucid': 'LCID', 'harley davidson': 'HOG', 'winnebago': 'WGO', 'grand design': 'WGO', 'newmar': 'WGO',
    'polaris': 'PII', 'indian motorcycle': 'PII', 'oshkosh': 'OSK', 'pierce manufacturing': 'OSK', 'blue bird': 'BLBD', 'toyota': 'TM',
    'honda': 'HMC', 'american honda': 'HMC', 'nissan': 'NSANY', 'navistar': 'TRATON', 'thor motor coach': 'THO', 'forest river': 'BRK-B',
    'janssen': 'JNJ', 'ethicon': 'JNJ', 'depuy': 'JNJ', 'biosense webster': 'JNJ', 'kenvue': 'KVUE', 'hospira': 'PFE', 'pfizer': 'PFE',
    'abbott': 'ABT', 'medtronic': 'MDT', 'covidien': 'MDT', 'baxter': 'BAX', 'becton dickinson': 'BDX', 'bd': 'BDX', 'boston scientific': 'BSX',
    'stryker': 'SYK', 'zimmer': 'ZBH', 'philips': 'PHG', 'teva': 'TEVA', 'viatris': 'VTRS', 'mylan': 'VTRS', 'fresenius kabi': 'FMS',
    'hikma': 'HIK', 'amneal': 'AMRX', 'sun pharmaceutical': 'SUN', 'procter gamble': 'PG', 'kimberly clark': 'KMB', 'colgate palmolive': 'CL',
    'general mills': 'GIS', 'kraft heinz': 'KHC', 'conagra': 'CAG', 'tyson': 'TSN', 'hormel': 'HRL', 'smucker': 'SJM', 'campbell': 'CPB',
    'mondelez': 'MDLZ', 'pepsico': 'PEP', 'frito lay': 'PEP', 'quaker oats': 'PEP', 'coca cola': 'KO', 'nestle': 'NSRGY', 'kellanova': 'K',
    'walmart': 'WMT', 'target corporation': 'TGT', 'costco': 'COST', 'home depot': 'HD', 'lowe s': 'LOW', 'amazon': 'AMZN', 'best buy': 'BBY',
    'hasbro': 'HAS', 'mattel': 'MAT', 'fisher price': 'MAT', 'newell': 'NWL', 'graco': 'NWL', 'stanley black decker': 'SWK', 'whirlpool': 'WHR',
    'modernatx': 'MRNA', 'genentech': None, 'merck sharp dohme': 'MRK', 'bristol myers': 'BMY', 'celgene': 'BMY', 'allergan': 'ABBV', 'pharmacyclics': 'ABBV',
    'kite pharma': 'GILD', 'alexion': 'AZN', 'lg electronics': 'LGEAF', 'samsung': 'SSNLF', 'peloton': 'PTON', 'ikea': None,
}


# ---------------------------------------------------------------- http
def get(url, params=None, headers=None, timeout=60, tries=4, pause=0.0):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params, doseq=True)
    h = {'User-Agent': UA, 'Accept': 'application/json, text/csv;q=0.9, */*;q=0.5', **(headers or {})}
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read()
            if pause:
                time.sleep(pause)
            return body
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}'
            if e.code in (400, 401, 403, 404, 422):
                raise RuntimeError(last) from None
            if k < tries - 1:
                wait = e.headers.get('Retry-After', '')
                time.sleep(min(60, int(wait) if wait.isdigit() else 2 ** (k + 1)))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(e)[:120]
            time.sleep(2 ** k)
    raise RuntimeError(last or 'request failed')


def get_json(url, params=None, **kw):
    return json.loads(get(url, params, **kw))


# ---------------------------------------------------------------- companies and names
GENERIC = r'\b(laboratories|labs|pharmaceuticals?|pharma|therapeutics|biosciences|bioscience|biotherapeutics|biopharma|medical|sciences|' \
          r'international|technologies|technology|industries|enterprises|worldwide|global|incorporated|research development)\b'


def norm(s):
    s = re.sub(r'\s*/\s*[a-z]{1,4}\b/?', ' ', re.sub(r'\(.*?\)', ' ', str(s or '').lower())).replace('&', ' ')
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(SUFFIX, ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


COMMON = {'united', 'american', 'general', 'first', 'national', 'north', 'south', 'west', 'east', 'pacific', 'atlantic', 'central', 'western',
          'southern', 'northern', 'eastern', 'universal', 'standard', 'great', 'royal', 'premier', 'advanced', 'applied', 'integrated', 'capital',
          'summit', 'pioneer', 'liberty', 'atlas', 'alpha', 'omega', 'delta', 'apex', 'vista', 'precision', 'innovative', 'allied', 'consolidated',
          'continental', 'federal', 'mutual', 'trans', 'inter', 'bio', 'gen', 'life', 'health', 'care', 'medical', 'smart', 'digital', 'quantum'}


def core(s):
    """The distinctive part of a name: 'abbott laboratories' → 'abbott', 'vertex pharmaceuticals' → 'vertex' — but never a
    lone common word ('united therapeutics' stays whole, or it would match United Dairy Farmers)."""
    k = norm(s)
    c = re.sub(r'\s+', ' ', re.sub(GENERIC, ' ', k)).strip()
    if len(c) < 4 or c in COMMON:
        return k
    return c


def same(a, b):
    """Two names for the same company: equal cores, or one core the other followed by more words."""
    ca, cb = core(a), core(b)
    return bool(ca and cb) and (ca == cb or ca.startswith(cb + ' ') or cb.startswith(ca + ' '))


def display_name(name):
    """'LOCKHEED MARTIN CORP' → 'Lockheed Martin'; 'Apple Inc.' → 'Apple Inc' (a one-word name keeps its suffix, which
    keeps a search for 'Apple' from returning every notice about apples)."""
    raw = re.sub(r'\s+', ' ', re.sub(r'[,.]', ' ', re.sub(r'\s*/\s*[A-Za-z]{1,4}\b/?', ' ', str(name or '')))).strip()
    words = raw.split(' ')
    keep = [w for w in words if not re.fullmatch(SUFFIX, w.lower())]
    if not keep:
        return raw
    if len(keep) == 1:
        suf = next((w for w in words[1:] if re.fullmatch(r'(?i)inc|corp|corporation|co|company|plc|ltd|n\.?v', w)), '')
        out = keep[0] + (' ' + suf if suf else '')
    else:
        out = ' '.join(keep)
    if out.isupper():                                 # 'LOCKHEED MARTIN' → 'Lockheed Martin'; short acronyms stay: 'AES Corp'
        out = ' '.join(w if len(w) <= 3 and w.isalpha() and len(out.split()) <= 2 else w.title() for w in out.split())
    return out


def universe(site_index):
    """[{cik, ticker, name, key, sector, sic, revenue}] from the site's index.json."""
    d = read_json(site_index, {}) or {}
    out = []
    for c in (d.get('companies') or []):
        try:
            sic = int(c.get('sic') or 0)
        except (TypeError, ValueError):
            sic = 0
        key = norm(c.get('name'))
        if not key or not c.get('cik') or not c.get('ticker'):
            continue
        out.append({'cik': int(c['cik']), 'ticker': c['ticker'], 'name': c.get('name') or c['ticker'], 'key': key, 'core': core(c.get('name')), 'sector': c.get('sector') or 'other',
                    'industry': c.get('industry'), 'sic': sic, 'revenue': c.get('revenue') or 0, 'display': display_name(c.get('name'))})
    return out


def matcher(companies, extra=None):
    """A function source-name → company (or None): the company whose name key starts the source's name key (longest
    key wins; at least five letters or two words, so 'AT' or 'GE' alone never match), else an alias."""
    keys = {}
    for c in companies:
        for k in (c['key'], c.get('core') or c['key']):
            if len(k) >= 5 or ' ' in k:
                keys.setdefault(k, c)
    by_t = {c['ticker']: c for c in companies}
    order = sorted(keys, key=len, reverse=True)
    alias = sorted([(k, t) for k, t in ALIASES.items() if t] + [(norm(k), t) for k, t in (extra or {}).items() if t], key=lambda x: -len(x[0]))

    def find(src):
        s = norm(src)
        if not s:
            return None
        cs = core(src)
        for k in order:
            if cs == k or cs.startswith(k + ' '):
                return keys[k]
        for k in order:
            if s == k or s.startswith(k + ' '):
                return keys[k]
        for k, t in alias:
            if (s == k or s.startswith(k + ' ')) and t in by_t:
                return by_t[t]
        return None
    return find


# ---------------------------------------------------------------- Wikipedia attention
SPARQL = ('SELECT ?cik ?article WHERE { ?item wdt:P5531 ?cik . ?article schema:about ?item ; '
          'schema:isPartOf <https://en.wikipedia.org/> . }')


def wiki_map(root, fetch=get_json, max_age_days=7):
    p = Path(root) / 'cache' / 'wiki_map.json'
    m = read_json(p, None)
    if m and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(m['at'])).days < max_age_days:
        return m['map']
    d = fetch('https://query.wikidata.org/sparql', {'query': SPARQL, 'format': 'json'}, headers={'Accept': 'application/sparql-results+json'})
    out = {}
    for b in d['results']['bindings']:
        cik = b['cik']['value'].lstrip('0')
        title = urllib.parse.unquote(b['article']['value'].rsplit('/wiki/', 1)[-1])
        if cik.isdigit():
            out.setdefault(cik, title)
    write_json(p, {'at': now(), 'map': out})
    return out


def pageviews(root, companies, wmap, budget_s, start='2024-01-01', fetch=None, today=None, pause=0.6, daily_top=400, every_days=7):
    """Daily views per company article, kept in cache/views/<cik>.json and topped up: the largest companies every day,
    the rest once a week (Wikimedia limits how fast one address may ask; the run stops for the day when it says so)."""
    today = today or dt.date.today()
    fetch = fetch or (lambda url: get_json(url, tries=1, pause=pause))
    end = (today - dt.timedelta(days=1)).isoformat()
    t0, done, fails, limited = time.time(), 0, 0, 0
    folder = Path(root) / 'cache' / 'views'
    folder.mkdir(parents=True, exist_ok=True)
    ranked = sorted(companies, key=lambda c: -(c['revenue'] or 0))
    top = {c['cik'] for c in ranked[:daily_top]}
    cands = []
    for c in ranked:
        title = wmap.get(str(c['cik']))
        if not title:
            continue
        d = read_json(folder / f"{c['cik']}.json", {}) or {}
        last = max(d.get('days') or {'': 0}) or None
        stale = (today - dt.date.fromisoformat(last)).days if last else 10 ** 6
        if stale > (1 if c['cik'] in top else every_days):
            cands.append((-stale, c))
    cands.sort(key=lambda x: x[0])
    for _, c in cands:
        title = wmap.get(str(c['cik']))
        if not title:
            continue
        p = folder / f"{c['cik']}.json"
        d = read_json(p, {'article': title, 'days': {}})
        if d.get('article') != title:
            d = {'article': title, 'days': {}}
        last = max(d['days']) if d['days'] else None
        frm = (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat() if last else start
        if frm > end:
            continue
        if time.time() - t0 > budget_s:
            break
        url = ('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/'
               + urllib.parse.quote(title.replace(' ', '_'), safe='') + f"/daily/{frm.replace('-', '')}/{end.replace('-', '')}")
        try:
            items = fetch(url).get('items') or []
            limited = 0
        except RuntimeError as e:
            if '429' in str(e):
                limited += 1
                if limited >= 5:
                    break                                 # asked to slow down: the rest wait for the next run
                time.sleep(20)
                continue
            if '404' not in str(e):
                fails += 1
            items = []
        for it in items:
            ts = it.get('timestamp', '')
            if len(ts) >= 8:
                d['days'][f'{ts[:4]}-{ts[4:6]}-{ts[6:8]}'] = it.get('views', 0)
        write_json(p, d)
        done += 1
    return {'updated': done, 'failed': fails, 'waiting': max(0, len(cands) - done), 'rate_limited': limited >= 5}


def attention(days, today=None):
    """Weekly views (Monday-based weeks), the last 7 days against the 90 before, the biggest days of the last year."""
    if not days:
        return None
    ds = sorted(days)
    last = dt.date.fromisoformat(ds[-1])
    val = lambda d: days.get(d.isoformat(), 0)     # noqa: E731
    l7 = sum(val(last - dt.timedelta(days=i)) for i in range(7)) / 7
    base = [val(last - dt.timedelta(days=i)) for i in range(7, 97)]
    b90 = sum(base) / len(base) if base else 0
    weeks = {}
    for d in ds:
        dd = dt.date.fromisoformat(d)
        wk = (dd - dt.timedelta(days=dd.weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0) + days[d]
    yr = [(d, days[d]) for d in ds if d >= (last - dt.timedelta(days=365)).isoformat()]
    peaks = sorted(yr, key=lambda x: -x[1])[:5]
    return {'last': ds[-1], 'avg7': round(l7), 'avg90': round(b90), 'ratio': round(l7 / b90, 2) if b90 else None,
            'avg365': round(sum(v for _, v in yr) / len(yr)) if yr else None, 'weeks': [[w, v] for w, v in sorted(weeks.items())][-110:],
            'peaks': peaks}


# ---------------------------------------------------------------- ClinicalTrials.gov
CT_FIELDS = ('NCTId,BriefTitle,Phase,OverallStatus,PrimaryCompletionDate,StartDate,LeadSponsorName,Condition,InterventionName,'
             'EnrollmentCount,LastUpdatePostDate,StudyType')


def own_names(company):
    """The names a company's studies and recalls appear under: its own and its listed brands and subsidiaries."""
    return [company.get('core') or company['key']] + [k for k, t in ALIASES.items() if t == company['ticker'] and k != (company.get('core') or company['key'])]


def trials_fetch(company, fetch=get_json):
    """Every study whose lead sponsor is the company or one of its subsidiaries (ClinicalTrials.gov's sponsor search,
    then our own name check)."""
    out, seen = [], set()
    for q in own_names(company):
        out += _trials_query(company, q, seen, fetch)
    return out


def _trials_query(company, q, seen, fetch):
    out, token = [], None
    names = own_names(company)
    for _ in range(20):
        params = {'query.lead': q, 'pageSize': 1000, 'fields': CT_FIELDS, 'format': 'json'}
        if token:
            params['pageToken'] = token
        d = fetch('https://clinicaltrials.gov/api/v2/studies', params)
        for s in d.get('studies') or []:
            p = s.get('protocolSection') or {}
            lead = ((p.get('sponsorCollaboratorsModule') or {}).get('leadSponsor') or {}).get('name') or ''
            nct = (p.get('identificationModule') or {}).get('nctId')
            if nct in seen or not any(same(lead, n) for n in names):
                continue
            seen.add(nct)
            st, ds, cm = p.get('statusModule') or {}, p.get('designModule') or {}, p.get('conditionsModule') or {}
            out.append({'id': (p.get('identificationModule') or {}).get('nctId'), 'title': (p.get('identificationModule') or {}).get('briefTitle'),
                        'phases': ds.get('phases') or [], 'type': ds.get('studyType'), 'status': st.get('overallStatus'),
                        'pcd': (st.get('primaryCompletionDateStruct') or {}).get('date'), 'start': (st.get('startDateStruct') or {}).get('date'),
                        'updated': (st.get('lastUpdatePostDateStruct') or {}).get('date'), 'n': (ds.get('enrollmentInfo') or {}).get('count'),
                        'conditions': (cm.get('conditions') or [])[:4], 'drugs': [i.get('name') for i in ((p.get('armsInterventionsModule') or {}).get('interventions') or [])][:4],
                        'sponsor': lead})
        token = d.get('nextPageToken')
        if not token:
            break
    return out


def _phase(ph):
    """The highest phase of a study ('PHASE2/PHASE3' counts as phase 3); None for observational studies."""
    best = None
    for p in ph or []:
        if p in PHASES and (best is None or PHASES.index(p) > PHASES.index(best)):
            best = p
    return best


def trials_summary(studies, today=None):
    today = (today or dt.date.today()).isoformat()
    if not studies:
        return None
    active = [s for s in studies if s['status'] in TRIAL_ACTIVE]
    by = {p: {'active': 0, 'all': 0} for p in PHASES}
    for s in studies:
        p = _phase(s['phases'])
        if p:
            by[p]['all'] += 1
            if s['status'] in TRIAL_ACTIVE:
                by[p]['active'] += 1
    horizon = (dt.date.fromisoformat(today) + dt.timedelta(days=550)).isoformat()
    due = [s for s in active if s.get('pcd') and today[:7] <= s['pcd'][:10] <= horizon and _phase(s['phases']) in ('PHASE2', 'PHASE3')]
    due.sort(key=lambda s: (s['pcd'], -PHASES.index(_phase(s['phases']))))
    recent = [s for s in studies if s['status'] == 'COMPLETED' and s.get('pcd') and s['pcd'] >= str(int(today[:4]) - 2)]
    cond = {}
    for s in active:
        for c in s['conditions']:
            cond[c] = cond.get(c, 0) + 1
    slim = lambda s: [s['id'], (s['title'] or '')[:120], _phase(s['phases']), s['status'], s.get('pcd'), s.get('n'), ', '.join(s['conditions'][:2])[:80], ', '.join(d for d in s['drugs'] if d)[:80]]  # noqa: E731
    return {'studies': len(studies), 'active': len(active), 'phases': by, 'completed_2y': len(recent),
            'enrollment_active': sum(s['n'] or 0 for s in active), 'conditions': sorted(cond.items(), key=lambda x: -x[1])[:10],
            'due': [slim(s) for s in due[:25]], 'sponsor': studies[0]['sponsor'],
            'fields': ['id', 'title', 'phase', 'status', 'primary_completion', 'enrollment', 'conditions', 'interventions']}


# ---------------------------------------------------------------- recalls
def fda_recalls(company, since, fetch=get_json):
    out = []
    q = (company.get('core') or company['key']).replace('"', '')
    for kind in ('drug', 'device', 'food'):
        rows = []
        for skip in range(0, 1000, 100):                  # up to a thousand reports a kind, newest first
            params = {'search': f'recalling_firm:"{q}" AND report_date:[{since.replace("-", "")} TO 29991231]', 'limit': 100, 'skip': skip, 'sort': 'report_date:desc'}
            try:
                d = fetch(f'https://api.fda.gov/{kind}/enforcement.json', params)
            except RuntimeError as e:
                if '404' in str(e):
                    break
                raise
            got = d.get('results') or []
            rows += got
            if len(got) < 100 or skip + 100 >= ((d.get('meta') or {}).get('results') or {}).get('total', 0):
                break
        for r in rows:
            if not any(same(r.get('recalling_firm'), n) for n in own_names(company)):
                continue
            rd = r.get('report_date') or ''
            out.append({'source': 'FDA ' + kind, 'date': f'{rd[:4]}-{rd[4:6]}-{rd[6:8]}' if len(rd) == 8 else rd, 'class': r.get('classification'),
                        'firm': r.get('recalling_firm'), 'what': (r.get('product_description') or '')[:160], 'why': (r.get('reason_for_recall') or '')[:200],
                        'status': r.get('status'), 'id': r.get('recall_number')})
    return out


def cpsc_all(since, fetch=get_json):
    return fetch('https://www.saferproducts.gov/RestWebServices/Recall', {'format': 'json', 'RecallDateStart': since}) or []


def cpsc_match(recalls, find):
    out = {}
    for r in recalls:
        names = []
        for k in ('Manufacturers', 'Importers', 'Distributors'):
            names += [x.get('Name') for x in r.get(k) or [] if x.get('Name')]
        hit = None
        for n in names:
            hit = find(n)
            if hit:
                break
        if not hit:
            continue
        out.setdefault(hit['cik'], []).append({'source': 'CPSC', 'date': (r.get('RecallDate') or '')[:10], 'class': None, 'firm': ', '.join(names)[:120],
                                               'what': (r.get('Title') or '')[:200], 'why': ', '.join(h.get('Name', '') for h in r.get('Hazards') or [])[:200],
                                               'units': ', '.join(p.get('NumberOfUnits', '') for p in r.get('Products') or [] if p.get('NumberOfUnits'))[:60],
                                               'id': r.get('RecallNumber'), 'url': r.get('URL')})
    return out


def nhtsa_all(since, fetch=get_json, page=50000):
    rows, off = [], 0
    while True:
        d = fetch('https://datahub.transportation.gov/resource/6axg-epim.json',
                  {'$where': f"report_received_date >= '{since}'", '$order': 'report_received_date DESC', '$limit': page, '$offset': off})
        rows += d
        if len(d) < page:
            return rows
        off += page


def nhtsa_match(rows, find):
    out = {}
    for r in rows:
        hit = find(r.get('manufacturer'))
        if not hit:
            continue
        try:
            units = int(r.get('potentially_affected') or 0)
        except ValueError:
            units = 0
        out.setdefault(hit['cik'], []).append({'source': 'NHTSA', 'date': (r.get('report_received_date') or '')[:10], 'class': r.get('component'),
                                               'firm': r.get('manufacturer'), 'what': (r.get('subject') or '')[:200], 'why': (r.get('consequence_summary') or '')[:200],
                                               'units': units, 'id': r.get('nhtsa_id'), 'url': ((r.get('recall_link') or {}).get('url'))})
    return out


def recalls_summary(items, today=None):
    if not items:
        return None
    today = today or dt.date.today()
    y1 = (today - dt.timedelta(days=365)).isoformat()
    items = sorted(items, key=lambda x: x['date'], reverse=True)
    by_year = {}
    for x in items:
        by_year[x['date'][:4]] = by_year.get(x['date'][:4], 0) + 1
    return {'n': len(items), 'last_12m': sum(1 for x in items if x['date'] >= y1), 'class1': sum(1 for x in items if x.get('class') == 'Class I'),
            'units_12m': sum(x['units'] for x in items if isinstance(x.get('units'), int) and x['date'] >= y1),
            'by_year': sorted(by_year.items()), 'by_source': {s: sum(1 for x in items if x['source'] == s) for s in sorted({x['source'] for x in items})},
            'latest': items[:25]}


# ---------------------------------------------------------------- Federal Register
def fedreg(company, since, fetch=get_json):
    params = [('conditions[term]', f'"{company["display"]}"'), ('conditions[publication_date][gte]', since), ('per_page', 20), ('order', 'newest')]
    params += [('fields[]', f) for f in ('title', 'type', 'agencies', 'publication_date', 'html_url', 'document_number')]
    d = fetch('https://www.federalregister.gov/api/v1/documents.json', params)
    docs = d.get('results') or []
    by_type, agencies = {}, {}
    for x in docs:
        by_type[x.get('type')] = by_type.get(x.get('type'), 0) + 1
        for a in x.get('agencies') or []:
            n = a.get('name') or a.get('raw_name')
            if n:
                agencies[n] = agencies.get(n, 0) + 1
    return {'count': d.get('count') or 0, 'since': since, 'by_type_recent': by_type, 'agencies_recent': sorted(agencies.items(), key=lambda x: -x[1])[:8],
            'docs': [[x.get('publication_date'), x.get('type'), ', '.join(a.get('name') or a.get('raw_name') or '' for a in x.get('agencies') or [] if a)[:80],
                      (x.get('title') or '')[:160], x.get('html_url')] for x in docs[:10]], 'query': company['display']}


# ---------------------------------------------------------------- OpenFEC
FEC = 'https://api.open.fec.gov/v1'


def fec(company, key, cycles, fetch=get_json):
    """The company's connected PAC(s): committees of corporations whose connected organization (or name) is the company."""
    d = fetch(f'{FEC}/committees/', {'api_key': key, 'q': company['display'], 'per_page': 20})
    pacs = []
    for c in d.get('results') or []:
        org = norm(c.get('affiliated_committee_name') or '')
        nm = norm(c.get('name') or '')
        ok_org = org and (org == company['key'] or org.startswith(company['key'] + ' '))
        ok_name = nm.startswith(company['key'] + ' ') and re.search(r'political action|pac\b|employee', nm)
        if c.get('committee_type') in ('Q', 'N') and (ok_org or ok_name) and (c.get('organization_type') in ('C', None, '')):
            pacs.append(c)
    if not pacs:
        return None
    out = {'pacs': [], 'cycles': {}}
    for c in pacs[:3]:
        out['pacs'].append([c['committee_id'], c.get('name'), c.get('affiliated_committee_name')])
        for cy in cycles:
            t = fetch(f"{FEC}/committee/{c['committee_id']}/totals/", {'api_key': key, 'cycle': cy, 'per_page': 1})
            r = (t.get('results') or [{}])[0] if t.get('results') else {}
            if not r:
                continue
            agg = out['cycles'].setdefault(str(cy), {'receipts': 0, 'disbursements': 0, 'to_candidates': 0, 'cash': 0})
            agg['receipts'] += r.get('receipts') or 0
            agg['disbursements'] += r.get('disbursements') or 0
            agg['to_candidates'] += (r.get('fed_candidate_committee_contributions') or r.get('contributions_to_other_committees') or 0)
            agg['cash'] += r.get('last_cash_on_hand_end_period') or r.get('cash_on_hand_end_period') or 0
    top = {}
    try:
        b = fetch(f'{FEC}/schedules/schedule_b/by_recipient/', {'api_key': key, 'committee_id': [p[0] for p in out['pacs']], 'cycle': cycles[0],
                                                               'per_page': 15, 'sort': '-total'})
        for r in b.get('results') or []:
            n = r.get('recipient_name')
            if n:
                top[n] = top.get(n, 0) + (r.get('total') or 0)
    except RuntimeError:
        pass
    out['top_recipients'] = sorted(top.items(), key=lambda x: -x[1])[:12]
    return out


# ---------------------------------------------------------------- CFPB consumer complaints
CFPB = 'https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/'
# the names complaints are filed under → ticker (banks file as their bank, lenders as their servicer)
CFPB_ALIASES = {
    'citibank': 'C', 'citigroup': 'C', 'synchrony': 'SYF', 'u s bancorp': 'USB', 'us bancorp': 'USB', 'u s bank': 'USB', 'pnc bank': 'PNC',
    'pnc financial': 'PNC', 'discover bank': 'COF', 'discover financial': 'COF', 'td bank': 'TD', 'santander': 'SAN', 'barclays bank': 'BCS',
    'rocket mortgage': 'RKT', 'quicken loans': 'RKT', 'nationstar mortgage': 'RKT', 'mr cooper': 'RKT', 'ocwen': 'ONIT', 'onity': 'ONIT',
    'phh mortgage': 'ONIT', 'nelnet': 'NNI', 'regions': 'RF', 'fifth third': 'FITB', 'huntington national bank': 'HBAN', 'huntington bancshares': 'HBAN',
    'm t bank': 'MTB', 'toyota motor credit': 'TM', 'american honda finance': 'HMC', 'lendingclub': 'LC', 'lending club': 'LC', 'credit karma': 'INTU',
    'wells fargo': 'WFC', 'jpmorgan': 'JPM', 'charles schwab': 'SCHW', 'hsbc': 'HSBC', 'bmo harris': 'BMO', 'comerica': 'CMA', 'zions': 'ZION',
    'webster bank': 'WBS', 'east west bank': 'EWBC', 'first horizon': 'FHN', 'navient': 'NAVI', 'sallie mae': 'SLM', 'green dot': 'GDOT',
    'marqeta': 'MQ', 'dave operating': 'DAVE', 'moneylion': 'ML', 'lendingtree': 'TREE', 'loandepot': 'LDI', 'united wholesale mortgage': 'UWMC',
    'guild mortgage': 'GHLD', 'pennymac': 'PFSI', 'onemain': 'OMF', 'one main': 'OMF', 'american express': 'AXP', 'visa': 'V', 'mastercard': 'MA',
    'gm financial': 'GM', 'general motors financial': 'GM', 'ford motor credit': 'F', 'harley davidson financial': 'HOG', 'lennar financial': 'LEN',
    'tesla': 'TSLA', 'carmax': 'KMX', 'carvana': 'CVNA', 'toyota financial': 'TM', 'nissan motor acceptance': 'NSANY',
}
CFPB_EXTRA = r'\b(bank|banks|bancorp|bancshares|banc|financial|finance|credit|mortgage|card|cards|n a|national association|securities|markets|usa)\b'


def _fin(c):
    return 6000 <= c['sic'] <= 6799 or 7370 <= c['sic'] <= 7399 or 5500 <= c['sic'] <= 5599


def cfpb_matcher(companies):
    """Complaint company name → listed company, stricter than matcher(): a financial company whose name is the source's
    name, or a large bank or lender whose name starts it and the rest is banking words ('Bank of America, National
    Association'); else a known servicer or captive lender. Credit unions never match."""
    find = matcher(companies)
    by_t = {c['ticker']: c for c in companies}
    al = sorted(((norm(k), t) for k, t in CFPB_ALIASES.items() if t), key=lambda x: -len(x[0]))

    def f(name):
        s = norm(name)
        if not s or re.search(r'\b(credit union|employees|federal credit)\b', s):
            return None
        banking = lambda rest: all(w in ('of', 'and', 'the') for w in re.sub(CFPB_EXTRA, ' ', rest).split())   # noqa: E731
        for k, t in al:
            if (s == k or s.startswith(k + ' ') and (' ' in k or banking(s[len(k):]))) and t in by_t:
                return by_t[t]
        c = find(name)
        if not c or not _fin(c):
            return None
        cs = core(name)
        if cs == c['core'] or s == c['key']:
            return c
        rest = s[len(c['key']):] if s.startswith(c['key'] + ' ') else (cs[len(c['core']):] if cs.startswith(c['core'] + ' ') else '')
        if (c['core'].split(' ')[0] not in COMMON and 6000 <= c['sic'] <= 6799 and (c['revenue'] or 0) >= 1e9 and rest.strip()
                and banking(rest)):
            return c
        return None
    return f


def _buckets(aggs, k):
    a = (aggs or {}).get(k) or {}
    return (a.get(k) or a).get('buckets') or []


def cfpb_windows(today, years=5):
    """Trailing twelve-month windows, newest first: [(start, end), ...]."""
    out, end = [], today
    for _ in range(years):
        start = end - dt.timedelta(days=365)
        out.append((start.isoformat(), end.isoformat()))
        end = start - dt.timedelta(days=1)
    return out


def cfpb_counts(start, end, fetch=get_json):
    d = fetch(CFPB, {'size': 0, 'date_received_min': start, 'date_received_max': end}, timeout=120)
    return {x['key']: x['doc_count'] for x in _buckets(d.get('aggregations'), 'company')}


def cfpb_detail(names, start, end, fetch=get_json):
    d = fetch(CFPB, [('size', 0), ('date_received_min', start), ('date_received_max', end)] + [('company', n) for n in names], timeout=120)
    a = d.get('aggregations') or {}
    top = lambda k, n=6: [[x['key'], x['doc_count']] for x in _buckets(a, k)[:n]]   # noqa: E731
    return {'total': ((d.get('hits') or {}).get('total') or {}).get('value'), 'products': top('product'), 'issues': top('issue', 8),
            'responses': top('company_response', 8), 'timely': top('timely', 3), 'via': top('submitted_via', 6), 'states': top('state', 8),
            'window': [start, end]}


def cfpb_summary(names, years, detail, revenue):
    """years: [{name: n}] trailing windows newest first."""
    ys = [sum(w.get(n, 0) for n in names) for w in years]
    if not ys or not ys[0]:
        return None
    out = {'names': names, 'last_12m': ys[0], 'prev_12m': ys[1] if len(ys) > 1 else None, 'years': ys[::-1],
           'change': round(ys[0] / ys[1] - 1, 3) if len(ys) > 1 and ys[1] else None,
           'per_bn': round(ys[0] / (revenue / 1e9), 1) if revenue and revenue >= 1e8 else None}
    if detail:
        tot = detail.get('total') or 0
        resp = dict(detail.get('responses') or [])
        tim = dict(detail.get('timely') or [])
        out.update({'products': detail.get('products'), 'issues': detail.get('issues'), 'responses': detail.get('responses'),
                    'relief_share': round((resp.get('Closed with monetary relief', 0)) / tot, 4) if tot else None,
                    'any_relief_share': round((resp.get('Closed with monetary relief', 0) + resp.get('Closed with non-monetary relief', 0)) / tot, 4) if tot else None,
                    'late_share': round(tim.get('No', 0) / tot, 4) if tot else None, 'states': detail.get('states')})
    return out


def cfpb_names(companies, cache, min_n=10):
    """{cik: [complaint company names]} for the companies with at least min_n complaints in the latest window."""
    f = cfpb_matcher(companies)
    counts = cache.get('counts') or []
    out = {}
    for w in counts:
        for name in w:
            c = f(name)
            if c:
                out.setdefault(c['cik'], set()).add(name)
    latest = counts[0] if counts else {}
    return {cik: sorted(ns) for cik, ns in out.items() if sum(latest.get(n, 0) for n in ns) >= min_n}


# ---------------------------------------------------------------- EPA ECHO environmental compliance
ECHO = 'https://echodata.epa.gov/echo/echo_rest_services.'
EPA_ALIASES = {
    'exxonmobil': 'XOM', 'exxon': 'XOM', 'mobil': 'XOM', 'dow chemical': 'DOW', 'dow silicones': 'DOW', 'union carbide': 'DOW',
    'georgia power': 'SO', 'alabama power': 'SO', 'mississippi power': 'SO', 'southern california edison': 'EIX', 'pacific gas electric': 'PCG',
    'consumers energy': 'CMS', 'dte electric': 'DTE', 'detroit edison': 'DTE', 'florida power light': 'NEE', 'appalachian power': 'AEP',
    'indiana michigan power': 'AEP', 'ohio power': 'AEP', 'public service company of colorado': 'XEL', 'northern states power': 'XEL',
    'virginia electric power': 'D', 'dominion energy': 'D', 'commonwealth edison': 'EXC', 'peco energy': 'EXC', 'baltimore gas electric': 'EXC',
    'waste management': 'WM', 'marathon petroleum': 'MPC', 'tesoro': 'MPC', 'valero': 'VLO', 'chevron': 'CVX', 'conocophillips': 'COP',
    'occidental': 'OXY', 'oxy usa': 'OXY', 'anadarko': 'OXY', 'pioneer natural resources': 'XOM', 'devon energy': 'DVN', 'eog resources': 'EOG',
    'noble energy': 'CVX', 'southern california gas': 'SRE', 'san diego gas electric': 'SRE', 'tyson': 'TSN', 'pilgrim s pride': 'PPC', 'dupont': 'DD', 'chemours': 'CC', 'eastman chemical': 'EMN', 'lyondell': 'LYB', 'equistar': 'LYB',
    'nucor': 'NUE', 'steel dynamics': 'STLD', 'cleveland cliffs': 'CLF', 'alcoa': 'AA', 'freeport mcmillan': 'FCX', 'international paper': 'IP',
    'kinder morgan': 'KMI', 'tennessee gas pipeline': 'KMI', 'el paso natural gas': 'KMI', 'williams': 'WMB', 'transcontinental gas': 'WMB',
}
EPA_SECTORS = {'industrials', 'materials', 'consumer-staples', 'utilities', 'energy', 'consumer-disc', 'health', 'technology'}
EPA_ZIP = 'https://echo.epa.gov/files/echodownloads/echo_exporter.zip'
EPA_FIELDS = ['name', 'city', 'state', 'snc', 'qtrs_nc', 'status', 'inspections', 'formal', 'last_formal', 'penalties', 'penalty_n', 'last_penalty',
              'major', 'co2_t', 'tri_lb', 'registry']


def _money(s):
    try:
        return float(re.sub(r'[^0-9.\-]', '', str(s or '')) or 0)
    except ValueError:
        return 0.0


def prefix_matcher(companies, extra=None):
    """matcher()'s rule — a company key is a whole-word prefix of the name's core (else of the whole name), longest first —
    with the aliases in the same table, by dictionary lookup: fast enough for the 1.5 million facilities of the EPA
    exporter. find(name) → (company, the matched key) or (None, '')."""
    keys = {}
    for c in sorted(companies, key=lambda c: -(c['revenue'] or 0)):
        for k in (c['key'], c.get('core') or c['key']):
            if len(k) >= 5 or ' ' in k:
                keys.setdefault(k, c)
    by_t = {c['ticker']: c for c in companies}
    for k, t in list(ALIASES.items()) + [(norm(k), t) for k, t in (extra or {}).items()]:
        if t and t in by_t and (len(k) >= 4 or ' ' in k):
            keys[k] = by_t[t]

    def find(src):
        s = norm(src)
        if not s:
            return None, 0
        for words in (core(src).split(' '), s.split(' ')):
            for n in range(min(len(words), 7), 0, -1):
                k = ' '.join(words[:n])
                hit = keys.get(k)
                if hit:
                    return hit, k
        return None, ''
    return find


def _fam_sic(code):
    try:
        g = int(str(code).strip()[:2])
    except ValueError:
        return None
    return ('ag' if g < 10 else 'mining' if g < 15 else 'constr' if g < 18 else 'manuf' if g < 40 else 'transport' if g < 48 else
            'telecom' if g == 48 else 'util' if g == 49 else 'wholesale' if g < 52 else 'retail' if g < 60 else 'fin' if g < 68 else 'services')


def _fam_naics(code):
    try:
        g = int(str(code).strip()[:2])
    except ValueError:
        return None
    return {11: 'ag', 21: 'mining', 22: 'util', 23: 'constr', 31: 'manuf', 32: 'manuf', 33: 'manuf', 42: 'wholesale', 44: 'retail', 45: 'retail',
            48: 'transport', 49: 'transport', 51: 'telecom', 52: 'fin', 53: 'fin', 72: 'retail'}.get(g, 'services')


FAM_OK = {'mining': {'mining', 'manuf', 'util', 'transport', 'wholesale'}, 'manuf': {'manuf', 'mining', 'wholesale', 'transport', 'util'},
          'util': {'util', 'mining', 'transport', 'manuf', 'constr'}, 'transport': {'transport', 'wholesale', 'retail', 'services'},
          'retail': {'retail', 'wholesale', 'transport', 'services'}, 'wholesale': {'wholesale', 'retail', 'transport', 'manuf'},
          'constr': {'constr', 'manuf', 'mining', 'services'}, 'ag': {'ag', 'manuf', 'wholesale'}, 'telecom': {'telecom', 'services', 'util'},
          'services': {'services', 'telecom', 'transport', 'retail'}, 'fin': {'fin', 'services'}}


# words too ordinary to identify a company on a facility's name by themselves
EPA_STOP = {'industrial', 'northwest', 'northeast', 'southwest', 'southeast', 'midwest', 'heritage', 'frontier', 'century', 'crown', 'castle',
            'harmony', 'sunshine', 'hudson', 'rogers', 'trinity', 'miller', 'williams', 'noble', 'phoenix', 'eagle', 'diamond', 'golden', 'silver',
            'valley', 'river', 'mountain', 'lake', 'park', 'city', 'county', 'state', 'service', 'services', 'environmental', 'energy', 'power',
            'cumberland', 'superior', 'genesis', 'legacy', 'patriot', 'victory', 'triumph', 'compass', 'meridian', 'horizon', 'ascent', 'insight'}


def epa_bulk(zip_path, companies, pick=lambda c: True):
    """{cik: [facility rows]} from the ECHO exporter: active facilities whose name matches a picked company. A match on a
    one-word name ('Williams', 'Crown') also needs the facility's industry codes to be in the company's line of business,
    so Roger Williams Medical Center is not the Williams Companies and an Exxon-branded gas station is not ExxonMobil — and
    an ordinary word never matches alone; nor does one where most facilities named with it are in other industries
    (unless the company is very large: Chevron-branded gas stations outnumber Chevron's own plants)."""
    import csv
    import io
    import zipfile
    find = prefix_matcher(companies, EPA_ALIASES)
    out, seen, kept, pend = {}, {}, {}, []
    with zipfile.ZipFile(zip_path) as z:
        name = next(i.filename for i in z.infolist() if i.filename.lower().endswith('.csv'))
        with z.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', newline='')):
                if r.get('FAC_ACTIVE_FLAG') == 'N' or r.get('FAC_COMPLIANCE_STATUS') == 'Inactive':
                    continue
                c, key = find(r.get('FAC_NAME'))
                if not c or not pick(c):
                    continue
                one = ' ' not in key
                if one:
                    if key in COMMON or key in EPA_STOP:
                        continue
                    seen[key] = seen.get(key, 0) + 1
                    fams = {_fam_sic(x) for x in (r.get('FAC_SIC_CODES') or '').split()} | {_fam_naics(x) for x in (r.get('FAC_NAICS_CODES') or '').split()}
                    fams.discard(None)
                    if not fams & FAM_OK.get(_fam_sic(f"{c['sic']:04d}") or '', set()):
                        continue
                    kept[key] = kept.get(key, 0) + 1
                snc = int(_money(r.get('FAC_PROGRAMS_WITH_SNC'))) > 0 or 'Y' in (r.get('CWA_SNC_FLAG'), r.get('RCRA_SNC_FLAG'), r.get('SDWA_SNC_FLAG'), r.get('CAA_HPV_FLAG'))
                pend.append((c['cik'], key if one else None, [
                    r.get('FAC_NAME'), r.get('FAC_CITY'), r.get('FAC_STATE'), 'Y' if snc else 'N', int(_money(r.get('FAC_QTRS_WITH_NC'))),
                    r.get('FAC_COMPLIANCE_STATUS'), int(_money(r.get('FAC_INSPECTION_COUNT'))), int(_money(r.get('FAC_FORMAL_ACTION_COUNT'))),
                    r.get('FAC_DATE_LAST_FORMAL_ACTION'), _money(r.get('FAC_TOTAL_PENALTIES')), int(_money(r.get('FAC_PENALTY_COUNT'))),
                    r.get('FAC_DATE_LAST_PENALTY'), r.get('FAC_MAJOR_FLAG'), round(_money(r.get('GHG_CO2_RELEASES'))), round(_money(r.get('TRI_ON_SITE_RELEASES'))),
                    r.get('REGISTRY_ID')]))
    by_cik = {c['cik']: c for c in companies}
    for cik, key, row in pend:
        if key and kept[key] / seen[key] < 0.3 and (by_cik[cik]['revenue'] or 0) < 20e9:
            continue
        out.setdefault(cik, []).append(row)
    return out


def _us_date(s):
    m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', str(s or '').strip())
    return f'{m[3]}-{m[1]}-{m[2]}' if m else None


def epa_summary(rows, revenue):
    if not rows:
        return None
    viol = [r for r in rows if r[5] and 'violation' in r[5].lower() and not r[5].lower().startswith('no ')]
    # one settlement often sits on every facility it covers (same amount, same date): count each amount-and-date once
    pen = sum(a for a, _ in {(r[9], r[11]) for r in rows if r[9]})
    states = {}
    for r in rows:
        states[r[2]] = states.get(r[2], 0) + 1
    lastp = max((d for d in (_us_date(r[11]) for r in rows) if d), default=None)
    row = lambda r: [r[0], r[1], r[2], r[3], r[4], r[5], r[7], round(r[9]), _us_date(r[11]), r[13] or None, r[14] or None, r[15]]   # noqa: E731
    top = sorted(rows, key=lambda r: (-r[9], -r[7], -(r[3] == 'Y'), -r[4]))[:10]
    emit = sorted((r for r in rows if r[13]), key=lambda r: -r[13])[:6]
    co2, tri = sum(r[13] for r in rows), sum(r[14] for r in rows)
    return {'facilities': len(rows), 'major': sum(1 for r in rows if r[12] == 'Y'), 'snc': sum(1 for r in rows if r[3] == 'Y'),
            'in_violation': len(viol), 'qtrs_nc': sum(r[4] for r in rows), 'inspections_5y': sum(r[6] for r in rows),
            'formal_5y': sum(r[7] for r in rows), 'penalties_5y': round(pen), 'penalty_n': sum(r[10] for r in rows), 'last_penalty': lastp,
            'co2_t': co2 or None, 'tri_lb': tri or None, 'per_bn': round(pen / (revenue / 1e9)) if revenue and revenue >= 1e8 else None,
            'co2_per_mn': round(co2 / (revenue / 1e6), 1) if co2 and revenue and revenue >= 1e8 else None,
            'states': sorted(states.items(), key=lambda x: -x[1])[:8], 'top': [row(r) for r in top], 'emitters': [row(r) for r in emit]}


# ---------------------------------------------------------------- cost shocks
COSTS = [('oil', 'Crude oil (WTI)', 'DCOILWTICO'), ('gas', 'Natural gas (Henry Hub)', 'DHHNGSP'), ('diesel', 'Diesel', 'GASDESW'),
         ('jet', 'Jet fuel', 'DJFUELUSGULF'), ('power', 'Industrial electricity (PPI)', 'WPU0543'), ('wages', 'Hourly earnings, private sector', 'CES0500000003'),
         ('steel', 'Steel mill products (PPI)', 'WPU101'), ('copper', 'Copper', 'PCOPPUSDM')]


def fred_quarterly(root, fetch_series=None, max_age_h=20, fetch=True):
    """{key: {'CY2025Q3': average}} for each input (fetch=False: from the cache only)."""
    import macro_history as MH
    fetch_series = fetch_series or MH.fetch_one
    out = {}
    folder = Path(root) / 'cache' / 'fred'
    folder.mkdir(parents=True, exist_ok=True)
    for key, _, sid in COSTS:
        p = folder / f'{sid}.csv'
        if fetch and (not p.exists() or time.time() - p.stat().st_mtime > max_age_h * 3600):
            try:
                p.write_text(fetch_series(sid), encoding='utf-8')
            except Exception as e:  # noqa: BLE001
                print(f'FRED {sid}: {str(e)[:120]}', flush=True)
        if not p.exists():
            continue
        acc = {}
        for d, v in MH.parse_csv(p.read_text(encoding='utf-8')):
            q = f'CY{d.year}Q{(d.month - 1) // 3 + 1}'
            acc.setdefault(q, []).append(v)
        out[key] = {q: sum(v) / len(v) for q, v in acc.items() if v}
    return out


def _yoy(series, q):
    y, n = int(q[2:6]), q[-1]
    p = f'CY{y - 1}Q{n}'
    a, b = series.get(q), series.get(p)
    return math.log(a / b) if a and b and a > 0 and b > 0 else None


def cost_panel(qfig, inputs, sector_of, min_obs=8):
    """Year-on-year change in gross and operating margin against the year-on-year log change of each input, per company
    and per sector (pooled). Returns ({sector: {input: fit}}, {cik: {input: fit}}); fit = {'b_gm', 'b_om', 'r2_gm', 'n'}."""
    obs_sec, obs_co = {}, {}
    for cik, per in qfig.items():
        sec = sector_of(cik)
        for q, f in per.items():
            y = int(q[2:6])
            p = per.get(f'CY{y - 1}Q{q[-1]}')
            if not p or not f.get('rev') or not p.get('rev') or f['rev'] <= 0 or p['rev'] <= 0:
                continue
            gm = (f['gp'] / f['rev'] - p['gp'] / p['rev']) if f.get('gp') is not None and p.get('gp') is not None else None
            om = (f['oi'] / f['rev'] - p['oi'] / p['rev']) if f.get('oi') is not None and p.get('oi') is not None else None
            if (gm is not None and abs(gm) > 0.5) or (om is not None and abs(om) > 0.5):
                continue
            for key, s in inputs.items():
                x = _yoy(s, q)
                if x is None:
                    continue
                obs_sec.setdefault(sec, {}).setdefault(key, []).append((x, gm, om))
                obs_co.setdefault(cik, {}).setdefault(key, []).append((x, gm, om))

    def fit(lst):
        out = {'n': len(lst)}
        for name, idx in (('gm', 1), ('om', 2)):
            pts = [(o[0], o[idx]) for o in lst if o[idx] is not None]
            if len(pts) < min_obs:
                continue
            n = len(pts)
            mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
            sxx = sum((p[0] - mx) ** 2 for p in pts)
            if not sxx:
                continue
            b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
            res = [p[1] - my - b * (p[0] - mx) for p in pts]
            se = math.sqrt(sum(e * e for e in res) / max(n - 2, 1) / sxx)
            ss = sum((p[1] - my) ** 2 for p in pts)
            out['b_' + name] = round(b, 5)
            out['t_' + name] = round(b / se, 2) if se else None
            out['r2_' + name] = round(1 - sum(e * e for e in res) / ss, 3) if ss else None
        return out
    sec_fit = {s: {k: fit(v) for k, v in d.items()} for s, d in obs_sec.items()}
    co_fit = {c: {k: fit(v) for k, v in d.items()} for c, d in obs_co.items()}
    # each company's own estimate shrunk toward its sector's: weight n / (n + 20)
    for cik, d in co_fit.items():
        sec = sector_of(cik)
        for k, f in d.items():
            s = (sec_fit.get(sec) or {}).get(k) or {}
            for m in ('gm', 'om'):
                if f.get('b_' + m) is not None and s.get('b_' + m) is not None:
                    w = f['n'] / (f['n'] + 20)
                    f['shrunk_' + m] = round(w * f['b_' + m] + (1 - w) * s['b_' + m], 5)
    return sec_fit, co_fit


# ---------------------------------------------------------------- collect
def collect(root, site_index, minutes=40, today=None, only=None):
    root = Path(root)
    today = today or dt.date.today()
    t0 = time.time()
    left = lambda: minutes * 60 - (time.time() - t0)   # noqa: E731
    comps = universe(site_index)
    find = matcher(comps)
    state = read_json(root / 'state.json', {})
    res = {}
    since5 = (today - dt.timedelta(days=5 * 365)).isoformat()

    def fresh(key, days):
        at = state.get(key)
        return at and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(at)).days < days

    def run(name, fn):
        if only and name not in only:
            return
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001
            res[name] = {'error': str(e)[:200]}
            print(f'{name}: {str(e)[:200]}', flush=True)

    # recalls in bulk (weekly): CPSC and NHTSA
    def bulk():
        out = {}
        if not fresh('cpsc', 3):
            write_json(root / 'cache' / 'cpsc.json', cpsc_all(since5))
            state['cpsc'] = now()
            out['cpsc'] = 'fetched'
        if not fresh('nhtsa', 3):
            write_json(root / 'cache' / 'nhtsa.json', nhtsa_all(since5))
            state['nhtsa'] = now()
            out['nhtsa'] = 'fetched'
        return out
    run('bulk', bulk)

    def per_company(name, pick, fn, days, share):
        """fn(company) for the companies `pick` keeps whose entry is older than `days`, within a share of the time left."""
        folder = root / 'cache' / name
        folder.mkdir(parents=True, exist_ok=True)
        budget = left() * share
        t1, done, fails = time.time(), 0, 0
        cands = [c for c in comps if pick(c)]
        cands.sort(key=lambda c: (read_json(folder / f"{c['cik']}.json", {}).get('at') or '', -(c['revenue'] or 0)))
        for c in cands:
            if time.time() - t1 > budget:
                break
            p = folder / f"{c['cik']}.json"
            old = read_json(p, {})
            if old.get('at') and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(old['at'])).days < days:
                continue
            try:
                write_json(p, {'at': now(), 'data': fn(c)})
                done += 1
            except Exception as e:  # noqa: BLE001
                fails += 1
                if fails <= 3:
                    print(f'{name} {c["ticker"]}: {str(e)[:160]}', flush=True)
                if fails > 25:
                    break
        return {'updated': done, 'failed': fails, 'candidates': len(cands)}

    run('trials', lambda: per_company('trials', lambda c: c['sic'] in PHARMA_SIC, trials_fetch, 7, 0.25))
    run('fda', lambda: per_company('fda', lambda c: c['sic'] in FDA_SIC, lambda c: fda_recalls(c, since5), 7, 0.2))
    since1 = (today - dt.timedelta(days=365)).isoformat()
    run('fedreg', lambda: per_company('fedreg', lambda c: (c['revenue'] or 0) >= 1e9, lambda c: fedreg(c, since1), 7, 0.3))
    key = os.environ.get('DATA_GOV_API_KEY', '').strip()
    if key:
        cy = today.year + (today.year % 2)
        run('fec', lambda: per_company('fec', lambda c: (c['revenue'] or 0) >= 2e9, lambda c: fec(c, key, [cy, cy - 2]), 14, 0.3))
    else:
        res['fec'] = {'skipped': 'no DATA_GOV_API_KEY (free at api.data.gov/signup); the demo key allows ten requests an hour'}
    def cfpb_bulk():
        if fresh('cfpb', 1) and (root / 'cache' / 'cfpb_years.json').exists():
            return 'fresh'
        wins = cfpb_windows(today)
        write_json(root / 'cache' / 'cfpb_years.json', {'at': now(), 'windows': wins, 'counts': [cfpb_counts(a, b) for a, b in wins]})
        state['cfpb'] = now()
        return 'fetched'
    run('cfpb_bulk', cfpb_bulk)
    cf = read_json(root / 'cache' / 'cfpb_years.json', {}) or {}
    cmap = cfpb_names(comps, cf) if cf.get('counts') else {}
    run('cfpb', lambda: per_company('cfpb', lambda c: c['cik'] in cmap, lambda c: cfpb_detail(cmap[c['cik']], *cf['windows'][0]), 7, 0.15))
    def epa():
        if fresh('epa', 6) and (root / 'cache' / 'epa.json').exists():
            return 'fresh'
        tmp = root.parent / 'echo_exporter.zip'
        with open(tmp, 'wb') as f:
            f.write(get(EPA_ZIP, timeout=900, tries=3))
        try:
            m = epa_bulk(tmp, comps, lambda c: c['sector'] in EPA_SECTORS)
        finally:
            tmp.unlink(missing_ok=True)
        write_json(root / 'cache' / 'epa.json', {'at': now(), 'by_cik': {str(k): v for k, v in m.items()}})
        state['epa'] = now()
        return {'companies': len(m), 'facilities': sum(len(v) for v in m.values())}
    run('epa', epa)
    run('wiki', lambda: pageviews(root, comps, wiki_map(root), budget_s=max(60, left() * 0.8), today=today))
    run('costs', lambda: {k: len(v) for k, v in fred_quarterly(root).items()})
    state['last_collect'] = {'at': now(), 'seconds': round(time.time() - t0), **{k: v for k, v in res.items()}}
    write_json(root / 'state.json', state)
    return state['last_collect']


# ---------------------------------------------------------------- build
def build(root, site_index, frames_root=None, today=None):
    root = Path(root)
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    comps = universe(site_index)
    by_cik = {c['cik']: c for c in comps}
    find = matcher(comps)
    docs = {c['cik']: {} for c in comps}
    # trials
    for p in (root / 'cache' / 'trials').glob('*.json'):
        cik = int(p.stem)
        s = trials_summary((read_json(p, {}) or {}).get('data') or [], today)
        if s and cik in docs:
            docs[cik]['trials'] = s
    # recalls: FDA per company, CPSC and NHTSA in bulk
    rec = {}
    for p in (root / 'cache' / 'fda').glob('*.json'):
        rec.setdefault(int(p.stem), []).extend((read_json(p, {}) or {}).get('data') or [])
    for cik, lst in cpsc_match(read_json(root / 'cache' / 'cpsc.json', []) or [], find).items():
        rec.setdefault(cik, []).extend(lst)
    for cik, lst in nhtsa_match(read_json(root / 'cache' / 'nhtsa.json', []) or [], find).items():
        rec.setdefault(cik, []).extend(lst)
    for cik, lst in rec.items():
        s = recalls_summary(lst, today)
        if s and cik in docs:
            docs[cik]['recalls'] = s
    # Federal Register, FEC
    for name in ('fedreg', 'fec'):
        for p in (root / 'cache' / name).glob('*.json'):
            d = (read_json(p, {}) or {}).get('data')
            cik = int(p.stem)
            if d and cik in docs and (name != 'fedreg' or d.get('count')):
                docs[cik][name] = d
    # attention
    for p in (root / 'cache' / 'views').glob('*.json'):
        d = read_json(p, {}) or {}
        a = attention(d.get('days') or {}, today)
        cik = int(p.stem)
        if a and cik in docs:
            docs[cik]['attention'] = {'article': d.get('article'), **a}
    # consumer complaints (CFPB) and environmental compliance (EPA ECHO)
    cf = read_json(root / 'cache' / 'cfpb_years.json', {}) or {}
    if cf.get('counts'):
        for cik, names in cfpb_names(comps, cf).items():
            det = (read_json(root / 'cache' / 'cfpb' / f'{cik}.json', {}) or {}).get('data')
            s = cfpb_summary(names, cf['counts'], det, by_cik[cik]['revenue'])
            if s and cik in docs:
                docs[cik]['complaints'] = {**s, 'window': cf['windows'][0]}
    for k, rows in ((read_json(root / 'cache' / 'epa.json', {}) or {}).get('by_cik') or {}).items():
        cik = int(k)
        s = epa_summary(rows, (by_cik.get(cik) or {}).get('revenue'))
        if s and cik in docs:
            docs[cik]['environment'] = s
    # cost shocks
    costs = {}
    sec_fit, co_fit = {}, {}
    if frames_root:
        import frames as FR
        inputs = fred_quarterly(root, fetch=False)
        qfig = FR.figures(frames_root, FR.calendar_quarters(25, today))
        sec_of = {str(c['cik']): c['sector'] for c in comps}
        sec_fit, co_fit = cost_panel(qfig, inputs, lambda cik: sec_of.get(str(cik).lstrip('0'), 'other'))
        latest = {k: (max(v.items())[0], _yoy(v, max(v))) for k, v in inputs.items() if v}
        costs = {'inputs': [[k, l, sid, latest.get(k, (None, None))[0], latest.get(k, (None, None))[1]] for k, l, sid in COSTS],
                 'sectors': sec_fit, 'generated_at': now(),
                 'note': ('Year-on-year change in each sector\'s gross and operating margin (percentage points) against the year-on-year '
                          'log change of each input, quarterly, pooled over the companies of the sector (SEC XBRL frames; FRED). '
                          'b = margin points per 100% change of the input. One input at a time: inputs that move together share their effect.')}
        for cik, d in co_fit.items():
            try:
                k = int(str(cik).lstrip('0') or 0)
            except ValueError:
                continue
            if k in docs and any(f.get('b_gm') is not None or f.get('b_om') is not None for f in d.values()):
                docs[k]['costs'] = {kk: {m: f.get(m) for m in ('n', 'b_gm', 'b_om', 't_gm', 't_om', 'shrunk_gm', 'shrunk_om')} for kk, f in d.items()}
    # publish
    index = []
    for cik, d in docs.items():
        if not d:
            continue
        c = by_cik[cik]
        write_json(pub / 'c' / f'{cik}.json', {'cik': cik, 'ticker': c['ticker'], 'name': c['name'], 'sector': c['sector'], 'generated_at': now(), **d})
        t, r, f, w, fe = d.get('trials') or {}, d.get('recalls') or {}, d.get('fedreg') or {}, d.get('attention') or {}, d.get('fec') or {}
        cp, en = d.get('complaints') or {}, d.get('environment') or {}
        cy = sorted((fe.get('cycles') or {}).items())[-1][1] if fe.get('cycles') else {}
        index.append([cik, c['ticker'], c['name'], c['sector'], t.get('active'), (t.get('phases') or {}).get('PHASE3', {}).get('active'),
                      len(t.get('due') or []) or None, r.get('last_12m'), r.get('n'), r.get('class1'), f.get('count'), w.get('avg7'), w.get('ratio'),
                      cy.get('receipts'), cy.get('to_candidates'), cp.get('last_12m'), cp.get('change'), cp.get('per_bn'),
                      en.get('facilities'), en.get('snc'), en.get('in_violation'), en.get('penalties_5y'), en.get('co2_t'), c['revenue'] or None])
    fields = ['cik', 'ticker', 'name', 'sector', 'trials_active', 'phase3_active', 'catalysts', 'recalls_12m', 'recalls_5y', 'class1',
              'fedreg_12m', 'views_7d', 'views_ratio', 'pac_receipts', 'pac_to_candidates', 'complaints_12m', 'complaints_change', 'complaints_per_bn',
              'epa_facilities', 'epa_snc', 'epa_violation', 'epa_penalties_5y', 'epa_co2_t', 'revenue']
    write_json(pub / 'index.json', {'generated_at': now(), 'fields': fields, 'rows': sorted(index, key=lambda r: -(r[-1] or 0))})
    # the cross-company lists: catalysts due, the latest recalls, the latest rules
    cat, recent, regs = [], [], []
    for cik, d in docs.items():
        c = by_cik[cik]
        for s in (d.get('trials') or {}).get('due') or []:
            cat.append([s[4], c['ticker'], cik] + s)
        for x in ((d.get('recalls') or {}).get('latest') or [])[:10]:
            recent.append([x['date'], c['ticker'], cik, x['source'], x.get('class'), x['what'], x.get('why'), x.get('url') or ''])
        for x in ((d.get('fedreg') or {}).get('docs') or [])[:5]:
            regs.append([x[0], c['ticker'], cik] + x[1:])
    k0 = lambda r: str(r[0] or '')                     # noqa: E731
    write_json(pub / 'lists.json', {'generated_at': now(), 'catalysts': sorted(cat, key=k0)[:600], 'recalls': sorted(recent, key=k0, reverse=True)[:500],
                                    'regulation': sorted(regs, key=k0, reverse=True)[:400]})
    write_json(pub / 'costs.json', costs)
    st = read_json(root / 'state.json', {})
    status = {'built_at': now(), 'companies': len(index), 'trials': sum(1 for d in docs.values() if d.get('trials')),
              'recalls': sum(1 for d in docs.values() if d.get('recalls')), 'fedreg': sum(1 for d in docs.values() if d.get('fedreg')),
              'fec': sum(1 for d in docs.values() if d.get('fec')), 'attention': sum(1 for d in docs.values() if d.get('attention')),
              'costs': sum(1 for d in docs.values() if d.get('costs')), 'complaints': sum(1 for d in docs.values() if d.get('complaints')),
              'environment': sum(1 for d in docs.values() if d.get('environment')), 'last_collect': st.get('last_collect')}
    write_json(pub / 'status.json', status)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--site-index', required=True)
    c.add_argument('--minutes', type=float, default=40)
    c.add_argument('--only', default='', help='comma-separated: bulk,trials,fda,fedreg,fec,cfpb_bulk,cfpb,epa,wiki,costs')
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--site-index', required=True)
    b.add_argument('--frames-root', default=None)
    a = ap.parse_args()
    if a.cmd == 'collect':
        print(json.dumps(collect(a.root, a.site_index, a.minutes, only=set(filter(None, a.only.split(','))) or None)), flush=True)
    else:
        print(json.dumps(build(a.root, a.site_index, a.frames_root)), flush=True)


if __name__ == '__main__':
    main()
