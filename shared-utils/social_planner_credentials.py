#!/usr/bin/env python3
"""
social_planner_credentials.py — F18 ONE documented credential resolver for the
social planner skills (35 and 57).

ONE module that both skills import instead of each restating its own
config-field/env-name mapping:

    from social_planner_credentials import (
        resolve_planner_credentials,   # full credential set + diagnostics
        CREDENTIAL_REPORT,             # per-credential diagnostic codes
    )

Precedence (EXPLICIT, highest first):
    1. config field          (the client config.json value)
    2. env canonical name    (process env + fleet env files via the Skill 44
                              canon — shared-utils/secret_helper.py)
    3. Skill 44 canonical resolver (key_resolver.resolve_key service lookup,
                              importable only; skipped silently when the
                              module is not on the path)

Conflicting values FAIL CLOSED: when the config field and an env canonical
name are BOTH set and DIFFER, resolution raises CredentialConflictError.
Silent precedence would let a stale config key or a leftover env var quietly
aim a publishing cycle at the wrong client — the exact cross-client risk F18
exists to close.

Diagnostics NEVER print a value. Every credential resolves to a report entry
with source + a boolean; the value itself is only ever handed back through the
resolver's return (used to authenticate, never logged).

Canonical names follow shared-utils/secret_names.json (the ONE secret-name
canon): GOHIGHLEVEL_API_KEY (GHL Private Integration Token) and
GOHIGHLEVEL_LOCATION_ID (prevents cross-location posting).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "resolve_planner_credentials",
    "CredentialConflictError",
    "CREDENTIAL_REPORT",
    "diagnose",
]


class CredentialConflictError(ValueError):
    """Config and env BOTH set for one credential and the values DIFFER.

    Never carries the values — only the canonical name and sources, so the
    error is safe to print or report to the client."""


# ---------------------------------------------------------------------------
# Skill 44 canonical resolver (importable-only dependency)
# ---------------------------------------------------------------------------
def _load_canon_resolver():
    """Import shared-utils/key_resolver.py when it is on the path.

    shared-utils is not a package and skills live in sibling directories, so
    this probes the well-known fleet locations (Mac ~/.openclaw/skills and VPS
    /data/.openclaw/skills) in addition to sys.path. Returns the module or
    None — the resolver is an OPTIONAL third tier, never a hard dependency.
    """
    if "key_resolver" in sys.modules:
        return sys.modules["key_resolver"]
    here = Path(__file__).resolve().parent
    candidates = [
        here,  # resolver deployed alongside this file in shared-utils
        here.parent / "shared-utils",
        Path.home() / ".openclaw" / "skills" / "shared-utils",
        Path("/data/.openclaw/skills/shared-utils"),
        Path("/data/.openclaw/skills/_shared/shared-utils"),
        Path.home() / ".openclaw" / "skills" / "_shared" / "shared-utils",
    ]
    for cand in list(candidates) + [Path(p) for p in sys.path if p]:
        try:
            if not cand.is_dir():
                continue
            target = cand / "key_resolver.py"
            if not target.is_file():
                continue
            spec = importlib.util.spec_from_file_location("key_resolver", target)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["key_resolver"] = mod  # cache: one canon load per process
            spec.loader.exec_module(mod)
            return mod
        except Exception:  # noqa: BLE001 — a broken resolver degrades to tier 2
            continue
    return None


# ---------------------------------------------------------------------------
# Credential table: field -> (config key, canonical env name, Skill 44 service)
# ---------------------------------------------------------------------------
CREDENTIALS: Dict[str, tuple] = {
    "pit": ("pit", "GOHIGHLEVEL_API_KEY", "ghl"),
    "location_id": ("locationId", "GOHIGHLEVEL_LOCATION_ID", "ghl_location_id"),
}


def _env_canonical(canonical: str) -> Optional[str]:
    """The canonical env name from the process env + fleet env-file canon."""
    try:
        from secret_helper import resolve_secret  # noqa: PLC0415 — optional tier

        value = resolve_secret(canonical)
        if value:
            return value
    except Exception:  # noqa: BLE001 — canon unavailable: fall back to os.environ
        pass
    value = os.environ.get(canonical, "")
    return value or None


def _skill44_service(service: str) -> Optional[str]:
    resolver = _load_canon_resolver()
    if resolver is None:
        return None
    try:
        return resolver.resolve_key(service)
    except Exception:  # noqa: BLE001 — tier 3 never raises
        return None


def _is_placeholder(value: str) -> bool:
    try:
        from secret_helper import is_placeholder  # noqa: PLC0415

        return bool(is_placeholder(value))
    except Exception:  # noqa: BLE001
        return False


def resolve_one(
    key: str,
    cfg: Optional[dict] = None,
    env: Optional[Dict[str, str]] = None,
) -> tuple:
    """Resolve ONE credential through the explicit precedence.

    Returns (value_or_None, report_entry). Raises CredentialConflictError when
    the config value and an env value are both present and differ.
    """
    cfg = cfg or {}
    env = env if env is not None else None
    config_field, canonical_env, service = CREDENTIALS[key]

    config_value = cfg.get(config_field)
    if isinstance(config_value, str) and not config_value.strip():
        config_value = None

    # Tier 2 consults ONLY the explicit env mapping in tests; production reads
    # the canonical env name through the fleet canon.
    if env is not None:
        env_value = env.get(canonical_env) or None
        skill44_value = None
    else:
        env_value = _env_canonical(canonical_env)
        skill44_value = _skill44_service(service)

    # Conflict: config and env both set and DIFFER -> fail closed.
    if config_value and env_value and config_value.strip() != env_value.strip():
        raise CredentialConflictError(
            "%s is set in BOTH the client config (%s) and the environment (%s) "
            "with DIFFERENT values — resolve the mismatch before running a "
            "publishing cycle. (Values are never printed.)"
            % (key, config_field, canonical_env)
        )

    if config_value:
        if _is_placeholder(config_value):
            return None, {"source": "config", "status": "placeholder", "set": False}
        return config_value, {"source": "config", "status": "ok", "set": True}
    if env_value:
        if _is_placeholder(env_value):
            return None, {"source": "env", "status": "placeholder", "set": False}
        return env_value, {"source": "env", "status": "ok", "set": True}
    if skill44_value:
        if _is_placeholder(skill44_value):
            return None, {"source": "skill44", "status": "placeholder", "set": False}
        return skill44_value, {"source": "skill44", "status": "ok", "set": True}
    return None, {"source": None, "status": "missing", "set": False}


def resolve_planner_credentials(
    cfg: Optional[dict] = None,
    env: Optional[Dict[str, str]] = None,
) -> tuple:
    """Resolve the full planner credential set.

    Returns (credentials, report). `credentials` maps key -> value-or-None;
    `report` maps key -> {source, status, set}. NEVER includes a value in the
    report. Raises CredentialConflictError on a config/env value mismatch.
    """
    creds: Dict[str, Optional[str]] = {}
    report: Dict[str, dict] = {}
    for key in CREDENTIALS:
        value, entry = resolve_one(key, cfg, env)
        creds[key] = value
        report[key] = entry
    return creds, report


def diagnose(report: Dict[str, dict]) -> List[str]:
    """Human-readable, REDACTED diagnostics: what is missing/broken and the
    remedy. Never contains a credential value — safe for receipts and logs."""
    lines: List[str] = []
    for key, entry in report.items():
        canonical_env = CREDENTIALS[key][1]
        if entry["status"] == "ok":
            lines.append("%s: OK (source: %s)." % (key, entry["source"]))
        elif entry["status"] == "placeholder":
            lines.append(
                "%s: present but placeholder-shaped under %s — replace it with "
                "the real credential in the client config or %s." % (key, entry["source"], canonical_env)
            )
        else:
            lines.append(
                "%s: MISSING — set %s in the client config or the %s "
                "environment variable (any canonical alias resolves)." % (key, CREDENTIALS[key][0], canonical_env)
            )
    return lines