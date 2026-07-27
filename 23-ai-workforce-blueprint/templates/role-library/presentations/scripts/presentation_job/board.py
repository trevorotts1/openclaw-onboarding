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

    def open_card(self, deck_slug, title, description):
        """Create a task card via cc_board.ingest_deck_task."""
        cc = _get_cc_board()

        def _do():
            task_id = cc.ingest_deck_task(
                self.run_dir, deck_slug, title, description,
                priority="normal", env=os.environ)
            if task_id:
                self.state.setdefault("board", {})["task_id"] = task_id
                self.store.save(self.state)
            return task_id

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

