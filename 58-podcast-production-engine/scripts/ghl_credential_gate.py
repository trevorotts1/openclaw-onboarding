#!/usr/bin/env python3
"""ghl_credential_gate.py, the Convert and Flow credential gate for the Podcast Production Engine.

WHY THIS EXISTS
---------------
No Convert and Flow (GoHighLevel) operation in the podcast engine runs unless this
gate has passed for this client in this run. It is the enforcement point behind
PRD Section 4 gap 4 and ghl-design.md Section 7: per-client isolation is proven,
not asserted. The pipeline invokes it at Step 0 (full mode, with --check-fields)
and re-invokes it cheaply (cached mode) before Steps 14 to 17.

The credential in question is ONE value with many names: the Location Private
Integration Token (PIT), prefix pit-. It is identically the "GHL API key", the
"GoHighLevel API key", the "Convert and Flow API key", and the "private
integration token". This gate must never conclude a credential is missing merely
because a client stored it under a different alias, and it must never accept an
Agency PIT or a Firebase refresh token in its place (those are different
credentials for different purposes and are deliberately excluded from the alias
list below).

Naming rule: internal code and operator logs may say GHL for brevity; every
client-visible string says "Convert and Flow", never GoHighLevel and never GHL.
This script emits to the operator channel only and is never client-facing.

EXIT CODES (the verdict codes; ghl-design.md Section 7.1)
--------------------------------------------------------
  0  PASS, every requested check passed.
  2  Credential MISSING, valid only after the full ENV-CHECK-BEFORE-FAIL sweep
     over every alias and every store (Section 2.3) finds nothing usable.
  3  ISOLATION VIOLATION, a pairing mismatch, a webhook/env Location mismatch, or
     a commingling fingerprint under a different client. Hard abort, founder alert.
  4  Required custom FIELDS missing (client must contact support for the snapshot;
     fields are never created silently).
  5  Rate FLOOR not met (the per-Location daily budget is too low to safely start
     a publish phase that could die mid-write).
  1  Gate could NOT complete (infrastructure or usage error, for example the
     pairing endpoint was unreachable). This is not a credential verdict; retry.

SECRECY RULES (absolute, enforced in code; Section 7.3)
-------------------------------------------------------
  * The PIT value never appears in stdout, stderr, logs, JSON output, exceptions,
    or tracebacks. A module-level redactor scrubs the resolved value from every
    string this process emits.
  * Reports say only: alias name, store name, SET or NOT SET, prefix_ok, length.
  * The unknown-name sweep is filename-only by construction; file contents are
    never read into any report.
  * The token travels only inside an in-memory Authorization header. It never
    reaches a shell string, subprocess argv, or an environment dump.
  * No mode, flag, or verbosity level weakens any of the above.

This module is standard-library only on purpose: it must run unmodified on every
client box (Mac mini or Virtual Private Server) with no pip install step. It also
never writes config as root (root-owned config freezes the gateway), so state
persistence is skipped when the effective user id is 0.
"""
from __future__ import annotations

import argparse
import calendar
import glob
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #
EXIT_PASS = 0
EXIT_INCOMPLETE = 1
EXIT_MISSING = 2
EXIT_ISOLATION = 3
EXIT_FIELDS = 4
EXIT_RATE_FLOOR = 5

# --------------------------------------------------------------------------- #
# Alias tables (ghl-design.md Section 2.2). LOCATION-PIT ONLY. The Agency PIT
# (GOHIGHLEVEL_AGENCY_PIT) and the Firebase refresh token are DELIBERATELY absent:
# they are separate credentials and must never satisfy this gate.
# --------------------------------------------------------------------------- #
PIT_ALIASES: List[str] = [
    # 11 canonical, first hit wins, canonical name first.
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
    # Convert and Flow branded additions (Section 2.2 recommendation). These also
    # land in the SHARED resolver (Skills 29/36/44) in a separate merge slice; the
    # gate carries its own authoritative copy so a sub-agent never depends on the
    # shared resolver already having them.
    "CONVERTFLOW_API_KEY",
    "CONVERTANDFLOW_API_KEY",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERTFLOW_PIT",
    "CONVERTANDFLOW_PIT",
]

LOCATION_ALIASES: List[str] = [
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "LOCATION_ID",
    "CONVERTANDFLOW_LOCATION_ID",
    "CONVERTFLOW_LOCATION_ID",
]

# --------------------------------------------------------------------------- #
# Required custom-field keys (ghl-design.md Sections 3.2/3.3). Stored as BARE
# keys (the "contact." prefix is stripped before comparison). Exact-match only:
# the double underscore in podcast_survey__additional_info is asserted and the
# single-underscore variant is never accepted as a substitute.
# --------------------------------------------------------------------------- #
REQUIRED_READ_FIELDS: List[str] = [
    "podcast_survey_writing_style",
    "my_preferred_pronoun",
    "podcast_interview_smiq",
    "podcast_survey__additional_info",  # DOUBLE underscore, asserted exactly.
]
REQUIRED_WRITE_FIELDS: List[str] = [
    "podcast_survey_episode_url",
    "podcast_survey_episode_title",
    "podcast_survey_episode_description",
    "finish_podcast_google_doc_link",
    "podcast_transcript_link",
]
REQUIRED_FIELDS: List[str] = REQUIRED_READ_FIELDS + REQUIRED_WRITE_FIELDS
BOOK_TEASER_FIELD = "book_teaser"  # Interview-mode only; ABSENT is reported, never fails the gate.
SINGLE_UNDERSCORE_TRAP = "podcast_survey_additional_info"  # never a valid substitute.

# --------------------------------------------------------------------------- #
# HTTP / rate config
# --------------------------------------------------------------------------- #
DEFAULT_API_BASE = "https://services.leadconnectorhq.com"
API_VERSION_HEADER = "2021-07-28"
HTTP_TIMEOUT_SECONDS = 20
# Header casing is confirmed against a live response during the operator-box
# canary (ghl-design.md Section 10 open item 4); we look these up case-insensitively.
RATE_REMAINING_HEADER_CANDIDATES = [
    "x-ratelimit-daily-remaining",
    "x-ratelimit-remaining-daily",
    "x-ratelimit-daily-remain",
]
DEFAULT_EPISODE_BUDGET = 30  # worst-case Interview-mode requests per episode (Section 6).
CACHE_FRESH_SECONDS = 24 * 3600

# --------------------------------------------------------------------------- #
# Env-store discovery (Section 2.3 step 2). Live process env is handled
# separately and always comes FIRST.
# --------------------------------------------------------------------------- #
ENV_FILE_PATHS: List[str] = [
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.openclaw/.env"),
    "/data/.openclaw/.env",
    os.path.expanduser("~/.env"),
    os.path.expanduser("~/.clawdbot/.env"),
]
# Hostinger-style hosts keep env at /docker/<project>/.env (fleet doctrine).
ENV_FILE_GLOBS: List[str] = ["/docker/*/.env"]
OPENCLAW_JSON_PATHS: List[str] = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    "/data/.openclaw/openclaw.json",
]
AUTH_PROFILES_PATHS: List[str] = [
    os.path.expanduser("~/.openclaw/auth-profiles.json"),
    "/data/.openclaw/auth-profiles.json",
]
# Directories the filename-only "pit-" sweep may scan (contents never emitted).
SWEEP_DIRS: List[str] = [
    os.path.expanduser("~/clawd/secrets"),
    os.path.expanduser("~/.openclaw"),
    "/data/.openclaw",
]

# Store labels (never carry values).
STORE_LIVE_SELF = "live-process-env(self)"
STORE_LIVE_GATEWAY = "live-process-env(gateway)"


# --------------------------------------------------------------------------- #
# Redaction: nothing this process emits may contain the PIT value.
# --------------------------------------------------------------------------- #
class Redactor:
    """Holds secret values and scrubs them from any string before it is emitted."""

    def __init__(self) -> None:
        self._secrets: List[str] = []

    def register(self, secret: Optional[str]) -> None:
        if secret and isinstance(secret, str) and len(secret) >= 6:
            if secret not in self._secrets:
                self._secrets.append(secret)

    def scrub(self, text: str) -> str:
        if not isinstance(text, str):
            text = str(text)
        for secret in self._secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def out(self, text: str = "") -> None:
        sys.stdout.write(self.scrub(text) + "\n")

    def err(self, text: str = "") -> None:
        sys.stderr.write(self.scrub(text) + "\n")


REDACTOR = Redactor()


class GateIncomplete(RuntimeError):
    """Raised when the gate cannot reach a verdict for an infrastructure reason.

    Maps to EXIT_INCOMPLETE. Distinct from a real credential verdict so a
    transient network failure never masquerades as an isolation violation.
    """


# --------------------------------------------------------------------------- #
# Env-store parsing (values kept in memory only, never emitted)
# --------------------------------------------------------------------------- #
def _parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not os.path.isfile(path):
        return values
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
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


def _openclaw_json_maps(path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (env.vars.<KEY>, root env.<KEY>) as two maps; both shapes exist in the fleet."""
    env_vars: Dict[str, str] = {}
    root_env: Dict[str, str] = {}
    if not os.path.isfile(path):
        return env_vars, root_env
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return env_vars, root_env
    env = data.get("env", {})
    if isinstance(env, dict):
        vars_map = env.get("vars", {})
        if isinstance(vars_map, dict):
            for k, v in vars_map.items():
                if isinstance(v, str):
                    env_vars[k] = v
        for k, v in env.items():
            if k == "vars":
                continue
            if isinstance(v, str):
                root_env[k] = v
    return env_vars, root_env


def _auth_profiles_map(path: str) -> Dict[str, str]:
    """Flatten string leaves of auth-profiles.json into a KEY->value map (best effort)."""
    out: Dict[str, str] = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return out

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    out.setdefault(k, v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return out


def _live_gateway_env() -> Dict[str, str]:
    """Best-effort read of the RUNNING gateway's environment (Section 2.3 step 1).

    Values are captured to memory only and never emitted. Discovery is explicit
    (env overrides or a pid file) so we never guess a wrong process and leak.
    Containerized boxes set GHL_GATEWAY_CONTAINER; Mac boxes may set
    GHL_GATEWAY_PID or drop a pid file. os.environ (the self process) is the
    always-present live layer and is handled by the caller.
    """
    found: Dict[str, str] = {}
    keys = PIT_ALIASES + LOCATION_ALIASES

    container = os.environ.get("GHL_GATEWAY_CONTAINER", "").strip()
    if container:
        for key in keys:
            try:
                res = subprocess.run(
                    ["docker", "exec", container, "printenv", key],
                    capture_output=True, text=True, timeout=8, check=False,
                )
                val = res.stdout.strip() if res.returncode == 0 else ""
                if val:
                    found[key] = val
            except (OSError, subprocess.SubprocessError):
                break  # docker unavailable; stop probing.

    pid = os.environ.get("GHL_GATEWAY_PID", "").strip()
    if not pid:
        for pid_file in (
            os.path.expanduser("~/.openclaw/gateway.pid"),
            "/data/.openclaw/gateway.pid",
        ):
            if os.path.isfile(pid_file):
                try:
                    with open(pid_file, "r", encoding="utf-8") as fh:
                        pid = fh.read().strip()
                except OSError:
                    pid = ""
                if pid:
                    break
    if pid and pid.isdigit():
        try:
            res = subprocess.run(
                ["ps", "eww", "-p", pid],
                capture_output=True, text=True, timeout=8, check=False,
            )
            if res.returncode == 0:
                for tok in res.stdout.split():
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        if k in keys and v and k not in found:
                            found[k] = v
        except (OSError, subprocess.SubprocessError):
            pass
    return found


# --------------------------------------------------------------------------- #
# Store enumeration: an ordered list of (store_label, {KEY: value}) maps.
# Live process env FIRST, then files, then openclaw.json, then auth-profiles.json.
# --------------------------------------------------------------------------- #
def _ordered_stores() -> List[Tuple[str, Dict[str, str]]]:
    stores: List[Tuple[str, Dict[str, str]]] = []
    # 1. Live process env (self) is the truth the agent executes with.
    stores.append((STORE_LIVE_SELF, dict(os.environ)))
    # 1b. Live gateway env (explicit discovery only).
    gw = _live_gateway_env()
    if gw:
        stores.append((STORE_LIVE_GATEWAY, gw))
    # 2. Env-store files.
    file_paths = list(ENV_FILE_PATHS)
    for pattern in ENV_FILE_GLOBS:
        file_paths.extend(sorted(glob.glob(pattern)))
    extra = os.environ.get("GHL_EXTRA_ENV_FILES", "")
    if extra:
        file_paths.extend(p for p in extra.split(":") if p)
    for path in file_paths:
        parsed = _parse_env_file(path)
        if parsed:
            stores.append((f"envfile:{path}", parsed))
    # 3. openclaw.json, BOTH shapes.
    for path in OPENCLAW_JSON_PATHS:
        env_vars, root_env = _openclaw_json_maps(path)
        if env_vars:
            stores.append((f"openclaw.json:env.vars:{path}", env_vars))
        if root_env:
            stores.append((f"openclaw.json:env:{path}", root_env))
    # 4. auth-profiles.json.
    for path in AUTH_PROFILES_PATHS:
        ap = _auth_profiles_map(path)
        if ap:
            stores.append((f"auth-profiles.json:{path}", ap))
    return stores


def _resolve(aliases: List[str], stores: List[Tuple[str, Dict[str, str]]]) -> Dict[str, object]:
    """Resolve an alias set across ordered stores. First (alias, store) hit wins,
    but the full audit (every alias x every store) is always recorded.

    Returns {value, winner_alias, winner_store, audit} where audit maps
    alias -> list of store labels the alias was found in. VALUES ARE NEVER in audit.
    """
    audit: Dict[str, List[str]] = {a: [] for a in aliases}
    winner_value: Optional[str] = None
    winner_alias: Optional[str] = None
    winner_store: Optional[str] = None
    for store_label, kv in stores:
        for alias in aliases:
            val = kv.get(alias)
            if val:
                audit[alias].append(store_label)
                if winner_value is None:
                    winner_value = val
                    winner_alias = alias
                    winner_store = store_label
    return {
        "value": winner_value,
        "winner_alias": winner_alias,
        "winner_store": winner_store,
        "audit": {a: s for a, s in audit.items() if s},  # only found rows.
    }


def _unknown_name_sweep() -> List[str]:
    """Filename-only sweep for a pit- value stored under an unknown key.

    Diagnostic ONLY (a value under an unknown name is never trusted; it could be
    an Agency PIT or another client's token). Returns FILE PATHS ONLY; contents
    are never read into any report.
    """
    hits: List[str] = []
    candidate_files: List[str] = list(ENV_FILE_PATHS) + OPENCLAW_JSON_PATHS + AUTH_PROFILES_PATHS
    for pattern in ENV_FILE_GLOBS:
        candidate_files.extend(sorted(glob.glob(pattern)))
    for d in SWEEP_DIRS:
        if os.path.isdir(d):
            for name in os.listdir(d):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    candidate_files.append(p)
    seen = set()
    for path in candidate_files:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            if os.path.getsize(path) > 5_000_000:
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "pit-" in line:
                        hits.append(path)  # PATH ONLY, never the line.
                        break
        except OSError:
            continue
    return sorted(set(hits))


# --------------------------------------------------------------------------- #
# HTTP layer (stdlib urllib; injectable for the self-test)
# --------------------------------------------------------------------------- #
class HttpResult:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: Dict[str, str], body: str) -> None:
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body


def default_http_get(base: str, path: str, token: str, extra_headers: Dict[str, str]) -> HttpResult:
    """GET base+path with a Bearer PIT built only in memory. Never logs the token."""
    url = base.rstrip("/") + path
    headers = {
        "Authorization": f"Bearer {token}",
        "Version": API_VERSION_HEADER,
        "Accept": "application/json",
    }
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return HttpResult(resp.status, dict(resp.headers.items()), body)
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry status + headers.
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            body = ""
        return HttpResult(exc.code, dict(exc.headers.items()) if exc.headers else {}, body)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Redact defensively: the exception text could echo the URL but never the token.
        raise GateIncomplete(f"pairing endpoint unreachable: {type(exc).__name__}") from exc


def _rate_remaining(result: HttpResult) -> Optional[int]:
    for name in RATE_REMAINING_HEADER_CANDIDATES:
        if name in result.headers:
            try:
                return int(str(result.headers[name]).strip())
            except (TypeError, ValueError):
                return None
    return None


# --------------------------------------------------------------------------- #
# State file (read-modify-write; gate-owned keys only; never as root)
# --------------------------------------------------------------------------- #
def _state_path(state_dir: str) -> str:
    return os.path.join(state_dir, "ghl-state.json")


def _read_state(state_dir: str) -> Dict[str, object]:
    path = _state_path(state_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _running_as_root() -> bool:
    getuid = getattr(os, "geteuid", None)
    return bool(getuid and getuid() == 0)


def _write_state(state_dir: str, patch: Dict[str, object]) -> Optional[str]:
    """Merge gate-owned keys into ghl-state.json. Returns a warning string or None.

    Refuses to write when running as root (root-owned config freezes the gateway).
    """
    if _running_as_root():
        return "state write SKIPPED: running as root; run the gate as the node user."
    try:
        os.makedirs(state_dir, exist_ok=True)
    except OSError as exc:
        return f"state dir not writable: {type(exc).__name__}"
    current = _read_state(state_dir)
    current.update(patch)
    tmp = _state_path(state_dir) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, sort_keys=True)
        os.replace(tmp, _state_path(state_dir))
    except OSError as exc:
        return f"state write failed: {type(exc).__name__}"
    return None


# --------------------------------------------------------------------------- #
# Fingerprint registry (optional; commingling detection across clients)
# --------------------------------------------------------------------------- #
def _fingerprint(pit: str) -> str:
    """One-way sha256(PIT)[:12]. Not reversible; safe to store and report."""
    return hashlib.sha256(pit.encode("utf-8")).hexdigest()[:12]


def _registry_path() -> Optional[str]:
    override = os.environ.get("GHL_FINGERPRINT_REGISTRY", "").strip()
    if override:
        return override
    default = os.path.expanduser("~/.openclaw/state/podcast-engine/fingerprint-registry.json")
    if os.path.isfile(default):
        return default
    return None


def _registry_conflict(fingerprint: str, client: str) -> Optional[str]:
    """Return the OTHER client name if this fingerprint is registered to a
    different client (a commingling alarm), else None. Best-effort; never fatal
    on its own read error.
    """
    path = _registry_path()
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(reg, dict):
        owner = reg.get(fingerprint)
        if isinstance(owner, str) and owner and owner != client:
            return owner
    return None


def _registry_record(fingerprint: str, client: str) -> None:
    """Write-on-first-pass registry entry (best effort, never as root)."""
    if _running_as_root():
        return
    path = _registry_path() or os.path.expanduser(
        "~/.openclaw/state/podcast-engine/fingerprint-registry.json"
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        reg: Dict[str, str] = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                reg = {k: v for k, v in loaded.items() if isinstance(v, str)}
        if reg.get(fingerprint) == client:
            return
        reg[fingerprint] = client
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except (OSError, ValueError):
        pass


# --------------------------------------------------------------------------- #
# Field helpers
# --------------------------------------------------------------------------- #
def _bare_key(field_key: str) -> str:
    return field_key[len("contact."):] if field_key.startswith("contact.") else field_key


def _parse_custom_fields(body: str) -> Dict[str, str]:
    """Return {bare_field_key: field_id} from a customFields list response."""
    out: Dict[str, str] = {}
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return out
    fields = []
    if isinstance(data, dict):
        fields = data.get("customFields") or data.get("customField") or []
    elif isinstance(data, list):
        fields = data
    if not isinstance(fields, list):
        return out
    for f in fields:
        if not isinstance(f, dict):
            continue
        key = f.get("fieldKey") or f.get("key") or f.get("name")
        fid = f.get("id") or f.get("_id") or ""
        if isinstance(key, str) and key:
            out[_bare_key(key)] = str(fid)
    return out


# --------------------------------------------------------------------------- #
# The verdict object
# --------------------------------------------------------------------------- #
class Verdict:
    def __init__(self) -> None:
        self.gate = "ghl_credential_gate"
        self.result = "PENDING"
        self.exit_code = EXIT_INCOMPLETE
        self.reason = ""
        self.checks: Dict[str, object] = {}
        self.alerts: List[str] = []
        self.warnings: List[str] = []

    def finish(self, result: str, code: int, reason: str) -> "Verdict":
        self.result = result
        self.exit_code = code
        self.reason = reason
        return self

    def to_dict(self) -> Dict[str, object]:
        return {
            "gate": self.gate,
            "result": self.result,
            "exit_code": self.exit_code,
            "reason": REDACTOR.scrub(self.reason),
            "checks": self.checks,
            "alerts": [REDACTOR.scrub(a) for a in self.alerts],
            "warnings": [REDACTOR.scrub(w) for w in self.warnings],
        }


# --------------------------------------------------------------------------- #
# The gate itself
# --------------------------------------------------------------------------- #
class CredentialGate:
    def __init__(
        self,
        client: str,
        expected_location_id: str,
        state_dir: str,
        mode: str = "full",
        check_fields: bool = False,
        webhook_location_id: Optional[str] = None,
        episode_budget: int = DEFAULT_EPISODE_BUDGET,
        api_base: Optional[str] = None,
        http_get: Optional[Callable[..., HttpResult]] = None,
        stores: Optional[List[Tuple[str, Dict[str, str]]]] = None,
        strict_rate_header: bool = False,
    ) -> None:
        self.client = client
        self.expected_arg = expected_location_id
        self.state_dir = state_dir
        self.mode = mode
        self.check_fields = check_fields
        self.webhook_location_id = webhook_location_id
        self.episode_budget = max(1, int(episode_budget))
        self.api_base = api_base or os.environ.get("GHL_API_BASE", DEFAULT_API_BASE)
        self.http_get = http_get or (lambda path, token: default_http_get(self.api_base, path, token, {}))
        self._stores = stores  # injectable for the self-test.
        self.strict_rate_header = strict_rate_header
        self.verdict = Verdict()

    # -- rate floor ------------------------------------------------------- #
    @property
    def rate_floor(self) -> int:
        return max(500, 10 * self.episode_budget)

    # -- store access ----------------------------------------------------- #
    def _stores_list(self) -> List[Tuple[str, Dict[str, str]]]:
        return self._stores if self._stores is not None else _ordered_stores()

    # -- main run --------------------------------------------------------- #
    def run(self) -> Verdict:
        v = self.verdict
        stores = self._stores_list()

        # CHECK 1: resolve the PIT across all aliases and all stores.
        pit_res = _resolve(PIT_ALIASES, stores)
        pit = pit_res["value"]  # type: ignore[assignment]
        REDACTOR.register(pit if isinstance(pit, str) else None)
        v.checks["resolution"] = {
            "winner_alias": pit_res["winner_alias"],
            "winner_store": pit_res["winner_store"],
            "audit": pit_res["audit"],
            "unknown_name_sweep": [] if pit else _unknown_name_sweep(),
        }
        if not pit:
            return v.finish(
                "MISSING", EXIT_MISSING,
                "no Location Private Integration Token resolved under any of the "
                f"{len(PIT_ALIASES)} aliases across any store; see resolution audit "
                "(a pit- value found under an unknown name is never trusted).",
            )

        # CHECK 2: shape. Report prefix_ok and length ONLY, never the value.
        prefix_ok = pit.startswith("pit-")
        v.checks["shape"] = {"prefix_ok": prefix_ok, "length": len(pit)}
        if not prefix_ok:
            v.warnings.append(
                "resolved token does not carry the pit- prefix; a Location Private "
                "Integration Token is expected. Pairing proof is authoritative."
            )

        # CHECK 3: resolve Location ID; enforce webhook == env equality.
        loc_res = _resolve(LOCATION_ALIASES, stores)
        env_location = loc_res["value"]  # type: ignore[assignment]
        v.checks["location"] = {
            "winner_alias": loc_res["winner_alias"],
            "winner_store": loc_res["winner_store"],
            "env_location_present": bool(env_location),
        }
        if self.webhook_location_id and env_location and self.webhook_location_id != env_location:
            v.alerts.append(
                "ISOLATION: webhook location_id does not equal the box env Location ID."
            )
            return v.finish(
                "ISOLATION", EXIT_ISOLATION,
                "webhook location_id and environment Location ID differ; the box is "
                "serving a request for a Location it is not configured for.",
            )

        expected = self._resolve_expected(env_location)
        if not expected:
            return v.finish(
                "MISSING", EXIT_MISSING,
                "no Location ID resolved (env alias set empty and none supplied); "
                "the tenant check cannot run.",
            )
        v.checks["location"]["expected_location_id"] = expected  # id is not secret.
        if env_location and expected != env_location:
            v.alerts.append(
                "ISOLATION: expected Location ID differs from the box env Location ID."
            )
            return v.finish(
                "ISOLATION", EXIT_ISOLATION,
                "the expected Location ID differs from the box env Location ID; refusing "
                "to pair a token against a Location this box is not configured for.",
            )

        fingerprint = _fingerprint(pit)

        # CACHED fast-path: honour a fresh, fingerprint-matching prior full pass.
        if self.mode == "cached":
            cached = self._try_cached(expected, fingerprint)
            if cached is not None:
                return cached
            # else: cache stale/mismatched; fall through to full checks.

        # CHECK 4: live pairing proof.
        try:
            pair = self.http_get(f"/locations/{expected}", pit)
        except GateIncomplete as exc:
            return v.finish(
                "INCOMPLETE", EXIT_INCOMPLETE,
                f"pairing proof could not complete: {exc}. Not a credential verdict; retry.",
            )
        v.checks["pairing"] = {"status": pair.status}
        if pair.status != 200:
            v.alerts.append(
                f"ISOLATION: PIT did not pair with Location {expected} (HTTP {pair.status})."
            )
            return v.finish(
                "ISOLATION", EXIT_ISOLATION,
                f"pairing proof returned HTTP {pair.status}; this PIT does not belong to "
                "the expected Location (wrong, rotated, or cross-client token). Do NOT proceed.",
            )

        # CHECK 5: isolation / anti-commingling fingerprint.
        prior_state = _read_state(self.state_dir)
        prior_fp = prior_state.get("pit_fingerprint")
        fp_check: Dict[str, object] = {"fingerprint": fingerprint, "changed": False}
        if isinstance(prior_fp, str) and prior_fp and prior_fp != fingerprint:
            fp_check["changed"] = True
            v.warnings.append(
                "PIT fingerprint changed for this client since the last pass "
                "(token rotation is normal; logged for the operator)."
            )
        conflict = _registry_conflict(fingerprint, self.client)
        if conflict:
            fp_check["commingling_with"] = conflict
            v.alerts.append(
                f"ISOLATION: this PIT fingerprint is already registered to a DIFFERENT "
                f"client ({conflict}); commingling alarm."
            )
            v.checks["fingerprint"] = fp_check
            return v.finish(
                "ISOLATION", EXIT_ISOLATION,
                "credential commingling detected: the same token fingerprint is registered "
                "under another client name. Hard abort.",
            )
        v.checks["fingerprint"] = fp_check

        # CHECK 6: required custom fields (first run per client, --check-fields).
        field_map: Dict[str, str] = {}
        book_teaser_present = False
        if self.check_fields:
            try:
                fld = self.http_get(f"/locations/{expected}/customFields", pit)
            except GateIncomplete as exc:
                return v.finish(
                    "INCOMPLETE", EXIT_INCOMPLETE,
                    f"custom-field smoke test could not complete: {exc}. Retry.",
                )
            if fld.status != 200:
                return v.finish(
                    "INCOMPLETE", EXIT_INCOMPLETE,
                    f"custom-field list returned HTTP {fld.status}; cannot verify fields. Retry.",
                )
            present = _parse_custom_fields(fld.body)
            missing = [k for k in REQUIRED_FIELDS if k not in present]
            book_teaser_present = BOOK_TEASER_FIELD in present
            single_trap = (
                "podcast_survey__additional_info" in missing
                and SINGLE_UNDERSCORE_TRAP in present
            )
            field_map = {k: present[k] for k in REQUIRED_FIELDS if k in present}
            if book_teaser_present:
                field_map[BOOK_TEASER_FIELD] = present[BOOK_TEASER_FIELD]
            v.checks["fields"] = {
                "required_total": len(REQUIRED_FIELDS),
                "present_count": len(REQUIRED_FIELDS) - len(missing),
                "missing": missing,
                "book_teaser": "present" if book_teaser_present
                else "ABSENT (remind founder to create custom field book_teaser; do not create silently)",
                "single_underscore_trap_seen": single_trap,
            }
            if missing:
                note = ""
                if single_trap:
                    note = (
                        " NOTE: a single-underscore variant exists but the required "
                        "double-underscore key podcast_survey__additional_info is absent; "
                        "the single-underscore variant is never an acceptable substitute."
                    )
                return v.finish(
                    "FIELDS_MISSING", EXIT_FIELDS,
                    "required Convert and Flow custom fields are missing: "
                    f"{', '.join(missing)}. The client must contact support to have them "
                    "created via the snapshot; fields are never created silently." + note,
                )
        else:
            v.checks["fields"] = {"skipped": "run with --check-fields on first run per client"}

        # CHECK 7: rate floor from the pairing (or field) response headers.
        remaining = _rate_remaining(pair)
        if remaining is None and self.check_fields:
            remaining = _rate_remaining(fld)  # type: ignore[name-defined]
        rate_check: Dict[str, object] = {"floor": self.rate_floor, "daily_remaining": remaining}
        if remaining is None:
            if self.strict_rate_header:
                v.checks["rate"] = rate_check
                return v.finish(
                    "RATE_FLOOR", EXIT_RATE_FLOOR,
                    "rate-limit remaining header absent and strict mode requires it.",
                )
            rate_check["note"] = (
                "daily-remaining header absent on this response; floor not confirmable, "
                "passing with a warning (confirm header name on the canary)."
            )
            v.warnings.append("Convert and Flow daily-remaining rate header was absent.")
        elif remaining < self.rate_floor:
            v.checks["rate"] = rate_check
            return v.finish(
                "RATE_FLOOR", EXIT_RATE_FLOOR,
                f"per-Location daily budget {remaining} is below the floor {self.rate_floor}; "
                "hold the job rather than start a publish phase that could die mid-write.",
            )
        v.checks["rate"] = rate_check

        # CHECK 8: write verdict/state for cached mode (never as root).
        patch: Dict[str, object] = {
            "client": self.client,
            "location_id": expected,
            "pit_fingerprint": fingerprint,
            "pit_alias": pit_res["winner_alias"],
            "pit_store": pit_res["winner_store"],
            "gate": {"last_pass": _now_iso(), "mode": self.mode, "result": "PASS"},
        }
        if self.check_fields:
            fm = dict(field_map)
            fm.setdefault(BOOK_TEASER_FIELD, None)  # explicit null when absent.
            patch["field_map"] = fm
            patch["book_teaser_field_present"] = book_teaser_present
            patch["field_map_hash"] = _field_map_hash(field_map)
        warn = _write_state(self.state_dir, patch)
        if warn:
            v.warnings.append(warn)
        _registry_record(fingerprint, self.client)

        return v.finish("PASS", EXIT_PASS, "all requested Convert and Flow credential checks passed.")

    # -- helpers ---------------------------------------------------------- #
    def _resolve_expected(self, env_location: Optional[str]) -> Optional[str]:
        arg = (self.expected_arg or "").strip()
        if arg and arg not in ("from-registry", "from-env"):
            return arg
        if arg == "from-registry":
            prior = _read_state(self.state_dir).get("location_id")
            if isinstance(prior, str) and prior:
                return prior
        return env_location

    def _try_cached(self, expected: str, fingerprint: str) -> Optional[Verdict]:
        v = self.verdict
        state = _read_state(self.state_dir)
        gate = state.get("gate") if isinstance(state.get("gate"), dict) else {}
        last_pass = gate.get("last_pass") if isinstance(gate, dict) else None
        prior_fp = state.get("pit_fingerprint")
        prior_loc = state.get("location_id")
        fresh = False
        if isinstance(last_pass, str):
            ts = _parse_iso(last_pass)
            fresh = ts is not None and (time.time() - ts) < CACHE_FRESH_SECONDS
        if (
            fresh
            and prior_fp == fingerprint
            and prior_loc == expected
            and gate.get("result") == "PASS"
        ):
            v.checks["cached"] = {"fresh": True, "last_pass": last_pass}
            return v.finish(
                "PASS", EXIT_PASS,
                "cached fast-path: a fresh (<24h) full pass exists and the PIT fingerprint "
                "and Location still match.",
            )
        v.checks["cached"] = {"fresh": False, "escalated_to_full": True}
        return None


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(value: str) -> Optional[float]:
    # _now_iso() writes UTC with a trailing Z; parse back as UTC via timegm so the
    # freshness delta is not skewed by the local timezone or DST.
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return float(calendar.timegm(time.strptime(value, fmt)))
        except (ValueError, OverflowError):
            continue
    return None


def _field_map_hash(field_map: Dict[str, str]) -> str:
    canon = json.dumps(field_map, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _emit(verdict: Verdict, as_json: bool) -> None:
    if as_json:
        REDACTOR.out(json.dumps(verdict.to_dict(), indent=2, sort_keys=True))
        return
    d = verdict.to_dict()
    REDACTOR.out(f"gate: {d['gate']}")
    REDACTOR.out(f"result: {d['result']} (exit {d['exit_code']})")
    REDACTOR.out(f"reason: {d['reason']}")
    res = d["checks"].get("resolution") if isinstance(d["checks"], dict) else None
    if isinstance(res, dict):
        REDACTOR.out(f"  PIT resolved via alias={res.get('winner_alias')} store={res.get('winner_store')}")
    shape = d["checks"].get("shape") if isinstance(d["checks"], dict) else None
    if isinstance(shape, dict):
        REDACTOR.out(f"  shape: prefix_ok={shape.get('prefix_ok')} length={shape.get('length')}")
    for alert in d["alerts"]:
        REDACTOR.err(f"ALERT (route through alert-dedup.py, operator only): {alert}")
    for warn in d["warnings"]:
        REDACTOR.err(f"warning: {warn}")


# --------------------------------------------------------------------------- #
# Argument parsing (usage errors exit 1, never 2, so exit 2 means only MISSING)
# --------------------------------------------------------------------------- #
class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        sys.stderr.write(f"usage error: {message}\n")
        sys.exit(EXIT_INCOMPLETE)


def _build_parser() -> argparse.ArgumentParser:
    ap = _ArgParser(
        prog="ghl_credential_gate",
        description=(
            "Convert and Flow credential gate for the Podcast Production Engine. "
            "Exit 0 pass, 2 missing, 3 isolation, 4 fields, 5 rate floor, 1 incomplete. "
            "Never prints a secret value."
        ),
    )
    ap.add_argument("--client", required=False, help="client name (isolation key)")
    ap.add_argument(
        "--expected-location-id", default="from-env",
        help="literal Location ID to pair against, or 'from-registry'/'from-env' (default)",
    )
    ap.add_argument("--state-dir", default=None, help="per-client state directory")
    ap.add_argument("--mode", choices=["full", "cached"], default="full")
    ap.add_argument("--check-fields", action="store_true", help="run the custom-field smoke test")
    ap.add_argument("--webhook-location-id", default=None, help="the run's webhook location_id, if any")
    ap.add_argument("--episode-budget", type=int, default=DEFAULT_EPISODE_BUDGET)
    ap.add_argument("--api-base", default=None, help="override the Convert and Flow REST base URL")
    ap.add_argument("--strict-rate-header", action="store_true",
                    help="fail exit 5 if the daily-remaining header is absent")
    ap.add_argument("--json", action="store_true", help="machine-readable verdict")
    ap.add_argument("--selftest", action="store_true", help="run the built-in offline test battery")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.client:
        sys.stderr.write("usage error: --client is required (unless --selftest)\n")
        return EXIT_INCOMPLETE
    state_dir = args.state_dir or os.path.expanduser(
        f"~/.openclaw/state/podcast-engine/{args.client}"
    )
    gate = CredentialGate(
        client=args.client,
        expected_location_id=args.expected_location_id,
        state_dir=state_dir,
        mode=args.mode,
        check_fields=args.check_fields,
        webhook_location_id=args.webhook_location_id,
        episode_budget=args.episode_budget,
        api_base=args.api_base,
        strict_rate_header=args.strict_rate_header,
    )
    try:
        verdict = gate.run()
    except GateIncomplete as exc:
        REDACTOR.err(f"gate incomplete: {exc}")
        return EXIT_INCOMPLETE
    _emit(verdict, args.json)
    return verdict.exit_code


# --------------------------------------------------------------------------- #
# Built-in offline self-test (no network, no real secrets). Proves the exit-code
# taxonomy and the secrecy wrapper. Run: python3 ghl_credential_gate.py --selftest
# --------------------------------------------------------------------------- #
def _selftest() -> int:
    import tempfile

    FAKE_PIT = "pit-selftest-000000000000000000000000"
    GOOD_LOC = "LOC_GOOD_1234567890"
    passed = 0
    failed = 0
    reports: List[str] = []

    def check(name: str, got: int, want: int) -> None:
        nonlocal passed, failed
        ok = got == want
        passed += int(ok)
        failed += int(not ok)
        reports.append(f"[{'PASS' if ok else 'FAIL'}] {name}: exit {got} (want {want})")

    all_fields = {
        f"contact.{k}": {"id": f"id_{i}", "fieldKey": f"contact.{k}"}
        for i, k in enumerate(REQUIRED_FIELDS + [BOOK_TEASER_FIELD])
    }

    def fake_http(fields_body: object, remaining: Optional[int], pair_status: int = 200):
        def _get(path: str, token: str) -> HttpResult:
            headers: Dict[str, str] = {}
            if remaining is not None:
                headers["X-RateLimit-Daily-Remaining"] = str(remaining)
            if path.endswith("/customFields"):
                return HttpResult(200, headers, json.dumps({"customFields": fields_body}))
            return HttpResult(pair_status, headers, "{}")
        return _get

    def stores_with(pit: Optional[str], loc: Optional[str]) -> List[Tuple[str, Dict[str, str]]]:
        kv: Dict[str, str] = {}
        if pit:
            kv["CONVERTFLOW_API_KEY"] = pit  # exercise a branded alias.
        if loc:
            kv["GHL_LOCATION_ID"] = loc
        return [("live-process-env(self)", kv)]

    with tempfile.TemporaryDirectory() as td:
        # 1. PASS full with fields + healthy rate.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme"), mode="full", check_fields=True,
            http_get=fake_http(list(all_fields.values()), 190000),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("full pass", g.run().exit_code, EXIT_PASS)

        # 2. MISSING: no PIT anywhere.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme2"), mode="full",
            http_get=fake_http(list(all_fields.values()), 190000),
            stores=stores_with(None, GOOD_LOC),
        )
        check("missing pit", g.run().exit_code, EXIT_MISSING)

        # 3. ISOLATION: pairing returns 401.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme3"), mode="full",
            http_get=fake_http(list(all_fields.values()), 190000, pair_status=401),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("pairing 401 isolation", g.run().exit_code, EXIT_ISOLATION)

        # 4. ISOLATION: webhook location != env location.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme4"), mode="full",
            webhook_location_id="LOC_OTHER",
            http_get=fake_http(list(all_fields.values()), 190000),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("webhook/env mismatch isolation", g.run().exit_code, EXIT_ISOLATION)

        # 5. FIELDS: drop the double-underscore key, keep the single-underscore trap.
        trimmed = [
            v for k, v in all_fields.items()
            if not k.endswith("podcast_survey__additional_info")
        ]
        trimmed.append({"id": "trap", "fieldKey": f"contact.{SINGLE_UNDERSCORE_TRAP}"})
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme5"), mode="full", check_fields=True,
            http_get=fake_http(trimmed, 190000),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("double-underscore field missing", g.run().exit_code, EXIT_FIELDS)

        # 6. RATE FLOOR: remaining below floor.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme6"), mode="full", check_fields=True,
            http_get=fake_http(list(all_fields.values()), 100),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("rate floor", g.run().exit_code, EXIT_RATE_FLOOR)

        # 7. CACHED fast-path after a full pass reuses state without a live call.
        cdir = os.path.join(td, "cached")
        CredentialGate(
            "acme", GOOD_LOC, cdir, mode="full", check_fields=True,
            http_get=fake_http(list(all_fields.values()), 190000),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        ).run()

        def _boom(path: str, token: str) -> HttpResult:
            raise AssertionError("cached mode must not make a live call")

        g = CredentialGate(
            "acme", GOOD_LOC, cdir, mode="cached",
            http_get=_boom, stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        check("cached fast-path", g.run().exit_code, EXIT_PASS)

        # 8. COMMINGLING: same fingerprint registered to a different client.
        reg = os.path.join(td, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({_fingerprint(FAKE_PIT): "other-client"}, fh)
        os.environ["GHL_FINGERPRINT_REGISTRY"] = reg
        try:
            g = CredentialGate(
                "acme", GOOD_LOC, os.path.join(td, "acme8"), mode="full",
                http_get=fake_http(list(all_fields.values()), 190000),
                stores=stores_with(FAKE_PIT, GOOD_LOC),
            )
            check("commingling isolation", g.run().exit_code, EXIT_ISOLATION)
        finally:
            os.environ.pop("GHL_FINGERPRINT_REGISTRY", None)

        # 9. SECRECY: the PIT value never appears in the JSON verdict.
        g = CredentialGate(
            "acme", GOOD_LOC, os.path.join(td, "acme9"), mode="full", check_fields=True,
            http_get=fake_http(list(all_fields.values()), 190000),
            stores=stores_with(FAKE_PIT, GOOD_LOC),
        )
        blob = json.dumps(g.run().to_dict())
        leak = FAKE_PIT in blob
        reports.append(f"[{'PASS' if not leak else 'FAIL'}] secrecy: PIT absent from JSON verdict")
        passed += int(not leak)
        failed += int(leak)

    for line in reports:
        REDACTOR.out(line)
    REDACTOR.out(f"selftest: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
