"""PD-300 -- the grader is STAMPED into every merged quality report.

Finding PD-300, decision D-29 default. Before this unit the merged QC report
carried no statement of which provider/model graded it, so the image check and
every later grader-vs-author comparison had nothing to read.

What is proven here (no paid call, no manifest load, no network):
  * the reducer writes `graded_by_provider` / `graded_by_model` per row from
    THAT unit's own recorded route, overriding anything the model wrote about
    itself;
  * the same fields are written at the top level ONLY when every row agrees --
    a merge whose units used different grading models keeps them per row and
    makes no top-level claim;
  * `request_id` is recorded per row and at the top level, and is `null` when
    the provider returned none -- an id is never invented;
  * `author_model` comes from the trusted execution stamps of the graded
    files, and a graded file whose bytes changed after its stamp has no author
    (unproven), never a stale name.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import execution_stamp as ES  # noqa: E402


def _unit(ordinal: int, total: int, **kw) -> dict:
    p = {"phase_id": "P-IMAGE-QC", "unit_count": total, "ordinal": ordinal,
         "slide_id": f"slide-{ordinal:02d}", "reviewer_role": "qc-specialist-x"}
    p.update(kw)
    return p


def _verdict(ordinal: int) -> str:
    return json.dumps({"slide": ordinal, "slide_id": f"slide-{ordinal:02d}",
                       "pass": True, "average": 9.0,
                       "observed_text": "HEADLINE READS ..."})


def test_grader_stamped_per_row_and_at_the_top_level():
    rows = [(_unit(1, 2, route_provider="ollama-cloud",
                   route_model="glm-ocr", route_request_id="req-1"),
             _verdict(1)),
            (_unit(2, 2, route_provider="ollama-cloud",
                   route_model="glm-ocr", route_request_id="req-1"),
             _verdict(2))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert rep["graded_by_provider"] == "ollama-cloud"
    assert rep["graded_by_model"] == "glm-ocr"
    assert rep["request_id"] == "req-1"
    for row in rep["slides"]:
        assert row["graded_by_provider"] == "ollama-cloud"
        assert row["graded_by_model"] == "glm-ocr"
        assert row["request_id"] == "req-1"


def test_mixed_graders_write_per_row_only():
    rows = [(_unit(1, 2, route_provider="ollama-cloud",
                   route_model="glm-ocr", route_request_id="req-1"),
             _verdict(1)),
            (_unit(2, 2, route_provider="openrouter",
                   route_model="z-ai/glm-4.6v", route_request_id="req-2"),
             _verdict(2))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert "graded_by_model" not in rep
    assert "graded_by_provider" not in rep
    assert "request_id" not in rep
    assert [r["graded_by_model"] for r in rep["slides"]] == [
        "glm-ocr", "z-ai/glm-4.6v"]
    # one call per slide: nothing shared, so no report-level request_id claim —
    # but the legacy key names the FIRST unit's REAL id (never a fabricated one)
    # because the FIX 33 readers accept it and need a route id to trace.
    assert rep["route_request_id"] == "req-1"
    assert [r["request_id"] for r in rep["slides"]] == ["req-1", "req-2"]


def test_a_model_cannot_stamp_its_own_grader_claim():
    # the model's prose says one thing; the dispatch record says another and wins
    forged = json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True,
                         "graded_by_model": "deepseek-v4",
                         "graded_by_provider": "deepseek-direct"})
    rep = json.loads(D._reduce_qc_union(
        [(_unit(1, 1, route_provider="ollama-cloud", route_model="glm-ocr"),
          forged)]))
    assert rep["slides"][0]["graded_by_model"] == "glm-ocr"
    assert rep["slides"][0]["graded_by_provider"] == "ollama-cloud"
    assert rep["graded_by_model"] == "glm-ocr"


def test_unknown_route_is_null_never_invented():
    rows = [(_unit(1, 1), _verdict(1))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert rep["graded_by_provider"] is None
    assert rep["graded_by_model"] is None
    assert rep["request_id"] is None
    assert rep["slides"][0]["request_id"] is None


def test_author_model_is_carried_from_the_payload():
    rows = [(_unit(1, 1, author_model="deepseek-v4"), _verdict(1))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert rep["author_model"] == "deepseek-v4"
    # absent stamp evidence is null, never a name
    rep2 = json.loads(D._reduce_qc_union([(_unit(1, 1), _verdict(1))]))
    assert rep2["author_model"] is None


def test_graded_author_model_reads_the_stamp_and_refuses_a_revised_file(
        tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    slide = run_dir / "renders" / "slide-01.png"
    slide.parent.mkdir(parents=True)
    slide.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    monkeypatch.setattr(D, "_graded_artifacts", lambda rd, pid: [slide])

    # no stamp yet -> unproven, not a guess
    assert D._graded_author_model(run_dir, "P-IMAGE-QC") == ""

    ES.author_stamp(run_dir, "P4-RENDER", slide,
                    model="deepseek-v4", provider="deepseek-direct")
    assert D._graded_author_model(run_dir, "P-IMAGE-QC") == "deepseek-v4"

    # a repaired file is a NEW revision with no stamp for its current bytes
    slide.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
    assert D._graded_author_model(run_dir, "P-IMAGE-QC") == ""
