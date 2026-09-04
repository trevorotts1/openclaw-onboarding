#!/usr/bin/env python3
"""test_wave_contract_three_seams.py -- FIX 104 (Master Part 8).

THE PROBLEM the fix deletes: owning_role, measured_capacity, and every extra
stamp field (route_reason, capacity_status, requested_alias, ...) were dropped
at three independent seams --

  seam 1  dispatcher._prompt_routing_stamp     (shape lived in dispatcher.py)
  seam 2  dispatcher._dispatch_prompt_phase_parallel  (hand-built wave_input)
  seam 3  parallel_prompt_worker.validate_input (hand-built whitelist rebuild)

P4-PROMPT burned 21 attempts in the live run (ledger F20/F21/F41/F42/F43); the
serial path never broke, because the serial loop never round-tripped through a
whitelist.

FIX 104: ONE WaveContract in presentation_job/wave_contract.py. Dispatcher
builds it from the routing stamp; wave_input() produces the canonical document;
validate_input() is the single whole-input gate -- identity-preserving, so NO
field can be lost between stamp and validate no matter which side grows first.

These tests drive the three seams in both cases QC.md names:

  case A (profile present): stamp -> wave_input -> validate with a routed
      profile stamp; asserts NO field is lost -- every input key appears in
      the validated output, and the worker's own validate_input also accepts
      the written document (the end-to-end wire shape).
  case B (no profile): the routing stamp falls back to the dispatcher default
      (DeepSeek-direct, router=disabled); asserts the default stamp round-trips
      through the contract AND the dispatcher's serial fallback branch still
      runs -- i.e. the worker-reject path lands in
      _dispatch_prompt_phase_serial, not in a crash, not in a fabricated route.

Also proves the F41 class fix NON-VACUOUSLY: measured_capacity popped to None
is rejected by the SAME validator with the exact F41 message, and an unknown
stamp field (the class that silently died before) survives verbatim.

No network, no API key, no provider call: the worker's transport seam is
stubbed through parallel_prompt_worker.provider_call.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402
from presentation_job import wave_contract  # noqa: E402
from presentation_job.wave_contract import (  # noqa: E402
    WaveContract, RoutingStamp, PromptConstraints, WaveContractError,
    SCHEMA_VERSION as WC_SCHEMA_VERSION,
)

CONTRACT_FIELDS = ("run_id", "run_dir", "owning_role", "routing", "slides",
                   "prompt_constraints", "schema_version", "phase_id")

# FIX 41's exact rejection -- the message must never silently change shape,
# because real dispatchers string-match it in sidecars.
F41_REJECT = "routing.measured_capacity must be a positive integer"


def _slide(ordinal: int) -> Dict[str, Any]:
    return {
        "slide_id": f"slide-{ordinal:02d}",
        "ordinal": ordinal,
        "copy": ["copy text"],
        "archetype": "hero",
        "research_anchors": [],
        "design_tokens": {},
        "negative_requirements": [],
    }


def _routed_stamp() -> Dict[str, Any]:
    """A stamp as _prompt_routing_stamp produces when a routed profile is
    present: the FIX 7 keys PLUS the probe-derived capacity truthtell keys."""
    return {
        "provider": "deepseek-direct",
        "model": "deepseek-v4-flash",
        "router": "model_router",
        "mode": "standard",
        "measured_capacity": 8,
        "route_reason": "profile route: primary alias eligible",
        "requested_alias": "deepseek-v4-flash",
        "capacity_status": "unbounded-byok",
        "capacity_source": "capacity-probe",
    }


def _default_stamp() -> Dict[str, Any]:
    """A stamp as _prompt_routing_stamp produces when the router is absent /
    no profile captured (pre-FIX-7 fallback, shape unchanged by FIX 7)."""
    return {
        "provider": "deepseek-direct",
        "model": "dispatcher.DEEPSEEK_MODEL",
        "router": "disabled",
        "mode": "standard",
        "measured_capacity": 8,
        "capacity_status": "fallback-default",
        "capacity_source": "dispatcher-default",
    }


def _contract(stamp: Dict[str, Any], n: int = 3) -> WaveContract:
    return WaveContract(
        run_id="pres-wave-a1",
        run_dir="/tmp/pres-wave-a1",
        owning_role="prompt-author-presentations",
        routing=RoutingStamp(
            provider=stamp["provider"],
            model=stamp["model"],
            router=stamp["router"],
            mode=stamp["mode"],
            measured_capacity=stamp["measured_capacity"],
            extra={k: v for k, v in stamp.items()
                   if k not in ("provider", "model", "router", "mode",
                                "measured_capacity")},
        ),
        slides=[_slide(i) for i in range(1, n + 1)],
        prompt_constraints=PromptConstraints(min_chars=9000, max_chars=18000,
                                             required_blocks=(
                                                 "[ARCHETYPE", "DO-NOT BLOCK",
                                                 "Do not ")),
    )


# ---------------------------------------------------------------------------
# seam 1 + 2: stamp -> wave_input. A routed profile stamp enters the
# contract and the canonical document carries EVERY field, extra ones included.
# ---------------------------------------------------------------------------
def test_seam1_stamp_to_wave_input_profile_present_no_field_lost():
    stamp = _routed_stamp()
    contract = _contract(stamp, n=12)
    doc = contract.wave_input()

    assert doc["schema_version"] == WC_SCHEMA_VERSION == 1
    assert doc["phase_id"] == "P4-PROMPT"
    assert doc["run_id"] == "pres-wave-a1"
    assert doc["owning_role"] == "prompt-author-presentations"
    assert len(doc["slides"]) == 12
    for key in stamp:
        assert doc["routing"][key] == stamp[key], \
            f"stamp field {key!r} lost between stamp and wave_input"
    assert doc["prompt_constraints"]["min_chars"] == 9000
    assert doc["prompt_constraints"]["max_chars"] == 18000
    assert doc["prompt_constraints"]["required_blocks"] == [
        "[ARCHETYPE", "DO-NOT BLOCK", "Do not "]


# ---------------------------------------------------------------------------
# seam 3: validate_input. Identity-preserving: EVERY input key survives, and
# the worker's own gate accepts the dispatcher's written document verbatim.
# ---------------------------------------------------------------------------
def test_seam3_validate_no_field_lost_profile_present():
    stamp = _routed_stamp()
    contract = _contract(stamp, n=12)
    doc = contract.wave_input()

    validated = wave_contract.validate_input(doc, "test-contract")
    for key in doc:
        assert key in validated, f"validate_input dropped field {key!r}"
    assert validated["owning_role"] == "prompt-author-presentations"
    assert validated["routing"]["route_reason"] == stamp["route_reason"]
    assert validated["routing"]["capacity_status"] == "unbounded-byok"
    assert validated["routing"]["requested_alias"] == "deepseek-v4-flash"
    assert validated["routing"]["measured_capacity"] == 8
    assert validated["slides"] == doc["slides"]

    # The worker's gate is the SAME gate (no second whitelist): accepting the
    # output of the contract's own wave_input() proves the wire shape.
    accepted = ppw.validate_input(doc, "test-worker")
    assert accepted == validated

    # And the validator survives a completely unknown extra field -- the class
    # of field the old whitelist silently deleted (F41/F42).
    grown = dict(doc)
    grown["routing"] = dict(doc["routing"])
    grown["routing"]["future_fix_field"] = {"nested": ["kept"]}
    out = wave_contract.validate_input(grown, "grown")
    assert out["routing"]["future_fix_field"] == {"nested": ["kept"]}


# ---------------------------------------------------------------------------
# The F41 rejection still fires -- non-vacuously -- with the exact message.
# ---------------------------------------------------------------------------
def test_f41_measured_capacity_none_still_rejected():
    stamp = _routed_stamp()
    doc = _contract(stamp, n=2).wave_input()
    bad = dict(doc)
    bad["routing"] = dict(doc["routing"])
    bad["routing"]["measured_capacity"] = None
    with pytest.raises(WaveContractError) as exc:
        wave_contract.validate_input(bad, "fixture")
    assert F41_REJECT in str(exc.value)
    with pytest.raises(ppw.WorkerUsageError) as w_exc:
        ppw.validate_input(bad, "fixture")
    assert F41_REJECT in str(w_exc.value)


# ---------------------------------------------------------------------------
# case B (no profile): the DEFAULT stamp (router disabled / absent profile)
# round-trips through the contract, and the dispatcher's serial fallback still
# runs when the worker rejects the input (FIX 15 behavior preserved).
# ---------------------------------------------------------------------------
def test_case_b_no_profile_default_stamp_roundtrips(tmp_path, monkeypatch):
    # no profile: model_router would return profile_state "absent"; the
    # dispatcher stamp = the deepseek-direct default. Build that stamp here
    # and prove the contract round-trips it identically.
    default = _default_stamp()
    doc = _contract(default, n=5).wave_input()
    validated = wave_contract.validate_input(doc, "no-profile")
    assert validated["routing"]["router"] == "disabled"
    assert validated["routing"]["provider"] == "deepseek-direct"
    for key in default:
        assert validated["routing"][key] == default[key]
    assert validated["owning_role"] == "prompt-author-presentations"


def test_case_b_serial_fallback_runs_when_worker_rejects(tmp_path, monkeypatch):
    """QC.md case B: 'no profile: serial fallback runs'. Force the worker to
    reject the wave input (exit-2 class) and prove the dispatcher lands in
    _dispatch_prompt_phase_serial -- the documented rollback -- instead of
    crashing or fabricating a route."""
    from presentation_job.manifest import Phase

    run_dir = tmp_path / "runs" / "pres-fallback"
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": i, "copy": ["x"], "archetype": "a",
                     "research_anchors": [], "design_tokens": {},
                     "negative_requirements": []} for i in range(1, 6)]),
        encoding="utf-8")
    # token cost is stubbed to zero: the serial loop's call site is
    # dispatch_complete (compose_prompt feeds it), so BOTH must be stubbed or
    # the fixture would spend a real provider call (measured live: the unstub
    # case reached deepseek-direct and burned an HTTP 402). Verify is stubbed
    # by the same content marker.
    monkeypatch.setattr(dispatcher, "compose_prompt",
                        lambda **kw: ("SYS", "USER"))
    monkeypatch.setattr(
        dispatcher, "dispatch_complete",
        lambda system_prompt, user_prompt, **kw:
            ("PROMPT BODY " + "x" * 9000, {}, {"model": "stub",
                                               "provider": "stub"}))
    monkeypatch.setattr(
        dispatcher, "_verify_single_prompt",
        lambda run_dir, ordinal: (True, []))

    class RejectingPPW:  # a worker whose validate rejects: WorkerUsageError
        class WorkerUsageError(RuntimeError):
            pass

        @staticmethod
        def run_worker(data):
            raise RejectingPPW.WorkerUsageError("fixture: forced rejection")

    monkeypatch.setattr(dispatcher, "_ppw", RejectingPPW)

    phase = Phase(
        id="P4-PROMPT", order=4.7,
        owning_role="prompt-author-presentations",
        produces_artifact=["working/prompts/slide-*.txt"],
        executor_kind="agent", executor_cmd=None,
        verifier="phase_verifiers.verify", workers=4,
    )
    result = dispatcher._dispatch_prompt_phase_parallel(
        run_dir, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=phase, worker_id="w1")

    # The serial path produced the 5 prompt files (stub content) and the
    # dispatcher sidecar names the fallback with the worker's rejection
    # reason. Sidecar truth: _append_sidecar writes
    # working/work-orders/<phase>.dispatcher-log.jsonl (JSONL, one record per
    # row) -- NOT working/checkpoints/P4-PROMPT.json (no such file exists;
    # the checkpoints dir holds prompt-wave-input.json and the worker's
    # result file, and the worker writes no dispatcher rows at all).
    prompts = sorted(p.name for p in
                     (run_dir / "working" / "prompts").glob("*.txt"))
    assert prompts == [f"slide-{i:02d}.txt" for i in range(1, 6)], prompts
    sidecar = run_dir / "working" / "work-orders" / "P4-PROMPT.dispatcher-log.jsonl"
    assert sidecar.is_file(), f"no dispatcher sidecar at {sidecar}"
    rows = [json.loads(line) for line in
            sidecar.read_text(encoding="utf-8").splitlines() if line.strip()]
    fallback = [r for r in rows if r.get("status") == "serial_fallback"]
    assert fallback, rows
    assert "fixture: forced rejection" in (fallback[0].get("reason") or ""), \
        fallback[0]
    assert result.status in ("ok", "exhausted"), result.status
