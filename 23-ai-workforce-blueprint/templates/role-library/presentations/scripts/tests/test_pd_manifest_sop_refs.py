"""PD-047 -- the eleven sales-package phases must name the procedure that governs them.

The manifest is the pipeline's single source of truth (SOP-SLIDE-06), and until
this unit eleven of its phases carried no `sop_refs` at all: the five sales /
checkout copy-brief-QC phases, the three VSL phases, and the three GHL install
phases. An agent dispatched into any of them had nothing to read. The procedures
existed on disk the whole time -- they were simply never wired.

This file checks the two things the acceptance row asks for, plus the mapping
itself so a wrong-but-existing file cannot pass:

  1. NO phase has an empty `sop_refs` (allow-list: none).
  2. Every named file exists in the department `sops/` dir or the slide-craft
     folder (the two places a procedure may live).
  3. The eleven phases this unit wired name the procedure that actually
     describes them (SALES-CHECKOUT-BUILDER / VSL-BUILDER / GHL-EXTERNAL-
     INSTALLER), and P9.6-WEBINAR-VIDEO also names WEBINAR-BUILDER-SOP.md
     (finding PD-102: the Media Librarian file it named had no webinar
     procedure).

CONTROL: set PD_MANIFEST_PATH to another manifest's path to run every check
against that file instead. `PD_MANIFEST_PATH=<the pre-PD-047 manifest>
python3 -m pytest test_pd_manifest_sop_refs.py` FAILS on check 1 (eleven empty
lists) -- that is what makes the pass on the edited manifest mean something.

Manifest location is resolved the way the deployed tree carries it FIRST
(scripts/../sops/PIPELINE-MANIFEST.json) then by walking up to a repo checkout,
mirroring manifest_source.resolve_manifest's installed-then-cluster tiering. If
neither resolves this file FAILS rather than skipping -- a skipped manifest test
is a green suite that proved nothing (tests/test_client_package.py's rule).

Standard library plus pytest. No network, no model, no paid call.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
PRESENTATIONS = SCRIPTS.parent                      # .../presentations

MANIFEST_REL = pathlib.Path("universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json")
SLIDE_CRAFT_REL = pathlib.Path("universal-sops/presentation-slide-craft")
DEPT_SOPS_REL = pathlib.Path("23-ai-workforce-blueprint/templates/role-library/presentations/sops")

# The three procedures this unit read in full, and the phases each one governs.
SALES = "SALES-CHECKOUT-BUILDER-SOP.md"
VSL = "VSL-BUILDER-SOP.md"
GHL = "GHL-EXTERNAL-INSTALLER-SOP.md"
EXPECTED_REFS = {
    "P-U-SALES-COPY": [SALES],
    "P-U-CHECKOUT-COPY": [SALES],
    "P-U-BRIEF-SALES": [SALES],
    "P-U-QC": [SALES, VSL],
    "P-U-COLLATERAL": [SALES, VSL],
    "P-U-VSL-RESEARCH": [VSL],
    "P-U-VSL-COPY": [VSL],
    "P-U-BRIEF-VSL": [VSL],
    "P-U-FORM-GATE": [GHL],
    "P-U-GHL-SALES": [GHL],
    "P-U-GHL-VSL": [GHL],
}


def _find_root(start: pathlib.Path) -> pathlib.Path | None:
    """Directory holding the manifest: deployed sops/ beside the scripts dir,
    else the first ancestor that carries the repo layout."""
    if (PRESENTATIONS / "sops" / "PIPELINE-MANIFEST.json").is_file():
        return PRESENTATIONS
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


def _manifest_path() -> pathlib.Path:
    override = os.environ.get("PD_MANIFEST_PATH")
    if override:
        p = pathlib.Path(override)
        if not p.is_file():
            pytest.fail(f"PD_MANIFEST_PATH is set but {p} is not a file")
        return p
    root = _find_root(pathlib.Path(__file__).parent)
    if root is None:
        pytest.fail(
            "manifest could not be resolved: looked for "
            f"{PRESENTATIONS / 'sops' / 'PIPELINE-MANIFEST.json'} and for an "
            f"ancestor of this test file containing {MANIFEST_REL}. This is a "
            "FAIL, never a skip.")
    if (root / "PIPELINE-MANIFEST.json").is_file():
        return root / "PIPELINE-MANIFEST.json"
    return root / MANIFEST_REL


def _manifest() -> dict:
    return json.loads(_manifest_path().read_text(encoding="utf-8"))


def _sop_dirs() -> list[pathlib.Path]:
    """Every directory a procedure may live in: the department sops/ dir and the
    slide-craft folder. Resolved from the repo root when one is available, else
    from this file's own position (the deployed layouts put the dept sops/ beside
    the scripts)."""
    root = _find_root(pathlib.Path(__file__).parent)
    dirs = [PRESENTATIONS / "sops"]
    if root is not None:
        dirs.append(root / DEPT_SOPS_REL)
        dirs.append(root / SLIDE_CRAFT_REL)
    seen, found = set(), []
    for d in dirs:
        if d.is_dir() and d.resolve() not in seen:
            seen.add(d.resolve())
            found.append(d)
    return found


def test_every_phase_names_at_least_one_procedure():
    """Allow-list: none. A dispatched agent with no procedure has nothing to read."""
    phases = _manifest()["phases"]
    empty = [p["id"] for p in phases if not p.get("sop_refs")]
    assert not empty, (
        f"{len(empty)} phase(s) carry no sop_refs: {empty}. Every phase is "
        "dispatched to a real agent, so every phase must name the procedure that "
        "governs it -- there is no allow-list.")


def test_every_named_procedure_exists():
    """A sop_ref the reader cannot open is worse than none: it looks wired."""
    dirs = _sop_dirs()
    assert dirs, "no procedure directory resolved (dept sops/ and slide-craft both missing)"
    phases = _manifest()["phases"]
    missing = []
    for ph in phases:
        for ref in ph.get("sop_refs") or []:
            name = str(ref).split("#", 1)[0].strip()
            if name and not any((d / name).is_file() for d in dirs):
                missing.append(f"{ph['id']} -> {name}")
    assert not missing, (
        "sop_refs naming a file absent from every procedure directory "
        f"({[str(d) for d in dirs]}): {missing}")


def test_the_sales_package_phases_name_the_procedure_that_governs_them():
    """The mapping itself: each phase points at the procedure that describes it,
    so a wrong-but-existing file cannot pass checks 1 and 2."""
    by_id = {p["id"]: p for p in _manifest()["phases"]}
    wrong = {}
    for pid, expected in EXPECTED_REFS.items():
        assert pid in by_id, f"manifest no longer has phase {pid}"
        got = by_id[pid].get("sop_refs") or []
        if got != expected:
            wrong[pid] = {"expected": expected, "got": got}
    assert not wrong, f"sales-package sop_refs do not match the governing procedure: {wrong}"


def test_the_webinar_video_names_its_webinar_procedure():
    """PD-102: P9.6-WEBINAR-VIDEO named only the Media Librarian role file, which
    carries no webinar procedure. The webinar procedure must be named too."""
    by_id = {p["id"]: p for p in _manifest()["phases"]}
    assert "P9.6-WEBINAR-VIDEO" in by_id, "manifest no longer has P9.6-WEBINAR-VIDEO"
    refs = by_id["P9.6-WEBINAR-VIDEO"].get("sop_refs") or []
    assert "WEBINAR-BUILDER-SOP.md" in refs, (
        f"P9.6-WEBINAR-VIDEO sop_refs = {refs}; the webinar procedure it is "
        "governed by is not named")
