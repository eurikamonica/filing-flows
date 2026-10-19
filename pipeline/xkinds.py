"""X post kinds added by feature modules, without edits elsewhere.

A feature module is a file pipeline/posts_<name>.py. Each of its plan functions is registered with @kind(...) and is then
picked up by:
  - pipeline/engage.py: the dispatch (python -m pipeline.engage --kinds <name>), the per-format cooldown, the hashtags,
    the writing guide (the system prompt), and the schedule tokens of .github/workflows/engage.yml (--kinds @close …)
  - the owner's buttons (Owner tools → "Write a post now": scripts/build_site.py writes the list into the page)
  - the owner's requests (send_requests kind "engage_<name>": pipeline/notify.py, supabase/schema.sql accept any engage_*)
  - the training corpus of the local models (pipeline/corpus.py market_examples: every rule-written phrasing a target)

A plan function has the engage plan signature (site, rows, c, by_ticker, state_ok, today) and returns None or a plan
dict: kind, task, cashtags, items (charts, may be []), fallback (+ optional fallbacks, allowed, must, forbid, lines, tags).

    from .xkinds import kind

    @kind("health_scores", tag="quality", hashtags=["#Piotroski", "#QualityStocks"], schedule=["close"],
          label="✦ Financial health", title="Companies with a perfect Piotroski F-score this quarter",
          guide="List 3–5 cashtags with their F-score; say what the score measures in a few words.")
    def plan_health_scores(site, rows, c, by_ticker, state_ok, today):
        ...
"""
import importlib
import os
import pkgutil
import re

REG = {}
SLOTS = ("morning", "close", "evening", "weekly", "events")   # the engage workflow's schedules (see engage.yml)
_loaded = False


def kind(name, *, tag, hashtags=None, cooldown=20, schedule=None, label=None, title="", guide="", corpus=5, button=True):
    """Register a plan. tag: the hashtag pool (pipeline/hashtags.py KINDS; `hashtags` creates it when new);
    cooldown: hours between two posts of this format; schedule: engage.yml slots that run it (SLOTS);
    label / title: the owner's button; guide: a paragraph for the writing guide; corpus: plans a day for training."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name):
        raise ValueError(f"post kind name {name!r}: lowercase letters, digits and _")
    bad = [s for s in schedule or [] if s not in SLOTS]
    if bad:
        raise ValueError(f"post kind {name}: unknown schedule {bad} (one of {SLOTS})")

    def deco(f):
        REG[name] = {"plan": f, "tag": tag, "hashtags": list(hashtags or []), "cooldown": cooldown, "schedule": list(schedule or []),
                     "label": label or "✦ " + name.replace("_", " ").capitalize(), "title": title, "guide": guide.strip(),
                     "corpus": int(corpus), "button": bool(button), "module": f.__module__}
        return f
    return deco


def load():
    """Import every pipeline/posts_*.py once (each registers its kinds); returns the registry. A module that fails to
    import is reported and skipped, so one broken feature never stops the others."""
    global _loaded
    if not _loaded:
        _loaded = True
        here = os.path.dirname(__file__)
        for m in sorted(pkgutil.iter_modules([here]), key=lambda m: m.name):
            if m.name.startswith("posts_"):
                try:
                    importlib.import_module(f"{__package__}.{m.name}")
                except Exception as err:                       # noqa: BLE001 — a broken module must not stop the rest
                    print(f"::warning::post kinds in pipeline/{m.name}.py not loaded ({str(err)[:200]})")
        try:
            from . import hashtags as H
            for k in REG.values():
                if k["hashtags"]:
                    H.KINDS.setdefault(k["tag"], k["hashtags"])
        except Exception:
            pass
    return REG


def get(name):
    return load().get(name)


def expand(kinds):
    """The workflow's kind list with its schedule tokens ("@close") replaced by the registered kinds of that slot."""
    out = []
    for k in kinds:
        if k.startswith("@"):
            out += [n for n, v in sorted(load().items()) if k[1:] in v["schedule"] and n not in out]
        elif k not in out:
            out.append(k)
    return out


def guide_text():
    """The registered kinds' paragraphs for the writing guide."""
    parts = [f"## {n}\n{v['guide']}" for n, v in sorted(load().items()) if v["guide"]]
    return ("\n\n# More formats\n\n" + "\n\n".join(parts)) if parts else ""


def buttons():
    """The owner's buttons for the registered kinds: [{kind: "engage_<name>", label, title}]."""
    return [{"kind": "engage_" + n, "label": v["label"], "title": v["title"]} for n, v in sorted(load().items()) if v["button"]]
