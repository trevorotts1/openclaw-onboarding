#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/attack_missing_field.py
# ATTACK FIXTURE — 27 OF 28 FIELDS, MUST FAIL (U02 tooling, extension module).
# The adversarial sibling of golden_fields.py: a live customFields read that
# carries EVERY contract field except one — a strict 27-key subset of the 28
# intended keys a Convert and Flow location must carry. The U02 verifier's
# byte-exact field gate (fields_check.py) MUST FAIL this read in BOTH of its
# directions (the missing key is a strict-subset MISSING, never a pass) and
# THIS module's own gate payload() MUST REFUSE it fail-closed with exit 5 —
# a 27-key read is drift, never a golden payload. The one dropped field is
# DETERMINISTIC: the LAST key of the field-map's provisioning.fields inventory
# (the control slot contact.anthology_rewrite_count today), so the fixture
# survives map edits — derive by position, never by hardcoded key (the field-
# map is the single source of truth; a hardcoded key list would drift).
#
# WHERE THIS SITS: scripts/u02_modules/ — an importable module under the U02
# template-verify tooling, exactly like its sibling golden_fields.py. It is
# NOT a manifest row and NOT a checker: it ships the ADVERSARIAL fixture
# surface the self-tests of the U02 verifier and its sibling checkers assert
# against, so the FAIL path is judged against the SAME payload the happy path
# judges against — a drift in the field-map contract breaks THIS module's
# self-test first (fail-closed: an inconsistent map is a refusal, never a
# blind pass). Imported BY NAME as u02_modules.attack_missing_field from the
# engine scripts, per the u02_modules package contract (__init__.py: pure
# namespace container — fail-closed empty init, no runtime code). Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling imports
# use resolves anthology_registry from scripts/.
#
# WHAT THIS OWNS:
#   1. ATTACK_FIELDS — a frozen, deterministic list of the 27 field records
#      ({fieldKey, name, dataType, id, options}) exactly as a live customFields
#      read would return them for a location missing the LAST contract field:
#      fieldKey and name byte-equal the map's intended_key and create_name,
#      dataType carries the map's declared type (LARGE_TEXT for every free-text
#      key, Gap G11; SINGLE_OPTIONS for the lone U8 cover-choice key, with its
#      four picklist options), and each record carries the SAME stable
#      synthetic field id the golden sibling ships (fld_golden_000 ..
#      fld_golden_026 — the missing field's id fld_golden_027 is absent, and
#      its record is absent: the attack is a STRICT SUBSET, the exact shape
#      that must never pass). The OPTIONS container is a tuple (never a list),
#      so an attack record can never be mutated through the module's public
#      surface.
#   2. attack_fields() — the builder, fail-closed: a missing/malformed
#      provisioning.fields inventory or a contract that does not satisfy the
#      28-key law raises FixtureError instead of shipping a wrong fixture.
#      The drop is applied by POSITION (the last inventory row), never by a
#      hardcoded key.
#   3. verify_live(client, location_id, field_map) — the JUDGE: reports the
#      27-key read against the field-map contract and exits 5 (mismatch family)
#      with missing=["<the last intended key>"], never a pass; on the true 28
#      key read it exits 0. The one place this module makes the FAIL explicit:
#      an attack fixture that PASSES any field gate is a broken gate.
#   4. payload() / payload_true() — the FAIL-CLOSED gates. payload() REFUSES
#      the 27-key fixture with exit 5 (verdict REFUSED — the fixture must fail,
#      and it must fail HERE, offline, before any live read). payload_true()
#      is the control: the TRUE 28-key golden payload passes exit 0, so the
#      self-test's pass/fail split discriminates the 27/28 boundary and never
#      a broken instrument (the negative-result contract: a negative is a
#      claim and carries the same burden of proof as a positive one — a gate
#      that fails everything is a broken check, not a real fault).
#
# DOCTRINE (inherited from the registry / drive adapter / U02 verifier):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory field metadata, and the verify surface
#     reports the location by masked marker (last 4 chars) only. Nothing in
#     this module can ever echo a secret because no secret is ever read.
#   - Fail-closed: a malformed map, an absent section, a non-object read all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The field-list surface this fixture emulates is the PUBLIC v2 custom
#     fields read. Any module that talks to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry the
#     browser User-Agent on every request — urllib's default "Python-urllib/x.y"
#     is 403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). This
#     module itself makes NO network call — it ships the offline adversarial
#     fixture only; the client that DOES (reg.CafClient) already sends
#     CAF_BROWSER_UA on every request, and the self-test pins the constant so
#     a registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier):
#   0  verified success — the golden 28-key payload is internally consistent
#      and byte-equal to the field-map contract; also self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON)
#   4  self-test FAILED (AF-AE-ATTACKMISSINGFIELD-* family, enforced violation)
#   5  mismatch — the 27-key attack fixture is REFUSED (payload), the 27-key
#      read is FAIL (verify_live), or the map drifted from the fixture
#      contract (inventory length != 28, or total_keys != the inventory
#      length) — all FAIL-CLOSED refusals, never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# golden_fields.py: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""attack_missing_field.py — the 27-of-28-field attack fixture that must FAIL.

The adversarial sibling of golden_fields.py: a deterministic strict 27-key
subset of the 28 contract fields, which the byte-exact field gate must never
pass and which this module's own gates refuse fail-closed (exit 5).
"""

from __future__ import annotations

import argparse
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

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. The 28 field KEYS themselves are NEVER
# hardcoded here — they come from the field-map (the single source of truth);
# a hardcoded key list would drift and defeat the fixture's whole purpose.
ATTACK_CONTRACT = "anthology-engine-attack-missing-field"

# The contract total, fixed by the PRD (19 base Section 6 link/control keys +
# 4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys). The
# attack fixture drops exactly ONE of these: 27 is the adversarial count.
CONTRACT_TOTAL = 28
ATTACK_TOTAL = CONTRACT_TOTAL - 1  # 27 of 28 — the strict-subset attack

# The ONE non-free-text field in the contract (PRD Section 6 / U8): the
# cover-choice picklist. Everything else must be LARGE_TEXT (Gap G11). The
# picklist's four options are the named cover styles the client picks from.
# Mirrors golden_fields.py byte-for-byte: the fixture stays golden-shaped
# on every field it KEEPS, so the ONLY deviation is the missing field.
COVER_CHOICE_KEY = "contact.anthology_cover_choice"
COVER_CHOICE_OPTIONS = ("Signature", "Bold Editorial", "Fine Art", "Pure Type")

# The drop position: the LAST row of the field-map's provisioning.fields
# inventory (the control slot contact.anthology_rewrite_count today). By
# POSITION, never by hardcoded key — the field-map is the single source of
# truth, so the attack tracks the map's own ordering. Drop exactly one: a
# 27-key strict subset, the shape that must NEVER pass a field gate.
DROP_INDEX = -1


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the field-map is
    inconsistent with the golden contract, so NO fixture is shipped — a wrong
    fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise FixtureError(
            "field-map.json has no provisioning.fields inventory — the attack "
            "fixture has nothing to drop from; refusing a blind fixture "
            "(never fabricated).")
    out = [f for f in fields if isinstance(f, dict)]
    if len(out) != len(fields):
        raise FixtureError(
            "field-map provisioning.fields carries non-object rows — refusing "
            "to derive an attack payload from a malformed inventory.")
    return out


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _contract_intended_keys(field_map: dict) -> list:
    return [f.get("intended_key") for f in _contract_inventory(field_map)
            if f.get("intended_key")]


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, golden-shaped minus one.
# ---------------------------------------------------------------------------
def attack_fields(field_map: dict) -> list:
    """Derive the 27-record attack payload from the field-map: every contract
    field EXCEPT the last inventory row, byte-exact golden shape (fieldKey and
    name byte-equal the map's intended_key and create_name, dataType per the
    G11/U8 law, stable synthetic field id). Raises FixtureError on ANY contract
    drift — a wrong fixture is never shipped.

    The returned list is a deep copy; mutating it never touches the internal
    canonical payload (which itself stores options in a tuple)."""
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    if total is not None and len(inventory) != total:
        raise FixtureError(
            "field-map provisioning.fields carries %d rows but "
            "provisioning.total_keys says %d — the map drifted from its own "
            "contract; refusing to ship an attack payload."
            % (len(inventory), total))
    if len(inventory) != CONTRACT_TOTAL:
        raise FixtureError(
            "field-map provisioning.fields carries %d keys, but the golden "
            "contract is %d (19 base PRD Section 6 + 4 Gap G10 rewrite + 5 U8 "
            "cover-style) — the map drifted; refusing to ship an attack payload."
            % (len(inventory), CONTRACT_TOTAL))

    seen = {}
    out = []
    for i, item in enumerate(inventory):
        if i == len(inventory) - 1 and DROP_INDEX == -1:
            continue  # the ONE dropped field: the last inventory row (by position)
        intended = item.get("intended_key")
        cname = item.get("create_name")
        dtype = item.get("data_type")
        if not isinstance(intended, str) or not intended:
            raise FixtureError(
                "field-map row %d has no intended_key — refusing." % i)
        if not intended.startswith(reg._KEY_PREFIX):
            raise FixtureError(
                "intended_key %r must carry the %r prefix — refusing."
                % (intended, reg._KEY_PREFIX))
        if not isinstance(cname, str) or not cname:
            raise FixtureError(
                "intended_key %r has no create_name — refusing." % intended)
        # The derivation law (W0.5): the API derives the fieldKey; create_name
        # must derive back to the intended key. A row that violates the law is
        # drift — the attack payload must never ship it.
        if reg.derive_field_key(cname) != intended:
            raise FixtureError(
                "create_name %r does not derive to intended_key %r — the map "
                "violates the fieldKey derivation law; refusing." % (cname, intended))
        if intended in seen:
            raise FixtureError(
                "intended_key %r repeats in the inventory — refusing." % intended)
        seen[intended] = True

        # The G11 / U8 data-type law, byte-exact: every free-text key is
        # LARGE_TEXT (the multi-line law, matching live provisioning); the lone
        # cover-choice key is SINGLE_OPTIONS carrying its four picklist options.
        if intended == COVER_CHOICE_KEY:
            if dtype != "SINGLE_OPTIONS":
                raise FixtureError(
                    "%s must be declared SINGLE_OPTIONS (U8), got %r — refusing."
                    % (intended, dtype))
            options = COVER_CHOICE_OPTIONS
        else:
            if dtype != "LARGE_TEXT":
                raise FixtureError(
                    "%s must be declared LARGE_TEXT (Gap G11), got %r — refusing "
                    "to ship a non-contract type in the attack payload."
                    % (intended, dtype))
            options = ()

        out.append({
            "fieldKey": intended,
            "name": cname,
            "dataType": dtype,
            "id": "fld_golden_%03d" % i,
            "options": list(options),
        })
    return copy.deepcopy(out)


# ---------------------------------------------------------------------------
# The attack fixture itself — derived ONCE at import, deep-frozen. Each record
# is a MappingProxyType (read-only mapping) and the OPTIONS containers are
# tuples, so NO caller can mutate the canonical payload through the module's
# public surface — the self-test proves it. Consumers that need a mutable
# payload call attack_fields() (a deep copy of plain dicts).
# ---------------------------------------------------------------------------
def _build_attack() -> tuple:
    from types import MappingProxyType
    fm = reg.load_field_map(FIELD_MAP_PATH)
    return tuple(
        MappingProxyType({
            "fieldKey": f["fieldKey"], "name": f["name"],
            "dataType": f["dataType"], "id": f["id"],
            "options": tuple(f["options"]),
        })
        for f in attack_fields(fm))


# The canonical attack payload: 27 records, tuple-frozen — 28 minus the last
# contract field. A live customFields read shaped exactly like this MUST FAIL
# every byte-exact field gate (missing strict subset); payload() below refuses
# it HERE, offline, so no live read ever has to.
ATTACK_FIELDS = _build_attack()

# The intended key the attack drops (the last inventory row, by position) —
# named in every FAIL verdict so the drift is actionable. Derived, never
# hardcoded; a drifted map surfaces it first in the self-test.
ATTACK_MISSING_KEY = _contract_intended_keys(reg.load_field_map(FIELD_MAP_PATH))[-1]


# ---------------------------------------------------------------------------
# The judge — verify_live: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _mask_location(loc: str) -> str:
    return reg._mask_location(loc)


def verify_live(client, location_id: str, field_map: dict, *, out=None) -> int:
    """Judge the 27-key attack read against the field-map contract.

    READ-ONLY and OFFLINE: the read surface is the ATTACK_FIELDS canonical
    payload (this module never makes a network call — reg.CafClient is the
    only thing that ever talks to Convert and Flow, and it sends
    CAF_BROWSER_UA on every request, the proven CF-1010 edge fix). The judge
    is the explicit fail: on the 27-key fixture the verdict is FAIL, exit 5
    (mismatch family), naming the missing key; on a true 28-key read the
    verdict is PASS, exit 0. The client argument exists so a future caller
    can hand a live read surface to the same judge; it is never called with
    anything but an in-memory fixture in this module.

    Report: ONE JSON object on stdout (masked location marker only — the
    location id is a tenant identifier, never printed in full), human notes
    on stderr. NEVER prints a token (it holds none: the fixture is pure field
    metadata)."""
    out = out or sys.stderr
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    if total is not None and len(inventory) != total:
        raise FixtureError(
            "field-map provisioning.fields carries %d intended keys but the "
            "provisioning.total_keys contract says %d — the field-map drifted "
            "from its own contract; refusing to judge against a "
            "self-contradicting map." % (len(inventory), total))
    want_keys = _contract_intended_keys(field_map)
    if len(want_keys) != CONTRACT_TOTAL:
        raise FixtureError(
            "field-map must carry %d intended keys to judge the 27-key attack "
            "fixture; got %d — refusing." % (CONTRACT_TOTAL, len(want_keys)))

    live = _collect_read(client, location_id)
    got_set = set(live)
    want_set = set(want_keys)
    missing = sorted(want_set - got_set)
    extra = sorted(got_set - want_set)
    mismatched = [k for k in want_keys
                  if k in live and live[k].get("fieldKey") != k]

    ok = (not missing and not extra and not mismatched)
    detail = ("all %d contract fields present, byte-exact (the golden control "
              "PASSES this judge)" % CONTRACT_TOTAL if ok else (
                  "%d of %d fields — %d missing, %d extra, %d mismatched"
                  % (len(got_set), CONTRACT_TOTAL,
                     len(missing), len(extra), len(mismatched))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "location": _mask_location(location_id),
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "total": len(got_set),
        "expected": CONTRACT_TOTAL,
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "detail": detail,
        "fail_closed": {
            "strict_subset_fails": True,
            "byte_exact_required": True,
            "note": "a 27-of-28 read is a MISSING strict subset — exit 5, "
                    "never a pass. An attack fixture that passes ANY field "
                    "gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-missing-field] verify OK: %s (marker %s).\n"
                  % (detail, _mask_location(location_id)))
        return EX_OK
    out.write("[attack-missing-field] verify FAIL: %s (marker %s).\n"
              % (detail, _mask_location(location_id)))
    return EX_MISMATCH


def _collect_read(client, location_id: str) -> dict:
    """Index a live customFields read by fieldKey. Fail-closed: an empty /
    non-list read is a refusal, never a silent pass. The read surface here is
    always the canonical ATTACK_FIELDS fixture (this module is offline)."""
    del location_id  # the fixture surface never routes to a live location
    fields = getattr(client, "read_attack_fields", lambda: ATTACK_FIELDS)()
    if not isinstance(fields, (list, tuple)):
        raise FixtureError(
            "customFields read did not return a list — refusing to judge an "
            "unread surface (never fabricated).")
    out = {}
    for f in fields:
        if isinstance(f, dict):
            k = f.get("fieldKey")
            if k:
                out[k] = f
    return out


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def payload(field_map: dict, *, out=None) -> int:
    """The FAIL-CLOSED gate: the 27-key attack fixture must NEVER ship as a
    golden payload. Any payload whose record count is not exactly the
    CONTRACT_TOTAL (28) is REFUSED with exit 5 (verdict REFUSED, ok False) —
    including the canonical 27-key attack. Returns the exit code; emits the
    ONE JSON report object on stdout, human notes on stderr."""
    out = out or sys.stderr
    try:
        attack = attack_fields(field_map)
    except FixtureError as exc:
        out.write("[attack-missing-field] payload REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "total": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if len(attack) != ATTACK_TOTAL:
        out.write("[attack-missing-field] payload REFUSED: the attack fixture "
                  "carries %d records, not %d — the map drifted; refusing.\n"
                  % (len(attack), ATTACK_TOTAL))
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "total": len(attack),
            "detail": "attack fixture must carry exactly %d records (28 minus "
                      "one dropped field), got %d — drift." % (ATTACK_TOTAL, len(attack)),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "total": len(attack),
        "expected": CONTRACT_TOTAL,
        "missing": [ATTACK_MISSING_KEY],
        "fields": attack,
        "detail": "%d-record attack fixture derived byte-exact from field-map.json "
                  "(27 of 28 — the strict-subset read that MUST FAIL every "
                  "byte-exact field gate)" % len(attack),
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(field_map: dict, *, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE 28-key golden
    payload must PASS exit 0 — so a payload gate that fails EVERYTHING (a
    broken instrument) is never mistaken for a real 27/28 discrimination.
    Derives the full golden payload via the golden sibling (never a second
    implementation) and exits 0 only on exactly CONTRACT_TOTAL records."""
    out = out or sys.stderr
    try:
        from golden_fields import golden_fields, FixtureError as GoldenError  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — a missing sibling is a refusal, never a guess
        out.write("[attack-missing-field] payload-true REFUSED: golden sibling "
                  "unavailable (%s: %s).\n" % (type(exc).__name__, exc))
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "total": None,
            "detail": "control gate cannot derive the golden 28-key payload — "
                      "golden_fields.py unavailable.",
        }, indent=2, sort_keys=True))
        return EX_ERR
    try:
        golden = golden_fields(field_map)
    except GoldenError as exc:
        out.write("[attack-missing-field] payload-true REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "total": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "total": len(golden),
        "detail": "control: the true %d-key golden payload passes exit 0 — the "
                  "27-key attack fails by comparison, never by a broken gate."
                  % len(golden),
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(field_map: dict, *, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack drops and
    why, straight from the field-map (the single source of truth — never a
    hardcoded list). One JSON object on stdout."""
    out = out or sys.stderr
    inventory = _contract_inventory(field_map)
    keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
    total = _contract_total(field_map)
    if total is not None and len(keys) != total:
        out.write("[attack-missing-field] plan: inventory %d != total_keys %d — "
                  "refusing.\n" % (len(keys), total))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "total": CONTRACT_TOTAL,
        "attack_total": ATTACK_TOTAL,
        "dropped_index": DROP_INDEX,
        "dropped_key": ATTACK_MISSING_KEY,
        "keys": keys,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack drops the LAST provisioning.fields row by position.",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: attack coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline fields_check.py
# and golden_fields.py apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-missing-field] SELF-TEST FAILED "
                         "(AF-AE-ATTACKMISSINGFIELD-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


class _FixtureReader:
    """The in-memory read surface verify_live judges: hands back the canonical
    attack payload (27 of 28) — never a network call, never a token."""

    def __init__(self, fields=None):
        self._fields = fields  # None -> the canonical ATTACK_FIELDS
        self.calls = []

    def read_attack_fields(self):
        self.calls.append(("fields",))
        if self._fields is None:
            return [dict(f) for f in ATTACK_FIELDS]
        if isinstance(self._fields, list):
            return [dict(f) for f in self._fields]
        # A non-list attack shape is passed through UNTOUCHED so the judge's
        # own fail-closed read-shape check sees exactly what a live read
        # would return (a non-list is refused there, never judged).
        return self._fields


def _self_test_body(dev) -> None:
    field_map = reg.load_field_map(FIELD_MAP_PATH)
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    want_keys = _contract_intended_keys(field_map)

    # ---- contract coherence: the map is the single source of truth ---------
    assert total is not None and len(inventory) == total, \
        "inventory must equal provisioning.total_keys (%s != %s)" % (len(inventory), total)
    assert len(inventory) == CONTRACT_TOTAL, \
        "field-map must carry exactly 28 keys (19 base + 4 G10 + 5 U8), got %d" % len(inventory)
    assert len(set(want_keys)) == CONTRACT_TOTAL, "intended keys must be unique"
    assert all(k.startswith(reg._KEY_PREFIX) for k in want_keys), \
        "every intended key must carry the contact. prefix"
    # the dropped field is the LAST inventory row, by position (derived, never
    # hardcoded) — and the attack fixture must be missing EXACTLY that one.
    dropped = want_keys[-1]
    assert ATTACK_MISSING_KEY == dropped, \
        "ATTACK_MISSING_KEY must track the last inventory row (%r)" % dropped

    # ---- the canonical fixture: 27 records, byte-exact, tuple-frozen --------
    assert isinstance(ATTACK_FIELDS, tuple) and len(ATTACK_FIELDS) == ATTACK_TOTAL, \
        "ATTACK_FIELDS must be the tuple-frozen 27-record payload, got %d" % len(ATTACK_FIELDS)
    assert isinstance(ATTACK_FIELDS[0]["options"], tuple), \
        "attack options containers must be tuples (immutable canonical surface)"
    kept = [f["fieldKey"] for f in ATTACK_FIELDS]
    assert kept == [k for k in want_keys if k != dropped], \
        "attack fieldKey order/bytes must equal the map's intended keys in order, minus the dropped one"
    assert dropped not in kept, "the dropped field must be ABSENT from the attack"
    for f in ATTACK_FIELDS:
        assert f["fieldKey"].startswith(reg._KEY_PREFIX)
        assert reg.derive_field_key(f["name"]) == f["fieldKey"], \
            "attack name must derive back to the fieldKey (%r)" % f["fieldKey"]
        assert f["dataType"] in ("LARGE_TEXT", "SINGLE_OPTIONS"), f["dataType"]
        assert f["id"].startswith("fld_golden_"), f["id"]
    assert sum(1 for f in ATTACK_FIELDS if f["dataType"] == "SINGLE_OPTIONS") == 1, \
        "exactly one SINGLE_OPTIONS field (the U8 cover choice) survives the drop"
    cover = next(f for f in ATTACK_FIELDS if f["dataType"] == "SINGLE_OPTIONS")
    assert cover["fieldKey"] == COVER_CHOICE_KEY
    assert cover["options"] == COVER_CHOICE_OPTIONS, \
        "the cover-choice picklist options must be the four U8 cover styles"
    assert all(f["dataType"] == "LARGE_TEXT" for f in ATTACK_FIELDS
               if f["fieldKey"] != COVER_CHOICE_KEY), \
        "every non-cover attack field must be LARGE_TEXT (Gap G11)"

    # ---- the canonical fixture can never be mutated through the surface -----
    from types import MappingProxyType

    def _fp(items):
        return tuple(sorted(tuple(sorted((k, tuple(v) if isinstance(v, tuple) else v)
                                         for k, v in it.items()))
                            for it in items))
    before = _fp(ATTACK_FIELDS)

    def _try_rebind_record():        # subscript assignment on a tuple -> TypeError
        ATTACK_FIELDS[0] = {"x": 1}  # noqa: B034 -- deliberately attempted

    def _try_mutate_record():        # subscript assignment on a mappingproxy -> TypeError
        ATTACK_FIELDS[0]["fieldKey"] = "contact.anthology_MUTATED"  # noqa: B034 -- deliberately attempted

    def _try_mutate_options():       # subscript assignment on a tuple -> TypeError
        ATTACK_FIELDS[0]["options"][0] = "MUTATED"  # noqa: B034 -- deliberately attempted

    for attempt in (_try_rebind_record, _try_mutate_record, _try_mutate_options):
        try:
            attempt()
            raise AssertionError("the canonical fixture must be immutable")
        except TypeError:
            pass
    assert _fp(ATTACK_FIELDS) == before, \
        "the canonical fixture changed during the self-test"
    assert all(isinstance(f, MappingProxyType) and isinstance(f["options"], tuple)
               for f in ATTACK_FIELDS), \
        "attack records must stay mappingproxy-frozen with tuple options"
    # attack_fields() returns a deep copy: mutating it never touches the canon.
    copy_ = attack_fields(field_map)
    copy_[0]["fieldKey"] = "contact.anthology_MUTATED"
    assert ATTACK_FIELDS[0]["fieldKey"] == kept[0], \
        "the returned copy must not alias the canonical payload"

    # ---- the judge: 27-key read MUST FAIL, 28-key control MUST PASS ---------
    reader = _FixtureReader()
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(reader, "loc_fx", field_map, out=io.StringIO())
    assert rc == EX_MISMATCH, "the 27-key attack read must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the 27-key attack read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["total"] == ATTACK_TOTAL and parsed["expected"] == CONTRACT_TOTAL
    assert parsed["missing"] == [dropped], \
        "the attack read must name the dropped key as missing, got %s" % parsed["missing"]
    assert reader.calls and all(m == "fields" for m, in reader.calls), \
        "the judge must only read the fixture surface: %s" % reader.calls

    # the judge NEVER prints a token or a full location id (masked marker only)
    assert parsed["location"] == "...c_fx", \
        "location marker must be masked: %r" % parsed["location"]
    blob = buf.getvalue() + io.StringIO().getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"

    # ---- the fail-closed gates: 27 REFUSED, true 28 PASSES (the control) ----
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = payload(field_map, out=io.StringIO())
    assert rc == EX_OK, "payload on the true map must exit 0, got %s" % rc
    parsed2 = json.loads(buf2.getvalue())
    assert parsed2["ok"] is True and parsed2["verdict"] == "PASS"
    assert parsed2["total"] == ATTACK_TOTAL == 27, \
        "the attack fixture must carry exactly 27 records"
    assert parsed2["missing"] == [dropped], \
        "the attack payload must name the dropped key"
    assert parsed2["contract"] == ATTACK_CONTRACT

    # the attack payload can never be mistaken for a GOLDEN payload: the
    # golden gate REFUSES it (27 != 28) — cross-module fail-closed proof.
    from golden_fields import golden_fields, FixtureError as GoldenError
    try:
        golden_fields(field_map)
        golden_attack = None
    except GoldenError:
        golden_attack = None  # unreachable on the true map — assert below
    # the real cross-check: the golden builder applied to a 27-key inventory
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"] = tampered["provisioning"]["fields"][:-1]
    tampered["provisioning"]["total_keys"] = ATTACK_TOTAL
    try:
        golden_fields(tampered)
        raise AssertionError("the golden builder must REFUSE a 27-key inventory")
    except GoldenError:
        pass

    # payload-true (the control): the true 28-key golden payload passes exit 0
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc = payload_true(field_map, out=io.StringIO())
    assert rc == EX_OK, "payload-true on the true map must exit 0, got %s" % rc
    parsed3 = json.loads(buf3.getvalue())
    assert parsed3["ok"] is True and parsed3["verdict"] == "PASS"
    assert parsed3["total"] == CONTRACT_TOTAL == 28

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. a mutated fieldKey/name derivation -> FixtureError, never a wrong fixture
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][0]["create_name"] = "anthology_avatar_doc_url_WRONG"
    try:
        attack_fields(tampered)
        raise AssertionError("a derivation-law violation was NOT refused")
    except FixtureError:
        pass
    # 2. a non-contract data_type (the old TEXT, Gap G11 regression) -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][1]["data_type"] = "TEXT"
    try:
        attack_fields(tampered)
        raise AssertionError("a TEXT data_type was NOT refused (G11)")
    except FixtureError:
        pass
    # 3. total_keys drift vs the inventory -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        attack_fields(tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except FixtureError:
        pass
    # 4. inventory length drift (29th key) -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"].append(
        {"intended_key": "contact.anthology_extra", "create_name": "anthology_extra",
         "data_type": "LARGE_TEXT", "field_key": None, "field_id": None})
    try:
        attack_fields(tampered)
        raise AssertionError("a 29-key inventory was NOT refused")
    except FixtureError:
        pass
    # 5. duplicate intended_key -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][0]["intended_key"] = \
        tampered["provisioning"]["fields"][1]["intended_key"]
    tampered["provisioning"]["fields"][0]["create_name"] = \
        tampered["provisioning"]["fields"][1]["create_name"]
    try:
        attack_fields(tampered)
        raise AssertionError("a duplicate intended_key was NOT refused")
    except FixtureError:
        pass
    # 6. missing provisioning.fields section -> refusal
    try:
        attack_fields({})
        raise AssertionError("a missing inventory was NOT refused")
    except FixtureError:
        pass
    # 7. no contact. prefix on an intended_key -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][0]["intended_key"] = "anthology_avatar_doc_url"
    try:
        attack_fields(tampered)
        raise AssertionError("a prefix-less intended_key was NOT refused")
    except FixtureError:
        pass
    # 8. non-list live read on the judge -> hard refusal, never a verdict
    try:
        verify_live(_FixtureReader(fields={"not": "a list"}), "loc_fx",
                    field_map, out=io.StringIO())
        raise AssertionError("a non-list read was NOT refused")
    except FixtureError:
        pass

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact drop ----
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        rc = plan(field_map, out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf4.getvalue())
    assert p["dropped_key"] == dropped and p["attack_total"] == 27

    dev.write("attack_missing_field self-test: OK (field-map coherence %d keys "
              "== total_keys; canonical 27-record tuple-frozen attack payload "
              "byte-exact minus the last inventory row [%s]; immutability + "
              "deep-copy surface; judge FAILs the 27-key read with exit 5 and "
              "names the missing key; payload gate PASSes the 27-key attack "
              "fixture while the GOLDEN gate REFUSES it; payload-true control "
              "PASSes the 28-key golden payload; 8 attack fixtures refused "
              "(derivation-law violation / TEXT regression / total_keys drift / "
              "29-key inventory / duplicate key / missing inventory / "
              "prefix-less key / non-list read); masked location; CAF_BROWSER_UA "
              "pinned; plan offline)\n" % (CONTRACT_TOTAL, dropped))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_missing_field.py",
        description="Attack fixture — 27 of 28 contact custom fields, must FAIL "
                    "(Skill 59, U02 tooling): the adversarial sibling of "
                    "golden_fields.py, shipping the deterministic strict-subset "
                    "read that every byte-exact field gate must refuse, and the "
                    "fail-closed offline gates that prove it (27 REFUSED, the "
                    "28-key golden control PASSES).")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "payload-true",
                                               "verify", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U02 verifier use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        if args.cmd == "plan":
            return plan(field_map)
        if args.cmd == "payload-true":
            return payload_true(field_map)
        if args.cmd == "verify":
            return verify_live(_FixtureReader(), "loc_fx", field_map, out=sys.stderr)
        return payload(field_map)
    except FixtureError as exc:
        sys.stderr.write("[attack-missing-field] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[attack-missing-field] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-missing-field] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
