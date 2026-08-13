#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/golden_fields.py
# GOLDEN FIELD-LIST FIXTURE (U02 tooling, extension module) — the single
# canonical in-memory payload of the 28 contact custom fields a live Convert
# and Flow location must carry, derived BYTE-FOR-BYTE from
# config/field-map.json provisioning.fields (the single source of truth).
#
# WHERE THIS SITS: scripts/u02_modules/ — an importable module under the U02
# template-verify tooling, exactly like its sibling fields_check.py. It is NOT
# a manifest row and NOT a checker: it ships the GOLDEN fixture surface the
# self-tests of the U02 verifier and its sibling checkers assert against, so
# every checker's happy path is judged against the SAME payload and a drift in
# the field-map contract breaks THIS module's self-test first (fail-closed:
# an inconsistent map is a refusal, never a blind pass).
#
# WHAT THIS OWNS:
#   1. GOLDEN_FIELDS — a frozen, deterministic list of the 28 field records
#      ({fieldKey, name, dataType, id, options}) as a live customFields read
#      would return them: fieldKey and name byte-equal the map's intended_key
#      and create_name, dataType carries the map's declared type (LARGE_TEXT
#      for every free-text key, Gap G11; SINGLE_OPTIONS for the lone U8
#      cover-choice key, with its four picklist options), and each record
#      carries a stable synthetic field id (fld_golden_000 .. fld_golden_027).
#      The canonical payload is DEEP-FROZEN: the tuple of records is a tuple of
#      MappingProxyType records (stdlib types module) whose OPTIONS containers
#      are tuples, so a golden record can never be mutated through the module's
#      public surface — the self-test proves every mutation route raises.
#   2. golden_fields() — the builder, fail-closed: a missing/malformed
#      provisioning.fields inventory or an intended_key/create_name/data_type
#      that does not satisfy the contract (28 keys, unique, contact.-prefixed,
#      derive-roundtrip clean, declared types matching the G11/U8 law) raises
#      FixtureError instead of shipping a wrong fixture. 28 is the contract
#      total (19 base PRD Section 6 link/control keys + 4 Gap G10
#      chapter-rewrite-preservation keys + 5 U8 cover-style keys).
#   3. golden_field_ids() — the sorted fieldKey -> id map, for the resolved-
#      slot surfaces (a resolved per-box field-map must pin the SAME ids).
#   4. payload — a FAIL-CLOSED byte-level invariant on the field-map itself:
#      the map's provisioning.total_keys must equal the inventory length AND
#      this fixture's golden length, and a tampered map (a map whose golden
#      payload would not carry 28 fields) is REFUSED with exit 5, never
#      silently tolerated.
#
# DOCTRINE (inherited from the registry / drive adapter / U02 verifier):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT SET).
#   - Fail-closed: a malformed map, an absent section, a non-object read all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The field-list surface this fixture emulates is the PUBLIC v2 custom
#     fields read. Any module that talks to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry the
#     browser User-Agent on every request — urllib's default "Python-urllib/x.y"
#     is 403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). This
#     module itself makes NO network call; the client that DOES (reg.CafClient)
#     already sends CAF_BROWSER_UA on every request — the proven edge fix.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier):
#   0  verified success — the golden fixture is internally consistent and
#      byte-equal to the field-map contract; also self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON)
#   5  mismatch — the field-map drifted from the fixture contract (inventory
#      length != 28, or total_keys != the inventory length), a derived golden
#      fieldKey/name/data_type deviates from the map, or a non-contract
#      data_type would ship in the payload (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# fields_check.py / live_verify_template.py: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""golden_fields.py — golden field-list payload fixture (28 keys) for self-test."""

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

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. The 28 field KEYS themselves are NEVER
# hardcoded here — they come from the field-map (the single source of truth);
# a hardcoded key list would drift and defeat the fixture's whole purpose.
FIXTURE_CONTRACT = "anthology-engine-golden-fields"

# The contract total, fixed by the PRD (19 base Section 6 link/control keys +
# 4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys). The
# golden fixture asserts this exact number — a map that carries more or fewer
# keys has drifted and the fixture refuses to ship.
CONTRACT_TOTAL = 28

# The ONE non-free-text field in the contract (PRD Section 6 / U8): the
# cover-choice picklist. Everything else must be LARGE_TEXT (Gap G11). The
# picklist's four options are the named cover styles the client picks from.
COVER_CHOICE_KEY = "contact.anthology_cover_choice"
COVER_CHOICE_OPTIONS = ("Signature", "Bold Editorial", "Fine Art", "Pure Type")


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
            "field-map.json has no provisioning.fields inventory — the golden "
            "field-list payload has nothing to derive from; refusing a blind "
            "fixture (never fabricated).")
    out = [f for f in fields if isinstance(f, dict)]
    if len(out) != len(fields):
        raise FixtureError(
            "field-map provisioning.fields carries non-object rows — refusing "
            "to derive a golden payload from a malformed inventory.")
    return out


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, byte-equal to the map.
# ---------------------------------------------------------------------------
def golden_fields(field_map: dict) -> list:
    """Derive the golden field-list payload (28 records) from the field-map.

    Each record is EXACTLY what a live /locations/{id}/customFields read of a
    fully provisioned location returns: fieldKey and name byte-equal the map's
    intended_key and create_name, dataType carries the map's declared type
    (LARGE_TEXT for every free-text key, SINGLE_OPTIONS + its picklist options
    for the lone U8 cover choice), and a stable synthetic field id. Raises
    FixtureError on ANY contract drift — a wrong fixture is never shipped.

    The returned list is a deep copy; mutating it never touches the internal
    canonical payload (which itself stores options in a tuple)."""
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)
    if total is not None and len(inventory) != total:
        raise FixtureError(
            "field-map provisioning.fields carries %d rows but "
            "provisioning.total_keys says %d — the map drifted from its own "
            "contract; refusing to ship a golden payload."
            % (len(inventory), total))
    if len(inventory) != CONTRACT_TOTAL:
        raise FixtureError(
            "field-map provisioning.fields carries %d keys, but the golden "
            "contract is %d (19 base PRD Section 6 + 4 Gap G10 rewrite + 5 U8 "
            "cover-style) — the map drifted; refusing to ship a golden payload."
            % (len(inventory), CONTRACT_TOTAL))

    seen = {}
    out = []
    for i, item in enumerate(inventory):
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
        # drift — the golden payload must never ship it.
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
                    "to ship a non-contract type in the golden payload."
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


def golden_field_ids(field_map: dict) -> dict:
    """The sorted fieldKey -> golden field id map (the resolved-slot surface).

    A per-box provisioned field-map pins field_id slots; those slots must be
    CONSISTENT with this fixture's ids so a live read-back of the golden
    payload satisfies the id-consistency check of fields_check.py. The map is
    the source of truth for the ids, sorted deterministically (the customFields
    read returns no ordering contract)."""
    return {f["fieldKey"]: f["id"] for f in
            sorted(golden_fields(field_map), key=lambda f: f["fieldKey"])}


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. Each record
# is a MappingProxyType (read-only mapping) and the OPTIONS containers are
# tuples, so NO caller can mutate the canonical payload through the module's
# public surface — the self-test proves it. Consumers that need a mutable
# payload call golden_fields() (a deep copy of plain dicts).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    fm = reg.load_field_map(FIELD_MAP_PATH)
    return tuple(
        MappingProxyType({
            "fieldKey": f["fieldKey"], "name": f["name"],
            "dataType": f["dataType"], "id": f["id"],
            "options": tuple(f["options"]),
        })
        for f in golden_fields(fm))


# The canonical golden field-list payload: 28 records, deep-frozen (a tuple
# of mappingproxy records with tuple options — immutable through every route).
GOLDEN_FIELDS = _build_golden()


# ---------------------------------------------------------------------------
# Fail-closed payload invariant — the offline gate the self-test and `--plan`
# both ride on. A drifted field-map is REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def payload(field_map: dict, *, out=None) -> int:
    """Validate the field-map against the golden field-list contract.

    READ-ONLY: derives the golden payload and asserts the byte-level invariant
    — the map's provisioning.total_keys must equal the inventory length AND the
    golden length (28). Any drift is a FAIL-CLOSED exit 5, never a blind pass.
    The field keys themselves are never hardcoded (the map is the single source
    of truth); the CONTRACT TOTAL (28) is pinned by the PRD. Returns the exit
    code; emits the ONE JSON report object on stdout, human notes on stderr."""
    out = out or sys.stderr
    try:
        golden = golden_fields(field_map)
    except FixtureError as exc:
        out.write("[golden-fields] payload REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "total": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "total": len(golden),
        "fields": golden,
        "detail": "%d golden field records derived byte-exact from field-map.json"
                  % len(golden),
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline fields_check.py applies.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-fields] SELF-TEST FAILED "
                         "(AF-AE-GOLDENFIELDS-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    field_map = reg.load_field_map(FIELD_MAP_PATH)
    inventory = _contract_inventory(field_map)
    total = _contract_total(field_map)

    # ---- contract coherence: the map is the single source of truth ---------
    assert total is not None and len(inventory) == total, \
        "inventory must equal provisioning.total_keys (%s != %s)" % (len(inventory), total)
    assert len(inventory) == CONTRACT_TOTAL, \
        "field-map must carry exactly 28 keys (19 base + 4 G10 + 5 U8), got %d" % len(inventory)
    assert len(set(f.get("intended_key") for f in inventory)) == CONTRACT_TOTAL, \
        "intended keys must be unique"
    assert all(str(f.get("intended_key", "")).startswith(reg._KEY_PREFIX) for f in inventory), \
        "every intended key must carry the contact. prefix"

    # ---- the canonical fixture: 28 records, byte-exact, deep-frozen ---------
    assert isinstance(GOLDEN_FIELDS, tuple) and len(GOLDEN_FIELDS) == CONTRACT_TOTAL, \
        "GOLDEN_FIELDS must be the deep-frozen 28-record payload"
    assert isinstance(GOLDEN_FIELDS[0]["options"], tuple), \
        "golden options containers must be tuples (immutable canonical surface)"
    want_keys = [f["fieldKey"] for f in GOLDEN_FIELDS]
    assert want_keys == [f.get("intended_key") for f in inventory], \
        "golden fieldKey order/bytes must equal the map's intended keys in order"
    for f in GOLDEN_FIELDS:
        assert f["fieldKey"].startswith(reg._KEY_PREFIX)
        assert reg.derive_field_key(f["name"]) == f["fieldKey"], \
            "golden name must derive back to the fieldKey (%r)" % f["fieldKey"]
        assert f["dataType"] in ("LARGE_TEXT", "SINGLE_OPTIONS"), f["dataType"]
        assert f["id"].startswith("fld_golden_"), f["id"]
    assert sum(1 for f in GOLDEN_FIELDS if f["dataType"] == "SINGLE_OPTIONS") == 1, \
        "exactly one SINGLE_OPTIONS field (the U8 cover choice)"
    cover = next(f for f in GOLDEN_FIELDS if f["dataType"] == "SINGLE_OPTIONS")
    assert cover["fieldKey"] == COVER_CHOICE_KEY
    assert cover["options"] == COVER_CHOICE_OPTIONS, \
        "the cover-choice picklist options must be the four U8 cover styles"
    assert all(f["dataType"] == "LARGE_TEXT" for f in GOLDEN_FIELDS
               if f["fieldKey"] != COVER_CHOICE_KEY), \
        "every non-cover field must be LARGE_TEXT (Gap G11)"
    # Gap G10: the four rewrite-preservation keys are present and distinct from
    # the base chapter pair, so a rewrite can never overwrite the original.
    for slot in ("rewrite1_doc_url", "rewrite1_pdf_url", "rewrite2_doc_url", "rewrite2_pdf_url"):
        assert ("contact.anthology_chapter_%s" % slot) in want_keys, "G10 missing %s" % slot
    assert "contact.anthology_chapter_doc_url" in want_keys and \
           "contact.anthology_chapter_rewrite1_doc_url" in want_keys, \
        "G10 base + rewrite1 both present"
    # every PRD Section 6 deliverable + control key AND the U8 cover-style keys
    # are represented (the same inventory-drift gate the registry self-test runs).
    contract_keys = set()
    for pair in field_map["deliverable_fields"].values():
        contract_keys.update(pair.values())
    contract_keys.update(field_map["control_fields"].values())
    csf = field_map.get("cover_style_fields") or {}
    contract_keys.update((csf.get("sample_url_fields") or {}).values())
    if csf.get("choice_field"):
        contract_keys.add(csf["choice_field"])
    assert contract_keys == set(want_keys), \
        "inventory drifted from the deliverable/control/cover-style contract"

    # ---- the id map is deterministic and covers every key -------------------
    ids = golden_field_ids(field_map)
    assert len(ids) == CONTRACT_TOTAL and sorted(ids) == sorted(want_keys)
    for k, v in ids.items():
        assert v.startswith("fld_golden_") and v in {f["id"] for f in GOLDEN_FIELDS}

    # ---- the canonical fixture can never be mutated through the surface -----
    from types import MappingProxyType
    # a structural fingerprint that does not depend on json.dumps (the frozen
    # MappingProxyType records are not JSON-serializable, and that is intended).
    def _fp(items):
        return tuple(sorted(tuple(sorted((k, tuple(v) if isinstance(v, tuple) else v)
                                         for k, v in it.items()))
                            for it in items))
    before = _fp(GOLDEN_FIELDS)

    def _try_rebind_record():        # subscript assignment on a tuple -> TypeError
        GOLDEN_FIELDS[0] = {"x": 1}  # noqa: B034 -- deliberately attempted

    def _try_mutate_record():        # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_FIELDS[0]["fieldKey"] = "contact.anthology_MUTATED"  # noqa: B034 -- deliberately attempted

    def _try_mutate_options():       # subscript assignment on a tuple -> TypeError
        GOLDEN_FIELDS[0]["options"][0] = "MUTATED"  # noqa: B034 -- deliberately attempted

    for attempt in (_try_rebind_record, _try_mutate_record, _try_mutate_options):
        try:
            attempt()
            raise AssertionError("the canonical fixture must be immutable")
        except TypeError:
            pass
    assert _fp(GOLDEN_FIELDS) == before, \
        "the canonical fixture changed during the self-test"
    assert all(isinstance(f, MappingProxyType) and isinstance(f["options"], tuple)
               for f in GOLDEN_FIELDS), \
        "golden records must stay mappingproxy-frozen with tuple options"
    # golden_fields() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_fields(field_map)
    copy_[0]["fieldKey"] = "contact.anthology_MUTATED"
    assert GOLDEN_FIELDS[0]["fieldKey"] == want_keys[0], \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a mutated fieldKey/name derivation -> FixtureError, never a wrong fixture
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][0]["create_name"] = "anthology_avatar_doc_url_WRONG"
    try:
        golden_fields(tampered)
        raise AssertionError("a derivation-law violation was NOT refused")
    except FixtureError:
        pass
    # 2. a non-contract data_type (the old TEXT, Gap G11 regression) -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][1]["data_type"] = "TEXT"
    try:
        golden_fields(tampered)
        raise AssertionError("a TEXT data_type was NOT refused (G11)")
    except FixtureError:
        pass
    # 3. total_keys drift vs the inventory -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        golden_fields(tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except FixtureError:
        pass
    # 4. inventory length drift (29th key) -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"].append(
        {"intended_key": "contact.anthology_extra", "create_name": "anthology_extra",
         "data_type": "LARGE_TEXT", "field_key": None, "field_id": None})
    try:
        golden_fields(tampered)
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
        golden_fields(tampered)
        raise AssertionError("a duplicate intended_key was NOT refused")
    except FixtureError:
        pass
    # 6. missing provisioning.fields section -> refusal
    try:
        golden_fields({})
        raise AssertionError("a missing inventory was NOT refused")
    except FixtureError:
        pass
    # 7. no contact. prefix on an intended_key -> refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["fields"][0]["intended_key"] = "anthology_avatar_doc_url"
    try:
        golden_fields(tampered)
        raise AssertionError("a prefix-less intended_key was NOT refused")
    except FixtureError:
        pass

    # ---- payload: the fail-closed gate exits 0 on the true map, 5 on drift --
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(field_map, out=io.StringIO())
    assert rc == EX_OK, "payload on the true map must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["total"] == CONTRACT_TOTAL and len(parsed["fields"]) == CONTRACT_TOTAL
    assert parsed["contract"] == FIXTURE_CONTRACT
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = payload(tampered_total_keys(field_map), out=io.StringIO())
    assert rc == EX_MISMATCH, "payload on a drifted map must exit 5, got %s" % rc
    parsed2 = json.loads(buf2.getvalue())
    assert parsed2["ok"] is False and parsed2["verdict"] == "REFUSED", \
        "a drifted payload must be REFUSED, never shipped"

    dev.write("golden_fields self-test: OK (%d keys == total_keys == golden "
              "length; byte-exact fieldKey/name/dataType; G10 rewrite pairs + "
              "U8 SINGLE_OPTIONS picklist present; 7 attack fixtures refused "
              "(derivation-law violation / TEXT regression / total_keys drift / "
              "29-key inventory / duplicate key / missing inventory / prefix-less "
              "key); canonical deep-frozen immutability + deep-copy surface; "
              "payload gate exits 0 / drifts to exit 5)\n" % CONTRACT_TOTAL)


def tampered_total_keys(field_map: dict) -> dict:
    """A deep copy of the field-map with provisioning.total_keys bumped by one
    (the drift fixture the payload gate must REFUSE with exit 5)."""
    out = copy.deepcopy(field_map)
    out["provisioning"]["total_keys"] = (_contract_total(out) or 0) + 1
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_fields.py",
        description="Golden field-list payload fixture (28 keys) for the U02 "
                    "self-tests (Skill 59): derive the canonical customFields "
                    "payload byte-exact from config/field-map.json, fail-closed.")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
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
            # Offline plan (no network, no credentials): the 28 intended keys
            # the golden payload carries, straight from the field-map — never a
            # hardcoded list. One JSON object on stdout.
            inventory = _contract_inventory(field_map)
            keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
            total = _contract_total(field_map)
            if total is not None and len(keys) != total:
                sys.stderr.write("[golden-fields] plan: inventory %d != "
                                 "total_keys %d — refusing.\n" % (len(keys), total))
                return EX_MISMATCH
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "total": len(keys),
                "keys": keys,
                "dry_run": True,
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK
        return payload(field_map)
    except FixtureError as exc:
        sys.stderr.write("[golden-fields] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[golden-fields] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-fields] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
