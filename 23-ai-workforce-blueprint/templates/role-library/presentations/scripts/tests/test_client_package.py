"""U019 (D02, ratified 2026-07-26) — the teleprompter is the sixth client-package file.

Standard library plus pytest, tmp_path, no network. Flat file beside the code it
tests: there is no shared configuration file and no scripts/tests/ convention beyond
this directory, so this file manages its own import path (matching every sibling in
this directory, e.g. test_gates.py).

Manifest location is resolved by WALKING UP from this file to the first ancestor
directory that contains universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
— never a fixed ../../../../../ chain, which is only correct when run from the
scripts directory and resolves outside the checkout entirely from anywhere else
(e.g. the QC Q7 mutation-proof scratch tree). If no ancestor carries it, the affected
tests FAIL with a message naming the locator — a skipped manifest test is a green
suite that proved nothing.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import delivery_gate as dg  # noqa: E402

MANIFEST_REL = pathlib.Path("universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json")
SOURCE_REL = pathlib.Path("universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt")


def _find_manifest_root(start: pathlib.Path) -> pathlib.Path | None:
    """Walk up from `start` to the first ancestor whose tree contains
    universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json. Returns None if no
    ancestor carries it. This is the ONLY manifest locator this file uses — no fixed
    '../../../../../' chain anywhere below."""
    cur = start.resolve()
    seen = set()
    while cur not in seen:
        seen.add(cur)
        if (cur / MANIFEST_REL).is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _require_manifest_root() -> pathlib.Path:
    root = _find_manifest_root(pathlib.Path(__file__).parent)
    if root is None:
        pytest.fail(
            "no ancestor of this test file contains "
            f"{MANIFEST_REL} — _find_manifest_root (this file's own locator) could not "
            "resolve the manifest. This is a FAIL, never a skip: a skipped manifest "
            "test is a green suite that proved nothing.")
    return root


def _load_manifest() -> dict:
    root = _require_manifest_root()
    return json.loads((root / MANIFEST_REL).read_text())


def _manifest_path() -> pathlib.Path:
    return _require_manifest_root() / MANIFEST_REL


# ---------------------------------------------------------------------------
# Package-directory fixture helper (mirrors delivery_gate.py's own _mk_pkg, kept
# independent so this file has no import-order dependency on delivery_gate's
# selftest internals beyond the public/module-level names it already exposes).
# ---------------------------------------------------------------------------
def _mk_pkg(names):
    d = pathlib.Path(tempfile.mkdtemp()) / "demo-deck-FINAL"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(b"x" * 4096)
    return d


def _six_names() -> list[str]:
    man = _load_manifest()
    req = {e["key"]: e["filename"] for e in man["deliverables_required"]}
    return [req[k].replace("{deck_slug}", "demo-deck") for k in man["client_package_files"]]


# ---------------------------------------------------------------------------
# 1 & 2 — _categorize resolves the new exact name, and NOT the old fixture name.
# ---------------------------------------------------------------------------
def test_categorize_resolves_teleprompter_html():
    assert dg._categorize("presenter-teleprompter.html") == "teleprompter_html"


def test_categorize_rejects_old_fixture_name():
    # "teleprompter.html" is the OLD run-dir fixture name (delivery_gate.py's
    # _mk_full_run writes it under working/teleprompter/). It must NOT satisfy the
    # client-package slot, or a stale producer output silently fills it.
    assert dg._categorize("teleprompter.html") == ""


# ---------------------------------------------------------------------------
# 3 — a six-file package passes.
# ---------------------------------------------------------------------------
def test_six_file_package_passes():
    six = _six_names()
    assert dg.check_af_dh1(_mk_pkg(six)) == ""


# ---------------------------------------------------------------------------
# 4 — stage 1 (shipped): missing teleprompter warns but passes. stage 3 (toggled):
# missing teleprompter fails and names the key. Same package dir, same code path,
# only CLIENT_PACKAGE_WARN_ONLY changes.
# ---------------------------------------------------------------------------
def test_stage1_missing_teleprompter_warns_but_passes(capsys):
    six = _six_names()
    five = [n for n in six if n != "presenter-teleprompter.html"]
    assert "teleprompter_html" in dg.CLIENT_PACKAGE_WARN_ONLY
    result = dg.check_af_dh1(_mk_pkg(five))
    assert result == "", f"stage 1 must still PASS on a missing warn-only key, got {result!r}"
    out = capsys.readouterr().out
    assert "teleprompter_html" in out, (
        "stage 1 must record the warning (printed) even though it does not fail — "
        f"captured stdout was: {out!r}")


def test_stage3_missing_teleprompter_fails_when_warn_only_cleared(monkeypatch):
    six = _six_names()
    five = [n for n in six if n != "presenter-teleprompter.html"]
    monkeypatch.setattr(dg, "CLIENT_PACKAGE_WARN_ONLY", frozenset())
    result = dg.check_af_dh1(_mk_pkg(five))
    assert result != "", "stage 3 (CLIENT_PACKAGE_WARN_ONLY cleared) must FAIL on a missing teleprompter"
    assert "teleprompter_html" in result, f"the failure reason must name the missing key, got {result!r}"


# ---------------------------------------------------------------------------
# 5 — duplicate-slot vs. whitelist. A suffix slot (deck_pptx / deck_pdf) IS
# genuinely duplicable; teleprompter_html, mapped by an EXACT name, is not — two
# files literally cannot share one filename in one directory, so a "sibling" like
# presenter-teleprompter.html.bak falls through to the whitelist message instead.
# ---------------------------------------------------------------------------
def test_duplicate_suffix_slot_trips_duplicate_slot_error():
    six = _six_names()
    pkg = _mk_pkg(six + ["other-FINAL.pptx"])
    result = dg.check_af_dh1(pkg)
    assert "two files map to the same client slot" in result, result
    assert "deck_pptx" in result, result


def test_teleprompter_sibling_cannot_duplicate_the_slot():
    six = _six_names()
    pkg = _mk_pkg(six + ["presenter-teleprompter.html.bak"])
    result = dg.check_af_dh1(pkg)
    assert result != "", "an unrecognized sibling file must fail AF-DH1"
    assert "whitelist" in result, (
        f"presenter-teleprompter.html.bak must fail on the WHITELIST message (it does "
        f"not resolve to any category), not the duplicate-slot message — got {result!r}")
    assert "two files map to the same client slot" not in result, result


# ---------------------------------------------------------------------------
# 6 — six files plus one extra fails, and the message names the count.
# ---------------------------------------------------------------------------
def test_extra_file_fails_with_six_item_whitelist_message():
    six = _six_names()
    pkg = _mk_pkg(six + ["notes-draft.md"])
    result = dg.check_af_dh1(pkg)
    assert result != ""
    assert "seven-item" in result, f"expected the seven-item whitelist count in the message, got {result!r}"


# ---------------------------------------------------------------------------
# 7 — client_package_files has 6 entries and every one appears in deliverables_required.
# ---------------------------------------------------------------------------
def test_manifest_client_package_files_has_seven_entries_all_in_deliverables_required():
    man = _load_manifest()
    cpf = man["client_package_files"]
    assert len(cpf) == 7, f"expected 7 client_package_files, got {len(cpf)}: {cpf}"
    req_keys = {e["key"] for e in man["deliverables_required"]}
    missing = [k for k in cpf if k not in req_keys]
    assert not missing, f"client_package_files keys absent from deliverables_required: {missing}"


# ---------------------------------------------------------------------------
# 8 — every filename in client_package_files is reachable through _categorize.
# This is the test that makes Site 1 (_categorize) and Site 15 (the manifest) unable
# to drift apart from each other.
# ---------------------------------------------------------------------------
def test_every_client_package_file_round_trips_through_categorize():
    man = _load_manifest()
    req = {e["key"]: e["filename"] for e in man["deliverables_required"]}
    bad = []
    for key in man["client_package_files"]:
        filename = req.get(key, "").replace("{deck_slug}", "demo-deck")
        if dg._categorize(filename) != key:
            bad.append((key, filename, dg._categorize(filename)))
    assert not bad, f"keys that do not round-trip through _categorize: {bad}"


# ---------------------------------------------------------------------------
# 9 — EXACT_NAME_WHITELIST, if it still exists (Site 3 permits deletion as dead
# code), must not itself drift: every entry it carries must be one _categorize
# actually matches by exact name.
# ---------------------------------------------------------------------------
def test_exact_name_whitelist_if_present_matches_categorize():
    whitelist = getattr(dg, "EXACT_NAME_WHITELIST", None)
    if whitelist is None:
        pytest.skip("EXACT_NAME_WHITELIST does not exist in this tree — it was deleted "
                    "as dead code (Site 3; a *.py census this ticket records found zero "
                    "readers outside its own definition) — nothing to check")
    bad = [name for name in whitelist if dg._categorize(name) == ""]
    assert not bad, f"EXACT_NAME_WHITELIST entries _categorize does not match: {bad}"


# ---------------------------------------------------------------------------
# 10 — the repository manifest and the box copy the U004 handoff produces must
# agree on client_package_files, with no drift. This unit only edits the repository
# copy (the two box copies are handed to U004 — Touches: note). Skip with a clear
# message if the second is absent, OR if what's on disk at that path predates the
# U004 handoff (its manifest_version is still behind the repository's): in that case
# "the copy the U004 handoff produced" does not exist yet, and asserting equality
# against a pre-handoff artifact would report a false failure for a handoff that
# has not happened. Once U004 lands, this becomes a real drift-catcher.
# ---------------------------------------------------------------------------
def test_manifest_agrees_with_post_handoff_box_copy():
    repo = _load_manifest()
    # Box paths are always relative to the OPERATOR'S home directory, never a
    # hardcoded machine name — this repo is a fleet-wide template and a literal
    # "/Users/<operator>/..." path must never be committed (portability + the
    # repo's own client-name/operator-path guard, scripts/qc-assert-no-client-names.sh).
    home = pathlib.Path.home()
    box_paths = [
        home / ".openclaw/skills/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json",
        home / ".openclaw/workspace/departments/Presentations/sops/PIPELINE-MANIFEST.json",
    ]
    compared = []
    for box_path in box_paths:
        if not box_path.is_file():
            continue
        box = json.loads(box_path.read_text())
        if box.get("manifest_version", -1) < repo["manifest_version"]:
            continue  # pre-handoff artifact — U004 has not landed this box copy yet
        compared.append(box_path)
        assert box["client_package_files"] == repo["client_package_files"], (
            f"{box_path} has drifted from the repository copy after the U004 handoff")
    if not compared:
        pytest.skip("no post-handoff box copy found in this environment (either the "
                     "path does not exist, or it has not yet been updated by U004) — "
                     "nothing to compare")


# ---------------------------------------------------------------------------
# 11 — MANIFEST-SOURCE.txt's content_sha256= equals the manifest's real sha256.
# ---------------------------------------------------------------------------
def test_manifest_source_stamp_matches_actual_hash():
    import hashlib
    root = _require_manifest_root()
    manifest_path = root / MANIFEST_REL
    source_path = root / SOURCE_REL
    assert source_path.is_file(), f"{source_path} does not exist"
    want = ""
    for line in source_path.read_text().splitlines():
        if line.startswith("content_sha256="):
            want = line.split("=", 1)[1].strip()
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert want == actual, f"stamp {want!r} != actual {actual!r}"


# ---------------------------------------------------------------------------
# 12 — _assert_manifest_current accepts the bumped manifest and REJECTS a fixture
# one version below it. The rejected version is derived as manifest_version - 1,
# never a literal — six manifest writers land ahead of this unit, so today's value
# is not tomorrow's.
# ---------------------------------------------------------------------------
def test_assert_manifest_current_accepts_bumped_and_rejects_one_version_below():
    if SCRIPTS not in [pathlib.Path(p) for p in sys.path]:
        sys.path.insert(0, str(SCRIPTS))
    try:
        from presentation_job.manifest import _assert_manifest_current, MIN_MANIFEST_VERSION
    except ModuleNotFoundError:
        pytest.fail("presentation_job is not importable from this tree. U011 lands it "
                     "as NEW (SPEC/units/U011.md:26-37); this test cannot run until U011 "
                     "has merged. This is a FAIL, never a skip.")
    manifest_path = _manifest_path()
    obj = json.loads(manifest_path.read_text())
    assert MIN_MANIFEST_VERSION == obj["manifest_version"], (
        f"MIN_MANIFEST_VERSION ({MIN_MANIFEST_VERSION}) must equal manifest_version "
        f"({obj['manifest_version']}) — the floor must move WITH the manifest")
    # ACCEPT: the real, on-disk, bumped manifest.
    _assert_manifest_current(manifest_path)  # must not raise

    # REJECT: a fixture one version below, in its own scratch dir (never mutate the
    # tracked manifest). No sidecar stamp is written beside it, so the stale-version
    # check (not the stamp-mismatch check) is what trips.
    old = dict(obj)
    old["manifest_version"] = obj["manifest_version"] - 1
    scratch = pathlib.Path(tempfile.mkdtemp())
    fixture = scratch / "PIPELINE-MANIFEST.json"
    fixture.write_text(json.dumps(old))
    with pytest.raises(SystemExit) as exc_info:
        _assert_manifest_current(fixture)
    assert exc_info.value.code == 7, f"expected exit 7 (EXIT_MANIFEST_MISMATCH), got {exc_info.value.code}"


# ---------------------------------------------------------------------------
# 13 — _mk_full_run(teleprompter=False) still produces the CASE K
# AF-BUNDLE-COMPLETE rejection (the negative fixture this change is most likely to
# silently invert).
# ---------------------------------------------------------------------------
def test_mk_full_run_teleprompter_false_still_trips_case_k():
    with tempfile.TemporaryDirectory() as t:
        base = pathlib.Path(t)
        deck = dg._mk_full_run(base, with_text=False, task_ids=("kie-aaa",), teleprompter=False)
        ok, reasons = dg.gate_delivered_artifact(deck, base)
        assert not ok
        assert any("AF-BUNDLE-COMPLETE" in r and "teleprompter" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# 14 — the renamed no-audio fixture omits the AUDIO file by NAME, not by slice
# position (CLIENT_PACKAGE's last element is now the teleprompter, so a positional
# [:-1] would silently drop the wrong file).
# ---------------------------------------------------------------------------
def test_no_audio_fixture_excludes_audio_by_name_not_position():
    # Feature L2-G adds webinar_mp4 as the LAST client-package element (demo-deck-WEBINAR.mp4).
    # The test's real premise is: audio_mp3 is NOT last, so a positional slice that drops
    # the last element never drops the audio file. The audio is 5th; the last is the webinar.
    assert dg.CLIENT_PACKAGE[-1] == "demo-deck-WEBINAR.mp4", (
        "this test's premise (the last element is the webinar, not the audio file) no "
        "longer holds — a positional slice would drop the wrong file")
    no_audio = [f for f in dg.CLIENT_PACKAGE if f != "PRESENTER-AUDIO.mp3"]
    assert "PRESENTER-AUDIO.mp3" not in no_audio
    assert "presenter-teleprompter.html" in no_audio
    result = dg.check_af_dh1(_mk_pkg(no_audio))
    assert result != "" and "audio_mp3" in result, (
        f"expected an AF-DH1 failure naming audio_mp3, got {result!r}")
