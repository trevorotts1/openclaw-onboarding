#!/usr/bin/env python3
"""ghl_builder.py — Engine-agnostic orchestration helpers for the GoHighLevel
browser-driven Funnel / Website / Page builder (Skill 06 overhaul).

THIS IS THE GLUE, NOT THE CLICKER. The actual UI navigation is performed by the
AGENT at runtime using agent-browser (PRIMARY) or Playwright (FALLBACK), driven
by live snapshots and the gate registry (gates.json, D8). This module owns the
deterministic, mechanical parts so they are never improvised:

  * the page MANIFEST (A0.4) — the ordered build plan + resume key
  * the per-page LEDGER (D10/D12) — /tmp/<run-id>/<funnel>/<step>.json
  * the ZHC naming prefix enforcement (guardrail 2)
  * the hard sub-account match gate helper (A2.3)
  * the runtime-gate contract loader (gates.json) — captured vs runtime
  * the "never publish without approval" guard (A13.1)
  * marker-string verification of a fetched URL (A12.2 / A13.3 / C3)

It runs on Haiku-class mechanical work (ledger writes, manifest assembly, file
reads, URL/string verification) — NEVER the live UI loop. agent-browser/
Playwright commands are emitted as plans for the agent to execute; this module
does not itself drive the browser (keeps it testable + side-effect-free except
the ledger files it owns).

REST-autosave canvas wire-in (solution doc §5.2)
------------------------------------------------
``emit_rest_save_plan`` / ``emit_workflow_rewire_plan`` / ``emit_revert_plan``
turn the proven ``ghl_rest_canvas`` primitives into ordered, agent-runnable
eval-step PLANS — the read→splice→autosave→verify→revert recipe (and the
workflow read→rewire→re-read recipe). They keep the SAME glue-not-clicker
boundary: a plan is a side-effect-free ordered list of steps the agent executes
inside the (already-seeded) agent-browser; this module never opens or drives a
browser and makes no network calls of its own. The reused guards are wired
verbatim — ``subaccount_matches`` gates every write plan (MISMATCH = refuse),
``may_publish`` keeps autosave DRAFT by default, ``verify_url`` is the preview
HTTP-200+marker check. The funnels/builder + workflow routes are Cloudflare-WAF
gated (error 1010 for bare Python), so every step runs in-browser; the
media-upload + Skill-44 ecosystem routes (services.* origin, Bearer PIT) are a
SEPARATE auth model handled elsewhere — never routed through these plans.

Ledger states (furthest-reached per page): created | code-saved | page-saved |
previewed | published | FAILED. Workflows carry a parallel ``wf-rewired`` state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Page/funnel/website build states (furthest-reached, in order). The REST
# autosave flow maps onto these verbatim: page-saved = autosave 201 verified;
# previewed = verify_url pass; published only on may_publish().
LEDGER_STATES = ["created", "code-saved", "page-saved", "previewed", "published"]

# Workflow rewire is a PARALLEL state (not a page lifecycle stage): a trigger
# rewire that landed + read back via ?includeTriggers=true. Kept out of
# LEDGER_STATES so the page-flow ordering/idempotency is unaffected; recorded
# via ledger_write(..., state="wf-rewired") which is accepted exactly like a
# terminal state (never rewound, never ordered against the page states).
WORKFLOW_LEDGER_STATE = "wf-rewired"

# MATCH is case-INSENSITIVE (so an already-prefixed 'ZHC'/'zhc'/'Zhc' name is
# never double-prefixed), but every name this module EMITS uses the canonical
# UPPERCASE 'ZHC ' prefix exactly as Trevor states it in the transcript
# ("must carry a ZHC prefix … e.g. ZHC test", ~03:28–03:47). The old code emitted
# a lowercase 'zhc ' which drifted from the transcript — fixed here.
ZHC_PREFIX_RE = re.compile(r"^\s*zhc\b", re.IGNORECASE)

# Canonical, transcript-exact provenance prefix (UPPERCASE, trailing space).
ZHC_PREFIX = "ZHC "

# ── D6: HARD HEADLESS GUARD ──────────────────────────────────────────────────
# HEADLESS-ONLY — never open a visible window; taking over a screen is forbidden
# (esp. client boxes). agent-browser is headless by default, but an inherited
# AGENT_BROWSER_HEADED env var OR a {"headed": true} config file can silently
# force a HEADED window (this is exactly how a live run once opened a visible
# Chromium on the operator's screen). Every agent-browser invocation emitted or
# blessed by this module MUST start with this prefix, which:
#   - passes `--headed false` (agent-browser 0.27.0 documents this as the
#     explicit override that also disables a config-file "headed": true), and
#   - is paired with `unset AGENT_BROWSER_HEADED` in the shell wrappers.
# There is NO supported code path that may open a headed window — dev OR client.
AGENT_BROWSER_HEADLESS_PREFIX = "agent-browser --headed false"

# Values of AGENT_BROWSER_HEADED that are SAFE (headless). Anything else = headed.
_HEADED_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})


def headed_is_forced(env: dict | None = None) -> bool:
    """True iff the environment would force a VISIBLE (headed) browser window.
    Reads AGENT_BROWSER_HEADED (agent-browser's own env knob). A config-file
    "headed": true cannot be inspected here, which is exactly why the launch
    wrappers ALSO pass `--headed false` (the documented config override)."""
    env = env if env is not None else os.environ
    val = str(env.get("AGENT_BROWSER_HEADED", "")).strip().lower()
    return val not in _HEADED_OFF_VALUES


def headless_guard(env: dict | None = None) -> None:
    """REFUSE to proceed if a headed window could open (D6). Callers that are
    about to launch/drive the browser invoke this first. Raises RuntimeError
    rather than ever risk taking over a screen."""
    if headed_is_forced(env):
        raise RuntimeError(
            "REFUSE (D6 headless guard): AGENT_BROWSER_HEADED is set to a headed "
            "value, which would open a VISIBLE browser window. Headless is "
            "mandatory (never take over a screen, esp. client boxes). "
            "Run: unset AGENT_BROWSER_HEADED  and always pass `--headed false`."
        )


def browser_cmd(*args: str) -> str:
    """Return a single agent-browser command line, headless-FORCED (D6).
    Use this to emit any agent-browser invocation in a plan so no improvised
    call can ever drop `--headed false`. Example:
        browser_cmd("--session", "acme", "snapshot", "-i")
        -> 'agent-browser --headed false --session acme snapshot -i'

    SINGLETON POOLED BROWSER gateway: this emitter REFUSES (exit 75 / RuntimeError)
    if it is called outside an active ``browser_manager.browser_session()``
    context — so no plan can ever be assembled without a single canonical session
    + a guaranteed teardown step. Wrap callers in
    ``with browser_manager.browser_session(slug) as session:``."""
    import browser_manager  # lazy: keeps ghl_builder importable standalone
    browser_manager.assert_session_active("ghl_builder.browser_cmd")
    parts = [AGENT_BROWSER_HEADLESS_PREFIX, *(str(a) for a in args)]
    return " ".join(parts)


def _bracket_plan_with_teardown(plan: dict, session: str | None) -> dict:
    """Append the MANDATORY final teardown step to a plan's ``steps`` list when a
    session is in play (SINGLETON POOLED BROWSER gateway). Even a detach-and-exit
    run then tears down, because the close rides INSIDE the plan the agent runs.
    No-op when no session was supplied (the emitters then drive no browser)."""
    if not session:
        return plan
    import browser_manager  # lazy
    steps = plan.get("steps")
    if isinstance(steps, list):
        steps.append({
            "step": "teardown_browser",
            "action": "close_session",
            "session": session,
            "cmd": browser_manager.emit_teardown_step(session),
            "note": "MANDATORY close of the singleton session — guaranteed "
                    "teardown so no orphan agent-browser/Chromium survives the "
                    "build (reaper is the host backstop).",
        })
    return plan


# ── ZHC naming (guardrail 2 — carries standing build approval per Skill 44) ──

def ensure_zhc_prefix(name: str, order: int | None = None) -> str:
    """Return `name` guaranteed to start with the canonical UPPERCASE ``ZHC ``
    provenance prefix. The prefix is MANDATORY on every funnel / website / step
    the builder creates — it carries the standing build approval recorded in
    Skill 44's safety_gate. Refuses to silently drop it.

    CASING: the prefix is EMITTED uppercase (``ZHC ``) exactly as Trevor states
    it ("must carry a ZHC prefix … e.g. ZHC test", transcript ~03:28). Matching
    stays case-INSENSITIVE so an already-prefixed name ('ZHC'/'zhc'/'Zhc …') is
    never double-prefixed.

    MULTI-STEP NUMBERING (transcript step 20, ~10:16–10:45): for a multi-step
    funnel Trevor adds each subsequent step and numbers it ``ZHC part 2`` …
    ``ZHC part N``. When ``name`` is omitted/blank and an ``order`` (1-based step
    index) is supplied, this auto-names the step ``ZHC part <order>`` rather than
    the generic ``ZHC untitled`` — so created multi-step steps carry the exact
    transcript naming without the caller hand-typing it.
    """
    name = (name or "").strip()
    if not name:
        if order is not None and int(order) >= 1:
            return f"{ZHC_PREFIX}part {int(order)}"
        return f"{ZHC_PREFIX}untitled"
    if ZHC_PREFIX_RE.match(name):
        return name
    return f"{ZHC_PREFIX}{name}"


def zhc_step_name(name: str | None, order: int) -> str:
    """Canonical name for a created funnel/website STEP (transcript step 20).

    A thin, explicit wrapper over ``ensure_zhc_prefix(name, order)`` for the
    build loop: when the caller supplies a descriptive step name it is
    ZHC-prefixed; when the name is omitted the step is auto-numbered
    ``ZHC part <order>`` (the multi-step naming Trevor demonstrates). ``order`` is
    the 1-based step index within the funnel/website.
    """
    return ensure_zhc_prefix(name or "", order)


# ── Manifest (A0.4) ──────────────────────────────────────────────────────────

def build_manifest(funnel_name: str, surface: str, pages: list[dict]) -> dict:
    """Assemble the build manifest. ``surface`` is 'funnel' or 'website'.
    Each page: {name, path, payload_path, mode}. mode in {direct, iframe}.
    Validates payloads exist and are non-empty (A0.2).

    METHOD DECISION (B3 integration): the ``mode`` for each page is determined
    by ``ghl_method.classify_page(p).method`` (the B3 decision function) UNLESS
    the caller supplies an explicit ``mode`` override in the page dict, in which
    case that explicit override is honoured — but RECORDED alongside the
    classifier's recommendation so the decision is auditable.  When ``ghl_method``
    is not yet installed (B3 bucket not yet shipped), the function falls back to
    the page's own ``mode`` field or ``'direct'``, logging a one-time warning.
    """
    if surface not in ("funnel", "website"):
        raise ValueError("surface must be 'funnel' or 'website'")

    # Lazy import of ghl_method (B3 bucket).  Fail gracefully if not yet present.
    _ghl_method = None
    try:
        import ghl_method as _ghl_method  # type: ignore[import]
    except ImportError:
        pass  # B3 not yet installed — fall back to page-dict mode or 'direct'

    out_pages = []
    for i, p in enumerate(pages, 1):
        path = (p.get("path") or "").strip().lower()
        path = re.sub(r"[^a-z0-9-]+", "-", path).strip("-") or f"step-{i}"

        # METHOD DECISION: use ghl_method.classify_page when available.
        caller_override = p.get("mode")  # explicit caller-supplied mode, or None
        if _ghl_method is not None:
            decision = _ghl_method.classify_page(p)
            classifier_mode = decision.method
        else:
            classifier_mode = caller_override or "direct"

        if caller_override and caller_override != classifier_mode:
            # Caller explicitly chose a different mode from the classifier.
            # Honour the override but record both for auditability.
            mode = caller_override
            mode_source = "caller_override"
        else:
            mode = classifier_mode
            mode_source = "classifier" if _ghl_method is not None else "default"

        if mode not in ("direct", "iframe"):
            raise ValueError(f"page {i}: mode must be direct|iframe, got {mode!r}")

        payload_path = p.get("payload_path", "")
        if mode == "direct":
            if not payload_path or not os.path.isfile(payload_path):
                raise ValueError(f"page {i} ({p.get('name')}): payload_path missing/not a file: {payload_path}")
            if os.path.getsize(payload_path) == 0:
                raise ValueError(f"page {i} ({p.get('name')}): payload is empty")

        page_entry: dict = {
            "order": i,
            # Transcript step 20: created steps carry the ZHC prefix; an unnamed
            # multi-step step is auto-numbered 'ZHC part <i>' (not 'Step i').
            "name": zhc_step_name(p.get("name"), i),
            "path": path,
            "payload_path": payload_path,
            "mode": mode,
            "mode_source": mode_source,
            "iframe_src": p.get("iframe_src", ""),
        }
        if caller_override and caller_override != classifier_mode:
            page_entry["mode_classifier_recommendation"] = classifier_mode
        out_pages.append(page_entry)

    return {
        "funnel_name": ensure_zhc_prefix(funnel_name),
        "surface": surface,
        "pages": out_pages,
        "created_at": int(time.time()),
    }


# ── Ledger (D10 / D12 resume) ─────────────────────────────────────────────────

def _ledger_path(run_id: str, funnel: str, step: str) -> str:
    safe_funnel = re.sub(r"[^A-Za-z0-9_-]+", "_", funnel)
    safe_step = re.sub(r"[^A-Za-z0-9_-]+", "_", step)
    return os.path.join("/tmp", run_id, safe_funnel, f"{safe_step}.json")


def ledger_write(run_id: str, funnel: str, step: str, state: str, extra: dict | None = None) -> str:
    """Record a page's furthest-reached state. Idempotent: only advances; never
    rewinds a page that already reached a later state (unless state==FAILED).

    ``FAILED`` and ``WORKFLOW_LEDGER_STATE`` ('wf-rewired') are accepted but are
    NOT part of the ordered page lifecycle — they are never ordered against the
    LEDGER_STATES sequence (a workflow rewire is a parallel fact about a
    workflow step, not a page-build stage)."""
    if state not in LEDGER_STATES and state not in ("FAILED", WORKFLOW_LEDGER_STATE):
        raise ValueError(f"unknown ledger state: {state}")
    path = _ledger_path(run_id, funnel, step)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prev = {}
    if os.path.isfile(path):
        try:
            prev = json.load(open(path))
        except Exception:
            prev = {}
    prev_state = prev.get("state")
    # Do not rewind a good state with an earlier good state.
    if prev_state in LEDGER_STATES and state in LEDGER_STATES \
            and LEDGER_STATES.index(state) < LEDGER_STATES.index(prev_state):
        state = prev_state
    rec = {"funnel": funnel, "step": step, "state": state,
           "updated_at": int(time.time()), **(extra or {})}
    if prev:
        rec = {**prev, **rec}
    with open(path, "w") as f:
        json.dump(rec, f, indent=2)
    return path


def ledger_read(run_id: str, funnel: str, step: str) -> dict:
    path = _ledger_path(run_id, funnel, step)
    if not os.path.isfile(path):
        return {"state": None}
    try:
        return json.load(open(path))
    except Exception:
        return {"state": None}


def resume_point(run_id: str, manifest: dict) -> list[dict]:
    """Return, per page, the next ledger state to attempt — the resume plan
    (D12). A page already at `published` is done; one at `previewed` resumes at
    publish-if-approved; a FAILED page resumes from its recorded last-good.
    NEVER re-create a step that already exists (state >= created)."""
    plan = []
    funnel = manifest["funnel_name"]
    for pg in manifest["pages"]:
        led = ledger_read(run_id, funnel, pg["name"])
        st = led.get("state")
        if st == "published":
            nxt = "DONE"
        elif st in LEDGER_STATES:
            idx = LEDGER_STATES.index(st)
            nxt = LEDGER_STATES[idx + 1] if idx + 1 < len(LEDGER_STATES) else "DONE"
        elif st == "FAILED":
            nxt = led.get("last_good", "created")
        else:
            nxt = "created"
        plan.append({
            "name": pg["name"], "path": pg["path"], "mode": pg["mode"],
            "current_state": st, "resume_at": nxt,
            "skip_create": st is not None and st != "FAILED",
        })
    return plan


# ── Sub-account hard gate (A2.3) ──────────────────────────────────────────────

# Minimum length of a valid GoHighLevel location_id.  GHL location IDs are
# 20-character alphanumeric strings.  Anything shorter is either a human label
# fragment, a placeholder, or a generic word — all of which are REJECTED so the
# guard can never be tricked into a false match via a too-short target.
_LOCATION_ID_MIN_LEN = 8

# Normalise a location_id candidate: strip whitespace, collapse internal
# whitespace, lowercase.  Only characters that are valid in a GHL location ID
# are kept (alphanumeric + hyphens + underscores).
_LOCATION_ID_CLEAN_RE = re.compile(r"[^A-Za-z0-9_-]")


def _normalise_location_id(value: str) -> str:
    """Strip and lowercase a location_id candidate, removing non-ID characters."""
    return _LOCATION_ID_CLEAN_RE.sub("", value.strip()).lower()


# Generic/placeholder strings that are never valid location IDs.  Exact-match
# after normalisation.
_GENERIC_TARGETS: frozenset[str] = frozenset({
    "test", "demo", "example", "placeholder", "unknown", "none", "null",
    "undefined", "default", "account", "client", "location",
})


class MatchGuard:
    """Return value of subaccount_matches().

    Truth-value (bool) is True only when the match passes all gates, so
    existing callers that do ``if subaccount_matches(...):`` continue to work
    correctly.  The guard also carries structured fields that the build loop
    MUST inspect before any write:

        guard.ok        – bool  – True = safe to proceed
        guard.reason    – str   – human-readable verdict (for logs / errors)
        guard.target_id – str   – normalised location_id that was checked
        guard.matched   – str   – normalised location_id extracted from current
                                  (empty string when ok=False)

    The build loop MUST NOT write to any sub-account when ``guard.ok`` is
    False.  Treat it as a hard STOP, not an advisory warning.
    """

    __slots__ = ("ok", "reason", "target_id", "matched")

    def __init__(self, ok: bool, reason: str,
                 target_id: str = "", matched: str = "") -> None:
        self.ok = ok
        self.reason = reason
        self.target_id = target_id
        self.matched = matched

    # ── bool / truthiness ────────────────────────────────────────────────────
    def __bool__(self) -> bool:
        return self.ok

    # ── dict-like interface so callers can do guard["ok"] if they prefer ─────
    def __getitem__(self, key: str):  # type: ignore[return]
        return getattr(self, key)

    def __repr__(self) -> str:
        return (
            f"MatchGuard(ok={self.ok!r}, reason={self.reason!r}, "
            f"target_id={self.target_id!r}, matched={self.matched!r})"
        )

    def as_dict(self) -> dict:
        """Serialisable representation for ledger / log writes."""
        return {
            "ok": self.ok,
            "reason": self.reason,
            "target_id": self.target_id,
            "matched": self.matched,
        }


def subaccount_matches(current_location_id: str, target: str) -> MatchGuard:
    """Hard gate: verify that *target* is the exact normalised location_id of
    the currently-active GHL sub-account (A2.3 — NO-COMINGLING).

    CHANGED from the old implementation:
      - Operates on **location_id values** (the 20-char alphanumeric GHL ID),
        NOT on human-readable label strings.  Pass the location_id captured
        from the live sub-account selector, not its display name.
      - Uses **exact equality** after normalisation, not substring/contains.
      - Rejects targets that are too short (< _LOCATION_ID_MIN_LEN chars after
        normalisation) or are known generic placeholders.
      - Returns a ``MatchGuard`` object instead of a bare bool.  The guard
        evaluates as ``True``/``False`` in boolean context so existing
        ``if subaccount_matches(...):`` callers remain correct.  The build loop
        MUST check ``guard.ok`` (or use the guard in a boolean expression) and
        MUST NOT proceed on ``False``.

    Args:
        current_location_id: The location_id extracted from the live GHL UI
            sub-account selector (NOT the human label / display name).
        target: The expected location_id for the client being built.

    Returns:
        MatchGuard — always returned, never raises.  ok=False = hard stop.
    """
    if not current_location_id:
        return MatchGuard(
            ok=False,
            reason="REJECT: current_location_id is empty — no active sub-account detected",
        )
    if not target:
        return MatchGuard(
            ok=False,
            reason="REJECT: target location_id is empty — refusing to match against nothing",
        )

    norm_current = _normalise_location_id(current_location_id)
    norm_target = _normalise_location_id(target)

    if not norm_target:
        return MatchGuard(
            ok=False,
            reason=f"REJECT: target {target!r} contains no valid location_id characters after normalisation",
            target_id=norm_target,
        )

    if len(norm_target) < _LOCATION_ID_MIN_LEN:
        return MatchGuard(
            ok=False,
            reason=(
                f"REJECT: target {norm_target!r} is too short ({len(norm_target)} chars, "
                f"minimum {_LOCATION_ID_MIN_LEN}) — generic or label fragment, not a real location_id"
            ),
            target_id=norm_target,
        )

    if norm_target in _GENERIC_TARGETS:
        return MatchGuard(
            ok=False,
            reason=f"REJECT: target {norm_target!r} is a known generic/placeholder value, not a real location_id",
            target_id=norm_target,
        )

    if not norm_current:
        return MatchGuard(
            ok=False,
            reason=f"REJECT: current_location_id {current_location_id!r} contains no valid ID characters after normalisation",
            target_id=norm_target,
        )

    if norm_current == norm_target:
        return MatchGuard(
            ok=True,
            reason=f"PASS: exact location_id match ({norm_target!r})",
            target_id=norm_target,
            matched=norm_current,
        )

    return MatchGuard(
        ok=False,
        reason=(
            f"MISMATCH: active sub-account location_id {norm_current!r} "
            f"!= expected {norm_target!r} — HARD STOP (NO-COMINGLING)"
        ),
        target_id=norm_target,
        matched=norm_current,
    )


# ── Publish guard (A13.1 / guardrail 4) ───────────────────────────────────────

def may_publish(approval: str | None) -> bool:
    """Return True ONLY on an explicit affirmative LIVE answer. Default = draft.
    Any absent/ambiguous/negative answer => False."""
    if not approval:
        return False
    a = approval.strip().lower()
    return a in ("live", "publish", "yes", "approved", "go", "go ahead", "true")


# ── Two-saves invariant (transcript steps 17→18, ~08:31–09:05) ────────────────
# Trevor is explicit: there are TWO saves and BOTH are required, in order —
# (1) SAVE the CODE inside the 'Custom Javascript/HTML' modal (gate 17), THEN
# (2) SAVE the PAGE via the top-right disk icon next to Publish (gate 19).
# Autosave is OFF in the editor, so a missing 2nd save silently loses the page.
# In the REST-autosave path the same two end-states are reached and ledgered:
# the custom-code splice == CODE save (ledger 'code-saved') and the page autosave
# == PAGE save (ledger 'page-saved'), in that order.
CODE_SAVE_GATE = 17          # 'Save' inside the 'Custom Javascript/HTML' modal
PAGE_SAVE_GATE = 19          # top-right disk Save (next to Publish); autosave OFF
TWO_SAVE_SEQUENCE = ("code-saved", "page-saved")  # required ledger order


def emit_two_save_plan(session: str | None = None) -> dict:
    """Emit the ORDERED two-saves browser sub-plan (transcript steps 17→18).

    Glue-not-clicker: this returns a side-effect-free ordered plan the agent
    executes against the live editor (it drives no browser itself). The two
    steps are STRICTLY ORDERED — code save (gate 17) MUST land before page save
    (gate 19) — and each carries the gates.json find-seed so the agent resolves
    the live @ref at runtime (NO invented CSS shipped as fact)."""
    plan = {
        "plan": "two_saves",
        "ok": True,
        "sequence": list(TWO_SAVE_SEQUENCE),
        "steps": [
            {
                "step": "save_code",
                "order": 1,
                "gate": CODE_SAVE_GATE,
                "ledger_target": "code-saved",
                "find": "find role button name Save (within the 'Custom "
                        "Javascript/HTML' modal)",
                "note": "1st SAVE — commit the pasted code inside the code modal "
                        "(gate 17). Wait for the modal's save confirmation.",
            },
            {
                "step": "save_page",
                "order": 2,
                "gate": PAGE_SAVE_GATE,
                "ledger_target": "page-saved",
                "find": "find role button name Save | top-right disk icon",
                "note": "2nd SAVE — the top-right disk Save next to Publish (gate "
                        "19). Autosave is OFF, so this is REQUIRED. Wait for the "
                        "save-confirmation toast (never a fixed sleep).",
            },
        ],
    }
    return _bracket_plan_with_teardown(plan, session)


def assert_two_saves(plan: dict) -> dict:
    """Verify a rest_save plan satisfies the two-saves invariant: the CODE save
    (ledger 'code-saved', the custom-code splice 'edit' step) lands BEFORE the
    PAGE save (ledger 'page-saved', the 'page_autosave' step), and BOTH are
    present. Returns ``{ok, reasons, code_save_step, page_save_step}``; pure
    (raises nothing) so callers can gate on ``ok``."""
    targets = plan.get("ledger_targets") or {}
    step_names = [s.get("step") for s in plan.get("steps", [])]
    reasons: list[str] = []

    code_step = next((s for s, t in targets.items() if t == "code-saved"), None)
    # page-saved OR published (a published page also passed through page-save).
    page_step = next(
        (s for s, t in targets.items() if t in ("page-saved", "published")), None)

    if code_step is None:
        reasons.append("missing CODE save (no step maps to ledger 'code-saved')")
    if page_step is None:
        reasons.append("missing PAGE save (no step maps to 'page-saved'/'published')")
    if code_step is not None and page_step is not None:
        if code_step not in step_names:
            reasons.append(f"code-save step {code_step!r} not in plan steps")
        if page_step not in step_names:
            reasons.append(f"page-save step {page_step!r} not in plan steps")
        if code_step in step_names and page_step in step_names \
                and step_names.index(code_step) >= step_names.index(page_step):
            reasons.append(
                f"ORDER violation: CODE save ({code_step!r}) must precede PAGE "
                f"save ({page_step!r})")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "code_save_step": code_step,
        "page_save_step": page_step,
    }


# ── SEO / AI-search "Content" panel (transcript §2, ~09:05–10:16) ─────────────
# Trevor: "content keywords authors and meta links tags and canonical links are
# added — this is really key." The REST autosave path historically populated
# NONE of this; this run closes that gap. Every rule below is transcript-derived
# and hardened with the audit's overlookedImprovements (length caps, canonical
# format, researched-keywords floor, founder-as-author, explicit language).
SEO_TITLE_MAX = 60            # title <= 60 chars (stricter than GHL's 70 on
                             # purpose — protects search-result truncation; do
                             # NOT loosen to 70)
SEO_DESC_MAX = 155           # meta description <= 155 chars — matches GHL's own
                             # live validator string "Description is under 155
                             # characters." (was 160: a 156-160 char desc passed
                             # build_seo_meta but tripped GHL's in-app validator)
SEO_MIN_DISTINCT_KEYWORDS = 3  # researched-keywords floor (>N distinct, real)
SEO_DEFAULT_LANGUAGE = "en"  # set explicitly — never inherit the GHL default

# Placeholder/junk tokens that are NEVER a real keyword, author, or value. A
# build that leaves any of these in the SEO panel is unfinished — HARD FAIL.
_SEO_PLACEHOLDER_TOKENS: frozenset[str] = frozenset({
    "", "todo", "tbd", "to do", "placeholder", "lorem", "ipsum", "keyword",
    "keywords", "example", "sample", "xxx", "xxxx", "n/a", "na", "none", "null",
    "test", "foo", "bar", "your keyword", "your keywords", "add keywords",
    "founder", "founder name", "your name", "brand", "brand name", "author",
    "description", "title", "company", "your company",
})

# Hosts that must NEVER appear in a canonical URL: a canonical pointing at a
# storage/CDN bucket (Firebase, Google Cloud Storage, msgsndr) is a build bug —
# the canonical is the page's own preview/live domain, not where an asset lives.
_FORBIDDEN_CANONICAL_HOST_FRAGMENTS: tuple[str, ...] = (
    "storage.googleapis.com", "firebasestorage", "firebaseapp.com",
    "appspot.com", "msgsndr", "googleusercontent.com",
)


class SeoValidationError(ValueError):
    """Raised when the SEO panel inputs do not meet the transcript end-state.
    A ValueError subclass so existing ``except ValueError`` callers still catch
    it; the build loop treats it as a HALT (the page is not done)."""


def _is_placeholder_token(value: str) -> bool:
    return (value or "").strip().lower() in _SEO_PLACEHOLDER_TOKENS


def validate_founder_name(founder_name: str | None, *, brand: str | None = None) -> str:
    """P0 pre-flight gate: the SEO ``author`` MUST be the FOUNDER's name
    (transcript §2 — "author MUST be the name of the FOUNDER"). The founder name
    is a REQUIRED build-time input that must be SOURCED from the client / GHL
    location record — never free-typed or fabricated (never-fabricate rule).

    HALT (raise ``SeoValidationError``) when the founder name is missing, a
    placeholder, or equal to the brand (so author can never silently default to
    the brand or blank). Returns the cleaned founder name on success."""
    name = (founder_name or "").strip()
    if not name:
        raise SeoValidationError(
            "HALT (P0): founder_name is REQUIRED — it is the SEO author and a "
            "pre-flight build input sourced from the client / GHL location "
            "record (NEVER free-typed). Re-run with founder_name set.")
    if _is_placeholder_token(name):
        raise SeoValidationError(
            f"HALT (P0): founder_name {name!r} is a placeholder, not a real "
            "founder name. Source it from the client / GHL location record.")
    if brand and name.strip().lower() == brand.strip().lower():
        raise SeoValidationError(
            f"HALT (P0): SEO author {name!r} equals the brand — the author MUST "
            "be the FOUNDER's personal name, not the brand/company name.")
    return name


def _clean_keywords(keywords) -> list[str]:
    """Researched-keywords gate: return a DISTINCT, non-placeholder keyword list
    (case-insensitive de-dup, original order). Accepts a list or a
    comma/newline-separated string. HALT when fewer than
    ``SEO_MIN_DISTINCT_KEYWORDS`` real keywords survive (placeholders/blanks do
    not count) — the transcript demands RESEARCHED keywords, not filler."""
    if isinstance(keywords, str):
        items = re.split(r"[,\n]", keywords)
    else:
        items = list(keywords or [])
    cleaned: list[str] = []
    seen: set[str] = set()
    for k in items:
        k = (k or "").strip()
        if not k or _is_placeholder_token(k):
            continue
        key = k.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(k)
    if len(cleaned) < SEO_MIN_DISTINCT_KEYWORDS:
        raise SeoValidationError(
            f"HALT: researched-keywords gate — need >= {SEO_MIN_DISTINCT_KEYWORDS} "
            f"distinct, non-placeholder keywords; got {len(cleaned)} ({cleaned}). "
            "Use real keyword research, not placeholders.")
    return cleaned


def _validate_canonical(canonical_url: str, expected_host: str | None = None) -> str:
    """Canonical-URL format gate: must be an ABSOLUTE ``https://`` URL with a real
    host that is NOT a storage/CDN bucket. When ``expected_host`` is given, the
    canonical host must match the intended preview/live domain (www-insensitive).
    Returns the canonical on success; HALT otherwise."""
    from urllib.parse import urlparse
    url = (canonical_url or "").strip()
    if not url:
        raise SeoValidationError("HALT: canonicalUrl is empty (transcript: 'really key').")
    p = urlparse(url)
    if p.scheme != "https":
        raise SeoValidationError(
            f"HALT: canonicalUrl must be absolute https:// (got {url!r}).")
    if not p.netloc:
        raise SeoValidationError(f"HALT: canonicalUrl has no host (got {url!r}).")
    host = p.netloc.lower()
    for frag in _FORBIDDEN_CANONICAL_HOST_FRAGMENTS:
        if frag in host:
            raise SeoValidationError(
                f"HALT: canonicalUrl host {host!r} is a storage/CDN URL, not the "
                "page's own preview/live domain.")
    if expected_host:
        eh = expected_host.lower().removeprefix("www.")
        if host.removeprefix("www.") != eh:
            raise SeoValidationError(
                f"HALT: canonicalUrl host {host!r} != intended domain "
                f"{expected_host!r}.")
    return url


def build_seo_meta(
    *,
    title: str,
    description: str,
    keywords,
    founder_name: str,
    canonical_url: str,
    og_image: str,
    language: str = SEO_DEFAULT_LANGUAGE,
    expected_host: str | None = None,
    brand: str | None = None,
    links: list | None = None,
    tags: list | None = None,
) -> dict:
    """Build the validated page ``seoMeta`` object for the SEO/AI-search panel
    (transcript §2). PURE: validates every field and HALTs (``SeoValidationError``)
    on any violation; makes NO network call (the ogImage HTTP-200 re-verify is
    emitted as a plan step expectation, not performed here — same glue-not-clicker
    boundary as the rest of this module).

    Fields + gates (all transcript-derived, hardened by the audit):
      * ``title``        — non-empty, <= 60 chars.
      * ``description``  — non-empty, <= 155 chars (GHL validator: "under 155").
      * ``keywords``     — >= 3 distinct, non-placeholder (researched).
      * ``author``       — := founder_name (P0 founder gate; never brand/blank).
      * ``canonicalUrl`` — absolute https, real host (not storage/CDN; optional
                           host-match to the preview/live domain).
      * ``ogImage``      — absolute https URL (HTTP-200 re-verify is a plan step).
      * ``language``     — explicit (default 'en'), never the GHL default.
      * ``links`` / ``tags`` — passthrough lists (transcript: "links tags").
    """
    title = (title or "").strip()
    description = (description or "").strip()
    author = validate_founder_name(founder_name, brand=brand)  # P0 HALT

    if not title:
        raise SeoValidationError("HALT: seo title is empty.")
    if len(title) > SEO_TITLE_MAX:
        raise SeoValidationError(
            f"HALT: seo title is {len(title)} chars (> {SEO_TITLE_MAX}).")
    if not description:
        raise SeoValidationError("HALT: seo description is empty.")
    if len(description) > SEO_DESC_MAX:
        raise SeoValidationError(
            f"HALT: seo description is {len(description)} chars (> {SEO_DESC_MAX}).")

    kw = _clean_keywords(keywords)
    canon = _validate_canonical(canonical_url, expected_host)

    og = (og_image or "").strip()
    if not og:
        raise SeoValidationError("HALT: ogImage is empty (transcript: add images).")
    if not og.lower().startswith("https://"):
        raise SeoValidationError(
            f"HALT: ogImage must be an absolute https URL (got {og!r}).")

    lang = (language or "").strip() or SEO_DEFAULT_LANGUAGE

    return {
        "title": title,
        "description": description,
        "keywords": kw,
        "author": author,
        "canonicalUrl": canon,
        "ogImage": og,
        "language": lang,
        "links": list(links or []),
        "tags": list(tags or []),
    }


def _visible_copy_text(page_copy: str | None) -> str:
    """Lower-cased, HTML-tag-stripped, whitespace-collapsed copy text for the
    keyword-in-copy gate (H1). Accepts raw HTML (the page body) or plain text."""
    text = re.sub(r"<[^>]+>", " ", page_copy or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def assert_keywords_in_copy(seo_meta: dict | None, page_copy: str | None) -> dict:
    """SEO keyword-in-copy gate (H1, §2.07). Each RESEARCHED SEO keyword MUST
    actually appear in the page's body copy — the classic SEO defect is keywords
    stuffed into the meta panel that never appear in the visible copy. This is the
    mirror of the copy-fidelity gate (P1-4, which asserts approved copy appears in
    the rendered DOM); here we assert the SEO keywords appear in the copy.

    PURE: never raises; returns ``{ok, reasons, missing}``. ``ok=False`` means at
    least one keyword is absent from the copy (or the copy is empty). Matching is
    case-insensitive substring against the tag-stripped copy text."""
    keywords = [k for k in ((seo_meta or {}).get("keywords") or []) if (k or "").strip()]
    copy_text = _visible_copy_text(page_copy)
    if not copy_text:
        return {"ok": False, "missing": list(keywords),
                "reasons": ["page copy is empty — cannot verify SEO keywords appear "
                            "in the body copy (H1, §2.07)"]}
    missing = [k for k in keywords if k.strip().lower() not in copy_text]
    reasons = ([f"SEO keyword(s) absent from page copy: {missing} — each researched "
                "keyword MUST appear in the body copy, not only the SEO meta panel "
                "(H1, §2.07)"] if missing else [])
    return {"ok": not missing, "missing": missing, "reasons": reasons}


def assert_seo_populated(seo_meta: dict | None, *, brand: str | None = None,
                         page_copy: str | None = None) -> dict:
    """End-state gate for the QC scorers (qc-built-funnel.sh /
    qc-ghl-install-pages.sh): re-assert that a saved ``seoMeta`` is fully
    populated to the transcript bar. Returns ``{ok, reasons}`` (pure — never
    raises) so a QC script can score it without crashing. ``ok=False`` means the
    SEO §2 end-state was NOT reached (FAB-QC must not score it >= 8.5).

    ``page_copy`` is OPT-IN (default ``None`` → skipped, existing callers
    unaffected). When supplied (the page's body copy/HTML), the H1 keyword-in-copy
    gate also runs: every researched keyword must appear in the copy, or each
    absent keyword folds into ``reasons`` as a fail."""
    reasons: list[str] = []
    if not isinstance(seo_meta, dict) or not seo_meta:
        return {"ok": False, "reasons": ["seoMeta is absent/empty"]}
    try:
        build_seo_meta(
            title=seo_meta.get("title", ""),
            description=seo_meta.get("description", ""),
            keywords=seo_meta.get("keywords", []),
            founder_name=seo_meta.get("author", ""),
            canonical_url=seo_meta.get("canonicalUrl", ""),
            og_image=seo_meta.get("ogImage", ""),
            language=seo_meta.get("language", SEO_DEFAULT_LANGUAGE),
            brand=brand,
        )
    except SeoValidationError as exc:
        reasons.append(str(exc))
    if (seo_meta.get("language") or "").strip().lower() != SEO_DEFAULT_LANGUAGE:
        reasons.append(
            f"language must be explicitly {SEO_DEFAULT_LANGUAGE!r} "
            f"(got {seo_meta.get('language')!r})")
    # H1 — keyword-in-copy gate (opt-in; only when page_copy is supplied).
    if page_copy is not None:
        kc = assert_keywords_in_copy(seo_meta, page_copy)
        if not kc["ok"]:
            reasons.extend(kc["reasons"])
    return {"ok": not reasons, "reasons": reasons}


# ── Marker-string verification (A12.2 / A13.3 / C3) ───────────────────────────

def verify_url(url: str, marker: str, timeout: int = 20) -> dict:
    """FAST PRE-SCREEN / NON-HYDRATED EMBEDS ONLY — NOT sufficient for pass.

    Fetches ``url`` via bare urllib (no JavaScript execution, no hydration) and
    checks HTTP 200 AND ``marker`` in the RAW response body.  Because this does
    NOT render JavaScript or wait for network-idle, it is suitable ONLY for:

      * a quick pre-screen (is the origin reachable at all?),
      * non-hydrated embed pages whose content is in the initial HTML payload.

    It is NOT a pass criterion for GoHighLevel preview pages: GHL's renderer
    crashes with ``TypeError: Cannot read properties of undefined (reading
    'colors')`` before any content appears, but the HTTP status is still 200 and
    the raw bytes contain the marker from the autosave payload — giving a false
    positive.  Use ``render_check`` (below) for all pass decisions.

    For the canonical pass gate use ``render_check`` which drives a headless
    browser through ``browser_manager.browser_session()`` / ``browser_cmd``,
    waits for network-idle / hydration, captures the RENDERED DOM and a real PNG
    screenshot, and asserts the marker in the RENDERED text — not the raw bytes.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ghl-builder-verify/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.getcode()
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "marker_found": False, "url": url}
    except Exception as e:
        return {"ok": False, "http": None, "marker_found": False, "url": url, "error": str(e)}
    found = bool(marker) and marker in body
    return {"ok": code == 200 and found, "http": code, "marker_found": found, "url": url}


# Minimum rendered-text length for a page to be considered non-blank.
# A page that renders as 500 / blank / error produces near-zero visible text;
# a real content page produces at minimum a few hundred chars of text.
#
# IMPORTANT (P0-1b): this is measured over the SCRIPT/STYLE-STRIPPED text, never
# the raw DOM. A blank GoHighLevel render still ships a large Nuxt hydration
# <script>__NUXT__={...}</script> blob plus inline <style>; counting the raw DOM
# would credit that machinery as "content" and mask a blank page.
MIN_RENDERED_TEXT = 400

# Minimum count of block-level layout elements a real content page carries
# (P1-3 content-richness floor). A blank / error render collapses to ~0 block
# elements; a real funnel/website page has many. This is a STRUCTURAL signal
# that a bare visible-char count cannot spoof (whitespace runs inflate chars but
# not block elements).
MIN_BLOCK_ELEMENTS = 3


# ── Anti-fabricated-pass render-signal helpers (P0-1 / P0-2 / P1-3) ───────────
# These are pure, side-effect-free functions so they are unit-testable WITHOUT a
# browser session (render_check itself needs the singleton agent-browser).

# <script>/<style>/<template>/<noscript> blocks + HTML comments are NON-VISIBLE:
# their bytes never become rendered text. They MUST be removed before any
# visible-text / marker / richness measurement, or a blank page's hydration
# machinery would be miscounted as content (the core fabricated-pass surface).
_NON_VISIBLE_RE = re.compile(
    r"<(script|style|template|noscript)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Orphan opening tag with no matching close (truncated capture) — strip to EOF.
_NON_VISIBLE_OPEN_RE = re.compile(
    r"<(script|style|template|noscript)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*['\"]?\s*([^'\"\s>]+)", re.IGNORECASE)
_HEADLINE_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
_BLOCK_RE = re.compile(
    r"<(?:div|section|p|article|header|footer|main|ul|ol|li|h[1-6]|table|tr|td|form|nav|figure|figcaption|blockquote|aside)\b",
    re.IGNORECASE,
)


def strip_non_visible_html(html: str) -> str:
    """Remove <script>/<style>/<template>/<noscript> blocks and HTML comments.

    The remaining markup still carries every VISIBLE tag (so attribute-borne
    markers and block-element structure survive), but the non-rendered
    machinery — most importantly the large Nuxt ``__NUXT__`` hydration script and
    inline <style> — is gone. This is the substrate for the visible-text length,
    the marker check, and the content-richness count (P0-1b / P0-1c / P1-3)."""
    if not html:
        return ""
    out = _NON_VISIBLE_RE.sub(" ", html)
    out = _NON_VISIBLE_OPEN_RE.sub(" ", out)  # truncated / unclosed tail
    out = _HTML_COMMENT_RE.sub(" ", out)
    return out


def visible_text(html: str) -> str:
    """Script/style-stripped, tag-stripped, entity-decoded, whitespace-collapsed
    visible text of a rendered DOM. Length of this is the blank-page signal."""
    from html import unescape
    stripped = strip_non_visible_html(html)
    text = _TAG_RE.sub(" ", stripped)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def content_richness(stripped_html: str) -> dict:
    """Structural content signals over already-script-stripped markup (P1-3).

    Returns ``img_count`` (number of <img> carrying a non-empty src — our static
    proxy for a loaded image), ``block_count`` (block-level layout elements), and
    ``has_headline`` (any <h1>–<h6>). A blank / error render scores ~0 on all
    three; a real funnel/website page scores high — a signal a bare visible-char
    count (which whitespace can inflate) cannot fabricate."""
    if not stripped_html:
        return {"img_count": 0, "block_count": 0, "has_headline": False}
    img_count = sum(1 for m in _IMG_SRC_RE.finditer(stripped_html) if m.group(1).strip())
    block_count = len(_BLOCK_RE.findall(stripped_html))
    has_headline = bool(_HEADLINE_RE.search(stripped_html))
    return {"img_count": img_count, "block_count": block_count, "has_headline": has_headline}


# Plausible HTTP status range; anything outside is treated as "no status found".
_HTTP_STATUS_RE = re.compile(
    r"(?:\"?status(?:_?code)?\"?\s*[:=]\s*|HTTP/\d(?:\.\d)?\s+|"
    r"(?:response|navigat\w*|http)\b[^0-9\n]{0,24})(\d{3})\b",
    re.IGNORECASE,
)


def parse_nav_http_status(*streams: str) -> int | None:
    """Extract a REAL navigation HTTP status from agent-browser `open` output.

    Scans the navigate command's stdout/stderr for a status code reported next to
    a status/response/navigation/HTTP keyword (handles ``status: 200``,
    ``"statusCode":404``, ``HTTP/1.1 500``, ``response 200``). Returns the int
    status, or ``None`` when nothing plausible is found — render_check then
    FAILS CLOSED (falls back to a real urllib probe, never a byte heuristic).

    A bare 3-digit token with no nearby keyword is ignored on purpose (a page
    body can contain any number); only a keyword-anchored 100–599 counts."""
    for stream in streams:
        if not stream:
            continue
        for m in _HTTP_STATUS_RE.finditer(stream):
            code = int(m.group(1))
            if 100 <= code <= 599:
                return code
    return None


# Console-line severity tokens. agent-browser's `console` emits PLAIN TEXT lines
# (no structured type/level), so a blank/crashed page's ``TypeError`` surfaces as
# text — we MUST parse severity from the text or every console.error is silently
# dropped (the exact fabricated-pass surface P0-1d closes).
_CONSOLE_ERROR_RE = re.compile(
    r"(?:^\s*\[?\s*(?:page\s*)?error\b|^\s*\[?\s*severe\b|"
    r"\b(?:uncaught|unhandled)\b|"
    r"\b(?:Type|Reference|Syntax|Range|Eval|URI)Error\b|"
    r"Cannot\s+read\s+propert|is\s+not\s+a\s+function|is\s+not\s+defined)",
    re.IGNORECASE,
)


def console_line_is_error(text: str) -> bool:
    """True if a plain-text console line denotes a page error / console.error.

    Conservative-but-robust: matches a leading ``error``/``[error]``/``pageerror``
    /``severe`` severity token, an ``Uncaught``/``Unhandled`` prefix, any JS error
    constructor name (TypeError/ReferenceError/…), or the GoHighLevel
    ``Cannot read properties of undefined`` crash. Treats ANY such line as fail
    (P0-1d). A leading keyword anchor keeps benign lines that merely contain the
    word 'error' deeper in a sentence from tripping it."""
    if not text:
        return False
    return bool(_CONSOLE_ERROR_RE.search(text))


def png_blank_report(
    path: str,
    *,
    min_width: int = 64,
    min_height: int = 64,
    single_color_fraction: float = 0.98,
) -> dict:
    """Pixel-inspect a screenshot PNG for a blank render (P0-2).

    Rejects (``blank=True``) when the image is below ``min_width`` × ``min_height``
    (a truncated/failed capture) OR when a single colour covers
    ``single_color_fraction`` (default 98%) or more of the pixels (a white/blank
    error page). Uses Pillow when present for an exact dominant-colour fraction;
    falls back to a header-only IHDR dimension read (dimension reject only) when
    Pillow is unavailable so the helper never hard-depends on it.

    ``determinable=False`` means we could not inspect (missing/corrupt file or no
    decoder) — the caller treats that as NON-fatal (best-effort screenshot), only
    a POSITIVE blank verdict feeds ``ok``."""
    report: dict = {
        "blank": False,
        "determinable": False,
        "reason": "",
        "width": None,
        "height": None,
        "dominant_fraction": None,
    }
    if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
        report["reason"] = "png_missing_or_empty"
        return report

    # Try Pillow (exact dominant-colour fraction + dimensions).
    try:
        from PIL import Image  # type: ignore[import]
    except Exception:  # noqa: BLE001
        Image = None  # type: ignore[assignment]

    if Image is not None:
        try:
            with Image.open(path) as im:
                im.load()
                width, height = im.size
                report["width"], report["height"] = width, height
                report["determinable"] = True
                if width < min_width or height < min_height:
                    report["blank"] = True
                    report["reason"] = f"below_min_dims_{width}x{height}"
                    return report
                rgb = im.convert("RGB")
                total = width * height
                colors = rgb.getcolors(maxcolors=total)  # None if all-unique
                if colors:
                    top = max(c[0] for c in colors)
                    frac = top / total if total else 0.0
                    report["dominant_fraction"] = round(frac, 4)
                    if frac >= single_color_fraction:
                        report["blank"] = True
                        report["reason"] = f"single_color_{report['dominant_fraction']}"
                return report
        except Exception as exc:  # noqa: BLE001
            report["reason"] = f"pillow_error:{type(exc).__name__}"
            # fall through to header-only parse

    # Header-only fallback: parse IHDR for width/height (bytes 16..24).
    try:
        with open(path, "rb") as f:
            head = f.read(33)
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            width = int.from_bytes(head[16:20], "big")
            height = int.from_bytes(head[20:24], "big")
            report["width"], report["height"] = width, height
            report["determinable"] = True
            if width < min_width or height < min_height:
                report["blank"] = True
                report["reason"] = f"below_min_dims_{width}x{height}"
    except Exception as exc:  # noqa: BLE001
        report["reason"] = f"png_header_error:{type(exc).__name__}"
    return report


def render_check(
    preview_url: str,
    marker: str,
    *,
    run_dir: str,
    step: str,
    timeout: int = 45,
    img_src: str | None = None,
    widget_src: str | None = None,
    min_block_elements: int = MIN_BLOCK_ELEMENTS,
    require_headline: bool = False,
    min_images: int = 0,
    inspect_screenshot: bool = True,
) -> dict:
    """THE single source of truth for pass/fail — headless-rendered DOM check.

    This is the ONLY function whose ``ok=True`` result is accepted as a pass
    criterion for a GoHighLevel preview page.  It drives the headless browser
    through the EXISTING ``browser_manager.browser_session()`` + ``browser_cmd``
    machinery (lines 109-126) to:

      1. NAVIGATE to ``preview_url`` and wait for hydration / network-idle.
      2. Capture the RENDERED DOM -> ``<run_dir>/render/<step>.dom.html``.
      3. Capture a real PNG screenshot -> ``<run_dir>/render/<step>.png``.
      4. Collect console + pageerror entries -> ``<run_dir>/render/<step>.console.json``.

    Returns a record with ALL of:
      * ``http`` — navigation HTTP status (from the browser, not urllib).
      * ``marker_in_rendered_dom`` — marker present in the RENDERED DOM file
        (NOT raw shell, NOT Firebase storage, NOT urllib raw bytes).
      * ``render_errors`` — list of ``pageerror`` / ``console.error`` entries.
        The GoHighLevel ``TypeError: Cannot read properties of undefined
        (reading 'colors')`` crash surfaces here.
      * ``dom_path``, ``png_path``, ``console_path`` — absolute paths (cited
        evidence).
      * ``dom_bytes``, ``visible_text_len`` — size signals for blank-page detection.
        ``visible_text_len`` is measured over the SCRIPT/STYLE-STRIPPED text
        (P0-1b), so a blank page's Nuxt hydration <script> blob never counts.
      * ``content_richness`` — {img_count, block_count, has_headline} structural
        signals (P1-3) a whitespace-padded char count cannot fabricate.
      * ``png_blank`` — the screenshot pixel-inspection verdict (P0-2).
      * ``ok`` — True IFF ALL of:
          - ``http == 200`` (a REAL nav status / urllib fallback, never the old
            ``dom_bytes > 100`` heuristic — fail-closed on unknown, P0-1a);
          - ``marker_in_rendered_dom`` (marker present in the SCRIPT-STRIPPED
            DOM, not the raw bytes — P0-1c);
          - ``render_errors == []`` (this ALSO absorbs any console.error /
            pageerror — P0-1d — and a POSITIVE blank-screenshot verdict — P0-2);
          - ``visible_text_len >= MIN_RENDERED_TEXT``;
          - ``content_richness['block_count'] >= min_block_elements`` (P1-3);
          - ``has_headline`` when ``require_headline`` (default False — see note);
          - ``img_count >= min_images`` (default 0 — see note).

    Content-richness floor (P1-3): ``min_block_elements`` (default 3) and the
    stripped visible-text floor harden the bare char count for EVERY page. The
    stronger probe signals — ``require_headline`` and ``min_images`` — default to
    the SAFE values (off / 0) because "every built page carries a headline / a
    loaded <img>" is NOT a confirmed universal invariant (a thank-you / redirect
    page legitimately may not), and the project RULE forbids hard-gating an
    unconfirmed claim. Probe/verification callers that KNOW their page is
    content-rich pass ``require_headline=True`` / ``min_images=1``.

    Optional asserts (called by ghl_verify when present):
      * ``img_src`` — asserted present in the rendered body (image pipeline check,
        B4).  Added to ``render_errors`` as a synthetic entry if missing.
      * ``widget_src`` — asserted present in the rendered body (widget/iframe
        check, B3).  Added to ``render_errors`` if missing.

    STORAGE-MARKER PROXY IS DEAD: this function NEVER inspects Firebase storage,
    raw autosave response bytes, or the urllib raw response.  The only marker
    check is ``marker in <rendered DOM file content>``.  A marker in storage
    proves nothing about rendering.

    SINGLETON BROWSER GATEWAY: must be called inside a
    ``browser_manager.browser_session()`` context — the same requirement as
    ``browser_cmd``.  Callers in ``ghl_verify.verify_page`` acquire the session
    before the verify loop.
    """
    import hashlib
    import shlex
    import subprocess

    render_dir = os.path.join(run_dir, "render")
    os.makedirs(render_dir, exist_ok=True)

    dom_path = os.path.join(render_dir, f"{step}.dom.html")
    png_path = os.path.join(render_dir, f"{step}.png")
    console_path = os.path.join(render_dir, f"{step}.console.json")

    render_errors: list[str] = []
    http_status: int | None = None
    dom_bytes: int = 0
    visible_text_len: int = 0
    marker_in_rendered_dom: bool = False
    dom_content: str = ""
    richness: dict = {"img_count": 0, "block_count": 0, "has_headline": False}
    png_blank: dict = {"blank": False, "determinable": False, "reason": "not_inspected"}

    # ── P2-4: agent-browser version-pin guard ─────────────────────────────────
    # The command spellings below are 0.27.0-specific: `get html html` (not
    # `html --output`), `screenshot` (stdout path, not --output), and `console`
    # (plain text, not `console-log --json`). An unverified upgrade can silently
    # mis-capture HTML, screenshots, or console logs without any subprocess error,
    # which would make the render gate pass on stale/wrong data.
    # Assert the live binary matches the pin BEFORE any subprocess is spawned.
    import browser_manager as _bm_ver  # lazy: avoids import cycle at module level
    _bm_ver.assert_agent_browser_version()

    # ── Drive the headless browser (browser_manager singleton gateway) ─────────
    # We use the browser_cmd machinery which enforces --headed false (D6).
    # The agent-browser command sequence is:
    #   1. navigate to the URL (waits for network-idle by default)
    #   2. capture the rendered HTML
    #   3. take a real PNG screenshot
    #   4. dump console/pageerror log as JSON
    # Since render_check is executed by a Python caller (not emitted as a plan),
    # we invoke the agent-browser CLI directly as a subprocess.  browser_cmd()
    # enforces the singleton session guard so this is safe.
    try:
        # Step 1: navigate to URL (waits for network-idle by default).
        nav_cmd = browser_cmd("open", preview_url)
        # Step 2: capture rendered HTML. agent-browser 0.27.0 uses `get html html`
        # (not `html --output`); stdout is the rendered HTML, redirect to dom_path.
        html_cmd = browser_cmd("get", "html", "html")
        # Step 3: screenshot. agent-browser 0.27.0 `screenshot` with no --output
        # saves to a temp path printed on stdout; capture stdout to know the path.
        shot_cmd = browser_cmd("screenshot")
        # Step 4: console log. agent-browser 0.27.0 uses `console` (not
        # `console-log --json`); output is plain text, not JSON.
        console_cmd = browser_cmd("console")

        # Navigate first.
        nav_result = subprocess.run(
            shlex.split(nav_cmd),
            capture_output=True, text=True, timeout=timeout,
        )
        if nav_result.returncode not in (0,):
            render_errors.append(
                f"browser_cmd failed (exit {nav_result.returncode}): "
                + (nav_result.stderr or nav_result.stdout or nav_cmd)[:400]
            )

        # Capture rendered HTML via `get html html` (stdout → dom_path).
        html_result = subprocess.run(
            shlex.split(html_cmd),
            capture_output=True, text=True, timeout=timeout,
        )
        if html_result.returncode not in (0,):
            render_errors.append(
                f"browser_cmd failed (exit {html_result.returncode}): "
                + (html_result.stderr or html_result.stdout or html_cmd)[:400]
            )
        elif html_result.stdout:
            with open(dom_path, "w", encoding="utf-8") as f:
                f.write(html_result.stdout)

        # Screenshot (saves to agent-browser tmp dir; path printed on stdout).
        shot_result = subprocess.run(
            shlex.split(shot_cmd),
            capture_output=True, text=True, timeout=timeout,
        )
        if shot_result.returncode not in (0,):
            render_errors.append(
                f"browser_cmd failed (exit {shot_result.returncode}): "
                + (shot_result.stderr or shot_result.stdout or shot_cmd)[:400]
            )
        else:
            # Copy from agent-browser tmp to the expected png_path.
            import re as _re_png
            match = _re_png.search(r'/[^\s]+\.png', shot_result.stdout)
            if match:
                tmp_png = match.group(0).strip()
                if os.path.isfile(tmp_png):
                    import shutil
                    shutil.copy2(tmp_png, png_path)

        # Capture console/pageerror. `console` in 0.27.0 outputs plain text.
        console_result = subprocess.run(
            shlex.split(console_cmd),
            capture_output=True, text=True, timeout=30,
        )
        console_entries: list[dict] = []
        raw_console = (console_result.stdout or "").strip()
        if raw_console:
            # agent-browser `console` emits plain-text lines; wrap each as a record.
            for line in raw_console.splitlines():
                line = line.strip()
                if line:
                    console_entries.append({"raw": line, "text": line})

        # Write console log.
        with open(console_path, "w", encoding="utf-8") as f:
            json.dump(console_entries, f, indent=2)

        # Extract pageerror / console.error entries (P0-1d). agent-browser's
        # `console` emits PLAIN TEXT (kind is usually empty), so structured
        # type/level is checked FIRST, then a robust text-severity parse — ANY
        # pageerror / console.error fails the render, never silently dropped.
        for entry in console_entries:
            kind = (entry.get("type") or entry.get("level") or "").lower()
            msg = entry.get("text") or entry.get("message") or entry.get("raw") or ""
            if kind in ("pageerror", "error", "severe") or console_line_is_error(msg):
                render_errors.append(f"{kind or 'console'}: {msg}"[:400])

        # Read the captured DOM.
        if os.path.isfile(dom_path):
            with open(dom_path, encoding="utf-8", errors="replace") as f:
                dom_content = f.read()
            dom_bytes = len(dom_content.encode("utf-8", errors="replace"))
            # P0-1b/c: strip <script>/<style>/<template>/<noscript>/comments
            # BEFORE measuring, so a blank page's Nuxt hydration <script> blob
            # cannot pose as content and the marker must be in VISIBLE markup
            # (not the raw autosave bytes echoed into a hydration <script>).
            stripped_html = strip_non_visible_html(dom_content)
            visible_text_len = len(visible_text(dom_content))
            marker_in_rendered_dom = bool(marker) and marker in stripped_html
            richness = content_richness(stripped_html)
        else:
            render_errors.append(f"dom capture missing: {dom_path}")

        # REAL navigation HTTP status (P0-1a): parse the actual status agent-
        # browser reported on `open`; if none is parseable, FAIL CLOSED via a
        # real urllib status probe — NEVER the old ``dom_bytes > 100`` heuristic
        # (which credited any non-empty error page as 200).
        http_status = parse_nav_http_status(nav_result.stdout, nav_result.stderr)
        if http_status is None:
            fallback = verify_url(preview_url, marker, timeout=min(timeout, 20))
            http_status = fallback.get("http")  # int or None; None => ok=False

        # Screenshot pixel-inspection (P0-2): reject a blank / single-colour /
        # undersized render. Feeds ``ok`` via render_errors. Only a POSITIVE
        # blank verdict fails; an undeterminable capture is non-fatal.
        if inspect_screenshot:
            png_blank = png_blank_report(png_path)
            if png_blank.get("blank"):
                render_errors.append(
                    f"screenshot_blank_render: {png_blank.get('reason') or 'single_color'}"
                )

        # Optional asserts (B4 image, B3 widget).
        if img_src and img_src not in dom_content:
            render_errors.append(f"img_src_not_in_rendered_body: {img_src[:200]}")
        if widget_src and widget_src not in dom_content:
            render_errors.append(f"widget_src_not_in_rendered_body: {widget_src[:200]}")

    except subprocess.TimeoutExpired:
        render_errors.append(f"browser navigation timed out after {timeout}s: {preview_url}")
        http_status = None
    except Exception as exc:  # noqa: BLE001
        render_errors.append(f"render_check exception: {type(exc).__name__}: {exc}"[:400])
        http_status = None

    # ── Compute artifact hashes (provenance) ──────────────────────────────────
    def _sha256(path: str) -> str:
        if not os.path.isfile(path):
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    dom_sha256 = _sha256(dom_path)
    png_sha256 = _sha256(png_path)
    console_sha256 = _sha256(console_path)

    # ── ok requires ALL conditions (any failure already pushed render_errors) ──
    ok = (
        http_status == 200
        and marker_in_rendered_dom
        and render_errors == []
        and visible_text_len >= MIN_RENDERED_TEXT
        and richness["block_count"] >= min_block_elements
        and (not require_headline or richness["has_headline"])
        and richness["img_count"] >= min_images
    )

    return {
        "ok": ok,
        "http": http_status,
        "marker_in_rendered_dom": marker_in_rendered_dom,
        "render_errors": render_errors,
        "dom_path": dom_path,
        "png_path": png_path,
        "console_path": console_path,
        "dom_bytes": dom_bytes,
        "visible_text_len": visible_text_len,
        "content_richness": richness,
        "png_blank": png_blank,
        "dom_sha256": dom_sha256,
        "png_sha256": png_sha256,
        "console_sha256": console_sha256,
        "url": preview_url,
        "step": step,
    }


# ── REST-autosave canvas wire-in (solution doc §5.2) ──────────────────────────
# These three emitters orchestrate the proven ghl_rest_canvas primitives into
# ORDERED, agent-runnable eval-step PLANS. Each returns a plain dict (a plan);
# it makes NO network calls and opens NO browser — the agent runs the steps'
# `eval`/`argv` inside the already-seeded agent-browser (the funnels/builder +
# workflow routes are Cloudflare-WAF gated, so they MUST run in-browser). The
# reused guards are wired verbatim: subaccount_matches() gates every write plan
# (MISMATCH = refuse, no steps emitted), may_publish() keeps autosave DRAFT by
# default, verify_url() is the preview HTTP-200+marker check.
#
# ghl_rest_canvas is imported lazily inside each emitter (mirroring
# ghl_rest_canvas.agent_browser_eval_cmd's lazy import of browser_cmd from here)
# so neither module hard-imports the other at load time.

def _rest_refuse_plan(kind: str, guard: "MatchGuard") -> dict:
    """Return the canonical REFUSED plan when the sub-account hard gate fails.
    No steps are emitted (nothing can run), and the guard verdict is carried for
    the ledger/log. ``ok=False`` is a HARD STOP, never an advisory."""
    return {
        "plan": kind,
        "ok": False,
        "refused": True,
        "reason": guard.reason,
        "guard": guard.as_dict(),
        "steps": [],
    }


def emit_rest_save_plan(
    *,
    page_id: str,
    funnel_id: str,
    location_id: str,
    current_location_id: str,
    locator: dict,
    new_value: str,
    page_version: int,
    page_data: dict,
    preview_url: str,
    marker: str,
    integrations: dict | None = None,
    approval: str | None = None,
    token_js_path: str = "/tmp/ghl-token.js",
    session: str | None = None,
    seo: dict | None = None,
) -> dict:
    """Emit the ordered REST-autosave plan (read→splice→autosave→verify→revert
    baseline), per solution §5.2. The steps the agent runs IN-BROWSER, in order:

      1. ``stage_token`` — write the JWT to ``token_js_path`` via a python-WRITTEN
         JS file (``ghl_rest_canvas.write_token_js_file``); the agent feeds it to
         ``agent-browser eval --stdin`` so the token never passes through bash
         ``${VAR@Q}`` (which mangles a JWT → spurious 401).
      2. ``page_read`` — GET ``/funnels/page/<id>`` (then fetch the signed
         ``pageDataDownloadUrl`` — no auth header — for the editable blob).
      3. ``edit`` — the GAP-1 splice: ``edit_element_customcode`` sets the
         custom-code node's ``rawCustomCode`` to ``new_value`` (e.g. the marker +
         a real ``<img src=<cdn_url>>``). Pure transform — the pristine
         ``page_data`` baseline is preserved for the revert.
      4. ``page_autosave`` — POST the edited blob as a DRAFT (``publish`` is gated
         by ``may_publish(approval)`` — default DRAFT; the live pointer never
         moves while ``pageType`` is ``draft``).
      5. ``verify_preview`` — ``verify_url(preview_url, marker)`` (HTTP 200 AND
         marker in body — never trust no-error).
      6. ``revert_baseline`` — re-POST the pristine baseline as a new draft
         version (byte-identical restore; the live pointer never moves).

    The whole plan is gated behind ``subaccount_matches(current_location_id,
    location_id)`` — on MISMATCH no steps are emitted and ``ok=False`` (HARD
    STOP, NO-COMINGLING). ``ledger_targets`` map each landed step to its ledger
    state (``code-saved`` → ``page-saved`` → ``previewed``); ``published`` only
    when ``may_publish`` is True.

    Args:
        page_id: The funnel/website page id.
        funnel_id: The parent funnel id (autosave body).
        location_id: The TARGET sub-account location id (the gate's expected id).
        current_location_id: The location_id read from the LIVE session
            (``login/current``) — compared against ``location_id`` by the gate.
        locator: ``{"section_idx": int, "element_idx": int}`` — the custom-code
            node to edit.
        new_value: The new ``rawCustomCode`` (marker + real ``<img>``).
        page_version: The numeric ``pageVersion`` read from the page record.
        page_data: The PRISTINE editable blob (preserved as the revert baseline).
        preview_url: ``https://www.<preview-domain>/preview/<page_id>``.
        marker: The verification marker string (must render in the preview).
        integrations: Passthrough integrations object from the read.
        approval: Publish approval — gated by ``may_publish`` (default DRAFT).
        token_js_path: Where the agent writes the staged-token JS file.
        session: Optional agent-browser session; when given, each in-browser step
            carries an ``argv`` so the agent can shell out directly.

    Returns:
        ``{plan, ok, publish, marker, preview_url, location_id, guard, steps,
        ledger_targets}``. On gate MISMATCH: ``{plan, ok:False, refused:True,
        reason, guard, steps:[]}``.
    """
    import ghl_rest_canvas as rc  # lazy: avoids a hard mutual import at load

    guard = subaccount_matches(current_location_id, location_id)
    if not guard.ok:
        return _rest_refuse_plan("rest_save", guard)

    publish = may_publish(approval)

    # Step 3 (pure transform): produce the edited blob now so the autosave step
    # carries the spliced body. The input page_data is NOT mutated (deep-copied
    # inside edit_element_customcode), so it stays the pristine revert baseline.
    edited = rc.edit_element_customcode(page_data, locator, new_value)

    # SEO §2 (transcript ~09:05–10:16): when a `seo` spec is supplied, build the
    # validated seoMeta now (HALTs on any unmet gate) and splice it into the
    # EDITED blob so the autosave carries the SEO end-state. The pristine
    # `page_data` baseline is untouched (revert remains byte-identical to the
    # original, which by design did NOT carry our seoMeta).
    seo_meta = build_seo_meta(**seo) if seo is not None else None
    if seo_meta is not None:
        edited["seoMeta"] = seo_meta

    # 1. Stage the JWT via a python-WRITTEN JS file (NEVER bash ${VAR@Q}).
    stage_step = {
        "step": "stage_token",
        "action": "write_token_js_file",
        "token_js_path": token_js_path,
        "token_global": rc.TOKEN_JS_GLOBAL,
        "note": "agent writes the minted id_token to this JS file via "
                "rc.write_token_js_file(<token>, token_js_path), then feeds it to "
                "`agent-browser eval --stdin` — NEVER bash ${VAR@Q}",
    }

    # 2. READ the page record (then fetch the signed blob URL, no auth header).
    read_step = rc.page_read(page_id, location_id, session=session)
    read_step["step"] = "page_read"

    # 4. AUTOSAVE the edited blob (DRAFT unless may_publish gated it True).
    save_step = rc.page_autosave(
        page_id, edited, funnel_id=funnel_id, page_version=page_version,
        integrations=integrations, publish=publish, session=session,
    )
    save_step["step"] = "page_autosave"

    # 5. VERIFY the preview (HTTP 200 AND marker present — never no-error alone).
    verify_step = {
        "step": "verify_preview",
        "action": "verify_url",
        "url": preview_url,
        "marker": marker,
        "expect": {"ok": True, "http": 200, "marker_found": True},
        "note": "ghl_builder.verify_url(preview_url, marker): HTTP 200 AND marker "
                "in body; a passing preview advances the ledger to 'previewed'",
    }

    # 6. REVERT baseline (byte-identical restore; live pointer never moves).
    revert_plan = emit_revert_plan(
        page_id=page_id, funnel_id=funnel_id, location_id=location_id,
        current_location_id=current_location_id, baseline_page_data=page_data,
        current_page_version=page_version, session=session, _skip_gate=True,
    )

    edit_step = {
        "step": "edit",
        "action": "edit_element_customcode",
        "locator": locator,
        "new_value_len": len(new_value),
        "marker_in_value": marker in new_value,
        "note": "pure JSON splice of sections[s].elements[e].extra.customCode."
                "value.rawCustomCode; pristine baseline preserved for revert",
    }

    steps = [stage_step, read_step, edit_step, save_step]

    # SEO step (ordered AFTER the page autosave — transcript fills the SEO/Content
    # panel after the two saves). Carries the validated seoMeta the autosave
    # already persisted, plus the ogImage HTTP-200 re-verify as a step EXPECTATION
    # (reuse §3 asset-cdn re-verify — performed by the agent, not in this pure
    # builder). Only emitted when a `seo` spec is supplied, so the default plan
    # shape (no SEO) is unchanged.
    if seo_meta is not None:
        steps.append({
            "step": "seo_apply",
            "action": "seo_meta_populated",
            "seo_meta": seo_meta,
            "expect": {
                "seo_populated": True,
                "author_is_founder": True,
                "language": seo_meta["language"],
                "title_max": SEO_TITLE_MAX,
                "description_max": SEO_DESC_MAX,
                "og_image_http_200": seo_meta["ogImage"],
                "canonical_https": seo_meta["canonicalUrl"],
            },
            "note": "SEO/AI-search Content panel end-state (transcript §2): "
                    "title/description/keywords/author(=founder)/canonical/"
                    "ogImage/language populated. ogImage must re-verify HTTP 200 "
                    "(reuse the §3 asset-cdn re-verify) before it is accepted.",
        })

    steps += [verify_step, revert_plan["steps"][0]]

    ledger_targets = {
        "page_autosave": "published" if publish else "page-saved",
        "edit": "code-saved",
        "verify_preview": "previewed",
    }

    plan = {
        "plan": "rest_save",
        "ok": True,
        "publish": publish,
        "marker": marker,
        "preview_url": preview_url,
        "location_id": guard.target_id,
        "guard": guard.as_dict(),
        "steps": steps,
        # Map each LANDED step to the ledger state it proves (the build loop
        # writes these as it confirms each step). 'published' only when publish.
        "ledger_targets": ledger_targets,
    }
    if seo_meta is not None:
        plan["seo"] = seo_meta
    # Self-verify the two-saves invariant (CODE save before PAGE save) — the REST
    # path's edit(code-saved) → page_autosave(page-saved) maps the transcript's
    # two ordered saves. Attached for the build loop / QC to assert on.
    plan["two_saves"] = assert_two_saves(plan)
    return _bracket_plan_with_teardown(plan, session)


def emit_workflow_rewire_plan(
    *,
    location_id: str,
    current_location_id: str,
    workflow_id: str,
    trigger_id: str,
    spec: dict,
    existing_trigger: dict,
    token_js_path: str = "/tmp/ghl-token.js",
    session: str | None = None,
) -> dict:
    """Emit the ordered workflow trigger-rewire plan (read→rewire→re-read), per
    solution §5.2. The steps the agent runs IN-BROWSER, in order:

      1. ``stage_token`` — stage the JWT via a python-written JS file.
      2. ``read_triggers`` — GET ``/workflow/<loc>/<wf>?includeTriggers=true``
         (the ``?includeTriggers=true`` query is LOAD-BEARING — the bare detail
         omits ``triggers[]`` and a verifier reading it wrongly concludes the
         rewire failed).
      3. ``rewire_trigger`` — PUT ``/workflow/<loc>/trigger/<id>`` with the whole
         trigger record + the changed fields (``spec`` merged over
         ``existing_trigger``); the verify re-read (also
         ``?includeTriggers=true``) asserts the changed field(s) are present.

    Gated behind ``subaccount_matches`` (MISMATCH = refuse). On success the build
    loop records ``ledger_write(..., state=WORKFLOW_LEDGER_STATE)`` once the
    re-read confirms the change.

    Returns:
        ``{plan, ok, location_id, workflow_id, guard, steps, ledger_target}``.
        On gate MISMATCH: ``{plan, ok:False, refused:True, reason, guard,
        steps:[]}``.
    """
    import ghl_rest_canvas as rc  # lazy

    guard = subaccount_matches(current_location_id, location_id)
    if not guard.ok:
        return _rest_refuse_plan("workflow_rewire", guard)

    stage_step = {
        "step": "stage_token",
        "action": "write_token_js_file",
        "token_js_path": token_js_path,
        "token_global": rc.TOKEN_JS_GLOBAL,
        "note": "stage the minted id_token via rc.write_token_js_file — never "
                "bash ${VAR@Q}",
    }

    read_step = rc.workflow_read_triggers(location_id, workflow_id, session=session)
    read_step["step"] = "read_triggers"

    rewire_step = rc.workflow_rewire_trigger(
        location_id, workflow_id, trigger_id, spec,
        existing_trigger=existing_trigger, session=session,
    )
    rewire_step["step"] = "rewire_trigger"

    return _bracket_plan_with_teardown({
        "plan": "workflow_rewire",
        "ok": True,
        "location_id": guard.target_id,
        "workflow_id": workflow_id,
        "guard": guard.as_dict(),
        "steps": [stage_step, read_step, rewire_step],
        # The rewire is a parallel ledger fact (not a page stage).
        "ledger_target": WORKFLOW_LEDGER_STATE,
    }, session)


def emit_revert_plan(
    *,
    page_id: str,
    funnel_id: str,
    location_id: str,
    current_location_id: str,
    baseline_page_data: dict,
    current_page_version: int,
    session: str | None = None,
    _skip_gate: bool = False,
) -> dict:
    """Emit the reversibility plan: re-POST the PRISTINE baseline blob as a NEW
    draft version, then assert byte-identical (md5) on the canonical re-read, per
    solution §5.2. The single in-browser step is a DRAFT autosave of the captured
    baseline ``pageData`` — the live ``pageVersion`` pointer never moves; the
    content reads back byte-identical (the proven reversibility bar: live pointer
    unchanged + content byte-identical, NOT zero extra draft rows).

    Gated behind ``subaccount_matches`` (MISMATCH = refuse). ``_skip_gate`` is an
    internal flag used by ``emit_rest_save_plan`` (which already gated the same
    location) to avoid re-checking; external callers always run the gate.

    Returns:
        ``{plan, ok, location_id, guard?, steps, expect}``. The ``expect`` block
        carries the byte-identical assertion contract (the md5 the re-read must
        match). On gate MISMATCH: ``{plan, ok:False, refused:True, ...}``.
    """
    import ghl_rest_canvas as rc  # lazy

    if not _skip_gate:
        guard = subaccount_matches(current_location_id, location_id)
        if not guard.ok:
            return _rest_refuse_plan("revert", guard)
    else:
        guard = None

    body = rc.revert_body(funnel_id, baseline_page_data, current_page_version)
    js = rc.build_fetch_js("POST", rc.page_autosave_path(page_id), body=body)
    baseline_md5 = rc.blob_md5(baseline_page_data)

    revert_step: dict = {
        "step": "revert_baseline",
        "method": "POST",
        "path": rc.page_autosave_path(page_id),
        "url": rc.GHL_BACKEND_ORIGIN.rstrip("/") + rc.page_autosave_path(page_id),
        "body": body,
        "eval": js,
        "expect": {
            "status": 201,
            # The reversibility bar: re-read the canonical record's OWN
            # pageDataDownloadUrl and assert its blob md5 == the pristine
            # baseline md5 (byte-identical), AND that the live pageVersion is
            # unchanged (never published; revert is always a draft).
            "byte_identical_md5": baseline_md5,
            "live_pointer_unchanged": True,
            "verify": "re-read GET /funnels/page/<id>; fetch its pageDataDownloadUrl; "
                      "assert rc.blob_md5(reread) == byte_identical_md5",
        },
    }
    if session:
        revert_step["argv"] = rc.agent_browser_eval_cmd(session, js)

    out: dict = {
        "plan": "revert",
        "ok": True,
        "location_id": location_id,
        "steps": [revert_step],
        "expect": revert_step["expect"],
    }
    if guard is not None:
        out["guard"] = guard.as_dict()
    # Bracket only the STANDALONE revert plan with a teardown. When called as a
    # sub-plan (``_skip_gate=True`` from emit_rest_save_plan, which consumes only
    # steps[0]), the parent plan already carries the single mandatory teardown.
    if not _skip_gate:
        out = _bracket_plan_with_teardown(out, session)
    return out


# ── Gate registry loader (D8 contract) ────────────────────────────────────────

def load_gates(gates_path: str | None = None) -> dict:
    gates_path = gates_path or os.path.join(os.path.dirname(__file__), "gates.json")
    return json.load(open(gates_path))


def runtime_gates(gates_path: str | None = None) -> list[dict]:
    """Return only the gates that MUST be captured at runtime (status=runtime).
    These are the snapshot-gates — the agent snapshots the live DOM and picks
    the @ref. NO invented CSS is ever shipped as fact for these."""
    g = load_gates(gates_path)
    return [x for x in g["gates"] if x.get("status") == "runtime"]


def captured_gates(gates_path: str | None = None) -> list[dict]:
    g = load_gates(gates_path)
    return [x for x in g["gates"] if x.get("status") == "captured"]


# ── CLI (mechanical helpers the agent shells out to) ─────────────────────────

def main() -> int:
    # `browser-cmd` is intercepted BEFORE argparse so pass-through flags like
    # --session / -i reach the emitted agent-browser line verbatim (argparse
    # would otherwise treat them as unknown options of THIS program).
    if len(sys.argv) >= 2 and sys.argv[1] == "browser-cmd":
        try:
            headless_guard()
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n"); return 75
        # browser_cmd() asserts an active session (singleton gateway). Bracket
        # this emit in a browser_session() so the canonical name is used and the
        # mandatory teardown step is emitted on exit.
        import browser_manager
        try:
            with browser_manager.browser_session():
                print(browser_cmd(*sys.argv[2:]))
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n"); return 75
        return 0

    # `browser-session` — print the ONE canonical session name (so a shell caller
    # can `SESSION="$(python3 ghl_builder.py browser-session)"`) plus the
    # mandatory final teardown step, all inside a browser_session() bracket.
    if len(sys.argv) >= 2 and sys.argv[1] == "browser-session":
        try:
            headless_guard()
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n"); return 75
        import browser_manager
        slug = sys.argv[2] if len(sys.argv) >= 3 else None
        with browser_manager.browser_session(slug) as session:
            print(session)
            sys.stderr.write(
                "teardown-step: " + browser_manager.emit_teardown_step(session) + "\n"
            )
        return 0

    ap = argparse.ArgumentParser(description="GoHighLevel builder mechanical helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("zhc"); p.add_argument("name")
    p.add_argument("--order", type=int, default=None,
                   help="1-based step index; an omitted/blank name auto-names the step 'ZHC part <order>'")
    # SEO §2: validate a seoMeta spec (JSON of build_seo_meta kwargs incl. founder_name).
    p = sub.add_parser("seo-check", help="validate a SEO spec (transcript §2); exit 0 = populated, 1 = HALT")
    p.add_argument("spec_path"); p.add_argument("--brand", default=None)
    # Two-saves browser sub-plan (transcript steps 17->18: save CODE then PAGE).
    sub.add_parser("two-saves", help="emit the ordered two-saves browser sub-plan (gate 17 code save -> gate 19 page save)")
    p = sub.add_parser("verify"); p.add_argument("url"); p.add_argument("marker")
    p = sub.add_parser("ledger-write")
    for a in ("run_id", "funnel", "step", "state"):
        p.add_argument(a)
    p.add_argument("--last-good", default=None)
    p = sub.add_parser("resume"); p.add_argument("run_id"); p.add_argument("manifest_path")
    p = sub.add_parser("gates"); p.add_argument("--runtime", action="store_true"); p.add_argument("--captured", action="store_true")
    p = sub.add_parser("may-publish"); p.add_argument("approval", nargs="?", default="")
    p = sub.add_parser("subaccount"); p.add_argument("current"); p.add_argument("target")
    # REST-autosave canvas wire-in plan emitters (solution §5.2). Each reads a
    # JSON spec file (the params include page-data blobs) and prints the plan.
    p = sub.add_parser("rest-save-plan", help="emit the read->splice->autosave->verify->revert plan from a JSON spec")
    p.add_argument("spec_path")
    p = sub.add_parser("wf-rewire-plan", help="emit the workflow read->rewire->re-read plan from a JSON spec")
    p.add_argument("spec_path")
    p = sub.add_parser("revert-plan", help="emit the byte-identical revert plan from a JSON spec")
    p.add_argument("spec_path")
    # R7 fix: the ONE canonical verifier. Delegates to ghl_verify so there is a
    # SINGLE implementation (one source of truth + one consistency guard)
    # reachable from either `ghl_builder.py verify-all` or `ghl_verify.py
    # verify-all`. This kills the dual-writer 6/6-vs-1/6 contradiction: the raw
    # logs/final-preview-verify.json is the source of truth and
    # scorecard/verify-summary.json is a guarded pure reduction of it.
    p = sub.add_parser("verify-all",
                       help="canonical single-pass verify: write logs/final-preview-verify.json "
                            "(raw HTTP+marker per page) then derive scorecard/verify-summary.json "
                            "from it, with a hard consistency guard (FAIL-LOUD on any drift)")
    p.add_argument("run_dir"); p.add_argument("pages_json")
    p.add_argument("--run-id", default=""); p.add_argument("--version", default="")
    p.add_argument("--brand", default="")
    # D6 headless guard helpers.
    sub.add_parser("headless-guard")  # exit 0 = headless OK; exit 75 = headed would open
    # browser-cmd is intercepted before argparse (top of main) so its args pass
    # through verbatim; registered here only so it appears in --help.
    sub.add_parser("browser-cmd", help="emit a headless-forced agent-browser line (--headed false prepended); all following args pass through")
    # browser-session is intercepted before argparse (top of main); registered
    # here only so it appears in --help. Prints the ONE canonical session name +
    # the mandatory teardown step (SINGLETON POOLED BROWSER gateway).
    sub.add_parser("browser-session", help="print the canonical singleton session name (+ mandatory teardown step on stderr)")

    args = ap.parse_args()

    if args.cmd == "zhc":
        print(ensure_zhc_prefix(args.name, args.order)); return 0
    if args.cmd == "seo-check":
        spec = json.load(open(args.spec_path))
        try:
            seo_meta = build_seo_meta(brand=args.brand, **spec)
        except SeoValidationError as e:
            print(json.dumps({"ok": False, "reason": str(e)}, indent=2)); return 1
        res = assert_seo_populated(seo_meta, brand=args.brand)
        print(json.dumps({"ok": res["ok"], "seo_meta": seo_meta,
                          "reasons": res["reasons"]}, indent=2))
        return 0 if res["ok"] else 1
    if args.cmd == "two-saves":
        print(json.dumps(emit_two_save_plan(), indent=2)); return 0
    if args.cmd == "verify":
        res = verify_url(args.url, args.marker)
        print(json.dumps(res)); return 0 if res["ok"] else 1
    if args.cmd == "ledger-write":
        extra = {"last_good": args.last_good} if args.last_good else None
        print(ledger_write(args.run_id, args.funnel, args.step, args.state, extra)); return 0
    if args.cmd == "resume":
        manifest = json.load(open(args.manifest_path))
        print(json.dumps(resume_point(args.run_id, manifest), indent=2)); return 0
    if args.cmd == "gates":
        if args.runtime: print(json.dumps(runtime_gates(), indent=2))
        elif args.captured: print(json.dumps(captured_gates(), indent=2))
        else: print(json.dumps(load_gates(), indent=2))
        return 0
    if args.cmd == "may-publish":
        ok = may_publish(args.approval); print("PUBLISH" if ok else "DRAFT"); return 0 if ok else 1
    if args.cmd == "subaccount":
        guard = subaccount_matches(args.current, args.target)
        print(json.dumps(guard.as_dict(), indent=2))
        return 0 if guard.ok else 1
    if args.cmd in ("rest-save-plan", "wf-rewire-plan", "revert-plan"):
        spec = json.load(open(args.spec_path))
        if args.cmd == "rest-save-plan":
            plan = emit_rest_save_plan(**spec)
        elif args.cmd == "wf-rewire-plan":
            plan = emit_workflow_rewire_plan(**spec)
        else:
            plan = emit_revert_plan(**spec)
        print(json.dumps(plan, indent=2))
        # A refused plan (sub-account MISMATCH) is a hard stop -> non-zero exit.
        return 0 if plan.get("ok") else 1
    if args.cmd == "verify-all":
        # Delegate to the single canonical verifier (one source of truth + the
        # consistency guard live in ghl_verify; ghl_builder just exposes the CLI).
        import ghl_verify  # lazy: keeps ghl_builder importable without ghl_verify
        return ghl_verify.main(
            ["verify-all", args.run_dir, args.pages_json,
             "--run-id", args.run_id, "--version", args.version,
             "--brand", args.brand])
    if args.cmd == "headless-guard":
        try:
            headless_guard()
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n"); return 75
        print("HEADLESS-OK"); return 0
    # `browser-cmd` is handled by the pre-argparse intercept at the top of main().
    return 0


def emit_batch_rest_save_plan(pages: list, *, session: str) -> dict:
    """Delegate to ``parallel_saves.emit_batch_rest_save_plan``.

    This is the canonical entry point for callers who only import ``ghl_builder``.
    All logic lives in ``parallel_saves``; this function is a thin delegation shim
    that ensures ghl_builder remains the single import point for producers.
    """
    import parallel_saves as _ps  # lazy import — parallel_saves is an optional dep

    return _ps.emit_batch_rest_save_plan(pages, session=session)


if __name__ == "__main__":
    sys.exit(main())
