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


def x_options():
    """The owner page's "X posts" form: the starting values (config/x.json, until the owner saves their own) and the tag
    pools posts pick from (pipeline/hashtags.py). Nothing secret: the same tags appear in every post."""
    import sys
    sys.path.insert(0, ROOT)
    from pipeline import hashtags as H
    try:
        c = json.load(open(os.path.join(ROOT, "config", "x.json"), encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    media = [str(m).lower() for m in (c.get("media") or ["png", "jpg", "gif"])]
    more = engage_more()                          # first: the feature modules add their hashtag pools to H.KINDS
    return {"links": c.get("links", True) is not False, "gif": "gif" in media, "hashtags_max": int(c.get("hashtags_max", H.MAX)),
            "hashtags": H.clean(c["hashtags"]) if isinstance(c.get("hashtags"), list) else H.GENERAL,
            "headline_tag": c.get("headline_tag", "#earnings"), "tags": dict(H.PARTS), "kinds": H.KINDS,
            "industry": sorted({t for _, _, t in H.INDUSTRY} | set(H.SECTOR.values()), key=str.lower),
            "candidates": H.CANDIDATES, "engage_more": more}


def engage_more():
    """The owner's buttons for the post formats feature modules register (pipeline/posts_*.py, pipeline/xkinds.py)."""
    try:
        from pipeline import xkinds
        return xkinds.buttons()
    except Exception as err:                     # noqa: BLE001 — the site builds without them
        print(f"::warning::feature post formats not listed ({str(err)[:160]})")
        return []


# the page's scripts, in load order (web/index.html): the chart, the valuation maths, the discovery & UX modules, the app
SCRIPTS = ("nav.js", "sankey.js", "fsa.js", "chains.js", "gamma.js", "model.js", "network.js", "ux.js", "search.js", "overview.js", "feed.js", "charts.js", "studio.js", "editor.js", "eps-research.js", "local-model.js", "app.js")
STYLES = ("styles.css", "nav.css", "ux.css", "gamma.css", "eps-research.css", "local-model.css")


def page_assets(html):
    """Every local script and stylesheet web/index.html references, the lists above first: a file added to the page
    but not to a list was left out of the site (scenario-elasticity.js answered 404)."""
    scripts = list(SCRIPTS) + [s for s in re.findall(r'<script src="([\w.-]+\.js)"></script>', html) if s not in SCRIPTS]
    styles = list(STYLES) + [s for s in re.findall(r'<link rel="stylesheet" href="([\w.-]+\.css)">', html) if s not in STYLES]
    return ([s for s in scripts if os.path.exists(os.path.join(WEB, s))], [s for s in styles if os.path.exists(os.path.join(WEB, s))])


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
    scripts, styles = page_assets(html)
    if args.inline:
        for name in styles:
            css = open(os.path.join(WEB, name), encoding="utf-8").read()
            html = html.replace(f'<link rel="stylesheet" href="{name}">', f"<style>\n{css}</style>")
        for name in scripts:
            js = open(os.path.join(WEB, name), encoding="utf-8").read()
            html = html.replace(f'<script src="{name}"></script>', f"<script>\n{js}</script>")
        if args.fragment:
            head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
            keep = [m.group(0) for m in re.finditer(r"<title>.*?</title>|<link [^>]*fonts\.(?:googleapis|gstatic)[^>]*>|<style>.*?</style>", head, re.S)]
            shell = re.search(r"<!--SHELL-->(.*?)<!--/SHELL-->", html, re.S).group(1)
            scripts = re.findall(r"<script>.*?</script>", html, re.S)
            html = "\n".join(keep) + "\n" + shell + "\n".join(scripts) + "\n"
    else:
        for name in styles + scripts + ["favicon.svg", "favicon-32.png", "favicon.ico", "apple-touch-icon.png"]:
            shutil.copy(os.path.join(WEB, name), os.path.join(args.out, name))
    open(os.path.join(args.out, "index.html"), "w", encoding="utf-8").write(html)
    # test versions of views (web/beta/: Money flow Beta 1.0), served next to the site and linked from nowhere in it
    if not args.inline and os.path.isdir(os.path.join(WEB, "beta")):
        shutil.copytree(os.path.join(WEB, "beta"), os.path.join(args.out, "beta"), dirs_exist_ok=True)
    data_out = os.path.join(args.out, "data")
    if os.path.abspath(args.data) != os.path.abspath(data_out):
        shutil.rmtree(data_out, ignore_errors=True)
        shutil.copytree(args.data, data_out)
    site = {"repo": os.environ.get("GITHUB_REPOSITORY", ""),
            # accounts: the project URL and the public (publishable / anon) key; row-level security protects the data
            "supabase_url": setting("SUPABASE_URL", url=True), "supabase_key": setting("SUPABASE_ANON_KEY"),
            "contact": setting("CONTACT_EMAIL"),       # shown on the privacy and terms pages
            "x": x_options()}                          # the owner page's "X posts" form
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
    # search-engine pages (c/<ticker>/, sector/<id>/, sitemap.xml, robots.txt): the app's #c-… routes are not indexed
    if not args.inline:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import seo
        for name in ("seo.css", "og.png"):
            if os.path.exists(os.path.join(WEB, name)):
                shutil.copy(os.path.join(WEB, name), os.path.join(args.out, name))
        base = setting("SITE_URL", url=True)
        if not base and os.environ.get("GITHUB_REPOSITORY"):
            owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
            base = f"https://{owner.lower()}.github.io/{repo}"
        if base:
            print(f"search pages: {seo.write_pages(data_out, args.out, base)} companies, sitemap at {base}/sitemap.xml")
        try:                                     # the global search index and Atom feeds (redone after the hub is staged)
            import hub_extras
            r = hub_extras.build(args.out, base or "https://filing-flows.com/")
            print(f"search index: {r['managers']} managers, {r['officials']} officials, {r['etfs']} ETFs; {r['company_feeds']} company feeds")
        except Exception as err:                 # noqa: BLE001 — never fails the site
            print(f"::warning::search index / feeds not written ({str(err)[:160]})")
    # a custom domain (repository variable SITE_URL, e.g. https://filing-flows.com/): GitHub Pages reads the CNAME file
    host = re.sub(r"^https?://", "", setting("SITE_URL", url=True)).split("/")[0]
    if host and not host.endswith("github.io"):
        open(os.path.join(args.out, "CNAME"), "w").write(host + "\n")
    n = sum(len(f) for _, _, f in os.walk(data_out))
    print(f"site written to {args.out} ({n} data files)")


if __name__ == "__main__":
    main()
