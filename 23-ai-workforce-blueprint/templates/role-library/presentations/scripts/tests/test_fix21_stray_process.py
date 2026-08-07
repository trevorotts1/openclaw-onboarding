#!/usr/bin/env python3
"""
test_fix21_stray_process.py — FIX-21 (D21): stray/zombie process cleanup + build health check.

FIX-21 gate (Gauntlet Loop per-task QC row):
    Launch a long-running fake build process; run the reaper/timeout.
    -> Process killed after timeout; health check distinguishes a real build from a
       stray (seeded both).
    Evidence: process-table listing before/after (python psutil, not grep).

D21 (from PRESENTATION-DEPARTMENT-ERRORS-DETECTED.md):
    "A `find ~ -name build_deck.py` process ran 18+ minutes as a zombie alongside the
     real build. Their presence masked whether the real render was alive (they matched
     the process filter)."

The engine's exec sites either had NO timeout (run_signature_deck._dispatch_render /
_dispatch_notes_sync) or a plain `subprocess.run(timeout=…)` that killed only the direct
child, orphaning grandchildren (the zombie path). And the old "process filter" was a NAME
match — any process mentioning build_deck.py looked like the live build.

This test proves the QC gate end-to-end with REAL seeded processes and REAL kills
(no mocks of the kill, no faked evidence):

  1. run_with_cleanup TIME-OUT + CLEANUP — a long-running exec (with a grandchild) is
     killed after a short timeout; BOTH the direct child and its grandchild die. The
     old `subprocess.run(timeout=…)` killed only the child, leaving the grandchild
     orphaned — the D21 mechanism.
  2. HEALTH CHECK CLASSIFICATION — seed a REAL build (alive run dir) AND two STRAYs
     (a `find`-style scanner with no run dir, and a build on a TERMINAL run dir). The
     classifier must label the real one REAL_BUILD and both strays STRAY.
  3. THE REAPER — reap_strays() kills the STRAYs (SIGTERM -> SIGKILL), leaves the REAL
     build running, and writes BEFORE/AFTER process-table evidence to
     process-reaper-evidence.json (psutil-quality; the exact evidence the QC row wants).

Every check is against the REAL process table (psutil when importable, `ps` fallback
otherwise) — never a grep, never a claim.

Run:  python3 test_fix21_stray_process.py
      python3 -m pytest test_fix21_stray_process.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import pytest  # noqa: F401  (pytest runs; the __main__ runner works without it)
except ImportError:
    class _PytestShim:
        @staticmethod
        def raises(exc, *a, **kw):
            class _Ctx:
                def __enter__(self):
                    return self
                def __exit__(self, et, ev, tb):
                    return ev is not None and issubclass(et, exc) if ev is not None else False
            return _Ctx()
    pytest = _PytestShim()

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import process_reaper as pr  # noqa: E402

try:
    import psutil  # noqa: F401
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _pid_state(pid: int) -> Optional[str]:
    """psutil status string (normalised: 'zombie' -> 'ZOMBIE'), or None when the pid
    is fully gone (reaped). psutil and `ps` spell it differently; normalise."""
    if HAS_PSUTIL:
        try:
            return psutil.Process(pid).status().upper()
        except psutil.NoSuchProcess:
            return None
        except psutil.ZombieProcess:
            return "ZOMBIE"
        except Exception:  # noqa: BLE001
            return None
    # Fallback: `ps` state.
    try:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           shell=False, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return "ZOMBIE" if "Z" in r.stdout.strip() else r.stdout.strip().upper()
        return None
    except Exception:  # noqa: BLE001
        return None


def _proc_row(pid: int) -> Optional[Dict]:
    for row in pr.list_processes():
        if row and row.get("pid") == pid:
            verdict, detail = pr.classify(row)
            row["class"] = verdict
            row["class_detail"] = detail
            return row
    return None


def _write_run_state(run_dir: Path, terminal: Optional[str], age_minutes: int) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    hb_ts = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
             ).isoformat(timespec="seconds")
    (run_dir / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "job_id": "pj_" + run_dir.name,
        "terminal": terminal,
        "heartbeat": {"last_checkpoint_at": hb_ts, "interval_minutes": 10},
    }))


_SLEEP_SRC = "import time; time.sleep(300)"


# ---------------------------------------------------------------------------
# 1. run_with_cleanup — timeout + WHOLE-GROUP cleanup (D21 mechanism)
# ---------------------------------------------------------------------------
class TestRunWithCleanup:
    def test_timeout_kills_child_and_grandchild(self, tmp_path):
        """A long-running exec that spawns a grandchild must be killed entirely on
        timeout — the old subprocess.run(timeout=…) killed only the direct child and
        orphaned the grandchild (D21)."""
        grand_pid_file = tmp_path / "grand.pid"
        parent_pid_file = tmp_path / "parent.pid"
        script = (
            "import subprocess, sys, time, os\n"
            "grand = subprocess.Popen([sys.executable, '-c', "
            "\"import time,os; open('" + str(grand_pid_file) +
            "','w').write(str(os.getpid())); time.sleep(300)\"])\n"
            "open('" + str(parent_pid_file) + "','w').write(str(os.getpid()))\n"
            "time.sleep(300)\n"
        )
        with pytest.raises(subprocess.TimeoutExpired):
            pr.run_with_cleanup([sys.executable, "-c", script],
                                timeout=2, capture=True)

        # Allow the pids to be written.
        deadline = time.time() + 10
        while (not grand_pid_file.exists() or not parent_pid_file.exists()) \
                and time.time() < deadline:
            time.sleep(0.2)
        assert parent_pid_file.exists(), "parent never wrote its pid file"
        assert grand_pid_file.exists(), "grandchild never wrote its pid file"
        parent_pid = int(parent_pid_file.read_text().strip())
        grand_pid = int(grand_pid_file.read_text().strip())

        # Both must be gone (or a reaped zombie) shortly after the timeout.
        time.sleep(1)
        assert _pid_state(parent_pid) is None or _pid_state(parent_pid) == "ZOMBIE", \
            f"parent pid {parent_pid} survived the timeout (D21 orphan)"
        assert _pid_state(grand_pid) is None or _pid_state(grand_pid) == "ZOMBIE", \
            f"grandchild pid {grand_pid} survived the timeout (D21 orphan)"

    def test_short_exec_completes(self, tmp_path):
        """A subprocess that finishes within the timeout completes normally."""
        r = pr.run_with_cleanup([sys.executable, "-c", "print('hi')"],
                                timeout=30, capture=True)
        assert r.returncode == 0
        assert "hi" in (r.stdout or "")


# ---------------------------------------------------------------------------
# 2. Health-check classification — real build vs strays (seeded both)
# ---------------------------------------------------------------------------
class TestClassification:
    def test_distinguishes_real_build_from_strays(self, tmp_path):
        """Seed a REAL build (alive run dir) AND two STRAYs (find-style, terminal run
        dir). classify() must label them REAL_BUILD / STRAY / STRAY — never lump the
        strays in with the real build (D21's masking failure)."""
        live = tmp_path / "live-run"
        _write_run_state(live, terminal=None, age_minutes=1)

        # REAL build: cmdline = python -c ... build_deck.py --run-dir <live>
        real = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                 "build_deck.py", "--run-dir", str(live)])
        # STRAY #1: D21's `find ~ -name build_deck.py` — executable is a scan tool,
        # a token names the script, but there is NO run dir.
        stray_find = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                       "find", "/Users", "-name", "build_deck.py"])
        # STRAY #2: a build process on a TERMINAL run dir.
        term = tmp_path / "term-run"
        _write_run_state(term, terminal="BLOCKED", age_minutes=1)
        stray_term = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                       "build_deck.py", "--run-dir", str(term)])
        try:
            time.sleep(0.5)
            row_real = _proc_row(real.pid)
            row_find = _proc_row(stray_find.pid)
            row_term = _proc_row(stray_term.pid)
            assert row_real is not None, "seeded real build not in the process table"
            assert row_find is not None, "seeded find stray not in the process table"
            assert row_term is not None, "seeded terminal stray not in the process table"

            v_real, d_real = pr.classify(row_real)
            v_find, d_find = pr.classify(row_find)
            v_term, d_term = pr.classify(row_term)

            assert v_real == "REAL_BUILD", f"real build classified {v_real}: {d_real}"
            assert v_find == "STRAY", f"find-style stray classified {v_find}: {d_find}"
            assert v_term == "STRAY", f"terminal-run stray classified {v_term}: {d_term}"
        finally:
            for p in (real, stray_find, stray_term):
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    p.kill()

    def test_zombie_is_stray(self):
        """A defunct/zombie process is ALWAYS a STRAY (it cannot be a live build)."""
        v, d = pr.classify({"cmdline": ["build_deck.py"], "cmdline_str": "build_deck.py",
                            "status": "ZOMBIE", "elapsed_seconds": 100.0})
        assert v == "STRAY"

    def test_watchdog_never_stray(self):
        v, d = pr.classify({"cmdline": ["python3", "presentation_job.py", "--watchdog",
                                        "--scan-root", "/tmp"],
                            "cmdline_str": "", "status": "running",
                            "elapsed_seconds": 10.0})
        assert v == "WATCHDOG"

    def test_shell_wrapper_mentioning_script_is_not_build(self):
        """A shell whose inline history merely mentions build_deck.py is OTHER, not a
        build — the substring-matching trap that made D21 strays look healthy."""
        v, d = pr.classify({"cmdline": ["/bin/zsh", "-c",
                                        "echo some history mentioning build_deck.py"],
                            "cmdline_str": "", "status": "running",
                            "elapsed_seconds": 10.0})
        assert v == "OTHER"


# ---------------------------------------------------------------------------
# 3. The reaper — kills strays, leaves the real build, writes before/after evidence
# ---------------------------------------------------------------------------
class TestReaper:
    def test_reap_kills_strays_leaves_real_build_and_writes_evidence(self, tmp_path):
        """Full reaper run: seed a real build + two strays, reap, and assert the
        strays are gone (or reaped zombies), the real build is still running, and the
        BEFORE/AFTER process-table evidence file is written (psutil-quality)."""
        live = tmp_path / "live-run"
        _write_run_state(live, terminal=None, age_minutes=1)

        real = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                 "build_deck.py", "--run-dir", str(live)])
        stray_find = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                       "find", "/Users", "-name", "build_deck.py"])
        term = tmp_path / "term-run"
        _write_run_state(term, terminal="BLOCKED", age_minutes=1)
        stray_term = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                       "build_deck.py", "--run-dir", str(term)])
        try:
            time.sleep(0.5)
            ev = tmp_path / "evidence.json"
            rec = pr.reap_strays(tmp_path, evidence_path=ev)

            # Evidence file written with before/after tables + counts.
            assert ev.is_file(), "reaper did not write the evidence file"
            data = json.loads(ev.read_text())
            assert "before_table" in data and "after_table" in data
            assert "counts_before" in data and "counts_after" in data
            assert len(data["before_table"]) > 0

            # The real build is alive and still classified REAL_BUILD after.
            after_real = _proc_row(real.pid)
            assert after_real is not None, "real build vanished after reap"
            assert after_real.get("class") == "REAL_BUILD", \
                f"real build misclassified after reap: {after_real.get('class')}"
            assert _pid_state(real.pid) not in (None,), \
                "real build was killed by the reaper"

            # Both strays are dead (gone or a reaped zombie).
            for p in (stray_find, stray_term):
                st = _pid_state(p.pid)
                assert st is None or st == "ZOMBIE", \
                    f"stray pid {p.pid} survived the reap (state={st})"

            # The kills[] record names both strays (not the real build).
            killed = {k["pid"] for k in rec["kills"]}
            assert stray_find.pid in killed, "find stray not in kills[]"
            assert stray_term.pid in killed, "terminal stray not in kills[]"
            assert real.pid not in killed, "real build was in kills[] (BUG)"
        finally:
            for p in (real, stray_find, stray_term):
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    try:
                        p.kill()
                    except Exception:  # noqa: BLE001
                        pass

    def test_dry_run_kills_nothing(self, tmp_path):
        """dry_run=True classifies and reports but never kills — and the health check
        still separates the real build (REAL_BUILD) from the stray (STRAY) in the same
        pass (the "seeded both" half of the QC gate)."""
        live = tmp_path / "live-run"
        _write_run_state(live, terminal=None, age_minutes=1)
        real = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                 "build_deck.py", "--run-dir", str(live)])
        term = tmp_path / "term-run"
        _write_run_state(term, terminal="BLOCKED", age_minutes=1)
        stray = subprocess.Popen([sys.executable, "-c", _SLEEP_SRC,
                                  "build_deck.py", "--run-dir", str(term)])
        try:
            time.sleep(0.5)
            rec = pr.reap_strays(tmp_path, dry_run=True)
            assert rec["kills"] == [], "dry-run must not kill anything"
            # Both seeded processes still alive (dry-run reaps nothing).
            assert _pid_state(stray.pid) not in (None,), \
                "dry-run killed the stray (BUG)"
            assert _pid_state(real.pid) not in (None,), \
                "dry-run killed the real build (BUG)"
            # Health check separated them in the same pass.
            counts = rec["counts_before"]
            assert counts.get("REAL_BUILD", 0) >= 1, \
                f"real build not classified REAL_BUILD in dry-run: {counts}"
            assert counts.get("STRAY", 0) >= 1, \
                f"stray not classified STRAY in dry-run: {counts}"
        finally:
            for p in (real, stray):
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    p.kill()


if __name__ == "__main__":
    import inspect
    import traceback
    import tempfile
    failed = 0
    total = 0
    for cls in (TestRunWithCleanup, TestClassification, TestReaper):
        for name in sorted(dir(cls)):
            if not name.startswith("test_"):
                continue
            fn = getattr(cls, name)
            total += 1
            try:
                if "tmp_path" in inspect.signature(fn).parameters:
                    with tempfile.TemporaryDirectory() as td:
                        fn(cls(), Path(td))
                else:
                    fn(cls())
                print(f"PASS {cls.__name__}.{name}")
            except Exception:
                failed += 1
                print(f"FAIL {cls.__name__}.{name}")
                traceback.print_exc()
    if failed:
        sys.exit(1)
    print(f"\nALL FIX-21 QC TESTS PASSED ({total} checks)")
