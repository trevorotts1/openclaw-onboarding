"""Tests for the manifest `workers` field (Ticket 3, PARALLEL-PIPELINE-SPEC).

Absent -> 1 (the literal existing serial path); a positive int -> that int;
a bad value (string, 0, negative, float, bool) refuses the WHOLE manifest
with EXIT_MANIFEST_MISMATCH (7) rather than silently coercing to 1 -- the
same silent-coercion defect class capacity.py was written to eliminate.

Also proves the shipped PIPELINE-MANIFEST.json parses unchanged and every
phase reports workers == 1 (Ticket 3's stated exit condition: "field exists,
validates, and changes nothing").

ITEM 11 UPDATE (FIX-PLAN Item 11 / B23, manifest v71): Ticket 3's exit
condition is superseded for fanout phases. The shipped manifest now declares
`workers` on every fanout phase (P4-PROMPT declared 12 first, which already
broke the all-ones assertion on pristine HEAD; v71 declares the rest), and
the shipped-manifest test below pins the new contract: non-fanout phases
still report the default 1, fanout phases report their declared width. The
declaration rule and the loud undeclared-width warning are pinned by
tests/test_item11_fanout_width_declarations.py.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.

ITEM 16 UPDATE (FIX-PLAN Item 16): the loud warning this file's Item 11
paragraph points at is a failure now. sync_check's W2 class moved from the
advisory warnings list to the drift list (the gate exits non-zero on an
undeclared fanout width), and phases.py refuses the same condition at plan
time. The last test below pins the gate half; the plan-time half is pinned
in tests/test_f6_fanout_width.py section 7. The parse contract above is
unchanged: Manifest.load still does not refuse, and the fallback is
still 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.state import EXIT_MANIFEST_MISMATCH  # noqa: E402


def _canonical_manifest() -> Path:
    """Same resolution order as every sibling test file's own copy
    (test_l11_webinar_executor_no_recursion.py)."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    pytest.skip("PIPELINE-MANIFEST.json not found from this checkout root")


def _write_manifest(tmp_path: Path, phases: list) -> Path:
    data = {
        "manifest_version": 1,
        "phases": phases,
        "autofails": [],
        "roles": [],
    }
    path = tmp_path / "PIPELINE-MANIFEST.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _base_phase(**overrides) -> dict:
    phase = {
        "id": "P-TEST",
        "order": 1.0,
        "owning_role": "test-role",
        "produces_artifact": "working/x.txt",
        "executor": {"kind": "agent"},
        "verifier": "phase_verifiers.verify",
    }
    phase.update(overrides)
    return phase


def test_absent_workers_defaults_to_one(tmp_path):
    path = _write_manifest(tmp_path, [_base_phase()])
    m = Manifest(path)
    assert m.phase("P-TEST").workers == 1


def test_explicit_workers_50(tmp_path):
    path = _write_manifest(tmp_path, [_base_phase(workers=50)])
    m = Manifest(path)
    assert m.phase("P-TEST").workers == 50


@pytest.mark.parametrize("bad_value", ["50", 0, -1, 1.5, True, False, [], {}])
def test_bad_workers_value_refuses_whole_manifest(tmp_path, bad_value):
    path = _write_manifest(tmp_path, [_base_phase(workers=bad_value)])
    with pytest.raises(SystemExit) as exc_info:
        Manifest(path)
    assert exc_info.value.code == EXIT_MANIFEST_MISMATCH


def test_null_workers_treated_as_absent(tmp_path):
    path = _write_manifest(tmp_path, [_base_phase(workers=None)])
    m = Manifest(path)
    assert m.phase("P-TEST").workers == 1


def test_shipped_manifest_workers_contract_after_item11():
    """The shipped manifest under the post-Item-11 contract (manifest v71):
    phases WITHOUT a fanout declaration still report workers == 1 (the
    feature stays off by default, Ticket 3's parse contract intact), and
    every phase WITH a fanout declaration declares its width explicitly.
    (Ticket 3's original all-ones form of this test went stale when
    P4-PROMPT declared workers: 12; it failed on pristine HEAD.)"""
    path = _canonical_manifest()
    m = Manifest(path)
    assert len(m.phases) > 0
    for phase in m.phases:
        if phase.fanout is None:
            assert phase.workers == 1, (
                f"{phase.id} has no fanout declaration but reports "
                f"workers={phase.workers}")
            assert phase.workers_declared is False
        else:
            assert phase.workers_declared, (
                f"{phase.id} declares a fanout field but no workers "
                f"(Item 11: declare the width, or an explicit 1)")
    assert m.phase("P4-PROMPT").workers == 12


def test_w2_undeclared_fanout_width_is_drift_not_advisory():
    """FIX-PLAN Item 16: the drift gate's posture on the undeclared width.

    sync_check.run_checks emits W2 (class render_path) for a fanout phase
    with no workers declaration; warn_checks no longer reports W2 at all.
    The shipped manifest (every width declared) produces neither; a copy
    with one declaration removed produces exactly one drift entry naming
    that phase. The engine half of the promotion (plan-time refusal) is
    pinned in test_f6_fanout_width.py section 7."""
    import copy

    import sync_check

    raw = json.loads(_canonical_manifest().read_text(encoding="utf-8"))
    bd = {"chk_funcs": set(), "defined_names": set(), "af_strings": set()}

    def _w2_drift(manifest):
        drift = sync_check.run_checks(manifest, bd, set(), set(), set())
        return [d for d in drift if d["check"] == "W2"]

    assert _w2_drift(raw) == [], "the shipped manifest declares every width"
    assert [w for w in sync_check.warn_checks(raw, set())
            if w["check"] == "W2"] == [], (
        "W2 left the advisory list in FIX-PLAN Item 16")

    broken = copy.deepcopy(raw)
    for ph in broken["phases"]:
        if ph["id"] == "P4-COPY":
            ph["workers"] = None
    w2 = _w2_drift(broken)
    assert [d["item"] for d in w2] == ["P4-COPY"], w2
    assert all(d["class"] == "render_path" for d in w2), w2
