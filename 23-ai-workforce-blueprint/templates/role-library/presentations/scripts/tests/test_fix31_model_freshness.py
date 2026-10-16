#!/usr/bin/env python3
"""test_fix31_model_freshness.py -- FIX 31: the pre-run model freshness
check (B11 design, acceptance tests FT-01 to FT-20).

Every catalog response is injected through capacity's transport seam
(probe_transport / refresh_provider_inventory's transport= parameter);
no test touches the network. Profiles live in tmp config dirs; the
operator's live profile is never read or written. API keys below are
fake presence markers for the probe's key-presence check, never real
credentials.

What is pinned, per the design:
  * the successor rule is structural (same stem + variant, strictly
    greater version, no exclusion tag, not expired) -- never name
    matching alone (FT-04..FT-08, FT-14, FT-17);
  * never auto-switch, never block: offline is a verdict about the
    check, the run proceeds on the recorded selection (FT-01, FT-11,
    FT-12, FT-19);
  * the three outcomes are recorded exactly (switch through
    record_model_plan only, keep suppresses the tuple, defer keeps it
    pending) and a refused switch is a recorded refusal, not a silent
    fallback (FT-02, FT-03, FT-09, FT-13);
  * cached readings are honest about being cached, and stale readings
    ground nothing (FT-10, FT-11);
  * the two launch paths leave the same record (FT-18).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity as cap  # noqa: E402
from presentation_job import launch_plan  # noqa: E402
from presentation_job import launcher  # noqa: E402
from presentation_job import model_freshness as mf  # noqa: E402
from presentation_job import model_router as router  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402

DRIVER = SCRIPTS / "deck-intake-driver.py"
BANK = SCRIPTS.parent / "intake" / "deck-intake-questions.json"

DS = "deepseek-direct"
OR = "openrouter"
OL = "ollama-cloud"

_URL_MARKERS = {DS: "api.deepseek.com", OR: "openrouter.ai", OL: "ollama.com"}


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _rig(monkeypatch):
    cap._INVENTORY_SNAPSHOT.clear()
    # Fake presence markers, shaped like real keys: the router's FIX 114
    # key gate (secret_helper.looks_like_real_key) is a real surface in
    # the dispatch tests below and refuses placeholder-shaped values.
    monkeypatch.setenv("DEEPSEEK_API_KEY",
                       "sk-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d")
    monkeypatch.setenv("OPENROUTER_API_KEY",
                       "sk-or-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7a8b")
    monkeypatch.setenv("OLLAMA_API_KEY",
                       "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7a8b9c0d")
    yield
    cap._INVENTORY_SNAPSHOT.clear()


def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


def _seed(cfg: Path, providers: dict, plan: dict | None = None):
    """A profile the production way: providers in the store, the model
    plan recorded through record_model_plan (the intake writer)."""
    cfg.mkdir(parents=True, exist_ok=True)
    prof = rp.new_profile()
    for provider, models in providers.items():
        prof["providers"][provider] = _wired(provider, models)
    rp.save_profile(prof, cfg)
    if plan:
        rp.record_model_plan(plan, source="interview", config_dir=cfg)
    return rp.load_profile(cfg)


def _transport(mapping: dict, extras: dict | None = None):
    """A capacity transport stub. mapping: provider -> list of model ids
    | (status, list) | Exception (raised, i.e. transport failure).
    extras: model id -> extra payload fields (pricing, expiration_date,
    created) merged into that id's catalog item."""
    extras = extras or {}

    def stub(url, key=None, timeout=8.0):
        for provider, marker in _URL_MARKERS.items():
            if marker not in url or provider not in mapping:
                continue
            spec = mapping[provider]
            if isinstance(spec, Exception):
                raise spec
            status, ids = spec if isinstance(spec, tuple) else (200, spec)
            items = []
            for mid in ids:
                item = {"id": mid}
                item.update(extras.get(mid) or {})
                items.append(item)
            return status, json.dumps({"data": items}).encode()
        return 0, b"unmapped provider URL"

    return stub


def _check(cfg: Path, transport):
    cap._INVENTORY_SNAPSHOT.clear()
    return mf.check_freshness(config_dir=cfg, transport=transport)


def _intake(cfg: Path, transport):
    cap._INVENTORY_SNAPSHOT.clear()
    return mf.intake_check(config_dir=cfg, transport=transport)


def _row(verdict, provider=DS):
    rows = [r for r in verdict["checks"] if r["provider"] == provider]
    assert len(rows) == 1, verdict["checks"]
    return rows[0]


def _log(cfg: Path):
    return rp.load_profile(cfg)["interview"]["model_freshness"]


def _freshness_summary(cfg: Path):
    return rp.load_profile(cfg).get("model_freshness") or {}


DS_PLAN = {"workhorse": "deepseek-v4.1-flash@deepseek-direct"}
DS_CATALOG = ["deepseek-v4.1-flash", "deepseek-flash", "deepseek-v5-flash"]


# ---------------------------------------------------------------------------
# The parser + worked examples (design 3.4)
# ---------------------------------------------------------------------------
def test_parse_worked_examples():
    p = mf.parse_model_id("deepseek-v4.1-flash")
    assert (p["stem"], p["version"], p["variant"]) == ("deepseek", (4, 1), "flash")
    p = mf.parse_model_id("deepseek-v5-pro")
    assert (p["stem"], p["version"], p["variant"]) == ("deepseek", (5,), "pro")
    p = mf.parse_model_id("z-ai/glm-5.3-flash-20261001")
    assert (p["stem"], p["version"], p["variant"]) == ("glm", (5, 3), "flash")
    p = mf.parse_model_id("glm-5.3-flash:cloud")
    assert p["tags"] == ["cloud"] and p["version"] == (5, 3)
    p = mf.parse_model_id("deepseek-flash")
    assert p["version"] is None and p["variant"] == "flash"
    p = mf.parse_model_id("kimi-k3")
    assert p["version"] is None
    p = mf.parse_model_id("deepseek-v5-flash-preview")
    assert "preview" in p["tags"]
    assert mf._version_cmp((5,), (4, 1)) > 0
    assert mf._version_cmp((5, 3), (5, 10)) < 0
    assert mf.display_name("deepseek-v4.1-flash") == "DeepSeek V4.1 Flash"


def test_defaults_are_derived_from_router_and_catalog():
    sels = mf.effective_selections({"providers": {}})
    pairs = {(s["provider"], s["selected_model"]) for s in sels}
    assert pairs == {(DS, "deepseek-v4.1-flash"), (DS, "deepseek-flash")}
    assert all(s["selected_source"] == "department-default" for s in sels)


# ---------------------------------------------------------------------------
# FT-04..FT-08, FT-14, FT-17: the structural successor rule
# ---------------------------------------------------------------------------
def test_ft04_no_successor_is_fresh_and_logged(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: ["deepseek-v4.1-flash",
                                            "deepseek-v3-flash",
                                            "deepseek-flash"]}))
    row = _row(verdict)
    assert verdict["status"] == "fresh"
    assert row["status"] == "fresh" and row["successor_model"] is None
    assert verdict["offers"] == []
    assert mf.pending_offers(rp.load_profile(cfg)) == []
    checks = [r for r in _log(cfg) if r["kind"] == "check"]
    assert len(checks) == 1 and checks[0]["status"] == "fresh"


def test_ft05_tagged_candidate_is_excluded_and_noted(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: ["deepseek-v4.1-flash",
                                            "deepseek-v5-flash-preview"]}))
    row = _row(verdict)
    assert row["status"] == "fresh" and verdict["offers"] == []
    assert "excluded" in row["note"] and "preview" in row["note"]


def test_ft06_pro_is_not_a_successor_of_flash(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: ["deepseek-v4.1-flash",
                                            "deepseek-v5-pro"]}))
    assert _row(verdict)["status"] == "fresh" and verdict["offers"] == []


def test_ft07_rerelease_is_not_a_successor(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {OR: ["z-ai/glm-5.3-flash"]},
          {"workhorse": "z-ai/glm-5.3-flash@openrouter"})
    verdict = _intake(cfg, _transport(
        {OR: ["z-ai/glm-5.3-flash", "glm-5.3-flash-20261001"]},
        extras={"z-ai/glm-5.3-flash": {"created": 1799999999}}))
    row = _row(verdict, OR)
    assert row["status"] == "fresh" and verdict["offers"] == []
    assert "re-release" in (row["note"] or "")


def test_ft08_other_families_are_not_successors(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: ["deepseek-v4.1-flash",
                                            "kimi-k3", "glm-6-flash"]}))
    assert _row(verdict)["status"] == "fresh" and verdict["offers"] == []


def test_ft14_legacy_and_unversioned_selections_get_no_offer(tmp_path):
    # (a) a saved deepseek-v4-flash folds to deepseek-flash: unversioned.
    cfg = tmp_path / "cfg-a"
    cfg.mkdir(parents=True)
    prof = rp.new_profile()
    prof["providers"][DS] = _wired(DS, ["deepseek-v4-flash", "deepseek-flash"])
    prof["model_plan"] = {
        "workhorse": {"provider": DS, "model": "deepseek-v4-flash"},
        "reasoning": None, "judge": None, "thinking": None,
        "floor_waivers": [], "source": "interview"}
    rp.save_profile(prof, cfg)
    verdict = _check(cfg, _transport({DS: ["deepseek-v4-flash",
                                            "deepseek-v5-flash"]}))
    row = _row(verdict)
    assert row["status"] == "fresh" and verdict["offers"] == []
    assert row["note"] == "unversioned-selection"
    # (b) deepseek-flash itself, with a v5 in the catalog: same rule.
    cfg2 = tmp_path / "cfg-b"
    _seed(cfg2, {DS: ["deepseek-flash"]},
          {"workhorse": "deepseek-flash@deepseek-direct"})
    verdict2 = _check(cfg2, _transport({DS: ["deepseek-flash",
                                             "deepseek-v5-flash"]}))
    row2 = _row(verdict2)
    assert row2["status"] == "fresh" and verdict2["offers"] == []
    assert row2["note"] == "unversioned-selection"


def test_ft17_expired_successor_is_not_offered(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {OR: ["z-ai/glm-5.3-flash"]},
          {"workhorse": "z-ai/glm-5.3-flash@openrouter"})
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    verdict = _intake(cfg, _transport(
        {OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]},
        extras={"z-ai/glm-6-flash": {
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "expiration_date": yesterday}}))
    row = _row(verdict, OR)
    assert row["status"] == "fresh" and verdict["offers"] == []
    assert "expired" in (row["note"] or "")


# ---------------------------------------------------------------------------
# FT-02 / FT-03: the decision outcomes against a declared plan
# ---------------------------------------------------------------------------
def test_ft02_decline_suppresses_the_tuple_not_the_future(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    assert [o["successor_model"] for o in verdict["offers"]] == ["deepseek-v5-flash"]
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "keep", config_dir=cfg)
    assert result["outcome"] == "keep"
    decisions = [r for r in _log(cfg) if r["kind"] == "decision"]
    assert decisions[-1]["outcome"] == "keep"
    assert decisions[-1]["successor_model"] == "deepseek-v5-flash"
    prof = rp.load_profile(cfg)
    assert rp.model_plan(prof)["workhorse"]["model"] == "deepseek-v4.1-flash"
    assert mf.pending_offers(prof) == []
    # Same catalog again: no offer for the declined successor.
    verdict2 = _intake(cfg, _transport({DS: DS_CATALOG}))
    assert verdict2["offers"] == []
    # A strictly newer successor is a new question.
    verdict3 = _intake(cfg, _transport({DS: DS_CATALOG + ["deepseek-v6-flash"]}))
    assert [o["successor_model"] for o in verdict3["offers"]] == ["deepseek-v6-flash"]


def test_ft03_accept_switches_through_record_model_plan(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]},
          {"workhorse": "deepseek-v4.1-flash@deepseek-direct",
           "judge": "deepseek-flash@deepseek-direct"})
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "switch", config_dir=cfg)
    assert result["outcome"] == "switch", result
    prof = rp.load_profile(cfg)
    plan = rp.model_plan(prof)
    assert plan["workhorse"] == {"provider": DS, "model": "deepseek-v5-flash"}
    # PRESERVE-BEFORE-OVERLAY: the untouched slot is verbatim.
    assert plan["judge"] == {"provider": DS, "model": "deepseek-flash"}
    assert any(r.get("kind") == "decision" and r.get("outcome") == "switch"
               for r in _log(cfg))
    # The switch landed through record_model_plan: its own audit row in
    # interview.model_plan names the successor on the workhorse slot.
    audit = prof["interview"]["model_plan"]
    assert audit[-1]["declared"]["workhorse"]["model"] == "deepseek-v5-flash"
    # A router decision for an authoring phase routes to the successor.
    phase = next(pid for pid, c in router.PHASE_CAPABILITY.items()
                 if c == "authoring")
    decision = router.resolve_route(phase, profile=prof)
    assert decision["route"] == {"provider": DS, "model": "deepseek-v5-flash"}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cap._INVENTORY_SNAPSHOT.clear()
    launched = mf.launch_check(run_dir, config_dir=cfg)
    eff = {(s["provider"], s["selected_model"])
           for s in launched["run_record"]["effective_selection"]}
    assert (DS, "deepseek-v5-flash") in eff


def test_ft13_refused_switch_is_recorded_and_the_run_proceeds(tmp_path):
    cfg = tmp_path / "cfg"
    # The public catalog lists the successor; the client's own wired
    # inventory does not carry it, so record_model_plan must refuse.
    _seed(cfg, {OR: ["z-ai/glm-5.3-flash"]},
          {"workhorse": "z-ai/glm-5.3-flash@openrouter"})
    verdict = _intake(cfg, _transport(
        {OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]}))
    assert [o["successor_model"] for o in verdict["offers"]] == ["z-ai/glm-6-flash"]
    # The divergence FT-13 names: OpenRouter's /models list is PUBLIC --
    # it lists every model the provider serves, not the models this
    # client's account has unlocked. The freshness refresh persisted
    # that public list into the profile (capacity's designed behavior),
    # so the fixture restores the account's own wired inventory -- the
    # inventory record_model_plan validates against -- to what the
    # client's account actually carries. With the successor absent
    # there, the accepted switch cannot be applied.
    prof = rp.load_profile(cfg)
    prof["providers"][OR]["wired_models"] = ["z-ai/glm-5.3-flash"]
    rp.save_profile(prof, cfg)
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "switch", config_dir=cfg)
    assert result["outcome"] == "switch-refused"
    assert result["detail"]
    assert "could not be applied" in result["message"]
    prof = rp.load_profile(cfg)
    assert rp.model_plan(prof)["workhorse"]["model"] == "z-ai/glm-5.3-flash"
    decisions = [r for r in _log(cfg) if r["kind"] == "decision"]
    assert decisions[-1]["outcome"] == "switch-refused"
    assert decisions[-1]["detail"] == result["detail"]


def test_offer_text_carries_the_openrouter_price_line_only_when_priced(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]},
          {"workhorse": "z-ai/glm-5.3-flash@openrouter"})
    extras = {
        "z-ai/glm-5.3-flash": {"pricing": {"prompt": "0.000000075",
                                           "completion": "0.00000025"}},
        "z-ai/glm-6-flash": {"pricing": {"prompt": "0.0000001",
                                         "completion": "0.0000004"}},
    }
    verdict = _check(cfg, _transport(
        {OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]}, extras=extras))
    text = verdict["offers"][0]["text"]
    assert "listed at $0.1 in / $0.4 out per million tokens" in text
    assert "your current model is listed at $0.075 in / $0.25 out" in text
    assert "recommended" not in text.lower()
    # Unpriced reading: the line is omitted entirely, never estimated.
    verdict2 = _check(cfg, _transport({OR: ["z-ai/glm-5.3-flash",
                                            "z-ai/glm-6-flash"]}))
    assert "listed at" not in verdict2["offers"][0]["text"]


# ---------------------------------------------------------------------------
# FT-09 / FT-19 / FT-20: defer, pending at launch, withdrawal
# ---------------------------------------------------------------------------
def test_ft09_defer_keeps_the_offer_waiting_and_represents_once(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "defer", config_dir=cfg)
    assert result["outcome"] == "defer"
    prof = rp.load_profile(cfg)
    pending = mf.pending_offers(prof)
    assert len(pending) == 1 and pending[0]["successor_model"] == "deepseek-v5-flash"
    assert rp.model_plan(prof)["workhorse"]["model"] == "deepseek-v4.1-flash"
    log_before = _log(cfg)
    # A resume of the run: launch records the check in the run record
    # only -- no new offer is presented inside the run that detected
    # it, and the narrow launch rule writes no profile rows for an
    # already-pending successor.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch_transport = _transport({DS: DS_CATALOG})
    with _patched_transport(monkeypatch_transport):
        launched = mf.launch_check(run_dir, config_dir=cfg)
    assert launched["run_record"]["status"] == "successor-available"
    assert _log(cfg) == log_before
    # The next run's intake presents the offer again, once.
    verdict2 = _intake(cfg, _transport({DS: DS_CATALOG}))
    assert [o["successor_model"] for o in verdict2["offers"]] == ["deepseek-v5-flash"]


def test_ft19_pending_offer_never_switches_silently_at_launch(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    _intake(cfg, _transport({DS: DS_CATALOG}))
    assert mf.pending_offers(rp.load_profile(cfg))
    plan_before = rp.model_plan(rp.load_profile(cfg))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with _patched_transport(_transport({DS: DS_CATALOG})):
        launched = mf.launch_check(run_dir, config_dir=cfg)
    record = launched["run_record"]
    assert record["decision"]["outcome"] == "pending"
    assert record["decision"]["successor_model"] == "deepseek-v5-flash"
    eff = {(s["provider"], s["selected_model"])
           for s in record["effective_selection"]}
    assert eff == {(DS, "deepseek-v4.1-flash")}
    assert rp.model_plan(rp.load_profile(cfg)) == plan_before


def test_ft20_withdrawn_successor_loses_its_pending_row(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    _intake(cfg, _transport({DS: DS_CATALOG}))
    assert mf.pending_offers(rp.load_profile(cfg))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with _patched_transport(_transport({DS: ["deepseek-v4.1-flash",
                                             "deepseek-flash"]})):
        launched = mf.launch_check(run_dir, config_dir=cfg)
    assert launched["run_record"]["status"] == "fresh"
    assert mf.pending_offers(rp.load_profile(cfg)) == []
    launch_rows = [r for r in _log(cfg)
                   if r["kind"] == "check" and r["surface"] == "launch"]
    assert launch_rows and "withdrawn" in (launch_rows[-1]["note"] or "")


def test_pending_offer_is_withdrawn_when_the_client_declares_it_directly(
        tmp_path):
    # The design does not name this edge (named in the manifest as a
    # judgment call): the client answers a later plan turn by declaring
    # the pending successor directly. The offer is moot -- removed and
    # logged at the next check, never presented against a selection
    # that already names the successor.
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash",
                     "deepseek-v5-flash"]}, DS_PLAN)
    _intake(cfg, _transport({DS: DS_CATALOG}))
    assert mf.pending_offers(rp.load_profile(cfg))
    rp.record_model_plan({"workhorse": "deepseek-v5-flash@deepseek-direct"},
                         source="interview", config_dir=cfg)
    _intake(cfg, _transport({DS: DS_CATALOG}))
    assert mf.pending_offers(rp.load_profile(cfg)) == []
    notes = " ".join(str(r.get("note") or "") for r in _log(cfg))
    assert "already the saved selection" in notes


# ---------------------------------------------------------------------------
# FT-10 / FT-11: the profile-cache layer and its TTL
# ---------------------------------------------------------------------------
def _seed_with_cache(cfg: Path, age_seconds: float):
    stamp = (datetime.datetime.now().astimezone()
             - datetime.timedelta(seconds=age_seconds)).isoformat(
                 timespec="seconds")
    cfg.mkdir(parents=True, exist_ok=True)
    prof = rp.new_profile()
    prof["providers"][DS] = _wired(
        DS, ["deepseek-v4.1-flash", "deepseek-flash", "deepseek-v5-flash"],
        probed_at=stamp)
    rp.save_profile(prof, cfg)
    rp.record_model_plan(DS_PLAN, source="interview", config_dir=cfg)
    return stamp


def test_ft10_offline_with_fresh_cache_offers_from_the_cache(tmp_path):
    cfg = tmp_path / "cfg"
    stamp = _seed_with_cache(cfg, age_seconds=300)
    verdict = _intake(cfg, _transport({DS: RuntimeError("network down")}))
    row = _row(verdict)
    assert row["status"] == "successor-available"
    assert row["catalog_source"] == "profile-cache"
    assert row["probed_at"] == stamp
    offer = verdict["offers"][0]
    assert offer["catalog_source"] == "profile-cache"
    assert f"Checked against the provider's catalog as read at {stamp}." \
        in offer["text"]
    assert mf.pending_offers(rp.load_profile(cfg))


def test_ft11_offline_with_stale_cache_is_unknown_offline(tmp_path):
    cfg = tmp_path / "cfg"
    stamp = _seed_with_cache(cfg, age_seconds=7200)
    verdict = _check(cfg, _transport({DS: RuntimeError("network down")}))
    row = _row(verdict)
    assert verdict["status"] == "unknown-offline"
    assert row["status"] == "unknown-offline"
    assert row["catalog_source"] == "profile-cache"
    assert row["probed_at"] == stamp
    assert verdict["offers"] == []


# ---------------------------------------------------------------------------
# FT-15 / FT-16: the record survives the store; the flag is a real off
# ---------------------------------------------------------------------------
def test_ft15_freshness_fields_survive_the_redaction_round_trip(tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "defer", config_dir=cfg)
    before = rp.load_profile(cfg)
    assert before["interview"]["model_freshness"]
    assert before["model_freshness"]["pending"]
    cfg2 = tmp_path / "cfg2"
    cfg2.mkdir()
    rp.save_profile(before, cfg2)
    after = rp.load_profile(cfg2)
    assert after["interview"]["model_freshness"] == \
        before["interview"]["model_freshness"]
    assert after["model_freshness"] == before["model_freshness"]


def test_ft16_flag_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(mf.FLAG_ENV, "0")
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    before = (cfg / "resource_profile.json").read_bytes()
    assert mf.check_freshness(config_dir=cfg,
                              transport=_transport({DS: DS_CATALOG})) is None
    assert mf.intake_check(config_dir=cfg,
                           transport=_transport({DS: DS_CATALOG})) is None
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert mf.launch_check(run_dir, config_dir=cfg) is None
    assert not (run_dir / ".model-freshness.json").exists()
    assert mf.pending_offers(rp.load_profile(cfg)) == []
    assert (cfg / "resource_profile.json").read_bytes() == before


def test_provider_with_no_model_list_reads_unknown_offline(tmp_path):
    # A client-declared provider this build has never heard of (adopted
    # onto the profile by record_model_plan, F17) exposes no model list
    # to check against: unknown-offline with the design's note.
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-flash"]},
          {"workhorse": "acme-1.0-pro@acme-llm"})
    verdict = _check(cfg, _transport({}))
    row = [r for r in verdict["checks"] if r["provider"] == "acme-llm"]
    assert len(row) == 1
    assert row[0]["status"] == "unknown-offline"
    assert row[0]["note"] == "provider exposes no model list"


def test_ollama_cloud_suffix_listing_is_a_successor(tmp_path):
    # Design worked example 7: the :cloud tag is neutral, never a
    # different family, and never disqualifying.
    cfg = tmp_path / "cfg"
    _seed(cfg, {OL: ["glm-5.3-flash"]},
          {"workhorse": "glm-5.3-flash@ollama-cloud"})
    verdict = _check(cfg, _transport(
        {OL: ["glm-5.3-flash:cloud", "glm-6-flash",
              "deepseek-v4.1-flash:cloud"]}))
    assert [o["successor_model"] for o in verdict["offers"]] == ["glm-6-flash"]


# ---------------------------------------------------------------------------
# FT-01 / FT-12 / FT-18: the real launcher paths
# ---------------------------------------------------------------------------
class _patched_transport:
    """Context manager: swap capacity's default transport (the seam
    launch_check, which takes no transport argument, resolves through
    probe_one_provider)."""

    def __init__(self, stub):
        self.stub = stub

    def __enter__(self):
        self._orig = cap.probe_transport
        cap.probe_transport = self.stub
        cap._INVENTORY_SNAPSHOT.clear()
        return self

    def __exit__(self, *exc):
        cap.probe_transport = self._orig
        cap._INVENTORY_SNAPSHOT.clear()
        return False


def _dispatch_rig(monkeypatch, tmp_path, cfg):
    """The no-config-box dispatch rig (the same shape as
    test_capacity_detection's): isolated detection, a stub engine that
    proves it ran by writing state.json, gates declared or rolled back
    so the freshness behavior is what is under test."""
    monkeypatch.setattr(cap, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(cap, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent.json",))
    monkeypatch.setattr(cap, "OPENCLAW_CONFIG",
                        tmp_path / "absent-openclaw.json")
    monkeypatch.setattr(cap, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.setenv("PRESENTATION_OCR_VERIFY", "0")
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "presentation_job.py").write_text(
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "rd = pathlib.Path(args[args.index('--run-dir') + 1])\n"
        "(rd / 'state.json').write_text(json.dumps({'stub': True}))\n",
        encoding="utf-8")
    monkeypatch.setattr(launcher, "resolve_scripts_dir",
                        lambda: scripts_dir)


def test_ft01_catalog_unreachable_dispatches_and_records_offline(
        monkeypatch, tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    plan_before = rp.model_plan(rp.load_profile(cfg))
    _dispatch_rig(monkeypatch, tmp_path, cfg)
    run_dir = tmp_path / "run"

    def _down(url, key=None, timeout=8.0):
        raise RuntimeError("catalog unreachable")

    monkeypatch.setattr(cap, "probe_transport", _down)
    pid = launcher.dispatch(str(run_dir), client="acme",
                            deck_type="standard", background=True)
    assert isinstance(pid, int) and pid > 0
    record = json.loads((run_dir / ".model-freshness.json").read_text())
    assert record["status"] == "unknown-offline"
    assert record["checks"]
    assert all(r["catalog_source"] == "none" for r in record["checks"])
    assert rp.model_plan(rp.load_profile(cfg)) == plan_before
    assert mf.pending_offers(rp.load_profile(cfg)) == []


def test_ft12_one_provider_down_never_contaminates_the_other(
        monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash"], OR: ["z-ai/glm-5.3-flash"]},
          {"workhorse": "deepseek-v4.1-flash@deepseek-direct",
           "judge": "z-ai/glm-5.3-flash@openrouter"})
    _dispatch_rig(monkeypatch, tmp_path, cfg)
    run_dir = tmp_path / "run"
    monkeypatch.setattr(cap, "probe_transport", _transport(
        {DS: (500, []), OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]}))
    pid = launcher.dispatch(str(run_dir), client="acme",
                            deck_type="standard", background=True)
    assert isinstance(pid, int) and pid > 0
    record = json.loads((run_dir / ".model-freshness.json").read_text())
    by_provider = {r["provider"]: r for r in record["checks"]}
    assert by_provider[DS]["status"] == "unknown-offline"
    assert "HTTP 500" in (by_provider[DS]["catalog_error"] or "")
    assert by_provider[OR]["status"] == "successor-available"
    assert by_provider[OR]["successor_model"] == "z-ai/glm-6-flash"
    assert record["status"] == "successor-available"
    pending = mf.pending_offers(rp.load_profile(cfg))
    assert [p["provider"] for p in pending] == [OR]
    out = capsys.readouterr().out
    assert "model freshness: GLM 6 Flash is available as the successor" in out
    assert "check offline for DeepSeek Direct" in out


def test_ft18_launch_paths_leave_the_same_record(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    _dispatch_rig(monkeypatch, tmp_path, cfg)
    monkeypatch.setattr(cap, "probe_transport",
                        _transport({DS: DS_CATALOG}))
    run_a = tmp_path / "run-a"
    pid = launcher.dispatch(str(run_a), client="acme",
                            deck_type="standard", background=True)
    assert isinstance(pid, int) and pid > 0
    cap._INVENTORY_SNAPSHOT.clear()
    run_b = tmp_path / "run-b"
    result = launch_plan.write_launch_plan(run_b)
    assert ".model-freshness.json" in result["wrote"]
    rec_a = json.loads((run_a / ".model-freshness.json").read_text())
    rec_b = json.loads((run_b / ".model-freshness.json").read_text())
    assert sorted(rec_a.keys()) == sorted(rec_b.keys())
    assert sorted(rec_a["checks"][0].keys()) == \
        sorted(rec_b["checks"][0].keys())

    def _verdicts(rec):
        return (rec["status"],
                [(r["provider"], r["selected_model"], r["status"],
                  r["successor_model"], r["catalog_source"])
                 for r in rec["checks"]],
                (rec["decision"] or {}).get("outcome"))

    assert _verdicts(rec_a) == _verdicts(rec_b)


# ---------------------------------------------------------------------------
# Hook A on the real driver surface
# ---------------------------------------------------------------------------
def _load_driver():
    spec = importlib.util.spec_from_file_location("deck_intake_driver_ft31",
                                                  DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def test_driver_hook_a_presents_pending_and_records_the_decision(
        tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "cfg"
    _seed(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]}, DS_PLAN)
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(cap, "probe_transport",
                        _transport({DS: DS_CATALOG}))
    # Detection at an earlier surface leaves the offer pending.
    _intake(cfg, _transport({DS: DS_CATALOG}))
    assert mf.pending_offers(rp.load_profile(cfg))
    driver = _load_driver()
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qdef = next(q for q in bank["questions"] if q["id"] == "resource_plan")

    # The turn presents the pending offer in its own output object,
    # attached after the route_honesty block's position.
    assert driver._emit_question(qdef, {}) == 0
    out = json.loads(capsys.readouterr().out)
    assert "model_freshness" in out
    assert "Model update available." in out["model_freshness"]["text"]
    assert "Model update available." in out["help"]

    # The client answers the turn and declines the offer with the
    # explicit label: the decision is recorded in the same turn, the
    # saved plan is untouched, and the turn's response carries the
    # decision back.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    args = SimpleNamespace(
        run_dir=run_dir, question_id="resource_plan",
        text="resource_plan: v4-flash; "
             "workhorse: deepseek-v4.1-flash@deepseek-direct; "
             "model_freshness: keep")
    assert driver.cmd_answer(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model_freshness"]["decision"]["outcome"] == "keep"
    prof = rp.load_profile(cfg)
    decisions = [r for r in prof["interview"]["model_freshness"]
                 if r["kind"] == "decision"]
    assert decisions[-1]["outcome"] == "keep"
    assert rp.model_plan(prof)["workhorse"]["model"] == "deepseek-v4.1-flash"
    assert mf.pending_offers(prof) == []
