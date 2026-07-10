#!/usr/bin/env python3
"""test_stage_s8_deliver.py -- offline contract test for the S8 dispatcher's
delivered Google Doc link (scripts/stage_s8_deliver.py).

Regression cover for the doc-url key defect: drive_adapter.deliver_doc() returns
the live Doc link under the key "doc_url" (its files_get webViewLink) and the
file id under "doc_id" -- NOT a top-level webViewLink/link/id. The dispatcher
must ship that real link to caf_delivery (--doc-url) and record it on the ledger,
NOT None.

Network-free: every collaborator subprocess (drive_adapter, caf_delivery,
anthology_state, ...) is mocked; no live Google is touched. The drive_adapter
mock returns deliver_doc()'s EXACT return shape (drive_adapter.py deliver_doc()).

Run: python3 -m pytest 59-anthology-engine/tests/test_stage_s8_deliver.py -q
"""
import json
import sys
import types
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import stage_s8_deliver as s8  # noqa: E402

# The live Google Doc link deliver_doc() would hand back (its webViewLink).
REAL_DOC_LINK = "https://docs.google.com/document/d/DOCID_REAL_1234/edit"
DRIVE_FOLDER_ID = "FOLDER_XYZ_1"


def _deliver_doc_true_shape():
    """The EXACT dict drive_adapter.deliver_doc() emits (drive_adapter.py).

    Note the keys: doc_url + doc_id -- there is NO top-level webViewLink/link/id."""
    return {
        "ok": True, "action": "create-doc", "doc_id": "DOCID_REAL_1234",
        "name": "CONTACT1-avatar", "doc_url": REAL_DOC_LINK,
        "view_shared": True, "permission_id": "perm_1", "verified": True,
    }


def _make_fake_run(captured):
    """A stage_s8_deliver.subprocess.run stand-in that routes by collaborator."""
    def fake_run(argv, *args, **kwargs):
        script = Path(argv[1]).name if len(argv) > 1 else ""
        out = "{}"
        if script == "anthology_state.py" and "get-participant" in argv:
            out = json.dumps({"drive_folder_id": DRIVE_FOLDER_ID,
                              "participant_key": "CONTACT1::ANTH1"})
        elif script == "anthology_state.py" and "record-artifact" in argv:
            captured["record_artifact_argv"] = list(argv)
            out = json.dumps({"ok": True})
        elif script == "drive_adapter.py":
            captured["drive_argv"] = list(argv)
            out = json.dumps(_deliver_doc_true_shape())
        elif script == "pdf_render.py":
            out = json.dumps({"ok": True})  # no real PDF written to disk
        elif script == "anthology_registry.py":
            out = json.dumps({})            # no pipeline binding -> stage-map skipped
        elif script == "caf_delivery.py":
            captured["caf_argv"] = list(argv)
            out = json.dumps({"ok": True, "report": "state/reports/r.json",
                              "certificate": None})
        elif script in ("nudge_send.py", "mc_board.py"):
            out = json.dumps({"ok": True})
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
    return fake_run


def _argv_value(argv, flag):
    """Return the token immediately following `flag` in an argv list, else None."""
    for i, tok in enumerate(argv):
        if tok == flag and i + 1 < len(argv):
            return argv[i + 1]
    return None


def test_delivered_doc_url_is_the_real_google_doc_link(tmp_path, monkeypatch):
    """End-to-end: with drive_adapter mocked at its TRUE return shape, the
    dispatcher ships the real Doc link to caf_delivery and the ledger, and returns
    it in its own result -- proving the doc_url key defect is fixed."""
    # a real working file so the create-doc branch (folder_id + content) is taken
    working = tmp_path / "working"
    working.mkdir(parents=True)
    (working / "avatar.md").write_text("avatar body text\n", encoding="utf-8")

    captured = {}
    monkeypatch.setattr(s8.subprocess, "run", _make_fake_run(captured))

    rc, result = s8._invoke_wiring(
        "CONTACT1::ANTH1", run_dir=str(tmp_path), deliverable="avatar")

    assert rc == s8.EX_OK, "dispatcher should complete; got rc=%s" % rc
    # 1. the dispatcher's own result carries the REAL link, not None
    assert result is not None and result["doc_url"] == REAL_DOC_LINK
    # 2. caf_delivery was handed the REAL link via --doc-url (what ships to email/SMS)
    assert _argv_value(captured["caf_argv"], "--doc-url") == REAL_DOC_LINK
    # 3. the ledger artifact row records the same REAL link
    assert _argv_value(captured["record_artifact_argv"], "--doc-url") == REAL_DOC_LINK


def test_old_key_guesses_would_have_dropped_the_link():
    """Regression witness: the pre-fix guesses (webViewLink/link/id) do NOT exist
    on deliver_doc()'s dict, so the old expression resolved to None."""
    created = _deliver_doc_true_shape()
    old = created.get("webViewLink") or created.get("link") or created.get("id")
    assert old is None
    # the fix reads the real key
    assert s8._doc_url_from_created(created) == REAL_DOC_LINK


def test_doc_url_helper_fallbacks_and_absence():
    """The helper prefers doc_url, honors legacy fallbacks, and is None when absent."""
    assert s8._doc_url_from_created({"doc_url": REAL_DOC_LINK}) == REAL_DOC_LINK
    assert s8._doc_url_from_created({"webViewLink": REAL_DOC_LINK}) == REAL_DOC_LINK
    assert s8._doc_url_from_created({"link": REAL_DOC_LINK}) == REAL_DOC_LINK
    assert s8._doc_url_from_created({}) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
