"""Discovery and XML loading integrated from the prior standalone 13F package."""
from urllib.parse import quote
from .core import xml, local, parse_filing, compare

def filing_list(client, cik, since):
    root = client.json(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json')
    blocks = [root['filings']['recent']]
    for extra in root['filings'].get('files', []):
        if extra.get('filingTo', '') >= since:
            blocks.append(client.json('https://data.sec.gov/submissions/' + quote(extra['name'])))
    records = {}
    for block in blocks:
        for i, form in enumerate(block.get('form', [])):
            if form not in ('13F-HR', '13F-HR/A', '13F-NT', '13F-NT/A'):
                continue
            def val(k):
                values = block.get(k, [])
                return values[i] if i < len(values) else ''
            if val('filingDate') < since:
                continue
            acc = val('accessionNumber')
            records[acc] = {'cik': str(int(cik)), 'accession': acc, 'form': form,
                            'filed': val('filingDate'), 'accepted': val('acceptanceDateTime'),
                            'primary': val('primaryDocument'),
                            'url': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{acc}-index.html'}
    return root.get('name', str(cik)), sorted(records.values(), key=lambda f: (f['filed'], f['accession']))


def load_filing(client, meta):
    base = f'https://www.sec.gov/Archives/edgar/data/{meta["cik"]}/{meta["accession"].replace("-", "")}/'
    listing = client.json(base + 'index.json')
    names = [x['name'] for x in listing['directory']['item'] if x['name'].lower().endswith('.xml') and '/' not in x['name']]
    cover, tables = None, []
    for name in names:
        body = client.get(base + quote(name), immutable=True)
        try:
            root = xml(body)
        except Exception:
            if name == meta['primary'].rsplit('/', 1)[-1]:
                raise
            continue
        tags = {local(e.tag) for e in root.iter()}
        if 'reportCalendarOrQuarter' in tags:
            if cover is not None:
                raise ValueError('Multiple cover documents')
            cover = body
        elif 'infoTable' in tags or local(root.tag) == 'informationTable':
            tables.append(body)
    if cover is None:
        raise ValueError('No supported XML cover (pre-May-2013 text filings unsupported)')
    return parse_filing(cover, tables, meta)



def demo():
    """Fictional data, never presented as real manager filings."""
    from .core import aggregate, key
    managers = []
    for n, manager in enumerate(('DEMO · Cedar Capital', 'DEMO · Harbor Partners')):
        snapshots = []
        for i, period in enumerate(('2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30')):
            rows = []
            for j, issuer in enumerate(('Aurora Technology', 'Northstar Systems', 'Cobalt Retail', 'Juniper Health', 'Atlas Energy', 'Pacific Payments')):
                q = (900-j*110+i*(70 if j%2==0 else -60)+n*40)*1000
                if (j==4 and i<2) or (j==5 and i==3):
                    continue
                row = dict(cusip=f'DEMO{j:05d}', issuer=issuer, **{'class':'COM'}, put_call='NONE', share_type='SH', shares=q, value_usd=q*(85+j*18+i*4))
                row['id'] = key(row)
                rows.append(row)
            positions = aggregate(rows)
            snap = {'period': period, 'filed': ('2025-11-14', '2026-02-13', '2026-05-15', '2026-08-14')[i], 'complete': True,
                    'confidential': False, 'warnings': [], 'sources': [], 'positions': positions,
                    'total_usd': sum(r['value_usd'] for r in positions), 'baseline_period': snapshots[-1]['period'] if snapshots else None}
            snap['changes'] = compare(snapshots[-1], snap) if snapshots else []
            snapshots.append(snap)
        managers.append({'cik': f'demo-{n}', 'name': manager, 'label': manager, 'snapshots': snapshots, 'notices': [], 'history_since':'2025-09-30', 'last_success': None})
    return managers


