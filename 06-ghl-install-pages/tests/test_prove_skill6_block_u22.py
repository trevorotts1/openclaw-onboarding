"""test_prove_skill6_block_u22.py — CI wrapper for U22/B-U8's operator-box
proof run.

Wires ``prove_skill6_block_u22.py`` (guards + fixtures + ONE end-to-end
operator-box proof run for the whole Skill-6 persona-unification block) into
the standard pytest run so it executes on every push/PR that touches the
funnel-automation-libraries-guard.yml path set — not just when invoked by
hand on an operator box.

No network, no browser.
"""
from __future__ import annotations

import os
import sys

_SCRIPTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import prove_skill6_block_u22 as proof  # noqa: E402


def test_operator_box_block_proof_run_exits_zero(capsys):
    rc = proof.run()
    out = capsys.readouterr().out
    assert rc == 0, out
    # Every landed-unit check must have printed PASS — a silent skip that
    # never ran a check would still exit 0 with zero PASS lines, which must
    # never be mistaken for a real proof.
    assert out.count("[PASS]") >= 18, (
        "expected the full landed-block checklist to have run and passed; "
        f"got {out.count('[PASS]')} PASS lines:\n{out}"
    )
    assert "[FAIL]" not in out
    # The honest scope-gap notice for the two not-yet-landed prerequisite
    # units must be present verbatim — this test would also catch someone
    # silently deleting the honesty guard around B-U4/U18 + B-U7/U21.
    assert "B-U4/U18" in out
    assert "B-U7/U21" in out


def test_bundle_voice_persona_id_matches_cc_repo_companion_guard():
    """Pin the literal blackceo-command-center's
    tests/unit/u22-b-u8-persona-block-guard.test.ts asserts a zero-mismatch
    agreement against. If this ever changes here, the CC-side companion
    guard must change in lockstep (see that file's own docstring)."""
    assert proof.BUNDLE_VOICE_PERSONA_ID == "hormozi-100m-offers"


def test_scope_gap_detectors_never_raise():
    # These flip from False -> True the moment B-U4/U18 / B-U7/U21 actually
    # land (by design — they read the real tree, not a stale flag), so this
    # test only pins that they run cleanly, never their current value.
    assert proof._crosswalk_has_copy_craft_pool() in (True, False)
    assert proof._ingest_task_has_persona_fields() in (True, False)
