"""Qwen3 LoRA/QLoRA trainer. Created by ChatGPT (OpenAI)."""
import argparse
import json
import hashlib
import math
import traceback
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from training import read_dataset
from ml_runtime import load_options, memory_stats
from model_sources import model_source
from run_control import stop_reason, write_json, gpu_status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--model', choices=['Qwen/Qwen3-0.6B', 'Qwen/Qwen3-1.7B', 'HuggingFaceTB/SmolLM2-1.7B-Instruct', 'Qwen/Qwen2.5-Math-1.5B-Instruct', 'Qwen/Qwen3-4B'], default='Qwen/Qwen3-0.6B')
    ap.add_argument('--epochs', type=int, default=1)
    ap.add_argument('--max-length', type=int, default=512)
    ap.add_argument('--max-steps', type=int, default=-1)
    ap.add_argument('--gradient-accumulation-steps', type=int, default=8)
    ap.add_argument('--gradient-checkpointing', action='store_true')
    ap.add_argument('--qlora', action='store_true')
    ap.add_argument('--batch-size', type=int, default=1)
    ap.add_argument('--learning-rate', type=float, default=2e-4)
    ap.add_argument('--lora-rank', type=int, default=8)
    ap.add_argument('--target-modules', choices=['qv', 'all-linear'], default='qv')
    ap.add_argument('--eval-steps', type=int, default=100)
    ap.add_argument('--save-steps', type=int, default=0)
    ap.add_argument('--logging-steps', type=int, default=1)
    ap.add_argument('--validation-limit', type=int, default=0)
    ap.add_argument('--resume-from-checkpoint')
    ap.add_argument('--init-adapter', help='Warm-start trainable adapter; uses a fresh optimizer and output directory')
    ap.add_argument('--deadline-utc')
    ap.add_argument('--stop-file')
    ap.add_argument('--temperature-limit', type=float)
    ap.add_argument('--min-free-gib', type=float, default=12)
    ap.add_argument('--compute-dtype', choices=['float16', 'bfloat16'], default='float16')
    ap.add_argument('--pause-at-step', type=int, default=0)
    a = ap.parse_args()
    if a.batch_size <= 0 or a.lora_rank <= 0 or a.learning_rate <= 0 or a.eval_steps <= 0 or a.logging_steps <= 0 or a.save_steps < 0 or a.validation_limit < 0:
        ap.error('Invalid training configuration')
    if a.save_steps and a.save_steps % a.eval_steps:
        ap.error('--save-steps must be a multiple of --eval-steps')
    if a.max_steps != -1 and a.max_steps <= 0:
        ap.error('--max-steps must be positive or -1')
    if a.max_length <= 0 or a.gradient_accumulation_steps <= 0 or a.epochs <= 0:
        ap.error('Length, accumulation and epochs must be positive')
    if a.init_adapter and a.resume_from_checkpoint:
        ap.error('Choose adapter warm-start or full checkpoint resume, not both')
    rows = read_dataset(a.data)
    out = Path(a.out)
    if out.exists() and not a.resume_from_checkpoint:
        raise SystemExit('Use a new output directory or an explicit checkpoint to resume')
    if a.resume_from_checkpoint:
        checkpoint = Path(a.resume_from_checkpoint).resolve()
        if not checkpoint.is_relative_to(out.resolve()) or not (checkpoint / 'trainer_state.json').exists():
            raise SystemExit('Resume checkpoint must be a Trainer checkpoint inside the output directory')
    out.mkdir(parents=True, exist_ok=bool(a.resume_from_checkpoint))
    status = {'author': 'Created by ChatGPT (OpenAI)', 'status': 'started', 'config': vars(a),
              'dataset_sha256': hashlib.sha256(Path(a.data).read_bytes()).hexdigest()}
    write_json(out / 'fsa_manifest.json', status)
    torch = None
    trainer = None
    try:
        import torch
        torch.set_num_threads(4)
        from datasets import Dataset
        from transformers import (AutoTokenizer, AutoModelForCausalLM, Trainer,
                                  TrainerCallback, TrainingArguments, DataCollatorForSeq2Seq)
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        status['environment'] = {'torch': torch.__version__, 'cuda_runtime': torch.version.cuda}
        options = load_options(torch, a.qlora, a.compute_dtype)
        initial = None
        if a.init_adapter:
            initial_path = Path(a.init_adapter).resolve()
            if not initial_path.is_relative_to(Path(__file__).resolve().parent):
                raise ValueError('Initial adapter must stay in this Beta')
            initial = json.loads((initial_path/'fsa_manifest.json').read_text(encoding='utf-8'))
            if initial['status'] != 'completed' or initial['config']['model'] != a.model:
                raise ValueError('Initial adapter must be completed and use the same base model')
            options['revision'] = initial['base_revision']
            status['initial_adapter_sha256'] = hashlib.sha256((initial_path/'adapter_model.safetensors').read_bytes()).hexdigest()
            status['initial_best_checkpoint'] = initial.get('best_checkpoint')
            status['continuation'] = 'Adapter warm-start; fresh optimizer and learning-rate schedule'
        source, source_revision = model_source(a.model, options.get('revision'))
        tokenizer = AutoTokenizer.from_pretrained(source)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(source, **options)
        status['base_revision'] = getattr(model.config, '_commit_hash', None) or source_revision
        if a.qlora:
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=a.gradient_checkpointing,
                gradient_checkpointing_kwargs={'use_reentrant': False})
        model.config.use_cache = False
        if initial is not None:
            model = PeftModel.from_pretrained(model, str(initial_path), is_trainable=True)
            if model.peft_config['default'].r != a.lora_rank:
                raise ValueError('Requested rank must match initial adapter rank')
        else:
            model = get_peft_model(model, LoraConfig(task_type='CAUSAL_LM', r=a.lora_rank,
                lora_alpha=2*a.lora_rank, lora_dropout=0.05,
                target_modules='all-linear' if a.target_modules == 'all-linear' else ['q_proj', 'v_proj']))
        model.print_trainable_parameters()
        status['trainable_parameters'], status['total_parameters'] = model.get_nb_trainable_parameters()
        def encode(row):
            prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': row['input']}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
            p = tokenizer.encode(prompt, add_special_tokens=False)
            ans = tokenizer.encode(row['output'], add_special_tokens=False) + [tokenizer.eos_token_id]
            if len(p) + len(ans) > a.max_length:
                raise ValueError('Example exceeds max length; shorten context rather than truncate the answer')
            return {'input_ids': p + ans, 'attention_mask': [1] * (len(p) + len(ans)), 'labels': [-100] * len(p) + ans}
        datasets = {s: Dataset.from_list([encode(r) for r in rows if r['split'] == s]) for s in ('train', 'validation')}
        if a.validation_limit:
            datasets['validation'] = datasets['validation'].select(range(min(a.validation_limit, len(datasets['validation']))))
        status['split_rows'] = {s: len(ds) for s, ds in datasets.items()}
        class MemoryCallback(TrainerCallback):
            reason = None
            last_step_time = None
            active_seconds = 0
            def on_train_begin(self, args, state, control, **kwargs):
                self.last_step_time = time.monotonic()
                status['resumed_global_step'] = state.global_step
            def on_step_begin(self, args, state, control, **kwargs):
                self.last_step_time = time.monotonic()
            def on_step_end(self, args, state, control, **kwargs):
                self.active_seconds += time.monotonic() - self.last_step_time
                if state.global_step % 5 == 0:
                    self.reason = stop_reason(a.deadline_utc, a.stop_file, a.temperature_limit, a.min_free_gib, out.resolve())
                    if a.pause_at_step and state.global_step >= a.pause_at_step:
                        self.reason = self.reason or 'resume_verification'
                    if self.reason:
                        status['stop_reason'] = self.reason
                        control.should_save = True
                        control.should_training_stop = True
                return control
            def on_log(self, args, state, control, logs=None, **kwargs):
                import psutil
                status['active_optimizer_seconds'] = self.active_seconds
                status['process_rss_mib'] = psutil.Process().memory_info().rss / 2**20
                status['useful_nonpadding_tokens_per_second'] = status.get('consumed_nonpadding_tokens', 0) / max(self.active_seconds, 1e-9)
                if logs and 'grad_norm' in logs and not math.isfinite(float(logs['grad_norm'])):
                    raise RuntimeError('Nonfinite gradient norm; candidate rejected rather than counting skipped updates')
                with (out / 'memory.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'step': state.global_step, 'logs': logs,
                        'rss_mib': status['process_rss_mib'], 'active_optimizer_seconds': self.active_seconds,
                        'physical_gpu': gpu_status(), 'useful_nonpadding_tokens_per_second': status['useful_nonpadding_tokens_per_second'],
                        **memory_stats(torch)}) + '\n')
                (out / 'progress.json').write_text(json.dumps({'status': 'training', 'step': state.global_step,
                    'max_steps': args.max_steps, 'logs': logs, 'memory': memory_stats(torch)}, indent=2), encoding='utf-8')
            def on_save(self, args, state, control, **kwargs):
                card = out / f'checkpoint-{state.global_step}' / 'README.md'
                with card.open('a', encoding='utf-8') as f:
                    f.write('\nCreated by ChatGPT (OpenAI).\n')
        args = TrainingArguments(output_dir=str(out), num_train_epochs=a.epochs,
            max_steps=a.max_steps, per_device_train_batch_size=a.batch_size, per_device_eval_batch_size=a.batch_size,
            gradient_accumulation_steps=a.gradient_accumulation_steps, learning_rate=a.learning_rate,
            warmup_ratio=0.03,
            gradient_checkpointing=a.gradient_checkpointing,
            gradient_checkpointing_kwargs={'use_reentrant': False}, fp16=a.qlora and a.compute_dtype == 'float16',
            bf16=a.qlora and a.compute_dtype == 'bfloat16',
            optim='adamw_torch', eval_strategy='steps' if a.save_steps else 'epoch',
            eval_steps=a.eval_steps, save_strategy='steps' if a.save_steps else 'no',
            save_steps=a.save_steps or 500, save_total_limit=2,
            load_best_model_at_end=bool(a.save_steps), metric_for_best_model='eval_loss', greater_is_better=False,
            logging_steps=a.logging_steps, report_to=[], seed=42, dataloader_num_workers=0,
            dataloader_pin_memory=torch.cuda.is_available(), remove_unused_columns=False)
        memory_callback = MemoryCallback()
        status['useful_tokens_per_training_epoch'] = sum(sum(encoded['attention_mask']) for encoded in datasets['train'])
        status['supervised_tokens_per_training_epoch'] = sum(sum(label != -100 for label in encoded['labels']) for encoded in datasets['train'])
        class MeasuredTrainer(Trainer):
            def training_step(self, model, inputs, *step_args, **step_kwargs):
                status['consumed_nonpadding_tokens'] = status.get('consumed_nonpadding_tokens', 0) + int(inputs['attention_mask'].sum())
                status['consumed_supervised_tokens'] = status.get('consumed_supervised_tokens', 0) + int((inputs['labels'] != -100).sum())
                return super().training_step(model, inputs, *step_args, **step_kwargs)
        trainer = MeasuredTrainer(model=model, args=args, train_dataset=datasets['train'],
            eval_dataset=datasets['validation'], callbacks=[memory_callback],
            data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100))
        result = trainer.train(resume_from_checkpoint=a.resume_from_checkpoint)
        if not math.isfinite(result.metrics.get('train_loss', float('nan'))):
            raise RuntimeError('Training produced a nonfinite loss')
        if a.max_steps > 0 and trainer.state.global_step != a.max_steps and not memory_callback.reason:
            raise RuntimeError('Training did not reach the requested optimizer step count')
        model.save_pretrained(out)
        tokenizer.save_pretrained(out)
        card = out / 'README.md'
        with card.open('a', encoding='utf-8') as f:
            f.write('\nCreated by ChatGPT (OpenAI).\n')
        status['log_history'] = trainer.state.log_history
        status['best_checkpoint'] = trainer.state.best_model_checkpoint
        status['best_validation_loss'] = trainer.state.best_metric
        status.update(status='paused' if memory_callback.reason and trainer.state.global_step < trainer.state.max_steps else 'completed', global_step=trainer.state.global_step, metrics=result.metrics,
            training='QLoRA SFT' if a.qlora else 'FP32 LoRA SFT',
            warning='Synthetic pipeline smoke test only; no claim of financial accuracy or improvement.')
    except BaseException as exc:
        status.update(status='failed', error=repr(exc), traceback=traceback.format_exc(),
                      global_step=trainer.state.global_step if trainer else 0)
        raise
    finally:
        if torch is not None:
            status['memory'] = memory_stats(torch)
        write_json(out / 'fsa_manifest.json', status)
        print(json.dumps(status, indent=2), flush=True)


if __name__ == '__main__':
    main()
