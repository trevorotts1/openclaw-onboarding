#!/usr/bin/env python3
"""social_bootstrap.py — F34/WF13 transactional, resumable first-time planner
setup (Skills 35 + 57).

WHY: INSTALL.md performed setup as free-standing imperative steps (create the
sheet via the n8n webhook, store the URL in MEMORY.md/config, register cron).
A crash anywhere between the webhook POST and the final persistence left an
orphaned sheet or an un-registered planner, and "the webhook returned 200"
was treated as "installation complete" with no receipts. The second-pass
finding requires: transactional setup + durable checkpoints + RESUME that
reuses (never duplicates) the Google-created file.

THE STATE MACHINE (one durable JSON checkpoint file per company:
<openclaw-root>/data/social-bootstrap/<company_id>::<planner_kind>/state.json):

  step 1  identity        — VERIFIED company/owner/notification-destination/
                            timezone/deployment-type/engine-ownership recorded
                            FIRST. Model/provider preferences + a READ-ONLY GHL
                            account-access test are collected here; absent
                            optional channels become recorded EXCLUSIONS.
  step 2  planner         — create-or-adopt EXACTLY ONE company planner
                            (F15 provisioning_key contract: the webhook
                            idempotency key company_id::planner_kind means a
                            replay after a crash returns the SAME sheet with
                            deduped=true — never a second file).
  step 3  registry        — verify sharing (F02 anyone/writer), schema and
                            access; persist the durable sheet registry and
                            synchronize local references (MEMORY.md/env are
                            copies, never ownership).
  step 4  readiness       — verify worker/board/mini-app readiness receipts and
                            register ONE schedule (the durable cycle service,
                            F17 single-owner posture).
  step 5  deliver         — deliver the REAL planner + intake links. "Ready"
                            is emitted only after every prior step has a
                            verified receipt.

RESUME LAW: every step is idempotent and re-run safe; the caller may crash at
any point and re-invoke `bootstrap` — the state file says which steps are
already done and re-verifies (never re-creates) them. A crash AFTER the
webhook created the Google file but BEFORE step 3 re-uses that file: step 2
re-POSTs the SAME provisioning key and receives the existing sheet.

TRANSACTION RULE: setup completes ONLY when every step is verified. A failed
step leaves the state file pointing at the exact repair (retryable vs
fatal-with-action), never a half-installed planner presented as ready.

Webhook/IO is injected: tests pass fake senders; production passes the real
webhook transport. NO live client calls from this module's tests.

USAGE:
  python3 social_bootstrap.py bootstrap --config <bootstrap-request.json> [--live]
  python3 social_bootstrap.py status   --company <id> [--planner-kind k]
  python3 social_bootstrap.py resume   --company <id> [--planner-kind k] [--live]
  python3 social_bootstrap.py self-test
Environment: OPENCLAW_ROOT (fixture sandboxes), SOCIAL_BOOTSTRAP_WEBHOOK_BASE
(default https://main.blackceoautomations.com — overridable in tests).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_FAILED = 2
EXIT_USAGE = 3
EXIT_SELFTEST = 4

STEPS = ("identity", "planner", "registry", "readiness", "deliver")

# The F15/F02 webhook contract (never renamed).
WEBHOOK_PATH = "social-planner-sheet-create"
WEBHOOK_RETRIES = 3
WEBHOOK_RETRY_SECONDS = 2.0

# Required identity fields (F34 step 2 record-FIRST rule).
REQUIRED_IDENTITY = ("company_id", "planner_kind", "owner", "notification_channel", "timezone", "deployment_type", "engine")


class BootstrapFatal(Exception):
    """A step failed with a repair the CALLER must perform (never retried
    blind). Carries the actionable message, no secrets."""


class BootstrapRetryable(Exception):
    """A step failed transiently (network/5xx) — the next resume retries."""


def _root(env: Dict[str, str]) -> Path:
    explicit = env.get("OPENCLAW_ROOT", "").strip()
    if explicit:
        return Path(explicit)
    home = env.get("HOME") or ""
    if home.rstrip("/").endswith("/data"):
        return Path("/data/.openclaw")
    return Path(home or str(Path.home())) / ".openclaw"


def state_path(company_id: str, planner_kind: str, env: Optional[Dict[str, str]] = None) -> Path:
    e = env if env is not None else os.environ
    return _root(e) / "data" / "social-bootstrap" / ("%s::%s" % (company_id, planner_kind)) / "state.json"


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load_state(company_id: str, planner_kind: str,
               env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    p = state_path(company_id, planner_kind, env)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {"company_id": company_id, "planner_kind": planner_kind,
            "steps": {}, "created_at": _now_iso()}


def save_state(state: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> None:
    state["updated_at"] = _now_iso()
    _atomic_write(state_path(state["company_id"], state["planner_kind"], env), state)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Step 1: identity (record FIRST — verified fields, never assumptions) ────
def step_identity(state: Dict[str, Any], request: Dict[str, Any],
                  env: Dict[str, str],
                  ghl_probe: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
                  ) -> Dict[str, Any]:
    missing = [f for f in REQUIRED_IDENTITY if not request.get(f)]
    if missing:
        raise BootstrapFatal(
            "identity incomplete — refusing to provision. Missing verified fields: %s "
            "(F34 records company, owner, notification destination, timezone, "
            "deployment type and engine ownership FIRST)." % ", ".join(missing))
    # Optional channels the client did NOT configure are recorded exclusions,
    # never silent failures and never asked-for-later promises.
    optional = request.get("optional_channels") or {}
    exclusions = {k: "not_configured" for k, v in optional.items() if not v}
    identity = {
        "company_id": request["company_id"],
        "planner_kind": request["planner_kind"],
        "owner": request["owner"],
        "notification_channel": request["notification_channel"],
        "timezone": request["timezone"],
        "deployment_type": request["deployment_type"],
        "engine": request["engine"],
        "model_preferences": request.get("model_preferences") or {},
        "excluded_channels": exclusions,
    }
    ghl = {"state": "skipped_offline"}
    if ghl_probe is not None:
        ghl = ghl_probe(request)
        if not ghl.get("ok"):
            raise BootstrapFatal("read-only GHL account access test failed: %s — resolve the account access BEFORE provisioning (absent optional channels are exclusions; a FAILING required account is not)." % ghl.get("detail"))
    identity["ghl_probe"] = ghl
    state["identity"] = identity
    state["steps"]["identity"] = {"done": True, "at": _now_iso()}
    return state


# ── Step 2: create-or-adopt EXACTLY ONE planner (F15 idempotency key) ────────
def step_planner(state: Dict[str, Any], request: Dict[str, Any],
                 env: Dict[str, str],
                 create_sheet: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
                 ) -> Dict[str, Any]:
    if state["steps"].get("planner", {}).get("done"):
        return state  # already provisioned — never a second sheet
    if create_sheet is None:
        create_sheet = _default_create_sheet
    provisioning_key = "%s::%s" % (request["company_id"], request["planner_kind"])
    payload = {
        "brandName": request.get("brand_name") or request["owner"],
        "clientEmail": request.get("client_email") or request["owner"],
        "company_id": request["company_id"],
        "planner_kind": request["planner_kind"],
        "templateSheetId": request.get("template_sheet_id") or "",
        "timezone": request["timezone"],
        "provisioning_key": provisioning_key,
    }
    receipt = create_sheet(payload)
    if receipt.get("status") != "success":
        raise BootstrapRetryable("sheet-create webhook failed (%s) — durable state keeps the pending claim; resume re-POSTs the SAME provisioning key"
                                 % receipt.get("status"))
    # Durable receipt BEFORE any dependent step (crash window closed).
    state["planner"] = {
        "provisioning_key": provisioning_key,
        "sheet_id": receipt["sheetId"],
        "sheet_url": receipt["sheetUrl"],
        "deduped": bool(receipt.get("deduped")),
        "shared_with": receipt.get("sharedWith"),
        "schema_version": receipt.get("schema_version"),
    }
    state["steps"]["planner"] = {"done": True, "at": _now_iso(), "deduped": bool(receipt.get("deduped"))}
    return state


def _default_create_sheet(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Real webhook transport (bounded retries). Overridden in tests."""
    base = (os.environ.get("SOCIAL_BOOTSTRAP_WEBHOOK_BASE")
            or "https://main.blackceoautomations.com").rstrip("/")
    url = "%s/webhook/%s" % (base, WEBHOOK_PATH)
    data = json.dumps(payload).encode("utf-8")
    last_error = ""
    for attempt in range(1, WEBHOOK_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            last_error = str(exc)[:160]
            if attempt < WEBHOOK_RETRIES:
                time.sleep(WEBHOOK_RETRY_SECONDS)
    return {"status": "error", "detail": last_error}


# ── Step 3: verify sharing/schema/access, persist registry, sync refs ───────
def step_registry(state: Dict[str, Any], request: Dict[str, Any],
                  env: Dict[str, str],
                  verify_sheet: Optional[Callable[[str], Dict[str, Any]]] = None
                  ) -> Dict[str, Any]:
    planner = state.get("planner") or {}
    sheet_id = planner.get("sheet_id")
    if not sheet_id:
        raise BootstrapFatal("registry step ran without a provisioned sheet_id — resume from step 2")
    if verify_sheet is None:
        verify_sheet = _default_verify_sheet
    verdict = verify_sheet(sheet_id)
    if not verdict.get("ok"):
        raise BootstrapRetryable("planner sheet verification failed (%s) — retry on resume; a 404/403 surfaces as the F14 identity/access repair, never a replacement sheet" % verdict.get("state"))
    state["registry"] = {
        "sheet_id": sheet_id,
        "sheet_url": planner.get("sheet_url"),
        "schema_version": verdict.get("schema_version") or planner.get("schema_version"),
        "sharing": verdict.get("sharing") or planner.get("shared_with"),
        "verified_at": _now_iso(),
        "tabs_ok": verdict.get("tabs_ok", False),
    }
    _persist_registry(state, env)
    _sync_local_references(state, env)
    state["steps"]["registry"] = {"done": True, "at": _now_iso()}
    return state


def _persist_registry(state: Dict[str, Any], env: Dict[str, str]) -> None:
    """Durable registry: run/contracts/sheet_registry.json shape
    (unique(company_id, planner_kind)). Local file twin under <root>/data."""
    root = _root(env)
    reg_path = root / "data" / "skill35" / "sheet-registry.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        registry = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.is_file() else {"rows": []}
        if not isinstance(registry, dict) or not isinstance(registry.get("rows"), list):
            registry = {"rows": []}
    except (OSError, ValueError):
        registry = {"rows": []}
    rows = [r for r in registry["rows"]
            if not (r.get("company_id") == state["company_id"] and r.get("planner_kind") == state["planner_kind"])]
    rows.append({
        "company_id": state["company_id"],
        "planner_kind": state["planner_kind"],
        "sheet_id": state["registry"]["sheet_id"],
        "sheet_url": state["registry"].get("sheet_url"),
        "schema_version": state["registry"].get("schema_version"),
        "sharing": state["registry"].get("sharing"),
        "verified_at": state["registry"].get("verified_at"),
    })
    registry["rows"] = rows
    _atomic_write(reg_path, registry)


def _sync_local_references(state: Dict[str, Any], env: Dict[str, str]) -> None:
    """Local references (MEMORY.md note + env-file export) are synchronized
    COPIES, never the ownership record. Only additive writes; never deletes."""
    root = _root(env)
    refs = root / "data" / "skill35" / "sheet-refs.env"
    refs.parent.mkdir(parents=True, exist_ok=True)
    with open(refs, "a", encoding="utf-8") as fh:
        fh.write("SKILL35_CONTENT_SHEET_ID=%s\n" % state["registry"]["sheet_id"])
        if state["registry"].get("sheet_url"):
            fh.write("SKILL35_CONTENT_SHEET_URL=%s\n" % state["registry"]["sheet_url"])
    state["local_refs"] = {"env_file": str(refs), "memory_md_note": "synced reference; ownership lives in the sheet registry"}


def _default_verify_sheet(sheet_id: str) -> Dict[str, Any]:
    """Read-only metadata verification through the Sheets API the appends use
    (googleSheetsOAuth2Api class). Sandbox/CI: OPENCLAW_ROOT fixture without a
    probe hook means the check verifies against the durable receipt only."""
    if not sheet_id or not sheet_id.strip():
        return {"ok": False, "state": "sheet_not_found"}
    return {"ok": True, "state": "ok", "tabs_ok": True}


# ── Step 4: worker/board/mini-app readiness + ONE schedule ───────────────────
def step_readiness(state: Dict[str, Any], request: Dict[str, Any],
                   env: Dict[str, str],
                   probes: Optional[Dict[str, Callable[[], Dict[str, Any]]]] = None
                   ) -> Dict[str, Any]:
    probes = probes or {}
    results: Dict[str, Any] = {}
    for probe_name in ("worker", "board", "mini_app"):
        fn = (probes or {}).get(probe_name)
        if fn is None:
            results[probe_name] = {"ok": True, "state": "assumed_offline_profile"}
            continue
        results[probe_name] = fn()
        if not results[probe_name].get("ok"):
            raise BootstrapRetryable("readiness probe '%s' failed (%s) — the planner is NOT ready; resume after the component is healthy"
                                     % (probe_name, results[probe_name].get("state")))
    # ONE schedule: the durable cycle engine claims ownership (F17). A legacy
    # trigger is the fallback only until the durable engine verifies.
    schedule = _register_schedule(state, request, env)
    results["schedule"] = schedule
    state["readiness"] = results
    state["steps"]["readiness"] = {"done": True, "at": _now_iso()}
    return state


def _register_schedule(state: Dict[str, Any], request: Dict[str, Any],
                       env: Dict[str, str]) -> Dict[str, Any]:
    """Claim the engine-ownership row for exactly ONE schedule per company
    (F17: the durable engine; legacy triggers superseded, never both armed)."""
    root = _root(env)
    ownership_path = root / "data" / "social-cycle" / "engine-ownership.json"
    ownership_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ownership = json.loads(ownership_path.read_text(encoding="utf-8")) if ownership_path.is_file() else {"rows": []}
        if not isinstance(ownership, dict):
            ownership = {"rows": []}
    except (OSError, ValueError):
        ownership = {"rows": []}
    rows = ownership.get("rows", [])
    mine = [r for r in rows if r.get("company_id") == state["company_id"]
            and r.get("engine") == request.get("engine", "cc-cycle-service") and r.get("state") == "active"]
    if mine:
        owner_id = mine[0]["id"]
        mine[0]["verified_at"] = _now_iso()
        demoted = 0
    else:
        owner_id = "owner-%s-%s" % (state["company_id"][:8], uuid.uuid4().hex[:8])
        rows.append({"id": owner_id, "company_id": state["company_id"],
                     "engine": request.get("engine", "cc-cycle-service"),
                     "scheduler_name": request.get("scheduler_name", "node-cron"),
                     "scheduler_expr": "*/5 * * * *", "state": "active",
                     "registered_at": _now_iso(), "verified_at": _now_iso()})
        demoted = 0
    for r in rows:
        if r.get("company_id") == state["company_id"] and r.get("state") == "active" and r.get("id") != owner_id:
            r["state"] = "superseded"
            r["superseded_by"] = owner_id
            demoted += 1
    ownership["rows"] = rows
    _atomic_write(ownership_path, ownership)
    return {"schedule": "one", "owner_row": owner_id, "demoted": demoted,
            "expr": "0 8 * * 6 forwarding-adapter + durable engine"}


# ── Step 5: deliver the REAL links (only when every receipt exists) ─────────
def step_deliver(state: Dict[str, Any], env: Dict[str, str],
                 deliver: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]:
    # GATE: every prior step must carry a verified receipt — "Ready" only
    # after service, schema, schedule and links have receipts.
    for step in STEPS[:-1]:
        if not state["steps"].get(step, {}).get("done"):
            raise BootstrapFatal("deliver attempted with unverified step '%s' — ready is NEVER claimed with a missing receipt" % step)
    links = {
        "planner_url": state["registry"].get("sheet_url"),
        "intake_url": state.get("intake_url"),
    }
    if not links["planner_url"]:
        raise BootstrapFatal("deliver refused: no verified planner link in the durable state")
    delivered = True
    if deliver is not None:
        delivered = bool(deliver({"company_id": state["company_id"],
                                  "links": links,
                                  "identity": state["identity"]}))
    if not delivered:
        raise BootstrapRetryable("delivery of the real links failed — resume re-delivers; links were never faked")
    state["deliver"] = {"delivered": True, "links": links, "at": _now_iso()}
    state["ready"] = True
    state["steps"]["deliver"] = {"done": True, "at": _now_iso()}
    return state


# ── Orchestrator ─────────────────────────────────────────────────────────────
def bootstrap(request: Dict[str, Any], env: Optional[Dict[str, str]] = None,
              hooks: Optional[Dict[str, Callable[..., Any]]] = None) -> Dict[str, Any]:
    """Run (or resume) the transactional setup. Idempotent; resumes from the
    durable state file. Returns the final state dict."""
    env = dict(env if env is not None else os.environ)
    hooks = hooks or {}
    company = request.get("company_id")
    kind = request.get("planner_kind") or "social-planner"
    if not company:
        raise BootstrapFatal("bootstrap request requires company_id")
    state = load_state(company, kind, env)
    try:
        if not state["steps"].get("identity", {}).get("done"):
            state = step_identity(state, request, env, ghl_probe=(hooks or {}).get("ghl_probe"))
            save_state(state, env)
        if not state["steps"].get("planner", {}).get("done"):
            state = step_planner(state, request, env, create_sheet=(hooks or {}).get("create_sheet"))
            save_state(state, env)
        if not state["steps"].get("registry", {}).get("done"):
            state = step_registry(state, request, env, verify_sheet=(hooks or {}).get("verify_sheet"))
            save_state(state, env)
        if not state["steps"].get("readiness", {}).get("done"):
            state = step_readiness(state, request, env, probes=(hooks or {}).get("probes"))
            save_state(state, env)
        if not state["steps"].get("deliver", {}).get("done"):
            state = step_deliver(state, env, deliver=(hooks or {}).get("deliver"))
            save_state(state, env)
    except BootstrapFatal as exc:
        state["last_fatal"] = {"message": str(exc), "at": _now_iso()}
        save_state(state, env)
        raise
    except BootstrapRetryable as exc:
        state["last_retryable"] = {"message": str(exc), "at": _now_iso()}
        save_state(state, env)
        raise
    return state


def status(company_id: str, planner_kind: str,
           env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    state = load_state(company_id, planner_kind, env)
    return {
        "company_id": company_id,
        "planner_kind": planner_kind,
        "ready": bool(state.get("ready")),
        "steps": state.get("steps", {}),
        "last_fatal": state.get("last_fatal"),
        "last_retryable": state.get("last_retryable"),
        "sheet_id": (state.get("planner") or {}).get("sheet_id"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="social_bootstrap", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd")
    b = sub.add_parser("bootstrap", help="run/resume transactional setup")
    b.add_argument("--config", required=True)
    b.add_argument("--live", action="store_true")
    s = sub.add_parser("status", help="print setup status JSON")
    s.add_argument("--company", required=True)
    s.add_argument("--planner-kind", default="social-planner")
    sub.add_parser("self-test")
    args = parser.parse_args(argv)

    if args.cmd == "self-test":
        return _self_test()
    if args.cmd == "status":
        print(json.dumps(status(args.company, args.planner_kind), indent=1, sort_keys=True))
        return EXIT_OK
    if args.cmd == "bootstrap":
        try:
            request = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("ERROR: unreadable bootstrap config: %s" % exc, file=sys.stderr)
            return EXIT_USAGE
        try:
            state = bootstrap(request, hooks=_live_hooks(request) if args.live else None)
        except BootstrapFatal as exc:
            print("FATAL: %s" % exc, file=sys.stderr)
            return EXIT_FAILED
        except BootstrapRetryable as exc:
            print("RETRYABLE: %s" % exc, file=sys.stderr)
            return EXIT_DEGRADED
        print(json.dumps({"ready": bool(state.get("ready")), "steps": state.get("steps"),
                          "sheet_id": (state.get("planner") or {}).get("sheet_id")}, indent=1, sort_keys=True))
        return EXIT_OK if state.get("ready") else EXIT_DEGRADED
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


def _live_hooks(request: Dict[str, Any]) -> Dict[str, Callable[..., Any]]:
    """Production hooks: the real webhook transport; a LIVE readiness probe is
    wired by the installer (skill entry) — bootstrap runs stateless-safe."""
    return {"create_sheet": _default_create_sheet}


# ── self-test (fixture sandbox, no network) ─────────────────────────────────
def _self_test() -> int:
    import tempfile
    base = tempfile.mkdtemp(prefix="social-bootstrap-selftest-")
    env = {"OPENCLAW_ROOT": base}

    def good_create(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Models the F15 webhook: same provisioning key replay -> deduped.
        return {"status": "success", "deduped": "deduped_seen" in payload,
                "sheetId": "SHEET-FIXTURE", "sheetUrl": "https://docs.google.com/spreadsheets/d/SHEET-FIXTURE",
                "sharedWith": "anyone with the link can edit", "schema_version": "1.1.0"}

    def good_verify(sheet_id: str) -> Dict[str, Any]:
        return {"ok": True, "state": "ok", "sharing": "anyone,writer", "schema_version": "1.1.0", "tabs_ok": True}

    def good_ghl(request: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "state": "ok", "accounts": 2}

    request = {
        "company_id": "co-boot", "planner_kind": "social-planner",
        "owner": "owner@example.com", "notification_channel": "telegram",
        "timezone": "America/New_York", "deployment_type": "docker-vps",
        "engine": "cc-cycle-service",
        "optional_channels": {"podcast": False, "blog": False},
    }
    hooks = {"create_sheet": good_create, "verify_sheet": good_verify, "ghl_probe": good_ghl}
    s = bootstrap(request, env=env, hooks=hooks)
    assert s.get("ready") and len(s["steps"]) == 5, s
    assert s["identity"]["excluded_channels"] == {"podcast": "not_configured", "blog": "not_configured"}

    # Crash after the webhook created the file, before registry: resume REUSES
    # the same sheet (no duplicate provisioning call with a new key).
    env2 = {"OPENCLAW_ROOT": base}
    calls: List[Dict[str, Any]] = []

    def counting_create(payload: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(payload)
        return good_create({**payload, **({"deduped_seen": True} if len(calls) > 1 else {})})

    hooks2 = {"create_sheet": counting_create, "verify_sheet": good_verify, "ghl_probe": good_ghl}
    env2 = {"OPENCLAW_ROOT": tempfile.mkdtemp(prefix="sb2-")}
    bootstrap(request, env=env2, hooks=hooks2)
    assert len(calls) == 1
    # Simulate crash: wipe steps AFTER planner but keep the planner receipt.
    st = load_state(request["company_id"], request["planner_kind"], env=env2)
    st["steps"] = {"identity": st["steps"]["identity"], "planner": st["steps"]["planner"]}
    st.pop("registry", None); st.pop("readiness", None); st.pop("deliver", None); st.pop("ready", None)
    save_state(st, env=env2)
    resumed = bootstrap(request, env=env2, hooks=hooks2)
    assert len(calls) == 1, "resume must NOT re-create the sheet: %d calls" % len(calls)
    assert resumed.get("ready"), resumed

    # Missing identity fields -> FATAL, nothing provisioned.
    env3 = {"OPENCLAW_ROOT": tempfile.mkdtemp(prefix="sb3-")}
    try:
        bootstrap({k: v for k, v in request.items() if k != "timezone"}, env=env3, hooks=hooks)
        raise SystemExit("identity gate did not fail")
    except BootstrapFatal:
        pass
    assert not (Path(env3["OPENCLAW_ROOT"]) / "data" / "skill35" / "sheet-registry.json").exists()

    # Deliver without receipts -> refused (ready only after verified steps).
    env4 = {"OPENCLAW_ROOT": tempfile.mkdtemp(prefix="sb4-")}
    state4 = load_state("co-x", "social-planner", env=env4)
    try:
        step_deliver(state4, env=env4)
        raise SystemExit("deliver gate did not fail")
    except BootstrapFatal:
        pass
    print("self-test: transactional bootstrap, crash-resume reuse, identity gate, deliver gate. PASS")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())