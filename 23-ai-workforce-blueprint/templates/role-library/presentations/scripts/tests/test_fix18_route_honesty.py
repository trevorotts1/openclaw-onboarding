#!/usr/bin/env python3
"""test_fix18_route_honesty.py -- the numeric honesty block (FIX 18).

WHAT THIS FILE PINS, mechanically:

  1. THE NUMBERS COME FROM THE TABLES. The block renders the concurrency
     a client's Ollama tier actually buys, derived in THIS file from
     capacity.CAP_TABLE / capacity.ACCOUNT_LIMITS at test time -- if the
     table moves, the expected text moves with it, and a hardcoded number
     in the module would fail here.
  2. THE MANDATED COPY IS VERBATIM. The recommendation (owner ruling
     2026-10-13: recommend OpenRouter or DeepSeek Direct for best results,
     with the reason) is asserted as an exact literal string carried by
     THIS test, so any future edit to the module's copy fails loudly
     instead of drifting in silence. Same for the speed warning, the
     no-estimate note, and the choice note.
  3. NO DARK PATTERNS. The rendered block is swept for penalty / pressure
     phrasing, for any fabricated multiplier (the retired "up to 16x"
     phrasing and every "N times longer/faster" shape), and for any
     minutes/hours figure the engine cannot honestly support.
  4. ASK-ONCE. Shown once per account-level answer set: after a decision
     is recorded, a fresh load of the same profile (a later run) owes
     nothing. A CHANGED selection re-opens the block exactly once.
  5. DECLINING IS FREE AND FINAL. Keeping the Ollama selection records
     "declined", mutates nothing about the client's model plan, and the
     route proceeds on the client's selection. Switching off Ollama
     records "accepted".
  6. THE RECORD SURVIVES THE STORE. The route_honesty record round-trips
     resource_profile's save/load (and its redaction filter) intact --
     the "authoring"-style silent-drop trap, pinned shut.
  7. THE REAL SURFACES. The real deck-intake-driver records the decision
     from a real merged-turn answer (subprocess, like the F5 plan-tier
     gate), the real _emit_question attaches the block to the
     resource_plan turn exactly once, and launch_plan writes the
     .route-honesty.json launch record.

Unit-level: no network, no spend, no engine. Every profile lives in a tmp
config dir; the operator's live profile is never read or written.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity as cap  # noqa: E402
from presentation_job import launch_plan  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402
from presentation_job import route_honesty as rh  # noqa: E402

DRIVER = SCRIPTS / "deck-intake-driver.py"
BANK = SCRIPTS.parent / "intake" / "deck-intake-questions.json"

OLLAMA = "ollama-cloud"
TIER_20 = cap.PLAN_OLLAMA_20
TIER_100 = cap.PLAN_OLLAMA_100
CEIL_20 = cap.CAP_TABLE[(OLLAMA, TIER_20)]
CEIL_100 = cap.CAP_TABLE[(OLLAMA, TIER_100)]
LIMIT_20, RESERVE_20 = cap.ACCOUNT_LIMITS[(OLLAMA, TIER_20)]
LIMIT_100, RESERVE_100 = cap.ACCOUNT_LIMITS[(OLLAMA, TIER_100)]
_DS_CAPS = sorted(n for (p, _pl), n in cap.CAP_TABLE.items()
                  if p == "deepseek-direct")

# The mandated copy, carried as literals HERE so a module-side copy edit
# fails this file instead of drifting. Until the owner ruling of
# 2026-10-15 the DeepSeek part was computed from CAP_TABLE (the span the
# table carried, 500 to 2500) and quoted as a cap far above deck scale;
# the ruling settled that DeepSeek Direct has NO provider cap, so the
# recommendation is now one full literal that quotes no number for
# either recommended route, and _DS_CAPS above must stay empty (pinned
# by test_no_deepseek_cap_exists_to_quote below).
EXPECTED_RECOMMENDATION = (
    "Recommendation: for best results, use OpenRouter or DeepSeek "
    "Direct. Neither route holds a deck back with a provider "
    "concurrency cap: OpenRouter and DeepSeek Direct have no provider "
    "concurrency cap at all, so on those routes your machine is "
    "the only limit."
)
EXPECTED_SPEED_WARNING = (
    "Speed: Ollama routes, whether local or cloud, are materially slower "
    "for this workload than direct API routes."
)
EXPECTED_NO_ESTIMATE = (
    "One honest limit: this engine has no measured per-slide time for "
    "your setup, so there is no honest minutes estimate for the "
    "difference, and we will not invent one. The concurrency numbers "
    "here come from your plan's own table; the time difference is real "
    "but unmeasured in this engine."
)
EXPECTED_CHOICE = (
    "The choice is yours, and it is recorded once: keep your Ollama "
    "selection in this answer and the run proceeds on it exactly as "
    "chosen, or name an OpenRouter or DeepSeek Direct model instead. "
    "Declining this recommendation changes nothing about how your deck "
    "is handled, and we will not ask again unless you change your "
    "selection."
)

DECK = 55


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


def _seed(cfg: Path, tier=None, workhorse="glm-5.3-flash@ollama-cloud"):
    """A profile the production way: providers probed in, the tier answer
    recorded through record_plan_answer, the model plan through
    record_model_plan -- the same writers the intake driver calls."""
    prof = rp.new_profile()
    prof["providers"][OLLAMA] = _wired(
        OLLAMA, ["glm-5.3-flash", "glm-5.3"])
    prof["providers"]["openrouter"] = _wired(
        "openrouter", ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"])
    prof["providers"]["deepseek-direct"] = _wired(
        "deepseek-direct", ["deepseek-flash"])
    rp.save_profile(prof, cfg)
    if tier:
        rp.record_plan_answer(OLLAMA, tier, cfg)
    if workhorse:
        rp.record_model_plan({"workhorse": workhorse},
                             source="interview", config_dir=cfg)
    return rp.load_profile(cfg)


def _decide_keeping_ollama(cfg: Path, slides=DECK):
    """The full intake beat against the store: owed -> shown -> answered
    with the Ollama selection kept. Returns the recorded decision."""
    prof = rp.load_profile(cfg)
    assert rh.block_owed(prof)
    sig = rh.selection_signature(prof)
    rh.note_block_shown(deck_slides=slides, config_dir=cfg)
    return rh.record_route_decision(pre_signature=sig, pre_owed=True,
                                    deck_slides=slides, config_dir=cfg)


# ---------------------------------------------------------------------------
# 1 + 2: the numbers and the mandated copy, verbatim
# ---------------------------------------------------------------------------
def test_block_numbers_for_the_20_tier_come_from_the_tables(tmp_path):
    prof = _seed(tmp_path, tier=TIER_20)
    block = rh.render_block(prof, deck_slides=DECK)
    assert block is not None
    text = block["text"]
    assert (f"your Ollama Cloud plan is {TIER_20}: it allows {LIMIT_20} "
            f"at once at the account, and this engine uses {CEIL_20} at "
            f"a time") in text
    rounds = math.ceil(DECK / CEIL_20)
    assert (f"For a deck of {DECK} slides, the slide work alone runs in "
            f"rounds of at most {CEIL_20} at a time: about {rounds} "
            f"rounds") in text
    assert block["facts"]["concurrency_ceiling"] == CEIL_20
    assert block["facts"]["rounds"] == rounds


def test_block_numbers_for_the_100_tier_come_from_the_tables(tmp_path):
    prof = _seed(tmp_path, tier=TIER_100)
    block = rh.render_block(prof, deck_slides=DECK)
    text = block["text"]
    assert (f"your Ollama Cloud plan is {TIER_100}: it allows "
            f"{LIMIT_100} at once at the account; this engine uses "
            f"{CEIL_100} at a time and keeps {RESERVE_100} in reserve "
            f"for your other work") in text
    rounds = math.ceil(DECK / CEIL_100)
    assert f"about {rounds} rounds" in text
    assert block["facts"]["concurrency_ceiling"] == CEIL_100


def test_block_unknown_tier_shows_both_table_rows(tmp_path):
    prof = _seed(tmp_path, tier=None)
    text = rh.render_block(prof, deck_slides=DECK)["text"]
    assert (f"{TIER_20} allows {LIMIT_20} at once at the account, and "
            f"this engine uses {CEIL_20} at a time") in text
    assert (f"{TIER_100} allows {LIMIT_100} at once at the account; "
            f"this engine uses {CEIL_100} at a time and keeps "
            f"{RESERVE_100} in reserve for your other work") in text
    assert (f"at {CEIL_20} at a time ({TIER_20}), about "
            f"{math.ceil(DECK / CEIL_20)} rounds") in text
    assert (f"at {CEIL_100} at a time ({TIER_100}), about "
            f"{math.ceil(DECK / CEIL_100)} rounds") in text


def test_recommendation_matches_the_mandated_copy_verbatim(tmp_path):
    assert rh.recommendation_text(cap) == EXPECTED_RECOMMENDATION
    prof = _seed(tmp_path, tier=TIER_100)
    text = rh.render_block(prof, deck_slides=DECK)["text"]
    assert EXPECTED_RECOMMENDATION in text
    # The mandated elements, named individually so a failure says which
    # half of the owner ruling moved:
    assert "for best results, use OpenRouter or DeepSeek Direct" in text
    assert "no provider concurrency cap at all" in text
    assert "your machine is the only limit" in text


def test_no_deepseek_cap_exists_to_quote():
    """Owner ruling 2026-10-15 (EXEC-DS): DeepSeek Direct has NO provider
    cap. The table rows the old copy read its span from are gone and
    deepseek-direct stands in NO_CAP_PROVIDERS; if a row ever comes back
    this fails before any copy can quote it as a cap again."""
    assert _DS_CAPS == []
    assert cap.PROVIDER_DEEPSEEK_DIRECT in cap.NO_CAP_PROVIDERS
    text = rh.recommendation_text(cap)
    assert "DeepSeek Direct's cap" not in text
    assert "2500" not in text and "500" not in text


def test_speed_warning_verbatim_and_no_fabricated_multiplier(tmp_path):
    prof = _seed(tmp_path, tier=TIER_20)
    text = rh.render_block(prof, deck_slides=DECK)["text"]
    assert EXPECTED_SPEED_WARNING in text
    assert EXPECTED_NO_ESTIMATE in text
    lowered = text.lower()
    # The retired phrasing stays retired, and no replacement multiple is
    # invented: no "Nx", no "N times faster/longer" anywhere in the block.
    assert "16x" not in lowered and "16 x" not in lowered
    assert "times faster" not in lowered
    assert "times longer" not in lowered
    assert "up to" not in lowered
    # No wall-clock figure the engine cannot support: no digit-minutes or
    # digit-hours claims anywhere in the rendered block.
    import re
    assert not re.search(r"\d+\s*(minutes|minute|mins|hours|hour)\b", lowered)


def test_no_penalty_or_pressure_phrasing_anywhere_in_the_block(tmp_path):
    prof = _seed(tmp_path, tier=TIER_100)
    text = rh.render_block(prof, deck_slides=DECK)["text"]
    assert EXPECTED_CHOICE in text
    lowered = text.lower()
    for banned in ("penalty", "penalized", "penalised", "miss out",
                   "act now", "hurry", "last chance", "expires",
                   "you must switch", "required to switch", "punish",
                   "lose access", "degraded", "worse service",
                   "only if you switch", "before it is too late"):
        assert banned not in lowered, f"dark-pattern phrasing present: {banned}"


def test_local_ollama_route_warns_without_inventing_a_plan_number(tmp_path):
    prof = rp.new_profile()
    prof["model_plan"] = {
        "workhorse": {"provider": "ollama-local", "model": "llama3.1"},
        "reasoning": None, "judge": None, "thinking": None,
        "floor_waivers": [], "source": "interview"}
    block = rh.render_block(prof, deck_slides=DECK)
    assert block is not None
    assert "no purchased plan tier" in block["text"]
    assert EXPECTED_SPEED_WARNING in block["text"]
    assert EXPECTED_RECOMMENDATION in block["text"]
    assert block["facts"]["concurrency_ceiling"] is None


def test_declared_off_ollama_is_never_owed(tmp_path):
    prof = _seed(tmp_path, tier=TIER_100,
                 workhorse="z-ai/glm-5.3-flash@openrouter")
    assert rh.ollama_context(prof) is None
    assert rh.block_owed(prof) is False
    assert rh.render_block(prof, deck_slides=DECK) is None


# ---------------------------------------------------------------------------
# 4 + 5: ask-once, re-open on change, free decline, recorded accept
# ---------------------------------------------------------------------------
def test_ask_once_holds_across_runs(tmp_path):
    _seed(tmp_path, tier=TIER_100)
    rec = _decide_keeping_ollama(tmp_path)
    assert rec["status"] == "declined"
    # A later run = a fresh load of the same store. Nothing is owed, and
    # the intake surface hands back no block.
    later = rp.load_profile(tmp_path)
    assert rh.block_owed(later) is False
    pend = rh.pending_honesty(later, deck_slides=DECK)
    assert pend["owed"] is False and pend["block"] is None
    assert pend["record"]["status"] == "declined"


def test_changed_selection_reopens_exactly_once(tmp_path):
    _seed(tmp_path, tier=TIER_100)
    _decide_keeping_ollama(tmp_path)
    assert rh.block_owed(rp.load_profile(tmp_path)) is False
    # The client changes their selection (a different Ollama workhorse):
    # the block re-opens for the new selection...
    rp.record_model_plan({"workhorse": "glm-5.3@ollama-cloud"},
                         source="interview", config_dir=tmp_path)
    changed = rp.load_profile(tmp_path)
    assert rh.block_owed(changed) is True
    # ...and once they answer for THAT selection, it closes again.
    rec = _decide_keeping_ollama(tmp_path)
    assert rec["status"] == "declined"
    assert rh.block_owed(rp.load_profile(tmp_path)) is False


def test_accept_is_recorded_when_the_client_moves_off_ollama(tmp_path):
    _seed(tmp_path, tier=TIER_20)
    prof = rp.load_profile(tmp_path)
    sig = rh.selection_signature(prof)
    rh.note_block_shown(config_dir=tmp_path)
    rp.record_model_plan({"workhorse": "z-ai/glm-5.3-flash@openrouter"},
                         source="interview", config_dir=tmp_path)
    rec = rh.record_route_decision(pre_signature=sig, pre_owed=True,
                                   config_dir=tmp_path)
    assert rec["status"] == "accepted"
    assert rh.block_owed(rp.load_profile(tmp_path)) is False
    # The recorder never writes the plan: what stands is the client's own
    # declaration, byte for byte.
    plan = rp.model_plan(rp.load_profile(tmp_path))
    assert plan["workhorse"] == {"provider": "openrouter",
                                  "model": "z-ai/glm-5.3-flash"}


def test_decline_proceeds_on_the_client_selection_and_records_it(tmp_path):
    _seed(tmp_path, tier=TIER_100)
    before = rp.model_plan(rp.load_profile(tmp_path))
    rec = _decide_keeping_ollama(tmp_path)
    after_prof = rp.load_profile(tmp_path)
    # The plan is untouched by the honesty recorder...
    assert rp.model_plan(after_prof) == before
    # ...and the decision record carries the decision, the selection it
    # was made against, and the table numbers it was shown with.
    assert rec["status"] == "declined"
    assert rec["selection"]["workhorse"] == {
        "provider": "ollama-cloud", "model": "glm-5.3-flash"}
    assert rec["plan_tier"] == TIER_100
    assert rec["concurrency_ceiling"] == CEIL_100
    assert rec["decided_signature"] == rec["shown_signature"]
    log = after_prof["interview"]["route_honesty"]
    assert [r["event"] for r in log] == ["shown", "decision"]
    assert log[-1]["status"] == "declined"


def test_no_offer_outstanding_records_nothing(tmp_path):
    _seed(tmp_path, tier=TIER_100)
    rec = rh.record_route_decision(pre_owed=False, config_dir=tmp_path)
    assert rec is None
    assert "route_honesty" not in rp.load_profile(tmp_path)


def test_record_survives_the_redaction_round_trip(tmp_path):
    _seed(tmp_path, tier=TIER_20)
    _decide_keeping_ollama(tmp_path)
    raw = json.loads((tmp_path / "resource_profile.json").read_text())
    assert raw["route_honesty"]["status"] == "declined"
    loaded = rp.load_profile(tmp_path)
    rec = rh.current_record(loaded)
    assert rec is not None
    assert rec["status"] == "declined"
    assert rec["decided_signature"] == rh.selection_signature(loaded)
    # The counterfactual that gives this test teeth: the filter really
    # does drop secret-named keys (the "authoring" trap), so survival
    # above is a property of the field names, not of a lax filter.
    assert rp.redact_record({"route_honesty": {"x": 1},
                             "authoring_note": "y"}) == {
        "route_honesty": {"x": 1}}


def test_flag_off_is_inert(tmp_path, monkeypatch):
    monkeypatch.setenv(rh.FLAG_ENV, "0")
    prof = _seed(tmp_path, tier=TIER_100)
    assert rh.render_block(prof, deck_slides=DECK) is None
    assert rh.block_owed(prof) is False
    assert rh.note_block_shown(config_dir=tmp_path) is None
    assert rh.record_route_decision(pre_owed=True, config_dir=tmp_path) is None
    assert rh.launch_summary(profile=prof) is None
    assert "route_honesty" not in rp.load_profile(tmp_path)


# ---------------------------------------------------------------------------
# 7: the real surfaces
# ---------------------------------------------------------------------------
def _driver_env(cfg: Path):
    env = dict(os.environ)
    env["PRESENTATION_RESOURCE_PROFILE_DIR"] = str(cfg)
    env["PRESENTATION_CAPACITY_CONFIG_DIR"] = str(cfg)
    env["PRESENTATION_PROVIDER_PROBES"] = "0"
    return env


def _driver_answer(cfg: Path, run_dir: Path, text: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir),
         "--answer", "resource_plan", text],
        capture_output=True, text=True, timeout=180, env=_driver_env(cfg))


def test_driver_records_the_decision_and_never_reasks(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    prof = rp.new_profile()
    prof["providers"][OLLAMA] = _wired(OLLAMA, ["glm-5.3-flash"])
    rp.save_profile(prof, cfg)

    answer = "$100/month; workhorse: glm-5.3-flash@ollama-cloud"
    proc = _driver_answer(cfg, tmp_path / "run1", answer)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    stored = rp.load_profile(cfg)
    rec = rh.current_record(stored)
    assert rec is not None and rec["status"] == "declined"
    assert rec["plan_tier"] == TIER_100
    assert rec["concurrency_ceiling"] == CEIL_100
    assert rp.model_plan(stored)["workhorse"]["provider"] == OLLAMA
    decisions = [r for r in stored["interview"]["route_honesty"]
                 if r["event"] == "decision"]
    assert len(decisions) == 1

    # A later run on the same account, the same answer: the plan recorders
    # run again (their own audit logs grow), but the honesty decision is
    # NOT re-taken -- ask-once is a property of the account, not the run.
    proc2 = _driver_answer(cfg, tmp_path / "run2", answer)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    stored2 = rp.load_profile(cfg)
    decisions2 = [r for r in stored2["interview"]["route_honesty"]
                  if r["event"] == "decision"]
    assert len(decisions2) == 1
    assert rh.block_owed(stored2) is False


def test_driver_emits_the_block_once_with_the_turn(tmp_path, monkeypatch,
                                                   capsys):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    _seed(cfg, tier=TIER_100)
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")

    spec = importlib.util.spec_from_file_location("deck_intake_driver",
                                                  DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qdef = next(q for q in bank["questions"] if q["id"] == "resource_plan")

    assert driver._emit_question(qdef, {}) == 0
    out = json.loads(capsys.readouterr().out)
    assert EXPECTED_RECOMMENDATION in out["route_honesty"]
    assert out["help"].endswith(out["route_honesty"])
    # The showing was recorded as an offer, not a decision.
    prof = rp.load_profile(cfg)
    assert rh.current_record(prof)["status"] == "offered"
    assert rh.block_owed(prof) is True  # offered is not decided

    # The client answers keeping Ollama (through the module's decision
    # writer, the same call cmd_answer makes): the block never emits again.
    sig = rh.selection_signature(prof)
    rh.record_route_decision(pre_signature=sig, pre_owed=True, config_dir=cfg)
    assert driver._emit_question(qdef, {}) == 0
    out2 = json.loads(capsys.readouterr().out)
    assert "route_honesty" not in out2


def test_launch_summary_and_sidecar_carry_the_record(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(tmp_path))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(tmp_path))
    _seed(tmp_path, tier=TIER_20)
    _decide_keeping_ollama(tmp_path)
    prof = rp.load_profile(tmp_path)
    summary = rh.launch_summary(profile=prof, deck_slides=DECK)
    assert summary is not None
    assert f"{CEIL_20} at a time" in summary["text"]
    assert f"about {math.ceil(DECK / CEIL_20)} rounds" in summary["text"]
    assert EXPECTED_SPEED_WARNING in summary["text"]
    assert "route recommendation declined at intake" in summary["text"]
    assert summary["record"]["decision"] == "declined"

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = launch_plan.write_launch_plan(run_dir)
    assert ".route-honesty.json" in result["wrote"]
    sidecar = json.loads((run_dir / ".route-honesty.json").read_text())
    assert sidecar["route_honesty"]["decision"] == "declined"
    assert sidecar["route_honesty"]["concurrency_ceiling"] == CEIL_20
    assert EXPECTED_SPEED_WARNING in sidecar["text"]


def test_launch_summary_is_silent_without_ollama(tmp_path):
    prof = _seed(tmp_path, tier=TIER_100,
                 workhorse="z-ai/glm-5.3-flash@openrouter")
    assert rh.launch_summary(profile=prof) is None
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert rh.write_launch_sidecar(run_dir, profile=prof) is False
    assert not (run_dir / ".route-honesty.json").exists()
