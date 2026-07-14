#!/usr/bin/env python3
"""persona_bundle_ladder.py — the bundle-ACQUISITION ladder for Skill 6 (B-U1 / U15).

WHY THIS EXISTS
----------------
Skill 6 (`v2_dispatcher.py`) has zero wiring to the ONE unified persona-blend
system (`persona_blend.build_bundle` / `build_blend_directive`) the Command
Center already uses for every other content engine. This module is the seam
that converges Skill 6 onto that ONE system: it acquires a persona-bundle for
a task using a first-hit-wins ladder, normalizes whichever shape it received
into ONE canonical interface every downstream consumer reads, and ALWAYS
writes an audit receipt so the acquisition is honest and resumable.

LADDER (first hit wins)
------------------------
  1. threaded  — ``task['persona_bundle']`` was already supplied by the caller
                  (the Command Center dispatch payload carries `bundle_json`
                  per task in `task_persona_bundle` today; a CC-side change
                  threads it into the dispatch payload — this rung reads it
                  the moment that happens; it is a pure no-op until then).
  2. cc         — a read-only fetch against the Command Center
                  (`cc_board.fetch_persona_bundle`, GET
                  `/api/tasks/<id>/persona-bundle`). Fail-soft: an unreachable
                  or not-yet-shipped endpoint falls through to rung 3, never
                  blocks the build.
  3. local      — invoke the IDENTICAL blend engine the Command Center spawns,
                  locally (`persona-selector-v2.py --blend`), so a standalone /
                  offline box still gets a real bundle, not a second vocabulary.
  4. absent     — no bundle anywhere. Exact legacy behavior: the receipt says
                  so and every downstream consumer treats a missing bundle as
                  a clean no-op (fail-soft on AVAILABILITY).

FAIL-SOFT on availability, FAIL-CLOSED on honesty: a missing bundle never
blocks a build; a bundle that IS present but has its audience confirmation
still pending on a Command-Center-connected run HOLDS (the same class of gate
as FIX-COPY-01) rather than silently building under an unconfirmed voice. A
standalone run (no CC connection to wait on) instead DEGRADES to the neutral
topic-only house voice `persona_blend` already documents for this case, with
the degradation NAMED in the receipt — never silent.

Always writes ``routing/persona-bundle-receipt.json``:
    {source, bundle_sha, voice_persona_id, topic_persona_id, task_personas,
     confirm_state, degradation, hold}

Never raises into the dispatch loop — matches the posture of every other
optional seam in `v2_dispatcher.py` (step0, model routing, board mirror).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TOOLS_DIR, "..", ".."))
_SELECTOR_SCRIPT = os.path.normpath(
    os.path.join(_REPO_ROOT, "23-ai-workforce-blueprint", "scripts", "persona-selector-v2.py"))

RECEIPT_NAME = "persona-bundle-receipt.json"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Normalisation — bridges the two shapes a bundle can arrive in:
#   (a) CC's flat task_persona_bundle mirror columns (voice_persona_id,
#       topic_persona_id, audience_id, audience_label, audience_source,
#       voice_collapsed, blend_directive) — migration 090 (CC:migrations.ts).
#   (b) persona_blend.build_bundle()'s nested SUPERSET (persona_id, voice{},
#       resolved_audience{}, task_personas[]) — the shape rung 3 always
#       returns, and the shape CC's own `bundle_json` column carries.
# Every downstream consumer (B-U2/B-U3/B-U5) reads ONLY this canonical shape.
# --------------------------------------------------------------------------- #
def _normalize_bundle(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}

    voice_block = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
    resolved_audience = (raw.get("resolved_audience")
                         if isinstance(raw.get("resolved_audience"), dict) else {})

    voice_pid = raw.get("voice_persona_id")
    if voice_pid is None:
        voice_pid = raw.get("persona_id")

    topic_pid = raw.get("topic_persona_id")
    if topic_pid is None:
        tp = voice_block.get("topic_persona")
        topic_pid = tp.get("id") if isinstance(tp, dict) else None

    audience_id = raw.get("audience_id")
    if audience_id is None:
        ap = voice_block.get("audience_persona")
        audience_id = ap.get("id") if isinstance(ap, dict) else None

    audience_label = raw.get("audience_label")
    if audience_label is None:
        audience_label = resolved_audience.get("label")

    collapsed = raw.get("voice_collapsed")
    if collapsed is None:
        collapsed = voice_block.get("collapsed")

    confirm_required = raw.get("confirm_required")
    if confirm_required is None:
        confirm_required = resolved_audience.get("confirm_required")

    content_task = raw.get("content_task")

    task_personas = raw.get("task_personas")
    if not isinstance(task_personas, list):
        task_personas = []

    return {
        "voice_persona_id": voice_pid,
        "topic_persona_id": topic_pid,
        "audience_id": audience_id,
        "audience_label": audience_label,
        "collapsed": bool(collapsed) if collapsed is not None else None,
        "blend_directive": raw.get("blend_directive"),
        "confirm_required": (bool(confirm_required) if confirm_required is not None else None),
        "content_task": content_task,
        "task_personas": task_personas,
    }


def _bundle_sha(raw: dict) -> Optional[str]:
    if not raw:
        return None
    try:
        blob = json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Rung 2 — Command Center fetch (fail-soft; the endpoint may not exist yet).
# --------------------------------------------------------------------------- #
def _default_cc_fetch(board_id: str, *, env: Optional[dict] = None) -> Optional[dict]:
    try:
        if _TOOLS_DIR not in sys.path:
            sys.path.insert(0, _TOOLS_DIR)
        import cc_board as _cc_board  # type: ignore[import]
    except Exception:  # noqa: BLE001 — cc_board unavailable is a clean no-op
        return None
    fetch = getattr(_cc_board, "fetch_persona_bundle", None)
    if fetch is None:
        return None
    try:
        return fetch(board_id, env=env)
    except Exception:  # noqa: BLE001 — never blocks the ladder
        return None


# --------------------------------------------------------------------------- #
# Rung 3 — local compute: the IDENTICAL --blend engine the Command Center
# spawns, invoked in-process-adjacent via subprocess so a standalone / offline
# box unifies too (never a second vocabulary).
#
# Opt-in via GHL_PERSONA_BLEND_LOCAL (truthy) — same posture as STEP 0's own
# GHL_FUNNEL_CATALOG/GHL_FUNNEL_INDEX gating (v2_dispatcher.py's step0_matcher
# is "auto-configured from env vars ... when funnel_matcher is importable").
# A real selector run shells out to a ~1s subprocess and (read-only) touches
# whatever persona catalog / dashboard DB the box resolves by default — never
# something a BOUNDED, always-fast dispatcher should do unconditionally on
# every dispatch. Unconfigured => this rung is a fast, deterministic no-op and
# the ladder falls through to `absent` (exact legacy behavior).
# --------------------------------------------------------------------------- #
def _local_rung_enabled(env: dict) -> bool:
    return str(env.get("GHL_PERSONA_BLEND_LOCAL", "")).strip().lower() in (
        "1", "true", "yes", "on")


def _default_selector_runner(task: dict, *, env: Optional[dict] = None) -> Optional[dict]:
    env = env if env is not None else os.environ
    if not _local_rung_enabled(env):
        return None
    if not os.path.isfile(_SELECTOR_SCRIPT):
        return None
    task_text = (task.get("brief") or task.get("text") or task.get("title")
                or task.get("description") or "").strip() or "funnel page copy"
    department = task.get("department") or "marketing"
    topic = task.get("topic_hint") or ""
    cmd = [sys.executable, _SELECTOR_SCRIPT, "--blend",
           "--task", task_text, "--department", str(department),
           "--format", "json", "--no-record"]
    if topic:
        cmd += ["--topic", str(topic)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except Exception:  # noqa: BLE001 — a crashed/hung selector is just "absent"
        return None
    if proc.returncode not in (0, 1):
        return None
    try:
        bundle = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None
    return bundle if isinstance(bundle, dict) else None


# --------------------------------------------------------------------------- #
# THE LADDER
# --------------------------------------------------------------------------- #
def resolve_persona_bundle(
    task: dict,
    evidence_root: str,
    *,
    env: Optional[dict] = None,
    cc_fetch: Optional[Callable[..., Optional[dict]]] = None,
    selector_runner: Optional[Callable[..., Optional[dict]]] = None,
) -> dict:
    """Acquire a persona bundle for ``task`` via the threaded -> cc -> local ->
    absent ladder, normalize it, write the receipt, and thread the result onto
    the task (``task['persona_bundle']`` = normalized, ``task['persona_bundle_raw']``
    = whatever was actually received). Returns the receipt dict. Never raises.
    """
    env = env if env is not None else os.environ

    source = "absent"
    raw: Optional[dict] = None
    cc_connected = False

    threaded = task.get("persona_bundle")
    if isinstance(threaded, dict) and threaded:
        raw = threaded
        source = "threaded"
        cc_connected = True  # a threaded bundle implies a CC-dispatched task
    else:
        board_id = (task.get("board_task_id") or task.get("id") or "").strip()
        if board_id:
            fetch_fn = cc_fetch or _default_cc_fetch
            try:
                fetched = fetch_fn(board_id, env=env)
            except Exception:  # noqa: BLE001
                fetched = None
            if isinstance(fetched, dict) and fetched:
                raw = fetched
                source = "cc"
                cc_connected = True

        if raw is None:
            run_fn = selector_runner or _default_selector_runner
            try:
                computed = run_fn(task, env=env)
            except Exception:  # noqa: BLE001
                computed = None
            if isinstance(computed, dict) and computed:
                raw = computed
                source = "local"

    norm = _normalize_bundle(raw) if raw is not None else {}
    bundle_sha = _bundle_sha(raw) if raw is not None else None
    confirm_required = norm.get("confirm_required")

    if source == "absent":
        confirm_state = "n/a"
    elif confirm_required:
        confirm_state = "pending"
    else:
        confirm_state = "confirmed"

    degradation = None
    hold = False
    if confirm_state == "pending":
        if cc_connected:
            hold = True
        else:
            degradation = (
                "audience-unconfirmed-standalone: persona_blend degraded to the "
                "neutral topic-only house voice (build_blend_directive's documented "
                "graceful degradation) — no operator connection to HOLD against on "
                "an offline/local box."
            )

    receipt = {
        "task_id": task.get("id"),
        "source": source,
        "bundle_sha": bundle_sha,
        "voice_persona_id": norm.get("voice_persona_id"),
        "topic_persona_id": norm.get("topic_persona_id"),
        "task_personas": norm.get("task_personas") or [],
        "confirm_state": confirm_state,
        "degradation": degradation,
        "hold": hold,
        "generated_at": _ts(),
    }

    try:
        routing_dir = os.path.join(evidence_root, "routing")
        os.makedirs(routing_dir, exist_ok=True)
        with open(os.path.join(routing_dir, RECEIPT_NAME), "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)
    except OSError:
        pass  # receipt write is best-effort; the in-memory receipt is still returned

    if raw is not None:
        task["persona_bundle"] = norm
        task["persona_bundle_raw"] = raw
    task["persona_bundle_receipt"] = receipt

    return receipt


if __name__ == "__main__":
    # Offline self-test — no network, no CC, no live selector run required for
    # the threaded/absent rungs; the local rung is exercised only if the
    # selector script is reachable (best-effort, never fails the self-test).
    import tempfile

    ok = True

    def check(label, cond):
        global ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    with tempfile.TemporaryDirectory() as td:
        # threaded rung, confirmed -> no hold
        task = {"id": "t1", "persona_bundle": {
            "voice_persona_id": "hormozi-100m-offers", "topic_persona_id": "miller-storybrand",
            "confirm_required": False, "blend_directive": "Write in Hormozi's voice. GUARDRAIL",
            "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
        }}
        r = resolve_persona_bundle(task, td)
        check("threaded rung wins", r["source"] == "threaded")
        check("confirmed -> confirm_state=confirmed", r["confirm_state"] == "confirmed")
        check("no hold when confirmed", r["hold"] is False)
        check("voice id normalized", r["voice_persona_id"] == "hormozi-100m-offers")
        check("task carries normalized bundle",
              task["persona_bundle"]["voice_persona_id"] == "hormozi-100m-offers")
        check("receipt written to disk",
              os.path.isfile(os.path.join(td, "routing", RECEIPT_NAME)))

    with tempfile.TemporaryDirectory() as td:
        # threaded rung, PENDING confirm on a CC-connected run -> HOLD
        task = {"id": "t2", "persona_bundle": {
            "voice_persona_id": "hormozi-100m-offers", "confirm_required": True}}
        r = resolve_persona_bundle(task, td)
        check("pending + connected -> hold", r["hold"] is True)
        check("pending confirm_state", r["confirm_state"] == "pending")
        check("no degradation named on a HOLD", r["degradation"] is None)

    with tempfile.TemporaryDirectory() as td:
        # all rungs fail -> absent, byte-identical legacy behavior
        task = {"id": "t3"}
        r = resolve_persona_bundle(
            task, td, cc_fetch=lambda *_a, **_k: None, selector_runner=lambda *_a, **_k: None)
        check("all rungs failing -> absent", r["source"] == "absent")
        check("absent -> confirm_state n/a", r["confirm_state"] == "n/a")
        check("absent -> never holds", r["hold"] is False)

    with tempfile.TemporaryDirectory() as td:
        # cc rung wins over local when reachable, no threaded bundle
        task = {"id": "t4", "board_task_id": "cc-task-4"}
        r = resolve_persona_bundle(
            task, td,
            cc_fetch=lambda *_a, **_k: {"voice_persona_id": "wiebe-copy-hackers",
                                        "confirm_required": False},
            selector_runner=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("local rung must not run when cc rung hit")),
        )
        check("cc rung wins", r["source"] == "cc")

    with tempfile.TemporaryDirectory() as td:
        # standalone run, pending confirm -> degrades, never holds
        task = {"id": "t5"}
        r = resolve_persona_bundle(
            task, td, cc_fetch=lambda *_a, **_k: None,
            selector_runner=lambda *_a, **_k: {
                "persona_id": "miller-storybrand", "confirm_required": True,
                "voice": {"topic_persona": {"id": "miller-storybrand"}}},
        )
        check("local rung wins offline", r["source"] == "local")
        check("standalone pending -> never holds", r["hold"] is False)
        check("standalone pending -> degradation named", bool(r["degradation"]))

    with tempfile.TemporaryDirectory() as td:
        # DEFAULT posture (no injection, GHL_PERSONA_BLEND_LOCAL unset): rung 3
        # is a fast, deterministic no-op — same posture as STEP 0's own env
        # gating. A bounded dispatcher never shells out unconditionally.
        task = {"id": "t6"}
        r = resolve_persona_bundle(task, td, cc_fetch=lambda *_a, **_k: None,
                                   env={})
        check("rung 3 disabled by default (no GHL_PERSONA_BLEND_LOCAL) -> absent",
              r["source"] == "absent")

    if os.path.isfile(_SELECTOR_SCRIPT):
        with tempfile.TemporaryDirectory() as td:
            # Opt-in: GHL_PERSONA_BLEND_LOCAL=1 actually invokes the real
            # --blend engine (best-effort; skipped if the script errors in
            # this environment — never fails the self-test on that alone).
            task = {"id": "t7", "brief": "build a lead-magnet funnel"}
            r = resolve_persona_bundle(
                task, td, cc_fetch=lambda *_a, **_k: None,
                env={**os.environ, "GHL_PERSONA_BLEND_LOCAL": "1"})
            if r["source"] == "local":
                check("opt-in rung 3 fires a real local bundle", True)
            else:
                print("  [SKIP] opt-in rung 3 (selector unreachable in this env)")
    else:
        print("  [SKIP] opt-in rung 3 (persona-selector-v2.py not found)")

    print("== persona_bundle_ladder self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)
