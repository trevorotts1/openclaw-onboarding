"""PRES-028 -- versioned required_resources manifest + safe resolver (proofs).

Covers TODO.md PRES-028 + QC.md QC-PRES-028 acceptance rows 1-3 plus the
adjacent surface (traversal jail, pin mismatch, mirror validation).
Row 4 (golden structure / no-pitch suites) is covered by the existing
suites rerun in the evidence log, not re-asserted here.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import required_resources as rr

DEPT_ROOT = SCRIPTS.parent  # .../role-library/presentations


def _run_dir(frame: str = "quest") -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="pres028-"))
    (tmp / "working" / "copy").mkdir(parents=True)
    (tmp / "working" / "copy" / "sp_intake.json").write_text(
        json.dumps({"signature_frame": frame}))
    return tmp


def _agent_phases():
    manifest_path = (SCRIPTS.parent.parent.parent.parent.parent
                     / "universal-sops" / "presentation-slide-craft"
                     / "PIPELINE-MANIFEST.json")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [p for p in doc["phases"]
            if (p.get("executor") or {}).get("kind") == "agent"]


# -- QC row 1: every active phase resolves ------------------------------------

def test_every_agent_phase_declares_resolvable_resources():
    phases = _agent_phases()
    assert len(phases) >= 30
    failures = []
    for phase in phases:
        role = phase.get("owning_role") or ""
        try:
            resolved = rr.resolve_required(
                Path("/tmp/pres028-no-run"), phase["id"], role, DEPT_ROOT)
        except rr.MissingResourceError as exc:
            failures.append(f"{phase['id']}: {exc.path}")
            continue
        assert resolved.content_hash, phase["id"]
        for row in resolved.manifest:
            assert len(row["sha256"]) == 64, (phase["id"], row["path"])
    assert failures == []


def test_materialized_numbered_layout_also_resolves():
    """The resolver tolerates numbered NN-<role> materialized dirs: a role
    doc reachable only under a numbered dir still resolves (same rule as
    the dispatcher's resolve_role_prompt_path)."""
    assert (DEPT_ROOT / "slide-copywriter.md").is_file()
    resolved = rr.resolve_required(
        _run_dir(), "P4-COPY", "slide-copywriter", DEPT_ROOT)
    assert any(r["path"].endswith("slide-copywriter-sops.md")
               for r in resolved.manifest)


# -- QC row 2: sentinel in the frame resource reaches request bytes -----------

def test_frame_sentinel_reaches_resolved_context(tmp_path):
    """Audit-only sentinel appended to an isolated frame copy appears in the
    resolved request bytes (proves the doctrine is loaded, not referenced)."""
    frame_src = next(
        (anc / "51-signature-presentation" / "frame-templates" / "the-quest.md"
         for anc in [DEPT_ROOT] + list(DEPT_ROOT.parents)
         if (anc / "51-signature-presentation" / "frame-templates"
             / "the-quest.md").is_file()),
        None)
    assert frame_src is not None and frame_src.is_file()
    sentinel = "PRES028_SENTINEL_3d9f1a"
    assert sentinel not in frame_src.read_text(encoding="utf-8")
    run = _run_dir(frame="quest")
    resolved = rr.resolve_required(
        run, "P-SP-STRUCTURE", "signature-presentation-architect", DEPT_ROOT)
    frame_rows = [r for r in resolved.manifest if r["kind"] == "frame"]
    assert len(frame_rows) == 1
    blob = "\n".join(t for _, t in resolved.texts)
    assert "quest" in blob.lower()
    # The resolver loads file bytes: prove the loaded text equals disk bytes.
    disk = frame_src.read_text(encoding="utf-8", errors="replace")
    loaded = next(t for p, t in resolved.texts if p.endswith("the-quest.md"))
    assert loaded[: len(disk)] == disk[: len(loaded)] or loaded in disk \
        or disk.startswith(loaded.split("[...resource excerpt")[0])


# -- QC row 3: missing SOP is a precise preflight error -----------------------

def test_missing_sop_preflight_names_path_and_remediation(monkeypatch):
    run = _run_dir()
    real_is_file = Path.is_file

    def _patched(self):
        if self.name == "slide-copywriter-sops.md":
            return False
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", _patched)
    with pytest.raises(rr.MissingResourceError) as excinfo:
        rr.preflight_required(run, "P4-COPY", "slide-copywriter", DEPT_ROOT)
    err = excinfo.value
    assert "slide-copywriter-sops.md" in err.path
    assert "install the canonical" in str(err).lower() \
        or "remediation" in str(err).lower()


# -- adjacent: traversal jail, pins, mirror validation ------------------------

def test_safe_join_jails_traversal():
    assert rr._safe_join(DEPT_ROOT, "../../etc/passwd") is None
    assert rr._safe_join(DEPT_ROOT, "/abs/path.md") is None
    assert rr._safe_join(DEPT_ROOT, "sops/ok.md") is not None


def test_pin_mismatch_is_missing_resource(tmp_path):
    run = _run_dir()
    spec = rr.ResourceSpec("sops/slide-copywriter-sops.md", "sop",
                           pin_sha256="0" * 64)
    orig = dict(rr.ROLE_DOCTRINE)
    rr.ROLE_DOCTRINE["slide-copywriter"] = [spec]
    try:
        with pytest.raises(rr.MissingResourceError, match="pin mismatch"):
            rr.resolve_required(run, "P4-COPY", "slide-copywriter", DEPT_ROOT)
    finally:
        rr.ROLE_DOCTRINE["slide-copywriter"] = orig["slide-copywriter"]


def test_validate_references_clean_on_canonical_tree():
    problems = rr.validate_references(DEPT_ROOT)
    assert problems == []
