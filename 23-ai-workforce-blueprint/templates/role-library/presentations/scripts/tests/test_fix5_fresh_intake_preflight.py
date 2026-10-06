"""Fix 5 (H2) — fresh-intake ultra launches bypass the credit preflight.

THE DEFECT
`credit_preflight` ran only from `launcher.py`. The poller's fresh-intake
branch called the engine directly (`--new`), so a zero-balance run launched
without any credit check (the poller's own comment at line 470 admits it).

THE FIX
Just before the engine `--new` invocation, when RUN_MODE is set, the poller
runs `python3 -m presentation_job.credit_preflight --run-dir "$run_dir"
--mode "$RUN_MODE"`. If `${PIPESTATUS[0]}` is non-zero the run is counted as
REFUSED and the engine is never started. The `--new` branch is NOT re-routed
through the launcher. Also: `credit_preflight.main` now exits 0 on the
flag-off `{"skipped": ...}` result, so a disabled preflight never blocks.

THE TEST (MUST-TEST per the fix order): a fresh-intake run with a
zero-balance stub is refused before the engine starts.

Four legs:
  1. STATIC — the gate exists verbatim in the shipped script, positioned
     before the `--new` invocation, with the PIPESTATUS refusal accounting.
  2. DYNAMIC — the gate region is extracted VERBATIM (between the
     FIX5-PREFLIGHT-GATE markers) and executed in a sandbox bash. A stub
     `python3` makes the preflight exit 1 — the zero-balance refusal verdict
     (`main` exits 1 on anything but `proceed`, per its contract) — and
     records any `--new` engine start with a marker file. Assert the engine
     marker is ABSENT, REFUSED_DISPATCH == 1, and the log carries the
     refusal line.
  3. CONTROL (non-vacuous) — same harness with the preflight stub exiting 0:
     the engine IS started (marker present) and nothing is refused. A second
     control with RUN_MODE unset: no preflight runs, engine starts.
  4. UNIT — `credit_preflight.main` with PRESENTATION_CREDIT_PREFLIGHT=0
     (the flag-off `{"skipped": ...}` result) returns 0.

Every leg is offline: the stub python3 never runs a real preflight or a
real engine. Scratch dirs are pytest tmp_path fixtures.

Flat file inside tests/, manages its own import path — matching every
sibling here.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
POLLER = _SCRIPTS_DIR / "presentation-intake-poll.sh"

_GATE_RE = re.compile(
    r"# >>> FIX5-PREFLIGHT-GATE-BEGIN\n(?P<body>.*?)# <<< FIX5-PREFLIGHT-GATE-END",
    re.S,
)

STUB_PYTHON = """#!/usr/bin/env bash
# FIX 5 sandbox stub -- never runs a real preflight, never starts an engine.
#   -m presentation_job.credit_preflight ... -> exit $STUB_PREFLIGHT_RC
#       (1 stands in for the zero-balance refusal verdict: main exits 1 on
#       anything but "proceed").
#   * --new * -> touch $STUB_ENGINE_MARKER (proves the engine WOULD start).
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


def test_static_gate_before_new():
    """The gate is present, positioned before the --new invocation, and the
    refusal accounting keys off the preflight's own exit status."""
    src = POLLER.read_text()
    gate_pos = src.index("# >>> FIX5-PREFLIGHT-GATE-BEGIN")
    new_pos = src.index('"$ENGINE_ENTRY" --new')
    assert gate_pos < new_pos, "preflight gate must sit before the --new invocation"
    assert "python3 -m presentation_job.credit_preflight" in src
    assert '--run-dir "$run_dir" --mode "$RUN_MODE"' in src
    assert "PREFLIGHT_RC=${PIPESTATUS[0]}" in src
    assert 'if [ "$PREFLIGHT_RC" -ne 0 ]' in src


def _run_gate(tmp_path: Path, preflight_rc: int, run_mode: str | None) -> dict:
    """Execute the extracted gate region in a sandbox bash. Returns the
    observed {refused, engine_started, log}."""
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
            f'RUN_MODE={run_mode}' if run_mode is not None else "RUN_MODE=",
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


def test_zero_balance_refused_before_engine_starts(tmp_path):
    """MUST-TEST: preflight exits 1 (zero-balance refusal) -> the run is
    refused and the engine is never started."""
    obs = _run_gate(tmp_path, preflight_rc=1, run_mode="ultra")
    assert not obs["engine_started"], "engine --new ran despite preflight refusal"
    assert obs["refused"] == 1
    assert "credit preflight refused" in obs["log"]


def test_preflight_pass_starts_engine(tmp_path):
    """Control: preflight exits 0 -> the engine starts, nothing refused."""
    obs = _run_gate(tmp_path, preflight_rc=0, run_mode="ultra")
    assert obs["engine_started"], "engine --new did not run on preflight pass"
    assert obs["refused"] == 0


def test_no_run_mode_skips_preflight(tmp_path):
    """Control: RUN_MODE unset -> no preflight runs, engine starts."""
    obs = _run_gate(tmp_path, preflight_rc=1, run_mode=None)
    assert obs["engine_started"], "engine --new did not run with RUN_MODE unset"
    assert obs["refused"] == 0
    assert "credit-preflight" not in obs["log"]


def test_flag_off_skipped_returns_zero(tmp_path, monkeypatch):
    """A disabled preflight never blocks: the flag-off {"skipped": ...}
    result exits 0."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    monkeypatch.setenv("PRESENTATION_CREDIT_PREFLIGHT", "0")
    from presentation_job import credit_preflight

    rc = credit_preflight.main(["--run-dir", str(tmp_path), "--mode", "ultra"])
    assert rc == 0
