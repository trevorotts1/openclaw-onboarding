#!/usr/bin/env python3
"""test_run_publishing_cycle.py — U127: Skill 35 publishing cycle worker,
enqueue+completion flow, and per-post proof verification."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "run-publishing-cycle.sh"
TEST_PLATFORMS = "linkedin,x,instagram"

def _make_oc(home):
    oc = Path(home) / ".openclaw"
    (oc / "secrets").mkdir(parents=True, exist_ok=True)
    (oc / "config").mkdir(parents=True, exist_ok=True)
    for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
        (oc / f).write_text(f"fixture {f}")
    (oc / "secrets" / ".env").write_text("GOHIGHLEVEL_API_KEY=test-key\nGOHIGHLEVEL_LOCATION_ID=test-loc\n")
    (oc / "openclaw.json").write_text('{"agents": {"list": []}}\n')

def _run(home, workdir, *args):
    env = os.environ.copy()
    env["HOME"] = home
    for k in ("MC_API_TOKEN", "MISSION_CONTROL_URL", "SKILL35_LIVE_PREFLIGHT"):
        env.pop(k, None)
    return subprocess.run(["bash", str(SCRIPT), "--topic", "U127 Test", "--platforms", TEST_PLATFORMS, "--workdir", workdir, *args], capture_output=True, text=True, timeout=60, env=env)

class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)
    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()
    def test_exits_zero(self):
        p = _run(self.ht, self.wt, "--execute")
        self.assertEqual(p.returncode, 0, f"STDERR: {p.stderr}")
    def test_creates_receipts(self):
        _run(self.ht, self.wt, "--execute")
        self.assertTrue((Path(self.wt) / "publish-receipts.json").is_file())
    def test_one_entry_per_platform(self):
        _run(self.ht, self.wt, "--execute")
        d = json.loads((Path(self.wt) / "publish-receipts.json").read_text())
        self.assertEqual(len(d["posts"]), len(TEST_PLATFORMS.split(",")))
    def test_posts_have_ids(self):
        _run(self.ht, self.wt, "--execute")
        d = json.loads((Path(self.wt) / "publish-receipts.json").read_text())
        for p in d["posts"]:
            self.assertTrue(p["post_id"].startswith("skill35-"))
    def test_journal_has_entries(self):
        _run(self.ht, self.wt, "--execute")
        j = (Path(self.wt) / "journal.log").read_text()
        self.assertIn("per-post receipt", j)

class ProofTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.td = Path(self.t.name)
    def tearDown(self):
        self.t.cleanup()
    def _w(self, d):
        p = self.td / "publish-receipts.json"; p.write_text(json.dumps(d)); return p
    def test_empty_ok(self):
        r = self._w({"connected_accounts": 0, "planned_posts": 0, "created_posts": 0, "posts": []})
        self.assertEqual(subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(r)], capture_output=True, text=True, timeout=30).returncode, 0)
    def test_connected_zero_created_fraud(self):
        r = self._w({"connected_accounts": 3, "planned_posts": 3, "created_posts": 0, "posts": []})
        p = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(r)], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 6)
        self.assertIn("0 posts created", p.stderr)
    def test_planned_zero_created_fraud(self):
        r = self._w({"connected_accounts": 2, "planned_posts": 2, "created_posts": 0, "posts": []})
        self.assertEqual(subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(r)], capture_output=True, text=True, timeout=30).returncode, 6)
    def test_partial_warns(self):
        r = self._w({"connected_accounts": 3, "planned_posts": 3, "created_posts": 2, "posts": [{"platform": "linkedin", "post_id": "p1", "url": "u", "tier": 0}]})
        p = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(r)], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertIn("partial publish", p.stderr)
    def test_missing_file(self):
        self.assertEqual(subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(self.td / "nope.json")], capture_output=True, text=True, timeout=30).returncode, 6)

class EnqueueTests(unittest.TestCase):
    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)
    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()
    def test_default_exits_seven(self):
        p = _run(self.ht, self.wt)
        self.assertEqual(p.returncode, 7, f"got {p.returncode}\nSTDERR: {p.stderr}")
    def test_enqueue_flag_exits_seven(self):
        self.assertEqual(_run(self.ht, self.wt, "--enqueue").returncode, 7)
    def test_writes_handoff(self):
        _run(self.ht, self.wt)
        c = (Path(self.wt) / "READY-FOR-ORCHESTRATOR").read_text()
        self.assertIn("ENQUEUED", c)
    def test_no_receipts_in_enqueue(self):
        _run(self.ht, self.wt)
        self.assertFalse((Path(self.wt) / "publish-receipts.json").is_file())
    def test_consumer_completes_then_verify(self):
        _run(self.ht, self.wt)
        (Path(self.wt) / "publish-receipts.json").write_text(json.dumps({"connected_accounts": 3, "planned_posts": 3, "created_posts": 3, "posts": [{"platform": "x", "post_id": "r1", "url": "u", "tier": 1}]}))
        p = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", self.wt], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, f"STDERR: {p.stderr}")

class MutationTests(unittest.TestCase):
    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)
    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()
    def test_execute_exit_mutation(self):
        self.assertEqual(_run(self.ht, self.wt, "--execute").returncode, 0, "GREEN")
        bk = SCRIPT.read_text()
        mut = bk.replace("exit 0", "exit 99", 1)
        self.assertNotEqual(bk, mut)
        try:
            SCRIPT.write_text(mut)
            subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, check=True, timeout=10)
            w2 = tempfile.mkdtemp()
            try:
                self.assertNotEqual(_run(self.ht, w2, "--execute").returncode, 0, "RED")
            finally:
                import shutil; shutil.rmtree(w2, ignore_errors=True)
        finally:
            SCRIPT.write_text(bk)
        self.assertEqual(_run(self.ht, self.wt, "--execute").returncode, 0, "GREEN revert")
    def test_enqueue_exit_mutation(self):
        self.assertEqual(_run(self.ht, self.wt).returncode, 7, "GREEN")
        bk = SCRIPT.read_text()
        pos = bk.rfind("exit 7")
        self.assertGreater(pos, 0)
        mut = bk[:pos] + "exit 0" + bk[pos + 6:]
        self.assertNotEqual(bk, mut)
        try:
            SCRIPT.write_text(mut)
            subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, check=True, timeout=10)
            w2 = tempfile.mkdtemp()
            try:
                self.assertEqual(_run(self.ht, w2).returncode, 0, "RED: exit 7->0")
            finally:
                import shutil; shutil.rmtree(w2, ignore_errors=True)
        finally:
            SCRIPT.write_text(bk)
        self.assertEqual(_run(self.ht, self.wt).returncode, 7, "GREEN revert")

if __name__ == "__main__":
    unittest.main(verbosity=2)
