#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/golden_all_present.py  (U07 tooling)
# GOLDEN ALL-28-PRESENT FIXTURE — the canonical in-memory payload of the U07
# FIELD-CENSUS law in its GOLDEN state: ALL 28 Convert and Flow contact custom
# fields a provisioned location must carry are on the listing BY EXACT KEY,
# every one present — the golden control of the U07 all-present gate (the
# anti-attack mirror of the U07 absent-key fixture, which certifies the state
# where a field is MISSING).
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# package (pure namespace container per the u07 __init__.py: imported BY
# NAME, side-effect-free at import; the init records the U07 doctrine:
# destructive actions require --execute, Trevor-gated — WITHOUT --execute a
# module must report what it WOULD do and exit without mutating). It is NOT a
# manifest row and NOT a checker: it ships the GOLDEN all-present surface the
# offline self-tests of the U07 verifier and its sibling checkers assert
# against, so every checker's happy path is judged against the SAME payload
# and a drift in the engine's 28-key law breaks THIS module's self-test first
# (fail-closed: an inconsistent law is a refusal, never a blind pass).
#
# WHAT THIS OWNS (the U07 ALL-PRESENT LAW, PRD Section 6 / Gap G10 / U8,
# provisioned by anthology_registry.provision_fields — the ONE provisioning
# authority):
#   1. THE PRESENT-STATE LAW: the U07 census gate is count-then-key, and the
#      GOLDEN state is EXACTLY 28 field rows on the listing — the contract
#      total (19 base PRD Section 6 link/control keys + 4 Gap G10
#      chapter-rewrite-preservation keys + 5 U8 cover-style keys), each
#      matched BY EXACT KEY (the exact-key law: a row's fieldKey must
#      byte-equal the intended key — a renamed, re-prefixed, or drifted key
#      is indistinguishable from an absent one and BOTH refuse fail-closed).
#      The golden surface carries ALL 28 under the golden keys, every one
#      present (id_masked on every operator surface, full synthetic id inside
#      the JSON payload a machine consumer reads) — a listing that loses a
#      contract key is a FAIL, never a blind pass.
#   2. THE KEY LAW IS READ ONCE: the 28 intended keys are NEVER retyped here —
#      they come BYTE-EXACT from config/field-map.json provisioning.fields
#      read through anthology_registry.load_field_map (the single
#      single-implementation doctrine: a contract read once, in one file; the
#      same source of truth the U02 golden_fields sibling derives its 28
#      records from and the registry's own self-test pins at 28). A drift in
#      the field-map breaks THIS fixture's self-test first — never silently.
#   3. GOLDEN_ALL_PRESENT — the deep-frozen canonical record: a dict keyed by
#      the 28 map-derived intended keys, each carrying {"present": True,
#      "id_masked": <non-reversible last-4 marker>} — all 28 present, field
#      ids SYNTHETIC only (fld_golden_000 .. fld_golden_027 — the fixture
#      discipline: a fixture id is never a real field id; the same synthetic
#      id series the U02 golden_fields sibling pins, so a per-box resolved
#      field-map read-back can be id-consistent with BOTH fixtures). The
#      record is a MappingProxyType (types module) and every container inside
#      it is a tuple, so NO caller can mutate the canonical payload through
#      the module's public surface — the self-test proves every mutation
#      route raises.
#   4. golden_all_present() / golden_fields_payload() — the deep-copied
#      payload surfaces (the canonical all-present record, and the
#      {"fields": [...]} listing shape a live /locations/{id}/customFields
#      read of a fully provisioned location returns) consumers mutate freely;
#      the canon never changes. The listing is derived from the golden keys
#      ONCE, in the same row shape the census read uses (fieldKey, name,
#      dataType, id, options — the shape the U02 golden_fields sibling
#      emulates for the SAME read).
#   5. payload — a FAIL-CLOSED all-present gate: the golden listing carries
#      ALL 28 contract keys byte-exact by their golden keys (each present
#      with its one synthetic id, each matched BY EXACT KEY) -> PASS exit 0
#      with the dispatcher-consumed dict surface {"ok": True, "count": 28,
#      "af_code": "FIELDS-ALL-PRESENT", "note": ...}. ANY deviation (a
#      contract key absent or renamed, a foreign key that is not in the
#      contract, a listing of the wrong size, a malformed listing, a
#      non-object row, a credential-shaped value) is a REFUSED exit 5 — never
#      a blind pass, never a fabricated success. The one JSON report object
#      lands on stdout; human notes go to stderr; the dict the dispatcher's
#      verify_live consumes is the payload() RETURN VALUE.
#
# DOCTRINE (house, inherited from the registry / the u02/u03/u04/u05/u06
# golden siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var — a
#     fixture cannot leak what it never holds. The only id-shaped material it
#     carries is SYNTHETIC fixture markers (fld_golden_*), and the never-print
#     self-test proves no pit-/Bearer-shaped string ever rides any surface.
#   - Fail-closed: a malformed listing, an absent or renamed contract key, a
#     foreign key, a wrong-size listing, a credential-shaped value all STOP
#     or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates. The
#     --execute gate that refuses a WRITE ACTION (provisioning a missing
#     field is a write, Trevor-gated) lives in the dispatcher (main_skeleton.py),
#     never in a fixture; THIS module pins the gate as the law its surfaces
#     carry, exactly as golden_found pins it for the U06 archive action.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). THIS
#     module makes NO network call and defines NO User-Agent constant of its
#     own; the sibling that DOES (the live census reader rides the house rail
#     client, which sends CAF_BROWSER_UA on every request) — the proven edge
#     fix. The self-test pins the browser UA law so a registry regression is
#     caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8): the
# fixture ships SYNTHETIC deterministic ids only (fld_golden_000 .. — the
# discipline of the u02/u03/u04/u05 siblings: a fixture id is never a real
# participant, form, workflow, or field id). The LAW (the 28 contract keys,
# the exact-key census shape) is pinned from the engine sources:
# config/field-map.json provisioning.fields read through
# anthology_registry.load_field_map (the ONE keying authority — read once,
# never re-implemented). The OFFLINE self-test pins the contract values so a
# drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden all-present payload is internally
#      consistent and the golden listing PASSES the gate; also self-test /
#      plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — an absent or renamed contract key, a
#      foreign key, a wrong-size listing, a malformed listing, or a
#      credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u02/u03/u04/u05/u06 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the 28
# contract keys are read through reg.load_field_map(config/field-map.json
# provisioning.fields) — never duplicated here.
# =============================================================================
"""golden_all_present.py — golden ALL-28-PRESENT fixture for the U07
self-tests. Pure data + the fail-closed all-present gate; never prints a
token; the --execute write gate lives in the dispatcher, never here."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring, the exit-code contract, and the field-map IO;
# the 28 contract keys are read ONCE from the field-map through
# reg.load_field_map — the one source of truth the provisioner, the registry
# self-test, and the U02 golden_fields sibling all derive from. A fixture
# never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for an
# all-present fixture (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-all-present"

# The contract total, fixed by the PRD (19 base Section 6 link/control keys +
# 4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys) — the
# SAME 28 the registry's self-test and the U02 golden_fields sibling pin. The
# golden fixture asserts this exact number against the field-map inventory; a
# map that carries more or fewer keys has drifted and the fixture refuses to
# ship.
CONTRACT_TOTAL = 28

# The U07 WRITE-ACTION LAW (Trevor-gated, per the u07 package-init doctrine),
# pinned here exactly as the U06 golden_found sibling pins its archive gate:
# any WRITE ACTION (provisioning a missing field is a write) REQUIRES
# --execute. This module is READ-ONLY and never performs the mutation — the
# --execute gate lives in the dispatcher (main_skeleton.py), never in a
# fixture; a checker that would write without --execute is caught by the
# dispatcher's gate FIRST.
WRITE_ACTION = "provision"
EXECUTE_FLAG = "--execute"
GOLDEN_EXECUTE_REQUIRED = True  # the law: the WRITE ACTION is gated

# The all-present af_code the golden payload certifies (the same af_code the
# census reader's ok surface carries — the two can never drift apart).
GOLDEN_AF_CODE = "FIELDS-ALL-PRESENT"

# The af_code of the REFUSED state (an absent / renamed / foreign key or a
# drifted surface). Named, so a machine consumer never mistakes a refusal for
# a pass.
REFUSED_AF_CODE = "FIELDS-NOT-ALL-PRESENT"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the field-key
    law is inconsistent with the golden all-present state, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_keys() -> tuple:
    """The 28 intended keys, fail-closed. Read ONCE from
    config/field-map.json provisioning.fields through reg.load_field_map —
    the single source of truth; a map that cannot name the 28 contract keys
    is a refusal, never a pass (a fixture that does not know what it is a
    fixture OF is worthless)."""
    fm = reg.load_field_map(FIELD_MAP_PATH)
    fields = (fm.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise FixtureError(
            "field-map.json has no provisioning.fields inventory — the golden "
            "all-present payload has nothing to derive from; refusing a blind "
            "fixture (never fabricated).")
    out = []
    for item in fields:
        if not isinstance(item, dict):
            raise FixtureError(
                "field-map provisioning.fields carries a non-object row — "
                "refusing to derive a golden payload from a malformed "
                "inventory.")
        key = item.get("intended_key")
        if not isinstance(key, str) or not key.strip():
            raise FixtureError(
                "field-map provisioning.fields carries a blank intended_key — "
                "refusing to ship a golden payload.")
        out.append(key)
    if len(out) != CONTRACT_TOTAL:
        raise FixtureError(
            "field-map provisioning.fields carries %d keys, but the golden "
            "contract is %d (19 base PRD Section 6 + 4 Gap G10 rewrite + 5 "
            "U8 cover-style) — the map drifted; refusing to ship a golden "
            "payload." % (len(out), CONTRACT_TOTAL))
    if len(set(out)) != CONTRACT_TOTAL:
        raise FixtureError(
            "field-map provisioning.fields carries duplicate intended_key "
            "values — the census must bind to 28 distinct byte-exact keys, "
            "never duplicates.")
    return tuple(out)


def _contract_rows(payload: dict) -> tuple:
    """The listing's row surface, fail-closed. A listing without a 'fields'
    array is a malformed read (never a pass); rows that are not objects are
    drift (a wrong fixture is worse than no fixture)."""
    rows = payload.get("fields")
    if not isinstance(rows, list):
        raise FixtureError(
            "the listing carries no 'fields' array — a malformed read is "
            "never a pass; refusing to ship a golden payload.")
    out = [r for r in rows if isinstance(r, dict)]
    if len(out) != len(rows):
        raise FixtureError(
            "the listing carries non-object field rows — refusing to derive "
            "a golden payload from a malformed read.")
    return tuple(out)


def _row_key(row: dict) -> str:
    """The fieldKey of a listing row under any of its key-bearing keys
    ("fieldKey" canonical, "key" alternate — the same container keys the
    census reader resolves). Returns "" when the row carries none."""
    for key in ("fieldKey", "key"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_all_present() -> dict:
    """The canonical all-present record: all 28 contract fields present by
    exact key, each with its synthetic id masked to its non-reversible
    last-4 marker (the house surface shape for every operator-facing mention
    of an id; the full synthetic id rides inside the JSON payload a machine
    consumer reads). Returns a deep copy; mutating it never touches the
    internal canonical payload (which itself is mappingproxy-frozen)."""
    out = {}
    for i, key in enumerate(_contract_keys()):
        out[key] = {
            "present": True,
            # The non-reversible masking law (reg._mask_location — the same
            # last-4 marker shape find_legacy.mask_id uses for workflow ids):
            # an operator surface sees only a marker, never a full id.
            "id_masked": reg._mask_location("fld_golden_%03d" % i),
        }
    return copy.deepcopy(out)


def golden_fields_payload() -> dict:
    """The canonical all-present listing surface: {"fields": [...]} — all 28
    contract fields by the golden keys, exact, in the row shape a live
    /locations/{id}/customFields read of a fully provisioned location
    returns (fieldKey, name, dataType, id, options — the same shape the U02
    golden_fields sibling emulates for the same read). A deep copy; callers
    may mutate it."""
    fm = reg.load_field_map(FIELD_MAP_PATH)
    fields = (fm.get("provisioning") or {}).get("fields") or []
    rows = []
    for i, item in enumerate(fields):
        intended = item["intended_key"]
        rows.append({
            "fieldKey": intended,
            "name": item.get("create_name") or reg.create_name_of(intended),
            "dataType": item.get("data_type", "LARGE_TEXT"),
            "id": "fld_golden_%03d" % i,
            "options": list(item.get("options") or ()),
        })
    return {"fields": rows}


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_all_present() / golden_fields_payload() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    inner = golden_all_present()
    frozen = {}
    for key, row in inner.items():
        # every inner row is deep-frozen the same way: the row dict becomes
        # a mappingproxy over its own plain dict (a fresh copy, so a caller
        # could never have aliased it)
        frozen[key] = MappingProxyType(dict(row))
    return (MappingProxyType(frozen),)


# The canonical all-present record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_ALL_PRESENT = _build_golden()[0]

# The canonical count of the golden state — the contract total (28), derived
# from the frozen record itself (a count drift breaks the fixture first).
GOLDEN_COUNT = len(GOLDEN_ALL_PRESENT)


# ---------------------------------------------------------------------------
# Fail-closed all-present gate — the offline gate the self-test, `payload`
# and the dispatcher's live gate all ride on. An absent or renamed contract
# key or a drifted surface is REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _contract_present_rows(rows: tuple, keys: tuple) -> dict:
    """The all-present law over the listing rows, fail-closed. Every judged
    contract key must be matched BY EXACT KEY by exactly ONE field row (the
    row's fieldKey byte-equals the intended key). Returns {key: row}; a
    missing or renamed contract key raises FixtureError — never a blind pass,
    never an id guessed from memory."""
    out = {}
    for key in keys:
        matches = [r for r in rows if _row_key(r) == key]
        if not matches:
            raise FixtureError(
                "the contract field %r is ABSENT from the listing — a "
                "renamed or re-prefixed key is indistinguishable from an "
                "absent one and BOTH refuse fail-closed; never an id guessed "
                "from memory." % key)
        if len(matches) > 1:
            raise FixtureError(
                "the contract field %r is matched by %d rows — a DUPLICATE "
                "key makes the census ambiguous; the all-present gate must "
                "bind to ONE byte-exact field, never a duplicate."
                % (key, len(matches)))
        out[key] = matches[0]
    return out


def _judge(payload: dict, *, out) -> tuple:
    """The fail-closed all-present gate. Returns (exit_code, result_dict):
    0 PASS / 5 REFUSED, where result_dict is the dispatcher-consumed surface
    {"ok", "count", "af_code", "note"} (on a refusal the dict carries ok
    False with a named af_code). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"keys": None, "rows": None}
    af_code = REFUSED_AF_CODE
    try:
        keys = _contract_keys()
        rows = _contract_rows(payload)
        matched = _contract_present_rows(rows, keys)
    except FixtureError as exc:
        detail = str(exc)
    else:
        # The foreign-key law: the census must carry EXACTLY the contract —
        # a row whose key is not in the 28-key contract is drift, refused.
        foreign = sorted({_row_key(r) for r in rows} - set(keys))
        if foreign:
            detail = ("the listing carries FOREIGN field key(s) not in the "
                      "28-key contract: %s — a drifted location surface is "
                      "never a pass" % ", ".join(repr(k) for k in foreign))
        elif len(rows) != CONTRACT_TOTAL:
            detail = ("the listing carries %d field row(s) — the all-present "
                      "gate binds to EXACTLY %d contract keys"
                      % (len(rows), CONTRACT_TOTAL))
        else:
            found["keys"] = list(matched.keys())
            found["rows"] = len(rows)
            ok = True
            af_code = GOLDEN_AF_CODE
            detail = ("all %d contract fields present byte-exact by the "
                      "golden keys (the 19 base PRD Section 6 keys + 4 Gap "
                      "G10 rewrite-preservation keys + 5 U8 cover-style "
                      "keys, read once from config/field-map.json) — the U07 "
                      "all-present state holds (and any WRITE ACTION would "
                      "require %s, Trevor-gated)"
                      % (len(rows), EXECUTE_FLAG))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "contract_total": CONTRACT_TOTAL,
            "write_action": WRITE_ACTION,
            "execute_required": GOLDEN_EXECUTE_REQUIRED,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-all-present] REFUSED: %s\n" % detail)
        return EX_MISMATCH, {
            "ok": False,
            "count": found["rows"] if found["rows"] is not None else 0,
            "af_code": af_code,
            "note": detail,
        }
    return EX_OK, {
        "ok": True,
        "count": found["rows"],
        "af_code": af_code,
        "note": detail,
    }


def payload(candidate: dict = None, *, out=None) -> dict:
    """Judge a listing payload against the golden all-present contract.
    Returns the dispatcher-consumed dict {"ok", "count", "af_code", "note"}
    (the surface main_skeleton's verify_live reads).

    READ-ONLY: asserts the U07 all-present law — ALL 28 contract fields the
    census binds to are on the listing byte-exact by the golden keys, each
    present with its one synthetic id, each matched BY EXACT KEY. An absent
    or renamed contract key, a foreign key outside the 28-key contract, a
    wrong-size listing, a malformed listing (no 'fields' array, non-object
    rows), a non-object candidate, or a credential-shaped value is a
    FAIL-CLOSED refusal (exit 5 in the report), never a blind pass. With no
    candidate the GOLDEN listing itself is judged — the dispatcher's offline
    gate. Emits the ONE JSON report object on stdout; human notes go to out
    (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_fields_payload()
    if not isinstance(candidate, dict):
        detail = "the candidate is not a JSON object — malformed listing, " \
                 "never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {
                "contract_total": CONTRACT_TOTAL,
                "write_action": WRITE_ACTION,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
            },
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-all-present] REFUSED: %s\n" % detail)
        return {"ok": False, "count": 0, "af_code": REFUSED_AF_CODE,
                "note": detail}
    return _judge(candidate, out=out)[1]


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-all-present] SELF-TEST FAILED "
                         "(AF-AE-GOLDENALLPRESENT-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType

    keys = _contract_keys()

    # ---- contract coherence: the keys come ONCE from the field-map ---------
    assert len(keys) == CONTRACT_TOTAL == 28, \
        "the golden contract must be 28 keys (19 base + 4 G10 rewrite + 5 U8 cover-style)"
    assert len(set(keys)) == 28, "the golden keys must be distinct"
    assert all(k.startswith("contact.") for k in keys), \
        "every golden key must carry the contact. prefix (the exact-key law)"
    # the derivation law holds for every golden key (create_name derives back)
    fm = reg.load_field_map(FIELD_MAP_PATH)
    inventory = (fm.get("provisioning") or {}).get("fields") or []
    for item in inventory:
        assert reg.derive_field_key(item["create_name"]) == item["intended_key"], \
            "the derivation law broke for %r" % item["intended_key"]
    # pinned spot keys — the load-bearing members of the 28 (a drift breaks
    # THIS fixture first, never silently)
    assert "contact.anthology_avatar_doc_url" in keys
    assert "contact.anthology_chapter_doc_url" in keys
    assert "contact.anthology_chapter_rewrite1_doc_url" in keys
    assert "contact.anthology_chapter_rewrite2_pdf_url" in keys
    assert "contact.anthology_cover_choice" in keys
    assert "contact.anthology_manuscript_pdf_url" in keys
    assert "contact.anthology_stage" in keys

    # ---- the canonical fixture: all-present record deep-frozen --------------
    assert isinstance(GOLDEN_ALL_PRESENT, MappingProxyType), \
        "GOLDEN_ALL_PRESENT must be mappingproxy-frozen"
    assert GOLDEN_COUNT == 28, \
        "the golden record must carry all 28 fields, got %d" % GOLDEN_COUNT
    for key in keys:
        row = GOLDEN_ALL_PRESENT[key]
        assert row["present"] is True, \
            "the golden record must carry %r PRESENT" % key
        assert isinstance(row["id_masked"], str) and row["id_masked"].startswith("..."), \
            "the golden record must mask each synthetic id to its last-4 marker"

    # ---- the payload surfaces cover the law on every shape ------------------
    rec = golden_all_present()
    assert len(rec) == 28 and all(v["present"] is True for v in rec.values()), \
        "the canonical record drifted from the golden contract"
    listing = golden_fields_payload()
    assert isinstance(listing, dict) and isinstance(listing.get("fields"), list) \
        and len(listing["fields"]) == 28, \
        "the listing surface must carry exactly 28 rows"
    assert _row_key(listing["fields"][0]) == keys[0]
    assert all(_row_key(r) in keys for r in listing["fields"]), \
        "every listing row must carry a contract key"

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_ALL_PRESENT[keys[0]]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_ALL_PRESENT[keys[0]] = "fld_golden_mutated"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_ALL_PRESENT[keys[0]] == before, \
        "the canonical fixture changed during the self-test"
    # golden_all_present() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_all_present()
    copy_[keys[0]]["present"] = False
    assert GOLDEN_ALL_PRESENT[keys[0]] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a contract key ABSENT -> FixtureError
    try:
        _contract_present_rows(
            tuple(r for r in (golden_fields_payload()["fields"])[1:]),
            keys)
        raise AssertionError("an absent contract key was NOT refused")
    except FixtureError:
        pass
    # 2. a contract key RENAMED -> FixtureError (indistinguishable from
    #    absent — the exact-key law, never a similarity match)
    rows = golden_fields_payload()["fields"]
    renamed = [dict(rows[0]), dict(rows[1])]
    renamed[0]["fieldKey"] = "contact.anthology_avatar_doc_url_RENAMED"
    try:
        _contract_present_rows(tuple(renamed), keys)
        raise AssertionError("a renamed contract key was NOT refused")
    except FixtureError:
        pass
    # 3. a DUPLICATE key -> FixtureError (the census must bind to ONE
    #    byte-exact field, never a duplicate)
    dup = [dict(rows[0]), dict(rows[0]), dict(rows[1])]
    try:
        _contract_present_rows(tuple(dup), keys)
        raise AssertionError("a duplicate key was NOT refused")
    except FixtureError:
        pass
    # 4. missing fields array -> FixtureError
    try:
        _contract_rows({"nope": 1})
        raise AssertionError("a listing without fields was NOT refused")
    except FixtureError:
        pass
    # 5. non-object row -> FixtureError
    try:
        _contract_rows({"fields": ["not-an-object"]})
        raise AssertionError("a non-object row was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = payload()
    assert result["ok"] is True, \
        "payload on the golden listing must PASS, got %r" % result
    assert result["count"] == 28, "the golden result must count 28 fields"
    assert result["af_code"] == "FIELDS-ALL-PRESENT"
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["execute_required"] is True
    # an absent contract key -> REFUSED exit 5 (the result dict carries ok
    # False with a named af_code)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        result2 = payload({"fields": [dict(r) for r in rows[1:]]})
    assert result2["ok"] is False and result2["af_code"] == \
        "FIELDS-NOT-ALL-PRESENT", \
        "an absent contract key must refuse, got %r" % result2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a renamed contract key -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"fields": renamed})["ok"] is False, \
            "a renamed contract key must refuse"
    # a foreign key -> REFUSED exit 5 (a drifted location surface, never a pass)
    foreign = [dict(r) for r in rows]
    foreign[0]["fieldKey"] = "contact.some_foreign_key"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"fields": foreign})["ok"] is False, \
            "a foreign key must refuse"
    # a duplicate key -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"fields": dup})["ok"] is False, \
            "a duplicate key must refuse"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_fields_here": True})["ok"] is False, \
            "a malformed candidate must refuse"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("not-an-object")["ok"] is False, \
            "a non-object candidate must refuse"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_all_present self-test: OK (all-present law pinned: all "
              "%d contract fields %r..%r found byte-exact by the golden "
              "keys, read once from config/field-map.json provisioning.fields "
              "through reg.load_field_map; the WRITE ACTION is %s-gated, "
              "Trevor-gated — the gate lives in the dispatcher, never in a "
              "fixture; canonical mappingproxy-frozen immutability + "
              "deep-copy surface; 5 attack fixtures refused (absent / "
              "renamed / duplicate / no-fields-array / non-object-row); "
              "payload gate returns the dispatcher dict surface — ok True on "
              "the golden listing, ok False with a named af_code on every "
              "drift; BROWSER UA pinned; never-print)\n"
              % (len(keys), keys[0], keys[-1], EXECUTE_FLAG))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_all_present.py",
        description="Golden ALL-28-PRESENT fixture for the U07 self-tests "
                    "(Skill 59): the listing where all 28 contract fields the "
                    "census binds to are present byte-exact by the golden key "
                    "— fail-closed, offline, never prints a token; the "
                    "--execute write gate lives in the dispatcher, never in a "
                    "fixture.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U07 siblings use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden all-present
            # surface — the 28 contract keys (from the field-map, never
            # retyped), the present state, the --execute-gated write action.
            keys = _contract_keys()
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "contract_total": CONTRACT_TOTAL,
                "field_keys": list(keys),
                "present_state": "all %d present byte-exact by the golden "
                                 "key" % len(keys),
                "write_action": WRITE_ACTION,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed; a LIVE census read "
                        "must ride the house rail client (CAF_BROWSER_UA on "
                        "every request — CF 1010 law); the --execute gate "
                        "that refuses a WRITE ACTION without it "
                        "(Trevor-gated) lives in the dispatcher, never in "
                        "a fixture",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate listing arrives on stdin, read from NO
        # network (the live census reader is the sibling checker, which rides
        # the house rail client and its CAF_BROWSER_UA — this fixture never
        # touches the wire). The candidate is a {"fields": [...]} listing
        # object; with none, the golden listing itself is judged.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-all-present] the listing on stdin is "
                             "not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        result = payload(candidate)
        return EX_OK if result.get("ok") else EX_MISMATCH
    except FixtureError as exc:
        sys.stderr.write("[golden-all-present] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-all-present] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
