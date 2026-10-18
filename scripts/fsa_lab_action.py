#!/usr/bin/env python3
"""Isolated Qwen3-4B FSA lab: audit, QLoRA continuation, benchmark, and ask.

Never loads a sealed test, publishes weights, modifies production branches,
or automatically promotes a candidate. Requires lab snapshot checkout.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

BASE = "Qwen/Qwen3-4B"
BASE_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
CHAMPION = Path("champions/qwen4-bfv3mix-20261017")
MIX_RUN = Path("runs/4b-bfv3mix-20261017T211441Z")
BFV4 = Path("runs/corpus-bf-v4-20261018T052227Z")
OWNER = Path("runs/v3-data-20261018T052500Z")
BFV3 = Path("runs/corpus-v3-20261016T230644Z")
GATE2 = Path("runs/20261016T171524Z/data/dev-protocol.json")


def rows(path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rel(root, path):
    return root / path


def required_sources(root):
    return {
        "bfv4_train": rel(root, BFV4 / "train.jsonl"),
        "bfv4_dev": rel(root, BFV4 / "dev.jsonl"),
        "bfv4_protocol": rel(root, BFV4 / "dev-protocol.jsonl"),
        "replay": rel(root, MIX_RUN / "train-packed.jsonl"),
        "owner_train": rel(root, OWNER / "train.jsonl"),
        "owner_protocol": rel(root, OWNER / "dev-protocol.jsonl"),
        "bfv3_protocol": rel(root, BFV3 / "dev-protocol.jsonl"),
        "gate2_protocol": rel(root, GATE2),
    }


def sample_stratified(items, quota, seed):
    """Round robin tasks with deterministic shuffling; do not touch any dev data."""
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for item in items:
        buckets[str(item.get("task", "unknown"))].append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    keys = sorted(buckets)
    rng.shuffle(keys)
    picked = []
    while len(picked) < quota and keys:
        following = []
        for key in keys:
            if buckets[key] and len(picked) < quota:
                picked.append(buckets[key].pop())
            if buckets[key]:
                following.append(key)
        keys = following
    return picked


def load_gate2(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "validation" not in doc:
        raise ValueError("Gate2 format must contain validation")
    return doc["validation"]


def protocol_sets(paths):
    return {
        "bfv4_90": list(rows(paths["bfv4_protocol"])),
        "bfv3_40": list(rows(paths["bfv3_protocol"])),
        "gate2_48": load_gate2(paths["gate2_protocol"]),
        "owner_v3": list(rows(paths["owner_protocol"])),
    }


def read_approved_hourly(bank_path, max_rows):
    """Opt-in: read only reviewed eligible question rows; never use SEC review candidates."""
    if max_rows <= 0:
        return []
    if not bank_path:
        raise ValueError("An hourly bank path is required when hourly_count > 0")
    where = Path(bank_path)
    if where.is_dir():
        files = sorted(where.glob("hourly/*/[0-2][0-9].json"))[-168:]
    elif where.is_file():
        files = [where]
    else:
        raise FileNotFoundError("Hour-bank path missing; run the scheduled bank job first")
    if not files:
        raise ValueError("No hourly question-bank files located")
    selected = []
    seen = set()
    for file in reversed(files):
        data = json.loads(file.read_text(encoding="utf-8"))
        for record in data.get("questions", []):
            if len(selected) >= max_rows:
                break
            if not record.get("training_eligible"):
                continue
            source = record.get("source", {})
            status = record.get("review_status")
            authorized = (source.get("kind") == "synthetic" and status == "synthetic_verified") or (
                source.get("kind") == "research" and status == "human_verified_report_fact"
                and source.get("rights") in ("owned", "licensed_for_training", "public_domain"))
            if not authorized:
                continue
            prompt = record.get("input", "")
            response = record.get("output", "")
            if not isinstance(prompt, str) or not isinstance(response, str) or not prompt:
                continue
            try:
                if not isinstance(json.loads(response), dict):
                    continue
            except (TypeError, ValueError):
                continue
            if prompt in seen:
                continue
            seen.add(prompt)
            selected.append({"id": record["id"], "input": prompt, "output": response,
                             "task": record.get("task", "hourly_reviewed")})
    return selected


def assemble(root, destination, objective, seed, new_count, replay_count, owner_count, hourly_bank=None, hourly_count=0):
    paths = required_sources(root)
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing sparse-checkout files: " + ", ".join(missing))
    protocols = protocol_sets(paths)
    protected = {r["input"] for items in protocols.values() for r in items}
    protected.update(r["input"] for r in rows(paths["bfv4_dev"]))
    fresh = [r for r in rows(paths["bfv4_train"]) if r.get("split") == "train"]
    replay = [r for r in rows(paths["replay"]) if r.get("split") == "train"]
    # Real owner Task A is explicitly excluded: weak unreviewed reason labels.
    owner = [r for r in rows(paths["owner_train"])
             if r.get("split") == "train" and r.get("task") == "bs_line_classification"]
    # Require >=30% historical replay even when mixed and hourly examples are enabled.
    non_replay_target = new_count + (owner_count if objective == "mixed" else 0) + hourly_count
    effective_replay = max(replay_count, math.ceil(3 * non_replay_target / 7))
    if effective_replay > 2000:
        raise ValueError("Replay quota exceeds 2000; reduce new examples")
    spec = [("bfv4", fresh, new_count), ("historical_replay", replay, effective_replay)]
    if objective == "mixed":
        spec.append(("owner_rule_labels", owner, owner_count))
    if hourly_count:
        hourly = read_approved_hourly(hourly_bank, hourly_count)
        if hourly:
            spec.append(("hourly_approved", hourly, len(hourly)))
    taken = set(protected)
    merged = []
    dropped = Counter()
    for name, pool, quota in spec:
        for r in sample_stratified(pool, quota * 2, seed + len(merged) + len(name)):
            key = r["input"]
            if key in taken:
                dropped[name + ":duplicate_or_protected"] += 1
                continue
            expected = r.get("output")
            try:
                parsed = json.loads(expected)
            except (TypeError, ValueError):
                dropped[name + ":bad_output"] += 1
                continue
            if not isinstance(parsed, dict):
                dropped[name + ":non_object"] += 1
                continue
            merged.append({"task": r.get("task", "unknown"), "company_id": r.get("company_id"),
                           "input": key, "output": expected, "source": name})
            taken.add(key)
            if sum(x["source"] == name for x in merged) >= quota:
                break
    if not merged:
        raise ValueError("No training rows passed audit")
    replay_actual = sum(x["source"] == "historical_replay" for x in merged)
    if replay_actual / len(merged) < 0.30 - 1e-8:
        raise ValueError("Historical replay under 30%; stop rather than silently regress older contracts")
    rng = random.Random(seed)
    rng.shuffle(merged)
    destination.mkdir(parents=True, exist_ok=True)
    packed = destination / "train.jsonl"
    with packed.open("w", encoding="utf-8") as handle:
        for r in merged:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_only_not_trained", "objective": objective, "seed": seed,
        "base": BASE, "revision": BASE_REVISION,
        "sources": {k: {"path": str(p), "sha256": sha256(p)} for k, p in paths.items()},
        "counts": dict(Counter(r["source"] for r in merged)),
        "effective_historical_replay_target": effective_replay,
        "tasks": dict(Counter(r["task"] for r in merged)),
        "dropped": dict(dropped),
        "protected_protocol_sizes": {k: len(v) for k, v in protocols.items()},
        "protected_prompt_overlap": len({r["input"] for r in merged} & protected),
        "train_file_sha256": sha256(packed),
        "limitations": [
            "No sealed test is fetched or read.",
            "Owner task A excluded because rule-generated explanations lack human gold labels.",
            "Owner task C labels are pipeline defaults, not independent accounting gold labels.",
            "Template-generated dev results do not establish out-of-distribution FSA accuracy.",
            "Existing published protocols have been reused; construct an independent future holdout."
        ]
    }
    if manifest["protected_prompt_overlap"]:
        raise RuntimeError("Evaluation prompt contamination detected")
    dump(destination / "audit.json", manifest)
    return manifest


def compute_dtype(torch):
    if not torch.cuda.is_available():
        raise RuntimeError("GPU absent. Training/benchmark/ask requires a self-hosted CUDA runner.")
    if torch.cuda.get_device_properties(0).total_memory < 5 * 1024 ** 3:
        raise RuntimeError("Require >=5 GiB total GPU VRAM for this 4B QLoRA configuration.")
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def load_model(adapter_path, trainable=False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel, prepare_model_for_kbit_training
    dtype = compute_dtype(torch)
    if not (adapter_path / "adapter_model.safetensors").exists():
        raise FileNotFoundError("Missing Git LFS adapter weight: " + str(adapter_path))
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=BASE_REVISION)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    base = AutoModelForCausalLM.from_pretrained(
        BASE, revision=BASE_REVISION, quantization_config=config,
        device_map={"": 0}, torch_dtype=dtype)
    if trainable:
        base = prepare_model_for_kbit_training(
            base, use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False})
    model = PeftModel.from_pretrained(base, str(adapter_path), is_trainable=trainable)
    model.config.use_cache = not trainable
    if not trainable:
        model.eval()
    return tokenizer, model, dtype


def encode(tokenizer, row, max_length):
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": row["input"]}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prefix = tokenizer.encode(prompt, add_special_tokens=False)
    answer = tokenizer.encode(row["output"], add_special_tokens=False) + [tokenizer.eos_token_id]
    if len(prefix) + len(answer) > max_length:
        return None
    return {"input_ids": prefix + answer, "attention_mask": [1] * (len(prefix) + len(answer)),
            "labels": [-100] * len(prefix) + answer}


def train_model(root, out, max_steps, max_length, lr):
    import torch
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments
    if (out / "candidate").exists():
        raise FileExistsError("Candidate already exists; use a unique run output")
    torch.set_num_threads(4)
    tokenizer, model, dtype = load_model(root / CHAMPION, trainable=True)
    train_data = []
    skipped = Counter()
    for row in rows(out / "train.jsonl"):
        encoded = encode(tokenizer, row, max_length)
        if encoded is None:
            skipped[row["source"]] += 1
        else:
            train_data.append(encoded)
    validation = []
    for row in rows(root / BFV4 / "dev.jsonl"):
        encoded = encode(tokenizer, row, max_length)
        if encoded is not None:
            validation.append(encoded)
    if len(train_data) < 100 or len(validation) < 10:
        raise RuntimeError("Insufficient non-truncated train/validation examples")
    target = out / "candidate"
    args = TrainingArguments(
        output_dir=str(target), max_steps=max_steps,
        per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=4, learning_rate=lr, warmup_ratio=0.03,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16,
        logging_steps=5, eval_strategy="steps", eval_steps=50,
        save_strategy="steps", save_steps=50, save_total_limit=2,
        load_best_model_at_end=True, metric_for_best_model="eval_loss",
        greater_is_better=False, report_to="none", remove_unused_columns=False,
        optim="adamw_torch", seed=20261018, dataloader_num_workers=0)
    trainer = Trainer(
        model=model, args=args, train_dataset=Dataset.from_list(train_data),
        eval_dataset=Dataset.from_list(validation),
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100))
    result = trainer.train()
    if not math.isfinite(float(result.metrics.get("train_loss", math.nan))):
        raise RuntimeError("Training loss non-finite")
    trainer.model.save_pretrained(target)
    tokenizer.save_pretrained(target)
    dump(out / "train_report.json", {
        "steps_completed": trainer.state.global_step, "loss": result.metrics.get("train_loss"),
        "validation_best": trainer.state.best_metric,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "training_rows": len(train_data), "validation_rows": len(validation),
        "skipped_overlength": dict(skipped), "device": torch.cuda.get_device_name(0),
        "candidate_status": "unapproved", "no_auto_promotion": True,
        "warning": "Training may improve synthetic tasks but not real-filings accuracy."})


def extract_json(generation):
    # Strict: output must be a standalone object; no Markdown, no prose.
    try:
        obj = json.loads(generation, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None


def similar(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and similar(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(similar(a, b) for a, b in zip(actual, expected))
    if type(expected) is bool or expected is None:
        return type(actual) is type(expected) and actual == expected
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-4, abs_tol=1e-6)
    return actual == expected and type(actual) is type(expected)


def generate(model, tokenizer, question, limit):
    import torch
    messages = [{"role": "user", "content": question}]
    s = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    batch = tokenizer(s, return_tensors="pt").to("cuda")
    if batch["input_ids"].shape[1] > 1800:
        raise ValueError("Question too long for this interactive configuration")
    with torch.inference_mode():
        result = model.generate(**batch, max_new_tokens=limit, do_sample=False,
                                pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(result[0, batch["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def benchmark(root, adapter, out, protocol_names):
    tokenizer, model, dtype = load_model(adapter)
    sets = protocol_sets(required_sources(root))
    report = {"model": BASE, "adapter": str(adapter), "dtype": str(dtype),
              "is_promoted": False, "protocols": {}}
    for name in protocol_names:
        records = []
        for r in sets[name]:
            start = time.monotonic()
            output = generate(model, tokenizer, r["input"], 192 if name in ("gate2_48", "owner_v3") else 96)
            actual = extract_json(output)
            expected = r.get("expected")
            if expected is None:
                expected = json.loads(r["output"])
            # Gate2 arithmetic has a different historical scorer; this reports an independent strict estimate.
            gold = {k: v for k, v in expected.items() if k != "source_id"}
            correct = actual is not None and similar(actual, gold) and (
                "source_id" not in expected or actual.get("source_id") == expected["source_id"])
            records.append({"task": r.get("task"), "correct": bool(correct),
                            "valid_json": actual is not None, "elapsed_s": time.monotonic() - start,
                            "expected": expected, "output": output})
        counts = Counter(x["task"] for x in records)
        per_task = {k: {"correct": sum(x["correct"] for x in records if x["task"] == k), "total": v}
                    for k, v in counts.items()}
        summary = {"correct": sum(r["correct"] for r in records), "total": len(records),
                   "valid_json": sum(r["valid_json"] for r in records),
                   "macro": statistics.mean(v["correct"] / v["total"] for v in per_task.values()),
                   "median_seconds": statistics.median(x["elapsed_s"] for x in records),
                   "tasks": per_task, "examples": records}
        report["protocols"][name] = summary
        dump(out, report)
        print(f"{name}: {summary['correct']}/{summary['total']}", flush=True)
    report["notes"] = [
        "No sealed tests opened.",
        "This independently implemented strict scorer may differ slightly from historical Gate2 evaluator.",
        "Protocol reused for development; no claim of external generalization.",
        "Candidate is not promoted even when it passes an existing dev gate."
    ]
    dump(out, report)


def ask(root, adapter, question, out, interactive):
    tokenizer, model, dtype = load_model(adapter)
    def answer(q):
        if not q.strip():
            return
        response = generate(model, tokenizer, q, 256)
        record = {"question": q, "answer": response, "parsed": extract_json(response),
                  "model": BASE, "adapter": str(adapter)}
        print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
        if out:
            dump(out, record)
    if question:
        answer(question)
    if interactive:
        print("FSA chat: type a question; 'exit' to quit.", flush=True)
        while True:
            try:
                q = input("FSA> ")
            except (EOFError, KeyboardInterrupt):
                break
            if q.strip().lower() in ("exit", "quit"):
                break
            answer(q)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["audit", "train", "benchmark", "ask"])
    p.add_argument("--root", type=Path, default=Path("lab"))
    p.add_argument("--out", type=Path, default=Path("outputs"))
    p.add_argument("--objective", choices=["finance_v4", "mixed"], default="finance_v4")
    p.add_argument("--seed", type=int, default=20261018)
    p.add_argument("--new-count", type=int, default=1200)
    p.add_argument("--replay-count", type=int, default=600)
    p.add_argument("--owner-count", type=int, default=150)
    p.add_argument("--hourly-bank", type=Path, help="Optional separate fsa-question-bank branch checkout")
    p.add_argument("--hourly-count", type=int, default=0, help="0 disables integration; max 400 reviewed rows")
    p.add_argument("--steps", type=int, choices=[50, 100, 200], default=50)
    p.add_argument("--max-length", type=int, choices=[384, 512], default=384)
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--adapter", choices=["champion", "candidate"], default="champion")
    p.add_argument("--question", default="")
    p.add_argument("--interactive", action="store_true")
    args = p.parse_args()
    if not (0 < args.new_count <= 3000 and 0 <= args.replay_count <= 2000 and
            0 <= args.owner_count <= 500 and 0 <= args.hourly_count <= 400 and 1e-6 <= args.lr <= 1e-4):
        p.error("Quota or learning rate out of safe bounds")
    root = args.root.resolve()
    out = args.out.resolve()
    adapter = (root / CHAMPION) if args.adapter == "champion" else (out / "candidate")
    if args.mode in ("audit", "train"):
        report = assemble(root, out, args.objective, args.seed,
                          args.new_count, args.replay_count, args.owner_count,
                           hourly_bank=args.hourly_bank, hourly_count=args.hourly_count)
        print(json.dumps({"counts": report["counts"], "overlap": report["protected_prompt_overlap"],
                          "audit": str(out / "audit.json")}, indent=2), flush=True)
    if args.mode == "train":
        train_model(root, out, args.steps, args.max_length, args.lr)
        benchmark(root, out / "candidate", out / "evaluation.json", ["bfv4_90", "bfv3_40", "gate2_48"])
    elif args.mode == "benchmark":
        out.mkdir(parents=True, exist_ok=True)
        benchmark(root, adapter, out / "evaluation.json", ["bfv4_90", "bfv3_40", "gate2_48"])
    elif args.mode == "ask":
        out.mkdir(parents=True, exist_ok=True)
        if not args.question and not args.interactive:
            p.error("--question or --interactive required")
        ask(root, adapter, args.question, out / "answer.json" if args.question else None, args.interactive)


if __name__ == "__main__":
    main()
