"""The free fallback writer: a small open-weight model (Qwen3, Apache 2.0) with a LoRA adapter that
.github/workflows/train-local-model.yml keeps training on posts built from the site's own data (pipeline/corpus.py).

tweet.chat() tries it after every API provider (Gemini, Anthropic, OpenAI, a custom endpoint) has failed, when the
environment has LOCAL_MODEL=1. It runs on the CPU of the machine running the pipeline (a GitHub runner): the first use
in a run installs PyTorch/Transformers/PEFT and downloads the weights (about a minute or two); generation takes seconds.
Its post goes through the same checks as any other (tweet.clean / engage.clean), and the rule-based post stays the last
resort. No API output is used to train it.

The adapter lives on the "model" branch (adapter/), with the training corpus and the evaluation history:
    python -m pipeline.local_model "FORMAT: insider ..."      # write one post locally (needs the deps and an adapter)
"""
import os
import re
import subprocess
import sys

BASE = os.environ.get("LOCAL_BASE_MODEL") or "Qwen/Qwen3-0.6B"
BRANCH = "model"
MAX_CHARS = 1500                   # facts kept from a prompt: short inputs keep CPU training and generation fast
MAX_NEW = 170
INSTRUCTION = ("Write one factual post for X from the facts below. Use only numbers that appear in the facts, keep the "
               "cashtags, finish every sentence, give no advice, and end with the hashtags.")


def enabled():
    return (os.environ.get("LOCAL_MODEL") or "").strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ the prompt (training and inference alike)
SHORT = [  # long production instructions → the same rule in a few words (the facts keep the room)
    (re.compile(r"^THIS POST OPENS A THREAD", re.S), "Opens a thread: start with BREAKING or JUST FILED only if filed within "
     "the last two days (else NEW 10-Q, NEW 10-K or EARNINGS), then the cashtag and quarter; give the most striking fact with "
     "its number; end with “Full breakdown ↓” before the hashtags. Under 250 characters."),
]
LOW = re.compile(r"^(Business, in the company's words|Filing excerpts|Context on the company)")
RULE = re.compile(r"^(THIS POST|Today is|Start |Say |Then |Compare |List |Ask |TASK|Name |Write about)")


def compact(messages):
    """The model's input from the API-style chat messages: the first user turn (the task). Instructions are kept (long
    ones in short form), then the facts in order up to MAX_CHARS — the company description and filing excerpts first to
    go — and the cashtag and hashtag lines at the end."""
    users = [m["content"] for m in messages if m.get("role") == "user"]
    first = users[0] if users else ""
    cash = re.search(r"Cashtags that must appear: ([^\n]+)", first)
    tags = re.search(r"Hashtags to end with, in this order: ([^\n]+)", first)
    body = re.sub(r"\n*(Cashtags that must appear|Other cashtags you may use \(no others\)|Hashtags to end with, in this order):[^\n]*", "", first)
    body = re.sub(r"\s*Write the post now\.?\s*$", "", body).strip()
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    rules, facts = [], []
    for i, b in enumerate(blocks):
        short = next((t for rx, t in SHORT if rx.search(b)), None)
        if short or RULE.match(b):
            rules.append((i, short or b))
        elif not re.search(r"\(not available[^)]*\)\s*$", b):        # an empty "Filing excerpts" says nothing
            facts.append((i, b))
    room = MAX_CHARS - sum(len(r) + 2 for _, r in rules)
    kept = []
    for i, b in sorted(facts, key=lambda ib: (bool(LOW.match(ib[1])), ib[0])):   # low-priority blocks last
        if len(b) > room:
            if LOW.match(b) or room < 160:                             # no stub of a description or excerpt
                continue
            b = b[:room].rsplit("\n", 1)[0] if "\n" in b[:room] else b[:room].rsplit(" ", 1)[0] + " …"
        kept.append((i, b))
        room -= len(b) + 2
    kept = [b for _, b in sorted(kept)] + [r for _, r in rules]
    tail = (f"\nCashtags: {cash.group(1).strip()}" if cash else "") + (f"\nHashtags: {tags.group(1).strip()}" if tags else "")
    return f"{INSTRUCTION}\n\n" + "\n\n".join(kept) + "\n" + tail


# ------------------------------------------------------------------ fact check: no number that is not in the input
_NUM = re.compile(r"(?<![A-Za-z])[-−+]?\$?(\d[\d,]*(?:\.\d+)?)\s*(%|[KMBT]\b|bn\b|million\b|billion\b|thousand\b)?", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12}


def numbers(text):
    """Every number in a text as (value, is_percent), with K/M/B/T scales applied; cashtags and hashtags ignored."""
    text = re.sub(r"[#$][A-Za-z][\w.]*", " ", text)
    out = []
    for m in _NUM.finditer(text):
        v = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        out.append((v, True) if unit == "%" else (v * _SCALE.get(unit, 1), False))
    return out


def unsupported(post, facts):
    """The numbers in the post that the facts do not contain, within rounding ($0.66B = $661M; 12.5% shown as 13%)."""
    have = numbers(facts)
    bad = []
    for v, pct in numbers(post):
        if v == 0:
            continue
        if not any(p == pct and abs(v - w) <= max(0.051 * abs(w), 0.6 if pct else 0.51) for w, p in have):
            bad.append(v)
    return bad


# ------------------------------------------------------------------ dependencies, weights and adapter
def ensure_deps():
    try:
        import peft  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return
    except ImportError:
        pass
    pip = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
    subprocess.run(pip + ["torch>=2.4", "--index-url", "https://download.pytorch.org/whl/cpu"], check=True, timeout=900)
    subprocess.run(pip + ["transformers>=4.51,<5", "peft>=0.15,<1", "accelerate>=1.0", "safetensors"], check=True, timeout=900)


def fetch_adapter(dest):
    """The trained adapter from the "model" branch (GitHub API: works for private repositories with GITHUB_TOKEN), or
    LOCAL_ADAPTER_DIR when set. None when nothing has been promoted yet."""
    local = os.environ.get("LOCAL_ADAPTER_DIR")
    if local:
        return local if os.path.exists(os.path.join(local, "adapter_config.json")) else None
    import requests
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo:
        return None
    h = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})}
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/adapter?ref={BRANCH}", headers=h, timeout=30)
    if r.status_code != 200:
        return None
    os.makedirs(dest, exist_ok=True)
    for f in r.json():
        if f.get("type") != "file":
            continue
        g = requests.get(f["url"], headers={**h, "Accept": "application/vnd.github.raw"}, timeout=120)
        g.raise_for_status()
        with open(os.path.join(dest, f["name"]), "wb") as out:
            out.write(g.content)
    return dest if os.path.exists(os.path.join(dest, "adapter_config.json")) else None


def load(adapter=None, trainable=False):
    """(tokenizer, model) on the CPU: the base model with the adapter (merged for generation, trainable for training)."""
    ensure_deps()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float32)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, is_trainable=trainable)
        if not trainable:
            model = model.merge_and_unload()
    return tok, model


def chat_input(tok, prompt):
    """The tokenized chat prompt (Qwen3 thinking switched off: a short post needs none)."""
    msgs = [{"role": "user", "content": prompt}]
    try:
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    return text


def write(tok, model, prompt, max_new=MAX_NEW):
    import torch
    enc = tok(chat_input(tok, prompt), return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new, do_sample=False, repetition_penalty=1.05,
                             pad_token_id=tok.pad_token_id or tok.eos_token_id)
    text = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


_loaded = None


def generate(messages):
    """tweet.chat()'s local provider. A polish or rewrite turn (the conversation already holds a draft) returns that
    draft unchanged: the small model is not asked to edit."""
    global _loaded
    drafts = [m["content"] for m in messages if m.get("role") == "assistant"]
    if drafts:
        return drafts[-1]
    if _loaded is None:
        adapter = fetch_adapter(os.path.join(os.environ.get("RUNNER_TEMP") or "/tmp", "ff-adapter"))
        if not adapter and not os.environ.get("LOCAL_MODEL_BASE_OK"):
            raise RuntimeError("no trained adapter on the model branch yet")
        _loaded = load(adapter)
    tok, model = _loaded
    return write(tok, model, compact(messages))


if __name__ == "__main__":
    print(generate([{"role": "user", "content": " ".join(sys.argv[1:]) or sys.stdin.read()}]))
