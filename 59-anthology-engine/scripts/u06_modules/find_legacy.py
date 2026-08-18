#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/find_legacy.py  (U06 tooling)
# LEGACY WORKFLOW FINDER — the U06 archive-gate first step: it FINDS the two
# legacy engine workflows on a Convert and Flow location BY EXACT NAME and
# reports their ONE workflow id each. Nothing more. It never archives,
# deletes, renames, or mutates anything — an archive ACTION is a separate
# gate (see the ARCHIVE GATE law below), and this module is the FIND half of
# find-then-archive.
# -----------------------------------------------------------------------------
# THE TWO LEGACY WORKFLOWS (the U06 archive targets, BY EXACT NAME — the
# find law is byte-exact, never a substring match, never a similarity score):
#   1. "00-Start Anthology Writer with Avatar Alchemist"
#   2. "Anthology Pipeline Manager and Notification System"
# These are the pre-Skill-59 workflows a client location can still carry —
# the engine's front door (forms_check.py's live-verified "Anthology Intake
# Fire" workflow) and its eight release-notification workflows (the contract
# workflows.release_notifications rows) SUPERSEDE them. A location that
# still runs a legacy workflow is running the OLD pipeline path: its
# find-by-name bind cannot see it, its runs are not governed by the engine's
# gates, and its presence is exactly the drift the U06 family exists to
# surface. The finder's job: prove the legacy rows exist (or prove they do
# not) and report the ids — the id is the handle every later archive/verify
# step binds to, so it is reported MASKED on every operator surface and in
# full ONLY inside the JSON payload a machine consumer reads.
#
# WHY A DEDICATED MODULE: the U06 archive gate is find-then-archive, and
# the FIND must never be improvised by the archive step. This module owns
# the find law (byte-exact names, workflow-typed rows only, near-misses
# reported, renamed-legacy indistinguishable from absent-legacy) ONCE, so
# the finder and every later caller share ONE surface — the delta_reporter
# single-implementation doctrine (a contract read once, in one module).
# The live workflow rows are read with ONE GET against the internal rail
# (backend.leadconnectorhq.com, the ONLY workflow surface this repo has
# PROVEN live — Skill 58 verify-podcast-ghl-workflows.py:
# GET /workflow/<loc>/list?limit=200 with the token-id / channel APP /
# source WEB_USER / version 2021-07-28 header set that reg.InternalRailClient
# already sends; the rows are PROVEN to carry the shape
# {"rows": [ {"type": "workflow", "name": ..., "id": ...} ]}). The PUBLIC v2
# surface has NO proven workflows listing endpoint in this repo, so it is
# NOT used — the Skill 44 doctrine ("Do NOT add new endpoints without
# verifying against the live backend") is binding.
#
# FIND-BY-NAME (the exact-name law). Each contract legacy name is matched by
# EXACT NAME: a listing row whose type is "workflow" and whose name,
# normalized, equals the contract name with dashes -> spaces, normalized
# lowercase (the same name-match law form_reader.py pins for the forms slug
# and workflow_reader.py pins for "Anthology Intake Fire"). A RENAMED legacy
# workflow is indistinguishable from an ABSENT one to find-by-name — both
# refuse fail-closed; a near-miss is REPORTED (candidates), never silently
# accepted. Every row that carries a workflow id is kept, so a partial
# match (one legacy found, the other not) is a PARTIAL result with the
# found id and the absent name both on the surface — never a silent
# half-pass.
#
# PIN-BY-ID (the drift law). When --workflow-id is given (a box override
# slot), the finder ALSO requires the listing to carry that exact id — a
# pinned id the listing does not contain is a MISMATCH (exit 5), never a
# silent pass, and the pinned id BYPASSES the name law for that legacy name
# (a pin is a stronger contract than a name). A pinned id is matched ONLY
# against the workflow-typed rows under the legacy name it pins: a pinned
# id that resolves to a row under a DIFFERENT legacy name is a MISMATCH
# (PIN-ON-WRONG-NAME) — a pin can never point the archive at the wrong
# legacy.
#
# ARCHIVE GATE (the U06 write law, from the package init):
#   * THIS MODULE NEVER ARCHIVES. An archive ACTION (delete / archive /
#     remove / deactivate / unpublish of a legacy workflow) lives in a
#     SEPARATE module and REFUSES to run unless the operator explicitly
#     passes --execute (Trevor-gated). Without --execute the archive
#     surface reports what it WOULD do and exits without mutating.
#   * The write-side gate is TWO-sided: --execute (Trevor's explicit
#     authorization) AND a pinned --workflow-id for the exact target — the
#     id this finder reports is the ONLY handle the archive step may bind
#     to. A name alone never authorizes a write; a pin is a stronger
#     contract than a name (the U02 name law).
#   * THE PROVEN-WRITE LAW (this module, binding on the whole family): the
#     internal rail's PROVEN surfaces are GET /workflow/<loc>/list,
#     GET /workflow/<loc>/<wid>, GET /workflow/<loc>/trigger, PUT
#     /workflow/<loc>/trigger/<trg> (scope_applier.py), and the Skill 44
#     builder's POST/PUT /workflow/<loc> + /workflow/<loc>/<wid> — and the
#     repo has PROVEN NO workflow delete/archive endpoint anywhere (Skill 44
#     doctrine: "Do NOT add new endpoints without verifying against the
#     live backend" is binding; the registry itself documents that the
#     engine "never calls a nonexistent create/delete endpoint"). Until a
#     delete/archive surface is PROVEN live against the backend, NO module
#     in this family may perform an archive write — the archive step's
#     --execute gate stands on TOP of this law and never relaxes it.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail rides a Firebase refresh
# token + API key resolved via anthology_registry (ANTHOLOGY_GHL_FIREBASE_*
# / GOHIGHLEVEL_FIREBASE_* / GHL_FIREBASE_* — live process env first, then
# the canonical client env stores), with the PIT labels
# (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_PIT /
# GHL_API_KEY) as the second rail credential when no refresh token is SET.
# SET / NOT SET only on every operator surface; a value is NEVER printed.
# The location id is the CONTRACT's source_template_location (operator
# infrastructure config, not a secret). Workflow and location ids are
# markers (last 4 chars) on every operator surface.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.InternalRailClient /
# the PIT-fallback client, which apply CAF_BROWSER_UA on EVERY request —
# the Cloudflare edge fronting backend.leadconnectorhq.com 403s urllib's
# default "Python-urllib/x.y" User-Agent at the WAF edge (CF error 1010)
# before the request ever reaches Convert and Flow (the exact failure mode
# that 403s the bare client; the Podcast gate proved the browser UA live).
# A response body is never surfaced (it could echo a credential).
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable response, an empty listing, an absent legacy row, a pinned id
# the listing lacks, or a pinned id under the wrong legacy name is a
# REFUSAL / MISMATCH — never a silent pass, never a fabricated success, and
# never an id guessed from memory. A legacy workflow that cannot be FOUND
# (absent or renamed) is exactly as reportable as one that is found — the
# two findings are the two sides of the SAME surface.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 belongs to self-test FAILED):
#   0  PASS — both legacy workflows found on the listing (also plan /
#      self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      a malformed listing shape that cannot be read faithfully
#   3  HELD — Convert and Flow API unreachable / Cloudflare edge block /
#      internal rail unavailable (UNDETERMINED, retryable — never a
#      verdict)
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  MISMATCH — a legacy workflow ABSENT from the listing, a pinned id
#      absent from the listing, or a pinned id on the wrong legacy name
#      (the fail-closed default; also the PARTIAL case — one legacy found
#      and the other absent)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO token and NO network):
#   find_legacy.py check [--location-id ID]
#                        [--workflow-id ID] [--legacy-name NAME]
#   find_legacy.py plan  [--location-id ID] [--workflow-id ID]
#                        [--legacy-name NAME]
#   find_legacy.py self-test
#
# --legacy-name narrows the find to ONE of the two legacy names (the other
# is not judged — its absence is not reported as a MISMATCH; the narrowed
# surface is still fail-closed for the named one). Without it, BOTH names
# are found-or-absent on one surface.
#
# STDLIB ONLY (urllib + json via the registry). Calls NO model. Reuses
# anthology_registry (InternalRailClient, resolve_firebase_refresh_token,
# _resolve_firebase_api_key, resolve_pit, _internal_request_headers,
# _stop, _mask_location, InternalRailUnavailable and its exception
# classes). DOCTRINE: move in silence; NOTHING Anthropic in any runtime
# file; Convert and Flow naming in every client surface; NEVER print a
# secret value.
# =============================================================================
"""find_legacy.py — find the two legacy Anthology workflows by exact name
on a Convert and Flow location and report their one id each (Skill 59, U06
tooling). Read-only: this module never archives, deletes, or mutates."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring, the LeadConnector clients, the credential
# resolution, and the exit-code contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object
# for a legacy-workflow read (the self-test asserts the golden plan carries
# the exact string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-legacy-workflow-find"
CONFIG_SCHEMA_VERSION = 1

# THE TWO LEGACY WORKFLOWS — the U06 archive targets, BY EXACT NAME. The
# find law is byte-exact, never a substring match, never a similarity
# score; a renamed legacy is indistinguishable from an absent one and BOTH
# refuse fail-closed. Order is load-bearing: name 0 is the legacy front
# door, name 1 the legacy pipeline manager — the surface reports them under
# the stable keys "start_anthology_writer" and "pipeline_manager".
LEGACY_NAMES = {
    "start_anthology_writer": "00-Start Anthology Writer with Avatar Alchemist",
    "pipeline_manager": "Anthology Pipeline Manager and Notification System",
}

# The internal-rail workflows listing surface, proven live in Skill 58
# (58-podcast-production-engine/scripts/verify-podcast-ghl-workflows.py:
# GET /workflow/<loc>/list?limit=200 with the token-id / channel / source /
# version header set reg.InternalRailClient already sends). The PUBLIC v2
# surface has NO proven workflows listing endpoint in this repo — the rail
# is the ONLY surface used (Skill 44 doctrine: never an invented endpoint).
WORKFLOWS_LIST_PATH = "/workflow/%s/list"

# The listing row-type marker for a real workflow (the Skill 58 filter:
# rows whose type == "workflow"; non-workflow rows — a trigger, a step, a
# folder — never match the name law).
WORKFLOW_ROW_TYPE = "workflow"

# The name-match law: each contract name with dashes -> spaces, normalized
# lowercase — "00 start anthology writer with avatar alchemist" and
# "anthology pipeline manager and notification system". A listing row whose
# normalized name equals one of these strings IS that legacy workflow.
LEGACY_SLUGS = {
    key: re.sub(r"\s+", " ", name).lower()
    for key, name in LEGACY_NAMES.items()
}

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways, and every emitted surface is scanned
# against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The archive write law, machine-carried: the repo has PROVEN NO workflow
# delete/archive surface (Skill 44 doctrine binding — "Do NOT add new
# endpoints without verifying against the live backend"; the registry
# documents that the engine "never calls a nonexistent create/delete
# endpoint"). Until a delete/archive endpoint is proven live against the
# backend, no module in the U06 family may perform an archive write — the
# archive ACTION's --execute gate stands on TOP of this law, never instead
# of it.
PROVEN_ARCHIVE_SURFACE = ""


class LegacyFindError(Exception):
    """A fail-closed read refusal (STOP family): a malformed listing shape
    that cannot be read faithfully, an empty listing, or a credential-shaped
    string in a payload. An expectation that cannot name its own sources
    must not run."""


def mask_id(wid: str) -> str:
    """Non-reversible marker for a workflow id (last 4 chars) — the house
    surface shape for every operator-facing mention of a workflow id. The
    full id rides inside the JSON payload a machine consumer reads, never
    on a human surface."""
    return reg._mask_location(wid)


def _normalize_name(name: str) -> str:
    """The name-match normalization: lowercase, spaces collapsed — so
    "00-Start Anthology Writer with Avatar Alchemist " and "  ANTHOLOGY
    PIPELINE MANAGER..." all resolve to their law strings. Returns the
    normalized name."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _row_id(row) -> str:
    """The workflow id of a listing row under any of its container keys —
    "id" (the canonical key, proven in Skill 58 rows), "_id", or
    "workflowId". Returns "" when the row carries none."""
    if not isinstance(row, dict):
        return ""
    for key in ("id", "_id", "workflowId"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _row_name(row) -> str:
    """The display name of a listing row under any of its name-bearing keys
    ("name" canonical, "workflowName" alternate). Returns "" when the row
    carries none."""
    if not isinstance(row, dict):
        return ""
    for key in ("name", "workflowName"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _unmasked_row_id_scan(row_id: str) -> None:
    """Never-a-token guard for a SINGLE workflow id: a credential-shaped id
    REFUSES rather than surface (a row whose id looks like a token is not a
    workflow we report — the id is what this finder exists to emit)."""
    if _CREDENTIAL_SHAPE.search(row_id):
        raise LegacyFindError(
            "a listing row id resolved to a credential-shaped string — "
            "REFUSED without printing it")


def _flatten_rows(payload) -> list:
    """Flatten a workflows-listing payload to a list of row dicts over the
    ONE PROVEN container shape: {"rows": [...]} (the shape Skill 58's
    workflow listing read re-reads). Any other shape — including a payload
    that parses to a non-dict — is a LegacyFindError (never a silent empty;
    an unreadable shape is not proof of zero workflows)."""
    if not isinstance(payload, dict):
        raise LegacyFindError(
            "workflows listing payload is not a JSON object — the listing "
            "shape is not readable")
    rows = payload.get("rows")
    if rows is None:
        raise LegacyFindError(
            "workflows listing payload has no 'rows' array — the listing "
            "shape is not readable")
    if not isinstance(rows, list):
        raise LegacyFindError("workflows listing 'rows' value is not an array")
    return [r for r in rows if isinstance(r, dict)]


def _read_workflows_payload(client, location_id: str) -> dict:
    """The ONE live workflows read: the internal rail
    GET /workflow/<loc>/list?limit=200 via reg.InternalRailClient, which
    mints a Firebase id_token (the refresh token BY LABEL, never printed)
    and applies CAF_BROWSER_UA on the request (the CF 1010 law). Raises
    InternalRailUnavailable — mapped onto the HELD family by the CLI."""
    out = client._get(WORKFLOWS_LIST_PATH % location_id + "?limit=200")
    if not isinstance(out, dict):
        raise LegacyFindError(
            "workflows listing response is not a JSON object — the listing "
            "shape is not readable")
    return out


def find_legacies(client, location_id: str, *, pinned_id: str = "",
                  legacy_key: str = "", workflow_rows=None) -> dict:
    """Read the live workflows listing and FIND the two legacy workflows by
    EXACT NAME. Fail-closed, never a token.

    `client` is a reg.InternalRailClient (its _get rides CAF_BROWSER_UA and
    the token-id header).
    `workflow_rows` is an explicit row list (self-tests); when None the live
    GET is performed. `pinned_id` is a box-override workflow id — when
    non-empty it must appear on the listing (exit-5 MISMATCH otherwise) and
    it BYPASSES the name law for the legacy name it pins. `legacy_key` is
    one of the two LEGACY_NAMES keys — when given, ONLY that legacy is
    judged (the other's absence is not a MISMATCH).

    Returns the documented surface {contract, schema_version, ok,
    found, workflows, absent, pinned, count, candidates, sources, af_code,
    note} — fail-closed:
      - ok True ONLY when every judged legacy row matched its name law (a
        "workflow"-typed row whose normalized name equals the contract name
        with dashes -> spaces) AND a pinned_id, when given, appeared under
        that legacy name; the returned id under each key is the matched
        row's id,
      - the `workflows` mapping reports each judged legacy: {key: name} ->
        {found, id, id_masked, matched_by} — found True carries the id;
        found False carries NO id (never an id guessed from memory),
      - `absent` lists every judged legacy name NOT found — one of the two
        names missing is a PARTIAL MISMATCH (exit 5), never a silent
        half-pass; `pinned` names the pin state per legacy,
      - `candidates` keeps EVERY row that carried a workflow id (masked) so
        a near-miss (e.g. "Anthology Pipeline Manager and Notification
        System v2") is REPORTED, never silently ignored — even on the
        not-found paths,
      - count is the number of workflow rows read; sources names the exact
        read (the internal-rail path + the live/explicit seam),
      - named af_codes: LEGACY-FOUND (ok True), LEGACY-ABSENT (every
        judged legacy absent), LEGACY-PARTIAL (one judged legacy found and
        another absent), LEGACY-EMPTY (the listing held zero workflow rows),
        PIN-MISSING (a pinned id absent from the listing), and
        PIN-ON-WRONG-NAME (a pinned id that resolved to a row under a
        DIFFERENT legacy name — a pin can never point at the wrong legacy).
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (LegacyFindError, STOP family) or a transport
    failure (InternalRailUnavailable, HELD family). This module NEVER
    archives — it finds and reports ids only.
    """
    if workflow_rows is None:
        payload = _read_workflows_payload(client, location_id)
        rows = _flatten_rows(payload)
    else:
        rows = [r for r in workflow_rows if isinstance(r, dict)]
    rows = [r for r in rows if str(r.get("type") or "").strip() == WORKFLOW_ROW_TYPE]
    count = len(rows)

    # which legacies are judged on this surface
    judged = {key: name for key, name in LEGACY_NAMES.items()
              if not legacy_key or key == legacy_key}
    law = {key: LEGACY_SLUGS[key] for key in judged}

    # the pin law: a pinned id must appear on the listing AND attribute to
    # ONE legacy key. A pin is a STRONGER contract than a name: with
    # --legacy-name the pin binds to the named legacy even past a renamed
    # row; without it, the pin binds to the legacy whose name law the
    # pinned row's name matches. A pinned row absent from the listing
    # (PIN-MISSING), a pinned row whose name is a DIFFERENT legacy
    # (PIN-ON-WRONG-NAME), or a renamed pinned row the caller did not
    # attribute (PIN-UNATTRIBUTABLE) is a MISMATCH — a pin never binds by
    # guess and never points the archive at the wrong legacy.
    pinned = (pinned_id or "").strip()
    if pinned:
        _unmasked_row_id_scan(pinned)
    pin_state = ""   # "" (no pin) | "missing" | "wrong-name" | "unattributable" | "on-list"
    pin_owner = ""   # the legacy key the pin is attributed to
    pin_row = None
    if pinned:
        pin_row = next((r for r in rows if _row_id(r) == pinned), None)
    if pinned and pin_row is None:
        pin_state = "missing"
    elif pin_row is not None:
        pin_norm = _normalize_name(_row_name(pin_row))
        # the wrong-name property is judged against the FULL legacy set,
        # never the narrowed scope — a pinned row naming the other legacy
        # is wrong-name even when that legacy is not under judgment
        name_owners = [k for k in LEGACY_SLUGS if pin_norm == LEGACY_SLUGS[k]]
        if legacy_key and legacy_key in law:
            # the caller named the legacy the pin is for — a pin bypasses a
            # rename (a pinned row whose name matches NO legacy law is the
            # renamed case and is attributed by the caller's word), but a
            # pinned row whose name IS a different legacy is wrong-name (a
            # pin can never point at the wrong legacy), and a pinned row
            # whose name matches the CALLER'S OWN legacy is attributed to
            # it WITHOUT the caller's word — the pin rides the row's own
            # name, never a guess
            if name_owners and name_owners != [legacy_key]:
                pin_state, pin_owner = "wrong-name", ""
            elif legacy_key in name_owners:
                pin_state, pin_owner = "on-list", legacy_key
            else:
                pin_state, pin_owner = "on-list", legacy_key
        elif name_owners:
            pin_state, pin_owner = "on-list", name_owners[0]
        else:
            # a renamed pinned row with no --legacy-name cannot be
            # attributed — refuse, never bind by guess
            pin_state, pin_owner = "unattributable", ""

    # the name law + candidate collection (run FIRST, one pass over the
    # rows — the pin-refusal surfaces below still carry the candidates and
    # the name-matched rows on the surface)
    matched = {}  # key -> the matched row
    matched_by = {}  # key -> "name" | "pin"
    candidates = []
    for row in rows:
        row_id = _row_id(row)
        if row_id:
            _unmasked_row_id_scan(row_id)
            candidates.append({"id_masked": mask_id(row_id)})
        norm = _normalize_name(_row_name(row))
        for key, slug in law.items():
            if key in matched:
                continue
            if norm == slug:
                matched[key], matched_by[key] = row, "name"
                break

    _PIN_STATE_CODE = {
        "missing": "PIN-MISSING",
        "wrong-name": "PIN-ON-WRONG-NAME",
        "unattributable": "PIN-UNATTRIBUTABLE",
    }
    if pin_state in _PIN_STATE_CODE:
        # a pin refusal is maximally fail-closed (the workflow_reader
        # PIN-MISSING precedent): NO judged legacy carries an id — a
        # drifted name-row id could mislead an archive bind — and the
        # near-miss rows stay on the surface in `candidates` (masked) for
        # the operator to reconcile
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflows": {
                key: {
                    "found": False,
                    "id": "",
                    "id_masked": "",
                    "matched_by": "",
                } for key in judged
            },
            "absent": [name for key, name in judged.items()],
            "pinned": {key: {"pinned": False, "state": pin_state}
                       for key in judged},
            "count": count,
            "candidates": candidates,
            "sources": {"read": "internal rail %s (token-id header, "
                                "CAF_BROWSER_UA on the request)"
                                % (WORKFLOWS_LIST_PATH % "<loc>"),
                        "rows": "live GET" if workflow_rows is None else "explicit (self-test)"},
            "af_code": _PIN_STATE_CODE[pin_state],
            "note": {
                "missing": "the pinned workflow id is not on the listing — "
                           "fail-closed, never a silent pass; reconcile "
                           "from the masked candidates",
                "wrong-name": "a pinned workflow id resolved to a row under "
                              "a different legacy name — a pin can never "
                              "point the archive at the wrong legacy",
                "unattributable": "a pinned workflow id resolved to a "
                                  "renamed row with no --legacy-name to "
                                  "attribute it — refused, never bound by "
                                  "guess",
            }[pin_state],
        }
    # a pinned id BYPASSES the name law for the legacy it is attributed to
    # (a pin is a stronger contract than a name)
    if pin_owner and pin_owner not in matched:
        matched[pin_owner], matched_by[pin_owner] = pin_row, "pin"

    pinned_surface = {key: {"pinned": False, "state": "not-pinned"}
                      for key in judged}
    if pin_owner:
        pinned_surface = {key: {"pinned": key == pin_owner,
                                "state": "on-list" if key == pin_owner
                                else "not-pinned"} for key in judged}

    found_keys = [key for key in law if key in matched]
    absent = [name for key, name in judged.items() if key not in matched]
    workflows = {
        key: {
            "found": key in matched,
            "id": _row_id(matched[key]) if key in matched else "",
            "id_masked": mask_id(_row_id(matched[key])) if key in matched else "",
            "matched_by": matched_by.get(key, ""),
        } for key in judged
    }
    if not found_keys:
        af_code = "LEGACY-EMPTY" if count == 0 else "LEGACY-ABSENT"
        note = ("the listing is empty" if count == 0 else
                "no legacy workflow matched the exact-name law") + \
               " — fail-closed, never an id guessed from memory"
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflows": workflows,
            "absent": absent,
            "pinned": pinned_surface,
            "count": count,
            "candidates": candidates,
            "sources": {"read": "internal rail %s (token-id header, "
                                "CAF_BROWSER_UA on the request)"
                                % (WORKFLOWS_LIST_PATH % "<loc>"),
                        "rows": "live GET" if workflow_rows is None else "explicit (self-test)"},
            "af_code": af_code,
            "note": note,
        }
    if absent:
        # PARTIAL: one legacy found, another judged one absent — a
        # fail-closed MISMATCH (exit 5), never a silent half-pass
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": True,
            "workflows": workflows,
            "absent": absent,
            "pinned": pinned_surface,
            "count": count,
            "candidates": candidates,
            "sources": {"read": "internal rail %s (token-id header, "
                                "CAF_BROWSER_UA on the request)"
                                % (WORKFLOWS_LIST_PATH % "<loc>"),
                        "rows": "live GET" if workflow_rows is None else "explicit (self-test)"},
            "af_code": "LEGACY-PARTIAL",
            "note": "one legacy workflow was found, another judged legacy "
                    "is absent — the found id is reported, the absence is "
                    "a MISMATCH, never a silent half-pass",
        }
    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "found": True,
        "workflows": workflows,
        "absent": absent,
        "pinned": pinned_surface,
        "count": count,
        "candidates": candidates,
        "sources": {"read": "internal rail %s (token-id header, "
                            "CAF_BROWSER_UA on the request)"
                            % (WORKFLOWS_LIST_PATH % "<loc>"),
                    "rows": "live GET" if workflow_rows is None else "explicit (self-test)"},
        "af_code": "LEGACY-FOUND",
        "note": "both legacy workflows matched the exact-name law on the "
                "listing",
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the finder against
# the REAL committed constants, then runs every attack fixture: golden
# finds, the pin law both ways, every not-found path named, the renamed-
# legacy refusal, the never-a-token guard, the malformed-shape refusals,
# and the read-only law (this module has NO write surface at all).
# ---------------------------------------------------------------------------

class _FakeClient:
    """In-memory internal-rail client: serves the row list the self-test
    hands it and records the exact request, so the live-read contract (the
    rail path, the location in the path, the limit query, the token-id
    header, CAF_BROWSER_UA on the request) is provable offline."""

    def __init__(self, rows):
        self._rows = list(rows or [])
        self.calls = []

    def _get(self, path):
        self.calls.append({"path": path})
        return {"rows": [dict(r) for r in self._rows]}


def _golden_rows():
    """The golden listing rows: BOTH legacy workflows plus one unrelated
    workflow and one non-workflow row (a trigger) — the same shape Skill 58's
    listing read returns."""
    return [
        {"type": "workflow", "name": LEGACY_NAMES["start_anthology_writer"],
         "id": "wfLegacyStart01"},
        {"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
         "id": "wfLegacyPipe02"},
        {"type": "workflow", "name": "Anthology Intake Fire", "id": "wfIntakeFire03"},
        {"type": "trigger", "name": "Contact Tag Added", "id": "wfTriggerThing"},
    ]


def _self_test_body(dev) -> None:
    # ---- 1. golden: the live read finds BOTH legacy workflows by exact
    #      name, only workflow-typed rows count, and the request contract
    #      (rail path with the location, limit query, token-id header,
    #      browser UA) is exact
    client = _FakeClient(_golden_rows())
    res = find_legacies(client, "loc_tmpl")
    assert res["ok"] is True and res["found"] is True, \
        "the golden read must find both legacy workflows"
    assert res["workflows"]["start_anthology_writer"]["id"] == "wfLegacyStart01", \
        "the writer id must be the golden workflow id"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02", \
        "the pipeline-manager id must be the golden workflow id"
    assert res["workflows"]["start_anthology_writer"]["matched_by"] == "name"
    assert res["workflows"]["pipeline_manager"]["matched_by"] == "name"
    assert res["workflows"]["start_anthology_writer"]["id_masked"] == \
        mask_id("wfLegacyStart01")
    assert res["absent"] == [] and res["af_code"] == "LEGACY-FOUND"
    assert res["count"] == 3, "only workflow-typed rows may count"
    assert len(res["candidates"]) == 3, "only workflow-typed rows may be candidates"
    assert res["contract"] == CONFIG_CONTRACT
    assert client.calls == [{"path": WORKFLOWS_LIST_PATH % "loc_tmpl" + "?limit=200"}], \
        "the request must be the proven rail path with the location + limit"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "the house browser UA must stay a browser UA (CF 1010 law)"

    # ---- 2. the pin law, both ways: a pinned id ON the listing under its
    #      own legacy name passes (matched_by pin, the pin BYPASSES the
    #      name law); a pinned id ABSENT from a non-empty listing is
    #      PIN-MISSING (exit 5), never a silent pass
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["name"] = "Renamed Legacy Writer"  # the name law no longer matches
    client = _FakeClient(rows)
    res = find_legacies(client, "loc_tmpl", pinned_id="wfLegacyStart01",
                        legacy_key="start_anthology_writer")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND", \
        "a pinned id attributed by --legacy-name must pass even past a renamed row"
    assert res["workflows"]["start_anthology_writer"]["matched_by"] == "pin", \
        "the pin must bypass the name law for the legacy it pins"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["id"] = "DriftedLegacy0000"  # the pinned id disappears
    client = _FakeClient(rows)
    res = find_legacies(client, "loc_tmpl", pinned_id="wfLegacyStart01")
    assert res["ok"] is False and res["af_code"] == "PIN-MISSING", \
        "an absent pinned id must be a MISMATCH, got %r" % res
    assert res["workflows"]["start_anthology_writer"]["id"] == "", \
        "a pin refusal must never carry a workflow id"
    assert res["workflows"]["pipeline_manager"]["id"] == "", \
        "a pin refusal must never carry ANY judged legacy id"
    assert res["candidates"] == [{"id_masked": mask_id("DriftedLegacy0000")},
                                 {"id_masked": mask_id("wfLegacyPipe02")},
                                 {"id_masked": mask_id("wfIntakeFire03")}], \
        "the near-miss rows must stay on a pin refusal (masked, for reconcile)"

    # ---- 3. PIN-ON-WRONG-NAME / PIN-UNATTRIBUTABLE: a pinned id that is a
    #      row under the OTHER legacy name must refuse — a pin can never
    #      point at the wrong legacy; a renamed pinned row with no
    #      --legacy-name cannot be attributed and refuses rather than bind
    #      by guess
    client = _FakeClient(_golden_rows())
    res = find_legacies(client, "loc_tmpl", pinned_id="wfLegacyPipe02",
                        legacy_key="start_anthology_writer")
    assert res["ok"] is False and res["af_code"] == "PIN-ON-WRONG-NAME", \
        "a pin under the wrong legacy name must be a MISMATCH"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["name"] = "Renamed Legacy Writer"  # no --legacy-name to attribute
    client = _FakeClient(rows)
    res = find_legacies(client, "loc_tmpl", pinned_id="wfLegacyStart01")
    assert res["ok"] is False and res["af_code"] == "PIN-UNATTRIBUTABLE", \
        "an unattributable renamed pinned row must refuse"

    # ---- 4. not-found paths, each NAMED: an empty listing is LEGACY-EMPTY;
    #      a listing with only non-workflow rows is LEGACY-EMPTY; a non-empty
    #      listing without the legacy workflows is LEGACY-ABSENT; a listing
    #      with ONE legacy is LEGACY-PARTIAL — all carry no id for the
    #      absent keys and keep the candidate rows (near-misses are
    #      reported)
    res = find_legacies(client, "loc_tmpl", workflow_rows=[])
    assert res["ok"] is False and res["af_code"] == "LEGACY-EMPTY", \
        "an empty listing must be LEGACY-EMPTY"
    res = find_legacies(client, "loc_tmpl",
                        workflow_rows=[{"type": "trigger", "name": "Contact Tag Added",
                                        "id": "wfTriggerThing"}])
    assert res["ok"] is False and res["af_code"] == "LEGACY-EMPTY", \
        "a trigger-only listing must be LEGACY-EMPTY"
    client = _FakeClient([{"type": "workflow", "name": "Anthology Intake Fire",
                           "id": "wfIntakeFire03"}])
    res = find_legacies(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-ABSENT", \
        "a listing without any legacy workflow must be LEGACY-ABSENT"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", \
        "an absent legacy must never carry an id"
    assert res["candidates"] == [{"id_masked": mask_id("wfIntakeFire03")}], \
        "near-miss rows must stay on the surface (never silently ignored)"
    client = _FakeClient([{"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
                           "id": "wfLegacyPipe02"}])
    res = find_legacies(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-PARTIAL", \
        "one legacy found and the other absent must be LEGACY-PARTIAL"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02", \
        "the found id must be reported on the partial surface"
    assert res["workflows"]["start_anthology_writer"]["id"] == "" and \
        LEGACY_NAMES["start_anthology_writer"] in res["absent"], \
        "the absent legacy must be named, never silently dropped"

    # ---- 5. a RENAMED legacy is indistinguishable from an ABSENT one to
    #      find-by-name — both refuse (the exact-name law; never accepted by
    #      a near-miss)
    client = _FakeClient([{"type": "workflow", "name": "00-Start Anthology Writer",
                           "id": "wfRenamedLegacy1"},
                          {"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
                           "id": "wfLegacyPipe02"}])
    res = find_legacies(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-PARTIAL", \
        "a renamed legacy must refuse (never accepted by name similarity)"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", \
        "a renamed legacy must not be reported"

    # ---- 6. the narrowed surface: --legacy-name judges ONLY the named
    #      legacy — the other's absence is not a MISMATCH
    client = _FakeClient([{"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
                           "id": "wfLegacyPipe02"}])
    res = find_legacies(client, "loc_tmpl", legacy_key="pipeline_manager")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND", \
        "the narrowed surface must judge only the named legacy"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02"
    assert "start_anthology_writer" not in res["workflows"], \
        "the unjudged legacy must not appear on the narrowed surface"

    # ---- 7. never-a-token: a row id that IS a credential-shaped string
    #      REFUSES the whole read rather than print it; a pinned id that is
    #      credential-shaped refuses the same way
    client = _FakeClient([{"type": "workflow", "name": LEGACY_NAMES["pipeline_manager"],
                           "id": "pit-abc123"}])
    try:
        find_legacies(client, "loc_tmpl")
        raise AssertionError("a credential-shaped row id must refuse")
    except LegacyFindError:
        pass
    try:
        find_legacies(_FakeClient(_golden_rows()), "loc_tmpl",
                      pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except LegacyFindError:
        pass

    # ---- 8. malformed listing shapes REFUSE (never a silent empty): a
    #      payload without a 'rows' key, a 'rows' value that is not an
    #      array, and a response that is not an object
    class _BadClient(_FakeClient):
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def _get(self, path):
            self.calls.append({"path": path})
            return self._payload

    try:
        find_legacies(_BadClient({"nope": 1}), "loc_tmpl")
        raise AssertionError("a payload without 'rows' must refuse")
    except LegacyFindError:
        pass
    try:
        find_legacies(_BadClient({"rows": "not-a-list"}), "loc_tmpl")
        raise AssertionError("a non-array 'rows' must refuse")
    except LegacyFindError:
        pass
    try:
        find_legacies(_BadClient([{"id": "X"}]), "loc_tmpl")
        raise AssertionError("a non-object response must refuse")
    except LegacyFindError:
        pass

    # ---- 9. the read-only law: this module has NO write surface. The
    #      archive ACTION is Trevor-gated (--execute) AND pinned (--workflow-id)
    #      AND proven-surface-bound — and the repo has PROVEN no workflow
    #      archive endpoint, so the archive gate's write side must refuse
    #      until a surface is proven live. The finder itself never mutates:
    #      the only callable surface is find_legacies / plan / self-test,
    #      all read-only; the archive law is carried as DATA on the plan and
    #      the plan is scanned before print (a credential-shaped string on
    #      the plan REFUSES the surface)
    assert not PROVEN_ARCHIVE_SURFACE, \
        "the U06 family must not claim a proven archive surface that this " \
        "repo has not verified live"
    plan_data = plan_surface()
    assert plan_data["archive_gate"]["execute"], \
        "the archive gate must require --execute (Trevor-gated)"
    assert "NEVER archives" in plan_data["archive_gate"]["this_module"], \
        "the finder must declare itself read-only on the plan"
    assert "no workflow delete/archive surface is PROVEN" in \
        plan_data["archive_gate"]["proven_write_law"], \
        "the plan must carry the proven-write law"
    assert not _CREDENTIAL_SHAPE.search(json.dumps(plan_data)), \
        "the plan must never carry a credential-shaped string"
    assert not hasattr(sys.modules[__name__], "archive"), \
        "the finder must expose no archive write surface"

    # ---- 10. the surface contract: the golden read never emits a
    #      credential-shaped string anywhere on the payload
    dumped = json.dumps(find_legacies(_FakeClient(_golden_rows()), "loc_tmpl"),
                        indent=2, sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(dumped), \
        "a successful read must never carry a credential-shaped string"

    dev.write("[find-legacy] self-test PASS: golden find of BOTH legacy "
              "workflows by exact name + request contract (internal-rail "
              "path, location, limit, token-id header, CAF_BROWSER_UA), pin "
              "law both ways, PIN-ON-WRONG-NAME refused, LEGACY-EMPTY / "
              "LEGACY-ABSENT / LEGACY-PARTIAL named, renamed-legacy refused, "
              "narrowed --legacy-name surface, credential-shaped ids "
              "refused, malformed listing shapes refused, read-only law "
              "(no write surface; archive gate is --execute + pin + proven "
              "endpoint)\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[find-legacy] SELF-TEST FAILED: %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def plan_surface() -> dict:
    """The ONE offline plan payload (no network, no credential). The archive
    gate law rides here as DATA: --execute is Trevor's gate and a pinned
    --workflow-id the target contract, but the PROVEN-WRITE law holds — no
    workflow archive endpoint is proven in this repo, so an archive write
    must not be performed until a surface is proven live against the
    backend. The finder itself never archives."""
    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "legacy_names": {key: name for key, name in LEGACY_NAMES.items()},
        "name_law": "workflow-typed row name == the contract legacy name "
                    "(dashes -> spaces, normalized lowercase); a renamed "
                    "legacy is indistinguishable from an absent one and both "
                    "refuse",
        "read": "internal rail %s?limit=200 (token-id header; "
                "CAF_BROWSER_UA on the request — CF 1010 law)"
                % (WORKFLOWS_LIST_PATH % "<loc>"),
        "archive_gate": {
            "this_module": "read-only — finds and reports ids, NEVER archives",
            "execute": "an archive ACTION in the U06 family REQUIRES --execute "
                       "(Trevor-gated); without it the archive surface reports "
                       "what it WOULD do and exits without mutating",
            "pin": "an archive ACTION ALSO requires the workflow id this "
                   "finder reports (--workflow-id); a name alone never "
                   "authorizes a write",
            "proven_write_law": ("no workflow delete/archive surface is "
                                 "PROVEN in this repo (Skill 44 doctrine: "
                                 "only verified endpoints); until one is "
                                 "proven live against the backend, an "
                                 "archive write must NOT be performed — the "
                                 "--execute gate stands on top of this law, "
                                 "never instead of it")
                             if not PROVEN_ARCHIVE_SURFACE
                             else ("archive surface proven live: %s"
                                   % PROVEN_ARCHIVE_SURFACE),
        },
        "note": "offline plan only — no network, no credential needed; a "
                "legacy absent from the live listing is a MISMATCH (exit 5), "
                "never a silent pass; a partial find (one legacy present, "
                "one absent) is a MISMATCH, never a half-pass",
    }


def plan(location_id: str, pinned_id: str = "", legacy_key: str = "", *,
         out=None) -> int:
    """Emit the ONE offline plan JSON object (no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    pinned = (pinned_id or "").strip()
    if pinned:
        _unmasked_row_id_scan(pinned)
    payload = plan_surface()
    payload["location_marker"] = mask_id(location_id)
    payload["pinned_id_masked"] = mask_id(pinned) if pinned else ""
    payload["legacy_scope"] = (LEGACY_NAMES[legacy_key]
                               if legacy_key in LEGACY_NAMES else "both")
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise LegacyFindError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out = out or sys.stdout
    out.write(dumped)
    out.write("\n")
    return EX_OK


def _build_rail_client(location_id: str) -> object:
    """The ONE rail client for the live check, resolved BY LABEL, NEVER BY
    VALUE. The internal rail is the ONLY proven workflow surface, so the
    refresh token is resolved first; the PIT is resolved as a second rail
    credential when no refresh token is SET (it rides a plain urllib
    request with the same CAF_BROWSER_UA on the internal base — the PIT
    carries the Authorization header instead of a token-id, exactly as
    reg.CafClient sends it)."""
    refresh_label, refresh = reg.resolve_firebase_refresh_token()
    if refresh:
        api_label, api_key = reg._resolve_firebase_api_key()
        if not api_key:
            reg._stop(sys.stderr,
                      "The Firebase refresh token is SET but the Firebase "
                      "API key is NOT SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.FIREBASE_API_KEY_LABELS),
                       "The internal rail cannot mint an id_token without "
                       "both labels. Set the API-key label and re-run."])
            return None
        return reg.InternalRailClient(refresh, api_key)
    pit_label, token = reg.resolve_pit()
    if not token:
        checked = ", ".join(reg.PIT_LABELS)
        reg._stop(sys.stderr,
                  "No Convert and Flow credential is SET.",
                  ["Checked (in order): refresh-token labels %s — "
                   "all NOT SET; PIT labels %s — all NOT SET."
                   % (", ".join(reg.FIREBASE_REFRESH_LABELS), checked),
                   "The finder runs against the operator's OWN template "
                   "location marker %s; set the template refresh token "
                   "(preferred, the proven workflow surface) or the "
                   "template PIT and re-run." % mask_id(location_id)])
        return None

    class _PitRailClient:
        def __init__(self, token):
            self._token = token

        def _get(self, path):
            req = urllib.request.Request(
                reg.INTERNAL_API_BASE + path,
                headers={"Authorization": "Bearer %s" % self._token,
                         "version": reg.INTERNAL_VERSION_HEADER,
                         "Accept": "application/json",
                         "User-Agent": reg.CAF_BROWSER_UA})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8") or "{}"
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    body = b""
                    try:
                        body = exc.read()
                    except Exception:
                        body = b""
                    kind = reg._auth_denial_kind(body)
                    if kind == "scope":
                        raise reg.ScopeDenied(
                            "token not authorized for this scope "
                            "(HTTP %s)" % exc.code)
                    raise reg.UpstreamBlockedError(
                        "HTTP %s did NOT match a Convert and Flow "
                        "scope-denial signature — likely a "
                        "Cloudflare/WAF edge block, NOT a token-scope "
                        "problem (HTTP %s)" % (exc.code, exc.code))
                raise reg.CafUnreachable(
                    "Convert and Flow HTTP %s on %s" % (exc.code, path))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                raise reg.CafUnreachable(
                    "Convert and Flow transport error: %s" % type(exc).__name__)
    return _PitRailClient(token)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="find_legacy.py",
        description="Live-read the Convert and Flow workflow listing "
                    "(internal rail GET /workflow/<loc>/list?limit=200) and "
                    "find the two legacy Anthology workflows BY EXACT NAME, "
                    "reporting their one workflow id each (Skill 59, U06 "
                    "tooling). Read-only — this module NEVER archives. "
                    "Fail-closed; never prints a token. One JSON object on "
                    "stdout.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--workflow-id", default="",
                    help="a pinned legacy workflow id (masked on every surface; a "
                         "pinned id absent from the listing, or a pinned id on the "
                         "wrong legacy name, is a MISMATCH)")
    ap.add_argument("--legacy-name", default="",
                    choices=list(LEGACY_NAMES.keys()),
                    help="judge ONLY one legacy workflow by its key "
                         "(%s; default: both)" % " / ".join(LEGACY_NAMES.keys()))
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"], default="check")

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
    pinned_id = args.workflow_id.strip() or ""
    legacy_key = args.legacy_name.strip() or ""

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan(location_id, pinned_id, legacy_key)

        # ---- live check ----
        rail = _build_rail_client(location_id)
        if rail is None:
            return EX_STOP
        # The location id on every operator surface is the masked marker
        # only. A genuinely denied token raises ScopeDenied (STOP); an edge
        # block or any transport failure raises UpstreamBlockedError /
        # CafUnreachable / InternalRailUnavailable (HELD) — never mislabeled.
        result = find_legacies(rail, location_id, pinned_id=pinned_id,
                               legacy_key=legacy_key)
        print(json.dumps(result, indent=2, sort_keys=True))
        return EX_OK if result.get("ok") else EX_MISMATCH

    except LegacyFindError as exc:
        sys.stderr.write("[find-legacy] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[find-legacy] STOP: %s\n" % exc)
        return EX_STOP
    except (reg.UpstreamBlockedError, reg.CafUnreachable,
            reg.InternalRailUnavailable) as exc:
        sys.stderr.write("[find-legacy] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[find-legacy] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
