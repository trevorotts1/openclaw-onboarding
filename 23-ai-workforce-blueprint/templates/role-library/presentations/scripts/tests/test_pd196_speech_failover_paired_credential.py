"""PD-TEST-196 -- the speech fallback must fail over the CREDENTIAL, not just the model.

THE DEFECT, MEASURED LIVE. `P9-SPEECH` was quarantined on `pres-operator-1d269693`
with an HTTP 401, and I reproduced the exact body on this box using the
department's own resolution path:

    OLLAMA_API_KEY (21 chars)     -> https://ollama.com/v1/chat/completions
        -> HTTP 401 {"error":{"message":"Unauthorized","type":"api_error",
                              "param":null,"code":null}}
    OPENROUTER_API_KEY (73 chars) -> https://openrouter.ai/api/v1/chat/completions
        -> HTTP 200 OK

`resolve_api_key()` returns the first NON-EMPTY name from a precedence list --
a string, never a WORKING credential -- and `resolve_base_url()` picks the
endpoint from a DIFFERENT list, so the two were chosen independently. The only
actual failover switched the MODEL while reusing the SAME `api_key`, so a 401
from a dead key was retried against the same endpoint with the same rejected
credential and could only fail again. A fallback that cannot change the
credential is not a fallback -- and a working key sat unused in the same
environment.

These tests pin the property that fixes it: every candidate is an
(endpoint, key) PAIR, and a credential is only ever sent to the service that
issued it.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import speech_build_harness as sbh  # noqa: E402


def _env(monkeypatch, **kw):
    for name in ("SPEECH_LLM_API_KEY", "SPEECH_LLM_BASE_URL", "OPENAI_BASE_URL",
                 "OLLAMA_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for k, v in kw.items():
        monkeypatch.setenv(k, v)


def test_the_primary_is_FIRST_so_the_happy_path_is_unchanged(monkeypatch):
    _env(monkeypatch, OLLAMA_API_KEY="oll-21-chars-here", OPENROUTER_API_KEY="or-73")
    c = sbh.resolve_candidates()
    assert c, "no candidates at all"
    label, url, key, _m = c[0]
    assert label == "primary"
    assert key == "oll-21-chars-here"
    assert url == sbh.resolve_base_url()


def test_the_openrouter_candidate_carries_ITS_OWN_endpoint_and_key(monkeypatch):
    """THE REGRESSION: the rejected key must never travel to the other endpoint."""
    _env(monkeypatch, OLLAMA_API_KEY="oll-dead", OPENROUTER_API_KEY="or-live")
    c = sbh.resolve_candidates()
    pairs = {x[0]: (x[1], x[2]) for x in c}
    assert "openrouter" in pairs, f"no openrouter candidate: {list(pairs)}"
    url, key = pairs["openrouter"]
    assert key == "or-live", "the OpenRouter candidate did not carry the OpenRouter key"
    assert key != "oll-dead", "the REJECTED key was reused -- the original defect"
    assert "openrouter.ai" in url, url
    assert "ollama.com" not in url, "the OpenRouter key would be sent to Ollama"


def test_no_alternative_key_means_no_phantom_candidate(monkeypatch):
    _env(monkeypatch, OLLAMA_API_KEY="only-one")
    c = sbh.resolve_candidates()
    assert len(c) == 1 and c[0][0] == "primary", c


def test_every_candidate_is_a_paired_endpoint_and_key(monkeypatch):
    """No candidate may borrow another service's endpoint."""
    _env(monkeypatch, OLLAMA_API_KEY="oll", OPENROUTER_API_KEY="or", OPENAI_API_KEY="oa")
    for label, url, key, _model in sbh.resolve_candidates():
        if key == "or":
            assert "openrouter.ai" in url, (label, url)
        if key == "oa":
            assert "api.openai.com" in url, (label, url)
        if key == "oll":
            assert "ollama.com" in url, (label, url)


def test_an_explicit_operator_override_still_wins_the_primary_slot(monkeypatch):
    """Back-compat: SPEECH_LLM_BASE_URL/KEY remain the operator's explicit choice."""
    _env(monkeypatch, SPEECH_LLM_API_KEY="mine", SPEECH_LLM_BASE_URL="https://my.gateway/v1")
    c = sbh.resolve_candidates()
    label, url, key, _m = c[0]
    assert label == "primary" and key == "mine"
    assert url.endswith("/chat/completions") and "my.gateway" in url, url


def test_each_fallback_carries_its_OWN_MODEL(monkeypatch):
    """MEASURED: a credential pair alone is not enough.

    Probing the operator's real store with the primary's Ollama model name
    against OpenRouter returned **HTTP 400** -- the key was accepted and the
    REQUEST was wrong. The same key with `deepseek/deepseek-chat` returns 200.
    So a candidate must carry a model valid for ITS endpoint.
    """
    _env(monkeypatch, OLLAMA_API_KEY="oll", OPENROUTER_API_KEY="or")
    by = {x[0]: x for x in sbh.resolve_candidates()}
    assert by["primary"][3] is None, "the primary must keep the caller's model"
    assert by["openrouter"][3] == "deepseek/deepseek-chat", by["openrouter"]
    # ...and the operator can override it
    _env(monkeypatch, OLLAMA_API_KEY="oll", OPENROUTER_API_KEY="or",
         SPEECH_LLM_FALLBACK_MODEL="my/model")
    by2 = {x[0]: x for x in sbh.resolve_candidates()}
    assert by2["openrouter"][3] == "my/model", by2["openrouter"]
