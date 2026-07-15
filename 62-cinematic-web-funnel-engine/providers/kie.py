#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kie.py — the Kie.ai concrete MediaProvider adapter (Skill 62, U5).

Implements spec §10.1's mandate: "Implement providers/kie.py first. Reuse the
existing canonical Kie setup, secret resolution, callback infrastructure, and
image/video adapters where possible. Do not create a third divergent Kie
client if the repository already has two that must remain in lockstep."

This module is SKILL-LOCAL (62-cinematic-web-funnel-engine/providers/) and
has NO dependency on OpenMontage's ``tools.base_tool`` — unlike
``47-movie-producer/kie-adapters/tools/{graphics,video}/kie_*.py`` (the
OpenMontage-installed adapters, extended for ``bytedance/seedance-1.5-pro``
frame pinning in this same U5 unit), which only import inside a client's
cloned OpenMontage tree. Skill 62 must run standalone. This module is kept
IN LOCKSTEP with those two adapters by construction: identical endpoints
(``/api/v1/jobs/createTask`` + ``/api/v1/jobs/recordInfo``), identical
request-body shapes, and the identical ``resultJson``-is-a-JSON-encoded-
STRING decode contract (see ``_decode_result_json`` below) — never a
divergent third client (ADR per spec §10.1).

Every model is addressed through ``providers.base.ModelRegistry`` by its
registry ``model_id`` — this file NEVER hardcodes a provider wire slug or a
price literal (ADR-8; the one exception, by design, is the two fully-
qualified Kie HTTP endpoints below, which are transport plumbing, not a
model identity).

CALLBACK RELAY WIRING (spec §10.1, manifest ``delegation_seams.callback_relay``,
Skill 62 U5 directive): this module also ports the ``46-kie-callback-relay``
contract to Python so a Skill-62 run can (a) build an outgoing
``callBackUrl`` for a submitted task using the SAME per-client HMAC-SHA256
derivation as ``46-kie-callback-relay/kie-slide-submitter.js``, (b) pull a
verified result from the Worker's ``/kv-read`` endpoint the same way
``46-kie-callback-relay/box-kv-poller.js`` does, and (c) independently verify
a Kie webhook's own HMAC-SHA256 signature — the SAME algorithm the Worker
enforces (``46-kie-callback-relay/worker/src/index.js`` ``verifyKieSignature``;
documented in ``07-kie-setup/kie-setup-full.md`` "Callback and webhook
verification"): ``HMAC-SHA256(taskId + "." + timestampSeconds,
webhookHmacKey)``, base64-encoded, compared in CONSTANT TIME.

SECRETS BY NAME ONLY: every secret below (``KIE_API_KEY``,
``KIE_CALLBACK_HMAC_KEY``, ``KVREAD_TOKEN``, the Kie webhook HMAC key, a
``perTaskSecret``) is resolved from the environment by variable NAME, or
passed in by the caller as an opaque value. This module never logs, prints,
or embeds a secret VALUE in an exception message, a manifest, or a receipt —
only the env-var NAME (see ``_resolve_secret``) or a boolean
found/not-found.

NO LIVE/PAID CALLS: build+test happen against MOCKED Kie API fixtures
(spec §19.2 "Kie adapter against mocked API fixtures") via the injectable
``KieTransport`` seam — ``RequestsTransport`` is the only implementation that
ever touches the network, and it is never invoked by this unit's tests.

stdlib + optional ``requests`` (imported lazily, only inside
``RequestsTransport``, exactly like the OpenMontage adapters) — importing
this module never requires ``requests`` to be installed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .base import (
    AssetUploadRequest,
    CostEstimate,
    ImageGenerationRequest,
    MediaProvider,
    ModelRegistry,
    ProviderTaskError,
    TaskHandle,
    VideoGenerationRequest,
)

# ---------------------------------------------------------------------------
# Kie.ai API constants (kept in lockstep with 47-movie-producer/kie-adapters/
# tools/{graphics,video}/kie_*.py — same endpoints, same body shapes).
# ---------------------------------------------------------------------------
_KIE_API_BASE = "https://api.kie.ai"
_CREATE_TASK_URL = f"{_KIE_API_BASE}/api/v1/jobs/createTask"
_RECORD_INFO_URL = f"{_KIE_API_BASE}/api/v1/jobs/recordInfo"
# Base64 reference-image upload endpoint (verified 07-kie-setup/EXAMPLES.md
# Example 7; identical to kie_image.py's KieImage._upload_local_image).
_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-base64-upload"

_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 600  # 10 min ceiling; matches box-kv-poller.js's fallback ceiling

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _decode_result_json(raw: Any) -> Dict[str, Any]:
    """Normalise Kie's ``resultJson`` field into a parsed dict.

    Kie's poll endpoint (``/api/v1/jobs/recordInfo``) returns ``resultJson``
    as a JSON-ENCODED STRING, not an already-parsed object (confirmed live
    against api.kie.ai — see ``47-movie-producer/kie-adapters/tools/video/
    kie_video.py``'s identically-named helper, whose fix this mirrors
    exactly so both stay in lockstep). Defensive contract: str -> json.loads
    (``{}`` on failure); dict -> used as-is; anything else -> ``{}``.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, dict):
        return raw
    return {}


def _resolve_secret(env_var_name: str, *, required: bool = True) -> Optional[str]:
    """Resolve a secret VALUE from the environment by NAME only.

    Never logged, never embedded in an exception message — only the env-var
    NAME may appear in any error text this raises."""
    value = os.environ.get(env_var_name)
    if required and not value:
        raise ProviderTaskError(
            f"kie provider: {env_var_name} is not set in the environment "
            "(secret resolved by NAME only; the value itself is never logged)"
        )
    return value


# ---------------------------------------------------------------------------
# Transport seam — the ONLY place that ever touches the network. Tests inject
# a fake KieTransport against mocked fixtures (spec §19.2); RequestsTransport
# is never exercised by this unit's test suite.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json_body: Dict[str, Any]
    content: bytes = b""


class KieTransport(ABC):
    """Everything KieProvider needs to talk to Kie.ai / the callback relay
    Worker, abstracted so tests never make a real HTTP call."""

    @abstractmethod
    def post_json(
        self, url: str, *, headers: Dict[str, str], body: Dict[str, Any], timeout: float
    ) -> HttpResponse:
        raise NotImplementedError

    @abstractmethod
    def get_json(
        self,
        url: str,
        *,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]],
        timeout: float,
    ) -> HttpResponse:
        raise NotImplementedError

    @abstractmethod
    def download(self, url: str, *, timeout: float) -> bytes:
        raise NotImplementedError


def _safe_json(resp: Any) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


class RequestsTransport(KieTransport):
    """Default transport. Lazily imports ``requests`` inside each method
    (mirrors the existing OpenMontage adapters' lazy-import style) so this
    module imports cleanly even in an environment without ``requests``
    installed until a real call is actually made. NEVER used by this unit's
    tests — see the MOCKED ``KieTransport`` fakes in
    ``tests/unit/test_providers_kie.py``."""

    def post_json(self, url, *, headers, body, timeout):
        import requests

        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json(resp))

    def get_json(self, url, *, headers, params, timeout):
        import requests

        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        return HttpResponse(status_code=resp.status_code, json_body=_safe_json(resp))

    def download(self, url, *, timeout):
        import requests

        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# 46-kie-callback-relay wiring — Python port of kie-slide-submitter.js's
# callBackUrl construction, box-kv-poller.js's /kv-read pull, and
# worker/src/index.js's verifyKieSignature. Kept algorithmically identical so
# a Python-submitted task is indistinguishable, on the wire, from a
# JS-submitted one.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallbackTicket:
    """Everything needed to build one task's Kie ``callBackUrl`` and to
    later authenticate a ``/kv-read`` pull of its result. Mirrors
    ``46-kie-callback-relay/kie-slide-submitter.js``'s per-task fields
    (``submitId``, ``perTaskSecret``) exactly."""

    submit_id: str
    per_task_secret: str
    callback_url: str


def generate_submit_id() -> str:
    """128-bit random hex ``submitId`` (fix A, 46-kie-callback-relay
    DESIGN.md) — never a predictable/guessable label."""
    return secrets.token_hex(16)


def generate_per_task_secret() -> str:
    """256-bit random per-task secret (mirrors kie-slide-submitter.js
    ``crypto.randomBytes(32).toString('hex')``)."""
    return secrets.token_hex(32)


def _hmac_hex(message: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def build_callback_ticket(
    *, worker_base_url: str, client_slug: str, callback_hmac_key: str
) -> CallbackTicket:
    """Build a fresh ``callBackUrl`` for one Kie task, per the
    46-kie-callback-relay contract (``kie-slide-submitter.js``):

      callbackValidator (``s=``)  = HMAC-SHA256(clientSlug + ":" + submitId, callbackHmacKey)
      perTaskSecretHmac  (``h=``) = HMAC-SHA256(perTaskSecret, callbackHmacKey)

    ``callback_hmac_key`` is THIS CLIENT'S per-client derived key (fix F) —
    the value provisioned onto the box per ``46-kie-callback-relay/DEPLOY.md``,
    NEVER the fleet master key (the master never leaves the Worker). Nothing
    secret appears in the returned URL (fixes C+D): ``s=`` and ``h=`` are
    both HMACs, never a raw secret.
    """
    submit_id = generate_submit_id()
    per_task_secret = generate_per_task_secret()
    callback_validator = _hmac_hex(f"{client_slug}:{submit_id}", callback_hmac_key)
    per_task_secret_hmac = _hmac_hex(per_task_secret, callback_hmac_key)
    url = (
        f"{worker_base_url.rstrip('/')}/cb"
        f"?c={quote(client_slug, safe='')}"
        f"&j={quote(submit_id, safe='')}"
        f"&s={callback_validator}"
        f"&h={per_task_secret_hmac}"
    )
    return CallbackTicket(submit_id=submit_id, per_task_secret=per_task_secret, callback_url=url)


def verify_kie_webhook_signature(
    *, task_id: str, timestamp_seconds: str, signature_b64: str, webhook_hmac_key: str
) -> bool:
    """Verify a Kie webhook callback's HMAC-SHA256 signature.

    Algorithm (07-kie-setup/kie-setup-full.md "Callback and webhook
    verification"; identical to ``46-kie-callback-relay/worker/src/index.js``
    ``verifyKieSignature``, ported to Python so Skill 62 can independently
    verify a callback's authenticity):

        HMAC-SHA256(taskId + "." + timestampSeconds, webhookHmacKey),
        base64-encoded, compared in CONSTANT TIME.

    ``webhook_hmac_key`` is the ``webhookHmacKey`` from https://kie.ai/settings
    (env var name ``KIE_WEBHOOK_HMAC_KEY`` in this fleet's convention — the
    VALUE is passed in by the caller, never read from disk/env by this pure
    function, so it stays trivially testable against known vectors).

    Returns ``False`` — never raises — on any malformed/missing input; a bad
    or absent signature is always simply "not verified".
    """
    if not task_id or not timestamp_seconds or not signature_b64 or not webhook_hmac_key:
        return False
    message = f"{task_id}.{timestamp_seconds}".encode("utf-8")
    digest = hmac.new(webhook_hmac_key.encode("utf-8"), message, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(digest).decode("ascii")
    try:
        return hmac.compare_digest(expected_b64, signature_b64)
    except TypeError:
        return False


def kv_read(
    transport: KieTransport,
    *,
    worker_base_url: str,
    client_slug: str,
    submit_id: str,
    kv_read_token: str,
    per_task_secret: str,
    timeout: float = 15,
) -> Optional[Dict[str, Any]]:
    """Box-side pull of a verified callback result from the
    46-kie-callback-relay Worker's ``/kv-read`` endpoint (ports
    ``box-kv-poller.js``'s ``_pollKv``).

    Sends ``Authorization: Bearer <kv_read_token>`` and the RAW
    ``per_task_secret`` preimage in the ``X-Kie-Preimage`` request header
    (never a query param — fix G; query params land in edge access logs on
    every poll). Returns the parsed ``result`` object when found, or
    ``None`` when not-yet-available / unauthorized / not-found (never
    raises — mirrors the JS poller's non-fatal retry posture, since this is
    called in a polling loop).

    Fix 34 (confused-deputy defense, mirrored from ``box-kv-poller.js``
    ``_validatePerTaskSecret``): a result whose ``submitId`` does not
    EXACTLY match the one requested is treated as not-found, never accepted.
    """
    url = (
        f"{worker_base_url.rstrip('/')}/kv-read"
        f"?c={quote(client_slug, safe='')}"
        f"&j={quote(submit_id, safe='')}"
    )
    headers = {
        "Authorization": f"Bearer {kv_read_token}",
        "X-Kie-Preimage": per_task_secret,
    }
    resp = transport.get_json(url, headers=headers, params=None, timeout=timeout)
    if resp.status_code in (401, 403, 404):
        return None
    body = resp.json_body or {}
    if not body.get("found"):
        return None
    result = body.get("result") or {}
    if result.get("submitId") != submit_id:
        return None
    return result


# ---------------------------------------------------------------------------
# KieProvider — the concrete MediaProvider (spec §10.1)
# ---------------------------------------------------------------------------


class KieProvider(MediaProvider):
    """The Kie.ai concrete ``MediaProvider`` for the Cinematic and Web
    Funnel Engine. Every model slug/price is resolved through a
    ``ModelRegistry`` (never hardcoded, ADR-8); every secret is resolved by
    environment-variable NAME (never a literal value in this file).
    """

    name = "kie"

    def __init__(
        self,
        *,
        registry: Optional[ModelRegistry] = None,
        transport: Optional[KieTransport] = None,
        api_key_env: str = "KIE_API_KEY",
        callback_worker_url_env: str = "KIE_KV_BASE_URL",
        callback_hmac_key_env: str = "KIE_CALLBACK_HMAC_KEY",
        kv_read_token_env: str = "KVREAD_TOKEN",
        client_slug_env: str = "KIE_CLIENT_SLUG",
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.transport: KieTransport = transport or RequestsTransport()
        self._api_key_env = api_key_env
        self._callback_worker_url_env = callback_worker_url_env
        self._callback_hmac_key_env = callback_hmac_key_env
        self._kv_read_token_env = kv_read_token_env
        self._client_slug_env = client_slug_env
        # task_id -> CallbackTicket, for tasks submitted WITH a callback
        # attached by this instance. Purely in-process bookkeeping; nothing
        # here is persisted (a real run persists via the project's own
        # cost-ledger/state-engine artifacts, a later unit's concern).
        self._callback_tickets: Dict[str, CallbackTicket] = {}

    # -- secrets -----------------------------------------------------------

    def _api_key(self) -> str:
        return _resolve_secret(self._api_key_env)  # type: ignore[return-value]

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    def callback_enabled(self) -> bool:
        """True when every env var needed to attach a Kie callBackUrl to a
        submitted task is present. Checks PRESENCE only (by name) — never
        reads/logs the values here."""
        return bool(
            os.environ.get(self._callback_worker_url_env)
            and os.environ.get(self._callback_hmac_key_env)
            and os.environ.get(self._client_slug_env)
        )

    def _new_callback_ticket(self) -> CallbackTicket:
        worker_url = _resolve_secret(self._callback_worker_url_env)
        client_slug = _resolve_secret(self._client_slug_env)
        hmac_key = _resolve_secret(self._callback_hmac_key_env)
        return build_callback_ticket(
            worker_base_url=worker_url,  # type: ignore[arg-type]
            client_slug=client_slug,  # type: ignore[arg-type]
            callback_hmac_key=hmac_key,  # type: ignore[arg-type]
        )

    def _maybe_attach_callback(
        self, body: Dict[str, Any], *, use_callback: Optional[bool]
    ) -> Optional[CallbackTicket]:
        enabled = self.callback_enabled() if use_callback is None else use_callback
        if not enabled:
            return None
        ticket = self._new_callback_ticket()
        body["callBackUrl"] = ticket.callback_url
        return ticket

    def poll_callback_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Pull ``task_id``'s verified result from the 46-kie-callback-relay
        Worker's ``/kv-read`` endpoint. Returns ``None`` when this instance
        never attached a callback to ``task_id``, when callback wiring is
        not fully configured, or when the Worker reports not-yet-available/
        unauthorized/not-found — never raises (this is a poll)."""
        ticket = self._callback_tickets.get(task_id)
        if ticket is None:
            return None
        worker_url = os.environ.get(self._callback_worker_url_env)
        client_slug = os.environ.get(self._client_slug_env)
        kv_read_token = os.environ.get(self._kv_read_token_env)
        if not (worker_url and client_slug and kv_read_token):
            return None
        return kv_read(
            self.transport,
            worker_base_url=worker_url,
            client_slug=client_slug,
            submit_id=ticket.submit_id,
            kv_read_token=kv_read_token,
            per_task_secret=ticket.per_task_secret,
        )

    # -- MediaProvider interface --------------------------------------------

    def upload_asset(self, request: AssetUploadRequest) -> str:
        """Upload a local file via Kie's authenticated base64-upload
        endpoint (identical endpoint/shape to
        ``kie_image.py KieImage._upload_local_image``) and return a
        publicly reachable Kie-hosted URL."""
        path = Path(request.path)
        if not path.exists():
            raise ProviderTaskError(f"kie provider: local asset not found: {path}")
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        body = {
            "base64Data": f"data:{mime};base64,{b64}",
            "uploadPath": f"images/cinematic-web-funnel-engine/{request.purpose}",
            "fileName": path.name,
        }
        resp = self.transport.post_json(
            _UPLOAD_URL,
            headers={"Authorization": f"Bearer {self._api_key()}"},
            body=body,
            timeout=60,
        )
        data = resp.json_body.get("data") or {}
        url = data.get("downloadUrl") or resp.json_body.get("downloadUrl") or data.get("url")
        if not url or not str(url).startswith("http"):
            raise ProviderTaskError(
                f"kie provider: upload_asset returned no usable URL: {resp.json_body}"
            )
        return str(url)

    def generate_image(
        self, request: ImageGenerationRequest, *, use_callback: Optional[bool] = None
    ) -> TaskHandle:
        slug = self.registry.slug_for(request.model_id)
        prompt = request.prompt
        if request.negative_prompt:
            # gpt-image-2 has no dedicated negative-prompt field (mirrors
            # kie_image.py's FIX-IMG-09 in-prompt exclusion clause).
            prompt = f"{prompt} Do not include: {request.negative_prompt}"
        task_input: Dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "output_format": request.output_format,
        }
        if request.reference_image_urls:
            task_input["image_input"] = list(request.reference_image_urls)
        body: Dict[str, Any] = {"model": slug, "input": task_input}
        ticket = self._maybe_attach_callback(body, use_callback=use_callback)
        handle = self._submit(body, model_id=request.model_id)
        if ticket is not None:
            self._callback_tickets[handle.task_id] = ticket
        return handle

    def generate_video(
        self, request: VideoGenerationRequest, *, use_callback: Optional[bool] = None
    ) -> TaskHandle:
        slug = self.registry.slug_for(request.model_id)
        entry = self.registry.get_model(request.model_id)
        max_images = (entry.get("reference_image_support") or {}).get("max_images")
        if max_images is not None and len(request.input_urls) > max_images:
            raise ProviderTaskError(
                f"kie provider: {request.model_id} accepts at most {max_images} "
                f"input_urls (frame-pin images), got {len(request.input_urls)}"
            )
        task_input: Dict[str, Any] = {
            "prompt": request.prompt,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "duration": str(request.duration_seconds),  # STRING (422-fix pattern)
            "generate_audio": request.generate_audio,
        }
        if request.input_urls:
            # ORDER-SIGNIFICANT for frame-pinning models: index 0 = first
            # frame, index 1 = last frame (spec §10.1/§10.2). Never
            # re-sorted or de-duplicated — passed through exactly as given.
            task_input["input_urls"] = list(request.input_urls)
        body: Dict[str, Any] = {"model": slug, "input": task_input}
        ticket = self._maybe_attach_callback(body, use_callback=use_callback)
        handle = self._submit(body, model_id=request.model_id)
        if ticket is not None:
            self._callback_tickets[handle.task_id] = ticket
        return handle

    def _submit(self, body: Dict[str, Any], *, model_id: str) -> TaskHandle:
        resp = self.transport.post_json(
            _CREATE_TASK_URL, headers=self._auth_headers(), body=body, timeout=30
        )
        if resp.status_code >= 400:
            raise ProviderTaskError(
                f"kie provider: createTask HTTP {resp.status_code} for {model_id}: {resp.json_body}"
            )
        data = resp.json_body.get("data") or {}
        task_id = data.get("taskId") or resp.json_body.get("taskId")
        if not task_id:
            raise ProviderTaskError(
                f"kie provider: createTask for {model_id} returned no taskId: {resp.json_body}"
            )
        return TaskHandle(task_id=task_id, provider=self.name, model_id=model_id, status="queued")

    def get_task(self, task_id: str) -> TaskHandle:
        resp = self.transport.get_json(
            _RECORD_INFO_URL,
            headers={"Authorization": f"Bearer {self._api_key()}"},
            params={"taskId": task_id},
            timeout=15,
        )
        data = resp.json_body.get("data") or {}
        state = data.get("state", "")
        status_map = {"success": "success", "fail": "failed", "failed": "failed", "error": "failed"}
        status = status_map.get(state, "processing" if state else "queued")
        detail = None
        if status == "failed":
            detail = data.get("failMsg") or resp.json_body.get("msg")
        return TaskHandle(task_id=task_id, provider=self.name, model_id="", status=status, detail=detail)

    def cancel_task(self, task_id: str) -> bool:
        """Best-effort per the MediaProvider contract. Kie's documented
        surface (07-kie-setup/, 46-kie-callback-relay/) has no cancel
        endpoint, so this ALWAYS reports "not cancelled" rather than
        silently pretending to succeed."""
        return False

    def download_results(self, task_id: str, destination: str) -> List[str]:
        result_url = self._poll_result_url(task_id)
        content = self.transport.download(result_url, timeout=180)
        dest = Path(destination)
        if destination.endswith("/") or (dest.exists() and dest.is_dir()):
            dest = dest / task_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return [str(dest)]

    def _poll_result_url(
        self, task_id: str, *, interval: float = _POLL_INTERVAL_SECONDS, timeout: float = _POLL_TIMEOUT_SECONDS
    ) -> str:
        elapsed = 0.0
        while elapsed < timeout:
            resp = self.transport.get_json(
                _RECORD_INFO_URL,
                headers={"Authorization": f"Bearer {self._api_key()}"},
                params={"taskId": task_id},
                timeout=15,
            )
            data = resp.json_body.get("data") or {}
            state = data.get("state", "")
            if state == "success":
                result_json = _decode_result_json(data.get("resultJson"))
                urls = result_json.get("resultUrls") or []
                if urls:
                    return urls[0]
                fallback = (
                    result_json.get("videoUrl")
                    or result_json.get("url")
                    or result_json.get("resultUrl")
                )
                if fallback:
                    return str(fallback)
                images = result_json.get("images") or []
                if images:
                    return str(images[0].get("url", ""))
                raise ProviderTaskError(
                    f"kie provider: task {task_id} succeeded but no result URL found: {result_json}"
                )
            if state in ("fail", "failed", "error"):
                fail_msg = data.get("failMsg") or resp.json_body.get("msg") or "unknown"
                raise ProviderTaskError(f"kie provider: task {task_id} failed: {fail_msg}")
            time.sleep(interval)
            elapsed += interval
        raise ProviderTaskError(f"kie provider: task {task_id} timed out after {timeout}s")

    def estimate_cost(
        self, request: "ImageGenerationRequest | VideoGenerationRequest"
    ) -> CostEstimate:
        """Resolved ENTIRELY through ``ModelRegistry.estimate()`` —
        ``strict=False`` so an unpriced model (e.g.
        ``kie-bytedance-seedance-1.5-pro``, whose Kie.ai docs state pricing
        is not listed) returns an honest ``verified=False`` /
        ``estimated_total=None`` estimate instead of raising; the budget
        gate (a later unit, AF-CWFE-PAID-GATE) is what enforces
        ``strict=True`` before any actual paid call.

        The quantity multiplied against ``price.amount`` depends on the
        registry's own declared ``price.unit`` for this model — a
        ``usd_per_second`` model (e.g. gemini-omni-video, Seedance) is
        priced by ``duration_seconds``; a ``usd_per_clip`` model (veo3/
        veo3_fast) or a ``usd_per_image`` model is priced per unit
        regardless of duration. Reading the unit from the registry (instead
        of assuming every video request is priced per-second) is itself an
        ADR-8 "never hardcode a price literal OR a pricing assumption"
        consequence — a usd_per_clip model must never be silently
        multiplied by a clip's duration.
        """
        entry = self.registry.get_model(request.model_id)
        price_unit = (entry.get("price") or {}).get("unit", "")
        if isinstance(request, VideoGenerationRequest) and price_unit == "usd_per_second":
            quantity = float(request.duration_seconds)
        else:
            quantity = 1.0
        return self.registry.estimate(
            request.model_id, quantity, resolution=request.resolution, strict=False
        )
