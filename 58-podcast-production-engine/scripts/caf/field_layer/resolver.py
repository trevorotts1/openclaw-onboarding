#!/usr/bin/env python3
"""
Convert and Flow credential resolution: the field-layer call site.

Implements the ENV-CHECK-BEFORE-FAIL sequence (design Section 2.3) for the
Location Private Integration Token and the Location ID. A "missing" verdict is
valid only after every alias has been checked across every store, in order:

  1. live process environment first (os.environ; optional gateway pid or
     container probe)
  2. every environment-store file (three known stores plus platform .env)
  3. openclaw.json, BOTH env.vars.<KEY> and root-level env.<KEY>
  4. auth-profiles.json
  5. repeat 1 to 4 for all resolver aliases
  6. broad sweep last: grep -ril 'pit-' path-only, to flag a token filed under
     an unknown name

The shared fleet resolver (shared-utils/api_key_utils.py) is called as a
first-class store when importable so the field layer stays in lockstep with the
fleet resolver; the explicit stores below guarantee the full sequence even when
that import is unavailable or has not yet gained the Convert and Flow aliases.

Secrecy (design Section 7.3): no token value is ever returned in a public dict,
printed, logged, or placed in an exception. The value is held privately for the
Tier 3 Authorization header only.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from . import constants, redact

# ---------------------------------------------------------------------------
# Store scanners. Each returns a flat mapping {KEY: value} for the alias keys.
# ---------------------------------------------------------------------------

_ENV_FILE_STORES = [
    ("env-file:clawd-secrets", os.path.expanduser("~/clawd/secrets/.env")),
    ("env-file:openclaw", os.path.expanduser("~/.openclaw/.env")),
    ("env-file:clawdbot", os.path.expanduser("~/.clawdbot/.env")),
    ("env-file:data-openclaw", "/data/.openclaw/.env"),
]

_OPENCLAW_JSON_PATHS = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    "/data/.openclaw/openclaw.json",
]

_AUTH_PROFILE_PATHS = [
    os.path.expanduser("~/.openclaw/auth-profiles.json"),
    "/data/.openclaw/auth-profiles.json",
]

# Directories the path-only sweep walks for a token filed under an unknown name.
_SWEEP_DIRS = [
    os.path.expanduser("~/clawd/secrets"),
    os.path.expanduser("~/.openclaw"),
    os.path.expanduser("~/.clawdbot"),
    "/data/.openclaw",
]


def _parse_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.isfile(path):
        return values
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[key] = value
    except OSError:
        pass
    return values


def _openclaw_json_stores() -> list[tuple[str, dict[str, str]]]:
    """Return two logical stores per openclaw.json: env.vars.<KEY> and root
    env.<KEY> (both shapes exist in the fleet, design Section 2.3 step 3)."""
    env_vars: dict[str, str] = {}
    root_env: dict[str, str] = {}
    for path in _OPENCLAW_JSON_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (ValueError, OSError):
            continue
        env_block = data.get("env", {}) if isinstance(data, dict) else {}
        if isinstance(env_block, dict):
            vars_block = env_block.get("vars", {})
            if isinstance(vars_block, dict):
                for key, value in vars_block.items():
                    if isinstance(value, str):
                        env_vars.setdefault(key, value)
            for key, value in env_block.items():
                if key != "vars" and isinstance(value, str):
                    root_env.setdefault(key, value)
    return [("openclaw.json:env.vars", env_vars), ("openclaw.json:env.root", root_env)]


def _auth_profiles_store() -> dict[str, str]:
    """Shallow recursive scan of auth-profiles.json for alias-named string
    values. Defensive against unknown shapes."""
    found: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str):
                    found.setdefault(key, value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in _AUTH_PROFILE_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                walk(json.load(handle))
        except (ValueError, OSError):
            continue
    return found


def _gateway_process_env(gateway_pid: str | None, gateway_container: str | None,
                         keys: tuple[str, ...]) -> dict[str, str]:
    """Optional live gateway probe. Values are captured for resolution but are
    NEVER logged or returned publicly. On a Mac gateway parse `ps eww <pid>`;
    on a container use `docker exec <c> printenv <KEY>`."""
    values: dict[str, str] = {}
    if gateway_pid:
        try:
            out = subprocess.run(
                ["ps", "eww", str(gateway_pid)],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout
            # ps eww appends KEY=VALUE tokens on the command line.
            for token in out.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    if key in keys:
                        values.setdefault(key, value)
        except (OSError, subprocess.SubprocessError):
            pass
    if gateway_container:
        for key in keys:
            try:
                res = subprocess.run(
                    ["docker", "exec", gateway_container, "printenv", key],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                if res.returncode == 0:
                    value = res.stdout.strip()
                    if value:
                        values.setdefault(key, value)
            except (OSError, subprocess.SubprocessError):
                pass
    return values


def _shared_resolver_lookup(alias: str) -> str | None:
    """Call the shared fleet resolver as a first-class store, when importable.
    This is the field-layer call site into the SHARED resolver; the field layer
    never edits it."""
    try:
        import importlib
        import sys

        here = os.path.dirname(os.path.abspath(__file__))
        # scripts/caf/field_layer -> repo root is five parents up.
        root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
        shared = os.path.join(root, "shared-utils")
        if shared not in sys.path and os.path.isdir(shared):
            sys.path.insert(0, shared)
        module = importlib.import_module("api_key_utils")
        return module.get_api_key(alias)
    except Exception:
        return None


def _path_only_sweep() -> list[str]:
    """grep -ril 'pit-' across credential store directories. Filenames only, by
    construction (-l). File contents are never read into the report."""
    paths: list[str] = []
    for directory in _SWEEP_DIRS:
        if not os.path.isdir(directory):
            continue
        try:
            res = subprocess.run(
                ["grep", "-rilF", constants.PIT_PREFIX, directory],
                capture_output=True, text=True, timeout=20, check=False,
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if line:
                    paths.append(line)
        except (OSError, subprocess.SubprocessError):
            continue
    # De-dupe, keep order, cap so a noisy box cannot flood the report.
    seen: dict[str, None] = {}
    for path in paths:
        seen.setdefault(path, None)
    return list(seen.keys())[:50]


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass
class CredentialResolution:
    pit_found: bool = False
    pit_alias: str | None = None
    pit_store: str | None = None
    prefix_ok: bool = False
    pit_length: int = 0
    location_found: bool = False
    location_id: str | None = None
    location_alias: str | None = None
    location_store: str | None = None
    payload_location_mismatch: bool = False
    audit: list[dict[str, Any]] = field(default_factory=list)
    sweep_paths: list[str] = field(default_factory=list)
    _pit: str | None = None  # held in memory only, never serialized

    def pit(self) -> str | None:
        return self._pit

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "pit_found": self.pit_found,
            "pit_alias": self.pit_alias,
            "pit_store": self.pit_store,
            "prefix_ok": self.prefix_ok,
            "pit_length": self.pit_length,
            "location_found": self.location_found,
            "location_id": self.location_id,
            "location_alias": self.location_alias,
            "location_store": self.location_store,
            "payload_location_mismatch": self.payload_location_mismatch,
            "audit": self.audit,
            "sweep_paths": self.sweep_paths,
        }


def _build_stores(keys: tuple[str, ...], gateway_pid: str | None,
                  gateway_container: str | None) -> list[tuple[str, dict[str, str]]]:
    """Ordered list of (store_name, mapping). Live env first (design 2.3)."""
    stores: list[tuple[str, dict[str, str]]] = []
    # 1. live process environment first
    live = dict(os.environ)
    probe = _gateway_process_env(gateway_pid, gateway_container, keys)
    live.update(probe)  # gateway probe augments the current process env
    stores.append(("live-process-env", live))
    # 2. environment-store files
    for name, path in _ENV_FILE_STORES:
        stores.append((name, _parse_env_file(path)))
    # 3. openclaw.json both shapes
    stores.extend(_openclaw_json_stores())
    # 4. auth-profiles.json
    stores.append(("auth-profiles.json", _auth_profiles_store()))
    return stores


def _resolve_one(aliases: tuple[str, ...], forbidden: tuple[str, ...],
                 stores: list[tuple[str, dict[str, str]]],
                 audit: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    """First hit wins, canonical alias first, live store first. Returns
    (value, winning_alias, winning_store). Records every alias by store in the
    audit as FOUND or not (value never recorded)."""
    winner: tuple[str | None, str | None, str | None] = (None, None, None)
    for alias in aliases:
        if alias in forbidden:
            continue
        for store_name, mapping in stores:
            present = bool(mapping.get(alias))
            audit.append({"alias": alias, "store": store_name, "found": present})
            if present and winner[0] is None:
                winner = (mapping[alias], alias, store_name)
        # Shared fleet resolver as an additional store for this alias.
        shared_value = _shared_resolver_lookup(alias)
        shared_present = bool(shared_value)
        audit.append({"alias": alias, "store": "shared-fleet-resolver", "found": shared_present})
        if shared_present and winner[0] is None:
            winner = (shared_value, alias, "shared-fleet-resolver")
    return winner


def resolve_credentials(
    *,
    payload_location_id: str | None = None,
    gateway_pid: str | None = None,
    gateway_container: str | None = None,
    run_sweep: bool = True,
) -> CredentialResolution:
    """Full ENV-CHECK-BEFORE-FAIL resolution for the field layer."""
    result = CredentialResolution()

    pit_keys = constants.LOCATION_PIT_ALIASES
    loc_keys = constants.LOCATION_ID_ALIASES
    all_keys = tuple(dict.fromkeys((*pit_keys, *loc_keys)))
    stores = _build_stores(all_keys, gateway_pid, gateway_container)

    # Resolve the Location PIT.
    pit_value, pit_alias, pit_store = _resolve_one(
        pit_keys, constants.FORBIDDEN_PIT_ALIASES, stores, result.audit
    )
    if pit_value:
        result.pit_found = True
        result.pit_alias = pit_alias
        result.pit_store = pit_store
        result.prefix_ok = redact.prefix_ok(pit_value)
        result.pit_length = redact.safe_len(pit_value)
        result._pit = pit_value

    # Resolve the Location ID (not secret; an identifier).
    loc_value, loc_alias, loc_store = _resolve_one(
        loc_keys, (), stores, result.audit
    )
    if loc_value:
        result.location_found = True
        result.location_id = loc_value
        result.location_alias = loc_alias
        result.location_store = loc_store

    # Payload location must match the environment value (design Section 2.2).
    if payload_location_id and result.location_id:
        result.payload_location_mismatch = payload_location_id != result.location_id

    # Broad sweep last, path-only.
    if run_sweep and not result.pit_found:
        result.sweep_paths = _path_only_sweep()

    return result
