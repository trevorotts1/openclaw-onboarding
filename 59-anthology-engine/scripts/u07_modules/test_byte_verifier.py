#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/test_byte_verifier.py
# UNIT TESTS for the POST-CREATE READ-BACK VERIFIER (scripts/u07_modules/
# byte_verifier.py — U07 tooling): after provisioning creates a custom field,
# the verifier RE-READS the Convert and Flow location's custom-field inventory
# through the SAME live read surface the create used (reg.CafClient
# list_custom_fields, the house adapter) and confirms EVERY server fieldKey
# byte-exact against config/field-map.json provisioning.fields (the SINGLE
# source of truth, never a hardcoded list) — no normalization, no substring,
# no similarity score (the U06 exact-name law, applied to field keys): a
# renamed, re-prefixed, case-drifted, or whitespace-drifted key is
# indistinguishable from an absent one and BOTH refuse fail-closed (the
# AF-AE-READBACK-MISMATCH / AF-AE-FIELD-KEY-MISMATCH family). The comparison
# is byte-exact in BOTH directions, over the COMPLETE set: a declared key
# missing from the live read is a MISMATCH, and a live key the field map does
# not declare (an EXTRA) is a MISMATCH — an incomplete read-back is never a
# pass. The one law this file exists to enforce: THE VERIFIER NEVER WRITES.
# It is READ-ONLY by construction — every invocation, execute or not, performs
# zero mutations; and the VERIFY ACTION carries the family Trevor gate —
# WITHOUT --execute it is a STOP (exit 2), never a silent no-op, never a
# confirmation.
#
# WHAT THIS FILE PROVES (network-free, credential-free — the live read is
# NEVER performed: every verdict is driven through the module's own `journal`
# read seam, exactly the surface the module's self-test uses, so no client is
# constructed, no env var is read, no network is touched):
#   * the golden read-back: a journal with EVERY intended key carried live by
#     a byte-equal server fieldKey PASSes exit 0, ONE JSON report on stdout,
#     execute true, the location marker masked,
#   * the ACTION gate, both directions: without --execute the verify is a
#     STOP (exit 2) — even on the golden journal, so a plan that could be
#     mistaken for a confirmation is impossible — never a silent no-op; with
#     --execute the verifier still writes NOTHING (the golden journal PASSes
#     and no surface mutates),
#   * the byte-exact key law, every direction: a declared key missing from
#     the live read, a server fieldKey that is NOT byte-exact (the one-byte
#     drift — a trailing space — the byte-exact test), and a live key the
#     field map does not declare are each a MISMATCH (exit 5), never a pass —
#     the pass/fail split discriminates (the golden control is never a broken
#     instrument),
#   * the fail-closed refusal ladder: an empty expected inventory and a
#     missing expected inventory each STOP (exit 2, never a sweep); a
#     credential-shaped value on the read REFUSES (exit 2, never echoed); a
#     field-map contract that cannot be read is a hard refusal
#     (ByteVerifierError, STOP family); the derivation law is pinned — a
#     create_name that does not derive back to its intended key is a hard
#     refusal,
#   * the never-a-token law: no surface carries a credential shape or a full
#     location id (markers are last-4-char suffixes only), on PASS, MISMATCH,
#     and STOP verdicts alike,
#   * the house doctrine pins: the exit-code convention (0/1/2/3/4/5)
#     asserted through the registry's exported constants, the browser
#     User-Agent law (CF 1010 — CAF_BROWSER_UA is a browser UA, and the real
#     CafClient sends it on the live custom-fields and create requests), the
#     fail-closed-empty package init, the module's own self-test green (a red
#     battery is caught HERE first), determinism (the same journal gives the
#     same verdict every time; the golden journal never mutates through the
#     read), and the offline plan surface.
#
# House doctrine (Skill 59, u07_modules/__init__.py): fail-closed, both
# directions — the golden control passes and EVERY attack fails, so the
# pass/fail split discriminates (the golden control is never a broken
# instrument). Never a token printed; nothing Anthropic in any runtime
# surface; stdlib only; pytest with plain asserts; sys.path bootstrap
# identical to every other u07_modules/ test file; exit codes asserted by the
# exported module constants, never hardcoded. The registry's CafClient is
# NEVER constructed here (only the real request path is proven once, via the
# same urlopen patch the registry's own self-test uses), no network is
# touched.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u07_modules/test_byte_verifier.py -q
#  or: python3 59-anthology-engine/scripts/u07_modules/test_byte_verifier.py
# =============================================================================
"""test_byte_verifier.py -- the post-create read-back verifier's byte-exact
fieldKey law, the Trevor-gated ACTION, the never-writes law, and the
never-a-token / CF 1010 house pins (U07)."""

import contextlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))  # house bootstrap: scripts/ on sys.path

import anthology_registry as reg  # noqa: E402
import u07_modules.byte_verifier as bv  # noqa: E402  (the module under test)

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u07 surface is scanned against. No
# test fixture ever carries one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# Anthropic-family id shapes assembled from fragments; no banned literal
# appears anywhere in this file (AF-AE-ANTHROPIC / guard-no-anthropic-runtime).
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)

# The verifier's source of truth: the committed field-map, read through the
# registry's own load (the SAME surface every u07 sibling checks against).
FIELD_MAP = reg.load_field_map(reg.FIELD_MAP_PATH)
WANT_KEYS = [intended for intended, _ in
             bv._load_expected_inventory(reg.FIELD_MAP_PATH)]
TOTAL = len(WANT_KEYS)

# A live location marker: the last four characters are the ONLY part that may
# ever surface — the full id is a location handle, never a credential, and
# stays off every operator surface (the module's own masking law).
LOC = "loc_HERMETIC_fx8a"
LOC_MASK = reg._mask_location(LOC)  # "...fx8a"

# A credential-shaped row id — the shape every u07 surface must refuse to
# carry. No golden fixture ever contains one.
_ROWID = CREDENTIAL_SHAPE + "x" * 16


# ---------------------------------------------------------------------------
# The golden journal — the module's own explicit read seam (the self-test
# hand). No client is ever constructed and no network is ever touched: every
# verdict is driven through `verify(journal=...)`, the exact surface the
# module's own self-test battery uses.
# ---------------------------------------------------------------------------
def _golden_journal():
    """A journal whose expected inventory is the FULL committed field-map
    contract and whose live surface carries every intended key with a
    byte-equal server fieldKey under a synthetic field id (a real field id
    is never used)."""
    expected = bv._load_expected_inventory(reg.FIELD_MAP_PATH)
    return {
        "expected": list(expected),
        "live": {intended: "fld_golden_%d" % i
                 for i, (intended, _) in enumerate(expected)},
    }


def _check(journal, *, execute=True, **kw):
    """Run the verifier's verify with stdout and the REAL stderr captured,
    returning (rc, parsed, notes). The module writes its STOP refusals to
    sys.stderr directly (never to the `out` param), so both streams are
    captured into the same notes buffer. The journal seam is the ONLY
    surface exercised — offline, no client, no network."""
    buf = io.StringIO()
    notes = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(notes):
        rc = bv.verify(field_map_path=reg.FIELD_MAP_PATH,
                       location_override=LOC, execute=execute,
                       out=notes, journal=journal, **kw)
    parsed = None
    if buf.getvalue().strip():
        try:
            parsed = json.loads(buf.getvalue())
        except ValueError:
            parsed = None
    return rc, parsed, notes.getvalue()


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_verifier_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (the golden read-back plus every drift fixture refused; a
    red battery is caught HERE first)."""
    err = io.StringIO()
    rc = bv.self_test(field_map_path=reg.FIELD_MAP_PATH, out=err)
    assert rc == EX_OK, "self-test must exit 0, got %s" % rc
    assert "SELF-TEST FAILED" not in err.getvalue()
    assert err.getvalue().strip(), "self-test must write a human receipt to stderr"

def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)
    assert bv.EX_VIOLATION == EX_VIOLATION

def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge (CF error 1010) before it ever reaches Convert and Flow. The
    constant is a browser UA, never optional, never re-implemented here."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    assert "Python-urllib" not in reg.CAF_BROWSER_UA

def test_cafclient_sends_the_browser_ua_on_the_live_requests():
    """The REAL request path — the custom-fields listing and the create
    request the verifier's live read rides — sends CAF_BROWSER_UA on every
    request (proven by patching urlopen exactly as the registry's own
    self-test does). No request is ever made without it."""
    captured = []

    class _FakeResp:
        def read(self):
            return b'{"customFields": [], "customField": {}}'
        def getcode(self):
            return 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(req, timeout=None):
        captured.append({k.lower(): v for k, v in req.header_items()}
                        .get("user-agent"))
        return _FakeResp()

    real = urllib.request.urlopen
    try:
        urllib.request.urlopen = _open
        client = reg.CafClient("tok_probe")
        client.list_custom_fields("loc_probe")
        client.create_custom_field("loc_probe", "anthology_cover_choice",
                                   "SINGLE_OPTIONS")
    finally:
        urllib.request.urlopen = real
    assert captured and all(ua == reg.CAF_BROWSER_UA for ua in captured), (
        "browser User-Agent not sent on every request: %r" % captured)

def test_u07_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface (fail-closed empty init)."""
    import u07_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()

# ---------------------------------------------------------------------------
# Contract coherence (the source of truth the verifier judges against)
# ---------------------------------------------------------------------------
def test_contract_is_exactly_28_keys():
    """The field-map's provisioning contract is exactly 28 intended keys,
    every one prefixed contact. and unique — the law the live check asserts
    (a drift in the map breaks THIS test first, fail-closed)."""
    assert WANT_KEYS, "field-map must carry intended keys"
    assert TOTAL == 28, "the contract drifted from 28 keys, got %d" % TOTAL
    assert all(k.startswith("contact.") for k in WANT_KEYS), (
        "every intended key must carry the contact. prefix")
    assert len(set(WANT_KEYS)) == len(WANT_KEYS), "intended keys must be unique"

def test_every_create_name_derives_back_to_its_intended_key():
    """The derivation law (W0.5): every create_name derives back to its
    intended key through the registry's OWN derivation surface — a drifted
    derivation is a hard refusal, never a guessed expectation."""
    for intended, cname in bv._load_expected_inventory(reg.FIELD_MAP_PATH):
        assert reg.derive_field_key(cname) == intended, (
            "create_name %r must derive back to %r" % (cname, intended))

def test_verifier_is_deterministic_and_never_mutates_its_inputs():
    """The verifier never mutates the journal it judges — the same journal
    gives the same verdict every time."""
    journal = _golden_journal()
    before = json.dumps(journal, sort_keys=True)
    rc1, parsed1, _ = _check(journal, execute=True)
    rc2, parsed2, _ = _check(journal, execute=True)
    assert rc1 == rc2 == EX_OK
    assert parsed1 == parsed2, "the same journal must give the same report"
    assert json.dumps(journal, sort_keys=True) == before, (
        "the journal was mutated by the check")

# ---------------------------------------------------------------------------
# The golden read-back: every key byte-exact -> PASS.
# ---------------------------------------------------------------------------
def test_golden_read_back_passes():
    """The golden read-back: every intended key carried live by a byte-equal
    server fieldKey — PASS, exit 0, ONE JSON report with the contract, the
    action, execute true, and the location marker masked."""
    rc, parsed, _ = _check(_golden_journal(), execute=True)
    assert rc == EX_OK, "golden read-back must exit 0, got %s" % rc
    assert parsed["ok"] is True and parsed["verdict"] == "PASS", parsed
    assert parsed["contract"] == bv.CONFIG_CONTRACT, parsed
    assert parsed["action"] == "verify" and parsed["execute"] is True, parsed
    assert parsed["execute_required"] is True, parsed
    assert parsed["expected_keys"] == 28 == parsed["live_keys"], parsed
    assert parsed["missing"] == [] and parsed["mismatched"] == [], parsed
    assert parsed["extra"] == [], parsed
    assert parsed["location_masked"] == LOC_MASK == "...fx8a", (
        "the location marker must be masked, got %r"
        % parsed["location_masked"])
    assert LOC not in json.dumps(parsed), "the full location id must never surface"

def test_read_back_is_deterministic_and_never_mutates_its_inputs():
    """The same journal gives the same verdict every time, and the journal
    handed in is never mutated through the read (the verifier is READ-ONLY)."""
    journal = _golden_journal()
    before = json.dumps(journal, sort_keys=True)
    rc1, _, _ = _check(journal, execute=True)
    rc2, _, _ = _check(journal, execute=True)
    assert rc1 == rc2 == EX_OK
    assert json.dumps(journal, sort_keys=True) == before

# ---------------------------------------------------------------------------
# The ACTION gate: --execute required (Trevor-gated), never a silent no-op.
# ---------------------------------------------------------------------------
def test_verify_without_execute_stops_at_the_action_boundary():
    """An ACTION without --execute is a STOP (exit 2) — even on the golden
    journal, so a plan that could be mistaken for a confirmation is
    impossible. Never a silent no-op, never a mutation."""
    rc, _, err = _check(_golden_journal(), execute=False)
    assert rc == EX_STOP, "verify without --execute must exit 2, got %s" % rc
    assert "--execute" in err and "Trevor-gated" in err, err

def test_verify_cli_without_execute_stops():
    """The CLI boundary enforces the same Trevor gate: verify without
    --execute STOPS (exit 2) before any read — no token, no network, no
    verdict."""
    rc = bv.main(["verify", "--field-map", str(reg.FIELD_MAP_PATH)])
    assert rc == EX_STOP

def test_verifier_never_writes_even_with_execute():
    """WITH --execute the verifier still performs NO write: the golden
    read-back PASSes and the journal (the only thing it could touch) is
    byte-identical after the check — READ-ONLY by construction."""
    journal = _golden_journal()
    before = json.dumps(journal, sort_keys=True)
    rc, _, _ = _check(journal, execute=True)
    assert rc == EX_OK
    assert json.dumps(journal, sort_keys=True) == before

# ---------------------------------------------------------------------------
# The byte-exact key law: every deviation is a MISMATCH, never a pass.
# ---------------------------------------------------------------------------
def test_declared_key_missing_from_the_live_read_is_a_mismatch():
    """A declared key missing from the live read is a MISMATCH (exit 5) —
    a vanished key is not proof of presence, never a blind pass."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live.pop(WANT_KEYS[0])
    rc, parsed, err = _check({"expected": journal["expected"], "live": live},
                             execute=True)
    assert rc == EX_MISMATCH, "a missing declared key must exit 5, got %s" % rc
    assert parsed["verdict"] == "MISMATCH" and parsed["ok"] is False, parsed
    assert parsed["missing"] == [WANT_KEYS[0]], parsed
    assert "MISMATCH" in err, err

def test_non_byte_exact_fieldkey_is_a_mismatch():
    """A server fieldKey that is NOT byte-exact — the ONE-BYTE drift (a
    trailing space) — is a MISMATCH (exit 5): the byte-exact law, never a
    near-match pass."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live.pop(WANT_KEYS[0])
    live[WANT_KEYS[0] + " "] = "fld_golden_drift"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "a one-byte drift must exit 5, got %s" % rc
    assert WANT_KEYS[0] in parsed["missing"], parsed
    assert WANT_KEYS[0] + " " in parsed["extra"], parsed

def test_renamed_key_is_a_mismatch_never_a_pass():
    """An intended key carried live under a DRIFTED key (renamed) is a
    MISMATCH — byte equality is the law, never a similarity score."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live.pop(WANT_KEYS[0])
    live["contact.anthology_avatr_doc_url"] = "fld_golden_renamed"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "a renamed key must exit 5, got %s" % rc
    assert WANT_KEYS[0] in parsed["missing"], parsed
    assert "contact.anthology_avatr_doc_url" in parsed["extra"], parsed

def test_reprefixed_key_is_a_mismatch_never_a_pass():
    """An intended key carried live under a re-prefixed key (the contact.
    prefix altered) is a MISMATCH — the prefix is part of the byte law."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live.pop(WANT_KEYS[1])
    live[reg.create_name_of(WANT_KEYS[1])] = "fld_golden_reprefixed"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "a re-prefixed key must exit 5, got %s" % rc
    assert WANT_KEYS[1] in parsed["missing"], parsed

def test_case_drifted_key_is_a_mismatch_never_a_pass():
    """An intended key carried live with any letter case changed is a
    MISMATCH — byte-exact means case-exact, never a case-insensitive
    compare."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live.pop(WANT_KEYS[2])
    live[WANT_KEYS[2].replace("anthology", "Anthology")] = "fld_golden_case"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "a case-drifted key must exit 5, got %s" % rc
    assert WANT_KEYS[2] in parsed["missing"], parsed

def test_live_key_the_field_map_does_not_declare_is_a_mismatch():
    """A live key the field map does not declare (an EXTRA) is a MISMATCH —
    the read-back is byte-exact in BOTH directions, never a pass on a
    superset."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live["contact.anthology_sneak_key"] = "fld_golden_sneak"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "an undeclared live key must exit 5, got %s" % rc
    assert "contact.anthology_sneak_key" in parsed["extra"], parsed

def test_multiple_drifted_keys_are_all_named():
    """EVERY drifted key is named on its list — a partial listing is never
    mistaken for a clean one."""
    journal = _golden_journal()
    live = dict(journal["live"])
    for key in WANT_KEYS[4:7]:
        live.pop(key)
    live["contact.drifted_key"] = "fld_golden_drifted"
    rc, parsed, _ = _check({"expected": journal["expected"], "live": live},
                           execute=True)
    assert rc == EX_MISMATCH, "multiple drifts must exit 5, got %s" % rc
    assert len(parsed["missing"]) == 3, parsed["missing"]
    assert len(parsed["extra"]) == 1, parsed["extra"]

# ---------------------------------------------------------------------------
# The fail-closed refusal ladder.
# ---------------------------------------------------------------------------
def test_empty_expected_inventory_stops_never_a_sweep():
    """An empty expected inventory STOPS (exit 2) — the read-back law is
    unverifiable, never a sweep, never a pass."""
    rc, _, err = _check({"expected": [], "live": _golden_journal()["live"]},
                        execute=True)
    assert rc == EX_STOP, "an empty expected inventory must exit 2, got %s" % rc
    assert "STOP" in err, err

def test_missing_expected_inventory_stops():
    """A journal carrying NO expected inventory STOPS (exit 2) — REFUSED
    without guessing."""
    rc, _, err = _check({"live": _golden_journal()["live"]}, execute=True)
    assert rc == EX_STOP, "a missing expected inventory must exit 2, got %s" % rc
    assert "STOP" in err, err

def test_credential_shaped_read_value_refuses_never_echoed():
    """A credential-shaped value on the read REFUSES (exit 2) — never echoed
    onto any surface, never judged a key."""
    journal = _golden_journal()
    live = dict(journal["live"])
    live["contact.anthology_sneak"] = _ROWID
    rc, parsed, err = _check({"expected": journal["expected"], "live": live},
                             execute=True)
    assert rc == EX_STOP, "a credential-shaped read value must STOP, got %s" % rc
    assert parsed is None, "a refusal must emit no JSON report on stdout"
    assert "STOP" in err, err
    assert CREDENTIAL_SHAPE not in err, "the credential value was echoed"

def test_unreadable_field_map_is_a_hard_refusal():
    """A field-map contract that cannot be read is a hard refusal
    (ByteVerifierError, STOP family) — the expected surface is unverifiable,
    never a blind skip."""
    with pytest.raises(bv.ByteVerifierError):
        bv._load_expected_inventory(Path("/nonexistent/field-map.json"))

def test_map_without_provisioning_fields_is_a_hard_refusal():
    """A map with no provisioning.fields inventory is a hard refusal — the
    gate has nothing to assert, so it refuses a blind pass."""
    tmp = Path(__file__).with_name("_bv_map_empty.json")
    tmp.write_text(json.dumps({"provisioning": {}}), encoding="utf-8")
    try:
        with pytest.raises(bv.ByteVerifierError):
            bv._load_expected_inventory(tmp)
    finally:
        tmp.unlink(missing_ok=True)

def test_malformed_inventory_row_is_a_hard_refusal():
    """A provisioning.fields row carrying no intended_key is a hard refusal —
    an expectation that cannot name its own source must not run."""
    tmp = Path(__file__).with_name("_bv_map_badrow.json")
    tmp.write_text(json.dumps(
        {"provisioning": {"fields": [{"create_name": "anthology_stage"}]}}),
        encoding="utf-8")
    try:
        with pytest.raises(bv.ByteVerifierError):
            bv._load_expected_inventory(tmp)
    finally:
        tmp.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Never-a-token, every direction.
# ---------------------------------------------------------------------------
def test_no_surface_prints_a_token_or_a_full_location_id():
    """Every captured surface — the golden PASS report, the refusal reports —
    carries markers (last-4 suffixes) only: no credential shape, no full
    synthetic id, no full location id, no Anthropic-family identifier."""
    surfaces = []
    journal = _golden_journal()
    rc, parsed, err = _check(journal, execute=True)
    surfaces.append((rc, json.dumps(parsed, indent=2, sort_keys=True), err))
    live = dict(journal["live"])
    live.pop(WANT_KEYS[0])
    rc, parsed, err = _check({"expected": journal["expected"], "live": live},
                             execute=True)
    surfaces.append((rc, json.dumps(parsed, indent=2, sort_keys=True), err))
    rc, parsed, err = _check(journal, execute=False)
    surfaces.append((rc, err or "", ""))
    for rc, blob, err in surfaces:
        assert LOC not in blob and LOC not in err, (
            "the full location id leaked (rc %s)" % rc)
        assert CREDENTIAL_SHAPE not in blob and CREDENTIAL_SHAPE not in err, (
            "a credential shape leaked (rc %s)" % rc)
        assert "Bearer" not in blob and "Bearer" not in err, (
            "a Bearer shape leaked (rc %s)" % rc)
        assert not BANNED.search(blob) and not BANNED.search(err), (
            "an Anthropic-family identifier leaked (rc %s)" % rc)

def test_self_test_receipt_never_carries_a_token_shape():
    """The self-test receipt (the human note to stderr) never carries a
    credential shape or the full location id."""
    err = io.StringIO()
    rc = bv.self_test(field_map_path=reg.FIELD_MAP_PATH, out=err)
    assert rc == EX_OK, rc
    assert CREDENTIAL_SHAPE not in err.getvalue(), (
        "the self-test receipt leaked a token shape")
    assert "Bearer" not in err.getvalue(), (
        "the self-test receipt leaked a Bearer shape")

# ---------------------------------------------------------------------------
# The plan surface (offline, no network, no credential).
# ---------------------------------------------------------------------------
def test_plan_is_offline_and_carries_the_law():
    """plan emits ONE offline JSON object (no network, no credential) with
    the read-back law, the two sources of truth, and the --execute law;
    never a credential shape anywhere on the surface."""
    buf = io.StringIO()
    rc = bv.plan(field_map_path=reg.FIELD_MAP_PATH, out=buf)
    assert rc == EX_OK, "plan must exit 0, got %s" % rc
    plan = json.loads(buf.getvalue())
    assert plan["contract"] == bv.CONFIG_CONTRACT + "-plan", plan
    assert plan["action"] == "verify" and plan["execute_required"] is True, plan
    assert "byte-equal" in plan["law"], plan
    assert "reg.CafClient.list_custom_fields" in plan["live_source"], plan
    assert CREDENTIAL_SHAPE not in buf.getvalue(), (
        "the plan must never carry a credential-shaped string")

# ---------------------------------------------------------------------------
# The CLI surface (offline): self-test and plan run without credentials.
# ---------------------------------------------------------------------------
def test_cli_selftest_and_plan_are_offline():
    """Both --self-test and the positional self-test form run the OFFLINE
    battery and exit 0 (a tamper is exit 4, never 1); plan is offline too —
    with stdout/stderr captured so nothing leaks onto the real terminal."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc1 = bv.main(["--self-test", "--field-map", str(reg.FIELD_MAP_PATH)])
        rc2 = bv.main(["self-test", "--field-map", str(reg.FIELD_MAP_PATH)])
        rc3 = bv.main(["plan", "--field-map", str(reg.FIELD_MAP_PATH)])
    assert rc1 == rc2 == rc3 == EX_OK, (rc1, rc2, rc3)

# ---------------------------------------------------------------------------
# The module source (the runtime file, not this battery).
# ---------------------------------------------------------------------------
def test_module_source_contains_no_anthropic_identifier():
    text = Path(__file__).with_name("byte_verifier.py").read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if BANNED.search(line):
            raise AssertionError("byte_verifier.py:%d carries an Anthropic "
                                 "identifier VALUE: %s" % (lineno, line.strip()))

def test_module_source_has_no_inlined_credential_shape():
    text = Path(__file__).with_name("byte_verifier.py").read_text(encoding="utf-8")
    assert not re.search(r"(?i)(?:api[_-]?key|token|secret)\s*[=:]\s*[\"'][^\"']{12,}",
                         text), (
        "a credential-shaped assignment is inlined in byte_verifier.py")

# ---------------------------------------------------------------------------
# Plain-python runner (no pytest required) — house style.
# ---------------------------------------------------------------------------
TESTS = [
    (test_verifier_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_cafclient_sends_the_browser_ua_on_the_live_requests, False),
    (test_u07_package_init_is_fail_closed_empty, False),
    (test_contract_is_exactly_28_keys, False),
    (test_every_create_name_derives_back_to_its_intended_key, False),
    (test_verifier_is_deterministic_and_never_mutates_its_inputs, False),
    (test_golden_read_back_passes, False),
    (test_read_back_is_deterministic_and_never_mutates_its_inputs, False),
    (test_verify_without_execute_stops_at_the_action_boundary, False),
    (test_verify_cli_without_execute_stops, False),
    (test_verifier_never_writes_even_with_execute, False),
    (test_declared_key_missing_from_the_live_read_is_a_mismatch, False),
    (test_non_byte_exact_fieldkey_is_a_mismatch, False),
    (test_renamed_key_is_a_mismatch_never_a_pass, False),
    (test_reprefixed_key_is_a_mismatch_never_a_pass, False),
    (test_case_drifted_key_is_a_mismatch_never_a_pass, False),
    (test_live_key_the_field_map_does_not_declare_is_a_mismatch, False),
    (test_multiple_drifted_keys_are_all_named, False),
    (test_empty_expected_inventory_stops_never_a_sweep, False),
    (test_missing_expected_inventory_stops, False),
    (test_credential_shaped_read_value_refuses_never_echoed, False),
    (test_unreadable_field_map_is_a_hard_refusal, False),
    (test_map_without_provisioning_fields_is_a_hard_refusal, False),
    (test_malformed_inventory_row_is_a_hard_refusal, False),
    (test_no_surface_prints_a_token_or_a_full_location_id, False),
    (test_self_test_receipt_never_carries_a_token_shape, False),
    (test_plan_is_offline_and_carries_the_law, False),
    (test_cli_selftest_and_plan_are_offline, False),
    (test_module_source_contains_no_anthropic_identifier, False),
    (test_module_source_has_no_inlined_credential_shape, False),
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
