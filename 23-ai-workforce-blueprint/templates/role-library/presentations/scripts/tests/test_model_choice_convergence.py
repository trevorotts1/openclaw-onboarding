#!/usr/bin/env python3
"""test_model_choice_convergence.py -- the B28/B40 convergence onto
B27's unified model-choice record (profile["model_choices"]).

WHAT THIS FILE PINS, mechanically:

  1. A ROUTE DECISION LANDS IN THE UNIFIED RECORD. When the intake
     records the client's route-honesty decision (FIX 18), the
     recommendation the block showed is recorded on the family row of
     the Ollama route it was shown against, with the client's response
     ("accepted" / "declined") as the entry's response -- through
     resource_profile's own model-choice writers, in the same profile
     write as the decision itself.
  2. A FRESHNESS DECISION LANDS IN THE SAME RECORD. When the intake
     records a freshness decision (FIX 31), the offered successor is
     recorded as a recommendation shown on its provider family's row;
     switch records "accepted" AND the family's new selection (written
     through record_model_choice, source "selected"), keep records
     "declined", defer leaves the entry standing at "offered", and a
     refused switch records the acceptance without inventing a
     selection that never happened.
  3. NOTHING ELSE MOVED. Each module's own record (route_honesty, the
     freshness interview log, the pending list) carries exactly what it
     carried before the convergence; no selection is ever written by a
     recommendation response (owner decision 4: a recommendation is
     guidance, never a hidden prescription).
  4. NO OFFER, NO RECORD. A decision writer called with nothing
     outstanding writes nothing to the unified record either.

On the pre-convergence tree every landing assertion below fails (the
decision writers never touched model_choices; the record is absent),
while the no-offer assertions pass on both trees -- that asymmetry is
the negative control, and it is exercised by running this file against
pristine main.

Unit-level: no network (catalog traffic is stubbed at capacity's
transport seam, the FIX 31 pattern), no spend, no engine. Every profile
lives in a tmp config dir; the operator's live profile is never read or
written. API keys below are fake presence markers, never credentials.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity as cap  # noqa: E402
from presentation_job import model_freshness as mf  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402
from presentation_job import route_honesty as rh  # noqa: E402

OLLAMA = "ollama-cloud"
DS = "deepseek-direct"
OR = "openrouter"
TIER_20 = cap.PLAN_OLLAMA_20
TIER_100 = cap.PLAN_OLLAMA_100
DECK = 55

_URL_MARKERS = {DS: "api.deepseek.com", OR: "openrouter.ai",
                OLLAMA: "ollama.com"}


@pytest.fixture(autouse=True)
def _rig(monkeypatch):
    cap._INVENTORY_SNAPSHOT.clear()
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


def _choices(cfg: Path):
    return rp.load_profile(cfg).get("model_choices")


def _row(cfg: Path, family: str):
    rows = [r for r in (_choices(cfg) or [])
            if isinstance(r, dict) and r.get("provider_family") == family]
    assert len(rows) == 1, _choices(cfg)
    return rows[0]


# ---------------------------------------------------------------------------
# The route decision (FIX 18 -> the unified record)
# ---------------------------------------------------------------------------
def _seed_route(cfg: Path, tier, workhorse="glm-5.3-flash@ollama-cloud"):
    """The FIX 18 seed, the production way: providers probed in, the
    tier answer and the model plan through their own recorders."""
    cfg.mkdir(parents=True, exist_ok=True)
    prof = rp.new_profile()
    prof["providers"][OLLAMA] = _wired(OLLAMA, ["glm-5.3-flash", "glm-5.3"])
    prof["providers"][OR] = _wired(
        OR, ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"])
    prof["providers"][DS] = _wired(DS, ["deepseek-flash"])
    rp.save_profile(prof, cfg)
    if tier:
        rp.record_plan_answer(OLLAMA, tier, cfg)
    if workhorse:
        rp.record_model_plan({"workhorse": workhorse},
                             source="interview", config_dir=cfg)
    return rp.load_profile(cfg)


def _show_route_block(cfg: Path):
    prof = rp.load_profile(cfg)
    assert rh.block_owed(prof)
    sig = rh.selection_signature(prof)
    rh.note_block_shown(deck_slides=DECK, config_dir=cfg)
    return sig


def test_route_decline_lands_the_decision_in_model_choices(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_route(cfg, TIER_100)
    sig = _show_route_block(cfg)
    rec = rh.record_route_decision(pre_signature=sig, pre_owed=True,
                                   deck_slides=DECK, config_dir=cfg)
    # The module's own record is exactly what it was before the fold.
    assert rec["status"] == "declined"
    loaded = rp.load_profile(cfg)
    assert rh.current_record(loaded)["status"] == "declined"
    # The decision landed in the unified record, in its shape.
    row = _row(cfg, OLLAMA)
    assert row["selection"] is None  # a response never writes a selection
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["model"] == "glm-5.3-flash"
    assert entry["reason"] == rh.MODEL_CHOICES_REASON
    assert entry["response"] == "declined"
    assert entry["responded_at"]
    # The entry is stamped when the block was actually shown.
    assert entry["shown_at"] == rh.current_record(loaded)["shown_at"]
    assert rp.effective_model_choice(OLLAMA, profile=loaded) is None


def test_route_accept_lands_the_decision_in_model_choices(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_route(cfg, TIER_20)
    sig = _show_route_block(cfg)
    rp.record_model_plan({"workhorse": "z-ai/glm-5.3-flash@openrouter"},
                         source="interview", config_dir=cfg)
    rec = rh.record_route_decision(pre_signature=sig, pre_owed=True,
                                   config_dir=cfg)
    assert rec["status"] == "accepted"
    # The entry sits on the row of the route the recommendation was
    # shown against, even though the client is no longer on it.
    row = _row(cfg, OLLAMA)
    assert row["selection"] is None
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    assert entries[0]["model"] == "glm-5.3-flash"
    assert entries[0]["response"] == "accepted"
    assert entries[0]["responded_at"]


def test_route_reopened_decision_appends_a_fresh_unified_entry(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_route(cfg, TIER_100)
    sig = _show_route_block(cfg)
    rh.record_route_decision(pre_signature=sig, pre_owed=True,
                             config_dir=cfg)
    # The client changes their Ollama selection: the block re-opens and
    # the new decision appends a fresh entry; history is never rewritten.
    rp.record_model_plan({"workhorse": "glm-5.3@ollama-cloud"},
                         source="interview", config_dir=cfg)
    sig2 = _show_route_block(cfg)
    rh.record_route_decision(pre_signature=sig2, pre_owed=True,
                             config_dir=cfg)
    entries = _row(cfg, OLLAMA)["recommendations_shown"]
    assert [e["model"] for e in entries] == ["glm-5.3-flash", "glm-5.3"]
    assert [e["response"] for e in entries] == ["declined", "declined"]


def test_route_no_offer_writes_no_model_choices(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_route(cfg, TIER_100)
    assert rh.record_route_decision(pre_owed=False,
                                    config_dir=cfg) is None
    assert "model_choices" not in rp.load_profile(cfg)


# ---------------------------------------------------------------------------
# The freshness decision (FIX 31 -> the unified record)
# ---------------------------------------------------------------------------
def _seed_fresh(cfg: Path, providers: dict, plan: dict):
    cfg.mkdir(parents=True, exist_ok=True)
    prof = rp.new_profile()
    for provider, models in providers.items():
        prof["providers"][provider] = _wired(provider, models)
    rp.save_profile(prof, cfg)
    rp.record_model_plan(plan, source="interview", config_dir=cfg)
    return rp.load_profile(cfg)


def _transport(mapping: dict):
    def stub(url, key=None, timeout=8.0):
        for provider, marker in _URL_MARKERS.items():
            if marker not in url or provider not in mapping:
                continue
            spec = mapping[provider]
            if isinstance(spec, Exception):
                raise spec
            status, ids = spec if isinstance(spec, tuple) else (200, spec)
            items = [{"id": mid} for mid in ids]
            return status, json.dumps({"data": items}).encode()
        return 0, b"unmapped provider URL"

    return stub


def _intake(cfg: Path, transport):
    cap._INVENTORY_SNAPSHOT.clear()
    return mf.intake_check(config_dir=cfg, transport=transport)


def _fresh_log(cfg: Path):
    return rp.load_profile(cfg)["interview"]["model_freshness"]


DS_PLAN = {"workhorse": "deepseek-v4.1-flash@deepseek-direct"}
DS_CATALOG = ["deepseek-v4.1-flash", "deepseek-flash", "deepseek-v5-flash"]


def test_freshness_keep_lands_the_decision_in_model_choices(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_fresh(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]},
                DS_PLAN)
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    offer = verdict["offers"][0]
    assert offer["successor_model"] == "deepseek-v5-flash"
    result = mf.record_freshness_decision(offer["check_id"], "keep",
                                          config_dir=cfg)
    assert result["outcome"] == "keep"
    # The module's own records are exactly what they were before the fold.
    decisions = [r for r in _fresh_log(cfg) if r["kind"] == "decision"]
    assert decisions[-1]["outcome"] == "keep"
    assert mf.pending_offers(rp.load_profile(cfg)) == []
    # The decision landed in the unified record, in its shape.
    row = _row(cfg, DS)
    assert row["selection"] is None
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["model"] == "deepseek-v5-flash"
    assert entry["reason"] == mf.MODEL_CHOICES_REASON
    assert entry["response"] == "declined"
    assert entry["responded_at"]
    assert entry["shown_at"] == verdict["checked_at"]
    assert rp.effective_model_choice(DS, profile=rp.load_profile(cfg)) is None


def test_freshness_switch_lands_acceptance_and_selection(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_fresh(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]},
                {"workhorse": "deepseek-v4.1-flash@deepseek-direct",
                 "judge": "deepseek-flash@deepseek-direct"})
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "switch", config_dir=cfg)
    assert result["outcome"] == "switch", result
    # The plan moved through record_model_plan, as before the fold.
    plan = rp.model_plan(rp.load_profile(cfg))
    assert plan["workhorse"] == {"provider": DS,
                                 "model": "deepseek-v5-flash"}
    assert plan["judge"] == {"provider": DS, "model": "deepseek-flash"}
    # The unified record carries the acceptance AND the selection the
    # client actually made, written as a selection (source "selected").
    row = _row(cfg, DS)
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    assert entries[0]["model"] == "deepseek-v5-flash"
    assert entries[0]["response"] == "accepted"
    selection = rp.effective_model_choice(DS, profile=rp.load_profile(cfg))
    assert selection["model"] == "deepseek-v5-flash"
    assert selection["source"] == "selected"


def test_freshness_defer_leaves_the_unified_entry_offered(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_fresh(cfg, {DS: ["deepseek-v4.1-flash", "deepseek-flash"]},
                DS_PLAN)
    verdict = _intake(cfg, _transport({DS: DS_CATALOG}))
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "defer", config_dir=cfg)
    assert result["outcome"] == "defer"
    # The offer still waits, in both records.
    assert len(mf.pending_offers(rp.load_profile(cfg))) == 1
    row = _row(cfg, DS)
    assert row["selection"] is None
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    assert entries[0]["model"] == "deepseek-v5-flash"
    assert entries[0]["response"] == "offered"
    assert entries[0].get("responded_at") is None


def test_freshness_switch_refused_records_acceptance_no_selection(tmp_path):
    cfg = tmp_path / "cfg"
    # The FT-13 staging: the public catalog lists the successor; the
    # client's own wired inventory does not carry it, so the accepted
    # switch is refused by validation.
    _seed_fresh(cfg, {OR: ["z-ai/glm-5.3-flash"]},
                {"workhorse": "z-ai/glm-5.3-flash@openrouter"})
    verdict = _intake(cfg, _transport(
        {OR: ["z-ai/glm-5.3-flash", "z-ai/glm-6-flash"]}))
    assert [o["successor_model"] for o in verdict["offers"]] == [
        "z-ai/glm-6-flash"]
    prof = rp.load_profile(cfg)
    prof["providers"][OR]["wired_models"] = ["z-ai/glm-5.3-flash"]
    rp.save_profile(prof, cfg)
    result = mf.record_freshness_decision(
        verdict["offers"][0]["check_id"], "switch", config_dir=cfg)
    assert result["outcome"] == "switch-refused"
    # The client's response was acceptance; the refusal is validation's
    # act. The unified entry records the acceptance, and NO selection is
    # invented for a switch that never happened.
    row = _row(cfg, OR)
    entries = row["recommendations_shown"]
    assert len(entries) == 1
    assert entries[0]["model"] == "z-ai/glm-6-flash"
    assert entries[0]["response"] == "accepted"
    assert rp.effective_model_choice(OR, profile=rp.load_profile(cfg)) is None
    plan = rp.model_plan(rp.load_profile(cfg))
    assert plan["workhorse"]["model"] == "z-ai/glm-5.3-flash"


def test_freshness_unknown_check_id_writes_no_model_choices(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_fresh(cfg, {DS: ["deepseek-v4.1-flash"]}, DS_PLAN)
    assert mf.record_freshness_decision(
        "2000-01-01T00:00:00+00:00|deepseek-direct|deepseek-flash",
        "keep", config_dir=cfg) is None
    assert "model_choices" not in rp.load_profile(cfg)


# ---------------------------------------------------------------------------
# The unified record survives the store, on disk, verbatim
# ---------------------------------------------------------------------------
def test_unified_record_survives_the_store_round_trip(tmp_path):
    cfg = tmp_path / "cfg"
    _seed_route(cfg, TIER_100)
    sig = _show_route_block(cfg)
    rh.record_route_decision(pre_signature=sig, pre_owed=True,
                             config_dir=cfg)
    raw = json.loads((cfg / "resource_profile.json").read_text())
    rows = raw["model_choices"]
    assert len(rows) == 1
    assert rows[0]["provider_family"] == OLLAMA
    assert rows[0]["recommendations_shown"][0]["response"] == "declined"
    loaded = rp.load_profile(cfg)
    assert loaded["model_choices"] == rows
