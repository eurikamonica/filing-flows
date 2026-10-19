"""Explicit optional same-base CPU merge/equivalence pilot. Created by ChatGPT (OpenAI).

Not invoked by Gate 2. No cross-family weighted merging or parameter expansion.
"""
import argparse
import gc
from pathlib import Path
import shutil
from protocol import RUN, BETA, read, write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adapter',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    adapter=Path(args.adapter).resolve();out=Path(args.out).resolve()
    if not adapter.is_relative_to(RUN) or not out.is_relative_to(RUN) or out.exists():
        raise ValueError('Use an archived/current-run adapter and fresh export path inside the current run')
    manifest=read(adapter/'fsa_manifest.json'); config=read(adapter/'adapter_config.json')
    source=BETA/'.runtime/model-sources/qwen3-4b'
    if manifest['status']!='completed' or manifest['base_revision']!=read(source/'model-source.json')['revision']:
        raise ValueError('Completed same-revision adapter required')
    if config['r']!=8 or set(config['target_modules'])!={'q_proj','v_proj'}:
        raise ValueError('Unexpected adapter architecture')
    print('CPU BF16 same-base merge pilot; equivalence gate 0.125 max logit error and exact greedy next-token IDs; size remains 4B')
    if not args.execute:
        print('Prepared only; pass --execute for the separately scoped export experiment');return
    import psutil
    if psutil.virtual_memory().available<18*2**30 or shutil.disk_usage(RUN).free<20*2**30:
        raise RuntimeError('Insufficient CPU RAM or disk for explicit nonquantized export')
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(str(source),local_files_only=True)
    if max(tokenizer.get_vocab().values())>=read(source/'config.json')['vocab_size']:
        # Embedding padding beyond the tokenizer's largest ID is valid; resizing is not automatic.
        raise RuntimeError('Tokenizer ID exceeds embedding size; review before export')
    for filename in ('tokenizer.json','tokenizer_config.json'):
        from lab import sha
        if sha(adapter/filename)!=sha(source/filename):
            raise RuntimeError('Tokenizer bytes differ; review before merge')
    model=AutoModelForCausalLM.from_pretrained(str(source),local_files_only=True,torch_dtype=torch.bfloat16,device_map={'':'cpu'})
    model=PeftModel.from_pretrained(model,str(adapter)); model.eval()
    prompts=['Return JSON only: {"value":3}.','Compute free cash flow for OCF 80 and capex 25. Return JSON.']
    inputs=[tokenizer(p,return_tensors='pt') for p in prompts]
    with torch.inference_mode(): before=[model(**item).logits[:,-1,:].float() for item in inputs]
    merged=model.merge_and_unload(safe_merge=True); merged.save_pretrained(str(out)); tokenizer.save_pretrained(str(out))
    del model,merged;gc.collect()
    reloaded=AutoModelForCausalLM.from_pretrained(str(out),local_files_only=True,torch_dtype=torch.bfloat16,device_map={'':'cpu'}).eval()
    with torch.inference_mode(): after=[reloaded(**item).logits[:,-1,:].float() for item in inputs]
    errors=[float((a-b).abs().max()) for a,b in zip(before,after)]
    equal_tokens=all(int(a.argmax())==int(b.argmax()) for a,b in zip(before,after))
    passed=max(errors)<=0.125 and equal_tokens
    write(out/'merge-equivalence.json',{'author':'Created by ChatGPT (OpenAI)','prompts':prompts,'max_logit_errors':errors,
        'greedy_next_tokens_equal':equal_tokens,'passed':passed,'scope':'Two-prompt numerical smoke only; semantic development suite still required'})
    (out/'README.md').write_text('Created by ChatGPT (OpenAI). Same-base 4B merge experiment, not a larger model. Not approved for deployment.\n',encoding='utf-8')
    if not passed:raise RuntimeError('Export equivalence failed; retain only as a failed experiment')


if __name__=='__main__':main()
