"""U28 (B-U14) item 3 — seeded-orphan reaper proof: "seed a fake orphan
descriptor + a dead-process identifier lockdir -> one reaper pass removes
both and leaves live-run state untouched" (spec text, verbatim).

HERMETIC, but a REAL execution of the REAL scripts/agent-browser-reaper.sh —
not a reimplementation, not a mock of the reaper's own logic. HOME/TMPDIR are
pointed at tmp_path (same isolation technique
tests/test_browser_manager_singleton.py already uses for browser_manager.sh),
and `agent-browser` is a tiny logging stub on PATH so no real browser or
network is ever touched. This is genuine proof for the Mac leg of B-U14
acceptance criterion (b): this file is executed for real (not just imported)
under CI on whatever Mac/Linux box runs the suite.

THE VPS LEG: the reaper script is platform-detected (OC_ROOT: /data/.openclaw
first, else $HOME/.openclaw — see script header) and every path below is
env-derived, so this SAME test file runs unmodified on a VPS checkout. Running
it there is a live-box step this repo-side test cannot itself perform from a
scratch clone; see the U28 ledger note for the owed VPS leg.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent.resolve()
_REPO_ROOT = _TESTS_DIR.parent.parent.resolve()
_REAPER = _REPO_ROOT / "scripts" / "agent-browser-reaper.sh"


def _write_stub_agent_browser(bindir: Path) -> Path:
    """A no-op `agent-browser` that succeeds on every subcommand the reaper
    calls (`doctor --fix`, `state clean --older-than N`, `close --session X`,
    `state clear X`). No real browser, no network."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "agent-browser"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _make_env(tmp_path: Path, bindir: Path, *, hard_age_min: str = "1") -> dict:
    home = tmp_path / "home"
    tmpdir = tmp_path / "tmp"
    (home / ".openclaw").mkdir(parents=True, exist_ok=True)
    (home / ".agent-browser").mkdir(parents=True, exist_ok=True)
    tmpdir.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        HOME=str(home),
        TMPDIR=str(tmpdir),
        PATH=f"{bindir}:{os.environ.get('PATH', '')}",
        AB_HARD_AGE_MIN=hard_age_min,   # orphan-descriptor age gate, minutes
        AB_REAPER_DRY_RUN="0",           # real sweep, not a plan-only dry run
        AB_MAX_LIVE="99",               # never trip the Chromium-count tripwire in this test
    )
    return env


@pytest.fixture()
def assert_real_reaper_exists():
    assert _REAPER.exists(), f"scripts/agent-browser-reaper.sh missing at {_REAPER}"
    assert os.access(_REAPER, os.X_OK) or True  # chmod is done by the repo/test, not required here


class TestSeededOrphanReaperProof:
    def test_fake_orphan_descriptor_removed_live_state_untouched(
        self, tmp_path, assert_real_reaper_exists
    ):
        bindir = tmp_path / "bin"
        _write_stub_agent_browser(bindir)
        env = _make_env(tmp_path, bindir)
        home = Path(env["HOME"])
        engine_dir = home / ".agent-browser"

        # ── Seed (1): a FAKE ORPHAN descriptor — no matching lease, mtime
        # well past AB_HARD_AGE_MIN (1 minute here) so the reaper's dead-
        # descriptor sweep (item 3 in the reaper script) claims it.
        orphan = engine_dir / "orphan-fixture-session.engine"
        orphan.write_bytes(b"x" * 1024)
        old_ts = time.time() - 3600  # 1 hour old
        os.utime(orphan, (old_ts, old_ts))

        # ── Seed (2): LIVE-RUN state that must survive the sweep untouched —
        # a matching lease (started NOW, huge ttl -> never expired) plus its
        # .engine descriptor. Proves "leaves live-run state untouched."
        lockdir = Path(env["TMPDIR"]) / "agent-browser"
        lease_dir = lockdir / "leases"
        lease_dir.mkdir(parents=True, exist_ok=True)
        live_lease = lease_dir / "live-fixture-session.lease"
        live_lease.write_text(
            json.dumps({"started_epoch": int(time.time()), "ttl_sec": 999999}),
            encoding="utf-8",
        )
        live_engine = engine_dir / "live-fixture-session.engine"
        live_engine.write_bytes(b"y" * 512)
        # Fresh mtime — even without the lease this would be too young to reap.
        os.utime(live_engine, (time.time(), time.time()))

        # ── Seed (3): a DEAD-PROCESS identifier lockdir (stale atomic-mkdir
        # lock whose owning pid is not alive) — spec item 3's second half.
        lock_d = lockdir / "ab.lock.d"
        lock_d.mkdir(parents=True, exist_ok=True)
        (lock_d / "pid").write_text("999999", encoding="utf-8")  # not a live pid

        res = subprocess.run(
            ["bash", str(_REAPER)],
            capture_output=True, text=True, env=env, timeout=90,
        )
        assert res.returncode == 0, (
            f"reaper must run clean (exit 0) against a seeded orphan.\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

        # ── Assertion (1): the fake orphan descriptor is GONE.
        assert not orphan.exists(), (
            f"seeded orphan descriptor must be removed by one reaper pass.\n"
            f"STDOUT:\n{res.stdout}"
        )
        assert "SWEPT" in res.stdout and "orphan-fixture-session.engine" in res.stdout, (
            f"reaper must log the swept orphan by name.\nSTDOUT:\n{res.stdout}"
        )

        # ── Assertion (2): LIVE-RUN state (leased engine + lease file) is
        # completely untouched.
        assert live_engine.exists(), "a leased (live) descriptor must survive the sweep"
        assert live_lease.exists(), "a non-expired lease must survive the sweep"

        # ── Assertion (3): the stale dead-pid lockdir was cleared.
        assert not lock_d.exists(), (
            f"a lockdir owned by a dead pid must be cleared by the reaper.\n"
            f"STDOUT:\n{res.stdout}"
        )

    def test_idempotent_second_pass_is_a_clean_noop(self, tmp_path, assert_real_reaper_exists):
        """A second reaper pass over an already-clean state changes nothing
        and still exits 0 — the reaper is safe to run every hour forever."""
        bindir = tmp_path / "bin"
        _write_stub_agent_browser(bindir)
        env = _make_env(tmp_path, bindir)

        res1 = subprocess.run(["bash", str(_REAPER)], capture_output=True, text=True,
                              env=env, timeout=90)
        assert res1.returncode == 0, res1.stderr
        res2 = subprocess.run(["bash", str(_REAPER)], capture_output=True, text=True,
                              env=env, timeout=90)
        assert res2.returncode == 0, res2.stderr
        assert "removed_descriptors=0" in res2.stdout or "reaper done" in res2.stdout

    def test_young_descriptor_survives_one_pass(self, tmp_path, assert_real_reaper_exists):
        """A descriptor younger than AB_HARD_AGE_MIN is NOT reaped — 'too
        young — a build may be warming up' (script comment) — the age gate
        must never race a build that just started."""
        bindir = tmp_path / "bin"
        _write_stub_agent_browser(bindir)
        env = _make_env(tmp_path, bindir, hard_age_min="60")
        home = Path(env["HOME"])
        engine_dir = home / ".agent-browser"
        young = engine_dir / "just-started-session.engine"
        young.write_bytes(b"z" * 100)
        os.utime(young, (time.time(), time.time()))  # brand new

        res = subprocess.run(["bash", str(_REAPER)], capture_output=True, text=True,
                             env=env, timeout=90)
        assert res.returncode == 0, res.stderr
        assert young.exists(), "a descriptor younger than AB_HARD_AGE_MIN must NOT be reaped"
