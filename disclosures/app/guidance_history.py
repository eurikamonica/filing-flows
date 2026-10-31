"""Guidance history (4.7 add-on): every earnings release's guidance per company, kept beyond the 8-K window.

The 8-K store (app/events8k.py) keeps 120 days, about one or two releases per company: enough to tell whether the latest
release raised or lowered its guidance, not enough for a track record. This keeps each company's releases with
guidance for good (the last `keep` releases), so the site can show:

  - the record of moves: each guided period's ranges release after release (raised / lowered / narrowed / widened /
    reaffirmed), e.g. a full year guided in February, raised in May, raised and narrowed in August;
  - the hit rate: the guided range against what the company then reported (web/guidance.js compares it with the
    company's own figures, GAAP or basis-free lines only).

Store:  cache/guidance/<cik>.json.gz — {'cik', 'releases': [{accession, filed, url, label, tags, items}] newest first,
        'backfill': {'done', 'checked_at', 'tried': {accession: failures}}}
collect(client, root, cfg):
  1. every 8-K row with guidance on file (the 8-K store) is copied in — the store fills as new releases are read;
  2. releases read with an older guidance reader (guidance.VERSION) are read again, `reread` per run, so a fix reaches
     the whole record (a guided period dated a year early by a comparison base: "compared with fourth quarter 2025");
  3. companies not on file yet, largest first (SEC's company list): the latest earnings release of `discover` companies
     per run is read, and one with guidance figures starts its history — the 8-K store keeps only recent weeks, so
     a company reporting off the main season (NVIDIA, Salesforce, Walmart …) would otherwise never be found;
  4. a few older earnings releases per run (`budget`, newest first) for the companies that guide: the company's list of
     filings (data.sec.gov/submissions), its 8-Ks with item 2.02 of the last `years` years, each read once with
     events8k.parse_8k (the same reader as the 8-K events).
publish(root) → ticker → {'releases': [...]} (compact: no quotes, no segment figures) for the holders files.
"""
import datetime as dt
from pathlib import Path

from core import now, read_gz, read_json, write_gz, write_json
import guidance as G
import ownership as OWN

SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
KEEP = 16                     # releases kept per company (four years of quarters)
ITEM_KEYS = ('metric', 'name', 'basis', 'period', 'unit', 'lo', 'hi', 'approx', 'bound', 'said', 'said_range', 'change', 'range',
             'ends', 'prior')


def home(root):
    return Path(root) / 'cache' / 'guidance'


def load(root, cik):
    return read_gz(home(root) / f'{int(cik)}.json.gz', None) or {'cik': str(int(cik)), 'releases': [], 'backfill': {}}


def save(root, doc):
    doc['releases'] = sorted({r['accession']: r for r in doc['releases']}.values(), key=lambda r: (r.get('filed') or '', r['accession']),
                             reverse=True)[:KEEP]
    return write_gz(home(root) / f"{int(doc['cik'])}.json.gz", doc)


def compact(it):
    """An item as kept in the history: the figures and the change words, not the sentence."""
    out = {k: it[k] for k in ITEM_KEYS if it.get(k) not in (None, '', [])}
    if 'prior' in out:
        out['prior'] = {k: v for k, v in out['prior'].items() if k in ('lo', 'hi', 'src', 'filed')}
    return out


def release_of(row):
    """An 8-K row (events8k.parse_8k) → a history release, or None when it has no guidance figures."""
    items = [compact(it) for it in row.get('guidance_items') or [] if not it.get('scope')]
    if not items:
        return None
    return {'accession': row['accession'], 'filed': row.get('filed'), 'url': row.get('url'), 'label': row.get('guidance'),
            'tags': row.get('guidance_tags') or [], 'items': items, 'gv': int(row.get('gv') or 1)}


def add(doc, rel):
    """True when the release is new to the company's history (a re-read release replaces the stored one)."""
    old = next((r for r in doc['releases'] if r['accession'] == rel['accession']), None)
    if old == rel:
        return False
    doc['releases'] = [r for r in doc['releases'] if r['accession'] != rel['accession']] + [rel]
    return True


def from_events(root):
    """Copies the 8-K store's releases with guidance into the companies' histories. → {cik: doc} of the ones changed."""
    import events8k as E
    changed = {}
    for row in E.store(root).all():
        rel = release_of(row) if row.get('cik') else None
        if not rel:
            continue
        cik = row['cik']
        doc = changed.get(cik) or load(root, cik)
        if add(doc, rel):
            changed[cik] = doc
    return changed


def earnings_8ks(sub, since):
    """(accession, folder, filed) of a company's 8-Ks with item 2.02 since a date, newest first (EDGAR submissions JSON)."""
    rec = (sub.get('filings') or {}).get('recent') or {}
    cik = int(sub.get('cik') or 0)
    out = []
    for i, form in enumerate(rec.get('form') or []):
        if form not in ('8-K', '8-K/A'):
            continue
        items = str((rec.get('items') or [''] * (i + 1))[i] or '')
        filed = (rec.get('filingDate') or [''] * (i + 1))[i]
        acc = (rec.get('accessionNumber') or [''] * (i + 1))[i]
        if '2.02' not in items or not acc or (filed or '') < since:
            continue
        out.append((acc, f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/', filed))
    return sorted(out, key=lambda x: x[2], reverse=True)


def _read_release(client, acc, folder):
    import events8k as E
    txt = client.get(folder + acc + '.txt', sec=True).decode('utf-8', 'replace')
    return release_of(E.parse_8k(txt, acc, folder))


def _old(r):
    return int(r.get('gv') or 1) < G.VERSION


def reread(client, root, budget):
    """Releases kept from an older guidance reader (their 'gv') read again with the current one, the most recent companies
    first; a release that no longer has guidance figures is dropped. → (releases read, errors, companies finished)."""
    queue = []
    for p in sorted(home(root).glob('*.json.gz')) if home(root).exists() else []:
        if p.name.startswith('_'):
            continue
        doc = read_gz(p, None)
        if doc and any(_old(r) for r in doc.get('releases') or []):
            queue.append(doc)
    queue.sort(key=lambda d: d['releases'][0].get('filed') or '', reverse=True)
    read = errors = finished = 0
    for doc in queue:
        if read >= budget or errors > 5:
            break
        for r in [x for x in doc['releases'] if _old(x)]:
            if read >= budget or errors > 5:
                break
            read += 1
            try:
                rel = _read_release(client, r['accession'], r.get('url') or '')
            except Exception as exc:
                errors += 1
                print(f'guidance history re-read {r["accession"]}: {exc}', flush=True)
                continue
            doc['releases'] = [x for x in doc['releases'] if x['accession'] != r['accession']] + ([rel] if rel else [])
        finished += int(not any(_old(x) for x in doc['releases']))
        if doc['releases']:
            save(root, doc)
        else:
            (home(root) / f"{int(doc['cik'])}.json.gz").unlink(missing_ok=True)
    return read, errors, finished


def ranked_ciks(root):
    """Issuer CIKs in the order of SEC's company list (largest first), one per company."""
    out, seen = [], set()
    for r in (read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
        c = str(r.get('cik') or '').lstrip('0')
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def discover(client, root, budget, since, today, top=1500, recheck_days=100):
    """The latest earnings release of companies with no history yet, largest first; one with guidance figures starts a
    history (its earlier releases are then back-filled like the others). A company found without guidance is asked again
    after `recheck_days`. State: cache/guidance/_discover.json {cik: {at, acc, g}}. → (releases read, started, errors)."""
    path = home(root) / '_discover.json'
    st = read_json(path, {})
    have = {p.name.split('.')[0] for p in home(root).glob('*.json.gz')} if home(root).exists() else set()
    stale = (today - dt.timedelta(days=recheck_days)).isoformat()
    todo = [c for c in ranked_ciks(root)[:top] if c not in have and (c not in st or (st[c].get('at') or '') < stale)]
    todo.sort(key=lambda c: c in st)                    # never asked first, in size order
    read = started = errors = 0
    for cik in todo:
        if read >= budget or errors > 5:
            break
        try:
            sub = client.json(SUBMISSIONS.format(cik=int(cik)), sec=True)
            rels = earnings_8ks(sub, since)
            rec = {'at': today.isoformat()}
            if rels and (st.get(cik) or {}).get('acc') != rels[0][0]:
                read += 1
                rel = _read_release(client, rels[0][0], rels[0][1])
                rec.update(acc=rels[0][0], g=bool(rel))
                if rel:
                    doc = load(root, cik)
                    add(doc, rel)
                    save(root, doc)
                    started += 1
            elif rels:
                rec.update(acc=rels[0][0], g=False)
            st[cik] = rec
        except Exception as exc:
            errors += 1
            print(f'guidance discovery {cik}: {exc}', flush=True)
    write_json(path, st)
    return read, started, errors


def collect(client, root, cfg=None, today=None):
    """Copies new releases in, re-reads releases kept from an older reader, finds companies not on file yet, then reads up
    to `budget` older earnings releases of the companies that guide."""
    import events8k as E
    cfg = cfg or {}
    today = today or dt.date.today()
    budget = int(cfg.get('budget', 8))
    years = float(cfg.get('years', 3))
    since = (today - dt.timedelta(days=int(365 * years))).isoformat()
    docs = from_events(root)
    written = sum(1 for d in docs.values() if save(root, d))
    re_read, re_err, re_done = reread(client, root, int(cfg.get('reread', 40)))
    d_read, d_started, d_err = discover(client, root, int(cfg.get('discover', 20)), since, today, int(cfg.get('discover_top', 1500)))
    # the companies to back-fill: the ones with guidance on file whose earlier releases have not been read yet, the
    # most recent guidance first
    queue = []
    for p in sorted(home(root).glob('*.json.gz')) if home(root).exists() else []:
        if p.name.startswith('_'):
            continue
        doc = read_gz(p, None)
        if doc and not (doc.get('backfill') or {}).get('done') and doc.get('releases'):
            queue.append(doc)
    rank = {c: i for i, c in enumerate(ranked_ciks(root))}       # the largest companies first, then the latest guidance
    queue.sort(key=lambda d: d['releases'][0].get('filed') or '', reverse=True)
    queue.sort(key=lambda d: rank.get(str(d['cik']).lstrip('0'), 10 ** 6))
    read, errors, done = 0, 0, 0
    for doc in queue:
        if read >= budget or errors > 5:
            break
        bf = doc.setdefault('backfill', {})
        try:
            sub = client.json(SUBMISSIONS.format(cik=int(doc['cik'])), sec=True)
        except Exception as exc:
            errors += 1
            print(f'guidance history {doc["cik"]}: {exc}', flush=True)
            continue
        have = {r['accession'] for r in doc['releases']}
        tried = bf.setdefault('tried', {})
        todo = [x for x in earnings_8ks(sub, since) if x[0] not in have and tried.get(x[0], 0) < 3][:KEEP]
        for acc, folder, filed in todo:
            if read >= budget:
                break
            read += 1
            try:
                txt = client.get(folder + acc + '.txt', sec=True).decode('utf-8', 'replace')
                rel = release_of(E.parse_8k(txt, acc, folder))
                if rel:
                    add(doc, rel)
                else:
                    tried[acc] = 3                   # read: no guidance in it
            except Exception as exc:
                errors += 1
                tried[acc] = tried.get(acc, 0) + 1
                print(f'guidance history {acc}: {exc}', flush=True)
        left = [x for x in earnings_8ks(sub, since) if x[0] not in {r['accession'] for r in doc['releases']} and tried.get(x[0], 0) < 3]
        bf.update({'checked_at': now(), 'done': not left})
        bf['tried'] = {k: v for k, v in tried.items() if v < 3 or k in {x[0] for x in earnings_8ks(sub, since)}}
        done += int(not left)
        if save(root, doc):
            written += 1
    return {'status': 'partial' if errors or re_err or d_err else 'ok',
            'companies': len([p for p in home(root).glob('*.json.gz') if not p.name.startswith('_')]) if home(root).exists() else 0,
            'new_from_8k': len(docs), 'read': read, 'errors': errors + re_err + d_err, 'backfilled': done, 'waiting': max(0, len(queue) - done),
            're_read': re_read, 're_read_done': re_done, 'discover_read': d_read, 'discovered': d_started,
            'written': written, 'updated_at': now()}


def publish(root, keep=12):
    """ticker → {'releases': [...]}: each company's releases with guidance, newest first (holders files)."""
    tickers = OWN.cik_tickers(root)
    out = {}
    for p in sorted(home(root).glob('*.json.gz')) if home(root).exists() else []:
        if p.name.startswith('_'):
            continue
        doc = read_gz(p, None)
        t = tickers.get(str((doc or {}).get('cik') or '').lstrip('0'))
        if not t or not doc.get('releases'):
            continue
        out[t] = {'releases': [{k: r.get(k) for k in ('filed', 'accession', 'url', 'label', 'tags', 'items')} for r in doc['releases'][:keep]],
                  'complete': bool((doc.get('backfill') or {}).get('done'))}
    return out


def earlier(root, cik, accession, filed=None):
    """[(filed, items, accession)] of a company's releases before the given one, newest first (the prior ranges of
    events8k.guidance_by_ticker: a full year guided five months ago is still on file here)."""
    doc = load(root, cik)
    return [(r.get('filed'), r['items'], r['accession']) for r in doc['releases']
            if r['accession'] != accession and (not filed or (r.get('filed') or '') <= filed)]
