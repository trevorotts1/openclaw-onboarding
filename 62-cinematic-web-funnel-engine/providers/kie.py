#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kie.py — the Kie.ai concrete MediaProvider adapter (Skill 62, U5).

Implements spec §10.1's mandate: "Implement providers/kie.py first. Reuse the
existing canonical Kie setup, secret resolution, callback infrastructure, and
image/video adapters where possible."

CONSOLIDATED (v2.1.0): this module is NOT a standalone Kie client. Every Kie
API call (catalog, schema validation, prompt budget, upload, createTask,
recordInfo, price, save) runs through Skill 74 (74-kie-live-adapter, the one
fleet KIE transport), loaded from the sibling skill folder and called in
``active`` mode per call. This file keeps only Skill 62's own policy: the model
registry, tier selection, the Veo 3.1 wire shape, the quality-tier refusal, the
per-resolution price-table parsing, and the 46-kie-callback-relay HMAC wiring.
When Skill 74 is not installed the provider falls back to the quarantined
``providers/_kie_legacy.py`` client and logs ``path=legacy``; every other run
logs ``path=skill74``.

This module is SKILL-LOCAL (62-cinematic-web-funnel-engine/providers/) and
has NO dependency on OpenMontage's ``tools.base_tool``. Skill 47's OpenMontage
adapters ride the same Skill 74 transport. NOT shared with 47: Veo. 47 uses
the legacy ``POST /api/v1/veo/generate`` route (``veo3``/``veo3_fast``); this
module uses the current Veo route on createTask with model ``veo-3-1`` (see
``_veo_3_1_input``).

Every model is addressed through ``providers.base.ModelRegistry`` by its
registry ``model_id`` — this file NEVER hardcodes a provider wire slug or a
price literal (ADR-8).

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
``KieTransport`` seam (bridged onto Skill 74's transport interface);
``RequestsTransport`` is the only implementation that ever touches the
network, and it is never invoked by this unit's tests.

stdlib + optional ``requests`` (imported lazily, only inside
``RequestsTransport``); importing this module never requires ``requests``.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote, urlparse

from . import _kie_legacy

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

_POLL_TIMEOUT_SECONDS = 600  # 10 min ceiling; matches box-kv-poller.js's fallback ceiling
_KIE_HOSTS = ("api.kie.ai", "kieai.redpandaai.co")  # hosts that are the KIE API (everything else is a result file)


# Veo 3.1 on createTask (live KIE catalog/schema, verified 2026-10-05):
# GET /api/v1/models?q=veo lists ``veo-3-1`` (and the veo/extend,
# veo/get-1080p-video, veo/get-4k-video helpers); GET /api/v1/models/veo3 and
# /veo3_fast answer code 404 "model name ... not supported". The registry flags
# such models with ``"wire_schema": "veo-3-1"``.
_VEO_WIRE_SCHEMA = "veo-3-1"
_VEO_RESOLUTIONS = ("720p", "1080p", "4k")
_VEO_ASPECT_RATIOS = ("16:9", "9:16", "Auto")
_VEO_DURATIONS = (4, 6, 8)


def _veo_3_1_input(request: VideoGenerationRequest) -> Dict[str, Any]:
    """Build the createTask ``input`` for model ``veo-3-1`` exactly per its
    live schema: ``image_urls`` (NOT ``input_urls``), INTEGER ``duration`` in
    {4,6,8}, lowercase ``resolution`` in {720p,1080p,4k}, ``aspect_ratio`` in
    {16:9,9:16,Auto}, ``generation_type`` enum. There is no audio field (clips
    carry audio by default), so ``generate_audio`` is never sent. 1 image =
    image-to-video, 2 = first/last frame, order significant."""
    resolution = str(request.resolution).lower()
    if resolution not in _VEO_RESOLUTIONS:
        raise ProviderTaskError(
            f"kie provider: veo-3-1 resolution must be one of {_VEO_RESOLUTIONS}, got {request.resolution!r}"
        )
    if request.aspect_ratio not in _VEO_ASPECT_RATIOS:
        raise ProviderTaskError(
            f"kie provider: veo-3-1 aspect_ratio must be one of {_VEO_ASPECT_RATIOS}, got {request.aspect_ratio!r}"
        )
    if int(request.duration_seconds) not in _VEO_DURATIONS:
        raise ProviderTaskError(
            f"kie provider: veo-3-1 duration must be one of {_VEO_DURATIONS}, got {request.duration_seconds!r}"
        )
    task_input: Dict[str, Any] = {
        "prompt": request.prompt,
        "aspect_ratio": request.aspect_ratio,
        "resolution": resolution,
        "duration": int(request.duration_seconds),
        "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO" if request.input_urls else "TEXT_2_VIDEO",
    }
    if request.input_urls:
        task_input["image_urls"] = list(request.input_urls)
    return task_input


def _urls_from(value: Any) -> List[str]:
    """Normalise a ``resultUrls`` value: a list, or (callback docs type it as
    a string) a JSON-encoded list / single URL string."""
    if isinstance(value, list):
        return [str(u) for u in value if u]
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            return [str(u) for u in parsed if u]
        return [text.strip("[]")] if text.startswith("[") else [text]
    return []


def result_urls_from_callback(payload: Dict[str, Any]) -> List[str]:
    """Result URLs from a veo-3-1 callback body (documented shape:
    ``{"code":200,"data":{"taskId":...,"info":{"resultUrls":[...]}}}``).
    Empty list when the callback is not a success."""
    if not isinstance(payload, dict) or payload.get("code") != 200:
        return []
    return _urls_from(((payload.get("data") or {}).get("info") or {}).get("resultUrls"))


# Live price authority (2026-10-05): GET /api/v1/models/<id>/price returns
# data.pricingDesc, one line per mode, e.g.
#   "Fast mode (...): 720P — 60 credits (≈ $0.30) per video; 1080P — 65 credits (≈ $0.325) per video; ..."
_PRICE_ENTRY = re.compile(r"(\d+)\s*([PpKk])\s*—\s*[\d.]+\s*credits\s*\(≈\s*\$([0-9.]+)\)")


def parse_pricing_desc(text: str) -> Dict[str, Dict[str, float]]:
    """Parse a KIE ``pricingDesc`` into ``{"fast": {"720p": 0.30, ...}, ...}``
    keyed by lowercase mode name, then lowercase resolution (720p, 1080p, 4k).
    Lines that do not start with ``<Mode> mode`` are ignored."""
    out: Dict[str, Dict[str, float]] = {}
    for line in str(text or "").splitlines():
        m = re.match(r"\s*([A-Za-z]+) mode", line)
        if not m:
            continue
        prices = {f"{n}{u.lower()}": float(usd) for n, u, usd in _PRICE_ENTRY.findall(line)}
        if prices:
            out[m.group(1).lower()] = prices
    return out


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
# Skill 74 (74-kie-live-adapter): the one KIE transport. Loaded by file path
# from the sibling skill folder (installed tree or repo checkout); nothing is
# written into that folder (no bytecode: the source is compiled in memory).
# ---------------------------------------------------------------------------

_SKILL74_DIRNAME = "74-kie-live-adapter"
_SKILL74_MODULES: Dict[str, Any] = {}


def _skill74_candidates() -> List[Path]:
    override = os.environ.get("CWFE_SKILL74_DIR")
    if override is not None:  # test hook: look only here ("" = Skill 74 not installed)
        return [Path(override)] if override else []
    roots = [
        Path(__file__).resolve().parent.parent.parent,  # sibling of this skill (installed tree or checkout)
        Path(os.environ.get("OPENCLAW_SKILLS_DIR") or "") if os.environ.get("OPENCLAW_SKILLS_DIR") else None,
        Path.home() / ".openclaw" / "skills",
        Path("/data/.openclaw/skills"),
    ]
    return [r / _SKILL74_DIRNAME for r in roots if r is not None]


def load_skill74() -> Optional[Any]:
    """Return Skill 74's ``kie_live_adapter`` module, or None when it is not installed."""
    import types

    for d in _skill74_candidates():
        f = d / "scripts" / "kie_live_adapter.py"
        if not f.is_file():
            continue
        key = str(f)
        if key not in _SKILL74_MODULES:
            mod = types.ModuleType("kie_live_adapter_skill74")
            mod.__file__ = key
            exec(compile(f.read_text(encoding="utf-8"), key, "exec"), mod.__dict__)
            _SKILL74_MODULES[key] = mod
        return _SKILL74_MODULES[key]
    return None


class _Skill74Transport:
    """Adapts the injectable ``KieTransport`` test seam (post_json/get_json/
    download) to Skill 74's ``request(method, url, headers, body, timeout)``
    interface. Used ONLY when a caller injects a transport (offline fixtures);
    a real run lets Skill 74 use its own stdlib transport."""

    def __init__(self, transport: "KieTransport", kie_error: Any) -> None:
        self._t = transport
        self._err = kie_error

    def request(self, method, url, headers=None, body=None, timeout=60):
        headers = dict(headers or {})
        if method == "POST":
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except ValueError:
                raise self._err("network", "offline fixture transport carries JSON bodies only")
            r = self._t.post_json(url, headers=headers, body=payload, timeout=timeout)
            return r.status_code, json.dumps(r.json_body).encode("utf-8")
        parsed = urlparse(url)
        if parsed.hostname in _KIE_HOSTS:
            r = self._t.get_json(
                url.split("?")[0], headers=headers, params=dict(parse_qsl(parsed.query)) or None, timeout=timeout
            )
            return r.status_code, json.dumps(r.json_body).encode("utf-8")
        try:  # a result file on a CDN host, not the KIE API
            return 200, self._t.download(url, timeout=timeout)
        except Exception as exc:  # never leak transport internals; Skill 74 turns a non-200 into download_failed
            return getattr(getattr(exc, "response", None), "status_code", 502), b""


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


_UNSET = object()


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
        live_prices: bool = True,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self._injected_transport = transport is not None  # offline harness: ephemeral cache, no pacing sleeps
        self.transport: KieTransport = transport or RequestsTransport()
        self._skill74: Any = _UNSET
        self._scratch: Optional[str] = None
        self.client_path: Optional[str] = None  # "skill74" or "legacy" once the first call has chosen
        self._api_key_env = api_key_env
        self._callback_worker_url_env = callback_worker_url_env
        self._callback_hmac_key_env = callback_hmac_key_env
        self._kv_read_token_env = kv_read_token_env
        self._client_slug_env = client_slug_env
        self._live_prices = live_prices
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

    # -- Skill 74 plumbing ---------------------------------------------------

    def _use_skill74(self) -> bool:
        if self._skill74 is _UNSET:
            self._skill74 = load_skill74()
            self.client_path = "skill74" if self._skill74 is not None else "legacy"
            if self._skill74 is not None:
                self._log("path=skill74 mode=active (Skill 74 is the KIE transport)")
            else:
                self._log("WARNING path=legacy: Skill 74 (74-kie-live-adapter) is not installed; using the quarantined fallback client")
        return self._skill74 is not None

    @staticmethod
    def _log(message: str) -> None:
        print(f"[cwfe-kie] {message}", file=sys.stderr)

    def _adapter(self) -> Any:
        """A Skill 74 ``Adapter`` pinned to ``active`` mode for this call (owner order: live)."""
        mod = self._skill74
        env = {
            "KIE_API_KEY": self._api_key(),
            "KIE_LIVE_ADAPTER_MODE": "active",
            "HOME": os.environ.get("HOME") or str(Path.home()),
        }
        for name in ("KIE_LIVE_CACHE_DIR", "KIE_LIVE_RECEIPT_DIR", "OC_CONFIG"):
            if os.environ.get(name):
                env[name] = os.environ[name]
        kwargs: Dict[str, Any] = {}
        if self._injected_transport:
            if self._scratch is None:
                self._scratch = tempfile.mkdtemp(prefix="cwfe-kie74-")
                weakref.finalize(self, shutil.rmtree, self._scratch, True)
            env["KIE_LIVE_CACHE_DIR"] = self._scratch
            env["KIE_LIVE_MIN_SPACING"] = "0"
            kwargs = {"transport": _Skill74Transport(self.transport, mod.KieError), "sleep": lambda _s: None}
        adapter = mod.Adapter(env=env, **kwargs)
        adapter.mode = "active"
        return adapter

    def _check_prompt(self, adapter: Any, slug: str, prompt: Any, model_id: str) -> None:
        """Prompt length comes from Skill 74 prompt-budget (no band is hard-coded here): over the model
        maximum is refused; under the 80 percent floor is reported (this skill's templated prompts are
        short; the floor is enforced by the policy owner Skill 66)."""
        if not isinstance(prompt, str):
            return
        r = adapter.cmd_prompt_budget(slug, check=True, prompt_text=prompt)
        err = r.get("error") or {}
        if err.get("code") == "prompt_above_max":
            raise ProviderTaskError(f"kie provider: {model_id} prompt exceeds the model limit: {err.get('msg')}")
        if err.get("code") == "prompt_below_floor":
            self._log(f"WARNING {model_id} prompt below the prompt-budget floor: {err.get('msg')}")

    # -- MediaProvider interface --------------------------------------------

    def upload_asset(self, request: AssetUploadRequest) -> str:
        """Upload a local file through Skill 74 (authenticated, KIE-hosted
        URL back); the quarantined fallback client is used only without Skill 74."""
        path = Path(request.path)
        if not path.exists():
            raise ProviderTaskError(f"kie provider: local asset not found: {path}")
        if not self._use_skill74():
            return _kie_legacy.upload_asset(self.transport, self._api_key(), path, request.purpose)
        r = self._adapter().cmd_upload(
            file=str(path), upload_path=f"images/cinematic-web-funnel-engine/{request.purpose}"
        )
        url = (r.get("data") or {}).get("download_url")
        if r["state"] != "success" or not url or not str(url).startswith("http"):
            raise ProviderTaskError(f"kie provider: upload_asset failed: {r.get('error') or r.get('data')}")
        return str(url)

    def generate_image(
        self, request: ImageGenerationRequest, *, use_callback: Optional[bool] = None
    ) -> TaskHandle:
        slug = self.registry.slug_for(request.model_id)
        prompt = request.prompt
        if request.negative_prompt:
            # GPT-image-2.5 has no dedicated negative-prompt field (mirrors
            # kie_image.py's FIX-IMG-09 in-prompt exclusion clause).
            prompt = f"{prompt} Do not include: {request.negative_prompt}"
        # Only fields the sunburst schemas DECLARE are sent: no output_format; the
        # image-to-image reference field is `input_urls` (not Nano Banana's `image_input`).
        task_input: Dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
        }
        if request.reference_image_urls:
            task_input["input_urls"] = list(request.reference_image_urls)
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
        if entry.get("status") == "planned":
            raise ProviderTaskError(
                f"kie provider: {request.model_id} is status=planned and cannot be submitted: "
                f"{entry.get('wire_blocked_reason', 'not wired')}"
            )
        max_images = (entry.get("reference_image_support") or {}).get("max_images")
        if max_images is not None and len(request.input_urls) > max_images:
            raise ProviderTaskError(
                f"kie provider: {request.model_id} accepts at most {max_images} "
                f"input_urls (frame-pin images), got {len(request.input_urls)}"
            )
        if entry.get("wire_schema") == _VEO_WIRE_SCHEMA:
            task_input = _veo_3_1_input(request)
        else:
            task_input = {
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
        if not self._use_skill74():
            task_id = _kie_legacy.submit(self.transport, self._api_key(), body, model_id)
            return TaskHandle(task_id=task_id, provider=self.name, model_id=model_id, status="queued")
        adapter = self._adapter()
        self._check_prompt(adapter, body["model"], (body.get("input") or {}).get("prompt"), model_id)
        r = adapter.cmd_submit(body)  # validates against the live schema, then createTask (never retried on a network error)
        if r["state"] != "queued" or not r.get("task_id"):
            err = r.get("error") or {}
            raise ProviderTaskError(
                f"kie provider: Skill 74 submit for {model_id} did not queue ({r['state']}, {err.get('code')}): {err.get('msg')}"
            )
        return TaskHandle(task_id=r["task_id"], provider=self.name, model_id=model_id, status="queued")

    def get_task(self, task_id: str) -> TaskHandle:
        if not self._use_skill74():
            status, detail = _kie_legacy.task_state(self.transport, self._api_key(), task_id)
            return TaskHandle(task_id=task_id, provider=self.name, model_id="", status=status, detail=detail)
        r = self._adapter().cmd_wait(task_id, timeout=0)  # one poll: a zero deadline returns after the first read
        data = r.get("data") or {}
        if r["state"] == "fail" and "state_raw" not in data:  # an API/transport error, not a task verdict
            raise ProviderTaskError(f"kie provider: status read for {task_id} failed: {r.get('error')}")
        status = {"success": "success", "fail": "failed"}.get(r["state"]) or ("processing" if data.get("state_raw") else "queued")
        detail = (r.get("error") or {}).get("msg") if status == "failed" else None
        return TaskHandle(task_id=task_id, provider=self.name, model_id="", status=status, detail=detail)

    def cancel_task(self, task_id: str) -> bool:
        """Best-effort per the MediaProvider contract. Kie's documented
        surface (07-kie-setup/, 46-kie-callback-relay/) has no cancel
        endpoint, so this ALWAYS reports "not cancelled" rather than
        silently pretending to succeed."""
        return False

    def download_results(self, task_id: str, destination: str) -> List[str]:
        dest = Path(destination)
        into_dir = destination.endswith("/") or (dest.exists() and dest.is_dir())
        if into_dir:
            dest = dest / task_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not self._use_skill74():
            url = _kie_legacy.poll_result_url(self.transport, self._api_key(), task_id, timeout=_POLL_TIMEOUT_SECONDS)
            _kie_legacy.download(self.transport, url, dest)
            return [str(dest)]
        adapter = self._adapter()
        waited = adapter.cmd_wait(task_id, timeout=_POLL_TIMEOUT_SECONDS)
        if waited["state"] != "success":
            err = waited.get("error") or {}
            raise ProviderTaskError(f"kie provider: task {task_id} {waited['state']}: {err.get('msg') or err.get('code')}")
        scratch = tempfile.mkdtemp(prefix="cwfe-kie-save-")
        try:
            saved = adapter.cmd_save(task_id, scratch)
            if saved["state"] != "success" or not saved["saved_paths"]:
                err = saved.get("error") or {}
                raise ProviderTaskError(f"kie provider: task {task_id} result could not be saved: {err.get('msg') or saved['warnings']}")
            if into_dir:
                dest = dest.with_name(dest.name + Path(saved["saved_paths"][0]).suffix)
            shutil.move(saved["saved_paths"][0], str(dest))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return [str(dest)]

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
        live = self._live_estimate(entry, request)
        if live is not None:
            return live
        price_unit = (entry.get("price") or {}).get("unit", "")
        if isinstance(request, VideoGenerationRequest) and price_unit == "usd_per_second":
            quantity = float(request.duration_seconds)
        else:
            quantity = 1.0
        resolution = request.resolution
        if entry.get("wire_schema") == _VEO_WIRE_SCHEMA:
            resolution = str(resolution).lower()
        estimate = self.registry.estimate(
            request.model_id, quantity, resolution=resolution, strict=False
        )
        if (entry.get("price") or {}).get("live"):
            estimate = dataclasses.replace(
                estimate,
                note="FALLBACK registry constant (live catalog price not read; see price.source for its date). "
                + estimate.note,
            )
        return estimate

    def _live_estimate(self, entry: Dict[str, Any], request: Any) -> Optional[CostEstimate]:
        """Live price first: when the registry entry declares ``price.live``
        (mode), read the model's ``pricingDesc`` through Skill 74 ``price``
        (live catalog only; its registry snapshot is NOT a live read) and pick
        this skill's mode/resolution row. Returns None on any failure (no
        Skill 74, no key, catalog unavailable, mode/resolution missing) so
        the caller falls back to the dated registry constants."""
        live = (entry.get("price") or {}).get("live")
        if not (self._live_prices and live and isinstance(request, VideoGenerationRequest)):
            return None
        if not self._use_skill74():
            return None
        try:
            r = self._adapter().cmd_price(entry["provider_model_slug"])
            data = r.get("data") or {}
            if r["state"] == "fail" or not str(data.get("price_source", "")).startswith("catalog"):
                return None
            table = parse_pricing_desc(data.get("pricing_desc") or "")
            unit_price = table[str(live["mode"]).lower()][str(request.resolution).lower()]
        except Exception:  # fail soft to the labeled fallback constants
            return None
        return CostEstimate(
            model_id=request.model_id,
            provider_model_slug=entry["provider_model_slug"],
            unit=(entry.get("price") or {}).get("unit", "usd_per_clip"),
            unit_price=unit_price,
            quantity=1.0,
            estimated_total=round(unit_price, 6),
            verified=True,
            registry_snapshot_id=self.registry.snapshot_id,
            note=f"LIVE catalog price (Skill 74 price, {live['endpoint']}), {live['mode']} mode, {request.resolution}",
        )
