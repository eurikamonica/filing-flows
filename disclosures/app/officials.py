"""State and Canadian officials' disclosures (4.1): discovery of documents beyond the US House.

Jurisdictions
- New York State (COELIG): the public index of Financial Disclosure Statements for statewide elected officials,
  the Senate and the Assembly. Each listing links to a page that embeds a printable HTML statement.
- California (FPPC): the Public Official Financial Disclosure Portal (filings since 2025-01-01, Government Code
  §87200 filers: statewide officials, legislators, judges, other high-level decision makers). JSON search
  endpoint + redacted PDF download.
- Texas (TEC): Personal Financial Statements are not published online by the Commission; copies are obtained through
  an open-records request. Import-only.
- Canada (Office of the Conflict of Interest and Ethics Commissioner): the public registry of declarations by
  ministers, parliamentary secretaries, other reporting public office holders and Members of the House of Commons.
- Canada (SEDI): insider transaction reports. The site sits behind bot protection; the collector probes it and
  reports "blocked" rather than pretending. Import-only until that changes.

Every document ends in the same review pipeline as House PDFs: candidates are extracted, nothing is published as a
holding or transaction until a human reviews it against the source.
"""
import datetime as dt
import hashlib
import html
import re
from urllib.parse import urljoin, urlparse, parse_qs, quote

NY = 'https://ethics.ny.gov'
NY_INDEX = NY + '/financial-disclosure-statements-elected-officials'
CA = 'https://form700search.fppc.ca.gov'
CANADA = 'https://prciec-rpccie.parl.gc.ca'
SEDI = 'https://www.sedi.ca/sedi/SVTSelectInsiderIssuerType?locale=en_CA'
TX_INFO = 'https://www.ethics.texas.gov/filers/state/pfs/'

JURISDICTIONS = {
    'house': 'US House', 'ny': 'New York State', 'ca': 'California', 'tx': 'Texas',
    'canada': 'Canada (federal public office holders)', 'sedi': 'Canada (SEDI insider reports)'}

LINK = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def strip_tags(fragment):
    text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', fragment, flags=re.S | re.I)
    text = re.sub(r'<br\s*/?>|</(p|div|tr|li|h\d|table|section)>', '\n', text, flags=re.I)
    text = re.sub(r'</t[dh]>', '\t', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n\s*\n+', '\n', text).strip()


def html_to_pages(raw, chars_per_page=6000):
    """An HTML statement becomes text 'pages' so the review desk can cite a location."""
    text = strip_tags(raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw)
    if not text:
        raise ValueError('Document contained no readable text')
    pages, buf = [], ''
    for line in text.split('\n'):
        if len(buf) + len(line) > chars_per_page and buf:
            pages.append(buf); buf = ''
        buf += line + '\n'
    if buf:
        pages.append(buf)
    return [{'page': i + 1, 'method': 'html', 'mean_word_confidence': None, 'text': p, 'money_ranges': None} for i, p in enumerate(pages)]


# ---------------------------------------------------------------- New York
def ny_filters(index_html):
    """Map filter labels (years, offices) to their filter_term IDs from the index page links."""
    found = {}
    for href, label in LINK.findall(index_html):
        m = re.search(r'filter_term(?:%3A|:)(\d+)', href)
        if not m:
            continue
        name = strip_tags(label)
        name = re.sub(r'\s*\(\d+\)\s*$', '', name).strip()   # "2025 (210)" → "2025"
        if name and name not in found:
            found[name] = m[1]
    return found


def ny_listing(index_html):
    """Statement links on one index page: (slug URL, title)."""
    rows = []
    for href, label in LINK.findall(index_html):
        path = urlparse(href).path
        title = strip_tags(label)
        if not title or '?' in href or 'filter_term' in href:
            continue
        if re.fullmatch(r'/\d{4}-[a-z0-9-]+', path) or re.fullmatch(r'/[a-z0-9-]+-fds-\d{4}', path):
            rows.append((urljoin(NY, path), title))
    seen, out = set(), []
    for u, t in rows:
        if u not in seen:
            seen.add(u); out.append((u, t))
    return out


def ny_meta(url, title, office):
    slug = urlparse(url).path.strip('/')
    m = re.match(r'(\d{4})-(.+)', slug) or re.match(r'(.+)-fds-(\d{4})', slug)
    if slug.startswith(tuple(str(y) for y in range(2000, 2100))):
        year, rest = int(slug[:4]), slug[5:]
    else:
        year = int(slug[-4:]); rest = slug[:-9]
    person = title
    office_name = office
    if ' - ' in title:
        parts = [p.strip() for p in title.split(' - ')]
        person = parts[-1]; office_name = parts[0]
    return {'report_id': 'ny-' + hashlib.sha256(slug.encode()).hexdigest()[:16], 'person': person,
            'jurisdiction': JURISDICTIONS['ny'], 'office': office_name, 'index_year': year,
            'report_type': 'Annual FDS', 'filing_type_code': 'FDS', 'filed_date': '', 'source_url': url,
            'doc_kind': 'ny-html', 'slug': slug}


def ny_printable_url(page_html):
    m = re.search(r'https?://public\.ethics\.ny\.gov/FDS/Form/_ViewPrintable/\d+/\d+', page_html)
    if not m:
        m = re.search(r'(/FDS/Form/_ViewPrintable/\d+/\d+)', page_html)
        if not m:
            raise ValueError('No printable statement link on the NY filing page')
        return 'https://public.ethics.ny.gov' + m[1]
    return m[0]


def discover_ny(client, cfg, old_catalog):
    years = [int(y) for y in cfg.get('years', [])]
    offices = cfg.get('offices', ['Statewide Elected Officials', 'Senate', 'Assembly'])
    max_pages = int(cfg.get('max_index_pages_per_run', 40))
    catalog, errors, coverage = {}, [], []
    first = client.get(NY_INDEX + '?page=0').decode('utf-8', 'replace')
    filters = ny_filters(first)
    if not filters:
        raise ValueError('NY index page has no filter links; layout changed (first 300 chars: %r)' % strip_tags(first)[:300])
    fetched = 0
    for office in offices:
        if office not in filters:
            errors.append(f'NY: office filter "{office}" not on the index page (have: {", ".join(sorted(filters))[:200]})')
            continue
        for year in years:
            if str(year) not in filters:
                errors.append(f'NY: year filter {year} not on the index page')
                continue
            count, page = 0, 0
            while fetched < max_pages:
                url = f'{NY_INDEX}?f%5B0%5D=filter_term%3A{filters[office]}&f%5B1%5D=filter_term%3A{filters[str(year)]}&page={page}'
                body = client.get(url).decode('utf-8', 'replace'); fetched += 1
                rows = ny_listing(body)
                new = 0
                for link, title in rows:
                    meta = ny_meta(link, title, office)
                    if meta['index_year'] != year:
                        continue
                    if meta['report_id'] not in catalog:
                        catalog[meta['report_id']] = meta; new += 1
                count += new
                if not rows or new == 0 or f'page={page + 1}' not in body:
                    break
                page += 1
            coverage.append({'jurisdiction': 'ny', 'office': office, 'year': year, 'discovered': count, 'index_pages': page + 1,
                             'truncated': fetched >= max_pages})
    if not catalog and not errors:
        errors.append('NY: filters found but no statement links matched the expected slug patterns')
    return catalog, errors, coverage


def fetch_ny_document(client, meta):
    page = client.get(meta['source_url']).decode('utf-8', 'replace')
    printable = ny_printable_url(page)
    raw = client.get(printable)
    return raw, {'document_url': printable}


# ---------------------------------------------------------------- California
def ca_search_payload(year, position=None, last_initial=None, amendments_only=False):
    fields = []
    if position:
        fields.append({'queryField': 'FilerPosition', 'filterValue': position})
    if last_initial:
        fields.append({'queryField': 'FilerLastName', 'queryType': 'Start With', 'filterValue': last_initial})
    fields.append({'queryField': 'FilingType', 'filterValue': []})
    if year:
        fields.append({'queryField': 'FilingYear', 'filterValue': str(year)})
    if amendments_only:
        fields.append({'queryField': 'Amendment', 'filterValue': 'true'})
    return {'queryGenerationInfo': None, 'searchFieldQueryInfos': fields, 'showOnlyHeldPositions': False}


def ca_documents(response):
    """Normalise the portal's search response into metas (documents + total)."""
    if isinstance(response, str):
        import json
        response = json.loads(response)
    docs = response.get('documents') if isinstance(response, dict) else response
    total = response.get('total', len(docs or [])) if isinstance(response, dict) else len(docs or [])
    metas = []
    for d in docs or []:
        filer = d.get('filer') or {}
        pos = (d.get('filingPositions') or [{}])[0]
        index_id = str(d.get('indexID') or d.get('indexId') or '')
        if not index_id:
            continue
        person = ' '.join(x for x in [filer.get('firstName', ''), filer.get('lastName', '')] if x).strip()
        filed = str(d.get('filingDate') or d.get('dateFiled') or '')[:10]
        try:
            dt.date.fromisoformat(filed)
        except ValueError:
            filed = ''
        year = pos.get('filingYear') or d.get('filingYear') or ''
        metas.append({'report_id': 'ca-' + re.sub(r'[^A-Za-z0-9]', '', index_id)[:40], 'person': person or 'Unnamed filer',
                      'jurisdiction': JURISDICTIONS['ca'], 'office': ' · '.join(x for x in [pos.get('position', ''), pos.get('agency', '')] if x),
                      'index_year': int(str(year)[:4]) if str(year)[:4].isdigit() else None,
                      'report_type': 'Form 700 ' + str(pos.get('filingType') or d.get('filingType') or ''),
                      'filing_type_code': str(pos.get('filingType') or ''), 'filed_date': filed,
                      'source_url': CA + '/', 'doc_kind': 'ca-pdf',
                      'ca': {'LastName': filer.get('lastName', ''), 'FirstName': filer.get('firstName', ''), 'Agency': pos.get('agency', ''),
                             'Position': pos.get('position', ''), 'FilingYear': str(year), 'FilingType': pos.get('filingType', ''), 'indexID': index_id}})
    return metas, int(total or 0)


def discover_ca(client, cfg, old_catalog):
    years = [int(y) for y in cfg.get('years', [])]
    positions = cfg.get('positions', [])
    cap = int(cfg.get('result_cap', 1000))
    catalog, errors, coverage = {}, [], []
    for year in years:
        try:
            metas, total = ca_documents(client.post_json(CA + '/Home/SearchDocuments', ca_search_payload(year)))
        except Exception as exc:
            errors.append(f'CA {year}: {exc}')
            continue
        for m in metas:
            catalog.setdefault(m['report_id'], m)
        truncated = total > len(metas) or total >= cap
        splits = 0
        if truncated:
            # The portal returns at most 1,000 rows; split the year by position and by last-name initial.
            queries = [('position', p) for p in positions] + [('initial', ch) for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
            for kind, value in queries:
                try:
                    payload = ca_search_payload(year, position=value) if kind == 'position' else ca_search_payload(year, last_initial=value)
                    part, part_total = ca_documents(client.post_json(CA + '/Home/SearchDocuments', payload)); splits += 1
                    for m in part:
                        catalog.setdefault(m['report_id'], m)
                    if part_total > len(part):
                        errors.append(f'CA {year} {kind} {value}: {part_total} results, {len(part)} returned (portal cap)')
                except Exception as exc:
                    errors.append(f'CA {year} {kind} {value}: {exc}')
        coverage.append({'jurisdiction': 'ca', 'year': year, 'reported_total': total, 'discovered': sum(1 for m in catalog.values() if m['index_year'] == year),
                         'split_queries': splits, 'truncated': truncated and not splits})
    return catalog, errors, coverage


def fetch_ca_document(client, meta):
    info = meta['ca']
    payload = {'formInfo': {k: info[k] for k in ('LastName', 'FirstName', 'Agency', 'Position', 'FilingYear', 'FilingType')}, 'indexID': info['indexID']}
    answer = client.post_json(CA + '/Home/GetRedactedFormPdf', payload)
    url = answer.get('PDFDownloadUrl') if isinstance(answer, dict) else None
    if not url:
        raise ValueError('Portal returned no PDFDownloadUrl: ' + str(answer)[:200])
    if urlparse(url).hostname is None:
        url = urljoin(CA, url)
    raw = client.get(url)          # the session cookie from the POST travels in the client's cookie jar
    return raw, {'document_url': url}


# ---------------------------------------------------------------- Canada: public registry
def canada_listing(page_html, base):
    rows = []
    for href, label in LINK.findall(page_html):
        title = strip_tags(label)
        full = urljoin(base, href)
        if urlparse(full).hostname not in ('prciec-rpccie.parl.gc.ca',):
            continue
        low = full.lower()
        if any(k in low for k in ('declaration', 'summary', 'statement', 'disclosure', 'publicregistr')) and re.search(r'[?&](id|itemid|declarationid|poh|member)[^&]*=\d+', low):
            rows.append((full, title))
        elif re.search(r'/(DeclarationView|SummaryStatement|ViewDeclaration|PublicDeclaration)[^"]*', full, re.I):
            rows.append((full, title))
    seen, out = set(), []
    for u, t in rows:
        if u not in seen and t:
            seen.add(u); out.append((u, t))
    return out


def discover_canada(client, cfg, old_catalog):
    starts = cfg.get('start_pages', [CANADA + '/EN/PublicRegistries/Pages/PublicRegistryHome.aspx'])
    max_pages = int(cfg.get('max_index_pages_per_run', 30))
    catalog, errors, coverage = {}, [], []
    queue, seen, fetched = list(starts), set(), 0
    while queue and fetched < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            body = client.get(url, allow_block=True).decode('utf-8', 'replace'); fetched += 1
        except Exception as exc:
            errors.append(f'Canada registry {url}: {exc}')
            continue
        found = canada_listing(body, url)
        for link, title in found:
            rid = 'cafed-' + hashlib.sha256(link.encode()).hexdigest()[:16]
            catalog.setdefault(rid, {'report_id': rid, 'person': title, 'jurisdiction': JURISDICTIONS['canada'], 'office': '',
                                     'index_year': None, 'report_type': 'Public declaration', 'filing_type_code': 'DECL', 'filed_date': '',
                                     'source_url': link, 'doc_kind': 'html'})
        # follow registry list pages (not declarations) one level deep
        for href, label in LINK.findall(body):
            full = urljoin(url, href)
            if urlparse(full).hostname == 'prciec-rpccie.parl.gc.ca' and '/PublicRegistries/' in full and full not in seen and 'Pages/' in full and not any(full == l for l, _ in found):
                if len(queue) < 200:
                    queue.append(full.split('#')[0])
        if not found and fetched == 1:
            errors.append('Canada registry: no declaration links recognised on the start page; sample text: ' + strip_tags(body)[:300].replace('\n', ' '))
    coverage.append({'jurisdiction': 'canada', 'pages_fetched': fetched, 'discovered': len(catalog), 'truncated': bool(queue) and fetched >= max_pages})
    return catalog, errors, coverage


# ---------------------------------------------------------------- Canada: SEDI probe
def probe_sedi(client, cfg):
    try:
        body, final, ctype = client.request(SEDI, allow_block=True)
    except Exception as exc:
        return {'status': 'blocked' if 'challenge' in str(exc) or 'bot' in str(exc).lower() else 'error', 'detail': str(exc), 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    text = strip_tags(body.decode('utf-8', 'replace'))
    blocked = 'perfdrive' in final or 'validate' in final or 'Access Denied' in text or 'enable JavaScript' in text
    return {'status': 'blocked' if blocked else 'reachable', 'detail': ('Reached ' + final + '; the SEDI pages are session-driven forms, automatic collection not implemented') if not blocked else 'SEDI answered with a bot-protection challenge; automatic collection is not possible from a scheduled job',
            'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}


# ---------------------------------------------------------------- orchestration
def discover_all(client, cfg, old):
    """Catalog entries, errors and coverage for every configured non-House jurisdiction."""
    catalog, errors, coverage, notes = {}, [], [], {}
    old_catalog = {r['report_id']: r for r in old.get('directory', [])}
    jur = cfg.get('jurisdictions', {})
    for key, fn in (('ny', discover_ny), ('ca', discover_ca), ('canada', discover_canada)):
        settings = jur.get(key)
        if not settings or not settings.get('enabled', True):
            continue
        try:
            found, errs, cov = fn(client, settings, old_catalog)
            catalog.update(found); errors.extend(errs); coverage.extend(cov)
        except Exception as exc:
            errors.append(f'{JURISDICTIONS[key]} discovery: {exc}')
            coverage.append({'jurisdiction': key, 'discovered': 0, 'failed': True})
            # retain what an earlier run discovered
            catalog.update({k: v for k, v in old_catalog.items() if k.startswith(('ny-' if key == 'ny' else 'ca-' if key == 'ca' else 'cafed-'))})
    if jur.get('tx', {}).get('enabled', True):
        notes['tx'] = 'Texas Personal Financial Statements are not published online by the Texas Ethics Commission; copies come through an open-records request (' + TX_INFO + '). Add them as imports with jurisdiction "Texas".'
    if jur.get('sedi', {}).get('enabled', True):
        notes['sedi'] = probe_sedi(client, jur.get('sedi', {}))
    return catalog, errors, coverage, notes


def fetch_document(client, meta):
    kind = meta.get('doc_kind', 'pdf')
    if kind == 'ny-html':
        return fetch_ny_document(client, meta)
    if kind == 'ca-pdf':
        return fetch_ca_document(client, meta)
    if kind == 'html':
        return client.get(meta['source_url'], allow_block=True), {'document_url': meta['source_url']}
    return client.get(meta['source_url']), {}
