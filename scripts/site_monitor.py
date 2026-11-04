"""Is the site up, current and healthy? Run every half hour by server-monitor.yml (deploy/README.md, "Monitoring").

    python scripts/site_monitor.py --base https://filing-flows.com [--server-status server.json] [--state s.json]

Checks the public site, wherever it is served: the home page, robots.txt and the sitemap index answer 200, a
missing page answers 404, www goes to the bare domain, the HTTPS certificate has two weeks or more left, and the
build stamp (data/industry-intelligence/integration-health.json, written by every scan) is under three hours old.
With the own server's status (pipeline/server_status.py, over SSH) also: disk under 80% full, the web server
running, the last publish under two hours old. Problems go to the owner by e-mail (the MAIL_* secrets, as the
daily report) when they start, every 6 hours while they last, and once more when all is well again; the state of
the last run is kept in --state (the Actions cache). Exits 1 only when there is a problem no e-mail could report.
"""
import argparse
import datetime as dt
import json
import os
import smtplib
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import server_status  # noqa: E402

UA = "FilingFlows-Monitor/1.0"
STAMP = "/data/industry-intelligence/integration-health.json"
MAX_AGE_H = 3
CERT_DAYS = 14
REPEAT_H = 6


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(url, timeout=20):
    """(status, headers, body); 0 when nothing answered."""
    try:
        with OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"}),
                         timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, {"error": str(getattr(e, "reason", e))[:120]}, b""


def cert_days(host, port=443, timeout=15):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        end = ssl.cert_time_to_seconds(t.getpeercert()["notAfter"])
    return (end - time.time()) / 86400


def site_problems(base, now, fetch=get, days=cert_days):
    base = base.rstrip("/")
    host = urlsplit(base).hostname
    out = []
    for path, want in (("/", 200), ("/robots.txt", 200), ("/sitemap-index.xml", 200),
                       ("/ff-monitor-no-such-page", 404)):
        st, h, body = fetch(base + path + ("?monitor=%d" % int(now.timestamp()) if want == 200 else ""))
        if st != want:
            out.append(f"{path} answered {st or 'nothing'}" + (f" ({h.get('error')})" if not st else "")
                       + f" instead of {want}")
        elif path == "/" and b"<html" not in body[:4096].lower():
            out.append("the home page came back without HTML")
    st, h, _ = fetch(f"https://www.{host}/")
    loc = h.get("Location") or h.get("location") or ""
    if st and (st not in (301, 308) or urlsplit(loc).hostname != host):     # no www record at all: not an outage
        out.append(f"www.{host} answered {st} instead of a redirect to {host}")
    st, _, body = fetch(base + STAMP + "?monitor=%d" % int(now.timestamp()))
    try:
        stamp = json.loads(body)["generated_at"]
        age = (now - dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 3600
        if age > MAX_AGE_H:
            out.append(f"the site was last built {age:.0f} hours ago (it is rebuilt every 15 minutes)")
    except (ValueError, KeyError, TypeError):
        out.append(f"the build stamp {STAMP} is missing or unreadable ({st})")
    try:
        left = days(host)
        if left < CERT_DAYS:
            out.append(f"the HTTPS certificate expires in {left:.0f} days")
    except (OSError, ssl.SSLError, KeyError, ValueError) as e:
        out.append(f"HTTPS certificate check failed ({type(e).__name__})")
    return out


def send(subject, text, env=os.environ):
    user, password = env.get("MAIL_USERNAME"), env.get("MAIL_PASSWORD")
    to = env.get("MAIL_TO") or user
    if not (user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, env.get("MAIL_FROM") or user, to
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    host, port = env.get("SMTP_HOST") or "smtp.gmail.com", int(env.get("SMTP_PORT") or 465)
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=60)
        else:
            s = smtplib.SMTP(host, port, timeout=60)
            s.starttls()
        s.login(user, password)
        s.send_message(msg)
        s.quit()
        return True
    except (OSError, smtplib.SMTPException) as e:
        print(f"::warning::monitor e-mail not sent: {type(e).__name__}")
        return False


def decide(problems, state, now):
    """('alert' | 'repeat' | 'recovered' | None, new state)."""
    was = state.get("problems") or []
    last = state.get("alerted_at")
    age = (now.timestamp() - last) / 3600 if last else None
    if problems:
        if not was or set(problems) != set(was):
            return "alert", {"problems": problems, "alerted_at": now.timestamp(), "since": state.get("since") or now.isoformat()}
        if age is None or age >= REPEAT_H:
            return "repeat", {**state, "problems": problems, "alerted_at": now.timestamp()}
        return None, {**state, "problems": problems}
    if was:
        return "recovered", {}
    return None, {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default=os.environ.get("SITE_URL") or "https://filing-flows.com")
    ap.add_argument("--server-status", help="ff-status JSON fetched over SSH (none: no own server)")
    ap.add_argument("--state", default=".monitor/state.json")
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    problems = site_problems(a.base, now)
    status = None
    if a.server_status and os.path.exists(a.server_status):
        try:
            status = json.load(open(a.server_status))
        except ValueError:
            status = {"error": "unreadable status"}
    if status:
        problems += [f"own server: {p}" for p in server_status.problems(status, now)]
    try:
        state = json.load(open(a.state))
    except (OSError, ValueError):
        state = {}
    action, state = decide(problems, state, now)

    lines = [f"- {p}" for p in problems] or ["- all checks passed"]
    srv = server_status.sentence(status, now) if status else "No own server checked."
    report = "\n".join([f"Site check {now:%Y-%m-%d %H:%M} UTC for {a.base}", ""] + lines + ["", srv])
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("## Site monitor\n\n" + "\n".join(lines) + "\n\n" + srv + "\n")
    sent = True
    if action in ("alert", "repeat"):
        sent = send("Filing Flows 网站监控：需要处理 / site check: needs a look",
                    "网站监控发现问题 / The site check found:\n\n" + "\n".join(lines) + "\n\n" + srv +
                    "\n\nThe run: " + os.environ.get("RUN_URL", "(GitHub Actions, workflow server-monitor.yml)"))
        if not sent:
            state["alerted_at"] = None                 # no e-mail went out: try again next run (and fail this one)
    elif action == "recovered":
        send("Filing Flows 网站监控：已恢复 / site check: all well again", report)
    os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
    with open(a.state, "w") as f:
        json.dump(state, f)
    return 1 if (problems and not sent) else 0


if __name__ == "__main__":
    sys.exit(main())
