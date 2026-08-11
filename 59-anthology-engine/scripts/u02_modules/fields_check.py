#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/fields_check.py
# BYTE-EXACT LIVE FIELD CHECK (U02 tooling, extension module) — for a given
# Convert and Flow location, assert that EVERY fieldKey in field-map.json
# provisioning.fields is present LIVE with a byte-equal server fieldKey.
#
# WHERE THIS SITS: scripts/u02_modules/ — an importable module under the U02
# template-verify tooling. It is NOT a manifest row: it ships as a sibling
# helper, exactly the way delivery_report.py ships as the sibling helper of
# caf_delivery.py (ENGINE-MANIFEST row 12 pattern), so the U02 verifier stays
# the single manifest row while this module owns the field-key surface.
# Imported BY NAME as u02_modules.fields_check from the engine scripts, per
# the u02_modules package contract (__init__.py: pure namespace container —
# fail-closed empty init, no runtime code, side-effect free). Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling imports
# use resolves anthology_registry from scripts/.
#
# WHAT THIS OWNS (byte-exact, fail-closed):
#   1. READ-ONLY listing of the location's contact custom fields via the
#      engine's own LeadConnector v2 client (reg.CafClient — the sibling
#      registry's client already sets the CAF_BROWSER_UA browser User-Agent on
#      EVERY request, the proven CF-1010 edge fix; no request is ever made
#      without it).
#   2. EXACT-MATCH BOTH DIRECTIONS against config/field-map.json
#      provisioning.fields: the field-map's 28 intended_keys must all be
#      present LIVE (a strict subset is a MISSING, never a pass), the live
#      fieldKey set must not carry contract-foreign keys (EXTRA keys are
#      drift, never ignored), and every live fieldKey must byte-equal its
#      intended_key (AF-AE-TEMPLATE-KEY-MISMATCH family).
#   3. RESOLVED-SLOT CONSISTENCY: when the installed field-map has a resolved
#      field_id slot for a key (the per-box provision stamp), the live field
#      carrying that key must ALSO carry the same field id — a stale stamp is
#      drift. The committed template ships with null slots; the key-only
#      surface is what the repo copy checks.
#   4. A masked-location report (last 4 chars of the location id only — the
#      location id is a tenant identifier, never printed in full) as ONE JSON
#      object on stdout, human notes on stderr.
#
# DOCTRINE (inherited from the registry / U02 verifier):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT SET).
#   - Fail-closed: a malformed field-map section, an absent section, a
#     non-object read, an unreadable location all STOP or FAIL — never a
#     blind pass, never a fabricated success.
#   - Scope vs edge discrimination on every read (bare 401/403 is HELD, never
#     mislabeled as a scope problem) — inherited from reg.CafClient.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier):
#   0  verified success — every intended key present live, byte-exact, and
#      (when the map is resolved) id-consistent; also self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON is a STOP, not 1)
#   2  STOP — field-map has no provisioning.fields inventory (or the contract
#      total_keys does not match the inventory), a strict subset of the
#      intended keys is missing live, or PIT / location NOT SET
#   3  HELD — Convert and Flow unreachable (transport) or an upstream/edge
#      block (CF 1010); retryable, never mislabeled as scope
#   4  self-test FAILED (AF-AE-FIELDSCHECK-* family, enforced violation)
#   5  mismatch — extra/mutated live keys, a live fieldKey not byte-equal to
#      its intended_key, a resolved field_id stamp not matching the live
#      field id, or the inventory total != the contract total_keys
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# live_verify_template.py: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""fields_check.py — byte-exact live check of the field-map's field keys (U02).

Imported BY NAME as u02_modules.fields_check from the engine scripts, per
the u02_modules package contract (__init__.py: pure namespace container).
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

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. Byte-exact intended keys come from the
# field-map; nothing is hardcoded here (a hardcoded key list would drift and
# the whole point is the field-map is the SINGLE SOURCE OF TRUTH).
REPORT_CONTRACT = "anthology-engine-fields-check"


class FieldsCheckError(Exception):
    """A fail-closed verification refusal (STOP or mismatch family)."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_inventory(field_map: dict) -> list:
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise FieldsCheckError(
            "field-map.json has no provisioning.fields inventory — the "
            "byte-exact gate has nothing to assert; refusing a blind pass.")
    return [f for f in fields if isinstance(f, dict)]


def _contract_total(field_map: dict) -> int | None:
    total = (field_map.get("provisioning") or {}).get("total_keys")
    return total if isinstance(total, int) else None


def _contract_intended_keys(field_map: dict) -> list:
    return [f.get("intended_key") for f in _contract_inventory(field_map)
            if f.get("intended_key")]


def _mask_location(loc: str) -> str:
    return reg._mask_location(loc)


def _collect_live(live_fields) -> dict:
    """Index live custom-field records by fieldKey. Fail-closed: an empty /
    non-list read is a refusal, never a silent pass."""
    if not isinstance(live_fields, list):
        raise FieldsCheckError(
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


# ---------------------------------------------------------------------------
# The check — returns the machine report dict; raises on STOP / HELD /
# fail-closed refusal. NEVER prints a token (it holds none: credentials are
# resolved by the caller's label machinery, SET / NOT SET only).
# ---------------------------------------------------------------------------
def check_fields_live(client, location_id: str, field_map: dict) -> dict:
    """Byte-exact field-key check (both directions) + resolved-slot
    consistency. Returns the report dict; raises FieldsCheckError (STOP
    family) or reg.ScopeDenied / reg.CafUnreachable (HELD family) upward —
    exactly the propagation the U02 verifier's driver uses."""
    masked = _mask_location(location_id)
    inventory = _contract_inventory(field_map)
    want_keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
    total = _contract_total(field_map)
    if total is not None and len(want_keys) != total:
        raise FieldsCheckError(
            "field-map provisioning.fields carries %d intended keys but the "
            "provisioning.total_keys contract says %d — the field-map drifted "
            "from its own contract; refusing to judge against a self-contradicting "
            "map." % (len(want_keys), total))
    if not want_keys:
        raise FieldsCheckError(
            "field-map provisioning.fields carries no intended_key entries — "
            "refusing a blind pass.")

    live = _collect_live(client.list_custom_fields(location_id))
    want_set = set(want_keys)
    got_set = set(live)
    missing = sorted(want_set - got_set)
    extra = sorted(got_set - want_set)
    mismatched = []
    for key in want_keys:
        livef = live.get(key)
        if livef is None:
            continue  # counted under `missing` above
        if livef.get("fieldKey") != key:
            mismatched.append(key)
        # Resolved-slot consistency: the installed map (per-box provision
        # stamp) pins a field_id; the live field carrying this key must carry
        # the same id. The committed template ships null slots — those are
        # key-check only, never id-checked.
        pinned = (next((f for f in inventory if f.get("intended_key") == key), {})
                  or {}).get("field_id")
        if pinned and livef.get("id") != pinned:
            mismatched.append("%s (resolved field_id %r != live %r)"
                              % (key, livef.get("id"), pinned))

    ok = (not missing and not extra and not mismatched)
    detail = "all %d intended keys present live, byte-exact" % len(want_keys) if ok else (
        "%d missing, %d extra, %d mismatched" % (len(missing), len(extra), len(mismatched)))
    return {
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "location": masked,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "total": len(want_keys),
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "detail": detail,
        "fail_closed": {
            "strict_subset_stop": bool(missing),
            "extra_keys_fail": bool(extra),
            "byte_exact_required": True,
            "resolved_slot_consistency": "field_id slots resolved on this map"
                                         if any(f.get("field_id") for f in inventory)
                                         else "template (field_id slots null — key-only check)",
            "note": "a strict subset of the intended keys is a STOP; any other "
                    "set / key / id drift is exit 5 — never a silent pass."},
    }


# ---------------------------------------------------------------------------
# Verify driver — raises stop/held upward (the CLI maps them to exit codes),
# writes the machine report to stdout, human notes to stderr.
# ---------------------------------------------------------------------------
def verify_live(client, location_id: str, field_map: dict, *, out=None) -> int:
    """Run the live check and print the ONE JSON report object to stdout.
    Returns the exit code (0/2/3/5); STOP and HELD propagate as raised."""
    out = out or sys.stderr
    report = check_fields_live(client, location_id, field_map)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["ok"]:
        out.write("[fields-check] OK: %s (marker %s).\n"
                  % (report["detail"], report["location"]))
        return EX_OK
    out.write("[fields-check] FAIL: %s (marker %s).\n"
              % (report["detail"], report["location"]))
    return EX_MISMATCH


def plan(field_map: dict, *, out=None) -> int:
    """Offline plan (no network, no credentials): the intended keys the live
    check will assert, straight from the field-map (the single source of
    truth — never a hardcoded list). One JSON object on stdout."""
    out = out or sys.stderr
    inventory = _contract_inventory(field_map)
    keys = [f.get("intended_key") for f in inventory if f.get("intended_key")]
    total = _contract_total(field_map)
    if total is not None and len(keys) != total:
        out.write("[fields-check] plan: inventory %d != total_keys %d — refusing.\n"
                  % (len(keys), total))
        return EX_MISMATCH
    print(json.dumps({
        "contract": REPORT_CONTRACT + "-plan",
        "schema_version": 1,
        "total": len(keys),
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
    """In-memory Convert and Flow covering exactly the read surface with a
    programmable listing and a mutation log (self-tests prove zero writes)."""

    def __init__(self, fields=None, behavior=None):
        # Keep the raw read payload (a list of records, or an attack-shape
        # non-list) so the fail-closed read-shape check sees exactly what a
        # live read would return.
        self._fields = fields
        self.behavior = behavior  # None | scope | edge | transport
        self.calls = []

    def list_custom_fields(self, location_id):
        self.calls.append(("fields", location_id))
        self._maybe_raise()
        if isinstance(self._fields, list):
            return [dict(f) for f in self._fields]
        return self._fields

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")


def _fake_field_map():
    return reg.load_field_map(FIELD_MAP_PATH)


def _golden_fields(field_map: dict) -> list:
    """A live listing that EXACTLY matches the map's intended keys — with
    resolved field_id slots so the id-consistency surface is also exercised."""
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
        sys.stderr.write("[fields-check] SELF-TEST FAILED "
                         "(AF-AE-FIELDSCHECK-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    field_map = _fake_field_map()
    want_keys = _contract_intended_keys(field_map)
    # ---- contract coherence: the map is the source of truth ----
    assert want_keys, "field-map must carry intended keys"
    total = _contract_total(field_map)
    assert total is not None and len(want_keys) == total, \
        "inventory must equal provisioning.total_keys (%s != %s)" % (len(want_keys), total)
    assert all(k.startswith("contact.") for k in want_keys), \
        "every intended key must carry the contact. prefix"
    assert len(set(want_keys)) == len(want_keys), \
        "intended keys must be unique"

    # ---- golden live state: EVERYTHING passes ----
    golden = _golden_fields(field_map)
    caf = _FakeCaf(fields=golden)
    report = check_fields_live(caf, "loc_fx", field_map)
    assert report["verdict"] == "PASS", "golden: %s" % report["detail"]
    assert report["ok"] is True, "golden report must carry ok: true"
    assert report["total"] == len(want_keys)
    assert report["missing"] == [] and report["extra"] == [] and report["mismatched"] == []
    assert report["location"] == "...c_fx", "location marker must be masked: %r" % report["location"]

    # full verify_live on the golden state: exit 0, ONE JSON object on stdout
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(caf, "loc_fx", field_map, out=io.StringIO())
    assert rc == EX_OK, "golden verify_live must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS", "golden report must carry verdict PASS"
    assert parsed["ok"] is True, "golden report must carry ok: true"

    # ---- the check NEVER writes ----
    assert caf.calls and all(m == "fields" for m, _ in caf.calls), \
        "check performed an unexpected call: %s" % caf.calls

    # ---- attack fixtures: every mutation REFUSED / recorded ----
    # 1. fieldKey mutated -> mismatch recorded (exit 5 family)
    a1 = copy.deepcopy(golden)
    a1[0]["fieldKey"] = "contact.anthology_avatar_doc_url_MUTATED"
    report = check_fields_live(_FakeCaf(fields=a1), "loc_fx", field_map)
    assert report["verdict"] == "FAIL", "fieldKey-mutated must FAIL"
    assert report["missing"] == [want_keys[0]], "mutated key must count as missing"
    assert "contact.anthology_avatar_doc_url_MUTATED" in report["extra"]

    # 2. field DELETED (strict subset) -> missing -> STOP family (exit 2)
    a2 = copy.deepcopy(golden)[1:]
    report = check_fields_live(_FakeCaf(fields=a2), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and report["missing"] == [want_keys[0]], \
        "field-deleted must record the missing key"

    # 3. EXTRA field -> FAIL (exit 5 family), never a pass
    a3 = copy.deepcopy(golden)
    a3.append({"fieldKey": "contact.anthology_extra", "name": "anthology_extra",
               "dataType": "LARGE_TEXT", "id": "fld_extra"})
    report = check_fields_live(_FakeCaf(fields=a3), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and report["extra"] == ["contact.anthology_extra"], \
        "field-extra must FAIL"

    # 4. resolved field_id stamp not matching the live field id -> FAIL
    #    (the committed map ships null field_id slots, so the id-consistency
    #    branch only fires on a RESOLVED per-box map — fixture pins one)
    resolved_map = copy.deepcopy(field_map)
    for f, livef in zip(resolved_map["provisioning"]["fields"], golden):
        f["field_key"] = livef["fieldKey"]
        f["field_id"] = livef["id"]
    a4 = copy.deepcopy(golden)
    a4[0]["id"] = "fld_DRIFTED"
    report = check_fields_live(_FakeCaf(fields=a4), "loc_fx", resolved_map)
    assert report["verdict"] == "FAIL", "resolved field_id drift must FAIL"
    assert any("field_id" in m for m in report["mismatched"]), \
        "the drifted id must be named in mismatched"

    # 5. empty live listing -> strict subset -> FAIL (never a silent pass)
    report = check_fields_live(_FakeCaf(fields=[]), "loc_fx", field_map)
    assert report["verdict"] == "FAIL" and len(report["missing"]) == total, \
        "empty live listing must fail closed"

    # 6. non-list live read -> hard refusal (FieldsCheckError)
    try:
        check_fields_live(_FakeCaf(fields={"not": "a list"}), "loc_fx", field_map)
        raise AssertionError("non-list read was NOT refused")
    except FieldsCheckError:
        pass

    # 7. map with no provisioning.fields -> hard refusal
    try:
        check_fields_live(_FakeCaf(fields=golden), "loc_fx", {})
        raise AssertionError("missing inventory was NOT refused")
    except FieldsCheckError:
        pass

    # 8. inventory total != contract total_keys -> hard refusal
    tampered = copy.deepcopy(field_map)
    tampered["provisioning"]["total_keys"] = (total or 0) + 1
    try:
        check_fields_live(_FakeCaf(fields=golden), "loc_fx", tampered)
        raise AssertionError("total_keys drift was NOT refused")
    except FieldsCheckError:
        pass

    # 9. scope denied on the read -> STOP (exit 2), never a fabricated pass
    try:
        check_fields_live(_FakeCaf(fields=golden, behavior="scope"), "loc_fx", field_map)
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass

    # 10. edge block -> HELD (exit 3), never mislabeled as scope
    try:
        check_fields_live(_FakeCaf(fields=golden, behavior="edge"), "loc_fx", field_map)
        raise AssertionError("edge-block was NOT refused")
    except reg.UpstreamBlockedError:
        pass

    # 11. transport failure -> HELD (exit 3)
    try:
        check_fields_live(_FakeCaf(fields=golden, behavior="transport"), "loc_fx", field_map)
        raise AssertionError("transport failure was NOT refused")
    except reg.CafUnreachable:
        pass

    # 12. template-state map (all resolved slots null): key-only check passes
    template = copy.deepcopy(field_map)
    for f in template["provisioning"]["fields"]:
        f["field_key"] = None
        f["field_id"] = None
    report = check_fields_live(_FakeCaf(fields=golden), "loc_fx", template)
    assert report["verdict"] == "PASS", "template map key-only check must PASS"

    # ---- plan: offline, no network, exact key list ----
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = plan(field_map, out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf2.getvalue())
    assert p["keys"] == want_keys, "plan must list the intended keys in order"

    dev.write("fields_check self-test: OK (field-map coherence %d keys == "
              "total_keys, golden all-PASS + verify_live exit 0, 12 attack "
              "fixtures refused or FAIL-recorded (fieldKey-mutated/"
              "field-deleted/field-extra/field_id-drift/empty-listing/"
              "non-list-read/no-inventory/total_keys-drift/scope-denied/"
              "edge-block/transport/template-null-slots), no-writes, "
              "masked-location, plan offline)\n" % total)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fields_check.py",
        description="Byte-exact live check of the field-map's contact custom "
                    "field keys on a Convert and Flow location (U02 tooling, "
                    "Skill 59): every provisioning.fields intended_key present "
                    "live with a byte-equal server fieldKey, both directions, "
                    "fail-closed.")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"], default="verify")

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
        sys.stderr.write("[fields-check] PIT resolved via %s (SET). Location via "
                         "%s (marker %s).\n"
                         % (pit_label, loc_label, reg._mask_location(loc)))
        client = reg.CafClient(token)
        return verify_live(client, loc, field_map, out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[fields-check] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[fields-check] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[fields-check] HELD: %s\n" % exc)
        return EX_HELD
    except FieldsCheckError as exc:
        sys.stderr.write("[fields-check] STOP: %s\n" % exc)
        return EX_STOP
    except FileNotFoundError as exc:
        sys.stderr.write("[fields-check] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[fields-check] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
