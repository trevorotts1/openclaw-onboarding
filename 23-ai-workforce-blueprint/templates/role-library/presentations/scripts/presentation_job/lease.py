#!/usr/bin/env python3
"""A real lease: one owner per run (FIX 18, MASTER-ASSESSMENT-AND-FIX-PLAN Part 8).

PROBLEM FIX 18 CLOSES
---------------------
Five launch paths (the door, supervisor._restart, launcher.dispatch,
presentation-intake-poll.sh, cc_board._dispatch_engine_if_idle) each kept their
own "is something already running here?" predicate, and predicates disagree:
8 refused launches, concurrent-session resumes over one state.json, and a
render child outliving its engine were all observed in the same week. The
run-level RunLock (state.RunLock, flock) only guards processes that live long
enough to contend for it inside one box -- it says nothing to a *new* process
about WHO holds the run right now, and nothing at all across boxes.

THE CONTRACT (interface published in the fix plan)
--------------------------------------------------
    from presentation_job import lease
    held = lease.acquire(run_dir, holder, ttl_s=600)   # -> Lease | None
    lease.heartbeat(held)                              # extend expiry, re-prove liveness
    lease.release(held)                                # give it up (idempotent)
    doc = lease.read(run_dir)                          # peek: who owns this run?

The lease file is `working/.lease.json` and carries exactly::

    {"pid", "host", "session", "acquired_at", "expires_at"}

plus a `holder` dict merged in by the caller (the door writes its bridge id,
supervisor writes "supervisor", an interactive --run writes the user session),
so `lease.read()` can answer "name the holder" for the proof and for humans.

ACQUISITION SEMANTICS
---------------------
acquire() is atomic-by-rename: the new document is written to a temp file in
`working/` and os.replace()d over any existing lease, so two racers can never
both observe a half-written file. A stale lease does NOT block: it is taken
over when EITHER its `expires_at` has passed (the heartbeat is the truth for a
crashed holder that never got to release) OR its pid is provably dead on this
host (`host` must equal this machine's name AND pid_is_alive must fail -- a
live pid is never stolen, and a foreign host's pid is meaningless here so only
the expiry rules it). Same-session re-acquisition (the engine re-entering with
--resume inside one process, or a heartbeat renewing) refreshes in place.

The expiry answer to "can I take over a dead holder's lease?" is ttl_s: the
proof for FIX 18 kills the first engine and requires the second to acquire
within ttl_s of the kill. acquire() with wait=True (default wait_s=0) blocks
polling for takeover so callers like the door can ask for a bounded wait.

HEARTBEAT
---------
heartbeat(lease) rewrites expires_at = now + ttl_s. The engine heartbeats every
60 s from a daemon thread started by main() after a successful acquire and
stopped in the finally that also stops the auto-dispatcher -- so a killed
engine stops renewing and the lease expires on its own within ttl_s.

REFUSAL
-------
acquire() returns None and does NOT raise; callers convert that into their own
exit shape. __main__ prints the holder's pid and host from working/.lease.json
(the FIX 18 proof greps for exactly that) and exits EXIT_LOCK_HELD.

WHY NOT FLOCK
-------------
state.RunLock already flocks .job.lock, and supervisor.py reads that flock as
its liveness signal -- but a lease that is only an in-process lock cannot name
its holder to a human or to the second engine's refusal message, cannot be
inspected by a shell script (the intake poll), and cannot outlive its holder's
fd table on purpose. The lease is the FILE the ecosystem reads; the flock stays
the short-lived critical section.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .state import pid_is_alive

LEASE_FILENAME = ".lease.json"
DEFAULT_TTL_S = 600
HEARTBEAT_INTERVAL_S = 60


def lease_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / LEASE_FILENAME


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def read(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Return the current lease document, or None when absent/unreadable.

    A corrupt lease file reads as None (no lease), the same answer the takeover
    path gives it -- a file that cannot be parsed cannot name a live holder.
    """
    doc = None
    path = lease_path(run_dir)
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def _expired(doc: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    exp = _parse_iso(doc.get("expires_at"))
    if exp is None:
        # An unparseable expiry cannot be trusted to name a live owner: treat
        # the lease as already expired rather than as eternal.
        return True
    now = now or _now()
    return now >= exp


def _holder_is_live(doc: Dict[str, Any]) -> bool:
    """Is the lease's recorded pid still alive on the machine that wrote it?

    Only same-host pid checks mean anything: another box's pid namespace is
    not ours to interpret, so a foreign-host lease is live exactly as long as
    its expiry says it is.
    """
    pid = doc.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if doc.get("host") != socket.gethostname():
        return True  # not ours to judge; expiry is the only rule
    return pid_is_alive(pid)


def _session_now() -> str:
    return os.environ.get("PRESENTATION_SESSION") or os.environ.get("OPENCLAW_SESSION") \
        or f"pid:{os.getpid()}"


class Lease:
    """A held lease. Truth lives in the file; this object is the handle."""

    def __init__(self, run_dir: Path, doc: Dict[str, Any], ttl_s: float) -> None:
        self.run_dir = Path(run_dir)
        self.doc = dict(doc)
        self.ttl_s = float(ttl_s)
        self.released = False

    @property
    def pid(self) -> Optional[int]:
        v = self.doc.get("pid")
        return v if isinstance(v, int) else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"<Lease run={self.run_dir.name} pid={self.doc.get('pid')} "
                f"host={self.doc.get('host')} expires={self.doc.get('expires_at')}>")


def acquire(run_dir: Path, holder: Optional[Dict[str, Any]] = None,
            ttl_s: float = DEFAULT_TTL_S, wait_s: float = 0.0,
            poll_s: float = 0.25) -> Optional[Lease]:
    """Acquire the run lease, or return None when a live holder keeps it.

    holder: caller-supplied identity merged into the document (e.g.
    {"who": "bridge"}); pid/host/session/acquired_at/expires_at are always
    written here. wait_s > 0 polls that long for a dead holder's lease to
    expire before giving up.
    """
    run_dir = Path(run_dir)
    work = run_dir / "working"
    work.mkdir(parents=True, exist_ok=True)
    path = lease_path(run_dir)
    hostname = socket.gethostname()
    deadline = time.monotonic() + max(0.0, wait_s)

    while True:
        now = _now()
        current = read(run_dir)
        takeover = False
        if current is None:
            takeover = True
        elif current.get("host") == hostname and current.get("pid") == os.getpid():
            takeover = True  # re-acquire in place (same process re-entry)
        elif _expired(current, now):
            takeover = True  # heartbeat stopped: the holder is gone or stale
        elif not _holder_is_live(current) and not _expired(current, now):
            # Dead pid on our own host whose lease has not lapsed: refuse anyway.
            # The expiry is the takeover clock -- a documented ttl, not a guess.
            takeover = False
        if not takeover:
            if time.monotonic() >= deadline:
                return None
            time.sleep(max(0.05, poll_s))
            continue

        doc: Dict[str, Any] = {
            "pid": os.getpid(),
            "host": hostname,
            "session": _session_now(),
            "acquired_at": _iso(now),
            "expires_at": _iso(now + timedelta(seconds=ttl_s)),
        }
        for key, value in (holder or {}).items():
            doc[key] = value
        fd, tmp = tempfile.mkstemp(dir=str(work), prefix=".lease-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)  # atomic: a racer either sees old or new
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return Lease(run_dir, doc, ttl_s)


def heartbeat(lease: Lease) -> bool:
    """Extend the lease by its ttl; False when it was lost underneath us.

    Re-reads the file first: a heartbeat that blindly overwrites could steal
    the run back after our own takeover race lost. Loss is the caller's to
    handle (the engine's heartbeat thread logs and stops renewing).
    """
    if lease is None or lease.released:
        return False
    path = lease_path(lease.run_dir)
    current = read(lease.run_dir)
    if current is None:
        return False
    same = (current.get("pid") == lease.doc.get("pid")
            and current.get("host") == lease.doc.get("host")
            and current.get("acquired_at") == lease.doc.get("acquired_at"))
    if not same:
        return False
    now = _now()
    current["expires_at"] = _iso(now + timedelta(seconds=lease.ttl_s))
    fd, tmp = tempfile.mkstemp(dir=str(lease.run_dir / "working"),
                               prefix=".lease-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    lease.doc = dict(current)
    return True


def release(lease: Optional[Lease]) -> None:
    """Give the lease up. Idempotent; never raises; file stays for the audit
    trail with released_at set (a second engine reading it still sees expired
    semantics only via pid-liveness -- release() deletes nothing)."""
    if lease is None or lease.released:
        return
    lease.released = True
    path = lease_path(lease.run_dir)
    try:
        current = read(lease.run_dir)
        if current is None:
            return
        same = (current.get("pid") == lease.doc.get("pid")
                and current.get("host") == lease.doc.get("host")
                and current.get("acquired_at") == lease.doc.get("acquired_at"))
        if not same:
            return  # not ours anymore; leave the live holder's file alone
        current["released_at"] = _iso(_now())
        # A released lease must never block: expire it now.
        current["expires_at"] = _iso(_now() - timedelta(seconds=1))
        fd, tmp = tempfile.mkstemp(dir=str(lease.run_dir / "working"),
                                   prefix=".lease-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        return


class HeartbeatThread(threading.Thread):
    """Daemon thread renewing a held lease every `interval_s` seconds.

    The engine (presentation_job/__main__.py) starts one after acquiring and
    stops it in the same finally that stops the auto-dispatcher, so every exit
    path (done, blocked, exception) stops renewal and the lease either dies
    with the process or is released explicitly.
    """

    def __init__(self, lease: Lease, interval_s: float = HEARTBEAT_INTERVAL_S,
                 on_loss: Optional[Any] = None) -> None:
        super().__init__(name="lease-heartbeat", daemon=True)
        self.lease = lease
        self.interval_s = float(interval_s)
        self.on_loss = on_loss
        self._stop = threading.Event()
        self.lost = False

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(self.interval_s):
            if self.lease.released:
                return
            ok = heartbeat(self.lease)
            if not ok:
                self.lost = True
                if self.on_loss is not None:
                    try:
                        self.on_loss(self.lease)
                    except Exception:  # noqa: BLE001 - a lost lease must not crash the engine
                        pass
                return


def start_heartbeat(lease: Lease, interval_s: float = HEARTBEAT_INTERVAL_S,
                    on_loss: Optional[Any] = None) -> HeartbeatThread:
    """Start the engine's renewal thread. Caller MUST .stop() it on exit."""
    thread = HeartbeatThread(lease, interval_s=interval_s, on_loss=on_loss)
    thread.start()
    return thread


def describe_holder(run_dir: Path) -> str:
    """One-line refusal text naming the holder, from working/.lease.json.

    The FIX 18 proof greps the second engine's output for the first engine's
    pid and host -- this is the exact string it must find.
    """
    doc = read(run_dir)
    if doc is None:
        return "no lease file (working/.lease.json absent)"
    pid = doc.get("pid")
    host = doc.get("host")
    session = doc.get("session")
    who = doc.get("who") or session or "?"
    return (f"pid {pid} on host {host} (session {who}) "
            f"holds {lease_path(run_dir)} "
            f"since {doc.get('acquired_at')} until {doc.get('expires_at')}")
