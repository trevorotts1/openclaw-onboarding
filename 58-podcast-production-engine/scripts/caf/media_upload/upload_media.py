#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: MEDIA UPLOAD LAYER (PRD Step 14)
# -----------------------------------------------------------------------------
# Tier 3 direct REST multipart upload of the episode MP3, cover JPEG, and (in
# Interview mode) the book-teaser PDF into the client's Convert and Flow media
# library, followed by mandatory HEAD-verification of every returned public URL.
#
# DATA-PLANE DOCTRINE (ghl-design.md Section 1 and Section 4):
#   Media upload is the ONE operation where Tier 3 is not a fallback but the
#   ONLY path. Tier 0 caf does no binary multipart. The two Model Context
#   Protocol tiers are structurally forbidden in this pipeline (sub-agents get
#   no MCP injection). This module therefore speaks raw HTTPS to
#   services.leadconnectorhq.com and nothing else.
#
# FOLDERS ARE LOOKUP-ONLY AT RUNTIME (medias.md Section 4 folder caveat):
#   Folder creation via the REST API returns 404. The engine never creates a
#   folder mid-episode. It reuses the podcast / podcast images / podcast
#   episodes folders (case-insensitive, trimmed) when present, degrades to the
#   parent podcast folder or the media root when a child folder is absent, and
#   never fails an episode over folder creation. Folder provisioning is a
#   one-time onboarding task, not a runtime dependency.
#
# HARD RULES honored here:
#   - Never print or echo a secret value. Reports carry SET / NOT SET, the alias
#     that resolved, the store, the pit- prefix check, and length ONLY.
#   - Named client's OWN Location PIT and OWN Location ID only. An agency PIT
#     returns 401 for media operations and is never substituted.
#   - On HTTP 429: full stop. Never blind-retry, never tier-hop (all tiers share
#     one per-location bucket). Surface RateLimited so the caller hold-queues.
#   - The engine STOPS after media storage in its own lane; it never messages a
#     customer. Convert and Flow owns all messaging.
#
# EXIT CODES (CLI): 0 ok / 1 generic error / 2 credential missing /
#   3 usage / 4 public-URL reachability failure / 5 rate-limit stop.
#
# USAGE:
#   python3 upload_media.py --self-test
#   python3 upload_media.py store --job job.json [--state ghl-state.json]
#   python3 upload_media.py verify --url <url> --family image/
# =============================================================================
"""Tier 3 media upload and public-URL verification for the Podcast Engine."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover - requests is a fleet-standard dependency
    requests = None  # type: ignore

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BASE_HOST = "https://services.leadconnectorhq.com"
MEDIA_UPLOAD_PATH = "/medias/upload-file"
MEDIA_LIST_PATH = "/medias/files"
API_VERSION = "2021-07-28"

# Parent first, then children. Matched case-insensitively and trimmed so a
# manually created "Podcast" folder is reused, never duplicated.
PARENT_FOLDER = "podcast"
IMAGES_FOLDER = "podcast images"
EPISODES_FOLDER = "podcast episodes"
FOLDER_NAMES = (PARENT_FOLDER, IMAGES_FOLDER, EPISODES_FOLDER)

# The Location Private Integration Token (prefix pit-). One value, many names.
# Canonical first; the CONVERTFLOW family belongs in the SHARED resolver used by
# Skills 29/36/44 (ghl-design.md Section 2.2). Listed here so this module can
# resolve at runtime without importing a sibling slice, and kept in the same
# order so behavior matches the shared resolver once it lands.
PIT_ALIASES: Tuple[str, ...] = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
    "CONVERTFLOW_API_KEY",
    "CONVERTANDFLOW_API_KEY",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERTFLOW_PIT",
    "CONVERTANDFLOW_PIT",
)

LOCATION_ALIASES: Tuple[str, ...] = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "LOCATION_ID",
    "CONVERTANDFLOW_LOCATION_ID",
    "CONVERTFLOW_LOCATION_ID",
)

REDACTION = "***REDACTED***"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class MediaError(Exception):
    """Base class for every media-layer failure."""


class CredentialError(MediaError):
    """PIT or Location ID missing, malformed, or a tenant mismatch."""


class RateLimited(MediaError):
    """HTTP 429 from the shared per-location bucket. Full stop, never retry."""

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UploadFailed(MediaError):
    """The upload returned no fileId or no url after one retry."""


class ReachabilityError(MediaError):
    """The returned public URL failed HEAD/GET verification."""


# --------------------------------------------------------------------------- #
# Secrecy
# --------------------------------------------------------------------------- #

def redact(text: str, *secrets: str) -> str:
    """Scrub any secret substring from a string before it is emitted anywhere."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, REDACTION)
    return out


@dataclass
class Credential:
    """A resolved credential. The value is held only in memory and never logged."""

    present: bool
    value: str = ""          # internal only; never emitted
    alias: str = ""
    store: str = "env"
    prefix_ok: bool = False
    length: int = 0

    def report(self) -> Dict[str, Any]:
        """A safe, value-free description for logs and delivery reports."""
        return {
            "status": "SET" if self.present else "NOT SET",
            "alias": self.alias or None,
            "store": self.store if self.present else None,
            "prefix_ok": self.prefix_ok,
            "length": self.length,
        }


# --------------------------------------------------------------------------- #
# Credential resolution (env / live process environment for a runtime module)
# --------------------------------------------------------------------------- #

def resolve_pit(env: Optional[Dict[str, str]] = None) -> Credential:
    """Resolve the Location PIT from the process environment, alias by alias.

    This module runs inside the podcast agent's own turn, so the live process
    environment IS the authoritative store. The full ENV-CHECK-BEFORE-FAIL sweep
    across files, openclaw.json, and auth-profiles.json is owned by
    ghl_credential_gate.py at Step 0; the gate having passed is the precondition
    for calling this module.
    """
    env = os.environ if env is None else env
    for alias in PIT_ALIASES:
        value = env.get(alias)
        if value:
            value = value.strip()
            return Credential(
                present=True,
                value=value,
                alias=alias,
                store="live-process-env",
                prefix_ok=value.startswith("pit-"),
                length=len(value),
            )
    return Credential(present=False)


def resolve_location_id(
    env: Optional[Dict[str, str]] = None,
    payload_location_id: Optional[str] = None,
) -> str:
    """Resolve the Location ID and enforce tenant equality with the payload.

    A mismatch between the environment Location ID and a webhook-carried
    location_id is a hard tenant abort (cross-client contamination guard).
    """
    env = os.environ if env is None else env
    resolved = ""
    for alias in LOCATION_ALIASES:
        value = env.get(alias)
        if value:
            resolved = value.strip()
            break
    if payload_location_id:
        payload_location_id = payload_location_id.strip()
        if resolved and resolved != payload_location_id:
            raise CredentialError(
                "Location ID mismatch: environment value does not equal the "
                "webhook payload location_id. Tenant isolation abort."
            )
        if not resolved:
            resolved = payload_location_id
    if not resolved:
        raise CredentialError("Location ID could not be resolved from any alias.")
    return resolved


# --------------------------------------------------------------------------- #
# HTTP transport (single seam; tests patch this)
# --------------------------------------------------------------------------- #

def _parse_retry_after(response: Any) -> Optional[float]:
    header = ""
    try:
        header = response.headers.get("Retry-After", "") or ""
    except Exception:  # pragma: no cover - defensive
        return None
    header = header.strip()
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def http_request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    timeout: float = 60.0,
    allow_redirects: bool = True,
    bucket: bool = True,
) -> Any:
    """One HTTP call. Raises RateLimited on 429 for shared-bucket (GHL) calls.

    `bucket=True` marks calls that drain the per-location Convert and Flow rate
    bucket. Reachability HEADs against the CDN pass `bucket=False` because they
    do not touch that bucket.
    """
    if requests is None:  # pragma: no cover
        raise MediaError("The 'requests' library is required but not installed.")
    response = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        data=data,
        files=files,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )
    if bucket and getattr(response, "status_code", None) == 429:
        raise RateLimited(
            "Convert and Flow rate limit (429). Full stop; hold-queue and "
            "resume after the window.",
            retry_after=_parse_retry_after(response),
        )
    return response


Transport = Callable[..., Any]


# --------------------------------------------------------------------------- #
# Filenames (ghl-design.md Section 4.2)
# --------------------------------------------------------------------------- #

def _collapse(value: str, allowed_extra: str = "") -> str:
    """Collapse runs of disallowed characters into a single separator."""
    pattern = "[^A-Za-z0-9" + re.escape(allowed_extra) + "]+"
    return re.sub(pattern, "_" if not allowed_extra else " ", value).strip(" _")


def sanitize_strict(client_name: str, episode_title: str, ext: str) -> str:
    """Cover-image rule: letters, numbers, underscores, dashes only; no spaces.

    Produces client_name_episode_title.ext with a single extension period.
    """
    client = re.sub(r"[^A-Za-z0-9]+", "_", client_name).strip("_")
    title = re.sub(r"[^A-Za-z0-9]+", "_", episode_title).strip("_")
    stem = "_".join(part for part in (client, title) if part) or "podcast_episode"
    stem = re.sub(r"_+", "_", stem)
    return f"{stem}.{ext.lstrip('.')}"


def sanitize_loose(client_name: str, episode_title: str, ext: str) -> str:
    """MP3 / PDF rule: letters, numbers, spaces, underscores, dashes.

    Produces "Client Name - Episode Title.ext" (client first, then title).
    """
    client = re.sub(r"[^A-Za-z0-9 _-]+", " ", client_name)
    client = re.sub(r"\s+", " ", client).strip()
    title = re.sub(r"[^A-Za-z0-9 _-]+", " ", episode_title)
    title = re.sub(r"\s+", " ", title).strip()
    if client and title:
        stem = f"{client} - {title}"
    else:
        stem = client or title or "Podcast Episode"
    return f"{stem}.{ext.lstrip('.')}"


# --------------------------------------------------------------------------- #
# Folder lookup and ensure (LOOKUP-ONLY; never create at runtime)
# --------------------------------------------------------------------------- #

def _extract_folders(payload: Any) -> List[Dict[str, Any]]:
    """Pull a list of folder records out of a medias listing response body."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("files")
    if items is None:
        items = payload.get("folders")
    if items is None:
        items = payload.get("medias")
    if not isinstance(items, list):
        return []
    folders = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type", "")).lower()
        # Some accounts omit an explicit type on folder rows; keep any row that
        # is not clearly a file so name matching can still find a folder.
        if kind and kind != "folder":
            continue
        folder_id = item.get("id") or item.get("_id") or item.get("altId")
        name = item.get("name", "")
        if folder_id and name:
            folders.append(
                {
                    "id": str(folder_id),
                    "name": str(name),
                    "createdAt": item.get("createdAt", ""),
                }
            )
    return folders


def list_folders(
    cred: Credential,
    location_id: str,
    *,
    limit: int = 100,
    transport: Transport = http_request,
) -> List[Dict[str, Any]]:
    """List media-library folders. Never raises for a listing failure.

    Returns [] on any non-200 or parse error so callers degrade to the parent
    folder or the media root rather than failing an episode.
    """
    headers = {
        "Authorization": f"Bearer {cred.value}",
        "Version": API_VERSION,
    }
    params = {
        "locationId": location_id,
        "altId": location_id,
        "altType": "location",
        "type": "folder",
        "sortBy": "createdAt",
        "sortOrder": "asc",
        "limit": limit,
    }
    try:
        response = transport(
            "GET",
            BASE_HOST + MEDIA_LIST_PATH,
            headers=headers,
            params=params,
            bucket=True,
        )
    except RateLimited:
        raise
    except Exception:
        return []
    if getattr(response, "status_code", None) != 200:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    return _extract_folders(payload)


def _match_folder(
    folders: List[Dict[str, Any]], target: str
) -> Tuple[Optional[str], List[str]]:
    """Case-insensitive, trimmed match. On duplicates, pick the oldest and warn."""
    warnings: List[str] = []
    matches = [f for f in folders if f["name"].strip().lower() == target.lower()]
    if not matches:
        return None, warnings
    if len(matches) > 1:
        matches.sort(key=lambda f: str(f.get("createdAt", "")))
        warnings.append(
            f"Duplicate folders named '{target}' found; reusing the oldest "
            f"(id {matches[0]['id']}). Nothing created."
        )
    return matches[0]["id"], warnings


def ensure_folders(
    cred: Credential,
    location_id: str,
    *,
    state: Optional[Dict[str, Any]] = None,
    transport: Transport = http_request,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Return {folder_name: id_or_None} for the three podcast folders.

    Runtime is LOOKUP-ONLY (folder create is 404-broken). Missing folders stay
    None with a warning naming them for one-time onboarding creation.
    """
    warnings: List[str] = []
    cached = (state or {}).get("folders") if state else None
    if (
        cached
        and not force_refresh
        and all(cached.get(name) for name in FOLDER_NAMES)
    ):
        result = {name: cached[name] for name in FOLDER_NAMES}
        result["_warnings"] = warnings
        result["_source"] = "state-cache"
        return result

    folders = list_folders(cred, location_id, transport=transport)
    result: Dict[str, Any] = {}
    for name in FOLDER_NAMES:
        folder_id, folder_warnings = _match_folder(folders, name)
        warnings.extend(folder_warnings)
        result[name] = folder_id
        if folder_id is None:
            warnings.append(
                f"Media folder '{name}' not found. Create it once in the Convert "
                f"and Flow UI (folder create is unavailable via REST). Uploads "
                f"will fall back to the parent folder or the media root."
            )
    result["_warnings"] = warnings
    result["_source"] = "live-listing"
    return result


# --------------------------------------------------------------------------- #
# Upload (POST /medias/upload-file, multipart)
# --------------------------------------------------------------------------- #

def _guess_content_type(path: str, default: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or default


def upload_file(
    path: str,
    display_name: str,
    parent_id: Optional[str],
    cred: Credential,
    location_id: str,
    *,
    content_type: Optional[str] = None,
    transport: Transport = http_request,
    _retry: bool = True,
) -> Dict[str, str]:
    """POST one file, return {"fileId", "url"}. Retries ONCE (never on 429).

    Trusts the API's `url` field as the authoritative public URL. The CDN host
    varies by account and era, so no host is ever asserted here.
    """
    if not os.path.isfile(path):
        raise UploadFailed(f"File not found for upload: {path}")
    ctype = content_type or _guess_content_type(path, "application/octet-stream")
    headers = {
        "Authorization": f"Bearer {cred.value}",
        "Version": API_VERSION,
    }
    data = {
        "locationId": location_id,
        "name": display_name,
        "hosted": "false",
    }
    if parent_id:
        data["parentId"] = parent_id

    with open(path, "rb") as handle:
        files = {"file": (display_name, handle, ctype)}
        try:
            response = transport(
                "POST",
                BASE_HOST + MEDIA_UPLOAD_PATH,
                headers=headers,
                data=data,
                files=files,
                bucket=True,
            )
        except RateLimited:
            raise  # never retry a 429

    status = getattr(response, "status_code", None)
    body: Dict[str, Any] = {}
    try:
        body = response.json() or {}
    except Exception:
        body = {}
    file_id = body.get("fileId") or body.get("id") or ""
    url = body.get("url") or ""

    if status in (200, 201) and file_id and url:
        return {"fileId": str(file_id), "url": str(url)}

    if _retry:
        # One retry for a transient empty/failed response. Not for 429 (handled
        # above by RateLimited) and not for auth failures.
        if status in (401, 403):
            raise UploadFailed(
                "Media upload rejected (auth). The Location PIT may be an "
                "agency-level token, which returns 401 for media operations."
            )
        return upload_file(
            path,
            display_name,
            parent_id,
            cred,
            location_id,
            content_type=ctype,
            transport=transport,
            _retry=False,
        )

    raise UploadFailed(
        f"Media upload failed after one retry (status={status}, "
        f"fileId={'set' if file_id else 'missing'}, "
        f"url={'set' if url else 'missing'})."
    )


# --------------------------------------------------------------------------- #
# Public-URL reachability (mandatory before the URL is used anywhere)
# --------------------------------------------------------------------------- #

def verify_public_url(
    url: str,
    expected_family: str,
    *,
    transport: Transport = http_request,
) -> Dict[str, Any]:
    """Unauthenticated HEAD (ranged-GET fallback). Require 200/206 and a sane type.

    A text/html body on an asset URL is a login/error page and is a hard fail:
    that is exactly the downstream Podbean failure this check exists to prevent.
    An application/octet-stream type is accepted with a warning (real CDN
    behavior); a family mismatch that is not octet-stream is a warning too, but
    the request must still be publicly reachable.
    """
    warnings: List[str] = []
    response = None
    method = "HEAD"
    try:
        response = transport(
            "HEAD", url, allow_redirects=True, bucket=False
        )
    except Exception:
        response = None

    status = getattr(response, "status_code", None) if response is not None else None
    if status not in (200, 206):
        method = "GET"
        try:
            response = transport(
                "GET",
                url,
                headers={"Range": "bytes=0-0"},
                allow_redirects=True,
                bucket=False,
            )
        except Exception as exc:
            raise ReachabilityError(f"Public URL not reachable: {exc}")
        status = getattr(response, "status_code", None)

    if status not in (200, 206):
        raise ReachabilityError(
            f"Public URL returned HTTP {status}; expected 200 or 206."
        )

    content_type = ""
    try:
        content_type = (response.headers.get("Content-Type", "") or "").lower()
    except Exception:
        content_type = ""
    ctype_main = content_type.split(";")[0].strip()

    if ctype_main.startswith("text/html"):
        raise ReachabilityError(
            "Public URL returned text/html (login or error page), not the asset."
        )

    family = expected_family.lower()
    if ctype_main and not ctype_main.startswith(family):
        if ctype_main in ("application/octet-stream", "binary/octet-stream"):
            warnings.append(
                f"Content-Type is {ctype_main}; expected {expected_family}. "
                f"Accepted (CDN generic type) but flagged."
            )
        else:
            warnings.append(
                f"Content-Type {ctype_main} does not match expected "
                f"{expected_family}. Reachable, but flagged for review."
            )

    return {
        "ok": True,
        "status": status,
        "method": method,
        "content_type": ctype_main,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Orchestration (PRD Step 14)
# --------------------------------------------------------------------------- #

INTERVIEW_MODE = "interview_style_podcast"
PERSONAL_MODE = "personal_podcast_style"


def _pick_parent(folders: Dict[str, Any], preferred: str) -> Optional[str]:
    """Prefer the dedicated child folder; degrade to the parent podcast folder."""
    return folders.get(preferred) or folders.get(PARENT_FOLDER)


def store_media(
    job: Dict[str, Any],
    cred: Credential,
    location_id: str,
    *,
    state: Optional[Dict[str, Any]] = None,
    transport: Transport = http_request,
) -> Dict[str, Any]:
    """Upload cover + MP3 (+ teaser in Interview mode) and verify every URL.

    Raises on any terminal upload or reachability failure so the run stops
    BEFORE Podbean; a half-uploaded episode is never partially published.
    """
    if not cred.present:
        raise CredentialError("Location PIT is NOT SET; cannot upload media.")

    mode = job.get("mode", "")
    client = job.get("client_name", "")
    title = job.get("episode_title", "")
    if not client or not title:
        raise MediaError("job requires client_name and episode_title.")

    folders = ensure_folders(cred, location_id, state=state, transport=transport)
    warnings: List[str] = list(folders.get("_warnings", []))
    result: Dict[str, Any] = {
        "folders": {name: folders.get(name) for name in FOLDER_NAMES},
        "assets": {},
        "warnings": warnings,
    }

    plan: List[Tuple[str, str, str, str, str]] = []
    # (asset_key, path, filename, parent_folder_name, expected_family)
    cover_path = job.get("cover_path")
    if cover_path:
        plan.append(
            (
                "cover",
                cover_path,
                sanitize_strict(client, title, "jpg"),
                IMAGES_FOLDER,
                "image/",
            )
        )
    mp3_path = job.get("mp3_path")
    if mp3_path:
        plan.append(
            (
                "mp3",
                mp3_path,
                sanitize_loose(client, title, "mp3"),
                EPISODES_FOLDER,
                "audio/",
            )
        )
    teaser_path = job.get("teaser_path")
    if teaser_path:
        if mode == INTERVIEW_MODE:
            plan.append(
                (
                    "teaser",
                    teaser_path,
                    sanitize_loose(client, title, "pdf"),
                    PARENT_FOLDER,
                    "application/pdf",
                )
            )
        else:
            warnings.append(
                "teaser_path supplied but mode is not Interview; teaser skipped."
            )

    content_types = {
        "cover": "image/jpeg",
        "mp3": "audio/mpeg",
        "teaser": "application/pdf",
    }

    for asset_key, path, filename, parent_name, family in plan:
        parent_id = _pick_parent(folders, parent_name)
        if parent_id is None:
            warnings.append(
                f"{asset_key}: no '{parent_name}' or '{PARENT_FOLDER}' folder; "
                f"uploading to the media root."
            )
        uploaded = upload_file(
            path,
            filename,
            parent_id,
            cred,
            location_id,
            content_type=content_types.get(asset_key),
            transport=transport,
        )
        verification = verify_public_url(
            uploaded["url"], family, transport=transport
        )
        warnings.extend(verification.get("warnings", []))
        result["assets"][asset_key] = {
            "filename": filename,
            "parent_folder": parent_name,
            "parent_id": parent_id,
            "fileId": uploaded["fileId"],
            "url": uploaded["url"],
            "reachable": verification["ok"],
            "verify_status": verification["status"],
            "verify_method": verification["method"],
            "content_type": verification["content_type"],
        }

    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_store(args: argparse.Namespace) -> int:
    with open(args.job, "r", encoding="utf-8") as handle:
        job = json.load(handle)
    state = None
    if args.state and os.path.isfile(args.state):
        with open(args.state, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    cred = resolve_pit()
    if not cred.present:
        print(json.dumps({"error": "credential missing", "pit": cred.report()}))
        return 2
    location_id = resolve_location_id(
        payload_location_id=job.get("location_id")
    )
    try:
        result = store_media(job, cred, location_id, state=state)
    except RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after}))
        return 5
    except ReachabilityError as exc:
        print(json.dumps({"error": "reachability", "detail": str(exc)}))
        return 4
    except CredentialError as exc:
        print(json.dumps({"error": "credential", "detail": str(exc)}))
        return 2
    print(redact(json.dumps(result, indent=2), cred.value))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_public_url(args.url, args.family)
    except ReachabilityError as exc:
        print(json.dumps({"error": "reachability", "detail": str(exc)}))
        return 4
    print(json.dumps(result, indent=2))
    return 0


def _cmd_self_test(_args: argparse.Namespace) -> int:
    return 0 if _self_test() else 1


def _self_test() -> bool:
    """Offline checks. No network is contacted. Returns True on all-pass."""
    ok = True

    def check(label: str, condition: bool) -> None:
        nonlocal ok
        status = "PASS" if condition else "FAIL"
        if not condition:
            ok = False
        print(f"  [{status}] {label}")

    print("media_upload self-test:")

    # Filenames.
    check(
        "cover filename is strict (underscores, single .jpg)",
        sanitize_strict("Sample Speaker!", "The Power of Marketing", "jpg")
        == "Sample_Speaker_The_Power_of_Marketing.jpg",
    )
    check(
        "mp3 filename is client-first with spaces",
        sanitize_loose("Sample Speaker", "The Power of Marketing", "mp3")
        == "Sample Speaker - The Power of Marketing.mp3",
    )
    check(
        "teaser filename ext is pdf",
        sanitize_loose("A", "B", "pdf") == "A - B.pdf",
    )

    # Redaction.
    check(
        "redact scrubs the secret",
        REDACTION in redact("bearer pit-secret-123", "pit-secret-123")
        and "pit-secret-123" not in redact("x pit-secret-123", "pit-secret-123"),
    )

    # Credential report carries no value.
    cred = Credential(present=True, value="pit-abc", alias="GHL_API_KEY",
                      prefix_ok=True, length=7)
    check("credential report omits the value",
          "pit-abc" not in json.dumps(cred.report()))

    # Folder matching: case-insensitive, trimmed, duplicate picks oldest.
    folders = [
        {"id": "F2", "name": "Podcast Images ", "createdAt": "2026-02-01"},
        {"id": "F1", "name": "podcast images", "createdAt": "2026-01-01"},
    ]
    fid, warns = _match_folder(folders, IMAGES_FOLDER)
    check("duplicate folder match returns the oldest", fid == "F1" and bool(warns))

    fid_none, _ = _match_folder(folders, EPISODES_FOLDER)
    check("missing folder returns None (no create)", fid_none is None)

    # ensure_folders with a fake transport that returns only the parent.
    class _FakeResp:
        status_code = 200

        @staticmethod
        def json() -> Dict[str, Any]:
            return {"files": [{"id": "P", "name": "Podcast", "type": "folder",
                               "createdAt": "2026-01-01"}]}

    def fake_transport(method: str, url: str, **kwargs: Any) -> Any:
        return _FakeResp()

    fmap = ensure_folders(Credential(present=True, value="pit-x"), "LOC",
                          transport=fake_transport)
    check("ensure_folders finds the parent only",
          fmap[PARENT_FOLDER] == "P" and fmap[IMAGES_FOLDER] is None)
    check("ensure_folders warns about missing children",
          any("podcast images" in w for w in fmap["_warnings"]))
    check("degrade picks parent when child folder is absent",
          _pick_parent(fmap, IMAGES_FOLDER) == "P")

    # verify_public_url: text/html is a hard fail.
    class _HtmlResp:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

    def html_transport(method: str, url: str, **kwargs: Any) -> Any:
        return _HtmlResp()

    html_failed = False
    try:
        verify_public_url("http://x/asset.jpg", "image/", transport=html_transport)
    except ReachabilityError:
        html_failed = True
    check("text/html asset URL is a hard reachability fail", html_failed)

    # verify_public_url: octet-stream is accepted with a warning.
    class _OctetResp:
        status_code = 200
        headers = {"Content-Type": "application/octet-stream"}

    def octet_transport(method: str, url: str, **kwargs: Any) -> Any:
        return _OctetResp()

    octet = verify_public_url("http://x/a.mp3", "audio/", transport=octet_transport)
    check("octet-stream passes with a warning",
          octet["ok"] and bool(octet["warnings"]))

    # 429 raises RateLimited on a bucket call.
    class _RateResp:
        status_code = 429
        headers = {"Retry-After": "30"}

    rate_stopped = False
    try:
        # exercise the 429 branch directly through a fake requests layer
        _saved = globals().get("requests")
        class _FakeRequests:
            @staticmethod
            def request(*a: Any, **k: Any) -> Any:
                return _RateResp()
        globals()["requests"] = _FakeRequests
        try:
            http_request("GET", BASE_HOST + MEDIA_LIST_PATH, bucket=True)
        except RateLimited as exc:
            rate_stopped = exc.retry_after == 30.0
        finally:
            globals()["requests"] = _saved
    except Exception:
        rate_stopped = False
    check("429 on a bucket call raises RateLimited with retry_after", rate_stopped)

    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Podcast Engine Tier 3 media upload and URL verification.",
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Run offline self-checks (no network) and exit.")
    sub = parser.add_subparsers(dest="command")

    store = sub.add_parser("store", help="Upload and verify episode media.")
    store.add_argument("--job", required=True, help="Path to the job JSON file.")
    store.add_argument("--state", help="Path to the per-client ghl-state.json.")
    store.set_defaults(func=_cmd_store)

    verify = sub.add_parser("verify", help="HEAD-verify one public URL.")
    verify.add_argument("--url", required=True)
    verify.add_argument("--family", default="", help="Expected type family, e.g. image/")
    verify.set_defaults(func=_cmd_verify)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _cmd_self_test(args)
    if not getattr(args, "command", None):
        parser.print_help()
        return 3
    try:
        return args.func(args)
    except CredentialError as exc:
        print(json.dumps({"error": "credential", "detail": str(exc)}))
        return 2
    except RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after}))
        return 5


if __name__ == "__main__":
    sys.exit(main())
