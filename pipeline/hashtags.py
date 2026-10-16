"""Hashtags for X posts: a few, picked from larger pools by the post's kind, the event, the company's industry and a
general tag that takes turns, so posts do not all end the same way.

    pick("earnings", profile, key="NVDA:2026-07-26")      -> ["#earnings", "#semiconductors", "#StockMarket"]
    pick("8k", profile, topic="#MergersAndAcquisitions")   -> ["#8K", "#MergersAndAcquisitions", "#pharma"]

Order: the kind's own tag, the event's topic, the industry (from the SIC code; else the sector), one general tag (chosen
by the post's key, so the same post always gets the same one), then the kind's other tags and more general ones until
"hashtags_max" is reached (config/x.json; 3 by default). Each of the four kinds of tag can be switched off
("hashtag_parts"); the owner page's "X posts" options (pipeline/xprefs.py) win over config/x.json. Cashtags are not
hashtags and are never touched here.
"""
import hashlib
import json
import os

from .sectors import sector_of

CFG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "x.json")
MAX = 3
PARTS = {"kind": True, "topic": True, "industry": True, "general": True}
KINDS = {
    "earnings": ["#earnings", "#EarningsSeason"],
    "13f": ["#13F", "#hedgefunds", "#smartmoney"],
    "insider": ["#InsiderBuying", "#Form4", "#insiders"],
    "insider_sale": ["#InsiderSelling", "#Form4", "#insiders"],
    "congress": ["#CongressTrades", "#STOCKAct", "#PoliticianTrades"],     # US House periodic transaction reports
    "officials": ["#PoliticianTrades", "#disclosures"],                     # other jurisdictions' officials
    "8k": ["#8K", "#SEC"],
    "movers": ["#StockMovers", "#trading"],
    "capital": ["#buybacks", "#dividends"],
}
GENERAL = ["#stocks", "#investing", "#StockMarket", "#markets", "#investors", "#finance"]
# more general tags the owner page offers to pick from ("X posts"); any other tag can be typed in
CANDIDATES = GENERAL + ["#fintwit", "#WallStreet", "#StocksToWatch", "#trading", "#investment", "#economy", "#business",
                        "#money", "#valueinvesting", "#dividendinvesting", "#growthstocks", "#NASDAQ", "#SP500",
                        "#DowJones", "#stockmarketnews", "#financialnews", "#equities", "#wealth"]
# SIC code ranges, the specific before the broad
INDUSTRY = [
    (3674, 3674, "#semiconductors"), (7371, 7372, "#software"), (3570, 3579, "#tech"), (3660, 3679, "#tech"),
    (7370, 7379, "#tech"), (2834, 2834, "#pharma"), (2835, 2836, "#biotech"), (8731, 8731, "#biotech"),
    (3841, 3845, "#medtech"), (8000, 8099, "#healthcare"), (6021, 6036, "#banks"), (6311, 6411, "#insurance"),
    (6798, 6798, "#REITs"), (6770, 6770, "#SPAC"), (6199, 6282, "#finance"), (1311, 1389, "#oil"), (2911, 2911, "#oil"),
    (1040, 1040, "#gold"), (1000, 1499, "#mining"), (4911, 4991, "#utilities"), (3711, 3716, "#autos"),
    (3720, 3729, "#aerospace"), (3760, 3769, "#aerospace"), (3812, 3812, "#defense"), (4512, 4513, "#airlines"),
    (5812, 5812, "#restaurants"), (5961, 5961, "#ecommerce"), (5200, 5999, "#retail"), (4812, 4813, "#telecom"),
    (4841, 4841, "#media"), (7812, 7841, "#streaming"), (2080, 2086, "#beverages"),
]
SECTOR = {"technology": "#tech", "communication": "#media", "consumer-disc": "#consumer", "consumer-staples": "#consumer",
          "health": "#healthcare", "financials": "#finance", "real-estate": "#realestate", "energy": "#energy",
          "materials": "#materials", "industrials": "#industrials", "utilities": "#utilities"}


def industry_tag(profile):
    """The industry's tag from the SIC code, else the sector's, else None."""
    p = profile or {}
    try:
        sic = int(p.get("sic"))
    except (TypeError, ValueError):
        sic = None
    if sic is not None:
        for lo, hi, tag in INDUSTRY:
            if lo <= sic <= hi:
                return tag
    sec = p.get("sector") if p.get("sector") in SECTOR else sector_of(sic) if sic is not None else None
    return SECTOR.get(sec)


_cfg = None


def settings():
    """("hashtags_max", the general pool "hashtags", "hashtag_parts") from config/x.json with the owner's options on top,
    read once; the defaults without them. An empty pool means no general tag."""
    global _cfg
    if _cfg is None:
        try:
            c = json.load(open(CFG, encoding="utf-8"))
        except (OSError, ValueError):
            c = {}
        from . import xprefs
        c = xprefs.overlay(c)
        parts = {**PARTS, **{k: v for k, v in (c.get("hashtag_parts") or {}).items() if k in PARTS and isinstance(v, bool)}}
        _cfg = (int(c.get("hashtags_max", MAX)), clean(c["hashtags"]) if isinstance(c.get("hashtags"), list) else GENERAL, parts)
    return _cfg


def clean(tags):
    out = []
    for t in tags or []:
        if not t:
            continue
        t = "#" + str(t).lstrip("#").strip()
        if len(t) > 1 and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out


def pick(kind, profile=None, topic=None, key="", n=None, general=None, lead=None, parts=None):
    """Up to n hashtags for one post (see the module docstring). `general` replaces the general pool (config/x.json
    "hashtags"; [] for none); `lead` replaces the kind's own first tag (config/x.json "headline_tag" for earnings
    posts); `parts` switches kinds of tag off, e.g. {"industry": False}."""
    n_cfg, pool_cfg, parts_cfg = settings()
    n = n_cfg if n is None else max(0, int(n))
    use = {**parts_cfg, **{k: v for k, v in (parts or {}).items() if k in PARTS}}
    own = clean(([lead] if lead else []) + KINDS.get(kind, [])) if use["kind"] else []
    pool = (pool_cfg if general is None else clean(general)) if use["general"] else []
    start = int(hashlib.sha1(str(key).encode()).hexdigest(), 16) % len(pool) if pool else 0
    turn = pool[start:] + pool[:start]
    order = (own[:1] + (clean([topic]) if topic and use["topic"] else []) + (clean([industry_tag(profile)]) if use["industry"] else [])
             + turn[:1] + own[1:] + turn[1:])
    return clean(order)[:n]
