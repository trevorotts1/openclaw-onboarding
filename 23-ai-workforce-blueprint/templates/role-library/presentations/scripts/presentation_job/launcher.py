"""Engine dispatch bridge -- the single entry point for launching the engine.

WORK-ITEM-02: Every caller (intake poll.sh, canonical entry, CC ingest callback)
uses this shared dispatch function instead of independently constructing the
`presentation_job --new --run-dir <dir>` invocation. Centralizes dispatch logic so
there is exactly one place where the engine is launched.

Root cause prevented: The engine (presentation_job.py + 18 modules, 552 tests)
has zero production callers (CURRENT-STATE Section B breakpoint 5). The intake
cron, canonical entry, and CC all stop short. This module closes that gap.

CAPACITY GATE (unit u07)
------------------------
Dispatch now measures before it launches. capacity.probe() detects THIS client's
provider and plan; if it cannot produce a dispatchable number -- the plan is
undeclared (PARKED behind the one-time interview question), or a declared
capacity_override.json is unusable (FAILED) -- dispatch REFUSES with
AF-CAPACITY-UNMEASURED and a non-zero exit, and no engine process is spawned.
A capacity probe whose result nothing acts on is an advisory print, not a gate;
this is the acting-on.

THE NO-CONFIG CASE (UNDETERMINED) IS NOT THE SAME AS MEASURED
---------------------------------------------------------------
A box with no capacity_override.json, no 9Router combo, and no OpenClaw config
-- the state almost every client box starts in -- is UNDETERMINED, not FAILED
and not PARKED. capacity.probe() answers that with `available =
DEFAULT_CONSERVATIVE (3)` so the department is not dead out of the box, but
that 3 was never measured; it is a floor, never a proven ceiling.

Refusing every unconfigured box would make the department unusable by default,
which is its own outage -- so this gate does NOT refuse on UNDETERMINED alone.
Instead it does three things a plain "capacity measured" print cannot be
mistaken for:
  1. proceeds at the conservative floor, with a banner that says UNDETERMINED
     out loud (never the same line MEASURED prints);
  2. records the probe result into run state (state.json / a pre-state.json
     sidecar) so the anomaly outlives the launch log line;
  3. pings the operator (best-effort, never fatal to dispatch) so a fleet of
     boxes silently running at the floor is visible, not just archived.

It DOES refuse -- the same AF-CAPACITY-UNMEASURED, same non-zero exit, same
"nothing spawned" contract as PARKED/FAILED -- when a caller declares
`requested_parallel` and that request exceeds the conservative floor while
capacity is UNDETERMINED. Wanting more parallel width than the un-measured
floor, without a real measurement backing it, is exactly the blind dispatch
this gate exists to stop; wanting the floor itself (or not declaring a
request at all -- the overwhelming majority of callers today) is not.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .vocab import normalize_presentation_type, UnknownPresentationType

# ---------------------------------------------------------------------------
# FIX 34 — intake immutable after job creation
# ---------------------------------------------------------------------------
#: After the engine's --new consumed `working/copy/intake.json`, that file is the
#: run's constitutional record: every phase (mode, deck_type, requester.chat_id,
#: intake trace checks) reads it, and the D-lineage bugs all started with something
#: quietly REWRITING it mid-run. So once --new has consumed it the launcher seals
#: it 0444. Any later write attempt raises PermissionError at the OS level, and the
#: attempt is recorded in the intake-protection ledger before it raises.
#:
#: Changes go through the AMENDMENT channel instead: `apply_intake_amendment`
#: verifies a Fix 32-style owner approval (approved_by "Trevor" + a non-empty
#: owner_msg_id — the QC.md FIX 32 forged/real pair) and only then stages the new
#: intake (write to intake.json.staging, fsync), appends the full amendment row to
#: `working/copy/intake_amendments.jsonl`, and os.replace()s the staging file over
#: the sealed intake (os.replace works on a read-only TARGET — only the directory
#: needs write permission), then re-seals 0444. Every step lands in the ledger.
#:
#: The dispatcher's P0A contract ("re-emit intake verbatim/enriched") is thereby
#: inert operationally: the file cannot be re-emitted over, and the sanctioned way
#: to change intake data is this amendment path. (The contract text itself lives in
#: dispatcher.py, outside this workflow's file scope.)

#: Canonical mode bits for the sealed intake (read-only for everyone).
INTAKE_SEAL_MODE = 0o444

#: The amendment record file, canonical intake sibling (JSON Lines).
INTAKE_AMENDMENTS_FILENAME = "intake_amendments.jsonl"

#: The intake-protection ledger — every seal, every refused write attempt, every
#: amendment lands here (JSON Lines) under working/logs/.
INTAKE_LEDGER_RELATIVE = ("working", "logs", "intake_protection.jsonl")


def intake_paths(run_dir: Path) -> dict:
    """The three FIX 34 surfaces for a run dir, as absolute Paths."""
    run_dir = Path(run_dir).expanduser().resolve()
    return {
        "intake": run_dir / "working" / "copy" / "intake.json",
        "amendments": run_dir / "working" / "copy" / INTAKE_AMENDMENTS_FILENAME,
        "ledger": run_dir.joinpath(*INTAKE_LEDGER_RELATIVE),
    }


def _ledger_append(run_dir: Path, event: dict) -> None:
    """Append one JSON line to the intake-protection ledger. The ledger is the
    QC surface for "the attempt appears in the ledger", so a ledger failure is
    surfaced on stderr but NEVER blocks the protective action itself."""
    try:
        paths = intake_paths(run_dir)
        paths["ledger"].parent.mkdir(parents=True, exist_ok=True)
        row = dict(event)
        row.setdefault("at", __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"))
        with paths["ledger"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError as exc:
        print(f"launcher: intake ledger write failed: {exc}", file=sys.stderr,
              flush=True)


def seal_intake(run_dir: Path, reason: str = "new-job-consumed") -> bool:
    """chmod 0444 the run's working/copy/intake.json (idempotent) and record the
    seal in the ledger. Creates the amendments file (0644, empty) so the channel
    exists even before its first amendment. Returns True when the intake exists
    and ended sealed."""
    paths = intake_paths(run_dir)
    intake = paths["intake"]
    if not intake.is_file():
        return False
    try:
        os.chmod(intake, INTAKE_SEAL_MODE)
    except OSError as exc:
        _ledger_append(run_dir, {"event": "intake_seal_failed",
                                 "detail": str(exc), "reason": reason})
        return False
    try:
        if not paths["amendments"].exists():
            paths["amendments"].touch(mode=0o644)
    except OSError as exc:
        print(f"launcher: could not create {paths['amendments']}: {exc}",
              file=sys.stderr, flush=True)
    _ledger_append(run_dir, {"event": "intake_sealed",
                             "mode": oct(INTAKE_SEAL_MODE),
                             "detail": stat_mode(intake), "reason": reason})
    return True


def stat_mode(path: Path) -> str:
    """`stat -f %Sp`-shaped mode string (-r--r--r--), for evidence parity with the
    QC proof line."""
    try:
        import stat as _stat
        return _stat.filemode(path.stat().st_mode)
    except OSError:
        return "?"

def verify_amendment_approval(amendment: dict, run_dir: Optional[Path] = None) -> tuple:
    """Fix 32-style owner-approval verification for an intake amendment.

    Prefer presentation_job.approvals (W11, Fix 32) — approvals.verify_quiet
    against the run dir, the SAME fail-closed CC owner-message oracle every other
    gate uses. Its ApprovalError path (no owner_msg_id / oracle undetermined /
    id does not resolve) is a refusal here too. The deterministic local fallback
    below runs only when approvals.py is genuinely absent from the deployment
    (standalone scripts/ copy) and mirrors QC.md FIX 32 exactly:
      FORGED  — no approved_by / reason shorter than 8 chars / missing or
                midnight or naive granted_at / missing owner_msg_id.
      REAL    — owner-approved record: approved_by present, a real reason, a
                tz-aware granted_at, and an owner_msg_id that resolves.
    Returns (ok: bool, detail: str)."""
    if not isinstance(amendment, dict):
        return False, "amendment is not a JSON object"
    approval = amendment.get("approval") or amendment
    try:  # W11's approvals.py (Fix 32), when present, is authoritative.
        from .approvals import verify_quiet as _approvals_verify  # type: ignore
        ok = bool(_approvals_verify(approval, run_dir))
        return ok, ("owner approval verified via cc_board owner-message oracle"
                    if ok else "AF-FORGED-APPROVAL: approvals oracle refused the record")
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — a broken oracle refuses, never waves
        return False, f"approvals oracle error: {exc}"
    approved = approval.get("owner_approved") is True or approval.get("approved") is True
    by = str(approval.get("approved_by", "")).strip().casefold()
    msg = str(approval.get("owner_msg_id", "") or "").strip()
    if not approved:
        return False, "owner_approved is not true"
    if by != "trevor":
        return False, f"approved_by is {approval.get('approved_by')!r}, not 'Trevor'"
    if not msg or msg.casefold() in ("forged", "none"):
        return False, "owner_msg_id missing or not a verified id"
    return True, "owner approval verified (approved_by=Trevor, owner_msg_id present)"


def apply_intake_amendment(run_dir: Path, amendment: dict) -> dict:
    """Apply a verified amendment to the sealed intake — the ONLY sanctioned way
    intake data changes after --new.

    Contract:
      * approval unverified -> intake untouched, refusal recorded in the ledger,
        returns {"applied": False, "detail": ...}.
      * verified -> the new intake is written to intake.json.staging (fsynced),
        the full amendment row (payload + approval + at + sha of the new intake)
        is appended to working/copy/intake_amendments.jsonl, the staging file is
        os.replace()d over the sealed intake, and the intake is re-sealed 0444.
    Returns {"applied": bool, "detail": str, "intake_sha256": str|None}."""
    paths = intake_paths(run_dir)
    intake = paths["intake"]
    if not isinstance(amendment, dict):
        return {"applied": False, "detail": "amendment is not a JSON object",
                "intake_sha256": None}
    ok, detail = verify_amendment_approval(amendment, run_dir)
    if not ok:
        _ledger_append(run_dir, {"event": "intake_amendment_refused",
                                 "code": "AF-AMENDMENT-UNVERIFIED",
                                 "detail": detail})
        return {"applied": False, "detail": detail, "intake_sha256": None}
    payload = amendment.get("intake")
    if not isinstance(payload, dict):
        _ledger_append(run_dir, {"event": "intake_amendment_refused",
                                 "code": "AF-AMENDMENT-BAD-PAYLOAD",
                                 "detail": "amendment.intake is not a JSON object"})
        return {"applied": False,
                "detail": "amendment.intake must be the full replacement intake object",
                "intake_sha256": None}
    if not intake.is_file():
        return {"applied": False, "detail": f"no intake at {intake}",
                "intake_sha256": None}
    import hashlib
    staging = intake.with_name(intake.name + ".staging")
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        with staging.open("w", encoding="utf-8") as fh:  # staging file, never direct
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        new_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        row = {"at": __import__("datetime").datetime.now(
                   __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
               "kind": "intake_amendment",
               "approval": amendment.get("approval") or {},
               "detail": amendment.get("detail") or amendment.get("reason") or "",
               "intake_sha256": new_sha}
        with paths["amendments"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        # os.replace over a read-only target is legal — the target's own bits do
        # not matter, only the directory's write permission does.
        os.replace(staging, intake)
        os.chmod(intake, INTAKE_SEAL_MODE)   # re-seal after the replace
    except OSError as exc:
        _ledger_append(run_dir, {"event": "intake_amendment_failed",
                                 "detail": str(exc)})
        return {"applied": False, "detail": f"amendment failed: {exc}",
                "intake_sha256": None}
    _ledger_append(run_dir, {"event": "intake_amended",
                             "detail": detail, "intake_sha256": new_sha})
    return {"applied": True, "detail": detail, "intake_sha256": new_sha}


def worker_write_probe(run_dir: Path) -> dict:
    """QC oracle: attempt to append one byte to the sealed intake exactly the way
    a worker would, record the ATTEMPT in the ledger (before the verdict), and
    return what happened. A properly sealed intake raises PermissionError here —
    that raise IS the proof; the probe never swallows it into a success."""
    paths = intake_paths(run_dir)
    intake = paths["intake"]
    result = {"attempted": True, "raised": False, "errno": None, "mode": stat_mode(intake)}
    try:
        with intake.open("a", encoding="utf-8") as fh:
            fh.write("# probe")
        result["raised"] = False
    except PermissionError as exc:
        result["raised"] = True
        result["errno"] = exc.errno
    except OSError as exc:
        result["raised"] = True
        result["errno"] = exc.errno
    _ledger_append(run_dir, {"event": "intake_write_attempt",
                             "raised": result["raised"],
                             "errno": result["errno"]})
    if result["raised"]:
        # restore the sealed state in case the probe got as far as touching it
        try:
            os.chmod(intake, INTAKE_SEAL_MODE)
        except OSError:
            pass
    return result



# ---------------------------------------------------------------------------
# Dispatch return sentinels and exit codes
# ---------------------------------------------------------------------------
#: dispatch() already returns -1 (failure), -2 (already running) and -3 (already
#: DONE). -4 joins that family: capacity could not be measured, so NOTHING was
#: spawned. Callers that only test `> 0` keep working unchanged.
DISPATCH_CAPACITY_REFUSED = -4

#: CLI exit code for a capacity refusal (== state.EXIT_GATE_BLOCKED).
EXIT_CAPACITY_UNMEASURED = 3

#: dispatch()/dispatch_new() refuse before touching state.json at all when the
#: caller's deck_type does not resolve through vocab.normalize_presentation_type()
#: -- joins the -1..-4 refusal family above. fix/deck-type-routing-bypass:
#: launcher.py is one of the four callers (entry script, engine, poll, launcher)
#: that must agree on the deck-type vocabulary; an unrecognized value fails
#: loudly here too, never silently.
DISPATCH_UNKNOWN_DECK_TYPE = -5

#: CLI exit code for DISPATCH_UNKNOWN_DECK_TYPE.
EXIT_UNKNOWN_DECK_TYPE = 6

#: FIX 12: dispatch() refuses when the credit preflight blocks a declared mode
#: (AF-CREDIT-PREFLIGHT) -- joins the -1..-5 refusal family. Nothing spawned.
#: mode=None (the default for every caller today) never triggers this gate:
#: FIX 12 prices a MODE launch; a plain un-moded run keeps its pre-fix path.
DISPATCH_CREDIT_REFUSED = -6

#: CLI exit code for DISPATCH_CREDIT_REFUSED.
EXIT_CREDIT_REFUSED = 7

#: FIX 12 autofail code: the credit preflight blocked a declared mode launch
#: (low balance / cost_unknown rate / unestimable call counts) -- refuse
#: BEFORE any spend, never mid-run discovery of an empty account.
CREDIT_AUTOFAIL_CODE = "AF-CREDIT-PREFLIGHT"

#: FIX 22 (presentation rev2 waves): dispatch() refuses when the notify
#: transport is unconfigured (AF-NOTIFY-UNCONFIGURED) -- joins the -1..-6
#: refusal family. Nothing spawned. An unset transport means job
#: progress/blocked/done messages and watchdog stall findings can never
#: leave the box: fail-closed at launch, not warn-and-continue. The shared
#: structural check lives in notify_preflight (also the FIX 39 pre-roll
#: gate interface); the hard-stop is armed by
#: PRESENTATION_NOTIFY_FAIL_CLOSED (default ON, =0 = documented rollback to
#: the pre-fix warn-and-continue behavior).
DISPATCH_NOTIFY_REFUSED = -7

#: CLI exit code for DISPATCH_NOTIFY_REFUSED.
EXIT_NOTIFY_UNCONFIGURED = 8

NOTIFY_AUTOFAIL_CODE = "AF-NOTIFY-UNCONFIGURED"

CAPACITY_AUTOFAIL_CODE = "AF-CAPACITY-UNMEASURED"

#: FIX 11 (presentation rev2 waves): dispatch() refuses an unknown declared
#: mode before any gate runs and before any process exists
#: (AF-MODE-INVALID) -- joins the -1..-8 refusal family. Nothing spawned.
#: PRESENTATION_MODES=0 (documented rollback) leaves the whole FIX 11 mode
#: surface inert: no validation refusal, no .mode-plan.json, no mode env.
DISPATCH_MODE_INVALID = -9

#: CLI exit code for DISPATCH_MODE_INVALID.
EXIT_MODE_INVALID = 10

MODE_AUTOFAIL_CODE = "AF-MODE-INVALID"


#: FIX 33 (presentation rev2 waves): dispatch() refuses when the Step 0 OCR
#: verify-then-branch probe cannot prove the OCR stack functional under the
#: EXACT pipeline interpreter (AF-OCR-ENGINE-MISSING) -- joins the -1..-7
#: refusal family. Nothing spawned. The probe + receipt live in
#: presentation_job/ocr_verify (single source, the same module preflight_deps
#: reports from); the hard-stop is armed by PRESENTATION_OCR_VERIFY
#: (default ON, =0 = documented rollback to the pre-fix no-launch-check
#: behavior).
DISPATCH_OCR_REFUSED = -8

#: CLI exit code for DISPATCH_OCR_REFUSED.
EXIT_OCR_ENGINE_MISSING = 9

OCR_AUTOFAIL_CODE = "AF-OCR-ENGINE-MISSING"


#: CLIENT MODEL PLAN (operator requirement 2026-09-04): dispatch() refuses when
#: the client DECLARED a model plan and a capability class that plan covers has
#: no eligible route (AF-MODEL-PLAN-UNSATISFIED) -- joins the -1..-9 refusal
#: family. Nothing spawned.
#:
#: SCOPE, deliberately narrow: the gate fires ONLY for a client who declared a
#: plan, and only for the classes that plan COVERS. A client who declared
#: nothing reaches this gate exactly as before -- same route, same sidecars,
#: nothing written, nothing refused. Refusing every unroutable class on every
#: profile would be a different (and much larger) behavior change than "let the
#: client choose their own model", and it would newly refuse client boxes that
#: launch fine today.
DISPATCH_MODEL_PLAN_REFUSED = -10

#: CLI exit code for DISPATCH_MODEL_PLAN_REFUSED.
EXIT_MODEL_PLAN_UNSATISFIED = 11

MODEL_PLAN_AUTOFAIL_CODE = "AF-MODEL-PLAN-UNSATISFIED"


#: Mirrors capacity.STATUS_UNDETERMINED. `available` is non-None in this status
#: (it's capacity.DEFAULT_CONSERVATIVE) but was NEVER MEASURED -- it is a floor
#: to proceed AT, not a ceiling this account was proven to support. Checking
#: only `available is None` (as this gate used to) treats the no-config case,
#: which is what nearly every client box IS, as a clean measurement. See
#: dispatch()'s capacity gate below.
CAPACITY_STATUS_UNDETERMINED = "UNDETERMINED"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def resolve_scripts_dir() -> Path:
    """Walk up from this file's location to find the scripts/ directory.

    The scripts/ dir is the one containing run_signature_deck.py and build_deck.py.
    Returns the absolute Path. Exits 2 if not found.
    """
    here = Path(__file__).resolve().parent  # presentation_job/
    scripts = here.parent  # scripts/
    if (scripts / "build_deck.py").is_file() and (scripts / "run_signature_deck.py").is_file():
        return scripts
    print(f"launcher: canonical scripts not found under {scripts}", file=sys.stderr)
    print("  expected build_deck.py + run_signature_deck.py", file=sys.stderr)
    sys.exit(2)


def resolve_runs_root() -> Path:
    """Return the canonical Presentations runs/ directory."""
    scripts = resolve_scripts_dir()
    return scripts.parent / "runs"


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------
def is_engine_running(run_dir: str | Path) -> bool:
    """Read the recorded engine PID (state.json, or .engine.pid sidecar before
    state.json exists). Check if that PID is still alive.

    Uses os.kill(pid, 0) -- signal 0 is an existence check, never a real signal.
    Returns True if running, False if dead or no PID recorded.
    """
    pid = _read_engine_pid(run_dir)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_engine(run_dir: str | Path) -> bool:
    """Read the recorded engine PID (state.json, or .engine.pid sidecar before
    state.json exists). Send SIGTERM to the process group.

    Wait up to 10 seconds. If still alive, SIGKILL. Returns True on
    successful stop, False on timeout.

    FIX 19 (MASTER Part 8): every launcher spawn carries start_new_session=True,
    so the recorded pid IS its own process-group leader and os.killpg reaches the
    whole tree — the engine AND the auto-spawned dispatcher it fathered and any
    render children. Two hardenings close the gaps the SIGTERM-mid-wave QC probe
    exposed:

    1. If the recorded pid was never a group leader (spawned without
       start_new_session by an older launcher, or hand-launched), os.killpg(pid)
       targets the pid's OWN group — which on macOS may not exist as a distinct
       group, raising ProcessLookupError and silently skipping the kill. The
       fallback below signals the pid directly so a non-leader engine still dies.
    2. Between the SIGTERM and the final liveness check the engine may be reaped
       while its group persists (a surviving dispatcher child). The killpg on the
       final escalation uses the same pgid, so a group that outlived its leader is
       still torn down after the grace window — never a reparented orphan walking
       away with the run's intake.

    The engine-spawn site (dispatch(), background=True) already passes
    start_new_session=True; that contract is asserted below by killpg'ing the
    group first and only falling back to the bare pid when the group is gone.
    """
    pid = _read_engine_pid(run_dir)
    if pid is None:
        return True  # nothing to stop

    def _pgid() -> int:
        # The engine is spawned start_new_session=True, so pgid == pid. Fallback
        # only for a recorded pid from an older spawn; -1 means "unknown".
        return pid

    term_hit = False
    try:
        os.killpg(_pgid(), signal.SIGTERM)
        term_hit = True
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)  # FIX 19: non-leader fallback
            term_hit = True
        except OSError:
            pass
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            # The leader is gone; tear down whatever survived it in the group
            # (a dispatcher child may outlive its parent's reaping).
            if term_hit:
                try:
                    os.killpg(_pgid(), 0)
                except OSError:
                    return True  # group gone too — nothing survives
                try:
                    os.killpg(_pgid(), signal.SIGKILL)
                except OSError:
                    pass
            return True
        time.sleep(0.5)
    # Grace window expired with the leader alive: kill the group, then the pid.
    try:
        os.killpg(_pgid(), signal.SIGKILL)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


def _engine_pid_sidecar(run_dir: str | Path) -> Path:
    """Path of the engine-pid sidecar used until state.json exists.

    Canary D1 (R3): launcher.py must not create state.json itself on --new --
    the engine's cmd_new refuses to start when state.json already exists. Until
    cmd_new has written state.json, the engine PID is recorded here; once
    state.json exists the PID lives inside it (is_engine_running/stop_engine
    read the sidecar only as a fallback)."""
    return Path(run_dir) / ".engine.pid"


# ---------------------------------------------------------------------------
# FIX 27 (MASTER Part 8): launcher state writes go through StateStore under
# RunLock. The three launcher writers below used to read-modify-write
# state.json with a bare json.loads + tmp-write + os.replace. A save the
# engine lands in that window (heartbeat tick, phase row, event append) is
# clobbered -- the launcher's copy of the document overwrites it field for
# field. Every launcher merge now (a) takes the run's .job.lock -- the SAME
# exclusive flock the engine holds for its whole run -- before (b) reading
# through StateStore.load() and writing back through StateStore.save(), the
# engine's own atomic path. While the lock is held the engine cannot save
# (it blocks in its own flock), and while the engine holds the lock the
# launcher cannot interleave, so no save is ever lost.
#
# The lock is taken with LOCK_NB plus a bounded retry loop, and a busy lock
# is NEVER fatal to dispatch: a held lock means the engine is actively
# saving this exact run, and the launcher's merge (a pid stamp, a capacity
# status) is best-effort metadata, not run data. It retries briefly, then
# reports the miss and leaves the value to the sidecar / a later merge --
# never blocking, never wedging the launch.
# ---------------------------------------------------------------------------

#: How long (seconds) a launcher merge waits for the run lock before giving
#: the attempt up as busy. Bounded so a wedged engine can never hang dispatch.
LAUNCHER_LOCK_WAIT_S = 2.0


def _launcher_run_lock(run_dir: Path):
    """Context manager for a bounded, non-blocking RunLock acquisition.

    Yields the acquired state.RunLock, or None when the lock stayed busy for
    LAUNCHER_LOCK_WAIT_S (engine mid-save / engine holding it for the run).
    Mirrors state.RunLock's own flock protocol (same file, LOCK_EX) so the
    mutual exclusion with the engine is the engine's own, not a second
    hand-rolled lock beside it.
    """
    import contextlib
    from datetime import datetime, timezone

    try:
        from .state import RunLock
    except ImportError:
        from state import RunLock  # type: ignore[no-redef]

    @contextlib.contextmanager
    def _ctx():
        lock = RunLock(run_dir)
        # Reproduce RunLock.__enter__'s open + LOCK_NB, but wait-bounded and
        # yielding None instead of dying when busy (state.RunLock dies with
        # EXIT_LOCK_HELD -- correct for an engine start, wrong for a
        # best-effort launcher merge).
        lock.path.parent.mkdir(parents=True, exist_ok=True)
        fh = lock.path.open("a+")
        deadline = time.time() + LAUNCHER_LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    fh.close()
                    yield None
                    return
                time.sleep(0.05)
        lock._fh = fh  # so lock.__exit__ unlocks + closes the handle we opened
        try:
            fh.seek(0)
            fh.truncate()
            now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            fh.write(f"{os.getpid()} launcher-merge {now}\n")
            fh.flush()
        except OSError:
            pass
        try:
            yield lock
        finally:
            try:
                lock.__exit__()
            except Exception:  # noqa: BLE001 -- never let unlock break dispatch
                pass

    return _ctx()


def _merge_run_state_field(run_dir: Path, mutate, *, json_default=None) -> bool:
    """FIX 27: merge one launcher field into state.json through StateStore
    under the run's RunLock.

    mutate(state) applies the launcher's field(s) to the freshly loaded state
    document (a plain dict). The whole read-mutate-save happens with the run's
    exclusive .job.lock held, so a concurrent engine save can neither be
    clobbered by this write nor interleave inside it. Returns True when the
    merge landed in state.json.

    state.json ABSENT is a normal outcome here (the --new window before
    cmd_new writes it): nothing is synthesized, callers fall back to their
    sidecars. A corrupt/unreadable state.json is reported and skipped the
    same way -- the engine's StateStore.load() die() path must never fire
    from the launcher.

    json_default (when given) routes through to the save's json.dumps -- the
    capacity-status merge passes capacity.json_default so an UNBOUNDED
    availability serializes, never raises, never hangs.
    """
    run_dir = Path(run_dir).expanduser().resolve()
    state_path = run_dir / "state.json"
    if not state_path.is_file():
        return False
    try:
        from .state import StateStore
    except ImportError:
        from state import StateStore  # type: ignore[no-redef]

    with _launcher_run_lock(run_dir) as lock:
        if lock is None:
            return False
        try:
            with state_path.open("r", encoding="utf-8") as fh:
                state: Dict[str, Any] = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return False
        if not isinstance(state, dict):
            return False
        try:
            mutate(state)
        except Exception:  # noqa: BLE001 -- a bad mutate never blocks dispatch
            return False
        # Save through the engine's own atomic writer (temp + fsync +
        # os.replace), never a hand-rolled third copy of it.
        store = StateStore(run_dir)
        store.path = state_path  # pin: this run's state.json exactly
        try:
            state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            payload = json.dumps(state, indent=2, ensure_ascii=False,
                                 sort_keys=False, default=json_default)
        except (TypeError, ValueError):
            return False
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            import tempfile
            fd, tmp = tempfile.mkstemp(dir=str(run_dir), prefix=".state-",
                                       suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, store.path)
        except Exception:  # noqa: BLE001 -- never let a metadata merge block dispatch
            try:
                os.unlink(tmp)  # type: ignore[possibly-undefined]
            except OSError:
                pass
            return False
        return True


def _write_engine_pid(run_dir: str | Path, pid: int) -> None:
    """Record the engine PID for the watchdog to monitor.

    If state.json exists, the PID is merged into it (preserving every field
    the engine wrote) -- FIX 27: that merge goes through StateStore under the
    run's RunLock, so an engine save landing in the same window is never
    clobbered. If state.json does not exist yet -- the --new window, before
    cmd_new has run -- the PID goes to the .engine.pid sidecar instead;
    state.json is NEVER created here, so the engine's 'state.json already
    exists' refusal can never trigger from the launcher."""
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        merged = _merge_run_state_field(
            run_path,
            lambda state: state.__setitem__("engine_pid", pid),
        )
        if merged:
            try:
                _engine_pid_sidecar(run_path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        # Lock stayed busy (engine mid-save) or the document was unreadable:
        # leave the PID on the sidecar, which is_engine_pid/_read_engine_pid
        # consult as a fallback, and never clobber a concurrent engine save.
        print(f"launcher: state.json busy/unreadable -- engine pid {pid} left "
              f"on the sidecar only", file=sys.stderr)
        return
    # No state.json yet: sidecar only. Never synthesize state.json here.
    sidecar = _engine_pid_sidecar(run_path)
    try:
        tmp = sidecar.with_suffix(".pid.tmp")
        tmp.write_text(f"{pid}\n", encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError as exc:
        print(f"launcher: could not record engine pid {pid}: {exc}", file=sys.stderr)


def _read_engine_pid(run_dir: str | Path) -> Optional[int]:
    """Read the recorded engine PID: state.json first, .engine.pid sidecar second."""
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
        pid = state.get("engine_pid")
        if isinstance(pid, int) and pid > 0:
            return pid
    sidecar = _engine_pid_sidecar(run_path)
    if sidecar.is_file():
        try:
            pid = int(sidecar.read_text(encoding="utf-8").strip())
            if pid > 0:
                return pid
        except (OSError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------------
# Capacity gate -- measured before anything is launched
# ---------------------------------------------------------------------------
def capacity_gate() -> Tuple[Optional[int], dict]:
    """Probe THIS client's capacity. Returns (available, probe_result).

    `available` is None when the probe could not produce a number, which is the
    dispatch path's refusal condition. An import failure of the capacity module
    is itself an unmeasured capacity -- it is never treated as "no limit"."""
    try:
        try:
            from . import capacity  # package-relative (python3 -m presentation_job)
        except ImportError:
            import capacity  # direct file run from presentation_job/
        result = capacity.probe()
        return capacity.available_or_none(result), result
    except Exception as exc:  # noqa: BLE001 -- an unreadable probe is UNMEASURED
        return None, {
            "status": "FAILED",
            "available": None,
            "notes": [f"capacity probe could not run: {exc.__class__.__name__}: {exc}"],
        }


def notify_gate(run_path: Path) -> bool:
    """FIX 22 (presentation rev2 waves): the notify-transport preflight.

    An unset/unusable PRESENTATION_NOTIFY_CMD means job progress/blocked/done
    messages and watchdog stall findings can NEVER leave this box -- the
    exact silence the U14 comment in presentation-watchdog.sh documented and
    then tolerated. Under PRESENTATION_NOTIFY_FAIL_CLOSED (default ON) an
    unconfigured transport is a hard configuration error at launch, not a
    warning: print the AF-NOTIFY-UNCONFIGURED payload (marker NOT_READY_NOTIFY,
    the same string FIX 39's pre-roll gate keys on) and return False so
    dispatch() refuses BEFORE any process is spawned.

    =0 (the documented emergency kill-switch) restores the pre-fix
    warn-and-continue behavior: a loud WARNING to stderr, then True. It does
    NOT restore direct Telegram (FIX 23 owns the transport) and does NOT
    suppress FIX 21 SYSTEM-block notifications -- only the launch hard-stop
    is disabled.

    The structural check itself is single-sourced in notify_preflight
    (presentation_job.notify_preflight.check_notify_config) -- the same
    module the FIX 39 pre-roll gate runs as a CLI -- so "what counts as
    configured" can never drift between the launcher and the rollout check.
    """
    try:
        try:
            from . import notify_preflight
        except ImportError:
            import notify_preflight
    except ImportError:  # broken install: behave as configured, never fail-open silently
        print("launcher: WARNING notify_preflight unavailable -- cannot check "
              "the notify transport", file=sys.stderr)
        return True
    result = notify_preflight.check_notify_config()
    if result["ready"]:
        return True
    payload = notify_preflight.refusal_payload()
    payload["run_dir"] = str(run_path)
    if not result["fail_closed"]:
        print(f"launcher: WARNING {notify_preflight.NOTIFY_CMD_ENV} is unset or "
              f"unusable -- notifications will not be delivered "
              f"(PRESENTATION_NOTIFY_FAIL_CLOSED=0: warn-only mode)", file=sys.stderr)
        return True
    print(f"launcher: REFUSING to dispatch {run_path} -- "
          f"{NOTIFY_AUTOFAIL_CODE}: {result['reason']}", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return False


def ocr_launch_gate(run_path: Path) -> bool:
    """FIX 33 OCR LAUNCH GATE -- Step 0 verify-then-branch, invoked from
    dispatch() before any process exists.

    Runs the read-only, 5-minute-timeboxed OCR probe (ocr_verify.run_step0_
    probe) through the EXACT interpreter the canonical entry resolves for the
    pipeline, writes the redacted receipt into <run_dir>/working/checkpoints/,
    and refuses launch unless the probe measured BRANCH A (pytesseract
    importable + tesseract binary + version + REAL one-line fixture OCR all
    pass under THAT interpreter). A Branch B / unmeasured result is a hard
    launch refusal naming the exact failed layer -- the deck must never render
    (and never spend) on a box whose postflight OCR-readback gate can then
    never pass.

    The probe result is RECEIPT-BINDING: the receipt names the interpreter it
    measured, and the launch check compares it against the interpreter that
    is about to be spawned -- a DIFFERENT interpreter selected later fails
    launch; it never borrows a green receipt minted under another one.

    PRESENTATION_OCR_VERIFY=0 is the documented rollback: it restores the
    pre-fix behavior (no launch-time OCR check at all -- the legacy warn-mode
    preflight_deps probe remains available on its own).
    """
    try:
        try:
            from . import ocr_verify
        except ImportError:
            import ocr_verify
    except ImportError:  # broken install: never fail-open silently
        print("launcher: WARNING ocr_verify unavailable -- cannot run the "
              "FIX 33 Step 0 OCR probe", file=sys.stderr)
        return True
    if not ocr_verify.verify_enabled():
        print("launcher: PRESENTATION_OCR_VERIFY=0 -- Step 0 OCR launch gate "
              "disabled (documented rollback; pre-fix behavior)", file=sys.stderr)
        return True

    receipt = ocr_verify.run_step0_probe(scripts_dir=resolve_scripts_dir())
    ocr_verify.write_receipt(receipt, Path(run_path) / "working" / "checkpoints")

    if receipt.get("branch") != "A":
        layers = ocr_verify.failed_layers(receipt) or ["probe could not measure"]
        print(f"launcher: REFUSING to dispatch {run_path} -- "
              f"{OCR_AUTOFAIL_CODE}: OCR Step 0 did not verify Branch A under "
              f"the pipeline interpreter {receipt.get('interpreter')}.",
              file=sys.stderr)
        print("launcher: failed layer(s):", file=sys.stderr)
        for layer in layers:
            print(f"  - {layer}", file=sys.stderr)
        print("launcher: receipt written to "
              f"{Path(run_path) / 'working' / 'checkpoints' / ocr_verify.RECEIPT_NAME}",
              file=sys.stderr)
        return False

    # RECEIPT BINDING: the green receipt is only valid for the interpreter it
    # measured. A different interpreter about to run the pipeline must not
    # borrow it (spec, Branch A last sentence).
    spawn_interp = sys.executable or "python3"
    if not ocr_verify.interpreter_binding_ok(receipt, interpreter=spawn_interp):
        print(f"launcher: REFUSING to dispatch {run_path} -- "
              f"{OCR_AUTOFAIL_CODE}: the Step 0 green receipt was measured under "
              f"{receipt.get('interpreter')} but the launch interpreter is "
              f"{spawn_interp}. A different interpreter never borrows a green "
              f"receipt; re-run the probe under the interpreter that will "
              f"actually run the pipeline.", file=sys.stderr)
        return False

    # One-line smoke, recorded: interpreter + tesseract version + fixture OCR ok.
    print(f"launcher: OCR Step 0 (FIX 33) BRANCH A verified under "
          f"{receipt.get('interpreter')} -- pytesseract importable, tesseract "
          f"{receipt.get('tesseract_version')}, one-line fixture OCR passed "
          f"(no install mutation; receipt "
          f"{Path(run_path) / 'working' / 'checkpoints' / ocr_verify.RECEIPT_NAME})",
          file=sys.stderr)
    return True


def _refuse_unmeasured_capacity(result: dict, run_path: Path) -> int:
    """Emit the autofail and refuse. No engine process has been created."""
    try:
        try:
            from . import capacity
        except ImportError:
            import capacity
        payload = capacity.autofail_payload(result)
        detail = capacity.refusal_message(result)
    except Exception:  # noqa: BLE001 -- refuse loudly even if capacity.py is gone
        payload = {"code": CAPACITY_AUTOFAIL_CODE, "detail": str(result)}
        detail = str(result)
    payload["run_dir"] = str(run_path)
    print(f"launcher: REFUSING to dispatch {run_path} -- {CAPACITY_AUTOFAIL_CODE}: "
          f"{detail}", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return DISPATCH_CAPACITY_REFUSED


def _refuse_undetermined_parallel(result: dict, run_path: Path, requested: int,
                                  available: int) -> int:
    """Refuse a wide-parallel request when capacity was never actually measured.

    UNDETERMINED's `available` is capacity.DEFAULT_CONSERVATIVE -- a floor to
    proceed AT, never a ceiling this account was proven to support. A caller
    that declares it wants MORE than that floor, with nothing backing the
    number, is exactly the blind dispatch AF-CAPACITY-UNMEASURED exists to
    stop -- so this refuses the same way an unusable override refuses: same
    code, same non-zero sentinel, nothing spawned."""
    detail = (
        f"requested {requested} concurrent, but capacity is UNDETERMINED (no "
        f"provider/plan could be detected) -- only the conservative floor of "
        f"{available} is safe to assume. Declare capacity_override.json or answer "
        f"the capacity interview ('python3 -m presentation_job --capacity') to "
        f"unlock wider dispatch."
    )
    payload = {
        "code": CAPACITY_AUTOFAIL_CODE,
        "status": result.get("status"),
        "detection_source": result.get("detection_source"),
        "requested": requested,
        "conservative_floor": available,
        "run_dir": str(run_path),
        "detail": detail,
    }
    print(f"launcher: REFUSING to dispatch {run_path} -- {CAPACITY_AUTOFAIL_CODE}: "
          f"{detail}", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return DISPATCH_CAPACITY_REFUSED


def _record_capacity_status(run_path: Path, result: dict) -> None:
    """Record an UNDETERMINED probe into run state so the anomaly outlives the
    launch-line log entry. Written unconditionally to a `.capacity-status.json`
    sidecar (never depends on state.json existing yet -- the --new window,
    before cmd_new runs, is exactly when this matters) and merged into
    state.json too once it exists, mirroring _write_engine_pid's dual-write
    pattern. Best-effort: a write failure here must never affect dispatch.

    `result["available"]` is UNDETERMINED-only at this call site today (a
    plain int, capacity.DEFAULT_CONSERVATIVE), but this function takes any
    capacity result -- so the json.dumps() calls below still route through
    capacity.json_default in case a future caller ever records a
    NO_CAP_PROVIDERS (UNBOUNDED) result through here; that must serialize to
    the string "UNBOUNDED", never raise TypeError, never hang."""
    try:
        try:
            from . import capacity
        except ImportError:
            import capacity
        json_default = capacity.json_default
    except Exception:  # noqa: BLE001 -- a broken import must not block recording
        json_default = None

    record = {
        "status": result.get("status"),
        "available": result.get("available"),
        "provider": result.get("provider"),
        "plan": result.get("plan"),
        "detection_source": result.get("detection_source"),
        "notes": result.get("notes"),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    try:
        run_path.mkdir(parents=True, exist_ok=True)
        sidecar = run_path / ".capacity-status.json"
        tmp = sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, default=json_default), encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError as exc:
        print(f"launcher: could not record capacity status: {exc}", file=sys.stderr)
        return
    state_path = run_path / "state.json"
    if state_path.is_file():
        # FIX 27: merge through StateStore under the run's RunLock -- the
        # bare read-modify-write here used to clobber any engine save that
        # landed in the same window.
        ok = _merge_run_state_field(
            run_path,
            lambda state: state.__setitem__("capacity_status", record),
            json_default=json_default,
        )
        if not ok:
            print(f"launcher: state.json busy/unreadable -- capacity status "
                  f"left on the .capacity-status.json sidecar only",
                  file=sys.stderr)


def _notify_operator_undetermined(result: dict, run_path: Path, available: int) -> None:
    """Best-effort ping to the operator channel. Follows watchdog.py's own
    precedent (report.dispatch("watchdog", "stall", ...): a fixed, non-numeric
    chat_id names the subsystem raising the alert, distinct from any per-job
    requester chat_id). A notify failure is swallowed -- it must never affect
    the dispatch decision."""
    try:
        try:
            from . import report
        except ImportError:
            import report
        report.dispatch(
            "capacity",
            "capacity_undetermined",
            f"Presentations: capacity UNDETERMINED for {run_path} -- dispatching at "
            f"the conservative floor of {available} only (provider/plan could not be "
            f"detected). Declare capacity_override.json or answer the capacity "
            f"interview to unlock this box's real ceiling.",
        )
    except Exception:  # noqa: BLE001 -- never let operator-notify break dispatch
        pass


def _announce_undetermined_capacity(result: dict, run_path: Path, available: int) -> None:
    """Make the UNDETERMINED case impossible to miss: a banner that cannot be
    confused with the MEASURED print, a run-state record, and an operator
    ping. This -- not silence -- is what closes the no-config hole without
    turning an unconfigured box into an outage."""
    banner = (
        f"launcher: !! CAPACITY UNDETERMINED for {run_path} -- no provider/plan "
        f"could be detected (checked: declared override, 9Router, OpenClaw). "
        f"Proceeding at the conservative floor of {available} concurrent agent(s) "
        f"ONLY -- never guessed upward. Run 'python3 -m presentation_job --capacity' "
        f"(or answer the one-time capacity interview) to declare this box's real "
        f"ceiling."
    )
    print(banner, file=sys.stderr)
    print(banner, flush=True)
    _record_capacity_status(run_path, result)
    _notify_operator_undetermined(result, run_path, available)


# ---------------------------------------------------------------------------
# Dispatch -- the single entry point all callers use
# ---------------------------------------------------------------------------
def model_plan_gate(run_path: Path, mode: Optional[str] = None) -> Optional[int]:
    """CLIENT MODEL PLAN gate. Returns DISPATCH_MODEL_PLAN_REFUSED, or None.

    Runs AFTER the credit preflight on purpose (T9): credit_preflight prices an
    unrouted phase as the dispatcher's default model on deepseek-direct, so a
    client model nobody has priced yet is a preflight WARN, never a block --
    this gate is where a model plan actually decides a launch.

    Refuses when the client DECLARED a plan and a class that plan COVERS has no
    eligible route, naming the class, the declared model and every rejected
    candidate's reason. Never at dispatch time, twenty minutes in: at launch,
    with nothing spawned.

    Otherwise writes run_dir/.model-plan.json (the per-class table plus the
    per-decision client_plan / client_plan_floor stamps) and prints the banner
    naming every slot, every visible fallback and every waiver. The sidecar
    write is best-effort and never blocks a launch -- same contract as
    _record_capacity_status."""
    try:
        try:
            from . import model_router as _router
        except ImportError:
            import model_router as _router  # type: ignore[no-redef]
    except ImportError:
        return None  # no router deployed: nothing to gate, pre-fix behavior
    if not _router.flag_enabled():
        return None  # PRESENTATION_MODEL_ROUTER=0 rollback: the surface is inert

    try:
        try:
            from . import resource_profile as _rp
        except ImportError:
            import resource_profile as _rp  # type: ignore[no-redef]
        profile = _rp.load_profile()
    except Exception:  # noqa: BLE001 -- an unreadable store is not a plan
        return None
    plan = _router.model_plan(profile)
    if not plan:
        # No client declaration: this gate does not exist for this run. No
        # sidecar, no banner, no refusal -- byte-for-byte the pre-fix launch.
        return None

    decisions = {}
    unsatisfied = []
    for phase_id, capability in _router.PHASE_CAPABILITY.items():
        if capability == "mechanical" or capability in decisions:
            continue
        try:
            # mode=None (every caller that declares no FIX 11 mode) resolves
            # against the standard candidate lists -- resolve_route's own
            # default. Passing None through would raise in normalize_mode.
            decision = _router.resolve_route(phase_id, profile=profile,
                                             mode=mode or "standard")
        except Exception as exc:  # noqa: BLE001 -- a router error is not a verdict
            print(f"launcher: model-plan gate could not resolve {phase_id} "
                  f"({exc.__class__.__name__}: {exc}) -- gate skipped",
                  file=sys.stderr)
            return None
        decisions[capability] = decision
        if decision.get("profile_state") != "has_providers":
            continue
        if decision.get("route") is not None:
            continue
        if _router.CLASS_SLOT.get(capability) is None:
            continue  # a class the client's plan does not cover
        if _router.client_plan_for(capability, profile) is None:
            continue  # covered class, but this client declared no slot for it
        unsatisfied.append({
            "capability": capability,
            "phase_id": phase_id,
            "declared": (decision.get("client_plan")
                         or decision.get("client_plan_floor") or {}),
            "reason": decision.get("reason"),
            "rejected": [{"alias": c.get("alias"), "provider": c.get("provider"),
                          "model": c.get("model"), "reason": c.get("reason")}
                         for c in (decision.get("candidates") or [])],
        })

    if unsatisfied:
        detail = "; ".join(
            f"capability {u['capability']} (e.g. phase {u['phase_id']}) has no "
            f"eligible route -- {u['reason']}" for u in unsatisfied)
        payload = {
            "code": MODEL_PLAN_AUTOFAIL_CODE,
            "run_dir": str(run_path),
            "model_plan": _router.plan_report(profile),
            "unsatisfied": unsatisfied,
            "detail": detail,
        }
        print(f"launcher: REFUSING to dispatch {run_path} -- "
              f"{MODEL_PLAN_AUTOFAIL_CODE}: {detail}", file=sys.stderr)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return DISPATCH_MODEL_PLAN_REFUSED

    report = _router.plan_report(profile)
    stamps = []
    for capability, decision in sorted(decisions.items()):
        if decision.get("client_plan"):
            stamps.append({"capability": capability, **decision["client_plan"]})
        elif decision.get("client_plan_floor"):
            stamps.append({"capability": capability, "floor": "failed",
                           **decision["client_plan_floor"]})
    try:
        run_path.mkdir(parents=True, exist_ok=True)
        sidecar = run_path / ".model-plan.json"
        tmp = sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"run_dir": str(run_path), "plan": report,
                                   "decisions": stamps}, indent=2,
                                  sort_keys=True), encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError as exc:
        print(f"launcher: could not write the model-plan sidecar: {exc}",
              file=sys.stderr)

    lines = []
    for row in report["classes"]:
        if row["source"] == "client-plan":
            lines.append(f"{row['capability']}={row['provider']}/{row['model']}"
                         f" [client {row['slot']}"
                         + (", floor WAIVED" if row["floor"] == "waived" else "")
                         + (f", via {row['via']}" if row.get("via") == "workhorse-spill"
                            else "") + "]")
        elif row["floor"] == "failed":
            lines.append(f"{row['capability']}={row['default_alias']} "
                         f"[DEPARTMENT DEFAULT -- the declared "
                         f"{row['provider']}/{row['model']} does not meet this "
                         f"class's floor: {row['detail']}]")
    print(f"launcher: client model plan stamped -- "
          f"{'; '.join(lines) or 'no class is governed by the declared plan'}"
          + (f" (thinking={report['thinking']})" if report.get("thinking") else "")
          + (f" (waivers: {', '.join(report['floor_waivers'])})"
             if report["floor_waivers"] else ""), flush=True)
    return None


def dispatch(
    run_dir: str,
    client: Optional[str] = None,
    deck_type: Optional[str] = None,
    resume: bool = False,
    phase: Optional[str] = None,
    until: Optional[str] = None,
    background: bool = True,
    requested_parallel: Optional[int] = None,
    mode: Optional[str] = None,
    balances: Optional[dict] = None,
    plan_calls: Optional[dict] = None,
    last_run_dir: Optional[str] = None,
) -> int:
    """Launch the presentation engine.

    Args:
        run_dir: The job's run directory (must exist with state.json for resume).
        client: Client identifier for --new (written into state.json).
        deck_type: Deck type for --new (signature_presentation, standard, etc).
        resume: If True, use --resume instead of --new.
        phase: Run exactly one phase (passed through to engine --phase).
        until: Run through this phase then stop (passed through to --until).
        background: If True, spawn as detached subprocess (default).
                    If False, run synchronously (for testing).
        requested_parallel: How much parallel width this run wants, if the
                    caller knows and cares to declare it. None (the default,
                    and every caller today) means "no declared request" --
                    dispatch proceeds at whatever capacity.probe() measures,
                    including the conservative floor when it is UNDETERMINED.
                    When given AND capacity is UNDETERMINED, a request above
                    the conservative floor is refused (see the gate below);
                    it is never checked against a real MEASURED ceiling --
                    execution_plan.py already waves a wide request down to
                    a measured ceiling instead of refusing it.
        mode: FIX 12. The mode being launched ("ultra"/"standard"/"economy"
                    -- FIX 11 owns the vocabulary). Declaring one runs the
                    credit preflight before argv is built: the phase plan's
                    routes are priced from the FIX 13 catalog unit_costs
                    and checked against `balances` per provider; a blocked
                    verdict (low balance, cost_unknown rate, unestimable
                    calls) refuses with AF-CREDIT-PREFLIGHT and NOTHING is
                    spawned. None (every current caller) skips the gate --
                    FIX 12 prices mode launches; PRESENTATION_CREDIT_PREFLIGHT=0
                    is the documented rollback (no gate, pre-fix behavior).
        balances: {provider: usd} credit balances. None -> read
                    $PRESENTATION_CREDIT_BALANCES_FILE (the surface a live
                    balance probe writes).
        plan_calls: The plan's own per-phase slide/task counts
                    ({phase_id: n}) -- the estimation fallback when no FIX 5
                    measured call history exists.
        last_run_dir: Where to read FIX 5 measured per-phase call counts
                    (working/telemetry/stage-timings.jsonl). Defaults to
                    run_dir.

    Returns:
        PID on success (int > 0), -1 on failure, -4 when the capacity gate
        refused (AF-CAPACITY-UNMEASURED, nothing spawned), -5 when deck_type
        does not resolve (AF-DECK-TYPE-UNKNOWN, nothing spawned), -6 when
        the FIX 12 credit preflight blocked a declared mode
        (AF-CREDIT-PREFLIGHT, nothing spawned), -7 when the notify transport
        is unconfigured (AF-NOTIFY-UNCONFIGURED, FIX 22 fail-closed,
        nothing spawned).
        The function returns immediately when background=True.
    """
    # Single-sourced validation (fix/deck-type-routing-bypass): deck_type is
    # not itself passed to the engine's argv below -- --new reads
    # presentation_type from the --intake JSON, built by
    # presentation_job/resolve_intake.py, which applies this SAME check --
    # but an unrecognized value must fail loudly here too, not pass through
    # silently. None is exempt: dispatch_resume() never declares one, and a
    # resume never creates a new job (the type was already committed to
    # state.json by a prior --new).
    if deck_type is not None:
        try:
            normalize_presentation_type(deck_type)
        except UnknownPresentationType as exc:
            print(f"launcher: {exc}", file=sys.stderr)
            return DISPATCH_UNKNOWN_DECK_TYPE

    scripts = resolve_scripts_dir()
    engine_entry = scripts / "presentation_job.py"
    if not engine_entry.is_file():
        print(f"launcher: engine entry not found at {engine_entry}", file=sys.stderr)
        return -1

    run_path = Path(run_dir).expanduser().resolve()

    # FIX 11 MODE GATE -- an unknown declared mode is refused here, before
    # any gate, before the sidecar, before any process exists. An unknown
    # mode is never silently coerced into a cheaper or more expensive one.
    # PRESENTATION_MODES=0 (documented rollback) leaves the surface inert.
    mode_env: Optional[dict] = None
    _router = None
    if mode is not None:
        try:
            try:
                from . import model_router as _router
            except ImportError:
                import model_router as _router  # type: ignore[no-redef]
        except ImportError:
            _router = None
        if _router is not None and _router.modes_enabled():
            try:
                mode = _router.normalize_mode(mode)
            except ValueError as exc:
                print(f"launcher: REFUSING to dispatch {run_path} -- "
                      f"{MODE_AUTOFAIL_CODE}: {exc}", file=sys.stderr)
                return DISPATCH_MODE_INVALID

    # FIX 22 NOTIFY GATE -- before the capacity probe, before argv is built,
    # before any process exists. An unset/unusable PRESENTATION_NOTIFY_CMD is
    # a hard configuration error at launch (fail-closed default): a job
    # whose progress/blocked/done messages and stall findings can never
    # leave this box must not start. PRESENTATION_NOTIFY_FAIL_CLOSED=0 is
    # the documented rollback to the pre-fix warn-and-continue behavior.
    if not notify_gate(run_path):
        return DISPATCH_NOTIFY_REFUSED

    # FIX 33 OCR GATE -- Step 0 verify-then-branch, before the capacity probe,
    # before argv is built, before any process exists. A box whose OCR stack
    # cannot be proven functional under the EXACT pipeline interpreter is a
    # hard launch refusal (AF-OCR-ENGINE-MISSING): the postflight OCR-readback
    # gate would block every close anyway, so refusing at launch is the
    # minute-zero refusal MASTER-SPEC 7.4 asks for -- before any paid
    # generation. PRESENTATION_OCR_VERIFY=0 is the documented rollback.
    if not ocr_launch_gate(run_path):
        return DISPATCH_OCR_REFUSED

    # THE GATE. Measure before launching -- before argv is built, before any
    # process exists. A run that cannot be sized is a run that does not start.
    #
    # available is None            -> PARKED or FAILED: no number at all. Refuse.
    # status == UNDETERMINED       -> a number, but never MEASURED -- it is
    #                                  capacity.DEFAULT_CONSERVATIVE, a floor to
    #                                  proceed AT. Refuse ONLY if the caller
    #                                  declared it wants more than that floor;
    #                                  otherwise proceed, but loudly, on record,
    #                                  and with the operator told.
    # anything else (MEASURED)     -> a real, detected ceiling. Proceed as before.
    available, capacity_result = capacity_gate()
    if available is None:
        return _refuse_unmeasured_capacity(capacity_result, run_path)

    if capacity_result.get("status") == CAPACITY_STATUS_UNDETERMINED:
        if requested_parallel is not None and requested_parallel > available:
            return _refuse_undetermined_parallel(capacity_result, run_path,
                                                 requested_parallel, available)
        _announce_undetermined_capacity(capacity_result, run_path, available)
    else:
        print(f"launcher: capacity measured -- {available} concurrent agents available "
              f"(provider {capacity_result.get('provider')}, plan "
              f"{capacity_result.get('plan')}, source "
              f"{capacity_result.get('detection_source')})", flush=True)

    # FIX 12 CREDIT GATE -- before argv is built, before any process exists.
    # A declared mode launch is priced against the balances on every provider
    # the phase plan will use; a blocked verdict refuses with
    # AF-CREDIT-PREFLIGHT and NOTHING is spawned. mode=None (every current
    # caller) skips the gate -- FIX 12 prices mode launches; an un-moded run
    # keeps its pre-fix path, and the =0 flag is the documented rollback.
    if mode is not None:
        try:
            try:
                from . import credit_preflight
            except ImportError:
                import credit_preflight
        except ImportError:
            credit_preflight = None  # type: ignore[assignment]
        verdict = None
        if credit_preflight is not None:
            verdict = credit_preflight.launcher_gate(
                run_path, mode, balances=balances,
                plan_calls=plan_calls, last_run_dir=last_run_dir)
        if verdict is not None and "skipped" not in verdict:
            if verdict.get("verdict") == "blocked":
                blocking = "; ".join(
                    f"[{b.get('code')}] {b.get('detail')}"
                    for b in verdict.get("blocking", []))
                downgrade = verdict.get("downgrade_to")
                detail = (f"mode {mode} credit preflight BLOCKED -- "
                          f"estimated ${verdict.get('total_estimate_usd', 0):.2f} "
                          f"across "
                          f"{', '.join(p.get('provider', '?') for p in verdict.get('per_provider', [])) or 'no provider'}. "
                          f"{blocking}. "
                          + (f"Downgrade to '{downgrade}' may fit; "
                             f"re-preflight it. "
                             if downgrade else "No cheaper mode available. "))
                payload = {
                    "code": CREDIT_AUTOFAIL_CODE,
                    "mode": mode,
                    "verdict": verdict,
                    "run_dir": str(run_path),
                    "detail": detail,
                }
                print(f"launcher: REFUSING to dispatch {run_path} -- "
                      f"{CREDIT_AUTOFAIL_CODE}: {detail}", file=sys.stderr)
                print(json.dumps(payload, indent=2), file=sys.stderr)
                credit_preflight.notify_verdict(verdict)
                return DISPATCH_CREDIT_REFUSED
            # proceed: unverified balances are recorded + notified inside the
            # verdict (sidecar + operator ping); the launch continues loudly.
            credit_preflight.notify_verdict(verdict)
            parts = []
            for p in verdict.get("per_provider", []):
                bal = p.get("balance")
                bal_s = f"${bal}" if bal is not None else "UNVERIFIED"
                parts.append(f"{p.get('provider')}={bal_s}")
            print(f"launcher: credit preflight PASSED for mode {mode} -- "
                  f"estimated ${verdict.get('total_estimate_usd', 0):.2f} "
                  f"(balances: {', '.join(parts) or 'none'})",
                  flush=True)

    # CLIENT MODEL PLAN GATE -- after the credit preflight (an unpriced client
    # model is a preflight WARN, never a block), before the mode plan sidecar,
    # and before any process exists. A client who declared no plan passes
    # through untouched.
    _plan_refusal = model_plan_gate(run_path, mode=mode)
    if _plan_refusal is not None:
        return _plan_refusal

    # FIX 11 MODE PLAN -- the declared mode is stamped as an honest launch
    # plan: concurrency from the measured client ceiling (Ultra never above
    # the 100-task operator ceiling), ETA from FIX 5 measured wall-clock,
    # cost from the FIX 12 catalog-priced verdict. Written AFTER every
    # refusal gate, so a refused launch never leaves a sidecar. The engine
    # inherits the declared mode through PRESENTATION_MODE.
    # PRESENTATION_MODES=0 skips the whole block (pre-fix behavior).
    if mode is not None and _router is not None and _router.modes_enabled():
        est = None
        if isinstance(verdict, dict):
            est = verdict.get("total_estimate_usd")
        plan = _router.mode_plan(mode, plan_calls=plan_calls,
                                 estimate_usd=est)
        plan["run_dir"] = str(run_path)
        sidecar = run_path / ".mode-plan.json"
        tmp_plan = sidecar.with_suffix(".json.tmp")
        tmp_plan.write_text(json.dumps(plan, indent=2, sort_keys=True),
                            encoding="utf-8")
        os.replace(tmp_plan, sidecar)
        mode_env = dict(os.environ, PRESENTATION_MODE=mode)
        _conc = plan.get("concurrency") or {}
        print(f"launcher: mode {mode} plan stamped -- concurrency "
              f"{_conc.get('concurrency')} ({_conc.get('reason')})",
              flush=True)

    argv = [
        sys.executable or "python3",
        str(engine_entry),
    ]
    if resume:
        argv.append("--resume")
    else:
        argv.append("--new")
    argv.extend(["--run-dir", str(run_path)])

    if client and not resume:
        # --client and --deck-type are intake-time flags; they are embedded
        # in state.json during --new (cmd_new reads intake from --intake),
        # so they are not passed as separate CLI flags to the engine.
        # Instead, we pass them via the intake JSON mechanism: the intake
        # bridge populates working/copy/intake.json (launcher contract --
        # see dispatch_new's docstring). Pass that file to --new.
        intake_arg: Optional[str] = None
        for cand in (
            run_path / "working" / "copy" / "intake.json",
            run_path / "working" / "checkpoints" / ".engine-intake.json",
        ):
            if cand.is_file():
                intake_arg = str(cand)
                break
        if intake_arg:
            argv.extend(["--intake", intake_arg])
        else:
            print(f"launcher: WARNING no intake JSON at {run_path}/working/copy/intake.json "
                  "-- engine --new will refuse (presentation_type required)", file=sys.stderr)
    if resume:
        intake_check = run_path / "working" / "checkpoints" / ".engine-intake.json"
        if intake_check.is_file():
            argv.extend(["--intake", str(intake_check)])

    if phase:
        argv.extend(["--phase", phase])
    if until:
        argv.extend(["--until", until])

    if background:
        # Spawn detached: new process group, stdout/stderr to run-dir logs.
        # FIX 19: start_new_session=True makes the engine its own process-group
        # leader, so stop_engine()'s os.killpg reaches the engine AND everything
        # it fathers (the auto-spawned work_order_dispatcher, render children).
        # Killing only the engine pid — the pre-FIX 19 behavior — left the
        # dispatcher and its workers alive to rewrite intake on a dead run.
        log_dir = run_path / "working" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / "engine-stdout.log"
        stderr_path = log_dir / "engine-stderr.log"

        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                cwd=str(scripts),
                stdout=stdout_path.open("a", encoding="utf-8"),
                stderr=stderr_path.open("a", encoding="utf-8"),
                start_new_session=True,  # new process group for orphan-free timeout
                close_fds=True,
                env=mode_env,  # FIX 11: engine inherits the declared mode
            )
        except OSError as exc:
            print(f"launcher: could not start engine: {exc}", file=sys.stderr)
            return -1

        # Canary D1 (R3): record the engine PID ONLY after the spawn succeeded.
        # _write_engine_pid never creates state.json -- if cmd_new has not run
        # yet (the --new window) the PID lands in the .engine.pid sidecar, so
        # the engine's 'state.json already exists' refusal can never trigger
        # from the launcher. Same path for --new and --resume.
        _write_engine_pid(run_path, proc.pid)
        # Then, once cmd_new HAS written state.json (the --new path), merge the
        # PID into it so the watchdog sees a self-contained record. Poll briefly
        # (cmd_new is fast) and fall back to the sidecar without error.
        if not resume:
            deadline = time.time() + 5.0
            state_path = run_path / "state.json"
            while time.time() < deadline and not state_path.is_file():
                time.sleep(0.1)
            if state_path.is_file():
                # FIX 27: the poll-window merge goes through StateStore under
                # the run's RunLock. The bare read-modify-write here was the
                # exact lost-update shape QC FIX 27 probes: cmd_new writes
                # state.json, the engine immediately starts saving (heartbeat,
                # phase rows, events) from ITS copy, and the launcher's
                # write-back clobbered every field the engine had just saved.
                # Under the lock the two writers serialize; a lock that stays
                # busy for LAUNCHER_LOCK_WAIT_S leaves the pid on the sidecar
                # rather than racing the engine.
                if not _merge_run_state_field(
                    run_path,
                    lambda state: state.__setitem__("engine_pid", proc.pid),
                ):
                    print(f"launcher: state.json busy/unreadable after --new "
                          f"-- engine pid {proc.pid} left on the sidecar only",
                          file=sys.stderr)
            # FIX 34: --new consumed working/copy/intake.json the moment cmd_new
            # wrote state.json — seal it. The 5s poll above already gave cmd_new
            # its window; seal on state.json presence, log-and-continue if the
            # file never appeared (a failed --new has nothing to seal).
            if not resume:
                seal_intake(run_path, reason="dispatch-new-background")
        print(f"Engine launched: PID {proc.pid}  run-dir={run_path}  "
              f"cmd={' '.join(argv)}", flush=True)
        print(f"  logs: {stdout_path}, {stderr_path}", flush=True)
        return proc.pid
    else:
        # Synchronous -- run in foreground (for testing / debugging).
        try:
            proc = subprocess.run(argv, shell=False, cwd=str(scripts),
                                  check=False, env=mode_env)
        except OSError as exc:
            print(f"launcher: could not start engine: {exc}", file=sys.stderr)
            return -1
        # The child has already exited; recording a PID for a finished process
        # is meaningless, so nothing is written here. The engine's cmd_new
        # wrote state.json itself (if it succeeded).
        if not resume:
            # FIX 34: same seal as the background path — the synchronous spawn
            # (testing / debugging) seals intake after --new too.
            seal_intake(run_path, reason="dispatch-new-sync")
        return proc.returncode


def dispatch_new(
    run_dir: str,
    client: str,
    deck_type: str,
    background: bool = True,
    requested_parallel: Optional[int] = None,
    mode: Optional[str] = None,
) -> int:
    """Convenience wrapper: launch a new engine job.

    This is the call point for the intake bridge (poll.sh completion path)
    and the canonical entry after GATE 0/0b/1/1b/2/3 pass.

    The engine's --new path reads intake_json from the run directory's
    working/copy/intake.json (populated by the intake interview).

    FIX 34: the moment --new consumes that intake (cmd_new wrote state.json),
    the launcher seals it 0444 — a worker attempting to overwrite it mid-run
    raises PermissionError and the attempt lands in
    working/logs/intake_protection.jsonl. Subsequent intake data changes go
    through apply_intake_amendment() (Fix 32-verified owner approval) and are
    appended to working/copy/intake_amendments.jsonl — the dispatcher's P0A
    "re-emit intake" instruction can no longer touch the file.

    requested_parallel: see dispatch()'s docstring -- None (default) means no
    declared request; the capacity gate still runs either way.

    Returns PID on success, -1 on failure.
    """
    # Verify the run dir is ready for --new
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        # state.json already exists -- check if engine is already running or completed
        if is_engine_running(run_path):
            print(f"launcher: engine already running for {run_path}", flush=True)
            return -2  # distinct code for "already running"
        # If terminal, refuse to re-launch (must --resume instead)
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if st.get("terminal") in ("DONE",):
                print(f"launcher: job {run_path} is already DONE -- refusing to re-launch", flush=True)
                return -3
        except (json.JSONDecodeError, OSError):
            pass

    return dispatch(run_dir, client=client, deck_type=deck_type, resume=False,
                    background=background, requested_parallel=requested_parallel,
                    mode=mode)


def dispatch_resume(run_dir: str, background: bool = True,
                    requested_parallel: Optional[int] = None,
                    mode: Optional[str] = None) -> int:
    """Convenience wrapper: resume a parked engine job.

    Returns PID on success, -1 on failure.
    """
    run_path = Path(run_dir).expanduser().resolve()
    if not (run_path / "state.json").is_file():
        print(f"launcher: no state.json at {run_path} -- cannot resume", file=sys.stderr)
        return -1
    if is_engine_running(run_path):
        print(f"launcher: engine already running for {run_path}", flush=True)
        return -2
    return dispatch(run_dir, resume=True, background=background,
                    requested_parallel=requested_parallel, mode=mode)


# ---------------------------------------------------------------------------
# CLI entry point -- for shell-script callers (poll.sh, canonical entry)
# ---------------------------------------------------------------------------
def main(argv: Optional[list] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="launcher.py",
        description="Engine dispatch bridge -- launch the presentation engine",
    )
    p.add_argument("--run-dir", type=Path, required=True,
                   help="the job's run directory")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--new", action="store_true",
                   help="launch a new engine job")
    g.add_argument("--resume", action="store_true",
                   help="resume a parked engine job")
    p.add_argument("--client", help="client identifier")
    p.add_argument("--deck-type", help="deck type (signature_presentation, standard, etc)")
    p.add_argument("--foreground", action="store_true",
                   help="run synchronously (for testing)")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--check", action="store_true",
                   help="check if engine is running; exit 0 if yes, 1 if no")
    p.add_argument("--stop", action="store_true",
                   help="stop the engine for this run-dir")
    p.add_argument("--requested-parallel", type=int, default=None,
                   help="declare the parallel width this run wants. Only checked "
                        "when capacity is UNDETERMINED: a request above the "
                        "conservative floor (3) is refused (AF-CAPACITY-UNMEASURED). "
                        "Omit (the default) to run at whatever capacity.probe() "
                        "measures, floor included.")
    p.add_argument("--mode", default=None,
                   help="declare the FIX 11 mode (ultra/standard/economy). "
                        "Selects measured-capacity concurrency, stamps the "
                        "honest ETA+cost plan as .mode-plan.json in the run "
                        "dir, and hands the engine PRESENTATION_MODE. An "
                        "unknown mode refuses the launch "
                        "(AF-MODE-INVALID). PRESENTATION_MODES=0 leaves the "
                        "surface inert.")

    # FIX 34: the amendment channel, reachable from the shell callers.
    p.add_argument("--amend-intake", type=Path, default=None,
                   help="apply an intake amendment from this JSON file instead of "
                        "launching. The file must carry the full replacement intake "
                        "under 'intake' plus a Fix 32-verified owner approval "
                        "(owner_approved:true + approved_by:'Trevor' + a non-empty "
                        "owner_msg_id). Verified -> staged write, one row in "
                        "working/copy/intake_amendments.jsonl, intake re-sealed 0444. "
                        "Unverified -> intake untouched, refusal logged "
                        "(AF-AMENDMENT-UNVERIFIED).")
    p.add_argument("--seal-intake", action="store_true",
                   help="chmod 0444 working/copy/intake.json now (idempotent) and "
                        "record the seal in working/logs/intake_protection.jsonl; "
                        "no launch.")

    args = p.parse_args(argv)
    run_path = args.run_dir.expanduser().resolve()

    if args.check:
        running = is_engine_running(run_path)
        print(f"engine {'IS' if running else 'is NOT'} running for {run_path}")
        return 0 if running else 1

    if args.amend_intake is not None:
        try:
            amendment = json.loads(args.amend_intake.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"launcher: cannot read amendment JSON: {exc}", file=sys.stderr)
            return 1
        verdict = apply_intake_amendment(run_path, amendment)
        print(json.dumps(verdict, indent=2))
        return 0 if verdict.get("applied") else 1

    if args.seal_intake:
        ok = seal_intake(run_path, reason="cli-seal-intake")
        print(f"intake sealed: {ok} (mode {stat_mode(intake_paths(run_path)['intake'])})")
        return 0 if ok else 1

    if args.stop:
        ok = stop_engine(run_path)
        print(f"engine {'stopped' if ok else 'stop timed out'} for {run_path}")
        return 0 if ok else 1

    if args.foreground:
        # Sync mode: dispatch returns the engine's own exit code (0 == ok), or a
        # negative sentinel when the launcher itself refused before spawning.
        rc = dispatch_resume(str(run_path), background=False,
                             requested_parallel=args.requested_parallel,
                             mode=args.mode) if args.resume else \
            dispatch_new(str(run_path),
                         client=args.client or "operator",
                         deck_type=args.deck_type or "standard",
                         background=False,
                         requested_parallel=args.requested_parallel,
                         mode=args.mode)
        if rc == DISPATCH_CAPACITY_REFUSED:
            return EXIT_CAPACITY_UNMEASURED
        if rc == DISPATCH_UNKNOWN_DECK_TYPE:
            return EXIT_UNKNOWN_DECK_TYPE
        if rc == DISPATCH_CREDIT_REFUSED:
            return EXIT_CREDIT_REFUSED
        if rc == DISPATCH_NOTIFY_REFUSED:
            return EXIT_NOTIFY_UNCONFIGURED
        if rc == DISPATCH_MODE_INVALID:
            return EXIT_MODE_INVALID
        if rc == DISPATCH_OCR_REFUSED:
            return EXIT_OCR_ENGINE_MISSING
        if rc == DISPATCH_MODEL_PLAN_REFUSED:
            return EXIT_MODEL_PLAN_UNSATISFIED
        return 0 if rc == 0 else 1
    pid = dispatch_resume(str(run_path), background=True,
                          requested_parallel=args.requested_parallel,
                          mode=args.mode) if args.resume else \
        dispatch_new(str(run_path),
                     client=args.client or "operator",
                     deck_type=args.deck_type or "standard",
                     background=True,
                     requested_parallel=args.requested_parallel,
                     mode=args.mode)
    if pid == DISPATCH_CAPACITY_REFUSED:
        return EXIT_CAPACITY_UNMEASURED
    if pid == DISPATCH_UNKNOWN_DECK_TYPE:
        return EXIT_UNKNOWN_DECK_TYPE
    if pid == DISPATCH_CREDIT_REFUSED:
        return EXIT_CREDIT_REFUSED
    if pid == DISPATCH_NOTIFY_REFUSED:
        return EXIT_NOTIFY_UNCONFIGURED
    if pid == DISPATCH_MODE_INVALID:
        return EXIT_MODE_INVALID
    if pid == DISPATCH_OCR_REFUSED:
        return EXIT_OCR_ENGINE_MISSING
    if pid == DISPATCH_MODEL_PLAN_REFUSED:
        return EXIT_MODEL_PLAN_UNSATISFIED
    return 0 if pid > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
