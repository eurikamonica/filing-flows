"""Read operation evidence and produce an honest release report. Created by ChatGPT (OpenAI)."""
from pathlib import Path
from lab import LAB,BETA,AUTHOR,read,write,sha


def main():
    first=Path(read(LAB/'current-operation.json')['run'])
    bf16=Path(read(LAB/'current-merge-retry.json')['run'])
    fp16=Path(read(LAB/'current-merge-fp16.json')['run'])
    records={}
    for name,run in [('initial_dispatch',first),('cpu_bfloat16',bf16),('cpu_float16',fp16)]:
        file=run/'merge-status.json'
        records[name]=read(file) if file.exists() else {'status':'not_started'}
    result=records['cpu_float16']
    import psutil
    merge_still_alive=any((p.info['name'] or '').lower().startswith('python') and 'release_ops.py' in ' '.join(p.info['cmdline'] or [])
        and str(fp16) in ' '.join(p.info['cmdline'] or []) for p in psutil.process_iter(['name','cmdline']))
    if not merge_still_alive and result['status'] in ('passed_smoke','failed') and result.get('output'):
        source=Path(result['output']).resolve()
        target=fp16/'qwen4-merged-float16'
        # Normalize a legacy worker folder name only after the owned process has produced final status.
        if source.exists() and source.name=='qwen4-merged-bf16':
            assert source.is_relative_to(fp16.resolve()) and target.parent.resolve()==fp16.resolve() and not target.exists()
            source.rename(target);result['output']=str(target)
        elif source.exists():target=source
        if target.exists():
            license_file=BETA/'.runtime/model-sources/qwen3-4b/LICENSE'
            if license_file.exists():
                import shutil
                shutil.copy2(license_file,target/'LICENSE')
            (target/'README.md').write_text('# Qwen3-4B merged FP16 research export\n\n'+AUTHOR+'.\n\nBase: Qwen/Qwen3-4B by the Qwen team, revision '+result['base_revision']+'. The base remains 4B; the local financial adapter is merged once into its own base.\n\nStatus: '+result['status']+'. This records a two-prompt CPU FP16 packaging smoke only, not full production validation or NF4 re-quantization acceptance. Base license is retained in LICENSE.\n',encoding='utf-8')
            result['files_sha256']={p.name:sha(p) for p in target.iterdir() if p.is_file()}
            write(fp16/'merge-status.json',result)
    download=read(first/'download-status.json') if (first/'download-status.json').exists() else {'status':'not_started'}
    integrity=read(first/'8b-integrity.json') if (first/'8b-integrity.json').exists() else None
    lines=['# Model export, 8B download and production status','',AUTHOR+'.','',
        '## Actual operations','', '| Attempt | Status | Maximum logit errors |', '| --- | --- | --- |']
    for name,record in records.items():lines.append('| '+name+' | '+record['status']+' | '+str(record.get('max_logit_abs_errors','not measured'))+' |')
    lines+=['','Initial attempt failed with meta tensors after PEFT default redispatch. It is retained as failed. CPU BF16 output texts matched but errors 0.625/0.4375 exceeded the predeclared 0.125 threshold. No threshold was relaxed. A separate CPU float16 comparison uses the same threshold and exact generated-text criterion. Parameter devices are checked and CUDA visibility is disabled for the corrected CPU workers.','',
        'FP16 export: `'+str(result.get('output','not available'))+'`. Raw before/after outputs, pinned base revision, adapter checksum and all export checksums are in its merge-status.json. Two-prompt equivalence is a packaging check; separate development and re-quantization checks remain necessary before model-service deployment.','',
        '## Qwen3-8B download','', 'Status: '+download['status'], 'Revision: `'+str(download.get('revision','not pinned'))+'`.',
        'Expected safetensors bytes: '+str(download.get('expected_safetensors_bytes','unknown'))+'.',
        'Local source: `'+str(download.get('destination','not allocated'))+'`.',
        'License metadata: '+str(download.get('license','not verified'))+'. No 8B inference, training, or 4B-adapter loading into 8B was attempted.','',
        'Pinned official LFS SHA256 verification: '+str(integrity.get('all_passed') if integrity else 'not yet checked')+'.','',
        '## Website and production inference','',
        'The user requested publication and production inference changes. Repository discovery found eurikamonica/filing-flows with write access; README describes static GitHub Pages/Actions deployment and rule-based core analysis, plus an optional self-hosted static mirror. This is a candidate production repository, not a confirmed backend target. No existing remote GPU model endpoint has been provided or verified.','',
        'Missing target information was requested: confirm the production repository/deployment route and specify whether inference runs on Windows, an existing remote backend or in browsers. No additional authorization is being requested; the missing infrastructure details prevent a concrete working deployment. No remote files, branches, workflows, databases, secrets or production inference settings have been changed. No main-branch merge has occurred. No workflow with email/social-post side effects was triggered.','',
        'Prepared artifacts remain entirely in this Beta. No CPU equivalence or raw 8B download is represented as production correctness.']
    (LAB/'RELEASE_STATUS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(first/'operation-summary.json',{'author':AUTHOR,'merge_attempts':records,'download':download,'download_integrity':integrity,
        'production_status':'waiting_for_repository_confirmation_and_inference_backend_details','remote_mutations':False})
    print('FP16',result['status'],'8B',download['status'])


if __name__=='__main__':main()
