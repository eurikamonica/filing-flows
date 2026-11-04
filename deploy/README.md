# Serving the site from your own server

GitHub Actions keeps doing all the work (the 15-minute scans, the earnings fast lane, every build). Only the place
the finished site is served from changes: next to GitHub Pages, or instead of it, a plain Linux server with Caddy.
The site stays static; sign-in and alerts stay on Supabase. Every address stays the same, so search engines see a
change of host, not a move (no "change of address" in Search Console).

The owner's step-by-step list, in Chinese, one action at a time: [OWNER-CHECKLIST.zh.md](OWNER-CHECKLIST.zh.md).

```
scan.yml / earnings-fast.yml ── build _site ── artifact "github-pages" ─┬─ deploy        → GitHub Pages
                                                                         └─ deploy-server → rsync (changed files)
                                                                                            → server: stage/
                                                                                            → ff-publish: snapshot,
                                                                                              symlink switch
        then: verify-integration, indexnow, alerts, buffer (once either deploy is done)
```

## The server

Any Ubuntu or Debian machine with systemd: nothing below belongs to one hosting company. 2 cores, 4 GB and 40 GB
are plenty (the site is ~0.8 GB, ~70,000 pages; three published snapshots share their unchanged files).

```
curl -fsSL https://raw.githubusercontent.com/eurikamonica/filing-flows/main/deploy/server/setup.sh | sudo bash
```

[server/setup.sh](server/setup.sh) is safe to run again. It installs Caddy (its official apt repository), rsync,
ufw and unattended-upgrades; creates the user `deploy` (no password, no sudo) and `/srv/filing-flows`; installs the
commands below; makes the deploy key; starts Caddy in staging mode; opens only ports 22, 80 and 443; turns on
automatic security updates (a reboot at 08:10 UTC when one needs it); caps logs (Caddy's access log rolls at 50 MB,
5 kept; the journal stays under 300 MB); adds a 2 GB swap file (`--no-swap` to skip; `--fail2ban` adds fail2ban).
Other domain: `… | sudo bash -s -- --domain example.com`. It does not touch SSH logins: `sudo ff-ssh-lockdown`
turns off passwords and root login once your own key works, and refuses while your user has no key.

| Path | |
|---|---|
| `/srv/filing-flows/stage/` | what rsync uploads into |
| `/srv/filing-flows/releases/<UTC time>/` | published snapshots (hard links into stage/ at that moment) |
| `/srv/filing-flows/current` | symlink to the live snapshot; Caddy's root |
| `/srv/filing-flows/state/` | `lock`, `stage-ok` (the last upload finished), `last-publish.json` |
| `/etc/filing-flows/site.conf` | domain, server addresses, Caddy mode |
| `/etc/caddy/Caddyfile` | written by `ff-site` (the previous one kept as `Caddyfile.bak`) |
| `/var/log/caddy/access.log` | requests, JSON, rolled at 50 MB |

| Command | |
|---|---|
| `sudo ff-site staging` · `live [--wait-dns]` · `origin [--paste]` · `test-host NAME\|off` · `show` | Caddy's mode (below) |
| `sudo ff-deploy-key show` · `new` · `forget` | the three GitHub secrets; a new key (the old one stops working); delete the private key from the server |
| `sudo ff-ssh-lockdown [--undo]` | SSH keys only / passwords allowed again |
| `sudo -u deploy ff-publish --rollback [ID]` | the live site back to the previous snapshot (until the next deploy) |
| `ff-status` | JSON: disk, memory, web server, live snapshot, reboot pending |

## The deploy

[deploy-server.yml](../.github/workflows/deploy-server.yml) is called by scan.yml and earnings-fast.yml after every
build and can be run by hand (it then takes the newest published site). It does nothing until the repository has
the secrets `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` and `DEPLOY_HOST` (`DEPLOY_USER` optional, default `deploy`).

- `rsync -rp --checksum --delete --chmod=D755,F644`: no `-t`, so a file the build rewrote with the same content
  keeps its date on the server and is not sent (`--checksum` decides), and its ETag stays the same for browsers.
  Symlinks are not sent (`-r` without `-l`), and the server would defang them anyway (rrsync `-munge`).
- The deploy key's line in `~deploy/.ssh/authorized_keys` is `restrict,command="/usr/local/bin/ff-deploy-gate"`:
  no shell, no forwarding. The gate allows an upload through `rrsync -wo` into `stage/` only, `publish` and `status`.
- `--delete` only ever acts on `stage/`. The live site is a snapshot that rsync never writes into: rsync replaces a
  changed file by writing a new one and renaming it, so the snapshot keeps the old file (never `--inplace`).
- `ff-publish` refuses when the upload did not finish (`state/stage-ok` is written only after rsync exits 0), when
  there is no `index.html`, or when the upload has under 70% of the live site's pages (`allow_shrink` overrides;
  the workflow also refuses a build under 1,000 pages). Then it hard-links `stage/` into `releases/<time>/`,
  points `current` at it with one rename (atomic: a visitor gets the old site or the new one, never a mix) and
  keeps the newest three snapshots.
- One deploy at a time: the job's concurrency group `deploy-server` (shared by both workflows) and a lock on the
  server. A deploy waiting behind another is replaced by a newer one; both carry the whole site.
- Nothing secret is printed: the key goes to a 0600 file and is deleted at the end; the host is a secret, so
  GitHub masks it; rsync prints only its counts.
- `PAGES_DEPLOY` = `off` (repository variable) skips the GitHub Pages deploy once Pages is turned off.
  verify-integration, indexnow, alerts and buffer run once either deploy is done.

## Like GitHub Pages, rule by rule

Checked by [tests/test_server_caddy.py](../tests/test_server_caddy.py) against a real Caddy, and on the live site
before the switch by `scripts/compare_hosts.py` (server-monitor.yml with "compare").

| Request | GitHub Pages | Server |
|---|---|---|
| `/c/amzn/` | `c/amzn/index.html` | same (`try_files {path}` then `file_server`) |
| `/c/amzn` (a directory) | 301 to `/c/amzn/` | 301 to `/c/amzn/`, query kept |
| `/c/amzn/index.html`, `/index.html` | 200 | 200 (no redirect: `disable_canonical_uris`) |
| `/about` | `about.html` | same (`try_files {path} {path}.html`) |
| missing page | 404 status, the site's `404.html` or GitHub's page | 404 status, `404.html` if the site has one, else a short page |
| directory without `index.html` | 404 | 404 (never a listing) |
| `www.` | 301 to the bare domain (CNAME file) | 301 to the bare domain, path and query kept |
| `http://` | 301 to `https://` | 308 to `https://` (Caddy; treated like 301 by search engines) |
| `_underscore/`, `.nojekyll`, `CNAME` | served (`.nojekyll`) | served: nothing is special |
| robots.txt, sitemaps, `<IndexNow key>.txt` | at the root | same files, same paths |
| compression | gzip | zstd or gzip |
| `Cache-Control` | `max-age=600` | 300 s for pages, data, sitemaps; 600 s for other files; a year for `?v=` or hashed names |
| `Access-Control-Allow-Origin` | `*` | `*` |

## Caddy's modes ([server/bin/ff-site](server/bin/ff-site))

- **staging** (after setup): plain HTTP only, nothing to certify. `http://<server address>/` shows the site in a
  browser with `X-Robots-Tag: noindex` and a robots.txt that disallows everything; the real name answers by Host
  header for the comparison (also noindex). `sudo ff-site test-host test.example.com` adds an HTTPS test name
  (its DNS record first; the same noindex and robots.txt).
- **live**: the domain points straight at the server (Cloudflare "DNS only", grey cloud). Caddy gets and renews
  Let's Encrypt certificates itself. A certificate can only be issued once the name points here, so run
  `sudo ff-site live --wait-dns` and change the DNS record while it waits: it switches as soon as 1.1.1.1 and
  8.8.8.8 show the server's address. Visitors who reach the server in that minute get a certificate error.
- **origin**: through Cloudflare's proxy (orange cloud), SSL mode **Full (strict)**, with a **Cloudflare Origin
  Certificate** (`sudo ff-site origin --paste`). Chosen over the other two ways because it is installed before the
  switch (no minute without a certificate), runs 15 years without renewal, needs no Cloudflare API token on the
  server and no custom Caddy build (a DNS-challenge plugin would leave the apt package, so no automatic updates);
  issuing a Let's Encrypt certificate first and then turning the proxy on would leave its renewals depending on
  HTTP challenges passing through the proxy. Its one limit: only Cloudflare trusts it, so turning the proxy off
  later means `sudo ff-site live` at the same time.

### Cloudflare proxy (orange cloud) or not

| | Proxy on (orange) | DNS only (grey) |
|---|---|---|
| Switching and going back | in seconds: visitors always see Cloudflare's addresses, only the origin changes | as fast as the record's TTL (lower it to 1–5 minutes a day before) |
| Certificate at the switch | Origin Certificate installed beforehand: no gap | Let's Encrypt needs the DNS change first: up to a minute of errors |
| Speed far from Virginia (Asia, Europe; /zh/ readers) | Cloudflare's nearby caches for images, CSS, JS | every request crosses to Virginia |
| Attacks, traffic peaks | Cloudflare absorbs them; the server's address stays hidden | the server takes them (OVH filters large floods) |
| What Cloudflare does | sees all traffic; its outages become the site's; its settings can change answers | nothing beyond DNS |
| Settings to get right | SSL Full (strict); Caching → Browser Cache TTL "Respect Existing Headers" (otherwise it raises browser caching to 4 hours and readers keep old scripts); leave HTML uncached (the default) | none |
| Logs | visitors appear as Cloudflare addresses | real addresses |

With the proxy, HTML is not cached at Cloudflare (its default), so pages are as fresh as the server; images, CSS and
JS are cached for the 10 minutes the server's `Cache-Control` allows, as on GitHub Pages today. No purge after a
deploy is needed. Bot Fight Mode is best left off: it can challenge automated visitors from data centres, such as
the monitor and the comparison running on GitHub Actions (search engines' verified crawlers pass either way).

## Switching (each step only with the owner's go-ahead)

1. Server set up, secrets added, a full deploy done (the next scan, or deploy-server.yml by hand).
2. Look at `http://<server address>/`; run server-monitor.yml by hand with "compare": statuses, redirects, types and
   content of the fixed rules and ~300 sitemap pages, old host against the server. Differences in status or
   redirect are fixed before going on; different content is usually a build a minute apart.
3. Note the current DNS records of `@` and `www` (the way back). Grey cloud: lower their TTL a day ahead.
4. Orange: `sudo ff-site origin --paste` first, SSL Full (strict), Browser Cache TTL "Respect Existing Headers",
   then point the records at the server. Grey: start `sudo ff-site live --wait-dns`, then point the records.
   One `A` record each with the server's IPv4 (an `AAAA` with its IPv6 is optional). Every old record of the two
   names (GitHub's four A and four AAAA addresses, or a www CNAME) goes, or some visitors keep reaching GitHub.
5. Check: server-monitor.yml by hand, `curl -I https://filing-flows.com/`, Search Console's URL inspection.
6. GitHub Pages keeps running for some days as the way back (both get every build). When the server has been
   steady and Search Console crawls normally: Settings → Pages → turn off, then the variable `PAGES_DEPLOY` = `off`.

## Monitoring

- [server-monitor.yml](../.github/workflows/server-monitor.yml), every half hour (`SITE_MONITOR` = `off` stops it):
  the public site (home page, robots.txt, sitemap index, a missing page answers 404, www, certificate ≥ 14 days,
  the build stamp under 3 hours old) and, with the deploy secrets, the server over SSH (disk under 80%, Caddy
  running, last publish under 2 hours). Problems are e-mailed with the MAIL_* secrets of the daily report when they
  start, every 6 hours while they last, and once more when they are over.
- The owner's daily report opens with the server's line (pipeline/server_status.py): disk, last update, problems.
- Optional, outside GitHub: a free uptime service (e.g. UptimeRobot) on `https://filing-flows.com/` every 5 minutes.

## When something goes wrong

- A broken build went live: `sudo -u deploy ff-publish --rollback` (previous snapshot). The next deploy publishes
  the newest build again; ff-publish already refuses an upload that lost 30% of the pages.
- The server is down or unreachable: while GitHub Pages still runs, point the DNS records back to the values noted in
  step 3 (proxy on: seconds). Without Pages: the provider's web console (OVH: KVM in the control panel), reboot,
  `systemctl status caddy`, `journalctl -u caddy`.
- Locked out of SSH: the provider's web console, then `sudo ff-ssh-lockdown --undo`.
- Nothing on the server is unique: the site is rebuilt from GitHub every 15 minutes. A lost server is replaced by a
  new one (below) in half an hour; the provider's backups are a convenience, not the copy that counts.

## Moving to another provider

1. A new Ubuntu/Debian server; your SSH key on it; the same `setup.sh` command.
2. `sudo ff-deploy-key show` there; replace the three secrets in GitHub; run deploy-server.yml by hand.
3. `sudo ff-site origin --paste` (the same Origin Certificate works on any server) or `live --wait-dns`, then point
   the DNS records at the new address. Keep the old server for a day, then cancel it.
