"""Merge a Qwen3-4B LoRA champion into its base on CPU in float16 and check equivalence.

Same procedure and thresholds as the passed fp16 export (operations/20261016T183600Z-fp16-merge):
max |logit| error <= 0.125 on the check prompts and identical greedy outputs. CUDA is hidden; the GPU is not used.
Created by Claude (Anthropic).
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import time

os.environ['CUDA_VISIBLE_DEVICES'] = ''
LAB = Path(__file__).resolve().parent
SOURCE = LAB.parent / '.runtime/model-sources/qwen3-4b'
PROMPTS = ['Compute free cash flow for OCF 142 and capex 43. Return only JSON with value.',
           'Return only one JSON object with these fields and types: {"value":"number or null","source_id":"string"}. '
           'Copy source_id S1.\nEvidence S1:\nnet_income: 468\noperating_cash_flow: 640\naverage_total_assets: 100\n'
           'Request: Compute annual accrual ratio (net income - OCF) / average total assets as a fraction.']


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def run(model, tokenizer, torch):
    logits, texts = [], []
    for p in PROMPTS:
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': p}], add_generation_prompt=True,
                                            enable_thinking=False, return_tensors='pt')
        with torch.inference_mode():
            logits.append(model(ids).logits[:, -1, :].float())
            out = model.generate(ids, max_new_tokens=48, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        texts.append(tokenizer.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
    return logits, texts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    adapter, out = a.adapter.resolve(), a.out.resolve()
    if out.exists():
        raise SystemExit('Output exists; choose a fresh path')
    config = json.loads((adapter / 'adapter_config.json').read_text(encoding='utf-8'))
    manifest = json.loads((adapter / 'fsa_manifest.json').read_text(encoding='utf-8'))
    revision = json.loads((SOURCE / 'model-source.json').read_text(encoding='utf-8'))['revision']
    if manifest['base_revision'] != revision or config['r'] != 8 or set(config['target_modules']) != {'q_proj', 'v_proj'}:
        raise SystemExit('Adapter does not match the pinned Qwen3-4B base or expected LoRA shape')
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    torch.set_num_threads(8)
    started = time.time()
    tokenizer = AutoTokenizer.from_pretrained(str(SOURCE), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(str(SOURCE), local_files_only=True, dtype=torch.float16)
    model = PeftModel.from_pretrained(model, str(adapter)).eval()
    before_logits, before_text = run(model, tokenizer, torch)
    merged = model.merge_and_unload(safe_merge=True)
    merged.save_pretrained(str(out), safe_serialization=True)
    tokenizer.save_pretrained(str(out))
    del model, merged
    gc.collect()
    reloaded = AutoModelForCausalLM.from_pretrained(str(out), local_files_only=True, dtype=torch.float16).eval()
    after_logits, after_text = run(reloaded, tokenizer, torch)
    errors = [float((x - y).abs().max()) for x, y in zip(before_logits, after_logits)]
    passed = max(errors) <= 0.125 and before_text == after_text
    status = {'author': 'Created by Claude (Anthropic)', 'status': 'passed' if passed else 'failed',
              'base': 'Qwen/Qwen3-4B', 'base_revision': revision, 'adapter': str(adapter),
              'adapter_sha256': sha(adapter / 'adapter_model.safetensors'), 'precision': 'CPU float16 merge, no quantization',
              'thresholds': {'max_logit_abs_error': 0.125, 'exact_greedy_outputs': True},
              'max_logit_abs_errors': errors, 'prompts': PROMPTS, 'before_outputs': before_text, 'after_outputs': after_text,
              'files': {p.name: sha(p) for p in sorted(out.glob('*.safetensors'))}, 'seconds': time.time() - started,
              'scope': 'Packaging check only; same 4B parameter count; quantized exports need their own evaluation'}
    (out / 'merge-status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    print(json.dumps({k: status[k] for k in ('status', 'max_logit_abs_errors', 'before_outputs', 'after_outputs', 'seconds')}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
