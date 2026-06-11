"""contract.py — STRIP_KEYS, response normalizer, body skeleton builders.

Three responsibilities (adapter-design §7):

a) STRIP_KEYS frozenset (moved verbatim from ghl_internal_client.py) plus
   strip_for_put() helper.

b) normalize_result() maps the legacy tri-state into AdapterResult.

c) Named body builders — the exact wire skeletons lifted from CampaignBuilder
   so a body-shape change is a one-file edit.

KNOWN QUIRK documented here:
  GHL wait unit: "hour" (singular) vs "days"/"minutes" (plural).
  This lives in workflow_builder.wait_step (client-side construction, not a
  backend call) but is noted here as WAIT_UNIT_QUIRK so the probe can assert it.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from cli_anything.gohighlevel.internal.adapter_types import AdapterResult

# ── STRIP_KEYS (verified frozenset from ghl_internal_client.py) ──────────────
# Keys removed from a GET response before a PUT to avoid GHL validation errors.
# DO NOT change this set without verifying against the live backend and
# updating contract.golden.json.
STRIP_KEYS: frozenset[str] = frozenset([
    "_id", "id", "__v", "createdAt", "updatedAt", "companyId", "locationId",
    "companyAge", "creationSource", "originType", "deleted",
    "isTriggerBucketMigrated", "permissionMeta",
])

# ── Wait-unit quirk (documented for probe, authoritative copy stays in builder)
WAIT_UNIT_QUIRK = {
    "minutes": "minutes",
    "hours": "hour",   # GHL uses singular "hour" for hours
    "hour": "hour",
    "days": "days",
}


# ── strip_for_put ─────────────────────────────────────────────────────────────

def strip_for_put(obj: dict) -> dict:
    """Return a shallow copy of obj with all STRIP_KEYS removed."""
    return {k: v for k, v in obj.items() if k not in STRIP_KEYS}


# ── normalize_result ──────────────────────────────────────────────────────────

def normalize_result(raw: Optional[dict]) -> AdapterResult:
    """Map the legacy tri-state from InternalTransport into an AdapterResult.

    Legacy outcomes:
      success dict     -> AdapterResult(ok=True, data=raw)
      None             -> auth-exhausted after retry -> (ok=False, http_code=401)
      {"_error":True}  -> transport error -> (ok=False, error=msg, http_code=code)
    """
    if raw is None:
        return AdapterResult(ok=False, error="AUTH_EXHAUSTED", http_code=401)

    if raw.get("_error"):
        code = raw.get("http_code") or raw.get("code")
        msg = raw.get("message", "unknown error")
        # Surface 429 explicitly
        if code == 429:
            reset = raw.get("rate_limit_reset", "")
            err = f"RATE_LIMIT_429"
            if reset:
                err += f": reset at {reset}"
            return AdapterResult(ok=False, error=err, http_code=429, data=raw)
        return AdapterResult(ok=False, error=msg, http_code=code, data=raw)

    return AdapterResult(ok=True, data=raw)


# ── Body builders (wire skeletons lifted from CampaignBuilder) ─────────────

def tag_trigger_body(loc: str, wf_id: str, tag: str, active: bool = False) -> dict:
    """Create-trigger POST body skeleton.

    active=False by default (draft_only rule — triggers inactive until operator
    explicitly enables them).
    """
    return {
        "status": "draft",
        "workflowId": wf_id,
        "schedule_config": {},
        "conditions": [{
            "operator": "index-of-true",
            "field": "tagsAdded",
            "value": tag,
            "title": "Tag Added",
            "type": "select",
            "id": "tag-added",
        }],
        "type": "contact_tag",
        "masterType": "highlevel",
        "name": tag.replace("-", " ").title(),
        "actions": [{"workflow_id": wf_id, "type": "add_to_workflow"}],
        "active": active,
        "triggersChanged": True,
        "location_id": loc,
    }


def trigger_link_body(base: dict, first_step_id: str) -> dict:
    """PUT trigger body that links trigger to first step."""
    return {
        **base,
        "targetActionId": first_step_id,
        "advanceCanvasMeta": {"position": {"x": 57.5, "y": -73}},
    }


def save_steps_body(name: str, templates: list[dict], version: int = 1) -> dict:
    """First PUT body — saves workflow steps."""
    return {
        "name": name,
        "version": version,
        "workflowData": {"templates": templates},
    }


def sync_body(
    name: str,
    version: int,
    meta: dict,
    steps_with_meta: list[dict],
    trigger_list: list[dict],
) -> dict:
    """Second PUT body — syncs triggers + canvas meta."""
    return {
        "name": name,
        "version": version,
        "meta": meta,
        "workflowData": {"templates": steps_with_meta},
        "triggersChanged": bool(trigger_list),
        "oldTriggers": trigger_list,
        "newTriggers": trigger_list,
    }
