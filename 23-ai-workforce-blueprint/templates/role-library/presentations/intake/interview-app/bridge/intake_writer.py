#!/usr/bin/env python3
"""Assemble the dept-format intake JSON from the app's answers.

The Presentation Interview app produces an intake record in the shape
build_deck.py's _chk_intake / _chk_mode and the canonical entry gates expect:

    working/copy/intake.json   (the deck brief: deck_brief.* fields, the six
                                mandatory pre_presentation_capture fields, the
                                derived legacy axis fields, the upsell flags)
    working/interview/intake_ledger.json  (the completed, turn-gated interview
                                record that GATE 0 / _intake_provenance_gate
                                require)

This module performs that assembly on the BOX, so the app's submission is
replayed through the same governed record the chat driver would have produced.
It is the WRITER half of the submit-trigger: intake_bridge.py (below) polls the
Worker, this writer stamps the run dir, then cc_board.ingest_deck_task opens the
kanban card — the presentation department start. No shortcuts: the deck can only
build through presentation-canonical-entry.sh's gates.

FIX 11 (hosted run mode): the app's client can declare ultra|standard|economy
and this writer persists it to the intake ledger under the RUN_MODE key, in
deck-intake-driver._record_run_mode's exact record shape, so
presentation-intake-poll.sh reads it with no poller change. Absence writes
nothing and the launcher default (standard) applies -- never ultra by default.
The interview-depth vocabulary (quick/in-depth) is REFUSED here naming both
axes: run mode is FIX 11 build policy, interview depth is FIX 30/36 intake
length, and the two never share a slot. See _RUN_MODE_SUBFIELD below.

FAIL-CLOSED on deck type (PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3): this
module used to hardcode deck_type="webinar" (+ creation_mode/presentation_mode/
audience_mode) unconditionally, so a client who asked for a signature talk
silently got a webinar with "complete": true written on top of it -- a
fabricated answer made to look like an approved one. It no longer guesses.
deck_type is derived ONLY from a real `presentation_type` answer (see
_grounded_deck_type_fields()); when that answer is missing or unrecognized,
write_intake_file()/write_ledger() raise UngroundedDeckTypeError and write
NOTHING rather than mark an intake complete on a fabricated field. Full
routing through deck-intake-driver.py's presentation_type picker + turn
ledger + prove_sp_routing.py is the correct long-term fix and is deliberately
NOT implemented here -- see UngroundedDeckTypeError.__doc__.

Stdlib only. Run:
  python3 intake_writer.py --intake intake.json --run-dir /path/to/run
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

# The six mandatory pre_presentation_capture fields build_deck.py's
# _intake_provenance_gate requires (mirrored here for the non-driver path).
MANDATORY_PRE_CAPTURE = (
    "REPRESENTATION_MIX",
    "AUDIENCE_COMPOSITION_NOTE",
    "GROUNDED_CONTENT",
    "VISUAL_MIX",
    "DARK_OK",
    "HOOK_SEED",
)

# presentation_type -> {deck_type, creation_mode, presentation_mode,
# audience_mode}. Mirrors deck-intake-driver.py:LEGACY_FIELD_MAPPING /
# intake/deck-intake-questions.json's legacy_field_mapping -- THE SOURCE OF
# TRUTH for deck_type (same mirroring pattern as MANDATORY_PRE_CAPTURE above;
# this module runs standalone, stdlib only, so it cannot import the driver).
# presentation_type is the ONE client answer that legitimately determines
# these fields. Deliberately omits the driver table's "requires"/signature_
# source handling (recipient_name, extracted_substance, signature_source
# overrides) -- that is real intake-flow logic belonging to the driver
# integration named in UngroundedDeckTypeError.__doc__, not this patch.
LEGACY_FIELD_MAPPING = {
    "from_scratch": {
        "deck_type": "webinar",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
    },
    "content_personal": {
        "deck_type": "webinar",
        "creation_mode": "content_personal",
        "presentation_mode": "one-person",
        "audience_mode": "PERSONAL",
    },
    "content_general": {
        "deck_type": "webinar",
        "creation_mode": "content_general",
        "presentation_mode": "general",
        "audience_mode": "GENERAL",
    },
    "signature": {
        "deck_type": "signature_presentation",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
    },
}


class UngroundedDeckTypeError(RuntimeError):
    """Raised when deck_type/creation_mode/presentation_mode/audience_mode
    cannot be derived from an answer the client actually gave.

    FAIL CLOSED (PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3): this is the
    replacement for the hardcoded deck_type="webinar" bug. When
    presentation_type was not actually answered -- note the interview app's
    current 12-question set (interview-app/pages/index.html QUESTIONS) never
    asks it, so today this ALWAYS raises for every real app submission --
    callers must not write any file claiming the intake is complete. A
    caller-supplied deck_type/presentation_type claim (e.g. the app
    frontend's own buildIntakePayload(), which separately hardcodes
    presentation_type: "from_scratch" in JS) is never trusted either; only
    the client's own answers are. Full routing through
    deck-intake-driver.py's presentation_type picker, its turn-gated ledger,
    and prove_sp_routing.py (--signature --sig-record) is the correct
    long-term fix and is deliberately NOT implemented here -- that is a real
    design task (turn-ledger shape reconciliation between the two sanctioned
    driver copies, a non-signature batch-record path that does not exist
    today) out of scope for this fail-closed patch. See
    PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3.
    """


def _grounded_deck_type_fields(answers: dict) -> dict:
    """Derive {deck_type, creation_mode, presentation_mode, audience_mode,
    presentation_type} from the client's OWN presentation_type answer.

    Never defaults, never fabricates -- raises UngroundedDeckTypeError naming
    exactly what is missing/invalid when presentation_type was not answered
    or was answered with something unrecognized. This is the ONE function
    permitted to set these four fields; nothing else in this module may
    hardcode them.
    """
    raw = answers.get("presentation_type")
    if isinstance(raw, dict):
        raw = raw.get("value", "")
    raw = str(raw or "").strip()
    if not raw:
        raise UngroundedDeckTypeError(
            "no 'presentation_type' answer was captured in this intake -- "
            "cannot determine deck_type/creation_mode/presentation_mode/"
            "audience_mode. Refusing to default to webinar (or any other "
            "type). See UngroundedDeckTypeError.__doc__ for why and what to "
            "do instead."
        )
    if raw not in LEGACY_FIELD_MAPPING:
        raise UngroundedDeckTypeError(
            f"presentation_type answer {raw!r} is not one of "
            f"{sorted(LEGACY_FIELD_MAPPING)} -- refusing to guess a deck_type."
        )
    derived = dict(LEGACY_FIELD_MAPPING[raw])
    derived["presentation_type"] = raw
    return derived


def _require_grounded_deck_type(intake: dict) -> dict:
    """Validate -- and correct -- intake's deck-type axis against its OWN
    `answers`, in place.

    Called by both write_intake_file() and write_ledger() so the gate holds
    no matter which caller built `intake`: assemble_intake() below is NOT the
    only path into this module. intake_bridge.py's cmd_ingest() -- the real
    submit-trigger the app actually uses in production -- builds `intake`
    straight from the Worker payload and calls write_intake_file()/
    write_ledger() directly, never through assemble_intake(). Overwrites the
    four derived fields with the grounded values (never trusts whatever a
    caller pre-stamped there) so a stale or fabricated claim can never
    survive into a written file. Raises UngroundedDeckTypeError -- nothing is
    written -- if it cannot be grounded.
    """
    grounded = _grounded_deck_type_fields(intake.get("answers") or {})
    intake.update(grounded)
    return intake


# Question id -> intake.json field key (deck_brief section unless noted).
# Mirrors the canonical deck-intake-questions.json storeTarget mapping so the
# flat-answers fallback path produces the same keys the frontend-shaped path
# produces. Keys absent here are passed through uppercase.
ID_TO_FIELD = {
    "offer_name": "OFFER_NAME",
    "transformation_promise": "TRANSFORMATION_PROMISE",
    "audience": "AUDIENCE",
    "cta_action": "CTA_ACTION",
    "brand_primary": "BRAND_PRIMARY",
    "tone": "TONE",
    "final_price": "FINAL_PRICE",
    "price_mode": "PRICE_MODE",
    "goal": "GOAL",
    "target_feeling": "TARGET_FEELING",
    "hook_seed": "HOOK_SEED",
    "client_notes": "CLIENT_NOTES",
    "deadline": "DEADLINE",
    "slide_count": "SLIDE_COUNT",
    "delivery_destinations": "DELIVERY_DESTINATIONS",
    "primary_objection": "PRIMARY_OBJECTION",
    "proof_assets": "PROOF_ASSETS",
    "style_prefs": "STYLE_PREFS",
    # upsell yes-no (the new sales/checkout + VSL questions)
    "want_sales_checkout": "WANT_SALES_CHECKOUT",
    "want_vsl_page": "WANT_VSL_PAGE",
    # speech speed lives flat on the intake record (not deck_brief)
    "speech_speed_preference": "speech_speed_preference",
    # FIX 11 (hosted path): the client's run-mode declaration. Mapped
    # explicitly rather than left to field_for()'s qid.upper() fallback so the
    # key is stated once, next to the PRE_CAPTURE_FIELDS entry that keeps it
    # OUT of deck_brief. See _RUN_MODE_* below.
    "run_mode": "RUN_MODE",
}

# Fields that land under pre_presentation_capture rather than deck_brief.
# RUN_MODE is here for a different reason than the upsell flags: it is an
# EXECUTION axis, not deck content, and deck-intake-questions.json's run_mode
# subfield says so in as many words ("Deliberately NOT in storeTarget -- a run
# mode is an execution axis, not deck content, so it stays out of
# working/copy/intake.json's deck_brief"). pre_presentation_capture.RUN_MODE is
# a location presentation-intake-poll.sh's read_run_mode() already reads
# (candidate 2), so this routing costs the poller no change.
PRE_CAPTURE_FIELDS = {"WANT_SALES_CHECKOUT", "WANT_VSL_PAGE", "RUN_MODE"}


# ===========================================================================
# PRES-006 — THE CANONICAL FIELD-PATH CONTRACT (box-side mirror)
# ===========================================================================
# schema/intake_fields.js is the SOURCE OF TRUTH for where every intake answer
# lives; tools/gen_ui_questions.mjs regenerates the UI and
# schema/intake_fields.json (the JSON projection) from it in one pass, and
# test_pres006_canonical_paths.py fails if THIS mirror stops matching that
# projection. The pre-contract defect: the hosted form stored the upsell flags
# under pre_presentation_capture.* (the storeTarget home every engine consumer
# — defers.py, resolve_intake.py, sales_checkout_builder.py, vsl_builder.py —
# reads) while both Workers' hand-copied REQUIRED_BRIEF_FIELDS arrays required
# them inside deck_brief, so every complete form payload was rejected 422 by
# its own backend. The canonical location is pre_presentation_capture.*
# (engine-consumer need), declared ONCE here and pinned to the contract.
INTAKE_CONTRACT_VERSION = 2
_CONTRACT_PROJECTION_RELPATH = (
    "schema/intake_fields.json")

#: canonical_path -> the field's own id (the answers{} key the app records).
CANONICAL_FIELD_PATHS = {
    "presentation_type": "pre_presentation_capture.PRESENTATION_TYPE",
    "offer_name": "deck_brief.OFFER_NAME",
    "named_methodology": "deck_brief.NAMED_METHODOLOGY",
    "transformation_promise": "deck_brief.TRANSFORMATION_PROMISE",
    "time_to_result": "deck_brief.TIME_TO_RESULT",
    "audience": "deck_brief.AUDIENCE",
    "cta_action": "deck_brief.CTA_ACTION",
    "brand_primary": "deck_brief.BRAND_PRIMARY",
    "image_links": "deck_brief.IMAGE_LINKS",
    "tone": "deck_brief.TONE",
    "final_price": "deck_brief.FINAL_PRICE",
    "speech_speed_preference": "intake.json.speech_speed_preference",
    "want_sales_checkout": "pre_presentation_capture.WANT_SALES_CHECKOUT",
    "sales_checkout_declined_reason":
        "pre_presentation_capture.SALES_CHECKOUT_DECLINED_REASON",
    "want_vsl_page": "pre_presentation_capture.WANT_VSL_PAGE",
    "vsl_page_declined_reason":
        "pre_presentation_capture.VSL_PAGE_DECLINED_REASON",
    "run_mode": "pre_presentation_capture.RUN_MODE",
    "client_notes": "deck_brief.CLIENT_NOTES",
}

#: The canonical REQUIRED set. A "no"/"false" value is a REAL answer (a client
#: decline the engine gates on) and never counts as missing — only
#: absent/None/blank does. This mirrors schema/intake_fields.js's
#: required_fields; the mirror is pinned by test_pres006_canonical_paths.py.
REQUIRED_CANONICAL_FIELDS = (
    "deck_brief.OFFER_NAME",
    "deck_brief.NAMED_METHODOLOGY",
    "deck_brief.TRANSFORMATION_PROMISE",
    "deck_brief.TIME_TO_RESULT",
    "deck_brief.AUDIENCE",
    "deck_brief.CTA_ACTION",
    "deck_brief.TONE",
    "deck_brief.FINAL_PRICE",
    "pre_presentation_capture.PRESENTATION_TYPE",
    "pre_presentation_capture.WANT_SALES_CHECKOUT",
    "pre_presentation_capture.WANT_VSL_PAGE",
)

#: Version-aware legacy migration: version-1 records stored the upsell flags
#: (and RUN_MODE) in inconsistent locations. Each canonical field's aliases,
#: in the order the JS contract declares them. A legacy alias is moved to the
#: canonical path when the canonical path is empty; a legacy value that
#: CONTRADICTS a present canonical value refuses the migration (never
#: arbitrarily chosen). Pinned to schema/intake_fields.js's legacy_aliases.
LEGACY_ALIASES = {
    "want_sales_checkout": ("deck_brief.WANT_SALES_CHECKOUT", "WANT_SALES_CHECKOUT"),
    "want_vsl_page": ("deck_brief.WANT_VSL_PAGE", "WANT_VSL_PAGE"),
    "run_mode": ("deck_brief.RUN_MODE", "RUN_MODE", "run_mode"),
    "presentation_type": ("deck_brief.PRESENTATION_TYPE", "PRESENTATION_TYPE"),
}

#: booleanish strings legacy records used, normalized during migration.
_LEGACY_BOOLEAN_NORMALIZATION = {"true": "yes", "false": "no"}


class ContractMigrationError(RuntimeError):
    """Raised when a legacy intake record carries CONTRADICTORY values for one
    canonical field — the same answer recorded in two places with different
    values. FAIL CLOSED, the module's standing discipline: the record is not
    migrated, nothing is written, and the error names BOTH values so a human
    resolves the record rather than the code guessing which one wins."""


class IntakeIncompleteError(RuntimeError):
    """Raised when a migrated intake still misses canonical REQUIRED fields.

    Distinguishes missing from answered-no: WANT_SALES_CHECKOUT="no" is a real
    answer (the engine's waiver gate needs it); WANT_SALES_CHECKOUT absent is
    missing. The error names the missing canonical paths."""


def _split_path(path: str) -> tuple:
    """'deck_brief.OFFER_NAME' -> ('deck_brief', 'OFFER_NAME');
    'intake.json.speech_speed_preference' -> ('intake',
    'speech_speed_preference') — the flat intake.json section is stored under
    the record key 'intake', so its canonical path maps to
    record['intake'][key]. A single-segment alias ('WANT_SALES_CHECKOUT',
    'run_mode') names a FLAT top-level key on the record."""
    if path.startswith("intake.json."):
        return ("intake", path[len("intake.json."):])
    parts = tuple(p for p in path.split(".") if p)
    if not parts:
        raise ValueError(f"malformed canonical path: {path!r}")
    return parts


def read_canonical(intake: dict, path: str):
    """Read one canonical field path. Returns the value, or None when absent.
    Absence and answered-no are DIFFERENT results here: an answered-no reads
    back as the string 'no'."""
    if not isinstance(intake, dict):
        return None
    parts = _split_path(path)
    obj = intake
    for part in parts:
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    if obj is None:
        return None
    if isinstance(obj, str) and not obj.strip():
        return None
    return obj


def _write_canonical(intake: dict, path: str, value) -> None:
    parts = _split_path(path)
    obj = intake
    for part in parts[:-1]:
        nxt = obj.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            obj[part] = nxt
        obj = nxt
    obj[parts[-1]] = value


def _delete_alias(intake: dict, alias: str) -> None:
    parts = _split_path(alias)
    obj = intake
    for part in parts[:-1]:
        if not isinstance(obj, dict):
            return
        obj = obj.get(part) or {}
    if isinstance(obj, dict):
        obj.pop(parts[-1], None)


def _same_answer(a, b) -> bool:
    """Normalize both sides (booleanish, case, surrounding whitespace) and
    compare — 'True' and 'yes' are the same answer; 'yes' and 'no' are not."""
    def norm(v):
        if isinstance(v, bool):
            return "yes" if v else "no"
        s = str(v).strip().lower()
        return _LEGACY_BOOLEAN_NORMALIZATION.get(s, s)
    return norm(a) == norm(b)


def migrate_intake(intake: dict) -> dict:
    """Migrate a legacy (pre-contract / version-1) intake record IN PLACE.

    Returns the record. Every canonical field with declared LEGACY_ALIASES is
    reconciled: an empty canonical path adopts the first present alias
    (booleanish-normalized for the flag fields) and the alias copies are
    removed; an alias that AGREES with the canonical value is dropped as
    redundant; an alias that CONTRADICTS the canonical value raises
    ContractMigrationError naming both — never an arbitrary choice.

    A record already stamped with the current schema_version passes through
    untouched. A record stamped with a NEWER version refuses (refusing to
    downgrade)."""
    if not isinstance(intake, dict):
        raise ContractMigrationError(
            "migration refused: intake is not an object")
    version = intake.get("schema_version")
    if version == INTAKE_CONTRACT_VERSION:
        return intake
    if version is not None:
        try:
            v = int(version)
        except (TypeError, ValueError):
            v = None
        if v is not None and v > INTAKE_CONTRACT_VERSION:
            raise ContractMigrationError(
                f"migration refused: record declares schema_version {v}, newer "
                f"than this build's contract version {INTAKE_CONTRACT_VERSION} "
                "-- refusing to downgrade")

    conflicts = []
    for qid, aliases in LEGACY_ALIASES.items():
        canonical = CANONICAL_FIELD_PATHS[qid]
        canon_value = read_canonical(intake, canonical)
        for alias in aliases:
            legacy_value = read_canonical(intake, alias)
            if legacy_value is None:
                continue
            if canon_value is None:
                moved = legacy_value
                if isinstance(moved, bool):
                    moved = "yes" if moved else "no"
                _write_canonical(intake, canonical, moved)
                canon_value = moved
                _delete_alias(intake, alias)
            elif not _same_answer(canon_value, legacy_value):
                conflicts.append((canonical, canon_value, alias, legacy_value))
            else:
                _delete_alias(intake, alias)

    if conflicts:
        details = "; ".join(
            f"{alias}={legacy!r} vs {canonical}={canon!r}"
            for canonical, canon, alias, legacy in conflicts)
        raise ContractMigrationError(
            f"migration refused: contradictory legacy values cannot be "
            f"migrated (contract v{INTAKE_CONTRACT_VERSION}) -- {details}. "
            f"Both locations were read; they disagree, so neither was chosen. "
            f"Resolve the record and re-submit.")

    intake["schema_version"] = INTAKE_CONTRACT_VERSION
    return intake


def validate_intake_completeness(intake: dict) -> list:
    """The canonical REQUIRED check — false/no distinguished from missing.

    Returns the list of missing canonical paths (empty = complete). A present
    but falsy-LOOKING answer ('no', 'false', 0, False) is a REAL answer and is
    never reported missing; only absent/None/blank is."""
    missing = []
    for path in REQUIRED_CANONICAL_FIELDS:
        if read_canonical(intake, path) is None:
            missing.append(path)
    return missing


def validate_and_migrate(intake: dict) -> dict:
    """The Workers' POST /api/intake contract, box-side: migrate first, then
    the completeness gate. Raises ContractMigrationError on a contradictory
    legacy record and IntakeIncompleteError (naming the missing canonical
    paths) on an incomplete one — never writes a hollow intake."""
    migrate_intake(intake)
    missing = validate_intake_completeness(intake)
    if missing:
        raise IntakeIncompleteError(
            "intake incomplete -- required canonical fields missing or empty "
            f"(contract v{INTAKE_CONTRACT_VERSION}): {', '.join(missing)}")
    return intake


# ===========================================================================
# PRES-006 — configuration_pending (missing optional resource-plan subfields)
# ===========================================================================
# The resource_plan turn is OPTIONAL (required:false, block_gate:false): its
# model/mode subfields ride along, and its PLAN-TIER half is asked only when
# the capacity probe leaves a provider pending. An intake that answered the
# interview but left a plan tier (or the whole plan turn) unstated is NOT
# declined and NOT answered — it is configuration_pending. Before this fix the
# writer treated the empty tier as absence and said nothing, so a dispatched
# build PARKed on AF-CAPACITY-UNMEASURED with no durable record of WHY, no
# owner, and no next action. The durable event (below) carries the missing
# field, the provider, a scoped resume link and the next action; already
# configured independent routes proceed — the pending configuration never
# blocks the run, it stays VISIBLE.

#: The durable event's kind, as intake-poll/supervisor integrations read it.
CONFIGURATION_PENDING_EVENT = "configuration_pending"

#: Where the durable events live in the run dir (JSONL — appended, never
#: rewritten, so concurrent writers cannot clobber each other).
CONFIG_EVENTS_RELPATH = "working/events/configuration_events.jsonl"

#: The resource-plan canonical subfields whose absence is configuration-pending
#: (never "declined", never "answered"). Mirrors deck-intake-questions.json's
#: resource_plan subfields + LEGACY_ALIASES's canonical homes.
_RESOURCE_PLAN_CONFIG_FIELDS = (
    ("resource_plan", "pre_presentation_capture.RESOURCE_PLAN",
     "plan tier for the provider whose concurrency could not be detected"),
    ("workhorse_model", "pre_presentation_capture.WORKHORSE_MODEL",
     "workhorse model (model@provider)"),
    ("reasoning_model", "pre_presentation_capture.REASONING_MODEL",
     "reasoning model (model@provider)"),
    ("qc_model", "pre_presentation_capture.QC_MODEL",
     "qc judge model (model@provider)"),
    ("thinking_mode", "pre_presentation_capture.THINKING_MODE",
     "thinking mode (max/high/medium/low/off)"),
    ("run_mode", "pre_presentation_capture.RUN_MODE",
     "run mode (ultra/standard/economy)"),
)

#: Where pending providers are read from, BEFORE the empty-tier return —
#: resource_profile.pending_questions()'s shape ({id, provider, ...}).
_PENDING_PROVIDER_KEY = "pending_providers"


def _resume_url(session_id: str) -> str:
    """The client's scoped resume link for a pending configuration. The base
    comes from the PRESENTATION_INTAKE_BASE_URL env (the hosted app's own
    origin); without it the link is relative and the poller/supervisor renders
    it against the deployment it knows. NEVER an admin URL — this is the
    client's own capability surface."""
    base = os.environ.get("PRESENTATION_INTAKE_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}/s/{session_id}"
    return f"/s/{session_id}"


def pending_configurations(intake: dict, pending_providers: "list | None" = None) -> list:
    """The optional resource-plan subfields this intake left unstated.

    Inspects the pending providers FIRST (the ask-gate the bank documents:
    'asked only when the capacity probe leaves a pending question') and pairs
    each still-unstated subfield with the provider(s) it is owed for. Returns
    one record per pending configuration:

        {field, missing_field, provider, next_action, state}

    state is always "configuration_pending" — NEVER "declined" and NEVER
    "answered". Absence here is absence; silence is not consent. An intake
    that stated every subfield returns [] — nothing is invented."""
    if not isinstance(intake, dict):
        return []
    providers = pending_providers
    if providers is None:
        providers = intake.get(_PENDING_PROVIDER_KEY) or []
    if not isinstance(providers, list):
        providers = []
    provider_ids = []
    for p in providers:
        if isinstance(p, dict) and p.get("provider"):
            provider_ids.append(str(p["provider"]))
        elif isinstance(p, str) and p.strip():
            provider_ids.append(p.strip())
    if not provider_ids:
        # No probe left any provider pending (or none was recorded): nothing
        # is OWED, so nothing is pending — never a placeholder record for an
        # unstated subfield nobody is waiting on.
        return []

    out = []
    for sub_id, canonical, human in _RESOURCE_PLAN_CONFIG_FIELDS:
        if read_canonical(intake, canonical) is not None:
            continue  # stated — nothing pending for this subfield
        for provider in provider_ids:
            out.append({
                "field": canonical,
                "missing_field": sub_id,
                "provider": provider,
                "state": CONFIGURATION_PENDING_EVENT,
                "next_action": (
                    f"answer the resource-plan {sub_id} for {provider} ({human}); "
                    "the run is NOT blocked — already configured routes proceed"),
            })
    return out


def emit_configuration_pending_events(run_dir: pathlib.Path, intake: dict,
                                      session_id: str = "") -> list:
    """Write the configuration_pending durable events for `intake`'s unstated
    optional resource-plan subfields.

    Durable = appended (one JSON line each) to
    working/events/configuration_events.jsonl — never rewritten, so a
    concurrent reader (intake-poll, the supervisor, the engine) sees every
    event ever emitted. Each record carries the missing field, the provider,
    the SCOPED RESUME LINK (the client's own /s/<session> capability URL, never
    an admin surface) and the next action. Returns the records written.

    The pending-provider list is read from the intake record's own
    pending_providers key (stamped by the caller from the capacity probe's
    resource_profile.pending_questions BEFORE any empty-tier return) — this
    function never runs the probe itself (read-only caller contract, no
    network). Independent already-configured routes are NOT touched: this
    writes visibility, never a block."""
    pending = pending_configurations(intake)
    if not pending:
        return []
    events = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for rec in pending:
        events.append({
            "event": CONFIGURATION_PENDING_EVENT,
            "at": now_iso,
            "session_id": session_id or str(intake.get("intake_session_id") or ""),
            "run_dir": str(run_dir),
            "field": rec["field"],
            "missing_field": rec["missing_field"],
            "provider": rec["provider"],
            "resume_url": _resume_url(session_id or str(intake.get("intake_session_id") or "")),
            "next_action": rec["next_action"],
            "state": CONFIGURATION_PENDING_EVENT,
            "owner": "presentation-intake",
            "source": "intake_writer",
        })
    out = run_dir / CONFIG_EVENTS_RELPATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return events


# ===========================================================================
# FIX 11 -- THE CLIENT'S RUN MODE, ON THE HOSTED PATH
# ===========================================================================
# The hosted interview app is a THIRD intake path, beside the agent-driven
# deck-intake-driver.py and the canonical entry script. FIX 11 wired the run
# mode (ultra|standard|economy) through the bank, the driver and the poller --
# but this writer, pages/questions.json, pages/index.html and
# payload/build_questions_payload.py had no run-mode handling of ANY kind. The
# app never ASKED, so no client could declare one, and every hosted run
# executed STANDARD while every surface reported success. Silent, on real
# paying clients.
#
# Stated precisely, because it is not quite "the writer could not persist it":
# an INJECTED run_mode answer -- one no client could produce, because nothing
# asked -- fell through write_ledger()'s generic answer loop into
# entries["run_mode"] RAW, and read_run_mode()'s SECOND candidate key did pick
# that up. What was missing was everything around it: the question, the
# canonical RUN_MODE key (the poller's FIRST candidate, and the driver's), any
# normalisation, and any refusal -- "quick", "in-depth" and "turbo" all landed
# in the ledger and in deck_brief unrefused, to be dropped later by the poller
# with a stderr line no client ever sees.
#
# THE CONTRACT IS THE DRIVER'S, NOT A NEW ONE. deck-intake-driver.py's
# _record_run_mode is the reference implementation and this mirrors it exactly:
#
#   * the ledger key is RUN_MODE, and the subfield id run_mode is written
#     alongside it as the SAME record (driver: _RUN_MODE_SUBFIELD);
#   * the record shape is {value, validated, source, answered_at, normalized,
#     answer} -- only `source` differs, naming this writer;
#   * case-insensitive in, normalised lowercase out;
#   * an OMITTED declaration writes NOTHING AT ALL. Absence is absence, and
#     model_router.DEFAULT_MODE ("standard") then applies downstream. Never
#     "ultra" by default: nothing silently launches at the operator ceiling.
#
# WHAT THIS ADDS OVER THE DRIVER: a refusal. The driver refuses bad vocabulary
# one layer up, in validate_labeled_enums(), before _record_run_mode ever sees
# it. This module has no such layer -- write_intake_file()/write_ledger() ARE
# the entry points intake_bridge.cmd_ingest() calls -- so the refusal lives
# here, in the same fail-closed idiom as _require_grounded_deck_type(): raise,
# and write NOTHING, rather than let an unvalidated word reach a file.
#
# Stdlib only, so the vocabulary is MIRRORED from the bank rather than
# imported (the same reason MANDATORY_PRE_CAPTURE and LEGACY_FIELD_MAPPING
# above are mirrored). The mirror is not allowed to drift: the source of truth
# is deck-intake-questions.json's resource_plan.run_mode subfield, and
# test_intake_writer_run_mode.py fails if these constants stop matching it.
_RUN_MODE_SOURCE_OF_TRUTH = (
    "23-ai-workforce-blueprint/templates/role-library/presentations/intake/"
    "deck-intake-questions.json :: questions[resource_plan].subfields.run_mode")

#: (subfield id, ledger key) -- deck-intake-driver.py's _RUN_MODE_SUBFIELD.
_RUN_MODE_SUBFIELD = ("run_mode", "RUN_MODE")

#: The FIX 11 vocabulary. Mirrors the bank's enum AND
#: presentation_job.model_router.MODES, the authority the poller validates
#: against.
RUN_MODES = ("ultra", "standard", "economy")

#: What a run with NO declaration executes as -- model_router.DEFAULT_MODE.
#: Stated here so "the client said nothing" has a named, testable answer; it is
#: NOT written into any file (see _record_run_mode).
DEFAULT_RUN_MODE = "standard"

#: The OTHER axis's vocabulary, refused here. Mirrors the bank's refuse_values.
RUN_MODE_REFUSED_VALUES = ("quick", "in-depth", "in_depth", "indepth")

#: Mirrors the bank's refuse_message verbatim.
RUN_MODE_REFUSE_MESSAGE = (
    "run mode got interview-depth vocabulary {value}. The RUN-MODE axis "
    "(FIX 11) is ultra|standard|economy and decides how the deck is BUILT "
    "(concurrency, ceiling, model mix); the INTERVIEW-DEPTH axis (FIX 30/36 "
    "standard_mode, --intake-depth) is quick|in-depth and decides how much of "
    "this interview you are asked. The two axes are never interchangeable and "
    "never share a slot.")


class RunModeVocabularyError(RuntimeError):
    """Raised when a run-mode declaration is not one of RUN_MODES.

    FAIL CLOSED, like UngroundedDeckTypeError above: write_intake_file() and
    write_ledger() both raise this BEFORE writing anything, so a refused
    declaration can never half-land -- no intake.json carrying the bad word, no
    ledger marked "complete" on top of it.

    Two distinct refusals, both loud:

      * INTERVIEW-DEPTH vocabulary (quick / in-depth) gets
        RUN_MODE_REFUSE_MESSAGE, which names BOTH axes. Run mode is FIX 11
        concurrency/cost policy; interview depth is FIX 30/36 intake length.
        Conflating them is the exact mistake the FIX-11/FIX-36 split exists to
        prevent, so the client is told which two axes they crossed rather than
        given a bare "invalid value".
      * anything else unrecognised is refused naming the allowed vocabulary.
        NEVER coerced -- an unknown word is not quietly rounded to a cheaper or
        more expensive run.
    """


def normalize_run_mode(raw) -> "str | None":
    """One raw declaration -> a legal lowercase mode, or None when absent.

    Returns None for an omitted/blank declaration -- absence, which writes
    nothing and lets DEFAULT_RUN_MODE apply downstream. Raises
    RunModeVocabularyError for the interview-depth words and for anything else
    unrecognised.
    """
    if isinstance(raw, dict):
        raw = raw.get("value", raw.get("normalized", ""))
    text = str(raw or "").strip().strip("'\"").strip(";,.").strip().lower()
    if not text:
        return None
    if text in RUN_MODE_REFUSED_VALUES:
        raise RunModeVocabularyError(
            RUN_MODE_REFUSE_MESSAGE.replace("{value}", repr(text)))
    if text not in RUN_MODES:
        raise RunModeVocabularyError(
            f"run_mode declaration {text!r} is not one of "
            f"{'|'.join(RUN_MODES)} -- refusing to guess a run mode. An "
            f"unknown mode is never silently coerced into a cheaper or more "
            f"expensive one.")
    return text


def _raw_run_mode(intake: dict):
    """Find the client's declaration wherever this module's callers put it.

    The hosted app reaches write_intake_file()/write_ledger() by more than one
    route (see _require_grounded_deck_type's docstring): assemble_intake()'s
    flat-answers assembly, and intake_bridge.cmd_ingest() handing over the
    frontend-shaped payload whole. Checked in declaration order: the client's
    own answers first, then wherever a caller's routing already filed it.
    """
    sub_id, ledger_key = _RUN_MODE_SUBFIELD
    for candidate in (
            (intake.get("answers") or {}).get(sub_id),
            (intake.get("pre_presentation_capture") or {}).get(ledger_key),
            (intake.get("deck_brief") or {}).get(ledger_key),
            intake.get(ledger_key),
            intake.get(sub_id)):
        if isinstance(candidate, dict):
            candidate = candidate.get("value", candidate.get("normalized"))
        if str(candidate or "").strip():
            return candidate
    return None


def _require_grounded_run_mode(intake: dict) -> "str | None":
    """Validate -- and normalise -- intake's run-mode axis in place.

    Called by both write_intake_file() and write_ledger(), for the same reason
    _require_grounded_deck_type() is: assemble_intake() is not the only path
    into this module. Raises RunModeVocabularyError -- nothing is written -- on
    a refused declaration.

    On a VALID declaration the normalised lowercase value replaces whatever the
    client typed, everywhere it landed, so intake.json and the ledger can never
    disagree about the mode. On absence every trace is removed, so a blank
    answer leaves no empty RUN_MODE for a reader to trip over.

    deck_brief NEVER keeps it either way: a run mode is an execution axis, not
    deck content (see PRE_CAPTURE_FIELDS).
    """
    sub_id, ledger_key = _RUN_MODE_SUBFIELD
    mode = normalize_run_mode(_raw_run_mode(intake))

    brief = intake.get("deck_brief")
    if isinstance(brief, dict):
        brief.pop(ledger_key, None)
        brief.pop(sub_id, None)

    pre = intake.get("pre_presentation_capture")
    answers = intake.get("answers")
    if mode is None:
        if isinstance(pre, dict):
            pre.pop(ledger_key, None)
        if isinstance(answers, dict):
            answers.pop(sub_id, None)
        intake.pop(ledger_key, None)
        return None
    if not isinstance(pre, dict):
        # A caller that filed the mode somewhere else and supplied no capture
        # section at all still gets it recorded. Dropping the declaration here
        # -- silently, on a payload we know carried one -- is the exact defect
        # class this whole fix exists to close.
        pre = {}
        intake["pre_presentation_capture"] = pre
    pre[ledger_key] = mode
    if isinstance(answers, dict) and sub_id in answers:
        answers[sub_id] = mode
    return mode


def _record_run_mode(mode: "str | None", entries: dict) -> None:
    """Stamp the declared run mode onto the ledger in the DRIVER's shape.

    deck-intake-driver.py's _record_run_mode writes entries[RUN_MODE] and
    entries[run_mode] as the same record; presentation-intake-poll.sh's
    read_run_mode() reads exactly those two keys (candidate 1) and needs no
    change to see this one.

    Takes the mode _require_grounded_run_mode() already validated rather than
    re-deriving it from `intake`. Deriving twice was a real trap: the first
    pass normalises the record IN PLACE, so a second pass over the mutated
    intake could read a different answer than the one that was validated -- and
    the way it fails is by finding nothing and silently writing nothing, which
    is the defect this fix exists to close.

    An omitted declaration writes NOTHING and REMOVES the empty passthrough
    entry write_ledger()'s generic answer loop would otherwise leave behind --
    the driver writes no key at all in that case, and a ledger that says
    run_mode="" is not the same record as one that never mentions it.
    """
    sub_id, ledger_key = _RUN_MODE_SUBFIELD
    if mode is None:
        entries.pop(sub_id, None)
        entries.pop(ledger_key, None)
        return
    now_iso = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()
    rec = {"value": mode, "validated": True,
           "source": "presentation-interview-app",
           "answered_at": now_iso, "normalized": mode, "answer": mode}
    entries[ledger_key] = rec
    entries[sub_id] = dict(rec)


def field_for(qid: str, value) -> str:
    """Resolve the intake.json field key for a question id."""
    mapped = ID_TO_FIELD.get(qid)
    if mapped:
        return mapped
    return qid.upper()


def map_section(section: str) -> str:
    """Map a storeOn prefix to an intake.json section key."""
    return {
        "deck_brief": "deck_brief",
        "pre_presentation_capture": "pre_presentation_capture",
        "intake.json": "intake",
    }.get(section, "deck_brief")


# FIX-PITCH-ANTI-FAB: fields that MUST land as TRUE ROOT keys on intake.json
# (never nested under deck_brief/pre_presentation_capture/answers) because
# scripts/pitch_engines_check.py's chk_branded_method / chk_time_to_result
# read them with a bare `intake.get("named_methodology")` /
# `intake.get("time_to_result")` at the file's top level -- deliberately, so
# a copywriter can never invent a method name or delivery timeline, only the
# client's own answer can supply them. pitch_engines_check.py is a verifier
# this unit may not edit to add a nested-shape fallback (unlike
# sales_checkout_builder.py / vsl_builder.py, which test_upsell_intake_shape.py
# pins as reading BOTH the driver's flat shape and this bridge's nested
# shape) -- so the flat ROOT shape must be guaranteed on the write side
# instead. deck-intake-driver.py's cmd_complete() already produces this shape
# natively for the chat path (entries[qid] aliasing); this promotion is the
# equivalent guarantee for the app path.
ANTI_FABRICATION_ROOT_FIELDS = ("named_methodology", "time_to_result")


def _promote_anti_fabrication_fields(intake: dict) -> dict:
    """Ensure named_methodology/time_to_result land as TRUE ROOT keys, in place.

    Runs on every path into write_intake_file() -- the flat-answers assembly
    (which files the value under deck_brief.<UPPER> via field_for()'s
    qid.upper() fallback) AND the frontend-shaped passthrough (which has no
    "root" bucket at all in its client-side buildIntakePayload() and would
    otherwise strand the answer inside deck_brief.<UPPER> or the raw
    answers{} map, where pitch_engines_check.py's bare intake.get(...) read
    can never see it). Never invents a value -- only relocates one the client
    actually supplied, checked in this order: already at root, then
    deck_brief.<UPPER>, then answers.<qid>. A question the client was never
    asked (or left unanswered) is correctly left absent -- the gate should
    fail closed on that, not be papered over here.
    """
    answers = intake.get("answers") or {}
    brief = intake.get("deck_brief") or {}
    for qid in ANTI_FABRICATION_ROOT_FIELDS:
        if intake.get(qid):
            continue
        val = brief.get(qid.upper())
        if not val:
            raw = answers.get(qid)
            val = raw.get("value") if isinstance(raw, dict) else raw
        if val:
            intake[qid] = val
    return intake


def assemble_intake(app_payload: dict, run_id: str = "") -> dict:
    """Turn the app's answer map into the dept-format intake record.

    app_payload may carry either `answers` (a flat {qid: value} map) or an
    `intake` object already shaped by the frontend (interview_confirmed, deck
    fields, pre_presentation_capture, deck_brief, intake). When both exist the
    frontend-shaped intake wins and `answers` is attached for provenance.
    """
    if isinstance(app_payload.get("intake"), dict):
        base = dict(app_payload["intake"])
        base["answers"] = app_payload.get("answers") or base.get("answers") or {}
        return base

    answers = app_payload.get("answers") or {}
    brief = {}
    pre = {}
    intake_flat = {}
    for qid, v in answers.items():
        if qid.startswith("_"):
            continue
        if isinstance(v, dict):
            v = v.get("value", "")
        field = field_for(qid, v)
        if field == "speech_speed_preference":
            intake_flat[field] = v
        elif field in PRE_CAPTURE_FIELDS:
            pre[field] = v
        else:
            brief[field] = v
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    # deck_type/creation_mode/presentation_mode/audience_mode/
    # presentation_type: grounded ONLY in the client's own presentation_type
    # answer -- may raise UngroundedDeckTypeError. This used to be a
    # hardcoded "webinar" here; see UngroundedDeckTypeError.__doc__.
    deck_type_fields = _grounded_deck_type_fields(answers)

    intake = {
        "interview_confirmed": True,
        "target_talk_minutes": 20,
        "created_at": now,
        "source": "presentation-interview-app",
        "run_id": run_id,
        "deck_brief": brief,
        "pre_presentation_capture": {
            "REPRESENTATION_MIX": brief.get("AUDIENCE") or "the stated audience",
            "AUDIENCE_COMPOSITION_NOTE": brief.get("AUDIENCE") or "",
            "GROUNDED_CONTENT": brief.get("OFFER_NAME") or "",
            "VISUAL_MIX": "mix",
            "DARK_OK": False,
            "HOOK_SEED": brief.get("TRANSFORMATION_PROMISE") or "",
            **pre,
        },
        "intake": intake_flat,
        "answers": answers,
    }
    intake.update(deck_type_fields)
    return intake


def write_intake_file(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/copy/intake.json in the run dir (the deck brief).

    FAIL CLOSED: raises UngroundedDeckTypeError -- writing nothing -- if
    `intake`'s deck-type axis cannot be grounded in its own `answers`. Runs
    for every caller, not just assemble_intake()'s output: intake_bridge.py's
    cmd_ingest() calls this directly with a raw Worker payload. See
    _require_grounded_deck_type().

    PRES-006: migrates any legacy (pre-contract) record forward FIRST
    (ContractMigrationError refuses a contradictory one, writing nothing) and
    then runs the canonical completeness gate (IntakeIncompleteError names the
    missing canonical paths -- a real "no" answer never counts as missing).

    Also runs _promote_anti_fabrication_fields() (FIX-PITCH-ANTI-FAB) for the
    same reason -- so named_methodology/time_to_result land at intake.json's
    TRUE ROOT no matter which caller built `intake`.
    """
    _require_grounded_deck_type(intake)
    _require_grounded_run_mode(intake)
    _promote_anti_fabrication_fields(intake)
    migrate_intake(intake)
    missing = validate_intake_completeness(intake)
    if missing:
        raise IntakeIncompleteError(
            "intake incomplete -- required canonical fields missing or empty "
            f"(contract v{INTAKE_CONTRACT_VERSION}): {', '.join(missing)}")
    out = run_dir / "working" / "copy" / "intake.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(intake, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def write_ledger(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/interview/intake_ledger.json as 'complete'.

    This satisfies presentation-canonical-entry.sh GATE 0 (intake ledger) and
    the _intake_provenance_gate's ledger-consistency check for app-captured
    runs. `answers` carries the captured Q&A pairs so the ledger is NOT an
    empty fabrication.

    FAIL CLOSED: raises UngroundedDeckTypeError -- writing nothing, never
    "complete": true -- if `intake`'s deck-type axis cannot be grounded in
    its own `answers`. See _require_grounded_deck_type(). PRES-006: also runs
    the contract migration + canonical completeness gate first, so a
    contradictory legacy record or an incomplete one never reaches a
    "complete" ledger.
    """
    _require_grounded_deck_type(intake)
    _require_grounded_run_mode(intake)
    migrate_intake(intake)
    missing = validate_intake_completeness(intake)
    if missing:
        raise IntakeIncompleteError(
            "intake incomplete -- required canonical fields missing or empty "
            f"(contract v{INTAKE_CONTRACT_VERSION}): {', '.join(missing)}")
    run_mode = _require_grounded_run_mode(intake)
    ledger_path = run_dir / "working" / "interview" / "intake_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    answers = intake.get("answers") or {}
    entries = {}
    for qid, value in answers.items():
        if isinstance(value, dict):
            value = value.get("value", "")
        entries[qid] = {
            "value": value,
            "validated": True,
            "source": "presentation-interview-app",
        }
    # FIX 11: the run mode is stamped EXPLICITLY, after the generic loop, in
    # deck-intake-driver._record_run_mode's exact shape -- the loop above would
    # otherwise leave the client's raw, unnormalised word under the lowercase
    # id alone, with no RUN_MODE key for the poller's first candidate.
    _record_run_mode(run_mode, entries)
    ledger = {
        "status": "complete",
        "complete": True,
        "source": "presentation-interview-app",
        "intake_session_id": intake.get("intake_session_id", ""),
        "entries": entries,
    }
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    return ledger_path


_DRIVER_ENVELOPE_FORMAT = "sp-intake-transcript-v1"


class SignedEnvelopePresentError(RuntimeError):
    """Raised by write_transcript() when working/interview/intake_transcript.json
    already holds a SIGNED driver envelope (format == 'sp-intake-transcript-v1',
    written by deck-intake-driver.py's turn-gate -- see intake_trace_check.py's
    DRIVER PROVENANCE doctrine).

    FIX F21-SIBLING (2026-08-20): this module's own write_transcript()
    unconditionally overwrote intake_transcript.json with no read-first check
    at all -- the same "blind write destroys signed provenance" hazard fixed
    at its root in deck-intake-driver.py's cmd_answer/_sig_answer (FAULT-21).
    A driver-produced signed envelope is HIGHER-evidentiary-value provenance
    ("these turns really happened, in this order, through the driver") than
    this bridge's own synthetic Q&A-pair transcript (this module's own
    docstring: full routing through the driver's turn-gate "is the correct
    long-term fix and is deliberately NOT implemented here"). Silently
    replacing the former with the latter would be a real provenance loss, so
    this fails loudly instead -- naming the file -- rather than guessing which
    source should win."""


def write_transcript(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/interview/intake_transcript.json — the real conversation trace.

    presentation-canonical-entry.sh GATE 0b requires this file to exist and be
    non-trivial (>= 200 bytes) with a REAL one-at-a-time conversation (FIX-3:
    intake must be a REAL conversation, not a fabricated block). We build it from
    the app's captured answers: each Q&A pair becomes a dialogue turn, so the
    trace is grounded in the client's actual responses.

    FAIL CLOSED (FIX F21-SIBLING): refuses -- raises SignedEnvelopePresentError,
    writes nothing -- when a SIGNED driver envelope already exists at the
    destination path. See SignedEnvelopePresentError.__doc__.
    """
    out = run_dir / "working" / "interview" / "intake_transcript.json"
    if out.is_file():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict) and existing.get("format") == _DRIVER_ENVELOPE_FORMAT:
            raise SignedEnvelopePresentError(
                f"{out} already holds a signed driver envelope (format="
                f"{_DRIVER_ENVELOPE_FORMAT!r}) -- refusing to overwrite it with "
                "this bridge's own synthetic transcript. Writing nothing.")
    out.parent.mkdir(parents=True, exist_ok=True)
    answers = intake.get("answers") or {}
    brief = intake.get("deck_brief") or {}
    turns = []
    for qid, value in answers.items():
        if isinstance(value, dict):
            value = value.get("value", "")
        q = _question_text(qid, brief)
        turns.append({
            "question_id": qid,
            "question": q,
            "answer": str(value) if value not in (None, "") else "(skipped)",
            "validated": True,
            "source": "presentation-interview-app",
        })
    transcript = {
        "intake_session_id": intake.get("intake_session_id", ""),
        "interview_mode": "one_at_a_time",
        "completed": True,
        "source": "presentation-interview-app",
        "turn_count": len(turns),
        "turns": turns,
    }
    out.write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _question_text(qid: str, brief: dict) -> str:
    """A readable question label for a captured answer id.

    Maps known intake question ids to the human-facing prompt. Unknown ids fall
    back to a stable label so the transcript is always non-trivial and
    unambiguous.
    """
    labels = {
        "offer_name": "What is your offer?",
        "transformation_promise": "What is the transformation promise?",
        "audience": "Who is the audience?",
        "cta_action": "What is the call to action?",
        "brand_primary": "Primary brand color?",
        "tone": "What tone should the deck take?",
        "final_price": "What is the final price?",
        "price_mode": "Price mode?",
        "goal": "What is the deck's goal?",
        "target_feeling": "Target feeling?",
        "hook_seed": "Hook seed?",
        "client_notes": "Client notes?",
        "deadline": "Deadline?",
        "slide_count": "Slide count?",
        "speech_speed_preference": "Preferred speech pace?",
        "want_sales_checkout": "Do you need a sales + checkout page?",
        "want_vsl_page": "Would you like a VSL page?",
        "q1": "First intake question",
        "q2": "Second intake question",
        "q3": "Third intake question",
        "q4": "Fourth intake question",
        "q5": "Fifth intake question",
        "q6": "Sixth intake question",
        "q7": "Seventh intake question",
        "q8": "Eighth intake question",
    }
    return labels.get(str(qid), "Intake question: " + str(qid))


def cmd(args) -> int:
    raw = json.loads(pathlib.Path(args.intake).read_text(encoding="utf-8"))
    try:
        intake = assemble_intake(raw, run_id=args.run_id)
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        ipath = write_intake_file(run_dir, intake)
        lpath = write_ledger(run_dir, intake)
        tpath = write_transcript(run_dir, intake)
    except UngroundedDeckTypeError as exc:
        # Fail closed: nothing above wrote a file before raising. Exit 3
        # distinguishes "ungrounded deck type" from other failures.
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except RunModeVocabularyError as exc:
        # Fail closed the same way, with its own code: exit 4 distinguishes a
        # refused run-mode declaration from an ungrounded deck type, so a
        # caller can tell the client WHICH answer to fix.
        print(f"error: {exc}", file=sys.stderr)
        return 4
    if args.verbose:
        print(f"wrote {ipath}")
        print(f"wrote {lpath}")
        print(f"wrote {tpath}")
        print(f"mandatory pre_capture present: {all(k in intake.get('pre_presentation_capture', {}) for k in MANDATORY_PRE_CAPTURE)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intake", required=True, help="path to the app intake payload JSON")
    ap.add_argument("--run-dir", required=True, help="deck run directory (contains working/)")
    ap.add_argument("--run-id", default="", help="optional run id stamped into the record")
    ap.add_argument("--verbose", action="store_true")
    return cmd(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
