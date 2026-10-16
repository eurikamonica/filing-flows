"""One LLM-written post per new chart, for the Buffer queue (config/x.json "mode": "buffer").

Order of work for each new quarter, after the scan drew its chart:
  1. the chart images are rendered (pipeline/social.py)
  2. the filing is downloaded from SEC: the earnings release (8-K, Exhibit 99.1) or the 10-Q / 10-K main document
  3. config/tweet-guide.md + the headline figures + filing excerpts go to a model, which writes one post with the hashtags
  4. the post is checked (length, cashtag, hashtags, no advice words); if anything fails, the rule-based headline post
     from pipeline/social.py is used instead, so the queue never stalls on the model

Model (GitHub Models was retired on 30 Jul 2026): the first of these secrets that is set —
  GEMINI_API_KEY     Google Gemini, free tier (aistudio.google.com → Get API key); model: the newest "flash" model
  ANTHROPIC_API_KEY  Claude (console.anthropic.com); model claude-haiku-5-5
  OPENAI_API_KEY     OpenAI (platform.openai.com); model gpt-4.1-mini
  MODEL_API_URL + MODEL_API_KEY   any OpenAI-compatible chat-completions endpoint (Groq, OpenRouter, Azure…)
Repository variable TWEET_MODEL overrides the model name. Without any of them the rule-based post is used.
"""
import datetime as dt
import json
import os
import re
import time

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


def usd(v):
    """$4.1B, $661M, −$44M (the sign before the dollar)."""
    if v is None:
        return "—"
    a = abs(v)
    s = f"${a / 1e9:.1f}B" if a >= 0.95e9 else f"${a / 1e6:.0f}M" if a >= 0.95e6 else f"${a / 1e3:.0f}K"
    return ("−" if v < 0 else "") + s


def headline_lines(c, q, ticker):
    h = q.get("headline") or {}
    node = {n["id"]: n for n in q.get("nodes", [])}
    m = usd
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
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"
_gemini_models = None


def _gemini_candidates(key):
    """Models to try, best first: the newest stable "flash", the flash aliases, then the lighter flash-lite models (the
    free tier answers 503 "overloaded" for a busy model now and then; the next one usually answers)."""
    global _gemini_models
    if _gemini_models is not None:
        return _gemini_models
    found = []
    try:
        r = requests.get(GEMINI + "models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        ids = [m.get("id", "").split("/")[-1] for m in r.json().get("data", [])]
        ver = lambda i: float(re.search(r"(\d+(?:\.\d+)?)", i).group(1))
        flash = sorted((i for i in ids if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash", i)), key=ver, reverse=True)
        lite = sorted((i for i in ids if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash-lite", i)), key=ver, reverse=True)
        found = flash[:2] + lite[:1]
    except Exception:
        pass
    _gemini_models = list(dict.fromkeys(found + ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]))
    return _gemini_models


def providers():
    """[(name, url, key, [models])] for every configured key, in order of preference."""
    env = os.environ.get
    out = []
    if env("GEMINI_API_KEY"):
        out.append(("gemini", GEMINI + "chat/completions", env("GEMINI_API_KEY"),
                    [env("TWEET_MODEL")] if env("TWEET_MODEL") else _gemini_candidates(env("GEMINI_API_KEY"))))
    if env("ANTHROPIC_API_KEY"):
        out.append(("anthropic", "https://api.anthropic.com/v1/messages", env("ANTHROPIC_API_KEY"), [env("TWEET_MODEL") or "claude-haiku-5-5"]))
    if env("OPENAI_API_KEY"):
        out.append(("openai", "https://api.openai.com/v1/chat/completions", env("OPENAI_API_KEY"), [env("TWEET_MODEL") or "gpt-4.1-mini"]))
    if env("MODEL_API_URL") and env("MODEL_API_KEY"):
        out.append(("custom", env("MODEL_API_URL"), env("MODEL_API_KEY"), [env("TWEET_MODEL") or "gpt-4.1-mini"]))
    from . import local_model
    if local_model.enabled():                 # the free fallback: an open model on this machine's CPU (pipeline/local_model.py)
        out.append(("local", None, None, [local_model.BASE]))
    return out


def provider():
    p = providers()
    return (p[0][0], p[0][1], p[0][2], p[0][3][0]) if p else None


def _ask(name, url, key, model, messages, timeout, max_tokens=1200):
    # thinking models count their reasoning against max_tokens: 400 once cut posts off mid-sentence ("entered a
    # definitive …"), so the budget is generous and a cut-off answer is detected below (chat) and never used
    if name == "anthropic":
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0.4, "system": system,
                "messages": [m for m in messages if m["role"] != "system"]}
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        body = {"model": model, "messages": messages, "temperature": 0.4, "max_tokens": max_tokens}
        if name == "gemini":
            body["reasoning_effort"] = "low"          # a short post needs no long thinking; keeps answers fast
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    r = requests.post(url, json=body, headers=headers, timeout=timeout)
    if r.status_code == 400 and name == "gemini" and "reasoning" in r.text.lower():
        body.pop("reasoning_effort", None)
        r = requests.post(url, json=body, headers=headers, timeout=timeout)
    return r


def chat(messages):
    """One completion. Every configured provider and, for Gemini, several models are tried in turn; busy (429/5xx),
    slow and non-JSON answers move on to the next. The error lists what each one said, so a failing run shows why."""
    ps = providers()
    if not ps:
        raise RuntimeError("no model key: set the secret GEMINI_API_KEY (free), ANTHROPIC_API_KEY or OPENAI_API_KEY "
                           "(GitHub Models was retired on 30 Jul 2026), or LOCAL_MODEL=1 for the local fallback model")
    problems = []
    for name, url, key, models in ps:
        if name == "local":
            from . import local_model
            try:
                content = local_model.generate(messages)
                if content and content.strip():
                    print(f"::notice::post written by the local fallback model ({models[0]})")
                    return content.strip()
                problems.append("local model: empty answer")
            except Exception as err:
                problems.append(f"local model: {str(err)[:120]}")
            continue
        for model in models:
            budget = 1200
            for attempt in range(2):
                try:
                    r = _ask(name, url, key, model, messages, timeout=45, max_tokens=budget)
                except requests.RequestException as err:
                    problems.append(f"{model}: {err.__class__.__name__}")
                    break                                   # slow model: try the next one rather than wait again
                if r.status_code in (429, 500, 502, 503, 504, 529):
                    problems.append(f"{model}: HTTP {r.status_code}")
                    if attempt == 0 and r.status_code == 429:
                        wait = r.headers.get("retry-after")
                        time.sleep(min(20, int(wait)) if wait and wait.isdigit() else 5)
                        continue
                    break
                if r.status_code == 404:
                    problems.append(f"{model}: not available")
                    break
                if r.status_code >= 400:
                    problems.append(f"{model}: HTTP {r.status_code} {r.text[:120]!r}")
                    break
                try:
                    data = r.json()
                except ValueError:
                    problems.append(f"{model}: not JSON ({r.headers.get('content-type')})")
                    break
                if name == "anthropic":
                    content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
                    cut = data.get("stop_reason") == "max_tokens"
                else:
                    choice = (data.get("choices") or [{}])[0]
                    content = (choice.get("message") or {}).get("content")
                    cut = choice.get("finish_reason") == "length"
                if cut:                                     # ran out of tokens: the text stops mid-sentence
                    problems.append(f"{model}: answer cut off at {budget} tokens")
                    if attempt == 0:
                        budget = 4000
                        continue
                    break
                if content and content.strip():
                    return content.strip()
                problems.append(f"{model}: empty answer")
                break
    raise RuntimeError("model unavailable — " + " | ".join(problems[-5:]))


def cut_off(text):
    """True when the post (hashtags aside) stops mid-sentence — a truncated model answer."""
    body = re.sub(r"(\s*#\w+)+\s*$", "", text.strip()).rstrip()
    if len(body) < 40:                     # a lead and a cashtag but nothing said ("JUST FILED · $FNGR Q2 FY2")
        return True
    return bool(body) and not re.search(r"[.!?…:;)\]”\"'↓→⬇👇]$|\d%?$|[\U0001F300-\U0001FAFF]$", body)


def clean(post, ticker, tags, xlen, limit=270):
    post = post.strip().strip('"“”').strip()
    post = re.sub(r"\s*\n+\s*", " ", post)
    if cut_off(post):
        raise ValueError("the post stops mid-sentence; finish the last sentence")
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


HOLDER_TAGS = ["#13F", "#hedgefunds", "#smartmoney", "#stocks", "#investing"]


def holders_json(ticker, site_url):
    if not (ticker and site_url):
        return None
    try:
        r = requests.get(f"{site_url.rstrip('/')}/disclosures/data/holders/{ticker}.json", timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _shares(n):
    a = abs(n)
    return f"{a / 1e6:.1f}M" if a >= 1e6 else f"{a / 1e3:.0f}K" if a >= 1e4 else f"{a:,.0f}"


def _day(s):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
        return f"{d:%b} {d.day}"
    except ValueError:
        return str(s or "")


def holders_thread(ticker, site_url, cik, today=None):
    """The 13F 'who bought it' post without a model: lead, the biggest buyers and sellers with share changes, the
    quarter and the filing dates; replies listing them; a source line. None when the site has no 13F data yet."""
    from . import social
    h = holders_json(ticker, site_url)
    inst = (h or {}).get("institutional") or []
    if not inst:
        return None
    today = today or dt.date.today()
    tk = ticker.replace("-", ".")
    buys = sorted([x for x in inst if x.get("status") in ("NEW", "INCREASE") and x.get("delta_shares")], key=lambda x: -x["delta_shares"])
    sells = sorted([x for x in inst if x.get("status") in ("DECREASE", "EXIT") and x.get("delta_shares")], key=lambda x: x["delta_shares"])
    filed = max((x.get("filed") or "" for x in inst), default="")
    periods = [x.get("period") for x in inst if x.get("period")]
    period = max(set(periods), key=periods.count) if periods else ""
    age = (today - dt.date.fromisoformat(filed[:10])).days if filed else 99
    lead = "BREAKING" if age <= 2 else "JUST FILED" if age <= 10 else "13F"
    who = lambda x: social.display_name(x.get("manager") or "").replace(" Inc", "").strip()[:28]
    move = lambda x: (("opened" if x.get("status") == "NEW" else "added") + f" {_shares(x['delta_shares'])} sh" if x["delta_shares"] > 0
                      else ("sold out of" if x.get("status") == "EXIT" else "cut") + f" {_shares(x['delta_shares'])} sh")
    say = lambda x: f"{who(x)} {move(x)} (filed {_day(x.get('filed'))})"
    bits = [say(x) for x in buys[:1] + sells[:1] + buys[1:2]]        # shortened from the end: biggest buyer and seller stay
    post = (f"{lead}: Who's trading ${tk}? 13F filings for the quarter ended {_day(period)}: " + "; ".join(bits) + ". "
            f"{len(buys)} funds added, {len(sells)} cut. Which side is right?")
    while social.xlen(post) > 225 and len(bits) > 1:
        bits.pop()
        post = (f"{lead}: Who's trading ${tk}? 13F, quarter ended {_day(period)}: " + "; ".join(bits) + ". "
                f"{len(buys)} funds added, {len(sells)} cut. Which side is right?")
    m = lambda v: "" if v is None else f"${v / 1e9:.1f}B" if abs(v) >= 0.95e9 else f"${v / 1e6:.1f}M" if abs(v) >= 0.95e6 else f"${v / 1e3:.0f}K"

    def listing(head, rows):
        out = head
        for x in rows:
            now = "sold out" if x.get("status") == "EXIT" or not x.get("shares") else f"→ {_shares(x['shares'])} ({m(x.get('value_usd'))})"
            line = f"\n· {who(x)}: {'+' if x['delta_shares'] > 0 else '−'}{_shares(x['delta_shares'])} sh {now}, filed {_day(x.get('filed'))}"
            if social.xlen(out + line) > 275:
                break
            out += line
        return out if out != head else ""
    replies = [r for r in (listing(f"Bought or added, quarter ended {_day(period)}:", buys[:6]),
                           listing("Sold or cut:", sells[:6])) if r]
    link = f"{site_url.rstrip('/')}/#c-{cik}" if site_url else ""
    replies.append("Source: 13F-HR filings with the SEC — quarter-end positions, not trades, filed up to 45 days after the quarter. "
                   + (f"Every holder: {link}" if link else "Not investment advice."))
    return {"post": post, "replies": replies, "lead": lead, "period": period, "filed": filed,
            "pieces": {"buys": [(who(x), move(x), _day(x.get("filed"))) for x in buys[:3]],
                       "sells": [(who(x), move(x), _day(x.get("filed"))) for x in sells[:3]],
                       "n_add": len(buys), "n_cut": len(sells), "period": _day(period), "tk": tk}}


def holders_lines(ticker, site_url):
    """Who holds / bought the company, from the site's Disclosures index (13F quarter-end changes)."""
    h = holders_json(ticker, site_url)
    if not h:
        return ""
    inst = h.get("institutional") or []
    buys = [x for x in inst if x.get("status") in ("NEW", "INCREASE")]
    sells = [x for x in inst if x.get("status") in ("DECREASE", "EXIT", "NOT DISCLOSED")]
    m = lambda v: ("" if v is None else f"${v / 1e9:.1f}B" if abs(v) >= 0.95e9 else f"${v / 1e6:.0f}M")
    row = lambda x: f"- {x.get('manager')} (quarter ended {x.get('period')}, 13F filed {x.get('filed')}): {x.get('status', '').lower()} {('%+d' % x['delta_shares']) if x.get('delta_shares') else ''} shares, holds {x.get('shares'):,} worth {m(x.get('value_usd'))}, {round((x.get('weight') or 0) * 100, 1)}% of its portfolio"
    lines = [f"13F holders on file for {ticker}: {len(inst)} managers ({len(buys)} added or opened, {len(sells)} cut or closed); quarter-end positions, not trades.",
             "Largest buyers this quarter:"] + [row(x) for x in sorted(buys, key=lambda x: -(x.get('delta_shares') or 0))[:6]]
    lines += ["Largest sellers:"] + [row(x) for x in sorted(sells, key=lambda x: (x.get('delta_shares') or 0))[:4]]
    offs = h.get("officials") or []
    if offs:
        lines.append(f"Public officials' reviewed records naming {ticker}: " + "; ".join(
            f"{o.get('person')} ({o.get('jurisdiction')}) {o.get('kind')} {o.get('transaction_type') or ''} {o.get('date') or ''}".strip() for o in offs[:5]))
    return "\n".join(lines)


def post_messages(c, q, ticker, tags, kind="post", site_url="", thread=False, filing=True, today=None):
    """The chat messages for one post (see compose_one). Built the same way for the API models, the local fallback
    model and its training examples (pipeline/corpus.py, which passes filing=False: no SEC request per example)."""
    tags = list(tags)
    if kind == "post_trend":
        from . import animate
        task = ("TASK: the attached GIF shows this company's Sankey for each of the last quarters, oldest first. Write about the "
                "two-year TREND (how revenue, margin and earnings moved from the first to the last quarter), using only these "
                "figures:\n" + "\n".join(animate.trend_lines(c)) + "\n\nContext:\n" + headline_lines(c, q, ticker))
    elif kind == "post_holders":
        holders = holders_lines(ticker, site_url)
        if not holders:
            raise RuntimeError("no holders data on the site for this ticker yet")
        th = holders_thread(ticker, site_url, (c.get("profile") or {}).get("cik")) or {}
        lead = th.get("lead", "13F")
        task = ("TASK: this post is about WHO BOUGHT OR SOLD the company according to 13F filings (quarter-end positions), not the "
                f"earnings. Start with “{lead}:” then the cashtag. Name the two or three most notable buyers and sellers by name, "
                "each with the change in shares (and value if it fits), say the quarter the positions are for and when the 13Fs "
                "were filed. Attach no earnings figures. Finish every sentence; end with one short question, then the hashtags. "
                "Same rules otherwise (factual, no advice).\n\n" + holders + "\n\nContext on the company:\n" + headline_lines(c, q, ticker))
    else:
        task = ("Headline figures (source of truth for numbers):\n" + headline_lines(c, q, ticker)
                + "\n\nBusiness, in the company's words:\n" + ((c.get("intro") or {}).get("text", "") if isinstance(c.get("intro"), dict) else str(c.get("intro") or ""))[:1200]
                + "\n\nFiling excerpts:\n" + ((filing_text(q) if filing else "") or "(not available; use the headline figures and analysis lines)"))
    if thread:
        task += f"\n\nToday is {(today or dt.date.today()).isoformat()}."
        task += ("\n\nTHIS POST OPENS A THREAD (the replies carry the business mix, the analysis and the source link), so it is the "
                 "hook: begin with a short attention word before the cashtag — BREAKING, JUST FILED, NEW 10-Q or EARNINGS (pick what "
                 "is true: BREAKING / JUST FILED only when filed within the last two days) — e.g. `BREAKING · $TICK Q3 FY26:`; give the "
                 "single most striking fact with its number; and end, right before the hashtags, with a pointer into the thread "
                 "such as `Full breakdown ↓` or `Charts + what drove it ↓`. One arrow or emoji at most. Still factual, no advice, "
                 "under 250 characters.")
    return [{"role": "system", "content": guide()},
            {"role": "user", "content": task + "\n\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now."}]


def compose_one(c, q, cfg, ticker, hashtags, xlen, kind="post", site_url="", thread=False):
    """One post with hashtags, written by the model from the guide, the figures and the filing (kind "post") or the
    13F holder changes (kind "post_holders"). Raises on failure."""
    tags = list(hashtags)
    msgs = post_messages(c, q, ticker, tags, kind=kind, site_url=site_url, thread=thread)
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
    tags = ([t for t in [cfg.get("headline_tag", "#earnings")] + list(cfg.get("hashtags") or []) if t] if kind in ("post", "post_trend")
            else list(HOLDER_TAGS))
    try:
        post = compose_one(c, q, cfg, ticker, tags, xlen, kind=kind, site_url=site_url, thread=thread)
        return post, "model"
    except Exception as err:
        print(f"::warning::model post for {ticker or c['profile'].get('cik')} {q.get('label')} not used ({str(err)[:160]}); rule-based post instead")
        return fallback, "rules"
