"""One XBRL filing (a 10-K or 10-Q) read in full: every fact with its context, the labels, the presentation tree of every
statement and note, the calculation (summation) relationships, the dimensional structure, and the SEC's own list of
reports (FilingSummary.xml: cover, statements, notes, policies, tables, details — each detail report tied to its note).

  files    FilingSummary.xml, the instance (<name>_htm.xml extracted by the SEC from inline XBRL, or the filing's .xml
           instance), <name>.xsd, _pre.xml, _cal.xml, _def.xml, _lab.xml — read from a folder (fetch() downloads them)
  facts    concept ("us-gaap:Revenues"), value (float for numbers, text for text blocks), context id, unit, decimals
  context  period (instant or start–end) and the dimensions (axis → member, both "prefix:Local")

Used by app/notes.py. Standard library + lxml (falls back to xml.etree)."""
import json
import re
import time
import urllib.request
from pathlib import Path

try:
    from lxml import etree as ET
except ImportError:                                      # pragma: no cover
    import xml.etree.ElementTree as ET

XL = '{http://www.w3.org/1999/xlink}'
LINK = '{http://www.xbrl.org/2003/linkbase}'
XBRLI = '{http://www.xbrl.org/2003/instance}'
XBRLDI = '{http://xbrl.org/2006/xbrldi}'
SUMMATION = 'summation-item'
LABEL_ROLES = {'label': 'label', 'terseLabel': 'terse', 'verboseLabel': 'verbose', 'totalLabel': 'total', 'periodStartLabel': 'start',
               'periodEndLabel': 'end', 'negatedLabel': 'negated', 'negatedTerseLabel': 'negated', 'negatedTotalLabel': 'negated_total',
               'documentation': 'doc'}


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def concept_of_href(href):
    """'nvda-20260125.xsd#us-gaap_Revenues' or 'https://xbrl.fasb.org/…#us-gaap_Revenues' → 'us-gaap:Revenues'."""
    frag = href.split('#', 1)[-1]
    if '_' not in frag:
        return frag
    pre, loc = frag.split('_', 1)
    return pre + ':' + loc


def _parse(path):
    return ET.parse(str(path)).getroot()


# ------------------------------------------------------------------ the SEC's report list
def filing_summary(path):
    """FilingSummary.xml → [{r, long, short, role, cat (Cover/Statements/Notes/Policies/Tables/Details/…), parent, pos}]."""
    root = _parse(path)
    out = []
    for rep in root.iter('Report'):
        g = lambda k: (rep.findtext(k) or '').strip()
        if not g('Role'):
            continue
        out.append({'r': g('HtmlFileName').replace('.htm', '').replace('.xml', ''), 'long': g('LongName'), 'short': g('ShortName'),
                    'role': g('Role'), 'cat': g('MenuCategory'), 'parent': g('ParentRole') or None,
                    'pos': int(g('Position') or 0)})
    return out


# ------------------------------------------------------------------ instance
def instance(path):
    """→ contexts {id: {'i' | 's','e', 'dims': {axis: member}}}, units {id: 'USD' | 'shares' | 'USD/shares' …}, facts [..]."""
    root = _parse(path)
    nsmap = {}
    for el in root.iter():
        nsmap.update({v: k for k, v in (getattr(el, 'nsmap', None) or {}).items() if k})
        break
    if not nsmap:                                        # xml.etree: read the prefixes from the text
        txt = Path(path).read_text(encoding='utf-8', errors='replace')[:20000]
        nsmap = {u: p for p, u in re.findall(r'xmlns:([\w-]+)="([^"]+)"', txt)}
    ctx, units, facts = {}, {}, []
    for c in root.iter(XBRLI + 'context'):
        p = c.find(XBRLI + 'period')
        rec = {'dims': {}}
        if p.find(XBRLI + 'instant') is not None:
            rec['i'] = p.findtext(XBRLI + 'instant').strip()[:10]
        else:
            rec['s'], rec['e'] = p.findtext(XBRLI + 'startDate').strip()[:10], p.findtext(XBRLI + 'endDate').strip()[:10]
        for m in c.iter(XBRLDI + 'explicitMember'):
            rec['dims'][m.get('dimension')] = (m.text or '').strip()
        for m in c.iter(XBRLDI + 'typedMember'):
            rec['dims'][m.get('dimension')] = 'typed:' + ''.join(m.itertext()).strip()
        ctx[c.get('id')] = rec
    for u in root.iter(XBRLI + 'unit'):
        me = [(_local(x.tag), (x.text or '').strip().split(':')[-1]) for x in u.iter() if _local(x.tag) == 'measure']
        num = [m for t, m in me]
        div = u.find(XBRLI + 'divide')
        if div is not None:
            n = [x.text.split(':')[-1] for x in div.find(XBRLI + 'unitNumerator').iter(XBRLI + 'measure')]
            d = [x.text.split(':')[-1] for x in div.find(XBRLI + 'unitDenominator').iter(XBRLI + 'measure')]
            units[u.get('id')] = '*'.join(n) + '/' + '*'.join(d)
        else:
            units[u.get('id')] = '*'.join(num)
    for el in root:
        cref = el.get('contextRef')
        if cref is None:
            continue
        tag = el.tag
        if not isinstance(tag, str) or not tag.startswith('{'):
            continue
        uri, loc = tag[1:].split('}', 1)
        pre = nsmap.get(uri) or uri.rsplit('/', 2)[-2]
        nil = el.get('{http://www.w3.org/2001/XMLSchema-instance}nil') in ('true', '1')
        raw = (el.text or '') if len(el) == 0 else ET.tostring(el, encoding='unicode', method='xml')
        unit = el.get('unitRef')
        val = None
        if not nil:
            if unit:
                try:
                    val = float(raw.strip())
                except ValueError:
                    val = None
            else:
                val = raw.strip()
        facts.append({'c': pre + ':' + loc, 'v': val, 'ctx': cref, 'u': units.get(unit) if unit else None, 'd': el.get('decimals'),
                      'id': el.get('id')})
    return ctx, units, facts


# ------------------------------------------------------------------ linkbases
def labels(path):
    """_lab.xml → {concept: {'label', 'terse', 'total', 'start', 'end', 'negated', 'verbose', 'doc'}} (English)."""
    root = _parse(path)
    out = {}
    for lk in root.iter(LINK + 'labelLink'):
        locs = {l.get(XL + 'label'): concept_of_href(l.get(XL + 'href')) for l in lk.iter(LINK + 'loc')}
        res = {}
        for lab in lk.iter(LINK + 'label'):
            lang = lab.get('{http://www.w3.org/XML/1998/namespace}lang') or 'en'
            if not lang.startswith('en'):
                continue
            role = (lab.get(XL + 'role') or '').rsplit('/', 1)[-1]
            res.setdefault(lab.get(XL + 'label'), []).append((LABEL_ROLES.get(role, role), ' '.join((lab.text or '').split())))
        for arc in lk.iter(LINK + 'labelArc'):
            c = locs.get(arc.get(XL + 'from'))
            for role, text in res.get(arc.get(XL + 'to'), []):
                out.setdefault(c, {})[role] = text
    return out


def _arcs(path, link, arc_tag):
    """Any linkbase → {role: [(from_concept, to_concept, attrs)]}."""
    root = _parse(path)
    out = {}
    for lk in root.iter(LINK + link):
        role = lk.get(XL + 'role')
        locs = {l.get(XL + 'label'): concept_of_href(l.get(XL + 'href')) for l in lk.iter(LINK + 'loc')}
        lst = out.setdefault(role, [])
        for a in lk.iter(LINK + arc_tag):
            if a.get('use') == 'prohibited':
                continue
            lst.append((locs.get(a.get(XL + 'from')), locs.get(a.get(XL + 'to')),
                        {'order': float(a.get('order') or 0), 'pref': (a.get('preferredLabel') or '').rsplit('/', 1)[-1] or None,
                         'weight': float(a.get('weight')) if a.get('weight') else None, 'arcrole': (a.get(XL + 'arcrole') or '').rsplit('/', 1)[-1]}))
    return out


def presentation(path):
    """_pre.xml → {role: [nodes in document order: {'c', 'depth', 'pref'}]} (the tree flattened, as the report shows it)."""
    arcs = _arcs(path, 'presentationLink', 'presentationArc')
    out = {}
    for role, lst in arcs.items():
        kids, has_parent = {}, set()
        for f, t, a in lst:
            kids.setdefault(f, []).append((a['order'], t, a['pref']))
            has_parent.add(t)
        roots = [f for f in kids if f not in has_parent]
        seq = []

        def walk(c, depth, pref, seen):
            seq.append({'c': c, 'depth': depth, 'pref': LABEL_ROLES.get(pref, pref) if pref else None})
            if c in seen:
                return
            for o, t, p in sorted(kids.get(c, []), key=lambda x: x[0]):
                walk(t, depth + 1, p, seen | {c})
        for r in roots:
            walk(r, 0, None, frozenset())
        out[role] = seq
    return out


def calculation(path):
    """_cal.xml → {role: {parent: [(child, weight)]}}."""
    out = {}
    for role, lst in _arcs(path, 'calculationLink', 'calculationArc').items():
        d = out.setdefault(role, {})
        for f, t, a in lst:
            if a['arcrole'].startswith(SUMMATION):
                d.setdefault(f, []).append((t, a['weight'] if a['weight'] is not None else 1.0))
    return out


def definition(path):
    """_def.xml → {role: {'axes': {axis: [members, domain first]}, 'items': set(line items), 'closed'}}."""
    out = {}
    for role, lst in _arcs(path, 'definitionLink', 'definitionArc').items():
        dims, dm, items = {}, {}, set()
        hyper = set()
        for f, t, a in lst:
            ar = a['arcrole']
            if ar == 'hypercube-dimension':
                dims.setdefault(t, [])
                hyper.add(f)
            elif ar in ('dimension-domain', 'dimension-default'):
                if ar == 'dimension-domain':
                    dims.setdefault(f, []).insert(0, t)
                dm.setdefault(f, [])
            elif ar == 'domain-member':
                dm.setdefault(f, []).append(t)
            elif ar == 'all':
                items.add(f)
        axes = {}
        for ax, doms in dims.items():
            mem, stack = [], list(doms)
            while stack:
                m = stack.pop(0)
                if m in mem:
                    continue
                mem.append(m)
                stack[0:0] = dm.get(m, [])
            axes[ax] = mem
        out[role] = {'axes': axes, 'items': items}
    return out


def role_titles(xsd_path):
    """The extension schema's roleType definitions: {role URI: '9952153 - Disclosure - Debt (Details)'}."""
    root = _parse(xsd_path)
    out = {}
    for rt in root.iter(LINK + 'roleType'):
        out[rt.get('roleURI')] = (rt.findtext(LINK + 'definition') or '').strip()
    return out


# ------------------------------------------------------------------ fetch
def fetch(cik, accession, folder, ua, sleep=0.15, http_get=None):
    """Download one filing's XBRL files into folder (skipping files already there). → {kind: path}."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}'

    def get(url):
        if http_get:
            return http_get(url)
        req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    idx_p = folder / 'index.json'
    if not idx_p.exists():
        idx_p.write_bytes(get(base + '/index.json'))
        time.sleep(sleep)
    names = [it['name'] for it in json.loads(idx_p.read_text())['directory']['item']]
    pick = {}
    for n in names:
        lo = n.lower()
        if lo == 'filingsummary.xml':
            pick['summary'] = n
        elif lo.endswith('_htm.xml'):
            pick['instance'] = n
        elif lo.endswith('_pre.xml'):
            pick['pre'] = n
        elif lo.endswith('_cal.xml'):
            pick['cal'] = n
        elif lo.endswith('_def.xml'):
            pick['def'] = n
        elif lo.endswith('_lab.xml'):
            pick['lab'] = n
        elif lo.endswith('.xsd'):
            pick['xsd'] = n
    if 'instance' not in pick:                          # older filings: the plain .xml instance
        xs = [n for n in names if n.lower().endswith('.xml') and not re.search(r'_(pre|cal|def|lab)\.xml$|filingsummary', n.lower())]
        if xs:
            pick['instance'] = max(xs, key=len)
    out = {}
    for k, n in pick.items():
        p = folder / n
        if not p.exists() or not p.stat().st_size:
            p.write_bytes(get(base + '/' + n))
            time.sleep(sleep)
        out[k] = p
    for k in ('pre', 'cal', 'def', 'lab'):               # linkbases embedded in the schema (some filing agents do this)
        if k not in out and 'xsd' in out:
            out[k] = out['xsd']
    return out


def load(paths):
    """Every part of one filing from fetch()'s paths → a dict the notes builder reads."""
    ctx, units, facts = instance(paths['instance'])
    return {'reports': filing_summary(paths['summary']) if 'summary' in paths else [], 'contexts': ctx, 'units': units, 'facts': facts,
            'labels': labels(paths['lab']) if 'lab' in paths else {}, 'pre': presentation(paths['pre']) if 'pre' in paths else {},
            'cal': calculation(paths['cal']) if 'cal' in paths else {}, 'def': definition(paths['def']) if 'def' in paths else {},
            'roles': role_titles(paths['xsd']) if 'xsd' in paths else {}}
