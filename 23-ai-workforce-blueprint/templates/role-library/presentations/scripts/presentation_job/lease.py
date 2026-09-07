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

F19 (Fable review, H6) made the "provably dead on this host" half of that rule
REAL. The paragraph above documented it from the first commit, but the code
refused it anyway ("Dead pid on our own host whose lease has not lapsed: refuse
anyway"), so a crashed engine parked its own run for the whole ttl_s while the
one machine that could see the corpse stood there holding the death
certificate -- and the intake poller counted every refused dispatch as a
launch, so the operator's summary line read "launched" over a run that was not
running. "Provably dead" means exactly ProcessLookupError from
os.kill(pid, 0) (see _pid_provably_dead): a PermissionError says the process
EXISTS behind a privilege boundary, an unreadable pid says nothing at all, and
a foreign host's pid is not ours to interpret -- all three keep ttl_s as the
only takeover clock. Every same-host seizure appends one
`lease.takeover_dead_local_pid` row to working/logs/lease-events.jsonl so the
takeover is auditable after the fact.

ttl_s therefore remains the takeover clock for everything the pid check cannot
prove: the proof for FIX 18 kills the first engine and requires the second to
acquire within ttl_s of the kill (post-F19 it acquires at once when both
engines are on this box). acquire() with wait_s > 0 (default 0) blocks polling
for takeover so callers like the door can ask for a bounded wait.

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

#: F19: lease lifecycle events (JSON Lines), run-scoped like every other
#: working/logs ledger. Today it carries only the dead-local-pid takeover --
#: the one lease decision that overrides another actor's unexpired claim, and
#: therefore the one an operator must be able to reconstruct afterwards.
LEASE_EVENTS_RELATIVE = ("working", "logs", "lease-events.jsonl")


def lease_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / LEASE_FILENAME


def events_path(run_dir: Path) -> Path:
    """Where lease lifecycle events are appended for this run."""
    return Path(run_dir).joinpath(*LEASE_EVENTS_RELATIVE)


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


def _pid_provably_dead(pid: Any) -> bool:
    """True ONLY when os.kill(pid, 0) raises ProcessLookupError.

    F19 seizes another actor's unexpired lease, so it needs PROOF OF DEATH --
    not the absence of proof of life. pid_is_alive() answers the wider
    question (PermissionError -> alive, every other error -> dead), which is
    the right default for a liveness check and the wrong one for a takeover: a
    non-integer pid, a pid whose lookup errors in some other way, and an EPERM
    answer must all leave ttl_s in charge. Only ProcessLookupError says the
    kernel has no such process.

    ``isinstance(True, int)`` is True in Python, so booleans are rejected
    explicitly rather than sliding through as pid 1 / pid 0.
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        # PermissionError (the process exists, someone else owns it) and any
        # other errno are non-answers, never a corpse.
        return False
    return False


def _log_event(run_dir: Path, event: str, **fields: Any) -> None:
    """Append one JSON line to the run's lease event log.

    Logging must never break the lease call path: a run dir we cannot write to
    still gets its lease decision, it just goes unrecorded.
    """
    record: Dict[str, Any] = {"event": event, "at": _iso(_now())}
    record.update(fields)
    try:
        path = events_path(run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


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
        dead_local: Optional[Dict[str, Any]] = None  # the corpse we stepped over
        if current is None:
            takeover = True
        elif current.get("host") == hostname and current.get("pid") == os.getpid():
            takeover = True  # re-acquire in place (same process re-entry)
        elif _expired(current, now):
            takeover = True  # heartbeat stopped: the holder is gone or stale
        elif current.get("host") == hostname and _pid_provably_dead(current.get("pid")):
            # F19: the holder crashed on THIS box and the kernel says its pid is
            # free. Waiting out ttl_s here parks the run behind a process that
            # cannot come back, so take over now -- and log the seizure, because
            # this is the one path that overrides an unexpired claim.
            takeover = True
            dead_local = current
        elif not _holder_is_live(current):
            # Same host, but death is not PROVEN: an unreadable pid, or a
            # lookup that errored some other way. (A foreign host never reaches
            # here -- _holder_is_live calls it live by definition, and a live
            # local pid returns True.) The expiry stays the takeover clock --
            # a documented ttl, not a guess.
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
        if dead_local is not None:
            _log_event(run_dir, "lease.takeover_dead_local_pid",
                       pid=doc["pid"], host=hostname,
                       session=doc["session"],
                       previous_pid=dead_local.get("pid"),
                       previous_host=dead_local.get("host"),
                       previous_session=dead_local.get("session"),
                       previous_acquired_at=dead_local.get("acquired_at"),
                       previous_expires_at=dead_local.get("expires_at"))
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
