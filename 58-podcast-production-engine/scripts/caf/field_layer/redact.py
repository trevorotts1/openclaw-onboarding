#!/usr/bin/env python3
"""
Secrecy wrapper for the Convert and Flow field layer (design Section 7.3).

Absolute rule: the Private Integration Token value never appears in stdout,
stderr, logs, JSON output, exceptions, or tracebacks. Every string the layer
emits passes through the Redactor, which scrubs any registered secret. Reports
say only: alias name, store name, SET or NOT SET, prefix_ok, length.
"""
from __future__ import annotations

from typing import Iterable

from . import constants

_REDACTION = "[REDACTED]"


class Redactor:
    """Holds registered secret values and scrubs them from any emitted string.

    Values are held in memory only. The class never logs, prints, or serializes
    a registered secret. register() ignores empty and very short values so a
    stray one character secret can never turn every "a" in a report into noise.
    """

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def register(self, *values: str | None) -> None:
        for value in values:
            if value and len(value) >= 6:
                self._secrets.add(value)

    def register_many(self, values: Iterable[str | None]) -> None:
        self.register(*values)

    def redact(self, text: object) -> str:
        out = str(text)
        for secret in self._secrets:
            if secret and secret in out:
                out = out.replace(secret, _REDACTION)
        return out

    def scrub_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Return a copy safe to log: Authorization is masked entirely."""
        safe: dict[str, str] = {}
        for name, value in headers.items():
            if name.lower() == "authorization":
                safe[name] = "Bearer [REDACTED]"
            else:
                safe[name] = self.redact(value)
        return safe


def prefix_ok(token: str | None) -> bool:
    """True only when the token carries the Location PIT prefix."""
    return bool(token) and token.startswith(constants.PIT_PREFIX)


def safe_len(token: str | None) -> int:
    """Length only, never any character of the value."""
    return len(token) if token else 0


def build_auth_header(token: str) -> dict[str, str]:
    """Authorization header built in memory. Never log the returned dict raw;
    pass it through Redactor.scrub_headers first."""
    return {
        "Authorization": f"Bearer {token}",
        "Version": constants.GHL_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
