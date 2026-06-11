"""Shared types for the internal adapter — no circular imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdapterResult:
    """Normalized result from any InternalAdapter call.

    Replaces the legacy tri-state (success dict / None / {"_error":True,...}).
    All three outcomes map here; the shim in ghl_internal_client.py maps back
    to the legacy shape for callers not yet migrated.
    """
    ok: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    http_code: Optional[int] = None

    def get(self, key: str, default=None):
        """dict-like .get() delegating to self.data (shim backward-compat)."""
        if self.data is None:
            return default
        return self.data.get(key, default)


class AdapterError(Exception):
    """Raised by InternalTransport instead of sys.exit(1).

    Attributes:
        code    -- machine-readable error code (e.g. "NO_TOKEN", "TOKEN_REFRESH_FAILED")
        message -- human-readable detail
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message


@dataclass
class ProbeResult:
    """Result of a ContractProbe run."""
    ok: bool
    reason: str = ""
    failed_assertion: str = ""
    checked_at: str = ""          # UTC ISO timestamp
    scope: str = "contract"       # "token" | "contract"
