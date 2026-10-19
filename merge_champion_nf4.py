"""QLoRA-faithful merge: dequantize the NF4 base the adapter was trained and evaluated on, then merge the LoRA.

Why: merge_champion.py merged into the original full-precision base. The adapter was trained on the NF4-quantized base,
and that merged model lost 8 Gate 2 questions (36 -> 28/48 as Q8_0 GGUF). Here every bnb Linear4bit weight is
dequantized exactly (bitsandbytes dequantize_4bit, same NF4 double-quant config as training) and the LoRA delta is
merged on top, so the exported weights match what training/evaluation actually computed.
Check: greedy outputs of NF4+LoRA (GPU, the evaluated path) vs the merged bf16 model (CPU) on fixed prompts,
plus max |logit| error reported. Created by Claude (Anthropic).
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time

LAB = Path(__file__).resolve().parent
BETA = LAB.parent
SOURCE = BETA / '.runtime/model-sources/qwen3-4b'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check_prompts():
    rows = json.loads((LAB / 'runs/20261016T171524Z/data/dev-protocol.json').read_text(encoding='utf-8'))['validation']
    picked = [r['input'] for r in rows if r['task'] in ('field_extraction', 'missing_field')][:2]
    picked += [r['input'] for r in rows if r['task'].startswith('regression:')][:4]
    picked += ['Compute free cash flow for OCF 142 and capex 43. Return only JSON with value.']
    return picked


def run(model, tokenizer, torch, prompts, device):
    logits, texts = [], []
    for p in prompts:
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': p}], add_generation_prompt=True,
                                            enable_thinking=False, return_tensors='pt').to(device)
        with torch.inference_mode():
            logits.append(model(ids).logits[:, -1, :].float().cpu())
            out = model.generate(ids, max_new_tokens=96, do_sample=False, pad_token_id=tokenizer.eos_token_id)
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
    import torch
    import bitsandbytes.functional as F
    import bitsandbytes as bnb
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel
    started = time.time()
    tokenizer = AutoTokenizer.from_pretrained(str(SOURCE), local_files_only=True)
    prompts = check_prompts()
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.bfloat16)   # identical to ml_runtime.load_options(qlora, bf16)
    # Memory: load the dense CPU model first, then write each dequantized NF4 weight straight into it, one layer at a
    # time, instead of holding a second full copy of the dequantized weights (peak RAM ~8 GB instead of ~15 GB).
    full = AutoModelForCausalLM.from_pretrained(str(SOURCE), local_files_only=True, dtype=torch.bfloat16)
    state = full.state_dict()
    nf4 = AutoModelForCausalLM.from_pretrained(str(SOURCE), local_files_only=True, dtype=torch.bfloat16,
                                               device_map={'': 0}, quantization_config=quant)
    # reference: the evaluated path (NF4 base + LoRA on GPU)
    ref = PeftModel.from_pretrained(nf4, str(adapter)).eval()
    ref_logits, ref_text = run(ref, tokenizer, torch, prompts, 'cuda')
    base = ref.get_base_model()
    replaced = 0
    with torch.no_grad():
        for name, module in base.named_modules():
            if isinstance(module, bnb.nn.Linear4bit):
                key = name.replace('.base_layer', '') + '.weight'   # LoRA-wrapped layers keep the 4-bit weight in base_layer
                if key not in state:
                    raise SystemExit('Dequantized name not found in full model: ' + key)
                w = F.dequantize_4bit(module.weight.data, module.weight.quant_state).to(torch.bfloat16)
                if state[key].shape != w.shape:
                    raise SystemExit('Shape mismatch for ' + key)
                state[key].copy_(w.cpu())
                replaced += 1
                del w
    if replaced == 0:
        raise SystemExit('No 4-bit layers found')
    del ref, base, nf4
    gc.collect()
    torch.cuda.empty_cache()
    model = PeftModel.from_pretrained(full, str(adapter)).eval()
    merged = model.merge_and_unload(safe_merge=True).eval()
    merged_logits, merged_text = run(merged, tokenizer, torch, prompts, 'cpu')
    errors = [float((x - y).abs().max()) for x, y in zip(ref_logits, merged_logits)]
    same = [x == y for x, y in zip(ref_text, merged_text)]
    merged.save_pretrained(str(out), safe_serialization=True)
    tokenizer.save_pretrained(str(out))
    status = {'author': 'Created by Claude (Anthropic)', 'status': 'passed' if all(same) else 'outputs_differ',
              'method': 'NF4 (double quant, bf16 compute) base dequantized with bitsandbytes, LoRA merged in bf16 on CPU',
              'base': 'Qwen/Qwen3-4B', 'base_revision': json.loads((SOURCE / 'model-source.json').read_text(encoding='utf-8'))['revision'],
              'adapter': str(adapter), 'adapter_sha256': sha(adapter / 'adapter_model.safetensors'),
              'reference': 'NF4 base + LoRA on GPU (the path used for all training-time evaluations)',
              'greedy_outputs_equal': same, 'max_logit_abs_errors': errors, 'prompts': prompts,
              'reference_outputs': ref_text, 'merged_outputs': merged_text,
              'note': 'Logit differences reflect NF4 kernel vs dense bf16 arithmetic on identical weights.',
              'files': {p.name: sha(p) for p in sorted(out.glob('*.safetensors'))}, 'seconds': time.time() - started}
    (out / 'merge-status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    print(json.dumps({k: status[k] for k in ('status', 'greedy_outputs_equal', 'max_logit_abs_errors', 'seconds')}, indent=2))


if __name__ == '__main__':
    main()
