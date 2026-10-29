"""pipeline/buffer.py: one request per thread, the channel remembered, and Buffer's API limits waited out, not failed on."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import buffer  # noqa: E402

HEADERS = {"RateLimit-Policy": '"15m";q=150;w=900, "24h";q=600;w=86400, "30d";q=1000;w=2592000',
           "RateLimit": '"15m";r=140;t=800, "24h";r=590;t=80000, "30d";r=900;t=1296000'}


class Reply:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or HEADERS, json.dumps(body)

    def json(self):
        return self._body


class FakeBuffer:
    """Answers the three operations pipeline/buffer.py sends; `plan` overrides createPost answers in order."""
    def __init__(self, plan=()):
        self.calls, self.plan = [], list(plan)

    def __call__(self, url, json=None, headers=None, timeout=None):
        q = json["query"]
        self.calls.append("org" if "organizations" in q else "channels" if "channels(" in q else "create")
        if self.calls[-1] == "org":
            return Reply(200, {"data": {"account": {"organizations": [{"id": "o1", "name": "me"}]}}})
        if self.calls[-1] == "channels":
            return Reply(200, {"data": {"channels": [{"id": "c9", "name": "filingflows", "service": "twitter", "isQueuePaused": False}]}})
        if self.plan:
            return self.plan.pop(0)
        return Reply(200, {"data": {"createPost": {"post": {"id": f"p{len(self.calls)}", "status": "buffer", "dueAt": None}}}})


RATE_LIMITED = Reply(429, {"errors": [{"message": "Too many requests from this client.",
                                       "extensions": {"code": "RATE_LIMIT_EXCEEDED", "window": "30d"}}]},
                     {"Retry-After": "86400", **HEADERS})
FULL = Reply(200, {"data": {"createPost": {"message": "You have reached the maximum number of scheduled posts"}}})


class BufferPacing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "x").mkdir()
        self.state = str(self.root / "state" / "buffer-state.json")
        cfg = self.root / "x.json"
        cfg.write_text(json.dumps({"mode": "buffer", "links": True, "media": ["png"]}))
        self.cfg = str(cfg)
        env = patch.dict(os.environ, {"BUFFER_API_KEY": "k", "BUFFER_CHANNEL_ID": "", "BUFFER_DAILY_REQUESTS": ""})
        env.start()
        self.addCleanup(env.stop)
        overlay = patch("pipeline.xprefs.overlay", side_effect=lambda c: c)    # no owner settings from Supabase
        overlay.start()
        self.addCleanup(overlay.stop)

    def pending(self, *labels):
        (self.root / "x" / "pending.json").write_text(json.dumps(
            [{"label": lb, "posts": [f"{lb} post", f"{lb} reply"], "images": [f"{lb}.png"]} for lb in labels]))

    def run_buffer(self, fake):
        with patch.object(buffer.requests, "post", side_effect=fake):
            buffer.LIMITS.clear()
            return buffer.main(["--site", str(self.root), "--site-url", "https://media.example", "--state", self.state,
                                "--config", self.cfg])

    def read(self):
        return json.load(open(self.state))

    def test_channel_is_looked_up_once_then_one_request_per_thread(self):
        self.pending("A", "B")
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, ["org", "channels", "create", "create"])
        st = self.read()
        self.assertEqual(st["channel"]["id"], "c9")
        self.assertEqual(st["limits"]["2592000"]["remaining"], 900)
        self.pending("C")
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, ["create"])                    # no lookups the second time
        self.assertEqual(self.read()["spent"]["requests"], 5)

    def test_rate_limit_waits_and_does_not_fail(self):
        self.pending("A", "B")
        fake = FakeBuffer([RATE_LIMITED])
        self.assertEqual(self.run_buffer(fake), 0)                  # a 429 is not a failed run
        st = self.read()
        until = dt.datetime.fromisoformat(st["blocked_until"].replace("Z", "+00:00"))
        self.assertGreater(until - dt.datetime.now(dt.timezone.utc), dt.timedelta(hours=23))
        self.assertEqual([b["label"] for b in st["backlog"]], ["A", "B"])
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, [])                            # nothing is sent before Retry-After

    def test_full_queue_backs_off_and_keeps_the_threads(self):
        self.pending("A", "B")
        fake = FakeBuffer([FULL])
        self.assertEqual(self.run_buffer(fake), 0)
        st = self.read()
        self.assertTrue(st["queue_full_until"])
        self.assertEqual(len(st["backlog"]), 2)
        st["queue_full_until"] = "2000-01-01T00:00:00Z"            # the back-off is over
        buffer.save_state(self.state, st)
        self.pending("C")
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, ["create", "create", "create"])   # A and B first, then C
        self.assertEqual(self.read()["backlog"], [])

    def test_daily_budget_and_thirty_day_share(self):
        self.pending("A", "B", "C")
        with patch.dict(os.environ, {"BUFFER_CHANNEL_ID": "c9", "BUFFER_DAILY_REQUESTS": "2"}):
            fake = FakeBuffer()
            self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, ["create", "create"])          # BUFFER_CHANNEL_ID: no lookups; 2 a day
        self.assertEqual([b["label"] for b in self.read()["backlog"]], ["C"])
        now = dt.datetime(2026, 10, 29, tzinfo=dt.timezone.utc)
        st = {"limits": {"2592000": {"remaining": 30, "reset_in": 10 * 86400}}, "limits_at": "2026-10-29T00:00:00Z"}
        self.assertEqual(buffer.budget(st, now, 30), 3)             # 30 left over 10 days: 3 today

    def test_old_backlog_is_dropped_and_sent_threads_not_repeated(self):
        self.pending("A")
        old = {"label": "old", "parts": [{"text": "x", "images": []}], "key": "k1", "made_at": "2020-01-01T00:00:00Z"}
        buffer.save_state(self.state, {"backlog": [old], "channel": {"id": "c9"}})
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)
        self.assertEqual(fake.calls, ["create"])
        fake = FakeBuffer()
        self.assertEqual(self.run_buffer(fake), 0)                  # the same pending.json again: already sent
        self.assertEqual(fake.calls, [])

    def test_headers(self):
        lim = buffer.parse_limits(HEADERS)
        self.assertEqual(lim[2592000], {"remaining": 900, "reset_in": 1296000, "quota": 1000})
        self.assertEqual(lim[900]["remaining"], 140)


if __name__ == "__main__":
    unittest.main()
