"""Continuous local loop for the Qwen3-4B FSA lab: new questions -> train -> evaluate -> gate -> publish small files.

Owner decisions (2026-10-18): run until stopped; push only small files each cycle (data rows, evaluations, reports,
adapters) to eurikamonica/filing-flows branch lab/qwen3-4b-fsa-20261018; revision-reason (task A) labels are weak
(rule-derived, not human-reviewed): trained on, reported separately, excluded from the promotion gate; no GPU
temperature cutoff (readings are logged). 8B is not used.

Each cycle
  1. new SEC companies (never used before) -> owner v3 tasks A (revision reason) and C (balance-sheet op/fin) via
     build_v3_owner.py (UA "Filing Flows filingflows@gmail.com", <= 8 req/s); raw filings deleted after the build
  2. new owner-website companies + new synthetic fixtures -> basic-finance rows (corpus8b_v3 generators, unchanged)
  3. company-level 70/15/15 split; a fresh dev protocol for this cycle; nothing seen before enters dev/sealed
  4. train from the current champion on new rows + an equal-size replay sample of all earlier training rows
  5. evaluate candidate (fixed protocols + fresh protocol) and champion (fresh protocol)
  6. predeclared gate (PROTOCOL.md); promote or keep the champion
  7. commit and push small files
Stops on: continuous/STOP, < MIN_FREE_GIB disk, MAX_FAILURES consecutive failed cycles, PLATEAU consecutive
non-promotions, or an exhausted company pool. Created by Claude (Anthropic).
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request

LAB = Path(__file__).resolve().parent
BETA = LAB.parent
sys.path.insert(0, str(BETA))
sys.path.insert(0, str(LAB))
CONT = LAB / 'continuous'
STATE = CONT / 'state.json'
LOG = CONT / 'log.jsonl'
PY = str(BETA / '.venv/Scripts/python.exe')
REMOTE, BRANCH = 'filingflows', 'lab/qwen3-4b-fsa-20261018'
SEC_UA = 'Filing Flows filingflows@gmail.com'
WEB_UA = 'FilingFlowsBeta/0.5 (owner-authorized local research)'
FIRST_V3 = LAB / 'runs/v3-data-20261018T052500Z'
CFG = {
    'sec_companies': 30, 'web_companies': 40, 'sec_max_requests': 1500,
    'synth_per_task': {'train': 40, 'dev': 3, 'sealed_test': 3},
    'real_cap_per_task': {'train': 40, 'dev': 3, 'sealed_test': 3},
    'fresh_protocol': {'revision_reason': 20, 'bs_line_classification': 40, 'basic_per_task': 2},
    'replay_ratio': 1.0, 'max_length': 768, 'learning_rate': 5e-5, 'accumulation': 4, 'max_steps_cap': 600,
    'eval_steps': 100, 'min_free_gib': 25, 'max_failures': 3, 'plateau': 5, 'push_timeout_s': 3600,
    'gate': {'fresh_core_min_gain': 2, 'gate2_joint_max_drop': 1, 'gate2_regression_max_drop': 1,
             'bfv4_max_drop': 2, 'bfv3_max_drop': 2, 'valid_json_max_drop': 1},
}
FIXED = ['bfv3_dev40', 'gate2_dev48', 'bfv4_dev90']


def utc():
    return datetime.now(timezone.utc).isoformat()


def log(event, **kw):
    CONT.mkdir(exist_ok=True)
    line = json.dumps({'utc': utc(), 'event': event, **kw}, default=str)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line, flush=True)


def jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, default=str), encoding='utf-8')
    os.replace(tmp, path)


def h(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run(cmd, logfile, timeout, cwd=BETA):
    """Run a child process with output to logfile; kill the whole tree on timeout."""
    env = {**os.environ, 'PYTHONPATH': str(BETA), 'PYTHONIOENCODING': 'utf-8'}
    with open(logfile, 'w', encoding='utf-8') as out:
        p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env)
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
            return 'timeout'


# ----------------------------------------------------------------------------------------------- state

def initial_state():
    """Champion, used companies, seen inputs and replay pool from everything built before the loop."""
    used = set()
    for path in [FIRST_V3 / 'split-membership.json', LAB / 'runs/corpus-bf-v4-20261018T052227Z/split-membership.json',
                 LAB / 'runs/corpus-v3-20261016T230644Z/split-membership.json']:
        m = json.loads(path.read_text(encoding='utf-8'))
        for v in (m.get('company_split') or {}):
            used.add(str(v).replace('cik-', ''))
        for group in (m.get('companies') or {}).values():
            used |= {str(c) for c in group}
    for path in [LAB / 'runs/20261016T171524Z/data/manifest.json', LAB / 'runs/20261016T171524Z/data-v2/manifest.json']:
        for group in json.loads(path.read_text(encoding='utf-8'))['splits'].values():
            used |= {str(c) for c in group['companies']}
    used |= set(json.loads((BETA / '.runtime/website-data/manifest.json').read_text(encoding='utf-8'))['files'])
    seen = set()
    for f in ['runs/corpus-v3-20261016T230644Z/train.jsonl', 'runs/corpus-v3-20261016T230644Z/dev.jsonl',
              'runs/corpus-v3-20261016T230644Z/sealed/test.jsonl', 'runs/corpus-bf-v4-20261018T052227Z/train.jsonl',
              'runs/corpus-bf-v4-20261018T052227Z/dev.jsonl', 'runs/corpus-bf-v4-20261018T052227Z/sealed/test.jsonl',
              'runs/v3-data-20261018T052500Z/train.jsonl', 'runs/v3-data-20261018T052500Z/dev.jsonl',
              'runs/v3-data-20261018T052500Z/sealed/test.jsonl', 'runs/4b-bfv3mix-20261017T211441Z/train-packed.jsonl',
              'runs/20261016T171524Z/data/open/train.jsonl', 'runs/20261016T171524Z/data/open/dev.jsonl']:
        seen |= {h(r['input']) for r in jsonl(LAB / f)}
    seen |= {h(r['input']) for r in json.loads((LAB / 'runs/20261016T171524Z/data/dev-protocol.json').read_text(encoding='utf-8'))['validation']}
    (CONT / 'seen-inputs.txt').write_text('\n'.join(sorted(seen)) + '\n', encoding='utf-8')
    # replay pool: the champion's training rows plus the two corpora built but never trained on
    pool = [r for r in jsonl(LAB / 'runs/4b-bfv3mix-20261017T211441Z/train-packed.jsonl') if r['split'] == 'train']
    pool += [pack_row(r, 'v3_owner_first') for r in jsonl(FIRST_V3 / 'train.jsonl')]
    pool += [pack_row(r, 'bf_v4') for r in jsonl(LAB / 'runs/corpus-bf-v4-20261018T052227Z/train.jsonl')]
    write_jsonl(CONT / 'replay-pool.jsonl', pool)
    mix = LAB / 'runs/4b-bfv3mix-20261017T211441Z/eval-final.json'
    fixed = json.loads(mix.read_text(encoding='utf-8'))['protocols']
    fixed.update(json.loads((LAB / 'exports/eval-hf-champion-bfv4.json').read_text(encoding='utf-8'))['protocols'])
    return {'author': 'Created by Claude (Anthropic)', 'started_utc': utc(), 'cycle': 0, 'failures': 0,
            'non_promotions': 0, 'status': 'running', 'config': CFG, 'used_ciks': sorted(used),
            'champion': {'name': 'qwen4-bfv3mix-20261017', 'adapter': 'champions/qwen4-bfv3mix-20261017',
                         'fixed': {k: brief(v) for k, v in fixed.items() if k in FIXED}},
            'history': []}


def brief(p):
    return {k: p.get(k) for k in ('joint_correct', 'questions', 'macro_accuracy', 'valid_json', 'regression_correct',
                                  'regression_total', 'latency_p50_s')}


def pack_row(r, source):
    review = r.get('review', '')
    return {'id': r.get('id'), 'split': 'train', 'company_id': r['company_id'], 'task': r['task'], 'input': r['input'],
            'output': r['output'], 'origin': 'rule_generated', 'review': 'rule_verified',
            'source_kind': r.get('label_kind') or r.get('source_kind') or 'unknown', 'corpus_review': review,
            'weak_label': r['task'] == 'revision_reason', 'mix_source': source}


# ----------------------------------------------------------------------------------------------- data

def http_get(url, ua, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def pick(candidates, used, n, salt):
    fresh = [c for c in candidates if str(c[0]) not in used]
    fresh.sort(key=lambda c: h(f'{salt}-{c[0]}'))
    return fresh[:n]


def sec_batch(cycle, cdir, state):
    # NYSE/Nasdaq listings only: OTC shells, funds and unlisted filers rarely have usable 10-K XBRL or revisions
    tickers = CONT / 'sec-company-tickers-exchange.json'
    if not tickers.exists() or time.time() - tickers.stat().st_mtime > 7 * 86400:
        tickers.write_bytes(http_get('https://www.sec.gov/files/company_tickers_exchange.json', SEC_UA))
    table = json.loads(tickers.read_text(encoding='utf-8'))
    col = {name: i for i, name in enumerate(table['fields'])}
    candidates = sorted({(int(r[col['cik']]), r[col['name']]) for r in table['data'] if r[col['exchange']] in ('NYSE', 'Nasdaq')})
    batch = pick(candidates, set(state['used_ciks']), CFG['sec_companies'], f'sec-cycle-{cycle}')
    if not batch:
        return None, []
    save(cdir / 'sec-companies.json', [[c, n] for c, n in batch])
    out = cdir / 'v3'
    code = run([PY, LAB / 'build_v3_owner.py', '--run-dir', out, '--companies', cdir / 'sec-companies.json',
                '--seed', 20261018 + cycle, '--heldout-from', FIRST_V3 / 'heldout-tags.json',
                '--max-requests', CFG['sec_max_requests']], cdir / 'build_v3.log', timeout=4 * 3600)
    for sub in ('companyfacts', 'filings', 'submissions'):            # raw SEC files stay out of the disk budget
        shutil.rmtree(out / 'sources' / sub, ignore_errors=True)
    ciks = [str(c) for c, _ in batch]
    if code != 0 or not (out / 'train.jsonl').exists():
        log('sec_build_failed', cycle=cycle, code=code)
        return None, ciks
    return out, ciks


def web_batch(cycle, cdir, state, seen):
    from corpus8b_v3 import REAL_TASKS, SYNTH_TASKS, website_rows, synthetic
    train_only = {'basic_instruction', 'reserve_movement'}   # generator yields only 4 / 2 distinct prompts
    index = json.loads((BETA / '.runtime/overnight/site-index.json').read_text(encoding='utf-8'))
    candidates = sorted({(int(r['cik']), r.get('form')) for r in index['companies'] if r.get('form') in ('10-K', '10-Q', '8-K')})
    batch = pick(candidates, set(state['used_ciks']), CFG['web_companies'], f'web-cycle-{cycle}')
    src = cdir / 'web-sources'
    src.mkdir(parents=True, exist_ok=True)
    order = [str(c) for c, _ in batch]
    split_of = {c: ('train' if i < round(len(order) * 0.7) else 'dev' if i < round(len(order) * 0.85) else 'sealed_test')
                for i, c in enumerate(order)}
    rows, manifest = defaultdict(list), []
    for cik in order:
        try:
            blob = http_get(f'https://filing-flows.com/data/c/{cik}.json', WEB_UA, timeout=30)
            if str(json.loads(blob)['profile']['cik']) != cik:
                raise ValueError('identity mismatch')
            (src / f'{cik}.json').write_bytes(blob)
            manifest.append({'cik': cik, 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)})
            rows[split_of[cik]] += website_rows(split_of[cik], cik, src / f'{cik}.json')
        except Exception as exc:
            manifest.append({'cik': cik, 'error': repr(exc)})
        time.sleep(0.3)
    base = 10_000_000 * (cycle + 1)                               # synthetic numbers never reused across cycles
    for split, offset in (('train', 0), ('dev', 1_000_000), ('sealed_test', 2_000_000)):
        for task in SYNTH_TASKS:
            if task in train_only and split != 'train':
                continue
            if task in train_only:
                continue                                         # already saturated in earlier corpora
            rows[split] += [synthetic(split, task, base + offset + n) for n in range(CFG['synth_per_task'][split])]
    selected = {}
    for split, items in rows.items():
        groups = defaultdict(list)
        for r in items:
            key = h(r['input'])
            if key in seen or (split != 'train' and r['task'] in train_only):
                continue
            seen.add(key)
            groups[r['task']].append(r)
        selected[split] = [r for task in sorted(groups) for r in groups[task][:max(CFG['real_cap_per_task'][split],
                                                                                    CFG['synth_per_task'][split])]]
    save(src / 'manifest.json', {'author': 'Created by Claude (Anthropic)', 'files': manifest, 'split_of': split_of})
    for f in src.glob('*.json'):
        if f.name != 'manifest.json':
            f.unlink()                                           # raw website JSON stays local-only and transient
    return selected, order


def fits(tokenizer, row):
    prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': row['input']}], tokenize=False,
                                           add_generation_prompt=True, enable_thinking=False)
    n = len(tokenizer.encode(prompt, add_special_tokens=False)) + len(tokenizer.encode(row['output'], add_special_tokens=False)) + 1
    return n <= CFG['max_length']


def build_cycle_data(cycle, cdir, state, tokenizer):
    seen = set((CONT / 'seen-inputs.txt').read_text(encoding='utf-8').split())
    v3_dir, sec_ciks = sec_batch(cycle, cdir, state)
    web, web_ciks = web_batch(cycle, cdir, state, seen)
    state['used_ciks'] = sorted(set(state['used_ciks']) | set(sec_ciks) | set(web_ciks))
    splits = {'train': [], 'dev': [], 'sealed_test': []}
    if v3_dir:
        for split, f in (('train', 'train.jsonl'), ('dev', 'dev.jsonl'), ('sealed_test', 'sealed/test.jsonl')):
            for r in jsonl(v3_dir / f):
                key = h(r['input'])
                if key in seen:
                    continue
                seen.add(key)
                splits[split].append({**r, 'mix_source': f'cycle{cycle:03d}_v3'})
    for split, items in web.items():
        splits[split] += [{**r, 'mix_source': f'cycle{cycle:03d}_basic'} for r in items]
    dropped = Counter()
    for split in splits:
        kept = []
        for r in splits[split]:
            if fits(tokenizer, r):
                kept.append(r)
            else:
                dropped[f'{split}:{r["task"]}'] += 1
        splits[split] = kept
    (CONT / 'seen-inputs.txt').write_text('\n'.join(sorted(seen)) + '\n', encoding='utf-8')
    for split, items in splits.items():
        write_jsonl(cdir / 'data' / f'{split}.jsonl', items)
    # fresh protocol from this cycle's dev split, fixed before any inference
    rng = random.Random(cycle)
    dev = list(splits['dev'])
    rng.shuffle(dev)
    fp = CFG['fresh_protocol']
    protocol = [r for r in dev if r['task'] == 'revision_reason'][:fp['revision_reason']]
    c_rows = [r for r in dev if r['task'] == 'bs_line_classification']
    unseen = [r for r in c_rows if r.get('tag_seen_in_train') is False][:fp['bs_line_classification'] // 2]
    protocol += unseen + [r for r in c_rows if r not in unseen][:fp['bs_line_classification'] - len(unseen)]
    by_task = defaultdict(list)
    for r in dev:
        if r['task'] not in ('revision_reason', 'bs_line_classification'):
            by_task[r['task']].append(r)
    for task in sorted(by_task):
        protocol += by_task[task][:fp['basic_per_task']]
    write_jsonl(cdir / 'fresh-protocol.jsonl', protocol)
    counts = {s: dict(Counter(r['task'] for r in items)) for s, items in splits.items()}
    save(cdir / 'data/manifest.json', {'author': 'Created by Claude (Anthropic)', 'cycle': cycle,
         'sec_companies': sec_ciks, 'web_companies': web_ciks, 'v3_build': str(v3_dir) if v3_dir else None,
         'rows': counts, 'dropped_over_length': dict(dropped), 'fresh_protocol': dict(Counter(r['task'] for r in protocol)),
         'sha256': {s: hashlib.sha256((cdir / 'data' / f'{s}.jsonl').read_bytes()).hexdigest() for s in splits},
         'weak_labels': 'revision_reason rows are rule-derived, not human-reviewed'})
    return splits, protocol


def build_pack(cycle, cdir, splits, protocol, tokenizer):
    proto = {h(r['input']) for r in protocol}
    held = {h(r['input']) for s in ('dev', 'sealed_test') for r in splits[s]}
    new_train = [pack_row(r, r['mix_source']) for r in splits['train'] if h(r['input']) not in held]
    pool = [r for r in jsonl(CONT / 'replay-pool.jsonl') if h(r['input']) not in held]
    rng = random.Random(1000 + cycle)
    rng.shuffle(pool)
    replay = [r for r in pool if fits(tokenizer, r)][:int(len(new_train) * CFG['replay_ratio'])]
    validation = [{**pack_row(r, r['mix_source']), 'split': 'validation'} for r in splits['dev'] if h(r['input']) not in proto]
    if not validation:
        validation = [{**pack_row(r, r['mix_source']), 'split': 'validation'} for r in splits['dev']]
    test = [{**pack_row(r, r['mix_source']), 'split': 'test'} for r in splits['sealed_test']]
    rows = new_train + replay + validation + test
    # company ids must map to one split; drop train rows that collide (should not happen with fresh companies)
    owner = {}
    for r in validation + test:
        owner[r['company_id']] = r['split']
    rows = [r for r in rows if r['split'] != 'train' or owner.get(r['company_id'], 'train') == 'train']
    rng.shuffle(rows)
    write_jsonl(cdir / 'train-packed.jsonl', rows)
    n_train = sum(r['split'] == 'train' for r in rows)
    steps = max(20, min(CFG['max_steps_cap'], math.ceil(n_train / CFG['accumulation'])))
    save(cdir / 'plan.json', {'author': 'Created by Claude (Anthropic)', 'cycle': cycle, 'created_utc': utc(),
         'init_adapter': None, 'new_train_rows': len(new_train), 'replay_rows': len(replay),
         'validation_rows': len(validation), 'test_rows': len(test), 'max_steps': steps, 'config': CFG,
         'train_tasks': dict(Counter(r['task'] for r in rows if r['split'] == 'train')),
         'train_sources': dict(Counter(r['mix_source'] for r in rows if r['split'] == 'train'))})
    return new_train, steps


# ----------------------------------------------------------------------------------------------- gate

def summary(path, name):
    p = json.loads(Path(path).read_text(encoding='utf-8'))['protocols'][name]
    core = [d for d in p['details'] if d['task'] != 'revision_reason']
    weak = [d for d in p['details'] if d['task'] == 'revision_reason']
    label_ok = sum(1 for d in weak if isinstance(d.get('expected'), dict) and
                   f'"label":"{d["expected"].get("label")}"' in d['output'].replace(' ', ''))
    return {**brief(p), 'core_correct': sum(d['correct'] for d in core), 'core_questions': len(core),
            'weak_A_joint': sum(d['correct'] for d in weak), 'weak_A_label': label_ok, 'weak_A_questions': len(weak),
            'tasks': {t: f"{g['correct']}/{g['total']}" for t, g in p['tasks'].items()}}


def gate(cand_fixed, cand_fresh, champ_fixed, champ_fresh):
    g = CFG['gate']
    checks = {
        'fresh_core_gain': cand_fresh['core_correct'] - champ_fresh['core_correct'] >= g['fresh_core_min_gain'],
        'gate2_joint': cand_fixed['gate2_dev48']['joint_correct'] >= champ_fixed['gate2_dev48']['joint_correct'] - g['gate2_joint_max_drop'],
        'gate2_regression': cand_fixed['gate2_dev48']['regression_correct'] >= champ_fixed['gate2_dev48']['regression_correct'] - g['gate2_regression_max_drop'],
        'bfv4': cand_fixed['bfv4_dev90']['joint_correct'] >= champ_fixed['bfv4_dev90']['joint_correct'] - g['bfv4_max_drop'],
        'bfv3': cand_fixed['bfv3_dev40']['joint_correct'] >= champ_fixed['bfv3_dev40']['joint_correct'] - g['bfv3_max_drop'],
        'valid_json': all(cand_fixed[k]['valid_json'] >= champ_fixed[k]['valid_json'] - g['valid_json_max_drop'] for k in FIXED),
    }
    return all(checks.values()), checks


# ----------------------------------------------------------------------------------------------- publish

LLAMA = BETA / '.runtime/tools/llama.cpp-b11381'


def export_champion(name, state):
    """Owner decision 2026-10-19: on every promotion publish a Q8_0 GGUF of the new champion.
    NF4-faithful merge -> bf16 GGUF -> Q8_0 -> split under 1.9 GB (GitHub LFS 2 GiB limit) -> evaluate the split
    file on the fixed protocols. Temporary files and older champions' local exports are deleted afterwards."""
    edir = LAB / 'exports' / name
    shutil.rmtree(edir, ignore_errors=True)
    (edir / 'gguf').mkdir(parents=True)
    merged, tmp16, tmp8 = edir / 'merged-bf16', edir / 'tmp-bf16.gguf', edir / 'tmp-Q8_0.gguf'
    if run([PY, '-u', LAB / 'merge_champion_nf4.py', '--adapter', LAB / 'champions' / name, '--out', merged],
           edir / 'merge.log', timeout=3 * 3600) != 0:
        raise RuntimeError('export merge failed')
    shutil.copy2(merged / 'merge-status.json', edir / 'merge-status.json')
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONIOENCODING': 'utf-8',
           'PYTHONPATH': f"{LLAMA / 'src/llama.cpp-b11381/gguf-py'};{BETA / '.runtime/tools/pydeps'}"}
    with open(edir / 'convert.log', 'w', encoding='utf-8') as out:
        if subprocess.run([PY, str(LLAMA / 'src/llama.cpp-b11381/convert_hf_to_gguf.py'), str(merged), '--outtype', 'bf16',
                           '--outfile', str(tmp16)], stdout=out, stderr=subprocess.STDOUT, env=env, timeout=3600).returncode:
            raise RuntimeError('GGUF conversion failed')
    prefix = edir / 'gguf' / f'qwen3-4b-fsa-{name}-Q8_0'
    for cmd, logname in (([LLAMA / 'bin/llama-quantize.exe', tmp16, tmp8, 'Q8_0'], 'quantize.log'),
                         ([LLAMA / 'bin/llama-gguf-split.exe', '--split', '--split-max-size', '1900M', tmp8, prefix], 'split.log')):
        if run(cmd, edir / logname, timeout=3600, cwd=LAB) != 0:
            raise RuntimeError(logname + ' failed')
    shutil.rmtree(merged, ignore_errors=True)
    tmp16.unlink(missing_ok=True)
    tmp8.unlink(missing_ok=True)
    shards = sorted((edir / 'gguf').glob('*.gguf'))
    if run([PY, '-u', LAB / 'eval_gguf.py', '--gguf', shards[0], '--out', edir / 'eval-gguf-Q8_0.json',
            '--protocols', *FIXED], edir / 'eval-gguf.log', timeout=2 * 3600, cwd=LAB) != 0:
        raise RuntimeError('GGUF evaluation failed')
    (edir / 'gguf/SHA256SUMS').write_text(''.join(f"{hashlib.sha256(p.read_bytes()).hexdigest()} *{p.name}\n" for p in shards),
                                          encoding='utf-8')
    gg = {k: brief(v) for k, v in json.loads((edir / 'eval-gguf-Q8_0.json').read_text(encoding='utf-8'))['protocols'].items()}
    adapter = state['champion'].get('fixed', {})
    (edir / 'README.md').write_text('\n'.join([
        f'# {name} — Q8_0 GGUF', '', 'Created by Claude (Anthropic) by continuous.py on promotion.', '',
        f'Adapter: `champions/{name}`. NF4-faithful merge (merge-status.json), llama.cpp b11381 Q8_0, split under 1.9 GB.',
        f'Load with `llama-server -m gguf/{shards[0].name} --jinja` and `enable_thinking=false`.', '',
        '| Protocol | adapter (NF4) | Q8_0 GGUF |', '| --- | --- | --- |',
        *[f"| {k} | {adapter.get(k, {}).get('joint_correct')} | {gg[k]['joint_correct']} |" for k in FIXED], '']), encoding='utf-8')
    for old in (LAB / 'exports').iterdir():           # owner decision: delete older champions' local exports
        if old.is_dir() and old.name != name:
            shutil.rmtree(old, ignore_errors=True)
    state['champion']['export'] = {'dir': f'exports/{name}', 'gguf_eval': gg, 'utc': utc()}
    log('exported', champion=name, shards=[p.name for p in shards],
        gguf={k: v['joint_correct'] for k, v in gg.items()})


def publish(cycle, cdir, promoted, state):
    """Commit locally (full history kept on the local branch), then force-push a single-commit snapshot of the
    current useful tree (owner decision 2026-10-19). Older champions' exports and non-promoted candidate adapters
    are not in the snapshot. Note: GitHub keeps already-uploaded LFS objects; this does not reduce LFS quota."""
    keep = ('.jsonl', '.json', '.md', '.log', '.txt', '.jinja')
    paths = [str(p.relative_to(LAB)) for p in cdir.rglob('*')
             if p.is_file() and p.suffix in keep and 'checkpoint-' not in p.as_posix()]
    paths += ['continuous.py', 'continuous/PROTOCOL.md', 'continuous/state.json', 'CONTINUOUS_STATUS.md',
              'build_v3_owner.py', 'bfv3_4b.py', 'eval_gguf.py', 'merge_champion_nf4.py', 'MODEL_RELEASE.md']
    if promoted:
        paths.append(f'champions/{promoted}')
    export = state['champion'].get('export')
    git = lambda *a: subprocess.run(['git', *a], cwd=LAB, capture_output=True, text=True)
    # untrack everything under exports/ except the current champion's export, and all candidate adapters
    keep_export = export['dir'] if export else None
    for tracked in git('ls-files', 'exports').stdout.splitlines():
        if not keep_export or not tracked.startswith(keep_export + '/'):
            git('rm', '-q', '--cached', '--', tracked)
    for tracked in git('ls-files', 'cycles').stdout.splitlines():
        if tracked.endswith('.safetensors'):
            git('rm', '-q', '--cached', '--', tracked)
    if keep_export:
        paths.append(keep_export)
    git('add', '-f', '--', *paths)
    msg = f'Continuous cycle {cycle:03d}: ' + (f'promoted {promoted}' if promoted else 'champion kept') + \
          '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n'
    c = git('commit', '-q', '-m', msg)
    tree = git('rev-parse', 'HEAD^{tree}').stdout.strip()
    remote = git('ls-remote', REMOTE, f'refs/heads/{BRANCH}').stdout.split()
    snap_msg = (f'Lab snapshot after continuous cycle {cycle:03d} (champion {state["champion"]["name"]})\n\n'
                'Single-commit snapshot; full history is kept locally. See MODEL_RELEASE.md and CONTINUOUS_STATUS.md.\n\n'
                'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n')
    snap = subprocess.run(['git', 'commit-tree', tree, '-m', snap_msg], cwd=LAB, capture_output=True, text=True).stdout.strip()
    lease = f'--force-with-lease=refs/heads/{BRANCH}:{remote[0]}' if remote else '--force-with-lease'
    code = run(['git', 'push', lease, REMOTE, f'{snap}:refs/heads/{BRANCH}'], cdir / 'push.log', CFG['push_timeout_s'], cwd=LAB)
    log('published', cycle=cycle, commit_rc=c.returncode, snapshot=snap, push=code)
    return code == 0


def write_status(state):
    lines = ['# Continuous training status', '', 'Created by Claude (Anthropic). Updated every cycle by `continuous.py`.', '',
             f"Status: **{state['status']}** · cycles: {state['cycle']} · champion: `{state['champion']['name']}`", '',
             (f"Current weights: adapter `{state['champion']['adapter']}`; Q8_0 GGUF in `{state['champion']['export']['dir']}/gguf/` "
              f"(fixed protocols as GGUF: " + ', '.join(f"{k} {v['joint_correct']}" for k, v in state['champion']['export']['gguf_eval'].items()) + ')'
              if state['champion'].get('export') else f"Current weights: adapter `{state['champion']['adapter']}` (no GGUF export yet)"), '',
             '| Cycle | New train rows | Fresh core (cand / champ) | Weak A label (cand / champ) | Gate 2 (cand) | Regression | bfv4 | Result |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for e in state['history']:
        if e.get('error'):
            lines.append(f"| {e['cycle']} | — | — | — | — | — | — | failed: {e['error'][:60]} |")
            continue
        cf, ch, fx = e['candidate_fresh'], e['champion_fresh'], e['candidate_fixed']
        lines.append(f"| {e['cycle']} | {e['new_train_rows']} | {cf['core_correct']}/{cf['core_questions']} vs {ch['core_correct']} | "
                     f"{cf['weak_A_label']}/{cf['weak_A_questions']} vs {ch['weak_A_label']} | {fx['gate2_dev48']['joint_correct']}/48 | "
                     f"{fx['gate2_dev48']['regression_correct']}/18 | {fx['bfv4_dev90']['joint_correct']}/90 | "
                     f"{'promoted' if e['promoted'] else 'kept champion'} |")
    lines += ['', 'Fresh protocol = this cycle\'s new dev questions (companies never used before). "Core" excludes the weak',
              'revision-reason labels (rule-derived, not human-reviewed), which are reported separately and not gated.',
              'Gate and stop rules: continuous/PROTOCOL.md.']
    (LAB / 'CONTINUOUS_STATUS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


# ----------------------------------------------------------------------------------------------- loop

def gpu_busy():
    r = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], capture_output=True, text=True)
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def one_cycle(state, tokenizer):
    cycle = state['cycle'] + 1
    cdir = LAB / 'cycles' / f'c{cycle:03d}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
    cdir.mkdir(parents=True)
    log('cycle_start', cycle=cycle, dir=str(cdir))
    splits, protocol = build_cycle_data(cycle, cdir, state, tokenizer)
    if len(splits['train']) < 100 or len(protocol) < 20:
        raise RuntimeError(f'too little new data: train {len(splits["train"])}, protocol {len(protocol)}')
    new_train, steps = build_pack(cycle, cdir, splits, protocol, tokenizer)
    champ = state['champion']
    plan = json.loads((cdir / 'plan.json').read_text(encoding='utf-8'))
    plan['init_adapter'] = champ['adapter']
    save(cdir / 'plan.json', plan)
    while gpu_busy():
        log('gpu_busy_wait', pids=gpu_busy())
        time.sleep(600)
    code = run([PY, '-u', LAB / 'train_continuation.py', '--data', cdir / 'train-packed.jsonl', '--out', cdir / 'train',
                '--model', 'Qwen/Qwen3-4B', '--init-adapter', LAB / champ['adapter'], '--qlora', '--compute-dtype', 'bfloat16',
                '--gradient-checkpointing', '--max-length', CFG['max_length'], '--batch-size', 1,
                '--gradient-accumulation-steps', CFG['accumulation'], '--learning-rate', CFG['learning_rate'],
                '--lora-rank', 8, '--target-modules', 'qv', '--max-steps', steps, '--eval-steps', CFG['eval_steps'],
                '--save-steps', CFG['eval_steps'], '--logging-steps', 5, '--stop-file', CONT / 'STOP',
                '--min-free-gib', 16], cdir / 'train.log', timeout=8 * 3600)
    if code != 0 or not (cdir / 'train/adapter_model.safetensors').exists():
        raise RuntimeError(f'training failed: {code}')
    if (CONT / 'STOP').exists():
        raise SystemExit('STOP requested during training; candidate not evaluated')
    fresh = f'fresh={cdir / "fresh-protocol.jsonl"}'
    code = run([PY, '-u', LAB / 'bfv3_4b.py', 'eval', '--adapter', cdir / 'train', '--out', cdir / 'eval-candidate.json',
                '--protocols', *FIXED, fresh], cdir / 'eval-candidate.log', timeout=5 * 3600, cwd=LAB)
    if code != 0:
        raise RuntimeError(f'candidate evaluation failed: {code}')
    code = run([PY, '-u', LAB / 'bfv3_4b.py', 'eval', '--adapter', LAB / champ['adapter'], '--out', cdir / 'eval-champion.json',
                '--protocols', fresh], cdir / 'eval-champion.log', timeout=3 * 3600, cwd=LAB)
    if code != 0:
        raise RuntimeError(f'champion evaluation failed: {code}')
    cand_fixed = {k: summary(cdir / 'eval-candidate.json', k) for k in FIXED}
    cand_fresh = summary(cdir / 'eval-candidate.json', 'fresh')
    champ_fresh = summary(cdir / 'eval-champion.json', 'fresh')
    ok, checks = gate(cand_fixed, cand_fresh, champ['fixed'], champ_fresh)
    promoted = None
    if ok:
        promoted = f'cycle-{cycle:03d}'
        dst = LAB / 'champions' / promoted
        dst.mkdir(parents=True)
        for f in (cdir / 'train').iterdir():
            if f.is_file() and f.name != 'memory.jsonl':
                shutil.copy2(f, dst / f.name)
        state['champion'] = {'name': promoted, 'adapter': f'champions/{promoted}', 'fixed': cand_fixed}
        state['non_promotions'] = 0
    else:
        state['non_promotions'] += 1
    for ck in (cdir / 'train').glob('checkpoint-*'):
        shutil.rmtree(ck, ignore_errors=True)
    entry = {'cycle': cycle, 'dir': str(cdir.relative_to(LAB)), 'new_train_rows': len(new_train), 'steps': steps,
             'candidate_fixed': cand_fixed, 'candidate_fresh': cand_fresh, 'champion_fresh': champ_fresh,
             'gate_checks': checks, 'promoted': bool(promoted), 'champion_after': state['champion']['name'], 'ended_utc': utc()}
    save(cdir / 'decision.json', entry)
    report = [f'# Cycle {cycle:03d}', '', 'Created by Claude (Anthropic).', '',
              f"New training rows {len(new_train)} (+ equal replay), {steps} steps from `{champ['name']}`.", '',
              f"Fresh protocol core: candidate {cand_fresh['core_correct']} vs champion {champ_fresh['core_correct']} "
              f"of {cand_fresh['core_questions']}. Weak revision-reason labels: candidate {cand_fresh['weak_A_label']} vs "
              f"champion {champ_fresh['weak_A_label']} of {cand_fresh['weak_A_questions']} (not gated).", '',
              f"Fixed: Gate 2 {cand_fixed['gate2_dev48']['joint_correct']}/48 (regression {cand_fixed['gate2_dev48']['regression_correct']}/18), "
              f"bfv3 {cand_fixed['bfv3_dev40']['joint_correct']}/40, bfv4 {cand_fixed['bfv4_dev90']['joint_correct']}/90.", '',
              f"Gate checks: {json.dumps(checks)}. Result: {'promoted ' + promoted if promoted else 'champion kept'}.", '',
              'All protocols are development sets; nothing here is a sealed-test score.']
    (cdir / 'REPORT.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    return cycle, cdir, entry, promoted


def smoke():
    """Data path only, tiny batches, no training, no state/seen changes kept."""
    CFG.update(sec_companies=6, web_companies=4, sec_max_requests=400)
    seen_file = CONT / 'seen-inputs.txt'
    backup = seen_file.read_bytes() if seen_file.exists() else None
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else initial_state()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(BETA / '.runtime/model-sources/qwen3-4b'), local_files_only=True)
    cdir = CONT / 'smoke' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    cdir.mkdir(parents=True)
    try:
        splits, protocol = build_cycle_data(999, cdir, dict(state), tok)
        new_train, steps = build_pack(999, cdir, splits, protocol, tok)
        from training import read_dataset
        rows = read_dataset(cdir / 'train-packed.jsonl')
        print(json.dumps({'splits': {k: len(v) for k, v in splits.items()}, 'protocol': len(protocol),
                          'new_train': len(new_train), 'steps': steps, 'packed': Counter(r['split'] for r in rows)}, default=str))
    finally:
        if backup is not None:
            seen_file.write_bytes(backup)


def main():
    if '--smoke' in sys.argv:
        CONT.mkdir(exist_ok=True)
        return smoke()
    CONT.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else initial_state()
    state['status'] = 'running'
    save(STATE, state)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(BETA / '.runtime/model-sources/qwen3-4b'), local_files_only=True)
    log('loop_start', cycle=state['cycle'], champion=state['champion']['name'])
    while True:
        if (CONT / 'STOP').exists():
            state['status'] = 'stopped_by_owner'
            break
        free = shutil.disk_usage(LAB).free / 2**30
        if free < CFG['min_free_gib']:
            state['status'] = f'stopped_low_disk_{free:.0f}GiB'
            break
        if not state['champion'].get('export') and state['champion']['name'].startswith('cycle-'):
            try:                                         # retry a missing export between cycles, while the GPU is free
                export_champion(state['champion']['name'], state)
                save(STATE, state)
                write_status(state)
            except Exception as exc:
                log('export_failed', champion=state['champion']['name'], error=repr(exc))
        try:
            cycle, cdir, entry, promoted = one_cycle(state, tokenizer)
            state['cycle'] = cycle
            state['failures'] = 0
            state['history'].append(entry)
            # this cycle's training rows join the replay pool for later cycles
            with (CONT / 'replay-pool.jsonl').open('a', encoding='utf-8') as f:
                for r in jsonl(cdir / 'train-packed.jsonl'):
                    if r['split'] == 'train' and str(r.get('mix_source', '')).startswith('cycle'):
                        f.write(json.dumps(r, ensure_ascii=False) + '\n')
            if promoted:
                try:
                    export_champion(promoted, state)
                except Exception as exc:                 # a failed export must not lose the cycle; retried at next start
                    log('export_failed', champion=promoted, error=repr(exc))
            save(STATE, state)
            write_status(state)
            publish(cycle, cdir, promoted, state)
        except Exception as exc:
            state['cycle'] += 1
            state['failures'] += 1
            state['history'].append({'cycle': state['cycle'], 'error': repr(exc), 'ended_utc': utc()})
            log('cycle_failed', cycle=state['cycle'], error=repr(exc), traceback=traceback.format_exc())
            save(STATE, state)
            write_status(state)
            if state['failures'] >= CFG['max_failures']:
                state['status'] = 'stopped_repeated_failures'
                break
            time.sleep(300)
            continue
        if state['non_promotions'] >= CFG['plateau']:
            state['status'] = 'stopped_plateau'
            break
    save(STATE, state)
    write_status(state)
    log('loop_end', status=state['status'])


if __name__ == '__main__':
    main()
