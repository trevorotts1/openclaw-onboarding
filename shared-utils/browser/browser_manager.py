#!/usr/bin/env python3
"""shared-utils/browser/browser_manager.py — headless lease / lock / teardown
for managed browser execution (GHL delivery, stream W3, unit W3A-U1).

ONE WRITER per mutable browser session or location — even with spare CPU.
Explicit deadlines everywhere. Owned cleanup only.

What this module is
-------------------
The canonical writer-exclusion + lease + teardown primitives that delivery
code uses before it mutates anything browser-backed:

  1. ``WriterLease`` — exclusive writer per (kind, target_id): "session"
     (one mutable browser session) or "location" (one GHL location), or any
     caller-declared mutable target. Second writer is REFUSED after a BOUNDED
     wait — never a silent second writer, never an unbounded queue.
  2. Explicit deadlines — acquire wait deadline (``wait_s``), bounded lease
     lifetime (``ttl_sec``, absolute — a lease never becomes immortal), and a
     bounded teardown grace (``grace_s``) before force.
  3. Owned cleanup — ``release()`` tears down ONLY what the lease provably
     owns: processes carrying the lease's EXACT profile path, identified by
     PID + start-time (PID-reuse safe), graceful stop first, force only a
     provably owned survivor. Personal Chrome / attended profiles are never
     signaled. ``sweep()`` reclaims dead-owner / expired leases the same way.

What this module is NOT
-----------------------
It never launches a browser and never imports Playwright (the runtime lane
lives with the adapters), and it does NOT hold the box one-browser budget —
that singleton stays with ``06-ghl-install-pages/tools/browser_manager.sh``
(``ab.lock.d`` / ``ab.lock``, ``lock=1``). This module EXTENDS the browser
manager family's established conventions instead of competing with them:
leases land under the same ``${TMPDIR:-/tmp}/agent-browser`` root the host
reaper (``scripts/agent-browser-reaper.sh``) sweeps, so nothing here hides
state from it. Writer leases use their own ``.wmlease`` suffix — the same
separation the Playwright lane uses with ``.pwlease`` — and ``sweep()`` (or
``python3 browser_manager.py --sweep``) is the one-pass watchdog verb for
them.

Headless (D6): ``acquire()`` REFUSES to proceed while a headed window could
open (``AGENT_BROWSER_HEADED`` etc.). There is no headed fallback anywhere in
this module.

Usage::

    with WriterLease("location", loc_id, profile_path=owned_profile) as w:
        w.register_owned(browser_pid)   # owned browser child, if spawned
        ...                             # the ONE writer for this location
    # release() runs in finally: owned cleanup + lease/lock removal.

Self-check: ``python3 -I shared-utils/browser/browser_manager_selfcheck.py``
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from typing import Optional

# Version marker for the shared-utils writer lease/lock/teardown engine.
BROWSER_MANAGER_VERSION = "v0.1.0"

# ── Tunables (mirror the 06 browser-manager family) ──────────────────────────
WRITER_LOCK_WAIT_S = 10.0    # bounded acquire queue wait (never infinite)
LEASE_TTL_S = 1800.0         # bounded lease lifetime (mirror AB_SESSION_TTL)
STOP_GRACE_S = 5.0           # graceful stop wait before force
STALE_LOCK_MIN_AGE_S = 2.0   # never reclaim a lock dir younger than this
WM_LEASE_SUFFIX = ".wmlease" # writer leases (own suffix; .lease = shell lane)

# Same lock root as browser_manager.sh / agent-browser-reaper.sh: state is
# ephemeral by design — a lock or lease that survived a reboot is a stale-lock
# bug, and the dead-PID reclaim below handles a crash.
_HEADED_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})
_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


# ── D6 headless guard ────────────────────────────────────────────────────────

def headless_guard(env: Optional[dict] = None) -> None:
    """REFUSE if a headed window could open (D6). Raises ``HeadlessRefused``
    rather than ever risk taking over a screen."""
    env = env if env is not None else os.environ
    for var in ("AGENT_BROWSER_HEADED", "GHL_PLAYWRIGHT_HEADED",
                "PW_HEADED", "GHL_PW_HEADED"):
        val = str(env.get(var, "") or "").strip().lower()
        if val not in _HEADED_OFF_VALUES:
            raise HeadlessRefused(
                "REFUSE (D6 headless guard): %s=%r would open a VISIBLE "
                "browser window. Headless is mandatory. Unset it and run "
                "again — there is no headed fallback." % (var, val)
            )


class HeadlessRefused(RuntimeError):
    """A headed configuration was inherited or requested — refused before any
    state was taken. Never a fallback to headed."""


class WriterBusy(RuntimeError):
    """Another live writer holds this target and the BOUNDED wait expired."""


class NotOwner(RuntimeError):
    """Release/teardown attempted by a process that does not own the lease."""


# ── PID-reuse-safe process identity ──────────────────────────────────────────

def proc_start_time(pid: int) -> str:
    """PID start-time token (``ps -o lstart=``). With the PID this is a
    PID-reuse-safe process identity. Returns "" when unreadable — callers
    treat "" as UNKNOWN (never as alive)."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        return " ".join((out.stdout or "").split())
    except Exception:  # noqa: BLE001 - identity probing must never raise
        return ""


def proc_cmdline(pid: int) -> str:
    try:
        out = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _identity_alive(pid: int, start_time: str) -> bool:
    """True iff ``pid`` is alive AND its start-time still matches."""
    return bool(pid) and bool(start_time) and proc_start_time(pid) == start_time


def proc_identity_matches(pid: int, start_time: str, profile_path: str) -> bool:
    """True iff ``pid`` is alive, its start-time still matches AND its command
    line references the EXACT owned profile path. PID-reuse safe: a recycled
    PID has a different start-time and can never match. A process without the
    exact profile path (personal Chrome, anything else) can never match."""
    if not _identity_alive(pid, start_time):
        return False
    return bool(profile_path) and profile_path in proc_cmdline(pid)


def find_owned_pids(profile_path: str, exclude_pids: tuple = ()) -> list:
    """Every live PID whose command line references the EXACT owned profile
    path. Never returns a process lacking that path (personal Chrome is never
    in this list)."""
    if not profile_path:
        return []
    try:
        out = subprocess.run(["ps", "-axww", "-o", "pid=,command="],
                             capture_output=True, text=True, timeout=10)
        lines = (out.stdout or "").splitlines()
    except Exception:  # noqa: BLE001
        return []
    exclude = {int(p) for p in exclude_pids if p} | {os.getpid()}
    found = []
    for line in lines:
        stripped = line.strip()
        if not stripped or profile_path not in stripped:
            continue
        head = stripped.split(None, 1)[0]
        if not head.isdigit():
            continue
        pid = int(head)
        if pid in exclude:
            continue
        found.append(pid)
    return found


def stop_owned_processes(profile_path: str,
                         expected: Optional[dict] = None,
                         grace_s: float = STOP_GRACE_S,
                         *,
                         exclude_pids: tuple = (),
                         term_fn=None, kill_fn=None, sleep_fn=None,
                         scan_fn=None) -> dict:
    """Graceful stop BEFORE force, scoped to provably owned processes only.

    ``expected`` is the lease's {pid: start_time} identity map. ``exclude_pids``
    names the lease OWNER (and any other process that is not an owned browser
    child) — the owner's argv may carry the profile path, but teardown must
    never signal the owner itself. Every signal is re-verified against (PID,
    start-time, exact profile path) immediately before it is sent — a PID
    recycled between scan and signal is never hit. Processes without the exact
    owned profile path are NEVER signaled (personal Chrome preserved).
    Returns {"terminated": [pids], "killed": [pids]}."""
    term_fn = term_fn or (lambda p: os.kill(p, signal.SIGTERM))
    kill_fn = kill_fn or (lambda p: os.kill(p, signal.SIGKILL))
    sleep_fn = sleep_fn or time.sleep
    exclude = {int(p) for p in exclude_pids if p} | {os.getpid()}
    scan_fn = scan_fn or (lambda: find_owned_pids(profile_path, tuple(exclude)))

    seen: dict = {}
    for pid in scan_fn():
        pid = int(pid)
        if pid in exclude:
            continue
        st = proc_start_time(pid)
        if st:
            seen[pid] = st
    for pid, st in (expected or {}).items():
        pid = int(pid)
        if pid in exclude:
            continue
        if proc_identity_matches(pid, st, profile_path):
            seen[pid] = st

    terminated = []
    for pid, st in list(seen.items()):
        if proc_identity_matches(pid, st, profile_path):
            try:
                term_fn(pid)
                terminated.append(pid)
            except OSError:
                pass

    deadline = time.time() + max(0.0, float(grace_s))
    while time.time() < deadline:
        if not any(proc_identity_matches(p, s, profile_path)
                   for p, s in seen.items()):
            break
        sleep_fn(0.2)

    killed = []
    for pid, st in seen.items():
        # Re-verify ownership immediately before the force signal (PID reuse).
        if proc_identity_matches(pid, st, profile_path):
            try:
                kill_fn(pid)
                killed.append(pid)
            except OSError:
                pass
    return {"terminated": terminated, "killed": killed}


# ── Lock / lease locations (reaper-visible conventions) ──────────────────────

def lockdir(env: Optional[dict] = None) -> str:
    """Mirror browser_manager.sh LOCKDIR so state lands where the host reaper
    looks: ${TMPDIR:-/tmp}/agent-browser."""
    env = env if env is not None else os.environ
    return os.path.join(env.get("TMPDIR", "/tmp"), "agent-browser")


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", name) or "x"


def _check_key(kind: str, target_id: str) -> None:
    if not isinstance(kind, str) or not _KIND_RE.match(kind):
        raise ValueError("REFUSE: writer kind %r is not a plain slug" % (kind,))
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("REFUSE: writer target_id must be a non-empty string")


def writer_lock_path(root: str, kind: str, target_id: str) -> str:
    _check_key(kind, target_id)
    return os.path.join(root, "writers",
                        "%s--%s.lock.d" % (_safe(kind), _safe(target_id)))


def lease_path(root: str, kind: str, target_id: str) -> str:
    _check_key(kind, target_id)
    return os.path.join(root, "leases",
                        "%s--%s%s" % (_safe(kind), _safe(target_id),
                                      WM_LEASE_SUFFIX))


# ── Lease identity file (watchdog/reaper contract) ───────────────────────────

def lease_write(root: str, kind: str, target_id: str, *,
                owner_pid: int, owner_start: str,
                profile_path: str = "",
                owned_pids: Optional[dict] = None,
                ttl_sec: float = LEASE_TTL_S,
                now: Optional[float] = None) -> str:
    """Write the writer lease. ``owned_pids`` is {pid: start_time} for the
    browser children this lease owns (empty until ``register_owned``)."""
    path = lease_path(root, kind, target_id)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    lease = {
        "lane": "shared-utils-writer",
        "kind": kind,
        "target_id": target_id,
        "owner_pid": int(owner_pid),
        "owner_start": owner_start or "",
        "profile_path": profile_path or "",
        "owned_pids": {str(int(p)): str(s)
                       for p, s in (owned_pids or {}).items()},
        "started_epoch": float(now if now is not None else time.time()),
        "ttl_sec": float(ttl_sec),
        "box_id": "%s:%s" % (os.uname().nodename if hasattr(os, "uname")
                             else "box", os.environ.get("HOME", "")),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lease, fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def lease_read(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            lease = json.load(fh)
    except (OSError, ValueError):
        return None
    return lease if isinstance(lease, dict) else None


def lease_healthy(lease: dict, now: Optional[float] = None) -> bool:
    """True iff the owner is the SAME live process (PID alive AND start-time
    matching — PID-reuse safe) AND the bounded lifetime has not passed."""
    now = float(now if now is not None else time.time())
    if now > float(lease.get("started_epoch", 0)) + float(lease.get("ttl_sec", 0)):
        return False
    return _identity_alive(int(lease.get("owner_pid") or 0),
                           lease.get("owner_start", ""))


def reclaim_lease(lease: dict, path: str, *,
                  grace_s: float = STOP_GRACE_S, stop_fn=None) -> dict:
    """Reclaim one dead/expired lease: stop its owned processes (graceful then
    force), scoped to the exact profile path, NEVER the lease owner, then drop
    the lease file."""
    stop_fn = stop_fn or stop_owned_processes
    owned = {int(p): str(s) for p, s in (lease.get("owned_pids") or {}).items()}
    report = stop_fn(lease.get("profile_path", ""),
                     expected=owned or None,
                     grace_s=grace_s,
                     exclude_pids=(lease.get("owner_pid"),))
    try:
        os.unlink(path)
    except OSError:
        pass
    return report


def sweep(root: Optional[str] = None, *,
          now: Optional[float] = None,
          grace_s: float = STOP_GRACE_S,
          stop_fn=None, env: Optional[dict] = None) -> dict:
    """One watchdog pass over writer leases (``*.wmlease``).

    A lease is reclaimed when its owner PID is gone or reused (start-time
    mismatch) or its bounded lifetime has passed. Healthy leases are untouched.
    Processes without the lease's exact profile path are never signaled.
    Returns {"reclaimed": [keys], "healthy": [keys], "detail": {...}}."""
    root = root or lockdir(env)
    lease_dir = os.path.join(root, "leases")
    reclaimed, healthy, detail = [], [], {}
    try:
        names = sorted(os.listdir(lease_dir))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(WM_LEASE_SUFFIX):
            continue
        path = os.path.join(lease_dir, name)
        lease = lease_read(path)
        if lease is None:
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        key = "%s/%s" % (lease.get("kind", "?"), lease.get("target_id", name))
        if lease_healthy(lease, now=now):
            healthy.append(key)
            continue
        detail[key] = reclaim_lease(lease, path, grace_s=grace_s, stop_fn=stop_fn)
        reclaimed.append(key)
    return {"reclaimed": reclaimed, "healthy": healthy, "detail": detail}


# ── The one-writer gate ──────────────────────────────────────────────────────

class WriterLease:
    """ONE writer per mutable browser session or location.

    Atomic-mkdir exclusion (portable — ``flock`` is absent on macOS) under the
    shared ``writers/`` namespace, owner identity PID + start-time, a BOUNDED
    acquire wait (``wait_s``), a BOUNDED lease lifetime (``ttl_sec``), and
    owned cleanup on ``release()``. A crashed owner is reclaimed by
    ``sweep()`` — or by the next ``acquire()`` once the lock dir is older than
    ``STALE_LOCK_MIN_AGE_S`` (never steal a lock mid-creation).

    ``ttl_sec`` is an ABSOLUTE lifetime: ``heartbeat()`` re-verifies ownership
    but never extends it, so a wedged writer can never hold a target forever.
    ponytail: no renew-by-heartbeat — add a renewal policy if real builds
    outlive LEASE_TTL_S; the ceiling is the absolute TTL."""

    def __init__(self, kind: str, target_id: str, *,
                 ttl_sec: float = LEASE_TTL_S,
                 wait_s: float = WRITER_LOCK_WAIT_S,
                 profile_path: str = "",
                 root: Optional[str] = None,
                 env: Optional[dict] = None,
                 sleep_fn=None, now_fn=None):
        _check_key(kind, target_id)
        self.kind = kind
        self.target_id = target_id
        self.ttl_sec = float(ttl_sec)
        self.wait_s = float(wait_s)
        self.profile_path = profile_path or ""
        self._env = env
        self._root = root or lockdir(env)
        self._sleep = sleep_fn or time.sleep
        self._now = now_fn or time.time
        self._pid = os.getpid()
        self._start = proc_start_time(self._pid)
        self._held = False
        self._owned: dict = {}
        self.lock_path = writer_lock_path(self._root, kind, target_id)
        self.lease_file = lease_path(self._root, kind, target_id)

    # -- acquire ---------------------------------------------------------

    def acquire(self) -> "WriterLease":
        if self._held:
            return self
        headless_guard(self._env)  # D6: refuse BEFORE taking any state
        os.makedirs(os.path.join(self._root, "writers"),
                    mode=0o700, exist_ok=True)
        deadline = self._now() + self.wait_s
        while True:
            try:
                os.mkdir(self.lock_path)
            except FileExistsError:
                if self._owner_alive():
                    if self._now() >= deadline:
                        raise WriterBusy(
                            "REFUSE (one writer per %s %r): another live "
                            "writer holds it and the bounded wait (%.0fs) "
                            "expired. One writer — retry later or release "
                            "the held lease." % (self.kind, self.target_id,
                                                 self.wait_s)
                        )
                    self._sleep(0.2)
                    continue
                # Owner dead / PID reused — stale. Reclaim only once the lock
                # dir is old enough to not be mid-creation.
                if self._lock_age_s() < STALE_LOCK_MIN_AGE_S:
                    if self._now() >= deadline:
                        raise WriterBusy(
                            "REFUSE (one writer per %s %r): lock %s is "
                            "changing hands and the bounded wait expired."
                            % (self.kind, self.target_id, self.lock_path)
                        )
                    self._sleep(0.2)
                    continue
                self._reclaim_lock_dir()
                continue
            self._write_owner()
            self._held = True
            lease_write(self._root, self.kind, self.target_id,
                        owner_pid=self._pid, owner_start=self._start,
                        profile_path=self.profile_path,
                        owned_pids=self._owned, ttl_sec=self.ttl_sec,
                        now=self._now())
            return self

    def __enter__(self) -> "WriterLease":
        return self.acquire()

    def __exit__(self, *_exc) -> bool:
        if self._held:
            self.release()
        return False

    # -- ownership -------------------------------------------------------

    @property
    def env(self):  # pragma: no cover - trivial
        return self._env

    def register_owned(self, pid: int) -> dict:
        """Record an owned browser child (PID + start-time) in the lease so
        teardown/sweep can clean it up. PID-reuse safe."""
        if not self._held:
            raise RuntimeError("REFUSE: register_owned() without a held lease")
        pid = int(pid)
        st = proc_start_time(pid)
        if not st:
            raise RuntimeError(
                "REFUSE: pid %s is not a live process to own" % pid)
        self._owned[pid] = st
        lease_write(self._root, self.kind, self.target_id,
                    owner_pid=self._pid, owner_start=self._start,
                    profile_path=self.profile_path,
                    owned_pids=self._owned, ttl_sec=self.ttl_sec,
                    now=self._started())
        return {"pid": pid, "start": st}

    def heartbeat(self) -> None:
        """Re-verify this writer still owns the target. Raises ``NotOwner``
        when the lock was reclaimed under us. Does NOT extend the deadline."""
        if not self._held:
            raise RuntimeError("REFUSE: heartbeat() without a held lease")
        if not self._owner_alive():
            self._held = False
            raise NotOwner(
                "REFUSE: writer lease for %s/%s is no longer ours (lock "
                "reclaimed)." % (self.kind, self.target_id))

    def release(self) -> dict:
        """Owned cleanup + unlock. Owner-guarded: a non-owner can never tear
        down someone else's writer."""
        if not self._held:
            return {"terminated": [], "killed": []}
        self._assert_owner()
        report = {"terminated": [], "killed": []}
        if self.profile_path:
            report = stop_owned_processes(
                self.profile_path, expected=dict(self._owned),
                grace_s=STOP_GRACE_S, exclude_pids=(self._pid,))
        try:
            os.unlink(self.lease_file)
        except OSError:
            pass
        self._reclaim_lock_dir()
        self._held = False
        self._owned = {}
        return report

    # -- internals -------------------------------------------------------

    def _started(self) -> float:
        try:
            with open(os.path.join(self.lock_path, "owner.json"),
                      encoding="utf-8") as fh:
                return float(json.load(fh).get("acquired_epoch") or self._now())
        except (OSError, ValueError):
            return self._now()

    def _write_owner(self) -> None:
        with open(os.path.join(self.lock_path, "owner.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"pid": self._pid, "pid_start": self._start,
                       "kind": self.kind, "target_id": self.target_id,
                       "acquired_epoch": self._now()}, fh)

    def _read_owner(self) -> dict:
        try:
            with open(os.path.join(self.lock_path, "owner.json"),
                      encoding="utf-8") as fh:
                owner = json.load(fh)
        except (OSError, ValueError):
            return {}
        return owner if isinstance(owner, dict) else {}

    def _owner_alive(self) -> bool:
        owner = self._read_owner()
        return _identity_alive(int(owner.get("pid") or 0),
                               owner.get("pid_start", ""))

    def _lock_age_s(self) -> float:
        try:
            return max(0.0, self._now() - os.stat(self.lock_path).st_mtime)
        except OSError:
            return STALE_LOCK_MIN_AGE_S  # gone — treat as old, retry mkdir

    def _reclaim_lock_dir(self) -> None:
        try:
            os.unlink(os.path.join(self.lock_path, "owner.json"))
        except OSError:
            pass
        try:
            os.rmdir(self.lock_path)
        except OSError:
            pass

    def _assert_owner(self) -> None:
        owner = self._read_owner()
        if (int(owner.get("pid") or 0) != self._pid
                or owner.get("pid_start", "") != self._start):
            raise NotOwner(
                "REFUSE: release of %s/%s attempted by non-owner (pid %s)"
                % (self.kind, self.target_id, self._pid))


# ── CLI: one watchdog pass (reaper/cron wiring hook) ─────────────────────────

def _main(argv: list) -> int:
    if "--sweep" in argv:
        print(json.dumps(sweep(), sort_keys=True))
        return 0
    sys.stderr.write(
        "usage: browser_manager.py --sweep   (one writer-lease watchdog pass)\n")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
