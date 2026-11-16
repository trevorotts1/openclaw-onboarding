"""PD-066 (A1) — a renderer waiver needs a verified owner message.

Rows, verbatim from 01-BUILD-SPEC.md (PD-066):
  record without an id -> rejected with a reason naming the missing id;
  record with an id the oracle refuses -> rejected;
  record with a verified id -> granted;
  every case still prints the banner and writes the ledger row.

The oracle is presentation_job.approvals (the cc_board owner-message resolver),
stubbed per case so no network is touched.
"""

import contextlib
import io
import json
import pathlib
import sys

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS_DIR.parent
for _p in (str(SCRIPTS),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_deck as bd  # noqa: E402
import presentation_job.approvals as approvals  # noqa: E402

GATE = "AF-OCR-READBACK"
LEDGER_KEY = "owner_skip_events"


def _record(**over):
    rec = {
        "owner_approved": True,
        "af_code": GATE,
        "approved_by": "Trevor (operator)",
        "reason": "stylised numerals cannot be OCR-read; owner accepted the render",
        "timestamp": "2026-11-13T15:35:00Z",
    }
    rec.update(over)
    return rec


def _run_dir(tmp_path, record):
    pm = tmp_path / "working" / "checkpoints" / "process_manifest.json"
    pm.parent.mkdir(parents=True, exist_ok=True)
    pm.write_text(json.dumps({"owner_skip_approval": record}), encoding="utf-8")
    return tmp_path


def _consume(run_dir):
    """Ask the gate for its waiver; return (granted, stderr, ledger rows)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        granted = bd._owner_skip_approved(run_dir, GATE)
    ledger = json.loads(
        (run_dir / "working" / "checkpoints" / "process_manifest.json")
        .read_text(encoding="utf-8"))[LEDGER_KEY]
    return granted, err.getvalue(), ledger


def _oracle(monkeypatch, ids):
    monkeypatch.setattr(approvals, "_cc_board_oracle",
                        lambda run_dir=None: (frozenset(ids) if ids is not None else None))


def test_record_without_id_is_rejected_naming_the_missing_id(tmp_path, monkeypatch):
    _oracle(monkeypatch, {"owner-msg-1"})
    rd = _run_dir(tmp_path, _record())
    granted, err, ledger = _consume(rd)
    assert granted is None
    assert "owner_msg_id" in err, err
    assert "OWNER-SKIP-REJECTED" in err
    assert "owner_msg_id" in ledger[-1]["rejected_because"]
    assert ledger[-1]["outcome"] == "rejected"


def test_record_the_oracle_refuses_is_rejected(tmp_path, monkeypatch):
    _oracle(monkeypatch, {"a-real-owner-id"})
    rd = _run_dir(tmp_path, _record(owner_msg_id="forged-id"))
    granted, err, ledger = _consume(rd)
    assert granted is None
    assert "OWNER-SKIP-REJECTED" in err
    assert "does not resolve" in ledger[-1]["rejected_because"]
    assert ledger[-1]["outcome"] == "rejected"


def test_record_with_verified_id_is_granted(tmp_path, monkeypatch):
    _oracle(monkeypatch, {"owner-msg-42"})
    rd = _run_dir(tmp_path, _record(owner_msg_id="owner-msg-42"))
    granted, err, ledger = _consume(rd)
    assert granted is not None and granted["owner_msg_id"] == "owner-msg-42"
    assert "OWNER-SKIP-CONSUMED" in err and "WAIVED" in err
    assert ledger[-1]["outcome"] == "granted"


def test_unreachable_oracle_grants_nothing_and_says_so(tmp_path, monkeypatch):
    _oracle(monkeypatch, None)  # UNDETERMINED
    rd = _run_dir(tmp_path, _record(owner_msg_id="owner-msg-42"))
    granted, err, ledger = _consume(rd)
    assert granted is None
    assert "cannot be checked on this machine" in ledger[-1]["rejected_because"]
    assert ledger[-1]["outcome"] == "rejected"
    assert "OWNER-SKIP-REJECTED" in err
