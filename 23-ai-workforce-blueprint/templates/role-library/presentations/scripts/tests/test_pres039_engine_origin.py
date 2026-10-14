#!/usr/bin/env python3
"""test_pres039_engine_origin.py -- PRES-039: engine provenance + preflight.

WHAT THIS PROVES
----------------
The canonical engine (this tree, the authoritative ONB distributable) now
carries the engine_origin provenance preflight the CC vendored copy had
(FIX-PLAN Item 7, design Step 1 upstreaming). Ported from the CC copy's
tests/unit/pres039-engine-origin.test.sh assertions T1/T2/T4, plus the
canonical T5 recording path (cmd_new / cmd_status / describe_park) driven
against this checkout's REAL PIPELINE-MANIFEST.json:

  T1  engine_origin() reports the canonical identity: distributor ONB,
      copy role canonical-source-authoritative, contract v1, cutover
      PRES/PRES-049, dedup PRES-039, a 64-hex digest, and a package file
      count that matches the package dir's actual *.py + *.json census.
  T2  The digest is deterministic (two computations on the untouched tree
      agree) and a ONE-BYTE modification to a package file in a copied
      tree changes that tree's digest.
  T3  A stale duplicate on sys.path (subset copy, one file touched) makes
      preflight() refuse with exit 3 / AF-ENGINE-STALE-DUPLICATE.
  T4  An identical-byte mirror on sys.path is recorded, not fatal:
      preflight() returns 0 and notes the mirror.
  T5  The live contract holds on this tree (_check_contract -> no
      problems); a tampered copy whose launcher.py reads
      "DISPATCH_NOTIFY_REFUSED = -70" is flagged naming
      DISPATCH_NOTIFY_REFUSED (the line-anchor regex rejects -70), and a
      tampered "DISPATCH_ENGINE_REFUSED = -120" is flagged likewise
      (canonical numbering: -8 is DISPATCH_OCR_REFUSED in this tree, so
      the PRES-039 engine sentinel is -12; see launcher.py).
  T6  cmd_new records engine_origin into state.json, cmd_status and
      diagnose.describe_park print it, and a state without it reports
      origin NOT RECORDED (the pre-PRES-039 shape).
  T7  The launcher path invokes the preflight: dispatch() with a stale
      duplicate on sys.path returns DISPATCH_ENGINE_REFUSED (-12) before
      any other gate runs, and prints the origin line.

No network, no provider call, no spend. Fixtures are copies of this
checkout's own package files, never hand-written stand-ins for them.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

PACKAGE = SCRIPTS / "presentation_job"


def _eo():
    from presentation_job import engine_origin
    return engine_origin


def _canonical_manifest() -> Path:
    """Same resolution order as tests/test_f02_auto_repin.py's own copy."""
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
    raise AssertionError("canonical PIPELINE-MANIFEST.json not found")


def _copy_top_level(dst_pkg: Path) -> Path:
    """Copy the package's top-level *.py + *.json (the digest census) into
    dst_pkg (a directory named presentation_job)."""
    dst_pkg.mkdir(parents=True)
    for p in sorted(PACKAGE.iterdir()):
        if p.is_file() and p.suffix in (".py", ".json"):
            shutil.copy2(p, dst_pkg / p.name)
    return dst_pkg


# ---------------------------------------------------------------------------
# T1 -- origin identity (CC pres039 T1, canonical values)
# ---------------------------------------------------------------------------
def test_t1_origin_identity():
    eo = _eo()
    origin = eo.engine_origin()
    assert origin["distributor"] == "ONB"
    assert origin["copy_role"] == "canonical-source-authoritative"
    assert origin["contract_version"] == 1
    assert origin["cutover_owner"] == "PRES"
    assert origin["cutover_task"] == "PRES-049"
    assert origin["dedup_task"] == "PRES-039"
    assert len(origin["package_digest"]) == 64
    census = sum(1 for p in PACKAGE.iterdir()
                 if p.is_file() and p.suffix in (".py", ".json"))
    assert origin["package_files"] == census
    assert origin["package_files"] >= 70
    line = eo.format_origin_line(origin)
    assert line.startswith("engine origin: distributor=ONB ")
    assert "role=canonical-source-authoritative" in line


# ---------------------------------------------------------------------------
# T2 -- digest determinism + one-byte modification detection
# ---------------------------------------------------------------------------
def test_t2_digest_deterministic_and_detects_one_byte(tmp_path):
    eo = _eo()
    d1 = eo.package_digest()
    d2 = eo.package_digest()
    assert d1["digest"] == d2["digest"]
    assert d1["files"] == d2["files"]

    mirror = _copy_top_level(tmp_path / "presentation_job")
    assert eo.package_digest(mirror)["digest"] == d1["digest"]

    victim = mirror / "state.py"
    with victim.open("ab") as fh:
        fh.write(b" ")
    changed = eo.package_digest(mirror)
    assert changed["digest"] != d1["digest"]
    # The untouched tree's digest is unaffected by the copy's modification.
    assert eo.package_digest()["digest"] == d1["digest"]


# ---------------------------------------------------------------------------
# T3 -- stale duplicate refuses (CC pres039 T2)
# ---------------------------------------------------------------------------
def test_t3_stale_duplicate_refused(tmp_path, monkeypatch):
    eo = _eo()
    stale = tmp_path / "stale" / "presentation_job"
    stale.mkdir(parents=True)
    for name in ("__init__.py", "engine_origin.py", "state.py",
                 "board.py", "launcher.py"):
        shutil.copy2(PACKAGE / name, stale / name)
    with (stale / "state.py").open("a", encoding="utf-8") as fh:
        fh.write("\n# stale copy: one byte of drift is enough\n")
    monkeypatch.setattr(sys, "path", sys.path + [str(tmp_path / "stale")])
    code, report = eo.preflight()
    assert code == 3
    assert report["ok"] is False
    assert report["autofail"] == "AF-ENGINE-STALE-DUPLICATE"


# ---------------------------------------------------------------------------
# T4 -- identical-byte mirror recorded, not fatal (CC pres039 T3)
# ---------------------------------------------------------------------------
def test_t4_identical_mirror_tolerated(tmp_path, monkeypatch):
    eo = _eo()
    _copy_top_level(tmp_path / "mirror" / "presentation_job")
    monkeypatch.setattr(sys, "path", sys.path + [str(tmp_path / "mirror")])
    code, report = eo.preflight()
    assert code == 0
    assert report["ok"] is True
    assert any("identical-byte mirror" in n for n in report.get("notes", []))


# ---------------------------------------------------------------------------
# T5 -- contract holds live; tampered copies flagged (CC pres039 T4/T4b)
# ---------------------------------------------------------------------------
def test_t5_contract_holds_and_tamper_detected(tmp_path):
    eo = _eo()
    ok, problems = eo._check_contract()
    assert ok is True
    assert problems == []

    code, report = eo.preflight()
    assert code == 0
    assert report["contract_problems"] == []

    drift = tmp_path / "drift" / "presentation_job"
    drift.mkdir(parents=True)
    for name in ("__init__.py", "engine_origin.py", "state.py",
                 "board.py", "launcher.py"):
        shutil.copy2(PACKAGE / name, drift / name)
    launcher_copy = drift / "launcher.py"
    src = launcher_copy.read_text(encoding="utf-8")
    assert "DISPATCH_NOTIFY_REFUSED = -7" in src
    launcher_copy.write_text(
        src.replace("DISPATCH_NOTIFY_REFUSED = -7",
                    "DISPATCH_NOTIFY_REFUSED = -70"), encoding="utf-8")
    ok2, problems2 = eo._check_contract(drift)
    assert ok2 is False
    assert any("DISPATCH_NOTIFY_REFUSED" in p for p in problems2)

    src2 = launcher_copy.read_text(encoding="utf-8")
    assert "DISPATCH_ENGINE_REFUSED = -12" in src2
    launcher_copy.write_text(
        src2.replace("DISPATCH_ENGINE_REFUSED = -12",
                     "DISPATCH_ENGINE_REFUSED = -120"), encoding="utf-8")
    ok3, problems3 = eo._check_contract(drift)
    assert ok3 is False
    assert any("DISPATCH_ENGINE_REFUSED" in p for p in problems3)


# ---------------------------------------------------------------------------
# T6 -- cmd_new records origin; status + diagnose print it (CC pres039 T5)
# ---------------------------------------------------------------------------
def test_t6_cmd_new_records_origin(tmp_path, capsys):
    eo = _eo()
    from presentation_job import __main__ as pj_main
    from presentation_job import diagnose

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    intake = {
        "presentation_type": "from_scratch",
        "requester": {"chat_id": "pres039-test"},
    }
    intake_path = tmp_path / "intake.json"
    intake_path.write_text(json.dumps(intake), encoding="utf-8")

    args = SimpleNamespace(run_dir=run_dir, intake=intake_path,
                           manifest=str(_canonical_manifest()))
    rc = pj_main.cmd_new(args, SCRIPTS)
    assert rc == 0
    out = capsys.readouterr().out
    assert "engine origin: distributor=ONB" in out

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    recorded = state.get("engine_origin") or {}
    assert recorded.get("distributor") == "ONB"
    assert recorded.get("copy_role") == "canonical-source-authoritative"
    assert recorded.get("package_digest") == eo.package_digest()["digest"]

    rc = pj_main.cmd_status(SimpleNamespace(run_dir=run_dir, json=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "engine   : distributor=ONB" in out

    lines = diagnose.describe_park(state, run_dir)
    assert any(ln.startswith("engine   : distributor=ONB") for ln in lines)

    legacy = dict(state)
    legacy.pop("engine_origin", None)
    legacy_lines = diagnose.describe_park(legacy, run_dir)
    assert legacy_lines[0] == "engine   : origin NOT RECORDED (pre-PRES-039 run)"


# ---------------------------------------------------------------------------
# T7 -- the launcher path invokes the preflight
# ---------------------------------------------------------------------------
def test_t7_launcher_dispatch_invokes_preflight(tmp_path, monkeypatch, capsys):
    eo = _eo()
    from presentation_job import launcher

    assert launcher.DISPATCH_ENGINE_REFUSED == -12
    assert launcher.EXIT_ENGINE_REFUSED == 13

    stale = tmp_path / "stale" / "presentation_job"
    stale.mkdir(parents=True)
    for name in ("__init__.py", "engine_origin.py", "state.py",
                 "board.py", "launcher.py"):
        shutil.copy2(PACKAGE / name, stale / name)
    with (stale / "state.py").open("a", encoding="utf-8") as fh:
        fh.write("\n# stale copy\n")
    monkeypatch.setattr(sys, "path", sys.path + [str(tmp_path / "stale")])

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rc = launcher.dispatch(str(run_dir))
    assert rc == launcher.DISPATCH_ENGINE_REFUSED
    captured = capsys.readouterr()
    assert "engine origin: distributor=ONB" in captured.out
    assert "AF-ENGINE-STALE-DUPLICATE" in captured.err
