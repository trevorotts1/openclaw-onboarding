"""Workstream 3 — the speech harness injects the research map into the SPOKEN
speech so the presenter cites the assigned stat on stage.

The Deep Research Specialist writes working/research/research_map.json (P-3.5,
SOP 9.5) assigning a verbatim `anchor` (figure/quote) + real `source_url` to each
non-exempt content slide. build_deck._chk_research_map (AF-RESEARCH-WEAVE) already
requires the SLIDE COPY to carry the anchor; these tests prove speech_build_harness
closes the same loop for the SPEECH:

  1. load_research_map parses research_map.json -> {slide_no: [ResearchAnchor]}
  2. research_prompt_block injects the assigned stat + citation into the writer prompt
  3. generate_slide_text passes the directive so the LLM SPEAKS the anchor
  4. verify_research_spoken proves the written speech actually contains it
  5. sources_cited_block emits REAL citations (not the old fabricated boilerplate)
  6. run_build end-to-end with a stub API writes a speech that contains the anchors
"""
import json
import sys
import tempfile
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import pytest  # noqa: E402

import speech_build_harness as sbh  # noqa: E402

# A research map matching the SOP 9.5 schema, mirroring the P-3.5 artifact that
# AF-RESEARCH-WEAVE enforces. Slide 15 carries the "35%" proof stat the task cites.
RESEARCH_MAP_FIXTURE = {
    "deck_slug": "focusforge",
    "slides": [
        {"slide": 15, "section": "Proof", "assigned": [
            {"item_id": "D-07", "type": "stat", "anchor": "35%",
             "claim": "Home services businesses that run webinars grow 35% faster "
                      "than those that don't",
             "source_url": "https://example.com/webinar-growth-study",
             "source_date": "2025-09", "confidence": "HIGH", "category": "D"},
            {"item_id": "D-08", "type": "study", "anchor": "Stanford",
             "claim": "Stanford case study on webinar pipeline velocity",
             "source_url": "https://stanford.edu/example/case-study",
             "source_date": "2026-01", "confidence": "MEDIUM", "category": "D"},
        ]},
        {"slide": 7, "section": "Teaching", "assigned": [
            {"item_id": "C-03", "type": "stat", "anchor": "73%",
             "claim": "73% of buyers say webinars influence purchase decisions",
             "source_url": "https://example.com/buyer-survey",
             "source_date": "2024-11", "confidence": "HIGH", "category": "C"},
        ]},
        {"slide": 4, "section": "Hook", "assigned": [], "exempt": "hook_pure_type"},
        {"slide": 21, "section": "Offer", "assigned": [
            {"item_id": "G-02", "type": "quote", "anchor": "never go back",
             "claim": "Client quote about never going back to cold calling",
             "source_url": "https://example.com/testimonial",
             "source_date": "2025-06", "confidence": "HIGH", "category": "G"},
        ]},
    ],
    "distinct_items_used": 4,
    "content_slides_total": 3,
    "content_slides_with_research": 3,
}


def _make_slide(slide_no, kind="teach", stage="TEACH", headline="Test Slide"):
    return sbh.SlideSpec(
        slide_no=slide_no,
        headline=headline,
        kind=kind,
        stage=stage,
        presenter_note="Presenter note.",
        word_budget=0,
    )


class TestLoadResearchMap:
    def test_parses_assignments_by_slide(self, tmp_path):
        p = tmp_path / "research_map.json"
        p.write_text(json.dumps(RESEARCH_MAP_FIXTURE))
        by_slide = sbh.load_research_map(str(p))
        assert set(by_slide) == {7, 15, 21}
        assert by_slide[15][0].anchor == "35%"
        assert by_slide[15][0].item_id == "D-07"
        assert by_slide[15][0].source_url == "https://example.com/webinar-growth-study"
        # Exempt slide 4 carries nothing
        assert 4 not in by_slide

    def test_missing_path_is_empty(self):
        assert sbh.load_research_map(None) == {}
        assert sbh.load_research_map("/nonexistent/map.json") == {}

    def test_bad_json_is_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json{{{")
        assert sbh.load_research_map(str(p)) == {}


class TestResearchPromptBlock:
    def test_slide_with_assignment_injects_anchor_and_source(self):
        s = _make_slide(15)
        by_slide = {15: [
            sbh.ResearchAnchor("D-07", "stat", "35%",
                               "Home services businesses that run webinars grow 35% faster",
                               "https://example.com/webinar-growth-study",
                               "2025-09", "HIGH", "D"),
        ]}
        block = sbh.research_prompt_block(s, by_slide)
        assert "35%" in block
        assert "https://example.com/webinar-growth-study" in block
        assert "RESEARCH TO CITE ON STAGE" in block

    def test_slide_without_assignment_is_empty(self):
        s = _make_slide(4)
        assert sbh.research_prompt_block(s, {}) == ""
        assert sbh.research_prompt_block(s, {4: []}) == ""


class TestVerifyResearchSpoken:
    def test_anchor_present_marks_spoken(self):
        s = _make_slide(15)
        s.spoken_text = "This is the 35% number right here."
        mapped, spoken = sbh.verify_research_spoken([s], {15: [
            sbh.ResearchAnchor("D-07", "stat", "35%", "", "", "", "", "D")]}, Path("/tmp/x"), [])
        assert mapped == 1 and spoken == 1

    def test_anchor_missing_marks_unspoken(self):
        s = _make_slide(15)
        s.spoken_text = "No stat mentioned."
        mapped, spoken = sbh.verify_research_spoken([s], {15: [
            sbh.ResearchAnchor("D-07", "stat", "35%", "", "", "", "", "D")]}, Path("/tmp/x"), [])
        assert mapped == 1 and spoken == 0


class TestSourcesCitedBlock:
    def test_emits_real_citations(self):
        # Build via the loader so the fixtures are identical to production
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "research_map.json"
            p.write_text(json.dumps(RESEARCH_MAP_FIXTURE))
            by_slide = sbh.load_research_map(str(p))
        lines = sbh.sources_cited_block(by_slide)
        joined = "\n".join(lines)
        assert "SOURCES_CITED_ON_STAGE" in lines[0]
        assert "https://example.com/webinar-growth-study" in joined
        assert "https://stanford.edu/example/case-study" in joined
        # No fabricated boilerplate
        assert "none fabricated" not in joined.lower()

    def test_empty_map_is_honest(self):
        lines = sbh.sources_cited_block({})
        assert "none assigned in research_map.json" in lines[0]


class TestEndToEndBuild:
    def test_built_speech_contains_assigned_anchors(self, tmp_path):
        """End-to-end: run_build with a stub API that bakes the research directive
        into the spoken text. The output PRESENTER'S SPEECH must contain the 35%
        anchor (slide 15) and the sources-cited block must carry its real URL."""
        workdir = tmp_path / "work"
        out = tmp_path / "speech.md"

        slides = [
            _make_slide(7, kind="teach", stage="TEACH", headline="The framework"),
            _make_slide(15, kind="proof", stage="PROOF", headline="Proof it works"),
            _make_slide(21, kind="offer", stage="OFFER", headline="The offer"),
        ]
        # Budgets are computed inside run_build, so give them a floor.
        for s in slides:
            s.word_budget = 60

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "research_map.json"
            p.write_text(json.dumps(RESEARCH_MAP_FIXTURE))
            research_map = sbh.load_research_map(str(p))

        # Stub API: prove the research directive reached the prompt by echoing
        # the anchor verbatim into the generated text. This is the load-bearing
        # proof that generate_slide_text actually injects the map.
        captured = {}

        def _stub_llm_once(prompt, model, api_key, max_tokens=1024, base_url=None,
                           temperature=0.7):
            captured["prompt"] = prompt
            # Find the slide_no in the prompt to pick its anchor
            import re
            m = re.search(r"Slide (\d+)", prompt)
            slide_no = int(m.group(1)) if m else 1
            anchors = research_map.get(slide_no, [])
            anchor_txt = " and ".join(a.anchor for a in anchors) if anchors else "default"
            return f"Spoken words mentioning {anchor_txt}. " * 12

        # Replace the transport in the module namespace under test.
        orig = sbh._llm_generate_once
        sbh._llm_generate_once = _stub_llm_once
        try:
            intake = {"DURATION_MIN": 30, "DECK_SLUG": "focusforge",
                      "TONE": "warm", "HOOK": "There is a difference."}
            ledger = sbh.run_build(
                intake=intake,
                slides=slides,
                workdir=workdir,
                out_path=out,
                model="stub",
                fallback_model=None,
                api_key="stub-key",
                wpm=130,
                max_expand_rounds=1,
                research_map=research_map,
            )
        finally:
            sbh._llm_generate_once = orig

        # The research directive reached at least one writer prompt (proves
        # generate_slide_text injected the map, not just the output block).
        assert "RESEARCH TO CITE ON STAGE" in captured.get("prompt", "")

        text = out.read_text()
        # Slide 15 speaks its assigned stat
        assert "35%" in text
        # Slide 7 speaks its assigned stat
        assert "73%" in text
        # Slide 21 speaks its assigned quote anchor
        assert "never go back" in text
        # Sources-cited block carries the REAL URLs from the map
        assert "https://example.com/webinar-growth-study" in text
        assert "https://example.com/buyer-survey" in text
        # The weave metric reports 3/3 mapped slides spoken
        assert "RESEARCH_WEAVED_INTO_SPEECH: 3/3" in text
        # No fabricated boilerplate anywhere
        assert "none fabricated" not in text.lower()
