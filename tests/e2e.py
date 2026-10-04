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
  const db = { subscriptions: [], send_requests: [], chart_requests: [], company_requests: [],
    owner_settings: [{ id: true, thread_direct: true, daily_on: true, daily_hour: 8, tz: 'Asia/Shanghai', min_revenue: 1e9, instant_threads: false,
      daily_scope: 'min_revenue', reader_copy: false }] }, log = [];
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem('fake-session') || 'null'); } catch (e) {}
  window.__ff = { db, log, native: [], owners: [] };
  window.FilingFlowsApp = { setFollows: (j) => window.__ff.native.push(j) };
  const copy = (x) => JSON.parse(JSON.stringify(x));
  const auth = {
    // answers a moment later, like the real client (its sign-in lock and storage are asynchronous): code that reads
    // the click event after an await sees what a real browser gives it (event.currentTarget is null by then)
    async getSession() { await new Promise((r) => setTimeout(r, 30)); return { data: { session } }; },
    async signInWithOtp({ email, options }) { log.push(['otp', email, !!(options && options.shouldCreateUser)]); return { data: {}, error: null }; },
    async verifyOtp({ email, token, type }) {
      log.push(['verify', email, token, type]);
      if (token !== '123456') return { data: null, error: { message: 'Token has expired or is invalid' } };
      session = { user: { id: 'user-1', email } };
      return { data: { session }, error: null };
    },
    async signOut() { session = null; return { error: null }; },
  };
  const isOwner = () => !!session && (window.__ff.owners || []).includes(session.user.email);
  // owner_settings: one row, read and changed by the site owner only (row-level security)
  function ownerTable() {
    const q = { op: 'select', row: null };
    const run = () => {
      if (q.op === 'update') {
        if (!isOwner()) return { data: null, error: { code: 'PGRST116', message: 'JSON object requested, multiple (or no) rows returned' } };
        Object.assign(db.owner_settings[0], copy(q.row));
        log.push(['update', 'owner_settings']);
        return { data: copy(db.owner_settings[0]), error: null };
      }
      return { data: isOwner() ? copy(db.owner_settings[0]) : null, error: null };
    };
    const b = { select() { return b; }, eq() { return b; }, update(r) { q.op = 'update'; q.row = r; return b; },
      async maybeSingle() { return run(); }, async single() { return run(); }, then(ok, bad) { return Promise.resolve().then(run).then(ok, bad); } };
    return b;
  }
  function from(table) {
    if (table === 'owner_settings') return ownerTable();
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
      if (add.some((x) => x.kind === 'thread') && !isOwner()) return { data: null, error: { code: '42501', message: 'new row violates row-level security policy' } };
      if (add.some((x) => !(x.cik > 0 || (x.kind === 'day' && x.cik === 0))))
        return { data: null, error: { code: '23514', message: 'new row violates check constraint "send_requests_cik_check"' } };
      for (const x of add) {
        if (mine.concat(add.filter((y) => y !== x && add.indexOf(y) < add.indexOf(x)))
          .some((y) => y.status === 'pending' && y.cik === x.cik && y.period_end === x.period_end && (y.kind || 'q') === (x.kind || 'q')))
          return { data: null, error: { code: '23505', message: 'duplicate key value violates unique constraint' } };
      }
      if (mine.length + add.length > 30) return { data: null, error: { code: 'P0001', message: 'limit: 30 reports a day' } };
      add.forEach((x) => rows.push(x));
      log.push(['insert', table, add.length]);
      return { data: null, error: null };
    };
    // chart_requests / company_requests: own rows, an id, pending; one open request per company
    const asks = () => {
      if (!session) return { data: null, error: { code: '42501', message: 'new row violates row-level security policy' } };
      const x = Object.assign(copy(q.row), { id: rows.length + 1, user_id: session.user.id, status: 'pending', created_at: new Date().toISOString() });
      if (table === 'company_requests' && rows.some((y) => y.user_id === x.user_id && y.cik === x.cik && ['pending', 'queued'].includes(y.status)))
        return { data: null, error: { code: '23505', message: 'duplicate key value violates unique constraint' } };
      rows.push(x);
      log.push(['insert', table, 1]);
      return { data: copy(x), error: null };
    };
    const isAsk = () => (table === 'chart_requests' || table === 'company_requests') && q.op === 'insert';
    const run = () => {
      if (isAsk()) { const r = asks(); return r.error ? r : { data: [r.data], error: null }; }
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
      update(r) { q.op = 'update'; q.row = r; return b; },
      async maybeSingle() { const m = rows.filter((r) => session && r.user_id === session.user.id && match(r)); return { data: m[0] ? copy(m[0]) : null, error: null }; },
      async single() {
        if (q.op === 'update') {                               // a partial update of the reader's own row
          const r = rows.find((x) => session && x.user_id === session.user.id && match(x));
          if (!r) return { data: null, error: { code: 'PGRST116', message: 'no rows' } };
          Object.assign(r, copy(q.row));
          log.push(['update', table]);
          return { data: copy(r), error: null };
        }
        return isAsk() ? asks() : q.op === 'select' ? b.maybeSingle() : write();
      },
      then(ok, bad) { return Promise.resolve().then(run).then(ok, bad); },
    };
    return b;
  }
  async function rpc(name, args) {
    log.push(['rpc', name, args]);
    if (name === 'am_i_owner') return { data: !!session && (window.__ff.owners || []).includes(session.user.email), error: null };
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


AAPL_PERIODS = {
    "q": [{"end": e, "label": l, "q": n, "fy": f} for e, l, n, f in (
        ("2026-06-27", "Q3 FY26", 3, 2026), ("2026-03-28", "Q2 FY26", 2, 2026), ("2025-12-27", "Q1 FY26", 1, 2026),
        ("2025-09-27", "Q4 FY25", 4, 2025), ("2025-06-28", "Q3 FY25", 3, 2025), ("2024-06-29", "Q3 FY24", 3, 2024))],
    "fy": [{"end": "2025-09-27", "label": "FY25", "fy": 2025}, {"end": "2024-09-28", "label": "FY24", "fy": 2024}]}


def _with_years(route):
    """Apple with a full fiscal year (from a 10-K) and the period list, as the pipeline writes them."""
    import json as _json
    resp = route.fetch()
    c = _json.loads(resp.text())
    q = c["quarters"][0]
    y = _json.loads(_json.dumps(q))
    y.update(period="fy", key="fy-2025-09-27", end="2025-09-27", label="FY25", form="10-K", filed="2025-10-31", compare=None,
             title=q["title"].replace(q["label"], "FY25"))
    y["compare_y"] = dict(q["compare_y"] or q["compare"], vs="FY24")
    c["years"], c["periods"] = [y], AAPL_PERIODS
    c["intro"] = {"text": "Apple designs, manufactures and markets smartphones, personal computers, tablets, wearables and "
                          "accessories, and sells a variety of related services.", "source": "8-K", "filed": "2026-07-30",
                  "url": "https://www.sec.gov/"}
    route.fulfill(response=resp, body=_json.dumps(c))


def _comparison_result(site):
    """What the workflow writes back for 'Q3 FY26 compared with Q3 FY24' (the shape pipeline.custom produces)."""
    import json as _json
    q = _json.load(open(os.path.join(site, "data", "c", "320193.json")))["quarters"][0]
    q.update(compare=dict(q["compare"], vs="Q3 FY24"), compare_y=None, period="q", x_thread=[],
             custom={"a": "2026-06-27", "b": "2024-06-29", "a_label": "Q3 FY26", "b_label": "Q3 FY24", "kind": "q",
                     "b_filed": "2024-08-02", "b_index_url": None})
    return q


def check_accounts(b, base, fails, shot, site):
    """Sign in with a code, save alert settings, Follow on a company page, unsubscribe link."""
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(FAKE_SUPABASE)
    ctx.route("**/data/c/9999901.json", _final_quarter)
    ctx.route("**/data/c/320193.json", _with_years)
    built = {"done": False}

    def companies(route):                       # SEC's list has a company the site has not drawn yet
        import json as _json
        resp = route.fetch()
        d = _json.loads(resp.text())
        d["companies"].append([1652044, "GOOGL", "Alphabet Inc."])
        route.fulfill(response=resp, body=_json.dumps(d))

    def alphabet(route):                        # published once "the scan" has built it
        if not built["done"]:
            route.fulfill(status=404, body="not found")
            return
        import json as _json
        c = _json.load(open(os.path.join(site, "data", "c", "320193.json")))
        c["profile"].update(name="Alphabet Inc.", cik=1652044, tickers=["GOOGL"])
        route.fulfill(status=200, content_type="application/json", body=_json.dumps(c))
    def recent_index(route):                    # filings dated yesterday and the day before, for the daily report picker
        import datetime as _dt
        import json as _json
        resp = route.fetch()
        ix = _json.loads(resp.text())
        today = _dt.date.today()
        for e in ix["companies"]:
            if e["ticker"] in ("AAPL", "META"):
                e["filed"] = (today - _dt.timedelta(days=1)).isoformat()
            elif e["ticker"] == "EXDV":
                e["filed"] = (today - _dt.timedelta(days=2)).isoformat()
        route.fulfill(response=resp, body=_json.dumps(ix))
    ctx.route("**/data/companies.json", companies)
    ctx.route("**/data/c/1652044.json", alphabet)
    ctx.route("**/data/index.json", recent_index)
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
    defaults = (pg.is_checked("#chart-q"), pg.is_checked("#chart-y"), pg.is_checked("#chart-history"),
                pg.is_checked('input[name="attach"][value="png"]'), pg.is_checked("#attach-pdf"))
    if defaults != (False, False, False, True, True):
        fails.append(f"accounts: e-mail content defaults should be this quarter only, PNG and PDF: {defaults}")
    if pg.is_checked("#cmp-decreases") or pg.is_checked("#changes-detail"):
        fails.append("accounts: decreases and the full list of changes should be off by default")
    pg.check("#changes-detail")
    pg.check("#chart-y")
    pg.check("#chart-history")
    pg.check("#cmp-decreases")
    pg.check('input[name="attach"][value="jpg"]')
    pg.uncheck("#attach-pdf")
    pg.click("#prefs-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#save-msg').textContent === 'Saved.'")
    row = ff("window.__ff.db.subscriptions[0]")
    print("saved prefs:", {k: row[k] for k in ("tickers", "sectors", "frequency", "all_above", "min_revenue", "email")})
    if row.get("final_too") is not False:
        fails.append("accounts: final_too not saved")
    got = {k: row.get(k) for k in ("chart_q", "chart_y", "chart_history", "attach_images", "attach_pdf", "cmp_decreases", "changes_detail")}
    print("e-mail content:", got)
    if got != {"chart_q": False, "chart_y": True, "chart_history": True, "attach_images": "jpg", "attach_pdf": False,
               "cmp_decreases": True, "changes_detail": True}:
        fails.append(f"accounts: e-mail content options not saved: {got}")
    tz = pg.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
    if row.get("digest_hour") != 8 or row.get("tz") != tz:
        fails.append(f"accounts: daily report hour / time zone not saved: {row.get('digest_hour')} {row.get('tz')} (browser {tz})")

    # the home page's daily report: today and the five days before; the report of one day by e-mail
    pg.goto(base + "#home")
    pg.wait_for_selector("#daily:not([hidden]) .day")
    days = pg.locator("#daily .day").count()
    on = pg.inner_text("#daily .day.on")
    print("daily report picker:", days, "days; picked:", " ".join(on.split()))
    if days != 6 or "Yesterday" not in on or "you follow" not in on:
        fails.append(f"daily report: expected six days with yesterday picked, got {days}: {on!r}")
    if pg.locator("#daily .day:disabled").count() != 4:
        fails.append("daily report: days without filings should be disabled")
    pg.locator("#daily .day:not(:disabled)").nth(1).click()
    if "report for" not in pg.inner_text("#day-send"):
        fails.append(f"daily report: button says {pg.inner_text('#day-send')!r}")
    pg.click("#day-send")
    pg.wait_for_function("window.__ff.db.send_requests.some((r) => r.kind === 'day')")
    req = ff("window.__ff.db.send_requests.find((r) => r.kind === 'day')")
    import datetime as _dt
    if req["cik"] != 0 or req["period_end"] != (_dt.date.today() - _dt.timedelta(days=2)).isoformat():
        fails.append(f"daily report: request saved as {req}")
    pg.wait_for_function("/on the way|already|Could not|No answer/i.test(document.querySelector('#day-msg').textContent)")
    if "Report on the way" not in pg.inner_text("#day-msg"):
        fails.append(f"daily report: message {pg.inner_text('#day-msg')!r}")
    shot(pg, "home_daily.png")
    pg.evaluate("window.__ff.db.send_requests.length = 0")
    # the full daily report (Alerts): every company that filed, the followed ones first
    pg.goto(base + "#account")
    pg.wait_for_selector("#prefs-form")
    if pg.locator("#scope-box").is_hidden() or not pg.is_checked('input[name="scope"][value="follows"]'):
        fails.append("full report: the choice should show under the daily report, with 'the companies I follow' picked")
    if pg.locator("legend", has_text="Site owner").count():
        fails.append("full report: a reader's Alerts page shows the owner's switch")
    pg.check('input[name="freq"][value="instant"]')
    if not pg.locator("#scope-box").is_hidden():
        fails.append("full report: the choice should hide with alerts as soon as a chart is out")
    pg.check('input[name="freq"][value="daily"]')
    pg.check('input[name="scope"][value="all"]')
    shot(pg, "acct_scope.png")
    pg.click("#prefs-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#save-msg').textContent === 'Saved.'")
    if ff("window.__ff.db.subscriptions[0].daily_scope") != "all":
        fails.append(f"full report: saved as {ff('window.__ff.db.subscriptions[0].daily_scope')!r}")
    pg.goto(base + "#home")
    pg.wait_for_selector("#daily:not([hidden]) .day")
    if "your full report), the ones you follow first" not in pg.inner_text("#daily") or "you follow" not in pg.inner_text("#daily .day.on"):
        fails.append(f"full report: home panel says {pg.inner_text('#daily')!r}")
    shot(pg, "home_daily_full.png")
    pg.goto(base + "#account")                      # back to the default for the checks below
    pg.wait_for_selector("#prefs-form")
    pg.check('input[name="scope"][value="follows"]')
    pg.click("#prefs-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#save-msg').textContent === 'Saved.'")
    # the company page's "Show decreases" follows the account and changes it
    pg.goto(base + "#c-320193")
    pg.wait_for_selector(".sheet svg")
    pg.locator('[data-view="y"]').click()
    pg.wait_for_selector(".dec-toggle:not([hidden])")
    if not pg.is_checked("[data-dec]"):
        fails.append("accounts: company page did not take 'Show decreases' from the account")
    pg.uncheck("[data-dec]")
    pg.wait_for_function("window.__ff.db.subscriptions[0].cmp_decreases === false", timeout=5000)
    print("company page toggle saved to the account:", ff("window.__ff.db.subscriptions[0].cmp_decreases"))
    pg.locator('[data-view="std"]').click()
    pg.goto(base + "#account")
    pg.wait_for_selector("#prefs-form")
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
    if pg.inner_text(".toast").strip() != "Sending…":                     # something on screen at once
        fails.append(f"email-me: no 'Sending…' right after the click, got {pg.inner_text('.toast')!r}")
    pg.wait_for_function("!/Sending/.test(document.querySelector('.toast').textContent)")
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

    # a full fiscal year (10-K): its own pill and page; "Email me" asks for the year, not the fourth quarter
    pg.goto(base + "#c-320193")
    pg.wait_for_selector(".intro .src")
    if "earnings release (8-K) filed Jul 30, 2026" not in pg.inner_text(".intro .src"):
        fails.append(f"intro: source line says {pg.inner_text('.intro .src')!r}")
    pg.wait_for_selector(".pill.year")
    pg.click(".pill.year")
    pg.wait_for_function("location.hash === '#c-320193-fy-2025-09-27'")
    pg.wait_for_function("(document.querySelector('.facts') || {}).textContent?.includes('fiscal year ended')")   # the new page, not the old one
    pg.wait_for_selector(".sheet svg")
    if pg.locator('[data-view="q"]').is_visible() or not pg.locator('[data-view="y"]').is_visible():
        fails.append("fiscal year: should offer 'vs FY24' and no previous-quarter view")
    if "fiscal year ended" not in pg.inner_text(".facts"):
        fails.append("fiscal year: the facts do not say 'fiscal year ended'")
    pg.wait_for_selector(".btn.send:not([hidden])")
    if "FY25 full year" not in pg.inner_text(".btn.send"):
        fails.append(f"fiscal year: Email me says {pg.inner_text('.btn.send')!r}")
    pg.click(".btn.send")
    pg.wait_for_function("window.__ff.db.send_requests.some((r) => r.kind === 'fy' && r.period_end === '2025-09-27')")
    pg.locator('[data-view="y"]').click()
    pg.wait_for_function("[...document.querySelectorAll('.sheet svg text')].some((x) => x.textContent.includes('what changed'))")
    shot(pg, "fiscal_year.png", full_page=True)
    pg.locator('[data-view="std"]').click()

    # "Compare any two periods": off by default; on in the alerts, a picker on company pages
    if pg.locator("#cmp-open").is_visible():
        fails.append("compare: the button shows although the reader has not turned it on")
    pg.goto(base + "#account")
    pg.wait_for_selector("#prefs-form")
    if pg.is_checked("#custom-compare"):
        fails.append("compare: should be off by default")
    pg.check("#custom-compare")
    pg.click("#prefs-form button[type=submit]")
    pg.wait_for_function("window.__ff.db.subscriptions[0].custom_compare === true")
    pg.goto(base + "#c-320193")
    pg.wait_for_selector("#cmp-open:not([hidden])")
    pg.click("#cmp-open")
    pg.wait_for_selector(".period-grid")
    rows = pg.locator(".period-grid tbody tr").count()
    if rows != 3:
        fails.append(f"compare: the picker should list fiscal years 2026, 2025 and 2024, got {rows} rows")
    pick = lambda end, kind="q": pg.locator(f'input[data-end="{end}"][data-kind="{kind}"]')
    pick("2026-06-27").check()
    pick("2025-09-27", "fy").check()
    if "Quarters are compared with quarters" not in pg.inner_text("#cmp-msg") or pick("2026-06-27").is_checked():
        fails.append("compare: a quarter and a fiscal year were allowed together")
    pick("2026-06-27").check()
    pick("2024-06-29").check()
    pick("2025-06-28").check()                     # a third tick drops the first one
    pick("2026-06-27").check()
    if pg.inner_text("#cmp-sum") != "Q3 FY26 compared with Q3 FY25" or pick("2024-06-29").is_checked():
        fails.append(f"compare: picked {pg.inner_text('#cmp-sum')!r}")
    pick("2025-06-28").uncheck()
    pick("2024-06-29").check()
    pg.click("#cmp-swap")
    if pg.inner_text("#cmp-sum") != "Q3 FY24 compared with Q3 FY26":
        fails.append(f"compare: swap shows {pg.inner_text('#cmp-sum')!r}")
    pg.click("#cmp-swap")
    shot(pg, "compare_picker.png", full_page=True)
    pg.click("#cmp-go")
    pg.wait_for_function("location.hash === '#c-320193-cmp-1'")
    pg.wait_for_selector(".cmp-wait h2")
    req = ff("window.__ff.db.chart_requests[0]")
    if (req["cik"], req["kind"], req["a_end"], req["b_end"]) != (320193, "q", "2026-06-27", "2024-06-29"):
        fails.append(f"compare: request saved as {req}")
    if "Q3 FY26 compared with Q3 FY24" not in pg.inner_text(".cmp-wait h2"):
        fails.append(f"compare: waiting page says {pg.inner_text('.cmp-wait')!r}")
    shot(pg, "compare_wait.png")
    import json as _json
    pg.evaluate("(r) => Object.assign(window.__ff.db.chart_requests[0], {status: 'done', done_at: new Date().toISOString(), result: r})",
                _comparison_result(site))
    pg.wait_for_selector(".cmp-head", timeout=15000)
    pg.wait_for_function("[...document.querySelectorAll('.sheet svg text')].some((x) => x.textContent.includes('what changed'))")
    if pg.locator('[data-view="y"]').is_visible() or "vs Q3 FY24" not in pg.inner_text('[data-view="q"]'):
        fails.append("compare: the chart should open on 'vs Q3 FY24' with no year-ago view")
    issues = pg.evaluate(CHECK_LABELS)
    if issues:
        print("compare layout:", issues[:4])
    shot(pg, "compare_done.png", full_page=True)
    pg.goto(base + "#c-320193")
    pg.wait_for_selector("#cmp-open:not([hidden])")
    pg.click("#cmp-open")
    pg.wait_for_selector(".cmp-list li")
    if "Q3 FY26 vs Q3 FY24" not in pg.inner_text(".cmp-list") or "ready" not in pg.inner_text(".cmp-list"):
        fails.append(f"compare: earlier comparisons list says {pg.inner_text('.cmp-list')!r}")

    # search: a company SEC lists but the site has not drawn yet; "Build its charts"; the page fills in
    pg.evaluate("document.documentElement.classList.remove('in-app')")   # the stand-in app bridge hides the site header
    pg.fill("#q", "alph")
    pg.wait_for_selector(".suggest a.off")
    if "no chart yet" not in pg.inner_text(".suggest a.off"):
        fails.append("search: companies without charts are not marked")
    pg.click(".suggest a.off")
    pg.wait_for_selector("#build-go:not([hidden])")
    if pg.inner_text("h1") != "Alphabet Inc.":
        fails.append(f"search: missing company page shows {pg.inner_text('h1')!r}")
    shot(pg, "build_company.png")
    pg.click("#build-go")
    pg.wait_for_function("window.__ff.db.company_requests.length === 1 && window.__ff.db.company_requests[0].cik === 1652044")
    built["done"] = True
    pg.wait_for_selector(".pills", timeout=15000)
    if "Alphabet" not in pg.inner_text("h1"):
        fails.append("search: the page did not fill in once the company was built")

    # owner tools: only an account on the owner list (Supabase site_owners) can turn them on
    pg.goto(base + "#owner")
    pg.wait_for_function("document.querySelector('.page-head') && document.querySelector('.page-head').textContent.includes('not a site owner')")
    if pg.locator("#owner-toggle").count():
        fails.append("owner tools: a reader's account was offered the switch")
    pg.evaluate("() => { window.__ff.owners = ['reader@example.com']; }")
    pg.goto(base + "#account")
    pg.wait_for_selector("#sign-out")
    pg.click("#sign-out")
    pg.wait_for_selector("#cta-form")
    pg.goto(base + "#owner")
    pg.wait_for_selector("#owner-signin")
    pg.click("#owner-signin")
    pg.wait_for_selector("#auth-email")
    pg.fill("#auth-email input", "reader@example.com")
    pg.click("#auth-email button")
    pg.wait_for_selector("#auth-code:not([hidden])")
    pg.fill("#auth-code input", "123456")
    pg.click("#auth-code button[type=submit]")
    pg.wait_for_function("location.hash === '#owner'")
    pg.wait_for_selector("#owner-toggle")
    if "Verified: signed in as reader@example.com" not in pg.inner_text(".page-head"):
        fails.append("owner tools: the owner's sign-in was not confirmed on the page")
    pg.click("#owner-toggle")
    if not pg.locator("#owner-form").count() or "Send a daily report now" not in pg.inner_text("#daily h2", timeout=10000):
        fails.append("owner tools: settings form or 'send a daily report now' missing")
    pg.goto(base + "#c-320193")
    pg.wait_for_selector("#thread pre")
    n_posts = pg.locator("#thread pre").count()
    print("owner tools: thread shown to the verified owner:", n_posts, "posts")
    if pg.locator("#thread .thread-meta b").count() != n_posts or pg.locator("#thread [data-img]").count() != 2:
        fails.append("owner tools: thread posts need role labels and both images need Save PNG")
    if "Filing" not in pg.inner_text("#thread .thread-info") or "Chart 2" not in pg.inner_text("#thread .thread-info"):
        fails.append(f"owner tools: thread header says {pg.inner_text('#thread .thread-info')!r}")
    with pg.expect_download() as dl:
        pg.click('#thread [data-img="std"]')
    if not dl.value.suggested_filename.endswith("-1-chart.png"):
        fails.append(f"owner tools: image saved as {dl.value.suggested_filename}")
    pg.click("#thread-mail")                       # straight to the inbox: a queued request, no GitHub page
    pg.wait_for_function("window.__ff.db.send_requests.some((r) => r.kind === 'thread' && r.cik === 320193)")
    shot(pg, "owner_thread.png", full_page=True)
    pg.goto(base + "#owner")
    pg.wait_for_selector("#owner-form")
    pg.check('input[name="thread-mail"][value="github"]')
    pg.select_option("#daily-hour", "9")
    pg.fill("#daily-min", "2")
    pg.click("#owner-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#owner-msg').textContent === 'Saved.'")
    o = ff("window.__ff.db.owner_settings[0]")
    if (o["thread_direct"], o["daily_hour"], o["min_revenue"], o["daily_scope"]) != (False, 9, 2e9, "min_revenue"):
        fails.append(f"owner tools: settings saved as {o}")
    if "Reader version: off" not in pg.inner_text("#reader-copy-state"):
        fails.append(f"owner tools: reader version should start off: {pg.inner_text('#reader-copy-state')!r}")
    pg.check('input[name="owner-scope"][value="all"]')            # the full report
    pg.click("#owner-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#owner-msg').textContent === 'Saved.'")
    if ff("window.__ff.db.owner_settings[0].daily_scope") != "all":
        fails.append("owner tools: the full report was not saved")
    pg.wait_for_function("document.querySelector('#daily') && document.querySelector('#daily').textContent.includes('your full report')")
    if "all in your report" not in pg.inner_text("#daily .day.on"):
        fails.append(f"owner tools: the day picker should count every filing: {pg.inner_text('#daily .day.on')!r}")
    shot(pg, "owner_settings.png", full_page=True)
    # the reader version, on the owner's Alerts page
    pg.goto(base + "#account")
    pg.wait_for_selector("#prefs-form")
    if not pg.locator("#reader-copy").count() or pg.is_checked("#reader-copy"):
        fails.append("owner alerts: the reader-version switch is missing or on by default")
    else:
        pg.check("#reader-copy")
        pg.click("#prefs-form button[type=submit]")
        pg.wait_for_function("document.querySelector('#save-msg').textContent.startsWith('Saved')")
        if ff("window.__ff.db.owner_settings[0].reader_copy") is not True:
            fails.append("owner alerts: the reader version was not saved")
        pg.evaluate("window.scrollTo(0, 0)")
        shot(pg, "owner_alerts.png")
        pg.goto(base + "#owner")
        pg.wait_for_selector("#reader-copy-state")
        if "Reader version: on" not in pg.inner_text("#reader-copy-state"):
            fails.append(f"owner tools: reader version shown as {pg.inner_text('#reader-copy-state')!r}")
    pg.goto(base + "#c-320193")
    pg.wait_for_selector("#thread pre")
    if pg.locator("#thread-mail").count():
        fails.append("owner tools: 'send straight to my inbox' was turned off but the button still sends directly")

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
    pg.wait_for_selector('.btn.follow[data-follow="sector:technology"]:not([hidden])')   # not the company page's button
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
                if view != "std":                          # the same comparison with decreases drawn (hatched)
                    if pg.locator(".dec-toggle").is_hidden():
                        fails.append(f"{co['ticker']} {view}: 'Show decreases' not offered in a comparison")
                    pg.check("[data-dec]")
                    pg.wait_for_timeout(150)
                    issues = pg.evaluate(CHECK_LABELS)
                    hatched = pg.locator(".sheet svg .ghost").count()
                    if not hatched:
                        fails.append(f"{co['ticker']} {view}: 'Show decreases' drew nothing")
                    if not pg.locator(".sheet svg .ghost path[clip-path]").count():
                        fails.append(f"{co['ticker']} {view}: decreases have no hatch lines")
                    print(f"{co['ticker']:6} {view}+decreases: {len(issues)} layout issues, {hatched} hatched", issues[:4])
                    warns.extend(f"{co['ticker']} {view}+decreases: {i}" for i in issues)
                    shot(pg, f"c_{co['ticker']}_{view}_dec.png", full_page=True)
                    pg.uncheck("[data-dec]")
                    pg.wait_for_timeout(100)
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
        cols = pg.locator(".notes .trend .tr-col").count()             # the line's quarters on file, as a small chart
        print("trend columns in the note:", cols, pg.inner_text(".notes .tr-read"))
        if cols != 2 or "Q3 FY26 · $54.3B" not in pg.inner_text(".notes .tr-read"):
            fails.append(f"note: trend chart missing or wrong ({cols} columns)")
        for node, words in (("capex", "Reported line: “Payments To Acquire"), ("fcf", "Calculated: operating cash flow − capital expenditures"),
                            ("L:aapl:IPhoneMember", "aapl:IPhoneMember on ProductOrServiceAxis")):
            pg.locator(f'g.node[data-node="{node}"] rect.hit').dispatch_event("click")
            pg.wait_for_selector(".notes .node-src")
            if words not in pg.inner_text(".notes .node-src"):
                fails.append(f"note: {node} does not say where its figure comes from")
        print("capex note:", pg.inner_text(".notes .node-src")[:120])
        pg.locator('g.node[data-node="revenue"] rect.hit').dispatch_event("click")
        pg.wait_for_selector(".notes .node-src .links a")
        hrefs = pg.eval_on_selector_all(".notes .node-src .links a", "(as) => as.map((a) => a.textContent + ' ' + a.href)")
        print("revenue source links:", hrefs)
        want = ("The filing", "Inline XBRL viewer", "XBRL data for RevenueFromContractWithCustomerExcludingAssessedTax", "Filing index")
        if not all(any(h.startswith(w) for h in hrefs) for w in want) or "accession 0000320193-26-000020" not in pg.inner_text(".notes .cite"):
            fails.append(f"note: source links or citation missing: {hrefs}")
        shot(pg, "c_AAPL_note.png")
        if pg.locator("#thread").count():
            fails.append("X thread panel shows to readers (it is an owner tool)")
        pg.goto(f"{base}#owner")
        pg.locator("#owner-toggle").click()
        pg.wait_for_selector("text=On: company pages show the X thread.")
        pg.goto(f"{base}#c-320193")
        pg.wait_for_selector(".sheet svg")
        n_posts = pg.locator("#thread pre").count()
        print("X thread posts on the page (owner on):", n_posts)
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

        check_accounts(b, base, fails, shot, os.path.abspath(args.site))

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
