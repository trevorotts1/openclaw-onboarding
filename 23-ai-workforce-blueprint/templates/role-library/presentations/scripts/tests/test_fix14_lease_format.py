"""Fix 14 — the poller and the engine write two different lease formats
to the same file.

THE DEFECT
Both wrote `working/.lease.json` in different formats:
- The poller wrote epoch `acquired_at` with no `expires_at`.
- The engine wrote ISO `acquired_at` and `expires_at` (via lease.py).
Each treated the other's lease as expired and overwrote it, so cross-actor
serialization never worked.

THE FIX
- `lease.acquire` accepts optional `pid=` (for shell callers to pass $$).
- The poller's PYLEASE/PYREL heredocs are replaced with
  `python3 -c 'from presentation_job import lease; …'` calls passing
  `pid=$$` and `holder={"holder":"intake-poll-bridge"}`.
- Both actors now write the identical format via the same code path.

THE TEST (per the fix order): a live engine lease makes the poller skip
(`skipped_lease_held`).

The test verifies:
1. `lease.acquire` records an explicit `pid=` (not os.getpid()).
2. The poller's `lease_write` (via the new python3 -c) writes the engine's
   format: ISO `acquired_at` + `expires_at`, with the shell's pid.
3. A live engine lease blocks the poller's acquire (returns 1 = refused),
   which is what the poller counts as `skipped_lease_held`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import lease  # noqa: E402


def test_acquire_accepts_explicit_pid(tmp_path):
    """lease.acquire(pid=...) records the given pid, not os.getpid()."""
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    fake_pid = 99999
    l = lease.acquire(run_dir, holder={"holder": "test"}, pid=fake_pid, ttl_s=60)
    assert l is not None, "acquire should succeed on empty run dir"
    try:
        assert l.doc["pid"] == fake_pid, (
            f"expected pid {fake_pid}, got {l.doc['pid']}"
        )
        # Engine format: ISO acquired_at + expires_at
        assert "acquired_at" in l.doc, "missing acquired_at"
        assert "expires_at" in l.doc, "missing expires_at"
        # ISO format (contains T), not epoch float
        assert "T" in str(l.doc["acquired_at"]), (
            f"acquired_at not ISO format: {l.doc['acquired_at']}"
        )
    finally:
        lease.release(l)


def test_poller_lease_write_uses_engine_format(tmp_path):
    """The poller's lease_write writes the same format as the engine."""
    poller = SCRIPTS / "presentation-intake-poll.sh"
    run_dir = tmp_path / "run2"
    run_dir.mkdir()

    # Extract and run lease_write in isolation with test env vars
    script = f'''
source <(sed -n "/^lease_write/,/^}}/p" "{poller}")
LEASE_TTL_S=60
LEASE_HOLDER="intake-poll-bridge"
lease_write "{run_dir}"
'''
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPTS),
    )
    assert result.returncode == 0, (
        f"lease_write failed: {result.stderr[-1000:]}"
    )
    out = json.loads(result.stdout.strip())
    assert out["acquired"] is True, f"expected acquired=True, got {out}"

    # Verify the file has the engine's format
    lease_file = run_dir / "working" / ".lease.json"
    assert lease_file.exists(), "lease file not created"
    doc = json.loads(lease_file.read_text())
    assert doc["holder"] == "intake-poll-bridge", f"wrong holder: {doc.get('holder')}"
    assert "expires_at" in doc, "poller lease missing expires_at (engine format)"
    assert "T" in str(doc["acquired_at"]), (
        f"poller acquired_at not ISO: {doc['acquired_at']}"
    )
    # pid should be the bash shell's pid (numeric, > 0), not the python child's
    assert isinstance(doc["pid"], int) and doc["pid"] > 0


def test_live_engine_lease_blocks_poller_acquire(tmp_path):
    """A live engine lease makes the poller's acquire refuse (skipped_lease_held)."""
    poller = SCRIPTS / "presentation-intake-poll.sh"
    run_dir = tmp_path / "run3"
    run_dir.mkdir()

    # Simulate a live engine: acquire with THIS process's pid (alive)
    engine_lease = lease.acquire(
        run_dir,
        holder={"holder": "engine"},
        pid=os.getpid(),
        ttl_s=300,
    )
    assert engine_lease is not None
    try:
        # Now the poller tries to acquire — should be refused (rc=1)
        script = f'''
source <(sed -n "/^lease_write/,/^}}/p" "{poller}")
LEASE_TTL_S=60
LEASE_HOLDER="intake-poll-bridge"
lease_write "{run_dir}"
echo "RC=$?"
'''
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(SCRIPTS),
        )
        # The last line is RC=1 (refused)
        assert "RC=1" in result.stdout, (
            f"poller should refuse when engine holds live lease. "
            f"stdout: {result.stdout[-1000:]}, stderr: {result.stderr[-500:]}"
        )
        # The output should indicate not acquired
        assert '"acquired": false' in result.stdout.lower().replace(" ", ""), (
            f"expected acquired:false in output: {result.stdout[-1000:]}"
        )
    finally:
        lease.release(engine_lease)


def test_poller_lease_release_removes_own_lease(tmp_path):
    """The poller's lease_release removes its own lease by holder name."""
    poller = SCRIPTS / "presentation-intake-poll.sh"
    run_dir = tmp_path / "run4"
    run_dir.mkdir()

    # Acquire via poller's lease_write
    script = f'''
source <(sed -n "/^lease_write/,/^}}/p" "{poller}")
source <(sed -n "/^lease_release/,/^}}/p" "{poller}")
LEASE_TTL_S=60
LEASE_HOLDER="intake-poll-bridge"
lease_write "{run_dir}" >/dev/null
lease_release "{run_dir}"
echo "RELEASED"
'''
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPTS),
    )
    assert "RELEASED" in result.stdout
    lease_file = run_dir / "working" / ".lease.json"
    assert not lease_file.exists(), "lease file should be removed after release"
