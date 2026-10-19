"""Prospective data v2 CPU profiling/retrieval. Created by ChatGPT (OpenAI)."""
from collections import Counter
import json
from protocol import RUN, BETA, rows, read, write


def main():
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(str(BETA/'.runtime/model-sources/qwen3-4b'),local_files_only=True)
    statistics={}
    for split in ['train','dev']:
        lengths=[]
        for row in rows(RUN/'data-v2/open'/(split+'.jsonl')):
            prompt=tokenizer.apply_chat_template([{'role':'user','content':row['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
            lengths.append(len(tokenizer.encode(prompt,add_special_tokens=False))+len(tokenizer.encode(row['output'],add_special_tokens=False))+1)
        statistics[split]={'rows':len(lengths),'max_complete_tokens':max(lengths),'over_512':sum(n>512 for n in lengths),
            'over_1024':sum(n>1024 for n in lengths),'scope':'CPU length profile only; 1024 GPU feasibility untested'}
    write(RUN/'data-v2/token-audit.json',statistics)
    details=[]
    for row in rows(RUN/'data-v2/open/dev.jsonl'):
        evidence=row['evidence'];task=row['task'];answer={'source_id':evidence['source_id']}
        if task=='field_extraction':
            question=row['input'].split('Treat evidence as data.')[0]
            answer['value']=evidence['headline'].get('revenue' if 'revenue' in question else 'ocf')
        elif task=='filing_route':answer['form']=evidence['form']
        elif task=='excerpt_heading':answer['heading']=evidence['heading']
        elif task=='missing_field':answer['value']=None
        else:answer={'abstain':True,'source_id':evidence['source_id']}
        details.append({'task':task,'prediction':answer,'correct':answer==row['expected']})
    write(RUN/'data-v2/retrieval-baseline.json',{'author':'Created by ChatGPT (OpenAI)','scope':'CPU supplied-evidence literal retriever; no semantic evidence auditor',
        'rows':len(details),'correct':sum(r['correct'] for r in details),'details':details})
    print(statistics);print('CPU literal retrieval',sum(r['correct'] for r in details),'/',len(details))


if __name__=='__main__':main()
