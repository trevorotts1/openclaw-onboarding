from __future__ import annotations

# =============================================================================
# board.py — BoardMirror: Kanban board state mirror
# =============================================================================
#
# Purpose:
#   Mirror the job state to the Kanban (Command Center) board. Best-effort,
#   never blocking. If board_config() returns None (both URLs unset), every
#   method is a no-op that records a board.disabled event.
#
# Inputs:
#   - state.json (via store): persisted job state, holds board.task_id
#   - process_manifest.json (via cc_board._read_manifest): holds cc_task_id
#     from a prior successful ingest_deck_task
#   - Environment: BOARD_URL, BOARD_API_TOKEN (via board_config)
#   - run_dir: the job's run directory
#
# Outputs:
#   - state.json updates: board.task_id persistence, board.card_params for
#     re-creation fallback, board.task_id_missing_at timestamp
#   - process_manifest.json: cc_task_id (written by cc_board.stamp_task_id)
#   - CC API calls via cc_board: ingest_deck_task, post_activity, patch_phase
#   - Reporter events: board.recovered_task_id, board.no_task_id,
#     board.recreated_task_id, board.task_id_missing, board.disabled,
#     board.error, board.internal_error
#
# Callers:
#   - Engine.__init__() — instantiates BoardMirror
#   - phases.py phase walker — calls phase_progress/mark_in_progress/
#     mark_review/mark_blocked
#
# Callees:
#   - cc_board.ingest_deck_task() — create a Kanban card
#   - cc_board.post_activity() — post a phase activity comment
#   - cc_board.patch_phase() — advance the stepper label
#   - cc_board._read_manifest() — read process_manifest.json for fallback
#   - cc_board.board_config() — read board URLs/token from env
#   - store.save() — atomically persist state.json
#
# AF codes enforced:
#   - AF-BOARD-DISABLED-02 when board URLs unset
#   - AF-BOARD-NO-TASK-ID-03 when task_id absent with board enabled
# =============================================================================

import os
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

_cc_board = None


def _get_cc_board():
    global _cc_board
    if _cc_board is None:
        import cc_board as _cc_board
    return _cc_board


class BoardMirror:
    """Mirror the job state to the Kanban board. Best-effort, never blocking.

    Wraps cc_board.py with a fail-soft boundary. If board_config() returns None
    (both URLs unset), every method is a no-op that records a board.disabled event.

    Every method wraps calls in two except clauses:
      - (ConnectionError, TimeoutError, OSError, ValueError) -> board.error
      - Exception -> board.internal_error with traceback
    Neither clause raises — the board can NEVER block a build (Invariant 1).

    When the task_id file or state entry is missing (deleted, corrupted, or
    never created), the BoardMirror emits a WARNING-level event and attempts
    to re-create the card from stored parameters, rather than silently no-oping.

    child_report(phase_id, title, description, status, note) is the Option B
    entry point: one child card per phase, created once (idempotent via the
    dual state+manifest phase_id -> child_task_id mapping) and PATCHed to
    'done'/'blocked' as the phase resolves. Same fail-soft contract as every
    method above.
    """

    def __init__(self, run_dir, state, store, reporter):
        self.run_dir = Path(run_dir)
        self.state = state
        self.store = store
        self.report = reporter
        self._config = _get_cc_board().board_config(os.environ)
        # FIX 57: parent_task_id is cached PER RUN ID, never process-wide. The
        # 2026-08-31 incident had 47 of 49 children of a second job nested under
        # the FIRST job's parent because a resolved parent id outlived its run.
        # This map is instance state on a BoardMirror that is created once per
        # Engine (phases.py Engine.__init__), so it dies with the run.
        self._parent_by_run = {}
        self._resolve_task_id()

    # ------------------------------------------------------------------
    # task_id resolution
    # ------------------------------------------------------------------

    def _resolve_task_id(self):
        """Fill state["board"]["task_id"]. Emit diagnostic on total absence.

        Priority order:
          1. state["board"]["task_id"] already set -> no-op (the card exists).
          2. Fallback: read cc_task_id from process_manifest.json (written by
             stamp_task_id inside ingest_deck_task on prior success).
          3. If neither source has a task_id AND the board is enabled, emit a
             WARNING-level board.no_task_id event and record the timestamp.
             If card_params were stored from a prior open_card(), attempt to
             re-create the card now.

        This method MUST run after _config is set (self._config is populated
        in __init__ before this call).
        """
        board_state = self.state.setdefault("board", {})

        # Path 1: already resolved.
        if board_state.get("task_id"):
            return

        # Path 2: recover from persisted manifest.
        cc = _get_cc_board()
        try:
            manifest = cc._read_manifest(self.run_dir)
        except Exception:
            manifest = {}
        cc_task_id = manifest.get("cc_task_id")
        if cc_task_id:
            board_state["task_id"] = cc_task_id
            self.report.event("board.recovered_task_id",
                              f"recovered {cc_task_id} from process_manifest.json")
            return

        # Path 3: both sources empty. Board is either disabled or this is a
        # genuine gap. If the board is enabled, this is a problem -- every
        # downstream call will be a silent no-op unless we act now.
        if self._enabled():
            self.report.event(
                "board.no_task_id",
                "WARNING: board is enabled but no task_id found in state or "
                "process_manifest.json; board operations will be no-ops until "
                "open_card() succeeds"
            )
            board_state["task_id_missing_at"] = _utcnow_iso()

            # Attempt re-creation from stored card parameters.
            card_params = board_state.get("card_params")
            if card_params and isinstance(card_params, dict):
                deck = card_params.get("deck_slug")
                title = card_params.get("title")
                desc = card_params.get("description", "")
                if deck and title:
                    try:
                        task_id = cc.ingest_deck_task(
                            self.run_dir, deck, title, desc,
                            priority="normal", env=os.environ,
                            run_id=self._run_slug())
                        if task_id:
                            board_state["task_id"] = task_id
                            board_state.pop("task_id_missing_at", None)
                            self.store.save(self.state)
                            self.report.event(
                                "board.recreated_task_id",
                                f"re-created card {task_id} from stored params "
                                f"(deck={deck!r}, title={title!r})"
                            )
                    except Exception as exc:
                        self.report.event(
                            "board.recreate_failed",
                            f"failed to re-create card from stored params: {exc}"
                        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _enabled(self):
        return self._config is not None

    def _wrap(self, fn, *args, **kwargs):
        """Call fn; record any failure as an event. Never raise."""
        if not self._enabled():
            self.report.event("board.disabled", "board URLs not configured")
            return None
        try:
            return fn(*args, **kwargs)
        except (ConnectionError, TimeoutError, OSError, ValueError) as exc:
            self.report.event("board.error", f"{fn.__name__}: {exc}")
            return None
        except Exception as exc:
            self.report.event("board.internal_error",
                              f"{fn.__name__}: {exc}\n{traceback.format_exc()}")
            return None

    # ------------------------------------------------------------------
    # static probes (do not require an instance)
    # ------------------------------------------------------------------

    @staticmethod
    def task_id_anywhere(run_dir, state: Dict[str, Any]) -> bool:
        """True when a card was recorded in state["board"]["task_id"]
        OR process_manifest.json's cc_task_id."""
        if (state.get("board") or {}).get("task_id"):
            return True
        cc = _get_cc_board()
        manifest = cc._read_manifest(run_dir)
        if manifest.get("cc_task_id"):
            return True
        return False

    @staticmethod
    def has_failed_advance(run_dir) -> bool:
        """True when cc-board.json holds an unsuperseded ok:false status movement."""
        import json as _json
        import cc_board as _ccb
        p = _ccb._movements_path(run_dir)
        if not p.exists():
            return False
        try:
            data = _json.loads(p.read_text())
        except (_json.JSONDecodeError, OSError):
            return False
        movements = data.get("movements") if isinstance(data, dict) else None
        if not isinstance(movements, list):
            return False
        last_failed = None
        for m in movements:
            if not isinstance(m, dict) or m.get("kind") != "status":
                continue
            if m.get("ok"):
                last_failed = None
            else:
                last_failed = m
        return last_failed is not None

    # ------------------------------------------------------------------
    # board operations
    # ------------------------------------------------------------------

    def open_card(self, deck_slug, title, description):
        """Create a task card via cc_board.ingest_deck_task.

        Persists the returned task_id in self.state["board"]["task_id"] so
        every subsequent method (phase_progress, mark_in_progress, mark_review,
        mark_blocked) can read it without re-parsing process_manifest.json.

        Also stores card_params so _resolve_task_id() can re-create the card
        if the task_id is later lost (e.g. state.json deleted or corrupted).
        """
        cc = _get_cc_board()

        def _do():
            # Store params FIRST so even if ingest fails, _resolve_task_id()
            # has something to work with on a retry.
            board_state = self.state.setdefault("board", {})
            board_state["card_params"] = {
                "deck_slug": deck_slug,
                "title": title,
                "description": description,
            }

            # FIX 57: pass run_id in the BOARD identity namespace (_run_slug,
            # not _run_id -- the job_id is the per-run cache key and never
            # reaches the board) so the parent card's source_ref (its Ref:
            # line) and external_session_id (its Session: line) are THIS
            # run's identity -- the same namespace the child Session: line
            # and sweep._card_ref_identity read, so the pairing can match.
            task_id = cc.ingest_deck_task(
                self.run_dir, deck_slug, title, description,
                priority="normal", env=os.environ,
                run_id=self._run_slug())
            if task_id:
                board_state["task_id"] = task_id
                board_state.pop("task_id_missing_at", None)
                self.store.save(self.state)
            else:
                self.report.event(
                    "board.ingest_failed",
                    f"ingest_deck_task returned None for deck={deck_slug!r} "
                    f"title={title!r}; board will remain a no-op until ingestion succeeds"
                )
                board_state["ingest_attempted_at"] = _utcnow_iso()
            return task_id

        return self._wrap(_do)

    def phase_progress(self, phase_id, note):
        """Post mid-run activity. Never patch_phase -- use post_activity instead.

        activity_type is pinned to 'updated' (FIX 57 activity-type alignment):
        the CC CreateActivitySchema accepts only {spawned, updated, completed,
        file_created, status_changed} -- 'comment' is not a member and a strict
        server 422s it, silently dropping every mid-run phase breadcrumb."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
                self.report.event(
                    "board.task_id_missing",
                    f"phase_progress({phase_id!r}): no task_id; call open_card() first "
                    f"or check board.no_task_id for root cause"
                )
                return None
            return cc.post_activity(self.run_dir, task_id, phase_id, note,
                                    activity_type="updated", scores=None, env=os.environ)

        return self._wrap(_do)

    def mark_in_progress(self):
        """Mark the P4-RENDER start: patch_phase with status='in_progress'."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
                self.report.event(
                    "board.task_id_missing",
                    "mark_in_progress(): no task_id; call open_card() first "
                    "or check board.no_task_id for root cause"
                )
                return None
            status = "in_progress"
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, task_id, "P4-RENDER", status,
                                  "Rendering started", env=os.environ)

        return self._wrap(_do)

    def mark_review(self):
        """Mark complete: patch_phase with status='review'. Never 'done'."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
                self.report.event(
                    "board.task_id_missing",
                    "mark_review(): no task_id; call open_card() first "
                    "or check board.no_task_id for root cause"
                )
                return None
            status = "review"
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, task_id, "TERMINAL", status,
                                  "All gates passed", env=os.environ)

        return self._wrap(_do)

    def mark_blocked(self, phase_id, reason):
        """Mark the task blocked with a reason."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
                self.report.event(
                    "board.task_id_missing",
                    f"mark_blocked({phase_id!r}): no task_id; call open_card() first "
                    "or check board.no_task_id for root cause"
                )
                return None
            status = "blocked"
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, task_id, phase_id, status,
                                  reason, env=os.environ)

        return self._wrap(_do)

    # -- Option B child cards ---------------------------------------------
    def _run_id(self):
        """This run's identity for the per-run parent cache key: state.json's
        job_id (minted 'pj_...' in __main__.cmd_new), falling back to the run
        dir name. Instance-internal only -- it never reaches the board."""
        rid = self.state.get("job_id")
        if rid:
            return str(rid)
        return self.run_dir.name

    def _run_slug(self):
        """This run's identity in the BOARD's namespace: intake.deck_slug
        (FIX 48 makes resolve_intake write deck_slug = run dir name), falling
        back to the run dir name -- the same two sources sweep._deck_slug
        reads and the SAME value open_card() sent as source_ref. cc_board
        sends it as BOTH source_ref and external_session_id (cc_board.py
        :614,626), so the parent card's description carries 'Session: <slug>'
        and 'Ref: <slug>'. A child's Session line must be in this namespace
        or the parent's Ref could never match it."""
        slug = (self.state.get("intake") or {}).get("deck_slug")
        if slug:
            return str(slug)
        return self.run_dir.name

    def _resolve_parent_task_id(self):
        """Parent id lookup, cached PER RUN ID (FIX 57).

        Resolution order per run_id:
          1. state["board"]["task_id"] (live truth: open_card re-stamps it on
             re-ingest),
          2. process_manifest.json's cc_task_id,
          3. the per-run cache (a memo only, never an override).

        Sources 1 and 2 are both under THIS run_dir, so a value recovered from
        them can only belong to this run. The cache is instance state on a
        BoardMirror created once per Engine, so it is NEVER process-wide and a
        second concurrent job cannot inherit this run's parent -- the exact
        mechanism behind the 47-of-49 misparenting incident."""
        cc = _get_cc_board()
        rid = self._run_id()
        tid = (self.state.get("board") or {}).get("task_id")
        if not tid:
            try:
                manifest = cc._read_manifest(self.run_dir)
            except Exception:
                manifest = {}
            tid = manifest.get("cc_task_id")
        if not tid:
            cached = self._parent_by_run.get(rid)
            if cached:
                return str(cached)
            return None
        self._parent_by_run[rid] = str(tid)
        return str(tid)

    def _resolve_child_task_id(self, phase_id):
        """Dual-recovery child id lookup for one phase: state["board"]
        ["children"][phase_id] first, process_manifest.json's
        cc_child_task_ids map second (cc_board.read_child_task_id)."""
        children = (self.state.get("board") or {}).get("children") or {}
        tid = children.get(phase_id) if isinstance(children, dict) else None
        if tid:
            return str(tid)
        return _get_cc_board().read_child_task_id(self.run_dir, phase_id)

    def _remember_child_task_id(self, phase_id, task_id):
        """Write the phase_id -> child_task_id mapping into state.json -- the
        in-memory/on-disk half of the dual persistence; cc_board.
        ingest_child_task already wrote the process_manifest.json half via
        stamp_child_task_id. Any failure here surfaces through _wrap's own
        except clauses (never raises past this call)."""
        children = self.state.setdefault("board", {}).setdefault("children", {})
        children[phase_id] = task_id
        self.store.save(self.state)

    def child_report(self, phase_id, title, description, status, note):
        """Ensure a child card exists for `phase_id` (created ONCE, on the
        first call for that phase -- idempotent via the dual state+manifest
        check in _resolve_child_task_id, so a phase reporting progress twice
        never mints a second card), then PATCH it to `status` via the SAME
        patch_phase status-PATCH helper every other advance in this class
        uses (e.g. status='done' once the phase's verifier has passed,
        status='blocked' on a gate failure).

        FIX 57 — run identity on every child mint: the ingest description
        carries a 'Session: <run id>' line (this run's board-namespace slug)
        and the parent card's description carries 'Ref: <deck_slug>'. A child
        whose Session differs from the parent's Ref identity is HELD with
        deck_run_identity_mismatch instead of being patched/parented into the
        wrong run's set: the mismatch is recorded on the movement receipt and
        surfaced as a board.identity_mismatch event, and no child card is
        minted against a parent that does not belong to this run.

        No parent card yet (board disabled, or the parent ingest never
        landed) => nothing to nest a child under => clean no-op, same as
        every other method here. FAIL-SOFT: never raises (wrapped in _wrap,
        Invariant 1) -- a Command Center outage can never block the phase
        loop."""
        cc = _get_cc_board()

        def _do():
            parent_task_id = self._resolve_parent_task_id()
            if not parent_task_id:
                return None
            run_id = self._run_slug()
            if not self._parent_belongs_to_run(parent_task_id, run_id):
                detail = (f"deck_run_identity_mismatch: parent {parent_task_id} "
                          f"is not this run's card (run id {run_id!r}) -- child "
                          f"card for phase {phase_id} HELD, never parented into "
                          f"another run's set")
                self.report.event("board.identity_mismatch", detail)
                try:
                    cc._record_movement(self.run_dir, {
                        "phase_id": phase_id, "kind": "child_ingest",
                        "target": "deck_run_identity_mismatch",
                        "endpoint": "POST /api/tasks/ingest",
                        "http_status": None, "ok": False,
                        "detail": detail,
                    })
                except Exception:
                    pass
                return None
            child_task_id = self._resolve_child_task_id(phase_id)
            if not child_task_id:
                session_line = f"Session: {run_id}"
                ref_line = f"Ref: {parent_task_id}:{phase_id}"
                child_description = description if description else ""
                if session_line not in child_description:
                    child_description = (
                        f"{child_description}\n\n{session_line}\n{ref_line}".strip()
                    )
                # FIX 57 child Session line: run_id rides in
                # external_session_id (the card's Session: provenance line on
                # the wire), matching the Session: line already written into
                # the description above and pairing against the parent's Ref:
                # (= run id, since open_card now ingests with run_id) for the
                # deck_run_identity_mismatch hold.
                child_task_id = cc.ingest_child_task(
                    self.run_dir, parent_task_id, phase_id, title,
                    child_description, priority="normal", env=os.environ,
                    run_id=run_id)
                if not child_task_id:
                    return None
                self._remember_child_task_id(phase_id, child_task_id)
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, child_task_id, phase_id, status,
                                  note, env=os.environ)

        return self._wrap(_do)

    def _parent_belongs_to_run(self, parent_task_id, run_id):
        """FIX 57 identity check: does the parent card this child would nest
        under provably belong to THIS run?

        OFFLINE provenance (zero network — the sanctioned child-card tests
        budget their HTTP call sequences exactly, and the identity evidence
        is already on disk): process_manifest.json lives INSIDE this run's
        run_dir, and stamp_task_id writes cc_task_id AND the matching
        cc_registration.deck_slug in the SAME atomic merge from the SAME
        ingest_deck_task call (cc_board.py:666,1238) — so a registration
        tag present in this run's manifest is, by construction, the
        deck_slug THIS run's ingest sent as the parent's source_ref.

        Accept when the registered slug equals EITHER candidate identity:
        _run_slug (intake.deck_slug -> run dir name -- what the sweep
        resolves) or the raw run dir name (what phases.py passes to
        open_card as deck_slug -- the pre-FIX-48 engine handle, and the
        value actually stamped on the card when the ENGINE opened it).

        UNDETERMINED is not a mismatch: no registration tag in the manifest
        (older stamps, a hand-written task_id, a test stub) returns True and
        lets the mint proceed. Only a POSITIVE registration naming a foreign
        slug holds the child with deck_run_identity_mismatch -- the in-memory
        parent leak shape this run's per-run cache (_parent_by_run) alone
        already closes; this is the on-disk belt on that suspender."""
        cc = _get_cc_board()
        try:
            manifest = cc._read_manifest(self.run_dir)
        except Exception:
            manifest = {}
        reg = manifest.get("cc_registration") if isinstance(manifest, dict) else None
        if isinstance(reg, dict):
            slug = reg.get("deck_slug")
            if slug:
                slug = str(slug)
                candidates = {str(run_id), str(self.run_dir.name)}
                return any(
                    slug == cand or slug.startswith(f"{cand}:")
                    for cand in candidates
                )
        # No registration tag -> UNDETERMINED, never a mismatch.
        return True


# ------------------------------------------------------------------
# internal helpers
# ------------------------------------------------------------------

def _utcnow_iso():
    """Return current UTC timestamp as ISO-8601 string, timezone-naive."""
    from datetime import datetime, timezone as _tz
    return datetime.now(_tz.utc).isoformat()
