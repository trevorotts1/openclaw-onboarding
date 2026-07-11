#!/usr/bin/env python3
"""ghl_pipeline_builder.py — GoHighLevel (Convert and Flow) PIPELINE builder for
Skill 06, driven ENTIRELY by browser control.

WHY BROWSER CONTROL (operator-ratified 2026-07-07)
--------------------------------------------------
GHL exposes NO public API to CREATE a pipeline or CREATE/EDIT pipeline STAGES —
confirmed the same night against GHL's real v2 AND v3 OpenAPI specs (the only
public surface is the read-only ``GET /opportunities/pipelines`` list, which
Skill 44's ``caf opportunities pipelines`` already wraps). Pipeline + stage
creation is therefore UI-only and this walk drives the REAL GHL UI. The
BOUNDARY with Skill 44 (the GHL-API operator):

  • OPPORTUNITY create/update/delete → Skill 44 ``caf opportunities …`` (a real,
    proven public API — needs an existing pipelineId + stageId).
  • PIPELINE + STAGE creation → THIS browser walk (no API exists).

UI FLOW (researched 2026-07-07 against the official HighLevel support portal —
"Step-by-Step Guide: Creating Pipelines" + "Getting Started - Setup Pipelines
and Opportunities"; RESEARCH-SEEDED, runtime-gated — see
``SELECTORS-LIVE-pipeline.md``):

  Sub-account → Opportunities (left rail) → Pipelines (top nav) →
  "Create new pipeline" (top-right) → Pipeline Name (unique per sub-account) →
  per stage: Stage Name + "Add stage" → "Save".
  GHL auto-creates the terminal "Won" / "Lost" stages — never add them manually.

Because NO live selector-lock run has captured this surface yet (unlike the
FORM builder's SELECTORS-LIVE-form.md), every anchor here is RUNTIME-BOUND:
labels are read from the live snapshot by PATTERN (e.g. /Create new pipeline/i,
tolerating GHL's own capitalization drift between "Create new pipeline" and
"Create New Pipeline" in its docs) and clicked role-scoped by the EXACT label
that was actually seen. Every material outcome is POSITIVELY verified (the
v18.1.5 doctrine): the typed pipeline name must render, each typed stage name
must render, the saved pipeline must appear in the RENDERED list (leaf-text
count — never a snapshot substring), and cleanup is a present→delete→absent
proof that refuses to click any affordance it cannot COUNT to exactly one.

TWO-LAYER SPLIT + GLUE DOCTRINE — identical to ``ghl_form_builder.py``: this
module emits ordered agent-browser commands through the SAME proven DO-layer
primitives (imported from ``ghl_form_builder`` — one implementation of the
v18.1.3 text-verb doctrine, the v18.1.4 role+exact disambiguation, the v18.1.1+
poll-with-deadline waits, and the token-only seed rail). It never mutates GHL
state directly and owns only its own ledgers.

MODEL DOCTRINE — client-owned providers, NEVER Anthropic (ladders shared with
the form builder). NO LOGIN CODE — auth is the upstream token-only seed rail.

USAGE
-----
    result = build_pipeline(task, "/tmp/pipeline-run-01")             # dry-run
    result = build_pipeline(task, "/tmp/pipeline-run-01", dry_run=False)
    python3 ghl_pipeline_builder.py --dry-run --location-id LOC123 \
        --pipeline-name "Sales Pipeline" --stages "New Lead,Contacted,Booked Call"
    python3 ghl_pipeline_builder.py --selftest

EXACT-NAME MODE (``--exact-name`` / ``task["exact_name"]``): the pipeline name
is used BYTE-EXACT — the ZHC container prefix is NOT applied. For callers that
bind the created pipeline by name through the read API afterwards, e.g. the
Anthology Engine's standard "Anthology Engine" pipeline (Skill 59's
``anthology_registry.py provision-pipeline`` invokes this builder when the
standard pipeline is absent, then re-reads ``GET /opportunities/pipelines``
and binds ONLY what that read surface shows).

FIRST LIVE RUN (2026-07-08) — PL1.land hardening: the first real walk against
a live sub-account authenticated, router-pushed to the real
Opportunities▸Pipelines route, and confirmed ZERO iframes on the surface, but
then STOPped honestly at PL1.land — no control matching CREATE_PIPELINE_RE
ever rendered. Code inspection found the landing check took exactly ONE
``_snapshot()`` after only a generic "Pipeline" text wait (satisfied by the
page header regardless of whether the create control had hydrated) — the
same single-shot-race bug class the sibling form builder's v18.1.2 fix
(``_wait_text_polling``) already killed. Re-checked GHL's own support docs
(2026-07-08): the button text itself is still documented as unchanged
("Create new pipeline"/"Create New Pipeline"), but the Pipelines screen "now
uses the HighRise design system" (a newer frontend), which is consistent with
a render race rather than label drift. `_land_on_pipelines` now POLLS the
create-control acquisition on our own monotonic deadline
(``_poll_for_create_pipeline_label``) instead of trusting one opaque
snapshot, and a miss now reports RICH diagnostics
(``_diagnose_missing_create_control``) — every 'pipeline'-mentioning text
window actually seen, any unconfirmed alternate-wording hint, and any
possible plan/limit-gating text — so a second failure is actionable instead
of a bare "not found". See ``SELECTORS-LIVE-pipeline.md`` "FIRST LIVE RUN"
section for the full citations and the honest caveat: this fix closes the
CONCRETE bug the code proved (single-snapshot race) and is NOT an
independently live-confirmed fix — it has not yet been proven against a real
account.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap + shared DO-layer import.
# ghl_form_builder soft-imports ALL of its own deps, so importing it is safe in
# every environment (dry-run / selftest / CI need no browser, no skill glue).
# ---------------------------------------------------------------------------
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_form_builder as fb  # noqa: E402  — the ONE proven DO-layer implementation

# U8/U10 — shared phase-checkpoint store + the uniform RUN REPORT emitter.
import ghl_run_state  # noqa: E402
from ghl_run_state import PhaseSpec, run_phase  # noqa: E402

# ── U8: the pipeline builder's declared phase walk ──────────────────────────────
# HONESTLY COARSE: the live pipeline walk (create + stages + verify) is ONE
# `_walk_pipeline_build` call, so it is ONE resumable phase. Splitting it here
# would be a phase list that only LOOKS granular — the ledger would claim resume
# points the code cannot actually stop at. A pipeline is a small object; the THINK
# phases are the cheap part and the walk is the expensive part, and that is exactly
# what the two phases below say.
PIPELINE_PHASES: List[PhaseSpec] = [
    PhaseSpec("plan",       "pipeline plan (THINK)", resumable=False),
    PhaseSpec("preflight",  "preflight gate",        resumable=False),
    PhaseSpec("click_list", "click list",            resumable=False),
    PhaseSpec("pl_walk",    "PL1–PL6 — create pipeline + stages + verify"),
]

StopAndReport = fb.StopAndReport

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
PIPELINE_BUILDER_VERSION = "v0.2.0"

# SPA route for the Pipelines management screen (Opportunities ▸ Pipelines).
# RUNTIME SNAPSHOT-GATED: the official docs place the screen at Opportunities >
# Pipelines; the exact SPA path is confirmed on the first live run. On a route
# miss the walk falls back to the documented UI clicks (Opportunities →
# Pipelines) before STOPping honestly.
PIPELINES_ROUTE_TMPL = "/v2/location/{loc}/opportunities/pipelines"
OPPORTUNITIES_ROUTE_TMPL = "/v2/location/{loc}/opportunities/list"

# Label PATTERNS (GHL's own docs disagree on capitalization; bind at runtime).
CREATE_PIPELINE_RE = re.compile(r"Create\s+[Nn]ew\s+[Pp]ipeline")
ADD_STAGE_RE = re.compile(r"Add\s+[Ss]tage")

# UNCONFIRMED alternate wordings for the create-pipeline control — NOT GHL's
# own docs (help.gohighlevel.com/help.leadconnectorhq.com still show "Create
# new pipeline"/"Create New Pipeline" as of this fix's research pass,
# 2026-07-08 — see SELECTORS-LIVE-pipeline.md "FIRST LIVE RUN" section for the
# citations). These patterns are NEVER clicked and NEVER bound as the create
# label — they exist ONLY so a PL1.land STOP can tell the operator "the screen
# showed X" instead of a bare "not found" if GHL's real UI has drifted further
# than the docs record (docs are known to lag the live product by days).
_ALT_CREATE_LABEL_HINTS: List["re.Pattern[str]"] = [
    re.compile(r"[+]\s*Add\s+[Pp]ipeline"),
    re.compile(r"[+]\s*New\s+[Pp]ipeline"),
    re.compile(r"\bAdd\s+[Pp]ipeline\b"),
    re.compile(r"\bNew\s+[Pp]ipeline\b"),
]
# Community-reported possibility (unconfirmed against official docs): pipeline
# creation could be plan/limit-gated. Purely diagnostic — never a click target.
_LIMIT_GATING_RE = re.compile(r"(upgrade|limit\s+reached|maximum\s+number|plan\s+limit)",
                              re.IGNORECASE)

# Reference stages (docs example flow). GHL auto-creates Won/Lost — NEVER add.
REFERENCE_STAGES: List[str] = ["New Lead", "Contacted", "Booked Call", "Proposal Sent"]
AUTO_STAGES = ("Won", "Lost")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(msg: str) -> None:
    print(f"[ghl_pipeline_builder] {msg}", file=sys.stderr, flush=True)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def find_visible_label(snapshot: str, pattern: "re.Pattern[str]") -> str:
    """Bind a label at RUNTIME: return the EXACT visible text (first match of
    ``pattern``) as it appears in the live snapshot, or '' when absent. This is
    how a docs-known-but-capitalization-uncertain control ('Create new pipeline'
    vs 'Create New Pipeline') is clicked by the label the page ACTUALLY shows —
    never an invented/guessed literal."""
    m = pattern.search(snapshot or "")
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# PL1.land hardening (first live run, 2026-07-08) — poll-with-deadline +
# rich STOP diagnostics.
#
# THE BUG (first live attempt against a real Convert-and-Flow sub-account):
# the walk authenticated, router-pushed to the real Opportunities▸Pipelines
# route, and confirmed ZERO iframes on the surface (so it wasn't a cross-
# origin capture miss) — but the OLD landing check waited only for the
# generic word "Pipeline" (satisfied instantly by the screen's own header/
# breadcrumb, which says "Pipelines" regardless of whether the create control
# has hydrated yet), then took EXACTLY ONE `_snapshot()` and regex-searched
# THAT SINGLE OPAQUE CALL for CREATE_PIPELINE_RE. No poll, no retry — the
# textbook single-shot race this file's own doctrine (borrowed from
# ghl_form_builder's `_wait_text_polling` / `_capture_form_id`) already killed
# for the sibling form builder on 2026-07-07 (v18.1.2, F2's create-modal
# wait). GHL's own support docs (help.gohighlevel.com, refetched 2026-07-08)
# still describe the create control as "Create new pipeline" and note the
# Pipelines screen "now uses the HighRise design system" — a newer frontend
# implementation, which is exactly the kind of surface most likely to
# hydrate its header before its data-dependent action buttons. That is the
# best-evidenced hypothesis (a render race), NOT a wording change — but it is
# NOT independently confirmed live, so the fix below both (1) closes the
# concrete single-snapshot bug the code inspection proved, and (2) makes the
# NEXT failure (if the label truly changed, or moved into a menu) actionable
# instead of a bare "not found".
def _poll_for_create_pipeline_label(session: str, timeout_s: Optional[float] = None,
                                    poll_s: Optional[float] = None) -> "tuple[str, str]":
    """POLL (our OWN monotonic deadline) for the runtime-bound create-pipeline
    control across REPEATED snapshots — never trust one opaque single-shot
    snapshot. Same poll-with-deadline doctrine as `fb._wait_text_polling` /
    `fb._capture_form_id` / this file's own `_save_and_verify` leaf-count poll.
    Returns ``(label, last_snapshot)``: ``label`` is '' on a deadline miss;
    ``last_snapshot`` is ALWAYS the final snapshot taken, so a miss still
    carries full evidence for the STOP diagnostic. Always makes at least one
    attempt, even with a zero/negative budget."""
    budget = fb._TEXT_WAIT_TIMEOUT_S if timeout_s is None else timeout_s
    pause = fb._TEXT_WAIT_POLL_S if poll_s is None else poll_s
    deadline = time.monotonic() + max(0.0, budget)
    snap = ""
    while True:
        snap = fb._snapshot(session)
        label = find_visible_label(snap, CREATE_PIPELINE_RE)
        if label:
            return label, snap
        if time.monotonic() >= deadline:
            return "", snap
        time.sleep(max(0.0, pause))


_PIPELINE_MENTION_RE = re.compile(r".{0,20}[Pp]ipeline.{0,20}")
_MAX_DIAG_CANDIDATES = 12


def _diagnose_missing_create_control(snap: str) -> str:
    """Rich STOP-diagnostic for a PL1.land miss — NEVER a bare 'not found'.
    Lists every distinct 'pipeline'-mentioning text window seen in the FINAL
    polled snapshot (deduped, capped) plus any UNCONFIRMED alternate-wording
    hint that matched (evidence only — never auto-clicked) and any possible
    plan/limit-gating text, so a repeat failure tells the operator exactly
    what the screen showed and why it didn't satisfy CREATE_PIPELINE_RE.
    Never raises."""
    if not snap:
        return "the final polled snapshot was EMPTY — the page rendered no text at all"
    seen: List[str] = []
    for m in _PIPELINE_MENTION_RE.finditer(snap):
        token = " ".join(m.group(0).split())
        if token and token not in seen:
            seen.append(token)
        if len(seen) >= _MAX_DIAG_CANDIDATES:
            break
    hints = [pat.pattern for pat in _ALT_CREATE_LABEL_HINTS if pat.search(snap)]
    hint_note = (f" UNCONFIRMED alternate-wording pattern(s) matched (evidence "
                f"only, NEVER clicked): {hints!r}." if hints else "")
    gate_match = _LIMIT_GATING_RE.search(snap)
    gate_note = (" Possible plan/limit-gating text also present on screen "
                f"(unconfirmed): {gate_match.group(0)!r}." if gate_match else "")
    if not seen:
        return ("no text containing 'pipeline' appeared ANYWHERE in the final "
                "polled snapshot — this is not a label-wording miss, the "
                f"screen itself never rendered pipeline content.{hint_note}{gate_note}")
    return (f"{len(seen)} 'pipeline'-mentioning text window(s) seen across the "
            f"poll but NONE matched /Create\\s+[Nn]ew\\s+[Pp]ipeline/: "
            f"{seen!r}.{hint_note}{gate_note}")


def _resolve_stages(task: dict) -> List[str]:
    """Normalize task['stages'] (trimmed, de-duplicated, Won/Lost stripped —
    GHL creates those automatically and a manual duplicate would corrupt the
    pipeline's terminal semantics)."""
    raw = task.get("stages") or REFERENCE_STAGES
    out: List[str] = []
    for s in raw:
        name = str(s).strip()
        if not name or name in out:
            continue
        if name.lower() in tuple(a.lower() for a in AUTO_STAGES):
            continue
        out.append(name)
    return out


# ---------------------------------------------------------------------------
# THINK layer — plan + click list
# ---------------------------------------------------------------------------
def _build_pipeline_plan(task: dict, stages: List[str]) -> dict:
    location_id = (task.get("location_id") or task.get("GHL_LOCATION_ID")
                   or os.environ.get("GHL_LOCATION_ID", "")).strip()
    # exact_name mode: the CALLER owns a byte-exact contract name that a later
    # find-by-name bind depends on (e.g. the Anthology Engine's standard
    # pipeline "Anthology Engine" — Skill 59 anthology_registry.py binds the
    # created pipeline BY NAME through the read API afterwards, so the ZHC
    # container prefix must NOT be applied). Default stays the fleet ZHC rail.
    exact_name = bool(task.get("exact_name", False))
    raw_name = task.get("pipeline_name", task.get("title", "New Pipeline"))
    name = str(raw_name).strip() if exact_name else fb.ensure_zhc_name(raw_name)
    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "builder_version": PIPELINE_BUILDER_VERSION,
        "status": ("RESEARCH-SEEDED runtime-bound walk — anchors bound live by "
                   "pattern; first live run locks SELECTORS-LIVE-pipeline.md"),
        "location_id": location_id,
        "pipeline_name": name,      # default: ZHC <name>; exact_name: byte-exact
        "exact_name": exact_name,
        "stages": stages,
        "auto_stages": list(AUTO_STAGES),       # GHL adds these itself — never manual
        "cleanup_after_build": bool(task.get("cleanup_after_build", False)),
        "api_boundary": {
            "pipelines_and_stages": "UI-ONLY (no public v2/v3 API — this walk)",
            "opportunities": "Skill 44 `caf opportunities create` (public API; "
                             "needs pipelineId+stageId AFTER this walk)",
            "pipeline_listing": "Skill 44 `caf opportunities pipelines` "
                                "(GET /opportunities/pipelines) — the read-back/"
                                "id-capture surface once the pipeline exists",
        },
        "model_ladders": {"think": fb.THINK_LADDER, "execute": fb.EXECUTE_LADDER,
                          "qc": fb.QC_LADDER},
        "routes": {
            "pipelines": PIPELINES_ROUTE_TMPL.format(loc=location_id or "<LOC>"),
            "opportunities": OPPORTUNITIES_ROUTE_TMPL.format(loc=location_id or "<LOC>"),
            "note": "RUNTIME SNAPSHOT-GATED — fall back to the documented UI "
                    "clicks (Opportunities → Pipelines) on a route miss.",
        },
    }


def _emit_click_list(plan: dict) -> dict:
    steps: List[dict] = []
    n = 0

    def add(phase: str, action: str, target: str, note: str = "", wait: str = "") -> None:
        nonlocal n
        n += 1
        steps.append({"n": n, "phase": phase, "action": action, "target": target,
                      "wait_for": wait, "note": note})

    name = plan["pipeline_name"]
    add("PL1", "navigate", plan["routes"]["pipelines"],
        "Router-push to Opportunities ▸ Pipelines (fallback: click Opportunities "
        "then Pipelines).", wait="Create new pipeline")
    add("PL2", "click", "Create new pipeline",
        "Top-right button; label RUNTIME-BOUND by /Create new pipeline/i "
        "(docs show both capitalizations).", wait="Pipeline Name")
    add("PL3", "fill", f"Pipeline Name = {name!r}",
        "Unique per sub-account (GHL rejects duplicates).")
    for i, st in enumerate(plan["stages"], start=1):
        add("PL4", "stage", f"Stage {i} = {st!r}",
            "Stage Name input; 'Add stage' (runtime-bound) creates the next row. "
            "Typed name POSITIVELY verified to render before proceeding.")
    add("PL5", "click", "Save", "role=button --exact; returns to the Pipelines list.",
        wait=name)
    add("PL6", "verify", f"{name!r} rendered in the Pipelines list",
        "POSITIVE creation proof: rendered leaf-text count >= 1 (never a "
        "snapshot substring). Then capture pipelineId via Skill 44 "
        "`caf opportunities pipelines` (the read API) for opportunity wiring.")
    if plan.get("cleanup_after_build"):
        add("PL7", "cleanup", f"delete pipeline {name!r} + verify gone",
            "TEST RUNS ONLY: present→delete→absent proof; refuses to click any "
            "delete affordance it cannot count to exactly one.")
    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "pipeline_name": name,
        "total_steps": n,
        "dry_run": True,
        "selector_strategy": fb.SELECTOR_STRATEGY,
        "operator_note": (
            "DUMB-BROWSER SCRIPT — execute verbatim; every anchor is runtime-"
            "bound by pattern and every outcome positively verified. Won/Lost "
            "stages are GHL-automatic: never add them manually."),
        "steps": steps,
    }


def _run_preflight(task: dict, plan: dict, stages: List[str]) -> dict:
    checks: List[dict] = []
    stop: Optional[str] = None

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        nonlocal stop
        checks.append({"check": name, "pass": ok, "detail": detail})
        if not ok and hard and stop is None:
            stop = f"{name}: {detail}"

    chk("PL-P1:location_id", bool(plan["location_id"]),
        f"location_id={plan['location_id']!r}")
    if plan.get("exact_name"):
        chk("PL-P2:exact_pipeline_name", bool(plan["pipeline_name"]),
            "exact-name mode: the caller owns the byte-exact contract name "
            f"({plan['pipeline_name']!r}) for a later find-by-name bind — "
            "the ZHC container prefix is deliberately NOT applied")
    else:
        chk("PL-P2:zhc_pipeline_name", plan["pipeline_name"].startswith(fb.ZHC_NAME_PREFIX),
            "pipeline name carries the 'ZHC ' container prefix")
    chk("PL-P3:stages_present", bool(stages), f"{len(stages)} stage(s)")
    manual_terminal = [s for s in (task.get("stages") or [])
                       if str(s).strip().lower() in ("won", "lost")]
    chk("PL-P4:no_manual_won_lost", True,
        f"stripped manual terminal stages: {manual_terminal}" if manual_terminal
        else "no manual Won/Lost (GHL auto-creates them)", hard=False)
    out = {"pass": stop is None, "checks": checks, "ts": _ts()}
    if stop:
        out["stop_reason"] = stop
    return out


# ===========================================================================
# LIVE walk — every anchor runtime-bound, every outcome positively verified.
# ===========================================================================
def _pipelines_route(loc: str) -> str:
    return PIPELINES_ROUTE_TMPL.format(loc=loc)


def _land_on_pipelines(session: str, loc: str) -> str:
    """Land on the Pipelines management screen and return the RUNTIME-BOUND
    exact label of the create button. Primary: SPA router-push to the
    Opportunities▸Pipelines route. Fallback: the documented UI clicks.

    The create-control acquisition POLLS on a deadline across REPEATED
    snapshots (`_poll_for_create_pipeline_label`, first-live-run fix,
    2026-07-08) — never one opaque single-shot snapshot, which is the exact
    bug the first live run's PL1.land STOP diagnosis found (the generic
    `_wait_text_polling(session, "Pipeline")` pre-check below is satisfied
    instantly by the page's own header/breadcrumb; it does NOT prove the
    create control itself has hydrated). STOP honestly, with rich evidence of
    what WAS on screen, when the create control never renders within the
    poll window (the ONLY reliable proof we are on the right screen)."""
    try:
        fb._router_push(session, _pipelines_route(loc), expect_contains="opportunit")
    except StopAndReport:
        # Route drifted — fall back to the documented click path.
        fb._router_push(session, OPPORTUNITIES_ROUTE_TMPL.format(loc=loc),
                        expect_contains="opportunit")
        fb._click(session, "Pipelines")
    fb._wait_text_polling(session, "Pipeline")
    label, snap = _poll_for_create_pipeline_label(session)
    if not label:
        diag = _diagnose_missing_create_control(snap)
        raise StopAndReport(
            "PL1.land",
            "landed via the Opportunities▸Pipelines route (and the documented "
            "click fallback) but no control matching /Create\\s+[Nn]ew\\s+"
            f"[Pp]ipeline/ rendered within {fb._TEXT_WAIT_TIMEOUT_S:.0f}s of "
            "REPEATED polling (never a single static snapshot) — cannot prove "
            f"this is the Pipelines management screen. {diag} "
            f"({fb._capture_entry_diag(session)})")
    return label


def _click_runtime_button(session: str, label: str) -> None:
    """Click a runtime-bound label: role=button + exact accessible name first
    (the v18.1.4 disambiguation), visible-text fallback, rc-checked."""
    cp = fb._click_button(session, label)
    if cp.returncode != 0:
        cp = fb._click(session, label)
    if cp.returncode != 0:
        raise StopAndReport(
            "PL.click", f"the runtime-bound control {label!r} did not accept a "
                        f"click (role+exact rc, then text rc={cp.returncode})")


def _fill_pipeline_name(session: str, name: str) -> None:
    """Fill the Pipeline Name and POSITIVELY verify the typed name renders."""
    cp = fb._fill(session, "Pipeline Name", name)
    if cp.returncode != 0:
        # Placeholder drift ('Enter Pipeline Name' etc.) → type into the focused
        # element (the dialog focuses its name input on open) and verify below.
        fb._ab(session, "keyboard", "type", name, timeout=15)
    if not fb._wait_text_polling(session, name[:24]):
        raise StopAndReport(
            "PL3.name",
            f"typed the pipeline name {name!r} but it never rendered in the "
            "create dialog — the fill did NOT land. STOP (never save an unnamed "
            f"pipeline). ({fb._capture_entry_diag(session)})")


def _add_stage(session: str, stage: str, index: int) -> None:
    """Add ONE stage: bind the 'Add stage' control at runtime, click it, type
    the stage name into the newly-focused stage input, and POSITIVELY verify
    the name renders. The first stage row may pre-exist (GHL seeds the dialog);
    a direct label/placeholder fill is tried first for row 1."""
    if index == 1:
        cp = fb._fill(session, "Stage Name", stage)
        if cp.returncode == 0 and fb._wait_text_polling(session, stage[:24], timeout_s=6):
            return
    snap = fb._snapshot(session)
    add_label = find_visible_label(snap, ADD_STAGE_RE)
    if add_label:
        _click_runtime_button(session, add_label)
    fb._ab(session, "keyboard", "type", stage, timeout=15)
    if not fb._wait_text_polling(session, stage[:24]):
        raise StopAndReport(
            f"PL4.stage:{stage}",
            f"typed stage {stage!r} (row {index}) but it never rendered — the "
            "stage input did not receive the text. STOP "
            f"({fb._capture_entry_diag(session)})")


def _save_and_verify(session: str, name: str) -> int:
    """Save, then POSITIVELY verify the pipeline appears in the RENDERED list
    (leaf-text count — the v18.1.5 doctrine; a dialog echo can't satisfy it
    after the dialog closes). Returns the rendered row count (>=1)."""
    cp = fb._click_button(session, "Save")
    if cp.returncode != 0:
        raise StopAndReport("PL5.save", f"the Save click did not land (rc={cp.returncode})")
    fb._wait_text_polling(session, name[:24])
    deadline = time.monotonic() + fb._TEXT_WAIT_TIMEOUT_S
    rows = -1
    while True:
        rows = fb._eval_leaf_count(session, name)
        if rows > 0 or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    if rows <= 0:
        raise StopAndReport(
            "PL6.verify",
            f"saved but the pipeline {name!r} is NOT positively present in the "
            f"rendered Pipelines list (leaf-count {rows}). STOP — never report "
            f"an unverified creation. ({fb._capture_entry_diag(session)})")
    return rows


# ── cleanup: delete the TEST pipeline + positively verify it is gone ─────────
_DELETE_AFFORDANCE_CANDIDATES = ("Delete", "Delete Pipeline", "Delete pipeline")
_CONFIRM_CANDIDATES = ("Delete", "Confirm", "Yes")

_NAMED_BUTTON_COUNT_JS = (
    "(() => { const q = %s;"
    "  return String(Array.from(document.querySelectorAll('button'))"
    "    .filter(b => (b.textContent || '').trim() === q).length); })()"
)


def _eval_named_button_count(session: str, label: str) -> int:
    """Count visible buttons whose exact trimmed text equals ``label``.
    -1 = unknown (fail-closed, never treated as zero or one)."""
    try:
        raw = fb._eval(session, _NAMED_BUTTON_COUNT_JS % json.dumps(label), timeout=12)
        return int((raw or "").strip())
    except Exception:  # noqa: BLE001
        return -1


def _delete_pipeline(session: str, location_id: str, name: str) -> dict:
    """present→delete→absent proof for the TEST pipeline. Fail-closed at every
    step: requires EXACTLY ONE rendered row for ``name``; only clicks a delete
    affordance it can COUNT to exactly one; the whole-pipeline delete flow is
    runtime-capture (undocumented in the official portal), so any unlocatable
    affordance is an honest not-deleted + operator flag, NEVER a blind click."""
    out: Dict[str, Any] = {"deleted": False, "verified_gone": False,
                           "pipeline_name": name, "method": "browser-pipelines-delete"}
    try:
        _land_on_pipelines(session, location_id)
    except StopAndReport as sr:
        out["reason"] = f"could not land on the Pipelines screen ({sr.reason})"
        return out
    pre = fb._eval_leaf_count(session, name)
    out["pre_delete_rows"] = pre
    if pre == 0:
        out["deleted"] = True
        out["verified_gone"] = True
        out["note"] = f"{name!r} is already positively absent (leaf-count 0)"
        return out
    if pre != 1:
        out["reason"] = (f"expected EXACTLY ONE row for {name!r}, counted {pre} "
                         "(unknown=-1) — refusing to guess a delete target")
        return out
    # The row's own controls are runtime-capture: click the row NAME to open its
    # editor (docs: the pipeline editor exposes stage/pipeline management), then
    # look for a uniquely-countable delete affordance.
    fb._click(session, name)
    fb._wait_text_polling(session, "Pipeline", timeout_s=8)
    clicked = ""
    for cand in _DELETE_AFFORDANCE_CANDIDATES:
        n = _eval_named_button_count(session, cand)
        if n == 1:
            if fb._click_button(session, cand).returncode == 0:
                clicked = cand
                break
        elif n > 1:
            out["reason"] = (f"{n} buttons labeled {cand!r} on screen — ambiguous; "
                             "refusing to click (could hit the wrong control)")
            return out
    if not clicked:
        out["reason"] = (
            "no uniquely-countable delete affordance found (candidates "
            f"{list(_DELETE_AFFORDANCE_CANDIDATES)}) — the whole-pipeline delete "
            "flow is runtime-capture (undocumented); NOT claiming deletion. "
            "OPERATOR REVIEW REQUIRED.")
        return out
    out["delete_affordance"] = clicked
    # Confirm dialog (pattern varies; only ever click a UNIQUELY-countable button).
    for cand in _CONFIRM_CANDIDATES:
        if _eval_named_button_count(session, cand) == 1:
            fb._click_button(session, cand)
            break
    # POSITIVE post-verify: back on the list, poll to zero rendered rows.
    try:
        _land_on_pipelines(session, location_id)
    except StopAndReport:
        pass
    deadline = time.monotonic() + fb._TEXT_WAIT_TIMEOUT_S
    post = -1
    while True:
        post = fb._eval_leaf_count(session, name)
        if post == 0 or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    out["post_delete_rows"] = post
    out["residue_in_list"] = (post != 0)
    if post == 0:
        out["deleted"] = True
        out["verified_gone"] = True
    else:
        out["reason"] = (f"post-delete leaf-count for {name!r} is {post} "
                         "(expected 0) — deletion NOT verified; residue. "
                         "OPERATOR REVIEW REQUIRED.")
    return out


def _walk_pipeline_build(session: str, plan: dict, evidence_root: str,
                         shot_n: List[int], steps_done: List[str],
                         walk_state: Dict[str, Any]) -> dict:
    """The live walk: land → create → name → stages → save → POSITIVE verify.
    ``walk_state`` records the created-name marker AT SAVE TIME so cleanup can
    target it even when a later step raises (the v18.1.5 walk_state doctrine)."""
    loc = plan["location_id"]
    name = plan["pipeline_name"]

    create_label = _land_on_pipelines(session, loc)
    fb._screenshot(session, fb._shot(evidence_root, shot_n, "pl1-pipelines-list"))
    steps_done.append("PL1:land")

    _click_runtime_button(session, create_label)
    if not fb._wait_text_polling(session, "Pipeline Name"):
        raise StopAndReport(
            "PL2.dialog",
            f"clicked {create_label!r} but the create dialog never showed "
            f"'Pipeline Name' ({fb._capture_entry_diag(session)})")
    fb._screenshot(session, fb._shot(evidence_root, shot_n, "pl2-create-dialog"))
    steps_done.append(f"PL2:open:{create_label}")

    _fill_pipeline_name(session, name)
    walk_state["pipeline_name_typed"] = name    # survives a later-step STOP
    steps_done.append("PL3:name")

    for i, st in enumerate(plan["stages"], start=1):
        _add_stage(session, st, i)
        steps_done.append(f"PL4:stage:{st[:24]}")
    fb._screenshot(session, fb._shot(evidence_root, shot_n, "pl4-stages"))

    rows = _save_and_verify(session, name)
    walk_state["pipeline_created"] = True
    steps_done.append("PL5:save")
    steps_done.append(f"PL6:verified-rows:{rows}")
    fb._screenshot(session, fb._shot(evidence_root, shot_n, "pl6-verified"))
    return {"pipeline_name": name, "rendered_rows": rows}


def _live_build(task: dict, plan: dict, click_list: dict, preflight: dict,
                evidence_root: str, started: float,
                state: Optional["ghl_run_state.RunState"] = None) -> dict:
    """Live browser execution: seed → walk → verify → (optional) cleanup —
    mirrors ghl_form_builder._live_build (same session bracket, same STOP +
    always-cleanup contract)."""
    location_id = plan["location_id"]
    os.environ["GHL_LOCATION_ID"] = location_id
    session = fb._canonical_session(location_id)
    shot_n: List[int] = [0]
    steps_done: List[str] = []
    walk_state: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {"attempted": False}
    built: Dict[str, Any] = {}
    stop: Optional[StopAndReport] = None

    fb.browser_manager.headless_guard()                 # type: ignore[union-attr]
    fb.browser_manager.assert_agent_browser_version()   # type: ignore[union-attr]
    _session_cm = fb.browser_manager.browser_session(location_id)  # type: ignore[union-attr]
    _sess = _session_cm.__enter__()
    if _sess:
        session = _sess
    try:
        auth = fb._seed_and_land(session, location_id, evidence_root)
        _write_json(os.path.join(evidence_root, "routing", "auth-receipt.json"),
                    {"landed": auth["landed"], "seeded_at": _ts()})
        built = run_phase(state, "pl_walk", lambda: _walk_pipeline_build(
            session, plan, evidence_root, shot_n, steps_done, walk_state), log=_log)
    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
    finally:
        # Cleanup runs for TEST builds (cleanup_after_build) OR whenever a STOP
        # may have left a partially-created pipeline behind (name was typed) —
        # always a positive proof, never an assumption (v18.1.5 doctrine).
        try:
            if plan.get("cleanup_after_build") or (stop is not None
                                                   and walk_state.get("pipeline_name_typed")):
                cleanup["attempted"] = True
                cleanup.update(_delete_pipeline(session, location_id,
                                                plan["pipeline_name"]))
                fb._screenshot(session, fb._shot(evidence_root, shot_n, "pl7-cleanup"))
        except Exception as exc:  # noqa: BLE001
            cleanup["deleted"] = False
            cleanup["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                _session_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            fb._close_session(location_id)
        _write_json(os.path.join(evidence_root, "routing", "pipeline-cleanup.json"), cleanup)

    duration = time.monotonic() - started
    if stop is not None:
        return {"pages": [], "location_gate_ok": False, "duration_s": duration,
                "pipeline_name": plan["pipeline_name"],
                "pipeline_created": bool(walk_state.get("pipeline_created")),
                "error": str(stop), "stop_step": stop.step, "stop_reason": stop.reason,
                "steps_done": steps_done, "cleanup": cleanup, "preflight": preflight}
    return {"pages": [{"step": "pipeline", "pipeline_name": built.get("pipeline_name")}],
            "location_gate_ok": True, "duration_s": duration,
            "pipeline_name": built.get("pipeline_name", ""),
            "pipeline_created": True, "rendered_rows": built.get("rendered_rows", 0),
            "next": "capture pipelineId via Skill 44 `caf opportunities pipelines` "
                    "for opportunity wiring (the read API)",
            "steps_done": steps_done, "cleanup": cleanup, "preflight": preflight,
            "dry_run": False}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def build_pipeline(task: dict, evidence_root: str, *, dry_run: bool = True,
                   state: Optional["ghl_run_state.RunState"] = None) -> dict:
    """Build a GHL (Convert and Flow) PIPELINE (+stages) via browser-control.
    THINK always runs (plan + click list + preflight); LIVE needs the Skill-6
    tools (ghl_builder / browser_manager, via ghl_form_builder)."""
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    stages = _resolve_stages(task)
    plan = run_phase(state, "plan", lambda: _build_pipeline_plan(task, stages), log=_log)
    preflight = run_phase(state, "preflight",
                          lambda: _run_preflight(task, plan, stages), log=_log)
    click_list = run_phase(state, "click_list", lambda: _emit_click_list(plan), log=_log)
    _write_json(os.path.join(evidence_root, "routing", "pipeline-plan.json"), plan)
    _write_json(os.path.join(evidence_root, "routing", "pipeline-click-list.json"), click_list)
    _write_json(os.path.join(evidence_root, "routing", "pipeline-preflight.json"), preflight)

    if not preflight["pass"]:
        return {"pages": [], "location_gate_ok": False,
                "duration_s": time.monotonic() - started,
                "preflight": preflight, "error": preflight.get("stop_reason")}
    if dry_run:
        _log(f"[dry-run] plan + click list ({click_list['total_steps']} steps) written.")
        return {"pages": [{"step": "pipeline", "pipeline_name": plan["pipeline_name"]}],
                "location_gate_ok": True, "duration_s": time.monotonic() - started,
                "pipeline_name": plan["pipeline_name"], "pipeline_created": False,
                "preflight": preflight, "click_list": click_list, "dry_run": True}

    if fb.ghl_builder is None or fb.browser_manager is None:
        raise RuntimeError(
            "LIVE pipeline build requires the Skill-6 tools/ modules (ghl_builder + "
            "browser_manager) importable on sys.path — run --dry-run/--selftest here "
            "and live from the skill's tools/ dir only.")
    return _live_build(task, plan, click_list, preflight, evidence_root, started,
                       state=state)


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, no skill deps
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import subprocess
    import tempfile
    errors: List[str] = []

    # 1. THINK layer: zhc name, stage normalization, Won/Lost stripped.
    stages = _resolve_stages({"stages": [" New Lead ", "New Lead", "Won", "lost",
                                         "Booked Call", ""]})
    if stages != ["New Lead", "Booked Call"]:
        errors.append(f"stage normalization wrong: {stages}")
    plan = _build_pipeline_plan({"pipeline_name": "Sales Pipeline",
                                 "location_id": "SELFTEST_LOC"}, stages)
    if not plan["pipeline_name"].startswith("ZHC "):
        errors.append(f"pipeline name not ZHC-prefixed: {plan['pipeline_name']!r}")
    if plan["auto_stages"] != ["Won", "Lost"]:
        errors.append("auto stages wrong")

    # 1b. EXACT-NAME mode: byte-exact contract name, no ZHC prefix, preflight
    #     passes on a non-empty name and hard-fails on an empty one.
    task_x = {"pipeline_name": "Anthology Engine", "location_id": "SELFTEST_LOC",
              "exact_name": True}
    plan_x = _build_pipeline_plan(task_x, ["Intake", "Avatar"])
    if plan_x["pipeline_name"] != "Anthology Engine":
        errors.append(f"exact-name mode mangled the name: {plan_x['pipeline_name']!r}")
    if not plan_x.get("exact_name"):
        errors.append("exact-name mode not recorded in the plan")
    pf_x = _run_preflight(task_x, plan_x, ["Intake", "Avatar"])
    if not pf_x["pass"]:
        errors.append(f"exact-name preflight refused a valid contract name: {pf_x}")
    task_e = {"pipeline_name": "   ", "location_id": "SELFTEST_LOC", "exact_name": True}
    plan_e = _build_pipeline_plan(task_e, ["Intake"])
    pf_e = _run_preflight(task_e, plan_e, ["Intake"])
    if pf_e["pass"]:
        errors.append("exact-name preflight accepted an EMPTY pipeline name")

    # 2. Runtime label binder tolerates GHL's capitalization drift.
    for snap_label in ("Create new pipeline", "Create New Pipeline"):
        got = find_visible_label(f"chrome header {snap_label} button", CREATE_PIPELINE_RE)
        if got != snap_label:
            errors.append(f"label binder missed {snap_label!r}: {got!r}")
    if find_visible_label("no create control here", CREATE_PIPELINE_RE):
        errors.append("label binder invented a label")

    # 3. Dry-run output: phases + boundary note + no manual Won/Lost step.
    with tempfile.TemporaryDirectory() as tmp:
        res = build_pipeline({"pipeline_name": "Sales Pipeline",
                              "location_id": "SELFTEST_LOC",
                              "stages": ["New Lead", "Booked Call"]}, tmp)
        cl = res.get("click_list", {})
        phases = {s["phase"] for s in cl.get("steps", [])}
        for want in ("PL1", "PL2", "PL3", "PL4", "PL5", "PL6"):
            if want not in phases:
                errors.append(f"click list missing phase {want}")
        blob = json.dumps(cl)
        if "Won" in json.dumps([s for s in cl.get("steps", []) if s["phase"] == "PL4"]):
            errors.append("a manual Won/Lost stage step leaked into PL4")
        if "caf opportunities pipelines" not in blob:
            errors.append("click list missing the Skill-44 id-capture handoff")

    # 4. WALK happy path (mocked DO layer): runtime-bound create label, name
    #    verified, stages verified, save verified by rendered leaf count.
    calls = {"buttons": [], "fills": [], "typed": [], "leaf": [3 * [0], []]}

    def _cp(rc):
        return subprocess.CompletedProcess(args=[], returncode=rc, stdout="", stderr="")

    orig = {k: getattr(fb, k) for k in
            ("_router_push", "_wait_text_polling", "_snapshot", "_click_button",
             "_click", "_fill", "_ab", "_eval_leaf_count", "_screenshot",
             "_capture_entry_diag", "_TEXT_WAIT_TIMEOUT_S", "_TEXT_WAIT_POLL_S")}
    leaf_after_save = {"n": 0}
    try:
        # Shrink the poll-with-deadline window to keep this NO-NETWORK selftest
        # instant even when run standalone (outside pytest's own autouse
        # timeout-shrinking fixture) — _poll_for_create_pipeline_label (the
        # PL1.land hardening, 2026-07-08) reads these at call time.
        fb._TEXT_WAIT_TIMEOUT_S = 0.3
        fb._TEXT_WAIT_POLL_S = 0.01
        fb._router_push = lambda session, path, expect_contains="": "nav:" + path
        fb._wait_text_polling = lambda session, text, **kw: True
        fb._snapshot = lambda session, timeout=20: "list chrome Create New Pipeline Add stage"
        fb._click_button = lambda session, name, timeout=15: (calls["buttons"].append(name), _cp(0))[1]
        fb._click = lambda session, target, timeout=15: _cp(0)
        fb._fill = lambda session, label, value, timeout=15: (calls["fills"].append((label, value)), _cp(0))[1]
        fb._ab = lambda session, *a, timeout=30, stdin=None: (calls["typed"].append(a), _cp(0))[1]
        fb._eval_leaf_count = lambda session, text: 1
        fb._screenshot = lambda session, path: None
        fb._capture_entry_diag = lambda session: "{}"
        with tempfile.TemporaryDirectory() as tmp2:
            st: Dict[str, Any] = {}
            walk_plan = _build_pipeline_plan(
                {"pipeline_name": "Sales Pipeline", "location_id": "L"},
                ["New Lead", "Booked Call"])
            out = _walk_pipeline_build("s", walk_plan, tmp2, [0], [], st)
            if out["rendered_rows"] != 1 or not st.get("pipeline_created"):
                errors.append(f"walk happy path wrong: {out} / {st}")
            if "Create New Pipeline" not in calls["buttons"]:
                errors.append(f"create click not runtime-bound: {calls['buttons']}")
            if ("Pipeline Name", "ZHC Sales Pipeline") not in calls["fills"]:
                errors.append(f"pipeline name not filled: {calls['fills']}")

        # 5. FAIL-CLOSED: no create control on the landing screen → PL1.land STOP.
        fb._snapshot = lambda session, timeout=20: "some unrelated screen"
        try:
            _land_on_pipelines("s", "L")
            errors.append("missing create control did not STOP")
        except StopAndReport as sr:
            if sr.step != "PL1.land":
                errors.append(f"wrong land STOP step: {sr.step}")
            if "no text containing 'pipeline'" not in sr.reason:
                errors.append(f"PL1.land STOP missing rich diagnostic: {sr.reason}")

        # 5b. POLL RECOVERY (the actual first-live-run bug this fix kills): the
        # create control renders a beat AFTER the generic page chrome — a
        # single static snapshot would miss it, but the poll-with-deadline
        # must catch it on a later attempt within the window.
        _race = {"calls": 0}

        def _racing_snapshot(session, timeout=20):
            _race["calls"] += 1
            if _race["calls"] < 3:
                return "chrome Pipelines header only, list still loading"
            return "list chrome Create new pipeline Add stage"

        fb._snapshot = _racing_snapshot
        label = _land_on_pipelines("s", "L")
        if label != "Create new pipeline" or _race["calls"] < 3:
            errors.append(f"poll recovery failed: label={label!r} calls={_race['calls']}")

        # 5c. RICH DIAGNOSTICS: 'pipeline' text present but never matching the
        # create pattern — the STOP must quote what was actually seen, plus
        # any unconfirmed alt-label hint, rather than a bare 'not found'.
        fb._snapshot = (lambda session, timeout=20:
                        "Pipeline Settings header, + Add Pipeline (beta), no exact match")
        try:
            _land_on_pipelines("s", "L")
            errors.append("near-miss labels did not STOP")
        except StopAndReport as sr:
            if "Pipeline Settings header" not in sr.reason:
                errors.append(f"PL1.land STOP did not quote the seen text: {sr.reason}")
            if "UNCONFIRMED alternate-wording" not in sr.reason:
                errors.append(f"PL1.land STOP missed the alt-label hint: {sr.reason}")

        # 6. FAIL-CLOSED: typed pipeline name never renders → PL3.name STOP.
        fb._snapshot = lambda session, timeout=20: "list chrome Create new pipeline"
        fb._wait_text_polling = lambda session, text, **kw: False
        try:
            _fill_pipeline_name("s", "ZHC Sales Pipeline")
            errors.append("unrendered pipeline name did not STOP")
        except StopAndReport as sr:
            if sr.step != "PL3.name":
                errors.append(f"wrong name STOP step: {sr.step}")

        # 7. CLEANUP fail-closed: ambiguous / unlocatable delete affordances.
        fb._wait_text_polling = lambda session, text, **kw: True
        fb._eval_leaf_count = lambda session, text: 1
        fb._eval = lambda session, js, timeout=12: "2"     # 2 'Delete' buttons
        out7 = _delete_pipeline("s", "L", "ZHC Sales Pipeline")
        if out7["deleted"] is not False or "ambiguous" not in out7.get("reason", ""):
            errors.append(f"ambiguous delete affordance not refused: {out7}")
        fb._eval = lambda session, js, timeout=12: "0"     # none at all
        out7b = _delete_pipeline("s", "L", "ZHC Sales Pipeline")
        if out7b["deleted"] is not False or "OPERATOR REVIEW" not in out7b.get("reason", ""):
            errors.append(f"unlocatable delete affordance not flagged: {out7b}")

        # 8. CLEANUP positive: already absent → clean proof; present→absent → deleted.
        fb._eval_leaf_count = lambda session, text: 0
        out8 = _delete_pipeline("s", "L", "ZHC Sales Pipeline")
        if out8["deleted"] is not True or out8["verified_gone"] is not True:
            errors.append(f"already-absent not treated as positive proof: {out8}")
        seq = {"i": 0}

        def leaf_seq(session, text):
            seq["i"] += 1
            return 1 if seq["i"] <= 1 else 0    # present before, absent after

        fb._eval_leaf_count = leaf_seq
        fb._eval = lambda session, js, timeout=12: "1"     # unique affordances
        out8b = _delete_pipeline("s", "L", "ZHC Sales Pipeline")
        if out8b["deleted"] is not True or out8b["verified_gone"] is not True:
            errors.append(f"present->absent delete not verified: {out8b}")
    finally:
        for k, v in orig.items():
            setattr(fb, k, v)

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — pipeline THINK+walk+cleanup proven "
          "(no network / no browser / no skill deps)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_pipeline_builder",
        description="GHL (Convert and Flow) PIPELINE builder — Skill 06, browser-"
                    "control only (no public API exists for pipeline/stage "
                    "creation). Default: --dry-run.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Write plan + click list WITHOUT browser (default).")
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="Live browser execution (requires Skill 6 tools/).")
    p.add_argument("--selftest", action="store_true", help="Run no-dep self-test and exit.")
    p.add_argument("--evidence-root", default="/tmp/pipeline-run-01", metavar="DIR")
    p.add_argument("--pipeline-name", default="New Pipeline")
    p.add_argument("--stages", default="", help="Comma-separated stage names.")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--exact-name", action="store_true",
                   help="Use --pipeline-name BYTE-EXACT (no ZHC container prefix). "
                        "For callers that bind the created pipeline by name "
                        "afterwards, e.g. the Anthology Engine's standard "
                        "'Anthology Engine' pipeline (Skill 59).")
    p.add_argument("--cleanup-after-build", action="store_true",
                   help="TEST RUNS: delete the pipeline after a verified build.")
    # U8/U10 — identical flags on every Skill-6 builder.
    ghl_run_state.add_run_state_args(p)
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    task = {
        "id": "cli-pipeline-run",
        "pipeline_name": args.pipeline_name,
        "location_id": args.location_id,
        "exact_name": args.exact_name,
        "stages": [s.strip() for s in args.stages.split(",") if s.strip()] or None,
        "cleanup_after_build": args.cleanup_after_build,
    }
    return ghl_run_state.cli_run(
        args, builder="ghl_pipeline_builder", specs=PIPELINE_PHASES,
        script_path=__file__, task=task, build=build_pipeline,
        ok_key="location_gate_ok", url_key="pipeline_name",
        argv=list(argv if argv is not None else sys.argv[1:]),
    )


if __name__ == "__main__":
    sys.exit(main())
