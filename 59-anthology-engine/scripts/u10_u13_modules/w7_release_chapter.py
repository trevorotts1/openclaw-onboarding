#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: u10_u13_modules/w7_release_chapter.py
# UNIT W7 - THE ANTHOLOGY-RELEASE-CHAPTER COPY GENERATOR (EMAIL + SMS).
# A PURE DATA GENERATOR: this module renders the ONE client-facing email and
# the ONE client-facing SMS that a producer approve of a delivered chapter
# puts on the release bus (the gate-engine release slug
# `anthology-release-chapter`, fired by the s5_producer board-door gate in
# scripts/gate_engine.py GATE_BY_CURSOR on a committed producer approve).
# It is the Chapter row of the eight-row tag->notification family described
# as a CONTRACT DESCRIPTION (never a banned workflow JSON export) in
# config/anthology-snapshot-contract.json -> workflows.release_notifications
# + workflows.copy_law: trigger tag -> producer-branded EMAIL (per-stage
# PDF-view + Doc-edit links) -> link-only SMS.
# -----------------------------------------------------------------------------
# WHAT THIS MODULE IS:
#   * A DATA GENERATOR, NOT A SENDER. It emits the rendered copy: the email
#     subject, the email body, the SMS body, and the exact Convert and Flow
#     contact custom-field merge tags those bodies must carry, as one JSON
#     document. It performs NO delivery, NO network I/O, and holds NO
#     credential: there is no token to resolve, to read, or to print.
#   * OFFLINE BY CONSTRUCTION. Import and every render path touch nothing
#     but the module's own constant tables. No env vars, no files, no
#     sockets. self_test() is a pure function self-check over the same
#     constants. There is no --execute flag because there is nothing to
#     execute: rendering copy is not a write.
#   * THE COPY LAW, PINNED (config/anthology-snapshot-contract.json
#     workflows.copy_law, Trevor's verbatim law for every client-facing word):
#       - "editors" never "AI" (word-boundary "AI" and "ghostwriter" shapes
#         are banned from every client-facing string in this module),
#       - zero em dashes (U+2014) anywhere in this file, prose included,
#       - sign-off "The Editors" or the producer merge
#         {{ custom_values.producer }}; the family default is the producer
#         merge (email_from_name_merge), "The Editors" is the standing
#         chapter-family alternate,
#       - the standing instruction text is byte-exact from the contract
#         (workflows.copy_law.standing_instruction),
#       - the SMS is a link-only short message (one warm sentence plus ONE
#         link), per copy_law.sms_shape.
#   * THE STAGE-FORM LINK (contract forms + intake_router.py classify_stage:
#     every contract-bound per-stage form carries the universal hidden trio
#     contact_id / anthology_id / stage and is accepted by its stage token).
#     The minted intake-link shape lives in anthology_book.py
#     (build_intake_link: <forms_base>/widget/form/<form_id>
#     ?anthology_id=<minted>); the stage-prefilled release link is the SAME
#     shape plus the stage query key:
#       <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=s5_chapter
#     The form_id is a LOCATION identifier (the chapter-approve-or-rewrite
#     contract-bound form, reported BY MASKED MARKER on every surface), and
#     the anthology_id is a MINTED identifier. Neither is a credential.
#   * NEVER A TOKEN. Nothing in this module prints, reads, or references a
#     token value. The engine's credential doctrine (caf_credential_gate.py /
#     preflight.sh) is untouched: credential resolution stays with the gate;
#     the GHL workflow templates this module feeds put the merge tag in the
#     body and the live value lives only in the client's own Convert and Flow
#     account.
#   * THE ENGINE WRITES NO WORKFLOW JSON EXPORT (scan-no-json-exports.sh
#     bans them). This module emits TEMPLATE COPY ONLY: strings and merge
#     tags, ready to be dropped into the email and SMS actions of the
#     snapshot's tag->notification workflow builder (the Skill 44 caf
#     Firebase build rail), never an n8n/GHL node graph.
#
# CONTRACT ROW (workflows.release_notifications, the Chapter row):
#   {
#     "name": "Anthology Release: Chapter",
#     "trigger_tag": "anthology-release-chapter",
#     "slug_status": "WIRED-AHEAD",
#     "actions": ["send-email", "send-sms"],
#     "email_link_fields": ["{{contact.anthology_chapter_pdf_url}}",
#                           "{{contact.anthology_chapter_doc_url}}"],
#     "sms_link_field": "{{contact.anthology_chapter_doc_url}}",
#     "note": "carries the two-editors'-rewrites-maximum reminder"
#   }
# The producer chapter release gate itself is LIVE (CHANGELOG: the
# s5_chapter -> s5_producer GATE_BY_CURSOR entry + GATE_RELEASE_SLUG fire
# anthology-release-chapter on a committed board-door producer approve).
#
# EXIT CODES (house convention):
#   0  rendered (render subcommand) or self-test passed (self-test subcommand)
#   2  validation refusal: unknown subcommand, malformed input values
#      (unresolved slots, forbidden characters, an empty link), or an
#      enforced self-test violation (a banned word / em dash / tag shape
#      inside this module's own constants)
#   1  unexpected error
#
# RENDER SUBCOMMAND:
#   python3 w7_release_chapter.py render \
#       --forms-base https://link.msgsndr.com \
#       --form-id riNlAkYbcW3g92VRLqq0 \
#       --anthology-id anth-2026-007
#   The form id and anthology id never ride the rendered copy verbatim; they
#   are masked on the human output and the rendered JSON carries only the
#   SHAPE (the form-id placeholder + the minted-id placeholder), so a render
#   log can never leak a location or anthology identifier. The RENDERED
#   string is safe to hand to the workflow builder: it contains the merge
#   tags only. When the builder needs a concrete preview link it substitutes
#   the placeholders itself; this module never prints them.
# =============================================================================
"""Unit W7: the anthology-release-chapter EMAIL + SMS copy generator (offline data)."""

import argparse
import re
import sys

# ---------------------------------------------------------------------------
# PINNED CONTRACT CONSTANTS (the sources of truth are named on every one).
# ---------------------------------------------------------------------------

# The release slug fired by gate_engine.py GATE_RELEASE_SLUG for the
# s5_producer gate (GATE_BY_CURSOR s5_chapter), and the matching contract row
# in config/anthology-snapshot-contract.json workflows.release_notifications.
RELEASE_SLUG = "anthology-release-chapter"
RELEASE_NAME = "Anthology Release: Chapter"

# The stage token of the chapter-approve-or-rewrite contract-bound form
# (config/anthology-snapshot-contract.json forms.contract_bound_per_anthology
# s5 row + intake_router.py classify_stage). The chapter release fires while
# the participant sits at the s5_chapter cursor (chapter in producer review),
# so the release form link carries stage=s5_chapter. The stage query key is
# the SAME key the universal hidden trio carries: contact_id / anthology_id /
# stage.
STAGE = "s5_chapter"
STAGE_QUERY_KEY = "stage"

# The universal hidden-trio law, pinned by the forms contract:
# ("contact_id", "anthology_id", "stage"). The stage form link must carry
# BOTH the minted anthology_id query key (exactly "anthology_id", never
# "anthology_active_id", per anthology_book.py + the contract note) and the
# stage query key.
ANTHOLOGY_ID_QUERY_KEY = "anthology_id"

# Copy law (workflows.copy_law): the standing instruction is byte-exact.
STANDING_INSTRUCTION = (
    "The PDF is yours to view. The Google Doc is the one you edit, "
    "and it is the version we use."
)

# The two-editors'-rewrites-maximum reminder (the Chapter contract row note
# "carries the two-editors'-rewrites-maximum reminder"; the rewrite row
# shows rewrites-used count {{contact.anthology_rewrite_count}} of 2).
# "editors" is the sanctioned word; the phrase "written by editors" never
# appears (the copy law bans that shape outright).
TWO_EDITORS_REMINDER = (
    "Two editors' rewrites are included in your package. If you would like "
    "to go further, you can ask for one more pass."
)

# The deliverable label for this stage (S5 chapter, one per participant).
DELIVERABLE_LABEL = "chapter"

# The sanctioned sign-offs (workflows.copy_law: producer_name_merge and
# email_from_name_merge are {{ custom_values.producer }}; "The Editors" is
# the standing chapter-family alternate, named in Trevor's copy law).
SIGN_OFF_EDITORS = "The Editors"
SIGN_OFF_PRODUCER_MERGE = "{{ custom_values.producer }}"

# ---------------------------------------------------------------------------
# CLIENT-CLEAN SERIALIZER (SPEC 11.5; mirrored from gate_engine Tier 1 checks
# and nudge_send.py): every rendered message must fill every slot (an
# unresolved slot is fail-closed refused), carry zero em dash characters and
# zero code fences, leak no internal tool / model / provider identifier, and
# say Convert and Flow if it names the platform at all. Zero Anthropic
# identifiers ship in this module.
# ---------------------------------------------------------------------------
# The U+2014 em dash is NEVER written literally in this file (zero em dashes
# in the file itself); the validator below builds the character at runtime so
# a grep for the dash can prove the file clean, and every rendered message
# must still pass the same validator.
EM_DASH = chr(0x2014)
# The deny definition: the word-actor and provider-identifier tokens this
# module's copy law refuses, named under the DENY_ symbol so the engine's
# static guards (guard-no-anthropic-runtime.py enforcement-context
# allowlist, guard-prompt-pins.py) recognize the definition as the deny
# machinery it is. The provider identifiers are the runtime-values law the
# model router enforces at call time; generated copy never carries any of
# them (AF-AE-ANTHROPIC / AF-AE-COPY-LAW).
DENY_WORDS = ("ai", "ghostwriter", "ghost-writer", "llm", "gpt", "claude",
              "anthropic", "openai", "gemini")
SLOT_PATTERN = re.compile(r"\{\{[^{}]+\}\}")
SUBJECT_PREFIX = "[Chapter ready]"
SMS_SUBJECT_PREFIX = "[Anthology]"
NOT_SUBJECT_SUFFIX = ":0:"

# The Chapter workflow's per-stage contact custom-field merge tags, pinned
# byte-exact from config/field-map.json deliverable_fields.chapter + the
# contract row email_link_fields / sms_link_field. These tags are the ONLY
# link slots the Chapter email and SMS may carry.
CHAPTER_PDF_TAG = "{{contact.anthology_chapter_pdf_url}}"
CHAPTER_DOC_TAG = "{{contact.anthology_chapter_doc_url}}"
REWRITE_COUNT_TAG = "{{contact.anthology_rewrite_count}}"


def render_email(*, first_name, anthology_name, producer_display_name,
                 chapter_pdf_url, chapter_doc_url, rewrite_count, sign_off):
    """Render the Chapter release EMAIL (subject + body) from resolved slots.

    Pure string work, no I/O. Returns {"subject": str, "body": str}. The
    rewrite-count slot is filled from rewrite_count (an integer) only when
    the count merge is embedded in the copy: the count rides the "of 2"
    phrase, never a bare number.
    """
    _validate_common(producer_display_name=producer_display_name,
                     sign_off=sign_off)
    _require_nonempty_url(first_name, "first_name")
    _require_slot_free(first_name, "first_name")
    _require_nonempty_url(anthology_name, "anthology_name")
    _require_slot_free(anthology_name, "anthology_name")
    for value, name in ((chapter_pdf_url, "chapter_pdf_url"),
                        (chapter_doc_url, "chapter_doc_url")):
        _require_nonempty_url(value, name)
        if value not in (CHAPTER_PDF_TAG, CHAPTER_DOC_TAG):
            # The two sanctioned link tags are merge slots BY DESIGN (they
            # resolve at delivery time from the contact custom fields); any
            # OTHER slot is unresolved and refused.
            _require_slot_free(value, name)
    _require_int(rewrite_count, "rewrite_count")

    subject = "%s %s" % (SUBJECT_PREFIX, anthology_name)
    body_lines = [
        "Hi %s," % first_name,
        "",
        "Good news. Your %s is finished and saved for you." % DELIVERABLE_LABEL,
        "",
        "You can view the PDF here:",
        "",
        chapter_pdf_url,
        "",
        "The Google Doc is the one you edit:",
        "",
        chapter_doc_url,
        "",
        STANDING_INSTRUCTION,
        "",
        "Your package includes up to two editors' rewrites "
        "(%d used of 2)." % rewrite_count,
        "",
        TWO_EDITORS_REMINDER,
        "",
        "Thank you for contributing to %s." % anthology_name,
        "",
        "Warmly,",
        sign_off,
    ]
    return {"subject": subject, "body": "\n".join(body_lines)}


def render_sms(*, first_name, chapter_doc_url):
    """Render the Chapter release SMS: one warm sentence plus ONE link
    (workflows.copy_law.sms_shape: link-only short message)."""
    _require_nonempty_url(chapter_doc_url, "chapter_doc_url")
    if chapter_doc_url != CHAPTER_DOC_TAG:
        # The doc tag is a merge slot BY DESIGN (it resolves at delivery time
        # from the contact custom field); any OTHER slot is unresolved and
        # refused.
        _require_slot_free(chapter_doc_url, "chapter_doc_url")
    return "%s Your %s is ready for you here: %s" % (
        SMS_SUBJECT_PREFIX, DELIVERABLE_LABEL, chapter_doc_url)


def render_all(*, first_name, anthology_name, producer_display_name,
               chapter_pdf_url, chapter_doc_url, rewrite_count, sign_off):
    """Render both client-facing surfaces for the Chapter release as one
    JSON-document-ready dict: the email (subject + body) and the SMS (body),
    plus the merge-tag surface (the email link slots and the SMS link slot
    this stage must carry)."""
    email = render_email(
        first_name=first_name,
        anthology_name=anthology_name,
        producer_display_name=producer_display_name,
        chapter_pdf_url=chapter_pdf_url,
        chapter_doc_url=chapter_doc_url,
        rewrite_count=rewrite_count,
        sign_off=sign_off)
    sms = render_sms(first_name=first_name,
                     chapter_doc_url=chapter_doc_url)
    return {
        "template": "w7-release-chapter",
        "trigger_tag": RELEASE_SLUG,
        "workflow": RELEASE_NAME,
        "stage": STAGE,
        "actions": ["send-email", "send-sms"],
        "email": email,
        "sms": {"body": sms},
        "merge_tags": {
            "email_links": [CHAPTER_PDF_TAG, CHAPTER_DOC_TAG],
            "sms_link": CHAPTER_DOC_TAG,
            "producer": producer_display_name,
            "rewrite_count": rewrite_count,
        },
        "sign_off": sign_off,
        "forms": {
            "stage": STAGE,
            "link_shape": (
                "<forms_base_url>/widget/form/<form_id>?%s=<minted>&%s=%s"
                % (ANTHOLOGY_ID_QUERY_KEY, STAGE_QUERY_KEY, STAGE)),
            "form_id": MASKED_FORM_ID_MARKER,
            "anthology_id": MASKED_ANTHOLOGY_ID_MARKER,
            "hidden_fields": ("contact_id", "anthology_id", "stage"),
        },
    }


def build_stage_form_link(forms_base, form_id, anthology_id, stage=STAGE):
    """Build the stage-prefilled Convert and Flow hosted-form link:
    <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>.
    The shape is anthology_book.py's minted intake link plus the stage query
    key; the stage must be a legal stage token (the hidden-field trio's
    stage). The form id and anthology id are location / minted identifiers,
    never credentials; they are masked on every operator surface by the
    caller, and this function never prints them."""
    base = (forms_base or "").strip().rstrip("/")
    _require_nonempty_url(base)
    _require_slot_free(base, "forms_base")
    if not form_id or not str(form_id).strip():
        raise ValueError("form_id is required to build the stage form link")
    if not anthology_id or not str(anthology_id).strip():
        raise ValueError("anthology_id is required to build the stage form link")
    if not _is_legal_stage_token(stage):
        raise ValueError("refusing stage token %r" % (stage,))
    return "%s/widget/form/%s?%s=%s&%s=%s" % (
        base, form_id, ANTHOLOGY_ID_QUERY_KEY, anthology_id,
        STAGE_QUERY_KEY, stage)


# Exact stage-token vocabulary (anthology_state.STAGE_CURSORS, the SAME
# vocabulary the W3 sibling pins). The default stage the Chapter release
# email's form link pre-fills is the cursor the participant sits at while the
# chapter is in producer review: s5_chapter (the chapter-approve-or-rewrite
# contract-bound form rides the s5_chapter cursor in review and the s5_gate
# cursor while the participant decides; intake_router.py classify_stage
# accepts a stage token only when it names a known cursor). Bare "s5" is
# NOT a stage token, so the documented stage-form link carries
# stage=s5_chapter.
STAGE_VOCABULARY = frozenset((
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
))


def _is_legal_stage_token(token):
    """A stage token is legal only when it names a known cursor of the
    ledger (anthology_state.STAGE_CURSORS, the SAME vocabulary the W3 sibling
    pins; intake_router.py classify_stage accepts a stage token only when it
    names a known cursor, so an out-of-vocabulary token is a ValueError,
    never a fabricated token)."""
    value = (token or "").strip()
    return value in STAGE_VOCABULARY


# ---------------------------------------------------------------------------
# MASKED MARKERS. The form id and the anthology id NEVER ride the rendered
# JSON verbatim: the rendered copy carries placeholders (the workflow
# builder substitutes them per install), and the human surfaces carry the
# masked marker. A render log can never leak a location or anthology id.
# ---------------------------------------------------------------------------
MASKED_FORM_ID_MARKER = "<form_id:masked>"
MASKED_ANTHOLOGY_ID_MARKER = "<anthology_id:masked>"


def mask_form_id(form_id):
    """Report a form id as a masked marker (never the value)."""
    return MASKED_FORM_ID_MARKER if form_id else MASKED_FORM_ID_MARKER


def mask_anthology_id(anthology_id):
    """Report a minted anthology id as a masked marker (never the value)."""
    return MASKED_ANTHOLOGY_ID_MARKER if anthology_id else MASKED_ANTHOLOGY_ID_MARKER


# ---------------------------------------------------------------------------
# VALIDATORS (fail closed; every check names the offending slot).
# ---------------------------------------------------------------------------
def _require_nonempty_url(value, name="link"):
    if not value or not str(value).strip():
        raise ValueError("%s must be a non-empty URL or merge tag" % name)


def _require_slot_free(value, name):
    if SLOT_PATTERN.search(str(value)):
        raise ValueError(
            "%s must not carry an unresolved merge slot (got %r)" % (name, value))


def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer, got %r" % (name, value))


def _validate_common(*, producer_display_name, sign_off):
    _require_nonempty_url(producer_display_name, "producer_display_name")
    if producer_display_name != SIGN_OFF_PRODUCER_MERGE:
        # The producer merge is a slot BY DESIGN (it resolves at send time
        # from the client's Convert and Flow custom value); any OTHER slot
        # is unresolved and refused.
        _require_slot_free(producer_display_name, "producer_display_name")
    _require_nonempty_url(sign_off, "sign_off")
    if sign_off != SIGN_OFF_PRODUCER_MERGE:
        # Only the sanctioned producer merge may carry a merge slot; every
        # other sign-off must be a plain name ("The Editors" or a resolved
        # display name).
        _require_slot_free(sign_off, "sign_off")
    for s in (producer_display_name, sign_off):
        _forbid_banned_words(s)


def _forbid_banned_words(text, where="copy"):
    lowered = str(text).lower()
    for word in DENY_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            raise ValueError(
                "banned word %r found in %s (editors never AI)" % (word, where))


def _forbid_em_dash(text, where="copy"):
    if EM_DASH in str(text):
        raise ValueError("an em dash (U+2014) found in %s; zero em dashes" % where)


# ---------------------------------------------------------------------------
# SELF-TEST (pure; the module's own constants are the enforcement surface).
# ---------------------------------------------------------------------------
def _self_test_body() -> None:
    # --- the release identity is pinned to the engine's release bus ---
    assert RELEASE_SLUG == "anthology-release-chapter", "release slug drifted"
    assert RELEASE_NAME == "Anthology Release: Chapter", "release name drifted"
    assert STAGE == "s5_chapter", "stage drifted from the s5 chapter cursor"
    assert (STAGE_QUERY_KEY, ANTHOLOGY_ID_QUERY_KEY) == ("stage", "anthology_id"), \
        "the stage-form query keys drifted from the hidden-trio law"

    # --- the copy law holds on every client-facing constant of this module
    #     (enforced, not described: an em dash or a banned word here is an
    #     enforced self-test violation, exit 2) ---
    for where, text in (("STANDING_INSTRUCTION", STANDING_INSTRUCTION),
                        ("TWO_EDITORS_REMINDER", TWO_EDITORS_REMINDER),
                        ("SIGN_OFF_EDITORS", SIGN_OFF_EDITORS),
                        ("SIGN_OFF_PRODUCER_MERGE", SIGN_OFF_PRODUCER_MERGE)):
        _forbid_em_dash(text, where)
        _forbid_banned_words(text, where)
    assert "AI" not in TWO_EDITORS_REMINDER and "AI" not in STANDING_INSTRUCTION, \
        "the word AI must never appear in client-facing copy"

    # --- the standing instruction is byte-exact from the contract ---
    assert STANDING_INSTRUCTION == (
        "The PDF is yours to view. The Google Doc is the one you edit, "
        "and it is the version we use."), "the standing instruction drifted"

    # --- the merge tags are pinned byte-exact from field-map.json
    #     deliverable_fields.chapter + the contract Chapter row ---
    assert CHAPTER_PDF_TAG == "{{contact.anthology_chapter_pdf_url}}", \
        "the chapter pdf tag drifted from deliverable_fields"
    assert CHAPTER_DOC_TAG == "{{contact.anthology_chapter_doc_url}}", \
        "the chapter doc tag drifted from deliverable_fields"
    assert REWRITE_COUNT_TAG == "{{contact.anthology_rewrite_count}}", \
        "the rewrite-count tag drifted from the rewrite row"
    assert not SLOT_PATTERN.search(STANDING_INSTRUCTION), \
        "the standing instruction must never carry an unresolved slot"

    # --- the stage form link shape is anthology_book.py's minted shape plus
    #     the stage key; the stage hidden value rides the universal trio ---
    sample = build_stage_form_link(
        "https://link.msgsndr.com", "form_marker", "anth-marker", stage=STAGE)
    assert sample == ("https://link.msgsndr.com/widget/form/form_marker"
                      "?anthology_id=anth-marker&stage=s5_chapter"), \
        "the stage form link shape drifted: %r" % sample

    # --- an illegal stage token refuses (never a silent link) ---
    for bad in ("", "S5", "s5_extra_garbage", "s5 gate", "chapter"):
        try:
            build_stage_form_link("https://link.msgsndr.com", "f", "a", stage=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("stage token %r must refuse" % bad)

    # --- the rendered email: every slot filled, no em dash, no fence, no
    #     banned word, the sign-off contract honored, the rewrite-maximum
    #     reminder present (the Chapter row note) ---
    email = render_email(
        first_name="Maya",
        anthology_name="Stories We Carry",
        producer_display_name="Marlowe",
        chapter_pdf_url=CHAPTER_PDF_TAG,
        chapter_doc_url=CHAPTER_DOC_TAG,
        rewrite_count=0,
        sign_off=SIGN_OFF_PRODUCER_MERGE)
    assert email["subject"].startswith(SUBJECT_PREFIX), \
        "the subject must lead with the sanctioned prefix"
    assert "Stories We Carry" in email["subject"], \
        "the subject must carry the anthology name (resolved)"
    assert EMAIL_MUST_INCLUDE in email["body"], "the email must name the PDF"
    assert EMAIL_MUST_INCLUDE_2 in email["body"], "the email must name the Doc"
    assert STANDING_INSTRUCTION in email["body"], \
        "the standing instruction must ride the email byte-exact"
    assert "0 used of 2" in email["body"], \
        "the rewrite count must fill the of-2 phrase"
    assert TWO_EDITORS_REMINDER in email["body"], \
        "the two-editors'-rewrites-maximum reminder must ride the email"
    assert "editors" in email["body"], "editors must be the sanctioned word"
    assert "AI" not in email["body"] and "AI" not in email["subject"], \
        "the email must never say AI"
    assert "```" not in email["body"], "the email must never carry a code fence"
    assert not SLOT_PATTERN.search(email["subject"]), \
        "the subject must carry no unresolved slot (the anthology name is resolved)"
    _forbid_em_dash(email["body"], "rendered email body")
    _forbid_banned_words(email["body"], "rendered email body")
    assert email["body"].endswith(SIGN_OFF_PRODUCER_MERGE), \
        "the email must sign off with the producer merge or The Editors"

    # --- the producer-merge sign-off is the family default; The Editors is
    #     the standing alternate (copy law) ---
    email2 = render_email(
        first_name="Maya",
        anthology_name="Stories We Carry",
        producer_display_name="Marlowe",
        chapter_pdf_url=CHAPTER_PDF_TAG,
        chapter_doc_url=CHAPTER_DOC_TAG,
        rewrite_count=2,
        sign_off=SIGN_OFF_EDITORS)
    assert email2["body"].endswith(SIGN_OFF_EDITORS), \
        "The Editors must be a legal sign-off"
    assert "2 used of 2" in email2["body"], \
        "the second rewrite must count 2 of 2"

    # --- the SMS is link-only: one warm sentence plus exactly ONE link ---
    sms = render_sms(first_name="Maya", chapter_doc_url=CHAPTER_DOC_TAG)
    assert sms.count(CHAPTER_DOC_TAG) == 1, \
        "the SMS must carry exactly ONE link"
    assert sms.count("\n") == 0, "the SMS must be a single short line"
    assert len(sms) <= SMS_MAX_LENGTH, \
        "the SMS must stay under the 160-character ceiling, got %d" % len(sms)
    _forbid_em_dash(sms, "rendered SMS")
    _forbid_banned_words(sms, "rendered SMS")

    # --- unresolved slots refuse (fail-closed serializer) ---
    for kwargs in (
            {"first_name": "{{first_name}}", "anthology_name": "A",
             "producer_display_name": "P", "chapter_pdf_url": CHAPTER_PDF_TAG,
             "chapter_doc_url": CHAPTER_DOC_TAG, "rewrite_count": 0,
             "sign_off": SIGN_OFF_PRODUCER_MERGE},
            {"first_name": "Maya", "anthology_name": "A",
             "producer_display_name": "{{custom_values.producer}}",
             "chapter_pdf_url": CHAPTER_PDF_TAG,
             "chapter_doc_url": CHAPTER_DOC_TAG, "rewrite_count": 0,
             "sign_off": SIGN_OFF_PRODUCER_MERGE},
            {"first_name": "Maya", "anthology_name": "{{anthology_name}}",
             "producer_display_name": "P", "chapter_pdf_url": CHAPTER_PDF_TAG,
             "chapter_doc_url": CHAPTER_DOC_TAG, "rewrite_count": 0,
             "sign_off": SIGN_OFF_PRODUCER_MERGE},
            {"first_name": "Maya", "anthology_name": "A",
             "producer_display_name": "P", "chapter_pdf_url": "{{x}}",
             "chapter_doc_url": CHAPTER_DOC_TAG, "rewrite_count": 0,
             "sign_off": SIGN_OFF_PRODUCER_MERGE},
            {"first_name": "Maya", "anthology_name": "A",
             "producer_display_name": "P", "chapter_pdf_url": CHAPTER_PDF_TAG,
             "chapter_doc_url": "{{x}}", "rewrite_count": 0,
             "sign_off": SIGN_OFF_PRODUCER_MERGE}):
        try:
            render_email(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("an unresolved slot must refuse, got %r" % kwargs)
    try:
        render_sms(first_name="Maya", chapter_doc_url="")
    except ValueError:
        pass
    else:
        raise AssertionError("an empty SMS link must refuse")

    # --- the merged render is one self-describing JSON-ready document and
    #     never prints a form id or an anthology id value ---
    merged = render_all(
        first_name="Maya",
        anthology_name="Stories We Carry",
        producer_display_name="Marlowe",
        chapter_pdf_url=CHAPTER_PDF_TAG,
        chapter_doc_url=CHAPTER_DOC_TAG,
        rewrite_count=1,
        sign_off=SIGN_OFF_PRODUCER_MERGE)
    assert merged["trigger_tag"] == RELEASE_SLUG
    assert merged["actions"] == ["send-email", "send-sms"]
    assert merged["merge_tags"]["email_links"] == [CHAPTER_PDF_TAG, CHAPTER_DOC_TAG]
    assert merged["merge_tags"]["sms_link"] == CHAPTER_DOC_TAG
    assert merged["forms"]["link_shape"].endswith("&stage=s5_chapter"), \
        "the documented link shape must end with the stage query"
    assert merged["forms"]["form_id"] == MASKED_FORM_ID_MARKER, \
        "a form id value must never ride the rendered document"
    assert merged["forms"]["anthology_id"] == MASKED_ANTHOLOGY_ID_MARKER, \
        "a minted anthology id value must never ride the rendered document"
    assert "producer" in merged["merge_tags"], \
        "the producer merge must ride the rendered document"


def self_test(out=None) -> int:
    """Run the module's pure self-test. Returns 0 on PASS, 2 on an enforced
    violation (a banned word / em dash / tag shape inside this module's own
    constants or its rendered copy)."""
    dev = out if out is not None else sys.stdout
    try:
        _self_test_body()
    except (AssertionError, ValueError) as exc:
        dev.write("[w7-release-chapter] self-test FAILED: %s\n" % exc)
        return 2
    dev.write("[w7-release-chapter] self-test PASS\n")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_render_args(argv):
    parser = argparse.ArgumentParser(
        prog="w7_release_chapter.py",
        description="Unit W7: render the client-facing EMAIL + SMS for the "
                    "anthology-release-chapter release tag (a pure offline "
                    "data generator; it performs no delivery, holds no "
                    "credential, and never prints a token).")
    parser.add_argument("--forms-base", default="",
                        help="the Convert and Flow hosted-form base URL "
                             "(default: the fleet default "
                             "https://link.msgsndr.com; never printed when "
                             "overridden)")
    parser.add_argument("--form-id", default="",
                        help="the contract-bound chapter-approve-or-rewrite "
                             "form id (a location identifier; masked on every "
                             "surface, never printed verbatim)")
    parser.add_argument("--anthology-id", default="",
                        help="the minted anthology id (masked on every "
                             "surface, never printed verbatim)")
    parser.add_argument("--anthology-name", default="your anthology",
                        help="the anthology's display name (slot-filled into "
                             "the email subject and body)")
    parser.add_argument("--first-name", default="there",
                        help="the participant's first name (the email and "
                             "SMS greeting; never printed by this module)")
    parser.add_argument("--producer", default="",
                        help="the producer display name; default is the "
                             "{{ custom_values.producer }} merge "
                             "(workflows.copy_law producer_name_merge)")
    parser.add_argument("--sign-off", default="",
                        choices=["", "producer", "editors"],
                        help="the sanctioned sign-off: producer (the "
                             "{{ custom_values.producer }} merge, default) "
                             "or editors (The Editors, the standing alternate)")
    parser.add_argument("--rewrite-count", type=int, default=0,
                        help="the participant's rewrite count used so far "
                             "(0, 1, or 2)")
    parser.add_argument("cmd", nargs="?", choices=["render", "self-test"],
                        default="render")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = _parse_render_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        # ---- render (offline; no credential is read or printed) ----
        forms_base = args.forms_base.strip() or "https://link.msgsndr.com"
        form_id = args.form_id.strip() or MASKED_FORM_ID_MARKER
        anthology_id = args.anthology_id.strip() or MASKED_ANTHOLOGY_ID_MARKER
        producer = args.producer.strip() or SIGN_OFF_PRODUCER_MERGE
        sign_off = {
            "": SIGN_OFF_PRODUCER_MERGE,
            "producer": SIGN_OFF_PRODUCER_MERGE,
            "editors": SIGN_OFF_EDITORS,
        }[args.sign_off]
        rewrite_count = args.rewrite_count if args.rewrite_count is not None else 0

        # Render a concrete preview link (placeholders) to prove the stage
        # link shape; the form id and anthology id stay masked markers.
        stage_link = build_stage_form_link(forms_base, "<form_id>",
                                           "<anthology_id>", stage=STAGE)
        merged = render_all(
            first_name=args.first_name,
            anthology_name=args.anthology_name,
            producer_display_name=producer,
            chapter_pdf_url=CHAPTER_PDF_TAG,
            chapter_doc_url=CHAPTER_DOC_TAG,
            rewrite_count=rewrite_count,
            sign_off=sign_off)
        merged["forms"]["link_shape"] = stage_link
        merged["forms"]["form_id"] = mask_form_id(args.form_id)
        merged["forms"]["anthology_id"] = mask_anthology_id(args.anthology_id)

        import json
        sys.stdout.write(json.dumps(merged, indent=2) + "\n")
        return 0

    except ValueError as exc:
        sys.stderr.write("[w7-release-chapter] REFUSED: %s\n" % exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[w7-release-chapter] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return 1


# Sanctioned in-body markers, kept below the constants they assert against.
EMAIL_MUST_INCLUDE = "You can view the PDF here:"
EMAIL_MUST_INCLUDE_2 = "The Google Doc is the one you edit:"
SMS_MAX_LENGTH = 160

if __name__ == "__main__":
    sys.exit(main())
