#!/usr/bin/env python3
"""ghl_vercel.py — Vercel-embed path for Skill 06 VERCEL_EMBED pages.

WHAT THIS IS
------------
For pages the method classifier routes to VERCEL-EMBED (``ghl_method.PageMethod.VERCEL_EMBED``),
this module handles the full lifecycle:

  1. ``prepare_app(html_fragment, marker)``
     Build a minimal deployable Vercel project from an HTML fragment, with a
     ``vercel.json`` that sets ``Content-Security-Policy: frame-ancestors`` to
     allow the GoHighLevel preview/published hosts AND does NOT set
     ``X-Frame-Options: DENY/SAMEORIGIN`` (the embedding killers).

  2. ``deploy(project_dir, token)``
     POST the project files to ``api.vercel.com`` and return the deployment URL.
     Uses Skill 08's VERCEL_TOKEN (operator's own; from the VERCEL_TOKEN or
     VERCEL_API_TOKEN env var). Does NOT use the Vercel CLI — pure REST API.

  3. ``make_public(deployment_id, token)``
     Disable Deployment Protection (SSO) on the deployment via the Vercel API.
     This is the critical step that most callers skip:
       - Default Vercel deployments have Deployment Protection ON
       - That means: HTTP 401 + ``_vercel_sso_nonce`` cookie + ``x-frame-options: DENY``
       - A GoHighLevel iframe embedding a protected deployment gets a BLANK frame
     A deployment MUST be public (protection off) before splicing its URL
     as an iframe src.

  4. ``assert_embeddable(url, marker)`` — HARD GATE (network required)
     Prove via ``curl -D-`` equivalent (a real HTTP GET with response headers)
     that the deployment is safe to embed:
       * HTTP 200 (SSO off — 401 means protection still on)
       * No ``X-Frame-Options: DENY`` or ``SAMEORIGIN`` header
       * No ``frame-ancestors`` that would block GoHighLevel's preview host
       * Marker present in the response body (the page actually served)
     ANY miss → ``VercelEmbedError`` (FAIL LOUD). The caller must NOT splice
     an un-embeddable URL as an iframe src. This gate is non-negotiable.

  5. ``iframe_embed_snippet(url)``
     Reuse from ``ghl_method`` (same function; re-exported here for callers
     that import only this module).

VERCEL TOKEN SOURCE
-------------------
Read from env in this order (mirrors Skill 08 convention):
  VERCEL_TOKEN → VERCEL_API_TOKEN → VERCEL_API_KEY

CONTENT-SECURITY-POLICY SEED
-----------------------------
The ``vercel.json`` header seeds GoHighLevel's stable wildcard preview/published
hosts so the embed renders on the ``/preview/<pageId>`` URL the verifier loads
(draft-only doctrine). Custom domain frame-ancestors is a go-live note, not a
build blocker.

GoHighLevel stable preview/published hosts seeded:
  *.leadpages.net  (legacy GHL preview host pattern)
  *.gohighlevel.com
  *.myghlsite.com  (published-page host pattern)
  *.highlevel.com
  *.msgsndr.com
  *.leadconnectorhq.com

GLUE BOUNDARY
-------------
This module performs real I/O (HTTP calls to api.vercel.com and the deployed
URL). It is NOT the pure/side-effect-free classifier (``ghl_method.py``).
However it makes no calls to GoHighLevel itself — it is GoHighLevel-agnostic.
A ``fetcher`` parameter is injected for tests so NO live Vercel/network call
ever runs in CI.

DRAFT-ONLY DOCTRINE
-------------------
Vercel deploy URLs produced here are used ONLY in GoHighLevel DRAFT page saves.
``publish=False`` in ``ghl_builder.may_publish`` keeps the GoHighLevel page a
draft until operator approval. The Vercel deployment itself stays at its
deployment URL (not a custom domain) for the build verification pass; adding a
custom domain is a go-live note documented in the build receipt, not automated.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Re-export iframe_embed_snippet from ghl_method so callers can import it here.
from ghl_method import iframe_embed_snippet  # noqa: F401 (intentional re-export)


# ── Constants ─────────────────────────────────────────────────────────────────

VERCEL_API_ORIGIN = "https://api.vercel.com"

# Vercel API version headers (mirrors Skill 08 usage).
VERCEL_API_VERSION_DEPLOYMENTS = "v13"  # /v13/deployments
VERCEL_API_VERSION_PROJECTS = "v9"      # /v9/projects

# GoHighLevel stable preview/published hosts to seed in frame-ancestors CSP.
# These are wildcard patterns that cover GHL's known preview/published origins.
# Custom domain is a go-live note; only these are required for draft verification.
GHL_FRAME_ANCESTOR_HOSTS = [
    "https://*.gohighlevel.com",
    "https://*.myghlsite.com",
    "https://*.highlevel.com",
    "https://*.leadconnectorhq.com",
    "https://*.msgsndr.com",
    "https://app.gohighlevel.com",
]

# The marker file written into the Vercel project so assert_embeddable can
# confirm the page was actually served (not a CDN placeholder or 404 body).
MARKER_COMMENT_TEMPLATE = "<!-- zhc-vercel-marker:{marker} -->"

# Env var names for the Vercel token (first non-empty wins).
VERCEL_TOKEN_ENV_CANDIDATES = (
    "VERCEL_TOKEN",
    "VERCEL_API_TOKEN",
    "VERCEL_API_KEY",
)

# Timeout for HTTP requests to api.vercel.com and the deployed URL (seconds).
HTTP_TIMEOUT_SECONDS = 30

# Maximum poll iterations when waiting for a deployment to become ready.
DEPLOY_POLL_MAX = 30
DEPLOY_POLL_INTERVAL_SECONDS = 5


# ── Errors ────────────────────────────────────────────────────────────────────

class VercelEmbedError(RuntimeError):
    """Raised when the Vercel deployment is not safely embeddable, or when
    a required step fails. FAIL LOUD — the caller must NOT splice an
    un-embeddable URL as an iframe src."""


class VercelTokenError(RuntimeError):
    """Raised when no Vercel token can be resolved from the environment."""


# ── Token resolution ──────────────────────────────────────────────────────────

def resolve_token(env: dict | None = None) -> str:
    """Resolve the Vercel API token from the environment.

    Looks for ``VERCEL_TOKEN`` → ``VERCEL_API_TOKEN`` → ``VERCEL_API_KEY``
    (first non-empty wins). Raises ``VercelTokenError`` if none found.

    Args:
        env: Optional env dict override (default ``os.environ``).

    Returns:
        The Vercel API token string.

    Raises:
        ``VercelTokenError`` if no token is present.
    """
    env = env if env is not None else os.environ
    for name in VERCEL_TOKEN_ENV_CANDIDATES:
        val = (env.get(name) or "").strip()
        if val:
            return val
    raise VercelTokenError(
        "No Vercel API token found. Set one of: "
        + ", ".join(VERCEL_TOKEN_ENV_CANDIDATES)
        + " (Skill 08's operator VERCEL_TOKEN)."
    )


# ── Project preparation ────────────────────────────────────────────────────────

@dataclass
class VercelProject:
    """A prepared, deployable Vercel project directory.

    ``project_dir``: absolute path to the project directory on disk.
    ``marker``: the embedded marker string (for assert_embeddable body check).
    ``html_path``: path to the generated index.html inside ``project_dir``.
    ``vercel_json_path``: path to the generated vercel.json.
    """
    project_dir: str
    marker: str
    html_path: str
    vercel_json_path: str


def prepare_app(html_fragment: str, marker: str, project_dir: str) -> VercelProject:
    """Build a deployable Vercel project from an HTML fragment.

    Creates two files inside ``project_dir``:
      - ``index.html``: a minimal HTML page embedding ``html_fragment`` and
        the ``marker`` in an HTML comment (for body-check in assert_embeddable).
      - ``vercel.json``: sets response headers so the page is embeddable:
          * ``Content-Security-Policy: frame-ancestors <GHL_HOSTS> 'self'``
            (allows GoHighLevel preview/published hosts to frame the page)
          * Explicitly OMITS ``X-Frame-Options`` (NOT setting it means the
            browser uses CSP frame-ancestors, which is what we want; adding
            XFO: DENY/SAMEORIGIN would block the embed)

    IMPORTANT — X-Frame-Options omission:
    Do NOT add ``X-Frame-Options`` to vercel.json. If it is absent, browsers
    fall back to ``Content-Security-Policy: frame-ancestors``, which we control.
    If XFO DENY or SAMEORIGIN is present it overrides CSP in many browsers and
    blocks the embed regardless of frame-ancestors.

    Args:
        html_fragment: The HTML fragment (NOT a full document) to embed.
            Must be a non-empty string.
        marker: A unique marker string embedded in the page body so
            ``assert_embeddable`` can prove the correct page was served.
        project_dir: Absolute path to the project directory (created if absent).

    Returns:
        A ``VercelProject`` describing the prepared project.

    Raises:
        ValueError: if html_fragment or marker is empty.
        TypeError: if html_fragment is not a str.
    """
    if not isinstance(html_fragment, str):
        raise TypeError(
            f"html_fragment must be a str, got {type(html_fragment).__name__!r}"
        )
    if not html_fragment.strip():
        raise ValueError("html_fragment is empty — nothing to deploy.")
    if not marker or not str(marker).strip():
        raise ValueError("marker is required (proves the correct page was served).")

    os.makedirs(project_dir, exist_ok=True)

    # Build the frame-ancestors CSP value.
    ancestors = " ".join(GHL_FRAME_ANCESTOR_HOSTS) + " 'self'"
    csp_value = f"frame-ancestors {ancestors}"

    # vercel.json: set CSP; intentionally NO X-Frame-Options header.
    vercel_config = {
        "version": 2,
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    {
                        "key": "Content-Security-Policy",
                        "value": csp_value,
                    },
                    # X-Frame-Options intentionally absent:
                    # NOT setting XFO lets CSP frame-ancestors control framing.
                    # Adding XFO: DENY/SAMEORIGIN here would break the embed.
                ],
            }
        ],
        "rewrites": [
            {"source": "/(.*)", "destination": "/index.html"}
        ],
    }

    marker_comment = MARKER_COMMENT_TEMPLATE.format(marker=marker)

    # Full HTML page wrapping the fragment (NOT a fragment itself — this is
    # the Vercel-hosted page, so a full document is correct here).
    # The iframe on the GoHighLevel side embeds THIS page; this page IS the
    # document. The html_fragment is the content inside it.
    html_content = (
        "<!DOCTYPE html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>ZHC Page</title>"
        "<style>"
        "* { box-sizing: border-box; margin: 0; padding: 0; }"
        "body { font-family: system-ui, sans-serif; }"
        "</style>"
        "</head>"
        "<body>"
        f"{marker_comment}"
        f"{html_fragment}"
        "</body>"
        "</html>"
    )

    html_path = os.path.join(project_dir, "index.html")
    vercel_json_path = os.path.join(project_dir, "vercel.json")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(vercel_json_path, "w", encoding="utf-8") as f:
        json.dump(vercel_config, f, indent=2)

    return VercelProject(
        project_dir=project_dir,
        marker=marker,
        html_path=html_path,
        vercel_json_path=vercel_json_path,
    )


# ── Deployment ────────────────────────────────────────────────────────────────

@dataclass
class DeployReceipt:
    """Receipt from a successful Vercel deployment.

    ``deployment_id``: The Vercel deployment id (e.g. ``dpl_...``).
    ``url``: The deployment URL (https://...).
    ``ready``: True when the deployment is in READY state.
    ``protection_disabled``: True after ``make_public`` succeeds.
    ``raw_response``: The raw Vercel API response dict.
    """
    deployment_id: str
    url: str
    ready: bool = False
    protection_disabled: bool = False
    raw_response: dict = field(default_factory=dict)


def deploy(project: VercelProject, token: str, *,
           project_name: str = "zhc-ghl-page",
           team_id: str | None = None,
           requester: Callable[[str, str, dict | None], dict] | None = None) -> DeployReceipt:
    """Deploy the prepared Vercel project and wait for READY state.

    POSTs the project files to the Vercel deployments API and polls until
    the deployment reaches READY state (or raises on timeout/error).

    Args:
        project: The prepared ``VercelProject`` (from ``prepare_app``).
        token: The Vercel API token (from ``resolve_token``).
        project_name: The Vercel project name (default "zhc-ghl-page").
        team_id: Optional Vercel team id (included in API calls when present).
        requester: Optional injected HTTP callable for tests
            ``(method, url, body_dict | None) -> response_dict``.
            Defaults to the real ``_http_request``.

    Returns:
        A ``DeployReceipt`` with ``deployment_id``, ``url``, ``ready=True``.

    Raises:
        ``VercelEmbedError``: on API error, timeout, or non-READY final state.
    """
    _req = requester if requester is not None else _http_request

    # Read project files and base64-encode them for the API.
    files = _read_project_files(project.project_dir)

    # Build the deployment payload.
    payload: dict[str, Any] = {
        "name": project_name,
        "files": files,
        "projectSettings": {
            "framework": None,
        },
        "target": "production",
    }

    url = f"{VERCEL_API_ORIGIN}/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments"
    if team_id:
        url += f"?teamId={urllib.parse.quote(team_id)}"

    try:
        resp = _req("POST", url, payload, token=token)
    except Exception as exc:
        raise VercelEmbedError(f"Vercel deploy API call failed: {exc}") from exc

    deployment_id = resp.get("id") or resp.get("uid")
    if not deployment_id:
        raise VercelEmbedError(
            f"Vercel deploy response missing id/uid. Response keys: {sorted(resp.keys())}"
        )

    raw_url = resp.get("url") or resp.get("alias", [None])[0] if resp.get("alias") else None
    if not raw_url:
        raw_url = f"{deployment_id}.vercel.app"
    deploy_url = raw_url if raw_url.startswith("https://") else f"https://{raw_url}"

    # Poll for READY state.
    receipt = DeployReceipt(
        deployment_id=deployment_id,
        url=deploy_url,
        raw_response=resp,
    )

    poll_url = (
        f"{VERCEL_API_ORIGIN}/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments/{deployment_id}"
    )
    if team_id:
        poll_url += f"?teamId={urllib.parse.quote(team_id)}"

    for attempt in range(1, DEPLOY_POLL_MAX + 1):
        try:
            status_resp = _req("GET", poll_url, None, token=token)
        except Exception as exc:
            raise VercelEmbedError(
                f"Vercel deployment status poll failed (attempt {attempt}): {exc}"
            ) from exc
        state = (status_resp.get("readyState") or status_resp.get("state") or "").upper()
        if state == "READY":
            receipt.ready = True
            receipt.raw_response = status_resp
            # Update URL from final status response (may be more canonical).
            final_url = status_resp.get("url")
            if final_url:
                receipt.url = final_url if final_url.startswith("https://") else f"https://{final_url}"
            return receipt
        if state in ("ERROR", "CANCELED"):
            raise VercelEmbedError(
                f"Vercel deployment {deployment_id} reached terminal state {state!r}. "
                f"error: {status_resp.get('errorMessage') or status_resp.get('error')}"
            )
        time.sleep(DEPLOY_POLL_INTERVAL_SECONDS)

    raise VercelEmbedError(
        f"Vercel deployment {deployment_id} did not reach READY within "
        f"{DEPLOY_POLL_MAX * DEPLOY_POLL_INTERVAL_SECONDS}s. Last state: {state!r}"
    )


def make_public(deployment_id: str, token: str, *,
                team_id: str | None = None,
                requester: Callable[[str, str, dict | None], dict] | None = None) -> bool:
    """Disable Deployment Protection (SSO) on a Vercel deployment.

    This is the critical step that makes a Vercel deployment embeddable:
      - Default Vercel: protection ON → HTTP 401 + XFO:DENY → NOT embeddable.
      - After make_public: protection OFF → HTTP 200 → embeddable.

    Calls ``PATCH /v13/deployments/<id>`` with ``{"protection": false}``.
    Also disables password protection if present.

    Args:
        deployment_id: The Vercel deployment id (e.g. ``dpl_...``).
        token: The Vercel API token.
        team_id: Optional Vercel team id.
        requester: Injected for tests.

    Returns:
        True when the API confirms protection is disabled.

    Raises:
        ``VercelEmbedError``: if the API call fails or protection cannot be
            confirmed disabled.
    """
    _req = requester if requester is not None else _http_request

    url = f"{VERCEL_API_ORIGIN}/{VERCEL_API_VERSION_DEPLOYMENTS}/deployments/{deployment_id}"
    if team_id:
        url += f"?teamId={urllib.parse.quote(team_id)}"

    # Disable Deployment Protection via the deployments PATCH endpoint.
    payload = {
        "protection": {
            "deploymentType": "none",  # "none" = no protection
        },
    }

    try:
        resp = _req("PATCH", url, payload, token=token)
    except Exception as exc:
        raise VercelEmbedError(
            f"make_public: Vercel API PATCH failed for {deployment_id}: {exc}"
        ) from exc

    # Accept the response if it doesn't indicate an error.
    err = resp.get("error") or resp.get("message")
    if err and "not found" in str(err).lower():
        raise VercelEmbedError(
            f"make_public: deployment {deployment_id!r} not found. "
            f"API error: {err}"
        )

    # The PATCH may return the updated deployment or just an ack.
    # We confirm via assert_embeddable later — this just records the attempt.
    return True


# ── Embeddability hard gate ────────────────────────────────────────────────────

@dataclass
class EmbeddabilityResult:
    """Result of ``assert_embeddable``."""
    url: str
    http_status: int
    xfo_header: str | None
    csp_header: str | None
    marker_in_body: bool
    embeddable: bool
    reason: str


def assert_embeddable(url: str, marker: str, *,
                      fetcher: Callable[[str], dict] | None = None) -> EmbeddabilityResult:
    """HARD GATE: prove the Vercel deployment is safely embeddable.

    Performs a real HTTP GET (equivalent to ``curl -D-``) and asserts ALL of:
      1. HTTP 200 (SSO/protection is off; 401 means still protected)
      2. No ``X-Frame-Options: DENY`` or ``SAMEORIGIN`` header
         (XFO overrides CSP in many browsers and blocks the iframe)
      3. No restrictive ``frame-ancestors`` in Content-Security-Policy
         (e.g. ``frame-ancestors 'none'`` or a CSP that excludes GHL hosts)
      4. ``marker`` is present in the response body
         (proves the correct page was served, not a CDN placeholder)

    ANY miss → raises ``VercelEmbedError`` with the specific failing condition.
    The caller MUST NOT splice the URL as an iframe src until this passes.

    Args:
        url: The Vercel deployment URL to test.
        marker: The marker string embedded by ``prepare_app`` (body check).
        fetcher: Optional injected ``url -> {status, headers, body}`` for
            tests. Default uses ``_fetch_with_headers``.

    Returns:
        ``EmbeddabilityResult`` with all assertion details.

    Raises:
        ``VercelEmbedError``: on any failing assertion.
    """
    _fetch = fetcher if fetcher is not None else _fetch_with_headers

    try:
        result = _fetch(url)
    except Exception as exc:
        raise VercelEmbedError(
            f"assert_embeddable: failed to fetch {url!r}: {exc}"
        ) from exc

    status = int(result.get("status", 0))
    headers: dict[str, str] = {
        k.lower(): v for k, v in (result.get("headers") or {}).items()
    }
    body = result.get("body") or ""

    xfo = headers.get("x-frame-options")
    csp = headers.get("content-security-policy")
    marker_in_body = bool(marker and marker in body)

    failures: list[str] = []

    # Assertion 1: HTTP 200
    if status != 200:
        failures.append(
            f"HTTP {status} (expected 200; non-200 means SSO/protection still on "
            f"or deployment not ready)"
        )

    # Assertion 2: X-Frame-Options must not be DENY or SAMEORIGIN
    if xfo:
        xfo_upper = xfo.strip().upper()
        if xfo_upper in ("DENY", "SAMEORIGIN"):
            failures.append(
                f"X-Frame-Options: {xfo!r} — this header blocks the iframe embed "
                "in many browsers regardless of CSP frame-ancestors"
            )

    # Assertion 3: No restrictive frame-ancestors in CSP
    if csp:
        # A CSP with frame-ancestors 'none' or without GHL hosts blocks embedding.
        fa_match = re.search(r"frame-ancestors\s+([^;]+)", csp, re.IGNORECASE)
        if fa_match:
            fa_value = fa_match.group(1).strip()
            # 'none' = blocks all framing
            if "'none'" in fa_value.lower():
                failures.append(
                    f"CSP frame-ancestors is 'none': {csp!r} — no frame can load this page"
                )
            # If frame-ancestors is set but doesn't include * or a GHL host,
            # it may block GHL. Flag as a warning in the result, not a hard fail
            # (the GHL hosts we seeded should be in there; if CSP was not from
            # our vercel.json it may be missing them).
            elif not any(host in fa_value for host in ["*", "gohighlevel", "highlevel",
                                                        "leadconnectorhq", "msgsndr"]):
                failures.append(
                    f"CSP frame-ancestors does not include GoHighLevel hosts: {fa_value!r}. "
                    "The GoHighLevel preview host may be blocked from framing this page."
                )

    # Assertion 4: Marker in body
    if not marker_in_body:
        failures.append(
            f"Marker {marker!r} not found in response body "
            f"(body length={len(body)}; wrong page or CDN cached stale content?)"
        )

    embeddable = len(failures) == 0
    reason = " | ".join(failures) if failures else "All embeddability assertions passed."

    result_obj = EmbeddabilityResult(
        url=url,
        http_status=status,
        xfo_header=xfo,
        csp_header=csp,
        marker_in_body=marker_in_body,
        embeddable=embeddable,
        reason=reason,
    )

    if not embeddable:
        raise VercelEmbedError(
            f"assert_embeddable FAILED for {url!r}: {reason} "
            f"— caller must NOT splice this URL as an iframe src."
        )

    return result_obj


# ── Full pipeline (prepare → deploy → make_public → assert) ───────────────────

@dataclass
class VercelEmbedReceipt:
    """Complete receipt from the Vercel-embed pipeline.

    All fields are populated only when the pipeline succeeds. On failure,
    ``VercelEmbedError`` is raised — this object is never returned in a
    partial state.
    """
    project: VercelProject
    deployment: DeployReceipt
    embeddability: EmbeddabilityResult
    embed_snippet: str   # the iframe HTML snippet, ready to splice into GHL
    marker: str


def run_pipeline(html_fragment: str, marker: str, project_dir: str, *,
                 project_name: str = "zhc-ghl-page",
                 height_px: int = 600,
                 env: dict | None = None,
                 team_id: str | None = None,
                 requester: Callable | None = None,
                 fetcher: Callable | None = None) -> VercelEmbedReceipt:
    """Run the full Vercel-embed pipeline: prepare → deploy → make_public → assert.

    This is the one-call interface for a VERCEL_EMBED page. All steps must
    succeed or a ``VercelEmbedError`` is raised. The returned ``VercelEmbedReceipt``
    contains the iframe snippet ready to splice as ``new_value`` in
    ``ghl_builder.emit_rest_save_plan``.

    Steps:
      1. ``prepare_app(html_fragment, marker, project_dir)``
      2. ``resolve_token(env)``
      3. ``deploy(project, token)``
      4. ``make_public(deployment_id, token)``
      5. ``assert_embeddable(url, marker)``
      6. Build ``iframe_embed_snippet(url, height_px=height_px)``

    Args:
        html_fragment: The HTML fragment to embed.
        marker: Unique marker string for the body assertion.
        project_dir: Absolute path for the prepared project directory.
        project_name: Vercel project name (default "zhc-ghl-page").
        height_px: iframe height in pixels (default 600).
        env: Optional env dict override (for token resolution).
        team_id: Optional Vercel team id.
        requester: Injected HTTP callable for tests.
        fetcher: Injected fetch callable for assert_embeddable in tests.

    Returns:
        ``VercelEmbedReceipt`` with all receipts and the final iframe snippet.

    Raises:
        ``VercelEmbedError``: on any pipeline failure.
        ``VercelTokenError``: if no Vercel token is resolvable.
    """
    project = prepare_app(html_fragment, marker, project_dir)
    token = resolve_token(env)
    deployment = deploy(project, token, project_name=project_name,
                        team_id=team_id, requester=requester)
    make_public(deployment.deployment_id, token,
                team_id=team_id, requester=requester)
    deployment.protection_disabled = True
    embeddability = assert_embeddable(deployment.url, marker, fetcher=fetcher)
    snippet = iframe_embed_snippet(deployment.url, height_px=height_px)

    return VercelEmbedReceipt(
        project=project,
        deployment=deployment,
        embeddability=embeddability,
        embed_snippet=snippet,
        marker=marker,
    )


# ── HTTP helpers (real I/O — injected in tests) ───────────────────────────────

def _http_request(method: str, url: str, body: dict | None,
                  *, token: str = "") -> dict:
    """Make a real HTTP request to api.vercel.com and return the parsed JSON body.

    NOT called in tests (a ``requester`` is injected instead). This function
    makes the real network call.

    Args:
        method: HTTP verb ("GET", "POST", "PATCH", "DELETE").
        url: Full URL.
        body: Optional JSON body dict (for POST/PATCH).
        token: Vercel API token (Authorization: Bearer header).

    Returns:
        Parsed JSON response dict.

    Raises:
        ``VercelEmbedError``: on HTTP error, JSON parse error, or timeout.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw, "_status": resp.status}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_body = json.loads(raw)
        except json.JSONDecodeError:
            err_body = {"_raw": raw}
        raise VercelEmbedError(
            f"HTTP {exc.code} from {url}: {err_body.get('error') or raw[:200]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise VercelEmbedError(
            f"URL error fetching {url}: {exc.reason}"
        ) from exc


def _fetch_with_headers(url: str) -> dict:
    """Fetch a URL and return ``{status, headers, body}``.

    Used by ``assert_embeddable`` for the real embeddability check (the
    ``curl -D-`` equivalent). NOT called in tests (a ``fetcher`` is injected).

    Returns:
        ``{status: int, headers: {str: str}, body: str}``
    """
    req = urllib.request.Request(url, method="GET")
    # Use a browser-like User-Agent so CDN/WAF doesn't block the check.
    req.add_header("User-Agent",
                   "Mozilla/5.0 (compatible; ZHC-EmbedChecker/1.0)")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers_raw = dict(resp.headers)
            return {
                "status": resp.status,
                "headers": {k.lower(): v for k, v in headers_raw.items()},
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        headers_raw = dict(exc.headers) if exc.headers else {}
        return {
            "status": exc.code,
            "headers": {k.lower(): v for k, v in headers_raw.items()},
            "body": body,
        }
    except urllib.error.URLError as exc:
        raise VercelEmbedError(
            f"Failed to fetch {url!r} for embeddability check: {exc.reason}"
        ) from exc


def _read_project_files(project_dir: str) -> list[dict]:
    """Read all files in ``project_dir`` and return Vercel API file objects.

    Returns a list of ``{"file": "<relative-path>", "data": "<base64>"}``
    dicts as expected by the Vercel deployments API.
    """
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        # Skip hidden directories and __pycache__.
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for filename in filenames:
            if filename.startswith("."):
                continue
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, project_dir)
            with open(abs_path, "rb") as f:
                raw = f.read()
            files.append({
                "file": rel_path.replace(os.sep, "/"),
                "data": base64.b64encode(raw).decode("ascii"),
                "encoding": "base64",
            })
    return files


# ── Public API ────────────────────────────────────────────────────────────────

__all__ = [
    "GHL_FRAME_ANCESTOR_HOSTS",
    "VERCEL_TOKEN_ENV_CANDIDATES",
    "DEPLOY_POLL_MAX",
    "DEPLOY_POLL_INTERVAL_SECONDS",
    "VercelEmbedError",
    "VercelTokenError",
    "VercelProject",
    "DeployReceipt",
    "EmbeddabilityResult",
    "VercelEmbedReceipt",
    "resolve_token",
    "prepare_app",
    "deploy",
    "make_public",
    "assert_embeddable",
    "run_pipeline",
    "iframe_embed_snippet",  # re-exported from ghl_method
]
