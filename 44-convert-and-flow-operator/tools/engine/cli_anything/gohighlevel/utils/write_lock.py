"""Convert and Flow CLI — per-box internal-write serialization lock.

PRD Section 8 / Acceptance Criterion 21:
  "A single workflow build fires many sequential internal calls and the whole
  fleet shares one GHL rate bucket. Per box, internal-API WRITES are
  serialized — no two concurrent builds run on the same box (a lock file
  under the data dir; the second build WAITS)."

Usage:
    with WriteLock(location_id):
        # all internal-API writes here

The lock file path is:
    ~/.openclaw/tools/convert-and-flow-cli/data/locks/<location_id>.lock

The lock is an advisory file lock (fcntl.flock on POSIX).  A second process
attempting to acquire the same lock will BLOCK until the first releases it.

On Windows (no fcntl) the implementation falls back to a best-effort rename-
based lock so the module remains importable but serialization relies on the
OS not running two concurrent processes — acceptable given fleet deployment
is Mac/Linux only.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

# ── Per-location threading locks (in-process serialization) ───────────────────
# fcntl.flock works across PROCESSES but NOT across threads in the same process
# (POSIX: flock is per open file description; two threads opening the same file
# both succeed).  We layer a threading.Lock on top so same-process threads are
# also serialized — which is what the tests verify.

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_MUTEX: threading.Lock = threading.Lock()

# Thread-local storage to track which locations this thread currently holds
# the OS-level flock for.  Used to skip re-acquiring flock on re-entrant calls
# from the SAME thread (macOS fcntl.flock is not re-entrant across different
# file descriptors opened by the same process — re-entry deadlocks).
_TLS: threading.local = threading.local()


def _flock_held_by_thread(location_id: str) -> bool:
    """True if the calling thread already holds the OS lock for this location."""
    return location_id in getattr(_TLS, "held_locations", set())


def _flock_mark_held(location_id: str) -> None:
    """Record that the calling thread now holds the OS lock for this location."""
    if not hasattr(_TLS, "held_locations"):
        _TLS.held_locations = set()
    _TLS.held_locations.add(location_id)


def _flock_mark_released(location_id: str) -> None:
    """Record that the calling thread released the OS lock for this location."""
    held = getattr(_TLS, "held_locations", set())
    held.discard(location_id)


def _get_thread_lock(location_id: str) -> threading.RLock:
    """Return (creating if needed) the per-location threading.RLock.

    RLock (re-entrant lock) is used so that the same thread can acquire the
    WriteLock multiple times without deadlocking.  This matters when the CLI
    commands (e.g. ``workflows build``) already hold a WriteLock and then call
    ``CampaignBuilder.build()`` which also acquires a WriteLock for the same
    location.  Different threads still block on the lock as expected (the
    re-entrant property only applies to the SAME thread).
    """
    with _THREAD_LOCKS_MUTEX:
        if location_id not in _THREAD_LOCKS:
            _THREAD_LOCKS[location_id] = threading.RLock()
        return _THREAD_LOCKS[location_id]

# ── Data root helper (mirrors snapshot_manager, kept local to avoid circular) ──

def _locks_dir() -> Path:
    override = os.environ.get("CAF_DATA_DIR", "").strip()
    base = Path(override) if override else (
        Path.home() / ".openclaw" / "tools" / "convert-and-flow-cli" / "data"
    )
    d = base / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── POSIX file lock ────────────────────────────────────────────────────────────

def _flock_lock(lock_file: Path):
    """Open and exclusively flock a lock file.  Returns the open file handle."""
    import fcntl
    fh = open(lock_file, "a")  # "a" = create if absent, never truncate
    fcntl.flock(fh, fcntl.LOCK_EX)  # blocks until acquired
    return fh


def _flock_unlock(fh) -> None:
    import fcntl
    fcntl.flock(fh, fcntl.LOCK_UN)
    fh.close()


# ── Fallback (Windows / environments without fcntl) ───────────────────────────

class _BestEffortLock:
    """Polling spin-lock via exclusive file creation.  Best-effort only."""

    def __init__(self, lock_file: Path, poll_interval: float = 0.25, timeout: float = 300):
        self._path = lock_file
        self._poll = poll_interval
        self._timeout = timeout

    def acquire(self) -> None:
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Timed out waiting for write lock after {self._timeout}s. "
                        f"Lock file: {self._path}"
                    )
                time.sleep(self._poll)

    def release(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


# ── Public context manager ────────────────────────────────────────────────────

@contextmanager
def WriteLock(location_id: str) -> Generator[None, None, None]:
    """Context manager that serializes internal-API writes per location.

    Usage:
        with WriteLock("LOCATION_ID"):
            internal_client.request(...)

    The lock is per location_id so writes to different locations can proceed
    in parallel — only concurrent writes to the SAME location are serialized.

    Two-layer locking strategy:
    1. threading.Lock — serializes threads within the same process (fcntl.flock
       is per-open-file-description, so POSIX guarantees same-process threads
       ALL acquire it without blocking each other).
    2. fcntl.flock — serializes separate processes on the same host.

    Both layers are required for correct behavior in the test suite
    (threads) and in production (multiple CLI processes / subprocesses).
    """
    # Layer 1: in-process thread serialization (RLock = re-entrant so the same
    # thread can call WriteLock() from nested scopes without deadlocking).
    thread_lock = _get_thread_lock(location_id)
    with thread_lock:
        # Layer 2: cross-process OS file lock.
        # ONLY acquired on the outermost entry for this thread/location pair.
        # Reason: macOS fcntl.flock is NOT re-entrant across different file
        # descriptors opened by the same process — opening the lock file a
        # second time and calling LOCK_EX from the same PID deadlocks on BSD
        # (unlike Linux which upgrades/re-grants for the same PID).
        already_held = _flock_held_by_thread(location_id)
        lock_file = _locks_dir() / f"{location_id}.lock"

        if sys.platform == "win32":
            if already_held:
                yield
            else:
                lock = _BestEffortLock(lock_file)
                lock.acquire()
                _flock_mark_held(location_id)
                try:
                    yield
                finally:
                    lock.release()
                    _flock_mark_released(location_id)
        else:
            if already_held:
                # Re-entrant call from same thread — RLock already serializes;
                # skip the flock to avoid BSD re-entry deadlock.
                yield
            else:
                import fcntl  # noqa: F401 — confirm available
                fh = _flock_lock(lock_file)
                _flock_mark_held(location_id)
                try:
                    yield
                finally:
                    _flock_unlock(fh)
                    _flock_mark_released(location_id)
