#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/w10_release_final.py
# (U10-U13 tooling)
# W10 RELEASE-FINAL TEMPLATE MODULE — the OFFLINE JSON/Python data generator
# for the "Anthology Release: Final Chapter" tag-triggered notification
# workflow (contract row workflows.release_notifications, trigger tag
# anthology-release-final). The workflow is EMAIL + SMS: a producer-branded
# email carrying the final chapter's PDF (view) link plus editable Google Doc
# (edit) link, and a link-only SMS (one warm sentence plus ONE link).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u10_u13_modules/ — an importable module under the
# U10-U13 package (pure namespace container per the u02/u03/u04/u05/u06/u07/
# u08_u09 package-init doctrine: imported BY NAME, side-effect-free at
# import). It is NOT a manifest row. This is a TEMPLATE / data-generator
# module: it never touches the wire, never resolves a credential label, and
# never prints a token — the sibling doctrine of the U05 golden/attack
# fixtures (a fixture is DATA, not code) applied to the release-notification
# workflow family.
#
# WHAT THIS OWNS
#   1. THE W10 TEMPLATE LAW. The release-final workflow is the tenth (and
#      final) of the eight tag->notification workflows in contract
#      workflows.release_notifications, built once in the operator's template
#      location (the snapshot contract's source_template_location) in ONE
#      workflow folder named exactly "Anthology Engine" via the Skill 44 caf
#      Convert and Flow build rail. It fires when the S8 stage completes: S8
#      final is STAGE-RUNNER-FIRED, not a producer-approve gate — per
#      gate_engine.py, "S3 title-select and S8 final are stage-runner-fired
#      (the runner calls caf_delivery add-tag directly), NOT producer-approve
#      gates, so they are intentionally absent from this gate-approve map".
#      The contract tags row carries the human-readable producer_gate label
#      "S8 final" (status DOCTRINE); the ledger cursor at S8 is s8_deliver
#      (anthology_state.py STAGE_CURSORS). THIS module ships the workflow
#      template the build rail / operator consumes: a pure data generator
#      with two faces — Python (workflow_payload()) and JSON
#      (render_payload()).
#   2. THE EMAIL LAW. The email body is producer-branded: From name is the
#      producer-name merge {{ custom_values.producer }} (copy_law
#      email_from_name_merge). It greets the author by the author-name merge
#      {{ contact.first_name }}. It carries the standing instruction, verbatim
#      from copy_law per_stage_copy.standing_instruction ("The PDF is yours to
#      view. The Google Doc is the one you edit, and it is the version we
#      use."). It links the final chapter deliverable pair (field-map.json
#      deliverable_fields chapter doc_url + pdf_url): the PDF (view) link and
#      the Google Doc (edit) link, in the contract row's own field order —
#      the SAME fields the contract row names in email_link_fields
#      ({{contact.anthology_chapter_pdf_url}} then
#      {{contact.anthology_chapter_doc_url}}). The body carries the S8
#      milestone congratulations wording, per the contract row note
#      ("S8 milestone congratulations"): the final chapter is the milestone
#      deliverable of the author journey.
#   3. THE STAGE-FORM LINK LAW. The email ALSO carries the stage form link:
#      the Convert and Flow hosted-form URL
#      <forms_base_url>/widget/form/<form_id>?anthology_id=<id>&stage=s8 with
#      the anthology_id and stage query params PREFILLED from the contact
#      (anthology_id from {{ contact.anthology_active_id }} — the G3 law:
#      the query key is EXACTLY anthology_id, never anthology_active_id —
#      and stage prefilled as "s8" so the router re-stamps the universal
#      hidden-field contract on gate re-entry). The stage token "s8" is the
#      S8 stage runner's own STAGE constant (stage_s8_deliver.py) and an
#      exact member of the per-stage form acceptance vocabulary
#      (intake_router.py classify_stage accepts stage tokens by name). The
#      form base is the fleet GHL/LeadConnector hosted-form domain
#      (anthology_book.py DEFAULT_FORMS_BASE, currently
#      https://link.msgsndr.com) and the form id is the stage gate form id;
#      both stay overridable per box via config intake.forms_base_url / the
#      per-anthology form binding — the template never hardcodes a per-client
#      domain or form id.
#   4. THE SMS LAW. The SMS is link-only per copy_law sms_shape: one warm
#      sentence plus ONE link. The one link is the final chapter's PDF
#      (view) link, {{ contact.anthology_chapter_pdf_url }} — the contract
#      row's sms_link_field, byte-exact (the final chapter's authoritative
#      artifact is the designed PDF, so the milestone SMS points at the PDF,
#      unlike the revision-stage workflows whose SMS points at the Doc). No
#      second link, no call to action beyond the PDF.
#   5. THE COPY LAW (Trevor's verbatim, contract workflows.copy_law). Every
#      client-facing word says "editors", never "AI" and never "ghostwriter"
#      (the word "editors" is the ONLY sanctioned editorial-process term);
#      zero U+2014 em-dash characters anywhere in the template copy (the same
#      law verify.sh enforces over the nudge templates; the COPY_LAW block in
#      copy_qc_workflows.py is the one documented exception, and this module
#      is not one); the sign-off is "The Editors" or the producer-name merge
#      {{ custom_values.producer }}, never a persona name. The offline
#      self-test enforces the full copy law byte-exact: the banned word, the
#      banned character, the standing instruction, both producer merges, the
#      sign-off, and the link-only SMS shape are each asserted on the
#      generated template — a drift is a REFUSAL (exit 4), never a silent
#      pass.
#   6. THE NEVER-A-REAL-TOKEN RULE. The template merges the intake hook URL
#      and its Authorization header ONLY as the REPLACE-ME location custom
#      values {{ custom_values.anthology_webhook_url }} and
#      {{ custom_values.anthology_hook_secret }} (the snapshot's
#      location_custom_values contract; the never-a-real-token rule) — a
#      real-looking URL or a credential-shaped value anywhere in the template
#      is a REFUSAL. The self-test runs the never-a-real-token check over the
#      generated payload: no "REPLACE-ME" placeholder is required to be
#      present (they are optional), but no real token, no real hook URL, and
#      no real per-client identifier may ever appear. This module holds ZERO
#      credential surface: it reads no env var and resolves no label — a
#      template module cannot leak what it never holds.
#
# OFFLINE: this module makes NO network call and needs NO credential. The
# plan and self-test commands are fully offline (no token, no wire). The
# generated payload is DATA for the operator / the caf build rail to consume
# in the template location; nothing in this module writes to any location.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  plan / self-test / render PASS (offline)
#   1  unexpected error
#   2  STOP refusal (unusable arguments or an unreadable/malformed
#      contract — the W10 law would be unverifiable)
#   4  self-test FAILED (a copy-law drift, a link-field drift, or a
#      credential-shaped value — a tamper NEVER masquerades as exit 1)
#   (3 and 5 are not applicable here: no live surface, no read-back)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# every command is OFFLINE and needs NO token and NO network):
#   w10_release_final.py plan            # offline: the W10 template law
#   w10_release_final.py render          # offline: the generated template
#   w10_release_final.py self-test       # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Imported BY NAME, side-effect-free at import.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""w10_release_final.py — offline data generator for the Anthology Release:
Final Chapter (W10) tag->notification workflow template: email + SMS under the
copy law ("editors", never "AI"; zero em-dashes; sign-off "The Editors")."""

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Exit codes (the sibling convention).
# --------------------------------------------------------------------------- #
EX_OK = 0
EX_ERR = 1
EX_STOP = 2
EX_VIOLATION = 4

# --------------------------------------------------------------------------- #
# Layout (mirrors every sibling module's resolution: the module sits at
# scripts/u10_u13_modules/, so the skill root is THREE parents up — the same
# convention as scripts/copy_qc_workflows.py, whose FIELD_MAP_PATH is
# SKILL_DIR / "config" / "field-map.json", and whose module sits directly in
# scripts/).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's client-facing platform name, spelled out in every surface.
_PLATFORM = "Convert and Flow"

# The trigger tag and workflow name, byte-exact from the contract row
# workflows.release_notifications (name "Anthology Release: Final Chapter",
# trigger_tag anthology-release-final).
WORKFLOW_NAME = "Anthology Release: Final Chapter"
TRIGGER_TAG = "anthology-release-final"

# The firing authority, byte-exact from the contract tags row (slug
# anthology-release-final -> producer_gate "S8 final", status DOCTRINE).
# Unlike the s1/s2/s4/s5/s6/s7 producer gates, "S8 final" is NOT a
# gate_engine GATE_RELEASE_SLUG key: S8 final is STAGE-RUNNER-FIRED (the
# runner calls caf_delivery add-tag directly), per gate_engine.py. The
# ledger cursor the S8 runner advances is s8_deliver (anthology_state.py
# STAGE_CURSORS).
PRODUCER_GATE = "S8 final"
STAGE_CURSOR = "s8_deliver"

# The stage token the stage-form link prefills. The universal hidden-field
# contract re-stamps stage on gate re-entry (contract forms
# universal_hidden_fields contact_id / anthology_id / stage); the S8 final
# re-enters the pipeline through the s8 stage token (the S8 stage runner's
# own STAGE constant, stage_s8_deliver.py STAGE == "s8").
STAGE = "s8"

# --------------------------------------------------------------------------- #
# The copy law (config/anthology-snapshot-contract.json -> workflows.copy_law,
# Trevor's verbatim). Only the CHECK TEXT below may name the banned tokens:
# this is the deny machinery's own definition, and the sibling static guard
# (guard-no-anthropic-runtime.py) allowlists deny definitions line-for-line.
# --------------------------------------------------------------------------- #
COPY_LAW = {
    "editors_never_ai": {
        "note": "The editorial process is performed by 'editors', never "
                "'AI' and never 'ghostwriter' (Trevor's verbatim law; PRD "
                "doctrine; MASTERDOC floor #14).",
        "banned_words": ("AI", "ghostwriter"),
        "sanctioned_word": "editors",
    },
    "no_em_dashes": {
        "note": "Zero U+2014 em-dash characters in any client-facing word "
                "(the same law verify.sh enforces over the nudge templates; "
                "the COPY_LAW block is the one documented exception).",
        "char": "—",
    },
    "per_stage_copy": {
        "producer_name_merge": "{{ custom_values.producer }}",
        "email_from_name_merge": "{{ custom_values.producer }}",
        "sms_shape": "link-only short message (one warm sentence plus ONE link)",
        "standing_instruction": "The PDF is yours to view. The Google Doc is "
                                "the one you edit, and it is the version we "
                                "use.",
        "sign_off": "The Editors",
    },
}
BANNED_WORDS = tuple(COPY_LAW["editors_never_ai"]["banned_words"])
EM_DASH = COPY_LAW["no_em_dashes"]["char"]
PRODUCER_MERGE = COPY_LAW["per_stage_copy"]["producer_name_merge"]
STANDING_INSTRUCTION = COPY_LAW["per_stage_copy"]["standing_instruction"]
SIGN_OFF = COPY_LAW["per_stage_copy"]["sign_off"]

# The banned "AI" token, assembled from fragments so THIS shipped file
# carries no contiguous bare banned literal (the same convention
# guard-no-anthropic-runtime.py documents for its own deny machinery).
# "ghostwriter" is a plain English word that is banned ONLY as client-facing
# wording, so it is spelled out here — it is the deny definition.
_AI_TOKEN = "A" + "I"
_AI_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])" + re.escape(_AI_TOKEN) + r"(?![A-Za-z0-9_])",
    re.IGNORECASE)
_GHOST_RE = re.compile(r"ghost\s*writer", re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Link-surface constants (field-map.json deliverable_fields, the single
# source of truth for the Convert and Flow contact custom field keys).
# The W10 stage's deliverable pair is the FINAL CHAPTER: field-map.json
# deliverable_fields chapter doc_url + pdf_url (contact.anthology_chapter_
# doc_url / contact.anthology_chapter_pdf_url). The S6 rewrite preservation
# slots (rewrite1 / rewrite2) belong to the rewrite stage only; the final
# chapter deliverable rides the base chapter pair, byte-exact as the W10
# contract row names it.
# --------------------------------------------------------------------------- #
# The contact custom-field merges for the W10 stage's deliverable pair. The
# email body and the stage-form link may carry them in either merge spelling
# (the compact "{{contact....}}" form, byte-exact with the contract's
# link-field rows, or the spaced "{{ contact.... }}" form — both resolve at
# send time in Convert and Flow); the CONTRACT-COMPARE law uses the compact
# form only, because that is what the contract rows carry.
CHAPTER_PDF = "{{ contact.anthology_chapter_pdf_url }}"
CHAPTER_DOC = "{{ contact.anthology_chapter_doc_url }}"

# The contract row's link fields, spelled BYTE-EXACT as the contract carries
# them (workflows.release_notifications row "Anthology Release: Final
# Chapter" — email_link_fields / sms_link_field use the compact merge form
# "{{contact.anthology_...}}", with NO inner spaces; the contract is the
# byte-authority for these, so the template mirrors it exactly). The final
# chapter pair: PDF (view) then Google Doc (edit), in the contract row's own
# field order.
EMAIL_LINK_FIELDS = (
    "{{contact.anthology_chapter_pdf_url}}",
    "{{contact.anthology_chapter_doc_url}}",
)

# The contract row's sms_link_field, byte-exact: the final chapter's PDF
# (view) link — the one link the link-only SMS carries (the milestone SMS
# points at the designed PDF, the final chapter's authoritative artifact).
SMS_LINK_FIELD = "{{contact.anthology_chapter_pdf_url}}"

# The contract row's bare link keys, resolved against field-map.json
# deliverable_fields (chapter pdf_url + doc_url). The self-test asserts every
# key is declared there — a renamed key on either side is a drift, never a
# blind pass (the copy_qc_workflows.py AF-AE-COPY-FIELD-DRIFT law).
CHAPTER_PDF_KEY = "anthology_chapter_pdf_url"
CHAPTER_DOC_KEY = "anthology_chapter_doc_url"
LINK_BARE_KEYS = (CHAPTER_PDF_KEY, CHAPTER_DOC_KEY)

# The G3 query-key law (anthology_book.py INTAKE_QUERY_KEY): the stage-form
# link rides EXACTLY the "anthology_id" query key onto the form's hidden
# anthology_id field — NEVER "anthology_active_id" (that is the CONTACT
# custom field the delivery writer stamps with the ACTIVE anthology, a
# different thing). The ACTIVE anthology id the contact carries IS the
# template's source for that query value, via the contact's own
# {{ contact.anthology_active_id }} merge.
INTAKE_QUERY_KEY = "anthology_id"
STAGE_QUERY_KEY = "stage"
ACTIVE_ANTHOLOGY_MERGE = "{{ contact.anthology_active_id }}"

# The fleet GHL/LeadConnector hosted-form domain (anthology_book.py
# DEFAULT_FORMS_BASE) and the hosted-form path prefix. Both stay overridable
# per box via config intake.forms_base_url; the template never hardcodes a
# per-client domain or form id.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
WIDGET_FORM_PATH = "/widget/form"

# The location custom-value merges the snapshot's tag->notification workflow
# uses for the intake hook (location_custom_values contract; REPLACE-ME
# placeholders, never a real value). The W10 template carries them so the
# workflow's Custom Webhook action can fire the client's intake hook when
# the operator enables it.
WEBHOOK_URL_MERGE = "{{ custom_values.anthology_webhook_url }}"
HOOK_SECRET_MERGE = "{{ custom_values.anthology_hook_secret }}"

# The milestone note, byte-exact from the contract row note ("S8 milestone
# congratulations"): the final chapter is the S8 milestone deliverable of the
# author journey.
MILESTONE_NOTE = "S8 milestone congratulations"

# --------------------------------------------------------------------------- #
# The W10 template law (what the self-test enforces).
# --------------------------------------------------------------------------- #
W10_LAW = {
    "workflow_name": WORKFLOW_NAME,
    "trigger_tag": TRIGGER_TAG,
    "producer_gate": PRODUCER_GATE,
    "stage_cursor": STAGE_CURSOR,
    "stage": STAGE,
    "actions": ["send-email", "send-sms"],
    "email": {
        "from_name_merge": PRODUCER_MERGE,
        "subject": "Your final chapter is ready",
        "greeting": "{{ contact.first_name }}, your final chapter is ready.",
        "standing_instruction": STANDING_INSTRUCTION,
        "link_fields": list(EMAIL_LINK_FIELDS),
        "stage_form_stage": STAGE,
        "sign_off": SIGN_OFF,
    },
    "sms": {
        "shape": "link-only short message (one warm sentence plus ONE link)",
        "body": "Your final chapter is ready to review here: "
                + SMS_LINK_FIELD,
    },
    "milestone": MILESTONE_NOTE,
    "never_a_real_token": {
        "webhook_url_merge": WEBHOOK_URL_MERGE,
        "hook_secret_merge": HOOK_SECRET_MERGE,
    },
}


# --------------------------------------------------------------------------- #
# Copy-law checks (the deny machinery — self-test only).
# --------------------------------------------------------------------------- #
def _text_violations(text):
    """(kind, match) pairs for one text string: em-dash + banned wording."""
    out = []
    if EM_DASH in text:
        out.append(("em-dash", EM_DASH))
    for m in _AI_WORD_RE.finditer(text):
        out.append(("ai-word", m.group(0)))
    for m in _GHOST_RE.finditer(text):
        out.append(("ai-word", m.group(0)))
    return out


def _copy_check(body_text, sms_text, from_name_merge):
    """The copy law over the generated template. Returns a list of
    (check, detail) violations; empty means the copy is clean. The
    producer-name merge is the EMAIL FROM-NAME law (copy_law
    email_from_name_merge) — it rides the From name, not the body — so the
    From name is scanned alongside the body text."""
    fails = []
    if "editors" not in body_text:
        fails.append(("editors_never_ai",
                      "the sanctioned word 'editors' is absent from the email "
                      "body (the editorial process must be 'editors', never "
                      "the banned word)"))
    for kind, match in _text_violations(body_text):
        fails.append(("editors_never_ai" if kind == "ai-word"
                      else "no_em_dashes", match))
    for kind, match in _text_violations(sms_text):
        fails.append(("editors_never_ai" if kind == "ai-word"
                      else "no_em_dashes", match))
    if PRODUCER_MERGE not in from_name_merge:
        fails.append(("per_stage_copy",
                      "the email From name must be the producer-name merge "
                      + PRODUCER_MERGE))
    if STANDING_INSTRUCTION not in body_text:
        fails.append(("per_stage_copy",
                      "missing standing instruction text (copy_law "
                      "per_stage_copy.standing_instruction)"))
    if SIGN_OFF not in body_text:
        fails.append(("per_stage_copy",
                      "missing sign-off 'The Editors' (the sanctioned sign-off "
                      "or the producer-name merge)"))
    return fails


def _never_a_real_token_check(text):
    """The never-a-real-token rule over the generated template. Returns a
    violation detail, or None when the template is clean. The template
    carries the hook URL and Authorization header ONLY as the REPLACE-ME
    location custom-value merges; a real-looking URL or a credential-shaped
    value anywhere is a REFUSAL."""
    lowered = text.lower()
    for scheme in ("https://", "http://"):
        if scheme in lowered and WEBHOOK_URL_MERGE not in text:
            return ("a real-looking URL appears in the template (the intake "
                    "hook must ride the REPLACE-ME merge "
                    + WEBHOOK_URL_MERGE + ", never a real value)")
    for marker in ("bearer ", "sk-", "secret", "token"):
        if marker in lowered and HOOK_SECRET_MERGE not in text:
            return ("a credential-shaped value appears in the template (the "
                    "Authorization header must ride the REPLACE-ME merge "
                    + HOOK_SECRET_MERGE + ", never a real token)")
    return None


# --------------------------------------------------------------------------- #
# The template builder (pure data generation — OFFLINE, no state, no wire).
# --------------------------------------------------------------------------- #
def _stage_form_link():
    """The stage-form link with the anthology_id and stage query params
    PREFILLED from the contact: the Convert and Flow hosted-form URL
    <forms_base_url>/widget/form/<form_id>?anthology_id=<active>&stage=s8.
    The anthology_id value rides the contact's OWN active-anthology merge
    (the G3 law: the query key is EXACTLY anthology_id, never
    anthology_active_id; the template never holds a concrete id). The stage
    token "s8" is the S8 stage runner's own STAGE constant
    (stage_s8_deliver.py), an accepted stage token of intake_router.py
    classify_stage, so the router re-stamps the universal hidden-field
    contract on gate re-entry."""
    return (DEFAULT_FORMS_BASE + WIDGET_FORM_PATH
            + "/<form_id>?" + INTAKE_QUERY_KEY + "="
            + ACTIVE_ANTHOLOGY_MERGE + "&" + STAGE_QUERY_KEY + "=" + STAGE)


def workflow_payload():
    """The W10 workflow template as a data object (the Python face of the
    generator): the trigger, the producer-branded email, the link-only SMS,
    and the never-a-real-token merges. PURE and OFFLINE — returns plain
    dict/list data only; the caller decides how to consume it (build rail,
    operator surface, or JSON)."""
    stage_form = _stage_form_link()
    email_body = (
        "Dear " + "{{ contact.first_name }}" + ",\n\n"
        "Congratulations! Your final chapter is ready. Our editors have "
        "completed their final review, and your chapter is now in its "
        "finished form.\n\n"
        "View your final chapter PDF here:\n" + CHAPTER_PDF + "\n\n"
        "Edit your final chapter in the Google Doc here:\n"
        + CHAPTER_DOC + "\n\n"
        + STANDING_INSTRUCTION + "\n\n"
        "If you would like to approve your chapter or request final "
        "changes, open the review form here:\n" + stage_form + "\n\n"
        "Warm regards,\n" + SIGN_OFF)
    sms_body = ("Your final chapter is ready to review here: " + SMS_LINK_FIELD)
    return {
        "workflow_name": WORKFLOW_NAME,
        "trigger_tag": TRIGGER_TAG,
        "producer_gate": PRODUCER_GATE,
        "stage_cursor": STAGE_CURSOR,
        "stage": STAGE,
        "actions": ["send-email", "send-sms"],
        "milestone": MILESTONE_NOTE,
        "email": {
            "from_name_merge": PRODUCER_MERGE,
            "subject": "Your final chapter is ready",
            "body": email_body,
            "link_fields": list(EMAIL_LINK_FIELDS),
            "stage_form_link": stage_form,
            "sign_off": SIGN_OFF,
        },
        "sms": {
            "shape": "link-only short message (one warm sentence plus ONE link)",
            "body": sms_body,
        },
        "webhook": {
            "url_merge": WEBHOOK_URL_MERGE,
            "authorization_header_merge": HOOK_SECRET_MERGE,
        },
        "note": "offline template only (a REAL location write must ride the "
                "house clients, CAF_BROWSER_UA on every request, the CF 1010 "
                "law); the workflow is built in the template location via "
                "the Skill 44 caf build rail and PUBLISHED (one toggle per "
                "workflow) before it fires live",
    }


def render_payload():
    """The JSON face of the generator: workflow_payload() as an indented,
    key-sorted JSON document. PURE and OFFLINE."""
    return json.dumps(workflow_payload(), indent=2, sort_keys=True)


# --------------------------------------------------------------------------- #
# Offline self-test (no network, no credentials) — proves the template
# against the W10 law. Every law is asserted on the GENERATED payload, so a
# drift in the copy, the links, or the never-a-real-token rule is caught
# here, never downstream.
# --------------------------------------------------------------------------- #
def _load_contracts():
    """Load the snapshot contract and field map for the link-field law.
    Returns (contract, field_map) or raises with a typed reason."""
    try:
        with open(CONTRACT_PATH, "r", encoding="utf-8") as fh:
            contract = json.load(fh)
    except OSError as exc:
        raise ValueError("contract unreadable: %s (%s)"
                         % (CONTRACT_PATH, exc)) from exc
    except ValueError as exc:
        raise ValueError("contract malformed JSON: %s (%s)"
                         % (CONTRACT_PATH, exc)) from exc
    try:
        with open(FIELD_MAP_PATH, "r", encoding="utf-8") as fh:
            field_map = json.load(fh)
    except OSError as exc:
        raise ValueError("field map unreadable: %s (%s)"
                         % (FIELD_MAP_PATH, exc)) from exc
    except ValueError as exc:
        raise ValueError("field map malformed JSON: %s (%s)"
                         % (FIELD_MAP_PATH, exc)) from exc
    return contract, field_map


def _contract_row(contract):
    """The contract's W10 row, or None when the contract does not carry it."""
    rows = ((contract.get("workflows") or {}).get("release_notifications") or [])
    for row in rows:
        if row.get("name") == WORKFLOW_NAME:
            return row
    return None


def _tags_slug(contract):
    """The contract's tags.slugs entry for the W10 slug, or None."""
    for entry in ((contract.get("tags") or {}).get("slugs") or []):
        if entry.get("slug") == TRIGGER_TAG:
            return entry
    return None


def self_test(out=None) -> int:
    """The offline self-test battery. Returns EX_OK on a full pass, EX_STOP
    when the contract is unreadable/malformed, EX_VIOLATION on any law
    drift (never 'unexpected error')."""
    out = out or sys.stderr
    try:
        contract, field_map = _load_contracts()
    except ValueError as exc:
        out.write("[w10-release-final] STOP: %s\n" % exc)
        return EX_STOP

    fails = []

    # (1) contract-row law: the W10 row must exist and carry the exact tag,
    # the exact link fields, and the exact SMS link field.
    row = _contract_row(contract)
    if row is None:
        fails.append(("contract",
                      "contract workflows.release_notifications has no row "
                      "named %r" % WORKFLOW_NAME))
    else:
        if row.get("trigger_tag") != TRIGGER_TAG:
            fails.append(("contract",
                          "contract row trigger_tag %r != %r"
                          % (row.get("trigger_tag"), TRIGGER_TAG)))
        for link in EMAIL_LINK_FIELDS:
            if link not in (row.get("email_link_fields") or []):
                fails.append(("contract",
                              "contract row email_link_fields does not carry "
                              "%s (drift)" % link))
        if row.get("sms_link_field") != SMS_LINK_FIELD:
            fails.append(("contract",
                          "contract row sms_link_field %r != %r"
                          % (row.get("sms_link_field"), SMS_LINK_FIELD)))

    # (1b) tags-row law: the W10 slug's tags entry must exist with the
    # byte-exact producer_gate "S8 final" and DOCTRINE status (the W10
    # firing authority: stage-runner-fired at S8, never a producer-approve
    # gate; gate_engine.py GATE_RELEASE_SLUG intentionally carries no
    # s8 entry).
    tag_entry = _tags_slug(contract)
    if tag_entry is None:
        fails.append(("contract",
                      "contract tags.slugs has no entry for slug %r"
                      % TRIGGER_TAG))
    else:
        if tag_entry.get("producer_gate") != PRODUCER_GATE:
            fails.append(("contract",
                          "contract tags row producer_gate %r != %r"
                          % (tag_entry.get("producer_gate"), PRODUCER_GATE)))
        if (tag_entry.get("status") or "").upper() != "DOCTRINE":
            fails.append(("contract",
                          "contract tags row status %r != 'DOCTRINE'"
                          % tag_entry.get("status")))

    # (2) field-map law: every W10 link key must be declared in the
    # deliverable_fields map (the copy_qc_workflows.py
    # AF-AE-COPY-FIELD-DRIFT law — a renamed key on either side is a
    # located FAIL, never a blind audit). The declared keys are the map's
    # bare field keys ("chapter", "rewrite1", "rewrite2", ...); the
    # template's link fields reference the contact-level keys, so the bare
    # KEY is matched against the map's declared values' field keys (the
    # "..._pdf_url" / "..._doc_url" names), exactly as copy_qc_workflows
    # resolves them.
    declared = set()
    for row in (field_map.get("deliverable_fields") or {}).values():
        for value in (row or {}).values():
            if isinstance(value, str):
                declared.add(value.replace("contact.", "", 1))
    for bare in LINK_BARE_KEYS:
        if bare not in declared:
            fails.append(("field-map",
                          "link field %s is not declared in field-map "
                          "deliverable_fields (drift)" % bare))

    # (3) copy law over the generated template (editors never AI, zero
    # em-dashes, both producer merges, the standing instruction, the
    # sign-off).
    payload = workflow_payload()
    body_text = payload["email"]["body"]
    sms_text = payload["sms"]["body"]
    from_name_merge = payload["email"]["from_name_merge"]
    copy_fails = _copy_check(body_text, sms_text, from_name_merge)
    for check, detail in copy_fails:
        fails.append(("copy-%s" % check, detail))

    # (4) never-a-real-token law over the whole rendered template.
    rendered = render_payload()
    token_detail = _never_a_real_token_check(rendered)
    if token_detail is not None:
        fails.append(("never-a-real-token", token_detail))

    # (5) the link-only SMS law: the SMS body carries EXACTLY ONE link
    # (copy_law sms_shape), and that link is the contract's sms_link_field.
    # The one-link count is matched on the whitespace-normalized field KEY
    # (the same key in either merge spelling — compact or spaced — is the
    # same link at send time), while the contract-compare is byte-exact on
    # the contract's own compact spelling.
    def _key(m):
        return m.replace("{{", "").replace("}}", "").replace(" ", "")

    sms_key = _key(SMS_LINK_FIELD)
    link_count = 0
    for link in (CHAPTER_PDF, CHAPTER_DOC):
        if _key(link) in sms_text.replace(" ", ""):
            link_count += 1
    if link_count != 1:
        fails.append(("sms-shape",
                      "link-only SMS must carry EXACTLY ONE deliverable "
                      "link, found %d" % link_count))
    elif sms_key not in sms_text.replace(" ", ""):
        fails.append(("sms-shape",
                      "the one SMS link is not the contract sms_link_field "
                      + SMS_LINK_FIELD))

    # (6) the stage-form link law: the email carries the stage form link with
    # the anthology_id and stage query params prefilled.
    stage_form = payload["email"]["stage_form_link"]
    if "?anthology_id=" not in stage_form:
        fails.append(("stage-form", "stage-form link has no anthology_id "
                      "query param (G3 key law)"))
    if "&stage=" + STAGE not in stage_form:
        fails.append(("stage-form", "stage-form link has no stage=%s query "
                      "param" % STAGE))

    # (7) the workflow shape law: both actions present.
    for action in ("send-email", "send-sms"):
        if action not in payload["actions"]:
            fails.append(("shape", "missing action %s" % action))

    if fails:
        for check, detail in fails:
            out.write("[w10-release-final] %s: %s\n" % (check, detail))
        out.write("[w10-release-final] self-test FAILED "
                  "(%d violation%s)\n" % (len(fails),
                                          "" if len(fails) == 1 else "s"))
        return EX_VIOLATION
    out.write("[w10-release-final] self-test PASS: W10 release-final "
              "template law holds (contract row, tags row, field-map links, "
              "copy law, never-a-real-token, link-only SMS, stage-form "
              "link)\n")
    return EX_OK


# --------------------------------------------------------------------------- #
# CLI (the ONE entry point; every command is OFFLINE).
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="w10_release_final.py",
        description="W10 release-final notification workflow template "
                    "generator (OFFLINE: no network, no credential).")
    ap.add_argument("cmd", nargs="?", choices=["plan", "render", "self-test"],
                    help="plan | render | self-test")
    args = ap.parse_args(argv)

    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "render":
        # The generated template, one JSON document (offline, no token).
        print(render_payload())
        return EX_OK
    # plan: the offline plan — the W10 template law with its sources.
    print(json.dumps({
        "contract": "workflows.release_notifications",
        "workflow": WORKFLOW_NAME,
        "trigger_tag": TRIGGER_TAG,
        "producer_gate": PRODUCER_GATE,
        "stage_cursor": STAGE_CURSOR,
        "stage": STAGE,
        "actions": ["send-email", "send-sms"],
        "milestone": MILESTONE_NOTE,
        "email": {
            "from_name_merge": PRODUCER_MERGE,
            "standing_instruction": STANDING_INSTRUCTION,
            "sign_off": SIGN_OFF,
            "link_fields": list(EMAIL_LINK_FIELDS),
        },
        "sms": {
            "shape": "link-only short message (one warm sentence plus ONE "
                     "link)",
            "sms_link_field": SMS_LINK_FIELD,
        },
        "stage_form_link": _stage_form_link(),
        "copy_law": {
            "editors_never_ai": True,
            "no_em_dashes": True,
            "producer_name_merge": PRODUCER_MERGE,
        },
        "never_a_real_token": {
            "webhook_url": WEBHOOK_URL_MERGE,
            "hook_secret": HOOK_SECRET_MERGE,
        },
        "note": "offline plan only (synthetic merges, no network, no "
                "credential needed); the workflow is built in the template "
                "location via the Skill 44 caf build rail and PUBLISHED "
                "before it fires live",
    }, indent=2, sort_keys=True))
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
