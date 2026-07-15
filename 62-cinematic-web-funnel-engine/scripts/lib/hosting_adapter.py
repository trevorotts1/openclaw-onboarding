#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hosting_adapter.py — the provider-neutral hosting/storage adapter CONTRACT
(Skill 62, U17), implementing spec Section 14.4:

    "Use an adapter contract for: Vercel; Cloudflare Pages/Workers where
    compatible; Netlify; self-hosted Node/Docker; static export host only
    when the project uses no incompatible server features. Vercel remains
    the tested default. An alternate host may not be advertised as
    supported until its deployment adapter and E2E fixture pass."

This module mirrors the same shape ``providers/base.py`` already established
for ``MediaProvider`` (U4): an abstract base class every concrete adapter
must implement, plus small frozen dataclasses describing the wire-neutral
result shapes. Nothing here calls a network API or reads a secret value —
that is ``scripts/deploy_vercel.py``'s job (the concrete Vercel
implementation, the only adapter this unit ships and tests). A future unit
may add ``providers`` for Cloudflare/Netlify/self-hosted here without
touching this contract, exactly the way ``providers/kie.py`` slotted under
``providers/base.MediaProvider`` without changing that base class.

Two contracts live here:

1. ``HostingAdapter`` — deploys a materialized site directory (the P11
   ``build-receipt.json``'s ``site_dir``) to an application host and reports
   deployment state. Spec Section 17.8 (deployment gate) enumerates what a
   deployment must prove: "preview URL, commit SHA, deployment state,
   required environment configuration by key name only, custom-domain
   status if requested, iframe security headers when used, and successful
   post-deploy smoke tests." This contract's three methods
   (``deploy``/``get_status``/``smoke_test``) are the minimum surface a
   concrete adapter needs to produce that evidence; the caller
   (``scripts/deploy_vercel.py``'s producer functions) assembles the actual
   ``deployment-receipt.json`` (structure/deployment-receipt.schema.json).

2. ``BlobStorageAdapter`` — spec's executive summary (line 13): "Default
   media storage: Vercel Blob, with adapter support for Cloudflare
   R2/S3-compatible storage." One method, ``put``, uploads one local file
   and returns its public URL plus provenance. This is deliberately
   decoupled from ``HostingAdapter`` — a project may deploy to Vercel while
   its media lives in Blob (or vice versa; the two adapters do not assume
   the same backend), matching the spec's phrasing of Blob storage as
   independent "adapter support," not a property of the hosting adapter.

Neither contract is tied to Vercel's wire format. A concrete adapter (like
``deploy_vercel.VercelHostingAdapter``) owns every provider-specific detail
(endpoints, headers, polling cadence, payload shape); this module only
defines what every adapter must expose and the shape of what it returns.

stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Result shapes — provider-neutral, immutable. Concrete adapters build these
# from whatever their own wire response looks like; callers never see a raw
# provider response.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeployResult:
    """One deployment attempt's outcome, provider-neutral.

    ``status`` is one of the same four states ``deployment-receipt.schema.json``
    accepts for its own ``status`` field ("queued", "building", "ready",
    "error") plus "cancelled" — a concrete adapter is responsible for mapping
    its own provider's state vocabulary onto exactly these five values
    before returning a ``DeployResult`` (see
    ``deploy_vercel._map_ready_state`` for the Vercel mapping).
    """

    host: str
    host_project_id: Optional[str]
    host_deployment_id: str
    url: Optional[str]
    status: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SmokeTestResult:
    """Outcome of a post-deploy smoke test (spec 17.8 "successful post-deploy
    smoke tests"). ``ok`` is the single pass/fail a caller needs; ``detail``
    carries the reason for a human/log line, never a secret value."""

    ok: bool
    http_status: Optional[int]
    detail: str


@dataclass(frozen=True)
class BlobPutResult:
    """One uploaded blob's outcome, provider-neutral. Mirrors the fields
    ``@vercel/blob``'s ``put()`` documents (pathname/contentType/url) plus
    ``size_bytes`` and ``provider`` so a non-Vercel Blob-contract
    implementation (Cloudflare R2/S3-compatible, per spec line 13) can
    return the identical shape."""

    provider: str
    url: str
    pathname: str
    content_type: str
    size_bytes: int
    raw: Dict[str, Any] = field(default_factory=dict)


class HostingAdapterError(Exception):
    """Base class for every hosting-adapter failure. Fail-closed: a raised
    exception here must never be swallowed into a fabricated success
    receipt — callers propagate it (or record status="error") rather than
    guessing at a deployment's real state."""


class BlobStorageError(Exception):
    """Base class for every Blob-storage-adapter failure."""


# ---------------------------------------------------------------------------
# HostingAdapter contract
# ---------------------------------------------------------------------------


class HostingAdapter(ABC):
    """Every concrete application-host adapter (Vercel first; Cloudflare
    Pages/Workers, Netlify, self-hosted Node/Docker, static export are named
    in spec 14.4 as future adapters under this SAME contract) implements
    this interface. Callers (``scripts/deploy_vercel.py``'s producer
    functions, and eventually equivalents for other hosts) only ever depend
    on this interface, never on a concrete adapter's HTTP details."""

    @abstractmethod
    def deploy(
        self,
        site_dir: str,
        *,
        environment: str,
        project_name: str,
        commit_sha: str,
    ) -> DeployResult:
        """Submit ``site_dir`` for deployment. ``environment`` is
        "preview" or "production". Must return a receipt with the
        deployment in a state the host has actually acknowledged (queued at
        minimum) — never a synthesized/optimistic "ready"."""
        raise NotImplementedError

    @abstractmethod
    def get_status(self, host_deployment_id: str) -> DeployResult:
        """Re-fetch a previously submitted deployment's current state
        directly from the host. Used both to poll a deployment to
        completion and to independently reconcile a receipt after a
        process restart (spec 11.2: "deployment receipts and provider task
        IDs must survive restart"; spec 19.3: "deployment restart/reload")."""
        raise NotImplementedError

    @abstractmethod
    def smoke_test(self, url: str) -> SmokeTestResult:
        """Perform a real HTTP GET against the deployed ``url`` and report
        whether it served successfully (spec 17.8's "successful post-deploy
        smoke tests"). Never trusts the deployment's own reported "ready"
        state as a substitute for actually fetching the URL."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# BlobStorageAdapter contract
# ---------------------------------------------------------------------------


class BlobStorageAdapter(ABC):
    """Every concrete media-storage adapter (Vercel Blob first; Cloudflare
    R2/S3-compatible named in spec line 13 as a future adapter under this
    SAME contract) implements this interface."""

    @abstractmethod
    def put(
        self,
        local_path: str,
        *,
        pathname: str,
        content_type: Optional[str] = None,
    ) -> BlobPutResult:
        """Upload the file at ``local_path`` to the store under
        ``pathname`` and return its public URL plus provenance. Must raise
        ``BlobStorageError`` (never return a fabricated URL) on any
        non-success response from the store."""
        raise NotImplementedError
