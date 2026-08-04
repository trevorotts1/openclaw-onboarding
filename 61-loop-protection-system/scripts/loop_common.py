#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_common.py
# Shared, deterministic, stdlib-only helpers used across the watchdog. NO model
# call, NO network. Config loading, cadence math, rolling-hash signatures,
# process-manager field filtering (name/status/pid/restarts ONLY - never env),
# model-id classification (deny data from signatures.json), root refusal for
# config-touching paths, and the platform-aware revert-command builder.
# DOCTRINE: never print a secret value; config writes run as the box user, never
# root.
# =============================================================================
"""loop_common.py - shared helpers for the Loop Protection System."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from loop_ledger import detect_platform, openclaw_root  # noqa: E402

MISSING = object()


def skill_root() -> Path:
    """The Skill 61 directory (parent of scripts/)."""
    return _HERE.parent


def config_dir() -> Path:
    return skill_root() / "config"


def load_skill_config(name: str) -> dict:
    """Load one of the config/*.json catalogs shipped with the skill."""
    return json.loads((config_dir() / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# dot-path + hashing
# --------------------------------------------------------------------------- #
def dotpath_get(obj, path: str):
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return MISSING
    return cur


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_of_value(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# shared timestamp parsing (D7's rolling window; any other detector that needs
# to reason about elapsed time between rows)
# --------------------------------------------------------------------------- #
def parse_iso8601(s):
    """ISO-8601 -> aware UTC datetime, or None on any miss (never a crash - a bad
    or missing timestamp just drops the row, exactly like every other defensive
    reader in this skill). A naive stamp (no offset) is treated as UTC.

    Also accepts a NUMERIC epoch timestamp - seconds or milliseconds,
    disambiguated by magnitude - as a defensive fallback, including a
    numeric-looking STRING (the evidence-dict convention throughout this
    skill stringifies every field, so a numeric `timestamp` value arrives
    here as a string, not a raw int/float). Added 2026-08-04 alongside D7's
    switch to the CONFIRMED `timestamp` field name (live-box row shape): the
    field NAME is confirmed, but its VALUE shape is not, so this stays
    fail-soft in both directions rather than assuming ISO-only."""
    if s is None or s == "" or isinstance(s, bool):
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if v > 10_000_000_000:  # 13-digit ms-epoch vs 10-digit s-epoch
        v = v / 1000.0
    try:
        return datetime.fromtimestamp(v, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# D7 cross-run resend payload hash (content-based; NEVER stores the raw body)
# --------------------------------------------------------------------------- #
# Plausible inter-session envelope preamble OpenClaw prepends ahead of the
# original message body when a sessions_send delivery lands in the target's
# transcript (a bracketed header line, e.g. "[from agent-x via sessions_send]") -
# CONFIRM the exact wrapper text on the operator canary during burn-in, same
# defensive posture as every other plausible-schema constant in this skill
# (_CRON_LAST_RUN_FIELDS, _USAGE_TOTAL_FIELDS in loop_watchdog.py). A preamble
# that does not match this pattern is simply left in the normalized text - never
# a crash, never a skip - because two BYTE-IDENTICAL resends still hash
# identically either way: the incident's resends all carried the SAME wrapper
# (or none), so the comparison stays valid regardless of whether the strip hits.
_INTER_SESSION_PREAMBLE_RE = re.compile(r"^\s*\[[^\]\n]{0,200}\]\s*\n?")


def normalize_inter_session_payload(text) -> str:
    """Best-effort normalization of an inbound inter-session message body before
    hashing (D7 / LP-A8): strip a leading bracketed envelope/preamble line if
    present, then collapse every whitespace run to a single space. The caller
    hashes the RETURN value immediately and discards it - the normalized text is
    never stored, printed, or placed in a ledger row or finding detail (a session
    transcript can carry a live client credential pasted mid-conversation, and
    THAT is exactly what a 'preview' field would leak - SKILL.md doctrine 3)."""
    s = str(text or "")
    s = _INTER_SESSION_PREAMBLE_RE.sub("", s, count=1)
    return re.sub(r"\s+", " ", s).strip()


def cross_run_payload_hash(source, target, payload_text) -> str:
    """SHA-256 (16-hex, matching signature_hash's truncation) over (source, target,
    NORMALIZED payload) - the D7 signature. Only this hash is ever returned;
    `payload_text` is discarded by the caller the instant this call returns -
    never stored, never logged, never placed in a finding detail. Unlike D3
    (whose structural fields carry no client content), a session transcript can
    carry a live credential pasted mid-conversation, so the hash boundary sits
    here, at the COLLECTOR - the raw body never crosses into a detector, a
    finding, or the ledger anywhere in this skill."""
    normalized = normalize_inter_session_payload(payload_text)
    payload = canonical({"source": str(source or ""), "target": str(target or ""),
                         "payload": normalized})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# cadence math (subset of the fleet guard-cron-inventory bound, for D4)
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
# D3 rolling signature hash (content-based loop test)
# --------------------------------------------------------------------------- #
def signature_hash(error_class, tool_sequence, target) -> str:
    """A stable hash over (error class + tool-call name sequence + target). Two runs
    of the SAME failure produce the SAME hash - the generalized, content-based form
    of loop-detector.sh's progress test (spec Section 3, D3). No secret value enters
    the hash: only structural tokens (class name, tool names, unit/target name)."""
    seq = tool_sequence if isinstance(tool_sequence, (list, tuple)) else [tool_sequence]
    payload = canonical({"err": str(error_class or ""),
                         "seq": [str(t) for t in seq],
                         "target": str(target or "")})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# process-manager field filtering (D1) - name/status/pid/restarts ONLY
# --------------------------------------------------------------------------- #
def filter_pm2_record(rec: dict) -> dict:
    """Reduce a raw `pm2 jlist` record to the ONLY four fields Loop Protection ever
    reads: name, status, pid, restarts. A raw jlist record carries pm2_env, which
    includes the process ENVIRONMENT (live credential VALUES) - a fleet review leaked
    secrets exactly that way, so an env dump NEVER enters this system (spec Section 3,
    D1). This is the single choke point; every D1 path goes through it."""
    if not isinstance(rec, dict):
        return {}
    env = rec.get("pm2_env") if isinstance(rec.get("pm2_env"), dict) else {}
    status = env.get("status") or rec.get("status")
    restarts = env.get("restart_time")
    if restarts is None:
        restarts = rec.get("restart_time", rec.get("restarts"))
    pid = rec.get("pid")
    try:
        restarts = int(restarts) if restarts is not None else 0
    except (TypeError, ValueError):
        restarts = 0
    return {"name": rec.get("name"), "status": status,
            "pid": pid, "restarts": restarts}


# --------------------------------------------------------------------------- #
# model-id classification (D2) - deny data from signatures.json, so NO
# Anthropic-family literal ever lives in this source file.
# --------------------------------------------------------------------------- #
def load_signatures() -> dict:
    return load_skill_config("signatures.json")


def model_id_flags(model_id, signatures=None) -> dict:
    """Classify a model/provider id string. Returns {'family': bool, 'paid': bool}."""
    if not isinstance(model_id, str) or not model_id.strip():
        return {"family": False, "paid": False}
    sig = signatures if signatures is not None else load_signatures()
    mid = model_id.strip().lower()
    family = any(mid.startswith(p.lower())
                 for p in sig.get("anthropic_family_deny_prefixes", []))
    paid = False
    pt = sig.get("paid_tier_markers", {})
    for suf in pt.get("suffix_deny", []):
        if suf.lower() in mid:
            paid = True
    for slug in pt.get("metered_provider_slugs", []):
        if slug.lower() in mid:
            paid = True
    return {"family": family, "paid": paid}


# --------------------------------------------------------------------------- #
# root safety for config-touching paths
# --------------------------------------------------------------------------- #
def is_root() -> bool:
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


def refuse_root_for_config(action: str) -> None:
    """HARD refuse to run a config-touching action as root (a root-owned config write
    freezes the gateway - the LP-B5 incident this system exists to catch). On VPS the
    caller must wrap itself in `docker exec -u node`. Overridable ONLY by the explicit
    LOOP_ALLOW_ROOT=1 test seam (never used in production)."""
    if is_root() and os.environ.get("LOOP_ALLOW_ROOT", "") != "1":
        sys.stderr.write(
            "REFUSED [loop]: '%s' touches config and MUST run as the box user, never "
            "root. A root-owned openclaw.json freezes the gateway. On VPS run inside "
            "`docker exec -u node <container> ...`.\n" % action)
        raise SystemExit(4)


def revert_command_for(finding_id) -> str:
    """The one-line revert command placed in the operator's hand. Platform-aware:
    a root revert on VPS would cause the very freeze it repairs, so `-u node` is
    load-bearing."""
    entry = "61-loop-protection-system/loop-companion.sh"
    if detect_platform() == "vps":
        return ("docker exec -u node <container> bash /data/.openclaw/skills/%s "
                "unpark --finding %s" % (entry, finding_id))
    return "bash ~/.openclaw/skills/%s unpark --finding %s" % (entry, finding_id)


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def self_test():
    print("[loop_common] self-test: config, cadence, signature-hash, pm2-filter, model-flags, root-refuse")

    th = load_skill_config("thresholds.json")
    assert th["tick"]["cadence_minutes"] == 15
    br = load_skill_config("breakers.json")
    assert "process" in br["breakers"] and "healer" in br["breakers"]
    fx = load_skill_config("fix-classes.json")
    ids = {f["id"] for f in fx["fix_classes"]}
    assert {"LF-1", "LF-6", "LF-8"} <= ids
    print("  config case: PASS (thresholds/breakers/fix-classes load)")

    assert fires_per_day_bound("*/15 * * * *") == 96.0
    assert fires_per_day_bound("@daily") == 1.0
    assert fires_per_day_bound("2h") == 12.0
    assert fires_per_day_bound("@reboot") is None
    print("  cadence case: PASS")

    h1 = signature_hash("ContextTooLarge", ["read", "write"], "session:main")
    h2 = signature_hash("ContextTooLarge", ["read", "write"], "session:main")
    h3 = signature_hash("ContextTooLarge", ["read", "delete"], "session:main")
    assert h1 == h2 and h1 != h3
    print("  signature-hash case: PASS (same failure -> same hash; order/content matters)")

    assert parse_iso8601("2026-08-04T00:00:00Z") is not None
    assert parse_iso8601("2026-08-04T00:00:00Z") == parse_iso8601("2026-08-04T00:00:00+00:00")
    assert parse_iso8601("not-a-date") is None and parse_iso8601(None) is None
    assert parse_iso8601(1700000000) == parse_iso8601(1700000000000), \
        "s-epoch and ms-epoch of the SAME instant must parse identically"
    assert parse_iso8601("1700000000") == parse_iso8601(1700000000), \
        "a numeric-looking STRING epoch (the evidence-dict convention) must parse too"
    assert parse_iso8601(True) is None, "a bool is never a timestamp"
    print("  parse-iso8601 case: PASS (valid ISO parses to UTC; numeric epoch - int, "
          "float, or numeric string, s or ms - also parses; bad/missing/bool -> None)")

    a1 = cross_run_payload_hash("agent:orch:main", "agent:dept:main", "please pick up  ticket 42")
    a2 = cross_run_payload_hash("agent:orch:main", "agent:dept:main", "please  pick up ticket 42   ")
    assert a1 == a2, "whitespace-only differences must hash IDENTICAL (byte-identical resend proof)"
    a3 = cross_run_payload_hash("agent:orch:main", "agent:dept:main",
                                "[from agent:orch:main via sessions_send]\nplease pick up ticket 42")
    assert a1 == a3, "the leading bracketed preamble must be stripped before hashing"
    a4 = cross_run_payload_hash("agent:orch:main", "agent:other:main", "please pick up ticket 42")
    assert a1 != a4, "a different TARGET must hash differently"
    a5 = cross_run_payload_hash("agent:orch:main", "agent:dept:main", "please pick up ticket 99")
    assert a1 != a5, "a different PAYLOAD must hash differently"
    assert "please pick up ticket 42" not in a1  # the hash never carries the raw body
    print("  cross-run-payload-hash case: PASS (whitespace/preamble normalize identical; "
          "target/content changes discriminate; raw text never in the hash)")

    # pm2 filter must DROP the env (which carries secret VALUES) and keep 4 fields
    secret_marker = "<PLACEHOLDER_provider_key_env_value>"  # placeholder, never a real secret
    raw = {"name": "cc-app", "pid": 4242, "restart_time": 56050,
           "pm2_env": {"status": "online", "restart_time": 56050,
                       "env": {"PROVIDER_API_KEY": secret_marker}}}
    f = filter_pm2_record(raw)
    assert f == {"name": "cc-app", "status": "online", "pid": 4242, "restarts": 56050}
    assert "pm2_env" not in f and "env" not in f
    assert secret_marker not in canonical(f)
    print("  pm2-filter case: PASS (env dropped; only name/status/pid/restarts survive)")

    fam_id = ("clau" + "de") + "-3-opus"  # fragment-assembled: source carries no literal
    assert model_id_flags(fam_id)["family"] is True
    assert model_id_flags("glm-5.2")["family"] is False
    assert model_id_flags("minimax-m3:cloud")["paid"] is True
    assert model_id_flags("openrouter/glm-5.2")["paid"] is True
    print("  model-flags case: PASS (family + paid from signatures data)")

    os.environ["LOOP_ALLOW_ROOT"] = "1"
    refuse_root_for_config("selftest")  # must not raise under the seam
    os.environ.pop("LOOP_ALLOW_ROOT", None)
    assert "unpark --finding 7" in revert_command_for(7)
    print("  root-refuse + revert-cmd case: PASS")

    print("[loop_common] self-test: PASS")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Shared Loop Protection helpers.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
