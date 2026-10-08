"""Parse EDGAR XML, preserve amendments and compare disclosed positions."""
from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime
import xml.etree.ElementTree as ET


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD/entities are not supported')
    return ET.fromstring(data)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def field(root, name, default=''):
    return next(((e.text or '').strip() for e in root.iter() if local(e.tag) == name), default)


def number(value):
    n = Decimal(value.replace(',', ''))
    if not n.is_finite() or n < 0:
        raise ValueError('Invalid nonnegative amount: ' + value)
    return int(n) if n == n.to_integral_value() else float(n)


def key(row):
    return '|'.join(str(row[k]).strip().upper() for k in ('cusip', 'class', 'put_call', 'share_type'))


def parse_filing(cover_bytes, table_bytes, meta):
    root = xml(cover_bytes)
    period = field(root, 'reportCalendarOrQuarter') or field(root, 'periodOfReport')
    for pattern in ('%Y-%m-%d', '%m-%d-%Y', '%m/%d/%Y'):
        try:
            period = datetime.strptime(period, pattern).date().isoformat()
            break
        except ValueError:
            pass
    date.fromisoformat(period)
    amended = meta['form'].endswith('/A')
    amendment = field(root, 'amendmentType').upper()
    if amended and amendment not in ('RESTATEMENT', 'NEW HOLDINGS'):
        raise ValueError('Unknown amendment type; manual review required')
    # Convention changed with the amended form, not with the report quarter.
    multiplier = 1 if meta['filed'] >= '2023-01-03' else 1000
    rows = []
    for content in table_bytes:
        for e in xml(content).iter():
            if local(e.tag) != 'infoTable':
                continue
            row = {'issuer': field(e, 'nameOfIssuer'), 'class': field(e, 'titleOfClass'),
                   'cusip': field(e, 'cusip').upper().replace(' ', ''),
                   'put_call': field(e, 'putCall').upper() or 'NONE',
                   'share_type': field(e, 'sshPrnamtType').upper(),
                   'shares': number(field(e, 'sshPrnamt')),
                   'value_usd': number(field(e, 'value')) * multiplier,
                   'discretion': field(e, 'investmentDiscretion'),
                   'other_manager': field(e, 'otherManager'),
                   'voting_sole': field(e, 'Sole'), 'voting_shared': field(e, 'Shared'),
                   'voting_none': field(e, 'None')}
            if len(row['cusip']) != 9 or row['share_type'] not in ('SH', 'PRN') or row['put_call'] not in ('NONE', 'PUT', 'CALL'):
                raise ValueError('Invalid security identity or quantity type')
            row['id'] = key(row)
            rows.append(row)
    count = field(root, 'tableEntryTotal')
    total = field(root, 'tableValueTotal')
    if count == '' or total == '':
        raise ValueError('Missing summary totals')
    if int(count) != len(rows):
        raise ValueError(f'Entry reconciliation failed: {len(rows)} vs {count}')
    expected = number(total) * multiplier
    actual = sum(r['value_usd'] for r in rows)
    # Rounding in an older form can yield a small aggregate difference.
    if abs(actual - expected) > max(1, len(rows)) * multiplier:
        raise ValueError(f'Value reconciliation failed: {actual} vs {expected}')
    return {**meta, 'period': period, 'amendment': amendment if amended else 'ORIGINAL',
            'manager': field(root, 'name'), 'report_type': field(root, 'reportType'),
            'confidential': field(root, 'isConfidentialOmitted').lower() in ('true', '1'),
            'unit_multiplier': multiplier, 'reported_total_usd': expected, 'rows': rows}


def aggregate(rows):
    out = {}
    for r in rows:
        if r['id'] not in out:
            out[r['id']] = {**r, 'shares': 0, 'value_usd': 0, 'line_count': 0}
        out[r['id']]['shares'] += r['shares']
        out[r['id']]['value_usd'] += r['value_usd']
        out[r['id']]['line_count'] += 1
    total = sum(r['value_usd'] for r in out.values())
    for r in out.values():
        r['weight'] = r['value_usd'] / total if total else 0
    return sorted(out.values(), key=lambda r: (-r['value_usd'], r['id']))


def resolve(filings, as_of=None):
    """Latest restated view, or only records publicly filed by as_of (ISO date)."""
    groups = defaultdict(list)
    for f in filings:
        if as_of is None or f['filed'] <= as_of:
            groups[f['period']].append(f)
    result = []
    for period, fs in sorted(groups.items()):
        rows, chain, base, confidential, warnings = [], [], False, False, []
        for f in sorted(fs, key=lambda f: (f.get('accepted') or f['filed'], f['accession'])):
            kind = f['amendment']
            if kind in ('ORIGINAL', 'RESTATEMENT'):
                if kind == 'ORIGINAL' and base:
                    warnings.append('Multiple original filings for this quarter; manual review required')
                rows = list(f['rows'])
                base = True
                chain = [f]
                confidential = f['confidential']
            elif kind == 'NEW HOLDINGS':
                if not base:
                    warnings.append('Missing original/restatement; comparison disabled')
                rows.extend(f['rows'])
                chain.append(f)
                confidential = confidential or f['confidential']
        if not chain:
            continue
        positions = aggregate(rows)
        result.append({'period': period, 'filed': chain[-1]['filed'],
                       'available_at': chain[-1].get('accepted') or chain[-1]['filed'],
                       'sources': [{k: f.get(k) for k in ('accession', 'filed', 'accepted', 'url', 'amendment')} for f in chain],
                       'complete': base and not warnings, 'confidential': confidential,
                       'warnings': warnings, 'total_usd': sum(r['value_usd'] for r in positions),
                       'positions': positions})
    return result


def compare(prior, current):
    if not prior.get('complete') or not current.get('complete'):
        return []
    old = {r['id']: r for r in prior['positions']}
    new = {r['id']: r for r in current['positions']}
    result = []
    for identity in sorted(old.keys() | new.keys()):
        a, b = old.get(identity), new.get(identity)
        q0, q1 = (a or {}).get('shares', 0), (b or {}).get('shares', 0)
        v0, v1 = (a or {}).get('value_usd', 0), (b or {}).get('value_usd', 0)
        status = 'NEW' if not a else 'EXIT' if not b else 'INCREASE' if q1 > q0 else 'DECREASE' if q1 < q0 else 'UNCHANGED'
        result.append({**(b or a), 'status': status, 'prior_shares': q0, 'shares': q1,
                       'delta_shares': q1-q0, 'delta_pct': (q1/q0-1)*100 if q0 else None,
                       'prior_value_usd': v0, 'value_usd': v1, 'delta_value_usd': v1-v0,
                       'weight': (b or {}).get('weight', 0),
                       'delta_weight_pp': ((b or {}).get('weight', 0)-(a or {}).get('weight', 0))*100})
    return sorted(result, key=lambda r: -abs(r['delta_value_usd']))
