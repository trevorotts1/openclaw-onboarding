#!/usr/bin/env python3
"""
gr_board.py — Graphics dept PRODUCER-SIDE Command Center board caller (FAIL-SOFT).

Port of the proven presentations/scripts/cc_board.py pattern, retargeted to the GRAPHICS
department Kanban. Graphics work previously boarded onto Skill 48's /api/ad-campaigns
endpoints (SOP 9.12), so a graphics production run NEVER appeared as a
department_slug:"graphics" task on the department board the way presentations decks do
(diagnosis G4). This caller lands a graphics production job on the department board as ONE
task via POST /api/tasks/ingest and advances it through the graphics lifecycle
(PROMPT-QC → RENDER → IMAGE-QC → GHL-DELIVERED) with per-phase movement receipts.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from cc_board.py)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP error, a
    timeout, or any other failure is CAUGHT, LOGGED to stderr, and the run CONTINUES.
    Boarding is a convenience, never a gate on generation. Every public function returns a
    value (task_id / bool / int) and NEVER raises.

  * AUTH PARITY with the CC /api/tasks/ingest endpoint:
      - Authorization: Bearer <CC_API_TOKEN>            (global middleware layer)
      - x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex  (per-route layer)
    Both no-op when their env var is unset (the endpoint no-ops the check in dev mode). We
    sign the EXACT bytes we send, so a configured secret matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => fail-soft no-op.
      COMMAND_CENTER_URL / MISSION_CONTROL_URL  base URL (either accepted).
      CC_API_TOKEN / MC_API_TOKEN               bearer (optional).
      WEBHOOK_SECRET / CC_WEBHOOK_SECRET         HMAC secret (optional).
      CC_BOARD_TIMEOUT                           per-request timeout seconds (default 8).

REQUEST CONTRACT (matched to the live /api/tasks/ingest endpoint):
  CREATE   POST {base}/api/tasks/ingest
    body:  {title, description, priority, source:"gr_board", source_ref,
            department_slug:"graphics", persona:"Chief Design Officer",
            external_session_id, idempotency_key:sha256(job_id+title)}
    return: {ok, task_id, deduped}
  PATCH    PATCH {base}/api/tasks/{task_id}   (task-level STATUS change)
    body:  {phase_id, status, note?}
    status vocabulary is the authoritative CC TaskStatus enum (CC_TASK_STATUSES). The
    producer STOPS at 'review' (Gate 4 lives in the review column, SOP 9.12); promotion
    'review'->'done' is the CDO Gate-4 sign-off, never a producer self-close.
  ACTIVITY POST {base}/api/tasks/{task_id}/activities   (mid-run phase PROGRESS)
    body:  {activity_type:"updated", message}
    Mid-run phase boundaries are logged as ACTIVITIES, never task-level status changes.

MOVEMENT RECEIPT — every advance ATTEMPT + its HTTP status/body is appended to
<job>/checkpoints/cc-board.json so a failed advance is VISIBLE on disk. The task_id AND
cc_register_attempted=True are written into <job>/checkpoints/process_manifest.json so the
offline AF-GIP-CC-UNREGISTERED check passes whether or not the live POST succeeded:
  - PASS  when cc_task_id is set (successful registration).
  - PASS  when cc_register_attempted is True (transport failed, attempt logged).
  - FAIL  when neither field exists (this module was never called for this run).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_DEFAULT_TIMEOUT = 8
_DEPARTMENT_SLUG = "graphics"
_PERSONA = "Chief Design Officer"

# Authoritative Command Center TaskStatus enum — the 10 values of UpdateTaskSchema
# (CC repo src/lib/validation.ts). NB: there is NO 'delivered' status — a completed run
# closes at 'review' (producer) then 'done' (CDO Gate 4).
CC_TASK_STATUSES = frozenset({
    "backlog", "inbox", "planning", "in_progress", "assigned",
    "review", "testing", "blocked", "pending_dispatch", "done",
})

# The graphics production lifecycle phases surfaced as board ACTIVITIES (SOP 9.12 mapping +
# the GIP gates): a compact, ordered vocabulary the board feed shows for a graphics job.
GRAPHICS_PHASES = ("PROMPT-QC", "RENDER", "IMAGE-QC", "GHL-DELIVERED")


def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled, a clean
    no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    print(f"[gr_board/graphics] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict, cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None). Raises only
    urllib/OS errors, which the public callers catch (fail-soft)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# process_manifest.json + movement-receipt helpers (<job>/checkpoints/).
# ---------------------------------------------------------------------------
def _manifest_path(job_dir) -> Path:
    return Path(job_dir) / "checkpoints" / "process_manifest.json"


def _read_manifest(job_dir) -> dict:
    p = _manifest_path(job_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_manifest(job_dir, updates: dict) -> bool:
    p = _manifest_path(job_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(job_dir)
        manifest.update(updates)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"manifest write failed ({exc}).")
        return False


def _movements_path(job_dir) -> Path:
    return Path(job_dir) / "checkpoints" / "cc-board.json"


def _now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return ""


def _record_movement(job_dir, entry: dict) -> None:
    if job_dir is None:
        return
    p = _movements_path(job_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if p.exists():
            try:
                loaded = json.loads(p.read_text())
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}
        movements = data.get("movements")
        if not isinstance(movements, list):
            movements = []
        record = {"ts": _now()}
        record.update(entry)
        movements.append(record)
        data["movements"] = movements
        data["successful_advances"] = sum(1 for m in movements if isinstance(m, dict) and m.get("ok"))
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, p)
    except OSError as exc:
        _log(f"movement receipt write failed ({exc}).")


def count_successful_advances(job_dir) -> int:
    if job_dir is None:
        return 0
    p = _movements_path(job_dir)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    got = data.get("successful_advances")
    if isinstance(got, int):
        return got
    movements = data.get("movements")
    if isinstance(movements, list):
        return sum(1 for m in movements if isinstance(m, dict) and m.get("ok"))
    return 0


def assert_min_one_advance(job_dir) -> bool:
    return count_successful_advances(job_dir) >= 1


def stamp_task_id(job_dir, task_id: str) -> bool:
    if not task_id or job_dir is None:
        return False
    ok = _merge_manifest(job_dir, {"cc_task_id": task_id})
    if not ok:
        _log(f"stamp_task_id failed for task_id={task_id}.")
    return ok


def is_registered(job_dir) -> bool:
    """Offline AF-GIP-CC-UNREGISTERED check: PASS when the run has a cc_task_id OR a logged
    cc_register_attempt (fail-soft on transport); FAIL only when this module was NEVER called
    for the run (neither field present). Never raises."""
    m = _read_manifest(job_dir)
    return bool(m.get("cc_task_id")) or bool(m.get("cc_register_attempted"))


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on idempotency_key server-side)
# ---------------------------------------------------------------------------
def ingest_graphics_task(job_dir, job_slug: str, title: str, description: str,
                         priority: str = "medium", env: Optional[dict] = None) -> Optional[str]:
    """Ingest (or idempotently re-fetch) a graphics job task on the CC board. Always stamps
    cc_register_attempted=True BEFORE the HTTP call so a transport crash / URL-absent no-op is
    fail-soft (not never-attempted). Returns the task_id string on success, else None. FAIL-SOFT.
    Idempotency key is sha256(job_slug + title)."""
    if job_dir is None:
        return None
    if not _merge_manifest(job_dir, {"cc_register_attempted": True}):
        _log("could not stamp cc_register_attempted; continuing anyway.")

    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled (no-op); run "
             "continues ungrouped. cc_register_attempted=True logged.")
        return None

    source_ref = job_slug or "graphics-job"
    idempotency_key = hashlib.sha256(f"{source_ref}{title}".encode("utf-8")).hexdigest()
    payload = {
        "title": title,
        "description": description,
        "priority": priority,
        "source": "gr_board",
        "source_ref": source_ref,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": source_ref,
        "idempotency_key": idempotency_key,
    }
    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); run continues ungrouped.")
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        _log(f"task {'deduped (reused)' if body.get('deduped') else 'created'}: "
             f"task_id={task_id} job_slug={job_slug}")
        stamp_task_id(job_dir, task_id)
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; run continues ungrouped.")
    return None


# ---------------------------------------------------------------------------
# PATCH — advance the task card at a phase boundary (real status transitions only).
# ---------------------------------------------------------------------------
def patch_phase(job_dir, task_id: str, phase_id: str, status: str, note: str = "",
                env: Optional[dict] = None) -> bool:
    """PATCH the CC task card to a task-level STATUS. Use for real transitions only: the
    RENDER start (backlog->in_progress) and the TERMINAL producer close (status='review').
    The producer STOPS at 'review' (Gate 4 lives in the review column, SOP 9.12); promotion
    'review'->'done' is the CDO's job. Mid-run phase PROGRESS goes through post_activity().
    A status outside the CC enum is refused (recorded, no network). FAIL-SOFT: returns
    True/False, never raises."""
    endpoint = "PATCH /api/tasks/{id}"
    if status not in CC_TASK_STATUSES:
        _log(f"patch_phase refused — {status!r} is not a valid CC TaskStatus "
             f"({sorted(CC_TASK_STATUSES)}).")
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "status", "target": status,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": "invalid status (not in CC TaskStatus enum)"})
        return False
    cfg = board_config(env)
    if cfg is None:
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "status", "target": status,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)"})
        return False
    if not task_id:
        _log("patch_phase skipped — task_id missing.")
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "status", "target": status,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": "task_id missing"})
        return False

    payload = {"phase_id": phase_id, "status": status}
    if note:
        payload["note"] = note
    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_phase {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "status", "target": status,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": f"{type(exc).__name__}: {exc}"})
        return False

    ok = st == 200
    _record_movement(job_dir, {"phase_id": phase_id, "kind": "status", "target": status,
                               "endpoint": endpoint, "http_status": st, "ok": ok,
                               "detail": "OK" if ok else str(body)[:300]})
    if ok:
        _log(f"patch_phase {phase_id}->{status} OK (task_id={task_id}).")
        return True
    _log(f"patch_phase {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    return False


def post_activity(job_dir, task_id: str, phase_id: str, note: str,
                  activity_type: str = "updated", env: Optional[dict] = None) -> bool:
    """POST a mid-run phase-PROGRESS activity to /api/tasks/{task_id}/activities. This is how
    the graphics lifecycle phases (PROMPT-QC passed, RENDER complete, IMAGE-QC passed,
    GHL-DELIVERED) are recorded — as ACTIVITIES, NOT task-level status changes. FAIL-SOFT:
    returns True/False, never raises."""
    endpoint = "POST /api/tasks/{id}/activities"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "activity", "target": activity_type,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)"})
        return False
    if not task_id:
        _log("post_activity skipped — task_id missing.")
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "activity", "target": activity_type,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": "task_id missing"})
        return False

    message = (f"[{phase_id}] {note}".strip() if note else f"[{phase_id}]")
    payload = {"activity_type": activity_type, "message": message}
    url = f"{cfg['base_url']}/api/tasks/{task_id}/activities"
    try:
        st, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"post_activity {phase_id} failed ({type(exc).__name__}: {exc}).")
        _record_movement(job_dir, {"phase_id": phase_id, "kind": "activity", "target": activity_type,
                                   "endpoint": endpoint, "http_status": None, "ok": False,
                                   "detail": f"{type(exc).__name__}: {exc}"})
        return False

    ok = st in (200, 201)
    _record_movement(job_dir, {"phase_id": phase_id, "kind": "activity", "target": activity_type,
                               "endpoint": endpoint, "http_status": st, "ok": ok,
                               "detail": "OK" if ok else str(body)[:300]})
    if ok:
        _log(f"post_activity {phase_id} OK (task_id={task_id}).")
        return True
    _log(f"post_activity {phase_id} non-OK (HTTP {st}): {body}.")
    return False


# ---------------------------------------------------------------------------
# SELF-TEST — no network, stdlib only. Monkeypatches _request for the live path.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []
    global _request
    real_request = _request

    # 1) Board DISABLED (no env) — fail-soft no-op, but the attempt is stamped and the offline
    #    AF-GIP-CC-UNREGISTERED check still PASSES; a status patch records an ok:false movement.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        tid = ingest_graphics_task(base, "acme-launch", "Graphics: Acme launch pack", "3 ads",
                                   env={})
        if tid is not None:
            fails.append(f"1 disabled: expected None task_id, got {tid}")
        if not is_registered(base):
            fails.append("1 disabled: is_registered should PASS on a logged attempt (fail-soft)")
        patch_phase(base, "", "RENDER", "in_progress", env={})  # disabled -> ok:false movement
        if count_successful_advances(base) != 0:
            fails.append("1 disabled: expected 0 successful advances")

    # 2) never-called -> is_registered FALSE (fail-CLOSED only on never-attempted).
    with tempfile.TemporaryDirectory() as t:
        if is_registered(Path(t)):
            fails.append("2 never-called: is_registered should FAIL when the module was never called")

    # 3) invalid status is refused with NO network (records ok:false, returns False).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        if patch_phase(base, "tid_x", "P", "delivered", env={"COMMAND_CENTER_URL": "http://x"}):
            fails.append("3 enum-guard: 'delivered' (not a CC status) must be refused")

    # 4) LIVE path via a mock _request: ingest->task_id, patch->200, activity->201; receipts land.
    def _mock_request(method, url, payload, cfg):
        if url.endswith("/api/tasks/ingest"):
            return 200, {"ok": True, "task_id": "task_42", "deduped": False}
        if url.endswith("/activities"):
            return 201, {"activity": {"id": "act_1"}}
        return 200, {"task": {"id": payload.get("phase_id")}}

    env = {"COMMAND_CENTER_URL": "https://cc.example", "CC_API_TOKEN": "tok",
           "WEBHOOK_SECRET": "sek"}
    try:
        _request = _mock_request  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            tid = ingest_graphics_task(base, "acme", "Graphics: Acme", "pack", env=env)
            if tid != "task_42":
                fails.append(f"4 live-ingest: expected task_42, got {tid}")
            if _read_manifest(base).get("cc_task_id") != "task_42":
                fails.append("4 live-ingest: cc_task_id not stamped in manifest")
            ok_render = patch_phase(base, tid, "RENDER", "in_progress", env=env)
            for ph in GRAPHICS_PHASES:
                post_activity(base, tid, ph, f"{ph} passed", env=env)
            ok_review = patch_phase(base, tid, "GATE-4", "review", "review-ready", env=env)
            if not (ok_render and ok_review):
                fails.append("4 live-advance: status patches did not report OK")
            # 1 ingest? (ingest not counted in movements) + 2 status + 4 activities = 6 OK advances.
            if count_successful_advances(base) != 6:
                fails.append(f"4 live-advance: expected 6 successful advances, got "
                             f"{count_successful_advances(base)}")
            if not assert_min_one_advance(base):
                fails.append("4 live-advance: assert_min_one_advance should be True")
    finally:
        _request = real_request  # type: ignore[assignment]

    if fails:
        print("gr_board selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("gr_board selftest -> PASS (4 groups: disabled-no-op/never-called/enum-guard/"
          "live-ingest+advance+receipts)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    import argparse
    ap = argparse.ArgumentParser(description="Graphics Command Center board helper (fail-soft).")
    ap.add_argument("--registered", metavar="JOB_DIR",
                    help="offline AF-GIP-CC-UNREGISTERED check: exit 0 if the run has a "
                         "cc_task_id or a logged attempt, exit 1 if the board was never called.")
    args = ap.parse_args()
    if args.registered:
        sys.exit(0 if is_registered(args.registered) else 1)
    ap.print_help()
    sys.exit(0)
