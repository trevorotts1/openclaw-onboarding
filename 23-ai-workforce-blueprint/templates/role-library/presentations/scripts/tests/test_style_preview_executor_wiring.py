#!/usr/bin/env python3
"""test_style_preview_executor_wiring.py — F18 (fix/dept-autonomy-faults-20260820).

P-STYLE-PREVIEW (order 4.85) declared executor {"kind": "agent"} in PIPELINE-
MANIFEST.json even though the phase's own preflight checker (_chk_style_preview,
build_deck.py) requires 9 REAL kie.ai renders (3 attention-grade style variants x
3 representative slides) plus an owner-approved pick before P4-RENDER may proceed.
A text LLM cannot produce a real kie.ai render, so the work-order dispatcher
(presentation_job/dispatcher.py, DECLINE_PHASES) correctly refused the phase on
every poll -- 224 declines in the live run, a permanent spin. The REAL executor
already existed and was simply never wired: build_deck.run_style_preview_samples()
(build_deck.py, --sample CLI mode) reads working/copy/style_preview_spec.json (or
working/style-preview/style_preview_spec.json) + a slides.json, renders the 9
samples via kie.ai, and writes style_samples_manifest.json -- exactly the artifact
_chk_style_preview and P-STYLE-PREVIEW's own produces_artifact require.

This file proves, without spending a single kie.ai render (no network, no API key):

  1. The DEPLOYED manifest (resolved the same way every real caller resolves it,
     via manifest_source.resolve_manifest) declares P-STYLE-PREVIEW's executor as
     {"kind": "script", "cmd": "...build_deck.py ... --sample ..."} -- NOT
     {"kind": "agent"}. This is the assertion that FAILS without the fix (see
     test 5 below, which proves that non-vacuously against the real pre-fix byte
     content taken from this same fix's own backup file).
  2. That cmd string resolves, via BOTH manifest dispatchers this department ships
     (run_signature_deck._build_executor_argvs -- the legacy runner's generic
     dispatch, and presentation_job.manifest.Manifest -- the 36-phase engine's
     phase table), to a real, on-disk build_deck.py invocation carrying --sample
     and a run_dir-scoped slides.json path -- not a placeholder, not a typo.
  3. build_deck.run_style_preview_samples is a real, importable, callable symbol
     with the signature the manifest's argv actually invokes it with (positional
     slides_path, run_dir, style_spec_path, api_key, keyword-only logo_url).
  4. The human-approval gate this fix was explicitly forbidden from touching
     (_chk_style_preview / STYLE_CHOICE_REL / owner_approved) is untouched: the
     preflight checker name and gate codes are exactly what they were before.
  5. NON-VACUOUSNESS: the identical "kind must be script, not agent" assertion,
     re-run against the byte-for-byte PRE-FIX manifest (this fix's own
     .bak-F18-20260820 backup, taken before any edit), actually raises. A test
     that passes against both the old and the new content would be worthless;
     this proves it discriminates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest

import build_deck
import run_signature_deck as rsd
from manifest_source import resolve_manifest

PHASE_ID = "P-STYLE-PREVIEW"


# Resolve independently of directory-nesting assumptions: walk up from SCRIPTS
# to the repo root the same way manifest_source.find_repo_root does, then point
# at the known backup path beside the live manifest (test 5 uses this to load
# this fix's own pre-edit .bak-F18-20260820 backup — never mutated).
def _repo_root() -> Path:
    cur = SCRIPTS
    for _ in range(12):
        candidate = cur / "universal-sops"
        if candidate.is_dir() and (candidate / "presentation-slide-craft" /
                                    "PIPELINE-MANIFEST.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("could not locate repo root from " + str(SCRIPTS))


def _live_phase() -> dict:
    manifest_path, _provenance = resolve_manifest(SCRIPTS)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    phases = {p["id"]: p for p in manifest["phases"]}
    assert PHASE_ID in phases, f"{PHASE_ID} missing from the deployed manifest entirely"
    return phases[PHASE_ID]


def _assert_script_executor(ph: dict) -> None:
    """The one assertion this whole file exists to defend. Raises AssertionError
    on the pre-fix {"kind": "agent"} shape; passes only on a real script
    executor naming build_deck.py --sample."""
    executor = ph.get("executor") or {}
    assert executor.get("kind") == "script", (
        f"{PHASE_ID} executor.kind is {executor.get('kind')!r}, not 'script' -- a text "
        "agent cannot render 9 real kie.ai images, so this phase can never be "
        "honestly fulfilled as an agent-kind phase (see build_deck._chk_style_preview / "
        "presentation_job/dispatcher.py DECLINE_PHASES).")
    cmd = executor.get("cmd") or ""
    assert "build_deck.py" in cmd, f"{PHASE_ID} executor.cmd does not name build_deck.py: {cmd!r}"
    assert "--sample" in cmd, f"{PHASE_ID} executor.cmd does not pass --sample: {cmd!r}"
    assert "--run-dir" in cmd and "{run_dir}" in cmd, (
        f"{PHASE_ID} executor.cmd does not thread {{run_dir}} through --run-dir: {cmd!r}")


# ---------------------------------------------------------------------------
# 1/4. Manifest wiring — the fixed shape, and that the human-approval gate is
# untouched.
# ---------------------------------------------------------------------------
def test_style_preview_phase_declared_as_script_executor():
    ph = _live_phase()
    assert ph["order"] == 4.85
    _assert_script_executor(ph)
    # verifier/preflight/gate_codes are unrelated to the executor fix and MUST be
    # byte-identical to before — this fix only wires the mechanical render, it
    # never weakens the owner-pick gate.
    assert ph["verifier"] == "phase_verifiers.verify"
    assert ph["preflight"]["checker"] == "_chk_style_preview"
    assert ph["preflight"]["required"] is True
    assert set(ph["gate_codes"]) == {"AF-STYLE-UNPICKED", "AF-STYLE-DOUBLECHARGE"}
    assert ph["produces_artifact"] == "working/style-preview/style_samples_manifest.json"


# ---------------------------------------------------------------------------
# 2. Both real dispatchers resolve the cmd to a real, on-disk renderer call.
# ---------------------------------------------------------------------------
def test_legacy_runner_dispatcher_resolves_to_real_build_deck_sample_call(tmp_path):
    ph = _live_phase()
    argvs = rsd._build_executor_argvs(ph["executor"]["cmd"], tmp_path, PHASE_ID)
    assert len(argvs) == 1, "P-STYLE-PREVIEW's cmd must be a single stage, not && chained"
    argv = argvs[0]
    assert argv[0] in ("python3", sys.executable) or argv[0].endswith("python3")
    assert argv[1] == "scripts/build_deck.py", argv
    assert "--sample" in argv, argv
    assert "--run-dir" in argv, argv
    assert str(tmp_path) in argv[argv.index("--run-dir") + 1], argv
    # the positional slides.json argument is scoped under the given run_dir, not
    # a bare/relative literal that would resolve against the wrong cwd.
    slides_arg = argv[2]
    assert slides_arg.startswith(str(tmp_path)), slides_arg
    assert slides_arg.endswith("slides.json"), slides_arg
    # the script this argv names actually exists on disk (not a typo/renamed file).
    assert (SCRIPTS / "build_deck.py").is_file()


def test_engine_manifest_dispatcher_resolves_to_real_build_deck_sample_call(tmp_path):
    from presentation_job.manifest import Manifest

    manifest_path, _ = resolve_manifest(SCRIPTS)
    m = Manifest(manifest_path)
    phase = next(p for p in m.phases if p.id == PHASE_ID)
    assert phase.executor_kind == "script"
    assert "build_deck.py" in (phase.executor_cmd or "")
    assert "--sample" in (phase.executor_cmd or "")


# ---------------------------------------------------------------------------
# 3. The real executor symbol exists with the signature the manifest invokes.
# ---------------------------------------------------------------------------
def test_run_style_preview_samples_symbol_exists_with_expected_signature():
    import inspect

    fn = build_deck.run_style_preview_samples
    assert callable(fn)
    params = list(inspect.signature(fn).parameters)
    assert params[:4] == ["slides_path", "run_dir", "style_spec_path", "api_key"], params
    assert "logo_url" in params


# ---------------------------------------------------------------------------
# 5. Non-vacuousness: the SAME check fails against the real pre-fix bytes.
# ---------------------------------------------------------------------------
def test_scratch_copy_of_pre_fix_manifest_fails_the_script_kind_assertion():
    root = _repo_root()
    backup = root / "universal-sops" / "presentation-slide-craft" / \
        "PIPELINE-MANIFEST.json.bak-F18-20260820"
    if not backup.is_file():
        pytest.skip(f"F18 pre-fix backup not present at {backup} — cannot prove "
                    "non-vacuousness without the real pre-fix bytes; this is a "
                    "missing fixture, not a passing check.")
    pre_fix = json.loads(backup.read_text(encoding="utf-8"))
    pre_fix_phases = {p["id"]: p for p in pre_fix["phases"]}
    pre_fix_ph = pre_fix_phases[PHASE_ID]
    # Confirm the backup really is the OLD, agent-kind content (sanity: if this
    # fails, the "backup" is not what this test thinks it is).
    assert pre_fix_ph["executor"] == {"kind": "agent"}, (
        "the F18 backup does not carry the expected pre-fix agent-kind executor — "
        "wrong file, or the backup was itself modified")
    with pytest.raises(AssertionError):
        _assert_script_executor(pre_fix_ph)
