"""Convert and Flow CLI — pre-write snapshot manager.

HARD RULE (PRD Section 0 / Acceptance Criterion 20):
  Before EVERY workflows update/patch-email/patch-trigger the CLI must:
  1. GET the current workflow from the internal API.
  2. Save a timestamped snapshot to:
       ~/.openclaw/tools/convert-and-flow-cli/data/snapshots/<location>/<workflow-id>/<timestamp>.json
  3. Return the snapshot path so callers can print it.

  No live workflow is ever mutated without a captured rollback artifact on disk.

`restore(client, snapshot_path)` replays a snapshot via the internal PUT to
return the workflow to its prior state.

Accepts either an InternalAdapter (preferred) or a legacy InternalGHLClient
(backward-compat) — both expose .location_id and the GET/PUT paths needed.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

# ── Default data root (overridable via env for tests) ─────────────────────────

def _data_root() -> Path:
    """Base directory for snapshots.

    Overridable: set CAF_DATA_DIR=<path> in env (used by tests to avoid
    writing to the real ~/.openclaw tree).
    """
    override = os.environ.get("CAF_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".openclaw" / "tools" / "convert-and-flow-cli" / "data"


def snapshot_dir(location_id: str, workflow_id: str) -> Path:
    """Return (and create) the snapshot directory for a given location+workflow."""
    d = _data_root() / "snapshots" / location_id / workflow_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp_str() -> str:
    """ISO-8601-ish timestamp safe for filenames."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _client_get(client, workflow_id: str) -> Optional[dict]:
    """GET a workflow using either InternalAdapter or legacy client."""
    from cli_anything.gohighlevel.internal.adapter import InternalAdapter
    if isinstance(client, InternalAdapter):
        result = client.get_workflow(workflow_id)
        if result.ok:
            return result.data
        return None
    # Legacy InternalGHLClient — use endpoints.py as sole path source
    from cli_anything.gohighlevel.internal.endpoints import workflow_get
    loc = client.location_id
    raw = client.request("GET", workflow_get(loc, workflow_id))
    if raw is None or (isinstance(raw, dict) and raw.get("_error")):
        return None
    return raw


def _client_put(client, workflow_id: str, put_body: dict, workflow_name: str = "") -> dict:
    """PUT a workflow using either InternalAdapter or legacy client."""
    from cli_anything.gohighlevel.internal.adapter import InternalAdapter
    if isinstance(client, InternalAdapter):
        result = client.put_workflow(workflow_id, put_body)
        if result.ok:
            return result.data or {}
        return {"_error": True, "code": result.http_code, "message": result.error}
    # Legacy InternalGHLClient — use endpoints.py as sole path source
    from cli_anything.gohighlevel.internal.endpoints import workflow_put
    loc = client.location_id
    result = client.request(
        "PUT", workflow_put(loc, workflow_id), put_body,
        workflow_name=workflow_name,
    )
    return result or {}


# ── Public API ────────────────────────────────────────────────────────────────

def capture(
    client,
    workflow_id: str,
    label: str = "",
) -> Optional[Path]:
    """GET the workflow and write a snapshot to disk.

    Returns the Path of the written snapshot file, or None if the GET failed
    (caller should treat None as a hard error and abort the write).

    Args:
        client:       InternalAdapter or legacy InternalGHLClient.
        workflow_id:  GHL workflow ID.
        label:        Optional suffix for human readability (e.g. "pre-update").
    """
    loc = client.location_id
    raw = _client_get(client, workflow_id)
    if raw is None:
        return None

    ts = _timestamp_str()
    safe_label = "".join(c for c in label if c.isalnum() or c in "-_")
    filename = f"{ts}-{safe_label}.json" if safe_label else f"{ts}.json"

    snap_dir = snapshot_dir(loc, workflow_id)
    snap_path = snap_dir / filename
    snap_path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    return snap_path


def restore(
    client,
    workflow_id: str,
    snapshot_path: Path | str,
) -> dict:
    """Restore a workflow to its snapshot state via the internal PUT.

    Strips server-managed keys (STRIP_KEYS) before the PUT so GHL does not
    reject the payload.  Returns the API response dict.

    Args:
        client:        InternalAdapter or legacy InternalGHLClient.
        workflow_id:   GHL workflow ID.
        snapshot_path: Path to the previously captured snapshot JSON.

    Raises:
        FileNotFoundError: if snapshot_path does not exist.
        ValueError:        if the snapshot JSON is missing 'name' or 'workflowData'.
    """
    from cli_anything.gohighlevel.internal.contract import STRIP_KEYS

    snap = Path(snapshot_path)
    if not snap.exists():
        raise FileNotFoundError(f"Snapshot not found: {snap}")

    data: dict = json.loads(snap.read_text(encoding="utf-8"))

    if "name" not in data:
        raise ValueError("Snapshot is missing required 'name' field.")
    if "workflowData" not in data:
        raise ValueError("Snapshot is missing required 'workflowData' field.")

    # Build a clean PUT body — strip server-managed fields
    put_body: dict = {k: v for k, v in data.items() if k not in STRIP_KEYS}

    return _client_put(client, workflow_id, put_body, workflow_name=data.get("name", ""))


def list_snapshots(location_id: str, workflow_id: str) -> list[Path]:
    """Return all snapshot files for a workflow, newest first."""
    d = _data_root() / "snapshots" / location_id / workflow_id
    if not d.exists():
        return []
    files = sorted(d.glob("*.json"), key=lambda p: p.name, reverse=True)
    return files
