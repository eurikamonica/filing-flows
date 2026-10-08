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
import json
import re
from urllib.parse import urljoin, urlparse, parse_qs, quote

NY = 'https://ethics.ny.gov'
NY_INDEX = NY + '/financial-disclosure-statements-elected-officials'
CA = 'https://form700search.fppc.ca.gov'
CANADA = 'https://www.ethicscanada.ca'   # the registry moved here from prciec-rpccie.parl.gc.ca in 2026
SEDI = 'https://www.sedi.ca/'
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
    person = re.sub(r'\s*FDS(\s*\(\d{4}\))?\s*$', '', title).strip()   # "Last, First M. FDS (2025)" / "… FDS"
    person = re.sub(r'^\d{4}\s+', '', person).strip()                   # "2024 Governor Kathleen Hochul"
    office_name = office
    if ' - ' in person:
        parts = [p.strip() for p in person.split(' - ')]
        person = parts[-1]; office_name = parts[0]
    else:
        for title_word in ('Lieutenant Governor', 'Governor', 'Attorney General', 'Comptroller'):
            if person.startswith(title_word + ' '):
                office_name = title_word; person = person[len(title_word) + 1:].strip(); break
    return {'report_id': 'ny-' + hashlib.sha256(slug.encode()).hexdigest()[:16], 'person': person,
            'jurisdiction': JURISDICTIONS['ny'], 'office': office_name, 'index_year': year,
            'report_type': 'Annual FDS', 'filing_type_code': 'FDS', 'filed_date': '', 'source_url': url,
            'doc_kind': 'ny-html', 'slug': slug}


def ny_printable_url(page_html):
    m = re.search(r'https?://public\.ethics\.ny\.gov/FDS/[^"\'\s<>]+', page_html)
    if m:
        return html.unescape(m[0])
    m = re.search(r'(/FDS/Form/_ViewPrintable/\d+/\d+)', page_html)
    if m:
        return 'https://public.ethics.ny.gov' + m[1]
    # diagnostics: what does the page link to or embed?
    refs = re.findall(r'(?:href|src|data-src|data-url)=["\']([^"\']+)["\']', page_html, re.I)
    refs = [r for r in dict.fromkeys(refs) if re.search(r'fds|ethics|pdf|print|statement|iframe|embed', r, re.I) and not re.search(r'\.(css|js|png|svg|ico|woff2?)(\?|$)', r, re.I)]
    iframes = re.findall(r'<iframe\b[^>]*>', page_html, re.I)
    raise ValueError('No printable statement link on the NY filing page · refs: ' + ' | '.join(refs[:25])[:900] + ' · iframes: ' + ' | '.join(iframes[:3])[:400] + ' · text: ' + strip_tags(page_html)[:300].replace('\n', ' '))


def discover_ny(client, cfg, old_catalog, prior_state=None):
    """Walk the COELIG index a few pages per run; a cursor per (office, year) persists across runs."""
    years = [int(y) for y in cfg.get('years', [])]
    offices = cfg.get('offices', ['Statewide Elected Officials', 'Senate', 'Assembly'])
    max_pages = int(cfg.get('max_index_pages_per_run', 10))
    catalog = {}
    for k, v in old_catalog.items():                                          # keep what earlier runs found, names re-cleaned
        if k.startswith('ny-'):
            fixed = ny_meta(v['source_url'], v.get('person', ''), v.get('office', ''))
            catalog[k] = {**v, 'person': fixed['person'], 'office': fixed['office'] if v.get('office') in ('Statewide Elected Officials', '', None) else v['office']}
    errors, coverage = [], []
    cursors = dict((prior_state or {}).get('cursors', {}))
    first = client.get(NY_INDEX + '?page=0').decode('utf-8', 'replace')
    filters = ny_filters(first)
    if not filters:
        raise ValueError('NY index page has no filter links; layout changed (first 300 chars: %r)' % strip_tags(first)[:300])
    fetched = 1
    for office in offices:
        if office not in filters:
            errors.append(f'NY: office filter "{office}" not on the index page (have: {", ".join(sorted(filters))[:200]})')
            continue
        for year in years:
            if str(year) not in filters:
                coverage.append({'jurisdiction': 'ny', 'office': office, 'year': year, 'discovered': 0, 'note': 'year not yet on the index'})
                continue
            key = f'{office}|{year}'
            page = int(cursors.get(key, 0)); count = 0; pages_now = 0
            while fetched < max_pages:
                url = f'{NY_INDEX}?f%5B0%5D=filter_term%3A{filters[office]}&f%5B1%5D=filter_term%3A{filters[str(year)]}&page={page}'
                try:
                    body = client.get(url).decode('utf-8', 'replace')
                except Exception as exc:
                    errors.append(f'NY {office} {year} page {page}: {exc}'); fetched = max_pages; break
                fetched += 1; pages_now += 1
                rows = ny_listing(body)
                matched = 0
                for link, title in rows:
                    meta = ny_meta(link, title, office)
                    if meta['index_year'] != year:
                        continue
                    matched += 1
                    if meta['report_id'] not in catalog:
                        catalog[meta['report_id']] = meta; count += 1
                if not rows or matched == 0 or f'page={page + 1}' not in body:
                    page = 0; break      # end of this listing: start again from the first page next time
                page += 1
            cursors[key] = page
            coverage.append({'jurisdiction': 'ny', 'office': office, 'year': year, 'new_this_run': count, 'index_pages_this_run': pages_now, 'next_page': page,
                             'discovered': sum(1 for m in catalog.values() if m.get('index_year') == year and (m.get('office') == office if office != 'Statewide Elected Officials' else m.get('office') not in ('Senate', 'Assembly')))})
    return catalog, errors, coverage, {'cursors': cursors}


def fetch_ny_document(client, meta):
    first = client.get(meta['source_url'])
    if first[:5] == b'%PDF-':
        return first, {'document_url': meta['source_url']}      # legislators' statements are served as PDFs directly
    printable = ny_printable_url(first.decode('utf-8', 'replace'))
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
        filed = str(d.get('filingDate') or d.get('dateFiled') or d.get('filedDate') or d.get('dateReceived') or pos.get('filingDate') or pos.get('dateFiled') or '')[:10]
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
                      # compact (kept in the public catalog): only what ca_form_info() cannot rebuild from the other fields
                      'ca': [filer.get('lastName', ''), filer.get('firstName', ''), filer.get('middleName', '') or '',
                             bool((d.get('filingInfo') or {}).get('isAmendment', False)), str((d.get('filingInfo') or {}).get('filedDate') or '')]})
    return metas, int(total or 0)


def discover_ca(client, cfg, old_catalog, prior_state=None):
    years = [int(y) for y in cfg.get('years', [])]
    cap = int(cfg.get('result_cap', 1000))
    budget = int(cfg.get('max_queries_per_run', 160))
    catalog = {k: v for k, v in old_catalog.items() if k.startswith('ca-')}
    errors, coverage, state = [], [], {'queries': 0, 'uncovered': []}
    sample = {}
    carried = list((prior_state or {}).get('uncovered', []))

    def run(year, position=None, prefix=''):
        """One portal query; splits itself by last-name prefix while the portal cap hides rows."""
        if state['queries'] >= budget:
            state['uncovered'].append({'year': year, 'position': position, 'prefix': prefix}); return
        state['queries'] += 1
        answer = client.post_json(CA + '/Home/SearchDocuments', ca_search_payload(year, position=position, last_initial=prefix or None))
        if not sample and isinstance(answer, dict) and answer.get('documents'):
            d = answer['documents'][0]
            sample.update({k: (str(v)[:80] if not isinstance(v, (dict, list)) else v) for k, v in d.items()})
        metas, total = ca_documents(answer)
        for m in metas:
            old = catalog.get(m['report_id'])
            if old is None or len(old.get('ca') or []) != 5:      # upgrade rows discovered before the download fields were recorded
                catalog[m['report_id']] = m
        if total > len(metas) or total >= cap:
            if len(prefix) < 3:
                for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    run(year, position, prefix + ch)
            else:
                errors.append(f'CA {year} {position or "all"} {prefix}: {total} results, {len(metas)} returned (portal cap)')

    # partitions the previous run could not afford come first, so the sweep rotates instead of repeating itself
    for part in carried:
        try:
            run(part['year'], part.get('position'), part.get('prefix', ''))
        except Exception as exc:
            errors.append(f'CA carried partition {part}: {exc}')
    for year in years:
        before = sum(1 for m in catalog.values() if m.get('index_year') == year)
        try:
            run(year)
        except Exception as exc:
            errors.append(f'CA {year}: {exc}')
        coverage.append({'jurisdiction': 'ca', 'year': year, 'discovered': sum(1 for m in catalog.values() if m.get('index_year') == year),
                         'new_this_run': sum(1 for m in catalog.values() if m.get('index_year') == year) - before, 'queries_this_run': state['queries'],
                         'uncovered_partitions': len(state['uncovered']), 'truncated': bool(state['uncovered'])})
    if sample:
        coverage.append({'jurisdiction': 'ca', 'sample_document_fields': sample})
    # keep at most one run's worth of carried partitions
    return catalog, errors, coverage, {'uncovered': state['uncovered'][:budget]}


def ca_form_info(meta):
    info = meta.get('ca')
    parts = (meta.get('office') or '').split(' · ', 1)
    position, agency = (parts + [''])[:2]
    year, ftype = str(meta.get('index_year') or ''), meta.get('filing_type_code', '')
    hexid = meta['report_id'][3:]
    index_id = f'{hexid[:8]}-{hexid[8:12]}-{hexid[12:16]}-{hexid[16:20]}-{hexid[20:]}' if len(hexid) == 32 else hexid
    if isinstance(info, list) and len(info) == 5:
        last, first, middle, amendment, filed = info[0], info[1], info[2], bool(info[3]), info[4]
    elif isinstance(info, list) and len(info) >= 7:          # transitional 4.1 shape
        last, first, agency, position, year, ftype, index_id = info[:7]
        middle, amendment, filed = (info[7], bool(info[8]), info[9]) if len(info) >= 10 else ('', False, '')
    else:
        # rows from the first 4.1 run carried nothing: best effort from the public fields (the sweep upgrades them)
        names = (meta.get('person') or '').split(' ')
        first, last = (' '.join(names[:-1]), names[-1]) if len(names) > 1 else ('', names[0] if names else '')
        middle, amendment, filed = '', False, ''
    return {'formInfo': {'LastName': last, 'FirstName': first, 'Agency': agency, 'Position': position, 'FilingYear': year, 'FilingType': ftype,
                         'MiddleName': middle, 'IsAmendment': amendment, 'FilingDate': filed or (meta.get('filed_date') or '')}, 'indexID': index_id}


CA_PROBE = {'done': False, 'findings': []}


def ca_probe(client):
    """Once per run after a download failure: record which endpoints the portal's own scripts call."""
    if CA_PROBE['done']:
        return CA_PROBE['findings']
    CA_PROBE['done'] = True
    findings = []
    try:
        home = client.get(CA + '/').decode('utf-8', 'replace')
        scripts = [urljoin(CA + '/', m) for m in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', home, re.I)]
        findings.append('home scripts: ' + ', '.join(scripts)[:600])
        endpoints = set(re.findall(r'/Home/[A-Za-z]+', home))
        for src in scripts[:12]:
            if urlparse(src).hostname != 'form700search.fppc.ca.gov':
                continue
            try:
                js = client.get(src).decode('utf-8', 'replace')
            except Exception as exc:
                findings.append(f'{src}: {exc}'); continue
            found = set(re.findall(r'/Home/[A-Za-z]+', js)) | set(re.findall(r'["\'](?:\./)?(Home/[A-Za-z]+)["\']', js))
            if found:
                endpoints |= {e if e.startswith('/') else '/' + e for e in found}
                for e in sorted(found):
                    if re.search(r'pdf|download|document|form', e, re.I):
                        i = js.find(e.split('/')[-1])
                        findings.append(f'{src.split("/")[-1]} {e}: …{js[max(0, i - 220):i + 260]!r}')
        squeeze = lambda t: re.sub(r'\s+', ' ', t)
        for name in ('GetRedactedFormPdf', 'ExportSubmit'):
            for m in list(re.finditer(name, home))[:2]:
                findings.append(f'home context {name}: …{squeeze(home[max(0, m.start() - 700):m.end() + 500])!r}')
        for src in scripts[:12]:
            if urlparse(src).hostname != 'form700search.fppc.ca.gov':
                continue
            try:
                js = client.get(src).decode('utf-8', 'replace')
            except Exception:
                continue
            var = re.search(r'(\w+)=\$\("#hdnGetRedactedFormPdfUrl"\)\.val\(\)', js)
            name = src.split('/')[-1].split('?')[0]
            if var:
                v = var[1]
                for m in list(re.finditer(r'url:' + re.escape(v) + r'\b|\b' + re.escape(v) + r'[,)]', js))[:3]:
                    findings.append(f'{name} call using {v}: …{squeeze(js[max(0, m.start() - 900):m.end() + 700])!r}')
            for m in list(re.finditer(r'PDFDownloadUrl|formInfo:|indexID:', js))[:4]:
                findings.append(f'{name} context: …{squeeze(js[max(0, m.start() - 500):m.end() + 300])!r}')
        try:
            findings.append('GET /Home/GetBootstrap keys: ' + str(list(json.loads(client.get(CA + '/Home/GetBootstrap')).keys()))[:300])
        except Exception as exc:
            findings.append(f'GET /Home/GetBootstrap: {exc}')
        findings.insert(0, 'endpoints: ' + ', '.join(sorted(endpoints)))
    except Exception as exc:
        findings.append('probe failed: ' + str(exc))
    CA_PROBE['findings'] = findings
    return findings


def ca_download_url(payload):
    """The portal's own call (searchExportBundle): GET GetRedactedFormPdf?indexID=…&fileNameInfo.LastName=…&… → {Message, PDFDownloadUrl}."""
    from urllib.parse import urlencode
    info = payload['formInfo']
    params = [('indexID', payload['indexID']),
              ('fileNameInfo.LastName', info.get('LastName', '')), ('fileNameInfo.FirstName', info.get('FirstName', '')),
              ('fileNameInfo.FilingYear', str(info.get('FilingYear', ''))), ('fileNameInfo.Agency', info.get('Agency', '')),
              ('fileNameInfo.Position', info.get('Position', '')), ('fileNameInfo.FilingType', info.get('FilingType', '')),
              ('fileNameInfo.IsAmendment', 'true' if info.get('IsAmendment') else 'false'),
              ('fileNameInfo.FilingDate', info.get('FilingDate') or '')]
    return CA + '/Home/GetRedactedFormPdf?' + urlencode(params)


def fetch_ca_document(client, meta):
    payload = ca_form_info(meta)
    url = ca_download_url(payload)
    raw = client.get(url, headers={'Accept': 'application/json, text/plain, */*', 'X-Requested-With': 'XMLHttpRequest'})
    try:
        answer = json.loads(raw)
    except ValueError:
        first_time = not CA_PROBE['done']
        probe = ca_probe(client) if first_time else []
        raise ValueError('GetRedactedFormPdf answered a page instead of JSON · ' + re.sub(r'\s+', ' ', raw.decode('utf-8', 'replace'))[:200] + (' · ' + ' ‖ '.join(probe)[:5000] if first_time else '')) from None
    pdf_url = next((answer[k] for k in ('PDFDownloadUrl', 'pdfDownloadUrl', 'PdfDownloadUrl', 'url') if isinstance(answer, dict) and answer.get(k)), None)
    if not pdf_url:
        raise ValueError('Portal declined the download: ' + str((answer or {}).get('Message') if isinstance(answer, dict) else answer)[:300])
    if urlparse(pdf_url).hostname is None:
        pdf_url = urljoin(CA, pdf_url)
    if urlparse(pdf_url).hostname != 'form700search.fppc.ca.gov':
        client.hosts = tuple(client.hosts) + (urlparse(pdf_url).hostname,)   # signed storage URL on another host
    pdf = client.get(pdf_url)
    return pdf, {'document_url': CA + '/'}      # the signed URL expires; the portal home is the durable reference


# ---------------------------------------------------------------- Canada: public registry (ethicscanada.ca)
PROFILE = re.compile(r'href=["\']([^"\']*?/en/client\?clientId=([0-9a-fA-F-]{36}))["\'][^>]*>(.*?)</a>', re.I | re.S)
PAGE_OF = re.compile(r'(\d[\d,]*)\s*Result\(s\)\s*[—–-]+\s*page\s*(\d+)\s*of\s*(\d+)', re.I)


def canada_listing(page_html, base):
    """Profile links on one registry listing page: (profile URL, name, context text)."""
    rows, seen = [], set()
    for href, guid, label in PROFILE.findall(page_html):
        name = strip_tags(label)
        url = CANADA + '/en/client?clientId=' + guid.lower()
        if name and url not in seen:
            seen.add(url); rows.append((url, name))
    return rows


def canada_page_info(page_html):
    m = PAGE_OF.search(strip_tags(page_html))
    return (int(m[1].replace(',', '')), int(m[2]), int(m[3])) if m else (None, None, None)


def discover_canada(client, cfg, old_catalog, state=None):
    base = cfg.get('registry_url', CANADA + '/en/public-registry')
    max_pages = int(cfg.get('max_index_pages_per_run', 20))
    catalog = {k: v for k, v in old_catalog.items() if k.startswith('cafed-')}
    errors, coverage = [], []
    state = dict(state or {})
    page = int(state.get('next_page', 1)); fetched = 0; total_pages = None; results = None
    while fetched < max_pages:
        try:
            body = client.get(f'{base}?p={page}', allow_block=True).decode('utf-8', 'replace'); fetched += 1
        except Exception as exc:
            errors.append(f'Canada registry page {page}: {exc}'); break
        results, this_page, total_pages = canada_page_info(body)
        found = canada_listing(body, base)
        if not found:
            errors.append(f'Canada registry page {page}: no profile links recognised; text starts: ' + strip_tags(body)[:200].replace('\n', ' '))
            break
        for link, name in found:
            rid = 'cafed-' + hashlib.sha256(link.encode()).hexdigest()[:16]
            catalog.setdefault(rid, {'report_id': rid, 'person': name, 'jurisdiction': JURISDICTIONS['canada'], 'office': '',
                                     'index_year': None, 'report_type': 'Public registry profile', 'filing_type_code': 'PROFILE', 'filed_date': '',
                                     'source_url': link, 'doc_kind': 'html'})
        if total_pages and page >= total_pages:
            page = 0; break      # wrap around: next run starts again from page 1 (profiles change over time)
        page += 1
    state['next_page'] = max(1, page) if page else 1
    state['total_pages'] = total_pages; state['results'] = results
    coverage.append({'jurisdiction': 'canada', 'pages_fetched': fetched, 'next_page': state['next_page'], 'total_pages': total_pages,
                     'registry_results': results, 'discovered': len(catalog), 'truncated': bool(total_pages) and state['next_page'] > 1})
    return catalog, errors, coverage, state


# ---------------------------------------------------------------- Canada: SEDI probe
def probe_sedi(client, cfg):
    try:
        body, final, ctype = client.request(SEDI, allow_block=True)
    except Exception as exc:
        return {'status': 'blocked' if 'challenge' in str(exc) or 'bot' in str(exc).lower() else 'error', 'detail': str(exc), 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    page = body.decode('utf-8', 'replace'); text = strip_tags(page)
    blocked = 'perfdrive' in final or 'validate' in final or 'Access Denied' in text or 'enable JavaScript' in text or 'shieldsquare' in text.lower()
    links = [urljoin(final, h) for h, _ in LINK.findall(page)]
    links = [l for l in dict.fromkeys(links) if urlparse(l).hostname in ('www.sedi.ca', 'sedi.ca')][:40]
    return {'status': 'blocked' if blocked else 'reachable', 'detail': ('Reached ' + final + '; the SEDI pages are session-driven forms, automatic collection not implemented') if not blocked else 'SEDI answered with a bot-protection challenge; automatic collection is not possible from a scheduled job',
            'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'links': links, 'text_start': text[:300]}


# ---------------------------------------------------------------- orchestration
def discover_all(client, cfg, old):
    """Catalog entries, errors and coverage for every configured non-House jurisdiction."""
    catalog, errors, coverage, notes = {}, [], [], {}
    old_catalog = {r['report_id']: r for r in old.get('directory', [])}
    state = dict(old.get('officials_state', {}))
    jur = cfg.get('jurisdictions', {})
    for key, fn in (('ny', discover_ny), ('ca', discover_ca), ('canada', discover_canada)):
        settings = jur.get(key)
        if not settings or not settings.get('enabled', True):
            continue
        try:
            found, errs, cov, state[key] = fn(client, settings, old_catalog, state.get(key))
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
    notes['_state'] = state
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
