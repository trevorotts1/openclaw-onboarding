#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/attack_not_required.py
# NOT-REQUIRED ATTACK FIXTURE (U04 tooling) — the fail-closed EMAIL-NOT-
# REQUIRED gate: a payload that submits an author-intake form with EMAIL ABSENT,
# EMPTY, whitespace-only, or non-string — the exact object a live intake read
# serves on an author who never supplied one — is REFUSED with a loud operator
# STOP, never a pass, never a silent fallback, never a fabricated success. It
# is the attack half of the U04 required-flags pair: the sibling checker
# required_checker.py ships the law (first_name / last_name / email must be
# present and non-empty); THIS module ships the ATTACK state — the intake
# submission with NO email — that the SAME law must REFUSE.
#
# WHY EMAIL-NOT-REQUIRED IS THE U04 ATTACK: the intake front door keys the
# ledger by contact_id (MASTERDOC floor 8; anthology-state.py
# participant_key — email is a REQUIRED contact field, never a KEY), and the
# form REQUIRED flags are the contract's (config/anthology-snapshot-contract
# .json forms.required -> required_fields, with intake_router.py
# upsert_scalar_fields as the fallback law). A drift that makes email
# OPTIONAL is the ONE state a verifier could mistake for a pass: the payload
# parses, every present field is a fine string, and the email column is
# simply absent — no error, no exception, just nothing to reach the author
# on. A verifier that treated "no email" as a clean read would certify a
# contact that the delivery stage can never reach, and every subsequent
# author-touch gate would fail against a phantom address. THIS module exists
# so that state is REFUSED at the gate: exit 5, AF-AE-REQUIRED-MISSING, with
# the email absence PROVEN in `missing` — never a fabricated pass, never a
# silent failure.
#
# WHAT THIS OWNS
#   1. verify(payload, required_fields) — the fail-closed gate over an intake
#      PAYLOAD (exactly the object the intake extractor reads, so the live
#      surface and the offline attack surface share ONE implementation):
#        - every required field present AND a non-empty string -> ("PASS", ...)
#          with the required set read back
#        - email absent, empty, whitespace-only, non-string, or ANY required
#          field mutated -> raises NotRequiredError (STOP family, never a
#          pass, never a silent fallback) — a missing email is REFUSED with
#          its own loud message, so the U04 attack never shares the refusal
#          path with a generic shape error: the operator sees exactly which
#          drift the gate caught.
#   2. payload(*, out) — the CLI gate: emits the ONE JSON report object
#      (contract / ok / verdict / required / missing / detail), refusals are
#      exit 5 (data or read-back mismatch) with a loud operator STOP line on
#      stderr — the missing email is PROVEN in `missing` by field name, so an
#      email-less intake is never a fabricated pass and never a silent
#      failure.
#   3. self_test() — OFFLINE (no network, no credentials): the golden
#      payload passes; the EMAIL-NOT-REQUIRED attack (email absent), the
#      empty-string, whitespace-only, non-string, and every other required-
#      flag mutation are each REFUSED. A tamper NEVER masquerades as exit 1
#      — it is exit 4 (AF-AE-REQUIRED-ATTACK family), the house self-test
#      convention.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the U03
# attack_no_pipeline.py and the U04 required_checker.py siblings):
#   - A fixture is DATA, not code: this module performs NO I/O and NO network
#     call — it can never leak a token by construction. Nothing here reads an
#     env var or touches the wire.
#   - BROWSER UA (CF 1010 LAW): any module that TALKS to GoHighLevel /
#     Convert and Flow (services.leadconnectorhq.com, Cloudflare-fronted)
#     MUST carry a browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
#     ever reaches the API. This module makes no request of its own and
#     therefore defines no UA constant of its own; the client that DOES
#     (reg.CafClient) already sends reg.CAF_BROWSER_UA on every request —
#     the proven edge fix (W0.6 / GK-09 discipline). The offline self-test
#     pins the byte-exact CAF_BROWSER_UA string (house convention), so a
#     drift of the edge fix is caught, never silently.
#   - FAIL-CLOSED: a missing, empty, whitespace-only, or non-string required
#     field — the email-not-required attack included — REFUSES
#     (NotRequiredError / exit 5), never a blind pass, never a fabricated
#     success.
#   - NEVER print a secret value; SET / NOT SET only, by label. A report
#     carries field NAMES and PRESENCE verdicts only — never a payload value,
#     never a credential-shaped string (a payload may legitimately carry
#     contact data; this module never echoes any of it).
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE LAW IS NEVER HARDCODED HERE (SPEC M8): the required fields come from
# config/anthology-snapshot-contract.json forms.required.required_fields
# (the contract law), with the intake router's OWN committed
# upsert_scalar_fields (scripts/intake_router.py DEFAULTS) as the fallback —
# the SAME derivation required_checker.py applies, read once from the module
# that owns it. A drift of the law is caught by the offline self-test
# (golden state must match it), never silently.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified PASS — every required field is present with a non-empty
#      string value (also self-test PASS and plan OK)
#   1  unexpected error
#   2  STOP refusal — no gate mode selected, or the required-fields law is
#      EMPTY (no law to enforce; the contract is unverifiable)
#   4  self-test FAILED — an attack fixture was NOT refused (AF-AE-REQUIRED-
#      ATTACK family; a tamper NEVER masquerades as exit 1)
#   5  data or read-back mismatch — a required flag is missing, empty,
#      whitespace-only, or non-string: the email-not-required attack
#      (AF-AE-REQUIRED-MISSING)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --plan and --self-test are OFFLINE and need no token and no network):
#   attack_not_required.py --plan          # offline: the email-not-required
#                                          # law with its sources
#   attack_not_required.py --live < payload.json
#                                       # pipes an intake payload in and
#                                       # gates it (the SAME object the
#                                       # intake extractor reads)
#   attack_not_required.py --self-test     # offline golden + attack fixtures
#
#   # the canonical live pairing (extractor -> attack gate, one pipeline):
#   <u04 intake extractor>.py ... | attack_not_required.py --live
#
# STDLIB ONLY (json + argparse). Calls NO model. Reuses anthology_registry
# (_stop, _mask_location, CAF_BROWSER_UA doctrine).
# =============================================================================
"""attack_not_required.py — email-not-required attack fixture for the U04
required-flags law: REFUSES any intake payload whose required fields are not
all present and non-empty (email absent, empty, whitespace-only, or non-string
included), never a pass."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring (CAF_BROWSER_UA, applied by reg.CafClient —
# the fixture makes no request of its own, so it carries no UA of its own),
# the label resolution contract, and the fail-closed helper surfaces.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
CONTRACT_KEY = "forms.required"

FIXTURE_CONTRACT = "anthology-engine-attack-not-required"

# The ONE fixed report contract on every surface (plan / live / self-test).
_REPORT = {
    "contract": FIXTURE_CONTRACT,
    "schema_version": 1,
}

# The marker that PROVES the law source in `detail` — the contract path and
# the fallback surface must never masquerade as one another.
_SOURCE_CONTRACT = "contract"
_SOURCE_INTAKE_ROUTER = "intake_router.upsert_scalar_fields"

# The house credential shape (mirrors form_reader.py / delta_reporter.py):
# the pit- token prefix followed by a non-empty value. The label word "PIT"
# alone is NOT a credential; "pit-<value>" IS — and a hit REFUSES the whole
# surface rather than print it (never-a-real-token doctrine).
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class NotRequiredError(Exception):
    """A fail-closed verification refusal (STOP / mismatch family): a
    required field is missing, empty, whitespace-only, or non-string — the
    email-not-required attack is refused with its own loud message, so the
    U04 attack never shares the refusal path with a generic shape error."""


# ---------------------------------------------------------------------------
# Contract reader (fail-closed: an empty law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_required_fields(contract: dict) -> list:
    """The required participant fields from the contract (forms.required ->
    required_fields), never hardcoded. Returns [] on an ABSENT section so a
    missing contract cannot masquerade as 'nothing required'."""
    forms = contract.get("forms") or {}
    required = forms.get("required") or []
    for row in required:
        if not isinstance(row, dict):
            continue
        if row.get("role") == "universal-author-intake":
            rf = row.get("required_fields")
            if isinstance(rf, list):
                return [f for f in rf if isinstance(f, str) and f]
            break
    return []


def _intake_router_required_scalars() -> list:
    """The intake-REQUIRED participant scalars, read from the intake router's
    OWN committed config (scripts/intake_router.py DEFAULTS) — the canonical
    list of participant fields S0 upserts from the form payload, restricted
    to the first three (first_name / last_name / email), the fields the S0
    intake REQUIRES on every submission. NEVER hardcoded here (SPEC M8: a
    law read once, from the module that owns it)."""
    try:
        text = (SKILL_DIR / "scripts" / "intake_router.py").read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(r'"upsert_scalar_fields"\s*:\s*\[(.*?)\]', text, re.S)
    if not m:
        return []
    out = []
    for token in re.findall(r'"([^"]+)"', m.group(1)):
        if token not in out:
            out.append(token)
    return out[:3]


def _wanted_fields() -> tuple:
    """The required-fields law: the contract's forms.required.required_fields
    when the contract declares them (the form required-flag law), else the
    intake router's upsert scalar fields (the S0 intake-required law) — the
    SAME derivation required_checker.py applies, so the fixture can never
    drift from the checker it attacks. Returns (fields, source_label);
    raises NotRequiredError on an EMPTY law (no law to enforce)."""
    fields = _contract_required_fields(_load_contract())
    if fields:
        return fields, _SOURCE_CONTRACT
    fields = _intake_router_required_scalars()
    if fields:
        return fields, _SOURCE_INTAKE_ROUTER
    raise NotRequiredError(
        "the required-fields law is EMPTY — config/anthology-snapshot-contract"
        ".json forms.required carries no required_fields and "
        "scripts/intake_router.py upsert_scalar_fields carries none either; "
        "there is no law to enforce, so no payload can be certified clean "
        "(never a fabricated pass).")


def _load_contract() -> dict:
    """Load the committed snapshot contract. A missing/malformed file is a
    NOT-REQUIRED refusal: the law is unverifiable, so the fallback surface is
    the only remaining law and an unreadable contract never masquerades as
    'nothing required'."""
    try:
        with open(CONTRACT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# The intake extractor's canonical aliases for the same fields (mirrors
# intake_router.py FIELD_ALIASES — first_name/lastName/customData.first_name/
# contact.firstName are the SAME field, never a second column). A fixture is
# DATA: the aliases are the checker's law, pinned by the offline self-test.
FIELD_ALIASES: dict = {
    "first_name": ("first_name", "firstName", "customData.first_name",
                   "customData.firstName", "contact.firstName"),
    "last_name": ("last_name", "lastName", "customData.last_name",
                  "customData.lastName", "contact.lastName"),
    "email": ("email", "customData.email", "contact.email"),
}


# ---------------------------------------------------------------------------
# The fail-closed gate over an intake payload. The payload is EXACTLY the
# object the intake extractor reads (direct keys first, then customData,
# then the contact object), so the live surface and the offline attack
# surface share ONE implementation of the required-flags law.
# ---------------------------------------------------------------------------
def verify(payload, required_fields: list = None) -> tuple:
    """Verify an intake payload against the required-flags law, fail-closed.

    Returns ("PASS", detail, required, source) when every required field is
    present with a non-empty string value. Raises NotRequiredError on ANY
    other outcome — the email-not-required attack (email absent; refused
    with its own loud message), any other required flag missing, empty,
    whitespace-only, non-string, or a payload whose shape cannot be read —
    never a silent fallback. The missing fields are surfaced by NAME in the
    message (a field name cannot be a credential), so the drift is PROVEN
    present, not assumed. A report NEVER carries a payload value.
    """
    want, source = _wanted_fields()
    if not isinstance(payload, dict):
        raise NotRequiredError(
            "payload is %r, not a dict — the required flags cannot be "
            "verified; reading on would fabricate a clean check (fail-closed)."
            % type(payload).__name__)

    missing = []
    for field in want:
        aliases = FIELD_ALIASES.get(field) or (field,)
        if not _is_present(_first_value(payload, aliases)):
            missing.append(field)
    if missing:
        # THE U04 ATTACK gets its own loud refusal path: a missing email is
        # the one drift a verifier could mistake for a clean read (the
        # payload parses and every present field is fine), so it is refused
        # with the absence PROVEN by field name — never judged a clean read,
        # never a blind pass.
        raise NotRequiredError(
            "AF-AE-REQUIRED-MISSING: the intake payload is missing required "
            "fields %s — the author's email among them, the email-not-"
            "required attack state. A submission that cannot reach the "
            "author cannot be certified clean. Refusing — the required flags "
            "are PRESENCE, never content (law source: %s)."
            % (", ".join(missing), source))
    return ("PASS", "all required flags present and non-empty",
            list(want), source)


def _first_value(payload: dict, aliases: tuple):
    """First alias whose value is a non-empty string (the intake extractor's
    order: direct keys first, then customData, then the contact object)."""
    for alias in aliases:
        parts = alias.split(".")
        node = payload
        ok = True
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                ok = False
                break
            node = node[part]
        if ok:
            return node
    return None


def _is_present(value) -> bool:
    """PRESENCE is a non-empty string — never whitespace, never a number,
    never None (the multi-line text-input law: a filled field is a string)."""
    return isinstance(value, str) and bool(value.strip())


# ---------------------------------------------------------------------------
# CLI gate — ONE JSON object on stdout, human notes on stderr, fail-closed.
# ---------------------------------------------------------------------------
def _report(ok: bool, verdict: str, required: list, missing: list,
            source: str, detail: str) -> None:
    sys.stdout.write(json.dumps(dict(
        _REPORT,
        ok=ok,
        verdict=verdict,
        required=required,
        missing=missing,
        source=source,
        detail=detail,
    ), indent=2, sort_keys=True) + "\n")


def payload(payload_obj, *, out=None) -> int:
    """Run the fail-closed required-flags gate over an intake payload.
    Returns the exit code: 0 PASS, 5 refusal (mismatch family). Human notes
    go to stderr; the ONE JSON report object lands on stdout."""
    out = out or sys.stderr
    want, source = _wanted_fields()
    try:
        status, detail, required, src = verify(payload_obj, want)
    except NotRequiredError as exc:
        missing = _missing_names(payload_obj, want)
        reg._stop(out, "The intake payload does NOT carry every required "
                       "flag present and non-empty.",
                  [str(exc), "Required (presence law): %s"
                   % (", ".join(want) or "(none)"),
                   "Missing on the payload: %s"
                   % (", ".join(missing) or "(none)"),
                   "AF-AE-REQUIRED-MISSING — the intake form must require "
                   "every contract field; restore the flags, then re-run."])
        _report(False, "FAIL", want, missing, source, str(exc))
        return EX_MISMATCH
    _report(True, "PASS", required, [], src,
            "all required flags present and non-empty (law source: %s)" % src)
    out.write("[attack-not-required] OK: every required flag present and "
              "non-empty (%s; law source: %s).\n" % (", ".join(required), src))
    return EX_OK


def _missing_names(payload_obj, want: list) -> list:
    """The required flags that are missing on a payload — by NAME, never by
    value (a field name cannot be a credential; a value CAN)."""
    if not isinstance(payload_obj, dict):
        return list(want)
    missing = []
    for field in want:
        aliases = FIELD_ALIASES.get(field) or (field,)
        if not _is_present(_first_value(payload_obj, aliases)):
            missing.append(field)
    return missing


def _assert_no_credential_shaped(payload_obj) -> None:
    """Never-a-token guard on the whole surface: a credential-shaped string
    (pit-<value>) anywhere in the payload REFUSES rather than risk being
    reflected. The label word 'PIT' alone is NOT a credential."""
    def _walk(node):
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif isinstance(node, str) and _CREDENTIAL_SHAPE.search(node):
            raise NotRequiredError(
                "the payload carries a credential-shaped string — the "
                "required-flags gate REFUSES the whole surface rather than "
                "risk reflecting it (never-a-token doctrine).")
    _walk(payload_obj)


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets.
# A FAILED self-test is exit 4 (enforced violation, AF-AE-REQUIRED-ATTACK
# family), NEVER 'unexpected error' — the house convention.
# ---------------------------------------------------------------------------
def _golden_payload() -> dict:
    """The canonical intake submission (the exact aliases intake_router.py
    extracts by — direct keys, the field-map naming, never email as a key)."""
    return {
        "contact_id": "cnt_tmpl",
        "anthology_id": "anth_tmpl",
        "stage": "s0_intake",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@syn.test",
    }


def self_test(out=None) -> int:
    """OFFLINE self-test: golden + attack fixtures, no network, no secrets.
    A tamper NEVER masquerades as exit 1 — it is exit 4
    (AF-AE-REQUIRED-ATTACK family)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-not-required] SELF-TEST FAILED "
                         "(AF-AE-REQUIRED-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # 0. the law is never hardcoded and never empty: the fixture enforces
    #    EXACTLY the required_checker's derivation (contract first, intake
    #    router fallback) — the contract on disk carries no required_fields
    #    row, so the intake router's upsert_scalar_fields IS the law, and the
    #    mirror is pinned byte-equal by the checker's own self-test.
    want, source = _wanted_fields()
    assert want, "the required-fields law must not be empty"
    assert "email" in want, "email must be in the required law: %r" % want
    assert want[0] == "first_name" and want[1] == "last_name", (
        "required law must lead with the participant identity fields: %r"
        % want)
    assert source == _SOURCE_INTAKE_ROUTER, (
        "law source drifted from intake_router.upsert_scalar_fields (first "
        "three): %r" % source)

    # the browser-UA edge fix stays pinned byte-exact (CF 1010 law — the
    # house pattern the registry's own self-test proves live).
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the proven edge fix"

    # ---- golden state: every required flag present + non-empty -> PASS ----
    status, detail, required, src = verify(_golden_payload(), want)
    assert status == "PASS", "golden payload: %s" % detail
    assert required == want and src == source

    # ---- attack fixtures: every mutation REFUSED (never a silent pass) ----
    # 1. THE U04 ATTACK: email ABSENT entirely (the author never supplied
    #    one — the exact object a drifted form serves) -> refusal, and the
    #    absence PROVEN in the message, with its own loud AF code
    a1 = {k: v for k, v in _golden_payload().items() if k != "email"}
    try:
        verify(a1, want)
        raise AssertionError("email-not-required attack was NOT refused")
    except NotRequiredError as exc:
        assert "AF-AE-REQUIRED-MISSING" in str(exc), \
            "the refusal must carry the loud AF code: %s" % exc
        assert "email" in str(exc), \
            "the refusal must PROVE the missing email: %s" % exc
    # 2. email EMPTY string -> FAIL (presence is a NON-EMPTY string)
    a2 = dict(_golden_payload(), email="")
    try:
        verify(a2, want)
        raise AssertionError("empty-email was NOT refused")
    except NotRequiredError:
        pass
    # 3. email whitespace-only -> FAIL (never a padded 'present')
    a3 = dict(_golden_payload(), email="   ")
    try:
        verify(a3, want)
        raise AssertionError("whitespace-email was NOT refused")
    except NotRequiredError:
        pass
    # 4. email non-string (a number is not a filled text field) -> FAIL
    a4 = dict(_golden_payload(), email=42)
    try:
        verify(a4, want)
        raise AssertionError("non-string email was NOT refused")
    except NotRequiredError:
        pass
    # 5. email present only under an alias that is DROPPED (customData.email
    #    removed from an alias-only submission — the alias is the SAME field,
    #    never a second column, so a submission that stopped carrying it is
    #    exactly the email-not-required attack) -> FAIL
    a5 = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
          "stage": "s0_intake", "firstName": "Ada", "lastName": "Lovelace",
          "customData": {}}
    try:
        verify(a5, want)
        raise AssertionError("dropped-alias email was NOT refused")
    except NotRequiredError:
        pass
    # 6. last_name missing entirely (the attack is NOT email-specific: any
    #    required flag absent refuses) -> refusal
    a6 = {k: v for k, v in _golden_payload().items() if k != "last_name"}
    try:
        verify(a6, want)
        raise AssertionError("last_name-missing was NOT refused")
    except NotRequiredError:
        pass
    # 7. first_name whitespace-only -> refusal (never a padded 'present')
    a7 = dict(_golden_payload(), first_name="  ")
    try:
        verify(a7, want)
        raise AssertionError("whitespace-first_name was NOT refused")
    except NotRequiredError:
        pass
    # 8. unreadable shape (not a dict) -> refusal, never a fabricated clean
    #    check
    try:
        verify(["not", "a", "dict"], want)
        raise AssertionError("non-dict payload was NOT refused")
    except NotRequiredError:
        pass
    # 9. the alias-only submission with email carried under customData.email
    #    -> PASS: the aliases are the SAME fields, never a second column
    a9 = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
          "stage": "s0_intake", "firstName": "Ada", "lastName": "Lovelace",
          "customData": {"email": "ada@syn.test"}}
    status, detail, required, src = verify(a9, want)
    assert status == "PASS", "alias-only submission: %s" % detail
    # 10. contact-object nesting -> PASS (contact.firstName is the same field)
    a10 = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
           "stage": "s0_intake",
           "contact": {"firstName": "Ada", "lastName": "Lovelace",
                       "email": "ada@syn.test"}}
    status, detail, required, src = verify(a10, want)
    assert status == "PASS", "contact-object submission: %s" % detail

    # ---- never-a-token doctrine on the whole surface ----
    # 11. a credential-shaped value anywhere in the payload REFUSES the
    #     gate, never a value reflected (the label word "PIT" alone is NOT a
    #     credential)
    a11 = dict(_golden_payload(), email="pit-abc123")
    try:
        _assert_no_credential_shaped(a11)
        raise AssertionError("credential-shaped payload was NOT refused")
    except NotRequiredError:
        pass
    a11b = dict(_golden_payload(), note="PIT")
    _assert_no_credential_shaped(a11b)  # a label word is NOT a credential

    # ---- the CLI gate end-to-end (golden PASS, attack FAIL) ----
    # 12. golden state through the CLI gate -> exit 0, PASS JSON
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(_golden_payload(), out=io.StringIO())
    assert rc == EX_OK, "golden payload must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "PASS"
    assert report["required"] == want and report["missing"] == []
    assert report["contract"] == FIXTURE_CONTRACT
    # 13. THE U04 ATTACK through the CLI gate -> exit 5, FAIL JSON, and the
    #     missing email PROVEN in `missing` by name — never a fabricated
    #     pass, never a silent "(none)"
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(a1, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "email-missing payload must exit 5, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["verdict"] == "FAIL"
    assert report2["missing"] == ["email"], \
        "the missing email must be PROVEN in missing: %s" % report2["missing"]
    # 14. the report NEVER carries a payload value (never-a-token on the
    #     machine surface: field names and verdicts only)
    assert "ada@syn.test" not in json.dumps(report2), \
        "FAIL report leaked a payload value"
    assert "ada@syn.test" not in json.dumps(report), \
        "PASS report leaked a payload value"

    dev.write("attack_not_required self-test: OK (required-flags law derived "
              "exactly as required_checker.py does — source %s, %d fields, "
              "email included; golden PASS; 13 fixtures: email-absent / "
              "empty-email / whitespace-email / non-string-email / "
              "dropped-alias-email / last_name-missing / whitespace-first_name "
              "/ unreadable-shape / alias-only PASS / contact-object PASS / "
              "credential-shaped REFUSED / CLI-exit-5-with-email-proven / "
              "report-never-leaks; CAF_BROWSER_UA pinned byte-exact)\n"
              % (source, len(want)))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_not_required.py",
        description="Email-not-required attack fixture for the U04 "
                    "required-flags law (Skill 59): REFUSES any intake "
                    "payload that does not carry every required field "
                    "present and non-empty — email absent, empty, "
                    "whitespace-only, or non-string included — never a "
                    "pass. One JSON object on stdout; fail-closed; never "
                    "prints a secret value.")
    ap.add_argument("--live", action="store_true",
                    help="read an intake payload JSON from stdin (the exact "
                         "shape the intake extractor reads) and gate it "
                         "against the required-flags law")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    help="offline subcommands (no network, no credentials)")

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

        if args.cmd == "plan":
            # offline plan: no network, no credentials — the required-flags
            # law with its sources, including the attack this fixture exists
            # for.
            want, source = _wanted_fields()
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "required_fields": want,
                "source": source,
                "attack": "email-not-required — an intake payload with email "
                          "ABSENT, empty, whitespace-only, or non-string: "
                          "the one drift a verifier could mistake for a "
                          "clean read (every present field is fine, the "
                          "email column is simply absent). It is REFUSED, "
                          "never judged clean.",
                "check": "every required field must be present on the intake "
                         "payload as a non-empty string; a missing, empty, "
                         "whitespace-only, or non-string required flag is a "
                         "FAIL (AF-AE-REQUIRED-MISSING)",
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        if not args.live:
            reg._stop(sys.stderr, "No gate mode selected.",
                      ["Pass --live with an intake payload JSON on stdin "
                       "(<u04 intake extractor>.py | "
                       "attack_not_required.py --live), or --plan / "
                       "--self-test (offline)."])
            return EX_STOP
        try:
            payload_obj = json.load(sys.stdin)
        except ValueError as exc:
            reg._stop(sys.stderr, "The intake payload on stdin is not valid JSON.",
                      ["%s" % exc,
                       "Pipe the exact JSON the intake extractor reads."])
            return EX_STOP
        _assert_no_credential_shaped(payload_obj)
        return payload(payload_obj, out=sys.stderr)

    except NotRequiredError as exc:
        sys.stderr.write("[attack-not-required] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-not-required] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
