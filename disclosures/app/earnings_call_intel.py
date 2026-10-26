"""Conservative issuer-IR link discovery and evidence-labeled call intelligence.

Only verified issuer-host HTML transcripts reach text analytics. No generic
web search, aggressive crawling, invented guidance, or copyrighted full-text
redistribution. Original text stays in private collection artifacts.
"""
from collections import Counter
from decimal import Decimal
from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import urljoin, urlparse

HEADING = re.compile(r"(?m)^\s*Transcript\s*$", re.I)
SPEAKER = re.compile(r"(?m)^([A-Z][A-Z .,'-]{4,65}):\s*$")
RANGE = re.compile(
    r"(?:between|range\s+of|ranging\s+from)\s+\$?"
    r"(?P<low>\d+(?:\.\d+)?)\s*(?P<unit1>billion|million|%)?"
    r"\s*(?:and|to|[-–])\s*\$?(?P<high>\d+(?:\.\d+)?)"
    r"\s*(?P<unit2>billion|million|%)(?=\s|[.,;)]|$)", re.I)
MONEY_UNITS = {"billion": "USD billions", "million": "USD millions", "%": "percent"}
TOPICS = {
    "revenue": r"\b(revenue|sales|top.line|cloud revenue)\b",
    "capex": r"\b(capital expenditures?|capex|capital spending)\b",
    "operating_margin": r"\b(operating margin|operating income margin)\b",
    "gross_margin": r"\b(gross margin)\b",
    "operating_income": r"\b(operating income|operating profit)\b",
    "expenses": r"\b(expenses?|operating costs?)\b",
    "demand": r"\b(demand|backlog|bookings?|capacity)\b",
    "AI_infrastructure": r"\b(AI|GPU|datacenter|data center|compute)\b",
    "pricing": r"\b(pricing|ASP|average selling price|price per)\b",
    "cash_flow": r"\b(free cash flow|operating cash flow|cash conversion)\b",
}
FORECAST = re.compile(r"\b(we (?:now )?(?:expect|anticipate|forecast|project|guide)|"
                      r"our (?:outlook|guidance)|we are guiding|we expect|expected to be)\b", re.I)
HORIZON_Q = re.compile(r"\b(?:Q([1-4])|(?:first|second|third|fourth) quarter)\s*(?:FY\s*)?(\d{4})\b", re.I)
HORIZON_FY = re.compile(r"\b(?:full.year|fiscal year|FY)\s*(\d{4})\b", re.I)
QUARTERS = {"first": "1", "second": "2", "third": "3", "fourth": "4"}
LINK_WORDS = re.compile(r"(earnings|results|investor events?|transcript|webcast|conference call)", re.I)
NO_LINK = re.compile(r"(press release|10-[qk]|slide deck|annual report|financial statements)", re.I)


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href = None
        self.label = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.href is not None:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.label).strip()))
            self.href = None
            self.label = []


def trusted(url, hosts):
    p = urlparse(url)
    return (p.scheme == "https" and p.hostname in set(hosts) and p.port in (None, 443)
            and not p.username and not p.password and not p.fragment
            and len(url) < 1500)


def discover_links(page_url, html, hosts, limit=8):
    """Find bounded, same-allowlist official links; discovery != verification."""
    p = Anchors()
    p.feed(html.decode("utf-8", "replace"))
    result, seen = [], set()
    for href, label in p.links:
        url = urljoin(page_url, href).split("#", 1)[0]
        if url in seen or url == page_url or not trusted(url, hosts):
            continue
        relevant = label + " " + url
        if not LINK_WORDS.search(relevant) or NO_LINK.search(label):
            continue
        low = relevant.lower()
        kind = ("transcript_pdf_candidate" if ".pdf" in urlparse(url).path.lower() and "transcript" in low
                else "transcript_html_candidate" if "transcript" in low
                else "event_or_webcast_candidate")
        result.append({"url": url, "label": label[:110], "kind": kind})
        seen.add(url)
        if len(result) >= limit:
            break
    return result


def visible_html(html):
    """Use existing text extraction utility, imported lazily to avoid cycles."""
    from earnings_calls import VisibleText
    parser = VisibleText()
    parser.feed(html.decode("utf-8", "replace"))
    return parser.text()


def split_turns(html):
    text = visible_html(html)
    m = HEADING.search(text)
    if not m:
        return []
    section = text[m.end():]
    markers = list(SPEAKER.finditer(section))
    if len({x.group(1) for x in markers}) < 2 or len(section) < 1500:
        return []
    turns = []
    qa = False
    for i, match in enumerate(markers):
        before = section[:match.start()] if i == 0 else section[markers[i-1].end():match.start()]
        if re.search(r"question[s]?\s+and\s+answer|Q\s*&\s*A|open\s+(?:the\s+)?(?:line|call)\s+for\s+questions",
                     before[-250:], re.I):
            qa = True
        name = match.group(1).strip()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(section)
        body = section[match.end():end].strip()
        if "OPERATOR" in name:
            qa = True
        if len(body) > 10:
            turns.append({"speaker": name, "text": body, "qa_section": qa,
                          "turn": len(turns) + 1})
    return turns


def category(text):
    for name, pattern in TOPICS.items():
        if re.search(pattern, text, re.I):
            return name
    return "other"


def horizon(text):
    m = HORIZON_Q.search(text)
    if m:
        q = m.group(1) or next((val for name, val in QUARTERS.items()
                                 if re.search(r"\b" + name + r" quarter\b", m.group(0), re.I)), None)
        if q:
            return f"Q{q} {m.group(2)}"
    m = HORIZON_FY.search(text)
    return "FY" + m.group(1) if m else "unspecified"


def guidance_and_questions(turns, ticker, management=()):
    """Extract only unambiguous forward-looking NUMBER RANGES by management.

    Do not treat historical results, sales targets, approximate numbers, or
    analyst hypotheses as SEC-verified earnings guidance.
    """
    named = {x.upper() for x in management}
    seen, guidance, exercises, analyst_topics = set(), [], [], Counter()
    observed_analysts = []
    for turn in turns:
        speaker = turn["speaker"].upper()
        in_management = speaker in named or (not named and not turn["qa_section"] and speaker != "OPERATOR")
        if turn["qa_section"] and not in_management and speaker != "OPERATOR":
            if "?" in turn["text"] or len(turn["text"]) > 75:
                topic = category(turn["text"])
                analyst_topics[topic] += 1
                observed_analysts.append({
                    "speaker": turn["speaker"], "topic": topic, "turn": turn["turn"],
                    "source_sha256": hashlib.sha256(turn["text"].encode()).hexdigest(),
                    "question_prompt": f"What did analysts ask management about {topic.replace('_', ' ')}?",
                    "type": "paraphrased_topic_question", "confidence": "heuristic",
                })
        if not in_management:
            continue
        # Analyze at most individual sentences, including ranges in nearby clauses.
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", turn["text"])
        for sentence in sentences:
            if len(sentence) > 520:
                continue
            if not FORECAST.search(sentence):
                continue
            r = RANGE.search(sentence)
            if not r:
                continue
            c = category(sentence)
            if c not in {"revenue", "capex", "operating_margin", "gross_margin", "operating_income", "expenses", "cash_flow"}:
                continue
            u1 = (r.group("unit1") or r.group("unit2")).lower()
            u2 = r.group("unit2").lower()
            if u1 != u2:
                continue
            unit = MONEY_UNITS.get(u2)
            if not unit:
                continue
            # Percent versus currency must be consistent with metric type.
            if (unit == "percent") != (c in {"operating_margin", "gross_margin"}):
                continue
            lo, hi = Decimal(r.group("low")), Decimal(r.group("high"))
            if lo < 0 or hi <= lo:
                continue
            h = horizon(sentence)
            key = (c, h, unit, str(lo), str(hi))
            if key in seen:
                continue
            seen.add(key)
            source_hash = hashlib.sha256(sentence.encode()).hexdigest()
            item = {"metric": c, "horizon": h, "low": float(lo), "high": float(hi),
                    "unit": unit, "speaker": turn["speaker"], "turn": turn["turn"],
                    "source_sha256": source_hash, "verification": "management_statement_unreconciled",
                    "precision": "range_as_spoken"}
            guidance.append(item)
            mid = (lo + hi) / 2
            exercises.append({
                "id": hashlib.sha256((ticker + "|" + repr(key)).encode()).hexdigest()[:16],
                "type": "guided_quantitative",
                "ticker": ticker, "metric": c, "horizon": h, "unit": unit,
                "prompt": f"{ticker} management gave a {h} {c.replace('_',' ')} range of "
                          f"{lo}–{hi} {unit}. Calculate its midpoint and range width.",
                "answer": {"midpoint": float(mid), "width": float(hi - lo), "unit": unit},
                "formula": "midpoint = (low + high) / 2; width = high - low",
                "evidence_sha256": source_hash, "source_turn": turn["turn"],
                "verification": "arithmetic_verified; inputs_management_unreconciled",
            })
            if len(guidance) >= 18:
                break
    # Additional algebraic drills; never assume opposite endpoints co-occur.
    for g in guidance[:8]:
        lo, hi = Decimal(str(g["low"])), Decimal(str(g["high"]))
        middle = (lo + hi) / 2
        if middle <= 0:
            continue
        relative = ((hi - lo) / middle * 100).quantize(Decimal("0.01"))
        exercises.append({
            "id": hashlib.sha256((ticker + repr(g) + "relative-width").encode()).hexdigest()[:16],
            "type": "relative_guidance_width", "ticker": ticker,
            "metric": g["metric"], "horizon": g["horizon"],
            "prompt": f"Using {ticker}'s {g['horizon']} {g['metric'].replace('_',' ')} "
                      f"range ({g['low']}–{g['high']} {g['unit']}), compute "
                      "the range width as a percentage of its midpoint.",
            "answer": {"relative_width_pct": float(relative)},
            "unit": "percent",
            "formula": "100 * (high - low) / ((high + low) / 2)",
            "evidence_sha256": g["source_sha256"], "source_turn": g["turn"],
            "verification": "arithmetic_verified; inputs_management_unreconciled",
        })
    for numer_metric, denom_metric, label in [
        ("capex", "revenue", "CapEx intensity"),
        ("operating_income", "revenue", "operating margin"),
    ]:
        for num in (g for g in guidance if g["metric"] == numer_metric and g["horizon"] != "unspecified"):
            denom = next((g for g in guidance if g["metric"] == denom_metric and
                          g["horizon"] == num["horizon"] and
                          g["unit"] == num["unit"]), None)
            if (not denom or Decimal(str(denom["low"])) <= 0 or
                    Decimal(str(num["low"])) < 0):
                continue
            lower = (Decimal(str(num["low"])) / Decimal(str(denom["high"])) * 100)
            upper = (Decimal(str(num["high"])) / Decimal(str(denom["low"])) * 100)
            exercises.append({
                "id": hashlib.sha256((ticker + num["horizon"] + numer_metric + denom_metric).encode()).hexdigest()[:16],
                "type": "mechanical_ratio_bounds", "ticker": ticker,
                "metric": label, "horizon": num["horizon"],
                "unit": "percent",
                "prompt": f"Using {ticker}'s {num['horizon']} management-stated {numer_metric.replace('_',' ')} "
                          f"range ({num['low']}–{num['high']} {num['unit']}) and "
                          f"revenue range ({denom['low']}–{denom['high']} {denom['unit']}), "
                          f"derive mathematical bounds for {label}. Do not assume both endpoints occur together.",
                "answer": {"minimum_pct": round(float(lower), 2), "maximum_pct": round(float(upper), 2)},
                "formula": "lower = 100 * numerator_low / denominator_high; "
                           "upper = 100 * numerator_high / denominator_low",
                "evidence_sha256": [num["source_sha256"], denom["source_sha256"]],
                "source_turn": [num["turn"], denom["turn"]],
                "verification": "mathematical_bounds_only; ranges_not_joint_scenarios; management_unreconciled",
            })
    counts = dict(analyst_topics)
    return {"guidance": guidance, "qa_topic_counts": counts,
            "analyst_questions": observed_analysts[:12],
            "quantitative_exercises": exercises[:18], "qa_count_detected": sum(counts.values()),
            "extraction": "rules_v1_no_llm", "source_text_public": False}


def guidance_changes(current, history):
    """Compare only genuinely identical forecast horizon, metric and units."""
    latest = {}
    for row in sorted(history, key=lambda x: x.get("date", ""), reverse=True):
        for g in row.get("guidance", []):
            key = (g["metric"], g["horizon"], g["unit"])
            if g["horizon"] != "unspecified" and key not in latest:
                latest[key] = (g, row.get("date"))
    changes = []
    for g in current.get("guidance", []):
        key = (g["metric"], g["horizon"], g["unit"])
        if key not in latest or g["horizon"] == "unspecified":
            continue
        p, date = latest[key]
        prior = (Decimal(str(p["low"])) + Decimal(str(p["high"]))) / 2
        middle = (Decimal(str(g["low"])) + Decimal(str(g["high"]))) / 2
        delta = middle - prior
        changes.append({
            "metric": g["metric"], "horizon": g["horizon"], "unit": g["unit"],
            "prior_date": date, "prior_midpoint": float(prior),
            "current_midpoint": float(middle), "delta": float(delta),
            "delta_pct": float(100 * delta / prior) if prior != 0 else None,
            "verification": "same_horizon_arithmetic; management_inputs_not_SEC_reconciled",
        })
    return changes[:12]
