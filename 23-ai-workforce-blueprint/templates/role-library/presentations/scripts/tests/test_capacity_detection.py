#!/usr/bin/env python3
"""test_capacity_detection.py -- unit u07: client-capacity detection + its teeth.

Locks the four things that make capacity a GATE instead of an advisory print:

  1. the cap table maps (provider, plan) onto the right number, and every
     unknown collapses to DEFAULT_CONSERVATIVE = 3 -- never upward;
  2. detection order a -> b -> c -> d -> e, first hit wins, with a loud
     UNDETERMINED when nothing is found;
  3. wave width is min(ready phases, measured available) -- a probe of 3 over
     five independent phases yields waves of 3 then 2, and a probe of 10 yields
     one wave of 5 (the mutation proof: change the probe, the plan changes);
  4. the dispatch path REFUSES (non-zero, nothing spawned) when the probe
     cannot produce a number.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import execution_plan  # noqa: E402
from presentation_job import launcher  # noqa: E402


# ---------------------------------------------------------------------------
# 1. The cap table
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("provider,plan,expected", [
    ("ollama-cloud", "$20/month", 3),
    ("ollama-cloud", "$100/month", 10),
    ("deepseek-direct", "v4-pro", 500),
    ("deepseek-direct", "v4-flash", 2500),
])
def test_cap_table_exact(provider, plan, expected):
    assert capacity.CAP_TABLE[(provider, plan)] == expected


def test_default_conservative_is_three():
    assert capacity.DEFAULT_CONSERVATIVE == 3


@pytest.mark.parametrize("raw,expected", [
    ("ollama-cloud", "ollama-cloud"),
    ("Ollama Cloud", "ollama-cloud"),
    ("deepseek", "deepseek-direct"),
    ("ds-max", "deepseek-direct"),
    ("ollama-local", None),      # local Ollama buys no plan
    ("openrouter", None),
    ("", None),
    (None, None),
])
def test_normalize_provider_never_guesses(raw, expected):
    assert capacity.normalize_provider(raw) == expected


@pytest.mark.parametrize("raw,provider,expected", [
    ("$20", "ollama-cloud", "$20/month"),
    ("20/month", "ollama-cloud", "$20/month"),
    ("$100/month", "ollama-cloud", "$100/month"),
    ("v4 Pro", "deepseek-direct", "v4-pro"),
    ("v4-flash", "deepseek-direct", "v4-flash"),
    ("enterprise", "ollama-cloud", None),
])
def test_normalize_plan(raw, provider, expected):
    assert capacity.normalize_plan(raw, provider) == expected


# ---------------------------------------------------------------------------
# 2. Detection order
# ---------------------------------------------------------------------------
def _isolate(monkeypatch, tmp_path):
    """No 9Router db, no OpenClaw config, no harness settings -- steps b and c
    are structurally unreachable so a test can assert on a and e alone."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))


def test_step_a_declared_override_wins(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "ollama-cloud", "plan": "$20/month"}), encoding="utf-8")
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_MEASURED
    assert result["detection_source"] == capacity.SOURCE_OVERRIDE
    assert result["available"] == 3


def test_step_a_deepseek_flash_override(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "deepseek-direct", "plan": "v4-flash"}), encoding="utf-8")
    assert capacity.probe(cfg)["available"] == 2500


def test_declared_max_concurrent_never_raises_the_table(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "ollama-cloud", "plan": "$20/month",
                    "max_concurrent": 900}), encoding="utf-8")
    assert capacity.probe(cfg)["available"] == 3


def test_step_e_nothing_found_is_undetermined_and_three(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_UNDETERMINED
    assert result["undetermined"] is True
    assert result["available"] == capacity.DEFAULT_CONSERVATIVE == 3
    assert "UNDETERMINED" in capacity.format_report(result)


def test_step_d_provider_known_plan_unknown_parks_with_one_question(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    openclaw = tmp_path / "openclaw.json"
    openclaw.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "ollama/some-model:cloud"}}},
        "models": {"providers": {"ollama": {"baseUrl": "https://ollama.com/v1",
                                            "apiKey": "NEVER-READ"}}},
    }), encoding="utf-8")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", openclaw)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_PARKED
    assert result["provider"] == "ollama-cloud"
    assert result["available"] is None
    assert capacity.available_or_none(result) is None
    assert "Which plan is your ollama-cloud account on?" in result["interview_question"]
    # ...and the credential value never leaves the module.
    assert "NEVER-READ" not in json.dumps(result)


def test_local_ollama_is_not_a_cap_table_provider(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    openclaw = tmp_path / "openclaw.json"
    openclaw.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "ollama/llama:local"}}},
        "models": {"providers": {"ollama": {"baseUrl": "http://127.0.0.1:11434"}}},
    }), encoding="utf-8")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", openclaw)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    assert capacity.probe(cfg)["status"] == capacity.STATUS_UNDETERMINED


def test_interview_answer_is_asked_once(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    written = capacity.persist_plan_answer("ollama-cloud", "$100", cfg)
    assert written.is_file()
    result = capacity.probe(cfg)
    assert result["detection_source"] == capacity.SOURCE_OVERRIDE
    assert result["available"] == 10
    assert result["interview_question"] is None


def test_declared_max_concurrent_cannot_bypass_park_via_ordering(monkeypatch, tmp_path):
    """The breach: a KNOWN cap-table provider with no plan but a declared
    max_concurrent must PARK, not MEASURE the declared number verbatim. Before
    the fix, the bare-declared-int branch sat ahead of the PARK branch and
    9999 came back as status=MEASURED, available=9999, autofail_code=None --
    the launcher gate would have passed a 9999-wide dispatch against a
    provider whose highest cap-table row anywhere is 10."""
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "ollama-cloud", "max_concurrent": 9999}),
        encoding="utf-8")
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_PARKED
    assert result["available"] is None
    assert capacity.available_or_none(result) is None
    assert result["autofail_code"] == "AF-CAPACITY-UNMEASURED"
    assert "Which plan is your ollama-cloud account on?" in result["interview_question"]


def test_unknown_provider_declared_is_bounded_and_not_measured(monkeypatch, tmp_path):
    """A provider that is not on the cap table at all: a declared
    max_concurrent is a self-report, never a measurement. It is honoured only
    up to DEFAULT_CONSERVATIVE and must never be labelled MEASURED."""
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "some-random-unknown-llm", "max_concurrent": 50}),
        encoding="utf-8")
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_DECLARED_UNVERIFIED
    assert result["status"] != capacity.STATUS_MEASURED
    assert result["available"] == capacity.DEFAULT_CONSERVATIVE == 3
    assert capacity.available_or_none(result) == 3


def test_unknown_provider_declared_below_default_is_honoured(monkeypatch, tmp_path):
    """A self-throttling declaration below DEFAULT_CONSERVATIVE is still
    honoured -- only upward guesses are bounded, never downward caution."""
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "some-random-unknown-llm", "max_concurrent": 1}),
        encoding="utf-8")
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_DECLARED_UNVERIFIED
    assert result["available"] == 1


def test_broken_override_fails_closed_never_defaults(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text("{ not json", encoding="utf-8")
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_FAILED
    assert result["available"] is None
    assert capacity.autofail_payload(result)["code"] == "AF-CAPACITY-UNMEASURED"


# ---------------------------------------------------------------------------
# 3. Wave width is driven by the probe, not by a constant
# ---------------------------------------------------------------------------
FIVE_INDEPENDENT = {
    "manifest_version": 9901,
    "phases": [
        {"id": "A-alpha", "order": 1},
        {"id": "B-bravo", "order": 2},
        {"id": "C-charlie", "order": 3},
        {"id": "D-delta", "order": 4},
        {"id": "E-echo", "order": 5},
    ],
}


def _manifest(tmp_path) -> Path:
    path = tmp_path / "PIPELINE-MANIFEST.json"
    path.write_text(json.dumps(FIVE_INDEPENDENT), encoding="utf-8")
    return path


def _probe(available: int) -> dict:
    return {"probe_mode": "live", "status": "MEASURED", "provider": "ollama-cloud",
            "plan": "$20/month", "available": available, "dispatchable": available}


def test_five_independent_phases_at_three_dispatch_three_then_two(tmp_path):
    plan = execution_plan.build_execution_plan(_manifest(tmp_path), _probe(3))
    assert plan["wave_widths"] == [3, 2]
    assert plan["waves"] == [["A-alpha", "B-bravo", "C-charlie"], ["D-delta", "E-echo"]]


def test_same_dag_at_ten_is_one_wave(tmp_path):
    """Mutation proof: only the probe changed, and the plan changed with it."""
    plan = execution_plan.build_execution_plan(_manifest(tmp_path), _probe(10))
    assert plan["wave_widths"] == [5]


def test_plan_refuses_without_a_measurement(tmp_path):
    with pytest.raises(capacity.CapacityUnmeasured):
        execution_plan.build_execution_plan(_manifest(tmp_path), None)
    with pytest.raises(capacity.CapacityUnmeasured):
        execution_plan.build_execution_plan(_manifest(tmp_path), {"available": None})


def test_cap_wave_width_has_no_constant_fallback():
    assert execution_plan.cap_wave_width(3, 5) == 3
    assert execution_plan.cap_wave_width(10, 5) == 5
    with pytest.raises(capacity.CapacityUnmeasured):
        execution_plan.cap_wave_width(None, 5)


def test_dependency_logic_untouched(tmp_path):
    """A dependent phase never lands in the same wave as its dependency."""
    path = tmp_path / "PIPELINE-MANIFEST.json"
    path.write_text(json.dumps({
        "manifest_version": 9902,
        "phases": [{"id": "A-one", "order": 1},
                   {"id": "A-two", "order": 2},
                   {"id": "A-three", "order": 3}],
    }), encoding="utf-8")
    plan = execution_plan.build_execution_plan(path, _probe(10))
    assert plan["waves"] == [["A-one"], ["A-two"], ["A-three"]]


# ---------------------------------------------------------------------------
# 4. The dispatch path refuses
# ---------------------------------------------------------------------------
def test_dispatch_refuses_when_capacity_is_unmeasured(monkeypatch, tmp_path):
    spawned = []
    monkeypatch.setattr(launcher, "capacity_gate",
                        lambda: (None, {"status": "FAILED", "available": None,
                                        "notes": ["forced"]}))
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or pytest.fail("spawned!"))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    (tmp_path / "presentation_job.py").write_text("", encoding="utf-8")
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard")
    assert rc == launcher.DISPATCH_CAPACITY_REFUSED
    assert rc != 0
    assert spawned == []


def test_capacity_gate_probe_explosion_is_unmeasured_not_unlimited(monkeypatch):
    """A probe that blows up is UNMEASURED. It is never read as 'no limit'."""
    def boom():
        raise RuntimeError("9router database is locked")
    monkeypatch.setattr(capacity, "probe", boom)
    available, result = launcher.capacity_gate()
    assert available is None
    assert result["status"] == "FAILED"
    assert "9router database is locked" in " ".join(result["notes"])


def test_dispatch_refuses_a_parked_client_box(monkeypatch, tmp_path):
    """The realistic client-box case: Ollama Cloud detected, plan never declared."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES", (tmp_path / "absent.json",))
    openclaw = tmp_path / "openclaw.json"
    openclaw.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "ollama/glm-5.2"}}},
        "models": {"providers": {"ollama": {"baseUrl": "https://ollama.com/v1"}}},
    }), encoding="utf-8")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", openclaw)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    (tmp_path / "presentation_job.py").write_text("", encoding="utf-8")
    # capacity.measure_working_concurrent shells out to `ps`; stub it so the
    # Popen guard below can only ever fire on an ENGINE spawn.
    monkeypatch.setattr(capacity, "measure_working_concurrent", lambda: (0, "stub", True))
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("spawned despite PARKED capacity"))
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard")
    assert rc == launcher.DISPATCH_CAPACITY_REFUSED


# ---------------------------------------------------------------------------
# 5. The no-config hole: UNDETERMINED must not be silently treated as MEASURED
#
# These run dispatch() with background=False (subprocess.run, synchronous --
# the mode the module's own docstring calls out "for testing"). A real child
# interpreter runs a one-line stub `presentation_job.py` that touches a marker
# file, so "the engine was spawned" is proven by an actual process having
# actually run, not by mocking Popen and its .pid attribute.
# ---------------------------------------------------------------------------
def _stub_engine(tmp_path, monkeypatch):
    """No-config-box rig: isolated detection, ps stubbed, a stub
    presentation_job.py that proves it ran by writing a marker file.
    Returns (config_dir, marker_path)."""
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setattr(capacity, "measure_working_concurrent", lambda: (0, "stub", True))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    marker = tmp_path / "engine_ran.marker"
    (tmp_path / "presentation_job.py").write_text(
        "import pathlib, sys\n"
        f"pathlib.Path(r'''{marker}''').write_text('ran')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    return cfg, marker


def test_no_config_run_proceeds_at_conservative_floor_and_says_so_unmistakably(
        monkeypatch, tmp_path, capsys):
    """THE HOLE: almost every client box has no override, no 9Router combo, no
    OpenClaw config -- UNDETERMINED, available=3. Dispatch must proceed (an
    unconfigured box is not an outage) but the UNDETERMINED-ness must be
    impossible to miss: a distinct banner (never the MEASURED line), and a
    record in run state."""
    _, marker = _stub_engine(tmp_path, monkeypatch)
    run_dir = tmp_path / "run"
    rc = launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                           background=False)
    assert rc != launcher.DISPATCH_CAPACITY_REFUSED
    assert marker.is_file(), "expected the engine to actually run in the no-config case"

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "CAPACITY UNDETERMINED" in captured.err, "the banner must be loud on stderr"
    assert "capacity measured --" not in combined, (
        "the UNDETERMINED case must never print the same line as a real MEASURED probe")

    sidecar = run_dir / ".capacity-status.json"
    assert sidecar.is_file(), "UNDETERMINED must be recorded into run state"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    assert record["status"] == capacity.STATUS_UNDETERMINED
    assert record["available"] == capacity.DEFAULT_CONSERVATIVE == 3


def test_no_config_run_notifies_the_operator(monkeypatch, tmp_path):
    """Best-effort operator ping fires on the UNDETERMINED path (via
    report.dispatch, PRESENTATION_NOTIFY_CMD-gated, same mechanism watchdog.py
    already uses for system-level alerts)."""
    _stub_engine(tmp_path, monkeypatch)
    calls = []
    from presentation_job import report as report_mod
    monkeypatch.setattr(report_mod, "dispatch",
                        lambda chat_id, kind, message: calls.append((chat_id, kind, message)) or True)
    launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard",
                      background=False)
    assert calls, "expected a report.dispatch() call notifying the operator"
    chat_id, kind, message = calls[0]
    assert kind == "capacity_undetermined"
    assert "UNDETERMINED" in message


def test_dispatch_refuses_wide_parallel_request_when_capacity_undetermined(
        monkeypatch, tmp_path):
    """Refuse only the case the fix targets: capacity never measured AND the
    run asks for more parallel width than the conservative floor."""
    _, marker = _stub_engine(tmp_path, monkeypatch)
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard",
                           background=False, requested_parallel=16)
    assert rc == launcher.DISPATCH_CAPACITY_REFUSED
    assert not marker.is_file(), "the engine must not have run"


def test_dispatch_no_config_requesting_exactly_the_floor_still_proceeds(
        monkeypatch, tmp_path):
    """Requesting AT the conservative floor (or not declaring a request at
    all, the overwhelming majority of callers today) is not the blind-dispatch
    case -- only requesting MORE than the floor is."""
    _, marker = _stub_engine(tmp_path, monkeypatch)
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard",
                           background=False,
                           requested_parallel=capacity.DEFAULT_CONSERVATIVE)
    assert rc != launcher.DISPATCH_CAPACITY_REFUSED
    assert marker.is_file()


def test_measured_box_ignores_requested_parallel_and_dispatches_at_real_ceiling(
        monkeypatch, tmp_path, capsys):
    """A properly configured box (a real cap-table hit) is untouched by
    requested_parallel -- it is a MEASURED ceiling, not a floor to defend.
    execution_plan.py's wave-capping, not this gate, is what bounds a request
    that exceeds it."""
    _isolate(monkeypatch, tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps({"provider": "deepseek-direct", "plan": "v4-flash"}), encoding="utf-8")
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setattr(capacity, "measure_working_concurrent", lambda: (0, "stub", True))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    marker = tmp_path / "engine_ran.marker"
    (tmp_path / "presentation_job.py").write_text(
        "import pathlib, sys\n"
        f"pathlib.Path(r'''{marker}''').write_text('ran')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard",
                           background=False, requested_parallel=2000)
    assert rc != launcher.DISPATCH_CAPACITY_REFUSED
    assert marker.is_file()
    out = capsys.readouterr().out
    assert "capacity measured -- 2500 concurrent agents available" in out


def test_malformed_override_still_refuses_end_to_end(monkeypatch, tmp_path):
    """The behaviour this fix must NOT touch: a genuinely malformed
    capacity_override.json, read for real (not stubbed), still refuses --
    exercised through capacity.probe() -> launcher.capacity_gate() ->
    launcher.dispatch(), not a mocked capacity_gate()."""
    _, marker = _stub_engine(tmp_path, monkeypatch)
    cfg = Path(os.environ[capacity.CONFIG_DIR_ENV])
    (cfg / capacity.OVERRIDE_FILENAME).write_text("{ not json", encoding="utf-8")
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme", deck_type="standard",
                           background=False)
    assert rc == launcher.DISPATCH_CAPACITY_REFUSED
    assert not marker.is_file(), "the engine must not have run"
