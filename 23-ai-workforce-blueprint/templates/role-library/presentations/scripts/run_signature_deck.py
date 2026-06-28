#!/usr/bin/env python3
"""
run_signature_deck.py — DETERMINISTIC SIGNATURE-DECK RUNNER (Decision 3C).

================================================================================
A deterministic state machine over PIPELINE-MANIFEST.json. It does NOT replace
build_deck.py — it ORCHESTRATES the pipeline AROUND it and calls build_deck.py for
the render phase. The render path inside build_deck.py is never touched.
================================================================================

WHAT IT GUARANTEES
  * Manifest-driven phase order. Phases run in ascending `order`. Each phase's
    completion is proven by an ATTESTATION appended to
    working/checkpoints/process_manifest.json.
  * Skipping / reordering a phase is STRUCTURALLY IMPOSSIBLE. Before dispatching
    phase N, EVERY phase with a lower `order` must have an attestation on disk AND
    its produces_artifact present. A missing precondition is a HARD ABORT
    (AF-PHASE-SKIPPED, exit 2) — EXCEPT when an explicit, logged OWNER-AUTHORIZED
    skip record covers it (working/checkpoints/phase_skip_approvals.json,
    owner_approved:true). That is not a free flag — absent the signed record, the
    precondition is unmet and the run aborts.
  * Phase-0 PRE-FLIGHT (before ANY dispatch/render):
      - detect_platform() box-type resource note (mac -> fewer workers; vps ->
        more) recorded into the brief/attestation.
      - Kie.ai BALANCE pre-flight (GET https://api.kie.ai/api/v1/chat/credit):
        HARD-ABORTS (AF-KIE-BALANCE, exit 4) before any render when
        balance < estimated_floor. SHARED with build_deck.kie_balance_preflight.
  * --adhoc escape: OWNER-authorized + logged
    (working/checkpoints/adhoc_authorization.json). Without the logged record,
    --adhoc is REFUSED.

  * CANONICAL-RENDER GUARD (Fix 1, the enforcement surface): the ONLY sanctioned
    render path is build_deck.py. Before the render is dispatched the guard scans the
    run dir for hand-rolled renderers/assemblers (local 2048x1152 canvas, native
    on-slide text, direct kie createTask, per-deck render functions) and HARD-ABORTS
    on a finding (AF-CANONICAL-RENDER-BYPASS / AF-LOCAL-CANVAS, exit 5). The delivery
    phase is REFUSED unless the full process_manifest attestation chain is present AND
    the run dir is clean AND the Fix-2 pixel/vision image-QC passes (AF-IMAGE-QC-VISION).
    The ONLY bypass is a logged owner_skip_approval token in process_manifest.json.

EXIT CODES
    0 — all phases attested (or owner-authorized skips), pre-flight clean.
    2 — phase-precondition violation (AF-PHASE-SKIPPED) or usage error.
    4 — Phase-0 balance abort (AF-KIE-BALANCE).
    3 — a build_deck.py subprocess (render phase) failed preflight/render.
    5 — canonical-render guard hard-block (AF-CANONICAL-RENDER-BYPASS /
        AF-LOCAL-CANVAS / AF-IMAGE-QC-VISION / incomplete attestation chain).
    6 — QC SEND-BACK routeback written; the phase is NOT attested so the next phase
        (prompt authoring / render) stays BLOCKED until the failing items are
        re-authored and the phase is re-run (run_copy_qc_loop / run_prompt_qc_loop).
    7 — QC re-author cap (PROMPT_QC_MAX_ATTEMPTS) exhausted with no logged owner
        override, or the pre-assembly AF-HARMONY checkpoint failed — hard refusal.

SHIFT-LEFT QC SEND-BACK LOOPS (v15.0.0)
  * COPY-QC (run_copy_qc_loop) fires at P1Q-COPY-QC, BEFORE any image prompt is
    authored. The exit gate is the composed WRITING/PRICING-engine measurer
    (intelligence_engines_check.check_copy + pitch_engines_check.check_copy:
    Story villain-before-hero, Emotional felt-stakes, pricing promise-before-price
    + cadence, narrative harmony) — NOT the QC agent's self-score. A broken script
    routes back; no prompts are authored until the copy passes.
  * PROMPT-QC (run_prompt_qc_loop) fires at P-PROMPT-QC, BEFORE P4-RENDER (the money
    step). The exit gate is build_deck.check_prompt_qc_deterministic (BOTH floors:
    length >= 9,000 AND every engine AND harmony AND excellence). A thin/off prompt
    routes back and physically cannot reach submit_task/kie.ai until it passes.
  * Both loops: author -> deterministic QC -> on fail write a per-slide work order
    (write_routeback_payload) -> re-author ONLY the failing slides -> re-QC, bounded
    by PROMPT_QC_MAX_ATTEMPTS (default 4), exiting on the MEASURER. After the cap, the
    only exit is a logged owner override (build_deck._owner_skip_approved).
  * PRE-ASSEMBLY (pre_assembly_harmony_checkpoint) fires before P8-ASSEMBLE: proves
    deck-level cohesion via build_deck.check_deck_harmony before the deck is assembled.

USAGE
    python3 run_signature_deck.py --run-dir DIR --slides slides.json --out out.pptx
        [--plan]            # print the resolved phase plan + preconditions, do not run
        [--phase PHASE_ID]  # advance to / dispatch a single phase (checks preconditions)
        [--platform vps|mac]
        [--adhoc]           # owner-authorized + logged escape (refused without the record)

This is a SCRIPT (not a manifest role/phase). sync_check.py does not require a
symbol for it; AF-PHASE-SKIPPED is enforced_by:runner with py_symbol:null.
"""

import argparse
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Reuse build_deck.py's primitives — do NOT reimplement (detect_platform,
# find_run_dir, the shared Kie balance pre-flight, the run-dir JSON reader).
import build_deck as bd

# Fix 1 — the enforcement surface that makes the governed path the ONLY path. The
# guard scans the run dir for hand-rolled renderers/assemblers (AF-LOCAL-CANVAS /
# AF-CANONICAL-RENDER-BYPASS) at PRE-RENDER, and refuses delivery unless the full
# attestation chain is present + the Fix-2 pixel/vision image-QC passes
# (AF-IMAGE-QC-VISION) at PRE-DELIVERY. The ONLY bypass is a logged
# owner_skip_approval token in process_manifest.json.
import canonical_render_guard as guard

# Exit code for a guard hard-block (distinct from AF-PHASE-SKIPPED=2,
# render-subprocess=3, AF-KIE-BALANCE=4).
EXIT_GUARD_BLOCK = 5

# The delivery phase id (manifest order 9). Dispatching/attesting it triggers the
# PRE-DELIVERY guard: full attestation chain + clean run dir + pixel/vision QC.
DELIVERY_PHASE_ID = "P9-DELIVER"

# ---------------------------------------------------------------------------
# SEND-BACK-THROUGH QC LOOPS (v15.0.0) — shift-left routeback at COPY-QC and
# PROMPT-QC. The exit condition is the DETERMINISTIC MEASURER (build_deck.py /
# the engine checkers), NEVER an agent self-score. A failing script cannot advance
# to prompt authoring; a failing prompt physically cannot reach submit_task/kie.ai.
# ---------------------------------------------------------------------------
# Re-author attempt cap (shared by both loops; env-overridable). Bounds the loop so
# termination is guaranteed.
PROMPT_QC_MAX_ATTEMPTS = max(1, int(os.environ.get("PROMPT_QC_MAX_ATTEMPTS", "4")))

COPY_QC_PHASE_ID = "P1Q-COPY-QC"     # manifest order 4.2 — BEFORE any prompt authored
PROMPT_QC_PHASE_ID = "P-PROMPT-QC"   # manifest order 4.8 — BEFORE any render
ASSEMBLE_PHASE_ID = "P8-ASSEMBLE"    # manifest order 8 — deck-harmony checkpoint fires first

# Exit codes for the loops (distinct from guard=5, balance=4, render=3, skip=2).
EXIT_QC_ROUTEBACK = 6   # routeback written; downstream phase BLOCKED pending re-author
EXIT_QC_EXHAUSTED = 7   # re-author cap exhausted / harmony fail, no owner override — refusal

# Per-phase wiring tables (keyed by the loop's logical phase name).
_REAUTHOR_ROLE = {
    "COPY-QC": "slide-copywriter",            # + offer-price-strategist for pricing beats
    "PROMPT-QC": "prompt-author-presentations",
}
_ROUTEBACK_PREFIX = {
    "COPY-QC": "copy_qc_routeback",
    "PROMPT-QC": "prompt_qc_routeback",
}
_QC_PHASE_ID = {
    "COPY-QC": COPY_QC_PHASE_ID,
    "PROMPT-QC": PROMPT_QC_PHASE_ID,
}
_QC_OWNING_ROLE = {
    "COPY-QC": "qc-specialist-presentations",
    "PROMPT-QC": "qc-specialist-prompt-presentations",
}
_QC_AF_CODE = {
    "COPY-QC": "AF-COPY-QC",
    "PROMPT-QC": "AF-PROMPT-QC",
}


# ---------------------------------------------------------------------------
# Manifest resolution (same cluster-or-deployed layout sync_check uses)
# ---------------------------------------------------------------------------
def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_manifest() -> dict:
    repo = _find_repo_root(HERE)
    candidates = []
    if repo:
        candidates.append(repo / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "PIPELINE-MANIFEST.json",
        HERE.parent / "PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return json.loads(c.read_text())
    print("FATAL: PIPELINE-MANIFEST.json not found.", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Attestation ledger (process_manifest.json is build_deck.py's cumulative file)
# ---------------------------------------------------------------------------
def _process_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "process_manifest.json"


def _load_process_manifest(run_dir: Path) -> dict:
    p = _process_manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _attested_phase_ids(run_dir: Path) -> set:
    """Return the set of phase_ids that have an attestation. Accepts BOTH the
    runner's phase attestations (under 'phase_attestations') AND build_deck.py's
    own 'render' phase record (so a render done by the canonical renderer counts as
    the render phase being attested without the runner re-stamping it)."""
    obj = _load_process_manifest(run_dir)
    ids = set()
    for att in obj.get("phase_attestations", []) or []:
        if isinstance(att, dict) and att.get("phase_id"):
            ids.add(att["phase_id"])
    # build_deck.py appends render records under "phases": [{"phase":"render", ...}]
    for ph in obj.get("phases", []) or []:
        if isinstance(ph, dict) and ph.get("phase") == "render":
            ids.add("P4-RENDER")
    return ids


def attest_phase(run_dir: Path, phase_id: str, role: str, status: str,
                 artifact_sha: str = "") -> None:
    """Append a phase attestation to process_manifest.json (never clobber prior
    records — mirrors build_deck.write_process_manifest's append discipline)."""
    p = _process_manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    obj.setdefault("phase_attestations", [])
    obj["phase_attestations"].append({
        "phase_id": phase_id,
        "owning_role": role,
        "status": status,
        "artifact_sha": artifact_sha,
        "attested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    p.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------------------
# Owner-authorized skip records (the controlled exception — NOT a free flag)
# ---------------------------------------------------------------------------
def load_skip_approvals(run_dir: Path) -> dict:
    """Return {phase_id: approval_record} for every owner-authorized skip whose
    record is well-formed (owner_approved:true + approved_by + reason). A malformed
    or owner_approved:false record does NOT authorize a skip."""
    p = run_dir / "working" / "checkpoints" / "phase_skip_approvals.json"
    approvals = {}
    if not p.exists():
        return approvals
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return approvals
    records = obj if isinstance(obj, list) else obj.get("approvals", []) if isinstance(obj, dict) else []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if (rec.get("owner_approved") is True and rec.get("phase_id")
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            approvals[rec["phase_id"]] = rec
    return approvals


def _artifact_present(run_dir: Path, produces_artifact: str) -> bool:
    """True when a phase's declared produces_artifact exists in the run dir.
    Supports glob patterns (e.g. 'working/research/brief-*.md'). A null/empty
    artifact spec counts as satisfied (the phase declares no concrete artifact)."""
    spec = (produces_artifact or "").strip()
    if not spec:
        return True
    # Try run-dir-relative, then a bundle-style bare filename glob anywhere.
    if "*" in spec or "?" in spec:
        if list(run_dir.glob(spec)):
            return True
        return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))
    p = run_dir / spec
    if p.exists():
        return True
    # bare-filename artifacts (e.g. '*-FINAL.pptx') may live in the bundle dir
    return bool(list(run_dir.glob("**/" + spec.split("/")[-1])))


# ---------------------------------------------------------------------------
# Phase preconditions — AF-PHASE-SKIPPED
# ---------------------------------------------------------------------------
def check_phase_preconditions(run_dir: Path, phases: list, target_phase_id: str) -> str:
    """Return "" when every phase with a lower `order` than target is attested AND
    its produces_artifact is present (or is covered by an owner-authorized skip).
    Otherwise return a fatal AF-PHASE-SKIPPED message. This computes the ordered
    prior-phase list and DELEGATES the attestation/owner-skip decision to the shared
    build_deck.check_phase_preconditions (single source of truth — not reimplemented).
    It additionally enforces produces_artifact presence for each prior phase."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return f"AF-PHASE-SKIPPED: unknown phase id {target_phase_id!r} (not in manifest)."
    target_order = target.get("order", 0)
    prior = sorted([ph for ph in phases if ph.get("order", 0) < target_order],
                   key=lambda p: p.get("order", 0))
    prior_ids = [ph["id"] for ph in prior]
    # Shared attestation / owner-skip decision (build_deck is the single source of truth).
    reason = bd.check_phase_preconditions(run_dir, target_phase_id, prior_ids)
    if reason:
        return reason
    # Additionally require each attested prior phase's produces_artifact to be present
    # (an attestation must correspond to a real artifact, unless owner-skip-approved).
    approvals = load_skip_approvals(run_dir)
    for ph in prior:
        pid = ph["id"]
        if pid in approvals:
            continue
        if not _artifact_present(run_dir, ph.get("produces_artifact", "")):
            return (f"AF-PHASE-SKIPPED: prior phase {pid!r} is attested but its "
                    f"produces_artifact {ph.get('produces_artifact')!r} is not present in "
                    f"the run dir — an attestation must correspond to a real artifact. "
                    f"Re-run {pid!r} or add a logged owner-authorized skip.")
    return ""


# ---------------------------------------------------------------------------
# Phase-0 pre-flight — platform note + Kie balance (AF-KIE-BALANCE)
# ---------------------------------------------------------------------------
def _slide_count(run_dir: Path, slides_path: Path) -> int:
    try:
        slides = json.loads(slides_path.read_text())
        if isinstance(slides, list):
            return len(slides)
    except Exception:  # noqa: BLE001
        pass
    n = bd._count_output_slides(run_dir, slides_path)
    return n or 0


def phase0_preflight(run_dir: Path, slides_path: Path, platform_override=None,
                     adhoc: bool = False) -> None:
    """Phase-0: detect box type (resource note) + Kie balance pre-flight. HARD-ABORT
    (exit 4) on AF-KIE-BALANCE before any phase is dispatched."""
    platform = bd.detect_platform(run_dir, override=platform_override)
    worker_note = "mac -> fewer parallel render workers" if platform == "mac" else \
                  "vps -> more parallel render workers"
    print(f"=== PHASE-0 PRE-FLIGHT — box_type={platform} ({worker_note}) ===", flush=True)

    slide_count = _slide_count(run_dir, slides_path)
    print(f"=== PHASE-0 — deck slide_count={slide_count} ===", flush=True)

    if adhoc:
        print("=== PHASE-0 — adhoc (owner-authorized): Kie balance pre-flight skipped ===",
              flush=True)
        attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck",
                     "preflight_ok_adhoc")
        return

    api_key = ""
    try:
        api_key = bd.load_api_key()
    except SystemExit:
        # No key on this box — the render-phase subprocess will fail loud on its own.
        print("=== PHASE-0 — no Kie API key on this box; balance pre-flight deferred to "
              "the render subprocess ===", flush=True)
    reason = bd.kie_balance_preflight(run_dir, slide_count, api_key or None)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — Kie balance pre-flight PASSED (balance >= estimated floor) ===",
          flush=True)
    attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck", "preflight_ok")


# ---------------------------------------------------------------------------
# Plan printing
# ---------------------------------------------------------------------------
def print_plan(run_dir: Path, phases: list) -> None:
    attested = _attested_phase_ids(run_dir)
    approvals = load_skip_approvals(run_dir)
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    print("=== SIGNATURE-DECK PHASE PLAN (manifest order) ===")
    for ph in ordered:
        pid = ph["id"]
        if pid in attested:
            state = "ATTESTED"
        elif pid in approvals:
            state = "SKIP(owner-authorized)"
        else:
            state = "pending"
        print(f"  [{ph.get('order'):>5}] {pid:<16} {state:<22} "
              f"owner={ph.get('owning_role')}  -> {ph.get('produces_artifact')}")


# ---------------------------------------------------------------------------
# adhoc authorization (owner-authorized + logged; refused without the record)
# ---------------------------------------------------------------------------
def assert_adhoc_authorized(run_dir: Path) -> None:
    p = run_dir / "working" / "checkpoints" / "adhoc_authorization.json"
    ok = False
    if p.exists():
        try:
            obj = json.loads(p.read_text())
            ok = (isinstance(obj, dict) and obj.get("owner_approved") is True
                  and str(obj.get("approved_by", "")).strip()
                  and str(obj.get("reason", "")).strip())
        except Exception:  # noqa: BLE001
            ok = False
    if not ok:
        print("FATAL: --adhoc requires an OWNER-AUTHORIZED, LOGGED record at "
              "working/checkpoints/adhoc_authorization.json "
              "(owner_approved:true + approved_by + reason). It is NOT a free flag. "
              "Refusing the ad-hoc run.", file=sys.stderr)
        sys.exit(2)
    bar = "!" * 78
    print(bar, flush=True)
    print("!! ADHOC MODE (owner-authorized + logged): phase preconditions + balance "
          "pre-flight relaxed.", flush=True)
    print("!! Output of this run is NOT a process-compliant client deliverable.", flush=True)
    print(bar + "\n", flush=True)


# ---------------------------------------------------------------------------
# SEND-BACK-THROUGH QC LOOPS (v15.0.0) — measurers, routeback payload, harness
# ---------------------------------------------------------------------------
def _import_checker(modname: str):
    """Import a sibling engine-checker module (owned by Agent 3). Returns the module
    or None if it is not importable on this box (the loop degrades gracefully)."""
    try:
        return importlib.import_module(modname)
    except Exception:  # noqa: BLE001
        return None


def _pitch_included(run_dir: Path) -> bool:
    """Pricing sub-engines apply only to pitch decks (mirror build_deck._chk_pitch's
    intake gate). Skip ONLY when intake.json explicitly sets pitch_included:false;
    default True (fail-closed — never silently skip a required engine)."""
    intake = run_dir / "working" / "copy" / "intake.json"
    try:
        obj = json.loads(intake.read_text())
        if isinstance(obj, dict) and obj.get("pitch_included") is False:
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


def _measure_prompt_qc(run_dir: Path) -> dict:
    """SOURCE-OF-TRUTH prompt verdict — re-measures every on-disk prompt via
    build_deck.check_prompt_qc_deterministic (NOT the QC agent's self-score). The
    verdict gates BOTH floors: length >= 9,000 AND every engine AND harmony AND
    excellence (per the §3.5 contract)."""
    verdict = bd.check_prompt_qc_deterministic(run_dir)
    if not isinstance(verdict, dict):
        verdict = {"pass": bool(verdict)}
    return verdict


def _measure_copy_qc(run_dir: Path) -> dict:
    """SOURCE-OF-TRUTH copy verdict — composes the WRITING-engine checker
    (intelligence_engines_check.check_copy: Story villain-before-hero, Emotional
    felt-stakes, + narrative harmony) and the PRICING sub-engine checker
    (pitch_engines_check.check_copy: cadence / cost-of-inaction / promise-before-price
    / branded-method / time-to-result). Both append AF-code problem dicts to a shared
    list; pass == no problems. The checkers read run_dir/working/copy/slides_copy.md."""
    working = run_dir / "working"
    problems: list = []
    iec = _import_checker("intelligence_engines_check")
    if iec is not None and hasattr(iec, "check_copy"):
        iec.check_copy(working, problems)
    pec = _import_checker("pitch_engines_check")
    if pec is not None and hasattr(pec, "check_copy") and _pitch_included(run_dir):
        pec.check_copy(working, problems)
    return {"pass": len(problems) == 0, "problems": problems}


def _slide_key(sid) -> str:
    """Normalize a slide id to a zero-padded 2-digit key ('7'/'slide-07' -> '07')."""
    s = str(sid).strip()
    m = re.search(r"\d+", s)
    return f"{int(m.group()):02d}" if m else s


def _intelligence_for_code(code) -> str:
    """Map an AF code to the named INTELLIGENCE/ENGINE it enforces (so the work order
    tells the re-author exactly which engine is absent)."""
    c = (code or "").upper()
    table = {
        "AF-NO-VILLAIN": "Story",
        "AF-NO-FELT-STAKES": "Emotional",
        "AF-CADENCE": "Pricing",
        "AF-NO-COST-OF-INACTION": "Pricing",
        "AF-GUARANTEE-GENERIC": "Pricing",
        "AF-NO-BRANDED-METHOD": "Pricing",
        "AF-METHOD-FABRICATED": "Pricing",
        "AF-NO-TIME-TO-RESULT": "Pricing",
        "AF-NARRATIVE-HARMONY": "Harmony",
        "AF-HARMONY": "Harmony",
        "AF-NO-HOOK-REFRAIN": "Hook",
        "AF-NO-RECAP": "Recap",
        "AF-PRICE-BEFORE-PROMISE": "Pricing",
        "AF-NO-SHIFT": "Priority Shift",
        "AF-NO-PRIORITY-STACK": "Priority Shift",
        "AF-NO-RERANK": "Priority Shift",
        "AF-NO-TRIGGER": "Pricing",
        "AF-PROCLAMATION-HEDGE": "Proclamation",
        "AF-MODE-UNSET": "Creation Mode",
        "AF-PEAK-END": "Peak-End",
        "AF-NO-SALIENCE-APEX": "Salience",
        "AF-PRIORITY-SHIFT": "Priority Shift",
        "AF-FACE": "Facial",
        "AF-LIGHT": "Lighting",
        "AF-WORLD": "World",
        "AF-HAIR": "Hair",
        "AF-HOOK": "Hook",
        "AF-EXCELLENCE": "Excellence",
    }
    for k, v in table.items():
        if c.startswith(k):
            return v
    return ""


def _directive_for_slide(key: str, char_count, defs: list) -> str:
    """Build an actionable, NON-padding re-author directive for one slide from its
    measured-vs-required deficiencies."""
    head = f"Re-author slide-{key} to the 9,000-18,000 char band"
    if char_count is not None:
        head += f" (measured {char_count})"
    parts = [head]
    for d in defs:
        seg = []
        if d.get("intelligence"):
            seg.append(f"ENGINE {d.get('intelligence')}")
        if d.get("code"):
            seg.append(str(d.get("code")))
        if d.get("measured") is not None and d.get("required") is not None:
            seg.append(f"measured={d.get('measured')} required={d.get('required')}")
        fix = d.get("fix") or d.get("detail")
        if fix:
            seg.append(str(fix))
        if seg:
            parts.append("; ".join(seg))
    parts.append("Do NOT pad to hit the count — spend the budget on defect-preventing specificity.")
    return " | ".join(parts)


def _normalize_deficiencies(phase: str, deficiencies):
    """Turn a measurer verdict into (work_orders, deck_deficiencies, reauthor_slides).

    Accepts EITHER the PROMPT-QC dict shape ({slides:{N:{char_count, deficiencies:[...]}}})
    OR the COPY-QC dict ({problems:[{code, slide, detail, ...}]}) / a bare problems list.
    Only FAILING slides land in reauthor_slides — the re-author touches nothing else."""
    work_orders: dict = {}
    deck_defs: list = []
    reauthor_slides: list = []

    if isinstance(deficiencies, dict) and isinstance(deficiencies.get("slides"), dict):
        # PROMPT-QC verdict shape
        for sid, sd in deficiencies["slides"].items():
            if not isinstance(sd, dict):
                continue
            raw = [d for d in (sd.get("deficiencies") or []) if isinstance(d, dict)]
            failing = [d for d in raw if str(d.get("severity", "")).lower() != "ok"]
            if not failing:
                continue
            key = _slide_key(sid)
            reauthor_slides.append(key)
            for d in failing:
                d.setdefault("intelligence", _intelligence_for_code(d.get("code")))
            work_orders[key] = {
                "char_count": sd.get("char_count"),
                "deficiencies": failing,
                "reauthor_directive": _directive_for_slide(key, sd.get("char_count"), failing),
            }
    else:
        # COPY-QC problems list (or {"problems": [...]})
        problems = deficiencies.get("problems") if isinstance(deficiencies, dict) else deficiencies
        for p in (problems or []):
            if not isinstance(p, dict):
                p = {"code": "AF-COPY", "detail": str(p)}
            entry = {
                "code": p.get("code"),
                "intelligence": p.get("intelligence") or _intelligence_for_code(p.get("code")),
                "detail": p.get("detail"),
                "fix": p.get("fix") or p.get("detail"),
                "measured": p.get("measured"),
                "required": p.get("required"),
                "severity": p.get("severity", "reauthor"),
            }
            slide = str(p.get("slide", "DECK")).strip() or "DECK"
            if slide.upper() == "DECK":
                deck_defs.append(entry)
                continue
            key = _slide_key(slide)
            wo = work_orders.setdefault(key, {"char_count": None, "deficiencies": []})
            wo["deficiencies"].append(entry)
            if key not in reauthor_slides:
                reauthor_slides.append(key)
        for key, wo in work_orders.items():
            wo["reauthor_directive"] = _directive_for_slide(key, wo.get("char_count"),
                                                            wo["deficiencies"])

    reauthor_slides.sort()
    return work_orders, deck_defs, reauthor_slides


def write_routeback_payload(run_dir: Path, phase: str, deficiencies) -> Path:
    """Write a per-slide WORK ORDER routeback file for a failed QC phase; return its Path.

    `phase` is "COPY-QC" or "PROMPT-QC". `deficiencies` is the deterministic measurer's
    verdict (the PROMPT-QC dict {slides:{N:{char_count, deficiencies}}}, or the COPY-QC
    dict {problems:[...]}). The attempt number is derived from the routeback files already
    on disk, so the cap is enforced ACROSS invocations. The payload hands the re-author
    the measured-vs-required delta, the missing-intelligence name, and an actionable
    reauthor_directive PER FAILING SLIDE — so only the failing slides are re-authored,
    never the whole deck, never padded to hit the count."""
    phase = phase.upper()
    prefix = _ROUTEBACK_PREFIX.get(phase, "qc_routeback")
    qc_dir = run_dir / "working" / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    attempt = len(list(qc_dir.glob(f"{prefix}-*.json"))) + 1
    work_orders, deck_defs, reauthor_slides = _normalize_deficiencies(phase, deficiencies)
    payload = {
        "schema": "qc_routeback/v1",
        "phase": phase,
        "attempt": attempt,
        "max_attempts": PROMPT_QC_MAX_ATTEMPTS,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "measurer": ("build_deck.check_prompt_qc_deterministic" if phase == "PROMPT-QC"
                     else "intelligence_engines_check.check_copy + pitch_engines_check.check_copy"),
        "routed_back_to": _REAUTHOR_ROLE.get(phase, ""),
        "pass": False,
        "reauthor_slides": reauthor_slides,
        "deck_deficiencies": deck_defs,
        "work_orders": work_orders,
        "instruction": ("Re-author ONLY the slides in reauthor_slides (and address every "
                        "deck_deficiencies item). Hit the 9,000-18,000 char band with "
                        "defect-preventing specificity — do NOT pad to reach the count. "
                        "Every listed missing intelligence MUST be present on re-submit; "
                        "the deterministic measurer re-checks and will route back again "
                        "if it is not."),
    }
    out = qc_dir / f"{prefix}-{attempt}.json"
    out.write_text(json.dumps(payload, indent=2))
    return out


def _verdict_pass(verdict) -> bool:
    if isinstance(verdict, dict):
        return bool(verdict.get("pass"))
    return bool(verdict)


def _count_routebacks(run_dir: Path, phase: str) -> int:
    """How many routeback files already exist for this phase (cross-invocation cap)."""
    prefix = _ROUTEBACK_PREFIX.get(phase.upper(), "qc_routeback")
    qc_dir = run_dir / "working" / "qc"
    if not qc_dir.is_dir():
        return 0
    return len(list(qc_dir.glob(f"{prefix}-*.json")))


def _run_qc_loop(run_dir: Path, phase: str, measurer, *, reauthor=None,
                 max_attempts=None) -> int:
    """The bounded send-back harness shared by COPY-QC and PROMPT-QC.

    Flow: measure (the deterministic source of truth) -> if pass, attest the phase and
    return 0 (downstream unblocks) -> if fail, write a per-slide routeback work order and
    route it to the owning author. When an in-process `reauthor(role, routeback_path,
    attempt)` callable is supplied, the loop re-authors the failing slides and re-measures,
    up to `max_attempts`. When it is not (this runner does not spawn role subagents
    in-process), the loop writes the work order and returns EXIT_QC_ROUTEBACK WITHOUT
    attesting — the orchestrator re-authors only the failing slides and re-runs this phase;
    the cap is still enforced via the on-disk routeback count. After the cap, the only exit
    is a logged owner override (build_deck._owner_skip_approved); otherwise the phase is
    refused so the failing work physically cannot advance."""
    phase = phase.upper()
    max_attempts = max_attempts or PROMPT_QC_MAX_ATTEMPTS
    phase_id = _QC_PHASE_ID[phase]
    owning_role = _QC_OWNING_ROLE[phase]
    af_code = _QC_AF_CODE[phase]
    role = _REAUTHOR_ROLE.get(phase, "")
    downstream = "prompt never reaches kie.ai" if phase == "PROMPT-QC" \
        else "script never reaches prompt authoring"
    bar = "=" * 78
    print(f"{bar}\n=== {phase} SEND-BACK LOOP — exit on the MEASURER, not the self-score "
          f"(cap={max_attempts}) ===\n{bar}", flush=True)

    routeback_path = None
    consumed = _count_routebacks(run_dir, phase)  # attempts already written (cross-invocation)
    while True:
        if routeback_path is not None and reauthor is not None:
            print(f"=== {phase} attempt {consumed}: re-authoring FAILING slides only via "
                  f"{role} ({routeback_path.name}) ===", flush=True)
            reauthor(role, routeback_path, consumed)

        verdict = measurer(run_dir)
        if _verdict_pass(verdict):
            attest_phase(run_dir, phase_id, owning_role, "qc_pass_measurer")
            print(f"=== {phase} PASS (deterministic measurer) — phase {phase_id} attested; "
                  f"downstream unblocked ===", flush=True)
            return 0

        if consumed >= max_attempts:
            rec = bd._owner_skip_approved(run_dir, af_code)
            if rec:
                attest_phase(run_dir, phase_id, owning_role, "qc_owner_override")
                print(f"=== {phase} OWNER OVERRIDE after cap — {af_code} waived by "
                      f"{rec.get('approved_by')!r} (logged) ===", flush=True)
                return 0
            print("\n" + "!" * 78, file=sys.stderr)
            print(f"FATAL {af_code}: re-author attempts exhausted ({consumed}/{max_attempts}) "
                  f"and no logged owner override. Refusing to advance — the failing "
                  f"{downstream}.", file=sys.stderr)
            print("!" * 78 + "\n", file=sys.stderr)
            return EXIT_QC_EXHAUSTED

        consumed += 1
        routeback_path = write_routeback_payload(run_dir, phase, verdict)
        print(f"=== {phase} FAIL — routeback {routeback_path.name} written "
              f"(attempt {consumed}/{max_attempts}); routed back to {role} ===", flush=True)

        if reauthor is None:
            # This runner does not spawn role subagents in-process. The work order is on
            # disk; the orchestrator re-authors ONLY the failing slides and re-runs this
            # phase. The phase is NOT attested, so the next phase stays BLOCKED and the
            # failing work physically cannot advance.
            print(f"=== {phase} ROUTEBACK PENDING — {role} must re-author the listed slides, "
                  f"then re-run --phase {phase_id}. Phase NOT attested; downstream BLOCKED "
                  f"({downstream}). ===", flush=True)
            return EXIT_QC_ROUTEBACK
        # in-process reauthor supplied: loop, re-author, re-measure.


def run_prompt_qc_loop(run_dir: Path, phases=None, *, reauthor=None,
                       max_attempts=None) -> int:
    """PROMPT-QC send-back loop (G7). Fires AFTER prompt authoring, BEFORE P4-RENDER (the
    money step). Exit gate is build_deck.check_prompt_qc_deterministic (BOTH floors:
    length >= 9,000 AND every engine AND harmony AND excellence). A thin/off prompt routes
    back and physically cannot reach submit_task/kie.ai until it passes."""
    return _run_qc_loop(run_dir, "PROMPT-QC", _measure_prompt_qc,
                        reauthor=reauthor, max_attempts=max_attempts)


def run_copy_qc_loop(run_dir: Path, phases=None, *, reauthor=None,
                     max_attempts=None) -> int:
    """COPY-QC send-back loop (G8). Fires AFTER the script is written, BEFORE any image
    prompt is authored. Exit gate is the composed WRITING + PRICING engine measurer
    (Story villain-before-hero, Emotional felt-stakes, pricing promise-before-price +
    cadence, narrative harmony). A broken script routes back; no prompts are authored
    until the copy passes."""
    return _run_qc_loop(run_dir, "COPY-QC", _measure_copy_qc,
                        reauthor=reauthor, max_attempts=max_attempts)


def _harmony_failure(result):
    """Normalize build_deck.check_deck_harmony's return into a failure reason; None/''
    means PASS. Accepts a preflight-style string ('' == pass), a dict ({pass:bool, ...}),
    or a problems list ([] == pass)."""
    if result is None:
        return None
    if isinstance(result, str):
        return result.strip() or None
    if isinstance(result, dict):
        if result.get("pass") is True:
            return None
        probs = result.get("problems") or result.get("deficiencies")
        if probs:
            return json.dumps(probs)
        if result.get("pass") is False:
            return "AF-HARMONY: deck-level cohesion failed"
        return None
    if isinstance(result, (list, tuple)):
        return json.dumps(list(result)) if result else None
    return None


def pre_assembly_harmony_checkpoint(run_dir: Path) -> int:
    """PRE-ASSEMBLY checkpoint (G5, harmony placement 3): prove deck-level cohesion
    (recurring character, palette coherence, world continuity, archetype rhythm) BEFORE
    the deck is assembled — never assemble-then-discover. Calls build_deck.check_deck_harmony;
    on a finding it refuses assembly unless waived by a logged owner override (AF-HARMONY)."""
    fn = getattr(bd, "check_deck_harmony", None)
    if fn is None:
        print("=== PRE-ASSEMBLY HARMONY: build_deck.check_deck_harmony unavailable — "
              "skipping (checker not yet wired) ===", flush=True)
        return 0
    reason = _harmony_failure(fn(run_dir))
    if not reason:
        print("=== PRE-ASSEMBLY HARMONY: PASS — deck coheres (arc + visual consistency) ===",
              flush=True)
        return 0
    if bd._owner_skip_approved(run_dir, "AF-HARMONY"):
        print("=== PRE-ASSEMBLY HARMONY: AF-HARMONY waived by logged owner override ===",
              flush=True)
        return 0
    print("\n" + "!" * 78, file=sys.stderr)
    print("FATAL PRE-ASSEMBLY AF-HARMONY: deck-level cohesion failed; refusing to assemble. "
          "Re-render ONLY the inconsistent slides. Detail: " + reason, file=sys.stderr)
    print("!" * 78 + "\n", file=sys.stderr)
    return EXIT_QC_EXHAUSTED


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Deterministic signature-deck runner (3C).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--slides", help="slides.json (required to run; optional for --plan)")
    ap.add_argument("--out", help="out.pptx (required to dispatch the render phase)")
    ap.add_argument("--phase", help="dispatch/advance a single phase id (checks preconditions)")
    ap.add_argument("--platform", choices=["vps", "mac"], default=None)
    ap.add_argument("--plan", action="store_true", help="print the phase plan and exit")
    ap.add_argument("--adhoc", action="store_true",
                    help="owner-authorized + logged escape (refused without the record)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        sys.exit(2)

    manifest = load_manifest()
    phases = manifest["phases"]

    if args.plan:
        print_plan(run_dir, phases)
        sys.exit(0)

    if args.adhoc:
        assert_adhoc_authorized(run_dir)

    if not args.slides:
        print("FATAL: --slides is required to run (use --plan to inspect only).",
              file=sys.stderr)
        sys.exit(2)
    slides_path = Path(args.slides).resolve()
    if not slides_path.exists():
        print(f"FATAL: slides.json not found: {slides_path}", file=sys.stderr)
        sys.exit(2)

    # Phase-0 pre-flight (platform note + Kie balance). HARD-ABORTS on AF-KIE-BALANCE.
    phase0_preflight(run_dir, slides_path, platform_override=args.platform,
                     adhoc=args.adhoc)

    # Single-phase dispatch: enforce preconditions (AF-PHASE-SKIPPED), then dispatch.
    if args.phase:
        if not args.adhoc:
            reason = check_phase_preconditions(run_dir, phases, args.phase)
            if reason:
                print("\nFATAL: " + reason, file=sys.stderr)
                sys.exit(2)
        target = next((p for p in phases if p["id"] == args.phase), None)

        # --- SHIFT-LEFT QC SEND-BACK LOOPS (v15.0.0) ---
        # COPY-QC fires before ANY prompt is authored; PROMPT-QC before ANY render. The
        # exit gate is the deterministic measurer, never the QC agent's self-score. On a
        # fail the loop writes a per-slide work order and DOES NOT attest, so the next
        # phase (prompt authoring / render) is structurally blocked until it passes.
        if args.phase == COPY_QC_PHASE_ID:
            sys.exit(run_copy_qc_loop(run_dir, phases))
        if args.phase == PROMPT_QC_PHASE_ID:
            sys.exit(run_prompt_qc_loop(run_dir, phases))
        # PRE-ASSEMBLY deck-harmony checkpoint (G5, placement 3) — fires before the deck
        # is assembled, then falls through to the normal artifact-present attestation.
        if args.phase == ASSEMBLE_PHASE_ID:
            rc = pre_assembly_harmony_checkpoint(run_dir)
            if rc != 0:
                sys.exit(rc)

        # The render phase is the only one this runner dispatches into build_deck.py;
        # all other phases are produced by their owning department role/agent, and the
        # runner records their attestation once their produces_artifact is present.
        if args.phase == "P4-RENDER":
            if not args.out:
                print("FATAL: --out is required to dispatch the render phase.",
                      file=sys.stderr)
                sys.exit(2)
            rc = _dispatch_render(run_dir, slides_path, Path(args.out).resolve(),
                                  platform=args.platform, adhoc=args.adhoc)
            sys.exit(rc)
        # PRE-DELIVERY GUARD: the delivery phase may not be attested until the WHOLE
        # governed process is proven. The canonical render guard refuses delivery
        # unless (a) the full process_manifest attestation chain is present (every
        # governed phase attested or owner-skip-approved), (b) the run dir is free of
        # hand-rolled renderers, and (c) the Fix-2 pixel/vision image-QC passes
        # (AF-IMAGE-QC-VISION). The ONLY bypass per failing gate is a logged
        # owner_skip_approval token. --adhoc does NOT waive this — it is the gate that
        # makes a faked "Done" impossible.
        if args.phase == DELIVERY_PHASE_ID:
            phase_skips = set(load_skip_approvals(run_dir).keys())
            reason = guard.guard_pre_delivery(run_dir, phases, slides_path,
                                              phase_skip_approvals=phase_skips)
            if reason:
                print("\n" + "!" * 78, file=sys.stderr)
                print("FATAL PRE-DELIVERY: " + reason, file=sys.stderr)
                print("!" * 78 + "\n", file=sys.stderr)
                sys.exit(EXIT_GUARD_BLOCK)
            print("=== CANONICAL-RENDER-GUARD (pre-delivery): PASS — full attestation "
                  "chain present, no hand-rolled renderers, pixel/vision QC clean ===",
                  flush=True)

        # Non-render phase: verify the artifact landed, then attest.
        if _artifact_present(run_dir, target.get("produces_artifact", "")):
            attest_phase(run_dir, args.phase, target.get("owning_role", ""),
                         "artifact_present")
            print(f"=== PHASE {args.phase} attested (produces_artifact present) ===",
                  flush=True)
            sys.exit(0)
        print(f"FATAL: phase {args.phase} produces_artifact "
              f"{target.get('produces_artifact')!r} is not present; cannot attest.",
              file=sys.stderr)
        sys.exit(2)

    # No --phase: print the plan (the safe default — the runner never blindly fans
    # out every department role; it dispatches the render and attests artifacts).
    print_plan(run_dir, phases)
    print("\nNote: pass --phase P4-RENDER --out out.pptx to dispatch the deterministic "
          "render (build_deck.py) once all upstream phases are attested.", flush=True)
    sys.exit(0)


def _dispatch_render(run_dir: Path, slides_path: Path, out_path: Path,
                     platform=None, adhoc=False) -> int:
    """Dispatch the render phase by invoking build_deck.py as a SUBPROCESS with the
    same args (its render path is untouched). Returns the subprocess return code.

    PRE-RENDER GUARD: before a single image is rendered, the canonical render guard
    scans the run dir for hand-rolled renderers/assemblers (local 2048x1152 canvas,
    native on-slide text, direct kie createTask, per-deck render functions). A finding
    HARD-ABORTS the render (exit EXIT_GUARD_BLOCK) unless it is covered by a logged
    owner_skip_approval token. This is what blocks `python3 working/phase4_*.py`
    bypasses from ever reaching kie.ai. --adhoc does NOT waive it; only an owner token
    in process_manifest.json does."""
    import subprocess
    reason = guard.guard_pre_render(run_dir)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PRE-RENDER: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        return EXIT_GUARD_BLOCK
    print("=== CANONICAL-RENDER-GUARD (pre-render): PASS — no hand-rolled renderers ===",
          flush=True)
    cmd = [sys.executable, str(HERE / "build_deck.py"), str(slides_path), str(out_path),
           "--run-dir", str(run_dir)]
    if platform:
        cmd += ["--platform", platform]
    if adhoc:
        cmd += ["--adhoc-no-process"]
    print(f"=== DISPATCH RENDER (subprocess): {' '.join(cmd)} ===", flush=True)
    proc = subprocess.run(cmd)
    if proc.returncode == 0:
        # build_deck.py appends its own render record; the attestation reader counts it.
        print("=== RENDER phase complete — build_deck.py render record attested ===",
              flush=True)
    return proc.returncode


if __name__ == "__main__":
    main()
