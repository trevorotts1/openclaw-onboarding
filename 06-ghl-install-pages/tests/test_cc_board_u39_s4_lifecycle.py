# test_cc_board_u39_s4_lifecycle.py — U39 / C-08: S4 "not-Done" closure — the
# producer-half of the producer -> review -> done lifecycle contract proof.
#
# ONE end-to-end chain, exactly per C-08's "what":
#   1. cc_board.ingest_task() lands ONE card (mocked transport, zero network) and
#      returns the CC task_id every later step in this test reuses.
#   2. cc_board.BuildPhaseDriver drives that SAME task_id through
#      start -> step -> artifact, landing the card at 'review' (never 'done').
#   3. On that SAME task_id, a direct cc_board.move_task(task_id, 'done') attempt
#      is asserted refused: returns False, issues ZERO wire call, and is logged
#      with the 'BLOCKED' prefix (cc_board.py move_task's 'done' hard-block).
#   4. On that SAME task_id, a direct cc_board.update_status(task_id, 'done')
#      attempt is asserted refused the same way (the DoD5-parity guard that
#      closes the legacy update_status bypass move_task's own guard doesn't
#      cover).
#
# SCOPE — this is the ONB (producer) half of a both-repo unit. The consumer-side
# leg (a direct signed POST of 'done' to api/tasks/[id]/status/route.ts 403'ing
# with byte-parity HMAC auth present, and runQCOnReview's PASS->done /
# FAIL->backlog+qc_reroute_attempts promote path firing notifyOwnerDone) lives in
# trevorotts1/blackceo-command-center — a separate repo/runtime this Python suite
# cannot import or exercise. That leg is NOT faked here; see the CC-side unit's
# own test file + the U39 ledger row for its evidence.
#
# Cross-references, does NOT duplicate: whether the CC judge actually consumes
# the producer's own QC scorecard (the producer/consumer Quality-Control metadata
# contract, Section B / v1 B9-territory) is a SEPARATE, still-undecided unit. This
# test asserts the LIFECYCLE contract only (done is unreachable outside the QC
# gate) and makes zero assertion, either way, about scorecard consumption.
#
# Stdlib + pytest only, zero network.
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import urllib.request

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE, "MC_API_TOKEN": "t", "WEBHOOK_SECRET": "s"}


class _Recorder:
    """Stand-in for cc_board._post_json. Records every (method, url, payload) and
    returns a scripted 2xx body so the chain runs with zero network. Ingest always
    returns the SAME task_id so every later call in the chain targets one real
    card, not a hardcoded stand-in id."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, cfg, method="POST"):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "TASK-S4-1", "deduped": False, "status": "backlog"}
        return 200, {"ok": True}

    def statuses(self):
        return [c["payload"]["status"] for c in self.calls
                if isinstance(c["payload"], dict) and "status" in c["payload"]]


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr(cc_board, "_post_json", r)
    return r


class TestS4LifecycleContractProducerHalf:
    """U39 / C-08 — the ONE producer->review->done chain, on one real task_id."""

    def test_full_chain_ingest_review_then_both_done_attempts_refused(self, rec, capsys):
        # 1. Ingest — lands the card, returns the task_id every later call reuses.
        task_id = cc_board.ingest_task(
            "Skill-6 funnel build — S4 lifecycle contract proof",
            job_type="funnel",
            env=ENV,
        )
        assert task_id == "TASK-S4-1", "ingest_task must hand back the CC task_id"
        ingest_calls = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        assert len(ingest_calls) == 1, "exactly one card must be ingested"

        # 2. Drive to review via BuildPhaseDriver — same task_id, real sequencing.
        driver = cc_board.BuildPhaseDriver(task_id, env=ENV)
        driver.start("S4 lifecycle contract build started")
        driver.step(1, 1, "Step 1/1: build the fixture artifact")
        assert driver.artifact(
            "https://demo.zerohumanworkforce.com/funnel/s4-lifecycle-proof",
            meta={"type": "funnel_url"},
        ) is True

        written = rec.statuses()
        assert "review" in written, "the driver must land the card at review"
        assert written[-1] == "review", "review must be the TERMINAL producer status"
        assert "done" not in written, "the producer chain must never write done"

        # Isolate the two refusal attempts below from the setup traffic so the
        # wire-call and log assertions below are unambiguous.
        rec.calls.clear()
        capsys.readouterr()

        # 3. Direct move_task('done') on the SAME task_id — refused, zero wire call.
        assert cc_board.move_task(task_id, "done", env=ENV) is False, (
            "move_task('done') must be refused — the QC gate is the only promoter "
            "from review to done")
        assert rec.calls == [], "a blocked move_task('done') must issue NO wire call"
        err = capsys.readouterr().err
        assert "move_task BLOCKED" in err, (
            f"move_task('done') refusal must be logged with the 'BLOCKED' prefix, "
            f"got: {err!r}")

        # 4. Direct update_status('done') on the SAME task_id — refused, zero wire
        # call. DoD5 parity: closes the LEGACY bypass hole move_task's own guard
        # does not cover.
        assert cc_board.update_status(task_id, "done", env=ENV) is False, (
            "update_status('done') must be refused — mirrors move_task's hard-block")
        assert rec.calls == [], "a blocked update_status('done') must issue NO wire call"
        err = capsys.readouterr().err
        assert "update_status BLOCKED" in err, (
            f"update_status('done') refusal must be logged with the 'BLOCKED' "
            f"prefix, got: {err!r}")

        # Both refusals verified on the ONE task_id the ingest+driver chain
        # actually produced — the card is structurally incapable of reaching
        # done from the producer side, by two independently-triggered guards,
        # proven against a real chained id rather than two disconnected fixtures.

    def test_consumer_403_and_qc_promote_path_owned_by_cc_repo(self):
        """Documents (does not fake) the CC-side legs of this both-repo unit
        (U39 / C-08 BINARY acceptance (b) and (c)):

        (b) a direct signed POST of 'done' to api/tasks/[id]/status/route.ts is
            403'd consumer-side with byte-parity HMAC auth present (so the
            refusal is the done-gate, not an auth failure);
        (c) runQCOnReview with a PASS >= 8.5 fixture promotes review -> done with
            the audited event row and fires notifyOwnerDone; a FAIL fixture lands
            'backlog' with gap notes and increments qc_reroute_attempts.

        These live in trevorotts1/blackceo-command-center, a separate repo/
        runtime this Python test suite cannot import or exercise. The CC-side
        unit ships that half under its own test file and its own U39 ledger
        evidence — not asserted, not simulated, not stamped 'done' here."""
        pytest.skip(
            "OWED to trevorotts1/blackceo-command-center (U39/C-08 acceptance "
            "b+c): consumer 403 on api/tasks/[id]/status/route.ts + the "
            "runQCOnReview PASS/FAIL promote path. Not this repo, not faked here."
        )


class TestByteParityAuthOnTheDoneWireContract:
    """The ONB-provable slice of acceptance (b): cc_board's own HMAC signing is
    byte-for-byte the documented ``HMAC-SHA256(WEBHOOK_SECRET, raw_body)``
    formula the CC route verifies against (``_sign``'s own docstring —
    "byte-for-byte parity with verifyWebhookSignature() in the route
    handlers"). This proves that IF a 'done' payload ever reached the wire
    (it cannot, via the two guarded public functions — see the class above),
    its auth would be VALID — so any real consumer-side refusal of it is
    attributable to the done-gate, never to a bad signature. It does not, and
    cannot from this repo, exercise the real CC route or assert its response."""

    def test_sign_matches_the_documented_hmac_sha256_formula(self):
        secret = "s3cr3t-test-only"
        raw_body = b'{"status":"done"}'
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        assert cc_board._sign(secret, raw_body) == expected

    def test_sign_is_none_without_a_secret_mirroring_the_routes_noop(self):
        # "Returns None when no secret (the endpoint also no-ops in that case)."
        assert cc_board._sign("", b'{"status":"done"}') is None

    def test_a_raw_bypass_post_of_done_would_carry_a_byte_correct_signature(self, monkeypatch):
        # The ONLY way 'done' could ever reach the wire is a caller bypassing
        # both guarded public functions and calling the low-level transport
        # directly. Proving even THAT hypothetical carries a byte-correct
        # signature isolates "auth" from "gate" as two independent axes — the
        # CC-side 403 this repo cannot exercise sits on the gate axis alone.
        captured: dict = {}

        class _Resp:
            def __init__(self, body: bytes, status: int):
                self._body, self._status = body, status

            def read(self):
                return self._body

            def getcode(self):
                return self._status

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(req, timeout=None):
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["body"] = req.data
            return _Resp(b'{"error":"done is not a writable status"}', 200)

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

        cfg = cc_board.board_config(ENV)
        assert cfg is not None, "ENV must resolve to a configured board for this probe"
        cc_board._post_json(f"{BASE}/api/tasks/TASK-S4-1/status", {"status": "done"}, cfg)

        assert captured.get("body"), "the raw transport must have sent a body to sign over"
        expected_sig = hmac.new(
            ENV["WEBHOOK_SECRET"].encode("utf-8"), captured["body"], hashlib.sha256,
        ).hexdigest()
        assert captured["headers"].get("x-webhook-signature") == expected_sig, (
            "the raw transport must sign the EXACT bytes it sends, byte-for-byte")


def test_s4_lifecycle_module_selftest_still_clean():
    # Sanity: the module the whole chain depends on still self-tests clean.
    assert cc_board._status_selftest() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
