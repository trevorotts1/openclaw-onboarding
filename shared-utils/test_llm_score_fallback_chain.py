"""The scoring fallback chain: order, key gating, the override, and redaction.

WHY THIS EXISTS. score_layer used to carry its chain as three hard-coded
lambdas, so the order, the models and the credential rules were all one
unreadable block and nothing could assert on them. The chain is now DATA
(llm_score.SCORING_CHAIN) walked by one transport (_attempt_chat), and this
file is what stops that table drifting away from the order the operator asked
for on 2026-09-21:

    1. ollama-cloud     minimax-m3                     measured 3.1s
    2. openrouter       minimax/minimax-m3
    3. agnes            agnes-3.0-flash  -> agnes-2.5-flash on 400/404
    4. deepseek-direct  deepseek-flash
    5. ollama-cloud     deepseek-v4.1-flash            measured 1.5s
    6. openrouter       google/gemini-3.1-flash-lite

WHAT IS PINNED HERE:

  1. ORDER      -- the default table, literally, and the order the steps are
                   actually attempted in when every credential resolves.
  2. KEY GATING -- a step whose key does not resolve opens NO socket, and the
                   chain advances past it. deepseek-direct is the worked
                   example: absent without its key, present with it.
  3. FIRST WIN  -- the first parseable 200 ends the walk; later steps are not
                   called.
  4. LABEL      -- the returned `model` names the winning STEP,
                   "<provider>/<model>", which is what persona_selection_log
                   records.
  5. OVERRIDE   -- LLM_SCORE_CHAIN replaces the table outright, splits on the
                   FIRST colon so a tagged Ollama id survives, and skips an
                   unknown provider with exactly one warning.
  6. AGNES      -- the 3.0 -> 2.5 retry fires on a model-not-found, reuses the
                   key that already authenticated, and happens at most once.
                   Control: a 500 does NOT trigger it.
  7. REDACTION  -- no sentinel key appears in any returned dict, in the cached
                   row, or on stderr in verbose mode.
  8. UNTOUCHED  -- the 30-day cache TTL, and the 20s per-step HTTP timeout.

Every leg is hermetic: HOME is redirected into tmp_path, OPENCLAW_ROOT pins
the scratch installation so no leg can read this box's real store or its real
openclaw.json, every credential name the chain reads is removed from the
process environment, and `_post_chat` is monkeypatched in every leg that would
make a call. Nothing here touches the network.

    python3 -m pytest shared-utils/test_llm_score_fallback_chain.py -q
"""
from __future__ import annotations

import json
import socket
import sys
import urllib.error
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent          # .../shared-utils
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import llm_score  # noqa: E402

#: Values no real store carries. If one of these shows up in a result, a
#: report or a log line, a credential leaked.
K_OLLAMA = "sk-ollama-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
K_OPENROUTER = "sk-or-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
K_AGNES = "sk-agnes-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
K_DEEPSEEK = "sk-deepseek-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
K_GATEWAY_AGNES = "sk-agnes-GATEWAY-PROVIDER-KEY-SENTINEL-0123456789ab"
ALL_SENTINELS = (K_OLLAMA, K_OPENROUTER, K_AGNES, K_DEEPSEEK, K_GATEWAY_AGNES)

#: Every name any step of the chain reads, plus the root pins. A name left in
#: the process environment would let a leg below reach a REAL credential and
#: make its "this step is skipped" assertion vacuous.
_SCRUB = (
    "OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN",
    "OLLAMA_CLOUD_URL",
    "OPENROUTER_API_KEY", "OPENROUTER_KEY", "OR_API_KEY", "OPEN_ROUTER_API_KEY",
    "AGNES_API_KEY", "AGNES_AI_API_KEY", "AGNES_KEY",
    "DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "DEEP_SEEK_API_KEY",
    "LLM_SCORE_CHAIN", "OLLAMA_CLOUD_SCORING_MODEL", "OPENROUTER_SCORING_MODEL",
    "OPENCLAW_SECRETS", "OC_ROOT", "OC_CONFIG",
)

_SCORE_REPLY = {
    "choices": [{"message": {"content": '{"score": 0.77, "reasoning": "ok"}'}}]
}

#: The order the operator asked for. Held here as a literal so a reordering of
#: SCORING_CHAIN has to be a deliberate edit in two places.
EXPECTED_DEFAULT_CHAIN = [
    ("ollama-cloud", "minimax-m3"),
    ("openrouter", "minimax/minimax-m3"),
    ("agnes", "agnes-3.0-flash"),
    ("deepseek-direct", "deepseek-flash"),
    ("ollama-cloud", "deepseek-v4.1-flash"),
    ("openrouter", "google/gemini-3.1-flash-lite"),
]


@pytest.fixture()
def box(tmp_path, monkeypatch):
    """A scratch installation: HOME redirected, OPENCLAW_ROOT pinned to it,
    every credential name the chain reads removed from the process env.

    The PIN is what makes this hermetic on every host -- /data/.openclaw is an
    absolute candidate a redirected HOME cannot hide, and llm_score searches a
    pinned root and nothing else. Same harness as
    test_ollama_cloud_endpoint_and_key.py::box.
    """
    home = tmp_path / "home"
    (home / ".openclaw" / "secrets").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENCLAW_ROOT", str(home / ".openclaw"))
    for name in _SCRUB:
        monkeypatch.delenv(name, raising=False)
    return home


def all_keys(monkeypatch):
    """Every step's credential present, so the walk is gated by nothing."""
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", K_OLLAMA)
    monkeypatch.setenv("OPENROUTER_API_KEY", K_OPENROUTER)
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    monkeypatch.setenv("DEEPSEEK_API_KEY", K_DEEPSEEK)


def write_openclaw(home: Path, providers) -> Path:
    path = home / ".openclaw" / "openclaw.json"
    path.write_text(json.dumps({"models": {"providers": providers}}),
                    encoding="utf-8")
    return path


def capture_posts(monkeypatch, replies):
    """Record every _post_chat call; answer from `replies` (a value or an
    exception per call, in order; the last entry repeats)."""
    calls = []

    def fake_post(url, headers, body, timeout=None):
        calls.append({"url": url, "headers": dict(headers), "body": dict(body)})
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm_score, "_post_chat", fake_post)
    return calls


def http_error(code: str, reason: str = "boom"):
    return urllib.error.HTTPError(
        "https://provider.example/chat/completions", code, reason, {}, None)


def score(persona_id: str = "chain-probe", **kwargs) -> dict:
    return llm_score.score_layer(
        persona_id=persona_id, layer="mission",
        persona_blueprint_summary="scratch", context="scratch",
        use_cache=False, **kwargs)


def models_called(calls) -> list:
    return [c["body"]["model"] for c in calls]


def test_the_box_fixture_cannot_reach_another_installation(box):
    """ANTI-VACUITY for the harness. With the pin set, nothing outside the
    scratch installation may be a store candidate -- otherwise the 'this step
    has no key' legs below could be measuring a real box."""
    candidates = llm_score._secret_store_files()
    assert candidates, "control: there must be candidates to inspect"
    outside = [p for p in candidates if not p.startswith(str(box) + "/")]
    assert not outside, f"scratch box can still reach {outside}"


# ---------------------------------------------------------------------------
# 1. ORDER
# ---------------------------------------------------------------------------

def test_the_default_chain_is_the_operators_order(box):
    assert llm_score.scoring_chain() == EXPECTED_DEFAULT_CHAIN


def test_the_ollama_backstop_follows_the_boxs_configured_tag(box, monkeypatch):
    """Step 5 is the one id a box owns. v25.1.55 made it config precisely so a
    retired tag is not a fleet roll, and the chain must honour that rather
    than restate the default."""
    monkeypatch.setenv("OLLAMA_CLOUD_SCORING_MODEL", "deepseek-v4-flash:0731")
    assert llm_score.scoring_chain()[4] == ("ollama-cloud", "deepseek-v4-flash:0731")


def test_the_backstop_tag_is_read_per_call_not_at_import(box, monkeypatch):
    """CONTROL for building the table in a function: a module constant would
    freeze whatever the environment held at import, which under launchd and
    the openclaw cron is nothing at all."""
    before = llm_score.scoring_chain()[4]
    monkeypatch.setenv("OLLAMA_CLOUD_SCORING_MODEL", "deepseek-v4-pro:0813")
    after = llm_score.scoring_chain()[4]
    assert before == ("ollama-cloud", "deepseek-v4.1-flash")
    assert after == ("ollama-cloud", "deepseek-v4-pro:0813")


def test_every_step_is_attempted_in_order_when_each_one_fails(box, monkeypatch):
    """THE ORDER LEG. A 500 from every provider walks the whole table, so the
    recorded calls ARE the order -- models and URLs both.

    500 and not 400/404 on purpose: those two are the Agnes model-not-found
    retry, which has its own leg below.
    """
    all_keys(monkeypatch)
    calls = capture_posts(monkeypatch, [http_error(500, "Server Error")])

    result = score()

    assert models_called(calls) == [m for _, m in EXPECTED_DEFAULT_CHAIN]
    assert [c["url"] for c in calls] == [
        "https://ollama.com/v1/chat/completions",
        "https://openrouter.ai/api/v1/chat/completions",
        "https://apihub.agnes-ai.com/v1/chat/completions",
        "https://api.deepseek.com/chat/completions",
        "https://ollama.com/v1/chat/completions",
        "https://openrouter.ai/api/v1/chat/completions",
    ]
    assert result["fallback"] is True
    assert result["score"] == llm_score.NEUTRAL_FALLBACK_SCORE
    assert "openrouter/google/gemini-3.1-flash-lite" in result["reasoning"], (
        "the degraded reasoning must name the LAST step tried")


def test_the_first_parseable_200_wins_and_later_steps_are_not_called(box, monkeypatch):
    all_keys(monkeypatch)
    calls = capture_posts(monkeypatch, [http_error(500), _SCORE_REPLY])

    result = score()

    assert result["score"] == 0.77 and result["fallback"] is False
    assert result["model"] == "openrouter/minimax/minimax-m3", (
        "the returned model must name the WINNING STEP, not a family")
    assert len(calls) == 2, models_called(calls)


def test_a_socket_timeout_on_a_step_advances_instead_of_killing_the_run(box, monkeypatch):
    """THE PYTHON 3.9 LEG. `socket.timeout` is an OSError on every version but
    a TimeoutError only from 3.10 — they were unified in 3.10. The per-step
    except tuple used to name TimeoutError without OSError, so on a 3.9 box an
    Ollama Cloud read timeout ESCAPED _attempt_chat, propagated out of
    pool.map in the selector's score_personas, and killed the whole persona
    selection (rc 1) instead of falling through to step 2.

    Raising the real `socket.timeout` is the point: on 3.10+ it IS
    TimeoutError and this passes either way, so the leg only has teeth
    alongside the control below, which proves the class relationship this fix
    turns on rather than assuming the runner's version.
    """
    all_keys(monkeypatch)
    calls = capture_posts(monkeypatch, [socket.timeout("timed out"), _SCORE_REPLY])

    result = score()

    assert result["score"] == 0.77 and result["fallback"] is False
    assert result["model"] == "openrouter/minimax/minimax-m3", (
        "step 2 must serve the score after step 1 times out")
    assert len(calls) == 2, models_called(calls)


def test_socket_timeout_is_an_oserror_which_is_why_the_tuple_names_oserror():
    """CONTROL for the leg above. It is OSError, not TimeoutError, that makes
    the handler catch a 3.9 socket.timeout — so assert the relationship the
    fix depends on. On 3.9 the second assert is the whole bug: socket.timeout
    is NOT a TimeoutError there, and a tuple naming only TimeoutError misses
    it.
    """
    assert issubclass(socket.timeout, OSError)
    if sys.version_info < (3, 10):
        assert not issubclass(socket.timeout, TimeoutError), (
            "on <3.10 socket.timeout must NOT be a TimeoutError — that is the "
            "defect this fix exists for")
    else:
        assert socket.timeout is TimeoutError


def test_every_transport_error_returns_a_dict_rather_than_raising(box, monkeypatch):
    """The whole chain must survive each transport failure class: a raise from
    any of these is what took the selector down, so none may escape.
    ConnectionResetError and OSError are OSErrors that are not TimeoutErrors
    on ANY version — they were never caught before this fix.
    """
    for exc in (socket.timeout("timed out"),
                ConnectionResetError("peer reset"),
                OSError("transport went away"),
                TimeoutError("slow")):
        all_keys(monkeypatch)
        calls = capture_posts(monkeypatch, [exc])
        result = score(persona_id=f"probe-{type(exc).__name__}")
        assert result["fallback"] is True, f"{exc!r} did not degrade cleanly"
        assert len(calls) == len(EXPECTED_DEFAULT_CHAIN), (
            f"{exc!r} stopped the chain after {len(calls)} step(s)")


def test_an_unparseable_200_advances_instead_of_winning(box, monkeypatch):
    """CONTROL for 'first 200 wins': a 200 whose body is not a score is not a
    win. Without this leg the chain could stop on the first reachable
    provider regardless of what it said."""
    all_keys(monkeypatch)
    junk = {"choices": [{"message": {"content": "I'd rather not."}}]}
    calls = capture_posts(monkeypatch, [junk, _SCORE_REPLY])

    result = score()

    assert result["model"] == "openrouter/minimax/minimax-m3"
    assert len(calls) == 2, models_called(calls)


# ---------------------------------------------------------------------------
# 2. KEY GATING -- a step with no key is skipped, silently and socket-free
# ---------------------------------------------------------------------------

def test_a_step_whose_key_does_not_resolve_is_skipped(box, monkeypatch):
    """Only OpenRouter has a credential, so ONLY its two steps may be tried."""
    monkeypatch.setenv("OPENROUTER_API_KEY", K_OPENROUTER)
    calls = capture_posts(monkeypatch, [http_error(500)])

    result = score()

    assert models_called(calls) == ["minimax/minimax-m3",
                                    "google/gemini-3.1-flash-lite"]
    assert result["fallback"] is True


def test_no_credential_anywhere_opens_no_socket_at_all(box, monkeypatch):
    """CONTROL. The documented degraded answer, and zero HTTPS attempts."""
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])

    result = score()

    assert calls == []
    assert result["fallback"] is True
    assert result["score"] == llm_score.NEUTRAL_FALLBACK_SCORE


def test_deepseek_direct_runs_only_when_its_own_key_resolves(box, monkeypatch):
    """THE WORKED EXAMPLE for key gating: the step most boxes cannot run."""
    calls = capture_posts(monkeypatch, [http_error(500)])
    assert llm_score.deepseek_direct_api_keys() == [], "control: no key"
    score(persona_id="deepseek-absent")
    assert llm_score.DEEPSEEK_DIRECT_CHAT_URL not in [c["url"] for c in calls]

    monkeypatch.setenv("DEEPSEEK_API_KEY", K_DEEPSEEK)
    calls2 = capture_posts(monkeypatch, [http_error(500)])
    score(persona_id="deepseek-present")

    deepseek = [c for c in calls2 if c["url"] == llm_score.DEEPSEEK_DIRECT_CHAT_URL]
    assert len(deepseek) == 1, models_called(calls2)
    assert deepseek[0]["body"]["model"] == "deepseek-flash"
    assert deepseek[0]["headers"]["Authorization"] == f"Bearer {K_DEEPSEEK}"


def test_the_deepseek_alias_family_resolves(box, monkeypatch):
    """The canon accepts DEEPSEEK_KEY for DEEPSEEK_API_KEY; a box that wrote
    the alias must still run step 4."""
    monkeypatch.setenv("DEEPSEEK_KEY", K_DEEPSEEK)
    assert llm_score.deepseek_direct_api_keys() == [K_DEEPSEEK]


def test_the_agnes_alias_family_resolves(box, monkeypatch):
    """AGNES_AI_API_KEY is the name measured on live boxes; AGNES_API_KEY is
    the canonical head. Both must answer."""
    monkeypatch.setenv("AGNES_AI_API_KEY", K_AGNES)
    assert llm_score.agnes_api_keys() == [K_AGNES]


def test_the_agnes_gateway_provider_key_is_the_last_resort(box, monkeypatch):
    write_openclaw(box, {"agnes": {"baseUrl": "https://apihub.agnes-ai.com/v1",
                                   "apiKey": K_GATEWAY_AGNES}})
    assert llm_score._env("AGNES_API_KEY") == "", "control: no env key"
    assert llm_score.agnes_api_keys() == [K_GATEWAY_AGNES]

    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    assert llm_score.agnes_api_keys() == [K_AGNES, K_GATEWAY_AGNES], (
        "the env key leads; the gateway key follows it")


def test_a_provider_for_another_host_is_not_borrowed_for_agnes(box):
    """CONTROL: the baseUrl match is what selects the provider. Without this
    leg the fallback could be picking up any key in the file."""
    write_openclaw(box, {"ollama": {"baseUrl": "https://ollama.com",
                                    "apiKey": K_GATEWAY_AGNES}})
    assert llm_score.agnes_api_keys() == []


def test_openrouter_takes_no_gateway_key(box):
    """CONTROL for the deliberate asymmetry: only Ollama Cloud and Agnes read
    a gateway provider key. OpenRouter resolves from its env name or not at
    all."""
    write_openclaw(box, {"openrouter": {"baseUrl": "https://openrouter.ai/api/v1",
                                        "apiKey": K_OPENROUTER}})
    assert llm_score.openrouter_api_keys() == []


# ---------------------------------------------------------------------------
# 3. LLM_SCORE_CHAIN override
# ---------------------------------------------------------------------------

def test_the_override_replaces_the_table_outright(box, monkeypatch):
    monkeypatch.setenv(
        "LLM_SCORE_CHAIN",
        "openrouter:google/gemini-3.1-flash-lite, agnes:agnes-2.5-flash")
    assert llm_score.scoring_chain() == [
        ("openrouter", "google/gemini-3.1-flash-lite"),
        ("agnes", "agnes-2.5-flash"),
    ]


def test_the_override_splits_on_the_first_colon_only(box, monkeypatch):
    """An Ollama tag carries its own colon. Splitting anywhere else would
    turn deepseek-v4-pro:0813 into a model named 'deepseek-v4-pro'."""
    monkeypatch.setenv("LLM_SCORE_CHAIN", "ollama-cloud:deepseek-v4-pro:0813")
    assert llm_score.scoring_chain() == [("ollama-cloud", "deepseek-v4-pro:0813")]


def test_an_unknown_provider_is_skipped_with_one_warning(box, monkeypatch, capsys):
    monkeypatch.setenv(
        "LLM_SCORE_CHAIN",
        "nope:a,nope:b,openrouter:google/gemini-3.1-flash-lite")

    steps = llm_score.scoring_chain()

    assert steps == [("openrouter", "google/gemini-3.1-flash-lite")]
    warnings = [line for line in capsys.readouterr().err.splitlines()
                if "unknown provider" in line]
    assert len(warnings) == 1, warnings
    assert "'nope'" in warnings[0]


def test_the_override_is_what_gets_walked(box, monkeypatch):
    """End to end: the override changes which sockets open, not just what
    scoring_chain() returns."""
    all_keys(monkeypatch)
    monkeypatch.setenv("LLM_SCORE_CHAIN",
                       "deepseek-direct:deepseek-flash,ollama-cloud:minimax-m3")
    calls = capture_posts(monkeypatch, [http_error(500)])

    score()

    assert models_called(calls) == ["deepseek-flash", "minimax-m3"]


def test_an_override_naming_nothing_usable_degrades_rather_than_raising(box, monkeypatch):
    """An operator override wins even when it resolves to zero steps -- but
    the degraded reasoning has to SAY the chain was empty, or the typo is
    undiagnosable."""
    all_keys(monkeypatch)
    monkeypatch.setenv("LLM_SCORE_CHAIN", "nope:a")
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])

    result = score()

    assert calls == []
    assert result["fallback"] is True
    assert "zero steps" in result["reasoning"]


# ---------------------------------------------------------------------------
# 4. AGNES 3.0 -> 2.5
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [404, 400])
def test_agnes_retries_once_with_the_25_tag_on_model_not_found(box, monkeypatch, code):
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    calls = capture_posts(monkeypatch,
                          [http_error(code, "model not found"), _SCORE_REPLY])

    result = score()

    assert models_called(calls) == ["agnes-3.0-flash", "agnes-2.5-flash"]
    assert calls[1]["url"] == "https://apihub.agnes-ai.com/v1/chat/completions"
    assert calls[1]["headers"]["Authorization"] == f"Bearer {K_AGNES}", (
        "the retry keeps the key that already authenticated")
    assert result["model"] == "agnes/agnes-2.5-flash", (
        "the label must name the model that actually answered")
    assert result["score"] == 0.77


def test_the_agnes_retry_happens_at_most_once(box, monkeypatch):
    """CONTROL for the recursion: a 404 on the 2.5 tag ends the step, it does
    not loop."""
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    calls = capture_posts(monkeypatch, [http_error(404, "model not found")])

    score()

    assert models_called(calls) == ["agnes-3.0-flash", "agnes-2.5-flash"]


def test_a_500_from_agnes_does_not_trigger_the_model_retry(box, monkeypatch):
    """CONTROL: a 500 is Agnes being down, not Agnes refusing the model.
    Retrying would double an outage's cost for nothing."""
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    calls = capture_posts(monkeypatch, [http_error(500, "Server Error")])

    score()

    assert models_called(calls) == ["agnes-3.0-flash"]


def test_an_explicit_25_step_does_not_fall_back_to_itself(box, monkeypatch):
    """CONTROL: the fallback is pinned to the 3.0 id. An operator who named
    2.5 outright gets one attempt."""
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    monkeypatch.setenv("LLM_SCORE_CHAIN", "agnes:agnes-2.5-flash")
    calls = capture_posts(monkeypatch, [http_error(404, "model not found")])

    score()

    assert models_called(calls) == ["agnes-2.5-flash"]


def test_a_401_on_the_agnes_env_key_retries_with_the_gateway_key(box, monkeypatch):
    """The key ladder still works through the generalised transport."""
    write_openclaw(box, {"agnes": {"baseUrl": "https://apihub.agnes-ai.com/v1",
                                   "apiKey": K_GATEWAY_AGNES}})
    monkeypatch.setenv("AGNES_API_KEY", K_AGNES)
    calls = capture_posts(monkeypatch, [http_error(401, "Unauthorized"),
                                        _SCORE_REPLY])

    result = score()

    assert len(calls) == 2, models_called(calls)
    assert calls[0]["headers"]["Authorization"] == f"Bearer {K_AGNES}"
    assert calls[1]["headers"]["Authorization"] == f"Bearer {K_GATEWAY_AGNES}"
    assert result["model"] == "agnes/agnes-3.0-flash"


# ---------------------------------------------------------------------------
# 5. REDACTION
# ---------------------------------------------------------------------------

def test_no_key_reaches_the_result_or_the_verbose_log(box, monkeypatch, capsys):
    """Every step fails, verbose is on, and every sentinel key is resolvable.
    Nothing about a value may appear in the dict or on stderr."""
    all_keys(monkeypatch)
    write_openclaw(box, {"agnes": {"baseUrl": "https://apihub.agnes-ai.com/v1",
                                   "apiKey": K_GATEWAY_AGNES}})
    capture_posts(monkeypatch, [http_error(500, "Server Error")])

    result = score(verbose=True)
    blob = json.dumps(result) + capsys.readouterr().err + llm_score.env_report()

    for sentinel in ALL_SENTINELS:
        assert sentinel not in blob, "a credential leaked"
        assert sentinel[:12] not in blob, "a credential PREFIX leaked"


def test_the_winning_label_is_what_lands_in_the_cache(box, monkeypatch):
    """The label is not cosmetic: it is the `model` column the selection log
    reads back, so it has to survive the cache round trip."""
    monkeypatch.setenv("OPENROUTER_API_KEY", K_OPENROUTER)
    capture_posts(monkeypatch, [_SCORE_REPLY])

    fresh = llm_score.score_layer("cache-label-probe", "mission", "s", "c")
    cached = llm_score.score_layer("cache-label-probe", "mission", "s", "c")

    assert fresh["model"] == "openrouter/minimax/minimax-m3"
    assert cached["cached"] is True
    assert cached["model"] == fresh["model"]
    assert K_OPENROUTER not in json.dumps(cached)


# ---------------------------------------------------------------------------
# 6. WHAT THIS CHANGE MUST NOT TOUCH
# ---------------------------------------------------------------------------

def test_the_cache_ttl_is_still_thirty_days():
    assert llm_score.CACHE_TTL_SECONDS == 30 * 24 * 60 * 60


def test_the_per_step_http_timeout_is_twenty_seconds():
    """Every step inherits _post_chat's default, so the default IS the
    per-step budget."""
    import inspect
    assert llm_score.HTTP_TIMEOUT_SECONDS == 20
    assert inspect.signature(
        llm_score._post_chat).parameters["timeout"].default == 20


def test_the_back_compat_attempt_helpers_still_exist(box, monkeypatch):
    """verify-persona-adherence.py imports both of these at module level and
    switches its whole LLM path off on ImportError."""
    from llm_score import _attempt_ollama_cloud, _attempt_openrouter  # noqa: F401

    all_keys(monkeypatch)
    calls = capture_posts(monkeypatch, [_SCORE_REPLY])

    ollama = _attempt_ollama_cloud("score this")
    openrouter = _attempt_openrouter("score this", llm_score.openrouter_model())

    assert ollama["ok"] is True
    assert ollama["model"] == f"ollama-cloud/{llm_score.ollama_cloud_model()}"
    assert openrouter["model"] == f"openrouter/{llm_score.openrouter_model()}"
    assert models_called(calls) == [llm_score.ollama_cloud_model(),
                                    llm_score.openrouter_model()]
