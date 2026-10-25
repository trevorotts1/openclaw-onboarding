"""Negative/positive tests for the §2 SEO/media pre-gate in qc-built-funnel.sh.

Finding 33 (oct-25-fixes): the pre-gate failed OPEN — a Python import error exited
zero, the shell ignored the Python status and scanned for a literal FAIL, and a
MISSING seoMeta only warned, so required search metadata could go unproved while
the build passed.

These tests run the real wrapper against a synthetic evidence root with the shared
FAB scorer stubbed to PASS, so the wrapper's exit code is decided ONLY by the
pre-gate under test. Each case is discriminating on exit code, not just text.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "qc-built-funnel.sh"

VALID_SEO = {
    "title": "Book Your Strategy Call Today",
    "description": "Book a strategy call with our founder to map your next step.",
    "keywords": ["strategy call", "business coaching", "growth plan"],
    "author": "Jane Q Founder",
    "canonicalUrl": "https://example.com/book",
    "ogImage": "https://images.example-cdn.com/og.jpg",
    "language": "en",
    "links": [],
    "tags": [],
}


def _layout(tmp_path, with_tools=True):
    """Copy the wrapper into a throwaway skill dir whose FAB scorer always PASSES."""
    layout = tmp_path / "layout"
    skill = layout / "skill"
    skill.mkdir(parents=True)
    script = skill / "qc-built-funnel.sh"
    shutil.copy2(SCRIPT, script)
    if with_tools:
        (skill / "tools").symlink_to(SKILL_DIR / "tools", target_is_directory=True)
    scorer_dir = layout / "shared-utils"
    scorer_dir.mkdir()
    (scorer_dir / "fab_qc.py").write_text(
        "print('FAB-QC stub: PASS')\nraise SystemExit(0)\n", encoding="utf-8")
    evidence = layout / "evidence"
    evidence.mkdir()
    return script, evidence


def _run(script, evidence, tmp_path, extra_env=None):
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key in ("CC_TASK_ID", "PAGE_QC_ENABLED", "QC_FUNNEL_LEGACY_EVIDENCE"):
        env.pop(key, None)
    env["TMPDIR"] = str(tmpdir)
    env.update(extra_env or {})
    proc = subprocess.run(["bash", str(script), str(evidence)],
                          capture_output=True, text=True, env=env,
                          cwd=str(tmp_path))
    return proc.returncode, proc.stdout + proc.stderr


def test_missing_seo_meta_fails_current_build(tmp_path):
    """No seoMeta in evidence → hard miss (rc 1), never a WARN-only pass."""
    script, evidence = _layout(tmp_path)
    (evidence / "page.json").write_text(
        json.dumps({"pageData": {"elements": []}}), encoding="utf-8")

    rc, out = _run(script, evidence, tmp_path)

    assert "FAIL no seoMeta found in evidence" in out, out
    assert "WARN no seoMeta" not in out, out
    assert rc == 1, (rc, out)


def test_valid_seo_meta_passes_control(tmp_path):
    """Control: a populated seoMeta still passes, so the gate discriminates."""
    script, evidence = _layout(tmp_path)
    (evidence / "page.json").write_text(
        json.dumps({"pageData": {"seoMeta": VALID_SEO}}), encoding="utf-8")

    rc, out = _run(script, evidence, tmp_path)

    assert "PASS 1 seoMeta object(s) populated" in out, out
    assert rc == 0, (rc, out)


def test_legacy_opt_out_keeps_old_evidence_at_warn(tmp_path):
    """QC_FUNNEL_LEGACY_EVIDENCE=1 is the only way back to WARN for pre-SEO evidence."""
    script, evidence = _layout(tmp_path)
    (evidence / "page.json").write_text(
        json.dumps({"pageData": {"elements": []}}), encoding="utf-8")

    rc, out = _run(script, evidence, tmp_path,
                   {"QC_FUNNEL_LEGACY_EVIDENCE": "1"})

    assert "WARN no seoMeta" in out, out
    assert rc == 0, (rc, out)


def test_unreadable_evidence_fails(tmp_path):
    """Unparsable evidence JSON → hard miss (unreadable is not 'absent, keep going')."""
    script, evidence = _layout(tmp_path)
    (evidence / "page.json").write_text('{"pageData": {', encoding="utf-8")
    (evidence / "good.json").write_text(
        json.dumps({"pageData": {"seoMeta": VALID_SEO}}), encoding="utf-8")

    rc, out = _run(script, evidence, tmp_path)

    assert "FAIL unreadable evidence page.json" in out, out
    assert rc == 1, (rc, out)


def test_import_failure_fails(tmp_path):
    """ghl_builder import failure → hard miss; the pre-gate cannot prove the panel."""
    script, evidence = _layout(tmp_path, with_tools=False)
    (evidence / "page.json").write_text(
        json.dumps({"pageData": {"seoMeta": VALID_SEO}}), encoding="utf-8")

    rc, out = _run(script, evidence, tmp_path)

    assert "FAIL ghl_builder import failed" in out, out
    assert rc == 1, (rc, out)
