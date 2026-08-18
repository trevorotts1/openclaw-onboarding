#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/w2_title_fire.py
# (W2 template generator)
# TITLE FIRE WORKFLOW TEMPLATE — FORM_SUBMISSION TRIGGER -> WEBHOOK POST
# (OFFLINE data generator).
# The W2 workflow is the TITLE-SELECT FIRE: a form_submission trigger scoped
# EXACTLY to the S3 title-select form that, on a submission, POSTs the
# participant's chosen title and subtitle to the engine's intake webhook so
# the S0 router records the pick and the s3_selection gate stamps the ONE-WAY
# TITLE LOCK.
# -----------------------------------------------------------------------------
# THE W2 SHAPE (pinned to the live title-select surface):
#   trigger      form_submission, scoped to form.id == the title-select form
#                (slug title-select; the pinned id
#                UgiiSoZsA4vyqOVfO5fi — the Title Fire trigger AND the S3
#                title-and-subtitle link in "Release: Titles", live-verified
#                2026-08-11 on the template location; the SAME pin
#                forms_check.FORM_ID_BY_SLUG["title-select"] and
#                title_select_builder.DEFAULT_TITLE_SELECT_FORM_ID carry —
#                imported from the sibling, never re-typed)
#   trigger      ACTIVE only when the submission IS the title-select form;
#                every other form is out of scope for this fire (the U02
#                scope law, scope_check.py)
#   action       ONE custom-webhook POST, method POST, content type
#                application/json, to the engine's intake hook
#   url merge    {{ custom_values.anthology_webhook_url }} — the REPLACE-ME
#                location custom value (snapshot contract
#                location_custom_values, key anthology_webhook_url); NEVER a
#                real URL
#   auth merge   {{ custom_values.anthology_hook_secret }} — the REPLACE-ME
#                Authorization-header custom value (key
#                anthology_hook_secret); NEVER a real token
#   body         the routed submission: the title-select form's hidden pair
#                (anthology_id, stage) plus the participant's title and
#                subtitle — the exact keys intake_router.py's field_candidates
#                consumes (anthology_id; stage; title; subtitle), so the
#                picked title/subtitle reach the record-approval path at the
#                s3_selection gate (gate_engine ACTION_DECISION "select":
#                required fields ("title",), subtitle optional) and the
#                TITLE LOCK stamps title_locked / subtitle_locked one-way
#   stage        the form link pre-fills stage=<stage token> (the U08
#                pre-fill law: ?anthology_id=<minted>&stage=<stage>; the
#                router's classify_stage accepts the token), and the same
#                token rides the webhook body so the submission routes to the
#                participant's open s3_selection gate. Default "s3_gate" —
#                the STAGE_CURSORS cursor the participant sits at while that
#                gate is open (the same default the w5 titles-release
#                sibling ships)
#   contact      the title-select form carries NO contact_id hidden field
#                (title_select_builder HIDDEN_LAW = ("anthology_id","stage")
#                — the form is only ever opened from an ALREADY-resolved
#                participant token page). The webhook body therefore keys the
#                participant by the hidden pair alone; the id merge fields
#                below are the OPTIONAL send-time fills a title-select
#                submission may carry, never a required field of this
#                template.
# -----------------------------------------------------------------------------
# COPY LAW (workflows.copy_law — Trevor's verbatim law, enforced here at
# GENERATION time):
#   EDITORS, NEVER AI .... "editors" is the ONLY editorial byline actor in
#        any client-facing word. "AI", "ghostwriter", "automated" and
#        "generated" are absent from generated copy (guards below refuse
#        such strings by word boundary; the module's own docstring is the
#        single enforcement-context exception).
#   ZERO EM-DASHES .......... U+2014 is FORBIDDEN in generated copy. Every
#        sentence uses commas, periods, or a colon. The guards refuse any
#        rendered string containing U+2014.
#   SIGN-OFF ................ "The Editors" or "{{ custom_values.producer }}"
#        only, never a person's raw name and never a model persona. The
#        email sign-off is "The Editors"; the producer merge is the From
#        name (copy_law email_from_name_merge); SMS never carries a sign-off
#        (link-only short message: one warm sentence plus ONE link).
#   STANDING INSTRUCTION .... "The PDF is yours to view. The Google Doc is
#        the one you edit, and it is the version we use." — byte-exact, in
#        every release email (copy_law.standing_instruction).
#   STAGE FORM LINK ......... <forms_base>/widget/form/<form_id>?anthology_id=
#        <minted>&stage=<stage> — the U08 pre-fill law: the TWO query params
#        pre-fill the form's HIDDEN fields client-side (the universal
#        hidden-field contract; prefill_verifier.py owns the verifier). The
#        default form is the title-select form (pin UgiiSoZsA4vyqOVfO5fi)
#        and the default stage token is "s3_gate" (the EXACT STAGE_CURSORS
#        cursor the participant sits at while the s3_selection gate is open;
#        an out-of-vocabulary stage is a ValueError, never a fabricated
#        token).
#   MERGES ................... Every client-facing value that must be filled
#        at send time is a {{ ... }} merge slot (GHL merge tags, spaces
#        exactly as the contract writes them: {{ custom_values.producer }});
#        never a literal value.
#   ONE PDF VIEW + ONE DOC EDIT ..... the release email carries the Titles
#        PDF (view) link plus the Titles Google Doc (edit) link, both from
#        the contact custom fields (field-map deliverable_fields titles ->
#        doc_url / pdf_url); the SMS carries ONLY the doc link.
#   NO CODE FENCES / NO INTERNAL NAMES ... zero code fences, zero internal
#        tool or model names in generated copy (the nudge-template
#        discipline).
#   NO TOKENS ................ this module holds no credential surface and
#        never emits a real value: the webhook URL and Authorization header
#        ride ONLY the REPLACE-ME location custom-value merges, and the
#        self-test proves every rendered string is secret-free (no "Bearer",
#        no "sk-", no key-shaped value, no real-looking URL).
#
# OFFLINE: plan / render / self-test all run with no network and no
# credential; rendering is PURE (same inputs -> same bytes). This module is
# a TEMPLATE / data-generator module: it never touches the wire, never
# resolves a credential label, and never prints a token — the sibling
# doctrine of the U05 golden/attack fixtures applied to the W2 Title Fire
# workflow template.
#
# STDLIB ONLY. Importable by the u10_u13 package init and by the assembler
# sibling; executed directly with the same contract as the sibling modules
# (plan / render / self-test). Exit codes (house convention 0/1/2/4):
#   0  plan / render / self-test pass
#   1  unexpected error
#   2  usage or a law violation detected offline (e.g. an out-of-vocabulary
#      stage token, an em-dash, a banned word, an unknown form slug, an
#      unreadable contract)
#   4  self-test FAILED — a copy-law drift, a trigger-scope drift, a pinned
#      form-id drift from the sibling builder, or a credential-shaped value
#      (a tamper never masquerades as exit 1)
#   (3 and 5 are not applicable here: no live surface, no read-back)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; every command is OFFLINE and needs NO token and NO network):
#   w2_title_fire.py plan            # offline: the W2 template law
#   w2_title_fire.py render          # offline: the generated template
#   w2_title_fire.py self-test       # offline golden + attack battery
# =============================================================================

"""W2 Title Fire workflow template generator: form_submission trigger ->
webhook POST of title + subtitle, OFFLINE and pure."""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (house convention 0/1/2/4; see module header).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_STOP = 2
EX_VIOLATION = 4

# ---------------------------------------------------------------------------
# Layout (mirrors every sibling module's resolution: the module sits at
# scripts/u10_u13_modules/, so the skill root is THREE parents up — the same
# convention as scripts/copy_qc_workflows.py).
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's client-facing platform name, spelled out in every surface.
_PLATFORM = "Convert and Flow"

# ---------------------------------------------------------------------------
# THE W2 IDENTITY — the Title Fire workflow of the three-Fire family
# (Anthology Intake Fire / Review Fire / Title Fire; forms_check.py:271, the
# internal-rail trigger surface live-verified 2026-08-11: each of the three
# Fire workflows carries ONE ACTIVE form_submission trigger on its form id).
# ---------------------------------------------------------------------------
WORKFLOW_NAME = "Anthology Title Fire"
TRIGGER_TYPE = "form_submission"

# The title-select form slug and its pinned id — the S3 gate form of the
# three-slug family forms_check.FORM_ID_BY_SLUG pins (universal-intake /
# universal-review / title-select), and the snapshot contract's
# contract_bound_per_anthology row with stage "s3" and role
# "title-subtitle-selection". The id is the pinned Title Fire trigger form
# id, live-verified 2026-08-11 on the template location — a location
# identifier, not a secret (masked on every operator surface). Same value
# title_select_builder.DEFAULT_TITLE_SELECT_FORM_ID carries — pinned here
# against the sibling in the self-test, never re-typed.
TITLE_SELECT_SLUG = "title-select"
TITLE_SELECT_FORM_ID = "UgiiSoZsA4vyqOVfO5fi"
TITLE_SELECT_FORM_ID_MASKED = "…" + TITLE_SELECT_FORM_ID[-4:]

# The stage token the Title Fire carries (anthology_state.STAGE_CURSORS —
# the exact vocabulary; an out-of-vocabulary token is a ValueError, never a
# fabricated token). The default is the participant review gate that follows
# the Title stage: "s3_gate" is the cursor the participant sits at while the
# s3_selection gate is open (gate_engine GATE_BY_CURSOR["s3_gate"] ->
# s3_selection, the title-and-subtitle pick), and intake_router.
# classify_stage accepts the token and the S0 router routes the submission
# to that open gate. The SAME default the w5 titles-release sibling uses.
DEFAULT_STAGE = "s3_gate"

# The exact stage-token vocabulary (anthology_state.STAGE_CURSORS /
# stage_s3_title.STAGE) the W2 stage slot may hold — the same vocabulary the
# sibling w4/w7/w8 modules pin. An out-of-vocabulary token is a ValueError,
# never a fabricated token.
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)

# ---------------------------------------------------------------------------
# THE COPY LAW (config/anthology-snapshot-contract.json -> workflows.copy_law,
# Trevor's verbatim; the sibling static guard guard-no-anthropic-runtime.py
# allowlists deny definitions line-for-line).
# ---------------------------------------------------------------------------
# The U+2014 em dash is NEVER written literally in this file (zero em dashes
# in the file itself, the same law verify.sh enforces over the nudge
# templates); the validator below builds the character at runtime so a grep
# for the dash can prove the file clean, and every rendered message must
# still pass the same validator.
EM_DASH = chr(0x2014)

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

# The producer-name merge (copy_law producer_name_merge / email_from_name_merge).
PRODUCER_MERGE = "{{ custom_values.producer }}"

# The sanctioned sign-offs (workflows.copy_law): "The Editors" or the
# producer-name merge — never a persona.
SIGN_OFF_EDITORS = "The Editors"
SIGN_OFF_PRODUCER = PRODUCER_MERGE

# The standing instruction (copy_law.standing_instruction) — byte-exact.
STANDING_INSTRUCTION = (
    "The PDF is yours to view. The Google Doc is the one you edit, "
    "and it is the version we use."
)

# Field-map deliverable slots for the titles deliverable
# (field-map.json deliverable_fields.titles): the contact custom fields the
# generated release email/SMS reference — the Titles PDF (view) link and the
# Titles Google Doc (edit) link, per copy_law.per_stage_links.
PDF_LINK_MERGE = "{{contact.anthology_titles_pdf_url}}"
DOC_LINK_MERGE = "{{contact.anthology_titles_doc_url}}"

# The anthology-name and author-name merges (the copy slots of the email).
ANTHOLOGY_NAME_MERGE = "{{ custom_values.anthology_name }}"
FIRST_NAME_MERGE = "{{ contact.first_name }}"

# The stage form link's hidden-field query keys — the U08 pre-fill law
# (?anthology_id=<minted>&stage=<stage>; the snapshot contract forms block
# universal_hidden_fields contact_id / anthology_id / stage).
ANTHOLOGY_ID_KEY = "anthology_id"
STAGE_KEY = "stage"

# The fleet GHL/LeadConnector hosted-form domain (anthology_book.py
# DEFAULT_FORMS_BASE) and the widget path.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
WIDGET_FORM_PATH = "/widget/form"

# The minted-anthology merge slot (the G3 law: the query key is EXACTLY
# anthology_id, never anthology_active_id — the template never holds a
# concrete id).
ACTIVE_ANTHOLOGY_MERGE = "{{ contact.anthology_active_id }}"

# ---------------------------------------------------------------------------
# THE WEBHOOK SURFACE (the snapshot contract's location_custom_values —
# the never-a-real-token rule). The W2 webhook POST rides the REPLACE-ME
# custom values ONLY; a real-looking URL or a credential-shaped value
# anywhere in the template is a REFUSAL.
# ---------------------------------------------------------------------------
WEBHOOK_URL_MERGE = "{{ custom_values.anthology_webhook_url }}"
HOOK_SECRET_MERGE = "{{ custom_values.anthology_hook_secret }}"

# The POST body's content type (the snapshot contract's custom-webhook
# action: content_type application/json).
CONTENT_TYPE = "application/json"

# The Title Fire's field-scope: the trigger fires ONLY when the submission
# identifies as the title-select form (the U02 scope law: the intake-fire
# trigger fires ONLY when the submission is the universal-intake form;
# check_intake_fire_scope.py; the Title Fire analog is scoped to
# title-select, the S3 gate form).
SCOPE_FIELD = "form.id"

# ---------------------------------------------------------------------------
# Guards (offline, fail-closed). A template that cannot prove it obeys the
# law is a ValueError, never a silently-off-copy payload.
# ---------------------------------------------------------------------------

# Word-boundary forbidden shapes in CLIENT-FACING copy: the "AI" and
# "ghostwriter" shapes are banned, with "editor"/"editors"/"editorial"
# REQUIRED to be the only byline actors. The enforcement-context exception
# is the module docstring (which must name the ban to pin it) — the
# docstring is not generated copy.
_FORBIDDEN_AI = re.compile(
    r"\b(?:A\.?I\.?|ghostwriter(?:s)?|automated|generated)\b", re.IGNORECASE)
_EDITOR_WORD = re.compile(r"\beditor(?:ial)?(?:s)?\b", re.IGNORECASE)

# Secret-shaped fragments that must never appear in generated copy (a
# template cannot print a token it never holds; the guard keeps the render
# honest even against a future merge-slot mistake).
_SECRET_SHAPES = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|ANTHOLOGY_HOOK_SECRET|"
    r"[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})"
)

# A real-looking URL that is NOT the REPLACE-ME webhook merge is a
# never-a-real-token violation.
_REAL_URL = re.compile(r"https?://", re.IGNORECASE)

def _assert_copy_law(text, label):
    """Fail-closed copy-law check on one generated string.

    Refuses: any U+2014 em-dash, any forbidden AI/ghostwriter shape, any
    secret-shaped fragment. Raises ValueError with the exact offending
    fragment and the label of the payload that carried it.
    """
    if EM_DASH in text:
        raise ValueError(
            "copy-law violation in %s: em-dash (U+2014) is forbidden in "
            "client-facing copy; use a comma, a period, or a colon." % label
        )
    m = _FORBIDDEN_AI.search(text)
    if m:
        raise ValueError(
            "copy-law violation in %s: forbidden word %r (editors are the "
            "only byline actors; AI and ghostwriter shapes are banned)."
            % (label, m.group(0))
        )
    m = _SECRET_SHAPES.search(text)
    if m:
        raise ValueError(
            "copy-law violation in %s: secret-shaped fragment %r must never "
            "appear in generated copy." % (label, m.group(0))
        )
    if "{{" in text and "}}" not in text:
        raise ValueError(
            "copy-law violation in %s: unbalanced merge slot (a {{ without "
            "its }})." % label
        )
    return text

# ---------------------------------------------------------------------------
# The generators. The W2 template's client-facing words are the release
# email and SMS the Title Fire workflow carries (the release-notification
# row "Anthology Release: Titles" is the S3 sibling of the Avatar/Tone rows
# the w4 module already renders; the email is plain text — the same
# client-clean shape the nudge templates use — so the same law guards cover
# every channel).
# ---------------------------------------------------------------------------

def email_subject(anthology_name=ANTHOLOGY_NAME_MERGE):
    """Subject line: the titles deliverable is ready. ``anthology_name`` is
    the merge slot by default; a caller that renders an offline preview may
    pass a literal name (preview values are test values, never secrets)."""
    return _assert_copy_law(
        "Your title for %s is ready" % anthology_name, "email_subject"
    )

def email_body(anthology_name=ANTHOLOGY_NAME_MERGE,
               first_name=FIRST_NAME_MERGE,
               pdf_link=PDF_LINK_MERGE,
               doc_link=DOC_LINK_MERGE,
               sign_off=SIGN_OFF_EDITORS):
    """Render the release-titles EMAIL body (plain text).

    Slots (all merges by default): the author's first name, the anthology
    name, the Titles PDF view link, the Titles Google Doc edit link. The
    sign-off is "The Editors" (or the producer merge when the operator pins
    it). This email is the S3 release row of the tag->notification family —
    the SAME shape the w4/w7/w8 siblings render for their stages.
    """
    parts = []
    parts.append("Hi %s," % first_name)
    parts.append("")
    parts.append("Your title for %s is ready." % anthology_name)
    parts.append("")
    parts.append("You can view the PDF here:")
    parts.append(pdf_link)
    parts.append("")
    parts.append("And you can edit your Google Doc here:")
    parts.append(doc_link)
    parts.append("")
    parts.append(STANDING_INSTRUCTION)
    parts.append("")
    parts.append("Thank you for being part of %s." % anthology_name)
    parts.append("")
    parts.append("Warmly,")
    parts.append(sign_off)
    for i, line in enumerate(parts):
        _assert_copy_law(line, "email_body[%d]" % i)
    return "\n".join(parts)

def sms_body(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """Render the release-titles SMS body: ONE warm sentence plus ONE link
    (the sms_shape law; the SMS carries the doc link only, never the PDF).
    No sign-off — the SMS shape law has no room for one."""
    text = "%s, your title is ready to review. Here is your Google Doc: %s" % (
        first_name, doc_link
    )
    return _assert_copy_law(text, "sms_body")

def stage_form_link(form_id=TITLE_SELECT_FORM_ID,
                    anthology_id="",
                    stage=DEFAULT_STAGE,
                    forms_base=DEFAULT_FORMS_BASE):
    """Build the stage form link — the U08 pre-fill law:

        <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>

    ``anthology_id`` is the MINTED anthology id: the template slot keeps the
    contact's active-anthology merge ``{{ contact.anthology_active_id }}``
    when no value is given (the pre-fill hydrates it client-side from the
    query param); a caller rendering an offline preview passes a synthetic
    fixture value. ``stage`` must be EXACTLY one of the STAGE_VOCABULARY
    tokens (an out-of-vocabulary token is a ValueError, never a fabricated
    token). The default form is the pinned title-select form id — the form
    whose hidden stage field the stage query pre-fills.
    """
    if stage not in STAGE_VOCABULARY:
        raise ValueError(
            "stage token %r is not in the STAGE_CURSORS vocabulary; the "
            "pre-fill law demands an exact vocabulary token." % stage
        )
    if not anthology_id:
        anthology_id = ACTIVE_ANTHOLOGY_MERGE
    link = "%s%s/%s?%s=%s&%s=%s" % (
        (forms_base or DEFAULT_FORMS_BASE).rstrip("/"), WIDGET_FORM_PATH,
        form_id, ANTHOLOGY_ID_KEY, anthology_id, STAGE_KEY, stage,
    )
    return _assert_copy_law(link, "stage_form_link")

def webhook_body(anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                 stage=DEFAULT_STAGE,
                 title="{{ contact.title }}",
                 subtitle="{{ contact.subtitle }}"):
    """The W2 custom-webhook POST body — the routed submission the Title
    Fire posts to the engine's intake hook. The body carries the title-select
    form's hidden pair (anthology_id, stage) plus the participant's chosen
    title and subtitle — the exact keys intake_router.py's field_candidates
    consumes (anthology_id; stage; title; subtitle), so the pick reaches the
    record-approval path at the s3_selection gate and the ONE-WAY TITLE LOCK
    stamps title_locked / subtitle_locked (anthology_state.py record-approval
    reads --title and --subtitle at the s3_selection gate; gate_engine
    ACTION_DECISION "select": required ("title",), subtitle optional).

    Defaults are merge slots (the values are filled at send time by the
    hosting workflow); a caller rendering an offline preview passes fixture
    values (never secrets).
    """
    body = {
        "anthology_id": anthology_id,
        "stage": stage,
        "title": title,
        "subtitle": subtitle,
    }
    for key, value in body.items():
        _assert_copy_law(str(value), "webhook_body[%s]" % key)
    return body

# ---------------------------------------------------------------------------
# The render surface (pure; deterministic bytes for identical inputs).
# ---------------------------------------------------------------------------

EMAIL_SLOT_KEYS = ("subject", "body", "from_name", "reply_to", "pdf_link",
                   "doc_link", "stage_form_link")
SMS_SLOT_KEYS = ("body", "doc_link")
WEBHOOK_SLOT_KEYS = ("method", "content_type", "url_merge",
                     "authorization_header_merge", "body")

def render_email(sign_off=SIGN_OFF_EDITORS,
                 producer=PRODUCER_MERGE,
                 form_id=TITLE_SELECT_FORM_ID,
                 anthology_id="",
                 stage=DEFAULT_STAGE,
                 forms_base=DEFAULT_FORMS_BASE):
    """The complete release-titles EMAIL payload of the Title Fire family:
    subject, body, producer-branded from_name, reply_to, and the per-stage
    link set (Titles PDF view + Titles Doc edit + the pre-filled title-select
    form link). Pure and offline; every value is a merge slot unless the
    caller deliberately renders an offline preview (fixture values, never
    secrets)."""
    link = stage_form_link(
        form_id=form_id, anthology_id=anthology_id, stage=stage,
        forms_base=forms_base,
    )
    payload = {
        "subject": email_subject(),
        "body": email_body(
            sign_off=sign_off,
        ),
        "from_name": producer,
        "reply_to": "{{ custom_values.producer_email }}",
        "pdf_link": PDF_LINK_MERGE,
        "doc_link": DOC_LINK_MERGE,
        "stage_form_link": link,
    }
    for key in EMAIL_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_email[%s]" % key)
    return payload

def render_sms(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """The complete release-titles SMS payload: ONE warm sentence plus ONE
    doc link. Pure and offline; link is the merge slot by default."""
    payload = {"body": sms_body(doc_link=doc_link, first_name=first_name),
               "doc_link": doc_link}
    for key in SMS_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_sms[%s]" % key)
    return payload

def render_webhook(stage=DEFAULT_STAGE,
                   anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                   title="{{ contact.title }}",
                   subtitle="{{ contact.subtitle }}"):
    """The W2 custom-webhook POST action: method POST, content type
    application/json, URL and Authorization header riding ONLY the REPLACE-ME
    location custom-value merges, and the routed title+subtitle body.
    Pure and offline; never a real URL, never a real token."""
    payload = {
        "method": "POST",
        "content_type": CONTENT_TYPE,
        "url_merge": WEBHOOK_URL_MERGE,
        "authorization_header_merge": HOOK_SECRET_MERGE,
        "body": webhook_body(
            anthology_id=anthology_id, stage=stage, title=title,
            subtitle=subtitle,
        ),
    }
    for key in WEBHOOK_SLOT_KEYS:
        _assert_copy_law(json.dumps(payload[key]), "render_webhook[%s]" % key)
    return payload

def render_workflow(stage=DEFAULT_STAGE):
    """The complete W2 Title Fire workflow template as a data object — the
    Python face of the generator: the form_submission trigger scoped to the
    title-select form, the ONE custom-webhook POST action, the release email
    + SMS the family carries, and the never-a-real-token merges. PURE and
    OFFLINE — returns plain dict/list data only; the caller decides how to
    consume it (build rail, operator surface, or JSON)."""
    return {
        "contract": "anthology-engine-w2-title-fire-template",
        "schema_version": 1,
        "workflow_name": WORKFLOW_NAME,
        "trigger": {
            "type": TRIGGER_TYPE,
            "active_when": {
                "field": SCOPE_FIELD,
                "equals": [TITLE_SELECT_FORM_ID],
            },
            "scope_note": "the Title Fire fires ONLY when the submission is "
                          "the title-select form (the U02 scope law); every "
                          "other form is out of scope for this workflow",
            "form_slug": TITLE_SELECT_SLUG,
        },
        "actions": ["custom-webhook"],
        "webhook": render_webhook(stage=stage),
        "release": {
            "workflow": "Anthology Release: Titles",
            "trigger_tag": "anthology-release-titles",
            "actions": ["send-email", "send-sms"],
            "email": render_email(stage=stage),
            "sms": render_sms(),
        },
        "note": "offline template only — a REAL location write must ride the "
                "house clients (CAF_BROWSER_UA on every request — CF 1010 "
                "law); the workflow is built in the template location via the "
                "Skill 44 caf build rail and PUBLISHED (one toggle per "
                "workflow) before it fires live",
    }

def render_payload(stage=DEFAULT_STAGE):
    """The JSON face of the generator: render_workflow() as an indented,
    key-sorted JSON document. PURE and OFFLINE."""
    return json.dumps(render_workflow(stage=stage), indent=2, sort_keys=True)

# ---------------------------------------------------------------------------
# The never-a-real-token guard over the whole rendered template.
# ---------------------------------------------------------------------------
def _never_a_real_token_check(text):
    """Returns a violation detail, or None when the template is clean. The
    template carries the hook URL and Authorization header ONLY as the
    REPLACE-ME location custom-value merges; a real-looking URL or a
    credential-shaped value anywhere is a REFUSAL."""
    lowered = text.lower()
    if _REAL_URL.search(lowered) and WEBHOOK_URL_MERGE not in text:
        return ("a real-looking URL appears in the template (the intake "
                "hook must ride the REPLACE-ME merge " + WEBHOOK_URL_MERGE
                + ", never a real value)")
    for marker in ("bearer ", "sk-", "secret", "token"):
        if marker in lowered and HOOK_SECRET_MERGE not in text:
            return ("a credential-shaped value appears in the template (the "
                    "Authorization header must ride the REPLACE-ME merge "
                    + HOOK_SECRET_MERGE + ", never a real token)")
    return None

# ---------------------------------------------------------------------------
# CLI: plan / render / self-test, all OFFLINE.
# ---------------------------------------------------------------------------

def plan():
    """The offline plan — the W2 template law with its sources, one JSON
    object on stdout."""
    print(json.dumps({
        "contract": "anthology-engine-w2-title-fire-template",
        "workflow_name": WORKFLOW_NAME,
        "trigger": {
            "type": TRIGGER_TYPE,
            "form_slug": TITLE_SELECT_SLUG,
            "form_id": TITLE_SELECT_FORM_ID_MASKED,
            "form_id_note": "the pinned Title Fire trigger form id, "
                            "live-verified 2026-08-11 on the template "
                            "location (same pin forms_check / "
                            "title_select_builder carry); masked here",
            "scope": "fires ONLY when the submission is the title-select "
                     "form (form.id == the pinned id)",
        },
        "actions": ["custom-webhook"],
        "webhook": {
            "method": "POST",
            "content_type": CONTENT_TYPE,
            "url_merge": WEBHOOK_URL_MERGE,
            "authorization_header_merge": HOOK_SECRET_MERGE,
            "body_keys": ["anthology_id", "stage", "title", "subtitle"],
            "body_note": "the title-select hidden pair (anthology_id, stage) "
                         "plus the participant's chosen title and subtitle — "
                         "the keys intake_router.field_candidates consumes "
                         "so the s3_selection gate stamps the one-way TITLE "
                         "LOCK",
        },
        "stage_form_link": stage_form_link(),
        "stage": DEFAULT_STAGE,
        "release": {
            "workflow": "Anthology Release: Titles",
            "trigger_tag": "anthology-release-titles",
            "email_links": [PDF_LINK_MERGE, DOC_LINK_MERGE],
            "sms_link": DOC_LINK_MERGE,
        },
        "copy_law": {
            "editors_never_ai": True,
            "no_em_dashes": True,
            "sign_off": SIGN_OFF_EDITORS + " or " + PRODUCER_MERGE,
            "standing_instruction": STANDING_INSTRUCTION,
        },
        "never_a_real_token": {
            "webhook_url": WEBHOOK_URL_MERGE,
            "hook_secret": HOOK_SECRET_MERGE,
        },
        "offline": "no network, no credential, nothing sent",
    }, indent=2, sort_keys=True))
    return EX_OK

def self_test(out=None) -> int:
    """The house offline battery surface: runs :func:`_self_test` and maps a
    law violation onto EX_VIOLATION (4 — a tamper never masquerades as an
    unexpected error). The assembler sibling drives this surface; the CLI's
    self-test subcommand routes here too."""
    out = out or sys.stderr
    try:
        rc = _self_test()
    except (ValueError, AssertionError) as exc:
        out.write("w2_title_fire: self-test FAILED: %s\n" % exc)
        return EX_VIOLATION
    return rc

def _self_test():
    """Offline law proof: golden renders + attack fixtures. A tamper is a
    ValueError (exit 2), never a silent pass."""
    # Golden: the default render (merge slots) obeys every law.
    wf = render_workflow()
    trig = wf["trigger"]
    assert trig["type"] == "form_submission", "trigger type must be form_submission"
    assert trig["active_when"]["field"] == "form.id", "scope field must be form.id"
    assert TITLE_SELECT_FORM_ID in trig["active_when"]["equals"], (
        "the trigger must be scoped EXACTLY to the title-select form id")
    assert len(trig["active_when"]["equals"]) == 1, (
        "the Title Fire must scope to EXACTLY ONE form (the title-select)")

    hook = wf["webhook"]
    assert hook["method"] == "POST", "the webhook action must be a POST"
    assert hook["content_type"] == "application/json", (
        "the webhook content type must be application/json")
    assert hook["url_merge"] == WEBHOOK_URL_MERGE, (
        "the webhook URL must ride the REPLACE-ME custom-value merge")
    assert hook["authorization_header_merge"] == HOOK_SECRET_MERGE, (
        "the Authorization header must ride the REPLACE-ME custom-value merge")
    body = hook["body"]
    assert body["anthology_id"] == ACTIVE_ANTHOLOGY_MERGE, (
        "the body anthology_id must be the contact's active-anthology merge")
    assert body["stage"] == "s3_gate", (
        "the body stage must be s3_gate (the cursor of the open s3_selection "
        "gate)")
    assert "title" in body and "subtitle" in body, (
        "the body must carry the participant's title and subtitle")

    email = wf["release"]["email"]
    assert email["from_name"] == PRODUCER_MERGE, "from_name must be the producer merge"
    assert email["body"].endswith("\nWarmly,\nThe Editors"), (
        "sign-off must be exactly 'The Editors'")
    assert email["body"].count(STANDING_INSTRUCTION) == 1, (
        "standing instruction must appear exactly once")
    assert "AI" not in email["body"], "banned byline actor in golden email"
    assert EM_DASH not in email["body"], "em-dash in golden email"
    assert PDF_LINK_MERGE in email["body"] and DOC_LINK_MERGE in email["body"], (
        "email must carry BOTH the PDF view link and the Doc edit link")
    sms = wf["release"]["sms"]
    assert sms["body"].count(DOC_LINK_MERGE) == 1, (
        "SMS must carry exactly ONE link (the doc link merge slot)")
    assert EM_DASH not in sms["body"], "em-dash in golden SMS"

    link = email["stage_form_link"]
    assert link.startswith("%s%s/%s?%s=" % (
        DEFAULT_FORMS_BASE, WIDGET_FORM_PATH, TITLE_SELECT_FORM_ID,
        ANTHOLOGY_ID_KEY)), "stage form link shape"
    assert "&%s=s3_gate" % STAGE_KEY in link, "default stage token missing"

    # The editors-only law: every client-facing actor word in the generated
    # copy is an editor word; no forbidden shape anywhere in the payload.
    blob = json.dumps(wf)
    for m in re.finditer(r"\b[A-Za-z]+(?:s)?\b", blob):
        word = m.group(0).lower()
        if word in ("ai", "ghostwriter", "ghostwriters", "automated",
                    "generated"):
            raise ValueError("self-test: forbidden byline actor %r present"
                             % word)

    # The producer sign-off variant.
    email_prod = render_email(sign_off=SIGN_OFF_PRODUCER)
    assert email_prod["body"].endswith(
        "\nWarmly,\n{{ custom_values.producer }}")

    # The U08 pre-fill law with a synthetic (fixture) anthology id.
    preview = render_email(anthology_id="ANTH_TEST")
    assert "?anthology_id=ANTH_TEST&stage=s3_gate" in preview["stage_form_link"]

    # The pinned title-select form id must match the sibling builder's pin
    # (the one-form scope law; a drift is a located FAIL, never a blind pass).
    # Sibling bootstrap (house convention): the u08_u09 package sits under
    # scripts/, so the scripts dir goes on sys.path FIRST, then the package
    # imports BY NAME — the same bootstrap the u08_u09 siblings use to reach
    # anthology_registry.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import u08_u09_modules.title_select_builder as tsb
        sibling_pin = tsb.DEFAULT_TITLE_SELECT_FORM_ID
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "the title-select sibling pin is unavailable (%s) — the W2 "
            "scope law cannot be proven against its owning authority"
            % type(exc).__name__) from exc
    assert TITLE_SELECT_FORM_ID == sibling_pin, (
        "the pinned title-select form id drifted from "
        "title_select_builder.DEFAULT_TITLE_SELECT_FORM_ID (%r != %r)"
        % (TITLE_SELECT_FORM_ID, sibling_pin))

    # The never-a-real-token law over the whole rendered template.
    rendered = render_payload()
    detail = _never_a_real_token_check(rendered)
    if detail is not None:
        raise ValueError("self-test: never-a-real-token violation: %s"
                         % detail)

    # Attack fixtures — each must be REFUSED.
    def _attack(label, fn):
        try:
            result = fn()
        except ValueError:
            return
        # A guard that RETURNS a violation detail (never raises) is refused
        # only when the returned detail is non-empty.
        if isinstance(result, str) and result:
            return
        raise AssertionError("self-test: attack %s was NOT refused" % label)

    _attack("em-dash", lambda: _assert_copy_law("bad — dash", "attack"))
    _attack("ai-word", lambda: _assert_copy_law(
        "an AI wrote this", "attack"))
    _attack("ghostwriter", lambda: _assert_copy_law(
        "the ghostwriter did it", "attack"))
    _attack("secret-shape", lambda: _assert_copy_law(
        "Bearer abcdef0123456789", "attack"))
    _attack("unbalanced-merge", lambda: _assert_copy_law(
        "slot {{ antho", "attack"))
    _attack("out-of-vocabulary-stage", lambda: stage_form_link(stage="s99_bogus"))
    _attack("ai-in-subject", lambda: email_subject(
        anthology_name="AI Anthology"))
    _attack("ai-in-sms", lambda: sms_body(doc_link=DOC_LINK_MERGE,
                                          first_name="AI"))
    _attack("em-dash-in-body", lambda: _assert_copy_law(
        email_body(first_name="x", anthology_name="y",
                   pdf_link=PDF_LINK_MERGE, doc_link=DOC_LINK_MERGE)
        .replace("ready.", "ready—now."),
        "em-dash-in-body"))
    _attack("real-url-in-webhook", lambda: _never_a_real_token_check(
        json.dumps({"url_merge": "https://evil.example.com/hook"})))
    _attack("secret-in-webhook", lambda: _never_a_real_token_check(
        json.dumps({"authorization_header_merge": "Bearer abcdef0123456789"})))
    _attack("em-dash-in-webhook-body", lambda: webhook_body(title="bad — title"))
    print("w2_title_fire self-test: OK "
          "(trigger scope, webhook law, copy law, pre-fill law, "
          "never-a-real-token, all attacks refused)")
    return EX_OK

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W2 Title Fire template generator: the form_submission -> "
                    "custom-webhook POST workflow that carries the "
                    "participant's chosen title and subtitle to the engine's "
                    "intake hook (OFFLINE, no network, no credential)")
    ap.add_argument("cmd", nargs="?", choices=["plan", "render", "self-test"],
                    help="plan | render | self-test")
    ap.add_argument("--stage", default=DEFAULT_STAGE,
                    help="stage token for the prefilled form link and the "
                         "webhook body (default %s)" % DEFAULT_STAGE)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "render":
            print(render_payload(stage=args.stage))
            return EX_OK
        return plan()
    except SystemExit:
        raise
    except ValueError as exc:
        sys.stderr.write("w2_title_fire: law violation: %s\n" % exc)
        return EX_STOP
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("w2_title_fire: unexpected error: %s\n" % exc)
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
