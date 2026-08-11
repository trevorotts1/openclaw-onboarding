#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/title_select_builder.py
# (U08/U09 tooling)
# TITLE-SELECT FORM BUILDER — the gated, verified builder of the S3
# title-and-subtitle selection form (slug title-select) on a Convert and
# Flow location: TWO hidden fields (anthology_id, stage) plus TWO visible
# multi-line REQUIRED fields (title, subtitle) — the participant token-page
# pick the TITLE LOCK stamps from.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# U08/U09 package (pure namespace container per the u02/u03/u04/u05/u06/u07
# package-init doctrine: imported BY NAME, side-effect-free at import). It is
# NOT a manifest row: it ships as the shared build surface the U08/U09 family
# imports, so the title-select shape (the hidden pair, the visible pair, the
# multi-line law, the required law) can NEVER drift between this builder and
# its golden/attack siblings — the delta_reporter.py single-implementation
# doctrine (a contract read once, in one module).
#
# WHAT THIS OWNS
#   1. THE TITLE-SELECT FORM LAW. The S3 title-selection form (slug
#      title-select; the snapshot contract's contract_bound_per_anthology
#      row with stage "s3" and role "title-subtitle-selection") is the form
#      the participant picks title and subtitle in on the participant token
#      page; the pick is recorded by anthology_state.py record-approval at
#      the s3_selection gate and stamped into the ONE-WAY TITLE LOCK
#      (title_locked / subtitle_locked; MASTERDOC floor 4: the chosen title
#      and subtitle become byte-exact invariants carried into the outline,
#      the chapter, every rewrite, and the cover prompt). The contract row
#      (config/anthology-snapshot-contract.json forms
#      .contract_bound_per_anthology, stage "s3") is the form's hidden-field
#      authority — but the TITLE-SELECT form does NOT carry the universal
#      three-key trio: the S3 gate emits nothing extra (gate_engine.py: the
#      participant supplies the title, not the engine), so the only hidden
#      fields the form needs are the router's two routing keys — anthology_id
#      and stage (the form has no contact_id because it is only ever opened
#      from an ALREADY-resolved participant token page, never from a cold
#      intake). This module therefore builds EXACTLY TWO hidden fields:
#      HIDDEN_LAW = ("anthology_id", "stage") — the S3-specific pair, in
#      the contract's own universal order, byte-exact. The visible side is
#      the pair the record path consumes: "title" and "subtitle", BOTH
#      multi-line (LARGE_TEXT — the anthology free-text law of
#      provision_fields, PRD Gap G11; a title or subtitle may run several
#      lines) and BOTH required (the TITLE LOCK stamps the chosen title as
#      a byte-exact invariant, and the lock is one-way — a blank pick is a
#      lock on nothing, never permitted).
#   2. THE WRITE LAW (--execute). Building the form's field shape rides the
#      public v2 PUT /forms/{id} surface (the same surface the U04
#      query_key_fixer and the U08/U09 hidden-field creator use; proven in
#      Skill 44's ghl_client.py, Version 2021-07-28 — the same base +
#      version header reg.CafClient already sends). The PUT is REFUSED
#      unless the operator passes --execute to THIS module's own CLI
#      (Trevor-gated, per the u07 package-init doctrine and the U04/U08
#      sibling doctrine: the dispatcher never writes); every other
#      invocation is a read-only dry-run. After the PUT the form is read
#      back in the SAME job and must prove the shape byte-exact — a PUT
#      whose read-back does not prove the build is a MISMATCH
#      (AF-AE-READBACK-MISMATCH family), never a reported success.
#   3. THE TARGET LAW. The title-select form is found on the listing BY
#      SLUG: the row whose normalized name equals the slug with dashes ->
#      spaces ("title select") — the same name-match law forms_check.py /
#      golden_forms.py pin for the three-slug family. When --form-id is
#      given (the engine's pinned fleet-wide title-select id
#      DEFAULT_TITLE_SELECT_FORM_ID, live-verified 2026-08-11 on the
#      template location's Title Fire trigger), the pin BYPASSES the slug
#      law (a pin is a stronger contract than a name) and IS the row
#      written; a pinned id absent from the listing refuses the plan.
#   4. THE READ LAW. A 2xx whose body is not valid JSON, a listing with no
#      parseable rows, or a listing with NO title-select row is a FAIL
#      (exit 5), never a fabricated pass. A bare 401/403 is HELD
#      (UpstreamBlockedError — the CF 1010 edge-block guard; a scope denial
#      is only a REAL "not authorized for this scope" signature or the
#      live-verified "does not have access to this location" signature), a
#      transport failure is HELD (exit 3), and a missing/refused credential
#      STOPS (exit 2).
#   5. NEVER-A-TOKEN SURFACE. The PIT is resolved through
#      anthology_registry.resolve_pit (the house labels
#      CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
#      GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first then the three
#      canonical client env stores; SET / NOT SET only — a token value is
#      NEVER printed). Before any JSON is emitted, every payload is scanned
#      against the house credential shape (pit-<value>) and a hit REFUSES
#      the whole surface rather than print it — the delta_reporter.py
#      never-a-real-token doctrine.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever reaches
# Convert and Flow (GK-09; the same browser UA the Podcast gate proved live).
# A bare 401/403 is never proof of a scope problem — an edge block carries
# the same status (the exact Wave 5 false-positive guard).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, echoed, or reflected.
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable response, an empty listing, an absent title-select row, a
# pinned id the listing lacks, a malformed live row with no writable field
# surface, a credential-shaped string in any payload, or a PUT body that
# cannot be constructed from a live read-back is a REFUSAL / FAIL — never a
# silent pass, never a fabricated success, and never a shape guessed from
# memory.
#
# RETURN CONTRACT (the machine surface this module owns):
#   plan_form_build(client, location_id, *, pinned_id="", execute=False,
#                   form_rows=None) -> dict — {"contract", "schema_version",
#                   "ok", "applied", "execute", "form_id", "form_id_masked",
#                   "fields_current", "fields_law", "hidden_current",
#                   "hidden_law", "target_matched_by", "af_code", "note"};
#                   ok False carries NO form id (never an id guessed from
#                   memory) and a named af_code — FORMS-EMPTY / FORMS-NOT-
#                   FOUND / DRY-RUN / READBACK-MISMATCH. Raises FormsBuildError
#                   (STOP family) / reg.CafUnreachable, reg.ScopeDenied,
#                   reg.UpstreamBlockedError (HELD family) — a caller maps
#                   them onto the house exit codes.
#   plan(location_id, pinned_id, *, out=sys.stdout) -> int — ONE JSON
#       object, offline, no network, no credential.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers apply / plan / self-test; `apply` is a DRY-RUN
#   unless --execute is passed.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — dry-run plan pass, idempotent no-op (the shape is already
#      live), or applied + read-back verified
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      an unreadable listing shape / an unprovable target (the title-select
#      form cannot be identified) / a malformed live row with no writable
#      field surface / a PUT validation refusal
#   3  Convert and Flow API unreachable / edge-blocked (HELD, retryable —
#      the scope is UNDETERMINED here, never proven absent), including an
#      applied-but-unreadable PUT
#   4  self-test FAILED (a tamper NEVER masquerades as exit 1)
#   5  MISMATCH — the read-back after the PUT does not prove the build
#      (AF-AE-READBACK-MISMATCH family), or the shape is missing and no
#      build was performed (dry-run refusal surface)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   title_select_builder.py apply [--location-id ID] [--form-id ID]
#                                [--execute]
#   title_select_builder.py plan  [--location-id ID] [--form-id ID]
#   title_select_builder.py self-test
#
# --execute is the ONLY flag that performs the PUT. Its absence makes the
# apply run a dry-run: live reads only, nothing written, applied:false in
# the report. apply (dry-run included) needs the PIT — a truthful plan
# requires the live read; an unread state is never fabricated.
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, resolve_location, _stop,
# _mask_location, _auth_denial_kind and its exception classes) and
# u04_modules.form_reader (read_forms — the ONE forms-listing read, the
# slug/pin laws, the mask surface). DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value.
# =============================================================================
"""title_select_builder.py — gated, verified builder of the S3 title-select
form on the Anthology Convert and Flow location: the two routing hidden
fields (anthology_id, stage) and the two visible multi-line REQUIRED fields
(title, subtitle) via public v2 PUT /forms/{id} — REFUSED without --execute;
every other invocation is a read-only dry-run (Skill 59, U08/U09 tooling)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to hidden_field_
# module.py / query_key_fixer.py): the registry owns the Cloudflare browser-
# UA wiring, the LeadConnector client, the credential resolution, and the
# exit-code contract; the reader owns the ONE forms-listing read and its
# slug/pin laws.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "u04_modules"))
import form_reader as fr  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object for
# a title-select build (the self-test asserts the golden plan carries the
# exact string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-title-select-build"
CONFIG_SCHEMA_VERSION = 1

# The title-select form slug — the S3 gate form of the three-slug family
# forms_check.py / golden_forms.py pin (universal-intake / universal-review /
# title-select), and the snapshot contract's contract_bound_per_anthology
# row with stage "s3" and role "title-subtitle-selection".
FORM_SLUG = "title-select"

# The name-match law: the slug with dashes -> spaces ("title select") — the
# same law golden_forms.py / form_reader.py pin for the family. A listing row
# whose normalized name equals this string IS the title-select form.
SLUG_AS_NAME = FORM_SLUG.replace("-", " ")

# The S3 HIDDEN-FIELD LAW, byte-exact — the TWO routing keys the title-select
# form carries, in the snapshot contract's own universal order: anthology_id
# (the G3 query-key law build_intake_link mints with; cross-pinned against
# anthology_book.INTAKE_QUERY_KEY by the self-test so this module can never
# drift from the link builder it keeps honest) then stage (the token the S0
# pipeline reads to classify every submission). The title-select form does
# NOT carry contact_id — it is only ever opened from an ALREADY-resolved
# participant token page, so the routing pair is exactly two, never the
# intake trio (the gate_engine.py s3_selection surface: the participant
# supplies the title and subtitle, the engine emits nothing extra).
HIDDEN_LAW = ("anthology_id", "stage")

# The VISIBLE-FIELD LAW, byte-exact — the pair the s3_selection record path
# consumes and the TITLE LOCK stamps (anthology_state.py record-approval
# reads --title and --subtitle at the s3_selection gate and stamps
# title_locked / subtitle_locked, ONE-WAY per MASTERDOC floor 4). Both are
# MULTI-LINE (LARGE_TEXT — the anthology free-text law of provision_fields,
# PRD Gap G11: every anthology free-text field ships as LARGE_TEXT, and the
# multi-line law requires it) and both REQUIRED (a blank pick is a lock on
# nothing — the one-way TITLE LOCK never permits it).
VISIBLE_FIELDS = (
    {"name": "title", "data_type": "LARGE_TEXT", "required": True},
    {"name": "subtitle", "data_type": "LARGE_TEXT", "required": True},
)
TITLE_FIELD_NAME = "title"
SUBTITLE_FIELD_NAME = "subtitle"

# The complete shape law: the two hidden routing keys, then the two visible
# required multi-line fields, in the exact order the build will leave them.
FIELDS_LAW = (
    {"name": HIDDEN_LAW[0], "hidden": True, "required": False},
    {"name": HIDDEN_LAW[1], "hidden": True, "required": False},
    {"name": TITLE_FIELD_NAME, "hidden": False, "required": True,
     "data_type": "LARGE_TEXT"},
    {"name": SUBTITLE_FIELD_NAME, "hidden": False, "required": True,
     "data_type": "LARGE_TEXT"},
)

# The public v2 forms surfaces, proven in Skill 44
# (44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/
# ghl_client.py: GET /forms/ with params locationId/limit/skip and the PUT
# form update, Version 2021-07-28 — the same base + version header
# reg.CafClient already sends). The LIST path is the reader's constant (ONE
# read surface, owned by form_reader); this module owns the WRITE path.
FORMS_WRITE_PATH = "/forms/%s"

# The hidden-field container keys a live row may carry (the canonical
# "hiddenFields" spelling, the snake "hidden_fields", and the bracket
# "hiddenFields[]" alternate). The write normalizes whichever spelling is
# live onto the contract spelling — the container key itself is never
# duplicated.
HIDDEN_CONTAINER_KEYS = ("hiddenFields", "hidden_fields", "hiddenFields[]")

# The visible-field container keys a live row may carry (the canonical
# "fields" spelling and the snake "fields_list" alternate; a row that
# carries "fields" as a list of field objects). The write normalizes
# whichever spelling is live onto the contract spelling — the container key
# itself is never duplicated.
FIELDS_CONTAINER_KEYS = ("fields", "fields_list")

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests. Same
# value form_reader.DEFAULT_TEMPLATE_LOCATION carries — imported, never
# re-typed, so the two surfaces cannot drift.
DEFAULT_TEMPLATE_LOCATION = fr.DEFAULT_TEMPLATE_LOCATION

# The engine's pinned fleet-wide title-select form id — the S3 gate form of
# the three-slug family, live-verified 2026-08-11 on the template location's
# Title Fire trigger (the trigger surface the U02 forms read proved:
# title-select -> UgiiSoZsA4vyqOVfO5fi, the Title Fire trigger AND the S3
# title-and-subtitle link in "Release: Titles"). A location identifier, not
# a secret — but masked on every surface.
DEFAULT_TITLE_SELECT_FORM_ID = "UgiiSoZsA4vyqOVfO5fi"

# The engine's pinned fleet-wide universal-intake form id — the ONE intake
# front-door id baked into scripts/anthology_book.py (the first row of the
# golden three-slug family the self-test pins). Imported from the reader,
# the ONE owner of the pin, never re-typed.
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123") — the same guard the reader and the sibling
# builders ship. Every emitted surface is scanned against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FormsBuildError(Exception):
    """A fail-closed build refusal (STOP family): an unreadable listing
    shape, an unprovable target, a malformed live row with no writable field
    surface, a credential-shaped string in a payload, or a PUT body that
    cannot be constructed from a live read-back. An expectation that cannot
    name its own sources must not run."""


def mask_id(fid: str) -> str:
    """Non-reversible marker for a form id (last 4 chars) — the house surface
    shape for every operator-facing mention of a form id. Same surface the
    reader ships."""
    return fr.mask_id(fid)


def _row_id(row) -> str:
    """The form id of a live row — the reader's OWN resolver, so this module
    can never disagree with the reader about which id a row carries."""
    return fr._row_id(row)


def _row_hidden(row) -> tuple:
    """The hidden-field keys of a live form row under any of its container
    keys ("hiddenFields" / "hidden_fields" / "hiddenFields[]"), flattened,
    de-duplicated, in first-seen order. Returns () when the row carries no
    hidden-field container at all (a container-less row is a fixable target —
    the routing pair REQUIRES the keys — but the pre-write proof names what
    is absent). A non-list container value is a malformed shape ->
    FormsBuildError (never a guessed set)."""
    if not isinstance(row, dict):
        return ()
    for key in HIDDEN_CONTAINER_KEYS:
        if key not in row:
            continue
        value = row[key]
        if not isinstance(value, list):
            raise FormsBuildError(
                "the hidden-field container %r of the title-select row is "
                "%s, not an array — the row shape is not readable"
                % (key, type(value).__name__))
        seen = []
        for item in value:
            name = item if isinstance(item, str) else None
            if isinstance(item, dict):
                # a {key, value} row (the live hosted-form hidden-field
                # container spelling the attack fixture emulates)
                name = item.get("key")
                if not isinstance(name, str) or not name.strip():
                    continue
            if isinstance(name, str) and name.strip() and name not in seen:
                seen.append(name.strip())
        return tuple(seen)
    return ()


def _row_hidden_container_key(row) -> str:
    """The container key the live row actually carries ("" when none) — the
    write preserves the live spelling instead of imposing its own."""
    if not isinstance(row, dict):
        return ""
    for key in HIDDEN_CONTAINER_KEYS:
        if key in row:
            return key
    return ""


def _row_fields(row) -> tuple:
    """The visible-field objects of a live form row under any of its
    container keys ("fields" / "fields_list"), in first-seen order. Returns
    () when the row carries no visible-field container at all. A non-list
    container value is a malformed shape -> FormsBuildError (never a guessed
    set)."""
    if not isinstance(row, dict):
        return ()
    for key in FIELDS_CONTAINER_KEYS:
        if key not in row:
            continue
        value = row[key]
        if not isinstance(value, list):
            raise FormsBuildError(
                "the fields container %r of the title-select row is %s, not "
                "an array — the row shape is not readable"
                % (key, type(value).__name__))
        return tuple(f for f in value if isinstance(f, dict))
    return ()


def _row_fields_container_key(row) -> str:
    """The fields container key the live row actually carries ("" when
    none) — the write preserves the live spelling instead of imposing its
    own."""
    if not isinstance(row, dict):
        return ""
    for key in FIELDS_CONTAINER_KEYS:
        if key in row:
            return key
    return ""


def _field_name(field) -> str:
    """The name of a visible-field object under any of its name keys — "name"
    (the canonical spelling), "label", or "fieldName". Returns "" when the
    field carries none."""
    if not isinstance(field, dict):
        return ""
    for key in ("name", "label", "fieldName"):
        value = field.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _list_rows(client, location_id: str) -> list:
    """The ONE live forms read, owned by the reader: the public v2
    GET /forms/?locationId=<loc> (CAF_BROWSER_UA on the request — the CF 1010
    law) flattened over the two proven container shapes. A malformed shape is
    a FormsReadError -> STOP; a transport/scope failure propagates -> HELD."""
    payload = client._request(
        "GET", fr.FORMS_LIST_PATH,
        query={"locationId": location_id, "limit": 200})
    return fr._flatten_rows(payload)


def _find_target(row, pinned_id: str) -> bool:
    """The TARGET LAW, byte-exact, fail-closed: True ONLY when this row is
    the title-select form, proven by (a) the slug law — the row's normalized
    name equals the slug with dashes -> spaces ("title select") — or (b) the
    pin law, when a pinned id is given: the pinned id BYPASSES the slug law
    (a pin is a stronger contract than a name). A row that matches NEITHER
    law is False — a write to a form we cannot prove is the title-select form
    is a write to the wrong record, never performed. The id is resolved by
    the CALLER, so a slug-matched row that carries no id is still recognized
    (and refused as an unreadable shape), never silently skipped."""
    pinned = (pinned_id or "").strip()
    if pinned:
        return _row_id(row) == pinned
    if isinstance(row, dict):
        if fr._normalize_name(str(row.get("name") or "")) == SLUG_AS_NAME:
            return True
    return False


def _normalized_hidden_law(hidden_current) -> tuple:
    """The hidden keys as the build will leave them: the live row's keys
    normalized to the contract spelling, de-duplicated, with the missing law
    keys appended in law order and every non-law key preserved in first-seen
    order. Fail-closed: a current set that is not a flat string list is a
    malformed shape -> FormsBuildError (never a guessed set)."""
    if not isinstance(hidden_current, (tuple, list)):
        raise FormsBuildError(
            "the live hidden-field set is %s, not a flat list — the row "
            "shape is not readable" % type(hidden_current).__name__)
    out = []
    for key in hidden_current:
        if not isinstance(key, str) or not key.strip():
            continue
        if key not in out:
            out.append(key)
    for key in HIDDEN_LAW:
        if key not in out:
            out.append(key)
    return tuple(out)


def _normalized_fields_law(fields_current) -> tuple:
    """The visible fields as the build will leave them: the live row's field
    objects, keyed by name, with the two law fields (title, subtitle)
    normalized to {name, data_type LARGE_TEXT, required True} — a drift in
    either field (a blank title pick is a lock on nothing) is REPAIRED, never
    tolerated — and every non-law field preserved in first-seen order, so a
    live row that already carries extra fields is not destroyed by the build.
    A non-list current set is a malformed shape -> FormsBuildError (never a
    guessed set)."""
    if not isinstance(fields_current, (tuple, list)):
        raise FormsBuildError(
            "the live fields set is %s, not a list — the row shape is not "
            "readable" % type(fields_current).__name__)
    out = []
    seen = set()
    law_by_name = {f["name"]: f for f in VISIBLE_FIELDS}
    for field in fields_current:
        if not isinstance(field, dict):
            continue
        name = _field_name(field)
        if not name or name in seen:
            continue
        seen.add(name)
        if name in law_by_name:
            # the law wins: multi-line LARGE_TEXT and required, byte-exact
            out.append({"name": name,
                        "data_type": law_by_name[name]["data_type"],
                        "required": True})
        else:
            out.append(dict(field))
    for name in (TITLE_FIELD_NAME, SUBTITLE_FIELD_NAME):
        if name not in seen:
            out.append({"name": name, "data_type": "LARGE_TEXT",
                        "required": True})
    return tuple(out)


def _build_fix_body(row, fid: str) -> dict:
    """The PUT body, built ONLY from the live read-back row: every key and
    value echoed byte-for-byte with the hidden-field container normalized to
    the S3 routing pair and the visible-field container normalized to the
    two-law-field shape. A body constructed from memory is NEVER sent.
    Fail-closed: a row that is not a dict, a row whose id cannot be proven,
    or a field surface the law cannot be written onto is a FormsBuildError —
    never a guessed body."""
    if not isinstance(row, dict):
        raise FormsBuildError("the target row is not an object — a PUT body "
                              "cannot be constructed from it")
    if not fid:
        raise FormsBuildError("the target row carries no form id — a PUT to "
                              "an id-less row cannot be constructed")
    body = {}
    for key, value in row.items():
        if key in HIDDEN_CONTAINER_KEYS:
            body[key] = list(_normalized_hidden_law(_row_hidden(row)))
        elif key in FIELDS_CONTAINER_KEYS:
            body[key] = list(_normalized_fields_law(_row_fields(row)))
        else:
            body[key] = value
    if not any(key in body for key in HIDDEN_CONTAINER_KEYS):
        body[HIDDEN_CONTAINER_KEYS[0]] = list(HIDDEN_LAW)
    if not any(key in body for key in FIELDS_CONTAINER_KEYS):
        body[FIELDS_CONTAINER_KEYS[0]] = list(_normalized_fields_law(()))
    return body


def plan_form_build(client, location_id: str, *, pinned_id: str = "",
                    execute: bool = False, form_rows=None) -> dict:
    """Plan (and, ONLY with --execute, perform) the title-select form build.
    Fail-closed, never a token.

    `client` is a reg.CafClient (its own _request rides CAF_BROWSER_UA).
    `form_rows` is an explicit row list (self-tests); when None the live
    listing is read (the reader's ONE read). `pinned_id` is the engine's
    pinned fleet-wide title-select form id (or a box override) — when given
    it must be the row written and it BYPASSES the slug law.

    Returns the documented surface {contract, schema_version, ok, applied,
    execute, form_id, form_id_masked, fields_current, fields_law,
    hidden_current, hidden_law, target_matched_by, note} — fail-closed:
      - ok True ONLY when the live form already carries the two routing
        hidden keys AND the two visible required multi-line fields (an
        idempotent no-op: applied false, nothing written) OR the shape was
        built with --execute and read back byte-exact,
      - applied True ONLY when a PUT actually happened (--execute),
      - hidden_current is the live row's hidden-field keys (read-only; the
        full values are never emitted — a value could echo a credential),
      - fields_current is the live row's visible-field names and their
        multi-line/required flags (read-only),
      - hidden_law / fields_law are the shape the write will leave,
      - ok False carries NO form id (never an id guessed from memory) and a
        named af_code — FORMS-NOT-FOUND when no title-select row matched (or
        the pinned id was absent), FORMS-EMPTY when the listing held zero
        rows, READBACK-MISMATCH when a PUT happened but the read-back does
        not prove the build,
      - the field surface is NEVER a token: a row whose hidden-field or
        visible-field container resolves to a credential-shaped string
        REFUSES the whole plan rather than print it.
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (fr.FormsReadError / FormsBuildError, STOP family)
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
            # A slug-matched row carrying NO form id is an unreadable shape —
            # a write to an id-less row cannot be constructed, so it STOPS
            # (never a silent skip to FORMS-NOT-FOUND).
            if not _row_id(row):
                raise FormsBuildError(
                    "the title-select row matched the slug law but carries "
                    "no form id — the listing shape is not readable")
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
            "fields_current": [],
            "fields_law": [dict(f) for f in _normalized_fields_law(())],
            "hidden_current": [],
            "hidden_law": list(HIDDEN_LAW),
            "target_matched_by": "",
            "af_code": ("FORMS-EMPTY" if count == 0 else "FORMS-NOT-FOUND"),
            "note": ("the listing is empty" if count == 0 else
                     "no title-select row on the listing — the slug law "
                     "matched nothing" + (" and the pinned id is absent"
                                          if pinned else "")) +
                    " (fail-closed, never an id guessed from memory)",
        }

    fid = _row_id(target)
    if not fid:
        raise FormsBuildError("the title-select row carries no form id — "
                              "the listing shape is not readable")
    hidden_current = _row_hidden(target)
    fields_current = _row_fields(target)
    if hidden_current:
        dumped_current = json.dumps(list(hidden_current))
        if _CREDENTIAL_SHAPE.search(dumped_current):
            raise FormsBuildError(
                "the hidden-field surface resolved to a credential-shaped "
                "string — REFUSED without printing it")
    body = _build_fix_body(target, fid)
    dumped_body = json.dumps(body, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped_body):
        raise FormsBuildError(
            "the PUT body carries a credential-shaped string — REFUSED "
            "without printing it")

    # ---- the shape law, byte-exact: BOTH routing hidden keys present AND
    #      BOTH visible law fields present, required and multi-line
    hidden_present = all(key in hidden_current for key in HIDDEN_LAW)
    fields_law = _normalized_fields_law(fields_current)
    field_names = [f["name"] for f in fields_current]
    visible_present = (
        TITLE_FIELD_NAME in field_names and SUBTITLE_FIELD_NAME in field_names
        and all(f.get("required") is True and f.get("data_type") == "LARGE_TEXT"
                for f in fields_current
                if f.get("name") in (TITLE_FIELD_NAME, SUBTITLE_FIELD_NAME)))
    if hidden_present and visible_present:
        # Idempotent no-op: the form already carries the exact shape —
        # nothing is written, ever, even with --execute (the query_key_
        # fixer.py old==new doctrine).
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": True,
            "applied": False,
            "execute": execute,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "fields_current": [dict(f) for f in fields_current],
            "fields_law": [dict(f) for f in fields_law],
            "hidden_current": list(hidden_current),
            "hidden_law": list(HIDDEN_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "NO-OP",
            "note": "the live title-select form already carries the S3 "
                    "shape — hidden %s and visible %s (required, multi-line)"
                    " — idempotent no-op, nothing written"
                    % (", ".join(HIDDEN_LAW),
                       ", ".join(field_names)),
        }

    if not execute:
        # Dry-run: the plan is the report. The missing shape is surfaced;
        # applied stays false; nothing was written.
        missing_hidden = [k for k in HIDDEN_LAW if k not in hidden_current]
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": False,
            "execute": False,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "fields_current": [dict(f) for f in fields_current],
            "fields_law": [dict(f) for f in fields_law],
            "hidden_current": list(hidden_current),
            "hidden_law": list(HIDDEN_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "DRY-RUN",
            "note": ("the live title-select form carries %s hidden keys and "
                     "%s — the build is PLANNED, not applied; the missing "
                     "keys (%s) and the missing law fields (%s) would be "
                     "added/normalized; re-run with --execute to write"
                     % (", ".join(hidden_current) if hidden_current
                        else "<no hidden-field surface>",
                        ", ".join(field_names) if field_names
                        else "<no visible-field surface>",
                        ", ".join(missing_hidden) or "<none>",
                        ", ".join(n for n in (TITLE_FIELD_NAME,
                                              SUBTITLE_FIELD_NAME)
                                  if n not in field_names) or "<none>")),
        }

    # ---- --execute: the ONE write ------------------------------------------
    # The PUT body is the live-row echo with the hidden-field container
    # normalized to the S3 routing pair and the visible-field container
    # normalized to the two-law-field shape (never fabricated). The response
    # body of the PUT is never trusted: only the read-back proves the build.
    try:
        client._request("PUT", FORMS_WRITE_PATH % _url_quote(fid), body=body)
    except reg.CafValidation as exc:
        # 400/409/422 from Convert and Flow: a validation refusal is a STOP,
        # never a silent skip (the query_key_fixer.py doctrine).
        raise FormsBuildError("Convert and Flow refused the form PUT (HTTP "
                              "validation): %s" % exc)

    # ---- read-back: prove the build in the SAME job ------------------------
    # A PUT that returned success but cannot be read back is HELD (exit 3,
    # via reg.CafUnreachable) — the live state is UNDETERMINED, never
    # reported as built. The reader is the ONE read surface: its pin gate
    # proves the form id survived the PUT; the row extraction that follows
    # re-reads the SAME listing and carries the field shapes to judge. A
    # scope refusal on the read-back is a real credential STOP and propagates
    # untouched — never demoted to a HELD.
    try:
        read = fr.read_forms(client, location_id, pinned_id=fid)
    except reg.ScopeDenied:
        raise
    except (fr.FormsReadError, reg.CafUnreachable, reg.UpstreamBlockedError) as exc:
        raise reg.CafUnreachable(
            "the PUT returned success but the form cannot be read back "
            "(%s) — the live state is UNDETERMINED, never reported as "
            "built (form id marker %s)" % (type(exc).__name__, mask_id(fid)))
    if not read.get("ok"):
        raise reg.CafUnreachable(
            "the PUT returned success but the read-back cannot find the "
            "form (form id marker %s) — the live state is UNDETERMINED, "
            "never reported as built" % mask_id(fid))
    try:
        rb_row = _find_row_by_id(_list_rows(client, location_id), fid)
    except (fr.FormsReadError, reg.CafUnreachable, reg.UpstreamBlockedError) as exc:
        raise reg.CafUnreachable(
            "the PUT returned success but the form cannot be read back "
            "(%s) — the live state is UNDETERMINED, never reported as "
            "built (form id marker %s)" % (type(exc).__name__, mask_id(fid)))
    if rb_row is None:
        raise reg.CafUnreachable(
            "the PUT returned success but the form row is absent from the "
            "read-back listing (form id marker %s) — the live state is "
            "UNDETERMINED, never reported as built" % mask_id(fid))
    rb_hidden = _row_hidden(rb_row)
    rb_fields = _row_fields(rb_row)
    rb_field_names = [f["name"] for f in rb_fields]
    rb_ok = (
        all(key in rb_hidden for key in HIDDEN_LAW)
        and TITLE_FIELD_NAME in rb_field_names
        and SUBTITLE_FIELD_NAME in rb_field_names
        and all(f.get("required") is True and f.get("data_type") == "LARGE_TEXT"
                for f in rb_fields
                if f.get("name") in (TITLE_FIELD_NAME, SUBTITLE_FIELD_NAME)))
    if not rb_ok:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": True,
            "execute": True,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "fields_current": [dict(f) for f in rb_fields],
            "fields_law": [dict(f) for f in fields_law],
            "hidden_current": list(rb_hidden),
            "hidden_law": list(HIDDEN_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "READBACK-MISMATCH",
            "note": "the PUT returned success but the read-back does not "
                    "prove the S3 shape — hidden %s, visible %s "
                    "(AF-AE-READBACK-MISMATCH family), never reported as "
                    "built"
                    % (", ".join(rb_hidden) if rb_hidden else "<absent>",
                       ", ".join(rb_field_names) if rb_field_names
                       else "<absent>"),
        }

    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "applied": True,
        "execute": True,
        "form_id": fid,
        "form_id_masked": mask_id(fid),
        "fields_current": [dict(f) for f in rb_fields],
        "fields_law": [dict(f) for f in fields_law],
        "hidden_current": list(rb_hidden),
        "hidden_law": list(HIDDEN_LAW),
        "target_matched_by": target_matched_by,
        "af_code": "BUILT",
        "note": "the title-select form was built and read back byte-exact — "
                "hidden %s, visible %s (multi-line, required) — the S3 "
                "participant pick now lands title and subtitle for the "
                "one-way TITLE LOCK"
                % (", ".join(HIDDEN_LAW),
                   ", ".join(rb_field_names)),
    }


def _url_quote(fid: str) -> str:
    """URL-encode a form id for the write path (the registry quotes location
    ids the same way; a form id carries no reserved chars, but the path is
    never built with an unquoted interpolant)."""
    import urllib.parse
    return urllib.parse.quote(fid or "", safe="")


def _find_row_by_id(rows, fid: str):
    """The row whose id equals fid ("" when absent) — the read-back lookup
    the builder uses to re-read the field shapes AFTER a build."""
    for row in rows:
        if _row_id(row) == fid:
            return row
    return None


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the builder against
# the REAL committed constants (the S3 slug law, the pinned id, the two-key
# routing law), then runs every attack fixture: golden drift, the dry-run
# refusal, the --execute apply + read-back, every not-found path named, the
# pin law both ways, the multi-line/required law both ways, the never-a-token
# guard, and the scope-vs-edge 403 discrimination the CLI depends on.
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
        if method == "PUT" and path.startswith(FORMS_WRITE_PATH % ""):
            if self._fail_put:
                raise reg.CafValidation("Convert and Flow rejected the "
                                        "request (HTTP 422)")
            fid = path[len(FORMS_WRITE_PATH % ""):]
            for row in self._rows:
                if fr._row_id(row) == fid:
                    for key in HIDDEN_CONTAINER_KEYS:
                        if key in row:
                            row[key] = list(HIDDEN_LAW)
                            break
                    else:
                        row["hiddenFields"] = list(HIDDEN_LAW)
                    for key in FIELDS_CONTAINER_KEYS:
                        if key in row:
                            row[key] = list(_normalized_fields_law(()))
                            break
                    else:
                        row["fields"] = list(_normalized_fields_law(()))
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.CafUnreachable("unexpected request (fixture)")


def _golden_rows():
    """The golden listing rows: the title-select form carrying the pinned
    engine id, the full three-key hidden trio on the OTHER two family forms
    but only ONE of the two routing keys on title-select (the missing stage
    key is the defect this module exists to fix), and NO visible-field
    surface (the title/subtitle pair is the defect) — plus the family's
    other two forms, the same three-slug family forms_check.py /
    golden_forms.py / form_reader.py pin. The universal-intake and
    universal-review rows carry their OWN contract trio untouched."""
    return [
        {"id": DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "riNlAkYbcW3g92VRLqq0", "name": "Universal Review",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": DEFAULT_TITLE_SELECT_FORM_ID, "name": "Title Select",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["anthology_id"]},
    ]


def _self_test_body(dev) -> None:
    # ---- 0. the S3 shape law is pinned, and the reader's slug law is the
    #      same law this module builds under; the G3 lookalike can never
    #      satisfy the routing pair
    assert HIDDEN_LAW == ("anthology_id", "stage"), \
        "the S3 hidden-field law drifted from the routing pair the gate " \
        "link needs"
    assert "anthology_active_id" not in HIDDEN_LAW, \
        "the G3 lookalike must never enter the title-select hidden law"
    assert "contact_id" not in HIDDEN_LAW, \
        "the title-select form must NOT carry the intake contact_id — it is " \
        "only ever opened from a resolved participant token page"
    assert fr.SLUG_AS_NAME == "universal intake", \
        "the reader's slug law drifted (this module builds under it)"
    assert SLUG_AS_NAME == "title select", \
        "the title-select slug law drifted"
    assert TITLE_FIELD_NAME == "title" and SUBTITLE_FIELD_NAME == "subtitle", \
        "the visible-field names drifted from the s3_selection record path"
    for f in VISIBLE_FIELDS:
        assert f["data_type"] == "LARGE_TEXT" and f["required"] is True, \
            "every visible title-select field must be multi-line and " \
            "required (the one-way TITLE LOCK never stamps a blank pick)"

    # ---- 1. golden DRIFT: stage hidden key and both visible fields are
    #      missing -> dry-run refuses (exit 5 surface), the plan names the
    #      drift, nothing is written
    client = _FakeClient(_golden_rows())
    res = plan_form_build(client, "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False, \
        "a drifted form must refuse in dry-run"
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["form_id"] == DEFAULT_TITLE_SELECT_FORM_ID
    assert res["hidden_current"] == ["anthology_id"]
    assert res["hidden_law"] == list(HIDDEN_LAW)
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], \
        "a dry-run must perform ONLY the listing read"

    # ---- 2. --execute: the PUT happens, the read-back proves the build
    client = _FakeClient(_golden_rows())
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the build must apply and pass under --execute"
    assert res["af_code"] == "BUILT"
    assert res["hidden_current"] == list(HIDDEN_LAW)
    assert res["form_id"] == DEFAULT_TITLE_SELECT_FORM_ID
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == FORMS_WRITE_PATH % DEFAULT_TITLE_SELECT_FORM_ID
    # the PUT body echoes the live row byte-for-byte with the routing pair
    # added and the visible pair normalized — every other field is intact
    assert puts[0]["body"].get("hiddenFields") == list(HIDDEN_LAW), \
        "the PUT body must carry the two routing hidden fields"
    assert puts[0]["body"].get("id") == DEFAULT_TITLE_SELECT_FORM_ID, \
        "the PUT body must echo the live row's id"
    assert puts[0]["body"].get("name") == "Title Select", \
        "the PUT body must echo the live row's name"
    assert puts[0]["body"].get("queryKey") == "anthology_id", \
        "the PUT body must echo the live row's query key"
    fields = puts[0]["body"].get("fields")
    assert isinstance(fields, list) and len(fields) == 2, \
        "the PUT body must carry exactly the two visible fields"
    by_name = {f.get("name"): f for f in fields}
    assert set(by_name) == {"title", "subtitle"}, \
        "the visible pair must be exactly title and subtitle"
    for f in fields:
        assert f.get("data_type") == "LARGE_TEXT", \
            "every visible field must be multi-line (LARGE_TEXT)"
        assert f.get("required") is True, \
            "every visible field must be required"
    # the write is proven ONLY by the read-back in the same job
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, "the apply must re-read the listing for the read-back"

    # ---- 3. idempotent no-op: the full S3 shape is already live -> ok true,
    #      applied false, NOTHING written — even with --execute
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["hiddenFields"] = list(HIDDEN_LAW)
    rows[2]["fields"] = list(_normalized_fields_law(()))
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, \
        "an already-built form must be an idempotent no-op"
    assert res["af_code"] == "NO-OP"
    assert not any(c["method"] == "PUT" for c in client.calls), \
        "a no-op must never perform a PUT"

    # ---- 3b. the container-spelling drift is normalized: the live row
    #      carries "hidden_fields" (snake) and "fields_list" — the write
    #      preserves the live spellings and adds the missing keys; the
    #      read-back proves the law
    rows = [dict(r) for r in _golden_rows()]
    rows[2] = {"id": DEFAULT_TITLE_SELECT_FORM_ID, "name": "Title Select",
               "type": "form", "queryKey": "anthology_id",
               "hidden_fields": ["anthology_id"]}
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1 and "hidden_fields" in puts[0]["body"], \
        "the PUT body must preserve the live hidden container spelling"
    assert puts[0]["body"]["hidden_fields"] == list(HIDDEN_LAW)

    # ---- 3c. a visible-field drift is repaired, never tolerated: the live
    #      "title" field is single-line and optional — the build normalizes
    #      it to multi-line REQUIRED under --execute
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["fields"] = [{"name": "title", "data_type": "TEXT",
                          "required": False}]
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", \
        "a single-line or optional visible field must refuse in dry-run"
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the build must normalize the visible pair under --execute"
    puts = [c for c in client.calls if c["method"] == "PUT"]
    by_name = {f.get("name"): f for f in puts[0]["body"].get("fields", [])}
    assert by_name["title"]["data_type"] == "LARGE_TEXT", \
        "the law data type must win over a drifted live value"
    assert by_name["title"]["required"] is True, \
        "the law required flag must win over a drifted live value"
    assert by_name["subtitle"]["required"] is True, \
        "the subtitle field must be required after the build"

    # ---- 4. the pin law: the pinned id BYPASSES the slug law and IS the row
    #      written; a pinned id absent from the listing is FORMS-NOT-FOUND
    client = _FakeClient(_golden_rows())
    res = plan_form_build(client, "loc_tmpl",
                          pinned_id=DEFAULT_TITLE_SELECT_FORM_ID,
                          execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["target_matched_by"] == "pin"
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["id"] = "DriftedDriftedId00"
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl",
                          pinned_id=DEFAULT_TITLE_SELECT_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", \
        "an absent pinned id must refuse, got %r" % res
    assert res["form_id"] == "", "a failed plan must never carry a form id"

    # ---- 5. not-found paths, each NAMED: an empty listing is FORMS-EMPTY; a
    #      non-empty listing without title-select is FORMS-NOT-FOUND
    res = plan_form_build(_FakeClient([]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"
    client = _FakeClient([{"id": "OtherFormId0000", "name": "Contact Us",
                           "hiddenFields": ["email"]}])
    res = plan_form_build(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"

    # ---- 5b. a slug-matched row with NO form id is an unreadable shape — a
    #      STOP, never a silent FORMS-NOT-FOUND
    try:
        plan_form_build(_FakeClient([{"name": "Title Select",
                                      "hiddenFields": ["anthology_id"]}]),
                        "loc_tmpl")
        raise AssertionError("an id-less slug-matched row must STOP")
    except FormsBuildError:
        pass

    # ---- 5c. a container that is not an array is a malformed shape — a
    #      STOP, never a guessed set
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["hiddenFields"] = "anthology_id"
    try:
        plan_form_build(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a non-array hidden-field container must STOP")
    except FormsBuildError:
        pass
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["fields"] = "title"
    try:
        plan_form_build(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a non-array fields container must STOP")
    except FormsBuildError:
        pass

    # ---- 6. a CONTAINER-LESS row is fixable (the routing pair REQUIRES the
    #      keys) — the pre-write proof names the absence, the dry-run
    #      refuses, and --execute applies the full shape
    rows = [dict(r) for r in _golden_rows()]
    del rows[2]["hiddenFields"]
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl")
    assert res["ok"] is False and res["hidden_current"] == [], \
        "a container-less row must surface the absence, got %r" % res
    assert res["af_code"] == "DRY-RUN"
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["hidden_current"] == list(HIDDEN_LAW)

    # ---- 6b. the intake trio is NOT the title-select shape: a row carrying
    #      contact_id (the intake trio) still lacks the stage routing key —
    #      a drift — the write adds the true key and surfaces the wrong set
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["hiddenFields"] = ["contact_id", "anthology_id"]
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", \
        "the intake trio must never satisfy the title-select shape law"
    client = _FakeClient(rows)
    res = plan_form_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the build must add the stage key under --execute"
    assert res["hidden_current"] == list(HIDDEN_LAW)

    # ---- 7. never-a-token: a hidden-field surface that IS a credential-
    #      shaped string REFUSES the whole plan rather than print it; a
    #      pinned id that is credential-shaped refuses the same way
    rows = [dict(r) for r in _golden_rows()]
    rows[2]["hiddenFields"] = ["pit-abc123", "anthology_id"]
    try:
        plan_form_build(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a credential-shaped hidden field must refuse")
    except FormsBuildError:
        pass
    try:
        plan_form_build(_FakeClient(_golden_rows()), "loc_tmpl",
                        pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except fr.FormsReadError:
        pass

    # ---- 8. a validation refusal on the PUT (400/409/422) is a STOP, never
    #      a silent skip; an applied-but-unreadable PUT is HELD (the live
    #      state is UNDETERMINED, never reported as built), and a scope
    #      refusal on the read-back stays a real STOP, never demoted
    try:
        plan_form_build(_FakeClient(_golden_rows(), fail_put=True),
                        "loc_tmpl", execute=True)
        raise AssertionError("a PUT validation refusal must stop")
    except FormsBuildError:
        pass

    class _WriteButUnreadableClient(_FakeClient):
        """The PUT is accepted, but every read after it raises transport —
        the applied-but-unreadable seam (HELD family, never fabricated)."""

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == DEFAULT_TITLE_SELECT_FORM_ID:
                        row["hiddenFields"] = list(HIDDEN_LAW)
                        row["fields"] = list(_normalized_fields_law(()))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.CafUnreachable("read-back transport failure (fixture)")

    try:
        plan_form_build(_WriteButUnreadableClient(_golden_rows()),
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
                    if fr._row_id(row) == DEFAULT_TITLE_SELECT_FORM_ID:
                        row["hiddenFields"] = list(HIDDEN_LAW)
                        row["fields"] = list(_normalized_fields_law(()))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")

    try:
        plan_form_build(_ScopeOnReadbackClient(_golden_rows()),
                        "loc_tmpl", execute=True)
        raise AssertionError("a scope refusal on the read-back must STOP")
    except reg.ScopeDenied:
        pass

    # ---- 9. the surface contract: the golden dry-run and the golden apply
    #      never emit a credential-shaped string anywhere on the payload
    for kwargs in ({}, {"execute": True}):
        dumped = json.dumps(
            plan_form_build(_FakeClient(_golden_rows()), "loc_tmpl", **kwargs),
            indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(dumped), \
            "a builder surface must never carry a credential-shaped string"

    dev.write("[title-select-builder] self-test PASS: title-select shape law "
              "pinned (hidden anthology_id / stage — exactly two, never the "
              "intake trio; visible title / subtitle multi-line REQUIRED), "
              "golden drift (stage + visible pair missing) refused in "
              "dry-run, execute apply + read-back proven (ONE PUT, re-read "
              "in the same job), idempotent no-op writes nothing, "
              "container-spelling drift normalized, visible-field drift "
              "repaired, pin law both ways, FORMS-EMPTY / FORMS-NOT-FOUND "
              "named, container-less row fixable, the intake trio never "
              "satisfies the shape, credential-shaped values refused, PUT "
              "validation STOP\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[title-select-builder] SELF-TEST FAILED: %s\n"
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
        "form_slug": FORM_SLUG,
        "hidden_fields_law": list(HIDDEN_LAW),
        "visible_fields_law": [dict(f) for f in VISIBLE_FIELDS],
        "write": "public v2 %s (Version %s; CAF_BROWSER_UA on the request — "
                 "CF 1010 law) — REFUSED without --execute"
                 % (FORMS_WRITE_PATH % "<formId>", reg.CAF_VERSION_HEADER),
        "read": "public v2 %s?locationId=<loc> (Version %s; CAF_BROWSER_UA on "
                "the request — CF 1010 law)"
                % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
        "note": "offline plan only — no network, no credential needed; the "
                "live title-select form's shape is normalized to the S3 law "
                "(the two routing hidden keys and the two visible multi-line "
                "required fields) ONLY with --execute, and a read-back that "
                "does not prove the build is a MISMATCH (exit 5), never a "
                "reported success",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise FormsBuildError(
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
    masked = mask_id(location_id)
    result = plan_form_build(client, location_id, pinned_id=pinned_id,
                             execute=execute)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("ok"):
        if result.get("applied"):
            out.write("[title-select-builder] OK (marker %s): the "
                      "title-select form was built — hidden %s, visible %s "
                      "(multi-line, required) — and read back byte-exact.\n"
                      % (masked, ", ".join(HIDDEN_LAW),
                         ", ".join(f["name"] for f in result.get("fields_law")
                                   or [])))
        else:
            out.write("[title-select-builder] OK (marker %s): the live "
                      "title-select form already carries the S3 shape — "
                      "idempotent no-op, nothing written.\n" % masked)
        return EX_OK
    if result.get("af_code") == "DRY-RUN":
        out.write("[title-select-builder] DRY-RUN (marker %s): the live "
                  "title-select form carries %s hidden keys — the build is "
                  "PLANNED, not applied. Re-run with --execute to write "
                  "(contract %s).\n"
                  % (masked, ", ".join(result.get("hidden_current") or [])
                     or "<no hidden-field surface>",
                     ", ".join(HIDDEN_LAW)))
        return EX_MISMATCH
    if result.get("af_code") == "READBACK-MISMATCH":
        out.write("[title-select-builder] MISMATCH (marker %s): the PUT "
                  "returned success but the read-back does not prove the "
                  "build — AF-AE-READBACK-MISMATCH, never reported as "
                  "built.\n" % masked)
        return EX_MISMATCH
    # FORMS-EMPTY / FORMS-NOT-FOUND (and any other refusal) -> STOP: the
    # title-select form cannot be identified, so no write can be planned.
    reg._stop(out, "The title-select form cannot be identified on this "
              "location.",
              ["AF-AE-TEMPLATE-PIPELINE-MISSING family: no title-select row "
               "matched the slug law" + (", or the pinned form id is absent "
               "from the listing" if pinned_id else "") + ".",
               "Restore the title-select form (or pass --form-id with the "
               "pinned engine id) and re-run.",
               "Location marker: %s" % masked])
    return EX_STOP


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="title_select_builder.py",
        description="Build the S3 title-select form on the Anthology "
                    "Convert and Flow location: the two routing hidden "
                    "fields (anthology_id, stage) and the two visible "
                    "multi-line REQUIRED fields (title, subtitle) via "
                    "public v2 PUT /forms/{id} — REFUSED without --execute; "
                    "dry-run otherwise. One JSON object on stdout; never "
                    "prints a secret (Skill 59, U08/U09).")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned title-select form id (default: the engine "
                         "fleet value %s; masked on every surface; a pinned id "
                         "absent from the listing refuses the plan)"
                         % DEFAULT_TITLE_SELECT_FORM_ID)
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
    pinned_id = args.form_id.strip() or DEFAULT_TITLE_SELECT_FORM_ID

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
                       % mask_id(location_id)])
            return EX_STOP
        # The location id on every operator surface is the masked marker only.
        return _run_apply(reg.CafClient(token), location_id, pinned_id,
                          execute=args.execute, out=sys.stderr)

    except FormsBuildError as exc:
        sys.stderr.write("[title-select-builder] STOP: %s\n" % exc)
        return EX_STOP
    except fr.FormsReadError as exc:
        sys.stderr.write("[title-select-builder] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[title-select-builder] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[title-select-builder] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[title-select-builder] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[title-select-builder] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
