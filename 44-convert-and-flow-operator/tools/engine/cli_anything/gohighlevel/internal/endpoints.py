"""Internal endpoint path builders — every internal URL lives here and only here.

Pure functions; no I/O.  Each returns a path string.  The adapter composes
these with BASE_URL to build requests.

Verified paths from ghl_internal_client.py + workflow_builder.py (2026-03-25).
Do NOT add new endpoints without verifying against the live backend and
updating contract.golden.json.
"""
from __future__ import annotations

# The single place this string lives.  Any backend domain change is a one-line edit here.
BASE_URL = "https://backend.leadconnectorhq.com"


# ── Folder / workflow ─────────────────────────────────────────────────────────

def folder(loc: str) -> str:
    """POST body {name, type:"directory"} — creates a workflow folder."""
    return f"/workflow/{loc}"


def workflow_create(loc: str) -> str:
    """POST body {name, parentId} — creates a workflow inside a folder.

    NOTE: Same path as folder(); different body shape distinguishes them.
    Both names are kept so intent is readable and the probe can exercise each.
    """
    return f"/workflow/{loc}"


def workflow_get(loc: str, wf: str) -> str:
    """GET — fetch a single workflow by ID."""
    return f"/workflow/{loc}/{wf}"


def workflow_put(loc: str, wf: str) -> str:
    """PUT body {name, version, workflowData:{templates}} — save/sync steps."""
    return f"/workflow/{loc}/{wf}"


def trigger_create(loc: str) -> str:
    """POST body <trigger skeleton> — create a trigger."""
    return f"/workflow/{loc}/trigger"


def trigger_put(loc: str, tr: str) -> str:
    """PUT body <trigger + targetActionId> — link trigger to first step."""
    return f"/workflow/{loc}/trigger/{tr}"


def tag_create(loc: str) -> str:
    """POST body {tag:"..."} — create a location-level tag."""
    return f"/workflow/{loc}/tags/create"


# ── Agency operations (sub-account + user provisioning) ───────────────────────

def location_create() -> str:
    """POST body <create-location DTO> — create a sub-account (location).

    Internal/agency endpoint.  Body's companyId is the FIRESTORE document id of
    the agency, NOT the human-readable relationNumber.  Verified live: the
    "version": "2021-07-28" request header is REQUIRED (absent -> 401).
    """
    return "/locations/"


def user_create() -> str:
    """POST body <CreateUserDto> — add a user (and set their own login password).

    Internal/agency endpoint.  CreateUserDto required fields:
      companyId (FIRESTORE id), firstName, lastName, email, password, type,
      role, locationIds.  Verified live: the "version": "2021-07-28" request
      header is REQUIRED (absent -> 401).
    """
    return "/users/"
