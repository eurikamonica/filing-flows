"""Bounded Windows inference for the pinned Qwen3-8B. Created by ChatGPT (OpenAI)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from runtime_support import configure, write

SOURCE = Path(os.environ.get('FILING_FLOWS_MODEL_SOURCE', 'models/qwen3-8b'))
REVISION = 'b968826d9c46dd6066d109eabc6255188de91218'


def utc():
    return datetime.now(timezone.utc).isoformat()


def gpu():
    result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
    return dict(zip(('utilization_percent', 'used_mib', 'total_mib', 'temperature_c'),
                    map(int, result.stdout.strip().split(','))))


class LocalModel:
    def __init__(self, runtime, mode='offload', source=SOURCE):
        configure(runtime)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        expected = json.loads(Path(__file__).with_name('qwen3-8b-files.json').read_text(encoding='utf-8'))
        for name, signature in expected['files'].items():
            file = Path(source) / name
            digest = hashlib.sha256()
            with file.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != signature['sha256'] or file.stat().st_size != signature['bytes']:
                raise RuntimeError('Pinned source integrity check failed: ' + name)
        print('Pinned Qwen3-8B source checksums verified.', flush=True)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        self.torch = torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable; no automatic CPU fallback')
        snapshot = gpu()
        if snapshot['used_mib'] > 700:
            raise RuntimeError('GPU already in use: ' + str(snapshot))
        torch.cuda.reset_peak_memory_stats()
        torch.set_num_threads(6)
        started = time.monotonic()
        config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                   bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                   llm_int8_enable_fp32_cpu_offload=mode == 'offload')
        device_map = {'': 0} if mode == 'gpu' else {
            'model.embed_tokens': 'cpu', 'model.norm': 0, 'lm_head': 'cpu',
            **{'model.layers.' + str(i): 0 for i in range(36)}}
        self.tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            source, local_files_only=True, torch_dtype=torch.bfloat16, quantization_config=config,
            device_map=device_map, attn_implementation='sdpa').eval()
        self.load_seconds = time.monotonic() - started
        self.metadata = {'model': 'Qwen/Qwen3-8B', 'revision': REVISION, 'adapter': None,
                         'source_checksums_verified': True,
                         'quantization': 'NF4 double quantization; BF16 compute',
                         'device_map': self.model.hf_device_map, 'load_seconds': self.load_seconds,
                         'embedding_storage_dtype': str(self.model.model.embed_tokens.weight.dtype),
                         'head_storage_dtype': str(self.model.lm_head.weight.dtype),
                         'offload_note': 'Accelerate stages CPU-resident embeddings/head on the GPU for execution.'}

    def generate(self, messages, max_new_tokens=192):
        torch = self.torch
        from transformers import StoppingCriteria, StoppingCriteriaList
        class ThermalLimit(StoppingCriteria):
            def __init__(self):
                self.count = 0
                self.exceeded = False
            def __call__(self, input_ids, scores, **kwargs):
                self.count += 1
                if self.count % 8 == 0:
                    self.exceeded = gpu()['temperature_c'] >= 86
                return self.exceeded
        thermal = ThermalLimit()
        if gpu()['temperature_c'] > 78:
            raise RuntimeError('GPU must cool to <=78 C before a new request; no automatic restart')
        encoded = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                     enable_thinking=False, return_dict=True, return_tensors='pt')
        count = encoded['input_ids'].shape[-1]
        if count + max_new_tokens > 2048:
            raise ValueError(f'Complete input ({count}) plus answer budget exceeds 2048 tokens; nothing was truncated')
        encoded = {key: value.to('cuda:0') for key, value in encoded.items()}
        started = time.monotonic()
        with torch.inference_mode():
            output = self.model.generate(**encoded, max_new_tokens=max_new_tokens, do_sample=False,
                                         pad_token_id=self.tokenizer.eos_token_id, use_cache=True, max_time=90,
                                         stopping_criteria=StoppingCriteriaList([thermal]))
        torch.cuda.synchronize()
        if thermal.exceeded:
            raise RuntimeError('Generation stopped at the existing experiment cutoff of 86 C')
        tokens = output[0, count:]
        seconds = time.monotonic() - started
        return {'text': self.tokenizer.decode(tokens, skip_special_tokens=True), 'input_tokens': count,
                'output_tokens': len(tokens), 'seconds': seconds, 'output_tokens_per_second': len(tokens) / seconds,
                'peak_allocated_mib': torch.cuda.max_memory_allocated() / 2**20,
                'peak_reserved_mib': torch.cuda.max_memory_reserved() / 2**20, 'gpu_after': gpu()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--mode', choices=['gpu', 'offload'], default='offload')
    args = parser.parse_args()
    args.run.mkdir(parents=True, exist_ok=False)
    result = {'author': 'Created by ChatGPT (OpenAI)', 'started_utc': utc(), 'status': 'loading',
              'source': str(SOURCE), 'mode': args.mode, 'before': gpu()}
    write(args.run / 'preflight.json', result)
    try:
        model = LocalModel(args.run, args.mode)
        result.update(status='evaluating', metadata=model.metadata)
        write(args.run / 'preflight.json', result)
        prompts = [
            ('arithmetic_smoke', 'Return only a JSON object with key value. OCF is 142 and capex is 43. Compute OCF minus capex.'),
            ('evidence_smoke', 'Use only the supplied evidence. Return only JSON with keys answer, source_ids, insufficient_evidence. '
             'Evidence: [S1] Revenue was USD 100 million in 2025 and USD 80 million in 2024. '
             'Question: What was 2025 revenue? Use source_ids ["S1"].'),
            ('abstention_smoke', 'Use only the supplied evidence. Return only JSON with keys answer, source_ids, insufficient_evidence. '
             'Evidence: [S1] Revenue was USD 100 million in 2025. Question: What is the closing litigation reserve? '
             'If missing, answer null, source_ids [], insufficient_evidence true.')]
        result['outputs'] = []
        for name, prompt in prompts:
            output = model.generate([{'role': 'user', 'content': prompt}], max_new_tokens=128)
            output['name'] = name
            result['outputs'].append(output)
            write(args.run / 'preflight.json', result)
            print(json.dumps(output), flush=True)
        result['status'] = 'completed_smoke_only'
    except Exception as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        result['ended_utc'] = utc()
        write(args.run / 'preflight.json', result)


if __name__ == '__main__':
    main()
