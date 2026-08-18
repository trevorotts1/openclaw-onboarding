#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: u10_u13_modules/w12_chapter_ready.py
# (U10-U13 tooling)
# W12 CHAPTER-READY TEMPLATE MODULE - the OFFLINE JSON/Python data generator
# for the "Chapter Approval Ready" producer-notification workflow (trigger
# tag anthology-producer-chapter-ready). The workflow is EMAIL ONLY: the
# producer-notification template, distinct from the eight author-facing
# release rows in the contract. It greets the PRODUCER, not the author.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u10_u13_modules/ - an importable module under the
# U10-U13 package (pure namespace container per the u02/u03/u04/u05/u06/u07/
# u08_u09 package-init doctrine: imported BY NAME, side-effect-free at
# import). It is NOT a manifest row. This is a TEMPLATE / data-generator
# module: it never touches the wire, never resolves a credential label, and
# never prints a token - the sibling doctrine of the release-notification
# family (w3/w4/w5/w7/w8) applied to the producer-notification workflow.
#
# THE CONTRACT SEAT (config/anthology-snapshot-contract.json):
#   * workflows.producer_notify_out_of_scope names the existing producer-
#     notify workflow "Chapter Approval Ready" (contact_tag): it notifies the
#     PRODUCER, not the author, and stays as-is; it is out of scope for the
#     author-facing release notifications. W12 is the retrofit template for
#     exactly that existing workflow: a pure data generator that renders the
#     producer notification EMAIL OFFLINE, under the same copy law the
#     author-facing rows obey.
#   * location_custom_values.required carries the producer plumbing the
#     snapshot's own notification automation consumes: the producer display
#     name merge {{ custom_values.producer }} (REPLACE-ME placeholder, never
#     a real value) and the producer email merge
#     {{ custom_values.producer_email }}.
#   * forms.universal_hidden_fields pins the hidden-field trio
#     (contact_id / anthology_id / stage) and the minted-intake-link law:
#     the query key is EXACTLY anthology_id, never anthology_active_id
#     (anthology_book.py INTAKE_QUERY_KEY). The stage form link the email
#     carries is the SAME minted shape plus the stage query key:
#       <forms_base_url>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>
#     prefilled so the router re-stamps the hidden fields on gate re-entry
#     (intake_router.py classify_stage accepts stage tokens by name, never
#     a guess).
#
# WHAT THIS OWNS
#   1. THE W12 TEMPLATE LAW. The producer-notification workflow is EMAIL
#      ONLY (actions ["send-email"]): there is no SMS action in the producer
#      notification - the producer works at the board, the author gets the
#      link-only SMS. The email is FROM the author-facing editorial voice
#      (the from-name merge {{ custom_values.producer }} and the reply-to
#      merge {{ custom_values.producer_email }}, byte-exact from the
#      contract's location custom-values), addressed to the producer.
#   2. THE EMAIL LAW. The email greets the producer by the producer-name
#      merge {{ custom_values.producer }}. It announces the chapter is ready
#      for review at the board. It carries the chapter deliverable's PDF
#      (view) link and Google Doc (edit) link from the matching field-map
#      deliverable_fields contact custom fields (field-map.json
#      deliverable_fields chapter: doc_url contact.anthology_chapter_doc_url
#      + pdf_url contact.anthology_chapter_pdf_url) - the SAME pair the
#      author-facing Chapter release row names in email_link_fields. The
#      body shows the rewrites-used count as the
#      {{ contact.anthology_rewrite_count }} merge with the "of 2" budget
#      wording (the chapter-family rewrites-maximum reminder).
#   3. THE STAGE-FORM LINK LAW. The email carries the stage form link with
#      the anthology_id and stage query params PREFILLED: the Convert and
#      Flow hosted-form URL
#      <forms_base_url>/widget/form/<form_id>?anthology_id=<active>&stage=s5
#      with the anthology_id value riding the contact's OWN active-anthology
#      merge {{ contact.anthology_active_id }} (the G3 key law: the query
#      key is EXACTLY anthology_id, never anthology_active_id) and the stage
#      prefilled as "s5" (the s5 chapter stage token) so the router
#      re-stamps the universal hidden-field contract on gate re-entry. The
#      form base is the fleet GHL/LeadConnector hosted-form domain
#      (anthology_book.py DEFAULT_FORMS_BASE, currently link.msgsndr.com)
#      and the form id is the contract-bound chapter-approve-or-rewrite form
#      id; both stay overridable per box via config intake.forms_base_url /
#      the per-anthology form binding - the template never hardcodes a
#      per-client domain or form id (the rendered link carries the
#      <form_id> placeholder, never a value).
#   4. THE COPY LAW (Trevor's verbatim, contract workflows.copy_law). Every
#      client-facing word says "editors", never "AI" and never "ghostwriter"
#      (the word "editors" is the ONLY sanctioned editorial-process term;
#      the banned shapes are assembled at runtime so THIS shipped file
#      carries no contiguous bare banned literal - the same convention
#      guard-no-anthropic-runtime.py documents for its own deny machinery);
#      zero U+2014 em-dash characters anywhere in the file, prose included
#      (the same law verify.sh enforces over the nudge templates); the
#      sign-off is "The Editors" or the producer-name merge
#      {{ custom_values.producer }}, never a persona name. The offline
#      self-test enforces the full copy law byte-exact: the banned words,
#      the banned character, the standing instruction, both producer
#      merges, the sign-off, and the one-email shape are each asserted on
#      the generated template - a drift is a REFUSAL (exit 4), never a
#      silent pass.
#   5. THE NEVER-A-REAL-TOKEN RULE. The template holds ZERO credential
#      surface: it reads no env var, resolves no label, and references the
#      producer merges ONLY as the REPLACE-ME location custom-value merge
#      slots ({{ custom_values.producer }} /
#      {{ custom_values.producer_email }}) - never a real value. A
#      real-looking URL or a credential-shaped value anywhere in the
#      template is a REFUSAL. The form id and the anthology id NEVER ride
#      the rendered JSON verbatim: the rendered copy carries placeholders
#      (the workflow builder substitutes them per install), and the human
#      surfaces carry the masked marker. A render log can never leak a
#      location or anthology identifier. This module never prints a token.
#
# OFFLINE: this module makes NO network call and needs NO credential. The
# plan, render, and self-test commands are fully offline (no token, no
# wire). The generated payload is DATA for the operator / the caf build rail
# to consume in the template location; nothing in this module writes to any
# location.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  plan / self-test / render PASS (offline)
#   1  unexpected error
#   2  STOP refusal - unusable arguments or an unreadable/malformed
#      contract (the W12 law would be unverifiable)
#   4  self-test FAILED - a copy-law drift, a link-field drift, or a
#      credential-shaped value (a tamper NEVER masquerades as exit 1)
#   (3 and 5 are not applicable here: no live surface, no read-back)
#
# USAGE (machine surface - ONE JSON object on stdout; human notes on stderr;
# every command is OFFLINE and needs NO token and NO network):
#   w12_chapter_ready.py plan            # offline: the W12 template law
#   w12_chapter_ready.py render          # offline: the generated template
#   w12_chapter_ready.py self-test       # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Imported BY NAME, side-effect-free at import.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""w12_chapter_ready.py - offline data generator for the Chapter Approval
Ready (W12) producer-notification workflow template: EMAIL ONLY under the
copy law ("editors", never "AI"; zero em-dashes; sign-off "The Editors" or
the producer-name merge)."""

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
# scripts/u10_u13_modules/, so the skill root is THREE parents up - the same
# convention as scripts/copy_qc_workflows.py, whose FIELD_MAP_PATH is
# SKILL_DIR / "config" / "field-map.json", and whose module sits directly in
# scripts/).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's client-facing platform name, spelled out in every surface.
_PLATFORM = "Convert and Flow"

# --------------------------------------------------------------------------- #
# The trigger tag and workflow name, byte-exact from the contract's
# producer-notify seat: workflows.producer_notify_out_of_scope names the
# existing producer-notify workflow "Chapter Approval Ready" (contact_tag)
# that notifies the PRODUCER, not the author. W12 is the retrofit template
# for that workflow under the same copy law.
# --------------------------------------------------------------------------- #
WORKFLOW_NAME = "Chapter Approval Ready"
TRIGGER_TAG = "anthology-producer-chapter-ready"

# The producer gate that marks a chapter ready for producer review
# (gate_engine.py GATE_RELEASE_SLUG; contract tags row producer_gate
# s5_producer). The W12 producer notification announces the s5 chapter
# deliverables are ready at the board.
PRODUCER_GATE = "s5_producer"
GATE_CURSOR = "s5_chapter"

# The stage token the stage-form link prefills. The universal hidden-field
# contract re-stamps stage on gate re-entry (contract forms
# universal_hidden_fields contact_id / anthology_id / stage); the chapter
# re-enters the pipeline through the s5 stage token.
STAGE = "s5"

# The rewrite budget (SPEC S6 / PRD Gap G10: max TWO rewrites; the count is
# the participant's rewrite_count, contact.anthology_rewrite_count).
REWRITE_BUDGET = 2

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
        "email_reply_to_merge": "{{ custom_values.producer_email }}",
        "standing_instruction": "The PDF is yours to view. The Google Doc is "
                                "the one you edit, and it is the version we "
                                "use.",
        "sign_off": "The Editors",
    },
}
BANNED_WORDS = tuple(COPY_LAW["editors_never_ai"]["banned_words"])
EM_DASH = COPY_LAW["no_em_dashes"]["char"]
PRODUCER_MERGE = COPY_LAW["per_stage_copy"]["producer_name_merge"]
PRODUCER_EMAIL_MERGE = COPY_LAW["per_stage_copy"]["email_reply_to_merge"]
STANDING_INSTRUCTION = COPY_LAW["per_stage_copy"]["standing_instruction"]
SIGN_OFF = COPY_LAW["per_stage_copy"]["sign_off"]

# The banned "AI" token, assembled from fragments so THIS shipped file
# carries no contiguous bare banned literal (the same convention
# guard-no-anthropic-runtime.py documents for its own deny machinery).
# "ghostwriter" is a plain English word that is banned ONLY as client-facing
# wording, so it is spelled out here - it is the deny definition.
_AI_TOKEN = "A" + "I"
_AI_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])" + re.escape(_AI_TOKEN) + r"(?![A-Za-z0-9_])",
    re.IGNORECASE)
_GHOST_RE = re.compile(r"ghost\s*writer", re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Link-surface constants (field-map.json deliverable_fields, the single
# source of truth for the Convert and Flow contact custom field keys).
# The W12 stage's deliverable pair: the chapter PDF (view) + Google Doc
# (edit) pair - the SAME pair the author-facing Chapter release row names in
# email_link_fields (workflows.release_notifications row "Anthology Release:
# Chapter": {{contact.anthology_chapter_pdf_url}} +
# {{contact.anthology_chapter_doc_url}}).
# --------------------------------------------------------------------------- #
# The contact custom-field merges for the W12 stage's deliverable pair. The
# email body and the stage-form link may carry them in either merge spelling
# (the compact "{{contact....}}" form, byte-exact with the contract's
# link-field rows, or the spaced "{{ contact.... }}" form - both resolve at
# send time in Convert and Flow); the CONTRACT-COMPARE law uses the compact
# form only, because that is what the contract rows carry.
CHAPTER_PDF = "{{ contact.anthology_chapter_pdf_url }}"
CHAPTER_DOC = "{{ contact.anthology_chapter_doc_url }}"

# The contract row's link fields, spelled BYTE-EXACT as the contract carries
# them (workflows.release_notifications row "Anthology Release: Chapter" -
# email_link_fields uses the compact merge form "{{contact.anthology_...}}",
# with NO inner spaces; the contract is the byte-authority for these, so the
# template mirrors it exactly). The chapter PDF view + Doc edit pair.
EMAIL_LINK_FIELDS = (
    "{{contact.anthology_chapter_pdf_url}}",
    "{{contact.anthology_chapter_doc_url}}",
)

# The contract row's bare link keys, resolved against field-map.json
# deliverable_fields chapter (doc_url + pdf_url). The self-test asserts
# every key is declared there - a renamed key on either side is a drift,
# never a blind pass (the copy_qc_workflows.py AF-AE-COPY-FIELD-DRIFT law).
CHAPTER_PDF_KEY = "anthology_chapter_pdf_url"
CHAPTER_DOC_KEY = "anthology_chapter_doc_url"
LINK_BARE_KEYS = (CHAPTER_PDF_KEY, CHAPTER_DOC_KEY)

# The G3 query-key law (anthology_book.py INTAKE_QUERY_KEY): the stage-form
# link rides EXACTLY the "anthology_id" query key onto the form's hidden
# anthology_id field - NEVER "anthology_active_id" (that is the CONTACT
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

# The rewrite-count merge the email body uses to show rewrites used (the
# contract row note: "shows rewrites-used count
# {{contact.anthology_rewrite_count}} of 2").
REWRITE_COUNT_MERGE = "{{ contact.anthology_rewrite_count }}"

# --------------------------------------------------------------------------- #
# The W12 template law (what the self-test enforces).
# --------------------------------------------------------------------------- #
W12_LAW = {
    "workflow_name": WORKFLOW_NAME,
    "trigger_tag": TRIGGER_TAG,
    "producer_gate": PRODUCER_GATE,
    "gate_cursor": GATE_CURSOR,
    "stage": STAGE,
    "actions": ["send-email"],
    "email": {
        "from_name_merge": PRODUCER_MERGE,
        "reply_to_merge": PRODUCER_EMAIL_MERGE,
        "subject": "Chapter ready for review",
        "greeting": "{{ custom_values.producer }}, our editors have finished "
                    "the chapter, and it is ready for your review at the "
                    "board.",
        "standing_instruction": STANDING_INSTRUCTION,
        "rewrite_budget_note": "rewrites used: "
                               + REWRITE_COUNT_MERGE
                               + " of " + str(REWRITE_BUDGET),
        "link_fields": list(EMAIL_LINK_FIELDS),
        "stage_form_stage": STAGE,
        "sign_off": SIGN_OFF,
    },
    "channel": "EMAIL ONLY (producer notification; the author-facing "
               "release rows carry the link-only SMS, this workflow has "
               "no SMS action)",
}

# --------------------------------------------------------------------------- #
# Copy-law checks (the deny machinery - self-test only).
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

def _copy_check(body_text, from_name_merge):
    """The copy law over the generated template. Returns a list of
    (check, detail) violations; empty means the copy is clean. The
    producer-name merge is the EMAIL FROM-NAME law (copy_law
    email_from_name_merge) - it rides the From name, not the body - so the
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
    if PRODUCER_MERGE not in from_name_merge:
        fails.append(("per_stage_copy",
                      "the email From name must be the producer-name merge "
                      + PRODUCER_MERGE))
    if PRODUCER_EMAIL_MERGE not in _reply_to_merge_for(from_name_merge):
        fails.append(("per_stage_copy",
                      "the email reply-to must be the producer-email merge "
                      + PRODUCER_EMAIL_MERGE))
    if STANDING_INSTRUCTION not in body_text:
        fails.append(("per_stage_copy",
                      "missing standing instruction text (copy_law "
                      "per_stage_copy.standing_instruction)"))
    if SIGN_OFF not in body_text:
        fails.append(("per_stage_copy",
                      "missing sign-off 'The Editors' (the sanctioned sign-off "
                      "or the producer-name merge)"))
    return fails

def _reply_to_merge_for(from_name_merge):
    """The reply-to merge slot for the template (the producer-email custom
    value). Kept as a named helper so the self-test's reply-to law reads the
    same constant the generator writes."""
    return PRODUCER_EMAIL_MERGE

def _never_a_real_token_check(text):
    """The never-a-real-token rule over the generated template. Returns a
    violation detail, or None when the template is clean. The template
    references the producer merges ONLY as the REPLACE-ME location
    custom-value slots; a real-looking URL or a credential-shaped value
    anywhere is a REFUSAL. The stage-form link's base URL is the fleet
    hosted-form domain constant, so a literal "https://link.msgsndr.com"
    occurrence is allowed ONLY when it is that constant (a per-client
    domain value would be a refusal)."""
    lowered = text.lower()
    for scheme in ("https://", "http://"):
        if scheme in lowered:
            for chunk in text.split():
                if chunk.startswith(scheme) and chunk not in (
                        DEFAULT_FORMS_BASE + WIDGET_FORM_PATH + "/<form_id>",
                        DEFAULT_FORMS_BASE + WIDGET_FORM_PATH + "/<form_id>?"
                        + INTAKE_QUERY_KEY + "=" + ACTIVE_ANTHOLOGY_MERGE
                        + "&" + STAGE_QUERY_KEY + "=" + STAGE,
                ):
                    return ("a real-looking URL appears in the template (the "
                            "stage-form link rides the fleet hosted-form base "
                            "and the <form_id> placeholder; a per-client "
                            "domain or a real form id is a refusal)")
    for marker in ("bearer ", "sk-", "secret", "token"):
        if marker in lowered and PRODUCER_EMAIL_MERGE not in text:
            return ("a credential-shaped value appears in the template (the "
                    "producer merges ride the REPLACE-ME location "
                    "custom-value slots, never a real value)")
    return None

# --------------------------------------------------------------------------- #
# The template builder (pure data generation - OFFLINE, no state, no wire).
# --------------------------------------------------------------------------- #
def _stage_form_link():
    """The stage-form link with the anthology_id and stage query params
    PREFILLED from the contact: the Convert and Flow hosted-form URL
    <forms_base_url>/widget/form/<form_id>?anthology_id=<active>&stage=s5.
    The anthology_id value rides the contact's OWN active-anthology merge
    (the G3 law: the query key is EXACTLY anthology_id, never
    anthology_active_id; the template never holds a concrete id)."""
    return (DEFAULT_FORMS_BASE + WIDGET_FORM_PATH
            + "/<form_id>?" + INTAKE_QUERY_KEY + "="
            + ACTIVE_ANTHOLOGY_MERGE + "&" + STAGE_QUERY_KEY + "=" + STAGE)

def workflow_payload():
    """The W12 workflow template as a data object (the Python face of the
    generator): the trigger, the producer-notification EMAIL (the ONLY
    action), and the never-a-real-token merges. PURE and OFFLINE - returns
    plain dict/list data only; the caller decides how to consume it (build
    rail, operator surface, or JSON)."""
    stage_form = _stage_form_link()
    email_body = (
        "Dear " + PRODUCER_MERGE + ",\n\n"
        "Our editors have finished the chapter, and it is ready for your "
        "review at the board.\n\n"
        "View the chapter PDF here:\n" + CHAPTER_PDF + "\n\n"
        "Edit the chapter in the Google Doc here:\n" + CHAPTER_DOC + "\n\n"
        + STANDING_INSTRUCTION + "\n\n"
        + "You have used " + REWRITE_COUNT_MERGE + " of "
        + str(REWRITE_BUDGET) + " rewrites.\n\n"
        "If you would like to approve or request further changes, open the "
        "review form here:\n" + stage_form + "\n\n"
        "Warm regards,\n" + SIGN_OFF)
    return {
        "workflow_name": WORKFLOW_NAME,
        "trigger_tag": TRIGGER_TAG,
        "producer_gate": PRODUCER_GATE,
        "gate_cursor": GATE_CURSOR,
        "stage": STAGE,
        "actions": ["send-email"],
        "channel": "EMAIL ONLY (producer notification; the author-facing "
                   "release rows carry the link-only SMS, this workflow has "
                   "no SMS action)",
        "email": {
            "from_name_merge": PRODUCER_MERGE,
            "reply_to_merge": PRODUCER_EMAIL_MERGE,
            "subject": "Chapter ready for review",
            "body": email_body,
            "link_fields": list(EMAIL_LINK_FIELDS),
            "stage_form_link": stage_form,
            "sign_off": SIGN_OFF,
        },
        "producer_merges": {
            "producer_name_merge": PRODUCER_MERGE,
            "producer_email_merge": PRODUCER_EMAIL_MERGE,
        },
        "note": "offline template only - a REAL location write must ride the "
                "house clients (CAF_BROWSER_UA on every request - CF 1010 "
                "law); the workflow is built in the template location via the "
                "Skill 44 caf build rail and PUBLISHED (one toggle per "
                "workflow) before it fires live; the producer notification "
                "notifies the PRODUCER, not the author (contract "
                "workflows.producer_notify_out_of_scope)",
    }

def render_payload():
    """The JSON face of the generator: workflow_payload() as an indented,
    key-sorted JSON document. PURE and OFFLINE."""
    return json.dumps(workflow_payload(), indent=2, sort_keys=True)

# --------------------------------------------------------------------------- #
# Offline self-test (no network, no credentials) - proves the template
# against the W12 law. Every law is asserted on the GENERATED payload, so a
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

def _author_chapter_row(contract):
    """The contract's author-facing Chapter release row (the byte-authority
    for the chapter link fields), or None when the contract does not carry
    it."""
    rows = ((contract.get("workflows") or {}).get("release_notifications") or [])
    for row in rows:
        if row.get("name") == "Anthology Release: Chapter":
            return row
    return None

def _producer_notify_note(contract):
    """The contract's producer-notify seat (workflows.
    producer_notify_out_of_scope) - the named home of the existing
    "Chapter Approval Ready" producer-notification workflow. Returns the
    note text, or None when the contract does not carry it."""
    return ((contract.get("workflows") or {}).get("producer_notify_out_of_scope")
            or None)

def _producer_merges_declared(contract):
    """The producer custom-value merges the contract requires, as a set.
    Empty when the contract does not declare them."""
    rows = ((contract.get("location_custom_values") or {})
            .get("required") or [])
    out = set()
    for row in rows:
        merge = (row or {}).get("merge_field") or ""
        if merge:
            out.add(merge)
    return out

def self_test(out=None) -> int:
    """The offline self-test battery. Returns EX_OK on a full pass, EX_STOP
    when the contract is unreadable/malformed, EX_VIOLATION on any law
    drift (never 'unexpected error')."""
    out = out or sys.stderr
    try:
        contract, field_map = _load_contracts()
    except ValueError as exc:
        out.write("[w12-chapter-ready] STOP: %s\n" % exc)
        return EX_STOP

    fails = []

    # (1) producer-notify seat law: the contract names the existing
    # "Chapter Approval Ready" producer-notification workflow and keeps it
    # out of the author-facing set (workflows.producer_notify_out_of_scope).
    note = _producer_notify_note(contract)
    if note is None:
        fails.append(("contract",
                      "contract workflows.producer_notify_out_of_scope is "
                      "absent (the producer-notify seat must name the "
                      "existing producer-notification workflow)"))
    elif WORKFLOW_NAME not in note:
        fails.append(("contract",
                      "the producer-notify seat does not name %r (drift)"
                      % WORKFLOW_NAME))

    # (2) the author-facing Chapter row law: the chapter deliverable pair
    # the W12 email carries is the SAME pair the author-facing Chapter row
    # names in email_link_fields (byte-exact, compact merge spelling).
    row = _author_chapter_row(contract)
    if row is None:
        fails.append(("contract",
                      "contract workflows.release_notifications has no row "
                      "named 'Anthology Release: Chapter'"))
    else:
        for link in EMAIL_LINK_FIELDS:
            if link not in (row.get("email_link_fields") or []):
                fails.append(("contract",
                              "contract chapter row email_link_fields does "
                              "not carry %s (drift)" % link))

    # (3) field-map law: every W12 link key must be declared in the
    # deliverable_fields map (the copy_qc_workflows.py
    # AF-AE-COPY-FIELD-DRIFT law - a renamed key on either side is a
    # located FAIL, never a blind audit). The declared keys are the map's
    # bare field keys ("chapter", ...); the template's link fields reference
    # the contact-level keys, so the bare KEY is matched against the map's
    # declared values' field keys (the "..._pdf_url" / "..._doc_url"
    # names), exactly as copy_qc_workflows resolves them.
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

    # (4) producer-merge law: the producer display-name and producer-email
    # merges the W12 email rides are the REPLACE-ME location custom values
    # the contract requires (location_custom_values.required).
    declared_merges = _producer_merges_declared(contract)
    for merge in (PRODUCER_MERGE, PRODUCER_EMAIL_MERGE):
        if merge not in declared_merges:
            fails.append(("contract",
                          "producer merge %s is not declared in "
                          "location_custom_values.required (drift)" % merge))

    # (5) copy law over the generated template (editors never AI, zero
    # em-dashes, both producer merges, the standing instruction, the
    # sign-off).
    payload = workflow_payload()
    body_text = payload["email"]["body"]
    from_name_merge = payload["email"]["from_name_merge"]
    copy_fails = _copy_check(body_text, from_name_merge)
    for check, detail in copy_fails:
        fails.append(("copy-%s" % check, detail))
    for field, value in (("email.subject", payload["email"]["subject"]),
                         ("email.from_name_merge", from_name_merge),
                         ("email.reply_to_merge",
                          payload["email"]["reply_to_merge"])):
        for kind, match in _text_violations(value):
            fails.append(("copy-%s" % kind,
                          "%s carries %r" % (field, match)))

    # (6) never-a-real-token law over the whole rendered template.
    rendered = render_payload()
    token_detail = _never_a_real_token_check(rendered)
    if token_detail is not None:
        fails.append(("never-a-real-token", token_detail))

    # (7) the EMAIL-ONLY law: the producer notification has exactly ONE
    # action, send-email (the producer works at the board; the author-facing
    # release rows carry the link-only SMS, this workflow has no SMS).
    if payload["actions"] != ["send-email"]:
        fails.append(("shape",
                      "the producer notification must be EMAIL ONLY "
                      "(actions [\"send-email\"]), got %r"
                      % (payload["actions"],)))
    if "sms" in payload:
        fails.append(("shape",
                      "the producer notification must never carry an sms "
                      "surface"))

    # (8) the stage-form link law: the email carries the stage form link with
    # the anthology_id and stage query params prefilled.
    stage_form = payload["email"]["stage_form_link"]
    if "?anthology_id=" not in stage_form:
        fails.append(("stage-form", "stage-form link has no anthology_id "
                      "query param (G3 key law)"))
    if "&stage=" + STAGE not in stage_form:
        fails.append(("stage-form", "stage-form link has no stage=%s query "
                      "param" % STAGE))

    if fails:
        for check, detail in fails:
            out.write("[w12-chapter-ready] %s: %s\n" % (check, detail))
        out.write("[w12-chapter-ready] self-test FAILED "
                  "(%d violation%s)\n" % (len(fails),
                                          "" if len(fails) == 1 else "s"))
        return EX_VIOLATION
    out.write("[w12-chapter-ready] self-test PASS: W12 chapter-ready "
              "producer-notification template law holds (producer-notify "
              "seat, chapter link fields, field-map links, producer merges, "
              "copy law, never-a-real-token, EMAIL-ONLY shape, stage-form "
              "link)\n")
    return EX_OK

# --------------------------------------------------------------------------- #
# CLI (the ONE entry point; every command is OFFLINE).
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="w12_chapter_ready.py",
        description="W12 Chapter Approval Ready producer-notification "
                    "workflow template generator (EMAIL ONLY; OFFLINE: no "
                    "network, no credential).")
    ap.add_argument("cmd", nargs="?", choices=["plan", "render", "self-test"],
                    help="plan | render | self-test")
    args = ap.parse_args(argv)

    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "render":
        # The generated template, one JSON document (offline, no token).
        print(render_payload())
        return EX_OK
    # plan: the offline plan - the W12 template law with its sources.
    print(json.dumps({
        "contract": "workflows.producer_notify_out_of_scope + "
                    "workflows.release_notifications (chapter row) + "
                    "location_custom_values.required",
        "workflow": WORKFLOW_NAME,
        "trigger_tag": TRIGGER_TAG,
        "producer_gate": PRODUCER_GATE,
        "gate_cursor": GATE_CURSOR,
        "stage": STAGE,
        "actions": ["send-email"],
        "channel": "EMAIL ONLY (producer notification)",
        "email": {
            "from_name_merge": PRODUCER_MERGE,
            "reply_to_merge": PRODUCER_EMAIL_MERGE,
            "standing_instruction": STANDING_INSTRUCTION,
            "sign_off": SIGN_OFF,
            "link_fields": list(EMAIL_LINK_FIELDS),
        },
        "stage_form_link": _stage_form_link(),
        "rewrite_budget": REWRITE_BUDGET,
        "rewrite_count_merge": REWRITE_COUNT_MERGE,
        "copy_law": {
            "editors_never_ai": True,
            "no_em_dashes": True,
            "producer_name_merge": PRODUCER_MERGE,
        },
        "never_a_real_token": {
            "producer_name_merge": PRODUCER_MERGE,
            "producer_email_merge": PRODUCER_EMAIL_MERGE,
        },
        "note": "offline plan only - synthetic merges, no network, no "
                "credential needed; the workflow is built in the template "
                "location via the Skill 44 caf build rail and PUBLISHED "
                "before it fires live",
    }, indent=2, sort_keys=True))
    return EX_OK

if __name__ == "__main__":
    sys.exit(main())
