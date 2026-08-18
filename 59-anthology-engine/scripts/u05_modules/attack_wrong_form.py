#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/attack_wrong_form.py
# ATTACK FIXTURE — WRONG FORM ON THE INTAKE FILTER, MUST FAIL (U05
# pipeline-rule surface). The adversarial sibling of the U05 scope law: the
# U05 pipeline rule whose filter is EXACTLY "Form is universal-intake"
# (form == "universal-intake", byte-exact) is in intake scope and may fire
# as the intake gate; a rule whose filter names ANY OTHER FORM is OUT of
# scope and must never be accepted as the intake gate. The filter is the
# independent identity signal — a foreign form's rule is a foreign rule, and
# every byte-exact scope gate must FAIL it.
#
# WHY THE WRONG FORM IS THE U05 ATTACK: the intake front door is a
# WEBHOOK-TO-ROUTE — the gateway hooks surface
# (config/route-template.json /hooks/anthology-intake, match.source
# 'anthology-intake') answers ONLY through the box route, and the U05
# pipeline rule rides that same front door (scope_checker.py: filter
# "Form is universal-intake"). A pipeline rule whose filter names a
# DIFFERENT form — a legacy contact-info form, a cross-location form, a
# lookalike clone — would route the WRONG form's submissions into the
# intake pipeline: a filter that matched by name, by a wildcard, by
# nothing, or by a hardcoded string would let that foreign form fire the
# intake gate, and every subsequent stage would run against a phantom
# participant. THIS module ships the wrong-form read that every byte-exact
# scope gate must FAIL: verdict FAIL, exit 5 (mismatch family) — never a
# pass. The true golden filter passes the same gates (exit 0), so the
# pass/fail split discriminates the one-form-wrong boundary and never a
# broken instrument (the negative-result contract: a gate that fails
# everything is a broken check, not a real fault).
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the golden pipeline-rule
# payload is the canonical surface of the scope law (the exact shape the
# gateway transform pipes on stdin — scope_checker.py's own golden fixture
# shape, {"source": "anthology-intake", "location": ..., "filter":
# "Form is universal-intake"}), then the ONE form named by the filter is
# swapped to the adversarial form — "Form is contact-info-form" (a foreign
# form, never the universal author-intake form). Every other field is
# preserved byte-for-byte. A wrong form named by an otherwise-canonical
# rule is exactly the "a foreign form's rule got accepted as the intake
# gate" shape that must never fire; the form named is the single variable,
# so the failure isolates the scope law and nothing else.
#
# WHERE THIS SITS: scripts/u05_modules/ — an importable module under the U05
# package (pure namespace container per the u05 __init__.py: imported BY
# NAME, side-effect-free at import). It is NOT a manifest row and NOT a
# checker: it ships the ADVERSARIAL FIXTURE the self-tests of the U05 scope
# gates and their sibling checkers assert against, so the FAIL path is
# judged against the SAME surface the happy path judges against — a drift
# in the scope law (scope_checker) breaks THIS module's self-test first
# (fail-closed: an inconsistent law is a refusal, never a blind pass). The
# sibling attack_unscoped.py covers the EMPTY-filter direction (a filter
# that is empty/whitespace-only is an UNFILTERED rule — the U05
# empty-filter doctrine); THIS module owns the WRONG-FORM direction and
# refuses to ship any other shape (a fixture that drifts is REFUSED, never
# shipped).
#
# WHAT THIS OWNS:
#   1. attack_rule(rule=None) — the builder, fail-closed: the golden rule
#      payload comes from the SINGLE AUTHORITY (u05_modules.scope_checker
#      and its mirrored u02 sibling u02_modules.scope_check — the intake
#      scope law, never a second implementation), is checked against the
#      form law (the golden filter names exactly the universal-intake form),
#      then the ONE form named by the filter is swapped to the adversarial
#      one; a malformed rule or any drift raises FixtureError instead of
#      shipping a wrong fixture.
#   2. verify_rule(rule, gates=None) — the JUDGE: runs a rule payload
#      through the U05 scope gate AND its mirrored u02 trigger-side sibling
#      (both authorities — the trigger side and the pipeline side must
#      agree) and exits 5 (mismatch family) on the wrong-form attack,
#      naming the foreign form token and the expected one — never a pass;
#      on the true golden rule it exits 0. The one place this module makes
#      the FAIL explicit: an attack fixture that PASSES any scope gate is a
#      broken gate.
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships
#      the wrong-form attack rule (the fixture is the module's product) and
#      exits 0 only when the attack is EXACTLY the one-wrong-form shape; any
#      drift (the golden form, a missing filter, a malformed rule, a
#      conflated authority) is REFUSED with exit 5 (verdict REFUSED).
#      payload_true() is the control: the TRUE golden rule passes exit 0
#      and its own law pin catches a regression in the scope authority, so
#      the self-test's pass/fail split discriminates the one-form-wrong
#      boundary and never a broken instrument.
#
# DOCTRINE (inherited from the registry / the U02-U05 scope family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory rule metadata over SYNTHETIC fixture
#     data (never a live id, never a live domain), and the verify surface
#     reports form tokens (rule names, never credentials) verbatim exactly
#     as the scope gates' own return contracts do — never a token value.
#     Nothing in this module can ever echo a secret because no secret is
#     ever read.
#   - Fail-closed: a drifted authority, an unparseable rule, a wrong-shaped
#     payload all STOP or FAIL — never a blind pass, never a fabricated
#     success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The GHL / Convert and Flow surface is Cloudflare-fronted: urllib's
#     default "Python-urllib/x.y" User-Agent is 403'd at the WAF edge (CF
#     error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES talk to the platform must ride the house browser
#     User-Agent on every request, and the self-test pins the constant so a
#     registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U05 attack_unscoped
# sibling and the U04 attack_bad_query family):
#   0  verified success — the golden control rule is internally consistent
#      and byte-exact to the scope law; also self-test / plan OK
#   1  unexpected error (malformed input / no rule to judge)
#   4  self-test FAILED (AF-AE-ATTACKWRONGFORM-* family, enforced violation)
#   5  mismatch — the wrong-form attack rule is FAIL (verify_rule) or
#      REFUSED (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# attack_unscoped.py: sys.path.insert to scripts/ then `import
# anthology_registry as reg` / `import u05_modules.scope_checker as
# u05scope` / `import u02_modules.scope_check as u02scope`.
# =============================================================================
"""attack_wrong_form.py — the wrong-form-on-the-intake-filter attack fixture
that must FAIL.

The adversarial sibling of the U05 pipeline-rule scope law: a canonical
pipeline rule whose filter names a FOREIGN form ("Form is contact-info-form")
instead of the byte-exact "Form is universal-intake" — every scope gate must
refuse it while this module's own gates refuse anything that is not exactly
that shape (exit 5).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to attack_unscoped.py):
# the U05 scope checker owns the pipeline-rule filter law (the ONE filter
# expression in intake scope), the u02 scope gate is its mirrored trigger-side
# sibling (the two must agree), the registry owns the browser-UA wiring + the
# masking helper — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u02_modules.scope_check as u02scope  # noqa: E402  (trigger-side scope law)
import u05_modules.scope_checker as u05scope  # noqa: E402  (pipeline-rule scope law)

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-wrong-form"

# The adversarial form the attack filter names — a FOREIGN form, never the
# universal author-intake form (the same foreign-form token the scope gates'
# own self-tests attack with: scope_checker.py "Form is contact-info-form",
# u02 scope_check.py "contact-info-form"). Hardcoded here and PINNED against
# the authority in the self-test (the golden filter must name exactly the
# universal-intake form; if the authority ever drifts, the fixture's
# self-test breaks first, fail-closed). NEVER used to build a golden rule —
# only to attack one.
ATTACK_FORM = "contact-info-form"
ATTACK_FILTER = "Form is " + ATTACK_FORM  # "Form is contact-info-form"

# The canonical golden rule payload — the scope law's own golden surface (the
# exact shape the gateway transform pipes on stdin; scope_checker.py's golden
# fixture shape). Synthetic fixture data, never a live id, never a live
# domain.
GOLDEN_RULE = {
    "source": "anthology-intake",
    "location": "LOC-synthetic-AAA",
    "filter": u05scope.UNIVERSAL_INTAKE_FILTER,
}

# The form-token expression shape the filter must carry: the verb "Form is"
# + the form token — the independent identity signal of the intake rule.
_EXPRESSION_RE = re.compile(r"^Form is (.+)$")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the scope
    authority or the rule drifted from the law, so NO fixture is shipped — a
    wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, canonical minus the form.
# ---------------------------------------------------------------------------
def _named_form(rule: dict) -> str:
    """The form token a pipeline-rule filter names, under the expression law:
    the filter is the byte-exact "Form is <token>" expression (the ONE
    expression shape the U05 scope checker recognizes — any other shape names
    nothing). Returns "" when the rule carries no such filter. Fail-closed: a
    rule that is not a mapping refuses."""
    if not isinstance(rule, dict):
        raise FixtureError(
            "rule is %r, not a mapping — refusing to judge an unparseable "
            "surface (never fabricated)." % type(rule).__name__)
    flt = rule.get("filter")
    if not isinstance(flt, str):
        return ""
    m = _EXPRESSION_RE.match(flt.strip())
    if not m:
        return ""
    token = m.group(1).strip()
    return token if token else ""


def _swap_named_form(rule: dict, form: str) -> dict:
    """Rewrite the ONE form named by the filter of a canonical rule to form,
    preserving every other field byte-for-byte. Fail-closed: a canonical rule
    with no "Form is <token>" filter, or one that already names the
    adversarial form, is drift — refusing."""
    if not form or not form.strip() or " " in form.strip():
        raise FixtureError(
            "attack form %r is not a single form token — refusing." % form)
    if not isinstance(rule, dict) or "filter" not in rule:
        raise FixtureError(
            "canonical rule carries no 'filter' field — refusing to attack "
            "an unparseable rule.")
    flt = rule.get("filter")
    if not isinstance(flt, str):
        raise FixtureError(
            "canonical rule filter is %r, not a string — refusing." % flt)
    m = _EXPRESSION_RE.match(flt.strip())
    if not m:
        raise FixtureError(
            "canonical rule filter %r is not the 'Form is <token>' "
            "expression — refusing to attack an unparseable rule." % flt)
    token = m.group(1).strip()
    if token == form:
        raise FixtureError(
            "canonical rule already names the adversarial form %r — the "
            "authority conflated the forms; refusing to ship a double-swap "
            "attack." % form)
    out = dict(rule)
    out["filter"] = "Form is " + form
    return out


def attack_rule(rule: dict = None, form: str = ATTACK_FORM) -> dict:
    """Build the attack rule: the golden rule payload comes from the SINGLE
    AUTHORITY (u05_modules.scope_checker — never a second implementation),
    is checked against the form law (the golden filter names exactly the
    universal-intake form under the "Form is <token>" expression), then the
    ONE form named is swapped to the adversarial one. Any drift raises
    FixtureError — a wrong fixture is never shipped."""
    base = dict(rule) if rule is not None else dict(GOLDEN_RULE)
    token = _named_form(base)
    if not token:
        raise FixtureError(
            "golden rule carries no 'Form is <token>' filter — the scope "
            "authority drifted from the expression law; refusing to ship an "
            "attack payload.")
    if token != u05scope.UNIVERSAL_INTAKE_FORM:
        raise FixtureError(
            "golden rule filter names %r, not the byte-exact universal-"
            "intake form — the scope authority drifted; refusing to ship an "
            "attack payload." % token)
    return _swap_named_form(base, form)


# The canonical attack rule, derived ONCE at import from the scope authority
# — fail-fast: a drifted authority breaks the import of the fixture itself,
# so a checker that imports this module by name catches the drift first.
ATTACK_RULE = attack_rule()

# The golden control rule, derived from the SAME authority — the pass side of
# the pass/fail split (a gate that fails everything is a broken instrument).
GOLDEN_RULE_CANONICAL = dict(GOLDEN_RULE)


# ---------------------------------------------------------------------------
# The judge — verify_rule: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _to_trigger_shape(rule: dict) -> dict:
    """The trigger-side canonical surface the u02 scope gate judges: the
    intake-submission shape the u02 gate reads (its form candidates are
    form / customData.form / data.form — never the pipeline-rule 'filter'
    key), derived from the rule WITHOUT re-implementing the law: the form
    token is the token the rule's 'Form is <token>' filter names, the
    source / location ride along, and the stage is forwarded ONLY when the
    rule carries one (never fabricated)."""
    out = {"source": rule.get("source"), "location": rule.get("location")}
    token = _named_form(rule)
    if token:
        out["form"] = token
    stage = rule.get("stage")
    if stage is not None:
        out["stage"] = stage
    return out


def _verify_one_gate(gate_check, input_surface: dict) -> tuple:
    """Run ONE scope gate over ITS canonical input surface and return
    (ok, reason_or_form). The gate is the authority's own check function —
    never a re-implementation — and it is side-effect-free by contract
    (u05/u02 scope gates return a 2-tuple and print nothing). The u05
    pipeline-rule gate judges the rule itself; the u02 trigger-side gate
    judges the derived intake-submission shape (_to_trigger_shape)."""
    ok, flt = gate_check(input_surface)
    if ok:
        return True, ""
    reason = flt.get("reason") if isinstance(flt, dict) else "unknown"
    return False, str(reason or "unknown")


def verify_rule(rule: dict, gates=None, *, out=None) -> int:
    """Judge a rule payload against the U05 scope law.

    READ-ONLY and OFFLINE: the judged surface is whatever rule the caller
    hands in — the canonical ATTACK_RULE fixture, the GOLDEN_RULE_CANONICAL
    control, or a rule piped from the gateway transform (this module never
    makes a network call — reg.CafClient is the only thing that ever talks
    to Convert and Flow, and it sends CAF_BROWSER_UA on every request, the
    proven CF-1010 edge fix). The judge is the explicit fail: on the
    wrong-form attack the verdict is FAIL, exit 5 (mismatch family), naming
    the foreign form token and the expected one; on the true golden rule the
    verdict is PASS, exit 0.

    `gates` defaults to (u05scope.check, u02scope.check) — the pipeline-rule
    side AND its mirrored trigger-side sibling, because the two must agree:
    a rule that passes one gate while failing the other is a split, never a
    pass. Report: ONE JSON object on stdout (form tokens are rule names —
    never credentials — surfaced verbatim exactly as the gates' own return
    contracts do; the location is reported by MASKED MARKER only), human
    notes on stderr. NEVER prints a token (it holds none: the fixture is
    pure in-memory rule metadata)."""
    out = out or sys.stderr
    if gates is None:
        gates = (u05scope.check, u02scope.check)
    want = u05scope.UNIVERSAL_INTAKE_FORM
    results = []
    if not isinstance(rule, dict):
        results.append({"gate": "n/a", "ok": False, "reason": "not_a_dict"})
    else:
        trigger_shape = _to_trigger_shape(rule)
        for gate in gates:
            surface = rule if gate is u05scope.check else trigger_shape
            ok, reason = _verify_one_gate(gate, surface)
            results.append({"gate": getattr(gate, "__module__", "?") + "."
                            + getattr(gate, "__name__", "?"),
                            "ok": ok, "reason": reason})
    ok = all(r["ok"] for r in results) if results else False
    token = _named_form(rule) if isinstance(rule, dict) else ""
    location = rule.get("location") if isinstance(rule, dict) else ""
    detail = ("all scope gates pass: the rule filter names the byte-exact "
              "universal-intake form and every gate is IN_SCOPE — the golden "
              "control PASSES this judge"
              if ok else (
                  "%d scope gate(s) refuse the rule — form named %r, expected "
                  "exactly %r: %s"
                  % (sum(0 if r["ok"] else 1 for r in results),
                     token, want,
                     "; ".join("%s (%s)" % (r["reason"], r["gate"])
                               for r in results))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "form_named": token,
        "expected_form": want,
        "location_marker": reg._mask_location(location) if location else "",
        "gates": results,
        "detail": detail,
        "fail_closed": {
            "wrong_form_fails": True,
            "byte_exact_required": True,
            "note": "a rule whose filter names ANY form other than the "
                    "byte-exact universal-intake form is FAIL, exit 5 — "
                    "never a pass. An attack fixture that passes ANY scope "
                    "gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-wrong-form] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-wrong-form] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the wrong-form attack rule, but ONLY the
    one-wrong-form attack. Any drift — the golden form, a missing filter, a
    malformed rule, a conflated authority — is REFUSED with exit 5 (verdict
    REFUSED, ok False), never shipped. Returns the exit code; emits the ONE
    JSON report object on stdout, human notes on stderr. The shipped rule is
    built from SYNTHETIC fixture data (never a live id, never a live
    domain), so shipping it is harmless."""
    out = out or sys.stderr
    try:
        rule = attack_rule()
    except FixtureError as exc:
        out.write("[attack-wrong-form] payload REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rule": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    token = _named_form(rule)
    if token != ATTACK_FORM:
        out.write("[attack-wrong-form] payload REFUSED: the attack rule names "
                  "form %r, not exactly %r — the fixture drifted; "
                  "refusing.\n" % (token, ATTACK_FORM))
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rule": None,
            "detail": "attack fixture must name EXACTLY the one adversarial "
                      "form %r, got %r — drift." % (ATTACK_FORM, token),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "rule": rule,
        "form_named": token,
        "expected_form": u05scope.UNIVERSAL_INTAKE_FORM,
        "detail": "attack rule derived byte-exact from the scope authority "
                  "(the canonical 'Form is <token>' expression with the ONE "
                  "form named swapped from %r to %r, every other field "
                  "preserved): the wrong-form read that MUST FAIL every "
                  "byte-exact scope gate."
                  % (u05scope.UNIVERSAL_INTAKE_FORM, ATTACK_FORM),
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE golden rule must
    PASS exit 0 — so a payload gate that fails EVERYTHING (a broken
    instrument) is never mistaken for a real one-form-wrong discrimination.
    Derives the golden rule via the scope authority (never a second
    implementation) and pins the law on it: if the authority ever regresses
    (the filter stops naming the universal-intake form), the control REFUSES
    with exit 5 — a regression is caught HERE first."""
    out = out or sys.stderr
    rule = dict(GOLDEN_RULE)
    token = _named_form(rule)
    if token != u05scope.UNIVERSAL_INTAKE_FORM:
        out.write("[attack-wrong-form] payload-true REFUSED: the golden rule "
                  "names form %r, not exactly %r — the scope authority "
                  "regressed; refusing.\n"
                  % (token, u05scope.UNIVERSAL_INTAKE_FORM))
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rule": None,
            "detail": "the canonical rule no longer names the byte-exact "
                      "universal-intake form (got %r) — the authority "
                      "regressed." % token,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "rule": rule,
        "form_named": token,
        "expected_form": u05scope.UNIVERSAL_INTAKE_FORM,
        "detail": "control: the true golden rule names the byte-exact "
                  "universal-intake form and passes exit 0 — the wrong-form "
                  "attack fails by comparison, never by a broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack swaps and
    why, straight from the scope authority (the single source of truth —
    never a hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "expected_filter": u05scope.UNIVERSAL_INTAKE_FILTER,
        "attack_filter": ATTACK_FILTER,
        "expected_form": u05scope.UNIVERSAL_INTAKE_FORM,
        "attack_form": ATTACK_FORM,
        "other_fields_preserved": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack swaps the ONE form named by the canonical 'Form is "
                "<token>' rule filter from %r to %r, preserving every other "
                "field byte-for-byte: the wrong-form read that MUST FAIL "
                "every byte-exact scope gate (the U05 pipeline-rule gate and "
                "its mirrored u02 trigger-side gate)."
                % (u05scope.UNIVERSAL_INTAKE_FORM, ATTACK_FORM),
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline attack_unscoped
# and its siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-wrong-form] SELF-TEST FAILED "
                         "(AF-AE-ATTACKWRONGFORM-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the authority is the single source of truth ------------------------
    assert u05scope.UNIVERSAL_INTAKE_FILTER == "Form is universal-intake", \
        "the U05 filter authority must pin the byte-exact intake expression, " \
        "got %r" % u05scope.UNIVERSAL_INTAKE_FILTER
    assert u05scope.UNIVERSAL_INTAKE_FORM == "universal-intake", \
        "the U05 form authority must pin the universal-intake token, got %r" \
        % u05scope.UNIVERSAL_INTAKE_FORM
    assert u02scope.UNIVERSAL_INTAKE_FORM == "universal-intake", \
        "the u02 trigger-side gate must agree on the form token, got %r" \
        % u02scope.UNIVERSAL_INTAKE_FORM
    assert u02scope.UNIVERSAL_INTAKE_FORM == u05scope.UNIVERSAL_INTAKE_FORM, \
        "the two scope gates must agree on the gated form (never a split)"
    assert ATTACK_FORM != u05scope.UNIVERSAL_INTAKE_FORM, \
        "the adversarial form must differ from the universal-intake form"
    # the two gates agree on the golden rule BEFORE any attack is judged (a
    # gate that refuses the golden surface is a broken instrument, never a
    # pass). Each gate judges its OWN canonical surface: the u05 pipeline-rule
    # gate judges the rule itself, the u02 trigger-side gate judges the
    # derived intake-submission shape (_to_trigger_shape) — the exact split
    # the judge applies.
    ok_u05, flt_u05 = u05scope.check(dict(GOLDEN_RULE))
    ok_u02, flt_u02 = u02scope.check(_to_trigger_shape(dict(GOLDEN_RULE)))
    assert ok_u05 and ok_u02, \
        "both scope gates must IN_SCOPE the golden rule (u05=%r u02=%r)" \
        % (flt_u05, flt_u02)

    # ---- the canonical attack rule: the one form wrong, everything else
    #      preserved ------------------------------------------------
    rule = ATTACK_RULE
    assert _named_form(rule) == ATTACK_FORM, \
        "the attack rule must name EXACTLY the one adversarial form, got %r" \
        % _named_form(rule)
    assert rule["filter"] == ATTACK_FILTER, \
        "the attack filter must be byte-exact, got %r" % rule["filter"]
    assert rule.get("source") == GOLDEN_RULE.get("source"), \
        "the attack must preserve the source byte-for-byte"
    assert rule.get("location") == GOLDEN_RULE.get("location"), \
        "the attack must preserve the location byte-for-byte"
    # the golden control differs from the attack in the ONE variable only
    assert _named_form(GOLDEN_RULE_CANONICAL) == u05scope.UNIVERSAL_INTAKE_FORM
    assert GOLDEN_RULE_CANONICAL.get("source") == rule.get("source")
    assert GOLDEN_RULE_CANONICAL.get("location") == rule.get("location")

    # ---- the judge: wrong-form read MUST FAIL, golden control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(rule, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the wrong-form attack rule must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the wrong-form read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["form_named"] == ATTACK_FORM, \
        "the judge must name the foreign form token, got %r" \
        % parsed["form_named"]
    assert parsed["expected_form"] == "universal-intake", \
        "the judge must name the expected universal-intake form"
    assert len(parsed["gates"]) == 2 and all(
        g["ok"] is False for g in parsed["gates"]), \
        "BOTH scope gates must refuse the wrong-form attack, got %r" \
        % parsed["gates"]

    # the judge NEVER prints a token (form tokens are rule names — never
    # credentials — surfaced exactly as the gates' own return contracts do;
    # the location is masked, and no token shape ever rides any surface)
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"
    assert parsed["location_marker"] == reg._mask_location("LOC-synthetic-AAA"), \
        "the judge must mask the location"

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(GOLDEN_RULE_CANONICAL, out=io.StringIO())
    assert rc == EX_OK, "the golden rule must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert len(parsed["gates"]) == 2 and all(
        g["ok"] is True for g in parsed["gates"]), \
        "BOTH scope gates must pass the golden rule, got %r" % parsed["gates"]

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # 1. an EMPTY filter is the sibling U05 attack direction (empty-filter
    #    doctrine) -> FAIL, never a pass
    empty = dict(GOLDEN_RULE, filter="")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(empty, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "an empty filter must FAIL (exit 5), got %s" % rc
    assert all(g["ok"] is False for g in
               json.loads(buf.getvalue())["gates"]), \
        "the empty-filter read must fail EVERY gate"
    # 2. a whitespace-only filter -> FAIL (looks empty to the eye, not to
    #    the gate)
    blank = dict(GOLDEN_RULE, filter="   ")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(blank, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a whitespace-only filter must FAIL (exit 5), got %s" % rc
    # 3. a filter MISSING entirely -> FAIL, never a pass
    missing = {k: v for k, v in GOLDEN_RULE.items() if k != "filter"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(missing, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a filter-less rule must FAIL (exit 5), got %s" % rc
    # 4. a WILDCARD filter -> FAIL (a wildcard names every form — never the
    #    intake gate)
    wild = dict(GOLDEN_RULE, filter="*")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(wild, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a wildcard filter must FAIL (exit 5), got %s" % rc
    # 5. a case-drifted filter -> FAIL (byte-exact law; a rule that would
    #    silently NOT match the engine's fixtures is never the gate)
    case = dict(GOLDEN_RULE, filter="form is universal-intake")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule(case, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a case-drifted filter must FAIL (exit 5), got %s" % rc
    # 6. a non-mapping surface -> FAIL (the judge is never a pass: a
    #    non-mapping rule is drift, exit 5, never a pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_rule("not-a-mapping", out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a non-mapping surface must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "FAIL", \
        "a non-mapping surface must never be a pass"

    # ---- the fail-closed gates: the attack ships, the control passes --------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["form_named"] == ATTACK_FORM
    assert parsed["expected_form"] == "universal-intake"
    assert parsed["contract"] == ATTACK_CONTRACT
    shipped = parsed["rule"]
    assert isinstance(shipped, dict) and shipped["filter"] == ATTACK_FILTER
    # the shipped payload carries only synthetic fixture data — never a live
    # platform domain, never a token shape
    dumped = buf.getvalue()
    assert "https://" not in dumped and "msgsndr" not in dumped, \
        "the fixture must never reference a live platform domain"
    assert "pit-" not in dumped and "Bearer" not in dumped, \
        "the payload output must never carry a token shape"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES the golden form (the wrong direction is drift) --
    # cross-surface fail-closed proof.
    try:
        attack_rule(form=u05scope.UNIVERSAL_INTAKE_FORM)
        raise AssertionError("a golden-form attack must be REFUSED")
    except FixtureError:
        pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload must still ship the attack after the refusal"

    # payload-true (the control): the true golden rule passes exit 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, "payload-true on the true authority must exit 0, " \
        "got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["form_named"] == "universal-intake"

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. a canonical rule with no 'Form is <token>' expression -> refusal
    try:
        _swap_named_form({"filter": "universal-intake"}, ATTACK_FORM)
        raise AssertionError("a bare-token filter was NOT refused")
    except FixtureError:
        pass
    # 2. a canonical rule that already names the adversarial form -> refusal
    #    (the double-swap a regression would produce)
    try:
        _swap_named_form(dict(GOLDEN_RULE, filter=ATTACK_FILTER), ATTACK_FORM)
        raise AssertionError("a double-swap was NOT refused")
    except FixtureError:
        pass
    # 3. a canonical rule with a non-string filter -> refusal
    try:
        _swap_named_form(dict(GOLDEN_RULE, filter=42), ATTACK_FORM)
        raise AssertionError("a non-string filter was NOT refused")
    except FixtureError:
        pass
    # 4. a canonical rule without a 'filter' field -> refusal
    try:
        _swap_named_form({"source": "anthology-intake"}, ATTACK_FORM)
        raise AssertionError("a filter-less canonical rule was NOT refused")
    except FixtureError:
        pass
    # 5. a non-mapping rule -> refusal
    try:
        _swap_named_form("not-a-mapping", ATTACK_FORM)
        raise AssertionError("a non-mapping rule was NOT refused")
    except FixtureError:
        pass
    # 6. a golden rule whose filter names a foreign form -> refusal (the
    #    authority must never ship a wrong-form rule as the golden surface)
    try:
        attack_rule(dict(GOLDEN_RULE, filter=ATTACK_FILTER))
        raise AssertionError("a foreign-form golden rule was NOT refused")
    except FixtureError:
        pass

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact swap ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["expected_filter"] == "Form is universal-intake"
    assert p["attack_filter"] == ATTACK_FILTER
    assert p["other_fields_preserved"] is True

    dev.write("attack_wrong_form self-test: OK (scope authority pinned "
              "(u05 filter %r / form token %r, mirrored byte-exact by the "
              "u02 trigger-side gate); canonical one-form-wrong rule "
              "swapping the form named by 'Form is <token>' from %r to %r "
              "with every other field preserved byte-for-byte over "
              "synthetic fixture data; judge FAILs the wrong-form read with "
              "exit 5 through BOTH scope gates naming the foreign form "
              "token and masking the location while the golden control "
              "PASSES exit 0 through both; empty / whitespace / missing / "
              "wildcard / case-drift filters FAIL, non-mapping surfaces "
              "refuse; payload gate ships the one-wrong-form attack and "
              "REFUSES under a conflated authority while payload-true "
              "control PASSes the golden rule; 6 attack fixtures refused "
              "(bare-token / double-swap / non-string filter / filter-less "
              "rule / non-mapping / foreign-form golden); CAF_BROWSER_UA "
              "pinned; plan offline)\n"
              % (u05scope.UNIVERSAL_INTAKE_FILTER,
                 u05scope.UNIVERSAL_INTAKE_FORM,
                 u05scope.UNIVERSAL_INTAKE_FORM, ATTACK_FORM))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_wrong_form.py",
        description="Attack fixture — wrong form on the intake filter, must "
                    "FAIL (Skill 59, U05 tooling): the adversarial sibling "
                    "of the U05 pipeline-rule scope law, shipping the "
                    "deterministic one-form-wrong rule (the 'Form is "
                    "<token>' filter naming a foreign form instead of the "
                    "byte-exact universal-intake form, every other field "
                    "preserved) that every byte-exact scope gate must "
                    "refuse, and the fail-closed offline gates that prove "
                    "it (the golden control PASSES).")
    ap.add_argument("--rule", default=None,
                    help="rule to judge (verify); defaults to the first "
                         "stdin line (e.g. a gateway-transformed rule JSON "
                         "| attack_wrong_form.py --live)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "payload-true",
                                               "verify", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest / --live -> positional subcommands
    # (the same normalization the registry and the U02 verifier use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--live" in argv:
        argv = ["verify" if a == "--live" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan()
        if args.cmd == "payload-true":
            return payload_true()
        if args.cmd == "verify":
            raw = (args.rule or sys.stdin.read().strip())
            if not raw:
                sys.stderr.write("[attack-wrong-form] no rule given (--rule "
                                 "or stdin) — nothing to judge.\n")
                return EX_ERR
            try:
                rule = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[attack-wrong-form] the rule on stdin is "
                                 "not valid JSON: %s\n" % exc)
                return EX_ERR
            return verify_rule(rule, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-wrong-form] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-wrong-form] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
