#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/dropdown_module.py
# DROPDOWN CREATOR — the TWO SINGLE_OPTIONS picklist fields the engine's
# client-facing review surface ships: the PRD Section 4 universal-review
# DECISION field (the two-option chapter gate: approve_as_is /
# request_rewrite_with_notes) and the U8 COVER-STYLE choice field
# (anthology_cover_choice: the four named cover styles). CREATION requires
# --execute explicitly (Trevor-gated); without it the module reports the plan
# and writes nothing.
#
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# shared U08/U09 package (pure namespace container per the u08_u09 package
# init: imported BY NAME, side-effect-free at import). It is NOT a manifest
# row and it NEVER touches ENGINE-MANIFEST.json / ENGINE-PIN.sha256 /
# verify.sh: it ships as a sibling helper the way u07_modules/type_checker.py
# does (ENGINE-MANIFEST row 12 pattern — a family module is not a manifest
# row), imported BY NAME as u08_u09_modules.dropdown_module. Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling
# imports use resolves anthology_registry from scripts/.
#
# THE TWO DROPDOWNS THIS MODULE OWNS (each law read once from its owning
# authority, never re-implemented):
#   1. THE DECISION FIELD (PRD Section 4). The universal-review decision form
#      ('universal-review' — the U05 negative-mirror slug, forms_check.py /
#      golden_forms.py / u02_modules.forms_check) is the engine's one
#      client-facing decision form. Its decision field is a SINGLE_OPTIONS
#      that stays SINGLE_OPTIONS and is deliberately NOT in the provisioning
#      inventory (field-map.json, U8 note: "the PRD Section 4
#      universal-review decision field is a separate SINGLE_OPTIONS that
#      stays SINGLE_OPTIONS and is deliberately NOT in this map"). The
#      engine's gate law (gate_engine.py GateSpec s5_gate: EXACTLY TWO
#      actions — ("approve_as_is", "request_rewrite_with_notes"), asserted in
#      self_test) IS the two-option decision law: the review surface is a
#      2-option dropdown. The action names are imported BYTE-EXACT from
#      gate_engine (GATE_DECISION_OPTIONS), so the decision dropdown can
#      never drift from the gate vocabulary that consumes it. The DECISION
#      field key itself is NOT in any repo authority (the field-map excludes
#      it by design) — it is the engine's pinned contact-key convention
#      contact.anthology_review_decision, declared here as the module's own
#      contract and pinned byte-exact by the offline self-test, exactly as a
#      fixture pins the law it ships.
#   2. THE COVER-STYLE CHOICE FIELD (U8 / B8). anthology_cover_choice — the
#      ONE SINGLE_OPTIONS field IN the provisioning inventory (field-map.json
#      row, data_type SINGLE_OPTIONS) — the four named cover styles the
#      client picks ONE of in the universal-review cover dropdown
#      (stage_s7_cover.py: "the client picks ONE style in the
#      universal-review cover dropdown"; --apply-pick --choice <name|key>).
#      The four names are NOT hardcoded: the picklist is imported byte-exact
#      from scripts/cover_render.py COVER_STYLES/STYLE_NAMES (the engine's
#      named-style law: Signature, Bold Editorial, Fine Art, Pure Type — one
#      of them strictly typography-driven), and the module pins that import
#      byte-exact against the field-map's own declared options in order, so
#      the two surfaces can never drift apart (the same coherence law the
#      registry self-test pins: field-map choice_options == STYLE_NAMES).
#      The key itself is read from config/field-map.json cover_style_fields
#      (the ONE field-key authority; golden_review.py reads the same).
#
# CREATE-ONLY-MISSING PROVISION, Trevor-gated. Creating a SINGLE_OPTIONS
# field is a WRITE: it requires --execute explicitly (the Trevor gate; the
# same explicit-execute doctrine the U07 family enforces for its provisioning
# and the u08_u09 package init pins for archive ACTIONS). Without --execute a
# missing field is a STOP (exit 2) — never a silent no-op, never an
# auto-create. WITH --execute the module creates each missing field at its
# DECLARED data_type (SINGLE_OPTIONS with its exact picklist — exactly the
# registry's create_custom_field surface, POST
# /locations/{id}/customFields) and then RE-LISTS and re-verifies in the
# same job, so a report never claims a field that was not read back. The
# report states execute true/false explicitly on every run. A live field of
# the WRONG type is NEVER silently re-created or re-typed (changing a live
# field's dataType is a provisioning decision, never a silent runtime act;
# field-map resolution_rule): it is a FAIL (exit 5). A live field whose
# picklist drifted from the law (missing / extra / reordered / renamed
# option) is a VIOLATION of the picklist law — never a silent pass.
#
# READ-ONLY PATHS: plan (offline, no network, no credential) and the dry-run
# apply (one live listing read) perform ZERO writes. The self-test proves the
# read-only path never calls create.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / __init__.py):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds no credential value at any point — the client
#     object is resolved by the caller's label machinery.
#   - Browser UA on every request: the engine's own LeadConnector v2 client
#     (reg.CafClient) already sends CAF_BROWSER_UA — a public browser
#     User-Agent string — on EVERY request (the proven CF-1010 edge fix;
#     urllib's default "Python-urllib/x.y" is 403'd at the WAF edge before
#     it ever reaches the API). No request is ever made without it. The
#     self-test pins BROWSER_UA == reg.CAF_BROWSER_UA so a registry
#     regression is caught HERE first.
#   - Fail-closed: a malformed field-map section, an absent section, a
#     non-list live read, a drifted picklist contract, a map-vs-cover_render
#     options mismatch all STOP or FAIL — never a blind pass, never a
#     fabricated success. A credential-shaped value on any surface REFUSES
#     rather than echo.
#   - Scope vs edge discrimination on every read (bare 401/403 is HELD,
#     never mislabeled as a scope problem) — inherited from reg.CafClient.
#   - Move in silence; operator-verbose only. Nothing Anthropic in any
#     runtime file. Convert and Flow naming in every client surface.
#
# EXIT CODE CONTRACT (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — every required dropdown key is live SINGLE_OPTIONS
#      with its exact picklist in order (and, with --execute, any missing
#      fields created then read back); also self-test / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP — PIT / location NOT SET, the field-map carries no
#      SINGLE_OPTIONS inventory row, the cover_render style import failed,
#      the map-vs-cover_render options contract drifted, or a missing field
#      without --execute (the Trevor gate; with --execute missing fields are
#      created and re-read)
#   3  HELD — Convert and Flow unreachable (transport) or an upstream/edge
#      block (CF 1010); retryable, never mislabeled as scope
#   4  self-test FAILED (enforced violation detected — a tamper NEVER
#      masquerades as exit 1)
#   5  mismatch — a live dropdown's dataType is not SINGLE_OPTIONS, its live
#      picklist does not byte-equal the law in order, the decision field is
#      live as a non-SINGLE_OPTIONS type, or (--execute path) a created
#      field read back drifted
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr):
#   dropdown_module.py plan                      # offline: the two-dropdown contract
#   dropdown_module.py apply [--location-id X]   # live read-only; a missing
#                                                # field is a STOP without --execute
#   dropdown_module.py apply --execute           # Trevor-gated: create-only-missing
#                                                # then read back and re-verify
#   dropdown_module.py self-test                 # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# other u0X_modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""dropdown_module.py — the TWO SINGLE_OPTIONS dropdowns of the engine's
review surface (the PRD Section 4 universal-review decision field and the U8
cover-style choice field). Create-only-missing, Trevor-gated (--execute);
never prints a token; browser UA (CF 1010) on every request."""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u07 siblings):
# the registry owns the Cloudflare browser-UA wiring, the LeadConnector
# client, the credential label resolution, and the exit-code contract; the
# style-name law lives in scripts/cover_render.py (imported FOR CONSTANTS
# ONLY); the decision-option law lives in scripts/gate_engine.py (imported
# FOR CONSTANTS ONLY; its self-test runs only under `python gate_engine.py`,
# never at import).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import cover_render as cvr  # noqa: E402
import gate_engine as gate  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The Trevor gate: --execute is the ONLY flag that authorizes the create-only-
# missing write path. Without it a missing field is a STOP, never a silent
# no-op and never an auto-create (the same explicit-execute doctrine the U07
# family enforces for its provisioning and the u08_u09 package init pins for
# archive ACTIONS).
EXECUTE_FLAG = "--execute"

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a dropdown
# create (the self-test asserts the golden plan carries the exact string —
# the surface contract is load-bearing).
REPORT_CONTRACT = "anthology-engine-dropdown-create"
PLAN_CONTRACT = REPORT_CONTRACT + "-plan"

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123") — the same guard the u04 form reader and the
# u08_u09 hidden-field module ship. Every emitted surface is scanned against
# it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class DropdownError(Exception):
    """A fail-closed verification refusal (STOP or mismatch family)."""


class StyleImportError(Exception):
    """The cover_render style-name law is unavailable — refusing to judge a
    choice-field contract we cannot read (never a blind pass)."""


class DecisionImportError(Exception):
    """The gate_engine decision-option law is unavailable — refusing to judge
    a decision-field contract we cannot read (never a blind pass)."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing contract is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise DropdownError(
            "field-map.json has no provisioning.fields inventory — the "
            "dropdown gate has nothing to assert; refusing a blind pass.")
    return [f for f in fields if isinstance(f, dict)]


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _mask_location(loc: str) -> str:
    return reg._mask_location(loc)


def _field_map() -> dict:
    try:
        raw = json.loads(Path(FIELD_MAP_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DropdownError(
            "config/field-map.json cannot be read (%s) — the U8 field-key "
            "authority is missing; a dropdown creator never guesses a field "
            "key" % exc)
    if not isinstance(raw, dict) or not isinstance(
            (raw.get("provisioning") or {}).get("fields"), list):
        raise DropdownError(
            "config/field-map.json carries no provisioning.fields inventory "
            "— the U8 field-key authority drifted")
    return raw


# ---------------------------------------------------------------------------
# LAW 1 — the PRD Section 4 universal-review DECISION field. The engine's
# gate vocabulary is the two-option decision law: gate_engine.py GateSpec
# s5_gate pins EXACTLY ("approve_as_is", "request_rewrite_with_notes") and
# asserts it in self_test. The decision dropdown can never drift from the
# gate that consumes it — the options are imported byte-exact, never
# re-typed. The field KEY (contact.anthology_review_decision) is the
# engine's pinned contact-key convention: the decision field is deliberately
# NOT in the field-map provisioning inventory (U8 note) and NOT in any other
# repo authority, so this module declares its own contract key and pins it
# byte-exact by the offline self-test — exactly as a fixture pins the law it
# ships. The decision dropdown is a 2-option dropdown.
# ---------------------------------------------------------------------------
def _decision_option_law() -> tuple:
    """The EXACT two-option decision law, byte-exact, from gate_engine (the
    ONE authority — the gate that consumes the decision). Raises
    DecisionImportError when the law is unavailable or not exactly two
    distinct non-empty options: the decision contract cannot be judged
    against an unavailable or drifted surface."""
    # The authority is GATE_BY_CURSOR["s5_gate"].actions — the chapter gate's
    # EXACTLY-TWO-ACTIONS law (SPEC S5, asserted in gate_engine self_test).
    # GATE_DECISION_OPTIONS is this module's own mirror of the same law,
    # declared only so the self-test can prove the discrimination both ways.
    opts = ()
    s5 = getattr(gate, "GATE_BY_CURSOR", {}).get("s5_gate")
    if s5 is not None:
        cand = getattr(s5, "actions", None)
        if isinstance(cand, tuple):
            opts = cand
    if not opts:
        opts = getattr(gate, "GATE_DECISION_OPTIONS", ())
    if not isinstance(opts, tuple):
        opts = tuple(opts or ())
    if len(opts) != 2 or len(set(opts)) != 2 or \
            not all(isinstance(o, str) and o.strip() for o in opts):
        raise DecisionImportError(
            "gate_engine did not resolve to exactly two distinct "
            "non-empty decision actions (got %r) — the two-option "
            "decision law is unjudgeable; refusing a blind pass."
            % (opts,))
    return opts


def _decision_key_law() -> str:
    """The decision field KEY — the engine's pinned contact-key convention
    (contact.anthology_review_decision). The decision field is deliberately
    NOT in the field-map provisioning inventory (U8 note), so the key is
    this module's own contract, pinned byte-exact by the offline self-test
    and never fabricated at runtime."""
    return "contact.anthology_review_decision"


DECISION_KEY = _decision_key_law()


# ---------------------------------------------------------------------------
# LAW 2 — the U8 cover-style choice field. The key is read once from
# config/field-map.json cover_style_fields (the ONE field-key authority);
# the four style NAMES are imported byte-exact from cover_render.STYLE_NAMES
# (the naming authority; the registry self-test pins field-map
# choice_options == STYLE_NAMES in order — coherence is law).
# ---------------------------------------------------------------------------
def _choice_row(field_map: dict) -> dict:
    for f in _contract_inventory(field_map):
        if (f.get("data_type") or "") == "SINGLE_OPTIONS":
            return f
    raise DropdownError(
        "field-map provisioning.fields carries no SINGLE_OPTIONS row — the "
        "U8 cover-choice law is unjudgeable; refusing a blind pass.")


def _declared_choice_options(field_map: dict) -> list:
    """The field-map's declared options for the SINGLE_OPTIONS inventory row.
    Raises DropdownError when the declared options do not exist — a choice
    field without a picklist is a contradiction the map must never carry."""
    row = _choice_row(field_map)
    opts = row.get("options")
    if not isinstance(opts, list) or not opts:
        raise DropdownError(
            "field-map SINGLE_OPTIONS row %r carries no options — the "
            "choice picklist law is unjudgeable; refusing a blind pass."
            % (row.get("intended_key") or "?"))
    return list(opts)


def _choice_key_law(field_map: dict) -> str:
    csf = (field_map.get("cover_style_fields") or {})
    choice = csf.get("choice_field")
    if not isinstance(choice, str) or not choice.strip():
        raise DropdownError(
            "config/field-map.json carries no cover_style_fields.choice_field "
            "— the U8 choice key is missing")
    return choice


def _cover_style_names() -> tuple:
    """The four named cover styles in cover_render.py STYLE_NAMES order —
    the byte-exact names the client picks from in the universal-review cover
    dropdown. Raises StyleImportError when the law is unavailable or not
    exactly four distinct names: the choice contract cannot be judged
    against an unavailable or drifted surface."""
    names = tuple(getattr(cvr, "STYLE_NAMES", ()) or ())
    if not names or len(names) != 4 or len(set(names)) != 4:
        raise StyleImportError(
            "cover_render.STYLE_NAMES did not resolve to exactly four "
            "distinct names — the U8 choice contract is unjudgeable; "
            "refusing a blind pass.")
    if not all(isinstance(n, str) and n.strip() for n in names):
        raise StyleImportError(
            "cover_render.STYLE_NAMES carries a blank/non-string entry — "
            "the style-name law is drifted; refusing a blind pass.")
    return names


# The browser User-Agent law, pinned to the registry's constant. Every live
# request rides reg.CafClient, which sends CAF_BROWSER_UA on EVERY request
# (the CF 1010 law); the self-test pins BROWSER_UA == reg.CAF_BROWSER_UA so a
# registry regression is caught HERE first.
BROWSER_UA = reg.CAF_BROWSER_UA


# ---------------------------------------------------------------------------
# The check — returns the machine report dict; raises on STOP / HELD /
# fail-closed refusal. NEVER prints a token (it holds none: credentials are
# resolved by the caller's label machinery, SET / NOT SET only).
# ---------------------------------------------------------------------------
def _collect_live(live_fields) -> dict:
    """Index live custom-field records by fieldKey. Fail-closed: an empty /
    non-list read is a refusal, never a silent pass."""
    if not isinstance(live_fields, list):
        raise DropdownError(
            "customFields read did not return a list — refusing to judge an "
            "unread surface (never fabricated).")
    out = {}
    for f in live_fields:
        if not isinstance(f, dict):
            continue
        k = f.get("fieldKey")
        if k:
            out[k] = f
    return out


def check_dropdowns_live(client, location_id: str, field_map: dict,
                         *, execute: bool = False,
                         expected_styles=None,
                         expected_decision=None) -> dict:
    """Live dropdown check (the 2-option decision law + the 4-option
    cover-style law) with the Trevor-gated create-only-missing path. Returns
    the report dict; raises DropdownError (STOP family) or reg.ScopeDenied /
    reg.UpstreamBlockedError / reg.CafUnreachable (HELD family) upward —
    exactly the propagation the sibling verifier's driver uses.

    With execute=True, each MISSING dropdown key is created at its declared
    data_type (SINGLE_OPTIONS with its exact picklist in order), then the
    location is RE-LISTED and every created key is re-verified against the
    read-back — a report never claims a field that was not read back. A
    live field of the WRONG type is never re-created and never re-typed: it
    is a FAIL (a provisioning decision, never a silent runtime act)."""
    masked = _mask_location(location_id)
    styles = expected_styles if expected_styles is not None else _cover_style_names()
    decision = expected_decision if expected_decision is not None else _decision_option_law()

    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    if total is not None and len(inventory) != total:
        raise DropdownError(
            "field-map provisioning.fields carries %d keys but the "
            "provisioning.total_keys contract says %d — the field-map "
            "drifted from its own contract; refusing to judge against a "
            "self-contradicting map." % (len(inventory), total))

    # The two dropdown laws — key + data_type + picklist, every byte pinned.
    choice_row = _choice_row(field_map)
    choice_key = choice_row.get("intended_key") or ""
    declared_options = _declared_choice_options(field_map)
    if list(declared_options) != list(styles):
        raise DropdownError(
            "field-map declared options for %r do not byte-equal "
            "cover_render.STYLE_NAMES in order — the choice picklist "
            "drifted from the style-name law; refusing to judge (never a "
            "blind pass)." % choice_key)

    # The decision key is NOT in the field-map (U8 note) — it is the module's
    # own contract; the cover key must BE the inventory's lone SINGLE_OPTIONS
    # row (the U8 coherence law the registry self-test pins).
    if not choice_key:
        raise DropdownError(
            "the field-map SINGLE_OPTIONS row carries no intended_key — "
            "refusing a blind pass.")

    specs = [
        {"key": DECISION_KEY, "create_name": "anthology_review_decision",
         "data_type": "SINGLE_OPTIONS", "options": list(decision),
         "law": "decision"},
        {"key": choice_key,
         "create_name": choice_row.get("create_name") or "",
         "data_type": "SINGLE_OPTIONS", "options": list(styles),
         "law": "cover_style"},
    ]
    if not specs[1]["create_name"]:
        raise DropdownError(
            "the field-map SINGLE_OPTIONS row %r carries no create_name — "
            "the choice picklist law is unjudgeable; refusing a blind pass."
            % choice_key)

    live = _collect_live(client.list_custom_fields(location_id))
    created = []
    if execute:
        # Trevor-gated create-only-missing: create each ABSENT dropdown at
        # its declared data_type with its exact picklist, then the whole
        # location is re-listed below and every created key is verified
        # against the read-back.
        for spec in specs:
            if spec["key"] in live:
                continue
            client.create_custom_field(location_id, spec["create_name"],
                                       spec["data_type"],
                                       options=list(spec["options"]))
            created.append(spec["key"])
        if created:
            live = _collect_live(client.list_custom_fields(location_id))

    missing = sorted(set(s["key"] for s in specs) - set(live))
    violations = []
    for spec in specs:
        livef = live.get(spec["key"])
        if livef is None:
            continue  # counted under `missing` above
        got_type = livef.get("dataType")
        if got_type != "SINGLE_OPTIONS":
            violations.append(
                "%s dataType %r != SINGLE_OPTIONS (the picklist law: a "
                "dropdown must be SINGLE_OPTIONS)" % (spec["key"], got_type))
            continue
        got_opts = livef.get("options")
        if not isinstance(got_opts, list):
            violations.append(
                "%s carries no options list (a picklist field must ship its "
                "options)" % spec["key"])
        elif list(got_opts) != list(spec["options"]):
            violations.append(
                "%s options do not byte-equal the %s picklist in order"
                % (spec["key"], spec["law"]))

    ok = (not missing and not violations)
    detail = ("both dropdowns live as SINGLE_OPTIONS with their exact "
              "picklists in order" if ok else
              "%d missing, %d type/picklist violations"
              % (len(missing), len(violations)))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "location": masked,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "execute": bool(execute),
        "execute_required": True,
        "decision_key": DECISION_KEY,
        "decision_options": list(decision),
        "choice_key": choice_key,
        "choice_options": list(styles),
        "missing": missing,
        "created": sorted(created),
        "violations": violations,
        "detail": detail,
        "fail_closed": {
            "missing_without_execute_stop": True,
            "wrong_type_never_recreated": True,
            "options_byte_exact_in_order": True,
            "decision_law_source": "gate_engine s5_gate actions "
                                   "(byte-exact, 2 options)",
            "choice_law_source": "cover_render.STYLE_NAMES (byte-exact, "
                                 "self-pinned against the field-map options)",
            "note": "a missing dropdown without --execute is a STOP; a live "
                    "dropdown of the wrong type is exit 5 — never a silent "
                    "pass, never a silent re-type."},
    }


# ---------------------------------------------------------------------------
# Verify driver — raises stop/held upward (the CLI maps them to exit codes),
# writes the machine report to stdout, human notes to stderr. READ-ONLY
# unless --execute (Trevor-gated): WITHOUT --execute a missing field is a
# STOP; WITH --execute missing fields are created then read back.
# ---------------------------------------------------------------------------
def verify_live(client, location_id: str, field_map: dict, *,
                execute: bool = False, out=None) -> int:
    """Run the live check and print the ONE JSON report object to stdout.
    Returns the exit code (0/2/3/5); STOP and HELD propagate as raised.

    The Trevor gate is enforced HERE: missing keys without --execute are a
    STOP (exit 2) — the report still prints (operator-verbose, what WOULD be
    created) but nothing is mutated and the exit code refuses. WITH --execute
    missing keys are created at their declared types and re-read before the
    verdict; any remaining missing (a created key that read back absent) or
    type/picklist violation is exit 5."""
    out = out or sys.stderr
    report = check_dropdowns_live(client, location_id, field_map,
                                  execute=execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["ok"]:
        out.write("[dropdown] OK: %s (marker %s, execute %s).\n"
                  % (report["detail"], report["location"],
                     "true" if report["execute"] else "false"))
        return EX_OK
    if report["missing"] and not execute:
        out.write("[dropdown] STOP: %d dropdown key(s) missing live and "
                  "--execute was NOT given (Trevor-gated). Nothing was "
                  "created. Re-run with --execute to create ONLY the missing "
                  "dropdowns at SINGLE_OPTIONS with their exact picklists "
                  "(marker %s).\n"
                  % (len(report["missing"]), report["location"]))
        return EX_STOP
    out.write("[dropdown] FAIL: %s (marker %s).\n"
              % (report["detail"], report["location"]))
    return EX_MISMATCH


def plan(field_map: dict, *, out=None) -> int:
    """Offline plan (no network, no credentials): the two-dropdown contract
    the live check will assert, straight from the field-map + the
    cover_render style law + the gate_engine decision law (the sources of
    truth — never a hardcoded list). One JSON object on stdout. The payload
    is scanned against the credential shape before print: a hit REFUSES the
    surface rather than echo a token."""
    out = out or sys.stderr
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    if total is not None and len(inventory) != total:
        out.write("[dropdown] plan: inventory %d != total_keys %d — "
                  "refusing.\n" % (len(inventory), total))
        return EX_MISMATCH
    styles = _cover_style_names()
    decision = _decision_option_law()
    payload = {
        "contract": PLAN_CONTRACT,
        "schema_version": 1,
        "decision_key": DECISION_KEY,
        "decision_options": list(decision),
        "choice_key": _choice_row(field_map).get("intended_key"),
        "choice_options": _declared_choice_options(field_map),
        "data_type": "SINGLE_OPTIONS (both; options on create)",
        "create": "reg.CafClient.create_custom_field — POST "
                  "/locations/{id}/customFields (Version %s; "
                  "CAF_BROWSER_UA on the request — CF 1010 law) — REFUSED "
                  "without %s"
                  % (reg.CAF_VERSION_HEADER, EXECUTE_FLAG),
        "read": "reg.CafClient.list_custom_fields — GET "
                "/locations/{id}/customFields (Version %s; CAF_BROWSER_UA on "
                "the request — CF 1010 law)" % reg.CAF_VERSION_HEADER,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; the "
                "decision field (PRD Section 4) is deliberately NOT in the "
                "field-map provisioning inventory (U8 note) and is created "
                "by this module's own pinned contract key",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise DropdownError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out.write(dumped)
    out.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# A FAILED self-test is exit 4 (enforced violation), never 'unexpected
# error' — the same discipline the sibling families apply.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the read/write surface
    with a programmable listing and a mutation log (self-tests prove that
    the READ-ONLY path performs zero writes and that the --execute path
    creates exactly the missing keys, then re-reads)."""

    def __init__(self, fields=None, behavior=None):
        self._fields = list(fields) if isinstance(fields, list) else fields
        self.behavior = behavior  # None | scope | edge | transport
        self.calls = []
        self._n = 0

    def list_custom_fields(self, location_id):
        self.calls.append(("fields", location_id))
        self._maybe_raise()
        if isinstance(self._fields, list):
            return [dict(f) for f in self._fields]
        return self._fields

    def create_custom_field(self, location_id, name, data_type, options=None):
        self.calls.append(("create", location_id, name, data_type))
        self._maybe_raise()
        # The real API derives the fieldKey server-side as "contact.<name>"
        # (the engine law: fieldKey = contact. + create_name, the same
        # derivation reg.derive_field_key codifies) — the fake mirrors it so
        # the create-then-read-back path proves the derivation, not a guess.
        fk = reg.derive_field_key(name)
        self._n += 1
        rec = {"fieldKey": fk, "id": "fld_fake_%d" % self._n,
               "name": name, "dataType": data_type}
        if options is not None:
            rec["options"] = list(options)
        self._fields = ([dict(f) for f in self._fields]
                        if isinstance(self._fields, list) else [])
        self._fields.append(rec)
        return dict(rec)

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError(
                "HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: "
                                     "URLError")


def _fake_field_map() -> dict:
    return reg.load_field_map(FIELD_MAP_PATH)


def _golden_fields(field_map: dict, styles: tuple, decision: tuple) -> list:
    """A live listing that carries BOTH dropdown keys as SINGLE_OPTIONS with
    their exact picklists in order — the decision field (the module's own
    contract key, deliberately absent from the field-map) and the U8 cover
    choice at its field-map-derived key."""
    out = []
    i = 0
    for f in _contract_inventory(field_map):
        i += 1
        rec = {"fieldKey": f.get("intended_key"),
               "name": f.get("create_name"),
               "dataType": f.get("data_type", "LARGE_TEXT"),
               "id": "fld_%d" % i}
        if f.get("data_type") == "SINGLE_OPTIONS":
            rec["options"] = list(styles)
        out.append(rec)
    # The decision field rides the module's own contract key (the U8 note
    # excludes it from the inventory by design).
    out.append({"fieldKey": DECISION_KEY, "name": "anthology_review_decision",
                "dataType": "SINGLE_OPTIONS", "id": "fld_decision",
                "options": list(decision)})
    return out


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[dropdown] SELF-TEST FAILED (enforced violation): "
                         "%s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    field_map = _fake_field_map()
    styles = _cover_style_names()
    decision = _decision_option_law()

    # ---- contract coherence: the owning authorities are the shape law -----
    assert DECISION_KEY == "contact.anthology_review_decision", \
        "the decision key contract drifted: %r" % DECISION_KEY
    assert list(decision) == ["approve_as_is", "request_rewrite_with_notes"], \
        "the decision law must be exactly the two gate actions in order: " \
        "%r" % (decision,)
    # The decision key is deliberately NOT in the field-map inventory (U8
    # note) — the self-test pins the exclusion so a later inclusion cannot
    # silently fork the key authority.
    assert DECISION_KEY not in [f.get("intended_key")
                                for f in _contract_inventory(field_map)], \
        "the decision field must stay OUT of the provisioning inventory (U8 " \
        "note) — the key authority is this module's contract"
    total = _contract_total(field_map)
    assert total is not None and len(_contract_inventory(field_map)) == total, \
        "inventory must equal provisioning.total_keys"
    assert _declared_choice_options(field_map) == list(styles), \
        "field-map declared options must byte-equal cover_render.STYLE_NAMES"
    assert list(styles) == ["Signature", "Bold Editorial", "Fine Art",
                            "Pure Type"], \
        "the four named cover styles must be exactly Signature / Bold " \
        "Editorial / Fine Art / Pure Type in order"
    assert _choice_row(field_map)["intended_key"] == \
        "contact.anthology_cover_choice", \
        "the U8 choice key drifted from the field-map: %r" % \
        _choice_row(field_map).get("intended_key")
    assert BROWSER_UA == reg.CAF_BROWSER_UA and \
        "Python-urllib" not in BROWSER_UA, \
        "the browser User-Agent drifted from reg.CAF_BROWSER_UA (CF 1010)"

    # ---- golden live state: EVERYTHING passes (read-only) ----
    golden = _golden_fields(field_map, styles, decision)
    caf = _FakeCaf(fields=golden)
    report = check_dropdowns_live(caf, "loc_fx", field_map)
    assert report["verdict"] == "PASS", "golden: %s" % report["detail"]
    assert report["ok"] is True, "golden report must carry ok: true"
    assert report["decision_key"] == DECISION_KEY
    assert report["decision_options"] == list(decision)
    assert report["choice_key"] == "contact.anthology_cover_choice"
    assert report["choice_options"] == list(styles)
    assert report["missing"] == [] and report["violations"] == []
    assert report["execute"] is False, \
        "read-only path must report execute false"
    assert report["location"] == "...c_fx", \
        "location marker must be masked: %r" % report["location"]

    # full verify_live on the golden state: exit 0, ONE JSON object on stdout
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(caf, "loc_fx", field_map, out=io.StringIO())
    assert rc == EX_OK, "golden verify_live must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True

    # ---- the READ-ONLY path NEVER writes ----
    assert caf.calls and all(m == "fields" for m, _ in caf.calls), \
        "read-only check performed an unexpected call: %s" % caf.calls

    # ---- attack fixtures: every mutation REFUSED / recorded ----
    # 1. the decision field live as TEXT -> FAIL, never a pass
    a1 = copy.deepcopy(golden)
    for rec in a1:
        if rec["fieldKey"] == DECISION_KEY:
            rec["dataType"] = "TEXT"
    report = check_dropdowns_live(_FakeCaf(fields=a1), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "decision-as-TEXT must FAIL"
    assert report["violations"], \
        "a non-SINGLE_OPTIONS live decision must be a violation"

    # 2. the choice field live as TEXT -> FAIL, never a pass
    a2 = copy.deepcopy(golden)
    for rec in a2:
        if rec["fieldKey"] == "contact.anthology_cover_choice":
            rec["dataType"] = "TEXT"
    report = check_dropdowns_live(_FakeCaf(fields=a2), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "choice-as-TEXT must FAIL"

    # 3. the DECISION picklist drifted (reordered / extra / renamed) -> FAIL
    for mutation in (list(reversed(list(decision))),
                     list(decision) + ["Third Action"],
                     [d.replace("approve_as_is", "approve_as_is_2")
                      for d in decision]):
        a3 = copy.deepcopy(golden)
        for rec in a3:
            if rec["fieldKey"] == DECISION_KEY:
                rec["options"] = mutation
        report = check_dropdowns_live(_FakeCaf(fields=a3), "loc_fx", field_map)
        assert report["verdict"] == "FAIL", \
            "drifted decision options must FAIL: %r" % (mutation,)
        assert report["violations"], \
            "drifted decision options must be a violation"

    # 4. the COVER picklist drifted (reordered / extra / renamed) -> FAIL
    for mutation in (list(reversed(list(styles))),
                     list(styles) + ["Fourth Style"],
                     [s.replace("Fine Art", "Fine Arts") for s in styles]):
        a4 = copy.deepcopy(golden)
        for rec in a4:
            if rec["fieldKey"] == "contact.anthology_cover_choice":
                rec["options"] = mutation
        report = check_dropdowns_live(_FakeCaf(fields=a4), "loc_fx", field_map)
        assert report["verdict"] == "FAIL", \
            "drifted choice options must FAIL: %r" % (mutation,)
        assert report["violations"], \
            "drifted choice options must be a violation"

    # 5. picklist MISSING entirely -> FAIL (never a silent pass)
    for key in (DECISION_KEY, "contact.anthology_cover_choice"):
        a5 = copy.deepcopy(golden)
        for rec in a5:
            if rec["fieldKey"] == key:
                del rec["options"]
        report = check_dropdowns_live(_FakeCaf(fields=a5), "loc_fx", field_map)
        assert report["verdict"] == "FAIL", \
            "missing options list must FAIL for %s" % key
        assert report["violations"], "a picklist without options must violate"

    # 6. a dropdown DELETED (strict subset), no --execute -> FAIL; the
    #    driver treats that as the STOP family (exit 2) — never a silent pass
    for key in (DECISION_KEY, "contact.anthology_cover_choice"):
        a6 = [rec for rec in golden if rec["fieldKey"] != key]
        report = check_dropdowns_live(_FakeCaf(fields=a6), "loc_fx", field_map)
        assert report["verdict"] == "FAIL" and report["missing"] == [key], \
            "field-deleted must record the missing key: %r" % key
        caf6 = _FakeCaf(fields=a6)
        buf6 = io.StringIO()
        with contextlib.redirect_stdout(buf6):
            rc6 = verify_live(caf6, "loc_fx", field_map, out=io.StringIO())
        assert rc6 == EX_STOP, \
            "missing dropdown without --execute must exit 2, got %s" % rc6
        assert caf6.calls and all(m == "fields" for m, _ in caf6.calls), \
            "no-execute path must perform ZERO writes: %s" % caf6.calls
        r6 = json.loads(buf6.getvalue())
        assert r6["verdict"] == "FAIL" and r6["missing"] == [key]

    # 7. both dropdowns DELETED WITH --execute: created as SINGLE_OPTIONS
    #    with their exact picklists — never at a guessed type/picklist —
    #    then re-read; exit 0 with execute true on the report
    both = [rec for rec in golden
            if rec["fieldKey"] not in (DECISION_KEY,
                                       "contact.anthology_cover_choice")]
    caf7 = _FakeCaf(fields=both)
    buf7 = io.StringIO()
    with contextlib.redirect_stdout(buf7):
        rc7 = verify_live(caf7, "loc_fx", field_map, execute=True,
                          out=io.StringIO())
    assert rc7 == EX_OK, "--execute create-missing must exit 0, got %s" % rc7
    r7 = json.loads(buf7.getvalue())
    assert r7["ok"] is True and r7["execute"] is True
    assert sorted(r7["created"]) == sorted([DECISION_KEY,
                                            "contact.anthology_cover_choice"]), \
        "created must name the two missing dropdown keys"
    created_types = [c[3] for c in caf7.calls if c[0] == "create"]
    assert created_types == ["SINGLE_OPTIONS", "SINGLE_OPTIONS"], \
        "every dropdown must be created as SINGLE_OPTIONS, got %r" % \
        created_types
    live_decision = next(rec for rec in caf7._fields
                         if rec["fieldKey"] == DECISION_KEY)
    assert live_decision.get("options") == list(decision), \
        "the created decision field must carry the two gate actions in order"
    live_choice = next(rec for rec in caf7._fields
                       if rec["fieldKey"] == "contact.anthology_cover_choice")
    assert live_choice.get("options") == list(styles), \
        "the created choice field must carry the four named styles in order"
    assert caf7.calls[-1][0] == "fields", \
        "--execute path must RE-LIST after creating (read-back verification)"

    # 8. a live wrong-typed dropdown is NEVER re-created or re-typed even
    #    WITH --execute: it is a FAIL (a provisioning decision, never a
    #    silent runtime act)
    a8 = copy.deepcopy(golden)
    for rec in a8:
        if rec["fieldKey"] == DECISION_KEY:
            rec["dataType"] = "TEXT"
    caf8 = _FakeCaf(fields=a8)
    buf8 = io.StringIO()
    with contextlib.redirect_stdout(buf8):
        rc8 = verify_live(caf8, "loc_fx", field_map, execute=True,
                          out=io.StringIO())
    assert rc8 == EX_MISMATCH, \
        "wrong live type must FAIL even with --execute, got %s" % rc8
    assert not any(c[0] == "create" for c in caf8.calls), \
        "a wrong-typed live dropdown must NEVER be re-created: %s" % \
        caf8.calls

    # 9. empty live listing -> FAIL (never a silent pass)
    report = check_dropdowns_live(_FakeCaf(fields=[]), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and \
        sorted(report["missing"]) == sorted([DECISION_KEY,
                                             "contact.anthology_cover_choice"]), \
        "an empty listing must record BOTH dropdowns missing"

    # 10. non-list live read -> hard refusal (never a fabricated list)
    try:
        check_dropdowns_live(_FakeCaf(fields={"not": "a list"}), "loc_fx",
                             field_map)
        raise AssertionError("a non-list read was NOT refused")
    except DropdownError:
        pass

    # 11. map with no provisioning.fields -> hard refusal
    try:
        check_dropdowns_live(_FakeCaf(fields=golden), "loc_fx", {})
        raise AssertionError("missing inventory was NOT refused")
    except DropdownError:
        pass

    # 12. inventory total != contract total_keys -> hard refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        check_dropdowns_live(_FakeCaf(fields=golden), "loc_fx", tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except DropdownError:
        pass

    # 13. field-map options vs cover_render styles drifted -> hard refusal
    tampered2 = copy.deepcopy(field_map)
    for f in tampered2["provisioning"]["fields"]:
        if f.get("data_type") == "SINGLE_OPTIONS":
            f["options"] = ["Drifted", "Options", "List", "Here"]
    try:
        check_dropdowns_live(_FakeCaf(fields=golden), "loc_fx", tampered2)
        raise AssertionError("map-vs-cover_render options drift was NOT "
                             "refused")
    except DropdownError:
        pass

    # 14. the style law unavailable -> StyleImportError (unjudgeable, never a
    #     blind pass)
    try:
        _cover_style_names.__globals__["cvr"].STYLE_NAMES = ()
        try:
            _cover_style_names()
            raise AssertionError("empty STYLE_NAMES was NOT refused")
        except StyleImportError:
            pass
    finally:
        _cover_style_names.__globals__["cvr"].STYLE_NAMES = (
            tuple(s["name"] for s in cvr.COVER_STYLES))
    assert _cover_style_names() == styles, "style law must restore byte-exact"

    # 15. the decision law unavailable -> DecisionImportError (unjudgeable,
    #     never a blind pass)
    saved_cursor = getattr(gate, "GATE_BY_CURSOR", None)
    saved_mirror = getattr(gate, "GATE_DECISION_OPTIONS", None)
    try:
        _decision_option_law.__globals__["gate"].GATE_BY_CURSOR = {}
        _decision_option_law.__globals__["gate"].GATE_DECISION_OPTIONS = ()
        try:
            _decision_option_law()
            raise AssertionError("an unavailable decision law was NOT refused")
        except DecisionImportError:
            pass
    finally:
        if saved_cursor is not None:
            _decision_option_law.__globals__["gate"].GATE_BY_CURSOR = saved_cursor
        else:
            try:
                del _decision_option_law.__globals__["gate"].GATE_BY_CURSOR
            except AttributeError:
                pass
        if saved_mirror is not None:
            _decision_option_law.__globals__["gate"].GATE_DECISION_OPTIONS = saved_mirror
        else:
            try:
                del _decision_option_law.__globals__["gate"].GATE_DECISION_OPTIONS
            except AttributeError:
                pass
    assert _decision_option_law() == decision, \
        "the decision law must restore byte-exact"

    # 16. scope denied on the read -> STOP (exit 2), never a fabricated pass
    try:
        check_dropdowns_live(_FakeCaf(fields=golden, behavior="scope"),
                             "loc_fx", field_map)
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass

    # 17. edge block -> HELD (exit 3), never mislabeled as scope
    try:
        check_dropdowns_live(_FakeCaf(fields=golden, behavior="edge"),
                             "loc_fx", field_map)
        raise AssertionError("edge-block was NOT refused")
    except reg.UpstreamBlockedError:
        pass

    # 18. transport failure -> HELD (exit 3)
    try:
        check_dropdowns_live(_FakeCaf(fields=golden, behavior="transport"),
                             "loc_fx", field_map)
        raise AssertionError("transport failure was NOT refused")
    except reg.CafUnreachable:
        pass

    # ---- the never-print law: no secret-shaped string rides any surface ----
    leak = " ".join(json.dumps(
        check_dropdowns_live(_FakeCaf(fields=golden), "loc_fx", field_map),
        sort_keys=True) + json.dumps(
            plan(field_map, out=io.StringIO()) or {"plan": "ok"},
            sort_keys=True))
    for marker in ("pit_", "Bearer ", "client_secret", "api_key",
                   "sk-", "AKIA", "gcp-service", "private-integration"):
        assert marker not in leak, \
            "the dropdown surface leaked a secret-shaped marker: %r" % marker

    # ---- plan: offline, no network, exact key list ----
    buf_p = io.StringIO()
    rc_p = plan(field_map, out=buf_p)
    assert rc_p == EX_OK, "plan must exit 0"
    p = json.loads(buf_p.getvalue())
    assert p["decision_key"] == DECISION_KEY
    assert p["decision_options"] == list(decision)
    assert p["choice_key"] == "contact.anthology_cover_choice"
    assert p["choice_options"] == list(styles)

    dev.write("[dropdown] self-test: OK (contract: decision "
              "contact.anthology_review_decision 2-option approve_as_is / "
              "request_rewrite_with_notes from gate_engine, choice "
              "contact.anthology_cover_choice 4-style Signature / Bold "
              "Editorial / Fine Art / Pure Type from cover_render + "
              "field-map, both live SINGLE_OPTIONS with byte-exact picklists "
              "in order; golden all-PASS read-only + verify_live exit 0, "
              "no-execute missing STOP exit 2 with zero writes, --execute "
              "create-only-missing at SINGLE_OPTIONS with the exact "
              "picklists then re-read, wrong-type never re-created even with "
              "--execute, 18 attack fixtures refused or FAIL-recorded "
              "(decision-TEXT / choice-TEXT / decision-options-reordered / "
              "decision-options-extra / decision-options-renamed / "
              "choice-options-reordered / choice-options-extra / "
              "choice-options-renamed / options-missing / field-deleted / "
              "both-deleted / empty-listing / non-list-read / no-inventory / "
              "total_keys-drift / map-vs-cover_render drift / "
              "style-law-unavailable / decision-law-unavailable / "
              "scope-denied / edge-block / transport), no-writes on the "
              "read-only path, masked-location, plan offline)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dropdown_module.py",
        description="Create-or-verify the TWO SINGLE_OPTIONS dropdowns of "
                    "the engine's review surface (Skill 59, U08/U09): the "
                    "PRD Section 4 universal-review decision field "
                    "(contact.anthology_review_decision — the two gate "
                    "actions approve_as_is / request_rewrite_with_notes "
                    "from gate_engine) and the U8 cover-style choice field "
                    "(contact.anthology_cover_choice — the four named cover "
                    "styles from cover_render.STYLE_NAMES). Fail-closed. "
                    "Create-only-missing provisioning requires --execute "
                    "explicitly (Trevor-gated).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated: create ONLY missing dropdowns at "
                         "SINGLE_OPTIONS with their exact picklists, then "
                         "re-list and re-verify. Without this flag a missing "
                         "dropdown is a STOP (exit 2). Never re-creates or "
                         "re-types a live field.")
    ap.add_argument("cmd", nargs="?", choices=["apply", "plan", "self-test"],
                    default="apply")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling verifiers use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan(field_map)

        # ---- live apply (dry-run unless --execute) ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN location-scoped pit- token and "
                       "re-run."])
            return EX_STOP
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[dropdown] PIT resolved via %s (SET). Location via "
                         "%s (marker %s). execute=%s.\n"
                         % (pit_label, loc_label, reg._mask_location(loc),
                            "true" if args.execute else "false"))
        client = reg.CafClient(token)
        return verify_live(client, loc, field_map, execute=args.execute,
                           out=sys.stderr)

    except DropdownError as exc:
        sys.stderr.write("[dropdown] STOP: %s\n" % exc)
        return EX_STOP
    except StyleImportError as exc:
        sys.stderr.write("[dropdown] STOP: %s\n" % exc)
        return EX_STOP
    except DecisionImportError as exc:
        sys.stderr.write("[dropdown] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[dropdown] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[dropdown] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[dropdown] HELD: %s\n" % exc)
        return EX_HELD
    except FileNotFoundError as exc:
        sys.stderr.write("[dropdown] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[dropdown] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
