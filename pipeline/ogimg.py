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
import re
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
            out.append((f"chain-{ch['id']}", ver((ix.get("generated") or "")[:10], ch.get("asof")), "chain", ch["id"],
                        f"{ch['id']}-money-flow-sankey", f"{ch.get('name') or ch['id']}: money flow Sankey"))
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
        out.append((f"c-{r['cik']}", ver(r.get("label"), r.get("filed"), r.get("form")), "company", r["cik"], fname(r),
                    f"{r.get('name')} ({r.get('ticker')}) {r.get('label')} revenue breakdown: earnings and cash flow Sankey"))
    return out


def fname(r):
    """a file name that says what the picture is, for image search: nvda-revenue-breakdown-sankey (the page's slug)"""
    s = (r.get("ticker") or "").lower().replace(".", "-")
    s = s if re.fullmatch(r"[a-z0-9-]{1,12}", s) else f"cik-{r['cik']}"
    return f"{s}-revenue-breakdown-sankey"


XMP_TAG = b"http://ns.adobe.com/xap/1.0/\x00"


def with_xmp(jpg, title, site):
    """The picture's own credit and terms (IPTC photo metadata as XMP), read by Google Images for the credit line and
    the "Licensable" badge: creator, credit, copyright notice, web statement of rights and the licensor's page.
    An earlier XMP segment is replaced; anything that is not a JPEG comes back unchanged."""
    if not jpg.startswith(b"\xff\xd8"):
        return jpg
    from xml.sax.saxutils import escape
    lic = site.rstrip("/") + "/license/"
    t = escape(title or "Filing Flows chart")
    xmp = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" '
           'xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/" xmlns:plus="http://ns.useplus.org/ldf/xmp/1.0/">'
           f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{t}</rdf:li></rdf:Alt></dc:title>'
           f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{t}. Figures read from SEC filings by Filing Flows.</rdf:li></rdf:Alt></dc:description>'
           '<dc:creator><rdf:Seq><rdf:li>Filing Flows</rdf:li></rdf:Seq></dc:creator>'
           '<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">© Filing Flows (filing-flows.com). Free to use with credit and a link.</rdf:li></rdf:Alt></dc:rights>'
           '<photoshop:Credit>Filing Flows (filing-flows.com)</photoshop:Credit>'
           f'<xmpRights:WebStatement>{lic}</xmpRights:WebStatement><xmpRights:Marked>True</xmpRights:Marked>'
           f'<plus:Licensor><rdf:Seq><rdf:li rdf:parseType="Resource"><plus:LicensorName>Filing Flows</plus:LicensorName><plus:LicensorURL>{lic}</plus:LicensorURL></rdf:li></rdf:Seq></plus:Licensor>'
           '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode("utf-8")
    seg = b"\xff\xe1" + (len(XMP_TAG) + len(xmp) + 2).to_bytes(2, "big") + XMP_TAG + xmp
    # walk the segments after SOI: drop an old XMP, put ours after the APP0/APP1 headers
    i, out, placed = 2, [jpg[:2]], False
    while i + 4 <= len(jpg) and jpg[i] == 0xFF and jpg[i + 1] not in (0xDA, 0xD9):
        mk, ln = jpg[i + 1], int.from_bytes(jpg[i + 2:i + 4], "big")
        part = jpg[i:i + 2 + ln]
        if mk == 0xE1 and part[4:4 + len(XMP_TAG)] == XMP_TAG:
            i += 2 + ln
            continue
        if not placed and mk not in (0xE0, 0xE1):
            out.append(seg)
            placed = True
        out.append(part)
        i += 2 + ln
    if not placed:
        out.append(seg)
    out.append(jpg[i:])
    return b"".join(out)


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
    all_jobs = jobs(site)
    for key, v, kind, ident, name, title in all_jobs:       # a picture drawn under an older name: renamed, not redrawn
        old = images.get(key) or {}
        want = f"{name}.jpg"
        if old.get("file") and old["file"] != want and os.path.exists(os.path.join(out, old["file"])):
            os.replace(os.path.join(out, old["file"]), os.path.join(out, want))
            images[key] = dict(old, file=want)
    for key, v, kind, ident, name, title in all_jobs:       # pictures drawn before they carried their credit and terms
        img = images.get(key) or {}
        f = os.path.join(out, img.get("file") or "")
        if img.get("file") and not img.get("xmp") and os.path.exists(f):
            with open(f, "rb") as fh:
                b = fh.read()
            with open(f, "wb") as fh:
                fh.write(with_xmp(b, title, site))
            images[key] = dict(img, xmp=1)
    todo = [j for j in all_jobs if (images.get(j[0]) or {}).get("v") != j[1]]
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
        for key, v, kind, ident, name, title in todo[:limit]:
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
            with open(os.path.join(out, f"{name}.jpg"), "wb") as f:
                f.write(with_xmp(jpg, title, site))
            old = (images.get(key) or {}).get("file")
            if old and old != f"{name}.jpg" and os.path.exists(os.path.join(out, old)):
                os.remove(os.path.join(out, old))
            images[key] = {"file": f"{name}.jpg", "v": v, "xmp": 1}
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
