#!/usr/bin/env python3
"""
Data plane transport for the Convert and Flow field layer.

Tier 0 is the Skill 44 caf command line interface. Tier 3 is Skill 29 direct
REST. The two Model Context Protocol tiers are structurally forbidden here: a
sub-agent performing a field write would silently have no MCP tools, exactly the
false-done class the quality-control protocol exists to kill (design Section 1).
There is deliberately NO MCP code path in this module.

Routing (design Sections 1 and 3.4):
  reads   -> Tier 0 caf first, Tier 3 REST fallback.
  writes  -> Tier 0 caf if it supports custom-field writes, else Tier 3.
             The current caf `contacts update` exposes email, phone, name, and
             tags only, with no custom-field option, so a custom-field write is
             "command unsupported" and escalates to Tier 3 per the Section 1
             escalation rule. This is verified at runtime by a capability probe
             against `caf contacts update --help`, never assumed blindly.

Escalation never crosses to a Model Context Protocol tier, and a 429 never
escalates or tier-hops (all tiers share one per-location bucket, design
Section 6): a 429 is raised as RateLimited for the caller to full-stop on.

Secrecy: the token is never placed on the caf argv; caf resolves its own
credential from the environment. The Tier 3 header is built in memory and every
emitted error string is scrubbed through the Redactor.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import requests

from . import constants, redact


class DataPlaneError(Exception):
    """A data-plane operation failed after the permitted tier escalation."""


class Tier0Unavailable(Exception):
    """caf was missing, errored, or returned unusable output for this call."""


class RateLimited(DataPlaneError):
    """A 429 was seen. Callers full-stop; they never retry or tier-hop."""

    def __init__(self, retry_after: float | None) -> None:
        super().__init__("Convert and Flow rate limit reached")
        self.retry_after = retry_after


def _caf_binary() -> str | None:
    override = os.environ.get("CAF_BIN")
    if override and os.path.exists(override):
        return override
    found = shutil.which("caf")
    if found:
        return found
    candidate = os.path.expanduser("~/.openclaw/tools/convert-and-flow-cli/caf")
    return candidate if os.path.exists(candidate) else None


class CafRestDataPlane:
    """Real transport. Inject a fake with the same method surface for tests."""

    def __init__(self, location_id: str, pit: str | None,
                 redactor: redact.Redactor | None = None,
                 timeout: int = 30) -> None:
        self.location_id = location_id
        self._pit = pit
        self.redactor = redactor or redact.Redactor()
        if pit:
            self.redactor.register(pit)
        self.timeout = timeout
        self._session = requests.Session()
        self._tier0_write_supported: bool | None = None

    # -- Tier 0 caf -------------------------------------------------------
    def _run_caf(self, args: list[str]) -> Any:
        binary = _caf_binary()
        if not binary:
            raise Tier0Unavailable("caf binary not found")
        cmd = [binary, "--json", "--location-id", self.location_id, *args]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout,
                check=False, env=dict(os.environ),  # caf resolves its own token
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Tier0Unavailable(self.redactor.redact(str(exc))) from None
        if res.returncode != 0:
            raise Tier0Unavailable(self.redactor.redact(res.stderr.strip() or "caf non-zero exit"))
        try:
            return json.loads(res.stdout)
        except ValueError:
            raise Tier0Unavailable("caf did not return JSON") from None

    def _tier0_supports_custom_field_write(self) -> bool:
        if self._tier0_write_supported is not None:
            return self._tier0_write_supported
        binary = _caf_binary()
        if not binary:
            self._tier0_write_supported = False
            return False
        try:
            res = subprocess.run(
                [binary, "contacts", "update", "--help"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            help_text = (res.stdout + res.stderr).lower()
            self._tier0_write_supported = ("custom-field" in help_text
                                           or "custom_field" in help_text
                                           or "--field" in help_text)
        except (OSError, subprocess.SubprocessError):
            self._tier0_write_supported = False
        return self._tier0_write_supported

    # -- Tier 3 REST ------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if not self._pit:
            raise DataPlaneError("no Location token available for Tier 3")
        return redact.build_auth_header(self._pit)

    @staticmethod
    def _raise_for_rate_limit(resp: requests.Response) -> None:
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After") or resp.headers.get("X-RateLimit-Interval-Milliseconds")
            try:
                retry_after = float(retry) if retry is not None else None
            except ValueError:
                retry_after = None
            raise RateLimited(retry_after)

    def _rest_get(self, path: str) -> Any:
        url = f"{constants.LEADCONNECTOR_BASE_URL}{path}"
        try:
            resp = self._session.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise DataPlaneError(self.redactor.redact(str(exc))) from None
        self._raise_for_rate_limit(resp)
        if resp.status_code >= 400:
            raise DataPlaneError(self.redactor.redact(f"REST GET {resp.status_code}: {resp.text}"))
        return resp.json()

    def _rest_put(self, path: str, body: dict[str, Any]) -> Any:
        url = f"{constants.LEADCONNECTOR_BASE_URL}{path}"
        try:
            resp = self._session.put(url, headers=self._headers(),
                                     data=json.dumps(body), timeout=self.timeout)
        except requests.RequestException as exc:
            raise DataPlaneError(self.redactor.redact(str(exc))) from None
        self._raise_for_rate_limit(resp)
        if resp.status_code >= 400:
            raise DataPlaneError(self.redactor.redact(f"REST PUT {resp.status_code}: {resp.text}"))
        return resp.json()

    # -- normalizers ------------------------------------------------------
    @staticmethod
    def _unwrap_contact(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict) and isinstance(payload.get("contact"), dict):
            return payload["contact"]
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _unwrap_custom_fields(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            fields = payload.get("customFields")
            if isinstance(fields, list):
                return fields
        if isinstance(payload, list):
            return payload
        return []

    # -- public surface ---------------------------------------------------
    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Tier 0 caf first, Tier 3 REST fallback. Returns the contact dict."""
        try:
            return self._unwrap_contact(self._run_caf(["contacts", "get", contact_id]))
        except Tier0Unavailable:
            return self._unwrap_contact(self._rest_get(f"/contacts/{contact_id}"))

    def list_custom_fields(self) -> list[dict[str, Any]]:
        """Tier 0 caf first, Tier 3 REST fallback. Returns the field list."""
        try:
            return self._unwrap_custom_fields(self._run_caf(["locations", "custom-fields"]))
        except Tier0Unavailable:
            path = f"/locations/{self.location_id}/customFields"
            return self._unwrap_custom_fields(self._rest_get(path))

    def write_custom_fields(self, contact_id: str,
                            fields: list[dict[str, str]]) -> tuple[Any, str]:
        """Write custom fields by id. Returns (response, tier_used).

        fields is a list of {"id": <fieldId>, "value": <str>}. The current fleet
        caf contacts update carries no custom-field option, so a custom-field
        write is command-unsupported at Tier 0 and escalates to Tier 3 per the
        design Section 1 escalation rule. The capability is probed (result cached
        on the instance for observability) rather than assumed, so a future caf
        release that gains the write is detected; no speculative Tier 0 write is
        wired against an unverified subcommand."""
        # Records True or False on the instance; today it is False fleet-wide.
        self._tier0_supports_custom_field_write()
        body = {"customFields": [{"id": f["id"], "value": f["value"]} for f in fields]}
        return self._rest_put(f"/contacts/{contact_id}", body), "tier3"
