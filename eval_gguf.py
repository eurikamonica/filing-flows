"""Evaluate a GGUF export through llama-server with the same protocols and scoring as bfv3_4b.py.

Chat template comes from the GGUF (--jinja) with enable_thinking=false; greedy decoding; same max_new_tokens per protocol.
Created by Claude (Anthropic).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from bfv3_4b import LAB, BETA, protocol_sets, score, summarize, sha, utc, write

SERVER = BETA / '.runtime/tools/llama.cpp-b11381/bin/llama-server.exe'


def post(port, payload, timeout=300):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gguf', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--port', type=int, default=8790)
    ap.add_argument('--protocols', nargs='+', default=['bfv3_dev40', 'gate2_dev48', 'bfv4_dev90'])
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit('Refuse to overwrite ' + str(a.out))
    from run_control import gpu_status
    log = open(a.out.with_suffix('.server.log'), 'w', encoding='utf-8')
    server = subprocess.Popen([str(SERVER), '-m', str(a.gguf), '--host', '127.0.0.1', '--port', str(a.port), '-ngl', '99',
                               '-c', '4096', '--jinja', '--no-webui', '-np', '1'], stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(240):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health', timeout=2) as r:
                    if json.loads(r.read()).get('status') == 'ok':
                        break
            except Exception:
                pass
            if server.poll() is not None:
                raise RuntimeError('llama-server exited; see server log')
            time.sleep(1)
        else:
            raise RuntimeError('llama-server did not become healthy')
        sets = protocol_sets()
        result = {'author': 'Created by Claude (Anthropic)', 'gguf': str(a.gguf), 'gguf_bytes': a.gguf.stat().st_size,
                  'runtime': 'llama.cpp b11381 llama-server (Vulkan), -ngl 99, --jinja, enable_thinking=false, temperature 0',
                  'started_utc': utc(), 'protocols': {}}
        for name in a.protocols:
            tokens = 192 if name == 'gate2_dev48' else 64
            details, timings = [], []
            for row, expected in sets[name]:
                started = time.monotonic()
                reply = post(a.port, {'messages': [{'role': 'user', 'content': row['input']}], 'temperature': 0, 'top_k': 1,
                                      'max_tokens': tokens, 'chat_template_kwargs': {'enable_thinking': False}})
                elapsed = time.monotonic() - started
                timings.append(elapsed)
                output = reply['choices'][0]['message']['content'] or ''
                details.append({'task': row['task'], 'company_id': row['company_id'], 'expected': expected, 'output': output,
                                'seconds': elapsed, 'gpu': gpu_status(), **score(name, output, row, expected)})
                print('EVAL', name, len(details), '/', len(sets[name]), flush=True)
            result['protocols'][name] = summarize(details, timings)
            write(a.out, result)
        result.update(status='completed', ended_utc=utc())
        write(a.out, result)
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()


if __name__ == '__main__':
    main()
