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

FIX-PLAN ITEM 10 -- PARK CLASSES, ONE LEDGER, A CLIENT-SAFE RECORD. Three
additions on top of the bounds above, each detailed at its section below:

  * Every park is classified into a PARK CLASS that names WHO MUST ACT
    next -- transient_infra (nobody: the system retries on the bounded
    cadence above), client_action (the client owes an answer, an asset or
    a decision: never auto-resumed, the client is notified ONCE with
    exactly what is needed), operator_action (a credential, a verdict, an
    ambiguity only the operating team can resolve: never auto-resumed,
    the operator is notified with the specific action). A park whose
    record carries nothing classifiable defaults to operator_action --
    the safest class, because it never auto-resumes and it puts a human
    on the run. See `classify_park` and PARK_POLICY.
  * The park ledger and the Fix 35 crash ledger are ONE event stream now:
    new attempts from both paths are rows on state["auto_resume"] (crash
    rows carry kind="crash") and BOTH caps count the merged stream over
    the same rolling window, so a run can no longer be resumed by one
    counter while the other believes it is capped. Rows a field run
    still holds in the legacy state["auto_resume_crash"] key keep
    counting until they age out or are refunded, so an upgrade hands no
    capped run a fresh budget. This supersedes the Fix 35 two-ledger
    split for the LEDGER only: the two paths still decide different
    shapes (a classified park vs a dead engine), they just spend from
    one budget. The window convention is the same rolling 24h the heal
    budget (FIX-PLAN Item 9) counts its persisted heal_events over.
  * Every refused evaluation stamps state["park_status"]: the park in
    plain words (class label, what is needed from whom, since when), so
    the board and client surfaces that already read state.json can show
    the wait without ever showing the raw engineering reason.
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
    from .heal import (classify_failure, FAILURE_MISSING_INPUT,
                       FAILURE_OWNER_DECISION, FAILURE_PROVIDER_ERROR,
                       FAILURE_TRANSIENT, FAILURE_VERIFIER_SUBSTANCE)
    from .state import sha256_file, utcnow
except ImportError:  # pragma: no cover -- direct-path import, tests and shims
    from heal import (classify_failure, FAILURE_MISSING_INPUT,  # type: ignore[no-redef]
                      FAILURE_OWNER_DECISION, FAILURE_PROVIDER_ERROR,
                      FAILURE_TRANSIENT, FAILURE_VERIFIER_SUBSTANCE)
    from state import sha256_file, utcnow  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# PRES-019 QC4 -- THE KNOWN-PLAN RECOVERY PATH (never re-ask, never loop).
# ---------------------------------------------------------------------------

#: Provider ids a plan-gate park can name. Only these exist on the plan
#: interview at all (capacity.CAP_TABLE_PROVIDERS + capacity.NO_CAP_PROVIDERS);
#: a reason naming anything else has no one-time question behind it, so there
#: is no known-plan state to consult and the plain CONFIGURATION-PENDING
#: verdict is the honest one. Read lazily via _plan_gate_providers() so this
#: module keeps importing without the capacity graph.
_PLAN_GATE_PROVIDERS: Tuple[str, ...] = ()

#: Park-reason shapes that name WHICH provider owes a plan answer. The park
#: reasons this engine actually writes name the provider twice (the refusal
#: sentence and the interview question); one regex over the reason is enough,
#: and a miss degrades to the plain configuration-pending verdict -- it can
#: never invent a known-plan state out of an unnameable reason.
_PLAN_PROVIDER_RE = None  # compiled lazily, see _plan_provider_from_reason


def _plan_gate_providers() -> Tuple[str, ...]:
    """The providers whose plan can be KNOWN: cap-table rows plus BYOK
    entries. Never imports at module level -- capacity pulls a detection
    graph this module must not pay for on a plain read."""
    global _PLAN_GATE_PROVIDERS
    if _PLAN_GATE_PROVIDERS:
        return _PLAN_GATE_PROVIDERS
    try:
        try:
            from .capacity import CAP_TABLE_PROVIDERS, NO_CAP_PROVIDERS
        except ImportError:  # pragma: no cover -- direct-path run
            from capacity import CAP_TABLE_PROVIDERS, NO_CAP_PROVIDERS  # type: ignore[no-redef]
        _PLAN_GATE_PROVIDERS = tuple(sorted(set(CAP_TABLE_PROVIDERS)
                                            | set(NO_CAP_PROVIDERS)))
    except Exception:  # noqa: BLE001 -- a broken graph answers "no gate names"
        _PLAN_GATE_PROVIDERS = ()
    return _PLAN_GATE_PROVIDERS


def _plan_provider_from_reason(reason: str) -> Optional[str]:
    """The provider a plan-gate park reason asks about, or None.

    Reasons are human sentences ("capacity is PARKED: provider ollama-cloud
    was detected but its plan is undeclared..."), so this matches the known
    provider ids literally in the reason text. First canonical id found wins;
    an id that appears only inside a longer token never matches (word
    boundary on the left, and the ids themselves are the canonical tokens)."""
    text = str(reason or "").lower()
    for provider in _plan_gate_providers():
        if not provider:
            continue
        idx = text.find(provider)
        if idx >= 0 and (idx == 0 or not (text[idx - 1].isalnum()
                                          or text[idx - 1] == "_")):
            return provider
    return None


def _known_plan_entry(provider: Optional[str],
                      config_dir: Optional[Path] = None
                      ) -> Optional[Dict[str, Any]]:
    """The provider's LOCKED interview entry, or None.

    THE ASK-ONCE STORE IS THE RESOURCE PROFILE (resource_profile.py): an
    entry is a known answer only when it is LOCKED -- `record_plan_answer`
    locks a tier, `record_conservative_default` locks the decline, and a
    probe-created entry (no lock) is NOT an answer. Read-only, lazy import
    (the profile imports capacity, so a module-level import would be
    circular), never raises: a box with no profile, a flag-disabled profile
    or a corrupt one yields None and the caller keeps the plain verdict."""
    if not provider:
        return None
    try:
        try:
            from . import resource_profile as rp  # package-relative
        except ImportError:  # pragma: no cover -- direct-path run
            import resource_profile as rp  # type: ignore[no-redef]
    except ImportError:
        return None
    try:
        if not rp.flag_enabled():
            return None
        entry = rp.get_provider(rp.load_profile(config_dir), provider)
        if entry and entry.get("locked"):
            return entry
        return None
    except Exception:  # noqa: BLE001 -- a broken profile never breaks the read
        return None


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

#: state.json key holding the CRASH attempt ledger (Fix 35). A crash is an
#: engine-dead, nonterminal run -- the engine died without parking (BLOCKED)
#: or finishing, so the normal auto-resume path (which only ever un-parks a
#: BLOCKED run) refuses it. Before Fix 35 the poller resumed this shape on
#: EVERY tick with no bound at all: a run whose engine died on startup was
#: re-forked every five minutes, forever. The crash budget lives in its OWN
#: key so crash retries never consume the BLOCKED park budget and a BLOCKED
#: park never consumes the crash budget -- the two failure shapes are
#: different (a park is a decision the engine made; a crash is the engine
#: dying) and their bounds are not fungible.
#:
#: ITEM 10 SUPERSEDES THE SPLIT FOR THE LEDGER. The two-caps-on-two-ledgers
#: shape had a race: each counter measured only its own stream, so a run
#: could be resumed by one path while the other path's counter said the
#: run still had budget -- up to six automatic engine starts in a window
#: under two caps that each claimed three. New attempts from BOTH paths
#: are now rows on ONE ledger (STATE_KEY; crash rows carry kind="crash")
#: and both caps count the merged stream (see `_unified_counted_rows`).
#: This key remains as the LEGACY ledger: rows a field run already holds
#: here keep counting toward the unified cap and stay refundable until
#: they age out of the window, so an upgrade hands no capped run a fresh
#: budget. Nothing new is written here.
CRASH_STATE_KEY = "auto_resume_crash"

#: Automatic CRASH resumes allowed per run per rolling window (Fix 35).
#: Three, like the BLOCKED cap, for the same reason: no run has ever been
#: observed needing a fourth consecutive automatic restart, and a run whose
#: engine dies four times in a day needs a human, not a fifth fork.
#: ITEM 10: retained at the same value for readers that resolve it, but it
#: no longer gates anything on its own -- the crash path enforces the one
#: unified cap (AUTO_RESUME_CAP) over the merged park+crash stream.
AUTO_RESUME_CRASH_CAP = 3

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

# PRES-019 QC4: the recovery request matched a plan ALREADY KNOWN to the
# operator -- the resource profile carries a locked interview answer for the
# provider the park names. The system must NOT re-ask (the question was put
# once, and it was answered) and must NOT loop (a stamp that points the
# client at a question they already answered IS the loop, asked from the
# recovery side). Two shapes, one code:
#   * plan recorded  -> RESUME: the park's cause is cured (capacity.detect
#     reads the locked entry and MEASUREs); proceeding with the known plan is
#     exactly what a resume does -- bounded by the same cap/backoff as any.
#   * plan DECLINED  -> skip: the decline locks ask-once too, but
#     capacity.detect still PARKs a cap-table provider whose plan was
#     declined (there is no tier to measure), so resuming would re-park at
#     the same gate and loop. Report the known-plan state instead: owner and
#     next action named, nothing re-asked.
DECISION_KNOWN_PLAN = "KNOWN-PLAN"

# FIX-PLAN Item 10: the park-class gate's own verdicts. A client_action
# park (BOUND 2b) and an operator_action park that reaches the gate (in
# practice the unclassifiable default) each get a code naming the class,
# so the log says WHO the run is waiting on, not just that it was skipped.
# The older codes above still fire for the shapes they already named
# (OWNER-DECISION, CLOSE-TIME-GATE, CONFIGURATION-PENDING): the class is
# carried on the Decision as `park_class` alongside the code.
DECISION_CLIENT_ACTION = "CLIENT-ACTION"
DECISION_OPERATOR_ACTION = "OPERATOR-ACTION"

#: Fix 35 verdicts, for the crash path (engine dead, run nonterminal) --
#: separate codes so a crash-cap exhaustion never reads as a BLOCKED-park
#: cap exhaustion in the log.
DECISION_CRASH_RESUME = "CRASH-RESUME"
DECISION_CRASH_CAP = "CRASH-CAP-EXHAUSTED"
DECISION_CRASH_WRONG_SHAPE = "CRASH-NOT-APPLICABLE"

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
                 "phase", "attempt", "counted", "cap", "park_class")

    def __init__(self, resume: bool, why: str, code: str, exit_code: int,
                 failure_class: Optional[str] = None,
                 phase: Optional[str] = None,
                 attempt: Optional[int] = None,
                 counted: Optional[int] = None,
                 cap: int = AUTO_RESUME_CAP,
                 park_class: str = "") -> None:
        self.resume = resume
        self.why = why
        self.code = code
        self.exit_code = exit_code
        self.failure_class = failure_class
        self.phase = phase
        self.attempt = attempt
        self.counted = counted
        self.cap = cap
        # Item 10: the park class this verdict belongs to ("" when the
        # verdict is not about a park at all: the crash path, a disabled
        # rollback, an unreadable state).
        self.park_class = park_class

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


def _rows(state: Dict[str, Any],
          key: str = STATE_KEY) -> List[Dict[str, Any]]:
    raw = state.get(key)
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def _counted_rows(state: Dict[str, Any], now: datetime,
                  key: str = STATE_KEY) -> List[Dict[str, Any]]:
    """The attempt rows that COUNT against the cap: inside the rolling window
    and not refunded. A refunded row is one this module later proved bought no
    running engine (see `_refund_manifest_pin_attempts`). `key` selects the
    ledger: STATE_KEY for BLOCKED parks, CRASH_STATE_KEY for crash resumes
    (Fix 35) -- the two caps are always counted separately.

    ITEM 10: the per-key count above is retained for the refund machinery
    and for readers that ask about ONE ledger. The caps themselves no
    longer use it: both decision paths count `_unified_counted_rows`, the
    merged stream, so the two counters can never disagree again."""
    floor = now - timedelta(hours=AUTO_RESUME_WINDOW_HOURS)
    out = []
    for row in _rows(state, key):
        if row.get("refunded"):
            continue
        at = _parse_at(row.get("at"))
        if at is None or at < floor:
            continue
        out.append(row)
    return out


def _unified_counted_rows(state: Dict[str, Any],
                          now: datetime) -> List[Dict[str, Any]]:
    """ITEM 10: THE ONE EVENT STREAM both caps count.

    Every counted attempt row in the rolling window, from the unified
    ledger (STATE_KEY, which now carries park rows AND crash rows) PLUS
    any rows a field run still holds in the legacy crash ledger
    (CRASH_STATE_KEY) from before the unification. Merged and sorted
    oldest-first, so `len()` is the spend against the one cap and the
    last row is the most recent attempt either path made. Counting the
    legacy rows is load-bearing: ignoring them would hand a run that
    spent its crash budget yesterday a fresh budget on upgrade day,
    which is the two-cap race wearing a migration costume."""
    merged = (_counted_rows(state, now, STATE_KEY)
              + _counted_rows(state, now, CRASH_STATE_KEY))
    floor = now - timedelta(hours=AUTO_RESUME_WINDOW_HOURS)
    merged.sort(key=lambda r: _parse_at(r.get("at")) or floor)
    return merged


# ---------------------------------------------------------------------------
# FIX-PLAN ITEM 10 -- PARK CLASSES.
#
# A park class names WHO MUST ACT before the run can move, and carries the
# bounded auto-resume policy for that class:
#
#   transient_infra   -- a provider outage, a network failure, a transient
#                        executor failure: nobody must act. The system
#                        auto-resumes on the existing bounded cadence
#                        (AUTO_RESUME_CAP over the rolling window, the
#                        AUTO_RESUME_BACKOFF_MINUTES ladder).
#   client_action     -- a missing asset, an unanswered question, a
#                        decision only the client can make: NEVER
#                        auto-resumed. The client is notified ONCE per
#                        park with exactly what is needed (see
#                        `notify_park_wait`), and the park waits on the
#                        client. Item 33b's conversational layer plugs
#                        in at this class and at the notification record;
#                        this module builds the class and the record, not
#                        the conversation.
#   operator_action   -- a credential, a close-time verdict, an ambiguity
#                        only a human on the operating team can resolve:
#                        NEVER auto-resumed. The operator is notified once
#                        per park with the specific action needed.
#
# WHERE THE CLASS IS WRITTEN. The engine writes the park itself
# (phases.Engine._block and the close-time writers in phases.py). This
# module classifies at its FIRST EVALUATION of the recorded park -- the
# poller tick immediately after the park lands -- and persists the class
# on the run record (state["park_status"], plus `park_class` on every
# attempt row), derived deterministically from the recorded reason by
# the ONE classifier below, which itself rides on heal.classify_failure
# so the failure vocabulary still has a single definition. The
# classification of a recorded park is therefore identical to what a
# write-time stamp in the engine would say for every park shape the
# classifier covers; the engine-side stamp at the literal write point is
# sequenced separately (phases.py is owned by the Item 9 stream).
#
# THE DEFAULT. A park whose record carries nothing classifiable (no
# blocked record, no reason text) defaults to operator_action: the
# safest class, because it never auto-resumes and it puts a human on
# the run. heal.classify_failure calls an empty reason transient; Item
# 10 does not let an unclassifiable park inherit the retry class by
# that accident.
# ---------------------------------------------------------------------------

PARK_CLASS_TRANSIENT_INFRA = "transient_infra"
PARK_CLASS_CLIENT_ACTION = "client_action"
PARK_CLASS_OPERATOR_ACTION = "operator_action"

#: THE documented default for an unclassifiable park (see the section
#: header): never auto-resume, a human looks.
DEFAULT_PARK_CLASS = PARK_CLASS_OPERATOR_ACTION

#: state.json key holding the client-safe park status record (Item 10
#: work item 3). state.json is the run record the board and the client
#: surfaces already read; configuration_pending is the precedent.
PARK_STATUS_KEY = "park_status"

#: state.json key holding the once-per-park notification record.
PARK_NOTIFY_KEY = "park_notification"

#: The per-class policy, in one place: whether the class auto-resumes,
#: who the run waits on, and the plain-words label the client record
#: carries. The bounds for the auto-resuming class are the module's
#: existing AUTO_RESUME_CAP / AUTO_RESUME_WINDOW_HOURS /
#: AUTO_RESUME_BACKOFF_MINUTES; the policy table names the policy, the
#: constants keep the numbers.
PARK_POLICY: Dict[str, Dict[str, Any]] = {
    PARK_CLASS_TRANSIENT_INFRA: {
        "auto_resume": True,
        "waiting_on": "system",
        "label": "Paused by a temporary problem, retrying on its own",
    },
    PARK_CLASS_CLIENT_ACTION: {
        "auto_resume": False,
        "waiting_on": "client",
        "label": "Waiting for you",
    },
    PARK_CLASS_OPERATOR_ACTION: {
        "auto_resume": False,
        "waiting_on": "operator",
        "label": "Waiting for our team",
    },
}

#: The subset of heal's missing-input vocabulary that names something
#: only the CLIENT can supply. heal's own comment defines its
#: missing-input class as "an artifact another unit should have
#: produced", and every other marker in it names an engine-produced
#: artifact a resume re-creates; "missing intake" is the one that names
#: the client's own answers.
CLIENT_MISSING_MARKERS: Tuple[str, ...] = ("missing intake",)

#: The configuration markers split by who must act, mirroring the owner
#: split `_configuration_pending_decision` already makes: credential
#: markers are the box owner's (operator) action; the rest are the
#: resource-plan answer the client owes.
_CREDENTIAL_MARKERS: Tuple[str, ...] = (
    "has no resolvable key",
    "no store carries a plausible credential",
)
_PLAN_MARKERS: Tuple[str, ...] = tuple(
    m for m in CONFIGURATION_PENDING_MARKERS if m not in _CREDENTIAL_MARKERS)

# Plain-words "what is needed" lines for the client record and the
# notifications. Written for the reader named in each: no phase ids
# beyond the one human gate, no error text, no internal vocabulary. The
# raw blocked reason is NEVER copied into the client record.
_NEEDED_TRANSIENT = (
    "Nothing is needed from you. A temporary problem stopped this step "
    "and the system is retrying on its own.")
_NEEDED_CREDENTIAL = (
    "Our team needs to add a provider credential to the box's credential "
    "store. Nothing is needed from you.")
_NEEDED_PLAN = (
    "We need one answer from you: the resource plan for this run. Once "
    "you answer, the run continues on its own.")
_NEEDED_PLAN_DECLINED = (
    "Nothing new is needed. A no-metering choice is already on record "
    "for this run, so it stays paused until you tell us to continue "
    "another way.")
_NEEDED_STYLE_PICK = (
    "We need your style pick: reply A, B or C for the style samples you "
    "were sent. The deck continues as soon as you pick.")
_NEEDED_OWNER_DECISION = (
    "We need a decision from you on this step. Reply with your decision "
    "and the run continues.")
_NEEDED_MISSING_INTAKE = (
    "We are missing part of your intake. Send the missing item and the "
    "run continues.")
_NEEDED_CLOSE_VERDICT = (
    "A final quality check did not pass, so our team needs to review it "
    "before anything is handed over. Nothing is needed from you.")
_NEEDED_UNCLASSIFIABLE = (
    "Our team needs to look at this run and decide the next step. "
    "Nothing is needed from you.")


def classify_park(state: Dict[str, Any],
                  failure_class: Optional[str] = None) -> Dict[str, Any]:
    """Derive the Item 10 park class for the run's recorded park.

    Returns {"park_class", "waiting_on", "label", "auto_resume",
    "needed", "basis"}: the class, the policy view of it, the
    plain-words line naming what is needed from whom, and the basis the
    classification rests on (kept for logs and tests; the client record
    carries the plain fields, never the basis or the raw reason).

    Pure: reads `state` only. The order is load-bearing and mirrors the
    bounds in `evaluate`: configuration markers first (a credential park
    classifies provider_error to heal, because the gate that names it
    talks about providers, and it is NOT a retryable provider blip),
    then heal's failure class, with two documented refinements: an owner
    decision waits on the run's owner (the client), and heal's
    missing-input class splits on whether the missing thing is the
    client's own input or an artifact the engine re-creates on a resume.
    """
    blocked = state.get("blocked") if isinstance(state, dict) else None
    blocked = blocked if isinstance(blocked, dict) else {}
    reason = str(blocked.get("reason") or "")
    phase = str(blocked.get("phase") or "")
    text = reason.lower()

    def _result(park_class: str, needed: str, basis: str) -> Dict[str, Any]:
        policy = PARK_POLICY[park_class]
        return {"park_class": park_class,
                "waiting_on": policy["waiting_on"],
                "label": policy["label"],
                "auto_resume": policy["auto_resume"],
                "needed": needed,
                "basis": basis}

    if not text.strip():
        return _result(
            DEFAULT_PARK_CLASS, _NEEDED_UNCLASSIFIABLE,
            "unclassifiable: the park record carries no reason text, so "
            "no class can be derived; the documented default applies "
            "(operator_action, the safest class)")

    if any(m in text for m in _CREDENTIAL_MARKERS):
        return _result(
            PARK_CLASS_OPERATOR_ACTION, _NEEDED_CREDENTIAL,
            "configuration park: a provider credential is missing, which "
            "only the operating team can supply")

    if any(m in text for m in _PLAN_MARKERS):
        stamp = state.get("configuration_pending")
        known_plan = (stamp.get("known_plan") if isinstance(stamp, dict)
                      else None)
        if isinstance(known_plan, dict) and known_plan.get("declined"):
            return _result(
                PARK_CLASS_CLIENT_ACTION, _NEEDED_PLAN_DECLINED,
                "configuration park: the resource-plan answer is already "
                "recorded as a decline; nothing is re-asked")
        return _result(
            PARK_CLASS_CLIENT_ACTION, _NEEDED_PLAN,
            "configuration park: a one-time resource-plan answer is owed "
            "by the client")

    fclass = failure_class or classify_failure(reason)
    if fclass == FAILURE_OWNER_DECISION:
        needed = (_NEEDED_STYLE_PICK if phase == "P-STYLE-PICK"
                  else _NEEDED_OWNER_DECISION)
        return _result(
            PARK_CLASS_CLIENT_ACTION, needed,
            "owner decision: in this system the deciding party is the "
            "run's owner (the client) -- a style pick, a waiver, a gate "
            "decline -- so the run waits on the client")
    if fclass == FAILURE_PROVIDER_ERROR:
        return _result(PARK_CLASS_TRANSIENT_INFRA, _NEEDED_TRANSIENT,
                       "provider error: something outside this system "
                       "failed and a bounded retry is the cure")
    if fclass == FAILURE_MISSING_INPUT:
        if any(m in text for m in CLIENT_MISSING_MARKERS):
            return _result(
                PARK_CLASS_CLIENT_ACTION, _NEEDED_MISSING_INTAKE,
                "missing input only the client can supply (their intake)")
        return _result(
            PARK_CLASS_TRANSIENT_INFRA, _NEEDED_TRANSIENT,
            "missing input the engine itself produces: a resume re-runs "
            "the producing phase")
    if fclass == FAILURE_VERIFIER_SUBSTANCE:
        if phase in CLOSE_TIME_PHASES:
            return _result(
                PARK_CLASS_OPERATOR_ACTION, _NEEDED_CLOSE_VERDICT,
                "close-time gate verdict: a gate judged the artifacts "
                "and said no; the operating team reviews it")
        return _result(
            PARK_CLASS_TRANSIENT_INFRA, _NEEDED_TRANSIENT,
            "verifier substance at an authoring phase: a resume "
            "re-authors with the verifier's notes (the behaviour "
            "test_auto_resume pins)")
    if fclass == FAILURE_TRANSIENT:
        return _result(PARK_CLASS_TRANSIENT_INFRA, _NEEDED_TRANSIENT,
                       "transient failure: the classifier's retry class, "
                       "positively matched or its documented fallback "
                       "for a reason with classifiable text")
    return _result(
        DEFAULT_PARK_CLASS, _NEEDED_UNCLASSIFIABLE,
        f"unclassifiable: failure class {fclass!r} has no park-class "
        "mapping; the documented default applies (operator_action, the "
        "safest class)")


def park_status_record(state: Dict[str, Any],
                       decision: Optional[Decision] = None
                       ) -> Dict[str, Any]:
    """The client-safe park status record (Item 10 work item 3).

    Built from the classification of the CURRENT recorded park, never
    from the raw reason: the reason string appears nowhere in the
    record. `since` is the park's own stamp (state["blocked"]["at"]);
    the close-time writers that record no `at` fall back to the moment
    of this record, which `recorded_at` always carries. Attempt figures
    ride along only when the decision that prompted the record counted
    them (the cap and backoff refusals of the transient class)."""
    park = classify_park(
        state, decision.failure_class if decision is not None else None)
    blocked = state.get("blocked")
    blocked = blocked if isinstance(blocked, dict) else {}
    record: Dict[str, Any] = {
        "park_class": park["park_class"],
        "label": park["label"],
        "waiting_on": park["waiting_on"],
        "needed": park["needed"],
        "auto_resume": park["auto_resume"],
        "since": str(blocked.get("at") or "") or utcnow(),
        "recorded_at": utcnow(),
        "by": "presentation_job.auto_resume",
    }
    if blocked.get("phase"):
        record["phase"] = str(blocked["phase"])
    if (park["park_class"] == PARK_CLASS_TRANSIENT_INFRA
            and decision is not None and decision.counted is not None):
        record["attempts_used"] = decision.counted
        record["attempts_cap"] = decision.cap
    return record


def _stamp_park_status(run_path: Path, decision: Decision) -> bool:
    """Write state["park_status"] for a park that is STAYING parked.

    Called on the refusal paths of `evaluate` only: a resume decision
    ends the park, so it stamps nothing (a record describing a wait is
    written when the wait is real). Re-reads state fresh, because the
    configuration paths stamp state["configuration_pending"] during the
    same evaluation and the client record must agree with it (the
    known-plan decline wording depends on it). Fail-soft like the
    configuration stamp: a failed merge loses the record, never the
    verdict."""
    state, _why = _read_state(run_path)
    if state is None or str(state.get("terminal") or "") != "BLOCKED":
        return False
    record = park_status_record(state, decision)
    return _merge(run_path,
                  lambda st: st.__setitem__(PARK_STATUS_KEY, record))


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


def _refund_manifest_pin_attempts(state: Dict[str, Any], now: datetime,
                                  key: str = STATE_KEY) -> int:
    """Mark attempts that were spent under the pin that is STILL stale.

    An attempt row records the manifest sha the run was pinned to at the time.
    If the run is still pinned to that same sha while the manifest on disk has
    moved, that attempt bought a one-second EXIT_MANIFEST_MISMATCH death and
    nothing else. Refunding it is not generosity, it is accuracy: the cap
    counts ENGINE STARTS, and that attempt started no engine.

    Mutates `state` in place and returns how many rows it refunded. Bounded in
    the only direction that matters: it can only ever REMOVE attempts from the
    tally, and only for rows whose recorded pin is provably the stale one, so
    it can never manufacture an extra attempt. `key` selects which ledger the
    refund applies to -- the BLOCKED ledger, or the Fix 35 crash ledger.
    """
    pinned = state.get("manifest_sha256")
    if not isinstance(pinned, str) or not pinned:
        return 0
    refunded = 0
    for row in _counted_rows(state, now, key):
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


def _known_plan_decision(run_path: Path, phase: Optional[str],
                         reason: str, fclass: str, provider: str,
                         entry: Dict[str, Any]) -> Decision:
    """PRES-019 QC4: the KNOWN-PLAN verdict -- the recovery request matched a
    plan already known to the operator.

    The question was asked ONCE (resource_profile's lock) and the profile
    carries the answer, so the recovery machinery must NOT put it again: a
    configuration_pending stamp that points the client at a question they
    already answered is the re-ask, and re-issuing it every poller tick is
    the loop. What happens instead depends on WHICH known answer it is:

      * a recorded TIER (plan_tier set): the park's cause is cured --
        capacity.detect reads the locked entry (its own stage-2 precedence:
        model slug > detected > profile > override) and returns MEASURED at
        the recorded plan. The recovery request therefore PROCEEDS WITH THE
        KNOWN PLAN: resume=True, one bounded attempt (the same cap/backoff
        ladder as every other auto-resume -- the bounds are what stop a
        loop if the park turns out to have a second cause). The stamp is
        NOT configuration_pending (the configuration is not pending; it is
        known); the decision's why names the recorded plan and where it is
        stored, and state.json carries a known_plan stamp so the provenance
        survives detached execution.

      * a recorded DECLINE (locked, no tier): ask-once locks the decline
        too -- the client answered, so no re-ask. But capacity.detect still
        PARKs a cap-table provider whose plan was declined (nothing to
        measure), so a resume here would re-park at the same gate and
        loop. The recovery request therefore stays parked and REPORTS THE
        KNOWN-PLAN STATE: owner + next action name the recorded decline and
        the door that actually widens the run (an explicit operator
        declaration), and a configuration_pending stamp records THAT --
        never the question again.
    """
    plan_text = str(entry.get("plan_tier") or "").strip()
    if plan_text:
        why = (
            f"the park at {phase or 'an unrecorded phase'} names a plan-gate "
            f"({reason[:160]!r}), but the plan is ALREADY KNOWN: the resource "
            f"profile carries a locked answer for {provider} "
            f"(plan_tier={plan_text!r}, answered_at="
            f"{str(entry.get('answered_at') or 'unrecorded')[:19]}). The "
            "one-time question was asked once and answered -- this recovery "
            "does NOT re-ask it and does NOT stamp configuration_pending; it "
            f"proceeds with the known plan. Owner: the operator (nothing to "
            "do unless the answer itself is wrong).")
        return Decision(True, why, DECISION_KNOWN_PLAN, EXIT_RESUME,
                        failure_class=fclass, phase=phase)
    # The recorded answer is a DECLINE. Never re-ask; never loop; report.
    owner = ("the client (they chose 'use conservative default' for this "
             "provider)")
    next_action = ("the decline is already recorded and will not be asked "
                   "again; a declined cap-table provider has no tier to "
                   "measure, so the run needs the operator to widen it "
                   "explicitly (--declare-capacity N --declare-provider "
                   f"{provider}) or to record a real plan tier")
    why = (f"the park at {phase or 'an unrecorded phase'} names a plan-gate, "
           f"but the answer is ALREADY KNOWN and it is a DECLINE: the "
           f"resource profile carries a locked 'use conservative default' "
           f"for {provider}. The question is NOT re-asked (asked ONCE, and "
           "it was answered); the run stays parked because a declined "
           "cap-table provider has no tier capacity could measure -- a "
           "resume here would re-park at the same gate. Owner: "
           f"{owner}. Next action: {next_action}.")

    def _stamp(state: Dict[str, Any]) -> None:
        state["configuration_pending"] = {
            "at": utcnow(),
            "phase": phase,
            "reason": reason[:400],
            "matched_marker": next(
                (m for m in CONFIGURATION_PENDING_MARKERS
                 if m in reason.lower()), None),
            "failure_class": fclass,
            "known_plan": {
                "provider": provider,
                "recorded_choice": "use conservative default",
                "answered_at": entry.get("answered_at"),
                "source": "resource profile (locked entry)",
            },
            "owner": owner,
            "next_action": next_action,
            "reminder": ("the recorded decline is reported as the known "
                         "answer it is -- the question is never re-asked"),
            "by": "presentation_job.auto_resume",
        }

    _merge(run_path, _stamp)
    return Decision(False, why, DECISION_KNOWN_PLAN, EXIT_SKIP,
                    failure_class=fclass, phase=phase)


def evaluate(run_dir, now: Optional[datetime] = None) -> Decision:
    """The full verdict for one run dir.

    Reads only, with two long-standing write exceptions that are part of
    the verdict's contract, plus one Item 10 addition: the PRES-019
    configuration stamp (written by the decision helpers), and -- on
    refusal paths only -- the Item 10 park_status stamp (see
    `_stamp_park_status`). It never records an attempt and never
    notifies: those belong to `main`, after the verdict.

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

    # --- ITEM 10: the park class, derived ONCE from the recorded park.
    # Every verdict below carries it, every refusal below stamps the
    # client-safe record from it, and BOUND 2b enforces the two
    # never-auto-resume classes as a gate in their own right.
    park = classify_park(state, fclass)

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
        # --- PRES-019 QC4: check the ask-once store BEFORE declaring the
        # configuration missing. A plan-gate park whose provider already
        # carries a LOCKED interview answer must not re-ask (the stamp would
        # point the client at a question they answered). Two shapes:
        #   * a recorded TIER -- the recovery request PROCEEDS WITH THE
        #     KNOWN PLAN. The bounds below (cap, backoff) still gate the
        #     resume: a stronger bound outranks a known plan, so the fourth
        #     tick on a run that keeps re-parking is CAP-EXHAUSTED for a
        #     human, never an unbounded re-dispatch. The known-plan decision
        #     therefore returns the Decision the bounds produce -- the
        #     `known_plan` flag only changes WHAT the decision says (the
        #     known plan, never a re-ask), never WHAT the bounds allow.
        #   * a recorded DECLINE -- parked, reported as KNOWN-PLAN (the
        #     decline itself never re-asks and never loops; a resume would
        #     re-park at the same gate).
        plan_provider = _plan_provider_from_reason(reason_text)
        plan_entry = _known_plan_entry(plan_provider)
        if plan_provider and plan_entry:
            known = _known_plan_decision(run_path, phase, reason_text,
                                         fclass, plan_provider, plan_entry)
            if not known.resume:
                known.park_class = park["park_class"]
                _stamp_park_status(run_path, known)
                return known
            # fall through: the cap/backoff bounds decide whether this
            # known-plan resume may actually proceed.
            known_plan_reason = known.why
        else:
            pending = _configuration_pending_decision(run_path, phase,
                                                      reason_text, fclass)
            pending.park_class = park["park_class"]
            _stamp_park_status(run_path, pending)
            return pending
    else:
        known_plan_reason = None

    # --- BOUND 1: class. The heal ladder's own classifier, not a second one.
    if fclass == FAILURE_OWNER_DECISION:
        decision = Decision(False,
                            f"the park at {phase or 'an unrecorded phase'} "
                            f"classifies as {FAILURE_OWNER_DECISION} "
                            f"({str(reason)[:180]!r}) -- an owner decision is "
                            "never auto-healed and never auto-resumed; a person "
                            "has to decide",
                            DECISION_OWNER, EXIT_SKIP, failure_class=fclass,
                            phase=phase, park_class=park["park_class"])
        _stamp_park_status(run_path, decision)
        return decision

    # --- BOUND 2: close-time gates, unless nothing actually got judged.
    if phase in CLOSE_TIME_PHASES and fclass not in RETRYABLE_AT_CLOSE:
        decision = Decision(False,
                            f"the park is at the close-time sentinel {phase} with "
                            f"class {fclass} -- a gate, the certificate integrity "
                            "check, curation or the self-audit judged the "
                            "artifacts and said no. Asking it again with the same "
                            "artifacts gets the same answer, so no attempt is "
                            f"spent. (Only {'/'.join(RETRYABLE_AT_CLOSE)} pass "
                            "here, because those mean nothing was judged at all.)",
                            DECISION_CLOSE_GATE, EXIT_SKIP,
                            failure_class=fclass, phase=phase,
                            park_class=park["park_class"])
        _stamp_park_status(run_path, decision)
        return decision

    # --- BOUND 2b (ITEM 10): the park-class gate. The classes that wait
    # on a person are refused HERE, as a policy of the class itself, not
    # as a side effect of the older bounds: a client_action park that no
    # older bound happened to catch (a missing intake was the measured
    # shape: it fell through every bound and burned attempts on resumes
    # that could not fix it) still never auto-resumes, and an
    # unclassifiable park lands on the documented default. The one
    # exception is a known-plan fall-through from BOUND 0: the client
    # already answered, so the park is no longer waiting on them and the
    # ordinary bounds decide.
    if not known_plan_reason:
        if park["park_class"] == PARK_CLASS_CLIENT_ACTION:
            decision = Decision(
                False,
                f"the park at {phase or 'an unrecorded phase'} is park "
                f"class CLIENT-ACTION ({park['basis']}) -- it is never "
                "auto-resumed, because only the client can clear it. The "
                "client is notified once with exactly what is needed; "
                "the park waits on the client.",
                DECISION_CLIENT_ACTION, EXIT_SKIP, failure_class=fclass,
                phase=phase, park_class=park["park_class"])
            _stamp_park_status(run_path, decision)
            return decision
        if park["park_class"] == PARK_CLASS_OPERATOR_ACTION:
            decision = Decision(
                False,
                f"the park at {phase or 'an unrecorded phase'} is park "
                f"class OPERATOR-ACTION ({park['basis']}) -- it is never "
                "auto-resumed, because only a human on the operating "
                "team can clear it. The operator is notified once with "
                "the specific action needed.",
                DECISION_OPERATOR_ACTION, EXIT_SKIP, failure_class=fclass,
                phase=phase, park_class=park["park_class"])
            _stamp_park_status(run_path, decision)
            return decision

    # --- THE F2 DEPENDENCY: never spend an attempt on a death we can predict.
    status, mwhy = _manifest_status(state, run_path)
    if status == "mismatch":
        repin, rwhy = _auto_repin_available()
        if repin is not True:
            entry = _scripts_dir() / "presentation_job.py"
            decision = Decision(
                False,
                "the manifest moved under this run and this resume would die "
                f"EXIT_MANIFEST_MISMATCH in about one second: {mwhy}. "
                f"{rwhy}. Spending one of {AUTO_RESUME_CAP} attempts on a "
                "death that is certain would leave a fixable run with no "
                "budget once the pin is cured, so NO attempt was spent. "
                f"Cure it with: {entry} --repin --run-dir {run_path}",
                DECISION_MANIFEST_PIN, EXIT_UNDETERMINED,
                failure_class=fclass, phase=phase,
                park_class=park["park_class"])
            _stamp_park_status(run_path, decision)
            return decision
        # F2 is present: the launcher re-pins before it spawns, so the
        # mismatch is not an obstacle -- say so rather than staying silent.
        print(f"auto-resume: {mwhy}; {rwhy} -- the resume will re-pin itself "
              "before the engine starts", flush=True)

    # --- BOUND 3: the cap, counted over a rolling window, refunds honoured.
    # ITEM 10: counted over the UNIFIED stream (park rows and crash rows
    # together, legacy crash rows included), so this cap and the crash
    # cap are the same fact measured once, never two counters that can
    # disagree about the same run.
    counted = _unified_counted_rows(state, now)
    if len(counted) >= AUTO_RESUME_CAP:
        newest = max((_parse_at(r.get("at")) for r in counted
                      if _parse_at(r.get("at"))), default=None)
        decision = Decision(False,
                            f"{len(counted)} automatic resume(s) have already been "
                            f"spent on this run in the last "
                            f"{AUTO_RESUME_WINDOW_HOURS}h (cap {AUTO_RESUME_CAP}; "
                            f"most recent {newest.isoformat() if newest else 'unknown'}). "
                            "This run is now parked for a HUMAN -- three automatic "
                            "attempts did not clear it, so it is not the kind of "
                            f"failure another attempt fixes. "
                            + (f"(The plan is already known -- {known_plan_reason}"
                               if known_plan_reason else ""),
                            DECISION_CAP, EXIT_SKIP, failure_class=fclass,
                            phase=phase, counted=len(counted),
                            park_class=park["park_class"])
        _stamp_park_status(run_path, decision)
        return decision

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
                decision = Decision(
                    False,
                    f"attempt {attempt} of {AUTO_RESUME_CAP} must wait "
                    f"{wait_minutes} minute(s) after the previous automatic "
                    f"resume ({last.isoformat()}); only {elapsed:.1f} have "
                    "passed. Backoff is what stops a broken run from spending "
                    "its whole cap inside three poller ticks.",
                    DECISION_BACKOFF, EXIT_SKIP, failure_class=fclass,
                    phase=phase, counted=len(counted), attempt=attempt,
                    park_class=park["park_class"])
                _stamp_park_status(run_path, decision)
                return decision

    if known_plan_reason:
        # PRES-019 QC4: the bounds allowed this resume and the plan is
        # already known -- report the KNOWN-PLAN verdict, not a plain RESUME,
        # so the decision line never reads as if the question were asked.
        return Decision(
            True,
            f"attempt {attempt} of {AUTO_RESUME_CAP}: {known_plan_reason} "
            f"(bounded as always: {len(counted)} attempt(s) spent in the "
            f"last {AUTO_RESUME_WINDOW_HOURS}h, manifest pin {status}).",
            DECISION_KNOWN_PLAN, EXIT_RESUME, failure_class=fclass,
            phase=phase, attempt=attempt, counted=len(counted),
            park_class=park["park_class"])

    return Decision(
        True,
        f"attempt {attempt} of {AUTO_RESUME_CAP}: parked at "
        f"{phase or 'an unrecorded phase'} with class {fclass} "
        f"({str(reason)[:180]!r}) -- retryable, not an owner decision, "
        f"{len(counted)} attempt(s) spent in the last "
        f"{AUTO_RESUME_WINDOW_HOURS}h, manifest pin {status}.",
        DECISION_RESUME, EXIT_RESUME, failure_class=fclass, phase=phase,
        attempt=attempt, counted=len(counted),
        park_class=park["park_class"])


def evaluate_crash(run_dir, now: Optional[datetime] = None) -> Decision:
    """The full verdict for an engine-DEAD, nonterminal run. PURE: reads only.

    The crash path is the shape the BLOCKED path refuses: state.json exists,
    no engine is alive, and terminal is NOT BLOCKED (DONE and ABANDONED are
    endings and are never resumed by anything; BLOCKED belongs to
    `evaluate`). Before Fix 35 the poller resumed this shape on every tick
    with no bound at all -- a run whose engine died on startup was re-forked
    every five minutes, forever.

    The bound is the same SHAPE as the BLOCKED path (a cap over a rolling
    window, backoff between attempts, never spending an attempt on a death
    the manifest pin makes certain). Fix 35 originally gave it a SEPARATE
    cap (AUTO_RESUME_CRASH_CAP) in a SEPARATE ledger
    (state[CRASH_STATE_KEY]); FIX-PLAN Item 10 unified the ledger: both
    paths now spend from ONE stream under ONE cap (AUTO_RESUME_CAP), so a
    run at its cap is refused by whichever path asks. The two failure
    shapes are still different -- a park is a decision the engine made, a
    crash is the engine dying -- and they still get separate verdicts and
    separate decision codes; what they no longer get is separate budgets
    that can disagree.

    No operator chat alert on crash-cap exhaustion (unlike the BLOCKED path):
    the poller logs the decider's reason on every tick it leaves the run
    dead, which is where a crash loop is visible; a chat alert would
    duplicate that line, not add to it.
    """
    now = now or datetime.now(timezone.utc)
    run_path = Path(run_dir).expanduser()

    if os.environ.get(AUTO_RESUME_ENV, "").strip() == "0":
        return Decision(False, f"auto-resume is DISABLED ({AUTO_RESUME_ENV}=0) "
                               "-- this crashed run is left dead for a human, "
                               "which is the pre-Fix-35 behaviour",
                        DECISION_DISABLED, EXIT_SKIP,
                        cap=AUTO_RESUME_CAP)

    state, why = _read_state(run_path)
    if state is None:
        return Decision(False, f"cannot decide: {why}. Nothing was resumed "
                               "and no crash attempt was spent.",
                        DECISION_UNREADABLE, EXIT_UNDETERMINED,
                        cap=AUTO_RESUME_CAP)

    terminal = str(state.get("terminal") or "")
    if terminal in ("DONE", "ABANDONED"):
        return Decision(False, f"terminal is {terminal!r} -- an ending, "
                               "never resumed by anything, crash path "
                               "included",
                        DECISION_CRASH_WRONG_SHAPE, EXIT_SKIP,
                        cap=AUTO_RESUME_CAP)
    if terminal == "BLOCKED":
        return Decision(False, "terminal is 'BLOCKED' -- a parked run belongs "
                               "to the normal auto-resume path, not the crash "
                               "path (call without --crash)",
                        DECISION_CRASH_WRONG_SHAPE, EXIT_SKIP,
                        cap=AUTO_RESUME_CAP)

    # --- The F2 dependency: never spend an attempt on a death we can predict.
    status, mwhy = _manifest_status(state, run_path)
    if status == "mismatch":
        repin, rwhy = _auto_repin_available()
        if repin is not True:
            return Decision(
                False,
                "the manifest moved under this run and this resume would die "
                f"EXIT_MANIFEST_MISMATCH in about one second: {mwhy}. "
                f"{rwhy}. Spending one of {AUTO_RESUME_CAP} attempts on a "
                "death that is certain would leave a fixable "
                "run with no budget once the pin is cured, so NO attempt was "
                "spent.",
                DECISION_MANIFEST_PIN, EXIT_UNDETERMINED,
                cap=AUTO_RESUME_CAP)

    # --- The cap, counted over a rolling window, refunds honoured --
    # ITEM 10: over the UNIFIED stream. A run that spent its budget on
    # park resumes has none left for crash resumes, and vice versa.
    counted = _unified_counted_rows(state, now)
    if len(counted) >= AUTO_RESUME_CAP:
        newest = max((_parse_at(r.get("at")) for r in counted
                      if _parse_at(r.get("at"))), default=None)
        return Decision(False,
                        f"{len(counted)} automatic resume(s) have "
                        f"already been spent on this run in the last "
                        f"{AUTO_RESUME_WINDOW_HOURS}h (unified cap "
                        f"{AUTO_RESUME_CAP} over park and crash attempts "
                        f"together; most recent "
                        f"{newest.isoformat() if newest else 'unknown'}). "
                        "This run is now left dead for a HUMAN -- three "
                        "automatic restarts did not keep an engine alive, "
                        "so it is not the kind of failure another fork "
                        "fixes.",
                        DECISION_CRASH_CAP, EXIT_SKIP,
                        counted=len(counted), cap=AUTO_RESUME_CAP)

    # --- Backoff since the previous automatic crash resume (same schedule as
    # the BLOCKED path: the first retry is immediate, the 2nd and 3rd wait).
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
                    f"crash attempt {attempt} of {AUTO_RESUME_CAP} must "
                    f"wait {wait_minutes} minute(s) after the previous "
                    f"automatic resume ({last.isoformat()}); only "
                    f"{elapsed:.1f} have passed. Backoff is what stops a run "
                    "whose engine dies on startup from spending its whole "
                    "cap inside three poller ticks.",
                    DECISION_BACKOFF, EXIT_SKIP,
                    counted=len(counted), attempt=attempt,
                    cap=AUTO_RESUME_CAP)

    return Decision(
        True,
        f"crash attempt {attempt} of {AUTO_RESUME_CAP}: the engine is "
        f"dead and the run is nonterminal (terminal {terminal or 'unset'!r}) "
        f"-- {len(counted)} automatic attempt(s) of either kind spent in "
        f"the last {AUTO_RESUME_WINDOW_HOURS}h, manifest pin {status}.",
        DECISION_CRASH_RESUME, EXIT_RESUME,
        attempt=attempt, counted=len(counted), cap=AUTO_RESUME_CAP)


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
        # Item 10: rows on the ONE ledger say which path spent them and
        # which park class the spend answered, so the next diagnostic can
        # measure park time and spend by class honestly.
        "kind": "park",
        "park_class": decision.park_class,
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
            # Item 10: refunds are kind-scoped on the unified ledger. A
            # crash row is the crash path's charge to give back, never
            # this function's (see refund_last_crash_attempt).
            if row.get("kind") == "crash":
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


def record_crash_attempt(run_dir, decision: Decision) -> bool:
    """Append one attempt row to the ONE ledger, and say whether it landed.

    ITEM 10: the row lands on state[STATE_KEY] with kind="crash", not on
    the legacy crash key -- one event stream, counted once by both caps.
    (Fix 35 wrote state[CRASH_STATE_KEY]; rows already there keep
    counting and stay refundable, but nothing new is written there.)

    RECORDED BEFORE THE DISPATCH, deliberately, for the same reason as
    `record_attempt`. And the return value is load-bearing in the same way:
    a cap counted from a ledger that could not be written is not a cap, so
    `main()` treats a failed record as a REFUSAL -- nothing is dispatched.
    An uncounted crash resume repeats every poller tick forever, which is the
    exact runaway Fix 35 exists to close.
    """
    run_path = Path(run_dir).expanduser()
    row = {
        "at": utcnow(),
        "phase": decision.phase,
        "class": decision.failure_class,
        "attempt": decision.attempt,
        "cap": AUTO_RESUME_CAP,
        "window_hours": AUTO_RESUME_WINDOW_HOURS,
        "by": "presentation_job.auto_resume",
        "kind": "crash",
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
        # A fresh attempt reopens the alert, exactly as a park attempt
        # does: both spend from the one budget the alert reports on.
        state.pop(ALERT_KEY, None)

    ok = _merge(run_path, _mutate)
    if not ok:
        print(f"auto-resume: could not record crash attempt {decision.attempt} "
              f"in {run_path}/state.json (the run lock stayed busy, or the "
              "file is missing/unreadable). REFUSING the resume rather than "
              "spending a crash attempt the cap cannot see -- an uncounted "
              "attempt repeats every poller tick forever. Retrying next tick.",
              file=sys.stderr)
    return ok


def refund_last_crash_attempt(run_dir, reason: str) -> bool:
    """Give the most recent CRASH attempt back, because it bought no engine.

    The crash twin of `refund_last_attempt`: the cap counts ENGINE STARTS,
    and a crash attempt whose dispatch produced nothing (the launcher
    refused, or the running-engine proof came back negative) must not eat
    the budget. Marks at most ONE row, the newest un-refunded crash row,
    and only a row this module wrote -- it can never touch a PARK row, add
    an attempt, or un-refund one.

    ITEM 10: crash rows live on the unified ledger now, so the search
    order is the unified ledger first (kind="crash" rows there), then the
    LEGACY crash ledger, whose pre-unification rows stay refundable
    until they age out.
    """
    run_path = Path(run_dir).expanduser()
    marked = {"done": False}

    def _refund_in(rows_: Any) -> bool:
        if not isinstance(rows_, list):
            return False
        for row in reversed(rows_):
            if not isinstance(row, dict) or row.get("refunded"):
                continue
            if row.get("by") != "presentation_job.auto_resume":
                continue
            if row.get("kind") != "crash":
                continue
            row["refunded"] = "no-engine-started"
            row["refunded_at"] = utcnow()
            row["refunded_why"] = str(reason)[:400]
            return True
        return False

    def _mutate(state: Dict[str, Any]) -> None:
        if _refund_in(state.get(STATE_KEY)):
            marked["done"] = True
            return
        if _refund_in(state.get(CRASH_STATE_KEY)):
            marked["done"] = True

    if not _merge(run_path, _mutate):
        print("auto-resume: could not refund the last crash attempt in "
              f"{run_path}/state.json -- it stays counted against the "
              "cap", file=sys.stderr)
        return False
    if marked["done"]:
        print(f"auto-resume: refunded the crash attempt just made on "
              f"{run_path.name} -- no engine started ({str(reason)[:200]}). "
              "The crash cap counts engine starts, not dispatch attempts.",
              flush=True)
    else:
        print(f"auto-resume: nothing to refund on {run_path.name} (no "
              "un-refunded crash attempt of this module's own on the ledger)",
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
    # Item 10: the exhaustion is a fact about the UNIFIED stream, so the
    # once-only key is the newest counted row of either kind.
    counted = _unified_counted_rows(state, datetime.now(timezone.utc))
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


def _requester_chat_id(run_path: Path,
                       state: Dict[str, Any]) -> Optional[str]:
    """The requester's chat id as the run itself records it: state.json's
    requester block first (the shape report.Reporter reads), then the
    intake ledger's requester_chat_id (the shape the hosted bridge and
    the poller carry). None when the run records neither -- the caller
    then records the notification as undeliverable rather than inventing
    an address."""
    requester = state.get("requester")
    if isinstance(requester, dict):
        chat_id = requester.get("chat_id")
        if chat_id:
            return str(chat_id)
    ledger_path = (run_path / "working" / "interview"
                   / "intake_ledger.json")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if isinstance(ledger, dict) and ledger.get("requester_chat_id"):
        return str(ledger["requester_chat_id"])
    return None


def notify_park_wait(run_dir, decision: Decision) -> Optional[bool]:
    """ITEM 10: the once-per-park notification for a park that waits on a
    person, and the record that proves it happened.

    client_action parks notify the CLIENT, once, with exactly what is
    needed (the classification's plain-words `needed` line, never the raw
    park reason). operator_action parks notify the OPERATOR, once, with
    the specific action needed. "Once" is per PARK INSTANCE (phase +
    park stamp): the record lands in state[PARK_NOTIFY_KEY] keyed to the
    park, and a later tick on the same park sends nothing. A new park at
    the same phase is a new instance and is news again.

    The RECORD is the deliverable this stream owns: it is written whether
    or not a transport exists, with the delivery outcome stated. Item
    33b's conversational layer reads this record (and the class) later;
    the conversation itself is not built here.

    Returns True (sent and confirmed), False (attempted, not confirmed,
    or no address/transport), or None (already notified for this park --
    nothing sent).
    """
    run_path = Path(run_dir).expanduser()
    state, _why = _read_state(run_path)
    if state is None:
        return None
    blocked = state.get("blocked")
    blocked = blocked if isinstance(blocked, dict) else {}
    park_key = f"{blocked.get('phase') or ''}|{blocked.get('at') or ''}"
    prior = state.get(PARK_NOTIFY_KEY)
    if isinstance(prior, dict) and prior.get("park") == park_key:
        return None

    park = classify_park(state, decision.failure_class)
    record: Dict[str, Any] = {
        "park": park_key,
        "park_class": park["park_class"],
        "at": utcnow(),
        "needed": park["needed"],
        "by": "presentation_job.auto_resume",
    }

    try:
        try:
            from .report import dispatch as _dispatch
        except ImportError:
            from report import dispatch as _dispatch  # type: ignore[no-redef]
    except Exception:  # noqa: BLE001 -- no transport import, record says so
        _dispatch = None

    sent = False
    if park["park_class"] == PARK_CLASS_CLIENT_ACTION:
        record["to"] = "client"
        chat_id = _requester_chat_id(run_path, state)
        if chat_id is None:
            record["delivered"] = False
            record["outcome"] = ("no requester chat id recorded for this "
                                 "run; the need is recorded here and in "
                                 "park_status for any surface that reads "
                                 "the run")
        else:
            message = (
                f"Your presentation is paused. {park['needed']} "
                "Everything you already sent us is saved, and the work "
                "done so far is kept.")
            if _dispatch is not None:
                try:
                    sent = bool(_dispatch(chat_id, "blocked", message))
                except Exception:  # noqa: BLE001 -- never break a tick
                    sent = False
            record["delivered"] = sent
            record["outcome"] = ("delivered" if sent else
                                 "transport did not confirm delivery")
    else:
        record["to"] = "operator"
        entry = _scripts_dir() / "presentation_job.py"
        message = (
            f"Presentation run {run_path.name} is parked at "
            f"{decision.phase or 'an unrecorded phase'} and will NOT "
            f"auto-resume (park class: {park['park_class']}). Action "
            f"needed: {park['needed']} Inspect with: {entry} --status "
            f"--run-dir {run_path}")
        if _dispatch is not None:
            try:
                sent = bool(_dispatch(ALERT_CHAT_LABEL, "blocked", message))
            except Exception:  # noqa: BLE001 -- never break a tick
                sent = False
        record["delivered"] = sent
        record["outcome"] = ("delivered" if sent else
                             "transport did not confirm delivery")

    stamped = _merge(run_path,
                     lambda st: st.__setitem__(PARK_NOTIFY_KEY, record))
    if not stamped:
        # The record is what makes this ONE notification instead of one
        # every five minutes. Losing it is loud for the same reason the
        # cap-alert stamp loss is loud (see notify_cap_exhausted).
        print(f"auto-resume: WARNING -- the park notification for "
              f"{run_path.name} was attempted but its once-only record "
              "could not be written to state.json; until it can be, the "
              "notification may repeat on a later tick.", file=sys.stderr)
    if not record["delivered"]:
        print(f"auto-resume: the park notification for {run_path.name} "
              f"(park class {park['park_class']}) was NOT confirmed "
              f"delivered: {record['outcome']}. The need is recorded in "
              "state.json under park_status and park_notification.",
              file=sys.stderr)
    return sent


# ---------------------------------------------------------------------------
# CLI -- what presentation-intake-poll.sh calls in place of its old
# `TERMINAL = BLOCKED -> continue`.
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presentation_job.auto_resume",
        description=("Decide whether a BLOCKED presentation run may be "
                     "resumed automatically (or, with --crash, whether an "
                     "engine-dead, nonterminal run may be resumed under the "
                     "separate crash cap). Exit 0 = resume (an attempt has "
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
    p.add_argument("--crash", action="store_true",
                   help=("decide a CRASH resume instead of a BLOCKED one: the "
                         "engine is dead and the run is nonterminal. Since "
                         "FIX-PLAN Item 10 the crash path spends from the "
                         "ONE unified attempt ledger "
                         '(state["auto_resume"], crash rows carry '
                         'kind="crash") under the ONE cap (AUTO_RESUME_CAP) '
                         "the BLOCKED path uses. With --refund, gives "
                         "back the last crash attempt instead of the last "
                         "BLOCKED attempt."))
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run_path = Path(args.run_dir).expanduser()

    if args.refund:
        # A bookkeeping correction, not a decision. Exit 0 unconditionally:
        # the caller is already inside its dispatch-failure path, and a
        # non-zero here would only add a second failure to that log.
        # The refund stays kind-scoped on the one ledger (Item 10): the
        # --crash refund gives back a crash row, the plain refund a park
        # row, and neither can forgive the other kind's charge.
        if args.crash:
            refund_last_crash_attempt(run_path, args.refund)
        else:
            refund_last_attempt(run_path, args.refund)
        return EXIT_RESUME

    # Refund first, so the cap that is about to be counted is the honest one.
    # Only ever runs when a mismatch is provable RIGHT NOW, and only marks
    # rows whose recorded pin IS the still-stale one.
    # Fix 35: the crash path gets the same manifest-pin refund as the BLOCKED
    # path -- a crash attempt spent under a still-stale pin bought a one-second
    # EXIT_MANIFEST_MISMATCH death, not an engine start, so it must not count
    # against the crash cap either.
    # Item 10: the pin refund sweeps BOTH keys on either path -- rows of
    # both kinds live on the one ledger now, and legacy crash rows can
    # carry a stale pin too.
    ledger_keys = (STATE_KEY, CRASH_STATE_KEY)
    if not args.check:
        state, _why = _read_state(run_path)
        if state is not None and (str(state.get("terminal") or "") == "BLOCKED"
                                  or args.crash):
            status, mwhy = _manifest_status(state, run_path)
            repin, _rwhy = _auto_repin_available()
            if status == "mismatch" and repin is not True:
                now = datetime.now(timezone.utc)
                probe = json.loads(json.dumps(state))  # cheap deep copy
                if any(_refund_manifest_pin_attempts(probe, now, key)
                       for key in ledger_keys):
                    def _refund(live: Dict[str, Any]) -> None:
                        for key in ledger_keys:
                            _refund_manifest_pin_attempts(live, now, key)
                    if _merge(run_path, _refund):
                        print("auto-resume: refunded the attempt(s) spent "
                              f"under the still-stale pin ({mwhy}) -- they "
                              "started no engine, so they do not count "
                              "against the cap", flush=True)

    decision = evaluate_crash(run_path) if args.crash else evaluate(run_path)
    verdict = "RESUME" if decision.resume else "SKIP"
    print(f"auto-resume [{decision.code}] {verdict} {run_path}: "
          f"{decision.why}", flush=True)

    if not decision.resume:
        if decision.code == DECISION_CAP and not args.check:
            notify_cap_exhausted(run_path, decision)
        elif (not args.check and not args.crash
                and decision.park_class in (PARK_CLASS_CLIENT_ACTION,
                                            PARK_CLASS_OPERATOR_ACTION)
                and decision.code != DECISION_KNOWN_PLAN):
            # Item 10: a park that waits on a person notifies that person
            # ONCE per park, with what is needed, and records it. The
            # known-plan decline is the one exclusion: the client already
            # answered, and notifying them that an answer is needed
            # would be the re-ask PRES-019 QC4 forbids.
            notify_park_wait(run_path, decision)
        return decision.exit_code

    if args.check:
        print("auto-resume: --check, so nothing was recorded and no attempt "
              "was spent", flush=True)
        return EXIT_RESUME

    record = record_crash_attempt if args.crash else record_attempt
    if not record(run_path, decision):
        # FAIL-CLOSED. See record_attempt's docstring: a resume the ledger did
        # not record is a resume no bound can ever stop. The crash path
        # (record_crash_attempt) carries the same contract -- an uncounted
        # crash resume is the exact runaway Fix 35 exists to close.
        return EXIT_UNDETERMINED
    return EXIT_RESUME


if __name__ == "__main__":  # pragma: no cover -- CLI entry
    sys.exit(main())
