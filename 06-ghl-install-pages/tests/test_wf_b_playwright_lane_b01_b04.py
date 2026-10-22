"""WF-B (Skill 06 v3.0 P3) — browser lifecycle + resource guard, tests B01-B04.

Scope: the opt-in headless Playwright lane in tools/browser_manager.py and its
watchdog/lease contract with scripts/agent-browser-reaper.sh. Per plan §14.2:

  B01  headless normal/exception/timeout runs — no headed fallback; owned
       browser cleanup complete
  B02  ten sequential browser suites — zero owned orphan processes
  B03  two agents request the browser — single lease, bounded queue/wait
  B04  parent killed mid-operation — scoped watchdog closes owned children and
       preserves unrelated (personal-Chrome-like) processes

All browser processes here are OWNED DISPOSABLE test processes (short-lived
`python3 -c "time.sleep(...)"` children whose command line carries the owned
profile path). No real browser, no real GHL, no live writes, no personal
Chrome. Runs sequential (1 heavy job host-wide; Playwright 1 worker — these
suites spawn no Playwright at all: the launch_fn is a DI fake).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import browser_manager as bm  # noqa: E402


# ── owned disposable "browser" fake ─────────────────────────────────────────

class FakeBrowserHandle:
    """Owned disposable process standing in for a browser. Its command line
    carries the owned profile path, so the watchdog/reaper identity contract
    (lease + PID + start-time + exact profile path) applies to it exactly as to
    a real owned Chromium. ``close()`` is the supported close operation."""

    def __init__(self, profile_dir, options):
        self.options = dict(options)
        self.pages = []
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)", profile_dir],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @property
    def pid(self):
        return self.proc.pid

    def new_page(self):
        page = object()
        self.pages.append(page)
        return page

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _owned_pids(profile_dir):
    return bm.find_owned_pids(str(profile_dir))


def _spawn(tag_path):
    """A disposable process whose command line carries ``tag_path`` — used as
    the decoy (personal-Chrome-like) process in B04."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)", str(tag_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reap(proc):
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


# ── B01 ─────────────────────────────────────────────────────────────────────

class TestB01HeadlessAndCleanup:
    def test_headed_env_refused_before_any_resource(self, tmp_path):
        env = {"TMPDIR": str(tmp_path), "AGENT_BROWSER_HEADED": "true"}
        with pytest.raises(RuntimeError):
            with bm.PlaywrightSession(session="wf-b-b01", env=env,
                                      launch_fn=FakeBrowserHandle):
                pass
        assert not (tmp_path / "agent-browser" / "pw.lock.d").exists()
        assert list((tmp_path / "agent-browser" / "leases").glob("*.pwlease")) == []

    def test_headed_override_and_devtools_and_traces_refused(self):
        for overrides in ({"headless": False}, {"devtools": True},
                          {"record_har_path": "/tmp/x.har"},
                          {"record_video_dir": "/tmp/vid"}):
            with pytest.raises(bm.PWLaunchRefused):
                bm.pw_launch_options({}, overrides)
        for var in ("GHL_PLAYWRIGHT_HEADED", "PW_HEADED", "GHL_PW_HEADED"):
            with pytest.raises(bm.PWLaunchRefused):
                bm.pw_launch_options({var: "1"})

    def test_launch_options_always_headless(self):
        opts = bm.pw_launch_options({}, {"args": ["--no-sandbox"]})
        assert opts["headless"] is True
        assert opts["devtools"] is False
        assert opts["args"] == ["--no-sandbox"]

    def test_normal_run_cleans_owned_processes(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        profile = None
        with bm.PlaywrightSession(session="wf-b-b01n", env=env,
                                  launch_fn=FakeBrowserHandle,
                                  watchdog=False, wait_s=2) as s:
            profile = s._profile_dir
            s.new_page()
            assert _owned_pids(profile)  # the owned fake browser is live
        assert _owned_pids(profile) == []
        assert list((tmp_path / "agent-browser" / "leases").glob("*.pwlease")) == []
        assert not (tmp_path / "agent-browser" / "pw.lock.d").exists()

    def test_exception_run_still_cleans_up(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        profile = None
        with pytest.raises(RuntimeError, match="boom"):
            with bm.PlaywrightSession(session="wf-b-b01x", env=env,
                                      launch_fn=FakeBrowserHandle,
                                      watchdog=False, wait_s=2) as s:
                profile = s._profile_dir
                raise RuntimeError("boom")
        assert _owned_pids(profile) == []
        assert not (tmp_path / "agent-browser" / "pw.lock.d").exists()

    def test_timeout_run_stops_and_cleans(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        profile = None
        with pytest.raises(bm.PWLifetimeExceeded):
            with bm.PlaywrightSession(session="wf-b-b01t", env=env,
                                      launch_fn=FakeBrowserHandle,
                                      watchdog=False, wait_s=2,
                                      ttl_s=0.3) as s:
                profile = s._profile_dir
                time.sleep(0.5)
                s.assert_alive()  # bounded lifetime exceeded -> refuse, never warm
        assert _owned_pids(profile) == []
        assert not (tmp_path / "agent-browser" / "pw.lock.d").exists()

    def test_page_budget_two_pages(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        with bm.PlaywrightSession(session="wf-b-b01p", env=env,
                                  launch_fn=FakeBrowserHandle,
                                  watchdog=False, wait_s=2) as s:
            s.new_page()
            s.new_page()
            with pytest.raises(bm.PWPageBudgetExceeded):
                s.new_page()


# ── B02 ─────────────────────────────────────────────────────────────────────

class TestB02TenSequentialSuites:
    def test_ten_sequential_suites_zero_orphans(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        leases_dir = tmp_path / "agent-browser" / "leases"
        for i in range(10):
            with bm.PlaywrightSession(session=f"wf-b-b02-{i}", env=env,
                                      launch_fn=FakeBrowserHandle,
                                      watchdog=True,
                                      watchdog_interval_s=0.5,
                                      wait_s=2) as s:
                s.new_page()
                profile = s._profile_dir
                assert _owned_pids(profile), f"suite {i} had no live owned browser"
            assert _owned_pids(profile) == [], f"suite {i} leaked owned processes"
        # cumulative: zero orphan processes, zero stale leases, zero stale locks
        leftover = [p for i in range(10)
                    for p in _owned_pids(tmp_path / f"no-such-{i}")]
        assert leftover == []
        assert list(leases_dir.glob("*.pwlease")) == []
        assert not (tmp_path / "agent-browser" / "pw.lock.d").exists()


# ── B03 ─────────────────────────────────────────────────────────────────────

class _StubLedger:
    """Minimal AdmissionLedger-compatible stub (WF-A contract: acquire /
    heartbeat / release) with the one-browser budget."""

    def __init__(self):
        self.token = None
        self.acquires = 0
        self.releases = 0

    def acquire(self, kind, owner):
        assert kind == "browser"
        self.acquires += 1
        if self.token is not None:
            raise RuntimeError("SlotRefused: browser cap reached (1)")
        self.token = f"browser-stub-{self.acquires}"
        return self.token

    def heartbeat(self, token_id):
        assert token_id == self.token

    def release(self, token_id):
        assert token_id == self.token
        self.releases += 1
        self.token = None


class TestB03SingleLeaseBoundedQueue:
    def test_second_agent_refused_after_bounded_wait(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        first = bm.PlaywrightSession(session="wf-b-b03", env=env,
                                     launch_fn=FakeBrowserHandle,
                                     watchdog=False, wait_s=2)
        first.__enter__()
        try:
            leases = list((tmp_path / "agent-browser" / "leases").glob("*.pwlease"))
            assert len(leases) == 1  # single lease
            second = bm.PlaywrightSession(session="wf-b-b03-second", env=env,
                                          launch_fn=FakeBrowserHandle,
                                          watchdog=False, wait_s=0.6)
            t0 = time.time()
            with pytest.raises(RuntimeError, match="one-browser budget"):
                second.__enter__()
            assert time.time() - t0 < 5  # bounded queue wait, never unbounded
        finally:
            first.close()
        assert list((tmp_path / "agent-browser" / "leases").glob("*.pwlease")) == []

    def test_shared_admission_ledger_single_browser_token(self, tmp_path):
        env = {"TMPDIR": str(tmp_path)}
        ledger = _StubLedger()
        first = bm.PlaywrightSession(session="wf-b-b03l", env=env,
                                     launch_fn=FakeBrowserHandle,
                                     watchdog=False, wait_s=2, admission=ledger)
        first.__enter__()
        try:
            assert ledger.acquires == 1 and ledger.token is not None
            # second "agent" reaches the SHARED ledger (its own local lockdir,
            # so the refusal comes from the ledger's one-browser budget)
            second = bm.PlaywrightSession(session="wf-b-b03l-second", env=env,
                                          launch_fn=FakeBrowserHandle,
                                          watchdog=False, wait_s=2,
                                          lockdir=str(tmp_path / "other"),
                                          admission=ledger)
            with pytest.raises(RuntimeError, match="admission ledger refused"):
                second.__enter__()
            assert ledger.acquires == 2          # attempt recorded
            assert ledger.token is not None      # still exactly ONE token held
        finally:
            first.close()
        assert ledger.releases == 1 and ledger.token is None

    def test_stale_lock_reclaimed_pid_reuse_safe(self, tmp_path):
        lockdir = tmp_path / "agent-browser"
        lockdir.mkdir(parents=True)
        (lockdir / "pw.lock.d").mkdir()
        # owner file: a PID that is dead (or whose start-time cannot match)
        (lockdir / "pw.lock.d" / "owner").write_text("99999999\nno-such-start")
        lock = bm.OneBrowserLock(str(lockdir), wait_s=2)
        lock.acquire()  # reclaims the stale lock instead of blocking forever
        lock.release()


# ── B04 ─────────────────────────────────────────────────────────────────────

_DRIVER = r"""
import json, os, subprocess, sys, time
tools_dir, lockdir, profile = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, tools_dir)
import browser_manager as bm
os.makedirs(profile, exist_ok=True)
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(300)", profile],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
lease_path = bm.pw_lease_write(
    os.path.join(lockdir, "leases"), "wf-b-b04",
    owner_pid=os.getpid(), owner_start=bm.proc_start_time(os.getpid()),
    profile_path=profile, browser_pid=child.pid,
    browser_start=bm.proc_start_time(child.pid), ttl_sec=3600)
wd = subprocess.Popen(
    [sys.executable, os.path.join(tools_dir, "browser_manager.py"),
     "--pw-watchdog-serve", lease_path, "--pw-interval", "0.5"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
print(json.dumps({"lease": lease_path, "child": child.pid, "watchdog": wd.pid}),
      flush=True)
while True:
    time.sleep(60)
"""


class TestB04ParentKilledWatchdog:
    def test_watchdog_closes_owned_children_preserves_unrelated(self, tmp_path):
        lockdir = tmp_path / "agent-browser"
        profile = tmp_path / "owned-profile"
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER, encoding="utf-8")

        parent = subprocess.Popen(
            [sys.executable, str(driver), str(_TOOLS_DIR), str(lockdir),
             str(profile)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            line = parent.stdout.readline()
            info = json.loads(line)
            child_pid = info["child"]
            assert bm.proc_start_time(child_pid), "owned child must be live"
            # the owner's argv carries the profile path too (it passed it to the
            # child) — the child is the owned browser stand-in; the watchdog
            # must exclude the OWNER from any signal.
            assert child_pid in bm.find_owned_pids(str(profile))

            # decoy: personal-Chrome-like process WITHOUT the owned profile path
            decoy = _spawn(tmp_path / "personal-chrome-decoy")
            try:
                # parent agent killed mid-operation (SIGKILL — no finally, no trap)
                os.kill(parent.pid, signal.SIGKILL)
                parent.wait(timeout=5)

                # the detached watchdog must reclaim promptly: interval 0.5s
                # + graceful stop (well inside the 60s detection target)
                deadline = time.time() + 20
                while time.time() < deadline:
                    if bm.find_owned_pids(str(profile)) == []:
                        break
                    time.sleep(0.3)
                assert bm.find_owned_pids(str(profile)) == [], \
                    "watchdog did not close the owned child after parent death"

                # personal-Chrome-like decoy preserved (never signaled)
                assert decoy.poll() is None, "unrelated process was killed"
                assert bm.proc_start_time(decoy.pid), "decoy must still be alive"
                # lease reclaimed too
                assert list((lockdir / "leases").glob("*.pwlease")) == []
            finally:
                _reap(decoy)
        finally:
            _reap(parent)
            # belt: nothing of ours survives the test either way
            for pid in bm.find_owned_pids(str(profile)):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


# ── reaper wiring smoke (dry-run — changes nothing on any box) ──────────────

class TestReaperWatchdogWiring:
    def test_reaper_dry_run_delegates_pw_watchdog(self, tmp_path):
        reaper = _TOOLS_DIR.parent.parent / "scripts" / "agent-browser-reaper.sh"
        home = tmp_path / "home"
        (home / ".openclaw").mkdir(parents=True)
        env = dict(os.environ)
        env.update({"HOME": str(home), "TMPDIR": str(tmp_path),
                    "AB_REAPER_DRY_RUN": "1"})
        out = subprocess.run(["bash", str(reaper)], capture_output=True,
                             text=True, timeout=120, env=env)
        assert out.returncode == 0, out.stderr
        # dry-run: the delegation is planned and named, nothing is changed
        assert "Playwright-lane lease sweep" in out.stdout
        src = reaper.read_text(encoding="utf-8")
        assert "--pw-watchdog" in src
        # graceful-stop-before-force contract present in the reaper source
        src = reaper.read_text(encoding="utf-8")
        assert "SIGTERM then (after grace) SIGKILL" in src
        assert 'kill -TERM "$pid"' in src
