#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/negative_verifier.py  (U05 tooling)
# NEGATIVE VERIFIER — certify, fail-closed, that a submission does NOT fire the
# Intake Fire trigger. The universal-review submission (the PRD Section 4 / U8
# client decision form; slug "universal-review") must NEVER re-enter the intake
# front door: the Intake Fire trigger (the tag -> intake hook automation) fires
# ONLY when the submission identifies as the universal author-intake form
# (u02_modules/scope_check.py law). THIS module is the NEGATIVE mirror of that
# gate: it certifies "does not fire" with a typed basis, and REFUSES to certify
# anything else — a submission that identifies as the intake form (fires_intake
# True) or a shape that cannot be proven (INDETERMINATE) is never certified.
#
# WHY IT EXISTS (U05; MASTER-SPEC U02 item 5 "Intake Fire trigger scope"): the
# payload-side scope gate (scope_check.py) decides what MAY fire; this module
# decides what PROVABLY does NOT. The defect family it guards: the review form
# miswired to carry the intake form token (a review pick re-entering S0 as a
# new participant), the review submission forwarded under the intake source,
# or a filter/policy emptied so that everything certifies (the attack_unscoped
# empty-filter shape — an empty filter NEVER certifies anything here).
#
# THE LAW IS READ ONCE. This module does NOT re-implement the Intake Fire
# scope law: it imports u02_modules.scope_check and calls its check() — the
# single implementation (delta_reporter.py single-implementation doctrine;
# SPEC M8: a law read once, from the module that owns it). The trigger fires
# iff scope.check() returns ok True. Every refusal the law returns is then
# classified in the fail-closed direction: a refusal that is itself a PROOF
# (the trigger's gate deterministically refuses that payload) certifies
# does-not-fire; a refusal on a payload that presents intake identity, or on
# a broken/emptied policy, is REFUSED certification (INDETERMINATE — never
# fabricated, never blessed).
#
# CERTIFICATION CONTRACT (the whole point — fail-closed in BOTH directions):
#   verified True  <=> the Intake Fire trigger deterministically does NOT fire
#                      for this payload, proven by the shared scope law:
#                      basis not_a_dict / form_token_missing /
#                      form_token_unrecognized — the trigger's gate refuses
#                      those payloads outright, so they cannot fire. A payload
#                      carrying NO intake form token is not the intake form:
#                      the form token IS the trigger's scope key.
#   fires_intake True <=> the payload identifies as the universal author-intake
#                      form with an agreeing stage token -> the trigger FIRES
#                      -> the does-not-fire claim is FALSE (the FAIL this
#                      verifier exists to catch; AF-AE-NEGATIVE-INTAKE-FIRE).
#   INDETERMINATE (fires_intake None) <=> NEVER certified:
#                      stage_token_mismatch — the payload PRESENTS the intake
#                      form token; only the stage signal keeps the trigger
#                      from firing. That payload is intake identity, not the
#                      review submission under verification, and firing is
#                      UNDETERMINED — never blessed as does-not-fire.
#                      unknown — the scope policy is empty or malformed
#                      (stage_tokens / form_candidates emptied): a broken
#                      filter never certifies anything (the attack_unscoped
#                      empty-filter shape). The verifier's own pre-guard
#                      refuses before the law is even consulted.
#
# CREDENTIALS: NONE. This module holds no credential, resolves no env, makes
# NO HTTP request — it is a pure, deterministic predicate over ONE payload,
# exactly like its sibling scope_check.py. It never prints the payload or any
# field value; the ONLY payload-sourced value it ever surfaces is the verbatim
# form token (a form NAME — universal-intake / universal-review / title-select
# ... — never a credential, never PII, never a client identifier). The offline
# self-test asserts the report leaks nothing else.
#
# BROWSER UA (CF 1010 LAW): this module makes NO requests, so it needs no
# User-Agent — the rule is recorded here so a future caller that adds a live
# read keeps the discipline: every request to GoHighLevel / Convert and Flow
# (services.leadconnectorhq.com, Cloudflare-fronted) MUST ride reg.CafClient,
# which applies reg.CAF_BROWSER_UA on EVERY request — urllib's default
# "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it ever
# reaches the API (GK-09; the proven-live Podcast gate string, ported
# byte-for-byte in anthology_registry.py).
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY (json); calls
# NO model; never a client PII. Self-test failures are exit 4 (enforced
# violation, the AF-AE-NEGATIVE-ATTACK family) — a tamper never masquerades
# as exit 1.
#
# EXIT CODES (house convention 0/1/2/3/4/5; this module has NO network
# surface, so 3/HELD never occurs):
#   0  CERTIFIED does-not-fire (verified True)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — an empty/malformed scope policy (the empty-filter attack
#      shape) or CLI usage: a broken filter never certifies anything
#   5  verification FAILED — the submission FIRES Intake Fire (basis
#      in_scope), or certification REFUSED as INDETERMINATE (basis
#      stage_token_mismatch). Never a silent pass, never a fabricated one.
#   4  self-test FAILED (AF-AE-NEGATIVE-ATTACK family, enforced violation)
#
# USAGE (machine surface — ONE JSON report on stdout; human notes on stderr):
#   negative_verifier.py check [--stage-tokens a,b,c]
#                            [--form-candidates a,b,c]
#       reads ONE JSON payload on stdin; prints ONE JSON report on stdout;
#       exit 0 certified does-not-fire / 2 broken policy or usage / 5 fires
#       intake or INDETERMINATE. Empty stdin is a STOP, never a certification.
#   negative_verifier.py self-test         offline battery; exit 0 / 4
#   negative_verifier.py --help
#
# RETURN CONTRACT (the machine surface this module owns):
#   check(payload, *, stage_tokens=DEFAULT_STAGE_TOKENS,
#         form_candidates=DEFAULT_FORM_CANDIDATES) -> dict — the ONE report:
#     {"contract", "schema_version", "ok", "verified", "fires_intake",
#      "basis", "form_token", "intake_aliases", "stage_tokens",
#      "form_candidates", "note"}. ok True means CERTIFIED does-not-fire;
#      fires_intake True means the trigger fires (the negative claim is
#      FALSE); fires_intake None means INDETERMINATE — refused, never
#      fabricated. Never raises; never prints the payload or any field value
#      beyond the verbatim form token.
#   verify_exit(report) -> int — maps the ONE report onto the house exit
#      codes (0 / 2 / 5), deterministically.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery (no
#      network, no credential; exit 0 PASS / 4 enforced violation).
# =============================================================================
"""negative_verifier.py — U05 negative verifier: certify, fail-closed, that a
submission (the universal-review decision form) does NOT fire the Intake Fire
trigger. Pure, deterministic, credential-free: the scope law is imported from
u02_modules.scope_check (read once, never re-implemented), only the provable
does-not-fire refusals are certified, and no payload value is ever printed."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u02/u03/u04
# modules): the Intake Fire trigger scope law lives in
# u02_modules/scope_check.py — the payload-side gate that OWNS the trigger's
# scope. Imported by NAME, reused, NEVER re-implemented (SPEC M8 / the
# delta_reporter.py single-implementation doctrine: a law read once, from the
# module that owns it). scope_check is STDLIB-only and side-effect-free at
# import — no credentials, no network — so importing it cannot drag
# credential-resolution into this process.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import u02_modules.scope_check as scope  # noqa: E402  (the Intake Fire trigger scope law — read ONCE)

EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = 0, 1, 2, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract (mirrors the golden-fixture naming discipline).
NEGATIVE_CONTRACT = "anthology-engine-u05-negative-verify"
SCHEMA_VERSION = 1

# The engine's ONE client-facing decision form — the PRD Section 4 / U8
# cover-choice form (slug "universal-review"; forms_check.FORM_SLUGS /
# golden_forms.GOLDEN_FORM_SLUGS). The negative verifier certifies that THIS
# submission does not fire the Intake Fire trigger. The slug is pinned
# against the fixture authority in the offline self-test.
UNIVERSAL_REVIEW_FORM = "universal-review"

# The policy defaults — referenced from the scope law, never copied:
#   * the stage tokens the router treats as the universal intake form
#     (intake_router.py intake_stage_tokens: intake / s0 / s0_intake), and
#   * the candidate paths the law reads the form token along.
DEFAULT_STAGE_TOKENS = scope.DEFAULT_INTAKE_STAGE_TOKENS
DEFAULT_FORM_CANDIDATES = scope.FORM_CANDIDATE_PATHS

# The intake aliases the scope law recognizes — the form tokens that identify
# the universal author-intake form (scope_check._KNOWN_FORM_ALIASES: the
# canonical token plus the two engine spellings). REFERENCED, never copied, so
# a drift in the law is a drift here; the self-test pins the reference.
UNIVERSAL_INTAKE_ALIASES = scope._KNOWN_FORM_ALIASES  # the law's alias tuple


def _as_list(values):
    """A display list from a policy tuple. A bare string is ONE policy value
    (never iterated into characters); anything else is str()-mapped."""
    if isinstance(values, str):
        return [values]
    return [str(v) for v in values]


def _report(*, ok, verified, fires_intake, basis, form_token,
            intake_aliases, stage_tokens, form_candidates, note):
    """Build the ONE report dict. Never raises; never echoes a payload value
    beyond the verbatim form token (a form NAME — never a credential)."""
    return {
        "contract": NEGATIVE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "verified": verified,
        "fires_intake": fires_intake,
        "basis": basis,
        "form_token": form_token,
        "intake_aliases": sorted(str(a) for a in _as_list(intake_aliases)),
        "stage_tokens": _as_list(stage_tokens),
        "form_candidates": _as_list(form_candidates),
        "note": note,
    }


def check(payload, *, stage_tokens=DEFAULT_STAGE_TOKENS,
          form_candidates=DEFAULT_FORM_CANDIDATES) -> dict:
    """Certify, fail-closed, that a submission does NOT fire the Intake Fire
    trigger. Returns the ONE report dict (see the header RETURN CONTRACT).

    The proof is the shared scope law, never a guess: the trigger fires iff
    scope.check() returns ok True; the law's typed refusals are classified as
    follows.

      CERTIFIED does-not-fire (ok True, verified True, fires_intake False):
        not_a_dict / form_token_missing / form_token_unrecognized — the
        trigger's own gate deterministically refuses that payload, so it
        cannot fire. A payload carrying NO intake form token is not the
        intake form: the form token IS the trigger's scope key.

      FAILED verification (ok False, verified False, fires_intake True):
        in_scope — the payload identifies as the universal author-intake form
        with an agreeing stage token: the trigger FIRES. The does-not-fire
        claim is FALSE — the defect this verifier exists to catch.

      REFUSED certification — INDETERMINATE, never fabricated:
        stage_token_mismatch — the payload presents the intake form token;
        only the stage signal keeps the trigger from firing. That payload is
        intake identity (not the review submission under verification) and
        firing is UNDETERMINED — never blessed as does-not-fire.
        unknown — an empty or malformed policy (stage_tokens or
        form_candidates emptied): a broken filter never certifies anything
        (the attack_unscoped empty-filter shape). The verifier's own
        pre-guard refuses BEFORE the law is ever consulted.

    Never raises. Never prints the payload or any field value: the ONLY
    payload-sourced value in the report is the verbatim form token (a form
    NAME, never a credential)."""
    # -- the verifier's own fail-closed pre-guard ------------------------------
    # An EMPTIED candidate list would make the law read "no form token" and
    # certify does-not-fire for EVERYTHING — the empty-filter attack. A broken
    # policy never certifies: refuse INDETERMINATE before consulting the law.
    if not form_candidates or not stage_tokens:
        return _report(ok=False, verified=False, fires_intake=None,
                       basis="unknown", form_token=None,
                       intake_aliases=UNIVERSAL_INTAKE_ALIASES,
                       stage_tokens=stage_tokens,
                       form_candidates=form_candidates,
                       note="the scope policy is EMPTY or malformed "
                            "(stage_tokens / form_candidates emptied): a broken "
                            "filter never certifies does-not-fire. Fix the "
                            "policy and re-run.")

    ok_gate, flt = scope.check(payload, stage_tokens=stage_tokens,
                               form_candidates=form_candidates)
    basis = flt.get("reason") or "unknown"
    form_token = flt.get("form")  # verbatim form NAME or None; never a credential

    if ok_gate:
        # The law's gate PASSED: the submission IS the universal author-intake
        # form -> the Intake Fire trigger FIRES -> the negative claim is FALSE.
        return _report(ok=False, verified=False, fires_intake=True,
                       basis="in_scope", form_token=form_token,
                       intake_aliases=UNIVERSAL_INTAKE_ALIASES,
                       stage_tokens=stage_tokens,
                       form_candidates=form_candidates,
                       note="the payload identifies as the universal "
                            "author-intake form (%r): Intake Fire FIRES for "
                            "it. The does-not-fire claim is FALSE — the "
                            "review form is miswired or the payload carries "
                            "the intake token." % form_token)

    if basis == "stage_token_mismatch":
        return _report(ok=False, verified=False, fires_intake=None,
                       basis=basis, form_token=form_token,
                       intake_aliases=UNIVERSAL_INTAKE_ALIASES,
                       stage_tokens=stage_tokens,
                       form_candidates=form_candidates,
                       note="the payload PRESENTS the intake form token (%r) "
                            "but a stage token the intake gate refuses: "
                            "firing is UNDETERMINED — never certified as "
                            "does-not-fire. The payload is intake identity, "
                            "not the review submission under verification."
                            % form_token)

    if basis == "unknown":
        return _report(ok=False, verified=False, fires_intake=None,
                       basis=basis, form_token=form_token,
                       intake_aliases=UNIVERSAL_INTAKE_ALIASES,
                       stage_tokens=stage_tokens,
                       form_candidates=form_candidates,
                       note="the scope law could not classify the policy: "
                            "refused INDETERMINATE, never certified.")

    # not_a_dict / form_token_missing / form_token_unrecognized: the trigger's
    # own gate deterministically refuses this payload — it CANNOT fire. The
    # basis is named so the operator can audit exactly what was proven.
    return _report(ok=True, verified=True, fires_intake=False,
                   basis=basis, form_token=form_token,
                   intake_aliases=UNIVERSAL_INTAKE_ALIASES,
                   stage_tokens=stage_tokens,
                   form_candidates=form_candidates,
                   note="the Intake Fire trigger gate refuses this payload "
                        "(basis %s): it cannot fire. The refusal is the proof; "
                        "the basis is named for the operator to audit."
                        % basis)


def verify_exit(report: dict) -> int:
    """Map the ONE report onto the house exit codes, deterministically:
      0  certified does-not-fire (verified True)
      2  STOP — an empty/malformed scope policy (basis unknown; the
         empty-filter attack shape)
      5  verification FAILED (fires intake) or certification REFUSED
         (INDETERMINATE, never fabricated)
    A malformed report (no basis, no verdict) fails closed to 5 — a report
    that cannot be read never certifies anything."""
    if report.get("ok") is True and report.get("verified") is True:
        return EX_OK
    if report.get("basis") == "unknown":
        return EX_STOP
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; the same stdin seam the gateway transform
# uses — it pipes the form JSON on stdin).
# ---------------------------------------------------------------------------
USAGE = (
    "negative_verifier.py -- U05 negative verifier (Skill 59): certify,\n"
    "fail-closed, that a submission (the universal-review decision form)\n"
    "does NOT fire the Intake Fire trigger. The scope law is read once from\n"
    "u02_modules.scope_check; the report never echoes a payload value.\n"
    "\n"
    "  check [--stage-tokens a,b,c] [--form-candidates a,b,c]\n"
    "      reads ONE JSON payload on stdin; prints ONE JSON report on\n"
    "      stdout; exit 0 certified does-not-fire / 2 broken policy or\n"
    "      usage / 5 fires intake or INDETERMINATE (refused, never\n"
    "      certified). Empty stdin is a STOP, never a certification.\n"
    "  self-test                  offline battery; exit 0 / 4\n"
    "  --help                     this text\n"
)


def main(argv=None):
    """The CLI: check / self-test / --help. check reads ONE JSON payload on
    stdin and prints ONE JSON report on stdout. Empty stdin is a STOP, never
    a certification; an unparseable body follows the law's own not_a_dict
    refusal (certified does-not-fire — the trigger gate refuses it), never a
    crash. Never echoes the payload."""
    if argv is None:
        argv = sys.argv[1:]
    if "--self-test" in argv or (argv and argv[0] == "self-test"):
        return self_test()
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(USAGE)
        return EX_OK
    if argv and argv[0] == "check":
        argv = argv[1:]
    elif argv:
        sys.stderr.write("negative_verifier.py: unknown subcommand %r "
                         "(check | self-test | --help)\n" % argv[0])
        return EX_STOP

    stage_tokens = DEFAULT_STAGE_TOKENS
    form_candidates = DEFAULT_FORM_CANDIDATES
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--stage-tokens" and i + 1 < len(argv):
            stage_tokens = tuple(s.strip() for s in argv[i + 1].split(",") if s.strip())
            i += 2
        elif arg == "--form-candidates" and i + 1 < len(argv):
            form_candidates = tuple(s.strip() for s in argv[i + 1].split(",") if s.strip())
            i += 2
        else:
            sys.stderr.write("negative_verifier.py: unknown option %r\n" % arg)
            return EX_STOP

    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("negative_verifier.py: no payload on stdin (check "
                         "expects ONE JSON payload piped on stdin). Stopped.\n")
        return EX_STOP
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001 -- an unparseable body is the law's typed
        #                  not_a_dict refusal (T3 discipline), never a crash
        payload = None
    report = check(payload, stage_tokens=stage_tokens,
                   form_candidates=form_candidates)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return verify_exit(report)


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no credentials.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 4 (enforced violation — the AF-AE-NEGATIVE-ATTACK
    family; a tamper never masquerades as exit 1). The happy path writes the
    battery receipt to `out` and returns 0. Never touches the network; never
    prints a value from the fixtures beyond the form token."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[negative-verifier] SELF-TEST FAILED "
                         "(AF-AE-NEGATIVE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    """Offline acceptance battery: golden universal-review submissions are
    CERTIFIED does-not-fire; intake-claiming payloads FAIL with fires_intake
    True; stage-disagreeing and broken-policy shapes are REFUSED INDETERMINATE
    (never certified). All fixture data is synthetic — never a live id, never
    a live domain (the attack_bad_query synthetic-surface discipline)."""
    import u02_modules.golden_forms as golden  # the fixture authority (pure)

    # -- pins: the law and the fixtures are REFERENCED, never copied; a drift
    #    in either authority breaks THIS test first, fail-closed. --------------
    assert UNIVERSAL_REVIEW_FORM in golden.GOLDEN_FORM_SLUGS, (
        "the universal-review slug drifted from the golden forms authority: %r"
        % golden.GOLDEN_FORM_SLUGS)
    assert UNIVERSAL_INTAKE_ALIASES == ("universal-intake", "universal_intake",
                                        "intake"), (
        "the intake aliases drifted from the scope law: %r"
        % UNIVERSAL_INTAKE_ALIASES)
    assert scope.FORM_CANDIDATE_PATHS[0] == "form", (
        "the scope law's canonical form-token surface changed")
    assert DEFAULT_STAGE_TOKENS == scope.DEFAULT_INTAKE_STAGE_TOKENS, (
        "the stage-token policy drifted from the scope law")
    assert DEFAULT_FORM_CANDIDATES == scope.FORM_CANDIDATE_PATHS, (
        "the form-candidate policy drifted from the scope law")

    # -- golden: the universal-review submission does NOT fire intake ----------
    # Synthetic fixture data; the shape mirrors fixtures/webhook/t4-valid-
    # intake.json with the REVIEW form token (never a live id).
    golden_review = {"source": "anthology-intake", "location": "LOC-synthetic-RVW",
                     "form": UNIVERSAL_REVIEW_FORM, "contact_id": "C-9001",
                     "anthology_id": "A-9001", "stage": "s7_cover"}
    rep = check(golden_review)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["fires_intake"] is False, rep
    assert rep["basis"] == "form_token_unrecognized", rep
    assert rep["form_token"] == "universal-review", rep
    assert rep["intake_aliases"] == ["intake", "universal-intake",
                                     "universal_intake"], rep

    # -- the Convert and Flow / Flow customData list-of-{key,value} shape ------
    custom = {"source": "anthology-intake",
              "customData": [{"key": "form", "value": "universal-review"},
                             {"key": "stage", "value": "s7_cover"}]}
    rep = check(custom)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["basis"] == "form_token_unrecognized", rep

    # -- the data-envelope shape (data.form) ------------------------------------
    env = {"data": {"form": "universal-review", "stage": "s7_cover"}}
    rep = check(env)
    assert rep["ok"] is True and rep["verified"] is True, rep

    # -- ATTACK: the review submission smuggling the INTAKE form token ---------
    # The defect this verifier exists to catch: the review form miswired to
    # carry the intake form token (or forwarded under the intake source).
    # EVERY intake alias x EVERY intake stage token FIRES -> verification
    # FAILS with fires_intake True — never certified, never blessed.
    for alias in UNIVERSAL_INTAKE_ALIASES:
        for stage in DEFAULT_STAGE_TOKENS:
            rep = check(dict(golden_review, form=alias, stage=stage))
            assert rep["ok"] is False and rep["verified"] is False, rep
            assert rep["fires_intake"] is True, rep
            assert rep["basis"] == "in_scope", rep

    # -- stage disagreement: intake form token, non-intake stage ---------------
    # The payload PRESENTS intake identity; only the stage signal keeps the
    # trigger from firing -> INDETERMINATE, never certified as does-not-fire.
    rep = check(dict(golden_review, form="universal-intake",
                     stage="s4_blurb_outline"))
    assert rep["ok"] is False and rep["verified"] is False, rep
    assert rep["fires_intake"] is None, rep
    assert rep["basis"] == "stage_token_mismatch", rep

    # -- the law's typed refusals certify does-not-fire (proof, not guess) -----
    missing = {k: v for k, v in golden_review.items() if k != "form"}
    rep = check(missing)
    assert rep["ok"] is True and rep["basis"] == "form_token_missing", rep
    rep = check(dict(golden_review, form="   "))
    assert rep["ok"] is True and rep["basis"] == "form_token_missing", rep
    rep = check(dict(golden_review, form="contact-info-form"))
    assert rep["ok"] is True and rep["basis"] == "form_token_unrecognized", rep
    rep = check(["not", "a", "dict"])
    assert rep["ok"] is True and rep["basis"] == "not_a_dict", rep
    rep = check(None)
    assert rep["ok"] is True and rep["basis"] == "not_a_dict", rep

    # -- ATTACK: the EMPTIED policy (the attack_unscoped empty-filter shape) ---
    # An empty filter must NEVER certify: a broken policy is INDETERMINATE
    # (STOP at the CLI), never a does-not-fire pass.
    rep = check(golden_review, stage_tokens=[])
    assert rep["ok"] is False and rep["verified"] is False, rep
    assert rep["fires_intake"] is None, rep
    assert rep["basis"] == "unknown", rep
    rep = check(golden_review, form_candidates=())
    assert rep["ok"] is False and rep["fires_intake"] is None, rep
    assert rep["basis"] == "unknown", rep
    assert verify_exit(rep) == EX_STOP, verify_exit(rep)
    # A NON-empty policy still certifies (the policy, not its emptiness,
    # is the attack vector).
    rep = check(golden_review, stage_tokens=("intake", "s0", "s0_intake"),
                form_candidates=("form",))
    assert rep["ok"] is True and rep["verified"] is True, rep

    # -- the report never leaks a payload value ---------------------------------
    # Only the verbatim form token (a form NAME) may ever surface; the
    # contact/anthology ids, the location marker, and the payload body itself
    # must never appear in any report (never-a-token doctrine, payload side).
    for sample in (golden_review, custom, env,
                   dict(golden_review, form="universal-intake")):
        blob = json.dumps(check(sample))
        assert "C-9001" not in blob, "report leaked a contact id"
        assert "A-9001" not in blob, "report leaked an anthology id"
        assert "LOC-synthetic-RVW" not in blob, "report leaked the location marker"

    dev.write("negative_verifier self-test: OK (golden universal-review "
              "CERTIFIED does-not-fire; customData + data-envelope shapes; "
              "%d intake-alias x stage-token combinations FAIL fires_intake; "
              "stage-disagreement REFUSED INDETERMINATE; 5 typed refusals "
              "certified by the law; emptied policy REFUSED never certifies; "
              "report values never echoed)\n"
              % (len(UNIVERSAL_INTAKE_ALIASES) * len(DEFAULT_STAGE_TOKENS)))


if __name__ == "__main__":
    sys.exit(main())
