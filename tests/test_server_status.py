"""The own server's line in the owner's daily report (pipeline/server_status.py)."""
import datetime as dt
import json
import os
import stat
import subprocess
import unittest

from pipeline import server_status as S

NOW = dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.timezone.utc)
OK = {"disk": {"total_gb": 38.6, "used_gb": 6.2, "free_gb": 32.4, "used_pct": 16.1}, "web": "active",
      "published_at": "2026-11-03T08:49:12Z", "pages": 70412, "reboot_required": False}
ENV = {"DEPLOY_SSH_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----\r\nabc   \r\n-----END OPENSSH PRIVATE KEY-----\r\n",
       "DEPLOY_KNOWN_HOSTS": "203.0.113.5 ssh-ed25519 AAAA\n", "DEPLOY_HOST": "203.0.113.5"}


class ServerStatus(unittest.TestCase):
    def test_no_server_no_line(self):
        self.assertIsNone(S.fetch({}))
        self.assertEqual(S.report_line({}), "")

    def test_fetch_uses_a_private_key_file_and_cleans_up(self):
        seen = {}

        def run(cmd, **kw):
            kf = cmd[cmd.index("-i") + 1]
            seen["cmd"], seen["key"] = cmd, kf
            seen["mode"] = stat.S_IMODE(os.stat(kf).st_mode)
            seen["text"] = open(kf).read()
            return subprocess.CompletedProcess(cmd, 0, json.dumps(OK) + "\n", "")

        s = S.fetch(ENV, run=run)
        self.assertEqual(s["pages"], 70412)
        self.assertEqual(seen["mode"], 0o600)
        self.assertNotIn("\r", seen["text"])
        self.assertNotIn("abc   ", seen["text"])
        self.assertFalse(os.path.exists(seen["key"]))                  # deleted right after
        self.assertEqual(seen["cmd"][-2:], ["deploy@203.0.113.5", "status"])
        self.assertIn("StrictHostKeyChecking=yes", seen["cmd"])

    def test_fetch_errors(self):
        self.assertEqual(S.fetch(ENV, run=lambda c, **k: subprocess.CompletedProcess(c, 255, "", "nope")),
                         {"error": "ssh exit 255"})

        def boom(c, **k):
            raise subprocess.TimeoutExpired(c, 25)
        self.assertEqual(S.fetch(ENV, run=boom), {"error": "TimeoutExpired"})

    def test_sentences(self):
        self.assertEqual(S.sentence(OK, NOW),
                         "Own server: running fine (disk 16% used (32 GB free), site updated 08:49 UTC, 70,412 pages).")
        full = dict(OK, disk={"used_pct": 86.0, "free_gb": 5.4})
        self.assertIn("needs a look — its disk is 86% full (5.4 GB free)", S.sentence(full, NOW))
        stale = dict(OK, published_at="2026-11-03T04:10:00Z")
        self.assertIn("last updated 5 hours ago", S.sentence(stale, NOW))
        down = dict(OK, web="failed")
        self.assertIn("the web server is failed", S.sentence(down, NOW))
        self.assertEqual(S.sentence({"error": "ssh exit 255"}, NOW),
                         "Own server: needs a look — the server did not answer (ssh exit 255).")
        self.assertIn("restarts it at 08:10 UTC", S.sentence(dict(OK, reboot_required=True), NOW))
        self.assertEqual(S.problems(OK, NOW), [])


if __name__ == "__main__":
    unittest.main()
