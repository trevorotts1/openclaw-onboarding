#!/usr/bin/env python3
"""Box-side bridge: pick a finished intake up from the app, write the run-dir
record, and trigger the presentation department (kanban card).

This is the SUBMIT-TRIGGER. When a client finishes the Presentation Interview
app, the app (or the Worker /api/intake sink) has the assembled intake record.
This bridge:

  ingest  -> pull the finished intake from the Worker (/api/intake or the
             session answer stream), write working/copy/intake.json +
             working/interview/intake_ledger.json via intake_writer.py, then
             call cc_board.ingest_deck_task() to open the Command Center kanban
             card (department_slug=presentations) — the presentation department
             start. No shortcuts: the deck can only build through
             presentation-canonical-entry.sh's governed gates.

PRES-008 — DURABLE SUBMISSION STATES, NOT A BOOLEAN LEDGER
----------------------------------------------------------
The old bridge declared a submission "processed" (a bare session id appended
to the poll ledger) whenever cmd_ingest returned 0 — and cmd_ingest returned 0
when the CC card existed EVEN WHEN the engine dispatch had been refused, and
when the worker's /api/dept-start answered 202 deferred. A submission the
engine never launched was excluded from every later poll: the deck stalled
with a card and no builder, and the bridge had lost the retry.

The bridge now drives every submission through launch_ledger.py's durable
per-submission state document (working/checkpoints/intake_submission_state.json
inside the run dir, atomic write, crash-safe):

    staged -> board_registered -> launch_pending -> launching
           -> worker_acknowledged           (handoff COMPLETE)
    failed_retryable  (an attempt failed; bounded backoff re-arms)
    blocked_actionable (permanent refusal / exhausted budget; remediation
                        recorded; other sessions keep progressing)

  - Handoff completes ONLY on a persisted current execution id PLUS a live
    worker-start acknowledgement (a held launch lease alone is NOT completion;
    a 202 deferred is NOT success; a bare rc 0 is NOT success).
  - The board task id and run binding persist through launch retries; the
    bridge never re-registers a card that exists (no duplicate cards).
  - A live existing worker's acknowledgement is an IDEMPOTENT success: resume
    discovers the running engine, acks the current execution, and starts no
    second executor.
  - Refusals/deferrals retry with bounded exponential backoff; CEO/operator
    notification thresholds fire once per threshold.
  - Completed intake records and checkpoints are never overwritten by a
    retry: the run-dir record is written exactly once, in `staged`.
  - A crash inside `launching` (between dispatch and ledger write) is
    recoverable: the next tick finds the live worker by its recorded pid,
    acks, and completes — one active execution per run, ownership recoverable
    (launch_ledger's claim TTL takes over a crashed poller's claim).

It mirrors the canonical intake-miniapp bridge (intake_bridge.py) for the
hosted-session path, and adds the /api/dept-start hand-off for the static-app
path. Stdlib only (urllib) — nothing to install on a box.

No secrets are printed. The box→worker admin token is read from env
INTAKE_ADMIN_TOKEN (never from argv, never logged).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid



HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:  # the durable submission-state machine sits next to this bridge
    import launch_ledger as _ll
except ImportError:  # pragma: no cover — a broken tree must name itself
    _ll = None

sys.path.insert(0, str(HERE.parent))

try:
    import intake_writer
except ImportError:
    # Allow running from a checkout where intake_writer.py sits next to us.
    import importlib.util  # noqa: F401
    intake_writer = None


def _load_by_file(mod_name: str, file_name: str) -> object | None:
    """Locate a sanctioned scripts/ sibling module (cc_board.py,
    operator_requester.py, ...) by file path across the candidate roots this
    bridge can run from -- a checkout, a deployed box, or PRESENTATIONS_SCRIPTS
    override. Same technique for every such module so all of them resolve the
    SAME box/checkout, never a mix."""
    for root in (
        pathlib.Path(os.environ.get("PRESENTATIONS_SCRIPTS", "")) if os.environ.get("PRESENTATIONS_SCRIPTS") else HERE.parent,
        HERE.parent.parent / "scripts",
        pathlib.Path.home() / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts",
    ):
        cand = root / file_name
        if cand.is_file():
            import importlib.util as _u
            spec = _u.spec_from_file_location(mod_name, cand)
            if spec and spec.loader:
                mod = _u.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def _load_cc_board() -> object | None:
    """Locate cc_board.py (the Command Center ingest helper) if available."""
    return _load_by_file("cc_board", "cc_board.py")


def _load_operator_requester() -> object | None:
    """Locate operator_requester.py (FIX F19's sanctioned OPERATOR chat-id
    fallback) if available. Returns None -- never raises -- when the module
    is not reachable from any candidate root; callers treat that exactly
    like 'nothing configured' (see resolve_operator_chat_id()'s own
    never-fabricate contract)."""
    return _load_by_file("operator_requester", "operator_requester.py")


# FIX F19: mirrors cc_board.py's _REQUESTER_ENV_KEYS / deck-intake-driver.py's
# _REQUESTER_ENV_KEYS byte-for-byte. Before this fix, this bridge was the ONLY
# intake path reading a DIFFERENT env var name (PRESENTER_CHAT_ID) for the
# identical purpose -- an app-submitted session and a CLI/dispatcher-driven
# session silently disagreed on where the requester lives, the exact
# divergent-intake-path disease behind FAULT-02/05/11. The canonical keys are
# now checked FIRST so both paths agree; PRESENTER_CHAT_ID is kept as a
# back-compat alias (see cmd_ingest() below) so an existing deployment's env
# export keeps working.
_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
)


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


# ---------------------------------------------------------------------------
# PRES-008 — launch-policy classification of launcher refusals.
#
# A dispatch refusal is not one thing. Environment faults (notify unconfigured,
# capacity unmeasured, credit preflight, OCR engine missing) are curable
# WITHOUT touching the intake — they retry with bounded backoff. A permanent
# refusal (deck type unresolvable, mode invalid, model plan unsatisfiable)
# would produce the same refusal on every retry forever, so it BLOCKS the
# submission with a remediation instead of consuming the retry budget.
# ---------------------------------------------------------------------------
#: launcher DISPATCH_* refusals that retry (curable environment faults).
RETRYABLE_REFUSAL_RCS = {-4, -6, -7, -8, -11}
#: launcher DISPATCH_* refusals that are permanent for this submission.
PERMANENT_REFUSAL_RCS = {-5, -9, -10}
#: -1 spawn failure / -2 already running / -3 already DONE are handled by
#: their own branches, never classified here.


def _refusal_summary(pid_rc: int) -> str:
    codes = {
        -4: "AF-CAPACITY-UNMEASURED",
        -5: "AF-DECK-TYPE-UNKNOWN",
        -6: "AF-CREDIT-PREFLIGHT",
        -7: "AF-NOTIFY-UNCONFIGURED",
        -8: "AF-OCR-ENGINE-MISSING",
        -9: "AF-MODE-INVALID",
        -10: "AF-MODEL-PLAN-UNSATISFIED",
        -11: "AF-MANIFEST-REPIN-FAILED",
        -1: "spawn failure",
        -2: "already running",
        -3: "already DONE",
    }
    return f"{codes.get(pid_rc, 'refused')} (rc={pid_rc})"


def _bridge_notify(message: str) -> None:
    """Best-effort operator notice via report.dispatch3("intake-bridge", ...).
    presentation_job/report.py is the ONE dispatch implementation in this
    codebase (shell-safe argv, subsystem-label resolution); when the package
    is not reachable the message lands in this process's stdout, which the
    poll cron captures — never silently dropped, never a fabricated send."""
    try:
        pj_pkg = _load_presentation_job()
        report = None
        if pj_pkg is not None:
            report = getattr(pj_pkg, "report", None)
        if report is None:
            try:
                import importlib as _importlib
                report = _importlib.import_module("presentation_job.report")
            except ImportError:
                report = None
        if report is not None and hasattr(report, "dispatch3"):
            report.dispatch3("intake-bridge", "pres008", message)
            return
    except Exception:  # noqa: BLE001 — notify must never break the bridge
        pass
    print(json.dumps({"status": "operator_notice", "channel": "stdout-fallback",
                      "message": message[:400]}), file=sys.stderr)


def _make_notifier():
    """Notifier callable handed to launch_ledger. The kind names the reason;
    every message goes through _bridge_notify exactly once per threshold."""
    def _notify(kind: str, submission_id: str, message: str) -> None:
        _bridge_notify(f"[{kind}] {message}")
    return _notify


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _retry_policy() -> dict:
    """Bounded-backoff policy from env (all knobs documented in launch_ledger)."""
    thresholds = os.environ.get("PRES008_NOTIFY_THRESHOLDS", "")
    parsed: list = []
    for part in thresholds.replace(" ", "").split(","):
        if part.isdigit():
            parsed.append(int(part))
    return {
        "backoff_base_s": _env_float("PRES008_BACKOFF_BASE_S", _ll.DEFAULT_BACKOFF_BASE_S),
        "backoff_cap_s": _env_float("PRES008_BACKOFF_CAP_S", _ll.DEFAULT_BACKOFF_CAP_S),
        "max_attempts": _env_int("PRES008_MAX_RETRY_ATTEMPTS", _ll.DEFAULT_MAX_RETRY_ATTEMPTS),
        "notify_thresholds": tuple(parsed) if parsed else _ll.DEFAULT_NOTIFY_THRESHOLDS,
        "claim_ttl_s": _env_float("PRES008_CLAIM_TTL_S", _ll.DEFAULT_CLAIM_TTL_S),
    }


def _submission_hold(run_dir, session_id: str, policy: dict,
                     *, initial: str = "staged",
                     holder: dict | None = None,
                     run_dir_str: str = "") -> dict:
    """Acquire (fresh) or re-acquire (this poller's own claim) the durable
    state document for this submission. A LIVE FOREIGN claim returns {} —
    the caller skips this session this tick (one active execution per run;
    the claim is recoverable after the claim TTL). A CORRUPT state file is
    quarantined into an explicit blocked_actionable document (never silently
    reset, never a permanent skip)."""
    doc = _ll.load(run_dir, session_id)
    if doc is not None:
        if _ll.claim_is_fresh(doc, (holder or {}).get("claimed_by", ""),
                              ttl_s=policy["claim_ttl_s"]):
            return {}
        return _ll.reclaim(run_dir, session_id, doc, holder=holder)
    fresh = _ll.acquire_new(run_dir, session_id, initial=initial, holder=holder,
                            run_dir_str=run_dir_str)
    if fresh is not None:
        return fresh
    # acquire_new failed two ways: (a) a live foreign claimant won the race —
    # skip this tick; (b) an UNREADABLE state file blocks the O_EXCL create.
    # Distinguish: load() returned None for an EXISTING file => corrupt.
    if _ll.state_path(run_dir, session_id).exists():
        return _ll.quarantine_corrupt(run_dir, session_id)
    return {}


def _record_run_dir_files(run_dir: pathlib.Path, intake: dict, verbose: bool) -> bool:
    """Write the run-dir record EXACTLY ONCE (PRES-008: never overwrite a
    completed intake/checkpoint on retry). Idempotent by content: when
    working/copy/intake.json already exists this is a no-op — the retry
    re-reads what the first attempt wrote, and the engine's sealed intake
    (0444, launcher FIX 34) is never touched."""
    intake_path = run_dir / "working" / "copy" / "intake.json"
    if intake_path.is_file():
        if verbose:
            print(f"run-dir record already present under {run_dir}/working/ -- "
                  "retry keeps it (never overwrites completed intake)", file=sys.stderr)
        return True
    if intake_writer is None:
        return False
    intake_writer.migrate_intake(intake)
    missing = intake_writer.validate_intake_completeness(intake)
    if missing:
        raise ValueError("required canonical fields missing: " + ", ".join(missing))
    run_dir.mkdir(parents=True, exist_ok=True)
    intake_writer.write_intake_file(run_dir, intake)
    intake_writer.write_ledger(run_dir, intake)
    if hasattr(intake_writer, "write_transcript"):
        intake_writer.write_transcript(run_dir, intake)
    intake_writer.emit_configuration_pending_events(run_dir, intake, intake.get("intake_session_id", ""))
    if verbose:
        print(f"wrote run-dir record under {run_dir}/working/")
    return True


def _ensure_board_card(run_dir: pathlib.Path, intake: dict, session_id: str,
                       doc: dict, policy: dict) -> tuple[str, str]:
    """Register (or recover) the CC kanban card. Returns (state, task_id):

      "registered", task_id  -- card exists (freshly created, recovered from
                                the submission record, or recovered from the
                                run manifest)
      "unavailable", ""      -- board transport/config failure: retryable

    Dedup by construction: the submission's board_task_id persists across
    retries, so a retry NEVER re-ingests a card that exists; when the
    submission record predates the manifest stamp, the manifest's cc_task_id
    is adopted instead of minting a second card. cc_board.ingest_deck_task is
    itself idempotent (sha256(source_ref+title) key server-side) — the local
    record makes that idempotency durable across bridge restarts.
    """
    existing = str(doc.get("board_task_id") or "").strip()
    if existing:
        return "registered", existing
    manifest_task = ""
    try:
        man = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if man.is_file():
            manifest_task = str((json.loads(man.read_text(encoding="utf-8"))
                                 .get("cc_task_id")) or "").strip()
    except (OSError, ValueError):
        manifest_task = ""
    if manifest_task:
        return "registered", manifest_task
    cc = _load_cc_board()
    if cc is not None and hasattr(cc, "ingest_deck_task"):
        brief = intake.get("deck_brief") or {}
        title = brief.get("OFFER_NAME") or intake.get("intake_session_id") or session_id
        desc = (f"Intake captured by the Presentation Interview app ({session_id}).\n"
                + json.dumps(intake.get("deck_brief") or intake.get("answers") or {},
                             indent=2))
        # FIX F19: the requester already stamped onto `intake` (canonical env
        # vars -> PRESENTER_CHAT_ID back-compat -> operator fallback) — CC-board
        # registration and the engine's working/copy/intake.json never disagree.
        task_id = cc.ingest_deck_task(
            run_dir,
            deck_slug=session_id,
            title=f"Deck — {title}",
            description=desc,
            priority="medium",
            requester_chat_id=intake.get("requester_chat_id", ""),
        )
        if task_id:
            return "registered", str(task_id)
        # FIX F12/PRES-008: None = no card exists. Retryable — never success.
        return "unavailable", ""
    return "no-cc-board", ""


def _dispatch_launch(run_dir: pathlib.Path, intake: dict, session_id: str,
                     doc: dict, policy: dict, verbose: bool) -> tuple[str, str]:
    """Attempt the engine launch for an already-registered submission.

    Returns (verdict, detail):
      "launched"            -- engine process spawned under the run lease;
                               submission moves to launching, then completes
                               on the live-worker acknowledgement below.
      "refused_retryable"   -- environment refusal: bounded backoff re-arms.
      "refused_permanent"   -- permanent refusal: blocked_actionable.
      "lease_held"          -- another actor owns the dispatch window; the
                               submission stays launch_pending (a held lease
                               alone is NEVER completion).
      "no_engine"           -- presentation_job unreachable: retryable.
      "acknowledged"        -- a live existing worker was discovered and its
                               start acknowledged (idempotent success).
    """
    pj = _load_presentation_job()
    if pj is None:
        return "no_engine", "presentation_job not reachable"
    launcher = getattr(pj, "launcher", None)
    lease_mod = getattr(pj, "lease", None)
    if launcher is None or lease_mod is None:
        try:
            import importlib as _importlib
            if launcher is None:
                launcher = _importlib.import_module("presentation_job.launcher")
            if lease_mod is None:
                lease_mod = _importlib.import_module("presentation_job.lease")
        except ImportError as exc:
            return "no_engine", f"presentation_job incomplete: {exc}"

    # A live existing worker is an idempotent success: discover it BEFORE any
    # spawn — the crash-window recovery (state.json/.engine.pid named a pid
    # that is alive) completes the handoff without a second executor.
    if _ll.engine_alive(run_dir):
        exec_id = _ll.execution_id_of(run_dir)
        if exec_id:
            _ll.mark_worker_acknowledged(
                run_dir, session_id, doc, exec_id,
                engine_pid=_ll._read_run_state(run_dir).get("pid"),
                note="existing live worker discovered; acknowledgement idempotent")
            return "acknowledged", f"live worker holds the run ({exec_id})"

    deck_type = str(intake.get("deck_type") or "").strip()
    client = str(intake.get("requester_chat_id") or intake.get("intake_session_id")
                 or session_id or "").strip() or "operator"
    holder = {"who": "intake-bridge", "session_id": session_id}
    lease = None
    try:
        lease = lease_mod.acquire(run_dir, holder=holder,
                                  ttl_s=lease_mod.DEFAULT_TTL_S, wait_s=30.0)
        if lease is None:
            lease_doc = lease_mod.read(run_dir) or {}
            return ("lease_held",
                    "lease held by pid {pid} on host {host}; submission stays "
                    "launch_pending for the next tick".format(
                        pid=lease_doc.get("pid"), host=lease_doc.get("host")))
        exec_id = _ll.mint_execution_id(lease)
        pid = launcher.dispatch_new(str(run_dir), client=client,
                                    deck_type=deck_type, background=True)
        if isinstance(pid, int) and pid > 0:
            _ll.mark_launching(run_dir, session_id, doc, exec_id,
                               why="dispatch in flight under run lease")
            # The launcher forked an engine. Completion still waits for the
            # LIVE-worker proof: state.json/.engine.pid naming a live pid.
            live = _ll.engine_alive(run_dir)
            live_exec = _ll.execution_id_of(run_dir) or exec_id
            if live and live_exec:
                _ll.mark_worker_acknowledged(
                    run_dir, session_id, _ll.load(run_dir, session_id) or doc,
                    live_exec, engine_pid=pid,
                    note="engine spawned and holds the run")
                return "launched", f"engine dispatched (pid {pid}) and acknowledged"
            return "launched", (f"engine dispatched (pid {pid}) — awaiting the "
                                "live-worker acknowledgement on the next tick")
        if pid in PERMANENT_REFUSAL_RCS:
            _ll.mark_blocked(
                run_dir, session_id, _ll.load(run_dir, session_id) or doc,
                reason=f"engine dispatch permanently refused: {_refusal_summary(pid)} "
                       f"(deck_type {deck_type!r})",
                remediation=(
                    "fix the submission's deck_type/mode/model-plan (see the "
                    "refusal code in this submission's state file), correct "
                    "the intake if the deck type itself is wrong, then delete "
                    f"{_ll.state_path(run_dir, session_id)} to re-drive it"),
                notify=True, notifier=_make_notifier())
            return "refused_permanent", _refusal_summary(pid)
        if pid in RETRYABLE_REFUSAL_RCS:
            return "refused_retryable", _refusal_summary(pid)
        if pid == -2:
            # Already running: a worker exists that our pid probe could not
            # see (started between probe and spawn). Treat as the discover path.
            live_exec = _ll.execution_id_of(run_dir) or exec_id
            _ll.mark_worker_acknowledged(
                run_dir, session_id, _ll.load(run_dir, session_id) or doc,
                live_exec, note="launcher reports the engine already running")
            return "acknowledged", "engine already running (idempotent ack)"
        if pid == -3:
            return "acknowledged", "run already DONE (idempotent ack)"
        return "refused_retryable", _refusal_summary(pid)
    except Exception as exc:  # noqa: BLE001 — a dispatch failure must never break ingest
        return "refused_retryable", f"dispatch error: {type(exc).__name__}: {exc}"
    finally:
        if lease is not None:
            try:
                lease_mod.release(lease)
            except Exception:  # noqa: BLE001
                pass


def _mark_handoff_failure(run_dir: pathlib.Path, session_id: str, doc: dict,
                          policy: dict, failure_class: str, reason: str,
                          permanent_note: str = "") -> dict:
    """Route one failed attempt into the bounded retry (or block it when the
    refusal is permanent). The state document carries the truth even if this
    process dies before returning."""
    return _ll.mark_retry_pending(
        run_dir, session_id, doc, reason, failure_class=failure_class,
        backoff_base_s=policy["backoff_base_s"],
        backoff_cap_s=policy["backoff_cap_s"],
        max_attempts=policy["max_attempts"],
        notify_thresholds=policy["notify_thresholds"],
        notifier=_make_notifier())


def _out(rc: int, report: dict) -> dict:
    """Stamp the bridge rc (the durable-state rc contract) onto a report."""
    report["_rc"] = rc
    report.setdefault("state", "")
    return report


def _drive_submission(run_dir: pathlib.Path, intake: dict, session_id: str,
                      policy: dict, verbose: bool) -> dict:
    """Drive ONE submission through the durable states toward completion.

    Acquires the per-tick driver claim, then delegates to
    _drive_submission_claimed; releases the claim afterwards (any verdict).
    Returns a report dict carrying "_rc" — the bridge rc, which is 0 ONLY when
    the submission's handoff is COMPLETE (worker_acknowledged) — never on a
    deferral, never on a refusal, never on "card created but engine not
    launched". The poll loop maps that rc onto the durable state, never onto a
    boolean ledger.
    """
    doc = _submission_hold(run_dir, session_id, policy,
                           holder={"claimed_by": _poller_id()}, run_dir_str=str(run_dir))
    if not doc:
        return _out(7, {"verdict": "claim_held_elsewhere",
                        "detail": "a live claim by another poller holds this submission"})
    try:
        return _drive_submission_claimed(run_dir, intake, session_id, policy,
                                         verbose, doc)
    finally:
        # The claim serialized THIS tick's concurrent drivers; release it so
        # the next tick re-drives without waiting out the claim TTL. A
        # crashed driver never reaches this — its stale claim is taken over
        # after the TTL (recoverable ownership).
        latest = _ll.load(run_dir, session_id)
        if latest is not None:
            _ll.release_claim(run_dir, session_id, latest)


def _drive_submission_claimed(run_dir: pathlib.Path, intake: dict,
                              session_id: str, policy: dict, verbose: bool,
                              doc: dict) -> dict:

    # Complete stays complete (idempotent re-poll).
    if _ll.is_complete(doc):
        return _out(0, {"verdict": "already_complete", "state": _ll.WORKER_ACKNOWLEDGED,
                        "detail": _ll.describe(doc)})
    # Blocked stops consuming retries — other sessions keep progressing.
    if _ll.is_blocked(doc):
        return _out(8, {"verdict": "blocked", "state": _ll.BLOCKED_ACTIONABLE,
                        "detail": doc.get("blocked", {}).get("reason", ""),
                        "remediation": doc.get("blocked", {}).get("remediation", "")})
    # Bounded backoff: not due yet.
    if not _ll.due_for_retry(doc):
        return _out(7, {"verdict": "backoff", "state": doc.get("state"),
                        "detail": f"next retry at {doc.get('next_retry_at')} "
                                  f"(attempt {doc.get('retry_attempt') or 0})"})

    # 1) the run-dir record — exactly once, in staged.
    try:
        record_ok = _record_run_dir_files(run_dir, intake, verbose)
    except Exception as exc:  # noqa: BLE001 — classified below
        record_ok = exc
    if isinstance(record_ok, Exception):
        # A PERMANENT intake-grounding refusal (UngroundedDeckTypeError /
        # RunModeVocabularyError: no real presentation_type / run-mode answer
        # exists) would fail identically on every retry — PRES-008 surfaces it
        # as blocked_actionable with a remediation, while other sessions
        # progress. Nothing was written (the writer fails closed).
        if type(exc := record_ok).__name__ in ("UngroundedDeckTypeError",
                                               "RunModeVocabularyError"):
            doc = _ll.load(run_dir, session_id) or doc
            _ll.mark_blocked(
                run_dir, session_id, doc,
                reason=f"intake permanently ungrounded: {type(record_ok).__name__}: "
                       f"{str(record_ok)[:300]}",
                remediation=("the intake is missing the presentation_type / "
                             "run-mode answer the deck-type axis requires — "
                             "collect it (or amend the intake via the sanctioned "
                             "amendment path), then delete this submission state "
                             f"file ({_ll.state_path(run_dir, session_id)}) to "
                             "re-drive it"),
                notify=True, notifier=_make_notifier())
            return _out(8, {"verdict": "blocked", "state": _ll.BLOCKED_ACTIONABLE,
                            "detail": f"intake permanently ungrounded: {type(record_ok).__name__}"})
        # Any other writer fault is an environment problem: retryable.
        doc = _ll.load(run_dir, session_id) or doc
        _mark_handoff_failure(run_dir, session_id, doc, policy,
                              "intake_write_failed",
                              f"{type(record_ok).__name__}: {record_ok}")
        return _out(2, {"verdict": "retry_scheduled",
                        "detail": f"run-dir record write failed ({type(record_ok).__name__}); retry scheduled"})
    if not record_ok:
        doc = _ll.load(run_dir, session_id) or doc
        _mark_handoff_failure(run_dir, session_id, doc, policy,
                              "intake_write_failed",
                              "intake_writer.py not importable — cannot stamp the run dir")
        return _out(2, {"verdict": "retry_scheduled",
                        "detail": "run-dir record unavailable; retry scheduled"})

    # 2) the board card — persisted BEFORE any launch attempt, so the binding
    #    survives launch retries and the card is never duplicated.
    board_state, task_id = _ensure_board_card(run_dir, intake, session_id, doc, policy)
    if board_state == "registered":
        doc = _ll.load(run_dir, session_id) or doc
        if str(doc.get("board_task_id") or "") != task_id or doc.get("state") == _ll.STAGED:
            doc = _ll.transition(run_dir, session_id, doc, _ll.BOARD_REGISTERED,
                                 board_task_id=task_id,
                                 why="board card registered/recovered")
    elif board_state == "unavailable":
        doc = _ll.load(run_dir, session_id) or doc
        _mark_handoff_failure(run_dir, session_id, doc, policy,
                              "board_unavailable",
                              "cc_board.ingest_deck_task returned None (board URL "
                              "unset or transport failure); retry scheduled")
        return _out(5, {"verdict": "retry_scheduled",
                        "detail": "board card unavailable; retry scheduled"})
    else:  # "no-cc-board": the worker /api/dept-start fallback path
        rc, note = _dept_start_via_worker(session_id, intake)
        if rc != 0:
            doc = _ll.load(run_dir, session_id) or doc
            _mark_handoff_failure(run_dir, session_id, doc, policy,
                                  "worker_deferred" if rc == 202 else "board_unavailable",
                                  note)
            return _out(7 if rc == 202 else 4, {
                "verdict": "retry_scheduled",
                "detail": note})
        # The worker acked the start intent — but PRES-008 completion still
        # requires a live worker on THIS run dir. The worker-created card and
        # engine become discoverable on the next poll via _dispatch_launch's
        # discovery path; record the binding and go launch_pending.
        doc = _ll.load(run_dir, session_id) or doc
        if doc.get("state") == _ll.STAGED:
            doc = _ll.transition(run_dir, session_id, doc, _ll.BOARD_REGISTERED,
                                 board_worker_ack=True,
                                 why="worker /api/dept-start accepted the start")
        doc = _ll.load(run_dir, session_id) or doc
        doc = _ll.transition(run_dir, session_id, doc, _ll.LAUNCH_PENDING,
                             why="worker accepted the start; awaiting a live worker")
        return _out(7, {"verdict": "launch_pending",
                        "detail": "worker accepted the start; completion waits for a "
                                  "live worker on the run dir"})

    # 3) the launch — under the run lease, idempotent on a live worker.
    doc = _ll.load(run_dir, session_id) or doc
    verdict, detail = _dispatch_launch(run_dir, intake, session_id, doc, policy,
                                       verbose)
    if verdict == "acknowledged":
        return _out(0, {"verdict": "complete", "state": _ll.WORKER_ACKNOWLEDGED,
                        "detail": detail})
    if verdict == "launched":
        doc = _ll.load(run_dir, session_id) or doc
        if _ll.is_complete(doc):
            return _out(0, {"verdict": "complete", "state": _ll.WORKER_ACKNOWLEDGED,
                            "detail": detail})
        return _out(7, {"verdict": "launching", "state": doc.get("state"),
                        "detail": detail})
    if verdict == "lease_held":
        return _out(7, {"verdict": "launch_pending", "state": doc.get("state"),
                        "detail": detail})
    if verdict == "refused_permanent":
        return _out(8, {"verdict": "blocked", "state": _ll.BLOCKED_ACTIONABLE,
                        "detail": detail})
    if verdict == "no_engine":
        doc = _ll.load(run_dir, session_id) or doc
        _mark_handoff_failure(run_dir, session_id, doc, policy,
                              "engine_unavailable", detail)
        return _out(6, {"verdict": "retry_scheduled",
                        "detail": detail})
    # refused_retryable
    doc = _ll.load(run_dir, session_id) or doc
    _mark_handoff_failure(run_dir, session_id, doc, policy,
                          "dispatch_refused", detail)
    doc = _ll.load(run_dir, session_id) or doc
    return _out(7, {"verdict": "retry_scheduled", "state": doc.get("state"),
                    "detail": detail})


def _poller_id() -> str:
    """This poller process's claim identity (per-process, so two concurrent
    pollers never mistake each other for themselves — even two pollers born
    in the same second, whose pid@second stamps would collide)."""
    return f"pid:{os.getpid()}@{uuid.uuid4().hex[:8]}"


def _dept_start_via_worker(session_id: str, intake: dict) -> tuple[int, str]:
    """The Worker /api/dept-start fallback. Returns (http_status_or_rc, note).
    A 202 'deferred' is NOT success (PRES-008): it means COMMAND_CENTER_URL is
    unset on the worker and the card does not exist — the submission stays
    unprocessed and retries."""
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    status, resp = _http("POST", _DEPT_START_URL.rstrip("/") + "/api/dept-start",
                         token=admin,
                         body={"intake_session_id": session_id, "intake": intake})
    if status in (200, 201):
        return status, json.dumps(resp)
    if status == 202:
        return 202, ("worker returned 202 deferred (COMMAND_CENTER_URL unset) — "
                     "NOT success; submission stays unprocessed and retries")
    return status, f"dept-start failed (HTTP {status}): {resp.get('error')}"


_DEPT_START_URL = ""  # set from args before _dept_start_via_worker runs


def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None,
          timeout: int = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    # Browser-like UA so Cloudflare's bot check does not 1010-block the bridge.
    req.add_header("user-agent", _UA)
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:200]}


def _fetch_intake(args) -> dict:
    """Fetch the finished intake record from the Worker (by session id).

    PRES-009 QC repair (F3c): carries the box's tenant scope alongside the id
    (see _scoped_query) — a tuple-stored intake is only reachable through its
    own tenant scope; an unscoped fetch returns only pre-tenant flat rows.
    """
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    if not admin:
        raise RuntimeError("INTAKE_ADMIN_TOKEN not set in env")
    base = args.worker_url.rstrip("/") + "/api/intake?id=" + urllib.parse.quote(str(args.session_id), safe="")
    url = base + _scoped_query(args).replace("?", "&")
    status, resp = _http("GET", url, token=admin)
    if status != 200:
        raise RuntimeError(f"intake fetch failed (HTTP {status}): {resp.get('error')}")
    return resp


def stamp_requester(intake: dict, env: dict | None = None,
                    load_operator_requester=_load_operator_requester) -> dict:
    """Stamp requester_chat_id/requester_channel onto `intake` IN PLACE from a
    legitimate source, and return it (for easy call-site chaining). Never
    overwrites a value the app itself already supplied. Extracted to its own
    function (FIX F19) so this resolution order is unit-testable without
    driving the network-calling parts of cmd_ingest().

    Order (see operator_requester.py's docstring for the full rationale):
      1. the canonical chat-surface env vars every other intake path already
         reads (_REQUESTER_ENV_KEYS above -- the real client's identity, when
         a dispatcher exported it) -- this is the RIGHT source for a real
         client order and always wins when present;
      2. PRESENTER_CHAT_ID, kept ONLY as a back-compat alias for an existing
         deployment's env export (this bridge used to read ONLY this name --
         see the fix/deck-type-routing-bypass follow-up this replaces);
      3. the sanctioned OPERATOR fallback (operator_requester.py) for a
         genuinely operator-run app session that has neither -- never a
         client identity, never invented.
    `load_operator_requester` is injectable for tests (default: the real
    file-path loader above).
    """
    src_env = env if env is not None else os.environ
    if str(intake.get("requester_chat_id") or "").strip():
        return intake
    chat_id = ""
    channel = ""
    for key in _REQUESTER_ENV_KEYS:
        val = str(src_env.get(key) or "").strip()
        if val:
            chat_id = val
            break
    if not chat_id:
        chat_id = str(src_env.get("PRESENTER_CHAT_ID") or "").strip()
    if chat_id:
        channel = (
            str(src_env.get("PRESENTATION_REQUESTER_CHANNEL") or "").strip()
            or str(src_env.get("PRESENTER_CHANNEL") or "").strip()
            or "telegram"
        )
    else:
        op_mod = load_operator_requester()
        if op_mod is not None and hasattr(op_mod, "resolve_operator_chat_id"):
            chat_id, channel = op_mod.resolve_operator_chat_id()
    if chat_id:
        intake["requester_chat_id"] = chat_id
        intake["requester_channel"] = channel or "telegram"
    return intake


def _load_presentation_job():
    """Locate the presentation_job package root (the scripts/ directory that
    CONTAINS it) the same way every other sanctioned sibling is resolved here:
    by file path across the candidate roots, never a mix of boxes/checkouts.
    Candidate layouts covered:
      PRESENTATIONS_SCRIPTS override (deployed boxes);
      <presentations>/scripts (this checkout: interview-app sits under
      presentations/intake/, so presentations/ is HERE x3 parents up);
      <intake>/scripts and the OC workspace path (other deployed shapes).
    Returns the imported package or None -- never raises (a box without the
    department scripts installed keeps its pre-FIX-61 behavior)."""
    for root in (
        pathlib.Path(os.environ["PRESENTATIONS_SCRIPTS"]) if os.environ.get("PRESENTATIONS_SCRIPTS") else None,
        HERE.parent.parent.parent / "scripts",
        HERE.parent.parent / "scripts",
        pathlib.Path.home() / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts",
    ):
        if root is None:
            continue
        if (root / "presentation_job" / "launcher.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                import presentation_job  # noqa: F401
                return presentation_job
            except ImportError:
                continue
    return None


def cmd_ingest(args) -> int:
    """PRES-008: one submission, driven through the durable states. The return
    code mirrors the submission's DURABLE STATE, never a boolean 'processed':

      0  worker_acknowledged  — handoff COMPLETE (current execution id + live
                                worker start acknowledged)
      2  run-dir record unavailable            -> failed_retryable
      4  board transport unreachable           -> failed_retryable
      5  board card unavailable (ingest None)  -> failed_retryable
      6  engine unavailable                    -> failed_retryable
      7  deferred (launch_pending / backoff /
                claim held / worker 202)      -> stays retryable
      8  blocked_actionable — permanent refusal or exhausted budget
    """
    intake_payload = _fetch_intake(args)
    intake = intake_payload.get("intake") or intake_payload
    intake.setdefault("intake_session_id", args.session_id)

    # fix/deck-type-routing-bypass follow-up, extended by FIX F19: this
    # bridge needs a requester_chat_id stamped into `intake` itself, here,
    # BEFORE intake_writer.write_intake_file() persists it as
    # working/copy/intake.json -- the ONE file the engine's
    # resolve_intake.py reads -- or an app-submitted deck's engine job could
    # never report to the client who submitted it. See stamp_requester()'s
    # own docstring for the full resolution order.
    stamp_requester(intake)

    # PRES-008: per-session directories are the DEFAULT and a shared target
    # directory for multiple submissions is forbidden (see
    # _per_session_dirs_active).
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    if _per_session_dirs_active(args, intakes=1):
        run_dir = run_dir / args.session_id

    policy = _retry_policy()
    if _ll is None:
        print("error: launch_ledger.py not importable — cannot drive durable "
              "submission states (PRES-008)", file=sys.stderr)
        return 2

    global _DEPT_START_URL
    _DEPT_START_URL = args.worker_url  # the fallback posts to the SAME worker

    report = _drive_submission(run_dir, intake, args.session_id, policy,
                               verbose=bool(getattr(args, "verbose", False)))
    rc = report.get("_rc")
    verdict = report.get("verdict")
    print(json.dumps({"status": verdict, "session_id": args.session_id,
                      "run_dir": str(run_dir),
                      "state": (report.get("state") or ""),
                      **{k: v for k, v in report.items()
                         if k not in ("_rc", "verdict")}}),
          file=(sys.stderr if rc else sys.stdout))
    return rc



def _per_session_dirs_active(args, intakes: int = 1) -> bool:
    """PRES-008: per-session directories are the DEFAULT. A legacy opt-out is
    honored ONLY for a root that provably holds one submission — a shared
    target directory for MULTIPLE submissions is forbidden outright (two
    submissions in one run dir would race one lease, one engine pid slot, one
    state document). Returns True when the submission must stamp under
    <run-dir>/<session-id>/."""
    if getattr(args, "per_session_dirs", True):
        return True
    return intakes > 1  # the forbidden shape: opt-out overridden, never shared


def _tenant_scope(args) -> tuple[str, str]:
    """PRES-009 QC repair (F3c): the box's tenant identity for worker scoping.

    Resolution order: explicit CLI args (--company-id/--installation-id) then
    the per-box env (INTAKE_COMPANY_ID / INTAKE_INSTALLATION_ID). Both must be
    present for the bridge to present tenant scope to the worker; with only
    one set the scope is invalid and is NOT sent (the worker then serves only
    pre-tenant flat rows — fail closed, never a half-tuple guess).
    """
    company = str(getattr(args, "company_id", "") or os.environ.get("INTAKE_COMPANY_ID", "") or "")
    installation = str(getattr(args, "installation_id", "") or os.environ.get("INTAKE_INSTALLATION_ID", "") or "")
    return company, installation


def _scoped_query(args) -> str:
    """Query-string fragment carrying the tenant scope, '' when unscoped."""
    company, installation = _tenant_scope(args)
    if company and installation:
        return "?company_id=" + urllib.parse.quote(company, safe="") \
            + "&installation_id=" + urllib.parse.quote(installation, safe="")
    return ""


def _list_intakes(args) -> list:
    """GET /api/intake/list — enumerate finished intakes stored in the worker.

    PRES-009 QC repair (F3c): the list call now carries the box's
    company_id + installation_id (CLI args override INTAKE_COMPANY_ID /
    INTAKE_INSTALLATION_ID env) so the worker returns ONLY this tenant's rows.
    The old unscoped call returned every tenant's active intakes to whichever
    box held the admin token, and (on the R2 worker) derived session ids from
    key paths the opaque-id validator then rejects.
    """
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    if not admin:
        raise RuntimeError("INTAKE_ADMIN_TOKEN not set in env")
    url = args.worker_url.rstrip("/") + "/api/intake/list" + _scoped_query(args)
    status, resp = _http("GET", url, token=admin)
    if status != 200:
        raise RuntimeError(f"intake list failed (HTTP {status}): {resp.get('error')}")
    return resp.get("intakes") or []


def _processed_ledger(args) -> set:
    """Read the poll ledger (session ids already ingested) if present."""
    if not getattr(args, "poll_ledger", ""):
        return set()
    led = pathlib.Path(args.poll_ledger).expanduser()
    try:
        return set(led.read_text().split())
    except FileNotFoundError:
        return set()


def _mark_processed(args, session_id: str) -> None:
    """Append a session id to the poll ledger (idempotent — a session is ingested once)."""
    led = pathlib.Path(args.poll_ledger).expanduser()
    led.parent.mkdir(parents=True, exist_ok=True)
    done = _processed_ledger(args)
    done.add(session_id)
    led.write_text("\n".join(sorted(done)) + "\n")


def _valid_session_id(sid: object) -> bool:
    """PRES-009: a session id may become a filesystem path segment (per-session
    run dirs) and a poll-ledger token. Accept ONLY opaque ids — 3-64 chars,
    start alphanumeric, then [A-Za-z0-9._-]; never '/', '\\', '..' or control
    characters. The old code appended whatever the worker returned unvalidated:
    a traversal-shaped sid ("../other-run", an absolute path, "a/../b") could
    stamp a run dir OUTSIDE the configured root."""
    if not isinstance(sid, str):
        return False
    if len(sid) < 3 or len(sid) > 64:
        return False
    if "/" in sid or "\\" in sid or "\x00" in sid or ".." in sid:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", sid))


def _shared_dir_forbidden(args, sid: str) -> bool:
    """PRES-009: per-session dirs are OFF and the ledger already holds at least
    one DIFFERENT session — this submission would share its target directory.
    True (forbidden)."""
    processed = _processed_ledger(args)
    return any(other != sid for other in processed)


def cmd_poll(args) -> int:
    """PRES-008: discover finished intakes and drive each through the durable
    submission states. There is NO boolean processed ledger any more — a
    session's durable state document (working/checkpoints/
    intake_submission_state.json inside its own run dir) is the only
    processed/complete record, and it is only terminal at
    worker_acknowledged or blocked_actionable. rc=0 from cmd_ingest means
    COMPLETE, never merely "the card exists": 202 deferrals, dispatch
    refusals, held leases, and backoff all leave the submission retryable,
    so the next poll re-drives it."""
    if _ll is None:
        print("error: launch_ledger.py not importable — cannot drive durable "
              "submission states (PRES-008)", file=sys.stderr)
        return 2
    try:
        intakes = _list_intakes(args)
    except Exception as exc:  # noqa: BLE001 — a list failure is whole-batch, not per-session
        print(json.dumps({"status": "poll_list_failed",
                          "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 3
    if args.verbose:
        print(f"poll: {len(intakes)} stored intake(s) discovered")
    policy = _retry_policy()
    completed = 0
    deferred = 0
    blocked = 0
    crashes = 0
    rejected = 0
    for it in intakes:
        sid = it.get("session_id")
        if not _valid_session_id(sid):
            # PRES-009: a malformed/traversal-shaped sid is never appended to
            # any path and never added to the ledger — it is reported and
            # skipped so the operator can see the source refusing it.
            rejected += 1
            print(json.dumps({"status": "invalid_session_id_rejected",
                              "session_id": sid if isinstance(sid, str) else repr(sid),
                              "reason": "opaque-id validation failed; not used as a path or ledger token"}),
                  file=sys.stderr)
            continue
        # PRES-008: per-session directories are the DEFAULT; a shared target
        # directory for multiple submissions is forbidden. --no-per-session-dirs
        # is the explicit legacy opt-out for a single-session run root.
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        if _per_session_dirs_active(args, intakes=len(intakes)):
            run_dir = run_dir / sid
        elif _shared_dir_forbidden(args, sid):
            print(json.dumps({"status": "shared_target_dir_forbidden",
                              "session_id": sid,
                              "reason": "per-session dirs are OFF but the poll ledger already holds another session; pass --per-session-dirs (default) so submissions never share one run dir"}),
                  file=sys.stderr)
            rejected += 1
            continue
        # Reuse the ingest machinery via a synthetic args namespace.
        # PRES-009 QC repair (F3c): carry the tenant scope into cmd_ingest so
        # its /api/intake?id= fetch is tenant-scoped like the list call.
        sub = argparse.Namespace(
            worker_url=args.worker_url, session_id=sid, run_dir=str(run_dir),
            company_id=getattr(args, "company_id", ""),
            installation_id=getattr(args, "installation_id", ""),
            verbose=args.verbose, func=cmd_ingest,
            per_session_dirs=False, no_per_session_dirs=False,
        )
        # FIX F13 (retained): one poison session (malformed payload, transport
        # crash) must never raise out of the loop — every other waiting session
        # behind it still gets its tick. A crash leaves the durable state
        # untouched, so the next poll re-drives the session. SystemExit
        # included: _fetch_intake/_list_intakes raise RuntimeError now, but a
        # module still calling sys.exit must not take the batch down.
        try:
            rc = cmd_ingest(sub)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — poll must survive any single bad session
            crashes += 1
            print(json.dumps({"status": "ingest_crashed", "session_id": sid,
                              "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
            continue
        if rc == 0:
            completed += 1
        elif rc == 8:
            blocked += 1
        else:
            deferred += 1
    print(json.dumps({"status": "poll_done", "discovered": len(intakes),
                      "completed": completed, "deferred": deferred,
                      "blocked": blocked, "crashed": crashes, "rejected": rejected}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="pull a finished intake + drive it through the durable submission states")
    i.add_argument("--worker-url", required=True)
    i.add_argument("--session-id", required=True, help="the intake_session_id from the app")
    i.add_argument("--run-dir", required=True, help="deck run directory to stamp")
    i.add_argument("--company-id", default="", help="PRES-009: tenant company id for worker scoping "
                   "(overrides INTAKE_COMPANY_ID env; both ids required for scoped reads)")
    i.add_argument("--installation-id", default="", help="PRES-009: fleet installation id for worker scoping "
                   "(overrides INTAKE_INSTALLATION_ID env; both ids required for scoped reads)")
    i.add_argument("--no-per-session-dirs", action="store_true",
                   help="LEGACY opt-out: stamp this one intake directly under --run-dir "
                        "(only for a root that never holds a second submission)")
    i.add_argument("--verbose", action="store_true")
    i.set_defaults(func=cmd_ingest, per_session_dirs=True)
    p = sub.add_parser("poll", help="list finished intakes and drive each through the durable states")
    p.add_argument("--worker-url", required=True)
    p.add_argument("--run-dir", required=True, help="deck run directory to stamp each intake under")
    p.add_argument("--poll-ledger", default="", help="path to the poll ledger (processed session ids)")
    p.add_argument("--company-id", default="", help="PRES-009: tenant company id for worker scoping "
                   "(overrides INTAKE_COMPANY_ID env; both ids required for scoped reads)")
    p.add_argument("--installation-id", default="", help="PRES-009: fleet installation id for worker scoping "
                   "(overrides INTAKE_INSTALLATION_ID env; both ids required for scoped reads)")
    p.add_argument("--per-session-dirs", dest="per_session_dirs", action="store_true", default=True,
                   help="stamp each intake under <run-dir>/<session-id>/ (PRES-009 DEFAULT: ON — "
                        "submissions must never share one target directory)")
    p.add_argument("--no-per-session-dirs", dest="per_session_dirs", action="store_false",
                   help="opt out for a single-session deployment; refused when the poll ledger "
                        "already holds a different session")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_poll, per_session_dirs=True)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
