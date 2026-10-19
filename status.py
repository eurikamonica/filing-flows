"""Read-only local experiment status. Created by ChatGPT (OpenAI)."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import psutil
LAB=Path(__file__).resolve().parent


def main():
    run=Path(json.loads((LAB/'current-run.json').read_text(encoding='utf-8'))['run'])
    result={'author':'Created by ChatGPT (OpenAI)','observed_utc':datetime.now(timezone.utc).isoformat(),'run':str(run)}
    if (run/'execution.json').exists():result['execution']=json.loads((run/'execution.json').read_text(encoding='utf-8'))
    result['processes']=[p.info for p in psutil.process_iter(['pid','name','cmdline'])
        if (p.info['name'] or '').lower().startswith('python') and str(LAB) in ' '.join(p.info['cmdline'] or []) and 'status.py' not in ' '.join(p.info['cmdline'] or [])]
    result['evaluations']={}
    for name in ('baseline','candidate'):
        file=run/(name+'.json')
        if file.exists():
            data=json.loads(file.read_text(encoding='utf-8'));result['evaluations'][name]={'status':data['status'],
                'rows':len(data['details']),'updated_utc':datetime.fromtimestamp(file.stat().st_mtime,timezone.utc).isoformat()}
    result['training']={}
    for file in (run/'outputs').glob('*/progress.json'):
        data=json.loads(file.read_text(encoding='utf-8'));result['training'][file.parent.name]={'step':data['step'],'max_steps':data['max_steps']}
    gpu=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
    result['gpu']=gpu.stdout.strip() if not gpu.returncode else gpu.stderr.strip()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
