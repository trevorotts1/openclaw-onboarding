#!/usr/bin/env python3
"""parallel_saves.py — emitter for parallel page-save batches (Skill 06).

SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
reaper backstop.

This is an EMITTER, not an executor.  It builds a batch plan — a dict that
describes N per-page autosave steps all bracketed by ONE browser_session()
context and ONE mandatory teardown step — which the agent then feeds to
parallel_saves.sh run-batch (or drives directly via the browser_manager
eval path).

PRIMARY APPROACH (shared cleared session + fan-out concurrent evals):
  The Cloudflare-cleared session already exists as the ONE canonical
  agent-browser context opened by bm_ensure.  We parallelize by fanning out
  up to AB_SAVE_CONCURRENCY concurrent "agent-browser eval" calls against
  that SAME session.  AB_MAX_SESSIONS stays 1 (one browser).

KEY GUARANTEES:
  - Refuses to emit a batch plan outside an active browser_session() bracket
    (singleton gateway — same contract as ghl_builder.browser_cmd).
  - Every batch plan ends with EXACTLY ONE teardown_browser step, regardless
    of how many pages are in the batch.
  - save_concurrency() clamps the value to [1, 5]; never exceeds 5.
  - Never calls subprocess.run / os.system / os.exec* with "agent-browser" —
    this is a pure emitter (no live-process management).

VERSION (kept in sync by scripts/bump-version.sh):
"""

from __future__ import annotations

import os
from typing import List, Optional

PARALLEL_SAVES_PY_VERSION = "v14.3.7"

# Hard upper bound on in-flight eval calls.  AB_MAX_SESSIONS STAYS 1.
SAVE_CONCURRENCY_DEFAULT = 5
SAVE_CONCURRENCY_MIN = 1
SAVE_CONCURRENCY_MAX = 5


def save_concurrency(env: Optional[dict] = None) -> int:
    """Return the clamped save concurrency from the environment.

    Reads ``AB_SAVE_CONCURRENCY``; falls back to ``SAVE_CONCURRENCY_DEFAULT``
    (5).  Always returns an integer in ``[SAVE_CONCURRENCY_MIN,
    SAVE_CONCURRENCY_MAX]`` = [1, 5].  Mirrors ``bm_save_concurrency()`` in
    ``parallel_saves.sh``."""
    env = env if env is not None else os.environ
    raw = env.get("AB_SAVE_CONCURRENCY", str(SAVE_CONCURRENCY_DEFAULT))
    try:
        n = int(raw)
    except (ValueError, TypeError):
        n = SAVE_CONCURRENCY_DEFAULT
    # Hard clamp — the plan never promises more than 5 concurrent evals.
    return max(SAVE_CONCURRENCY_MIN, min(SAVE_CONCURRENCY_MAX, n))


def emit_batch_rest_save_plan(
    pages: List[dict],
    session: Optional[str] = None,
    *,
    env: Optional[dict] = None,
) -> dict:
    """Emit a batch plan for saving N pages concurrently (up to cap 5).

    Each element of ``pages`` is a per-page kwargs dict accepted by
    ``ghl_builder.emit_rest_save_plan`` (minus ``session``, which is injected
    here from the canonical singleton).  The batch plan:

      - Wraps ALL per-page steps in ONE ``browser_session()`` bracket.
      - Carries ONE ``teardown_browser`` step at the end (no per-page teardown
        — the teardown fires once after the whole batch).
      - Carries ``save_concurrency`` so the executor (parallel_saves.sh) knows
        the cap to apply.

    Refuses outside an active ``browser_session()`` context (same contract as
    ``ghl_builder.browser_cmd`` / ``browser_manager.assert_session_active``).

    Args:
        pages: list of per-page spec dicts, each accepted by
            ``ghl_builder.emit_rest_save_plan`` (without ``session``).
        session: the canonical session name; when None the active session name
            from ``browser_manager.session_name()`` is used.
        env: optional env dict for ``save_concurrency()``; defaults to
            ``os.environ``.

    Returns:
        ``{plan, ok, session, save_concurrency, page_count, pages, steps,
        teardown_step}``.  On any per-page gate MISMATCH the page plan is
        included in ``pages`` with ``ok=False``; the batch ``ok`` is False iff
        any page plan is refused."""
    import browser_manager  # lazy: keeps parallel_saves importable standalone
    import ghl_builder as gb  # lazy

    browser_manager.assert_session_active("parallel_saves.emit_batch_rest_save_plan")

    sname = session or browser_manager.session_name()
    cap = save_concurrency(env)

    page_plans: list[dict] = []
    all_steps: list[dict] = []
    batch_ok = True

    for i, page_kwargs in enumerate(pages):
        # Inject the canonical session; do NOT bracket individual page plans
        # with their own teardown (only one batch-level teardown at the end).
        kw = {**page_kwargs, "session": sname}
        try:
            pp = gb.emit_rest_save_plan(**kw)
        except Exception as exc:  # pragma: no cover — defensive
            pp = {
                "plan": "rest_save",
                "ok": False,
                "refused": True,
                "reason": f"emit_rest_save_plan raised: {exc}",
                "steps": [],
                "page_index": i,
            }

        # Strip the per-page teardown_browser step if present — the batch plan
        # carries exactly ONE teardown at the end.
        inner_steps = [
            s for s in pp.get("steps", [])
            if s.get("step") != "teardown_browser"
        ]
        # Tag each step with its page_index for the executor.
        for s in inner_steps:
            s = dict(s)
            s["page_index"] = i
            s["page_id"] = page_kwargs.get("page_id", "")
            all_steps.append(s)

        pp_summary = {k: v for k, v in pp.items() if k != "steps"}
        pp_summary["page_index"] = i
        pp_summary["step_count"] = len(inner_steps)
        page_plans.append(pp_summary)

        if not pp.get("ok", True):
            batch_ok = False

    # ONE mandatory batch-level teardown step (satisfies the singleton-test
    # invariant: plan ends with EXACTLY ONE teardown_browser step for K pages).
    teardown_step = {
        "step": "teardown_browser",
        "action": "close_session",
        "session": sname,
        "cmd": browser_manager.emit_teardown_step(sname),
        "note": (
            "MANDATORY close of the singleton session — fires once after ALL "
            "parallel page saves (batch-level teardown; no per-page teardown "
            "so the shared cleared session stays open during the fan-out)."
        ),
    }
    all_steps.append(teardown_step)

    return {
        "plan": "batch_rest_save",
        "ok": batch_ok,
        "session": sname,
        "save_concurrency": cap,
        "page_count": len(pages),
        "pages": page_plans,
        "steps": all_steps,
        # Convenience: the last step is always the teardown.
        "teardown_step": teardown_step,
    }
