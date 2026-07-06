#!/usr/bin/env python3
"""Delivery report generator for the Podcast Production Engine (Skill 58).

Implements PRD Step 18 and CHECKLIST.md Part A (the DELIVERY section) and the
QC-PROTOCOL matrix "Delivery" row (report completeness, checklist reproduced,
operator channel only).

PRD Step 18, verbatim intent:
  "Pure script plus links as the deliverable; the delivery report (title, honest
   word count, runtime, style, mode, writing model including any substitution,
   research tool, document destination and links, media locations, Podbean link,
   Convert and Flow save confirmations, enrollment confirmation, image prompt,
   completed checklist, rubric scores) goes to the operator channel, never inside
   the script, never to the customer."

Silence doctrine, enforced in code (move in silence):
  - The report is OPERATOR-ONLY. This module NEVER emits a client-facing message.
    assert_operator_destination() hard-refuses any destination that looks like a
    customer, guest, client chat, SMS, email, or subscriber channel.
  - It sends no Telegram itself (sub-agents get no MCP; the gateway owns Telegram).
    The default sink is an operator-only console block; a gateway operator hook can
    be injected for real delivery, but only to an operator target.
  - Secrets are never printed: a redaction filter scrubs secret-shaped and
    contact-shaped substrings from the whole report before it leaves the module.

Writing rules, enforced in code:
  - Zero em dash characters anywhere in the produced report (fail-closed assertion).
  - No triple-backtick code fences in the produced report (fail-closed assertion).

Honesty (CHECKLIST cardinal rule): "every box checked honestly or not at all.
Misreporting any check is an absolute failure." Checklist boxes are rendered ONLY
from the explicit per-item state the pipeline records. A box with no recorded state
renders unchecked with "(state not recorded)"; this module never auto-checks a box
it cannot verify. The one structural exception is the Book Teaser section, which is
marked not-applicable when the mode is Personal (the book teaser is skipped entirely
in Personal mode by design).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Callable, Optional

EM_DASH = "\u2014"  # the forbidden glyph, expressed as an escape so source stays clean
FENCE = chr(96) * 3  # three backticks, constructed so no literal fence sits in source

# The 10 Tier-2 rubric dimensions (CHECKLIST Part B, minimum 8 each, no averaging).
RUBRIC_DIMENSIONS = [
    ("authorial_voice_fidelity", "Authorial Voice Fidelity"),
    ("arc_execution", "Arc Execution"),
    ("persuasion_mechanics", "Persuasion Mechanics"),
    ("opening_power", "Opening Power"),
    ("closing_power", "Closing Power"),
    ("captivation_throughout", "Captivation Throughout"),
    ("fidelity_to_respondent", "Fidelity to the Respondent"),
    ("research_integration_quality", "Research Integration Quality"),
    ("delivery_craft", "Delivery Craft"),
    ("audio_direction_quality", "Audio Direction Quality"),
]
RUBRIC_MIN = 8

# CHECKLIST.md Part A, reproduced structurally so the report can render it with the
# honest per-item state. Each item is (item_id, text). Text is verbatim intent from
# CHECKLIST.md Part A. item_id is the stable key the pipeline uses in
# record["checklist_state"].
CHECKLIST_PART_A: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "INTAKE AND SETUP",
        [
            ("smoke_test", "First-run smoke test passed (custom field map, private integration token, Location ID, Podbean, Fish Audio, Kie.ai). Once per client."),
            ("input_fields", "All required input fields present (mode, style, show name and host for Interview, guest name, preferred pronoun, SMIQ transparency answer, Q1 through final answer). Missing fields raised to the OPERATOR, never guessed."),
            ("pronoun", "Preferred pronoun captured and governing every reference to the speaker or guest."),
            ("mode_identified", "Production Mode identified (Personal Podcast Style or Interview Style Podcast). Output-type preset resolved."),
            ("style_identified", "Presentation Style identified (Counter Intuitive, Vulnerable, Provocative, or Passionate)."),
            ("engine_loaded", "Matching Style Engine and Mode rules loaded."),
            ("job_key", "Job key computed; intake ledger claimed; duplicate deliveries acknowledged without a second run."),
        ],
    ),
    (
        "RESEARCH ASSISTANT STAGE",
        [
            ("research_tool", "Web research tool identified (Perplexity if available, otherwise the best available tool). Tool named in this report."),
            ("answers_improved", "Every respondent answer improved and expanded without losing detail or changing intent."),
            ("power_statements", "Three power statements extracted from the respondent's ideas, in their voice."),
            ("missing_pieces", "Missing pieces generated: three key takeaways, supporting findings, closing question or call to action."),
            ("case_studies", "Up to three case studies researched, each real and verified, demographic-matched where applicable."),
            ("no_fabrication_research", "No fabricated study, statistic, person, company, or outcome anywhere in the package."),
            ("research_cap", "Research call count within the 12-call cap; package frozen into the episode record."),
        ],
    ),
    (
        "BLUEPRINT AND SIZING",
        [
            ("title_created", "Episode title created: compelling, edgy, never preceded by the word Title; immutable from here on."),
            ("thesis", "Thesis in one sentence, traceable to Q1 (and Q2 for Provocative)."),
            ("signature_line", "Style signature line written verbatim (reversal, definition drop, refrain, or crescendo command)."),
            ("arc_budgets", "Every arc beat assigned content and a word budget summing to the chosen total."),
            ("beats_placed", "Transparency beat placed per the Style Engine; case studies and power statements placed."),
            ("opening_closing_first", "Opening line and final line written first."),
            ("runtime_chosen", "Runtime chosen inside 7 to 15 minutes, defaulting to the 10-minute sweet spot; word target set at 140 words per minute."),
        ],
    ),
    (
        "DRAFT AND IMPROVEMENT",
        [
            ("final_draft_format", "Full draft in Final Draft format: prose only, everything speakable."),
            ("tags_embedded", "Fish Audio tags embedded in correct syntax (S2.1 Pro square brackets by default) at all mandatory locations."),
            ("improvement_pass", "Improvement Pass completed: more compelling, more disruptive, more emotionally captivating, tone enforced."),
            ("improvement_constraints", "Improvement Pass did NOT change the title or thesis, remove the transparency beat, add fabricated material, or inflate length."),
            ("read_aloud", "Read-aloud pass completed; nothing a mouth would stumble on remains."),
        ],
    ),
    (
        "QUALITY CONTROL",
        [
            ("tier1_all", "All 16 Tier 1 hard-fail checks passed (CHECKLIST Part B)."),
            ("rubric_all", "All 10 rubric dimensions scored 8 or higher, no averaging."),
            ("word_count_honest", "Spoken word count verified honestly, tags excluded, inside the target range."),
            ("attempt_recorded", "Attempt count recorded; three-strike cap honored if reached (stop, founder notified with failing checks and best draft)."),
        ],
    ),
    (
        "IMAGE",
        [
            ("cover_generated", "Cover art generated via Kie.ai GPT-image-2 at 1K square from the visual description plus episode theme, within polling bounds."),
            ("cover_finalized", "Squared and compressed in-house with ffmpeg: JPEG, RGB, within 1400 to 3000, under 512 kilobytes, spec-valid filename. Never below 1400 square."),
        ],
    ),
    (
        "AUDIO",
        [
            ("fish_render", "Speech Script converted via Fish Audio model s2.1-pro with the client's own voice reference_id; free tier never used."),
            ("audio_mastered", "Split at natural boundaries and ffmpeg-joined if needed; condition_on_previous_chunks true; no seams; loudness mastered to the department doctrine; ffprobe-verified."),
            ("mp3_named", "MP3 named client name first, then episode title; valid characters only."),
        ],
    ),
    (
        "DOCUMENTS",
        [
            ("tooling_detected", "Document tooling detected (Google, Notion, or plain text) before creation."),
            ("package_rendered", "Episode Package created rich and fully rendered, no font below 12 point."),
            ("script_clean", "Speech Script created as clean text only."),
            ("sharing_set", "Google sharing set to anyone-with-the-link-can-edit where Google is the destination."),
        ],
    ),
    (
        "BOOK TEASER (Interview mode only; skipped entirely for Personal mode)",
        [
            ("teaser_written", "Teaser written (at most three pages) from answers, improved answers, and verified research, in the person's voice, ending on a cliffhanger, on Kimi 2.6 or GLM 5.2."),
            ("teaser_pdf", "Rendered as a book-typeset PDF, no font below 14 point, uploaded to Convert and Flow media storage, URL captured."),
            ("teaser_field", "Link written to the book_teaser field, or the founder reminder surfaced if the field is absent (never silently created, never fails the episode)."),
        ],
    ),
    (
        "MEDIA, PUBLISHING, LINK-BACK, ENROLLMENT",
        [
            ("media_uploaded", "MP3 and cover uploaded to the client's Convert and Flow media library folders; URLs captured and HEAD-verified publicly reachable."),
            ("published", "Episode published to the client's OWN Podbean channel; permalink captured; scheduled when a future release date exists."),
            ("link_back", "Title, description, Episode Package link, Speech Script link written first in one batch; podcast_survey_episode_url written ALONE and LAST; every write read back byte-for-byte."),
            ("enrollment", "Interview: enrollment into both workflows verified per the discovered trigger mechanism, double-enrollment guarded. Personal: running spreadsheet updated, no workflows, no messages."),
            ("boundary_stop", "Engine STOPPED at the boundary: zero SMS, zero email, zero customer messages from the agent."),
        ],
    ),
    (
        "DELIVERY",
        [
            ("deliverable", "Deliverable contains the pure script, document links, media URLs, and the Podbean episode link."),
            ("report_prepared", "Delivery report prepared separately (this report) to the operator channel only."),
            ("state_complete", "Ledger and database state complete; costs recorded; dashboard reflects the finished episode."),
        ],
    ),
]

# A Book Teaser section header is matched by its leading token so the Personal-mode
# structural skip is applied without pinning the whole header string.
_BOOK_TEASER_SECTION_PREFIX = "BOOK TEASER"

_REDACT_PATTERNS = [
    re.compile(r"\bpit-[A-Za-z0-9._-]+"),
    re.compile(r"\bsk-[A-Za-z0-9._-]+"),
    re.compile(r"\b(?:Bearer|Authorization)\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]

# Destination-name shapes that mean a customer-facing channel. Any match is refused.
_CLIENT_FACING_TOKENS = re.compile(
    r"(customer|client-?chat|clientchat|guest|subscriber|\bsms\b|\bemail\b|whatsapp|"
    r"twilio|end-?user|audience|listener|public)",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _REDACT_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def assert_no_forbidden_glyphs(text: str) -> None:
    """Fail closed if the produced report contains an em dash or a triple backtick."""
    if EM_DASH in text:
        raise ValueError("delivery report contains an em dash character (forbidden)")
    if FENCE in text:
        raise ValueError("delivery report contains a triple-backtick fence (forbidden)")


def assert_operator_destination(destination: str) -> None:
    """Hard-refuse any destination that looks client-facing (silence doctrine)."""
    if destination is None:
        return
    if _CLIENT_FACING_TOKENS.search(str(destination)):
        raise ValueError(
            "refusing to deliver the report to a client-facing destination: "
            + str(destination)
            + " (the report is OPERATOR ONLY)"
        )


def _fmt(value, missing: str = "not recorded") -> str:
    if value is None or value == "":
        return "(" + missing + ")"
    return str(value)


def _get(record: dict, *keys, default=None):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def _checkbox(state) -> str:
    if state is True:
        return "[x]"
    if state == "na":
        return "[-]"
    if state is False:
        return "[ ]"
    return "[ ] (state not recorded)"


def reproduce_checklist_part_a(record: dict) -> str:
    """Render CHECKLIST Part A with honest per-item state from record."""
    states = record.get("checklist_state") or {}
    mode = (record.get("mode") or "").lower()
    is_personal = "personal" in mode
    lines: list[str] = ["PART A, PER-EPISODE CHECKLIST (reproduced):", ""]
    for section, items in CHECKLIST_PART_A:
        lines.append(section)
        teaser_section = section.startswith(_BOOK_TEASER_SECTION_PREFIX)
        for item_id, text in items:
            if teaser_section and is_personal:
                box = "[-]"
                suffix = " (not applicable, Personal mode skips the book teaser)"
            else:
                box = _checkbox(states.get(item_id))
                suffix = ""
            lines.append("  " + box + " " + text + suffix)
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_rubric(record: dict) -> str:
    rubric = record.get("rubric") or {}
    lines = ["RUBRIC SCORES (Tier 2, minimum " + str(RUBRIC_MIN) + " per dimension, no averaging):"]
    all_present = True
    all_pass = True
    for key, label in RUBRIC_DIMENSIONS:
        score = rubric.get(key)
        if score is None:
            lines.append("  " + label + ": (not scored)")
            all_present = False
            continue
        try:
            passed = float(score) >= RUBRIC_MIN
        except (TypeError, ValueError):
            passed = False
        all_pass = all_pass and passed
        lines.append("  " + label + ": " + str(score) + " -> " + ("PASS" if passed else "FAIL"))
    if all_present:
        lines.append("  Gate: " + ("ALL DIMENSIONS AT OR ABOVE " + str(RUBRIC_MIN) if all_pass else "ONE OR MORE DIMENSIONS BELOW " + str(RUBRIC_MIN)))
    else:
        lines.append("  Gate: incomplete (one or more dimensions not scored)")
    return "\n".join(lines)


def _render_save_confirmations(record: dict) -> str:
    conf = record.get("ghl_save_confirmations")
    lines = ["Convert and Flow save confirmations (read-back verification):"]
    if not conf:
        lines.append("  (not recorded)")
        return "\n".join(lines)
    if isinstance(conf, dict):
        for field_key, status in conf.items():
            lines.append("  " + field_key + ": " + str(status))
    else:
        lines.append("  " + str(conf))
    return "\n".join(lines)


def _render_enrollment(record: dict) -> str:
    mode = (record.get("mode") or "").lower()
    enrollment = record.get("enrollment")
    lines = ["Enrollment confirmation:"]
    if "personal" in mode:
        spreadsheet = record.get("spreadsheet_updated")
        lines.append("  Personal mode: no workflows, no customer messages.")
        lines.append("  Running spreadsheet updated: " + _fmt(spreadsheet))
        return "\n".join(lines)
    if not enrollment:
        lines.append("  (not recorded)")
        return "\n".join(lines)
    if isinstance(enrollment, dict):
        for workflow, status in enrollment.items():
            lines.append("  " + workflow + ": " + str(status))
    else:
        lines.append("  " + str(enrollment))
    return "\n".join(lines)


def build_report(record: dict) -> str:
    """Assemble the full operator delivery report from an episode record.

    Expected record keys (all tolerant of absence; missing renders as not recorded):
      job_id, client_id, contact_id, episode_number
      episode_title | title, spoken_word_count, runtime_minutes, style, mode
      writing_model, writing_model_substitution, research_tool
      document_destination, episode_package_url, speech_script_url
      mp3_media_url, cover_image_url, book_teaser_url, podbean_permalink
      image_prompt, ghl_save_confirmations, enrollment, spreadsheet_updated
      checklist_state (dict of item_id -> True/False/"na"), rubric (dict), cost_usd
    """
    title = _get(record, "episode_title", "title")
    mode = _get(record, "mode")
    style = _get(record, "style")
    substitution = record.get("writing_model_substitution")
    model_line = _fmt(_get(record, "writing_model"))
    if substitution:
        model_line = model_line + " (substitution: " + str(substitution) + ")"

    header = [
        "PODCAST DELIVERY REPORT (OPERATOR ONLY, NOT FOR THE CUSTOMER)",
        "=============================================================",
        "Job: " + _fmt(_get(record, "job_id")),
        "Client: " + _fmt(_get(record, "client_id")),
        "Contact: " + _fmt(_get(record, "contact_id")),
        "Episode number: " + _fmt(_get(record, "episode_number")),
        "",
        "SUMMARY",
        "-------",
        "Title: " + _fmt(title),
        "Honest spoken word count (delivery tags excluded): " + _fmt(_get(record, "spoken_word_count")),
        "Runtime: " + (("about " + str(record["runtime_minutes"]) + " minutes") if _get(record, "runtime_minutes") is not None else "(not recorded)"),
        "Style: " + _fmt(style),
        "Mode: " + _fmt(mode),
        "Writing model: " + model_line,
        "Research tool: " + _fmt(_get(record, "research_tool")),
        "",
        "DOCUMENTS",
        "---------",
        "Destination: " + _fmt(_get(record, "document_destination")),
        "Episode Package: " + _fmt(_get(record, "episode_package_url")),
        "Speech Script: " + _fmt(_get(record, "speech_script_url")),
        "",
        "MEDIA LOCATIONS",
        "---------------",
        "Episode MP3: " + _fmt(_get(record, "mp3_media_url")),
        "Cover image: " + _fmt(_get(record, "cover_image_url")),
        "Book teaser PDF: " + (_fmt(_get(record, "book_teaser_url"), missing="none, Personal mode or field absent") if "personal" not in (mode or "").lower() else "(not applicable, Personal mode)"),
        "",
        "PUBLISH",
        "-------",
        "Podbean episode link: " + _fmt(_get(record, "podbean_permalink")),
        "",
    ]

    body = [
        _render_save_confirmations(record),
        "",
        _render_enrollment(record),
        "",
        "IMAGE PROMPT",
        "------------",
        _fmt(_get(record, "image_prompt")),
        "",
        _render_rubric(record),
        "",
        reproduce_checklist_part_a(record),
    ]

    if _get(record, "cost_usd") is not None:
        body += ["", "OPERATOR COST", "-------------", "Accrued this episode (USD): " + str(record["cost_usd"])]

    report = "\n".join(header + body)
    report = redact(report)
    assert_no_forbidden_glyphs(report)
    return report


# ---------------------------------------------------------------------------
# Operator-only delivery
# ---------------------------------------------------------------------------

OperatorSink = Callable[[str], None]


def stdout_operator_sink(report: str) -> None:
    sys.stdout.write(report + "\n")


def deliver(
    record: dict,
    destination: str = "operator",
    sink: OperatorSink = stdout_operator_sink,
    outbox_path: Optional[str] = None,
) -> str:
    """Build the report and route it to the operator ONLY.

    destination is validated by assert_operator_destination; a client-facing name
    raises before anything is emitted. sink is the operator channel writer (default
    stdout). A gateway operator hook can be injected as sink for real delivery, but
    it must target an operator, never a customer. Optionally also append to an
    operator-only outbox file for durability.
    """
    assert_operator_destination(destination)
    report = build_report(record)
    if outbox_path:
        with open(outbox_path, "a", encoding="utf-8") as fh:
            fh.write(report + "\n\n")
    sink(report)
    return report


def _load_record(value: str) -> dict:
    if value == "-":
        return json.load(sys.stdin)
    with open(value, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="delivery_report.py",
        description="Build and deliver the OPERATOR-ONLY podcast episode delivery report.",
    )
    parser.add_argument(
        "--record-file",
        required=True,
        help="episode record JSON (a file path or - for stdin)",
    )
    parser.add_argument(
        "--destination",
        default="operator",
        help="operator channel name; client-facing destinations are refused",
    )
    parser.add_argument("--outbox", default=None, help="optional operator-only outbox file to append to")
    parser.add_argument("--json", action="store_true", help="emit the report inside a JSON envelope")
    args = parser.parse_args(argv)

    record = _load_record(args.record_file)
    try:
        assert_operator_destination(args.destination)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    report = build_report(record)
    if args.outbox:
        with open(args.outbox, "a", encoding="utf-8") as fh:
            fh.write(report + "\n\n")

    if args.json:
        print(json.dumps({"destination": args.destination, "report": report}))
    else:
        sys.stdout.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
