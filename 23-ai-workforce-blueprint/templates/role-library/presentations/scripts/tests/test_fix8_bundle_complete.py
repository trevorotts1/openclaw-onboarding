"""Tests for FIX-8 — the full 9-deliverable bundle gate (bundle_complete.json).

Bar (Gauntlet Loop FIX-8 / T-09 / M2-M9):
  * a DECK-ONLY bundle FAILS, enumerating exactly which deliverables are missing;
  * the FULL 9-deliverable bundle PASSES and writes bundle_complete.json;
  * a zero-byte / placeholder file is NOT 'done' (non-empty is required);
  * the gate is fail-closed: a partial bundle never gets a pass marker, and a
    stale pass marker is removed when the bundle regresses.

No network. Stdlib + pytest/tmp_path only — the gate must run identically on a
deployed client box without python-pptx.
"""

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fix_bundle_complete as fbc  # noqa: E402

REQUIRED_KEYS = fbc.REQUIRED_KEYS


def _write_full_bundle(base: pathlib.Path, deck_slug: str = "deck") -> None:
    """Write all nine deliverables as real non-empty files."""
    for spec in fbc.REQUIRED_DELIVERABLES:
        fname = fbc._expand_filename(spec["filename"], deck_slug)
        (base / fname).write_bytes(b"x" * 2048)


def _write_deck_only(base: pathlib.Path, deck_slug: str = "deck") -> None:
    """Write ONLY the deck pptx (the live E2E failure: 8 of 9 missing)."""
    (base / fbc._expand_filename("{deck_slug}-FINAL.pptx", deck_slug)).write_bytes(b"x" * 2048)


# ---------------------------------------------------------------------------
# The FIX-8 bar: deck-only fails enumerating missing; full bundle passes.
# ---------------------------------------------------------------------------


def test_deck_only_fails_and_enumerates_missing(tmp_path):
    """A bundle with ONLY the deck pptx must FAIL with AF-BUNDLE-INCOMPLETE and
    enumerate exactly the eight missing deliverables."""
    base = tmp_path / "deck-only"
    base.mkdir(parents=True)
    _write_deck_only(base)

    missing = fbc.check_bundle_complete(base, deck_slug="deck")
    expected = set(REQUIRED_KEYS) - {"deck_pptx"}
    assert set(missing) == expected, (
        f"deck-only must report exactly the 8 missing keys; got {sorted(missing)}")

    ok, missing_run, gate = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok is False, "a deck-only bundle must fail the gate"
    assert set(missing_run) == expected, f"gate must enumerate missing; got {sorted(missing_run)}"
    assert gate is None, "no bundle_complete.json may be written on failure"


def test_full_bundle_passes_and_writes_gate(tmp_path):
    """All nine deliverables present and non-empty -> PASS, bundle_complete.json
    written with complete:true and all 9 recorded."""
    base = tmp_path / "full"
    base.mkdir(parents=True)
    _write_full_bundle(base)

    missing = fbc.check_bundle_complete(base, deck_slug="deck")
    assert missing == [], f"full bundle must have nothing missing; got {sorted(missing)}"

    ok, missing_run, gate = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok is True, f"full bundle must pass; got missing={sorted(missing_run)}"
    assert gate is not None and gate.is_file(), "bundle_complete.json must be written"
    rec = json.loads(gate.read_text())
    assert rec.get("complete") is True
    assert rec.get("deliverable_count") == len(REQUIRED_KEYS) == 9
    assert set(rec.get("deliverables", {})) == set(REQUIRED_KEYS)


def test_zero_byte_placeholder_is_not_done(tmp_path):
    """A zero-byte file is NOT 'done' — non-empty is part of the contract."""
    base = tmp_path / "zero"
    base.mkdir(parents=True)
    (base / "deck-FINAL.pptx").write_bytes(b"")  # empty placeholder
    (base / "PRESENTERS-SPEECH.md").write_text("real speech text")

    missing = fbc.check_bundle_complete(base, deck_slug="deck")
    assert "deck_pptx" in missing, "a zero-byte deck_pptx must count as missing"
    assert "speech_md" not in missing, "a real non-empty speech_md must not be missing"


def test_stale_pass_marker_removed_on_regression(tmp_path):
    """Fail-closed: a previously-passed bundle_complete.json is removed the moment
    the bundle regresses, so a partial bundle is never reported done."""
    base = tmp_path / "regress"
    base.mkdir(parents=True)
    _write_full_bundle(base)
    ok, _m, gate = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok is True and gate is not None

    # Now delete one deliverable -> the bundle regresses.
    (base / "PRESENTER-AUDIO.mp3").unlink()
    ok2, missing2, gate2 = fbc.run_bundle_gate(base, deck_slug="deck")
    assert ok2 is False, "a regressed bundle must fail"
    assert "audio_mp3" in missing2
    assert gate2 is None
    assert not (base / fbc.BUNDLE_COMPLETE_FILENAME).exists(), (
        "a stale bundle_complete.json must be removed on regression")


def test_deck_slug_templating(tmp_path):
    """{deck_slug}-templated filenames resolve correctly for a slugged bundle."""
    base = tmp_path / "acme"
    base.mkdir(parents=True)
    _write_full_bundle(base, deck_slug="acme-q1")
    ok, missing, gate = fbc.run_bundle_gate(base, deck_slug="acme-q1")
    assert ok is True, f"slugged full bundle must pass; got missing={sorted(missing)}"
    assert gate is not None and gate.is_file()
    rec = json.loads(gate.read_text())
    assert rec.get("deck_slug") == "acme-q1"


def test_resolve_bundle_dir_recorded_in_process_manifest(tmp_path):
    """resolve_bundle_dir honors the bundleDir recorded in process_manifest.json."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "process_manifest.json").write_text(json.dumps({"bundleDir": str(tmp_path / "bundle")}))
    resolved = fbc.resolve_bundle_dir(run_dir)
    assert resolved == tmp_path / "bundle", f"bundleDir from manifest must win; got {resolved}"


def test_in_pipeline_runner_resolution_path(tmp_path):
    """The exact code path the P9-DELIVER guard uses (resolve_bundle_dir from the
    recorded process_manifest bundleDir + run_bundle_gate) must fail closed on a
    deck-only bundle and pass on a full bundle."""
    import run_signature_deck as rsd
    run_dir = tmp_path / "the-run-abc"
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "process_manifest.json").write_text(
        json.dumps({"bundleDir": str(tmp_path / "bundle")}))
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)

    slug = rsd._deck_slug(run_dir)
    (bundle / fbc._expand_filename("{deck_slug}-FINAL.pptx", slug)).write_bytes(b"x" * 2048)

    resolved = fbc.resolve_bundle_dir(run_dir)
    assert resolved == tmp_path / "bundle", "bundleDir from process_manifest must win"
    ok, missing, gate = fbc.run_bundle_gate(resolved, deck_slug=slug)
    assert ok is False, "deck-only must fail the runner's FIX-8 gate"
    assert set(missing) == set(REQUIRED_KEYS) - {"deck_pptx"}
    assert gate is None

    for spec in fbc.REQUIRED_DELIVERABLES:
        (bundle / fbc._expand_filename(spec["filename"], slug)).write_bytes(b"x" * 2048)
    ok2, missing2, gate2 = fbc.run_bundle_gate(bundle, deck_slug=slug)
    assert ok2 is True and missing2 == [] and gate2 is not None and gate2.is_file()


def test_manifest_lockstep():
    """The nine REQUIRED_KEYS must equal PIPELINE-MANIFEST.build_bundle_files —
    they must never drift apart."""
    import os
    cur = pathlib.Path(fbc.__file__).resolve().parent
    manifest = None
    for _ in range(8):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            manifest = cand
            break
        cur = cur.parent
    assert manifest is not None, "PIPELINE-MANIFEST.json not found"
    man = json.loads(manifest.read_text())
    assert sorted(man.get("build_bundle_files", [])) == sorted(REQUIRED_KEYS), (
        "PIPELINE-MANIFEST.build_bundle_files drifted from fix_bundle_complete.REQUIRED_KEYS")

    # The emitted AF code must stay registered (sync_check C1 lockstep).
    codes = {a["code"] for a in man["autofails"]}
    assert "AF-BUNDLE-INCOMPLETE" in codes, (
        "AF-BUNDLE-INCOMPLETE must be registered in PIPELINE-MANIFEST.autofails")
