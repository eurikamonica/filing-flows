"""The own server's state in one sentence, for the owner's daily report (deploy/README.md).

Asks the server over SSH with the deploy key ("status": ff-status, a JSON line with disk, memory, the web server
and the last publish). Nothing happens without the secrets DEPLOY_SSH_KEY, DEPLOY_KNOWN_HOSTS and DEPLOY_HOST, so
the report is unchanged for a site on GitHub Pages alone. The key goes to a private temporary file and is deleted
right after; nothing secret is printed or put in the report.
"""
import datetime as dt
import json
import os
import subprocess
import tempfile

DISK_WARN = 80          # % used
STALE_HOURS = 2         # the site is published every 15 minutes


def fetch(env=None, timeout=25, run=subprocess.run):
    """The server's status dict, {"error": …} when it does not answer, None when there is no server."""
    env = os.environ if env is None else env
    key, known = env.get("DEPLOY_SSH_KEY", ""), env.get("DEPLOY_KNOWN_HOSTS", "")
    host, user = env.get("DEPLOY_HOST", ""), env.get("DEPLOY_USER") or "deploy"
    if not (key.strip() and known.strip() and host.strip()):
        return None
    with tempfile.TemporaryDirectory() as d:
        os.chmod(d, 0o700)
        kf, hf = os.path.join(d, "key"), os.path.join(d, "known_hosts")
        for path, text in ((kf, key), (hf, known)):
            lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n") if ln.strip()]
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                f.write("\n".join(lines) + "\n")
        cmd = ["ssh", "-i", kf, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", f"UserKnownHostsFile={hf}", "-o", "ConnectTimeout=15", "-o", "LogLevel=ERROR",
               f"{user}@{host.strip()}", "status"]
        try:
            r = run(cmd, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as err:
            return {"error": type(err).__name__}
    if r.returncode != 0:
        return {"error": f"ssh exit {r.returncode}"}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "no status from the server"}


def _age_hours(stamp, now):
    try:
        t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None
    return (now - t).total_seconds() / 3600


def problems(s, now=None):
    """What needs the owner's attention, in plain words (empty: all well)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if s.get("error"):
        return [f"the server did not answer ({s['error']})"]
    out = []
    disk = s.get("disk") or {}
    if (disk.get("used_pct") or 0) >= DISK_WARN:
        out.append(f"its disk is {disk['used_pct']:.0f}% full ({disk.get('free_gb', 0):.1f} GB free)")
    if s.get("web") not in (None, "active"):
        out.append(f"the web server is {s.get('web')}")
    age = _age_hours(s.get("published_at"), now)
    if age is None:
        out.append("nothing has been published on it yet")
    elif age > STALE_HOURS:
        out.append(f"the site there was last updated {age:.0f} hours ago")
    return out


def sentence(s, now=None):
    """One sentence for the report's opening paragraph; '' without a server."""
    if not s:
        return ""
    now = now or dt.datetime.now(dt.timezone.utc)
    bad = problems(s, now)
    if s.get("error"):
        return f"Own server: needs a look — {bad[0]}."
    disk = s.get("disk") or {}
    parts = [f"disk {disk.get('used_pct', 0):.0f}% used ({disk.get('free_gb', 0):.0f} GB free)"]
    stamp = s.get("published_at")
    if stamp:
        parts.append(f"site updated {stamp[11:16]} UTC" + (f", {s['pages']:,} pages" if s.get("pages") else ""))
    if s.get("reboot_required"):
        parts.append("an update restarts it at 08:10 UTC")
    if bad:
        return f"Own server: needs a look — {'; '.join(bad)} ({', '.join(parts)})."
    return f"Own server: running fine ({', '.join(parts)})."


def report_line(env=None):
    """fetch() + sentence(); never raises (the report goes out either way)."""
    try:
        return sentence(fetch(env))
    except Exception as err:                  # noqa: BLE001 - the report must not fail over the server
        return f"Own server: status not available ({type(err).__name__})."
