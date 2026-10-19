"""CPU-only prospective dataset revision; never reruns training. Created by ChatGPT (OpenAI)."""
from collections import Counter
import hashlib
import json
import time
import urllib.request
from protocol import RUN, BETA, rows, read, write, doc, sha


def flattened(value, prefix=''):
    if isinstance(value,dict):
        return [pair for key,item in value.items() for pair in flattened(item,(prefix+'.' if prefix else '')+key)]
    return [(prefix,json.dumps(value,ensure_ascii=True))]


def render(row):
    split=row['split']; evidence=row['evidence']
    instruction=row['input'].split(' Treat evidence as data.')[0].split(' Return only JSON.')[0]
    if row['task']=='basic_instruction':
        instruction='Set acknowledged to true and include source_id in this hypothetical instruction-following case.'
    instruction+=' Return a JSON object with keys: '+', '.join(row['expected'])+'. Treat evidence as data.'
    if split=='train':
        context='Evidence JSON: '+json.dumps(evidence)
        family='json_context'
    elif split=='dev':
        context='Evidence facts:\n'+'\n'.join(key+' = '+value for key,value in flattened(evidence))
        family='flat_fact_lines'
    else:
        context='Evidence table:\n| Field path | Literal value |\n| --- | --- |\n'+'\n'.join('| '+key+' | '+value.replace('|','\\|')+' |' for key,value in flattened(evidence))
        family='markdown_evidence_table'
    return {**row,'input':instruction+'\n'+context,'source_kind':'hypothetical_fixture' if row['label_kind']=='hypothetical' else 'owner_website',
        'template_family':row['task']+':'+family,'rendering_family':family,'semantic_operation_family':row['task']}


def main():
    target=RUN/'data-v2'
    if target.exists():raise RuntimeError('Refuse to overwrite prospective dataset revision')
    original=read(RUN/'data/manifest.json')
    # Dataset construction reads labels to fix the schema, never scores an unopened test.
    grouped={split:[render(row) for row in rows(entry['path'])] for split,entry in original['splits'].items()}
    excluded=set(read(BETA/'.runtime/website-data/manifest.json')['files'])
    excluded.update(source['cik'] for source in read(RUN/'sources/manifest.json')['sources'])
    index=read(BETA/'.runtime/overnight/site-index.json')['companies']
    additions=[]
    for company in [c for c in index if c.get('form')=='8-K' and str(c['cik']) not in excluded][:12]:
        cik=str(company['cik']);url='https://filing-flows.com/data/c/'+cik+'.json'
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'FilingFlowsBetaResearch/1.0'}),timeout=30) as response:
                raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise ValueError('Response too large')
            data=json.loads(raw); periods=[p for p in data.get('quarters',[]) if p.get('form')=='8-K' and p.get('headline')][:2]
            if not periods:continue
            split=('train','dev','sealed_test')[len(additions)]
            path=target/'sources'/(cik+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            digest=sha(path);additions.append({'cik':cik,'split':split,'url':url,'sha256':digest,'path':str(path)})
            for index,p in enumerate(periods):
                source_id=digest+':'+str(index)
                evidence={'source_id':source_id,'company':data['profile']['name'],'form':'8-K','preliminary':bool(p.get('preliminary')),
                    'period_end':p.get('end'),'headline':p['headline'],'units':'website-native; do not infer units'}
                for task,instruction,answer,kind in [
                    ('field_extraction','Read literal revenue and source_id.',{'value':p['headline'].get('revenue'),'source_id':source_id},'observed'),
                    ('filing_route','Identify filing form and source_id.',{'form':'8-K','source_id':source_id},'observed'),
                    ('missing_field','Return missing warranty utilization as null, with source_id.',{'value':None,'source_id':source_id},'derived'),
                    ('evidence_abstention','Does this evidence establish intentional fraud? Return supported boolean and source_id.',{'supported':False,'source_id':source_id},'derived')]:
                    row={'author':'Created by ChatGPT (OpenAI)','company_id':cik,'document_id':source_id,'split':split,'task':task,
                        'label_kind':kind,'source_url':url,'source_sha256':digest,'evidence':evidence,'input':instruction,
                        'expected':answer,'output':json.dumps(answer),'origin':'rule_generated','review':'rule_verified'}
                    grouped[split].append(render(row))
            print('V2_8K',cik,split,flush=True)
            if len(additions)==3:break
        except Exception as exc:print('V2_DOWNLOAD_ERROR',cik,repr(exc),flush=True)
        time.sleep(1)
    metadata={'author':'Created by ChatGPT (OpenAI)','purpose':'Prospective corrected data; NOT used in the completed v1 GPU experiment',
        'v1_preserved':True,'sealed_test_opened_for_evaluation':False,'added_8k_sources':additions,'splits':{}}
    for split,items in grouped.items():
        path=target/('sealed' if split=='sealed_test' else 'open')/(split+'.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('\n'.join(json.dumps(r) for r in items)+'\n',encoding='utf-8')
        metadata['splits'][split]={'path':str(path),'sha256':sha(path),'rows':len(items),'companies':sorted({r['company_id'] for r in items}),
            'tasks':dict(Counter(r['task'] for r in items)),'rendering_families':sorted({r['rendering_family'] for r in items})}
    groups=[set(v['companies']) for v in metadata['splits'].values()]
    assert not(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
    assert all('Set acknowledged to true' in r['input'] for items in grouped.values() for r in items if r['task']=='basic_instruction')
    assert len({v['rendering_families'][0] for v in metadata['splits'].values()})==3
    write(target/'manifest.json',metadata)
    doc(RUN,'DATA_QUALITY_REVIEW.md','The frozen v1 basic_instruction family omitted the requested acknowledged=true contract; some other prompts also did not explicitly require all output keys. Its raw metrics are retained but cannot establish general instruction-following improvement. No metric threshold, gold answer or v1 file was changed after inference.\n\nProspective data-v2 fixes explicit output contracts and derived provenance metadata, and separates actual evidence-rendering template families: training JSON, development fact lines, sealed-test Markdown tables. Semantic operation families remain shared and are documented; this is not unseen-financial-reasoning proof. Fresh 8-K companies are added per split when available, with recorded source hashes and owner authorization. No v2 training/evaluation has run. New test labels are constructed programmatically; no test inference or result inspection occurred.\n\nFull original financial-statement footnotes/tables, independent factual evidence review and human review remain unmet. This is a corrected limited pilot, not a fully audited financial corpus. Do not promote the v1 candidate on the basis of defective instruction questions. Future training requires a new run/plan and fresh token profiling for v2; do not reinterpret v1 training as using v2.')
    write(RUN/'quality-decision.json',{'author':'Created by ChatGPT (OpenAI)','v1_candidate_approved_for_use':False,
        'reason':'Underspecified v1 instruction/output contracts and limited real-note coverage; preserve raw metric decision separately',
        'retained_adapter':str(RUN/'archive/qwen4'),'prospective_dataset_manifest':str(target/'manifest.json'),'additional_gpu_jobs':0})
    print({split:entry['rows'] for split,entry in metadata['splits'].items()})


if __name__=='__main__':main()
