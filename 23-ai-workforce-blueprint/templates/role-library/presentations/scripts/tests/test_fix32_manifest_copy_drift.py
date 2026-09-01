#!/usr/bin/env python3
"""test_fix32_manifest_copy_drift.py — FIX 32 PROOF: real manifest drift detector.

The broken state FIX 32 exists for (verified on the operator box 2026-08-31):
the repo cluster copy of PIPELINE-MANIFEST.json and the materialized department
copy differed while BOTH were internally provenance-consistent — each copy's own
MANIFEST-SOURCE.txt hash matched its own file, so every per-copy check passed on
both copies simultaneously, and nothing anywhere compared the two. The
manifest_version field cannot catch this class: the live drift occurred WITHOUT
a version bump ("same version number, different bytes").

This file pins the three parts the FIX 32 spec demands:
  1. manifest_source.canonical_json_sha256 / compare_manifest_copies — a
     canonical-JSON content hash (sorted keys, no insignificant whitespace):
     a pure byte-level reformat is NOT drift; ANY value change IS.
  2. sync_check.copy_drift_checks — the (M1) drift item, class "render_path",
     wired into the sync_check drift list that CI GATE 5 and launch GATE 3
     consume (fail closed).
  3. The PROOF triple from the spec: a one-field change to either manifest copy
     trips the drift check; identical copies pass; a reformat-only copy passes.

Also pins the two honesty guarantees the first rev of FIX 32 lacked:
  - SELF-COMPARE GUARD: a peer that resolves to the resolved manifest itself
    is skipped and REPORTED, never silently "verified".
  - ROLLBACK FLAG: PRESENTATION_MANIFEST_COPY_DRIFT=0 prints the skip to stderr
    (never a silent pass).

Flat file in tests/, following the sibling convention (see
tests/test_manifest_assert.py for the same "no shared config, own import path"
pattern). No third-party deps beyond pytest.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import manifest_source  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: a minimal but structurally-real manifest (all four top-level keys
# load_manifest() requires), written to a scratch sops/ dir so MANIFEST-SOURCE
# installed-copy provenance is NOT involved — compare_manifest_copies operates
# on explicit paths.
# ---------------------------------------------------------------------------
def _manifest_obj() -> dict:
    return {
        "manifest_version": 54,
        "phases": [
            {"id": "P1-INTAKE", "label": "Intake", "order": 1},
            {"id": "P4-RENDER", "label": "Render", "order": 4},
        ],
        "autofails": [{"code": "AF-TEST-1", "py_symbol": "_chk_test_1"}],
        "roles": [{"id": "presentation-lead"}],
    }


def _write_manifest(dirpath: Path, obj: dict) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / "PIPELINE-MANIFEST.json"
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return p


def _copy(name: str) -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix=f"fix32_{name}_"))
    prim = _write_manifest(root / "primary", _manifest_obj())
    peer = _write_manifest(root / "peer", _manifest_obj())
    return prim, peer


# ---------------------------------------------------------------------------
# 1. canonical_json_sha256 — reformat-invariant, value-sensitive
# ---------------------------------------------------------------------------
def test_canonical_sha_ignores_byte_reformat():
    obj = _manifest_obj()
    a = json.dumps(obj, indent=2) + "\n"
    b = json.dumps(obj, indent=4)  # different indentation, no trailing newline
    assert a != b  # the bytes genuinely differ
    assert manifest_source.canonical_json_sha256(json.loads(a)) == \
        manifest_source.canonical_json_sha256(json.loads(b)), (
        "canonical-JSON hashing must treat a pure byte-level reformat (indent, "
        "key order, whitespace) as the SAME content — reformat is not drift.")


def test_canonical_sha_ignores_key_order():
    obj = _manifest_obj()
    reordered = {"roles": obj["roles"], "autofails": obj["autofails"],
                 "phases": obj["phases"], "manifest_version": 54}
    assert manifest_source.canonical_json_sha256(obj) == \
        manifest_source.canonical_json_sha256(reordered)


def test_canonical_sha_changes_on_one_field():
    obj = _manifest_obj()
    drifted = copy.deepcopy(obj)
    drifted["phases"][0]["label"] += " [one-field probe]"
    assert manifest_source.canonical_json_sha256(obj) != \
        manifest_source.canonical_json_sha256(drifted), (
        "a ONE-FIELD value change must hash differently — this is the exact "
        "drift class (same version, different content) FIX 32 exists to catch.")


# ---------------------------------------------------------------------------
# 2. compare_manifest_copies — the spec PROOF triple
# ---------------------------------------------------------------------------
def test_compare_identical_copies_no_drift():
    prim, peer = _copy("ident")
    r = manifest_source.compare_manifest_copies(str(prim), str(peer))
    assert r["drift"] is False
    assert r["primary_sha256"] == r["peer_sha256"]


def test_compare_one_field_change_same_version_trips():
    prim, peer = _copy("onefield")
    obj = json.loads(peer.read_text())
    same_version = obj["manifest_version"]
    obj["phases"][1]["label"] += " [GATE5 probe one-field]"
    peer.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    r = manifest_source.compare_manifest_copies(str(prim), str(peer))
    assert r["drift"] is True, (
        "a one-field change MUST trip the drift check even at the SAME "
        "manifest_version — the version field cannot detect this class.")
    assert r["same_version_number"] is True, (
        "the probe must hold the version CONSTANT: 'same version, different "
        "bytes' is exactly the live broken state this detector exists for.")
    assert r["primary_sha256"] != r["peer_sha256"]


def test_compare_reformat_only_no_drift():
    prim, peer = _copy("reformat")
    obj = json.loads(peer.read_text())
    peer.write_text(json.dumps(obj, indent=4), encoding="utf-8")  # reformat only
    r = manifest_source.compare_manifest_copies(str(prim), str(peer))
    assert r["drift"] is False, (
        "a byte-level reformat of identical JSON content is NOT drift under "
        "canonical-JSON hashing.")


def test_compare_missing_peer_refuses_loud():
    prim, _ = _copy("missing")
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import manifest_source; "
         "manifest_source.compare_manifest_copies(%r, %r)"
         % (str(SCRIPTS), str(prim), "/nonexistent/PIPELINE-MANIFEST.json")],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 2, "a missing peer must refuse loudly (exit 2), not silently pass"
    assert "FIX 32 copy comparison cannot run" in r.stderr


# ---------------------------------------------------------------------------
# 3. sync_check.copy_drift_checks — M1 wired, class render_path, honest skips
# ---------------------------------------------------------------------------
def _load_sync_check():
    spec = importlib.util.spec_from_file_location(
        "_sync_check_under_test", SCRIPTS / "sync_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_copy_drift_checks_trips_m1_on_one_field_change():
    prim, peer = _copy("m1trip")
    obj = json.loads(peer.read_text())
    obj["phases"][0]["label"] += " [one-field]"
    peer.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    import os
    old = os.environ.pop("PRESENTATION_MANIFEST_COPY_DRIFT", None)
    os.environ["PRESENTATION_MANIFEST_COPY"] = str(peer)
    try:
        sync_check = _load_sync_check()
        sync_check.MANIFEST = prim  # resolve the module to the fixture primary
        drift = sync_check.copy_drift_checks(_manifest_obj())
    finally:
        os.environ.pop("PRESENTATION_MANIFEST_COPY", None)
        if old is not None:
            os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = old
    m1 = [d for d in drift if d.get("check") == "M1"]
    assert len(m1) == 1, f"expected exactly one M1 item, got {drift!r}"
    assert m1[0]["class"] == "render_path", (
        "M1 must carry class render_path so GATE 3 fails closed at launch "
        "(it is NOT library-only A5/A6 debt).")
    assert "MANIFEST COPY DRIFT" in m1[0]["detail"]


def test_copy_drift_checks_passes_identical_copies():
    prim, peer = _copy("m1clean")
    import os
    old = os.environ.pop("PRESENTATION_MANIFEST_COPY_DRIFT", None)
    os.environ["PRESENTATION_MANIFEST_COPY"] = str(peer)
    try:
        sync_check = _load_sync_check()
        sync_check.MANIFEST = prim  # resolve the module to the fixture primary
        drift = sync_check.copy_drift_checks(_manifest_obj())
    finally:
        os.environ.pop("PRESENTATION_MANIFEST_COPY", None)
        if old is not None:
            os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = old
    assert drift == [], f"identical copies must produce NO drift, got {drift!r}"


def test_copy_drift_checks_rollback_flag_reports_skip_not_silent_pass(capsys):
    prim, peer = _copy("rollback")
    import os
    old = os.environ.get("PRESENTATION_MANIFEST_COPY_DRIFT")
    os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = "0"
    os.environ["PRESENTATION_MANIFEST_COPY"] = str(peer)
    try:
        sync_check = _load_sync_check()
        sync_check.MANIFEST = prim  # resolve the module to the fixture primary
        drift = sync_check.copy_drift_checks(_manifest_obj())
    finally:
        os.environ.pop("PRESENTATION_MANIFEST_COPY", None)
        if old is not None:
            os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = old
        else:
            os.environ.pop("PRESENTATION_MANIFEST_COPY_DRIFT", None)
    assert drift == []
    captured = capsys.readouterr()
    assert "DISABLED by rollback flag" in captured.err, (
        "the =0 rollback path must PRINT its skip to stderr — it never "
        "silently pretends an unverified copy was verified.")


def test_copy_drift_checks_missing_peer_reports_skip_not_drift():
    prim, _ = _copy("nopeer")
    import os
    old = os.environ.pop("PRESENTATION_MANIFEST_COPY_DRIFT", None)
    os.environ["PRESENTATION_MANIFEST_COPY"] = "/nonexistent-peer/PIPELINE-MANIFEST.json"
    try:
        sync_check = _load_sync_check()
        sync_check.MANIFEST = prim  # resolve the module to the fixture primary
        drift = sync_check.copy_drift_checks(_manifest_obj())
    finally:
        os.environ.pop("PRESENTATION_MANIFEST_COPY", None)
        if old is not None:
            os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = old
    assert drift == [], "a missing peer is an honest SKIP, not drift and not a crash"


def test_copy_drift_checks_self_compare_guard_skips():
    # A peer that IS the resolved manifest must never be "verified" against
    # itself — the exact silent no-op class the self-compare guard exists for.
    prim, peer = _copy("selfcmp")
    import os
    old = os.environ.pop("PRESENTATION_MANIFEST_COPY_DRIFT", None)
    os.environ["PRESENTATION_MANIFEST_COPY"] = str(prim)  # SAME file as MANIFEST
    try:
        sync_check = _load_sync_check()
        # Point the module's resolved MANIFEST at the primary copy.
        sync_check.MANIFEST = prim
        drift = sync_check.copy_drift_checks(_manifest_obj())
    finally:
        os.environ.pop("PRESENTATION_MANIFEST_COPY", None)
        if old is not None:
            os.environ["PRESENTATION_MANIFEST_COPY_DRIFT"] = old
    assert drift == [], f"self-compare must skip, not false-pass: {drift!r}"


# ---------------------------------------------------------------------------
# 4. End-to-end: sync_check.py --json against the LIVE repo, peer = repo copy
#    (the one-second CI-style proof: identical copies pass, in_sync true)
# ---------------------------------------------------------------------------
def test_live_repo_sync_check_passes_with_repo_copy_as_peer():
    manifest = SCRIPTS.parents[2].parents[1] / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    if not manifest.is_file():
        import pytest
        pytest.skip("live repo cluster manifest not present in this checkout")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "sync_check.py"), "--json"],
        capture_output=True, text=True, timeout=180,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin",
             "PRESENTATION_MANIFEST_COPY": str(manifest),
             "HOME": "/nonexistent-home-for-test-isolation"},
    )
    parsed = json.loads(proc.stdout)
    m1 = [d for d in parsed.get("drift", []) if d.get("check") == "M1"]
    assert m1 == [], (
        "with the peer equal to the resolved cluster manifest the repo must "
        "report NO M1 copy drift — identical copies PASS (spec PROOF).")
    assert parsed["in_sync"] is True, (
        f"expected in_sync=true with no other drift; got drift="
        f"{[d['check'] for d in parsed.get('drift', [])]}")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))