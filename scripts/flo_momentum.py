"""Flo five-minute momentum relay. Strict time-aligned minute bars, no fake realtime.
Uses Alpaca server-side credentials + curated constituent memberships and stores a
single JSON snapshot in Supabase. Historical snapshots are never implied to be live.
Run: python scripts/flo_momentum.py --once
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone, time as dtime
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
NY = ZoneInfo("America/New_York")
UNIVERSES = {"sp500": "S&P 500", "russell1000": "Russell 1000", "russell2000": "Russell 2000"}
PROVIDER = "alpaca"
BAR_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
SCHEMA = 1

def request(url, headers=None, payload=None):
    req = Request(url, data=payload, headers=headers or {}, method="POST" if payload else "GET")
    with urlopen(req, timeout=25) as r:
        body = r.read(3_000_000).decode("utf-8")
        return json.loads(body) if body.strip() else {}

def iso(v):
    if not isinstance(v, str):
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError, OverflowError):
        return None

def stamp(d):
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def ticker(v):
    t = str(v or "").upper().replace("/", "-").strip()
    return t if SYMBOL.fullmatch(t) else ""

class WikiMembers(HTMLParser):
    def __init__(self):
        super().__init__()
        self.intable = self.inrow = self.incell = False
        self.row = []
        self.parts = []
        self.rows = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "constituents":
            self.intable = True
        if not self.intable:
            return
        if tag == "tr":
            self.inrow = True
            self.row = []
        if self.inrow and tag in ("td", "th"):
            self.incell = True
            self.parts = []

    def handle_data(self, data):
        if self.incell:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if not self.intable:
            return
        if tag in ("td", "th") and self.incell:
            self.row.append("".join(self.parts).strip())
            self.incell = False
        if tag == "tr" and self.inrow:
            if self.row:
                self.rows.append(self.row)
            self.inrow = False
        if tag == "table":
            self.intable = False

def sp500_from_wikipedia(now, fetch=None):
    """Best-effort current member fetch; never treat 2024 local file as current."""
    fetch = fetch or request_text
    html = fetch("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    parser = WikiMembers()
    parser.feed(html)
    members = sorted({ticker(row[0]) for row in parser.rows[1:] if row})
    members = [m for m in members if m]
    if not 450 <= len(members) <= 520:
        raise ValueError("S&P 500 membership unverified or malformed; scan disabled")
    return {"source": "Wikipedia current S&P 500 constituent table", "as_of": now.date().isoformat(),
            "symbols": members, "status": "current_snapshot_unofficial"}

def request_text(url):
    req = Request(url, headers={"User-Agent": "FilingFlowsResearch/1.0 (index constituency transparency)"})
    with urlopen(req, timeout=20) as resp:
        return resp.read(2_500_000).decode("utf-8")

def curated_universe(path, now, max_age_days=110, minimum=600, maximum=3000):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        asof = datetime.fromisoformat(obj["as_of"]).date()
        src = str(obj.get("source", "")).strip()
        rows = obj["symbols"]
        if not src or not isinstance(rows, list) or not (minimum <= len(rows) <= maximum):
            return None
        if not (0 <= (now.date()-asof).days <= max_age_days):
            return None
        names = sorted({ticker(x) for x in rows})
        names = [x for x in names if x]
        if not minimum <= len(names) <= maximum or len(names) / len(rows) < .95:
            return None
        return {"source": src, "as_of": obj["as_of"], "symbols": names,
                "status": "licensed_or_curated_user_supplied"}
    except (OSError, ValueError, KeyError, TypeError):
        return None

def memberships(now, fetch_sp500=None, base=None):
    base = base or ROOT / "config" / "flo-market-universes"
    scopes = {}
    try:
        scopes["sp500"] = sp500_from_wikipedia(now, fetch_sp500)
    except (HTTPError, URLError, OSError, ValueError) as error:
        scopes["sp500"] = {"status": "unavailable", "reason": "Current constituent data unavailable; not using 2024 history",
                           "symbols": [], "source": "Wikipedia (request failed)", "as_of": None}
    for name in ("russell1000", "russell2000"):
        expected = (900, 1100) if name == "russell1000" else (1800, 2200)
        obj = curated_universe(base / (name+".json"), now,
                               minimum=expected[0], maximum=expected[1])
        scopes[name] = obj or {"status": "unavailable", "reason": "Provide an accurate, dated and licensed index membership file",
                               "symbols": [], "source": "", "as_of": None}
    return scopes

def batches(data, size=150):
    seq = list(data)
    for i in range(0, len(seq), size):
        yield seq[i:i+size]

def alpaca_bars(symbols, now, feed, key, secret, fetch=request):
    """Exact minute bars for the last 10 minutes. Pagination consumed in full.
    API permits feed=iex (single exchange), sip (licensed), delayed_sip.
    """
    if feed not in ("iex", "sip", "delayed_sip"):
        raise ValueError("Invalid Alpaca feed")
    if not key or not secret:
        raise ValueError("Alpaca keys missing; never fall back to EOD quotes")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}
    shift = 16 if feed == "delayed_sip" else 1
    end = (now-timedelta(minutes=shift)).replace(second=0, microsecond=0)
    start = end-timedelta(minutes=10)
    data = {}
    for chunk in batches(sorted(set(symbols)), 150):
        query = {"symbols": ",".join(chunk), "timeframe": "1Min", "start": stamp(start),
                 "end": stamp(end), "feed": feed, "limit": 10000, "adjustment": "raw"}
        token = None
        for page in range(15):
            if token:
                query["page_token"] = token
            else:
                query.pop("page_token", None)
            try:
                result = fetch(BAR_ENDPOINT+"?"+urlencode(query), headers)
            except HTTPError as err:
                # Fail closed on auth, plan entitlement, quota or upstream trouble.
                raise RuntimeError("Alpaca minute bars failed: HTTP "+str(err.code)) from err
            for symbol, entries in (result.get("bars") or {}).items():
                if symbol in chunk and isinstance(entries, list):
                    data.setdefault(symbol, []).extend(entries[:10000])
            token = result.get("next_page_token")
            if not token:
                break
        else:
            raise RuntimeError("Alpaca pagination incomplete; refuse false top gainer ranking")
    return data

def regular_minute(t):
    v=t.astimezone(NY)
    return v.weekday()<5 and dtime(9,30) <= v.time().replace(tzinfo=None) < dtime(16,0)

def calculate(bars, now, feed="sip", window=5):
    """Only exact 5-minute bar-close-to-bar-close comparisons are reported."""
    if feed not in ("iex", "sip", "delayed_sip"):
        raise ValueError("Unsupported minute-bar feed")
    max_delay = 23 if feed == "delayed_sip" else 4
    output={}
    for sym, rows in bars.items():
        if not ticker(sym) or not isinstance(rows,list):
            continue
        clean={}
        for bar in rows:
            t=iso(bar.get("t")) if isinstance(bar,dict) else None
            try:
                c=float(bar["c"]); v=float(bar["v"])
            except (TypeError, ValueError, KeyError, OverflowError):
                continue
            if t is None or not regular_minute(t) or not (0<c<1e8) or not (0<=v<1e12) or not math.isfinite(c*v):
                continue
            try:
                vw = float(bar.get("vw"))
            except (TypeError, ValueError, OverflowError):
                vw = None
            known_vwap = vw is not None and math.isfinite(vw) and 0 < vw < 1e8
            clean[t] = dict(c=c, v=v, dollar_price=vw if known_vwap else c,
                            has_vwap=known_vwap)
        if not clean:
            continue
        end=max(clean)
        if not timedelta(0) <= now-end <= timedelta(minutes=max_delay):
            continue
        prior=end-timedelta(minutes=window)
        if prior not in clean:
            continue
        # A valid exact 5-minute return does not require trades every minute,
        # but turnover is incomplete if one or more of those minute bars is absent.
        needed=[prior+timedelta(minutes=i) for i in range(1,window+1)]
        valid_bars=[clean[t] for t in needed if t in clean]
        p=clean[prior]["c"]
        move=(clean[end]["c"]/p-1)*100
        if not math.isfinite(move) or not -99<move<1000:
            continue
        result={"ticker":sym,"asof":stamp(end),"prev_asof":stamp(prior),
                "price":round(clean[end]["c"],4),"five_min_pct":round(move,4),
                "turnover_5m_usd":round(sum(x["dollar_price"]*x["v"] for x in valid_bars),2),
                "turnover_estimated":len(valid_bars)!=window or any(not x["has_vwap"] for x in valid_bars),
                "volume_5m":int(sum(x["v"] for x in valid_bars)),
                "volume_complete":len(valid_bars)==window}
        output[sym]=result
    return output

def rank_universes(universes, movers, previous, now, feed, top=60):
    result={}
    old=previous if isinstance(previous,dict) else {}
    old_asof=iso(old.get("generated_at"))
    chained=(old_asof is not None and timedelta(minutes=1)<now-old_asof<=timedelta(minutes=11)
             and old.get("feed")==feed)
    prev_top=old.get("universes") or {}
    for name,definition in universes.items():
        members=definition.get("symbols") or []
        status=definition.get("status","unavailable")
        covered=[movers[t] for t in members if t in movers]
        covered.sort(key=lambda r:(-r["five_min_pct"],-r["turnover_5m_usd"],r["ticker"]))
        candidates=[dict(x) for x in covered[:top]]
        prior=(prev_top.get(name) or {}).get("leaders") or []
        prior_map={r["ticker"]:r for r in prior if isinstance(r,dict) and ticker(r.get("ticker"))}
        for idx,row in enumerate(candidates,1):
            before=prior_map.get(row["ticker"]) if chained else None
            row["rank"]=idx
            row["previous_rank"]=before.get("rank") if before else None
            row["streak"]=min(100, int(before.get("streak",0))+1) if before else 1
            row["new_entry"]=not bool(before)
        coverage=round(len(covered)/len(members)*100,1) if members else 0
        result[name]={
            "label":UNIVERSES[name],"membership_asof":definition.get("as_of"),
            "membership_source":definition.get("source"),
            "membership_status":status,
            "universe_size":len(members),"symbols_with_exact_5m_bars":len(covered),
            "coverage_pct":coverage,
            "ranking_status":"unavailable" if not members else "partial" if coverage<80 else "complete_enough",
            "leaders":candidates
        }
    return result

def read_previous(url, service, fetch=request):
    if not url or not service:
        return {}
    try:
        rows=fetch(url.rstrip("/")+"/rest/v1/flo_momentum_scan?name=eq.latest&select=payload",
                   {"apikey":service,"Authorization":"Bearer "+service})
        return rows[0].get("payload",{}) if isinstance(rows,list) and rows else {}
    except (OSError,HTTPError,URLError,ValueError,KeyError,IndexError):
        return {}

def publish(url, service, payload, public, fetch=request):
    if not url or not service:
        raise ValueError("Missing Supabase server credentials")
    data=json.dumps({"name":"latest","payload":payload,"is_public":bool(public),
                     "updated_at":payload["generated_at"]},separators=(",",":")).encode()
    return fetch(url.rstrip("/")+"/rest/v1/flo_momentum_scan?on_conflict=name",
                 {"apikey":service,"Authorization":"Bearer "+service,
                  "Content-Type":"application/json","Prefer":"resolution=merge-duplicates,return=minimal"},data)

def run(now=None, provider_fetch=request, universe_fetch=None, directory=None):
    now=now or datetime.now(timezone.utc)
    key=os.environ.get("ALPACA_API_KEY_ID","")
    secret=os.environ.get("ALPACA_API_SECRET_KEY","")
    feed=os.environ.get("FLO_MINUTE_FEED","iex")
    if feed not in ("iex","sip","delayed_sip"):
        raise ValueError("Select iex, sip or delayed_sip")
    scopes=memberships(now,universe_fetch,directory)
    symbols=sorted(set().union(*(set(x.get("symbols") or []) for x in scopes.values())))
    if not symbols:
        raise RuntimeError("No fresh valid index memberships; refusing fabricated ranking")
    bars=alpaca_bars(symbols,now,feed,key,secret,provider_fetch)
    moves=calculate(bars,now,feed)
    url=os.environ.get("SUPABASE_URL","")
    service=os.environ.get("SUPABASE_SERVICE_KEY","")
    previous=read_previous(url,service)
    result={"schema":SCHEMA,"generated_at":stamp(now),"provider":PROVIDER,
            "feed":feed,"coverage_warning":"IEX is ONE EXCHANGE, not consolidated US volume/pricing."
                if feed=="iex" else "SIP requires provider authorization and redistribution rights." if feed=="sip"
                else "15-minute-delayed SIP is NOT real-time.",
            "window_minutes":5,"poll_hint_seconds":60,"universe_definitions":UNIVERSES,
            "universes":rank_universes(scopes,moves,previous,now,feed)}
    # Market data redistribution is subject to provider contracts. Publication
    # remains disabled unless the operator independently affirms authorization.
    allowed=os.environ.get("FLO_MINUTE_PUBLIC_LICENSED","").lower()=="true"
    publish(url,service,result,allowed)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--once",action="store_true",help="Run a single protected producer iteration")
    a=p.parse_args()
    if not a.once:
        p.error("Pass --once")
    try:
        obj=run()
        print(json.dumps({"generated_at":obj["generated_at"],"feed":obj["feed"],
                          "universe_status":{k:{"status":v["ranking_status"],"coverage":v["coverage_pct"],
                                                "leaders":len(v["leaders"])}
                                             for k,v in obj["universes"].items()}}))
    except (ValueError,RuntimeError,HTTPError,URLError,OSError) as e:
        print("Flo minute scanner unavailable: "+str(e)[:160],file=sys.stderr)
        sys.exit(2)

if __name__=="__main__":
    main()
