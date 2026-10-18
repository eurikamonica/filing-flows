"""Pictures next to the names of 13F managers and public officials (published as data/avatars.json with the hub).

The owner edits disclosures/config/avatars.json in git:

    {
      "managers": {"<13F CIK>": {"image": "https://… or a file name in disclosures/config/avatars/", "label": "optional"}},
      "people":   {"<name as the disclosures write it>": {"image": "…"} or {"bioguide": "P000197"}},
      "congress_portraits": true
    }

- Members of Congress get their official portrait automatically (public domain, from the @unitedstates project:
  theunitedstates.io/images/congress/225x275/<bioguide>.jpg), matched by name to legislators-current.json.
- Anyone else (a fund, a person outside Congress) shows a picture only if the owner sets one; the page otherwise draws
  initials. Use images you are allowed to use.
- Image files dropped into disclosures/config/avatars/ are published at disclosures/data/avatars/<file>.
The same name key is computed here and in the pages (web/app.js avKey, disclosures/docs/market.js avKey).
"""
import json
import re
import shutil
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'avatars.json'
IMAGES = ROOT / 'config' / 'avatars'
DATA = ROOT / 'docs' / 'data'
LEGISLATORS = 'https://unitedstates.github.io/congress-legislators/legislators-current.json'
PORTRAIT = 'https://theunitedstates.io/images/congress/225x275/{}.jpg'
TITLES = {'hon', 'honorable', 'dr', 'mr', 'mrs', 'ms', 'rep', 'sen', 'senator', 'representative', 'the'}
SUFFIX = {'jr', 'sr', 'ii', 'iii', 'iv', 'md', 'phd', 'esq', 'cpa'}


def person_key(name):
    """'Hon. Nancy Pelosi' / 'Nancy P. Pelosi' / 'PELOSI, NANCY' → 'nancy pelosi' (first + last word, no titles,
    initials or suffixes)."""
    s = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    if ',' in s and s.count(',') == 1 and not re.search(r',\s*(jr|sr|ii|iii|iv)\b', s):
        last, first = s.split(',')
        s = first + ' ' + last
    toks = [t for t in re.split(r'[^a-z]+', s) if t and t not in TITLES and t not in SUFFIX and len(t) > 1]
    if not toks:
        return ''
    return toks[0] if len(toks) == 1 else toks[0] + ' ' + toks[-1]


def org_key(name):
    s = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    return ' '.join(t for t in re.split(r'[^a-z0-9]+', s) if t)


def _image(v):
    img = (v or {}).get('image') or ''
    if img and not re.match(r'^https://', img):
        img = 'data/avatars/' + Path(img).name                  # a file in disclosures/config/avatars/
    return img


def legislators(fetch=True, timeout=20):
    if not fetch:
        return []
    try:
        with urllib.request.urlopen(urllib.request.Request(LEGISLATORS, headers={'User-Agent': 'FilingFlows/1.0'}), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        print(f'::warning::avatars: Congress list not fetched ({exc}); configured pictures only')
        return []


def build(out, names=(), managers_catalog=(), legis=None, cfg=None):
    """The published map: managers by CIK and by name key, people by name key."""
    cfg = cfg if cfg is not None else (json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {})
    out = Path(out)
    res = {'managers': {}, 'manager_names': {}, 'people': {}, 'note': 'Congress portraits: public domain (@unitedstates project). Other pictures: set by the site owner in disclosures/config/avatars.json.'}
    if legis is None:
        legis = legislators(cfg.get('congress_portraits', True))
    keymap = {}
    for m in legis:
        bid = (m.get('id') or {}).get('bioguide')
        n = m.get('name') or {}
        if not bid:
            continue
        for k in {person_key(n.get('official_full')), person_key(f"{n.get('first', '')} {n.get('last', '')}"),
                  person_key(f"{n.get('nickname', '')} {n.get('last', '')}") if n.get('nickname') else ''} - {''}:
            keymap.setdefault(k, set()).add(bid)
    wanted = {person_key(x) for x in names} - {''}
    for k in wanted:
        b = keymap.get(k)
        if b and len(b) == 1:
            bid = next(iter(b))
            res['people'][k] = {'image': PORTRAIT.format(bid), 'bioguide': bid, 'source': 'congress'}
    for name, v in (cfg.get('people') or {}).items():
        k = person_key(name)
        if not k:
            continue
        if v.get('bioguide'):
            res['people'][k] = {'image': PORTRAIT.format(v['bioguide']), 'bioguide': v['bioguide'], 'source': 'config'}
        elif _image(v):
            res['people'][k] = {'image': _image(v), 'source': 'config'}
    names_by_cik = {}
    for r in managers_catalog or ():
        names_by_cik.setdefault(str(int(r['cik'])), set()).add(r.get('name') or '')
    for cik, v in (cfg.get('managers') or {}).items():
        if cik.startswith('_') or not _image(v):
            continue
        c = str(int(cik))
        res['managers'][c] = {'image': _image(v), 'label': v.get('label')}
        for n in names_by_cik.get(c, set()) | {v.get('label') or ''}:
            if org_key(n):
                res['manager_names'][org_key(n)] = c
    if IMAGES.is_dir():
        dest = out / 'data' / 'avatars'
        dest.mkdir(parents=True, exist_ok=True)
        for f in IMAGES.iterdir():
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg') and f.stat().st_size < 400_000:
                shutil.copy(f, dest / f.name)
    (out / 'data').mkdir(parents=True, exist_ok=True)
    (out / 'data' / 'avatars.json').write_text(json.dumps(res, separators=(',', ':')), encoding='utf-8')
    return res


def officials_names(data=DATA):
    """Every official's name the hub publishes (machine-read House / Senate trades and reviewed records)."""
    names = set()
    try:
        names |= {t.get('person') for t in json.loads((data / 'market' / 'officials-trades.json').read_text(encoding='utf-8')).get('trades', [])}
    except Exception:
        pass
    try:
        live = json.loads((data / 'live.json').read_text(encoding='utf-8'))
        names |= {r.get('person') for r in (live.get('modules', {}).get('congress', {}) or {}).get('records', [])}
    except Exception:
        pass
    return {n for n in names if n}


def stage(out):
    try:
        cat = json.loads((DATA / 'catalogs' / 'holdings.json').read_text(encoding='utf-8'))
    except Exception:
        cat = []
    res = build(out, officials_names(), cat)
    print(f"avatars: {len(res['people'])} officials' portraits, {len(res['managers'])} managers' pictures")
    return res
