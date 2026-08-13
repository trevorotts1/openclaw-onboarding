#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/attack_bad_dropdown.py
# ATTACK FIXTURE — DECISION DROPDOWN WRONG OPTIONS, MUST FAIL (U08/U09
# decision-dropdown law). The adversarial sibling of the U08/U09 dropdown
# creator (u08_u09_modules.dropdown_module): the PRD Section 4
# universal-review DECISION field (contact.anthology_review_decision, a
# SINGLE_OPTIONS picklist) carrying a WRONG OPTION — the ONE option byte
# swapped to the adversarial spelling, the exact drift the repo itself
# documents. Every byte-exact picklist gate (the dropdown creator's law
# check, the U08/U09 picklist verifier) MUST FAIL this read in BOTH of its
# directions: the wrong-option picklist is a FAIL (never a pass); and THIS
# module's own gate payload() must REFUSE shipping anything that is not
# exactly the one-option-wrong attack — a picklist with zero, three, the
# right options, or a reordered/duplicated set is drift, never an attack
# fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical two-option
# picklist is built from the SINGLE AUTHORITY (gate_engine.py GateSpec
# s5_gate — EXACTLY ("approve_as_is", "request_rewrite_with_notes"), read
# through dropdown_module._decision_option_law(), never a second
# implementation; a hardcoded option list would drift and defeat the
# fixture's whole purpose), then the ONE variable — the FIRST option's byte
# — is swapped to the adversarial spelling "approved_as_is", preserving the
# second option byte-for-byte. A wrong option riding alongside the true
# second option is exactly the drift shape that must never pass a picklist
# gate; the preserved option is NOT part of the attack, so the failure
# isolates the option law and nothing else.
#
# THE ADVERSARIAL SPELLING IS THE REPO'S OWN DOCUMENTED DRIFT, never an
# invented byte: "approved_as_is" (dashed) is the exact decision value the
# committed golden-review fixture ships (u08_u09_modules/golden_review.py
# GOLDEN_DECISION = "approved_as_is" — the negative mirror's canonical
# pick). The gate vocabulary that consumes the decision dropdown is
# UNDASHED ("approve_as_is", request_rewrite_with_notes — gate_engine
# ACTION_DECISION / GateSpec s5_gate): a live picklist carrying the dashed
# spelling is a picklist whose submitted value no gate action can consume,
# the same conflation shape attack_bad_query.py guards for the intake-link
# query key (anthology_active_id is a REAL key elsewhere in the system, just
# not the form's query key — the parallel: the dashed spelling is a REAL
# committed decision value, just not a valid dropdown option). The attack
# option is hardcoded here and PINNED in the self-test against BOTH
# authorities — golden_review.GOLDEN_DECISION (it must equal the committed
# drift byte-exact) and the dropdown law (it must NOT be one of the two
# gate actions) — so a drifted authority breaks THIS module's self-test
# first (fail-closed: an inconsistent law is a refusal, never a blind
# pass).
#
# THE --execute GATE (Trevor's doctrine, package-init): the u08_u09 package
# init (u08_u09_modules/__init__.py) binds destructive actions to an
# explicit --execute. This module is an ATTACK fixture: shipping the attack
# (payload) and judging a picklist against it (verify) mutate NO live
# surface — they are pure in-memory fixtures — but the house doctrine is
# applied fail-closed in BOTH directions, exactly as the sibling
# attack_missing_hidden.py applies it: (a) the attack payload is REFUSED
# unless the operator passes --execute to THIS module's OWN CLI, and (b)
# the module's own verify of the wrong-option read carries
# execute_required: True and refuses to certify any picklist that does not
# byte-equal the two-option law. The failure the fixture exists to prove
# (wrong dropdown options -> FAIL) is therefore never produced by accident:
# it takes an explicit Trevor-gated invocation, exactly like the mutation
# surfaces of the family (query_key_fixer.py, hidden_field_module.py,
# dropdown_module.py --execute). Every OTHER invocation is a read-only plan
# or an offline self-test.
#
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# U08/U09 package (pure namespace container per the u08_u09 __init__.py:
# imported BY NAME, side-effect-free at import). It is NOT a manifest row
# and it NEVER touches ENGINE-MANIFEST.json / ENGINE-PIN.sha256 /
# verify.sh: it ships as the adversarial sibling of dropdown_module.py the
# way attack_missing_hidden.py siblings hidden_field_module.py and
# attack_bad_query.py siblings anthology_book.py (the u04 pattern — a
# fixture is not a manifest row). Standalone invocation works too: the SAME
# sys.path.insert bootstrap the sibling imports use resolves
# anthology_registry from scripts/.
#
# WHAT THIS OWNS:
#   1. ATTACK_OPTIONS — a frozen, deterministic tuple of the TWO option
#      strings exactly as a live decision dropdown would return them for a
#      picklist carrying the wrong first option: the preserved second
#      option byte-equal to the gate law, the FIRST option swapped to the
#      adversarial dashed spelling (approved_as_is), and NO option added,
#      dropped, or reordered: the attack is a ONE-BYTE-REPLACED set, the
#      exact shape that must never pass. The tuple is immutable through
#      every public route; consumers needing a mutable picklist call
#      attack_options() (a fresh tuple).
#   2. attack_options(law=None) — the builder, fail-closed: a law that does
#      not satisfy the TWO-option law (exactly two distinct non-empty
#      strings), or a law that already carries the adversarial spelling (the
#      exact conflation a regression would produce), raises FixtureError
#      instead of shipping a wrong fixture. The swap is by POSITION (the
#      first option), never by a hardcoded option byte.
#   3. verify_options(picklist, *, out) — the JUDGE: reports a picklist
#      against the two-option decision law and exits 5 (mismatch family) on
#      the wrong-option attack, naming the wrong option and the expected
#      one — never a pass; on the true two-option golden picklist it exits
#      0. The one place this module makes the FAIL explicit: an attack
#      fixture that PASSES any picklist gate is a broken gate. Other drift
#      directions (reordered / extra / dropped / duplicated / blank option)
#      FAIL with their named defect; a non-list surface is a hard refusal,
#      never a verdict.
#   4. payload(*, execute=False) / payload_true(*, execute=False) — the
#      FAIL-CLOSED gates. payload() REFUSES without --execute (the Trevor
#      gate; verdict REFUSED, exit 5) and ships the one-option-wrong
#      fixture ONLY with the gate; any drift (zero options, three options,
#      the right options, a reordered set, a conflated authority) is
#      REFUSED, never shipped. payload_true() is the control: the TRUE
#      two-option golden picklist passes exit 0 — so the self-test's
#      pass/fail split discriminates the one-byte boundary and never a
#      broken instrument (the negative-result contract: a negative is a
#      claim and carries the same burden of proof as a positive one — a
#      gate that fails everything is a broken check, not a real fault).
#
# DOCTRINE (inherited from the registry / the U02-U08 attack-fixture
# family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory option metadata over the gate-law
#     strings, nothing but the two-option law and its one adversarial byte;
#     nothing in this module can ever echo a secret because no secret is
#     ever read. The never-print self-test proves no pit-/Bearer-/
#     client-secret-shaped marker ever rides any surface.
#   - Fail-closed: a drifted authority, an unparseable picklist, a non-list
#     surface, a picklist that is not the exact one-option-wrong attack all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates —
#     the attack is a fixture the family's WRITE surfaces (dropdown_module,
#     --execute-gated) refuse, not a write this module performs.
#   - The decision-dropdown surface this fixture emulates is the public v2
#     custom-fields read (reg.CafClient.list_custom_fields) on a
#     Cloudflare-fronted host. Any module that TALKS to GoHighLevel /
#     Convert and Flow (services.leadconnectorhq.com, Cloudflare-fronted)
#     MUST carry the browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before
#     it ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is
#     the house pattern). THIS module makes NO network call — it ships the
#     offline adversarial fixture only; the client that DOES (reg.CafClient)
#     already sends CAF_BROWSER_UA on every request, and the self-test pins
#     BROWSER_UA == reg.CAF_BROWSER_UA so a registry regression is caught
#     HERE first.
#   - Move in silence; operator-verbose only. Nothing Anthropic in any
#     runtime file. Convert and Flow naming in every client surface.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden two-option control picklist is
#      internally consistent and byte-exact to the gate law; also self-test
#      / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (AF-AE-ATTACKBADDROPDOWN-* family, enforced
#      violation — a tamper NEVER masquerades as exit 1)
#   5  mismatch — the one-option-wrong attack fixture is REFUSED (payload
#      without --execute, the Trevor gate), the wrong-option picklist is
#      FAIL (verify_options), or the picklist drifted from the law — all
#      FAIL-CLOSED refusals, never a blind pass
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; payload / payload-true / verify ship ONLY with --execute):
#   attack_bad_dropdown.py plan                 # offline, NO --execute needed
#   attack_bad_dropdown.py payload --execute    # ship the wrong-option attack
#   attack_bad_dropdown.py payload-true --execute   # control: the golden picklist
#   attack_bad_dropdown.py verify --execute --picklist '[...]'  # judge a picklist
#   attack_bad_dropdown.py self-test            # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# attack_missing_hidden.py: sys.path.insert to scripts/ then
# `import anthology_registry as reg`; the decision law is read through
# u08_u09_modules.dropdown_module (the ONE owner of the decision key and
# the two-option law, itself byte-derived from gate_engine) and the
# adversarial spelling is pinned against u08_u09_modules.golden_review
# (the committed drift) — never re-implemented, never invented.
# =============================================================================
"""attack_bad_dropdown.py — the decision-dropdown-wrong-options attack
fixture that must FAIL.

The adversarial sibling of the U08/U09 dropdown creator: a deterministic
two-option picklist for the PRD Section 4 universal-review DECISION field
(contact.anthology_review_decision) whose FIRST option byte is swapped to
the repo's own documented drifted spelling (approved_as_is — the exact byte
of golden_review.GOLDEN_DECISION, NOT one of the two gate actions), which
every byte-exact picklist gate must never pass and which this module's own
gates refuse fail-closed (exit 5) unless the operator passes --execute to
this CLI (the Trevor gate).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u08_u09
# siblings): the registry owns the Cloudflare browser-UA wiring + the
# exit-code contract + the masked-marker helper; the dropdown module owns
# the decision KEY and the two-option law (byte-derived from gate_engine,
# never re-implemented); the golden-review fixture owns the committed
# drifted decision spelling the attack rides. This module reuses all three,
# never re-implements any of them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u08_u09_modules.dropdown_module as dd  # noqa: E402
import u08_u09_modules.golden_review as grv  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a
# bad-dropdown attack (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
ATTACK_CONTRACT = "anthology-engine-attack-bad-dropdown"

# The Trevor gate: --execute is the ONLY flag that ships the attack fixture
# or certifies a judged picklist (the package-init doctrine, exactly as the
# sibling attack_missing_hidden.py enforces it). Without it every fixture
# surface is a REFUSAL — never a silent no-op, never a blind certification.
EXECUTE_FLAG = "--execute"

# The decision field KEY — the dropdown module's own pinned contract key
# (the field-map excludes the decision field by design, U8 note). Imported,
# never re-typed, so the attack can never drift from the creator it
# siblings.
DECISION_KEY = dd.DECISION_KEY

# The adversarial option byte — the REPO'S OWN DOCUMENTED DRIFT, hardcoded
# here and PINNED in the self-test against both authorities: it must equal
# golden_review.GOLDEN_DECISION byte-exact (the committed dashed spelling of
# the review decision value) and it must NOT be one of the two gate actions
# the decision dropdown must carry (approve_as_is / request_rewrite_with_
# notes — gate_engine s5_gate). A live picklist carrying this byte submits
# a decision value no gate action can consume. NEVER used to build a golden
# picklist — only to attack one.
ATTACK_OPTION = "approved_as_is"  # dashed — the golden-review fixture's value, NOT a dropdown option

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123") — the same guard the u04 form reader and the
# u08_u09 siblings ship. Every emitted surface is scanned against it before
# print (this module holds no secret, but the guard is house law).
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the decision
    law or the picklist drifted from the law, so NO fixture is shipped — a
    wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The decision-option law — read ONCE from the dropdown module (the ONE
# owner of the decision contract, itself byte-derived from gate_engine's
# s5_gate GateSpec: EXACTLY two actions, approve_as_is /
# request_rewrite_with_notes, asserted in gate_engine's self_test). Never a
# second implementation.
# ---------------------------------------------------------------------------
def _law() -> tuple:
    """The exact two-option decision law, byte-exact, from the dropdown
    module's authority. Raises FixtureError when the law is unavailable or
    not exactly two distinct non-empty options: the attack cannot be
    derived from an unavailable or drifted surface."""
    try:
        opts = dd._decision_option_law()
    except Exception as exc:  # noqa: BLE001 — a missing authority is a
        # refusal, never a guessed law
        raise FixtureError(
            "the decision-option law is unavailable (%s) — refusing to "
            "build an attack against a law we cannot read" % exc)
    if not isinstance(opts, tuple) or len(opts) != 2 or \
            len(set(opts)) != 2 or \
            not all(isinstance(o, str) and o.strip() for o in opts):
        raise FixtureError(
            "the decision-option law did not resolve to exactly two "
            "distinct non-empty options (got %r) — refusing to build an "
            "attack against a drifted law." % (opts,))
    return opts


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, law-shaped minus one byte.
# ---------------------------------------------------------------------------
def attack_options(law=None) -> tuple:
    """Build the attack picklist: the canonical two-option law from the
    SINGLE AUTHORITY (dropdown_module._decision_option_law, never a second
    implementation), checked against the two-option law (exactly two
    distinct non-empty options, and the FIRST option must not already be
    the adversarial spelling — the exact conflation a regression would
    produce), then the first option is swapped to ATTACK_OPTION, the second
    preserved byte-for-byte. A drifted law raises FixtureError — a wrong
    fixture is never shipped."""
    if law is None:
        law = _law()
    if not isinstance(law, tuple) or len(law) != 2 or len(set(law)) != 2 or \
            not all(isinstance(o, str) and o.strip() for o in law):
        raise FixtureError(
            "the law must be exactly two distinct non-empty options, got "
            "%r — refusing to attack an unparseable law." % (law,))
    if law[0] == ATTACK_OPTION or law[1] == ATTACK_OPTION:
        raise FixtureError(
            "the law already carries the adversarial option %r — the "
            "authority conflated the spellings; refusing to ship a "
            "double-swap attack." % ATTACK_OPTION)
    return (ATTACK_OPTION, law[1])


# The canonical attack picklist, derived ONCE at import from the decision
# law — fail-fast: a drifted authority breaks the import of the fixture
# itself, so the verifier that imports this module by name catches the drift
# first. A tuple of plain strings is immutable through every public route.
ATTACK_OPTIONS = attack_options()

# The golden control picklist, derived from the SAME authority — the pass
# side of the pass/fail split (a gate that fails everything is a broken
# instrument).
GOLDEN_OPTIONS = _law()


# ---------------------------------------------------------------------------
# The judge — verify_options: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _defects(picklist) -> tuple:
    """The two-option law checks, byte-exact: the picklist must be a list
    of exactly two DISTINCT non-empty strings, byte-equal to the law in
    order. Returns the list of defect names (empty == PASS). A non-list
    surface is a refusal (raised), never a verdict."""
    if not isinstance(picklist, list):
        raise FixtureError(
            "no picklist to judge — refusing to judge a non-list surface "
            "(never fabricated).")
    bad = []
    if len(picklist) != 2:
        bad.append("option-count-%d" % len(picklist))
        return tuple(bad)
    for i, opt in enumerate(picklist):
        if not isinstance(opt, str) or not opt.strip():
            bad.append("blank-option")
            break
    if len(set(picklist)) != 2:
        bad.append("duplicated-option")
    elif tuple(picklist) != GOLDEN_OPTIONS:
        bad.append("wrong-option")
    return tuple(bad)


def verify_options(picklist, *, out=None) -> int:
    """Judge a picklist against the two-option decision law.

    READ-ONLY and OFFLINE: the judged surface is whatever picklist the
    caller hands in — the canonical ATTACK_OPTIONS fixture, the
    GOLDEN_OPTIONS control, or a live picklist piped from a custom-fields
    read (this module never makes a network call — reg.CafClient is the
    only thing that ever talks to Convert and Flow, and it sends
    CAF_BROWSER_UA on every request, the proven CF-1010 edge fix). The
    judge is the explicit fail: on the wrong-option attack the verdict is
    FAIL, exit 5 (mismatch family), naming the wrong option and the
    expected one; on the true two-option golden picklist the verdict is
    PASS, exit 0. Other drift directions — reordered / extra / dropped /
    duplicated / blank — FAIL with their named defect; a non-list surface
    is a hard refusal (FixtureError), never a verdict.

    Report: ONE JSON object on stdout (option values are the two-option law
    strings themselves — public contract values, never a token; this
    fixture holds NO id surface at all, so there is nothing to mask),
    human notes on stderr. NEVER prints a token (it holds none: the
    fixture is pure in-memory option metadata)."""
    out = out or sys.stderr
    bad = _defects(picklist)
    ok = not bad
    detail = ("all decision-option checks pass: exactly two distinct "
              "non-empty options byte-equal to the law %s in order — the "
              "golden control PASSES this judge"
              % (", ".join(GOLDEN_OPTIONS)) if ok else (
                  "%d defect(s) against the two-option decision law: %s — "
                  "options found %r, expected exactly %r"
                  % (len(bad), ", ".join(bad), picklist,
                     list(GOLDEN_OPTIONS))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "decision_key": DECISION_KEY,
        "options": picklist,
        "expected_options": list(GOLDEN_OPTIONS),
        "option_count": len(picklist),
        "defects": list(bad),
        "detail": detail,
        "fail_closed": {
            "wrong_option_fails": True,
            "byte_exact_required": True,
            "note": "a decision picklist whose options are not byte-exact "
                    "to the two gate actions (approve_as_is / "
                    "request_rewrite_with_notes) is FAIL, exit 5 — never a "
                    "pass. An attack fixture that passes ANY picklist gate "
                    "is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-bad-dropdown] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-bad-dropdown] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def _emit_refusal(detail: str, out) -> int:
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": False,
        "verdict": "REFUSED",
        "options": None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    out.write("[attack-bad-dropdown] payload REFUSED: %s\n" % detail)
    return EX_MISMATCH


def payload(*, execute: bool = False, out=None) -> int:
    """The FAIL-CLOSED gate: ship the one-option-wrong attack picklist —
    but ONLY with the operator's explicit --execute (the Trevor gate,
    package-init doctrine: this module's CLI REFUSES the attack without it,
    the same discipline attack_missing_hidden.py and dropdown_module apply
    to their surfaces). Any drift — the authority conflating the spellings,
    a law with zero/three options, an unparseable law — is REFUSED with
    exit 5 (verdict REFUSED, ok False), never shipped. Returns the exit
    code; emits the ONE JSON report object on stdout, human notes on
    stderr. The shipped picklist carries only the two-option law strings
    and the one adversarial byte — public contract values, nothing live,
    nothing secret — so shipping it is harmless."""
    out = out or sys.stderr
    if not execute:
        return _emit_refusal(
            "the attack fixture ships only with --execute (the Trevor "
            "gate): pass --execute to THIS CLI to emit the wrong-option "
            "decision-dropdown attack; every other invocation is a "
            "refusal, never a silent no-op.", out)
    try:
        attack = attack_options()
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    if list(attack) != [ATTACK_OPTION, GOLDEN_OPTIONS[1]]:
        return _emit_refusal(
            "the attack fixture must be exactly the one-option-wrong "
            "picklist [%r, %r] (the FIRST option swapped to the "
            "adversarial spelling, the second preserved), got %r — the "
            "fixture drifted; refusing."
            % (ATTACK_OPTION, GOLDEN_OPTIONS[1], list(attack)), out)
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "execute": True,
        "execute_required": True,
        "decision_key": DECISION_KEY,
        "options": list(attack),
        "expected_options": list(GOLDEN_OPTIONS),
        "wrong_option": ATTACK_OPTION,
        "option_count": 2,
        "detail": "wrong-option attack fixture derived byte-exact from the "
                  "decision-option law (dropdown_module, itself the "
                  "gate_engine s5_gate vocabulary), the FIRST option "
                  "swapped %r -> %r, the second preserved byte-for-byte: "
                  "the picklist that MUST FAIL every byte-exact "
                  "decision-dropdown gate (a submitted decision value no "
                  "gate action can consume)."
                  % (GOLDEN_OPTIONS[0], ATTACK_OPTION),
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, execute: bool = False, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE two-option
    golden picklist must PASS exit 0 — so a payload gate that fails
    EVERYTHING (a broken instrument) is never mistaken for a real
    one-option-wrong discrimination. Derives the golden picklist via the
    decision law (never a second implementation) and pins the law on it: if
    the authority ever regresses (zero options, three options, the wrong
    option), the control REFUSES with exit 5 — a regression is caught HERE
    first. Also gated: the control is a fixture surface, and this module's
    fixtures only ship under --execute (the Trevor gate) — the pass side of
    the split is proven the same way the attack side is proven."""
    out = out or sys.stderr
    if not execute:
        return _emit_refusal(
            "the control fixture also ships only with --execute (the Trevor "
            "gate) — the pass side of the split is proven with the same "
            "gate as the attack side.", out)
    try:
        golden = _law()
    except FixtureError as exc:
        out.write("[attack-bad-dropdown] payload-true REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "options": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "execute": True,
        "execute_required": True,
        "decision_key": DECISION_KEY,
        "options": list(golden),
        "option_count": 2,
        "detail": "control: the true two-option golden picklist %s passes "
                  "exit 0 — the wrong-option attack fails by comparison, "
                  "never by a broken gate."
                  % ", ".join(golden),
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials, NO --execute required):
    what the attack swaps and why, straight from the decision law (the
    single source of truth — never a hardcoded list) and the committed
    drift it rides. ONE JSON object on stdout (the machine surface, the
    same convention the attack-fixture siblings use); human notes go to
    out (stderr). The payload is scanned against the credential shape
    before print: a hit REFUSES the surface rather than echo a token."""
    out = out or sys.stderr
    law = _law()
    payload_dict = {
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "decision_key": DECISION_KEY,
        "golden_options": list(law),
        "attack_option": ATTACK_OPTION,
        "wrong_option_source": "u08_u09_modules.golden_review.GOLDEN_DECISION "
                               "(the committed dashed decision spelling — "
                               "a REAL repo byte, never invented)",
        "option_count": 2,
        "second_option_preserved": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential, no "
                "--execute needed. The attack swaps the FIRST option of "
                "the decision picklist from %r to %r (the dashed spelling "
                "of golden_review.GOLDEN_DECISION, NOT one of the two gate "
                "actions), preserving the second byte-for-byte: the "
                "wrong-option picklist that MUST FAIL every byte-exact "
                "decision-dropdown gate. The attack itself ships only with "
                "--execute."
                % (law[0], ATTACK_OPTION),
    }
    dumped = json.dumps(payload_dict, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise FixtureError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    sys.stdout.write(dumped)
    sys.stdout.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: attack coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline the U02-U08
# attack siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-bad-dropdown] SELF-TEST FAILED "
                         "(AF-AE-ATTACKBADDROPDOWN-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    law = _law()

    # ---- the authorities are the single source of truth --------------------
    assert DECISION_KEY == "contact.anthology_review_decision", \
        "the decision key must be the dropdown module's pinned contract " \
        "key, got %r" % DECISION_KEY
    assert list(law) == ["approve_as_is", "request_rewrite_with_notes"], \
        "the decision law must be exactly the two gate actions in order, " \
        "got %r" % (law,)
    assert law == dd._decision_option_law(), \
        "the attack law must never drift from the dropdown module's law"
    # the adversarial spelling is the repo's OWN committed drift — pinned
    # against golden_review.GOLDEN_DECISION byte-exact (never an invented
    # byte), and it must NOT be one of the two gate actions (the exact
    # conflation a regression would produce)
    assert ATTACK_OPTION == grv.GOLDEN_DECISION, \
        "the attack option must equal golden_review.GOLDEN_DECISION " \
        "byte-exact (the committed dashed spelling), got %r" % ATTACK_OPTION
    assert ATTACK_OPTION not in law, \
        "the adversarial option must never enter the decision law"
    assert ATTACK_OPTION != law[0], \
        "the adversarial spelling must differ from the golden option"

    # ---- the canonical attack: 2 options, first swapped, second preserved --
    assert isinstance(ATTACK_OPTIONS, tuple) and len(ATTACK_OPTIONS) == 2, \
        "ATTACK_OPTIONS must be the tuple-frozen 2-option payload, got %d" \
        % len(ATTACK_OPTIONS)
    assert list(ATTACK_OPTIONS) == [ATTACK_OPTION, law[1]], \
        "the attack must swap the FIRST option and preserve the second " \
        "byte-for-byte, got %r" % (ATTACK_OPTIONS,)
    assert isinstance(GOLDEN_OPTIONS, tuple) and \
        list(GOLDEN_OPTIONS) == list(law), \
        "the golden control must equal the law byte-exact"
    # the canonical fixture can never be mutated through the surface
    before = list(ATTACK_OPTIONS)
    try:
        ATTACK_OPTIONS[0] = law[0]  # noqa: B034 -- deliberately attempted
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert list(ATTACK_OPTIONS) == before, \
        "the canonical fixture changed during the self-test"
    # attack_options() returns a fresh tuple: mutating it never touches the
    # canon
    copy_ = attack_options()
    assert list(copy_) == list(ATTACK_OPTIONS), \
        "attack_options() must rebuild the canonical attack"

    # ---- the judge: wrong-option read MUST FAIL, golden control MUST PASS --
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options(list(ATTACK_OPTIONS), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the wrong-option attack picklist must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the wrong-option read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["options"] == [ATTACK_OPTION, law[1]], \
        "the judge must report the picklist as judged, got %r" % \
        parsed["options"]
    assert parsed["expected_options"] == list(law), \
        "the judge must name the expected two gate actions"
    assert parsed["defects"] == ["wrong-option"], \
        "the attack must fail on the option law and NOTHING else, got %r" % \
        parsed["defects"]
    assert parsed["option_count"] == 2
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options(list(GOLDEN_OPTIONS), out=io.StringIO())
    assert rc == EX_OK, "the golden picklist must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert parsed["options"] == list(law) and parsed["defects"] == []

    # ---- the judge's other FAIL directions (all never a pass) --------------
    # 1. reordered (the law's options swapped) -> FAIL
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options(list(reversed(law)), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a reordered picklist must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["wrong-option"], \
        "the reordered read must fail on the option law"
    # 2. an extra third option -> FAIL on the count law
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options(list(law) + ["Third Action"], out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a three-option picklist must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["option-count-3"], \
        "the three-option read must fail on the count law"
    # 3. a dropped option (a one-option picklist) -> FAIL on the count law
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options([law[0]], out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a one-option picklist must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["option-count-1"], \
        "the one-option read must fail on the count law"
    # 4. a duplicated option (a two-entry list of the same byte) -> FAIL
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options([law[0], law[0]], out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a duplicated-option picklist must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["duplicated-option"], \
        "the duplicated read must fail on the duplicate law"
    # 5. a blank option -> FAIL (never a silent pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_options([law[0], "   "], out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a blank-option picklist must FAIL (exit 5), got %s" % rc
    assert "blank-option" in json.loads(buf.getvalue())["defects"]
    # 6. a non-list surface is a REFUSAL, never a verdict
    try:
        verify_options({"not": "a list"}, out=io.StringIO())
        raise AssertionError("a non-list picklist was NOT refused")
    except FixtureError:
        pass

    # ---- the fail-closed gates: attack REFUSED without --execute -----------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(execute=False, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "payload WITHOUT --execute must REFUSE (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "REFUSED" and parsed["ok"] is False, \
        "the no-execute payload must be REFUSED (the Trevor gate), got %s" \
        % parsed["verdict"]

    # -- and ships the exact one-option-wrong attack WITH it ----------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(execute=True, out=io.StringIO())
    assert rc == EX_OK, \
        "payload with --execute on the true law must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["options"] == [ATTACK_OPTION, law[1]], \
        "the attack payload must carry the one-option-wrong picklist"
    assert parsed["expected_options"] == list(law), \
        "the attack payload must name the expected gate actions"
    assert parsed["wrong_option"] == ATTACK_OPTION
    assert parsed["option_count"] == 2
    assert parsed["execute"] is True and parsed["execute_required"] is True
    assert parsed["contract"] == ATTACK_CONTRACT
    assert parsed["decision_key"] == DECISION_KEY
    dumped = buf.getvalue()
    assert "pit-" not in dumped and "Bearer" not in dumped, \
        "the payload output must never carry a token shape"

    # the payload gate REFUSES under a conflated authority (never ships a
    # double-swap): the law itself carrying the adversarial spelling is the
    # exact regression the fixture pins shut
    saved = getattr(dd, "_decision_option_law")
    try:
        dd._decision_option_law = lambda: (ATTACK_OPTION, law[1])
        try:
            attack_options()
            raise AssertionError("a conflated law must be REFUSED")
        except FixtureError:
            pass
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload(execute=True, out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload under a conflated law must REFUSE (exit 5), got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
    finally:
        dd._decision_option_law = saved
    # after restore the payload ships again (the refusal was the drift, not
    # the instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(execute=True, out=io.StringIO())
    assert rc == EX_OK, \
        "payload must ship again after the law restored"

    # payload-true (the control): the true golden picklist passes exit 0 —
    # WITH the same --execute gate the attack ships under
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(execute=False, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "payload-true WITHOUT --execute must REFUSE (the Trevor gate), " \
        "got %s" % rc
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(execute=True, out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true with --execute on the true law must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["options"] == list(law) and parsed["option_count"] == 2

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. a one-option law -> refusal
    try:
        attack_options((law[0],))
        raise AssertionError("a one-option law was NOT refused")
    except FixtureError:
        pass
    # 2. a three-option law -> refusal
    try:
        attack_options(law + ("Third Action",))
        raise AssertionError("a three-option law was NOT refused")
    except FixtureError:
        pass
    # 3. a duplicated-option law -> refusal
    try:
        attack_options((law[0], law[0]))
        raise AssertionError("a duplicated-option law was NOT refused")
    except FixtureError:
        pass
    # 4. a blank-option law -> refusal
    try:
        attack_options((law[0], "  "))
        raise AssertionError("a blank-option law was NOT refused")
    except FixtureError:
        pass
    # 5. a law already carrying the adversarial option -> refusal (the
    #    double-swap)
    try:
        attack_options((ATTACK_OPTION, law[1]))
        raise AssertionError("a double-swap law was NOT refused")
    except FixtureError:
        pass
    # 6. a non-tuple law -> refusal
    try:
        attack_options([law[0], law[1]])
        raise AssertionError("a non-tuple law was NOT refused")
    except FixtureError:
        pass

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"
    assert dd.BROWSER_UA == reg.CAF_BROWSER_UA, \
        "the dropdown module's UA pin must stay the registry constant"

    # ---- never-a-token: no secret-shaped marker rides any surface ----------
    leak = " ".join(json.dumps({
        "options": list(ATTACK_OPTIONS),
        "expected": list(GOLDEN_OPTIONS),
        "decision_key": DECISION_KEY,
        "contract": ATTACK_CONTRACT}, sort_keys=True)
        + json.dumps({
            "plan": "offline", "golden_options": list(GOLDEN_OPTIONS),
            "attack_option": ATTACK_OPTION}, sort_keys=True))
    for marker in ("pit_", "Bearer ", "client_secret", "api_key",
                   "sk-", "AKIA", "gcp-service", "private-integration"):
        assert marker not in leak, \
            "the attack surface leaked a secret-shaped marker: %r" % marker

    # ---- plan: offline, no network, exact swap, NO --execute needed --------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["golden_options"] == list(law)
    assert p["attack_option"] == ATTACK_OPTION
    assert p["option_count"] == 2 and p["second_option_preserved"] is True
    assert p["dry_run"] is True and "pit-" not in buf.getvalue()

    dev.write("attack_bad_dropdown self-test: OK (decision law pinned "
              "contact.anthology_review_decision == the two gate actions "
              "approve_as_is / request_rewrite_with_notes byte-exact from "
              "gate_engine via dropdown_module; attack option pinned "
              "byte-exact to golden_review.GOLDEN_DECISION [approved_as_is "
              "-- the repo's own committed dashed drift, never invented] "
              "and proven NOT in the law; canonical 2-option tuple-frozen "
              "attack picklist with the FIRST option swapped and the "
              "second preserved, immutability + fresh-copy surface; judge "
              "FAILs the wrong-option read with exit 5 naming the wrong "
              "option while the golden control PASSES exit 0; reordered / "
              "extra / dropped / duplicated / blank reads FAIL with named "
              "defects, non-list surface refused; payload REFUSED without "
              "--execute (the Trevor gate) and ships the one-option-wrong "
              "attack with it, payload-true control PASSES the golden "
              "picklist under the same gate; conflated-law double-swap "
              "REFUSED then restores; 6 attack fixtures refused (one-"
              "option law / three-option law / duplicated law / blank law / "
              "double-swap law / non-tuple law); CAF_BROWSER_UA pinned; "
              "never-a-token; plan offline, no --execute)\n"
              % ())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_bad_dropdown.py",
        description="Attack fixture — decision dropdown wrong options, must "
                    "FAIL (Skill 59, U08/U09 tooling): the adversarial "
                    "sibling of dropdown_module.py, shipping the "
                    "deterministic one-option-wrong picklist for the PRD "
                    "Section 4 universal-review DECISION field "
                    "(contact.anthology_review_decision — the FIRST option "
                    "swapped to the repo's own committed dashed drift "
                    "approved_as_is, the second preserved byte-for-byte) "
                    "that every byte-exact picklist gate must refuse. The "
                    "attack ships and certifies ONLY with --execute (the "
                    "Trevor gate); every other invocation is a refusal.")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate: ship the attack fixture (payload "
                         "/ payload-true) or judge a piped picklist "
                         "(verify). Without it the attack is REFUSED — "
                         "never shipped, never certified.")
    ap.add_argument("--picklist", default=None,
                    help="picklist (JSON list of option strings) to judge "
                         "(verify); defaults to the first stdin line (e.g. "
                         "a live custom-fields read piped as "
                         "attack_bad_dropdown.py verify --execute).")
    ap.add_argument("cmd", nargs="?", choices=["payload", "payload-true",
                                               "verify", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling verifiers use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan()
        if args.cmd == "payload-true":
            return payload_true(execute=args.execute)
        if args.cmd == "verify":
            # The judge is a fail-closed surface in BOTH directions: without
            # --execute there is nothing to certify — the attack is never
            # judged by accident (the Trevor gate, package-init doctrine).
            if not args.execute:
                sys.stderr.write("[attack-bad-dropdown] verify REFUSED "
                                 "without --execute (the Trevor gate): pass "
                                 "--execute to judge a picklist against the "
                                 "two-option decision law.\n")
                return EX_MISMATCH
            raw = (args.picklist or sys.stdin.read().strip())
            if not raw:
                sys.stderr.write("[attack-bad-dropdown] no picklist given "
                                 "(--picklist or stdin) — nothing to "
                                 "judge.\n")
                return EX_ERR
            try:
                picklist = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[attack-bad-dropdown] the picklist on "
                                 "stdin is not valid JSON: %s\n" % exc)
                return EX_ERR
            return verify_options(picklist, out=sys.stderr)
        return payload(execute=args.execute)
    except FixtureError as exc:
        sys.stderr.write("[attack-bad-dropdown] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-bad-dropdown] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
