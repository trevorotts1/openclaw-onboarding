#!/usr/bin/env python3
"""test_pd_router_grader_independence.py -- PD-204.

A GRADER NEVER RIDES THE MODEL THAT WROTE THE ARTIFACT.

Pins the acceptance rows of PD-204 directly:

  1. A DeepSeek-only client gets NO route for P1Q-COPY-QC, with the plain
     reason "no independent model is available to grade this step", and every
     refused candidate row names "same model family as the author".
  2. DeepSeek + OpenRouter: the judge lands on the OTHER family (GLM).
  3. A declared judge on another family is USED (and reported applied).
  4. A declared judge in the AUTHOR's family is refused by the same rule --
     a client declaration can never re-open the hole.
  5. The rule follows the AUTHOR: when the client's declared workhorse is
     GLM, the grader moves to DeepSeek instead.
  6. Non-grader phases are untouched (no author_route stamp, same route).

Unit-level: no network, no spend, no engine. Profiles are written into a tmp
config dir the capacity/profile env points at.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

PLAIN_REASON = "no independent model is available to grade this step"
FAMILY_SKIP = "same model family as the author"


def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


DEEPSEEK_ONLY_PROFILE = {
    ".schema_version": 1,
    "providers": {
        "deepseek-direct": _wired("deepseek-direct",
                                  ["deepseek-flash", "deepseek-v4.1-flash"]),
    },
    "creative_prefs": {}, "consent": {}, "interview": {},
}

TWO_PROVIDER_PROFILE = {
    ".schema_version": 1,
    "providers": {
        "deepseek-direct": _wired("deepseek-direct",
                                  ["deepseek-flash", "deepseek-v4.1-flash"]),
        "openrouter": _wired("openrouter",
                             ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"]),
    },
    "creative_prefs": {}, "consent": {}, "interview": {},
}


def _profile_env(monkeypatch, tmp_path, profile):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE_DIR", raising=False)
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE", raising=False)
    monkeypatch.delenv("PRESENTATION_MODEL_ROUTER", raising=False)
    monkeypatch.delenv("PRESENTATION_MODES", raising=False)
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    monkeypatch.setenv("OPENCLAW_ROOT", str(tmp_path / "no-openclaw-root"))
    monkeypatch.delenv("PRESENTATION_MODEL_TEXT_STRONG", raising=False)
    (cfg / resource_profile.PROFILE_FILENAME).write_text(
        json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


def _with_plan(profile, plan):
    prof = copy.deepcopy(profile)
    prof["model_plan"] = plan
    return prof


def _plan(judge=None, workhorse=None):
    return {"workhorse": workhorse, "reasoning": None, "judge": judge,
            "thinking": None, "floor_waivers": [], "source": "interview"}


def _skipped_rows(decision):
    return [c for c in decision.get("candidates") or []
            if c.get("reason") == FAMILY_SKIP]


# ---------------------------------------------------------------------------
# _model_family -- the rule's only primitive
# ---------------------------------------------------------------------------
def test_model_family_is_the_vendor_prefix():
    assert model_router._model_family("deepseek-v4.1-flash") == "deepseek"
    assert model_router._model_family("deepseek-flash") == "deepseek"
    assert model_router._model_family("z-ai/glm-5.3-flash") == "glm"
    assert model_router._model_family("openrouter/z-ai/glm-5.3") == "glm"
    # UNKNOWN is empty, never a family -- two unknowns must not compare equal.
    assert model_router._model_family("") == ""
    assert model_router._model_family("123-model") == ""


# ---------------------------------------------------------------------------
# 1. DeepSeek-only client: no independent grader exists
# ---------------------------------------------------------------------------
def test_deepseek_only_client_has_no_independent_grader(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, DEEPSEEK_ONLY_PROFILE)
    decision = model_router.resolve_route("P1Q-COPY-QC")

    assert decision["route"] is None, decision
    assert decision["reason"] == PLAIN_REASON, decision
    assert decision["author_phase"] == "P4-COPY", decision
    assert decision["author_route"]["model"] == "deepseek-flash", decision
    assert _skipped_rows(decision), decision["candidates"]

    # The author phase itself is unaffected and is a DeepSeek route.
    author = model_router.resolve_route("P4-COPY")
    assert author["route"] is not None, author
    assert model_router._model_family(author["route"]["model"]) == "deepseek"


# ---------------------------------------------------------------------------
# 2. DeepSeek + OpenRouter: the judge goes to the other family
# ---------------------------------------------------------------------------
def test_judge_moves_to_the_other_family(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, TWO_PROVIDER_PROFILE)
    decision = model_router.resolve_route("P1Q-COPY-QC")

    assert decision["route"] == {"provider": "openrouter",
                                 "model": "z-ai/glm-5.3-flash"}, decision
    assert _skipped_rows(decision), decision["candidates"]
    # The skipped rows are the DeepSeek family the author used.
    for row in _skipped_rows(decision):
        assert model_router._model_family(row.get("model")) == "deepseek", row


# ---------------------------------------------------------------------------
# 3. Declared judge on ANOTHER family: used
# ---------------------------------------------------------------------------
def test_declared_judge_on_another_family_is_used(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, _with_plan(TWO_PROVIDER_PROFILE, _plan(
        judge={"provider": "openrouter", "model": "z-ai/glm-5.3"})))
    decision = model_router.resolve_route("P1Q-COPY-QC")

    assert decision["route"] == {"provider": "openrouter",
                                 "model": "z-ai/glm-5.3"}, decision
    assert decision["client_plan"]["applied"] is True, decision
    assert decision["model_source"] == "client-plan", decision


# ---------------------------------------------------------------------------
# 4. Declared judge in the AUTHOR's family: refused by the same rule
# ---------------------------------------------------------------------------
def test_declared_judge_in_the_author_family_is_refused(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, _with_plan(TWO_PROVIDER_PROFILE, _plan(
        judge={"provider": "deepseek-direct", "model": "deepseek-flash"})))
    decision = model_router.resolve_route("P1Q-COPY-QC")

    assert decision["client_plan"]["applied"] is False, decision
    assert decision["client_plan"]["rejected_reason"] == FAMILY_SKIP, decision
    # It falls through to the other family rather than parking.
    assert decision["route"]["provider"] == "openrouter", decision


# ---------------------------------------------------------------------------
# 5. The rule follows the AUTHOR, not a fixed vendor
# ---------------------------------------------------------------------------
def test_the_rule_follows_the_author(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, _with_plan(TWO_PROVIDER_PROFILE, _plan(
        workhorse={"provider": "openrouter", "model": "z-ai/glm-5.3-flash"})))
    author = model_router.resolve_route("P4-COPY")
    assert author["route"]["provider"] == "openrouter", author

    decision = model_router.resolve_route("P1Q-COPY-QC")
    assert decision["author_route"] == author["route"], decision
    assert decision["route"] is not None, decision
    assert model_router._model_family(decision["route"]["model"]) \
        == "deepseek", decision


# ---------------------------------------------------------------------------
# 6. No regression for a phase that is not a grader
# ---------------------------------------------------------------------------
def test_non_grader_phase_is_untouched(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, TWO_PROVIDER_PROFILE)
    decision = model_router.resolve_route("P4-COPY")

    assert "author_route" not in decision, decision
    assert "author_phase" not in decision, decision
    assert decision["route"] is not None, decision
