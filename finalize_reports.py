"""Finalize executed results without launching GPU work. Created by ChatGPT (OpenAI)."""
from collections import Counter
from pathlib import Path
import json
from protocol import RUN, LAB, BETA, read, write, doc, sha
from overnight_worker import equal


def metrics(result):
    records=result['details']; cited=[r for r in records if 'source_id' in r['expected']]
    citations=content=numeric_correct=numeric_rows=field_correct=field_rows=0
    for row in records:
        arithmetic=row['task'].startswith('Compute ')
        field=row['task']=='field_extraction'
        numeric_rows+=arithmetic
        field_rows+=field
        try:
            answer=json.loads(row['output'])
            valid=row['valid_json'] and isinstance(answer,dict)
            correct=valid and (equal(answer.get('value'),row['expected'].get('value'),True) if arithmetic else
                equal(answer,{k:v for k,v in row['expected'].items() if k!='source_id'}))
            content+=correct
            numeric_correct+=bool(arithmetic and correct)
            field_correct+=bool(field and correct)
            if 'source_id' in row['expected']:
                citations+=valid and answer.get('source_id')==row['expected']['source_id']
        except (ValueError,TypeError):pass
    return {'rows':len(records),'json_pass':sum(r['valid_json'] for r in records),
        'joint_correct':sum(r['correct'] for r in records),'source_id_correct':citations,'source_id_eligible':len(cited),
        'content_correct_excluding_source_id':content,'numeric_correct':numeric_correct,'numeric_rows':numeric_rows,
        'literal_field_correct':field_correct,'literal_field_rows':field_rows,
        'actual_evidence_support':'not independently verified','evaluation_seconds_excluding_load':result.get('seconds')}


def main():
    inventory=read(RUN/'archive/inventory.json')
    historic={}
    for slug,entry in inventory.items():
        historic[slug]={}
        for filename in Path(entry['archive']).glob('*validation.json'):
            result=read(filename)
            if result['status']=='completed':historic[slug][filename.name]=metrics(result)
        for filename in Path(entry['archive']).glob('*champion-test.json'):
            historic[slug][filename.name]={'status':read(filename)['status'],**metrics(read(filename))}
    write(RUN/'historical-metrics.json',historic)
    path=RUN/'BASELINE_AND_ERROR_REPORT.md'
    text=path.read_text(encoding='utf-8').split('\n## Reconciled metrics')[0]
    text+='\n## Reconciled metrics\n\nExact denominators, JSON pass, joint correctness, source-ID reproduction and measured evaluation latency for every preserved completed validation artifact are in historical-metrics.json. Evidence entailment is not independently verified. Baselines and adapters are comparable within each recorded model/task/decoding setup; cross-model precision and Math task differences remain explicit. No missing baseline was inferred from zero interface scores.\n'
    if (RUN/'baseline.json').exists():
        result=read(RUN/'baseline.json');text+='\nNew fixed development baseline status: '+result['status']+'; saved raw questions: '+str(len(result['details']))+'. This uses NF4/BF16 and therefore is not a re-run of the old FP16 small-model experiment.\n'
    path.write_text(text,encoding='utf-8')
    counts=read(RUN/'parameter-counts.json')
    doc(RUN,'PARAMETER_SCALING_REPORT.md','Executed CPU/meta inspection of pinned Qwen3-4B configuration:\n\n```json\n'+json.dumps(counts,indent=2)+'\n```\n\nNo independent-layer expansion, 8B download, or larger-base training executed. Base parameters are unique logical elements (tied embeddings counted once); rank-8 q/v adds 2,949,120 trainable elements. Packed 4-bit byte storage is a different quantity. A continued or merged adapter remains a 4B-based model. Inference memory and training memory must be profiled separately; the original overnight record includes Windows reported reserved memory above physical VRAM, so it does not establish spare GPU capacity.\n\nFuture options remain separate: pretrained Qwen3-8B with a fresh adapter, or a small independently copied layer pilot. Neither is authorized as an automatic sweep here. Official references: https://huggingface.co/Qwen/Qwen3-8B and https://huggingface.co/docs/peft/package_reference/lora . No paid service or deployment.')
    dataset=read(RUN/'data/manifest.json'); tokens=read(RUN/'data/token-audit.json')
    path=RUN/'DATASET_CARD.md';text=path.read_text(encoding='utf-8').split('\n## Frozen counts')[0]
    text+='\n## Frozen counts\n\n| Split | Rows | Companies | SHA256 |\n| --- | --- | --- | --- |\n'
    for split,entry in dataset['splits'].items():text+=f"| {split} | {entry['rows']} | {len(entry['companies'])} | {entry['sha256']} |\n"
    text+='\n512-token pilot retains '+str(tokens['train']['kept'])+' train rows, excludes '+str(len(tokens['train']['excluded']))+' complete oversized excerpt-heading samples without truncation, and uses 30 fixed new development plus 18 historical validation regression questions. All 218 new dev rows remain available; their larger denominator must not be confused with this 48-question pilot. The excluded passages are retained in the source corpus; 1024-context coverage is deferred rather than claiming full-note support.\n'
    text+='\nCoverage limits: the fresh selected website documents include 10-K and 10-Q but no 8-K. Item/Note tables, amended periods and reserve interpretation in this pilot are hypothetical fixtures rather than issuer originals. Generator structure is shared even though company/document membership and split-scoped template identifiers are disjoint; template IDs alone do not establish generator-family isolation. Full original-footnote and unseen-template acceptance remains unmet. Gate 1 completion refers to this bounded, explicitly limited data pilot, not satisfaction of all rich-corpus goals. No data were changed in response to baseline answers.\n'
    text+='\nProvenance erratum: this frozen version uses source_kind=hypothetical_fixture as a fallback for derived website missing-field/abstention rows. Their label_kind=derived, source_url, source_sha256 and supplied evidence correctly identify their website origin; label_kind is authoritative. This metadata-only generator bug was corrected for future runs without changing any frozen bytes or model inputs/answers in the current run. Document IDs identify website snapshot/period offsets, not SEC accession/page locations.\n'
    retrieval=read(RUN/'retrieval-baseline.json')
    text+='\nCPU literal retrieval baseline: '+str(retrieval['correct'])+'/'+str(retrieval['rows'])+' correct overall, with unsupported task types explicitly abstained. This is 42 literal-extraction answers out of 218 development questions, not a neural or full-document retrieval score.\n'
    path.write_text(text,encoding='utf-8')
    execution=read(RUN/'execution.json') if (RUN/'execution.json').exists() else {'status':'running'}
    selection=read(RUN/'selection.json') if (RUN/'selection.json').exists() else None
    quality=read(RUN/'quality-decision.json') if (RUN/'quality-decision.json').exists() else None
    if quality:
        path=RUN/'DATASET_CARD.md'
        text=path.read_text(encoding='utf-8')
        v2=read(RUN/'data-v2/manifest.json')
        text+='\n## Prospective corrected v2 (not used in this training)\n\nExplicit output contracts and provenance metadata corrected. Evidence rendering families are split-separated; common semantic operations remain shared. Added one previously unused 8-K company per split. Counts: '+json.dumps({s:e['rows'] for s,e in v2['splits'].items()})+'. Exact membership/hashes: data-v2/manifest.json. V2 test has not been scored. No v2 model exists. See DATA_QUALITY_REVIEW.md. Full real-footnote/table and human-reviewed data goals remain unmet.\n'
        path.write_text(text,encoding='utf-8')
    training=[]
    for path in (RUN/'outputs').glob('*/fsa_manifest.json'):
        result=read(path)
        training.append({'run':path.parent.name,**{key:result.get(key) for key in ['status','global_step','resumed_global_step','stop_reason','error',
            'memory','active_optimizer_seconds','process_rss_mib','useful_tokens_per_training_epoch','supervised_tokens_per_training_epoch',
            'consumed_nonpadding_tokens','consumed_supervised_tokens','useful_nonpadding_tokens_per_second']}})
    phases=[]
    for path in (RUN/'logs').glob('*.log'):
        raw=path.read_text(encoding='utf-8',errors='replace')
        offset=raw.rfind('\n{\n')
        if offset>=0:
            try:
                record,_=json.JSONDecoder().raw_decode(raw[offset:].lstrip())
                if 'global_step' in record and 'config' in record:
                    write(RUN/'phase-manifests'/(path.stem+'.json'),record)
                    phases.append({'phase':path.stem,'global_step':record['global_step'],'status':record['status'],
                        'stop_reason':record.get('stop_reason'),'consumed_nonpadding_tokens':record.get('consumed_nonpadding_tokens'),
                        'active_optimizer_seconds':record.get('active_optimizer_seconds'),
                        'useful_nonpadding_tokens_per_second':record.get('useful_nonpadding_tokens_per_second')})
            except (ValueError,TypeError):pass
    write(RUN/'executed-training-summary.json',training)
    write(RUN/'phase-summary.json',phases)
    resource_samples=[]
    for file in (RUN/'outputs').glob('*/memory.jsonl'):
        resource_samples += [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
    if resource_samples:
        write(RUN/'sampled-resource-peaks.json',{'author':'Created by ChatGPT (OpenAI)',
            'scope':'Sampled log peaks, not continuous OEM telemetry or whole-system RAM peaks',
            'rss_mib':max(r.get('rss_mib',0) for r in resource_samples),
            'gpu_temperature_c':max(r.get('physical_gpu',{}).get('temperature_c',0) for r in resource_samples),
            'physical_gpu_used_mib':max(r.get('physical_gpu',{}).get('used_mib',0) for r in resource_samples)})
    doc(RUN,'MODEL_CARD.md','Base: Qwen/Qwen3-4B, revision '+read(RUN/'plan.json')['revision']+'.\n\nExecution: '+json.dumps(execution)+'.\n\nSelection: '+json.dumps(selection)+'.\n\nTraining artifacts: executed-training-summary.json; raw logs and fsa_manifest.json are authoritative. No new final-test result exists: sealed test remains unopened for evaluation. Tasks use owner-authorized website evidence and rule-checked hypothetical financial fixtures; no human financial review, complete footnote understanding or independently established citation entailment is claimed. No base-size expansion, merge, publication, deployment or production inference change.')
    manifest=read(RUN/'manifest.json');manifest.update(gate2=execution,selection=selection,
        reports={p.name:sha(p) for p in RUN.glob('*.md')},code_sha256={p.name:sha(p) for p in LAB.glob('*.py')},
        executed_training=training,sealed_test_sha256_verified=sha(dataset['splits']['sealed_test']['path'])==dataset['splits']['sealed_test']['sha256'])
    manifest['hash_scope']='Artifact bytes at this finalization; current source hashes include documented metadata/budget guard corrections'
    manifest['output_artifacts']={str(path.relative_to(RUN)):sha(path) for path in (RUN/'outputs').rglob('*') if path.is_file()}
    manifest['raw_result_artifacts']={name:sha(RUN/name) for name in ['baseline.json','candidate.json','selection.json','execution.json','plan.json','parameter-counts.json'] if (RUN/name).exists()}
    manifest['lineage']={'base_revision':read(RUN/'plan.json')['revision'],
        'starting_adapter_sha256':sha(RUN/'archive/qwen4/adapter_model.safetensors'),
        'continued_adapter_sha256':sha(RUN/'outputs/first-epoch/adapter_model.safetensors') if (RUN/'outputs/first-epoch/adapter_model.safetensors').exists() else None,
        'main_optimizer':'fresh; smoke is not the parent of the main run'}
    card=RUN/'MODEL_CARD.md'
    card.write_text(card.read_text(encoding='utf-8')+'\n## Exact local lineage\n\n```json\n'+json.dumps(manifest['lineage'],indent=2)+'\n```\n',encoding='utf-8')
    if quality:
        card.write_text(card.read_text(encoding='utf-8')+'\n## Data-quality veto\n\nThe mechanical predeclared score gate passed, but this is not use approval. The v1 instruction contract defects invalidate a reliability claim. The candidate is an experimental artifact; retain the original champion and do not promote it. quality-decision.json is authoritative for this use decision; original selection.json is preserved unchanged.\n',encoding='utf-8')
        manifest.update(quality_decision=quality,prospective_dataset=read(RUN/'data-v2/manifest.json'))
    if selection:
        before,after=read(RUN/'baseline.json'),read(RUN/'candidate.json')
        report=RUN/'EVALUATION_REPORT.md'
        text=report.read_text(encoding='utf-8').split('\n## Detailed development counts')[0]
        text+='\n## Detailed development counts\n\nThe new pilot has 30 questions (3/task); historical validation regression has 18 (2/task). Combined macro is the mean of 19 task accuracies, not the 48-question micro accuracy. Neither is the 108-question historical test score.\n\n| Task | Starting correct/rows | Continued correct/rows |\n| --- | --- | --- |\n'
        for task,group in before['tasks'].items():
            text+=f"| {task} | {group['correct']}/{group['rows']} | {after['tasks'][task]['correct']}/{after['tasks'][task]['rows']} |\n"
        text+='\nSource-ID denominators: baseline '+str(before['source_id_eligible'])+', candidate '+str(after['source_id_eligible'])+'. Content excludes source_id; JSON failures still count as wrong. Actual issuer-evidence entailment is not independently scored.\n'
        if quality:
            text+='\n## Data quality overrides use approval\n\nRaw selection.json records the original metric gate pass and is not edited. Subsequent semantic review found an underspecified basic_instruction contract (and implicit output keys in other families). These v1 numbers are engineering diagnostics, not a clean capability-improvement benchmark. quality-decision.json rejects candidate promotion and retains the starting champion. Corrected data-v2 is prospective and has never been trained/evaluated; neither v1 nor v2 sealed test was scored. The full original-note/human-review Gate 1 objective remains unmet. See DATA_QUALITY_REVIEW.md. No extra GPU run was launched to obtain a preferred result.\n'
        text+='\n## Resource measurements\n\nTraining phase summaries with actual token counts, optimizer-active time and throughput are in phase-summary.json; per-step temperature/physical GPU readings and RSS are in outputs/*/memory.jsonl. Job wall times are in jobs.jsonl. Wall time minus optimizer-active time includes model loading, CPU packing, validation, save and teardown; these components were not individually timed. No explicit cooling/retry loop ran.\n\n```json\n'+json.dumps(training,indent=2)+'\n```\n'
        text+='\nThe smoke test consists of 10 initial updates plus 10 resumed updates (global_step 20). It is not 10+20 new updates. The main run has 60 fresh updates and is initialized from the archived champion rather than the smoke weights. Sampled resource peaks are in sampled-resource-peaks.json.\n'
        text+='\nGate 3 merge/export and Gate 4 scaling were prepared/deferred, not executed. Gate 5 sealed testing is not part of this bounded Gate 2 run. Next safe read-only command from Beta: `.\\.venv\\Scripts\\python.exe model-expansion-lab/status.py`. Re-running protocol.py execute against this completed run is not a supported continuation command; a future experiment needs a newly declared run/budget and appropriate compatible checkpoint.\n'
        if (RUN/'DEV_COMPARISON.png').exists():
            text+='\n## Measured development comparison\n\n![Fixed development comparison](DEV_COMPARISON.png)\n'
        report.write_text(text,encoding='utf-8')
    manifest['reports']={p.name:sha(p) for p in RUN.glob('*.md')}
    manifest['charts']={p.name:sha(p) for p in RUN.glob('DEV_COMPARISON.*')}
    write(RUN/'manifest.json',manifest)
    (LAB/'LATEST_RESULTS.md').write_text('# Current isolated experiment\n\nCreated by ChatGPT (OpenAI).\n\nRun: `'+RUN.name+'`\n\nGate 0: champions preserved and historical reports reconciled.\n\nGate 1: fresh-company splits and CPU retrieval baseline created; v1 contract defects documented and prospective v2 created. Real original-note/table and human-review goals remain unmet.\n\nGate 2: '+execution['status']+'. 20-step resume smoke and 60-step main completed. Mechanical development gate passed, but data-quality veto retains the old champion; candidate is not approved.\n\n[Evaluation report](runs/'+RUN.name+'/EVALUATION_REPORT.md) | [Audit](runs/'+RUN.name+'/AUDIT.md) | [Dataset card](runs/'+RUN.name+'/DATASET_CARD.md) | [Training plan](runs/'+RUN.name+'/TRAINING_PLAN.md) | [Model card](runs/'+RUN.name+'/MODEL_CARD.md).\n\nNo final test evaluation, merge, larger architecture, deployment or paid compute was run.\n',encoding='utf-8')
    print(json.dumps({'execution':execution,'training':training,'selection':selection},indent=2))


if __name__=='__main__':main()
