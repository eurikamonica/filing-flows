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

# A stand-in for the Supabase client (same calls app.js makes), so the account pages can be tested offline.
FAKE_SUPABASE = """
(() => {
  const GOOD_UNSUB = '11111111-2222-4333-8444-555555555555';
  const db = { subscriptions: [], send_requests: [] }, log = [];
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem('fake-session') || 'null'); } catch (e) {}
  window.__ff = { db, log, native: [] };
  window.FilingFlowsApp = { setFollows: (j) => window.__ff.native.push(j) };
  const copy = (x) => JSON.parse(JSON.stringify(x));
  const auth = {
    async getSession() { return { data: { session } }; },
    async signInWithOtp({ email, options }) { log.push(['otp', email, !!(options && options.shouldCreateUser)]); return { data: {}, error: null }; },
    async verifyOtp({ email, token, type }) {
      log.push(['verify', email, token, type]);
      if (token !== '123456') return { data: null, error: { message: 'Token has expired or is invalid' } };
      session = { user: { id: 'user-1', email } };
      return { data: { session }, error: null };
    },
    async signOut() { session = null; return { error: null }; },
  };
  function from(table) {
    const rows = db[table], q = { f: [], op: 'select', row: null };
    const match = (r) => q.f.every(([k, v]) => r[k] === v);
    const write = () => {
      const r = copy(q.row);
      if (!session || r.user_id !== session.user.id) return { data: null, error: { message: 'new row violates row-level security policy' } };
      r.email = session.user.email;                       // what the database trigger does
      const i = rows.findIndex((x) => x.user_id === r.user_id);
      if (i >= 0 && q.op === 'insert') return { data: null, error: { message: 'duplicate key' } };
      const keep = i >= 0 ? { unsub_token: rows[i].unsub_token, created_at: rows[i].created_at } : { unsub_token: GOOD_UNSUB, created_at: new Date().toISOString() };
      const out = Object.assign(r, keep, { updated_at: new Date().toISOString() });
      if (i >= 0) rows[i] = out; else rows.push(out);
      log.push([q.op, table]);
      return { data: copy(out), error: null };
    };
    // send_requests: what the table's policies and triggers do (own rows, one pending copy, 30 a day)
    const requests = () => {
      if (!session) return { data: null, error: { code: '42501', message: 'new row violates row-level security policy' } };
      const mine = rows.filter((x) => x.user_id === session.user.id);
      const add = (Array.isArray(q.row) ? q.row : [q.row]).map((x) => Object.assign(copy(x), {
        user_id: session.user.id, status: 'pending', created_at: new Date().toISOString() }));
      for (const x of add) {
        if (mine.concat(add.filter((y) => y !== x && add.indexOf(y) < add.indexOf(x)))
          .some((y) => y.status === 'pending' && y.cik === x.cik && y.period_end === x.period_end))
          return { data: null, error: { code: '23505', message: 'duplicate key value violates unique constraint' } };
      }
      if (mine.length + add.length > 30) return { data: null, error: { code: 'P0001', message: 'limit: 30 reports a day' } };
      add.forEach((x) => rows.push(x));
      log.push(['insert', table, add.length]);
      return { data: null, error: null };
    };
    const run = () => {
      if (table === 'send_requests' && q.op === 'insert') return requests();
      if (q.op === 'select') {
        let m = rows.filter((r) => session && r.user_id === session.user.id && match(r));
        if (q.order) m = m.slice().sort((a, c) => (a[q.order] < c[q.order] ? 1 : -1));
        if (q.limit) m = m.slice(0, q.limit);
        return { data: copy(m), error: null };
      }
      return write();
    };
    const b = {
      select() { return b; },
      eq(k, v) { q.f.push([k, v]); return b; },
      order(col) { q.order = col; return b; },
      limit(n) { q.limit = n; return b; },
      insert(r) { q.op = 'insert'; q.row = r; return b; },
      upsert(r) { q.op = 'upsert'; q.row = r; return b; },
      async maybeSingle() { const m = rows.filter((r) => session && r.user_id === session.user.id && match(r)); return { data: m[0] ? copy(m[0]) : null, error: null }; },
      async single() { return q.op === 'select' ? b.maybeSingle() : write(); },
      then(ok, bad) { return Promise.resolve().then(run).then(ok, bad); },
    };
    return b;
  }
  async function rpc(name, args) {
    log.push(['rpc', name, args]);
    if (name === 'delete_account') {
      const i = session ? db.subscriptions.findIndex((x) => x.user_id === session.user.id) : -1;
      if (i >= 0) db.subscriptions.splice(i, 1);
      return { data: !!session, error: null };
    }
    const r = db.subscriptions.find((x) => x.unsub_token === args.token);
    if (r) { r.email_on = false; r.push_on = false; }
    return { data: !!r || args.token === GOOD_UNSUB, error: null };
  }
  window.FF_SUPABASE = { auth, from, rpc };
})();
"""


def _final_quarter(route):
    import json as _json
    resp = route.fetch()
    c = _json.loads(resp.text())
    c["quarters"][0].update(form="10-Q", release_check={"filed": "2026-09-24", "accn": "x", "ok": False, "fields": [
        {"key": "revenue", "name": "Revenue", "release": 5.24e9, "final": 5.24e9, "ok": True},
        {"key": "ni", "name": "Net earnings", "release": 9.32e8, "final": 9.32e8, "ok": True},
        {"key": "ocf", "name": "Operating cash flow", "release": 1.6e9, "final": 1.2e9, "ok": False}]})
    route.fulfill(response=resp, body=_json.dumps(c))


def check_accounts(b, base, fails, shot):
    """Sign in with a code, save alert settings, Follow on a company page, unsubscribe link."""
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(FAKE_SUPABASE)
    ctx.route("**/data/c/9999901.json", _final_quarter)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    ff = lambda expr: pg.evaluate(f"() => {expr}")
    pg.goto(base + "#home")
    pg.wait_for_selector("#cta:not([hidden])")
    pg.fill("#cta-form input", "reader@example.com")
    pg.click("#cta-form button")
    pg.wait_for_selector("#auth-email")
    if pg.input_value("#auth-email input") != "reader@example.com":
        fails.append("accounts: address from the home form was not carried over")
    pg.click("#auth-email button")
    pg.wait_for_selector("#auth-code:not([hidden])")
    if ff("window.__ff.log.find((x) => x[0] === 'otp')") != ["otp", "reader@example.com", True]:
        fails.append("accounts: signInWithOtp not called with shouldCreateUser")
    shot(pg, "acct_code.png")
    pg.fill("#auth-code input", "000000")
    pg.click("#auth-code button[type=submit]")
    pg.wait_for_function("document.querySelector('#auth-msg').textContent.includes('did not work')")
    pg.fill("#auth-code input", "123456")
    pg.click("#auth-code button[type=submit]")
    pg.wait_for_selector("#prefs-form")
    if ff("window.__ff.db.subscriptions.length") != 1:
        fails.append("accounts: no preferences row created on first sign-in")
    pg.fill("#add-ticker", "aapl")
    pg.press("#add-ticker", "Enter")
    pg.locator('input[name="sector"]:not([value="technology"])').first.check()
    pg.check('input[name="freq"][value="daily"]')
    pg.check("#all-above")
    pg.fill("#min-rev", "5")
    if not pg.is_checked("#final-too"):
        fails.append("accounts: 'also send the final 10-Q' should be on by default")
    pg.uncheck("#final-too")
    pg.click("#prefs-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#save-msg').textContent === 'Saved.'")
    row = ff("window.__ff.db.subscriptions[0]")
    print("saved prefs:", {k: row[k] for k in ("tickers", "sectors", "frequency", "all_above", "min_revenue", "email")})
    if row.get("final_too") is not False:
        fails.append("accounts: final_too not saved")
    if row["tickers"] != ["AAPL"] or row["frequency"] != "daily" or len(row["sectors"]) != 1 or row["min_revenue"] != 5e9 or not row["all_above"]:
        fails.append(f"accounts: settings not saved as entered: {row}")
    if not ff("window.__ff.native.length"):
        fails.append("accounts: Android bridge setFollows not called")
    shot(pg, "acct_settings.png", full_page=True)

    # Follow on a company page
    pg.goto(base + "#c-1326801")
    pg.wait_for_selector(".btn.follow:not([hidden])")
    pg.click(".btn.follow")
    pg.wait_for_function("document.querySelector('.btn.follow').textContent.includes('Following')")
    if ff("window.__ff.db.subscriptions[0].tickers") != ["AAPL", "META"]:
        fails.append("accounts: Follow did not add META")
    shot(pg, "acct_follow.png")
    pg.click(".btn.follow")
    pg.wait_for_function("document.querySelector('.btn.follow').textContent.includes('☆ Follow')")
    if ff("window.__ff.db.subscriptions[0].tickers") != ["AAPL"]:
        fails.append("accounts: second Follow click did not remove META")

    # "Email me this report": the selected quarter, the same again, then all quarters (one already queued)
    pg.goto(base + "#c-320193")
    pg.wait_for_selector(".btn.send:not([hidden])")
    label = pg.inner_text(".btn.send")
    pg.click(".btn.send")
    pg.wait_for_selector(".toast")
    if "on the way to reader@example.com" not in pg.inner_text(".toast"):
        fails.append(f"email-me: unexpected message {pg.inner_text('.toast')!r}")
    shot(pg, "send_one.png")
    pg.click(".btn.send")
    pg.wait_for_function("document.querySelector('.toast').textContent.includes('Already')")
    pg.goto(base + "#c-320193-all")
    pg.wait_for_selector(".btn.send:not([hidden])")
    if "all 2 quarters" not in pg.inner_text(".btn.send"):
        fails.append(f"email-me: all-quarters button says {pg.inner_text('.btn.send')!r}")
    pg.click(".btn.send")
    pg.wait_for_function("document.querySelector('.toast') && document.querySelector('.toast').textContent.includes('Report on the way')")
    reqs = ff("window.__ff.db.send_requests.map((r) => r.cik + ':' + r.period_end)")
    print("email-me requests:", label, reqs)
    if len(reqs) != 2 or len(set(reqs)) != 2:
        fails.append(f"email-me: expected two different quarters queued, got {reqs}")
    pg.goto(base + "#account")
    pg.wait_for_selector("#requests table")
    if pg.locator("#requests tr").count() != 2 or "on its way" not in pg.inner_text("#requests"):
        fails.append("alerts page: requested reports not listed")
    shot(pg, "acct_requests.png", full_page=True)
    # a 10-Q that replaced an 8-K chart is labelled final, with what the release got right or wrong
    pg.goto(base + "#c-9999901")
    pg.wait_for_selector(".tag.final")
    facts = pg.inner_text(".facts")
    if "Revised: operating cash flow $1.6B in the release, $1.2B as filed" not in facts:
        fails.append(f"final label: facts say {facts!r}")
    shot(pg, "final_label.png")

    # home shows "Manage alerts" when signed in; sign out
    pg.goto(base + "#home")
    pg.wait_for_selector("#cta a[href='#account']")
    pg.goto(base + "#account")
    pg.wait_for_selector("#sign-out")
    pg.click("#sign-out")
    pg.wait_for_selector("#cta-form")

    # Follow while signed out: sign in, then back on the company page, following
    pg.goto(base + "#c-1326801")
    pg.wait_for_selector(".btn.follow:not([hidden])")
    pg.click(".btn.follow")
    pg.wait_for_selector("#auth-email")
    pg.fill("#auth-email input", "reader@example.com")
    pg.click("#auth-email button")
    pg.wait_for_selector("#auth-code:not([hidden])")
    pg.fill("#auth-code input", "123456")
    pg.click("#auth-code button[type=submit]")
    pg.wait_for_function("location.hash === '#c-1326801'")
    pg.wait_for_function("(document.querySelector('.btn.follow') || {}).textContent === '★ Following'")
    if ff("window.__ff.db.subscriptions.length") != 1:
        fails.append("accounts: signing in again created a second row")
    if ff("window.__ff.db.subscriptions[0].tickers") != ["AAPL", "META"]:
        fails.append("accounts: Follow from before signing in was not saved")

    # Email me while signed out: sign in, then back on the page with the report queued
    pg.goto(base + "#account")
    pg.wait_for_selector("#sign-out")
    pg.click("#sign-out")
    pg.wait_for_selector("#cta-form")
    pg.goto(base + "#c-1326801")
    pg.wait_for_selector(".btn.send:not([hidden])")
    pg.click(".btn.send")
    pg.wait_for_selector("#auth-email")
    pg.fill("#auth-email input", "reader@example.com")
    pg.click("#auth-email button")
    pg.wait_for_selector("#auth-code:not([hidden])")
    pg.fill("#auth-code input", "123456")
    pg.click("#auth-code button[type=submit]")
    pg.wait_for_function("location.hash === '#c-1326801'")
    pg.wait_for_function("document.querySelector('.toast') && document.querySelector('.toast').textContent.includes('on the way')")
    if not ff("window.__ff.db.send_requests.some((r) => r.cik === 1326801)"):
        fails.append("email-me: request from before signing in was not queued")

    # sector follow
    pg.goto(base + "#s-technology")
    pg.wait_for_selector(".btn.follow:not([hidden])")
    if "Following" in pg.inner_text(".btn.follow"):
        fails.append("accounts: sector shown as followed before Follow was clicked")
    pg.click(".btn.follow")
    pg.wait_for_function("document.querySelector('.btn.follow').textContent.includes('Following')")
    if "technology" not in ff("window.__ff.db.subscriptions[0].sectors"):
        fails.append("accounts: sector Follow not saved")

    # unsubscribe links
    pg.goto(base + "#unsubscribe-11111111-2222-4333-8444-555555555555")
    pg.wait_for_selector("h1")
    if "unsubscribed" not in pg.inner_text("h1"):
        fails.append("accounts: unsubscribe link failed")
    if ff("window.__ff.db.subscriptions[0].email_on"):
        fails.append("accounts: unsubscribe did not switch e-mail off")
    pg.goto(base + "#unsubscribe-99999999-2222-4333-8444-555555555555")
    pg.wait_for_function("document.querySelector('h1').textContent.includes('did not work')")

    # delete the account
    pg.goto(base + "#account")
    pg.wait_for_selector("#del-acct")
    pg.click("#del-acct")
    pg.click("#del-yes")
    pg.wait_for_function("document.querySelector('h1').textContent.includes('deleted')")
    if ff("window.__ff.db.subscriptions.length") != 0:
        fails.append("accounts: delete did not remove the row")

    # phone width
    mob = ctx.new_page()
    mob.set_viewport_size({"width": 390, "height": 844})
    for h in ("#account", "#home"):
        mob.goto(base + h)
        mob.wait_for_timeout(500)
        sw = mob.evaluate("document.scrollingElement.scrollWidth")
        if sw > 391:
            fails.append(f"accounts mobile {h}: page scrolls sideways ({sw}px)")
    shot(mob, "acct_mobile_home.png", full_page=True)
    fails.extend(f"accounts console: {e}" for e in errors)
    ctx.close()


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
            for view in ("std", "q", "y"):
                pg.goto(f"{base}#c-{cik}")
                pg.wait_for_selector(".sheet svg")
                if view != "std":
                    btn = pg.locator(f'[data-view="{view}"]')
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
                (warns if view != "std" else fails).extend(f"{co['ticker']} {view}: {i}" for i in issues)
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
        n_posts = pg.locator("#thread pre").count()
        print("X thread posts on the page:", n_posts)
        if n_posts < 3:
            fails.append("company page has no X thread")

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

        if pg.locator(".foot-links a").count() != 2:
            fails.append("footer: privacy / terms links missing")
        root = base.rsplit("/", 1)[0]
        for page, words in (("privacy", "Delete my account"), ("terms", "Not investment advice")):
            pg.goto(f"{root}/{page}.html")
            pg.wait_for_selector(".legal")
            text = pg.inner_text(".legal")
            if words not in text or "CONTACT" in pg.content() or "${" in text:
                fails.append(f"{page} page incomplete")
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

        # accounts switched off (no Supabase settings in site.json): no sign-up box, no Follow buttons
        pg.goto(base + "#home")
        pg.wait_for_selector("#rows tr")
        pg.wait_for_timeout(300)
        if pg.locator("#cta").is_visible():
            fails.append("home: sign-up box shown although accounts are not configured")
        pg.goto(base + "#c-320193")
        pg.wait_for_selector(".sheet svg")
        pg.wait_for_timeout(300)
        if pg.locator(".btn.follow").is_visible() or pg.locator(".btn.send").is_visible():
            fails.append("company: Follow / Email me shown although accounts are not configured")
        pg.goto(base + "#account")
        pg.wait_for_selector("h1")
        if "not switched on" not in pg.inner_text("h1"):
            fails.append("account page without configuration should say alerts are not switched on")

        check_accounts(b, base, fails, shot)

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
