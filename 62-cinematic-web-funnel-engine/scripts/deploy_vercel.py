#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deploy_vercel.py — the P14-PREVIEW / P15-PRODUCTION phase producer
(Skill 62, U17). CWFE-MANIFEST.json names this file for both phases
(``"delegate": "08-vercel-setup"``); the sibling gate is
``scripts/prove_deployment.py`` (``prove_deployment.evaluate_preview`` /
``prove_deployment.evaluate_production``).

Delegates to Skill 08 (``08-vercel-setup``) only for CREDENTIAL SETUP — the
operator/client provisions ``VERCEL_TOKEN`` there once; this module never
duplicates that onboarding flow, it only resolves the token BY NAME from the
environment (spec 20 client sovereignty; ADR-6-adjacent "never invent a
parallel platform" doctrine). The actual deployment mechanics below are kept
in LOCKSTEP, on purpose, with the one other proven Vercel REST client already
in this repository — ``06-ghl-install-pages/tools/ghl_vercel.py`` — reusing
its exact token-resolution order (``VERCEL_TOKEN`` -> ``VERCEL_API_TOKEN`` ->
``VERCEL_API_KEY``), its ``/v13/deployments`` POST + poll shape, its
``{"file", "data", "encoding": "base64"}`` file-inlining format, and its
plain ``urllib``-based transport pattern — never a third divergent Vercel
client (same "do not fork a divergent client" doctrine spec §10.1 states for
Kie adapters).

WHAT THIS UNIT SHIPS (spec Section 22 item 18 "Vercel deployment and storage
adapters"; U17 directive: "the Vercel deployment adapter + prove_deployment.py
+ the Blob storage / hosting adapter"):

  1. ``scripts/lib/hosting_adapter.py`` (sibling file) — the provider-neutral
     ``HostingAdapter`` / ``BlobStorageAdapter`` CONTRACT spec §14.4 asks for
     ("Use an adapter contract for: Vercel; Cloudflare ...; Netlify;
     self-hosted ...; static export ..."). Only Vercel gets a concrete,
     tested implementation in this unit — spec §14.4: "An alternate host may
     not be advertised as supported until its deployment adapter and E2E
     fixture pass."
  2. ``VercelHostingAdapter`` (below) — the concrete Vercel implementation of
     that contract: submits a deployment, polls it to a terminal state, and
     runs a real post-deploy smoke test (spec 17.8).
  3. ``VercelBlobAdapter`` (below) — the concrete Vercel Blob implementation
     of the storage contract (spec line 13: "Default media storage: Vercel
     Blob, with adapter support for Cloudflare R2/S3-compatible storage").
     Uploads scene media independently of the site deployment and writes
     ``blob-manifest.json``; NOT yet wired into the generated site's own
     data module (that would touch U15/U16-owned template files, outside
     this unit's file area) — the blob URLs are recorded as real, verified
     provenance for a later wiring unit to consume. Named here explicitly,
     the same way this skill has always named a real gap rather than
     papering over it (e.g. kie_video.py's pre-U5 Seedance gap).
  4. Producer functions (``deploy_preview``, ``deploy_production``,
     ``reconcile_deployment``, ``upload_scene_media_to_blob``) that read the
     P11 ``build-receipt.json``, drive an adapter, and persist the result
     through ``state_engine.ProjectState.append_deployment_receipt`` (the
     U6 state engine already implements the append-only
     ``deployment-receipts.json`` store + ``project-manifest.json``
     ``deployment{}`` mirror — this unit does not reinvent that).

FAIL-CLOSED ON A BAD RECEIPT: a deployment that does not reach Vercel's
``READY`` state, or that reaches ``READY`` but fails its post-deploy smoke
test, is still RECORDED (status ``"error"``) and then raises — this module
never returns/writes a receipt claiming success for a deployment that did
not actually succeed. Production additionally refuses to deploy a
``commit_sha`` that differs from the ``commit_sha`` its own already-proven
preview deployment recorded (spec 17.8 "commit SHA"; spec 14.1 "production
deployment only after generated-site QC passes" — the mechanical proxy used
here is "the exact commit a passing preview already proved").

Vercel Blob wire format grounding (spec 19.2 — this unit is MOCK-TESTED
ONLY, no live call is made by anything in this file's test suite or
self-test): the ``PUT https://blob.vercel-storage.com/<pathname>`` endpoint
and its ``authorization`` / ``x-api-version`` / ``x-content-type`` /
``x-cache-control-max-age`` / ``access`` headers are not published as a raw
HTTP spec by Vercel's own docs (which document only the ``@vercel/blob`` JS
SDK, e.g. ``vercel.com/docs/vercel-blob/using-blob-sdk`` for the
``BLOB_READ_WRITE_TOKEN`` env var and the ``url``/``pathname``/
``contentType``/``contentDisposition``/``downloadUrl`` response fields);
the exact header names are cross-checked against the open-source reference
client ``github.com/SuryaSekhar14/vercel_blob`` (``vercel_blob/blob_store.py``
``put()``), the best-grounded source available without a live call. This
MUST be re-verified against a real response before the U26 live canary.

NO LIVE/PAID CALL: every HTTP interaction goes through the injectable
``VercelTransport`` seam (mirrors ``providers/kie.py``'s ``KieTransport``
exactly). ``RequestsTransport`` — the only implementation that ever touches
the network — is never instantiated by this module's own tests or
``--self-test``.

SECRETS BY NAME ONLY: ``VERCEL_TOKEN``/``VERCEL_API_TOKEN``/
``VERCEL_API_KEY`` and ``BLOB_READ_WRITE_TOKEN`` are resolved from the
environment by variable NAME. No secret VALUE is ever logged, printed, or
embedded in an exception message, a manifest, or a receipt.

stdlib + optional ``requests`` (imported lazily, only inside
``RequestsTransport``, exactly like ``providers/kie.py`` and
``06-ghl-install-pages/tools/ghl_vercel.py``) — importing this module never
requires ``requests`` to be installed.

Exit codes (CLI): 0 = receipt/manifest written and the operation succeeded;
1 = the operation failed (a receipt recording the failure was still
written, where applicable); 2 = usage error.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402
import hosting_adapter as ha  # noqa: E402
import state_engine  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Constants — Vercel deployments API (lockstep with 06-ghl-install-pages/
# tools/ghl_vercel.py's VERCEL_API_ORIGIN / VERCEL_API_VERSION_DEPLOYMENTS,
# verified live against vercel.com/docs/rest-api/deployments/
# create-a-new-deployment 2026-07-15: "POST /v13/deployments"; readyState
# enum QUEUED/INITIALIZING/BUILDING/READY/ERROR, deployment-states doc adds
# CANCELED).
# ---------------------------------------------------------------------------
VERCEL_API_ORIGIN = "https://api.vercel.com"
VERCEL_API_VERSION_DEPLOYMENTS = "v13"
HTTP_TIMEOUT_SECONDS = 30
DEFAULT_POLL_MAX = 30
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

VERCEL_TOKEN_ENV_CANDIDATES = ("VERCEL_TOKEN", "VERCEL_API_TOKEN", "VERCEL_API_KEY")

# Directories never inlined into a Vercel deployment payload — Vercel builds
# the project itself (projectSettings.framework="nextjs"), so shipping a
# pre-installed node_modules/.next would only bloat (and could poison) the
# real build. Mirrors ghl_vercel.py's hidden-file/dir skip, extended with the
# Next.js-specific build/dependency directories this skill's own
# scripts/build_site.py materializes locally.
_EXCLUDED_DIR_NAMES = {"node_modules", ".next", ".git", "__pycache__", ".turbo", ".vercel", ".venv"}

# ---------------------------------------------------------------------------
# Constants — Vercel Blob (see module docstring for the sourcing note).
# ---------------------------------------------------------------------------
BLOB_API_ORIGIN = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "10"
BLOB_TOKEN_ENV_CANDIDATES = ("BLOB_READ_WRITE_TOKEN",)
DEFAULT_BLOB_CACHE_MAX_AGE_SECONDS = 31536000  # 1 year; matches the OSS reference client's default.


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class VercelTokenError(Exception):
    """Raised when no Vercel (or Blob) token can be resolved from the
    environment. The message names the candidate env-var NAMES only."""


class DeploymentError(ha.HostingAdapterError):
    """Raised for any deployment failure: submission error, a terminal
    non-READY state, a failed smoke test, a commit-sha mismatch on
    production, or a missing/invalid upstream artifact."""


class VercelBlobError(ha.BlobStorageError):
    """Raised for any Vercel Blob upload failure."""


# ---------------------------------------------------------------------------
# Transport seam — the ONLY place that ever touches the network.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json_body: Dict[str, Any] = field(default_factory=dict)
    content: bytes = b""


class VercelTransport:
    """Everything the Vercel adapters need to talk to api.vercel.com and
    blob.vercel-storage.com, abstracted so tests never make a real HTTP
    call. Not an ``abc.ABC`` (matching ``providers/kie.py``'s ``KieTransport``
    style is fine either way; kept as a plain base here since every method
    below already raises ``NotImplementedError`` by default, which is
    sufficient for a fake to override only what it exercises)."""

    def post_json(self, url: str, *, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> HttpResponse:
        raise NotImplementedError

    def get_json(self, url: str, *, headers: Dict[str, str], params: Optional[Dict[str, Any]], timeout: float) -> HttpResponse:
        raise NotImplementedError

    def patch_json(self, url: str, *, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> HttpResponse:
        raise NotImplementedError

    def put_bytes(self, url: str, *, headers: Dict[str, str], data: bytes, timeout: float) -> HttpResponse:
        raise NotImplementedError

    def fetch(self, url: str, *, timeout: float) -> HttpResponse:
        """Real GET of a deployed page (not a JSON API call) — used by
        ``smoke_test``. Returns raw ``content`` bytes; ``json_body`` is
        always ``{}``."""
        raise NotImplementedError


def _safe_json_from_requests(resp: Any) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


class RequestsTransport(VercelTransport):
    """Default transport. Lazily imports ``requests`` inside each method
    (mirrors ``providers/kie.py`` and ``ghl_vercel.py``'s lazy-import style).
    NEVER used by this unit's tests or ``--self-test`` — see the fakes in
    ``tests/unit/test_deploy_vercel.py`` and the module-local self-test
    fakes below."""

    def post_json(self, url, *, headers, body, timeout):
        import requests

        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json_from_requests(resp))

    def get_json(self, url, *, headers, params, timeout):
        import requests

        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json_from_requests(resp))

    def patch_json(self, url, *, headers, body, timeout):
        import requests

        resp = requests.patch(url, headers=headers, json=body, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json_from_requests(resp))

    def put_bytes(self, url, *, headers, data, timeout):
        import requests

        resp = requests.put(url, headers=headers, data=data, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json_from_requests(resp))

    def fetch(self, url, *, timeout):
        import requests

        resp = requests.get(url, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body={}, content=resp.content)


# ---------------------------------------------------------------------------
# Token resolution — secrets by NAME only.
# ---------------------------------------------------------------------------


def resolve_token(env: Optional[Dict[str, str]] = None, *,
                   candidates: tuple = VERCEL_TOKEN_ENV_CANDIDATES,
                   label: str = "Vercel API token") -> str:
    env = env if env is not None else os.environ
    for name in candidates:
        val = (env.get(name) or "").strip()
        if val:
            return val
    raise VercelTokenError(
        f"No {label} found. Set one of: {', '.join(candidates)} "
        "(secret resolved by NAME only; the value itself is never logged)."
    )


def resolve_blob_token(env: Optional[Dict[str, str]] = None) -> str:
    return resolve_token(env, candidates=BLOB_TOKEN_ENV_CANDIDATES, label="Vercel Blob read-write token")


# ---------------------------------------------------------------------------
# readyState mapping — fail-closed on an unrecognized value.
# ---------------------------------------------------------------------------

_READY_STATE_MAP = {
    "QUEUED": "queued",
    "INITIALIZING": "building",
    "BUILDING": "building",
    "READY": "ready",
    "ERROR": "error",
    "CANCELED": "cancelled",
    "CANCELLED": "cancelled",
}


def _map_ready_state(vercel_state: str) -> str:
    mapped = _READY_STATE_MAP.get((vercel_state or "").upper())
    if mapped is None:
        raise DeploymentError(
            f"unrecognized Vercel readyState {vercel_state!r} — refusing to guess a "
            f"deployment-receipt status (known states: {sorted(_READY_STATE_MAP)})"
        )
    return mapped


_TERMINAL_STATUSES = ("ready", "error", "cancelled")


# ---------------------------------------------------------------------------
# VercelHostingAdapter — concrete HostingAdapter implementation.
# ---------------------------------------------------------------------------


class VercelHostingAdapter(ha.HostingAdapter):
    def __init__(self, transport: VercelTransport, token: str, *,
                 team_id: Optional[str] = None,
                 poll_max: int = DEFAULT_POLL_MAX,
                 poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
                 sleep_fn=time.sleep) -> None:
        self._transport = transport
        self._token = token
        self._team_id = team_id
        self._poll_max = poll_max
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep_fn = sleep_fn

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        url = f"{VERCEL_API_ORIGIN}{path}"
        if self._team_id:
            url += f"?teamId={urllib.parse.quote(self._team_id)}"
        return url

    def deploy(self, site_dir: str, *, environment: str, project_name: str,
               commit_sha: str, wait_for_ready: bool = True) -> ha.DeployResult:
        if environment not in ("preview", "production"):
            raise DeploymentError(f"unknown environment {environment!r} (must be 'preview' or 'production')")

        files = _read_deployable_files(site_dir)
        if not files:
            raise DeploymentError(f"no deployable files found under {site_dir!r} — refusing to submit an empty deployment")

        payload: Dict[str, Any] = {
            "name": project_name,
            "files": files,
            "projectSettings": {"framework": "nextjs"},
            "gitMetadata": {"commitSha": commit_sha, "dirty": False},
        }
        # target field: omitted -> Vercel defaults to "preview" (verified against
        # the live REST doc's `target` description). "production" is set
        # explicitly, never inferred from anything else.
        if environment == "production":
            payload["target"] = "production"

        resp = self._transport.post_json(
            self._url(f"/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments"),
            headers=self._headers(), body=payload, timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise DeploymentError(f"Vercel deploy submission failed: HTTP {resp.status_code}: {resp.json_body}")

        deployment_id = resp.json_body.get("id") or resp.json_body.get("uid")
        if not deployment_id:
            raise DeploymentError(f"Vercel deploy response missing id/uid. keys={sorted(resp.json_body.keys())}")

        result = self._result_from_response(resp.json_body, deployment_id)

        if wait_for_ready and result.status not in _TERMINAL_STATUSES:
            result = self._poll_to_terminal(deployment_id)
        return result

    def _poll_to_terminal(self, deployment_id: str) -> ha.DeployResult:
        last: Optional[ha.DeployResult] = None
        for _attempt in range(1, self._poll_max + 1):
            last = self.get_status(deployment_id)
            if last.status in _TERMINAL_STATUSES:
                return last
            self._sleep_fn(self._poll_interval_seconds)
        raise DeploymentError(
            f"Vercel deployment {deployment_id} did not reach a terminal state within "
            f"{self._poll_max} polls (last status={last.status if last else 'unknown'!r})"
        )

    def get_status(self, host_deployment_id: str) -> ha.DeployResult:
        resp = self._transport.get_json(
            self._url(f"/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments/{host_deployment_id}"),
            headers=self._headers(), params=None, timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise DeploymentError(f"Vercel status poll failed for {host_deployment_id}: HTTP {resp.status_code}: {resp.json_body}")
        return self._result_from_response(resp.json_body, host_deployment_id)

    def disable_protection(self, host_deployment_id: str) -> bool:
        """Optional: disable Deployment Protection (SSO) on a deployment.
        Not called by ``deploy_preview``/``deploy_production`` for
        direct-hosted mode (spec 14.1 default) — new Vercel deployments are
        not protection-gated by default on the plans this engine targets,
        unlike the GHL-iframe-embed path (``ghl_vercel.make_public``, which
        this method mirrors) where protection defeats the iframe entirely.
        Exposed here so a caller that DOES need it never has to write a
        fourth divergent implementation of the same PATCH call."""
        resp = self._transport.patch_json(
            self._url(f"/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments/{host_deployment_id}"),
            headers=self._headers(), body={"protection": {"deploymentType": "none"}}, timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise DeploymentError(f"disable_protection failed for {host_deployment_id}: HTTP {resp.status_code}: {resp.json_body}")
        return True

    def _result_from_response(self, body: Dict[str, Any], deployment_id: str) -> ha.DeployResult:
        ready_state = str(body.get("readyState") or body.get("state") or "QUEUED")
        status = _map_ready_state(ready_state)
        raw_url = body.get("url")
        url = None
        if raw_url:
            url = raw_url if raw_url.startswith("https://") else f"https://{raw_url}"
        return ha.DeployResult(
            host="vercel",
            host_project_id=body.get("projectId"),
            host_deployment_id=deployment_id,
            url=url,
            status=status,
            raw=body,
        )

    def smoke_test(self, url: str) -> ha.SmokeTestResult:
        resp = self._transport.fetch(url, timeout=HTTP_TIMEOUT_SECONDS)
        ok = resp.status_code == 200
        detail = "smoke test OK (HTTP 200)" if ok else f"smoke test FAILED: HTTP {resp.status_code}"
        return ha.SmokeTestResult(ok=ok, http_status=resp.status_code, detail=detail)


# ---------------------------------------------------------------------------
# VercelBlobAdapter — concrete BlobStorageAdapter implementation.
# ---------------------------------------------------------------------------


class VercelBlobAdapter(ha.BlobStorageAdapter):
    def __init__(self, transport: VercelTransport, token: str) -> None:
        self._transport = transport
        self._token = token

    def put(self, local_path: str, *, pathname: str, content_type: Optional[str] = None) -> ha.BlobPutResult:
        path = Path(local_path)
        if not path.is_file():
            raise VercelBlobError(f"local_path does not exist or is not a file: {local_path}")
        data = path.read_bytes()
        resolved_content_type = content_type or (mimetypes.guess_type(str(path))[0] or "application/octet-stream")

        headers = {
            "access": "public",
            "authorization": f"Bearer {self._token}",
            "x-api-version": BLOB_API_VERSION,
            "x-content-type": resolved_content_type,
            "x-cache-control-max-age": str(DEFAULT_BLOB_CACHE_MAX_AGE_SECONDS),
        }
        url = f"{BLOB_API_ORIGIN}/{pathname.lstrip('/')}"
        resp = self._transport.put_bytes(url, headers=headers, data=data, timeout=HTTP_TIMEOUT_SECONDS)
        if resp.status_code >= 400:
            raise VercelBlobError(f"Vercel Blob upload failed for {pathname!r}: HTTP {resp.status_code}: {resp.json_body}")

        body = resp.json_body
        blob_url = body.get("url")
        if not blob_url:
            raise VercelBlobError(f"Vercel Blob upload response missing 'url'. keys={sorted(body.keys())}")
        if not blob_url.startswith("https://"):
            raise VercelBlobError(f"Vercel Blob upload returned a non-https url: {blob_url!r}")

        return ha.BlobPutResult(
            provider="vercel-blob",
            url=blob_url,
            pathname=body.get("pathname", pathname),
            content_type=body.get("contentType", resolved_content_type),
            size_bytes=len(data),
            raw=body,
        )


# ---------------------------------------------------------------------------
# File-tree helpers
# ---------------------------------------------------------------------------


def _read_deployable_files(site_dir: str) -> List[Dict[str, str]]:
    """Walk ``site_dir`` and return Vercel deployments-API file objects
    (``{"file", "data", "encoding": "base64"}`` — the exact shape
    ``ghl_vercel._read_project_files`` already uses, kept in lockstep).
    Excludes build/dependency directories (Vercel builds the project itself)
    and hidden files/dirs. Deterministic order (sorted) so two runs against
    an unchanged tree produce byte-identical payloads."""
    root = Path(site_dir)
    files: List[Dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_DIR_NAMES and not d.startswith("."))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            abs_path = Path(dirpath) / filename
            rel_path = abs_path.relative_to(root)
            raw = abs_path.read_bytes()
            files.append({
                "file": str(rel_path).replace(os.sep, "/"),
                "data": base64.b64encode(raw).decode("ascii"),
                "encoding": "base64",
            })
    return files


def resolve_commit_sha(explicit: Optional[str] = None, *, cwd: Optional[Path] = None) -> str:
    """Resolve the commit SHA a deployment receipt must record (spec 17.8).
    Never fabricates one: an explicit value is used verbatim (trimmed,
    rejected if empty); otherwise ``git rev-parse HEAD`` is run against
    ``cwd`` (default: this skill's own repository) and its failure raises
    rather than falling back to a placeholder."""
    if explicit is not None:
        trimmed = explicit.strip()
        if not trimmed:
            raise DeploymentError("commit_sha override was provided but is empty")
        return trimmed

    resolved_cwd = str(cwd) if cwd is not None else str(_SKILL_DIR)
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=resolved_cwd,
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError(f"could not resolve commit_sha via 'git rev-parse HEAD' in {resolved_cwd}: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise DeploymentError(
            f"'git rev-parse HEAD' failed in {resolved_cwd} (exit {proc.returncode}): "
            f"{proc.stderr.strip()} — pass commit_sha explicitly instead"
        )
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Receipt helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _make_receipt(*, project_id: str, environment: str,
                   host_project_id: Optional[str], host_deployment_id: Optional[str],
                   url: Optional[str], commit_sha: str, status: str,
                   restart_verified: bool = False) -> Dict[str, Any]:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "environment": environment,
        "host": "vercel",
        "host_project_id": host_project_id,
        "host_deployment_id": host_deployment_id,
        "url": url,
        "commit_sha": commit_sha,
        "status": status,
        "restart_verified": restart_verified,
        "created_at": now,
        "updated_at": now,
    }


def _load_build_receipt(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "build-receipt.json"
    if not path.is_file():
        raise DeploymentError(f"build-receipt.json not found at {path} — P11-SITE-BUILD must run before P14/P15")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"build-receipt.json is not valid JSON: {exc}") from exc
    schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        raise DeploymentError("build-receipt.json failed schema validation: " + "; ".join(errors))
    return receipt


# ---------------------------------------------------------------------------
# Producer functions
# ---------------------------------------------------------------------------


def _deploy(run_dir: "str | Path", *, environment: str, commit_sha: Optional[str],
            adapter: Optional[ha.HostingAdapter], project_name: Optional[str],
            run_smoke_test: bool = True) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    build_receipt = _load_build_receipt(run_dir)
    if build_receipt.get("status") != "pass":
        raise DeploymentError(
            f"refusing to deploy {environment}: build-receipt.json status is "
            f"{build_receipt.get('status')!r}, not 'pass' (spec 14.1: deployment must follow a "
            "passed P11-SITE-BUILD)"
        )
    site_dir = Path(build_receipt["site_dir"])
    if not site_dir.is_dir():
        raise DeploymentError(f"build-receipt.json's site_dir does not exist on disk: {site_dir}")

    state = state_engine.ProjectState(run_dir)
    manifest = state.load("project-manifest")
    project_id = manifest["project_id"]
    if build_receipt["project_id"] != project_id:
        raise DeploymentError(
            f"build-receipt.json project_id {build_receipt['project_id']!r} does not match "
            f"project-manifest.json project_id {project_id!r} — refusing to deploy a mismatched project"
        )

    resolved_commit_sha = resolve_commit_sha(commit_sha)
    resolved_project_name = project_name or manifest["project_slug"]

    _adapter: ha.HostingAdapter = adapter if adapter is not None else VercelHostingAdapter(RequestsTransport(), resolve_token())

    try:
        result = _adapter.deploy(
            str(site_dir), environment=environment,
            project_name=resolved_project_name, commit_sha=resolved_commit_sha,
        )
    except ha.HostingAdapterError as exc:
        receipt = _make_receipt(
            project_id=project_id, environment=environment,
            host_project_id=None, host_deployment_id=None, url=None,
            commit_sha=resolved_commit_sha, status="error",
        )
        state.append_deployment_receipt(receipt)
        raise DeploymentError(f"{environment} deployment submission failed: {exc}") from exc

    if result.status == "ready" and run_smoke_test and result.url:
        smoke = _adapter.smoke_test(result.url)
        if not smoke.ok:
            receipt = _make_receipt(
                project_id=project_id, environment=environment,
                host_project_id=result.host_project_id, host_deployment_id=result.host_deployment_id,
                url=result.url, commit_sha=resolved_commit_sha, status="error",
            )
            state.append_deployment_receipt(receipt)
            raise DeploymentError(
                f"{environment} deployment {result.host_deployment_id} reached READY but failed its "
                f"post-deploy smoke test: {smoke.detail}"
            )

    receipt = _make_receipt(
        project_id=project_id, environment=environment,
        host_project_id=result.host_project_id, host_deployment_id=result.host_deployment_id,
        url=result.url, commit_sha=resolved_commit_sha, status=result.status,
    )
    state.append_deployment_receipt(receipt)

    if result.status != "ready":
        raise DeploymentError(
            f"{environment} deployment {result.host_deployment_id} did not reach 'ready' "
            f"(status={result.status!r}); receipt recorded for diagnosis, not certified"
        )
    return receipt


def deploy_preview(run_dir: "str | Path", *, commit_sha: Optional[str] = None,
                    adapter: Optional[ha.HostingAdapter] = None,
                    project_name: Optional[str] = None) -> Dict[str, Any]:
    """P14-PREVIEW producer. Raises ``DeploymentError`` (never returns a
    receipt claiming success) on submission failure, a non-READY terminal
    state, or a failed smoke test — in every case a receipt is still
    appended to ``deployment-receipts.json`` recording what actually
    happened."""
    return _deploy(run_dir, environment="preview", commit_sha=commit_sha, adapter=adapter, project_name=project_name)


def deploy_production(run_dir: "str | Path", *, commit_sha: Optional[str] = None,
                       adapter: Optional[ha.HostingAdapter] = None,
                       project_name: Optional[str] = None,
                       require_preview: bool = True) -> Dict[str, Any]:
    """P15-PRODUCTION producer. When ``require_preview`` (default), refuses
    to run unless a ``ready`` preview deployment receipt already exists for
    this project, and refuses to deploy any ``commit_sha`` other than the
    one that preview already proved (spec 17.8's "commit SHA" gate,
    mechanically enforced rather than merely documented)."""
    run_dir = Path(run_dir)
    resolved_commit_sha = commit_sha

    if require_preview:
        state = state_engine.ProjectState(run_dir)
        preview = state.latest_deployment_receipt("preview")
        if preview is None:
            raise DeploymentError(
                "production deploy refused: no preview deployment receipt found for this project "
                "(P14-PREVIEW must complete and pass before P15-PRODUCTION runs)"
            )
        if preview["status"] != "ready":
            raise DeploymentError(
                f"production deploy refused: latest preview deployment status is "
                f"{preview['status']!r}, not 'ready'"
            )
        candidate_sha = resolve_commit_sha(commit_sha) if commit_sha is not None else preview["commit_sha"]
        if candidate_sha != preview["commit_sha"]:
            raise DeploymentError(
                f"production deploy refused: requested commit_sha {candidate_sha!r} does not match "
                f"the proven preview deployment's commit_sha {preview['commit_sha']!r} — production must "
                "deploy the exact commit the preview already validated, never a silently different one"
            )
        resolved_commit_sha = candidate_sha

    return _deploy(run_dir, environment="production", commit_sha=resolved_commit_sha, adapter=adapter, project_name=project_name)


def reconcile_deployment(run_dir: "str | Path", environment: str, *,
                          adapter: Optional[ha.HostingAdapter] = None) -> Dict[str, Any]:
    """Re-fetch the latest ``environment`` deployment's state DIRECTLY from
    the host and append a new receipt with ``restart_verified=True`` (spec
    11.2 "deployment receipts and provider task IDs must survive restart";
    spec 19.3 "deployment restart/reload"). Never trusts the stale local
    receipt's own claimed status — the appended receipt's ``status`` always
    comes from the fresh ``get_status`` call, even if that differs from
    what was last recorded."""
    run_dir = Path(run_dir)
    state = state_engine.ProjectState(run_dir)
    receipt = state.latest_deployment_receipt(environment)
    if receipt is None:
        raise DeploymentError(f"no {environment} deployment receipt found to reconcile")
    if not receipt.get("host_deployment_id"):
        raise DeploymentError(f"latest {environment} receipt has no host_deployment_id — nothing to reconcile against the host")

    _adapter: ha.HostingAdapter = adapter if adapter is not None else VercelHostingAdapter(RequestsTransport(), resolve_token())
    result = _adapter.get_status(receipt["host_deployment_id"])

    new_receipt = _make_receipt(
        project_id=receipt["project_id"], environment=environment,
        host_project_id=result.host_project_id or receipt.get("host_project_id"),
        host_deployment_id=receipt["host_deployment_id"],
        url=result.url or receipt.get("url"),
        commit_sha=receipt["commit_sha"], status=result.status,
        restart_verified=True,
    )
    state.append_deployment_receipt(new_receipt)
    return new_receipt


def upload_scene_media_to_blob(run_dir: "str | Path", *,
                                adapter: Optional[ha.BlobStorageAdapter] = None) -> Dict[str, Any]:
    """Uploads every scene's video + poster (as recorded in P11's
    ``build-receipt.json``) to the Blob storage adapter and writes
    ``blob-manifest.json`` (structure/blob-manifest.schema.json). Pathnames
    are fully deterministic (``<project_id>/<scene_id>/<filename>``, no
    random suffix) — a re-run against an unchanged build overwrites the
    same blob path rather than accumulating orphans, matching this skill's
    "no randomness" determinism doctrine (see ``tests/fixtures/site-fixture/
    make_fixture.py``'s own docstring)."""
    run_dir = Path(run_dir)
    build_receipt = _load_build_receipt(run_dir)
    site_dir = Path(build_receipt["site_dir"])
    project_id = build_receipt["project_id"]

    _adapter: ha.BlobStorageAdapter = adapter if adapter is not None else VercelBlobAdapter(RequestsTransport(), resolve_blob_token())

    now = _now()
    assets: List[Dict[str, Any]] = []
    for scene in build_receipt.get("scenes", []):
        for kind, rel_key in (("video", "video_path"), ("poster", "poster_path")):
            rel_path = scene[rel_key]
            local_path = site_dir / rel_path
            if not local_path.is_file():
                raise DeploymentError(f"scene {scene['scene_id']}: {kind} missing on disk at {local_path} — cannot upload to blob storage")
            pathname = f"{project_id}/{scene['scene_id']}/{Path(rel_path).name}"
            result = _adapter.put(str(local_path), pathname=pathname)
            assets.append({
                "scene_id": scene["scene_id"],
                "kind": kind,
                "local_path": str(local_path),
                "pathname": result.pathname,
                "url": result.url,
                "content_type": result.content_type,
                "size_bytes": result.size_bytes,
                "uploaded_at": _now(),
            })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "provider": "vercel-blob",
        "assets": assets,
        "created_at": now,
        "updated_at": _now(),
    }
    schema = json.loads((_STRUCTURE_DIR / "blob-manifest.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(manifest, schema)
    if errors:
        raise DeploymentError("generated blob-manifest.json failed its own schema: " + "; ".join(errors))
    _atomic_write_json(run_dir / "blob-manifest.json", manifest)
    return manifest


# ---------------------------------------------------------------------------
# Self-test — offline, deterministic, no network. Exercises the full
# preview -> production round trip, the commit-sha mismatch refusal, the
# fail-closed ERROR-state path (receipt recorded, exception raised), the
# Blob storage adapter, and restart reconciliation, all against small
# in-module fake transports (never RequestsTransport).
# ---------------------------------------------------------------------------


class _SelfTestDeployTransport(VercelTransport):
    """POST -> QUEUED; first poll -> BUILDING; subsequent polls -> READY
    (or always ERROR when force_error). Exercises the real polling loop
    rather than a single-shot success."""

    def __init__(self, *, force_error: bool = False) -> None:
        self._force_error = force_error
        self._poll_count = 0

    def post_json(self, url, *, headers, body, timeout):
        deployment_id = f"dpl_selftest_{abs(hash(json.dumps(body, sort_keys=True))) % 10**8}"
        return HttpResponse(status_code=200, json_body={
            "id": deployment_id, "url": f"{deployment_id}.vercel.app",
            "readyState": "QUEUED", "projectId": "prj_selftest",
        })

    def get_json(self, url, *, headers, params, timeout):
        self._poll_count += 1
        deployment_id = url.split("/deployments/", 1)[-1].split("?")[0]
        if self._force_error:
            state = "ERROR"
        elif self._poll_count == 1:
            state = "BUILDING"
        else:
            state = "READY"
        return HttpResponse(status_code=200, json_body={
            "id": deployment_id, "url": f"{deployment_id}.vercel.app",
            "readyState": state, "projectId": "prj_selftest",
        })

    def patch_json(self, url, *, headers, body, timeout):
        return HttpResponse(status_code=200, json_body={"ok": True})

    def fetch(self, url, *, timeout):
        return HttpResponse(status_code=200, json_body={}, content=b"<html>cwfe self-test ok</html>")


class _SelfTestBlobTransport(VercelTransport):
    def put_bytes(self, url, *, headers, data, timeout):
        pathname = url[len(BLOB_API_ORIGIN) + 1:]
        return HttpResponse(status_code=200, json_body={
            "url": f"https://selftest.public.blob.vercel-storage.com/{pathname}",
            "pathname": pathname,
            "contentType": headers.get("x-content-type", "application/octet-stream"),
            "contentDisposition": f'inline; filename="{Path(pathname).name}"',
        })


def _self_test() -> bool:
    import tempfile

    _fixture_dir = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"
    sys.path.insert(0, str(_fixture_dir))
    import make_fixture  # noqa: E402
    import build_site as bs  # noqa: E402

    ok_all = True

    with tempfile.TemporaryDirectory(prefix="cwfe-deploy-vercel-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        make_fixture.write_fixture_run_dir(run_dir)

        state = state_engine.ProjectState(run_dir)
        state.create_project(
            project_id=make_fixture.PROJECT_ID,
            client_slug="cwfe-u17-selftest",
            project_slug=make_fixture.PROJECT_ID,
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=25.0,
        )

        print("building fixture site (real npm/next toolchain)...")
        bs.build_site(run_dir, skip_toolchain=False, toolchain_timeout=600)

        adapter = VercelHostingAdapter(
            _SelfTestDeployTransport(), "fixture-token",
            poll_interval_seconds=0.0, sleep_fn=lambda *_: None,
        )

        preview_receipt = deploy_preview(run_dir, commit_sha="deadbeefcafefeed0001", adapter=adapter, project_name="cwfe-u17-selftest")
        print("preview deploy:", preview_receipt["status"], preview_receipt["url"])
        if preview_receipt["status"] != "ready":
            print("RESULT: FAIL (preview did not reach ready)")
            ok_all = False

        prod_receipt = deploy_production(run_dir, commit_sha="deadbeefcafefeed0001", adapter=adapter, project_name="cwfe-u17-selftest")
        print("production deploy:", prod_receipt["status"], prod_receipt["url"])
        if prod_receipt["status"] != "ready":
            print("RESULT: FAIL (production did not reach ready)")
            ok_all = False

        # Fail-closed: production must refuse a commit_sha that differs from
        # the one its own proven preview recorded.
        try:
            deploy_production(run_dir, commit_sha="0" * 40, adapter=adapter, project_name="cwfe-u17-selftest")
            print("RESULT: FAIL (production accepted a commit_sha that does not match the proven preview)")
            ok_all = False
        except DeploymentError as exc:
            print("commit-mismatch correctly refused:", str(exc)[:160])

        # Fail-closed: a readyState=ERROR terminal state must raise, and the
        # receipt recorded on disk must say "error", never "ready".
        failing_adapter = VercelHostingAdapter(
            _SelfTestDeployTransport(force_error=True), "fixture-token",
            poll_interval_seconds=0.0, sleep_fn=lambda *_: None,
        )
        try:
            deploy_preview(run_dir, commit_sha="deadbeefcafefeed0002", adapter=failing_adapter, project_name="cwfe-u17-selftest")
            print("RESULT: FAIL (an ERROR readyState was not raised)")
            ok_all = False
        except DeploymentError as exc:
            print("error readyState correctly raised:", str(exc)[:160])
            latest = state.latest_deployment_receipt("preview")
            if latest is None or latest["status"] != "error":
                print("RESULT: FAIL (the error deployment was not honestly recorded on disk)")
                ok_all = False

        # Blob storage adapter — real file bytes read from disk, round-tripped
        # through a fake PUT transport.
        blob_adapter = VercelBlobAdapter(_SelfTestBlobTransport(), "fixture-blob-token")
        blob_manifest = upload_scene_media_to_blob(run_dir, adapter=blob_adapter)
        print("blob upload assets:", len(blob_manifest["assets"]))
        if not blob_manifest["assets"]:
            print("RESULT: FAIL (no assets uploaded to blob storage)")
            ok_all = False
        for asset in blob_manifest["assets"]:
            if not asset["url"].startswith("https://"):
                print("RESULT: FAIL (a blob asset URL is not https)")
                ok_all = False

        # Restart survival: reconcile re-fetches from the host rather than
        # re-copying the stale local receipt.
        reconciled = reconcile_deployment(run_dir, "production", adapter=adapter)
        if not reconciled.get("restart_verified"):
            print("RESULT: FAIL (reconcile_deployment did not mark restart_verified)")
            ok_all = False
        if reconciled["status"] != "ready":
            print("RESULT: FAIL (reconciled production status was not 'ready')")
            ok_all = False

    print("RESULT:", "PASS" if ok_all else "FAIL")
    return ok_all


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--environment", choices=["preview", "production"], default=None)
    parser.add_argument("--commit-sha", default=None)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--upload-blob", action="store_true", help="Upload scene media to Blob storage instead of deploying the site.")
    parser.add_argument("--reconcile", action="store_true", help="Re-fetch the latest --environment deployment's status from the host instead of submitting a new deployment.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_FAIL

    if not args.run_dir or not args.run_dir.is_dir():
        print("USAGE ERROR: --run-dir is required and must exist (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE

    try:
        if args.upload_blob:
            manifest = upload_scene_media_to_blob(args.run_dir)
            print(json.dumps(manifest, indent=2))
            return EXIT_OK

        if not args.environment:
            print("USAGE ERROR: --environment is required unless --upload-blob or --self-test", file=sys.stderr)
            return EXIT_USAGE

        if args.reconcile:
            receipt = reconcile_deployment(args.run_dir, args.environment)
            print(json.dumps(receipt, indent=2))
            return EXIT_OK

        if args.environment == "preview":
            receipt = deploy_preview(args.run_dir, commit_sha=args.commit_sha, project_name=args.project_name)
        else:
            receipt = deploy_production(args.run_dir, commit_sha=args.commit_sha, project_name=args.project_name)
        print(json.dumps(receipt, indent=2))
        return EXIT_OK
    except (DeploymentError, ha.HostingAdapterError, ha.BlobStorageError, VercelTokenError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
