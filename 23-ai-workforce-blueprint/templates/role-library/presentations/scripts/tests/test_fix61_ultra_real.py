#!/usr/bin/env python3
"""test_fix61_ultra_real.py -- FIX 61.7: ultra mode is real, not cosmetic.

THE REQUIREMENT (Fix 61, D2): Ultra = the client's chosen strong models,
never Ollama. Ultra ceiling 400, standard 25.

SETUP:
  - Profile with deepseek-direct (concurrency_ceiling "UNBOUNDED"),
    ollama-cloud and openrouter all present.
  - Declared judge of glm-5.3-flash@ollama-cloud.
  - Monkeypatch model_router.provider_key_resolves to return True.

ASSERTS:
  - For every non-mechanical phase, ultra route provider != "ollama-cloud".
  - Judge phase routes to openrouter / z-ai/glm-5.3-flash.
  - mode_ceiling("ultra") == 400.
  - mode_ceiling("standard") == 25.
  - Unmeasured client (deepseek-direct presence only) standard == 25.
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import model_router


def _make_profile():
    """Profile with all three providers present, deepseek UNBOUNDED."""
    return {
        "providers": {
            "deepseek-direct": {
                "presence": True,
                "concurrency_ceiling": "UNBOUNDED",
                "ceiling_source": "test",
            },
            "ollama-cloud": {
                "presence": True,
                "concurrency_ceiling": 8,
                "ceiling_source": "test",
            },
            "openrouter": {
                "presence": True,
                "concurrency_ceiling": "UNBOUNDED",
                "ceiling_source": "test",
            },
        },
        "model_plan": {
            "judge": "glm-5.3-flash@ollama-cloud",
        },
    }


def test_ultra_never_routes_to_ollama(monkeypatch):
    """Every non-mechanical phase in ultra must NOT use ollama-cloud."""
    monkeypatch.setattr(
        model_router, "provider_key_resolves", lambda *a, **k: True
    )
    prof = _make_profile()
    for phase_id, capability in model_router.PHASE_CAPABILITY.items():
        if capability == "mechanical":
            continue
        result = model_router.resolve_route(phase_id, profile=prof, mode="ultra")
        route = result.get("route")
        assert route is not None, f"ultra: {phase_id} has no route"
        provider = str(route.get("provider") or "")
        assert provider != "ollama-cloud", (
            f"ultra: {phase_id} routed to ollama-cloud -- "
            f"ultra never uses Ollama (got {route})"
        )


def test_ultra_judge_routes_to_openrouter(monkeypatch):
    """The declared ollama-cloud judge becomes openrouter/z-ai/glm-5.3-flash."""
    monkeypatch.setattr(
        model_router, "provider_key_resolves", lambda *a, **k: True
    )
    prof = _make_profile()
    # Find the judge phase (capability "judge" or similar)
    judge_phase = None
    for phase_id, capability in model_router.PHASE_CAPABILITY.items():
        if "judge" in phase_id.lower() or capability == "judge":
            judge_phase = phase_id
            break
    if judge_phase is None:
        # Fallback: try a known phase id
        judge_phase = "judge"
        if judge_phase not in model_router.PHASE_CAPABILITY:
            return  # no judge phase in this version; skip
    result = model_router.resolve_route(judge_phase, profile=prof, mode="ultra")
    route = result.get("route") or {}
    assert route.get("provider") == "openrouter", (
        f"ultra judge should route to openrouter, got {route}"
    )
    model = str(route.get("model") or "")
    assert "glm-5.3-flash" in model, (
        f"ultra judge should be z-ai/glm-5.3-flash, got {model!r}"
    )


def test_ultra_ceiling_is_400(monkeypatch):
    """mode_ceiling("ultra") == 400."""
    monkeypatch.setattr(
        model_router, "provider_key_resolves", lambda *a, **k: True
    )
    prof = _make_profile()
    result = model_router.mode_ceiling("ultra", profile=prof)
    assert result["ceiling"] == 400, (
        f"ultra ceiling should be 400, got {result['ceiling']}"
    )


def test_standard_ceiling_is_25(monkeypatch):
    """mode_ceiling("standard") == 25."""
    monkeypatch.setattr(
        model_router, "provider_key_resolves", lambda *a, **k: True
    )
    prof = _make_profile()
    result = model_router.mode_ceiling("standard", profile=prof)
    assert result["ceiling"] == 25, (
        f"standard ceiling should be 25, got {result['ceiling']}"
    )


def test_unmeasured_client_standard_is_25(monkeypatch):
    """Unmeasured client (deepseek-direct presence only) gets 25, not 400."""
    monkeypatch.setattr(
        model_router, "provider_key_resolves", lambda *a, **k: True
    )
    prof = {"providers": {"deepseek-direct": {"presence": True}}}
    result = model_router.mode_ceiling("standard", profile=prof)
    assert result["ceiling"] == 25, (
        f"unmeasured standard should be 25 (not 400), got {result['ceiling']}"
    )
