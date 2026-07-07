#!/usr/bin/env python3
"""test_webhook.py -- offline contract tests for the W1.6 webhook layer.

Covers config/route-template.json, fixtures/webhook/*, and
scripts/verify-webhook-t1-t9.sh WITHOUT a live gateway (the live T1..T9 battery
is executed and observed on the operator canary at W5.3). These tests are pure,
deterministic, and network-free: they assert the intake contract, the per-client
secret model, secret hygiene, and that no fixture leaks a credential-shaped key,
PII, or an Anthropic identifier.

Run: python3 -m pytest 59-anthology-engine/tests/test_webhook.py -q
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG = SKILL_DIR / "config"
FIX = SKILL_DIR / "fixtures" / "webhook"
ROUTE_TPL = CONFIG / "route-template.json"
ENGINE_CFG = CONFIG / "engine-config.template.json"
EXPECTED = FIX / "expected.json"
VERIFIER = SKILL_DIR / "scripts" / "verify-webhook-t1-t9.sh"
LABEL = "ANTHOLOGY_INTAKE_HOOK_SECRET"

# Anthropic-family id shapes assembled from fragments; no banned literal appears.
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)

JSON_FIXTURES = [
    "t4-valid-intake.json", "t5-duplicate-intake.json", "t6-wrong-tenant.json",
    "t7-stage-mismatch.json", "t3b-missing-ids.json", "t3-malformed-empty.json",
]
CRED_SHAPED_KEYS = {
    "api_key", "apikey", "openrouter_api_key", "authorization", "bearer",
    "token", "secret", "x-openclaw-token", "x-openclaw-webhook-secret",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def walk_strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_strings(v)
    elif isinstance(node, str):
        yield node


# --------------------------------------------------------------------------
# Presence.
# --------------------------------------------------------------------------
def test_owned_files_present():
    for p in [ROUTE_TPL, EXPECTED, VERIFIER, FIX / "README.md",
              FIX / "t3-malformed-notjson.txt"]:
        assert p.is_file(), "missing owned file: %s" % p
    for fn in JSON_FIXTURES:
        assert (FIX / fn).is_file(), "missing fixture: %s" % fn


# --------------------------------------------------------------------------
# Route template: surface + per-client secret model.
# --------------------------------------------------------------------------
def test_route_template_surface_is_gateway_core_hooks():
    route = load(ROUTE_TPL)
    assert route["surface"] == "gateway-core-hooks"


def test_hooks_token_is_a_secretref_never_inlined():
    route = load(ROUTE_TPL)
    tok = route["hooks"]["token"]
    # A SecretRef object, not a literal string value.
    assert isinstance(tok, dict), "hooks.token must be a SecretRef object, not an inline value"
    assert tok.get("source") == "env"
    assert tok.get("id") == LABEL
    # No key in the token object holds a literal secret-shaped value.
    assert "value" not in tok


def test_intake_mapping_shape():
    route = load(ROUTE_TPL)
    hooks = route["hooks"]
    assert hooks["allowRequestSessionKey"] is False
    intake = next(m for m in hooks["mappings"] if m["id"] == "anthology-intake")
    assert intake["match"]["path"] == "anthology-intake"
    assert intake["match"].get("source") is not None, "match.source needed for shared-box isolation"
    assert intake["deliver"] is False, "client-silent doctrine"
    assert intake["allowUnsafeExternalContent"] is False, "untrusted form content stays safety-wrapped"
    assert intake["transform"]["module"], "deterministic intake_router dispatch"


def test_route_secret_label_agrees_with_engine_config():
    route = load(ROUTE_TPL)
    engcfg = load(ENGINE_CFG)
    assert route["route_secret_label"] == LABEL
    assert engcfg["intake"]["route_secret_label"] == LABEL


def test_route_path_is_the_spec_path():
    route = load(ROUTE_TPL)
    assert route["route_path"] == "/hooks/anthology-intake"


# --------------------------------------------------------------------------
# expected.json coherence.
# --------------------------------------------------------------------------
def test_expected_covers_all_nine_tests():
    exp = load(EXPECTED)
    for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"):
        assert t in exp["tests"], "expected.json missing %s" % t


def test_expected_reasons_are_in_the_spec_enum():
    exp = load(EXPECTED)
    reasons = set(exp["valid_exception_reasons"])
    # The Exceptions.reason singleSelect enum (SPEC 7.3).
    assert reasons == {
        "unroutable_missing_ids", "unknown_anthology", "stage_mismatch",
        "tenant_mismatch", "legacy_reconciliation",
    }
    for t, spec in exp["tests"].items():
        r = spec.get("expect_exception_reason")
        if r is not None:
            assert r in reasons, "%s reason %r not in enum" % (t, r)


def test_expected_tenant_and_stage_reasons_are_correct():
    exp = load(EXPECTED)["tests"]
    assert exp["T6"]["expect_exception_reason"] == "tenant_mismatch"
    assert exp["T7"]["expect_exception_reason"] == "stage_mismatch"
    assert exp["T3"]["expect_exception_reason"] == "unroutable_missing_ids"


def test_expected_referenced_fixtures_exist():
    exp = load(EXPECTED)["tests"]
    for t, spec in exp.items():
        if spec.get("fixture"):
            assert (FIX / spec["fixture"]).is_file(), "%s -> missing %s" % (t, spec["fixture"])
        for fn in spec.get("fixtures", []) or []:
            assert (FIX / fn).is_file(), "%s -> missing %s" % (t, fn)


# --------------------------------------------------------------------------
# Fixtures: routing semantics.
# --------------------------------------------------------------------------
def test_valid_fixture_carries_the_hidden_routing_ids():
    t4 = load(FIX / "t4-valid-intake.json")
    for k in ("contact_id", "anthology_id", "stage"):
        assert t4.get(k), "valid intake fixture missing hidden id %s" % k
    assert t4["source"] == "anthology-intake"


def test_duplicate_fixture_is_identical_to_valid_for_dedup():
    t4 = load(FIX / "t4-valid-intake.json")
    t5 = load(FIX / "t5-duplicate-intake.json")
    assert t4 == t5, "duplicate fixture must share the T4 fingerprint exactly"


def test_wrong_tenant_fixture_location_differs_from_registry_binding():
    exp = load(EXPECTED)
    bound = exp["registry_bound_location"]
    t6 = load(FIX / "t6-wrong-tenant.json")
    assert t6["location"] != bound, "T6 must carry a mismatching tenant location"
    # And the matching fixtures share the bound location.
    for fn in ("t4-valid-intake.json", "t5-duplicate-intake.json", "t7-stage-mismatch.json"):
        assert load(FIX / fn)["location"] == bound


def test_missing_ids_fixture_omits_hidden_ids():
    t3b = load(FIX / "t3b-missing-ids.json")
    for k in ("contact_id", "anthology_id", "stage"):
        assert k not in t3b, "unroutable fixture must OMIT %s" % k


def test_malformed_notjson_fixture_is_not_valid_json():
    raw = (FIX / "t3-malformed-notjson.txt").read_text(encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


# --------------------------------------------------------------------------
# Security hygiene.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fn", JSON_FIXTURES)
def test_fixtures_carry_no_credential_shaped_key(fn):
    obj = load(FIX / fn)

    def scan(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert str(k).lower() not in CRED_SHAPED_KEYS, \
                    "fixture %s carries credential-shaped key %r (legacy api_key field is abolished)" % (fn, k)
                scan(v)
        elif isinstance(node, list):
            for v in node:
                scan(v)

    scan(obj)


@pytest.mark.parametrize("fn", JSON_FIXTURES + ["t3-malformed-notjson.txt"])
def test_fixtures_use_synthetic_emails_only(fn):
    text = (FIX / fn).read_text(encoding="utf-8")
    for addr in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        assert addr.endswith("@example.com") or addr.endswith(".invalid"), \
            "fixture %s carries a non-synthetic email %r" % (fn, addr)


def test_no_anthropic_identifier_in_owned_webhook_files():
    files = [ROUTE_TPL, EXPECTED, VERIFIER, FIX / "README.md",
             FIX / "t3-malformed-notjson.txt"] + [FIX / f for f in JSON_FIXTURES]
    for p in files:
        txt = p.read_text(encoding="utf-8", errors="replace")
        assert not BANNED.search(txt), "Anthropic-family id shape in %s" % p.name


def test_verifier_never_echoes_the_secret_value():
    """The script may READ the secret (as a Bearer header) but must never print
    it. No echo/printf of the secret variable, and it must report SET/NOT SET."""
    src = VERIFIER.read_text(encoding="utf-8")
    # It reports the label state.
    assert "SET" in src and "NOT SET" in src
    # It never expands the secret into an echo/printf/print statement.
    for pat in (r"echo[^\n]*\$\{?ANTHOLOGY_INTAKE_HOOK_SECRET",
                r"printf[^\n]*\$\{?ANTHOLOGY_INTAKE_HOOK_SECRET",
                r"print\(([^)]*)ANTHOLOGY_INTAKE_HOOK_SECRET"):
        assert not re.search(pat, src), "verifier appears to print the secret value (%s)" % pat
    # The Python side reads it into SECRET and comments that the value is never printed.
    assert "never printed" in src.lower()


# --------------------------------------------------------------------------
# Verifier executable behavior (offline).
# --------------------------------------------------------------------------
def _run(*args):
    return subprocess.run(
        ["bash", str(VERIFIER), *args],
        capture_output=True, text=True, timeout=60,
        cwd=str(SKILL_DIR),
    )


def test_verifier_bash_syntax_is_valid():
    r = subprocess.run(["bash", "-n", str(VERIFIER)], capture_output=True, text=True)
    assert r.returncode == 0, "bash -n failed: %s" % r.stderr


def test_verifier_self_test_passes_structurally():
    r = _run("--self-test")
    assert r.returncode == 0, "verifier --self-test failed:\n%s\n%s" % (r.stdout, r.stderr)
    assert "structure OK" in r.stdout


def test_verifier_plan_lists_all_nine_tests():
    r = _run("--plan")
    assert r.returncode == 0
    for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"):
        assert t in r.stdout, "plan output missing %s" % t


def test_verifier_dry_run_defers_battery_without_a_gateway():
    # Point at an unused port so no live gateway can answer; battery must DEFER,
    # not FAIL, and the run must exit 0 (structure sound).
    r = _run("--dry-run", "--base-url", "http://127.0.0.1:9")
    assert r.returncode == 0, "dry-run should exit 0 when structure is sound:\n%s" % r.stdout
    assert "DEFERRED" in r.stdout
    assert "FAIL" not in r.stdout.replace("0 FAIL", "")


def test_verifier_help_exits_zero():
    r = _run("--help")
    assert r.returncode == 0


def test_verifier_unknown_arg_is_usage_error():
    r = _run("--nope")
    assert r.returncode == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
