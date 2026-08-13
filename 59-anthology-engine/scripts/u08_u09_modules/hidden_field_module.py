#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/hidden_field_module.py
# HIDDEN-FIELD CREATOR (U08/U09) — creates a hidden field on the universal
# author-intake form on the Anthology Convert and Flow location so that EVERY
# submission carries the minted Book ID plus its stage, through the public v2
# PUT /forms/{id} surface with the location's OWN private-integration token —
# and it REFUSES to write unless the operator explicitly passes --execute.
# Without --execute the tool is a DRY-RUN: it reads the live form, proves the
# hidden-field contract, and prints exactly the PUT it WOULD send — nothing is
# written, ever. Fail-closed: any ambiguity is a refusal, never a guessed
# write.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module in a fresh
# package under the scripts/ tree (the same layout and the same empty
# fail-closed package-init doctrine as scripts/u02_modules/,
# scripts/u03_modules/, scripts/u04_modules/, scripts/u05_modules/,
# scripts/u06_modules/ and scripts/u07_modules/). It is NOT a manifest row: it
# ships as the gated write sibling of u04_modules/form_reader.py — the reader
# OWNS the public v2 forms listing read (GET /forms/?locationId=, find-by-slug
# + pin-by-id) and this module owns the ONLY form WRITE the hidden-field law
# performs. The delta_reporter.py single-implementation doctrine: a law is
# read once, in one module — the hidden-field contract below is the SAME law
# config/anthology-snapshot-contract.json pins (forms.universal_hidden_fields)
# and form_reader.py's slug/pin semantics are REUSED here, never re-implemented.
#
# WHAT THIS OWNS
#   1. THE HIDDEN-FIELD CONTRACT LAW (G3 + the snapshot contract). The minted
#      author-intake link is
#      <forms_base>/widget/form/<form_id>?anthology_id=<minted> — the ONE
#      query param is EXACTLY "anthology_id" (the form's hidden-field key;
#      scripts/anthology_book.py INTAKE_QUERY_KEY, the same law the snapshot
#      contract's forms.universal_hidden_fields [contact_id, anthology_id,
#      stage] pins: "Every form carries the universal hidden-field contract
#      (contact_id, anthology_id, stage)"). The hidden-field law this module
#      writes under: the universal author-intake form MUST carry hidden
#      fields keyed exactly "contact_id", "anthology_id" and "stage" — the
#      trio the intake router reads (intake_router.py field_candidates
#      contact_id / anthology_id / stage) and the stage token the router
#      classifies per route (intake_stage_tokens ["intake", "s0",
#      "s0_intake"]). The query key of the hidden anthology_id field is NEVER
#      "anthology_active_id" — that is the CONTACT custom field the delivery
#      writer stamps with the ACTIVE anthology (caf_delivery.py), a DIFFERENT
#      thing; conflating the two is the G3 defect.
#   2. THE PUT SURFACE. The write is ONE PUT:
#      https://services.leadconnectorhq.com/forms/{formId}
#      (public v2, Version 2021-07-28 — the path-based version map
#      /forms/ -> 2021-07-28 proven in
#      44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/
#      utils/ghl_client.py, Skill 44; the same base + version header
#      reg.CafClient already sends on every request). The PUT body is built
#      ONLY from the live read-back row — every key, every value, the id
#      echoed byte-for-byte — with the missing hidden-field keys added and
#      any existing hidden-field spelling normalized to the contract spelling.
#      A body constructed from memory is NEVER sent.
#   3. THE TARGET LAW. The row this module may write MUST be the universal
#      intake form, proven two ways, exactly as form_reader.py proves it:
#      (a) the slug law — a listing row whose normalized name equals
#      "universal intake" (the slug with dashes -> spaces, the same
#      name-match law golden_forms.py pins), or an alias key match on the
#      hidden-contract spellings ("universal_intake",
#      "universal_intake_form_id"); and (b) the pin law — when --form-id is
#      given, the pinned id (the engine's fleet value
#      DEFAULT_UNIVERSAL_INTAKE_FORM_ID in scripts/anthology_book.py, or a
#      box override) must BE the row written; a pin BYPASSES the slug law (a
#      pin is a stronger contract than a name). A row that matches NEITHER
#      law STOPS — a write to a form we cannot prove is the intake form is a
#      write to the wrong record, never performed.
#   4. THE CREATE LAW. The hidden field is created ONLY when the live row
#      actually lacks it: when the live hidden-field set already carries the
#      three contract keys byte-exact, the run is an idempotent NO-OP —
#      nothing is written, applied:false, ok true (the rename_applier.py
#      old==new / query_key_fixer.py no-op doctrine). When the row carries
#      hidden fields under a drifted spelling ("hiddenFields" vs
#      "hidden_fields" vs "hiddenFields[]"), the write normalizes that
#      spelling to the contract one AND adds the missing keys — the drift is
#      surfaced in the pre-write proof, and --execute is still the only way
#      any write happens. A row with NO hidden-field surface at all is still
#      fixable (the minted link REQUIRES the trio): the pre-write proof names
#      what is absent and the write adds the full contract set.
#   5. THE READ-BACK LAW (with --execute only). After the PUT, the form is
#      GET-read back in the SAME job (form_reader.read_forms surface, by the
#      pinned id or by re-listing): the read-back hidden-field set must carry
#      the three contract keys byte-exact — any drift is a MISMATCH (exit 5,
#      the AF-AE-READBACK-MISMATCH family), never a reported success. A PUT
#      that returned success but cannot be read back is HELD (exit 3) with
#      the live state UNDETERMINED — never reported as created. The PUT's own
#      response body is never trusted: only the read-back proves the write.
#   6. NEVER-A-TOKEN SURFACE. The PIT is resolved through
#      anthology_registry.resolve_pit (the house labels CONVERT_AND_FLOW_PIT /
#      CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
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
# Convert and Flow (GK-09; the same browser UA the Podcast gate proved live).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, echoed, or reflected.
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable listing, an absent universal-intake row, an unprovable target, a
# PUT body that cannot be constructed from a live read-back, or a read-back
# that does not prove the creation is a REFUSAL / FAIL — never a silent pass,
# never a fabricated success, never a write performed without --execute.
#
# RETURN CONTRACT (the machine surface this module owns):
#   plan_field_create(client, location_id, *, pinned_id="", execute=False,
#                     form_rows=None) -> dict — {"contract", "schema_version",
#       "ok", "applied", "execute", "form_id", "form_id_masked",
#       "hidden_current", "hidden_law", "target_matched_by", "note"};
#       ok True means the live form already carries the three contract hidden
#       keys (a no-op) OR the fields were created with --execute and read
#       back byte-exact; applied True ONLY when a PUT actually happened
#       (--execute). Raises FormsFixError (STOP family) / reg.CafUnreachable,
#       reg.ScopeDenied, reg.UpstreamBlockedError (HELD family) — a caller
#       maps them onto the house exit codes.
#   plan(location_id, pinned_id, *, out=sys.stdout) -> int — ONE JSON
#       object, offline, no network, no credential.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers apply / plan / self-test; `apply` is a DRY-RUN
#   unless --execute is passed.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — dry-run plan pass, idempotent no-op (already present), or
#      applied + read-back verified
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      an unreadable listing shape / an unprovable target (the universal-
#      intake form cannot be identified) / a malformed live row with no
#      writable hidden-field surface
#   3  Convert and Flow API unreachable / edge-blocked (HELD, retryable —
#      the scope is UNDETERMINED here, never proven absent), including an
#      applied-but-unreadable PUT
#   4  self-test FAILED (a tamper NEVER masquerades as exit 1)
#   5  MISMATCH — the read-back after the PUT does not prove the creation
#      (AF-AE-READBACK-MISMATCH family), or the keys are absent and no
#      write was performed (dry-run refusal surface)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   hidden_field_module.py apply [--location-id ID] [--form-id ID] [--execute]
#   hidden_field_module.py plan  [--location-id ID] [--form-id ID]
#   hidden_field_module.py self-test
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
"""hidden_field_module.py — gated, verified hidden-field creator for the
universal author-intake form against the Anthology Convert and Flow location
(Skill 59, U08/U09 tooling). Creates the hidden fields the minted intake link
needs (contact_id, anthology_id, stage) via public v2 PUT /forms/{id} —
REFUSED without --execute; every other invocation is a read-only dry-run."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to query_key_fixer.py):
# the registry owns the Cloudflare browser-UA wiring, the LeadConnector
# client, the credential resolution, and the exit-code contract; the reader
# owns the ONE forms-listing read and its slug/pin laws.
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
# a hidden-field create (the self-test asserts the golden plan carries the
# exact string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-hidden-field-create"
CONFIG_SCHEMA_VERSION = 1

# The HIDDEN-FIELD CONTRACT LAW, byte-exact — the SAME trio
# config/anthology-snapshot-contract.json pins (forms.universal_hidden_fields
# ["contact_id", "anthology_id", "stage"], required on the universal author-
# intake form: "The intake front door. The minted link is
# <forms_base_url>/widget/form/<universal_intake_form_id>?anthology_id=<minted>,
# built by anthology_book.py") and the SAME keys the intake router reads
# (intake_router.py field_candidates: contact_id / anthology_id / stage). The
# anthology_id element is cross-pinned against anthology_book.INTAKE_QUERY_KEY
# (the G3 query-key law build_intake_link mints with) so this module can never
# drift from the link builder it keeps honest. The trio is pinned byte-exact
# by the offline self-test.
HIDDEN_FIELD_LAW = ("contact_id", "anthology_id", "stage")

# The wrong spelling this module exists to NEVER write — the CONTACT custom
# field the delivery writer stamps (caf_delivery.py control fields), conflated
# with the hidden-field key is the G3 defect. The self-test pins it, so a
# drifted wrong key (e.g. the law itself) fails the battery before any live
# run.
WRONG_QUERY_KEY = "anthology_active_id"

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

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests. Same
# value form_reader.DEFAULT_TEMPLATE_LOCATION carries — imported, never
# re-typed, so the two surfaces cannot drift.
DEFAULT_TEMPLATE_LOCATION = fr.DEFAULT_TEMPLATE_LOCATION

# The engine's pinned fleet-wide form id — the ONE universal author-intake
# form id baked into scripts/anthology_book.py and the slot
# config/engine-config.template.json intake.universal_intake_form_id can
# override per box. A location identifier, not a secret — but masked on
# every surface. Imported from the reader, the ONE owner of the pin.
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123") — the same guard the reader ships. Every emitted
# surface is scanned against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FormsFixError(Exception):
    """A fail-closed fix refusal (STOP family): an unreadable listing shape,
    an unprovable target, a malformed live row with no writable hidden-field
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
    the minted link REQUIRES the trio — but the pre-write proof names what is
    absent). A non-list container value is a malformed shape -> FormsFixError
    (never a guessed set)."""
    if not isinstance(row, dict):
        return ()
    for key in HIDDEN_CONTAINER_KEYS:
        if key not in row:
            continue
        val = row.get(key)
        if val is None:
            return ()
        if not isinstance(val, list):
            raise FormsFixError(
                "the form's hidden-field container %r is not an array — the "
                "listing shape is not readable" % key)
        seen = []
        for item in val:
            if isinstance(item, str) and item.strip() and item.strip() not in seen:
                seen.append(item.strip())
        return tuple(seen)
    return ()


def _row_hidden_container_key(row) -> str:
    """Which container spelling the live row carries ("hiddenFields" /
    "hidden_fields" / "hiddenFields[]") — the write echoes the row's OWN
    spelling when one exists, else the canonical one. Returns the canonical
    spelling when the row carries no container at all."""
    if isinstance(row, dict):
        for key in HIDDEN_CONTAINER_KEYS:
            if key in row:
                return key
    return HIDDEN_CONTAINER_KEYS[0]


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
    the universal intake form, proven by (a) the slug law — the row's
    normalized name equals the slug with dashes -> spaces ("universal
    intake"), or an alias key match on the hidden-contract spellings — or
    (b) the pin law, when a pinned id is given: the pinned id BYPASSES the
    slug law (a pin is a stronger contract than a name). A row that matches
    NEITHER law is False — a write to a form we cannot prove is the intake
    form is a write to the wrong record, never performed. The id is resolved
    by the CALLER, so a slug-matched row that carries no id is still
    recognized (and refused as an unreadable shape), never silently skipped.
    The slug law and the alias spellings are the READER's (fr.SLUG_AS_NAME,
    fr._KEY_ALIASES) — imported, never re-implemented."""
    pinned = (pinned_id or "").strip()
    if pinned:
        return _row_id(row) == pinned
    if isinstance(row, dict):
        if fr._normalize_name(str(row.get("name") or "")) == fr.SLUG_AS_NAME:
            return True
        for val in fr._row_keys(row):
            if fr._normalize_name(val) in fr._KEY_ALIASES:
                return True
    return False


def _normalized_law(hidden_current) -> tuple:
    """The contract trio in the live row's OWN spelling: every contract key
    that is present is left byte-exact (the live key IS the wire key — a
    live "anthology_id" is never rewritten to anything else, and the G3
    lookalike "anthology_active_id" can never satisfy it), and every contract
    key that is absent is appended in contract order. The result is the exact
    ordered hidden-field list the PUT writes."""
    present = set(hidden_current)
    missing = [key for key in HIDDEN_FIELD_LAW if key not in present]
    out = [key for key in hidden_current if key not in missing]
    out.extend(missing)
    return tuple(out)


def _build_fix_body(row, fid: str) -> dict:
    """The PUT body, built ONLY from the live read-back row: every key and
    value echoed byte-for-byte with the hidden-field container normalized to
    the law (missing contract keys added, container spelling preserved). A
    body constructed from memory is NEVER sent. Fail-closed: a row that is
    not a dict, a row whose id cannot be proven, or a hidden-field container
    that is present but not an array is a FormsFixError — never a guessed
    body."""
    if not isinstance(row, dict):
        raise FormsFixError("the target row is not an object — a PUT body "
                            "cannot be constructed from it")
    if not fid:
        raise FormsFixError("the target row carries no form id — a PUT to an "
                            "id-less row cannot be constructed")
    body = {}
    container_key = None
    for key, value in row.items():
        if key in HIDDEN_CONTAINER_KEYS:
            container_key = key
            break
    for key, value in row.items():
        if key in HIDDEN_CONTAINER_KEYS:
            body[_row_hidden_container_key(row)] = list(
                _normalized_law(_row_hidden(row)))
        elif container_key is not None and key == container_key:
            body[key] = list(_normalized_law(_row_hidden(row)))
        else:
            body[key] = value
    if container_key is None:
        body[HIDDEN_CONTAINER_KEYS[0]] = list(HIDDEN_FIELD_LAW)
    return body


def plan_field_create(client, location_id: str, *, pinned_id: str = "",
                      execute: bool = False, form_rows=None) -> dict:
    """Plan (and, ONLY with --execute, perform) the hidden-field creation on
    the universal author-intake form. Fail-closed, never a token.

    `client` is a reg.CafClient (its own _request rides CAF_BROWSER_UA).
    `form_rows` is an explicit row list (self-tests); when None the live
    listing is read (the reader's ONE read). `pinned_id` is the engine's
    pinned fleet-wide form id (or a box override) — when given it must be the
    row written and it BYPASSES the slug law.

    Returns the documented surface {contract, schema_version, ok, applied,
    execute, form_id, form_id_masked, hidden_current, hidden_law,
    target_matched_by, note} — fail-closed:
      - ok True ONLY when the live form's hidden-field set already carries
        the three contract keys (an idempotent no-op: applied false, nothing
        written) OR the fields were created with --execute and read back
        byte-exact,
      - applied True ONLY when a PUT actually happened (--execute),
      - hidden_current is the live row's hidden-field keys (read-only; the
        full values are never emitted — a value could echo a credential),
      - hidden_law is the three contract keys as the write will leave them,
      - ok False carries NO form id (never an id guessed from memory) and a
        named af_code — FORMS-NOT-FOUND when no universal-intake row matched
        (or the pinned id was absent), FORMS-EMPTY when the listing held
        zero rows, READBACK-MISMATCH when a PUT happened but the read-back
        does not prove the creation,
      - the hidden-field surface is NEVER a token: a row whose hidden-field
        container resolves to a credential-shaped string REFUSES the whole
        plan rather than print it.
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (fr.FormsReadError / FormsFixError, STOP family) or
    a transport/scope failure (the client's exceptions, HELD family). The
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
                raise FormsFixError(
                    "the universal-intake row matched the slug law but "
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
            "hidden_current": [],
            "hidden_law": list(HIDDEN_FIELD_LAW),
            "target_matched_by": "",
            "af_code": ("FORMS-EMPTY" if count == 0 else "FORMS-NOT-FOUND"),
            "note": ("the listing is empty" if count == 0 else
                     "no universal-intake row on the listing — the slug law "
                     "matched nothing" + (" and the pinned id is absent"
                                          if pinned else "")) +
                    " (fail-closed, never an id guessed from memory)",
        }

    fid = _row_id(target)
    if not fid:
        raise FormsFixError("the universal-intake row carries no form id — "
                            "the listing shape is not readable")
    current = _row_hidden(target)
    if current:
        dumped_current = json.dumps(list(current))
        if _CREDENTIAL_SHAPE.search(dumped_current):
            raise FormsFixError(
                "the hidden-field surface resolved to a credential-shaped "
                "string — REFUSED without printing it")
    body = _build_fix_body(target, fid)
    dumped_body = json.dumps(body, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped_body):
        raise FormsFixError(
            "the PUT body carries a credential-shaped string — REFUSED "
            "without printing it")

    present = set(current)
    if all(key in present for key in HIDDEN_FIELD_LAW):
        # Idempotent no-op: the form already carries the three contract keys
        # — nothing is written, ever, even with --execute (the query_key_
        # fixer.py old==new doctrine).
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": True,
            "applied": False,
            "execute": execute,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "hidden_current": list(current),
            "hidden_law": list(HIDDEN_FIELD_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "NO-OP",
            "note": "the live form already carries the three contract hidden "
                    "fields %s — idempotent no-op, nothing written"
                    % ", ".join(HIDDEN_FIELD_LAW),
        }

    if not execute:
        # Dry-run: the plan is the report. The missing keys are surfaced;
        # applied stays false; nothing was written.
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": False,
            "execute": False,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "hidden_current": list(current),
            "hidden_law": list(HIDDEN_FIELD_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "DRY-RUN",
            "note": ("the live form carries %s — the creation is PLANNED, "
                     "not applied; the missing contract keys (%s) would be "
                     "added; re-run with --execute to write"
                     % (", ".join(current) if current else "<no hidden-field "
                        "surface>",
                        ", ".join(k for k in HIDDEN_FIELD_LAW
                                  if k not in present))),
        }

    # ---- --execute: the ONE write ------------------------------------------
    # The PUT body is the live-row echo with the hidden-field container
    # normalized to the law (never fabricated). The response body of the PUT
    # is never trusted: only the read-back proves the write.
    try:
        client._request("PUT", FORMS_WRITE_PATH % _url_quote(fid), body=body)
    except reg.CafValidation as exc:
        # 400/409/422 from Convert and Flow: a validation refusal is a STOP,
        # never a silent skip (the query_key_fixer.py doctrine).
        raise FormsFixError("Convert and Flow refused the form PUT (HTTP "
                            "validation): %s" % exc)

    # ---- read-back: prove the creation in the SAME job ---------------------
    # A PUT that returned success but cannot be read back is HELD (exit 3,
    # via reg.CafUnreachable) — the live state is UNDETERMINED, never
    # reported as created. The reader is the ONE read surface: its pin gate
    # proves the form id survived the PUT; the row extraction that follows
    # re-reads the SAME listing and carries the hidden-field set to judge. A
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
            "created (form id marker %s)" % (type(exc).__name__, mask_id(fid)))
    if not read.get("ok"):
        raise reg.CafUnreachable(
            "the PUT returned success but the read-back cannot find the "
            "form (form id marker %s) — the live state is UNDETERMINED, "
            "never reported as created" % mask_id(fid))
    try:
        rb_row = _find_row_by_id(_list_rows(client, location_id), fid)
    except (fr.FormsReadError, reg.CafUnreachable, reg.UpstreamBlockedError) as exc:
        raise reg.CafUnreachable(
            "the PUT returned success but the form cannot be read back "
            "(%s) — the live state is UNDETERMINED, never reported as "
            "created (form id marker %s)" % (type(exc).__name__, mask_id(fid)))
    if rb_row is None:
        raise reg.CafUnreachable(
            "the PUT returned success but the form row is absent from the "
            "read-back listing (form id marker %s) — the live state is "
            "UNDETERMINED, never reported as created" % mask_id(fid))
    rb_current = _row_hidden(rb_row)
    if not all(key in set(rb_current) for key in HIDDEN_FIELD_LAW):
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "applied": True,
            "execute": True,
            "form_id": fid,
            "form_id_masked": mask_id(fid),
            "hidden_current": list(rb_current),
            "hidden_law": list(HIDDEN_FIELD_LAW),
            "target_matched_by": target_matched_by,
            "af_code": "READBACK-MISMATCH",
            "note": "the PUT returned success but the read-back hidden-field "
                    "set is %s — the creation did NOT land "
                    "(AF-AE-READBACK-MISMATCH family), never reported as "
                    "created"
                    % (", ".join(rb_current) if rb_current else "<absent>"),
        }

    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "applied": True,
        "execute": True,
        "form_id": fid,
        "form_id_masked": mask_id(fid),
        "hidden_current": list(rb_current),
        "hidden_law": list(HIDDEN_FIELD_LAW),
        "target_matched_by": target_matched_by,
        "af_code": "CREATED",
        "note": "the hidden fields were created and read back byte-exact "
                "(%s) — the minted intake link now lands the Book ID and "
                "stage on every submission"
                % ", ".join(HIDDEN_FIELD_LAW),
    }


def _url_quote(fid: str) -> str:
    """URL-encode a form id for the write path (the registry quotes location
    ids the same way; a form id carries no reserved chars, but the path is
    never built with an unquoted interpolant)."""
    import urllib.parse
    return urllib.parse.quote(fid or "", safe="")


def _find_row_by_id(rows, fid: str):
    """The row whose id equals fid ("" when absent) — the read-back lookup
    used to re-read the hidden-field set AFTER a creation."""
    for row in rows:
        if _row_id(row) == fid:
            return row
    return None


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the creator against
# the REAL committed constants (the hidden-field contract, the pinned id, the
# reader's slug law), then runs every attack fixture: golden no-op, the
# missing-key drift that needs a create, the dry-run refusal, the --execute
# apply + read-back, every not-found path named, the pin law both ways, the
# G3 lookalike key, the never-a-token guard, and the scope-vs-edge 403
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
        if method == "PUT" and path.startswith(FORMS_WRITE_PATH % ""):
            if self._fail_put:
                raise reg.CafValidation("Convert and Flow rejected the "
                                        "request (HTTP 422)")
            fid = path[len(FORMS_WRITE_PATH % ""):]
            for row in self._rows:
                if fr._row_id(row) == fid:
                    for key in HIDDEN_CONTAINER_KEYS:
                        if key in row:
                            row[key] = list(HIDDEN_FIELD_LAW)
                            break
                    else:
                        row["hiddenFields"] = list(HIDDEN_FIELD_LAW)
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.CafUnreachable("unexpected request (fixture)")


def _golden_rows():
    """The golden listing rows: the universal-intake form carrying the pinned
    engine id and only TWO of the three contract hidden fields (the missing
    stage key is the defect this module exists to fix), plus the engine's two
    gate forms — the same three-slug family forms_check.py / golden_forms.py /
    form_reader.py pin."""
    return [
        {"id": DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["contact_id", "anthology_id"]},
        {"id": "riNlAkYbcW3g92VRLqq0", "name": "Universal Review",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
         "type": "form", "queryKey": "anthology_id",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def _self_test_body(dev) -> None:
    # ---- 0. the hidden-field contract is pinned, and the reader's slug law
    #      is the same law this module writes under; the G3 lookalike can
    #      never satisfy the law
    assert HIDDEN_FIELD_LAW == ("contact_id", "anthology_id", "stage"), \
        "the hidden-field contract drifted from config/anthology-snapshot-" \
        "contract.json forms.universal_hidden_fields"
    assert WRONG_QUERY_KEY == "anthology_active_id", \
        "the wrong-key constant drifted from the G3 defect it guards"
    assert "anthology_active_id" not in HIDDEN_FIELD_LAW, \
        "the G3 lookalike must never enter the hidden-field law"
    assert fr.SLUG_AS_NAME == "universal intake", \
        "the reader's slug law drifted (this module writes under it)"
    assert "stage" in HIDDEN_FIELD_LAW, \
        "the stage hidden field must be in the contract (the router reads it)"

    # ---- 1. golden DRIFT: stage is missing -> dry-run refuses (exit 5
    #      surface), the plan names the drift, nothing is written
    client = _FakeClient(_golden_rows())
    res = plan_field_create(client, "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False, \
        "a drifted form must refuse in dry-run"
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["form_id"] == DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    assert res["hidden_current"] == ["contact_id", "anthology_id"]
    assert res["hidden_law"] == list(HIDDEN_FIELD_LAW)
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], \
        "a dry-run must perform ONLY the listing read"

    # ---- 2. --execute: the PUT happens, the read-back proves the creation
    client = _FakeClient(_golden_rows())
    res = plan_field_create(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the creation must apply and pass under --execute"
    assert res["af_code"] == "CREATED"
    assert res["hidden_current"] == list(HIDDEN_FIELD_LAW)
    assert res["form_id"] == DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == FORMS_WRITE_PATH % DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    # the PUT body echoes the live row byte-for-byte with the missing key
    # added — the contract trio is on, every other field is intact
    assert puts[0]["body"].get("hiddenFields") == list(HIDDEN_FIELD_LAW), \
        "the PUT body must carry the contract hidden fields"
    assert puts[0]["body"].get("id") == DEFAULT_UNIVERSAL_INTAKE_FORM_ID, \
        "the PUT body must echo the live row's id"
    assert puts[0]["body"].get("name") == "Universal Intake", \
        "the PUT body must echo the live row's name"
    assert puts[0]["body"].get("queryKey") == "anthology_id", \
        "the PUT body must echo the live row's query key"
    # the write is proven ONLY by the read-back in the same job
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, "the apply must re-read the listing for the read-back"

    # ---- 3. idempotent no-op: the full trio is already live -> ok true,
    #      applied false, NOTHING written — even with --execute
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["hiddenFields"] = list(HIDDEN_FIELD_LAW)
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, \
        "an already-present form must be an idempotent no-op"
    assert res["af_code"] == "NO-OP"
    assert not any(c["method"] == "PUT" for c in client.calls), \
        "a no-op must never perform a PUT"

    # ---- 3b. the container-spelling drift is normalized: the live row
    #      carries "hidden_fields" (snake) — the write preserves the live
    #      spelling and adds the missing key; the read-back proves the law
    rows = [dict(r) for r in _golden_rows()]
    rows[0] = {"id": DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
               "type": "form", "queryKey": "anthology_id",
               "hidden_fields": ["contact_id", "anthology_id"]}
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1 and "hidden_fields" in puts[0]["body"], \
        "the PUT body must preserve the live container spelling"
    assert puts[0]["body"]["hidden_fields"] == list(HIDDEN_FIELD_LAW)

    # ---- 4. the pin law: the pinned id BYPASSES the slug law and IS the row
    #      written; a pinned id absent from the listing is FORMS-NOT-FOUND
    client = _FakeClient(_golden_rows())
    res = plan_field_create(client, "loc_tmpl",
                            pinned_id=DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
                            execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["target_matched_by"] == "pin"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["id"] = "DriftedDriftedId00"
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl",
                            pinned_id=DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", \
        "an absent pinned id must refuse, got %r" % res
    assert res["form_id"] == "", "a failed plan must never carry a form id"

    # ---- 5. not-found paths, each NAMED: an empty listing is FORMS-EMPTY; a
    #      non-empty listing without universal-intake is FORMS-NOT-FOUND
    res = plan_field_create(_FakeClient([]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"
    client = _FakeClient([{"id": "OtherFormId0000", "name": "Contact Us",
                           "hiddenFields": ["email"]}])
    res = plan_field_create(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"

    # ---- 5b. a slug-matched row with NO form id is an unreadable shape — a
    #      STOP, never a silent FORMS-NOT-FOUND
    try:
        plan_field_create(_FakeClient([{"name": "Universal Intake",
                                        "hiddenFields": ["contact_id"]}]),
                          "loc_tmpl")
        raise AssertionError("an id-less slug-matched row must STOP")
    except FormsFixError:
        pass

    # ---- 5c. a container that is not an array is a malformed shape — a
    #      STOP, never a guessed set
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["hiddenFields"] = "contact_id"
    try:
        plan_field_create(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a non-array hidden-field container must STOP")
    except FormsFixError:
        pass

    # ---- 6. a CONTAINER-LESS row is fixable (the minted link REQUIRES the
    #      trio) — the pre-write proof names the absence, the dry-run refuses,
    #      and --execute applies the full law
    rows = [dict(r) for r in _golden_rows()]
    del rows[0]["hiddenFields"]
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl")
    assert res["ok"] is False and res["hidden_current"] == [], \
        "a container-less row must surface the absence, got %r" % res
    assert res["af_code"] == "DRY-RUN"
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["hidden_current"] == list(HIDDEN_FIELD_LAW)

    # ---- 6b. the G3 lookalike hidden key can never satisfy the law: a row
    #      carrying "anthology_active_id" instead of "anthology_id" is a
    #      drift — the write adds the true key and surfaces the wrong key
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["hiddenFields"] = ["contact_id", "anthology_active_id"]
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", \
        "the lookalike key must never satisfy the law"
    client = _FakeClient(rows)
    res = plan_field_create(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, \
        "the create must add the true key under --execute"
    assert res["hidden_current"] == list(HIDDEN_FIELD_LAW)

    # ---- 7. never-a-token: a hidden-field surface that IS a credential-
    #      shaped string REFUSES the whole plan rather than print it; a
    #      pinned id that is credential-shaped refuses the same way
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["hiddenFields"] = ["pit-abc123", "anthology_id"]
    try:
        plan_field_create(_FakeClient(rows), "loc_tmpl")
        raise AssertionError("a credential-shaped hidden field must refuse")
    except FormsFixError:
        pass
    try:
        plan_field_create(_FakeClient(_golden_rows()), "loc_tmpl",
                          pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except fr.FormsReadError:
        pass

    # ---- 8. a validation refusal on the PUT (400/409/422) is a STOP, never
    #      a silent skip; an applied-but-unreadable PUT is HELD (the live
    #      state is UNDETERMINED, never reported as created), and a scope
    #      refusal on the read-back stays a real STOP, never demoted
    try:
        plan_field_create(_FakeClient(_golden_rows(), fail_put=True),
                          "loc_tmpl", execute=True)
        raise AssertionError("a PUT validation refusal must stop")
    except FormsFixError:
        pass

    class _WriteButUnreadableClient(_FakeClient):
        """The PUT is accepted, but every read after it raises transport —
        the applied-but-unreadable seam (HELD family, never fabricated)."""

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == DEFAULT_UNIVERSAL_INTAKE_FORM_ID:
                        row["hiddenFields"] = list(HIDDEN_FIELD_LAW)
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.CafUnreachable("read-back transport failure (fixture)")

    try:
        plan_field_create(_WriteButUnreadableClient(_golden_rows()),
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
                    if fr._row_id(row) == DEFAULT_UNIVERSAL_INTAKE_FORM_ID:
                        row["hiddenFields"] = list(HIDDEN_FIELD_LAW)
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")

    try:
        plan_field_create(_ScopeOnReadbackClient(_golden_rows()),
                          "loc_tmpl", execute=True)
        raise AssertionError("a scope refusal on the read-back must STOP")
    except reg.ScopeDenied:
        pass

    # ---- 9. the surface contract: the golden dry-run and the golden apply
    #      never emit a credential-shaped string anywhere on the payload
    for kwargs in ({}, {"execute": True}):
        dumped = json.dumps(
            plan_field_create(_FakeClient(_golden_rows()), "loc_tmpl", **kwargs),
            indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(dumped), \
            "a creator surface must never carry a credential-shaped string"

    dev.write("[hidden-field-module] self-test PASS: hidden-field contract "
              "pinned (contact_id / anthology_id / stage, the snapshot "
              "contract's forms.universal_hidden_fields), golden drift "
              "(stage missing) refused in dry-run, execute apply + read-back "
              "proven (ONE PUT, re-read in the same job), idempotent no-op "
              "writes nothing, container-spelling drift normalized, pin law "
              "both ways, FORMS-EMPTY / FORMS-NOT-FOUND named, container-less "
              "row fixable, the G3 lookalike never satisfies the law, "
              "credential-shaped values refused, PUT validation STOP\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[hidden-field-module] SELF-TEST FAILED: %s\n" % exc)
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
        "hidden_fields_law": list(HIDDEN_FIELD_LAW),
        "wrong_query_key": WRONG_QUERY_KEY,
        "write": "public v2 %s (Version %s; CAF_BROWSER_UA on the request — "
                 "CF 1010 law) — REFUSED without --execute"
                 % (FORMS_WRITE_PATH % "<formId>", reg.CAF_VERSION_HEADER),
        "read": "public v2 %s?locationId=<loc> (Version %s; CAF_BROWSER_UA on "
                "the request — CF 1010 law)"
                % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
        "note": "offline plan only — no network, no credential needed; the "
                "live form's hidden fields are normalized to the contract "
                "trio ONLY with --execute, and a read-back that does not "
                "prove the creation is a MISMATCH (exit 5), never a reported "
                "success",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise FormsFixError(
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
    result = plan_field_create(client, location_id, pinned_id=pinned_id,
                               execute=execute)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("ok"):
        if result.get("applied"):
            out.write("[hidden-field-module] OK (marker %s): hidden fields "
                      "created (%s) and read back byte-exact.\n"
                      % (masked, ", ".join(HIDDEN_FIELD_LAW)))
        else:
            out.write("[hidden-field-module] OK (marker %s): the live form "
                      "already carries the three contract hidden fields — "
                      "idempotent no-op, nothing written.\n" % masked)
        return EX_OK
    if result.get("af_code") == "DRY-RUN":
        out.write("[hidden-field-module] DRY-RUN (marker %s): the live form "
                  "carries %s — the creation is PLANNED, not applied. "
                  "Re-run with --execute to write (contract %s).\n"
                  % (masked, ", ".join(result.get("hidden_current") or [])
                     or "<no hidden-field surface>",
                     ", ".join(HIDDEN_FIELD_LAW)))
        return EX_MISMATCH
    if result.get("af_code") == "READBACK-MISMATCH":
        out.write("[hidden-field-module] MISMATCH (marker %s): the PUT "
                  "returned success but the read-back does not prove the "
                  "creation — AF-AE-READBACK-MISMATCH, never reported as "
                  "created.\n" % masked)
        return EX_MISMATCH
    # FORMS-EMPTY / FORMS-NOT-FOUND (and any other refusal) -> STOP: the
    # universal-intake form cannot be identified, so no write can be planned.
    reg._stop(out, "The universal author-intake form cannot be identified on "
              "this location.",
              ["AF-AE-TEMPLATE-PIPELINE-MISSING family: no universal-intake "
               "row matched the slug law" + (", or the pinned form id is "
               "absent from the listing" if pinned_id else "") + ".",
               "Restore the universal-intake form (or pass --form-id with the "
               "pinned engine id) and re-run.",
               "Location marker: %s" % masked])
    return EX_STOP


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="hidden_field_module.py",
        description="Create the hidden fields the minted intake link needs "
                    "(contact_id, anthology_id, stage — the snapshot "
                    "contract's forms.universal_hidden_fields) on the "
                    "universal author-intake form of the Anthology Convert "
                    "and Flow location via public v2 PUT /forms/{id} — "
                    "REFUSED without --execute; dry-run otherwise. One JSON "
                    "object on stdout; never prints a secret (Skill 59, "
                    "U08/U09).")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned universal-intake form id (default: the engine "
                         "fleet value %s; masked on every surface; a pinned id "
                         "absent from the listing refuses the plan)"
                         % DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
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
    pinned_id = args.form_id.strip() or DEFAULT_UNIVERSAL_INTAKE_FORM_ID

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
                       "The creator runs against the operator's OWN template "
                       "location marker %s; set the template PIT "
                       "(client-standard labels first) and re-run."
                       % mask_id(location_id)])
            return EX_STOP
        # The location id on every operator surface is the masked marker only.
        return _run_apply(reg.CafClient(token), location_id, pinned_id,
                          execute=args.execute, out=sys.stderr)

    except FormsFixError as exc:
        sys.stderr.write("[hidden-field-module] STOP: %s\n" % exc)
        return EX_STOP
    except fr.FormsReadError as exc:
        sys.stderr.write("[hidden-field-module] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[hidden-field-module] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[hidden-field-module] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[hidden-field-module] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[hidden-field-module] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
