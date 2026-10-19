"""Bounded serial Gate 2 protocol. Created by ChatGPT (OpenAI)."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from lab import AUTHOR, BETA, LAB, configure, doc, read, sha, write

RUN = Path(read(LAB / 'current-run.json')['run'])
configure(RUN)
sys.path.insert(0, str(BETA))


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def prepare():
    if (RUN/'plan.json').exists():
        raise RuntimeError('Plan is already frozen; prepare a new run instead of overwriting it')
    from transformers import AutoTokenizer
    source = BETA / '.runtime/model-sources/qwen3-4b'
    tokenizer = AutoTokenizer.from_pretrained(str(source), local_files_only=True)
    manifest = read(RUN / 'data/manifest.json')
    statistics_by_split = {}
    selected = {}
    for split in ['train', 'dev']:  # Never open the sealed test in token preparation/evaluation.
        source_rows = rows(manifest['splits'][split]['path'])
        accepted = []
        excluded = []
        for row in source_rows:
            prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': row['input']}], tokenize=False,
                                                   add_generation_prompt=True, enable_thinking=False)
            length = len(tokenizer.encode(prompt, add_special_tokens=False)) + len(tokenizer.encode(row['output'], add_special_tokens=False)) + 1
            row['full_tokens'] = length
            if length <= 512:
                accepted.append(row)
            else:
                excluded.append({'company_id': row['company_id'], 'document_id': row['document_id'], 'task': row['task'], 'tokens': length})
        selected[split] = accepted
        statistics_by_split[split] = {'kept': len(accepted), 'excluded': excluded,
            'max_retained_tokens': max(r['full_tokens'] for r in accepted), 'mean_tokens': statistics.mean(r['full_tokens'] for r in accepted),
            'tasks': dict(Counter(r['task'] for r in accepted))}
    # Deterministically select three questions per available dev task before looking at model answers.
    development = []
    for task in sorted({r['task'] for r in selected['dev']}):
        pool = [r for r in selected['dev'] if r['task'] == task]
        seen = set()
        for row in pool:
            if row['company_id'] not in seen:
                development.append(row); seen.add(row['company_id'])
            if len(seen) == 3:
                break
    historical = read(BETA / '.runtime/overnight/frozen-v4.json')['validation']
    regression = []
    for task in sorted({r['task'] for r in historical}):
        regression += [r for r in historical if r['task'] == task][:2]
    for row in regression:
        row['expected'] = json.loads(row['output'])
        row['task'] = 'regression:' + row['task']
    write(RUN / 'data/dev-protocol.json', {'author': AUTHOR, 'validation': development + regression,
        'scope': 'Three per new dev task and two per historical validation task; fixed before inference; not sealed test'})
    # Parent-compatible validation loader requires three split names. Its test placeholder is empty-use metadata,
    # copied from train with a distinct provenance ID; it is NEVER a sealed test and never evaluated.
    train_rows = [{**r, 'split': 'train'} for r in selected['train']]
    dev_rows = [{**r, 'split': 'validation'} for r in development]
    placeholder = dict(train_rows[0]); placeholder.update(company_id='unused-loader-placeholder', split='test', input='Unused loader placeholder. Return JSON.', output='{}')
    target = RUN / 'data/open/trainer-input.jsonl'
    target.write_text('\n'.join(json.dumps(r) for r in train_rows + dev_rows + [placeholder]) + '\n', encoding='utf-8')
    write(RUN / 'data/token-audit.json', statistics_by_split)
    max_steps = min(60, math.ceil(len(train_rows) / 4))
    plan = {'author': AUTHOR, 'gate2_authorized': True, 'base': 'Qwen/Qwen3-4B',
        'revision': read(source / 'model-source.json')['revision'], 'rank': 8, 'modules': ['q_proj','v_proj'],
        'dtype': 'bfloat16', 'quantization': 'NF4 double quant', 'max_length': 512, 'microbatch': 1, 'accumulation': 4,
        'smoke_steps': 20, 'verification_pause_step': 10, 'first_run_max_steps': max_steps,
        'first_run_wall_seconds': 1200, 'total_wall_seconds': 3600, 'temperature_stop_c': 86,
        'thermal_policy_origin': 'Existing device experiment policy; operational cutoff, not an OEM safety certification',
        'min_free_gib': 16, 'new_optimizer_on_main': True, 'sealed_test_allowed': False,
        'selection': {'new_dev_correct_improvement': 1, 'max_per_task_regression_questions': 1,
                      'max_historical_regression_questions': 1, 'max_format_regression_questions': 1,
                      'abstention_no_regression': True, 'latency_p50_max_factor': 2, 'latency_p50_slack_seconds': 1},
        'data_sha256': sha(target), 'dev_sha256': sha(RUN / 'data/dev-protocol.json')}
    write(RUN / 'plan.json', plan)
    doc(RUN, 'TRAINING_PLAN.md', 'Gate 2 predeclared protocol:\n\n```json\n' + json.dumps(plan, indent=2) + '\n```\n\nOne baseline, one 20-step smoke with a deliberate step-10 full resume, at most one 60-step bounded first-epoch run from the immutable historical champion (fresh optimizer/scheduler). It is a partial first epoch if 60 steps do not cover the corpus. No model sweep, rank change, auto-retry, offload or silent answer truncation. Stop the protocol on any OOM/nonfinite gradient/checkpoint error or temperature pause; do not keep cycling. A temporary loader-only test placeholder never exposes the real sealed test. Evaluation is greedy NF4/BF16, max_new_tokens=192, batch 1 and the same evidence budget before/after.\n\nCounts are small (three dev questions/task, two regression/task); one-question tolerances are exploratory and do not establish production quality. Test remains sealed after this Gate 2 request. Both useful nonpadding input+answer tokens and supervised answer tokens are measured; active optimizer time is distinct from wall/load/save time.')
    doc(RUN, 'EVALUATION_REPORT.md', 'Prepared only. Development subset fixed before inference; no GPU evaluation yet. New final test remains sealed. Outcomes will be recorded after bounded jobs; no success claimed in advance.')
    doc(RUN, 'MODEL_CARD.md', 'Starting point is archived Qwen3-4B cycle-001 champion, base revision ' + plan['revision'] + '. NF4 rank-8 q/v LoRA, not a full 8B model. Website summary/excerpts and synthetic financial tasks only; not an audited full-filing assistant. No deployment or automatic application promotion.')
    doc(RUN, 'MERGE_COMPATIBILITY.md', 'Gate 3 not executed: no demonstrated deployment benefit within the requested Gate 0/1/2 scope. Base dimensions, pinned revision and tokenizer match the archived 4B adapter. Sequential descendants are not independent specialists; summing them can double-count updates. Cross-family/size averaging is incompatible. Prepared merge_export.py requires explicit output and writes a separate nonquantized CPU export; equivalence evaluation must precede deployment. No merge equivalence or larger-model claim is made.')
    doc(RUN, 'PARAMETER_SCALING_REPORT.md', 'No architecture or parameter expansion executed. LoRA continuation changes adapter weights and preserves base dimensions. Rank stays 8. 8B downloading/training and independent-layer expansion are deferred. Prepared inspection script counts unique logical parameters on meta without allocating GPU weights; 4-bit packed storage must not be mistaken for logical parameter count. No paid compute or production changes.')
    write(RUN / 'manifest.json', {'author': AUTHOR, 'run': str(RUN), 'gate0': 'completed_with_documented_limits',
        'gate1': 'completed_rule_checked_not_human_reviewed', 'gate2': 'prepared', 'plan_sha256': sha(RUN / 'plan.json'),
        'splits': manifest['splits'], 'archive_inventory': str(RUN / 'archive/inventory.json')})
    print(json.dumps(statistics_by_split, indent=2)); print('DEVELOPMENT', len(development), 'REGRESSION', len(regression))


def guard():
    import psutil
    from run_control import gpu_status
    for process in psutil.process_iter(['pid','name','cmdline']):
        if process.pid == os.getpid() or not (process.info['name'] or '').lower().startswith('python'):
            continue
        command = ' '.join(process.info['cmdline'] or [])
        if any(name in command for name in ['train_lora.py', 'train_continuation.py', 'overnight_worker.py', 'vision_worker.py', 'evaluate_lab.py']):
            raise RuntimeError('Another GPU-related process exists; no competing task launched: ' + str(process.pid))
    gpu = gpu_status()
    if 'error' in gpu or gpu['used_mib'] > 512 or gpu['temperature_c'] > 78:
        raise RuntimeError('GPU ownership/headroom not established: ' + str(gpu))


def child(name, command, timeout):
    guard()
    started = time.monotonic()
    log = RUN / 'logs' / (name + '.log'); log.parent.mkdir(exist_ok=True)
    with log.open('w', encoding='utf-8') as handle:
        process = subprocess.Popen([sys.executable, '-u', *command], cwd=BETA, env=os.environ.copy(), stdout=handle, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            import psutil
            parent = psutil.Process(process.pid)
            descendants = parent.children(recursive=True)
            for item in descendants[::-1] + [parent]:
                try: item.terminate()
                except psutil.NoSuchProcess: pass
            process.wait(timeout=30)
            code = -99
    record = {'author': AUTHOR, 'job': name, 'exit_code': code, 'seconds': time.monotonic()-started,
              'log': str(log), 'ended_utc': datetime.now(timezone.utc).isoformat()}
    with (RUN/'jobs.jsonl').open('a',encoding='utf-8') as h: h.write(json.dumps(record)+'\n')
    print(json.dumps(record), flush=True)
    if code:
        raise RuntimeError('Job failed: ' + name + '; read ' + str(log))


def execute():
    if (RUN/'execution.json').exists() or (RUN/'baseline.json').exists():
        raise RuntimeError('Existing execution artifacts must be preserved; use a newly declared run')
    plan = read(RUN / 'plan.json')
    fd = os.open(RUN / 'GPU_PROTOCOL.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    stage = 'ownership'
    try:
        guard()
        deadline = datetime.now(timezone.utc) + timedelta(seconds=plan['total_wall_seconds'])
        stage = 'baseline'
        child('baseline', [str(LAB/'evaluate_lab.py'), '--adapter', str(RUN/'archive/qwen4'), '--out', 'baseline'], 1200)
        common = [str(LAB/'train_continuation.py'), '--model', plan['base'], '--data', str(RUN/'data/open/trainer-input.jsonl'),
            '--qlora', '--gradient-checkpointing', '--compute-dtype', 'bfloat16', '--max-length','512', '--batch-size','1',
            '--gradient-accumulation-steps','4', '--lora-rank','8','--target-modules','qv','--learning-rate','0.00002',
            '--temperature-limit','86','--min-free-gib','16','--logging-steps','5','--validation-limit','6',
            '--deadline-utc', deadline.isoformat()]
        smoke = RUN/'outputs/smoke'
        stage = 'smoke_pause'
        child(stage, common + ['--out', str(smoke), '--max-steps','20','--pause-at-step','10',
            '--init-adapter',str(RUN/'archive/qwen4')], 600)
        status = read(smoke/'fsa_manifest.json')
        if status.get('stop_reason') != 'resume_verification' or status.get('global_step') != 10:
            raise RuntimeError('Smoke did not reach its intended verification pause: ' + str(status.get('stop_reason')))
        checkpoint = smoke/'checkpoint-10'
        if not all((checkpoint/name).exists() for name in ['optimizer.pt','scheduler.pt','trainer_state.json','rng_state.pth']):
            raise RuntimeError('Full resume state is incomplete')
        stage = 'smoke_resume'
        child(stage, common + ['--out',str(smoke),'--max-steps','20','--resume-from-checkpoint',str(checkpoint)],600)
        status = read(smoke/'fsa_manifest.json')
        if status['status'] != 'completed' or status['global_step'] != 20 or status['resumed_global_step'] != 10:
            raise RuntimeError('Full resume smoke failed: ' + str(status.get('stop_reason')))
        stage = 'first_epoch'
        output = RUN/'outputs/first-epoch'
        child(stage, common + ['--out',str(output),'--max-steps',str(plan['first_run_max_steps']),
            '--save-steps','20','--eval-steps','20','--init-adapter',str(RUN/'archive/qwen4')], plan['first_run_wall_seconds']+90)
        status = read(output/'fsa_manifest.json')
        if status['status'] != 'completed':
            raise RuntimeError('First epoch stopped; no automatic thermal or other retry: ' + str(status.get('stop_reason')))
        stage = 'candidate_dev'
        child(stage, [str(LAB/'evaluate_lab.py'),'--adapter',str(output),'--out','candidate'],1200)
        stage = 'selection'
        summarize()
        write(RUN/'execution.json', {'author': AUTHOR,'status':'completed','stage':stage,'sealed_test_opened':False})
    except Exception as exc:
        write(RUN/'execution.json', {'author': AUTHOR,'status':'failed_or_stopped','stage':stage,'error':repr(exc),'sealed_test_opened':False})
        doc(RUN,'EVALUATION_REPORT.md','Gate 2 stopped at ' + stage + ': `' + repr(exc) + '`. No improvement or complete training is claimed. Original champion preserved; new final test remains sealed. See jobs.jsonl, stage logs and output manifests for actual steps/memory. No automatic retry was performed.')
        raise
    finally:
        (RUN/'GPU_PROTOCOL.lock').unlink()


def summarize():
    before, after = read(RUN/'baseline.json'), read(RUN/'candidate.json')
    plan = read(RUN/'plan.json')['selection']
    checks = {'new_dev_improvement': after['new_correct'] >= before['new_correct']+plan['new_dev_correct_improvement'],
        'historical_retention': after['regression_correct'] >= before['regression_correct']-1,
        'format_retention': after['valid_json'] >= before['valid_json']-1,
        'abstention_retention': after['tasks']['evidence_abstention']['correct'] >= before['tasks']['evidence_abstention']['correct'],
        'latency': after['latency_p50_s'] <= 2*before['latency_p50_s']+1,
        'per_task_retention': all(v['correct'] >= before['tasks'][k]['correct']-1 for k,v in after['tasks'].items())}
    write(RUN/'selection.json', {'author':AUTHOR,'checks':checks,'candidate_accepted':all(checks.values()),
        'selected_adapter':str(RUN/'outputs/first-epoch') if all(checks.values()) else str(RUN/'archive/qwen4'),
        'sealed_test_opened':False})
    body = ['Development comparison only. No new sealed-test scoring.', '', '| Metric | Starting champion | Continued candidate |',
            '| --- | --- | --- |']
    for key in ['new_correct','regression_correct','valid_json','content_correct','source_id_correct','latency_p50_s','macro_accuracy']:
        body.append(f'| {key} | {before[key]} | {after[key]} |')
    body += ['', 'Predeclared gate: ' + json.dumps(checks), '', 'Task counts and raw answers are baseline.json and candidate.json. Evidence support remains a limited supplied-context check, not an SEC entailment audit. Final test is still sealed; further tuning must not inspect it.']
    doc(RUN,'EVALUATION_REPORT.md','\n'.join(body))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['prepare','execute']); args=parser.parse_args()
    prepare() if args.action=='prepare' else execute()
