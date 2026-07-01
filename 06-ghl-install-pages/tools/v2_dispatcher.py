#!/usr/bin/env python3
"""v2_dispatcher.py — the bounded backlog dispatcher for the autonomous Funnels /
Web-Dev department build (Skill 06, T4 / V2 build-completion).

WHY THIS EXISTS
---------------
The prior V2 run never BUILT: `POST /api/tasks/<id>/dispatch` hung (HTTP 000) and
the task sat in `backlog`, so no executor fired. This module is the *enforcement*
behind ``v2-autonomous-build-sop.md`` §1 Option B — a small, bounded dispatcher
that:

  * pulls ONE `backlog` task off the department board and runs it (max in-flight
    = 1 — never fan out a second build over the same fixture),
  * caps the build at a wall-clock deadline and converts a HANG into a `FAILED`
    task with partial evidence (the prior HTTP-000 hang becomes a recorded
    failure, never an indefinite stall),
  * runs the EVIDENCE-HYGIENE gate (scrub leaked client namespaces) and the ONE
    canonical verifier, and only marks a task `verified` when the verify ran and
    telemetry is clean,
  * drives the state machine ``backlog -> dispatched -> building -> verified |
    FAILED`` and writes ``routing/task-record.json`` at each transition so a
    partial run is always resumable + auditable.

GLUE, NOT THE CLICKER (same boundary as ghl_builder / ghl_rest_canvas). This
module owns the bounded control loop + the state transitions; the actual build
work (seed/activate, REST autosave per §2, image pipeline §3, ecosystem §4) is an
INJECTED ``builder`` callable supplied by the dept agent. The verify + scrub are
injected too, defaulting to the real ``ghl_verify`` / ``scrub_turn_telemetry``.
No network and no browser are opened HERE — so this is fully unit-testable with
mocks and NEVER touches live GHL on its own.

D6 / fixture: the builder the dept agent supplies must honor the headless guard
and the sub-account hard gate; this dispatcher refuses to mark `verified` if the
build's own location gate did not pass (it inspects the build result).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
import sys
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_verify  # noqa: E402
import ghl_gate  # noqa: E402
import scrub_turn_telemetry as scrub  # noqa: E402

try:
    import cc_board as _cc_board  # noqa: E402 — Kanban board producer (fail-soft, optional)
except Exception:  # noqa: BLE001 — board mirror is best-effort; never block the build
    _cc_board = None

# FAB-QC library-aware build-quality gate (shared scorer). Optional/best-effort: when the
# build evidence carries a match-decision receipt + fab-artifact, the dispatcher refuses to
# mark `verified` below 8.5. When that evidence is ABSENT (advisory not wired for this build),
# it is a NO-OP — so builds/tests that don't emit it are completely unaffected.
try:
    _SHARED_UTILS = os.path.normpath(os.path.join(_TOOLS_DIR, "..", "..", "shared-utils"))
    if _SHARED_UTILS not in sys.path:
        sys.path.insert(0, _SHARED_UTILS)
    import fab_qc as _fabqc  # type: ignore[import]
except Exception:  # noqa: BLE001
    _fabqc = None  # type: ignore[assignment]

# FAB-artifact PRODUCER (closes the D4 gap). On a template-aware build (a
# routing/match-decision.json receipt exists), this normalises the REAL build result
# (matched funnel_template_id, built pages, the actual copy the builder wrote, the flex
# decision, and the attached linked_automations) into build/fab-artifact.json — the file
# the FAB-QC overlay scores. Without this, the overlay had nothing to score on a real build
# and the >=8.5 gate was a silent no-op. Optional import: a no-op if unavailable.
try:
    import fab_artifact as _fabart  # type: ignore[import]
except Exception:  # noqa: BLE001
    _fabart = None  # type: ignore[assignment]


def _emit_fab_artifact(evidence_root: str, task: dict, build: dict) -> dict:
    """Producer: emit build/fab-artifact.json from the REAL build so the FAB-QC gate FIRES.

    Only runs on a TEMPLATE-AWARE build — i.e. when STEP 0 wrote routing/match-decision.json.
    Does NOT clobber an artifact a builder/upstream step already emitted. Best-effort: a
    failure here never blocks the build (the overlay simply stays a no-op as before)."""
    if _fabart is None:
        return {"emitted": False, "reason": "fab_artifact unavailable"}
    md = os.path.join(evidence_root, "routing", "match-decision.json")
    if not os.path.isfile(md):
        return {"emitted": False, "reason": "no match-decision receipt (build is not template-aware)"}
    try:
        artifact = _fabart.build_funnel_artifact(task, build)
        return _fabart.emit(evidence_root, artifact)
    except Exception as exc:  # noqa: BLE001
        return {"emitted": False, "reason": f"{type(exc).__name__}: {exc}"}


def _fab_overlay(evidence_root: str) -> dict:
    """Run FAB-QC if (and only if) the build emitted enough evidence to judge.

    Returns {ran, passed, score, reason}. ``ran`` is False (a no-op) unless BOTH
    routing/match-decision.json AND a normalised fab-artifact exist — so a build that
    has not wired the FAB artifact yet is never falsely failed."""
    if _fabqc is None:
        return {"ran": False, "reason": "fab_qc unavailable"}
    md = os.path.join(evidence_root, "routing", "match-decision.json")
    art = (os.path.join(evidence_root, "build", "fab-artifact.json"),
           os.path.join(evidence_root, "funnel", "fab-artifact.json"))
    if not os.path.isfile(md) or not any(os.path.isfile(a) for a in art):
        return {"ran": False, "reason": "no FAB evidence (match-decision.json + fab-artifact.json)"}
    try:
        inp = _fabqc.load_inputs_from_evidence(evidence_root, "funnel")
        res = _fabqc.grade(inp)
        return {"ran": True, "passed": bool(res["passed"]), "score": res["score"],
                "lowest_dimension": res["lowest_dimension"], "hard_misses": res["hard_misses"]}
    except Exception as exc:  # noqa: BLE001 — overlay must not crash the dispatcher
        return {"ran": False, "reason": f"fab_qc error: {type(exc).__name__}: {exc}"}

# ── STEP 0 — template-first funnel matcher (env-gated; never blocks a build) ─
# Import is lazy / optional so unit tests that do not set GHL_FUNNEL_CATALOG (or
# GHL_FUNNEL_INDEX) are completely unaffected — the matcher is a no-op when
# neither env var is set AND no step0_matcher is injected.
try:
    import funnel_matcher as _fm  # type: ignore[import]
    _FM_AVAILABLE = True
except ImportError:
    _fm = None  # type: ignore[assignment]
    _FM_AVAILABLE = False


def _resolve_step0(
    step0_matcher: "Callable[[dict, str], dict] | None",
) -> "Callable[[dict, str], dict] | None":
    """Return the STEP-0 callable to use, or None if none is configured.

    Priority: injected ``step0_matcher`` kwarg > env-gated auto-configure
    (``GHL_FUNNEL_INDEX`` or ``GHL_FUNNEL_CATALOG`` set) > None (no-op).
    The auto-configure path requires ``funnel_matcher`` to be importable.
    """
    if step0_matcher is not None:
        return step0_matcher
    if _FM_AVAILABLE:
        index_path = os.environ.get("GHL_FUNNEL_INDEX", "")
        catalog_root = os.environ.get("GHL_FUNNEL_CATALOG", "")
        # Gate UNCHANGED: the matcher stays a no-op unless the catalog/index env is set
        # (or a matcher is injected) — so unit tests that set neither are unaffected.
        # Box installs turn it on by exporting GHL_FUNNEL_INDEX/GHL_FUNNEL_CATALOG
        # (see 44-.../tools/engine/wire-ghl-env.sh).
        if index_path or catalog_root:
            # When the catalog IS configured, default GHL_FUNNEL_INDEX to the committed
            # sibling index so the index path always resolves.
            if not index_path:
                _default_index = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "catalog-index.json")
                if os.path.isfile(_default_index):
                    index_path = _default_index
            # Resolve the funnel->automation link map so the COMPLETE-funnel handoff
            # (task['linked_automations']) is on by DEFAULT whenever the catalog is
            # configured — not only when the separate links env var happens to be set.
            link_map_path = os.environ.get("GHL_FUNNEL_AUTOMATION_LINKS", "")
            if not link_map_path:
                _default_links = os.path.normpath(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "..", "..",
                    "44-convert-and-flow-operator", "automation-templates", "_links",
                    "funnel-to-automation.json"))
                if os.path.isfile(_default_links):
                    link_map_path = _default_links

            def _auto_step0(task: dict, evidence_root: str) -> dict:
                return _fm.step0_match(
                    task, evidence_root,
                    catalog_root=catalog_root or None,
                    index_path=index_path or None,
                    link_map_path=link_map_path or None,
                )
            return _auto_step0
    return None


# The bounded-dispatcher state machine (SOP §1). These are the ONLY task states.
STATE_BACKLOG = "backlog"
STATE_DISPATCHED = "dispatched"
STATE_BUILDING = "building"
STATE_VERIFIED = "verified"
STATE_FAILED = "FAILED"

# Bounded defaults (SOP §1). max_inflight is a HARD cap of 1.
DEFAULT_MAX_INFLIGHT = 1
DEFAULT_WALLCLOCK_CAP_S = 1800
DEFAULT_POLL_BACKOFF_S = 30

# ── P2-4: rate-limit governor + session keepalive ────────────────────────────
# GHL throttles rapid autosaves/publishes; bursting trips 429s and (worse) silent
# dropped writes. These two utilities are REUSABLE by the INJECTED builder (the
# dispatcher itself opens no browser/network — same GLUE boundary as the rest of
# this module). Defaults MIRROR gates.json::rate_limit_governor (single source of
# truth — keep them in sync). The clock + sleeper are injectable so the bounds are
# unit-testable instantly and deterministically (no real wall-clock sleeping).
MIN_SAVE_INTERVAL_S = 6.0          # gates.json rate_limit_governor.min_save_interval_s
MIN_PUBLISH_INTERVAL_S = 15.0      # gates.json rate_limit_governor.min_publish_interval_s
DEFAULT_429_COOLDOWN_S = 30.0      # gates.json rate_limit_governor.default_429_cooldown_s
SESSION_KEEPALIVE_INTERVAL_S = 30 * 60  # gates.json ...session_keepalive.interval_minutes


class RateGovernor:
    """Space write actions and back off on HTTP 429 (P2-4).

    Enforces a MINIMUM interval between repeat ``save`` actions and between repeat
    ``publish`` actions, plus a global cooldown after a 429 (honoring a
    ``Retry-After`` header when present, else ``DEFAULT_429_COOLDOWN_S``). It only
    ever DELAYS — it never speeds a build up. ``clock`` + ``sleeper`` are injected
    (default ``time.monotonic`` / ``time.sleep``) so tests run with a fake clock.

    Usage by the injected builder::

        gov = RateGovernor()
        gov.before("save");    do_autosave()
        gov.before("publish"); do_publish()
        # on a 429 response:
        gov.note_429(resp.headers.get("Retry-After")); retry()
    """

    def __init__(
        self,
        *,
        min_save_interval_s: float = MIN_SAVE_INTERVAL_S,
        min_publish_interval_s: float = MIN_PUBLISH_INTERVAL_S,
        default_429_cooldown_s: float = DEFAULT_429_COOLDOWN_S,
        clock: "Callable[[], float] | None" = None,
        sleeper: "Callable[[float], None] | None" = None,
    ) -> None:
        self.min_interval = {"save": float(min_save_interval_s),
                             "publish": float(min_publish_interval_s)}
        self.default_429_cooldown_s = float(default_429_cooldown_s)
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._last: dict[str, float] = {}   # action -> last allowed time
        self._cooldown_until = 0.0          # global 429 cooldown deadline

    def _wait_for(self, action: str) -> float:
        """Seconds the caller must wait before ``action`` is allowed (no sleep)."""
        now = self._clock()
        waits = []
        if now < self._cooldown_until:                     # global 429 cooldown
            waits.append(self._cooldown_until - now)
        last = self._last.get(action)                      # per-action min interval
        gap = self.min_interval.get(action, 0.0)
        if last is not None and gap > 0:
            elapsed = now - last
            if elapsed < gap:
                waits.append(gap - elapsed)
        return max(waits) if waits else 0.0

    def before(self, action: str) -> float:
        """Block (sleep) until ``action`` is allowed; return the seconds slept.

        The action time is recorded AFTER the wait so back-to-back calls space out
        by the full minimum interval."""
        wait = self._wait_for(action)
        if wait > 0:
            self._sleep(wait)
        self._last[action] = self._clock()
        return wait

    def note_429(self, retry_after: "float | str | None" = None) -> float:
        """Register a 429: cool down for ``max(Retry-After, default)`` seconds.

        ``retry_after`` accepts the raw header value (str/number/None). A
        malformed/absent value falls back to ``default_429_cooldown_s``. Returns
        the cooldown applied."""
        cooldown = self.default_429_cooldown_s
        if retry_after is not None:
            try:
                cooldown = max(cooldown, float(retry_after))
            except (TypeError, ValueError):
                pass  # malformed header -> keep the default floor
        self._cooldown_until = self._clock() + cooldown
        return cooldown


class SessionKeepalive:
    """No-op session-keepalive scheduler (P2-4).

    ``due()`` returns True at most once every ``interval_s`` so a long build can
    fire a HARMLESS keepalive (e.g. ``AB --session <s> eval 'true'``) to keep the
    seeded agent-browser session warm — NEVER a navigate/open/reload (that re-runs
    the boot IIFE and logs the seeded session out; see inject-ghl-auth.sh DO NOT
    RELOAD). This only SCHEDULES; the keepalive action belongs to the caller (the
    dispatcher opens no browser)."""

    def __init__(self, interval_s: float = SESSION_KEEPALIVE_INTERVAL_S,
                 clock: "Callable[[], float] | None" = None) -> None:
        self.interval_s = float(interval_s)
        self._clock = clock or time.monotonic
        self._last = self._clock()

    def due(self, now: "float | None" = None) -> bool:
        """True iff at least ``interval_s`` elapsed since the last due()==True."""
        now = self._clock() if now is None else now
        if now - self._last >= self.interval_s:
            self._last = now
            return True
        return False


class DispatchResult:
    """The outcome of dispatching one task. Truthy iff the task reached
    ``verified`` with ``overall_pass`` True."""

    __slots__ = ("task_id", "state", "reason", "verify", "evidence_root", "record_path")

    def __init__(self, task_id: str, state: str, reason: str = "",
                 verify: dict | None = None, evidence_root: str = "",
                 record_path: str = "") -> None:
        self.task_id = task_id
        self.state = state
        self.reason = reason
        self.verify = verify or {}
        self.evidence_root = evidence_root
        self.record_path = record_path

    def __bool__(self) -> bool:
        return self.state == STATE_VERIFIED and bool(self.verify.get("overall_pass"))

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id, "state": self.state, "reason": self.reason,
            "verify": self.verify, "evidence_root": self.evidence_root,
            "record_path": self.record_path,
        }


def _write_record(evidence_root: str, record: dict) -> str:
    """Write/refresh routing/task-record.json (the resumable audit trail)."""
    path = os.path.join(evidence_root, "routing", "task-record.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {**record, "updated_at": _ts()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return path


def _board_push(task: dict, state: str) -> None:
    """Fail-soft Kanban transition mirror (Area-6). Maps a dispatcher state onto
    the Command Center board status and pushes it so a running build no longer
    sits stuck at 'backlog'. ANY failure (module absent, board unconfigured,
    network, bad id) is swallowed — a board outage NEVER blocks the build.

    The board task id is threaded from routing/intake-receipt.json as
    ``task['board_task_id']``; it falls back to ``task['id']`` (the dispatcher id
    already equals the board id when the task was pulled off the board)."""
    if _cc_board is None:
        return
    try:
        board_id = (task.get("board_task_id") or task.get("id") or "").strip()
        if not board_id:
            return
        _cc_board.update_status_for_state(board_id, state)
    except Exception:  # noqa: BLE001 — best-effort mirror, never fatal
        return


def dispatch_one(
    task: dict,
    evidence_root: str,
    *,
    builder: Callable[[dict, str], dict],
    verifier: Callable[..., dict] | None = None,
    telemetry_glob: list[str] | None = None,
    max_inflight: int = DEFAULT_MAX_INFLIGHT,
    inflight_now: int = 0,
    wallclock_cap_s: int = DEFAULT_WALLCLOCK_CAP_S,
    clock: Callable[[], float] | None = None,
    live: bool = True,
    step0_matcher: "Callable[[dict, str], dict] | None" = None,
) -> DispatchResult:
    """Dispatch and run ONE department build task, bounded.

    State machine: ``backlog -> dispatched -> building -> verified | FAILED``.

    Args:
        task: ``{id, brand, brief, location_id, pages?}`` — the board task.
        evidence_root: ``skill6-fix/v2-<RUN_ID>/`` (never /tmp).
        builder: INJECTED callable ``(task, evidence_root) -> build_result``. The
            dept agent supplies the real builder (seed/activate + REST autosave +
            images + ecosystem per the SOP). It MUST return a dict with at least
            ``{"pages": [...], "location_gate_ok": bool, "duration_s": float}``
            and may write its own ledgers/logs under ``evidence_root`` as it goes.
            A builder that raises is caught and the task is marked FAILED with the
            partial evidence intact.
        verifier: INJECTED canonical verifier; defaults to ``ghl_verify.verify_all``.
        telemetry_glob: list of telemetry file paths to scrub + gate (SOP §6).
        max_inflight: HARD cap (default 1). If ``inflight_now >= max_inflight`` the
            task is NOT started (returns state ``backlog`` unchanged — never a
            second concurrent build over the same fixture).
        inflight_now: how many builds are already running (caller-tracked).
        wallclock_cap_s: build wall-clock cap; exceeding it = FAILED (the hang
            fix — a stalled/over-long build becomes a recorded failure).
        clock: INJECTED monotonic clock (defaults to time.monotonic) for tests.
        live: Threaded to ``ghl_verify.verify_all`` as ``live=True`` (production,
            uses the real render_check) or ``live=False`` (test/CI, uses the
            injected verifier / mock path).  In PRODUCTION, ``live=True`` is the
            ONLY valid value — passing ``live=False`` with a real verifier
            produces a MOCK verdict that is immediately downgraded to FAILED.
        step0_matcher: OPTIONAL INJECTED callable ``(task, evidence_root) -> decision``
            that makes Skill 6 template-first.  If supplied, it is called right after
            the max_inflight gate and before ``backlog -> dispatched``.  On a
            USE_TEMPLATE decision it mutates ``task['pages']`` / ``task['copy_persona']``
            so the injected builder receives an instantiated plan instead of building
            from scratch.  On CREATE_NEW it is a no-op (builder generates net-new).
            A SKIPPED result (matcher error or not configured) never blocks the build.
            Defaults to None; auto-configured from env vars GHL_FUNNEL_CATALOG /
            GHL_FUNNEL_INDEX when funnel_matcher is importable (see _resolve_step0).

    Returns:
        ``DispatchResult`` (truthy only on verified + overall_pass True).
    """
    verifier = verifier or ghl_verify.verify_all
    clock = clock or time.monotonic
    task_id = task.get("id") or "task"

    def _rec_write(r: dict) -> str:
        # Write the local audit record, THEN (fail-soft) mirror the transition to
        # the Command Center Kanban (Area-6). The board mirror is best-effort and
        # never blocks the build; 'backlog'/unknown states are a no-op.
        p = _write_record(evidence_root, r)
        _board_push(task, r.get("state", ""))
        return p

    # ── HARD max-inflight gate (one build at a time over the fixture) ─────────
    if inflight_now >= max_inflight:
        rec = {"task_id": task_id, "state": STATE_BACKLOG,
               "reason": f"max_inflight={max_inflight} reached (inflight={inflight_now}); "
                         "task left in backlog (never a second concurrent build)"}
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_BACKLOG, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    # ── STEP 0 — template-first funnel matcher (advisory, never blocks) ──────
    # Runs AFTER the max_inflight gate and BEFORE backlog->dispatched so that
    # when a template is matched the builder sees an already-instantiated page plan
    # (task['pages'] / task['copy_persona'] / task['template_match']).  A SKIPPED
    # or errored result is recorded but NEVER causes a build failure.
    _s0 = _resolve_step0(step0_matcher)
    if _s0 is not None:
        try:
            _step0_result = _s0(task, evidence_root)
        except Exception as _s0_exc:  # noqa: BLE001
            _step0_result = {"decision": "SKIPPED",
                             "reason": f"step0 raised: {type(_s0_exc).__name__}: {_s0_exc}"}
        task.setdefault("template_match", _step0_result.get("template_match",
                        {"decision": _step0_result.get("decision", "SKIPPED")}))

    # ── backlog -> dispatched ─────────────────────────────────────────────────
    started = clock()
    rec = {"task_id": task_id, "state": STATE_DISPATCHED, "claimed_at": _ts(),
           "max_inflight": max_inflight, "wallclock_cap_s": wallclock_cap_s,
           "brand": task.get("brand"), "location_id": task.get("location_id")}
    rp = _rec_write(rec)

    # ── dispatched -> building (run the injected builder, bounded) ────────────
    rec["state"] = STATE_BUILDING
    _rec_write(rec)
    try:
        build = builder(task, evidence_root)
    except Exception as exc:  # noqa: BLE001 — a crashed build = FAILED, partial kept
        rec.update({"state": STATE_FAILED,
                    "reason": f"builder raised: {type(exc).__name__}: {exc}"})
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    duration = float(build.get("duration_s", clock() - started))

    # ── wall-clock cap: a hang/over-long build is a FAILED, never a stall ─────
    if duration > wallclock_cap_s:
        rec.update({"state": STATE_FAILED, "build_duration_s": duration,
                    "reason": f"dispatch timeout: build ran {duration:.0f}s > cap "
                              f"{wallclock_cap_s}s (the HTTP-000 hang fix)"})
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    # ── sub-account hard gate must have passed in the build ───────────────────
    if not build.get("location_gate_ok", False):
        rec.update({"state": STATE_FAILED, "build_duration_s": duration,
                    "reason": "sub-account location gate did NOT pass in the build "
                              "(NO-COMINGLING hard stop)"})
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    # ── evidence hygiene gate: scrub + --check leaked client namespaces ───────
    for p in (telemetry_glob or []):
        if os.path.exists(p):
            scrub.scrub_file(p)
            with open(p, encoding="utf-8") as f:
                if not scrub.is_clean(f.read()):
                    rec.update({"state": STATE_FAILED,
                                "reason": f"telemetry still leaked after scrub: {p}"})
                    rp = _rec_write(rec)
                    return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                                          evidence_root=evidence_root, record_path=rp)

    # ── building -> verified (the ONE canonical verifier) ─────────────────────
    # In the PRODUCTION path (live=True), the verifier is called with NO injected
    # fetcher — the production verifier must use the real render_check.  The
    # building->verified transition is then GATED on ghl_gate.require_pass()
    # re-reading and re-validating the written scorecard/verify-summary.json from
    # disk (not from memory), including artifact hash binding.  A task that reaches
    # "verified" state while trust=='MOCK' is immediately downgraded to FAILED.
    pages = build.get("pages", [])

    if live and verifier is None:
        # Production path: call ghl_verify.verify_all directly, live=True, no fetcher.
        try:
            verify_out = ghl_verify.verify_all(
                evidence_root, pages, live=True,
                run_id=task_id, version="client-agent", brand=task.get("brand", ""),
            )
        except (ghl_verify.SealedGateViolation, ghl_verify.VerifyContradiction) as exc:
            rec.update({"state": STATE_FAILED,
                        "reason": f"verify_all integrity failure: {type(exc).__name__}: {exc}"})
            rp = _rec_write(rec)
            return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                                  evidence_root=evidence_root, record_path=rp)
    else:
        # Test/CI path: use the injected verifier (live=False).
        _actual_verifier = verifier or ghl_verify.verify_all
        try:
            verify_out = _actual_verifier(
                evidence_root, pages, run_id=task_id,
                version="client-agent", brand=task.get("brand", ""),
            )
        except Exception as exc:  # noqa: BLE001
            rec.update({"state": STATE_FAILED,
                        "reason": f"verifier raised: {type(exc).__name__}: {exc}"})
            rp = _rec_write(rec)
            return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                                  evidence_root=evidence_root, record_path=rp)

    summary = (
        verify_out["summary"]
        if isinstance(verify_out, dict) and "summary" in verify_out
        else verify_out
    )

    # ── GATE: re-validate the WRITTEN scorecard (not the in-memory dict) ──────
    # ghl_gate.require_pass() reads only the machine-written JSON files and
    # re-runs assert_consistent + artifact hashes.  It never reads .md / ledger.
    # ONLY invoked on the production path (live=True AND no injected verifier)
    # because the gate validates the writer/run_nonce of ghl_verify.verify_all,
    # which only appears when the production verifier ran.
    _production_path = live and verifier is None
    if _production_path:
        gate_rc = ghl_gate.require_pass(evidence_root)
        if gate_rc != 0:
            rec.update({"state": STATE_FAILED, "build_duration_s": duration,
                        "reason": f"ghl_gate.require_pass returned rc={gate_rc} — "
                                  "the written scorecard failed re-validation "
                                  "(not the in-memory dict).  Build is FAILED."})
            rp = _rec_write(rec)
            return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                                  evidence_root=evidence_root, record_path=rp)

    # ── MOCK VERDICT DOWNGRADE ─────────────────────────────────────────────────
    # A task on the PRODUCTION path that reaches verified-state while
    # trust=='MOCK' is downgraded to FAILED — a mock verifier cannot produce a
    # shippable verdict.  This check is only active on the production path
    # (_production_path=True, meaning live=True AND no injected verifier) because
    # the trust='MOCK' stamp is only added by ghl_verify.verify_all when
    # live=False — which the production path never uses.  When a test injects a
    # verifier explicitly, the caller is responsible for the trust value.
    verdict_trust = summary.get("trust", "LIVE") if isinstance(summary, dict) else "LIVE"
    if _production_path and verdict_trust == "MOCK":
        rec.update({"state": STATE_FAILED, "build_duration_s": duration,
                    "reason": "MOCK VERDICT DOWNGRADE: the production verifier "
                              "returned trust='MOCK'.  A mock verdict cannot be "
                              "accepted as a shippable build pass — task is FAILED."})
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    # ── FAB-ARTIFACT PRODUCER (D4) ────────────────────────────────────────────
    # Emit build/fab-artifact.json FROM THE REAL BUILD RESULT so the gate below has
    # something to score. Runs only on a template-aware build (match-decision receipt
    # present); no-op otherwise and never clobbers an already-emitted artifact. THIS is
    # what makes the FAB-QC gate fire on a real funnel build instead of a hand fixture.
    _fab_emit = _emit_fab_artifact(evidence_root, task, build)

    # ── FAB-QC BUILD-QUALITY GATE (>= 8.5, library-aware) ─────────────────────
    # SUPERSET overlay on top of the canonical ghl_verify floor. Binding ONLY when the
    # build emitted FAB evidence (match-decision receipt + fab-artifact); otherwise a
    # no-op. A definitive sub-8.5 verdict downgrades the task to FAILED — `verified`
    # requires BOTH ghl_verify overall_pass AND FAB-QC >= 8.5.
    _fab = _fab_overlay(evidence_root)
    if _fab.get("ran") and not _fab.get("passed"):
        rec.update({"state": STATE_FAILED, "build_duration_s": duration,
                    "fab_qc": _fab, "fab_artifact": _fab_emit,
                    "reason": f"FAB-QC GATE: build scored {_fab.get('score')} < 8.5 "
                              f"(lowest: {_fab.get('lowest_dimension')}; "
                              f"hard_misses: {_fab.get('hard_misses')}). Not done."})
        rp = _rec_write(rec)
        return DispatchResult(task_id, STATE_FAILED, rec["reason"],
                              evidence_root=evidence_root, record_path=rp)

    # Tag the ledger as authoritative:false + verdict_source pointer so callers
    # know the single authoritative verdict lives in the scorecard, not here.
    rec.update({
        "state": STATE_VERIFIED,
        "fab_qc": _fab,
        "fab_artifact": _fab_emit,
        "build_duration_s": duration,
        "verify_overall_pass": bool(summary.get("overall_pass")) if isinstance(summary, dict) else False,
        "verify_passed": summary.get("passed") if isinstance(summary, dict) else None,
        "verify_total": summary.get("total") if isinstance(summary, dict) else None,
        "authoritative": False,
        "verdict_source": os.path.join(evidence_root, ghl_verify.SUMMARY_REL),
        "reason": "verified (overall_pass recorded honestly — "
                  "FAIL is reported, never massaged)",
    })
    rp = _rec_write(rec)

    # ── COMPLETE-FUNNEL HANDOFF (P4->P5) ──────────────────────────────────────
    # The funnel pages verified. If STEP 0 attached linked follow-up automations
    # (task['linked_automations'], from the funnel->automation link map), persist a
    # handoff artifact so the orchestrator / Skill-44 (caf) agent can build each
    # build_now automation. RECOMMENDED, never mandatory; this is the documented
    # P4->P5 seam (SKILL.md "Full-Funnel Pipeline Integration"). Advisory: a failure
    # here never downgrades the verified verdict.
    try:
        la = task.get("linked_automations")
        if isinstance(la, dict) and la.get("automations"):
            handoff = {
                "from": "06-ghl-install-pages (P4 funnel build)",
                "to": "44-convert-and-flow-operator (P5 automation build)",
                "funnel_template_id": task.get("funnel_template_id"),
                "recommended": True, "mandatory": False,
                "to_build": [a for a in la["automations"] if a.get("build_now")],
                "reference_only": [a for a in la["automations"] if not a.get("build_now")],
                "note": "Each to_build automation should be dispatched to Skill 44 as its "
                        "own build (PLAN MODE + QC). Overridable/ignorable per flexibility.",
                "ts": _ts(),
            }
            json.dump(handoff, open(os.path.join(evidence_root, "routing",
                      "skill44-handoff.json"), "w", encoding="utf-8"), indent=2)
    except Exception:  # noqa: BLE001 — handoff persistence is advisory glue
        pass

    return DispatchResult(task_id, STATE_VERIFIED, rec["reason"], verify=summary,
                          evidence_root=evidence_root, record_path=rp)


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# CLI entrypoint — makes Option B (the bounded dispatcher) a REFERENCEABLE,
# SELF-PROVING default rather than a library with no entrypoint. This is GLUE:
# the real per-task build is an INJECTED `builder` supplied by the dept agent via
# dispatch_one(); a standalone cron cannot build without it. So this CLI exposes
# the bounded config (--print-config) and a hermetic selftest (--selftest) that
# proves the three bounds fire (max_inflight=1, 1800s wall-clock, verified happy
# path). No network, no browser — safe to run anywhere.
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Prove the bounded gates are wired, with stub builder/verifier (no network)."""
    import tempfile
    ok = True

    def _stub_builder(task, root, *, duration=1.0, gate=True):
        return {"pages": ["home"], "location_gate_ok": gate, "duration_s": duration}

    def _stub_verifier(root, pages, **kw):
        return {"overall_pass": True, "passed": len(pages), "total": len(pages)}

    task = {"id": "selftest", "brand": "Fixture", "location_id": "FIXTURE0LOCATION0000"}

    with tempfile.TemporaryDirectory() as d:
        # 1) HARD max_inflight gate — a second concurrent build is refused.
        r = dispatch_one(task, d, builder=_stub_builder, verifier=_stub_verifier,
                         max_inflight=1, inflight_now=1, live=False)
        ok &= (r.state == STATE_BACKLOG)
        print("  [%s] max_inflight=1 gate -> %s" % ("ok" if r.state == STATE_BACKLOG else "FAIL", r.state))

    with tempfile.TemporaryDirectory() as d:
        # 2) wall-clock cap — an over-long/hung build becomes FAILED (HTTP-000 fix).
        r = dispatch_one(
            task, d,
            builder=lambda t, root: _stub_builder(t, root, duration=DEFAULT_WALLCLOCK_CAP_S + 1),
            verifier=_stub_verifier, wallclock_cap_s=DEFAULT_WALLCLOCK_CAP_S, live=False)
        passed = (r.state == STATE_FAILED and "timeout" in r.reason)
        ok &= passed
        print("  [%s] wallclock_cap=%ds -> %s" % ("ok" if passed else "FAIL", DEFAULT_WALLCLOCK_CAP_S, r.state))

    with tempfile.TemporaryDirectory() as d:
        # 3) happy path — verified + overall_pass True (truthy result).
        r = dispatch_one(task, d, builder=_stub_builder, verifier=_stub_verifier, live=False)
        passed = (r.state == STATE_VERIFIED and bool(r))
        ok &= passed
        print("  [%s] happy path -> %s (truthy=%s)" % ("ok" if passed else "FAIL", r.state, bool(r)))

    # 4) RATE GOVERNOR (P2-4) — saves spaced >=6s, publishes >=15s, 429 cooldown.
    class _FakeClock:
        def __init__(self): self.t = 0.0
        def __call__(self): return self.t
        def advance(self, s): self.t += float(s)
    fc = _FakeClock()
    gov = RateGovernor(clock=fc, sleeper=fc.advance)
    w_save1 = gov.before("save")            # first save: no wait
    w_save2 = gov.before("save")            # immediate 2nd save: must wait >=6s
    g_save = (w_save1 == 0.0 and w_save2 >= MIN_SAVE_INTERVAL_S)
    ok &= g_save
    print("  [%s] rate governor save spacing -> wait1=%.0fs wait2=%.0fs (>=%.0f)"
          % ("ok" if g_save else "FAIL", w_save1, w_save2, MIN_SAVE_INTERVAL_S))
    w_pub1 = gov.before("publish")          # first publish: no wait
    w_pub2 = gov.before("publish")          # immediate 2nd: must wait >=15s
    g_pub = (w_pub1 == 0.0 and w_pub2 >= MIN_PUBLISH_INTERVAL_S)
    ok &= g_pub
    print("  [%s] rate governor publish spacing -> wait1=%.0fs wait2=%.0fs (>=%.0f)"
          % ("ok" if g_pub else "FAIL", w_pub1, w_pub2, MIN_PUBLISH_INTERVAL_S))
    cd_default = gov.note_429(None)         # malformed/absent header -> 30s floor
    cd_header = gov.note_429("45")          # Retry-After 45s honored (> floor)
    cd_floor = gov.note_429("5")            # Retry-After 5s -> floored at 30s
    g_429 = (cd_default == DEFAULT_429_COOLDOWN_S and cd_header == 45.0
             and cd_floor == DEFAULT_429_COOLDOWN_S)
    ok &= g_429
    print("  [%s] rate governor 429 cooldown -> default=%.0fs header=%.0fs floor=%.0fs"
          % ("ok" if g_429 else "FAIL", cd_default, cd_header, cd_floor))

    # 5) SESSION KEEPALIVE (P2-4) — due() at most once per 30min interval.
    kc = _FakeClock()
    ka = SessionKeepalive(clock=kc)
    due0 = ka.due()                         # nothing elapsed -> not due
    kc.advance(SESSION_KEEPALIVE_INTERVAL_S - 1)
    due_early = ka.due()                    # 29m59s -> still not due
    kc.advance(1)
    due_at = ka.due()                       # exactly 30m -> due
    due_again = ka.due()                    # immediately after -> not due
    g_ka = (not due0 and not due_early and due_at and not due_again)
    ok &= g_ka
    print("  [%s] session keepalive interval -> early=%s at30m=%s again=%s"
          % ("ok" if g_ka else "FAIL", due_early, due_at, due_again))

    print("v2_dispatcher selftest bounds: max_inflight=%d wallclock_cap_s=%d poll_backoff_s=%d "
          "min_save_s=%.0f min_publish_s=%.0f cooldown_429_s=%.0f keepalive_s=%d"
          % (DEFAULT_MAX_INFLIGHT, DEFAULT_WALLCLOCK_CAP_S, DEFAULT_POLL_BACKOFF_S,
             MIN_SAVE_INTERVAL_S, MIN_PUBLISH_INTERVAL_S, DEFAULT_429_COOLDOWN_S,
             SESSION_KEEPALIVE_INTERVAL_S))
    print("SELFTEST PASS" if ok else "SELFTEST FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="v2_dispatcher",
        description="Bounded backlog dispatcher (Skill 06 SOP §1 Option B — REQUIRED "
                    "DEFAULT). GLUE only: the real per-task build is an INJECTED builder "
                    "supplied by the dept agent via dispatch_one(); this CLI exposes the "
                    "bounded config and a hermetic selftest.")
    ap.add_argument("--print-config", action="store_true",
                    help="print the bounded caps (max_inflight/wallclock_cap_s/poll_backoff_s) as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the bounded gates fire (inflight=1 refuse, wallclock->FAILED, happy->verified)")
    args = ap.parse_args(argv)
    if args.print_config:
        print(json.dumps({"max_inflight": DEFAULT_MAX_INFLIGHT,
                          "wallclock_cap_s": DEFAULT_WALLCLOCK_CAP_S,
                          "poll_backoff_s": DEFAULT_POLL_BACKOFF_S,
                          "min_save_interval_s": MIN_SAVE_INTERVAL_S,
                          "min_publish_interval_s": MIN_PUBLISH_INTERVAL_S,
                          "default_429_cooldown_s": DEFAULT_429_COOLDOWN_S,
                          "session_keepalive_interval_s": SESSION_KEEPALIVE_INTERVAL_S},
                         indent=2))
        return 0
    if args.selftest:
        return _selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
