"""The site owner's e-mails: the daily report, and one X thread on request ("Email me this thread").

Daily report: every morning at the owner's hour (8:00 by default, in the owner's time zone), one e-mail with every
company that filed since the last report (over the owner's minimum revenue, or all of them: "the full report"), largest
first. For each: which filing and when, what the company does
(its SEC industry, revenue by line, its own description), the charts (this quarter, and against a year earlier),
the analysis and the ready-to-post X thread.

Settings come from the #owner page (Supabase table owner_settings), else from config/x.json, else the defaults below.
The report goes to the addresses in Supabase's site_owners table, else to MAIL_TO / MAIL_USERNAME.

    python -m pipeline.social --site _site --store store        # the scan's sending step calls send_daily() when due
"""
import datetime as dt
import html as H
import os
import re
from email.message import EmailMessage
from email.utils import make_msgid

from . import checks, notify, social

DEFAULTS = {"thread_direct": True, "daily_on": True, "daily_hour": 8, "tz": "Asia/Shanghai", "min_revenue": 1e9,
            "instant_threads": False,
            "daily_scope": "min_revenue",     # "all": every company that filed (the full report), whatever its revenue
            "reader_copy": False}             # also the reader e-mails the owner's own alert settings ask for (notify.py)
FULL_ITEMS = 20             # companies shown in full; the rest are listed with links
KEEP_SENT_DAYS = 30

INK, INK2, MUTED, ACCENT, LINE, PAPER, GROUND, FONT = (notify.INK, notify.INK2, notify.MUTED, notify.ACCENT, notify.LINE,
                                                       notify.PAPER, notify.GROUND, notify.FONT)


# ------------------------------------------------------------------ settings and addresses
def supa_from_env():
    url, key = notify.setting("SUPABASE_URL", url=True), notify.setting("SUPABASE_SERVICE_KEY")
    return notify.Supa(url, key) if url and key else None


def settings(supa, cfg=None):
    """The owner's preferences: Supabase owner_settings, else config/x.json keys of the same names, else DEFAULTS."""
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    if supa:
        try:
            rows = supa.select("owner_settings", {"select": "*"})
            if rows:
                s.update({k: v for k, v in rows[0].items() if k in DEFAULTS and v is not None})
        except Exception as err:                       # schema.sql not run again yet: the defaults
            print(f"owner settings not read ({str(err)[:120]}); using the defaults")
    return s


def owner_emails(supa):
    """Lower-case addresses of the site owners (Supabase site_owners), or an empty set."""
    if not supa:
        return set()
    try:
        return {str(r["email"]).strip().lower() for r in supa.select("site_owners", {"select": "email"}) if r.get("email")}
    except Exception as err:
        print(f"site owners not read ({str(err)[:120]})")
        return set()


def addresses(supa):
    """Where the owner's daily report goes: the site owners' addresses, else MAIL_TO, else MAIL_USERNAME."""
    got = sorted(owner_emails(supa))
    if got:
        return got
    one = os.environ.get("MAIL_TO") or os.environ.get("MAIL_USERNAME") or ""
    return [one] if one else []


# ------------------------------------------------------------------ what goes in
def is_full(s):
    return s.get("daily_scope") == "all"


def scope_words(s):
    """What the owner's report covers, for its first line."""
    if is_full(s):
        return "every company that filed (the full report)"
    min_b = (s.get("min_revenue") or 0) / 1e9
    return f"companies with quarterly revenue of ${min_b:g}B or more" if min_b else "every company that filed"


def pending(ix, st, s, cfg, now):
    """Filings not in an earlier daily report: filed in the last few days, revenue at least the owner's minimum (any
    revenue in the full report)."""
    sent = (st.get("daily") or {}).get("sent") or {}
    out = []
    for e in ix["companies"]:
        if not e.get("filed") or (now.date() - dt.date.fromisoformat(e["filed"])).days > cfg.get("max_age_days", 3):
            continue
        if not is_full(s) and (e.get("revenue") or 0) < (s.get("min_revenue") or 0):
            continue
        if e.get("prelim") and not cfg.get("preliminary", True):
            continue
        if cfg.get("scope") == "starred" and not e.get("starred"):
            continue
        if notify.item_key(e) in sent:
            continue
        out.append(e)
    out.sort(key=lambda e: -(e.get("revenue") or 0))
    return out


def due_slot(now, s, st):
    """The time today's report was due (UTC), when it is due now and not sent yet; else None."""
    if not s.get("daily_on"):
        return None
    slot = notify.local_slot(now, s.get("daily_hour", 8), s.get("tz"))
    if now - slot >= dt.timedelta(hours=notify.DIGEST_WINDOW_HOURS):
        return None
    last = (st.get("daily") or {}).get("last")
    if last and notify.parse_ts(last) >= slot:
        return None
    return slot


def mark_sent(st, items, slot, now):
    d = st.setdefault("daily", {})
    d["last"] = slot.isoformat()
    sent = d.setdefault("sent", {})
    stamp = now.isoformat(timespec="seconds")
    for e, *_ in items:
        sent[notify.item_key(e)] = stamp
    old = (now - dt.timedelta(days=KEEP_SENT_DAYS)).isoformat()
    for k in [k for k, t in sent.items() if t < old]:
        del sent[k]


# ------------------------------------------------------------------ the e-mail
def _esc(s):
    return H.escape(str(s or ""))


def _h3(txt):
    return (f'<p style="margin:16px 0 6px;font:600 12px/1.4 {FONT};letter-spacing:.06em;text-transform:uppercase;'
            f'color:{MUTED}">{_esc(txt)}</p>')


def report_message(items, images, cfg, sender, to, subject, lead, site_url, full=FULL_ITEMS, rest_title="Also new"):
    """items: [(index entry, company json, quarter, thread parts)]; images: {item key: {"std": jpg, "y": jpg}}.
    One HTML e-mail (with a plain-text copy) laid out for reading on a phone."""
    site_url = (site_url or "").rstrip("/")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg["Auto-Submitted"] = "auto-generated"
    budget = notify.env_int("MAIL_MAX_BYTES", notify.MAIL_MAX_BYTES)
    shown, used = [], 0
    for it in items[:full]:                            # each company's charts while they fit; the rest as a list
        k = notify.item_key(it[0])
        pics = {v: b for v, b in (images.get(k) or {}).items() if b}
        n = sum(len(b) for b in pics.values())
        if shown and used + n > budget:
            break
        shown.append(it)
        used += n
    rest = items[len(shown):]
    text, rich, related = [lead, ""], [], []
    p_style = f"margin:0 0 12px;font:15px/1.55 {FONT};color:{INK}"

    if len(items) > 1:
        listed = shown if rest else items             # with a list at the end, the top names the companies in full
        text += (["In this report:"] + [f"- {e.get('ticker') or ''} {social.display_name(c['profile']['name'])} {q.get('label')}: "
                                        f"{social.form_words(q)} filed {social.fdate(q.get('filed'))}" for e, c, q, _ in listed]
                 + ([f"- and {len(rest)} more, listed at the end"] if rest else []) + [""])
        rich.append(f'<tr><td style="padding:0 0 18px">{_h3("In this report")}'
                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
                    f'{notify.summary_rows_html([(e, c, q) for e, c, q, _ in listed], site_url)}'
                    f'{notify.more_row_html(len(rest), "listed at the end")}</table></td></tr>')

    def pic(img, link, alt, fname):
        cid = make_msgid(domain="filing-flows")
        related.append((img, cid, fname))
        tag = (f'<img src="cid:{cid[1:-1]}" width="632" alt="{_esc(alt)}" '
               f'style="display:block;width:100%;max-width:632px;height:auto;border:1px solid {LINE};border-radius:6px">')
        return (f'<a href="{_esc(link)}">{tag}</a>' if link else tag) + '<div style="height:10px"></div>'

    for e, c, q, parts in shown:
        k = notify.item_key(e)
        name = social.display_name(c["profile"]["name"])
        url = notify.page_url(site_url, e)
        pics = images.get(k) or {}
        acc = re.search(r"(\d{10}-\d{2}-\d{6})", q.get("index_url") or "")
        period = (f"{'Fiscal year' if q.get('period') == 'fy' else 'Quarter'} ended {social.fdate(q.get('end'))}"
                  + (f" · accession {acc.group(1)}" if acc else ""))
        text += ["=" * 64, notify.eyebrow(e, q), name, notify.headline(e, q), period]
        rich.append(f'<tr><td style="padding:22px 0 8px;border-top:1px solid {LINE}">'
                    f'<div style="font:600 12px/1.4 {FONT};letter-spacing:.06em;text-transform:uppercase;color:{MUTED}">{_esc(notify.eyebrow(e, q))}</div>'
                    f'<h2 style="margin:4px 0 6px;font:600 22px/1.25 {FONT};color:{INK}">{_esc(name)}</h2>'
                    f'<p style="margin:0 0 4px;font:500 15px/1.5 {FONT};color:{INK2}">{_esc(notify.headline(e, q))}</p>'
                    f'<p style="margin:0 0 6px;font:13.5px/1.5 {FONT};color:{MUTED}">{_esc(period)}</p>')
        if q.get("form") == "8-K":
            rich.append(f'<p style="margin:0 0 8px;font:13px/1.5 {FONT};color:{MUTED}">Preliminary: read from the earnings '
                        "release; replaced by the 10-Q/10-K when it is filed.</p>")
        note = notify.release_note(q)
        if note:
            text.append(note)
            rich.append(f'<p style="margin:6px 0 8px;padding:8px 12px;border-radius:6px;background:#dcebe2;font:14px/1.5 {FONT};'
                        f'color:#0f5134">{_esc(note)}</p>')
        if checks.has_warning(q.get("checks")):
            text.append("CHECK BEFORE POSTING: a probable data error (see below).")
        text.extend(checks.lines(q))
        rich.append(checks.html_box(q, owner=True))
        ind, mix = notify.business_rows(c, q)
        about = notify.intro_text(c, 520)
        if ind or mix or about:
            text += ["", "What the company does:"] + [x for x in (ind, mix) if x]
            rich.append(_h3("What the company does"))
            if ind or mix:
                rich.append(f'<p style="margin:0 0 10px;font:14px/1.55 {FONT};color:{INK2}">'
                            + "<br>".join(_esc(x) for x in (ind, mix) if x) + "</p>")
            if about:
                text.append(f"In its own words: {about} ({notify.intro_source(c)})")
                rich.append(f'<p style="margin:0 0 6px;padding:2px 0 2px 12px;border-left:3px solid #a8d1b9;font:14px/1.55 {FONT};color:{INK2}">'
                            f'{_esc(about)}<span style="display:block;margin-top:3px;font-size:12.5px;color:{MUTED}">'
                            f'{_esc(notify.intro_source(c))}</span></p>')
        caps = social.chart_captions(q, bool(pics.get("y")))
        if pics.get("std"):
            rich.append(_h3("The charts" if len(caps) > 1 else "The chart"))
            text += ["", "The charts:" if len(caps) > 1 else "The chart:"]
            for (short, cap), view in zip(caps, ("std", "y")):
                text.append(f"{short}: {cap}.")
                rich.append(f'<p style="margin:0 0 6px;font:13.5px/1.5 {FONT};color:{INK2}"><b>{_esc(short)}</b> · {_esc(cap)}.</p>'
                            + pic(pics[view], url, f"{name} {q.get('label')} {short}", notify.view_file(e, q, view, "jpg")))
        if q.get("analysis"):
            rich.append(_h3("Analysis"))
            text += ["", "Analysis:"]
            for para in q["analysis"]:
                text += [para, ""]
                rich.append(f'<p style="{p_style}">{_esc(para)}</p>')
        cmp = q.get("compare_y") or {}
        if cmp.get("bullets"):
            text += [f"What changed vs {cmp.get('vs')}:"] + [f"- {b}" for b in cmp["bullets"]] + [""]
            rich.append(f'<p style="margin:4px 0 6px;font:600 15px/1.4 {FONT};color:{INK}">What changed vs {_esc(cmp.get("vs"))}</p>'
                        f'<ul style="margin:0 0 12px;padding-left:20px;font:15px/1.55 {FONT};color:{INK}">'
                        + "".join(f'<li style="margin:0 0 4px">{_esc(b)}</li>' for b in cmp["bullets"]) + "</ul>")
        if parts:
            intent = social.intent_url(parts[0]["text"])
            rich.append(_h3(f"X thread · {len(parts)} posts"))
            rich.append(f'<p style="margin:0 0 8px;font:13.5px/1.5 {FONT};color:{INK2}">Post 1 goes out with the chart'
                        f'{"s" if len(caps) > 1 else ""} above attached; each later post replies to the one before. '
                        f'<a href="{_esc(intent)}" style="color:{ACCENT}">Open post 1 in X</a>'
                        + (f' · full-size PNGs: “Email me this thread” on the <a href="{_esc(url)}" style="color:{ACCENT}">company page</a>' if url else "")
                        + "</p>")
            text += ["", f"X thread ({len(parts)} posts). Open post 1 in X: {intent}"]
            for i, x in enumerate(parts):
                label = f"Post {i + 1} · {social.ROLES.get(x['role'], '')} · {social.xlen(x['text'])}/{social.LIMIT}"
                text += [f"--- {label} ---", x["text"], ""]
                rich.append(f'<div style="font:12px {FONT};color:{MUTED};margin:10px 0 3px">{_esc(label)}</div>'
                            f'<pre style="white-space:pre-wrap;font:14.5px/1.45 {FONT};background:{GROUND};'
                            f'border-radius:6px;padding:10px 12px;margin:0">{_esc(x["text"])}</pre>')
        links = [(u, label) for u, label in ((url, "Interactive chart"), (q.get("index_url"), "The filing on SEC EDGAR"),
                                            (q.get("doc_url"), "Press release" if q.get("form") == "8-K" else "The report")) if u]
        text += [f"{label}: {u}" for u, label in links] + [""]
        rich.append(f'<p style="margin:14px 0 0;font:600 14.5px/1.5 {FONT}">'
                    + " &nbsp;·&nbsp; ".join(f'<a href="{_esc(u)}" style="color:{ACCENT}">{label}</a>' for u, label in links)
                    + "</p></td></tr>")

    if rest:
        text += ["=" * 64, f"{rest_title} ({len(rest)}):"]
        listed, hidden = rest[:notify.REST_MAX], len(rest) - notify.REST_MAX
        for e, c, q, _ in listed:
            u = notify.page_url(site_url, e)
            text.append(f"- {e.get('ticker') or ''} {social.display_name(c['profile']['name'])} {q.get('label')}"
                        + (f"  {u}" if u else ""))
        if hidden > 0:
            text.append(f"- and {hidden} more on the site" + (f": {site_url}/#home" if site_url else ""))
        rich.append(f'<tr><td style="padding:8px 0 18px;border-top:1px solid {LINE}"><p style="margin:14px 0 6px;font:600 16px {FONT};color:{INK}">'
                    f'{_esc(rest_title)}</p><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
                    f'{notify.summary_rows_html([(e, c, q) for e, c, q, _ in listed], site_url)}'
                    f'{notify.more_row_html(hidden, "on the site", f"{site_url}/#home" if site_url else "")}</table></td></tr>')
    foot = ("Charts, analysis and threads are generated by fixed rules from SEC filings; quotes are the companies' own words. "
            "Figures are read automatically and can contain errors: check the filing before posting. "
            "Not investment advice. Change this report on the site's #owner page.")
    text += ["-" * 64, foot]
    owner_link = f'{site_url}/#owner' if site_url else ""
    html = (f'<div style="background:{GROUND};padding:20px 10px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="max-width:680px;margin:0 auto;background:{PAPER};border-radius:10px;border-collapse:separate">'
            f'<tr><td style="padding:22px 24px 0"><div style="font:600 13px {FONT};letter-spacing:.08em;text-transform:uppercase;color:{ACCENT}">Filing Flows · owner</div>'
            f'<p style="margin:6px 0 16px;font:15px/1.5 {FONT};color:{INK2}">{_esc(lead)}</p></td></tr>'
            f'<tr><td style="padding:0 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rich)}</table></td></tr>'
            f'<tr><td style="padding:4px 24px 22px;border-top:1px solid {LINE}"><p style="margin:14px 0 6px;font:12.5px/1.5 {FONT};color:{MUTED}">{_esc(foot)}</p>'
            + (f'<p style="margin:0;font:12.5px/1.5 {FONT}"><a href="{_esc(owner_link)}" style="color:{MUTED}">Owner settings</a></p>' if owner_link else "")
            + '</td></tr></table></div>')
    msg.set_content("\n".join(text))
    msg.add_alternative(html, subtype="html")
    part = msg.get_payload()[1]
    for img, cid, fname in related:
        part.add_related(img, maintype="image", subtype="jpeg", cid=cid, filename=fname, disposition="inline")
    return msg


def load(site, entries, cfg):
    """Index entries -> [(entry, company json, quarter, thread parts)] (company files read once)."""
    out, cache = [], {}
    for e in entries:
        k = notify.item_key(e)
        if k not in cache:
            try:
                cache[k] = site.quarter(e)
            except Exception as err:
                print(f"::warning::{e.get('ticker') or e['cik']} not read ({err})")
                cache[k] = None
        if cache[k]:
            c, q = cache[k]
            out.append((e, c, q, social.compose_parts(c, q, cfg)))
    return out


def images_for(assets, items, cfg, full=FULL_ITEMS):
    """{item key: {"std": jpg, "y": jpg}} for the companies shown in full (drawn once, in one Chromium)."""
    out = {}
    for e, c, q, _ in items[:full]:
        k = notify.item_key(e)
        out[k] = {"std": assets.image(e, c, q, "std")}
        if "year_ago" in (cfg.get("images") or []) and q.get("compare_y"):
            out[k]["y"] = assets.image(e, c, q, "y")
    return out


def subject_line(items, day_short):
    tick = [e.get("ticker") or social.display_name(c["profile"]["name"]) for e, c, *_ in items]
    return (f"Daily report, {day_short}: {len(items)} new filing{'s' if len(items) != 1 else ''} — "
            f"{', '.join(tick[:6])}{' and more' if len(tick) > 6 else ''}")


def send_daily(site, st, cfg, s, now, slot, mailer_send, sender, to_list, site_url, dry_run=False, assets=None):
    """Build and send the owner's daily report for the filings not in an earlier one. Returns the number sent."""
    ix = site.json("index.json")
    todo = pending(ix, st, s, cfg, now)
    if not todo:
        print("owner daily report: nothing new since the last one")
        mark_sent(st, [], slot, now)
        return 0
    items = load(site, todo, cfg)
    own = assets is None
    assets = assets or notify.Assets(site, enabled=not dry_run)
    try:
        pics = images_for(assets, items, cfg)
    finally:
        if own:
            assets.close()
    tz = s.get("tz")
    lead = (f"Your {'full ' if is_full(s) else ''}daily report for {notify.day_words(now, tz)}: {len(items)} "
            f"filing{'s' if len(items) != 1 else ''} since the last report, {scope_words(s)}, largest first.")
    sent = 0
    for to in to_list:
        msg = report_message(items, pics, cfg, sender, to, subject_line(items, notify.day_words(now, tz, True)), lead, site_url)
        if dry_run:
            print(f"--- owner daily report to {notify.mask(to)}: {msg['Subject']}")
            sent += 1
            continue
        mailer_send(msg)
        sent += 1
        print(f"owner daily report e-mailed to {notify.mask(to)}: {msg['Subject']}")
    if sent and not dry_run:
        mark_sent(st, items, slot, now)
    return sent


def day_message(site, day, s, cfg, sender, to, site_url, assets):
    """The owner's report of one filing date (the home page's "Email me this day's report"), or None if nothing filed."""
    entries = [e for e in notify.entries_for_day(site.json("index.json"), day)
               if is_full(s) or (e.get("revenue") or 0) >= (s.get("min_revenue") or 0)]
    if not entries:
        return None
    entries.sort(key=lambda e: -(e.get("revenue") or 0))
    items = load(site, entries, cfg)
    pics = images_for(assets, items, cfg)
    words = dt.date.fromisoformat(day).strftime("%A, %B %-d, %Y")
    lead = (f"The {'full ' if is_full(s) else ''}report for filings dated {words}: {len(items)} "
            f"filing{'s' if len(items) != 1 else ''}, {scope_words(s)}, largest first.")
    return report_message(items, pics, cfg, sender, to, subject_line(items, dt.date.fromisoformat(day).strftime("%b %-d")), lead, site_url)


def thread_message(e, c, q, assets, cfg, sender, to):
    """One quarter's X thread with its chart PNGs attached (the owner's "Email me this thread")."""
    modes = ["std"] + (["y"] if "year_ago" in (cfg.get("images") or []) and q.get("compare_y") else [])
    pngs = [assets.image(e, c, q, m, "png") for m in modes]
    names = social.image_names(e, q, len(modes))
    files = [(n, p) for n, p in zip(names, pngs) if p]
    item = (e, c, q, social.compose_parts(c, q, cfg), files)
    return social.build_email([item], cfg, sender, to)
