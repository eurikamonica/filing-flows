"""Assemble the static site: web/ (app) + rendered data/ -> _site/.

    python scripts/build_site.py --data _site/data --out _site
    python scripts/build_site.py --data _site/data --out demo --inline   # single-page bundle (CSS + JS inlined)
"""
import argparse
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def setting(name, url=False):
    """An environment setting as pasted into GitHub, forgiving quotes, spaces, a whole "NAME = value" line and,
    for the Supabase project URL, a trailing /rest/v1 (same rules as pipeline.notify.setting)."""
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
        shown = f"using {v}" if url else "using the value inside it"
        print(f"::warning::{name} had extra text around the value; {shown}. Fix it in Settings → Secrets and variables → Actions.")
    if url and v and not v.startswith("https://"):
        print(f"::warning::{name} should look like https://xxxx.supabase.co")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="_site/data", help="directory written by `pipeline.build render`")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--inline", action="store_true", help="inline styles.css, sankey.js and app.js into index.html")
    ap.add_argument("--fragment", action="store_true",
                    help="with --inline: write the page without <!doctype>/<html>/<head>/<body> (for hosts that add their own)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    if args.inline:
        css = open(os.path.join(WEB, "styles.css"), encoding="utf-8").read()
        html = html.replace('<link rel="stylesheet" href="styles.css">', f"<style>\n{css}</style>")
        for name in ("sankey.js", "app.js"):
            js = open(os.path.join(WEB, name), encoding="utf-8").read()
            html = html.replace(f'<script src="{name}"></script>', f"<script>\n{js}</script>")
        if args.fragment:
            head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
            keep = [m.group(0) for m in re.finditer(r"<title>.*?</title>|<link [^>]*fonts\.(?:googleapis|gstatic)[^>]*>|<style>.*?</style>", head, re.S)]
            shell = re.search(r"<!--SHELL-->(.*?)<!--/SHELL-->", html, re.S).group(1)
            scripts = re.findall(r"<script>.*?</script>", html, re.S)
            html = "\n".join(keep) + "\n" + shell + "\n".join(scripts) + "\n"
    else:
        for name in ("styles.css", "sankey.js", "app.js"):
            shutil.copy(os.path.join(WEB, name), os.path.join(args.out, name))
    open(os.path.join(args.out, "index.html"), "w", encoding="utf-8").write(html)
    data_out = os.path.join(args.out, "data")
    if os.path.abspath(args.data) != os.path.abspath(data_out):
        shutil.rmtree(data_out, ignore_errors=True)
        shutil.copytree(args.data, data_out)
    site = {"repo": os.environ.get("GITHUB_REPOSITORY", ""),
            # accounts: the project URL and the public (publishable / anon) key; row-level security protects the data
            "supabase_url": setting("SUPABASE_URL", url=True), "supabase_key": setting("SUPABASE_ANON_KEY"),
            "contact": setting("CONTACT_EMAIL")}       # shown on the privacy and terms pages
    json.dump(site, open(os.path.join(data_out, "site.json"), "w"))
    # privacy policy and terms: plain pages (app stores and crawlers read them without running the site's script)
    if site["contact"]:
        contact = f'e-mail <a href="mailto:{site["contact"]}">{site["contact"]}</a>'
    elif site["repo"]:
        contact = f'open an issue at <a href="https://github.com/{site["repo"]}/issues">github.com/{site["repo"]}</a>'
    else:
        contact = "contact the site owner"
    for name in ("privacy.html", "terms.html"):
        page = open(os.path.join(WEB, name), encoding="utf-8").read().replace("<!--CONTACT-->", contact)
        open(os.path.join(args.out, name), "w", encoding="utf-8").write(page)
    open(os.path.join(args.out, ".nojekyll"), "w").close()
    n = sum(len(f) for _, _, f in os.walk(data_out))
    print(f"site written to {args.out} ({n} data files)")


if __name__ == "__main__":
    main()
