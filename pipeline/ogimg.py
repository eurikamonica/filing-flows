"""Share pictures (og:image) for the search-engine pages: when a page of the site is posted on X, Reddit or in a chat,
the card shows that company's earnings Sankey or that chain's money flow instead of the site's one generic picture.

Drawn by the site's own renderer (web/sankey.js, web/chains.js) in headless Chromium from the published site, letterboxed
to 1200x630 (the size link cards use), as JPEG. Kept on the "media" branch under og/ with og/index.json:
    {"base": "https://raw.githubusercontent.com/<repo>/media/og", "images": {"c-<cik>": {"file": "c-<cik>.jpg", "v": "..."}}}
The site build reads that manifest (scripts/seo.py, OG_MANIFEST). A picture is redrawn only when its page's figures
change (a new filing, a rebuilt chain); the largest companies first, a few hundred a run.

    python -m pipeline.ogimg --site https://filing-flows.com/ --out media/og --base https://raw.githubusercontent.com/OWNER/REPO/media/og
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.request

TOP_COMPANIES = 800            # companies with their own picture, by revenue
PER_RUN = 300
W, H = 1200, 630

DRAW = """async ([kind, data, W, H]) => {
  await document.fonts.ready;
  let sc;
  if (kind === 'company') sc = Sankey.layout(data, {});
  else sc = FFChains.layout(data.view, data.opts);
  sc = Object.assign({}, sc, { shapes: sc.shapes.filter((s) => !s.ui) });
  const src = Sankey.toCanvas(sc, 2);
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = '#fbfaf7';
  g.fillRect(0, 0, W, H);
  const k = Math.min(W / src.width, H / src.height);
  const w = src.width * k, h = src.height * k;
  g.imageSmoothingQuality = 'high';
  g.drawImage(src, (W - w) / 2, (H - h) / 2, w, h);
  return c.toDataURL('image/jpeg', 0.86).split(',')[1];
}"""


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "filing-flows og images"}), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def ver(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def jobs(site):
    """[(key, version, kind, loader)] for every page that should have a picture, most important first."""
    out = []
    try:
        ix = get_json(site + "data/chains/index.json")
        for ch in ix.get("chains") or []:
            out.append((f"chain-{ch['id']}", ver((ix.get("generated") or "")[:10], ch.get("asof")), "chain", ch["id"]))
    except Exception as e:
        print(f"::warning::chains not listed for pictures: {e}")
    ix = get_json(site + "data/index.json")
    rows = ix["companies"] if isinstance(ix, dict) else ix
    latest = {}
    for r in rows:
        if r["cik"] not in latest or (r.get("filed") or "") > (latest[r["cik"]].get("filed") or ""):
            latest[r["cik"]] = r
    usd = [r for r in latest.values() if (r.get("currency") or "USD") == "USD"]
    for r in sorted(usd, key=lambda r: -(r.get("revenue") or 0))[:TOP_COMPANIES]:
        out.append((f"c-{r['cik']}", ver(r.get("label"), r.get("filed"), r.get("form")), "company", r["cik"]))
    return out


def draw(page, site, kind, ident):
    if kind == "company":
        c = get_json(f"{site}data/c/{ident}.json")
        q = (c.get("quarters") or [None])[0]
        if not q or not q.get("nodes"):
            return None
        data = q
    else:
        d = get_json(f"{site}data/chains/{ident}.json")
        v = (d.get("views") or {}).get("flow")
        if not v:
            return None
        data = {"view": v, "opts": {"title": f"{d['name']} — money flow", "subtitle": (d.get("about") or "")[:150],
                                    "footer": ["Source: SEC EDGAR filings, read by fixed rules. Not investment advice."]}}
    return base64.b64decode(page.evaluate(DRAW, [kind, data, W, H]))


def run(site, out, base, limit=PER_RUN, budget_s=900):
    from playwright.sync_api import sync_playwright
    site = site.rstrip("/") + "/"
    os.makedirs(out, exist_ok=True)
    mpath = os.path.join(out, "index.json")
    try:
        manifest = json.load(open(mpath))
    except (OSError, ValueError):
        manifest = {}
    images = manifest.get("images") or {}
    todo = [j for j in jobs(site) if (images.get(j[0]) or {}).get("v") != j[1]]
    print(f"{len(todo)} pictures to draw")
    t0, done, failed = time.time(), 0, 0
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:
            browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.goto(site + "index.html#method")
        page.wait_for_function("window.Sankey && window.FFChains && document.fonts")
        for key, v, kind, ident in todo[:limit]:
            if time.time() - t0 > budget_s:
                break
            try:
                jpg = draw(page, site, kind, ident)
            except Exception as e:
                failed += 1
                print(f"  {key}: {str(e)[:120]}", file=sys.stderr)
                continue
            if not jpg:
                continue
            with open(os.path.join(out, f"{key}.jpg"), "wb") as f:
                f.write(jpg)
            images[key] = {"file": f"{key}.jpg", "v": v}
            done += 1
        browser.close()
    manifest = {"base": base.rstrip("/"), "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "images": images}
    with open(mpath, "w") as f:
        json.dump(manifest, f, separators=(",", ":"))
    print(f"::notice::share pictures: {done} drawn, {failed} failed, {max(len(todo) - done - failed, 0)} waiting; {len(images)} in all")
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--out", default="media/og")
    ap.add_argument("--base", required=True)
    ap.add_argument("--limit", type=int, default=PER_RUN)
    a = ap.parse_args()
    run(a.site, a.out, a.base, a.limit)
