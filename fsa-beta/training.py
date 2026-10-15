"""Independent, formula-checked FSA training corpus. ChatGPT (OpenAI).
No Gemini output is consumed. Synthetic cases test the training pipeline only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random


def generate(n=100,seed=81):
    rng=random.Random(seed);rows=[]
    for i in range(n):
        company=f'synthetic-entity-{i:04d}'
        split='test' if i%5==0 else 'validation' if i%5==1 else 'train'
        ni=rng.randint(-60,200);ocf=rng.randint(-90,230);capex=rng.randint(0,100)
        assets0=rng.randint(200,1000);assets1=rng.randint(200,1000)
        opening=rng.randint(20,80);add=rng.randint(0,30);release=rng.randint(0,10);use=rng.randint(0,10)
        examples=[
          ('Compute total accruals.',{'net_income':ni,'ocf':ocf},{'value':ni-ocf,'formula':'net_income - ocf'}),
          ('Compute free cash flow.',{'ocf':ocf,'capex':capex},{'value':ocf-capex,'formula':'ocf - capex'}),
          ('Compute the annual accrual ratio.',{'net_income':ni,'ocf':ocf,'opening_assets':assets0,'closing_assets':assets1},
           {'value':round((ni-ocf)/((assets0+assets1)/2),8),'formula':'(net_income - ocf) / ((opening_assets + closing_assets) / 2)'}),
          ('Compute the closing reserve; no other movements.',{'opening':opening,'additions':add,'releases':release,'utilization':use},
           {'value':opening+add-release-use,'formula':'opening + additions - releases - utilization'}),
        ]
        for question,context,target in examples:
            rows.append({'author':'ChatGPT (OpenAI)','origin':'rule_generated','review':'formula_verified','company_id':company,
                         'split':split,'input':question+' Return JSON with value and formula. Amounts use the same unit. '+json.dumps(context),
                         'output':json.dumps(target,sort_keys=True)})
    return rows


def read_dataset(path):
    rows=[json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]
    if not rows:raise ValueError('Dataset is empty')
    groups={};seen={}
    for row in rows:
        if row.get('origin') not in ('rule_generated','human_authored') or row.get('review') not in ('formula_verified','human_verified'):
            raise ValueError('Only reviewed independent examples accepted; Gemini output is not enabled for training')
        if not row.get('company_id') or row.get('split') not in ('train','validation','test'):
            raise ValueError('company_id and train/validation/test split required')
        if groups.setdefault(row['company_id'],row['split'])!=row['split']:
            raise ValueError('Company leakage across splits')
        if not isinstance(row.get('input'),str) or not isinstance(row.get('output'),str):raise ValueError('input/output strings required')
        digest=hashlib.sha256(row['input'].encode()).hexdigest()
        if digest in seen and seen[digest]!=row['split']:raise ValueError('Duplicate question/context across splits')
        seen[digest]=row['split']
    if set(r['split'] for r in rows)!={'train','validation','test'}:raise ValueError('All three splits required')
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(Path(__file__).parent/'.runtime/training.jsonl'));a=ap.parse_args()
    out=Path(a.out)
    if out.exists():raise SystemExit('Choose a fresh output path')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(json.dumps(r) for r in generate())+'\n',encoding='utf-8')
    rows=read_dataset(out);print(json.dumps({s:sum(r['split']==s for r in rows) for s in ('train','validation','test')}))
