"""F1 -- BOUNDED AUTO-RESUME OF PARKED RUNS.

THE DEFECT THIS CLOSES (measured, and it is the department's dominant
wall-clock cost). Nothing in this system resumes a BLOCKED run. Not the
poller (`presentation-intake-poll.sh`: "Already finished or parked -- skip"),
not `supervisor.supervise()` (skips DONE|BLOCKED|ABANDONED), not
`cc_board._dispatch_engine_if_idle`, not the watchdog (report-only). A search
of every .py/.sh under scripts/ for a line mentioning BLOCKED *and* one of
resume/restart/dispatch/relaunch returned ZERO hits; the control -- "BLOCKED"
alone -- appears in five files. So the code that parks a run is real and the
code that un-parks it is a human being typing --resume.

WHAT THAT COST, on one measured run (`pres-mta0y199-qj40j3`, from_scratch,
manifest v51): 22 h 14 min of wall clock to reach 37 of 38 phases, **21
entries in resume_history, every one a human**, then ten days sitting parked.
NINE of those 21 resumes succeeded on the very next try -- "script executor
failed after 3 attempts", resumed minutes later by a person, passed. Those
nine were transient failures that nothing in the system retried.

WHAT THIS MODULE IS. One decision function, `decide(run_dir)`, that answers a
single question -- may this parked run be resumed automatically, right now? --
and a CLI the poller consults in place of its old
`TERMINAL = BLOCKED -> continue` branch. It starts nothing itself: a "yes"
means the poller's EXISTING launcher line runs, with the same
`${RUN_MODE:+--mode "$RUN_MODE"}` it always used. There is exactly one
dispatcher of engines in the poller and this does not become a second one.

BOUNDED IS THE WHOLE POINT. An unbounded auto-resume is a machine for
re-running a broken build forever at 12 attempts an hour, and it would have
done exactly that to the two runs that re-spawned every five minutes for days
this summer. Four independent bounds, each of which alone stops a runaway:

  1. CLASS      -- an owner decision is never auto-resumed. `heal.classify_
                   failure` is the SAME classifier the heal ladder dispatches
                   on, so "what may be retried" has one definition in this
                   codebase, not two. FAILURE_OWNER_DECISION parks for a
                   human, exactly as `_block`'s contract says it must.
  2. PHASE      -- the four close-time sentinels (CLOSE, CERT-INTEGRITY,
                   CURATION, SELF-AUDIT -- `phases.Engine.close`'s own literal
                   strings, not manifest phase ids) are refused UNLESS the
                   reason class is transient or provider_error. A gate that
                   did not pass does not pass because it was asked twice.
  3. CAP        -- AUTO_RESUME_CAP attempts per rolling
                   AUTO_RESUME_WINDOW_HOURS. Attempt 4 in a day does not
                   happen; it parks for a human and says so ONCE.
  4. BACKOFF    -- AUTO_RESUME_BACKOFF_MINUTES gates the interval since the
                   previous auto-resume. The first retry is IMMEDIATE (the
                   measured evidence says nine of these pass on the next try
                   and making them wait is pure added latency); the second
                   and third wait, so a genuinely broken run spends its cap
                   over ~40 minutes instead of over 15.

Together: at most three engine starts per run per day from this module, the
last of them at least half an hour after the first, and none at all for a
class of failure a resume cannot fix.

AND THE COUNTERPART OF A BOUND IS AN HONEST COUNTER. The cap counts ENGINE
STARTS, so an attempt that started no engine is REFUNDED (`--refund`, called
by the poller when the launcher refuses or when F3's running-engine proof
comes back negative). Otherwise one curable environment fault -- an unset
PRESENTATION_NOTIFY_CMD, a capacity autofail, a stale manifest pin -- eats
the whole budget in forty minutes and leaves a healthy deck parked with no
retries for a reason that had nothing to do with the deck. A refund can only
ever remove a charge, never add one, and refunded rows stay on the ledger
with the reason attached.

HARD DEPENDENCY ON F2 (auto-repin), STATED PLAINLY. A run whose pinned
manifest sha no longer matches the manifest on disk dies EXIT_MANIFEST_MISMATCH
(7) about one second into `__main__.main`, before any work happens. An
auto-resume without an auto-repin therefore burns its entire cap on three
one-second deaths after any manifest bump -- worse than no auto-resume at all,
because it also consumes the budget that would have been available once the
pin was fixed. So this module refuses to spend an attempt it can prove will
die that way: see `_manifest_status` and `_auto_repin_available`. When F2's
`launcher.auto_repin_gate` IS present the mismatch is not an obstacle (the
launcher re-pins before it spawns) and the resume proceeds; when it is NOT
present, or when its presence cannot be PROVEN, the decision is
DECISION_MANIFEST_PIN -- skip, spend nothing, name the exact command that
cures it. And attempts already spent under a pin that is still stale are
REFUNDED rather than counted, because they never bought a running engine.

WHAT IT DOES NOT DO. It does not heal, re-author, re-route, waive, or edit a
phase record. It does not clear `terminal` -- `__main__._reset_parked_state`
owns that and still does it, on the resume this module merely authorises. It
never writes outside `<run_dir>/state.json` (through the launcher's locked
merge, so an engine save can neither clobber it nor be clobbered by it).

ROLLBACK: `PRESENTATION_AUTO_RESUME=0` makes every decision a skip. The
poller then behaves exactly as it did before F1 -- a BLOCKED run is passed
over and counted as terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # package context (python3 -m presentation_job.auto_resume)
    from .heal import (classify_failure, FAILURE_OWNER_DECISION,
                       FAILURE_PROVIDER_ERROR, FAILURE_TRANSIENT)
    from .state import sha256_file, utcnow
except ImportError:  # pragma: no cover -- direct-path import, tests and shims
    from heal import (classify_failure, FAILURE_OWNER_DECISION,  # type: ignore[no-redef]
                      FAILURE_PROVIDER_ERROR, FAILURE_TRANSIENT)
    from state import sha256_file, utcnow  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# THE BOUNDS. Every one of these is a number a runaway cannot exceed.
# ---------------------------------------------------------------------------

#: Automatic resumes allowed per run per rolling window. Three, because of
#: what the one measured run actually shows: of its 21 human resumes, NINE
#: succeeded on the very next try. That is evidence about the FIRST retry and
#: nothing else -- no run has ever been observed needing a fourth -- so two
#: spare attempts is generosity, not a strategy. UNDETERMINED, and stated as
#: such: nobody has measured what a second or third automatic attempt buys.
AUTO_RESUME_CAP = 3

#: The window the cap is counted over. Rolling, not calendar: a run that
#: exhausted its cap at 03:00 is eligible again at 03:00 the next day, by
#: which time a human has either fixed it or it is still broken and will
#: exhaust the cap again with three more lines in the log saying so.
AUTO_RESUME_WINDOW_HOURS = 24

#: Minimum minutes since the PREVIOUS automatic resume, indexed by the attempt
#: about to be made (attempt 1 -> index 0). The first retry is immediate on
#: purpose: the measured tail failures ("script executor failed after 3
#: attempts", "regeneration produced nothing") passed on the very next human
#: resume minutes later, and a mandatory wait there is latency bought with
#: nothing. The 2nd and 3rd wait, so three attempts span ~40 minutes rather
#: than the 15 the poller's 5-minute tick would otherwise allow.
AUTO_RESUME_BACKOFF_MINUTES: Tuple[int, ...] = (0, 10, 30)

#: `phases.Engine.close()` writes these four literal strings into
#: state["blocked"]["phase"] -- they are SENTINELS, not manifest phase ids (no
#: phase in PIPELINE-MANIFEST.json v67 is called any of them). A park here
#: means a fail-closed gate, the process-certificate integrity check, curation
#: or the self-audit said no. Re-running the same close against the same
#: artifacts asks the same question and gets the same answer, so these are
#: refused -- UNLESS the recorded reason classifies transient/provider, which
#: is the case where the gate never got to make a judgement at all.
CLOSE_TIME_PHASES: Tuple[str, ...] = ("CLOSE", "CERT-INTEGRITY",
                                      "CURATION", "SELF-AUDIT")

#: The two classes a re-run can plausibly cure without changing anything:
#: something outside this system failed (provider) or nothing was recorded
#: (transient). These are the only classes allowed through the close-time
#: carve-out above.
RETRYABLE_AT_CLOSE: Tuple[str, ...] = (FAILURE_TRANSIENT, FAILURE_PROVIDER_ERROR)

#: state.json key holding the attempt ledger this module owns. Nothing else
#: reads or clears it -- in particular `__main__._reset_parked_state` pops
#: state["blocked"] and clears terminal on every resume, so an attempt ledger
#: kept anywhere near those would be erased by the very resume it is counting.
STATE_KEY = "auto_resume"

#: state.json key holding the "cap exhausted" alert stamp, so the operator is
#: told ONCE per exhaustion rather than every five minutes forever.
ALERT_KEY = "auto_resume_alert"

#: Documented rollback (same shape as PRESENTATION_AUTO_REPIN /
#: PRESENTATION_LAUNCH_VERIFY): "0" makes every decision a skip.
AUTO_RESUME_ENV = "PRESENTATION_AUTO_RESUME"

#: The subsystem label this module raises operator alerts under. `report.
#: dispatch3` resolves a KNOWN_SUBSYSTEM_IDS label to OWNER_CHAT_ID; this name
#: is registered there for exactly that reason (an unregistered label reaches
#: the transport unresolved and the alert lands nowhere).
ALERT_CHAT_LABEL = "auto-resume"

#: PRES-019 (step 4): vocabulary that names a MISSING CONFIGURATION rather
#: than a failure a retry could cure. Two shapes, both observable in the
#: parks this engine actually writes:
#:   * a provider key gate -- model_router FIX 114 parks with the exact
#:     phrase "has no resolvable key"; a credential the run cannot resolve
#:     is an OWNER-of-the-box action (add the key to the env store), never
#:     an auto-resume;
#:   * a resource-plan gate -- a provider whose one-time resource-plan
#:     answer is still pending parks asking for it (resource_profile's
#:     ask-once contract); the answer belongs to the client, not to a poller
#:     tick.
#: Matched case-insensitively against the blocked reason. Anything that
#: matches is a CONFIGURATION-PENDING decision: never auto-resumed (the run
#: would re-park at the same gate and a bound would be wasted), never
#: silent (the stamp below names who owns the answer and what the next
#: action is, and survives across detached execution where a notify may
#: have no transport).
CONFIGURATION_PENDING_MARKERS: Tuple[str, ...] = (
    "has no resolvable key",
    "no store carries a plausible credential",
    "resource plan pending",
    "resource-plan pending",
    "resource_plan answer",
    "plan is undeclared",
    "plan undeclared",
    "its plan is unknown",
)


# --- decision codes --------------------------------------------------------
# Distinct names so a log line, a test and an operator all say the same thing
# about WHY, and the CLI exit code separates "decided not to" from "could not
# tell". The poller treats every non-zero exit identically (skip + count as
# terminal); the codes exist so the reason survives into the log.

DECISION_RESUME = "RESUME"
DECISION_NOT_BLOCKED = "NOT-BLOCKED"
DECISION_OWNER = "OWNER-DECISION"
DECISION_CLOSE_GATE = "CLOSE-TIME-GATE"
DECISION_CAP = "CAP-EXHAUSTED"
DECISION_BACKOFF = "BACKOFF"
DECISION_DISABLED = "DISABLED"
DECISION_MANIFEST_PIN = "MANIFEST-PIN"
DECISION_UNREADABLE = "UNDETERMINED"
# PRES-019 (step 4): a park that is really a missing CONFIGURATION -- an
# unanswerable provider credential or an un-answered one-time resource-plan
# question. Retrying the engine without the missing answer is not a bound
# being spent, it is a bound being WASTED: the run will re-park at the same
# gate. So configuration parks are a distinct class: never auto-resumed,
# never silent -- every decision says WHO owns the answer and WHAT the next
# action is, and the visibility stamp below keeps that in state.json across
# detached execution (where a notify may not even have a transport).
DECISION_CONFIGURATION_PENDING = "CONFIGURATION-PENDING"

EXIT_RESUME = 0
EXIT_USAGE = 2
#: A decision was MADE and it was "do not resume".
EXIT_SKIP = 3
#: No decision could be made -- the state could not be read, or the resume is
#: provably going to die on a stale manifest pin that this tree cannot cure.
#: Distinct from EXIT_SKIP because "I decided no" and "I could not tell" are
#: different facts and a bare zero for both is how a negative gets believed.
EXIT_UNDETERMINED = 4


class Decision:
    """One auto-resume verdict, with its reason and everything the caller
    needs to record it. `resume` is the answer; `why` is a full sentence
    naming what was checked -- a bare verdict in a log is not evidence."""

    __slots__ = ("resume", "why", "code", "exit_code", "failure_class",
                 "phase", "attempt", "counted", "cap")

    def __init__(self, resume: bool, why: str, code: str, exit_code: int,
                 failure_class: Optional[str] = None,
                 phase: Optional[str] = None,
                 attempt: Optional[int] = None,
                 counted: Optional[int] = None,
                 cap: int = AUTO_RESUME_CAP) -> None:
        self.resume = resume
        self.why = why
        self.code = code
        self.exit_code = exit_code
        self.failure_class = failure_class
        self.phase = phase
        self.attempt = attempt
        self.counted = counted
        self.cap = cap

    def __repr__(self) -> str:  # pragma: no cover -- diagnostics only
        return (f"Decision(resume={self.resume!r}, code={self.code!r}, "
                f"why={self.why!r})")


# ---------------------------------------------------------------------------
# Reads. None of these raise, and none of them guess: every failure comes back
# as a stated UNDETERMINED with the reason named.
# ---------------------------------------------------------------------------

def _read_state(run_path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    state_path = run_path / "state.json"
    if not state_path.is_file():
        return None, f"no state.json at {state_path}"
    try:
        doc = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return None, f"{state_path} is unreadable ({exc})"
    if not isinstance(doc, dict):
        return None, f"{state_path} is not a JSON object"
    return doc, "read"


def _parse_at(value: Any) -> Optional[datetime]:
    """Parse one of this codebase's `utcnow()` stamps (local-tz-aware ISO,
    seconds precision) into an aware UTC datetime. Anything unparseable is
    None -- the caller then treats the row as OUTSIDE the window rather than
    inventing a time, which can only ever make the cap more permissive by one
    row, never less, and never crashes on a hand-edited state file."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):  # tolerate a UTC-suffixed stamp from any writer
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = state.get(STATE_KEY)
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def _counted_rows(state: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """The attempt rows that COUNT against the cap: inside the rolling window
    and not refunded. A refunded row is one this module later proved bought no
    running engine (see `_refund_manifest_pin_attempts`)."""
    floor = now - timedelta(hours=AUTO_RESUME_WINDOW_HOURS)
    out = []
    for row in _rows(state):
        if row.get("refunded"):
            continue
        at = _parse_at(row.get("at"))
        if at is None or at < floor:
            continue
        out.append(row)
    return out


def _scripts_dir() -> Path:
    """.../presentations/scripts -- the package's parent, the same anchor
    launcher.py and __main__.py use."""
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# THE F2 DEPENDENCY, made explicit and self-checking.
# ---------------------------------------------------------------------------

def _pinned_manifest(state: Dict[str, Any],
                     run_path: Path) -> Tuple[Optional[str], Optional[Path], str]:
    """(pinned_sha, manifest_on_disk, why) -- or a stated UNDETERMINED.

    Deliberately a plain read: `manifest.Manifest()` and `resolve_manifest()`
    both `die()` (SystemExit) on a stale MANIFEST-SOURCE stamp or an
    unparseable file, and a *decision* helper that can kill its own process is
    not a helper. `sha256_file` is the same hash `Manifest.__init__` takes, so
    the comparison here is the comparison `__main__.main` will make.
    """
    pinned = state.get("manifest_sha256")
    if not isinstance(pinned, str) or not pinned:
        return None, None, "state.json carries no manifest_sha256 pin"
    declared = state.get("manifest_path")
    if isinstance(declared, str) and declared:
        cand = Path(declared).expanduser()
        if cand.is_file():
            return pinned, cand, f"pinned manifest_path {cand}"
        return None, None, (f"the pinned manifest_path {cand} is gone -- "
                            "--repin needs an explicit --manifest here")
    # No declared path: reproduce manifest.resolve_manifest's OWN order --
    # candidate 2 (<scripts_dir>/../sops/PIPELINE-MANIFEST.json, the
    # materialized department) then candidate 3 ($PRESENTATION_MANIFEST) --
    # so this comparison is made against the file __main__ will actually load.
    # Candidate 1 (--manifest) cannot apply: the poller passes no --manifest.
    # `_assert_manifest_current` is deliberately NOT called: it die()s, and a
    # stale-stamp error is a fact for the engine to report, never something a
    # read-only decision helper may exit the process over.
    candidates = [_scripts_dir().parent / "sops" / "PIPELINE-MANIFEST.json"]
    env_manifest = os.environ.get("PRESENTATION_MANIFEST")
    if env_manifest:
        candidates.append(Path(env_manifest).expanduser())
    for cand in candidates:
        if cand.is_file():
            return pinned, cand, (f"resolved {cand} the way "
                                  "manifest.resolve_manifest would (state "
                                  "declared no manifest_path)")
    return None, None, ("state.json declares no manifest_path, and neither "
                        f"{candidates[0]} nor $PRESENTATION_MANIFEST names a "
                        "readable manifest -- the pin cannot be compared")


def _auto_repin_available(scripts_dir: Optional[Path] = None) -> Tuple[Optional[bool], str]:
    """Is F2's auto-repin in THIS tree? (True / False / None = cannot tell).

    Read as TEXT, never imported: importing launcher.py to answer a yes/no
    question drags in capacity, the model router and a page of module-level
    setup, and an ImportError from any of that would be indistinguishable from
    "F2 is absent". A full-string search for the symbol's own `def` line is
    exact and side-effect free.

    THE CONTROL, and it is the point of this function: the same read also
    looks for `def dispatch(`, a symbol launcher.py has always had. If the
    control string is missing too, the file is not the launcher this check
    thinks it is (moved, truncated, unreadable) and the answer is None --
    UNDETERMINED -- never False. A negative that cannot pass its own control
    is a broken instrument, not a fact about the tree.
    """
    launcher = (scripts_dir or _scripts_dir()) / "presentation_job" / "launcher.py"
    try:
        src = launcher.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"cannot read {launcher} ({exc}) -- F2 presence UNDETERMINED"
    control = "def dispatch(" in src
    if not control:
        return None, (f"{launcher} does not contain the control symbol "
                      "`def dispatch(` -- this is not a readable launcher, so "
                      "F2 presence is UNDETERMINED, not absent")
    if "def auto_repin_gate(" in src:
        if os.environ.get("PRESENTATION_AUTO_REPIN", "").strip() == "0":
            return False, (f"{launcher} has F2's auto_repin_gate but "
                           "PRESENTATION_AUTO_REPIN=0 disables it")
        return True, f"{launcher} defines auto_repin_gate (F2 present)"
    return False, (f"{launcher} defines `def dispatch(` (control OK) but not "
                   "`def auto_repin_gate(` -- F2 auto-repin is NOT in this tree")


def _manifest_status(state: Dict[str, Any],
                     run_path: Path) -> Tuple[str, str]:
    """("ok" | "mismatch" | "undetermined", why).

    "mismatch" is the exact condition `__main__.main` dies on with
    EXIT_MANIFEST_MISMATCH (7) roughly one second after the launcher's Popen
    returns 0 -- long before any phase runs, and long before anything this
    module wanted could happen.
    """
    pinned, manifest_path, why = _pinned_manifest(state, run_path)
    if pinned is None or manifest_path is None:
        return "undetermined", why
    try:
        on_disk = sha256_file(manifest_path)
    except OSError as exc:
        return "undetermined", f"cannot hash {manifest_path} ({exc})"
    if on_disk == pinned:
        return "ok", (f"pinned manifest {pinned[:12]} matches {manifest_path} "
                      f"({why})")
    return "mismatch", (f"pinned {pinned[:12]} != on disk {on_disk[:12]} "
                        f"({manifest_path})")


def _refund_manifest_pin_attempts(state: Dict[str, Any], now: datetime) -> int:
    """Mark attempts that were spent under the pin that is STILL stale.

    An attempt row records the manifest sha the run was pinned to at the time.
    If the run is still pinned to that same sha while the manifest on disk has
    moved, that attempt bought a one-second EXIT_MANIFEST_MISMATCH death and
    nothing else. Refunding it is not generosity, it is accuracy: the cap
    counts ENGINE STARTS, and that attempt started no engine.

    Mutates `state` in place and returns how many rows it refunded. Bounded in
    the only direction that matters: it can only ever REMOVE attempts from the
    tally, and only for rows whose recorded pin is provably the stale one, so
    it can never manufacture an extra attempt.
    """
    pinned = state.get("manifest_sha256")
    if not isinstance(pinned, str) or not pinned:
        return 0
    refunded = 0
    for row in _counted_rows(state, now):
        if row.get("manifest_sha256") == pinned:
            row["refunded"] = "manifest-pin"
            row["refunded_at"] = utcnow()
            refunded += 1
    return refunded


# ---------------------------------------------------------------------------
# THE DECISION
# ---------------------------------------------------------------------------

def _configuration_pending_decision(run_path: Path, phase: Optional[str],
                                    reason: str, fclass: str) -> Decision:
    """PRES-019 (step 4): the CONFIGURATION-PENDING verdict.

    Two jobs, one stamp:

      1. NEVER RESUME. The Decision itself does that (resume=False) -- no
         attempt is spent, no backoff is started, the cap is untouched.

      2. STAMP THE VISIBILITY. `evaluate` is a pure read, so the stamp is
         written here (the write side of the decision), directly into
         state.json through the launcher's locked merge: owner, next action,
         the matched configuration reason and a reminder time. The stamp is
         what keeps a missing provider answer VISIBLE across detached
         execution -- a poller tick on an unattended box may have no notify
         transport at all, but state.json is read by every later pass
         (report, board, watchdog), so the pending configuration is reported
         as pending by anything that looks, never as "working".

    The stamp is idempotent per (phase, reason): rewritten on every
    evaluation, so a cured-and-reparked configuration refreshes it, and a
    merged write that loses a race simply loses to the newer truth.
    Fail-soft: an unwritable state.json degrades this to the plain decision
    -- the verdict still holds, only the stamp is lost.
    """
    marker_hit = next(
        (m for m in CONFIGURATION_PENDING_MARKERS if m in reason.lower()), None)
    if marker_hit and ("resolvable key" in marker_hit
                       or "plausible credential" in marker_hit):
        owner = "the box owner (a provider credential must be added to the "
        owner += "env store)"
        next_action = ("add a plausible credential for the named provider to "
                       "the box env store, then resume with `presentation_job.py "
                       "--resume --run-dir <run-dir>`")
    elif marker_hit:
        owner = "the client (a one-time resource-plan answer)"
        next_action = ("answer the pending resource-plan question for the "
                       "named provider; the run unblocks exactly once the "
                       "answer is recorded")
    else:  # pragma: no cover -- defensive; callers match first
        owner = "the box owner"
        next_action = ("resolve the missing configuration named in the blocked "
                       "reason, then resume")
    why = (f"the park at {phase or 'an unrecorded phase'} is a missing "
           f"CONFIGURATION ({reason[:180]!r}) -- retrying the engine without "
           "the missing answer re-parks at the same gate, so no attempt is "
           f"spent and none will be. Owner: {owner}. Next action: "
           f"{next_action}. The configuration_pending stamp in state.json "
           "keeps this visible to every later pass.")

    def _stamp(state: Dict[str, Any]) -> None:
        state["configuration_pending"] = {
            "at": utcnow(),
            "phase": phase,
            "reason": reason[:400],
            "matched_marker": marker_hit,
            "failure_class": fclass,
            "owner": owner,
            "next_action": next_action,
            "reminder": ("shown as PENDING, never as working, by every "
                         "status pass until the answer is recorded"),
            "by": "presentation_job.auto_resume",
        }

    _merge(run_path, _stamp)
    return Decision(False, why,
                    DECISION_CONFIGURATION_PENDING, EXIT_SKIP,
                    failure_class=fclass, phase=phase)


def evaluate(run_dir, now: Optional[datetime] = None) -> Decision:
    """The full verdict for one run dir. PURE: reads only, writes nothing.

    Ordered so the strongest refusal is checked first and so no bound can be
    reached past a bound that already said no.
    """
    now = now or datetime.now(timezone.utc)
    run_path = Path(run_dir).expanduser()

    if os.environ.get(AUTO_RESUME_ENV, "").strip() == "0":
        return Decision(False, f"auto-resume is DISABLED ({AUTO_RESUME_ENV}=0) "
                               "-- this run is left parked for a human, which "
                               "is the pre-F1 behaviour",
                        DECISION_DISABLED, EXIT_SKIP)

    state, why = _read_state(run_path)
    if state is None:
        return Decision(False, f"cannot decide: {why}. Nothing was resumed and "
                               "no attempt was spent.",
                        DECISION_UNREADABLE, EXIT_UNDETERMINED)

    terminal = str(state.get("terminal") or "")
    if terminal != "BLOCKED":
        return Decision(False, f"terminal is {terminal or 'unset'!r}, not "
                               "'BLOCKED' -- auto-resume only ever un-parks a "
                               "BLOCKED run",
                        DECISION_NOT_BLOCKED, EXIT_SKIP)

    blocked = state.get("blocked")
    blocked = blocked if isinstance(blocked, dict) else {}
    phase = str(blocked.get("phase") or "") or None
    reason = blocked.get("reason")
    fclass = classify_failure(reason)

    # --- PRES-019 BOUND 0: missing CONFIGURATION is not a retryable failure.
    # Checked BEFORE the class bound: a park like "provider X has no
    # resolvable key" classifies provider_error (the gate that names it talks
    # about providers), and provider_error is the class the backoff bound is
    # otherwise happy to spend attempts on. Retrying into a gate that can
    # only be answered by a human (a credential in the box's env store) or by
    # the client (the one-time resource-plan answer) burns the cap and parks
    # the run in exactly the same place. So a configuration park gets its own
    # verdict: never resumed, and -- unlike a plain skip -- stamped with WHO
    # owns the answer and WHAT the next action is, kept in state.json so the
    # visibility survives detached execution.
    reason_text = str(reason or "")
    reason_lower = reason_text.lower()
    if any(m in reason_lower for m in CONFIGURATION_PENDING_MARKERS):
        return _configuration_pending_decision(run_path, phase, reason_text,
                                               fclass)

    # --- BOUND 1: class. The heal ladder's own classifier, not a second one.
    if fclass == FAILURE_OWNER_DECISION:
        return Decision(False,
                        f"the park at {phase or 'an unrecorded phase'} "
                        f"classifies as {FAILURE_OWNER_DECISION} "
                        f"({str(reason)[:180]!r}) -- an owner decision is "
                        "never auto-healed and never auto-resumed; a person "
                        "has to decide",
                        DECISION_OWNER, EXIT_SKIP, failure_class=fclass,
                        phase=phase)

    # --- BOUND 2: close-time gates, unless nothing actually got judged.
    if phase in CLOSE_TIME_PHASES and fclass not in RETRYABLE_AT_CLOSE:
        return Decision(False,
                        f"the park is at the close-time sentinel {phase} with "
                        f"class {fclass} -- a gate, the certificate integrity "
                        "check, curation or the self-audit judged the "
                        "artifacts and said no. Asking it again with the same "
                        "artifacts gets the same answer, so no attempt is "
                        f"spent. (Only {'/'.join(RETRYABLE_AT_CLOSE)} pass "
                        "here, because those mean nothing was judged at all.)",
                        DECISION_CLOSE_GATE, EXIT_SKIP, failure_class=fclass,
                        phase=phase)

    # --- THE F2 DEPENDENCY: never spend an attempt on a death we can predict.
    status, mwhy = _manifest_status(state, run_path)
    if status == "mismatch":
        repin, rwhy = _auto_repin_available()
        if repin is not True:
            entry = _scripts_dir() / "presentation_job.py"
            return Decision(
                False,
                "the manifest moved under this run and this resume would die "
                f"EXIT_MANIFEST_MISMATCH in about one second: {mwhy}. "
                f"{rwhy}. Spending one of {AUTO_RESUME_CAP} attempts on a "
                "death that is certain would leave a fixable run with no "
                "budget once the pin is cured, so NO attempt was spent. "
                f"Cure it with: {entry} --repin --run-dir {run_path}",
                DECISION_MANIFEST_PIN, EXIT_UNDETERMINED,
                failure_class=fclass, phase=phase)
        # F2 is present: the launcher re-pins before it spawns, so the
        # mismatch is not an obstacle -- say so rather than staying silent.
        print(f"auto-resume: {mwhy}; {rwhy} -- the resume will re-pin itself "
              "before the engine starts", flush=True)

    # --- BOUND 3: the cap, counted over a rolling window, refunds honoured.
    counted = _counted_rows(state, now)
    if len(counted) >= AUTO_RESUME_CAP:
        newest = max((_parse_at(r.get("at")) for r in counted
                      if _parse_at(r.get("at"))), default=None)
        return Decision(False,
                        f"{len(counted)} automatic resume(s) have already been "
                        f"spent on this run in the last "
                        f"{AUTO_RESUME_WINDOW_HOURS}h (cap {AUTO_RESUME_CAP}; "
                        f"most recent {newest.isoformat() if newest else 'unknown'}). "
                        "This run is now parked for a HUMAN -- three automatic "
                        "attempts did not clear it, so it is not the kind of "
                        "failure another attempt fixes.",
                        DECISION_CAP, EXIT_SKIP, failure_class=fclass,
                        phase=phase, counted=len(counted))

    # --- BOUND 4: backoff since the previous automatic resume.
    attempt = len(counted) + 1
    idx = min(attempt - 1, len(AUTO_RESUME_BACKOFF_MINUTES) - 1)
    wait_minutes = AUTO_RESUME_BACKOFF_MINUTES[idx]
    if wait_minutes and counted:
        last = max((_parse_at(r.get("at")) for r in counted
                    if _parse_at(r.get("at"))), default=None)
        if last is not None:
            elapsed = (now - last).total_seconds() / 60.0
            if elapsed < wait_minutes:
                return Decision(
                    False,
                    f"attempt {attempt} of {AUTO_RESUME_CAP} must wait "
                    f"{wait_minutes} minute(s) after the previous automatic "
                    f"resume ({last.isoformat()}); only {elapsed:.1f} have "
                    "passed. Backoff is what stops a broken run from spending "
                    "its whole cap inside three poller ticks.",
                    DECISION_BACKOFF, EXIT_SKIP, failure_class=fclass,
                    phase=phase, counted=len(counted), attempt=attempt)

    return Decision(
        True,
        f"attempt {attempt} of {AUTO_RESUME_CAP}: parked at "
        f"{phase or 'an unrecorded phase'} with class {fclass} "
        f"({str(reason)[:180]!r}) -- retryable, not an owner decision, "
        f"{len(counted)} attempt(s) spent in the last "
        f"{AUTO_RESUME_WINDOW_HOURS}h, manifest pin {status}.",
        DECISION_RESUME, EXIT_RESUME, failure_class=fclass, phase=phase,
        attempt=attempt, counted=len(counted))


def decide(run_dir) -> Tuple[bool, str]:
    """The spec's shape: (resume, why). A thin read over `evaluate`, kept
    because it is the contract other code should depend on -- callers that
    only need the answer must not have to know about exit codes."""
    d = evaluate(run_dir)
    return d.resume, d.why


# ---------------------------------------------------------------------------
# Writes -- all of them through the launcher's locked state merge.
# ---------------------------------------------------------------------------

def _merge(run_path: Path, mutate) -> bool:
    """`launcher._merge_run_state_field` is the ONE writer of a non-engine
    field into a live state.json: it takes the run's .job.lock, re-reads,
    mutates, and saves through StateStore's atomic temp+fsync+replace. Writing
    state.json any other way from outside the engine is the FIX 27 lost-update
    shape. Imported lazily so a decision (a pure read) never pays for the
    launcher's import graph."""
    try:
        try:
            from .launcher import _merge_run_state_field
        except ImportError:
            from launcher import _merge_run_state_field  # type: ignore[no-redef]
    except ImportError as exc:  # pragma: no cover -- broken tree
        print(f"auto-resume: cannot record in state.json ({exc})",
              file=sys.stderr)
        return False
    return bool(_merge_run_state_field(run_path, mutate))


def record_attempt(run_dir, decision: Decision) -> bool:
    """Append one attempt row to state[STATE_KEY], and say whether it landed.

    RECORDED BEFORE THE DISPATCH, deliberately: `__main__._reset_parked_state`
    pops state["blocked"] and clears terminal the moment the engine starts, so
    a row written afterwards could not name the park it was answering.

    THE RETURN VALUE IS LOAD-BEARING. A cap counted from a ledger that could
    not be written is not a cap: if the merge never landed, every tick would
    read zero attempts and resume again, forever, which is the exact runaway
    this module exists to prevent. So `main()` treats a failed record as a
    REFUSAL -- nothing is dispatched -- rather than resuming on an uncounted
    attempt. Losing five minutes to a busy state.json is a cost; an unbounded
    auto-resume is a defect."""
    run_path = Path(run_dir).expanduser()
    row = {
        "at": utcnow(),
        "phase": decision.phase,
        "class": decision.failure_class,
        "attempt": decision.attempt,
        "cap": AUTO_RESUME_CAP,
        "window_hours": AUTO_RESUME_WINDOW_HOURS,
        "by": "presentation_job.auto_resume",
        "why": decision.why,
    }

    def _mutate(state: Dict[str, Any]) -> None:
        # Carry the pin this attempt is made under, so a later tick can prove
        # the attempt died on a stale manifest and refund it.
        pin = state.get("manifest_sha256")
        if isinstance(pin, str) and pin:
            row["manifest_sha256"] = pin
        rows = state.setdefault(STATE_KEY, [])
        if isinstance(rows, list):
            rows.append(row)
        # A fresh attempt reopens the alert: the NEXT exhaustion is news again.
        state.pop(ALERT_KEY, None)

    ok = _merge(run_path, _mutate)
    if not ok:
        print(f"auto-resume: could not record attempt {decision.attempt} in "
              f"{run_path}/state.json (the run lock stayed busy, or the file "
              "is missing/unreadable). REFUSING the resume rather than "
              "spending an attempt the cap cannot see -- an uncounted attempt "
              "repeats every poller tick forever. Retrying next tick.",
              file=sys.stderr)
    return ok


def refund_last_attempt(run_dir, reason: str) -> bool:
    """Give the most recent attempt back, because it bought no engine.

    THE RULE THIS ENFORCES: the cap counts ENGINE STARTS. An attempt the
    launcher refused (AF-NOTIFY-UNCONFIGURED, a capacity autofail, the credit
    preflight, a failed repin) or one whose engine died on arrival (F3's
    running-engine proof came back negative) started nothing, and charging the
    run for it lets one curable environment fault eat the entire budget in
    forty minutes -- leaving a healthy deck parked with no retries left for a
    reason that had nothing to do with the deck.

    BOUNDED IN THE ONLY DIRECTION THAT MATTERS. It marks at most ONE row, the
    newest un-refunded one, and only a row this module wrote. It can never add
    an attempt, never un-refund one, and never touch a row from an earlier
    tick that did start an engine. Refunded rows stay in state.json with the
    reason attached: the ledger keeps the whole history, the CAP just stops
    counting a charge that bought nothing.
    """
    run_path = Path(run_dir).expanduser()
    marked = {"done": False}

    def _mutate(state: Dict[str, Any]) -> None:
        rows_ = state.get(STATE_KEY)
        if not isinstance(rows_, list):
            return
        for row in reversed(rows_):
            if not isinstance(row, dict) or row.get("refunded"):
                continue
            if row.get("by") != "presentation_job.auto_resume":
                continue
            row["refunded"] = "no-engine-started"
            row["refunded_at"] = utcnow()
            row["refunded_why"] = str(reason)[:400]
            marked["done"] = True
            return

    if not _merge(run_path, _mutate):
        print("auto-resume: could not refund the last attempt in "
              f"{run_path}/state.json -- it stays counted against the cap",
              file=sys.stderr)
        return False
    if marked["done"]:
        print(f"auto-resume: refunded the attempt just made on {run_path.name} "
              f"-- no engine started ({str(reason)[:200]}). The cap counts "
              "engine starts, not dispatch attempts.", flush=True)
    else:
        print(f"auto-resume: nothing to refund on {run_path.name} (no "
              "un-refunded attempt of this module's own on the ledger)",
              flush=True)
    return marked["done"]


def _alert_message(run_path: Path, decision: Decision) -> str:
    entry = _scripts_dir() / "presentation_job.py"
    return (
        f"Presentation run {run_path.name} is parked and AUTOMATIC RESUME IS "
        f"EXHAUSTED. {decision.counted} of {AUTO_RESUME_CAP} automatic "
        f"attempts were spent in the last {AUTO_RESUME_WINDOW_HOURS}h and the "
        f"run is still BLOCKED at {decision.phase or 'an unrecorded phase'}. "
        "No further automatic attempt will be made in this window -- it needs "
        f"a person. Look at it with: {entry} --status --run-dir {run_path}"
        f" (and, once you know what to fix: {entry} --resume --run-dir "
        f"{run_path} --diagnose-only)"
    )


def notify_cap_exhausted(run_dir, decision: Decision) -> Optional[bool]:
    """ONE operator notification per exhaustion, never one per poller tick.

    Returns True (sent), False (transport said no) or None (already alerted
    for this exact attempt series -- nothing sent, which is the whole point).
    The stamp is keyed to the newest counted attempt, so a NEW attempt (which
    clears the stamp in `record_attempt`) makes the next exhaustion news
    again, while five minutes later on the same three attempts it is not.
    """
    run_path = Path(run_dir).expanduser()
    state, _why = _read_state(run_path)
    if state is None:
        return None
    counted = _counted_rows(state, datetime.now(timezone.utc))
    key = str(max((str(r.get("at") or "") for r in counted), default=""))
    prior = state.get(ALERT_KEY)
    if isinstance(prior, dict) and prior.get("for_attempt_at") == key:
        return None

    message = _alert_message(run_path, decision)
    sent: Optional[bool]
    try:
        try:
            from .report import dispatch as _dispatch
        except ImportError:
            from report import dispatch as _dispatch  # type: ignore[no-redef]
        sent = bool(_dispatch(ALERT_CHAT_LABEL, "blocked", message))
    except Exception as exc:  # noqa: BLE001 -- an alert never breaks a poll tick
        print(f"auto-resume: could not raise the cap-exhausted alert ({exc}) "
              f"-- the reason is still in this log: {message}", file=sys.stderr)
        sent = False

    stamped = _merge(run_path, lambda state: state.__setitem__(ALERT_KEY, {
        "at": utcnow(), "for_attempt_at": key, "attempts": decision.counted,
        "cap": AUTO_RESUME_CAP, "phase": decision.phase, "delivered": sent,
        "message": message,
    }))
    if not stamped:
        # The stamp is what makes this ONE alert instead of one every five
        # minutes forever. Losing it is not fatal but it is loud, because the
        # visible symptom is an operator's chat repeating the same line all
        # night and the cause is nowhere near the chat.
        print(f"auto-resume: WARNING -- the cap-exhausted alert was raised but "
              f"the once-only stamp could not be written to {run_path}/"
              "state.json. Until it can be, this alert repeats on every poll "
              "tick.", file=sys.stderr)
    if not sent:
        print("auto-resume: the cap-exhausted alert was NOT confirmed "
              "delivered (PRESENTATION_NOTIFY_CMD unset, or the transport "
              f"returned non-zero). Message: {message}", file=sys.stderr)
    return sent


# ---------------------------------------------------------------------------
# CLI -- what presentation-intake-poll.sh calls in place of its old
# `TERMINAL = BLOCKED -> continue`.
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presentation_job.auto_resume",
        description=("Decide whether a BLOCKED presentation run may be "
                     "resumed automatically. Exit 0 = resume (an attempt has "
                     "been recorded), 3 = decided not to, 4 = undetermined. "
                     "This command starts nothing; the caller dispatches."))
    p.add_argument("--run-dir", required=True,
                   help="the run directory to decide about")
    p.add_argument("--check", action="store_true",
                   help=("decide and print, but record NOTHING and notify "
                         "nobody -- for an operator asking 'would this "
                         "resume?' without consuming an attempt"))
    p.add_argument("--refund", metavar="REASON",
                   help=("give back the attempt just made because no engine "
                         "started (the launcher refused, or the running-engine "
                         "proof failed). Makes no decision and never resumes; "
                         "always exits 0 so it can never turn a dispatch "
                         "outcome into a second, unrelated failure."))
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run_path = Path(args.run_dir).expanduser()

    if args.refund:
        # A bookkeeping correction, not a decision. Exit 0 unconditionally:
        # the caller is already inside its dispatch-failure path, and a
        # non-zero here would only add a second failure to that log.
        refund_last_attempt(run_path, args.refund)
        return EXIT_RESUME

    # Refund first, so the cap that is about to be counted is the honest one.
    # Only ever runs when a mismatch is provable RIGHT NOW, and only marks
    # rows whose recorded pin IS the still-stale one.
    if not args.check:
        state, _why = _read_state(run_path)
        if state is not None and str(state.get("terminal") or "") == "BLOCKED":
            status, mwhy = _manifest_status(state, run_path)
            repin, _rwhy = _auto_repin_available()
            if status == "mismatch" and repin is not True:
                now = datetime.now(timezone.utc)
                probe = json.loads(json.dumps(state))  # cheap deep copy
                if _refund_manifest_pin_attempts(probe, now):
                    def _refund(live: Dict[str, Any]) -> None:
                        _refund_manifest_pin_attempts(live, now)
                    if _merge(run_path, _refund):
                        print("auto-resume: refunded the attempt(s) spent "
                              f"under the still-stale pin ({mwhy}) -- they "
                              "started no engine, so they do not count "
                              "against the cap", flush=True)

    decision = evaluate(run_path)
    verdict = "RESUME" if decision.resume else "SKIP"
    print(f"auto-resume [{decision.code}] {verdict} {run_path}: "
          f"{decision.why}", flush=True)

    if not decision.resume:
        if decision.code == DECISION_CAP and not args.check:
            notify_cap_exhausted(run_path, decision)
        return decision.exit_code

    if args.check:
        print("auto-resume: --check, so nothing was recorded and no attempt "
              "was spent", flush=True)
        return EXIT_RESUME

    if not record_attempt(run_path, decision):
        # FAIL-CLOSED. See record_attempt's docstring: a resume the ledger did
        # not record is a resume no bound can ever stop.
        return EXIT_UNDETERMINED
    return EXIT_RESUME


if __name__ == "__main__":  # pragma: no cover -- CLI entry
    sys.exit(main())
