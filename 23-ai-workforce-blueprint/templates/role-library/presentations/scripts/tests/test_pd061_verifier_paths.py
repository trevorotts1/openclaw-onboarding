#!/usr/bin/env python3
"""test_pd061_verifier_paths.py — PD-061 (Critical, lane FL17).

The speech step check read a folder the speech is never delivered to:
``PHASE_VERIFIERS["P9-SPEECH"]`` demanded
``working/presenter-speech/PRESENTERS-SPEECH.md`` (the harness's scratch
``--workdir``) while the manifest declares, and ``speech_build_harness``'s own
``--out`` writes, ``working/deliverables/PRESENTERS-SPEECH.md``. A run that had
produced the speech parked at the speech step.

Rows (01-BUILD-SPEC.md, section PD-061 amendments):

  A1  speech at ``working/deliverables/`` ONLY      -> passes
  A2  speech at ``working/presenter-speech/`` ONLY  -> fails
  A3  no speech anywhere                            -> fails
  A4  parity over the WHOLE registry: every registry entry built by
      ``_verify_text_artifact`` / ``_verify_json_artifact`` (the checked path
      is exposed as ``artifact_pattern``) reads the path its manifest
      ``produces_artifact`` declares.

The manifest is loaded with ``json`` from the cluster copy that ships beside the
department (the same file ``presentation_job/manifest.py`` loads), never from a
per-run copy.

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

# The registry entries whose checked path comes from a path factory. Pinned in
# BOTH directions: a new factory registration must be added here deliberately
# (otherwise the parity walk below could silently stop covering it), and an
# entry listed here must still carry its checked path.
EXPECTED_FACTORY_PHASES = frozenset({
    "P0A-INTAKE",
    "P0B-PRIORITY",
    "P-3.5-RESEARCH-MAP",
    "P-STYLE-PREVIEW",
    "P-TYPO-QC",          # built by the factory, wrapped in the shadow verifier
    "PF-DESIGN",
    "P9-SPEECH",
    "P7-TELEPROMPTER",
    "P8.1-PDF-EXPORT",
    "P8.2-GUIDE",
    "P9.1-SPEECH-PDF",
})

# A4 allow-list: (unit id, phase id) for a mismatch ANOTHER unit of lane FL17
# fixes. Empty today — no such mismatch survived the fix. A mismatch that is
# not listed here is reported as BLOCKED-FOLLOWUP by the assertion message.
A4_ALLOW_LIST: dict[str, str] = {}


def _manifest() -> dict:
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    return json.loads(CLUSTER_MANIFEST.read_text(encoding="utf-8"))


def _manifest_artifact(pid: str) -> object:
    m = _manifest()
    row = next((p for p in m["phases"] if p.get("id") == pid), None)
    assert row is not None, f"{pid} is in the verifier registry but not the manifest"
    return row.get("produces_artifact")


def _run_dir_with(tmp_path: Path, rel: str) -> Path:
    run_dir = tmp_path / "run"
    p = run_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    # Comfortably over P9-SPEECH's 200-byte floor: this test is about WHICH
    # path is read, not about the floor.
    p.write_text("# Presenter speech\n\n" + ("Speak this line aloud. " * 40),
                 encoding="utf-8")
    return run_dir


def test_a1_speech_only_under_deliverables_passes(tmp_path):
    """A1: the path the manifest declares is the path that is read."""
    run_dir = _run_dir_with(tmp_path, "working/deliverables/PRESENTERS-SPEECH.md")
    ok, reasons = pv.PHASE_VERIFIERS["P9-SPEECH"](run_dir)
    assert ok, f"speech at the manifest path must pass, got reasons={reasons}"


def test_a2_speech_only_under_presenter_speech_fails(tmp_path):
    """A2: the old scratch workdir is NOT the delivered artifact."""
    run_dir = _run_dir_with(tmp_path, "working/presenter-speech/PRESENTERS-SPEECH.md")
    ok, reasons = pv.PHASE_VERIFIERS["P9-SPEECH"](run_dir)
    assert not ok, "speech only in the scratch workdir must NOT satisfy the step"
    assert any("working/deliverables/PRESENTERS-SPEECH.md" in r for r in reasons), (
        f"the failure must name the expected path, got reasons={reasons}")


def test_a3_no_speech_fails(tmp_path):
    """A3: absence is a hard failure, not a vacuous pass."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ok, reasons = pv.PHASE_VERIFIERS["P9-SPEECH"](run_dir)
    assert not ok, "no speech file must fail"
    assert any("file not found" in r for r in reasons), f"got reasons={reasons}"


def test_a4_every_path_factory_entry_matches_the_manifest():
    """A4: parity across the WHOLE registry, not a hand-picked sample."""
    covered = {
        pid: fn.artifact_pattern
        for pid, fn in pv.PHASE_VERIFIERS.items()
        if getattr(fn, "artifact_pattern", None) is not None
    }
    # Whole-registry classification: nothing escapes the walk.
    assert set(covered) == set(EXPECTED_FACTORY_PHASES), (
        "the set of registry entries carrying a checked path changed: "
        f"unexpected={sorted(set(covered) - EXPECTED_FACTORY_PHASES)}, "
        f"missing={sorted(EXPECTED_FACTORY_PHASES - set(covered))}")
    mismatches = []
    for pid, pattern in sorted(covered.items()):
        declared = _manifest_artifact(pid)
        if isinstance(declared, list):
            # A list-valued produces_artifact: the checked path must be ONE of
            # the declared paths (A4 speaks of entries whose artifact is one
            # literal path).
            if pattern not in declared:
                mismatches.append(f"{pid}: check reads {pattern!r}; manifest declares {declared!r}")
            continue
        if declared != pattern:
            mismatches.append(f"{pid}: check reads {pattern!r}; manifest declares {declared!r}")
    unlisted = [m for m in mismatches
                if not any(m.startswith(f"{pid}:") for pid in A4_ALLOW_LIST)]
    assert not unlisted, (
        "BLOCKED-FOLLOWUP — these checked paths are not the paths the manifest "
        "declares: " + "; ".join(unlisted))
