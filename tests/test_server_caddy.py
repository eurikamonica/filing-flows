"""The web server's configuration (deploy/server/bin/ff-site) answers like GitHub Pages did: a real Caddy on local
ports serves a small site in staging mode (HTTP, Host header) and live mode (HTTPS with Caddy's local test
certificates). Skipped where Caddy is not installed or deploy/ is not checked out."""
import gzip
import http.client
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FF_SITE = ROOT / "deploy" / "server" / "bin" / "ff-site"
CADDY = shutil.which("caddy")
DOMAIN = "filing-flows.com"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_site(root):
    (root / "c" / "amzn").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "_under").mkdir()
    (root / "both").mkdir()
    (root / "index.html").write_text("<!doctype html><title>home</title>" + "x" * 2000)
    (root / "about.html").write_text("about page")
    (root / "both.html").write_text("both file")
    (root / "both" / "index.html").write_text("both dir")
    (root / "c" / "amzn" / "index.html").write_text("amazon page")
    (root / "data" / "index.json").write_text('{"v": 1}')
    (root / "styles.css").write_text("body{color:red}")
    (root / "app.0123abcd.js").write_text("var a=1;")
    (root / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://filing-flows.com/sitemap-index.xml\n")
    (root / "sitemap-index.xml").write_text("<sitemapindex/>")
    (root / "_under" / "x.html").write_text("underscore")
    (root / ".nojekyll").write_text("")


class Caddy:
    def __init__(self, tmp, mode, root):
        self.http_port, self.https_port = free_port(), free_port()
        conf = tmp / f"{mode}.conf"
        conf.write_text(f'DOMAIN="{DOMAIN}"\nSITE_NAME="Filing Flows"\nMODE="{mode}"\n')
        env = dict(os.environ, FF_CONF=str(conf), FF_ROOT=str(root), FF_LOG="off",
                   FF_HTTP_PORT=str(self.http_port), FF_HTTPS_PORT=str(self.https_port),
                   FF_EXTRA_GLOBAL="\tadmin off\n\tlocal_certs\n\tskip_install_trust\n\tstorage file_system "
                                   f"{tmp / ('store-' + mode)}",
                   XDG_DATA_HOME=str(tmp / "xdg"), XDG_CONFIG_HOME=str(tmp / "xdg"), HOME=str(tmp))
        self.file = tmp / f"Caddyfile.{mode}"
        self.file.write_text(subprocess.run(["bash", str(FF_SITE), "render", mode], env=env, check=True,
                                            capture_output=True, text=True).stdout)
        self.log = open(tmp / f"caddy-{mode}.log", "w")
        self.proc = subprocess.Popen([CADDY, "run", "--adapter", "caddyfile", "--config", str(self.file)], env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        port = self.https_port if mode != "staging" else self.http_port
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.3)

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def get(port, path, host=DOMAIN, tls=False, method="GET", headers=None):
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=ctx)
        conn._tunnel_host = None
        # SNI must name the site: connect by hand
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        conn.sock = ctx.wrap_socket(sock, server_hostname=host)
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, headers={"Host": host, **(headers or {})})
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, body


@unittest.skipUnless(CADDY and FF_SITE.exists(), "needs caddy and deploy/server/bin/ff-site")
class CaddyLikeGitHubPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.srv = cls.tmp / "srv"
        (cls.srv / "releases" / "one").mkdir(parents=True)
        make_site(cls.srv / "releases" / "one")
        os.symlink("releases/one", cls.srv / "current")
        cls.staging = Caddy(cls.tmp, "staging", cls.srv / "current")
        cls.live = Caddy(cls.tmp, "live", cls.srv / "current")

    @classmethod
    def tearDownClass(cls):
        cls.staging.stop()
        cls.live.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def s(self, path, **kw):
        return get(self.staging.http_port, path, **kw)

    def test_directories(self):
        st, h, _ = self.s("/c/amzn")
        self.assertEqual((st, h["location"]), (301, "/c/amzn/"))
        st, h, _ = self.s("/c/amzn?x=1&y=2")
        self.assertEqual((st, h["location"]), (301, "/c/amzn/?x=1&y=2"))
        st, _, body = self.s("/c/amzn/")
        self.assertEqual((st, body), (200, b"amazon page"))
        st, _, body = self.s("/c/amzn/index.html")                 # no redirect to the directory
        self.assertEqual((st, body), (200, b"amazon page"))
        st, _, body = self.s("/")
        self.assertEqual(st, 200)
        self.assertTrue(body.startswith(b"<!doctype html>"))
        st, h, _ = self.s("/both")                                   # a directory wins over both.html
        self.assertEqual((st, h["location"]), (301, "/both/"))
        st, _, _ = self.s("/data/")                                  # no index: 404, never a listing
        self.assertEqual(st, 404)
        st, _, _ = self.s("/data")
        self.assertEqual(st, 404)

    def test_pages_without_html(self):
        st, _, body = self.s("/about")
        self.assertEqual((st, body), (200, b"about page"))
        st, _, body = self.s("/about.html")
        self.assertEqual((st, body), (200, b"about page"))
        st, _, _ = self.s("/about/")
        self.assertEqual(st, 404)
        st, _, body = self.s("/_under/x.html")
        self.assertEqual((st, body), (200, b"underscore"))

    def test_missing_pages_are_404(self):
        st, h, body = self.s("/no/such/page")
        self.assertEqual(st, 404)
        self.assertIn(b"Page not found", body)
        self.assertIn("text/html", h["content-type"])
        st, _, _ = self.s("/../../etc/passwd")
        self.assertIn(st, (400, 404))
        page = self.srv / "releases" / "one" / "404.html"
        page.write_text("the site's own 404 page")
        try:
            st, _, body = self.s("/still/missing")
            self.assertEqual((st, body), (404, b"the site's own 404 page"))
        finally:
            page.unlink()

    def test_headers(self):
        st, h, _ = self.s("/")
        self.assertEqual(h["cache-control"], "public, max-age=300")
        self.assertEqual(h["access-control-allow-origin"], "*")
        self.assertEqual(h["x-robots-tag"], "noindex, nofollow")       # staging only
        self.assertIn("etag", h)
        _, h, _ = self.s("/data/index.json")
        self.assertEqual(h["cache-control"], "public, max-age=300")
        self.assertIn("json", h["content-type"])
        _, h, _ = self.s("/about")
        self.assertEqual(h["cache-control"], "public, max-age=300")
        _, h, _ = self.s("/styles.css")
        self.assertEqual(h["cache-control"], "public, max-age=600")
        self.assertIn("text/css", h["content-type"])
        _, h, _ = self.s("/styles.css?v=7")
        self.assertEqual(h["cache-control"], "public, max-age=31536000, immutable")
        _, h, _ = self.s("/app.0123abcd.js")
        self.assertEqual(h["cache-control"], "public, max-age=31536000, immutable")
        st, h, body = self.s("/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(h.get("content-encoding"), "gzip")
        self.assertTrue(gzip.decompress(body).startswith(b"<!doctype html>"))
        st, h, body = self.s("/", method="HEAD")
        self.assertEqual((st, body), (200, b""))

    def test_www_goes_to_the_bare_domain(self):
        st, h, _ = self.s("/c/amzn/?a=b", host="www." + DOMAIN)
        self.assertEqual((st, h["location"]), (301, "https://filing-flows.com/c/amzn/?a=b"))

    def test_robots_and_sitemaps(self):
        st, _, body = self.s("/robots.txt")
        self.assertEqual(st, 200)
        self.assertIn(b"Allow: /", body)                              # the site's own on the real name
        st, h, _ = self.s("/sitemap-index.xml")
        self.assertEqual(st, 200)
        self.assertEqual(h["content-type"], "application/xml; charset=utf-8")    # as GitHub Pages
        st, h, _ = self.s("/no-such-sitemap.xml")
        self.assertEqual(st, 404)
        self.assertIn("text/html", h["content-type"])

    def test_preview_by_address_is_never_indexed(self):
        st, h, _ = self.s("/", host="127.0.0.1")
        self.assertEqual(st, 200)
        self.assertEqual(h["x-robots-tag"], "noindex, nofollow")
        st, _, body = self.s("/robots.txt", host="127.0.0.1")
        self.assertEqual(st, 200)
        self.assertIn(b"Disallow: /", body)

    def test_switching_the_symlink_switches_the_site(self):
        two = self.srv / "releases" / "two"
        make_site(two)
        (two / "about.html").write_text("about, new")
        tmp = self.srv / ".current.new"
        os.symlink("releases/two", tmp)
        os.replace(tmp, self.srv / "current")
        try:
            st, _, body = self.s("/about")
            self.assertEqual(body, b"about, new")
        finally:
            os.symlink("releases/one", tmp)
            os.replace(tmp, self.srv / "current")

    def test_live_mode(self):
        port = self.live.https_port
        st, h, body = get(port, "/c/amzn/", tls=True)
        self.assertEqual((st, body), (200, b"amazon page"))
        self.assertNotIn("x-robots-tag", h)
        st, h, _ = get(port, "/c/amzn", tls=True)
        self.assertEqual((st, h["location"]), (301, "/c/amzn/"))
        st, h, _ = get(port, "/x?y=1", host="www." + DOMAIN, tls=True)
        self.assertEqual((st, h["location"]), (301, "https://filing-flows.com/x?y=1"))
        st, _, body = get(port, "/nothing-here", tls=True)
        self.assertEqual(st, 404)
        st, h, _ = get(self.live.http_port, "/c/amzn/?q=1")              # plain HTTP: to HTTPS, permanently
        self.assertIn(st, (301, 308))
        self.assertTrue(h["location"].startswith("https://filing-flows.com"))
        self.assertTrue(h["location"].endswith("/c/amzn/?q=1"))


if __name__ == "__main__":
    unittest.main()
