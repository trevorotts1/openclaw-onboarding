"""PD-207 — the upload step needs an upload record.

Spec (01-BUILD-SPEC.md, "### PD-207"): in `_verify_ghl_upload` (keep one
definition; delete the byte-identical second copy): a missing, unreadable or
non-object record returns `False` with "media_library.json is missing — the
upload did not run". A missing `ghl_folder_id` is a failure, not a note.

Acceptance row A1: the PD-207 probe as a test — empty run -> fail; a record with
ids -> pass (the network list-back stubbed away).

No network: `ghl_media`'s three functions are monkeypatched on the module object
that `_verify_ghl_upload` imports lazily.
"""

from __future__ import annotations

import ast
import json
import pathlib

NO_RECORD = "media_library.json is missing — the upload did not run"
SRC = pathlib.Path(__file__).resolve().parents[1] / "phase_verifiers.py"


def _ledger(base: pathlib.Path, body) -> None:
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    (ck / "media_library.json").write_text(
        body if isinstance(body, str) else json.dumps(body))


def _stub_transport(monkeypatch, *, listing):
    import ghl_media
    monkeypatch.setattr(ghl_media, "resolve_location_pit", lambda: "pit-token")
    monkeypatch.setattr(ghl_media, "resolve_location_id", lambda: "loc-1")
    monkeypatch.setattr(ghl_media, "list_media",
                        lambda loc, pit, **kw: {"http": 200, "data": listing})


def _hard(reasons):
    return [r for r in reasons if not str(r).startswith("NOTE")]


# --- A1, first half: empty run fails -------------------------------------


def test_missing_record_fails_with_the_spec_message(tmp_path):
    import phase_verifiers as pv
    ok, reasons = pv._verify_ghl_upload(tmp_path / "empty")
    assert ok is False
    assert reasons == [NO_RECORD]


def test_unreadable_record_fails(tmp_path):
    import phase_verifiers as pv
    base = tmp_path / "run"
    _ledger(base, "{not json at all")
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert reasons == [NO_RECORD]


def test_non_object_record_fails(tmp_path):
    import phase_verifiers as pv
    base = tmp_path / "run"
    _ledger(base, ["a", "list", "not", "an", "object"])
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert reasons == [NO_RECORD]


# --- A1, second half: a record with ids passes (network stubbed) ---------


def test_record_with_ids_passes_with_stubbed_transport(tmp_path, monkeypatch):
    import phase_verifiers as pv
    base = tmp_path / "run"
    _ledger(base, {"ghl_folder_id": "fld-1", "pptx_ghl_media_id": "file_deck",
                   "pptx_ghl_remote_name": "DECK demo.pptx"})
    _stub_transport(monkeypatch, listing=[{"name": "DECK demo.pptx", "_id": "file_deck"}])
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is True, reasons
    assert _hard(reasons) == []


# --- ghl_folder_id is a failure, not a note ------------------------------


def test_missing_folder_id_fails_even_when_listing_finds_the_deck(tmp_path, monkeypatch):
    import phase_verifiers as pv
    base = tmp_path / "run"
    _ledger(base, {"pptx_ghl_media_id": "file_deck",
                   "pptx_ghl_remote_name": "DECK demo.pptx"})
    _stub_transport(monkeypatch, listing=[{"name": "DECK demo.pptx", "_id": "file_deck"}])
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert any("ghl_folder_id" in r for r in reasons)
    assert not any(str(r).startswith("NOTE: ghl_folder_id") for r in reasons), \
        "a missing folder id must be a failure, not a NOTE"


def test_missing_folder_id_fails_when_the_list_back_is_skipped(tmp_path, monkeypatch):
    """Fail-soft transport must not soften a hard reason into a pass."""
    import ghl_media
    import phase_verifiers as pv
    base = tmp_path / "run"
    _ledger(base, {"pptx_ghl_media_id": "file_deck", "pptx_ghl_remote_name": "D.pptx"})
    monkeypatch.setattr(ghl_media, "resolve_location_pit", lambda: "")
    monkeypatch.setattr(ghl_media, "resolve_location_id", lambda: "loc-1")
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert any("ghl_folder_id" in r for r in reasons)


# --- one definition ------------------------------------------------------


def test_only_one_definition_of_the_verifier():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    defs = [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert defs.count("_verify_ghl_upload") == 1, \
        f"expected one _verify_ghl_upload, found {defs.count('_verify_ghl_upload')}"
