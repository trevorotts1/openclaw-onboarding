"""F13 regression -- the undeliverable-message sweep must actually be RUNNABLE
and actually be SCHEDULED.

WHAT WAS BROKEN (measured on pristine origin/main @ ea331f82a, 2026-09-06):

  1. NOTHING SCHEDULED IT. `--sweep-undeliverable-roots` appeared in exactly
     one file in the whole repository -- presentation_job/__main__.py itself
     (9 occurrences: the argparse flag, the docstring, and its own print
     lines). presentation-watchdog.sh ran four passes (watchdog,
     reconcile-board, supervise, run-discovery) and none of them was the
     sweep. A message report.py queued into state["undeliverable"] therefore
     sat there forever unless a human ran the per-run sweep by hand against
     a run dir they had to already know the path of.

  2. THE FLAG WAS NOT EVEN WIRED TO ITS COMMAND. build_parser() declared
     `--sweep-undeliverable-roots`, but main() had no branch for it. The flag
     fell through every scan-root mode to `if not args.run_dir: die(EXIT_USAGE,
     "--run-dir is required")`:

         $ python3 presentation_job.py --sweep-undeliverable-roots \
               --scan-root <root>
         FATAL: --run-dir is required          # exit 2

     Control on the same instrument, same root, same interpreter:
     `--reconcile-board --scan-root <same root>` printed its full roots report
     and exited 12 -- so the CLI, the root and the run dir were all fine; only
     this flag was dead.

  3. THE COMMAND BODY WOULD HAVE CRASHED IF IT HAD BEEN REACHED.
     cmd_sweep_undeliverable_roots referenced four names that __main__.py never
     imported -- `resolve_scan_roots`, `format_roots_report`,
     `_find_run_dirs_multi`, `EXIT_SWEEP_HAD_FAILURES` -- and called
     resolve_scan_roots with a `roots_config=` keyword it does not accept (the
     parameter is `config_path=`; watchdog.py and sweep.py both pass it
     correctly). Calling the function directly on pristine main raised
     `NameError: name 'resolve_scan_roots' is not defined` while the sibling
     cmd_sweep_undeliverable, called through the same harness, reached real
     application code.

  So the spec's "exists and is called by nothing scheduled" understated it:
  the command was unreachable AND unrunnable. Scheduling alone would have
  added a pass that died `exit 2` on every tick.

WHAT THIS TEST PINS (each leg fails on pristine main for a different reason):

  Leg 1  STATIC   -- presentation-watchdog.sh ships a sweep pass.
  Leg 2  WIRING   -- main() dispatches the flag instead of demanding --run-dir.
  Leg 3  RUNTIME  -- the command executes end to end and a queued message is
                     really retried through the real transport boundary and
                     really leaves the queue.
  Leg 4  DYNAMIC  -- the sweep line is extracted VERBATIM from the shipped
                     watchdog script and executed. Nothing here is a
                     hand-written stand-in: the reason this defect survived is
                     that nothing ever ran the real line.
  Leg 5  CONTROL  -- leg 4's extractor is proven capable of failing, against a
                     SCRATCH COPY of the script with the pass deleted. Without
                     this, legs 1 and 4 could be passing vacuously.

Safety: every leg runs against a tmp_path scan root holding a synthetic run
dir. The only subprocess the sweep can start is the notify stub this test
writes itself (a python script that records its stdin and exits 0), so no
real transport, no engine, no renderer and no network call is reachable from
here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

WATCHDOG_SCRIPT = _SCRIPTS_DIR / "presentation-watchdog.sh"
ENTRY = _SCRIPTS_DIR / "presentation_job.py"

from presentation_job.state import STATE_SCHEMA_VERSION, EXIT_OK  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _logical_lines(src: str) -> list:
    """Collapse `\\`-continuations so a multi-line shell command is one line."""
    return re.sub(r"\\\n\s*", " ", src).split("\n")


def _extract_sweep_command(src: str) -> str:
    """Pull the sweep invocation VERBATIM out of the shipped watchdog script.

    Deliberately keyed on the FLAG, not on any comment or variable name, so a
    rename of the surrounding block cannot make this silently stop finding
    anything (it would fail loudly instead)."""
    candidates = [
        line.strip() for line in _logical_lines(src)
        if "--sweep-undeliverable-roots" in line and line.strip().startswith("python3")
    ]
    assert len(candidates) == 1, (
        "expected exactly one python3 invocation of --sweep-undeliverable-roots "
        f"in {WATCHDOG_SCRIPT.name}; found {len(candidates)}: {candidates}"
    )
    return candidates[0]


def _write_run_dir(root: Path, name: str, queued: list) -> Path:
    """A minimally valid job state document with an undeliverable queue.

    Shape copied from tests/test_fault14_undeliverable_loud.py::_mkstate --
    StateStore.load() rejects anything without job_id or with the wrong
    schema_version, and the per-run sweep this pass delegates to uses
    StateStore."""
    run_dir = root / name
    (run_dir / "working").mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "job_id": name,
        "run_dir": str(run_dir),
        "created_at": "2026-09-06T00:00:00+00:00",
        "manifest_path": "/x.json",
        "manifest_version": 25,
        "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch",
        "requester": {"chat_id": "12345"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": list(queued),
        "heartbeat": {}, "terminal": None,
    }
    (run_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return run_dir


def _queued(kind: str = "blocked", chat_id: str = "12345") -> dict:
    return {"at": "2026-09-06T00:00:00+00:00", "kind": kind, "chat_id": chat_id,
            "message": "your deck is paused", "attempts": 0, "outcome": "fail"}


def _notify_stub(tmp_path: Path) -> tuple:
    """A transport that succeeds and records what it was handed."""
    record = tmp_path / "notify-calls.jsonl"
    stub = tmp_path / "notify_stub.py"
    stub.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(record)!r}).open('a').write(sys.stdin.read() + '\\n')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {stub}", record


def _read_state(run_dir: Path) -> dict:
    return json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolated_roots(monkeypatch, tmp_path):
    """Hermetic root resolution: the sweep also reads PRESENTATION_SCAN_ROOTS
    and a scan-roots config file, and a box that has either set would make
    these legs scan real run dirs. Point both at nothing."""
    monkeypatch.delenv("PRESENTATION_SCAN_ROOTS", raising=False)
    monkeypatch.setenv("SCAN_ROOTS_CONFIG", str(tmp_path / "no-such-scan-roots.conf"))
    monkeypatch.delenv("OWNER_CHAT_ID", raising=False)


# ---------------------------------------------------------------------------
# Leg 1 -- STATIC: the watchdog schedules the sweep at all
# ---------------------------------------------------------------------------

class TestWatchdogSchedulesTheSweep:
    def test_watchdog_script_runs_the_sweep_pass(self):
        src = WATCHDOG_SCRIPT.read_text(encoding="utf-8")
        assert "--sweep-undeliverable-roots" in src, (
            "presentation-watchdog.sh does not run the undeliverable sweep. "
            "cmd_sweep_undeliverable_roots is the ONLY scheduled driver for "
            "state['undeliverable']; with no scheduler, a queued client notice "
            "(the measured run's 'paused' message) is never retried by anything."
        )

    def test_sweep_pass_is_given_the_scan_root(self):
        cmd = _extract_sweep_command(WATCHDOG_SCRIPT.read_text(encoding="utf-8"))
        assert '--scan-root "${SCAN_ROOT}"' in cmd, (
            "the sweep pass must be handed the same ${SCAN_ROOT} the other "
            f"passes get; got: {cmd}"
        )
        assert "${ROOTS_FLAGS}" in cmd, (
            "the sweep pass must honour ${ROOTS_FLAGS} (--roots-config) like "
            f"every other scanning pass, or extra roots are a blind spot; got: {cmd}"
        )

    def test_sweep_pass_cannot_abort_the_script_under_set_e(self):
        """The script runs under `set -e` and the sweep returns 11 when a run
        dir fails. An uncaptured nonzero there would kill the pass -- the exact
        failure mode the reconcile-board and supervise blocks already guard."""
        src = WATCHDOG_SCRIPT.read_text(encoding="utf-8")
        cmd = _extract_sweep_command(src)
        assert ("|| SWEEP_RC=$?" in cmd) or ("|| true" in cmd), (
            "the sweep invocation must capture or swallow its exit status; an "
            f"uncaptured nonzero aborts the whole watchdog under set -e: {cmd}"
        )


# ---------------------------------------------------------------------------
# Leg 2 -- WIRING: main() dispatches the flag
# ---------------------------------------------------------------------------

class TestFlagIsWiredToItsCommand:
    def test_main_does_not_demand_a_run_dir(self, tmp_path, capsys):
        """On pristine main this raised SystemExit(2) 'FATAL: --run-dir is
        required' -- the flag was declared and never dispatched."""
        from presentation_job.__main__ import main

        root = tmp_path / "runs"
        root.mkdir()
        rc = main(["--sweep-undeliverable-roots", "--scan-root", str(root)])
        out = capsys.readouterr().out
        assert rc == EXIT_OK, f"sweep over an empty root should pass; rc={rc}\n{out}"
        assert "sweep-undeliverable-roots: 0 run dirs" in out, (
            f"the sweep printed no ROOTS summary line:\n{out}"
        )


# ---------------------------------------------------------------------------
# Leg 3 -- RUNTIME: the command body actually executes and drains a queue
# ---------------------------------------------------------------------------

class TestSweepActuallyRetriesQueuedMessages:
    def test_queued_message_is_delivered_and_leaves_the_queue(self, tmp_path, monkeypatch, capsys):
        """On pristine main the body raised NameError before touching a run
        dir (resolve_scan_roots / format_roots_report / _find_run_dirs_multi /
        EXIT_SWEEP_HAD_FAILURES were never imported, and resolve_scan_roots was
        called with a `roots_config=` keyword it does not accept)."""
        from presentation_job.__main__ import main

        root = tmp_path / "runs"
        root.mkdir()
        run_dir = _write_run_dir(root, "pres-f13", [_queued()])
        notify_cmd, record = _notify_stub(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", notify_cmd)

        rc = main(["--sweep-undeliverable-roots", "--scan-root", str(root),
                   "--scan-depth", "3"])
        out = capsys.readouterr().out

        assert rc == EXIT_OK, f"rc={rc}\n{out}"
        assert record.exists(), (
            "the sweep never reached the transport boundary -- nothing was "
            f"retried:\n{out}"
        )
        payload = json.loads(record.read_text(encoding="utf-8").strip().splitlines()[0])
        assert payload["kind"] == "blocked"
        assert payload["message"] == "your deck is paused"

        after = _read_state(run_dir)
        assert after["undeliverable"] == [], (
            "the delivered message is still queued -- the sweep did not write "
            f"the drained state back:\n{out}"
        )
        assert "sweep-undeliverable-roots: 1 run dirs, 1 swept" in out, out

    def test_run_dirs_without_a_queue_are_left_alone(self, tmp_path, monkeypatch, capsys):
        """Cheap pre-check: a run dir with an empty queue must never be locked
        or rewritten -- a watchdog tick runs this every cycle over every run."""
        from presentation_job.__main__ import main

        root = tmp_path / "runs"
        root.mkdir()
        idle = _write_run_dir(root, "pres-idle", [])
        before = (idle / "state.json").read_text(encoding="utf-8")
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)

        rc = main(["--sweep-undeliverable-roots", "--scan-root", str(root)])
        out = capsys.readouterr().out
        assert rc == EXIT_OK, f"rc={rc}\n{out}"
        assert (idle / "state.json").read_text(encoding="utf-8") == before, (
            "an idle run dir's state.json was rewritten by the sweep"
        )
        assert "0 queued messages remaining across 0 run dirs seen" in out, out


# ---------------------------------------------------------------------------
# Leg 4 -- DYNAMIC: run the shipped line verbatim
# ---------------------------------------------------------------------------

class TestShippedWatchdogLineExecutes:
    def _run_shipped_line(self, cmd: str, scan_root: Path, log: Path, env: dict) -> int:
        script = f"set -e\nSWEEP_RC=0\n{cmd}\nexit $SWEEP_RC\n"
        proc = subprocess.run(
            ["sh", "-c", script],
            env={**os.environ, **env,
                 "SCRIPT_DIR": str(_SCRIPTS_DIR),
                 "SCAN_ROOT": str(scan_root),
                 "ROOTS_FLAGS": "",
                 "LOG": str(log)},
            capture_output=True, text=True, timeout=300,
        )
        assert proc.returncode != 127, (
            f"shell aborted (127) -- the line never ran: {proc.stderr}"
        )
        return proc.returncode

    def test_the_real_line_from_the_real_script_sweeps_a_real_queue(self, tmp_path):
        cmd = _extract_sweep_command(WATCHDOG_SCRIPT.read_text(encoding="utf-8"))
        root = tmp_path / "runs"
        root.mkdir()
        run_dir = _write_run_dir(root, "pres-shipped", [_queued(kind="progress")])
        notify_cmd, record = _notify_stub(tmp_path)
        log = tmp_path / "watchdog.log"

        rc = self._run_shipped_line(cmd, root, log, {"PRESENTATION_NOTIFY_CMD": notify_cmd})
        text = log.read_text(encoding="utf-8") if log.exists() else ""

        assert rc == 0, f"the shipped sweep line exited {rc}\n{text}"
        assert "sweep-undeliverable-roots: scan roots:" in text, (
            f"the shipped line produced no roots audit line:\n{text}"
        )
        assert "sweep-undeliverable-roots: 1 run dirs, 1 swept" in text, text
        assert record.exists(), f"the shipped line never retried anything:\n{text}"
        assert _read_state(run_dir)["undeliverable"] == [], text


# ---------------------------------------------------------------------------
# Leg 5 -- NEGATIVE CONTROL for legs 1 and 4
# ---------------------------------------------------------------------------

class TestExtractorIsNotVacuous:
    def test_extractor_fails_when_the_pass_is_removed(self, tmp_path):
        """Against a SCRATCH COPY (never the worktree) of the watchdog script
        with the sweep pass stripped, the extractor must fail. Without this,
        legs 1 and 4 could pass on any script at all."""
        src = WATCHDOG_SCRIPT.read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in _logical_lines(src)
            if "--sweep-undeliverable-roots" not in line
        )
        assert "--sweep-undeliverable-roots" not in stripped
        with pytest.raises(AssertionError):
            _extract_sweep_command(stripped)
