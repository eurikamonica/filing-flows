"""One LLM-written post per new chart, for the Buffer queue (config/x.json "mode": "buffer").

Order of work for each new quarter, after the scan drew its chart:
  1. the chart images are rendered (pipeline/social.py)
  2. the filing is downloaded from SEC: the earnings release (8-K, Exhibit 99.1) or the 10-Q / 10-K main document
  3. config/tweet-guide.md + the headline figures + filing excerpts go to a model, which writes one post with the hashtags
  4. the post is checked (length, cashtag, hashtags, no advice words); if anything fails, the rule-based headline post
     from pipeline/social.py is used instead, so the queue never stalls on the model

Models: GitHub Models (free with the Actions GITHUB_TOKEN; the job needs `models: read`) unless OPENAI_API_KEY is set.
Repository variables: TWEET_MODEL (default openai/gpt-4.1-mini on GitHub Models, gpt-4.1-mini on OpenAI).
"""
import json
import os
import re

import requests

from . import sec, text as T

GUIDE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "tweet-guide.md")
ADVICE = re.compile(r"\b(buy|sell|bullish|bearish|undervalued|overvalued|moon|crushes|massive|to the moon)\b", re.I)
MAX_DOC = 14_000          # characters of filing text the model sees


def guide():
    try:
        return open(GUIDE, encoding="utf-8").read()
    except FileNotFoundError:
        return "Write one factual post for X about the quarter, under 270 characters, ending with the given hashtags."


# ------------------------------------------------------------------ the filing
def filing_text(q):
    """The most useful part of the filing, as plain text: the press release (8-K) or the MD&A (10-Q/10-K), clipped."""
    url = q.get("doc_url")
    if not url:
        return ""
    try:
        html = sec.get(url)
    except Exception as err:
        print(f"::warning::filing not downloaded for the post ({err}); headline figures only")
        return ""
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    paras = T.paragraphs(html)
    if q.get("form") in ("10-Q", "10-K"):
        md = T.mdna(html)
        if md:
            paras = md
    out, n = [], 0
    for p in paras:
        p = re.sub(r"\s+", " ", p["text"] if isinstance(p, dict) else str(p)).strip()
        if len(p) < 40:
            continue
        out.append(p)
        n += len(p) + 1
        if n > MAX_DOC:
            break
    return "\n".join(out)


def headline_lines(c, q, ticker):
    h = q.get("headline") or {}
    node = {n["id"]: n for n in q.get("nodes", [])}
    m = lambda v: ("—" if v is None else f"${v / 1e9:.1f}B" if abs(v) >= 0.95e9 else f"${v / 1e6:.0f}M" if abs(v) >= 0.95e6 else f"${v / 1e3:.0f}K")
    pc = lambda v: ("—" if v is None else f"{v:+.0f}%")
    om = "—" if h.get("om") is None else f"{h['om']:.1f}%"
    lines = [f"Company: {c['profile']['name']} ({ticker or 'no ticker'})",
             f"Quarter: {q.get('label')} · form {q.get('form')} · period ended {q.get('end')} · filed {q.get('filed')}",
             f"Revenue {m(h.get('revenue'))} · Y/Y {pc(h.get('yoy'))} · operating margin {om}",
             f"Net earnings {m(h.get('ni'))}" + (f" · operating cash flow {m(node['ocf']['v'])}" if node.get("ocf") else "")]
    if q.get("form") == "8-K":
        lines.append("Status: preliminary (8-K earnings release; the 10-Q/10-K follows)")
    for a in (q.get("analysis") or [])[:3]:
        lines.append("Analysis (fixed rules): " + a)
    if q.get("checks"):
        lines.append("Data checks: " + "; ".join(x.get("text", "") for x in q["checks"][:3]))
    return "\n".join(lines)


# ------------------------------------------------------------------ the model
def chat(messages):
    if os.environ.get("OPENAI_API_KEY"):
        url, key = "https://api.openai.com/v1/chat/completions", os.environ["OPENAI_API_KEY"]
        model = os.environ.get("TWEET_MODEL") or "gpt-4.1-mini"
    elif os.environ.get("GITHUB_TOKEN"):
        url, key = "https://models.github.ai/inference/chat/completions", os.environ["GITHUB_TOKEN"]
        model = os.environ.get("TWEET_MODEL") or "openai/gpt-4.1-mini"
    else:
        raise RuntimeError("no model credentials (GITHUB_TOKEN with models: read, or OPENAI_API_KEY)")
    r = requests.post(url, json={"model": model, "messages": messages, "temperature": 0.4, "max_tokens": 200},
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}, timeout=90)
    if r.status_code >= 400:
        raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"].strip()


def clean(post, ticker, tags, xlen, limit=270):
    post = post.strip().strip('"“”').strip()
    post = re.sub(r"\s*\n+\s*", " ", post)
    if ticker and not re.match(r"^(\W*[A-Z0-9][A-Z0-9 \-·:]{0,24}\W+)?\$" + re.escape(ticker.upper()) + r"\b", post.upper()):
        post = f"${ticker} " + post
    present = [t for t in tags if t.lower() in post.lower()]
    if len(present) < len(tags):
        post = re.sub(r"(\s*#\w+)+\s*$", "", post).rstrip()
        post = post + " " + " ".join(tags)
    if ADVICE.search(re.sub(r"#\w+", "", post)):
        raise ValueError("advice / hype wording")
    if xlen(post) > limit:
        raise ValueError(f"too long ({xlen(post)})")
    return post


def holders_lines(ticker, site_url):
    """Who holds / bought the company, from the site's Disclosures index (13F quarter-end changes)."""
    if not (ticker and site_url):
        return ""
    try:
        r = requests.get(f"{site_url.rstrip('/')}/disclosures/data/holders/{ticker}.json", timeout=30)
        if r.status_code != 200:
            return ""
        h = r.json()
    except Exception:
        return ""
    inst = h.get("institutional") or []
    buys = [x for x in inst if x.get("status") in ("NEW", "INCREASE")]
    sells = [x for x in inst if x.get("status") in ("DECREASE", "NOT DISCLOSED")]
    m = lambda v: ("" if v is None else f"${v / 1e9:.1f}B" if abs(v) >= 0.95e9 else f"${v / 1e6:.0f}M")
    row = lambda x: f"- {x.get('manager')} ({x.get('period')}): {x.get('status', '').lower()} {('%+d' % x['delta_shares']) if x.get('delta_shares') else ''} shares, holds {x.get('shares'):,} worth {m(x.get('value_usd'))}, {round((x.get('weight') or 0) * 100, 1)}% of its portfolio"
    lines = [f"13F holders on file for {ticker}: {len(inst)} managers ({len(buys)} added or opened, {len(sells)} cut or closed); quarter-end positions, not trades.",
             "Largest buyers this quarter:"] + [row(x) for x in sorted(buys, key=lambda x: -(x.get('delta_shares') or 0))[:6]]
    lines += ["Largest sellers:"] + [row(x) for x in sorted(sells, key=lambda x: (x.get('delta_shares') or 0))[:4]]
    offs = h.get("officials") or []
    if offs:
        lines.append(f"Public officials' reviewed records naming {ticker}: " + "; ".join(
            f"{o.get('person')} ({o.get('jurisdiction')}) {o.get('kind')} {o.get('transaction_type') or ''} {o.get('date') or ''}".strip() for o in offs[:5]))
    return "\n".join(lines)


def compose_one(c, q, cfg, ticker, hashtags, xlen, kind="post", site_url="", thread=False):
    """One post with hashtags, written by the model from the guide, the figures and the filing (kind "post") or the
    13F holder changes (kind "post_holders"). Raises on failure."""
    tags = list(hashtags)
    if kind == "post_holders":
        holders = holders_lines(ticker, site_url)
        if not holders:
            raise RuntimeError("no holders data on the site for this ticker yet")
        task = ("TASK: this post is about WHO BOUGHT OR SOLD the company according to 13F filings (quarter-end positions), not the "
                "earnings. Name the two or three most notable buyers/sellers with the change in shares; say the period; attach no "
                "earnings figures beyond one line of context. Same rules otherwise (cashtag first, factual, hashtags last).\n\n"
                + holders + "\n\nContext on the company:\n" + headline_lines(c, q, ticker))
    else:
        task = ("Headline figures (source of truth for numbers):\n" + headline_lines(c, q, ticker)
                + "\n\nBusiness, in the company's words:\n" + ((c.get("intro") or {}).get("text", "") if isinstance(c.get("intro"), dict) else str(c.get("intro") or ""))[:1200]
                + "\n\nFiling excerpts:\n" + (filing_text(q) or "(not available; use the headline figures and analysis lines)"))
    if thread:
        task += ("\n\nTHIS POST OPENS A THREAD (the replies carry the business mix, the analysis and the source link), so it is the "
                 "hook: begin with a short attention word before the cashtag — BREAKING, JUST FILED, NEW 10-Q or EARNINGS (pick what "
                 "is true: BREAKING / JUST FILED only when filed within the last two days) — e.g. `BREAKING · $TICK Q3 FY26:`; give the "
                 "single most striking fact with its number; and end, right before the hashtags, with a pointer into the thread "
                 "such as `Full breakdown ↓` or `Charts + what drove it ↓`. One arrow or emoji at most. Still factual, no advice, "
                 "under 250 characters.")
    msgs = [{"role": "system", "content": guide()},
            {"role": "user", "content": task + "\n\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now."}]
    draft = chat(msgs)
    try:
        return clean(draft, ticker, tags, xlen)
    except ValueError as why:
        # one retry with the problem named
        msgs.append({"role": "assistant", "content": draft})
        msgs.append({"role": "user", "content": f"Rewrite: {why}. Keep it under 240 characters, factual, ending with the hashtags."})
        return clean(chat(msgs), ticker, tags, xlen)


def post_for(c, q, cfg, ticker, fallback, xlen, kind="post", site_url="", thread=False):
    """The model's post, or the rule-based headline post when the model is unavailable or its draft fails the checks."""
    tags = [t for t in ([cfg.get("headline_tag", "#earnings")] if kind == "post" else ["#13F"]) + list(cfg.get("hashtags") or []) if t]
    try:
        post = compose_one(c, q, cfg, ticker, tags, xlen, kind=kind, site_url=site_url, thread=thread)
        return post, "model"
    except Exception as err:
        print(f"::warning::model post for {ticker or c['profile'].get('cik')} {q.get('label')} not used ({str(err)[:160]}); rule-based post instead")
        return fallback, "rules"
