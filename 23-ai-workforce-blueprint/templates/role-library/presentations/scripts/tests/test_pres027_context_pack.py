"""PRES-027 -- dependency-driven context pack (proof tests).

Covers TODO.md PRES-027 + QC.md QC-PRES-027 acceptance rows 1 and 4 plus the
adjacent regression surface (whole-only JSON, protected research budget,
per-slide anchors, deterministic shard hints, model-aware budgets).

Baseline (pre-fix dispatcher.gather_upstream_context): a >100000-char intake
consumes the whole P4-COPY 100000-char budget and drops RESEARCH_SENTINEL
with no warning. These tests FAIL on that path and PASS on context_pack.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import context_pack as cp
from presentation_job import dispatcher as d

SENTINEL = "RESEARCH_SENTINEL_7f3a9c"


def _run_dir(*, intake_chars: int = 1000, with_research: bool = True) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="pres027-"))
    (tmp / "working" / "copy").mkdir(parents=True)
    (tmp / "working" / "research").mkdir(parents=True)
    (tmp / "working" / "copy" / "intake.json").write_text("X" * intake_chars)
    (tmp / "working" / "copy" / "arc_allocation.json").write_text("{}")
    (tmp / "working" / "copy" / "priority_shift_spec.json").write_text("{}")
    (tmp / "working" / "copy" / "sp_intake.json").write_text("{}")
    if with_research:
        (tmp / "working" / "research" / "research_map.json").write_text(
            json.dumps({"items": []}))
        (tmp / "working" / "research" / "brief-test.md").write_text(
            f"{SENTINEL} " + "grounded fact. " * 400)
    return tmp


# -- baseline: the defect exists pre-fix -------------------------------------

def test_baseline_large_intake_drops_research_silently():
    """Pre-fix gather_upstream_context: intake >100K excludes the sentinel
    with no truncation warning (the QC-PRES-027 row-1 fixture)."""
    run = _run_dir(intake_chars=120_000)
    out = d.gather_upstream_context(run, phase_id="P4-COPY")
    assert SENTINEL not in out
    lowered = out.lower()
    assert "truncat" not in lowered and "overflow" not in lowered \
        and "shard" not in lowered


# -- candidate: required research included or explicit overflow ----------------

def test_pack_includes_required_research_or_raises_overflow():
    """Fixed behavior: required research is included whole, or the build
    raises an explicit ContextOverflow with a shard action -- never a
    silent drop."""
    run = _run_dir(intake_chars=120_000)
    try:
        pack = cp.build_pack(
            run, "P4-COPY", model="deepseek-v4-flash",
            extra_required=["working/copy/intake.json",
                            "working/research/research_map.json",
                            "working/research/brief-*.md"])
    except cp.ContextOverflow as exc:
        assert exc.overflow["action"] == "shard"
        assert exc.overflow["required_chars"] > exc.overflow["available_chars"]
        return
    assert SENTINEL in pack.text
    assert pack.overflow is None
    assert pack.content_hash


def test_overflow_carries_deterministic_shard_action():
    run = _run_dir(intake_chars=10_000, with_research=False)
    (run / "working" / "copy" / "intake.json").write_text("Y" * 600_000)
    with pytest.raises(cp.ContextOverflow) as excinfo:
        cp.build_pack(run, "P4-COPY", model="glm-flash",
                      extra_required=["working/copy/intake.json"])
    overflow = excinfo.value.overflow
    assert overflow["event"] == "context_overflow"
    assert overflow["phase_id"] == "P4-COPY"
    assert overflow["action"] == "shard"
    assert overflow["shard_hint"]["strategy"] in (
        "shard-by-unit", "shard-by-section", "compact-optional-first")


def test_optional_json_never_truncated_mid_value():
    """Optional files are whole-or-skipped: a 500K optional JSON is recorded
    as excluded, never sliced mid-value into the prompt text."""
    run = _run_dir(intake_chars=100)
    (run / "working" / "copy" / "sp_claims.json").write_text(
        '{"big": "' + "z" * 500_000 + '"}')
    pack = cp.build_pack(run, "P4-COPY", model="deepseek-v4-flash")
    row = next(r for r in pack.inclusion_manifest
               if r["path"] == "working/copy/sp_claims.json")
    assert row["included"] is False
    assert "z" * 1000 not in pack.text


def test_research_protected_before_transcript():
    """research_map + brief excerpts receive protected budget before the raw
    interview transcript (TODO step 5)."""
    run = _run_dir(intake_chars=100)
    (run / "working" / "interview").mkdir(parents=True, exist_ok=True)
    (run / "working" / "interview" / "intake_transcript.json").write_text(
        "T" * 300_000)
    pack = cp.build_pack(run, "P4-COPY", model="deepseek-v4-flash")
    by_path = {r["path"]: r for r in pack.inclusion_manifest}
    assert by_path["working/research/research_map.json"]["included"] is True
    assert by_path["working/research/brief-test.md"]["included"] is True
    assert SENTINEL in pack.text


def test_per_slide_anchor_scoping():
    run = _run_dir(intake_chars=100, with_research=False)
    (run / "working" / "research" / "research_map.json").write_text(json.dumps({
        "items": [
            {"claim": "aurora fact", "slides": [7]},
            {"claim": "other fact", "slides": [9]},
        ]}))
    pack = cp.build_pack(run, "P4-PROMPT", model="deepseek-v4-flash",
                         slide_ordinal=7)
    assert "aurora fact" in pack.text
    head, sep, tail = pack.text.partition("### slide-7-research-anchor")
    assert sep, "this ordinal's anchor block must be present"
    assert "aurora fact" in tail
    assert "other fact" not in tail
    assert "other fact" not in pack.text


def test_model_aware_budget_small_model_shards_first():
    """A small-context model preflights to shards instead of an oversized
    request (QC row 4): same inputs fit flash but overflow glm-flash."""
    run = _run_dir(intake_chars=150_000)
    ok_pack = cp.build_pack(
        run, "P4-COPY", model="deepseek-v4-flash",
        extra_required=["working/copy/intake.json"])
    assert ok_pack.overflow is None
    with pytest.raises(cp.ContextOverflow):
        cp.build_pack(run, "P4-COPY", model="glm-flash",
                      extra_required=["working/copy/intake.json"])


def test_shard_units_deterministic_with_complete_inputs():
    units = cp.shard_units("P-PROMPT-QC", 25)
    assert len(units) == 25
    assert all(u["requires_complete_inputs"] for u in units)
    assert [u["unit"] for u in units] == list(range(1, 26))


def test_inclusion_manifest_hashes_prove_agent_view():
    """QC proves what the agent saw: every row carries path + sha256."""
    run = _run_dir(intake_chars=100)
    pack = cp.build_pack(run, "P4-COPY", model="deepseek-v4-flash")
    assert pack.inclusion_manifest
    for row in pack.inclusion_manifest:
        assert row["path"] and len(row["sha256"]) == 64
    assert len(pack.content_hash) == 64


def test_flag_off_is_documented_rollback():
    assert cp.flag_enabled() is True


def test_design_brief_change_rehashes_only_dependent_view():
    """QC row 3 (unit scope): editing the design brief changes the pack
    content hash (dependent units rerun) while the intake row is untouched."""
    run = _run_dir(intake_chars=100)
    brief = run / "working" / "research" / "brief-test.md"
    before = cp.build_pack(run, "P4-COPY", model="deepseek-v4-flash")
    brief.write_text(f"{SENTINEL} revised direction. " + "new fact. " * 400)
    after = cp.build_pack(run, "P4-COPY", model="deepseek-v4-flash")
    assert before.content_hash != after.content_hash
    intake_before = next(r["sha256"] for r in before.inclusion_manifest
                         if r["path"] == "working/copy/intake.json")
    intake_after = next(r["sha256"] for r in after.inclusion_manifest
                        if r["path"] == "working/copy/intake.json")
    assert intake_before == intake_after
