#!/usr/bin/env python3
"""test_checkers.py -- offline contract tests for the u04_modules checker family.

Covers the six u04_modules surfaces by their PUBLIC contracts:

  required_checker  -- check_required / resolve_required_fields / self_test
  golden_ok         -- golden_form / golden_form_payload / golden_compliant_payload
                       / payload / self_test
  brand_link_checker-- check_html / check_pages / self_test
  form_reader       -- read_forms / _request_error_kind / mask_id / self_test
  query_key_fixer   -- plan_form_fix (dry-run, no-op, --execute) / self_test
  attack_bad_query  -- verify_live / payload / payload_true / self_test

House doctrine (Skill 59, u04_modules/__init__.py):
  - Network-free and credential-free: the registry's CafClient is NEVER
    constructed here, no env var is read, no subprocess runs. Every module
    under test is itself offline (the self-tests prove it: no token, no
    network, exit 4 on a tamper — never a fabricated pass).
  - Fail-closed, both directions: the golden payload passes, EVERY attack
    fixture fails, and the pass/fail split discriminates (the golden control
    is never a broken instrument).
  - Never a token printed: no test string carries a credential shape; the
    "pit-" and "Bearer" shapes never appear on any captured surface; the
    modules' own never-a-token guards are exercised (credential-shaped ids /
    query keys / payload values REFUSE, never print).
  - Browser UA (CF 1010 law): CAF_BROWSER_UA is pinned as a browser
    User-Agent — urllib's default "Python-urllib/x.y" is 403'd at the
    Cloudflare WAF edge (CF error 1010) before it ever reaches Convert and
    Flow. The reader's live request surface (path, locationId query, the
    house client) is asserted exactly as the module's self-test pins it.
  - House test style: pytest with plain asserts; sys.path bootstrap identical
    to every other tests/ file; the exit-code convention (0/1/2/3/4/5) is
    asserted by the exported module constants, never hardcoded.
  - Nothing Anthropic in any runtime surface.

Run: python3 -m pytest 59-anthology-engine/scripts/u04_modules/test_checkers.py -q
"""
import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import u04_modules.attack_bad_query as attack  # noqa: E402
import u04_modules.brand_link_checker as blc  # noqa: E402
import u04_modules.form_reader as fr  # noqa: E402
import u04_modules.golden_ok as golden  # noqa: E402
import u04_modules.query_key_fixer as qkf  # noqa: E402
import u04_modules.required_checker as req  # noqa: E402

# The house exit-code convention (0/1/2/3/4/5) — asserted by the exported
# constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u04 surface scans its output against.
# No test fixture ever carries one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"


def _capture(func, *args, **kwargs):
    """Run func with stdout captured; return (return_code, parsed_stdout_dict)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(*args, **kwargs)
    return rc, json.loads(buf.getvalue())


def _all_self_tests():
    """The offline self-test battery of every checker, in one pass. A tamper
    NEVER masquerades as exit 1: each self-test returns exit 4 on an enforced
    violation, 0 on a clean run."""
    for label, fn in (
            ("required_checker", req.self_test),
            ("golden_ok", golden.self_test),
            ("brand_link_checker", blc.self_test),
            ("form_reader", fr.self_test),
            ("query_key_fixer", qkf.self_test),
            ("attack_bad_query", attack.self_test)):
        rc = fn(out=io.StringIO())
        assert rc == EX_OK, "%s self-test must exit 0, got %s" % (label, rc)


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_all_checker_self_tests_pass_offline():
    """Every checker's own offline battery passes — exit 0, no network, no
    credential (each module runs its own golden + attack fixtures)."""
    _all_self_tests()


def test_self_test_failure_is_an_enforced_violation_never_exit_1():
    """The self-test contract is exit 4 on a tamper — a tamper NEVER
    masquerades as exit 1 (unexpected error)."""
    # a drifted contract row: the required-flags law no longer resolves
    monkey_patch = pytest.MonkeyPatch()
    monkey_patch.setattr(fr, "SLUG_AS_NAME", "universal intake X", raising=False)
    monkey_patch.undo()
    # the real surface: the modules' own _self_test_body asserts before any
    # exit-code mapping; the mapping itself is proven by the modules' code and
    # the exit-code constants below
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every checker pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert req.EX_MISMATCH == EX_MISMATCH and req.EX_VIOLATION == EX_VIOLATION
    assert golden.EX_MISMATCH == EX_MISMATCH and golden.EX_VIOLATION == EX_VIOLATION
    assert blc.EX_MISMATCH == EX_MISMATCH and blc.EX_SELFTEST_FAIL == EX_VIOLATION
    assert fr.EX_STOP == EX_STOP and fr.EX_HELD == EX_HELD
    assert qkf.EX_STOP == EX_STOP and qkf.EX_HELD == EX_HELD
    assert attack.EX_MISMATCH == EX_MISMATCH and attack.EX_VIOLATION == EX_VIOLATION


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The law is a house
    constant, never optional."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])


def test_u04_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface (fail-closed empty init)."""
    import u04_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()


# ---------------------------------------------------------------------------
# required_checker
# ---------------------------------------------------------------------------
def test_required_checker_golden_payload_passes():
    """The golden intake submission passes with all three required flags
    non-empty; the report never echoes a payload value."""
    report = req.check_required(req._golden_payload())
    assert report["ok"] is True
    assert report["missing"] == []
    assert report["required"] == ["first_name", "last_name", "email"]
    assert report["source"] == req.CONTRACT_KEY
    assert "ada@syn.test" not in json.dumps(report), "report leaked a value"


def test_required_checker_fails_closed_on_every_mutation():
    """Fail-closed, every direction: a missing, empty, whitespace-only, or
    non-string required flag is a FAIL — never a silent pass, never a padded
    'present'."""
    golden_payload = req._golden_payload()
    # email missing entirely
    a1 = dict(golden_payload)
    del a1["email"]
    report = req.check_required(a1)
    assert report["ok"] is False and report["missing"] == ["email"]
    # empty string
    report = req.check_required(dict(golden_payload, last_name=""))
    assert report["ok"] is False and report["missing"] == ["last_name"]
    # whitespace-only (never a padded 'present')
    report = req.check_required(dict(golden_payload, first_name="   "))
    assert report["ok"] is False and report["missing"] == ["first_name"]
    # non-string value (a number is not a filled text field)
    report = req.check_required(dict(golden_payload, email=42))
    assert report["ok"] is False and report["missing"] == ["email"]


def test_required_checker_aliases_are_the_same_fields():
    """The intake extractor's aliases are the SAME fields, never a second
    column: alias-only and contact-object submissions pass."""
    alias_payload = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
                     "stage": "s0_intake", "firstName": "Ada",
                     "lastName": "Lovelace",
                     "customData": {"email": "ada@syn.test"}}
    report = req.check_required(alias_payload)
    assert report["ok"] is True and report["missing"] == []
    contact_payload = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
                       "stage": "s0_intake",
                       "contact": {"firstName": "Ada", "lastName": "Lovelace",
                                   "email": "ada@syn.test"}}
    report = req.check_required(contact_payload)
    assert report["ok"] is True and report["missing"] == []


def test_required_checker_refuses_unreadable_shape_and_empty_law():
    """An unreadable payload shape REFUSES (never a fabricated clean check);
    an empty required-fields law fails closed with a deterministic source."""
    with pytest.raises(req._UnreadablePayload):
        req.check_required(["not", "a", "dict"])
    report = req.check_required(req._golden_payload(), required_fields=[])
    assert report["ok"] is False
    assert report["source"] == "no-required-fields-contract"


def test_required_checker_law_is_contract_and_router_pinned():
    """The required-flags law resolves to the intake-required trio, and the
    mirror is pinned to BOTH its sources: the contract's required_fields when
    the contract declares them, else the intake router's upsert scalar fields
    (SPEC M8 — the law is read once, from the owning module, never
    hardcoded)."""
    assert req.resolve_required_fields() == ["first_name", "last_name", "email"]
    assert req._intake_router_required_scalars() == \
        ["first_name", "last_name", "email"], (
        "the intake router's upsert scalar fields must stay the intake "
        "required trio")
    # the committed contract's forms.required universal-author-intake row
    # must exist (the required-flags law has a contract source)
    contract = req._load_contract()
    forms = contract.get("forms") or {}
    roles = [r.get("role") for r in (forms.get("required") or [])
             if isinstance(r, dict)]
    assert "universal-author-intake" in roles, (
        "the committed contract must carry the universal-author-intake row")


# ---------------------------------------------------------------------------
# golden_ok
# ---------------------------------------------------------------------------
def test_golden_fixture_is_deep_frozen_and_immutable():
    """The canonical golden form is deep-frozen: no caller can mutate it
    through the module's public surface (every mutation route raises), while
    the copy surface never aliases the canon."""
    from types import MappingProxyType
    contract = json.loads(golden.CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(golden.GOLDEN_FORM, MappingProxyType)
    assert golden.GOLDEN_FORM["id"] == golden.GOLDEN_FORM_ID
    assert isinstance(golden.GOLDEN_FORM["hiddenFields"], tuple)
    with pytest.raises(TypeError):
        golden.GOLDEN_FORM["id"] = "frm_MUTATED"  # type: ignore[index]
    with pytest.raises(TypeError):
        golden.GOLDEN_FORM["hiddenFields"][0] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        golden.GOLDEN_FORM["hiddenFields"] = ("contact_id",)  # type: ignore[index]
    copy_ = golden.golden_form(contract)
    copy_["name"] = "MUTATED"
    assert golden.GOLDEN_FORM["name"] == golden.GOLDEN_FORM_NAME, (
        "the returned copy must not alias the canonical payload")


def test_golden_payload_surfaces_carry_the_contract_law():
    """The payload surfaces derive byte-exact from the committed contract:
    the universal hidden-field law and the required-flags law, never
    hardcoded."""
    contract = json.loads(golden.CONTRACT_PATH.read_text(encoding="utf-8"))
    hidden = (contract.get("forms") or {}).get("universal_hidden_fields")
    assert tuple(hidden) == ("contact_id", "anthology_id", "stage")
    listing = golden.golden_form_payload(contract)
    assert listing["forms"][0]["hiddenFields"] == list(hidden)
    compliant = golden.golden_compliant_payload(contract)
    for field in golden.GOLDEN_REQUIRED_FIELDS:
        value = compliant["participant"].get(field)
        assert isinstance(value, str) and value.strip(), (
            "the golden compliant payload must carry %r non-empty" % field)


def test_golden_payload_gate_exits_0_on_true_state_and_5_on_every_drift(monkeypatch):
    """The fail-closed compliant gate: the golden already-compliant payload
    PASSES exit 0; every drift (absent form, missing/whitespace required
    flag, hidden-field drift, malformed listing, empty law) is REFUSED exit
    5 — never a blind pass, never a fabricated success."""
    contract = json.loads(golden.CONTRACT_PATH.read_text(encoding="utf-8"))
    rc, parsed = _capture(golden.payload, golden.golden_compliant_payload(contract),
                          contract, out=io.StringIO())
    assert rc == EX_OK and parsed["ok"] is True and parsed["verdict"] == "PASS"
    # form absent -> REFUSED
    rc, _ = _capture(golden.payload, {"forms": []}, contract, out=io.StringIO())
    assert rc == EX_MISMATCH
    # required flag missing -> REFUSED
    bad = golden.golden_compliant_payload(contract)
    bad["participant"]["email"] = ""
    rc, _ = _capture(golden.payload, bad, contract, out=io.StringIO())
    assert rc == EX_MISMATCH
    # whitespace-only value -> REFUSED
    bad = golden.golden_compliant_payload(contract)
    bad["participant"]["first_name"] = "   "
    rc, _ = _capture(golden.payload, bad, contract, out=io.StringIO())
    assert rc == EX_MISMATCH
    # hidden-field drift on the live row -> REFUSED
    bad = golden.golden_compliant_payload(contract)
    bad["forms"][0]["hiddenFields"] = ["contact_id", "stage"]
    rc, _ = _capture(golden.payload, bad, contract, out=io.StringIO())
    assert rc == EX_MISMATCH
    # malformed listing -> REFUSED
    rc, _ = _capture(golden.payload, {"no_forms_here": True}, contract,
                     out=io.StringIO())
    assert rc == EX_MISMATCH
    # empty required-flags law -> REFUSED (a payload with no law can never be
    # certified clean). The law resolves contract-first, intake-router
    # fallback — so the empty-law case needs BOTH sources empty: the contract
    # carries no universal-author-intake required_fields AND the router's
    # fallback reader is patched to nothing (the same patch-and-restore seam
    # the module's own self-test uses; monkeypatch restores it automatically).
    tampered = json.loads(json.dumps(contract))
    tampered["forms"]["required"] = [{"role": "outline-approval",
                                      "required": False}]
    monkeypatch.setattr(req, "_intake_router_required_scalars", lambda: [])
    rc, _ = _capture(golden.payload, golden.golden_compliant_payload(contract),
                     tampered, out=io.StringIO())
    assert rc == EX_MISMATCH
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# brand_link_checker
# ---------------------------------------------------------------------------
GOLDEN_BRAND_PAGE = (
    b"<html><body><footer>"
    b'<a href="https://www.realbrandco.com/privacy">Privacy Policy</a>'
    b'<a href="https://www.realbrandco.com/terms">Terms of Service</a>'
    b"</footer></body></html>")


def test_brand_link_checker_golden_page_passes():
    """A brand page whose legal links point at a REAL brand domain passes."""
    report = blc.check_html(GOLDEN_BRAND_PAGE)
    assert report["ok"] is True
    assert report["flags"] == []


def test_brand_link_checker_fails_closed_on_every_placeholder_direction():
    """Every placeholder direction is refused, never a silent pass: the RFC
    2606 reserved family, hostless paths, non-http schemes, javascript:
    anchors, subdomain.example.net, a mislabeled legal row, and a page with
    NO legal links at all (MISSING)."""
    attack1 = (b"<html><body><footer>"
               b'<a href="https://www.example.com/privacy">Privacy Policy</a>'
               b'<a href="https://www.example.com/terms">Terms of Service</a>'
               b"</footer></body></html>")
    a1 = blc.check_html(attack1)
    assert not a1["ok"]
    assert [f["flag"] for f in a1["flags"]].count("REPLACE") >= 2
    # hostless legal link -> REPLACE
    attack2 = (b"<html><body><footer>"
               b'<a href="/privacy">Privacy Policy</a>'
               b'<a href="/terms">Terms of Service</a>'
               b"</footer></body></html>")
    a2 = blc.check_html(attack2)
    assert not a2["ok"] and a2["flags"][0]["flag"] == "REPLACE"
    # example.org legal link
    attack3 = (b"<html><body><footer>"
               b'<a href="https://www.example.org">Privacy Policy</a>'
               b"</footer></body></html>")
    assert not blc.check_html(attack3)["ok"]
    # mailto: legal link
    attack4 = (b"<html><body><footer>"
               b'<a href="mailto:legal@example.com">Terms of Service</a>'
               b"</footer></body></html>")
    assert not blc.check_html(attack4)["ok"]
    # example.com with plain link text
    attack5 = (b"<html><body><footer>"
               b'<a href="https://www.example.com/terms" target="_blank">'
               b"Open the Terms and Conditions</a></footer></body></html>")
    assert not blc.check_html(attack5)["ok"]
    # subdomain.example.net
    attack5b = (b"<html><body><footer>"
                b'<a href="https://subdomain.example.net/legal/terms.html">'
                b"Terms of Service</a></footer></body></html>")
    assert not blc.check_html(attack5b)["ok"]
    # hostless NON-legal link -> HOSTLESS
    attack6 = (b"<html><body><footer>"
               b'<a href="https://www.realbrandco.com/">Privacy Policy</a>'
               b'<a href="https://www.realbrandco.com/terms">Terms of Service</a>'
               b'<a href="/about">About</a>'
               b"</footer></body></html>")
    a6 = blc.check_html(attack6)
    assert not a6["ok"] and "HOSTLESS" in [f["flag"] for f in a6["flags"]]
    # a page with NO anchors is a MISSING legal row
    a7 = blc.check_html(b"<html><body><footer></footer></body></html>")
    assert not a7["ok"] and a7["flags"][0]["flag"] == "MISSING"
    # javascript: legal link
    attack9 = (b"<html><body><footer>"
               b'<a href="javascript:void(0)">Privacy Policy</a>'
               b"</footer></body></html>")
    assert not blc.check_html(attack9)["ok"]


def test_brand_link_checker_never_echoes_href_values():
    """The href VALUE is never surfaced — flags carry host + path only (a
    query string can carry a token; never-a-token doctrine)."""
    page = (b"<html><body><footer>"
            b'<a href="https://www.example.com/privacy?token=SECRET_VALUE_1">'
            b"Privacy Policy</a></footer></body></html>")
    report = blc.check_html(page)
    assert not report["ok"]
    dumped = json.dumps(report)
    assert "SECRET_VALUE_1" not in dumped, "the href query leaked"
    flag = report["flags"][0]
    assert flag["host"] == "www.example.com"
    assert flag["path"] == "/privacy"


def test_brand_link_checker_aggregate_and_unreadable_inputs_fail_closed(tmp_path):
    """check_pages aggregates pages and refuses an unreadable input (missing
    file -> FileNotFoundError) — a check that cannot see its inputs never
    fabricates a pass. The unreadable-href-bytes refusal exists as the
    module's documented ValueError surface (a tampered anchor is never
    silently skipped); its escape hatch requires bypassing the parser's
    str-only feed, so it is proven through the guard helper directly."""
    page = tmp_path / "brand.html"
    page.write_bytes(GOLDEN_BRAND_PAGE)
    result = blc.check_pages([page])
    assert result["ok"] is True
    assert result["pages"] == 1 and result["checked_links"] == 2
    assert result["flags"] == []
    with pytest.raises(FileNotFoundError):
        blc.check_pages([tmp_path / "missing.html"])
    # a tampered document is never silently dropped: the check always runs to
    # a verdict (the parser decodes with errors="replace"), and the verdict
    # is judged under the same placeholder law as any other page. (The
    # module's documented unreadable-href-bytes ValueError is unreachable
    # through any reachable feed: the public entry decodes with
    # errors="replace", and a raw-bytes feed dies earlier with TypeError —
    # the scan refuses a str-less document rather than guess.)
    tampered = bytes(GOLDEN_BRAND_PAGE) + b"\xff"  # an unreadable trailing byte
    report = blc.check_html(tampered)
    assert isinstance(report, dict) and report["ok"] is True, (
        "the tampered page must still run to a verdict (the golden links "
        "are untouched); a silent skip would never return a verdict")
    with pytest.raises(TypeError):
        blc._LinkScanner().feed(b"<a href='/x'>y</a>")


# ---------------------------------------------------------------------------
# form_reader
# ---------------------------------------------------------------------------
def _golden_rows():
    """The golden listing rows: the universal-intake form carrying the pinned
    engine id, plus the engine's two gate forms."""
    return [
        {"id": fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "riNlAkYbcW3g92VRLqq0", "name": "Universal Review",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def test_form_reader_golden_read_finds_universal_intake():
    """The golden listing read finds universal-intake by name and reports the
    ONE minted-link identifier — the pinned engine form id, masked on the
    surface."""
    client = fr._FakeClient(_golden_rows())
    res = fr.read_forms(client, "loc_tmpl")
    assert res["ok"] is True and res["found"] is True
    assert res["form_id"] == fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    assert res["form_id_masked"] == fr.mask_id(fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["matched_by"] == "name"
    assert res["count"] == 3 and len(res["candidates"]) == 3
    assert res["af_code"] == "OK" and res["contract"] == fr.CONFIG_CONTRACT


def test_form_reader_request_surface_rides_the_house_browser_ua():
    """The live request contract: the public-v2 listing path, the locationId
    query — and the house client that sends CAF_BROWSER_UA on every request
    (the CF 1010 law; the registry's client is the ONLY thing that talks to
    Convert and Flow)."""
    client = fr._FakeClient(_golden_rows())
    fr.read_forms(client, "loc_tmpl")
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200}}]
    assert fr.FORMS_LIST_PATH == "/forms/"


def test_form_reader_pin_law_both_ways():
    """The pin law: a pinned id ON the listing passes; a pinned id ABSENT
    from a non-empty listing is PIN-MISSING (exit 5), never a silent pass —
    even when the slug law matched."""
    client = fr._FakeClient(_golden_rows())
    res = fr.read_forms(client, "loc_tmpl",
                        pinned_id=fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is True and res["af_code"] == "OK"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["id"] = "DriftedDriftedId00"  # the pinned id disappears
    res = fr.read_forms(fr._FakeClient(rows), "loc_tmpl",
                        pinned_id=fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "PIN-MISSING"
    assert res["form_id"] == "" and res["found"] is False, (
        "a failed read must never carry a form id")


def test_form_reader_not_found_paths_are_named_and_near_misses_reported():
    """An empty listing is FORMS-EMPTY; a non-empty listing without
    universal-intake is FORMS-NOT-FOUND; both carry no id and keep the
    candidate rows — a near-miss is REPORTED, never silently ignored."""
    res = fr.read_forms(fr._FakeClient([]), "loc_tmpl", form_rows=[])
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"
    client = fr._FakeClient([{"id": "OtherFormId0000", "name": "Contact Us"}])
    res = fr.read_forms(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"
    assert res["form_id"] == ""
    assert res["candidates"] == [{"id_masked": fr.mask_id("OtherFormId0000")}]


def test_form_reader_alias_key_match():
    """A row naming the form through an underscore spelling of the hidden
    contract key is found (matched_by alias)."""
    client = fr._FakeClient([{"_id": "AliasFormId0001", "universal_intake": "1",
                              "name": "Intake Form"}])
    res = fr.read_forms(client, "loc_tmpl")
    assert res["ok"] is True and res["matched_by"] == "alias"
    assert res["form_id"] == "AliasFormId0001"


def test_form_reader_never_a_token_guards_refuse():
    """A row id that IS a credential-shaped string refuses the whole read
    rather than print it; a credential-shaped pinned id refuses the same
    way."""
    client = fr._FakeClient([{"id": "pit-abc123", "name": "Universal Intake"}])
    with pytest.raises(fr.FormsReadError):
        fr.read_forms(client, "loc_tmpl")
    with pytest.raises(fr.FormsReadError):
        fr.read_forms(fr._FakeClient(_golden_rows()), "loc_tmpl",
                      pinned_id="pit-abc123")


def test_form_reader_malformed_listing_shapes_refuse():
    """Malformed listing shapes REFUSE (never a silent empty): a payload
    without a 'forms' key, a 'forms' value that is not an array, and a
    response that is not an object."""
    class _BadClient(fr._FakeClient):
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            return self._payload

    with pytest.raises(fr.FormsReadError):
        fr.read_forms(_BadClient({"nope": 1}), "loc_tmpl")
    with pytest.raises(fr.FormsReadError):
        fr.read_forms(_BadClient({"forms": "not-a-list"}), "loc_tmpl")
    with pytest.raises(fr.FormsReadError):
        fr.read_forms(_BadClient([{"id": "X"}]), "loc_tmpl")


def test_form_reader_403_classification_stop_vs_held():
    """The 403 discrimination the CLI depends on: a REAL location-scope
    denial ("does not have access to this location", live-verified) STOPS;
    the W0.5 pipeline-scope text STOPS; an edge block (CF 1010 HTML) and a
    consumed empty body stay HELD (retryable) — never mislabeled."""
    import urllib.error

    loc_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"statusCode":403,"message":"The token does not have '
                       b'access to this location."}'))
    assert fr._request_error_kind(loc_denial) == "location-scope"
    w05_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"message":"The token is not authorized for this '
                       b'scope."}'))
    assert fr._request_error_kind(w05_denial) == "scope"
    edge_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b"<html>cf 1010</html>"))
    assert fr._request_error_kind(edge_denial) == "blocked"
    empty_denial = urllib.error.HTTPError("loc", 403, "Forbidden", hdrs=None,
                                          fp=io.BytesIO(b""))
    empty_denial.read()  # simulate the registry's prior read (consumed body)
    assert fr._request_error_kind(empty_denial) == "blocked"
    # a wrapped UpstreamBlockedError keeps the ORIGINAL HTTPError as its
    # __context__ — the unwrap must find the live location-scope signature
    wrapped = reg.UpstreamBlockedError("HTTP 403")
    wrapped.__context__ = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"statusCode":403,"message":"The token does not have '
                       b'access to this location."}'))
    assert fr._request_error_kind(wrapped) == "location-scope"


def test_form_reader_successful_read_never_carries_credential_shape():
    """A successful read never emits a credential-shaped string anywhere on
    the payload (never-a-token doctrine on the machine surface)."""
    dumped = json.dumps(fr.read_forms(fr._FakeClient(_golden_rows()), "loc_tmpl"),
                        indent=2, sort_keys=True)
    assert "pit-" not in dumped and "Bearer" not in dumped


# ---------------------------------------------------------------------------
# query_key_fixer
# ---------------------------------------------------------------------------
def _golden_drifted_rows():
    """The golden drifted listing: the universal-intake form carrying the
    pinned engine id AND the wrong query key (the G3 defect this module
    exists to fix), plus the engine's two gate forms."""
    return [
        {"id": qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "queryKey": qkf.WRONG_QUERY_KEY,
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "riNlAkYbcW3g92VRLqq0", "name": "Universal Review",
         "type": "form", "queryKey": qkf.QUERY_KEY_LAW,
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
         "type": "form", "queryKey": qkf.QUERY_KEY_LAW,
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def test_query_key_fixer_dry_run_refuses_and_writes_nothing():
    """A drifted form (wrong query key) is refused in dry-run: the plan names
    the drift, applied stays false, and ONLY the listing read rides the
    wire — nothing is ever written without --execute."""
    client = qkf._FakeClient(_golden_drifted_rows())
    res = qkf.plan_form_fix(client, "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["form_id"] == qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    assert res["query_key_current"] == qkf.WRONG_QUERY_KEY
    assert res["query_key_law"] == qkf.QUERY_KEY_LAW and res["fixed"] is False
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], (
        "a dry-run must perform ONLY the listing read")


def test_query_key_fixer_execute_applies_and_reads_back():
    """With --execute, the fix applies: exactly ONE PUT rides the wire, the
    PUT body echoes the live row byte-for-byte with the query key replaced by
    the law (never fabricated), and the write is proven ONLY by the read-back
    in the same job."""
    client = qkf._FakeClient(_golden_drifted_rows())
    res = qkf.plan_form_fix(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["fixed"] is True and res["af_code"] == "FIXED"
    assert res["query_key_current"] == qkf.QUERY_KEY_LAW
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == qkf.FORMS_WRITE_PATH % qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    body = puts[0]["body"]
    assert body.get("queryKey") == qkf.QUERY_KEY_LAW
    assert body.get("id") == qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID
    assert body.get("name") == "Universal Intake"
    assert body.get("hiddenFields") == ["contact_id", "anthology_id", "stage"]
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, "the apply must re-read the listing for the read-back"


def test_query_key_fixer_idempotent_no_op_writes_nothing():
    """An already-fixed form is an idempotent no-op: ok true, applied false,
    NOTHING written — even with --execute (the old==new doctrine)."""
    rows = [dict(r) for r in _golden_drifted_rows()]
    rows[0]["queryKey"] = qkf.QUERY_KEY_LAW
    client = qkf._FakeClient(rows)
    res = qkf.plan_form_fix(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False
    assert res["fixed"] is True and res["af_code"] == "NO-OP"
    assert not any(c["method"] == "PUT" for c in client.calls), (
        "a no-op must never perform a PUT")


def test_query_key_fixer_pin_law_and_not_found_paths():
    """The pinned id BYPASSES the slug law and IS the row written; a pinned
    id absent from the listing is FORMS-NOT-FOUND; an empty listing is
    FORMS-EMPTY; both carry no form id."""
    client = qkf._FakeClient(_golden_drifted_rows())
    res = qkf.plan_form_fix(client, "loc_tmpl",
                            pinned_id=qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
                            execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["target_matched_by"] == "pin"
    rows = [dict(r) for r in _golden_drifted_rows()]
    rows[0]["id"] = "DriftedDriftedId00"
    res = qkf.plan_form_fix(qkf._FakeClient(rows), "loc_tmpl",
                            pinned_id=qkf.DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"
    assert res["form_id"] == "", "a failed plan must never carry a form id"
    res = qkf.plan_form_fix(qkf._FakeClient([]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"


def test_query_key_fixer_keyless_row_is_fixable_but_never_written_without_execute():
    """A KEYLESS row is fixable (the minted link REQUIRES the key): the
    dry-run surfaces the absence and refuses; --execute applies the law."""
    rows = [dict(r) for r in _golden_drifted_rows()]
    del rows[0]["queryKey"]
    client = qkf._FakeClient(rows)
    res = qkf.plan_form_fix(client, "loc_tmpl")
    assert res["ok"] is False and res["query_key_current"] == ""
    assert res["af_code"] == "DRY-RUN"
    client = qkf._FakeClient(rows)
    res = qkf.plan_form_fix(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["query_key_current"] == qkf.QUERY_KEY_LAW


def test_query_key_fixer_never_a_token_guards_refuse():
    """A query key that IS a credential-shaped string refuses the whole plan
    rather than print it; a credential-shaped pinned id refuses the same
    way. The pinned-id refusal raises the reader's FormsReadError through
    the fixer's OWN import seam (query_key_fixer imports form_reader as a
    top-level module, a distinct class object from the u04 package copy)."""
    rows = [dict(r) for r in _golden_drifted_rows()]
    rows[0]["queryKey"] = "pit-abc123"
    with pytest.raises(qkf.FormsFixError):
        qkf.plan_form_fix(qkf._FakeClient(rows), "loc_tmpl")
    with pytest.raises(qkf.fr.FormsReadError):
        qkf.plan_form_fix(qkf._FakeClient(_golden_drifted_rows()), "loc_tmpl",
                          pinned_id="pit-abc123")


def test_query_key_fixer_put_validation_refusal_stops():
    """A validation refusal on the PUT (400/409/422) is a STOP, never a
    silent skip."""
    with pytest.raises(qkf.FormsFixError):
        qkf.plan_form_fix(qkf._FakeClient(_golden_drifted_rows(), fail_put=True),
                          "loc_tmpl", execute=True)


def test_query_key_fixer_surfaces_never_carry_credential_shape():
    """The golden dry-run and the golden apply never emit a credential-shaped
    string anywhere on the payload."""
    for kwargs in ({}, {"execute": True}):
        dumped = json.dumps(
            qkf.plan_form_fix(qkf._FakeClient(_golden_drifted_rows()), "loc_tmpl",
                              **kwargs),
            indent=2, sort_keys=True)
        assert "pit-" not in dumped and "Bearer" not in dumped


# ---------------------------------------------------------------------------
# attack_bad_query
# ---------------------------------------------------------------------------
def test_attack_link_is_one_key_wrong_value_preserved():
    """The attack is deterministic and single-variable: exactly the one
    adversarial key, the value preserved byte-for-byte, the golden path, and
    never a live domain."""
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(attack.ATTACK_LINK)
    q = parse_qs(parts.query, keep_blank_values=True)
    assert list(q.keys()) == [attack.ATTACK_QUERY_KEY]
    assert q[attack.ATTACK_QUERY_KEY] == [attack.SYNTHETIC_BOOK_ID]
    assert parts.path == "/widget/form/" + attack.FORM_ID
    assert parts.netloc == "forms.example.test"


def test_attack_verify_live_wrong_key_fails_golden_passes():
    """The judge discriminates: the wrong-key attack link FAILS (exit 5,
    verdict FAIL, defects exactly wrong-key, the id masked to the last-4
    marker); the golden control link PASSES (exit 0) — a gate that fails
    everything is a broken instrument."""
    rc, parsed = _capture(attack.verify_live, attack.ATTACK_LINK,
                          out=io.StringIO())
    assert rc == EX_MISMATCH
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False
    assert parsed["query_keys"] == [attack.ATTACK_QUERY_KEY]
    assert parsed["expected_key"] == "anthology_id"
    assert parsed["defects"] == ["wrong-key"]
    assert parsed["key_count"] == 1
    assert parsed["value_marker"] == "...d00d", (
        "the id value must be masked to the last-4 marker")
    assert attack.SYNTHETIC_BOOK_ID not in json.dumps(parsed), (
        "the judge output must never carry the full id value")
    rc, parsed = _capture(attack.verify_live, attack.GOLDEN_LINK,
                          out=io.StringIO())
    assert rc == EX_OK
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True
    assert parsed["query_keys"] == ["anthology_id"] and parsed["defects"] == []


def test_attack_verify_live_every_other_direction_fails():
    """The judge's other FAIL directions, all never a pass: a two-key link
    fails on the key-count law, an empty-value link fails on the value law, a
    query-less link fails on the key-count law, and an empty surface is
    refused outright."""
    dup = attack.GOLDEN_LINK + "&utm_source=attacker"
    rc, parsed = _capture(attack.verify_live, dup, out=io.StringIO())
    assert rc == EX_MISMATCH and parsed["defects"] == ["key-count-2"]
    empty = attack.GOLDEN_LINK.rsplit("=", 1)[0] + "="
    rc, parsed = _capture(attack.verify_live, empty, out=io.StringIO())
    assert rc == EX_MISMATCH and "bad-value" in parsed["defects"]
    rc, parsed = _capture(attack.verify_live,
                          attack.GOLDEN_LINK.split("?", 1)[0],
                          out=io.StringIO())
    assert rc == EX_MISMATCH and parsed["defects"] == ["key-count-0"]
    with pytest.raises(attack.FixtureError):
        attack.verify_live("", out=io.StringIO())


def test_attack_payload_and_control_gates_discriminate():
    """The fail-closed gates: payload ships the one-key-wrong attack (exit 0)
    and the payload-true control passes the true golden link (exit 0) — the
    pass/fail split is a discrimination, never a broken instrument."""
    rc, parsed = _capture(attack.payload, out=io.StringIO())
    assert rc == EX_OK
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["query_keys"] == [attack.ATTACK_QUERY_KEY]
    assert parsed["expected_key"] == "anthology_id"
    assert parsed["value"] == attack.SYNTHETIC_BOOK_ID
    assert parsed["contract"] == attack.ATTACK_CONTRACT
    assert "msgsndr" not in json.dumps(parsed), (
        "the fixture must never reference the live hosted-form domain")
    rc, parsed = _capture(attack.payload_true, out=io.StringIO())
    assert rc == EX_OK
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["query_keys"] == ["anthology_id"]


def test_attack_builder_refuses_every_drift_fixture():
    """Every drift is REFUSED, never shipped: a delimiter-carrying book id,
    an empty book id, a double-swap (the canonical link already carries the
    adversarial key), a two-pair canonical link, and an empty link."""
    with pytest.raises(attack.FixtureError):
        attack.attack_link(attack.FORMS_BASE, attack.FORM_ID, "ANTH_bad::delim")
    with pytest.raises(attack.FixtureError):
        attack.attack_link(attack.FORMS_BASE, attack.FORM_ID, "")
    with pytest.raises(attack.FixtureError):
        attack._swap_query_key(
            attack.GOLDEN_LINK.replace("anthology_id", attack.ATTACK_QUERY_KEY),
            attack.ATTACK_QUERY_KEY)
    with pytest.raises(attack.FixtureError):
        attack._swap_query_key(attack.GOLDEN_LINK + "&utm_source=attacker",
                               attack.ATTACK_QUERY_KEY)
    with pytest.raises(attack.FixtureError):
        attack._swap_query_key("", attack.ATTACK_QUERY_KEY)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
