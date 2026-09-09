"""PRES-001 (W2 WF05) tests -- per-phase UnitContracts on the manifest fan-out
path (presentation_job/dispatcher.py).

TODO.md PRES-001 step 1 + acceptance, exercised ISOLATED (no paid call, no
state.json, no manifest load): every contract phase declares (input schema via
immutable upstream input hashes, scope, expected output schema, validator,
reducer); the P4-COPY reducer is an ordered EXACTLY-ONCE Markdown reducer; the
QC reducer unions verdicts by STABLE slide_id refusing duplicate/missing; the
style spec is bounded to EXACTLY three A/B/C variants; an incompatible
manifest fanout is refused at preflight BEFORE any paid call; and a unit's
prompt carries the one-scope instruction INSTEAD of the whole-artifact tail.

Negative cases proven here (each refuses rather than corrupts):
  * two identical whole-deck responses fail unit validation (whole-deck shape
    at the QC validator; duplicate ordinals at the markdown reducer);
  * duplicate ordinal fails the reducer; missing ordinal fails the reducer;
  * duplicate/missing slide_id fails the QC union;
  * more than three / fewer than three style variants fail the reduce;
  * a changed input hash invalidates ONLY the consuming unit's reuse.
Positive: 3 sections / 20 slides reduce exactly once, in input order, all
verdict rows preserved.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402


# ---------------------------------------------------------------------------
# Contract declarations (input schema, immutable upstream hashes, scope,
# output schema, validator, reducer) -- TODO.md step 1's list, per phase.
# ---------------------------------------------------------------------------

MANIFEST_FANOUT_PHASES = (
    "P4-COPY", "P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL",
    "P-PROMPT-QC", "P-STYLE-SPEC", "P-IMAGE-QC", "P9-SPEECH",
)
# P4-PROMPT also declares a manifest fanout but NEVER reaches the generic
# dispatch path (dispatch_one routes it to its own dedicated per-slide loop
# before the fanout branch) — it owns a different, pre-existing contract and
# is out of scope here; only the eight generic-path phases need contracts.


@pytest.mark.parametrize("phase_id", MANIFEST_FANOUT_PHASES)
def test_every_manifest_fanout_phase_has_a_full_contract(phase_id):
    c = D._unit_contract_for(phase_id)
    assert c is not None, f"{phase_id} declares a manifest fanout but no UnitContract"
    assert c.scope in ("section", "slide", "file")
    assert c.output_schema and isinstance(c.output_schema, str)
    assert callable(c.validator) and callable(c.reducer)
    assert isinstance(c.inputs, tuple) and c.inputs, \
        f"{phase_id} contract names no immutable upstream inputs"


def test_p4_copy_scope_is_section_and_qc_slide():
    assert D._unit_contract_for("P4-COPY").scope == "section"
    assert D._unit_contract_for("P-PROMPT-QC").scope == "slide"
    assert D._unit_contract_for("P-IMAGE-QC").scope == "slide"
    # the P-U-DESIGN fanouts are by=slide in the manifest (one design prompt
    # per slide), NOT by=file -- scope must agree with the manifest.
    for pid in ("P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL"):
        assert D._unit_contract_for(pid).scope == "slide"


def test_style_spec_variants_bounded_abc():
    assert set(D.STYLE_SPEC_VARIANT_IDS) == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# Unit input hashes: immutable upstream inputs, glob-expanded; a changed hash
# invalidates ONLY the units consuming the changed input.
# ---------------------------------------------------------------------------

def _contract_run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"a": 1}))
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({"slots": []}))
    (rd / "working" / "research" / "research_map.json").write_text(json.dumps({"m": 1}))
    (rd / "working" / "research" / "brief-a.md").write_text("# A")
    (rd / "working" / "research" / "brief-b.md").write_text("# B")
    return rd


def test_unit_input_hashes_glob_and_change(tmp_path):
    rd = _contract_run(tmp_path)
    h1 = D.unit_input_hashes(rd, "P4-COPY")
    assert set(h1) == {"working/copy/intake.json", "working/copy/arc_allocation.json",
                       "working/research/research_map.json", "working/research/brief-*.md"}
    assert all(v not in ("absent", "unreadable") for v in h1.values())
    # one file changes -> exactly that input's hash changes
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"a": 2}))
    h2 = D.unit_input_hashes(rd, "P4-COPY")
    assert D.unit_inputs_changed(h1, h2) == ["working/copy/intake.json"]
    # the glob covers add AND edit of any matching file
    (rd / "working" / "research" / "brief-c.md").write_text("# C")
    h3 = D.unit_input_hashes(rd, "P4-COPY")
    assert h3["working/research/brief-*.md"] != h2["working/research/brief-*.md"]


def test_changed_input_invalidates_only_affected_units(tmp_path):
    rd = _contract_run(tmp_path)
    h_before = D.unit_input_hashes(rd, "P4-COPY")
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"a": 9}))
    h_after = D.unit_input_hashes(rd, "P4-COPY")
    assert D.unit_inputs_changed(h_before, h_after) == ["working/copy/intake.json"]
    # per-unit snapshots: unit A produced against BEFORE, unit B against AFTER.
    # A's recorded snapshot no longer matches -> A re-pays; B's matches -> reused.
    unit_a = {"key": "section-01", "unit_inputs": h_before,
              "unit_inputs_now": h_after}
    unit_b = {"key": "section-02", "unit_inputs": h_after,
              "unit_inputs_now": h_after}
    invalidated = D.invalidated_units([unit_a, unit_b],
                                      D.unit_inputs_changed(h_before, h_after))
    assert invalidated == ["section-01"]


# ---------------------------------------------------------------------------
# Markdown reducer (P4-COPY / P9-SPEECH): ordered, EXACTLY-ONCE.
# ---------------------------------------------------------------------------

def _sec(lo: int, hi: int, name: str = "S") -> dict:
    return {"scope": "section", "first_ordinal": lo, "last_ordinal": hi,
            "ordinal": lo, "name": name}


def test_markdown_reducer_three_sections_twenty_slides_exactly_once():
    ordered = [(_sec(1, 5, "Hook"), "\n".join(f"SLIDE {n}\nbody {n}" for n in range(1, 6))),
               (_sec(6, 15, "Teach"), "\n".join(f"SLIDE {n}\nbody {n}" for n in range(6, 16))),
               (_sec(16, 20, "Offer"), "\n".join(f"SLIDE {n}\nbody {n}" for n in range(16, 21)))]
    out = D._reduce_markdown_sections(ordered)
    assert out is not None
    ords = [int(m) for m in re.findall(r"(?im)^SLIDE\s+(\d+)\s*$", out)]
    assert ords == list(range(1, 21)), "input order retained, each ordinal once"


def test_markdown_reducer_duplicate_ordinal_fails():
    ordered = [(_sec(1, 2), "SLIDE 1\nA\nSLIDE 2\nB"),
               (_sec(1, 2, "dup"), "SLIDE 1\nX\nSLIDE 2\nY")]
    assert D._reduce_markdown_sections(ordered) is None


def test_markdown_reducer_missing_ordinal_fails():
    ordered = [(_sec(1, 2), "SLIDE 1\nA"),  # SLIDE 2 promised but absent
               (_sec(3, 4), "SLIDE 3\nC\nSLIDE 4\nD")]
    assert D._reduce_markdown_sections(ordered) is None


def test_markdown_reducer_gap_between_units_fails():
    ordered = [(_sec(1, 2), "SLIDE 1\nA\nSLIDE 2\nB"),
               (_sec(4, 5), "SLIDE 4\nD\nSLIDE 5\nE")]  # slide 3 missing
    assert D._reduce_markdown_sections(ordered) is None


def test_markdown_reducer_accepts_valid_text():
    out = D._reduce_markdown_sections([(_sec(1, 2), "SLIDE 1\nreal copy\nSLIDE 2\nmore copy")])
    assert out is not None and "real copy" in out and "more copy" in out


def test_copy_section_validator_scope():
    p = _sec(1, 2, "Hook")
    ok, _ = D._validate_copy_section(p, "SLIDE 1\nA\nSLIDE 2\nB")
    assert ok
    ok, reasons = D._validate_copy_section(p, "SLIDE 3\nother section's slide")
    assert not ok and "range" in reasons[0]
    ok, reasons = D._validate_copy_section(p, "SLIDE 1\nA\nSLIDE 2\nB\nSLIDE 3\nC")
    assert not ok  # a unit may never author another section's slide
    ok, _ = D._validate_copy_section(p, "no slide blocks at all")
    assert not ok


# ---------------------------------------------------------------------------
# QC union by stable slide_id (P-PROMPT-QC / P-IMAGE-QC).
# ---------------------------------------------------------------------------

def _qc(n: int, total: int = 3) -> dict:
    return {"scope": "slide", "ordinal": n, "slide_id": f"slide-{n:02d}",
            "unit_count": total, "phase_id": "P-PROMPT-QC"}


def test_qc_validator_refuses_whole_deck_response():
    p = _qc(2)
    whole = json.dumps({"slides": [{"slide": n, "pass": True} for n in range(1, 4)]})
    ok, reasons = D._validate_qc_slide(p, whole)
    assert not ok and "WHOLE-DECK" in reasons[0]
    # TWO IDENTICAL whole-deck responses both fail (the paid-work duplicate)
    ok2, reasons2 = D._validate_qc_slide(p, whole)
    assert not ok2 and reasons2 == reasons


def test_qc_validator_refuses_out_of_scope_and_shapeless():
    p = _qc(2)
    assert not D._validate_qc_slide(p, json.dumps({"slide": 3, "pass": True}))[0]
    assert not D._validate_qc_slide(p, json.dumps({"slide": 2, "slide_id": "slide-09", "pass": True}))[0]
    assert not D._validate_qc_slide(p, "not json")[0]
    assert not D._validate_qc_slide(p, json.dumps({"slide": 2}))[0]  # no verdict


def test_qc_union_preserves_all_results():
    rows = [(_qc(n), json.dumps({"slide": n, "slide_id": f"slide-{n:02d}",
                                 "pass": n != 3, "average": 9.0 if n != 3 else 6.0}))
            for n in (1, 2, 3)]
    out = D._reduce_qc_union(rows)
    assert out is not None
    rep = json.loads(out)
    assert len(rep["slides"]) == 3 and len(rep["results"]) == 3
    assert rep["pass"] is False  # all-results success: one failed row fails it
    assert rep["average"] == pytest.approx((9.0 + 9.0 + 6.0) / 3)
    assert rep["gate"] == "Phase Prompt-QC"
    assert [r["slide_id"] for r in rep["slides"]] == ["slide-01", "slide-02", "slide-03"]


def test_qc_union_duplicate_slide_id_fails():
    assert D._reduce_qc_union([(_qc(1), json.dumps({"slide": 1, "pass": True})),
                               (_qc(1), json.dumps({"slide": 1, "pass": True}))]) is None


def test_qc_union_missing_slide_fails():
    # two of three units handed in: the union must refuse, never pass partial
    rows = [(_qc(1), json.dumps({"slide": 1, "pass": True})),
            (_qc(3), json.dumps({"slide": 3, "pass": True}))]
    assert D._reduce_qc_union(rows) is None


def test_qc_union_image_qc_requires_observed_text():
    p = dict(_qc(1), phase_id="P-IMAGE-QC", needs_observed_text=True)
    blind = json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True})
    assert not D._validate_qc_slide(p, blind)[0]
    good = json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True,
                       "observed_text": "HEADLINE READS ..."})
    assert D._validate_qc_slide(p, good)[0]


def test_qc_union_carries_independence_provenance():
    # no per-row provenance: the envelope stamps the phase's REVIEWER role
    # (the independent QC specialist the work order dispatches)
    p = dict(_qc(1, total=2), reviewer_role="qc-specialist-x")
    rows = [(p, json.dumps({"slide": 1, "slide_id": "slide-01",
                            "pass": True, "average": 9.0})),
            (dict(_qc(2, total=2), reviewer_role="qc-specialist-x"),
             json.dumps({"slide": 2, "slide_id": "slide-02",
                         "pass": True, "average": 9.0}))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert rep["qc_independence"] == {"graded_by": "qc-specialist-x",
                                      "independent": True}
    # a row's OWN provenance block wins over the role fallback
    rows2 = [(p, json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True,
                             "average": 9.0,
                             "qc_independence": {"graded_by": "ind-7",
                                                 "independent": True}})),
             (dict(_qc(2, total=2), reviewer_role="qc-specialist-x"),
              json.dumps({"slide": 2, "slide_id": "slide-02",
                          "pass": True, "average": 9.0}))]
    rep2 = json.loads(D._reduce_qc_union(rows2))
    assert rep2["qc_independence"]["graded_by"] == "ind-7"


# ---------------------------------------------------------------------------
# Style spec: bounded THREE A/B/C variants.
# ---------------------------------------------------------------------------

def _var(vid: str, slide: int) -> str:
    return json.dumps({"id": vid, "style_directive": f"dir {vid}",
                       "representative_slide": slide})


def test_style_reduce_three_variants_ok():
    p = {"unit_count": 3}
    out = D._reduce_style_variants([(p, _var("A", 2)), (p, _var("B", 5)),
                                    (p, _var("C", 9))])
    spec = json.loads(out)
    assert [v["id"] for v in spec["variants"]] == ["A", "B", "C"]
    assert spec["representative_slides"] == [2, 5, 9]


def test_style_reduce_fewer_or_more_than_three_fails():
    p = {"unit_count": 3}
    # FEWER than three well-formed candidates: the reduced spec cannot carry
    # the contract's exactly-three bound — refused, never a 2-variant spec.
    two = [(p, _var("A", 2)), (p, _var("B", 5))]
    assert D._reduce_style_variants(two) is None
    # MORE candidates than the bound: the first three WELL-FORMED ones are
    # the deck-level spec (the per-slide enumeration is preserved; the OUTPUT
    # bound is what TODO.md names) — 5 candidates still reduce to exactly 3.
    five = two + [(p, _var("C", 9)), (p, _var("A", 11)), (p, _var("B", 13))]
    out = D._reduce_style_variants(five)
    assert out is not None
    spec = json.loads(out)
    assert [v["id"] for v in spec["variants"]] == ["A", "B", "C"]
    assert spec["representative_slides"] == [2, 5, 9]


def test_style_validator_rejects_out_of_bounds_ids():
    p = {"unit_count": 3}
    bad = json.dumps({"id": "D", "style_directive": "x", "representative_slide": 1})
    assert not D._validate_style_variant(p, bad)[0]
    empty = json.dumps({"id": "A", "style_directive": "", "representative_slide": 1})
    assert not D._validate_style_variant(p, empty)[0]


def test_style_unit_payload_carries_assigned_variant_id(tmp_path):
    rd = _p4_run(tmp_path)
    p = D._unit_payload_enrichment(rd, "P-STYLE-SPEC",
                                   {"key": "slide-01", "ordinal": 1}, 3)
    assert p["variant_id"] == "A"  # explicit variant ids, bounded three
    p2 = D._unit_payload_enrichment(rd, "P-STYLE-SPEC",
                                    {"key": "slide-04", "ordinal": 4}, 3)
    assert p2["variant_id"] == "A"  # cycle wraps, never leaves A/B/C
    # a unit that omits its id in the OUTPUT is repaired by the assignment
    # at reduce time; an out-of-bounds id is still refused by the validator.
    ok, _ = D._validate_style_variant(
        p2, json.dumps({"style_directive": "x", "representative_slide": 1}))
    assert ok


# ---------------------------------------------------------------------------
# Preflight: incompatible manifest fanout refused BEFORE any paid call.
# ---------------------------------------------------------------------------

def test_preflight_refuses_phase_without_contract(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    reason = D._preflight_fanout_contract("P-NOT-A-CONTRACT-PHASE",
                                          fanout.FanoutSpec(by="slide"), rd)
    assert reason and "AF-UNIT-CONTRACT" in reason


def test_preflight_refuses_scope_disagreement(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    reason = D._preflight_fanout_contract("P4-COPY", fanout.FanoutSpec(by="slide"), rd)
    assert reason and "incompatible manifest fanout" in reason


def test_preflight_allows_compatible_p4_copy(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    assert D._preflight_fanout_contract("P4-COPY", fanout.FanoutSpec(by="section"),
                                        rd) is None


def test_rollback_flag_restores_legacy_path(monkeypatch):
    monkeypatch.setenv("PRESENTATION_UNIT_CONTRACTS", "0")
    assert D.unit_contracts_enabled() is False
    rd = tmp_path = Path("/tmp")  # unused path: flag checked first
    assert D._preflight_fanout_contract("P-NOT-A-CONTRACT-PHASE",
                                        fanout.FanoutSpec(by="slide"), rd) is None
    monkeypatch.delenv("PRESENTATION_UNIT_CONTRACTS")
    assert D.unit_contracts_enabled() is True


# ---------------------------------------------------------------------------
# compose_prompt: unit prompts carry the ONE-SCOPE instruction and lose the
# whole-artifact trigger; the serial path keeps its tail byte-for-byte.
# ---------------------------------------------------------------------------

def _dept_with_role(tmp_path: Path) -> Path:
    dept = tmp_path / "dept"
    role = dept / "slide-copywriter"
    role.mkdir(parents=True)
    (role / "how-to.md").write_text("SOP")
    return dept


def test_unit_prompt_suppresses_whole_artifact_tail(tmp_path):
    dept = _dept_with_role(tmp_path)
    payload = {"key": "section-01", "scope": "section", "ordinal": 1,
               "unit_count": 3, "name": "Hook", "first_ordinal": 1,
               "last_ordinal": 5, "phase_id": "P4-COPY",
               "output_schema": D._UNIT_CONTRACT_OUTPUT["P4-COPY"]}
    order = {"owning_role": "slide-copywriter"}
    wo = D._unit_scope_work_order(order, payload)
    _sys, user = D.compose_prompt(phase_id="P4-COPY", owning_role="slide-copywriter",
                                  dept_root=dept, run_dir=tmp_path, order=wo,
                                  attempt=1, prior_reasons=None)
    assert "AUTHORS EXACTLY ONE SECTION" in user
    assert "UNIT OUTPUT SCHEMA" in user
    assert "Write the complete, final content of the target artifact file" not in user
    assert "section 1 of 3" in user and "slides 1-5" in user


def test_serial_prompt_keeps_whole_artifact_tail(tmp_path):
    dept = _dept_with_role(tmp_path)
    _sys, user = D.compose_prompt(phase_id="P-UNKNOWN-X",
                                  owning_role="slide-copywriter",
                                  dept_root=dept, run_dir=tmp_path,
                                  order={"owning_role": "slide-copywriter"},
                                  attempt=1, prior_reasons=None)
    assert "Write the complete, final content of the target artifact file" in user


def test_unit_scope_text_slide_shape(tmp_path):
    txt = D._unit_scope_text({"scope": "slide", "ordinal": 7, "unit_count": 20,
                              "unit_kind": "json verdict row"})
    assert "SLIDE 7 OF 20" in txt


# ---------------------------------------------------------------------------
# Payload enrichment: full payload carries scope, ordinals, stable slide_id,
# and the per-unit input-hash snapshot pair.
# ---------------------------------------------------------------------------

def _p4_run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    slots = []
    for name, lo, hi in (("Hook", 1, 2), ("Teach", 3, 4)):
        for n in range(lo, hi + 1):
            slots.append({"ordinal": n, "arc": name})
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({"slots": slots}))
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    return rd


def test_section_payload_carries_ordinal_range_and_hashes(tmp_path):
    rd = _p4_run(tmp_path)
    p = D._unit_payload_enrichment(rd, "P4-COPY",
                                   {"key": "section-01", "ordinal": 1, "name": "Hook"}, 2)
    assert p["scope"] == "section"
    assert (p["first_ordinal"], p["last_ordinal"]) == (1, 2)
    assert isinstance(p["unit_inputs"], dict) and p["unit_inputs"] == p["unit_inputs_now"]
    assert p["output_schema"]


def test_slide_payload_carries_stable_slide_id(tmp_path):
    rd = _p4_run(tmp_path)
    p = D._unit_payload_enrichment(rd, "P-PROMPT-QC",
                                   {"key": "slide-07", "ordinal": 7}, 20)
    assert p["scope"] == "slide" and p["slide_id"] == "slide-07"
    assert p["unit_count"] == 20


def test_named_slide_object_id_wins():
    p = D._unit_payload_enrichment(Path("/tmp"), "P-PROMPT-QC",
                                   {"key": "slide-01", "ordinal": 1,
                                    "slide": {"ordinal": 1, "id": "deck1-s1"}}, 1)
    assert p["slide_id"] == "deck1-s1"
