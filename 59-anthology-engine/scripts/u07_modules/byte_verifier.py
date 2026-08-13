#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/byte_verifier.py  (U07 tooling)
# POST-CREATE READ-BACK VERIFIER — after provisioning creates a custom field,
# RE-READS the Convert and Flow location's custom-field inventory through the
# SAME live read surface the create used (reg.CafClient.list_custom_fields, the
# house adapter) and confirms EVERY server fieldKey byte-exact against the
# field map's intended keys (config/field-map.json provisioning.fields — the
# SINGLE source of truth for field keys; the committed template's 28-key
# inventory). The verifier is the post-write half of the U07 fieldKey law: it
# does NOT create or stamp anything — it RE-READS and CONFIRMS. A fieldKey that
# is not byte-exact is a MISMATCH (exit 5, AF-AE-READBACK-MISMATCH family),
# never a pass, never a fabricated success.
# -----------------------------------------------------------------------------
# WHAT THIS MODULE CONFIRMS (the U07 READ-BACK LAW):
#   1. THE BYTE-EXACT LAW (config/field-map.json readback_rule, carried in by
#      the field map, never re-implemented): "Every write is read back
#      byte-for-byte in the same job; a mismatch is AF-AE-READBACK-MISMATCH
#      (caf_delivery.py exit 5)." This verifier applies the same law to the
#      CREATE surface (the post-create read-back the fieldKey derivation law
#      demands): every server fieldKey must byte-equal its intended key.
#   2. THE SINGLE SOURCE OF TRUTH (config/field-map.json — the ONLY place
#      field keys are spelled; $schema_note). The expected set is read from
#      provisioning.fields (28 rows: the ten deliverable Doc/PDF pairs = 20
#      keys, the three control fields, and the five U8 cover-style fields; the
#      provisioning_rule counts the same 28), one row per key with the
#      immutable CONTRACT (intended_key / create_name / data_type /
#      deliverable / slot) — the intended key is read from the row, never
#      re-typed.
#   3. THE DERIVATION LAW (field_key_derivation_law, W0.5-verified): the
#      LeadConnector v2 create-custom-field endpoint DERIVES the fieldKey —
#      fieldKey = 'contact.' + <name> — and provisioning creates each field
#      with name = the intended key minus the leading 'contact.' prefix, then
#      reads the server-returned fieldKey back and asserts it byte-equals the
#      intended key (exact_match_verify). THIS module re-derives the expected
#      key from the create_name through the registry's OWN derivation surface
#      (reg.derive_field_key — the single implementation, read once) so the
#      derivation can never drift between the provisioner and the verifier.
#   4. THE READ-BACK SET: the live read is the SAME surface the create path
#      used (reg.CafClient.list_custom_fields — GET /locations/{locationId}/
#      customFields, the house adapter), NEVER a second implementation and
#      NEVER a re-read of field-map.json's resolved slots (a stamped map can
#      lie; the live inventory cannot). A fieldKey the live read shows but the
#      field map does not declare is an EXTRA — a drift (AF-AE-FIELD-KEY-
#      MISMATCH family), never ignored; a declared key the live read does not
#      show is MISSING (AF-AE-FIELD-MISSING family), never a silent skip. The
#      comparison is byte-exact in BOTH directions, over the COMPLETE set —
#      an incomplete read-back is a mismatch, never a pass.
#   5. THE ACTION GATE (Trevor-gated, per the u07 package-init doctrine and
#      the family shape the U06 archive verifier pins): an ACTION — any
#      mutation that deletes / archives / removes / deactivates / revokes /
#      unpublishes — REQUIRES --execute explicitly. THIS module performs NO
#      mutation at all (it RE-READS and CONFIRMS; READ-ONLY by construction)
#      and the VERIFY action is the one ACTION surface it carries — an
#      ACTION without --execute is a STOP (exit 2), never a silent no-op,
#      exactly the family gate.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The token is resolved through the
# registry's own resolver (reg.resolve_pit — the PIT label set, pit- prefix
# validated; a value that is not a pit- token REFUSES, never used) and the
# location id through reg.resolve_location (the LOCATION_LABELS set; an
# explicit --location-id is an argument, never a secret). A value is NEVER
# printed: labels are reported SET / NOT SET only; the location id is masked
# (last 4 chars) on every human surface. This module pins the house credential
# LAW offline in the self-test (the PIT label set is asserted, and the
# resolve_pit invariant — a non-pit- value must be REFUSED) so a registry
# regression is caught HERE first.
#
# BROWSER UA (CF 1010 LAW): services.leadconnectorhq.com is Cloudflare-fronted
# and 403s urllib's default "Python-urllib/x.y" User-Agent at the WAF edge (CF
# error 1010) before the request ever reaches Convert and Flow. This module
# makes its ONE live request through reg.CafClient, which carries the browser
# User-Agent CAF_BROWSER_UA on EVERY request (the house pattern, ported
# byte-for-byte from the proven Podcast-gate string). This module defines NO
# User-Agent constant of its own; the self-test PINS the constant (a
# well-formed browser UA, never "Python-urllib") so a drifted UA is caught
# before a single live request ever rides the family. The UA is a public
# per-request header, never a secret.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  PASS — every server fieldKey byte-exact against the field map (also
#      plan / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage, an ACTION without --execute (the Trevor gate),
#      a missing credential label, a PIT value that is not a pit- token, a
#      genuine scope denial, a field-map contract that cannot be read, or a
#      credential-shaped string on any surface
#   3  HELD — the Convert and Flow API is unreachable (incl. the Cloudflare
#      edge 403, which is an upstream/edge block, never mislabeled as scope)
#      — UNDETERMINED, retryable, never a verdict
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  MISMATCH — a server fieldKey not byte-exact, a declared key missing
#      from the live read, or a live key the field map does not declare (the
#      fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO token and NO network;
# verify needs the live Convert and Flow read):
#   byte_verifier.py verify [--field-map PATH] [--location-id ID]
#                           [--execute]      # Trevor-gated ACTION; the
#                                             # verifier still never writes
#   byte_verifier.py plan [--field-map PATH]  # offline plan
#   byte_verifier.py self-test [--field-map PATH]  # offline fixtures
#
# --execute is the ONLY flag that authorizes the ACTION (Trevor-gated).
# WITHOUT it the ACTION is a STOP (exit 2), never a silent no-op — the
# family gate. WITH it the ACTION still performs NO write: this module
# re-reads and confirms field keys only, and the report records the execute
# state explicitly.
#
# STDLIB ONLY. Calls NO model. Reuses anthology_registry (exit-code
# constants, CAF_BROWSER_UA, PIT_LABELS, LOCATION_LABELS, resolve_pit,
# resolve_location, _mask_location, load_field_map, derive_field_key,
# create_name_of, FIELD_MAP_PATH, and the CafClient — the house adapter whose
# ONE live request already carries the browser UA). DOCTRINE: move in
# silence; operator-verbose only; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value.
# =============================================================================
"""byte_verifier.py — post-create read-back verifier: confirms EVERY server
fieldKey byte-exact against config/field-map.json provisioning.fields after a
provisioning create (Skill 59, U07 tooling). READ-ONLY: never creates, never
stamps, never writes; the verify ACTION requires --execute (Trevor-gated) and
is reported, never mutated."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA law, the exit-code contract, the field-map IO, the
# derivation law's single implementation, and the house Convert and Flow
# adapter. All are STDLIB-only and side-effect-free at import — importing
# them cannot drag credential resolution into this process.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a field-key
# read-back (the self-test asserts the golden report carries the exact string —
# the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-byte-verifier"
CONFIG_SCHEMA_VERSION = 1

# The VERIFY ACTION, Trevor-gated (the family shape the u07 package-init
# doctrine pins and the U06 archive verifier applies to its ACTION surface):
# without --execute the ACTION is a STOP (exit 2), never a silent no-op; with
# it the verifier STILL performs no write — it re-reads and confirms.
VERIFY_ACTION = "verify"
EXECUTE_FLAG = "--execute"

# The field map — the SINGLE source of truth for field keys
# (config/field-map.json $schema_note: "This is the ONLY place field keys are
# spelled"). The expected keys are read from the provisioning.fields inventory
# rows, one intended key per row, never re-typed.
FIELD_MAP_PATH = reg.FIELD_MAP_PATH  # the engine's canonical repo path

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (the house guard shape every u07 surface is scanned against — the
# credential LAW every adapter guards with the same pattern). A hit on any
# emitted surface REFUSES rather than echo.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class ByteVerifierError(Exception):
    """A fail-closed refusal (STOP family): a credential-shaped string on a
    surface, a credential that cannot be resolved, a genuine scope denial, or
    a field-map contract that cannot be read. An expectation that cannot name
    its own sources must not run."""


# ---------------------------------------------------------------------------
# Fail-closed read helpers. Pure; never print a secret value.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible marker for an id (last 4 chars) — the house surface
    shape for every operator-facing mention of an id. Full ids ride inside
    the machine payload a consumer reads, never on a human surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def _mask_location(loc: str) -> str:
    """Non-reversible marker for the location id, via the registry's own
    masking surface (the single implementation, read once — never a second
    copy of the mask rule)."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# The expected surface — the field map's provisioning.fields inventory, the
# SINGLE source of truth for field keys. Fail-closed: an unreadable or
# malformed map is a REFUSAL, never a blind skip; a malformed inventory row
# is a REFUSAL, never a guessed key.
# ---------------------------------------------------------------------------
def _load_expected_inventory(field_map_path: Path) -> list:
    """The expected field-key inventory, read from the field map's
    provisioning.fields rows (the SINGLE source of truth — one intended_key
    per row, plus the immutable CONTRACT create_name / data_type / deliverable
    / slot). Fail-closed: an unreadable or malformed map, a missing or empty
    inventory, or a malformed row is a REFUSAL (ByteVerifierError) — never a
    blind skip and never a guessed key."""
    try:
        fm = reg.load_field_map(field_map_path)
    except (OSError, IOError, ValueError) as exc:
        raise ByteVerifierError(
            "field-map.json unreadable/malformed at %s: %s — the expected "
            "keys are unverifiable" % (field_map_path, exc))
    inventory = (fm or {}).get("provisioning", {}).get("fields")
    if not isinstance(inventory, list) or not inventory:
        raise ByteVerifierError(
            "field-map.json has no provisioning.fields inventory at %s — the "
            "expected keys are unverifiable" % field_map_path)
    rows = []
    for item in inventory:
        if not isinstance(item, dict):
            raise ByteVerifierError(
                "field-map.json provisioning.fields carries a non-object row "
                "at %s — REFUSED without guessing" % field_map_path)
        intended = item.get("intended_key")
        cname = item.get("create_name")
        if not isinstance(intended, str) or not intended:
            raise ByteVerifierError(
                "field-map.json provisioning.fields row carries no "
                "intended_key at %s — REFUSED without guessing"
                % field_map_path)
        if not isinstance(cname, str) or not cname:
            raise ByteVerifierError(
                "field-map.json provisioning.fields row %r carries no "
                "create_name at %s — REFUSED without guessing"
                % (intended, field_map_path))
        rows.append((intended, cname))
    return rows


def _derive_expected(intended: str, cname: str) -> str:
    """The expected server fieldKey, derived through the registry's OWN
    derivation surface (reg.derive_field_key — the W0.5-verified single
    implementation, read once): fieldKey = 'contact.' + <name>, where <name>
    is the create_name the provisioner supplied snake-cased. Fail-closed: a
    create_name that does not derive back to the intended key is a REFUSAL —
    the derivation law would be broken, never a guessed expectation."""
    expected = reg.derive_field_key(cname)
    if expected != intended:
        raise ByteVerifierError(
            "create_name %r does not derive back to the intended key %r — "
            "the field_key derivation law (W0.5) would be violated; the "
            "expected surface is unverifiable" % (cname, intended))
    return expected


# ---------------------------------------------------------------------------
# The live surface — the SAME read the create path used (reg.CafClient
# list_custom_fields, the house adapter, whose request already carries the
# browser UA on every request — CF 1010 law). Never a second implementation,
# and NEVER a re-read of field-map.json's resolved slots: a stamped map can
# lie, the live inventory cannot.
# ---------------------------------------------------------------------------
def _resolve_credentials(location_override: str = "") -> tuple:
    """Resolve the client's OWN Convert and Flow token and the location id —
    BY LABEL, NEVER BY VALUE — through the registry's own resolvers (the
    single implementation, read once). Returns (token, location_label,
    location_id) with the location id MASKED on the label surface. Fail-closed:
    a missing label or a PIT value that is not a pit- token is a REFUSAL."""
    token_label, token = reg.resolve_pit()
    if token is None:
        raise ByteVerifierError(
            "no Convert and Flow private-integration token resolved by label "
            "(checked: %s); the live read-back cannot authenticate — SET / "
            "NOT SET reported, value never printed" % ", ".join(reg.PIT_LABELS))
    if not token.startswith(reg.PIT_PREFIX):
        raise ByteVerifierError(
            "a value under %s is not a pit- token — REFUSED without using it "
            "(never printed)" % token_label)
    loc_label, loc = reg.resolve_location(location_override)
    if not loc:
        raise ByteVerifierError(
            "no Convert and Flow location id resolved (checked: %s); the "
            "live read-back has no target" % ", ".join(reg.LOCATION_LABELS))
    return token, loc_label, loc


def _live_field_keys(token: str, location_id: str) -> dict:
    """The live server fieldKey inventory, read through the house adapter
    (reg.CafClient.list_custom_fields — the SAME surface the create path
    used, browser UA carried on the request). Returns {fieldKey: field_id}.
    Fail-closed: a genuine scope denial is a STOP (ByteVerifierError); an
    unreadable Convert and Flow (incl. the Cloudflare edge 403, an upstream
    block never mislabeled as scope) is HELD (CafUnreachable — the caller
    maps it); a field without a fieldKey is REFUSED (a keyless row cannot be
    judged). The token is used in the request only, never printed."""
    client = reg.CafClient(token)
    try:
        rows = client.list_custom_fields(location_id)
    except reg.ScopeDenied as exc:
        raise ByteVerifierError(
            "the Convert and Flow token is not authorized to READ custom "
            "fields on this location (genuine scope denial): %s — STOP, "
            "never a guessed verdict" % exc)
    keys = {}
    for field in rows:
        if not isinstance(field, dict):
            continue
        fk = field.get("fieldKey")
        if not isinstance(fk, str) or not fk:
            raise ByteVerifierError(
                "the live custom-field read returned a field with no "
                "fieldKey — a keyless row cannot be judged; REFUSED without "
                "guessing")
        keys[fk] = field.get("id")
    return keys


# ---------------------------------------------------------------------------
# The verdict — confirm every server fieldKey byte-exact, fail-closed.
# ---------------------------------------------------------------------------
def _verify_keys(expected_pairs: list, live: dict) -> tuple:
    """The read-back verdict, fail-closed and byte-exact: EVERY expected key
    must be present in the live read with a byte-equal server fieldKey, and
    EVERY live key must be declared by the field map. Returns (ok, missing,
    mismatched, extra) — pure, never prints."""
    expected = {}
    for intended, cname in expected_pairs:
        expected[intended] = _derive_expected(intended, cname)
    missing = sorted(intended for intended, _ in expected_pairs
                     if expected[intended] not in live)
    mismatched = sorted(intended for intended, expected_key in expected.items()
                        if intended in live and expected_key != intended)
    extra = sorted(fk for fk in live if fk not in set(expected.values()))
    return (not missing and not mismatched and not extra,
            missing, mismatched, extra)


# ---------------------------------------------------------------------------
# The verify command — the Trevor-gated ACTION. Re-reads the live inventory
# through the house adapter and confirms every server fieldKey byte-exact.
# READ-ONLY by construction: it never creates, never stamps, never writes.
# ---------------------------------------------------------------------------
def verify(*, field_map_path: Path, location_override: str = "",
           execute: bool = False, out=None, journal=None) -> int:
    """Re-read the Convert and Flow location's custom-field inventory and
    confirm EVERY server fieldKey byte-exact against the field map,
    fail-closed. Emits the ONE JSON report object on stdout; human notes go
    to out (stderr).

    - the expected surface is the field map's provisioning.fields inventory
      (the SINGLE source of truth — one intended key per row, never re-typed)
      with each expectation derived through the registry's OWN derivation
      surface (reg.derive_field_key, the W0.5-verified single implementation),
    - the live surface is the SAME read the create path used
      (reg.CafClient.list_custom_fields — the house adapter, browser UA on
      every request; NEVER a re-read of field-map.json's resolved slots, a
      stamped map can lie),
    - the ACTION is Trevor-gated: WITHOUT --execute it is a STOP (exit 2,
      the family gate), never a silent no-op; WITH --execute the ACTION is
      reported explicitly on the report (execute true) and the verifier
      STILL performs no write,
    - a missing credential label / a non-pit- token / a genuine scope denial
      / a field-map contract that cannot be read REFUSES (STOP, exit 2); an
      unreadable Convert and Flow (incl. the Cloudflare edge 403) is HELD
      (exit 3, UNDETERMINED — never a verdict); a credential-shaped value on
      any surface REFUSES, never echo.
    `journal` is an explicit read seam (the self-tests hand a journal of
    expected pairs + live keys; when None the live Convert and Flow read is
    performed)."""
    out = out or sys.stderr
    if not execute:
        sys.stderr.write(
            "[byte-verifier] STOP: an ACTION requires --execute explicitly "
            "(Trevor-gated). Without --execute the ACTION is a refusal, "
            "never a silent no-op; the verifier STILL never writes.\n")
        return EX_STOP
    masked = _mask_location(location_override)
    if journal is not None:
        expected_pairs = journal.get("expected")
        live = journal.get("live")
        if not isinstance(expected_pairs, list) or not expected_pairs:
            sys.stderr.write(
                "[byte-verifier] STOP: the journal carries no expected "
                "inventory — REFUSED without guessing (self-test seam).\n")
            return EX_STOP
        if not isinstance(live, dict):
            sys.stderr.write(
                "[byte-verifier] STOP: the journal carries no live key "
                "surface — REFUSED without guessing (self-test seam).\n")
            return EX_STOP
        live_read = "explicit (self-test)"
        expected_source = "explicit (self-test)"
    else:
        try:
            expected_pairs = _load_expected_inventory(field_map_path)
        except ByteVerifierError as exc:
            sys.stderr.write("[byte-verifier] STOP: %s\n" % exc)
            return EX_STOP
        try:
            token, loc_label, loc = _resolve_credentials(location_override)
        except ByteVerifierError as exc:
            sys.stderr.write("[byte-verifier] STOP: %s\n" % exc)
            return EX_STOP
        masked = _mask_location(loc)
        try:
            live = _live_field_keys(token, loc)
        except ByteVerifierError as exc:
            sys.stderr.write("[byte-verifier] STOP: %s\n" % exc)
            return EX_STOP
        except reg.CafUnreachable as exc:
            sys.stderr.write(
                "[byte-verifier] HELD: the Convert and Flow custom-field "
                "read is unreachable (marker %s): %s — UNDETERMINED, never "
                "a verdict.\n" % (masked, exc))
            return EX_HELD
        live_read = ("reg.CafClient.list_custom_fields (GET /locations/{id}/"
                     "customFields — the SAME read the create path used, "
                     "browser UA on every request)")
        expected_source = ("config/field-map.json provisioning.fields "
                           "(the single source of truth)")

    # never-a-token: every emitted value is scanned before print
    blob = json.dumps({"live": live})
    if _CREDENTIAL_SHAPE.search(blob):
        sys.stderr.write(
            "[byte-verifier] STOP: a credential-shaped string appeared on "
            "the read surface — REFUSED without printing it.\n")
        return EX_STOP

    ok, missing, mismatched, extra = _verify_keys(expected_pairs, live)
    if not ok:
        detail = []
        for intended in missing:
            detail.append("declared key missing from the live read: %s"
                          % intended)
        for intended in mismatched:
            detail.append("server fieldKey != intended key: %s"
                          % intended)
        for fk in extra:
            detail.append("live key the field map does not declare: %s" % fk)
        out.write("[byte-verifier] MISMATCH: %s\n" % "; ".join(detail))
    report = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": ok,
        "verdict": "PASS" if ok else "MISMATCH",
        "execute": execute,
        "action": VERIFY_ACTION,
        "execute_required": True,
        "expected_keys": len(expected_pairs),
        "live_keys": len(live),
        "missing": missing,
        "mismatched": mismatched,
        "extra": extra,
        "sources": {
            "expected": expected_source,
            "live": live_read,
        },
        "location_masked": masked,
        "note": ("every server fieldKey byte-exact against the field map "
                 "(%d keys; live read confirmed %d)"
                 % (len(expected_pairs), len(live)) if ok else
                 "a server fieldKey is not byte-exact (missing / mismatched "
                 "/ extra) — fail-closed, never a fabricated success"),
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return EX_OK if ok else EX_MISMATCH


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials, no live read needed. The
# read-back law with the exact sources of truth, printed as ONE JSON object
# on stdout. The payload is scanned against the credential shape before
# print.
# ---------------------------------------------------------------------------
def _plan_payload(field_map_path: Path) -> dict:
    """The ONE offline plan payload (shared by plan() and the self-test's
    never-a-token scan, so the two can never drift)."""
    return {
        "contract": CONFIG_CONTRACT + "-plan",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "action": VERIFY_ACTION,
        "execute_required": True,
        "expected_source": "config/field-map.json provisioning.fields "
                           "(the single source of truth for field keys; the "
                           "committed template's 28-key inventory)",
        "live_source": "reg.CafClient.list_custom_fields (GET /locations/"
                       "{id}/customFields — the SAME read the create path "
                       "used; browser UA carried on every request, CF 1010 "
                       "law; NEVER a re-read of field-map.json's resolved "
                       "slots, a stamped map can lie)",
        "law": "every server fieldKey must byte-equal its intended key "
               "(config/field-map.json readback_rule; the field_key "
               "derivation law, W0.5-verified: fieldKey = 'contact.' + "
               "<name>); a declared key missing from the live read is "
               "AF-AE-FIELD-MISSING family; a server fieldKey not byte-exact "
               "or a live key the field map does not declare is the "
               "AF-AE-FIELD-KEY-MISMATCH family (exit 5)",
        "note": "offline plan only — no network, no credential, no live read "
                "needed; a server fieldKey not byte-exact is a MISMATCH "
                "(exit 5), never a pass; an unreadable Convert and Flow "
                "(incl. the Cloudflare edge 403) is HELD (exit 3), never a "
                "verdict; the verify ACTION is --execute-gated "
                "(Trevor-gated) and this verifier NEVER writes",
    }


def plan(*, field_map_path: Path, out=None) -> int:
    out = out or sys.stdout
    payload = _plan_payload(field_map_path)
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise ByteVerifierError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out.write(dumped)
    out.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — no network, no credentials, no live read needed. The
# golden read-back (every server fieldKey byte-exact) PASSES; every drift
# REFUSES. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the U05 / U06 families apply.
# ---------------------------------------------------------------------------
def _golden_expected() -> list:
    """The golden expected inventory: the THREE control rows of the
    field-map contract, derived through the registry's OWN derivation
    surface. Every row's create_name derives back to its intended key, so a
    drifted derivation law trips the self-test first (fail-closed: the
    expectation is never guessed)."""
    rows = []
    for intended, cname in (
            ("contact.anthology_active_id", "anthology_active_id"),
            ("contact.anthology_stage", "anthology_stage"),
            ("contact.anthology_rewrite_count", "anthology_rewrite_count")):
        assert reg.derive_field_key(cname) == intended, \
            "the derivation law (W0.5) no longer derives %r from %r" \
            % (intended, cname)
        rows.append((intended, cname))
    return rows


def _golden_live() -> dict:
    """The golden live surface: every golden expected key present with a
    byte-equal server fieldKey and an opaque field id (a real GHL field id is
    never used — the id is a synthetic marker, and no value here is a
    credential)."""
    return {
        "contact.anthology_active_id": "fld_golden_active",
        "contact.anthology_stage": "fld_golden_stage",
        "contact.anthology_rewrite_count": "fld_golden_rewrite",
    }


def _self_test_body(dev, field_map_path: Path) -> None:
    expected_golden = _golden_expected()
    live_golden = _golden_live()

    # ---- contract coherence: the single source of truth is readable --------
    try:
        _load_expected_inventory(field_map_path)
    except ByteVerifierError as exc:
        raise AssertionError(
            "the field map contract is unreadable — the expected surface "
            "law cannot be proven: %s" % exc)

    # ---- the golden read-back: every key byte-exact -> PASS ----------------
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(),
                    journal={"expected": expected_golden, "live": live_golden})
    assert rc == EX_OK, "the golden byte-exact read-back must PASS, got %s" % rc

    # ---- the ACTION gate, both directions -----------------------------------
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=False,
                    out=io.StringIO(),
                    journal={"expected": expected_golden, "live": live_golden})
    assert rc == EX_STOP, \
        "an ACTION without --execute must STOP (Trevor-gated), got %s" % rc

    # ---- drift fixtures: every deviation REFUSED (fail-closed) -------------
    # 1. a declared key missing from the live read -> MISMATCH (exit 5)
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(), journal={
                        "expected": expected_golden,
                        "live": {k: v for k, v in live_golden.items()
                                 if k != "contact.anthology_stage"}})
    assert rc == EX_MISMATCH, \
        "a declared key missing from the live read must exit 5"
    # 2. a server fieldKey that is NOT byte-exact -> MISMATCH (exit 5). The
    #    one-byte drift (a trailing space) is the byte-exact test: the live
    #    key differs from the intended key by one byte, so the exact-match
    #    comparison must fail — the byte-exact law, never a near-match pass.
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(), journal={
                        "expected": expected_golden,
                        "live": dict(live_golden,
                                     **{"contact.anthology_stage ":
                                        "fld_golden_stage"})})
    assert rc == EX_MISMATCH, \
        "a server fieldKey that is not byte-exact must exit 5"
    # 3. a live key the field map does not declare -> MISMATCH (exit 5)
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(), journal={
                        "expected": expected_golden,
                        "live": dict(live_golden,
                                     **{"contact.anthology_sneak_key":
                                        "fld_golden_sneak"})})
    assert rc == EX_MISMATCH, \
        "a live key the field map does not declare must exit 5"
    # 4. a credential-shaped key on the live surface -> STOP (exit 2), never
    #    echoed
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(), journal={
                        "expected": expected_golden,
                        "live": dict(live_golden,
                                     **{"contact.anthology_sneak":
                                        "pit-abc123"})})
    assert rc == EX_STOP, \
        "a credential-shaped read value must STOP, never echo"
    # 5. an empty expected inventory -> STOP (exit 2), never a sweep
    with _redirect_stdout():
        rc = verify(field_map_path=field_map_path, execute=True,
                    out=io.StringIO(),
                    journal={"expected": [], "live": live_golden})
    assert rc == EX_STOP, "an empty expected inventory must STOP"

    # ---- the BROWSER UA law is pinned (CF 1010) -----------------------------
    ua = reg.CAF_BROWSER_UA
    assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
    assert "Python-urllib" not in ua, \
        "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
    assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
        "CAF_BROWSER_UA is not a well-formed browser UA"

    # ---- the credential LAW is the house set --------------------------------
    assert tuple(reg.PIT_LABELS) == (
        "CONVERT_AND_FLOW_PIT", "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_PIT", "GHL_API_KEY"), \
        "PIT label set drifted from the house credential law"
    _label, token = reg.resolve_pit()
    assert token is None or str(token).startswith("pit-"), \
        "resolve_pit returned a non-pit- token (would be refused)"

    # ---- never-print: no credential-shaped string on any surface -----------
    plan_blob = json.dumps(_plan_payload(field_map_path), indent=2,
                           sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(plan_blob), \
        "the plan surface must never carry a credential-shaped string"

    dev.write("byte_verifier self-test: OK (golden byte-exact read-back "
              "PASSES; the ACTION without %s STOPS (Trevor-gated); 5 drift "
              "fixtures refused fail-closed: missing-declared-key / "
              "non-byte-exact-fieldKey / undeclared-live-key / "
              "credential-shaped-read-STOP / empty-expected-STOP; browser-UA "
              "+ credential-law pinned; never-print)\n" % EXECUTE_FLAG)


def self_test(*, field_map_path: Path, out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev, field_map_path)
    except AssertionError as exc:
        sys.stderr.write("[byte-verifier] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


# The self-test seam, module-local (the U05 / U06 siblings use the same
# contextlib redirect inline; keeping it named here makes the fixture battery
# read as one story).
def _redirect_stdout():
    import contextlib
    return contextlib.redirect_stdout(io.StringIO())


# ---------------------------------------------------------------------------
# CLI — house shape: --self-test / --selftest normalize to the positional
# subcommand form exactly as the registry and the U02 / U03 / U04 / U05 / U06
# siblings normalize. The ACTION (verify) requires --execute (the Trevor
# gate); plan and self-test are OFFLINE.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="byte_verifier.py",
        description="Post-create read-back verifier: after provisioning "
                    "creates a custom field, RE-READS the Convert and Flow "
                    "location's custom-field inventory through the same live "
                    "read surface the create used and confirms EVERY server "
                    "fieldKey byte-exact against config/field-map.json "
                    "provisioning.fields (the single source of truth — Skill "
                    "59, U07 tooling). READ-ONLY: never creates, never "
                    "stamps, never writes; the verify ACTION requires "
                    "--execute (Trevor-gated) and is reported, never "
                    "mutated. Never prints a token; the read rides "
                    "reg.CafClient with CAF_BROWSER_UA on every request "
                    "(CF 1010 law).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to config/field-map.json (default: the "
                         "engine's canonical repo path)")
    ap.add_argument("--location-id", default="",
                    help="Convert and Flow location id (default: resolved "
                         "by label, CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID; masked "
                         "on every surface, never printed in full)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for an ACTION — REQUIRED before "
                         "the verify runs; without it the ACTION is a STOP "
                         "(exit 2), never a silent no-op; even WITH it this "
                         "verifier never writes")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    default="verify")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    field_map_path = Path(args.field_map).expanduser()

    try:
        if args.cmd == "self-test":
            return self_test(field_map_path=field_map_path, out=sys.stderr)
        if args.cmd == "plan":
            return plan(field_map_path=field_map_path)
        return verify(field_map_path=field_map_path,
                      location_override=args.location_id,
                      execute=args.execute, out=sys.stderr)
    except ByteVerifierError as exc:
        sys.stderr.write("[byte-verifier] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[byte-verifier] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
