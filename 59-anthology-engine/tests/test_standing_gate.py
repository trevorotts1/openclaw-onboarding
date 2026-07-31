#!/usr/bin/env python3
"""test_standing_gate.py -- Item 2 (fleet approval gate: anthology) offline contract
tests for scripts/standing_gate.py.

WHY THIS TEST EXISTS: anthology_approved is a real column on fleet_standing and,
before this unit, nothing in the anthology engine ever read it. This suite is the
"real test" the parent SPEC item requires ("a rule with no test is a suggestion"):
it proves box_slug resolution order, credential resolution, the curl secret-hygiene
idiom (config on stdin, never argv), and -- most importantly -- the FAIL-CLOSED
contract: an unreachable endpoint, a non-200 reply, or a malformed/unexpected body
must all be treated as NOT approved, and reason_code must never be guessed when the
gate itself could not get a definite answer.

Hermetic: imports standing_gate.py directly (stdlib only). subprocess.run is
monkeypatched everywhere a curl call would otherwise fire, so this suite makes ZERO
real network calls and never reads or writes any real credential. Every test
isolates os.environ via monkeypatch.

Run: python3 -m pytest 59-anthology-engine/tests/test_standing_gate.py -q
"""
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import standing_gate  # noqa: E402

ENV_NAMES = (
    "FLEET_STANDING_BOX_SLUG", "FLEET_STANDING_GATE_HEADER", "FLEET_STANDING_GATE_SECRET",
    "OC_JSON",
)


def _clear_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# box_slug resolution: explicit env -> openclaw.json env.vars -> hostname.
# Identical precedence to update-skills.sh's fleet_standing_resolve_slug() --
# reusing a working convention rather than inventing a second one.
# ---------------------------------------------------------------------------
def test_box_slug_explicit_env_wins(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("FLEET_STANDING_BOX_SLUG", "explicit-box")
    oc_json = tmp_path / "openclaw.json"
    oc_json.write_text(json.dumps({"env": {"vars": {"FLEET_STANDING_BOX_SLUG": "from-config"}}}))
    monkeypatch.setenv("OC_JSON", str(oc_json))
    assert standing_gate.resolve_box_slug() == "explicit-box"


def test_box_slug_falls_back_to_openclaw_json(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    oc_json = tmp_path / "openclaw.json"
    oc_json.write_text(json.dumps({"env": {"vars": {"FLEET_STANDING_BOX_SLUG": "from-config"}}}))
    monkeypatch.setenv("OC_JSON", str(oc_json))
    assert standing_gate.resolve_box_slug() == "from-config"


def test_box_slug_falls_back_to_hostname_when_nothing_configured(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OC_JSON", str(tmp_path / "does-not-exist.json"))
    import socket
    expected = (socket.gethostname() or "").split(".")[0]
    assert standing_gate.resolve_box_slug() == expected


def test_box_slug_malformed_openclaw_json_never_crashes(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    oc_json = tmp_path / "openclaw.json"
    oc_json.write_text("{not json")
    monkeypatch.setenv("OC_JSON", str(oc_json))
    # must fall through to hostname, never raise
    assert isinstance(standing_gate.resolve_box_slug(), str)


# ---------------------------------------------------------------------------
# Credential resolution: reuses the legacy roster gate's already-propagated
# FLEET_STANDING_GATE_HEADER / FLEET_STANDING_GATE_SECRET -- proven live
# 2026-07-31 to be the SAME n8n credential that authenticates this endpoint.
# ---------------------------------------------------------------------------
def test_header_name_defaults_when_unset(monkeypatch):
    _clear_env(monkeypatch)
    name, value = standing_gate._resolve_header_auth()
    assert name == "X-Fleet-Standing-Secret"
    assert value == ""


def test_header_name_honors_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("FLEET_STANDING_GATE_HEADER", "X-Custom-Header")
    monkeypatch.setenv("FLEET_STANDING_GATE_SECRET", "sekrit")
    name, value = standing_gate._resolve_header_auth()
    assert name == "X-Custom-Header"
    assert value == "sekrit"


# ---------------------------------------------------------------------------
# Secret hygiene: the header value must ride in the curl CONFIG TEXT (piped to
# curl's stdin by the real caller), never in the argv list subprocess.run sees.
# ---------------------------------------------------------------------------
def test_curl_invocation_never_carries_the_secret_in_argv(monkeypatch):
    _clear_env(monkeypatch)
    seen = {}

    class FakeProc:
        stdout = '{"ok":true}\n200'

    def fake_run(argv, input=None, capture_output=None, text=None, timeout=None):
        seen["argv"] = argv
        seen["input"] = input
        return FakeProc()

    monkeypatch.setattr(standing_gate.subprocess, "run", fake_run)
    body, code, err = standing_gate._curl_post_json(
        "https://example.invalid/webhook/x", {"a": 1}, "X-Test", "top-secret-value")
    assert err is None
    assert code == "200"
    assert "top-secret-value" not in seen["argv"], \
        "the secret value must never appear in the curl argv (ps exposure)"
    assert "top-secret-value" in seen["input"], \
        "the secret value must ride the curl config text via stdin, not vanish entirely"


def test_curl_output_without_status_line_is_malformed_not_a_crash(monkeypatch):
    _clear_env(monkeypatch)

    class FakeProc:
        stdout = "no newline at all"

    monkeypatch.setattr(standing_gate.subprocess, "run",
                        lambda *a, **k: FakeProc())
    body, code, err = standing_gate._curl_post_json(
        "https://example.invalid/x", {}, "X-Test", "v")
    assert body is None and code is None
    assert err is not None


def test_curl_transient_failure_retries_once_then_gives_up(monkeypatch):
    _clear_env(monkeypatch)
    calls = {"n": 0}

    class FakeProc:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(*a, **k):
        calls["n"] += 1
        return FakeProc("\n000")  # network-level failure every time

    monkeypatch.setattr(standing_gate.subprocess, "run", fake_run)
    body, code, err = standing_gate._curl_post_json(
        "https://example.invalid/x", {}, "X-Test", "v")
    assert calls["n"] == 2, "exactly one retry on a transient (000) failure, never more"
    assert code == "000"


def test_curl_deterministic_403_is_never_retried(monkeypatch):
    _clear_env(monkeypatch)
    calls = {"n": 0}

    class FakeProc:
        stdout = '{"ok":false}\n403'

    def fake_run(*a, **k):
        calls["n"] += 1
        return FakeProc()

    monkeypatch.setattr(standing_gate.subprocess, "run", fake_run)
    body, code, err = standing_gate._curl_post_json(
        "https://example.invalid/x", {}, "X-Test", "v")
    assert calls["n"] == 1, "a deterministic 403 must never be retried"
    assert code == "403"


# ---------------------------------------------------------------------------
# check_standing: the fail-closed contract. Every branch below must resolve to
# approved=False EXCEPT the one genuinely-approved shape.
# ---------------------------------------------------------------------------
def _stub_transport(monkeypatch, box_slug="test-box", secret="sekrit",
                    curl_return=(None, None, "not called")):
    _clear_env(monkeypatch)
    monkeypatch.setenv("FLEET_STANDING_BOX_SLUG", box_slug)
    monkeypatch.setenv("FLEET_STANDING_GATE_SECRET", secret)
    monkeypatch.setattr(standing_gate, "_curl_post_json", lambda *a, **k: curl_return)


def test_check_standing_approved_true(monkeypatch):
    _stub_transport(monkeypatch, curl_return=(
        json.dumps({"ok": True, "approved": True, "reason_code": ""}), "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is True
    assert r["reason_code"] == ""


def test_check_standing_refused_standing(monkeypatch):
    _stub_transport(monkeypatch, curl_return=(
        json.dumps({"ok": True, "approved": False, "reason_code": "standing"}), "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == "standing"


def test_check_standing_refused_not_enrolled(monkeypatch):
    _stub_transport(monkeypatch, curl_return=(
        json.dumps({"ok": True, "approved": False, "reason_code": "not_enrolled"}), "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == "not_enrolled"


def test_check_standing_fails_closed_on_network_error(monkeypatch):
    _stub_transport(monkeypatch, curl_return=(None, None, "curl invocation failed: TimeoutExpired"))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == "", "an infra failure must never invent a business reason"


def test_check_standing_fails_closed_on_non_200(monkeypatch):
    _stub_transport(monkeypatch, curl_return=('{"ok":false}', "500", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == ""


def test_check_standing_fails_closed_on_malformed_json(monkeypatch):
    _stub_transport(monkeypatch, curl_return=("not json at all", "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == ""


def test_check_standing_fails_closed_on_unexpected_shape(monkeypatch):
    # ok:true but no 'approved' key at all -- must never be treated as approved
    _stub_transport(monkeypatch, curl_return=(json.dumps({"ok": True}), "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == ""


def test_check_standing_never_guesses_a_reason_when_reason_code_missing(monkeypatch):
    # approved explicitly False but no recognized reason_code -- must not hedge
    _stub_transport(monkeypatch, curl_return=(
        json.dumps({"ok": True, "approved": False, "reason_code": "something_new"}), "200", None))
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert r["reason_code"] == "", \
        "an unrecognized reason_code must never be passed through as though it were trusted"


def test_check_standing_fails_closed_when_box_slug_unresolvable(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(standing_gate, "resolve_box_slug", lambda: "")
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False


def test_check_standing_fails_closed_when_secret_not_configured(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("FLEET_STANDING_BOX_SLUG", "test-box")
    r = standing_gate.check_standing("anthology")
    assert r["approved"] is False
    assert "not set" in r["note"].lower()


# ---------------------------------------------------------------------------
# notify_rejection: best-effort, correct body shape, never raises.
# ---------------------------------------------------------------------------
def test_notify_rejection_builds_expected_body(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("FLEET_STANDING_GATE_SECRET", "sekrit")
    seen = {}

    def fake_curl(url, body_obj, header_name, header_value, timeout=None):
        seen["url"] = url
        seen["body"] = body_obj
        return None, "200", None

    monkeypatch.setattr(standing_gate, "_curl_post_json", fake_curl)
    code, err = standing_gate.notify_rejection(
        "anthology", "test-box", "not_enrolled",
        client_label="Ada Lovelace", client_email="ada@example.test")
    assert err is None and code == "200"
    assert seen["url"] == standing_gate.NOTIFY_URL
    assert seen["body"] == {
        "system": "anthology", "box_slug": "test-box", "reason": "not_enrolled",
        "client_label": "Ada Lovelace", "client_email": "ada@example.test",
    }


def test_notify_rejection_omits_empty_optional_fields(monkeypatch):
    _clear_env(monkeypatch)
    seen = {}
    monkeypatch.setattr(standing_gate, "_curl_post_json",
                        lambda url, body_obj, *a, **k: seen.update(body=body_obj) or (None, "200", None))
    standing_gate.notify_rejection("anthology", "test-box", "")
    assert "client_label" not in seen["body"]
    assert "client_email" not in seen["body"]
    assert seen["body"]["reason"] == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
