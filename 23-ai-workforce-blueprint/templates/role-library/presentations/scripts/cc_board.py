#!/usr/bin/env python3
"""
cc_board.py — Presentations dept PRODUCER-SIDE Command Center board caller (FAIL-SOFT).

Port of the proven Skill-48 cc_board.py pattern, adapted to the presentations
pipeline endpoints from SOP-00-Owner-Task-Routing. Lands a deck build on the CC
Kanban board as ONE task and advances that task through phase boundaries as the
pipeline progresses.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from Skill-48)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    deck build CONTINUES. Boarding the run is a convenience, never a gate. The
    ONLY thing that actually fails a deck job for "not on the board" is the
    offline _chk_cc_registered() check (AF-CC-UNREGISTERED / AF-CC-UNVERIFIED)
    in build_deck.py — VERIFIED only with a cc_task_id + a matching
    cc_registration linkage tag (stamped by a real round-trip). NOTE (honesty
    fix, 2026-08-18): that tag is a same-file consistency check, NOT a
    cryptographic proof — see registration_linkage_tag()'s docstring below for
    exactly what it does and does not establish. A LOGGED ATTEMPT with no
    matching tag is UNVERIFIED (fails with an honest message, never read as
    verified); never-attempted is UNREGISTERED (fail-closed). So every public
    function here returns a value (task_id / bool) and NEVER raises.

  * AUTH PARITY with the CC endpoint:
      - ``Authorization: Bearer <CC_API_TOKEN>``  — global middleware layer.
        No-op when CC_API_TOKEN / MC_API_TOKEN is unset.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex —
        per-route layer copied verbatim from /api/tasks/ingest. Endpoint
        no-ops the check when WEBHOOK_SECRET is unset (dev mode). We sign the
        EXACT bytes we send, so a configured secret matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => fail-soft no-op.
      COMMAND_CENTER_URL   base URL of the Command Center (preferred name).
      MISSION_CONTROL_URL  fallback alias; accepted when COMMAND_CENTER_URL absent.
      CC_API_TOKEN         long-lived bearer (middleware layer). Optional.
      MC_API_TOKEN         alias for CC_API_TOKEN. Optional.
      WEBHOOK_SECRET       HMAC secret (per-route layer). Optional.
      CC_WEBHOOK_SECRET    alias for WEBHOOK_SECRET. Optional.
      CC_BOARD_TIMEOUT     per-request timeout seconds (default 8).

REQUEST CONTRACT (matched to the live /api/tasks/ingest endpoint):

  CREATE   POST {base}/api/tasks/ingest
    body:  {title, description, priority, source, source_ref,
            department_slug:"presentations", persona:"Director of Presentations",
            external_session_id, idempotency_key:sha256(source_ref+title)}
    return: {ok, task_id, deduped}

  PATCH    PATCH {base}/api/tasks/{task_id}   (task-level STATUS change)
    body:  {phase_id, status, note?, process_certificate_sha?}
    return: 200 -> {task}
    status vocabulary is the authoritative CC TaskStatus enum (UpdateTaskSchema in
    src/lib/validation.ts): backlog | inbox | planning | in_progress | assigned |
    review | testing | blocked | pending_dispatch | done. There is NO 'delivered'
    status — a COMPLETED deck closes with status='done' + process_certificate_sha
    (the minted PROCESS-CERTIFICATE sha); the word "delivered" belongs in the note.

  ACTIVITY POST {base}/api/tasks/{task_id}/activities   (mid-run phase PROGRESS)
    body:  {activity_type:"updated", message, metadata:{phase_id}}
    return: 201 -> {activity}
    Mid-run phase boundaries (P4-RENDER complete, P8-ASSEMBLE complete) are logged
    as ACTIVITIES, never as task-level status changes: a mid-run status='done'
    422s the presentations cert done-gate (no PROCESS-CERTIFICATE exists yet) and
    would wrongly close a non-presentation card. The phase id rides in BOTH the
    message text (human-readable) and metadata.phase_id (machine-readable — the
    U060 stepper reducer reads it there, not from the message).

MOVEMENT RECEIPT — every advance ATTEMPT (status change or activity post) plus its
HTTP status / body is appended to working/checkpoints/cc-board.json (mirroring the
campaign skills' mc-board.json receipt) so a failed advance is VISIBLE on disk.
Recording is fail-soft; it never raises and never blocks the deck build.

The task_id AND cc_register_attempted=True are written into
``working/checkpoints/process_manifest.json`` so the offline AF-CC-UNREGISTERED
check in build_deck._chk_cc_registered can judge the run:
  - VERIFIED  when cc_task_id is set AND the cc_registration linkage tag
    (a same-file consistency value over cc_task_id|idempotency_key, stamped
    only by a real ingest round-trip — NOT a cryptographic proof; see
    registration_linkage_tag()) matches — a hint of an intact registration,
    never authorization.
  - UNVERIFIED when cc_register_attempted is True but there is NO cc_task_id or
    the tag does not match (transport/partial failure, or a hand-written
    id). The gate FAILS with an explicit honest AF-CC-UNVERIFIED message —
    could-not-confirm-consistency NEVER prints as verified.
  - UNREGISTERED when neither field exists (this module was never called).

PUBLIC API
  ingest_deck_task(run_dir, deck_slug, title, description, priority="medium")
      -> task_id str | None
  ingest_child_task(run_dir, parent_task_id, phase_id, title, description,
      priority="normal") -> task_id str | None
      # Option B: one child card per phase, nested under parent_task_id.
      # Idempotency key sha256(parent_task_id + ':' + phase_id). Call site
      # (BoardMirror.child_report in presentation_job/board.py) checks
      # read_child_task_id()/state FIRST so a phase reporting progress twice
      # never reaches this function twice.
  read_child_task_id(run_dir, phase_id) -> task_id str | None
  stamp_child_task_id(run_dir, phase_id, task_id) -> bool
  patch_phase(run_dir, task_id, phase_id, status, note="") -> bool
      # task-level STATUS change. The producer's TERMINAL close is status='review'
      # (never a self-closed 'done'); on 'review'/'done' it auto-attaches the cert
      # sha, and on 'review' it also folds the real per-gate QC scores into the note
      # + a structured qc_scores key (retried without the key on a strict-server 422).
  post_activity(run_dir, task_id, phase_id, note, activity_type="updated",
                scores=None) -> bool
      # mid-run phase PROGRESS via the /activities endpoint (NOT a status change);
      # optional per-gate `scores` fold into the message + a structured scores key.
      # Always carries metadata.phase_id — the field the U060 stepper reducer reads
      # (a phase id only in the message text never advances the stepper).
  post_qc_activities(run_dir, task_id) -> int
      # post one QC-grade activity per graded gate (from collect_qc_summary).
  collect_qc_summary(run_dir) -> dict   # distil working/qc/*.json into board scores
  stamp_task_id(run_dir, task_id, idempotency_key="", deck_slug="") -> bool
      # merge cc_task_id (and, when the ingest idempotency_key is supplied, the
      # cc_registration linkage tag -- a same-file consistency hint, NOT a
      # cryptographic proof) into process_manifest.json.
  register_deliverable(task_id, url, meta=None, *, env=None) -> bool
      # POST /api/tasks/{task_id}/deliverables — the FIX-12 registration bridge
      # (ported from Skill-06 cc_board.py). FAIL-SOFT: never raises; a False
      # return never blocks the deck build. The task can leave in_progress only
      # once task_deliverables holds a row (POST 2xx -> row created).
  count_successful_advances(run_dir) -> int
  assert_min_one_advance(run_dir) -> bool
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_DEFAULT_TIMEOUT = 8
_DEPARTMENT_SLUG = "presentations"
_PERSONA = "Director of Presentations"

# WORK-ITEM-02 engine dispatch: the single callback that wires the presentation
# engine into the CC ingest completion path. Called after a CC task card is
# successfully created (or re-fetched via idempotency). Best-effort, fail-soft
# -- a failed engine launch never blocks the deck build or the board registration.
#
# FIX 18 (lease discipline): this launcher is one of the lease's five named
# launch paths (lease.py's docstring: "the door, supervisor._restart,
# launcher.dispatch, presentation-intake-poll.sh, cc_board._dispatch_engine_if_idle").
# It acquires the run lease BEFORE spawning and, on success, releases it again
# before the Popen — the exact acquire -> spawn-hand-off pattern supervisor.
# _restart uses, for the same reason: the resumed engine's own __main__ acquire
# is the hand-off, and a lease still held by THIS pid when the child starts
# would refuse the child (same-host live pid, unexpired lease => takeover
# denied) and the child would then have to wait out the whole TTL. A live
# holder keeps the lease: no spawn, log it, return — the run already has an
# owner, which is the lease doing its job. The lease is a GUARDED import, not
# a gate: if presentation_job.lease is absent or acquire raises, the launch
# proceeds UNLEASED and says so in the log — degrade loudly, never crash the
# dispatch callback (same discipline as supervisor._acquire_restart_lease).
_DISPATCH_LEASE_TTL_SECONDS = 300  # headroom over the engine's own acquire; matches supervisor's restart TTL

def _dispatch_engine_if_idle(run_dir) -> None:
    """If the engine is not running for this run_dir, launch it as a background
    subprocess via presentation_job --run. Fail-soft: never raises.

    FIX 18: acquires the run lease first (guarded import; unleased launch with
    a logged reason when the module is absent), refuses when a live holder owns
    the run, and releases the lease right before the spawn so the child engine
    acquires it as its own hand-off."""
    import subprocess as _subprocess
    run_path = Path(run_dir) if not isinstance(run_dir, Path) else run_dir
    state_json = run_path / "state.json"
    if not state_json.is_file():
        return  # no state.json -- engine was never created (not an error)
    try:
        st = json.loads(state_json.read_text(encoding="utf-8"))
        terminal = st.get("terminal")
    except (json.JSONDecodeError, OSError):
        return
    # Do not re-launch a job that is already done/blocked, or one whose engine
    # PID is already alive.
    if terminal in ("DONE", "BLOCKED"):
        return
    pid = st.get("engine_pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            return  # already running
        except OSError:
            pass  # dead PID -- safe to re-launch

    # Resolve the engine entry point from this module's location.
    here = Path(__file__).resolve().parent  # scripts/
    engine = here / "presentation_job.py"
    if not engine.is_file():
        return

    # FIX 18 -- lease before launch. cc_board.py sits at scripts/ next to the
    # presentation_job package, so the package is importable from this file's
    # directory (the dispatch callback may run with a different cwd, so the
    # path insert is explicit and symmetric with how the tests import cc_board).
    lease = None
    lease_note = ""
    try:
        import sys as _sys
        _here = str(here)
        if _here not in _sys.path:
            _sys.path.insert(0, _here)
        try:
            from presentation_job import lease as _lease_mod
        except ImportError:
            _lease_mod = None
        if _lease_mod is not None:
            lease = _lease_mod.acquire(
                run_path,
                {"who": "cc_board.dispatch", "purpose": "cc_board.engine_dispatch"},
                ttl_s=_DISPATCH_LEASE_TTL_SECONDS,
            )
            if lease is None:
                holder_desc = ""
                try:
                    holder_desc = _lease_mod.describe_holder(run_path)
                except Exception:  # noqa: BLE001 -- a read failure must not hide the refusal
                    holder_desc = ""
                detail = holder_desc or "an unreadable lease at working/.lease.json"
                _log(f"engine dispatch refused for {run_path}: lease held by {detail}")
                return  # the run has an owner; not a spawn failure
            lease_note = "; lease acquired, verified unowned"
        else:
            lease_note = "; UNLEASED: presentation_job.lease unavailable"
    except Exception as exc:  # noqa: BLE001 -- lease trouble must not kill the dispatch callback
        lease = None
        lease_note = f"; UNLEASED: lease acquire raised {type(exc).__name__}: {exc}"

    try:
        _subprocess.Popen(
            [sys.executable or "python3", str(engine), "--run", "--run-dir", str(run_path)],
            shell=False, cwd=str(here),
            start_new_session=True, close_fds=True,
        )
        _log(f"engine dispatched for {run_path}{lease_note}")
    except (OSError, _subprocess.SubprocessError) as exc:
        _log(f"engine dispatch failed for {run_path}: {exc}")
    finally:
        if lease is not None:
            try:
                from presentation_job import lease as _lease_mod2
                _lease_mod2.release(lease)
            except Exception:  # noqa: BLE001 -- a failed release must not abort the dispatch
                pass

# U030 (audit E1): the statuses whose PATCH payload carries proof the narrower
# status endpoint cannot accept. POST /api/tasks/{id}/status validates against
# {status, note} ONLY (StatusTransitionSchema) and is NOT strict, so any other key
# is DROPPED SILENTLY with a 200 — including process_certificate_sha, which is the
# whole no-skip proof. So these statuses keep using PATCH /api/tasks/{id}; every
# other status uses the status endpoint, which does not run the Triad gate.
# This is the SAME predicate that decides whether a certificate is attached at all
# (see the if status in _CERT_BEARING_STATUSES block below) — one constant, one
# truth, so the two can never drift apart.
_CERT_BEARING_STATUSES = frozenset({"review", "done"})
_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
)


def resolve_requester(run_dir, env: Optional[dict] = None) -> tuple:
    """Resolve (chat_id, channel) for the client who asked for this deck.

    Order: intake.json (working/copy/intake.json -> requester_chat_id) first, because
    it is per-deck and durable; then the env keys above, which is how the CEO's route
    helper and the orchestrator pass it today. Returns ("", "") when nothing resolves —
    an operator-initiated build legitimately has no client requester.
    Never raises: an unreadable/absent intake.json is treated as "not declared".
    """
    src = env if env is not None else os.environ
    chat = ""
    channel = ""
    try:
        obj = json.loads((Path(run_dir) / "working" / "copy" / "intake.json").read_text())
        if isinstance(obj, dict):
            chat = str(obj.get("requester_chat_id") or "").strip()
            channel = str(obj.get("requester_channel") or "").strip()
    except Exception:  # noqa: BLE001 — absent/unreadable intake is an expected state
        pass
    if not chat:
        for key in _REQUESTER_ENV_KEYS:
            val = str(src.get(key) or "").strip()
            if val:
                chat = val
                break
    if chat and not channel:
        channel = str(src.get("PRESENTATION_REQUESTER_CHANNEL") or "").strip() or "telegram"
    return (chat, channel) if chat else ("", "")

# Authoritative Command Center TaskStatus enum — the 10 values of UpdateTaskSchema
# in the CC repo src/lib/validation.ts. Kept here as the single source of truth on
# the producer side; the contract test (test_cc_contract.py) fails if this drifts
# from the CC enum or if build_deck.py / this module emit a status outside it.
# NB: there is NO 'delivered' status — a completed deck closes with 'done'.
CC_TASK_STATUSES = frozenset({
    "backlog",
    "inbox",
    "planning",
    "in_progress",
    "assigned",
    "review",
    "testing",
    "blocked",
    "pending_dispatch",
    "done",
})


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is
    set — the graceful-degradation contract. Never raises."""
    env = env if env is not None else os.environ
    base = (
        env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or ""
    ).strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (
            env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or ""
        ).strip(),
        "secret": (
            env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or ""
        ).strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent,
    and never fatal."""
    print(f"[cc_board/presentations] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-
    for-byte parity with verifyWebhookSignature() in the route handlers. None
    when no secret (the endpoint also no-ops in that case)."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict, cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors, which the public callers catch (fail-soft)."""
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
    except urllib.error.HTTPError as exc:  # 4xx/5xx — read the body for context
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# process_manifest.json helpers — atomic read / merge / write.
# ---------------------------------------------------------------------------
def _manifest_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"


def _read_manifest(run_dir) -> dict:
    """Read process_manifest.json; return {} on any error. Never raises."""
    p = _manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_manifest(run_dir, updates: dict) -> bool:
    """Merge `updates` into process_manifest.json atomically.
    Returns True on success, False on error. Never raises."""
    p = _manifest_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(run_dir)
        manifest.update(updates)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"manifest write failed ({exc}).")
        return False


# ---------------------------------------------------------------------------
# MOVEMENT RECEIPT — working/checkpoints/cc-board.json. Mirrors the campaign
# skills' mc-board.json pattern: every board advance ATTEMPT (a task-level status
# change or an activity post) is appended with its HTTP status/body so a failed
# advance is VISIBLE on disk. successful_advances is recomputed on every append.
# Recording is fail-soft — it never raises and never blocks the deck build.
# ---------------------------------------------------------------------------
def _movements_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "cc-board.json"


def _now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001 — a clock hiccup must not break a receipt
        return ""


def _record_movement(run_dir, entry: dict) -> None:
    """Append one advance-attempt receipt to working/checkpoints/cc-board.json.
    Never raises. A no-op when run_dir is None."""
    if run_dir is None:
        return
    p = _movements_path(run_dir)
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
        data["successful_advances"] = sum(
            1 for m in movements if isinstance(m, dict) and m.get("ok")
        )
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, p)
    except OSError as exc:
        _log(f"movement receipt write failed ({exc}).")


def count_successful_advances(run_dir) -> int:
    """Number of board advances that returned OK for this run (0 when the receipt
    is absent / unreadable / board disabled). Never raises."""
    if run_dir is None:
        return 0
    p = _movements_path(run_dir)
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


def assert_min_one_advance(run_dir) -> bool:
    """Lightweight gate: a completed run should have recorded >= 1 SUCCESSFUL board
    advance. Returns True/False; NEVER raises and never blocks — the caller decides
    whether to warn (a disabled board legitimately records none)."""
    return count_successful_advances(run_dir) >= 1


# ---------------------------------------------------------------------------
# QC SCORE SUMMARY — read the five per-phase QC reports the render engine writes
# to working/qc/*.json and distil the real grades into a compact, board-ready
# summary. This is the DATA behind the CC QC-scorer / Devil's-Advocate promotion
# from 'review' -> 'done': the producer stops at 'review' and hands the actual
# per-gate scores (average / pass / autofail count) to the board so the reviewer
# sees WHY the deck is review-ready, not just a phase breadcrumb + a cert hash.
# Field names match the render engine's own QC-report schema (build_deck.py's
# _chk_copy_qc / _qc_report_gate): {gate, average|average_score, pass,
# triggered_autofails|autofails_triggered}. Every function here is FAIL-SOFT —
# it never raises; an unreadable/absent report is simply omitted from the summary.
# ---------------------------------------------------------------------------
_QC_REPORTS = (
    ("copy_qc_report.json", "Copy-QC"),
    ("prompt_qc_report.json", "Prompt-QC"),
    ("image_qc_report.json", "Image-QC"),
    ("typography_qc_report.json", "Typography-QC"),
    ("speech_qc_report.json", "Speech-QC"),
)


def _extract_qc_gate(report: str, obj: dict) -> Optional[dict]:
    """Distil one QC report dict into {report, gate, average, pass, autofails_count}.
    Returns None when `obj` is not a governed grade (not a dict). Mirrors the
    render engine's own field tolerance (average|average_score,
    triggered_autofails|autofails_triggered). Never raises."""
    if not isinstance(obj, dict):
        return None
    avg = obj.get("average", obj.get("average_score"))
    try:
        avg_val = round(float(avg), 2) if avg is not None else None
    except (TypeError, ValueError):
        avg_val = None
    triggered = obj.get("triggered_autofails") or obj.get("autofails_triggered") or []
    autofails_count = len(triggered) if isinstance(triggered, (list, tuple)) else 0
    gate = str(obj.get("gate", "")).strip() or None
    return {
        "report": report,
        "gate": gate,
        "average": avg_val,
        "pass": obj.get("pass") is True,
        "autofails_count": autofails_count,
    }


def collect_qc_summary(run_dir) -> dict:
    """Read the per-phase QC reports at <run_dir>/working/qc/*.json and return a
    compact score summary for the Command Center. FAIL-SOFT: never raises; returns
    {"gates": [], ...} when run_dir is falsy or no report is readable.

    Shape:
      {
        "gates": [{report, gate, average, pass, autofails_count}, ...],
        "gates_graded":   int,          # reports actually found + parsed
        "overall_pass":   bool,         # every graded gate pass:true AND 0 autofails
        "min_average":    float | None, # lowest numeric average across graded gates
        "autofails_total": int,
      }"""
    summary = {
        "gates": [],
        "gates_graded": 0,
        "overall_pass": False,
        "min_average": None,
        "autofails_total": 0,
    }
    if run_dir is None:
        return summary
    qc_dir = Path(run_dir) / "working" / "qc"
    if not qc_dir.is_dir():
        return summary
    gates = []
    averages = []
    autofails_total = 0
    all_pass = True
    for fname, _label in _QC_REPORTS:
        path = qc_dir / fname
        if not path.is_file():
            continue
        try:
            obj = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        gate = _extract_qc_gate(fname, obj)
        if gate is None:
            continue
        gates.append(gate)
        if gate["average"] is not None:
            averages.append(gate["average"])
        autofails_total += gate["autofails_count"]
        if not gate["pass"] or gate["autofails_count"] > 0:
            all_pass = False
    summary["gates"] = gates
    summary["gates_graded"] = len(gates)
    summary["autofails_total"] = autofails_total
    summary["min_average"] = min(averages) if averages else None
    # overall_pass is only meaningful once at least one gate was graded.
    summary["overall_pass"] = bool(gates) and all_pass
    return summary


def qc_summary_note(summary: dict) -> str:
    """One compact, human/DA-readable line for the CC note/activity message, e.g.
    'QC copy=9.1 prompt=9.3 image=8.7 typo=9.0 speech=8.9 | min=8.7 autofails=0'.
    Returns '' when nothing was graded. Never raises — a summary field surface
    that ALWAYS lands (the note is an accepted CC field) even if a strict server
    rejects the structured qc_scores key."""
    if not isinstance(summary, dict):
        return ""
    gates = summary.get("gates") or []
    if not gates:
        return ""
    _short = {
        "copy_qc_report.json": "copy",
        "prompt_qc_report.json": "prompt",
        "image_qc_report.json": "image",
        "typography_qc_report.json": "typo",
        "speech_qc_report.json": "speech",
    }
    parts = []
    for g in gates:
        if not isinstance(g, dict):
            continue
        label = _short.get(g.get("report"), g.get("report") or "gate")
        avg = g.get("average")
        mark = "" if g.get("pass") else "!"
        parts.append(f"{label}={avg if avg is not None else '?'}{mark}")
    tail = f"min={summary.get('min_average')} autofails={summary.get('autofails_total', 0)}"
    return f"QC {' '.join(parts)} | {tail}".strip()


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on idempotency_key server-side)
# ---------------------------------------------------------------------------
def ingest_deck_task(
    run_dir,
    deck_slug: str,
    title: str,
    description: str,
    priority: str = "medium",
    env: Optional[dict] = None,
    requester_chat_id: Optional[str] = None,
    requester_channel: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[str]:
    """Ingest (or idempotently re-fetch) a deck task on the CC board.

    Always stamps cc_register_attempted=True in process_manifest.json BEFORE
    the HTTP call so a transport crash or URL-absent no-op is distinguished
    from never-attempted by build_deck._chk_cc_registered (a failed attempt is
    UNVERIFIED, never the UNREGISTERED fail-closed, and never read as
    verified).

    Returns the task_id string on success, else None. FAIL-SOFT — a None
    return never blocks the deck build; the offline gate is satisfied by the
    cc_register_attempted flag.

    Idempotency key is sha256(source_ref + title). FIX 57 (per-run parent
    identity): when `run_id` is supplied, source_ref (and therefore the
    idempotency key AND the card's ``Ref:`` provenance line AND the
    ``Session:`` line via external_session_id) is the RUN id, not the
    deck_slug — so two concurrent runs of the same deck each mint their OWN
    parent card instead of the server deduping the second run's parent onto
    the first run's card (the R5B §E.4 "47 of 49 children pointed at the
    first job's parent" defect). Without run_id the exact legacy deck_slug
    behavior is preserved byte-for-byte. The deck_slug is still recorded —
    in the title and, when run_id is set, folded into the description's
    provenance block — so the board stays human-readable."""
    if run_dir is None:
        return None

    # Mark the attempt FIRST — before any network call — so a crash looks
    # like transport failure (soft) rather than never-attempted (hard fail).
    if not _merge_manifest(run_dir, {"cc_register_attempted": True}):
        _log("could not stamp cc_register_attempted; continuing anyway.")

    cfg = board_config(env)
    if cfg is None:
        _log(
            "COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled "
            "(no-op); run continues ungrouped. cc_register_attempted=True logged."
        )
        return None

    # FIX 57 — per-run parent identity. With a run_id the card's source_ref
    # (its ``Ref:`` line) and external_session_id (its ``Session:`` line) are
    # BOTH the run id, so (a) the idempotency key sha256(source_ref + title)
    # is run-scoped — two concurrent runs of the same deck never collide onto
    # one parent — and (b) a child carrying Session: = run id matches its own
    # parent's Ref:, which is exactly the identity pairing the board's
    # deck_run_identity_mismatch hold checks. No run_id => legacy deck_slug
    # source_ref, byte-identical payloads.
    rid = (run_id or "").strip()
    if rid:
        source_ref = rid
    else:
        source_ref = deck_slug or "deck"
    idem_input = f"{source_ref}{title}".encode("utf-8")
    idempotency_key = hashlib.sha256(idem_input).hexdigest()

    payload: dict = {
        "title": title,
        "description": description,
        "priority": priority,
        "source": "build_deck",
        "source_ref": source_ref,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": source_ref,
        "idempotency_key": idempotency_key,
    }
    if rid and (deck_slug or "").strip() and rid != (deck_slug or "").strip():
        # Keep the deck handle visible on the run-scoped parent card without
        # touching the identity fields (Ref:/Session: stay the run id).
        payload["description"] = (
            f"{description} [deck: {deck_slug}]".strip()
        )

    rcid = (requester_chat_id or "").strip()
    rchan = (requester_channel or "").strip()
    if not rcid:
        rcid, rchan = resolve_requester(run_dir, env)
    if rcid:
        payload["requester_chat_id"] = rcid
        payload["requester_channel"] = rchan or "telegram"

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(
            f"ingest POST failed ({type(exc).__name__}: {exc}); "
            "run continues ungrouped. cc_register_attempted=True already logged."
        )
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(
            f"task {'deduped (reused)' if deduped else 'created'}: "
            f"task_id={task_id} deck_slug={deck_slug}"
        )
        # T2 gate teeth (honesty fix, 2026-08-18): the receipt carries a
        # same-file consistency tag (registration_linkage_tag over
        # cc_task_id|idempotency_key, NOT a cryptographic proof/signature -- no
        # secret is available offline for this to be a real MAC) so
        # build_deck._chk_cc_registered can spot an internally-inconsistent
        # manifest. A match is a hint only, never authorization -- anyone with
        # this source can compute a matching tag without ever calling this
        # function, so it cannot prove a real round-trip happened. Field name
        # in the stamped receipt is kept as "hmac" for backward compatibility
        # with every process_manifest.json already on disk (see
        # registration_linkage_tag()'s docstring).
        stamp_task_id(run_dir, task_id, idempotency_key=idempotency_key,
                      deck_slug=deck_slug)

        # WORK-ITEM-02: after CC card creation, dispatch the engine if it is
        # not already running. This closes the "CC ingest callback stops short"
        # gap: the intake completes, the CC card is created, and the engine
        # starts walking every manifest phase mechanically -- instead of sitting
        # dead at "Being Prepared" forever.
        _dispatch_engine_if_idle(run_dir)

        return task_id

    _log(
        f"ingest POST non-OK (HTTP {status}): {body}; "
        "run continues ungrouped. cc_register_attempted=True already logged."
    )
    return None


# ---------------------------------------------------------------------------
# CHILD CARDS (Option B) — one task card per phase, nested under the deck's
# parent task via the `parent_task_id` field on the SAME /api/tasks/ingest
# endpoint ingest_deck_task uses above. Field name and idempotency-key
# derivation (sha256(parent_task_id + ':' + stage)) match the established
# parent/child convention already live in master-orchestrator-dept/SOP-07
# (Full-Funnel epic + staged child cards) -- this is the second producer to
# mint children under that same contract, not a new one.
#
# The phase_id -> child_task_id mapping is persisted into
# process_manifest.json's cc_child_task_ids map the same way the single
# parent task_id is persisted via stamp_task_id/cc_task_id, so a resumed run
# recovers each phase's card instead of re-minting it. BoardMirror.child_report
# (board.py) is the idempotent caller: it checks this mapping (plus its
# state.json mirror) BEFORE ever invoking ingest_child_task, so a phase
# reporting progress twice never reaches this function twice.
# ---------------------------------------------------------------------------
_CHILD_MANIFEST_KEY = "cc_child_task_ids"


def read_child_task_id(run_dir, phase_id: str) -> Optional[str]:
    """process_manifest.json half of the phase_id -> child_task_id dual
    recovery (the state.json half is BoardMirror's ["board"]["children"] map,
    read by the caller directly -- mirrors task_id_anywhere's two-source
    check for the parent). Returns None on any absent/unreadable manifest or
    missing entry. Never raises."""
    children = _read_manifest(run_dir).get(_CHILD_MANIFEST_KEY)
    if isinstance(children, dict):
        val = children.get(phase_id)
        if val:
            return str(val)
    return None


def stamp_child_task_id(run_dir, phase_id: str, task_id: str) -> bool:
    """Merge {phase_id: task_id} into process_manifest.json's cc_child_task_ids
    map without disturbing any other phase already recorded there or any other
    manifest field. Atomic replace (via _merge_manifest). Returns True on
    success. Never raises."""
    if not task_id or not phase_id or run_dir is None:
        return False
    existing = _read_manifest(run_dir).get(_CHILD_MANIFEST_KEY)
    children = dict(existing) if isinstance(existing, dict) else {}
    children[phase_id] = task_id
    ok = _merge_manifest(run_dir, {_CHILD_MANIFEST_KEY: children})
    if not ok:
        _log(f"stamp_child_task_id failed for phase={phase_id} task_id={task_id}.")
    return ok


def ingest_child_task(
    run_dir,
    parent_task_id: str,
    phase_id: str,
    title: str,
    description: str,
    priority: str = "normal",
    env: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> Optional[str]:
    """Ingest (or idempotently re-fetch) a per-phase CHILD task card, nested
    under `parent_task_id` via the `parent_task_id` field on the ingest
    payload.

    Idempotency key is sha256(parent_task_id + ':' + phase_id) -- deterministic
    per (deck, phase), so a retried POST for the same phase re-fetches the
    same server-side row instead of minting a duplicate. That server-side
    guard is the SECOND line of defense; the FIRST is the caller
    (BoardMirror.child_report) checking read_child_task_id()/state and never
    calling this function at all once a child_task_id is already known.

    FIX 57 (per-run parent identity): when `run_id` is supplied it rides in
    ``external_session_id`` — the card's ``Session:`` provenance line — so
    every child of a run carries Session: = its own run's id. The board's
    deck_run_identity_mismatch hold pairs that Session: against the parent's
    ``Ref:`` (also the run id, since ingest_deck_task(run_id=...) sets
    source_ref = run_id): a child whose Session differs from its parent's Ref
    is HELD, not patched. Without run_id the legacy ``<parent>:<phase>``
    Session value is preserved byte-for-byte.

    Returns the child task_id string on success, else None. FAIL-SOFT — same
    contract as ingest_deck_task: never raises, and a None return never
    blocks the deck build. No parent_task_id => nothing to nest under => a
    clean no-op (there is no cc_register_attempted-style hard gate on a child
    card the way there is on the parent)."""
    if run_dir is None or not parent_task_id or not phase_id:
        return None

    cfg = board_config(env)
    if cfg is None:
        _log(
            "COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled "
            f"(no-op); child card for phase {phase_id} not created."
        )
        return None

    rid = (run_id or "").strip()
    source_ref = f"{parent_task_id}:{phase_id}"
    idempotency_key = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()

    payload: dict = {
        "title": title,
        "description": description,
        "priority": priority,
        "source": "build_deck_phase",
        "source_ref": source_ref,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": rid or source_ref,
        "parent_task_id": parent_task_id,
        "stage": phase_id,
        "idempotency_key": idempotency_key,
    }

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(
            f"child ingest POST failed for phase {phase_id} "
            f"({type(exc).__name__}: {exc}); run continues without a child card."
        )
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(
            f"child task {'deduped (reused)' if deduped else 'created'} for "
            f"phase {phase_id}: task_id={task_id} parent_task_id={parent_task_id}"
        )
        stamp_child_task_id(run_dir, phase_id, task_id)
        return task_id

    _log(
        f"child ingest POST non-OK for phase {phase_id} (HTTP {status}): {body}; "
        "run continues without a child card."
    )
    return None


# ---------------------------------------------------------------------------
# PATCH — advance the task card at a phase boundary.
# ---------------------------------------------------------------------------
def patch_phase(
    run_dir,
    task_id: str,
    phase_id: str,
    status: str,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """PATCH the CC task card to a task-level STATUS at a phase boundary.

    Use this for real status transitions only: the P4-RENDER START
    (backlog->in_progress) and the TERMINAL producer close of a completed deck
    (status='review'). Mid-run phase PROGRESS must go through post_activity()
    instead — a mid-run terminal status 422s the presentations cert gate.

    The producer STOPS at 'review': promotion 'review'->'done' is the CC-side QC
    scorer / Devil's-Advocate gate's job (the interlock every sibling department
    respects), never a producer self-close.

    On the terminal transitions ('review' and 'done'): automatically reads
    delivery/*-FINAL/PROCESS-CERTIFICATE.json (the sha prove-deck.py minted) and
    includes it as process_certificate_sha in the PATCH body — the cert is the
    ticket INTO review and the sha the no-skip done-gate reads on promotion. On
    'review' it ALSO folds the real per-gate QC scores (collect_qc_summary) into the
    note and a structured `qc_scores` key so the reviewer sees why the deck passed.
    The word "delivered" is NOT a status — pass it in `note`, never as `status`.

    Every attempt (disabled board, missing id, transport error, non-200, 200) is
    recorded to the movement receipt (working/checkpoints/cc-board.json) so a failed
    advance is visible. FAIL-SOFT: returns False (never raises); the deck build is
    never blocked by this function."""
    endpoint = "PATCH /api/tasks/{id}"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)",
        })
        return False
    if not task_id:
        _log("patch_phase skipped — task_id missing.")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "task_id missing",
        })
        return False

    # Build the note FIRST so a QC-summary line is folded in before the payload is
    # assembled — the note is a guaranteed-accepted CC field, so it is the summary's
    # ALWAYS-lands home even if a strict server rejects the structured qc_scores key.
    note_text = note or ""

    # TERMINAL PRODUCER CLOSE -> 'review': the presentations pipeline stops at
    # 'review' and hands promotion to 'done' to the CC-side QC scorer / Devil's-
    # Advocate gate (the same interlock every sibling department respects). Attach
    # the REAL per-gate QC scores so the reviewer sees WHY the deck is review-ready.
    qc_scores = None
    if status == "review" and run_dir is not None:
        qc_scores = collect_qc_summary(run_dir)
        _line = qc_summary_note(qc_scores)
        if _line:
            note_text = f"{note_text} — {_line}" if note_text else _line

    payload: dict = {
        "phase_id": phase_id,
        "status": status,
    }
    if note_text:
        payload["note"] = note_text

    # The PROCESS-CERTIFICATE is the ticket INTO 'review' AND the sha the CC
    # presentations no-skip done-gate reads on the eventual 'done' — so attach it on
    # BOTH terminal transitions once prove-deck.py has minted it (Fix 2a / Fix 2b).
    if status in _CERT_BEARING_STATUSES and run_dir is not None:
        cert_sha = _read_certificate_sha(run_dir)
        if cert_sha:
            payload["process_certificate_sha"] = cert_sha
            _log(f"patch_phase attaching process_certificate_sha={cert_sha[:16]}...")

    # Structured QC scores for a lenient CC server (machine-readable promotion
    # input). OPTIONAL enrichment key: if a strict server rejects it, we retry once
    # WITHOUT it so the status transition itself never strands (the human-readable
    # summary already rode in on `note`).
    if qc_scores and qc_scores.get("gates_graded"):
        payload["qc_scores"] = qc_scores

    # U030 (audit E1): route non-cert-bearing transitions around the Triad gate
    if status in _CERT_BEARING_STATUSES:
        url = f"{cfg['base_url']}/api/tasks/{task_id}"
        method = "PATCH"
        endpoint = "PATCH /api/tasks/{id}"
        body_payload = payload
    else:
        url = f"{cfg['base_url']}/api/tasks/{task_id}/status"
        method = "POST"
        endpoint = "POST /api/tasks/{id}/status"
        body_payload = {"status": status}
        _note_with_phase = f"[{phase_id}] {note_text}" if note_text else f"[{phase_id}] phase start"
        body_payload["note"] = _note_with_phase
    try:
        st, body = _request(method, url, body_payload, cfg)
        if st in (400, 422) and "qc_scores" in body_payload:
            _log(f"patch_phase {phase_id}->{status} HTTP {st} with qc_scores present "
                 "— retrying once without the structured enrichment key.")
            core = {k: v for k, v in body_payload.items() if k != "qc_scores"}
            st, body = _request(method, url, core, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_phase {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return False

    ok = st == 200
    _record_movement(run_dir, {
        "phase_id": phase_id, "kind": "status", "target": status,
        "endpoint": endpoint, "http_status": st, "ok": ok,
        "detail": "OK" if ok else str(body)[:300],
    })
    if ok:
        _log(f"patch_phase {phase_id}->{status} OK (task_id={task_id}).")
        return True

    _log(f"patch_phase {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    return False


def _activity_score_tail(gate: dict) -> str:
    """Compact per-gate score tail for a QC activity message, e.g.
    'avg=9.1 pass=true autofails=0'. '' for a non-dict. Never raises."""
    if not isinstance(gate, dict):
        return ""
    avg = gate.get("average")
    return (f"avg={avg if avg is not None else '?'} "
            f"pass={str(gate.get('pass') is True).lower()} "
            f"autofails={gate.get('autofails_count', 0)}").strip()


def post_activity(
    run_dir,
    task_id: str,
    phase_id: str,
    note: str,
    activity_type: str = "updated",
    scores: Optional[dict] = None,
    env: Optional[dict] = None,
) -> bool:
    """POST a mid-run phase-PROGRESS activity to /api/tasks/{task_id}/activities.

    This is how P4-RENDER-complete and P8-ASSEMBLE-complete are recorded — as
    ACTIVITIES, NOT task-level status changes. A mid-run status='done' would 422 the
    presentations cert done-gate (no PROCESS-CERTIFICATE exists mid-run) and would
    wrongly close a non-presentation card; an activity carries the phase in its
    message without touching the card's column.

    Body matches the CC CreateActivitySchema: activity_type in
    {spawned,updated,completed,file_created,status_changed} + a non-empty message
    (the phase id is embedded in the message for human readers) + structured
    ``metadata = {"phase_id": phase_id}``. The metadata field is what the U060 phase
    reducer (computePhaseProgress / phaseIdOf in src/lib/presentation-phases.ts)
    reads to advance the stepper — the phase id in the message text is NOT seen by
    the reducer. Every attempt is recorded to the movement receipt. FAIL-SOFT:
    returns False (never raises)."""
    endpoint = "POST /api/tasks/{id}/activities"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)",
        })
        return False
    if not task_id:
        _log("post_activity skipped — task_id missing.")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "task_id missing",
        })
        return False

    message = (f"[{phase_id}] {note}".strip() if note else f"[{phase_id}]")
    payload: dict = {
        "activity_type": activity_type,
        "message": message,
        # Structured phase id for the U060 phase reducer
        # (computePhaseProgress / phaseIdOf in src/lib/presentation-phases.ts reads
        # task_activities.metadata.phase_id). The phase MUST ride in metadata, not
        # just the message text — the reducer ignores message content entirely, so a
        # phase id only in the message never advances the stepper.
        "metadata": {"phase_id": phase_id},
    }
    # OPTIONAL structured QC scores on a per-gate QC activity: fold a compact score
    # tail into the (always-accepted) message AND attach the structured `scores` key
    # for a lenient CC. A strict server that 422s the unknown key gets a one-shot
    # retry without it — the message tail still carries the numbers.
    if scores:
        _tail = _activity_score_tail(scores)
        if _tail:
            payload["message"] = f"{message} {_tail}".strip()
        payload["scores"] = scores

    url = f"{cfg['base_url']}/api/tasks/{task_id}/activities"
    try:
        st, body = _request("POST", url, payload, cfg)
        if st in (400, 422) and ("scores" in payload or "metadata" in payload):
            _log(f"post_activity {phase_id} HTTP {st} with structured enrichment "
                 "present — retrying once without the structured keys "
                 "(scores/metadata); the phase id still rides in the message.")
            core = {k: v for k, v in payload.items() if k not in ("scores", "metadata")}
            st, body = _request("POST", url, core, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"post_activity {phase_id} failed ({type(exc).__name__}: {exc}).")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return False

    ok = st in (200, 201)
    _record_movement(run_dir, {
        "phase_id": phase_id, "kind": "activity", "target": activity_type,
        "endpoint": endpoint, "http_status": st, "ok": ok,
        "detail": "OK" if ok else str(body)[:300],
    })
    if ok:
        _log(f"post_activity {phase_id} OK (task_id={task_id}).")
        return True

    _log(f"post_activity {phase_id} non-OK (HTTP {st}): {body}.")
    return False


def post_qc_activities(run_dir, task_id: str, env: Optional[dict] = None) -> int:
    """Post ONE phase-progress activity per graded QC gate, each carrying the real
    {gate, average, pass, autofails_count} (via post_activity's `scores`). The board's
    activity feed then shows every QC phase's ACTUAL grade — not just a phase
    breadcrumb + a cert hash. Reads the reports through collect_qc_summary.

    Intended to fire at the terminal close (right before the 'review' PATCH) so all
    five reports already exist on disk. FAIL-SOFT: returns the number of activities
    that posted OK (0 on a disabled board / no reports / any failure); never raises —
    the board is a view, never a gate."""
    posted = 0
    try:
        summary = collect_qc_summary(run_dir)
        for gate in summary.get("gates", []):
            if not isinstance(gate, dict):
                continue
            phase_label = gate.get("gate") or gate.get("report") or "QC"
            if post_activity(run_dir, task_id, f"QC:{phase_label}",
                             "governed QC grade", scores=gate, env=env):
                posted += 1
    except Exception as exc:  # noqa: BLE001 — the board is a view, never a gate
        _log(f"post_qc_activities raised ({exc}) — non-fatal.")
    return posted


def _read_certificate_sha(run_dir) -> Optional[str]:
    """Glob delivery/*-FINAL/PROCESS-CERTIFICATE.json and return the first
    certificate_sha found, or None. Never raises."""
    try:
        delivery = Path(run_dir) / "delivery"
        if not delivery.is_dir():
            return None
        for cert_path in delivery.glob("*-FINAL/PROCESS-CERTIFICATE.json"):
            try:
                data = json.loads(cert_path.read_text())
                if isinstance(data, dict) and data.get("certificate_sha"):
                    return str(data["certificate_sha"])
            except (json.JSONDecodeError, OSError):
                continue
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Receipt stamping — write task_id into process_manifest.json so the offline
# AF-CC-UNREGISTERED check passes (degrade-to-ungrouped is logged, not
# silent). Mirrors Skill-48's stamp_campaign_id pattern at cc_board.py:370-401.
# ---------------------------------------------------------------------------
def registration_linkage_tag(task_id: str, idempotency_key: str, deck_slug: str) -> Optional[dict]:
    """Build a same-file CONSISTENCY TAG for the closeout gate
    (build_deck._chk_cc_registered) to spot-check offline. This is NOT a
    cryptographic proof and NOT a signature, despite this function's former
    name (``registration_proof``) claiming otherwise — renamed 2026-08-18
    (fakehmac honesty fix) because that naming overclaimed a security property
    this value cannot provide.

    WHAT THIS IS: ``hmac.new(canonical, b"", hashlib.sha256).hexdigest()``
    where ``canonical = cc_task_id + "|" + idempotency_key`` — stored under
    the dict key ``"hmac"`` in the SAME process_manifest.json as the
    ``cc_task_id`` and ``idempotency_key`` it was computed from. It is
    deterministic and it catches ACCIDENTAL inconsistency: a ``cc_task_id``
    string copied into a manifest without its matching
    ``idempotency_key``/``deck_slug``, a partially-applied hand-edit, or
    truncated/corrupted field writes.

    WHAT THIS IS NOT: a genuine MAC needs a key the verifier can check but a
    forger cannot produce — i.e. an actual SECRET. This construction has no
    secret: ``canonical`` (used here as the HMAC *key*, over an EMPTY
    message) is fully attacker/author-computable, since both of its inputs
    are visible in the very manifest file the tag is stored in.
    ``idempotency_key`` is ``sha256(source_ref + title)`` — derived from data
    the manifest's author already knows, not a server-issued token — and this
    function itself ships in the repo (it is not secret). Anyone who can
    write process_manifest.json can read this code and compute a matching tag
    for ANY task_id/idempotency_key/deck_slug triple of their own choosing,
    without ever calling cc_board.ingest_deck_task or touching the network.

    A MATCH therefore proves only that these three fields are internally
    consistent with each other IN THIS FILE. It is NOT evidence that a live
    Command Center round-trip occurred. No caller may treat a match as
    authorization or as cryptographic proof of anything — it is a hint /
    staleness-and-typo guard only. No env-provided secret is available to the
    offline gate that reads this (by design: zero network/env dependency), so
    a real MAC is not achievable in this code path; see this module's
    WEBHOOK_SECRET-signed outbound requests for what an actual keyed
    signature looks like when a real secret IS available.

    WIRE FORMAT / BACKWARD COMPATIBILITY: the returned dict key is
    deliberately left as ``"hmac"`` (not renamed to something like ``"tag"``)
    and the digest computation is deliberately left byte-for-byte unchanged
    from the pre-2026-08-18 implementation. Every process_manifest.json
    already stamped by production — and every one stamped going forward —
    uses the exact same field name and formula, so there is no legacy/new
    format split for the reader to reconcile and no receipt in flight is
    ever invalidated by this rename. Only the SYMBOL name and the
    documentation changed; the on-disk contract did not.

    Deterministic (no timestamp, no secret) so the offline gate is hermetic:
    same inputs -> same digest, forever, with zero env or network dependency.
    None when any input is empty (a malformed receipt proves nothing at all,
    not even self-consistency)."""
    tid = (task_id or "").strip()
    key = (idempotency_key or "").strip()
    slug = (deck_slug or "").strip()
    if not tid or not key or not slug:
        return None
    canonical = f"{tid}|{key}"
    digest = hmac.new(canonical.encode("utf-8"), b"", hashlib.sha256).hexdigest()
    return {
        "task_id": tid,
        "idempotency_key": key,
        "deck_slug": slug,
        "hmac": digest,
    }


# Deprecated alias — kept so any external caller still importing the old
# symbol name does not break. Prefer registration_linkage_tag(); the old name
# claimed a security property ("proof") this value never had.
registration_proof = registration_linkage_tag


def stamp_task_id(run_dir, task_id: str, idempotency_key: str = "",
                  deck_slug: str = "") -> bool:
    """Merge cc_task_id into process_manifest.json without disturbing other
    fields. Atomic replace. Returns True on success. Never raises.

    When idempotency_key is supplied (the ingest round-trip path), ALSO stamps
    ``cc_registration`` — a same-file consistency tag (registration_linkage_tag;
    NOT a cryptographic proof — see its docstring) — so
    build_deck._chk_cc_registered can distinguish a task_id whose accompanying
    fields are internally consistent from a bare task_id with no tag at all.
    Neither state is a security guarantee: a consistent tag is trivially
    reproducible by anyone with the source, so treat it strictly as a hint,
    never as authorization. The plain cc_task_id merge remains for backward
    compatibility: callers that only have an id (e.g. a runner re-stamping a
    recovered id) still write the id without a tag, and the gate treats that
    as UNVERIFIED, never as verified."""
    if not task_id or run_dir is None:
        return False
    updates: dict = {"cc_task_id": task_id}
    linkage = registration_linkage_tag(task_id, idempotency_key, deck_slug)
    if linkage is not None:
        updates["cc_registration"] = linkage
    ok = _merge_manifest(run_dir, updates)
    if not ok:
        _log(f"stamp_task_id failed for task_id={task_id}.")
    return ok


# ---------------------------------------------------------------------------
# DELIVERABLE REGISTRATION — POST /api/tasks/{id}/deliverables (FIX-12).
#
# The producer-side registration bridge (ported from Skill-06's
# register_deliverable at 06-ghl-install-pages/tools/cc_board.py). M11 in
# ERRORS-DETECTED: the dept cc_board.py had NO register_deliverable, so a
# completed deck was never registered and its task could never leave
# in_progress. POST a 2xx -> the CC server inserts a task_deliverables row ->
# the task is registerable and may advance. The CC route validates against
# CreateDeliverableSchema (deliverable_type enum file|url|artifact|image +
# non-empty title; optional path/description) — it does NOT accept a bare
# `url` or `meta` key, so the payload carries deliverable_type='url' +
# title + path (the artifact URL), with meta folded into `description`.
# FAIL-SOFT: never raises; a False return (board disabled, missing id/url,
# transport error, non-2xx) never blocks the deck build.
# ---------------------------------------------------------------------------
def register_deliverable(
    task_id: str,
    url: str,
    meta: Optional[dict] = None,
    *,
    env: Optional[dict] = None,
) -> bool:
    """Register a built artifact via ``POST /api/tasks/{id}/deliverables``.

    Auth: both headers (Bearer + HMAC) per this module's AUTH PARITY rules —
    the same signed _request() every other advance uses. If the /deliverables
    endpoint is absent (404) the call fail-softs and the build continues
    unregistered (the deck's task_id is still on disk via stamp_task_id).

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id: CC task UUID returned by ingest_deck_task (or read from the
                 process_manifest cc_task_id).
        url:     The built artifact URL (e.g. the deck/guide location) to
                 register on the card.
        meta:    Optional metadata dict (e.g. {"type": "deck_pptx",
                 "title": "My Deck", "slug": "deck-1"}). A title found here
                 becomes the deliverable title; the rest rides in description.
        env:     Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure (including 404 if endpoint absent).
    """
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — board disabled; "
             "deliverable not registered.")
        return False

    tid = (task_id or "").strip()
    if not tid:
        _log("register_deliverable skipped — empty task_id.")
        return False

    artifact_url = (url or "").strip()
    if not artifact_url:
        _log("register_deliverable skipped — empty url.")
        return False

    # The CC server's POST /api/tasks/{id}/deliverables validates against the
    # CreateDeliverableSchema (deliverable_type enum file|url|artifact|image +
    # a non-empty title, optional path/description) — it does NOT accept a
    # bare `url` or `meta` key, so the old {"url": ..., "meta": ...} shape 400s.
    title = "Artifact URL"
    if meta and isinstance(meta, dict):
        for _key in ("title", "slug", "type"):
            _val = meta.get(_key)
            if _val:
                title = str(_val)
                break

    payload: dict = {
        "deliverable_type": "url",
        "title": title,
        "path": artifact_url,
    }
    if meta and isinstance(meta, dict):
        # Fold the metadata into `description` (JSON) so nothing is lost — the
        # schema has no `meta` field to carry it.
        payload["description"] = json.dumps(meta, separators=(",", ":"))

    endpoint = f"{cfg['base_url']}/api/tasks/{tid}/deliverables"
    try:
        http_status, body = _request("POST", endpoint, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(
            f"POST {endpoint} failed ({type(exc).__name__}: {exc}); "
            "deliverable not registered; build continues."
        )
        return False

    if 200 <= http_status < 300:
        _log(f"task {tid} deliverable registered: url={artifact_url!r} "
             f"http={http_status}.")
        return True

    _log(
        f"POST /deliverables non-2xx (HTTP {http_status}) for task {tid}: "
        f"{body}; build continues. If 404, confirm /deliverables endpoint in "
        "blackceo-command-center."
    )
    return False


# ---------------------------------------------------------------------------
# DELIVERABLES REGISTRATION (plural) — FIX 7 engine close path.
#
# register_deliverable() above posts ONE file. The engine's close() (Fix 7
# HOW: "cc_board.register_deliverables() for all ten files") needs the
# curated flat deliverables/ folder registered on the parent card so the
# task can leave in_progress. This wrapper walks the curated folder (the
# flat run_dir/deliverables/ set curate.py assembled, standardized
# destination names from presentation_job.deliverables.DESTINATION_FILENAMES
# when importable, else whatever the folder holds) and posts each file,
# FAIL-SOFT per file: one bad registration never stops the rest and never
# blocks the close. Returns the number of deliverables registered 2xx.
# ---------------------------------------------------------------------------
def register_deliverables(
    task_id: str,
    run_dir,
    *,
    env: Optional[dict] = None,
    deck_slug: str = "",
) -> int:
    """Register every file in the run's flat deliverables/ folder on the
    parent card via register_deliverable, one POST per file.

    Reads run_dir/deliverables/ (curate.py's output). Files that cannot be
    read or post non-2xx are logged and skipped; a disabled board or a
    missing folder registers nothing. FAIL-SOFT: never raises; the count
    returned is informational, never a gate."""
    if run_dir is None:
        return 0
    deliv_dir = Path(run_dir) / "deliverables"
    if not deliv_dir.is_dir():
        _log(f"register_deliverables: no {deliv_dir} — nothing to register.")
        return 0
    try:
        paths = sorted(p for p in deliv_dir.iterdir() if p.is_file())
    except OSError as exc:
        _log(f"register_deliverables: could not list {deliv_dir} ({exc}).")
        return 0
    if not paths:
        _log("register_deliverables: deliverables/ is empty — nothing to register.")
        return 0

    slug = (deck_slug or "").strip()
    registered = 0
    for path in paths:
        name = path.name
        # A human title from the standardized name: DECK-FINAL.pptx ->
        # "deck (DECK-FINAL.pptx)"-style is overkill; the filename IS the
        # board-readable label. Fold the size in so the reviewer sees mass.
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        meta = {
            "type": "deck_deliverable",
            "title": name,
            "size_bytes": size,
        }
        if slug:
            meta["slug"] = slug
        if register_deliverable(task_id, path.resolve().as_uri(), meta=meta, env=env):
            registered += 1
    _log(f"register_deliverables: {registered}/{len(paths)} deliverable(s) "
         f"registered on task {task_id}.")
    return registered


# ---------------------------------------------------------------------------
# OWNER-MESSAGE ORACLE — the authoritative owner-approval check (FIX-1).
#
# A phase-skip approval is authentic ONLY when its owner_msg_id resolves to a
# REAL owner-authored message row in the Command Center task_activities table.
# Presence of a string in phase_skip_approvals.json is NEVER proof — the live
# E2E forged "e2e-test-002". This client is the fail-closed oracle: when the
# owner-ids endpoint is unreachable or the task is unknown, the check returns
# None (UNDETERMINED), which the caller treats as DENIED — undetermined never
# opens the gate. See the CC route GET /api/tasks/[id]/messages/owner-ids.
# ---------------------------------------------------------------------------
def list_owner_message_ids(task_id: str, env: Optional[dict] = None) -> Optional[frozenset]:
    """Resolve `task_id` to the set of REAL owner-authored message ids in CC
    task_activities. Returns a frozenset of ids on success; None when the board
    is disabled, the endpoint errors, or the result cannot be proven (the caller
    must fail CLOSED on None — a skip that cannot be verified is DENIED)."""
    if not task_id or not str(task_id).strip():
        return None
    cfg = board_config(env)
    if cfg is None:
        return None
    tid = urllib.parse.quote(str(task_id).strip(), safe="")
    url = f"{cfg['base_url']}/api/tasks/{tid}/messages/owner-ids"
    try:
        status, parsed = _request("GET", url, {}, cfg)
    except Exception:  # noqa: BLE001 — fail-closed: a transport error is DENIED
        _log(f"owner-message oracle {url} raised; owner approval treated as DENIED.")
        return None
    if status != 200 or not isinstance(parsed, list):
        _log(f"owner-message oracle {url} returned HTTP {status} — owner approval "
             "treated as DENIED (undetermined never opens the gate).")
        return None
    ids = set()
    for item in parsed:
        if isinstance(item, str) and item.strip():
            ids.add(item.strip())
        elif isinstance(item, dict):
            v = item.get("id")
            if isinstance(v, str) and v.strip():
                ids.add(v.strip())
    return frozenset(ids)


def owner_message_ids_match(run_dir, task_id: str, env: Optional[dict] = None) -> Optional[frozenset]:
    """Compatibility helper: resolve the CC task id from the run's
    process_manifest.json (cc_task_id) and return its real owner-message ids.
    None when the run has no cc_task_id or the oracle cannot resolve — fail-closed.
    Delegates to list_owner_message_ids so there is ONE oracle implementation."""
    if run_dir is not None:
        tid = _read_manifest(run_dir).get("cc_task_id")
        if tid:
            return list_owner_message_ids(str(tid), env=env)
    return None


# ---------------------------------------------------------------------------
# RECONCILE — replay the last failed board advance (FIX-PRES-08b).
# ---------------------------------------------------------------------------
def reconcile(run_dir) -> int:
    """Replay the LAST outstanding failed board advance from the movement receipt
    (working/checkpoints/cc-board.json).

    WHY: a transport-failed TERMINAL close (run_signature_deck._board_close_delivery
    is fail-soft) otherwise leaves a delivered deck's card stuck at in_progress
    forever, with no retry. This reads cc_task_id from the manifest and the last
    ok:false STATUS movement that was NOT superseded by a later OK, and re-issues
    that patch_phase (which, for status='done', re-attaches the process_certificate_sha).

    Returns 0 on success or a clean no-op (nothing to reconcile / board consistent /
    board disabled), 1 when a replay was attempted but still failed. FAIL-SOFT:
    never raises — the board is a view, never a gate."""
    try:
        tid = _read_manifest(run_dir).get("cc_task_id")
        if not tid:
            _log("reconcile: no cc_task_id in manifest — nothing to reconcile.")
            return 0
        p = _movements_path(run_dir)
        if not p.exists():
            _log("reconcile: no movement receipt — nothing to reconcile.")
            return 0
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            _log("reconcile: movement receipt unreadable — nothing to reconcile.")
            return 0
        movements = data.get("movements") if isinstance(data, dict) else None
        if not isinstance(movements, list) or not movements:
            _log("reconcile: empty movement receipt — nothing to reconcile.")
            return 0
        # Walk in order: a later OK status advance supersedes an earlier failure.
        last_failed = None
        for m in movements:
            if not isinstance(m, dict) or m.get("kind") != "status":
                continue
            if m.get("ok"):
                last_failed = None
            else:
                last_failed = m
        if last_failed is None:
            _log("reconcile: no outstanding failed status advance — board is consistent.")
            return 0
        phase_id = last_failed.get("phase_id")
        status = last_failed.get("target") or last_failed.get("status")
        if not phase_id or not status:
            _log("reconcile: last failed movement missing phase_id/status — cannot replay.")
            return 0
        _log(f"reconcile: replaying failed advance {phase_id}->{status} (task_id={tid}).")
        ok = patch_phase(
            run_dir, str(tid), str(phase_id), str(status),
            note="reconcile: replay of a transport-failed advance",
        )
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001 — reconcile is best-effort, never a gate
        _log(f"reconcile raised ({exc}) — non-fatal.")
        return 0


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser(
        description="Presentations Command Center board helper (fail-soft).")
    _ap.add_argument(
        "--reconcile", metavar="RUN_DIR",
        help="Replay the last failed board advance from RUN_DIR's movement receipt "
             "(FIX-PRES-08b). Exit 0 = success/clean no-op, 1 = replay still failed.")
    _args = _ap.parse_args()
    if _args.reconcile:
        sys.exit(reconcile(_args.reconcile))
    _ap.print_help()
    sys.exit(0)
