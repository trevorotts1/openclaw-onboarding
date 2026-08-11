#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: u10_u13_modules/w1_review_fire.py
# (W1 template generator)
# UNIVERSAL-REVIEW FIRE TEMPLATE - form_submission TRIGGER + WEBHOOK POST
# (OFFLINE data generator). The ONLY client-facing copy the universal-review
# decision form may send, and the ONE trigger/action contract of the Review
# Fire workflow:
#   trigger      form_submission, scoped universal-review (the engine's ONE
#                client-facing decision form; the Review Fire trigger AND
#                the form the release emails link - forms_check.py
#                FORM_ID_BY_SLUG "universal-review", live-verified
#                2026-08-11 on the internal-rail trigger surface)
#   scope        EXACTLY form == "universal-review" - the SAME scope law
#                the Intake Fire trigger owns for the universal-intake form
#                (u02_modules.scope_check.py: the trigger filter is a form
#                token, byte-exact; a universal-intake submission must
#                NEVER ride the review trigger, the U05 negative mirror in
#                reverse)
#   action       webhook POST - the Custom Webhook action of the snapshot's
#                tag->notification workflow shape
#                (config/anthology-snapshot-contract.json workflows
#                .tag_to_notification.actions: method POST, URL merge
#                {{ custom_values.anthology_webhook_url }},
#                Authorization header merge
#                {{ custom_values.anthology_hook_secret }}, Content-Type
#                application/json). The URL and the Authorization header
#                ride the REPLACE-ME location custom values ONLY - never a
#                real value, never an inlined token (the never-a-real-token
#                rule, Skill 38 law; the intake route the hook may call is
#                config/route-template.json "anthology-intake" -
#                /hooks/anthology-intake - but the template never inlines
#                it, it is a merge at send time)
#   payload      the submission payload shape intake_router.py consumes
#                (source "anthology-intake", location, form, the universal
#                hidden-field contract contact_id / anthology_id / stage
#                byte-exact - the same surface the webhook fixtures carry,
#                fixtures/webhook/t4-valid-intake.json - plus the review
#                decision surface and, when carried, the cover choice)
# This module is a TEMPLATE GENERATOR, never a messenger: it renders the
# trigger/action contract, the payload shape, and the stage review link
# OFFLINE - zero network, zero credentials, nothing ever sent. A send path
# (the GHL workflow builder / the caf build rail) fills the rendered slots
# at build time; this module never touches a token, an env secret, or the
# wire.
# -----------------------------------------------------------------------------
# COPY LAW (workflows.copy_law - Trevor's verbatim law for every client-facing
# word these workflows carry; enforced here at GENERATION time so a templated
# review can never drift from the law):
#   EDITORS, NEVER AI ........ "editors" and "editorial team" are the ONLY
#        byline actors. "AI", "ghostwriter", "automated", "generated" and
#        every model/tool name are ABSENT from the generated copy (guards
#        below refuse such strings by word boundary, with the single
#        enforcement-context exception of the module's own docstring).
#   ZERO EM-DASHES .......... U+2014 is FORBIDDEN in generated copy. Every
#        sentence uses commas, periods, or a colon instead. The generators
#        refuse (ValueError) if any rendered string contains U+2014.
#   SIGN-OFF ................ "The Editors" or "{{ custom_values.producer }}"
#        only, never a person's raw name and never a model persona. The
#        email sign-off is "The Editors"; SMS never carries a sign-off (the
#        SMS shape law: one warm sentence plus ONE link).
#   STANDING INSTRUCTION .... "The PDF is yours to view. The Google Doc is
#        the one you edit, and it is the version we use." - byte-exact, in
#        every release email (copy_law.standing_instruction).
#   STAGE FORM LINK ......... <forms_base>/widget/form/<form_id>?anthology_id=
#        <minted>&stage=<stage> - the U08 pre-fill law: the TWO query params
#        pre-fill the form's HIDDEN fields client-side
#        (contact_id/anthology_id/stage universal hidden-field contract;
#        prefill_verifier.py owns the verifier). The default form is the
#        universal-review form (pin riNlAkYbcW3g92VRLqq0 - the Review Fire
#        trigger AND the form the release emails link) and the default stage
#        token is "s5_gate" (the EXACT STAGE_CURSORS vocabulary of
#        anthology_state.py; an out-of-vocabulary stage is a ValueError,
#        never a fabricated token). The participant gate at s5_gate exposes
#        EXACTLY TWO actions - approve_as_is / request_rewrite_with_notes
#        (gate_engine.py GATE_BY_CURSOR["s5_gate"], read ONCE below, never
#        re-implemented).
#   MERGES ................... Every client-facing value that must be filled
#        at send time is a {{ ... }} merge slot (GHL merge tags, spaces
#        exactly as the contract writes them: {{ custom_values.producer }});
#        never a literal value.
#   NO CODE FENCES / NO INTERNAL NAMES ... zero code fences, zero internal
#        tool or model names (the nudge-template discipline).
#   NO TOKENS ................ this module holds no credential surface:
#        nothing to resolve, nothing that could ever print a secret. The
#        webhook URL and its Authorization header ride the REPLACE-ME
#        location custom-value merges ONLY, and the self-test proves every
#        rendered string is secret-free (no "Bearer", no "sk-", no
#        key-shaped value).
#
# OFFLINE: plan / render / self-test all run with no network and no
# credential; rendering is PURE (same inputs -> same bytes).
#
# STDLIB ONLY. Importable by the u10_u13 package init and by the W1 assembler
# sibling; executed directly with the same contract as the sibling modules
# (plan / render / self-test). Exit codes (house convention):
#   0  plan / render / self-test pass
#   1  unexpected error
#   2  usage or a law violation detected offline (e.g. an out-of-vocabulary
#      stage token, an em-dash, an AI-word, an unknown form slug)
# =============================================================================

"""W1 review-fire template generator: the form_submission trigger + webhook
POST contract for the universal-review decision form, OFFLINE and pure."""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# The law, pinned at module top so every generator and every self-test
# assertion reads the SAME constants (single-implementation doctrine).
# ---------------------------------------------------------------------------

# The Review Fire workflow this template serves (forms_check.py header: the
# Anthology Intake/Review/Title Fire workflows each carry one ACTIVE
# form_submission trigger; this module serves the universal-review one).
WORKFLOW_NAME = "Anthology Review Fire"
TRIGGER_TYPE = "form_submission"
SCOPED_FORM = "universal-review"

# The universal-review decision form - the Review Fire trigger AND the form
# the release emails link (forms_check.FORM_ID_BY_SLUG - the SAME pin
# form_spec_loader.py and title_select_builder.py ship against). A location
# identifier, not a secret; reported by masked marker on every surface.
STAGE_FORM_SLUG = "universal-review"
STAGE_FORM_ID = "riNlAkYbcW3g92VRLqq0"

# The trigger scope law: EXACTLY the universal-review form token, byte-exact
# - the SAME law u02_modules/scope_check.py owns for the universal-intake
# form (the Intake Fire trigger filter is EXACTLY 'Form is
# universal-intake'; the Review Fire trigger is the mirror image: the
# filter is EXACTLY 'Form is universal-review', so a universal-intake
# submission NEVER fires the review trigger - the U05 negative mirror in
# reverse, and the W1 scope-applier sibling certifies it).
SCOPE_FILTER_FORM = "universal-review"

# The webhook action contract (the snapshot contract's tag_to_notification
# actions custom-webhook row: method POST, URL merge, Authorization header
# merge, Content-Type application/json). The URL and the Authorization
# header ride the REPLACE-ME location custom values ONLY - never an inlined
# URL, never an inlined token (never-a-real-token rule; Skill 38 law).
WEBHOOK_METHOD = "POST"
WEBHOOK_URL_MERGE = "{{ custom_values.anthology_webhook_url }}"
HOOK_SECRET_MERGE = "{{ custom_values.anthology_hook_secret }}"
WEBHOOK_CONTENT_TYPE = "application/json"

# The intake route the hook may call (config/route-template.json route_path;
# the engine-config intake.route_path cross-check - the same route the
# snapshot's webhook custom value points at). The template carries it as
# DOCUMENTATION ONLY - the actual value at send time is the client's real
# intake hook URL, resolved per install by
# anthology_snapshot.py provision-custom-values from the REPLACE-ME merge.
INTAKE_ROUTE_PATH = "/hooks/anthology-intake"

# The universal hidden-field contract (G3 + the snapshot contract forms
# block): EXACTLY this trio, byte-exact, on the review submission payload -
# the same trio the intake webhook fixtures carry
# (fixtures/webhook/t4-valid-intake.json) and the same trio
# form_spec_loader.HIDDEN_FIELD_LAW pins. The Review Fire trigger scope
# law, in payload form: a payload that drifts from the trio is REFUSED by
# the generators (ValueError), never rendered.
HIDDEN_FIELD_LAW = ("contact_id", "anthology_id", "stage")

# Exact stage-token vocabulary (anthology_state.STAGE_CURSORS). The default
# stage the review link pre-fills: the participant chapter-review gate that
# follows the S5 chapter deliverable (the s5_participant gate, EXACTLY TWO
# actions - approve_as_is / request_rewrite_with_notes).
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)
DEFAULT_STAGE = "s5_gate"

# The two decision actions of the s5_participant gate - read ONCE from the
# owning authority (gate_engine.py GATE_BY_CURSOR["s5_gate"].actions, the
# engine's gate state machine; the SAME vocabulary the U08/U09 decision
# dropdown owns, universal_review_builder.DECISION_OPTION_VALUES). Never
# re-implemented: a submitted decision must byte-equal one of these.
DECISION_ACTIONS = ("approve_as_is", "request_rewrite_with_notes")

# The four named cover styles (U8; cover_render.STYLE_NAMES - the choice
# picklist of the review form's cover dropdown, the same law
# universal_review_builder.COVER_CHOICE_OPTIONS reads once). The review
# payload may carry a cover choice; when it does, it must be ONE of these.
COVER_STYLE_NAMES = ("Signature", "Bold Editorial", "Fine Art", "Pure Type")

# The review submission's canonical payload keys, in order (the same surface
# the golden review fixture carries, golden_review.golden_review_payload:
# source, location, form, contact_id, anthology_id, stage, decision - plus
# the optional cover choice and the free-text notes the
# request_rewrite_with_notes decision requires, gate_engine
# ACTION_DECISION["request_rewrite_with_notes"] == ("request_rewrite",
# ("notes",))).
PAYLOAD_KEYS = ("source", "location", "form", "contact_id", "anthology_id",
                "stage", "decision", "notes", "cover_choice")
SOURCE_TOKEN = "anthology-intake"

# Field-map deliverable slots for the chapter deliverable
# (field-map.json deliverable_fields.chapter): the contact custom fields a
# decision email would reference. The W1 review copy references the chapter
# PDF (view) and the chapter Google Doc (edit) - the artifacts the
# participant is deciding on at s5_gate.
PDF_LINK_MERGE = "{{contact.anthology_chapter_pdf_url}}"
DOC_LINK_MERGE = "{{contact.anthology_chapter_doc_url}}"

# Copy-law merges - spaces EXACTLY as the contract writes them.
PRODUCER_MERGE = "{{ custom_values.producer }}"
PRODUCER_EMAIL_MERGE = "{{ custom_values.producer_email }}"
FIRST_NAME_MERGE = "{{ contact.first_name }}"
ANTHOLOGY_NAME_MERGE = "{{ custom_values.anthology_name }}"

# The standing instruction (copy_law.standing_instruction) - byte-exact.
STANDING_INSTRUCTION = (
    "The PDF is yours to view. The Google Doc is the one you edit, "
    "and it is the version we use."
)

# The only sanctioned sign-off (copy_law: "The Editors" or the producer merge).
SIGN_OFF_EDITORS = "The Editors"
SIGN_OFF_PRODUCER = PRODUCER_MERGE

# The review link's hidden-field query keys - the U08 pre-fill law
# (?anthology_id=<minted>&stage=<stage>; the universal hidden-field contract
# contact_id / anthology_id / stage of the snapshot contract forms block).
ANTHOLOGY_ID_KEY = "anthology_id"
STAGE_KEY = "stage"

# ---------------------------------------------------------------------------
# Guards (offline, fail-closed). A template that cannot prove it obeys the
# law is a ValueError, never a silently-off-copy payload.
# ---------------------------------------------------------------------------

# Word-boundary forbidden shapes in CLIENT-FACING copy: "AI" and
# "ghostwriter" are banned, with "editor"/"editors"/"editorial" REQUIRED to
# be the only byline actors. The enforcement-context exception is the module
# docstring (which must say "AI" to pin the law) - the docstring is not
# generated copy.
_FORBIDDEN_AI = re.compile(r"\b(?:A\.?I\.?|ghostwriter(?:s)?|automated|generated)\b", re.IGNORECASE)
_EDITOR_WORD = re.compile(r"\beditor(?:ial)?(?:s)?\b", re.IGNORECASE)

# Secret-shaped fragments that must never appear in generated copy (a
# template cannot print a token it never holds; the guard keeps the render
# honest even against a future merge-slot mistake).
_SECRET_SHAPES = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|ANTHOLOGY_HOOK_SECRET|"
    r"[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})"
)

# The U+2014 em dash is NEVER written literally in this file (zero em dashes
# in the file itself); the guard below builds the character at runtime so a
# grep for the dash can prove the file clean, and every rendered message
# must still pass the same guard (the w7 sibling's pattern).
EM_DASH = chr(0x2014)


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


def _assert_hidden_law(payload):
    """The universal hidden-field contract on the payload: contact_id,
    anthology_id and stage must ALL be present and non-empty (the same
    fail-closed validation intake_router.py performs before routing; a
    payload without the hidden trio is unroutable - unroutable_missing_ids -
    and is never rendered)."""
    for key in HIDDEN_FIELD_LAW:
        value = payload.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(
                "payload law violation: hidden field %r is missing or empty "
                "in the review payload - the universal hidden-field contract "
                "%s is byte-exact; a payload that cannot route is never "
                "rendered." % (key, ", ".join(HIDDEN_FIELD_LAW))
            )


def _assert_decision(payload):
    """The decision surface law: the review payload MUST carry a decision,
    and it must byte-equal one of the s5_participant gate's EXACTLY TWO
    actions (gate_engine GATE_BY_CURSOR["s5_gate"] - approve_as_is /
    request_rewrite_with_notes; the same vocabulary the U08/U09 decision
    dropdown owns). A blank or foreign decision is a refusal, never a
    render."""
    decision = payload.get("decision")
    if not isinstance(decision, str) or not decision.strip():
        raise ValueError(
            "payload law violation: the review payload carries no decision - "
            "the s5_participant gate requires EXACTLY ONE decision action."
        )
    if decision not in DECISION_ACTIONS:
        raise ValueError(
            "payload law violation: decision %r is not one of the two "
            "s5_participant gate actions %s - a foreign decision is drift, "
            "never a rendered review payload."
            % (decision, ", ".join(DECISION_ACTIONS))
        )
    # The request_rewrite_with_notes decision REQUIRES the free-text notes
    # surface (gate_engine ACTION_DECISION["request_rewrite_with_notes"] ==
    # ("request_rewrite", ("notes",))); the notes feed chapter_updates
    # verbatim. A rewrite request without notes is a refusal.
    if decision == "request_rewrite_with_notes":
        notes = payload.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError(
                "payload law violation: decision request_rewrite_with_notes "
                "requires the multi-line notes surface (gate_engine "
                "ACTION_DECISION law); a rewrite request without notes is "
                "refused, never rendered."
            )


def _assert_cover_choice(payload):
    """The U8 cover-choice law: when the payload carries a cover choice, it
    must be ONE of the four named style names (cover_render.STYLE_NAMES,
    the same law the U08/U09 cover dropdown owns). An out-of-set choice is
    drift, never a rendered payload."""
    choice = payload.get("cover_choice")
    if choice is None:
        return
    if not isinstance(choice, str) or choice not in COVER_STYLE_NAMES:
        raise ValueError(
            "payload law violation: cover choice %r is NOT one of the four "
            "named styles %s - an out-of-set choice is drift, never a "
            "rendered review payload."
            % (choice, ", ".join(COVER_STYLE_NAMES))
        )


def _validate_payload(payload):
    """The full review-payload law, fail-closed: the hidden trio byte-exact,
    the form token EXACTLY universal-review, the decision one of the two
    gate actions (with its required notes), and the cover choice in-set
    when carried. Every generated string inside the payload then passes the
    copy law."""
    if payload.get("form") != SCOPED_FORM:
        raise ValueError(
            "payload law violation: form token %r != %r - the Review Fire "
            "trigger is scoped EXACTLY to the universal-review form; a "
            "universal-intake submission must never ride it (the U05 "
            "negative mirror in reverse)." % (payload.get("form"), SCOPED_FORM)
        )
    _assert_hidden_law(payload)
    _assert_decision(payload)
    _assert_cover_choice(payload)


# ---------------------------------------------------------------------------
# The generators. Each returns plain-text client-facing copy; the email is
# plain text (the same client-clean shape the nudge templates use), so the
# same law guards cover every channel.
# ---------------------------------------------------------------------------


def email_subject(anthology_name=ANTHOLOGY_NAME_MERGE):
    """Subject line: the chapter is ready for its decision. ``anthology_name``
    is the GHL merge slot by default; a caller that renders an offline
    preview may pass a literal name (preview values are test values, never
    secrets)."""
    return _assert_copy_law(
        "Your chapter for %s is ready for your review" % anthology_name,
        "email_subject"
    )


def email_body(anthology_name=ANTHOLOGY_NAME_MERGE,
               first_name=FIRST_NAME_MERGE,
               pdf_link=PDF_LINK_MERGE,
               doc_link=DOC_LINK_MERGE,
               sign_off=SIGN_OFF_EDITORS,
               stage_form_link=None):
    """Render the review-decision EMAIL body (plain text).

    Slots (all GHL merges by default): the author's first name, the
    anthology name, the chapter PDF view link, the chapter Google Doc edit
    link, and the decision form link. The sign-off is "The Editors" (or the
    producer merge when the operator pins it). The decision link is
    optional and must be produced by :func:`stage_form_link` (the U08
    pre-fill law) when present; a malformed link is a ValueError, never a
    dropped link.
    """
    parts = []
    parts.append("Hi %s," % first_name)
    parts.append("")
    parts.append("Your chapter for %s is ready for your review." % anthology_name)
    parts.append("")
    parts.append("You can view the PDF here:")
    parts.append(pdf_link)
    parts.append("")
    parts.append("And you can edit your Google Doc here:")
    parts.append(doc_link)
    parts.append("")
    parts.append(STANDING_INSTRUCTION)
    if stage_form_link:
        parts.append("")
        parts.append("You can now approve your chapter or request an "
                     "editors' rewrite by opening this link:")
        parts.append(stage_form_link)
    parts.append("")
    parts.append("Thank you for being part of %s." % anthology_name)
    parts.append("")
    parts.append("Warmly,")
    parts.append(sign_off)
    for i, line in enumerate(parts):
        _assert_copy_law(line, "email_body[%d]" % i)
    return "\n".join(parts)


def sms_body(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """Render the review-decision SMS body: ONE warm sentence plus ONE link
    (the sms_shape law; the SMS carries the doc link only, never the PDF).
    No sign-off - the SMS shape law has no room for one."""
    text = "%s, your chapter is ready to review. Here is your Google Doc: %s" % (
        first_name, doc_link
    )
    return _assert_copy_law(text, "sms_body")


def stage_form_link(form_id=STAGE_FORM_ID,
                    anthology_id="",
                    stage=DEFAULT_STAGE,
                    forms_base="https://link.msgsndr.com"):
    """Build the stage decision form link - the U08 pre-fill law:

        <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>

    ``anthology_id`` is the MINTED anthology id: the template slot keeps the
    GHL merge marker ``{{ contact.anthology_id }}`` when no value is given
    (the pre-fill hydrates it client-side from the query param); a caller
    rendering an offline preview passes a synthetic fixture value. ``stage``
    must be EXACTLY one of the STAGE_CURSORS vocabulary (an
    out-of-vocabulary token is a ValueError, never a fabricated token).
    """
    if stage not in STAGE_VOCABULARY:
        raise ValueError(
            "stage token %r is not in the STAGE_CURSORS vocabulary; the "
            "pre-fill law demands an exact vocabulary token." % stage
        )
    if not anthology_id:
        anthology_id = "{{ contact.anthology_id }}"
    link = "%s/widget/form/%s?%s=%s&%s=%s" % (
        forms_base.rstrip("/"), form_id,
        ANTHOLOGY_ID_KEY, anthology_id, STAGE_KEY, stage,
    )
    return _assert_copy_law(link, "stage_form_link")


# ---------------------------------------------------------------------------
# The render surface (pure; deterministic bytes for identical inputs).
# ---------------------------------------------------------------------------

TRIGGER_SLOT_KEYS = ("workflow_name", "trigger_type", "scoped_form",
                     "trigger_filter", "form_id_marker")
WEBHOOK_SLOT_KEYS = ("method", "url_merge", "authorization_header_merge",
                     "content_type")
PAYLOAD_SLOT_KEYS = ("source", "location", "form", "contact_id",
                     "anthology_id", "stage", "decision", "notes",
                     "cover_choice")
EMAIL_SLOT_KEYS = ("subject", "body", "from_name", "reply_to", "pdf_link",
                   "doc_link", "stage_form_link")
SMS_SLOT_KEYS = ("body", "doc_link")


def _mask_id(fid):
    """The masked marker of a form id (the house location-policy shape: the
    last 4 characters with a dots prefix, the same shape reg._mask_location
    / form_reader.mask_id render). A form id VALUE never rides any surface;
    only the marker does."""
    return "...%s" % fid[-4:] if len(fid) >= 4 else "..."

FORM_ID_MARKER = _mask_id(STAGE_FORM_ID)


def render_trigger(form_id=STAGE_FORM_ID,
                   scoped_form=SCOPED_FORM):
    """The Review Fire TRIGGER contract: a form_submission trigger scoped
    EXACTLY to the universal-review form (the mirror image of the Intake
    Fire trigger's scope law, u02_modules.scope_check.py - the filter is a
    form token, byte-exact). The form id rides BY MASKED MARKER only; the
    id VALUE never surfaces. Pure and offline."""
    payload = {
        "workflow_name": WORKFLOW_NAME,
        "trigger_type": TRIGGER_TYPE,
        "scoped_form": scoped_form,
        "trigger_filter": "Form is %s" % SCOPE_FILTER_FORM,
        "form_id_marker": _mask_id(form_id),
    }
    for key in TRIGGER_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_trigger[%s]" % key)
    return payload


def render_webhook(webhook_url=WEBHOOK_URL_MERGE,
                   hook_secret=HOOK_SECRET_MERGE):
    """The Review Fire WEBHOOK action contract: method POST, the URL and
    Authorization header as the REPLACE-ME location custom-value merges ONLY
    (never a real URL, never a real token - the never-a-real-token rule),
    and Content-Type application/json (the snapshot contract's
    tag_to_notification custom-webhook action row). Pure and offline."""
    payload = {
        "method": WEBHOOK_METHOD,
        "url_merge": webhook_url,
        "authorization_header_merge": hook_secret,
        "content_type": WEBHOOK_CONTENT_TYPE,
    }
    for key in WEBHOOK_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_webhook[%s]" % key)
    return payload


def render_payload(location="",
                   contact_id="",
                   anthology_id="",
                   stage=DEFAULT_STAGE,
                   decision=DECISION_ACTIONS[0],
                   notes="",
                   cover_choice=None,
                   source=SOURCE_TOKEN,
                   form=SCOPED_FORM):
    """The review submission payload shape - exactly what the Review Fire
    webhook POSTs: the source token, the location, the form token
    universal-review, the universal hidden-field trio byte-exact
    (contact_id / anthology_id / stage), and the decision surface (one of
    the two gate actions, the required notes for a rewrite request, and an
    optional cover choice from the four named styles). Every empty routing
    id keeps its GHL merge slot when no value is given; a caller rendering
    an offline preview passes synthetic fixture values (never secrets). The
    full payload law is enforced fail-closed - a drift (including a foreign
    form token) is a ValueError, never a render."""
    payload = {
        "source": source,
        "location": location or "{{ location.id }}",
        "form": form,
        "contact_id": contact_id or "{{ contact.id }}",
        "anthology_id": anthology_id or "{{ contact.anthology_id }}",
        "stage": stage,
        "decision": decision,
    }
    if decision == "request_rewrite_with_notes":
        payload["notes"] = notes or "{{ form.notes }}"
    if cover_choice is not None:
        payload["cover_choice"] = cover_choice
    _validate_payload(payload)
    out = {}
    for key in PAYLOAD_KEYS:
        if key in payload:
            _assert_copy_law(payload[key], "render_payload[%s]" % key)
            out[key] = payload[key]
    return out


def render_email(sign_off=SIGN_OFF_EDITORS,
                 producer=PRODUCER_MERGE,
                 producer_email=PRODUCER_EMAIL_MERGE,
                 form_id=STAGE_FORM_ID,
                 anthology_id="",
                 stage=DEFAULT_STAGE,
                 forms_base="https://link.msgsndr.com"):
    """The complete EMAIL payload of the review decision: subject, body,
    producer-branded from_name, reply_to, and the per-stage link set
    (chapter PDF view + chapter Doc edit + the pre-filled decision form
    link). Pure and offline; every value is a merge slot unless the caller
    deliberately renders an offline preview (fixture values, never
    secrets)."""
    link = stage_form_link(
        form_id=form_id, anthology_id=anthology_id, stage=stage,
        forms_base=forms_base,
    )
    payload = {
        "subject": email_subject(),
        "body": email_body(
            sign_off=sign_off, stage_form_link=link,
        ),
        "from_name": producer,
        "reply_to": producer_email,
        "pdf_link": PDF_LINK_MERGE,
        "doc_link": DOC_LINK_MERGE,
        "stage_form_link": link,
    }
    for key in EMAIL_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_email[%s]" % key)
    return payload


def render_sms(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """The complete SMS payload: ONE warm sentence plus ONE doc link.
    Pure and offline; link is the merge slot by default."""
    payload = {"body": sms_body(doc_link=doc_link, first_name=first_name),
               "doc_link": doc_link}
    for key in SMS_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_sms[%s]" % key)
    return payload


def render(include_email=True, include_sms=True, **email_kwargs):
    """The full W1 render: the trigger contract, the webhook action, the
    submission payload shape, and (when asked) the email + SMS decision
    copy - the complete template the Review Fire build consumes. Every
    surface is pure and OFFLINE: nothing is sent, no credential is held."""
    out = {
        "workflow": WORKFLOW_NAME,
        "trigger": render_trigger(),
        "webhook": render_webhook(),
        "payload": render_payload(),
    }
    if include_email:
        out["email"] = render_email(**email_kwargs)
    if include_sms:
        out["sms"] = render_sms()
    return out


# ---------------------------------------------------------------------------
# CLI: plan / render / self-test, all OFFLINE.
# ---------------------------------------------------------------------------


def plan():
    print("W1 TEMPLATE  %s" % WORKFLOW_NAME)
    print("trigger:     %s scoped %s (filter 'Form is %s'; the U05 negative "
          "mirror: a universal-intake submission never rides it)"
          % (TRIGGER_TYPE, SCOPED_FORM, SCOPE_FILTER_FORM))
    print("action:      webhook %s to %s with Authorization %s, Content-Type %s"
          % (WEBHOOK_METHOD, WEBHOOK_URL_MERGE, HOOK_SECRET_MERGE,
             WEBHOOK_CONTENT_TYPE))
    print("payload:     source %s + the universal hidden trio %s + the "
          "decision surface (%s)"
          % (SOURCE_TOKEN, ", ".join(HIDDEN_FIELD_LAW),
             " / ".join(DECISION_ACTIONS)))
    print("channels:    EMAIL + SMS (decision copy; the email sign-off '%s' "
          "or %s)" % (SIGN_OFF_EDITORS, PRODUCER_MERGE))
    print("email links: %s (PDF view) + %s (Doc edit)" % (PDF_LINK_MERGE, DOC_LINK_MERGE))
    print("sms link:    %s (Doc edit only)" % DOC_LINK_MERGE)
    print("copy law:    editors never AI; zero em-dashes")
    print("standing:    %s" % STANDING_INSTRUCTION)
    print("stage form:  slug %s pin %s pre-filled %s=<minted>&%s=<stage> "
          "(default stage %s)"
          % (STAGE_FORM_SLUG, FORM_ID_MARKER, ANTHOLOGY_ID_KEY, STAGE_KEY,
             DEFAULT_STAGE))
    print("offline:     no network, no credential, nothing sent; the hook URL "
          "and Authorization header ride the REPLACE-ME merges ONLY "
          "(never-a-real-token)")
    return 0


def _self_test():
    """Offline law proof: golden renders + attack fixtures. A tamper is a
    ValueError (exit 2), never a silent pass."""
    # Golden: the default render obeys every law.
    trigger = render_trigger()
    assert trigger["trigger_type"] == "form_submission", "trigger type"
    assert trigger["scoped_form"] == "universal-review", "trigger scope form"
    assert trigger["trigger_filter"] == "Form is universal-review", \
        "trigger filter must be EXACTLY 'Form is universal-review'"
    assert trigger["form_id_marker"] == "...Lqq0", "form id must ride by masked marker only"
    assert STAGE_FORM_ID not in json.dumps(trigger), \
        "the form id VALUE must never ride the report surface"
    webhook = render_webhook()
    assert webhook["method"] == "POST", "webhook method must be POST"
    assert webhook["url_merge"] == WEBHOOK_URL_MERGE, \
        "webhook URL must be the REPLACE-ME merge, never a real value"
    assert webhook["authorization_header_merge"] == HOOK_SECRET_MERGE, \
        "Authorization header must be the REPLACE-ME merge, never a real token"
    assert webhook["content_type"] == "application/json", "content type"
    payload = render_payload()
    assert payload["form"] == "universal-review", "payload form token"
    for key in HIDDEN_FIELD_LAW:
        assert payload.get(key), "payload hidden field %s missing" % key
    assert payload["decision"] == "approve_as_is", "golden decision"
    assert payload["stage"] == "s5_gate", "golden stage token"
    # The rewrite-request payload carries its REQUIRED notes surface.
    payload_rw = render_payload(decision="request_rewrite_with_notes")
    assert payload_rw["notes"], "rewrite request must carry notes"
    # The cover choice is in-set when carried.
    payload_cover = render_payload(cover_choice="Signature")
    assert payload_cover["cover_choice"] == "Signature", "in-set cover choice"
    # The email obeys the copy law.
    email = render_email()
    assert email["from_name"] == PRODUCER_MERGE, "from_name must be the producer merge"
    assert email["reply_to"] == PRODUCER_EMAIL_MERGE, "reply_to must be the producer email merge"
    assert email["body"].endswith("\nWarmly,\nThe Editors"), (
        "sign-off must be exactly 'The Editors'")
    assert email["body"].count(STANDING_INSTRUCTION) == 1, (
        "standing instruction must appear exactly once")
    assert "AI" not in email["body"], "banned byline actor in golden email"
    assert "-" not in email["body"], "em-dash in golden email"
    assert PDF_LINK_MERGE in email["body"] and DOC_LINK_MERGE in email["body"], (
        "email must carry BOTH the PDF view link and the Doc edit link")
    sms = render_sms()
    assert sms["body"].count(DOC_LINK_MERGE) == 1 and "http" not in sms["body"], (
        "SMS must carry exactly ONE link (the doc link merge slot; a literal "
        "URL is a send-time fill, never a generated value)")
    assert "-" not in sms["body"], "em-dash in golden SMS"
    link = email["stage_form_link"]
    assert link.startswith("https://link.msgsndr.com/widget/form/%s?%s=" % (
        STAGE_FORM_ID, ANTHOLOGY_ID_KEY)), "stage form link shape"
    assert "&%s=s5_gate" % STAGE_KEY in link, "default stage token missing"
    # The editors-only law: every client-facing actor word in the generated
    # copy is an editor word; no forbidden shape anywhere in the payload.
    blob = json.dumps(email) + json.dumps(sms)
    for m in re.finditer(r"\b[A-Za-z]+(?:s)?\b", blob):
        word = m.group(0).lower()
        if word in ("ai", "ghostwriter", "ghostwriters", "automated", "generated"):
            raise ValueError("self-test: forbidden byline actor %r present" % word)
    # The producer sign-off variant.
    email_prod = render_email(sign_off=SIGN_OFF_PRODUCER)
    assert email_prod["body"].endswith("\nWarmly,\n{{ custom_values.producer }}")
    # The U08 pre-fill law with a synthetic (fixture) anthology id.
    preview = render_email(anthology_id="ANTH_TEST")
    assert "?anthology_id=ANTH_TEST&stage=s5_gate" in preview["stage_form_link"]
    # The never-a-real-token law over the whole render: the hook URL and the
    # Authorization header are merges ONLY; the intake route path is
    # documentation, never an inlined URL with a token.
    rendered = json.dumps(render())
    assert WEBHOOK_URL_MERGE in rendered and HOOK_SECRET_MERGE in rendered
    assert "Bearer" not in rendered and "sk-" not in rendered
    # Attack fixtures - each must be REFUSED.
    def _attack(label, fn):
        try:
            fn()
        except ValueError:
            return
        raise AssertionError("self-test: attack %s was NOT refused" % label)

    _attack("em-dash", lambda: _assert_copy_law(
        "bad %s dash" % EM_DASH, "attack"))
    _attack("ai-word", lambda: _assert_copy_law(
        "an AI wrote this", "attack"))
    _attack("ghostwriter", lambda: _assert_copy_law(
        "the ghostwriter did it", "attack"))
    _attack("secret-shape", lambda: _assert_copy_law(
        "Bearer abcdef0123456789", "attack"))
    _attack("unbalanced-merge", lambda: _assert_copy_law(
        "slot {{ antho", "attack"))
    _attack("out-of-vocabulary-stage", lambda: stage_form_link(stage="s99_bogus"))
    _attack("em-dash-in-body", lambda: _assert_copy_law(
        email_body(first_name="x", anthology_name="y", pdf_link=PDF_LINK_MERGE,
                   doc_link=DOC_LINK_MERGE,
                   stage_form_link=None).replace(
                       "ready for your review.",
                       "ready%s now." % EM_DASH),
        "em-dash-in-body"))
    _attack("ai-in-subject", lambda: email_subject(anthology_name="AI Anthology"))
    _attack("ai-in-sms", lambda: sms_body(doc_link=DOC_LINK_MERGE,
                                          first_name="AI"))
    # The hidden-trio law is enforced by _assert_hidden_law on the ALREADY
    # merged payload - the empty-string fallback keeps the GHL merge slot, so
    # the attack targets the merge fallback itself: a caller-supplied value
    # that is STILL empty after the merge (the merge slot is not a value,
    # and a payload whose hidden id is not even a merge is unroutable).
    _attack("missing-hidden-id", lambda: _assert_hidden_law(
        {"contact_id": "", "anthology_id": "A-1", "stage": "s5_gate"}))
    _attack("blank-decision", lambda: render_payload(decision=""))
    _attack("foreign-decision", lambda: render_payload(decision="approved"))
    _attack("rewrite-without-notes", lambda: _assert_decision(
        {"decision": "request_rewrite_with_notes", "notes": ""}))
    _attack("out-of-set-cover", lambda: render_payload(cover_choice="Neon"))
    _attack("intake-form-on-review", lambda: render_payload(
        form="universal-intake"))
    print("w1_review_fire self-test: OK "
          "(trigger scope law, webhook never-a-real-token, payload hidden "
          "trio + decision + cover laws, copy law, pre-fill law, channel "
          "shape, all attacks refused)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W1 template generator: the universal-review form_submission "
                    "trigger + webhook POST contract and decision copy "
                    "(OFFLINE, no network, no credential)")
    ap.add_argument("--plan", action="store_true",
                    help="print the template contract and exit (OFFLINE)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the trigger/payload/copy laws offline and exit")
    ap.add_argument("--render", action="store_true",
                    help="render the trigger + webhook + payload (and, with "
                         "--email-only / --sms-only, the copy) as JSON (OFFLINE)")
    ap.add_argument("--email-only", action="store_true",
                    help="with --render: email payload only")
    ap.add_argument("--sms-only", action="store_true",
                    help="with --render: sms payload only")
    ap.add_argument("--stage", default=DEFAULT_STAGE,
                    help="stage token for the decision link pre-fill "
                         "(default %s)" % DEFAULT_STAGE)
    ap.add_argument("--form-id", default=STAGE_FORM_ID,
                    help="stage form id (default the universal-review pin)")
    ap.add_argument("--forms-base", default="https://link.msgsndr.com",
                    help="hosted-form base URL (default link.msgsndr.com)")
    ap.add_argument("--anthology-id", default="",
                    help="fixture anthology id for an OFFLINE preview render; "
                         "default keeps the {{ contact.anthology_id }} merge")
    ap.add_argument("--sign-off", choices=("editors", "producer"),
                    default="editors",
                    help="email sign-off: editors (default) or producer merge")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return _self_test()
        if args.plan:
            return plan()
        if args.render:
            if args.email_only and args.sms_only:
                ap.error("--email-only and --sms-only are mutually exclusive")
            sign_off = SIGN_OFF_EDITORS if args.sign_off == "editors" else SIGN_OFF_PRODUCER
            payload = render(
                include_email=not args.sms_only,
                include_sms=not args.email_only,
                sign_off=sign_off,
                form_id=args.form_id,
                anthology_id=args.anthology_id,
                stage=args.stage,
                forms_base=args.forms_base,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        ap.error("one of --plan, --self-test, --render is required")
    except SystemExit:
        raise
    except ValueError as exc:
        sys.stderr.write("w1_review_fire: law violation: %s\n" % exc)
        return 2
    except Exception as exc:
        sys.stderr.write("w1_review_fire: unexpected error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
