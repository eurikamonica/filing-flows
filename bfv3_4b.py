"""Qwen3-4B continuation on basic-finance-v3: pack data, evaluate adapters, summarise.

pack:  writes train_continuation.py-compatible rows into a fresh run directory.
eval:  greedy generation on (a) the frozen 40-question basic-finance-v3 dev protocol, scored exactly as
       train8b.score so 4B and 8B numbers are comparable, and (b) the Gate 2 48-question dev protocol
       (30 new + 18 historical regression), scored as evaluate_lab.py.
The sealed test of corpus-v3 is never read. No temperature cutoff (owner decision 2026-10-17); readings are logged.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

LAB = Path(__file__).resolve().parent
BETA = LAB.parent
CORPUS = LAB / 'runs/corpus-v3-20261016T230644Z'
GATE2 = LAB / 'runs/20261016T171524Z'
CHAMPION = GATE2 / 'archive/qwen4'
BFV4 = LAB / 'runs/corpus-bf-v4-20261018T052227Z'
sys.path.insert(0, str(BETA))


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write(path, value):
    from run_control import write_json
    write_json(path, value)


# Same strict parsing and matching as train8b.py (8B basic-finance-v3 runs), copied to avoid importing the 8B runtime.
def strict_json(text):
    def reject(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(text, parse_constant=reject)


def matches(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and matches(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(matches(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, bool) or expected is None:
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-4, abs_tol=1e-6)
    return type(actual) is type(expected) and actual == expected


def score_bfv3(text, expected):
    try:
        actual = strict_json(text)
        valid = isinstance(actual, dict)
    except (ValueError, TypeError):
        actual, valid = None, False
    content = valid and matches(actual, {k: v for k, v in expected.items() if k != 'source_id'})
    source = valid and actual.get('source_id') == expected['source_id'] if 'source_id' in expected else None
    numeric = valid and matches(actual.get('value'), expected['value']) if type(expected.get('value')) in (int, float) else None
    return {'valid_json': valid, 'content_correct': content, 'source_id_correct': source, 'numeric_correct': numeric,
            'correct': bool(content and (source if source is not None else True))}


def score_gate2(text, row):
    from overnight_worker import equal
    try:
        def reject(value): raise ValueError(value)
        actual = json.loads(text, parse_constant=reject)
        valid = isinstance(actual, dict)
    except (ValueError, TypeError):
        actual, valid = None, False
    expected = row['expected']
    arithmetic = row['task'].startswith('regression:Compute ') or row['task'] in ('reserve_calculation', 'accrual_ratio', 'amended_ytd')
    content = valid and (equal(actual.get('value'), expected.get('value'), True) if arithmetic else
                         equal(actual, {k: v for k, v in expected.items() if k != 'source_id'}))
    source = valid and actual.get('source_id') == expected.get('source_id') if 'source_id' in expected else None
    return {'valid_json': valid, 'content_correct': content, 'source_id_correct': source, 'numeric_correct': None,
            'correct': bool(content and (source if source is not None else True))}


def pack(run):
    if run.exists():
        raise SystemExit('Run directory exists; choose a fresh one')
    train, dev, protocol = jsonl(CORPUS / 'train.jsonl'), jsonl(CORPUS / 'dev.jsonl'), jsonl(CORPUS / 'dev-protocol.jsonl')
    protocol_companies = {r['company_id'] for r in protocol}
    validation = [r for r in dev if r['company_id'] in protocol_companies]
    # corpus dev repeats a few identical categorical prompts across hypothetical entities; keep them out of the placeholder
    seen = {r['input'] for r in validation}
    rows = []
    for split, items in (('train', train), ('validation', validation),
                         # placeholder so training.read_dataset sees three splits; never loaded by the trainer
                         ('test', [r for r in dev if r['company_id'] not in protocol_companies and r['input'] not in seen])):
        for r in items:
            rows.append({'id': r['id'], 'split': split, 'company_id': r['company_id'], 'task': r['task'],
                         'input': r['input'], 'output': r['output'], 'origin': 'rule_generated', 'review': 'rule_verified',
                         'source_kind': r['label_kind'], 'corpus_review': r['review'], 'corpus_split': r['split']})
    run.mkdir(parents=True)
    data = run / 'train-packed.jsonl'
    data.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    from training import read_dataset
    checked = read_dataset(data)
    counts = {s: sum(r['split'] == s for r in checked) for s in ('train', 'validation', 'test')}
    write(run / 'plan.json', {
        'author': 'Created by Claude (Anthropic)', 'created_utc': utc(), 'base': 'Qwen/Qwen3-4B',
        'init_adapter': str(CHAMPION), 'init_adapter_sha256': sha(CHAMPION / 'adapter_model.safetensors'),
        'corpus': str(CORPUS), 'corpus_manifest_sha256': sha(CORPUS / 'manifest.json'),
        'packed_sha256': sha(data), 'packed_rows': counts,
        'test_split_note': 'Packed "test" = 22 corpus-dev rows from non-protocol companies, a format placeholder; '
                           'the corpus sealed test is not read.',
        'eval_protocols': {'bfv3_dev40': sha(CORPUS / 'dev-protocol.jsonl'), 'gate2_dev48': sha(GATE2 / 'data/dev-protocol.json')},
        'owner_decision': '2026-10-17: train Qwen3-4B on basic-finance-v3; no temperature cutoff.'})
    print(json.dumps(counts))


HISTORICAL = BETA / '.runtime/overnight/initial-corpus-v4.jsonl'


def pack_mix(run, seed=20261017, per_bfv3_task=120, historical_train=1200, max_length=384):
    """bfv3 plus replay in the old output contracts, to counter the format drift seen in run 4b-bfv3-20261017T062749Z.
    Replay = historical overnight corpus (train split only; Gate 2 regression questions come from its validation split)
    and Gate 2 v1 train rows without the defective basic_instruction family. Over-length rows are dropped, never truncated."""
    import random
    from collections import Counter
    from transformers import AutoTokenizer
    if run.exists():
        raise SystemExit('Run directory exists; choose a fresh one')
    rng = random.Random(seed)
    tokenizer = AutoTokenizer.from_pretrained(str(BETA / '.runtime/model-sources/qwen3-4b'), local_files_only=True)

    def fits(row):
        prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': row['input']}], tokenize=False,
                                               add_generation_prompt=True, enable_thinking=False)
        return len(tokenizer.encode(prompt, add_special_tokens=False)) + len(tokenizer.encode(row['output'], add_special_tokens=False)) + 1 <= max_length

    def stratified(items, key, total=None, per=None):
        groups = defaultdict(list)
        for r in items:
            groups[key(r)].append(r)
        out = []
        for name in sorted(groups):
            g = groups[name]
            rng.shuffle(g)
            out += g[:per if per else round(total * len(g) / len(items))]
        return out

    protected = {r['input'] for r in json.loads((GATE2 / 'data/dev-protocol.json').read_text(encoding='utf-8'))['validation']}
    protected |= {r['input'] for r in jsonl(CORPUS / 'dev-protocol.jsonl')}
    dropped = Counter()

    def keep(rows, name):
        out = []
        for r in rows:
            if r['input'] in protected:
                dropped[name + ':protocol_overlap'] += 1
            elif not fits(r):
                dropped[name + ':over_length'] += 1
            else:
                out.append(r)
        return out

    bfv3 = keep(stratified(jsonl(CORPUS / 'train.jsonl'), lambda r: r['task'], per=per_bfv3_task), 'bfv3')
    hist_all = [r for r in jsonl(HISTORICAL) if r['split'] == 'train']
    hist = keep(stratified(hist_all, lambda r: r['task'], total=historical_train), 'historical')
    v1 = keep([r for r in jsonl(GATE2 / 'data/open/train.jsonl') if r['task'] != 'basic_instruction'], 'gate2_v1')

    dev = jsonl(CORPUS / 'dev.jsonl')
    protocol_companies = {r['company_id'] for r in jsonl(CORPUS / 'dev-protocol.jsonl')}
    validation = [r for r in dev if r['company_id'] in protocol_companies]
    seen = {r['input'] for r in validation}
    placeholder = [r for r in dev if r['company_id'] not in protocol_companies and r['input'] not in seen]

    rows = []
    def add(r, split, source, kind, review):
        rows.append({'id': r.get('id'), 'split': split, 'company_id': r['company_id'], 'task': r['task'],
                     'input': r['input'], 'output': r['output'], 'origin': 'rule_generated', 'review': review,
                     'source_kind': kind, 'mix_source': source})
    for r in bfv3:
        add(r, 'train', 'bfv3', r['label_kind'], 'rule_verified')
    for r in hist:
        add(r, 'train', 'historical', r.get('source_kind', 'synthetic'), r['review'])
    for r in v1:
        add(r, 'train', 'gate2_v1', r['source_kind'], 'rule_verified')
    for r in validation:
        add(r, 'validation', 'bfv3', r['label_kind'], 'rule_verified')
    for r in placeholder:
        add(r, 'test', 'bfv3', r['label_kind'], 'rule_verified')
    rng.shuffle(rows)
    run.mkdir(parents=True)
    data = run / 'train-packed.jsonl'
    data.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    from training import read_dataset
    checked = read_dataset(data)
    counts = {s: sum(r['split'] == s for r in checked) for s in ('train', 'validation', 'test')}
    mix = Counter(r['mix_source'] for r in rows if r['split'] == 'train')
    write(run / 'plan.json', {
        'author': 'Created by Claude (Anthropic)', 'created_utc': utc(), 'base': 'Qwen/Qwen3-4B', 'seed': seed,
        'init_adapter': str(CHAMPION), 'init_adapter_sha256': sha(CHAMPION / 'adapter_model.safetensors'),
        'previous_run': 'runs/4b-bfv3-20261017T062749Z (bfv3 only; Gate 2 regression 18 -> 12, not promoted)',
        'sources': {'bfv3': str(CORPUS / 'train.jsonl'), 'historical': str(HISTORICAL), 'gate2_v1': str(GATE2 / 'data/open/train.jsonl')},
        'source_sha256': {'bfv3': sha(CORPUS / 'train.jsonl'), 'historical': sha(HISTORICAL), 'gate2_v1': sha(GATE2 / 'data/open/train.jsonl')},
        'train_mix': dict(mix), 'train_tasks': dict(Counter(r['task'] for r in rows if r['split'] == 'train')),
        'dropped': dict(dropped), 'max_length': max_length, 'packed_sha256': sha(data), 'packed_rows': counts,
        'excluded': 'Gate 2 v1 basic_instruction (defective contract, DATA_QUALITY_REVIEW.md); all eval-protocol inputs; corpus sealed test',
        'eval_protocols': {'bfv3_dev40': sha(CORPUS / 'dev-protocol.jsonl'), 'gate2_dev48': sha(GATE2 / 'data/dev-protocol.json')},
        'owner_decision': '2026-10-17: continue training 4B with old-contract replay; no temperature cutoff.'})
    print(json.dumps({'rows': counts, 'mix': mix, 'dropped': dropped}, default=dict))


def protocol_sets():
    return {'bfv3_dev40': [(r, r['expected']) for r in jsonl(CORPUS / 'dev-protocol.jsonl')],
            'gate2_dev48': [(r, r['expected']) for r in json.loads((GATE2 / 'data/dev-protocol.json').read_text(encoding='utf-8'))['validation']],
            # fresh 90-question basic-finance-v4 protocol: no prior run trained or selected on it
            'bfv4_dev90': [(r, r['expected']) for r in jsonl(BFV4 / 'dev-protocol.jsonl')]}


def summarize(details, timings):
    groups = defaultdict(lambda: {'correct': 0, 'total': 0})
    for d in details:
        groups[d['task']]['correct'] += d['correct']
        groups[d['task']]['total'] += 1
    return {'details': details, 'tasks': dict(groups),
            'macro_accuracy': statistics.mean(g['correct'] / g['total'] for g in groups.values()),
            'joint_correct': sum(d['correct'] for d in details), 'questions': len(details),
            'valid_json': sum(d['valid_json'] for d in details),
            'content_correct': sum(bool(d['content_correct']) for d in details),
            'source_correct': sum(d['source_id_correct'] is True for d in details),
            'source_eligible': sum(d['source_id_correct'] is not None for d in details),
            'numeric_correct': sum(d['numeric_correct'] is True for d in details),
            'numeric_eligible': sum(d['numeric_correct'] is not None for d in details),
            'regression_correct': sum(d['correct'] for d in details if d['task'].startswith('regression:')),
            'regression_total': sum(d['task'].startswith('regression:') for d in details),
            'latency_p50_s': statistics.median(timings),
            'max_temperature_c': max(d['gpu'].get('temperature_c', 0) for d in details)}


def score(name, output, row, expected):
    return score_gate2(output, row) if name == 'gate2_dev48' else score_bfv3(output, expected)


def evaluate(adapter, out, protocols):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    from ml_runtime import load_options, memory_stats
    from run_control import gpu_status
    if out.exists():
        raise SystemExit('Refuse to overwrite ' + str(out))
    torch.set_num_threads(4)
    source = BETA / '.runtime/model-sources/qwen3-4b'
    tokenizer = AutoTokenizer.from_pretrained(str(source), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(str(source), local_files_only=True, **load_options(torch, True, 'bfloat16'))
    model = PeftModel.from_pretrained(model, str(adapter))
    model.eval()
    model.config.use_cache = True
    sets = protocol_sets()
    for name in protocols:                                 # NAME=PATH: an extra jsonl protocol (e.g. a cycle's fresh dev set)
        if '=' in name:
            key, path = name.split('=', 1)
            sets[key] = [(r, r['expected']) for r in jsonl(path)]
    protocols = [n.split('=', 1)[0] for n in protocols]
    result = {'author': 'Created by Claude (Anthropic)', 'adapter': str(adapter),
              'adapter_sha256': sha(Path(adapter) / 'adapter_model.safetensors'), 'started_utc': utc(),
              'precision': 'NF4 BF16', 'decoding': 'greedy; thinking disabled', 'protocols': {}}
    for name in protocols:
        tokens = 192 if name == 'gate2_dev48' else 64 if name in ('bfv3_dev40', 'bfv4_dev90') else 256   # 256: quotes in revision rows
        details, timings = [], []
        for row, expected in sets[name]:
            prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': row['input']}], tokenize=False,
                                                   add_generation_prompt=True, enable_thinking=False)
            inputs = tokenizer(prompt, return_tensors='pt').to('cuda')
            started = time.monotonic()
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=tokens, do_sample=False, pad_token_id=tokenizer.eos_token_id)
            torch.cuda.synchronize()
            elapsed = time.monotonic() - started
            timings.append(elapsed)
            output = tokenizer.decode(generated[0, inputs.input_ids.shape[1]:], skip_special_tokens=True)
            scored = score(name, output, row, expected)
            details.append({'task': row['task'], 'company_id': row['company_id'], 'expected': expected, 'output': output,
                            'seconds': elapsed, 'gpu': gpu_status(), **scored})
            print('EVAL', name, len(details), '/', len(sets[name]), flush=True)
        result['protocols'][name] = summarize(details, timings)
        write(out, result)
    result.update(status='completed', ended_utc=utc(), memory=memory_stats(torch))
    write(out, result)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pack')
    p.add_argument('--run', type=Path, required=True)
    m = sub.add_parser('pack-mix')
    m.add_argument('--run', type=Path, required=True)
    e = sub.add_parser('eval')
    e.add_argument('--adapter', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    e.add_argument('--protocols', nargs='+', default=['bfv3_dev40', 'gate2_dev48'])
    a = ap.parse_args()
    if a.cmd == 'pack':
        pack(a.run.resolve())
    elif a.cmd == 'pack-mix':
        pack_mix(a.run.resolve())
    else:
        evaluate(a.adapter.resolve(), a.out.resolve(), a.protocols)


if __name__ == '__main__':
    main()
