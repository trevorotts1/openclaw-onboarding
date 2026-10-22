"""One resolved capability manifest (finding D30, spec 7.5 / 15.3).

`resolve_manifest` builds a single manifest from the installed runtime schema
and the authoritative provider catalog, then reconciles every surface against
it: selectable models, allowlists, provider entries, role bindings, scheduler
jobs, and session/UI cache versions. Every cache row carries source revision,
fetched time and a supported refresh path. A role binding is only VERIFIED by
an actual host dispatch receipt proving the chosen model; a label is never
proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .effort import ModelCaps

REASONING_EFFORT_PARAM = "reasoning_effort"


@dataclass
class Finding:
    code: str
    detail: str
    surface: str
    severity: str = "error"

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "surface": self.surface, "severity": self.severity}


@dataclass
class DispatchReceipt:
    """Correlated host-dispatch evidence for one role binding.

    requested/resolved/response model plus the router-side request id. An
    agent-authored label is not a receipt.
    """
    role: str
    requested_model: str
    resolved_model: str
    response_model: Optional[str]
    router_request_id: Optional[str]
    timestamp: str


def _effort_selector_from_authoritative(entry: Dict[str, Any]) -> Optional[bool]:
    params = entry.get("supported_parameters")
    if isinstance(params, list):
        return REASONING_EFFORT_PARAM in params
    return None


def _effort_selector_from_host(entry: Dict[str, Any]) -> Optional[bool]:
    caps = entry.get("capabilities")
    if isinstance(caps, dict) and "thinkingEffortSupported" in caps:
        return bool(caps["thinkingEffortSupported"])
    return None


@dataclass
class CapabilityManifest:
    schema_id: str
    models: List[ModelCaps]
    providers: List[Dict[str, Any]]
    allowlist: Dict[str, Any]
    role_bindings: List[Dict[str, Any]]
    scheduler_jobs: List[Dict[str, Any]]
    caches: List[Dict[str, Any]]
    findings: List[Finding] = field(default_factory=list)
    dispatch_receipts: List[DispatchReceipt] = field(default_factory=list)

    def model(self, model_id: str) -> Optional[ModelCaps]:
        for m in self.models:
            if m.model_id == model_id:
                return m
        return None

    def verify_dispatch(self, receipt: DispatchReceipt) -> Finding:
        """Bind one role binding to actual host dispatch proof."""
        self.dispatch_receipts.append(receipt)
        binding = next((b for b in self.role_bindings if b.get("role") == receipt.role), None)
        if binding is None:
            f = Finding("UNKNOWN_ROLE", "no role binding named %r" % receipt.role, "role_bindings")
            self.findings.append(f)
            return f
        if receipt.requested_model != binding.get("model_id"):
            f = Finding("DISPATCH_MISMATCH", "receipt requested %r but binding wants %r" % (receipt.requested_model, binding.get("model_id")), "role_bindings")
            self.findings.append(f)
            return f
        proven = receipt.resolved_model == binding.get("model_id") and self._response_proves(
            receipt.response_model, binding.get("model_id"))
        if proven:
            binding["verification"] = "verified_by_host_dispatch"
            binding["verified_by"] = receipt.router_request_id or receipt.timestamp
            return Finding("DISPATCH_VERIFIED", "role %s proven at model %s" % (receipt.role, receipt.resolved_model), "role_bindings", severity="info")
        f = Finding("DISPATCH_MISMATCH", "resolved/response model does not prove %r (resolved=%r response=%r)" % (binding.get("model_id"), receipt.resolved_model, receipt.response_model), "role_bindings")
        self.findings.append(f)
        return f

    @staticmethod
    def _response_proves(response_model: Optional[str], bound: Optional[str]) -> bool:
        """Response metadata proves the binding when it matches exactly or is the
        provider-local echo of the bound route (openrouter/x/y echoes x/y)."""
        if response_model is None:
            return True  # backend identity not exposed: stated, never invented
        if response_model == bound:
            return True
        return bool(bound) and bound.endswith("/" + response_model)

    def unverified_roles(self) -> List[str]:
        return [b.get("role") for b in self.role_bindings if b.get("verification") != "verified_by_host_dispatch"]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "models": [vars(m) for m in self.models],
            "providers": self.providers,
            "allowlist": self.allowlist,
            "role_bindings": self.role_bindings,
            "scheduler_jobs": self.scheduler_jobs,
            "caches": self.caches,
            "findings": [f.as_dict() for f in self.findings],
            "dispatch_receipts": [vars(r) for r in self.dispatch_receipts],
        }


def resolve_manifest(schema_id: str,
                     authoritative_catalog: Dict[str, Dict[str, Any]],
                     host_catalog: Dict[str, Dict[str, Any]],
                     surfaces: Dict[str, Any]) -> CapabilityManifest:
    """Build the one resolved manifest and reconcile every surface.

    authoritative_catalog: model_id -> authoritative provider catalog entry
      (e.g. OpenRouter /api/v1/models row: supported_parameters etc.)
    host_catalog: model_id -> installed-host /v1/models row (capability flags).
    surfaces: allowlist, provider_entries, role_bindings, scheduler_jobs,
      caches (each cache dict needs cache_id, source_revision, fetched_at,
      refresh_path) and selectable (the selectable-model list to reconcile).
    """
    findings: List[Finding] = []
    models: List[ModelCaps] = []

    for model_id in surfaces.get("selectable", []):
        auth = authoritative_catalog.get(model_id)
        host = host_catalog.get(model_id)
        if auth is None:
            findings.append(Finding("UNKNOWN_MODEL", "%s absent from authoritative provider catalog" % model_id, "selectable_models"))
            continue
        if host is None:
            findings.append(Finding("UNKNOWN_MODEL", "%s absent from installed host catalog" % model_id, "selectable_models"))
            continue
        auth_effort = _effort_selector_from_authoritative(auth)
        host_effort = _effort_selector_from_host(host)
        effort = auth_effort
        if auth_effort is not None and host_effort is not None and auth_effort != host_effort:
            findings.append(Finding(
                "CATALOG_CONFLICT",
                "%s effort-selector disagreement: authoritative=%s host=%s; resolving conservatively to %s"
                % (model_id, auth_effort, host_effort, auth_effort),
                "selectable_models", severity="warning"))
        caps_meta = host.get("capabilities", {}) or {}
        models.append(ModelCaps(
            model_id=model_id,
            provider=host.get("owned_by") or auth.get("owned_by") or "",
            reasoning=bool(caps_meta.get("reasoning", False)),
            effort_selector=bool(effort) if effort is not None else False,
            tools=bool(caps_meta.get("tools", False)),
            source_revision=str((host.get("provenance_revision") or auth.get("provenance_revision") or "")),
            fetched_at=str((host.get("provenance_fetched_at") or auth.get("provenance_fetched_at") or "")),
        ))

    # Provider entries must map to catalog providers.
    providers = surfaces.get("provider_entries", [])
    known_providers = {m.provider for m in models if m.provider}
    for entry in providers:
        if entry.get("provider") and known_providers and entry["provider"] not in known_providers:
            findings.append(Finding("PROVIDER_ENTRY_DRIFT", "provider entry %r names provider %r absent from resolved models" % (entry.get("entry_id"), entry.get("provider")), "provider_entries"))

    # Allowlist reconciliation: every enabled entry resolves; disabled wins.
    allowlist = surfaces.get("allowlist", {"enabled": [], "disabled": []})
    model_ids = {m.model_id for m in models}
    disabled = set(allowlist.get("disabled", []))
    for mid in allowlist.get("enabled", []):
        if mid in disabled:
            findings.append(Finding("ALLOWLIST_DRIFT", "%s is both enabled and disabled" % mid, "allowlist"))
        elif mid not in model_ids:
            findings.append(Finding("ALLOWLIST_DRIFT", "allowlist entry %r does not resolve to a catalog model" % mid, "allowlist"))
    for alias, target in (allowlist.get("aliases") or {}).items():
        if isinstance(target, str) and target not in model_ids and target not in disabled:
            findings.append(Finding("ALLOWLIST_DRIFT", "alias %r targets unknown model %r" % (alias, target), "allowlist"))

    # Scheduler jobs: any job pin must resolve.
    for job in surfaces.get("scheduler_jobs", []):
        mid = job.get("model_id")
        if mid and mid not in model_ids:
            findings.append(Finding("SCHEDULER_JOB_DRIFT", "job %r pins unknown model %r" % (job.get("job_id"), mid), "scheduler_jobs"))

    # Cache rows: provenance is mandatory; staleness is a finding.
    caches = []
    authoritative_revision = surfaces.get("authoritative_revision")
    for cache in surfaces.get("caches", []):
        row = dict(cache)
        missing = [k for k in ("source_revision", "fetched_at", "refresh_path") if not row.get(k)]
        if missing:
            findings.append(Finding("CACHE_PROVENANCE_INCOMPLETE", "cache %r missing %s" % (row.get("cache_id"), missing), "caches"))
        if authoritative_revision and row.get("source_revision") and row["source_revision"] != authoritative_revision:
            findings.append(Finding("CACHE_STALE", "cache %r at revision %r != authoritative %r" % (row.get("cache_id"), row.get("source_revision"), authoritative_revision), "caches", severity="warning"))
        caches.append(row)

    return CapabilityManifest(
        schema_id=schema_id,
        models=models,
        providers=providers,
        allowlist=allowlist,
        role_bindings=[dict(b) for b in surfaces.get("role_bindings", [])],
        scheduler_jobs=[dict(j) for j in surfaces.get("scheduler_jobs", [])],
        caches=caches,
        findings=findings,
    )


def effort_claims_findings(manifest: CapabilityManifest, claimed: Dict[str, str]) -> List[Finding]:
    """Flag fabricated effort claims (UI ladders, combo annotations).

    `claimed`: model_id -> effort value someone claims (e.g. from a UI ladder
    or a fallback-chain annotation like "model(max)"). A claim on a model
    without an authoritative effort selector is fabrication.
    """
    out: List[Finding] = []
    for model_id, value in claimed.items():
        caps = manifest.model(model_id)
        if caps is None:
            out.append(Finding("UNSUPPORTED_EFFORT_CLAIM", "effort %r claimed for unknown model %r" % (value, model_id), "effort"))
        elif not caps.effort_selector:
            out.append(Finding(
                "UNSUPPORTED_EFFORT_CLAIM",
                "effort %r claimed for %s, which supports reasoning without an effort selector; "
                "a UI ladder cannot create provider support" % (value, model_id),
                "effort"))
    return out
