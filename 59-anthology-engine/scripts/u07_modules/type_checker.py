#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/type_checker.py  (U07 tooling)
# LIVE FIELD-TYPE CHECKER — for a given Convert and Flow location, assert that
# EVERY free-text field in config/field-map.json provisioning.fields is LIVE
# LARGE_TEXT (Trevor's every-text-input-field-is-multi-line law; the field-map's
# data_type_choice note) and that the ONE SINGLE_OPTIONS field in the inventory
# (the U8 cover choice, anthology_cover_choice) is live with EXACTLY the four
# named cover-style options, byte-exact, in order.
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# package. It is NOT a manifest row (no ENGINE-MANIFEST row exists for it yet
# and this file NEVER touches the manifest): it ships as a sibling helper the
# way u02_modules/fields_check.py and delivery_report.py do (ENGINE-MANIFEST
# row 12 pattern), imported BY NAME as u07_modules.type_checker per the
# u07_modules package contract (__init__.py: pure namespace container,
# fail-closed empty init, side-effect free at import). Standalone invocation
# works too: the SAME sys.path.insert bootstrap the sibling imports use
# resolves anthology_registry from scripts/.
#
# WHAT THIS OWNS (live, fail-closed, READ-ONLY unless --execute):
#   1. THE LARGE_TEXT LAW. The field-map declares LARGE_TEXT for all
#      twenty-seven free-text keys (PRD Gap G11 reconciliation; U10
#      rewrite-preservation + U8 cover-style; field-map data_type_choice):
#      the eight base deliverable Doc/PDF pairs, the two chapter-rewrite
#      pairs, the three control keys, and the four U8 cover sample-url keys.
#      Live Convert and Flow provisions every free-text field as LARGE_TEXT,
#      and Trevor's every-text-input-field-is-multi-line law requires it.
#      A live field whose dataType is NOT LARGE_TEXT (TEXT, PHONE, or any
#      other byte) is a VIOLATION of that law — never a silent pass.
#   2. THE SINGLE_OPTIONS CHOICE LAW. The inventory's ONE SINGLE_OPTIONS
#      field — anthology_cover_choice (the U8 cover choice) — must be live
#      as SINGLE_OPTIONS with EXACTLY the four named style options the client
#      picks from in the universal-review cover dropdown. The four names are
#      NOT hardcoded: the picklist is imported byte-exact from
#      scripts/cover_render.py COVER_STYLES/STYLE_NAMES (the engine's named
#      style law: Signature, Bold Editorial, Fine Art, Pure Type — one of
#      them strictly typography-driven), and the module pins that import
#      byte-exact against the field-map's own declared options in order, so
#      the two surfaces can never drift apart. Any missing / extra /
#      reordered / byte-drifted option is a violation.
#   3. THE SAMPLE-URL SLOT LAW. The four sample1..4 LARGE_TEXT fields are
#      matched to the four style names in cover_render.py order — slot 1 is
#      the FIRST declared style, slot 4 the LAST — the same order the U8
#      provision note pins. A style order change in cover_render.py without a
#      matching sample-slot meaning is caught by the coherence self-test.
#   4. CREATE-ONLY-MISSING PROVISION, Trevor-gated. Creating a missing field
#      is a WRITE: it requires --execute explicitly (the Trevor gate). Without
#      --execute a missing field is a STOP (exit 2) — never a silent no-op,
#      never an auto-create. WITH --execute the module creates each missing
#      field at its DECLARED data_type (LARGE_TEXT for every free-text key,
#      SINGLE_OPTIONS with the four options for the cover choice — exactly
#      the registry's create_custom_field surface) and then RE-LISTS and
#      re-verifies in the same job, so a report never claims a type that was
#      not read back. The report states execute true/false explicitly on every
#      run. A live field of the WRONG type is NEVER silently re-created or
#      re-typed (changing a live field's dataType is a provisioning decision,
#      never a silent runtime act; field-map resolution_rule): it is a FAIL.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / __init__.py):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds no credential value at any point — the client
#     object is resolved by the caller's label machinery.
#   - Browser UA on every request: the engine's own LeadConnector v2 client
#     (reg.CafClient) already sends CAF_BROWSER_UA — a public browser
#     User-Agent string — on EVERY request (the proven CF-1010 edge fix;
#     urllib's default "Python-urllib/x.y" is 403'd at the WAF edge). No
#     request is ever made without it.
#   - Fail-closed: a malformed field-map section, an absent section, a
#     non-list live read, a drifted options contract, a map-vs-cover_render
#     options mismatch all STOP or FAIL — never a blind pass, never a
#     fabricated success.
#   - Scope vs edge discrimination on every read (bare 401/403 is HELD, never
#     mislabeled as a scope problem) — inherited from reg.CafClient.
#   - Move in silence; operator-verbose only. Nothing Anthropic in any
#     runtime file. Convert and Flow naming in every client surface.
#
# EXIT CODE CONTRACT (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — every free-text key live LARGE_TEXT, the choice
#      field live SINGLE_OPTIONS with the exact four options in order (and,
#      with --execute, any missing fields created then read back); also
#      self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON is a STOP, not 1)
#   2  STOP — field-map has no provisioning.fields inventory (or the contract
#      total_keys does not match the inventory), a strict subset of the
#      intended keys is missing live and --execute was NOT given (the Trevor
#      gate; with --execute missing fields are created and re-read), the
#      cover_render style import failed, the map-vs-cover_render options
#      contract drifted, or PIT / location NOT SET
#   3  HELD — Convert and Flow unreachable (transport) or an upstream/edge
#      block (CF 1010); retryable, never mislabeled as scope
#   4  self-test FAILED (enforced violation detected — a tamper NEVER
#      masquerades as exit 1)
#   5  mismatch — a live free-text field's dataType is not LARGE_TEXT, the
#      choice field's dataType is not SINGLE_OPTIONS, its live options do not
#      byte-equal the four named styles in order, or (--execute path) a
#      created field read back drifted
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr):
#   type_checker.py plan                      # offline: the 28-key contract
#   type_checker.py verify [--location-id X]  # live read-only; a missing
#                                             # field is a STOP without --execute
#   type_checker.py verify --execute          # Trevor-gated: create-only-missing
#                                             # then read back and re-verify
#   type_checker.py self-test                 # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# other u0X_modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""type_checker.py — live field-TYPE checker for the field-map's 28 keys (U07).

Every free-text field must be live LARGE_TEXT; the ONE SINGLE_OPTIONS field
(the U8 cover choice) must carry exactly the four named cover styles.
Imported BY NAME as u07_modules.type_checker per the u07_modules package
contract (__init__.py: pure namespace container). Never prints a token.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring + the LeadConnector client + the credential
# label resolution — the module reuses them, never re-implements. The style
# name import (the named-style law) lives in scripts/cover_render.py — the
# engine's cover adapter, imported FOR CONSTANTS ONLY (STYLE_NAMES); its
# self-test runs only under `python cover_render.py`, never at import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import cover_render as cvr  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The Trevor gate: --execute is the ONLY flag that authorizes the create-only-
# missing write path. Without it a missing field is a STOP, never a silent
# no-op and never an auto-create (the same explicit-execute doctrine the U06
# archive verifier enforces for its ACTION).
EXECUTE_FLAG = "--execute"

# The one fixed report contract. Byte-exact intended keys and declared types
# come from the field-map; the named style options come from cover_render —
# nothing is hardcoded here (a hardcoded list would drift and the whole point
# is the field-map + cover_render are the SINGLE SOURCES OF TRUTH).
REPORT_CONTRACT = "anthology-engine-type-check"
PLAN_CONTRACT = REPORT_CONTRACT + "-plan"


class TypeCheckError(Exception):
    """A fail-closed verification refusal (STOP or mismatch family)."""


class StyleImportError(Exception):
    """The cover_render style-name law is unavailable — refusing to judge a
    choice-field contract we cannot read (never a blind pass)."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise TypeCheckError(
            "field-map.json has no provisioning.fields inventory — the "
            "type-check gate has nothing to assert; refusing a blind pass.")
    return [f for f in fields if isinstance(f, dict)]


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _mask_location(loc: str) -> str:
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# Style-name law: the four named cover styles, byte-exact, cover_render-order
# ---------------------------------------------------------------------------
def named_cover_styles() -> tuple:
    """The four named cover styles in cover_render.py STYLE_NAMES order —
    the byte-exact names the client picks from in the universal-review cover
    dropdown (the U8 choice field's picklist). Raises StyleImportError when
    the law is unavailable or not exactly four distinct names: the choice
    contract cannot be judged against an unavailable or drifted surface."""
    names = tuple(getattr(cvr, "STYLE_NAMES", ()) or ())
    if not names or len(names) != 4 or len(set(names)) != 4:
        raise StyleImportError(
            "cover_render.STYLE_NAMES did not resolve to exactly four distinct "
            "names — the U8 choice contract is unjudgeable; refusing a blind "
            "pass.")
    if not all(isinstance(n, str) and n.strip() for n in names):
        raise StyleImportError(
            "cover_render.STYLE_NAMES carries a blank/non-string entry — the "
            "style-name law is drifted; refusing a blind pass.")
    return names


def _declared_choice_options(field_map: dict) -> list:
    """The field-map's declared options for the SINGLE_OPTIONS inventory row.
    Raises TypeCheckError when the declared options do not exist — a choice
    field without a picklist is a contradiction the map must never carry."""
    for f in _contract_inventory(field_map):
        if (f.get("data_type") or "") == "SINGLE_OPTIONS":
            opts = f.get("options")
            if not isinstance(opts, list) or not opts:
                raise TypeCheckError(
                    "field-map SINGLE_OPTIONS row %r carries no options — the "
                    "choice picklist law is unjudgeable; refusing a blind pass."
                    % (f.get("intended_key") or "?"))
            return list(opts)
    raise TypeCheckError(
        "field-map provisioning.fields carries no SINGLE_OPTIONS row — the "
        "U8 cover-choice law is unjudgeable; refusing a blind pass.")


def _choice_row(field_map: dict) -> dict:
    for f in _contract_inventory(field_map):
        if (f.get("data_type") or "") == "SINGLE_OPTIONS":
            return f
    raise TypeCheckError(
        "field-map provisioning.fields carries no SINGLE_OPTIONS row — the "
        "U8 cover-choice law is unjudgeable; refusing a blind pass.")


# ---------------------------------------------------------------------------
# The check — returns the machine report dict; raises on STOP / HELD /
# fail-closed refusal. NEVER prints a token (it holds none: credentials are
# resolved by the caller's label machinery, SET / NOT SET only).
# ---------------------------------------------------------------------------
def _collect_live(live_fields) -> dict:
    """Index live custom-field records by fieldKey. Fail-closed: an empty /
    non-list read is a refusal, never a silent pass."""
    if not isinstance(live_fields, list):
        raise TypeCheckError(
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


def check_types_live(client, location_id: str, field_map: dict,
                     *, execute: bool = False,
                     expected_styles=None) -> dict:
    """Live field-TYPE check (the 27 LARGE_TEXT law + the ONE SINGLE_OPTIONS
    choice law) with the Trevor-gated create-only-missing path. Returns the
    report dict; raises TypeCheckError (STOP family) or reg.ScopeDenied /
    reg.UpstreamBlockedError / reg.CafUnreachable (HELD family) upward —
    exactly the propagation the sibling verifier's driver uses.

    With execute=True, each MISSING free-text key is created at its declared
    LARGE_TEXT data_type and the missing choice field at SINGLE_OPTIONS with
    the four named style options, then the location is RE-LISTED and every
    created key is re-verified against the read-back — a report never claims
    a type that was not read back. A live field of the WRONG type is never
    re-created and never re-typed: it is a FAIL (a provisioning decision,
    never a silent runtime act)."""
    masked = _mask_location(location_id)
    styles = expected_styles if expected_styles is not None else named_cover_styles()

    inventory = _contract_inventory(field_map)
    want_keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
    total = _contract_total(field_map)
    if total is not None and len(want_keys) != total:
        raise TypeCheckError(
            "field-map provisioning.fields carries %d intended keys but the "
            "provisioning.total_keys contract says %d — the field-map drifted "
            "from its own contract; refusing to judge against a self-contradicting "
            "map." % (len(want_keys), total))
    if not want_keys:
        raise TypeCheckError(
            "field-map provisioning.fields carries no intended_key entries — "
            "refusing a blind pass.")

    declared = {}
    for f in inventory:
        key = f.get("intended_key")
        if key:
            declared[key] = f
    text_rows = [f for f in inventory
                 if (f.get("data_type") or "") == "LARGE_TEXT"]
    choice = _choice_row(field_map)
    choice_key = choice.get("intended_key") or ""
    declared_options = _declared_choice_options(field_map)
    if list(declared_options) != list(styles):
        raise TypeCheckError(
            "field-map declared options for %r do not byte-equal "
            "cover_render.STYLE_NAMES in order — the choice picklist drifted "
            "from the style-name law; refusing to judge (never a blind pass)."
            % choice_key)

    if len(text_rows) + 1 != len(want_keys):
        raise TypeCheckError(
            "field-map inventory does not resolve to exactly 27 LARGE_TEXT "
            "rows + 1 SINGLE_OPTIONS row (got %d text rows for %d keys) — the "
            "type contract drifted; refusing a blind pass."
            % (len(text_rows), len(want_keys)))

    live = _collect_live(client.list_custom_fields(location_id))
    created = []
    if execute:
        # Trevor-gated create-only-missing: create each ABSENT key at its
        # declared data_type, then the whole location is re-listed below and
        # every created key is verified against the read-back.
        for key in want_keys:
            if key in live:
                continue
            f = declared[key]
            opts = list(styles) if (f.get("data_type") or "") == "SINGLE_OPTIONS" else None
            client.create_custom_field(location_id, f.get("create_name") or "",
                                       f.get("data_type") or "LARGE_TEXT",
                                       options=opts)
            created.append(key)
        if created:
            live = _collect_live(client.list_custom_fields(location_id))

    missing = sorted(set(want_keys) - set(live))
    violations = []
    for key in want_keys:
        livef = live.get(key)
        if livef is None:
            continue  # counted under `missing` above
        want_type = declared[key].get("data_type") or ""
        got_type = livef.get("dataType")
        if want_type == "SINGLE_OPTIONS":
            if got_type != "SINGLE_OPTIONS":
                violations.append("%s dataType %r != SINGLE_OPTIONS"
                                  % (key, got_type))
            got_opts = livef.get("options")
            if not isinstance(got_opts, list):
                violations.append("%s carries no options list (a picklist "
                                  "field must ship its options)"
                                  % key)
            elif list(got_opts) != list(styles):
                violations.append("%s options do not byte-equal the four "
                                  "named cover styles in order"
                                  % key)
        else:
            if got_type != want_type:
                violations.append("%s dataType %r != LARGE_TEXT (the "
                                  "every-text-input-field-is-multi-line law)"
                                  % (key, got_type))

    ok = (not missing and not violations)
    detail = "all %d keys live at their declared types" % len(want_keys) if ok else (
        "%d missing, %d type/options violations" % (len(missing), len(violations)))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "location": masked,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "execute": bool(execute),
        "execute_required": True,
        "total": len(want_keys),
        "text_keys": len(text_rows),
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
            "style_law_source": "cover_render.STYLE_NAMES (byte-exact, "
                                "self-pinned against the field-map options)",
            "note": "a missing key without --execute is a STOP; a live field "
                    "of the wrong type is exit 5 — never a silent pass, never "
                    "a silent re-type."},
    }


# ---------------------------------------------------------------------------
# Verify driver — raises stop/held upward (the CLI maps them to exit codes),
# writes the machine report to stdout, human notes to stderr. READ-ONLY
# unless --execute (Trevor-gated): WITHOUT --execute a missing field is a
# STOP; WITH --execute missing fields are created then read back.
# ---------------------------------------------------------------------------
def verify_live(client, location_id: str, field_map: dict, *, execute: bool = False,
                out=None) -> int:
    """Run the live check and print the ONE JSON report object to stdout.
    Returns the exit code (0/2/3/5); STOP and HELD propagate as raised.

    The Trevor gate is enforced HERE: missing keys without --execute are a
    STOP (exit 2) — the report still prints (operator-verbose, what WOULD be
    created) but nothing is mutated and the exit code refuses. WITH --execute
    missing keys are created at their declared types and re-read before the
    verdict; any remaining missing (a created key that read back absent) or
    type/options violation is exit 5."""
    out = out or sys.stderr
    report = check_types_live(client, location_id, field_map, execute=execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["ok"]:
        out.write("[type-check] OK: %s (marker %s, execute %s).\n"
                  % (report["detail"], report["location"],
                     "true" if report["execute"] else "false"))
        return EX_OK
    if report["missing"] and not execute:
        out.write("[type-check] STOP: %d intended key(s) missing live and "
                  "--execute was NOT given (Trevor-gated). Nothing was "
                  "created. Re-run with --execute to create ONLY the missing "
                  "fields at their declared types (marker %s).\n"
                  % (len(report["missing"]), report["location"]))
        return EX_STOP
    out.write("[type-check] FAIL: %s (marker %s).\n"
              % (report["detail"], report["location"]))
    return EX_MISMATCH


def plan(field_map: dict, *, out=None) -> int:
    """Offline plan (no network, no credentials): the 28-key type contract the
    live check will assert, straight from the field-map + the cover_render
    style law (the sources of truth — never a hardcoded list). One JSON
    object on stdout."""
    out = out or sys.stderr
    inventory = _contract_inventory(field_map)
    keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
    total = _contract_total(field_map)
    if total is not None and len(keys) != total:
        out.write("[type-check] plan: inventory %d != total_keys %d — refusing.\n"
                  % (len(keys), total))
        return EX_MISMATCH
    text_keys = [k for k in keys
                 if (next((f for f in inventory
                           if f.get("intended_key") == k), {}) or {}
                     ).get("data_type") == "LARGE_TEXT"]
    print(json.dumps({
        "contract": PLAN_CONTRACT,
        "schema_version": 1,
        "total": len(keys),
        "text_keys": len(text_keys),
        "choice_key": _choice_row(field_map).get("intended_key"),
        "choice_options": _declared_choice_options(field_map),
        "keys": keys,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# A FAILED self-test is exit 4 (enforced violation), never 'unexpected error'.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the read/write surface with
    a programmable listing and a mutation log (self-tests prove that the
    READ-ONLY path performs zero writes and that the --execute path creates
    exactly the missing keys, then re-reads)."""

    def __init__(self, fields=None, behavior=None, key_mangler=None):
        # Keep the raw read payload (a list of records, or an attack-shape
        # non-list) so the fail-closed read-shape check sees exactly what a
        # live read would return.
        self._fields = list(fields) if isinstance(fields, list) else fields
        self.behavior = behavior  # None | scope | edge | transport
        self.key_mangler = key_mangler
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
        fk = self.key_mangler(name) if self.key_mangler else reg.derive_field_key(name)
        self._n += 1
        rec = {"fieldKey": fk, "id": "fld_fake_%d" % self._n,
               "name": name, "dataType": data_type}
        if options is not None:
            rec["options"] = list(options)
        self._fields = [dict(f) for f in self._fields] if isinstance(self._fields, list) else []
        self._fields.append(rec)
        return dict(rec)

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")


def _fake_field_map():
    return reg.load_field_map(FIELD_MAP_PATH)


def _golden_fields(field_map: dict, styles: tuple) -> list:
    """A live listing that EXACTLY matches the map's intended keys at their
    declared types — with the choice field carrying the four named style
    options in order and resolved field ids."""
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
    return out


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[type-check] SELF-TEST FAILED "
                         "(enforced violation): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    field_map = _fake_field_map()
    want_keys = [f.get("intended_key")
                 for f in _contract_inventory(field_map) if f.get("intended_key")]
    styles = named_cover_styles()

    # ---- contract coherence: the map and cover_render are the sources ----
    assert want_keys, "field-map must carry intended keys"
    total = _contract_total(field_map)
    assert total is not None and len(want_keys) == total, \
        "inventory must equal provisioning.total_keys (%s != %s)" % (len(want_keys), total)
    assert all(k.startswith("contact.") for k in want_keys), \
        "every intended key must carry the contact. prefix"
    assert len(set(want_keys)) == len(want_keys), "intended keys must be unique"

    text_rows = [f for f in _contract_inventory(field_map)
                 if f.get("data_type") == "LARGE_TEXT"]
    choice_rows = [f for f in _contract_inventory(field_map)
                   if f.get("data_type") == "SINGLE_OPTIONS"]
    assert len(text_rows) == 27 and len(choice_rows) == 1, \
        "the type contract must be exactly 27 LARGE_TEXT + 1 SINGLE_OPTIONS " \
        "(got %d text / %d choice)" % (len(text_rows), len(choice_rows))
    assert _declared_choice_options(field_map) == list(styles), \
        "field-map declared options must byte-equal cover_render.STYLE_NAMES"
    assert list(styles) == ["Signature", "Bold Editorial", "Fine Art", "Pure Type"], \
        "the four named cover styles must be exactly Signature / Bold Editorial / " \
        "Fine Art / Pure Type in order"
    from cover_render import STYLE_KEYS  # noqa: F401
    # the sample-url slot law: sample1..4 fields pair with the four styles in
    # style order (the same order the U8 provision note pins)
    sample_keys = [f.get("intended_key") for f in _contract_inventory(field_map)
                   if f.get("slot") in ("sample1", "sample2", "sample3", "sample4")]
    assert len(sample_keys) == 4, "exactly four sample-url keys required"
    for slot, key in zip(("sample1", "sample2", "sample3", "sample4"), sample_keys):
        assert key == "contact.anthology_cover_%s_url" % slot, \
            "sample-url keys must pair 1:1 with slots in order (got %r)" % key

    # ---- golden live state: EVERYTHING passes (read-only) ----
    golden = _golden_fields(field_map, styles)
    caf = _FakeCaf(fields=golden)
    report = check_types_live(caf, "loc_fx", field_map)
    assert report["verdict"] == "PASS", "golden: %s" % report["detail"]
    assert report["ok"] is True, "golden report must carry ok: true"
    assert report["total"] == len(want_keys) == 28
    assert report["text_keys"] == 27
    assert report["choice_key"] == "contact.anthology_cover_choice"
    assert report["choice_options"] == list(styles)
    assert report["missing"] == [] and report["violations"] == []
    assert report["execute"] is False, "read-only path must report execute false"
    assert report["location"] == "...c_fx", "location marker must be masked: %r" % report["location"]

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
    # 1. a free-text field live as TEXT (not LARGE_TEXT) -> FAIL (exit 5
    #    family) — the multi-line law, never a pass
    a1 = copy.deepcopy(golden)
    for rec in a1:
        if rec["fieldKey"].startswith("contact.anthology_avatar_doc_url"):
            rec["dataType"] = "TEXT"
    report = check_types_live(_FakeCaf(fields=a1), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "live TEXT must FAIL"
    assert report["violations"], "a non-LARGE_TEXT live type must be a violation"

    # 2. the choice field live as TEXT -> FAIL, never a pass
    a2 = copy.deepcopy(golden)
    for rec in a2:
        if rec["fieldKey"] == "contact.anthology_cover_choice":
            rec["dataType"] = "TEXT"
    report = check_types_live(_FakeCaf(fields=a2), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "choice-as-TEXT must FAIL"

    # 3. choice options drifted (reordered / extra / renamed) -> FAIL
    for mutation in (list(reversed(list(styles))),
                     list(styles) + ["Fourth Style"],
                     [s.replace("Fine Art", "Fine Arts") for s in styles]):
        a3 = copy.deepcopy(golden)
        for rec in a3:
            if rec["fieldKey"] == "contact.anthology_cover_choice":
                rec["options"] = mutation
        report = check_types_live(_FakeCaf(fields=a3), "loc_fx", field_map)
        assert report["verdict"] == "FAIL", \
            "drifted choice options must FAIL: %r" % (mutation,)
        assert report["violations"], "drifted options must be a violation"

    # 4. choice options MISSING entirely -> FAIL
    a4 = copy.deepcopy(golden)
    for rec in a4:
        if rec["fieldKey"] == "contact.anthology_cover_choice":
            del rec["options"]
    report = check_types_live(_FakeCaf(fields=a4), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "missing options list must FAIL"

    # 5. field DELETED (strict subset), no --execute -> FAIL; the driver
    #    treats that as the STOP family (exit 2) — never a silent pass
    a5 = copy.deepcopy(golden)[1:]
    report = check_types_live(_FakeCaf(fields=a5), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and report["missing"] == [want_keys[0]], \
        "field-deleted must record the missing key"
    caf5 = _FakeCaf(fields=a5)
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        rc5 = verify_live(caf5, "loc_fx", field_map, out=io.StringIO())
    assert rc5 == EX_STOP, "missing field without --execute must exit 2, got %s" % rc5
    assert caf5.calls and all(m == "fields" for m, _ in caf5.calls), \
        "no-execute path must perform ZERO writes: %s" % caf5.calls
    r5 = json.loads(buf5.getvalue())
    assert r5["verdict"] == "FAIL" and r5["missing"] == [want_keys[0]]

    # 6. field DELETED WITH --execute: created at its DECLARED type, then the
    #    re-read is verified — exit 0 with execute true on the report
    caf6 = _FakeCaf(fields=a5)
    buf6 = io.StringIO()
    with contextlib.redirect_stdout(buf6):
        rc6 = verify_live(caf6, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc6 == EX_OK, "--execute create-missing must exit 0, got %s" % rc6
    r6 = json.loads(buf6.getvalue())
    assert r6["ok"] is True and r6["execute"] is True
    assert r6["created"] == [want_keys[0]], "created must name the missing key"
    created_types = [c[3] for c in caf6.calls if c[0] == "create"]
    assert created_types == ["LARGE_TEXT"], \
        "the missing field must be created at its declared type, got %r" % created_types
    assert caf6.calls[-1][0] == "fields", \
        "--execute path must RE-LIST after creating (read-back verification)"

    # 7. choice field deleted WITH --execute: created as SINGLE_OPTIONS with
    #    the four named style options — never at a guessed type/picklist
    golden_minus_choice = [rec for rec in golden
                           if rec["fieldKey"] != "contact.anthology_cover_choice"]
    caf7 = _FakeCaf(fields=golden_minus_choice)
    buf7 = io.StringIO()
    with contextlib.redirect_stdout(buf7):
        rc7 = verify_live(caf7, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc7 == EX_OK, "--execute choice create must exit 0, got %s" % rc7
    create_calls = [c for c in caf7.calls if c[0] == "create"]
    assert len(create_calls) == 1
    assert create_calls[0][2] == "anthology_cover_choice"
    assert create_calls[0][3] == "SINGLE_OPTIONS", \
        "the choice field must be created as SINGLE_OPTIONS"
    live_choice = next(rec for rec in caf7._fields
                       if rec["fieldKey"] == "contact.anthology_cover_choice")
    assert live_choice.get("options") == list(styles), \
        "the created choice field must carry the four named styles in order"

    # 8. a live wrong-typed field is NEVER re-created or re-typed even WITH
    #    --execute: it is a FAIL (a provisioning decision, never a silent
    #    runtime act)
    a8 = copy.deepcopy(golden)
    for rec in a8:
        if rec["fieldKey"].startswith("contact.anthology_tone_doc_url"):
            rec["dataType"] = "TEXT"
    caf8 = _FakeCaf(fields=a8)
    buf8 = io.StringIO()
    with contextlib.redirect_stdout(buf8):
        rc8 = verify_live(caf8, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc8 == EX_MISMATCH, "wrong live type must FAIL even with --execute, got %s" % rc8
    assert not any(c[0] == "create" for c in caf8.calls), \
        "a wrong-typed live field must NEVER be re-created: %s" % caf8.calls

    # 9. empty live listing without --execute -> FAIL (never a silent pass)
    report = check_types_live(_FakeCaf(fields=[]), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and len(report["missing"]) == total, \
        "empty live listing must fail closed"

    # 10. non-list live read -> hard refusal (TypeCheckError)
    try:
        check_types_live(_FakeCaf(fields={"not": "a list"}), "loc_fx", field_map)
        raise AssertionError("non-list read was NOT refused")
    except TypeCheckError:
        pass

    # 11. map with no provisioning.fields -> hard refusal
    try:
        check_types_live(_FakeCaf(fields=golden), "loc_fx", {})
        raise AssertionError("missing inventory was NOT refused")
    except TypeCheckError:
        pass

    # 12. inventory total != contract total_keys -> hard refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        check_types_live(_FakeCaf(fields=golden), "loc_fx", tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except TypeCheckError:
        pass

    # 13. field-map options vs cover_render styles drifted -> hard refusal
    tampered2 = copy.deepcopy(field_map)
    for f in tampered2["provisioning"]["fields"]:
        if f.get("data_type") == "SINGLE_OPTIONS":
            f["options"] = ["Drifted", "Options", "List", "Here"]
    try:
        check_types_live(_FakeCaf(fields=golden), "loc_fx", tampered2)
        raise AssertionError("map-vs-cover_render options drift was NOT refused")
    except TypeCheckError:
        pass

    # 14. the style law unavailable -> StyleImportError (unjudgeable, never a
    #     blind pass) — prove the guard discriminates an import failure
    #     without touching the real module state
    try:
        named_cover_styles.__globals__["cvr"].STYLE_NAMES = ()
        try:
            named_cover_styles()
            raise AssertionError("empty STYLE_NAMES was NOT refused")
        except StyleImportError:
            pass
    finally:
        named_cover_styles.__globals__["cvr"].STYLE_NAMES = (
            tuple(s["name"] for s in cvr.COVER_STYLES))
    assert named_cover_styles() == styles, "style law must restore byte-exact"

    # 15. scope denied on the read -> STOP (exit 2), never a fabricated pass
    try:
        check_types_live(_FakeCaf(fields=golden, behavior="scope"), "loc_fx", field_map)
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass

    # 16. edge block -> HELD (exit 3), never mislabeled as scope
    try:
        check_types_live(_FakeCaf(fields=golden, behavior="edge"), "loc_fx", field_map)
        raise AssertionError("edge-block was NOT refused")
    except reg.UpstreamBlockedError:
        pass

    # 17. transport failure -> HELD (exit 3)
    try:
        check_types_live(_FakeCaf(fields=golden, behavior="transport"), "loc_fx", field_map)
        raise AssertionError("transport failure was NOT refused")
    except reg.CafUnreachable:
        pass

    # ---- plan: offline, no network, exact key list ----
    buf_p = io.StringIO()
    with contextlib.redirect_stdout(buf_p):
        rc_p = plan(field_map, out=io.StringIO())
    assert rc_p == EX_OK, "plan must exit 0"
    p = json.loads(buf_p.getvalue())
    assert p["keys"] == want_keys, "plan must list the intended keys in order"
    assert p["choice_key"] == "contact.anthology_cover_choice"
    assert p["choice_options"] == list(styles), \
        "plan must carry the four named styles in order"

    dev.write("type_checker self-test: OK (contract 27 LARGE_TEXT + 1 "
              "SINGLE_OPTIONS, golden all-PASS read-only + verify_live exit 0, "
              "no-execute missing STOP exit 2 with zero writes, --execute "
              "create-only-missing at declared type then re-read, wrong-type "
              "never re-created even with --execute, 4 named styles byte-exact "
              "Signature / Bold Editorial / Fine Art / Pure Type in order, "
              "17 attack fixtures refused or FAIL-recorded (live-TEXT / "
              "choice-TEXT / options reordered / options extra / options "
              "renamed / options missing / field-deleted / empty-listing / "
              "non-list-read / no-inventory / total_keys-drift / "
              "map-vs-cover_render drift / style-law-unavailable / "
              "scope-denied / edge-block / transport), no-writes on the "
              "read-only path, masked-location, plan offline)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="type_checker.py",
        description="Live field-TYPE check of the field-map's 28 contact "
                    "custom fields on a Convert and Flow location (U07 "
                    "tooling, Skill 59): every free-text field live "
                    "LARGE_TEXT, the ONE SINGLE_OPTIONS choice field live "
                    "with exactly the four named cover styles in order. "
                    "Fail-closed. Create-only-missing provisioning requires "
                    "--execute explicitly (Trevor-gated).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated: create ONLY missing fields at their "
                         "declared types, then re-list and re-verify. Without "
                         "this flag a missing field is a STOP (exit 2). "
                         "Never re-creates or re-types a live field.")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    default="verify")

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

        # ---- live verify ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN location-scoped pit- token and re-run."])
            return EX_STOP
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[type-check] PIT resolved via %s (SET). Location via "
                         "%s (marker %s). execute=%s.\n"
                         % (pit_label, loc_label, reg._mask_location(loc),
                            "true" if args.execute else "false"))
        client = reg.CafClient(token)
        return verify_live(client, loc, field_map, execute=args.execute,
                           out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[type-check] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[type-check] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[type-check] HELD: %s\n" % exc)
        return EX_HELD
    except TypeCheckError as exc:
        sys.stderr.write("[type-check] STOP: %s\n" % exc)
        return EX_STOP
    except StyleImportError as exc:
        sys.stderr.write("[type-check] STOP: %s\n" % exc)
        return EX_STOP
    except FileNotFoundError as exc:
        sys.stderr.write("[type-check] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[type-check] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
