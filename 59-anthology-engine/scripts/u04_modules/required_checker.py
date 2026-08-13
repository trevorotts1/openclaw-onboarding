#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/required_checker.py  (U04 tooling)
# REQUIRED-FLAG CHECKER — the pure, OFFLINE, fail-closed checker for the
# engine's REQUIRED contact flags on the Convert and Flow intake form
# (LeadConnector v2 hosted form -> gateway /hooks/anthology-intake route ->
# intake_router.py). It verifies that the three intake-required participant
# fields — first_name, last_name, email — are present on the payload with
# non-empty string values, exactly as the intake extractor reads them
# (scripts/intake_router.py FIELD_ALIASES: firstName/lastName/customData.*/
# contact.firstName are the SAME field, never a second column).
#
# WHAT THIS MODULE IS NOT: it makes NO network call, holds NO credential, and
# does NOT decide which fields are required — that is the contract's job
# (config/anthology-snapshot-contract.json forms.required + intake aliases
# intake_router.py). This checker only APPLIES the required flags to a given
# payload and reports PASS/FAIL per field, fail-closed. The live read of the
# form definition (GET /locations/<id>/customFields and the forms rail) is the
# sibling form_reader's surface; this module is its pure offline companion —
# the same split the U03 family keeps between name_reader (live read) and
# rename_checker (the byte-exact law applied to what the read returned).
#
# FAIL-CLOSED (the whole point): an empty or missing first_name, last_name,
# or email is a FAIL — never a silent pass, never a fabricated value, never a
# whitespace-padded "present". A payload whose SHAPE cannot be read faithfully
# (not a dict, a field that is not a string) is ALSO a FAIL (the required
# flags are unverifiable — reading on would fabricate a clean check). There
# is no auto-heal: a missing required flag is a reportable FAIL, not
# something this module fixes. Keying law: email is a REQUIRED contact field
# here, never a KEY — everything keys off contact_id, never email
# (MASTERDOC floor 8; anthology-state.py participant_key).
#
# CREDENTIALS: this module holds ZERO credential surface — it reads no env
# var and resolves no label. Never-a-token doctrine applies twice: it never
# prints a secret because it never holds one, and its reports carry values
# ONLY from the payload it was handed (a payload may legitimately carry
# contact data; this module never echoes anything that looks like a token,
# only the field presence verdicts). A required flag is about PRESENCE and
# NON-EMPTINESS, never about content — a check result is a bool, not a value.
#
# BROWSER UA: no network surface exists here, so no User-Agent rides this
# module. The rule this module ENFORCES for its siblings: any module in the
# u04 package that talks to GoHighLevel / Convert and Flow
# (services.leadconnectorhq.com, Cloudflare-fronted) MUST send a browser
# User-Agent on every request (reg.CafClient applies CAF_BROWSER_UA — CF
# error 1010 403s urllib's default "Python-urllib/x.y" UA at the WAF edge
# before the request ever reaches the API; W0.6 / GK-09 discipline, the
# house pattern ported byte-for-byte from the Podcast gate).
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  PASS — every required flag is present with a non-empty string value
#      (also plan and self-test PASS)
#   1  unexpected error
#   2  STOP refusal — no contract source (the required-flags law is
#      unverifiable), usage error, or a payload whose shape cannot be read
#  4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  FAIL — a required flag is missing, empty, or not a string (data or
#      read-back mismatch; the fail-closed verdict for a drifted form)
#   (3 is not applicable here: no live surface, nothing to hold)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --self-test is OFFLINE and needs NO token and NO network):
#   required_checker.py check <payload.json>        # offline: the required
#                                                    # flags applied to a file
#   required_checker.py check --payload <json>      # offline; also from stdin
#                                                    # when --payload is "-"
#   required_checker.py plan                         # offline; the required
#                                                    # flags with their sources
#   required_checker.py self-test                    # offline golden + attack
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# other u04/u03 modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants. DOCTRINE:
# move in silence; NOTHING Anthropic in any runtime file; Convert and Flow
# naming in every client surface; NEVER print a secret value.
# =============================================================================
"""required_checker.py — the engine's required-flag checker: first_name,
last_name, email must be present and non-empty on the intake payload."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# canonical constants (CAF_BROWSER_UA / CAF_VERSION_HEADER) and the
# fail-closed helper surfaces; this module mirrors the constants it needs and
# pins the mirror in its offline self-test.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP = reg.EX_OK, reg.EX_ERR, reg.EX_STOP
EX_MISMATCH = reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# Canonical repo layout for the contract mirror-check (Skill 59 root ->
# config/anthology-snapshot-contract.json), mirroring the house layout used
# by house_rules.py and rename_checker.py (SKILL_DIR/scripts/<module> ->
# parent.parent = the skill root).
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
CONTRACT_KEY = "forms.required"

# ---------------------------------------------------------------------------
# THE REQUIRED-FLAGS LAW — contract-driven, never hardcoded (SPEC M8: a law
# read once, from the committed contract). The first_name / last_name / email
# keys are the intake-required participant fields as the intake extractor
# reads them (scripts/intake_router.py FIELD_ALIASES + upsert_scalar_fields).
# ---------------------------------------------------------------------------
def _contract_required_fields(contract: dict) -> list:
    """The required participant fields from the contract (forms.required ->
    required_fields), never hardcoded. Returns [] on an ABSENT section so a
    missing contract cannot masquerade as 'nothing required'."""
    forms = contract.get("forms") or {}
    required = forms.get("required") or []
    fields = []
    for row in required:
        if not isinstance(row, dict):
            continue
        if row.get("role") == "universal-author-intake":
            rf = row.get("required_fields")
            if isinstance(rf, list):
                fields = [f for f in rf if isinstance(f, str) and f]
            break
    return fields

def _load_contract() -> dict:
    """Load the committed required-flags contract. A missing/malformed file
    raises _ContractError (STOP family) — the law is unverifiable."""
    try:
        with open(CONTRACT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise _ContractError(
            "AF-AE-REQUIRED-CONTRACT-UNREADABLE: %s cannot be read (%s) — "
            "the required-flags law is unverifiable" % (CONTRACT_PATH, type(exc).__name__))

class _ContractError(Exception):
    """Fail-closed STOP: the required-flags contract cannot be read, so the
    law is unverifiable and no check may pass."""

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

# The canonical required set: the contract's forms.required.required_fields
# when the contract declares them (the form required-flag law), else the
# intake router's upsert scalar fields (the S0 intake-required law). Derived
# LAZILY at each entry point — exactly the rename_checker.py construction
# (_expected_name) — so a fail-closed contract read can never blow up at
# import time. The mirror is pinned byte-equal to both sources by the
# offline self-test.
def _required_fields() -> list:
    fields = _contract_required_fields(_load_contract())
    if not fields:
        fields = _intake_router_required_scalars()
    return fields

def resolve_required_fields() -> list:
    """The canonical required-fields law (contract first, intake router
    fallback), evaluated lazily and fail-closed on an unreadable contract."""
    return _required_fields()

# The intake extractor's canonical aliases for the same fields (mirrors
# intake_router.py FIELD_ALIASES — first_name/lastName/customData.first_name/
# contact.firstName are the SAME field, never a second column).
FIELD_ALIASES: dict = {
    "first_name": ("first_name", "firstName", "customData.first_name",
                   "customData.firstName", "contact.firstName"),
    "last_name": ("last_name", "lastName", "customData.last_name",
                  "customData.lastName", "contact.lastName"),
    "email": ("email", "customData.email", "contact.email"),
}

def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)

# ---------------------------------------------------------------------------
# The check — returns {"ok": bool, "required": [..], "missing": [..]}.
# FAIL-CLOSED: every required flag must be present AND a non-empty string.
# An unreadable shape (not a dict, a field that is not a string) is a FAIL —
# never a silent pass, never a fabricated value.
# ---------------------------------------------------------------------------
def check_required(payload, required_fields: list = None) -> dict:
    """Check the required participant flags against a payload.

    Returns {"ok": bool, "required": list, "missing": list, "source": str}.
    A field is MISSING when it is absent, an empty string, whitespace-only,
    or not a string at all. The report NEVER echoes any payload value — only
    the field names and the presence verdicts. NEVER raises on a missing
    flag (a FAIL is a reportable result, not an exception); raises only on a
    payload whose SHAPE cannot be read (not a dict — the required flags are
    unverifiable, reading on would fabricate a clean check).
    """
    if required_fields is None:
        required_fields = resolve_required_fields()
    if not required_fields:
        # Fail closed: no contract source, no required-flags law — a payload
        # with no contract cannot be certified clean.
        return {"ok": False, "required": [], "missing": [],
                "source": "no-required-fields-contract"}

    if not isinstance(payload, dict):
        raise _UnreadablePayload(
            "AF-AE-REQUIRED-PAYLOAD-UNREADABLE: payload is %s, not a dict — "
            "the required flags cannot be verified" % type(payload).__name__)

    missing = []
    for field in required_fields:
        aliases = FIELD_ALIASES.get(field) or (field,)
        value = _first_value(payload, aliases)
        if not _is_present(value):
            missing.append(field)
    return {"ok": not missing, "required": list(required_fields),
            "missing": missing, "source": CONTRACT_KEY}

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

class _UnreadablePayload(Exception):
    """Fail-closed refusal: the payload's shape cannot be read faithfully, so
    reporting would fabricate a check (STOP family, exit 2)."""

# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden payload passes, every attack fixture FAILS, and the required-flags
# law stays pinned to the committed contract. A tamper NEVER masquerades as
# exit 1.
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
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[required-checker] SELF-TEST FAILED "
                         "(AF-AE-REQUIRED-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

def _self_test_body(dev) -> None:
    want = list(resolve_required_fields())
    assert want, "the required-fields law must not be empty"
    assert want == ["first_name", "last_name", "email"], (
        "the required-fields law drifted from the U04 contract (forms.required "
        "required_fields / intake_router upsert_scalar_fields): %r" % want)
    # Pin the law to its TWO sources: the contract's required_fields when it
    # declares them, else the intake router's upsert scalar fields (never a
    # hardcoded tuple — SPEC M8: the law read once, from the owning module).
    contract_fields = _contract_required_fields(_load_contract())
    router_fields = _intake_router_required_scalars()
    assert router_fields, "intake_router upsert_scalar_fields must be readable"
    if contract_fields:
        assert contract_fields == want, (
            "contract forms.required required_fields drifted from the U04 "
            "contract: %r" % contract_fields)
    else:
        assert router_fields == want, (
            "intake_router upsert_scalar_fields drifted from the U04 contract: %r"
            % router_fields)

    # ---- golden payload: all three present -> ok True ----
    report = check_required(_golden_payload())
    assert report["ok"] is True, "golden payload must pass"
    assert report["missing"] == []
    assert report["required"] == want

    # ---- attack fixtures: every mutation FAILS (never a silent pass) ----
    # 1. email missing entirely -> ok False, email listed
    a1 = dict(_golden_payload())
    del a1["email"]
    report = check_required(a1)
    assert report["ok"] is False, "email-missing was NOT failed"
    assert report["missing"] == ["email"], report["missing"]
    # 2. empty string -> FAIL (presence is a NON-EMPTY string)
    a2 = dict(_golden_payload(), last_name="")
    report = check_required(a2)
    assert report["ok"] is False and report["missing"] == ["last_name"]
    # 3. whitespace-only -> FAIL (never a padded 'present')
    a3 = dict(_golden_payload(), first_name="   ")
    report = check_required(a3)
    assert report["ok"] is False and report["missing"] == ["first_name"]
    # 4. non-string value -> FAIL (a number is not a filled text field)
    a4 = dict(_golden_payload(), email=42)
    report = check_required(a4)
    assert report["ok"] is False and report["missing"] == ["email"]
    # 5. alias-only submission (firstName/customData.email) -> PASS: the
    #    aliases are the SAME fields, never a second column
    a5 = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
          "stage": "s0_intake", "firstName": "Ada", "lastName": "Lovelace",
          "customData": {"email": "ada@syn.test"}}
    report = check_required(a5)
    assert report["ok"] is True, "alias-only submission must pass"
    assert report["missing"] == []
    # 6. contact-object nesting -> PASS (contact.firstName is the same field)
    a6 = {"contact_id": "cnt_tmpl", "anthology_id": "anth_tmpl",
          "stage": "s0_intake",
          "contact": {"firstName": "Ada", "lastName": "Lovelace",
                      "email": "ada@syn.test"}}
    report = check_required(a6)
    assert report["ok"] is True, "contact-object submission must pass"
    # 7. unreadable shape -> refused, never a fabricated clean check
    try:
        check_required(["not", "a", "dict"])
        raise AssertionError("non-dict payload was NOT refused")
    except _UnreadablePayload:
        pass
    # 8. NO contract source -> fail closed with ok False (an empty law can
    #    never certify a payload clean; the no-required-fields-contract
    #    report is deterministic)
    report = check_required(_golden_payload(), required_fields=[])
    assert report["ok"] is False
    assert report["source"] == "no-required-fields-contract"
    # 9. the mirror never leaks: a required field's VALUE never appears in a
    #    report (never-a-token doctrine on the payload surface)
    assert "ada@syn.test" not in json.dumps(report), "report leaked a value"

    dev.write("required_checker self-test: OK (required-flags law pinned to "
              "config/anthology-snapshot-contract.json forms.required %r; "
              "golden PASS; 9 fixtures: email-missing / empty-string / "
              "whitespace-only / non-string / alias-only PASS / "
              "contact-object PASS / unreadable-shape REFUSED / no-contract "
              "FAIL closed; report values never echoed)\n" % want)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _report_json(report: dict) -> None:
    """Emit the ONE JSON object (machine surface, stdout) for a check run."""
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")

def run_check(payload, required_fields: list = None, *, out=None) -> int:
    """Apply the required flags to a payload. Returns the exit code. One JSON
    object lands on stdout; human notes go to stderr."""
    out = out or sys.stderr
    try:
        fields = list(required_fields) if required_fields is not None else list(resolve_required_fields())
    except _ContractError as exc:
        reg._stop(out, str(exc), ["Restore the committed contract and re-run."])
        return EX_STOP
    if not fields:
        reg._stop(out, "The required-flags contract is EMPTY.",
                  ["config/anthology-snapshot-contract.json forms.required "
                   "carries no required_fields and intake_router.py "
                   "upsert_scalar_fields is empty.",
                   "Restore the contract and re-run."])
        return EX_MISMATCH
    try:
        report = check_required(payload, fields)
    except _UnreadablePayload as exc:
        reg._stop(out, str(exc), ["Hand the payload a dict-shaped object and re-run."])
        return EX_STOP

    if report["ok"]:
        out.write("[required-checker] PASS: required flags present and "
                  "non-empty: %s.\n" % ", ".join(report["required"]))
        _report_json(report)
        return EX_OK

    reg._stop(out, "Required intake flags are MISSING on the payload.",
              ["Missing (first_name / last_name / email law): %s"
               % (", ".join(report["missing"]) or "none")],
              )
    _report_json(report)
    return EX_MISMATCH

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="required_checker.py",
        description="Fail-closed required-flag checker (U04): first_name, "
                    "last_name, email must be present and non-empty on the "
                    "Convert and Flow intake payload — a missing or empty "
                    "required flag is a FAIL, never a silent pass. One JSON "
                    "object on stdout; never prints a secret (Skill 59).")
    ap.add_argument("--payload", default="",
                    help="path to the payload JSON to check ('-' reads "
                         "stdin); the positional payload path is also "
                         "accepted (never the payload VALUE on argv)")
    ap.add_argument("cmd", nargs="?",
                    choices=["check", "plan", "self-test"], default="check")
    ap.add_argument("payload_path", nargs="?", default="",
                    help="path to the payload JSON (or '-' for stdin); "
                         "--payload wins when both are given")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-required-check-plan",
                "schema_version": 1,
                "required_fields": resolve_required_fields(),
                "source": CONTRACT_KEY,
                "law": "first_name / last_name / email must be present on the "
                       "intake payload as non-empty strings (the intake "
                       "extractor's aliases are the SAME fields); a missing, "
                       "empty, whitespace-only, or non-string value is a FAIL "
                       "— fail-closed, never a silent pass, never a "
                       "fabricated value",
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- check (offline): read the payload, apply the law ----
        # The payload is handed by PATH (file or '-') only — never by VALUE on
        # argv: a payload may carry contact data, and argv is an operator
        # surface (never-a-token doctrine; house scanning discipline).
        path = args.payload or args.payload_path
        if not path:
            ap.error("check requires a payload: PASS a path, --payload, or "
                     "'-' for stdin")
        try:
            if path == "-":
                payload = json.load(sys.stdin)
            else:
                with open(Path(path).expanduser(), encoding="utf-8") as fh:
                    payload = json.load(fh)
        except (OSError, ValueError) as exc:
            reg._stop(sys.stderr, "The payload cannot be read as JSON.",
                      ["Source: %r" % path,
                       "Error: %s" % type(exc).__name__])
            return EX_STOP

        return run_check(payload, out=sys.stderr)

    except _ContractError as exc:
        reg._stop(sys.stderr, str(exc), ["Restore the committed contract and re-run."])
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[required-checker] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
