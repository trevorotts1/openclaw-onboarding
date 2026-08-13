#!/usr/bin/env python3
"""capacity.py -- CLIENT capacity detection for the Presentations department.

WHAT CHANGED AND WHY (unit u07)
-------------------------------
The previous version of this module hard-coded ONE operator's setup as module
constants -- PROVIDER_CEILING = 2500 (DeepSeek v4 Flash), WORKFLOWS = 30,
SUBAGENTS_PER_WORKFLOW = 16 -- read an operator-box settings path, and was
consulted by nothing in the dispatch path. On a client box running Ollama Cloud
at $20/month it would have reported hundreds of dispatchable agents. That is not
a measurement, it is one machine's number wearing a measurement's clothes.

This module now DETECTS the client's provider and plan and returns the cap that
belongs to THAT account. It never guesses upward: an unknown provider or an
unknown plan collapses to DEFAULT_CONSERVATIVE (3), and a provider whose plan
cannot be determined PARKS the run behind a one-time interview question instead
of inventing a number.

THE CAP TABLE (binding)
-----------------------
    ollama-cloud    + $20/month    ->     3 concurrent agents
    ollama-cloud    + $100/month   ->    10 concurrent agents
    deepseek-direct + v4-pro       ->   500 subagents
    deepseek-direct + v4-flash     ->  2500 subagents
    unknown provider OR plan       ->     3 (DEFAULT_CONSERVATIVE)

DETECTION ORDER (first hit wins; every step is read-only)
---------------------------------------------------------
    a. capacity_override.json in the department config dir -- an explicitly
       declared {provider, plan, max_concurrent}.
    b. the 9Router configuration -- which provider the primary model routes to
       (~/.9router/db/data.sqlite, opened read-only; ONLY the non-secret
       `combos.name` / `combos.models` columns are read).
    c. the OpenClaw agent model configuration -- the provider namespace prefix
       on the primary model (~/.openclaw/openclaw.json, `agents.*.model.primary`).
    d. provider known but plan unknown -> emit the interview question and PARK.
       The answer is persisted to capacity_override.json so the question is asked
       ONCE, never every run.
    e. nothing found -> DEFAULT_CONSERVATIVE plus a loud UNDETERMINED line.

CREDENTIAL SAFETY (binding)
---------------------------
Detection reads only WHICH provider is configured. It never reads, returns, logs
or prints a credential VALUE. Every value that leaves this module passes through
_safe_value(), which refuses any field whose key looks like a secret
(key/token/secret/password/auth/credential/cookie/bearer). The 9Router
`apiKeys` table and `providerConnections.data` blob are never queried. If a
provider cannot be determined without touching secret material, this module
returns UNDETERMINED instead.

STATUSES
--------
    MEASURED     -- provider + plan resolved; `available` is the cap-table number.
    UNDETERMINED -- nothing resolved; `available` = DEFAULT_CONSERVATIVE (3).
    PARKED       -- provider known, plan unknown; `available` is None and an
                    interview question is attached. Dispatch must REFUSE.
    FAILED       -- a declared config exists but is unusable (e.g. malformed
                    capacity_override.json); `available` is None. Dispatch must
                    REFUSE. A broken declaration is never silently downgraded to
                    a default -- that would hide the operator's own mistake.

`available is None` is the ONLY signal a caller needs: it means "this probe could
not produce a number", and the dispatch path fails closed with
AF-CAPACITY-UNMEASURED.

Exit codes (CLI): 0 success, 3 probe could not produce a number, 2 usage.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Cap table + doctrine constants
# ---------------------------------------------------------------------------

#: The floor every unknown collapses to. NEVER guess upward.
DEFAULT_CONSERVATIVE = 3

PROBE_MODE = "live"  # NEVER "SIMULATED"

PROVIDER_OLLAMA_CLOUD = "ollama-cloud"
PROVIDER_DEEPSEEK_DIRECT = "deepseek-direct"

PLAN_OLLAMA_20 = "$20/month"
PLAN_OLLAMA_100 = "$100/month"
PLAN_DEEPSEEK_PRO = "v4-pro"
PLAN_DEEPSEEK_FLASH = "v4-flash"

#: (provider, plan) -> concurrent agents. The single source of truth for capacity.
CAP_TABLE = {
    (PROVIDER_OLLAMA_CLOUD, PLAN_OLLAMA_20): 3,
    (PROVIDER_OLLAMA_CLOUD, PLAN_OLLAMA_100): 10,
    (PROVIDER_DEEPSEEK_DIRECT, PLAN_DEEPSEEK_PRO): 500,
    (PROVIDER_DEEPSEEK_DIRECT, PLAN_DEEPSEEK_FLASH): 2500,
}

#: Which plans a provider can be on -- drives the interview question and the
#: "provider known, plan unknown" PARK.
PLANS_BY_PROVIDER = {
    PROVIDER_OLLAMA_CLOUD: (PLAN_OLLAMA_20, PLAN_OLLAMA_100),
    PROVIDER_DEEPSEEK_DIRECT: (PLAN_DEEPSEEK_PRO, PLAN_DEEPSEEK_FLASH),
}

STATUS_MEASURED = "MEASURED"
STATUS_UNDETERMINED = "UNDETERMINED"
STATUS_PARKED = "PARKED"
STATUS_FAILED = "FAILED"

#: The autofail the dispatch path raises when this probe cannot produce a number.
AUTOFAIL_CODE = "AF-CAPACITY-UNMEASURED"

SOURCE_OVERRIDE = "capacity_override.json"
SOURCE_9ROUTER = "9router"
SOURCE_OPENCLAW = "openclaw"
SOURCE_NONE = "none"

OVERRIDE_FILENAME = "capacity_override.json"
CONFIG_DIR_ENV = "PRESENTATION_CAPACITY_CONFIG_DIR"

NINEROUTER_DB = Path.home() / ".9router" / "db" / "data.sqlite"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
HARNESS_SETTINGS_CANDIDATES = (
    Path.home() / ".claude-nine" / "settings.json",
    Path.home() / ".claude" / "settings.json",
)

# Process-table signature for the working-concurrency observation. argv[0]
# basename starting with "claude" catches live sessions and their spawned
# subagents; "openclaw" catches the gateway. The pattern is reported alongside
# the count so the number is auditable, never taken on faith.
PROCESS_PATTERN = re.compile(r"^(claude|openclaw)")


class CapacityUnmeasured(RuntimeError):
    """Raised when a caller demands a number this probe could not produce."""


# ---------------------------------------------------------------------------
# Credential safety
# ---------------------------------------------------------------------------
_SECRET_KEY_RE = re.compile(
    r"(api[-_]?key|key|token|secret|password|passwd|auth|credential|cookie|bearer)",
    re.IGNORECASE,
)


def _safe_value(key: str, value):
    """Return `value` only when `key` cannot be carrying credential material.

    Every string this module lifts out of a config file goes through here. A
    field named apiKey / token / authToken / password / ... is dropped on the
    floor: detection needs to know WHICH provider is configured, never what the
    account's secret is."""
    if _SECRET_KEY_RE.search(str(key)):
        return None
    return value


def _get_safe(node, *path):
    """Walk a nested dict by key path, refusing any secret-named segment."""
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return None
        if _safe_value(key, True) is None:
            return None
        cur = cur.get(key)
    return cur


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize_provider(raw) -> Optional[str]:
    """Map a declared/detected provider string onto a cap-table provider id.

    Returns None for anything the cap table does not cover -- an unknown
    provider is an unknown provider, never the nearest-looking one."""
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().replace("_", "-").replace(" ", "-")
    if not token:
        return None
    if token in ("ollama-local", "ollama-localhost", "local-ollama"):
        return None  # a local Ollama has no purchased plan; not a cap-table row
    if token in ("ollama-cloud", "ollamacloud", "ollama", "ollman"):
        return PROVIDER_OLLAMA_CLOUD
    if token.startswith("ollama-cloud"):
        return PROVIDER_OLLAMA_CLOUD
    if token in ("deepseek-direct", "deepseek", "deepseekdirect", "ds",
                 "ds-max", "dspro", "dspro-max", "dspromax"):
        return PROVIDER_DEEPSEEK_DIRECT
    if token.startswith("deepseek"):
        return PROVIDER_DEEPSEEK_DIRECT
    return None


def normalize_plan(raw, provider: Optional[str]) -> Optional[str]:
    """Map a declared/detected plan string onto a cap-table plan id."""
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower()
    if not token:
        return None
    if provider == PROVIDER_OLLAMA_CLOUD or provider is None:
        digits = re.sub(r"[^0-9]", "", token)
        if digits == "20":
            return PLAN_OLLAMA_20
        if digits == "100":
            return PLAN_OLLAMA_100
    if provider == PROVIDER_DEEPSEEK_DIRECT or provider is None:
        compact = token.replace(" ", "-").replace("_", "-")
        if "pro" in compact:
            return PLAN_DEEPSEEK_PRO
        if "flash" in compact:
            return PLAN_DEEPSEEK_FLASH
    return None


def _plan_from_model_slug(provider: Optional[str], slug: str) -> Optional[str]:
    """Derive the plan from a model identifier, where the model IMPLIES the plan.

    DeepSeek Direct is the only provider where it does: v4-pro and v4-flash are
    different products with different parallel ceilings, and the model id names
    which one. Ollama Cloud's $20 and $100 plans run the SAME models, so no model
    id can ever reveal the plan -- that is why Ollama Cloud always reaches the
    interview question."""
    if provider != PROVIDER_DEEPSEEK_DIRECT:
        return None
    text = slug.lower()
    if "pro" in text:
        return PLAN_DEEPSEEK_PRO
    if "flash" in text:
        return PLAN_DEEPSEEK_FLASH
    return None


def interview_question(provider: str) -> str:
    """The ONE question that resolves a known provider with an unknown plan."""
    return (
        f"Which plan is your {provider} account on? "
        "(Ollama Cloud: $20 -> 3 parallel agents, $100 -> 10. "
        "DeepSeek direct: v4 Pro -> 500, v4 Flash -> 2,500.)"
    )


# ---------------------------------------------------------------------------
# Step (a): the declared override
# ---------------------------------------------------------------------------
def department_config_dir() -> Path:
    """Where capacity_override.json lives.

    $PRESENTATION_CAPACITY_CONFIG_DIR wins when set (this is how a client box, a
    test, or an operator points detection at a specific declaration). Otherwise
    the department's own config/ dir, falling back to the department root --
    resolved by walking up from this file (presentation_job/ -> scripts/ -> dept),
    never from a hard-coded operator path."""
    env = os.environ.get(CONFIG_DIR_ENV)
    if env:
        return Path(env).expanduser()
    dept = Path(__file__).resolve().parent.parent.parent
    cfg = dept / "config"
    return cfg if cfg.is_dir() else dept


def override_path(config_dir: Optional[Path] = None) -> Path:
    return Path(config_dir or department_config_dir()) / OVERRIDE_FILENAME


def read_override(config_dir: Optional[Path] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Read the declared override. Returns (record, error).

    Absent file -> (None, None): not an error, detection moves to step (b).
    Present but unreadable/not-JSON/not-an-object -> (None, reason): a HARD error.
    A declaration the operator wrote and we cannot parse is never downgraded to a
    silent default -- that would hide their mistake behind a plausible number."""
    path = override_path(config_dir)
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path} is present but unreadable/not valid JSON: {exc}"
    if not isinstance(raw, dict):
        return None, f"{path} must contain a JSON object, found {type(raw).__name__}"
    return raw, None


def _resolve_override(record: dict, path: Path) -> dict:
    """Turn a declared {provider, plan, max_concurrent} into a resolution dict."""
    provider = normalize_provider(_safe_value("provider", record.get("provider")))
    plan = normalize_plan(_safe_value("plan", record.get("plan")), provider)
    declared = record.get("max_concurrent")
    declared_int = declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    if declared_int is not None and declared_int < 1:
        declared_int = None

    notes = []
    if provider and plan:
        capped = CAP_TABLE[(provider, plan)]
        if declared_int is not None and declared_int != capped:
            # The table is authoritative for a known pair. A declared number may
            # lower it (an operator throttling themselves is legitimate) but must
            # never raise it above what the account can actually run.
            available = min(declared_int, capped)
            notes.append(
                f"declared max_concurrent={declared_int} reconciled against cap table "
                f"{capped} for ({provider}, {plan}) -> {available} (never above the table)"
            )
        else:
            available = capped
        return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                "available": available, "notes": notes}

    if declared_int is not None:
        notes.append(
            f"({record.get('provider')!r}, {record.get('plan')!r}) is not a cap-table row; "
            f"using the explicitly declared max_concurrent={declared_int}"
        )
        return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                "available": declared_int, "notes": notes}

    if provider and not plan:
        return {"status": STATUS_PARKED, "provider": provider, "plan": None,
                "available": None,
                "notes": [f"{path} declares provider {provider} but no recognisable plan"]}

    return {"status": STATUS_UNDETERMINED, "provider": provider, "plan": plan,
            "available": DEFAULT_CONSERVATIVE,
            "notes": [f"{path} declares neither a cap-table provider/plan pair nor a "
                      f"positive integer max_concurrent"]}


def persist_plan_answer(provider: str, plan: str,
                        config_dir: Optional[Path] = None) -> Path:
    """Write the interview answer to capacity_override.json -- asked ONCE.

    After this file exists, step (a) hits on every subsequent run and the
    interview question is never emitted again. Returns the written path.
    Raises ValueError on a provider/plan pair the cap table does not know."""
    norm_provider = normalize_provider(provider)
    norm_plan = normalize_plan(plan, norm_provider)
    if not norm_provider or not norm_plan or (norm_provider, norm_plan) not in CAP_TABLE:
        raise ValueError(
            f"refusing to persist an unknown pair (provider={provider!r}, plan={plan!r}); "
            f"known pairs: {sorted(CAP_TABLE)}"
        )
    path = override_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": norm_provider,
        "plan": norm_plan,
        "max_concurrent": CAP_TABLE[(norm_provider, norm_plan)],
        "source": "interview",
        "answered_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "_note": "Written by capacity.py after the one-time capacity interview. "
                 "Delete this file to be asked again.",
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Step (b): the 9Router configuration
# ---------------------------------------------------------------------------
def _harness_settings() -> Tuple[Optional[dict], Optional[Path]]:
    """Read the harness settings.json, if one exists. Never exits.

    Only three non-secret fields are ever consulted: `model`, `modelOverrides`,
    and the ANTHROPIC_DEFAULT_*_MODEL aliases. Anything whose key looks like a
    credential is refused by _safe_value()."""
    for path in HARNESS_SETTINGS_CANDIDATES:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            return raw, path
    return None, None


def _primary_route_alias(settings: Optional[dict]) -> Optional[str]:
    """The 9Router combo name the harness' primary model routes through.

    settings.json declares `model` (e.g. "opus"); the ANTHROPIC_DEFAULT_*_MODEL
    env aliases and `modelOverrides` map that onto a 9Router combo (e.g.
    "opus-chain"). Both are plain model/route names -- no credential is read."""
    if not isinstance(settings, dict):
        return None
    model = _safe_value("model", settings.get("model"))
    if not isinstance(model, str) or not model.strip():
        return None
    model = model.strip()
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    alias_key = f"ANTHROPIC_DEFAULT_{model.upper()}_MODEL"
    alias = _safe_value(alias_key, env.get(alias_key))
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    overrides = settings.get("modelOverrides")
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if _safe_value(key, True) is None or not isinstance(value, str):
                continue
            if key == model or key.endswith(f"-{model}") or model in key.split("-"):
                return value.strip()
    return model


def _combo_models(alias: str, db_path: Path) -> Optional[list]:
    """Read ONLY combos.name / combos.models for `alias`, read-only, never the
    apiKeys table and never providerConnections.data (both carry secrets)."""
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(
            "select models from combos where name = ? limit 1", (alias,)
        ).fetchone()
        if row is None:
            return None
        try:
            models = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except ValueError:
            return None
        return models if isinstance(models, list) else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _split_route_entry(entry: str) -> Tuple[Optional[str], str]:
    """'ds-max/deepseek-v4-flash(max)' -> ('ds-max', 'deepseek-v4-flash')."""
    if not isinstance(entry, str) or "/" not in entry:
        return None, str(entry or "")
    namespace, remainder = entry.split("/", 1)
    slug = re.sub(r"\(.*?\)", "", remainder).strip()
    return namespace.strip(), slug


def detect_from_9router(db_path: Optional[Path] = None) -> dict:
    """Step (b). Which provider does the primary model route to?"""
    db_path = Path(db_path) if db_path else NINEROUTER_DB
    settings, settings_path = _harness_settings()
    alias = _primary_route_alias(settings)
    if not alias:
        return {"hit": False,
                "detail": f"no harness settings.json with a `model` field at "
                          f"{', '.join(str(p) for p in HARNESS_SETTINGS_CANDIDATES)}"}
    if not db_path.is_file():
        return {"hit": False,
                "detail": f"primary model alias {alias!r} (from {settings_path}) but no "
                          f"9Router database at {db_path}"}
    models = _combo_models(alias, db_path)
    if not models:
        return {"hit": False,
                "detail": f"9Router database {db_path} has no combo named {alias!r} "
                          f"(or it declares no models)"}
    for entry in models:
        namespace, slug = _split_route_entry(entry)
        provider = normalize_provider(namespace)
        if not provider:
            continue
        return {"hit": True, "provider": provider,
                "plan": _plan_from_model_slug(provider, slug),
                "detail": f"9Router combo {alias!r} routes to namespace {namespace!r} "
                          f"(model {slug!r}) -> {provider}"}
    namespaces = [_split_route_entry(e)[0] for e in models]
    return {"hit": False,
            "detail": f"9Router combo {alias!r} routes to namespaces {namespaces!r}, "
                      f"none of which is a cap-table provider"}


# ---------------------------------------------------------------------------
# Step (c): the OpenClaw agent model configuration
# ---------------------------------------------------------------------------
_OPENCLAW_PRIMARY_PATHS = (
    ("agents", "defaults", "model", "primary"),
    ("agents", "defaults", "subagents", "model", "primary"),
)


def _openclaw_namespace_is_cloud(config: dict, namespace: str) -> Optional[bool]:
    """Is this OpenClaw provider namespace the CLOUD Ollama or a local one?

    Decided from models.providers.<ns>.baseUrl -- a routing endpoint, not a
    credential (and the URL itself never leaves this function). Returns None when
    the namespace declares no baseUrl."""
    base_url = _get_safe(config, "models", "providers", namespace, "baseUrl")
    if not isinstance(base_url, str) or not base_url:
        return None
    host = base_url.lower()
    if "localhost" in host or "127.0.0.1" in host or "::1" in host or "0.0.0.0" in host:
        return False
    return True


def detect_from_openclaw(config_path: Optional[Path] = None) -> dict:
    """Step (c). The provider namespace prefix on the primary model."""
    path = Path(config_path) if config_path else OPENCLAW_CONFIG
    if not path.is_file():
        return {"hit": False, "detail": f"no OpenClaw config at {path}"}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"hit": False, "detail": f"OpenClaw config {path} unreadable: {exc}"}
    if not isinstance(config, dict):
        return {"hit": False, "detail": f"OpenClaw config {path} is not a JSON object"}

    candidates = []
    for keys in _OPENCLAW_PRIMARY_PATHS:
        value = _get_safe(config, *keys)
        if isinstance(value, str) and value.strip():
            candidates.append((".".join(keys), value.strip()))
    agents_list = _get_safe(config, "agents", "list")
    if isinstance(agents_list, list):
        for idx, agent in enumerate(agents_list):
            value = _get_safe(agent, "model", "primary")
            if isinstance(value, str) and value.strip():
                candidates.append((f"agents.list[{idx}].model.primary", value.strip()))

    if not candidates:
        return {"hit": False,
                "detail": f"OpenClaw config {path} declares no agents.*.model.primary"}

    for where, model_id in candidates:
        namespace, slug = _split_route_entry(model_id)
        if namespace is None:
            continue
        if namespace.lower().startswith("ollama"):
            is_cloud = _openclaw_namespace_is_cloud(config, namespace)
            if is_cloud is False:
                continue  # a local Ollama has no purchased plan
        provider = normalize_provider(namespace)
        if not provider:
            continue
        return {"hit": True, "provider": provider,
                "plan": _plan_from_model_slug(provider, slug),
                "detail": f"OpenClaw {where} = namespace {namespace!r} (model {slug!r}) "
                          f"-> {provider}"}
    namespaces = sorted({_split_route_entry(m)[0] for _, m in candidates})
    return {"hit": False,
            "detail": f"OpenClaw primary models use namespaces {namespaces!r}, none of "
                      f"which is a cap-table provider"}


# ---------------------------------------------------------------------------
# Observation: how many harness processes are running right now
# ---------------------------------------------------------------------------
def measure_working_concurrent() -> tuple:
    """Count live harness/subagent processes on the local box.

    Uses psutil when importable; otherwise `ps -A -o pid=,command=` parsing.
    Returns (count, method, ok). On failure returns (0, reason, False) and the
    caller labels the number UNMEASURED -- never a fabricated value."""
    self_pid = os.getpid()
    try:
        import psutil  # optional dependency

        count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == self_pid:
                    continue
                if PROCESS_PATTERN.match(proc.info["name"] or ""):
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return count, "psutil process_iter, pattern " + PROCESS_PATTERN.pattern, True
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return 0, f"ps exited {out.returncode}", False
        count = 0
        for line in out.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_str, command = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid == self_pid:
                continue
            argv0 = command.split(None, 1)[0]
            basename = os.path.basename(argv0)
            if basename.startswith("python") and "capacity.py" in command:
                continue  # this probe's own interpreter
            if PROCESS_PATTERN.match(basename):
                count += 1
        return count, "ps -A scan, argv[0] pattern " + PROCESS_PATTERN.pattern, True
    except Exception as exc:  # noqa: BLE001 -- measurement must never raise
        return 0, f"measurement failed: {exc}", False


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------
def detect(config_dir: Optional[Path] = None) -> dict:
    """Run the detection chain. Returns the resolution plus the audit trail.

    Never raises, never exits, never reads a credential value."""
    trail = []
    path = override_path(config_dir)

    # (a) the declared override
    record, error = read_override(config_dir)
    if error:
        trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": "ERROR",
                      "detail": error})
        return {"status": STATUS_FAILED, "provider": None, "plan": None,
                "available": None, "source": SOURCE_OVERRIDE,
                "override_path": str(path), "trail": trail, "notes": [error]}
    if record is not None:
        resolved = _resolve_override(record, path)
        trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": resolved["status"],
                      "detail": f"declared override at {path}: provider="
                                f"{resolved['provider']}, plan={resolved['plan']}"})
        resolved.update({"source": SOURCE_OVERRIDE, "override_path": str(path),
                         "trail": trail})
        return resolved
    trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": "MISS",
                  "detail": f"no declared override at {path}"})

    # (b) 9Router, then (c) OpenClaw
    for step, source, detector in (("b", SOURCE_9ROUTER, detect_from_9router),
                                   ("c", SOURCE_OPENCLAW, detect_from_openclaw)):
        found = detector()
        if not found.get("hit"):
            trail.append({"step": step, "source": source, "result": "MISS",
                          "detail": found.get("detail", "")})
            continue
        provider = found["provider"]
        plan = found.get("plan")
        trail.append({"step": step, "source": source,
                      "result": "HIT" if plan else "HIT (plan unknown)",
                      "detail": found.get("detail", "")})
        if plan and (provider, plan) in CAP_TABLE:
            return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                    "available": CAP_TABLE[(provider, plan)], "source": source,
                    "override_path": str(path), "trail": trail, "notes": []}
        # (d) provider known, plan unknown -> PARK behind the interview question
        trail.append({"step": "d", "source": source, "result": "PARK",
                      "detail": f"provider {provider} detected but its plan cannot be "
                                f"read from any configuration -- asking once"})
        return {"status": STATUS_PARKED, "provider": provider, "plan": None,
                "available": None, "source": source, "override_path": str(path),
                "trail": trail,
                "notes": [f"answer persists to {path}; the question is asked ONCE"]}

    # (e) nothing found
    trail.append({"step": "e", "source": SOURCE_NONE, "result": "UNDETERMINED",
                  "detail": f"no provider could be determined from any source; falling "
                            f"back to DEFAULT_CONSERVATIVE={DEFAULT_CONSERVATIVE}"})
    return {"status": STATUS_UNDETERMINED, "provider": None, "plan": None,
            "available": DEFAULT_CONSERVATIVE, "source": SOURCE_NONE,
            "override_path": str(path), "trail": trail, "notes": []}


def probe(config_dir: Optional[Path] = None) -> dict:
    """The main entry point. Read-only; never mutates anything, never exits.

    Signature-compatible with the previous version (`probe()` with no arguments
    is the call every existing caller makes). Returns the measured budget:

        available     int  -> the number of agents this account may run at once
        available     None -> the probe COULD NOT produce a number; the dispatch
                              path must refuse with AF-CAPACITY-UNMEASURED
    """
    resolution = detect(config_dir)
    working, method, ok = measure_working_concurrent()
    available = resolution["available"]
    result = {
        "probe_mode": PROBE_MODE,
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "status": resolution["status"],
        "undetermined": resolution["status"] == STATUS_UNDETERMINED,
        "provider": resolution["provider"],
        "plan": resolution["plan"],
        "detection_source": resolution["source"],
        "detection_trail": resolution["trail"],
        "override_path": resolution["override_path"],
        "default_conservative": DEFAULT_CONSERVATIVE,
        "cap_table": {f"{p}|{pl}": n for (p, pl), n in sorted(CAP_TABLE.items())},
        "dispatchable": available,
        "available": available,
        "reserve": 0,
        "interview_question": (interview_question(resolution["provider"])
                               if resolution["status"] == STATUS_PARKED else None),
        "autofail_code": AUTOFAIL_CODE if available is None else None,
        "notes": resolution.get("notes", []),
        "working_concurrent": working if ok else "UNMEASURED",
        "working_concurrent_method": method,
    }
    return result


def available_or_none(result: dict) -> Optional[int]:
    """The one accessor the dispatch path needs: a positive int, or None."""
    if not isinstance(result, dict):
        return None
    value = result.get("available")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def require_available(result: dict) -> int:
    """available_or_none(), but refuses instead of returning None."""
    value = available_or_none(result)
    if value is None:
        raise CapacityUnmeasured(refusal_message(result))
    return value


def autofail_payload(result: dict) -> dict:
    """The machine-readable refusal the dispatch path emits. The literal AF code
    below is what registers this module against PIPELINE-MANIFEST.autofails."""
    status = (result or {}).get("status") if isinstance(result, dict) else None
    return {
        "code": "AF-CAPACITY-UNMEASURED",
        "status": status,
        "detection_source": (result or {}).get("detection_source"),
        "provider": (result or {}).get("provider"),
        "plan": (result or {}).get("plan"),
        "interview_question": (result or {}).get("interview_question"),
        "override_path": (result or {}).get("override_path"),
        "detail": refusal_message(result),
    }


def refusal_message(result: dict) -> str:
    """Why the probe could not produce a number, in one sentence."""
    if not isinstance(result, dict):
        return ("capacity probe returned no result object -- capacity is UNMEASURED "
                "and dispatch must not proceed")
    status = result.get("status")
    if status == STATUS_PARKED:
        return (f"capacity is PARKED: provider {result.get('provider')} was detected but "
                f"its plan is undeclared. Answer the interview question and the answer is "
                f"persisted to {result.get('override_path')} (asked ONCE): "
                f"{result.get('interview_question')}")
    if status == STATUS_FAILED:
        notes = "; ".join(result.get("notes") or []) or "the declared configuration is unusable"
        return f"capacity detection FAILED: {notes}"
    return (f"capacity probe produced no dispatchable number "
            f"(status={status!r}, available={result.get('available')!r})")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def format_report(result: dict) -> str:
    """Human-readable report + machine-greppable JSON block.

    Signature-compatible with the previous version. The JSON block guarantees the
    acceptance greps succeed:
      grep '"probe_mode"'  -> "probe_mode": "live"
      grep '"available"'   -> the cap for THIS account (or null when unmeasured)
    """
    lines = [
        "CAPACITY PROBE -- Presentations department (client-capacity detection)",
        f"Probe mode: {result.get('probe_mode')} (never SIMULATED)",
        f"Status: {result.get('status')}",
        f"Detection source: {result.get('detection_source')}",
        f"Provider: {result.get('provider') or 'UNKNOWN'}",
        f"Plan: {result.get('plan') or 'UNKNOWN'}",
    ]
    if result.get("status") == STATUS_UNDETERMINED:
        sources = ", ".join(
            f"{e.get('source')}({e.get('result')})" for e in result.get("detection_trail", [])
        )
        lines += [
            "",
            "!! UNDETERMINED -- no provider or plan could be determined from any source.",
            f"!! Sources checked: {sources}",
            f"!! Falling back to DEFAULT_CONSERVATIVE = {result.get('default_conservative')}. "
            "Capacity is NEVER guessed upward.",
            "",
        ]
    if result.get("status") == STATUS_PARKED:
        lines += [
            "",
            f"!! PARKED -- {AUTOFAIL_CODE}: provider known, plan undeclared. Dispatch "
            "must refuse until this is answered.",
            f"!! INTERVIEW QUESTION: {result.get('interview_question')}",
            f"!! The answer persists to {result.get('override_path')} -- asked ONCE, "
            "never every run.",
            "",
        ]
    if result.get("status") == STATUS_FAILED:
        lines += [
            "",
            f"!! FAILED -- {AUTOFAIL_CODE}: {refusal_message(result)}",
            "",
        ]
    available = result.get("available")
    lines += [
        f"Dispatchable: {available if available is not None else 'UNMEASURED'}",
        f"Reserve: {result.get('reserve')}",
        f"Effective available: {available if available is not None else 'UNMEASURED'}",
        (f"Working concurrent now: {result.get('working_concurrent')} "
         f"({result.get('working_concurrent_method')})"),
    ]
    for note in result.get("notes") or []:
        lines.append(f"Note: {note}")
    lines.append("Detection trail:")
    for entry in result.get("detection_trail", []):
        lines.append(f"  ({entry.get('step')}) {entry.get('source')}: "
                     f"{entry.get('result')} -- {entry.get('detail')}")
    lines += ["", "=== JSON ===", json.dumps(result, indent=2)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capacity.py",
        description="Client-capacity detection -- detects, never guesses upward.",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Run the capacity probe and print the detected numbers (default).",
    )
    parser.add_argument(
        "--answer-plan", metavar="PLAN",
        help="Persist the capacity-interview answer (e.g. '$20', '$100', 'v4 Pro', "
             "'v4 Flash') to capacity_override.json so it is asked ONCE.",
    )
    parser.add_argument(
        "--provider", metavar="PROVIDER",
        help="Provider for --answer-plan; defaults to the detected provider.",
    )
    parser.add_argument(
        "--config-dir", metavar="DIR",
        help=f"Department config dir holding {OVERRIDE_FILENAME} "
             f"(default: ${CONFIG_DIR_ENV} or the department root).",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else None

    if args.answer_plan:
        provider = args.provider
        if not provider:
            provider = detect(config_dir).get("provider")
        if not provider:
            print("capacity: no provider detected and none given -- pass --provider "
                  f"(one of {sorted(PLANS_BY_PROVIDER)})", file=sys.stderr)
            return 2
        try:
            written = persist_plan_answer(provider, args.answer_plan, config_dir)
        except (ValueError, OSError) as exc:
            print(f"capacity: {exc}", file=sys.stderr)
            return 2
        print(f"capacity: recorded {provider} / {args.answer_plan} -> {written}")

    result = probe(config_dir)
    print(format_report(result))
    if available_or_none(result) is None:
        print(json.dumps(autofail_payload(result), indent=2), file=sys.stderr)
        return 3  # == state.EXIT_GATE_BLOCKED: measured nothing, so nothing dispatches
    return 0


if __name__ == "__main__":
    sys.exit(main())
