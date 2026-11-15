#!/usr/bin/env python3
"""test_pd_router_vision.py -- PD-205a: the vision rule applies to the
image-check list.

THE DEFECT
----------
`CAPABILITY_CANDIDATES["vision_ocr"]` shipped text-model rows
(`deepseek-v4.1-flash`, `glm-5.3`) under a comment arguing a text model could
serve the image check, and `resolve_route`'s candidate loop never looked at a
candidate's modality. The class floor declared `vision_ocr: modality vision`
and nothing enforced it, so a text model could be selected for P-IMAGE-QC /
P-TYPO-QC.

THE FIX (unit PD-205a)
----------------------
1. The `vision_ocr` list carries only vision models.
2. In the candidate loop, a `vision_ocr` / `image_render` candidate takes its
   kind from `_registry_capability_meta` (alias first, then the served id) and
   is marked ineligible with "not a vision model" / "not an image model" when
   it does not meet `class_floor`. An unknown kind is ineligible too.

Unit-level: no network, no spend, no deck, no render. The profile rig is
tests/test_f3_per_route_ceiling.py's deliberately, and the configured-default
source is stubbed empty so no openclaw.json on the box can influence a route.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import model_catalog  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

VISION_PHASES = ("P-IMAGE-QC", "P-TYPO-QC")

#: Every id a text model can be selected as on the shipped catalog/registry.
TEXT_MODELS = frozenset({
    "deepseek-flash", "deepseek-v4.1-flash", "glm-5.3", "glm-flash",
    "z-ai/glm-5.3", "z-ai/glm-5.3-flash",
})

#: Every id the vision class may legitimately return.
VISION_MODELS = frozenset({"glm-ocr", "z-ai/glm-4.6v"})


def _wired(provider, models):
    return {"provider": provider, "consented": True, "detected": True,
            "presence": True, "wired_models": list(models)}


def _profile(providers):
    return {
        ".schema_version": 1,
        "providers": providers,
        "creative_prefs": {}, "consent": {}, "interview": {},
    }


def _env(monkeypatch, tmp_path, profile):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES",
                model_router.MODE_ENV):
        monkeypatch.delenv(var, raising=False)
    # Selection, not credentials: the FIX 114 key gate is satisfied for every
    # provider and no real key is ever read.
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    # No openclaw.json on this box may become a configured default.
    monkeypatch.setattr(model_catalog, "client_configured_default_model",
                        lambda: "")
    (cfg / resource_profile.PROFILE_FILENAME).write_text(
        json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


def _deepseek_only():
    return _profile({"deepseek-direct": _wired("deepseek-direct",
                                               ["deepseek-flash"])})


def _with_ollama():
    return _profile({
        "deepseek-direct": _wired("deepseek-direct", ["deepseek-flash"]),
        "ollama-cloud": _wired("ollama-cloud", ["glm-ocr"]),
    })


# ---------------------------------------------------------------------------
# 1. THE LIST ITSELF CARRIES NO TEXT MODEL
# ---------------------------------------------------------------------------
def test_the_vision_ocr_list_carries_only_vision_models():
    """The defect's first half: text-model rows under a comment arguing a text
    model satisfies the check. _registry_capability_meta is the same lookup
    the candidate loop uses, so this pins the table and the gate together."""
    aliases = [str(c.get("alias") or "")
               for c in model_router.CAPABILITY_CANDIDATES["vision_ocr"]]
    assert aliases, "the vision_ocr list is empty"
    for alias in aliases:
        meta = model_router._registry_capability_meta(alias)
        assert meta.get("modality") == "vision", (
            f"{alias!r} is on the vision_ocr list but the registry says "
            f"{meta!r}")


# ---------------------------------------------------------------------------
# 2. ACCEPTANCE: DeepSeek-only client -> P-IMAGE-QC parks, reason names the
#    vision rule.
# ---------------------------------------------------------------------------
def test_deepseek_only_client_parks_image_qc_with_the_vision_rule(
        monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, _deepseek_only())
    decision = model_router.resolve_route("P-IMAGE-QC")
    assert decision["route"] is None, decision
    assert decision["capability"] == "vision_ocr", decision
    reason = str(decision["reason"]).lower()
    assert "no eligible route" in reason, decision["reason"]
    assert "vision" in reason, (
        "the park reason must name the vision rule, not only provider "
        f"ownership: {decision['reason']}")


# ---------------------------------------------------------------------------
# 3. ACCEPTANCE: a client with Ollama Cloud gets glm-ocr.
# ---------------------------------------------------------------------------
def test_ollama_cloud_client_gets_glm_ocr(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, _with_ollama())
    decision = model_router.resolve_route("P-IMAGE-QC")
    assert decision["route"] is not None, decision
    assert model_router._norm_provider(decision["route"]["provider"]) == \
        "ollama-cloud", decision["route"]
    assert decision["route"]["model"] == "glm-ocr", decision["route"]


# ---------------------------------------------------------------------------
# 4. ACCEPTANCE: no text model is ever returned for either vision phase.
#    Every client shape and every mode; a park is fine, a text model is not.
# ---------------------------------------------------------------------------
def test_no_text_model_is_ever_returned_for_the_vision_phases(
        monkeypatch, tmp_path):
    shapes = {
        "deepseek-only": _deepseek_only(),
        "ollama-cloud": _with_ollama(),
        "deepseek+openrouter": _profile({
            "deepseek-direct": _wired("deepseek-direct", ["deepseek-flash"]),
            "openrouter": _wired("openrouter", ["z-ai/glm-4.6v"]),
        }),
    }
    seen = []
    for shape, profile in shapes.items():
        for mode in model_router.MODES:
            _env(monkeypatch, tmp_path, profile)
            for phase in VISION_PHASES:
                decision = model_router.resolve_route(phase, mode=mode)
                route = decision.get("route")
                if route is None:
                    continue
                model = str(route.get("model") or "")
                seen.append((shape, mode, phase, model))
                assert model not in TEXT_MODELS, (
                    f"{shape} / {mode} / {phase} selected the text model "
                    f"{model!r}: {decision}")
                assert model in VISION_MODELS, (
                    f"{shape} / {mode} / {phase} selected {model!r}, not a "
                    f"registered vision model: {decision}")
    assert any(s[1] == "standard" for s in seen), (
        "the guard never resolved a route for a vision phase -- vacuous")


# ---------------------------------------------------------------------------
# 5. THE LOOP GATE: a text candidate is marked "not a vision model" and the
#    vision candidate behind it still wins.
# ---------------------------------------------------------------------------
def test_a_text_candidate_is_marked_not_a_vision_model(monkeypatch, tmp_path):
    monkeypatch.setitem(
        model_router.CAPABILITY_CANDIDATES, "vision_ocr",
        [{"alias": "deepseek-flash"}, {"alias": "glm-ocr"}])
    _env(monkeypatch, tmp_path, _with_ollama())
    decision = model_router.resolve_route("P-TYPO-QC")
    first = decision["candidates"][0]
    # The catalog's own alias label rides through on the resolved row.
    assert first["alias"] in ("deepseek-flash", "text.fast"), \
        decision["candidates"]
    assert first["eligible"] is False, first
    assert first["reason"] == "not a vision model", first
    assert decision["route"] is not None, decision
    assert decision["route"]["model"] == "glm-ocr", decision["route"]


def test_a_text_candidate_is_marked_not_an_image_model(monkeypatch, tmp_path):
    monkeypatch.setitem(
        model_router.CAPABILITY_CANDIDATES, "image_render",
        [{"alias": "deepseek-flash"}, {"alias": "gpt-image-2"}])
    _env(monkeypatch, tmp_path, _profile({
        "deepseek-direct": _wired("deepseek-direct", ["deepseek-flash"]),
        "kie": _wired("kie", ["gpt-image-2-6/sunburst-text-to-image"]),
    }))
    decision = model_router.resolve_route("P4-RENDER")
    first = decision["candidates"][0]
    assert first["alias"] in ("deepseek-flash", "text.fast"), \
        decision["candidates"]
    assert first["eligible"] is False, first
    assert first["reason"] == "not an image model", first
    assert decision["route"] is not None, decision
    assert decision["route"]["model"] == \
        "gpt-image-2-6/sunburst-text-to-image", decision["route"]


def test_an_unknown_kind_is_refused_for_the_vision_class(monkeypatch,
                                                        tmp_path):
    """An unknown reading is never rounded up into a capability: a candidate
    carrying an id the registry does not describe cannot serve vision."""
    monkeypatch.setitem(
        model_router.CAPABILITY_CANDIDATES, "vision_ocr",
        [{"provider": "ollama-cloud", "model": "mystery-vision"}])
    _env(monkeypatch, tmp_path, _with_ollama())
    decision = model_router.resolve_route("P-TYPO-QC")
    assert decision["route"] is None, decision
    assert decision["candidates"][0]["eligible"] is False, decision
    assert decision["candidates"][0]["reason"] == "not a vision model", \
        decision["candidates"][0]
