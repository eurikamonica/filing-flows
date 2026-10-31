"""What listed companies invest in, read from their own filings: the investment balances and gains every company tags in
XBRL, and the companies it names as investees in its 10-Q and 10-K. Behind the company page's "Investments" view and the
#investors pages (who invests in what, and which listed companies have invested in a private company such as Anthropic).

  balances   quarter ends, as tagged in SEC's company facts (us-gaap):
               nm  non-marketable equity securities: no readily determinable fair value, carried under ASC 321's
                   measurement alternative (cost − impairment ± observable price changes): most private-company stakes
               em  equity-method investments (ASC 323: significant influence, usually 20–50% of the investee)
               fv  marketable equity securities at fair value through net income (FV-NI)
               lt  long-term investments as tagged, only for a company that tags neither nm nor em (Salesforce's
                   "Strategic investments")
             A filer that tags a balance only on a dimension (Alphabet's marketable equity in 2026, "recurring fair value
             measurements") gets it from the filing's own XBRL instance once that filing has been read.
  gains      by quarter: gains (losses) on investments as the company totals them (GainLossOnInvestments,
             DebtAndEquitySecuritiesGainLoss), else gains on equity securities at fair value plus the upward adjustments
             less the downward adjustments and impairments of non-marketable equity. Equity-method income apart, and
             pretax income alongside: the share of profit that came from revaluing investments.
  investees  1. members of investee axes in the filing's XBRL (Amazon tags "Anthropic", Microsoft "OpenAI Global LLC",
                Alphabet "SpaceX", Salesforce "Anthropic PBC"), with the facts tagged on each;
             2. sentences that put a name in an investment phrase: "we invested $5.0 billion in Anthropic Series H
                nonvoting preferred stock", "our investment in Crux AI", "X, an unconsolidated equity method joint
                venture". A name that appears only as a customer, lessor, lender or guarantee counterparty is no investee.
             Names are matched to SEC registrants when the site is built (custnet.Names): a listed investee links to its
             company page; any other is shown as private (or a company the matcher does not know).

Stored per company: rec["inv"] (figures from company facts, refreshed with the "Profit and cash" figures) and
rec["invr"] (the reading of its latest 10-Q and 10-K, {"q": ..., "k": ...}). Outputs: data/investors/index.json (every
company with an investment balance or a named investee), data/investors/c/<cik>.json, data/investors/investees.json.

    python -m pipeline.investments 1018724          # one company: its figures and the reading of its latest 10-Q
"""
import datetime as dt
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

from . import facts as F

VERSION = 1                # the figures from company facts (rec["inv"])
READ_V = 1                 # the reading of a filing (rec["invr"]); a new version reads the latest filings again
KEEP_Q = 12                # quarters shown
REFRESH_PER_RUN = 80       # companies whose figures are computed again per run (company facts downloads)
READ_PER_RUN = 30          # filings read per run (a document, its XBRL instance and labels)
MAX_SENT = 20
MAX_MEMBERS = 30
MAX_FACTS = 10
FINANCIAL = range(6000, 6800)        # banks, insurers, brokers, funds: their portfolios are the business
OPERATING_INVESTORS = {1067983}      # Berkshire Hathaway: an insurer counted among the companies investing their own capital

BAL = {
    "nm": ["EquitySecuritiesWithoutReadilyDeterminableFairValueAmount"],
    "em": ["EquityMethodInvestments"],
    "fv": ["EquitySecuritiesFvNi", "EquitySecuritiesFvNiCurrentAndNoncurrent", "EquitySecuritiesFvNiNoncurrent",
           "MarketableSecuritiesEquitySecurities"],
    "lt": ["OtherLongTermInvestments", "LongTermInvestments"],     # shown only for a company that tags neither nm nor em
}                                                                  # (Salesforce's "Strategic investments")
BAL_X = {**BAL, "fv": BAL["fv"] + ["EquitySecuritiesFVNINoncurrent"]}   # also read on a dimension in the filing's instance
INSTANT_CONCEPTS = {t for ts in BAL.values() for t in ts}        # balances facts.index_facts keeps (via quality.INSTANTS)
TOTAL_GAIN = ["GainLossOnInvestments", "DebtAndEquitySecuritiesGainLoss"]
GAIN = {
    "gfv": ["EquitySecuritiesFvNiGainLoss"],
    "up": ["EquitySecuritiesWithoutReadilyDeterminableFairValueUpwardPriceAdjustmentAnnualAmount"],
    "dn": ["EquitySecuritiesWithoutReadilyDeterminableFairValueDownwardPriceAdjustmentAnnualAmount"],
    "imp": ["EquitySecuritiesWithoutReadilyDeterminableFairValueImpairmentLossAnnualAmount"],
    "emi": ["IncomeLossFromEquityMethodInvestments"],
    "pti": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
}


def _d(s):
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------------------------------------------- figures
def _quarter(per, end):
    try:
        return F._quarter_from(per, end)
    except Exception:
        return None


def compute(fx, fye="1231"):
    """{"v", "q": [{"end", "label", "nm", "em", "fv", "g", "gfv", "up", "dn", "imp", "emi", "pti"}], "ttm", "src"} from
    the indexed company facts (facts.index_facts); {"v"} alone when the company tags none of it."""
    inst = fx.get("__instants__") or {}
    labels = fx.get("__labels__") or {}
    bal_days = set()
    for tags in BAL.values():
        for t in tags:
            bal_days |= set((inst.get(t) or {}).keys())
    flows = [t for tags in GAIN.values() for t in tags] + TOTAL_GAIN
    has_gain = any(fx.get(t) for t in flows if t not in GAIN["pti"])
    if not bal_days and not has_gain:
        return {"v": VERSION}
    ends = set(bal_days)
    try:
        ends |= set(F.quarter_ends(fx))
    except Exception:
        pass
    for t in GAIN["pti"]:
        ends |= {e for (s, e) in (fx.get(t) or {}) if 75 <= (_d(e) - _d(s)).days <= 380}
    if not ends:
        return {"v": VERSION}
    last = max(ends)
    cut = (_d(last) - dt.timedelta(days=int(365.25 * 4.3))).isoformat()
    src, rows = {}, []
    for e in sorted(x for x in ends if x >= cut):
        r = {"end": e}
        for role, tags in BAL.items():
            for t in tags:
                f = (inst.get(t) or {}).get(e)
                if f is not None and f.get("val") is not None:
                    r[role] = f["val"]
                    src.setdefault(role, t)
                    break
        for role, tags in GAIN.items():
            for t in tags:
                if fx.get(t):
                    v = _quarter(fx[t], e)
                    if v is not None:
                        r[role] = v
                        src.setdefault(role, t)
                        break
        for t in TOTAL_GAIN:
            if fx.get(t):
                v = _quarter(fx[t], e)
                if v is not None:
                    r["g"], r["gk"] = v, t
                    src.setdefault("g", t)
                    break
        if r.get("fv") is not None and r.get("fv") == r.get("nm"):
            del r["fv"]                                      # one balance-sheet line tagged twice (NVIDIA, 2024–2025)
        if r.get("nm") is not None or r.get("em") is not None:
            r.pop("lt", None)
        if "g" not in r and any(k in r for k in ("gfv", "up", "dn", "imp")):
            r["g"] = r.get("gfv", 0) + r.get("up", 0) - r.get("dn", 0) - r.get("imp", 0)
            r["gk"] = "sum"
        if any(k in r for k in ("nm", "em", "fv", "lt", "g", "emi")):
            try:
                r["label"] = F.fiscal_label(e, fye or "1231")[0]
            except Exception:
                r["label"] = e
            rows.append(r)
    if not rows:
        return {"v": VERSION}
    # a balance tagged on a 52/53-week calendar a few days off the quarter's revenue end: one row, not two
    merged = []
    for r in rows:
        if merged and (_d(r["end"]) - _d(merged[-1]["end"])).days <= 10:
            keep, other = (r, merged[-1]) if len(r) >= len(merged[-1]) else (merged[-1], r)
            merged[-1] = {**other, **keep}
        else:
            merged.append(r)
    rows = merged
    ttm = {}
    q4 = rows[-4:]
    if len(q4) == 4 and 330 <= (_d(q4[-1]["end"]) - _d(q4[0]["end"])).days + 91 <= 400:
        for k in ("g", "emi", "pti", "up", "dn", "imp", "gfv"):
            if all(r.get(k) is not None for r in q4):
                ttm[k] = sum(r[k] for r in q4)
        if ttm:
            ttm["end"] = q4[-1]["end"]
    return {"v": VERSION, "q": rows[-KEEP_Q - 4:], "ttm": ttm,
            "src": {k: [t, labels.get(t) or t] for k, t in src.items()}}


# ---------------------------------------------------------------------------------------------------- names
SUFFIX = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "lp", "l", "p", "plc",
          "pbc", "sa", "ag", "nv", "se", "gmbh", "bv", "holdings", "holding", "group", "global", "the", "spa", "kk", "ab",
          "asa", "oyj", "sas", "srl", "pte", "pty", "member", "s", "a", "de", "cv"}
CATEGORY = re.compile(r"(?i)\b(securities|security|investments?|investees|equity|debt|bonds?|notes?|funds?|level\s?\d|"
                      r"measurement|marketable|non-?marketable|publicly|privately|private|public|other|others|various|several|"
                      r"certain|portfolio|instruments?|stocks?|shares|units|warrants?|options?|loans?|receivables?|assets?|cash|"
                      r"money market|treasury|treasuries|government|municipal|corporate|mortgage|asset-backed|commercial paper|"
                      r"derivatives?|hedg\w*|currency|foreign|domestic|total|aggregate|newly formed|one|two|three|four|five|six|"
                      r"unconsolidated|consolidated|segments?|subsidiar\w*|venture capital|strategic|affiliates|related part\w*|"
                      r"customers?|suppliers?|vendors?|lessors?|lenders?|counterpart\w*|carrying|reported|estimate|"
                      r"fair value|recurring|nonrecurring|accumulated|unrealized|realized|gains?|losses?|impairments?|"
                      r"adjustments?|preferred|common|series|class|convertible|available for sale|held to maturity|trading|transactions?|"
                      r"liquidation)\b")
START_STOP = set("""the our its their this these those such certain other each all any some no a an in as at for from on of by to
with and or but q1 q2 q3 q4 note notes level series class item part fiscal january february march april may june july august
september october november december u.s us usa united north south east west latin europe european asia asian china chinese india
japan japanese germany canada mexico brazil korea taiwan emea apac americas international total net gross accumulated common
preferred equity debt treasury government federal state corporate cash marketable non-marketable nonmarketable
available-for-sale trading held-to-maturity privately private public publicly strategic venture restricted short-term long-term
current noncurrent interest operating financing investing capital property real infrastructure data cloud research development
technology technologies products services revenue revenues income statements consolidated condensed company companies
subsidiaries affiliates partners partnership joint fund funds plan plans trust securities shares stock board directors management
ai it r&d esg gaap sec irs fasb asc asu libor sofr covid-19 ceo cfo tier we us following prior during under see refer if when
mandatory cumulative perpetual depositary redeemable exchangeable senior subordinated junior floating fixed variable
activity activities intellectual technical talent people employees growth innovation sustainability marketing sales content
devices hardware software facilities manufacturing capacity programs initiatives systems platforms network networks machine
learning continued increased significant additional new existing further vies vie firm you earnings pipeline
insurance transferable tax retained industry automotive plastic waste bottling sales-type""".split())
GENERIC = {"ai", "artificial intelligence", "data centers", "data center", "infrastructure", "research", "technology", "cloud",
           "energy", "real estate", "startups", "start ups", "early stage companies", "emerging companies", "ecommerce", "e commerce"}
LEAD = re.compile(r"(?i)^(?:(?:our|its|the)\s+)?(?:ownership|investments?|interests?|equity interests?|stakes?)\s+in\s+(?:the\s+)?")
POSS = re.compile(r"(?:’s|'s|’|')$")
TRAIL = re.compile(r"(?i)(?:\s+(?:equity[- ]method|joint\s+venture|investee|investment|investments|member|series\s+[a-z][\w-]*|"
                   r"preferred|common|stock|shares|notes|convertible|nonvoting|non-voting|class\s+[a-z]|units|warrants?|"
                   r"securities|interests?|stake|and|of|the|in|&))+$")
LEGAL = r"(?:,?\s(?:Inc|PBC|LLC|L\.L\.C|Ltd|L\.P|LP|plc|Corp|Corporation|N\.V|S\.A|AG|SE|GmbH|Co)\.?)"


def norm(s):
    s = (s or "").lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"'s\b", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def key_of(name):
    """'Anthropic, PBC' and 'Anthropic' -> 'anthropic'; 'OpenAI Global LLC' -> 'openai'."""
    w = norm(name).split()
    while len(w) > 1 and w[-1] in SUFFIX:
        w.pop()
    while len(w) > 1 and w[0] == "the":
        w.pop(0)
    return " ".join(w)


def camel(local):
    """'OpenAIGlobalLlcMember' -> 'OpenAI Global Llc'; 'AnthropicPBCMember' -> 'Anthropic PBC'; 'SpaceXMember' -> 'SpaceX'."""
    s = re.sub(r"Member$", "", local)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z][a-z])|(?<=[A-Z])(?=[A-Z][a-z]{2,})|(?<=[a-z])(?=[A-Z]{2,}$)", " ", s)
    return s.strip()


def clean_name(name, me=()):
    """A company name as a filing writes it, or None when it is no name ('Privately held equity securities', 'AI',
    'Series C', the filer itself)."""
    n = re.sub(r"\s+", " ", (name or "")).strip(" ,.;:()“”\"")
    n = LEAD.sub("", n)                                          # 'Ownership In Cotton Draw Midstream' (a member's label)
    n = re.sub(r"\s*\((?:“|\")[^)]*(?:”|\")\)$", "", n)          # 'Anthropic PBC (“Anthropic”)'
    for _ in range(3):
        n = POSS.sub("", n).strip()
        n2 = TRAIL.sub("", n).strip(" ,.")
        if n2 == n:
            break
        n = n2
    if not n or len(n) < 2 or len(n) > 60 or not re.search(r"[A-Za-z]", n):
        return None
    words = n.split()
    if words[0].lower().strip(",.") in START_STOP or norm(n) in GENERIC or CATEGORY.search(n):
        return None
    if len(words) == 1 and re.fullmatch(r"[A-Z0-9&]{1,5}s?", n):        # 'AWS', 'AI', 'R&D', 'VIEs': a segment or an acronym
        return None
    if not (n[0].isupper() or re.match(r"[a-z][A-Z]", n) or n[0].isdigit()):
        return None
    k = key_of(n)
    flat = k.replace(" ", "")
    if not k or any(k == m or k.split()[0] == m or (len(m) >= 5 and flat.startswith(m.replace(" ", ""))) for m in me):
        return None
    if re.match(r"\d", n) and len(words) == 1:                    # '2nm', '5G': a technology, not a company
        return None
    return n


# ---------------------------------------------------------------------------------------------------- the XBRL instance
IV_AXIS = re.compile(r"InvesteeName|InvestmentIssuerName|InvestmentIssuerAffiliation|ScheduleOfEquityMethodInvestment|"
                     r"EquityMethodInvestee|InvesteeAxis")
WEAK_AXIS = re.compile(r"^(FinancialInstrumentAxis|InvestmentTypeAxis|EquitySecuritiesByIndustryAxis|InvestmentTypeCategorizationAxis|"
                       r"LegalEntityAxis|CounterpartyNameAxis|BusinessAcquisitionAxis|RelatedPartyTransactionsByRelatedPartyAxis|"
                       r"RelatedPartyTransactionAxis|ConvertibleDebtInstrumentAxis|DebtInstrumentAxis)$")
INV_CONCEPT = re.compile(r"Invest|EquitySecurit|EquityMethod|AvailableForSale|ConvertibleNotes|GainLossOn|UpwardPrice|"
                         r"DownwardPrice|OwnershipPercentage|InvestmentOwned|Warrant")
NEUTRAL = {("FairValueByMeasurementFrequencyAxis", "FairValueMeasurementsRecurringMember"),
           ("FinancialInstrumentAxis", "EquitySecuritiesMember"),
           ("FairValueByMeasurementBasisAxis", "CarryingReportedAmountFairValueDisclosureMember")}


def _local(tag):
    return tag.split("}")[-1]


def _num(text):
    try:
        return float((text or "").strip())
    except ValueError:
        return None


def instance(xml_text, labels=None, me=()):
    """(investee members [{"name", "m", "axis", "weak", "f": [[concept, label, start, end, value, unit]]}],
        balances {role: {day: value}} from undimensioned or 'recurring fair value' facts,
        the keys of the company's own segments, products and regions) of one XBRL instance."""
    root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    labels = labels or {}
    ctx, units = {}, {}
    for el in root:
        n = _local(el.tag)
        if n == "context":
            start = end = inst = None
            dims = []
            for x in el.iter():
                m = _local(x.tag)
                if m == "startDate":
                    start = (x.text or "").strip()
                elif m == "endDate":
                    end = (x.text or "").strip()
                elif m == "instant":
                    inst = (x.text or "").strip()
                elif m == "explicitMember":
                    dims.append((x.get("dimension", "").split(":")[-1], (x.text or "").strip()))
            ctx[el.get("id")] = (start, end or inst, inst, dims)
        elif n == "unit":
            meas = [(x.text or "").strip().split(":")[-1] for x in el.iter() if _local(x.tag) == "measure"]
            units[el.get("id")] = meas[0] if len(meas) == 1 else "/".join(meas)
    bal_tags = {t: role for role, ts in BAL_X.items() for t in ts if role != "lt"}
    by_local = {}
    for k_, v_ in labels.items():                        # 'goog_EquityMethodInvestmentCreditBackstopCommitment' -> its label
        by_local.setdefault(k_.split("_", 1)[-1], v_)
    members, bal, segs = {}, defaultdict(dict), set()
    for el in root:
        cref = el.get("contextRef")
        if cref not in ctx:
            continue
        concept = _local(el.tag)
        v = _num(el.text)
        if v is None:
            continue
        start, end, inst, dims = ctx[cref]
        if concept in bal_tags and inst and dims and all((a, m.split(":")[-1]) in NEUTRAL for a, m in dims):
            role = bal_tags[concept]
            bal[role][inst] = max(bal[role].get(inst, 0), v)
            continue
        for a, m in dims:
            if a in OWN_AXES and not m.startswith(("us-gaap:", "srt:")):
                segs.add(key_of(labels.get(m.replace(":", "_")) or camel(m.split(":")[-1])))
        if not dims or not INV_CONCEPT.search(concept):
            continue
        for a, m in dims:
            strong = bool(IV_AXIS.search(a))
            if not strong and not WEAK_AXIS.match(a):
                continue
            if m.startswith(("us-gaap:", "srt:", "dei:", "ifrs-full:")):
                continue
            local = m.split(":")[-1]
            raw = labels.get(m.replace(":", "_")) or camel(local)
            name = clean_name(re.sub(r"(?i)\s*\[member\]$", "", raw), me)
            if not name or key_of(name) in GEO:
                continue
            rec = members.setdefault(m, {"name": name, "m": local, "axis": a, "weak": not strong, "f": {}})
            rec["weak"] = rec["weak"] and not strong
            u = units.get(el.get("unitRef")) or ""
            k = (concept, start if not inst else None, end)
            extra = len(dims) - 1
            old = rec["f"].get(k)
            if old is None or extra < old[1]:
                lab = by_local.get(concept) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", concept).capitalize()
                rec["f"][k] = ([concept, lab, start if not inst else None, end, v, u], extra)
    out = []
    for rec in members.values():
        fs = sorted((f for f, _ in rec["f"].values()), key=lambda f: (f[3] or "", f[0]), reverse=True)[:MAX_FACTS]
        out.append({"name": rec["name"], "m": rec["m"], "axis": rec["axis"], "weak": rec["weak"], "f": fs})
    out.sort(key=lambda r: (r["weak"], -max((abs(f[4]) for f in r["f"] if f[5] == "USD"), default=0)))
    return out[:MAX_MEMBERS], {k: dict(v) for k, v in bal.items()}, segs - {""}


# ---------------------------------------------------------------------------------------------------- sentences
TOK = r"(?:[A-ZÀ-ÖØ-Þ][^\W_]*(?:[&\-][^\W_]+)*(?:\.[^\W_]+)*|[a-z][A-Z][^\W_]*|\d+[A-Za-z][^\W_]*)"
NAME = rf"({TOK}(?:\s(?:{TOK}|of|and|&|de|du|la|der)){{0,5}}{LEGAL}?)"
MONEY_RX = r"\$\s?[\d][\d,]*(?:\.\d+)?\s*(?:billion|million|thousand)?"
INSTR = (r"(?i:(?:series\s+[a-z][\w-]*\s+)?(?:(?:non-?voting|convertible|redeemable|senior|participating)\s+)*"
         r"(?:preferred\s+stock|preferred\s+shares|preferred\s+units|common\s+stock|common\s+shares|ordinary\s+shares|shares|"
         r"stock|equity|units|convertible\s+notes|notes|warrants|securities))")
PATTERNS = [
    re.compile(rf"\b(?i:invest(?:ed|ing|ment|ments)?)\s+(?:(?i:of|totaling|totalling|approximately|an?|additional|aggregate|"
               rf"over|about|nearly|up\s+to)\s+)*(?:{MONEY_RX}\s+)?(?i:in|into)\s+(?:(?i:the|an?)\s+)?"
               rf"(?:{INSTR}\s+(?i:of|in|from|issued\s+by)\s+)?{NAME}"),
    re.compile(rf"\b(?i:stake|ownership\s+interest|equity\s+interest|noncontrolling\s+interest|minority\s+interest|"
               rf"equity\s+investments?|investments?|holdings?|position)\s+(?i:in)\s+(?:(?i:the)\s+)?{NAME}"),
    re.compile(rf"\b{INSTR}\s+(?i:of|in|from|issued\s+by)\s+{NAME}"),
    re.compile(rf"{NAME}(?:’s|'s)\s+(?i:(?:series\s+[a-z][\w-]*\s+)?(?:non-?voting\s+)?(?:preferred|common|ordinary)\s+"
               rf"(?:stock|shares|units)|convertible\s+notes)"),
    re.compile(rf"{NAME},?\s+(?:\((?:“|\")[^)]{{1,40}}(?:”|\")\)\s*,?\s*)?(?i:an?\s+(?:unconsolidated\s+)?(?:equity[- ]method\s+"
               rf"(?:joint\s+venture|investee|investment|affiliate)|joint\s+venture\s+in\s+which\s+we|investee))"),
    re.compile(rf"\b(?i:equity[- ]method\s+(?:investment|investee|joint\s+venture)s?)\s*(?:(?i:in)\s+|,\s+){NAME}"),
    re.compile(rf"{MONEY_RX}\s+(?i:in|into)\s+(?:(?i:the)\s+)?(?:{INSTR}\s+(?i:of|in|from|issued\s+by)\s+)?{NAME}"),   # "…, and $10.0
]                                                                                                          # billion in Anthropic"
INV_WORD = re.compile(r"(?i)\b(invest(?:ed|ing|ment|ments)|equity[- ]method|non-?marketable|privately[- ]held|preferred stock|"
                      r"convertible notes?|stake|ownership interest|carrying value|joint venture)\b")
NOT_INV = re.compile(r"(?i)\b(customers?|lessors?|leases? (?:to|from|with)|guarantee[sd]?|credit support|backlog|"
                     r"license agreement|supply agreement|commercial agreement|purchase obligations?|competitors?)\b")
MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)?", re.I)
SCALE = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
KIND = [("value", re.compile(r"(?i)carrying (?:value|amount)|fair value of|represent(?:ed|s|ing) (?:approximately )?\$|valued at|balance of")),
        ("invested", re.compile(r"(?i)\binvest(?:ed|ing)\b|\bpurchased\b|\bacquired\b|made an investment|participat\w* in")),
        ("commit", re.compile(r"(?i)\bcommit\w*|agreed to (?:purchase|invest|fund|provide)|up to \$|option to (?:purchase|invest)|backstops?")),
        ("gain", re.compile(r"(?i)\bgains?\b|upward adjustments?|unrealized gains?")),
        ("loss", re.compile(r"(?i)\blosses\b|\bloss\b|impairments?|downward adjustments?|write-?downs?"))]
NOT_AMOUNT = re.compile(r"(?i)backlog|revenues?\b|\btax\b|tax (?:expense|provision|benefit)|\bleases?\b|\bloans?\b|borrowings?|"
                        r"credit agreement|term loan|notes due|senior notes|diluted eps|per share|"
                        r"\b(?:increased|decreased|rose|fell|declined|grew)\s+(?:by\s+)?(?:approximately\s+)?\$")
CLAUSE = re.compile(r";\s+|,\s+(?=(?:including|which|of which|while|whereas|compared|partially|and\s+(?:we|our|the|\$)|"
                    r"but|although|as well as)\b)|\s+\((?=[^)]*\$)")
SUBSIDIARY = re.compile(r"(?i)^,?\s+(?:an?|our)\s+(?:wholly[- ]owned|consolidated|majority[- ]owned)\s+subsidiar")


def _amounts(s):
    out = []
    for m in MONEY.finditer(s):
        unit = (m.group(2) or "").lower()
        if not unit:
            continue                                     # "$272" in a table's thousands: no scale to read it with
        try:
            out.append((m.start(), m.end(), float(m.group(1).replace(",", "")) * SCALE[unit]))
        except ValueError:
            pass
    return out


def _kind(text):
    return next((k for k, rx in KIND if rx.search(text)), "other")


LIST_MORE = re.compile(rf"^(?:,\s*(?:and\s+)?|\s+and\s+)(?:(?i:the)\s+)?{NAME}")
OWN_AXES = {"StatementBusinessSegmentsAxis", "ProductOrServiceAxis", "StatementGeographicalAxis", "ConsolidationItemsAxis",
            "SegmentReportingInformationBySegmentAxis", "RevenueFromContractWithCustomerByProductOrServiceAxis"}
FIRST_PERSON = re.compile(r"\b(?:[Ww]e|[Oo]ur|[Uu]s|[Tt]he (?:Company|Firm|Corporation|Registrant)(?:’s|'s)?)\b")
STRONG_CTX = re.compile(r"(?i)\b(?:stock|shares?|preferred|convertible|notes?|warrants?|equity|stake|ownership|carrying (?:value|amount)|"
                        r"investee|joint venture|fair value|non-?marketable|privately[- ]held|portfolio|securities|minority|"
                        r"valuation|financing|series [a-z])\b")
WEAK_CTX = re.compile(r"(?i)\b(?:gains?|losses|upward|downward|impairments?|unrealized|realized|write-?downs?)\b")
NEG_CTX = re.compile(r"(?i)operating (?:profit|loss|losses|income|expenses?|margin)|capital expenditures|research and development|"
                     r"initiatives|headcount|marketing|talent")
OWN_STAKE = re.compile(r"(?i)\b(?:our|its|the company['’]s|equity|minority|strategic|noncontrolling)\s+(?:[\w-]+\s+)?"
                       r"investments?\s+in\s+(?:the\s+)?(?:[A-Z][\w&.\-]*,?\s+(?:and\s+)?)*$")
INDEX_AFTER = re.compile(r"^(?:’s|'s)?\s*(?:\d+\s+)?(?:Stock\s+|Composite\s+|Total Return\s+)?Index\b")
ACQUIRE = re.compile(r"(?i)\bacqui(?:re|red|res|ring|sition of)\b|\bmerger with\b|\bpurchase of all\b")
LEGAL_TAIL = re.compile(r"(?i)\b(?:inc|pbc|llc|l\.l\.c|ltd|l\.p|lp|plc|corp|corporation|n\.v|s\.a|ag|se|gmbh|limited|company|co)\.?$")
GEO = {g.strip() for g in """afghanistan, albania, algeria, angola, argentina, armenia, australia, austria, azerbaijan, bahrain, bangladesh,
belarus, belgium, bolivia, bosnia, botswana, brazil, bulgaria, cambodia, cameroon, canada, chile, china, colombia, costa rica, croatia,
cyprus, czech republic, denmark, dominican republic, ecuador, egypt, el salvador, estonia, ethiopia, finland, france, germany, ghana,
greece, guatemala, honduras, hong kong, hungary, iceland, india, indonesia, iran, iraq, ireland, israel, italy, jamaica, japan, jordan,
kazakhstan, kenya, korea, south korea, kuwait, latvia, lebanon, lithuania, luxembourg, macau, malaysia, malta, mexico, morocco,
mozambique, myanmar, namibia, nepal, netherlands, new zealand, nicaragua, nigeria, norway, oman, pakistan, panama, paraguay, peru,
philippines, poland, portugal, puerto rico, qatar, romania, russia, saudi arabia, senegal, serbia, singapore, slovakia, slovenia,
south africa, spain, sri lanka, sweden, switzerland, taiwan, tanzania, thailand, tunisia, turkey, turkiye, uganda, ukraine,
united arab emirates, uae, united kingdom, uk, england, scotland, wales, uruguay, uzbekistan, venezuela, vietnam, zambia, zimbabwe,
africa, asia, europe, latin america, north america, south america, middle east, asia pacific, alabama, alaska, arizona, arkansas,
california, colorado, connecticut, delaware, florida, hawaii, idaho, illinois, indiana, iowa, kansas, kentucky, louisiana, maine,
maryland, massachusetts, michigan, minnesota, mississippi, missouri, montana, nebraska, nevada, new hampshire, new jersey, new mexico,
new york, north carolina, north dakota, ohio, oklahoma, oregon, pennsylvania, rhode island, south carolina, south dakota, tennessee,
texas, utah, vermont, virginia, washington, west virginia, wisconsin, wyoming""".replace("\n", " ").split(",")}


def _plain(n, lower_words):
    """A capitalised run of everyday words ('Bottling Operations', 'Tax Credit Structures'): every word of it is also
    written in lower case elsewhere in the filing, and no legal suffix says it is a company."""
    if LEGAL_TAIL.search(n):
        return False
    ws = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]*", n) if w.lower() not in ("of", "and", "the", "for", "in", "de")]
    return bool(ws) and all(w.lower() in lower_words and not (w.isupper() and len(w) > 1) and not re.search(r"[a-z][A-Z]", w)
                            for w in ws)


def _ok_text_name(n, s, me, segs, lower_words):
    """A name read from an investment phrase counts only where the filer speaks of its own investment ('we', 'our',
    'the Company', its own name) about shares, notes, stakes or their gains — not an investment in a product line
    ('investing in Reels'), a country, one of its own segments, or a heading of everyday words."""
    k = key_of(n)
    if not k or k in GEO or k.split()[0] in GEO and len(k.split()) == 1 or k in segs:
        return False
    at = s.find(n)
    if at >= 0 and INDEX_AFTER.match(s[at + len(n):at + len(n) + 40]):
        return False                                     # "a similar investment in the Standard & Poor’s 500 Stock Index"
    if at >= 0 and ACQUIRE.search(s[max(0, at - 60):at]) and not re.search(r"(?i)stake|minority|equity[- ]method|interest in|shares of", s):
        return False                                     # "the firm’s commitment to acquire X": a purchase of the company
    if not (FIRST_PERSON.search(s) or any(m and re.search(r"(?i)\b" + re.escape(m) + r"\b", s) for m in me if len(m) >= 4)):
        return False
    own_stake = at > 0 and OWN_STAKE.search(s[max(0, at - 70):at])
    if not (STRONG_CTX.search(s) or ((WEAK_CTX.search(s) or own_stake) and not NEG_CTX.search(s))):
        return False
    return not _plain(n, lower_words)


def also_names(names):
    """XBRL member names as the text writes them: 'OpenAI Global Llc' -> 'OpenAI Global Llc', 'OpenAI'."""
    out = []
    for n in names:
        out.append(n)
        ws = n.split()
        cut = next((i for i, w in enumerate(ws) if i and norm(w) in SUFFIX), None)
        if cut:
            short = " ".join(ws[:cut]).rstrip(",")
            if len(short) >= 3:
                out.append(short)
    return list(dict.fromkeys(out))


def _split_and(n, me):
    """'Anthropic and OpenAI' -> ['Anthropic', 'OpenAI'] when both halves are names; a name with 'and' in it stays."""
    if " and " not in n:
        return [n]
    parts = [clean_name(p, me) for p in n.split(" and ")]
    return [p for p in parts if p] if all(p and len(p) >= 3 for p in parts) else [n]


def names_in(s, me=(), also=()):
    """[(start, end, name, via)] of the companies a sentence puts in an investment phrase (via "p"), lists included
    ('investments in Anthropic, OpenAI and xAI'), plus the XBRL members ('also') it mentions (via "x")."""
    found = []
    head = s.find(":")
    if 0 < head < 120:                                   # "Continued Investment in Intellectual Property: We …"
        lead = s[:head].split()
        if lead and sum(w[:1].isupper() for w in lead) >= 0.6 * len(lead):
            head = head
        else:
            head = -1
    for rx in PATTERNS:
        for m in rx.finditer(s):
            pos, raw = m.start(1), m.group(1)
            if 0 < head and pos < head:
                continue
            while True:
                n = clean_name(raw, me)
                if n and not SUBSIDIARY.match(s[pos + len(raw):pos + len(raw) + 40]):
                    for part in _split_and(n, me):
                        st = s.find(part, pos)
                        st = pos if st < 0 else st
                        found.append((st, st + len(part), part, "p"))
                more = LIST_MORE.match(s[pos + len(raw):])
                if not more:
                    break
                pos, raw = pos + len(raw) + more.start(1), more.group(1)
    for a in also:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", s):
            found.append((m.start(), m.end(), a, "x"))
    found.sort(key=lambda f: (f[0], -(f[1] - f[0]), f[3] != "p"))
    out = []
    for f in found:                                      # one name per place in the text, the longest
        if out and f[0] < out[-1][1]:
            if f[1] - f[0] > out[-1][1] - out[-1][0]:
                out[-1] = (f[0], f[1], f[2], "p" if "p" in (f[3], out[-1][3]) else f[3])
            elif f[3] == "p" and out[-1][3] != "p":
                out[-1] = out[-1][:3] + ("p",)
            continue
        out.append(f)
    return out


def attribute(s, hits):
    """{name key: [(kind, usd)]} for the amounts a sentence states for a name. Amounts count only inside the name's
    clause ('…$11.3 billion, including … Anthropic PBC which represented approximately $5.1 billion' gives Anthropic
    $5.1 billion); a clause that names several companies gives each only the amount right before it ('$50.0 billion in
    OpenAI’s Series C …, and $10.0 billion in Anthropic'). Tax, revenue, backlog, lease and loan amounts are no
    investment's."""
    amts = _amounts(s)
    if not amts or not hits:
        return {}
    cuts = [0] + [m.end() for m in CLAUSE.finditer(s)] + [len(s) + 1]
    clause = lambda i: next(j for j in range(len(cuts) - 1) if cuts[j] <= i < cuts[j + 1])
    out = defaultdict(list)
    for a0, a1, v in amts:
        c = clause(a0)
        here = [h for h in hits if clause(h[0]) == c]
        if not here:
            continue
        local = s[max(cuts[c], a0 - 70):min(a1 + 25, cuts[c + 1] - 1)]
        if NOT_AMOUNT.search(local):
            continue
        keys = {key_of(h[2]) for h in here}
        if len(keys) > 1:
            nxt = [h for h in here if h[0] >= a1 and h[0] - a1 <= 40
                   and re.fullmatch(r"(?i)\s*(?:of|in|into|for)?\s*(?:the\s+)?(?:[\w-]+\s+){0,4}", s[a1:h[0]])]
            if not nxt:
                continue
            target = min(nxt, key=lambda h: h[0])
        else:
            target = here[0]
        k = _kind(local)
        if k == "other":
            k = _kind(s[cuts[c]:cuts[c + 1]])
        if k == "other":
            k = _kind(s)
        out[key_of(target[2])].append((k, v))
    return dict(out)


def sentences(doc, me=(), also=(), segs=()):
    """Candidate statements about investees: [{"t", "k", "n": [names], "p": [names read from an investment phrase],
    "a": {key: [[kind, usd]]}}], at most MAX_SENT."""
    from .custnet import _flat, _sentences
    lines = _flat(doc)
    lower_words = set(re.findall(r"\b[a-z][a-z\-]+\b", " ".join(l for l in lines if l not in ("¶T", "¶E"))))
    segs = set(segs or ())
    also = also_names(also)
    out, seen, in_table = [], set(), False
    for line in lines:
        if line == "¶T":
            in_table = True
            continue
        if line == "¶E":
            in_table = False
            continue
        if in_table or len(line) < 30 or not INV_WORD.search(line):
            continue
        for s in _sentences(line):
            if len(s) < 25 or len(s) > 1200 or not INV_WORD.search(s):
                continue
            hits = [h for h in names_in(s, me, also) if h[3] == "x" or _ok_text_name(h[2], s, me, segs, lower_words)]
            if not hits:
                continue
            if NOT_INV.search(s) and not re.search(r"(?i)\binvest(?:ed|ing|ment)|equity[- ]method|preferred stock|stake\b", s):
                continue
            k = re.sub(r"\W+", "", s.lower())[:220]
            if k in seen:
                continue
            seen.add(k)
            a = attribute(s, hits)
            names, by_pattern = [], []
            for _, _, n, via in hits:
                if n not in names:
                    names.append(n)
                if via == "p" and n not in by_pattern:
                    by_pattern.append(n)
            out.append({"t": s[:700], "k": _kind(s), "n": names, "p": by_pattern,
                        **({"a": {kk: [[x, round(v)] for x, v in vv] for kk, vv in a.items()}} if a else {})})
    rank = {"value": 0, "invested": 1, "commit": 2, "gain": 3, "loss": 4, "other": 5}
    out.sort(key=lambda x: (not x.get("a"), rank.get(x["k"], 9)))
    return out[:MAX_SENT]


def own_names(name, tickers=()):
    """The filer's own names, never its investees: 'Amazon.com, Inc.' -> {'amazon com', 'amazon'}."""
    k = key_of(name or "")
    out = {k} if k else set()
    if k:
        out.add(k.split()[0])
        out.add(k.replace(" ", ""))
    for t in tickers or ():
        out.add(norm(t))
    return out


def read(cik, accn, form, filed, doc_url, doc, inst_text=None, lab_text=None, end=None, me=()):
    """The reading kept for one filing: investee members of its XBRL, balances tagged only on a dimension, and the
    sentences that name investees."""
    rec = {"v": READ_V, "accn": accn, "form": form, "filed": filed, "url": doc_url, "end": end, "x": [], "s": [], "bal": {}}
    segs = set()
    if inst_text:
        try:
            from . import dims
            labels = dims.parse_labels(lab_text) if lab_text else {}
            rec["x"], rec["bal"], segs = instance(inst_text, labels, me)
        except Exception as e:
            print(f"  investment facts skipped for {cik}: {e}", file=sys.stderr)
    if doc:
        try:
            rec["s"] = sentences(doc, me, [x["name"] for x in rec["x"]], segs)
        except Exception as e:
            print(f"  investment sentences skipped for {cik}: {e}", file=sys.stderr)
    text_keys = {key_of(n) for s in rec["s"] for n in s.get("p") or []}
    rec["x"] = [x for x in rec["x"] if not x["weak"] or key_of(x["name"]) in text_keys]   # a 'legal entity' or a type of
    kept = text_keys | {key_of(x["name"]) for x in rec["x"]}                                # instrument only when the text
    for s in rec["s"]:                                                                      # invests in it
        s["n"] = [n for n in s["n"] if key_of(n) in kept]
        if s.get("a"):
            s["a"] = {k: v for k, v in s["a"].items() if k in kept}
            if not s["a"]:
                del s["a"]
    rec["s"] = [s for s in rec["s"] if s["n"]]
    return rec


def slot(form):
    return "k" if (form or "").startswith("10-K") else "q" if (form or "").startswith("10-Q") else None


def note_filing(c, cik, form, accn, filed, doc_url, doc, inst_text, lab_text, end=None):
    """Called while a new 10-Q or 10-K is processed (the documents are already in hand): keep its reading."""
    k = slot(form)
    if not k or not doc:
        return
    old = (c.get("invr") or {}).get(k) or {}
    if old.get("v") == READ_V and (old.get("filed") or "") > (filed or ""):
        return
    p = c.get("profile") or {}
    c.setdefault("invr", {})[k] = read(cik, accn, form, filed, doc_url, doc, inst_text, lab_text, end,
                                       own_names(p.get("name"), p.get("tickers")))


def latest_filings(rec):
    """{"q": {...}, "k": {...}}: the latest 10-Q and 10-K on file for a stored company."""
    out = {}
    pool = list((rec.get("quarters") or {}).values()) + list((rec.get("years") or {}).values())
    for q in pool:
        k = slot(q.get("form"))
        if k and q.get("doc_url") and q.get("accn") and (k not in out or (q.get("filed") or "") > (out[k].get("filed") or "")):
            out[k] = {kk: q.get(kk) for kk in ("accn", "form", "filed", "doc_url", "end")}
    return out


def _size(rec):
    q = ((rec.get("inv") or {}).get("q") or [])
    last = q[-1] if q else {}
    return sum(abs(last.get(k) or 0) for k in ("nm", "em", "fv"))


def refresh(store, sec, dims, time_up, limit=READ_PER_RUN):
    """Read the latest 10-Q and 10-K of the companies not read yet (or read before the current version): the largest
    investment balances first, then the largest companies."""
    todo = []
    for cik in store.ciks():
        rec = store.company(cik)
        if not rec.get("profile"):
            continue
        have = rec.get("invr") or {}
        for k, f in latest_filings(rec).items():
            old = have.get(k) or {}
            if old.get("v") == READ_V and old.get("accn") == f["accn"]:
                continue
            rev = max(((q.get("raw") or {}).get("revenue") or 0) for q in (rec.get("quarters") or {}).values()) if rec.get("quarters") else 0
            todo.append((0 if not old else 1, -_size(rec), -rev, k != "q", cik, k, f))
    todo.sort(key=lambda x: x[:4])
    done = 0
    for _, _, _, _, cik, k, f in todo:
        if done >= limit or time_up():
            break
        done += 1
        rec = store.company(cik)
        try:
            doc = sec.get(f["doc_url"])
            inst = lab = None
            try:
                iu, lu = dims.find_files(cik, f["accn"])
                inst = sec.get(iu) if iu else None
                lab = sec.get(lu) if lu else None
            except Exception as e:
                print(f"  instance not read for {cik}: {e}", file=sys.stderr)
            p = rec.get("profile") or {}
            rec.setdefault("invr", {})[k] = read(cik, f["accn"], f.get("form"), f.get("filed"), f["doc_url"], doc, inst, lab,
                                                 f.get("end"), own_names(p.get("name"), p.get("tickers")))
        except Exception as e:
            print(f"  investments not read for {cik}: {e}", file=sys.stderr)
            rec.setdefault("invr", {})[k] = {"v": READ_V, "accn": f["accn"], "form": f.get("form"), "filed": f.get("filed"),
                                             "url": f["doc_url"], "error": str(e)[:160], "x": [], "s": [], "bal": {}}
        store.put(cik, rec)
    if todo:
        print(f"investments read: {done} filings, {max(len(todo) - done, 0)} to go")


# ---------------------------------------------------------------------------------------------------- the pages
BAL_FACT = re.compile(r"^(EquityMethodInvestments|EquitySecuritiesFvNi\w*|EquitySecuritiesWithoutReadilyDeterminableFairValueAmount|"
                      r"InvestmentOwnedAtFairValue|InvestmentOwnedAtCost|InvestmentsFairValueDisclosure|AvailableForSaleSecuritiesDebtSecurities\w*|"
                      r"LongTermInvestments|OtherLongTermInvestments|InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures)$")


def _rows(inv, invr):
    """The quarter rows with the balances a filing tagged only on a dimension filled in."""
    rows = [dict(r) for r in (inv.get("q") or [])]
    fill = defaultdict(dict)
    for r in (invr or {}).values():
        for role, days in (r.get("bal") or {}).items():
            for day, v in days.items():
                fill[role][day] = v
    for r in rows:
        for role, days in fill.items():
            if r.get(role) is None:
                v = days.get(r["end"]) or next((x for d_, x in days.items() if abs((_d(d_) - _d(r["end"])).days) <= 10), None)
                if v is not None and v != r.get("nm"):
                    r[role] = v
                    r.setdefault("filled", []).append(role)
        if r.get("nm") is not None or r.get("em") is not None:
            r.pop("lt", None)
    return rows


X_KIND = [("value", BAL_FACT), ("invested", re.compile(r"Funded|PaymentsToAcquire|AtCost|ContributedCapital|PaidInCapital")),
          ("commit", re.compile(r"Commitment|Committed|Backstop")),
          ("gain", re.compile(r"Gain|UpwardPrice|IncomeLossFromEquityMethod|Unrealized|NonoperatingIncome")),
          ("loss", re.compile(r"DownwardPrice|Impairment|Loss"))]


def _x_kind(concept):
    return next((k for k, rx in X_KIND if rx.search(concept)), "fact")


def _best(x_facts, stated):
    """The amount shown for one investee, the most telling first: a balance tagged on it (the latest), the value the
    text states, the amount funded or invested (tagged, else stated), a commitment, a gain."""
    usd = [f for f in x_facts if f[5] == "USD" and f[4]]
    stated = [x for x in stated if x[1]]
    tagged = defaultdict(list)
    for f in usd:
        k = _x_kind(f[0])
        if k == "value" and f[2] is not None:
            continue                                         # a balance is a point in time
        tagged[k].append(f)
    said = defaultdict(list)
    for x in stated:
        said[x[0]].append(x)
    for k in ("value", "invested", "commit", "gain", "loss"):
        if tagged.get(k) and (k != "gain" or not said.get("value")):
            f = max(tagged[k], key=lambda f: (f[3] or "", abs(f[4])))
            return {"k": k, "usd": f[4], "at": f[3], **({"from": f[2]} if f[2] else {}), "how": "xbrl", "l": f[1]}
        if said.get(k):
            x = max(said[k], key=lambda x: abs(x[1]))
            return {"k": k, "usd": x[1], "how": "text", **({"t": x[2]} if len(x) > 2 else {})}
    if usd:
        f = max(usd, key=lambda f: (f[3] or "", abs(f[4])))
        return {"k": "fact", "usd": f[4], "at": f[3], "how": "xbrl", "l": f[1]}
    return None


SENT_RANK = {"value": 0, "invested": 1, "commit": 2, "gain": 3, "loss": 4, "other": 5}


INV_ALIASES = {"spacex": "SPCX"}          # an investee's everyday name -> the ticker of the registrant (custnet.Names)


def _resolve(names, counts, key):
    """(cik, ticker) of the registrant an investee name belongs to: the full legal name first, then a short name that
    only one registrant answers to ('Rivian', 'Anthropic'), then a known other name ('SpaceX')."""
    for cand in sorted(counts, key=len, reverse=True):
        try:
            cik, _ = names.resolve(cand)
        except Exception:
            cik = None
        if cik:
            return cik
    if key in INV_ALIASES and INV_ALIASES[key] in names.by_t:
        return names.by_t[INV_ALIASES[key]]
    if len(key) >= 4 and " " not in key:
        cik = names.alias.get(key)
        if cik:
            return cik
    return None


def named(invr, names=None, self_cik=None):
    """[{"key", "name", "cik"?, "t"?, "via", "x", "s", "best", "form", "filed", "url"}] across the company's readings,
    newest filing first; one entry per investee ('Rivian' and 'Rivian Automotive, Inc.' are one)."""
    by = {}
    reads = sorted((r for r in (invr or {}).values() if r and r.get("v") == READ_V), key=lambda r: r.get("filed") or "", reverse=True)
    new = lambda k, src: {"key": k, "names": [], "via": set(), "x": [], "s": [], "stated": [], **src}
    for r in reads:
        src = {"form": r.get("form"), "filed": r.get("filed"), "url": r.get("url"), "end": r.get("end")}
        for x in r.get("x") or []:
            k = key_of(x["name"])
            e = by.setdefault(k, new(k, src))
            e["names"].append(x["name"])
            e.setdefault("xnames", []).append(x["name"])
            e["via"].add("xbrl")
            if not e["x"]:
                e["x"] = x["f"]
        for s in r.get("s") or []:
            for n in s["n"]:
                k = key_of(n)
                e = by.setdefault(k, new(k, src))
                e["names"].append(n)
                e["via"].add("text")
                a = (s.get("a") or {}).get(k, [])
                if s["t"] not in (y["t"] for y in e["s"]):
                    e["s"].append({"t": s["t"], "k": s["k"], "_r": (not a, -int(re.sub(r"\D", "", r.get("filed") or "") or 0), SENT_RANK.get(s["k"], 9)),
                                   "form": r.get("form"), "filed": r.get("filed"), "url": r.get("url")})
                for kind, v in a:
                    e["stated"].append((kind, v, s["t"]))
    flat = {}
    for k in list(by):                                   # the same name spaced two ways (a member name split by case)
        f_ = k.replace(" ", "")
        if f_ in flat and flat[f_] in by:
            e, into = by.pop(k), by[flat[f_]]
            into["names"] += e["names"]
            into["xnames"] = into.get("xnames", []) + e.get("xnames", [])
            into["via"] |= e["via"]
            into["x"] = into["x"] or e["x"]
            into["s"] += [y for y in e["s"] if y["t"] not in (z["t"] for z in into["s"])]
            into["stated"] += e["stated"]
        else:
            flat[f_] = k
    for k in sorted(by, key=len):                        # a short form of a longer name the same filings use
        longer = [kk for kk in by if kk != k and kk.startswith(k + " ")]
        if len(longer) == 1 and k in by:
            e, into = by.pop(k), by[longer[0]]
            into["names"] += e["names"]
            into["via"] |= e["via"]
            into["x"] = into["x"] or e["x"]
            into["s"] += [y for y in e["s"] if y["t"] not in (z["t"] for z in into["s"])]
            into["stated"] += e["stated"]
    out = []
    for k, e in by.items():
        if not k:
            continue
        counts = defaultdict(float)
        for n in e["names"]:
            counts[n] += 1
        for n in e.get("xnames") or []:
            counts[n] -= 0.1                             # a member name split by case loses a tie with the text's spelling
        name = min(counts, key=lambda n: (-counts[n], len(n)))                      # the form the filing uses most
        cik = tk = None
        if names is not None:
            cik = _resolve(names, counts, key_of(name) or k)
            if cik == self_cik:
                continue
            tk = names.ticker.get(cik) if cik else None
        best = _best(e["x"], e["stated"])
        lead = (best or {}).get("t")
        sents = sorted(e["s"], key=lambda y: (y["t"] != lead, y["_r"]))[:4]
        for y in sents:
            del y["_r"]
            if y.get("url") == e.get("url"):
                for kk in ("form", "filed", "url"):
                    y.pop(kk, None)
        out.append({"key": key_of(name) or k, "name": name, **({"cik": cik, "t": tk} if cik else {}), "via": sorted(e["via"]),
                    "x": e["x"], "s": sents, "best": ({kk: v for kk, v in best.items() if kk != "t"} if best else None),
                    "form": e["form"], "filed": e["filed"], "url": e["url"]})
    out.sort(key=lambda e: (-(abs((e.get("best") or {}).get("usd") or 0)), "xbrl" not in e["via"], e["name"]))
    return out


def _financial(p):
    try:
        sic = int((p or {}).get("sic") or 0)
    except (TypeError, ValueError):
        sic = 0
    return sic in FINANCIAL and int((p or {}).get("cik") or 0) not in OPERATING_INVESTORS


def company_doc(cik, rec, names=None):
    inv, invr = rec.get("inv") or {}, rec.get("invr") or {}
    p = rec.get("profile") or {}
    rows = _rows(inv, invr)
    nm = named(invr, names, cik)
    if not rows and not nm:
        return None
    reads = [{k: r.get(k) for k in ("form", "filed", "url", "end", "accn")} for r in invr.values() if r and r.get("v") == READ_V]
    return {"cik": cik, "name": p.get("name"), "t": (p.get("tickers") or [None])[0], "sic": p.get("sic"),
            "sector": p.get("sector"), "fin": _financial(p), "currency": rec.get("currency") or "USD",
            "q": rows[-KEEP_Q:], "ttm": inv.get("ttm") or {}, "src": inv.get("src") or {}, "named": nm,
            "read": sorted(reads, key=lambda r: r.get("filed") or "", reverse=True)}


def _year_ago(rows, role):
    if not rows or rows[-1].get(role) is None:
        return None
    e0 = _d(rows[-1]["end"])
    for r in rows:
        if r.get(role) is not None and 340 <= (e0 - _d(r["end"])).days <= 390:
            return r[role]
    return None


def build(store, out, index, today=None):
    """data/investors/index.json, data/investors/c/<cik>.json and data/investors/investees.json."""
    from .custnet import Names
    st = store.state
    rows_n = (st.get("sec_names") or {}).get("rows") or []
    revenue = {int(p["cik"]): p.get("revenue") or 0 for p in index if p.get("cik")}
    if not rows_n:
        rows_n = [[p["cik"], p.get("ticker") or "", p.get("name") or ""] for p in index if p.get("cik")]
    names = Names(rows_n, revenue)
    root = os.path.join(out, "investors", "c")
    os.makedirs(root, exist_ok=True)
    keep, table, rev_ix = set(), [], defaultdict(list)
    read_n = 0
    for p in index:
        cik = int(p["cik"])
        rec = store.company(cik)
        if rec.get("currency") not in (None, "USD"):
            continue                                                 # us-gaap dollars only, for one ranking
        if any((r or {}).get("v") == READ_V for r in (rec.get("invr") or {}).values()):
            read_n += 1
        doc = company_doc(cik, rec, names)
        if not doc:
            continue
        with open(os.path.join(root, f"{cik}.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"))
        keep.add(cik)
        q = doc["q"]
        last = q[-1] if q else {}
        tot = sum(last.get(k) or 0 for k in ("nm", "em", "fv", "lt"))
        ya = [_year_ago(q, k) for k in ("nm", "em", "fv", "lt")]
        tot_ya = sum(v or 0 for v in ya) if any(v is not None for v in ya) else None
        ttm = doc["ttm"]
        share = (ttm["g"] / ttm["pti"]) if ttm.get("g") is not None and (ttm.get("pti") or 0) > 0 else None
        table.append([cik, doc["t"], doc["name"], doc.get("sector"), 1 if doc["fin"] else 0, last.get("end"),
                      last.get("nm"), last.get("em"), last.get("fv"), tot or None, tot_ya, ttm.get("g"), ttm.get("pti"),
                      ttm.get("emi"), round(share, 4) if share is not None else None, len(doc["named"]),
                      [[n["name"], n.get("t"), n["key"]] for n in doc["named"][:4]]])
        for n in doc["named"]:
            rev_ix[n["key"]].append({"cik": cik, "t": doc["t"], "name": doc["name"], "fin": doc["fin"], "via": n["via"],
                                     "best": n.get("best"), "form": n["form"], "filed": n["filed"], "url": n["url"],
                                     "q": (((n.get("best") or {}).get("t") or (n["s"][0]["t"] if n["s"] else ""))[:420] or None),
                                     "nm": n["name"],
                                     **({"icik": n["cik"], "it": n.get("t")} if n.get("cik") else {})})
    for f in os.listdir(root):
        if f.endswith(".json") and f[:-5].isdigit() and int(f[:-5]) not in keep:
            os.remove(os.path.join(root, f))
    table.sort(key=lambda r: -(r[9] or 0))
    inv_rows = []
    for k, xs in rev_ix.items():
        counts = defaultdict(int)
        for x in xs:
            counts[x["nm"]] += 1
        name = min(counts, key=lambda n: (-counts[n], len(n)))
        icik = next((x["icik"] for x in xs if x.get("icik")), None)
        xs.sort(key=lambda x: -(abs((x.get("best") or {}).get("usd") or 0)))
        inv_rows.append({"key": k, "name": name, **({"cik": icik, "t": next((x.get("it") for x in xs if x.get("it")), None)} if icik else {}),
                         "n": len({x["cik"] for x in xs}), "inv": [{kk: v for kk, v in x.items() if kk not in ("nm", "icik", "it")} for x in xs]})
    inv_rows.sort(key=lambda r: (-r["n"], -max((abs((x.get("best") or {}).get("usd") or 0) for x in r["inv"]), default=0), r["name"]))
    gen = (today or dt.date.today()).isoformat()
    fields = ["cik", "t", "name", "sector", "fin", "end", "nm", "em", "fv", "total", "total_ya", "g_ttm", "pti_ttm", "emi_ttm",
              "g_share", "named", "top"]
    with open(os.path.join(out, "investors", "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": gen, "companies": len(table), "read": read_n, "fields": fields, "rows": table,
                   "investees": [{"key": r["key"], "name": r["name"], "n": r["n"], **({"cik": r["cik"], "t": r.get("t")} if r.get("cik") else {}),
                                  "by": [x["t"] or x["name"] for x in r["inv"][:5]]} for r in inv_rows[:60]]},
                  fh, separators=(",", ":"))
    with open(os.path.join(out, "investors", "investees.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": gen, "rows": inv_rows}, fh, separators=(",", ":"))
    print(f"::notice::investments: {len(table)} companies with an investment balance or a named investee; {read_n} with "
          f"filings read; {len(inv_rows)} named investees")
    return table


# ---------------------------------------------------------------------------------------------------- one company, by hand
def _main(argv):
    from . import sec, dims
    cik = int(argv[0])
    raw = sec.get_json(sec.companyfacts_url(cik))
    fx = F.index_facts(raw)
    sub = sec.get_json(sec.submissions_url(cik))
    print(json.dumps(compute(fx), indent=1)[:4000])
    r = sub["filings"]["recent"]
    rows = [dict(zip(r.keys(), v)) for v in zip(*r.values())]
    row = next(x for x in rows if x["form"] in ("10-Q", "10-K"))
    url = sec.doc_url(cik, row["accessionNumber"], row["primaryDocument"])
    iu, lu = dims.find_files(cik, row["accessionNumber"])
    rd = read(cik, row["accessionNumber"], row["form"], row["filingDate"], url, sec.get(url), sec.get(iu) if iu else None,
              sec.get(lu) if lu else None, row.get("reportDate"), own_names(sub.get("name"), sub.get("tickers")))
    print(json.dumps(rd, indent=1)[:8000])


if __name__ == "__main__":
    _main(sys.argv[1:])
