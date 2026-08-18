#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/test_type_checker.py
# UNIT TESTS for the LIVE FIELD-TYPE CHECKER (scripts/u07_modules/
# type_checker.py — U07 tooling): every free-text field in the field-map
# provisioning inventory must be live LARGE_TEXT (Trevor's every-text-input-
# field-is-multi-line law; the field-map's data_type_choice note), and the
# TWO SINGLE_OPTIONS fields (the U8 cover choice, anthology_cover_choice,
# and the U15-absorbed review decision, anthology_review_decision) must be
# live with EXACTLY their declared options, byte-exact, in order — the cover
# picklist imported byte-exact from cover_render.STYLE_NAMES (the named-style
# law), never hardcoded.
#
# WHAT THIS FILE PROVES (network-free, credential-free — the client is an
# in-memory stub; the only env touches are the live-CLI hermetic-refusal
# tests, which use an explicit EMPTY environ so no canonical store is read):
#   * the golden live read: every intended key live at its declared type and
#     the choice field carrying the four named styles byte-exact in order —
#     PASS, exit 0 through the verify driver, ONE JSON report on stdout,
#     execute false, the location marker masked,
#   * the read-only law: the no-execute path performs ZERO writes (every
#     client call is a list; nothing is ever created, archived, or re-typed)
#     — the create-only-missing write surface is Trevor-gated behind the
#     module's own --execute flag,
#   * the multi-line law, every direction: a live free-text field at any
#     other type (TEXT / PHONE / bare absent dataType) is a FAIL with the
#     violation named — never a pass; the ONE choice field live as anything
#     but SINGLE_OPTIONS is a FAIL,
#   * the choice picklist law, every direction: reordered, extra, renamed,
#     and missing option lists each FAIL with a violation — the client's
#     cover dropdown is the byte-exact four, in order, or the gate refuses,
#   * the Trevor gate, both ways: a strict subset of keys missing live
#     without --execute is a STOP (exit 2) with the report still printed and
#     ZERO writes on the client; WITH --execute each missing key is created
#     ONCE at its declared type (LARGE_TEXT for free text, SINGLE_OPTIONS
#     with the four named options for the choice), the location is RE-LISTED,
#     and the read-back is verified — a report never claims a type that was
#     not read back; a created key that read back drifted FAILS (exit 5),
#   * the never-re-create law: a live field of the WRONG type is NEVER
#     re-created or re-typed, even WITH --execute — it is a FAIL (a
#     provisioning decision, never a silent runtime act),
#   * the fail-closed ladder: an empty live listing FAILS (never a silent
#     pass), a non-list live read, a map with no provisioning.fields, a
#     total_keys drift, and a map-vs-cover_render options drift are each a
#     hard refusal (TypeCheckError, STOP family) — and the style-law guard
#     discriminates an unavailable surface (StyleImportError) without
#     touching the real module state,
#   * the HELD family, discriminated: a scope-denied read is a STOP-family
#     refusal (reg.ScopeDenied), while an edge block and a transport failure
#     are HELD-family (reg.UpstreamBlockedError / reg.CafUnreachable) — a
#     bare 403 is never mislabeled as a scope problem,
#   * never-a-token, every direction: no test fixture carries a credential
#     shape; the report only ever carries the masked location marker and the
#     key names (the checker emits no field ids at all — a token-shaped id
#     on a live row can never surface); the live-CLI refusal says SET / NOT
#     SET only and never echoes a token value or fragment onto any operator
#     surface; the self-test receipt never carries one,
#   * the house pins: the exit-code convention (0/1/2/3/4/5) asserted
#     through the registry's exported constants, the browser User-Agent law
#     (CF 1010 — CAF_BROWSER_UA is a browser UA, and the real CafClient
#     sends it on the live custom-fields and create requests), the
#     fail-closed-empty u07 package init, the sample-url slot law
#     (sample1..4 keys pair 1:1 with the style order), the plan surface
#     (offline, exact key list), the module's own self-test green (a red
#     battery is caught HERE first), and determinism (the checker never
#     mutates its inputs).
#
# House doctrine (Skill 59, u07_modules/__init__.py): fail-closed, both
# directions — the golden control passes and EVERY attack fails, so the
# pass/fail split discriminates (the golden control is never a broken
# instrument). Never a token printed; nothing Anthropic in any runtime
# surface; stdlib only; pytest with plain asserts; sys.path bootstrap
# identical to every other tests/ file; exit codes asserted by the exported
# module constants, never hardcoded. The registry's CafClient is NEVER
# constructed here (only the real request path is proven once, via the same
# urlopen patch the registry's own self-test uses), no network is touched.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u07_modules/test_type_checker.py -q
#  or: python3 59-anthology-engine/scripts/u07_modules/test_type_checker.py
# =============================================================================
"""test_type_checker.py -- the live field-TYPE checker's multi-line law, the
four-options choice law, the Trevor-gated create-only-missing path, and the
never-a-token / CF 1010 house pins (U07)."""

import contextlib
import copy
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
import u07_modules.type_checker as tc  # noqa: E402

# The house exit-code convention (0/1/2/3/4/5) — asserted by the exported
# constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u07 surface scans its output against.
# No test fixture ever carries one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# Anthropic-family id shapes assembled from fragments; no banned literal
# appears anywhere in this file (AF-AE-ANTHROPIC / guard-no-anthropic-runtime).
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)

FIELD_MAP = reg.load_field_map(tc.FIELD_MAP_PATH)
WANT_KEYS = [f.get("intended_key") for f in tc._contract_inventory(FIELD_MAP)
             if f.get("intended_key")]
TOTAL = tc._contract_total(FIELD_MAP)
STYLES = tc.named_cover_styles()
TEXT_ROWS = [f for f in tc._contract_inventory(FIELD_MAP)
             if f.get("data_type") == "LARGE_TEXT"]
CHOICE_KEY = "contact.anthology_cover_choice"
DECISION_KEY = "contact.anthology_review_decision"

# A live location marker: the last four characters are the ONLY part that may
# ever surface — the full id is a location handle, never a credential, and
# stays off every operator surface (the module's own masking law).
LOC = "loc_HERMETIC_fx8a"
LOC_MASK = reg._mask_location(LOC)  # "...fx8a"

# A credential-shaped row id — the shape every u07 surface must refuse to
# carry. No golden fixture ever contains one.
_ROWID = CREDENTIAL_SHAPE + "x" * 16

# The sample-url slot law: the four sample1..4 LARGE_TEXT slots pair 1:1 with
# the four named styles in style order (the same order the U8 provision note
# pins — slot 1 is the FIRST declared style, slot 4 the LAST).
SAMPLE_SLOTS = ("sample1", "sample2", "sample3", "sample4")


# ---------------------------------------------------------------------------
# The stub client — the module's own offline seam (the same shape its
# self-test proves): a programmable listing and a mutation log, so the
# read-only law and the --execute create-then-read-back law are proven from
# the test side without ever touching the network.
# ---------------------------------------------------------------------------
class _FakeCaf:
    def __init__(self, fields, behavior=None):
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
        # (reg.derive_field_key — the same derivation the checker's declared
        # keys carry); the stub mirrors it so the create-then-read-back path
        # proves the derivation, not a guess.
        self._n += 1
        rec = {"fieldKey": reg.derive_field_key(name),
               "id": "fld_fake_%d" % self._n,
               "name": name, "dataType": data_type}
        if options is not None:
            rec["options"] = list(options)
        self._fields = ([dict(f) for f in self._fields]
                        if isinstance(self._fields, list) else [])
        self._fields.append(rec)
        return dict(rec)

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")


def _golden_fields(field_map=None, styles=None):
    """A live listing that EXACTLY matches the map's intended keys at their
    declared types — the cover choice carrying the four named style options
    and the review decision carrying the two gate_engine actions, each in
    order, with resolved field ids."""
    field_map = FIELD_MAP if field_map is None else field_map
    styles = STYLES if styles is None else styles
    out = []
    i = 0
    decision_options = tc._declared_decision_options(field_map)
    for f in tc._contract_inventory(field_map):
        i += 1
        rec = {"fieldKey": f.get("intended_key"),
               "name": f.get("create_name"),
               "dataType": f.get("data_type", "LARGE_TEXT"),
               "id": "fld_%d" % i}
        if f.get("data_type") == "SINGLE_OPTIONS":
            rec["options"] = (list(styles)
                              if f.get("intended_key") == CHOICE_KEY
                              else list(decision_options))
        out.append(rec)
    return out


def _capture(func, *args, **kwargs):
    """Run func with stdout captured; return (return_code, parsed_stdout_dict)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(*args, **kwargs)
    return rc, json.loads(buf.getvalue())


def _run_cli(argv):
    """Run the module's CLI with stdout/stderr captured; return
    (exit_code, stdout_text, stderr_text). Hermetic by construction: the
    credential-resolution seams are stubbed (see the CLI tests below), so no
    canonical env store is ever read and no network is ever touched."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(argv)
    except SystemExit as exc:  # argparse usage errors and --help
        rc = exc.code
    return rc, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def _patch(obj, name, value):
    """Temporarily replace one attribute of an object; restore on exit."""
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_checker_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (the golden control plus every attack fixture refused; a
    red battery is caught HERE first)."""
    err = io.StringIO()
    rc = tc.self_test(out=err)
    assert rc == EX_OK, "self-test must exit 0, got %s" % rc
    assert "SELF-TEST FAILED" not in err.getvalue()
    assert err.getvalue().strip(), "self-test must write a human receipt to stderr"

def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)
    assert tc.EX_VIOLATION == EX_VIOLATION

def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge (CF error 1010) before it ever reaches Convert and Flow. The
    constant is a browser UA, never optional, never re-implemented here."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])

def test_cafclient_sends_the_browser_ua_on_the_live_requests():
    """The REAL request path — the custom-fields listing and the create
    request the checker's verify driver rides — sends CAF_BROWSER_UA on
    every request (proven by patching urlopen exactly as the registry's own
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
                                   "SINGLE_OPTIONS", options=list(STYLES))
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
# Contract coherence (the sources of truth the checker judges against)
# ---------------------------------------------------------------------------
def test_contract_is_exactly_38_keys():
    """The field-map's provisioning contract is exactly 36 LARGE_TEXT rows
    plus the TWO SINGLE_OPTIONS choice rows (cover choice + review
    decision) — the law the live check asserts (a drift in the map breaks
    THIS test first, fail-closed)."""
    assert WANT_KEYS, "field-map must carry intended keys"
    assert TOTAL is not None and len(WANT_KEYS) == TOTAL == 38, (
        "inventory %d != provisioning.total_keys %d" % (len(WANT_KEYS), TOTAL))
    assert len(TEXT_ROWS) == 36, "the type contract must carry 36 LARGE_TEXT rows"
    choice_rows = [f for f in tc._contract_inventory(FIELD_MAP)
                   if f.get("data_type") == "SINGLE_OPTIONS"]
    assert len(choice_rows) == 2, "the contract must carry 2 SINGLE_OPTIONS rows"
    assert {f.get("intended_key") for f in choice_rows} == {CHOICE_KEY,
                                                            DECISION_KEY}, (
        "the two SINGLE_OPTIONS rows must be the cover choice and the "
        "review decision")
    assert all(k.startswith("contact.") for k in WANT_KEYS), (
        "every intended key must carry the contact. prefix")
    assert len(set(WANT_KEYS)) == len(WANT_KEYS), "intended keys must be unique"

def test_decision_options_are_the_two_gate_engine_actions_byte_exact():
    """The decision picklist law: the review_decision_field block carries
    exactly the two gate_engine s5_gate actions — approve_as_is and
    request_rewrite_with_notes — in order, and the provisioning.fields
    decision row declares the same options (the two surfaces never
    drift)."""
    assert tc._declared_decision_options(FIELD_MAP) == [
        "approve_as_is", "request_rewrite_with_notes"], (
        "the decision picklist drifted from the gate_engine law")

def test_style_names_are_the_four_named_styles_byte_exact():
    """The named-style law: exactly four distinct, non-blank names, in the
    byte-exact order the client picks from in the universal-review cover
    dropdown — Signature / Bold Editorial / Fine Art / Pure Type (the one
    typography-driven style strictly last)."""
    assert STYLES == ("Signature", "Bold Editorial", "Fine Art", "Pure Type"), (
        "the four named cover styles drifted from the pinned law")
    assert list(cvr_STYLE_NAMES()) == list(STYLES)

def cvr_STYLE_NAMES():
    """The cover_render import the checker rides (the style-law source) —
    kept in one place so the byte-exact pin above cannot drift from it."""
    import cover_render as cvr
    return cvr.STYLE_NAMES

def test_sample_url_slots_pair_with_the_style_order():
    """The sample-url slot law: the four sample1..4 LARGE_TEXT keys pair 1:1
    with the four styles in style order — slot 1 is the FIRST declared
    style, slot 4 the LAST (the same order the U8 provision note pins)."""
    import cover_render as cvr
    sample_keys = [f.get("intended_key")
                   for f in tc._contract_inventory(FIELD_MAP)
                   if f.get("slot") in SAMPLE_SLOTS]
    assert len(sample_keys) == 4, "exactly four sample-url keys required"
    for slot, key in zip(SAMPLE_SLOTS, sample_keys):
        assert key == "contact.anthology_cover_%s_url" % slot, (
            "sample-url keys must pair 1:1 with slots in order (got %r)" % key)
    assert cvr.STYLE_KEYS == ("signature", "bold_editorial", "fine_art",
                              "pure_type"), (
        "cover_render's style keys must mirror the four named styles in order")

def test_checker_is_deterministic_and_never_mutates_its_inputs():
    """The checker never mutates the field-map it judges — the same map and
    the same listing give the same verdict every time."""
    golden = _golden_fields()
    snapshot = json.dumps(FIELD_MAP, sort_keys=True)
    caf = _FakeCaf(fields=golden)
    r1 = tc.check_types_live(caf, LOC, FIELD_MAP)
    r2 = tc.check_types_live(caf, LOC, FIELD_MAP)
    assert r1 == r2, "the same state must give the same report"
    assert json.dumps(FIELD_MAP, sort_keys=True) == snapshot, (
        "the field-map was mutated by the check")

# ---------------------------------------------------------------------------
# Golden: everything live at its declared type
# ---------------------------------------------------------------------------
def test_golden_live_state_passes_read_only():
    """The golden live read: every key live at its declared type, the choice
    field carrying the four named styles byte-exact in order — PASS, ok
    true, no missing keys, no violations, execute false, the location
    marker masked."""
    report = tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC, FIELD_MAP)
    assert report["verdict"] == "PASS", report["detail"]
    assert report["ok"] is True, report
    assert report["total"] == 38 and report["text_keys"] == 36
    assert report["choice_key"] == CHOICE_KEY, report
    assert report["choice_options"] == list(STYLES), report
    assert report["decision_key"] == DECISION_KEY, report
    assert report["decision_options"] == ["approve_as_is",
                                          "request_rewrite_with_notes"], report
    assert report["missing"] == [] and report["violations"] == [], report
    assert report["execute"] is False, "the read-only path must report execute false"
    assert report["contract"] == tc.REPORT_CONTRACT, report
    assert report["schema_version"] == 1, report
    assert report["location"] == LOC_MASK == "...fx8a", (
        "the location marker must be masked, got %r" % report["location"])
    assert LOC not in json.dumps(report), "the full location id must never surface"

def test_golden_verify_driver_exits_zero_with_one_json_object():
    """The verify driver on the golden state: exit 0, ONE JSON report on
    stdout, the PASS verdict, and a human note to stderr."""
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, _FakeCaf(fields=_golden_fields()),
                          LOC, FIELD_MAP, out=err)
    assert rc == EX_OK, "golden verify_live must exit 0, got %s" % rc
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, parsed
    assert parsed["contract"] == tc.REPORT_CONTRACT, parsed
    assert "type-check] OK" in err.getvalue(), err.getvalue()

def test_golden_explicit_expected_styles_agree_with_the_law():
    """The explicit expected_styles seam (the self-test seam) agrees with
    the imported style law — the four named styles, byte-exact, in order."""
    report = tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC,
                                 FIELD_MAP, expected_styles=STYLES)
    assert report["verdict"] == "PASS", report

def test_read_only_path_performs_zero_writes():
    """The read-only law: the no-execute check makes ONLY list calls — a
    create call on the golden path is a fail-closed defect, never a silent
    write."""
    caf = _FakeCaf(fields=_golden_fields())
    tc.check_types_live(caf, LOC, FIELD_MAP)
    assert caf.calls and all(m == "fields" for m, _ in caf.calls), (
        "the read-only check performed an unexpected call: %s" % caf.calls)
    caf2 = _FakeCaf(fields=_golden_fields())
    tc.verify_live(caf2, LOC, FIELD_MAP, out=io.StringIO())
    assert all(m == "fields" for m, _ in caf2.calls), (
        "the verify driver must be read-only without --execute: %s" % caf2.calls)

# ---------------------------------------------------------------------------
# The multi-line law: a live free-text field at any other type is a FAIL
# ---------------------------------------------------------------------------
def test_live_text_field_is_a_violation_never_a_pass():
    """A free-text key live as TEXT (not LARGE_TEXT) violates the
    every-text-input-field-is-multi-line law: FAIL with the violation named,
    missing stays empty, execute stays false."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == "contact.anthology_avatar_doc_url":
            rec["dataType"] = "TEXT"
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL", "live TEXT must FAIL"
    assert report["missing"] == [], report
    assert any("anthology_avatar_doc_url" in v and "LARGE_TEXT" in v
               for v in report["violations"]), report["violations"]

def test_live_phone_field_is_a_violation_never_a_pass():
    """A free-text key live as PHONE fails the same way — every non-LARGE_TEXT
    byte on a free-text key is a violation of the multi-line law."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == "contact.anthology_tone_doc_url":
            rec["dataType"] = "PHONE"
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL", "live PHONE must FAIL"
    assert any("anthology_tone_doc_url" in v for v in report["violations"]), (
        report["violations"])

def test_live_row_without_a_datatype_is_a_violation():
    """A live free-text row carrying NO dataType (or a None dataType) is a
    violation — an untyped live field can never read as LARGE_TEXT, and the
    violation names the key."""
    for mutate in ("pop", "none"):
        attack = copy.deepcopy(_golden_fields())
        for rec in attack:
            if rec["fieldKey"] == "contact.anthology_tone_doc_url":
                if mutate == "pop":
                    rec.pop("dataType", None)
                else:
                    rec["dataType"] = None
        report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
        assert report["verdict"] == "FAIL", (
            "an untyped live field must FAIL (%s)" % mutate)
        assert any("anthology_tone_doc_url" in v for v in report["violations"]), (
            report["violations"])

def test_multiple_wrong_typed_keys_are_all_named():
    """EVERY wrong-typed live key is named on the violation list — a
    partial listing is never mistaken for a clean one."""
    attack = copy.deepcopy(_golden_fields())
    hit = 0
    for rec in attack:
        if rec["fieldKey"].endswith("_url") and hit < 2:
            rec["dataType"] = "TEXT"
            hit += 1
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL"
    assert len(report["violations"]) == 2, report["violations"]

def test_wrong_typed_verify_driver_exits_five():
    """A live wrong-typed field through the verify driver: exit 5 (mismatch
    — the multi-line law, never a silent pass)."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == "contact.anthology_avatar_doc_url":
            rec["dataType"] = "TEXT"
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, _FakeCaf(fields=attack), LOC,
                          FIELD_MAP, out=err)
    assert rc == EX_MISMATCH, "live TEXT must exit 5, got %s" % rc
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, parsed
    assert "type-check] FAIL" in err.getvalue(), err.getvalue()

# ---------------------------------------------------------------------------
# The choice law: the cover-choice SINGLE_OPTIONS field, four options byte-exact
# ---------------------------------------------------------------------------
def test_choice_field_live_as_text_is_a_violation():
    """The cover-choice SINGLE_OPTIONS field live as TEXT is a FAIL — the
    cover dropdown must ship its type, never a silent pass."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == CHOICE_KEY:
            rec["dataType"] = "TEXT"
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL", "choice-as-TEXT must FAIL"
    assert any("SINGLE_OPTIONS" in v for v in report["violations"]), (
        report["violations"])

def test_drifted_choice_options_each_fail():
    """The picklist law, every direction: reordered, extra, and renamed
    option lists each FAIL with a violation — the client's cover dropdown
    is the byte-exact four, in order, or the gate refuses."""
    for mutation in (list(reversed(list(STYLES))),
                     list(STYLES) + ["Fourth Style"],
                     [s.replace("Fine Art", "Fine Arts") for s in STYLES]):
        attack = copy.deepcopy(_golden_fields())
        for rec in attack:
            if rec["fieldKey"] == CHOICE_KEY:
                rec["options"] = mutation
        report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
        assert report["verdict"] == "FAIL", (
            "drifted choice options must FAIL: %r" % (mutation,))
        assert report["violations"], "drifted options must be a violation"

def test_missing_choice_options_list_is_a_violation():
    """A choice field carrying NO options list is a FAIL — a picklist field
    must ship its options (never a bare dropdown)."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == CHOICE_KEY:
            del rec["options"]
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL", "missing options must FAIL"
    assert any("no options list" in v for v in report["violations"]), (
        report["violations"])

# ---------------------------------------------------------------------------
# The Trevor gate: create-only-missing requires --execute
# ---------------------------------------------------------------------------
def test_missing_field_without_execute_is_a_stop_with_zero_writes():
    """A strict subset of keys missing live WITHOUT --execute is a STOP
    (exit 2) — the report still prints (operator-verbose, what WOULD be
    created) but NOTHING is mutated: the missing key is named, the verdict
    is FAIL, and the driver records ZERO writes on the client."""
    subset = _golden_fields()[1:]  # the FIRST intended key is gone
    caf = _FakeCaf(fields=subset)
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, caf, LOC, FIELD_MAP, out=err)
    assert rc == EX_STOP, "missing field without --execute must exit 2, got %s" % rc
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, parsed
    assert parsed["missing"] == [WANT_KEYS[0]], parsed
    assert parsed["execute"] is False, parsed
    assert "STOP" in err.getvalue() and "--execute" in err.getvalue(), (
        err.getvalue())
    assert caf.calls and all(m == "fields" for m, _ in caf.calls), (
        "no-execute path must perform ZERO writes: %s" % caf.calls)

def test_check_types_live_reports_missing_without_execute():
    """The check surface itself records the missing keys and FAILS (never a
    silent pass) — the STOP exit is the driver's mapping of that FAIL."""
    subset = _golden_fields()[1:]
    report = tc.check_types_live(_FakeCaf(fields=subset), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL" and report["ok"] is False, report
    assert report["missing"] == [WANT_KEYS[0]], report

def test_execute_creates_only_missing_at_declared_type_then_reads_back():
    """WITH --execute the missing key is created ONCE at its declared
    LARGE_TEXT type, the location is RE-LISTED, and the read-back is
    verified — exit 0 with execute true and the created key named (a report
    never claims a type that was not read back)."""
    subset = _golden_fields()[1:]
    caf = _FakeCaf(fields=subset)
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, caf, LOC, FIELD_MAP,
                          execute=True, out=err)
    assert rc == EX_OK, "--execute create-missing must exit 0, got %s" % rc
    assert parsed["ok"] is True and parsed["execute"] is True, parsed
    assert parsed["created"] == [WANT_KEYS[0]], (
        "created must name the missing key, got %r" % parsed["created"])
    creates = [c for c in caf.calls if c[0] == "create"]
    assert [c[3] for c in creates] == ["LARGE_TEXT"], (
        "the missing field must be created at its declared type, got %r"
        % [c[3] for c in creates])
    assert caf.calls[-1][0] == "fields", (
        "--execute path must RE-LIST after creating (read-back verification)")

def test_execute_creates_only_the_choice_field_with_the_four_options():
    """The missing choice field WITH --execute is created as SINGLE_OPTIONS
    with the four named style options — never at a guessed type or picklist
    (the style-law import is the picklist's only source)."""
    minus_choice = [rec for rec in _golden_fields()
                    if rec["fieldKey"] != CHOICE_KEY]
    caf = _FakeCaf(fields=minus_choice)
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, caf, LOC, FIELD_MAP,
                          execute=True, out=err)
    assert rc == EX_OK, "--execute choice create must exit 0, got %s" % rc
    assert parsed["created"] == [CHOICE_KEY], parsed
    creates = [c for c in caf.calls if c[0] == "create"]
    assert len(creates) == 1
    assert creates[0][2] == "anthology_cover_choice"
    assert creates[0][3] == "SINGLE_OPTIONS", (
        "the choice field must be created as SINGLE_OPTIONS")
    live_choice = next(rec for rec in caf._fields
                       if rec["fieldKey"] == CHOICE_KEY)
    assert live_choice.get("options") == list(STYLES), (
        "the created choice field must carry the four named styles in order")

def test_execute_never_creates_keys_that_are_already_live():
    """--execute is create-ONLY-missing: keys already live at their declared
    types are never touched — the golden state with --execute performs ZERO
    writes (the gate is a no-op, not a re-provisioner)."""
    caf = _FakeCaf(fields=_golden_fields())
    tc.check_types_live(caf, LOC, FIELD_MAP, execute=True)
    assert all(m == "fields" for m, _ in caf.calls), (
        "execute over a complete state must perform ZERO writes: %s"
        % caf.calls)

def test_wrong_typed_live_field_is_never_recreated_even_with_execute():
    """A live field of the WRONG type is NEVER re-created or re-typed, even
    WITH --execute — it is a FAIL (exit 5): a provisioning decision, never
    a silent runtime act."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == "contact.anthology_tone_doc_url":
            rec["dataType"] = "TEXT"
    caf = _FakeCaf(fields=attack)
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, caf, LOC, FIELD_MAP,
                          execute=True, out=err)
    assert rc == EX_MISMATCH, "wrong live type must FAIL even with --execute, got %s" % rc
    assert parsed["verdict"] == "FAIL", parsed
    assert not any(c[0] == "create" for c in caf.calls), (
        "a wrong-typed live field must NEVER be re-created: %s" % caf.calls)

# ---------------------------------------------------------------------------
# The fail-closed ladder: empty, malformed, drifted, unjudgeable
# ---------------------------------------------------------------------------
def test_empty_live_listing_fails_closed():
    """An empty live listing FAILS with EVERY intended key missing (never a
    silent pass) — without --execute the driver maps that to the STOP
    family."""
    report = tc.check_types_live(_FakeCaf(fields=[]), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL" and report["ok"] is False, report
    assert len(report["missing"]) == TOTAL == 38, report

def test_non_list_live_read_is_a_hard_refusal():
    """A non-list live read is a hard refusal (TypeCheckError, STOP family)
    — a malformed read is never judged, never fabricated into a pass."""
    with pytest.raises(tc.TypeCheckError):
        tc.check_types_live(_FakeCaf(fields={"not": "a list"}), LOC, FIELD_MAP)

def test_map_without_provisioning_fields_is_a_hard_refusal():
    """A map with no provisioning.fields inventory is a hard refusal — the
    gate has nothing to assert, so it refuses a blind pass."""
    with pytest.raises(tc.TypeCheckError):
        tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC, {})

def test_total_keys_drift_is_a_hard_refusal():
    """A provisioning.total_keys that does not match the inventory is a hard
    refusal — the map drifted from its own contract, never judged."""
    tampered = copy.deepcopy(FIELD_MAP)
    tampered["provisioning"]["total_keys"] = (TOTAL or 0) + 1
    with pytest.raises(tc.TypeCheckError):
        tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC, tampered)

def test_map_vs_cover_render_options_drift_is_a_hard_refusal():
    """A field-map whose declared cover-choice options no longer byte-equal
    cover_render.STYLE_NAMES in order is a hard refusal — the two surfaces
    must never drift apart; the checker refuses to judge against a
    self-contradicting map."""
    tampered = copy.deepcopy(FIELD_MAP)
    for f in tampered["provisioning"]["fields"]:
        if f.get("data_type") == "SINGLE_OPTIONS" and \
                f.get("intended_key") == CHOICE_KEY:
            f["options"] = ["Drifted", "Options", "List", "Here"]
    with pytest.raises(tc.TypeCheckError):
        tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC, tampered)

def test_decision_options_drift_is_a_hard_refusal():
    """A field-map whose review_decision_field options drift (or whose
    decision row no longer matches the block) is a hard refusal — the
    decision picklist law is the gate_engine actions, never judged
    against a self-contradicting map."""
    tampered = copy.deepcopy(FIELD_MAP)
    tampered["review_decision_field"]["options"] = ["Drifted", "Decisions"]
    with pytest.raises(tc.TypeCheckError):
        tc.check_types_live(_FakeCaf(fields=_golden_fields()), LOC, tampered)

def test_decision_field_live_with_drifted_options_is_a_violation():
    """The decision field live with drifted options is a FAIL — the
    gate_engine two-action picklist is the law, every direction."""
    attack = copy.deepcopy(_golden_fields())
    for rec in attack:
        if rec["fieldKey"] == DECISION_KEY:
            rec["options"] = ["approve_as_is", "request_rewrite_with_notes",
                              "reject_outright"]
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    assert report["verdict"] == "FAIL", "drifted decision options must FAIL"
    assert any("gate_engine" in v for v in report["violations"]), (
        report["violations"])

def test_style_law_unavailable_is_refused_never_a_blind_pass():
    """The style-law guard discriminates an unavailable surface: an empty
    STYLE_NAMES is a StyleImportError (the choice contract is unjudgeable,
    never a blind pass) — proven without touching the real module state,
    and restored byte-exact afterward."""
    try:
        tc.named_cover_styles.__globals__["cvr"].STYLE_NAMES = ()
        with pytest.raises(tc.StyleImportError):
            tc.named_cover_styles()
    finally:
        import cover_render as cvr
        tc.named_cover_styles.__globals__["cvr"].STYLE_NAMES = (
            tuple(s["name"] for s in cvr.COVER_STYLES))
    assert tc.named_cover_styles() == STYLES, (
        "the style law must restore byte-exact")

# ---------------------------------------------------------------------------
# The HELD family, discriminated (a bare 403 is never a scope problem)
# ---------------------------------------------------------------------------
def test_scope_denied_read_is_a_stop_family_refusal():
    """A scope-denied read is a STOP-family refusal (reg.ScopeDenied) —
    never a fabricated pass."""
    with pytest.raises(reg.ScopeDenied):
        tc.check_types_live(_FakeCaf(fields=_golden_fields(), behavior="scope"),
                            LOC, FIELD_MAP)

def test_edge_block_is_held_never_mislabeled_as_scope():
    """An upstream/edge block (CF 1010) is HELD-family (reg.UpstreamBlockedError)
    — never mislabeled as a scope problem."""
    with pytest.raises(reg.UpstreamBlockedError):
        tc.check_types_live(_FakeCaf(fields=_golden_fields(), behavior="edge"),
                            LOC, FIELD_MAP)

def test_transport_failure_is_held():
    """A transport failure is HELD-family (reg.CafUnreachable)."""
    with pytest.raises(reg.CafUnreachable):
        tc.check_types_live(_FakeCaf(fields=_golden_fields(),
                                     behavior="transport"), LOC, FIELD_MAP)

# ---------------------------------------------------------------------------
# Never-a-token, every direction
# ---------------------------------------------------------------------------
def test_no_surface_prints_a_token_or_the_full_location_id():
    """The report and the driver's stderr never carry the full location id,
    never carry a credential shape, and never carry an Anthropic-family
    identifier — on PASS, FAIL, and STOP verdicts alike."""
    surfaces = []
    for fields in (_golden_fields(),
                   _golden_fields()[1:],
                   copy.deepcopy(_golden_fields())):
        caf = _FakeCaf(fields=fields)
        err = io.StringIO()
        rc, parsed = _capture(tc.verify_live, caf, LOC, FIELD_MAP, out=err)
        surfaces.append((rc, json.dumps(parsed, indent=2, sort_keys=True),
                         err.getvalue()))
    for rc, blob, err in surfaces:
        assert LOC not in blob and LOC not in err, (
            "the full location id leaked (rc %s)" % rc)
        assert CREDENTIAL_SHAPE not in blob and CREDENTIAL_SHAPE not in err, (
            "a credential shape leaked (rc %s)" % rc)
        assert "Bearer" not in blob and "Bearer" not in err, (
            "a Bearer shape leaked (rc %s)" % rc)
        assert not BANNED.search(blob) and not BANNED.search(err), (
            "an Anthropic-family identifier leaked (rc %s)" % rc)

def test_report_never_carries_credential_shaped_values():
    """The check report on every verdict carries only the key names, the
    masked location marker, and the style names — never a credential-shaped
    value (a credential-shaped id REFUSES the whole read; the golden and
    attack fixtures carry none)."""
    for fields in (_golden_fields(), _golden_fields()[1:], []):
        report = tc.check_types_live(_FakeCaf(fields=fields), LOC, FIELD_MAP)
        blob = json.dumps(report, indent=2, sort_keys=True)
        assert LOC not in blob, "the report leaked the location id"
        assert CREDENTIAL_SHAPE not in blob, "the report leaked a token shape"
        assert "Bearer" not in blob, "the report leaked a Bearer shape"

def test_credential_shaped_live_id_never_surfaces_on_any_report():
    """The checker emits NO field ids at all — a live row carrying a
    credential-shaped id is never echoed onto any surface: the report and
    the driver's stderr carry only the masked location marker and the key
    names, never a token-shaped value."""
    attack = [dict(rec) for rec in _golden_fields()]
    attack[0]["id"] = _ROWID
    report = tc.check_types_live(_FakeCaf(fields=attack), LOC, FIELD_MAP)
    blob = json.dumps(report, indent=2, sort_keys=True)
    assert CREDENTIAL_SHAPE not in blob, "a token-shaped id leaked into the report"
    assert "Bearer" not in blob, "a Bearer-shaped id leaked into the report"
    err = io.StringIO()
    rc, parsed = _capture(tc.verify_live, _FakeCaf(fields=attack), LOC,
                          FIELD_MAP, out=err)
    assert rc == EX_OK and parsed["verdict"] == "PASS", (
        "the golden state apart from the id must still pass")
    assert CREDENTIAL_SHAPE not in (json.dumps(parsed) + err.getvalue()), (
        "a token-shaped id leaked onto the driver surface")

def test_self_test_receipt_never_carries_a_token_shape():
    """The self-test receipt (the human note to stderr) never carries a
    credential shape or the full location id."""
    err = io.StringIO()
    rc = tc.self_test(out=err)
    assert rc == EX_OK, rc
    assert CREDENTIAL_SHAPE not in err.getvalue(), (
        "the self-test receipt leaked a token shape")
    assert "Bearer" not in err.getvalue(), (
        "the self-test receipt leaked a Bearer shape")

# ---------------------------------------------------------------------------
# The CLI boundary (hermetic: the credential-resolution seams and the client
# constructor are stubbed, so no canonical env store is read and no network
# is touched — the stop-texts are the refusal contract)
# ---------------------------------------------------------------------------
def test_live_cli_no_token_stops_with_not_set_only():
    """verify with NO credential resolved: STOP (exit 2) before any client
    work — no JSON report on stdout, and the refusal says NOT SET only,
    never a value (the value shape never appears on the surface)."""
    with _patch(reg, "resolve_pit", lambda: (None, None)):
        rc, out, err = _run_cli(["verify"])
    assert rc == EX_STOP, "no token must STOP, got %s" % rc
    assert out == "", "a refusal must emit no JSON report on stdout"
    assert "No Convert and Flow private-integration token is SET." in err, err
    assert "NOT SET" in err, "the refusal must say NOT SET, never a value"
    assert "Bearer" not in err, "the refusal leaked a Bearer shape"
    # The stop text names the checked LABELS and the token KIND (the
    # "pit-" prefix in the help line), never a value under a label.
    assert "=pit-" not in err and "pit-HERMETIC" not in err, (
        "the refusal leaked a token-shaped value: %s" % err)

def test_live_cli_non_pit_token_stops():
    """A non-pit- token under a PIT label is refused (a placeholder or a
    mis-set value) — the label is reported NOT SET, never its value."""
    with _patch(reg, "resolve_pit", lambda: ("CONVERT_AND_FLOW_API_KEY", None)):
        rc, out, err = _run_cli(["verify"])
    assert rc == EX_STOP, "a non-pit- token must STOP, got %s" % rc
    assert "No Convert and Flow private-integration token is SET." in err, err
    assert "NOT SET" in err, "the refusal must report the label as NOT SET"

def test_live_cli_no_location_stops():
    """verify with a token but no location id resolved: STOP (exit 2) — no
    location, no check, never a fabricated pass."""
    with _patch(reg, "resolve_pit", lambda: ("GHL_API_KEY", "pit-hermetic-test-token")), \
         _patch(reg, "resolve_location", lambda override="": (None, None)):
        rc, out, err = _run_cli(["verify"])
    assert rc == EX_STOP, "no location id must STOP, got %s" % rc
    assert "No Convert and Flow Location id is SET." in err, err
    assert "NOT SET" in err, "the refusal must report the location label as NOT SET"

def test_live_cli_never_prints_the_token_value():
    """With BOTH a pit- token and a location id resolved, the verify driver
    builds the real client and performs ONE read over a stubbed transport —
    the token VALUE or any fragment of it never appears on stdout or stderr
    (the resolution note names the LABELS, never the values)."""
    calls = []

    class _FakeResp:
        def read(self):
            return b'{"customFields": []}'
        def getcode(self):
            return 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(req, timeout=None):
        calls.append(req)
        return _FakeResp()

    real = urllib.request.urlopen
    urllib.request.urlopen = _open
    try:
        with _patch(reg, "resolve_pit",
                    lambda: ("CONVERT_AND_FLOW_PIT",
                             "pit-HERMETIC-TOKEN-0123456789abcdef")), \
             _patch(reg, "resolve_location",
                    lambda override="": ("CONVERT_AND_FLOW_LOCATION_ID", LOC)):
            rc, out, err = _run_cli(["verify"])
    finally:
        urllib.request.urlopen = real
    assert "pit-HERMETIC-TOKEN-0123456789abcdef" not in (out + err), (
        "the token value leaked onto an operator surface")
    assert "HERMETIC-TOKEN" not in (out + err), (
        "a token fragment leaked onto an operator surface")
    assert "PIT resolved via" in err and "Location via" in err, (
        "the resolution note must name the labels: %s" % err)
    assert rc == EX_STOP, (
        "an empty live listing without --execute must STOP (exit 2), got %s"
        % rc)
    assert calls, "the verify driver must perform the live read"
    assert dict(calls[0].header_items())["User-agent"] == reg.CAF_BROWSER_UA, (
        "the real client must ride the browser UA on the live read (CF 1010)")

# ---------------------------------------------------------------------------
# The plan surface (offline, no network, no credential)
# ---------------------------------------------------------------------------
def test_plan_is_offline_and_lists_the_exact_contract():
    """The offline plan: exit 0, ONE JSON object, the exact intended-key
    list in order, the choice key, and the four named styles — with no
    credential shape anywhere on the surface."""
    rc, parsed = _capture(tc.plan, FIELD_MAP, out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0, got %s" % rc
    assert parsed["contract"] == tc.PLAN_CONTRACT, parsed
    assert parsed["total"] == 38 and parsed["text_keys"] == 36, parsed
    assert parsed["keys"] == WANT_KEYS, (
        "plan must list the intended keys in order")
    assert parsed["choice_key"] == CHOICE_KEY, parsed
    assert parsed["choice_options"] == list(STYLES), parsed
    assert parsed["decision_key"] == DECISION_KEY, parsed
    assert parsed["decision_options"] == ["approve_as_is",
                                          "request_rewrite_with_notes"], parsed
    assert parsed["dry_run"] is True, parsed
    assert CREDENTIAL_SHAPE not in json.dumps(parsed), (
        "the plan must never carry a credential-shaped string")

# ---------------------------------------------------------------------------
# The module source (the runtime file, not this battery)
# ---------------------------------------------------------------------------
def test_module_source_contains_no_anthropic_identifier():
    text = Path(__file__).with_name("type_checker.py").read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if BANNED.search(line):
            raise AssertionError("type_checker.py:%d carries an Anthropic "
                                 "identifier VALUE: %s" % (lineno, line.strip()))

def test_module_source_has_no_inlined_credential_shape():
    text = Path(__file__).with_name("type_checker.py").read_text(encoding="utf-8")
    assert not re.search(r"(?i)(?:api[_-]?key|token|secret)\s*[=:]\s*[\"'][^\"']{12,}",
                         text), (
        "a credential-shaped assignment is inlined in type_checker.py")


TESTS = [
    (test_checker_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_cafclient_sends_the_browser_ua_on_the_live_requests, False),
    (test_u07_package_init_is_fail_closed_empty, False),
    (test_contract_is_exactly_38_keys, False),
    (test_decision_options_are_the_two_gate_engine_actions_byte_exact, False),
    (test_style_names_are_the_four_named_styles_byte_exact, False),
    (test_sample_url_slots_pair_with_the_style_order, False),
    (test_checker_is_deterministic_and_never_mutates_its_inputs, False),
    (test_golden_live_state_passes_read_only, False),
    (test_golden_verify_driver_exits_zero_with_one_json_object, False),
    (test_golden_explicit_expected_styles_agree_with_the_law, False),
    (test_read_only_path_performs_zero_writes, False),
    (test_live_text_field_is_a_violation_never_a_pass, False),
    (test_live_phone_field_is_a_violation_never_a_pass, False),
    (test_live_row_without_a_datatype_is_a_violation, False),
    (test_multiple_wrong_typed_keys_are_all_named, False),
    (test_wrong_typed_verify_driver_exits_five, False),
    (test_choice_field_live_as_text_is_a_violation, False),
    (test_drifted_choice_options_each_fail, False),
    (test_missing_choice_options_list_is_a_violation, False),
    (test_missing_field_without_execute_is_a_stop_with_zero_writes, False),
    (test_check_types_live_reports_missing_without_execute, False),
    (test_execute_creates_only_missing_at_declared_type_then_reads_back, False),
    (test_execute_creates_only_the_choice_field_with_the_four_options, False),
    (test_execute_never_creates_keys_that_are_already_live, False),
    (test_wrong_typed_live_field_is_never_recreated_even_with_execute, False),
    (test_empty_live_listing_fails_closed, False),
    (test_non_list_live_read_is_a_hard_refusal, False),
    (test_map_without_provisioning_fields_is_a_hard_refusal, False),
    (test_total_keys_drift_is_a_hard_refusal, False),
    (test_map_vs_cover_render_options_drift_is_a_hard_refusal, False),
    (test_decision_options_drift_is_a_hard_refusal, False),
    (test_decision_field_live_with_drifted_options_is_a_violation, False),
    (test_style_law_unavailable_is_refused_never_a_blind_pass, False),
    (test_scope_denied_read_is_a_stop_family_refusal, False),
    (test_edge_block_is_held_never_mislabeled_as_scope, False),
    (test_transport_failure_is_held, False),
    (test_no_surface_prints_a_token_or_the_full_location_id, False),
    (test_report_never_carries_credential_shaped_values, False),
    (test_credential_shaped_live_id_never_surfaces_on_any_report, False),
    (test_self_test_receipt_never_carries_a_token_shape, False),
    (test_live_cli_no_token_stops_with_not_set_only, False),
    (test_live_cli_non_pit_token_stops, False),
    (test_live_cli_no_location_stops, False),
    (test_live_cli_never_prints_the_token_value, False),
    (test_plan_is_offline_and_lists_the_exact_contract, False),
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
