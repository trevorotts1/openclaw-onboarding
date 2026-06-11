"""adapter.py — InternalAdapter: the ONE isolation point.

Every workflow write goes through InternalAdapter.  It composes:
  transport   -> token + raw HTTP
  endpoints   -> URL path builders
  contract    -> STRIP_KEYS, body normalizers, result normalization
  guards      -> step_backoff
  degrade     -> write-gate check

Only this module knows the endpoint names; callers import only from
internal/__init__.py.  No endpoint path string appears outside this file
(plus endpoints.py where they are defined).

adapter-design §4.
"""
from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from cli_anything.gohighlevel.internal.adapter_types import AdapterResult, AdapterError
from cli_anything.gohighlevel.internal.transport import InternalTransport
from cli_anything.gohighlevel.internal.endpoints import (
    BASE_URL,
    folder,
    workflow_create,
    workflow_get,
    workflow_put,
    trigger_create,
    trigger_put,
    tag_create,
)
from cli_anything.gohighlevel.internal.contract import (
    normalize_result,
    strip_for_put,
    tag_trigger_body,
    trigger_link_body,
    save_steps_body,
    sync_body,
)
from cli_anything.gohighlevel.internal.guards import step_backoff
from cli_anything.gohighlevel.internal import degrade

# Max workers for parallel builds (lowered from source's 10 to reduce burst pressure).
# Configurable via CAF_INTERNAL_MAX_WORKERS.
_DEFAULT_MAX_WORKERS = 3


def _get_max_workers() -> int:
    raw = os.environ.get("CAF_INTERNAL_MAX_WORKERS", "").strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return _DEFAULT_MAX_WORKERS


class InternalAdapter:
    """The one object every workflow write goes through.

    Composes transport + endpoints + contract + guards + degrade.
    The CLI factory (get_adapter) hands this back; CampaignBuilder
    uses it instead of InternalGHLClient directly.
    """

    def __init__(
        self,
        location_id: str,
        *,
        transport: Optional[InternalTransport] = None,
    ) -> None:
        self.location_id = location_id
        self.transport = transport or InternalTransport()
        self._step_index = 0  # resets per build; increments per write call

    # ── Write-step counter ────────────────────────────────────────────────────

    def reset_step_index(self) -> None:
        """Reset the step index at the start of each build."""
        self._step_index = 0

    # ── Typed endpoint methods (one per endpoint) ─────────────────────────────

    def create_folder(self, name: str) -> AdapterResult:
        """POST {name, type:'directory'} — create a workflow folder."""
        path = folder(self.location_id)
        body = {"name": name, "type": "directory"}
        return self._call("POST", path, body, is_write=True)

    def create_workflow(self, name: str, parent_id: str) -> AdapterResult:
        """POST {name, parentId} — create a workflow inside a folder."""
        path = workflow_create(self.location_id)
        body = {"name": name, "parentId": parent_id}
        return self._call("POST", path, body, is_write=True)

    def get_workflow(self, wf_id: str) -> AdapterResult:
        """GET a single workflow by ID (read-only — never blocked by write gate)."""
        path = workflow_get(self.location_id, wf_id)
        return self._call("GET", path, None, is_write=False)

    def put_workflow(self, wf_id: str, body: dict) -> AdapterResult:
        """PUT {name, version, workflowData:{templates}} — save/sync steps."""
        path = workflow_put(self.location_id, wf_id)
        return self._call("PUT", path, body, is_write=True)

    def create_trigger(self, body: dict) -> AdapterResult:
        """POST trigger skeleton — create a trigger."""
        path = trigger_create(self.location_id)
        return self._call("POST", path, body, is_write=True)

    def put_trigger(self, tr_id: str, body: dict) -> AdapterResult:
        """PUT trigger + targetActionId — link trigger to first step."""
        path = trigger_put(self.location_id, tr_id)
        return self._call("PUT", path, body, is_write=True)

    def create_tag(self, tag: str) -> AdapterResult:
        """POST {tag:"..."} — create a location-level tag."""
        path = tag_create(self.location_id)
        body = {"tag": tag}
        return self._call("POST", path, body, is_write=True)

    # ── Single choke point ────────────────────────────────────────────────────

    def _call(
        self,
        method: str,
        path: str,
        body: Optional[dict],
        *,
        is_write: bool,
    ) -> AdapterResult:
        """All endpoint methods delegate here.

        Steps (adapter-design §4):
          1. WRITE GATE: if write disabled -> AdapterResult(ok=False) cleanly.
          2. STEP BACKOFF: sleep between sequential writes.
          3. Safety gate (location whitelist + approval token).
          4. Transport call -> raw result.
          5. normalize_result() -> AdapterResult.
        """
        # Step 1 — write gate
        if is_write and degrade.is_write_disabled():
            record = degrade.read_disable_record() or {}
            reason = record.get("reason", "contract probe failed")
            return AdapterResult(
                ok=False,
                error=(
                    f"WRITE_DISABLED: {reason}. "
                    "Workflow writes are degraded read-only fleet-wide until the "
                    "adapter is refreshed. See contract probe result for details."
                ),
                http_code=None,
            )

        # Step 2 — inter-step backoff (before transport call, skip on first write)
        if is_write:
            step_backoff(self._step_index)
            self._step_index += 1

        # Step 3 — safety gate (whitelist + approval + dry-run)
        if is_write and method.upper() != "GET":
            from cli_anything.gohighlevel.utils.safety_gate import check_write, SafetyRefused
            url = f"{BASE_URL}{path}"
            try:
                check_write(method, url, body, location_id=self.location_id)
            except SafetyRefused as exc:
                return AdapterResult(ok=False, error=str(exc), http_code=None)

        # Step 4 — transport
        raw = self.transport.request(method, path, body)

        # Step 5 — normalize
        return normalize_result(raw)


# ── Factory ───────────────────────────────────────────────────────────────────

def get_adapter(ctx) -> "InternalAdapter":
    """CLI factory — replaces _get_internal_client(ctx).

    Resolves the location id the same way the CLI does (_loc(ctx))
    so no location resolution behavior changes.
    """
    from cli_anything.gohighlevel.gohighlevel_cli import _loc
    return InternalAdapter(location_id=_loc(ctx))
