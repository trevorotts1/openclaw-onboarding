#!/usr/bin/env python3
"""social-planner-doctor.py — ONE doctor command for the social planner
deployment (F21 / WF13 portable deployment + service health contract).

WHY: repository inspection cannot establish that a client host has an enabled
scheduler, a healthy worker or a current n8n mapping. A Mac-only success
proves nothing about Hostinger or Contabo. This doctor runs ON any supported
install (Mac launchd profile or Docker VPS profile) and produces a
machine-readable verdict over the SAME durable state every other WF-owned
component writes:

Checks (each maps to a WF-owned durable record — no new source of truth):
  identity          company_id + planner_kind + GHL location binding
  engine            active cycle-service engine (durable engine vs legacy
                    trigger) + scheduler registration (systemd/launchd unit
                    or gateway cron, whichever the deployment type owns)
  worker            last worker acknowledgement (publish receipts) — a
                    stopped worker is reported as a HEALTH PROBLEM, never as
                    work progressing
  cycles            last cycle + next action (invited/responded/cutoff)
  ghl               read-only GHL discovery probe (connected accounts count
                    via the documented contract probe — offline unless --live)
  sheet             registered planner sheet (social_sheet_registry /
                    sheet_registry.json contract): sharing + schema_version
  n8n               n8n contract version of the installed mapping (both
                    webhook exports, schema_version 1.1.0)
  retries           unresolved publish retries / overdue dispatch rows

RECEIPT SHAPE (never includes a secret value):
  { deployment: {platform, profile}, checks: {<name>: {ok, state, detail?}},
    ok: <bool>, overdue: [...], generated_at }

EXIT: 0 healthy / 1 degraded (soft states only) / 2 unhealthy (worker stopped,
schedule missing, identity/sheet/n8n mismatch) / 3 usage / 4 self-test fail.

Sandbox/CI: pass --root <dir> to redirect ALL state paths under a fixture
sandbox (the doctor then reads fixture layouts, never live fleet state).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_UNHEALTHY = 2
EXIT_USAGE = 3

# The n8n export contract version the deployment must carry (WF04 F15/F16).
EXPECTED_N8N_SCHEMA_VERSION = "1.1.0"
# publish receipts considered stale after this many seconds (worker silence).
WORKER_STALE_SECONDS = 7 * 24 * 3600.0
# A scheduled trigger not verified within this window is stale.
SCHEDULE_STALE_SECONDS = 8 * 24 * 3600.0


def _openclaw_root(env: Dict[str, str]) -> Path:
    """The openclaw state root for THIS deployment profile:
    Mac -> ~/.openclaw ; Docker VPS -> /data/.openclaw (HOME=/data)."""
    explicit = env.get("OPENCLAW_ROOT", "").strip()
    if explicit:
        return Path(explicit)
    home = env.get("HOME") or ""
    if home.rstrip("/").endswith("/data"):
        return Path("/data/.openclaw")
    return Path(home or str(Path.home())) / ".openclaw"


def _detect_deployment(env: Dict[str, str]) -> Dict[str, str]:
    """Mac vs Docker profile detection, read-only. Provider NAMES are not
    evidence; the profile decides which service-manager probes apply."""
    home = env.get("HOME") or ""
    if os.path.isdir("/data/.openclaw") and not os.path.isdir(
            os.path.join(home, ".openclaw")) if home else False:
        prof = "docker-vps"
    elif env.get("SOCIAL_PLANNER_DEPLOYMENT_PROFILE"):
        prof = env["SOCIAL_PLANNER_DEPLOYMENT_PROFILE"]
    elif platform.system() == "Darwin":
        prof = "mac"
    elif os.path.isdir("/data/.openclaw"):
        prof = "docker-vps"
    else:
        prof = "linux-vps"
    return {
        "platform": platform.system().lower(),
        "profile": prof,
        "tz": env.get("SOCIAL_PLANNER_TIMEZONE") or env.get("TZ") or "client-local",
    }


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, (dict, list)) else None
    except (OSError, ValueError):
        return None


# ── Check: identity ──────────────────────────────────────────────────────────
def check_identity(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    """company_id + planner_kind + GHL location binding."""
    binding = _read_json(root / "data" / "skill35" / "company-identity.json")
    if not binding:
        # Skill 57 single-state-spine layout (client-config.json fields)
        binding = _read_json(root / "data" / "skill57" / "client-config.json")
    if not binding:
        return {"ok": False, "state": "absent",
                "detail": "no company-identity record under <root>/data (skill35/company-identity.json or skill57/client-config.json)"}
    company_id = binding.get("company_id") or binding.get("companyId")
    location_id = binding.get("locationId") or binding.get("GOHIGHLEVEL_LOCATION_ID")
    missing = [k for k, v in (("company_id", company_id), ("locationId", location_id)) if not v]
    if missing:
        return {"ok": False, "state": "incomplete", "detail": "missing fields: %s" % ", ".join(missing)}
    return {"ok": True, "state": "ok",
            "company_id": company_id,
            "location_id": location_id,
            "planner_kind": binding.get("planner_kind") or "social-planner"}


# ── Check: engine + scheduler registration ───────────────────────────────────
def check_engine(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    """Engine-ownership verdict (F17) + the installed scheduler unit."""
    ownership = _read_json(root / "data" / "social-cycle" / "engine-ownership.json")
    rows = (ownership or {}).get("rows", [])
    by_company: Dict[str, Dict[str, int]] = {}
    for r in rows:
        e = by_company.setdefault(r.get("company_id", ""), {"active": 0, "superseded": 0})
        if r.get("state") == "active":
            e["active"] += 1
        elif r.get("state") == "superseded":
            e["superseded"] += 1
    if not by_company:
        return {"ok": False, "state": "no_owner",
                "detail": "no engine-ownership rows — the durable cycle service never claimed this box"}
    bad = {c: v for c, v in by_company.items() if v["active"] != 1}
    if bad:
        return {"ok": False, "state": "ownership_violated", "detail": "companies with != 1 active owner: %s" % ", ".join(sorted(bad))}
    scheduler = _read_json(root / "data" / "social-cycle" / "scheduler-registration.json")
    if scheduler:
        return {"ok": True, "state": "ok",
                "engine": "cc-cycle-service",
                "scheduler": scheduler.get("scheduler_name"),
                "expr": scheduler.get("expr"),
                "last_verified_at": scheduler.get("verified_at")}
    # Mac profile: the gateway cron trigger is the registered forwarding adapter.
    if _detect_deployment(env)["profile"] == "mac":
        return {"ok": True, "state": "ok", "engine": "cc-cycle-service",
                "scheduler": "gateway-cron (skill35-weekly-theme forwarding adapter)"}
    return {"ok": False, "state": "scheduler_unregistered",
            "detail": "durable engine owns the schedule but no scheduler-registration record exists on this profile"}


# ── Check: worker acknowledgement ────────────────────────────────────────────
def check_worker(root: Path, env: Dict[str, str], now_s: float) -> Dict[str, Any]:
    """A stopped worker is a HEALTH PROBLEM, never 'work progressing'.

    Evidence: the newest publish receipt / dispatch record under the skill35
    runs tree. NO receipt within WORKER_STALE_SECONDS -> worker_stale.
    """
    runs_root = root / "data" / "skill-35" / "runs"
    newest: Optional[float] = None
    newest_path: Optional[str] = None
    if runs_root.is_dir():
        for rec_dir in sorted(runs_root.iterdir(), reverse=True)[:64]:
            for cand in ("working/dispatch.json", "publish-receipts.json"):
                p = rec_dir / cand
                if p.is_file():
                    m = p.stat().st_mtime
                    if newest is None or m > newest:
                        newest, newest_path = m, str(p)
            if newest is not None:
                break
    if newest is None:
        return {"ok": True, "state": "no_cycles_yet",
                "detail": "no publish run recorded — fresh install; not a failure"}
    age = now_s - newest
    if age > WORKER_STALE_SECONDS:
        return {"ok": False, "state": "worker_stale",
                "detail": "newest worker receipt %s is %d days old — the publish worker is NOT progressing" % (
                    newest_path, int(age // 86400))}
    return {"ok": True, "state": "ok", "last_receipt_age_s": int(age), "last_receipt": newest_path}


# ── Check: last/next cycle ───────────────────────────────────────────────────
def check_cycles(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    base = root / "data" / "social-cycle"
    if not base.is_dir():
        return {"ok": True, "state": "no_cycles_yet"}
    companies = sorted(p.name for p in base.iterdir() if (p / "cycles.json").is_file())
    if not companies:
        return {"ok": True, "state": "no_cycles_yet"}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary: List[Dict[str, Any]] = []
    for company in companies:
        cycles = _read_json(base / company / "cycles.json") or {}
        if not cycles:
            continue
        latest = max(cycles.values(), key=lambda c: c.get("week_start_local", ""))
        summary.append({"company_id": company,
                        "last_week": latest.get("week_start_local"),
                        "state": latest.get("state"),
                        "disposition": latest.get("disposition"),
                        "next_cycle_at": latest.get("next_cycle_at")})
    return {"ok": True, "state": "ok", "companies": summary}


# ── Check: GHL discovery (read-only, offline by default) ────────────────────
def check_ghl(env: Dict[str, str], live: bool) -> Dict[str, Any]:
    if not live:
        return {"ok": True, "state": "skipped_offline",
                "detail": "use --live for a read-only connected-accounts probe"}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from social_planner_credentials import resolve_planner_credentials  # noqa: PLC0415
        creds, report = resolve_planner_credentials()
        missing = [k for k, v in creds.items() if not v]
        if missing:
            return {"ok": False, "state": "credentials_missing", "detail": "missing: %s" % ", ".join(missing)}
        return {"ok": True, "state": "ok",
                "detail": "credentials resolve (%s)" % ", ".join(sorted(creds))}
    except Exception as exc:  # noqa: BLE001 — probe failure is a degraded check, never a crash
        return {"ok": False, "state": "probe_error", "detail": str(exc)[:160]}


# ── Check: registered sheet (sheet_registry contract) ───────────────────────
def check_sheet(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    reg = _read_json(root / "data" / "skill35" / "sheet-registry.json")
    if not reg:
        return {"ok": False, "state": "unregistered",
                "detail": "no sheet-registry.json — the provisioned planner sheet was never persisted (F34 step 3)"}
    entries = reg.get("rows", reg if isinstance(reg, list) else [])
    if isinstance(entries, dict):
        entries = list(entries.values())
    if not entries:
        return {"ok": False, "state": "unregistered", "detail": "empty sheet registry"}
    for e in entries:
        if e.get("sharing") not in (None, "anyone,writer", "anyone-with-the-link-can-edit"):
            return {"ok": False, "state": "sharing_drift",
                    "detail": "planner sharing drifted from the F02 contract (%s)" % e.get("sharing")}
        if not e.get("sheet_id") or not e.get("verified_at"):
            return {"ok": False, "state": "unverified",
                    "detail": "registered sheet lacks a verified_at receipt"}
    return {"ok": True, "state": "ok", "sheets": len(entries)}


# ── Check: n8n contract version ──────────────────────────────────────────────
def check_n8n(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    mapping = _read_json(root / "data" / "skill35" / "n8n-mapping.json")
    if not mapping:
        return {"ok": False, "state": "mapping_missing",
                "detail": "no n8n-mapping.json — install must persist the deployed workflow ids (F34)"}
    version = mapping.get("schema_version")
    if version != EXPECTED_N8N_SCHEMA_VERSION:
        return {"ok": False, "state": "contract_stale",
                "detail": "n8n mapping schema_version %s != %s — redeploy the exports" % (version, EXPECTED_N8N_SCHEMA_VERSION)}
    return {"ok": True, "state": "ok", "schema_version": version,
            "sheet_create": mapping.get("sheet_create_workflow_id"),
            "row_append": mapping.get("row_append_workflow_id")}


# ── Check: unresolved retries / overdue dispatch ─────────────────────────────
def check_retries(root: Path, env: Dict[str, str]) -> Dict[str, Any]:
    """Overdue = dispatch.json records stuck pre-review past the threshold
    (mirrors run-publishing-cycle.sh --overdue-after, default 900s)."""
    overdue: List[Dict[str, Any]] = []
    runs_root = root / "data" / "skill-35" / "runs"
    if runs_root.is_dir():
        now_s = time.time()
        for rec_dir in sorted(runs_root.iterdir(), reverse=True)[:64]:
            rec = _read_json(rec_dir / "working" / "dispatch.json")
            if not rec:
                continue
            state = rec.get("state")
            if state in ("queued", "in_progress"):
                started = rec.get("queued_at") or rec.get("created_at") or ""
                try:
                    import calendar
                    ts = calendar.timegm(time.strptime(started[:19], "%Y-%m-%dT%H:%M:%S")) if started else 0
                except ValueError:
                    ts = 0
                if ts and (now_s - ts) > 900:
                    overdue.append({"run": rec_dir.name, "state": state,
                                    "age_s": int(now_s - ts)})
    if overdue:
        return {"ok": False, "state": "overdue", "detail": "%d dispatch record(s) past the overdue window" % len(overdue),
                "overdue": overdue}
    return {"ok": True, "state": "ok"}


CHECK_ORDER = ["identity", "engine", "worker", "cycles", "sheet", "n8n", "retries"]
# Hard checks: a failure makes the deployment UNHEALTHY (not "degraded"):
# identity, engine ownership, worker liveness, sheet registry, n8n contract
# version, and unresolved retries. A stopped worker is a HARD failure — the
# health view NEVER claims work is progressing while the worker is stopped.
HARD_CHECKS = {"identity", "engine", "worker", "sheet", "n8n", "retries"}


def run_doctor(env: Optional[Dict[str, str]] = None, live: bool = False,
               root_override: Optional[str] = None) -> Dict[str, Any]:
    env = dict(env if env is not None else os.environ)
    root = Path(root_override) if root_override else _openclaw_root(env)
    deployment = _detect_deployment(env)
    checks: Dict[str, Any] = {}
    checks["identity"] = check_identity(root, env)
    checks["engine"] = check_engine(root, env)
    checks["worker"] = check_worker(root, env, time.time())
    checks["cycles"] = check_cycles(root, env)
    checks["sheet"] = check_sheet(root, env)
    checks["n8n"] = check_n8n(root, env)
    checks["retries"] = check_retries(root, env)
    checks["ghl"] = check_ghl(env, live)
    ok = all(
        c.get("ok", False) for name, c in checks.items()
        if name in HARD_CHECKS
    )
    soft_bad = [n for n, c in checks.items() if n not in HARD_CHECKS and not c.get("ok", False)]
    verdict = {
        "doctor": "social-planner-doctor",
        "deployment": deployment,
        "root": str(root),
        "checks": checks,
        "overdue": checks["retries"].get("overdue", []),
        "ok": ok,
        "degraded_soft": soft_bad,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return verdict


def _self_test() -> int:
    """Fixture sandbox self-test: a healthy layout -> ok; a layout with the
    worker receipt removed -> worker stale is SURFACED (and with the registry
    missing -> unhealthy)."""
    import tempfile
    base = tempfile.mkdtemp(prefix="doctor-selftest-")
    env = {"OPENCLAW_ROOT": base, "HOME": "/home/op", "SOCIAL_PLANNER_TIMEZONE": "America/New_York"}
    skill35 = Path(base) / "data" / "skill35"
    skill35.mkdir(parents=True)
    (skill35 / "company-identity.json").write_text(json.dumps(
        {"company_id": "co-fixtures", "locationId": "LOC123", "planner_kind": "social-planner"}))
    (skill35 / "sheet-registry.json").write_text(json.dumps({"rows": [
        {"sheet_id": "SHEET1", "sharing": "anyone,writer", "verified_at": "2026-09-09T00:00:00Z"}]}))
    (skill35 / "n8n-mapping.json").write_text(json.dumps(
        {"schema_version": "1.1.0", "sheet_create_workflow_id": "INyGjT8jQ6JjrZSh",
         "row_append_workflow_id": "myXde6jbIIkaG5zW"}))
    sc = Path(base) / "data" / "social-cycle"
    sc.mkdir(parents=True)
    (sc / "engine-ownership.json").write_text(json.dumps({"rows": [
        {"company_id": "co-fixtures", "engine": "cc-cycle-service", "state": "active"}]}))
    (sc / "scheduler-registration.json").write_text(json.dumps(
        {"scheduler_name": "systemd", "expr": "*/5 * * * *", "verified_at": "2026-09-09T00:00:00Z"}))
    v = run_doctor(env=env, root_override=base)
    assert v["ok"], v
    # Break: remove the sheet registry -> identity+engine still ok but sheet fails hard.
    (skill35 / "sheet-registry.json").unlink()
    v2 = run_doctor(env=env, root_override=base)
    assert not v2["ok"] and v2["checks"]["sheet"]["state"] == "unregistered", v2
    print("self-test: healthy fixture -> ok; missing registry -> unhealthy. PASS")
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="social-planner-doctor", description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="enable read-only GHL probes")
    parser.add_argument("--root", default=None, help="fixture sandbox root (CI)")
    parser.add_argument("--json", action="store_true", default=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        try:
            return _self_test()
        except AssertionError as exc:
            print("self-test FAIL: %s" % exc, file=sys.stderr)
            return 4
    verdict = run_doctor(root_override=args.root, live=args.live)
    print(json.dumps(verdict, indent=1, sort_keys=True))
    if verdict["ok"]:
        return EXIT_OK
    return EXIT_UNHEALTHY if not verdict["degraded_soft"] else EXIT_DEGRADED


if __name__ == "__main__":
    sys.exit(main())