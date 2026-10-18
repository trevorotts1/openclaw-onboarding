"""Auth context, tenant binding, alias-chain resolution and ``*_FILE`` input.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md sections 1.4 and 4.1.

Four credential classes are kept distinct and are never substituted for one
another: ``location_pit``, ``oauth``, ``agency_pit`` and ``firebase_internal``.
Agency aliases are explicitly unmapped in the freeze; they produce a fail-loud
refusal naming the variables, never a credential.

Nothing in this module prints or stores a secret value.  Only the source label
(``env:<NAME>`` / ``file:<NAME>`` / ``oauth:<NAME>``) is recorded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping

from .errors import ContractViolation, CredentialMissing


class AuthKind(str, Enum):
    location_pit = "location_pit"
    oauth = "oauth"
    agency_pit = "agency_pit"
    firebase_internal = "firebase_internal"


# Section 4.1, location PIT alias union.  Order is the frozen precedence.
LOCATION_PIT_ALIASES: tuple[str, ...] = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
    "GOHIGHLEVEL_PIT",
    "GOHIGHLEVEL_CF_PIT",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERT_AND_FLOW_PIT",
    "CONVERT_AND_FLOW_PRIVATE_INTEGRATION_TOKEN",
    "CONVERTANDFLOW_API_KEY",
    "CONVERTFLOW_API_KEY",
    "PODCAST_ENGINE_GHL_PIT",
)

LOCATION_PIT_FILE_ALIASES: tuple[str, ...] = ("GHL_LOCATION_PIT_FILE",)

FIREBASE_ALIASES: tuple[str, ...] = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
)

FIREBASE_FILE_ALIASES: tuple[str, ...] = ("GHL_REFRESH_TOKEN_FILE",)

# Explicitly unmapped: no operation in the freeze accepts agency auth.
AGENCY_PIT_ALIASES: tuple[str, ...] = (
    "GOHIGHLEVEL_AGENCY_PIT",
    "GOHIGHLEVEL_AGENCY_API_KEY",
    "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT",
    "GHL_AGENCY_PIT",
)

# Tenant binding aliases (caller-driven only; the adapter never infers).
LOCATION_ID_ALIASES: tuple[str, ...] = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
    "CONVERT_AND_FLOW_LOCATION_ID",
    "convert_and_flow_location",
    "CAF_LOCATION_ID",
    "CAF_ALLOWED_LOCATION_IDS",
    "HIGHLEVEL_LOCATION_ID",
    "PODCAST_ENGINE_GHL_LOCATION_ID",
)

LOCATION_ID_FILE_ALIASES: tuple[str, ...] = ("GHL_LOCATION_ID_FILE",)

_PLACEHOLDER_EXACT = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "change_me",
        "dummy",
        "none",
        "null",
        "placeholder",
        "replace-me",
        "replace_me",
        "tbd",
        "todo",
        "undefined",
        "xxxx",
    }
)
_PLACEHOLDER_PREFIXES = (
    "your-",
    "your_",
    "replace",
    "<",
    "${",
    "insert_",
    "insert-",
    "example",
    "dummy",
    "placeholder",
)


@dataclass(frozen=True)
class AuthContext:
    kind: AuthKind
    location_id: str | None
    resolve_secret: Callable[[str], str]
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AuthKind(self.kind))
        if not callable(self.resolve_secret):
            raise ContractViolation("auth_resolver_invalid")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ContractViolation("auth_source_missing")
        if self.kind in (AuthKind.location_pit, AuthKind.oauth):
            if not isinstance(self.location_id, str) or not self.location_id.strip():
                # The tenant is never inferred from the environment.
                raise ContractViolation(
                    "tenant_not_inferred", detail={"kind": self.kind.value}
                )
        elif self.location_id is not None:
            raise ContractViolation(
                "auth_kind_context_mixed",
                detail={"kind": self.kind.value, "field": "location_id"},
            )


@dataclass(frozen=True)
class TenantBinding:
    location_id: str
    source: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.location_id, str)
            or not self.location_id.strip()
            or is_placeholder(self.location_id)
        ):
            raise ContractViolation("tenant_invalid")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ContractViolation("tenant_source_missing")


def is_placeholder(value: object) -> bool:
    """Placeholder-shaped values are skipped everywhere (section 4.1)."""

    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered in _PLACEHOLDER_EXACT:
        return True
    return lowered.startswith(_PLACEHOLDER_PREFIXES)


def _lookup(env: Mapping[str, str], name: str) -> str | None:
    if name in env:
        return env[name]
    lowered = name.lower()
    for key, value in env.items():
        if str(key).lower() == lowered:
            return value
    return None


def _read_value_file(path: str) -> str | None:
    try:
        return Path(str(path)).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return None


def make_secret_resolver(
    env: Mapping[str, str] | None = None,
) -> Callable[[str], str]:
    """Build ``resolve_secret``: env name -> value, ``*_FILE`` reads a file."""

    source = os.environ if env is None else env

    def resolve(name: str) -> str:
        raw = _lookup(source, name)
        if raw is None or not str(raw).strip():
            raise CredentialMissing(detail={"name": name})
        if str(name).upper().endswith("_FILE"):
            value = _read_value_file(raw)
            if value is None:
                raise CredentialMissing(detail={"name": name, "reason": "file_unreadable"})
        else:
            value = str(raw).strip()
        if is_placeholder(value):
            raise CredentialMissing(detail={"name": name, "reason": "placeholder"})
        return value

    return resolve


def resolve_auth(
    *,
    kind: AuthKind,
    env: Mapping[str, str] | None = None,
    location_id: str | None = None,
    resolve_secret: Callable[[str], str] | None = None,
    secret_name: str | None = None,
    prefer_engine_tenant: bool = False,
) -> AuthContext:
    """Resolve one credential class through its frozen alias chain.

    ``location_id`` must be supplied by the caller for location-scoped classes.
    It is never read from the environment here.
    """

    auth_kind = AuthKind(kind)
    resolver = resolve_secret or make_secret_resolver(env)

    if auth_kind is AuthKind.agency_pit:
        raise ContractViolation(
            "agency_auth_unmapped",
            detail={"aliases": list(AGENCY_PIT_ALIASES)},
        )

    if auth_kind is AuthKind.oauth:
        if not secret_name:
            raise ContractViolation("oauth_secret_name_required")
        chain: list[tuple[str, str]] = [(str(secret_name), "oauth")]
    elif auth_kind is AuthKind.location_pit:
        chain = [(name, "file") for name in LOCATION_PIT_FILE_ALIASES]
        chain += _ordered_env_aliases(LOCATION_PIT_ALIASES, prefer_engine_tenant)
    else:  # firebase_internal
        chain = [(name, "file") for name in FIREBASE_FILE_ALIASES]
        chain += [(name, "env") for name in FIREBASE_ALIASES]

    tried: list[str] = []
    for name, label in chain:
        tried.append(name)
        try:
            value = resolver(name)
        except CredentialMissing:
            continue
        if is_placeholder(value):
            continue
        return AuthContext(
            kind=auth_kind,
            location_id=location_id,
            resolve_secret=resolver,
            source=f"{label}:{name}",
        )

    raise CredentialMissing(
        detail={"kind": auth_kind.value, "tried": tried},
    )


def _ordered_env_aliases(
    aliases: tuple[str, ...], prefer_engine_tenant: bool
) -> list[tuple[str, str]]:
    engine = [name for name in aliases if name.startswith("PODCAST_ENGINE_")]
    rest = [name for name in aliases if not name.startswith("PODCAST_ENGINE_")]
    ordered = engine + rest if prefer_engine_tenant else rest + engine
    return [(name, "env") for name in ordered]


def resolve_tenant_from_env(
    env: Mapping[str, str] | None = None,
) -> TenantBinding:
    """Explicit caller opt-in; the adapter itself never calls this.

    The tenant is a per-call argument.  This helper exists only so a caller can
    build the binding from the frozen alias map (including ``*_FILE``) instead
    of inventing a name.
    """

    source = os.environ if env is None else env
    chain = [(name, "file") for name in LOCATION_ID_FILE_ALIASES]
    chain += [(name, "env") for name in LOCATION_ID_ALIASES]
    tried: list[str] = []
    for name, label in chain:
        tried.append(name)
        raw = _lookup(source, name)
        if raw is None:
            continue
        if label == "file":
            value = _read_value_file(raw)
            if value is None:
                continue
        else:
            value = str(raw).strip()
        if "ALLOWED_LOCATION_IDS" in name and value:
            value = value.split(",")[0].strip()
        if is_placeholder(value):
            continue
        return TenantBinding(location_id=value, source=f"{label}:{name}")

    raise ContractViolation("tenant_not_inferred", detail={"tried": tried})


def secret_name(auth: AuthContext) -> str:
    """The variable/file name the resolver was built for.  Never a value."""

    source = str(getattr(auth, "source", "") or "")
    if ":" not in source:
        raise ContractViolation("auth_source_unreadable", detail={"source": source})
    label, name = source.split(":", 1)
    if label not in ("env", "file", "oauth") or not name:
        raise ContractViolation("auth_source_unreadable", detail={"source": source})
    return name


def secret_for(auth: AuthContext) -> str:
    """Resolve the credential value at the last possible moment."""

    return auth.resolve_secret(secret_name(auth))


def auth_headers(auth: AuthContext) -> dict[str, str]:
    """Headers for one call.  The value is never logged or recorded."""

    value = secret_for(auth)
    if not value:
        raise CredentialMissing(detail={"kind": auth.kind.value})
    if auth.kind is AuthKind.firebase_internal:
        return {"token-id": value}
    return {"Authorization": "Bearer " + value}
