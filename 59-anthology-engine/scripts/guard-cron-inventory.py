#!/usr/bin/env python3
"""guard-cron-inventory.py -- proves the cron INVENTORY, never the intention.

Unit W2.5. SPEC 3.4 row 25 / SPEC 2.1 (daily tick) / config.cron / AF-AE-CRON-DRIFT.

Asserts the invariant that the Anthology Engine installs EXACTLY the one daily tick and
NOTHING else recurring: no heartbeat cron ever (PRD Section 15 explicitly bans "any
heartbeat cron beyond the one daily tick"; the daily smoke test IS the heartbeat
substitute, PRD Section 10 loop 1), and that a full provision/revoke churn cycle leaves
ZERO recurring jobs (SPEC 13.3: revoke-anthology-client.sh "leave ZERO recurring jobs,
guard-cron-inventory.py proves it").

WHAT IT INSPECTS: the live OpenClaw cron inventory as emitted by `openclaw cron list
--json` (schema: a top-level {"jobs":[...], "total":...} envelope; each job carries
id/name/description/enabled/schedule{kind,expr,tz}/payload/delivery/state/status). The
guard accepts that envelope, a bare list of job objects, or a single job -- from an
--inventory file, from --stdin, or fetched live with --live. It does NOT shell out to the
gateway on its own; a source is always explicit, so an automated gate run never surprises
the live scheduler.

SCOPING: the guard polices ONLY the engine's OWN jobs (owner-tag match, default
"anthology", on name/description/sessionTarget/agentId/payload). The operator's fleet
heartbeat and every other unrelated cron are IGNORED by design -- the engine has no
business deleting the operator's schedule; it only proves that IT installed exactly one
daily tick and left nothing recurring behind.

TWO EXPECTATIONS:
  --expect one   (default; steady state / post-provision) exactly one recurring engine
                 job, it must be DAILY cadence (not sub-daily = a disguised heartbeat, not
                 supra-daily = not actually a daily tick), and no engine job may be a
                 heartbeat by name.
  --expect zero  (post-revoke / churn) zero recurring engine jobs remain and no engine
                 heartbeat lingers -- a paused-but-present recurring definition still
                 counts as a leftover (enforcement, not description).

DOCTRINE: this guard NEVER prints a cron PAYLOAD MESSAGE, a DELIVERY CHANNEL (chat ids
are client-adjacent PII), or an agentId. Non-engine jobs are only ever counted, never
named. Engine jobs (names the engine itself authors, e.g. "anthology-daily-tick") are
named only to make a violation actionable. Move in silence.

Exit codes (SPEC 3.4 row 25; house convention for the edge cases):
  0  clean   (policy satisfied for the requested expectation, including idempotent no-op)
  4  violation (AF-AE-CRON-DRIFT: more than one tick, a heartbeat entry, a sub-daily/
                non-daily tick, or churn left a recurring job)
  2  bad invocation (no source given, an explicit --inventory path missing/unreadable, or
                     malformed inventory JSON)
  3  inventory unavailable (a live `openclaw cron list` could not be obtained)
  1  unexpected error
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_BAD, EX_DEP, EX_VIOLATION = 0, 1, 2, 3, 4

DEFAULT_OWNER_TAGS = ("anthology",)
DEFAULT_CRON_LIST_CMD = "openclaw cron list --json"

# A job whose name/description reads as a heartbeat is forbidden outright -- the daily
# smoke test is the ONLY sanctioned periodic pulse. Sub-daily cadence is caught
# structurally below regardless of name, so this is the by-name backstop.
HEARTBEAT_NAME_RE = re.compile(r"heart[\W_]?beat|keep[\W_]?alive|\bpulse\b", re.IGNORECASE)

# schedule.kind values that are NOT recurring (a one-shot never counts as a leftover tick).
_ONESHOT_KINDS = frozenset({"once", "at", "date", "oneshot", "one_shot", "reboot", "startup"})
_RECURRING_KINDS = frozenset({"cron", "interval", "recurring", "every", "rate", "periodic"})


class InventoryUnavailable(RuntimeError):
    """The live cron inventory could not be obtained (CLI maps to exit 3)."""


# ---------------------------------------------------------------------------
# Cadence classification: how often does a schedule fire?
# ---------------------------------------------------------------------------
def _field_value_count(field, lo, hi):
    """Distinct trigger values a single cron field selects within [lo, hi], or None if
    the field cannot be parsed. Handles '*', '*/step', 'a-b', 'a-b/step', and 'a,b,c'."""
    field = field.strip()
    if field in ("*", "?"):
        return hi - lo + 1
    selected = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            return None
        step = 1
        base = part
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                return None
            if step <= 0:
                return None
        if base in ("*", "?"):
            rng_lo, rng_hi = lo, hi
        elif "-" in base.lstrip("-"):  # a range like 6-21 (guard against a lone negative)
            a_s, b_s = base.split("-", 1)
            try:
                rng_lo, rng_hi = int(a_s), int(b_s)
            except ValueError:
                return None
            if rng_lo > rng_hi:
                return None
        else:
            try:
                v = int(base)
            except ValueError:
                return None
            rng_lo = rng_hi = v
        if rng_lo < lo or rng_hi > hi:
            return None
        for offset, val in enumerate(range(rng_lo, rng_hi + 1)):
            if offset % step == 0:
                selected.add(val)
    return len(selected) if selected else None


def _interval_cadence(expr):
    """Classify an interval schedule (kind='interval'). expr is seconds or a duration like
    '30m'/'24h'/'1d'. Returns one of daily / sub-daily / supra-daily / unknown."""
    if expr is None:
        return "unknown"
    s = str(expr).strip().lower()
    seconds = None
    if s.isdigit():
        seconds = int(s)
    else:
        m = re.fullmatch(r"(\d+)\s*([smhd])", s)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            seconds = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    if seconds is None:
        return "unknown"
    if seconds <= 0:
        return "unknown"
    if seconds < 86400:
        return "sub-daily"
    if seconds == 86400:
        return "daily"
    return "supra-daily"


def classify_cadence(schedule):
    """Return the firing cadence of a schedule dict: 'daily' (exactly once per day),
    'sub-daily' (more than once per day -- heartbeat class), 'supra-daily' (less than once
    per day, e.g. weekly/monthly), 'non-recurring' (one-shot), or 'unknown'."""
    if not isinstance(schedule, dict):
        return "unknown"
    kind = str(schedule.get("kind", "")).strip().lower()
    if kind in _ONESHOT_KINDS:
        return "non-recurring"
    expr = schedule.get("expr", schedule.get("cron", schedule.get("value", "")))
    if kind == "interval" or kind == "rate":
        return _interval_cadence(expr)

    expr = str(expr or "").strip()
    if not expr:
        return "unknown"

    # Named macros.
    macro = expr.lower()
    if macro in ("@reboot", "@startup"):
        return "non-recurring"
    if macro in ("@hourly",):
        return "sub-daily"
    if macro in ("@daily", "@midnight"):
        return "daily"
    if macro in ("@weekly", "@monthly", "@yearly", "@annually"):
        return "supra-daily"
    if macro.startswith("@every"):
        return _interval_cadence(macro.split(None, 1)[1] if " " in macro else "")

    fields = expr.split()
    # Accept 5-field (min hour dom mon dow) or 6-field (sec min hour dom mon dow).
    if len(fields) == 6:
        sec_count = _field_value_count(fields[0], 0, 59)
        if sec_count is None:
            return "unknown"
        if sec_count > 1:
            return "sub-daily"  # fires many times a minute
        fields = fields[1:]
    if len(fields) != 5:
        return "unknown"

    minute, hour, dom, mon, dow = fields
    minute_count = _field_value_count(minute, 0, 59)
    hour_count = _field_value_count(hour, 0, 23)
    if minute_count is None or hour_count is None:
        return "unknown"
    intra_day = minute_count * hour_count
    if intra_day > 1:
        return "sub-daily"
    if intra_day == 1:
        all_star = dom.strip() in ("*", "?") and mon.strip() == "*" and dow.strip() in ("*", "?")
        return "daily" if all_star else "supra-daily"
    return "unknown"


def _is_recurring(schedule):
    """True if the schedule would fire more than once over time (a recurring definition)."""
    if not isinstance(schedule, dict):
        return False
    kind = str(schedule.get("kind", "")).strip().lower()
    if kind in _ONESHOT_KINDS:
        return False
    if kind in _RECURRING_KINDS:
        return True
    # Unknown/blank kind: infer from the expression. Anything with a cron/interval-looking
    # expr is treated as recurring so a renamed or oddly-typed leftover is never missed.
    cadence = classify_cadence(schedule)
    return cadence in ("daily", "sub-daily", "supra-daily")


# ---------------------------------------------------------------------------
# Job normalization + ownership
# ---------------------------------------------------------------------------
def extract_jobs(obj):
    """Return the list of job dicts from a gateway-cronlist envelope, a bare list, or a
    single job dict. Raises ValueError on any other shape."""
    if isinstance(obj, dict):
        if "jobs" in obj and isinstance(obj["jobs"], list):
            jobs = obj["jobs"]
        elif {"id", "schedule"} & set(obj.keys()) or "name" in obj:
            jobs = [obj]  # a single job object
        else:
            raise ValueError("inventory dict has no 'jobs' array and is not a single job")
    elif isinstance(obj, list):
        jobs = obj
    else:
        raise ValueError("inventory must be a JSON object or array, got %s" % type(obj).__name__)
    for j in jobs:
        if not isinstance(j, dict):
            raise ValueError("every cron job must be a JSON object")
    return jobs


def _job_haystack(job):
    parts = [str(job.get(k, "")) for k in ("name", "description", "sessionTarget", "agentId")]
    payload = job.get("payload")
    if isinstance(payload, dict):
        parts.append(str(payload.get("message", "")))
        parts.append(str(payload.get("kind", "")))
        parts.append(str(payload.get("command", "")))
    return " ".join(parts).lower()


def is_engine_owned(job, owner_tags):
    hay = _job_haystack(job)
    return any(str(t).lower() in hay for t in owner_tags)


def _is_heartbeat_by_name(job):
    for k in ("name", "description"):
        if HEARTBEAT_NAME_RE.search(str(job.get(k, ""))):
            return True
    return False


def _safe_name(job):
    """A print-safe label for an ENGINE-owned job (names the engine authors are safe)."""
    name = str(job.get("name", "")).strip() or "(unnamed)"
    jid = str(job.get("id", "")).strip()
    tail = ("#" + jid[-8:]) if jid else ""
    return "%s %s" % (name, tail) if tail else name


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------
def analyze(jobs, expect="one", owner_tags=DEFAULT_OWNER_TAGS, tick_name=None):
    """Score the cron inventory against the daily-tick invariant. Returns a report dict
    with an 'ok' boolean and a typed 'violations' list. Never includes payload/delivery."""
    if expect not in ("one", "zero"):
        raise ValueError("expect must be 'one' or 'zero', got %r" % (expect,))

    engine_jobs, foreign_count = [], 0
    for j in jobs:
        if is_engine_owned(j, owner_tags):
            engine_jobs.append(j)
        else:
            foreign_count += 1

    engine_recurring = [j for j in engine_jobs if _is_recurring(j.get("schedule"))]
    heartbeat_named = [j for j in engine_jobs if _is_heartbeat_by_name(j)]

    def entry(job):
        sched = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
        return {
            "name": _safe_name(job),
            "enabled": bool(job.get("enabled", True)),
            "kind": str(sched.get("kind", "")),
            "expr": str(sched.get("expr", sched.get("cron", ""))),
            "cadence": classify_cadence(sched),
        }

    violations = []

    # A heartbeat entry is forbidden no matter the expectation, enabled or not, recurring
    # or one-shot -- "no heartbeat cron ever".
    for j in heartbeat_named:
        violations.append({
            "code": "CRON-HEARTBEAT",
            "detail": "engine-owned job reads as a heartbeat; the daily tick is the only sanctioned pulse",
            "job": entry(j),
        })

    if expect == "zero":
        # Post-revoke / churn: nothing recurring may remain.
        for j in engine_recurring:
            violations.append({
                "code": "CRON-CHURN-LEFTOVER",
                "detail": "a recurring engine job survived revoke; churn must leave zero recurring jobs",
                "job": entry(j),
            })
    else:  # expect == "one"
        n = len(engine_recurring)
        if n != 1:
            violations.append({
                "code": "CRON-COUNT",
                "detail": "expected exactly one recurring engine job (the daily tick), found %d" % n,
                "jobs": [entry(j) for j in engine_recurring],
            })
        if n == 1:
            tick = engine_recurring[0]
            cad = classify_cadence(tick.get("schedule"))
            if cad == "sub-daily":
                violations.append({
                    "code": "CRON-SUBDAILY",
                    "detail": "the tick fires more than once per day -- that is a heartbeat, not a daily tick",
                    "job": entry(tick),
                })
            elif cad != "daily":
                violations.append({
                    "code": "CRON-NOT-DAILY",
                    "detail": "the single recurring tick is not daily cadence (got %s)" % cad,
                    "job": entry(tick),
                })
            if tick_name is not None and str(tick.get("name", "")).strip() != str(tick_name).strip():
                violations.append({
                    "code": "CRON-TICK-NAME",
                    "detail": "the recurring tick name does not match the pinned --tick-name",
                    "job": entry(tick),
                })

    # De-duplicate identical violations (a heartbeat that is also the sole recurring job
    # can surface twice); keep first occurrence order.
    seen, deduped = set(), []
    for v in violations:
        key = (v["code"], json.dumps(v.get("job", v.get("jobs", "")), sort_keys=True))
        if key not in seen:
            seen.add(key)
            deduped.append(v)

    return {
        "expect": expect,
        "owner_tags": list(owner_tags),
        "total_jobs": len(jobs),
        "foreign_jobs_ignored": foreign_count,
        "engine_jobs": len(engine_jobs),
        "engine_recurring": len(engine_recurring),
        "engine_recurring_detail": [entry(j) for j in engine_recurring],
        "engine_heartbeats": len(heartbeat_named),
        "violations": deduped,
        "ok": len(deduped) == 0,
    }


def evaluate(inventory, expect="one", owner_tags=None, tick_name=None):
    """Manifest autofail symbol (ENGINE-MANIFEST AF-AE-CRON-DRIFT, py_symbol 'evaluate').

    Return True when the cron policy holds, False on any AF-AE-CRON-DRIFT violation.

    `inventory` may be: a list of job dicts, a gateway-cronlist envelope {"jobs": [...]},
    a single job dict, or a str/Path to a JSON file of any of those. `expect` is 'one'
    (steady state) or 'zero' (post-revoke churn). Raises ValueError on a malformed
    inventory and InventoryUnavailable when a given path cannot be read (the CLI maps
    these to exit 2 and 3)."""
    tags = tuple(owner_tags) if owner_tags else DEFAULT_OWNER_TAGS
    if isinstance(inventory, (str, Path)):
        p = Path(inventory)
        if not p.exists() or not p.is_file():
            raise InventoryUnavailable("inventory file not found: %s" % inventory)
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("inventory file is not valid JSON: %s" % exc)
    else:
        obj = inventory
    jobs = extract_jobs(obj)
    return analyze(jobs, expect=expect, owner_tags=tags, tick_name=tick_name)["ok"]


# ---------------------------------------------------------------------------
# Live inventory fetch (opt-in only)
# ---------------------------------------------------------------------------
def fetch_live_inventory(cmd=DEFAULT_CRON_LIST_CMD, timeout=30):
    """Run `openclaw cron list --json` (or an override) and parse its JSON. Raises
    InventoryUnavailable if the command is missing, times out, exits nonzero, or emits
    unparseable output. Never runs unless the caller explicitly asked for --live."""
    argv = shlex.split(cmd)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise InventoryUnavailable("cron-list command not found: %s" % argv[0])
    except subprocess.TimeoutExpired:
        raise InventoryUnavailable("cron-list command timed out after %ss" % timeout)
    if proc.returncode != 0:
        raise InventoryUnavailable("cron-list command exited %d" % proc.returncode)
    out = (proc.stdout or "").strip()
    if not out:
        raise InventoryUnavailable("cron-list command produced no output")
    try:
        return json.loads(out)
    except ValueError as exc:
        raise InventoryUnavailable("cron-list output is not valid JSON: %s" % exc)


# ---------------------------------------------------------------------------
# Self-test: force-observe every exit-code path and every violation class.
# ---------------------------------------------------------------------------
def _job(name, expr, kind="cron", enabled=True, jid=None, message="anthology daily tick"):
    return {
        "id": jid or ("id-" + re.sub(r"\W+", "-", name)),
        "name": name,
        "description": "",
        "enabled": enabled,
        "schedule": {"kind": kind, "expr": expr, "tz": "America/New_York"},
        "payload": {"kind": "agentTurn", "message": message},
        "delivery": {"mode": "silent", "channel": "REDACTED"},
    }


def self_test():
    import tempfile
    import os

    print("[guard-cron-inventory] self-test: exercising cadence, ownership, and both expectations")

    # -- cadence classifier truth table -------------------------------------------------
    assert classify_cadence({"kind": "cron", "expr": "0 9 * * *"}) == "daily"
    assert classify_cadence({"kind": "cron", "expr": "30 6 * * *"}) == "daily"
    assert classify_cadence({"kind": "cron", "expr": "@daily"}) == "daily"
    assert classify_cadence({"kind": "cron", "expr": "*/5 * * * *"}) == "sub-daily"
    assert classify_cadence({"kind": "cron", "expr": "0 6-21 * * *"}) == "sub-daily", \
        "the real fleet-heartbeat cadence must read as sub-daily"
    assert classify_cadence({"kind": "cron", "expr": "0 9,17 * * *"}) == "sub-daily"
    assert classify_cadence({"kind": "cron", "expr": "@hourly"}) == "sub-daily"
    assert classify_cadence({"kind": "cron", "expr": "0 9 * * 1"}) == "supra-daily"
    assert classify_cadence({"kind": "cron", "expr": "@weekly"}) == "supra-daily"
    assert classify_cadence({"kind": "interval", "expr": "3600"}) == "sub-daily"
    assert classify_cadence({"kind": "interval", "expr": "86400"}) == "daily"
    assert classify_cadence({"kind": "interval", "expr": "30m"}) == "sub-daily"
    assert classify_cadence({"kind": "once", "expr": "2026-07-07T09:00"}) == "non-recurring"
    assert classify_cadence({"kind": "cron", "expr": "@reboot"}) == "non-recurring"
    assert classify_cadence({"kind": "cron", "expr": "garbage garbage"}) == "unknown"
    print("[guard-cron-inventory] cadence classifier: PASS (14 cases incl. the fleet-heartbeat shape)")

    tick = _job("anthology-daily-tick", "0 9 * * *")
    foreign_hb = _job("fleet-heartbeat", "0 6-21 * * *", message="per-client status summary")
    foreign_hb["payload"]["message"] = "per-client status summary"  # no 'anthology' token -> foreign

    # 1. PASS steady state: one daily engine tick + an UNRELATED heartbeat that must be ignored.
    r = analyze([tick, foreign_hb], expect="one")
    assert r["ok"], "clean steady state wrongly flagged: %r" % r["violations"]
    assert r["foreign_jobs_ignored"] == 1 and r["engine_recurring"] == 1
    assert evaluate([tick, foreign_hb], expect="one") is True
    print("[guard-cron-inventory] PASS steady-state (one tick, foreign heartbeat ignored): PASS")

    # 2. VIOLATION two ticks.
    r = analyze([tick, _job("anthology-extra-tick", "0 10 * * *")], expect="one")
    assert not r["ok"] and any(v["code"] == "CRON-COUNT" for v in r["violations"])
    print("[guard-cron-inventory] DETECT two recurring engine jobs (CRON-COUNT): PASS")

    # 3. VIOLATION engine heartbeat by name (even alongside a valid tick).
    r = analyze([tick, _job("anthology-heartbeat", "0 8 * * *")], expect="one")
    assert not r["ok"] and any(v["code"] == "CRON-HEARTBEAT" for v in r["violations"])
    print("[guard-cron-inventory] DETECT engine heartbeat by name (CRON-HEARTBEAT): PASS")

    # 4. VIOLATION the tick itself is sub-daily (a disguised heartbeat).
    r = analyze([_job("anthology-daily-tick", "*/5 * * * *")], expect="one")
    assert not r["ok"] and any(v["code"] == "CRON-SUBDAILY" for v in r["violations"])
    print("[guard-cron-inventory] DETECT sub-daily tick (CRON-SUBDAILY): PASS")

    # 5. VIOLATION the tick is supra-daily (weekly) -- present but not a DAILY tick.
    r = analyze([_job("anthology-daily-tick", "0 9 * * 1")], expect="one")
    assert not r["ok"] and any(v["code"] == "CRON-NOT-DAILY" for v in r["violations"])
    print("[guard-cron-inventory] DETECT non-daily tick (CRON-NOT-DAILY): PASS")

    # 6. VIOLATION expect one but zero registered (provision failed to install the tick).
    r = analyze([foreign_hb], expect="one")
    assert not r["ok"] and any(v["code"] == "CRON-COUNT" for v in r["violations"])
    print("[guard-cron-inventory] DETECT missing tick (CRON-COUNT, found 0): PASS")

    # 7. PASS churn clean: post-revoke, zero engine recurring jobs (foreign jobs still fine).
    r = analyze([foreign_hb], expect="zero")
    assert r["ok"], "clean post-revoke wrongly flagged: %r" % r["violations"]
    assert evaluate([foreign_hb], expect="zero") is True
    print("[guard-cron-inventory] PASS churn-clean (zero engine recurring): PASS")

    # 8. VIOLATION churn leftover: a paused (disabled) engine tick still counts as recurring.
    r = analyze([_job("anthology-daily-tick", "0 9 * * *", enabled=False)], expect="zero")
    assert not r["ok"] and any(v["code"] == "CRON-CHURN-LEFTOVER" for v in r["violations"]), \
        "a lingering disabled recurring engine job must fail the churn assertion: %r" % r
    print("[guard-cron-inventory] DETECT churn leftover incl. paused job (CRON-CHURN-LEFTOVER): PASS")

    # 9. VIOLATION pinned tick-name mismatch.
    r = analyze([_job("anthology-wrong-name", "0 9 * * *")], expect="one",
                tick_name="anthology-daily-tick")
    assert not r["ok"] and any(v["code"] == "CRON-TICK-NAME" for v in r["violations"])
    print("[guard-cron-inventory] DETECT tick-name mismatch (CRON-TICK-NAME): PASS")

    # 10. Malformed inventory raises ValueError (CLI -> exit 2).
    for bad in (42, "not-json-object", {"nope": 1}):
        try:
            extract_jobs(bad) if not isinstance(bad, str) else evaluate(bad + "-no-such-file.json")
            raise AssertionError("expected a raise on malformed inventory: %r" % (bad,))
        except (ValueError, InventoryUnavailable):
            pass
    print("[guard-cron-inventory] malformed-inventory raises (CLI exit 2/3): PASS")

    # -- force-observe the CLI exit-code mapping end to end -----------------------------
    with tempfile.TemporaryDirectory() as td:
        clean = os.path.join(td, "clean.json")
        dirty = os.path.join(td, "dirty.json")
        broken = os.path.join(td, "broken.json")
        Path(clean).write_text(json.dumps({"jobs": [tick, foreign_hb]}))
        Path(dirty).write_text(json.dumps({"jobs": [tick, _job("anthology-heartbeat", "0 8 * * *")]}))
        Path(broken).write_text("{ this is not json ")

        assert main(["--inventory", clean, "--expect", "one"]) == EX_OK, "clean file must exit 0"
        assert main(["--inventory", dirty, "--expect", "one"]) == EX_VIOLATION, "dirty file must exit 4"
        assert main(["--inventory", broken]) == EX_BAD, "malformed JSON must exit 2"
        assert main(["--inventory", os.path.join(td, "missing.json")]) == EX_BAD, \
            "missing explicit path must exit 2"
        assert main([]) == EX_BAD, "no source must exit 2"
        # exit 3: --live against a command that does not exist -> inventory unavailable.
        assert main(["--live", "--cron-list-cmd",
                     "this-cron-binary-does-not-exist --json"]) == EX_DEP, \
            "unavailable live inventory must exit 3"
    print("[guard-cron-inventory] CLI exit-code mapping (0/2/3/4): PASS")

    print("[guard-cron-inventory] self-test: PASS")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _render(report):
    lines = []
    head = "CLEAN" if report["ok"] else "VIOLATION"
    lines.append("[guard-cron-inventory] %s  expect=%s  engine_recurring=%d  "
                 "engine_jobs=%d  foreign_ignored=%d"
                 % (head, report["expect"], report["engine_recurring"],
                    report["engine_jobs"], report["foreign_jobs_ignored"]))
    for e in report["engine_recurring_detail"]:
        lines.append("    tick: %s  [%s %s]  cadence=%s  enabled=%s"
                     % (e["name"], e["kind"] or "cron", e["expr"], e["cadence"], e["enabled"]))
    for v in report["violations"]:
        lines.append("    !! %s: %s" % (v["code"], v["detail"]))
        job = v.get("job")
        if job:
            lines.append("       job: %s  [%s]  cadence=%s"
                         % (job["name"], job["expr"], job["cadence"]))
        for job in v.get("jobs", []):
            lines.append("       job: %s  [%s]  cadence=%s"
                         % (job["name"], job["expr"], job["cadence"]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Cron-inventory gate for the Anthology Engine (W2.5): exactly one "
                    "daily tick, no heartbeat, zero recurring jobs after churn.")
    src = ap.add_argument_group("inventory source (exactly one)")
    src.add_argument("--inventory", metavar="PATH",
                     help="JSON file: a gateway-cronlist envelope, a bare job list, or one job")
    src.add_argument("--stdin", action="store_true", help="read the inventory JSON from stdin")
    src.add_argument("--live", action="store_true",
                     help="fetch the inventory live via the cron-list command (opt-in)")
    ap.add_argument("--cron-list-cmd", default=DEFAULT_CRON_LIST_CMD,
                    help="command run for --live (default: %(default)r)")
    ap.add_argument("--expect", choices=("one", "zero"), default="one",
                    help="'one' steady-state/post-provision (default), 'zero' post-revoke/churn")
    ap.add_argument("--owner-tag", action="append", default=None,
                    help="token identifying an engine-owned job (repeatable; default 'anthology')")
    ap.add_argument("--tick-name", default=None,
                    help="pin the exact expected daily-tick job name (stricter identity check)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report to stdout")
    ap.add_argument("--self-test", action="store_true", help="run the built-in self-test and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test()

        owner_tags = tuple(args.owner_tag) if args.owner_tag else DEFAULT_OWNER_TAGS

        sources = [bool(args.inventory), bool(args.stdin), bool(args.live)]
        if sum(sources) == 0:
            sys.stderr.write("[guard-cron-inventory] bad invocation: one of --inventory / "
                             "--stdin / --live is required (or --self-test)\n")
            return EX_BAD
        if sum(sources) > 1:
            sys.stderr.write("[guard-cron-inventory] bad invocation: give exactly one "
                             "inventory source\n")
            return EX_BAD

        # Resolve the inventory object.
        if args.inventory:
            p = Path(args.inventory)
            if not p.exists() or not p.is_file():
                sys.stderr.write("[guard-cron-inventory] bad invocation: no such inventory "
                                 "file: %s\n" % args.inventory)
                return EX_BAD
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                sys.stderr.write("[guard-cron-inventory] bad invocation: inventory is not "
                                 "valid JSON: %s\n" % exc)
                return EX_BAD
        elif args.stdin:
            raw = sys.stdin.read()
            try:
                obj = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[guard-cron-inventory] bad invocation: stdin is not valid "
                                 "JSON: %s\n" % exc)
                return EX_BAD
        else:  # args.live
            try:
                obj = fetch_live_inventory(args.cron_list_cmd)
            except InventoryUnavailable as exc:
                sys.stderr.write("[guard-cron-inventory] inventory unavailable: %s\n" % exc)
                return EX_DEP

        try:
            jobs = extract_jobs(obj)
        except ValueError as exc:
            sys.stderr.write("[guard-cron-inventory] bad invocation: %s\n" % exc)
            return EX_BAD

        report = analyze(jobs, expect=args.expect, owner_tags=owner_tags,
                         tick_name=args.tick_name)

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(_render(report))

        return EX_OK if report["ok"] else EX_VIOLATION

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[guard-cron-inventory] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
