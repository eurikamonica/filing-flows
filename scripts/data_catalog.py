"""The data catalog: every kind of data the site publishes, measured in the built site at each deploy.

config/data-catalog.json names each kind — what it is, its source, its home on the site, the branch or store that keeps
it, the workflow and script that make it, how often, the pages that read it — and this script adds what only the build
can tell: each home's files and size, when the data was last made, every folder of the site's data that no kind lists
(not catalogued: a new data set cannot go unseen), and identical files published twice. It writes data/catalog.json,
which the page #data draws (web/catalog.js).

    python scripts/data_catalog.py --site _site [--registry config/data-catalog.json]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('built_at', 'finished', 'generated_at', 'generated', 'updated_at')   # when a data set says it was made
DATA_ROOTS = ('data', 'disclosures/data')                                    # where the built site keeps data
MAX_JSON = 80 << 20                     # a file larger than this is not read for its date
DUP_MIN, DUP_MAX = 4 << 10, 16 << 20    # files compared for identical copies (by size first, then by hash)


def walk(path):
    """(files, bytes) of a file or a folder."""
    if path.is_file():
        return 1, path.stat().st_size
    n = b = 0
    for dirpath, _, names in os.walk(path):
        for name in names:
            try:
                b += os.stat(os.path.join(dirpath, name)).st_size
                n += 1
            except OSError:
                pass
    return n, b


_READ = {}


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() and path.stat().st_size <= MAX_JSON else None
    except (OSError, ValueError):
        return None


def stamp(path, key=None):
    """When the data in this JSON file was made: its dotted key (modules.holdings.updated_at), or the first of KEYS at
    its top level. None when the file is missing, too large, not JSON or has no date. (A file asked for by key is read
    once: the hub's live.json dates several kinds.)"""
    if key:
        if path not in _READ:
            _READ[path] = read(path)
        d = _READ[path]
    else:
        d = read(path)
    if d is None:
        return None
    if key:
        for part in key.split('.'):
            d = d.get(part) if isinstance(d, dict) else None
        return d if isinstance(d, str) and d[:2] == '20' else None
    if isinstance(d, dict):
        for k in KEYS:
            v = d.get(k)
            if isinstance(v, str) and v[:2] == '20':
                return v
    return None


def folder_stamp(path):
    """A folder's date: its status.json, then index.json, then the first other JSON file that carries one."""
    for name in ('status.json', 'index.json'):
        t = stamp(path / name)
        if t:
            return t
    try:
        names = sorted(p for p in path.iterdir() if p.suffix == '.json')[:20]
    except OSError:
        return None
    for p in names:
        t = stamp(p)
        if t:
            return t
    return None


def when(s):
    """An ISO date or time → an aware datetime (a date alone: its midnight, UTC)."""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        try:
            t = dt.datetime.fromisoformat(str(s)[:10])
        except ValueError:
            return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def measure(site, kind, now):
    """One kind in the built site: each home's files and bytes (or missing), the total, and when it was last made."""
    homes, files, size, t = [], 0, 0, None
    for h in kind.get('homes') or []:
        p = site / h
        if not p.exists():
            homes.append({'path': h, 'missing': True})
            continue
        n, b = walk(p)
        homes.append({'path': h, 'files': n, 'bytes': b})
        files += n
        size += b
    fresh = kind.get('fresh')
    if fresh:
        t = stamp(site / fresh[0], fresh[1] if len(fresh) > 1 else None)
    for h in homes:
        if t:
            break
        if h.get('missing'):
            continue
        p = site / h['path']
        t = folder_stamp(p) if p.is_dir() else stamp(p)
    out = {k: kind[k] for k in ('id', 'group', 'title', 'what', 'source', 'workflow', 'script', 'store', 'cadence', 'pages', 'remote', 'note')
           if kind.get(k)}
    if kind.get('published') is False:
        out['published'] = False                          # a collector's own store: nothing of it is on the site
    out.update({'files': files, 'bytes': size, 'homes': homes})
    w = when(t)
    if w:
        out['updated'] = t
        out['age_h'] = round((now - w).total_seconds() / 3600, 1)
    return out


def covers(homes):
    """A test: is this site-relative path inside one of the homes (a folder home ends with /)?"""
    files = {h for h in homes if not h.endswith('/')}
    folders = tuple(h for h in homes if h.endswith('/'))
    return lambda rel: rel in files or rel.startswith(folders)


def unlisted(site, kinds, top=40):
    """Every file of the site's data that no kind's homes cover, summed by its folder (two levels under the data root:
    data/foo/, disclosures/data/market/bar.json): the data sets the catalog does not describe yet."""
    inside = covers([h for k in kinds for h in (k.get('homes') or [])])
    sums = defaultdict(lambda: [0, 0])
    for root in DATA_ROOTS:
        base = site / root
        if not base.is_dir():
            continue
        for dirpath, _, names in os.walk(base):
            for name in names:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, site).replace(os.sep, '/')
                if inside(rel):
                    continue
                parts = os.path.relpath(full, base).replace(os.sep, '/').split('/')
                depth = 2 if root == 'disclosures/data' and parts[0] in ('market', 'research', 'shards', 'catalogs', 'lazy') else 1
                key = root + '/' + '/'.join(parts[:depth]) + ('/' if len(parts) > depth else '')
                try:
                    sums[key][1] += os.stat(full).st_size
                    sums[key][0] += 1
                except OSError:
                    pass
    rows = [{'path': k, 'files': n, 'bytes': b} for k, (n, b) in sums.items()]
    return sorted(rows, key=lambda r: -r['bytes'])[:top], len(rows)


def duplicates(site, top=25):
    """Identical files in the site's data (same size, then the same SHA-1): how many groups, the bytes they repeat,
    the largest groups."""
    by_size = defaultdict(list)
    for root in DATA_ROOTS:
        base = site / root
        if not base.is_dir():
            continue
        for dirpath, _, names in os.walk(base):
            for name in names:
                full = os.path.join(dirpath, name)
                try:
                    s = os.stat(full).st_size
                except OSError:
                    continue
                if DUP_MIN <= s <= DUP_MAX:
                    by_size[s].append(full)
    groups = []
    for s, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash = defaultdict(list)
        for p in paths:
            try:
                with open(p, 'rb') as f:
                    by_hash[hashlib.sha1(f.read()).hexdigest()].append(os.path.relpath(p, site).replace(os.sep, '/'))
            except OSError:
                pass
        for same in by_hash.values():
            if len(same) > 1:
                groups.append({'bytes': s, 'copies': len(same), 'paths': sorted(same)[:6]})
    groups.sort(key=lambda g: -g['bytes'] * (g['copies'] - 1))
    return {'groups': len(groups), 'bytes': sum(g['bytes'] * (g['copies'] - 1) for g in groups), 'top': groups[:top]}


DATA_BRANCH = re.compile(r'(-history|-data|-refresh)$|^research-|probe|^(data|media|fastlane|model|fsa-question-bank)$')


def branches(reg, names):
    """The repository's data branches (named like one: *-history, *-data, research-*, probes …) split into the ones a
    kind names (its store or its remote address) and the ones nothing in the catalog reads."""
    text = json.dumps(reg['kinds'])
    named = set(re.findall(r'filing-flows/([a-z0-9_-]+)/', text))           # a remote address names its branch
    for m in re.findall(r'branch(?:es)? ([a-z0-9/_-]+(?:(?:, | and )[a-z0-9/_-]+)*)', text):   # "branches a, b and c"
        named |= set(re.split(r', | and ', m))
    data = sorted({n for n in names if DATA_BRANCH.search(n) and ('/' not in n or n.endswith('-data'))})   # not feature/…-history
    return {'used': [b for b in data if b in named], 'unread': [b for b in data if b not in named]}


def build(site, registry, now=None, commit='', branch_names=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    reg = json.loads(Path(registry).read_text(encoding='utf-8'))
    kinds = [measure(site, k, now) for k in reg['kinds']]
    rows, n_unlisted = unlisted(site, reg['kinds'])
    by_id = {k['id']: k for k in kinds}
    overlaps = [dict(o, bytes=sum(by_id[i]['bytes'] for i in o.get('kinds', []) if i in by_id)) for o in reg.get('overlaps', [])]
    totals = {}
    for root in DATA_ROOTS:
        if (site / root).is_dir():
            n, b = walk(site / root)
            totals[root] = {'files': n, 'bytes': b}
    return {'generated_at': now.isoformat(timespec='seconds'), 'commit': commit[:12], 'about': reg.get('about', ''),
            'groups': reg.get('groups', []), 'kinds': kinds, 'overlaps': overlaps,
            'unlisted': rows, 'unlisted_folders': n_unlisted, 'duplicates': duplicates(site), 'totals': totals,
            **({'branches': branches(reg, branch_names)} if branch_names else {})}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--site', default='_site', help='the built site')
    ap.add_argument('--registry', default=str(ROOT / 'config' / 'data-catalog.json'))
    ap.add_argument('--branches', help="the repository's branch names, one a line (git ls-remote --heads): data branches no kind reads are listed")
    args = ap.parse_args()
    site = Path(args.site)
    names = None
    if args.branches and Path(args.branches).is_file():
        names = [l.strip() for l in Path(args.branches).read_text(encoding='utf-8').splitlines() if l.strip()]
    cat = build(site, args.registry, commit=os.environ.get('GITHUB_SHA', ''), branch_names=names)
    out = site / 'data' / 'catalog.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cat, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    gb = sum(t['bytes'] for t in cat['totals'].values()) / 1e9
    missing = [f"{k['id']}: {h['path']}" for k in cat['kinds'] for h in k['homes'] if h.get('missing')]
    print(f"::notice::data catalog: {len(cat['kinds'])} kinds, {gb:.2f} GB of data in the site, {cat['unlisted_folders']} folders not "
          f"catalogued, {cat['duplicates']['groups']} identical-file groups ({cat['duplicates']['bytes'] / 1e6:.1f} MB repeated)")
    if missing:
        print(f"::warning::data catalog: homes not in this build: {', '.join(missing[:12])}")
    if cat.get('branches', {}).get('unread'):
        print(f"::notice::data catalog: data branches no kind reads: {', '.join(cat['branches']['unread'])}")
    big = [f"{r['path']} ({r['bytes'] / 1e6:.0f} MB)" for r in cat['unlisted'] if r['bytes'] > 20e6]
    if big:
        print(f"::warning::data catalog: large data not in config/data-catalog.json: {', '.join(big[:8])}")


if __name__ == '__main__':
    main()
