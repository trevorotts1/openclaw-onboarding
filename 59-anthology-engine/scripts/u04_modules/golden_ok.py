#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/golden_ok.py  (U04 tooling)
# GOLDEN COMPLIANT-FORM FIXTURE — the canonical in-memory payload of the
# universal author-intake form in its ALREADY-COMPLIANT state: the live read
# the U04 verification family asserts against (a form the read returns and
# the required-flags law must certify clean -> PASS). The golden fixture:
# form already compliant -> PASS, by construction.
#
# WHERE THIS SITS: scripts/u04_modules/ — an importable module under the U04
# package (pure namespace container per the u02/u03/u04 package-init
# doctrine: imported BY NAME, side-effect-free at import). It is NOT a
# manifest row and NOT a checker: it ships the GOLDEN compliant surface the
# offline self-tests of the U04 verifier and its sibling checkers assert
# against, so every checker's happy path is judged against the SAME payload
# and a drift in the committed contract breaks THIS module's self-test first
# (fail-closed: an inconsistent contract is a refusal, never a blind pass).
#
# WHAT THIS OWNS:
#   1. GOLDEN_FORM — the deep-frozen canonical form record: the universal
#      author-intake form exactly as the public v2 forms read (form_reader.py
#      flatten) serves it — id, name, and the hidden-field contract
#      (contact_id / anthology_id / stage, asserted byte-exact from the
#      snapshot contract's forms.universal_hidden_fields). The record is a
#      MappingProxyType (types module) and its hiddenFields container is a
#      tuple, so NO caller can mutate the canonical payload through the
#      module's public surface — the self-test proves every mutation route
#      raises.
#   2. golden_form() / golden_form_payload() — the deep-copied payload
#      surfaces (the single-form record and the full listing object
#      {"forms": [...]} the live read returns) consumers mutate freely; the
#      canon never changes. Synthetic ids only (frm_golden_intake / masked
#      form ids) — a fixture id is never a real form id, exactly the
#      synthetic-id discipline of the u02 golden siblings.
#   3. payload — a FAIL-CLOSED compliant gate over a forms-listing payload:
#      the listing carries the golden intake form with every required flag
#      (the first_name / last_name / email law, contract-derived through
#      required_checker.required_fields()) present and non-empty, the
#      universal hidden-field contract byte-exact, and the required-flags
#      contract itself present (an empty law is never a clean check) ->
#      PASS exit 0. ANY deviation (absent form, absent/empty/whitespace-only/
#      non-string required flag, hidden-field drift, malformed read, or a
#      missing required-flags law) is a REFUSED exit 5 — never a blind pass,
#      never a fabricated success. The one JSON report object lands on
#      stdout; human notes go to stderr.
#
# DOCTRINE (house, inherited from the registry / the u02 golden siblings /
#   the u03 golden name fixture — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The one identifier it
#     carries (the golden form id) is a SYNTHETIC fixture id, and the form
#     id is masked on every surface exactly like a location id.
#   - Fail-closed: a malformed listing, an absent form, an absent hidden
#     contract, a drifted required-flags law all STOP or FAIL — never a
#     blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before
#     it ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is
#     the house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (form_reader.py)
#     rides reg.CafClient, which sends CAF_BROWSER_UA on every request — the
#     proven edge fix. The payload surface pipes a listing in on stdin and
#     reads NOTHING from the network; the live reader is form_reader.py.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE REQUIRED-FLAGS LAW IS NEVER HARDCODED HERE (SPEC M8): it comes from
# config/anthology-snapshot-contract.json forms.required -> required_fields
# (the form required-flag law), read through the sibling
# required_checker.resolve_required_fields() — the SAME source the U04
# checker certifies by. The OFFLINE self-test pins the contract value so a
# drift in the CONTRACT is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden form is internally consistent and the
#      compliant payload PASSES the gate; also self-test / plan OK
#   1  unexpected error (malformed/unreadable contract JSON)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a drifted contract, an absent form,
#      a missing/empty/whitespace-only/non-string required flag, hidden-field
#      drift, or a malformed listing (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# golden_fields.py / golden_pipeline.py / the u04 siblings: sys.path.insert
# to scripts/ then `import anthology_registry as reg` for its canonical
# constants, and the required-flags law is read through
# `u04_modules.required_checker` — never duplicated here.
# =============================================================================
"""golden_ok.py — golden ALREADY-COMPLIANT intake-form fixture for the U04
self-tests. Pure data + the fail-closed compliant gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u03 golden
# siblings): the registry owns the canonical constants and the fail-closed
# helper surfaces; the required-flags law is read through the sibling
# required_checker (the ONE law surface) — a fixture never re-implements
# what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u04_modules.required_checker as req  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
REQUIRED_SOURCE = "forms.required"

# The one fixed report contract. The required-flags law and the hidden-field
# contract are NEVER hardcoded here — they come from the committed snapshot
# contract (the single source of truth); a hardcoded list would drift and
# defeat the fixture's whole purpose.
FIXTURE_CONTRACT = "anthology-engine-golden-ok"

# The stable synthetic form id of the golden payload (the synthetic-id
# discipline of the u02 golden siblings: pipe_golden / fld_golden_<n> — a
# fixture id is never a real form id). The real pinned fleet id lives in
# anthology_book.py DEFAULT_UNIVERSAL_INTAKE_FORM_ID and is masked on every
# surface; THIS golden id is the fixture's own stable marker.
GOLDEN_FORM_ID = "frm_golden_intake"

# The one form this fixture exists for — the same slug law form_reader.py
# finds by and forms_check.py asserts: the universal author-intake form.
GOLDEN_FORM_SLUG = "universal-intake"
GOLDEN_FORM_NAME = "Universal Author Intake"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the snapshot
    contract is inconsistent with the golden compliant state, so NO fixture
    is shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_forms(contract: dict) -> dict:
    forms = contract.get("forms")
    if not isinstance(forms, dict):
        raise FixtureError(
            "anthology-snapshot-contract.json has no forms section — the "
            "golden compliant payload has nothing to derive from; refusing "
            "a blind fixture (never fabricated).")
    return forms


def _contract_universal_hidden(forms: dict) -> list:
    hidden = forms.get("universal_hidden_fields")
    if not isinstance(hidden, list) or not hidden:
        raise FixtureError(
            "contract forms.universal_hidden_fields is missing or empty — "
            "the hidden-field law has no contract source; refusing to ship "
            "a golden payload.")
    if not all(isinstance(h, str) and h for h in hidden):
        raise FixtureError(
            "contract forms.universal_hidden_fields carries non-string "
            "entries — refusing to derive a golden payload from a malformed "
            "contract.")
    return list(hidden)


def _contract_required_role(forms: dict) -> dict:
    for row in list(forms.get("required") or []):
        if isinstance(row, dict) and row.get("role") == "universal-author-intake":
            return row
    raise FixtureError(
        "contract forms.required carries no universal-author-intake row — "
        "the intake required-flags law has no contract source; refusing to "
        "ship a golden payload.")


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, byte-equal to the contract.
# ---------------------------------------------------------------------------
def golden_form(contract: dict) -> dict:
    """Derive the golden intake-form record from the committed snapshot
    contract.

    Each field is EXACTLY what a live public v2 forms read of a fully
    compliant location returns (form_reader.py flatten): id, name, and the
    universal hidden-field contract from the contract's
    forms.universal_hidden_fields, asserted byte-exact. The record carries
    the SAME shape the sibling reader's flattened rows carry so the live
    surface and the offline fixture surface share ONE shape. Raises
    FixtureError on ANY contract drift — a wrong fixture is never shipped.

    The returned dict is a deep copy; mutating it never touches the internal
    canonical payload (which itself stores hiddenFields in a tuple)."""
    forms = _contract_forms(contract)
    hidden = _contract_universal_hidden(forms)
    if tuple(hidden) != ("contact_id", "anthology_id", "stage"):
        raise FixtureError(
            "contract forms.universal_hidden_fields drifted: %r != "
            "[contact_id, anthology_id, stage] — refusing to ship a golden "
            "payload." % (hidden,))
    _contract_required_role(forms)  # the required-flags law must exist
    return copy.deepcopy({
        "id": GOLDEN_FORM_ID,
        "name": GOLDEN_FORM_NAME,
        "slug": GOLDEN_FORM_SLUG,
        "hiddenFields": hidden,
    })


def golden_form_payload(contract: dict) -> dict:
    """The full listing object the public v2 forms read serves for the golden
    state: {"forms": [golden_form]} — exactly the shape form_reader.py
    flattens from the live GET (a listing row; the reader normalizes a bare
    top-level array to this container), so the live surface and the offline
    fixture surface share ONE shape. A deep copy; callers may mutate it."""
    return {"forms": [golden_form(contract)]}


def golden_compliant_payload(contract: dict) -> dict:
    """The golden ALREADY-COMPLIANT payload: the intake form row plus the
    required participant fields with non-empty values, exactly as the
    required-flags law demands (first_name / last_name / email from the
    contract's forms.required.required_fields, never hardcoded). This is the
    payload the gate must certify clean -> PASS, by construction. The
    fixture values are deliberate: values, not tokens; every identifier is
    synthetic; nothing on this surface could ever be a credential. A deep
    copy; callers may mutate it."""
    return {
        "forms": [golden_form(contract)],
        "participant": {
            "first_name": "Golden",
            "last_name": "Author",
            "email": "golden.author@example.com",
        },
    }


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The form
# record is a MappingProxyType and the hiddenFields container is a tuple, so
# NO caller can mutate the canonical payload through the module's public
# surface — the self-test proves it. Consumers that need a mutable payload
# call golden_form() / golden_form_payload() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    form = golden_form(contract)
    return (
        MappingProxyType({
            "id": form["id"],
            "name": form["name"],
            "slug": form["slug"],
            "hiddenFields": tuple(form["hiddenFields"]),
        }),
    )


# The canonical golden form record: 1 intake-form row, deep-frozen (a
# mappingproxy record with tuple-of-strings hiddenFields — immutable through
# every route). The record carries the SAME shape the sibling reader's
# flattened rows carry.
GOLDEN_FORM = _build_golden()[0]

# The canonical golden required-flags law, read ONCE through the sibling
# required_checker at import (the lazy fail-closed contract read the checker
# performs) — the same law the gate certifies by. An empty law is a refusal,
# never a clean check.
GOLDEN_REQUIRED_FIELDS = req.resolve_required_fields()


# ---------------------------------------------------------------------------
# Fail-closed compliant gate — the offline surface the U04 verifier and the
# sibling checkers ride on. A drifted contract or a drifted listing is
# REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _mask_form_id(fid: str) -> str:
    """Non-reversible form-id marker for operator surfaces (the same masking
    discipline the sibling reader applies to form ids)."""
    return reg._mask_location(fid) if hasattr(reg, "_mask_location") else (
        "%s...%s" % (fid[:4], fid[-4:]) if len(fid) > 8 else "****")


def _required_present(payload: dict, required: list) -> tuple:
    """Apply the required-flags law to the participant surface. Returns
    (missing, detail) — missing is [] exactly when every required flag is
    present with a non-empty string value (never whitespace, never a number,
    never None — the multi-line text-input law). The report NEVER echoes any
    payload value — only the field names and the presence verdicts."""
    participant = payload.get("participant")
    if not isinstance(participant, dict):
        return list(required), "participant surface is not an object — the required flags cannot be verified"
    missing = []
    for field in required:
        value = participant.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing, ""


def _judge_payload(payload, hidden: list, required: list, *, out) -> int:
    """The fail-closed compliant gate. Returns the exit code: 0 PASS, 5
    REFUSED (mismatch family). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    detail = ""
    ok = False
    if not isinstance(payload, dict):
        detail = "the payload is not an object — malformed read, never a pass (fail-closed)"
    elif not isinstance(payload.get("forms"), list) or not payload["forms"]:
        detail = ("AF-AE-FORM-MISSING: the listing carries no form rows — "
                  "the universal intake form is absent (found: none). "
                  "Never a blind pass.")
    else:
        form = next((f for f in payload["forms"]
                     if isinstance(f, dict) and f.get("id") == GOLDEN_FORM_ID), None)
        if form is None:
            detail = ("AF-AE-FORM-MISSING: the golden intake form %s is ABSENT "
                      "from the listing — renamed, removed, or near-miss. "
                      "Never a blind pass."
                      % _mask_form_id(GOLDEN_FORM_ID))
        else:
            live_hidden = form.get("hiddenFields")
            if not isinstance(live_hidden, list):
                detail = "the golden form row carries no hiddenFields list — hidden-field law unverifiable (fail-closed)"
            elif tuple(live_hidden) != tuple(hidden):
                detail = ("hidden-field drift: expected %s; live %s — a strict "
                          "subset is a FAIL, never a pass"
                          % (hidden, live_hidden))
            else:
                missing, req_detail = _required_present(payload, required)
                if req_detail:
                    detail = req_detail
                elif missing:
                    detail = ("AF-AE-REQUIRED-FLAG-MISSING: required flags "
                              "absent/empty/whitespace-only/non-string: %s — "
                              "never a fabricated value"
                              % ", ".join(missing))
                else:
                    ok = True
                    detail = ("universal intake form present BYTE-EXACT with "
                              "the universal hidden-field contract and every "
                              "required flag non-empty (%s) — the form is "
                              "ALREADY COMPLIANT" % ", ".join(required))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "form_id": GOLDEN_FORM_ID,
            "name": GOLDEN_FORM_NAME,
            "hidden_fields": hidden,
            "required": required,
        },
        "found": [form.get("name") or form.get("id")
                  for form in (payload.get("forms") or [])
                  if isinstance(form, dict)] if isinstance(payload, dict) else None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-ok] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(compliance: dict, contract: dict, *, out=None) -> int:
    """Judge a candidate compliant-state payload against the golden contract.

    READ-ONLY: derives the golden compliant state from the committed snapshot
    contract and asserts the byte-level invariant — the universal intake form
    present with the universal hidden-field contract and every required flag
    present and non-empty -> PASS exit 0. Any deviation is a FAIL-CLOSED exit
    5, never a blind pass. Emits the ONE JSON report object on stdout; human
    notes go to out (stderr)."""
    out = out or sys.stderr
    try:
        hidden = _contract_universal_hidden(_contract_forms(contract))
        required = list(req.resolve_required_fields())
    except FixtureError as exc:
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": None,
            "found": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        out.write("[golden-ok] payload REFUSED: %s\n" % exc)
        return EX_MISMATCH
    if not required:
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": None,
            "found": None,
            "detail": ("the required-flags law is EMPTY (forms.required "
                       "carries no required_fields) — a payload with no "
                       "contract cannot be certified clean; refusing (fail-closed)"),
        }, indent=2, sort_keys=True))
        out.write("[golden-ok] payload REFUSED: required-flags law is empty\n")
        return EX_MISMATCH
    return _judge_payload(compliance, hidden, required, out=out)


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
        sys.stderr.write("[golden-ok] SELF-TEST FAILED "
                         "(AF-AE-GOLDENOK-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    forms = _contract_forms(contract)
    hidden = _contract_universal_hidden(forms)
    required = list(GOLDEN_REQUIRED_FIELDS)

    # ---- contract coherence: the committed contract is the single source --
    assert tuple(hidden) == ("contact_id", "anthology_id", "stage"), \
        "contract universal hidden fields drifted"
    _contract_required_role(forms)  # the required-flags law must exist
    assert required, "the required-flags law must never be empty"

    # ---- the canonical fixture: byte-exact, deep-frozen --------------------
    assert isinstance(GOLDEN_FORM, MappingProxyType), \
        "GOLDEN_FORM must be mappingproxy-frozen"
    assert GOLDEN_FORM["id"] == GOLDEN_FORM_ID
    assert GOLDEN_FORM["name"] == GOLDEN_FORM_NAME
    assert GOLDEN_FORM["slug"] == GOLDEN_FORM_SLUG
    assert isinstance(GOLDEN_FORM["hiddenFields"], tuple), \
        "golden hiddenFields container must be a tuple (immutable canonical surface)"
    assert tuple(GOLDEN_FORM["hiddenFields"]) == tuple(hidden), \
        "golden hidden fields must equal the contract's universal_hidden_fields"

    # ---- the payload surfaces carry the same shape the live read serves ----
    listing = golden_form_payload(contract)
    assert isinstance(listing, dict) and isinstance(listing.get("forms"), list) \
        and len(listing["forms"]) == 1
    assert listing["forms"][0]["id"] == GOLDEN_FORM_ID
    assert listing["forms"][0]["hiddenFields"] == list(hidden)
    compliant = golden_compliant_payload(contract)
    assert isinstance(compliant.get("participant"), dict)
    for field in required:
        value = compliant["participant"].get(field)
        assert isinstance(value, str) and value.strip(), \
            "the golden compliant payload must carry %r non-empty" % field

    # ---- the canonical fixture can never be mutated through the surface -----
    def _fp():
        return tuple(
            sorted((k, (tuple(v) if isinstance(v, tuple) else v))
                   for k, v in item.items())
            for item in (GOLDEN_FORM,))

    before = _fp()

    def _try_rebind():        # attribute assignment on a mappingproxy -> TypeError
        GOLDEN_FORM["id"] = "frm_MUTATED"  # noqa: B034 -- deliberately attempted

    def _try_mutate_hidden():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_FORM["hiddenFields"][0] = "contact_id_MUTATED"  # noqa: B034

    def _try_swap_hidden():   # subscript assignment on a tuple -> TypeError
        GOLDEN_FORM["hiddenFields"] = ("contact_id", "stage")  # noqa: B034

    for attempt in (_try_rebind, _try_mutate_hidden, _try_swap_hidden):
        try:
            attempt()
            raise AssertionError("the canonical fixture must be immutable")
        except TypeError:
            pass
    assert _fp() == before, "the canonical fixture changed during the self-test"
    # golden_form() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_form(contract)
    copy_["name"] = "Universal Intake MUTATED"
    copy_["hiddenFields"] = ["contact_id", "stage"]
    assert GOLDEN_FORM["name"] == GOLDEN_FORM_NAME and \
        tuple(GOLDEN_FORM["hiddenFields"]) == tuple(hidden), \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. missing forms section -> FixtureError
    try:
        golden_form({"$note": "no forms section"})
        raise AssertionError("a missing forms section was NOT refused")
    except FixtureError:
        pass
    # 2. empty hidden fields -> FixtureError
    tampered = copy.deepcopy(contract)
    tampered["forms"]["universal_hidden_fields"] = []
    try:
        golden_form(tampered)
        raise AssertionError("empty hidden fields were NOT refused")
    except FixtureError:
        pass
    # 3. drifted hidden fields -> FixtureError
    tampered = copy.deepcopy(contract)
    tampered["forms"]["universal_hidden_fields"] = ["contact_id", "stage"]
    try:
        golden_form(tampered)
        raise AssertionError("drifted hidden fields were NOT refused")
    except FixtureError:
        pass
    # 4. missing intake role row -> FixtureError
    tampered = copy.deepcopy(contract)
    tampered["forms"]["required"] = []
    try:
        golden_form(tampered)
        raise AssertionError("a missing intake role row was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(golden_compliant_payload(contract), contract, out=io.StringIO())
    assert rc == EX_OK, "payload on the true compliant state must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["required"] == required
    # 5. form absent -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        rc2 = payload({"forms": []}, contract, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "absent form must exit 5, got %s" % rc2
    # 6. required flag missing -> REFUSED exit 5
    bad = golden_compliant_payload(contract)
    bad["participant"]["email"] = ""
    with contextlib.redirect_stdout(io.StringIO()):
        rc3 = payload(bad, contract, out=io.StringIO())
    assert rc3 == EX_MISMATCH, "missing required flag must exit 5, got %s" % rc3
    # 7. whitespace-only value -> REFUSED exit 5 (never a padded "present")
    bad = golden_compliant_payload(contract)
    bad["participant"]["first_name"] = "   "
    with contextlib.redirect_stdout(io.StringIO()):
        rc4 = payload(bad, contract, out=io.StringIO())
    assert rc4 == EX_MISMATCH, "whitespace-only value must exit 5, got %s" % rc4
    # 8. hidden-field drift on the live row -> REFUSED exit 5
    bad = golden_compliant_payload(contract)
    bad["forms"][0]["hiddenFields"] = ["contact_id", "stage"]
    with contextlib.redirect_stdout(io.StringIO()):
        rc5 = payload(bad, contract, out=io.StringIO())
    assert rc5 == EX_MISMATCH, "hidden-field drift must exit 5, got %s" % rc5
    # 9. malformed listing -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        rc6 = payload({"no_forms_here": True}, contract, out=io.StringIO())
    assert rc6 == EX_MISMATCH, "malformed payload must exit 5, got %s" % rc6
    # 10. empty required-flags law -> REFUSED exit 5 (no contract source).
    #     The sibling resolves the law as contract-first, intake-router
    #     fallback (resolve_required_fields): the empty-law case is BOTH
    #     sources empty — a contract with no intake-role required_fields AND
    #     no router scalars to fall back on. A payload with no law can never
    #     be certified clean. The sibling's fallback reader is patched and
    #     restored (the same patch-and-restore seam the golden siblings use
    #     for their coherence gates).
    tampered = copy.deepcopy(contract)
    tampered["forms"]["required"] = [{"role": "outline-approval",
                                      "required": False}]
    _saved_scalars = getattr(req, "_intake_router_required_scalars", None)
    try:
        if _saved_scalars is not None:
            req._intake_router_required_scalars = lambda: []
        with contextlib.redirect_stdout(io.StringIO()):
            rc7 = payload(golden_compliant_payload(contract), tampered,
                          out=io.StringIO())
    finally:
        if _saved_scalars is not None:
            req._intake_router_required_scalars = _saved_scalars
    assert rc7 == EX_MISMATCH, "empty required-flags law must exit 5, got %s" % rc7

    # ---- never-print: no credential-shaped string on any surface -----------
    all_text = buf.getvalue() + json.dumps(parsed)
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_ok self-test: OK (golden compliant intake-form fixture "
              "pinned byte-exact to the snapshot contract: hidden fields %s; "
              "required-flags law %s; canonical deep-frozen immutability + "
              "deep-copy surface; attack fixtures refused (missing-forms-"
              "section / empty-hidden / drifted-hidden / missing-intake-role / "
              "absent-form / missing-required / whitespace-only / hidden-"
              "drift / malformed / empty-law); payload gate exits 0 on the "
              "golden compliant state, 5 on every drift; never-print)\n"
              % (list(hidden), required))

    dev.write("[golden-ok] golden fixture: form already compliant -> PASS "
              "(by construction)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_ok.py",
        description="Golden compliant-form payload fixture for the U04 "
                    "self-tests (Skill 59): derive the canonical "
                    "already-compliant intake-form payload byte-exact from "
                    "config/anthology-snapshot-contract.json, fail-closed. "
                    "One JSON object on stdout; never prints a secret.")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json (the "
                         "single source of truth)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

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
        if args.cmd == "self-test":
            return self_test()
        contract = json.loads(Path(args.contract).expanduser().read_text(encoding="utf-8"))
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden compliant
            # state, straight from the contract — never a hardcoded list.
            form = golden_form(contract)
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "form": {
                    "id": form["id"],
                    "name": form["name"],
                    "hidden_fields": list(form["hiddenFields"]),
                },
                "required_fields": list(req.resolve_required_fields()),
                "source": REQUIRED_SOURCE,
                "dry_run": True,
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the compliant-state payload arrives on stdin, read from NO
        # network (the live READER is form_reader.py / required_checker.py,
        # which ride reg.CafClient and its CAF_BROWSER_UA — this fixture
        # never touches the wire).
        try:
            compliance = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-ok] the payload on stdin is not valid "
                             "JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(compliance, contract)
    except FixtureError as exc:
        sys.stderr.write("[golden-ok] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[golden-ok] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-ok] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
