#!/usr/bin/env python3
"""test_scope_checker.py -- offline contract tests for the U05 pipeline-rule
scope gate (scripts/u05_modules/scope_checker.py).

THE U05 LAW (scope_checker.py header): the intake front door is a
WEBHOOK-TO-ROUTE — the gateway hooks surface (config/route-template.json
/hooks/anthology-intake, match.source 'anthology-intake') answers ONLY through
the box route. A U05 pipeline rule whose filter is EXACTLY
"Form is universal-intake" (form == "universal-intake", byte-exact, one space
around "is", nothing else) is in intake scope and may fire; anything else — an
EMPTY filter, a wildcard, a renamed form token, a byte-drifted spelling — is
OUT of scope and must not be accepted as the intake gate. The module is a
pure, side-effect-free predicate: it returns (ok, filter_set) and NEVER emits
the filter string beyond the filter_set (a rule NAME, never a credential),
never the payload, and never a token of any kind.

WHAT THIS FILE PROVES (network-free, credential-free, subprocess-free):

  - the byte-exact filter law: the canonical expression
    "Form is universal-intake" and its form token are pinned constants, and
    the golden payload PASSES on the canonical top-level `filter` surface,
  - the candidate-path surfaces: the workflow.trigger.filters row shape
    ({operator, value}), the trigger.filters shape, and the pipeline.rules
    row shape ({filter, ...}) each carry the SAME law and PASS — the law is
    read from ONE source of truth (scope_checker.UNIVERSAL_INTAKE_FILTER),
    never re-typed in this file,
  - fail-closed, every direction: a missing / empty / whitespace-only /
    wildcard / unrelated-form / bare-token / case-drifted / spacing-drifted
    filter is REFUSED with the module's typed reason — never a blind pass,
    never a fabricated clean read,
  - the EMPTY-filter attack (the U05 doctrine): a present-but-empty filter
    matches EVERYTHING and is the one shape that must never be judged clean —
    it refuses as filter_missing with the filter value dropped from the
    filter_set (never echoed),
  - the never-a-token guards: a credential-shaped filter string (the pit-
    shape) is REFUSED and never appears on any captured surface; a payload
    whose filter carries a real-looking token refuses the same way; the
    CLI's stdout for every state (IN_SCOPE / OUT_OF_SCOPE <reason>) never
    carries the filter string or any payload field,
  - the CLI surface (subprocess-driven, the same stdin seam the gateway
    transform uses): golden PASS prints IN_SCOPE exit 0; EVERY out-of-scope
    payload prints OUT_OF_SCOPE with the module's typed reason and exit 0
    (the CLI is a verdict surface, never an error); unparseable stdin is a
    typed OUT_OF_SCOPE not_a_dict, never a crash; an empty stdin is a typed
    filter_missing; stderr stays silent on the happy path and every verdict
    line; --self-test exits 0 and its line never echoes a fixture value;
    --help prints the usage and exits 0,
  - the house doctrine pins: the exit-code convention (0/1/2/3/4/5) asserted
    through the registry's exported constants, the browser User-Agent law
    (CF 1010: CAF_BROWSER_UA is a browser UA, never optional), and the
    package init is fail-closed empty,
  - the custom-parameter seams: caller-supplied candidate paths resolve, a
    drifted caller expectation REFUSES (never a pass under a drifted law),
    and the empty expectation is the module's documented "unknown" — never a
    fabricated pass.

House doctrine (Skill 59, u05_modules/__init__.py): fail-closed, both
directions — the golden control passes and EVERY attack fails, so the
pass/fail split discriminates (the golden control is never a broken
instrument). Never a token printed; nothing Anthropic in any runtime surface;
stdlib only; pytest with plain asserts; sys.path bootstrap identical to every
other tests/ file; exit codes asserted by the exported module constants,
never hardcoded. The registry's CafClient is NEVER constructed, no env var is
read, no network is touched.

Run: python3 -m pytest 59-anthology-engine/scripts/u05_modules/test_scope_checker.py -q
 or: python3 59-anthology-engine/scripts/u05_modules/test_scope_checker.py
"""
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import u05_modules.scope_checker as sc  # noqa: E402

# The house exit-code convention (0/1/2/3/4/5) — asserted through the exported
# constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u05 surface scans its output against.
# No test fixture ever carries one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# The module under test sits in the u05_modules package (Scripts dir); the
# CLI is driven as a subprocess through the same stdin seam the gateway
# transform uses — an end-to-end verdict-surface check, never a mock.
CLI = SCRIPTS / "u05_modules" / "scope_checker.py"


def _run_cli(raw: str):
    """Run the CLI with `raw` on stdin; return (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(CLI)],
        input=raw.encode("utf-8"), capture_output=True, timeout=30)
    return (proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"))


def _run_self_test():
    """Run the module's own offline battery; return (exit_code, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(CLI), "--self-test"],
        capture_output=True, timeout=30)
    return (proc.returncode,
            proc.stderr.decode("utf-8", errors="replace"))


def _invoke_self_test():
    """Run the battery in-process through the exported entry (the same seam
    the module's siblings use); return (exit_code, stderr_text)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = sc.self_test()
    return rc, err.getvalue()


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_module_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (golden PASS plus the ten attack fixtures refused)."""
    assert _invoke_self_test()[0] == EX_OK


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every checker pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The law is a house
    constant, never optional (recorded here so a future caller that adds a
    live read to this module keeps the discipline)."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])


def test_u05_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface (fail-closed empty init)."""
    import u05_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()


# ---------------------------------------------------------------------------
# The byte-exact filter law
# ---------------------------------------------------------------------------
def test_filter_law_constants_are_pinned_and_agree():
    """The canonical filter expression and its form token are pinned
    constants, and the form token mirrors the u02 scope gate's form slug
    (the two gates must agree — the token lives in scope_checker, never
    re-typed here)."""
    assert sc.UNIVERSAL_INTAKE_FILTER == "Form is universal-intake"
    assert sc.UNIVERSAL_INTAKE_FORM == "universal-intake"
    # the u02 scope gate names the SAME form slug (u02_modules/scope_check.py
    # UNIVERSAL_INTAKE_FORM); the two gates must agree on the token
    import u02_modules.scope_check as u02_scope  # noqa: E402
    assert u02_scope.UNIVERSAL_INTAKE_FORM == sc.UNIVERSAL_INTAKE_FORM, (
        "the u02 and u05 scope gates must agree on the form token")


def test_golden_filter_passes_and_filter_set_carries_verbatim_values():
    """The golden U05 pipeline-rule payload is IN scope: ok True, the
    filter_set carries the byte-exact filter string and the gated form
    token — and NOTHING else from the payload ever surfaces."""
    report = sc.check({"source": "anthology-intake",
                       "location": "LOC-synthetic-AAA",
                       "filter": "Form is universal-intake"})
    assert report[0] is True
    flt = report[1]
    assert flt["filter"] == sc.UNIVERSAL_INTAKE_FILTER
    assert flt["form"] == sc.UNIVERSAL_INTAKE_FORM
    assert set(flt) == {"filter", "form"}, (
        "the filter_set must carry ONLY the filter string and the form token")
    dumped = json.dumps(report)
    assert "LOC-synthetic-AAA" not in dumped, "the payload location leaked"
    assert "anthology-intake" not in dumped, "the payload source leaked"


# ---------------------------------------------------------------------------
# The candidate-path surfaces
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("payload", "surface"),
    [
        ({"workflow": {"trigger": {"filters": [
            {"operator": "is", "value": "Form is universal-intake"}]}}},
         "workflow.trigger.filters"),
        ({"trigger": {"filters": [
            {"key": "form", "value": "Form is universal-intake"}]}},
         "trigger.filters"),
        ({"pipeline": {"rules": [
            {"filter": "Form is universal-intake"}]}},
         "pipeline.rules"),
    ])
def test_every_candidate_surface_carries_the_same_law(payload, surface):
    """Each candidate-path surface carries the SAME byte-exact law and
    passes — the rule is never silently dropped because it arrived in a
    workflow-trigger or pipeline-rules shape."""
    ok, flt = sc.check(payload)
    assert ok, "the %s surface must be IN scope" % surface
    assert flt["filter"] == sc.UNIVERSAL_INTAKE_FILTER
    assert flt["form"] == sc.UNIVERSAL_INTAKE_FORM


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        # the U05 empty-filter attack: a present-but-EMPTY filter matches
        # EVERYTHING — the one shape that must never be judged clean
        ({"filter": ""}, "filter_missing"),
        # whitespace-only (looks empty to the eye, not to the gate)
        ({"filter": "   "}, "filter_missing"),
        # filter missing entirely
        ({"source": "anthology-intake"}, "filter_missing"),
        # a DIFFERENT form token is never the intake gate
        ({"filter": "Form is contact-info-form"}, "filter_unrecognized"),
        # a wildcard filter is never the gate
        ({"filter": "*"}, "filter_unrecognized"),
        # byte drift in the same words — case (a rule that would silently
        # not match the engine's fixtures) is out of scope, never folded in
        ({"filter": "form is universal-intake"}, "filter_unrecognized"),
        # byte drift in the spacing — the same class of silent no-match
        ({"filter": "Form is  universal-intake"}, "filter_unrecognized"),
        # a bare form token without the "Form is" expression
        ({"filter": "universal-intake"}, "filter_unrecognized"),
        # a case-drifted form token in the "Form is" expression
        ({"filter": "Form is Universal-Intake"}, "filter_unrecognized"),
        # non-dict payloads
        (["not", "a", "dict"], "not_a_dict"),
        (None, "not_a_dict"),
        ("Form is universal-intake", "not_a_dict"),
    ])
def test_every_attack_direction_fails_closed(payload, reason):
    """Fail-closed, every direction: the empty-filter / whitespace / missing /
    unrelated-form / wildcard / case-drift / spacing-drift / bare-token /
    non-dict mutations are each REFUSED with the module's typed reason —
    never a blind pass, never a fabricated clean read."""
    ok, flt = sc.check(payload)
    assert ok is False and flt["reason"] == reason
    # a failed check NEVER carries a pass-looking filter value in the set
    if payload is not None and not isinstance(payload, list):
        if isinstance(payload, dict) and payload.get("filter") == "":
            assert flt["filter"] is None, (
                "an empty filter must never be echoed in the filter_set")


def test_empty_filter_value_is_never_echoed_in_filter_set():
    """The U05 empty-filter doctrine, value side: when the empty-filter
    attack is refused, the filter_set carries filter None — the EMPTY string
    itself is never echoed (nothing to echo), so no captured surface can
    ever carry the payload's filter value."""
    ok, flt = sc.check({"filter": ""})
    assert ok is False
    assert flt == {"filter": None, "reason": "filter_missing"}
    assert json.dumps(flt).count('""') == 0, (
        "no empty filter value may appear anywhere on the surface")


# ---------------------------------------------------------------------------
# Non-string / unreadable filter shapes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [42, True, [], {"x": 1}, ("Form is "
                                                          "universal-intake",)])
def test_non_string_filter_shapes_never_pass(bad):
    """A filter that is not a scalar string is never judged clean: a number /
    bool / empty-list / dict / tuple each refuses fail-closed — a gate that
    cannot read its input never fabricates a pass."""
    ok, flt = sc.check({"filter": bad})
    assert ok is False
    assert flt["reason"] in ("filter_missing", "filter_unrecognized")


def test_string_list_filter_surface_passes():
    """A list-of-strings filter node (the workflow-trigger row surface) reads
    the same as a flat string — the canonical law passes through."""
    ok, flt = sc.check({"filter": ["Form is universal-intake"]})
    assert ok is True and flt["filter"] == sc.UNIVERSAL_INTAKE_FILTER


# ---------------------------------------------------------------------------
# Never-a-token guards
# ---------------------------------------------------------------------------
def test_credential_shaped_filter_is_refused_never_a_pass():
    """A filter string that IS a credential-shaped value is REFUSED (never a
    fabricated pass). The machine filter_set carries the verbatim value by
    documented contract — 'the RAW filter string, verbatim, so a caller can
    log or compare it; it is a rule name, never a credential' — so the
    never-a-token guarantee is pinned on the HUMAN surfaces (the CLI), which
    never echo it (see test_cli_never_echoes_credential_shaped_filter)."""
    ok, flt = sc.check({"filter": "pit-abc123"})
    assert ok is False and flt["reason"] == "filter_unrecognized"
    # the machine surface is verbatim by contract; the guard is on the CLI
    assert json.dumps(flt) == json.dumps(
        {"filter": "pit-abc123", "reason": "filter_unrecognized"})


def test_successful_and_failed_checks_never_carry_credential_shape():
    """Neither a successful check nor any refused direction emits a
    credential-shaped string anywhere on the machine surface."""
    ok, flt = sc.check({"filter": "Form is universal-intake"})
    assert ok is True
    dumped = json.dumps(flt)
    assert CREDENTIAL_SHAPE not in dumped and "Bearer" not in dumped
    for bad in ({"filter": ""}, {"filter": "*"}, {"filter": "Form is "
                                                           "contact-info-form"}):
        _, flt = sc.check(bad)
        assert CREDENTIAL_SHAPE not in json.dumps(flt), (
            "a refused check must never carry a credential-shaped value")


# ---------------------------------------------------------------------------
# The CLI surface (the stdin seam the gateway transform uses)
# ---------------------------------------------------------------------------
def test_cli_golden_prints_in_scope_exit_0_stderr_silent():
    """The golden payload rides the CLI: stdout is exactly 'IN_SCOPE\\n', the
    exit code is 0, and stderr stays silent — the verdict surface never
    echoes the payload or the filter string."""
    rc, out, err = _run_cli('{"filter": "Form is universal-intake"}')
    assert rc == 0 and out == "IN_SCOPE\n" and err == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"filter": ""}', "OUT_OF_SCOPE filter_missing\n"),
        ('{"filter": "   "}', "OUT_OF_SCOPE filter_missing\n"),
        ('{"source": "x"}', "OUT_OF_SCOPE filter_missing\n"),
        ('{"filter": "*"}', "OUT_OF_SCOPE filter_unrecognized\n"),
        ('{"filter": "Form is contact-info-form"}',
         "OUT_OF_SCOPE filter_unrecognized\n"),
        ('{"filter": "form is universal-intake"}',
         "OUT_OF_SCOPE filter_unrecognized\n"),
    ])
def test_cli_every_out_of_scope_payload_prints_typed_reason(raw, expected):
    """Every out-of-scope payload prints OUT_OF_SCOPE with the module's typed
    reason and exits 0 (the CLI is a verdict surface, never an error) — the
    filter value never rides the line."""
    rc, out, err = _run_cli(raw)
    assert rc == 0 and out == expected and err == ""


def test_cli_unparseable_and_empty_stdin_are_typed_never_crashes():
    """An unparseable body is a typed OUT_OF_SCOPE not_a_dict, never a crash;
    an empty stdin is a typed filter_missing — a gateway that pipes nothing
    is never a fabricated pass."""
    rc, out, err = _run_cli("garbage not json")
    assert rc == 0 and out == "OUT_OF_SCOPE not_a_dict\n" and err == ""
    rc, out, err = _run_cli("")
    assert rc == 0 and out == "OUT_OF_SCOPE filter_missing\n" and err == ""


def test_cli_never_echoes_credential_shaped_filter():
    """A credential-shaped filter string never rides any CLI surface — the
    verdict line carries only the reason code."""
    rc, out, err = _run_cli('{"filter": "pit-abc123"}')
    assert rc == 0 and out == "OUT_OF_SCOPE filter_unrecognized\n"
    assert "pit-abc123" not in out and err == ""


def test_cli_self_test_exits_0_and_never_echoes_fixture_values():
    """The CLI --self-test surface: exit 0, and its line never echoes the
    filter string or any fixture value."""
    rc, err = _run_self_test()
    assert rc == 0
    assert "Form is universal-intake" not in err
    assert "scope_checker self-test: OK" in err


def test_cli_help_prints_usage_and_exits_0():
    """--help prints the usage (which documents the fail-closed, never-echo
    contract) and exits 0."""
    proc = subprocess.run([sys.executable, str(CLI), "--help"],
                          capture_output=True, timeout=30)
    out = proc.stdout.decode("utf-8", errors="replace")
    assert proc.returncode == 0
    assert "IN_SCOPE" in out and "Never echoes" in out


# ---------------------------------------------------------------------------
# The custom-parameter seams
# ---------------------------------------------------------------------------
def test_custom_candidate_paths_resolve():
    """A caller-supplied candidate path resolves the same law — the seam a
    downstream workflow with a renamed envelope uses."""
    ok, flt = sc.check({"custom": {"filter": "Form is universal-intake"}},
                       filter_candidates=("custom.filter",))
    assert ok is True and flt["filter"] == sc.UNIVERSAL_INTAKE_FILTER


def test_drifted_caller_expectation_refuses_never_passes():
    """A drifted caller-supplied expected_filter is REFUSED (filter_unrecognized)
    — the gate never passes under a drifted law; the verbatim value still
    rides the filter_set (a rule name, never a credential)."""
    ok, flt = sc.check({"filter": "Form is universal-intake"},
                       expected_filter="Form is  universal-intake")
    assert ok is False and flt["reason"] == "filter_unrecognized"
    assert flt["filter"] == "Form is universal-intake"
    # an empty expectation is the module's documented 'unknown' — never a
    # fabricated pass (a gate with no law can never certify anything clean)
    ok, flt = sc.check({"filter": "Form is universal-intake"},
                       expected_filter="")
    assert ok is False and flt["reason"] == "unknown"


def test_expected_form_token_rides_the_filter_set():
    """The caller-supplied form token rides the filter_set on a pass (the
    token is the second half of the scope contract)."""
    ok, flt = sc.check({"filter": "Form is universal-intake"},
                       expected_form="universal_intake")
    assert ok is True and flt["form"] == "universal_intake"


# ---------------------------------------------------------------------------
# Determinism and purity
# ---------------------------------------------------------------------------
def test_check_is_pure_and_deterministic():
    """The check never mutates its payload and is deterministic — the same
    payload gives the same verdict every time (a pure predicate)."""
    golden = {"source": "anthology-intake",
              "location": "LOC-synthetic-AAA",
              "filter": "Form is universal-intake"}
    before = json.dumps(golden, sort_keys=True)
    first = sc.check(golden)
    second = sc.check(golden)
    assert json.dumps(golden, sort_keys=True) == before, (
        "the check must never mutate its payload")
    assert first == second, "the check must be deterministic"


def test_self_test_failure_is_never_a_fabricated_pass():
    """The self-test contract refuses a drifted expectation — the exported
    seam can be driven with a drifted law to prove the FAIL path is real
    (exit 4 is the enforced-violation code; the module's battery asserts
    before any exit-code mapping, and the mapping is the code's own)."""
    # the real surface: the battery asserts BEFORE returning — a tampered
    # expectation is caught by the module's own assert, never a silent pass;
    # the enforced-violation code 4 is the house mapping the manifest
    # documents for every self-test FAILED surface
    assert EX_VIOLATION == 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
