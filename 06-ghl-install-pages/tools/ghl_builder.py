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

ZHC_PREFIX_RE = re.compile(r"^\s*zhc\b", re.IGNORECASE)

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
        -> 'agent-browser --headed false --session acme snapshot -i'"""
    parts = [AGENT_BROWSER_HEADLESS_PREFIX, *(str(a) for a in args)]
    return " ".join(parts)


# ── ZHC naming (guardrail 2 — carries standing build approval per Skill 44) ──

def ensure_zhc_prefix(name: str) -> str:
    """Return `name` guaranteed to start with the `zhc` provenance prefix.
    The prefix is MANDATORY on every funnel / website / step the builder
    creates — it carries the standing build approval recorded in Skill 44's
    safety_gate. Refuses to silently drop it."""
    name = (name or "").strip()
    if not name:
        return "zhc untitled"
    if ZHC_PREFIX_RE.match(name):
        return name
    return f"zhc {name}"


# ── Manifest (A0.4) ──────────────────────────────────────────────────────────

def build_manifest(funnel_name: str, surface: str, pages: list[dict]) -> dict:
    """Assemble the build manifest. `surface` is 'funnel' or 'website'.
    Each page: {name, path, payload_path, mode}. mode in {direct, iframe}.
    Validates payloads exist and are non-empty (A0.2)."""
    if surface not in ("funnel", "website"):
        raise ValueError("surface must be 'funnel' or 'website'")
    out_pages = []
    for i, p in enumerate(pages, 1):
        path = (p.get("path") or "").strip().lower()
        path = re.sub(r"[^a-z0-9-]+", "-", path).strip("-") or f"step-{i}"
        mode = p.get("mode", "direct")
        if mode not in ("direct", "iframe"):
            raise ValueError(f"page {i}: mode must be direct|iframe")
        payload_path = p.get("payload_path", "")
        if mode == "direct":
            if not payload_path or not os.path.isfile(payload_path):
                raise ValueError(f"page {i} ({p.get('name')}): payload_path missing/not a file: {payload_path}")
            if os.path.getsize(payload_path) == 0:
                raise ValueError(f"page {i} ({p.get('name')}): payload is empty")
        out_pages.append({
            "order": i,
            "name": p.get("name") or f"Step {i}",
            "path": path,
            "payload_path": payload_path,
            "mode": mode,
            "iframe_src": p.get("iframe_src", ""),
        })
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


# ── Marker-string verification (A12.2 / A13.3 / C3) ───────────────────────────

def verify_url(url: str, marker: str, timeout: int = 20) -> dict:
    """Fetch `url`; pass iff HTTP 200 AND `marker` appears in the body. Used for
    preview/published/embed verification — never report a page 'good' on
    no-error alone (edge #15)."""
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

    steps = [stage_step, read_step, {
        "step": "edit",
        "action": "edit_element_customcode",
        "locator": locator,
        "new_value_len": len(new_value),
        "marker_in_value": marker in new_value,
        "note": "pure JSON splice of sections[s].elements[e].extra.customCode."
                "value.rawCustomCode; pristine baseline preserved for revert",
    }, save_step, verify_step, revert_plan["steps"][0]]

    return {
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
        "ledger_targets": {
            "page_autosave": "published" if publish else "page-saved",
            "edit": "code-saved",
            "verify_preview": "previewed",
        },
    }


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

    return {
        "plan": "workflow_rewire",
        "ok": True,
        "location_id": guard.target_id,
        "workflow_id": workflow_id,
        "guard": guard.as_dict(),
        "steps": [stage_step, read_step, rewire_step],
        # The rewire is a parallel ledger fact (not a page stage).
        "ledger_target": WORKFLOW_LEDGER_STATE,
    }


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
        print(browser_cmd(*sys.argv[2:])); return 0

    ap = argparse.ArgumentParser(description="GoHighLevel builder mechanical helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("zhc"); p.add_argument("name")
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

    args = ap.parse_args()

    if args.cmd == "zhc":
        print(ensure_zhc_prefix(args.name)); return 0
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


if __name__ == "__main__":
    sys.exit(main())
