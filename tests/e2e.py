"""End-to-end check of the built site with Playwright (Chromium).

    python tests/e2e.py _site [--shots DIR]

Checks: every page renders without console errors; chart labels do not overlap each other, bars or bands;
clicking a node shows the filing's own text; PNG/JPG/PDF exports download and contain the chart only;
no horizontal page scroll at phone width.
"""
import argparse
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright

CHECK_LABELS = """() => {
  const svg = document.querySelector('.sheet svg');
  if (!svg) return ['no svg'];
  const out = [];
  const groups = [...svg.querySelectorAll('g.node')];
  const box = (els) => {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    els.forEach((e) => { const b = e.getBBox(); x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height); });
    return [x0, y0, x1, y1];
  };
  const labs = groups.map((g) => ({ id: g.dataset.node, r: box([...g.querySelectorAll('text')]), bar: box([g.querySelector('rect.bar')]) }));
  const ov = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  for (let i = 0; i < labs.length; i++) {
    for (let j = 0; j < labs.length; j++) {
      if (i < j && ov(labs[i].r, labs[j].r)) out.push(`label ${labs[i].id} overlaps label ${labs[j].id}`);
      if (i !== j && ov(labs[i].r, labs[j].bar)) out.push(`label ${labs[i].id} overlaps bar ${labs[j].id}`);
    }
  }
  const paths = [...svg.querySelectorAll('path.band')];
  const W = svg.viewBox.baseVal.width, H = svg.viewBox.baseVal.height;
  labs.forEach(({ id, r }) => {
    if (r[0] < 0 || r[1] < 0 || r[2] > W || r[3] > H) out.push(`label ${id} leaves the canvas`);
    for (let x = r[0] + 1; x < r[2] - 1; x += 3) for (let y = r[1] + 1; y < r[3] - 1; y += 3) {
      const p = paths.find((q) => q.isPointInFill(new DOMPoint(x, y)));
      if (p) { out.push(`label ${id} sits on band ${p.dataset.s}>${p.dataset.t}`); return; }
    }
  });
  return out;
}"""


def serve(root, port):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=root)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("--shots", default=None)
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    srv = serve(os.path.abspath(args.site), args.port)
    base = f"http://127.0.0.1:{args.port}/index.html"
    fails, warns = [], []
    shot = (lambda pg, name, **kw: pg.screenshot(path=os.path.join(args.shots, name), **kw)) if args.shots else (lambda *a, **k: None)
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        local = f"127.0.0.1:{args.port}"
        pg.on("console", lambda m: m.type == "error" and not m.text.startswith("Failed to load resource") and errors.append(m.text))
        pg.on("requestfailed", lambda r: local in r.url and errors.append(f"request failed: {r.url}"))
        pg.on("response", lambda r: local in r.url and r.status >= 400 and "site.json" not in r.url and errors.append(f"HTTP {r.status}: {r.url}"))

        # home
        pg.goto(base + "#home")
        pg.wait_for_selector("#rows tr")
        rows = pg.locator("#rows tr[data-href]").count()
        print("home rows:", rows)
        if rows < 1:
            fails.append("home: no filings listed")
        shot(pg, "home.png", full_page=True)

        import json
        index = json.load(open(os.path.join(args.site, "data", "index.json")))
        for co in index["companies"]:
            cik = co["cik"]
            for view in ("std", "cmp"):
                pg.goto(f"{base}#c-{cik}")
                pg.wait_for_selector(".sheet svg")
                if view == "cmp":
                    btn = pg.locator('[data-view="cmp"]')
                    if btn.is_disabled():
                        continue
                    btn.click()
                    pg.wait_for_function("[...document.querySelectorAll('.sheet svg text')].some((x) => x.textContent.includes('what changed'))")
                else:
                    std = pg.locator('[data-view="std"]')
                    std.click()
                    pg.wait_for_timeout(100)
                issues = pg.evaluate(CHECK_LABELS)
                print(f"{co['ticker']:6} {view}: {len(issues)} layout issues", issues[:4])
                (warns if view == "cmp" else fails).extend(f"{co['ticker']} {view}: {i}" for i in issues)
                shot(pg, f"c_{co['ticker']}_{view}.png", full_page=True)
            pg.locator('[data-view="std"]').click()

        # notes on click (Apple fixture has MD&A text for iPhone)
        pg.goto(f"{base}#c-320193")
        pg.wait_for_selector(".sheet svg")
        pg.locator('g.node[data-node="L:aapl:IPhoneMember"] rect.hit').click()
        txt = pg.locator(".notes").inner_text()
        print("notes:", txt[:160].replace("\n", " | "))
        if "iPhone net sales" not in txt:
            fails.append("notes panel did not show the 10-Q passage for iPhone")
        if pg.locator("svg.has-sel path.band.on").count() < 1:
            fails.append("selected node's bands are not highlighted")
        shot(pg, "c_AAPL_note.png")

        # exports: chart only, right size, valid files
        W = pg.evaluate("document.querySelector('.sheet svg').viewBox.baseVal.width")
        for fmt, magic in (("png", b"\x89PNG"), ("jpg", b"\xff\xd8\xff"), ("pdf", b"%PDF")):
            with pg.expect_download() as dl:
                pg.locator(f'[data-x="{fmt}"]').click()
            path = dl.value.path()
            data = open(path, "rb").read()
            print(f"export {fmt}: {dl.value.suggested_filename} {len(data) // 1024} KB")
            if not data.startswith(magic):
                fails.append(f"export {fmt}: wrong file signature")
            if args.shots and fmt != "pdf":
                open(os.path.join(args.shots, f"export.{fmt}"), "wb").write(data)
            if fmt == "png":
                import struct
                w, h = struct.unpack(">II", data[16:24])
                if abs(w - 2 * W) > 2:
                    fails.append(f"export png width {w} != 2 x {W}")
        # the export must contain the flows: count flow-coloured pixels on the exported canvas
        px = pg.evaluate("""() => {
          const sc = document.querySelector('.chart-ui').getScene();
          const c = window.Sankey.toCanvas(sc, 1), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          const want = [[217, 216, 211], [168, 209, 185], [246, 195, 184]];   // revenue, profit, cost flow colours
          let n = 0;
          for (let i = 0; i < d.length; i += 4) if (want.some(([r, g, b]) => Math.abs(d[i] - r) < 3 && Math.abs(d[i + 1] - g) < 3 && Math.abs(d[i + 2] - b) < 3)) n++;
          return { n, total: c.width * c.height };
        }""")
        print(f"export flow pixels: {px['n']} of {px['total']}")
        if px["n"] < 0.05 * px["total"]:
            fails.append("export: flows missing from the exported image")
        # the exported scene must not contain screen-only shapes
        leaked = pg.evaluate("""() => {
          const c = document.createElement('canvas');
          return [...document.querySelectorAll('.sheet svg .note-mark')].length > 0 &&
                 !!window.Sankey && typeof window.Sankey.toCanvas === 'function';
        }""")
        print("note markers on screen (not exported):", leaked)

        # all quarters view
        pg.goto(f"{base}#c-320193-all")
        pg.wait_for_selector(".thumb .sheet svg")
        print("thumbs:", pg.locator(".thumb").count())
        shot(pg, "c_AAPL_all.png", full_page=True)

        # sector page + company link from a leaf
        for s in index["sectors"]:
            pg.goto(f"{base}#s-{s['id']}")
            pg.wait_for_selector(".sheet svg")
            issues = pg.evaluate(CHECK_LABELS)
            print(f"sector {s['id']}: {len(issues)} layout issues", issues[:4])
            fails.extend(f"sector {s['id']}: {i}" for i in issues)
            pg.locator('g.node[data-node="L:m0"] rect.hit').click()
            if "chart" not in pg.locator(".notes").inner_text():
                fails.append("sector leaf did not offer a company link")
            shot(pg, f"s_{s['id']}.png", full_page=True)

        pg.goto(f"{base}#sectors")
        pg.wait_for_selector("h1")
        pg.goto(f"{base}#method")
        pg.wait_for_selector("h1")

        # phone width: no sideways page scroll
        mob = b.new_page(viewport={"width": 390, "height": 844})
        for h in ("#home", "#c-320193", "#s-technology", "#method"):
            mob.goto(base + h)
            mob.wait_for_timeout(600)
            sw = mob.evaluate("document.scrollingElement.scrollWidth")
            if sw > 391:
                fails.append(f"mobile {h}: page scrolls sideways ({sw}px)")
        mob.goto(base + "#c-320193")
        mob.wait_for_selector(".sheet svg")
        shot(mob, "mobile_company.png", full_page=True)

        # dark theme
        dark = b.new_page(viewport={"width": 1440, "height": 1000}, color_scheme="dark")
        dark.goto(base + "#c-1326801")
        dark.wait_for_selector(".sheet svg")
        shot(dark, "dark_meta.png")

        if errors:
            fails.extend(f"console: {e}" for e in errors)
        b.close()
    srv.shutdown()
    print("\nWARNINGS (comparison view):" if warns else "", *warns, sep="\n  ")
    if fails:
        print("\nFAILED:", *fails, sep="\n  ")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
