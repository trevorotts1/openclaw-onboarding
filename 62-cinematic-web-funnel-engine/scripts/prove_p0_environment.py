#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_p0_environment.py — the P0-ENVIRONMENT phase gate declared in
CWFE-MANIFEST.json (`"gate": "scripts/prove_p0_environment.py"`,
`"py_symbol": "prove_p0_environment.evaluate"`, `"af_code":
"AF-CWFE-P0-ENVIRONMENT"`).

Thin wrapper around resolve_execution_environment.resolve(): every knob the
resolver's CLI exposes is read here from CWFE_* environment variables instead
of extra CLI flags, because the orchestrator (run_cinematic_web_funnel.py)
invokes every phase gate uniformly as `python3 <gate> --run-dir <run_dir>` and
never passes phase-specific flags (see run_cinematic_web_funnel._run_phase_gate).
This keeps the gate contract identical to every other phase gate in the
manifest while still giving the operator full control over resolution inputs.

Recognized environment variables (all optional except where resolution
requires them — see resolve_execution_environment.py's own fail-closed rules):
  CWFE_ENVIRONMENT                          explicit environment override
  CWFE_ROLE_CONFIG_PATH                     path to a project role-config JSON
  CWFE_RESOLUTION_FILE_PATH                 path to a JSON role->actual-model map
  CWFE_MODEL_ARCHITECT_JUDGE / _BUILDER /
    _MECHANICAL_VERIFIER / _DOCUMENTATION_WRITER   per-role actual model ids
  CWFE_ALLOW_CAPABILITY_FALLBACK            "1"/"true" to permit the explicit,
                                             recorded, non-judge fallback path
  CWFE_ACKNOWLEDGE_SAME_MODEL_BUILDER_JUDGE "1"/"true" plus CWFE_SAME_MODEL_REASON
    to explicitly, non-silently accept a builder/judge model collision

Writes environment-receipt.json into --run-dir on every invocation (PASS or
FAIL) so a failed run leaves a fully evidence-bearing artifact behind, never a
bare non-zero exit with no record.

Exit 0 = PASS, 2 = FAIL (matches run_cinematic_web_funnel._run_phase_gate's
returncode == 0 => PASS convention), 3 = usage error (missing/invalid
--run-dir or a malformed CWFE_ROLE_CONFIG_PATH/CWFE_RESOLUTION_FILE_PATH).

stdlib only. Exposes evaluate(run_dir) -> (bool, str) as required by the
manifest's py_symbol reference, in addition to the --run-dir CLI contract the
orchestrator's subprocess call uses.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import resolve_execution_environment as ree  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3


def _truthy(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def evaluate(run_dir: Path) -> Tuple[bool, str]:
    """Runs the P0 environment/model resolution, writes environment-receipt.json
    into run_dir, and returns (passed, detail_message). This is the function
    CWFE-MANIFEST.json's py_symbol "prove_p0_environment.evaluate" refers to —
    a future direct-import consumer (e.g. a test harness or a non-subprocess
    orchestrator path) can call this exact signature."""
    env = dict(os.environ)
    try:
        receipt = ree.resolve(
            environment_override=env.get("CWFE_ENVIRONMENT") or None,
            role_config_path=env.get("CWFE_ROLE_CONFIG_PATH") or None,
            resolution_file_path=env.get("CWFE_RESOLUTION_FILE_PATH") or None,
            allow_capability_fallback=_truthy(env.get("CWFE_ALLOW_CAPABILITY_FALLBACK", "")),
            acknowledge_same_model_builder_judge=_truthy(env.get("CWFE_ACKNOWLEDGE_SAME_MODEL_BUILDER_JUDGE", "")),
            same_model_reason=env.get("CWFE_SAME_MODEL_REASON") or None,
            env=env,
        )
    except ree.UsageError as exc:
        return False, f"USAGE ERROR: {exc}"

    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = ree.write_receipt(receipt, run_dir)

    if receipt["status"] == "PASS":
        detail = (
            f"environment-receipt.json written ({out_path.name}): "
            f"environment='{receipt['environment']['name']}', "
            f"judge='{receipt['roles']['architect_judge']['actual_model']}', "
            f"builder='{receipt['roles']['builder']['actual_model']}', "
            f"distinct={receipt['builder_judge_distinctness']['distinct']}"
        )
        return True, detail

    detail = f"[{receipt['af_code']}] " + "; ".join(receipt["failure_reasons"])
    return False, detail


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P0-ENVIRONMENT phase gate for the Cinematic and Web Funnel Engine. "
        "Invoked by run_cinematic_web_funnel.py as `prove_p0_environment.py --run-dir <dir>`."
    )
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir is not a directory: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    passed, detail = evaluate(run_dir)
    if passed:
        print(f"[PASS] P0-ENVIRONMENT — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] P0-ENVIRONMENT — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
