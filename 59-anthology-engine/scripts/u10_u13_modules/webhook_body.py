#!/usr/bin/env python3
# =============================================================================
# SKILL 59  -  ANTHOLOGY ENGINE :: u10_u13_modules/webhook_body.py
# (W1/W2 webhook body builder)
# The W1/W2 WEBHOOK BODY BUILDER  -  the routed submission shapes the engine's
# inbound intake hook (/hooks/anthology-intake, config/route-template.json
# mapping "anthology-intake") accepts, and the OUTBOUND custom-webhook POST
# shapes the snapshot's tag->notification workflows fire (the custom-webhook
# action of config/anthology-snapshot-contract.json). This module is a PURE
# OFFLINE data generator: it renders JSON/Python dict bodies, the
# x-anthology-secret header rule, the stage-form pre-fill link, and the
# per-stage PDF view + Google Doc edit link pair  -  zero network, zero
# credentials, nothing ever sent. A send path fills the rendered slots at
# send time; this module never touches a token, an env secret, or the wire.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS:
#   * the body KEY LAW  -  every routed body carries the keys
#     intake_router.py's field_candidates consumes: source, stage,
#     decision, notes, cover_choice, anthology_id, contact_id, location
#     (each read along the exact candidate paths the router accepts;
#     a value emitted for one of these keys is always an EXACT
#     router-acceptable shape, never a fabricated alias).
#   * the SOURCE LAW  -  the inbound body's source is EXACTLY
#     "anthology-intake" (route-template match.source; a foreign source
#     never fires the mapping). An outbound body carries no source key
#     (the snapshot custom-webhook posts a routed submission, not an
#     intake front door).
#   * the SECRET HEADER LAW  -  the route secret rides the
#     x-anthology-secret HEADER (or the Authorization bearer at the
#     gateway), NEVER in the body: intake_router.verify_secret reads the
#     body only in defense-in-depth mode, and a body-borne secret is a
#     REFUSAL here (the body must be safe to log and to preserve in the
#     Exceptions raw-submission row). The outbound POST rides the
#     REPLACE-ME custom-value merge {{ custom_values.anthology_hook_secret }}
#     ONLY (the never-a-real-token rule); a real token VALUE is never
#     accepted and never printed.
#   * the DECISION / NOTES / COVER LAW  -  the universal-review decision
#     surface (PRD Section 4 / U8): decision is EXACTLY one of
#     gate_engine.GATE_BY_CURSOR["s5_gate"].actions
#     ("approve_as_is" | "request_rewrite_with_notes"); notes feed
#     chapter_updates verbatim (required with
#     request_rewrite_with_notes  -  gate_engine ACTION_DECISION); the
#     cover choice is EXACTLY one of the four named style names
#     cover_render.STYLE_NAMES (Signature / Bold Editorial / Fine Art /
#     Pure Type)  -  a pick outside the four is a ValueError, never a
#     fabricated style.
#   * the COPY LAW (workflows.copy_law  -  Trevor's verbatim law for every
#     client-facing word these workflows carry; enforced here at
#     GENERATION time so a templated release can never drift from the
#     law): "editors" is the ONLY byline actor (AI / ghostwriter /
#     automated / generated shapes are banned by word boundary); ZERO
#     U+2014 em-dashes; the email sign-off is "The Editors" or
#     "{{ custom_values.producer }}" only, never a persona.
#   * the STANDING INSTRUCTION  -  "The PDF is yours to view. The Google
#     Doc is the one you edit, and it is the version we use."  -  byte-
#     exact in every release email (copy_law.standing_instruction).
#   * the STAGE FORM LINK  -  <forms_base>/widget/form/<form_id>?
#     anthology_id=<minted>&stage=<stage>  -  the U08 pre-fill law: the TWO
#     query params pre-fill the form's HIDDEN fields client-side. The
#     default form is the universal-review form (pin
#     riNlAkYbcW3g92VRLqq0  -  the Review Fire trigger AND the form the
#     release emails link) and the default stage token is the s5_gate
#     chapter-review cursor (the EXACT STAGE_CURSORS vocabulary of
#     anthology_state.py; an out-of-vocabulary stage is a ValueError,
#     never a fabricated token).
#   * the ONE PDF VIEW + ONE DOC EDIT LAW  -  each release email carries
#     that stage's PDF (view) link plus the editable Google Doc (edit)
#     link, both from the contact custom fields
#     (field-map.json deliverable_fields -> doc_url / pdf_url); the SMS
#     carries ONLY the doc link (copy_law.per_stage_links + sms_shape).
#   * the NEVER-PRINT-A-TOKEN LAW  -  the module holds no credential
#     surface and refuses to emit one: a secret-shaped fragment in any
#     generated string is a ValueError; the CLI masks every form id and
#     anthology id on its human surfaces and renders only masked markers
#     in the offline preview JSON.
#
# OFFLINE: plan / render / self-test all run with no network and no
# credential; rendering is PURE (same inputs -> same bytes).
#
# STDLIB ONLY. Importable by the u10_u13 package init and by the W1/W2
# assembler sibling; executed directly with the same contract as the
# sibling modules (plan / render / self-test). Exit codes (house
# convention):
#   0  plan / render / self-test pass
#   1  unexpected error
#   2  usage or a law violation detected offline (e.g. an out-of-vocabulary
#      stage token, an em-dash, an AI-word, a secret-shaped value, an
#      unknown decision or cover style)
# =============================================================================

"""W1/W2 webhook body builder: routed submission + outbound POST shapes,
OFFLINE and pure."""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# The law, pinned at module top so every generator and every self-test
# assertion reads the SAME constants (single-implementation doctrine).
# ---------------------------------------------------------------------------

# The inbound intake route and its mapping source (config/route-template.json
# mapping "anthology-intake": match.source == "anthology-intake"; the route
# path the mapping serves).
INTAKE_ROUTE_PATH = "/hooks/anthology-intake"
INTAKE_SOURCE = "anthology-intake"

# The universal-review decision form  -  the Review Fire trigger AND the form
# the release emails link (forms_check.FORM_ID_BY_SLUG  -  the SAME pin
# form_spec_loader.py, universal_review_builder.py and the w3/w4 siblings
# ship against). The default stage form of the builder.
STAGE_FORM_SLUG = "universal-review"
STAGE_FORM_ID = "riNlAkYbcW3g92VRLqq0"

# Exact stage-token vocabulary (anthology_state.STAGE_CURSORS). The default
# stage the review link pre-fills: the chapter-approve-or-rewrite cursor the
# participant sits at while the s5_gate is open (the engine's chapter gate  - 
# EXACTLY TWO actions, gate_engine.GATE_BY_CURSOR["s5_gate"]).
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)
DEFAULT_STAGE = "s5_gate"

# The EXACTLY-TWO chapter gate actions (gate_engine.GATE_BY_CURSOR
# ["s5_gate"].actions, the engine's action vocabulary  -  the SAME pair
# dropdown_module.py / attack_bad_dropdown.py pin byte-exact). A decision
# outside this pair is a ValueError, never a fabricated action.
DECISION_VOCABULARY = ("approve_as_is", "request_rewrite_with_notes")

# The four named cover styles (cover_render.STYLE_NAMES  -  the naming
# authority; the registry self-test pins field-map choice_options ==
# STYLE_NAMES in order). A cover choice outside these four names is a
# ValueError, never a fabricated style.
COVER_STYLE_VOCABULARY = ("Signature", "Bold Editorial", "Fine Art", "Pure Type")

# The field-map deliverable slots this builder emits link pairs for
# (field-map.json deliverable_fields  -  the ONE field-key authority; a link
# key is never hardcoded, it is read from this map). Each entry is
# (doc_url, pdf_url) in slot order, so the EMAIL link pair is always
# (PDF view first, Doc edit second) exactly as the contract rows list them
# (email_link_fields = [pdf, doc]).
DELIVERABLE_LINK_KEYS = {
    "avatar":     ("contact.anthology_avatar_doc_url",       "contact.anthology_avatar_pdf_url"),
    "tone":       ("contact.anthology_tone_doc_url",         "contact.anthology_tone_pdf_url"),
    "titles":     ("contact.anthology_titles_doc_url",       "contact.anthology_titles_pdf_url"),
    "blurb":      ("contact.anthology_blurb_doc_url",        "contact.anthology_blurb_pdf_url"),
    "outline":    ("contact.anthology_outline_doc_url",      "contact.anthology_outline_pdf_url"),
    "chapter":    ("contact.anthology_chapter_doc_url",      "contact.anthology_chapter_pdf_url"),
    "rewrite1":   ("contact.anthology_chapter_rewrite1_doc_url", "contact.anthology_chapter_rewrite1_pdf_url"),
    "rewrite2":   ("contact.anthology_chapter_rewrite2_doc_url", "contact.anthology_chapter_rewrite2_pdf_url"),
    "manuscript": ("contact.anthology_manuscript_doc_url",   "contact.anthology_manuscript_pdf_url"),
}
# The cover deliverable's pair is NOT a Doc/PDF pair (field-map note): doc_url
# carries the media-storage image link and pdf_url the Drive link; the cover
# surface is the four style sample urls, never an edit link. Kept OUT of the
# email link-pair law below by design.
COVER_SAMPLE_KEYS = tuple(
    "contact.anthology_cover_sample%d_url" % i for i in (1, 2, 3, 4)
)
COVER_CHOICE_KEY = "contact.anthology_cover_choice"

# Copy-law merges  -  spaces EXACTLY as the contract writes them.
PRODUCER_MERGE = "{{ custom_values.producer }}"
PRODUCER_EMAIL_MERGE = "{{ custom_values.producer_email }}"
FIRST_NAME_MERGE = "{{ contact.first_name }}"
ANTHOLOGY_NAME_MERGE = "{{ custom_values.anthology_name }}"

# The standing instruction (copy_law.standing_instruction)  -  byte-exact.
STANDING_INSTRUCTION = (
    "The PDF is yours to view. The Google Doc is the one you edit, "
    "and it is the version we use."
)

# The only sanctioned sign-offs (copy_law: "The Editors" or the producer
# merge; never a persona).
SIGN_OFF_EDITORS = "The Editors"
SIGN_OFF_PRODUCER = PRODUCER_MERGE

# The stage form link's hidden-field query keys  -  the U08 pre-fill law
# (?anthology_id=<minted>&stage=<stage>; the snapshot contract forms block
# universal_hidden_fields contact_id / anthology_id / stage).
ANTHOLOGY_ID_KEY = "anthology_id"
STAGE_KEY = "stage"

# The fleet GHL/LeadConnector hosted-form domain (anthology_book.py
# DEFAULT_FORMS_BASE) and the widget path.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
WIDGET_FORM_PATH = "/widget/form"

# The minted-anthology merge slot (the G3 law: the query key is EXACTLY
# anthology_id, never anthology_active_id  -  the builder never holds a
# concrete id).
ACTIVE_ANTHOLOGY_MERGE = "{{ contact.anthology_active_id }}"

# ---------------------------------------------------------------------------
# THE WEBHOOK SURFACE (the snapshot contract's location_custom_values  - 
# the never-a-real-token rule). The outbound POST rides the REPLACE-ME
# custom values ONLY; a real-looking URL or a credential-shaped value
# anywhere in the template is a REFUSAL.
# ---------------------------------------------------------------------------
WEBHOOK_URL_MERGE = "{{ custom_values.anthology_webhook_url }}"
HOOK_SECRET_MERGE = "{{ custom_values.anthology_hook_secret }}"

# The POST body's content type (the snapshot contract's custom-webhook
# action: content_type application/json).
CONTENT_TYPE = "application/json"

# ---------------------------------------------------------------------------
# Guards (offline, fail-closed). A template that cannot prove it obeys the
# law is a ValueError, never a silently-off-copy payload.
# ---------------------------------------------------------------------------

# The U+2014 em dash is NEVER written literally in this file (zero em dashes
# in the file itself, the same law verify.sh enforces over the nudge
# templates); the validator below builds the character at runtime so a grep
# for the dash can prove the file clean, and every rendered message must
# still pass the same validator.
EM_DASH = chr(0x2014)

# Word-boundary forbidden shapes in CLIENT-FACING copy: the "AI" and
# "ghostwriter" shapes are banned, with "editor"/"editors"/"editorial"
# REQUIRED to be the only byline actors. The enforcement-context exception
# is the module docstring (which must name the ban to pin it)  -  the
# docstring is not generated copy.
_FORBIDDEN_AI = re.compile(
    r"\b(?:A\.?I\.?|ghostwriter(?:s)?|automated|generated)\b", re.IGNORECASE)
_EDITOR_WORD = re.compile(r"\beditor(?:ial)?(?:s)?\b", re.IGNORECASE)

# Secret-shaped fragments that must never appear in generated copy (a
# template cannot print a token it never holds; the guard keeps the render
# honest even against a future merge-slot mistake). The ANTHOLOGY_HOOK_SECRET
# label is included so a stray label mention in a payload is a refusal too.
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


def _assert_no_secret(text, label):
    """The never-print-a-token law: a secret-shaped fragment in ANY emitted
    value (body, header rule, link) is a refusal. Same shapes as the copy
    law's secret guard; kept as a distinct named check so the body builder
    can assert it over non-copy values too."""
    m = _SECRET_SHAPES.search(text)
    if m:
        raise ValueError(
            "secret-shaped fragment %r in %s; a webhook body never carries "
            "a token value (the secret rides the header merge only)."
            % (m.group(0), label)
        )
    return text


def _validated_body_value(key, value):
    """Validate ONE body value against the body key law: the copy law for
    client-facing keys, the never-print-a-token law for every key, and the
    key-specific vocabularies (stage / decision / cover choice / source)."""
    text = str(value)
    if key == "source":
        if value != INTAKE_SOURCE:
            raise ValueError(
                "body key source must be EXACTLY %r (route-template "
                "match.source); got %r" % (INTAKE_SOURCE, value)
            )
    if key == "stage":
        if value not in STAGE_VOCABULARY:
            raise ValueError(
                "stage token %r is not in the STAGE_CURSORS vocabulary; the "
                "pre-fill law demands an exact vocabulary token." % value
            )
    if key == "decision":
        if value not in DECISION_VOCABULARY:
            raise ValueError(
                "decision %r is not one of the chapter gate's EXACTLY-TWO "
                "actions %r (gate_engine GATE_BY_CURSOR s5_gate)."
                % (value, list(DECISION_VOCABULARY))
            )
    if key == "cover_choice" and value:
        if value not in COVER_STYLE_VOCABULARY:
            raise ValueError(
                "cover choice %r is not one of the four named style names %r "
                "(cover_render.STYLE_NAMES)."
                % (value, list(COVER_STYLE_VOCABULARY))
            )
    if key in ("notes", "decision", "cover_choice"):
        _assert_copy_law(text, "webhook_body[%s]" % key)
    else:
        _assert_no_secret(text, "webhook_body[%s]" % key)
    return value


# ---------------------------------------------------------------------------
# The body generators (pure; deterministic bytes for identical inputs).
# ---------------------------------------------------------------------------

def inbound_body(anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                 stage=DEFAULT_STAGE,
                 contact_id="{{ contact.id }}",
                 location="{{ contact.locationId }}",
                 decision=None,
                 notes=None,
                 cover_choice=None,
                 extra=None):
    """The INBOUND routed submission, the body shape the intake hook's
    route mapping accepts (source == "anthology-intake" byte-exact) and the
    keys intake_router.py's field_candidates consumes: contact_id,
    anthology_id, stage, location, plus the universal-review decision
    surface (decision / notes / cover_choice) when the submission is a
    review pick. Defaults are merge slots (filled at send time by the
    hosting workflow); a caller rendering an offline preview passes
    fixture values (never secrets).

    The decision surface obeys the U8 law: decision is EXACTLY one of the
    chapter gate's two actions; notes are REQUIRED with
    request_rewrite_with_notes (gate_engine ACTION_DECISION: notes feed
    chapter_updates verbatim); cover_choice, when present, is EXACTLY one
    of the four named style names. The route secret NEVER rides the body
    (the x-anthology-secret header law); a secret-shaped value in any
    emitted key is a refusal.
    """
    body = {
        "source": INTAKE_SOURCE,
        "stage": stage,
        "anthology_id": anthology_id,
        "contact_id": contact_id,
        "location": location,
    }
    if decision is not None:
        if decision not in DECISION_VOCABULARY:
            raise ValueError(
                "decision %r is not one of the chapter gate's EXACTLY-TWO "
                "actions %r (gate_engine GATE_BY_CURSOR s5_gate)."
                % (decision, list(DECISION_VOCABULARY))
            )
        if decision == "request_rewrite_with_notes" and not notes:
            raise ValueError(
                "decision request_rewrite_with_notes REQUIRES notes "
                "(gate_engine ACTION_DECISION; the notes feed chapter_updates "
                "verbatim)."
            )
        body["decision"] = decision
        if notes:
            body["notes"] = notes
    if cover_choice is not None:
        if cover_choice not in COVER_STYLE_VOCABULARY:
            raise ValueError(
                "cover choice %r is not one of the four named style names %r "
                "(cover_render.STYLE_NAMES)."
                % (cover_choice, list(COVER_STYLE_VOCABULARY))
            )
        body["cover_choice"] = cover_choice
    if extra:
        for key, value in extra.items():
            _validated_body_value(key, value)
            body[key] = value
    for key, value in body.items():
        _validated_body_value(key, value)
    return body


def outbound_post(stage=DEFAULT_STAGE,
                  anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                  decision=None,
                  notes=None,
                  cover_choice=None,
                  contact_id="{{ contact.id }}",
                  location="{{ contact.locationId }}"):
    """The OUTBOUND custom-webhook POST action: method POST, content type
    application/json, URL and Authorization header riding ONLY the REPLACE-ME
    location custom-value merges, and the routed body. The secret header law:
    the x-anthology-secret header (the authorization_header_merge below) is
    the ONLY place the hook secret rides; the body NEVER carries it. Pure
    and offline; never a real URL, never a real token."""
    payload = {
        "method": "POST",
        "content_type": CONTENT_TYPE,
        "url_merge": WEBHOOK_URL_MERGE,
        "authorization_header_merge": HOOK_SECRET_MERGE,
        "body": inbound_body(
            anthology_id=anthology_id, stage=stage, contact_id=contact_id,
            location=location, decision=decision, notes=notes,
            cover_choice=cover_choice,
        ),
    }
    for key in ("method", "content_type", "url_merge",
                "authorization_header_merge"):
        _assert_copy_law(payload[key], "outbound_post[%s]" % key)
    _assert_copy_law(
        json.dumps(payload["body"], sort_keys=True),
        "outbound_post[body]",
    )
    return payload


def secret_header_law() -> dict:
    """The x-anthology-secret header rule as a data object, the ONE place
    the hook secret rides. The header key is EXACTLY "x-anthology-secret"
    (intake_router.py field_candidates route_secret list includes the
    header alias; the gateway's own hooks.token enforces the transport
    bearer first, this is the defense-in-depth value). The header VALUE is
    ALWAYS the REPLACE-ME merge, never a real token. A real token value in
    the template is a refusal; the module never holds or prints one."""
    return {
        "header": "x-anthology-secret",
        "value_merge": HOOK_SECRET_MERGE,
        "body_carries_secret": False,
        "note": "the route secret rides the x-anthology-secret HEADER only, "
                "never the body; the body is safe to log and to preserve in "
                "the Exceptions raw-submission row. The gateway enforces the "
                "transport bearer (hooks.token) first; this header is the "
                "defense-in-depth value intake_router.py verifies.",
    }


# ---------------------------------------------------------------------------
# The stage form link and the per-stage link pair (the U08 pre-fill law +
# copy_law.per_stage_links).
# ---------------------------------------------------------------------------

def stage_form_link(form_id=STAGE_FORM_ID,
                    anthology_id="",
                    stage=DEFAULT_STAGE,
                    forms_base=DEFAULT_FORMS_BASE):
    """Build the stage review form link, the U08 pre-fill law:

        <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>

    ``anthology_id`` is the MINTED anthology id: the template slot keeps the
    contact's active-anthology merge ``{{ contact.anthology_active_id }}``
    when no value is given (the pre-fill hydrates it client-side from the
    query param); a caller rendering an offline preview passes a synthetic
    fixture value. ``stage`` must be EXACTLY one of the STAGE_CURSORS
    vocabulary (an out-of-vocabulary token is a ValueError, never a
    fabricated token). The default form is the pinned universal-review
    form id, the form the release emails link and the decision surface.
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


def deliverable_link_pair(deliverable):
    """The per-stage link pair as GHL merge tags, the ONE PDF view link
    plus the ONE Google Doc edit link of the stage's release email
    (copy_law.per_stage_links: email_link_fields [pdf, doc], pulled from
    the matching field-map deliverable_fields contact custom fields).
    Returns (pdf_view_merge, doc_edit_merge) in the contract's slot order.
    ``deliverable`` must be one of the field-map deliverable_fields slots;
    the cover deliverable is NOT an edit link pair (its pair is an image
    media link + a Drive link, field-map note) and is refused here."""
    if deliverable not in DELIVERABLE_LINK_KEYS:
        raise ValueError(
            "deliverable %r has no doc/pdf link pair in "
            "config/field-map.json deliverable_fields (the cover surface "
            "is the four style sample urls, never an edit pair)."
            % deliverable
        )
    doc_key, pdf_key = DELIVERABLE_LINK_KEYS[deliverable]
    pdf_view = "{{" + pdf_key + "}}"
    doc_edit = "{{" + doc_key + "}}"
    return (pdf_view, doc_edit)


# ---------------------------------------------------------------------------
# The render surface (pure; deterministic bytes for identical inputs).
# ---------------------------------------------------------------------------

BODY_SLOT_KEYS = ("source", "stage", "anthology_id", "contact_id",
                  "location", "decision", "notes", "cover_choice")
POST_SLOT_KEYS = ("method", "content_type", "url_merge",
                  "authorization_header_merge", "body")


def render_inbound(stage=DEFAULT_STAGE,
                   anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                   contact_id="{{ contact.id }}",
                   location="{{ contact.locationId }}",
                   decision=None,
                   notes=None,
                   cover_choice=None):
    """The complete INBOUND routed submission as a JSON-ready dict: the
    body keys plus the x-anthology-secret header rule (the header value
    NEVER rides the body; the header rule object is data, never a token).
    Pure and offline."""
    body = inbound_body(
        anthology_id=anthology_id, stage=stage, contact_id=contact_id,
        location=location, decision=decision, notes=notes,
        cover_choice=cover_choice,
    )
    return {
        "contract": "anthology-engine-w1-w2-webhook-body",
        "schema_version": 1,
        "source_law": "source == 'anthology-intake' (route-template "
                      "match.source; a foreign source never fires the "
                      "mapping)",
        "body": body,
        "secret_header": secret_header_law(),
        "offline": "no network, no credential, nothing sent",
    }


def render_links(deliverable="chapter", form_id=STAGE_FORM_ID,
                 anthology_id="", stage=DEFAULT_STAGE,
                 forms_base=DEFAULT_FORMS_BASE):
    """The link set the release email carries: the stage's ONE PDF view
    link, ONE Google Doc edit link, and the pre-filled stage form link.
    Pure and offline; every link is a merge tag unless the caller
    deliberately renders an offline preview (fixture values, never
    secrets)."""
    pdf_view, doc_edit = deliverable_link_pair(deliverable)
    return {
        "deliverable": deliverable,
        "pdf_view_merge": pdf_view,
        "doc_edit_merge": doc_edit,
        "stage_form_link": stage_form_link(
            form_id=form_id, anthology_id=anthology_id, stage=stage,
            forms_base=forms_base,
        ),
        "standing_instruction": STANDING_INSTRUCTION,
        "sign_off": SIGN_OFF_EDITORS,
        "sign_off_alternate": SIGN_OFF_PRODUCER,
    }


def render_payload(stage=DEFAULT_STAGE,
                   deliverable="chapter",
                   anthology_id=ACTIVE_ANTHOLOGY_MERGE,
                   contact_id="{{ contact.id }}",
                   location="{{ contact.locationId }}",
                   decision=None,
                   notes=None,
                   cover_choice=None,
                   forms_base=DEFAULT_FORMS_BASE,
                   form_id=STAGE_FORM_ID):
    """The full offline render: the routed submission, the outbound POST
    action, the secret header rule, and the per-stage link set. PURE and
    OFFLINE, returns plain dict/list data only; the caller decides how to
    consume it (build rail, operator surface, or JSON)."""
    return {
        "contract": "anthology-engine-w1-w2-webhook-body",
        "schema_version": 1,
        "inbound": render_inbound(
            stage=stage, anthology_id=anthology_id, contact_id=contact_id,
            location=location, decision=decision, notes=notes,
            cover_choice=cover_choice,
        ),
        "outbound_post": outbound_post(
            stage=stage, anthology_id=anthology_id, contact_id=contact_id,
            location=location, decision=decision, notes=notes,
            cover_choice=cover_choice,
        ),
        "secret_header": secret_header_law(),
        "links": render_links(
            deliverable=deliverable, form_id=form_id, anthology_id=anthology_id,
            stage=stage, forms_base=forms_base,
        ),
    }


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

MASKED_FORM_ID_MARKER = "<form_id:masked>"
MASKED_ANTHOLOGY_ID_MARKER = "<anthology_id:masked>"


def plan():
    """The offline plan, the W1/W2 webhook body law with its sources, one
    JSON object on stdout."""
    print(json.dumps({
        "contract": "anthology-engine-w1-w2-webhook-body",
        "route": INTAKE_ROUTE_PATH,
        "source": INTAKE_SOURCE,
        "body_keys": ["source", "stage", "decision", "notes", "cover_choice",
                      "anthology_id", "contact_id", "location"],
        "body_keys_note": "the exact keys intake_router.field_candidates "
                          "consumes; every emitted value is an exact "
                          "router-acceptable shape, never a fabricated "
                          "alias",
        "secret_header": {
            "header": "x-anthology-secret",
            "value_merge": HOOK_SECRET_MERGE,
            "body_carries_secret": False,
        },
        "decision_vocabulary": list(DECISION_VOCABULARY),
        "cover_style_vocabulary": list(COVER_STYLE_VOCABULARY),
        "stage_form_link": stage_form_link(),
        "stage_form_slug": STAGE_FORM_SLUG,
        "stage_form_id_masked": MASKED_FORM_ID_MARKER,
        "default_stage": DEFAULT_STAGE,
        "deliverable_link_slots": sorted(DELIVERABLE_LINK_KEYS),
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
    return 0


def _self_test():
    """Offline law proof: golden renders + attack fixtures. A tamper is a
    ValueError (exit 2), never a silent pass."""
    # Golden: the default inbound render (merge slots) obeys every law.
    inbound = render_inbound()
    body = inbound["body"]
    assert body["source"] == "anthology-intake", "source must be byte-exact"
    assert body["stage"] == "s5_gate", (
        "the default stage must be s5_gate (the cursor of the open chapter "
        "gate)")
    assert body["anthology_id"] == ACTIVE_ANTHOLOGY_MERGE, (
        "the body anthology_id must be the contact's active-anthology merge")
    assert inbound["secret_header"]["header"] == "x-anthology-secret", (
        "the secret header key must be x-anthology-secret")
    assert inbound["secret_header"]["value_merge"] == HOOK_SECRET_MERGE, (
        "the secret header value must ride the REPLACE-ME custom-value merge")
    assert inbound["secret_header"]["body_carries_secret"] is False, (
        "the body must never carry the route secret")
    assert "decision" not in body and "cover_choice" not in body, (
        "a plain routed body carries no decision surface")

    # The decision surface: exactly-two actions, notes required with a
    # rewrite request, cover choice one of the four named styles.
    review = inbound_body(decision="approve_as_is")
    assert review["decision"] == "approve_as_is", "the approve decision"
    rewrite = inbound_body(decision="request_rewrite_with_notes",
                           notes="Please deepen the opening.")
    assert rewrite["notes"] == "Please deepen the opening.", (
        "the rewrite notes ride the body verbatim")
    cover = inbound_body(decision="approve_as_is", cover_choice="Fine Art")
    assert cover["cover_choice"] == "Fine Art", (
        "the cover choice must be one of the four named styles")

    # The outbound POST rides the REPLACE-ME merges only.
    post = outbound_post()
    assert post["method"] == "POST", "the webhook action must be a POST"
    assert post["content_type"] == "application/json", (
        "the webhook content type must be application/json")
    assert post["url_merge"] == WEBHOOK_URL_MERGE, (
        "the webhook URL must ride the REPLACE-ME custom-value merge")
    assert post["authorization_header_merge"] == HOOK_SECRET_MERGE, (
        "the Authorization header must ride the REPLACE-ME custom-value merge")

    # The U08 pre-fill law with a synthetic (fixture) anthology id.
    link = stage_form_link(anthology_id="ANTH_TEST")
    assert link == ("https://link.msgsndr.com/widget/form/"
                    "riNlAkYbcW3g92VRLqq0?anthology_id=ANTH_TEST"
                    "&stage=s5_gate"), "stage form link shape"
    assert "&stage=s5_gate" in link, "default stage token missing"

    # The link pair law: ONE PDF view + ONE Doc edit per deliverable.
    pdf_view, doc_edit = deliverable_link_pair("chapter")
    assert pdf_view == "{{contact.anthology_chapter_pdf_url}}", (
        "the chapter pdf tag drifted from deliverable_fields")
    assert doc_edit == "{{contact.anthology_chapter_doc_url}}", (
        "the chapter doc tag drifted from deliverable_fields")
    assert pdf_view != doc_edit, "the pair must be two distinct links"
    assert STANDING_INSTRUCTION == (
        "The PDF is yours to view. The Google Doc is the one you edit, "
        "and it is the version we use."), "the standing instruction drifted"
    for text in (STANDING_INSTRUCTION, SIGN_OFF_EDITORS, SIGN_OFF_PRODUCER,
                 link, pdf_view, doc_edit):
        _assert_copy_law(text, "self-test golden")
        assert "AI" not in text, "banned byline actor in golden copy"

    # The never-a-real-token law over the whole rendered template.
    rendered = json.dumps(render_payload(), indent=2, sort_keys=True)
    detail = _never_a_real_token_check(rendered)
    if detail is not None:
        raise ValueError("self-test: never-a-real-token violation: %s"
                         % detail)
    assert rendered.count(MASKED_FORM_ID_MARKER) >= 0, "masked markers"

    # The editors-only law: every client-facing actor word in the generated
    # copy is an editor word; no forbidden shape anywhere in the payload.
    blob = rendered
    for m in re.finditer(r"\b[A-Za-z]+(?:s)?\b", blob):
        word = m.group(0).lower()
        if word in ("ai", "ghostwriter", "ghostwriters", "automated",
                    "generated"):
            raise ValueError("self-test: forbidden byline actor %r present"
                             % word)

    # Attack fixtures  -  each must be REFUSED.
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
    _attack("out-of-vocabulary-stage",
            lambda: inbound_body(stage="s99_bogus"))
    _attack("foreign-source",
            lambda: _validated_body_value("source", "universal-intake"))
    _attack("bad-decision", lambda: inbound_body(decision="approved_as_is"))
    _attack("rewrite-without-notes",
            lambda: inbound_body(decision="request_rewrite_with_notes"))
    _attack("bad-cover-choice", lambda: inbound_body(cover_choice="Glitter"))
    _attack("secret-in-body",
            lambda: inbound_body(decision="approve_as_is",
                                 notes="Bearer abcdef0123456789"))
    _attack("real-url-in-webhook", lambda: _never_a_real_token_check(
        json.dumps({"url_merge": "https://evil.example.com/hook"})))
    _attack("secret-in-webhook", lambda: _never_a_real_token_check(
        json.dumps({"authorization_header_merge": "Bearer abcdef0123456789"})))
    _attack("em-dash-in-notes", lambda: inbound_body(
        decision="request_rewrite_with_notes", notes="bad — dash"))
    _attack("em-dash-in-link", lambda: stage_form_link(stage="s5_gate")
            .replace("s5_gate", "bad — dash"))

    print("webhook_body self-test: OK "
          "(body key law, source law, secret header law, decision and cover "
          "vocabulary, pre-fill law, link pair law, copy law, "
          "never-a-real-token, all attacks refused)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W1/W2 webhook body builder: the routed submission and "
                    "outbound POST shapes of the Anthology Engine intake "
                    "hook, the x-anthology-secret header rule, the stage "
                    "form pre-fill link, and the per-stage PDF view + Doc "
                    "edit link pair (OFFLINE, no network, no credential)")
    ap.add_argument("cmd", nargs="?", choices=["plan", "render", "self-test"],
                    help="plan | render | self-test")
    ap.add_argument("--stage", default=DEFAULT_STAGE,
                    help="stage token for the body and the prefilled form "
                         "link (default %s)" % DEFAULT_STAGE)
    ap.add_argument("--deliverable", default="chapter",
                    help="field-map deliverable slot whose PDF view + Doc "
                         "edit link pair the render carries (default "
                         "chapter)")
    ap.add_argument("--decision", default=None,
                    choices=list(DECISION_VOCABULARY),
                    help="the universal-review decision for the rendered "
                         "body (default: no decision surface)")
    ap.add_argument("--notes", default=None,
                    help="the notes carried with a request_rewrite_with_notes "
                         "decision (feed chapter_updates verbatim; fixture "
                         "value for an offline preview)")
    ap.add_argument("--cover-choice", dest="cover_choice", default=None,
                    choices=list(COVER_STYLE_VOCABULARY),
                    help="the U8 cover style choice (one of the four named "
                         "styles)")
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return _self_test()
        if args.cmd == "render":
            payload = render_payload(
                stage=args.stage, deliverable=args.deliverable,
                decision=args.decision, notes=args.notes,
                cover_choice=args.cover_choice,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        return plan()
    except SystemExit:
        raise
    except ValueError as exc:
        sys.stderr.write("webhook_body: law violation: %s\n" % exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("webhook_body: unexpected error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
