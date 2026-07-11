#!/usr/bin/env python3
"""Unit tests for the per-box fleet ledger + post-fan-out validation harness (AUD-58).

These lock down the ONE property the whole item exists for:

    a fan-out that reports green on a broken box is the failure mode this closes.

So every test below is really the same test asked a different way — "can this
thing be made to say PASS when it should not?"  Unparseable output, a probe that
never ran, an ssh that timed out, an expectation nobody declared, a required
check that was skipped, a corrupt ledger row, a stale repo stamp, a missing
runRetries row: every one of them must come back FAIL or UNKNOWN, never PASS.

Run:
    python3 tests/unit/fleet-ledger-harness.test.py
    pytest  tests/unit/fleet-ledger-harness.test.py
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
sys.path.insert(0, str(_SHARED))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load("fleet_ledger")
H = _load("fleet_validation_harness")


# ── fixture helpers ───────────────────────────────────────────────────────────

HEALTHY_TOKEN_JSON = json.dumps({
    # NEEDS_BLOCK (exit 3) is the HEALTHY verdict for MC_API_TOKEN — it is not a
    # model-provider key, so no models.providers block will ever reference it.
    "verdict": "NEEDS_BLOCK",
    "where_found": ["~/.openclaw/secrets/.env"],
    "live_env_checked": True,
})

ABSENT_TOKEN_JSON = json.dumps({
    "verdict": "GENUINELY-ABSENT",
    "where_found": [],
    "live_env_checked": True,
})

EXPECTATIONS = {
    "repo_version": "v19.44.0",
    "repo_sha": "002f8333aaaabbbbccccddddeeeeffff00001111",
    "openclaw_min_version": "2026.5.22",
    "run_retries_max": 3,
    "writeback_url": "http://127.0.0.1:4000/api/tasks/ingest",
}


def healthy_probes() -> dict:
    return {
        H.PROBE_TOKEN: {"rc": 3, "stdout": HEALTHY_TOKEN_JSON},          # exit 3 = NEEDS_BLOCK = healthy
        H.PROBE_WRITEBACK: {"rc": 0, "stdout": "401"},
        H.PROBE_BROWSER: {"rc": 0, "stdout": "Agent Browser preflight: ALL CHECKS PASS"},
        H.PROBE_VERSION: {"rc": 0, "stdout": "2026.5.22"},
        H.PROBE_RUN_RETRIES: {"rc": 0, "stdout": "3"},
        H.PROBE_STAMP: {"rc": 0, "stdout": f"{EXPECTATIONS['repo_version']}\n{EXPECTATIONS['repo_sha']}"},
    }


def fixture_for(n: int, broken: dict | None = None) -> dict:
    """n healthy boxes; `broken` maps box-name -> probe overrides."""
    boxes = {}
    for i in range(1, n + 1):
        boxes[f"box-{i:02d}"] = {"probes": healthy_probes()}
    for name, overrides in (broken or {}).items():
        probes = healthy_probes()
        for pid, val in overrides.items():
            if val is None:
                probes.pop(pid, None)      # probe returns nothing at all
            else:
                probes[pid] = val
        boxes[name] = {"probes": probes}
    return {"boxes": boxes}


def R(rc=0, stdout="", stderr="", error=""):
    return H.ProbeResult(rc, stdout, stderr, error)


class LedgerRootMixin(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fleet-ledger-test.")
        self.sweep = "sweep-" + uuid.uuid4().hex[:8]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ── 1. the ledger ─────────────────────────────────────────────────────────────

class TestLedger(LedgerRootMixin):

    def test_canonical_path_is_root_sweep_box_json(self):
        p = L.ledger_path("my-sweep", "box-01", self.root)
        self.assertEqual(p, Path(self.root) / "my-sweep" / "box-01.json")

    def test_default_ledger_root_is_tmp(self):
        # The doctrine path is /tmp/<sweep>/<box>.json — prove the default, don't assume it.
        self.assertEqual(str(L.ledger_path("s", "b")), "/tmp/s/b.json")

    def test_path_traversal_in_box_name_is_refused(self):
        for bad in ("../etc/passwd", "a/b", "", "." * 80):
            with self.assertRaises(L.LedgerError):
                L.ledger_path("s", bad, self.root)

    def test_invalid_status_raises_rather_than_silently_passing(self):
        with self.assertRaises(L.LedgerError):
            L.record_check(self.sweep, "box-01", "c", "GREENISH", root=self.root)

    def test_finalize_fails_closed_when_a_required_check_never_ran(self):
        L.record_check(self.sweep, "box-01", H.CHECK_TOKEN, L.PASS, root=self.root)
        row = L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        self.assertEqual(row["status"], L.FAIL)
        self.assertEqual(row["checks"][H.CHECK_BROWSER]["status"], L.FAIL)
        self.assertIn("NEVER RAN", row["checks"][H.CHECK_BROWSER]["reason"])

    def test_finalize_passes_only_when_every_required_check_passes(self):
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root)
        row = L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        self.assertEqual(row["status"], L.PASS)
        self.assertEqual(row["attempts"], 1)

    def test_unknown_never_becomes_green(self):
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root)
        L.record_check(self.sweep, "box-01", H.CHECK_BROWSER, L.UNKNOWN, "ssh timed out", root=self.root)
        row = L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        self.assertEqual(row["status"], L.UNKNOWN)
        self.assertNotEqual(L.exit_code_for(row["status"]), 0)

    def test_fail_outranks_unknown(self):
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root)
        L.record_check(self.sweep, "box-01", H.CHECK_BROWSER, L.UNKNOWN, root=self.root)
        L.record_check(self.sweep, "box-01", H.CHECK_TOKEN, L.FAIL, root=self.root)
        self.assertEqual(L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)["status"], L.FAIL)

    def test_history_is_appended_across_attempts(self):
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.FAIL, "boom", root=self.root)
        L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root)
        row = L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        self.assertEqual(row["attempts"], 2)
        self.assertEqual([h["status"] for h in row["history"]], [L.FAIL, L.PASS])

    def test_ledger_persists_across_processes(self):
        L.record_check(self.sweep, "box-01", H.CHECK_TOKEN, L.PASS, "ok", root=self.root)
        again = _load("fleet_ledger")     # fresh module object == fresh process, same disk
        row = again.load_row(self.sweep, "box-01", self.root)
        self.assertEqual(row["checks"][H.CHECK_TOKEN]["status"], L.PASS)

    def test_corrupt_row_is_a_FAIL_not_a_shrug(self):
        p = L.ledger_path(self.sweep, "box-01", self.root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"schema": "fleet-ledger/v1", "trunca', encoding="utf-8")
        row = L.load_row(self.sweep, "box-01", self.root)
        self.assertEqual(row["status"], L.FAIL)
        self.assertIn("CORRUPT", row["reasons"][0])

    def test_resume_skips_only_a_PASS_under_the_same_expectations(self):
        esha = L.expectations_sha(EXPECTATIONS)
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root, expect_sha=esha)
        row = L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root, esha)
        self.assertTrue(L.should_skip(row, esha))
        # change ONE expectation -> the cached PASS is worthless
        other = L.expectations_sha({**EXPECTATIONS, "repo_sha": "deadbeef" * 5})
        self.assertFalse(L.should_skip(row, other))

    def test_rollup_counts_a_box_that_never_reported_as_FAIL(self):
        for c in H.REQUIRED_CHECKS:
            L.record_check(self.sweep, "box-01", c, L.PASS, root=self.root)
        L.finalize(self.sweep, "box-01", H.REQUIRED_CHECKS, self.root)
        doc = L.rollup(self.sweep, self.root, expected_boxes=["box-01", "box-02"])
        self.assertEqual(doc["verdict"], L.FAIL)
        self.assertEqual(doc["counts"][L.FAIL], 1)
        self.assertIn("NO LEDGER ROW", doc["boxes"]["box-02"]["reasons"][0])

    def test_rollup_of_zero_boxes_is_FAIL_not_PASS(self):
        doc = L.rollup(self.sweep, self.root)
        self.assertEqual(doc["verdict"], L.FAIL)
        self.assertEqual(L.exit_code_for(doc["verdict"]), 2)

    def test_finalize_cli_refuses_an_empty_required_list(self):
        rc = L._main(["finalize", "--sweep-id", self.sweep, "--box", "box-01",
                      "--ledger-root", self.root])
        self.assertEqual(rc, 1)     # fatal — finalizing with no required checks is fail-open


# ── 2. the five checks, each interrogated for fail-open ───────────────────────

class TestChecks(unittest.TestCase):

    # 1 — MC_API_TOKEN store
    def test_token_store_healthy_needs_block_is_PASS_despite_exit_3(self):
        oc = H.check_token_store(R(3, HEALTHY_TOKEN_JSON))
        self.assertEqual(oc.status, L.PASS)
        self.assertEqual(oc.observed["stores_found"], 1)

    def test_token_store_absent_is_FAIL(self):
        oc = H.check_token_store(R(1, ABSENT_TOKEN_JSON))
        self.assertEqual(oc.status, L.FAIL)
        self.assertIn("UNREACHABLE", oc.reason)

    def test_token_store_unparseable_output_is_FAIL_not_PASS(self):
        self.assertEqual(H.check_token_store(R(0, "<html>504 gateway</html>")).status, L.FAIL)

    def test_token_store_empty_where_found_is_FAIL_even_if_verdict_looks_ok(self):
        blob = json.dumps({"verdict": "NEEDS_BLOCK", "where_found": [], "live_env_checked": True})
        self.assertEqual(H.check_token_store(R(0, blob)).status, L.FAIL)

    def test_token_store_probe_that_never_ran_is_FAIL(self):
        self.assertEqual(H.check_token_store(R(127, "", "[sim] no canned response")).status, L.FAIL)

    def test_token_store_transport_failure_is_UNKNOWN_never_PASS(self):
        oc = H.check_token_store(R(255, error="ssh transport failure"))
        self.assertEqual(oc.status, L.UNKNOWN)

    def test_token_value_is_never_requested_by_the_probe_command(self):
        cmds = H.probe_commands("/repo", "http://x/api")
        # the token probe asks for a VERDICT; it must not cat/grep/echo a secret store
        tok = cmds[H.PROBE_TOKEN]
        self.assertIn("check-credential.sh MC_API_TOKEN --json", tok)
        for banned in ("cat ", "grep ", "echo $", "printf %s \"$MC_API_TOKEN"):
            self.assertNotIn(banned, tok)
        # and the default write-back probe sends NO bearer -> it cannot mutate a live box
        self.assertNotIn("Authorization", cmds[H.PROBE_WRITEBACK])
        with_bearer = H.probe_commands("/repo", "http://x/api", send_bearer=True)[H.PROBE_WRITEBACK]
        self.assertIn('Bearer ${MC_API_TOKEN:-}', with_bearer)   # expanded on the BOX, never here

    # 2 — write-back probe
    def test_writeback_2xx_and_401_are_PASS(self):
        for code in ("200", "201", "204", "299", "401"):
            self.assertEqual(H.check_writeback(R(0, code)).status, L.PASS, code)

    def test_writeback_everything_else_is_FAIL(self):
        for code in ("000", "301", "403", "404", "409", "500", "502", "503"):
            oc = H.check_writeback(R(0, code))
            self.assertEqual(oc.status, L.FAIL, code)

    def test_writeback_non_numeric_is_FAIL(self):
        self.assertEqual(H.check_writeback(R(0, "curl: (7) Failed to connect")).status, L.FAIL)
        self.assertEqual(H.check_writeback(R(0, "")).status, L.FAIL)

    def test_writeback_unauthenticated_2xx_is_flagged_as_auth_not_enforced(self):
        oc = H.check_writeback(R(0, "200"), sent_bearer=False)
        self.assertEqual(oc.status, L.PASS)                       # spec: 2xx is a PASS
        self.assertFalse(oc.observed["auth_enforced"])            # ...but the operator is TOLD
        self.assertIn("NOT enforcing auth", oc.reason)

    # 3 — browser probe
    def test_browser_rc0_with_marker_is_PASS(self):
        self.assertEqual(H.check_browser(R(0, "Agent Browser preflight: ALL CHECKS PASS")).status, L.PASS)

    def test_browser_failure_is_FAIL(self):
        self.assertEqual(H.check_browser(R(1, "", "CDP probe FAILED")).status, L.FAIL)

    def test_browser_rc0_with_no_marker_is_UNKNOWN_not_PASS(self):
        # rc=0 + silence is the exact shape of a fail-open. Refuse it.
        self.assertEqual(H.check_browser(R(0, "")).status, L.UNKNOWN)

    # 4 — openclaw --version + the runRetries ceiling row
    def test_ceiling_healthy_is_PASS(self):
        oc = H.check_ceiling(R(0, "2026.5.22"), R(0, "3"), "2026.5.22", 3)
        self.assertEqual(oc.status, L.PASS)
        self.assertEqual(oc.observed["run_retries"], 3)

    def test_ceiling_absent_runRetries_row_is_FAIL(self):
        oc = H.check_ceiling(R(0, "2026.5.22"), R(0, "ABSENT"), "2026.5.22", 3)
        self.assertEqual(oc.status, L.FAIL)
        self.assertIn("ABSENT", oc.reason)

    def test_ceiling_over_ceiling_is_FAIL(self):
        self.assertEqual(H.check_ceiling(R(0, "2026.5.22"), R(0, "9"), "2026.5.22", 3).status, L.FAIL)

    def test_ceiling_below_min_openclaw_version_is_FAIL(self):
        oc = H.check_ceiling(R(0, "2026.4.1"), R(0, "3"), "2026.5.22", 3)
        self.assertEqual(oc.status, L.FAIL)
        self.assertIn("BELOW", oc.reason)

    def test_ceiling_missing_version_output_is_FAIL(self):
        self.assertEqual(H.check_ceiling(R(0, ""), R(0, "3"), "2026.5.22", 3).status, L.FAIL)

    def test_ceiling_with_an_undeclared_expectation_is_FAIL(self):
        # A gate with no expectation cannot fail -> it must not be allowed to pass either.
        self.assertEqual(H.check_ceiling(R(0, "2026.5.22"), R(0, "3"), None, None).status, L.FAIL)
        self.assertEqual(H.check_ceiling(R(0, "2026.5.22"), R(0, "3"), "2026.5.22", None).status, L.FAIL)

    # 5 — repo stamp (the stale-checkout / downgrade detector)
    def test_stamp_match_is_PASS(self):
        out = f"{EXPECTATIONS['repo_version']}\n{EXPECTATIONS['repo_sha']}"
        self.assertEqual(H.check_repo_stamp(R(0, out), EXPECTATIONS["repo_version"],
                                            EXPECTATIONS["repo_sha"]).status, L.PASS)

    def test_stamp_older_version_is_FAIL_downgrade(self):
        out = f"v19.20.0\n{EXPECTATIONS['repo_sha']}"
        oc = H.check_repo_stamp(R(0, out), EXPECTATIONS["repo_version"], EXPECTATIONS["repo_sha"])
        self.assertEqual(oc.status, L.FAIL)
        self.assertIn("did not take the roll", oc.reason)

    def test_stamp_same_version_different_sha_is_FAIL(self):
        out = f"{EXPECTATIONS['repo_version']}\n" + "f" * 40
        oc = H.check_repo_stamp(R(0, out), EXPECTATIONS["repo_version"], EXPECTATIONS["repo_sha"])
        self.assertEqual(oc.status, L.FAIL)
        self.assertIn("DIFFERENT code", oc.reason)

    def test_stamp_undeclared_expectation_is_FAIL(self):
        self.assertEqual(H.check_repo_stamp(R(0, "v19.44.0\nabc"), "", "").status, L.FAIL)

    def test_stamp_unreadable_is_FAIL(self):
        self.assertEqual(H.check_repo_stamp(R(1, ""), EXPECTATIONS["repo_version"],
                                            EXPECTATIONS["repo_sha"]).status, L.FAIL)

    # secret hygiene
    def test_scrub_redacts_secret_shaped_strings(self):
        self.assertNotIn("pit-", H._scrub("token pit-abcdef123456 leaked"))
        self.assertNotIn("sk-", H._scrub("sk-livekey"))
        self.assertIn("[REDACTED]", H._scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"))


# ── 3. the sweep — including the ACCEPTANCE TEST ─────────────────────────────

class TestSweep(LedgerRootMixin):

    def _run(self, fixture: dict, boxes: list, extra: list | None = None, exp: dict | None = None) -> int:
        fx = Path(self.root) / "fixture.json"
        fx.write_text(json.dumps(fixture), encoding="utf-8")
        bx = Path(self.root) / "boxes.json"
        bx.write_text(json.dumps([{"name": b, "ssh_target": f"u@{b}"} for b in boxes]), encoding="utf-8")
        ex = Path(self.root) / "expectations.json"
        ex.write_text(json.dumps(exp if exp is not None else EXPECTATIONS), encoding="utf-8")
        argv = ["--sweep-id", self.sweep, "--boxes-file", str(bx), "--expectations", str(ex),
                "--backend", "sim", "--sim-fixture", str(fx), "--ledger-root", self.root,
                "--max-parallel", "8"]
        return H.main(argv + (extra or []))

    def test_ACCEPTANCE_20_box_fanout_writes_20_ledger_files(self):
        boxes = [f"box-{i:02d}" for i in range(1, 21)]
        rc = self._run(fixture_for(20), boxes)
        self.assertEqual(rc, 0)
        written = sorted(p.name for p in L.sweep_dir(self.sweep, self.root).glob("*.json")
                         if not p.name.startswith("_"))
        self.assertEqual(len(written), 20, written)
        self.assertEqual(written, sorted(f"{b}.json" for b in boxes))
        for b in boxes:
            row = L.load_row(self.sweep, b, self.root)
            self.assertEqual(row["status"], L.PASS, b)
            self.assertEqual(sorted(row["checks"]), sorted(H.REQUIRED_CHECKS))
        self.assertEqual(L.rollup(self.sweep, self.root)["verdict"], L.PASS)

    def test_ACCEPTANCE_one_broken_box_fails_the_whole_wave_loudly(self):
        boxes = [f"box-{i:02d}" for i in range(1, 21)]
        # box-07's MC_API_TOKEN store is UNREACHABLE — the deliberately-broken box.
        fx = fixture_for(20, broken={"box-07": {H.PROBE_TOKEN: {"rc": 1, "stdout": ABSENT_TOKEN_JSON}}})
        rc = self._run(fx, boxes)
        self.assertEqual(rc, 2, "a broken box MUST make the sweep exit non-zero")
        self.assertEqual(len(list(L.sweep_dir(self.sweep, self.root).glob("box-*.json"))), 20)
        bad = L.load_row(self.sweep, "box-07", self.root)
        self.assertEqual(bad["status"], L.FAIL)
        self.assertEqual(bad["checks"][H.CHECK_TOKEN]["status"], L.FAIL)
        self.assertIn("UNREACHABLE", bad["reasons"][0])
        for b in boxes:
            if b != "box-07":
                self.assertEqual(L.load_row(self.sweep, b, self.root)["status"], L.PASS, b)
        doc = json.loads(L.sweep_rollup_path(self.sweep, self.root).read_text())
        self.assertEqual(doc["verdict"], L.FAIL)
        self.assertEqual(doc["counts"][L.PASS], 19)
        self.assertEqual(doc["counts"][L.FAIL], 1)

    def test_each_of_the_five_checks_can_independently_fail_the_wave(self):
        breaks = {
            H.PROBE_TOKEN: {"rc": 1, "stdout": ABSENT_TOKEN_JSON},
            H.PROBE_WRITEBACK: {"rc": 0, "stdout": "500"},
            H.PROBE_BROWSER: {"rc": 1, "stdout": "CDP probe FAILED"},
            H.PROBE_RUN_RETRIES: {"rc": 0, "stdout": "ABSENT"},
            H.PROBE_STAMP: {"rc": 0, "stdout": "v19.20.0\n" + "a" * 40},
        }
        for pid, override in breaks.items():
            self.sweep = "sweep-" + uuid.uuid4().hex[:8]
            rc = self._run(fixture_for(2, broken={"box-02": {pid: override}}), ["box-01", "box-02"])
            self.assertEqual(rc, 2, f"breaking {pid} must fail the wave")
            self.assertEqual(L.load_row(self.sweep, "box-02", self.root)["status"], L.FAIL, pid)
            self.assertEqual(L.load_row(self.sweep, "box-01", self.root)["status"], L.PASS, pid)

    def test_a_silent_box_that_answers_nothing_is_FAIL_not_PASS(self):
        # every probe missing from the fixture = a box that answered nothing at all
        fx = {"boxes": {"box-01": {"probes": healthy_probes()}, "box-02": {"probes": {}}}}
        rc = self._run(fx, ["box-01", "box-02"])
        self.assertEqual(rc, 2)
        self.assertEqual(L.load_row(self.sweep, "box-02", self.root)["status"], L.FAIL)

    def test_unreachable_box_is_UNKNOWN_and_still_blocks_the_roll(self):
        down = {p: {"rc": 255, "error": "ssh transport failure to u@box-02"} for p in healthy_probes()}
        rc = self._run(fixture_for(2, broken={"box-02": down}), ["box-01", "box-02"])
        self.assertEqual(rc, 3, "UNKNOWN must be non-zero — it is not green")
        self.assertEqual(L.load_row(self.sweep, "box-02", self.root)["status"], L.UNKNOWN)

    def test_undeclared_expectations_refuse_the_sweep_before_touching_a_box(self):
        for drop in sorted(H.REQUIRED_EXPECTATIONS):
            self.sweep = "sweep-" + uuid.uuid4().hex[:8]
            partial = {k: v for k, v in EXPECTATIONS.items() if k != drop}
            rc = self._run(fixture_for(2), ["box-01", "box-02"], exp=partial)
            self.assertEqual(rc, 4, f"missing {drop} must REFUSE the sweep")
            self.assertFalse(L.sweep_dir(self.sweep, self.root).exists(),
                             "a refused sweep must not write any ledger row")

    def test_wave_cap_of_20_is_enforced(self):
        rc = self._run(fixture_for(21), [f"box-{i:02d}" for i in range(1, 22)])
        self.assertEqual(rc, 4)

    def test_zero_boxes_is_refused_not_green(self):
        rc = self._run(fixture_for(1), [])
        self.assertEqual(rc, 4)

    def test_resume_reruns_only_the_broken_box_and_keeps_history(self):
        boxes = ["box-01", "box-02"]
        broken = {"box-02": {H.PROBE_WRITEBACK: {"rc": 0, "stdout": "502"}}}
        self.assertEqual(self._run(fixture_for(2, broken=broken), boxes), 2)
        self.assertEqual(L.load_row(self.sweep, "box-01", self.root)["attempts"], 1)

        # box-02 is fixed; re-run with --resume
        self.assertEqual(self._run(fixture_for(2), boxes, extra=["--resume"]), 0)
        b1 = L.load_row(self.sweep, "box-01", self.root)
        b2 = L.load_row(self.sweep, "box-02", self.root)
        self.assertEqual(b1["attempts"], 1, "an already-green box must be SKIPPED, not re-probed")
        self.assertEqual(b2["attempts"], 2, "the broken box must be re-probed")
        self.assertEqual([h["status"] for h in b2["history"]], [L.FAIL, L.PASS])
        self.assertEqual(b2["status"], L.PASS)

    def test_resume_does_NOT_skip_when_the_expectations_changed(self):
        boxes = ["box-01"]
        self.assertEqual(self._run(fixture_for(1), boxes), 0)
        moved = {**EXPECTATIONS, "repo_sha": "9" * 40}       # new roll target
        rc = self._run(fixture_for(1), boxes, extra=["--resume"], exp=moved)
        self.assertEqual(rc, 2, "a PASS under OLD expectations must never satisfy NEW ones")
        self.assertEqual(L.load_row(self.sweep, "box-01", self.root)["status"], L.FAIL)

    def test_no_secret_value_is_ever_written_into_a_ledger_row(self):
        leak = "pit-THIS-IS-A-FAKE-TOKEN-VALUE-000"
        fx = fixture_for(1, broken={"box-01": {
            H.PROBE_TOKEN: {"rc": 0, "stdout": f"garbage {leak}"},          # unparseable + secret-shaped
            H.PROBE_WRITEBACK: {"rc": 0, "stdout": f"Bearer {leak}"},
        }})
        self.assertEqual(self._run(fx, ["box-01"]), 2)
        blob = L.ledger_path(self.sweep, "box-01", self.root).read_text()
        self.assertNotIn(leak, blob)
        self.assertIn("[REDACTED]", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
