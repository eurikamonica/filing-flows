"""Trainable local question router + deterministic FSA answers. ChatGPT (OpenAI).
This small Naive Bayes classifier is NOT a distilled language model.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
SEEDS={
 'reserves':['reserve release warranty provision','cookie jar earnings smoothing','allowance rollforward utilization','bad debt reserve additions','准备 转回 坏账 保修','储备罐 盈余管理'],
 'accruals':['net income operating cash flow accruals','earnings cash conversion','working capital cash quality','accrual ratio average assets','应计 利润 现金流','净利润 经营现金流 差异'],
 'reformulation':['operating financial assets liabilities','NOA NFO equity reformulation','RNOA operating return tax','NOPAT return invested operating assets','报表重构 经营 融资','经营资产 回报率 税率'],
 'fcf':['free cash flow capex','FCF capital expenditure','cash after investment','OCF less capex','自由现金流 资本支出','现金 投资 支出'],
}
HELDOUT=[('Explain the warranty reserve reversal','reserves'),('Is a cookie jar proven','reserves'),
 ('Why do earnings exceed cash flow','accruals'),('Calculate accrual ratio','accruals'),
 ('Reconcile NOA with financing and equity','reformulation'),('What is RNOA','reformulation'),
 ('Explain FCF after capex','fcf'),('How much free cash remains','fcf')]


def tokens(text):
    words=re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]',text.lower())
    return words


def train():
    counts={k:dict(Counter(t for s in v for t in tokens(s))) for k,v in SEEDS.items()}
    vocab=sorted({w for c in counts.values() for w in c})
    model={'author':'ChatGPT (OpenAI)','kind':'multinomial_naive_bayes_question_router',
           'data_origin':'independently authored seed phrases; no Gemini outputs','counts':counts,'vocabulary':vocab}
    predicted=[predict(q,model)['label'] for q,_ in HELDOUT]
    model['evaluation']={'heldout_examples':len(HELDOUT),'accuracy':sum(a==b for a,(_,b) in zip(predicted,HELDOUT))/len(HELDOUT),
                         'limit':'Tiny developer-authored smoke set; not a financial capability benchmark.'}
    return model


def predict(question,model):
    words=[t for t in tokens(question) if t in model['vocabulary']]
    if not words:return {'label':'unknown','confidence':0.0}
    scores={}
    for label,c in model['counts'].items():
        total=sum(c.values())+len(model['vocabulary'])
        scores[label]=sum(math.log((c.get(w,0)+1)/total) for w in words)
    mx=max(scores.values());weights={k:math.exp(v-mx) for k,v in scores.items()}
    best=max(weights,key=weights.get);conf=weights[best]/sum(weights.values())
    return {'label':best if conf>=0.38 else 'unknown','confidence':conf}


def answer(question,report):
    model=json.loads((ROOT/'models/router.json').read_text())
    route=predict(question,model)
    p=report['periods'][-1]
    mapping={'accruals':['accruals','accrual_ratio','cash_conversion'],
             'reformulation':['noa','nfo','nopat_estimate','rnoa','balance_residual'],'fcf':['fcf']}
    label=route['label']
    return {'author':'ChatGPT (OpenAI)','type':'local trained router + deterministic calculator',
            'route':route,'period':p['label'],'metrics':{k:p['metrics'][k] for k in mapping.get(label,[])},
            'reserves':p['reserves'] if label=='reserves' else [],
            'findings':p['findings'],
            'message':'Ask about reserves, accruals, NOA/RNOA or FCF.' if label=='unknown' else 'Amounts come from the validated report; the classifier selects a topic only.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--train',action='store_true');args=ap.parse_args()
    if args.train:
        model=train();(ROOT/'models').mkdir(exist_ok=True)
        (ROOT/'models/router.json').write_text(json.dumps(model,ensure_ascii=False,indent=2))
        print(json.dumps(model['evaluation']))
