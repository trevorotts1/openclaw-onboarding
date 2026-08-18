#!/usr/bin/env python3
"""test_negative_verifier.py -- offline unit tests for the U05 NEGATIVE-RESULT
VERIFIER (scripts/u05_modules/negative_verifier.py).

The module certifies, fail-closed, that a submission (the universal-review
decision form) does NOT fire the Intake Fire trigger. The proof is the shared
u02 scope law (u02_modules.scope_check.check), read once and never
re-implemented. These tests prove the same law from the test side: golden
universal-review submissions are CERTIFIED does-not-fire, every intake-claim
payload FAILS with fires_intake True, stage-disagreeing and broken-policy
shapes are REFUSED INDETERMINATE (never certified), and the CLI honors the
same verdicts with house exit codes.

Fail-closed, BOTH directions, and the split always discriminates:
  - the golden control (the review submission) certifies does-not-fire, so a
    verifier that fails EVERYTHING (a broken instrument) is never mistaken
    for a real negative-result discrimination (the negative-result contract:
    a negative is a claim and carries the same burden of proof as a positive
    one);
  - EVERY intake alias x intake stage token combination FIRES (the defect
    this verifier exists to catch: a review submission smuggling the intake
    form token must never be blessed);
  - an EMPTIED policy (stage_tokens / form_candidates emptied) is the
    attack_unscoped empty-filter shape: a broken filter NEVER certifies
    anything, INDETERMINATE and STOP (exit 2), never a does-not-fire pass.

House doctrine (Skill 59, u05_modules/__init__.py):
  - Network-free and credential-free: no env var is read, no subprocess
    runs, reg.CafClient is NEVER constructed. The verifier itself is a
    pure, deterministic predicate over ONE payload and never raises.
  - Never a token printed: no test string carries a credential shape; the
    "pit-" and "Bearer" shapes never appear on any captured surface; the
    report may surface ONLY the verbatim form token (a form NAME — never a
    credential, never PII, never a client identifier); the self-test's
    leak scan (contact/anthology ids, location markers) is re-proven here
    against every report this battery captures.
  - Browser UA (CF 1010 law): CAF_BROWSER_UA is pinned as a browser
    User-Agent — urllib's default "Python-urllib/x.y" is 403'd at the
    Cloudflare WAF edge (CF error 1010) before it ever reaches Convert and
    Flow. The verifier makes NO request, so the law is proven at the
    constant surface (reg.CAF_BROWSER_UA and its u05_modules/house_rules
    mirror), never re-implemented here.
  - House test style: pytest with plain asserts; sys.path bootstrap
    identical to every other tests/ file; the exit-code convention
    (0/1/2/3/4/5) is asserted through the exported module constants, never
    hardcoded.
  - No foreign model-provider identifier in any runtime surface.

Run: python3 -m pytest 59-anthology-engine/scripts/u05_modules/test_negative_verifier.py -q
"""
import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))  # house bootstrap: scripts/ on sys.path

import anthology_registry as reg  # noqa: E402
import u02_modules.golden_forms as golden  # noqa: E402  (the form-slug fixture authority)
import u02_modules.scope_check as scope  # noqa: E402  (the Intake Fire scope law)
import u05_modules.negative_verifier as nv  # noqa: E402  (the module under test)

# The house exit-code convention — asserted by the exported constants, never
# re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u05 surface scans its output against.
# No test fixture ever carries one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# Synthetic fixture surface (the same discipline the module's self-test
# carries): never a live id, never a live domain. The review submission
# mirrors fixtures/webhook/t4-valid-intake.json with the REVIEW form token.
REVIEW_SUBMISSION = {"source": "anthology-intake",
                     "location": "LOC-synthetic-RVW",
                     "form": nv.UNIVERSAL_REVIEW_FORM,
                     "contact_id": "C-9001",
                     "anthology_id": "A-9001",
                     "stage": "s7_cover"}


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_verifier_self_test_passes_offline():
    """The verifier's own offline battery passes — exit 0, no network, no
    credential (the module runs its own golden + attack fixtures)."""
    rc = nv.self_test(out=io.StringIO())
    assert rc == EX_OK, "self-test must exit 0, got %s" % rc


def test_self_test_failure_is_an_enforced_violation_never_exit_1():
    """The self-test contract is exit 4 on a tamper — a tamper NEVER
    masquerades as exit 1 (unexpected error)."""
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)
    assert nv.EX_VIOLATION == EX_VIOLATION
    assert nv.EX_STOP == EX_STOP and nv.EX_MISMATCH == EX_MISMATCH


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """The module pins the house exit-code convention — asserted through the
    exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert (nv.EX_OK, nv.EX_ERR, nv.EX_STOP, nv.EX_MISMATCH) == (0, 1, 2, 5)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The law is a house
    constant, never optional (and the verifier makes NO request, so the
    constant surface is the only place the law is enforceable here)."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    # the u05 house-rules mirror must not drift from the registry's
    # proven-live string (byte-exact — a header, never a secret)
    import u05_modules.house_rules as house
    assert house.CAF_BROWSER_UA == reg.CAF_BROWSER_UA, (
        "the u05 mirror drifted from the registry's CAF_BROWSER_UA")


def test_u05_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface (fail-closed empty init)."""
    import u05_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()


def test_report_contract_is_fixed_and_stable():
    """The one fixed report contract: every report carries the same contract
    string and schema version, so a machine consumer can never mistake
    another JSON object for a negative-verify report (the surface contract
    is load-bearing)."""
    for payload in (REVIEW_SUBMISSION,
                    dict(REVIEW_SUBMISSION, form="universal-intake",
                         stage="intake"),
                    dict(REVIEW_SUBMISSION, form="universal-intake",
                         stage="s4_blurb_outline"),
                    {},
                    None):
        rep = nv.check(payload)
        assert rep["contract"] == nv.NEGATIVE_CONTRACT == \
            "anthology-engine-u05-negative-verify", rep
        assert rep["schema_version"] == nv.SCHEMA_VERSION == 1, rep


def test_scope_law_is_read_once_never_re_implemented():
    """The Intake Fire scope law is REFERENCED, never copied (SPEC M8 / the
    delta_reporter.py single-implementation doctrine): the verifier's policy
    defaults are the scope law's own constants, and the law's form slugs pin
    against the golden-forms fixture authority — a drift in any authority
    breaks THIS test first, fail-closed."""
    assert nv.DEFAULT_STAGE_TOKENS == scope.DEFAULT_INTAKE_STAGE_TOKENS == \
        ("intake", "s0", "s0_intake"), (
        "the stage-token policy drifted from the scope law")
    assert nv.DEFAULT_FORM_CANDIDATES == scope.FORM_CANDIDATE_PATHS, (
        "the form-candidate policy drifted from the scope law")
    assert scope.FORM_CANDIDATE_PATHS[0] == "form", (
        "the scope law's canonical form-token surface changed")
    assert nv.UNIVERSAL_INTAKE_ALIASES == scope._KNOWN_FORM_ALIASES == \
        ("universal-intake", "universal_intake", "intake"), (
        "the intake aliases drifted from the scope law")
    assert nv.UNIVERSAL_REVIEW_FORM in golden.GOLDEN_FORM_SLUGS, (
        "the universal-review slug drifted from the golden-forms authority: %r"
        % golden.GOLDEN_FORM_SLUGS)


# ---------------------------------------------------------------------------
# Golden: the universal-review submission does NOT fire intake
# ---------------------------------------------------------------------------
def test_golden_review_submission_is_certified_does_not_fire():
    """The golden universal-review submission (the PRD Section 4 / U8 client
    decision form) is CERTIFIED does-not-fire: ok True, verified True,
    fires_intake False, and the basis names the typed proof (the intake
    gate's own refusal of the review form token)."""
    rep = nv.check(REVIEW_SUBMISSION)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["fires_intake"] is False, rep
    assert rep["basis"] == "form_token_unrecognized", rep
    assert rep["form_token"] == nv.UNIVERSAL_REVIEW_FORM == "universal-review", rep
    assert nv.verify_exit(rep) == EX_OK


def test_golden_custom_data_and_envelope_shapes_certify():
    """The Convert and Flow / Flow customData list-of-{key,value} shape and
    the data-envelope shape (data.form) certify the same way — the law reads
    the form token along every candidate path."""
    custom = {"source": "anthology-intake",
              "customData": [{"key": "form", "value": "universal-review"},
                             {"key": "stage", "value": "s7_cover"}]}
    rep = nv.check(custom)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["basis"] == "form_token_unrecognized", rep
    env = {"data": {"form": "universal-review", "stage": "s7_cover"}}
    rep = nv.check(env)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["basis"] == "form_token_unrecognized", rep


def test_typed_refusals_are_proof_and_certify_does_not_fire():
    """The law's typed refusals ARE the proof (the trigger's gate
    deterministically refuses those payloads, so they cannot fire): a missing
    form token, a whitespace-only token, a foreign form token, a non-dict
    payload, and None all certify does-not-fire with the basis named."""
    missing = {k: v for k, v in REVIEW_SUBMISSION.items() if k != "form"}
    rep = nv.check(missing)
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["basis"] == "form_token_missing", rep
    assert rep["form_token"] is None, rep
    rep = nv.check(dict(REVIEW_SUBMISSION, form="   "))
    assert rep["ok"] is True and rep["basis"] == "form_token_missing", rep
    rep = nv.check(dict(REVIEW_SUBMISSION, form="contact-info-form"))
    assert rep["ok"] is True and rep["basis"] == "form_token_unrecognized", rep
    rep = nv.check(["not", "a", "dict"])
    assert rep["ok"] is True and rep["basis"] == "not_a_dict", rep
    rep = nv.check(None)
    assert rep["ok"] is True and rep["basis"] == "not_a_dict", rep


# ---------------------------------------------------------------------------
# Attack: a submission carrying the INTAKE form token must NEVER certify
# ---------------------------------------------------------------------------
def test_every_intake_alias_times_stage_token_fires_intake():
    """The defect this verifier exists to catch: a review submission
    miswired to carry the intake form token (or forwarded under the intake
    source) FIRES Intake Fire. EVERY intake alias x EVERY intake stage token
    FAILS with fires_intake True, ok False, verified False, basis in_scope —
    never certified, never blessed."""
    for alias in nv.UNIVERSAL_INTAKE_ALIASES:
        for stage in nv.DEFAULT_STAGE_TOKENS:
            rep = nv.check(dict(REVIEW_SUBMISSION, form=alias, stage=stage))
            assert rep["ok"] is False and rep["verified"] is False, rep
            assert rep["fires_intake"] is True, rep
            assert rep["basis"] == "in_scope", rep
            assert nv.verify_exit(rep) == EX_MISMATCH


def test_intake_identity_with_foreign_stage_is_indeterminate_never_certified():
    """A payload that PRESENTS the intake form token under a non-intake
    stage is intake identity, not the review submission under verification:
    firing is UNDETERMINED — REFUSED (fires_intake None, basis
    stage_token_mismatch, exit 5), never blessed as does-not-fire."""
    rep = nv.check(dict(REVIEW_SUBMISSION, form="universal-intake",
                        stage="s4_blurb_outline"))
    assert rep["ok"] is False and rep["verified"] is False, rep
    assert rep["fires_intake"] is None, rep
    assert rep["basis"] == "stage_token_mismatch", rep
    assert rep["form_token"] == "universal-intake", rep
    assert nv.verify_exit(rep) == EX_MISMATCH


# ---------------------------------------------------------------------------
# Attack: the EMPTIED policy (the attack_unscoped empty-filter shape)
# ---------------------------------------------------------------------------
def test_emptied_stage_tokens_never_certify():
    """An EMPTIED stage-token policy is the attack_unscoped empty-filter
    shape: a broken filter never certifies does-not-fire. The verifier's own
    pre-guard refuses INDETERMINATE (basis unknown) BEFORE the law is even
    consulted — and the exit mapping STOPs (exit 2), never a pass."""
    rep = nv.check(REVIEW_SUBMISSION, stage_tokens=[])
    assert rep["ok"] is False and rep["verified"] is False, rep
    assert rep["fires_intake"] is None, rep
    assert rep["basis"] == "unknown", rep
    assert nv.verify_exit(rep) == EX_STOP


def test_emptied_form_candidates_never_certify():
    """An EMPTIED form-candidate policy refuses the same way — an empty
    candidate list would make the law read 'no form token' and certify
    does-not-fire for EVERYTHING (the empty-filter attack). Refused, never
    blessed."""
    rep = nv.check(REVIEW_SUBMISSION, form_candidates=())
    assert rep["ok"] is False and rep["verified"] is False, rep
    assert rep["fires_intake"] is None, rep
    assert rep["basis"] == "unknown", rep
    assert nv.verify_exit(rep) == EX_STOP


def test_non_empty_policy_still_certifies():
    """The policy, not its emptiness, is the attack vector: an explicit
    non-empty policy over the golden review submission still certifies
    does-not-fire (the golden control discriminates — the pass/fail split is
    never a broken instrument)."""
    rep = nv.check(REVIEW_SUBMISSION,
                   stage_tokens=("intake", "s0", "s0_intake"),
                   form_candidates=("form",))
    assert rep["ok"] is True and rep["verified"] is True, rep
    assert rep["fires_intake"] is False, rep
    assert nv.verify_exit(rep) == EX_OK


def test_check_never_raises_on_any_shape():
    """The check surface is a pure, deterministic predicate over ONE payload:
    never raises, never touches the network, never reads an env var — for
    golden, attack, malformed, and None shapes alike."""
    shapes = (REVIEW_SUBMISSION,
              dict(REVIEW_SUBMISSION, form="universal-intake"),
              ["not", "a", "dict"],
              "a bare string",
              42,
              None)
    for shape in shapes:
        rep = nv.check(shape)  # must not raise
        assert isinstance(rep, dict) and "basis" in rep, rep


# ---------------------------------------------------------------------------
# The report never leaks a payload value (never-a-token, payload side)
# ---------------------------------------------------------------------------
def test_report_never_leaks_payload_values():
    """Only the verbatim form token (a form NAME — never a credential, never
    PII) may surface: the synthetic contact id, the anthology id, and the
    location marker must never appear in any report, on any verdict. The
    credential shapes never appear anywhere on any surface."""
    samples = (REVIEW_SUBMISSION,
               {"customData": [{"key": "form", "value": "universal-review"},
                               {"key": "stage", "value": "s7_cover"}]},
               {"data": {"form": "universal-review", "stage": "s7_cover"}},
               dict(REVIEW_SUBMISSION, form="universal-intake"),
               dict(REVIEW_SUBMISSION, form="universal-intake",
                    stage="s4_blurb_outline"),
               {})
    for sample in samples:
        blob = json.dumps(nv.check(sample), indent=2, sort_keys=True)
        assert "C-9001" not in blob, "a report leaked the contact id"
        assert "A-9001" not in blob, "a report leaked the anthology id"
        assert "LOC-synthetic-RVW" not in blob, (
            "a report leaked the location marker")
        assert CREDENTIAL_SHAPE not in blob, "a report leaked a token shape"
        assert "Bearer" not in blob, "a report leaked a Bearer shape"


# ---------------------------------------------------------------------------
# The CLI surface (the stdin seam the gateway transform uses)
# ---------------------------------------------------------------------------
class _FakeStdin:
    """A one-shot stdin stand-in (the CLI reads stdin exactly once)."""

    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw


def _cli_check(raw, argv=("check",), env_ok=True):
    """Run the CLI check subcommand with `raw` piped on stdin; return
    (exit_code, stdout_text, stderr_text). Never touches the network."""
    real_in, real_out, real_err = sys.stdin, sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.stdin = _FakeStdin(raw)
        sys.stdout = out
        sys.stderr = err
        rc = nv.main(list(argv))
    finally:
        sys.stdin, sys.stdout, sys.stderr = real_in, real_out, real_err
    return rc, out.getvalue(), err.getvalue()


def test_cli_check_certifies_golden_review_submission():
    """check on the golden review submission: ONE JSON report on stdout, exit
    0 (certified does-not-fire), stderr silent on the happy path."""
    rc, out, err = _cli_check(json.dumps(REVIEW_SUBMISSION))
    assert rc == EX_OK, "CLI check must exit 0, got %s" % rc
    parsed = json.loads(out)
    assert parsed["ok"] is True and parsed["verified"] is True, parsed
    assert parsed["fires_intake"] is False, parsed
    assert parsed["contract"] == nv.NEGATIVE_CONTRACT, parsed
    assert err == "", "stderr must stay silent on the happy path"


def test_cli_check_fires_intake_exits_5():
    """check on an intake-claiming payload: the report says fires_intake
    True, and the CLI exits 5 (verification FAILED — never a silent pass)."""
    rc, out, _ = _cli_check(
        json.dumps(dict(REVIEW_SUBMISSION, form="universal-intake",
                        stage="intake")))
    assert rc == EX_MISMATCH, "fires-intake must exit 5, got %s" % rc
    parsed = json.loads(out)
    assert parsed["fires_intake"] is True and parsed["basis"] == "in_scope", parsed


def test_cli_check_indeterminate_exits_5():
    """check on a stage-disagreeing intake-identity payload: INDETERMINATE,
    exit 5 — certification REFUSED, never blessed."""
    rc, out, _ = _cli_check(
        json.dumps(dict(REVIEW_SUBMISSION, form="universal-intake",
                        stage="s4_blurb_outline")))
    assert rc == EX_MISMATCH, "INDETERMINATE must exit 5, got %s" % rc
    parsed = json.loads(out)
    assert parsed["fires_intake"] is None, parsed
    assert parsed["basis"] == "stage_token_mismatch", parsed


def test_cli_check_emptied_policy_stops_exit_2():
    """check with an EMPTIED policy is a STOP (exit 2), never a certification
    — a broken filter never certifies anything (the attack_unscoped
    empty-filter shape, honored at the CLI boundary too)."""
    rc, out, _ = _cli_check(json.dumps(REVIEW_SUBMISSION),
                            argv=("check", "--stage-tokens", ""))
    assert rc == EX_STOP, "emptied policy must STOP (exit 2), got %s" % rc
    parsed = json.loads(out)
    assert parsed["basis"] == "unknown", parsed
    assert parsed["verified"] is False and parsed["fires_intake"] is None, parsed


def test_cli_empty_stdin_is_a_stop_never_a_certification():
    """Empty stdin is a STOP, never a certification — a verifier with no
    payload to judge must never bless a negative claim."""
    rc, out, err = _cli_check("")
    assert rc == EX_STOP, "empty stdin must STOP (exit 2), got %s" % rc
    assert "no payload on stdin" in err, err


def test_cli_unparseable_body_follows_the_law_typed_refusal():
    """An unparseable body follows the law's own not_a_dict refusal (the
    trigger gate refuses it, so it cannot fire) — a typed verdict, never a
    crash (T3 discipline)."""
    rc, out, _ = _cli_check("{not json")
    assert rc == EX_OK, "an unparseable body certifies not_a_dict, got %s" % rc
    parsed = json.loads(out)
    assert parsed["ok"] is True and parsed["basis"] == "not_a_dict", parsed


def test_cli_unknown_subcommand_and_option_stop():
    """An unknown subcommand and an unknown option are usage errors: STOP
    (exit 2), never a crash, never a certification."""
    rc, _, err = _cli_check("", argv=("frobnicate",))
    assert rc == EX_STOP and "unknown subcommand" in err, err
    rc, _, err = _cli_check(json.dumps(REVIEW_SUBMISSION),
                            argv=("check", "--bogus-flag"))
    assert rc == EX_STOP and "unknown option" in err, err


def test_cli_help_and_self_test_are_offline():
    """--help prints usage and exits 0; self-test runs the offline battery
    (exit 0). Neither reads stdin, neither touches the network. The
    self-test receipt goes to stderr (the module's own convention: the
    receipt is a human note, the machine surface stays JSON on stdout)."""
    rc, out, _ = _cli_check("", argv=("--help",))
    assert rc == EX_OK and "negative_verifier" in out, out
    rc, out, err = _cli_check("", argv=("self-test",))
    assert rc == EX_OK, "self-test must exit 0, got %s" % rc
    assert "negative_verifier self-test: OK" in err, err
    assert out.strip() == "", (
        "self-test must not emit a JSON report on stdout")


# ---------------------------------------------------------------------------
# The verifier and its sibling fixtures agree (the U05 family contract)
# ---------------------------------------------------------------------------
def test_sibling_attack_fixtures_self_tests_pass_offline():
    """The U05 family's other offline batteries pass — the empty-filter
    attack fixture and the golden scoped fixture — so the negative verifier
    is tested against a green family (a red sibling is caught HERE first)."""
    import u05_modules.attack_unscoped as attack
    import u05_modules.golden_scoped as gscoped
    assert attack.self_test(out=io.StringIO()) == EX_OK
    assert gscoped.self_test(out=io.StringIO()) == EX_OK


def test_sibling_attack_shape_is_the_empty_filter_attack():
    """The attack_unscoped fixture IS the empty-filter attack this verifier
    refuses by policy: its payload gate ships exactly the one empty-filter
    read over the two-anthology synthetic ledger (matched_rows 2, never a
    full id on the surface)."""
    import u05_modules.attack_unscoped as attack
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = attack.payload(out=io.StringIO())
    assert rc == EX_OK
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "PASS"
    assert report["matched_rows"] == 2 and report["ledger_rows"] == 2
    assert report["row_markers"] == ["...beef", "...d00d"], (
        "every anthology id must be a masked last-4 marker, never full")
    assert attack.SCOPED_BOOK_ID not in buf.getvalue(), (
        "the fixture surface must never carry a full anthology id")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
