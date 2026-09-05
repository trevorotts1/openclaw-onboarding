#!/usr/bin/env python3
"""FIX 11 -- the CLIENT can actually reach Ultra.

FIX 11 (v24.2.2) wired the ENGINE to read the mode it is handed:
dispatcher._active_mode reads PRESENTATION_MODE, and launcher.py has carried
`--mode ultra|standard|economy` since FIX 11 landed. What still did not exist
was anything on the CLIENT path that ever HANDED it one.

Measured on pristine main, with an intake ledger that declared ultra:

  * presentation-intake-poll.sh contained ZERO occurrences of "--mode"
    (control: launcher.py, the same scan, 3);
  * deck-intake-questions.json contained ZERO run-mode slots -- 62 subfields,
    none with the ultra|standard|economy vocabulary (control: the same scan
    found all 6 enum subfields that do exist, standard_mode among them);
  * both poller dispatch branches resolved model_router.active_mode() ==
    "standard" anyway.

So a client on the hands-off path (agent intake -> launchd poller -> engine)
ALWAYS got standard, whatever they asked for. Ultra was unreachable for a
client by construction.

This file pins the three wires that close it:

  1. the BANK carries a client-declarable run_mode slot, riding the EXISTING
     resource_plan turn (order 9) as a sixth labelled subfield -- never a 24th
     turn (Trevor ruling: session_budget.max_turns = 23);
  2. the DRIVER normalises it, refuses the interview-depth vocabulary naming
     BOTH axes, and records nothing at all when nothing was declared;
  3. the POLLER reads it and hands it to the run-mode door -- launcher --mode
     on the resume branch, PRESENTATION_MODE on the new-intake branch (which
     calls the engine directly and never touches the launcher).

THE TWO AXES ARE NOT INTERCHANGEABLE. Run mode (ultra|standard|economy) is how
the deck is BUILT. Interview depth (quick|in-depth, FIX 30 standard_mode /
FIX 36 --intake-depth) is how much of the interview is asked. The canonical
entry script refuses run-mode words on --intake-depth; run_mode refuses the
interview-depth words here. Nothing in this file touches that script or
tests/test_fix36_intake_depth.py, which owns that direction of the guard.

NEVER ULTRA BY DEFAULT. Every "undeclared" case below asserts standard: nothing
silently launches at the operator ceiling.

Unit-level: no network, no spend, no deck, no render. The poller runs for real
against a stub launcher/engine that record what they were handed; HOME is
redirected into tmp_path so the poller's log and telemetry writes stay there.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import model_router  # noqa: E402

BANK = SCRIPTS.parent / "intake" / "deck-intake-questions.json"
POLLER = SCRIPTS / "presentation-intake-poll.sh"
DRIVER = SCRIPTS / "deck-intake-driver.py"


def _bank() -> dict:
    return json.loads(BANK.read_text(encoding="utf-8"))


def _run_mode_subfield() -> dict:
    rp = [q for q in _bank()["questions"] if q["id"] == "resource_plan"][0]
    return rp["subfields"]["run_mode"]


# ---------------------------------------------------------------------------
# 1. THE BANK -- a client-declarable slot that costs no extra turn
# ---------------------------------------------------------------------------
def test_run_mode_slot_rides_the_existing_resource_plan_turn():
    bank = _bank()
    rp = [q for q in bank["questions"] if q["id"] == "resource_plan"][0]
    assert rp["order"] == 9 and rp["kind"] == "merged"
    assert "run_mode" in rp["subfields"], sorted(rp["subfields"])
    # It is a SUBFIELD, never its own row: no question carries the id.
    assert [q for q in bank["questions"] if q["id"] == "run_mode"] == []


def test_the_ceiling_is_untouched():
    """Trevor ruling, binding -- 23 turns, and this slot did not spend one."""
    bank = _bank()
    assert bank["session_budget"]["max_turns"] == 23
    assert len([q for q in bank["questions"] if q.get("kind") == "merged"]) == 23


def test_vocabulary_is_exactly_the_fix11_modes_and_matches_the_router():
    ann = _run_mode_subfield()
    assert [str(v).lower() for v in ann["enum"]] == list(model_router.MODES)
    assert ann["storeOn"] == "RUN_MODE"
    assert ann["default"] == ""          # undeclared is undeclared
    assert "mode" in ann["labels"]       # the client's own word


def test_the_slot_declares_the_interview_depth_words_as_refused():
    ann = _run_mode_subfield()
    refused = {str(v).lower() for v in ann["refuse_values"]}
    assert {"quick", "in-depth"} <= refused
    # and the message names BOTH axes, not just "invalid"
    msg = ann["refuse_message"]
    assert "ultra|standard|economy" in msg
    assert "quick|in-depth" in msg
    assert "never interchangeable" in msg


# ---------------------------------------------------------------------------
# 2. THE DRIVER -- normalise, refuse, or record nothing
# ---------------------------------------------------------------------------
def _answer(tmp_path, text):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    (cfg / "resource_profile.json").write_text(json.dumps(
        {".schema_version": 1, "providers": {"deepseek-direct": {
            "provider": "deepseek-direct", "consented": True, "detected": True,
            "presence": True, "wired_models": ["deepseek-v4-flash"]}}}),
        encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PRESENTATION_CONFIG_DIR"] = str(cfg)
    env.pop("PRESENTATION_RESOURCE_PROFILE_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir),
         "--answer", "resource_plan", text],
        capture_output=True, text=True, env=env, timeout=120)
    ledger = run_dir / "working" / "interview" / "intake_ledger.json"
    entries = (json.loads(ledger.read_text(encoding="utf-8"))["entries"]
               if ledger.is_file() else {})
    return proc, entries, run_dir


@pytest.mark.parametrize("text,expected", [
    ("mode: ultra", "ultra"),
    ("mode: ULTRA", "ultra"),            # case-insensitive in, lowercase out
    ("mode: Economy", "economy"),
    ("mode: standard", "standard"),
    ("run mode: ultra", "ultra"),        # the client's other spelling
    ("workhorse: deepseek-v4-flash@deepseek-direct; mode: ultra", "ultra"),
])
def test_driver_records_a_declared_run_mode(tmp_path, text, expected):
    proc, entries, _ = _answer(tmp_path, text)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert entries["RUN_MODE"]["value"] == expected
    assert entries["run_mode"]["value"] == expected


def test_undeclared_records_nothing_at_all(tmp_path):
    """Absence is absence. No RUN_MODE key, so the launcher default stands --
    and it is never 'ultra'."""
    proc, entries, _ = _answer(tmp_path, "use conservative default")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RUN_MODE" not in entries, sorted(entries)
    assert model_router.DEFAULT_MODE == "standard"


@pytest.mark.parametrize("word", ["quick", "QUICK", "in-depth", "in_depth"])
def test_interview_depth_vocabulary_is_refused_naming_both_axes(tmp_path, word):
    """The mirror image of test_fix36_intake_depth's guard: that one refuses
    the run-mode words on --intake-depth, this one refuses the
    interview-depth words in the run-mode slot. Neither axis ever silently
    accepts the other's vocabulary."""
    proc, entries, _ = _answer(tmp_path, f"mode: {word}")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    err = json.loads(proc.stdout.strip().splitlines()[-1])["error"]
    assert "ultra|standard|economy" in err
    assert "quick|in-depth" in err
    assert "never interchangeable" in err
    assert "RUN_MODE" not in entries, "a refused answer must not half-land"


def test_reanswering_without_a_mode_keeps_the_earlier_declaration(tmp_path):
    """A re-answer that omits the mode must not silently downgrade the run.

    A client who already said ultra is not "saying nothing" -- so a later
    answer about MODELS leaves the run mode alone. The asymmetry is the safe
    one: only an explicit new mode changes it, and only an explicit "ultra"
    can ever escalate TO ultra."""
    _answer(tmp_path, "mode: ultra")
    proc, entries, _ = _answer(
        tmp_path, "workhorse: deepseek-v4-flash@deepseek-direct")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert entries["RUN_MODE"]["value"] == "ultra"
    # ... and an explicit new mode DOES change it.
    proc, entries, _ = _answer(tmp_path, "mode: economy")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert entries["RUN_MODE"]["value"] == "economy"


def test_a_later_answer_can_never_silently_escalate_to_ultra(tmp_path):
    """The one direction that must never happen by accident."""
    _answer(tmp_path, "mode: economy")
    for follow_up in ("use conservative default",
                      "workhorse: deepseek-v4-flash@deepseek-direct",
                      "qc: deepseek-v4-flash@deepseek-direct; thinking: max"):
        proc, entries, _ = _answer(tmp_path, follow_up)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert entries["RUN_MODE"]["value"] != "ultra", follow_up


def test_garbage_is_refused_never_coerced(tmp_path):
    proc, entries, _ = _answer(tmp_path, "mode: banana")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    err = json.loads(proc.stdout.strip().splitlines()[-1])["error"]
    assert "banana" in err and "run_mode" in err
    assert "RUN_MODE" not in entries


# ---------------------------------------------------------------------------
# 3. THE POLLER -- the wire that was missing
# ---------------------------------------------------------------------------
def test_poller_source_carries_both_run_mode_doors():
    """The resume branch goes through the launcher (--mode); the new-intake
    branch calls the engine directly and therefore uses PRESENTATION_MODE. A
    poller carrying neither is the pristine-main state this fix replaces."""
    src = POLLER.read_text(encoding="utf-8")
    assert "--mode" in src
    assert "PRESENTATION_MODE" in src
    assert "read_run_mode" in src


_ENGINE_STUB = '''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["SIM_RECORD_DIR"], "engine.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv,
                         "mode_env": os.environ.get("PRESENTATION_MODE")}) + "\\n")
if "--new" in sys.argv:
    rd = sys.argv[sys.argv.index("--run-dir") + 1]
    with open(os.path.join(rd, "state.json"), "w") as fh:
        json.dump({"terminal": "", "phase": "P0"}, fh)
'''

_LAUNCHER_STUB = '''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["SIM_RECORD_DIR"], "launcher.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv,
                         "mode_env": os.environ.get("PRESENTATION_MODE")}) + "\\n")
'''

_RESOLVE_STUB = '''#!/usr/bin/env python3
import json, sys
with open(sys.argv[sys.argv.index("--out") + 1], "w") as fh:
    json.dump({"presentation_type": "from_scratch"}, fh)
'''


def _poller_rig(tmp_path, ledger_entries, parked):
    """A SCRIPTS_DIR the poller resolves to, whose launcher and engine are
    recorders. model_router is the real one, so the poller validates the
    declared mode against the same authority active_mode() uses."""
    scripts = tmp_path / "rig"
    (scripts / "presentation_job").mkdir(parents=True)
    for name in ("__init__.py", "model_router.py", "launch_plan.py"):
        shutil.copy2(SCRIPTS / "presentation_job" / name,
                     scripts / "presentation_job" / name)
    (scripts / "presentation_job" / "launcher.py").write_text(_LAUNCHER_STUB)
    (scripts / "presentation_job" / "resolve_intake.py").write_text(_RESOLVE_STUB)
    (scripts / "presentation_job.py").write_text(_ENGINE_STUB)
    shutil.copy2(POLLER, scripts / POLLER.name)

    runs = tmp_path / "runs"
    run_dir = runs / "pres-rig-0001"
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True,
                    "entries": ledger_entries}), encoding="utf-8")
    if parked:
        (run_dir / "state.json").write_text(
            json.dumps({"terminal": "", "engine_pid": ""}), encoding="utf-8")

    records = tmp_path / "records"
    records.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home" / "Library" / "Logs" / "openclaw").mkdir(parents=True)
    env["PRESENTATION_RUNS_DIR"] = str(runs)
    env["SIM_RECORD_DIR"] = str(records)
    env.pop("PRESENTATION_MODE", None)
    proc = subprocess.run(["bash", str(scripts / POLLER.name)],
                          env=env, capture_output=True, text=True, timeout=300)
    got = {}
    for f in records.glob("*.jsonl"):
        got[f.stem] = [json.loads(line) for line in
                       f.read_text().splitlines() if line.strip()]
    return proc, got


def _resolved(row):
    """What model_router.active_mode() answers for what this process got."""
    argv = row["argv"]
    explicit = (argv[argv.index("--mode") + 1] if "--mode" in argv else None)
    saved = os.environ.pop(model_router.MODE_ENV, None)
    if row.get("mode_env"):
        os.environ[model_router.MODE_ENV] = row["mode_env"]
    try:
        return model_router.active_mode(explicit, strict=False)
    finally:
        os.environ.pop(model_router.MODE_ENV, None)
        if saved is not None:
            os.environ[model_router.MODE_ENV] = saved


_DECLARED = {"RUN_MODE": {"value": "ultra", "validated": True}}
_UNDECLARED = {"resource_plan": {"value": "use conservative default"}}


@pytest.mark.parametrize("parked,process", [(False, "engine"), (True, "launcher")])
def test_declared_ultra_reaches_the_dispatched_process(tmp_path, parked, process):
    proc, got = _poller_rig(tmp_path, _DECLARED, parked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = got.get(process) or []
    assert rows, f"{process} was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert _resolved(row) == "ultra", row


@pytest.mark.parametrize("parked,process", [(False, "engine"), (True, "launcher")])
def test_undeclared_stays_standard(tmp_path, parked, process):
    """Never ultra by default -- and nothing is passed at all, so it is the
    launcher's own default that answers, not a guess made here."""
    proc, got = _poller_rig(tmp_path, _UNDECLARED, parked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = got.get(process) or []
    assert rows, f"{process} was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert "--mode" not in row["argv"], row
        assert row.get("mode_env") is None, row
        assert _resolved(row) == "standard", row


@pytest.mark.parametrize("parked,process", [(False, "engine"), (True, "launcher")])
def test_unparseable_declaration_is_dropped_loudly_never_guessed(
        tmp_path, parked, process):
    """A ledger carrying a word from the OTHER axis (or any non-mode) must not
    become a mode. It is dropped, said out loud, and standard applies."""
    proc, got = _poller_rig(tmp_path, {"RUN_MODE": {"value": "quick"}}, parked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ultra|standard|economy" in proc.stderr, proc.stderr
    rows = got.get(process) or []
    assert rows, f"{process} was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert "--mode" not in row["argv"], row
        assert row.get("mode_env") is None, row
        assert _resolved(row) == "standard", row


# ---------------------------------------------------------------------------
# 4. THE LAUNCH RECORD -- the --new branch must leave EVIDENCE
# ---------------------------------------------------------------------------
# The --new branch does not go through the launcher, so before this it wrote
# none of the launcher's launch-plan sidecars: a fresh client intake declaring
# ULTRA would correctly RUN ultra and leave nothing behind that said so. The
# mode governed but was unauditable -- "ultra was on" became an unverifiable
# claim exactly where proof was demanded. These pin the record.

def _sidecar(run_root, name):
    p = run_root / "runs" / "pres-rig-0001" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def test_new_branch_records_the_declared_mode_with_its_provenance(tmp_path):
    proc, _ = _poller_rig(tmp_path, _DECLARED, parked=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rec = _sidecar(tmp_path, ".mode-plan.json")
    assert rec is not None, f"no .mode-plan.json: {proc.stdout[-1500:]}"
    assert rec["mode"] == "ultra"
    assert rec["declared"] is True
    # The PROVENANCE: which seam supplied it. Not "--mode" (this branch has no
    # launcher and the engine entry has no such flag) -- the client's intake.
    assert rec["mode_source"] == "intake-slot", rec["mode_source"]
    assert rec["ceiling"]["operator_ceiling"] == 100


def test_new_branch_records_standard_when_nothing_was_declared(tmp_path):
    """An un-moded run still leaves a record, and it says standard. The record
    exists for EVERY launch: "which mode was this deck built in?" must have an
    answer after the fact even when nobody declared one."""
    proc, _ = _poller_rig(tmp_path, _UNDECLARED, parked=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rec = _sidecar(tmp_path, ".mode-plan.json")
    assert rec is not None, f"no .mode-plan.json: {proc.stdout[-1500:]}"
    assert rec["mode"] == "standard"
    assert rec["declared"] is False
    assert rec["mode_source"] == "default"


def test_resume_branch_writes_no_sidecar_from_the_poller(tmp_path):
    """The resume branch goes through the launcher, which writes the sidecar
    itself. The poller must NOT also write one there -- two writers for one
    file is how records start disagreeing."""
    proc, _ = _poller_rig(tmp_path, _DECLARED, parked=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # the rig's launcher is a stub, so nothing should have written it
    assert _sidecar(tmp_path, ".mode-plan.json") is None


# ---- shape parity with the REAL launcher ----------------------------------
def _launcher_rig(monkeypatch, tmp_path, profile=None):
    """test_fix11_mode_axis.py's rig: a real child interpreter runs a one-line
    stub engine, so the launcher's own writer really runs."""
    from presentation_job import capacity, launcher, resource_profile
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE_DIR", raising=False)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    (tmp_path / "presentation_job.py").write_text("import sys; sys.exit(0)\n",
                                                  encoding="utf-8")
    return launcher


def _wired(provider, models):
    return {"provider": provider, "consented": True, "detected": True,
            "presence": True, "wired_models": list(models)}


#: Trevor's END check #4 shape: both models + thinking max.
_PROFILE_WITH_PLAN = {
    ".schema_version": 1,
    "providers": {
        "deepseek-direct": _wired("deepseek-direct",
                                  ["deepseek-v4-flash", "deepseek-v4-pro"]),
        "ollama-cloud": _wired("ollama-cloud", ["glm-5.3-flash"]),
    },
    "creative_prefs": {}, "consent": {}, "interview": {},
    "model_plan": {
        "workhorse": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
        "reasoning": {"provider": "deepseek-direct", "model": "deepseek-v4-pro"},
        "judge": {"provider": "ollama-cloud", "model": "glm-5.3-flash"},
        "thinking": "max",
        "source": "interview",
    },
}


def test_both_dispatch_paths_write_the_same_sidecar_shape(monkeypatch, tmp_path):
    """THE ANTI-DRIFT GUARD. A consumer must not need to know which branch ran.

    This is why the new-intake writer may restate the launcher's dozen lines of
    assembly rather than share them: the shapes are pinned here, executably, and
    this fails if EITHER writer's shape moves."""
    from presentation_job import launch_plan
    launcher = _launcher_rig(monkeypatch, tmp_path, _PROFILE_WITH_PLAN)
    left = tmp_path / "left"
    launcher.dispatch(str(left), client="acme", deck_type="standard",
                      background=False, mode="ultra")
    right = tmp_path / "right"
    right.mkdir(parents=True, exist_ok=True)
    launch_plan.write_launch_plan(right, "ultra", launch_plan.SOURCE_INTAKE)

    for name in (launch_plan.MODE_PLAN_SIDECAR, launch_plan.MODEL_PLAN_SIDECAR):
        lp, rp = left / name, right / name
        assert lp.is_file(), f"the real launcher wrote no {name}"
        assert rp.is_file(), f"the new-intake branch wrote no {name}"
        lj = json.loads(lp.read_text(encoding="utf-8"))
        rj = json.loads(rp.read_text(encoding="utf-8"))
        assert sorted(lj) == sorted(rj), (name, sorted(lj), sorted(rj))
    lmode = json.loads((left / launch_plan.MODE_PLAN_SIDECAR).read_text())
    rmode = json.loads((right / launch_plan.MODE_PLAN_SIDECAR).read_text())
    assert lmode["mode"] == rmode["mode"] == "ultra"
    assert lmode["ceiling"] == rmode["ceiling"]
    # ... and the provenance is the ONE field that legitimately differs.
    assert lmode["mode_source"] == "--mode"
    assert rmode["mode_source"] == "intake-slot"


def test_routing_stamp_carries_both_models_and_the_thinking_level(monkeypatch,
                                                                  tmp_path):
    """END check #4, verbatim: "routing stamp: both models + thinking max"."""
    from presentation_job import launch_plan
    _launcher_rig(monkeypatch, tmp_path, _PROFILE_WITH_PLAN)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    launch_plan.write_launch_plan(run_dir, "ultra", launch_plan.SOURCE_INTAKE)
    stamp = json.loads(
        (run_dir / launch_plan.MODEL_PLAN_SIDECAR).read_text(encoding="utf-8"))
    slots = stamp["plan"]["slots"]
    assert slots["workhorse"] == {"provider": "deepseek-direct",
                                  "model": "deepseek-v4-flash"}
    assert slots["judge"] == {"provider": "ollama-cloud",
                              "model": "glm-5.3-flash"}
    assert stamp["plan"]["thinking"] == "max"


def test_no_client_model_plan_writes_no_routing_stamp(monkeypatch, tmp_path):
    """Byte-for-byte the pre-fix launch when the client declared nothing --
    the launcher writes no .model-plan.json in that case either."""
    from presentation_job import launch_plan
    profile = dict(_PROFILE_WITH_PLAN)
    profile.pop("model_plan")
    _launcher_rig(monkeypatch, tmp_path, profile)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = launch_plan.write_launch_plan(run_dir, "ultra", launch_plan.SOURCE_INTAKE)
    assert launch_plan.MODE_PLAN_SIDECAR in out["wrote"]
    assert launch_plan.MODEL_PLAN_SIDECAR not in out["wrote"]
    assert not (run_dir / launch_plan.MODEL_PLAN_SIDECAR).exists()


def test_modes_rollback_writes_no_sidecar_at_all(monkeypatch, tmp_path):
    """PRESENTATION_MODES=0 is the documented rollback: the whole FIX 11
    surface goes inert, sidecar included. Inherited exactly."""
    from presentation_job import launch_plan
    _launcher_rig(monkeypatch, tmp_path, _PROFILE_WITH_PLAN)
    monkeypatch.setenv(model_router.MODE_FLAG_ENV, "0")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = launch_plan.write_launch_plan(run_dir, "ultra", launch_plan.SOURCE_INTAKE)
    assert out["wrote"] == []
    assert not (run_dir / launch_plan.MODE_PLAN_SIDECAR).exists()
    assert not (run_dir / launch_plan.MODEL_PLAN_SIDECAR).exists()


def test_an_unrecordable_plan_never_blocks_a_dispatch(tmp_path):
    """Best-effort by contract: the CLI exits 0 even on a bad mode, so an audit
    record can never be the reason a client's deck does not get built."""
    from presentation_job import launch_plan
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    rc = launch_plan.main(["--run-dir", str(run_dir), "--mode", "banana"])
    assert rc == 0
    assert not (run_dir / launch_plan.MODE_PLAN_SIDECAR).exists()
