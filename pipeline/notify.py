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

from . import social

MAX_AGE_DAYS = 3            # charts for filings older than this are not sent
FULL_ITEMS = 6              # charts shown in full per e-mail; the rest are listed with a link
REQUEST_FULL_ITEMS = 10     # reports a reader asked for are all shown in full (up to this many per e-mail)
REQUEST_ATTEMPTS = 3
STALE_CLAIM_MINUTES = 30
SAME_QUARTER_DAYS = 10      # an 8-K quarter and the 10-Q/10-K that replaces it count as one item
KEEP_DELIVERIES_DAYS = 120


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


def item_key(e):
    """"<cik>:<quarter end>", plus ":8-K" for a chart read from an earnings release."""
    return f"{int(e['cik'])}:{e['end']}" + (":8-K" if is_prelim(e) else "")


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
    return " · ".join(x for x in (e.get("ticker"), q.get("label"), f"{form} filed {social.fdate(q.get('filed'))}",
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
    return f"{site_url}/#c-{e['cik']}-{e['end']}" if site_url else ""


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


def build_message(sub, items, site_url, images, sender, daily=False, requested=False):
    """items: [(index entry, company json, quarter, reasons)]; images: {item key: jpeg bytes}."""
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
        img = images.get(item_key(e))
        if img:
            cid = make_msgid(domain="filing-flows")
            related.append((img, cid, re.sub(r"[^A-Za-z0-9.]+", "-", f"{e.get('ticker') or e['cik']}-{q.get('label')}") + ".jpg"))
            pic = (f'<img src="cid:{cid[1:-1]}" width="632" alt="{H.escape(q.get("title") or name)} Sankey chart" '
                   f'style="display:block;width:100%;max-width:632px;height:auto;border:1px solid {LINE};border-radius:6px">')
            rich.append((f'<a href="{H.escape(url)}">{pic}</a>' if url else pic) + '<div style="height:14px"></div>')
        for para in q.get("analysis") or []:
            text.append(para)
            text.append("")
            rich.append(f'<p style="{p_style}">{H.escape(para)}</p>')
        cy = q.get("compare_y") or {}
        if cy.get("bullets"):
            text.append(f"What changed vs {cy.get('vs')}:")
            text += [f"- {b}" for b in cy["bullets"]] + [""]
            rich.append(f'<p style="margin:4px 0 6px;font:600 15px/1.4 {FONT};color:{INK}">What changed vs {H.escape(cy.get("vs") or "a year earlier")}</p>'
                        f'<ul style="margin:0 0 12px;padding-left:20px;font:15px/1.55 {FONT};color:{INK}">'
                        + "".join(f'<li style="margin:0 0 4px">{H.escape(b)}</li>' for b in cy["bullets"]) + "</ul>")
        quote = social.filing_quote(q)
        if quote:
            words = quote[0] if len(quote[0]) <= 700 else quote[0][:700].rsplit(" ", 1)[0] + " …"
            text += [f"From the filing: “{words}” — {quote[1]}", ""]
            rich.append(f'<blockquote style="margin:0 0 12px;padding:2px 0 2px 14px;border-left:3px solid #a8d1b9;font:14.5px/1.55 {FONT};color:{INK2}">'
                        f'“{H.escape(words)}”<div style="margin-top:4px;font-size:13px;color:{MUTED}">— {H.escape(quote[1])}</div></blockquote>')
        links = [(u, label) for u, label in ((url, "Open the interactive chart"), (q.get("index_url"), "The filing on SEC EDGAR")) if u]
        text += [f"{label}: {u}" for u, label in links]
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
        part.add_related(img, maintype="image", subtype="jpeg", cid=cid, filename=fname)
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
    """{item key: (index entry, quarter)} -> {item key: jpeg}; empty when Chromium is not available."""
    if not wanted:
        return {}
    try:
        keys = list(wanted)
        jpgs = social.render_charts(site.src, [(wanted[k][1], None) for k in keys], fmt="jpg", width=1400, quality=0.85)
        return dict(zip(keys, jpgs))
    except Exception as err:                                  # e-mails still go out, with a link instead
        print(f"charts not rendered ({err.__class__.__name__}: {err}); sending without images", file=sys.stderr)
        return {}


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


def find_quarter(site, cik, end):
    """The quarter a reader asked for; an 8-K quarter that a 10-Q/10-K has since replaced resolves to the latter."""
    try:
        c = site.json(f"c/{int(cik)}.json")
    except Exception:
        return None, None
    e0 = dt.date.fromisoformat(str(end)[:10])
    best = None
    for q in c["quarters"]:
        d = abs((dt.date.fromisoformat(q["end"]) - e0).days)
        if d <= SAME_QUARTER_DAYS and (best is None or d < best[0]):
            best = (d, q)
    return c, (best[1] if best else None)


def process_requests(site, supa, mailer, sender, site_url, now, dry_run, images, budget):
    """E-mail the reports readers asked for with "Email me". Returns the number of e-mails sent."""
    if dry_run:
        reqs = supa.select("send_requests", {"select": "id,user_id,cik,period_end,attempts,created_at", "status": "eq.pending"})
    else:
        reqs = claim_requests(supa, now)
    if not reqs:
        return 0
    users = sorted({r["user_id"] for r in reqs})
    subs = {s_["user_id"]: s_ for s_ in supa.select("subscriptions", {
        "select": "user_id,email,unsub_token", "user_id": f"in.({','.join(users)})"})}
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
            c, q = find_quarter(site, r["cik"], r["period_end"])
            if not q:
                missing.append(r)
                continue
            e = {"cik": int(r["cik"]), "end": q["end"], "form": q.get("form"), "ticker": (c["profile"].get("tickers") or [""])[0],
                 "name": c["profile"]["name"], "rev": (q.get("headline") or {}).get("rev_fmt")}
            if all(item_key(x[0]) != item_key(e) for x in items):     # the same quarter asked twice: one copy
                items.append((e, c, q, ["you asked for this report"]))
        finish(missing, status="failed", error="that quarter is no longer on the site")
        if items:
            jobs.append((sub, rows, [r for r in rows if r not in missing], items))
    if not jobs:
        return 0
    if len(jobs) > budget:
        print(f"::warning::daily e-mail limit reached; {len(jobs) - max(budget, 0)} requests wait for the next run")
        for _, _, ok_rows, _ in jobs[max(budget, 0):]:
            finish(ok_rows, status="pending", claimed_at=None)
        jobs = jobs[:max(budget, 0)]
    wanted = {item_key(e): (e, q) for _, _, _, items in jobs for e, c, q, _ in items}
    pics = render_images(site, wanted) if images and not dry_run else {}
    for sub, rows, ok_rows, items in jobs:
        msg = build_message(sub, items, site_url, pics, sender, requested=True)
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
    try:
        sent += process_requests(site, supa, mailer, sender, site_url, now, dry_run, images, budget)
        budget -= sent
        if requests_only:
            return sent
        ix = site.json("index.json")
        subs = supa.select("subscriptions", {"select": "user_id,email,tickers,sectors,all_above,min_revenue,starred,frequency,"
                                             "email_on,final_too,unsub_token,created_at", "email_on": "is.true",
                                             "order": "created_at.asc"})
        todo = plan(subs, dels, ix, now, hour, MAX_AGE_DAYS)
        print(f"{len(subs)} readers with e-mail on; {len(todo)} due now; {max(budget, 0)} e-mails left in the 24-hour limit")
        if budget < len(todo):
            print(f"::warning::daily e-mail limit reached; {len(todo) - max(budget, 0)} readers wait for the next run")
            todo = todo[:max(budget, 0)]
        cache, wanted = {}, {}
        loaded = [(sub, _load_items(site, cache, items)) for sub, items in todo]
        for sub, items in loaded:
            for e, c, q, _ in items[:FULL_ITEMS]:
                wanted[item_key(e)] = (e, q)
        pics = render_images(site, wanted) if images and not dry_run and loaded else {}
        for sub, items in loaded:
            msg = build_message(sub, items, site_url, pics, sender, daily=sub.get("frequency") == "daily")
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
