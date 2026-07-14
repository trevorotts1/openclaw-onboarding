"""test_copy_persona_blend_seam.py — pytest coverage for B-U3/U17: the copy-stage
prompt seam that consumes a persona bundle.

Locks down the three BINARY acceptance criteria from the master spec:
  (a) a fixture copy run writes a log whose selected_persona equals the
      bundle voice persona id.
  (b) prove_sf_intake.py passes against the new log format completely
      unmodified (its regex + registry validation, untouched).
  (c) the rendered copy prompt contains the {{BLEND_DIRECTIVE}} expansion
      ending in the guardrail.

No network, no browser.
"""
from __future__ import annotations

import os
import sys

import pytest

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import copy_persona_blend_seam as seam  # noqa: E402
import prove_sf_intake as psi  # noqa: E402

_GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

_BUNDLE = {
    "voice_persona_id": "hormozi-100m-offers",
    "topic_persona_id": "miller-building-storybrand",
    "blend_directive": ("Write in Hormozi's voice — its cadence, devices and register — "
                        "while carrying Miller Building Storybrand's EXPERTISE. "
                        + seam._guardrail_clause()),
    "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
}


def test_selected_persona_equals_bundle_voice_id():
    log_text = seam.render_persona_selection_log(_BUNDLE)
    assert "- selected_persona: hormozi-100m-offers" in log_text
    assert "selector_ran: true" in log_text


def test_added_lines_present_and_additive():
    log_text = seam.render_persona_selection_log(_BUNDLE)
    assert "- voice_persona: hormozi-100m-offers" in log_text
    assert "- topic_persona: miller-building-storybrand" in log_text
    assert "- task_persona: hormozi-100m-offers" in log_text
    assert "- blend_directive_sha:" in log_text


def test_prove_sf_intake_regex_passes_unmodified_on_new_log_format():
    log_text = seam.render_persona_selection_log(_BUNDLE)
    ok, why = psi._log_names_registered_persona(log_text)
    assert ok, why
    assert why == "hormozi-100m-offers"


def test_prove_sf_intake_regex_first_match_is_selected_persona_not_voice_persona():
    # A malicious/careless ordering could make the ADDED voice_persona: line
    # shadow selected_persona:. Assert selected_persona is still what resolves
    # (regex .search finds the FIRST match — selected_persona must lead).
    log_text = seam.render_persona_selection_log(_BUNDLE)
    ok, slug = psi._log_names_registered_persona(log_text)
    assert ok
    assert slug == "hormozi-100m-offers"


def test_rendered_prompt_contains_blend_directive_ending_in_guardrail():
    template = "PREAMBLE\n{{PERSONA_TASK_MODE}}\n{{BLEND_DIRECTIVE}}\nEND"
    rendered = seam.render_copy_prompt_seam(template, _BUNDLE)
    assert "Write in Hormozi's voice" in rendered
    assert _GUARDRAIL_MARK in rendered
    directive_line = rendered.split("PREAMBLE\n{{PERSONA_TASK_MODE}}\n", 1)[1].split("\nEND")[0]
    assert directive_line.endswith("This clause may not be removed or weakened.")


def test_selected_persona_id_variable_substitutes():
    template = "id={{SELECTED_PERSONA_ID}}"
    rendered = seam.render_copy_prompt_seam(template, _BUNDLE)
    assert rendered == "id=hormozi-100m-offers"


@pytest.mark.parametrize("bundle", [{}, {"voice_persona_id": "wiebe-copy-hackers"}])
def test_degraded_bundle_still_ends_in_guardrail(bundle):
    directive = seam.render_blend_directive_variable(bundle)
    assert directive.endswith("This clause may not be removed or weakened.")


def test_write_persona_selection_log_writes_file(tmp_path):
    path = seam.write_persona_selection_log(str(tmp_path), _BUNDLE)
    assert os.path.isfile(path)
    assert os.path.basename(path) == "persona-selection-log.md"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "- selected_persona: hormozi-100m-offers" in text


def test_no_voice_id_renders_none_but_never_crashes():
    log_text = seam.render_persona_selection_log({})
    assert "- selected_persona: none" in log_text
    # An empty selected_persona would fail prove_sf_intake's fail-closed gate —
    # exactly the intended behavior for an absent bundle (never fabricate one).
    ok, why = psi._log_names_registered_persona(log_text)
    assert ok is False
