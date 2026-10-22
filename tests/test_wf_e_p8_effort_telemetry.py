#!/usr/bin/env python3
"""WF-E (P8 / C9) — opt-in model effort + billing telemetry regression.

Owner: WF-E test lane (DeepSeek 1017). Scope is TEST FIXTURES ONLY — this file
never edits ``model_router.py`` or ``billing_telemetry.py``; it asserts them.

Proves checklist C9 (plan §4.4 + §15.1):

  C9a  Legacy ``high`` is preserved when no effort profile is set, and the
       client's model choice / configured default still wins (nothing is
       prescribed by name).
  C9b  An unsupported effort level fails EXPLICITLY — never silently max.
  C9c  S24: an excluded model (Luna / Terra / Qwen / Muse Wonder / free
       endpoint) proposed as a fallback is refused with an explicit policy
       error and is never called.
  C9d  Receipt fields are present and consistent: provider, model, token
       accounting (incl. the no-double-count rule), tool calls, billed $.
  C9e  Provider capability validation: an effort the provider cannot do fails
       explicitly (observed preflight capabilities win over the static table).
  C9f  B18: deterministic procedures make ZERO model-selection calls per click.

Synthetic/offline only: no network, no real GHL, no client identifiers, no
secrets. Executors are stubs.

Run:  python3 -m pytest tests/test_wf_e_p8_effort_telemetry.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "06-ghl-install-pages" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import billing_telemetry as bt  # noqa: E402
import ghl_ab_executor as abx  # noqa: E402
import model_router as mr  # noqa: E402

ALL_ROLES = ("content", "html", "reasoning", "execution", "qc")

# A configured client box in test form. Neutral slugs: no project model names.
DEFAULT_ENV = {"MODEL_ROUTER_DEFAULT": "client-default:cloud"}
CHOICE_ENV = {
    "MODEL_ROUTER_CHOICE": "client/choice-model",
    "MODEL_ROUTER_DEFAULT": "client-default:cloud",
}


def _slugs(ladder):
    return [m["slug"] for rung in ladder for m in rung["models"]]


# ---------------------------------------------------------------------------
# C9a — legacy "high" preserved when the profile is absent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ALL_ROLES)
def test_legacy_high_preserved_when_profile_absent(role):
    """No effort profile → legacy thinking=high on every rung, and the client's
    own model choice is still what resolves. Nothing is prescribed."""
    ladder = mr.build_ladder(DEFAULT_ENV, role=role)
    assert ladder, f"role {role!r}: empty ladder"
    assert [r["thinking"] for r in ladder] == ["high"] * len(ladder)
    assert _slugs(ladder) == ["client-default:cloud"]


def test_legacy_high_preserved_through_select_and_client_choice_wins():
    """select() carries the legacy high into the chosen entry, and the client's
    explicit choice outranks the configured default (precedence preserved)."""
    receipt = mr.select(
        mr.make_stub_executor(), role="html", env=CHOICE_ENV, sleep=lambda *_: None
    )
    chosen = receipt["chosen"]
    assert chosen is not None, "a configured client must resolve a rung"
    assert chosen["thinking"] == "high", "legacy effort must survive select()"
    assert chosen["model"] == "client/choice-model", "client choice must win"
    # Ladder order is choice → default; nothing else is invented.
    assert [m["resolution"] for m in receipt["ladder"]] == [
        "client-choice",
        "client-default",
    ]


# ---------------------------------------------------------------------------
# C9b — unsupported effort level fails explicitly, never silently max
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["ultra", "maximum", "HIGHEST", "max", "0"])
def test_unsupported_effort_level_fails_explicitly(bad):
    env = {"MODEL_ROUTER_EFFORT_PROFILE": bad}
    with pytest.raises(mr.EffortProfileError) as exc:
        mr.resolve_effort(env, "html", "openrouter")
    # The error must be explicit about the rejected value — no silent fallback.
    assert bad in str(exc.value)


def test_bad_effort_profile_aborts_ladder_build_not_silently_maxed():
    """A malformed opt-in must stop ladder construction. If it silently became
    max/high the build would succeed — that is the regression this pins."""
    env = dict(DEFAULT_ENV, MODEL_ROUTER_EFFORT_PROFILE="ultra")
    with pytest.raises(mr.EffortProfileError):
        mr.build_ladder(env, role="html")
    # And select() must not route around it.
    with pytest.raises(mr.EffortProfileError):
        mr.select(mr.make_stub_executor(), role="html", env=env,
                  sleep=lambda *_: None)


# ---------------------------------------------------------------------------
# C9c — S24 excluded-model policy rejection (never called, never a fallback)
# ---------------------------------------------------------------------------

EXCLUDED_SLUGS = [
    "vendor/luna-1",
    "vendor/terra-pro",
    "qwen/qwen3-coder",
    "vendor/muse-wonder",
    "vendor/muse-wonder-full",
    "vendor/some-model:free",
]


@pytest.mark.parametrize("slug", EXCLUDED_SLUGS)
def test_s24_excluded_choice_is_a_policy_rejection(slug):
    with pytest.raises(mr.ExcludedModelPolicyError):
        mr.resolve_client_models({"MODEL_ROUTER_CHOICE": slug}, "execution")


@pytest.mark.parametrize("slug", EXCLUDED_SLUGS)
def test_s24_excluded_fallback_ladder_refused_before_any_call(slug):
    """A caller-proposed fallback naming an excluded model is refused with an
    explicit policy error, and the executor is NEVER invoked."""
    calls = []

    def executor(provider, model, base_url, task):
        calls.append((provider, model))
        return {"tool_call_fired": True, "parsed": True, "args": {"ok": True}}

    ladder = [
        {"rung": 1, "role": "execution", "provider": "openrouter",
         "base_url": mr.OPENROUTER_BASE_URL, "probe_gated": False,
         "thinking": "high", "vision": False, "resolution": "client-choice",
         "models": [{"slug": slug, "family": "x",
                     "slug_confidence": "client-configured"}]},
    ]
    with pytest.raises(mr.ExcludedModelPolicyError):
        mr.select(executor, ladder=ladder, sleep=lambda *_: None)
    assert calls == [], f"excluded model {slug!r} was CALLED: {calls}"


# ---------------------------------------------------------------------------
# C9d — receipt fields present and consistent (no double-count rule)
# ---------------------------------------------------------------------------


def test_receipt_has_all_real_fields():
    r = bt.build_receipt(
        provider="openrouter",
        model="client/model",
        raw_usage={"prompt_tokens": 1000, "completion_tokens": 400,
                   "reasoning_tokens": 250, "cached_tokens": 300,
                   "cost": 0.0123},
        tool_calls=2,
    )
    for key in ("provider", "model", "prompt_tokens", "cache_tokens",
                "output_tokens", "reasoning_tokens", "tool_calls",
                "billed_dollars"):
        assert key in r, f"receipt missing real field {key!r}"
    assert r["schema"] == bt.RECEIPT_SCHEMA
    assert (r["provider"], r["model"]) == ("openrouter", "client/model")
    assert (r["prompt_tokens"], r["output_tokens"]) == (1000, 400)
    assert r["cache_tokens"] == 300
    assert r["tool_calls"] == 2
    assert r["billed_dollars"] == pytest.approx(0.0123)


def test_reasoning_inside_output_is_never_double_counted():
    """Provider includes reasoning in output totals → total is prompt+output,
    reasoning stays visible but is not billed twice."""
    r = bt.build_receipt(
        provider="openrouter", model="m",
        raw_usage={"prompt_tokens": 1000, "completion_tokens": 400,
                   "reasoning_tokens": 250},
    )
    assert r["reasoning_included_in_output"] is True
    assert r["billed_tokens_total"] == 1400
    assert r["reasoning_tokens"] == 250


def test_separate_reasoning_added_exactly_once():
    r = bt.build_receipt(
        provider="acme", model="m",
        raw_usage={"prompt_tokens": 10, "output_tokens": 5, "reasoning_tokens": 3},
        reasoning_in_output=False,
    )
    assert r["reasoning_included_in_output"] is False
    assert r["billed_tokens_total"] == 18


def test_unpriced_receipt_never_invents_dollars():
    r = bt.build_receipt(provider="acme", model="m",
                         raw_usage={"prompt_tokens": 1})
    assert r["billed_dollars"] is None
    assert r["cost_source"] == "unpriced"


def test_price_table_bills_without_double_counting_reasoning():
    r = bt.build_receipt(
        provider="acme", model="m",
        raw_usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000,
                   "reasoning_tokens": 500_000},
        price_table={"prompt_per_mtok": 2.0, "output_per_mtok": 8.0,
                     "reasoning_per_mtok": 8.0},
    )
    assert r["cost_source"] == "price-table"
    # 1M*2 + 1M*8 = 10.0; the 500k reasoning is inside output → not added again.
    assert r["billed_dollars"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# C9e — provider capability validation (observed preflight wins)
# ---------------------------------------------------------------------------


def test_effort_unsupported_by_provider_fails_explicitly():
    env = {"MODEL_ROUTER_EFFORT_PROFILE": "low"}
    with pytest.raises(mr.EffortUnsupportedError):
        mr.resolve_effort(env, "html", "openrouter",
                          capabilities={"openrouter": frozenset(["high"])})


def test_unknown_provider_supports_no_effort_levels():
    """No capability entry → empty set → any opted-in level fails explicitly
    rather than being assumed supported."""
    env = {"MODEL_ROUTER_EFFORT_PROFILE": "medium"}
    with pytest.raises(mr.EffortUnsupportedError):
        mr.resolve_effort(env, "html", "mystery-provider")


def test_observed_capabilities_win_over_static_table():
    """The static table says openrouter does low; a narrower preflight
    observation must win, and a wider one must be honoured."""
    env = {"MODEL_ROUTER_EFFORT_PROFILE": "low"}
    with pytest.raises(mr.EffortUnsupportedError):
        mr.resolve_effort(env, "html", "openrouter",
                          capabilities={"openrouter": frozenset(["medium"])})
    assert mr.resolve_effort(
        env, "html", "openrouter",
        capabilities={"openrouter": frozenset(["low"])},
    ) == "low"


def test_supported_effort_resolves_and_reaches_the_rung():
    env = dict(DEFAULT_ENV, MODEL_ROUTER_EFFORT_PROFILE_EXECUTION="medium")
    ladder = mr.build_ladder(env, role="execution")
    assert [r["thinking"] for r in ladder] == ["medium"]
    # Opt-in is per role: an unrelated role keeps legacy high.
    assert [r["thinking"] for r in mr.build_ladder(env, role="html")] == ["high"]


# ---------------------------------------------------------------------------
# C9f — B18: deterministic procedures make ZERO model-selection calls per click
# ---------------------------------------------------------------------------


def _counting_selection(monkeypatch):
    """Count every model-selection entry point a recipe could accidentally hit."""
    counter = {"select": 0, "build_ladder": 0, "resolve_effort": 0}

    def _wrap(name):
        real = getattr(mr, name)

        def _inner(*a, **kw):
            counter[name] += 1
            return real(*a, **kw)

        monkeypatch.setattr(mr, name, _inner)

    for name in counter:
        _wrap(name)
    return counter


def test_deterministic_click_fill_loop_makes_zero_model_selection_calls(monkeypatch):
    """A scripted click/fill/wait recipe drives agent-browser directly — it must
    never ask the router to pick a model per action (B18)."""
    counter = _counting_selection(monkeypatch)

    class CP:
        returncode = 0
        stdout = "ok"
        stderr = ""

    ab_calls = []

    def ab(session, *args, timeout=15):
        ab_calls.append(args)
        return CP()

    def ev(session, js, timeout=15):
        return "CLICKED:x"

    ex = abx.AbExecutor(ab=ab, ev=ev)
    actions = [
        ("click", "getByRole('button', { name: 'Create Group' })"),
        ("fill", "#group-name"),
        ("click", "button[type=submit]"),
        ("click", "getByText('Save')"),
        ("click", "button[type=submit]"),
    ]
    for action, anchor in actions:
        if action == "fill":
            res = ex.fill("s1", anchor, "Synthetic Name")
        else:
            res = ex.click("s1", anchor)
        assert res["ok"] is True, res

    assert len(ab_calls) == len(actions), "every action must reach the browser"
    assert counter == {"select": 0, "build_ladder": 0, "resolve_effort": 0}, (
        f"deterministic recipe must make zero model-selection calls, got {counter}"
    )


def test_deterministic_recipe_receipt_records_zero_llm_calls():
    """The receipt for a deterministic procedure states llm_calls_during_recipe=0
    and bills nothing — the B18 measurement is recorded, not assumed."""
    r = bt.build_receipt(provider="none", model="deterministic-procedure",
                         llm_calls_during_recipe=0)
    assert r["llm_calls_during_recipe"] == 0
    assert r["billed_dollars"] is None
    assert r["cost_source"] == "unpriced"
