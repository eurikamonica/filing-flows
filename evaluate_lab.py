"""Fixed development-only evaluator. Created by ChatGPT (OpenAI)."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import statistics
import sys
import time
from protocol import RUN, BETA, configure, read, write, sha
configure(RUN)
sys.path.insert(0,str(BETA))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--adapter',required=True); parser.add_argument('--out',required=True); args=parser.parse_args()
    overall_deadline = None
    job_history = RUN/'jobs.jsonl'
    if job_history.exists():
        first = json.loads(job_history.read_text(encoding='utf-8').splitlines()[0])
        overall_deadline = datetime.fromisoformat(first['ended_utc']) - timedelta(seconds=first['seconds']) + timedelta(seconds=read(RUN/'plan.json')['total_wall_seconds'])
        if datetime.now(timezone.utc) >= overall_deadline:
            write(RUN/(args.out+'.json'),{'author':'Created by ChatGPT (OpenAI)','status':'stopped','stop_reason':'overall_time_budget','details':[]})
            raise RuntimeError('Overall protocol budget exhausted before model loading')
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    from ml_runtime import load_options, memory_stats
    from overnight_worker import equal
    from run_control import gpu_status
    torch.set_num_threads(4)
    source=BETA/'.runtime/model-sources/qwen3-4b'
    manifest=read(__import__('pathlib').Path(args.adapter)/'fsa_manifest.json')
    assert manifest['status']=='completed' and manifest['base_revision']==read(RUN/'plan.json')['revision']
    tokenizer=AutoTokenizer.from_pretrained(str(source),local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(str(source),local_files_only=True,**load_options(torch,True,'bfloat16'))
    model=PeftModel.from_pretrained(model,args.adapter); model.eval(); model.config.use_cache=True
    data=read(RUN/'data/dev-protocol.json')['validation']
    result={'author':'Created by ChatGPT (OpenAI)','adapter':args.adapter,'status':'running','details':[],
            'dataset_sha256':sha(RUN/'data/dev-protocol.json'),'max_new_tokens':192,'precision':'NF4 BF16','batch_size':1}
    timings=[]
    for row in data:
        if overall_deadline and datetime.now(timezone.utc) >= overall_deadline:
            result.update(status='stopped',stop_reason='overall_time_budget')
            write(RUN/(args.out+'.json'),result)
            raise RuntimeError('Overall protocol budget exhausted during evaluation')
        gpu=gpu_status()
        if 'error' in gpu or gpu['temperature_c']>=86:
            result.update(status='stopped',stop_reason='thermal_or_monitor_guard')
            write(RUN/(args.out+'.json'),result)
            raise RuntimeError('Evaluation stopped by thermal/monitor guard; no retry')
        prompt=tokenizer.apply_chat_template([{'role':'user','content':row['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inputs=tokenizer(prompt,return_tensors='pt').to('cuda')
        started=time.monotonic()
        with torch.inference_mode():
            generated=model.generate(**inputs,max_new_tokens=192,do_sample=False,pad_token_id=tokenizer.eos_token_id)
        torch.cuda.synchronize(); elapsed=time.monotonic()-started; timings.append(elapsed)
        output=tokenizer.decode(generated[0,inputs.input_ids.shape[1]:],skip_special_tokens=True)
        try:
            def reject(value): raise ValueError(value)
            actual=json.loads(output,parse_constant=reject)
            valid=isinstance(actual,dict)
        except (ValueError,TypeError): actual=None; valid=False
        expected=row['expected']
        arithmetic = row['task'].startswith('regression:Compute ') or row['task'] in ('reserve_calculation','accrual_ratio','amended_ytd')
        content=valid and (equal(actual.get('value'),expected.get('value'),True) if arithmetic else
            equal(actual,{k:v for k,v in expected.items() if k!='source_id'}))
        eligible='source_id' in expected
        source_correct=valid and actual.get('source_id')==expected.get('source_id') if eligible else None
        correct=content and (source_correct if eligible else True)
        result['details'].append({'task':row['task'],'company_id':row['company_id'],'input':row['input'],
            'expected':expected,'output':output,'valid_json':valid,'content_correct':content,'source_id_correct':source_correct,
            'correct':correct,'seconds':elapsed,'utc':datetime.now(timezone.utc).isoformat()})
        write(RUN/(args.out+'.json'),result)
        print(args.out,len(result['details']),len(data),flush=True)
    tasks={}
    for row in result['details']:
        group=tasks.setdefault(row['task'],{'rows':0,'correct':0}); group['rows']+=1; group['correct']+=row['correct']
    result.update(status='completed',tasks=tasks,latency_p50_s=statistics.median(timings),memory=memory_stats(torch),
        macro_accuracy=statistics.mean(g['correct']/g['rows'] for g in tasks.values()),
        valid_json=sum(r['valid_json'] for r in result['details']),content_correct=sum(r['content_correct'] for r in result['details']),
        source_id_correct=sum(r['source_id_correct'] is True for r in result['details']),
        source_id_eligible=sum(r['source_id_correct'] is not None for r in result['details']),
        new_correct=sum(r['correct'] for r in result['details'] if not r['task'].startswith('regression:')),
        regression_correct=sum(r['correct'] for r in result['details'] if r['task'].startswith('regression:')))
    write(RUN/(args.out+'.json'),result)


if __name__=='__main__': main()
