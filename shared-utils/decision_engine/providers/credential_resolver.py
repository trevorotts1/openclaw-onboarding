#!/usr/bin/env python3
"""D06 client-scoped credential resolution (JEV spec 1.1, sections 3.3 + 3.8).

Stdlib only. No network, no filesystem, no state writes — and by design this
module never reads the live process table. The caller passes every candidate
store in explicitly; on a shared process the only lawful inputs are
company-scoped stores plus a process snapshot the caller has already bound
to the requesting company.

Scope rules (spec 3.3), enforced before any value is looked at:

  * Company-scoped stores are consulted first, in caller order.
  * A store tagged with another company's id is skipped WITHOUT reading its
    values (never scan another company's directory or auth profiles).
  * An unscoped (company_id None) store — operator/global key, raw process
    environment — is eligible only when the context proves a single-company
    installation, or the store is explicitly bound to the requesting company.
    On a shared installation it is not a fallback credential.
  * Read-only: nothing here rotates, overwrites, copies, or prints a secret.
    Sanitized logs carry provider, source category, state, error category only.

Value rules (spec 3.3): empty values, unresolved placeholders, and malformed
references are rejected before any call. Presence means ``configured``, never
``verified_working`` — only a successfully validated decisions response
establishes the latter, which this resolver can never observe.

Permission rules (spec 3.8): a usable credential answers neither the spend nor
the transmit question. Every status therefore carries ``authorizes_spend`` and
``authorizes_transmit`` pinned to False; something else (policy/budget checks
at the send boundary) must answer those.

Key names (spec 3.3): ``TYPESAFE_API_KEY`` is the documented direct key,
``JEV_API_KEY`` is the explicitly documented project compatibility alias for
the direct route (not a claim about TypeSafe's native SDK), and
``OPENROUTER_API_KEY`` serves OpenRouter. The extra OpenRouter aliases below
are already-documented names found in this repository's own readers
(``api_key_utils.KEY_PATTERNS``); the route key sets are closed and disjoint —
nothing is guessed from arbitrary secret names. New aliases arrive only with a
spec/doc update, never by fuzzy matching here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

DIRECT_ROUTE = "direct"
OPENROUTER_ROUTE = "openrouter"

TYPESAFE_API_KEY = "TYPESAFE_API_KEY"
JEV_API_KEY = "JEV_API_KEY"  # project compatibility alias for the direct route
OPENROUTER_API_KEY = "OPENROUTER_API_KEY"

# Closed per-route key sets. Disjoint by construction (collision test locks it).
DIRECT_KEYS: Tuple[str, ...] = (TYPESAFE_API_KEY, JEV_API_KEY)
OPENROUTER_KEYS: Tuple[str, ...] = (
    OPENROUTER_API_KEY,
    "OPENROUTER_KEY",
    "OPEN_ROUTER_API_KEY",
)
ROUTE_KEYS: Dict[str, Tuple[str, ...]] = {
    DIRECT_ROUTE: DIRECT_KEYS,
    OPENROUTER_ROUTE: OPENROUTER_KEYS,
}

# Resolution states. ``configured`` is presence only — never verified working.
STATE_CONFIGURED = "configured"
STATE_ABSENT = "absent"
STATE_REJECTED_EMPTY = "rejected_empty"
STATE_REJECTED_PLACEHOLDER = "rejected_placeholder"
STATE_REJECTED_MALFORMED = "rejected_malformed"
STATE_REJECTED_UNSCOPED = "rejected_unscoped"
STATE_ERROR = "error"


@dataclass(frozen=True)
class CredentialStatus:
    """Outcome for one route. Carries no secret value, ever."""

    route: str
    state: str
    source_category: Optional[str] = None
    key_name: Optional[str] = None
    configured: bool = False
    # 3.3: only a validated decisions response establishes working state.
    verified_working: bool = False
    # 3.8: presence answers neither permission question. Always False here.
    authorizes_spend: bool = False
    authorizes_transmit: bool = False
    error_category: Optional[str] = None
    skipped_sources: Tuple[str, ...] = ()


# Whole-value matches (case-insensitive): the entire value is one of these.
_WHOLE_VALUE_NONKEYS = frozenset({
    "", "null", "none", "undefined", "n/a", "na", "nil", "empty",
    "test", "demo", "example", "sample", "missing", "unset", "false",
    "no", "nope", "tbd", "todo",
})

# Substring markers (case-insensitive): value was never a real credential.
_PLACEHOLDER_MARKERS = (
    "xxxxx", "your_key", "your-key", "yourkey", "your_api", "your-api",
    "your_token", "your-token", "replace_me", "replace-me", "replaceme",
    "changeme", "change_me", "change-me", "placeholder", "example",
    "sample_key", "sample-key", "dummy", "demo_key", "demo-key",
    "test_key", "test-key", "fake_key", "fake-key", "sk-test", "sk-xxx",
    "sk-example", "sk-replace", "fill_in", "fill-in", "fillin",
    "paste-your", "paste_your", "paste-real", "paste_real", "pastereal",
    "insert_your", "insert-your", "enter_your", "enter-your",
    "set_your", "set-your", "no_key", "nokey", "none_yet",
    "not_set", "not-set", "enter-", "<todo>", "{{", "}}",
)

_MIN_CREDENTIAL_LEN = 8


def _classify_value(value) -> Optional[str]:
    """Return None when usable, else the rejection state for the value."""
    if not isinstance(value, str):
        return STATE_REJECTED_MALFORMED
    stripped = value.strip()
    if not stripped:
        return STATE_REJECTED_EMPTY
    # Unresolved template / interpolation shapes are malformed references.
    # Checked before placeholder markers so "<TODO>" reads as malformed.
    if stripped.startswith("<") and stripped.endswith(">"):
        return STATE_REJECTED_MALFORMED
    if stripped.startswith("[") and stripped.endswith("]"):
        return STATE_REJECTED_MALFORMED
    if "${" in stripped:
        return STATE_REJECTED_MALFORMED
    low = stripped.lower()
    if low in _WHOLE_VALUE_NONKEYS:
        return STATE_REJECTED_PLACEHOLDER
    for marker in _PLACEHOLDER_MARKERS:
        if marker in low:
            return STATE_REJECTED_PLACEHOLDER
    if low.startswith("undefined"):
        return STATE_REJECTED_MALFORMED
    if any(ch.isspace() for ch in stripped):
        return STATE_REJECTED_MALFORMED
    if len(stripped) < _MIN_CREDENTIAL_LEN:
        return STATE_REJECTED_MALFORMED
    return None


def _store_company(store: Mapping) -> Optional[str]:
    company = store.get("company_id")
    if company is None:
        return None
    if isinstance(company, str) and company.strip():
        return company
    return None


def resolve_provider_key(
    route: str,
    company_id: str,
    stores: Sequence[Mapping] = (),
    context: Optional[Mapping] = None,
) -> CredentialStatus:
    """Resolve one route's credential for one company. Never raises on data.

    ``stores``: sequence of ``{"source_category": str,
    "company_id": str | None, "values": {name: value}}``. ``company_id`` None
    marks an unscoped (operator/global/process-env) store.
    ``context``: ``{"single_company_installation": bool}`` — proven, not
    assumed. Defaults to shared (False).
    """
    ctx = dict(context or {})
    single_company = ctx.get("single_company_installation") is True
    skipped: List[str] = []

    if not isinstance(company_id, str) or not company_id.strip():
        return CredentialStatus(
            route=route, state=STATE_ERROR, error_category="company_id_required",
        )
    if route not in ROUTE_KEYS:
        return CredentialStatus(
            route=route, state=STATE_ERROR, error_category="unknown_route",
        )

    def eligible(store: Mapping) -> bool:
        tagged = _store_company(store)
        if tagged is None:
            return single_company
        return tagged == company_id

    # Pass 1: company-scoped stores, caller order. Pass 2: eligible unscoped.
    scoped = [s for s in stores if isinstance(s, Mapping) and _store_company(s) == company_id]
    unscoped = [
        s for s in stores
        if isinstance(s, Mapping) and _store_company(s) is None and eligible(s)
    ]
    for s in stores:
        if not isinstance(s, Mapping):
            continue
        tagged = _store_company(s)
        if tagged is not None and tagged != company_id:
            skipped.append(f"{s.get('source_category', 'unknown')}:other_company")
        elif tagged is None and not single_company:
            vals = s.get("values")
            if isinstance(vals, Mapping) and vals:
                skipped.append(
                    f"{s.get('source_category', 'unknown')}:unscoped_on_shared")

    first_defect: Optional[Tuple[str, str, str]] = None  # (state, category, key)
    saw_unscoped_value = False
    for store in list(scoped) + list(unscoped):
        values = store.get("values")
        if not isinstance(values, Mapping):
            continue
        category = str(store.get("source_category", "unknown"))
        for key in ROUTE_KEYS[route]:
            if key not in values:
                continue
            if _store_company(store) is None:
                saw_unscoped_value = True
            rejection = _classify_value(values[key])
            if rejection is None:
                return CredentialStatus(
                    route=route, state=STATE_CONFIGURED,
                    source_category=category, key_name=key, configured=True,
                    skipped_sources=tuple(skipped),
                )
            if first_defect is None:
                first_defect = (rejection, category, key)
    if first_defect is not None:
        state, _, _ = first_defect
        return CredentialStatus(
            route=route, state=state, error_category=state,
            skipped_sources=tuple(skipped),
        )
    if saw_unscoped_value:
        # Values existed only where they may not be used (defensive; normally
        # unreachable since ineligible stores are excluded above).
        return CredentialStatus(
            route=route, state=STATE_REJECTED_UNSCOPED,
            error_category=STATE_REJECTED_UNSCOPED,
            skipped_sources=tuple(skipped),
        )
    unusable_only = any(s.endswith(":unscoped_on_shared") for s in skipped)
    if unusable_only and skipped:
        return CredentialStatus(
            route=route, state=STATE_REJECTED_UNSCOPED,
            error_category=STATE_REJECTED_UNSCOPED,
            skipped_sources=tuple(skipped),
        )
    return CredentialStatus(
        route=route, state=STATE_ABSENT, error_category=STATE_ABSENT,
        skipped_sources=tuple(skipped),
    )


def resolve_company_credentials(
    company_id: str,
    stores: Sequence[Mapping] = (),
    context: Optional[Mapping] = None,
) -> Dict[str, CredentialStatus]:
    """Resolve both JEV routes for one company. Never raises on data."""
    return {
        route: resolve_provider_key(route, company_id, stores, context)
        for route in ROUTE_KEYS
    }


def sanitized_log_line(status: CredentialStatus) -> str:
    """One log line: provider, source category, state, error category. No values."""
    return (
        f"route={status.route} "
        f"source={status.source_category or 'none'} "
        f"state={status.state} "
        f"error={status.error_category or 'none'} "
        f"configured={int(status.configured)} "
        f"verified_working={int(status.verified_working)}"
    )


def sanitized_summary(resolution: Mapping[str, CredentialStatus]) -> List[str]:
    """Sanitized log lines for a full resolution. No values."""
    return [sanitized_log_line(resolution[route]) for route in ROUTE_KEYS]
