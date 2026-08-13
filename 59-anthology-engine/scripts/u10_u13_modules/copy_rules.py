#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/copy_rules.py
# (U10-U13 tooling)
# THE COPY-RULE CONSTANT MODULE — the single canonical source of the copy law
# (config/anthology-snapshot-contract.json -> workflows.copy_law, Trevor's
# verbatim) plus the two link-surface laws for the U10-U13 tag->notification
# template family. Every sibling template module in this package (the
# w*_release_*.py generators and the main_skeleton.py dispatcher) imports its
# constants and deny machinery FROM HERE, so the law is DEFINED ONCE and
# ENFORCED EVERYWHERE: a drift is a refusal (exit 4), never a silent pass.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u10_u13_modules/ — an importable module under the
# U10-U13 package (pure namespace container per the u02/u03/u04/u05/u06/u07/
# u08_u09 package-init doctrine: imported BY NAME, side-effect-free at
# import — no file read, no env read, no wire touch at import time). It is
# NOT a manifest row. It is a TEMPLATE / DATA-GENERATOR module: it never
# touches the wire, never resolves a credential label, and never prints a
# token — the sibling doctrine of the U05 golden/attack fixtures (a fixture
# is DATA, not code) applied to the copy law itself.
#
# WHAT THIS OWNS
#   1. THE COPY LAW (workflows.copy_law, byte-exact). Every client-facing
#      word says "editors", never "AI" and never "ghostwriter" — the word
#      "editors" is the ONLY sanctioned editorial-process term (PRD
#      doctrine; MASTERDOC floor #14). Zero U+2014 em-dash characters
#      anywhere in the template copy (the same law verify.sh enforces over
#      the nudge templates; the COPY_LAW block below is the one documented
#      exception, exactly as copy_qc_workflows.py documents for its own
#      deny machinery). The sign-off is "The Editors" OR the producer-name
#      merge {{ custom_values.producer }}, NEVER a persona name. The email
#      From name is the producer-name merge (email_from_name_merge). The
#      standing instruction rides verbatim ("The PDF is yours to view. The
#      Google Doc is the one you edit, and it is the version we use."). The
#      SMS shape is link-only: one warm sentence plus ONE link
#      (sms_shape).
#   2. THE WARM-LANGUAGE LAW. Every client-facing word is warm and
#      personal: the email greets the author BY NAME via the author-name
#      merge {{ contact.first_name }} and closes warm ("Warm regards")
#      before the sanctioned sign-off. No cold or robotic phrasing is ever
#      sanctioned.
#   3. THE TWO-LINK LAW (per_stage_links). Each stage email carries that
#      stage's PDF (VIEW) link plus the editable Google Doc (EDIT) link,
#      pulled from the matching config/field-map.json deliverable_fields
#      contact custom fields — the SAME fields the contract row names in
#      email_link_fields. The PDF is the view artifact; the Google Doc is
#      the edit artifact (the standing instruction says so, verbatim).
#   4. THE STAGE-FORM LINK LAW. The email carries the stage form link: the
#      Convert and Flow hosted-form URL
#      <forms_base_url>/widget/form/<form_id>?anthology_id=<id>&stage=<stage>
#      with the anthology_id and stage query params PREFILLED — the
#      anthology_id value from the contact's OWN active-anthology merge
#      {{ contact.anthology_active_id }} (the G3 law: the query key is
#      EXACTLY "anthology_id", never "anthology_active_id" — that is the
#      CONTACT custom field, a different thing), and the stage token so the
#      intake router re-stamps the universal hidden-field contract on gate
#      re-entry (intake_router.py classify_stage accepts stage tokens by
#      name). The form base stays overridable per box via config
#      intake.forms_base_url; the template never hardcodes a per-client
#      domain or form id.
#   5. THE NEVER-A-REAL-TOKEN RULE. The template family merges the intake
#      hook URL and its Authorization header ONLY as the REPLACE-ME
#      location custom values {{ custom_values.anthology_webhook_url }} and
#      {{ custom_values.anthology_hook_secret }} (the snapshot's
#      location_custom_values contract) — a real-looking URL or a
#      credential-shaped value anywhere in the generated payload is a
#      REFUSAL. This module holds ZERO credential surface: it reads no env
#      var and resolves no label — a template module cannot leak what it
#      never holds.
#
# OFFLINE: this module makes NO network call and needs NO credential at any
# command. The generated payload is DATA for the sibling template generators
# and for the operator / the caf build rail to consume; nothing here writes
# to any location.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  plan / render / self-test PASS (offline)
#   1  unexpected error
#   2  STOP refusal (unusable arguments or an unreadable/malformed
#      contract — the copy law would be unverifiable)
#   4  self-test FAILED (a copy-law drift, a link-law drift, or a
#      credential-shaped value — a tamper NEVER masquerades as exit 1)
#   (3 and 5 are not applicable here: no live surface, no read-back)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# every command is OFFLINE and needs NO token and NO network):
#   copy_rules.py plan            # offline: the copy law with its sources
#   copy_rules.py render          # offline: the copy rules as JSON data
#   copy_rules.py self-test       # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Imported BY NAME, side-effect-free at import.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""copy_rules.py — canonical copy-law constants and deny machinery for the
U10-U13 release-notification template family: "editors", never the banned
words; zero em-dashes; sign-off "The Editors" or the producer merge; warm
language; stage-form link with anthology_id and stage prefilled; PDF view
plus Doc edit links per stage."""

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
# scripts/). NOTE: the contract and field map are loaded LAZILY in the
# self-test only; import stays side-effect-free (no file read at import).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's client-facing platform name, spelled out in every surface.
_PLATFORM = "Convert and Flow"

# --------------------------------------------------------------------------- #
# THE COPY LAW (config/anthology-snapshot-contract.json -> workflows.copy_law,
# Trevor's verbatim). Only this COPY_LAW block below may name the banned
# tokens or the banned character: this is the deny machinery's own
# definition, and the sibling static guard (guard-no-anthropic-runtime.py)
# allowlists deny definitions line-for-line. Every constant the sibling
# template modules import comes from here, so the law is defined exactly
# once.
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
    "warm_language": {
        "note": "Every client-facing word is warm and personal: the email "
                "greets the author BY NAME and closes warm before the "
                "sanctioned sign-off (Trevor's verbatim law: warm language "
                "in every client-facing word).",
        "greeting_merge": "{{ contact.first_name }}",
        "warm_close": "Warm regards",
    },
    "per_stage_links": {
        "note": "Each email carries that stage's PDF (VIEW) link plus "
                "editable Google Doc (EDIT) link pulled from the matching "
                "config/field-map.json deliverable_fields contact custom "
                "fields (contract workflows.copy_law per_stage_links).",
    },
}
BANNED_WORDS = tuple(COPY_LAW["editors_never_ai"]["banned_words"])
SANCTIONED_WORD = COPY_LAW["editors_never_ai"]["sanctioned_word"]
EM_DASH = COPY_LAW["no_em_dashes"]["char"]
PRODUCER_MERGE = COPY_LAW["per_stage_copy"]["producer_name_merge"]
FROM_NAME_MERGE = COPY_LAW["per_stage_copy"]["email_from_name_merge"]
SMS_SHAPE = COPY_LAW["per_stage_copy"]["sms_shape"]
STANDING_INSTRUCTION = COPY_LAW["per_stage_copy"]["standing_instruction"]
SIGN_OFF = COPY_LAW["per_stage_copy"]["sign_off"]
GREETING_MERGE = COPY_LAW["warm_language"]["greeting_merge"]
WARM_CLOSE = COPY_LAW["warm_language"]["warm_close"]

# The sign-off law, as a rule: the sign-off is "The Editors" OR the
# producer-name merge {{ custom_values.producer }}, NEVER a persona name
# (Trevor's verbatim). The self-test accepts EITHER sanctioned form; a
# template that signs off with anything else is a refusal.
SANCTIONED_SIGNOFFS = (SIGN_OFF, PRODUCER_MERGE)

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
# The stage-form link surface (the G3 law; anthology_book.py
# INTAKE_QUERY_KEY). The stage-form link rides EXACTLY the "anthology_id"
# query key onto the form's hidden anthology_id field — NEVER
# "anthology_active_id" (that is the CONTACT custom field the delivery
# writer stamps with the ACTIVE anthology, a different thing). The ACTIVE
# anthology id the contact carries IS the template's source for that query
# value, via the contact's own {{ contact.anthology_active_id }} merge — a
# template never holds a concrete id.
# --------------------------------------------------------------------------- #
INTAKE_QUERY_KEY = "anthology_id"
STAGE_QUERY_KEY = "stage"
ACTIVE_ANTHOLOGY_MERGE = "{{ contact.anthology_active_id }}"

# The fleet GHL/LeadConnector hosted-form domain (anthology_book.py
# DEFAULT_FORMS_BASE) and the hosted-form path prefix. Both stay overridable
# per box via config intake.forms_base_url; the template never hardcodes a
# per-client domain or form id.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
WIDGET_FORM_PATH = "/widget/form"

# The location custom-value merges the snapshot's tag->notification
# workflows use for the intake hook (location_custom_values contract;
# REPLACE-ME placeholders, never a real value). The template family carries
# them so a workflow's Custom Webhook action can fire the client's intake
# hook when the operator enables it.
WEBHOOK_URL_MERGE = "{{ custom_values.anthology_webhook_url }}"
HOOK_SECRET_MERGE = "{{ custom_values.anthology_hook_secret }}"

# --------------------------------------------------------------------------- #
# The two-link surface (contract workflows.copy_law per_stage_links +
# config/field-map.json deliverable_fields, the single source of truth for
# the Convert and Flow contact custom field keys). The stage keys below are
# the map's declared deliverable groups; each stage email carries that
# group's PDF (VIEW) link plus editable Google Doc (EDIT) link. The bare
# keys are matched against the map's declared values' field keys (the
# "..._pdf_url" / "..._doc_url" names), exactly as copy_qc_workflows.py
# resolves them.
# --------------------------------------------------------------------------- #
DELIVERABLE_STAGE_KEYS = (
    "avatar", "tone", "titles", "blurb", "outline",
    "chapter", "rewrite1", "rewrite2", "cover", "manuscript",
)

# The chapter stage's contact-level merges, in the spaced spelling the
# template bodies carry (both spellings resolve at send time in Convert and
# Flow; the CONTRACT-COMPARE law uses the compact form only, because that is
# what the contract rows carry). The self-test builds a canonical chapter
# email body from these to prove the two-link law on the generated rules
# payload.
CHAPTER_PDF_MERGE = "{{ contact.anthology_chapter_pdf_url }}"
CHAPTER_DOC_MERGE = "{{ contact.anthology_chapter_doc_url }}"

# --------------------------------------------------------------------------- #
# Copy-law checks (the deny machinery — self-test only). These are the
# shared helpers the sibling template modules call at their own self-tests,
# so a drift in ANY template trips the SAME denial machinery, defined once.
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

def copy_check(body_text, sms_text, from_name_merge):
    """The copy law over one template's email body, SMS body, and From-name
    merge. Returns a list of (check, detail) violations; empty means the
    copy is clean. The producer-name merge is the EMAIL FROM-NAME law
    (copy_law email_from_name_merge) — it rides the From name, not the body
    — so the From name is scanned alongside the body text. The sign-off law
    accepts EITHER sanctioned form ("The Editors" or the producer-name
    merge) in the body. The warm-language law requires the by-name greeting
    and the warm close in the email body."""
    fails = []
    if SANCTIONED_WORD not in body_text:
        fails.append(("editors_never_ai",
                      "the sanctioned word 'editors' is absent from the "
                      "email body (the editorial process must be 'editors', "
                      "never the banned word)"))
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
    if not any(signoff in body_text for signoff in SANCTIONED_SIGNOFFS):
        fails.append(("per_stage_copy",
                      "missing sanctioned sign-off (either 'The Editors' or "
                      "the producer-name merge " + PRODUCER_MERGE
                      + ", never a persona name)"))
    if GREETING_MERGE not in body_text:
        fails.append(("warm_language",
                      "the email must greet the author by name (the "
                      "author-name merge " + GREETING_MERGE
                      + ") — warm language is the law"))
    if WARM_CLOSE not in body_text:
        fails.append(("warm_language",
                      "the email must close warm ('" + WARM_CLOSE
                      + "') before the sanctioned sign-off"))
    return fails

def two_link_check(body_text, pdf_merge, doc_merge):
    """The two-link law (per_stage_links) over one email body: the stage's
    PDF (VIEW) link and the editable Google Doc (EDIT) link must BOTH be
    present. Returns a list of (check, detail) violations; empty means the
    pair is complete."""
    fails = []
    if pdf_merge not in body_text:
        fails.append(("per_stage_links",
                      "missing the stage's PDF (VIEW) link " + pdf_merge))
    if doc_merge not in body_text:
        fails.append(("per_stage_links",
                      "missing the stage's editable Google Doc (EDIT) link "
                      + doc_merge))
    return fails

def stage_form_link(stage):
    """The stage-form link with the anthology_id and stage query params
    PREFILLED: the Convert and Flow hosted-form URL
    <forms_base_url>/widget/form/<form_id>?anthology_id=<active>&stage=<stage>.
    The anthology_id value rides the contact's OWN active-anthology merge
    (the G3 law: the query key is EXACTLY anthology_id, never
    anthology_active_id; a template never holds a concrete id). The stage
    token is the stage runner's own STAGE constant (e.g. stage_s8_deliver.py
    STAGE == "s8"), an accepted stage token of intake_router.py
    classify_stage, so the router re-stamps the universal hidden-field
    contract on gate re-entry."""
    return (DEFAULT_FORMS_BASE + WIDGET_FORM_PATH
            + "/<form_id>?" + INTAKE_QUERY_KEY + "="
            + ACTIVE_ANTHOLOGY_MERGE + "&" + STAGE_QUERY_KEY + "=" + stage)

def stage_form_check(link, stage):
    """The stage-form link law over one built link: it must carry the
    anthology_id query param (the G3 key, prefilled from the contact's own
    active-anthology merge) AND the stage query param, prefilled with the
    given stage token. Returns a list of (check, detail) violations; empty
    means the link is legal."""
    fails = []
    if INTAKE_QUERY_KEY + "=" not in link:
        fails.append(("stage-form",
                      "stage-form link has no %s query param (G3 key law)"
                      % INTAKE_QUERY_KEY))
    if ACTIVE_ANTHOLOGY_MERGE not in link:
        fails.append(("stage-form",
                      "stage-form link does not prefill the anthology_id "
                      "from the contact's own active-anthology merge "
                      + ACTIVE_ANTHOLOGY_MERGE + " (never a concrete id)"))
    if STAGE_QUERY_KEY + "=" + stage not in link:
        fails.append(("stage-form",
                      "stage-form link has no %s=%s query param"
                      % (STAGE_QUERY_KEY, stage)))
    if "anthology_active_id=" in link:
        fails.append(("stage-form",
                      "the query key must be EXACTLY 'anthology_id', never "
                      "'anthology_active_id' (the G3 law)"))
    return fails

def never_a_real_token(text):
    """The never-a-real-token rule over generated template text. Returns a
    violation detail, or None when the text is clean. The template family
    carries the hook URL and Authorization header ONLY as the REPLACE-ME
    location custom-value merges; a real-looking URL or a
    credential-shaped value anywhere is a REFUSAL."""
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
# The rules payload (pure data generation — OFFLINE, no state, no wire).
# This is the JSON/Python data-generator face of the module: the copy rules
# as DATA for the sibling template generators, the operator surface, and the
# caf build rail. Nothing here is live; nothing here writes anywhere.
# --------------------------------------------------------------------------- #
def rules_payload():
    """The copy rules as a data object (the Python face of the generator):
    the copy law with its sanctioned word, banned words, banned character,
    producer merges, standing instruction, sign-off law, warm-language law,
    the two-link law with its deliverable stage keys, the stage-form link
    law, and the never-a-real-token merges. PURE and OFFLINE — returns
    plain dict/list data only; the caller decides how to consume it."""
    return {
        "copy_law": {
            "editors_never_ai": {
                "sanctioned_word": SANCTIONED_WORD,
                "banned_words": list(BANNED_WORDS),
                "note": COPY_LAW["editors_never_ai"]["note"],
            },
            "no_em_dashes": {
                "banned_character": "U+2014 em-dash",
                "note": COPY_LAW["no_em_dashes"]["note"],
            },
            "producer_name_merge": PRODUCER_MERGE,
            "email_from_name_merge": FROM_NAME_MERGE,
            "sms_shape": SMS_SHAPE,
            "standing_instruction": STANDING_INSTRUCTION,
            "sign_off": SIGN_OFF,
            "sanctioned_signoffs": list(SANCTIONED_SIGNOFFS),
            "warm_language": {
                "greeting_merge": GREETING_MERGE,
                "warm_close": WARM_CLOSE,
                "note": COPY_LAW["warm_language"]["note"],
            },
        },
        "two_link_law": {
            "note": COPY_LAW["per_stage_links"]["note"],
            "stage_keys": list(DELIVERABLE_STAGE_KEYS),
            "pdf_view": "PDF (VIEW) link, from the stage's deliverable "
                        "field pdf_url",
            "doc_edit": "editable Google Doc (EDIT) link, from the stage's "
                        "deliverable field doc_url",
        },
        "stage_form_link": {
            "query_keys": [INTAKE_QUERY_KEY, STAGE_QUERY_KEY],
            "prefilled_from": ACTIVE_ANTHOLOGY_MERGE,
            "law": "G3: the query key is EXACTLY 'anthology_id', never "
                   "'anthology_active_id'; the stage token is the stage "
                   "runner's own STAGE constant",
            "example": stage_form_link("s8"),
        },
        "never_a_real_token": {
            "webhook_url_merge": WEBHOOK_URL_MERGE,
            "hook_secret_merge": HOOK_SECRET_MERGE,
        },
        "platform": _PLATFORM,
        "note": "offline copy rules only (synthetic merges, no network, no "
                "credential needed); the sibling template modules import "
                "these constants and deny machinery BY NAME",
    }

def render_payload():
    """The JSON face of the generator: rules_payload() as an indented,
    key-sorted JSON document. PURE and OFFLINE."""
    return json.dumps(rules_payload(), indent=2, sort_keys=True)

# --------------------------------------------------------------------------- #
# Offline self-test (no network, no credentials) — proves the rules payload
# against the copy law. Every law is asserted on the GENERATED payload, so a
# drift in the copy, the links, or the never-a-real-token rule is caught
# here, never downstream. The contract and field map are read lazily (the
# self-test is the ONLY path that touches disk).
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

def _contract_copy_law(contract):
    """The contract's workflows.copy_law block, or None."""
    return ((contract.get("workflows") or {}).get("copy_law") or None)

def _declared_link_keys(field_map):
    """The bare link keys declared in field-map.json deliverable_fields,
    resolved exactly as copy_qc_workflows.py resolves them (the map's
    declared values' field keys, stripped of the "contact." prefix)."""
    declared = set()
    for row in (field_map.get("deliverable_fields") or {}).values():
        for value in (row or {}).values():
            if isinstance(value, str):
                declared.add(value.replace("contact.", "", 1))
    return declared

def _chapter_pair_merges(field_map):
    """The chapter group's declared doc_url and pdf_url values as
    whitespace-spaced merges, exactly as the template bodies carry them
    ({{ contact.anthology_chapter_pdf_url }} / doc_url), or (None, None)
    when the chapter group is missing or incomplete. The MAP is the
    authority — the template's chapter merges must be byte-equal to what
    the map declares for the chapter group, never constructed."""
    group = (field_map.get("deliverable_fields") or {}).get("chapter") or {}
    doc = group.get("doc_url")
    pdf = group.get("pdf_url")
    if not isinstance(doc, str) or not isinstance(pdf, str):
        return None, None
    return "{{ " + pdf + " }}", "{{ " + doc + " }}"

def self_test(out=None) -> int:
    """The offline self-test battery. Returns EX_OK on a full pass, EX_STOP
    when the contract is unreadable/malformed, EX_VIOLATION on any law
    drift (never 'unexpected error')."""
    out = out or sys.stderr
    try:
        contract, field_map = _load_contracts()
    except ValueError as exc:
        out.write("[copy-rules] STOP: %s\n" % exc)
        return EX_STOP

    fails = []

    # (1) contract law: workflows.copy_law must exist and carry the
    # byte-exact constants this module is the canonical source of. A
    # drift on either side is a located FAIL, never a blind audit.
    law = _contract_copy_law(contract)
    if law is None:
        fails.append(("contract",
                      "contract workflows.copy_law is missing"))
    else:
        if law.get("editors_never_ai") is not True:
            fails.append(("contract",
                          "contract copy_law editors_never_ai is not true"))
        if law.get("no_em_dashes") is not True:
            fails.append(("contract",
                          "contract copy_law no_em_dashes is not true"))
        if law.get("producer_name_merge") != PRODUCER_MERGE:
            fails.append(("contract",
                          "contract copy_law producer_name_merge %r != %r"
                          % (law.get("producer_name_merge"), PRODUCER_MERGE)))
        if law.get("email_from_name_merge") != FROM_NAME_MERGE:
            fails.append(("contract",
                          "contract copy_law email_from_name_merge %r != %r"
                          % (law.get("email_from_name_merge"),
                             FROM_NAME_MERGE)))
        if law.get("sms_shape") != SMS_SHAPE:
            fails.append(("contract",
                          "contract copy_law sms_shape %r != %r"
                          % (law.get("sms_shape"), SMS_SHAPE)))
        if law.get("standing_instruction") != STANDING_INSTRUCTION:
            fails.append(("contract",
                          "contract copy_law standing_instruction drifts "
                          "from the canonical constant"))

    # (2) two-link law over the field map: every deliverable stage key must
    # be declared as a group carrying BOTH its pdf_url and doc_url fields
    # (the copy_qc_workflows.py AF-AE-COPY-FIELD-DRIFT law — a renamed key
    # on either side is a located FAIL, never a blind audit). The MAP is
    # the authority: group membership is asserted against the canonical
    # stage keys, each group must carry its two-link pair, and the
    # template's chapter merges are checked byte-equal to the map's own
    # chapter values — never constructed.
    declared = _declared_link_keys(field_map)
    map_groups = (field_map.get("deliverable_fields") or {})
    for stage in DELIVERABLE_STAGE_KEYS:
        group = map_groups.get(stage)
        if group is None:
            fails.append(("field-map",
                          "deliverable stage %r is not declared in "
                          "field-map deliverable_fields" % stage))
            continue
        if not isinstance(group.get("doc_url"), str) or \
                not isinstance(group.get("pdf_url"), str):
            fails.append(("field-map",
                          "deliverable stage %r must carry BOTH doc_url and "
                          "pdf_url fields (the two-link law)" % stage))
        for bare in (str(group.get("pdf_url", "")).replace("contact.", "", 1),
                     str(group.get("doc_url", "")).replace("contact.", "", 1)):
            if bare and bare not in declared:
                fails.append(("field-map",
                              "link field %s is not declared in field-map "
                              "deliverable_fields (drift)" % bare))
    map_pdf, map_doc = _chapter_pair_merges(field_map)
    if map_pdf is None or map_doc is None:
        fails.append(("field-map",
                      "field-map chapter group is missing or incomplete "
                      "(the template's PDF and Doc merges cannot be "
                      "verified against the map)"))
    else:
        if map_pdf != CHAPTER_PDF_MERGE:
            fails.append(("field-map",
                          "the template's chapter PDF merge %s is not the "
                          "field-map's own declared value %s (drift)"
                          % (CHAPTER_PDF_MERGE, map_pdf)))
        if map_doc != CHAPTER_DOC_MERGE:
            fails.append(("field-map",
                          "the template's chapter Doc merge %s is not the "
                          "field-map's own declared value %s (drift)"
                          % (CHAPTER_DOC_MERGE, map_doc)))

    # (3) copy law over the generated rules payload: the sanctioned word,
    # zero banned words, zero em-dashes, both producer merges, the standing
    # instruction, the sanctioned sign-off, and the warm-language pair.
    # The canonical email body is built from the field-map's OWN declared
    # chapter pair, so the copy law and the two-link law are proven on the
    # same text the map authorizes.
    payload = rules_payload()
    map_pdf, map_doc = _chapter_pair_merges(field_map)
    if map_pdf is None or map_doc is None:
        map_pdf, map_doc = CHAPTER_PDF_MERGE, CHAPTER_DOC_MERGE
    body_text = ("Dear " + GREETING_MERGE + ",\n\n"
                 "Your chapter is ready. Our " + SANCTIONED_WORD
                 + " have reviewed it, and we are happy with it.\n\n"
                 + STANDING_INSTRUCTION + "\n\n"
                 + "View your PDF here:\n" + map_pdf + "\n\n"
                 + "Edit your Google Doc here:\n" + map_doc + "\n\n"
                 + WARM_CLOSE + ",\n" + SIGN_OFF)
    sms_text = ("Your chapter is ready to review here: " + map_pdf)
    from_name_merge = payload["copy_law"]["email_from_name_merge"]
    copy_fails = copy_check(body_text, sms_text, from_name_merge)
    for check, detail in copy_fails:
        fails.append(("copy-%s" % check, detail))

    # (4) the two-link law over the canonical email body: the PDF (VIEW)
    # link AND the editable Google Doc (EDIT) link are both present.
    pair_fails = two_link_check(body_text, map_pdf, map_doc)
    for check, detail in pair_fails:
        fails.append(("copy-%s" % check, detail))

    # (5) the stage-form link law: the built link carries the anthology_id
    # query param prefilled from the contact's own active-anthology merge
    # (G3 key law, never a concrete id) and the stage query param prefilled
    # with the stage token.
    stage = "s8"
    link = payload["stage_form_link"]["example"]
    if link != stage_form_link(stage):
        fails.append(("stage-form",
                      "the payload example link drifts from "
                      "stage_form_link(%r)" % stage))
    form_fails = stage_form_check(link, stage)
    for check, detail in form_fails:
        fails.append(("copy-%s" % check, detail))

    # (6) the never-a-real-token law over the whole rendered payload.
    rendered = render_payload()
    token_detail = never_a_real_token(rendered)
    if token_detail is not None:
        fails.append(("never-a-real-token", token_detail))

    # (7) the sign-off law: every sanctioned sign-off is one of the two
    # allowed forms ("The Editors" or the producer-name merge), and the
    # payload carries both forms.
    for signoff in payload["copy_law"]["sanctioned_signoffs"]:
        if signoff not in SANCTIONED_SIGNOFFS:
            fails.append(("sign-off",
                          "sanctioned sign-off %r is not one of the two "
                          "allowed forms" % signoff))
    if SIGN_OFF not in payload["copy_law"]["sign_off"]:
        fails.append(("sign-off",
                      "payload sign_off drifts from 'The Editors'"))

    if fails:
        for check, detail in fails:
            out.write("[copy-rules] %s: %s\n" % (check, detail))
        out.write("[copy-rules] self-test FAILED "
                  "(%d violation%s)\n" % (len(fails),
                                          "" if len(fails) == 1 else "s"))
        return EX_VIOLATION
    out.write("[copy-rules] self-test PASS: the copy law holds (contract "
              "row, field-map two-link law, editors never the banned words, "
              "zero em-dashes, producer merges, standing instruction, "
              "sanctioned sign-off, warm language, stage-form link, "
              "never-a-real-token)\n")
    return EX_OK

# --------------------------------------------------------------------------- #
# CLI (the ONE entry point; every command is OFFLINE).
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="copy_rules.py",
        description="The canonical copy-law constants and deny machinery "
                    "for the U10-U13 release-notification template family "
                    "(OFFLINE: no network, no credential).")
    ap.add_argument("cmd", nargs="?", choices=["plan", "render", "self-test"],
                    help="plan | render | self-test")
    args = ap.parse_args(argv)

    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "render":
        # The copy rules as one JSON document (offline, no token).
        print(render_payload())
        return EX_OK
    # plan: the offline plan — the copy law with its sources.
    print(json.dumps({
        "contract": "workflows.copy_law",
        "copy_law": {
            "editors_never_ai": {
                "sanctioned_word": SANCTIONED_WORD,
                "banned_words": list(BANNED_WORDS),
            },
            "no_em_dashes": "zero U+2014 em-dash characters in any "
                            "client-facing word",
            "producer_name_merge": PRODUCER_MERGE,
            "email_from_name_merge": FROM_NAME_MERGE,
            "sms_shape": SMS_SHAPE,
            "standing_instruction": STANDING_INSTRUCTION,
            "sign_off": SIGN_OFF,
            "sanctioned_signoffs": list(SANCTIONED_SIGNOFFS),
            "warm_language": {
                "greeting_merge": GREETING_MERGE,
                "warm_close": WARM_CLOSE,
            },
        },
        "two_link_law": {
            "note": "each email carries that stage's PDF (VIEW) link plus "
                    "editable Google Doc (EDIT) link from field-map.json "
                    "deliverable_fields",
            "stage_keys": list(DELIVERABLE_STAGE_KEYS),
        },
        "stage_form_link": {
            "shape": "<forms_base>/widget/form/<form_id>?"
                     + INTAKE_QUERY_KEY + "=<active>&"
                     + STAGE_QUERY_KEY + "=<stage>",
            "example": stage_form_link("s8"),
            "law": "G3: the query key is EXACTLY 'anthology_id', never "
                   "'anthology_active_id'; stage prefilled from the stage "
                   "runner's own STAGE constant",
        },
        "never_a_real_token": {
            "webhook_url": WEBHOOK_URL_MERGE,
            "hook_secret": HOOK_SECRET_MERGE,
        },
        "note": "offline plan only (synthetic merges, no network, no "
                "credential needed); the sibling template modules import "
                "these constants and deny machinery BY NAME",
    }, indent=2, sort_keys=True))
    return EX_OK

if __name__ == "__main__":
    sys.exit(main())
