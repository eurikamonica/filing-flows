"""E-mail alerts for readers who signed up on the site: every new chart that matches what they follow, with the chart
itself, the analysis, what changed against the year-ago quarter and a quote from the filing. No language model.

Accounts and preferences live in Supabase (supabase/schema.sql). This script reads them with the secret
(service-role) key, so it runs only where that key is kept secret: GitHub Actions, or your own computer.

    python -m pipeline.notify --site _site                     # send what is due now
    python -m pipeline.notify --site _site --dry-run           # print who would get what; send nothing
    python -m pipeline.notify --site https://you.github.io/filing-flows/      # read the published site instead

Environment
    SUPABASE_URL, SUPABASE_SERVICE_KEY         project URL and secret key (sb_secret_... or the legacy service_role JWT)
    MAIL_USERNAME, MAIL_PASSWORD               SMTP login (Gmail address + app password by default)
    SMTP_HOST, SMTP_PORT                       default smtp.gmail.com, 465 (587 uses STARTTLS)
    MAIL_FROM                                  default "Filing Flows <MAIL_USERNAME>"
    SITE_URL                                   public address of the site, for links (default X_SITE_URL)
    MAIL_DAILY_LIMIT                           most alert e-mails in 24 hours (default 400; Gmail allows about 500,
                                               and the sign-in codes go through the same account)
    DIGEST_HOUR_UTC                            when daily digests go out (default 22 = 6 pm New York in summer)
"""
import argparse
import datetime as dt
import html as H
import json
import os
import re
import sys
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

import requests

from . import social, text

MAX_AGE_DAYS = 3            # charts for filings older than this are not sent
FULL_ITEMS = 6              # charts shown in full per e-mail; the rest are listed with a link
REQUEST_FULL_ITEMS = 10     # reports a reader asked for are all shown in full (up to this many per e-mail)
REQUEST_ATTEMPTS = 3
STALE_CLAIM_MINUTES = 30
SAME_QUARTER_DAYS = 10      # an 8-K quarter and the 10-Q/10-K that replaces it count as one item
KEEP_DELIVERIES_DAYS = 120
MAIL_MAX_BYTES = 15_000_000  # images and attachments per e-mail (about 20 MB once encoded; Gmail takes 25 MB)


def env_int(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def mask(addr):
    """Public Actions logs must not show readers' addresses."""
    name, _, domain = str(addr).partition("@")
    return f"{name[:2]}***@{domain[:1]}***" if domain else "***"


def setting(name, url=False):
    """An environment setting as pasted into GitHub, forgiving the usual slips: quotes, spaces, a whole
    "NAME = value" line, and for the project URL a trailing /rest/v1 copied from the API page."""
    raw = os.environ.get(name, "")
    v = raw.strip().strip("'\"").strip()
    m = re.match(r"^[A-Z][A-Z0-9_]*\s*[=:]\s*(.*)$", v)
    if m:
        v = m.group(1).strip().strip("'\"").strip()
    if url:
        v = v.rstrip("/")
        for tail in ("/rest/v1", "/auth/v1"):
            if v.endswith(tail):
                v = v[: -len(tail)].rstrip("/")
    if v != raw:
        shown = f"using {v}" if url else "using the value inside it"     # never print any part of a key
        print(f"::warning::{name} had extra text around the value; {shown}. Fix it in Settings → Secrets and variables → Actions.")
    return v


def parse_ts(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------ Supabase (PostgREST) with the secret key
class Supa:
    PAGE = 1000

    def __init__(self, url, key, session=None):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.key = key
        self.s = session or requests.Session()

    def _h(self, **extra):
        h = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):                 # legacy JWT keys also go in Authorization
            h["Authorization"] = f"Bearer {self.key}"
        h.update(extra)
        return h

    def _check(self, r):
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
        return r

    def select(self, table, params):
        rows, off = [], 0
        while True:
            p = dict(params, limit=str(self.PAGE), offset=str(off))
            got = self._check(self.s.get(self.base + table, params=p, headers=self._h(), timeout=60)).json()
            rows += got
            if len(got) < self.PAGE:
                return rows
            off += len(got)

    def insert(self, table, rows):
        if rows:
            self._check(self.s.post(self.base + table, data=json.dumps(rows), timeout=60,
                                    headers=self._h(Prefer="resolution=ignore-duplicates,return=minimal")))

    def update(self, table, params, fields):
        """PATCH the matching rows; returns the rows as updated."""
        r = self._check(self.s.patch(self.base + table, params=params, data=json.dumps(fields), timeout=60,
                                     headers=self._h(Prefer="return=representation")))
        return r.json() if r.text else []

    def delete(self, table, params):
        self._check(self.s.delete(self.base + table, params=params, headers=self._h(Prefer="return=minimal"), timeout=60))


# ------------------------------------------------------------------ the site's data (built folder or published URL)
class Site:
    def __init__(self, src):
        self.src = str(src)
        self.remote = bool(re.match(r"https?://", self.src))
        self._cache = {}

    def json(self, path):
        if path not in self._cache:
            if self.remote:
                r = requests.get(self.src.rstrip("/") + "/data/" + path, timeout=60)
                r.raise_for_status()
                self._cache[path] = r.json()
            else:
                with open(os.path.join(self.src, "data", path)) as f:
                    self._cache[path] = json.load(f)
        return self._cache[path]

    def quarter(self, e):
        c = self.json(f"c/{e['cik']}.json")
        q = next((x for x in c["quarters"] if x["end"] == e["end"]), c["quarters"][0])
        return c, q


# ------------------------------------------------------------------ who gets what
def is_prelim(e):
    return e.get("form") == "8-K" or bool(e.get("prelim"))


def is_year(x):
    """A full fiscal year (10-K annual chart) rather than a quarter."""
    return (x or {}).get("period") == "fy"


def item_key(e):
    """"<cik>:<quarter end>", plus ":8-K" for a chart read from an earnings release, ":fy" for a full fiscal year."""
    return f"{int(e['cik'])}:{e['end']}" + (":8-K" if is_prelim(e) else ":fy" if is_year(e) else "")


def _split(k):
    parts = k.split(":")
    return int(parts[0]), parts[1], len(parts) > 2 and parts[2] == "8-K"


def norm_ticker(t):
    return str(t).strip().upper().replace(".", "-")


def release_sent(keys, e):
    """When the reader got the 8-K chart of the quarter this 10-Q/10-K belongs to (keys: {item: sent_at}), or None."""
    e0 = dt.date.fromisoformat(e["end"])
    for k, at in dict(keys).items():
        cik, end, pre = _split(k)
        if pre and cik == int(e["cik"]) and abs((dt.date.fromisoformat(end) - e0).days) <= SAME_QUARTER_DAYS:
            return at or True
    return None


def delivered(keys, e, final_too=True):
    """Sent already? With final_too off, the 10-Q/10-K that follows an 8-K chart the reader got counts as sent."""
    if item_key(e) in keys:
        return True
    return not is_prelim(e) and not final_too and release_sent(keys, e) is not None


def bn(v):
    v = v / 1e9
    return f"${v:.0f}B" if v >= 10 else f"${v:.1f}B".replace(".0B", "B")


def reasons(sub, e, sector_names):
    out = []
    if e.get("ticker") and norm_ticker(e["ticker"]) in {norm_ticker(t) for t in sub.get("tickers") or []}:
        out.append(f"you follow {e['ticker']}")
    if e.get("sector") in (sub.get("sectors") or []):
        out.append(f"you follow the {sector_names.get(e['sector'], e['sector'])} sector")
    if sub.get("all_above") and (e.get("revenue") or 0) >= (sub.get("min_revenue") or 0):
        out.append(f"you follow every company with quarterly revenue of at least {bn(sub.get('min_revenue') or 0)}")
    if sub.get("starred") and e.get("starred"):
        out.append("you follow the site's starred companies")
    return out


def digest_slot(now, hour):
    return now.replace(hour=hour, minute=0, second=0, microsecond=0)


def is_due(sub, last_sent, now, hour):
    if sub.get("frequency") != "daily":
        return True
    slot = digest_slot(now, hour)
    if now < slot:
        return False
    return last_sent is None or last_sent < slot


def plan(subs, deliveries, ix, now, hour=22, max_age=MAX_AGE_DAYS):
    """-> [(subscription, [(index entry, reasons)])] for every reader with something due now."""
    names = ix.get("sector_names") or {}
    recent = [e for e in ix["companies"]
              if e.get("filed") and (now.date() - dt.date.fromisoformat(e["filed"])).days <= max_age]
    recent.sort(key=lambda e: (e.get("filed") or "", e.get("revenue") or 0), reverse=True)
    by_user, last = {}, {}
    for d in deliveries:
        by_user.setdefault(d["user_id"], {})[d["item"]] = d["sent_at"]
        t = parse_ts(d["sent_at"])
        if d["user_id"] not in last or t > last[d["user_id"]]:
            last[d["user_id"]] = t
    out = []
    for sub in subs:
        if not sub.get("email_on") or not sub.get("email"):
            continue
        since = parse_ts(sub["created_at"]).date() - dt.timedelta(days=1) if sub.get("created_at") else None
        keys = by_user.get(sub["user_id"], {})
        final_too = sub.get("final_too") is not False
        items = []
        for e in recent:
            if since and dt.date.fromisoformat(e["filed"]) < since:
                continue                          # nothing from before the reader signed up
            why = reasons(sub, e, names)
            if why and not delivered(keys, e, final_too):
                got = None if is_prelim(e) else release_sent(keys, e)
                items.append((dict(e, _release_sent=got) if got else e, why))
        if items and is_due(sub, last.get(sub["user_id"]), now, hour):
            out.append((sub, items))
    return out


def emails_last_24h(rows, now):
    """rows: deliveries and sent requests; every e-mail stamps all its rows with the same time."""
    return len({(d["user_id"], d["sent_at"]) for d in rows
                if d.get("sent_at") and parse_ts(d["sent_at"]) >= now - dt.timedelta(hours=24)})


# ------------------------------------------------------------------ the e-mail
INK, INK2, MUTED, ACCENT, LINE, PAPER, GROUND = "#1d1d1b", "#3d3c39", "#6b6a66", "#17734a", "#e3e1db", "#fcfcfb", "#f3f2ee"
FONT = "Helvetica,Arial,sans-serif"


def pct(v):
    if v is None:
        return ""
    return f"{'+' if v >= 0 else '−'}{abs(v):.0f}%"


def headline(e, q):
    h = q.get("headline") or {}
    parts = [f"Revenue {h.get('rev_fmt') or e.get('rev')}" + (f" ({pct(h.get('yoy'))} Y/Y)" if h.get("yoy") is not None else "")]
    if h.get("om") is not None:
        parts.append(f"operating margin {h['om']:.1f}%")
    if h.get("ni") is not None:
        ni = h["ni"]
        parts.append(f"net earnings {h.get('ni_fmt')}" if ni >= 0 else f"net loss {social.money(-ni, abs(ni) >= 1e9 or (h.get('revenue') or 0) >= 1e9)}")
    return " · ".join(parts)


def eyebrow(e, q):
    form = "8-K earnings release" if q.get("form") == "8-K" else q.get("form", "")
    return " · ".join(x for x in (e.get("ticker"), q.get("label") + (" full year" if is_year(q) else ""),
                                  f"{form} filed {social.fdate(q.get('filed'))}",
                                  "final" if q.get("release_check") else "") if x)


def release_note(q, got_at=None):
    """The 10-Q/10-K that replaces an 8-K chart: say so, and how the release's figures compare with the filing."""
    rc = q.get("release_check")
    if not rc:
        return ""
    big = ((q.get("headline") or {}).get("revenue") or 0) >= 1e9
    if got_at and got_at is not True:
        out = (f"Final figures from the {q.get('form')}. You received the preliminary chart from the earnings release "
               f"(8-K) on {social.fdate(str(got_at))}.")
    else:
        out = f"Final figures from the {q.get('form')}; they replace the preliminary chart read from the 8-K earnings release filed {social.fdate(rc.get('filed'))}."
    ok = [f["name"].lower() for f in rc.get("fields", []) if f["ok"]]
    bad = [f"{f['name'].lower()} {social.money(f['release'], big)} in the release, {social.money(f['final'], big)} as filed"
           for f in rc.get("fields", []) if not f["ok"]]
    if ok:
        words = ok[0] if len(ok) == 1 else ", ".join(ok[:-1]) + " and " + ok[-1]
        out += f" {words[0].upper() + words[1:]} {'match' if len(ok) > 1 else 'matches'} the release."
    if bad:
        out += f" Revised: {'; '.join(bad)}."
    return out


def page_url(site_url, e):
    return f"{site_url}/#c-{e['cik']}-{'fy-' if is_year(e) else ''}{e['end']}" if site_url else ""


def subject(items, daily, requested=False):
    tick = [e.get("ticker") or social.display_name(e.get("name") or c["profile"]["name"]) for e, c, *_ in items]
    more = " and more" if len(tick) > 5 else ""
    if daily:
        return f"Your daily charts: {', '.join(tick[:5])}{more}"
    if len(items) == 1:
        e, q = items[0][0], items[0][2]
        h = q.get("headline") or {}
        return (f"{tick[0]} {q.get('label')}: revenue {h.get('rev_fmt') or e.get('rev')}"
                + (f", {pct(h.get('yoy'))} Y/Y" if h.get("yoy") is not None else "")
                + (" (preliminary)" if q.get("form") == "8-K" else f" (final {q.get('form')})" if q.get("release_check") else ""))
    if requested:
        labels = [f"{tk} {q.get('label')}" for tk, (e, c, q, *_) in zip(tick, items)]
        return f"Your reports: {', '.join(labels[:4])}{' and more' if len(labels) > 4 else ''}"
    return f"{len(items)} new charts: {', '.join(tick[:5])}{more}"


# ------------------------------------------------------------------ what each reader gets drawn
VIEW_ORDER = ("std", "y", "q", "h")


DOT = {"rev": "#7a7974", "profit": "#17734a", "cost": "#ea6a52", "noncash": "#5b7fa6"}


def change_rows(q):
    """Every line of the chart with its change vs the year-ago and the previous quarter, in reading order."""
    big = ((q.get("headline") or {}).get("revenue") or 0) >= 1e9
    money = lambda v: "—" if v is None else social.money(v, big)

    def delta(now, then):
        if then is None or now is None:
            return "—", "—"
        d = now - then
        dm = ("+" if d > 0 else "−" if d < 0 else "±") + social.money(abs(d), big)
        pc = social.chg(now, then) if now > 0 and then > 0 else "n/m"
        return dm, pc or "0%"

    def mix(cmp):                                   # "Δ +$9.7B · scale +8.1 · mix +1.6" -> "scale +8.1 · mix +1.6"
        parts = H.unescape(cmp or "").split(" \u00b7 ", 1)
        return parts[1] if len(parts) > 1 else ""

    nodes = sorted(enumerate(q.get("nodes") or []), key=lambda x: (x[1].get("col", 0), x[0]))
    out = []
    for _, n in nodes:
        v = n.get("v")
        dy, py = delta(v, n.get("y"))
        dq, pq = delta(v, n.get("q"))
        out.append({"name": H.unescape(str(n.get("name") or "")), "color": DOT.get(n.get("color"), "#7a7974"),
                    "now": money(v), "y": money(n.get("y")), "q": money(n.get("q")), "dy": dy, "py": py, "dq": dq, "pq": pq,
                    "mix_y": mix(n.get("cmp_y")), "mix_q": mix(n.get("cmp"))})
    return out


def changes_email_html(q):
    """All changes as a compact table for the e-mail (fits 632 px)."""
    rows = change_rows(q)
    if not rows:
        return ""
    vy = (q.get("compare_y") or {}).get("vs") or "year ago"
    vq = (q.get("compare") or {}).get("vs") or "prev. quarter"
    th = f'padding:4px 6px;border-bottom:1px solid {LINE};font:600 11.5px/1.3 {FONT};color:{MUTED};text-align:right;white-space:nowrap'
    td = f'padding:4px 6px;border-bottom:1px solid {LINE};font:13px/1.35 {FONT};color:{INK};text-align:right;white-space:nowrap'
    yq = not is_year(q)                                  # a fiscal year has no "previous quarter" columns
    body = "".join(
        f'<tr><td style="{td};text-align:left;white-space:normal"><span style="display:inline-block;width:8px;height:8px;'
        f'border-radius:2px;background:{r["color"]};margin-right:6px"></span>{H.escape(r["name"])}</td>'
        f'<td style="{td}">{r["now"]}</td><td style="{td}">{r["dy"]}</td><td style="{td};color:{MUTED}">{r["py"]}</td>'
        + (f'<td style="{td}">{r["dq"]}</td><td style="{td};color:{MUTED}">{r["pq"]}</td>' if yq else "") + '</tr>' for r in rows)
    return (f'<p style="margin:4px 0 6px;font:600 15px/1.4 {FONT};color:{INK}">All changes</p>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 14px">'
            f'<tr><td style="{th};text-align:left">Line</td><td style="{th}">{H.escape(q.get("label") or "Now")}</td>'
            f'<td style="{th}" colspan="2">vs {H.escape(vy)}</td>'
            + (f'<td style="{th}" colspan="2">vs {H.escape(vq)}</td>' if yq else "") + f'</tr>{body}</table>')


def changes_text(q):
    rows = change_rows(q)
    vy = (q.get("compare_y") or {}).get("vs") or "year ago"
    vq = (q.get("compare") or {}).get("vs") or "previous quarter"
    if is_year(q):
        return [f"All changes (vs {vy}):"] + [f"- {r['name']}: {r['now']}; {r['dy']} ({r['py']})" for r in rows] + [""]
    return [f"All changes (vs {vy}; vs {vq}):"] + [
        f"- {r['name']}: {r['now']}; {r['dy']} ({r['py']}); {r['dq']} ({r['pq']})" for r in rows] + [""]


def changes_pdf_html(q):
    """All changes for the PDF: values of all three quarters, the changes and the scale/mix split."""
    rows = change_rows(q)
    if not rows:
        return ""
    vy = (q.get("compare_y") or {}).get("vs") or "Year ago"
    vq = (q.get("compare") or {}).get("vs") or "Prev. quarter"
    esc = H.escape
    yq = not is_year(q)
    head = (f"<tr><th>Line</th><th class=n>{esc(q.get('label') or '')}</th><th class=n>{esc(vy)}</th><th class=n>Change</th>"
            f"<th class=n>%</th><th>scale · mix</th>"
            + (f"<th class=n>{esc(vq)}</th><th class=n>Change</th><th class=n>%</th><th>scale · mix</th>" if yq else "") + "</tr>")
    body = "".join(
        f'<tr><td><i style="background:{r["color"]}"></i>{esc(r["name"])}</td><td class=n>{r["now"]}</td><td class=n>{r["y"]}</td>'
        f'<td class=n>{r["dy"]}</td><td class=n>{r["py"]}</td><td class=m>{esc(r["mix_y"])}</td>'
        + (f'<td class=n>{r["q"]}</td><td class=n>{r["dq"]}</td><td class=n>{r["pq"]}</td><td class=m>{esc(r["mix_q"])}</td>' if yq else "")
        + '</tr>' for r in rows)
    return f'<table class="hist changes"><thead>{head}</thead><tbody>{body}</tbody></table>'


def history_company(c, q):
    """The company's quarters up to this one (newest first), trimmed to what the history chart reads."""
    keep = [x for x in c["quarters"] if x["end"] <= q["end"]]
    return {"profile": c["profile"], "quarters": [
        {k: x.get(k) for k in ("label", "form", "filed", "end", "headline")} |
        {"nodes": [n for n in x.get("nodes") or [] if n.get("id") == "ocf"]} for x in keep[:8]]}


def views_for(sub, c, q):
    """The charts a reader gets for one quarter: always this quarter; the comparisons and history they ticked."""
    out = ["std"]
    if sub.get("chart_y") and q.get("compare_y"):
        out.append("y")
    if sub.get("chart_q") and q.get("compare"):
        out.append("q")
    if sub.get("chart_history") and not is_year(q) and sum(1 for x in c["quarters"] if x["end"] <= q["end"]) >= 2:
        out.append("h")
    return out


def view_caption(view, q):
    if view == "y":
        return f"Compared with {(q.get('compare_y') or {}).get('vs')}"
    if view == "q":
        return f"Compared with {(q.get('compare') or {}).get('vs')}"
    if view == "h":
        return "Quarter by quarter"
    return q.get("label") or ""


def file_base(e, q):
    return re.sub(r"[^A-Za-z0-9.]+", "-", f"{e.get('ticker') or e['cik']}-{q.get('label')}").strip("-")


def view_file(e, q, view, ext):
    vs = (q.get("compare_y") if view == "y" else q.get("compare") if view == "q" else None) or {}
    tail = {"std": "sankey", "h": "history"}.get(view) or "vs-" + re.sub(r"[^A-Za-z0-9.]+", "-", str(vs.get("vs") or view))
    return f"{file_base(e, q)}-{tail}.{ext}"


CMP_NOTE = ("Band width is this {unit}; a dark strip inside a band is the increase over {vs}, "
            "a band without a strip fell (its Δ is negative).")
CMP_NOTE_DEC = ("Band width is this {unit}; a dark strip inside a band is the increase over {vs}; "
                "a hatched area with a dashed outline beside a band is the decrease: what that line had in {vs} beyond this {unit}.")


def cmp_note(vs, decreases, unit="quarter"):
    return (CMP_NOTE_DEC if decreases else CMP_NOTE).format(vs=vs, unit=unit)


def intro_text(c, limit):
    """The company's own description (10-K Item 1, or an earnings release / 10-Q), cut near `limit` characters."""
    intro = c.get("intro")
    text = (intro if isinstance(intro, str) else (intro or {}).get("text") or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(". ", 1)[0]
    return cut + "." if len(cut) > limit * 0.5 else text[:limit].rsplit(" ", 1)[0] + " …"


def intro_source(c):
    return text.intro_cite(c.get("intro"))


def report_html(e, c, q, views, svgs, site_url, decreases=False, detail=False):
    """A printable report of one quarter: the charts (vector), company profile, analysis, what changed, the filing."""
    esc = H.escape
    p = c["profile"]
    name = social.display_name(p["name"])
    url = page_url(site_url.rstrip("/"), e) if site_url else ""
    h = q.get("headline") or {}
    big = (h.get("revenue") or 0) >= 1e9
    fye = ""
    if p.get("fye") and len(str(p["fye"])) == 4:
        try:
            fye = dt.date(2001, int(p["fye"][:2]), int(p["fye"][2:])).strftime("%b %-d")
        except ValueError:
            fye = ""
    meta = [x for x in (e.get("ticker"), ((p.get("exchanges") or [None])[0]),
                        f"SIC {p['sic']} {p.get('industry') or ''}".strip() if p.get("sic") else None,
                        f"Fiscal year ends {fye}" if fye else None, p.get("category"), f"CIK {p.get('cik')}") if x]
    profile = intro_text(c, 1400)
    profile_src = intro_source(c) if profile else ""
    note = release_note(q, e.get("_release_sent"))
    prelim = q.get("form") == "8-K"
    quote = social.filing_quote(q)
    acc = re.search(r"/(\d{10})-?(\d{2})-?(\d{6})", q.get("index_url") or "")

    def fig(view, room=6.0):
        svg = svgs.get(view)
        if not svg:
            return ""
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        width = min(10.0, room * float(m.group(1)) / float(m.group(2))) if m else 10.0   # inches: fits 10 x room
        return f'<figure class="chart" style="width:{width:.2f}in">{svg}</figure>'

    def bullets(cmp):
        if not cmp or not cmp.get("bullets"):
            return ""
        return (f'<h3>What changed vs {esc(cmp.get("vs") or "")}</h3><ul>' +
                "".join(f"<li>{esc(b)}</li>" for b in cmp["bullets"]) + "</ul>")

    facts = [("Form", esc(q.get("form") or "") + (" \u00b7 earnings release (Item 2.02), preliminary" if prelim else "")),
             ("Period", f"{esc(q.get('label') or '')} \u00b7 {'fiscal year' if is_year(q) else 'quarter'} ended {esc(social.fdate(q.get('end')))}"),
             ("Filed", esc(social.fdate(q.get("filed"))))]
    if acc:
        facts.append(("Accession", "-".join(acc.groups())))
    links = [(u, label) for u, label in ((url, "Interactive chart"), (q.get("index_url"), "Filing on SEC EDGAR"),
                                         (q.get("doc_url"), "Press release" if prelim else "The report")) if u]
    if links:
        facts.append(("Links", " \u00b7 ".join(f'<a href="{esc(u)}">{label}</a>' for u, label in links)))

    hist_rows = ""
    if "h" in views:
        qs = [x for x in c["quarters"] if x["end"] <= q["end"]][:8]
        def money(v):
            return "\u2014" if v is None else social.money(v, big)
        cells = []
        for x in qs:
            hx = x.get("headline") or {}
            ocf = hx.get("ocf")
            if ocf is None:
                ocf = next((n.get("v") for n in x.get("nodes") or [] if n.get("id") == "ocf"), None)
            om = hx.get("om")
            dash = "\u2014"
            yoy = esc(pct(hx.get("yoy")) or dash)
            omt = dash if om is None else f"{om:.1f}%".replace("-", "\u2212")
            cells.append(f"<tr><td>{esc(x.get('label') or '')}</td><td>{esc(x.get('form') or '')}</td><td>{esc(social.fdate(x.get('filed')))}</td>"
                         f"<td class=n>{money(hx.get('revenue'))}</td><td class=n>{yoy}</td><td class=n>{omt}</td>"
                         f"<td class=n>{money(hx.get('ni'))}</td><td class=n>{money(ocf)}</td></tr>")
        hist_rows = ('<table class="hist"><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class=n>Revenue</th><th class=n>Y/Y</th>'
                     '<th class=n>Op. margin</th><th class=n>Net earnings</th><th class=n>Operating cash flow</th></tr></thead>'
                     f'<tbody>{"".join(cells)}</tbody></table>')

    extra = []
    if detail and change_rows(q):
        extra.append(f'<section class="page"><h2>{esc(name)} {esc(q.get("label") or "")}: all changes</h2>'
                     '<p class="muted">' + ('Every line of the chart, this year against the year before. ' if is_year(q) else
                     'Every line of the chart, this quarter against a year earlier and against the previous quarter. ') +
                     'Δ = scale + mix: scale = change explained by the parent line growing, mix = change in the line’s share of it.</p>'
                     + changes_pdf_html(q) + "</section>")
    for v in views[1:]:
        cmp = q.get("compare_y") if v == "y" else q.get("compare") if v == "q" else None
        head = f"{esc(name)} {esc(q.get('label') or '')}: " + (f"compared with {esc(cmp.get('vs') or '')}" if cmp else "quarter by quarter")
        extra.append(f'<section class="page"><h2>{head}</h2>'
                     + (f'<p class="muted">{esc(cmp_note(cmp.get("vs"), decreases, "year" if is_year(q) else "quarter"))}</p>' if cmp else "")
                     + fig(v, 4.6 if v == "h" else 5.4) + (bullets(cmp) if cmp else "") + (hist_rows if v == "h" else "") + "</section>")

    css = """
      * { box-sizing: border-box; }
      body { margin: 0; font-family: 'IBM Plex Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #1d1d1b;
             font-size: 10pt; line-height: 1.45; font-variant-numeric: tabular-nums; }
      .eyebrow { font-size: 8pt; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #6b6a66; }
      .brand { color: #17734a; }
      h1 { font-size: 22pt; line-height: 1.15; margin: 3pt 0 3pt; font-weight: 600; }
      h2 { font-size: 13pt; margin: 0 0 6pt; font-weight: 600; }
      h3 { font-size: 10.5pt; margin: 10pt 0 4pt; font-weight: 600; }
      p { margin: 0 0 7pt; }
      .headline { font-size: 11.5pt; font-weight: 500; color: #3d3c39; margin: 0 0 3pt; }
      .meta { color: #6b6a66; font-size: 8.5pt; }
      .meta span + span::before { content: " \u00b7 "; }
      .note { background: #dcebe2; color: #0f5134; border-radius: 4pt; padding: 5pt 8pt; font-size: 9pt; margin: 6pt 0 0; }
      .muted { color: #6b6a66; font-size: 9pt; }
      figure.chart { margin: 8pt 0 0; break-inside: avoid; max-width: 100%; }
      figure.chart svg { display: block; width: 100%; height: auto; border: 0.75pt solid #e3e1db; border-radius: 4pt; }
      .page { break-before: page; }
      .cols { display: grid; grid-template-columns: 1.45fr 1fr; gap: 0 26pt; }
      ul { margin: 0 0 8pt; padding-left: 14pt; } li { margin: 0 0 3pt; }
      blockquote { margin: 4pt 0 8pt; padding: 1pt 0 1pt 9pt; border-left: 2.5pt solid #a8d1b9; color: #3d3c39; font-size: 9.5pt; }
      blockquote .src { display: block; color: #6b6a66; font-size: 8.5pt; margin-top: 3pt; }
      .profile { border-left: 2.5pt solid #a8d1b9; padding-left: 9pt; color: #3d3c39; font-size: 9.5pt; margin: 7pt 0 0; max-width: 9.2in; }
      .profile .src { display: block; color: #6b6a66; font-size: 8pt; margin-top: 3pt; }
      dl { display: grid; grid-template-columns: auto 1fr; gap: 3pt 10pt; margin: 6pt 0 8pt; font-size: 9pt; }
      dt { color: #6b6a66; } dd { margin: 0; }
      a { color: #17734a; text-decoration: none; }
      table.hist { width: 100%; border-collapse: collapse; margin-top: 10pt; font-size: 9pt; break-inside: avoid; }
      table.hist th, table.hist td { padding: 3pt 6pt; border-bottom: 0.75pt solid #e3e1db; text-align: left; }
      table.hist th { color: #6b6a66; font-weight: 600; } table.hist .n { text-align: right; }
      table.changes { font-size: 8.5pt; } table.changes td, table.changes th { padding: 2.2pt 5pt; white-space: nowrap; }
      table.changes td.m { color: #6b6a66; font-size: 7.5pt; } table.changes tbody tr { break-inside: avoid; }
      table.changes i { display: inline-block; width: 6pt; height: 6pt; border-radius: 1.5pt; margin-right: 4pt; }
      .legal { margin-top: 14pt; color: #6b6a66; font-size: 8pt; }
    """
    analysis = "".join(f"<p>{esc(x)}</p>" for x in q.get("analysis") or [])
    quote_html = ""
    if quote:
        words = quote[0] if len(quote[0]) <= 900 else quote[0][:900].rsplit(" ", 1)[0] + " \u2026"
        quote_html = f'<h3>In the company\u2019s words</h3><blockquote>\u201c{esc(words)}\u201d<span class="src">\u2014 {esc(quote[1])}</span></blockquote>'
    made_at = (" \u00b7 " + esc(site_url.rstrip("/"))) if site_url else ""
    prelim_html = ('<p class="note">Preliminary: read from the earnings release; replaced by the 10-Q/10-K when it is filed.</p>'
                   if prelim else "")
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    meta_html = "".join(f"<span>{esc(str(x))}</span>" for x in meta)
    company_html = "<h2>The filing</h2>"
    profile_html = f'<div class="profile">{esc(profile)}<span class="src">{esc(profile_src)}</span></div>' if profile else ""
    room1 = max(3.4, 6.0 - (len(profile) / 175 * 0.2 + 0.25 if profile else 0))   # the chart shares page 1 with the profile
    facts_html = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<title>{esc(name)} {esc(q.get('label') or '')}</title><style>{css}</style></head><body>
<section>
  <div class="eyebrow"><span class="brand">Filing Flows</span> \u00b7 {esc(eyebrow(e, q))}</div>
  <h1>{esc(name)}</h1>
  <p class="headline">{esc(headline(e, q))}</p>
  <div class="meta">{meta_html}</div>
  {profile_html}
  {prelim_html}
  {note_html}
  {fig('std', room1)}
</section>
<section class="page cols">
  <div>
    <h2>Analysis</h2>{analysis}
    {bullets(q.get('compare_y'))}
    <p class="muted">Written by fixed rules from the reported figures: growth, margins, the line that drove the change and cash conversion.</p>
    <p class="legal">Charts and analysis are generated by fixed rules from SEC filings; quotes are the companies\u2019 own words.
    Not investment advice. Made by Filing Flows{made_at}.</p>
  </div>
  <div>
    {company_html}
    <dl>{facts_html}</dl>
    {quote_html}
  </div>
</section>
{''.join(extra)}
</body></html>"""


class Assets:
    """Everything drawn for one run's e-mails, in one headless Chromium, each drawing made once and shared:
    the inline JPGs, the PNG/JPG files and the PDF reports. Without Chromium the e-mails go out with links only."""
    INLINE = {"fmt": "jpg", "width": 1400, "quality": 0.85}
    FILE = {"png": {"fmt": "png", "width": 2400}, "jpg": {"fmt": "jpg", "width": 2400, "quality": 0.92}}

    def __init__(self, site, enabled=True, charts=None):
        self.site, self.enabled = site, enabled
        self.ch, self.broken, self.cache = charts, not enabled, {}
        self.own = charts is None

    def close(self):
        if self.ch is not None and self.own:
            self.ch.__exit__(None, None, None)
        self.ch = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def _charts(self):
        if self.broken:
            return None
        if self.ch is None:
            try:
                self.ch = social.Charts(self.site.src).__enter__()
            except Exception as err:                     # e-mails still go out, with links instead of pictures
                print(f"charts not rendered ({err.__class__.__name__}: {err}); sending without images", file=sys.stderr)
                self.broken = True
                return None
        return self.ch

    @staticmethod
    def what(c, q, view, decreases=False):
        if view == "h":
            return ("history", history_company(c, q))
        return ("chart", q, None if view == "std" else view, {"decreases": bool(decreases and view in ("q", "y"))})

    def _get(self, key, make):
        if key not in self.cache:
            ch = self._charts()
            if ch is None:
                return None
            try:
                self.cache[key] = make(ch)
            except Exception as err:
                print(f"::warning::could not draw {key[0]} {key[1]} ({err.__class__.__name__}: {err})")
                self.cache[key] = None
        return self.cache[key]

    def image(self, e, c, q, view, kind="inline", decreases=False):
        o = self.INLINE if kind == "inline" else self.FILE[kind]
        dec = bool(decreases and view in ("q", "y"))
        return self._get((item_key(e), view + ("+dec" if dec else ""), kind),
                         lambda ch: ch.image(self.what(c, q, view, dec), o["fmt"], width=o["width"], quality=o.get("quality")))

    def pdf(self, e, c, q, views, site_url, decreases=False, detail=False):
        def make(ch):
            svgs = {v: ch.svg(self.what(c, q, v, decreases), view_caption(v, q)) for v in views}
            name = H.escape(f"Filing Flows \u00b7 {social.display_name(c['profile']['name'])} {q.get('label')}")
            return ch.pdf(report_html(e, c, q, views, svgs, site_url, decreases, detail), footer=name)
        return self._get((item_key(e), "pdf:" + ",".join(views) + ("+dec" if decreases else "") + ("+all" if detail else ""), "pdf"),
                         make)

    def for_message(self, sub, items, site_url, full):
        """(inline images, extras) for one reader's e-mail; extras[key] = {"inline": {view: jpg}, "files": [...]}."""
        images, extras = {}, {}
        if self.broken:
            return images, extras
        fmt = sub.get("attach_images") or "png"
        want_pdf = sub.get("attach_pdf", True) is not False
        dec = bool(sub.get("cmp_decreases"))
        for e, c, q, _ in items[:full]:
            k = item_key(e)
            views = views_for(sub, c, q)
            images[k] = self.image(e, c, q, "std")
            inline = {v: self.image(e, c, q, v, decreases=dec) for v in views[1:]}
            files = []
            if want_pdf:
                pdf = self.pdf(e, c, q, views, site_url, dec, bool(sub.get("changes_detail")))
                if pdf:
                    files.append((f"{file_base(e, q)}-report.pdf", pdf, "application", "pdf"))
            if fmt in self.FILE:
                for v in views:
                    data = self.image(e, c, q, v, fmt, decreases=dec)
                    if data:
                        files.append((view_file(e, q, v, fmt), data, "image", "jpeg" if fmt == "jpg" else "png"))
            extras[k] = {"inline": {v: x for v, x in inline.items() if x}, "files": files}
        return images, extras


def build_message(sub, items, site_url, images, sender, daily=False, requested=False, extras=None):
    """items: [(index entry, company json, quarter, reasons)]; images: {item key: jpeg bytes} (this quarter's chart);
    extras: {item key: {"inline": {view: jpeg}, "files": [(file name, bytes, maintype, subtype)]}} (Assets.for_message)."""
    site_url = site_url.rstrip("/")
    msg = EmailMessage()
    msg["Subject"] = subject(items, daily, requested)
    msg["From"] = sender
    msg["To"] = sub["email"]
    msg["Auto-Submitted"] = "auto-generated"
    unsub = f"{site_url}/#unsubscribe-{sub['unsub_token']}" if site_url and sub.get("unsub_token") else ""
    manage = f"{site_url}/#account" if site_url else ""
    if unsub:
        msg["List-Unsubscribe"] = f"<{unsub}>"

    cut = REQUEST_FULL_ITEMS if requested else FULL_ITEMS
    full, rest = items[:cut], items[cut:]
    n = len(items)
    # size budget: this quarter's charts, then the extra charts, then the PDF reports, then the image files
    extras = extras or {}
    budget = env_int("MAIL_MAX_BYTES", MAIL_MAX_BYTES)
    used = sum(len(images.get(item_key(e)) or b"") for e, *_ in full)
    keep_inline, keep_files, dropped = {}, {}, 0
    for e, *_ in full:
        k = item_key(e)
        keep_inline[k] = {}
        for v, data in ((extras.get(k) or {}).get("inline") or {}).items():
            if data and used + len(data) <= budget:
                keep_inline[k][v] = data
                used += len(data)
            elif data:
                dropped += 1
    for want_pdf in (True, False):
        for e, *_ in full:
            k = item_key(e)
            for f in (extras.get(k) or {}).get("files") or []:
                if (f[2] == "application") != want_pdf:
                    continue
                if used + len(f[1]) <= budget:
                    keep_files.setdefault(k, []).append(f)
                    used += len(f[1])
                else:
                    dropped += 1
    intro = ("The report you asked for." if requested and n == 1 else f"The {n} reports you asked for." if requested
             else f"{n} new chart{'s' if n != 1 else ''} since your last digest." if daily
             else "The final figures for a quarter you first got from its earnings release."
             if n == 1 and items[0][2].get("release_check") and items[0][0].get("_release_sent")
             else "A new chart for a company you follow." if n == 1 else f"{n} new charts for companies you follow.")
    text, rich, related = [intro, ""], [], []
    p_style = f"margin:0 0 12px;font:15px/1.55 {FONT};color:{INK}"
    for e, c, q, why in full:
        name = social.display_name(c["profile"]["name"])
        url = page_url(site_url, e)
        prelim = q.get("form") == "8-K"
        text += ["=" * 64, eyebrow(e, q), name, headline(e, q)]
        note = release_note(q, e.get("_release_sent"))
        if prelim:
            text.append("Preliminary: read from the earnings release; replaced by the 10-Q/10-K when it is filed.")
        if note:
            text.append(note)
        if url:
            text.append(f"Interactive chart: {url}")
        text.append("")
        rich.append(f'<tr><td style="padding:22px 0 0;border-top:1px solid {LINE}">'
                    f'<div style="font:600 12px/1.4 {FONT};letter-spacing:.06em;text-transform:uppercase;color:{MUTED}">{H.escape(eyebrow(e, q))}</div>'
                    f'<h2 style="margin:4px 0 6px;font:600 22px/1.25 {FONT};color:{INK}">{H.escape(name)}</h2>'
                    f'<p style="margin:0 0 12px;font:500 15px/1.5 {FONT};color:{INK2}">{H.escape(headline(e, q))}</p>')
        if prelim:
            rich.append(f'<p style="margin:0 0 12px;font:13px/1.5 {FONT};color:{MUTED}">Preliminary: read from the earnings '
                        "release; replaced by the 10-Q/10-K when it is filed.</p>")
        if note:
            rich.append(f'<p style="margin:0 0 12px;padding:8px 12px;border-radius:6px;background:#dcebe2;font:14px/1.5 {FONT};'
                        f'color:#0f5134">{H.escape(note)}</p>')
        k = item_key(e)

        def pic(img, link, alt, fname):
            cid = make_msgid(domain="filing-flows")
            related.append((img, cid, fname))
            tag = (f'<img src="cid:{cid[1:-1]}" width="632" alt="{H.escape(alt)}" '
                   f'style="display:block;width:100%;max-width:632px;height:auto;border:1px solid {LINE};border-radius:6px">')
            return (f'<a href="{H.escape(link)}">{tag}</a>' if link else tag) + '<div style="height:14px"></div>'

        def changed(cmp, fallback):
            if not cmp.get("bullets"):
                return
            text.append(f"What changed vs {cmp.get('vs')}:")
            text.extend([f"- {b}" for b in cmp["bullets"]] + [""])
            rich.append(f'<p style="margin:4px 0 6px;font:600 15px/1.4 {FONT};color:{INK}">What changed vs {H.escape(cmp.get("vs") or fallback)}</p>'
                        f'<ul style="margin:0 0 12px;padding-left:20px;font:15px/1.55 {FONT};color:{INK}">'
                        + "".join(f'<li style="margin:0 0 4px">{H.escape(b)}</li>' for b in cmp["bullets"]) + "</ul>")

        def extra_chart(view, cmp, link):
            img = keep_inline.get(k, {}).get(view)
            if not img:
                return
            if cmp:
                rich.append(f'<p style="margin:0 0 8px;font:13px/1.5 {FONT};color:{MUTED}">'
                            f'{H.escape(cmp_note(cmp.get("vs"), sub.get("cmp_decreases"), "year" if is_year(q) else "quarter"))}</p>')
            rich.append(pic(img, link, f"{name} {q.get('label')}: {view_caption(view, q).lower()}", view_file(e, q, view, "jpg")))

        about = intro_text(c, 420)
        if about:
            text += [f"About the company: {about} ({intro_source(c)})", ""]
            rich.append(f'<p style="margin:0 0 14px;padding:2px 0 2px 12px;border-left:3px solid #a8d1b9;font:14px/1.55 {FONT};color:{INK2}">'
                        f'{H.escape(about)}<span style="display:block;margin-top:3px;font-size:12.5px;color:{MUTED}">'
                        f'{H.escape(intro_source(c))}</span></p>')
        img = images.get(k)
        if img:
            rich.append(pic(img, url, f"{q.get('title') or name} Sankey chart".replace("&amp;", "&"), view_file(e, q, "std", "jpg")))
        for para in q.get("analysis") or []:
            text.append(para)
            text.append("")
            rich.append(f'<p style="{p_style}">{H.escape(para)}</p>')
        views = views_for(sub, c, q)
        changed(q.get("compare_y") or {}, "a year earlier")
        if "y" in views:
            extra_chart("y", q.get("compare_y") or {}, url)
        if "q" in views:
            changed(q.get("compare") or {}, "the previous quarter")
            extra_chart("q", q.get("compare") or {}, url)
        if sub.get("changes_detail"):
            text.extend(changes_text(q))
            rich.append(changes_email_html(q))
        if "h" in views and keep_inline.get(k, {}).get("h"):
            rich.append(f'<p style="margin:4px 0 6px;font:600 15px/1.4 {FONT};color:{INK}">Quarter by quarter</p>')
            extra_chart("h", None, f"{site_url}/#c-{e['cik']}-all" if site_url else "")
        quote = social.filing_quote(q)
        if quote:
            words = quote[0] if len(quote[0]) <= 700 else quote[0][:700].rsplit(" ", 1)[0] + " …"
            text += [f"From the filing: “{words}” — {quote[1]}", ""]
            rich.append(f'<blockquote style="margin:0 0 12px;padding:2px 0 2px 14px;border-left:3px solid #a8d1b9;font:14.5px/1.55 {FONT};color:{INK2}">'
                        f'“{H.escape(words)}”<div style="margin-top:4px;font-size:13px;color:{MUTED}">— {H.escape(quote[1])}</div></blockquote>')
        links = [(u, label) for u, label in ((url, "Open the interactive chart"), (q.get("index_url"), "The filing on SEC EDGAR")) if u]
        text += [f"{label}: {u}" for u, label in links]
        files = [f[0] for f in keep_files.get(k, [])]
        if files:
            text.append(f"Attached: {', '.join(files)}")
            rich.append(f'<p style="margin:0 0 8px;font:13px/1.5 {FONT};color:{MUTED}">Attached: {H.escape(", ".join(files))}</p>')
        text += [f"Why you got this: {'; '.join(why)}.", ""]
        rich.append(f'<p style="margin:0 0 8px;font:600 14.5px/1.5 {FONT}">'
                    + " &nbsp;·&nbsp; ".join(f'<a href="{H.escape(u)}" style="color:{ACCENT}">{label}</a>' for u, label in links) + "</p>"
                    f'<p style="margin:0 0 22px;font:13px/1.5 {FONT};color:{MUTED}">Why you got this: {H.escape("; ".join(why))}.</p></td></tr>')
    if rest:
        text += ["=" * 64, f"Also new ({len(rest)}):"]
        rows = []
        for e, c, q, why in rest:
            url = page_url(site_url, e)
            h = q.get("headline") or {}
            line = f"{e.get('ticker') or ''} {social.display_name(c['profile']['name'])} {q.get('label')}: revenue {h.get('rev_fmt') or e.get('rev')}" \
                   + (f" ({pct(h.get('yoy'))} Y/Y)" if h.get("yoy") is not None else "")
            text.append(f"- {line.strip()}" + (f"  {url}" if url else ""))
            rows.append(f'<tr><td style="padding:6px 8px 6px 0;border-top:1px solid {LINE};font:600 13px {FONT};color:{INK}">{H.escape(e.get("ticker") or "")}</td>'
                        f'<td style="padding:6px 8px;border-top:1px solid {LINE};font:14px/1.4 {FONT}">'
                        + (f'<a href="{H.escape(url)}" style="color:{ACCENT}">' if url else "") + H.escape(social.display_name(c["profile"]["name"]))
                        + ("</a>" if url else "") + f' <span style="color:{MUTED}">{H.escape(q.get("label") or "")}</span></td>'
                        f'<td style="padding:6px 0;border-top:1px solid {LINE};font:14px {FONT};text-align:right;white-space:nowrap">'
                        f'{H.escape(h.get("rev_fmt") or e.get("rev") or "")} <span style="color:{MUTED}">{H.escape(pct(h.get("yoy")) + " Y/Y" if h.get("yoy") is not None else "")}</span></td></tr>')
        rich.append(f'<tr><td style="padding:8px 0 18px;border-top:1px solid {LINE}"><p style="margin:14px 0 6px;font:600 16px {FONT};color:{INK}">Also new</p>'
                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{"".join(rows)}</table></td></tr>')
    foot = ("Charts and analysis are generated by fixed rules from SEC filings; quotes are the companies' own words. "
            "Not investment advice.")
    if dropped:
        foot = (f"Some files were left out to keep this e-mail under {budget // 1_000_000} MB; the interactive chart "
                "exports any view as PNG, JPG or PDF. ") + foot
    text += ["-" * 64, foot]
    if manage:
        text.append(f"Change what you get: {manage}")
    if unsub:
        text.append(f"Unsubscribe: {unsub}")
    privacy = f"{site_url}/privacy.html" if site_url else ""
    foot_links = " &nbsp;·&nbsp; ".join(f'<a href="{H.escape(u)}" style="color:{MUTED}">{label}</a>'
                                        for u, label in ((manage, "Change what you get"), (unsub, "Unsubscribe"),
                                                         (privacy, "Privacy")) if u)
    html = (f'<div style="background:{GROUND};padding:20px 10px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="max-width:680px;margin:0 auto;background:{PAPER};border-radius:10px;border-collapse:separate">'
            f'<tr><td style="padding:22px 24px 0"><div style="font:600 13px {FONT};letter-spacing:.08em;text-transform:uppercase;color:{ACCENT}">Filing Flows</div>'
            f'<p style="margin:6px 0 16px;font:15px/1.5 {FONT};color:{INK2}">{H.escape(intro)}</p></td></tr>'
            f'<tr><td style="padding:0 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rich)}</table></td></tr>'
            f'<tr><td style="padding:4px 24px 22px;border-top:1px solid {LINE}"><p style="margin:14px 0 6px;font:12.5px/1.5 {FONT};color:{MUTED}">{H.escape(foot)}</p>'
            f'<p style="margin:0;font:12.5px/1.5 {FONT}">{foot_links}</p></td></tr></table></div>')
    msg.set_content("\n".join(text))
    msg.add_alternative(html, subtype="html")
    part = msg.get_payload()[1]
    for img, cid, fname in related:
        part.add_related(img, maintype="image", subtype="jpeg", cid=cid, filename=fname, disposition="inline")
    for e, *_ in full:
        for fname, data, maintype, subtype in keep_files.get(item_key(e), []):
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)
    return msg


# ------------------------------------------------------------------ sending
class Mailer:
    def __init__(self, host, port, user, password):
        self.host, self.port, self.user, self.password = host, int(port), user, password
        self.smtp = None

    def _connect(self):
        import smtplib
        if self.port == 465:
            self.smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=60)
        else:
            self.smtp = smtplib.SMTP(self.host, self.port, timeout=60)
            self.smtp.starttls()
        self.smtp.login(self.user, self.password)

    def send(self, msg):
        import smtplib
        if self.smtp is None:
            self._connect()
        try:
            self.smtp.send_message(msg)
        except smtplib.SMTPServerDisconnected:
            self._connect()
            self.smtp.send_message(msg)

    def close(self):
        if self.smtp is not None:
            try:
                self.smtp.quit()
            except Exception:
                pass
            self.smtp = None


def render_images(site, wanted):
    """{item key: (index entry, quarter)} -> {item key: jpeg} of this quarter's chart; empty without Chromium."""
    if not wanted:
        return {}
    with Assets(site) as a:
        out = {k: a.image(e, None, q, "std") for k, (e, q) in wanted.items()}
    return {k: v for k, v in out.items() if v}


def _load_items(site, cache, pairs):
    """[(index-like entry, reasons)] -> [(entry, company json, quarter, reasons)] (company files read once)."""
    out = []
    for e, why in pairs:
        k = item_key(e)
        if k not in cache:
            cache[k] = site.quarter(e)
        out.append((e, *cache[k], why))
    return out


def _send(mailer, msg, dry_run, label):
    if dry_run:
        print(f"--- to {label}: {msg['Subject']}")
        return True
    try:
        mailer.send(msg)
        return True
    except Exception as err:
        print(f"::warning::could not e-mail {label}: {err}")
        return False


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def claim_requests(supa, now):
    """Take the waiting "Email me" requests (and ones a crashed run left half-done). Each row is claimed by one run."""
    stamp = now.isoformat()
    got = supa.update("send_requests", {"status": "eq.pending"}, {"status": "sending", "claimed_at": stamp})
    stale = (now - dt.timedelta(minutes=STALE_CLAIM_MINUTES)).isoformat()
    got += supa.update("send_requests", {"status": "eq.sending", "claimed_at": f"lt.{stale}"},
                       {"status": "sending", "claimed_at": stamp})
    return sorted(got, key=lambda r: (r.get("created_at") or "", r["id"]))


def find_quarter(site, cik, end, kind="q"):
    """The quarter (or, kind "fy", the fiscal year) a reader asked for; an 8-K quarter that a 10-Q/10-K has since
    replaced resolves to the latter."""
    try:
        c = site.json(f"c/{int(cik)}.json")
    except Exception:
        return None, None
    e0 = dt.date.fromisoformat(str(end)[:10])
    best = None
    for q in (c.get("years") or []) if kind == "fy" else c["quarters"]:
        d = abs((dt.date.fromisoformat(q["end"]) - e0).days)
        if d <= SAME_QUARTER_DAYS and (best is None or d < best[0]):
            best = (d, q)
    return c, (best[1] if best else None)


def process_requests(site, supa, mailer, sender, site_url, now, dry_run, assets, budget):
    """E-mail the reports readers asked for with "Email me". Returns the number of e-mails sent."""
    if dry_run:
        reqs = supa.select("send_requests", {"select": "*", "status": "eq.pending"})   # "*": with or without the kind column
    else:
        reqs = claim_requests(supa, now)
    if not reqs:
        return 0
    users = sorted({r["user_id"] for r in reqs})
    subs = {s_["user_id"]: s_ for s_ in supa.select("subscriptions", {          # "*": works before and after new columns
        "select": "*", "user_id": f"in.({','.join(users)})"})}
    by_user = {}
    for r in reqs:
        by_user.setdefault(r["user_id"], []).append(r)

    def finish(rows, **fields):
        if rows and not dry_run:
            supa.update("send_requests", {"id": f"in.({','.join(str(r['id']) for r in rows)})"}, fields)

    sent = 0
    jobs = []
    for uid, rows in by_user.items():
        sub = subs.get(uid)
        if not sub or not sub.get("email"):
            finish(rows, status="failed", error="no e-mail address on the account")
            continue
        items, missing = [], []
        for r in rows:
            kind = r.get("kind") or "q"
            c, q = find_quarter(site, r["cik"], r["period_end"], kind)
            if not q:
                missing.append(r)
                continue
            e = {"cik": int(r["cik"]), "end": q["end"], "form": q.get("form"), "ticker": (c["profile"].get("tickers") or [""])[0],
                 "name": c["profile"]["name"], "rev": (q.get("headline") or {}).get("rev_fmt")}
            if kind == "fy":
                e["period"] = "fy"
            if all(item_key(x[0]) != item_key(e) for x in items):     # the same quarter asked twice: one copy
                items.append((e, c, q, ["you asked for this report"]))
        finish(missing, status="failed", error="that period is no longer on the site")
        if items:
            jobs.append((sub, rows, [r for r in rows if r not in missing], items))
    if not jobs:
        return 0
    if len(jobs) > budget:
        print(f"::warning::daily e-mail limit reached; {len(jobs) - max(budget, 0)} requests wait for the next run")
        for _, _, ok_rows, _ in jobs[max(budget, 0):]:
            finish(ok_rows, status="pending", claimed_at=None)
        jobs = jobs[:max(budget, 0)]
    for sub, rows, ok_rows, items in jobs:
        pics, extras = assets.for_message(sub, items, site_url, REQUEST_FULL_ITEMS)
        msg = build_message(sub, items, site_url, pics, sender, requested=True, extras=extras)
        if _send(mailer, msg, dry_run, mask(sub["email"])):
            finish(ok_rows, status="sent", sent_at=_now_iso(), error=None)
            sent += 1
            if not dry_run:
                print(f"e-mailed {mask(sub['email'])}: {msg['Subject']}")
        else:
            again = [r for r in ok_rows if (r.get("attempts") or 0) + 1 < REQUEST_ATTEMPTS]
            for r in ok_rows:
                fields = ({"status": "pending", "claimed_at": None} if r in again
                          else {"status": "failed", "error": "the e-mail could not be sent"})
                fields["attempts"] = (r.get("attempts") or 0) + 1
                finish([r], **fields)
    return sent


def run(site, supa, mailer, sender, site_url, now=None, dry_run=False, images=True, hour=None, daily_limit=None,
        due_only=False, requests_only=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    hour = env_int("DIGEST_HOUR_UTC", 22) if hour is None else hour
    daily_limit = env_int("MAIL_DAILY_LIMIT", 400) if daily_limit is None else daily_limit
    day_ago = (now - dt.timedelta(hours=24)).isoformat()
    since = (now - dt.timedelta(days=KEEP_DELIVERIES_DAYS)).isoformat()
    dels = supa.select("deliveries", {"select": "user_id,item,sent_at", "sent_at": f"gte.{day_ago if requests_only else since}"})
    sent_req = supa.select("send_requests", {"select": "user_id,sent_at", "status": "eq.sent", "sent_at": f"gte.{day_ago}"})
    budget = daily_limit - emails_last_24h(dels + sent_req, now)

    if due_only:
        stale = (now - dt.timedelta(minutes=STALE_CLAIM_MINUTES)).isoformat()
        n = len(supa.select("send_requests", {"select": "id", "status": "eq.pending"})) + \
            len(supa.select("send_requests", {"select": "id", "status": "eq.sending", "claimed_at": f"lt.{stale}"}))
        if not requests_only:
            subs = supa.select("subscriptions", {"select": "user_id,email,tickers,sectors,all_above,min_revenue,starred,"
                                                 "frequency,email_on,final_too,unsub_token,created_at", "email_on": "is.true"})
            n += len(plan(subs, dels, site.json("index.json"), now, hour, MAX_AGE_DAYS))
        print(f"{n} e-mails due")
        return n

    sent = 0
    assets = Assets(site, enabled=images and not dry_run)
    try:
        sent += process_requests(site, supa, mailer, sender, site_url, now, dry_run, assets, budget)
        budget -= sent
        if requests_only:
            return sent
        ix = site.json("index.json")
        subs = supa.select("subscriptions", {"select": "*", "email_on": "is.true", "order": "created_at.asc"})
        todo = plan(subs, dels, ix, now, hour, MAX_AGE_DAYS)
        print(f"{len(subs)} readers with e-mail on; {len(todo)} due now; {max(budget, 0)} e-mails left in the 24-hour limit")
        if budget < len(todo):
            print(f"::warning::daily e-mail limit reached; {len(todo) - max(budget, 0)} readers wait for the next run")
            todo = todo[:max(budget, 0)]
        cache = {}
        loaded = [(sub, _load_items(site, cache, items)) for sub, items in todo]
        for sub, items in loaded:
            pics, extras = assets.for_message(sub, items, site_url, FULL_ITEMS)
            msg = build_message(sub, items, site_url, pics, sender, daily=sub.get("frequency") == "daily", extras=extras)
            if not _send(mailer, msg, dry_run, mask(sub["email"])):
                continue
            if dry_run:
                for e, c, q, why in items:
                    print(f"    {item_key(e)} {e.get('ticker')}  ({'; '.join(why)})")
                continue
            stamp = _now_iso()
            supa.insert("deliveries", [{"user_id": sub["user_id"], "item": item_key(e), "sent_at": stamp} for e, *_ in items])
            sent += 1
            print(f"e-mailed {mask(sub['email'])}: {msg['Subject']}")
    finally:
        assets.close()
        if mailer:
            mailer.close()
    if not dry_run and not requests_only:
        try:
            supa.delete("deliveries", {"sent_at": f"lt.{since}"})
        except Exception as err:
            print(f"old deliveries not pruned: {err}", file=sys.stderr)
    return sent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="_site", help="built site folder, or the published site's URL")
    ap.add_argument("--site-url", default=None, help="public address used in links (default SITE_URL / X_SITE_URL)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 0 when the Supabase settings are present")
    ap.add_argument("--due", action="store_true", help="exit 0 when some reader has an e-mail due now; send nothing")
    ap.add_argument("--requests", action="store_true", help="only the reports readers asked for with \"Email me\"")
    args = ap.parse_args()
    url, key = setting("SUPABASE_URL", url=True), setting("SUPABASE_SERVICE_KEY")
    user, password = os.environ.get("MAIL_USERNAME", ""), os.environ.get("MAIL_PASSWORD", "")
    if args.check:
        sys.exit(0 if url and key else 1)
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set: reader alerts are off.")
        sys.exit(1 if args.due else 0)
    site = Site(args.site)
    if args.due:
        try:
            n = run(site, Supa(url, key), None, "", "", due_only=True, requests_only=args.requests)
        except Exception as err:
            print(f"::error::reader alerts: {err}")
            sys.exit(2)
        sys.exit(0 if n else 1)
    site_url = args.site_url or os.environ.get("SITE_URL") or os.environ.get("X_SITE_URL") or (args.site if site.remote else "")
    mailer = None
    if not args.dry_run:
        if not (user and password):
            print("MAIL_USERNAME / MAIL_PASSWORD not set: printing what would be sent.")
            args.dry_run = True
        else:
            mailer = Mailer(os.environ.get("SMTP_HOST") or "smtp.gmail.com", os.environ.get("SMTP_PORT") or 465, user, password)
    sender = os.environ.get("MAIL_FROM") or formataddr(("Filing Flows", parseaddr(user)[1] or user))
    run(site, Supa(url, key), mailer, sender, site_url.rstrip("/"), dry_run=args.dry_run, images=not args.no_images,
        requests_only=args.requests)


if __name__ == "__main__":
    main()
