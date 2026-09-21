"""Ollama Cloud step-1 regression: the endpoint, the model tag and the key.

WHY THIS EXISTS (measured on a live client box, 2026-09-21 -- no credential
value was read or printed by the measurement):

  * `_attempt_ollama_cloud` POSTed to `_env("OLLAMA_CLOUD_URL",
    "https://ollama.com/api") + "/chat/completions"`. That path does not
    exist: ollama.com answers HTTP 404 `path "/api/chat/completions" not
    found`. The identical request body against
    https://ollama.com/v1/chat/completions answers HTTP 200 in 0.7s. Step 1
    of this module's documented chain -- the primary, cheap one -- had
    therefore never once succeeded on any box, and every persona-scoring call
    silently fell through to paid OpenRouter at ~4s a call.

  * The model tag `deepseek-v4-pro:cloud` was deleted from Ollama Cloud on
    2026-08-17 and every call for it failed silently. `GET
    https://ollama.com/api/tags` on 2026-09-21 lists exactly
    `deepseek-v4.1-flash`, `deepseek-v4-flash:0731` and
    `deepseek-v4-pro:0813`. A tag a provider can retire under us belongs in
    config, not in a constant, so both scoring model ids are env-overridable:
    OLLAMA_CLOUD_SCORING_MODEL and OPENROUTER_SCORING_MODEL.

  * The key `_env("OLLAMA_CLOUD_API_KEY")` resolves answered 401 on that box,
    while the key the OpenClaw gateway itself uses -- `models.providers.<name>
    .apiKey` for the provider whose baseUrl names ollama.com -- answered 200
    for the same request. The gateway's provider key is therefore tried as a
    LAST RESORT: when the env name resolves nothing, and when the first key
    comes back 401.

WHAT IS PINNED HERE:

  1. URL       -- the built URL is https://ollama.com/v1/chat/completions by
                  default AND when OLLAMA_CLOUD_URL still carries the old
                  https://ollama.com/api base. Any other override is honoured
                  verbatim.
  2. MODEL     -- the request body carries deepseek-v4.1-flash by default,
                  OLLAMA_CLOUD_SCORING_MODEL overrides it, step 2 defaults to
                  deepseek/deepseek-v4.1-flash with OPENROUTER_SCORING_MODEL
                  overriding, and the dead :cloud tag appears nowhere.
  3. FALLBACK  -- with no OLLAMA_CLOUD_API_KEY anywhere, the gateway's
                  provider key from openclaw.json is what gets sent.
  4. 401 RETRY -- a 401 on the env key retries exactly once, with the provider
                  key, and a 401 with no second key does not retry.
  5. REDACTION -- neither key ever appears in the returned dict, in its
                  reasoning or error string, or in env_report().
  6. CONTROL   -- an env-NAME in the apiKey field ("${OLLAMA_CLOUD_API_KEY}",
                  the bare SHOUTING_NAME) is NOT a credential and must not be
                  sent; with only that in openclaw.json, nothing resolves.

Every leg is hermetic: HOME is redirected into tmp_path and OPENCLAW_ROOT pins
the scratch installation, so no leg can read this box's real store or its real
openclaw.json. `_post_chat` is monkeypatched in every leg, so nothing here
touches the network.

    python3 -m pytest shared-utils/test_ollama_cloud_endpoint_and_key.py -q
"""
from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent          # .../shared-utils
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import llm_score  # noqa: E402

#: Values no real store carries. If either appears in a result or a report,
#: a credential leaked.
ENV_KEY = "sk-ollama-ENV-KEY-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
PROVIDER_KEY = "sk-ollama-GATEWAY-PROVIDER-KEY-SENTINEL-0123456789abcdef"

_SCRUB = (
    "OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN",
    "OLLAMA_CLOUD_URL", "OPENCLAW_SECRETS", "OC_ROOT", "OC_CONFIG",
    "OPENROUTER_API_KEY", "OLLAMA_CLOUD_SCORING_MODEL", "OPENROUTER_SCORING_MODEL",
)

_SCORE_REPLY = {
    "choices": [{"message": {"content": '{"score": 0.77, "reasoning": "ok"}'}}]
}


@pytest.fixture()
def box(tmp_path, monkeypatch):
    """A scratch installation: HOME redirected, OPENCLAW_ROOT pinned to it,
    every name these tests touch removed from the process environment.

    The PIN is what makes this hermetic on every host -- /data/.openclaw is an
    absolute candidate a redirected HOME cannot hide, and llm_score searches a
    pinned root and nothing else. Same harness as
    test_f25_llm_score_secrets.py::box.
    """
    home = tmp_path / "home"
    (home / ".openclaw" / "secrets").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENCLAW_ROOT", str(home / ".openclaw"))
    for name in _SCRUB:
        monkeypatch.delenv(name, raising=False)
    return home


def write_openclaw(home: Path, providers) -> Path:
    path = home / ".openclaw" / "openclaw.json"
    path.write_text(json.dumps({"models": {"providers": providers}}), encoding="utf-8")
    return path


def capture_posts(monkeypatch, replies):
    """Record every _post_chat call; answer from `replies` (a value or an
    exception per call, in order)."""
    calls = []

    def fake_post(url, headers, body, timeout=None):
        calls.append({"url": url, "headers": dict(headers), "body": dict(body)})
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm_score, "_post_chat", fake_post)
    return calls


def http_401():
    return urllib.error.HTTPError(
        "https://ollama.com/v1/chat/completions", 401, "Unauthorized", {}, None
    )


def test_the_box_fixture_cannot_reach_another_installation(box):
    """ANTI-VACUITY for the harness itself. With the pin set, nothing outside
    the scratch installation may be a candidate -- otherwise the 'nothing
    resolves' legs below could be measuring a real box."""
    candidates = llm_score._secret_store_files()
    assert candidates, "control: there must be candidates to inspect"
    outside = [p for p in candidates if not p.startswith(str(box) + "/")]
    assert not outside, f"scratch box can still reach {outside}"


# ---------------------------------------------------------------------------
# 1. URL
# ---------------------------------------------------------------------------

def test_default_url_is_v1_chat_completions(box):
    assert llm_score.ollama_cloud_chat_url() == "https://ollama.com/v1/chat/completions"


def test_old_api_base_is_normalised_to_v1(box, monkeypatch):
    """THE LEG THAT MATTERS FOR ALREADY-PROVISIONED BOXES. A box whose store
    or env still pins this module's OLD default must not be left POSTing to
    the 404 path."""
    monkeypatch.setenv("OLLAMA_CLOUD_URL", "https://ollama.com/api")
    assert llm_score.ollama_cloud_chat_url() == "https://ollama.com/v1/chat/completions"
    monkeypatch.setenv("OLLAMA_CLOUD_URL", "https://ollama.com/api/")
    assert llm_score.ollama_cloud_chat_url() == "https://ollama.com/v1/chat/completions"


def test_a_real_override_is_honoured_verbatim(box, monkeypatch):
    """CONTROL for the normalisation: it must rewrite the old default only,
    never hijack a deliberate override."""
    monkeypatch.setenv("OLLAMA_CLOUD_URL", "https://ollama.example/v1")
    assert llm_score.ollama_cloud_chat_url() == "https://ollama.example/v1/chat/completions"


# ---------------------------------------------------------------------------
# 2. MODEL
# ---------------------------------------------------------------------------

def test_request_body_carries_the_live_flash_tag(box, monkeypatch):
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])
    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is True and result["score"] == 0.77
    assert calls[0]["body"]["model"] == "deepseek-v4.1-flash"
    assert calls[0]["url"] == "https://ollama.com/v1/chat/completions"
    assert result["model"] == "ollama/deepseek-v4.1-flash"


def test_both_scoring_model_ids_are_env_overridable(box, monkeypatch):
    """A provider renaming a tag must be a config change on the box, never a
    code change and a fleet roll. That is the whole lesson of :cloud."""
    assert llm_score.ollama_cloud_model() == "deepseek-v4.1-flash"
    assert llm_score.openrouter_model() == "deepseek/deepseek-v4.1-flash"

    monkeypatch.setenv("OLLAMA_CLOUD_SCORING_MODEL", "deepseek-v4-pro:0813")
    monkeypatch.setenv("OPENROUTER_SCORING_MODEL", "deepseek/deepseek-v4-pro")
    assert llm_score.ollama_cloud_model() == "deepseek-v4-pro:0813"
    assert llm_score.ollama_cloud_model_id() == "ollama/deepseek-v4-pro:0813"
    assert llm_score.openrouter_model() == "deepseek/deepseek-v4-pro"

    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])
    result = llm_score._attempt_ollama_cloud("score this")
    assert calls[0]["body"]["model"] == "deepseek-v4-pro:0813"
    assert result["model"] == "ollama/deepseek-v4-pro:0813"


def test_the_override_resolves_from_the_secrets_store_too(box):
    """CONTROL: the overrides go through the same F25 chain as every other
    name, so a box that carries one in its store and nothing in its
    environment -- launchd, the openclaw cron -- still honours it."""
    store = box / ".openclaw" / "secrets" / ".env"
    store.write_text("OLLAMA_CLOUD_SCORING_MODEL=deepseek-v4-flash:0731\n",
                     encoding="utf-8")
    assert llm_score.ollama_cloud_model() == "deepseek-v4-flash:0731"


def test_the_deleted_cloud_tag_is_gone_from_the_module():
    """It was deleted upstream on 2026-08-17; a stray STRING LITERAL carrying
    it would put a box back on a model that cannot be served. The prose note
    recording the retirement is deliberately still allowed -- the pattern
    requires a closing quote right after the tag."""
    import re
    source = (_HERE / "llm_score.py").read_text()
    offenders = [line for line in source.splitlines()
                 if re.search(r"""deepseek-v4-pro:cloud["']""", line)]
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# 3. PROVIDER-KEY FALLBACK
# ---------------------------------------------------------------------------

def test_provider_key_is_used_when_the_env_key_is_empty(box, monkeypatch):
    write_openclaw(box, {"ollama": {"api": "ollama",
                                    "baseUrl": "https://ollama.com",
                                    "apiKey": PROVIDER_KEY}})
    assert llm_score._env("OLLAMA_CLOUD_API_KEY") == "", "control: no env key"
    assert llm_score.ollama_cloud_api_keys() == [PROVIDER_KEY]

    calls = capture_posts(monkeypatch, [_SCORE_REPLY])
    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is True
    assert calls[0]["headers"]["Authorization"] == f"Bearer {PROVIDER_KEY}"
    assert PROVIDER_KEY not in json.dumps(result)
    assert PROVIDER_KEY not in llm_score.env_report()


def test_providers_as_a_list_resolve_too(box):
    write_openclaw(box, [{"name": "ollama",
                          "baseUrl": "https://ollama.com/v1",
                          "apiKey": PROVIDER_KEY}])
    assert llm_score.ollama_cloud_api_keys() == [PROVIDER_KEY]


def test_a_provider_for_another_host_is_not_borrowed(box):
    """CONTROL: the baseUrl match is what selects the provider. Without this
    leg the fallback could be picking up any key in the file."""
    write_openclaw(box, {"openrouter": {"baseUrl": "https://openrouter.ai/api/v1",
                                        "apiKey": PROVIDER_KEY}})
    assert llm_score.ollama_cloud_api_keys() == []


def test_an_env_name_in_apikey_is_not_a_credential(box):
    """CONTROL for _is_literal_key: sending the literal string
    "${OLLAMA_CLOUD_API_KEY}" as a bearer token would just earn a 401."""
    for placeholder in ("${OLLAMA_CLOUD_API_KEY}", "$OLLAMA_CLOUD_API_KEY",
                        "OLLAMA_CLOUD_API_KEY", "env:OLLAMA_CLOUD_API_KEY", ""):
        write_openclaw(box, {"ollama": {"baseUrl": "https://ollama.com",
                                        "apiKey": placeholder}})
        assert llm_score.ollama_cloud_api_keys() == [], placeholder


def test_env_key_wins_and_provider_key_follows_it(box, monkeypatch):
    write_openclaw(box, {"ollama": {"baseUrl": "https://ollama.com",
                                    "apiKey": PROVIDER_KEY}})
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    assert llm_score.ollama_cloud_api_keys() == [ENV_KEY, PROVIDER_KEY]


# ---------------------------------------------------------------------------
# 4. 401 RETRY
# ---------------------------------------------------------------------------

def test_401_on_the_env_key_retries_once_with_the_provider_key(box, monkeypatch):
    """THE LIVE-BOX CASE. The resolved env key is rejected; the gateway's own
    key is the one that works."""
    write_openclaw(box, {"ollama": {"baseUrl": "https://ollama.com",
                                    "apiKey": PROVIDER_KEY}})
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    calls = capture_posts(monkeypatch, [http_401(), _SCORE_REPLY])

    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is True and result["score"] == 0.77
    assert len(calls) == 2, calls
    assert calls[0]["headers"]["Authorization"] == f"Bearer {ENV_KEY}"
    assert calls[1]["headers"]["Authorization"] == f"Bearer {PROVIDER_KEY}"
    blob = json.dumps(result)
    assert ENV_KEY not in blob and PROVIDER_KEY not in blob


def test_401_with_no_second_key_does_not_retry(box, monkeypatch):
    """CONTROL for the retry: one key means one attempt, and the failure is
    reported without either key in it."""
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    calls = capture_posts(monkeypatch, [http_401()])

    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is False
    assert len(calls) == 1, calls
    assert "401" in result["error"]
    assert ENV_KEY not in json.dumps(result)


def test_a_non_401_failure_does_not_burn_the_second_key(box, monkeypatch):
    """A 500 is the provider being down, not this key being wrong. Retrying
    would double every outage's cost for nothing."""
    write_openclaw(box, {"ollama": {"baseUrl": "https://ollama.com",
                                    "apiKey": PROVIDER_KEY}})
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", ENV_KEY)
    boom = urllib.error.HTTPError(
        "https://ollama.com/v1/chat/completions", 500, "Server Error", {}, None)
    calls = capture_posts(monkeypatch, [boom])

    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is False
    assert len(calls) == 1, calls


def test_no_key_anywhere_degrades_without_a_call(box, monkeypatch):
    """CONTROL. With nothing to send, the documented degraded answer, and no
    HTTPS attempt at all."""
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])
    result = llm_score._attempt_ollama_cloud("score this")
    assert result["ok"] is False
    assert result["model"] == "ollama/deepseek-v4.1-flash"
    assert calls == []
