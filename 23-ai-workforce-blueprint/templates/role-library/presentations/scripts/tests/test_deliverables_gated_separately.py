#!/usr/bin/env python3
"""test_deliverables_gated_separately.py — B1 pin (2026-08-19).

Bar (CONTROL/MASTER-WORK-ORDER-20260818.md Wave B, unit B1;
CONTROL/FABLE-TRUTH.md §2):

`{deck}-WORKBOOK.pdf`, `{deck}-WORKBOOK-FILLABLE.pdf` (P8.25-WORKBOOK) and
`PRESENTER-AUDIO-WEBINAR.mp3` (P9-SPEECH-WEBINAR-INTRO) are produced and
phase-gated every run but are deliberately NOT folded into the 10-item
DELIVERABLE_AUDIT_SPEC (folding them in without the PIPELINE-MANIFEST version
lockstep would desync REQUIRED_KEYS from the manifest's build_bundle_files —
see tests/test_deliverables_single_source.py::test_canonical_spec_has_ten_unique_keys,
::test_canonical_spec_matches_pipeline_manifest, and
tests/test_fix8_bundle_complete.py::test_full_bundle_passes_and_writes_gate,
::test_manifest_lockstep, all of which pin the bundle at exactly 10).

Instead, presentation_job/deliverables.py carries an authoritative,
code-referenced note plus a DELIVERABLES_GATED_SEPARATELY constant naming the
producing phase, producing script, gate codes, and SOP section for each of the
three artifacts. This test is the pin: it fails if that decision is silently
reverted (constant deleted/renamed/emptied), if the citations drift from the
live PIPELINE-MANIFEST.json phase records, or if DELIVERABLE_COUNT / REQUIRED_KEYS
quietly grow to absorb these artifacts without the version lockstep.

No network. Stdlib + pytest only, matching the repo's other flat-import tests
(see test_deliverables_single_source.py) — SCRIPTS is inserted onto sys.path.
"""

from __future__ import annotations

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import deliverables  # noqa: E402


# ---------------------------------------------------------------------------
# The 10-item bundle spec is unchanged by this unit — pin it here too, so a
# future edit that folds the gated-separately artifacts INTO the spec (without
# also running the manifest lockstep) is caught by this file as well as by
# test_deliverables_single_source.py / test_fix8_bundle_complete.py.
# ---------------------------------------------------------------------------
def test_bundle_spec_still_ten_and_excludes_gated_separately_keys():
    assert deliverables.DELIVERABLE_COUNT == 10
    assert len(deliverables.REQUIRED_KEYS) == 10
    for key in ("workbook_pdf", "workbook_pdf_fillable", "presenter_audio_webinar_mp3"):
        assert key not in deliverables.REQUIRED_KEYS, (
            f"{key} must not be folded into the 10-item DELIVERABLE_AUDIT_SPEC "
            f"without the PIPELINE-MANIFEST version lockstep (bump-version.sh + "
            f"version-markers.json + the three hash registries + an annotated tag)")


# ---------------------------------------------------------------------------
# The documented-separately record exists, is not empty, and covers exactly
# the two B1-named cases.
# ---------------------------------------------------------------------------
def test_gated_separately_constant_exists_and_covers_both_cases():
    assert hasattr(deliverables, "DELIVERABLES_GATED_SEPARATELY"), (
        "deliverables.py must document workbook + webinar-intro-audio as "
        "gated-separately artifacts (B1) — DELIVERABLES_GATED_SEPARATELY is missing")
    spec = deliverables.DELIVERABLES_GATED_SEPARATELY
    assert isinstance(spec, dict) and spec, "DELIVERABLES_GATED_SEPARATELY must be a non-empty dict"
    assert set(spec.keys()) == {"workbook_pdf", "presenter_audio_webinar_mp3"}


def test_workbook_entry_cites_real_producing_phase_and_gate_codes():
    entry = deliverables.DELIVERABLES_GATED_SEPARATELY["workbook_pdf"]
    assert entry["producing_phase"] == "P8.25-WORKBOOK"
    assert entry["producing_script"] == "scripts/workbook_builder.py"
    assert set(entry["gate_codes"]) == {
        "AF-WORKBOOK-PROMPT-NO-CONTENT", "AF-WORKBOOK-EMPTY", "AF-WORKBOOK-BOTH",
    }
    assert "{deck_slug}-WORKBOOK.pdf" in entry["filenames"]
    assert "{deck_slug}-WORKBOOK-FILLABLE.pdf" in entry["filenames"]
    assert "WORKBOOK-BUILDER-SOP.md" in entry["sop"]


def test_webinar_audio_entry_cites_real_producing_phase_and_gate_code():
    entry = deliverables.DELIVERABLES_GATED_SEPARATELY["presenter_audio_webinar_mp3"]
    assert entry["producing_phase"] == "P9-SPEECH-WEBINAR-INTRO"
    assert "synthesize_full_speech.py" in entry["producing_script"]
    assert entry["gate_codes"] == ["AF-WEBINAR-INTRO"]
    assert "PRESENTER-AUDIO-WEBINAR.mp3" in entry["filenames"]
    assert "WEBINAR-BUILDER-SOP.md" in entry["sop"]


# ---------------------------------------------------------------------------
# Cross-check the citations against the LIVE PIPELINE-MANIFEST.json, so this
# pin also catches manifest-side drift (phase renamed/removed/gate codes
# changed) — not just a deliverables.py-side revert.
# ---------------------------------------------------------------------------
def _locate_pipeline_manifest() -> pathlib.Path:
    cur = pathlib.Path(__file__).resolve().parent
    for _ in range(8):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        cur = cur.parent
    raise FileNotFoundError(
        f"PIPELINE-MANIFEST.json not found walking up from {pathlib.Path(__file__)}")


def test_citations_match_live_manifest_phase_records():
    manifest = json.loads(_locate_pipeline_manifest().read_text())
    phases = {p["id"]: p for p in manifest["phases"]}

    assert "P8.25-WORKBOOK" in phases, "P8.25-WORKBOOK phase missing from PIPELINE-MANIFEST.json"
    wb_phase = phases["P8.25-WORKBOOK"]
    wb_entry = deliverables.DELIVERABLES_GATED_SEPARATELY["workbook_pdf"]
    assert set(wb_entry["gate_codes"]) == set(wb_phase["gate_codes"]), (
        "workbook_pdf gate_codes in deliverables.py drifted from "
        "PIPELINE-MANIFEST.json P8.25-WORKBOOK.gate_codes")

    assert "P9-SPEECH-WEBINAR-INTRO" in phases, (
        "P9-SPEECH-WEBINAR-INTRO phase missing from PIPELINE-MANIFEST.json")
    wa_phase = phases["P9-SPEECH-WEBINAR-INTRO"]
    wa_entry = deliverables.DELIVERABLES_GATED_SEPARATELY["presenter_audio_webinar_mp3"]
    assert set(wa_entry["gate_codes"]) == set(wa_phase["gate_codes"]), (
        "presenter_audio_webinar_mp3 gate_codes in deliverables.py drifted from "
        "PIPELINE-MANIFEST.json P9-SPEECH-WEBINAR-INTRO.gate_codes")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
