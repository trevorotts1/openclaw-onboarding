#!/usr/bin/env python3
"""test_run_publishing_cycle.py — F20: Skill 35 publishing cycle tests rebuilt
around the AGREED contract (F04 staging-not-review + F08 execution modes +
F12 canonical ingest + F13 writeback proof), offline, fake transports.

The OLD suite here expected --execute/--enqueue behavior the argument parser
never implemented (an isolated --execute exits 2), accepted FABRICATED
"skill35-" post ids as live success, and tested incomplete receipt cases
inconsistent with the current verification. F20 replaces it with the real
contract:

  Staging (default invocation, required args):
    - exits 0, state=queued in the durable dispatch record, NEVER review/done,
      no publish receipts (staging is not posting proof).
  Unknown flags (--execute, --enqueue, anything else) exit 2.

  --verify-receipts (the post-cycle deterministic QC gate):
    - empty cycle (nothing connected/planned/created) is a clean pass;
    - connected/planned but 0 created -> exit 6 (0 posts is an ERROR, never
      silent success);
    - when posts were created, counters alone are NOT proof: every post needs
      a non-empty remote post_id + url, and at least one post must carry a
      read-back record (readback.id == post_id) proving it was read back from
      the remote platform. FABRICATED ids without a read-back are refused.

  Consumer removal (F04/F03): with every worker stopped the cycle stays
  queued + overdue; --status reports overdue, never review/done.

  Review gate (F04): --mark-review refused while queued and until EVERY phase
  is complete with verified sha256 artifact hashes (artifacts-before-review).

Run:  python3 35-social-media-planner/scripts/test_run_publishing_cycle.py
Exit: 0 = contract holds.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "run-publishing-cycle.sh"
TEST_PLATFORMS = "linkedin,x,instagram"

# Offline stub: the fixture credential hits the LIVE GHL preflight; the stub
# refuses leadconnectorhq.com (the transient-warn path — the cycle continues)
# so NO network call ever leaves the machine. Forward everything else to the
# real curl.
_CURL_STUB = """#!/bin/sh
for a in "$@"; do
  case "$a" in
    *leadconnectorhq.com*) exit 7 ;;
  esac
done
exec {real_curl} "$@"
"""


def _make_oc(home):
    """Fixture $HOME with the Skill 35 prerequisite files (offline) and a curl
    stub that refuses the live GHL preflight."""
    oc = Path(home) / ".openclaw"
    (oc / "secrets").mkdir(parents=True, exist_ok=True)
    (oc / "config").mkdir(parents=True, exist_ok=True)
    for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
        (oc / f).write_text(f"fixture {f}")
    (oc / "secrets" / ".env").write_text(
        "GOHIGHLEVEL_API_KEY=test-key\nGOHIGHLEVEL_LOCATION_ID=test-loc\n")
    (oc / "openclaw.json").write_text('{"agents": {"list": []}}\n')
    bindir = Path(home) / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "curl"
    stub.write_text(_CURL_STUB.format(real_curl=shutil.which("curl") or "/usr/bin/curl"))
    stub.chmod(0o755)


def _run(home, workdir, *args):
    """Run the cycle script with an isolated HOME and no CC env — the GHL live
    preflight is refused by the curl stub (transient-warn), never a live call."""
    env = os.environ.copy()
    env["HOME"] = home
    env["PATH"] = "%s:/usr/bin:/bin" % (Path(home) / "bin")
    for k in ("MC_API_TOKEN", "MISSION_CONTROL_URL", "SKILL35_LIVE_PREFLIGHT",
              "CC_WEBHOOK_SECRET", "WEBHOOK_SECRET"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(SCRIPT), "--topic", "F20 Test", "--platforms", TEST_PLATFORMS,
         "--workdir", workdir, *args],
        capture_output=True, text=True, timeout=120, env=env)


class StagingTests(unittest.TestCase):
    """The agreed F04 contract: staging is QUEUED, not execution."""

    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)

    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()

    def test_staging_exits_zero_and_is_queued(self):
        p = _run(self.ht, self.wt)
        self.assertEqual(p.returncode, 0, f"STDERR: {p.stderr}")
        d = json.loads((Path(self.wt) / "working" / "dispatch.json").read_text())
        self.assertEqual(d["state"], "queued")
        self.assertEqual(d["accepted_execution"], None)
        self.assertEqual(d["completion_receipt"], None)

    def test_staging_never_writes_publish_receipts(self):
        _run(self.ht, self.wt)
        self.assertFalse((Path(self.wt) / "publish-receipts.json").is_file(),
                         "staging wrote publish receipts — staging is not posting proof")

    def test_unknown_flags_exit_two(self):
        # The old suite asserted --execute exits 0 and --enqueue exits 7; the
        # parser implements NEITHER flag, and an unknown argument must exit 2.
        self.assertEqual(_run(self.ht, self.wt, "--execute").returncode, 2)
        self.assertEqual(_run(self.ht, self.wt, "--enqueue").returncode, 2)

    def test_consumer_completes_then_verify(self):
        # The agreed consume path: a worker acks, phases complete with verified
        # artifact hashes, review happens — and the POST-CYCLE receipts gate
        # accepts a receipt with a real remote post id + a read-back record.
        _run(self.ht, self.wt)
        ack = _run(self.ht, self.wt, "--ack-execution", "--worker-id", "w1")
        self.assertEqual(ack.returncode, 0, ack.stderr)
        for phase in range(1, 6):
            pdir = Path(self.wt) / "working" / f"phase-{phase}" / "artifacts"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"artifact-{phase}.txt").write_text(f"phase {phase} output")
            cp = _run(self.ht, self.wt, "--complete-phase", str(phase),
                      "--worker-id", "w1")
            self.assertEqual(cp.returncode, 0, cp.stderr)
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 0, mr.stderr)
        state = json.loads((Path(self.wt) / "working" / "dispatch.json").read_text())["state"]
        self.assertEqual(state, "review")
        # A complete receipt (post_ids + urls + read-back) passes the QC gate.
        receipt = Path(self.wt) / "publish-receipts.json"
        receipt.write_text(json.dumps({
            "connected_accounts": 3, "planned_posts": 3, "created_posts": 3,
            "posts": [{"platform": "linkedin", "post_id": "r-li", "url": "u-li",
                       "readback": {"id": "r-li"}},
                      {"platform": "x", "post_id": "r-x", "url": "u-x",
                       "readback": {"id": "r-x"}},
                      {"platform": "instagram", "post_id": "r-ig", "url": "u-ig"}]}))
        v = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", self.wt],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(v.returncode, 0, v.stderr)


class ProofTests(unittest.TestCase):
    """verify-receipts: fabricated success is refused; read-back is required."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.td = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def _w(self, d):
        p = self.td / "publish-receipts.json"; p.write_text(json.dumps(d)); return p

    def _verify(self, path):
        return subprocess.run(["bash", str(SCRIPT), "--verify-receipts", str(path)],
                              capture_output=True, text=True, timeout=60)

    def test_empty_cycle_passes(self):
        # A genuine no-op cycle (nothing connected/planned/created) is a pass.
        r = self._w({"connected_accounts": 0, "planned_posts": 0, "created_posts": 0,
                     "posts": []})
        self.assertEqual(self._verify(r).returncode, 0)

    def test_connected_zero_created_is_fraud(self):
        r = self._w({"connected_accounts": 3, "planned_posts": 3, "created_posts": 0,
                     "posts": []})
        p = self._verify(r)
        self.assertEqual(p.returncode, 6)
        self.assertIn("0 posts created", p.stderr)

    def test_planned_zero_created_is_fraud(self):
        r = self._w({"connected_accounts": 0, "planned_posts": 2, "created_posts": 0,
                     "posts": []})
        p = self._verify(r)
        self.assertEqual(p.returncode, 6)

    def test_counter_only_receipt_is_fraud(self):
        # created_posts=3 with an EMPTY posts array — three numbers from the
        # same pipeline prove nothing. F20: this must FAIL, not pass.
        r = self._w({"connected_accounts": 3, "planned_posts": 3, "created_posts": 3,
                     "posts": []})
        p = self._verify(r)
        self.assertEqual(p.returncode, 6)
        self.assertIn("per-post receipt", p.stderr)

    def test_declared_more_than_receipts_is_fraud(self):
        # 3 created but only 1 per-post receipt present.
        r = self._w({"connected_accounts": 3, "planned_posts": 3, "created_posts": 3,
                     "posts": [{"platform": "x", "post_id": "p1", "url": "u",
                                "readback": {"id": "p1"}}]})
        p = self._verify(r)
        self.assertEqual(p.returncode, 6)
        self.assertIn("per-post receipt", p.stderr)

    def test_fabricated_id_without_readback_is_refused(self):
        # The OLD suite accepted any "skill35-" id as live success. A receipt
        # whose posts carry ids/urls but NO read-back record from the remote
        # platform is success DECLARED, not verified — it must fail.
        r = self._w({"connected_accounts": 2, "planned_posts": 2, "created_posts": 2,
                     "posts": [{"platform": "x", "post_id": "skill35-fake-1", "url": "u1"},
                               {"platform": "linkedin", "post_id": "skill35-fake-2", "url": "u2"}]})
        p = self._verify(r)
        self.assertEqual(p.returncode, 6, "fabricated ids accepted as live success")
        self.assertIn("read-back", p.stderr)

    def test_readback_id_mismatch_is_refused(self):
        # A read-back whose id does not match the post_id proves nothing.
        r = self._w({"connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
                     "posts": [{"platform": "x", "post_id": "p1", "url": "u",
                                "readback": {"id": "DIFFERENT"}}]})
        self.assertEqual(self._verify(r).returncode, 6)

    def test_real_readback_passes(self):
        r = self._w({"connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
                     "posts": [{"platform": "x", "post_id": "p1", "url": "u",
                                "readback": {"id": "p1"}}]})
        self.assertEqual(self._verify(r).returncode, 0)

    def test_post_missing_id_or_url_is_refused(self):
        r = self._w({"connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
                     "posts": [{"platform": "x", "post_id": "", "url": "u"}]})
        self.assertEqual(self._verify(r).returncode, 6)
        r2 = self._w({"connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
                      "posts": [{"platform": "x", "post_id": "p", "url": ""}]})
        self.assertEqual(self._verify(r2).returncode, 6)

    def test_missing_file_is_error(self):
        self.assertEqual(self._verify(self.td / "nope.json").returncode, 6)


class ConsumerRemovalTests(unittest.TestCase):
    """F04/F03: workers stopped -> queued + overdue, never review/done."""

    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)

    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()

    def test_stopped_workers_leave_cycle_queued_overdue(self):
        p = _run(self.ht, self.wt)
        self.assertEqual(p.returncode, 0, p.stderr)
        # A long-staged cycle: --status with a 1s overdue window MUST report
        # overdue for a QUEUED cycle with no accepted execution — and NEVER
        # review/done, with no completion receipt. Ensure the queue instant is
        # reliably older than the threshold (clock granularity).
        time.sleep(2)
        st = subprocess.run(
            ["bash", str(SCRIPT), "--status", "--workdir", self.wt,
             "--overdue-after", "1"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(st.returncode, 0, st.stderr)
        out = json.loads(st.stdout)
        self.assertEqual(out["state"], "queued")
        self.assertTrue(out["overdue"], "a long-queued unacked cycle must be OVERDUE")
        self.assertIn("no worker ack", out.get("overdue_reason") or "")
        self.assertEqual(out.get("completion_receipt"), None)

    def test_review_refused_while_queued(self):
        _run(self.ht, self.wt)
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 7, "staging must never be review-eligible")
        self.assertIn("still QUEUED", mr.stderr)

    def test_phase_complete_requires_accepted_execution(self):
        _run(self.ht, self.wt)
        pdir = Path(self.wt) / "working" / "phase-1" / "artifacts"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "artifact-1.txt").write_text("x")
        cp = _run(self.ht, self.wt, "--complete-phase", "1", "--worker-id", "w1")
        self.assertEqual(cp.returncode, 7, "no artifacts count without an accepted ack")
        d = json.loads((Path(self.wt) / "working" / "dispatch.json").read_text())
        self.assertEqual(d["state"], "queued")
        self.assertEqual(d["phases_complete"], [])


class ReviewGateTests(unittest.TestCase):
    """F04: review requires EVERY phase complete with verified artifact hashes."""

    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)
        self.assertEqual(_run(self.ht, self.wt).returncode, 0)
        self.assertEqual(_run(self.ht, self.wt, "--ack-execution",
                              "--worker-id", "w1").returncode, 0)

    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()

    def _complete_all(self, worker="w1"):
        for phase in range(1, 6):
            pdir = Path(self.wt) / "working" / f"phase-{phase}" / "artifacts"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"artifact-{phase}.txt").write_text(f"phase {phase} output")
            cp = _run(self.ht, self.wt, "--complete-phase", str(phase),
                      "--worker-id", worker)
            self.assertEqual(cp.returncode, 0, cp.stderr)

    def test_review_refused_until_every_phase_complete(self):
        for phase in range(1, 5):
            pdir = Path(self.wt) / "working" / f"phase-{phase}" / "artifacts"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"artifact-{phase}.txt").write_text("x")
            _run(self.ht, self.wt, "--complete-phase", str(phase), "--worker-id", "w1")
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 7)
        self.assertIn("phase(s) 5", mr.stderr)

    def test_review_refused_when_artifact_edited_after_hash_recorded(self):
        self._complete_all()
        # Tamper with a verified artifact AFTER its sha256 was recorded.
        p = Path(self.wt) / "working" / "phase-2" / "artifacts" / "artifact-2.txt"
        p.write_text("TAMPERED")
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 7, "review must re-verify recorded hashes")
        self.assertIn("changed after its hash was recorded", mr.stderr)

    def test_review_refused_when_verified_artifact_deleted(self):
        self._complete_all()
        p = Path(self.wt) / "working" / "phase-3" / "artifacts" / "artifact-3.txt"
        p.unlink()
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 7)
        self.assertIn("missing on disk", mr.stderr)

    def test_review_accepted_after_all_phases_verified(self):
        self._complete_all()
        mr = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(mr.returncode, 0, mr.stderr)
        d = json.loads((Path(self.wt) / "working" / "dispatch.json").read_text())
        self.assertEqual(d["state"], "review")
        self.assertTrue(d["review_eligible"])

    def test_ack_on_review_state_refused(self):
        self._complete_all()
        self.assertEqual(_run(self.ht, self.wt, "--mark-review").returncode, 0)
        ack2 = _run(self.ht, self.wt, "--ack-execution", "--worker-id", "w2")
        self.assertEqual(ack2.returncode, 7, "cannot ack a review-state cycle")


class ContractMutationTests(unittest.TestCase):
    """F20 required outcome: the tests DETECT a consumer removed, review marked
    before artifacts, or live verification bypassed. Each test mutates the
    script's guard, proves the suite's observable turns RED, then restores."""

    def setUp(self):
        self.h = tempfile.TemporaryDirectory(); self.ht = self.h.name
        self.w = tempfile.TemporaryDirectory(); self.wt = self.w.name
        _make_oc(self.ht)

    def tearDown(self):
        self.h.cleanup(); self.w.cleanup()

    def _with_mutated(self, mut, fn):
        """mut(script_text)->mutated. Assert bash -n passes, run fn(mutated)
        while the file is swapped, always restore. Returns nothing; fn owns
        assertions (GREEN on the ORIGINAL, RED on the mutation)."""
        bk = SCRIPT.read_text()
        mut = mut(bk)
        self.assertNotEqual(bk, mut, "mutation did not apply")
        try:
            subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, check=True,
                           timeout=30)
            SCRIPT.write_text(mut)
            fn()
        finally:
            SCRIPT.write_text(bk)
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)],
                                        capture_output=True, timeout=30).returncode, 0,
                         "restored script must parse")

    def test_consumer_removal_mutation_is_caught(self):
        # Remove the durable dispatch-record write (the consumer binding).
        # GREEN: staging writes working/dispatch.json (state=queued).
        # RED: with the write removed the suite's queued-state invariant loses
        # its evidence — the test detects a staged cycle with NO durable state.
        assert _run(self.ht, self.wt).returncode == 0
        assert (Path(self.wt) / "working" / "dispatch.json").is_file(), "GREEN"
        w2t = tempfile.TemporaryDirectory(); w2 = w2t.name
        try:
            def _mut(bk):
                start = bk.index("_dispatch_write \\")
                end = bk.index('log "Cycle $RUN_ID staged as QUEUED')
                return bk[:start] + "true  # consumer binding removed\n" + bk[end:]
            def _red():
                self.assertEqual(_run(self.ht, w2).returncode, 0, "staging still exits 0")
                self.assertFalse((Path(w2) / "working" / "dispatch.json").exists(),
                                 "RED: consumer removal leaves no durable dispatch record")
            self._with_mutated(_mut, _red)
        finally:
            w2t.cleanup()
        assert (Path(self.wt) / "working" / "dispatch.json").is_file(), "GREEN revert"

    def test_mark_review_before_artifacts_mutation_is_caught(self):
        # Remove the queued-state refusal from --mark-review. GREEN: marking a
        # never-acked queued cycle is refused (exit 7). RED: it passes — before
        # every phase is complete with verified hashes.
        _run(self.ht, self.wt)
        green = _run(self.ht, self.wt, "--mark-review")
        self.assertEqual(green.returncode, 7, "GREEN: queued cycle cannot reach review")
        def _mut(bk):
            # Remove BOTH guards: the queued-state refusal AND the
            # phases-complete refusal — a review gate that checks neither
            # artifact state nor worker acceptance.
            bk = bk.replace(
                'if state == "queued":\n    fail("--mark-review refused: the cycle is still QUEUED with no accepted worker "\n         "execution — staging is never review-eligible")\n',
                "")
            return bk.replace(
                'if missing:\n    fail("--mark-review refused: phase(s) %s are not recorded complete with verified "\n         "artifact hashes — review requires EVERY phase complete" % ", ".join(missing))\n',
                "")
        def _red():
            self.assertEqual(_run(self.ht, self.wt, "--mark-review").returncode, 0,
                             "RED: review granted before artifacts")
        self._with_mutated(_mut, _red)
        # GREEN revert on a FRESH workdir (the RED run already moved the first
        # one to review; review-state mark is a deduped success).
        w3t = tempfile.TemporaryDirectory()
        try:
            _run(self.ht, w3t.name)
            self.assertEqual(_run(self.ht, w3t.name, "--mark-review").returncode, 7,
                             "GREEN revert")
        finally:
            w3t.cleanup()

    def test_live_verification_bypass_mutation_is_caught(self):
        # Gut the read-back requirement in --verify-receipts. GREEN: fabricated
        # ids without a read-back are refused (exit 6). RED: they pass.
        receipt = {"connected_accounts": 2, "planned_posts": 2, "created_posts": 2,
                   "posts": [{"platform": "x", "post_id": "skill35-fake-1", "url": "u1"},
                             {"platform": "linkedin", "post_id": "skill35-fake-2", "url": "u2"}]}
        td = tempfile.mkdtemp()
        try:
            (Path(td) / "publish-receipts.json").write_text(json.dumps(receipt))
            green = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", td],
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(green.returncode, 6, "GREEN: fabricated ids refused")
            def _mut(bk):
                return bk.replace(
                    'if not readback_ok:\n        sys.stderr.write("[Skill35] QC FAIL: no post carries a read-back record from the remote platform — success was declared, not verified.\\n"); sys.exit(6)\n',
                    "readback_ok = True\n")
            def _red():
                mutated = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", td],
                                         capture_output=True, text=True, timeout=60)
                self.assertEqual(mutated.returncode, 0,
                                 "RED: live verification bypassed, fabricated ids accepted")
            self._with_mutated(_mut, _red)
            post = subprocess.run(["bash", str(SCRIPT), "--verify-receipts", td],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(post.returncode, 6, "GREEN revert")
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
