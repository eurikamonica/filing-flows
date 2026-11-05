"""The data catalog (scripts/data_catalog.py, config/data-catalog.json → data/catalog.json, the page #data): each kind
measured in a built site — its homes' files and size, when it was made — the data no kind lists, identical files; and
the registry itself kept honest (unique ids, known groups, every script and workflow it names exists)."""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import data_catalog as C  # noqa: E402


def write(site, rel, data):
    p = site / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding='utf-8')
    return p


def test_registry_is_complete_and_names_real_files():
    reg = json.loads((ROOT / 'config' / 'data-catalog.json').read_text(encoding='utf-8'))
    groups = {g for g, _ in reg['groups']}
    ids = [k['id'] for k in reg['kinds']]
    assert len(ids) == len(set(ids)), 'every kind once'
    for k in reg['kinds']:
        for field in ('id', 'group', 'title', 'what', 'source', 'workflow', 'store', 'cadence', 'pages'):
            assert k.get(field), f"{k['id']}: {field}"
        assert k['group'] in groups, k['id']
        assert k.get('homes') or k.get('remote') or k.get('published') is False, f"{k['id']}: a home on the site, a remote address or none"
        folder = ''
        for part in (k.get('script') or '').split(','):
            p = part.strip()
            if not p:
                continue
            if '/' not in p:
                p = os.path.join(folder, p)        # "pipeline/a.py, b.py": b.py in the same folder
            folder = os.path.dirname(p)
            assert (ROOT / p).exists(), f"{k['id']}: {p}"
        for w in k['workflow'].split(','):
            assert (ROOT / '.github' / 'workflows' / w.strip()).exists(), f"{k['id']}: {w}"
    for o in reg['overlaps']:
        assert set(o['kinds']) <= set(ids) and o['what'] and o['plan'], o['title']


def test_measure_unlisted_and_duplicates():
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp)
        write(site, 'data/index.json', {'generated': '2026-11-05T14:00:00Z', 'companies': []})
        write(site, 'data/c/1.json', 'x' * 5000)
        write(site, 'data/c/2.json', 'x' * 5000)                                  # the same bytes as 1.json
        write(site, 'disclosures/data/etf/status.json', {'built_at': '2026-11-05T13:00:00+00:00'})
        write(site, 'disclosures/data/etf/px/SPY.json', 'y' * 6000)
        write(site, 'disclosures/data/live.json', {'modules': {'holdings': {'updated_at': '2026-11-04T08:16:12+00:00'}}})
        write(site, 'disclosures/data/market/new-thing.json', 'z' * 7000)       # in no kind's homes
        write(site, 'data/surprise/a.json', 'w' * 8000)
        reg = {'groups': [['g', 'G']], 'kinds': [
            {'id': 'companies', 'group': 'g', 'title': 'Charts', 'homes': ['data/index.json', 'data/c/'], 'fresh': ['data/index.json', 'generated']},
            {'id': 'etf', 'group': 'g', 'title': 'ETFs', 'homes': ['disclosures/data/etf/', 'disclosures/data/etf-old/']},
            {'id': 'holdings13f', 'group': 'g', 'title': '13F', 'homes': ['disclosures/data/live.json'], 'fresh': ['disclosures/data/live.json', 'modules.holdings.updated_at'],
             'remote': 'https://raw.githubusercontent.com/o/r/x/'},
        ], 'overlaps': [{'title': 'twice', 'kinds': ['companies', 'etf'], 'what': 'w', 'plan': 'p'}]}
        rp = write(site.parent / (site.name + '-reg'), 'r.json', reg)
        now = dt.datetime(2026, 11, 5, 15, 0, tzinfo=dt.timezone.utc)
        cat = C.build(site, rp, now=now, commit='abcdef1234567890')
        k = {x['id']: x for x in cat['kinds']}
        assert k['companies']['files'] == 3 and k['companies']['updated'] == '2026-11-05T14:00:00Z' and k['companies']['age_h'] == 1.0
        assert k['etf']['files'] == 2 and k['etf']['homes'][1] == {'path': 'disclosures/data/etf-old/', 'missing': True}
        assert k['etf']['updated'].startswith('2026-11-05T13'), 'the folder date: its status.json'
        assert k['holdings13f']['updated'].startswith('2026-11-04T08') and k['holdings13f']['remote']
        paths = {r['path']: r for r in cat['unlisted']}
        assert set(paths) == {'disclosures/data/market/new-thing.json', 'data/surprise/'}, paths
        assert paths['data/surprise/']['bytes'] == 8000
        d = cat['duplicates']
        assert d['groups'] == 1 and d['bytes'] == 5000 and d['top'][0]['paths'] == ['data/c/1.json', 'data/c/2.json']
        assert cat['overlaps'][0]['bytes'] == k['companies']['bytes'] + k['etf']['bytes']
        assert cat['commit'] == 'abcdef123456' and cat['totals']['data']['files'] == 4


def test_dates():
    assert C.when('2026-11-05').isoformat() == '2026-11-05T00:00:00+00:00'
    assert C.when('2026-11-05T14:00:00Z').hour == 14 and C.when('nope') is None and C.when(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        p = write(Path(tmp), 's.json', {'started': '2026-11-01', 'finished': '2026-11-02T01:00:00+00:00'})
        assert C.stamp(p) == '2026-11-02T01:00:00+00:00'
        assert C.stamp(p, 'started') == '2026-11-01' and C.stamp(p, 'missing.key') is None
        assert C.stamp(Path(tmp) / 'none.json') is None


def test_branches_named_by_the_catalog_and_the_rest():
    reg = {'kinds': [{'store': 'branch etf-history'}, {'store': 'branches model and fsa-question-bank'},
                     {'source': 'BEA tables (branches bea-refresh, mrio-refresh)'},
                     {'remote': 'https://raw.githubusercontent.com/o/filing-flows/notes-history/public/'}]}
    names = ['main', 'etf-history', 'model', 'fsa-question-bank', 'mrio-refresh', 'notes-history', 'probe-data', 'research/reversion-data',
             'feature/move-odds-history', 'research-old', 'codex/x']
    b = C.branches(reg, names)
    assert b['used'] == ['etf-history', 'fsa-question-bank', 'model', 'mrio-refresh', 'notes-history']
    assert b['unread'] == ['probe-data', 'research-old', 'research/reversion-data'], 'feature and code branches are not data branches'
