"""Explicit merge and pinned 8B download operations. Created by ChatGPT (OpenAI)."""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from lab import LAB, BETA, AUTHOR, configure, read, write, sha


def merge(run,dtype_name='bfloat16'):
    import psutil
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    torch.set_num_threads(4)
    dtype=getattr(torch,dtype_name)
    previous=Path(read(LAB/'current-run.json')['run'])
    adapter=previous/'archive/qwen4'
    source=BETA/'.runtime/model-sources/qwen3-4b'
    manifest=read(adapter/'fsa_manifest.json');base_manifest=read(source/'model-source.json')
    assert manifest['status']=='completed' and manifest['base_revision']==base_manifest['revision']
    config=read(source/'config.json'); peft_config=read(adapter/'adapter_config.json')
    assert peft_config['r']==8 and set(peft_config['target_modules'])=={'q_proj','v_proj'}
    largest=max(p.stat().st_size for p in source.glob('*.safetensors'))
    base_bytes=read(source/'model.safetensors.index.json')['metadata']['total_size']
    required_ram=base_bytes+largest+2*2**30
    if psutil.virtual_memory().available<required_ram:
        raise RuntimeError('CPU BF16 load budget unmet: need '+str(required_ram/2**30)+' GiB available')
    if shutil.disk_usage(run).free<base_bytes+20*2**30:
        raise RuntimeError('Insufficient disk for fresh merge plus reserve')
    original_tokenizer=AutoTokenizer.from_pretrained(str(source),local_files_only=True)
    adapter_tokenizer=AutoTokenizer.from_pretrained(str(adapter),local_files_only=True)
    messages=[{'role':'user','content':'Return JSON with value and formula. OCF=142, capex=43. Compute free cash flow.'}]
    template=lambda tok:tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
    tokenizer_checks={'vocabulary_equal':original_tokenizer.get_vocab()==adapter_tokenizer.get_vocab(),
        'special_ids_equal':original_tokenizer.all_special_ids==adapter_tokenizer.all_special_ids,
        'rendered_template_equal':template(original_tokenizer)==template(adapter_tokenizer),
        'max_id_within_embedding':max(adapter_tokenizer.get_vocab().values())<config['vocab_size']}
    if not all(tokenizer_checks.values()):raise RuntimeError('Tokenizer semantic compatibility failed: '+str(tokenizer_checks))
    output=run/('qwen4-merged-'+dtype_name)
    if output.exists():raise RuntimeError('Refuse to overwrite merge output')
    started=time.monotonic()
    result={'author':AUTHOR,'status':'running','base_revision':base_manifest['revision'],
        'adapter_sha256':sha(adapter/'adapter_model.safetensors'),'tokenizer_checks':tokenizer_checks,
        'ram_required_gib':required_ram/2**30,'precision':'CPU '+dtype_name+'; no quantization/offload',
        'thresholds':{'max_logit_abs_error':0.125,'exact_greedy_outputs':True},
        'scope':'Same-base 4B export packaging; no parameter growth; not full production acceptance'}
    write(run/'merge-status.json',result)
    prompts=[messages[0]['content'],'Return JSON with value and formula. OCF=80, capex=25. Compute free cash flow.']
    def evaluate(model):
        logits=[];outputs=[]
        for prompt in prompts:
            rendered=adapter_tokenizer.apply_chat_template([{'role':'user','content':prompt}],tokenize=False,
                add_generation_prompt=True,enable_thinking=False)
            inputs=adapter_tokenizer(rendered,return_tensors='pt')
            with torch.inference_mode():
                score=model(**inputs).logits[:,-1,:].float().clone()
                if not torch.isfinite(score).all():raise RuntimeError('Nonfinite merge validation logits')
                logits.append(score)
                generated=model.generate(**inputs,max_new_tokens=48,do_sample=False,pad_token_id=adapter_tokenizer.eos_token_id)
            outputs.append(adapter_tokenizer.decode(generated[0,inputs.input_ids.shape[1]:],skip_special_tokens=True))
            print('CPU_EQUIVALENCE',len(outputs),outputs[-1],flush=True)
        return logits,outputs
    model=AutoModelForCausalLM.from_pretrained(str(source),local_files_only=True,torch_dtype=dtype,
        low_cpu_mem_usage=True,device_map={'':'cpu'})
    model=PeftModel.from_pretrained(model,str(adapter),device_map={'':'cpu'});model.eval();model.config.use_cache=True
    actual_devices=sorted({parameter.device.type for parameter in model.parameters()})
    result['actual_parameter_devices']=actual_devices
    if actual_devices!=['cpu']:
        raise RuntimeError('CPU-only equivalence contract violated before generation: '+str(actual_devices))
    before,before_text=evaluate(model)
    merged=model.merge_and_unload(safe_merge=True)
    merged.save_pretrained(str(output),max_shard_size='2GB');adapter_tokenizer.save_pretrained(str(output))
    del model,merged;gc.collect()
    reloaded=AutoModelForCausalLM.from_pretrained(str(output),local_files_only=True,torch_dtype=dtype,
        low_cpu_mem_usage=True,device_map={'':'cpu'}).eval()
    after,after_text=evaluate(reloaded)
    errors=[float((a-b).abs().max()) for a,b in zip(before,after)]
    passed=max(errors)<=0.125 and before_text==after_text
    result.update(status='passed_smoke' if passed else 'failed_equivalence',max_logit_abs_errors=errors,
        prompts=prompts,before_outputs=before_text,after_outputs=after_text,seconds=time.monotonic()-started,
        output=str(output),files_sha256={p.name:sha(p) for p in output.iterdir() if p.is_file()})
    write(run/'merge-status.json',result)
    (output/'README.md').write_text('# Merged Qwen3-4B research export\n\nCreated by ChatGPT (OpenAI).\n\nSame-base '+dtype_name+' merge; retains 4B architecture. '+result['status']+'. Two-prompt packaging check only; not production model validation.\n',encoding='utf-8')
    if not passed:raise RuntimeError('Export equivalence failed; no deployment approval inferred')


def download(run):
    from huggingface_hub import HfApi,snapshot_download
    api=HfApi();model_id='Qwen/Qwen3-8B';info=api.model_info(model_id,files_metadata=True)
    license_name=getattr(info.card_data,'license',None)
    if license_name!='apache-2.0':raise RuntimeError('Unexpected license metadata; inspect before downloading weights: '+str(license_name))
    weight_files=[s for s in info.siblings if s.rfilename.endswith('.safetensors')]
    size=sum(s.size or 0 for s in weight_files)
    if not weight_files or size<=0:raise RuntimeError('Model weight size unavailable')
    if shutil.disk_usage(run).free < size+20*2**30:raise RuntimeError('Insufficient storage for pinned 8B download plus reserve')
    destination=run/'qwen3-8b-source'
    metadata={'author':AUTHOR,'model_id':model_id,'revision':info.sha,'license':license_name,'status':'downloading',
        'expected_safetensors_bytes':size,'destination':str(destination),'training_started':False}
    write(run/'download-status.json',metadata)
    print('PINNED_8B',info.sha,'WEIGHT_GIB',size/2**30,flush=True)
    snapshot_download(model_id,revision=info.sha,local_dir=str(destination),max_workers=1,
        allow_patterns=['*.json','*.safetensors','*.txt','*.jinja','README.md','LICENSE','LICENSE.txt'])
    metadata.update(status='completed',files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in destination.iterdir() if p.is_file()})
    write(run/'download-status.json',metadata)
    (destination/'LOCAL_PROVENANCE.md').write_text('# Local pinned model source\n\nCreated by ChatGPT (OpenAI).\n\n'+model_id+' at revision '+info.sha+'. Apache-2.0 metadata verified. Weights downloaded only; no inference, training or production integration executed.\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','merge','download']);parser.add_argument('--run')
    parser.add_argument('--dtype',choices=['float16','bfloat16'],default='bfloat16');args=parser.parse_args()
    if args.action=='start':
        run=LAB/'operations'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run.mkdir(parents=True,exist_ok=False);configure(run)
        write(LAB/'current-operation.json',{'author':AUTHOR,'run':str(run)})
        state={'author':AUTHOR,'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'Explicit user request: same-base merge and 8B download; production target details pending','jobs':[]}
        for action,timeout in [('merge',1200),('download',3600)]:
            with (run/(action+'.log')).open('w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-u',str(Path(__file__)),action,'--run',str(run)],cwd=BETA,
                    env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                state.update(active_job=action,child_pid=process.pid);write(run/'state.json',state)
                try:code=process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    import psutil
                    parent=psutil.Process(process.pid)
                    for item in parent.children(recursive=True)[::-1]+[parent]:
                        try:item.terminate()
                        except psutil.NoSuchProcess:pass
                    process.wait(timeout=30);code=-99
                state['jobs'].append({'job':action,'exit_code':code,'log':str(run/(action+'.log'))})
                write(run/'state.json',state)
        state.update(status='ended',active_job=None,child_pid=None,ended_utc=datetime.now(timezone.utc).isoformat());write(run/'state.json',state)
        return
    run=Path(args.run).resolve()
    if not run.is_relative_to(LAB/'operations'):raise ValueError('Operation must remain in this lab')
    configure(run)
    if args.action=='merge':
        os.environ['CUDA_VISIBLE_DEVICES']=''
    try:merge(run,args.dtype) if args.action=='merge' else download(run)
    except Exception as exc:
        path=run/('merge-status.json' if args.action=='merge' else 'download-status.json')
        status=read(path) if path.exists() else {'author':AUTHOR}
        status.update(status='failed',error=repr(exc));write(path,status)
        raise


if __name__=='__main__':main()
