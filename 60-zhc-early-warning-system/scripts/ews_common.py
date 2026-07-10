#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_common.py
# Shared, deterministic, stdlib-only helpers used across the sentinel. NO model
# call, NO network. Config resolution, dot-path reads, cadence math, model-id
# extraction, root refusal for config-touching paths, and the value-free hashing
# the whole skill uses. DOCTRINE: never print a secret value; config writes run
# as the box user, never root.
# =============================================================================
"""ews_common.py - shared helpers for the ZHC Early Warning System."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# Import the platform/path resolution from the ledger so there is ONE source.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from ews_ledger import detect_platform, openclaw_root  # noqa: E402

MISSING = object()  # sentinel distinct from JSON null


def skill_root() -> Path:
    """The Skill 60 directory (parent of scripts/)."""
    return _HERE.parent


def config_dir() -> Path:
    return skill_root() / "config"


def load_skill_config(name: str) -> dict:
    """Load one of the config/*.json catalogs shipped with the skill."""
    p = config_dir() / name
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# live config resolution
# --------------------------------------------------------------------------- #
def default_config_path() -> Path:
    """The live openclaw.json for this box. Env EWS_CONFIG_PATH overrides (tests)."""
    env = os.environ.get("EWS_CONFIG_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return openclaw_root() / "openclaw.json"


def read_config(path=None) -> dict:
    p = Path(path) if path else default_config_path()
    return json.loads(p.read_text(encoding="utf-8"))


def dotpath_get(obj, path: str):
    """Read a dot-path like 'agents.defaults.model.primary' out of a nested dict.
    Returns MISSING when any segment is absent. Never raises."""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return MISSING
    return cur


# --------------------------------------------------------------------------- #
# hashing (value-free storage / comparison)
# --------------------------------------------------------------------------- #
def canonical(value) -> str:
    """A stable canonical JSON string for any monitored value (order-independent)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_of_value(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# cadence math (subset of the fleet guard-cron-inventory bound, for S5/S10)
# --------------------------------------------------------------------------- #
_INTERVAL_UNITS = {"s": 1, "sec": 1, "second": 1, "seconds": 1,
                   "m": 60, "min": 60, "minute": 60, "minutes": 60,
                   "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
                   "d": 86400, "day": 86400, "days": 86400,
                   "w": 604800, "week": 604800, "weeks": 604800}
_AT_SHORTCUTS = {"@yearly": 1.0 / 365, "@annually": 1.0 / 365, "@monthly": 1.0 / 30,
                 "@weekly": 1.0 / 7, "@daily": 1.0, "@midnight": 1.0, "@hourly": 24.0}


def _field_count(field, lo, hi):
    total = 0
    for part in str(field).split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        base = part
        if "/" in part:
            base, s = part.split("/", 1)
            try:
                step = max(1, int(s))
            except ValueError:
                return hi - lo + 1
        if base in ("*", ""):
            a, b = lo, hi
        elif "-" in base:
            x, y = base.split("-", 1)
            try:
                a, b = int(x), int(y)
            except ValueError:
                return hi - lo + 1
        else:
            try:
                a = b = int(base)
            except ValueError:
                return hi - lo + 1
        if b < a:
            a, b = b, a
        cnt, v = 0, a
        while v <= b:
            cnt += 1
            v += step
        total += cnt
    return total if total > 0 else 1


def fires_per_day_bound(schedule):
    """Upper bound on fires per day, or None if unparseable. <=1 is once-daily."""
    if schedule is None:
        return None
    s = str(schedule).strip().lower()
    if not s:
        return None
    if s in _AT_SHORTCUTS:
        return _AT_SHORTCUTS[s]
    if s == "@reboot":
        return None
    m = re.match(r"^(?:@every\s+|every\s+)?(\d+)\s*([a-z]+)$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        sec = _INTERVAL_UNITS.get(unit)
        if sec:
            secs = n * sec
            return None if secs <= 0 else 86400.0 / secs
        return None
    fields = s.split()
    if len(fields) in (5, 6):
        if len(fields) == 6:
            sec_c = _field_count(fields[0], 0, 59)
            minute, hour = fields[1], fields[2]
        else:
            sec_c = 1
            minute, hour = fields[0], fields[1]
        return float(sec_c * _field_count(minute, 0, 59) * _field_count(hour, 0, 23))
    return None


# --------------------------------------------------------------------------- #
# model-id extraction (S1/S2 allowlist)
# --------------------------------------------------------------------------- #
def extract_model_ids(config) -> list:
    """The set of model ids this config references: primary + fallbacks + the
    explicit models map keys + subagent models. Deterministic sorted list."""
    ids = set()
    defaults = dotpath_get(config, "agents.defaults")
    if not isinstance(defaults, dict):
        return []

    def add(v):
        if isinstance(v, str) and v.strip():
            ids.add(v.strip())
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x.strip():
                    ids.add(x.strip())

    for base in (defaults, defaults.get("subagents") if isinstance(defaults.get("subagents"), dict) else {}):
        if not isinstance(base, dict):
            continue
        model = base.get("model")
        if isinstance(model, dict):
            add(model.get("primary"))
            add(model.get("fallbacks"))
    models_map = defaults.get("models")
    if isinstance(models_map, dict):
        for k in models_map.keys():
            add(k)
    hb = defaults.get("heartbeat")
    if isinstance(hb, dict):
        add(hb.get("model"))
    return sorted(ids)


# --------------------------------------------------------------------------- #
# cron inventory normalization (S10)
# --------------------------------------------------------------------------- #
def cron_inventory(config) -> list:
    """Normalized cron entries: [{name, schedule, delivery, target}]. Reads the
    openclaw.json `cron` key (array, or object wrapping crons/jobs/entries)."""
    raw = config.get("cron") if isinstance(config, dict) else None
    items = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in ("crons", "jobs", "entries", "items", "schedules"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name") or it.get("id") or "<unnamed>"
        sched = it.get("schedule") or it.get("cron") or it.get("interval") or it.get("when")
        delivery = (it.get("delivery") or it.get("deliveryMode") or it.get("mode")
                    or ("announce" if it.get("announce") is True else None))
        target = it.get("target") or it.get("chat") or it.get("account")
        out.append({"name": str(name), "schedule": sched,
                    "delivery": (str(delivery).lower() if delivery else None),
                    "target": (str(target) if target else None)})
    return sorted(out, key=lambda e: e["name"])


# --------------------------------------------------------------------------- #
# root safety for config-touching paths
# --------------------------------------------------------------------------- #
def is_root() -> bool:
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


def refuse_root_for_config(action: str) -> None:
    """HARD refuse to run a config-touching action as root (a root-owned config
    write freezes the gateway - the exact S6 incident this system exists to catch).
    On VPS the caller must wrap itself in `docker exec -u node`. Overridable ONLY by
    the explicit EWS_ALLOW_ROOT=1 test seam (never used in production)."""
    if is_root() and os.environ.get("EWS_ALLOW_ROOT", "") != "1":
        sys.stderr.write(
            "REFUSED [ews]: '%s' touches config and MUST run as the box user, never "
            "root. A root-owned openclaw.json freezes the gateway. On VPS run inside "
            "`docker exec -u node <container> ...`.\n" % action)
        raise SystemExit(4)


def revert_command_for(ts_token: str) -> str:
    """The one-line revert command placed in the operator's hand. Platform-aware:
    a root revert on VPS would cause the very freeze it repairs, so `-u node` is
    load-bearing."""
    entry = "60-zhc-early-warning-system/ews-entry.sh"
    if detect_platform() == "vps":
        return ("docker exec -u node <container> bash /data/.openclaw/skills/%s "
                "revert --to %s" % (entry, ts_token))
    return "bash ~/.openclaw/skills/%s revert --to %s" % (entry, ts_token)


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def self_test():
    print("[ews_common] self-test: dotpath, hashing, cadence, model-ids, cron, root-refuse")
    cfg = {"agents": {"defaults": {
        "model": {"primary": "glm-5.2", "fallbacks": ["minimax-m3:cloud", "deepseek-v4"]},
        "models": {"openrouter/glm-5.2": {}, "ollama-cloud/minimax-m3:cloud": {}},
        "subagents": {"model": {"primary": "gemini-3.5-flash", "fallbacks": []},
                      "maxConcurrent": 16},
        "heartbeat": {"every": "@daily", "model": "minimax-m3"},
        "compaction": {"memoryFlush": {"softThresholdTokens": 20000}}}},
        "channels": {"telegram": {"accounts": {"default": {"allowFrom": ["1"], "dmPolicy": "allowlist"}}}},
        "cron": [{"name": "ews-tick", "schedule": "*/15 * * * *", "delivery": "silent"}]}

    assert dotpath_get(cfg, "agents.defaults.model.primary") == "glm-5.2"
    assert dotpath_get(cfg, "agents.defaults.subagents.maxConcurrent") == 16
    assert dotpath_get(cfg, "agents.defaults.nope.here") is MISSING
    print("  dotpath case: PASS")

    assert sha256_of_value(64) == sha256_of_value(64)
    assert sha256_of_value([1, 2]) != sha256_of_value([2, 1])  # order matters for lists
    assert sha256_of_value({"a": 1, "b": 2}) == sha256_of_value({"b": 2, "a": 1})  # dict order-free
    print("  hashing case: PASS (value-free, deterministic, dict order-independent)")

    assert fires_per_day_bound("*/15 * * * *") == 96.0
    assert fires_per_day_bound("@daily") == 1.0
    assert fires_per_day_bound("0 * * * *") == 24.0
    assert fires_per_day_bound("15m") == 96.0
    assert fires_per_day_bound("@reboot") is None
    print("  cadence case: PASS")

    ids = extract_model_ids(cfg)
    assert "glm-5.2" in ids and "minimax-m3:cloud" in ids and "gemini-3.5-flash" in ids
    assert "minimax-m3" in ids  # heartbeat model included
    print("  model-ids case: PASS (%d ids)" % len(ids))

    inv = cron_inventory(cfg)
    assert len(inv) == 1 and inv[0]["name"] == "ews-tick" and inv[0]["delivery"] == "silent"
    print("  cron case: PASS")

    # root refuse honors the test seam
    os.environ["EWS_ALLOW_ROOT"] = "1"
    refuse_root_for_config("selftest")  # must not raise under the seam
    os.environ.pop("EWS_ALLOW_ROOT", None)
    print("  root-refuse case: PASS (seam honored; hard-refuses as root otherwise)")

    rc = revert_command_for("20260101T000000")
    assert "revert --to 20260101T000000" in rc
    print("  revert-command case: PASS")

    print("[ews_common] self-test: PASS")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Shared EWS helpers.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
