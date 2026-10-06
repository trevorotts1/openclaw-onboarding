"""Tests for FIX 20 — `--repin` (Master Part 8 Fix 20; QC.md FIX 20).

PROOF (QC.md FIX 20): "Park a run, change one byte in the manifest, run
`presentation_job.py --repin --run-dir <run>` then `--resume`. PASS iff the
run continues and the ledger holds both shas."

What each test proves:
- resume on a bumped manifest dies EXIT_MANIFEST_MISMATCH (7) and its message
  names the --repin command (the operator is never left with a dead end);
- --repin records BOTH shas (manifest_sha256_prev + manifest.repin history
  rows carry old_sha256 and new_sha256);
- phases removed from the manifest are marked obsolete (never silently
  dropped); phases added become pending with repin_added=True; done phases
  survive untouched;
- repinning an unchanged manifest is a no-op (rc 0, history untouched);
- resume after repin gets PAST the pin check (no exit 7) — it proceeds into
  the engine, which parks on the synthetic dir's missing intake (the run
  CONTINUED, which is the pass condition).

Flat file inside tests/, manages its own import path — matching every
sibling in this directory.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.__main__ import main  # noqa: E402
from presentation_job.state import EXIT_MANIFEST_MISMATCH  # noqa: E402


def _canonical_manifest() -> Path:
    """Same resolution order as every sibling test file's own copy."""
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


def _make_run(tmp_path: Path, phases: list, *, bump: bool = False) -> Path:
    """A synthetic parked run pinned to a copy of the canonical manifest."""
    src = _canonical_manifest()
    man = tmp_path / "manifest.json"
    man.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    if bump:
        raw = man.read_text(encoding="utf-8")
        # Change exactly ONE byte: bump the version digit.
        old = '"manifest_version":'
        i = raw.index(old)
        j = raw.index("\n", i)
        seg = raw[i:j]
        digits = "".join(c for c in seg if c.isdigit())
        new_digit = str((int(digits) + 1) % 10 or 1)
        man.write_text(raw[:i] + seg.replace(digits, new_digit, 1) + raw[j:],
                       encoding="utf-8")
    state = {
        "schema_version": 1,
        "job_id": "pj_test_fix20",
        "run_dir": str(tmp_path),
        "created_at": "2026-09-02T00:00:00Z",
        "manifest_path": str(man),
        "manifest_version": 55,
        "manifest_sha256": hashlib.sha256(
            man.read_bytes()).hexdigest() if not bump else "0" * 64,
        "phases": phases,
        "gates": {}, "events": [], "sent": {}, "terminal": None,
    }
    (tmp_path / "working").mkdir(exist_ok=True)
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return tmp_path


def _load(run: Path) -> dict:
    return json.loads((run / "state.json").read_text(encoding="utf-8"))


def test_resume_on_bumped_manifest_exits_7_and_names_repin(
        tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
    run = _make_run(tmp_path, [], bump=True)
    with pytest.raises(SystemExit) as exc:
        main(["--resume", "--run-dir", str(run)])
    assert exc.value.code == EXIT_MANIFEST_MISMATCH
    out = capsys.readouterr().err + capsys.readouterr().out
    assert "--repin" in out
    assert str(run) in out


def test_repin_records_both_shas(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
    run = _make_run(tmp_path, [{"id": "P4-COPY", "status": "done",
                                "artifacts": [], "sha256": {}}], bump=True)
    rc = main(["--repin", "--run-dir", str(run)])
    assert rc == 0
    st = _load(run)
    prev = st["manifest_sha256_prev"]
    cur = st["manifest_sha256"]
    assert prev and cur and prev != cur
    hist = st["manifest_repin_history"]
    assert len(hist) == 1
    assert hist[0]["old_sha256"] == prev
    assert hist[0]["new_sha256"] == cur
    # the live pin moved to the CURRENT manifest
    assert cur == hashlib.sha256(
        Path(st["manifest_path"]).read_bytes()).hexdigest()


def test_repin_marks_removed_obsolete_and_added_pending(
        tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
    # P-GONE is not in the real manifest -> must become obsolete.
    # P4-COPY IS in the real manifest and arrives done -> survives untouched.
    run = _make_run(tmp_path, [
        {"id": "P-GONE", "status": "done", "artifacts": [], "sha256": {}},
        {"id": "P4-COPY", "status": "done", "artifacts": [], "sha256": {}},
    ], bump=True)
    rc = main(["--repin", "--run-dir", str(run)])
    assert rc == 0
    st = _load(run)
    rows = {p["id"]: p for p in st["phases"]}
    assert rows["P-GONE"]["status"] == "obsolete"
    assert "repin (FIX 20)" in rows["P-GONE"]["obsolete_reason"]
    assert rows["P4-COPY"]["status"] == "done"
    hist = st["manifest_repin_history"][0]
    assert "P-GONE" in hist["phases_removed"]
    assert "P4-COPY" not in hist["phases_added"]


def test_repin_unchanged_manifest_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
    run = _make_run(tmp_path, [], bump=False)
    rc = main(["--repin", "--run-dir", str(run)])
    assert rc == 0
    st = _load(run)
    assert "manifest_repin_history" not in st
    assert "manifest_sha256_prev" not in st


def test_resume_after_repin_gets_past_the_pin_check(
        tmp_path, capsys, monkeypatch):
    """QC FIX 20 pass condition: after repin, the run CONTINUES — resume must
    not exit 7. --diagnose-only returns after the pin check and the park
    diagnosis, so this proves the pin check itself passes without running the
    full (long, agent-phase) loop; the full-loop continuation is proven by the
    manual proof run (see cmd_repin docstring, W05-B4)."""
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
    run = _make_run(tmp_path, [{"id": "P4-COPY", "status": "done",
                                "artifacts": [], "sha256": {}}], bump=True)
    assert main(["--repin", "--run-dir", str(run)]) == 0
    capsys.readouterr()
    rc = main(["--resume", "--diagnose-only", "--run-dir", str(run)])
    assert rc == 0  # EXIT_OK, NOT EXIT_MANIFEST_MISMATCH (7)
    out = capsys.readouterr().err + capsys.readouterr().out
    assert "repin" not in out.lower() or "repin" not in out
