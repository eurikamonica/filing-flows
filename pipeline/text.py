"""The company's own words, without any language model:
- node notes: MD&A paragraphs from the 10-Q/10-K that discuss a line item (matched by heading or phrase)
- company introduction: the opening paragraphs of Item 1 'Business' in the latest 10-K; for a company without one yet,
  the "About <company>" paragraph of its earnings release (8-K), else Note 1 of its 10-Q ("Description of Business")
"""
import re

from bs4 import BeautifulSoup

MAX_NOTE_CHARS = 1400
MAX_INTRO_CHARS = 900


BOLD = re.compile(r"font-weight:\s*(bold|[6-9]00)", re.I)


def _blocks(html_text):
    """(element, text, heading flag) for every block-level text paragraph in document order. Tables are skipped."""
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
        bold = bool(el.find(["b", "strong"])) or bool(BOLD.search(str(el)[:600]))
        heading = (len(text) <= 90 and not text.endswith((".", ":", ";")) and len(text.split()) <= 12) or \
                  (bold and len(text) <= 120 and not text.endswith("."))
        out.append((el, text, heading))
    return out


def paragraphs(html_text):
    """Block-level text paragraphs in document order, with a heading flag. Tables are skipped."""
    return [{"text": t, "heading": h} for _, t, h in _blocks(html_text)]


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


# ------------------------------------------------------------------ fallbacks for companies without a 10-K yet
NAME_STOP = {"the", "inc", "corp", "corporation", "co", "company", "companies", "holdings", "holding", "group", "plc",
             "ltd", "limited", "sa", "nv", "ag", "se", "llc", "lp", "and", "of", "de", "trust", "bancorp", "class"}


def name_words(names, tickers=()):
    """The words a company goes by: 'MICRON TECHNOLOGY INC' -> {'micron'}, plus its tickers ('mu')."""
    out = set()
    for n in names or ():
        words = [w for w in re.findall(r"[a-z0-9]+", str(n).lower()) if w not in NAME_STOP]
        if words:
            out.add(words[0])
    out.update(str(t).lower().replace("-", " ").split()[0] for t in tickers or () if t)
    return {w for w in out if len(w) >= 2}


def _mentions(text, words):
    t = set(re.findall(r"[a-z0-9]+", text.lower()))
    return bool(t & words)


ABOUT_SKIP = re.compile(r"non-?gaap|forward|conference|webcast|this (press )?release|safe harbor|presentation|"
                        r"reconciliation|the call|risk", re.I)
ABOUT_STOP = re.compile(r"^(forward[- ]looking|cautionary|safe harbor|contacts?\b|media|investor|press contact|source:|"
                        r"about\s|non-?gaap|###|#\s*#|certain statements|statements in this|this (press )?release|"
                        r"to learn more|learn more|for more information|more information|visit\s|©|copyright)|"
                        r"forward-looking statements", re.I)


def about(html_text, names, tickers=()):
    """The "About <Company>" paragraph(s) near the end of an earnings release, or None."""
    words = name_words(names, tickers)
    blocks = _blocks(html_text)
    for i, (el, text, heading) in enumerate(blocks):
        if not re.match(r"about\s", text, re.I):
            continue
        rest = ""
        if len(text) <= 90:
            head = text
        else:                                                # "<b>About NVIDIA</b><br>NVIDIA (NASDAQ: NVDA) is ..."
            b = next((x for x in el.find_all(["b", "strong", "span", "font"])
                      if (x.name in ("b", "strong") or BOLD.search(x.get("style") or ""))
                      and re.match(r"about\s", x.get_text(" ", strip=True), re.I)), None)
            if b is None:
                continue
            head = re.sub(r"\s+", " ", b.get_text(" ", strip=True)).strip()
            if len(head) > 90 or not text.startswith(head):
                continue
            rest = text[len(head):].strip(" :–—-")
        head_words = head.rstrip(".: ")
        if ABOUT_SKIP.search(head_words) or not (_mentions(head_words, words) or re.match(r"about (us|the company)$", head_words, re.I)):
            continue
        parts = [rest] if len(rest) >= 80 else []
        for _, t2, h2 in blocks[i + 1:]:
            if ABOUT_STOP.match(t2) or ABOUT_STOP.search(t2[:400]) and "forward-looking" in t2.lower() or (h2 and len(t2) < 90):
                break
            if len(t2) < 60:
                if parts:
                    break
                continue
            parts.append(t2)
            if len(parts) == 2 or sum(map(len, parts)) > MAX_INTRO_CHARS * 0.7:
                break
        if parts:
            return _clip(" ".join(parts), MAX_INTRO_CHARS)
    return None


NOTE1_START = re.compile(r"^(note\s*)?1\s*[.:)\-–—]?\s*[-–—:]?\s*(?P<title>[a-z].{3,150})$", re.I)
BUSINESS_TITLE = re.compile(r"organi[sz]ation|nature of (the )?(business|operations)|description of (the )?business|"
                            r"\bbusiness\b|overview|background|general", re.I)
BUSINESS_SUB = re.compile(r"^(description of (the )?business|nature of (the )?(business|operations)|organi[sz]ation"
                          r"( and (description of )?business)?|business( description| overview)?|overview|the company|"
                          r"company overview|background)\.?$", re.I)
NOTE1_END = re.compile(r"^(note\s*)?2\s*[.:)\-–—]|^(basis of (presentation|preparation)|principles of consolidation|use of "
                       r"estimates|recent(ly)? (issued|adopted)|fiscal (year|period)|reclassifications?|segment|"
                       r"significant accounting policies|summary of significant)", re.I)
BOILERPLATE = re.compile(r"^(the accompanying|these (unaudited )?(condensed )?(consolidated )?financial|in the opinion of|"
                         r"the (unaudited )?(interim )?(condensed )?consolidated financial|certain (prior|amounts|information)|"
                         r"the results of operations|interim results|this (quarterly )?report)", re.I)


def note1(html_text, names, tickers=()):
    """'Description of Business' from Note 1 to the financial statements of a 10-Q, or None."""
    words = name_words(names, tickers) | {"company", "we"}
    paras = paragraphs(html_text)
    start = next((i for i, p in enumerate(paras) if re.search(r"notes to (the )?(unaudited )?(condensed )?"
                                                               r"(consolidated )?financial statements", p["text"], re.I)), 0)
    for i in range(start, len(paras)):
        m = NOTE1_START.match(paras[i]["text"])
        if not m or len(paras[i]["text"]) > 160:
            continue
        title = m.group("title")
        strict = not BUSINESS_TITLE.search(title)            # "Summary of Significant Accounting Policies": needs a sub-heading
        if strict and not re.search(r"significant accounting policies|basis of presentation", title, re.I):
            continue
        parts, under = [], not strict
        for p in paras[i + 1:]:
            t = p["text"]
            if p["heading"] or len(t) <= 90:
                if BUSINESS_SUB.match(t.strip()):
                    under = True
                    continue
                if NOTE1_END.match(t) or re.match(r"(note\s*)?\d+\s*[.:)\-–—]", t, re.I):
                    break
                if parts:
                    break
                continue
            if not under or BOILERPLATE.match(t) or not _mentions(t, words):
                continue
            parts.append(t)
            if len(parts) == 2 or sum(map(len, parts)) > MAX_INTRO_CHARS * 0.7:
                break
        if parts:
            return _clip(" ".join(parts), MAX_INTRO_CHARS)
        return None
    return None


def intro_cite(intro, short=False):
    """Where a company description was quoted from, for the page, the e-mails and the X thread."""
    if not intro:
        return ""
    src = intro.get("source", "10-K") if isinstance(intro, dict) else "10-K"
    filed = intro.get("filed") if isinstance(intro, dict) else None
    when = f" filed {_fdate(filed)}" if filed else ""
    if src == "8-K":
        return f"earnings release (8-K){when}" if short else f"From the company’s earnings release (8-K){when}, “About” section"
    if src == "10-Q":
        return f"10-Q{when}, Note 1" if short else f"From the company’s 10-Q{when}, Note 1 to the financial statements"
    return f"10-K{when}, Item 1" if short else f"From the company’s 10-K{when}, Item 1. Business"


def _fdate(s):
    import datetime as _dt
    try:
        return _dt.date.fromisoformat(str(s)[:10]).strftime("%b %-d, %Y")
    except ValueError:
        return str(s)
