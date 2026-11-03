"""The server side of the deploy (deploy/server/bin): rsync through the forced-command gate into stage/, then
ff-publish's hard-linked snapshot and symlink switch. Runs the real rsync and rrsync with a stand-in for ssh (no
network, no server); skipped where rsync or rrsync is not installed or deploy/ is not checked out."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "deploy" / "server" / "bin"
RSYNC = shutil.which("rsync")
RRSYNC = shutil.which("rrsync") or ("/usr/bin/rrsync" if os.path.exists("/usr/bin/rrsync") else None)
# the same options as .github/workflows/deploy-server.yml (no -t: unchanged files keep their time and inode)
RSYNC_OPTS = ["-rp", "--checksum", "--delete", "--chmod=D755,F644", "--stats"]

FAKE_SSH = """#!/bin/bash
# stands in for ssh: drops ssh's own options and the host, hands the rest to the gate the way sshd does
while [ $# -gt 0 ]; do
  case "$1" in -l|-p|-i|-o|-F) shift 2 ;; -*) shift ;; *) break ;; esac
done
shift
export SSH_ORIGINAL_COMMAND="$*"
exec "$FF_BIN/ff-deploy-gate"
"""


@unittest.skipUnless(RSYNC and RRSYNC and BIN.is_dir(), "needs rsync, rrsync and deploy/server/bin")
class ServerDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "srv"
        for d in ("stage", "releases", "state"):
            (self.base / d).mkdir(parents=True)
        self.site = self.tmp / "site"
        self.ssh = self.tmp / "fake-ssh"
        self.ssh.write_text(FAKE_SSH)
        self.ssh.chmod(0o755)
        self.env = dict(os.environ, FF_BASE=str(self.base), FF_BIN=str(BIN), FF_RRSYNC=RRSYNC, FF_LOCK_WAIT="5")
        self.make_site(pages=40)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_site(self, pages):
        shutil.rmtree(self.site, ignore_errors=True)
        (self.site / "c" / "amzn").mkdir(parents=True)
        (self.site / "data").mkdir()
        (self.site / "index.html").write_text("<h1>home</h1>")
        (self.site / "about.html").write_text("about")
        (self.site / "c" / "amzn" / "index.html").write_text("amazon")
        (self.site / "data" / "index.json").write_text('{"v": 1}')
        (self.site / ".nojekyll").write_text("")
        (self.site / "_under").mkdir()
        (self.site / "_under" / "x.html").write_text("underscore")
        for i in range(pages):
            (self.site / f"p{i}.html").write_text(f"page {i}")

    def sync(self, extra=(), dest="deploy@server:"):
        return subprocess.run([RSYNC, *RSYNC_OPTS, *extra, "-e", str(self.ssh), f"{self.site}/", dest],
                              env=self.env, capture_output=True, text=True)

    def gate(self, command):
        return subprocess.run([str(BIN / "ff-deploy-gate")], env=dict(self.env, SSH_ORIGINAL_COMMAND=command),
                              capture_output=True, text=True)

    def live(self):
        return self.base / "current"

    def test_sync_and_publish(self):
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.base / "state" / "stage-ok").exists())
        self.assertEqual((self.base / "stage" / "c" / "amzn" / "index.html").read_text(), "amazon")
        self.assertTrue((self.base / "stage" / ".nojekyll").exists())
        self.assertEqual((self.base / "stage" / "_under" / "x.html").read_text(), "underscore")
        mode = stat.S_IMODE((self.base / "stage" / "index.html").stat().st_mode)
        self.assertEqual(mode, 0o644)
        p = self.gate("publish")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.live().is_symlink())
        self.assertEqual(os.readlink(self.live()).split("/")[0], "releases")
        self.assertEqual((self.live() / "about.html").read_text(), "about")
        info = json.loads((self.base / "state" / "last-publish.json").read_text())
        self.assertEqual(info["html"], 44)

    def test_second_deploy_leaves_the_published_snapshot_alone(self):
        self.sync()
        self.gate("publish")
        first = self.live().resolve()
        (self.site / "about.html").write_text("about, changed")
        (self.site / "p0.html").unlink()
        (self.site / "new.html").write_text("new")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Number of regular files transferred: 2", r.stdout)     # only the changed and the new file
        p = self.gate("publish")
        self.assertEqual(p.returncode, 0, p.stderr)
        second = self.live().resolve()
        self.assertNotEqual(first, second)
        self.assertEqual((first / "about.html").read_text(), "about")          # the old snapshot is untouched
        self.assertTrue((first / "p0.html").exists())
        self.assertEqual((second / "about.html").read_text(), "about, changed")
        self.assertFalse((second / "p0.html").exists())
        self.assertEqual((second / "new.html").read_text(), "new")
        # unchanged files are the same file on disk (hard links), changed ones are not
        self.assertEqual((first / "p5.html").stat().st_ino, (second / "p5.html").stat().st_ino)
        self.assertNotEqual((first / "about.html").stat().st_ino, (second / "about.html").stat().st_ino)

    def test_old_snapshots_are_pruned(self):
        for i in range(5):
            (self.site / "index.html").write_text(f"home {i}")
            self.sync()
            self.assertEqual(self.gate("publish").returncode, 0)
        names = sorted(os.listdir(self.base / "releases"))
        self.assertEqual(len(names), 3)
        self.assertIn(self.live().resolve().name, names)
        self.assertEqual((self.live() / "index.html").read_text(), "home 4")

    def test_rollback(self):
        for i in range(3):
            (self.site / "index.html").write_text(f"home {i}")
            self.sync()
            self.gate("publish")
        names = sorted(os.listdir(self.base / "releases"))
        r = subprocess.run([str(BIN / "ff-publish"), "--rollback"], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.live().resolve().name, names[1])
        self.assertEqual((self.live() / "index.html").read_text(), "home 1")
        r = subprocess.run([str(BIN / "ff-publish"), "--rollback", names[2]], env=self.env, capture_output=True, text=True)
        self.assertEqual((self.live() / "index.html").read_text(), "home 2")
        r = subprocess.run([str(BIN / "ff-publish"), "--rollback", "nope"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.gate("--rollback").returncode, 1)              # not something the deploy key can do

    def test_a_much_smaller_site_is_not_published(self):
        self.sync()
        self.gate("publish")
        before = self.live().resolve()
        self.make_site(pages=2)
        self.sync()
        p = self.gate("publish")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not published", p.stderr)
        self.assertEqual(self.live().resolve(), before)
        p = self.gate("publish --allow-shrink")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotEqual(self.live().resolve(), before)

    def test_unfinished_upload_is_not_published(self):
        self.sync()
        self.gate("publish")
        before = self.live().resolve()
        (self.base / "state" / "stage-ok").unlink()                           # as after a broken connection
        p = self.gate("publish")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.live().resolve(), before)

    def test_upload_without_index_is_not_published(self):
        (self.site / "index.html").unlink()
        self.sync()
        p = self.gate("publish")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(self.live().exists())

    def test_the_gate_lets_nothing_else_through(self):
        for cmd in ("ls /", "bash", "rsync --server --sender -logDtpre.iLsfxCIvu . /etc", "publish; echo extra",
                    "status && id", ""):
            r = self.gate(cmd)
            self.assertNotEqual(r.returncode, 0, cmd)

    def test_downloads_are_refused(self):
        self.sync()
        out = self.tmp / "down"
        r = subprocess.run([RSYNC, "-r", "-e", str(self.ssh), "deploy@server:", f"{out}/"], env=self.env,
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((out / "index.html").exists())

    def test_uploads_stay_inside_stage(self):
        r = self.sync(dest="deploy@server:../state/")
        self.assertFalse((self.base / "state" / "index.html").exists())
        r = self.sync(dest="deploy@server:/tmp/")
        self.assertFalse((self.base / "state" / "index.html").exists())
        self.assertFalse(Path("/tmp/p1.html").exists() and Path("/tmp/p1.html").read_text() == "page 1")

    def test_symlinks_are_never_published(self):
        os.symlink("/etc/passwd", self.site / "passwd.html")
        os.symlink("/etc", self.site / "etc")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.gate("publish").returncode, 0)
        self.assertFalse(os.path.lexists(self.live() / "passwd.html"))
        self.assertFalse(os.path.lexists(self.live() / "etc"))

    def test_status(self):
        self.sync()
        self.gate("publish")
        r = self.gate("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads(r.stdout)
        self.assertEqual(s["release"], self.live().resolve().name)
        self.assertEqual(s["pages"], 44)
        self.assertGreater(s["disk"]["total_gb"], 0)
        self.assertIn("web", s)


if __name__ == "__main__":
    unittest.main()
