"""FIX 61.4 follow-on (B5): an ultra-check REFUSAL in the poller is TERMINAL.

THE DEFECT
In presentation-intake-poll.sh's fresh-intake branch, the FIX 61.4 ultra
checks run first and, on refusal, log NOT LAUNCHED, increment
REFUSED_DISPATCH, and set PREFLIGHT_RC=$ULTRA_CHECK_RC. The FIX 5
standalone credit preflight block then ran UNCONDITIONALLY (whenever
RUN_MODE was set) and ended with `PREFLIGHT_RC=${PIPESTATUS[0]}` -- an
unconditional overwrite. When the credit preflight PASSED, the ultra
refusal was silently erased: the create guard saw PREFLIGHT_RC == 0 and
the engine started anyway. The FIX 61.4 validation (unknown or retired
OpenRouter model, non-mechanical phase with no route) therefore never
actually validated on the poller path, and the run was counted REFUSED
and then launched, breaking the poller's own tally
(seen == launched + refused + skips). When the preflight ALSO refused,
the same run was counted refused TWICE.

THE FIX
The standalone preflight block runs only while no refusal stands:
`if [ -n "${RUN_MODE:-}" ] && [ "$PREFLIGHT_RC" -eq 0 ]`. The first
refusal is terminal for the launch attempt: logged with its reason,
counted exactly once, and the engine is never started.

THE TESTS
Same harness discipline as test_fix5_fresh_intake_preflight.py: the gate
region is extracted VERBATIM from the shipped script (between the
FIX5-PREFLIGHT-GATE markers) and executed in a sandbox bash with a stub
python3. The stub distinguishes the two python calls in the gate by
shape: the ultra check is the gate's only `python3 -c` call (exit
$STUB_ULTRA_RC; 3 stands in for the real block's refusal exit), the
standalone preflight is `-m presentation_job.credit_preflight` (exit
$STUB_PREFLIGHT_RC), and any invocation carrying `--new` records that the
engine WOULD have started.

  1. STATIC -- the terminality guard exists verbatim in the shipped
     script, before the --new invocation.
  2. TERMINAL -- ultra refuses (3), preflight would pass (0): engine NOT
     started, REFUSED_DISPATCH == 1, the log carries the ultra refusal,
     and NO [credit-preflight] line appears (the preflight never ran, so
     nothing could overwrite the verdict).
  3. COUNTED ONCE -- ultra refuses (3), preflight would also refuse (1):
     REFUSED_DISPATCH == 1 exactly, engine NOT started.
  4. POSITIVE CONTROL -- ultra passes, preflight passes: engine starts,
     nothing refused (the guard did not nail the gate shut).
  5. PRESERVED BEHAVIOR -- ultra passes, preflight refuses: refused once
     with the credit-preflight line, engine NOT started (the FIX 5 gate
     still gates when it is the first refusal).

Every leg is offline: the stub python3 never runs a real check, a real
preflight, or a real engine. Scratch dirs are pytest tmp_path fixtures.

Flat file inside tests/, matching every sibling here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
POLLER = _SCRIPTS_DIR / "presentation-intake-poll.sh"

_GATE_RE = re.compile(
    r"# >>> FIX5-PREFLIGHT-GATE-BEGIN\n(?P<body>.*?)# <<< FIX5-PREFLIGHT-GATE-END",
    re.S,
)

STUB_PYTHON = """#!/usr/bin/env bash
# B5 sandbox stub -- never runs a real check, preflight, or engine.
#   python3 -c <...>  (the gate's FIX 61.4 ultra-check block, its only -c
#       call) -> exit $STUB_ULTRA_RC (3 = the real block's refusal exit).
#   -m presentation_job.credit_preflight -> exit $STUB_PREFLIGHT_RC.
#   * --new * -> touch $STUB_ENGINE_MARKER (proves the engine WOULD start).
if [ "$1" = "-c" ]; then
  exit "${STUB_ULTRA_RC:-0}"
fi
if [ "$1" = "-m" ] && [ "$2" = "presentation_job.credit_preflight" ]; then
  echo '{"verdict": "stub"}'
  exit "${STUB_PREFLIGHT_RC:-0}"
fi
for _a in "$@"; do
  if [ "$_a" = "--new" ]; then
    touch "$STUB_ENGINE_MARKER"
    exit 0
  fi
done
exit 0
"""


def _gate_body() -> str:
    src = POLLER.read_text()
    m = _GATE_RE.search(src)
    assert m, "FIX5-PREFLIGHT-GATE markers not found in the poll script"
    return m.group("body")


def test_static_terminality_guard():
    """The standalone preflight may run only while no refusal stands, and
    the guarded block still sits before the --new invocation."""
    src = POLLER.read_text()
    assert 'if [ -n "${RUN_MODE:-}" ] && [ "$PREFLIGHT_RC" -eq 0 ]; then' in src, (
        "the credit preflight block is not guarded on PREFLIGHT_RC still "
        "being 0 -- an ultra refusal can still be overwritten"
    )
    gate_pos = src.index("# >>> FIX5-PREFLIGHT-GATE-BEGIN")
    new_pos = src.index('"$ENGINE_ENTRY" --new')
    assert gate_pos < new_pos, "preflight gate must sit before the --new invocation"


def _run_gate(tmp_path: Path, ultra_rc: int, preflight_rc: int) -> dict:
    """Execute the extracted gate region in a sandbox bash with
    RUN_MODE=ultra. Returns the observed {refused, engine_started, log}."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(0o755)

    marker = tmp_path / "engine-started.marker"
    logf = tmp_path / "poller.log"
    run_dir = tmp_path / "pres-test"
    run_dir.mkdir()

    harness = "\n".join(
        [
            "set -uo pipefail",
            'log() { printf "%s\\n" "$*" >> "$STUB_LOG"; }',
            "REFUSED_DISPATCH=0",
            "RUN_MODE=ultra",
            f'SCRIPTS_DIR="{tmp_path}"',
            f'run_dir="{run_dir}"',
            f'ENGINE_ENTRY="{tmp_path}/engine.py"',
            f'ENGINE_INTAKE_TMP="{tmp_path}/intake.json"',
            _gate_body(),
            'printf "REFUSED_DISPATCH=%s\\n" "$REFUSED_DISPATCH" >> "$STUB_LOG"',
        ]
    )
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "STUB_ULTRA_RC": str(ultra_rc),
        "STUB_PREFLIGHT_RC": str(preflight_rc),
        "STUB_ENGINE_MARKER": str(marker),
        "STUB_LOG": str(logf),
    }
    r = subprocess.run(
        ["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, f"harness failed: {r.stderr}"
    log_text = logf.read_text(encoding="utf-8")
    m = re.search(r"REFUSED_DISPATCH=(\d+)", log_text)
    return {
        "refused": int(m.group(1)) if m else -1,
        "engine_started": marker.exists(),
        "log": log_text,
    }


def test_ultra_refusal_terminal_when_preflight_would_pass(tmp_path):
    """THE DEFECT: ultra checks refuse (unknown/retired model) but the
    standalone credit preflight passes. Pre-fix, PREFLIGHT_RC was
    overwritten to 0 and the engine started. The refusal must stand:
    no engine, exactly one refusal, and the preflight never ran."""
    obs = _run_gate(tmp_path, ultra_rc=3, preflight_rc=0)
    assert not obs["engine_started"], (
        "engine --new ran despite the ultra-check refusal -- the refusal "
        "was overwritten by the passing preflight"
    )
    assert obs["refused"] == 1, obs["log"]
    assert "ultra checks refused" in obs["log"]
    assert "[credit-preflight]" not in obs["log"], (
        "the standalone preflight ran after a terminal refusal:\n" + obs["log"]
    )


def test_ultra_refusal_counted_once_when_preflight_would_also_refuse(tmp_path):
    """Both gates would refuse: the run is refused exactly ONCE (the first
    verdict), never double-counted."""
    obs = _run_gate(tmp_path, ultra_rc=3, preflight_rc=1)
    assert not obs["engine_started"]
    assert obs["refused"] == 1, obs["log"]
    assert "ultra checks refused" in obs["log"]


def test_ultra_and_preflight_pass_starts_engine(tmp_path):
    """Positive control: both gates pass -> the engine starts and nothing
    is refused. The terminality guard must not nail the gate shut."""
    obs = _run_gate(tmp_path, ultra_rc=0, preflight_rc=0)
    assert obs["engine_started"], "engine --new did not run when both gates passed"
    assert obs["refused"] == 0


def test_preflight_refusal_still_refuses_when_ultra_passes(tmp_path):
    """Preserved FIX 5 behavior: when the ultra checks pass, the credit
    preflight remains the gate -- its refusal still refuses, once, with
    its own log line."""
    obs = _run_gate(tmp_path, ultra_rc=0, preflight_rc=1)
    assert not obs["engine_started"]
    assert obs["refused"] == 1, obs["log"]
    assert "credit preflight refused" in obs["log"]
