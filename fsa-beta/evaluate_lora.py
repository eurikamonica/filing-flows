"""Evaluate a local adapter against numeric held-out examples. ChatGPT (OpenAI)."""
import argparse
import json
import math
from pathlib import Path
from training import read_dataset


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--adapter',required=True);ap.add_argument('--data',required=True);a=ap.parse_args()
    import torch
    from transformers import AutoTokenizer
    from peft import AutoPeftModelForCausalLM
    tokenizer=AutoTokenizer.from_pretrained(a.adapter)
    model=AutoPeftModelForCausalLM.from_pretrained(a.adapter,torch_dtype=torch.float32)
    model.to('cuda' if torch.cuda.is_available() else 'cpu');model.eval()
    rows=[r for r in read_dataset(a.data) if r['split']=='test'];details=[]
    for row in rows:
        prompt=tokenizer.apply_chat_template([{'role':'user','content':row['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inputs=tokenizer(prompt,return_tensors='pt').to(model.device)
        with torch.no_grad():out=model.generate(**inputs,max_new_tokens=120,do_sample=False,pad_token_id=tokenizer.pad_token_id)
        text=tokenizer.decode(out[0,inputs['input_ids'].shape[1]:],skip_special_tokens=True)
        try:
            got=json.loads(text)['value'];expected=json.loads(row['output'])['value']
            ok=not isinstance(got,bool) and math.isclose(float(got),expected,rel_tol=1e-4,abs_tol=1e-6)
        except (ValueError,KeyError,TypeError):ok=False
        details.append({'company_id':row['company_id'],'correct':ok,'output':text})
    result={'author':'ChatGPT (OpenAI)','test_rows':len(details),'numeric_accuracy':sum(x['correct'] for x in details)/len(details),
            'scope':'Synthetic arithmetic only; not real-filing generalization','details':details}
    out=Path(a.adapter)/'evaluation.json';out.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='details'}))

if __name__=='__main__':main()
