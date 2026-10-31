"""A registration statement as a reader can use it, from the document itself: the table of contents with a link into the
SEC copy for every section, each section's opening paragraphs and headings, the risk factors (the summary's bullets and
every risk heading), the notes to the financial statements, the principal stockholders table and the share-class
rights table, and the cover facts (the proposed ticker and exchange, the price range once it is filled in).

Source text only: excerpts are cut, never summarized or reworded, and nothing comes from a model. Two document shapes
are read alike: ordinary HTML with a paragraph per element, and "positioned" HTML where every printed line is its own
element (lines are joined back into paragraphs).

    python -m pipeline.ipo_reader prospectus.htm [https://www.sec.gov/Archives/...htm]     # print the reading
"""
import bisect
import json
import re
import sys
import warnings
from collections import Counter

from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:                                   # older bs4
    pass

READER_VERSION = 1
BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "center", "blockquote", "dt", "dd"}
BOLD = re.compile(r"font-weight:\s*(?:bold|[6-9]00)", re.I)
ITALIC = re.compile(r"font-style:\s*italic", re.I)
PAGE = re.compile(r"^(?:[A-Z]{1,2}-)?\d{1,3}$|^[ivxlc]{1,6}$|^Page \d+$", re.I)
BULLET = re.compile(r"^(?:[•●◦▪■□◆∎·–—-]|\(\w{1,3}\)|\d{1,2}\.)\s*")
# a list marker in a cell of its own; not a dash ("—" is a zero) nor "(123)" (a negative figure) nor "(1)" (a footnote)
GLYPH = re.compile(r"^(?:[•●◦▪■□◆∎·]|\((?:[a-z]|[ivx]{1,4})\)|(?:[a-z]|\d{1,2})\.)$", re.I)
FIELD = re.compile(r"^Field: |^(?:\* ?)?MERGEFORMAT|^PAGE \\\*", re.I)
YEARISH = re.compile(r"^(?:\(?unaudited\)?|\(?continued\)?|(?:19|20)\d{2}|as of .{0,40}|(?:year|years|three|six|nine|twelve) "
                     r"months? ended.{0,40}|years? ended.{0,40}|\(in (?:thousands|millions).{0,40})$", re.I)
EXCERPT = 1800                   # characters of a section's opening text
LONG = {"use of proceeds": 4500, "dilution": 2500, "dividend policy": 1500, "capitalization": 2000}
MAX_HEADS = 40
MAX_RISKS = 220
KNOWN = ["prospectus summary", "the offering", "summary consolidated financial", "risk factors", "use of proceeds",
         "dividend policy", "capitalization", "dilution", "management’s discussion and analysis", "management's discussion and analysis",
         "business", "management", "executive compensation", "certain relationships and related", "principal stockholders",
         "principal and selling stockholders", "principal shareholders", "principal and selling shareholders",
         "description of capital stock", "description of share capital", "shares eligible for future sale", "underwriting",
         "legal matters", "experts", "where you can find", "index to consolidated financial statements",
         "index to financial statements", "notes to consolidated financial statements", "notes to financial statements"]


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "")).strip()


def _cut(t, n):
    """The text cut to about n characters at the end of a sentence (else of a word), marked with an ellipsis."""
    if len(t) <= n:
        return t
    head = t[:n]
    end = max(head.rfind(". "), head.rfind("; "))
    return head[:end + 1] + " …" if end > n * 0.5 else head.rsplit(" ", 1)[0] + " …"


def _title(t):
    """'PRINCIPAL AND SELLING STOCKHOLDERS' -> 'Principal and Selling Stockholders'."""
    if t.isupper() and len(t) > 3:
        small = {"and", "of", "the", "to", "for", "in", "on", "a", "an", "or", "by"}
        words = t.lower().split()
        return " ".join(w if (i and w in small) else (w[:1].upper() + w[1:]) for i, w in enumerate(words)).replace("U.s.", "U.S.")
    return t


class Doc:
    """The document as blocks in reading order: [{"t", "b" (bold), "i" (italic), "tbl", "pos"}], and element positions."""

    def __init__(self, soup):
        self.soup = soup
        body = soup.body or soup
        for tag in body(["script", "style", "head", "title"]):
            tag.decompose()
        for tag in body.find_all(style=re.compile(r"display:\s*none", re.I)):
            tag.decompose()
        for tag in body.find_all(re.compile(r"^ix:header$", re.I)):
            tag.decompose()
        self.pos = {}
        for i, el in enumerate(body.descendants):
            if isinstance(el, Tag):
                self.pos[id(el)] = i
        self._style = {}
        blocks, current, key = [], None, None
        for s in body.find_all(string=True):
            if not isinstance(s, NavigableString):
                continue
            blk = s.parent
            while blk is not None and blk.name not in BLOCKS:
                blk = blk.parent
            if blk is None:
                continue
            if not s.strip():                      # the space between two inline elements: kept, never a block
                if key == id(blk) and current["t"]:
                    current["t"].append(" ")
                continue
            b, i = self._styled(s.parent, blk)
            if key != id(blk):
                current = {"t": [], "b": [], "i": [], "tbl": blk.find_parent("table") is not None or blk.name in ("td", "th"),
                           "pos": self.pos.get(id(blk), 0), "el": blk}
                blocks.append(current)
                key = id(blk)
            current["t"].append(str(s))
            current["b"].append(b)
            current["i"].append(i)
        self.blocks = []
        for blk in blocks:
            text = _clean("".join(blk["t"]))
            if not text:
                continue
            self.blocks.append({"t": text, "b": all(blk["b"]), "i": all(blk["i"]), "tbl": blk["tbl"], "pos": blk["pos"],
                                "el": blk["el"]})
        self.by_el = {id(b["el"]): b for b in self.blocks}
        counts = Counter(b["t"] for b in self.blocks if len(b["t"]) <= 90)
        self.running = {t for t, n in counts.items() if n >= 6}            # page headers and footers
        body_lens = sorted(len(b["t"]) for b in self.blocks if not b["b"] and not b["tbl"] and len(b["t"]) > 20)
        self.median = body_lens[len(body_lens) // 2] if body_lens else 200
        self.lines_mode = self.median < 125                                 # every printed line is an element

    def _styled(self, el, blk):
        """(bold, italic) of a text node, from its elements up to its block."""
        b = i = False
        node = el
        while node is not None:
            k = id(node)
            if k not in self._style:
                st = node.get("style", "") if isinstance(node, Tag) else ""
                self._style[k] = (node.name in ("b", "strong", "h1", "h2", "h3", "h4") or bool(BOLD.search(st)),
                                  node.name in ("i", "em") or bool(ITALIC.search(st)))
            sb, si = self._style[k]
            b, i = b or sb, i or si
            if node is blk:
                break
            node = node.parent
        return b, i

    def noise(self, blk):
        t = blk["t"]
        return (PAGE.match(t) is not None or t.lower() in ("table of contents", "back to contents", "index") or t in self.running
                or FIELD.match(t) is not None)

    def start(self, target):
        """Where a section begins: the anchor, or the short block (its heading) that holds an inline anchor."""
        pos = self.pos.get(id(target), 0)
        if target.name in BLOCKS:
            return pos
        node = target.parent
        while node is not None and node.name not in BLOCKS:
            node = node.parent
        if node is not None:
            blk = self.by_el.get(id(node))
            if blk is not None and len(blk["t"]) < 300:
                return min(pos, blk["pos"])
        return pos


def toc(doc):
    """[(title, anchor, page, pos)] from the document's own table of contents links, in document order."""
    soup = doc.soup
    by_href = {}
    order = []
    for a in soup.find_all("a", href=re.compile(r"^#.+")):
        href = a["href"][1:]
        t = _clean(a.get_text(" "))
        if not t:
            continue
        if href not in by_href:
            by_href[href] = {"title": [], "page": None}
            order.append(href)
        e = by_href[href]
        if re.fullmatch(r"(?:[A-Z]{1,2}-)?\d{1,3}|[ivxlc]{1,6}", t, re.I):
            e["page"] = e["page"] or t
        elif t.lower() not in ("table of contents", "table of", "contents", "back to contents", "index") and len(t) < 160:
            if t.lower() not in (x.lower() for x in e["title"]) and not any(t.lower() in x.lower() for x in e["title"]):
                e["title"].append(t)
    out = []
    for href in order:
        e = by_href[href]
        if not e["title"]:
            continue
        target = soup.find(id=href) or soup.find("a", attrs={"name": href})
        if target is None:
            continue
        title = _clean(" ".join(e["title"]))
        if len(title) > 150 or re.match(r"^(?:see|refer to)\b", title, re.I):
            continue
        out.append((_title(title), href, e["page"], doc.start(target)))
    out.sort(key=lambda x: x[3])
    seen, uniq = set(), []
    for x in out:                                    # one entry per place in the document
        if x[3] in seen:
            continue
        seen.add(x[3])
        uniq.append(x)
    return uniq


def headings_fallback(doc):
    """Section starts when the document has no linked table of contents: bold lines naming a usual section, the
    occurrence with the most text after it (the table of contents lists them too, with nothing after)."""
    found = {}
    bold = [(k, b) for k, b in enumerate(doc.blocks) if b["b"] and not b["tbl"] and len(b["t"]) < 120]
    for idx, (k, b) in enumerate(bold):
        low = b["t"].lower().strip(" .:")
        name = next((n for n in KNOWN if low == n or (low.startswith(n) and len(low) - len(n) < 25)), None)
        if not name:
            continue
        nxt = bold[idx + 1][0] if idx + 1 < len(bold) else len(doc.blocks)
        size = sum(len(x["t"]) for x in doc.blocks[k + 1:nxt])
        if size > found.get(name, (0, None))[0]:
            found[name] = (size, (_title(b["t"]), None, None, b["pos"]))
    return sorted((v[1] for v in found.values()), key=lambda x: x[3])


def paragraphs(doc, blocks):
    """Blocks -> [("h", heading) | ("p", paragraph)], lines joined back into paragraphs in a positioned document."""
    out = []
    typical = doc.median
    prev_len, prev_head, glyph = 0, None, False
    for b in blocks:
        t = b["t"]
        if b["tbl"] and GLYPH.match(t):                    # a bullet drawn in its own cell (repeats, so not noise)
            glyph = True
            continue
        if doc.noise(b):
            continue
        if b["tbl"]:                                       # a table cell: kept only as the text of a bulleted row
            if glyph or (BULLET.match(t) and len(t) > 30 and not re.match(r"^[\d(]", t)):
                out.append(("p", "• " + (t if glyph else BULLET.sub("", t))))
                prev_len, prev_head, glyph = len(t), None, False
            else:
                glyph = False
            continue
        glyph = False
        if b["b"] and len(t) < 400 and not YEARISH.match(t):
            if (out and out[-1][0] == "h" and doc.lines_mode and prev_head is not None and prev_head["i"] == b["i"]
                    and not re.search(r"[.:]$", out[-1][1])
                    and (len(prev_head["t"]) >= 0.75 * typical or t[:1].islower()
                         or re.search(r"(?:\b(?:and|of|to|the|for|in|on|or|by|with|a|an)|[,&\-–])$", prev_head["t"]))):
                out[-1] = ("h", out[-1][1] + " " + t)            # a heading printed on two lines
            else:
                out.append(("h", t))
            prev_head = b
            prev_len = 0
            continue
        prev_head = None
        if b["b"]:
            continue
        starts = BULLET.match(t) is not None
        if doc.lines_mode and out and out[-1][0] == "p" and not starts:
            last = out[-1][1]
            ended = re.search(r"[.:;?!”\"]$", last) and prev_len < 0.8 * typical and t[:1].isupper()
            if not ended:
                out[-1] = ("p", last + " " + t)
                prev_len = len(t)
                continue
        out.append(("p", t))
        prev_len = len(t)
    return out


def _table(el, max_rows=45, max_cols=14):
    """The table as printed: [[cell, ...]], a cell being its text, or [text, columns] when it spans columns. The spacer
    columns EDGAR tables are full of are dropped, and a "$" joins the number after it and a "%" or ")" the one before,
    so the columns line up as on the page."""
    grid = []                                             # rows of [text, span]
    for tr in el.find_all("tr"):
        row = []
        for c in tr.find_all(["td", "th"]):
            try:
                span = max(1, min(int(c.get("colspan") or 1), 40))
            except ValueError:
                span = 1
            row.append([_clean(c.get_text(" "))[:160], span])
        for i, cell in enumerate(row):                  # a figure split over cells: "$" | "1,234" | ")" | "%"
            if cell[0] in ("$", "(", "$("):
                j = next((k for k in range(i + 1, len(row)) if row[k][0]), None)
                if j is not None and re.match(r"^[\d(.]", row[j][0]):
                    row[j][0], cell[0] = cell[0] + row[j][0], ""
            elif cell[0] in ("%", ")", ")%", "%)"):
                j = next((k for k in range(i - 1, -1, -1) if row[k][0]), None)
                if j is not None and re.search(r"[\d)]$", row[j][0]):
                    row[j][0], cell[0] = row[j][0] + cell[0], ""
        if any(t for t, _ in row):
            grid.append(row)
        if len(grid) >= max_rows:
            break
    used = set()                                          # columns with text in a cell of their own
    for row in grid:
        col = 0
        for t, span in row:
            if t and span == 1:
                used.add(col)
            col += span
    out = []
    for row in grid:
        col, cells = 0, []
        for t, span in row:
            cover = [c for c in range(col, col + span) if c in used]
            if cover:
                cells.append(t if len(cover) == 1 else [t, len(cover)])
            elif t and span > 1:                          # a heading over spacer columns only: kept, one column
                cells.append(t)
            col += span
        cells = cells[:max_cols]
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            out.append(cells)
    return out


def cover(text):
    """Proposed ticker and exchange, price range and share counts as the cover states them (blank in a first filing)."""
    head = text[:60000]
    out = {}
    m = re.search(r"under the (?:trading )?symbols?\s*[“\"'‘]([A-Z][A-Z.\-]{0,6})[”\"'’]", head)
    if m:
        out["symbol"] = m.group(1).rstrip(".-")
    m = re.search(r"(Nasdaq Global Select Market|Nasdaq Global Market|Nasdaq Capital Market|New York Stock Exchange|NYSE American|"
                  r"NYSE Texas|NYSE Arca|Cboe BZX)", head)
    if m:
        out["exchange"] = m.group(1)
    m = re.search(r"between \$\s?(\d{1,4}(?:\.\d{1,2})?) and \$\s?(\d{1,4}(?:\.\d{1,2})?) per share", head)
    if m:
        out["range"] = [float(m.group(1)), float(m.group(2))]
    m = re.search(r"(?:offering|offer(?:ing)? to sell)\s+([\d,]{5,}) shares of (?:our )?(Class [A-Z] )?(?:common stock|ordinary shares)", head)
    if m:
        out["shares"] = int(m.group(1).replace(",", ""))
    flags = []
    if re.search(r"emerging growth company", head, re.I):
        flags.append("emerging growth company")
    if re.search(r"public benefit corporation", head, re.I):
        flags.append("public benefit corporation")
    if re.search(r"controlled company", head, re.I):
        flags.append("controlled company")
    if len(set(re.findall(r"\bClass ([A-Z]) (?:common stock|ordinary shares)", head))) >= 2:
        flags.append("multiple share classes")
    if re.search(r"blank check company|special purpose acquisition", head, re.I):
        flags.append("blank check company (SPAC)")
    if flags:
        out["flags"] = flags
    return out


NOTES_TO = re.compile(r"(?:[\w.,&’' -]{0,80}\s)?notes to (?:the )?(?:condensed )?(?:consolidated )?(?:combined )?"
                      r"(?:condensed )?(?:interim )?financial statements")
NOTE_HEAD = re.compile(r"^(?:note\s+(\d{1,2})\s*[.:—–-]?|(\d{1,2})\s*[.:—–-])\s*(.+)$", re.I)
CONT = re.compile(r"\s*[(\[]?\b(?:cont(?:inued|’d|'d)?\.?)[)\]]?\s*$", re.I)


def read_notes(doc, paras):
    """[{"n", "title", "text", "topics"}] from the paragraphs of the notes to the financial statements: one entry per
    note number (a note continued over pages is one note), the opening text and the subheadings as topics."""
    notes, cur = [], None
    for kind, t in paras:
        m = NOTE_HEAD.match(t) if kind == "h" else None
        if m and len(m.group(3)) > 3 and not re.match(r"^\d", m.group(3)):
            n = int(m.group(1) or m.group(2))
            title = CONT.sub("", m.group(3)).strip(" .:—–-")
            if notes and n == notes[-1]["n"]:
                cur = notes[-1]                                  # the same note, continued
                continue
            if notes and n < notes[-1]["n"]:
                break                                            # a second set of notes (the interim statements)
            cur = {"n": n, "title": title[:160], "text": [], "topics": []}
            notes.append(cur)
        elif cur is not None:
            if kind == "h" and len(t) < 120 and not NOTES_TO.match(t.lower()) and not CONT.fullmatch(t):
                t = CONT.sub("", t)
                if t and t not in cur["topics"] and t != cur["title"]:
                    cur["topics"].append(t)
            elif kind == "p" and sum(len(x) for x in cur["text"]) < 700:
                cur["text"].append(t[:900])
    for nt in notes:
        nt["topics"] = nt["topics"][:12]
    return notes


def _comparison(md, months, end):
    """The MD&A paragraphs comparing the period ending `end` with a year earlier ("Comparison of the Six Months Ended
    June 30, 2025 and 2026"), up to the next comparison or the next part of the MD&A; None when there is none."""
    span = {3: "three months", 6: "six months", 9: "nine months", 12: "(?:fiscal )?years?"}.get(months)
    if not span:
        return None
    y = int(end[:4])
    pat = re.compile(rf"^comparison of (?:the )?{span} ended\b.*\b{y - 1}\b.*\b{y}\b", re.I)
    start = next((i for i, p in enumerate(md) if p["heading"] and pat.match(p["text"])), None)
    if start is None:
        return None
    stop = next((i for i in range(start + 1, len(md)) if md[i]["heading"]
                 and re.match(r"^(?:comparison of|non-gaap|liquidity|quarterly results|key (?:business )?metrics)", md[i]["text"], re.I)),
                len(md))
    return md[start + 1:stop]


def node_notes(paras, keys, periods=()):
    """{period key or "*": {line key: [{"heading", "text"}]}}: what the MD&A says about each chart line (pipeline/text.py
    match_notes), quoted. For a period, the passage of the MD&A that compares it with a year earlier ("Compute and
    infrastructure expenses increased ... primarily due to ..."); "*" for the rest (a heading of the line's name)."""
    from .text import match_notes
    md = [{"text": t, "heading": kind == "h"} for kind, t in paras]
    out = {}
    base = {k: m for k, words in keys.items() if (m := match_notes(md, words, fallback=False))}
    if base:
        out["*"] = base
    for pkey, months, end in periods:
        sub = _comparison(md, months, end)
        if sub:
            got = {k: m for k, words in keys.items() if (m := match_notes(sub, words, fallback=True))}
            if got:
                out[pkey] = got
    return out


def read(html_or_soup, source_url=None, note_keys=None, periods=()):
    """{"v", "sections", "risks": {"summary", "groups", "count"}, "notes", "holders", "classes", "cover"} of one
    document; with note_keys ({line key: words}) also "node_notes", the MD&A passages about each line, per period
    ([(period key, months, end date)]) where the MD&A compares that period with a year earlier."""
    soup = html_or_soup if isinstance(html_or_soup, BeautifulSoup) else BeautifulSoup(html_or_soup, "lxml")
    doc = Doc(soup)
    starts = toc(doc)
    how = "toc"
    if len(starts) < 4:
        starts, how = headings_fallback(doc), "headings"
    poss = [s[3] for s in starts]
    by_section = [[] for _ in starts]
    for b in doc.blocks:
        k = bisect.bisect_right(poss, b["pos"]) - 1
        if k >= 0:
            by_section[k].append(b)
    sections, risks, notes, holders, classes, fs_paras, mdna = [], {}, [], None, None, [], None
    for (title, anchor, page, _), blocks in zip(starts, by_section):
        paras = paragraphs(doc, blocks)
        low = title.lower()
        if paras and paras[0][0] == "h" and paras[0][1].lower().strip(" .") in (low, low.replace("’", "'")):
            paras = paras[1:]                                     # the section's own heading
        limit = next((v for k, v in LONG.items() if low.startswith(k)), EXCERPT)
        text, n = [], 0
        for kind, t in paras:
            if kind == "p" and n < limit:
                text.append(_cut(t, limit - n + 200) if n + len(t) > limit + 200 else t)
                n += len(t)
        heads = [t[:220] for kind, t in paras if kind == "h"]
        words = sum(len(b["t"].split()) for b in blocks if not b["tbl"])
        sec = {"title": title, **({"anchor": anchor} if anchor else {}), **({"page": page} if page else {}),
               "words": words, "text": text}
        if heads and not low.startswith("risk factors"):
            sec["heads"] = heads[:MAX_HEADS]
        sections.append(sec)
        if low.startswith("prospectus summary") or low == "summary":
            bullets, on = [], False
            for kind, t in paras:
                if kind == "h":
                    on = "risk" in t.lower()
                    if bullets and not on:
                        break
                elif on and BULLET.match(t):
                    bullets.append(BULLET.sub("", t)[:400])
            if bullets:
                risks["summary"] = bullets[:40]
        if low.startswith("risk factors"):
            groups, cur = [], None
            for kind, t in paras:
                if kind != "h":
                    continue
                if re.match(r"^risks? (?:related|relating) to|^general risk", t, re.I) and len(t) < 160:
                    cur = {"group": t, "items": []}
                    groups.append(cur)
                elif len(t) > 40:
                    if cur is None:
                        cur = {"group": "Risks", "items": []}
                        groups.append(cur)
                    cur["items"].append(t[:320])
            total = 0
            for g in groups:
                g["items"] = g["items"][:max(0, MAX_RISKS - total)]
                total += len(g["items"])
            risks["groups"] = [g for g in groups if g["items"]]
            risks["count"] = sum(len(g["items"]) for g in groups)
        if not notes and NOTES_TO.match(low):
            notes = read_notes(doc, paras)
        elif re.search(r"financial statements", low):
            fs_paras.append(paras)
        if note_keys and mdna is None and re.match(r"management[’']s discussion and analysis", low):
            mdna = node_notes(paras, note_keys, periods)
        if holders is None and re.search(r"principal (?:and selling )?(?:stock|share)holders|security ownership", low):
            for b in blocks:
                if b["tbl"] and re.search(r"beneficial", b["t"], re.I):
                    t = b["el"].find_parent("table")
                    if t is not None:
                        rows = _table(t)
                        if len(rows) >= 4:
                            holders = rows
                            break
        if classes is None and re.search(r"description of (?:capital stock|share capital|securities)", low):
            for b in blocks:
                if b["tbl"] and re.search(r"votes? per share", b["t"], re.I):
                    t = b["el"].find_parent("table")
                    if t is not None:
                        classes = _table(t, 14, 7)
                        break
    if not notes:                       # no contents entry for the notes: find their heading in the financial pages
        for paras in fs_paras:
            k = next((i for i, (kind, t) in enumerate(paras) if kind == "h" and NOTES_TO.match(t.lower())), None)
            if k is not None:
                notes = read_notes(doc, paras[k + 1:])
                if notes:
                    break
    text = " ".join(b["t"] for b in doc.blocks[:4000])
    out = {"v": READER_VERSION, "how": how, "lines": doc.lines_mode, "sections": sections, "cover": cover(text)}
    if source_url:
        out["url"] = source_url
    if risks:
        out["risks"] = risks
    if notes:
        out["notes"] = notes[:40]
    if holders:
        out["holders"] = holders
    if classes:
        out["classes"] = classes
    if mdna:
        out["node_notes"] = mdna
    return out


if __name__ == "__main__":
    html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    print(json.dumps(read(html, sys.argv[2] if len(sys.argv) > 2 else None), indent=1, ensure_ascii=False)[:20000])
