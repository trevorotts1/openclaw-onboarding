#!/usr/bin/env python3
"""PRES-056 -- persistence slice (writer2): autosave, metrics, no re-prompt.

WHAT THIS PROVES (executed against the REAL driver + bank + the two NEW
modules, never a grep):
  1. Pause / token-renewal / resume: the store's snapshot + the ledger keep
     every answer and resource choice across a fresh process on the same
     dirs; --next surfaces the identical turn, nothing re-asked.
  2. Two simultaneous decks: per-company/per-presentation scoping -- answers
     and resource choices (RUN_MODE) never leak between run dirs.
  3. A locked valid plan preference never triggers an extra plan prompt:
     resource_plan resolves from the lock and --complete passes.
  4. Metrics: turn-count + time-to-valid-brief measured against the 23-turn
     baseline (bank header is the single source: 23 merged turns, 48 rows,
     20 required). Valid brief = every required field real /
     approved-derived / explicit pending -- never null, never invented;
     omitted vs declined stays distinct (a declined toggle without a
     validated reason fails the verdict; silence never fabricates one).

ISOLATION. Same contract as writer1's file: every case points
PRESENTATION_RESOURCE_PROFILE_DIR and PRESENTATION_CAPACITY_CONFIG_DIR at
tmp_path for BOTH this process and the driver subprocess, and disables
provider probes. The operator's live profile is never read or written.

DISJOINTNESS. This file owns the store + metrics surface only. It never
touches writer1's three files and never writes run/candidates.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PRES_SCRIPTS = _TESTS_DIR.parent                    # .../presentations/scripts
_DRIVER = _PRES_SCRIPTS / "deck-intake-driver.py"
_STORE = _PRES_SCRIPTS / "progressive_intake_store.py"
_METRICS = _PRES_SCRIPTS / "intake_brief_metrics.py"
_BANK = _PRES_SCRIPTS.parent / "intake" / "deck-intake-questions.json"

sys.path.insert(0, str(_PRES_SCRIPTS))
import intake_brief_metrics as metrics
import progressive_intake_store as store

BASELINE_TURNS = 23

_NEW_ANSWERS = [
    ("deck_type_source", "from_scratch"),
    ("audience_recipient_cast",
     "audience: women founders 35-55 SaaS; audience_composition_note: mixed "
     "room, operators; representation_mix: no people"),
    ("grounding_and_method",
     "grounded_content: The Momentum Method book; named_methodology: The "
     "Three-Move Pipeline"),
    ("goal_cta_feeling",
     "goal: fill the masterclass; cta_action: book a call; "
     "target_feeling: fired up and clear"),
    ("promise_objection_timing",
     "transformation_promise: stuck to closing; primary_objection: no time; "
     "time_to_result: 8 weeks"),
    ("hook_and_tone",
     "hook_seed: the pipeline pays for itself; tone: inspirational"),
    ("duration_and_slide_count", "duration_min: 45"),
    ("deadline_and_notes", "deadline: 2026-10-01; client_notes: none"),
    ("interview_depth", "standard_mode: QUICK"),
    ("resource_plan", "mode: standard"),
]

_REFINE_DECK = [
    ("offer_and_stack", "offer_name: Momentum; offer_stack: course plus calls"),
    ("event_access", "event_price: $97"),
    ("price_structure", "price_mode: straight; final_price: $97"),
    ("payment_and_vip", "payment_plan: none; vip_tier: no"),
    ("proof_assets", "proof_assets: two testimonials, one screenshot"),
    ("style_and_brand",
     "style_source: create-new; style_prefs: fresh clean-white; "
     "brand_primary: #123456; dark_ok: no"),
    ("visual_mix", "visual_mix: product plus text"),
    ("logo_placement", "logo_on_slides: no"),
    ("core_deliverables",
     "want_teleprompter: yes; want_speech_script: yes; "
     "want_audio_deliverable: no"),
    ("delivery_and_ghl",
     "delivery_destinations: email link; want_ghl_upload: no"),
    ("growth_assets", "want_sales_checkout: no; want_vsl_page: no"),
    ("decline_context",
     "audio_declined_reason: no note; ghl_upload_declined_reason: client "
     "has no GHL account; sales_checkout_declined_reason: no checkout this "
     "quarter; vsl_page_declined_reason: no note"),
]

_SEED_PREFS = {
    "style_prefs": "clean", "brand_primary": "#123456", "dark_ok": False,
    "visual_mix": "product plus text", "logo_on_slides": False,
    "target_wpm": 140,
}


def _env(cfg: Path) -> dict:
    env = dict(os.environ)
    env["PRESENTATION_RESOURCE_PROFILE_DIR"] = str(cfg)
    env["PRESENTATION_CAPACITY_CONFIG_DIR"] = str(cfg)
    env["PRESENTATION_PROVIDER_PROBES"] = "0"
    return env


def _fresh(tmp_path: Path, seed_prefs: dict | None = None):
    root = tmp_path / "persist"
    root.mkdir(exist_ok=True)
    run = root / "run"
    run.mkdir(exist_ok=True)
    cfg = root / "cfg"
    cfg.mkdir(exist_ok=True)
    if seed_prefs is not None:
        (cfg / "resource_profile.json").write_text(json.dumps({
            ".schema_version": 1,
            "profile_version": "20260101T000000Z0000",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "providers": {},
            "creative_prefs": seed_prefs,
            "consent": {},
            "interview": {},
        }, indent=2), encoding="utf-8")
    return run, cfg, _env(cfg)


def _run(driver_args, run: Path, env: dict):
    proc = subprocess.run(
        [sys.executable, str(_DRIVER), "--run-dir", str(run), *driver_args],
        capture_output=True, text=True, timeout=180, env=env,
    )
    return proc


def _next(run: Path, env: dict) -> dict:
    proc = _run(["--next"], run, env)
    assert proc.returncode == 0, (
        f"--next exited {proc.returncode}\nstdout: {proc.stdout[:500]}\n"
        f"stderr: {proc.stderr[:500]}")
    return json.loads(proc.stdout)


def _answer(run: Path, env: dict, qid: str, text: str) -> dict:
    proc = _run(["--answer", qid, text], run, env)
    assert proc.returncode == 0, (
        f"--answer {qid} exited {proc.returncode}\nstdout: {proc.stdout[:500]}\n"
        f"stderr: {proc.stderr[:500]}")
    return json.loads(proc.stdout)


def _drive(run: Path, env: dict, pairs) -> list:
    asked = []
    for qid, text in pairs:
        nxt = _next(run, env)
        assert nxt.get("question_id") == qid, (
            f"expected next={qid}, got {nxt.get('question_id', nxt.get('status'))}")
        asked.append(qid)
        _answer(run, env, qid, text)
    return asked


def _ledger(run: Path) -> dict:
    return json.loads(
        (run / "working" / "interview" / "intake_ledger.json").read_text(
            encoding="utf-8"))


# ---------------------------------------------------------------------------
# Non-vacuity controls
# ---------------------------------------------------------------------------

def test_store_and_metrics_modules_present():
    assert _STORE.is_file(), f"store missing at {_STORE}"
    assert _METRICS.is_file(), f"metrics missing at {_METRICS}"
    assert _DRIVER.is_file(), f"driver missing at {_DRIVER}"
    assert _BANK.is_file(), f"bank missing at {_BANK}"


def test_metrics_bank_shape_still_23_48_20():
    shape = metrics.verify_bank_shape(_BANK)
    assert shape["ok"], shape["mismatches"]
    assert shape["measured"]["baseline"] == BASELINE_TURNS


# ---------------------------------------------------------------------------
# 1. Pause / token-renewal / resume preserves answers + resource choices
# ---------------------------------------------------------------------------

def test_pause_renew_resume_preserves_answers_and_choices(tmp_path,
                                                          monkeypatch):
    run, cfg, env = _fresh(tmp_path)
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    _drive(run, env, _NEW_ANSWERS)
    before = _next(run, env)["question_id"]
    assert before == "offer_and_stack"

    snap = store.save_progress(run)
    assert len(snap["asked_order"]) >= 10
    loaded = store.load_progress(run)
    assert loaded["asked_order"] == snap["asked_order"]

    # Token renewal = fresh process, same dirs. Re-point the store at the
    # same company profile and resume.
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    ctx = store.resume_context(run)
    assert ctx["answers"].get("goal") == "fill the masterclass;"
    assert ctx["answers"].get("run_mode") == "standard"
    assert len(ctx["asked_order"]) >= 10

    env2 = _env(cfg)
    after = _next(run, env2)["question_id"]
    assert after == before, (before, after)
    entries = _ledger(run)["entries"]
    assert entries["RUN_MODE"]["value"] == "standard"
    assert entries["goal"]["value"] == "fill the masterclass;"


def test_absent_snapshot_is_absence_not_evidence(tmp_path):
    run, _cfg, _env = _fresh(tmp_path)
    assert store.load_progress(run) == {}
    ctx = store.resume_context(run)
    assert ctx["asked_order"] == [] and ctx["answers"] == {}


# ---------------------------------------------------------------------------
# 2. Two simultaneous decks stay isolated (answers + resource choices)
# ---------------------------------------------------------------------------

def test_two_simultaneous_decks_preserve_answers_and_choices(tmp_path):
    cfg = tmp_path / "cfg2"
    cfg.mkdir()
    env = _env(cfg)
    run_a = tmp_path / "deck-a"
    run_b = tmp_path / "deck-b"
    run_a.mkdir()
    run_b.mkdir()
    answers_a = [p for p in _NEW_ANSWERS]
    answers_b = [(qid, text.replace("fill the masterclass",
                                    "launch the cohort")
                  if qid == "goal_cta_feeling" else
                  ("mode: economy" if qid == "resource_plan" else text))
                 for qid, text in _NEW_ANSWERS]
    _drive(run_a, env, answers_a)
    _drive(run_b, env, answers_b)

    ent_a = _ledger(run_a)["entries"]
    ent_b = _ledger(run_b)["entries"]
    assert ent_a["goal"]["value"] == "fill the masterclass;"
    assert ent_b["goal"]["value"] == "launch the cohort;"
    assert ent_a["RUN_MODE"]["value"] == "standard"
    assert ent_b["RUN_MODE"]["value"] == "economy"

    snap_a = store.load_progress(run_a)
    snap_b = store.load_progress(run_b)
    assert snap_a["answers"].get("goal") == "fill the masterclass;"
    assert snap_b["answers"].get("goal") == "launch the cohort;"
    assert _next(run_a, env)["question_id"] == "offer_and_stack"
    assert _next(run_b, env)["question_id"] == "offer_and_stack"


# ---------------------------------------------------------------------------
# 3. Locked valid preference triggers no extra plan prompt
# ---------------------------------------------------------------------------

def test_locked_plan_preference_triggers_no_extra_prompt(tmp_path,
                                                         monkeypatch):
    cfg = tmp_path / "lockcfg"
    cfg.mkdir(exist_ok=True)
    (cfg / "resource_profile.json").write_text(json.dumps({
        ".schema_version": 1,
        "profile_version": "20260101T000000Z0000",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "providers": {"ollama-cloud": {
            "provider": "ollama-cloud", "plan_tier": "$100/month",
            "plan_known": True, "concurrency_ceiling": 8,
            "ceiling_source": "cap-table", "locked": True}},
        "creative_prefs": {}, "consent": {}, "interview": {},
    }, indent=2), encoding="utf-8")
    run = tmp_path / "lockrun"
    run.mkdir(exist_ok=True)
    env = _env(cfg)
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")

    prefs = store.load_locked_preferences()
    assert prefs.get("RESOURCE_PLAN") == "locked"

    asked = _drive(run, env, [p for p in _NEW_ANSWERS
                              if p[0] != "resource_plan"] + _REFINE_DECK)
    assert "resource_plan" not in asked, asked
    # The lock resolves the turn in place (plan-lock provenance), so the
    # brief still completes with no extra prompt.
    assert _ledger(run)["entries"]["resource_plan"]["source"] == "plan-lock"
    assert _run(["--complete"], run, env).returncode == 0

    m = metrics.measure_run(run, returning_client=False, bank_file=_BANK)
    assert m["brief"]["valid"], m["brief"]["bad"]
    assert m["baseline"] == BASELINE_TURNS
    assert m["saved"] == max(0, BASELINE_TURNS - m["asked"])


# ---------------------------------------------------------------------------
# 4. Metrics: turn-count + time-to-valid-brief vs the 23-turn baseline
# ---------------------------------------------------------------------------

def test_completed_deck_only_brief_measures_valid_under_baseline(tmp_path):
    run, _cfg, env = _fresh(tmp_path)
    asked = _drive(run, env, _NEW_ANSWERS + _REFINE_DECK)
    assert "audio_settings" not in asked
    assert len(asked) < BASELINE_TURNS
    assert _run(["--complete"], run, env).returncode == 0

    m = metrics.measure_run(run, returning_client=False, bank_file=_BANK)
    assert m["baseline"] == BASELINE_TURNS
    assert m["target"] == metrics.NEW_CLIENT_TARGET
    assert m["asked"] == len(store.load_progress(run)["asked_order"])
    assert m["saved"] == BASELINE_TURNS - m["asked"]
    assert m["meets_target"] == (m["asked"] <= metrics.NEW_CLIENT_TARGET)
    assert m["brief"]["valid"], m["brief"]["bad"]
    assert m["bank_shape"]["ok"], m["bank_shape"]["mismatches"]


def test_repeat_client_reuse_rate_and_fewer_asks(tmp_path, monkeypatch):
    run, cfg, env = _fresh(tmp_path, seed_prefs=dict(_SEED_PREFS))
    assert _run(["--reuse-preferences"], run, env).returncode == 0
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")

    copied = store.copy_preferences_into_ledger(
        _ledger(run)["entries"], store.load_locked_preferences())
    assert not copied  # already copied by the driver flag; never duplicated

    asked = []
    pairs = dict(_NEW_ANSWERS + _REFINE_DECK)
    for _ in range(len(pairs) + 5):
        nxt = _next(run, env)
        if nxt.get("status") == "complete":
            break
        qid = nxt.get("question_id")
        assert qid in pairs, qid
        asked.append(qid)
        _answer(run, env, qid, pairs[qid])
    assert len(asked) < BASELINE_TURNS
    assert _run(["--complete"], run, env).returncode == 0

    m = metrics.measure_run(run, bank_file=_BANK)
    assert m["returning_client"] is True
    assert m["target"] == metrics.REPEAT_CLIENT_TARGET
    assert m["preference_reuse_rate"] == 1.0
    assert m["brief"]["valid"], m["brief"]["bad"]


def test_omitted_and_declined_differ_in_verdict():
    declined_no_reason = {
        "want_audio_deliverable": {"value": "no", "validated": True,
                                   "source": "deck-intake-driver"}}
    verdict = metrics.brief_valid(declined_no_reason)
    assert verdict["valid"] is False
    assert "want_audio_deliverable-reason" in verdict["bad"]

    omitted = {}  # silence: no toggle, no reason owed, nothing fabricated
    verdict2 = metrics.brief_valid(omitted)
    assert not any("want_audio_deliverable" in b for b in verdict2["bad"])

    declined_with_reason = {
        "want_audio_deliverable": {"value": "no", "validated": True,
                                   "source": "deck-intake-driver"},
        "audio_declined_reason": {"value": "no note.", "validated": True,
                                  "source": "deck-intake-driver"}}
    verdict3 = metrics.brief_valid(declined_with_reason)
    assert not any("audio" in b for b in verdict3["bad"]), verdict3["bad"]


def test_summarize_runs_aggregates_measurements():
    runs = [{"asked": 22, "saved": 1, "meets_target": False,
             "brief": {"valid": True}},
            {"asked": 6, "saved": 17, "meets_target": True,
             "brief": {"valid": True}}]
    summary = metrics.summarize_runs(runs)
    assert summary["runs"] == 2
    assert summary["meet_target"] == 1
    assert summary["briefs_valid"] == 2
    assert summary["mean_asked"] == 14.0
    assert metrics.summarize_runs([]) == {"runs": 0}
