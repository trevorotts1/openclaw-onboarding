"""F19 -- lease takeover for a dead pid on the SAME host.

BROKEN (H6 in the Fable review): ``lease.acquire`` refused a lease whose pid
is provably dead when that lease had not yet passed ``expires_at``::

    elif not _holder_is_live(current) and not _expired(current, now):
        # Dead pid on our own host whose lease has not lapsed: refuse anyway.
        takeover = False

so every crashed engine parked its own run for up to ``DEFAULT_TTL_S`` (600 s)
even though the machine that could see the corpse was the machine asking. The
poller counts each refused dispatch as a launch, so the operator's summary line
says "launched" while nothing runs. lease.py's OWN module docstring already
promised the fixed behaviour ("taken over when EITHER its expires_at has passed
OR its pid is provably dead on this host") -- the code contradicted its
published contract.

FIXED: same host + ``ProcessLookupError`` on the recorded pid => immediate
takeover, logged as ``lease.takeover_dead_local_pid`` in
``working/logs/lease-events.jsonl``. Everything else keeps the TTL rule: a live
pid is never stolen, a ``PermissionError`` pid (the process EXISTS behind a
privilege boundary) is never stolen, and a foreign host's pid stays
uninterpretable so only its expiry rules.

This file is F19 of the Fable review. It is unrelated to the older
``test_fix19_research_web.py`` / ``test_fix19_sliced_reads.py`` (a different
numbering scheme entirely).
"""
import json
import os
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import lease as lease_mod  # noqa: E402


def _dead_local_pid() -> int:
    """A pid that is provably free on THIS host: spawn, wait, reap.

    Not a made-up large integer -- the child really ran and really exited, and
    ``Popen.wait()`` reaps it, so ``os.kill(pid, 0)`` raises ProcessLookupError
    rather than finding a zombie.
    """
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    pid = proc.pid
    for _ in range(200):  # up to ~2 s for the kernel to release the pid
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:  # pragma: no cover - pid reused by another user
            break
        time.sleep(0.01)
    pytest.skip(f"pid {pid} did not become free; cannot prove a dead pid here")


def _live_child():
    """A child process that stays alive until the caller terminates it."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


def _write_lease(run_dir: Path, *, pid, host: str, ttl_s: float = 600.0,
                 **extra) -> dict:
    """Plant a lease document directly, bypassing acquire()."""
    now = lease_mod._now()
    doc = {
        "pid": pid,
        "host": host,
        "session": "planted",
        "acquired_at": lease_mod._iso(now),
        "expires_at": lease_mod._iso(now + timedelta(seconds=ttl_s)),
    }
    doc.update(extra)
    path = lease_mod.lease_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


# ---------------------------------------------------------------------------
# The regression itself
# ---------------------------------------------------------------------------

def test_dead_local_pid_is_taken_over_immediately(tmp_path):
    """The fault: a crashed holder on our own host blocked for the full TTL."""
    run_dir = tmp_path / "pres-f19"
    planted = _write_lease(run_dir, pid=_dead_local_pid(),
                           host=socket.gethostname(), ttl_s=600.0)
    # The planted lease is NOT expired -- pristine main refused exactly here.
    assert not lease_mod._expired(planted), "fixture must test the unexpired path"

    held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                             ttl_s=600.0, wait_s=0.0)

    assert held is not None, (
        "a lease held by a pid that is provably dead on THIS host must be "
        "taken over immediately, not after the 600 s TTL")
    assert held.pid == os.getpid()
    on_disk = lease_mod.read(run_dir)
    assert on_disk["pid"] == os.getpid()
    assert on_disk["host"] == socket.gethostname()
    assert on_disk["who"] == "second-engine"


def test_takeover_of_dead_local_pid_is_logged(tmp_path):
    """The takeover must be auditable: lease.takeover_dead_local_pid."""
    run_dir = tmp_path / "pres-f19-log"
    dead = _dead_local_pid()
    _write_lease(run_dir, pid=dead, host=socket.gethostname(), ttl_s=600.0)

    held = lease_mod.acquire(run_dir, {"who": "second-engine"}, ttl_s=600.0)
    assert held is not None

    events_path = lease_mod.events_path(run_dir)
    assert events_path.exists(), f"no lease event log at {events_path}"
    rows = [json.loads(line) for line in
            events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    hits = [r for r in rows if r.get("event") == "lease.takeover_dead_local_pid"]
    assert hits, f"no lease.takeover_dead_local_pid row in {rows}"
    assert hits[-1]["previous_pid"] == dead
    assert hits[-1]["previous_host"] == socket.gethostname()
    assert hits[-1]["pid"] == os.getpid()


# ---------------------------------------------------------------------------
# The guards -- the fix must not become "always take over"
# ---------------------------------------------------------------------------

def test_live_local_pid_is_never_stolen(tmp_path):
    """A running holder on this host still owns its run."""
    run_dir = tmp_path / "pres-f19-live"
    proc = _live_child()
    try:
        _write_lease(run_dir, pid=proc.pid, host=socket.gethostname(),
                     ttl_s=600.0)
        held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                                 ttl_s=600.0, wait_s=0.0)
        assert held is None, "a LIVE holder's lease was stolen"
        assert lease_mod.read(run_dir)["pid"] == proc.pid
    finally:
        proc.terminate()
        proc.wait()


def test_foreign_host_dead_pid_still_waits_for_the_ttl(tmp_path):
    """Another box's pid means nothing here; only its expiry rules."""
    run_dir = tmp_path / "pres-f19-foreign"
    foreign = socket.gethostname() + "-not-this-box"
    _write_lease(run_dir, pid=_dead_local_pid(), host=foreign, ttl_s=600.0)

    held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                             ttl_s=600.0, wait_s=0.0)
    assert held is None, (
        "a foreign host's lease was taken over on the strength of a pid "
        "lookup that is meaningless off that box")
    assert lease_mod.read(run_dir)["host"] == foreign


def test_permission_error_pid_still_waits_for_the_ttl(tmp_path, monkeypatch):
    """EPERM means the process EXISTS -- never proof of a dead pid."""
    run_dir = tmp_path / "pres-f19-eperm"
    guarded = _dead_local_pid()
    _write_lease(run_dir, pid=guarded, host=socket.gethostname(), ttl_s=600.0)

    real_kill = os.kill

    def fake_kill(pid, sig, *args, **kwargs):
        if pid == guarded and sig == 0:
            raise PermissionError(1, "Operation not permitted")
        return real_kill(pid, sig, *args, **kwargs)

    monkeypatch.setattr(os, "kill", fake_kill)

    held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                             ttl_s=600.0, wait_s=0.0)
    assert held is None, (
        "a pid that answered EPERM (alive, other owner) was treated as dead")
    assert lease_mod.read(run_dir)["pid"] == guarded


def test_expired_lease_is_still_taken_over(tmp_path):
    """The pre-existing TTL takeover path must keep working."""
    run_dir = tmp_path / "pres-f19-expired"
    proc = _live_child()
    try:
        _write_lease(run_dir, pid=proc.pid, host=socket.gethostname(),
                     ttl_s=-5.0)
        held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                                 ttl_s=600.0, wait_s=0.0)
        assert held is not None, "an expired lease must never block"
        assert held.pid == os.getpid()
    finally:
        proc.terminate()
        proc.wait()


def test_malformed_pid_still_waits_for_the_ttl(tmp_path):
    """'Unreadable pid' is not 'provably dead' -- the TTL still rules."""
    run_dir = tmp_path / "pres-f19-malformed"
    _write_lease(run_dir, pid="not-a-pid", host=socket.gethostname(),
                 ttl_s=600.0)

    held = lease_mod.acquire(run_dir, {"who": "second-engine"},
                             ttl_s=600.0, wait_s=0.0)
    assert held is None, (
        "a lease whose pid cannot be read was treated as a proven corpse")
