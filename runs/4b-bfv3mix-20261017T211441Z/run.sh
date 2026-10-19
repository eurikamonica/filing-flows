#!/usr/bin/env bash
# Created by Claude (Anthropic). Mixed bfv3 + old-contract replay continuation from the 4B champion, then eval.
# Baseline evaluation is reused from runs/4b-bfv3-20261017T062749Z/eval-baseline.json. Touch model-expansion-lab/runs/4b-bfv3mix-20261017T211441Z/STOP to stop training.
set -u
cd "/c/Users/Oliver Hu/Downloads/filing-flows-beta-fsa-chatgpt/filing-flows-beta-fsa-chatgpt/fsa-beta"
export PYTHONPATH="$(pwd)" PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python.exe
R=model-expansion-lab/runs/4b-bfv3mix-20261017T211441Z
stamp(){ echo "{\"utc\":\"$(date -u +%FT%TZ)\",\"stage\":\"$1\",\"exit\":\"${2:-}\"}" >> $R/stages.jsonl; }
stamp train_start
$PY -u model-expansion-lab/train_continuation.py --data $R/train-packed.jsonl --out $R/train --model Qwen/Qwen3-4B   --init-adapter model-expansion-lab/runs/20261016T171524Z/archive/qwen4 --qlora --compute-dtype bfloat16 --gradient-checkpointing   --max-length 384 --batch-size 1 --gradient-accumulation-steps 4 --learning-rate 5e-5 --lora-rank 8 --target-modules qv   --max-steps 900 --eval-steps 100 --save-steps 100 --logging-steps 5 --stop-file $R/STOP --min-free-gib 16 > $R/train.log 2>&1
stamp train_end $?
if [ -f $R/train/adapter_model.safetensors ]; then
  stamp final_eval_start
  $PY -u model-expansion-lab/bfv3_4b.py eval --adapter $R/train --out $R/eval-final.json > $R/eval-final.log 2>&1; stamp final_eval_end $?
  last=$(ls -d $R/train/checkpoint-* 2>/dev/null | sort -t- -k2 -n | tail -1)
  best=$($PY -c "import json;print(json.load(open('$R/train/fsa_manifest.json')).get('best_checkpoint') or '')")
  if [ -n "$last" ] && [ "$(basename "$last")" != "$(basename "$best")" ] && [ -f "$last/adapter_model.safetensors" ]; then
    stamp last_eval_start
    $PY -u model-expansion-lab/bfv3_4b.py eval --adapter "$last" --out $R/eval-last.json > $R/eval-last.log 2>&1; stamp last_eval_end $?
  fi
fi
stamp done
