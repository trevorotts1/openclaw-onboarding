#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/test_missing_finder.py
# UNIT TESTS for the MISSING-FIELD FINDER (scripts/u07_modules/missing_finder.py
# — U07 tooling: GET-check-by-name, list missing fields, and idempotent
# create-or-verify). The laws this file exists to enforce:
#
#   * THE SINGLE SOURCE OF TRUTH — the finder judges config/field-map.json
#     provisioning.fields and provisioning.total_keys ONLY (never a hardcoded
#     list, never a guessed count): a map with no inventory, an inventory that
#     contradicts total_keys, a malformed row, or a create_name that does not
#     derive to its intended key is a REFUSAL (MissingFinderError, STOP
#     family), never a silent pass;
#   * THE CHECK-BY-NAME LAW, all three branches — an intended key present
#     live by byte-equal fieldKey is PRESENT (a differing live name is an
#     informational name-hint note, never a fail); an intended key absent
#     while its create_name is live under a DIFFERENT key is NAME-SQUAT
#     DRIFT (exit 5 family, human-fix, never counted missing, never created);
#     neither is MISSING (the payload the finder exists to surface);
#   * THE TREVOR GATE — creation REQUIRES --execute; without it a location
#     with missing fields is a STOP (exit 2) that lists them by name
#     (creation is never silent); WITH --execute each missing field is
#     created by its create_name and the server-returned fieldKey is read
#     back byte-exact against the intended key — a drifted key or a rejected
#     create is a MISMATCH (exit 5), never certified;
#   * THE IDEMPOTENCY LAW — a field already present live is verified, never
#     re-created; a re-run over a healed listing finds everything present
#     and creates NOTHING (proven by the call log: zero creates);
#   * FAIL-CLOSED, every direction — an empty live listing is "everything
#     missing" (never a silent pass), a non-list live read is a refusal, a
#     scope-denied read/create is the STOP family, an edge block or
#     transport failure is HELD (retryable, never mislabeled), and every
#     comparison is byte-exact (no normalization, no similarity);
#   * NEVER A TOKEN — credentials are resolved BY LABEL (SET / NOT SET only);
#     no fixture carries a credential and no captured surface (JSON payload
#     or human note) may; the location rides every surface MASKED (last 4
#     chars); created field ids ride the machine payload FULLY but are
#     MASKED on every operator note (the same marker law find_legacy pins);
#   * THE HOUSE DOCTRINE PINS — the exit-code convention asserted through
#     the registry's exported constants (0/1/2/3/5, 4 = self-test FAILED),
#     the browser User-Agent law (CF 1010 — CAF_BROWSER_UA is a browser UA,
#     never optional: urllib's default Python-urllib/x.y is 403'd at the
#     Cloudflare edge), the fail-closed-empty u07 package init, the module's
#     own offline battery green (a red self-test is caught HERE first), and
#     determinism (the check never mutates its inputs).
#
# Hermetic: imports missing_finder.py directly (stdlib only), reuses the
# module's OWN offline _FakeCaf for every live-surface test (the exact seam
# the module's self-test proves), and exercises the create-phase propagation
# through a read-ok/create-fail stub the module's own fake cannot isolate.
# ZERO network calls, ZERO credentials, NO env var read, NO real CafClient
# constructed. The CLI credential boundary is deliberately NOT exercised
# (main() resolves the real token stores — that is the operator surface, not
# a unit-testable seam); the tested seams are check_fields / apply_create /
# run_check / plan / self_test, plus the offline main() paths (self-test,
# plan, and a bad --field-map that must exit 1 before any credential work).
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u07_modules/test_missing_finder.py -q
#  or: python3 59-anthology-engine/scripts/u07_modules/test_missing_finder.py
# =============================================================================
"""test_missing_finder.py -- the missing-field finder's check-by-name law,
Trevor-gated create-or-verify, fail-closed refusals, and never-a-token
surfaces (U07)."""

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import u07_modules.missing_finder as mf  # noqa: E402  (the module under test)

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix — the house guard
# shape every operator surface is scanned against. No fixture carries a
# real one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

LOC = "loc_tmpl"  # the fixture location label (masked on every surface)


def _field_map() -> dict:
    """The committed field-map — the single source of truth under test."""
    return reg.load_field_map(reg.FIELD_MAP_PATH)


def _golden_fields() -> list:
    """A live listing that EXACTLY matches the map: every intended key
    carrying BOTH its create_name AND its derived fieldKey (the canonical
    shape per the derivation law) — the module's own golden helper."""
    return mf._golden_fields(_field_map())


def _want_keys() -> list:
    """The intended keys in map order — the module's own contract reader,
    never a hardcoded list typed in this file."""
    return [e[0] for e in mf._intended_entries(_field_map())]


def _squatter_row(golden_row: dict, wrong_key: str) -> dict:
    """A NAME-SQUAT row: the golden field's create_name under a fieldKey
    that does NOT derive to its intended key."""
    row = dict(golden_row)
    row["fieldKey"] = wrong_key
    return row


class _CreateGateClient:
    """Reads the listing fine; the FIRST N create calls raise the given
    exception, later ones succeed. Isolates the create-phase ladder that
    the module's own _FakeCaf cannot (its behavior knob fails the READ
    first for scope/transport, and every create for validation)."""

    def __init__(self, fields, exc, n=1):
        self._fields = [dict(f) for f in fields]
        self._exc = exc
        self._n = n
        self.calls = []
        self.created = []

    def list_custom_fields(self, location_id):
        self.calls.append(("fields", location_id))
        return [dict(f) for f in self._fields]

    def create_custom_field(self, location_id, name, data_type, options=None):
        self.calls.append(("create", location_id, name, data_type, options))
        n_creates = len([c for c in self.calls if c[0] == "create"])
        if n_creates <= self._n:
            raise self._exc
        self.created.append(name)
        rec = {"fieldKey": reg.derive_field_key(name), "name": name,
               "dataType": data_type, "id": "fld_new_%d" % len(self.created)}
        self._fields.append(rec)
        return dict(rec)


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_module_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (golden all-PASS plus every attack fixture refused or
    FAIL-recorded)."""
    assert mf.self_test(out=io.StringIO()) == EX_OK


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge (CF error 1010) before it ever reaches Convert and Flow. The
    finder's every request rides reg.CafClient, which applies this UA."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    assert "Chrome/" in reg.CAF_BROWSER_UA, (
        "CAF_BROWSER_UA must be a well-formed Chrome build (GK-09)")
    assert hasattr(reg, "CafClient"), (
        "reg.CafClient — the client that applies CAF_BROWSER_UA — must exist")


def test_u07_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface — and it CARRIES the --execute
    (Trevor-gated) and browser-UA doctrine in its DOCTRINE comment block."""
    import u07_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()
    init_text = Path(pkg.__file__).read_text(encoding="utf-8")
    assert "--execute" in init_text and "Trevor-gated" in init_text
    assert "browser" in init_text and "1010" in init_text
    assert "secret" in init_text.lower()


def test_report_contract_is_pinned():
    """The ONE fixed report contract — a machine consumer can never mistake
    another JSON object for a missing-field read (the module's own self-test
    asserts the golden report carries the exact string)."""
    assert mf.REPORT_CONTRACT == "anthology-engine-missing-finder"
    assert mf.REPORT_SCHEMA_VERSION == 1
    assert mf.EXECUTE_FLAG == "--execute"


def test_field_map_is_the_single_source_of_truth():
    """The map is the source of truth and self-consistent: every intended key
    carries the contact. prefix, keys are unique, every create_name derives
    byte-exactly to its intended key, the inventory equals total_keys, and
    the TWO SINGLE_OPTIONS keys (anthology_cover_choice + the review
    decision) carry their options from the map."""
    field_map = _field_map()
    entries = mf._intended_entries(field_map)
    keys = [e[0] for e in entries]
    total = field_map["provisioning"]["total_keys"]
    assert len(keys) == len(field_map["provisioning"]["fields"]) == total, (
        "inventory must equal provisioning.total_keys")
    assert keys and all(k.startswith("contact.") for k in keys), (
        "every intended key must carry the contact. prefix")
    assert len(set(keys)) == len(keys), "intended keys must be unique"
    for intended, cname, _d, _o in entries:
        assert reg.derive_field_key(cname) == intended, (
            "create_name %r must derive to intended key %r"
            % (cname, intended))
    cover = [f for f in field_map["provisioning"]["fields"]
             if f["intended_key"] == "contact.anthology_cover_choice"]
    assert len(cover) == 1 and cover[0]["data_type"] == "SINGLE_OPTIONS"
    assert isinstance(cover[0]["options"], list) and cover[0]["options"]


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a malformed map is a refusal, never a pass)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("bad_map", "detail"),
    [
        ({}, "no provisioning.fields inventory"),
        ({"provisioning": {}}, "no provisioning.fields inventory"),
        ({"provisioning": {"fields": "not-a-list"}},
         "no provisioning.fields inventory"),
        ({"provisioning": {"fields": []}}, "no provisioning.fields inventory"),
    ])
def test_malformed_field_map_shapes_refuse(bad_map, detail):
    """A map with no inventory, a non-list inventory, or an EMPTY inventory
    each REFUSE (MissingFinderError, STOP family) — the gate has nothing to
    judge and never passes blind."""
    with pytest.raises(mf.MissingFinderError) as excinfo:
        mf.check_fields(mf._FakeCaf(fields=_golden_fields()), LOC, bad_map)
    assert detail in str(excinfo.value)


def test_tampered_field_map_shapes_refuse():
    """The tampered-map ladder, one case at a time off the real map: a row
    missing intended_key/create_name, a non-string key, a create_name that
    does not derive to its intended key (the map contradicting its own
    derivation law), and an inventory that contradicts total_keys — each
    REFUSES with the module's exact typed reason."""
    for mutate, detail in (
            (lambda m: m["provisioning"]["fields"][0].pop("create_name"),
             "missing intended_key or create_name"),
            (lambda m: m["provisioning"]["fields"][0].pop("intended_key"),
             "missing intended_key or create_name"),
            (lambda m: m["provisioning"]["fields"][0].__setitem__(
                "intended_key", 42),
             "non-string key/name"),
            (lambda m: m["provisioning"]["fields"][0].__setitem__(
                "create_name", "not_the_right_name"),
             "does not derive to intended key"),
            (lambda m: m["provisioning"].__setitem__(
                "total_keys", m["provisioning"]["total_keys"] + 1),
             "total_keys contract")):
        tampered = copy.deepcopy(_field_map())
        mutate(tampered)
        with pytest.raises(mf.MissingFinderError) as excinfo:
            mf.check_fields(mf._FakeCaf(fields=_golden_fields()),
                            LOC, tampered)
        assert detail in str(excinfo.value), (
            "tampered map must refuse with %r, got: %s"
            % (detail, excinfo.value))


# ---------------------------------------------------------------------------
# The golden read: everything present, byte-exact, nothing written.
# ---------------------------------------------------------------------------
def test_golden_check_everything_present_byte_exact():
    """The golden live listing: ok True, verdict PASS, every intended key
    present in map order, zero missing, zero drift, zero name-hint notes,
    the masked location marker, and the fail-closed contract on the report."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=_golden_fields())
    report = mf.check_fields(caf, LOC, _field_map())
    assert report["contract"] == mf.REPORT_CONTRACT
    assert report["schema_version"] == mf.REPORT_SCHEMA_VERSION
    assert report["verdict"] == "PASS" and report["ok"] is True
    assert report["total"] == len(want)
    assert report["present"] == want, "every intended key must be present"
    assert report["missing"] == [] and report["name_squat_drift"] == []
    assert report["name_hint_notes"] == []
    assert report["created"] == [] and report["created_ids"] == {}
    assert report["mismatches"] == [] and report["execute"] is False
    assert report["location"] == reg._mask_location(LOC), (
        "the location must ride the report masked, never in full")
    fc = report["fail_closed"]
    assert fc["check_by_name"] is True and fc["byte_exact_required"] is True
    assert fc["name_squat_never_created"] is True
    assert fc["creation_requires_execute"] is True


def test_golden_check_never_writes():
    """The check performs EXACTLY one read and ZERO creates — a read-only
    surface, proven by the stub's call log."""
    caf = mf._FakeCaf(fields=_golden_fields())
    mf.check_fields(caf, LOC, _field_map())
    assert caf.calls == [("fields", LOC)], (
        "the check must perform exactly one listing read: %s" % caf.calls)
    assert caf.created == [], "the check must never create"


def test_golden_check_is_deterministic_and_never_mutates_its_inputs():
    """The check is pure and deterministic: the same listing gives the same
    verdict every time, and neither the listing nor the field-map is ever
    mutated."""
    field_map = _field_map()
    before = json.dumps(field_map, sort_keys=True)
    first = mf.check_fields(mf._FakeCaf(fields=_golden_fields()), LOC, field_map)
    second = mf.check_fields(mf._FakeCaf(fields=_golden_fields()), LOC, field_map)
    assert json.dumps(field_map, sort_keys=True) == before, (
        "the check must never mutate the field-map")
    assert first == second, "the check must be deterministic"


def test_name_hint_note_is_informational_never_a_fail():
    """A key present live byte-exact under a DIFFERENT name (hand-created)
    stays PASS — the key contract holds, the differing name is an
    informational note, never a fail and never a rename."""
    listing = copy.deepcopy(_golden_fields())
    listing[0]["name"] = "hand_created_different_name"
    report = mf.check_fields(mf._FakeCaf(fields=listing), LOC, _field_map())
    assert report["verdict"] == "PASS" and report["ok"] is True
    assert report["missing"] == [] and report["name_squat_drift"] == []
    assert len(report["name_hint_notes"]) == 1
    note = report["name_hint_notes"][0]
    assert note["intended_key"] == listing[0]["fieldKey"]
    assert note["live_name"] == "hand_created_different_name"
    assert note["create_name"] == mf._missing_create_name(
        _field_map(), listing[0]["fieldKey"]), (
        "the note's create_name must be the MAP's name, never the live name")


def test_run_check_golden_exits_0_with_one_json_on_stdout():
    """The full run on the golden state: exit 0, ONE JSON object on stdout
    (the machine payload), the human OK note on the given out stream."""
    buf = io.StringIO()
    notes = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=_golden_fields()), LOC,
                          _field_map(), out=notes)
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "PASS" and payload["ok"] is True
    assert buf.getvalue().count(payload["contract"]) == 1, (
        "exactly ONE report object on stdout")
    note = notes.getvalue()
    assert "[missing-finder] OK" in note and reg._mask_location(LOC) in note
    assert LOC not in note and LOC not in buf.getvalue(), (
        "the location must never ride a surface in full")


# ---------------------------------------------------------------------------
# Missing fields and the Trevor gate (--execute).
# ---------------------------------------------------------------------------
def test_field_deleted_live_is_missing_and_stops_without_execute():
    """A field deleted live is MISSING and listed; without --execute the run
    STOPS (exit 2, Trevor gate) — creation is never silent — and the STOP
    performs ZERO creates."""
    want = _want_keys()
    listing = _golden_fields()[1:]  # the first field is gone
    caf = mf._FakeCaf(fields=listing)
    report = mf.check_fields(caf, LOC, _field_map())
    assert report["verdict"] == "FAIL" and report["ok"] is False
    assert report["missing"] == [want[0]], (
        "the field-deleted live state must record the missing key")
    assert report["execute"] is False
    assert caf.created == [], "the check must never create"

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=listing), LOC,
                          _field_map(), out=io.StringIO())
    assert rc == EX_STOP, "missing WITHOUT --execute must STOP (exit 2)"
    payload = json.loads(buf.getvalue())
    assert payload["missing"] == [want[0]], (
        "the STOP payload must carry the missing key list")
    assert payload["execute"] is False


def test_stop_payload_and_note_list_the_missing_by_name():
    """The STOP note names the gate flag and the missing fields BY NAME
    (the create identity — the finder's payload), never bare keys only."""
    want = _want_keys()
    cname0 = reg.create_name_of(want[0])
    notes = io.StringIO()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=_golden_fields()[1:]), LOC,
                          _field_map(), out=notes)
    assert rc == EX_STOP
    note = notes.getvalue()
    assert "[missing-finder] STOP" in note
    assert mf.EXECUTE_FLAG in note, "the STOP must name the --execute gate"
    assert "Trevor-gated" in note
    assert "%s (%s)" % (want[0], cname0) in note, (
        "the STOP must list the missing field by key AND create name")
    assert LOC not in note and "pit-" not in note


def test_execute_creates_and_verifies_byte_exact():
    """WITH --execute the same location is created-and-verified (exit 0):
    the missing field is created by its create_name, the server-returned
    fieldKey is read back byte-exact against the intended key, the created
    id rides the machine payload FULLY, and nothing is left missing."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=_golden_fields()[1:])
    notes = io.StringIO()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True, out=notes)
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "PASS" and payload["ok"] is True
    assert payload["created"] == [want[0]]
    assert payload["missing"] == [], "after the create nothing may be missing"
    assert set(payload["created_ids"]) == {want[0]}, (
        "the created id must be on the payload (full, machine-readable)")
    assert payload["execute"] is True
    assert caf.created == [reg.create_name_of(want[0])], (
        "the field must be created by its create_name (the derivation-law "
        "input)")


def test_execute_creates_only_the_missing_keys_never_present():
    """The create touches EXACTLY the missing keys: with one field missing
    the stub records one create, with the missing key's create_name — a
    present field is verified, never re-created."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=_golden_fields()[1:])
    with contextlib.redirect_stdout(io.StringIO()):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True,
                          out=io.StringIO())
    assert rc == EX_OK
    assert [c for c in caf.calls if c[0] == "create"] == [
        ("create", LOC, reg.create_name_of(want[0]), "LARGE_TEXT")], (
        "exactly ONE create, for the missing key, with the map's data_type: "
        "%s" % caf.calls)


def test_idempotent_rerun_after_heal_creates_nothing():
    """IDEMPOTENCY: a re-run over the healed listing finds everything
    present and creates NOTHING — the call log proves zero creates."""
    caf1 = mf._FakeCaf(fields=_golden_fields()[1:])
    with contextlib.redirect_stdout(io.StringIO()):
        rc1 = mf.run_check(caf1, LOC, _field_map(), execute=True,
                           out=io.StringIO())
    assert rc1 == EX_OK
    caf2 = mf._FakeCaf(fields=caf1._fields)  # the healed listing
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc2 = mf.run_check(caf2, LOC, _field_map(), execute=True,
                           out=io.StringIO())
    assert rc2 == EX_OK, "the idempotent re-run must exit 0"
    assert [c for c in caf2.calls if c[0] == "create"] == [], (
        "the re-run must perform ZERO creates: %s" % caf2.calls)
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "PASS" and payload["created"] == []


def test_empty_live_listing_is_everything_missing():
    """An EMPTY live listing is "everything missing" — listed in map order,
    FAIL, never a silent pass — and STOPS without --execute."""
    want = _want_keys()
    report = mf.check_fields(mf._FakeCaf(fields=[]), LOC, _field_map())
    assert report["verdict"] == "FAIL" and report["ok"] is False
    assert report["missing"] == want, (
        "an empty live listing must list every intended key missing")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=[]), LOC, _field_map(),
                          out=io.StringIO())
    assert rc == EX_STOP


def test_all_missing_created_with_execute_from_empty_listing():
    """FROM an empty listing WITH --execute: every missing field is
    created-and-verified byte-exact — exit 0, every key created, every
    created id on the payload."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=[])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True,
                          out=io.StringIO())
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "PASS"
    assert payload["created"] == want, (
        "every missing field must be created, in map order")
    assert set(payload["created_ids"]) == set(want)


def test_map_options_ride_the_create_for_the_single_options_key():
    """data_type and options ride the create FROM THE MAP — the ONE
    SINGLE_OPTIONS key (anthology_cover_choice) carries its option list,
    every other key creates with the map's data_type — the map is the
    single source of truth, never a hardcoded list."""
    field_map = _field_map()
    cover = [f for f in field_map["provisioning"]["fields"]
             if f["intended_key"] == "contact.anthology_cover_choice"][0]
    client = _CreateGateClient(fields=[], exc=reg.CafValidation("never"),
                               n=0)  # no failures; n=0 disables the gate
    with contextlib.redirect_stdout(io.StringIO()):
        rc = mf.run_check(client, LOC, field_map, execute=True,
                          out=io.StringIO())
    assert rc == EX_OK
    creates = [c for c in client.calls if c[0] == "create"]
    assert len(creates) == len(_want_keys())
    for call in creates:
        _, loc, name, dtype, options = call
        assert loc == LOC
        row = [f for f in field_map["provisioning"]["fields"]
               if f["create_name"] == name][0]
        assert dtype == row.get("data_type", "LARGE_TEXT"), (
            "data_type must come from the map for %s" % name)
        assert options == row.get("options"), (
            "options must come from the map for %s" % name)
    cover_call = [c for c in creates if c[2] == cover["create_name"]][0]
    assert cover_call[3] == "SINGLE_OPTIONS"
    assert cover_call[4] == cover["options"]


# ---------------------------------------------------------------------------
# The name-squat law (drift is never missing, never created).
# ---------------------------------------------------------------------------
def test_name_squat_is_drift_never_missing_never_created():
    """A live field named EXACTLY the create_name but keyed under something
    else is NAME-SQUAT DRIFT: never counted missing, never created, the
    live (wrong) fieldKey reported — exit 5 MISMATCH, and --execute never
    relaxes it (a drift-only surface never reaches the create path)."""
    want = _want_keys()
    listing = _golden_fields()[1:]
    listing.append(_squatter_row(_golden_fields()[0], "contact.squatted_key"))
    caf = mf._FakeCaf(fields=listing)
    report = mf.check_fields(caf, LOC, _field_map())
    assert report["missing"] == [], (
        "the squatted key must NOT be 'missing'")
    assert len(report["name_squat_drift"]) == 1
    drift = report["name_squat_drift"][0]
    assert drift["name"] == reg.create_name_of(want[0])
    assert drift["intended_key"] == want[0]
    assert drift["live_fieldKey"] == "contact.squatted_key"
    notes = io.StringIO()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True, out=notes)
    assert rc == EX_MISMATCH, (
        "name-squat must be MISMATCH (exit 5) even WITH --execute")
    assert caf.created == [], "a name-squat must NEVER be created"
    payload = json.loads(buf.getvalue())
    assert payload["ok"] is False and payload["execute"] is False, (
        "the drift-only surface never reaches the create path")
    assert payload["created"] == [] and payload["mismatches"] == []
    assert "[missing-finder] MISMATCH" in notes.getvalue()
    assert "never created" in notes.getvalue()


def test_drift_only_exits_5_even_without_execute():
    """A drift-only surface is a MISMATCH (exit 5 family) even WITHOUT
    --execute — the drift is a human-fix condition, never a silent pass and
    never gated behind the create flag."""
    listing = _golden_fields()[1:]
    listing.append(_squatter_row(_golden_fields()[0], "contact.squatted_key"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=listing), LOC, _field_map(),
                          out=io.StringIO())
    assert rc == EX_MISMATCH
    payload = json.loads(buf.getvalue())
    assert payload["ok"] is False and payload["execute"] is False
    assert payload["missing"] == [] and len(payload["name_squat_drift"]) == 1


def test_drift_plus_missing_stops_without_execute():
    """Missing AND drift together: without --execute the run STOPS (exit 2)
    and lists the missing — the drift is reported, never created, and the
    gate still holds for the missing fields."""
    want = _want_keys()
    listing = _golden_fields()[2:]
    # key 0 fully absent (missing); key 1's create_name live under a wrong
    # key (drift); keys 2+ present. A squatter is never the missing case.
    listing.append(_squatter_row(_golden_fields()[1], "contact.squat_b"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=listing), LOC, _field_map(),
                          out=io.StringIO())
    assert rc == EX_STOP
    payload = json.loads(buf.getvalue())
    assert payload["missing"] == [want[0]]
    assert len(payload["name_squat_drift"]) == 1
    assert payload["name_squat_drift"][0]["name"] == reg.create_name_of(want[1])
    assert payload["execute"] is False


def test_drift_plus_missing_with_execute_creates_missing_never_drift():
    """WITH --execute the MISSING fields are created-and-verified while the
    drift is NEVER created — the surface stays a MISMATCH (exit 5) because
    the drift remains human-fix."""
    want = _want_keys()
    listing = _golden_fields()[2:]
    listing.append(_squatter_row(_golden_fields()[1], "contact.squat_b"))
    caf = mf._FakeCaf(fields=listing)
    notes = io.StringIO()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True, out=notes)
    assert rc == EX_MISMATCH
    payload = json.loads(buf.getvalue())
    assert payload["created"] == [want[0]], (
        "the missing field must be created-and-verified")
    assert payload["verdict"] == "MISMATCH"
    assert "name-squat" in payload["detail"]
    assert len(payload["name_squat_drift"]) == 1
    assert payload["execute"] is True
    assert caf.created == [reg.create_name_of(want[0])], (
        "the drift must NEVER be created")


# ---------------------------------------------------------------------------
# The create-or-verify mismatch ladder (exit 5 family).
# ---------------------------------------------------------------------------
def test_derived_key_drift_on_create_is_mismatch():
    """The server returns a fieldKey that is NOT byte-equal to the intended
    key (derivation law changed or server drift) -> MISMATCH (exit 5),
    recorded with the drifted key, never certified, never a pass."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=_golden_fields()[1:])
    caf._derive = lambda name: "contact." + name + "_WRONG"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True,
                          out=io.StringIO())
    assert rc == EX_MISMATCH
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "MISMATCH" and payload["created"] == []
    assert len(payload["mismatches"]) == 1
    assert payload["mismatches"][0]["key"] == want[0]
    assert "server fieldKey" in payload["mismatches"][0]["why"]


def test_validation_rejected_create_is_mismatch_recorded_and_continues():
    """A create REJECTED by the API (CafValidation) is recorded as a
    mismatch and the finder CONTINUES to the next missing field — the
    rejected key is never certified and never silently retried as a
    different shape."""
    want = _want_keys()
    client = _CreateGateClient(
        fields=_golden_fields()[2:],
        exc=reg.CafValidation("Convert and Flow rejected the request (HTTP 422)"),
        n=1)  # the FIRST create fails, the rest succeed
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(client, LOC, _field_map(), execute=True,
                          out=io.StringIO())
    assert rc == EX_MISMATCH
    payload = json.loads(buf.getvalue())
    assert payload["created"] == [want[1]], (
        "the second missing field must still be created-and-verified")
    assert len(payload["mismatches"]) == 1
    assert payload["mismatches"][0]["key"] == want[0]
    assert "create rejected" in payload["mismatches"][0]["why"]


def test_created_ids_full_in_payload_masked_on_stderr():
    """Created field ids ride the machine payload FULLY (the documented
    machine contract) but appear MASKED (last 4 chars) on every operator
    note — the same marker law find_legacy pins for workflow ids."""
    want = _want_keys()
    caf = mf._FakeCaf(fields=_golden_fields()[1:])
    notes = io.StringIO()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(caf, LOC, _field_map(), execute=True, out=notes)
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    full_id = payload["created_ids"][want[0]]
    assert full_id and full_id.startswith("fld_new_"), (
        "the payload must carry the FULL created id")
    assert mf._mask_id(full_id) in notes.getvalue(), (
        "the operator note must carry the MASKED marker, got: %s"
        % notes.getvalue())
    assert full_id not in notes.getvalue(), (
        "the full id must never ride an operator note")
    assert mf._mask_id("fld_new_0") == "...ew_0"
    assert mf._mask_id("") == "...(short)"


# ---------------------------------------------------------------------------
# STOP / HELD propagation (never a fabricated pass).
# ---------------------------------------------------------------------------
def test_scope_denied_on_read_is_stop_family():
    """Scope denied on the READ is the STOP family (reg.ScopeDenied), never
    a fabricated verdict."""
    with pytest.raises(reg.ScopeDenied):
        mf.check_fields(mf._FakeCaf(fields=_golden_fields(), behavior="scope"),
                        LOC, _field_map())


def test_scope_denied_on_create_propagates():
    """Scope denied on a CREATE propagates the same STOP family — the
    create-phase refusal is not swallowed into a mismatch."""
    with pytest.raises(reg.ScopeDenied):
        mf.run_check(_CreateGateClient(fields=_golden_fields()[1:],
                                       exc=reg.ScopeDenied(
                                           "token not authorized for this "
                                           "scope (HTTP 403)")),
                     LOC, _field_map(), execute=True, out=io.StringIO())


def test_edge_block_is_held_family():
    """An edge block (CF 1010 / 403 without a scope signature) is the HELD
    family (UpstreamBlockedError) — retryable, never mislabeled as scope,
    never a fabricated pass."""
    with pytest.raises(reg.UpstreamBlockedError):
        mf.check_fields(mf._FakeCaf(fields=_golden_fields(), behavior="edge"),
                        LOC, _field_map())


def test_transport_failure_is_held_family():
    """A transport failure (URLError) is the HELD family (CafUnreachable) —
    UNDETERMINED is a correct answer, never a verdict."""
    with pytest.raises(reg.CafUnreachable):
        mf.check_fields(
            mf._FakeCaf(fields=_golden_fields(), behavior="transport"),
            LOC, _field_map())


def test_transport_failure_on_create_propagates():
    """A transport failure on a CREATE propagates the same HELD family."""
    with pytest.raises(reg.CafUnreachable):
        mf.run_check(_CreateGateClient(
            fields=_golden_fields()[1:],
            exc=reg.CafUnreachable("Convert and Flow transport error: URLError")),
            LOC, _field_map(), execute=True, out=io.StringIO())


def test_non_list_live_read_is_refused():
    """A non-list live read (dict, None) is a hard refusal
    (MissingFinderError, STOP family) — an unread surface is never judged
    and never a silent pass."""
    for bad in (None, {"not": "a list"}):
        with pytest.raises(mf.MissingFinderError) as excinfo:
            mf.check_fields(mf._FakeCaf(fields=bad), LOC, _field_map())
        assert "did not return a list" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The offline plan (no network, no credentials).
# ---------------------------------------------------------------------------
def test_plan_is_offline_exact_key_list():
    """The offline plan carries the intended keys and create names IN ORDER
    straight from the map (the single source of truth, never a hardcoded
    list), flags dry_run, and carries the Trevor gate as data."""
    want = _want_keys()
    field_map = _field_map()
    entries = mf._intended_entries(field_map)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.plan(field_map, out=io.StringIO())
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == mf.REPORT_CONTRACT + "-plan"
    assert payload["total"] == len(want)
    assert payload["keys"] == want
    assert payload["create_names"] == [e[1] for e in entries]
    assert payload["dry_run"] is True
    assert mf.EXECUTE_FLAG in payload["note"] and "Trevor-gated" in payload["note"]


def test_plan_never_carries_credential_shape():
    """The plan payload is scanned against the credential shape before
    print — no pit-/Bearer-shaped string may ever ride it."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.plan(_field_map(), out=io.StringIO())
    assert rc == EX_OK
    out = buf.getvalue()
    assert CREDENTIAL_SHAPE not in out and "Bearer" not in out
    assert "Authorization" not in out


def test_plan_refuses_a_malformed_map():
    """The offline plan refuses a map that contradicts itself — a plan is
    never printed for a map the live check could not judge."""
    tampered = copy.deepcopy(_field_map())
    tampered["provisioning"]["total_keys"] += 1
    with pytest.raises(mf.MissingFinderError):
        mf.plan(tampered, out=io.StringIO())


# ---------------------------------------------------------------------------
# Never-a-token sweep: every captured surface, every exit path.
# ---------------------------------------------------------------------------
def _captured_surfaces():
    """Runs every exit path (PASS / STOP / create-OK / MISMATCH-drift /
    plan) capturing stdout, and returns (label, text) pairs for the
    credential-shape sweep."""
    field_map = _field_map()
    golden = _golden_fields()
    out = []

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=golden), LOC, field_map,
                          out=io.StringIO())
    out.append(("golden-rc%d" % rc, buf.getvalue()))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=golden[1:]), LOC, field_map,
                          out=io.StringIO())
    out.append(("stop-rc%d" % rc, buf.getvalue()))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=golden[1:]), LOC, field_map,
                          execute=True, out=io.StringIO())
    out.append(("execute-rc%d" % rc, buf.getvalue()))

    listing = golden[1:]
    listing.append(_squatter_row(golden[0], "contact.squatted_key"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.run_check(mf._FakeCaf(fields=listing), LOC, field_map,
                          execute=True, out=io.StringIO())
    out.append(("drift-rc%d" % rc, buf.getvalue()))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.plan(field_map, out=io.StringIO())
    out.append(("plan-rc%d" % rc, buf.getvalue()))
    return out


def test_no_captured_surface_prints_a_token():
    """No captured surface — PASS, STOP, create-OK, MISMATCH, or plan —
    carries a credential-shaped string (pit-/Bearer/Authorization)."""
    surfaces = _captured_surfaces()
    assert surfaces, "the sweep must exercise at least one surface"
    for label, text in surfaces:
        assert CREDENTIAL_SHAPE not in text, label
        assert "Bearer" not in text, label
        assert "Authorization" not in text, label
        assert "token" not in text.lower(), label


# ---------------------------------------------------------------------------
# CLI surface — the OFFLINE main() paths only. The credential boundary
# resolves the real token stores and is deliberately not exercised here.
# ---------------------------------------------------------------------------
def test_cli_self_test_subcommand_runs_offline():
    """main(['self-test']) and the --self-test / --selftest normalizations
    run the offline battery — exit 0, no network, no credential."""
    assert mf.main(["self-test"]) == EX_OK
    assert mf.main(["--self-test"]) == EX_OK
    assert mf.main(["--selftest"]) == EX_OK


def test_cli_plan_with_explicit_field_map_is_offline():
    """main(['plan', '--field-map', PATH]) prints the offline plan — exit 0,
    ONE JSON object, before any credential work."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.main(["plan", "--field-map", str(reg.FIELD_MAP_PATH)])
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == mf.REPORT_CONTRACT + "-plan"
    assert payload["keys"] == _want_keys()


def test_cli_missing_field_map_is_exit_1_before_any_credential_work():
    """A --field-map that cannot be read exits 1 (unexpected-error family)
    BEFORE any credential resolution — the CLI never guesses and never
    prints a secret."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mf.main(["--field-map",
                      str(SKILL_DIR / "no-such-field-map-xyz.json")])
    assert rc == EX_ERR


# ---------------------------------------------------------------------------
# Plain-python runner (no pytest required) — house style.
# ---------------------------------------------------------------------------
TESTS = [
    (test_module_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_u07_package_init_is_fail_closed_empty, False),
    (test_report_contract_is_pinned, False),
    (test_field_map_is_the_single_source_of_truth, False),
    (test_tampered_field_map_shapes_refuse, False),
    (test_golden_check_everything_present_byte_exact, False),
    (test_golden_check_never_writes, False),
    (test_golden_check_is_deterministic_and_never_mutates_its_inputs, False),
    (test_name_hint_note_is_informational_never_a_fail, False),
    (test_run_check_golden_exits_0_with_one_json_on_stdout, False),
    (test_field_deleted_live_is_missing_and_stops_without_execute, False),
    (test_stop_payload_and_note_list_the_missing_by_name, False),
    (test_execute_creates_and_verifies_byte_exact, False),
    (test_execute_creates_only_the_missing_keys_never_present, False),
    (test_idempotent_rerun_after_heal_creates_nothing, False),
    (test_empty_live_listing_is_everything_missing, False),
    (test_all_missing_created_with_execute_from_empty_listing, False),
    (test_map_options_ride_the_create_for_the_single_options_key, False),
    (test_name_squat_is_drift_never_missing_never_created, False),
    (test_drift_only_exits_5_even_without_execute, False),
    (test_drift_plus_missing_stops_without_execute, False),
    (test_drift_plus_missing_with_execute_creates_missing_never_drift, False),
    (test_derived_key_drift_on_create_is_mismatch, False),
    (test_validation_rejected_create_is_mismatch_recorded_and_continues, False),
    (test_created_ids_full_in_payload_masked_on_stderr, False),
    (test_scope_denied_on_read_is_stop_family, False),
    (test_scope_denied_on_create_propagates, False),
    (test_edge_block_is_held_family, False),
    (test_transport_failure_is_held_family, False),
    (test_transport_failure_on_create_propagates, False),
    (test_non_list_live_read_is_refused, False),
    (test_plan_is_offline_exact_key_list, False),
    (test_plan_never_carries_credential_shape, False),
    (test_plan_refuses_a_malformed_map, False),
    (test_no_captured_surface_prints_a_token, False),
    (test_cli_self_test_subcommand_runs_offline, False),
    (test_cli_plan_with_explicit_field_map_is_offline, False),
    (test_cli_missing_field_map_is_exit_1_before_any_credential_work, False),
]


def main():
    failed = 0
    for t, _ in TESTS:
        try:
            t()
            print("  PASS: %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL: %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001 — a crash is a failure, reported as one
            failed += 1
            print("  ERROR: %s\n        %r" % (t.__name__, exc))
    print("\n=== %d passed, %d failed ===" % (len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
