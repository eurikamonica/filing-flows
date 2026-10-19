"""basic-finance-v4: a larger, fresh basic-finance corpus built with the v3 generators.

Reuses corpus8b_v3.website_rows / synthetic / make_row unchanged (same task semantics, contracts and gold checks), with:
- 100 owner-website companies never used before (v1/v2/v3 and legacy downloads excluded), stratified by latest form;
- synthetic fixtures from a new number range per split, so no fixture repeats an earlier corpus;
- 360 train / 20 dev / 20 sealed rows per task, and a fresh 100-question dev protocol (5 per task) never used for selection.
Created by Claude (Anthropic).
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import urllib.request

from lab import LAB, BETA, read, write, sha
from corpus8b_v3 import REAL_TASKS, SYNTH_TASKS, website_rows, synthetic, write_rows

AUTHOR = 'Created by Claude (Anthropic)'
STRATA = {'10-K': 40, '10-Q': 45, '8-K': 15}
PER_TASK = {'train': 360, 'dev': 20, 'sealed_test': 20}
NUMBER_BASE = {'train': 100000, 'dev': 200000, 'sealed_test': 300000}   # v3 used 0..179 / 0..7
PROTOCOL_PER_TASK = 5
# The v3 generator yields only 4 / 2 distinct prompts for these, all already in v3; they cannot be evaluated fresh.
TRAIN_ONLY = {'basic_instruction', 'reserve_movement'}


def build():
    root = LAB / 'runs' / ('corpus-bf-v4-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    root.mkdir(exist_ok=False)
    source_dir = root / 'sources'
    source_dir.mkdir()
    excluded = {str(c) for g in read(LAB / 'runs/20261016T171524Z/data-v2/manifest.json')['splits'].values() for c in g['companies']}
    excluded |= {str(c) for g in read(LAB / 'runs/20261016T171524Z/data/manifest.json')['splits'].values() for c in g['companies']}
    excluded |= set(read(BETA / '.runtime/website-data/manifest.json')['files'])
    excluded |= {c for g in read(LAB / 'runs/corpus-v3-20261016T230644Z/split-membership.json')['companies'].values() for c in g}
    index = read(BETA / '.runtime/overnight/site-index.json')
    memberships = {s: [] for s in PER_TASK}
    for form, count in STRATA.items():
        eligible = sorted((r for r in index['companies'] if r.get('form') == form and str(r['cik']) not in excluded),
                          key=lambda r: hashlib.sha256(('bf-v4-company-' + str(r['cik'])).encode()).hexdigest())[:count]
        if len(eligible) != count:
            raise RuntimeError('Insufficient unused companies for ' + form)
        a, b = round(count * 0.7), round(count * 0.85)
        for split, group in zip(memberships, (eligible[:a], eligible[a:b], eligible[b:])):
            memberships[split].extend(str(r['cik']) for r in group)
    write(root / 'split-membership.json', {'author': AUTHOR, 'companies': memberships, 'excluded_prior_companies': sorted(excluded),
          'stratification': {f: f'{c} companies, 70/15/15 by hash order' for f, c in STRATA.items()}})

    def download(cik):
        url = f'https://filing-flows.com/data/c/{cik}.json'
        request = urllib.request.Request(url, headers={'User-Agent': 'FilingFlowsBeta/0.4 (owner-authorized local research)'})
        with urllib.request.urlopen(request, timeout=30) as response:
            blob = response.read(8 * 1024 * 1024 + 1)
        if len(blob) > 8 * 1024 * 1024:
            raise RuntimeError('Company download size budget exceeded: ' + cik)
        if str(json.loads(blob)['profile']['cik']) != cik:
            raise ValueError('Company identity mismatch')
        path = source_dir / (cik + '.json')
        path.write_bytes(blob)
        return {'cik': cik, 'url': url, 'sha256': sha(path), 'bytes': len(blob),
                'downloaded_utc': datetime.now(timezone.utc).isoformat()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(download, [c for g in memberships.values() for c in g]))
    write(source_dir / 'manifest.json', {'author': AUTHOR, 'files': sources,
          'permission': 'User-owned website; user explicitly authorized download', 'not_tracked': 'raw JSON stays local'})

    # inputs the current champion trained on or was selected with (v3 train/dev); kept out of v4 dev and sealed test
    prior = {json.loads(l)['input'] for f in ('train.jsonl', 'dev.jsonl', 'dev-protocol.jsonl')
             for l in (LAB / 'runs/corpus-v3-20261016T230644Z' / f).read_text(encoding='utf-8').splitlines() if l.strip()}
    manifests, selected_by_split = {}, {}
    for split, companies in memberships.items():
        rows = []
        for cik in companies:
            rows.extend(website_rows(split, cik, source_dir / (cik + '.json')))
        rows.extend(synthetic(split, task, NUMBER_BASE[split] + n) for task in SYNTH_TASKS for n in range(PER_TASK[split]))
        groups, seen = defaultdict(list), set()
        for row in rows:
            if row['input'] not in seen and (split == 'train' or row['input'] not in prior):   # dedupe; keep prior inputs out of dev/test
                seen.add(row['input'])
                groups[row['task']].append(row)
        required = set(REAL_TASKS + SYNTH_TASKS) - (set() if split == 'train' else TRAIN_ONLY)
        if split != 'train':
            groups = {t: g for t, g in groups.items() if t not in TRAIN_ONLY}
        if set(groups) != required:
            raise RuntimeError('Missing task coverage in split ' + split + ': ' + str(required - set(groups)))
        selected = []
        for task, group in sorted(groups.items()):
            group.sort(key=lambda r: hashlib.sha256(r['input'].encode()).hexdigest())
            selected.extend(group[:PER_TASK[split]])
        for i, row in enumerate(selected):
            row['id'] = f'bf4-{split}-{i:06d}'
            row['author'] = AUTHOR
        random.Random(20261018).shuffle(selected)
        path = root / ('sealed/test.jsonl' if split == 'sealed_test' else split + '.jsonl')
        write_rows(path, selected)
        selected_by_split[split] = selected
        manifests[split] = {'path': str(path.relative_to(root)), 'sha256': sha(path), 'rows': len(selected), 'companies': companies,
                            'tasks': dict(Counter(r['task'] for r in selected)),
                            'label_kinds': dict(Counter(r['label_kind'] for r in selected)),
                            'documents': len({r['document_id'] for r in selected})}
    protocol = []
    for task in sorted(set(REAL_TASKS + SYNTH_TASKS) - TRAIN_ONLY):
        candidates = [r for r in selected_by_split['dev'] if r['task'] == task]
        picked, companies = [], set()
        for r in candidates:                                 # prefer distinct companies, then fill
            if r['company_id'] not in companies:
                picked.append(r)
                companies.add(r['company_id'])
            if len(picked) == PROTOCOL_PER_TASK:
                break
        picked += [r for r in candidates if r not in picked][:PROTOCOL_PER_TASK - len(picked)]
        protocol.extend(picked)
    write_rows(root / 'dev-protocol.jsonl', protocol)
    checks = {}
    for a, b in [('train', 'dev'), ('train', 'sealed_test'), ('dev', 'sealed_test')]:
        checks[a + ':' + b] = {f: len({r[f] for r in selected_by_split[a]} & {r[f] for r in selected_by_split[b]})
                               for f in ('company_id', 'document_id', 'input')}
        if any(checks[a + ':' + b].values()):
            raise RuntimeError('Cross-split leakage ' + a + ':' + b)
    checks['exact_input_overlap_with_v3_open_files'] = {s: sum(r['input'] in prior for r in rows) for s, rows in selected_by_split.items()}
    manifest = {'author': AUTHOR, 'version': 'basic-finance-v4', 'generator': 'corpus8b_v3.py functions, unchanged',
                'generator_sha256': sha(LAB / 'corpus8b_v3.py'), 'splits': manifests,
                'dev_protocol': {'rows': len(protocol), 'sha256': sha(root / 'dev-protocol.jsonl'),
                                 'tasks': dict(Counter(r['task'] for r in protocol)), 'fixed_before_any_inference': True},
                'train_only_tasks': sorted(TRAIN_ONLY), 'contamination_checks': checks, 'sealed_test_evaluated': False, 'source_files': len(sources),
                'source_download_bytes': sum(s['bytes'] for s in sources)}
    write(root / 'manifest.json', manifest)
    shutil.copy2(Path(__file__), root / 'corpus_bf_v4.py')
    (root / 'DATASET_CARD.md').write_text('# DATASET CARD\n\n' + AUTHOR + '.\n\n' +
        f"Version: basic-finance-v4. Train/dev/sealed rows: {manifests['train']['rows']}/{manifests['dev']['rows']}/{manifests['sealed_test']['rows']}; "
        f"dev protocol {len(protocol)} questions ({PROTOCOL_PER_TASK} per task).\n\n"
        '100 owner-website companies not used by any earlier corpus (stratified 40 10-K / 45 10-Q / 15 8-K by latest form), '
        'split 70/15/15 by company. Synthetic fixtures use new generator numbers, so none repeats basic-finance-v3. '
        'Task semantics, prompt contracts and gold checks are identical to basic-finance-v3 (same generator functions). '
        'Website values/headings are literal owner-source labels, not independent SEC verification; synthetic rows are explicitly hypothetical. '
        'basic_instruction and reserve_movement are train-only: the generator yields only 4 and 2 distinct prompts, all already present in v3, so they cannot be evaluated fresh. '
        'No human review. Exact prompt/company/document overlap across splits is zero; exact-input overlap with v3 open files is reported in manifest.json. '
        'The sealed test is not to be loaded for training or selection.\n', encoding='utf-8')
    print(json.dumps({'root': str(root), 'rows': {k: v['rows'] for k, v in manifests.items()}, 'protocol': len(protocol),
                      'checks': checks}, default=str), flush=True)


if __name__ == '__main__':
    build()
