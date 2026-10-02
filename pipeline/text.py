"""The company's own words, without any language model:
- node notes: MD&A paragraphs from the 10-Q/10-K that discuss a line item (matched by heading or phrase)
- company introduction: the opening paragraphs of Item 1 'Business' in the latest 10-K
"""
import re

from bs4 import BeautifulSoup

MAX_NOTE_CHARS = 1400
MAX_INTRO_CHARS = 900


def paragraphs(html_text):
    """Block-level text paragraphs in document order, with a heading flag. Tables are skipped."""
    soup = BeautifulSoup(html_text, "lxml")
    for t in soup.find_all(["table", "script", "style"]):
        t.decompose()
    for hidden in soup.find_all(style=re.compile(r"display:\s*none", re.I)):
        hidden.decompose()
    out = []
    for el in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"]):
        if el.find(["p", "div", "li", "h1", "h2", "h3", "h4"]):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not text or re.fullmatch(r"[\d\s.,()$%—-]*", text):
            continue
        bold = bool(el.find(["b", "strong"])) or bool(re.search(r"font-weight:\s*(bold|[6-9]00)", str(el)[:600], re.I))
        heading = (len(text) <= 90 and not text.endswith((".", ":", ";")) and len(text.split()) <= 12) or \
                  (bold and len(text) <= 120 and not text.endswith("."))
        out.append({"text": text, "heading": heading})
    return out


def section(paras, start_pat, end_pat):
    """Paragraphs between the last heading matching start_pat (skips the table of contents) and end_pat."""
    starts = [i for i, p in enumerate(paras) if re.match(start_pat, p["text"], re.I)]
    if not starts:
        return []
    for s in reversed(starts):
        body = []
        for p in paras[s + 1:]:
            if re.match(end_pat, p["text"], re.I):
                break
            body.append(p)
        if sum(len(p["text"]) for p in body) > 400:
            return body
    return []


def mdna(html_text):
    paras = paragraphs(html_text)
    return section(paras, r"^item\s*[27]\.?\s*(—|-|:)?\s*management", r"^item\s*(3|7a)\.?\s")


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("&amp;", "and").replace("&", "and")).strip()


def match_notes(md, keys, fallback=True):
    """Paragraphs about one node: a matching sub-heading and the text under it, else sentences that name it."""
    if not md or not keys:
        return []
    nk = [_norm(k) for k in keys if k]
    out = []
    heads = [(i, _norm(p["text"])) for i, p in enumerate(md) if p["heading"]]
    tests = (lambda h, k: h == k,
             lambda h, k: h.startswith(k + " ") and len(h) <= len(k) + 25,
             lambda h, k: len(k) > 6 and k in h and len(h) <= len(k) + 25)
    for test in tests:                                   # exact heading first, then looser matches
        for i, h in heads:
            if not any(test(h, k) for k in nk):
                continue
            body, size = [], 0
            for q in md[i + 1:]:
                if q["heading"]:
                    break
                if len(q["text"]) < 40:
                    continue
                body.append(q["text"])
                size += len(q["text"])
                if size > MAX_NOTE_CHARS:
                    break
            if body:
                out.append({"heading": md[i]["text"], "text": _clip("\n\n".join(body), MAX_NOTE_CHARS)})
                break
        if out:
            break
    if out or not fallback:
        return out
    hits = []
    for p in md:
        if p["heading"] or len(p["text"]) < 80:
            continue
        t = _norm(p["text"])
        first = _norm(re.split(r"(?<=\.)\s", p["text"], 1)[0])
        score = sum(2 if k in first else (1 if k in t else 0) for k in nk if len(k) > 3)
        if score:
            hits.append((score, p["text"]))
    hits.sort(key=lambda x: -x[0])
    if hits and hits[0][0] >= 2:
        return [{"heading": None, "text": _clip(hits[0][1], MAX_NOTE_CHARS)}]
    return []


def _clip(text, n):
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(". ", 1)[0]
    return cut + "." if len(cut) > n * 0.5 else text[:n].rsplit(" ", 1)[0] + "…"


def intro(html_text):
    """First substantive paragraphs of Item 1. Business."""
    paras = paragraphs(html_text)
    body = section(paras, r"^item\s*1\.?\s*(—|-|:)?\s*business\b", r"^item\s*1a\.?")
    picked, size = [], 0
    for p in body:
        if p["heading"] or len(p["text"]) < 120:
            continue
        picked.append(p["text"])
        size += len(p["text"])
        if size > MAX_INTRO_CHARS * 0.6 or len(picked) == 2:
            break
    return _clip(" ".join(picked), MAX_INTRO_CHARS) if picked else None
