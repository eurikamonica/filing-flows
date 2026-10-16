"""Keep training the local fallback model (pipeline/local_model.py) — one run of .github/workflows/train-local-model.yml.

The "model" branch holds:
  adapter/          the LoRA adapter the posting workflows use (production)
  work/             the adapter in training: every run continues it on the new examples plus a replay of older ones
  corpus.jsonl.gz   every training example so far (pipeline/corpus.py), newest kept when it grows past MAX_CORPUS
  corpus-ids.txt    the source keys already turned into examples (the next corpus run skips them)
  state.json        which examples work/ has seen, the scores
  reports.jsonl     one line per run: examples, steps, loss, held-out scores, whether it was promoted, sample posts
  README.md         the latest run in words

Evaluation: companies whose CIK falls in a fixed tenth are never trained on. On a sample of their examples, a post counts
when it would be published: it passes the same checks as a real post (tweet.clean / engage.clean: length, cashtags,
hashtags, finished sentences, no advice) and every number in it is in the facts. work/ replaces adapter/ only when it
scores higher (the first adapter needs half of the held-out posts right).

    python -m pipeline.train_local --model-dir model --new new.jsonl --minutes 40 --eval 40
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import random
import shutil
import sys
import time

from . import corpus as C, engage, local_model as L, social, tweet

MAX_CORPUS = 30000
REPLAY = 0.3                      # share of each run's training on examples work/ has seen before
FIRST_BAR = 0.5                   # the first adapter must get half of the held-out posts right
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def held_out(ex):
    return int(hashlib.sha1(str(ex.get("cik")).encode()).hexdigest(), 16) % 10 == 0


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def grade(ex, post):
    """(published?, why not) for one generated post."""
    try:
        if ex["check"] == "engage":
            post = engage.clean(post, ex["cashtags"], ex["tags"])
        else:
            post = tweet.clean(post, (ex["cashtags"] or [""])[0], ex["tags"], social.xlen)
    except ValueError as why:
        return False, str(why)[:80]
    bad = L.unsupported(post, ex["prompt"])
    return (not bad), (f"numbers not in the facts: {bad[:3]}" if bad else "")


def evaluate(tok, model, sample):
    out = []
    for ex in sample:
        t0 = time.time()
        try:
            post = L.write(tok, model, ex["prompt"])
        except Exception as err:                       # one bad generation does not end the run
            post = f"(error: {str(err)[:80]})"
        ok, why = grade(ex, post)
        out.append({"id": ex["id"], "kind": ex["kind"], "ok": ok, "why": why, "post": post, "secs": round(time.time() - t0, 1)})
    score = sum(r["ok"] for r in out) / len(out) if out else 0.0
    return score, out


def train(tok, model, examples, minutes, lr=2e-4, accum=4, max_len=768):
    import torch
    model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
    end = tok.eos_token or "<|im_end|>"
    t0, losses, seen, n = time.time(), [], [], 0
    opt.zero_grad()
    for ex in examples:
        if time.time() - t0 > minutes * 60:
            break
        p_ids = tok(L.chat_input(tok, ex["prompt"]), add_special_tokens=False)["input_ids"]
        t_ids = tok(ex["target"] + end, add_special_tokens=False)["input_ids"]
        ids, labels = (p_ids + t_ids)[-max_len:], ([-100] * len(p_ids) + t_ids)[-max_len:]
        if all(x == -100 for x in labels):
            continue
        loss = model(input_ids=torch.tensor([ids]), labels=torch.tensor([labels])).loss
        (loss / accum).backward()
        losses.append(float(loss.item()))
        seen.append(ex["id"])
        n += 1
        if n % accum == 0:
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            opt.zero_grad()
    if n % accum:
        opt.step()
        opt.zero_grad()
    model.eval()
    return {"examples": n, "steps": (n + accum - 1) // accum, "loss_first": round(sum(losses[:20]) / max(1, len(losses[:20])), 4),
            "loss_last": round(sum(losses[-20:]) / max(1, len(losses[-20:])), 4), "minutes": round((time.time() - t0) / 60, 1)}, seen


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="model")
    ap.add_argument("--new", default="new.jsonl")
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--eval", type=int, default=40)
    args = ap.parse_args()
    md = args.model_dir
    os.makedirs(md, exist_ok=True)
    state_path = os.path.join(md, "state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    state.setdefault("seen", [])
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # the corpus: old + new, deduplicated, newest kept
    corpus = {ex["id"]: ex for ex in read_jsonl(os.path.join(md, "corpus.jsonl.gz")) if ex.get("v", 1) >= C.VERSION}
    new = [ex for ex in read_jsonl(args.new) if ex["id"] not in corpus]
    for ex in new:
        corpus[ex["id"]] = ex
    allx = sorted(corpus.values(), key=lambda e: e.get("created", ""))[-MAX_CORPUS:]
    with gzip.open(os.path.join(md, "corpus.jsonl.gz"), "wt", encoding="utf-8") as f:
        for ex in allx:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    ids_path = os.path.join(md, "corpus-ids.txt")
    old_ids = open(ids_path).read().split() if os.path.exists(ids_path) else []
    srcs = set(old_ids[1:]) if old_ids[:1] == [f"#v{C.VERSION}"] else set()
    srcs |= {ex.get("src") for ex in allx if ex.get("src")}
    open(ids_path, "w").write(f"#v{C.VERSION}\n" + "\n".join(sorted(srcs)) + "\n")
    by_kind = {}
    for ex in allx:
        by_kind[ex["kind"]] = by_kind.get(ex["kind"], 0) + 1
    print(f"corpus: {len(allx)} examples ({len(new)} new) · " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))

    # held-out sample (stable: seeded by the corpus size bucket), stratified by kind
    hold = [ex for ex in allx if held_out(ex)]
    rng = random.Random(len(hold) // 200)
    kinds = sorted({ex["kind"] for ex in hold})
    sample = []
    per = {k: [ex for ex in hold if ex["kind"] == k] for k in kinds}
    for xs in per.values():
        rng.shuffle(xs)
    while len(sample) < args.eval and any(per.values()):                # equal shares, the rest from the larger kinds
        for k in kinds:
            if per[k] and len(sample) < args.eval:
                sample.append(per[k].pop())

    # training order: examples work/ has not seen, then a replay of seen ones
    seen = set(state["seen"])
    pool = [ex for ex in allx if not held_out(ex)]
    fresh = [ex for ex in pool if ex["id"] not in seen]
    old = [ex for ex in pool if ex["id"] in seen]
    random.Random(started).shuffle(fresh)
    random.Random(started + "r").shuffle(old)
    # kinds take turns (earnings quarters outnumber 8-Ks a hundred to one): every kind is trained every run
    def by_kind(xs):
        q = {}
        for ex in xs:
            q.setdefault(ex["kind"], []).append(ex)
        return q
    fq, oq = by_kind(fresh), by_kind(old)
    plan, kinds_all = [], sorted(set(fq) | set(oq))
    while any(fq.values()) or any(oq.values()):
        for k in kinds_all:
            f, o = fq.get(k) or [], oq.get(k) or []
            if o and (not f or random.random() < REPLAY):
                plan.append(o.pop())
            elif f:
                plan.append(f.pop())
    if not plan or not sample:
        print("nothing to train or evaluate yet")
        json.dump(state, open(state_path, "w"))
        return 0

    work = os.path.join(md, "work")
    prod = os.path.join(md, "adapter")
    has_work = os.path.exists(os.path.join(work, "adapter_config.json"))
    has_prod = os.path.exists(os.path.join(prod, "adapter_config.json"))
    tok, model = L.load(work if has_work else None, trainable=True)
    if not has_work:
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=TARGETS, task_type="CAUSAL_LM"))
    stats, used = train(tok, model, plan, args.minutes)
    print(f"trained: {stats}")
    tmp = os.path.join(md, ".work-new")
    shutil.rmtree(tmp, ignore_errors=True)
    model.save_pretrained(tmp)
    score_w, res_w = evaluate(tok, model, sample)
    print(f"held-out: work {score_w:.2f} on {len(sample)} posts")
    del model

    score_p, res_p = None, []
    if has_prod:
        tok_p, model_p = L.load(prod)
        score_p, res_p = evaluate(tok_p, model_p, sample)
        del model_p
        print(f"held-out: production {score_p:.2f}")
    elif "base_score" not in state:
        tok_b, model_b = L.load(None)
        state["base_score"], _ = evaluate(tok_b, model_b, sample)
        del model_b
        print(f"held-out: base model without an adapter {state['base_score']:.2f}")

    # the trained state always continues; production changes only on a better score
    shutil.rmtree(work, ignore_errors=True)
    shutil.move(tmp, work)
    state["seen"] = sorted(seen | set(used))[-MAX_CORPUS:]
    promote = (score_w >= FIRST_BAR) if score_p is None else (score_w > score_p)
    if promote:
        shutil.rmtree(prod, ignore_errors=True)
        shutil.copytree(work, prod)
        state["production"] = {"score": score_w, "since": started, "examples_seen": len(state["seen"])}
    state["last"] = {"at": started, "work_score": score_w, "production_score": score_p}
    json.dump(state, open(state_path, "w"))

    report = {"at": started, "base": L.BASE, "corpus": len(allx), "new": len(new), "by_kind": by_kind, **stats,
              "eval_n": len(sample), "work_score": round(score_w, 3), "production_score": None if score_p is None else round(score_p, 3),
              "base_score": state.get("base_score"), "promoted": promote,
              "fails": {}, "samples": [r for r in res_w if r["ok"]][:3] + [r for r in res_w if not r["ok"]][:3]}
    for r in res_w:
        if not r["ok"]:
            k = r["why"].split(":")[0][:40]
            report["fails"][k] = report["fails"].get(k, 0) + 1
    with open(os.path.join(md, "reports.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")
    prod_line = (f"**{state['production']['score']:.0%}** of held-out posts publishable (promoted {state['production']['since'][:16]} UTC)"
                 if state.get("production") else "none yet — the first adapter needs " + f"{FIRST_BAR:.0%} of held-out posts publishable")
    open(os.path.join(md, "README.md"), "w", encoding="utf-8").write(
        f"# Local fallback model\n\nBase: `{L.BASE}` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` "
        f"on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API "
        f"model failed (`pipeline/local_model.py`).\n\n"
        f"- Production adapter: {prod_line}\n"
        f"- Last run {started[:16]} UTC: {stats['examples']} examples, loss {stats['loss_first']} → {stats['loss_last']}, "
        f"work adapter {score_w:.0%} vs production {('—' if score_p is None else f'{score_p:.0%}')}"
        f"{' → promoted' if promote else ''}\n- Corpus: {len(allx)} examples " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items()))
        + "\n- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.\n\nEvery run: `reports.jsonl`.\n")
    print(f"{'promoted' if promote else 'kept production'}: work {score_w:.2f} vs production {score_p}")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
        f.write(open(os.path.join(md, "README.md")).read() + "\n\n**Sample posts (held-out companies)**\n\n"
                + "\n".join(f"- {'✅' if r['ok'] else '❌ ' + r['why']}: {r['post']}" for r in report["samples"]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
