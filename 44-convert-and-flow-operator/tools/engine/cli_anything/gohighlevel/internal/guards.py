"""guards.py — serialization lock, snapshot hook, step backoff, data_dir.

Three components (adapter-design §9, §10, §11):

1. data_dir() — single resolver for CAF_DATA_DIR env with ~/.openclaw fallback.
   Never hardcode the path; always call this function.

2. write_lock() — context manager wrapping WriteLock for internal-adapter callers.
   (Re-exports the per-location WriteLock from write_lock.py so the adapter
   package does not duplicate serialization logic.)

3. snapshot_workflow() — pre-mutate snapshot hook for the adapter layer.
   Wraps snapshot_manager.capture() and returns the Path.

4. step_backoff() — inter-step sleep inserted between sequential WRITE calls
   inside a single build.  CAF_INTERNAL_STEP_BACKOFF_MS controls the interval
   (default: 300 ms).  The first write of a build (step_index=0) skips the sleep.

Note: the write_lock used by the CLI commands in gohighlevel_cli.py still
imports WriteLock from utils/write_lock.py directly.  This module re-exports
the same underlying context manager so adapter code uses a single import path.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cli_anything.gohighlevel.internal.adapter import InternalAdapter

# Default inter-step backoff in milliseconds (tunable via env)
_DEFAULT_STEP_BACKOFF_MS = 300


# ── data_dir ──────────────────────────────────────────────────────────────────

def data_dir() -> Path:
    """Return the root data directory for convert-and-flow-cli.

    Resolution order (adapter-design §1):
      1. CAF_DATA_DIR env var (set by platform installer)
      2. ~/.openclaw/tools/convert-and-flow-cli/data  (Mac fallback)
      VPS path root /data/.openclaw/... is handled by setting CAF_DATA_DIR
      in the platform overlay environment.

    This is the ONLY place the data path is computed — never hardcode it elsewhere.
    """
    override = os.environ.get("CAF_DATA_DIR", "").strip()
    if override:
        base = Path(override)
    else:
        base = Path.home() / ".openclaw" / "tools" / "convert-and-flow-cli" / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ── write_lock ────────────────────────────────────────────────────────────────

@contextmanager
def write_lock(location_id: str) -> Generator[None, None, None]:
    """Re-export of WriteLock for adapter-layer callers.

    Acquires the per-location advisory file lock.  The second build on the
    same box for the same location will wait (bounded by the lock timeout).
    Reads are not serialized.

    Usage:
        with write_lock(adapter.location_id):
            adapter.put_workflow(...)
    """
    from cli_anything.gohighlevel.utils.write_lock import WriteLock
    with WriteLock(location_id):
        yield


# ── snapshot_workflow ─────────────────────────────────────────────────────────

def snapshot_workflow(adapter: "InternalAdapter", wf_id: str, label: str = "") -> Optional[Path]:
    """GET the current workflow and save a timestamped snapshot.

    Returns the Path of the written file, or None if the GET failed.
    Callers MUST treat None as a hard error and abort the write — there is
    no rollback artifact without a successful snapshot.

    The snapshot is written to:
      data_dir()/snapshots/<location_id>/<wf_id>/<utc-timestamp>[-label].json
    as the raw (un-stripped) GET response, preserving a faithful pre-image.
    strip_for_put() is applied at restore time.
    """
    result = adapter.get_workflow(wf_id)
    if not result.ok or result.data is None:
        return None

    raw = result.data
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_label = "".join(c for c in label if c.isalnum() or c in "-_")
    filename = f"{ts}-{safe_label}.json" if safe_label else f"{ts}.json"

    snap_dir = data_dir() / "snapshots" / adapter.location_id / wf_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / filename

    import json
    snap_path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    return snap_path


# ── step_backoff ──────────────────────────────────────────────────────────────

def step_backoff(step_index: int, base_ms: Optional[int] = None) -> None:
    """Sleep for the configured inter-step interval.

    Called by InternalAdapter._call() before each WRITE after the first.
    step_index=0 is skipped (the very first write of a build has no prior step).

    The interval is read at call time from CAF_INTERNAL_STEP_BACKOFF_MS so
    tests can set it to 0 without patching module state.

    Args:
        step_index: 0-based index of the current write step in this build.
        base_ms:    Override (for tests or explicit callers); if None reads env.
    """
    if step_index == 0:
        return  # first write in a build — no preceding step to pace against

    if base_ms is None:
        raw = os.environ.get("CAF_INTERNAL_STEP_BACKOFF_MS", "").strip()
        try:
            base_ms = int(raw)
        except (ValueError, TypeError):
            base_ms = _DEFAULT_STEP_BACKOFF_MS

    if base_ms > 0:
        time.sleep(base_ms / 1000.0)
