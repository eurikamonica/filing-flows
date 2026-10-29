import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import indexnow  # noqa: E402

BASE = "https://filing-flows.com"
KEY, _ = indexnow.config()


def sitemap(pages):
    rows = "".join(f"<url><loc>{u}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>" for u, m in pages.items())
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>'.encode()


class Site:
    def __init__(self, main, people=None, key_live=True, status=200):
        self.main, self.people, self.key_live, self.status, self.sent = main, people or {}, key_live, status, []

    def fetch(self, url):
        path = url.split("?")[0][len(BASE):]
        if path == "/sitemap.xml":
            return sitemap(self.main)
        if path == "/sitemap-people.xml":
            return sitemap(self.people)
        if path == f"/{KEY}.txt" and self.key_live:
            return KEY.encode()
        raise OSError("404")

    def send(self, endpoint, host, key, urls):
        assert host == "filing-flows.com" and key == KEY and endpoint.startswith("https://")
        self.sent.append(list(urls))
        return self.status, ""


def test_key_is_valid_and_written(tmp_path):
    assert KEY and indexnow.write_key(str(tmp_path)) == KEY
    assert (tmp_path / f"{KEY}.txt").read_text() == KEY


def test_first_run_sends_all_then_only_changes(tmp_path):
    state = str(tmp_path / "s" / "state.json")
    pages = {f"{BASE}/": "", f"{BASE}/c/nvda/": "2026-08-26", f"{BASE}/c/aapl/": "2026-08-01",
             "https://eurikamonica.github.io/filing-flows/m/x/": ""}            # another host: never sent
    site = Site(pages, {f"{BASE}/o/nancy-pelosi/": "2026-10-01"})
    assert indexnow.submit(BASE + "/", state, fetch=site.fetch, send=site.send) == 4
    assert sorted(site.sent[0]) == sorted([f"{BASE}/", f"{BASE}/c/nvda/", f"{BASE}/c/aapl/", f"{BASE}/o/nancy-pelosi/"])
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 0 and len(site.sent) == 1   # nothing changed
    site.main[f"{BASE}/c/nvda/"] = "2026-11-20"                         # a new filing
    del site.main[f"{BASE}/c/aapl/"]                                    # a page that is gone
    site.main[f"{BASE}/c/msft/"] = "2026-10-29"                         # a new company
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 3
    assert sorted(site.sent[1]) == [f"{BASE}/c/aapl/", f"{BASE}/c/msft/", f"{BASE}/c/nvda/"]
    assert json.load(open(state))[f"{BASE}/c/nvda/"] == "2026-11-20"


def test_nothing_saved_when_key_not_live_or_refused(tmp_path):
    state = str(tmp_path / "state.json")
    site = Site({f"{BASE}/c/nvda/": "2026-08-26"}, key_live=False)
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 0
    assert site.sent == [] and not os.path.exists(state)
    site.key_live, site.status = True, 429
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 0
    assert len(site.sent) == 1 and not os.path.exists(state)          # retried by the next scan
    site.status = 202
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 1 and os.path.exists(state)


def test_batches_of_ten_thousand(tmp_path):
    site = Site({f"{BASE}/c/x{i}/": "2026-10-01" for i in range(10001)})
    assert indexnow.submit(BASE, str(tmp_path / "state.json"), fetch=site.fetch, send=site.send) == 10001
    assert [len(b) for b in site.sent] == [10000, 1]


def test_a_new_resend_round_sends_every_page_again(tmp_path, monkeypatch):
    state = str(tmp_path / "state.json")
    site = Site({f"{BASE}/": "", f"{BASE}/c/nvda/": "2026-08-26"})
    monkeypatch.setattr(indexnow, "resend_round", lambda: "a")
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 2
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 0
    monkeypatch.setattr(indexnow, "resend_round", lambda: "b")          # the config's "resend_all" changed
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 2
    assert indexnow.submit(BASE, state, fetch=site.fetch, send=site.send) == 0
