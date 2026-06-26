"""MOCK-only unit tests — ghl_gate (the un-bypassable QC gate).

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO network, NO
real build runs.  All file content is synthesised in memory and written to
tmp_path.  The assertions cover the core anti-fabrication contract:

  * The gate reader IGNORES .md / ledger.json prose files — planting a
    run-funnel.md or a ledger.json that says "RESULT: PASS" / "verified:true"
    next to a FAILING machine summary cannot override require_pass.
  * A summary with trust:'MOCK' or a MOCK-DO-NOT-SHIP sentinel makes
    require_pass exit non-zero.
  * Only the machine-derived summary file (scorecard/verify-summary.json,
    written by ghl_verify.verify_all) is consulted — nothing else.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_gate.py -v
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest


# ── Import ghl_gate (may not exist yet — skip when B2 not landed) ─────────────

def _import_gate():
    try:
        import ghl_gate  # noqa: F401 — imported for side-effect / availability check
        return ghl_gate
    except ImportError:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_summary(run_dir: str, *, overall_pass: bool, passed: int = 1,
                   total: int = 1, trust: str | None = None,
                   include_writer: bool = True) -> str:
    """Write a scorecard/verify-summary.json and return its path.

    include_writer=True (default) adds the writer + run_nonce fields that
    ghl_gate.require_pass expects.  Set include_writer=False to test the
    gate's rejection of hand-crafted (non-ghl_verify) summaries.
    """
    import uuid
    scorecard = os.path.join(run_dir, "scorecard")
    os.makedirs(scorecard, exist_ok=True)
    data = {
        "overall_pass": overall_pass,
        "passed": passed,
        "total": total,
        "failed": total - passed,
    }
    if include_writer:
        data["writer"] = "ghl_verify.verify_all"
        data["run_nonce"] = str(uuid.uuid4())
    if trust is not None:
        data["trust"] = trust
    path = os.path.join(scorecard, "verify-summary.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _write_raw(run_dir: str, records: list) -> str:
    """Write a logs/final-preview-verify.json and return its path."""
    logs = os.path.join(run_dir, "logs")
    os.makedirs(logs, exist_ok=True)
    path = os.path.join(logs, "final-preview-verify.json")
    with open(path, "w") as f:
        json.dump(records, f)
    return path


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestProseMdCannotOverrideGate:
    """Prose .md / ledger.json files claiming PASS must NOT override the gate.

    The gate reads ONLY scorecard/verify-summary.json (machine-written by
    ghl_verify).  Any other file is data, not a verdict.
    """

    def test_pass_md_next_to_failing_summary_is_rejected(self, tmp_path):
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)

        # Plant the FAILING machine summary (the truth).
        _write_summary(run_dir, overall_pass=False, passed=0, total=1)
        _write_raw(run_dir, [{"step": "home", "PASS": False, "http_code": 500}])

        # Plant prose files claiming PASS (the lies the pre-flight wrote).
        with open(os.path.join(run_dir, "run-funnel.md"), "w") as f:
            f.write("# Build Summary\n\nRESULT: PASS\n\nBoth pages verified live.\n")

        ledger = {"overall_pass": True, "verified": True, "pages": [
            {"step": "optin", "verified": True,
             "traceId": "6ab74873-fake-fabricated"},
        ]}
        with open(os.path.join(run_dir, "ledger.json"), "w") as f:
            json.dump(ledger, f)

        # require_pass must exit non-zero (or raise) — the prose cannot override.
        rc = gate.require_pass(run_dir)
        assert rc != 0, (
            "require_pass must return non-zero when the machine summary says FAIL, "
            "even if prose .md / ledger.json files claim PASS"
        )

    def test_passing_summary_without_prose_passes(self, tmp_path):
        """A genuine PASS summary (no prose files at all) must succeed."""
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)
        _write_summary(run_dir, overall_pass=True, passed=1, total=1)
        _write_raw(run_dir, [{"step": "home", "PASS": True, "http_code": 200}])

        rc = gate.require_pass(run_dir)
        assert rc == 0, \
            "require_pass must return 0 when the machine summary is overall_pass:True"

    def test_ledger_verified_true_next_to_failing_summary_is_rejected(self, tmp_path):
        """A ledger.json with verified:true cannot flip a FAIL summary to PASS."""
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)
        _write_summary(run_dir, overall_pass=False, passed=0, total=2)
        _write_raw(run_dir, [
            {"step": "optin", "PASS": False, "http_code": 403},
            {"step": "thanks", "PASS": False, "http_code": 403},
        ])

        # The fabricated ledger (exactly what the pre-flight produced for the funnel).
        ledger = {
            "overall_pass": True,
            "verified": True,
            "pages": [
                {"step": "optin", "verified": True, "autosave_status": 201,
                 "traceId": "6ab74873-fake-fabricated-optin"},
                {"step": "thanks", "verified": True, "autosave_status": 201,
                 "traceId": "cf072cf0-fake-fabricated-thanks"},
            ],
        }
        with open(os.path.join(run_dir, "ledger.json"), "w") as f:
            json.dump(ledger, f)

        rc = gate.require_pass(run_dir)
        assert rc != 0, \
            "ledger.json with verified:true must NOT override a FAIL machine summary"


class TestMockTrustBlocksGate:
    """A summary with trust:'MOCK' or a MOCK-DO-NOT-SHIP sentinel must make
    require_pass exit non-zero — mock runs are never shippable."""

    def test_mock_trust_in_summary_is_rejected(self, tmp_path):
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)
        # A "passing" summary but with trust:'MOCK'.
        _write_summary(run_dir, overall_pass=True, passed=1, total=1,
                       trust="MOCK")
        _write_raw(run_dir, [{"step": "home", "PASS": True, "http_code": 200}])

        rc = gate.require_pass(run_dir)
        assert rc != 0, \
            "require_pass must return non-zero when summary.trust is 'MOCK'"

    def test_mock_do_not_ship_sentinel_is_rejected(self, tmp_path):
        """A summary tagged with the MOCK-DO-NOT-SHIP sentinel is not shippable."""
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        # Get the sentinel value from the gate module (or fall back to the string).
        sentinel = getattr(gate, "MOCK_DO_NOT_SHIP", "MOCK-DO-NOT-SHIP")

        run_dir = str(tmp_path)
        _write_summary(run_dir, overall_pass=True, passed=1, total=1,
                       trust=sentinel)
        _write_raw(run_dir, [{"step": "home", "PASS": True, "http_code": 200}])

        rc = gate.require_pass(run_dir)
        assert rc != 0, \
            "require_pass must return non-zero when summary carries the MOCK-DO-NOT-SHIP sentinel"

    def test_no_trust_field_with_passing_summary_passes(self, tmp_path):
        """A summary with no trust field and overall_pass:True must pass."""
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)
        _write_summary(run_dir, overall_pass=True, passed=2, total=2)
        _write_raw(run_dir, [
            {"step": "optin", "PASS": True, "http_code": 200},
            {"step": "thanks", "PASS": True, "http_code": 200},
        ])

        rc = gate.require_pass(run_dir)
        assert rc == 0, \
            "require_pass must return 0 for a genuine PASS summary with no trust flag"


class TestGateIgnoresAllOtherFiles:
    """The gate must consult ONLY scorecard/verify-summary.json.  No other file
    in the run directory (build.log, run-website.md, VERIFY-opus-final.md,
    evidence.json) must affect the verdict."""

    def test_only_summary_matters_other_files_ignored(self, tmp_path):
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)

        # Failing machine summary.
        _write_summary(run_dir, overall_pass=False, passed=0, total=3)
        _write_raw(run_dir, [
            {"step": "home", "PASS": False, "http_code": 500},
            {"step": "about", "PASS": False, "http_code": 500},
            {"step": "contact", "PASS": False, "http_code": 500},
        ])

        # Decoy files with optimistic content (matching what the pre-flight wrote).
        with open(os.path.join(run_dir, "build.log"), "w") as f:
            f.write("Overall PASS: True\nRESULT: PASS — all pages verified\n")

        with open(os.path.join(run_dir, "VERIFY-opus-final.md"), "w") as f:
            f.write(
                "# Final Verification\n\n"
                "BOTH BUILDS PASS — verified LIVE in GoHighLevel.\n"
                "marker present in Firebase blob.\n"
            )

        evidence = {
            "overall_pass": True,
            "pages": [
                {"step": "home", "verified": True, "autosave_status": 201},
            ],
        }
        with open(os.path.join(run_dir, "evidence.json"), "w") as f:
            json.dump(evidence, f)

        rc = gate.require_pass(run_dir)
        assert rc != 0, (
            "require_pass must return non-zero when the machine summary says FAIL, "
            "regardless of what build.log / VERIFY-opus-final.md / evidence.json claim"
        )

    def test_missing_summary_file_is_not_a_pass(self, tmp_path):
        """When scorecard/verify-summary.json does not exist, the gate must not
        pretend the build passed — a missing summary is at best UNKNOWN and must
        exit non-zero."""
        gate = _import_gate()
        if gate is None:
            pytest.skip("ghl_gate not yet implemented (B2 pending)")
        if not hasattr(gate, "require_pass"):
            pytest.skip("ghl_gate.require_pass not yet implemented (B2 pending)")

        run_dir = str(tmp_path)
        # Write decoy files but NOT the machine summary.
        with open(os.path.join(run_dir, "run-funnel.md"), "w") as f:
            f.write("RESULT: PASS\n")

        rc = gate.require_pass(run_dir)
        assert rc != 0, \
            "require_pass must return non-zero when scorecard/verify-summary.json is absent"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
