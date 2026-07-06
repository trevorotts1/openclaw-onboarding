"""Tests for the operator-only delivery report generator (W1.26, PRD Step 18)."""

from __future__ import annotations

import pytest

import delivery_report as dr


def _interview_record():
    return {
        "job_id": "pj_01",
        "client_id": "acme",
        "contact_id": "ct_9",
        "episode_number": 12,
        "episode_title": "The Cost of Playing Small",
        "spoken_word_count": 1420,
        "runtime_minutes": 10.1,
        "style": "provocative",
        "mode": "interview_style_podcast",
        "writing_model": "ollama-cloud/kimi-2.6",
        "writing_model_substitution": "gemini-3.1-flash-lite (Kimi and GLM both refused)",
        "research_tool": "perplexity",
        "document_destination": "google",
        "episode_package_url": "https://docs.example.com/package",
        "speech_script_url": "https://docs.example.com/script",
        "mp3_media_url": "https://media.example.com/ep12.mp3",
        "cover_image_url": "https://media.example.com/ep12.jpg",
        "book_teaser_url": "https://media.example.com/ep12-teaser.pdf",
        "podbean_permalink": "https://acme.podbean.com/e/ep12",
        "image_prompt": "A lone founder at a crossroads at dawn, bold cinematic light",
        "ghl_save_confirmations": {
            "podcast_survey_episode_title": "read-back PASS",
            "podcast_survey_episode_url": "read-back PASS",
        },
        "enrollment": {
            "04-Podcast is Completed": "enrolled via field trigger, verified",
            "06-Podcast_Episode_Is_Ready": "enrolled, verified",
        },
        "rubric": {k: 9 for k, _ in dr.RUBRIC_DIMENSIONS},
        "checklist_state": {"smoke_test": True, "title_created": True, "tier1_all": True},
        "cost_usd": 1.31,
    }


def test_report_contains_every_mandated_field():
    report = dr.build_report(_interview_record())
    for needle in [
        "The Cost of Playing Small",
        "1420",
        "about 10.1 minutes",
        "provocative",
        "interview_style_podcast",
        "ollama-cloud/kimi-2.6",
        "substitution:",
        "perplexity",
        "Episode Package: https://docs.example.com/package",
        "Speech Script: https://docs.example.com/script",
        "Episode MP3: https://media.example.com/ep12.mp3",
        "Cover image: https://media.example.com/ep12.jpg",
        "Book teaser PDF: https://media.example.com/ep12-teaser.pdf",
        "Podbean episode link: https://acme.podbean.com/e/ep12",
        "Convert and Flow save confirmations",
        "A lone founder at a crossroads",
        "RUBRIC SCORES",
        "PART A, PER-EPISODE CHECKLIST",
    ]:
        assert needle in report, needle


def test_report_has_no_forbidden_glyphs():
    report = dr.build_report(_interview_record())
    assert "\u2014" not in report  # em dash
    assert (chr(96) * 3) not in report
    # the assertion inside build_report would already raise, but double-check
    dr.assert_no_forbidden_glyphs(report)


def test_report_is_operator_labeled_never_customer():
    report = dr.build_report(_interview_record())
    assert "OPERATOR ONLY" in report
    assert "NOT FOR THE CUSTOMER" in report


def test_checklist_honesty_missing_is_unchecked_not_faked():
    record = _interview_record()
    checklist = dr.reproduce_checklist_part_a(record)
    # explicitly recorded true -> checked
    assert "[x] First-run smoke test passed" in checklist
    # unrecorded item -> unchecked with an honest marker, never silently checked
    assert "[ ] (state not recorded) Preferred pronoun captured" in checklist


def test_personal_mode_skips_book_teaser_section():
    record = _interview_record()
    record["mode"] = "personal_podcast_style"
    checklist = dr.reproduce_checklist_part_a(record)
    assert "not applicable, Personal mode skips the book teaser" in checklist
    report = dr.build_report(record)
    assert "Book teaser PDF: (not applicable, Personal mode)" in report
    assert "running spreadsheet" in report.lower()


def test_rubric_below_minimum_flags_fail():
    record = _interview_record()
    record["rubric"]["opening_power"] = 6
    report = dr.build_report(record)
    assert "Opening Power: 6 -> FAIL" in report
    assert "ONE OR MORE DIMENSIONS BELOW 8" in report


def test_secrets_are_redacted_from_the_report():
    record = _interview_record()
    record["image_prompt"] = "prompt leaking pit-SECRETVALUE123 do not print"
    report = dr.build_report(record)
    assert "pit-SECRETVALUE123" not in report
    assert "[REDACTED]" in report


def test_operator_destination_guard_refuses_client_channels():
    for bad in ["customer-sms", "client-chat", "guest_email", "whatsapp", "subscriber"]:
        with pytest.raises(ValueError):
            dr.assert_operator_destination(bad)
    # operator names pass
    for ok in ["operator", "founder-ops", "ops-channel", None]:
        dr.assert_operator_destination(ok)


def test_deliver_routes_to_injected_operator_sink():
    captured = {}

    def sink(text):
        captured["text"] = text

    report = dr.deliver(_interview_record(), destination="operator", sink=sink)
    assert captured["text"] == report
    assert "OPERATOR ONLY" in captured["text"]


def test_deliver_refuses_client_destination_before_emitting():
    calls = []
    with pytest.raises(ValueError):
        dr.deliver(_interview_record(), destination="customer", sink=lambda t: calls.append(t))
    assert calls == []  # nothing emitted
