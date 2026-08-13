from __future__ import annotations

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

    def open_card(self, deck_slug, title, description):
        """Create a task card via cc_board.ingest_deck_task."""
        cc = _get_cc_board()

        def _do():
            return cc.ingest_deck_task(
                self.run_dir, deck_slug, title, description,
                priority="normal", env=os.environ)

        return self._wrap(_do)

    def phase_progress(self, phase_id, note):
        """Post mid-run activity. Never patch_phase — use post_activity instead."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
                return None
            return cc.post_activity(self.run_dir, task_id, phase_id, note,
                                    activity_type="comment", scores=None, env=os.environ)

        return self._wrap(_do)

    def mark_in_progress(self):
        """Mark the P4-RENDER start: patch_phase with status='in_progress'."""
        cc = _get_cc_board()

        def _do():
            task_id = (self.state.get("board") or {}).get("task_id")
            if not task_id:
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
                return None
            status = "blocked"
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, task_id, phase_id, status,
                                  reason, env=os.environ)

        return self._wrap(_do)

    # -- Option B child cards ---------------------------------------------
    def _resolve_parent_task_id(self):
        """Dual-recovery parent id lookup: state["board"]["task_id"] first,
        process_manifest.json's cc_task_id second -- the same two sources
        task_id_anywhere() checks."""
        tid = (self.state.get("board") or {}).get("task_id")
        if tid:
            return str(tid)
        manifest = _get_cc_board()._read_manifest(self.run_dir)
        val = manifest.get("cc_task_id")
        return str(val) if val else None

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
            child_task_id = self._resolve_child_task_id(phase_id)
            if not child_task_id:
                child_task_id = cc.ingest_child_task(
                    self.run_dir, parent_task_id, phase_id, title, description,
                    priority="normal", env=os.environ)
                if not child_task_id:
                    return None
                self._remember_child_task_id(phase_id, child_task_id)
            if status not in cc.CC_TASK_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            return cc.patch_phase(self.run_dir, child_task_id, phase_id, status,
                                  note, env=os.environ)

        return self._wrap(_do)
