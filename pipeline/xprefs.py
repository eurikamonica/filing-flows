"""The owner's X post options, set on the #owner page ("X posts") and kept in Supabase (owner_settings.x_post), laid
over config/x.json for every run that writes or queues a post: the scan's threads, the owner's "Post to X" buttons,
the engagement and movers posts, and pipeline/buffer.py just before Buffer.

    links         false: no web address in any post (text, cashtags, hashtags and the chart images only)
    gif           false: animated charts go out as still PNG charts
    hashtags_max  hashtags per post, 0-6 (0: none)
    hashtags      the general tags that take turns, one per post
    headline_tag  the tag in the first line of earnings posts ("$NVDA NVIDIA Q2 FY27 #earnings"); "" for none
    tags          which kinds of tag a post may carry: {"kind", "topic", "industry", "general"} (pipeline/hashtags.py)

Read once per run with the service key. Without Supabase, or before supabase/schema.sql is run again (no x_post column
yet), config/x.json alone decides. Only these keys are taken, each checked, so a bad value never reaches a post.
"""
import os
import re

PARTS = ("kind", "topic", "industry", "general")
MAX_TAGS = 6
MAX_POOL = 30
_cache = None


def tag(word):
    w = re.sub(r"[^\w]", "", str(word or "").replace("#", ""), flags=re.ASCII)
    return f"#{w[:40]}" if w and not w.isdigit() else ""


def valid(x):
    """The config/x.json keys these options stand for, from the stored x_post object; anything unknown or malformed
    is left out (config/x.json then decides that key)."""
    out = {}
    if not isinstance(x, dict):
        return out
    if isinstance(x.get("links"), bool):
        out["links"] = x["links"]
    if isinstance(x.get("gif"), bool):
        out["media"] = ["png", "jpg"] + (["gif"] if x["gif"] else [])
    n = x.get("hashtags_max")
    if isinstance(n, (int, float)) and not isinstance(n, bool):
        out["hashtags_max"] = max(0, min(MAX_TAGS, int(n)))
    if isinstance(x.get("hashtags"), list):
        pool = []
        for w in x["hashtags"][:MAX_POOL]:
            t = tag(w)
            if t and t.lower() not in [p.lower() for p in pool]:
                pool.append(t)
        out["hashtags"] = pool
    if isinstance(x.get("headline_tag"), str):
        out["headline_tag"] = tag(x["headline_tag"])
    if isinstance(x.get("tags"), dict):
        parts = {k: x["tags"][k] for k in PARTS if isinstance(x["tags"].get(k), bool)}
        if parts:
            out["hashtag_parts"] = parts
    return out


def env(name):
    """An environment setting as pasted into GitHub, without quotes, spaces or a "NAME = " in front (as notify.setting)."""
    v = os.environ.get(name, "").strip().strip("'\"").strip()
    m = re.match(r"^[A-Z][A-Z0-9_]*\s*[=:]\s*(.*)$", v)
    return m.group(1).strip().strip("'\"").strip() if m else v


def owner_x():
    """The owner's options as config/x.json keys ({} without Supabase or the x_post column); read once per run."""
    global _cache
    if _cache is None:
        _cache = {}
        url, key = env("SUPABASE_URL").rstrip("/"), env("SUPABASE_SERVICE_KEY")
        url = re.sub(r"/(rest|auth)/v1$", "", url)
        if url and key:
            try:
                import requests
                h = {"apikey": key, **({"Authorization": f"Bearer {key}"} if key.startswith("eyJ") else {})}
                r = requests.get(f"{url}/rest/v1/owner_settings", params={"select": "x_post"}, headers=h, timeout=20)
                if r.status_code >= 300:
                    raise RuntimeError(f"Supabase {r.status_code}: {r.text[:200]}")
                rows = r.json()
                _cache = valid(rows[0].get("x_post")) if rows else {}
                if _cache:
                    print("X post options from the owner page: " + ", ".join(f"{k}={v}" for k, v in sorted(_cache.items())))
            except Exception as err:                    # schema.sql not run again yet: config/x.json decides
                print(f"owner X options not read ({str(err)[:120]}); config/x.json decides")
    return _cache


def overlay(cfg):
    """cfg (config/x.json and its defaults) with the owner's options on top."""
    return {**cfg, **owner_x()}
