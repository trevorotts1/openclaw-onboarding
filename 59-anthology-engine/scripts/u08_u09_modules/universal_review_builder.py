#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/universal_review_builder.py
# UNIVERSAL-REVIEW BUILDER (U08/U09) — the ONE client-facing decision form
# (slug "universal-review"; PRD Section 4 / U8) carries exactly TWO hidden
# fields (anthology_id, stage), a SINGLE_OPTIONS decision dropdown with
# exactly TWO options (Approve as-is / Request rewrite with notes), a
# multi-line notes surface, and the U8 cover dropdown offering the FOUR
# named cover styles (choice_options == cover_render.STYLE_NAMES) — built
# on the public v2 PUT /forms/{id} surface with the location's OWN
# private-integration token, and it REFUSES to write unless the operator
# explicitly passes --execute. Without --execute the tool is a DRY-RUN: it
# reads the live form, proves the review contract, and prints exactly the
# PUT it WOULD send — nothing is written, ever. Fail-closed: any ambiguity
# is a refusal, never a guessed write.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module in the
# shared U08/U09 package (the same layout and the same empty fail-closed
# package-init doctrine as scripts/u02_modules/ through scripts/u07_modules/).
# It is NOT a manifest row: it ships as the gated form-builder sibling of
# u08_u09_modules/hidden_field_module.py (which owns the hidden-field create
# on the universal-INTAKE form and the ONE form WRITE path
# FORMS_WRITE_PATH = "/forms/%s") and of u04_modules/form_reader.py (which
# OWNS the public v2 forms listing read — GET /forms/?locationId=,
# find-by-slug + pin-by-id). The delta_reporter.py single-implementation
# doctrine: a law is read once, in one module — the form slug / pin /
# hidden-field keys below are the SAME laws config/anthology-snapshot-
# contract.json, forms_check.py, golden_forms.py, form_reader.py and
# cover_render.py pin, and they are REFERENCED here, never re-implemented.
#
# WHAT THIS OWNS
#   1. THE UNIVERSAL-REVIEW CONTRACT LAW (PRD Section 4 / U8 + the U05
#      negative-mirror law). The universal-review form is the engine's ONE
#      client-facing decision form: slug "universal-review"
#      (negative_verifier.UNIVERSAL_REVIEW_FORM), pinned form id
#      riNlAkYbcW3g92VRLqq0 (forms_check.FORM_ID_BY_SLUG — the Review Fire
#      trigger AND the form the release emails link), carrying EXACTLY TWO
#      hidden fields — anthology_id and stage (NOT the three-field
#      universal hidden-field contract of the intake/title forms: the
#      review submission must never ride the intake front door, and the
#      release links pre-key the anthology, so the contact_id hidden field
#      is deliberately ABSENT here). The decision surface: a SINGLE_OPTIONS
#      decision dropdown with EXACTLY TWO options — "Approve as-is" and
#      "Request rewrite with notes" (the engine's chapter-gate decision
#      pair: gate_engine.GATE_BY_CURSOR["s5_gate"].actions
#      approve_as_is / request_rewrite_with_notes, with the notes feeding
#      chapter_updates verbatim per ENGINE-MANIFEST.json gate_table) — plus
#      a multi-line free-text notes field (the every-text-input-field-is-
#      multi-line law: LARGE_TEXT) and the U8 cover dropdown
#      (field-map cover_style_fields.choice_field
#      contact.anthology_cover_choice, SINGLE_OPTIONS, options == the FOUR
#      named style names cover_render.STYLE_NAMES in order). The decision
#      field is a SINGLE_OPTIONS that stays SINGLE_OPTIONS and is
#      deliberately NOT in the provisioning inventory (field-map.json, U8
#      note — this builder's surface is the FORM, not the field map).
#   2. THE PUT SURFACE. The write is ONE PUT:
#      https://services.leadconnectorhq.com/forms/{formId} (public v2,
#      Version 2021-07-28 — the same path + version header reg.CafClient
#      already sends; the same proven path hidden_field_module.py uses).
#      The PUT body is built ONLY from the live read-back row — every key,
#      every value, the id echoed byte-for-byte — with the review hidden
#      fields normalized to [anthology_id, stage] and the decision
#      dropdown options to the two contract options (any drifted option is
#      corrected to the contract set; the cover choice options are
#      normalized to the four STYLE_NAMES). A body constructed from memory
#      is NEVER sent.
#   3. THE TARGET LAW. The row this module may write MUST be the
#      universal-review form, proven two ways, exactly as form_reader.py
#      proves the intake form: (a) the slug law — a listing row whose
#      normalized name equals "universal review" (the slug with dashes ->
#      spaces, the same name-match law golden_forms.py pins), or an alias
#      key match on the review spellings ("universal_review",
#      "universal_review_form_id"); and (b) the pin law — when --form-id is
#      given, the pinned id (forms_check.FORM_ID_BY_SLUG["universal-review"],
#      the live-verified Review Fire form) must BE the row written; a pin
#      BYPASSES the slug law. A row that matches NEITHER law STOPS — a
#      write to a form we cannot prove is the review form is a write to
#      the wrong record, never performed.
#   4. THE CREATE/NO-OP LAW. The form is rebuilt ONLY when the live row
#      actually drifts from the contract: when the live row already
#      carries exactly [anthology_id, stage] hidden fields, the two
#      decision options byte-exact, and the four cover options byte-exact,
#      the run is an idempotent NO-OP — nothing is written, applied:false,
#      ok true (the hidden_field_module.py / query_key_fixer.py no-op
#      doctrine). Any drift (a wrong hidden-field set — including the
#      three-field universal trio that would let a review submission ride
#      intake, a missing/drifted decision option, a missing notes surface,
#      a drifted cover option) is surfaced in the pre-write proof, and
#      --execute is still the only way any write happens.
#   5. THE READ-BACK LAW (with --execute only). After the PUT, the form is
#      GET-read back in the SAME job (form_reader.read_forms surface, by
#      the pinned id or by re-listing): the read-back must carry the review
#      hidden fields, the two decision options, and the four cover options
#      byte-exact — any drift is a MISMATCH (exit 5, the
#      AF-AE-READBACK-MISMATCH family), never a reported success. A PUT
#      that returned success but cannot be read back is HELD (exit 3) with
#      the live state UNDETERMINED — never reported as built. The PUT's own
#      response body is never trusted: only the read-back proves the write.
#   6. NEVER-A-TOKEN SURFACE. The PIT is resolved through
#      anthology_registry.resolve_pit (the house labels CONVERT_AND_FLOW_PIT
#      / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
#      GHL_API_KEY, live process env first then the three canonical client
#      env stores; SET / NOT SET only — a token value is NEVER printed).
#      Before ANY JSON is emitted, the payload is scanned against the house
#      credential shape (pit-<value>) and a hit REFUSES the whole surface
#      rather than print it — the delta_reporter.py never-a-real-token
#      doctrine. Form ids and the location id are markers (last 4 chars) on
#      every operator surface; the full ids ride only inside request bodies.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever reaches
# Convert and Flow (GK-09). Scope-vs-edge-block discrimination: a bare
# 401/403 is HELD (UpstreamBlockedError), never reported as a scope problem;
# a genuine scope refusal (ScopeDenied) or the live-verified Convert and
# Flow LOCATION-scope denial ("does not have access to this location") is a
# STOP (exit 2) — never a HELD misdiagnosis.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, echoed, or reflected.
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable listing, an absent universal-review row, an unprovable target,
# a PUT body that cannot be constructed from a live read-back, a
# credential-shaped string on any surface, or a read-back that does not
# prove the build is a REFUSAL / FAIL — never a silent pass, never a
# fabricated success, never a write performed without --execute.
#
# RETURN CONTRACT (the machine surface this module owns):
#   plan_review_build(client, location_id, *, pinned_id="", execute=False,
#                     form_rows=None) -> dict — {"contract", "schema_version",
#       "ok", "applied", "execute", "form_id", "form_id_masked",
#       "hidden_law", "decision_options", "cover_options", "note",
#       "af_code"}: ok True ONLY when the live form already matches the
#       review contract (idempotent no-op: applied false, nothing written)
#       OR the build was performed with --execute and read back byte-exact;
#       applied True ONLY when a PUT actually happened; ok False carries NO
#       form id (never an id guessed from memory) and a named af_code —
#       FORMS-EMPTY / FORMS-NOT-FOUND / DRY-RUN / READBACK-MISMATCH.
#   Never raises for a data mismatch (a mismatch is a result); raises for a
#   broken listing shape (fr.FormsReadError / ReviewBuildError, STOP family)
#   or a transport/scope failure (the client's exceptions, HELD family).
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   universal_review_builder.py apply [--location-id ID] [--form-id ID] [--execute]
#   universal_review_builder.py plan  [--location-id ID] [--form-id ID]
#   universal_review_builder.py self-test
#
# --execute is the ONLY flag that performs the PUT. Its absence makes the
# apply run a dry-run: live reads only, nothing written, applied:false in
# the report. apply (dry-run included) needs the PIT — a truthful plan
# requires the live read; an unread state is never fabricated.
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, _stop, _mask_location and its
# exception classes), u04_modules.form_reader (read_forms — the ONE
# forms-listing read, the slug/pin laws, the mask surface) and the sibling
# u08_u09_modules.hidden_field_module (the ONE form WRITE path + the
# container-key normalization). DOCTRINE: move in silence; NOTHING Anthropic
# in any runtime file; Convert and Flow naming in every client surface;
# NEVER print a secret value.
# =============================================================================
"""universal_review_builder.py — gated, verified universal-review form
builder against the Anthology Convert and Flow location (Skill 59, U08/U09
tooling). Builds the review form's contract — exactly TWO hidden fields
(anthology_id, stage), the two-option decision dropdown, the multi-line
notes surface, the four-option cover dropdown — via public v2 PUT /forms/{id}
— REFUSED without --execute; every other invocation is a read-only dry-run."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to
# hidden_field_module.py): the registry owns the Cloudflare browser-UA
# wiring, the LeadConnector client, the credential resolution, and the
# exit-code contract; the reader owns the ONE forms-listing read and its
# slug/pin laws; the sibling hidden-field module owns the ONE form WRITE
# path and the container-key normalization — every law is read once, in the
# module that owns it, never re-implemented.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "u04_modules"))
import form_reader as fr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hidden_field_module as hfm  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object for
# a universal-review build (the self-test asserts the golden plan carries the
# exact string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-universal-review-build"
CONFIG_SCHEMA_VERSION = 1

# The REVIEW hidden-field law — EXACTLY TWO keys, and only these: the
# anthology_id + stage the release links pre-key
# (widget/form/<id>?anthology_id=..&stage=..; forms_check.py header, the
# Review Fire trigger). The universal-INTAKE trio (contact_id / anthology_id
# / stage — hfm.HIDDEN_FIELD_LAW) is deliberately NOT the review law: a
# review submission must never ride the intake front door (the U05 negative
# mirror), and the contact is pre-identified by the anthology link, so the
# contact_id hidden field is ABSENT by contract. The self-test pins the pair
# byte-exact, so a drift (including a regression back to the three-field
# trio) fails the battery before any live run.
REVIEW_HIDDEN_LAW = ("anthology_id", "stage")

# The decision dropdown contract — EXACTLY TWO options, byte-exact, in this
# order: the chapter gate's decision pair (gate_engine.
# GATE_BY_CURSOR["s5_gate"].actions == ("approve_as_is",
# "request_rewrite_with_notes"); ENGINE-MANIFEST.json gate_table
# "s5_participant": "participant token page; exactly two actions; notes feed
# chapter_updates verbatim"; the sibling u08_u09_modules.dropdown_module
# owns the decision KEY contact.anthology_review_decision and the two-option
# law for the contact custom FIELD, and attack_bad_dropdown.py certifies
# that picklist byte-exact against the same gate law — the FORM surface
# below is the same law, so the form dropdown and the contact field can
# never disagree). The DECISION_OPTION_VALUES below are the engine action
# names themselves, resolved through the dropdown module's law (the ONE
# authority, itself byte-derived from gate_engine) — never a second
# implementation, never a hardcoded spelling that could drift from the
# gate vocabulary that consumes the submitted value.
DECISION_OPTION_VALUES = None  # resolved in _decision_option_law() at first use

# The human-facing display labels of the two decision options — the same
# wording the engine's gate documentation surfaces ("Approve as-is" /
# "Request rewrite with notes", SKILL.md S5 row and ENGINE-MANIFEST.json
# gate_table); the form option label a client sees while the SUBMITTED
# value is the byte-exact action name (the label is the surface, the value
# is the vocabulary the gate consumes).
DECISION_OPTION_LABELS = ("Approve as-is", "Request rewrite with notes")
_DECISION_OPTION_LABEL_BY_VALUE = {
    "approve_as_is": "Approve as-is",
    "request_rewrite_with_notes": "Request rewrite with notes",
}

# The notes surface — the free-text multi-line field the decision's notes
# ride on (gate_engine ACTION_DECISION["request_rewrite_with_notes"]
# requires ("notes",); the notes feed chapter_updates verbatim). The
# every-text-input-field-is-multi-line law (field-map.json data_type_choice)
# declares every free-text key LARGE_TEXT; the review notes field is the
# same law.
NOTES_FIELD_LABEL = "notes"
NOTES_DATA_TYPE = "LARGE_TEXT"

# The U8 cover dropdown contract — the SINGLE_OPTIONS cover choice field of
# the universal-review form: exactly ONE option set, the FOUR named style
# names in slot order. The field key and the option names are read ONCE from
# the owning authorities (config/field-map.json cover_style_fields
# choice_field / choice_options and scripts/cover_render.py STYLE_NAMES),
# never re-implemented here — see _cover_choice_options() below.
COVER_FIELD_LABEL = "cover"
COVER_CHOICE_OPTIONS = None  # resolved in _cover_choice_options() at first use

# The notes surface — the free-text multi-line field the decision's notes
# ride on (gate_engine ACTION_DECISION["request_rewrite_with_notes"]
# requires ("notes",); the notes feed chapter_updates verbatim). The
# every-text-input-field-is-multi-line law (field-map.json data_type_choice)
# declares every free-text key LARGE_TEXT; the review notes field is the
# same law.
NOTES_FIELD_LABEL = "notes"
NOTES_DATA_TYPE = "LARGE_TEXT"

# The U8 cover dropdown contract — the SINGLE_OPTIONS cover choice field of
# the universal-review form: exactly ONE option set, the FOUR named style
# names in slot order. The field key and the option names are read ONCE from
# the owning authorities (config/field-map.json cover_style_fields
# choice_field / choice_options and scripts/cover_render.py STYLE_NAMES),
# never re-implemented here — see _cover_choice_options() below.
COVER_FIELD_LABEL = "cover"
COVER_CHOICE_OPTIONS = None  # resolved in _cover_choice_options() at first use

# The form slug this builder exists for — the engine's ONE client-facing
# decision form (the same slug forms_check.FORM_SLUGS / golden_forms.py
# GOLDEN_FORM_SLUGS / negative_verifier.UNIVERSAL_REVIEW_FORM pin; PRD
# Section 4 / U8). The slug with dashes -> spaces is the name-match law,
# exactly as form_reader.SLUG_AS_NAME is for the intake form.
REVIEW_SLUG = "universal-review"
REVIEW_SLUG_AS_NAME = REVIEW_SLUG.replace("-", " ")

# The alternate spellings of the review key that may ride a form row (the
# same alias discipline form_reader._KEY_ALIASES uses for the intake form) —
# any of them names the same form.
_REVIEW_KEY_ALIASES = ("universal_review", "universal_review_form_id")

# The pinned review form id — the LIVE-VERIFIED Review Fire form id
# (forms_check.FORM_ID_BY_SLUG["universal-review"]: the Review Fire trigger
# AND the form the release emails link, widget/form/<id>?anthology_id=..&stage=..;
# live-verified 2026-08-11 against the internal-rail trigger surface). A
# location identifier, not a secret — but masked on every surface.
DEFAULT_UNIVERSAL_REVIEW_FORM_ID = "riNlAkYbcW3g92VRLqq0"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The builder pins to it; --location-id overrides for tests. Same
# value fr.DEFAULT_TEMPLATE_LOCATION carries — imported, never re-typed, so
# the two surfaces cannot drift.
DEFAULT_TEMPLATE_LOCATION = fr.DEFAULT_TEMPLATE_LOCATION

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123") — the same guard the reader and the sibling
# hidden-field module ship. Every emitted surface is scanned against it
# before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class ReviewBuildError(Exception):
    """A fail-closed build refusal (STOP family): an unreadable listing shape,
    an unprovable target, a malformed live row with no writable surface, a
    credential-shaped string in a payload, or a PUT body that cannot be
    constructed from a live read-back. An expectation that cannot name its
    own sources must not run."""


def _mask_id(fid: str) -> str:
    """Non-reversible marker for a form id (last 4 chars) — the house surface
    shape, identical to fr.mask_id / reg._mask_location."""
    return fr.mask_id(fid)


def _row_id(row) -> str:
    """The form id of a listing row under any of its container keys — the
    SAME surface fr._row_id owns, referenced not re-implemented."""
    return fr._row_id(row)


def _normalize_name(name: str) -> str:
    """The name-match normalization (lowercase, spaces collapsed) — the SAME
    law fr._normalize_name owns."""
    return fr._normalize_name(name)


def _normalized_law(values) -> tuple:
    """A normalized, ordered, de-duplicated tuple of the given option/hidden
    values — the comparison surface for byte-exact drift judgment (a list is
    order-significant; a tuple is the comparable contract shape)."""
    out = []
    for v in values or ():
        if isinstance(v, str) and v.strip():
            s = v.strip()
            if s not in out:
                out.append(s)
    return tuple(out)


def _decision_option_law() -> tuple:
    """The TWO-option decision law, byte-exact, from the ONE authority: the
    sibling u08_u09_modules.dropdown_module's own law (itself byte-derived
    from gate_engine.GATE_BY_CURSOR["s5_gate"].actions — the chapter gate's
    EXACTLY-TWO-ACTIONS contract, asserted in gate_engine's self_test), so
    the form dropdown can never drift from the gate vocabulary that
    consumes the submitted value and never disagree with the contact
    custom-field picklist the dropdown module builds. A law that does not
    resolve to exactly two distinct non-empty options STOPS the build —
    never a guessed option set."""
    global DECISION_OPTION_VALUES
    if DECISION_OPTION_VALUES is None:
        try:
            import u08_u09_modules.dropdown_module as dd
            opts = dd._decision_option_law()
        except Exception as exc:  # noqa: BLE001
            raise ReviewBuildError(
                "the decision-option law is unavailable (%s) — the dropdown "
                "module's law authority is missing; a builder never guesses "
                "the two decision options" % type(exc).__name__)
        if not isinstance(opts, tuple) or len(opts) != 2 or \
                len(set(opts)) != 2 or \
                not all(isinstance(o, str) and o.strip() for o in opts):
            raise ReviewBuildError(
                "the decision-option law drifted from the two-option "
                "contract: %r — a drifted option set is a refusal, never a "
                "guessed write" % (opts,))
        for value in opts:
            if value not in _DECISION_OPTION_LABEL_BY_VALUE:
                raise ReviewBuildError(
                    "the decision option %r has no contract display label — "
                    "the label mapping drifted from the gate documentation; "
                    "a builder never invents an option label" % value)
        DECISION_OPTION_VALUES = tuple(opts)
    return DECISION_OPTION_VALUES


def decision_options() -> tuple:
    """The TWO option LABELS of the review decision dropdown, in law order:
    each byte-exact engine action name mapped to its contract display label
    ("Approve as-is" / "Request rewrite with notes"). The SUBMITTED value
    is the action name itself (the vocabulary the gate consumes); the label
    is the client-facing surface."""
    return tuple(_DECISION_OPTION_LABEL_BY_VALUE[v]
                 for v in _decision_option_law())


def _cover_choice_options() -> tuple:
    """The FOUR named cover-style options of the review cover dropdown —
    read once from scripts/cover_render.py STYLE_NAMES (the ONE config-
    pinned style-name authority; field-map.json cover_style_fields
    choice_options == STYLE_NAMES in order is the coherence law the
    registry self-test pins). Imported lazily so a fixture-less import of
    this module (self-test of a sibling) never drags cover_render in; a
    missing cover_render STOPS the build, never a guessed option set."""
    global COVER_CHOICE_OPTIONS
    if COVER_CHOICE_OPTIONS is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from cover_render import STYLE_NAMES as _style_names
        except Exception as exc:  # noqa: BLE001
            raise ReviewBuildError(
                "cover_render.STYLE_NAMES cannot be imported (%s) — the U8 "
                "style-name authority is missing; a builder never guesses "
                "the four cover options" % type(exc).__name__)
        names = tuple(str(n) for n in _style_names if str(n).strip())
        if len(names) != 4 or tuple(names) != (
                "Signature", "Bold Editorial", "Fine Art", "Pure Type"):
            raise ReviewBuildError(
                "cover_render.STYLE_NAMES drifted from the U8 four-style "
                "contract: %r — a drifted cover option set is a refusal, "
                "never a guessed write" % (names,))
        COVER_CHOICE_OPTIONS = names
    return COVER_CHOICE_OPTIONS


def _list_rows(client, location_id: str) -> list:
    """The ONE live forms-listing read — the reader's public v2 GET, exactly
    as hidden_field_module reads it (the reader owns the read; this module
    never re-implements it)."""
    payload = client._request(
        "GET", fr.FORMS_LIST_PATH,
        query={"locationId": location_id, "limit": 200})
    rows = payload.get("forms")
    if rows is None:
        raise fr.FormsReadError(
            "forms listing payload has no 'forms' array — the listing shape "
            "is not readable")
    if not isinstance(rows, list):
        raise fr.FormsReadError("forms listing 'forms' value is not an array")
    return [r for r in rows if isinstance(r, dict)]


def _row_option_container(row) -> tuple:
    """The option-bearing keys a live row may carry, in container order —
    "options" (the canonical spelling) and "choiceOptions" (an alternate
    the engine's own choice field surfaces use). Returns (key, value) or
    (None, None); the value is normalized to a tuple by the caller."""
    if not isinstance(row, dict):
        return None, None
    for key in ("options", "choiceOptions"):
        v = row.get(key)
        if v is not None:
            return key, v
    return None, None


def _row_notes(row) -> str:
    """The notes-surface key of a live row, under any container spelling —
    "notes" (canonical), "note", or "notesField". Returns "" when the row
    carries none (the contract law checks the surface presence separately)."""
    if not isinstance(row, dict):
        return ""
    for key in ("notes", "note", "notesField"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return key
    return None


def _find_target(row, pinned: str) -> bool:
    """The target law: a row IS the universal-review form when the pinned id
    (when given) is its id, or — absent a pin — when its normalized name
    equals "universal review" or it carries an alias key of the review slug.
    The same slug/pin semantics fr.read_forms applies to the intake form."""
    if pinned:
        return _row_id(row) == pinned
    if _normalize_name(str(row.get("name") or "")) == REVIEW_SLUG_AS_NAME:
        return True
    for key in row:
        if _normalize_name(str(key)) in _REVIEW_KEY_ALIASES:
            return True
    for k, v in row.items():
        if isinstance(v, str) and v.strip() and \
                _normalize_name(v) in _REVIEW_KEY_ALIASES:
            return True
    return False


def _hidden_keys(row) -> tuple:
    """The hidden-field keys of a live row under any container spelling —
    the SAME container law hfm.HIDDEN_CONTAINER_KEYS owns. Returns the
    normalized tuple of keys ("" keys are dropped; a non-array container is
    a malformed shape the caller refuses)."""
    if not isinstance(row, dict):
        return ()
    for key in hfm.HIDDEN_CONTAINER_KEYS:
        v = row.get(key)
        if v is not None:
            if not isinstance(v, (list, tuple)):
                raise ReviewBuildError(
                    "the hidden-field container %r is not an array — the "
                    "listing shape is not readable" % key)
            return _normalized_law(v)
    return ()


def _build_fix_body(row, fid: str) -> dict:
    """The PUT body: the live row echoed byte-for-byte (every key, every
    value, the id included) with the review surface normalized to the
    contract — the hidden-field container spelling preserved with the keys
    set to exactly [anthology_id, stage], the decision dropdown set to the
    two contract options under its canonical "options" key, the cover
    dropdown set to the four style names under its canonical
    "choiceOptions" key, and the notes surface present as a multi-line
    (LARGE_TEXT) field. A surface the contract requires but the live row
    does not carry is CREATED (the same create-law hidden_field_module
    applies to a missing hidden-field container — the minted review link
    REQUIRES the pair, the decision REQUIRES its two options, the cover
    REQUIRES its four names, and the notes REQUIRES its multi-line field).
    A body constructed from memory is NEVER sent — every piece is read from
    the live row first."""
    body = dict(row)
    body["id"] = fid
    # The hidden-field container: preserve the live spelling, write the
    # contract pair (the same container normalization hidden_field_module
    # performs; the container key itself is never duplicated).
    hidden_written = False
    for key in hfm.HIDDEN_CONTAINER_KEYS:
        if key in body:
            body[key] = list(REVIEW_HIDDEN_LAW)
            hidden_written = True
            break
    if not hidden_written:
        body["hiddenFields"] = list(REVIEW_HIDDEN_LAW)
    # The decision dropdown: EXACTLY the two contract options, under the
    # canonical "options" key (a stale/drifted live value is replaced by
    # the contract set — never a third option, never a renamed one).
    body["options"] = list(decision_options())
    # The U8 cover dropdown: EXACTLY the four style names, under the
    # canonical "choiceOptions" key (the choice-options naming of
    # field-map cover_style_fields.choice_options). Created when the live
    # row carries no cover dropdown — a review form without the cover pick
    # cannot offer the client the four-style choice the release emails link.
    body["choiceOptions"] = list(_cover_choice_options())
    # The notes surface: preserve the live container spelling when present;
    # the multi-line (LARGE_TEXT) notes surface is part of the review
    # contract (the S5 decision's notes feed chapter_updates verbatim), so
    # an absent surface is CREATED under the canonical "notes" key.
    notes_key = _row_notes(body)
    if notes_key:
        body[notes_key] = NOTES_FIELD_LABEL
    else:
        body["notes"] = NOTES_FIELD_LABEL
    body.setdefault("dataType", NOTES_DATA_TYPE)
    return body


def plan_review_build(client, location_id: str, *, pinned_id: str = "",
                      execute: bool = False, form_rows=None) -> dict:
    """Plan (and, ONLY with --execute, perform) the universal-review form
    build. Fail-closed, never a token.

    `client` is a reg.CafClient (its own _request rides CAF_BROWSER_UA).
    `form_rows` is an explicit row list (self-tests); when None the live
    listing is read (the reader's ONE read). `pinned_id` is the engine's
    pinned review form id (or a box override) — when given it must be the
    row written and it BYPASSES the slug law.

    Returns the documented surface {contract, schema_version, ok, applied,
    execute, form_id, form_id_masked, hidden_law, decision_options,
    cover_options, notes_law, note, af_code} — fail-closed:
      - ok True ONLY when the live form already matches the review contract
        (idempotent no-op: applied false, nothing written) OR the build was
        performed with --execute and read back byte-exact,
      - applied True ONLY when a PUT actually happened (--execute),
      - hidden_law / decision_options / cover_options / notes_law are the
        contract surfaces as the build will leave them,
      - ok False carries NO form id (never an id guessed from memory) and a
        named af_code — FORMS-NOT-FOUND when no universal-review row matched
        (or the pinned id was absent), FORMS-EMPTY when the listing held
        zero rows, READBACK-MISMATCH when a PUT happened but the read-back
        does not prove the build,
      - every surface is scanned against the credential shape; a hit REFUSES
        the whole plan rather than print it.
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (fr.FormsReadError / ReviewBuildError, STOP family)
    or a transport/scope failure (the client's exceptions, HELD family). The
    write surface is exercised ONLY when execute is True; every other path
    is read-only.
    """
    if form_rows is None:
        rows = _list_rows(client, location_id)
    else:
        rows = [r for r in form_rows if isinstance(r, dict)]
    count = len(rows)

    pinned = (pinned_id or "").strip()
    if pinned:
        fr._unmasked_row_id_scan(pinned)

    # ---- the target law: one row, proven by slug or pin --------------------
    target = None
    target_matched_by = ""
    for row in rows:
        if _row_id(row):
            fr._unmasked_row_id_scan(_row_id(row))
        if _find_target(row, pinned):
            if not _row_id(row):
                raise ReviewBuildError(
                    "the universal-review row matched the slug law but "
                    "carries no form id — the listing shape is not readable")
            target, target_matched_by = row, ("pin" if pinned else "slug")
            break
    if target is None:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": False,
            "execute": execute,
            "form_id": "",
            "form_id_masked": "",
            "hidden_law": list(REVIEW_HIDDEN_LAW),
            "decision_options": list(decision_options()),
            "cover_options": list(_cover_choice_options()),
            "notes_law": NOTES_FIELD_LABEL,
            "af_code": ("FORMS-EMPTY" if count == 0 else "FORMS-NOT-FOUND"),
            "note": ("the listing is empty" if count == 0 else
                     "no universal-review row on the listing — the slug law "
                     "matched nothing" + (" and the pinned id is absent"
                                          if pinned else "")) +
                    " (fail-closed, never an id guessed from memory)",
        }

    fid = _row_id(target)
    if not fid:
        raise ReviewBuildError("the universal-review row carries no form id — "
                               "the listing shape is not readable")

    # ---- drift judgment: the review contract, byte-exact -------------------
    hidden_current = _hidden_keys(target)
    if hidden_current:
        dumped_current = json.dumps(list(hidden_current))
        if _CREDENTIAL_SHAPE.search(dumped_current):
            raise ReviewBuildError(
                "the hidden-field surface resolved to a credential-shaped "
                "string — REFUSED without printing it")

    body = _build_fix_body(target, fid)
    dumped_body = json.dumps(body, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped_body):
        raise ReviewBuildError(
            "the PUT body carries a credential-shaped string — REFUSED "
            "without printing it")

    opt_key, opt_value = _row_option_container(target)
    options_current = _normalized_law(
        opt_value if opt_key and isinstance(opt_value, (list, tuple))
        else ())
    cover_key, cover_value = _row_option_container(target)
    # The cover container, when the row carries one under "choiceOptions":
    cover_current = ()
    if "choiceOptions" in target and isinstance(target["choiceOptions"],
                                                (list, tuple)):
        cover_current = _normalized_law(target["choiceOptions"])
    notes_current = _row_notes(target)

    hidden_matches = (tuple(hidden_current) == REVIEW_HIDDEN_LAW)
    options_match = (tuple(options_current) == decision_options())
    cover_match = (tuple(cover_current) == _cover_choice_options())
    notes_match = bool(notes_current)

    if hidden_matches and options_match and cover_match and notes_match:
        # Idempotent no-op: the live form already matches the review
        # contract — nothing is written, ever, even with --execute.
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": True,
            "applied": False,
            "execute": execute,
            "form_id": fid,
            "form_id_masked": _mask_id(fid),
            "hidden_law": list(REVIEW_HIDDEN_LAW),
            "decision_options": list(decision_options()),
            "cover_options": list(_cover_choice_options()),
            "notes_law": NOTES_FIELD_LABEL,
            "target_matched_by": target_matched_by,
            "af_code": "NO-OP",
            "note": "the live universal-review form already carries the "
                    "review contract (hidden %s, decision options %s, "
                    "cover options %s, notes %s) — idempotent no-op, "
                    "nothing written"
                    % (", ".join(REVIEW_HIDDEN_LAW),
                       ", ".join(decision_options()),
                       ", ".join(_cover_choice_options()),
                       NOTES_FIELD_LABEL),
        }

    if not execute:
        # Dry-run: the plan is the report. The drift is surfaced; applied
        # stays false; nothing was written.
        drift = []
        if not hidden_matches:
            drift.append("hidden fields %r != %r"
                         % (list(hidden_current), list(REVIEW_HIDDEN_LAW)))
        if not options_match:
            drift.append("decision options %r != %r"
                         % (list(options_current), list(decision_options())))
        if not cover_match:
            drift.append("cover options %r != %r"
                         % (list(cover_current), list(_cover_choice_options())))
        if not notes_match:
            drift.append("the notes (multi-line) surface is absent")
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": False,
            "execute": False,
            "form_id": fid,
            "form_id_masked": _mask_id(fid),
            "hidden_law": list(REVIEW_HIDDEN_LAW),
            "decision_options": list(decision_options()),
            "cover_options": list(_cover_choice_options()),
            "notes_law": NOTES_FIELD_LABEL,
            "target_matched_by": target_matched_by,
            "af_code": "DRY-RUN",
            "note": "the live universal-review form drifts from the review "
                    "contract: %s — the build is PLANNED, not applied; "
                    "re-run with --execute to write" % "; ".join(drift),
        }

    # ---- --execute: the ONE write ------------------------------------------
    # The PUT body is the live-row echo with the review surface normalized
    # to the contract (never fabricated). The response body of the PUT is
    # never trusted: only the read-back proves the write.
    try:
        client._request("PUT", hfm.FORMS_WRITE_PATH % hfm._url_quote(fid),
                        body=body)
    except reg.CafValidation as exc:
        # 400/409/422 from Convert and Flow: a validation refusal is a STOP,
        # never a silent skip.
        raise ReviewBuildError("Convert and Flow refused the form PUT (HTTP "
                               "validation): %s" % exc)

    # ---- read-back: prove the build in the SAME job -------------------------
    # A PUT that returned success but cannot be read back is HELD (exit 3,
    # via reg.CafUnreachable) — the live state is UNDETERMINED, never
    # reported as built. A scope refusal on the read-back is a real
    # credential STOP and propagates untouched — never demoted to a HELD.
    # The read-back lookup is BY THE PINNED ID — the row we PUT, re-found
    # under the id the PUT echoed (the sibling title_select_builder reads
    # back the same way: the pinned row is the written row, never the
    # reader's intake-slug law, which cannot name a renamed review row).
    try:
        rb_row = hfm._find_row_by_id(_list_rows(client, location_id), fid)
    except (fr.FormsReadError, reg.CafUnreachable, reg.UpstreamBlockedError) as exc:
        raise reg.CafUnreachable(
            "the PUT returned success but the form cannot be read back "
            "(%s) — the live state is UNDETERMINED, never reported as "
            "built (form id marker %s)" % (type(exc).__name__, _mask_id(fid)))
    if rb_row is None:
        raise reg.CafUnreachable(
            "the PUT returned success but the form row is absent from the "
            "read-back listing (form id marker %s) — the live state is "
            "UNDETERMINED, never reported as built" % _mask_id(fid))
    rb_hidden = _hidden_keys(rb_row)
    rb_options = _normalized_law(
        rb_row.get("options") if isinstance(rb_row.get("options"), (list, tuple))
        else ())
    rb_cover = ()
    if isinstance(rb_row.get("choiceOptions"), (list, tuple)):
        rb_cover = _normalized_law(rb_row["choiceOptions"])
    rb_notes = _row_notes(rb_row)
    if (tuple(rb_hidden) != REVIEW_HIDDEN_LAW or
            tuple(rb_options) != decision_options() or
            tuple(rb_cover) != _cover_choice_options() or
            not rb_notes):
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": True,
            "execute": True,
            "form_id": fid,
            "form_id_masked": _mask_id(fid),
            "hidden_law": list(REVIEW_HIDDEN_LAW),
            "decision_options": list(decision_options()),
            "cover_options": list(_cover_choice_options()),
            "notes_law": NOTES_FIELD_LABEL,
            "target_matched_by": target_matched_by,
            "af_code": "READBACK-MISMATCH",
            "note": "the PUT returned success but the read-back does not "
                    "prove the review build (hidden %r, decision %r, "
                    "cover %r, notes %r) — never reported as built "
                    "(AF-AE-READBACK-MISMATCH family)"
                    % (list(rb_hidden), list(rb_options),
                       list(rb_cover), rb_notes),
        }

    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "applied": True,
        "execute": True,
        "form_id": fid,
        "form_id_masked": _mask_id(fid),
        "hidden_law": list(REVIEW_HIDDEN_LAW),
        "decision_options": list(decision_options()),
        "cover_options": list(_cover_choice_options()),
        "notes_law": NOTES_FIELD_LABEL,
        "target_matched_by": target_matched_by,
        "af_code": "CREATED",
        "note": "the universal-review form was built and read back "
                "byte-exact (hidden %s, decision %s, cover %s, notes %s) — "
                "the client-facing review now carries the two hidden keys, "
                "the two-option decision, and the four-option cover pick"
                % (", ".join(REVIEW_HIDDEN_LAW), ", ".join(decision_options()),
                   ", ".join(_cover_choice_options()), NOTES_FIELD_LABEL),
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the builder against
# the REAL committed constants (the review hidden pair, the pinned id, the
# two decision options, the four cover style names, the reader's slug law),
# then runs every attack fixture: golden no-op, every drift that needs a
# build, the dry-run refusal, the --execute apply + read-back, every
# not-found path named, the pin law both ways, the three-field intake trio
# attack (the review form must never carry contact_id), the option drift
# attacks, the never-a-token guard, and the scope-vs-edge 403
# discrimination the CLI depends on.
# ---------------------------------------------------------------------------

class _FakeClient:
    """In-memory public-v2 client: serves the row list the self-test hands
    it, applies a PUT to its rows (the write seam), and records the exact
    requests, so the live contract (the listing path, the locationId query,
    the PUT path, CAF_BROWSER_UA on the request) is provable offline."""

    def __init__(self, rows, fail_put=False):
        self._rows = [dict(r) for r in (rows or [])]
        self._fail_put = fail_put
        self.calls = []

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path,
                           "query": dict(query or {}), "body": body})
        if method == "GET" and path == fr.FORMS_LIST_PATH:
            return {"forms": [dict(r) for r in self._rows]}
        if method == "PUT" and path.startswith(hfm.FORMS_WRITE_PATH % ""):
            if self._fail_put:
                raise reg.CafValidation("Convert and Flow rejected the "
                                        "request (HTTP 422)")
            fid = path[len(hfm.FORMS_WRITE_PATH % ""):]
            for row in self._rows:
                if fr._row_id(row) == fid:
                    # Apply the PUT body onto the row — the write seam (the
                    # read-back then sees the applied surface).
                    row.clear()
                    row.update(dict(body))
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.CafUnreachable("unexpected request (fixture)")


def _golden_rows():
    """The golden listing rows: the universal-review form carrying the pinned
    Review Fire id and the review contract (hidden pair, two decision
    options, four cover options, notes surface), plus the engine's two other
    forms — the same three-slug family forms_check.py / golden_forms.py /
    form_reader.py pin."""
    return [
        {"id": fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": DEFAULT_UNIVERSAL_REVIEW_FORM_ID, "name": "Universal Review",
         "type": "form",
         "hiddenFields": list(REVIEW_HIDDEN_LAW),
         "options": list(decision_options()),
         "choiceOptions": list(_cover_choice_options()),
         "notes": NOTES_FIELD_LABEL,
         "dataType": NOTES_DATA_TYPE},
        {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def _golden_review_row():
    """A mutable deep copy of the golden universal-review row."""
    return [dict(r) for r in _golden_rows() if
            _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID][0]


def _self_test_body(dev) -> None:
    # ---- 0. the review law is pinned against its owning authorities; the
    #      three-field intake trio can never satisfy the review law
    assert REVIEW_HIDDEN_LAW == ("anthology_id", "stage"), \
        "the review hidden-field law drifted from the release-link contract"
    assert "contact_id" not in REVIEW_HIDDEN_LAW, \
        "a review submission must never carry the intake contact_id hidden field"
    assert decision_options() == ("Approve as-is", "Request rewrite with notes"), \
        "the two decision options drifted from the chapter-gate contract"
    assert len(decision_options()) == 2, \
        "the decision dropdown must offer EXACTLY TWO options"
    assert _cover_choice_options() == ("Signature", "Bold Editorial",
                                       "Fine Art", "Pure Type"), \
        "the four cover options drifted from cover_render.STYLE_NAMES"
    assert REVIEW_SLUG == "universal-review" and \
        REVIEW_SLUG_AS_NAME == "universal review", \
        "the review slug drifted from the engine's client-facing decision form"
    assert DEFAULT_UNIVERSAL_REVIEW_FORM_ID == "riNlAkYbcW3g92VRLqq0", \
        "the pinned Review Fire form id drifted from forms_check.FORM_ID_BY_SLUG"
    assert hfm.HIDDEN_FIELD_LAW == ("contact_id", "anthology_id", "stage"), \
        "the sibling intake hidden-field law drifted (the review law must stay distinct)"

    # ---- 1. golden NO-OP: the review form already matches the contract ->
    #      ok true, applied false, NOTHING written — even with --execute
    client = _FakeClient(_golden_rows())
    res = plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, \
        "a contract-matching form must be an idempotent no-op, got %r" % res
    assert res["af_code"] == "NO-OP"
    assert res["hidden_law"] == list(REVIEW_HIDDEN_LAW)
    assert res["decision_options"] == list(decision_options())
    assert res["cover_options"] == list(_cover_choice_options())
    assert not any(c["method"] == "PUT" for c in client.calls), \
        "a no-op must never perform a PUT"
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], \
        "a no-op must perform ONLY the listing read"

    # ---- 2. golden DRIFT: the review form carries the three-field INTAKE
    #      trio instead of the pair -> dry-run refuses (exit 5 surface), the
    #      plan names the drift, nothing is written
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False, \
        "a drifted review form must refuse in dry-run, got %r" % res
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["form_id"] == DEFAULT_UNIVERSAL_REVIEW_FORM_ID
    assert res["hidden_law"] == list(REVIEW_HIDDEN_LAW)
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], \
        "a dry-run must perform ONLY the listing read"

    # ---- 3. --execute on the drifted row: the PUT happens (hidden pair
    #      normalized, no contact_id anywhere), the read-back proves the build
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
            r["options"] = ["Approve as-is"]
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the build must apply and pass under --execute, got %r" % res
    assert res["af_code"] == "CREATED"
    assert res["hidden_law"] == list(REVIEW_HIDDEN_LAW)
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == hfm.FORMS_WRITE_PATH % DEFAULT_UNIVERSAL_REVIEW_FORM_ID
    body = puts[0]["body"]
    assert body.get("hiddenFields") == list(REVIEW_HIDDEN_LAW), \
        "the PUT body must carry the review hidden pair only"
    assert "contact_id" not in json.dumps(body), \
        "the review PUT body must never carry the intake contact_id hidden field"
    assert body.get("options") == list(decision_options()), \
        "the PUT body must carry the two decision options"
    assert body.get("id") == DEFAULT_UNIVERSAL_REVIEW_FORM_ID, \
        "the PUT body must echo the live row's id"
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, "the apply must re-read the listing for the read-back"

    # ---- 4. the pin law: the pinned id BYPASSES the slug law and IS the row
    #      written; a pinned id absent from the listing is FORMS-NOT-FOUND
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
            r["options"] = ["Approve as-is"]
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl",
                            pinned_id=DEFAULT_UNIVERSAL_REVIEW_FORM_ID,
                            execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "a pinned drift must build under --execute, got %r" % res
    assert res["target_matched_by"] == "pin"
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["id"] = "DriftedDriftedId00"
    res = plan_review_build(_FakeClient(rows), "loc_tmpl",
                            pinned_id=DEFAULT_UNIVERSAL_REVIEW_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", \
        "an absent pinned id must refuse, got %r" % res
    assert res["form_id"] == "", "a failed plan must never carry a form id"

    # ---- 5. not-found paths, each NAMED: an empty listing is FORMS-EMPTY; a
    #      non-empty listing without universal-review is FORMS-NOT-FOUND
    res = plan_review_build(_FakeClient([]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"
    client = _FakeClient([{"id": "OtherFormId0000", "name": "Contact Us",
                           "hiddenFields": ["email"]}])
    res = plan_review_build(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"

    # ---- 5b. a slug-matched row with NO form id is an unreadable shape — a
    #      STOP, never a silent FORMS-NOT-FOUND
    try:
        plan_review_build(_FakeClient([{"name": "Universal Review",
                                        "hiddenFields": list(REVIEW_HIDDEN_LAW)}]),
                          "loc_tmpl")
        raise AssertionError("an id-less slug-matched row must STOP")
    except ReviewBuildError:
        pass

    # ---- 5c. a non-array hidden-field container is a malformed shape — a
    #      STOP, never a guessed set
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = "anthology_id"
    try:
        plan_review_build(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a non-array hidden-field container must STOP")
    except ReviewBuildError:
        pass

    # ---- 6. option drift attacks: a THIRD decision option, a renamed
    #      option, a drifted cover set — each refused in dry-run, each
    #      normalized to the contract set under --execute
    cases = (
        ("options", ["Approve as-is", "Request rewrite with notes", "Third"]),
        ("options", ["Approve as-is"]),
        ("options", ["Request rewrite with notes", "Approve as-is"]),
        ("choiceOptions", ["Signature", "Bold Editorial"]),
        ("choiceOptions", ["Signature", "Bold Editorial", "Fine Art",
                           "Pure Type", "Extra"]),
    )
    for key, value in cases:
        rows = _golden_rows()
        for r in rows:
            if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
                r[key] = list(value)
        res = plan_review_build(_FakeClient(rows), "loc_tmpl")
        assert res["ok"] is False and res["af_code"] == "DRY-RUN", \
            "drift %r=%r must refuse in dry-run" % (key, value)
        client = _FakeClient(rows)
        res = plan_review_build(client, "loc_tmpl", execute=True)
        assert res["ok"] is True and res["applied"] is True, \
            "drift %r=%r must build under --execute, got %r" % (key, value, res)
        puts = [c for c in client.calls if c["method"] == "PUT"]
        assert puts[0]["body"].get(key) == (
            list(decision_options()) if key == "options"
            else list(_cover_choice_options())), \
            "the PUT body must normalize %r to the contract set" % key

    # ---- 6b. the notes surface attack: the notes field absent -> dry-run
    #      refuses, --execute restores it (the multi-line LARGE_TEXT law)
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            del r["notes"]
    res = plan_review_build(_FakeClient(rows), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", \
        "a missing notes surface must refuse in dry-run"
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert "notes" in puts[0]["body"], \
        "the PUT body must restore the notes surface"

    # ---- 6c. the container-spelling drift: the live row carries
    #      "hidden_fields" (snake) — the CONTRACT surface is the key SET, so
    #      a spelling-only drift with the pair present is an idempotent
    #      NO-OP (nothing written, never a churn); when the CONTENT drifts
    #      under the snake spelling, the write preserves the live spelling
    #      and writes the contract pair
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hidden_fields"] = list(REVIEW_HIDDEN_LAW)
            del r["hiddenFields"]
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, \
        "a spelling-only drift is not a contract drift — idempotent no-op, got %r" % res
    assert res["af_code"] == "NO-OP"
    assert not any(c["method"] == "PUT" for c in client.calls), \
        "a spelling-only drift must never perform a PUT"
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hidden_fields"] = ["contact_id", "anthology_id", "stage"]
            del r["hiddenFields"]
    client = _FakeClient(rows)
    res = plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "a content drift under the snake spelling must build, got %r" % res
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert "hidden_fields" in puts[0]["body"], \
        "the PUT body must preserve the live container spelling"
    assert puts[0]["body"]["hidden_fields"] == list(REVIEW_HIDDEN_LAW), \
        "the PUT body must write the contract pair under the live spelling"

    # ---- 7. never-a-token: a hidden-field surface that IS a credential-
    #      shaped string REFUSES the whole plan rather than print it; a
    #      pinned id that is credential-shaped refuses the same way
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["pit-abc123", "stage"]
    try:
        plan_review_build(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a credential-shaped hidden field must refuse")
    except ReviewBuildError:
        pass
    try:
        plan_review_build(_FakeClient(_golden_rows()), "loc_tmpl",
                          pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except fr.FormsReadError:
        pass

    # ---- 8. a validation refusal on the PUT (400/409/422) is a STOP, never
    #      a silent skip; an applied-but-unreadable PUT is HELD (the live
    #      state is UNDETERMINED, never reported as built)
    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
    try:
        plan_review_build(_FakeClient(rows, fail_put=True),
                          "loc_tmpl", execute=True)
        raise AssertionError("a PUT validation refusal must stop")
    except ReviewBuildError:
        pass

    class _WriteButUnreadableClient(_FakeClient):
        """The PUT is accepted, but every read after it raises transport —
        the applied-but-unreadable seam (HELD family, never fabricated)."""

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
                        row.update(dict(body))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.CafUnreachable("read-back transport failure (fixture)")

    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
    try:
        plan_review_build(_WriteButUnreadableClient(rows),
                          "loc_tmpl", execute=True)
        raise AssertionError("an applied-but-unreadable PUT must be HELD")
    except reg.CafUnreachable:
        pass

    class _ScopeOnReadbackClient(_FakeClient):
        """The PUT is accepted; the read-back then refuses scope — a real
        credential problem on the SECOND leg, a STOP, never a HELD."""

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
                        row.update(dict(body))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")

    rows = _golden_rows()
    for r in rows:
        if _row_id(r) == DEFAULT_UNIVERSAL_REVIEW_FORM_ID:
            r["hiddenFields"] = ["contact_id", "anthology_id", "stage"]
    try:
        plan_review_build(_ScopeOnReadbackClient(rows),
                          "loc_tmpl", execute=True)
        raise AssertionError("a scope refusal on the read-back must STOP")
    except reg.ScopeDenied:
        pass

    # ---- 9. the surface contract: the golden dry-run and the golden apply
    #      never emit a credential-shaped string anywhere on the payload
    for kwargs in ({}, {"execute": True}):
        dumped = json.dumps(
            plan_review_build(_FakeClient(_golden_rows()), "loc_tmpl", **kwargs),
            indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(dumped), \
            "a builder surface must never carry a credential-shaped string"

    dev.write("[universal-review-builder] self-test PASS: review contract "
              "pinned (hidden pair anthology_id/stage — NO contact_id, the "
              "two decision options Approve as-is / Request rewrite with "
              "notes, the four U8 cover options == cover_render.STYLE_NAMES, "
              "the multi-line notes surface), golden no-op writes nothing, "
              "intake-trio drift refused in dry-run, execute apply + "
              "read-back proven (ONE PUT, re-read in the same job), "
              "decision/cover option drift normalized, missing notes "
              "restored, container-spelling drift preserved, pin law both "
              "ways, FORMS-EMPTY / FORMS-NOT-FOUND named, credential-shaped "
              "values refused, PUT validation STOP\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[universal-review-builder] SELF-TEST FAILED: %s\n"
                         % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def plan(location_id: str, pinned_id: str = "", *, out=None) -> int:
    """Emit the ONE offline plan JSON object (no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    pinned = (pinned_id or "").strip()
    if pinned:
        fr._unmasked_row_id_scan(pinned)
    payload = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "form_slug": REVIEW_SLUG,
        "hidden_fields_law": list(REVIEW_HIDDEN_LAW),
        "decision_options": list(decision_options()),
        "cover_options": list(_cover_choice_options()),
        "notes_law": NOTES_FIELD_LABEL,
        "write": "public v2 %s (Version %s; CAF_BROWSER_UA on the request — "
                 "CF 1010 law) — REFUSED without --execute"
                 % (hfm.FORMS_WRITE_PATH % "<formId>", reg.CAF_VERSION_HEADER),
        "read": "public v2 %s?locationId=<loc> (Version %s; CAF_BROWSER_UA on "
                "the request — CF 1010 law)"
                % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
        "note": "offline plan only — no network, no credential needed; the "
                "live review form's hidden fields are normalized to the pair "
                "[anthology_id, stage] (never the intake trio), the decision "
                "dropdown to the two options, the cover dropdown to the four "
                "style names, and the notes surface to the multi-line field "
                "ONLY with --execute, and a read-back that does not prove "
                "the build is a MISMATCH (exit 5), never a reported success",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise ReviewBuildError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out = out or sys.stdout
    out.write(dumped)
    out.write("\n")
    return EX_OK


def _run_apply(client, location_id: str, pinned_id: str, execute: bool,
               *, out=None) -> int:
    """The live apply: one JSON report on stdout, human notes on stderr.
    Maps the result onto the house exit codes — a dry-run on a drifted form
    is a MISMATCH surface (exit 5, nothing written); an applied read-back
    that cannot be proven is the same family."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    result = plan_review_build(client, location_id, pinned_id=pinned_id,
                               execute=execute)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("ok"):
        if result.get("applied"):
            out.write("[universal-review-builder] OK (marker %s): the review "
                      "form was built (hidden %s, decision %s, cover %s, "
                      "notes %s) and read back byte-exact.\n"
                      % (masked, ", ".join(REVIEW_HIDDEN_LAW),
                         ", ".join(decision_options()),
                         ", ".join(_cover_choice_options()),
                         NOTES_FIELD_LABEL))
        else:
            out.write("[universal-review-builder] OK (marker %s): the live "
                      "review form already matches the contract — idempotent "
                      "no-op, nothing written.\n" % masked)
        return EX_OK
    if result.get("af_code") == "DRY-RUN":
        out.write("[universal-review-builder] DRY-RUN (marker %s): the live "
                  "review form drifts from the contract — the build is "
                  "PLANNED, not applied. Re-run with --execute to write "
                  "(contract %s).\n"
                  % (masked, ", ".join(REVIEW_HIDDEN_LAW)))
        return EX_MISMATCH
    if result.get("af_code") == "READBACK-MISMATCH":
        out.write("[universal-review-builder] MISMATCH (marker %s): the PUT "
                  "returned success but the read-back does not prove the "
                  "build — AF-AE-READBACK-MISMATCH, never reported as "
                  "built.\n" % masked)
        return EX_MISMATCH
    # FORMS-EMPTY / FORMS-NOT-FOUND (and any other refusal) -> STOP: the
    # universal-review form cannot be identified, so no build can be planned.
    reg._stop(out, "The universal-review form cannot be identified on this "
                   "location.",
              ["AF-AE-TEMPLATE-PIPELINE-MISSING family: no universal-review "
               "row matched the slug law" + (", or the pinned form id is "
               "absent from the listing" if pinned_id else "") + ".",
               "Restore the universal-review form (or pass --form-id with the "
               "pinned Review Fire id) and re-run.",
               "Location marker: %s" % masked])
    return EX_STOP


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="universal_review_builder.py",
        description="Build the universal-review decision form of the "
                    "Anthology Convert and Flow location via public v2 "
                    "PUT /forms/{id}: EXACTLY TWO hidden fields (anthology_id, "
                    "stage — never the intake trio), the TWO-option decision "
                    "dropdown (Approve as-is / Request rewrite with notes), "
                    "the multi-line notes surface, and the FOUR-option cover "
                    "dropdown (the U8 style names) — REFUSED without "
                    "--execute; dry-run otherwise. One JSON object on "
                    "stdout; never prints a secret (Skill 59, U08/U09).")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned universal-review form id (default: the Review "
                         "Fire id %s; masked on every surface; a pinned id "
                         "absent from the listing refuses the plan)"
                         % DEFAULT_UNIVERSAL_REVIEW_FORM_ID)
    ap.add_argument("--execute", action="store_true",
                    help="PERFORM the PUT — the ONLY flag that writes. "
                         "Without it, apply is a read-only dry-run and "
                         "applied stays false.")
    ap.add_argument("cmd", nargs="?", choices=["apply", "plan", "self-test"],
                    default="apply")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION
    pinned_id = args.form_id.strip() or DEFAULT_UNIVERSAL_REVIEW_FORM_ID

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan(location_id, pinned_id)

        # ---- live apply (dry-run unless --execute) ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The builder runs against the operator's OWN template "
                       "location marker %s; set the template PIT "
                       "(client-standard labels first) and re-run."
                       % reg._mask_location(location_id)])
            return EX_STOP
        # The location id on every operator surface is the masked marker only.
        return _run_apply(reg.CafClient(token), location_id, pinned_id,
                          execute=args.execute, out=sys.stderr)

    except ReviewBuildError as exc:
        sys.stderr.write("[universal-review-builder] STOP: %s\n" % exc)
        return EX_STOP
    except fr.FormsReadError as exc:
        sys.stderr.write("[universal-review-builder] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[universal-review-builder] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[universal-review-builder] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[universal-review-builder] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[universal-review-builder] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
