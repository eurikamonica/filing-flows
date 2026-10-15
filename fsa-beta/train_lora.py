"""Optional Qwen3 LoRA trainer. Created by ChatGPT (OpenAI).
Requires separate ML dependencies; never invoked by the Beta server.
"""
import argparse
import json
from pathlib import Path
from training import read_dataset


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--model',choices=['Qwen/Qwen3-0.6B','Qwen/Qwen3-1.7B'],default='Qwen/Qwen3-0.6B')
    ap.add_argument('--epochs',type=int,default=1);ap.add_argument('--max-length',type=int,default=512)
    a=ap.parse_args();rows=read_dataset(a.data)
    out=Path(a.out)
    if out.exists():raise SystemExit('Use a new output directory')
    import torch
    from datasets import Dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments, DataCollatorForSeq2Seq
    from peft import LoraConfig, get_peft_model
    tokenizer=AutoTokenizer.from_pretrained(a.model)
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    model=AutoModelForCausalLM.from_pretrained(a.model,torch_dtype=torch.float32)
    model=get_peft_model(model,LoraConfig(task_type='CAUSAL_LM',r=8,lora_alpha=16,lora_dropout=0.05,target_modules=['q_proj','v_proj']))
    def encode(row):
        prompt=tokenizer.apply_chat_template([{'role':'user','content':row['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        p=tokenizer.encode(prompt,add_special_tokens=False)
        ans=tokenizer.encode(row['output'],add_special_tokens=False)+[tokenizer.eos_token_id]
        if len(p)+len(ans)>a.max_length:raise ValueError('Example exceeds max length; shorten context rather than truncate the answer')
        return {'input_ids':p+ans,'attention_mask':[1]*(len(p)+len(ans)),'labels':[-100]*len(p)+ans}
    datasets={s:Dataset.from_list([encode(r) for r in rows if r['split']==s]) for s in ('train','validation')}
    args=TrainingArguments(output_dir=str(out),num_train_epochs=a.epochs,per_device_train_batch_size=1,
         per_device_eval_batch_size=1,gradient_accumulation_steps=8,learning_rate=2e-4,
         eval_strategy='epoch',save_strategy='epoch',logging_steps=10,report_to=[],seed=42,
         dataloader_pin_memory=torch.cuda.is_available(),remove_unused_columns=False)
    trainer=Trainer(model=model,args=args,train_dataset=datasets['train'],eval_dataset=datasets['validation'],
                    data_collator=DataCollatorForSeq2Seq(tokenizer,padding=True,label_pad_token_id=-100))
    trainer.train();model.save_pretrained(out);tokenizer.save_pretrained(out)
    (out/'fsa_manifest.json').write_text(json.dumps({'author':'ChatGPT (OpenAI)','base_model':a.model,
        'dataset':str(Path(a.data).resolve()),'training':'LoRA SFT, not Gemini distillation',
        'warning':'Validation loss is not financial accuracy; run evaluate_lora.py on held-out companies.'},indent=2))

if __name__=='__main__':main()
