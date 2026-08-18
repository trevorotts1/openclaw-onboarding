"""Tests for U05 — single-source the deliverable whitelist into deliverables.py.

Bar:
  * presentation_job/deliverables.py is THE single source of truth: ten keys,
    matching PIPELINE-MANIFEST.build_bundle_files.
  * fix_bundle_complete.py, presentation_job/curate.py, phase_verifiers.py, and
    self_audit.py all derive an IDENTICAL key set from it -- no consumer may
    see a whitelist that has drifted from the canonical spec (the exact bug
    this file exists to prevent: phase_verifiers.py previously carried a
    "workbook_pdf" key that was never part of the canonical bundle while
    silently missing "speech_md", and the repo's own fix_bundle_complete.py
    had gone stale at nine pieces while the live deployed copy had ten).
  * self_audit.py has NO inline fallback list -- if the canonical whitelist
    cannot be imported, self_audit.py fails LOUDLY (ImportError) rather than
    silently auditing against a stale hand-copied list.

No network. Stdlib + pytest only, matching the repo's other flat-import tests
(see test_fix8_bundle_complete.py) -- SCRIPTS is inserted onto sys.path so the
top-level bare modules (fix_bundle_complete, phase_verifiers, self_audit) and
the presentation_job package resolve identically to how the real pipeline
imports them.
"""

import importlib.util
import json
import pathlib
import sys
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402
import fix_bundle_complete as fbc  # noqa: E402
import phase_verifiers as pv  # noqa: E402
import presenters_speech_pdf as psp  # noqa: E402
import self_audit  # noqa: E402
from presentation_job import curate  # noqa: E402
from presentation_job import deliverables  # noqa: E402
from presentation_job import gates as gates_mod  # noqa: E402


# ---------------------------------------------------------------------------
# The canonical spec itself
# ---------------------------------------------------------------------------


def test_canonical_spec_has_ten_unique_keys():
    """The single source of truth is exactly ten deliverables, no duplicates."""
    assert len(deliverables.DELIVERABLE_AUDIT_SPEC) == 10
    assert len(deliverables.REQUIRED_KEYS) == 10
    assert len(set(deliverables.REQUIRED_KEYS)) == 10, "duplicate key in DELIVERABLE_AUDIT_SPEC"
    assert deliverables.DELIVERABLE_COUNT == 10


def test_canonical_spec_matches_pipeline_manifest():
    """The canonical key set must never drift from PIPELINE-MANIFEST.build_bundle_files
    (the same lockstep fix_bundle_complete.py's own self-test enforces)."""
    cur = pathlib.Path(deliverables.__file__).resolve().parent
    manifest = None
    for _ in range(8):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            manifest = cand
            break
        cur = cur.parent
    assert manifest is not None, "PIPELINE-MANIFEST.json not found"
    man = json.loads(manifest.read_text())
    assert sorted(man.get("build_bundle_files", [])) == sorted(deliverables.REQUIRED_KEYS)


# ---------------------------------------------------------------------------
# Every consumer imports the SAME object / derives the SAME key set
# ---------------------------------------------------------------------------


def test_fix_bundle_complete_imports_the_canonical_object():
    """fix_bundle_complete.py must not define its own DELIVERABLE_AUDIT_SPEC --
    it must be the literal same list object as the canonical source."""
    assert fbc.DELIVERABLE_AUDIT_SPEC is deliverables.DELIVERABLE_AUDIT_SPEC
    assert fbc.REQUIRED_KEYS == deliverables.REQUIRED_KEYS
    assert fbc.REQUIRED_DELIVERABLES == deliverables.REQUIRED_DELIVERABLES
    assert fbc.BUNDLE_COMPLETE_FILENAME == deliverables.BUNDLE_COMPLETE_FILENAME
    assert fbc.AF_BUNDLE_INCOMPLETE == deliverables.AF_BUNDLE_INCOMPLETE


def test_curate_imports_the_canonical_object():
    """curate.py must not define its own copy -- same list object, same keys."""
    assert curate.DELIVERABLE_AUDIT_SPEC is deliverables.DELIVERABLE_AUDIT_SPEC
    assert curate.REQUIRED_KEYS == deliverables.REQUIRED_KEYS
    assert set(curate.DESTINATION_FILENAMES.keys()) == set(deliverables.REQUIRED_KEYS)


def test_self_audit_derives_identical_keys():
    """self_audit.DELIVERABLE_AUDIT_LIST is DERIVED from the canonical spec --
    same key set, same min_bytes per key."""
    audit_keys = {item["key"] for item in self_audit.DELIVERABLE_AUDIT_LIST}
    assert audit_keys == set(deliverables.REQUIRED_KEYS)

    canonical_min_bytes = {s["key"]: s["min_bytes"] for s in deliverables.DELIVERABLE_AUDIT_SPEC}
    for item in self_audit.DELIVERABLE_AUDIT_LIST:
        assert item["min_bytes"] == canonical_min_bytes[item["key"]], (
            f"{item['key']}: self_audit min_bytes drifted from canonical spec")


def test_phase_verifiers_delivery_whitelist_matches_canonical_keys():
    """phase_verifiers._DELIVERY_DELIVERABLES must carry EXACTLY the canonical
    key set -- this is the concrete drift bug U05 fixes: the prior hardcoded
    list carried a 'workbook_pdf' key that was never part of the canonical
    bundle (the workbook is a separate P8.25-WORKBOOK deliverable with its own
    gate) while silently missing 'speech_md'."""
    delivery_keys = {item["key"] for item in pv._DELIVERY_DELIVERABLES}
    assert delivery_keys == set(deliverables.REQUIRED_KEYS)
    assert "workbook_pdf" not in delivery_keys, (
        "workbook_pdf is not part of the canonical whitelist and must not "
        "reappear in the P9-DELIVER check")
    assert "speech_md" in delivery_keys


def test_infographic_floor_matches_doctrine():
    """Pin the infographic_png min_bytes floor to the doctrine value (Part 6 #8 of the
    2026-08-17 fix review). PIPELINE-MANIFEST.json's own note reads '>100KB; one-page
    infographic slide exported as PNG', and build_deck.py's DELIVERABLES_REQUIRED
    carries the same 102_400 (100 KB) floor with the identical rationale comment.
    Single-sourcing the whitelist into this file (U05) silently carried a
    never-chosen 10_000 instead -- nobody picked it, no test pinned it, and it let a
    10-99KB placeholder/thumbnail pass a gate the doctrine floor was built to reject.
    This test is the pin so it cannot drift back unnoticed."""
    spec = next(s for s in deliverables.DELIVERABLE_AUDIT_SPEC if s["key"] == "infographic_png")
    assert spec["min_bytes"] == 102_400, (
        f"infographic_png min_bytes drifted from the 100KB doctrine floor: "
        f"got {spec['min_bytes']}")


def test_no_min_bytes_drift_between_deliverables_and_build_deck():
    """The permanent drift guard (2026-08-18 split-brain fix): deliverables.py's
    DELIVERABLE_AUDIT_SPEC and build_deck.py's DELIVERABLES_REQUIRED are two
    independently-maintained tables that carry a per-artifact min_bytes gate for
    the SAME nine-plus-one deliverables. They drifted apart on 8 of 9 named
    artifacts (deck_pptx 21x, speech_pdf 6.7x, audio_mp3 5.1x, teleprompter_html
    4.0x, guide_pdf 2.6x, speech_md 2.4x, speech_fish_md 2.4x, deck_pdf ~1x) plus
    a 10th unreviewed key (webinar_mp4, 2.1x) found during this reconciliation --
    a live split-brain where a file could pass one runtime gate (self_audit.py /
    curate.py / phase_verifiers.py, which import deliverables.py) and fail the
    other (build_deck.py's own internal P8-ASSEMBLE check) for the exact same
    artifact. This test is the guard: it fails the instant either table's
    min_bytes value for any shared key moves without the other -- a one-off
    reconciliation with no guard just resets the clock until the next drift.
    """
    canonical_min_bytes = {s["key"]: s["min_bytes"] for s in deliverables.DELIVERABLE_AUDIT_SPEC}
    build_deck_min_bytes = {s["key"]: s["min_bytes"] for s in build_deck.DELIVERABLES_REQUIRED}
    shared_keys = set(canonical_min_bytes) & set(build_deck_min_bytes)
    assert shared_keys, "expected at least one shared deliverable key between the two tables"

    mismatches = [
        f"{key}: deliverables.py={canonical_min_bytes[key]:,} bytes vs "
        f"build_deck.py={build_deck_min_bytes[key]:,} bytes"
        for key in sorted(shared_keys)
        if canonical_min_bytes[key] != build_deck_min_bytes[key]
    ]
    assert not mismatches, (
        "deliverables.DELIVERABLE_AUDIT_SPEC and build_deck.DELIVERABLES_REQUIRED "
        "disagree on min_bytes for the following shared key(s) -- these two tables "
        "gate the SAME artifacts and must never drift apart:\n  " + "\n  ".join(mismatches))


def _locate_pipeline_manifest() -> pathlib.Path:
    """Walk up from this test file to find PIPELINE-MANIFEST.json -- same strategy
    as test_canonical_spec_matches_pipeline_manifest above, independent of CWD."""
    cur = pathlib.Path(__file__).resolve().parent
    for _ in range(8):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        cur = cur.parent
    raise FileNotFoundError(
        f"PIPELINE-MANIFEST.json not found walking up from {pathlib.Path(__file__)}")


def test_no_min_bytes_drift_across_all_known_copies():
    """The EXTENDED drift guard (2026-08-18, second reconciliation pass).

    test_no_min_bytes_drift_between_deliverables_and_build_deck (above) only
    compared deliverables.py against build_deck.py. A follow-up audit against the
    doctrine sources (sops/presenters-speech-writer-sops.md's AF-BUNDLE-COMPLETE
    gate-tie-in line + commit eaae2e33, 2026-07-12) found the SAME two thresholds
    -- speech_pdf and teleprompter_html -- still stale in FOUR more independently-
    maintained places:
      * PIPELINE-MANIFEST.json (speech_pdf 20480, teleprompter_html 10240 -- both
        orphaned, dated 2026-06-17 by git blame, predating the doctrine fix).
      * presenters_speech_pdf.py's PDF_MIN_BYTES (20480, with a comment claiming it
        "matches PIPELINE-MANIFEST" -- true only because the manifest was itself stale).
      * presentation_job/gates.py's teleprompter artifact-gate floor (10240 -- a
        THIRD independent hardcoded copy, in a gates system not derived from
        deliverables.py at all).
      * phase_verifiers.py's P7-TELEPROMPTER / P9.1-SPEECH-PDF phase verifiers
        (10240 / 20480 -- found in the same file that already imports the
        canonical spec for its P9-DELIVER whitelist, but did not use it here).

    presenters_speech_pdf.py, presentation_job/gates.py, and phase_verifiers.py now
    DERIVE these two floors from deliverables.DELIVERABLE_AUDIT_SPEC instead of
    hardcoding a fifth (sixth, seventh...) copy. PIPELINE-MANIFEST.json is JSON and
    cannot import Python, so it stays an independently hand-maintained copy -- this
    test is ALSO the guard for that one.

    NOT value-checked against the derived intermediate for gates.py / phase_verifiers.py:
    both bake their min_bytes into a CLOSURE at call-site time (gates.py's
    evaluate_all() reads _MIN_BYTES[...] once per call; phase_verifiers.py's
    _verify_text_artifact(...) captures it once at PHASE_VERIFIERS-dict-construction
    time). A hand-verified probe during this fix proved that swapping the call-site
    argument back to a bare literal (bypassing _MIN_BYTES entirely) left the
    _MIN_BYTES dict itself untouched and correct -- a value-equality check against
    _MIN_BYTES would have stayed GREEN through that exact regression. So those two
    are checked BEHAVIORALLY below: a fixture one byte under the canonical floor must
    FAIL, and one at the floor must not fail on size -- this exercises the real
    enforcement path, not an intermediate that can go stale unread.
    """
    canonical = {s["key"]: s["min_bytes"] for s in deliverables.DELIVERABLE_AUDIT_SPEC}

    manifest = json.loads(_locate_pipeline_manifest().read_text())
    manifest_min_bytes = {d["key"]: d["min_bytes"] for d in manifest["deliverables_required"]}

    # source_name -> {key: value} -- direct-read copies, safe to value-check because
    # each is read straight from its module attribute at its own enforcement point
    # (no intervening closure/call-site copy).
    sources = {
        "PIPELINE-MANIFEST.json deliverables_required": manifest_min_bytes,
        "presenters_speech_pdf.PDF_MIN_BYTES": {"speech_pdf": psp.PDF_MIN_BYTES},
    }

    mismatches = [
        f"{source_name}[{key}] = {value:,} bytes vs canonical "
        f"deliverables.py[{key}] = {canonical[key]:,} bytes"
        for source_name, values in sources.items()
        for key, value in values.items()
        if value != canonical[key]
    ]

    # --- Behavioral checks: gates.py's Gates.evaluate_all() teleprompter gate ---
    floor = canonical["teleprompter_html"]
    rd_short = pathlib.Path(tempfile.mkdtemp())
    (rd_short / "working" / "deliverables").mkdir(parents=True)
    (rd_short / "working" / "deliverables" / "presenter-teleprompter.html").write_text(
        "y" * (floor - 1), encoding="utf-8")
    g_short = gates_mod.Gates(rd_short, {}).evaluate_all()
    if g_short["teleprompter"]["state"] != "fail":
        mismatches.append(
            f"presentation_job.gates.Gates.evaluate_all()[teleprompter]: a "
            f"{floor - 1:,}-byte file (one under the canonical {floor:,}-byte "
            f"teleprompter_html floor) did not fail -- the gate's real runtime floor "
            f"is below doctrine")

    rd_ok = pathlib.Path(tempfile.mkdtemp())
    (rd_ok / "working" / "deliverables").mkdir(parents=True)
    (rd_ok / "working" / "deliverables" / "presenter-teleprompter.html").write_text(
        "y" * floor, encoding="utf-8")
    g_ok = gates_mod.Gates(rd_ok, {}).evaluate_all()
    if g_ok["teleprompter"]["state"] == "fail":
        mismatches.append(
            f"presentation_job.gates.Gates.evaluate_all()[teleprompter]: a "
            f"{floor:,}-byte file (exactly the canonical floor) failed on size -- "
            f"the gate's real runtime floor is above doctrine: {g_ok['teleprompter']}")

    # --- Behavioral checks: phase_verifiers.py's P7-TELEPROMPTER / P9.1-SPEECH-PDF ---
    for phase_id, rel_path, key in (
        ("P7-TELEPROMPTER", "working/deliverables/presenter-teleprompter.html", "teleprompter_html"),
        ("P9.1-SPEECH-PDF", "working/deliverables/PRESENTERS-SPEECH.pdf", "speech_pdf"),
    ):
        pv_floor = canonical[key]
        rd_pv_short = pathlib.Path(tempfile.mkdtemp())
        p = rd_pv_short / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("z" * (pv_floor - 1), encoding="utf-8")
        ok_short, _ = pv.PHASE_VERIFIERS[phase_id](rd_pv_short)
        if ok_short:
            mismatches.append(
                f"phase_verifiers.PHASE_VERIFIERS[{phase_id!r}]: a {pv_floor - 1:,}-byte "
                f"file (one under the canonical {pv_floor:,}-byte {key} floor) passed -- "
                f"the verifier's real runtime floor is below doctrine")

        rd_pv_ok = pathlib.Path(tempfile.mkdtemp())
        p = rd_pv_ok / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("z" * pv_floor, encoding="utf-8")
        ok_at_floor, reasons = pv.PHASE_VERIFIERS[phase_id](rd_pv_ok)
        if not ok_at_floor:
            mismatches.append(
                f"phase_verifiers.PHASE_VERIFIERS[{phase_id!r}]: a {pv_floor:,}-byte file "
                f"(exactly the canonical floor) failed on size -- the verifier's real "
                f"runtime floor is above doctrine: {reasons}")

    assert not mismatches, (
        "min_bytes drift detected across independently-maintained copies of the "
        "same threshold -- these all gate the SAME artifact and must never "
        "disagree:\n  " + "\n  ".join(mismatches))


def test_phase_verifiers_delivery_min_bytes_matches_canonical():
    """The byte-size floor per key must come from the canonical spec, not a
    locally hardcoded (and driftable) number."""
    canonical_min_bytes = {s["key"]: s["min_bytes"] for s in deliverables.DELIVERABLE_AUDIT_SPEC}
    for item in pv._DELIVERY_DELIVERABLES:
        assert item["min_bytes"] == canonical_min_bytes[item["key"]], (
            f"{item['key']}: phase_verifiers min_bytes drifted from canonical spec")


def test_all_four_consumers_see_an_identical_key_set():
    """The acceptance bar for U05: every consumer's key set, compared pairwise
    against the canonical spec AND against each other, must be identical."""
    canonical = set(deliverables.REQUIRED_KEYS)
    consumer_key_sets = {
        "fix_bundle_complete.REQUIRED_KEYS": set(fbc.REQUIRED_KEYS),
        "curate.REQUIRED_KEYS": set(curate.REQUIRED_KEYS),
        "self_audit.DELIVERABLE_AUDIT_LIST": {i["key"] for i in self_audit.DELIVERABLE_AUDIT_LIST},
        "phase_verifiers._DELIVERY_DELIVERABLES": {i["key"] for i in pv._DELIVERY_DELIVERABLES},
    }
    for name, keys in consumer_key_sets.items():
        assert keys == canonical, (
            f"{name} drifted from the canonical whitelist: "
            f"missing={canonical - keys} extra={keys - canonical}")
    # And pairwise against each other, not just against canonical.
    all_sets = list(consumer_key_sets.values())
    for other in all_sets[1:]:
        assert other == all_sets[0]


# ---------------------------------------------------------------------------
# self_audit.py: no inline fallback -- a missing canonical source is a HARD
# ImportError, never a silent stale-copy audit.
# ---------------------------------------------------------------------------


def test_self_audit_hard_fails_when_canonical_source_unavailable(monkeypatch):
    """If presentation_job.deliverables cannot be imported, self_audit.py must
    raise ImportError at import time -- never fall back to a hardcoded list."""
    # Block the canonical module: setting a sys.modules entry to None makes
    # the import system raise ImportError for that name (stdlib-documented
    # negative-cache behavior), without touching the real module for other
    # tests in this session.
    monkeypatch.setitem(sys.modules, "presentation_job.deliverables", None)

    spec = importlib.util.spec_from_file_location(
        "self_audit_reload_for_test", str(SCRIPTS / "self_audit.py"))
    mod = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]


def test_self_audit_source_has_no_inline_deliverable_literal():
    """Structural guard: self_audit.py's `except ImportError` block must RAISE,
    never assign a fallback list literal (the exact bug this unit deletes --
    a deployed self-audit that silently keeps running against a stale
    hand-copied whitelist when the canonical import fails)."""
    src = (SCRIPTS / "self_audit.py").read_text()
    # No hardcoded per-deliverable filename literals of the kind the deleted
    # fallback contained (e.g. "DECK-FINAL.pptx" as a bare dict value) may
    # appear outside the derived comprehension.
    for literal in ("\"DECK-FINAL.pptx\"", "\"PRESENTER-GUIDE.pdf\"", "\"WEBINAR-VIDEO.mp4\""):
        assert literal not in src, (
            f"self_audit.py must not hardcode deliverable filenames like {literal} "
            f"-- DELIVERABLE_AUDIT_LIST must be derived from the imported canonical "
            f"spec only")
    # The except-block must raise, not silently assign a replacement spec.
    except_block = src.split("except ImportError", 1)[1].split("DELIVERABLE_AUDIT_LIST", 1)[0]
    assert "raise" in except_block, (
        "self_audit.py's except ImportError block must raise -- a caught "
        "ImportError that falls through to a fallback assignment is the "
        "exact silent-drift bug this unit deletes")
    assert "_AUDIT_SPEC = [" not in except_block, (
        "self_audit.py must not assign a fallback _AUDIT_SPEC list literal "
        "inside the except ImportError block")


# ---------------------------------------------------------------------------
# Import smoke — curate, phases (via phase_verifiers wiring), self_audit
# ---------------------------------------------------------------------------


def test_import_smoke_curate_phase_verifiers_self_audit():
    """All four consumers import cleanly with the single-sourced whitelist
    wired in, and phase_verifiers.PHASE_VERIFIERS still registers P9-DELIVER
    against the refactored _verify_delivery."""
    assert hasattr(curate, "DESTINATION_FILENAMES")
    assert hasattr(self_audit, "DELIVERABLE_AUDIT_LIST")
    assert "P9-DELIVER" in pv.PHASE_VERIFIERS
    # SLICE 3: P9-DELIVER is wired through the sealed-RunFacts shadow wrapper
    # (_shadow_composite_verifier) — report-only by default, stricter only
    # under PRES_TRUST_BOUNDARY_ENFORCE=1. The wrapper still delegates to the
    # refactored single-sourced _verify_delivery, so the whitelist contract
    # the legacy verifier enforces stays live on every report-only run.
    assert pv.PHASE_VERIFIERS["P9-DELIVER"] is not pv._verify_delivery
    assert pv.PHASE_VERIFIERS["P9-DELIVER"].__closure__ is not None
    wrapped = [c.cell_contents for c in pv.PHASE_VERIFIERS["P9-DELIVER"].__closure__]
    assert any(cell is pv._verify_delivery for cell in wrapped), (
        "P9-DELIVER shadow wrapper must delegate to the single-sourced "
        "_verify_delivery (legacy verdict still enforced report-only)")
