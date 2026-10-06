#!/usr/bin/env python3
"""
provider_adapters.py — Extensible direct-provider adapter registry (F31).

Each adapter defines, per the model build contract:
  - authentication/secret reference (NAME only — never a secret value)
  - model discovery or verified inventory
  - capabilities per model
  - invocation (HTTP endpoint shape; no implicit routing)
  - quotas, usage and error mapping

INVARIANTS:
  - provider_id is SEPARATE from model_id. A direct selection is invoked BY
    its own adapter — never re-routed through OpenRouter or Ollama implicitly.
  - An unsupported provider is reported as adapter/setup work required, never
    silently substituted.
  - Adapters are registered in REGISTRY; new providers plug in by subclassing
    ProviderAdapter and registering — no selector-code change.

Usage:
    from provider_adapters import get_adapter, register_adapter, ProviderAdapter
    adapter = get_adapter("deepseek")
    inv = adapter.list_models()          # verified inventory (or discovery)
    r = adapter.invoke(model_id="deepseek/deepseek-v4-pro", messages=[...])
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

# ─── Adapter interface ─────────────────────────────────────────────────────────


class AdapterError(Exception):
    """Mapped provider error (auth/quota/rate/network/model)."""


class ProviderAdapter:
    """Base adapter. Subclass and register to add a provider."""

    provider_id: str = ""
    base_url: str = ""
    secret_env_name: str = ""          # NAME of the env var holding the key
    requires_key: bool = True

    def secret_reference(self) -> dict:
        """Authentication reference — the env var NAME, never the value."""
        return {"env_var": self.secret_env_name, "present": bool(os.environ.get(self.secret_env_name))}

    def _key(self) -> str:
        if not self.requires_key:
            return ""
        key = os.environ.get(self.secret_env_name, "")
        if not key:
            raise AdapterError(
                f"auth_missing: environment variable {self.secret_env_name} is not set "
                f"(secret values are never printed)"
            )
        return key

    def list_models(self) -> list:
        """Model discovery / verified inventory. Override per provider."""
        raise NotImplementedError

    def capabilities_for(self, model_id: str) -> list:
        """Capabilities for a model from the adapter's inventory/discovery."""
        for entry in self.list_models():
            mid = (entry.get("id") or "").strip().lower()
            if mid == (model_id or "").strip().lower():
                return entry.get("capabilities", [])
        return []

    def invoke(self, model_id: str, messages: list, timeout: int = 60) -> dict:
        """Direct invocation against THIS provider's endpoint — no re-routing."""
        raise NotImplementedError

    def map_error(self, exc: Exception) -> dict:
        """Error mapping: status/code -> structured, client-safe record."""
        if isinstance(exc, AdapterError):
            return {"provider": self.provider_id, "error": str(exc)}
        if isinstance(exc, urllib.error.HTTPError):
            return {"provider": self.provider_id, "error": "http_error",
                    "status": exc.code, "retryable": exc.code in (429, 500, 502, 503)}
        if isinstance(exc, urllib.error.URLError):
            return {"provider": self.provider_id, "error": "network_error", "retryable": True}
        return {"provider": self.provider_id, "error": "unknown_error",
                "detail": exc.__class__.__name__}


# ─── DeepSeek direct adapter ───────────────────────────────────────────────────


class DeepSeekAdapter(ProviderAdapter):
    """DeepSeek direct API (api.deepseek.com) — OpenAI-compatible chat shape."""

    provider_id = "deepseek"
    base_url = "https://api.deepseek.com"
    secret_env_name = "DEEPSEEK_API_KEY"
    verified_inventory = [
        {"id": "deepseek/deepseek-v4-pro", "family": "deepseek-pro",
         "capabilities": ["text", "reasoning", "tool_use", "structured_output", "long_context", "streaming"]},
        {"id": "deepseek/deepseek-v4-flash", "family": "deepseek-flash",
         "capabilities": ["text", "tool_use", "structured_output", "streaming"]},
    ]

    def list_models(self) -> list:
        # Verified inventory per the model build contract; discovery via
        # GET {base_url}/models when a key is configured.
        return [dict(e) for e in self.verified_inventory]

    def invoke(self, model_id: str, messages: list, timeout: int = 60) -> dict:
        key = self._key()
        payload = json.dumps({
            "model": model_id.split("/")[-1],
            "messages": messages,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise AdapterError(json.dumps(self.map_error(exc))) from exc
        return {
            "provider_id": self.provider_id,      # provider_id SEPARATE from model_id
            "model_id": model_id,
            "content": data.get("choices", [{}])[0].get("message", {}).get("content"),
            "usage": data.get("usage", {}),
        }


# ─── TEST-ONLY adapter stub (never production) ────────────────────────────────


class TestProviderAdapter(ProviderAdapter):
    """TEST-ONLY fourth adapter stub — labeled, deterministic, no network.

    Exists purely to prove the registry is extensible (QC-F31's fourth adapter).
    Never ships in production paths; any client config pointing at
    test-provider fails closed outside tests.
    """

    provider_id = "test-provider"
    base_url = "http://localhost:0"      # port 0: connection always refused
    secret_env_name = "TEST_PROVIDER_API_KEY"
    requires_key = False
    verified_inventory = [
        {"id": "test-provider/test-model-pro", "family": "test-pro",
         "capabilities": ["text", "reasoning", "tool_use"]},
        {"id": "test-provider/test-model-vision", "family": "test-vision",
         "capabilities": ["text", "vision"]},
    ]

    def list_models(self) -> list:
        return [dict(e) for e in self.verified_inventory]

    def invoke(self, model_id: str, messages: list, timeout: int = 60) -> dict:
        raise AdapterError("test_only: TEST-ONLY adapter stub never invokes a real endpoint")


# ─── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict = {}


def register_adapter(adapter_cls) -> ProviderAdapter:
    """Register an adapter class by provider_id. Extensible: new providers
    register here; selector code never changes."""
    inst = adapter_cls()
    REGISTRY[inst.provider_id] = inst
    return inst


def get_adapter(provider_id: str) -> ProviderAdapter:
    """Fetch a registered adapter. Unknown provider -> AdapterError reporting
    the adapter/setup work required (never a silent substitution)."""
    pid = (provider_id or "").strip().lower()
    if pid not in REGISTRY:
        raise AdapterError(
            f"adapter_missing: provider '{provider_id}' has no registered adapter — "
            f"adapter/setup work required (registered: {', '.join(sorted(REGISTRY))})"
        )
    return REGISTRY[pid]


def registered_providers() -> list:
    return sorted(REGISTRY)


register_adapter(DeepSeekAdapter)
register_adapter(TestProviderAdapter)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Direct-provider adapter registry (F31)")
    parser.add_argument("--provider", default="", help="provider_id to inspect")
    parser.add_argument("--list", action="store_true", help="List registered providers")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(registered_providers(), indent=2))
        sys.exit(0)
    if args.provider:
        try:
            ad = get_adapter(args.provider)
            print(json.dumps({
                "provider_id": ad.provider_id,
                "secret_reference": ad.secret_reference(),
                "models": ad.list_models(),
            }, indent=2))
        except AdapterError as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            sys.exit(2)
        sys.exit(0)
    parser.print_help()