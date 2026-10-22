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


def _embedding_weight(source):
    """The embedding table (BF16, 151,936 x 4,096) read straight from the checkpoint into RAM."""
    import torch
    from safetensors import safe_open
    index = Path(source) / 'model.safetensors.index.json'
    name = 'model.embed_tokens.weight'
    shard = json.loads(index.read_text(encoding='utf-8'))['weight_map'][name] if index.exists() else 'model.safetensors'
    with safe_open(str(Path(source) / shard), framework='pt', device='cpu') as f:
        return f.get_tensor(name).to(torch.bfloat16).contiguous()


def _cpu_embedding_class():
    import torch

    class CpuEmbedding(torch.nn.Module):
        """Embedding lookups in RAM: only the rows of the tokens are sent to the GPU (kilobytes per step)."""
        def __init__(self, weight, device):
            super().__init__()
            self.register_buffer('weight', weight, persistent=False)    # a buffer: model.device stays the GPU
            self.device = torch.device(device)
            self.num_embeddings, self.embedding_dim = weight.shape

        def forward(self, input_ids):
            rows = torch.nn.functional.embedding(input_ids.to('cpu'), self.weight)
            return rows.to(self.device, non_blocking=True)

        def _apply(self, fn, *args, **kwargs):             # model.to()/cuda() must not move the table onto the card
            return self
    return CpuEmbedding


def CpuEmbedding(weight, device):
    return _cpu_embedding_class()(weight, device)


class LocalModel:
    def __init__(self, runtime, mode='auto', source=SOURCE):
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
        if mode == 'auto':
            # 'gpu': everything on the card (about 6.5 GB with the BF16 embeddings and output head; 10 GB cards and up).
            # 'lean': the 36 blocks and an NF4 output head on the card (about 4.5 GB), the embedding table in RAM, looked
            # up there (a few rows per step, nothing staged). 'offload': the earlier layout, where Accelerate copies the
            # 1.2 GB embedding table and the 1.2 GB output head to the card at every generated token (slow).
            mode = 'gpu' if snapshot['total_mib'] >= 10000 else 'lean'
        self.tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True)
        try:
            self._load(source, mode)
        except Exception as exc:                            # noqa: BLE001 — the lean layout failed: the proven one
            if mode != 'lean':
                raise
            print('Lean layout unavailable (' + repr(exc)[:200] + '); using the offload layout.', flush=True)
            self.model = None
            torch.cuda.empty_cache()
            mode = 'offload'
            self._load(source, mode)
        self.mode = mode
        self.load_seconds = time.monotonic() - started
        notes = {'gpu': 'All weights on the GPU.',
                 'lean': 'Decoder blocks and NF4 output head on the GPU; the embedding table stays in RAM and is looked up there.',
                 'offload': 'Accelerate stages CPU-resident embeddings/head on the GPU for execution.'}
        self.metadata = {'model': 'Qwen/Qwen3-8B', 'revision': REVISION, 'adapter': None,
                         'source_checksums_verified': True, 'layout': mode,
                         'quantization': 'NF4 double quantization; BF16 compute' + (' (output head NF4 too)' if mode == 'lean' else ''),
                         'device_map': getattr(self.model, 'hf_device_map', None), 'load_seconds': self.load_seconds,
                         'embedding_storage_dtype': str(self.model.model.embed_tokens.weight.dtype),
                         'head_storage_dtype': str(self.model.lm_head.weight.dtype),
                         'offload_note': notes[mode]}
        print(f'Layout: {mode} — {notes[mode]} Loaded in {self.load_seconds:.0f} s.', flush=True)

    def _load(self, source, mode):
        torch = self.torch
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        layers = {'model.layers.' + str(i): 0 for i in range(36)}
        extra = {}
        if mode == 'lean':
            # quantize the output head as well (by default bitsandbytes keeps it in BF16): the skip list names a module
            # that does not exist, so nothing is left out
            extra['llm_int8_skip_modules'] = ['model.embed_tokens']
        config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                   bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                   llm_int8_enable_fp32_cpu_offload=mode in ('offload', 'lean'), **extra)
        device_map = {'': 0} if mode == 'gpu' else {
            'model.embed_tokens': 'cpu', 'model.norm': 0, 'lm_head': 0 if mode == 'lean' else 'cpu', **layers}
        self.model = AutoModelForCausalLM.from_pretrained(
            source, local_files_only=True, torch_dtype=torch.bfloat16, quantization_config=config,
            device_map=device_map, attn_implementation='sdpa').eval()
        if mode == 'lean':
            self.model.model.embed_tokens = CpuEmbedding(_embedding_weight(source), 'cuda:0')
            if hasattr(self.model, 'hf_device_map'):
                self.model.hf_device_map['model.embed_tokens'] = 'cpu (lookup)'
            # a quick forward pass: any layout problem shows here, at load, not at the first question
            with torch.inference_mode():
                ids = self.tokenizer('ping', return_tensors='pt')['input_ids'].to('cuda:0')
                self.model(input_ids=ids)

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
        print(f'Answering: {count} input tokens, up to {max_new_tokens} new ...', flush=True)
        with torch.inference_mode():
            output = self.model.generate(**encoded, max_new_tokens=max_new_tokens, do_sample=False,
                                         pad_token_id=self.tokenizer.eos_token_id, use_cache=True, max_time=90,
                                         stopping_criteria=StoppingCriteriaList([thermal]))
        torch.cuda.synchronize()
        if thermal.exceeded:
            raise RuntimeError('Generation stopped at the existing experiment cutoff of 86 C')
        tokens = output[0, count:]
        seconds = time.monotonic() - started
        print(f'Done: {len(tokens)} tokens in {seconds:.1f} s ({len(tokens) / max(seconds, 1e-9):.1f} tokens/s).', flush=True)
        return {'text': self.tokenizer.decode(tokens, skip_special_tokens=True), 'input_tokens': count,
                'output_tokens': len(tokens), 'seconds': seconds, 'output_tokens_per_second': len(tokens) / seconds,
                'peak_allocated_mib': torch.cuda.max_memory_allocated() / 2**20,
                'peak_reserved_mib': torch.cuda.max_memory_reserved() / 2**20, 'gpu_after': gpu()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--mode', choices=['auto', 'gpu', 'lean', 'offload'], default='auto')
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
