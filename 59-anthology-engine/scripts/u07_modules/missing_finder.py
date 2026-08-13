#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/missing_finder.py  (U07 tooling)
# MISSING-FIELD FINDER — GET-check-by-name, list missing fields, and
# idempotent create-or-verify. For a given Convert and Flow location, this
# module READS the live custom-fields listing (ONE GET through the engine's
# own LeadConnector client) and reports, against config/field-map.json
# provisioning.fields (the SINGLE SOURCE OF TRUTH, never a hardcoded list):
#   * PRESENT  — intended keys carried live by a byte-equal server fieldKey,
#   * MISSING  — intended keys with no live field under their derived key
#     AND no live field under their create name (the finder's payload),
#   * DRIFT    — a live field whose name equals an intended create_name but
#     whose fieldKey does NOT derive to that intended key (a name squat:
#     the field exists under the wrong key, so creating by name would
#     collide or derive a wrong key — never counted as missing, never
#     silently created; a human-fix drift, the AF-AE-FIELD-KEY-MISMATCH
#     family).
# With the operator's explicit --execute (Trevor-gated), the module then
# CREATES each missing field by name (create_name, the derivation-law input)
# and reads the server-returned fieldKey back byte-for-byte against the
# intended key — idempotent create-or-verify: a re-run over the healed
# location finds everything present and creates nothing.
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# package (pure namespace container per the u07 __init__.py: imported BY
# NAME, side-effect free at import; the init records the archive doctrine:
# destructive actions require --execute, Trevor-gated). It is NOT a manifest
# row: it ships as a sibling helper exactly the way fields_check.py ships as
# the sibling helper of the U02 verifier (ENGINE-MANIFEST row pattern), so
# the manifest stays stable while THIS module owns the missing-field
# surface. Standalone invocation works too: the SAME sys.path.insert
# bootstrap the sibling imports use resolves anthology_registry from
# scripts/.
#
# CHECK-BY-NAME (the name law, from the field-map's own derivation law):
#   config/field-map.json field_key_derivation_law pins how a field lands on
#   the EXACT PRD Section 6 key: provisioning creates each field with
#   name = the intended key WITHOUT the leading 'contact.' prefix, then
#   reads the server-returned fieldKey back and asserts it byte-equals the
#   intended key. So the canonical live field for an intended key carries
#   BOTH its create_name AND its derived fieldKey. The GET-check indexes the
#   live listing BY NAME as well as BY KEY, because the NAME is the create
#   identity: a live field whose name equals a create_name but whose key
#   does not derive to the intended key is NOT missing — it is a name squat,
#   and creating by that name is exactly the collision the derivation law
#   exists to prevent. Fail-closed on all three branches:
#     - intended key present live by fieldKey -> PRESENT, byte-exact (the
#       read-back contract downstream writes bind to); a live name hint that
#       differs from the create_name is reported as an informational note
#       (the key contract holds; the field may have been hand-created with
#       a different name — never a fail, never silently renamed),
#     - key absent but the create_name present under a DIFFERENT key ->
#       NAME-SQUAT DRIFT (exit 5 family, human-fix; never created, never
#       counted missing),
#     - neither -> MISSING (the list the module exists to surface).
#   Every comparison is byte-exact — no normalization, no substring, no
#   similarity score (the U06 exact-name law, applied to field names).
#
# IDEMPOTENT CREATE-OR-VERIFY (the create gate):
#   * CREATION REQUIRES --execute. An operator surface that lists missing
#     fields and stops is the DEFAULT (a missing field STOPS setup with an
#     operator surface; runtime NEVER silently creates a field — the
#     field-map provisioning_rule, byte-for-byte). Without --execute the
#     module reports missing and STOPS (exit 2, Trevor-gated): the list IS
#     the payload, creation is never silent.
#   * WITH --execute the module creates each missing field by name via the
#     engine's proven create surface (reg.CafClient.create_custom_field —
#     POST /locations/{locationId}/customFields, the derivation-law create
#     endpoint, with data_type from the map and options from the map for
#     the ONE SINGLE_OPTIONS key, anthology_cover_choice), then reads the
#     server-returned fieldKey back and asserts byte-equality to the
#     intended key (the derivation law's exact_match_verify). A created
#     fieldKey that is NOT byte-equal is a MISMATCH (exit 5,
#     AF-AE-FIELD-KEY-MISMATCH family) — the derivation law changed or the
#     server drifted, and NOTHING about that key is certified. Name-squat
#     drift is NEVER created, with or without --execute.
#   * IDEMPOTENT: a field already present live is verified, never
#     re-created; a re-run after a healing create finds the created field by
#     its key and creates nothing (the self-test proves the re-run).
#   * This module NEVER stamps field-map.json: resolved-slot stamping
#     (field_key / field_id / verified_at / location_masked per box) is
#     provision-fields' own duty (anthology_registry.py provision-fields,
#     the sole writer). The finder reports and creates fields only — the
#     map stays the committed template, and a later provision-fields run
#     re-verifies the healed location and stamps it.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The client rides the client's OWN
# Convert and Flow private-integration token resolved via anthology_registry
# (resolve_pit: PIT_LABELS, pit- prefix validated — a placeholder or mis-set
# value is refused WITHOUT printing it). SET / NOT SET only on every
# operator surface; a token value is NEVER printed. The location id is the
# CONTRACT's location label (resolve_location, or --location-id override);
# it is a tenant identifier, reported MASKED (last 4 chars) on every
# surface. Field ids are markers (last 4 chars) on operator surfaces and
# full ONLY inside the JSON payload a machine consumer reads — the same
# masked-on-operator / full-in-payload law find_legacy pins for workflow
# ids.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# backend.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever
# reaches Convert and Flow (the exact failure mode that 403s the bare
# client; the Podcast gate proved the browser UA live; GK-09 pins the
# well-formed four-segment Chrome build). No request is ever made without
# it, and a response BODY is never surfaced (it could echo a credential).
#
# FAIL-CLOSED (the whole point): a field-map with no provisioning.fields
# inventory, an inventory whose total != the map's total_keys contract, an
# unreadable field-map, a non-list live read, an empty live read judged as
# anything but "everything missing", a missing credential or location, a
# name-squat, a created fieldKey that is not byte-equal, or a create
# rejected by the API — every one of these is a REFUSAL / STOP / MISMATCH,
# never a silent pass, never a fabricated success, never a guessed id.
# UNDETERMINED (transport / edge block) is a correct answer: HELD, never a
# verdict.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 belongs to self-test FAILED):
#   0  PASS — every intended key present live (nothing missing, nothing
#      created), or all missing created-and-verified byte-exact with
#      --execute; also plan / self-test OK
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP — usage; no Convert and Flow credential or location SET;
#      field-map has no provisioning.fields inventory (or total drift);
#      a non-list live read (refusal); scope-denied on read or create; or
#      missing fields WITHOUT --execute (the Trevor gate — creation is
#      never silent, AF-AE-FIELD-MISSING family)
#   3  HELD — Convert and Flow unreachable (transport) or an upstream/edge
#      block (CF 1010) — retryable, never mislabeled as scope (the
#      ScopeDenied vs UpstreamBlockedError discrimination)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as an unexpected error)
#   5  MISMATCH — a name-squat drift (a live name under a non-derived key),
#      a created fieldKey that is not byte-equal to its intended key, or a
#      create rejected as invalid (the AF-AE-FIELD-KEY-MISMATCH family)
#
# USAGE:
#   missing_finder.py check [--field-map PATH] [--location-id LOC] [--execute]
#   missing_finder.py plan                      # offline: intended keys
#   missing_finder.py self-test                 # offline fixtures, exit 4 on FAIL
# --execute is the ONLY flag that authorizes field creation (Trevor-gated);
# without it a location with missing fields is a STOP that lists them.
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# fields_check.py: sys.path.insert to scripts/ then `import anthology_registry
# as reg`.
# =============================================================================
"""missing_finder.py — GET-check-by-name and idempotent create-or-verify of
the field-map's custom fields (U07 tooling).

Imported BY NAME as u07_modules.missing_finder from the engine scripts, per
the u07_modules package contract (__init__.py: pure namespace container).
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
# label resolution — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a
# missing-field read (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
REPORT_CONTRACT = "anthology-engine-missing-finder"
REPORT_SCHEMA_VERSION = 1

# The Trevor gate: the ONLY flag that authorizes field creation. Explicit
# presence on the CLI is the operator's authorization; absence with missing
# fields is a STOP, never a silent create.
EXECUTE_FLAG = "--execute"


class MissingFinderError(Exception):
    """A fail-closed verification refusal (STOP family)."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise MissingFinderError(
            "field-map.json has no provisioning.fields inventory — the "
            "missing-field gate has nothing to judge; refusing a blind pass.")
    return [f for f in fields if isinstance(f, dict)]


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _intended_entries(field_map: dict) -> list:
    """(intended_key, create_name, data_type, options) tuples, every one
    sanity-checked: the create_name MUST derive back to the intended key
    (the field-map's own derivation law), else the map contradicts itself
    and the gate refuses."""
    inventory = _contract_inventory(field_map)
    out = []
    for f in inventory:
        intended = f.get("intended_key")
        cname = f.get("create_name")
        if not intended or not cname:
            raise MissingFinderError(
                "a provisioning.fields row is missing intended_key or "
                "create_name — the map is malformed; refusing.")
        if not isinstance(intended, str) or not isinstance(cname, str):
            raise MissingFinderError(
                "a provisioning.fields row carries a non-string key/name — "
                "the map is malformed; refusing.")
        if reg.derive_field_key(cname) != intended:
            raise MissingFinderError(
                "create_name %r does not derive to intended key %r — the "
                "map contradicts its own derivation law; refusing."
                % (cname, intended))
        out.append((intended, cname,
                    f.get("data_type", "LARGE_TEXT"), f.get("options")))
    total = _contract_total(field_map)
    if total is not None and len(out) != total:
        raise MissingFinderError(
            "field-map provisioning.fields carries %d intended keys but the "
            "provisioning.total_keys contract says %d — the map drifted "
            "from its own contract; refusing to judge against a "
            "self-contradicting map." % (len(out), total))
    if not out:
        raise MissingFinderError(
            "field-map provisioning.fields carries no intended_key entries — "
            "refusing a blind pass.")
    return out


def _mask_location(loc: str) -> str:
    return reg._mask_location(loc)


def _mask_id(field_id) -> str:
    """Non-reversible marker for a field id: last 4 chars only (the same
    marker law find_legacy pins for workflow ids)."""
    s = str(field_id or "")
    return ("..." + s[-4:]) if len(s) >= 4 else "...(short)"


def _collect_live(live_fields) -> tuple:
    """Index the live custom-fields listing BY KEY and BY NAME. Fail-closed:
    a non-list read is a refusal, never a silent pass."""
    if not isinstance(live_fields, list):
        raise MissingFinderError(
            "customFields read did not return a list — refusing to judge an "
            "unread surface (never fabricated).")
    by_key, by_name = {}, {}
    for f in live_fields:
        if not isinstance(f, dict):
            continue
        k = f.get("fieldKey")
        if isinstance(k, str) and k:
            by_key[k] = f
        n = f.get("name")
        if isinstance(n, str) and n:
            by_name[n] = f
    return by_key, by_name


# ---------------------------------------------------------------------------
# The check — returns the machine report dict; raises on STOP / HELD /
# fail-closed refusal. NEVER prints a token (it holds none: credentials are
# resolved by the caller's label machinery, SET / NOT SET only).
# ---------------------------------------------------------------------------
def check_fields(client, location_id: str, field_map: dict) -> dict:
    """GET-check-by-name against the live listing. Returns the report dict;
    raises MissingFinderError (STOP family) or reg.ScopeDenied /
    reg.CafUnreachable / reg.UpstreamBlockedError (HELD family) upward —
    exactly the propagation the driver uses. NEVER mutates: the create path
    is the separate apply_create() surface, --execute-gated."""
    masked = _mask_location(location_id)
    entries = _intended_entries(field_map)

    live = client.list_custom_fields(location_id)
    by_key, by_name = _collect_live(live)

    present, missing, drift, name_hints = [], [], [], []
    for intended, cname, _dtype, _opts in entries:
        livef = by_key.get(intended)
        if livef is not None:
            present.append(intended)
            lname = livef.get("name")
            if isinstance(lname, str) and lname and lname != cname:
                name_hints.append({"intended_key": intended,
                                   "create_name": cname,
                                   "live_name": lname})
            continue
        # Key absent: is the CREATE NAME present under a different key? A
        # field named exactly like our create_name but keyed differently is
        # a NAME SQUAT — creating by that name would collide or derive a
        # wrong key. Drift, never missing, never created.
        squatter = by_name.get(cname)
        if squatter is not None:
            drift.append({"name": cname,
                          "intended_key": intended,
                          "live_fieldKey": squatter.get("fieldKey")})
            continue
        missing.append(intended)

    return {
        "contract": REPORT_CONTRACT,
        "schema_version": REPORT_SCHEMA_VERSION,
        "location": masked,
        "ok": (not missing and not drift),
        "verdict": "PASS" if (not missing and not drift) else "FAIL",
        "total": len(entries),
        "present": present,
        "missing": missing,
        "name_squat_drift": drift,
        "name_hint_notes": name_hints,
        "created": [],
        "created_ids": {},
        "mismatches": [],
        "execute": False,
        "detail": ("all %d intended keys present live, byte-exact"
                   % len(entries)
                   if not missing and not drift else
                   "%d missing, %d name-squat drift"
                   % (len(missing), len(drift))),
        "fail_closed": {
            "check_by_name": True,
            "byte_exact_required": True,
            "name_squat_never_created": True,
            "creation_requires_execute": True,
            "note": "a missing field STOPS setup with an operator surface; "
                    "runtime NEVER silently creates a field."},
    }


def apply_create(client, location_id: str, field_map: dict, report: dict) -> dict:
    """The --execute-gated CREATE surface: create each field the check found
    MISSING, by name (create_name, the derivation-law input), then read the
    server-returned fieldKey back and assert byte-equality to the intended
    key. Name-squat drift is NEVER created. Idempotent: fields present live
    are untouched. Returns the report dict updated in place; raises STOP /
    HELD family upward; records per-key mismatches and exits 5 at the end
    (the provision-fields pattern: continue, then STOP the certification)."""
    entries = {intended: (cname, dtype, opts)
               for intended, cname, dtype, opts in _intended_entries(field_map)}
    created, created_ids, mismatches = [], {}, []
    still_missing = []
    for intended in report["missing"]:
        cname, dtype, opts = entries[intended]
        try:
            resp = client.create_custom_field(location_id, cname, dtype,
                                              options=opts)
        except reg.ScopeDenied:
            raise
        except reg.CafValidation as exc:
            mismatches.append({"key": intended,
                               "why": "create rejected: %s" % exc})
            continue
        except (reg.CafUnreachable, reg.UpstreamBlockedError):
            raise
        server_key = resp.get("fieldKey") if isinstance(resp, dict) else None
        if server_key != intended:
            mismatches.append(
                {"key": intended,
                 "why": "server fieldKey %r != intended %r (derivation law "
                        "changed or server drift)" % (server_key, intended)})
            continue
        created.append(intended)
        created_ids[intended] = str(resp.get("id") or "")

    report["missing"] = still_missing
    report["created"] = created
    report["created_ids"] = created_ids
    report["mismatches"] = mismatches
    report["execute"] = True
    if mismatches:
        report["ok"] = False
        report["verdict"] = "MISMATCH"
        report["detail"] = ("%d created and verified byte-exact, %d mismatched"
                            % (len(created), len(mismatches)))
    elif report["name_squat_drift"]:
        report["ok"] = False
        report["verdict"] = "MISMATCH"
        report["detail"] = ("%d created and verified byte-exact, %d name-squat "
                            "drift (never created)"
                            % (len(created), len(report["name_squat_drift"])))
    else:
        report["ok"] = True
        report["verdict"] = "PASS"
        report["detail"] = ("%d created and verified byte-exact; %d already "
                            "present" % (len(created), len(report["present"])))
    return report


# ---------------------------------------------------------------------------
# Driver — prints the ONE JSON report object to stdout, human notes to
# stderr, returns the exit code. STOP and HELD propagate as raised.
# ---------------------------------------------------------------------------
def run_check(client, location_id: str, field_map: dict, *,
              execute: bool = False, out=None) -> int:
    out = out or sys.stderr
    report = check_fields(client, location_id, field_map)
    if not report["missing"] and not report["name_squat_drift"]:
        print(json.dumps(report, indent=2, sort_keys=True))
        out.write("[missing-finder] OK (marker %s): %s.\n"
                  % (report["location"], report["detail"]))
        return EX_OK

    if report["name_squat_drift"] and not report["missing"]:
        # Nothing to create; the drift alone is a MISMATCH (exit 5 family),
        # never created and never a pass.
        print(json.dumps(report, indent=2, sort_keys=True))
        out.write("[missing-finder] MISMATCH (marker %s): %d name-squat drift "
                  "field(s) — a live name under a non-derived key. Human fix, "
                  "never created. First: %s\n"
                  % (report["location"], len(report["name_squat_drift"]),
                     report["name_squat_drift"][0]["name"]))
        return EX_MISMATCH

    # Missing fields exist. Creation is Trevor-gated: without --execute the
    # finder STOPS and lists them — creation is never silent.
    if not execute:
        print(json.dumps(report, indent=2, sort_keys=True))
        out.write("[missing-finder] STOP (marker %s): %d intended field(s) "
                  "missing live and %s was not given. Creation is Trevor-"
                  "gated: re-run with %s to create-or-verify. Missing "
                  "fields (by name): %s\n"
                  % (report["location"], len(report["missing"]),
                     EXECUTE_FLAG, EXECUTE_FLAG,
                     ", ".join("%s (%s)"
                               % (report["missing"][i],
                                  _missing_create_name(field_map,
                                                       report["missing"][i]))
                               for i in range(len(report["missing"])))))
        return EX_STOP

    report = apply_create(client, location_id, field_map, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["verdict"] == "PASS":
        out.write("[missing-finder] OK (marker %s): %s. Created field ids: %s\n"
                  % (report["location"], report["detail"],
                     ", ".join("%s=%s" % (k, _mask_id(v))
                               for k, v in report["created_ids"].items())
                     or "(none)"))
        return EX_OK
    out.write("[missing-finder] MISMATCH (marker %s): %s. First: %s\n"
              % (report["location"], report["detail"],
                 report["mismatches"][0]["why"]
                 if report["mismatches"] else
                 report["name_squat_drift"][0]["name"]))
    return EX_MISMATCH


def _missing_create_name(field_map: dict, intended: str) -> str:
    for f in _contract_inventory(field_map):
        if f.get("intended_key") == intended:
            return f.get("create_name") or ""
    return ""


def plan(field_map: dict, *, out=None) -> int:
    """Offline plan (no network, no credentials): the intended keys and their
    create names the live check will assert, straight from the field-map
    (the single source of truth — never a hardcoded list). One JSON object
    on stdout."""
    out = out or sys.stderr
    entries = _intended_entries(field_map)
    keys = [e[0] for e in entries]
    print(json.dumps({
        "contract": REPORT_CONTRACT + "-plan",
        "schema_version": REPORT_SCHEMA_VERSION,
        "total": len(keys),
        "keys": keys,
        "create_names": [e[1] for e in entries],
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; "
                "creation additionally requires --execute (Trevor-gated)",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# A FAILED self-test is exit 4 (enforced violation), never 'unexpected error'.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the read/create surface
    with a programmable listing and a mutation log (self-tests prove the
    idempotency law: present fields are never re-created)."""

    def __init__(self, fields=None, behavior=None):
        self._fields = list(fields) if isinstance(fields, list) else fields
        self.behavior = behavior  # None | scope | edge | transport | validation
        self.calls = []
        self.created = []

    def list_custom_fields(self, location_id):
        self.calls.append(("fields", location_id))
        self._maybe_raise("read")
        if isinstance(self._fields, list):
            return [dict(f) for f in self._fields]
        return self._fields

    def create_custom_field(self, location_id, name, data_type, options=None):
        self.calls.append(("create", location_id, name, data_type))
        self._maybe_raise("create")
        self.created.append(name)
        # The derivation law: server derives fieldKey = 'contact.' + name.
        # A caller can reprogram _derive to simulate derivation-law drift.
        derived = getattr(self, "_derive", None)
        field_key = derived(name) if derived else reg.derive_field_key(name)
        rec = {"fieldKey": field_key, "name": name,
               "dataType": data_type, "id": "fld_new_%d" % len(self.created)}
        if isinstance(self._fields, list):
            self._fields.append(rec)
        # The real CafClient unwraps the response (out.get("customField") or
        # out) before returning — the fake mirrors that shape exactly.
        return dict(rec)

    def _maybe_raise(self, phase):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")
        if self.behavior == "validation" and phase == "create":
            raise reg.CafValidation("Convert and Flow rejected the request (HTTP 422)")


def _fake_field_map() -> dict:
    return reg.load_field_map(FIELD_MAP_PATH)


def _golden_fields(field_map: dict) -> list:
    """A live listing that EXACTLY matches the map's intended keys — every
    field carries BOTH its create_name AND its derived fieldKey (the
    canonical shape per the derivation law)."""
    return [{"fieldKey": f.get("intended_key"),
             "name": f.get("create_name"),
             "dataType": f.get("data_type", "LARGE_TEXT"),
             "id": "fld_%d" % i}
            for i, f in enumerate(_contract_inventory(field_map))]


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[missing-finder] SELF-TEST FAILED "
                         "(AF-AE-MISSINGFINDER-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    field_map = _fake_field_map()
    entries = _intended_entries(field_map)
    want_keys = [e[0] for e in entries]

    # ---- contract coherence: the map is the source of truth ----
    assert want_keys, "field-map must carry intended keys"
    total = _contract_total(field_map)
    assert total is not None and len(want_keys) == total, \
        "inventory must equal provisioning.total_keys"
    assert all(k.startswith("contact.") for k in want_keys), \
        "every intended key must carry the contact. prefix"
    assert len(set(want_keys)) == len(want_keys), "intended keys must be unique"
    # The derivation law is load-bearing for check-by-name: every create_name
    # must derive to its intended key (the contract reader refuses drift).
    for intended, cname, _d, _o in entries:
        assert reg.derive_field_key(cname) == intended, \
            "create_name %r must derive to %r" % (cname, intended)
    # The browser-UA law: the registry carries the proven CAF_BROWSER_UA and
    # the client that applies it on EVERY request (CF 1010) — pinned here so
    # a registry regression is caught by THIS module's self-test first.
    ua = getattr(reg, "CAF_BROWSER_UA", "")
    assert ua.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a well-formed browser UA, got %r" % ua
    assert "Chrome/" in ua and ua.split("Chrome/")[1].split(" ")[0].count(".") == 3, \
        "CAF_BROWSER_UA must carry a four-segment Chrome build"
    assert hasattr(reg, "CafClient"), \
        "reg.CafClient (the client that applies CAF_BROWSER_UA) must exist"

    # ---- golden live state: EVERYTHING present, NOTHING missing ----
    golden = _golden_fields(field_map)
    caf = _FakeCaf(fields=golden)
    report = check_fields(caf, "loc_fx", field_map)
    assert report["verdict"] == "PASS", "golden: %s" % report["detail"]
    assert report["ok"] is True, "golden report must carry ok: true"
    assert report["total"] == len(want_keys)
    assert report["missing"] == [] and report["name_squat_drift"] == [], \
        "golden must carry zero missing and zero drift"
    assert report["present"] == want_keys, "golden must list every key present"
    assert report["location"] == "...c_fx", \
        "location marker must be masked: %r" % report["location"]
    assert report["fail_closed"]["creation_requires_execute"] is True

    # full run_check on the golden state: exit 0, ONE JSON object on stdout
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_check(caf, "loc_fx", field_map, out=io.StringIO())
    assert rc == EX_OK, "golden run_check must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True

    # ---- the check NEVER writes ----
    assert caf.calls and all(m == "fields" for m, _ in caf.calls), \
        "check performed an unexpected call: %s" % caf.calls
    assert caf.created == [], "check must never create"

    # ---- attack fixtures ----
    # 1. a field DELETED live -> missing, listed; without --execute the run
    #    STOPS (exit 2, Trevor gate) and the JSON lists the missing key
    a1 = copy.deepcopy(golden)[1:]
    caf1 = _FakeCaf(fields=a1)
    report = check_fields(caf1, "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and report["missing"] == [want_keys[0]], \
        "field-deleted must record the missing key"
    buf1 = io.StringIO()
    with contextlib.redirect_stdout(buf1):
        rc = run_check(caf1, "loc_fx", field_map, out=io.StringIO())
    assert rc == EX_STOP, "missing WITHOUT --execute must STOP (exit 2), got %s" % rc
    parsed1 = json.loads(buf1.getvalue())
    assert parsed1["missing"] == [want_keys[0]], \
        "the STOP payload must carry the missing key list"
    assert parsed1["execute"] is False

    # 2. WITH --execute the same location is created-and-verified (exit 0),
    #    server fieldKey read back byte-exact
    caf2 = _FakeCaf(fields=copy.deepcopy(a1))
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = run_check(caf2, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc == EX_OK, "execute create-or-verify must exit 0, got %s" % rc
    parsed2 = json.loads(buf2.getvalue())
    assert parsed2["verdict"] == "PASS" and parsed2["created"] == [want_keys[0]]
    assert parsed2["missing"] == [], "after the create nothing may be missing"
    assert set(parsed2["created_ids"]) == {want_keys[0]}, \
        "the created id must be on the payload (full, machine-readable)"

    # 3. IDEMPOTENCY: a re-run over the healed listing finds everything
    #    present and creates NOTHING
    caf3 = _FakeCaf(fields=caf2._fields)
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc = run_check(caf3, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc == EX_OK, "idempotent re-run must exit 0, got %s" % rc
    assert [m for m, *_ in caf3.calls] == ["fields"], \
        "the re-run must perform ZERO creates: %s" % caf3.calls

    # 4. NAME-SQUAT: a live field named exactly the create_name but keyed
    #    under something else -> drift, NEVER counted missing, NEVER created
    a4 = copy.deepcopy(golden)[1:]
    squatter = dict(golden[0])
    squatter["fieldKey"] = "contact.squatted_key"
    a4.append(squatter)
    caf4 = _FakeCaf(fields=a4)
    report = check_fields(caf4, "loc_fx", field_map)
    assert report["missing"] == [], "the squatted key must NOT be 'missing'"
    assert len(report["name_squat_drift"]) == 1
    assert report["name_squat_drift"][0]["name"] == want_keys[0][len("contact."):]
    assert report["name_squat_drift"][0]["live_fieldKey"] == "contact.squatted_key"
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        rc = run_check(caf4, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "name-squat with --execute must be MISMATCH (5), got %s" % rc
    assert caf4.created == [], "a name-squat must NEVER be created"

    # 5. DERIVATION-LAW DRIFT ON CREATE: the server returns a fieldKey that
    #    is not the intended key -> MISMATCH (exit 5), never certified
    caf5 = _FakeCaf(fields=copy.deepcopy(a1))
    caf5._derive = lambda name: "contact." + name + "_WRONG"
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        rc = run_check(caf5, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "derived-key drift on create must be MISMATCH (5), got %s" % rc
    parsed5 = json.loads(buf5.getvalue())
    assert parsed5["verdict"] == "MISMATCH" and parsed5["created"] == []
    assert any("server fieldKey" in m["why"] for m in parsed5["mismatches"])

    # 6. CREATE REJECTED by the API (validation) -> recorded, MISMATCH (5)
    caf6 = _FakeCaf(fields=copy.deepcopy(a1), behavior="validation")
    buf6 = io.StringIO()
    with contextlib.redirect_stdout(buf6):
        rc = run_check(caf6, "loc_fx", field_map, execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "validation-rejected create must be MISMATCH (5)"
    parsed6 = json.loads(buf6.getvalue())
    assert any("create rejected" in m["why"] for m in parsed6["mismatches"])

    # 7. EMPTY live listing -> everything missing, listed (never a silent
    #    pass), STOP without --execute
    report = check_fields(_FakeCaf(fields=[]), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and len(report["missing"]) == total, \
        "empty live listing must list every key missing"

    # 8. NON-LIST live read -> hard refusal (MissingFinderError)
    try:
        check_fields(_FakeCaf(fields={"not": "a list"}), "loc_fx", field_map)
        raise AssertionError("non-list read was NOT refused")
    except MissingFinderError:
        pass

    # 9. map with no provisioning.fields -> hard refusal
    try:
        check_fields(_FakeCaf(fields=golden), "loc_fx", {})
        raise AssertionError("missing inventory was NOT refused")
    except MissingFinderError:
        pass

    # 10. inventory total != contract total_keys -> hard refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        check_fields(_FakeCaf(fields=golden), "loc_fx", tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except MissingFinderError:
        pass

    # 11. create_name that does not derive -> hard refusal
    tampered2 = copy.deepcopy(field_map)
    tampered2["provisioning"]["fields"][0]["create_name"] = "not_the_right_name"
    try:
        check_fields(_FakeCaf(fields=golden), "loc_fx", tampered2)
        raise AssertionError("derivation-contradicting map was NOT refused")
    except MissingFinderError:
        pass

    # 12. scope denied on the read -> STOP family, never a fabricated pass
    try:
        check_fields(_FakeCaf(fields=golden, behavior="scope"), "loc_fx", field_map)
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass

    # 13. edge block -> HELD family (UpstreamBlockedError, a CafUnreachable)
    try:
        check_fields(_FakeCaf(fields=golden, behavior="edge"), "loc_fx", field_map)
        raise AssertionError("edge-block was NOT refused")
    except reg.UpstreamBlockedError:
        pass

    # 14. transport failure -> HELD family
    try:
        check_fields(_FakeCaf(fields=golden, behavior="transport"), "loc_fx", field_map)
        raise AssertionError("transport failure was NOT refused")
    except reg.CafUnreachable:
        pass

    # 15. name-hint note: key present byte-exact under a DIFFERENT name is
    #    informational, never a fail
    a15 = copy.deepcopy(golden)
    a15[0]["name"] = "hand_created_different_name"
    report = check_fields(_FakeCaf(fields=a15), "loc_fx", field_map)
    assert report["verdict"] == "PASS", "name-hint drift must stay PASS"
    assert report["missing"] == [] and report["name_squat_drift"] == []
    assert len(report["name_hint_notes"]) == 1
    assert report["name_hint_notes"][0]["live_name"] == "hand_created_different_name"

    # ---- plan: offline, no network, exact key list ----
    buf_p = io.StringIO()
    with contextlib.redirect_stdout(buf_p):
        rc = plan(field_map, out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf_p.getvalue())
    assert p["keys"] == want_keys, "plan must list the intended keys in order"
    assert p["create_names"] == [e[1] for e in entries]

    dev.write("missing_finder self-test: OK (field-map coherence %d keys == "
              "total_keys, derivation law self-consistent, CAF_BROWSER_UA "
              "pinned, golden all-PASS + run_check exit 0, 15 attack fixtures "
              "refused or FAIL-recorded (field-deleted/missing-listed/"
              "no-execute-STOP/execute-create-verify/idempotent-re-run/"
              "name-squat/derived-key-drift/validation-reject/empty-listing/"
              "non-list-read/no-inventory/total_keys-drift/bad-create_name/"
              "scope-denied/edge-block/transport/name-hint-note), no-writes, "
              "masked-location, plan offline)\n" % total)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="missing_finder.py",
        description="GET-check-by-name of the field-map's contact custom "
                    "fields on a Convert and Flow location (U07 tooling, "
                    "Skill 59): list missing fields and, with --execute "
                    "(Trevor-gated), create-or-verify them idempotently. "
                    "Never prints a token; the sibling client carries "
                    "CAF_BROWSER_UA on every request (CF 1010 law).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for CREATION — REQUIRED before any "
                         "missing field is created; without it a location "
                         "with missing fields is a STOP (exit 2) that lists "
                         "them; creation is never silent")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"],
                    default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling checkers use).
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

        # ---- live check ----
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
        sys.stderr.write("[missing-finder] PIT resolved via %s (SET). Location "
                         "via %s (marker %s).\n"
                         % (pit_label, loc_label, reg._mask_location(loc)))
        client = reg.CafClient(token)
        return run_check(client, loc, field_map, execute=args.execute,
                         out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[missing-finder] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[missing-finder] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[missing-finder] HELD: %s\n" % exc)
        return EX_HELD
    except MissingFinderError as exc:
        sys.stderr.write("[missing-finder] STOP: %s\n" % exc)
        return EX_STOP
    except FileNotFoundError as exc:
        sys.stderr.write("[missing-finder] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[missing-finder] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
