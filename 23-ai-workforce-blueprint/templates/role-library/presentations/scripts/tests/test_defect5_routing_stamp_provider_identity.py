"""DEFECT 5 -- dispatcher._prompt_routing_stamp compared provider SPELLING,
not provider IDENTITY, and silently fell back to the default wave width.

THE DEFECT (measured on the shipped table, this box, 2026-09-05)

    model_router.resolve_alias("deepseek-v4-pro")["provider"]  -> 'deepseek'
    capacity.probe()["provider"]                               -> 'deepseek-direct'

`route["provider"]` comes from model_catalog.json, which spells the provider
"deepseek"; resolve_alias() normalises the served_ids KEYS but passes the
catalog's own provider string straight through. `probe_res["provider"]` is
always canonical, because capacity.detect() runs every id through
capacity.normalize_provider(). The stamp compared the two raw strings:

    elif isinstance(available, int) and available > 0 \\
            and probe_provider == routed_provider:

'deepseek' != 'deepseek-direct', so that branch was FALSE on every DeepSeek
route -- the department default for authoring, prompt_authoring and the
reasoning classes. A real measured ceiling (2,500 for Flash, 500 for Pro) was
discarded and the P4-PROMPT fan-out silently ran at DEFAULT_MAX_WORKERS.

WHY IT WAS NEVER CAUGHT: tests/test_fix11_mode_axis.py builds its probe fixture
from `_DS_PROVIDER = model_router.resolve_alias(...)["provider"]` -- the ROUTER's
spelling. Feeding the router's own string back in makes the raw equality true, so
those tests never exercise the mismatch that a real capacity.probe() produces.
These tests use capacity.PROVIDER_DEEPSEEK_DIRECT -- the value the real probe
actually returns -- so the two sides differ exactly as they do in production.

THE FIX: fold BOTH sides through capacity.normalize_provider (the one cap-table
authority) before comparing, and make an UNRESOLVABLE identity loud on stderr
and in the phase sidecar instead of a quiet default.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402


#: What the CATALOG spells (what reaches route["provider"]).
_ROUTED_SPELLING = model_router.resolve_alias("deepseek-v4-pro")["provider"]
#: What the real capacity probe returns (always canonical).
_PROBED_SPELLING = capacity.PROVIDER_DEEPSEEK_DIRECT


def _wired(provider, models):
    return {"provider": provider, "consented": True, "detected": True,
            "presence": True, "wired_models": list(models)}


def _env(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES",
                model_router.MODE_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    (cfg / resource_profile.PROFILE_FILENAME).write_text(json.dumps({
        ".schema_version": 1,
        "providers": {
            "deepseek-direct": _wired("deepseek-direct",
                                      ["deepseek-v4-flash", "deepseek-v4-pro"]),
            "openrouter": _wired("openrouter",
                                 ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"]),
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }, indent=2), encoding="utf-8")
    return cfg


def _stamp(monkeypatch, tmp_path, *, probe_provider, available=500,
           status="measured"):
    _env(monkeypatch, tmp_path)
    monkeypatch.setattr(capacity, "probe", lambda *a, **k: {
        "available": available, "provider": probe_provider,
        "status": status, "detection_source": "test-fixture"})
    return dispatcher._prompt_routing_stamp(run_dir=tmp_path)


# ---------------------------------------------------------------------------
# 0. THE PREMISE, measured rather than asserted from memory: the two sides
#    really do disagree on the shipped table. If a future catalog respelling
#    makes them agree, this test says so instead of letting the rest of the
#    file quietly stop testing anything.
# ---------------------------------------------------------------------------
def test_the_two_sides_really_do_spell_the_provider_differently():
    assert _ROUTED_SPELLING != _PROBED_SPELLING, (
        "the catalog and the capacity probe now agree on the provider "
        "spelling; this file's fixtures no longer reproduce DEFECT 5 -- "
        f"routed={_ROUTED_SPELLING!r} probed={_PROBED_SPELLING!r}")
    assert capacity.normalize_provider(_ROUTED_SPELLING) == \
        capacity.normalize_provider(_PROBED_SPELLING), (
        "both spellings must still fold onto ONE cap-table identity")


# ---------------------------------------------------------------------------
# 1. THE DEFECT: a real measurement must survive the spelling difference.
# ---------------------------------------------------------------------------
def test_real_probe_spelling_still_yields_a_measured_capacity(monkeypatch,
                                                              tmp_path):
    stamp = _stamp(monkeypatch, tmp_path, probe_provider=_PROBED_SPELLING,
                   available=500)

    assert stamp["capacity_status"].startswith("measured"), (
        "DEFECT 5: the routed provider and the probed provider are the SAME "
        f"provider ({_ROUTED_SPELLING!r} vs {_PROBED_SPELLING!r}, both "
        "cap-table 'deepseek-direct'), but the stamp compared raw strings and "
        f"silently discarded the measurement: {stamp}")
    assert stamp["capacity_source"] == "test-fixture", (
        "the width must be sourced from the probe, not from the "
        f"dispatcher default: {stamp}")
    # The real measurement (500) is then legitimately cut by the FIX 11 mode
    # ceiling -- a CAP, applied to a width that was actually measured. What
    # matters is that the wave is no longer pinned to the 8-wide dispatcher
    # default the string mismatch forced on every DeepSeek run.
    assert stamp["measured_capacity"] == stamp["mode_cap"]["width"], stamp
    assert stamp["measured_capacity"] > dispatcher.DEFAULT_MAX_WORKERS, (
        "the measured ceiling was discarded and the wave fell back to the "
        f"dispatcher default width: {stamp}")


# ---------------------------------------------------------------------------
# 2. NO REGRESSION: a probe about a genuinely DIFFERENT provider is still
#    rejected. Normalising identity must not turn into accepting anything.
# ---------------------------------------------------------------------------
def test_a_genuinely_different_provider_is_still_not_a_measurement(monkeypatch,
                                                                   tmp_path):
    stamp = _stamp(monkeypatch, tmp_path,
                   probe_provider=capacity.PROVIDER_OLLAMA_CLOUD, available=3)

    assert not stamp["capacity_status"].startswith("measured"), stamp
    assert stamp["capacity_status"] == "probe-not-measured", stamp
    assert stamp["measured_capacity"] != 3, (
        "an ollama-cloud measurement must never be attributed to a deepseek "
        f"route: {stamp}")


# ---------------------------------------------------------------------------
# 3. LOUD, never silent: an identity the cap table cannot resolve is announced
#    on stderr AND labelled in the stamp -- it is not a quiet default.
# ---------------------------------------------------------------------------
def test_unresolvable_provider_identity_is_loud(monkeypatch, tmp_path, capsys):
    stamp = _stamp(monkeypatch, tmp_path, probe_provider="acme-llm-9000",
                   available=42)

    assert capacity.normalize_provider("acme-llm-9000") is None, (
        "fixture premise: this id must be outside the cap table")
    assert stamp["capacity_status"] == "provider-unresolved", stamp
    err = capsys.readouterr().err
    assert "UNRESOLVABLE" in err, (
        "an unresolvable provider identity must be announced, never a silent "
        f"fallback; stderr was: {err!r}")
    assert "acme-llm-9000" in err, err


# ---------------------------------------------------------------------------
# 4. The stamp records BOTH spellings and BOTH canonical forms, so the audit
#    trail can never again hide which two strings were compared.
# ---------------------------------------------------------------------------
def test_the_stamp_records_what_was_actually_compared(monkeypatch, tmp_path):
    stamp = _stamp(monkeypatch, tmp_path, probe_provider=_PROBED_SPELLING)

    assert stamp["routed_provider"] == _ROUTED_SPELLING, stamp
    assert stamp["probe_provider"] == _PROBED_SPELLING, stamp
    assert stamp["routed_provider_canonical"] == \
        capacity.PROVIDER_DEEPSEEK_DIRECT, stamp
    assert stamp["probe_provider_canonical"] == \
        capacity.PROVIDER_DEEPSEEK_DIRECT, stamp
