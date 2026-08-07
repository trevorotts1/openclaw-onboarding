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
      - OCR-ENGINE availability pre-flight (MASTER-SPEC 7.4): HARD-ABORTS
        (AF-OCR-ENGINE-MISSING, exit 4) before ANY phase — not merely before
        render — when this render environment has no OCR engine (pytesseract /
        Pillow / the tesseract binary unreachable from the exact interpreter that
        will render). SHARED with build_deck.ocr_engine_preflight. The missing
        OCR dependency fails at minute zero, before any paid generation, never
        after images have already been rendered.
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
    4 — Phase-0 balance abort (AF-KIE-BALANCE) or Phase-0 OCR-engine abort
        (AF-OCR-ENGINE-MISSING, MASTER-SPEC 7.4).
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
        [--next]            # print ONLY the single next required phase (turn-gate), read-only
        [--phase PHASE_ID]  # advance to / dispatch a single phase (checks preconditions)
        [--platform vps|mac]
        [--adhoc]           # owner-authorized + logged escape (refused without the record)

THE PHASE TURN-GATE (--next). The RUNNER — not prose — is the agent's interface to
"what is next." `--next` reads PIPELINE-MANIFEST.json + the on-disk attestation
ledger and emits ONE payload describing ONLY the single next required phase (its
owning role, artifact contract, SOP refs, and the exact attest command). It
deliberately refuses to describe anything further ahead. The orchestrating loop is:
`--next` -> do exactly that one phase -> `--phase <ID>` (verify + attest) -> `--next`.
Because attestation is order-enforced (check_phase_preconditions, AF-PHASE-SKIPPED)
the agent physically cannot run the process out of the order the runner serves it.
Canonical doctrine home: universal-sops/PRESENTATION-MASTER-DOCTRINE.md.

This is a SCRIPT (not a manifest role/phase). sync_check.py does not require a
symbol for it; AF-PHASE-SKIPPED is enforced_by:runner with py_symbol:null.
"""

import argparse
import hashlib
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from manifest_source import resolve_manifest, resolve_ruleset, refuse, find_repo_root
from presentation_job.defers import load_intake, phase_is_deferred

# FIX-21 (D21): run_with_cleanup dispatches the build_deck.py render/notes-sync and
# manifest executors in a NEW PROCESS GROUP and, on timeout, kills the WHOLE group
# (SIGTERM -> SIGKILL). Previously these dispatchers had NO timeout at all — a hung
# build_deck.py ran forever and its `find`-style scanning orphans matched the old
# name-based process filter, masking the dead render for 18+ minutes.
try:
    from process_reaper import run_with_cleanup
except ImportError:  # pragma: no cover — module ships beside run_signature_deck.py
    run_with_cleanup = None

# Hard wall-clock cap for a build_deck.py render/notes-sync/executor subprocess.
# build_deck.py is the canonical renderer and self-limits internally; this is the
# outer fail-safe so a hung subprocess can never orphan forever (D21).
RENDER_DISPATCH_TIMEOUT_SECONDS = 240 * 60   # 240 min — the P4-RENDER phase budget
EXECUTOR_TIMEOUT_SECONDS = 60 * 60           # 60 min outer cap for manifest executors

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

# FIX 5d — per-phase substance verifier registry. Imported defensively so CI/test
# contexts that lack the sibling module still parse without error.
try:
    import phase_verifiers as _pv
except ImportError:
    _pv = None

# FIX-14 — MC_API_TOKEN / MISSION_CONTROL_URL regression guard. Imported
# defensively so CI/test contexts that lack the sibling module (or run on a box
# where it has not been installed) still parse; the Phase-0 preflight refuses
# (AF-AGENT-ENV-MISSING / AF-AGENT-ENV-UNMANAGED) only when the module is present
# AND its verdict is not PASS — a missing module is never silently "PASS" (see
# phase0_preflight below).
try:
    import check_agent_env as _agent_env
except ImportError:
    _agent_env = None

# FIX-18 — tool-schema hardening (Error 10 / D17). Imported defensively so
# CI/test contexts that lack the sibling module still parse. The Phase-0
# preflight reads this run's AF-TOOL-SCHEMA-LOOP event ledger and HARD-ABORTS
# (exit 4) when a tool hit 5 consecutive malformed-args failures — a looping
# model is stopped instead of silently burning turns. A missing module is a
# WARNING, not an abort: this validator is a mitigation (the normalized schema
# hint + loop alert), not a delivery credential — its absence is caught by the
# dept verify.sh self-test, and delivery must not brick on a mitigation.
try:
    import tool_schema_validator as _tool_schema
except ImportError:
    _tool_schema = None

# FIX-PRES-07: the GOVERNED set of phases that REQUIRE a substance verifier. When
# phase_verifiers.py is importable we derive it LIVE from the registry; when the
# module is MISSING beside the runner (_pv is None) we fall back to this pinned
# copy (kept in lockstep with phase_verifiers.PHASE_VERIFIERS) so a real run of a
# governed phase fails CLOSED instead of silently attesting with no substance
# verification. A degraded pass is allowed ONLY under an explicit test/CI marker.
_GOVERNED_VERIFIER_PHASES = frozenset({
    "P-CONVERTER", "P-0.5-RESEARCH", "P0A-INTAKE", "P0B-PRIORITY", "P3-ARC",
    "P-3.5-RESEARCH-MAP", "P4-COPY", "P1Q-COPY-QC", "PF-DESIGN", "P-TYPO-QC",
    "P4-PROMPT", "P-PROMPT-QC", "P-STYLE-PREVIEW", "P4-RENDER", "P-IMAGE-QC",
    "P-SHIFT-QC", "P8-ASSEMBLE", "P9-SPEECH", "P-SPEECH-QC", "P9.5-NOTES-SYNC",
    "P9-DELIVER", "P-SP-INTAKE", "P-SP-STRUCTURE", "P-SP-P3-HYGIENE",
})
if _pv is not None:
    try:
        _GOVERNED_VERIFIER_PHASES = frozenset(_pv.PHASE_VERIFIERS.keys())
    except Exception:  # noqa: BLE001 — keep the pinned fallback on any registry read error
        pass


def _degraded_verifiers_allowed(run_dir) -> bool:
    """FIX-PRES-07: a degraded (skipped) substance-verify is permitted ONLY in an
    explicit test/CI context. Signals: PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1, a
    CI / OPENCLAW_TEST env marker, or a `.test-context` marker file the test
    harness drops in the run dir. A real production run has NONE of these, so a
    missing phase_verifiers.py fails CLOSED for a governed phase."""
    if os.environ.get("PRESENTATION_ALLOW_DEGRADED_VERIFIERS") == "1":
        return True
    if os.environ.get("CI") or os.environ.get("OPENCLAW_TEST"):
        return True
    try:
        if (Path(run_dir) / "working" / "checkpoints" / ".test-context").exists():
            return True
    except Exception:  # noqa: BLE001 — a marker-read hiccup must not open the gate
        pass
    return False

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
# P9.5-NOTES-SYNC (manifest order 8.7) — fires AFTER P9-SPEECH/P-SPEECH-QC and BEFORE
# P9-DELIVER. Reopens the already-assembled .pptx and re-injects per-slide speaker
# notes from the now QC-passed presenter speech (build_deck.notes_sync_pass). This is
# the code fix for the documented root cause: assembly (P8) precedes the speech
# (P9), so the notes pane is empty at assembly time on a normal linear run. The
# postflight AF-EMPTY-NOTES-PANE gate (build_deck._chk_notes_pane) is what turns an
# un-synced deck into a hard delivery failure; this phase is what fixes it in time.
NOTES_SYNC_PHASE_ID = "P9.5-NOTES-SYNC"

# Exit codes for the loops (distinct from guard=5, balance=4, render=3, skip=2).
EXIT_QC_ROUTEBACK = 6   # routeback written; downstream phase BLOCKED pending re-author
EXIT_QC_EXHAUSTED = 7   # re-author cap exhausted / harmony fail, no owner override — refusal
EXIT_EXECUTOR_FAILED = 8  # a phase's declared manifest executor exited non-zero (or was
                          # malformed) — the phase is NOT attested (see _dispatch_generic_executor)


class PhaseExecutorContractError(RuntimeError):
    """A phase's manifest executor.cmd is not a parseable argument vector, or an
    executor.cmd segment (split on a trusted, manifest-authored `&&`) is empty.
    Named to mirror presentation_job/phases.py's identical U069 contract error —
    this is the SAME dispatch contract, reimplemented here because
    run_signature_deck.py (not presentation_job/phases.py) is the runner
    presentation-canonical-entry.sh actually invokes."""

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
# Fallback produces_artifact specs for QC phases (used when phases list not available).
_QC_PRODUCES_ARTIFACT = {
    "COPY-QC": "working/qc/copy_qc_report.json",
    "PROMPT-QC": "working/qc/prompt_qc_report.json",
}


# ---------------------------------------------------------------------------
# Manifest resolution (same cluster-or-deployed layout sync_check uses)
# ---------------------------------------------------------------------------
_MANIFEST_PATH, _MANIFEST_PROVENANCE = resolve_manifest(HERE)
_MASTER_RULESET, _RULESET_PROVENANCE = resolve_ruleset(HERE)


def load_manifest() -> dict:
    return json.loads(_MANIFEST_PATH.read_text())


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


def _hash_render_set(run_dir: Path) -> str:
    """Return a content hash of the rendered slide set (names + sizes), used as
    the artifact_sha when attesting P4-RENDER from existing verified renders
    (FIX 4/E requires a non-empty sha proving the artifact was inspected)."""
    import hashlib as _hl
    _h = _hl.sha256()
    _renders_dir = run_dir / "renders"
    if _renders_dir.is_dir():
        for _png in sorted(_renders_dir.glob("slide-*.png")):
            _h.update(_png.name.encode())
            try:
                _h.update(str(_png.stat().st_size).encode())
            except OSError:  # noqa: BLE001
                pass
    return _h.hexdigest()


def _write_render_record_from_existing(run_dir: Path, out_path: Path) -> str:
    """Record the genuine render in process_manifest.json's 'phases' list (the
    `phase=='render'` record the delivery boundary gate's AF-NOT-KIE-RENDERED
    check requires). Populated from the run's REAL pending_tasks.json (genuine
    kie taskIds + sha256s) + the on-disk renders — the actual render that already
    happened, NOT a fabrication. Returns the record's artifact sha."""
    import hashlib as _hl
    import json as _json
    _manifest_p = _process_manifest_path(run_dir)
    _obj = _load_process_manifest(run_dir)
    _obj.setdefault("phases", [])
    # avoid duplicating an existing render record
    for _ph in _obj.get("phases", []) or []:
        if isinstance(_ph, dict) and _ph.get("phase") == "render":
            return _ph.get("artifact_sha", "") or _hl.sha256(b"").hexdigest()
    _pending = {}
    _ppt = run_dir / "working" / "checkpoints" / "pending_tasks.json"
    try:
        _pending = _json.loads(_ppt.read_text()) if _ppt.is_file() else {}
    except Exception:  # noqa: BLE001
        _pending = {}
    _task_ids = set()
    _per_slide = []
    for _png in sorted((run_dir / "renders").glob("slide-*.png")):
        import re as _re
        _m = _re.search(r"slide-(\d+)", _png.name)
        if not _m:
            continue
        _n = int(_m.group(1))
        _rec = _pending.get(str(_n), {}) if isinstance(_pending, dict) else {}
        _tid = str(_rec.get("task_id") or "").strip()
        _sha = str(_rec.get("sha256") or "").strip()
        if not _sha:
            try:
                _sha = _hl.sha256(_png.read_bytes()).hexdigest()
            except OSError:  # noqa: BLE001
                _sha = ""
        if _tid:
            _task_ids.add(_tid)
        _per_slide.append({
            "slide": _n, "taskId": _tid or None, "image": str(_png),
            "image_sha256": _sha or None,
        })
    _record_sha = _hl.sha256(
        ("render-existing-" + "".join(sorted(_task_ids))).encode()).hexdigest()
    _obj["phases"].append({
        "phase": "render", "tool": "build_deck.py", "timestamp": _now_iso(),
        "taskIds": sorted(_task_ids), "output_slide_count": len(_per_slide),
        "output_pptx": str(out_path), "slides": _per_slide,
        "artifact_sha": _record_sha, "attested_existing": True,
    })
    _manifest_p.write_text(_json.dumps(_obj, indent=2))
    return _record_sha


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def attest_phase(run_dir: Path, phase_id: str, role: str, status: str,
                 artifact_sha: str = "", substance_verified: bool = False) -> None:
    """Append a phase attestation to process_manifest.json (never clobber prior
    records — mirrors build_deck.write_process_manifest's append discipline).

    FIX 4/E: artifact_sha MUST be non-empty. This is the machine-readable proof
    that the produces_artifact was inspected before attestation. Refusing to attest
    with an empty sha makes it structurally impossible to attest without first
    computing a real artifact hash. Pass 'no-artifact-spec' for system phases that
    declare no concrete artifact.

    FIX 5d: substance_verified records that phase_verifiers.verify passed for this
    phase — prove-deck.py asserts this field is true for every declared step."""
    if not artifact_sha:
        print(
            f"FATAL: attest_phase called for {phase_id!r} with empty artifact_sha — "
            "refusing to attest without a verified artifact hash (FIX 4/E enforcement). "
            "Pass the sha256 of the produces_artifact, or 'no-artifact-spec' for phases "
            "with no concrete artifact.",
            file=sys.stderr,
        )
        sys.exit(2)
    # FIX-2 (Error 2): a QC phase may NOT attest unless its report clears the
    # REAL-CONTENT floor (>256 bytes, valid JSON, >=20 real per-slide verdicts).
    # A 3-byte '{}' placeholder (the exact Error-2 artifact) can never satisfy a
    # QC phase — refusing the attestation makes QC structurally unskippable at the
    # ledger, not just in prose. AF-QC-PLACEHOLDER.
    _qc_floor = bd.check_qc_phase_report_real(run_dir, phase_id)
    if _qc_floor:
        print("FATAL: " + _qc_floor + " Refusing to attest phase " + phase_id + ".",
              file=sys.stderr)
        sys.exit(2)
    p = _process_manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    obj.setdefault("phase_attestations", [])
    obj["phase_attestations"].append({
        "phase_id": phase_id,
        "owning_role": role,
        "status": status,
        "artifact_sha": artifact_sha,
        "substance_verified": substance_verified,
        "attested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    p.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------------------
# Artifact SHA computation (FIX 4/E — mandatory non-empty sha for every attest)
# ---------------------------------------------------------------------------
def _compute_artifact_sha(run_dir: Path, produces_artifact: str) -> str:
    """Compute sha256 of the phase's produces_artifact file(s). For glob specs,
    hashes the concatenation of all matching file contents (sorted path order).
    Returns a deterministic hex string. Returns 'no-artifact-spec' when the spec
    is empty (the phase declares no concrete artifact — gate accepts this marker).

    '{deck_slug}' placeholder is expanded to the run's deck slug first (mirroring
    _artifact_present)."""
    spec = _expand_artifact_spec(run_dir, produces_artifact)
    if not spec:
        return "no-artifact-spec"
    h = hashlib.sha256()
    if "*" in spec or "?" in spec:
        candidates = sorted(run_dir.glob(spec))
        if not candidates:
            candidates = sorted(run_dir.glob("**/" + spec.split("/")[-1]))
        for p in candidates:
            try:
                h.update(p.read_bytes())
            except Exception:  # noqa: BLE001
                pass
        return h.hexdigest() if candidates else "no-match"
    p = run_dir / spec
    if not p.exists():
        cands = list(run_dir.glob("**/" + spec.split("/")[-1]))
        p = cands[0] if cands else None  # type: ignore[assignment]
    if p and p.exists():
        try:
            h.update(p.read_bytes())
            return h.hexdigest()
        except Exception:  # noqa: BLE001
            return "read-error"
    return "not-found"


# ---------------------------------------------------------------------------
# Client progress reports (FIX 4b — AF-PHASE-REPORT-START / AF-PHASE-REPORT-DONE)
# ---------------------------------------------------------------------------
def _client_reports_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "client_reports.json"


def _load_client_reports(run_dir: Path) -> list:
    p = _client_reports_path(run_dir)
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, list) else []
    except Exception:  # noqa: BLE001
        return []


def _resolve_owner_route() -> tuple:
    """Resolve (channel, target) for the client progress report from the box's
    environment. The producer cannot know the owner chat intrinsically, so it reads
    the same owner-routing env the gateway exposes, in priority order. Returns
    (None, None) when no target is configured — in that case the report is recorded
    as a non-confirmed attempt (sent=False) and delivery is NOT deadlocked (the
    process-integrity gate bites on a MISSING record, not on an unconfirmed send;
    see OQ-2)."""
    target = (
        os.environ.get("PRESENTATION_OWNER_CHAT_ID")
        or os.environ.get("OPENCLAW_OWNER_CHAT_ID")
        or os.environ.get("OWNER_CHAT_ID")
        or os.environ.get("OWNER_TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or ""
    ).strip()
    channel = (os.environ.get("PRESENTATION_OWNER_CHANNEL")
               or os.environ.get("OPENCLAW_OWNER_CHANNEL")
               or "telegram").strip()
    return (channel, target) if target else (None, None)


def _send_owner_message(text: str) -> tuple:
    """Best-effort send via `openclaw message send` (NEVER the Telegram API directly).
    Uses the correct CLI flags (-m / --channel / -t) and an env-resolved target.
    Returns (msg_id, sent_bool). Never raises."""
    channel, target = _resolve_owner_route()
    if not target:
        print("[client_report] no owner target configured "
              "(PRESENTATION_OWNER_CHAT_ID / TELEGRAM_CHAT_ID …) — recording a "
              "non-confirmed report attempt; delivery is not blocked.",
              file=sys.stderr)
        return "", False
    try:
        proc = subprocess.run(
            ["openclaw", "message", "send", "--channel", channel,
             "--target", target, "--message", text, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0:
            print(f"[client_report] openclaw message send rc={proc.returncode}: "
                  f"{(proc.stderr or raw)[:200]}", file=sys.stderr)
            return raw, False
        try:
            msg_id = json.loads(raw).get("message_id") or raw
        except Exception:  # noqa: BLE001
            msg_id = raw
        return msg_id, True
    except Exception as exc:  # noqa: BLE001
        print(f"[client_report] send failed: {exc}", file=sys.stderr)
        return "", False


def _append_report_record(run_dir: Path, phase_id: str, kind: str,
                          gateway_msg_id: str, text: str, sent: bool = False,
                          undeliverable: str = "") -> None:
    """Append a client report record to client_reports.json.
    kind should be 'start' (AF-PHASE-REPORT-START) or 'done' (AF-PHASE-REPORT-DONE).
    Never raises — if the file is unwritable the record is silently dropped and
    the AF-PHASE-REPORT-MISSING gate will detect the absence on the next phase.

    The gate bites on a MISSING record (a phase whose report step was skipped), NOT
    on an unconfirmed gateway_msg_id — so a box without a configured owner target
    still ships (the report was emitted; confirmation is best-effort, OQ-2)."""
    p = _client_reports_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    records = _load_client_reports(run_dir)
    records.append({
        "phase_id": phase_id,
        "kind": kind,
        "gateway_msg_id": gateway_msg_id or "",
        "sent": bool(sent),
        "text": text,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        # U046: a non-empty string names WHY delivery is impossible, which the
        # phase gate accepts as an honest answer. Empty means "not recorded" —
        # which is the case the gate warns (and later fails) on.
        "undeliverable": undeliverable or "",
    })
    try:
        p.write_text(json.dumps(records, indent=2))
    except Exception:  # noqa: BLE001
        pass


def emit_client_report(run_dir: Path, phase_id: str, kind: str,
                       k=None, N=None, eta=None):
    """Send a phase start/done client progress report via ``openclaw message send``
    and record the gateway_msg_id in client_reports.json.

    kind in {"start", "done"} corresponding to AF-PHASE-REPORT-START /
    AF-PHASE-REPORT-DONE. FAIL-CLOSED for the gate: if no record exists at all,
    attest_phase (and the next-phase precondition check AF-PHASE-REPORT-MISSING)
    refuses. Never raises — U046: a send failure records an empty gateway_msg_id
    and the gate warns (PRESENTATION_REPORT_CONFIRM_ENFORCE=1 to make it fatal).

    NEVER calls the Telegram API directly — uses ``openclaw message send``
    exclusively (fleet memory: never-bypass-openclaw-telegram)."""
    if k is not None and N is not None:
        tmpl = (f"Step {k} of {N} — {phase_id} — "
                f"{'starting' if kind == 'start' else 'complete'}")
    else:
        tmpl = f"{phase_id} — {'starting' if kind == 'start' else 'complete'}"
    if kind == "start" and eta:
        tmpl += f" (ETA ~{eta} min)"

    msg_id, sent = _send_owner_message(tmpl)
    # U046: a provable non-delivery is RECORDED as such, not left as a bare
    # sent=False that reads identically to "nobody looked". The two cases the
    # transport proves are: no target resolvable, and a non-zero/raised send.
    undeliverable = ""
    if not sent:
        channel, target = _resolve_owner_route()
        undeliverable = ("no owner target configured" if not target
                         else "gateway send did not confirm")
    _append_report_record(run_dir, phase_id, kind, msg_id, tmpl, sent=sent,
                          undeliverable=undeliverable)
    return msg_id or None


# ---------------------------------------------------------------------------
# FIX-13 — OWNER DELIVERY LINK (M12). After the deck is registered and the
# delivery phase is attested, the OWNER must receive a Telegram message naming
# WHERE the deck is. Prior to this fix the pipeline only ever told the owner a
# generic "P9-DELIVER — complete"; the deck LOCATION (GHL public URL / live
# teleprompter URL / local package path) was never sent.
#
# Routing NEVER hardcodes a chat id. It reuses the same owner-routing env the
# gateway exposes (_resolve_owner_route), so on a client box the message lands
# with the deck's own owner and on the OPERATOR box it lands wherever
# PRESENTATION_OWNER_CHAT_ID points (the operator test target). The transport is
# `openclaw message send` via _send_owner_message — the CC report-back loop's
# send path — NEVER the raw Telegram API (fleet rule: never-bypass-openclaw-
# telegram).
#
# The send is recorded in client_reports.json as a `delivery_link` record whose
# `text` carries the resolved deck location and whose gateway_msg_id is the
# confirmed send id — so "the deck link is in the sent-message record" is
# mechanically provable (the FIX-13 QC gate). Never raises; a box with no
# resolvable owner target records an honest undeliverable and the run ships
# (matching the U046 report contract: the gate bites on a MISSING record, not on
# an unconfirmed send).
# ---------------------------------------------------------------------------
def _resolve_deck_location(run_dir: Path) -> str:
    """Resolve a human-readable deck location for the owner delivery message.

    Priority order (first source that yields a usable value wins):
      1. the live teleprompter public URL  — <bundle_dir>/teleprompter_publish.json
         (the verified HTTP-200 host; the most owner-actionable link);
      2. the GHL deck public URL           — working/checkpoints/media_library.json
         `pptx_ghl_url` (the deck's hosted GHL object);
      3. the local client package path     — delivery/*-FINAL/ (the on-disk folder).

    Returns a non-empty string; falls back to the run dir itself. Never raises.
    """
    run_dir = Path(run_dir)
    # 1. Teleprompter public URL (verified live at publish).
    try:
        import fix_bundle_complete as _fbc
        bundle_dir = _fbc.resolve_bundle_dir(run_dir)
        tp = bundle_dir / "teleprompter_publish.json"
        if tp.exists():
            rec = json.loads(tp.read_text())
            url = str(rec.get("public_url") or "").strip()
            if url:
                return url
    except Exception:  # noqa: BLE001 — never let a location read break the send
        pass
    # 2. GHL deck public URL.
    try:
        ml = run_dir / "working" / "checkpoints" / "media_library.json"
        if ml.exists():
            rec = json.loads(ml.read_text())
            url = str(rec.get("pptx_ghl_url") or rec.get("pptx_url") or "").strip()
            if url:
                return url
    except Exception:  # noqa: BLE001
        pass
    # 3. Local client package path (AF-DH1 six-file folder).
    try:
        pkgs = sorted(run_dir.glob("delivery/*-FINAL"))
        if pkgs:
            return str(pkgs[0])
    except Exception:  # noqa: BLE001
        pass
    return str(run_dir)


def emit_delivery_link(run_dir: Path, deck_slug: str = "") -> str | None:
    """Send the owner the deck LOCATION via the CC report-back transport and
    record the send-log row (FIX-13 / M12).

    Composes a delivery message that names WHERE the deck is, sends it through
    `openclaw message send` (never the raw Telegram API), and appends a
    `delivery_link` record to working/checkpoints/client_reports.json whose
    `text` IS the deck-location message and whose gateway_msg_id is the confirmed
    send id — the QC evidence that "the deck link is in the sent-message record".

    Returns the gateway message id on a confirmed send, else None. Never raises:
    an unresolved owner target or a failed send records `undeliverable` (honest)
    and the run continues (the delivery itself is already complete at this
    point — the link message is the final notification, not a gate)."""
    slug = (deck_slug or _deck_slug(run_dir)).strip()
    location = _resolve_deck_location(run_dir)
    # Snippet-able deck link for the sent-message record's readability check. When
    # the resolved location IS the link (a public URL) the same value is used so the
    # "Deck link:" line is always present and machine-checkable; otherwise the local
    # package path is named (a deck that lives on disk, not on a URL).
    link_hint = ""
    if location.startswith("http"):
        link_hint = location
    elif location:
        link_hint = location.split("delivery/")[-1] if "delivery/" in location else location
    text = (f"Your deck is ready, {slug}.\n"
            f"Location: {location}")
    if link_hint:
        text += f"\nDeck link: {link_hint}"
    msg_id, sent = _send_owner_message(text)
    undeliverable = ""
    if not sent:
        _ch, _t = _resolve_owner_route()
        undeliverable = ("no owner target configured" if not _t
                         else "gateway send did not confirm")
    _append_report_record(run_dir, DELIVERY_PHASE_ID, "delivery_link",
                          msg_id, text, sent=sent, undeliverable=undeliverable)
    if sent and msg_id:
        print(f"=== FIX-13 OWNER DELIVERY LINK: sent (msg_id={msg_id}) — {location} ===",
              flush=True)
    else:
        print(f"[FIX-13] owner delivery link not confirmed "
              f"({undeliverable or 'unknown'}) — recorded; delivery already complete.",
              file=sys.stderr, flush=True)
    return msg_id or None


# ---------------------------------------------------------------------------
# Up-front step declaration (FIX 4a — step contract for prove-deck.py)
# ---------------------------------------------------------------------------
def _deck_slug(run_dir: Path) -> str:
    """Derive the deck slug from the run dir's config files, falling back to
    the run dir's base name when no config is found."""
    for cand in [run_dir / "working" / "copy" / "intake.json",
                 run_dir / "working" / "config.json"]:
        try:
            obj = json.loads(cand.read_text())
            if isinstance(obj, dict):
                for k in ("deck_slug", "slug", "title"):
                    v = (obj.get(k) or "").strip()
                    if v:
                        return v
        except Exception:  # noqa: BLE001
            pass
    return run_dir.name


def _declared_plan_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "declared_plan.json"


def declare_plan(run_dir: Path, phases: list) -> None:
    """Write working/checkpoints/declared_plan.json (the step contract) and emit
    ONE client message listing all N steps. IDEMPOTENT — skips if the file already
    exists so re-runs of any phase never double-send the step list.

    The declared_plan.json is the contract that prove-deck.py checks against
    (FIX 2a / AF-PROCESS-INTEGRITY). Records step_declaration_msg_id in both the
    plan file and process_manifest.json. Wraps the openclaw message send in
    try/except so a send failure never aborts the run — the plan file is still
    written (the gate will note 'no step_declaration_msg_id')."""
    plan_path = _declared_plan_path(run_dir)
    if plan_path.exists():
        return  # idempotent — already declared on a prior phase run

    slug = _deck_slug(run_dir)
    # DESIGN-OPUS.md §4.2 — deferred (defers_unless-gated-out) phases are NOT
    # declared as steps: a deck-only run's step contract is identical to today's.
    deferred = _deferred_phase_ids(run_dir, phases)
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    steps = [
        {
            "order": ph.get("order", 0),
            "id": ph["id"],
            "name": ph.get("name", ph["id"]),
            "owning_role": ph.get("owning_role", ""),
        }
        for ph in ordered
        if ph["id"] not in deferred
    ]

    step_lines = "  ".join(f"{i + 1}) {s['name']}" for i, s in enumerate(steps))
    text = (
        f"Starting {slug}. I'll follow these {len(steps)} steps and report "
        f"after each: {step_lines}"
    )

    msg_id, _sent = _send_owner_message(text)

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({
        "deck_slug": slug,
        "declared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "steps": steps,
        "total": len(steps),
        "step_declaration_msg_id": msg_id,
    }, indent=2))

    # Record step_declaration_msg_id in process_manifest.json too.
    pm_path = _process_manifest_path(run_dir)
    pm_path.parent.mkdir(parents=True, exist_ok=True)
    obj = _load_process_manifest(run_dir)
    if "step_declaration_msg_id" not in obj:
        obj["step_declaration_msg_id"] = msg_id
        pm_path.write_text(json.dumps(obj, indent=2))

    print(f"=== DECLARE-PLAN: step contract written ({len(steps)} steps, "
          f"msg_id={msg_id!r}) ===", flush=True)


# ---------------------------------------------------------------------------
# Phase index helper (for k/N in client reports)
# ---------------------------------------------------------------------------
def _phase_index(phase_id: str, phases: list) -> tuple:
    """Return (k, N) — 1-based position of phase_id in the ordered phases list,
    and N = total phase count. Returns (None, N) if phase_id is not found."""
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    for i, ph in enumerate(ordered):
        if ph["id"] == phase_id:
            return i + 1, len(ordered)
    return None, len(ordered)


# ---------------------------------------------------------------------------
# Report CONFIRMATION (U046). Rule 3.5 staging: this ships in WARN mode.
#
# The gate below has always bitten on a MISSING record and never on an
# unconfirmed one, even though check_phase_preconditions' docstring claimed
# otherwise. A record now counts as CONFIRMED only when the transport actually
# reported success — `sent` true AND a non-empty gateway_msg_id — or when the
# non-delivery was explicitly recorded as undeliverable (the producer-side twin
# of the Command Center's recordUndeliverable path, U043 Part A).
#
# WARN vs ENFORCE: on a box with no owner target configured, EVERY existing
# record has sent=False and gateway_msg_id="" — so enforcing on day one blocks
# every build immediately. Stage 1 reports and continues; the finding count is
# the work list. Stage 3 sets PRESENTATION_REPORT_CONFIRM_ENFORCE=1 (or flips
# the default here) once the count is zero.
# ---------------------------------------------------------------------------
REPORT_CONFIRM_ENFORCE_ENV = "PRESENTATION_REPORT_CONFIRM_ENFORCE"


def _report_confirm_enforced() -> bool:
    """True when an unconfirmed report record must FAIL the phase gate.

    Default False (WARN mode). Only the exact string '1' enables enforcement, so a
    stray 'true'/'yes'/'0 ' cannot silently arm a build-blocking gate.
    """
    return os.environ.get(REPORT_CONFIRM_ENFORCE_ENV, "") == "1"


def _report_confirmed(rec: dict) -> bool:
    """A report record counts as delivered.

    Confirmed = the transport reported success AND returned an id, OR the
    non-delivery was explicitly recorded (undeliverable), which is an honest
    'a human could not be told and we said so' rather than a silent gap.

    WHY `undeliverable` IS TRUSTED, AND WHAT THAT TRUST DOES NOT COVER.
    It is engine-written: emit_client_report is its only producer, and it sets
    the field from a closed two-branch expression ("no owner target configured"
    / "gateway send did not confirm"), never from agent input. But the records
    read here come off disk, and _load_client_reports does a plain json.loads
    with no per-record schema validation — so anything that can write into the
    run directory could forge the key and this predicate would call the phase
    delivered. That is ACCEPTED at stage 1, where nothing blocks, and it MUST BE
    RE-EXAMINED BEFORE STAGE 3 makes this predicate load-bearing. The
    MISSING-record return in the gate above is unforgeable by that route and
    stays the hard gate either way.

    ANY truthy value counts, on purpose. A future transport that records a third
    honest reason must fall through to WARN, not to rejection; a closed
    vocabulary would make the gate fire on correct behaviour.
    """
    if rec.get("undeliverable"):
        return True
    return bool(rec.get("sent")) and bool(str(rec.get("gateway_msg_id") or "").strip())


# ---------------------------------------------------------------------------
# Prior-phase report gate (FIX 4b — AF-PHASE-REPORT-MISSING enforcement)
# ---------------------------------------------------------------------------
def _check_prior_phase_reports(run_dir: Path, phases: list, target_phase_id: str) -> str:
    """For every phase PRIOR to target that is attested, verify that BOTH an
    AF-PHASE-REPORT-START and an AF-PHASE-REPORT-DONE record EXIST in
    client_reports.json. Returns '' if satisfied; otherwise an
    AF-PHASE-REPORT-MISSING fatal string.

    The gate bites on a MISSING report record (a phase whose report step was
    skipped entirely), NOT on an unconfirmed gateway_msg_id — so a box where
    `openclaw message send` cannot resolve a target still ships (the report was
    emitted; confirmation is best-effort, OQ-2). Each record carries a `sent`
    boolean for audit.

    Internal system phases (P-0-PREFLIGHT) with no produces_artifact are exempt —
    they are runner housekeeping, not client-reportable pipeline steps."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return ""  # unknown phase — check_phase_preconditions handles the error
    target_order = target.get("order", 0)
    deferred = _deferred_phase_ids(run_dir, phases)
    prior_attested = {
        pid for pid in _attested_phase_ids(run_dir)
        if pid in by_id and pid not in deferred
        and by_id[pid].get("order", 0) < target_order
    }
    if not prior_attested:
        return ""

    reports = _load_client_reports(run_dir)
    start_ids = {r["phase_id"] for r in reports if r.get("kind") == "start"}
    done_ids = {r["phase_id"] for r in reports if r.get("kind") == "done"}
    # U046: the CONFIRMED subsets — a record whose transport actually reported
    # success (or whose non-delivery was explicitly recorded).
    start_confirmed = {r["phase_id"] for r in reports
                       if r.get("kind") == "start" and _report_confirmed(r)}
    done_confirmed = {r["phase_id"] for r in reports
                      if r.get("kind") == "done" and _report_confirmed(r)}
    unconfirmed = []

    for pid in sorted(prior_attested):
        ph = by_id.get(pid, {})
        # Exempt internal system phases with no produces_artifact (runner bookkeeping).
        if pid.startswith("P-0") and not ph.get("produces_artifact"):
            continue
        if pid not in start_ids:
            return (
                f"AF-PHASE-REPORT-MISSING: prior attested phase {pid!r} has no "
                "AF-PHASE-REPORT-START record in client_reports.json — its client "
                "start-report step was skipped."
            )
        if pid not in done_ids:
            return (
                f"AF-PHASE-REPORT-MISSING: prior attested phase {pid!r} has no "
                "AF-PHASE-REPORT-DONE record in client_reports.json — its client "
                "done-report step was skipped."
            )
        # U046 — WARN stage. The record exists; was it delivered?
        for kind, confirmed in (("start", start_confirmed), ("done", done_confirmed)):
            if pid not in confirmed:
                unconfirmed.append(f"{pid}:{kind}")

    if unconfirmed:
        detail = (
            f"AF-PHASE-REPORT-MISSING: {len(unconfirmed)} prior phase report(s) exist "
            f"in client_reports.json but were never DELIVERED (no gateway_msg_id and no "
            f"recorded undeliverable): {', '.join(unconfirmed)}. A written record is not a "
            f"told human. Configure an owner target "
            f"(PRESENTATION_OWNER_CHAT_ID / OPENCLAW_OWNER_CHAT_ID / OWNER_CHAT_ID / "
            f"OWNER_TELEGRAM_CHAT_ID / TELEGRAM_CHAT_ID) so the gateway can resolve one."
        )
        if _report_confirm_enforced():
            return detail
        print("[client_report] WARN-REPORT-UNCONFIRMED: " + detail
              + f" (WARN mode — set {REPORT_CONFIRM_ENFORCE_ENV}=1 to make this fatal.)",
              file=sys.stderr, flush=True)
    return ""


# ---------------------------------------------------------------------------
# Owner-authorized skip records (the controlled exception — NOT a free flag)
# ---------------------------------------------------------------------------
class ForgedApprovalError(Exception):
    """A phase-skip approval could not be proven authentic — its owner_msg_id
    does not resolve to a real owner-authored message in Command Center. Fatal:
    the build MUST fail (the plan print and the precondition gate both consume
    this). See AF-FORGED-APPROVAL."""


def _resolve_owner_msg_ids(run_dir: Path) -> frozenset | None:
    """Resolve the run's CC task to its REAL owner-authored message ids (the
    authoritative owner-approval oracle, FIX-1).

    Returns a frozenset of ids on success; None when UNDETERMINED (no cc_task_id
    in the manifest, the board is disabled, or the owner-ids endpoint could not
    be reached/proven). None NEVER opens the gate — the caller treats undetermined
    as DENIED so a skip that cannot be verified can never authorize a phase.
    Uses cc_board (the dept's own authed CC client) so the HTTP/auth contract is
    identical to every other board call."""
    try:
        import cc_board
        return cc_board.owner_message_ids_match(run_dir, "", env=None)
    except Exception:  # noqa: BLE001 — fail-closed: any oracle failure is DENIED
        return None


def _resolve_owner_msg_ids_for_task(task_id: str) -> frozenset | None:
    """Resolve an explicit CC task_id (independent of any run dir) to its real
    owner-authored message ids. Used by the unit tests and by callers that know
    the task id directly. None on undetermined — fail-closed."""
    try:
        import cc_board
        return cc_board.list_owner_message_ids(task_id, env=None)
    except Exception:  # noqa: BLE001
        return None


def load_skip_approvals(run_dir: Path) -> dict:
    """Return {phase_id: approval_record} for every owner-authorized skip whose
    record is well-formed. A malformed, self-granted, or placeholder-timestamp
    record does NOT authorize a skip.

    Additional rejection criteria (FIX 4/E hardening — beyond the basic
    owner_approved:true + approved_by + reason requirement):

    (1) SELF-GRANT: approved_by contains markers indicating the producing agent
        approved its own skip ('executive strategy', 'via ... directive', 'self',
        'auto-approved', 'builder', 'producing'). Producing agents may NOT approve
        their own phase skips — only a real owner action counts.
    (2) PLACEHOLDER TIMESTAMP: timestamp ends with T00:00:00 or contains that pattern
        with timezone — midnight-exactly timestamps indicate a fabricated record.
        Timestamps must also carry a timezone component (Z or +/-HH:MM).
    (3) MISSING OWNER REFERENCE: record must have an owner_msg_id (a real Telegram
        message id) or an owner_action field tracing the skip to a verifiable human
        decision. Records with neither field are rejected.
    (4) AUTHENTICITY (FIX-1 — AF-FORGED-APPROVAL): EVERY skip record MUST carry a
        non-empty owner_msg_id, and that id must RESOLVE to a real owner-authored
        message in Command Center task_activities (the authoritative oracle).
        Presence of a string is NEVER proof — the live E2E forged "e2e-test-002"
        and it authorized 9+ skips. A record whose owner_msg_id does not resolve
        raises ForgedApprovalError, which the build fails on (AF-FORGED-APPROVAL).
        A record with ONLY an owner_action (no owner_msg_id) — or with no owner
        reference at all — has NO message id to resolve through the oracle and is
        exactly the self-forgery vector the live E2E used: it is ALSO
        AF-FORGED-APPROVAL and the build FAILS. An owner_action string alone is
        never proof of an owner decision; only a resolvable owner message counts."""
    p = run_dir / "working" / "checkpoints" / "phase_skip_approvals.json"
    approvals = {}
    if not p.exists():
        return approvals
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return approvals
    records = (obj if isinstance(obj, list)
               else obj.get("approvals", []) if isinstance(obj, dict) else [])

    _SELF_GRANT_MARKERS = (
        "executive strategy", "via ", "directive", "auto-approved",
        "self", "auto_approved", "producing", "builder",
    )

    # FIX-1: resolve the REAL owner-authored message ids ONCE for the run, before
    # walking records. None (undetermined) fails CLOSED for any owner_msg_id-bearing
    # record — a skip that cannot be proven authentic is DENIED, never passed.
    real_owner_msg_ids = _resolve_owner_msg_ids(run_dir)
    _oracle_unavailable = real_owner_msg_ids is None

    for rec in records:
        if not isinstance(rec, dict):
            continue

        # Basic required fields.
        if not (rec.get("owner_approved") is True
                and str(rec.get("phase_id", "")).strip()
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            continue

        approved_by_lower = str(rec.get("approved_by", "")).strip().lower()
        ts = str(rec.get("timestamp", "") or "")

        # (1) Reject self-granted approvals.
        if any(m in approved_by_lower for m in _SELF_GRANT_MARKERS):
            print(
                f"[load_skip_approvals] REJECTED phase {rec['phase_id']!r}: "
                f"approved_by {rec.get('approved_by')!r} contains a self-grant marker — "
                "producing agents may not approve their own skips.",
                file=sys.stderr,
            )
            continue

        # (2) Reject placeholder/timezone-free timestamps.
        if ts:
            _midnight = ts.endswith("T00:00:00") or "T00:00:00+" in ts or "T00:00:00Z" in ts
            if _midnight:
                print(
                    f"[load_skip_approvals] REJECTED phase {rec['phase_id']!r}: "
                    f"timestamp {ts!r} is a midnight placeholder — likely fabricated.",
                    file=sys.stderr,
                )
                continue
            _has_tz = ts.endswith("Z") or bool(re.search(r"[+-]\d{2}:\d{2}$", ts))
            if not _has_tz:
                print(
                    f"[load_skip_approvals] REJECTED phase {rec['phase_id']!r}: "
                    f"timestamp {ts!r} has no timezone — not a verifiable timestamp.",
                    file=sys.stderr,
                )
                continue

        # (3) AUTHENTICITY / REQUIRED MESSAGE ID (FIX-1 — AF-FORGED-APPROVAL).
        # EVERY skip record MUST carry a non-empty owner_msg_id — the FORGER's exact
        # vector was an owner_action-only record with no message id that passed
        # without any oracle query. There is no verifiable owner reference without a
        # message id, so a record with only an owner_action string (or neither field)
        # is SELF-FORGED: raise FATAL, never accept it. Undetermined is DENIED too
        # (never opens the gate).
        owner_msg_id = str(rec.get("owner_msg_id", "") or "").strip()
        owner_action = str(rec.get("owner_action", "") or "").strip()
        if not owner_msg_id:
            raise ForgedApprovalError(
                "AF-FORGED-APPROVAL: phase %r has NO owner_msg_id (owner_action=%r). "
                "Every phase-skip approval must carry a non-empty owner_msg_id that "
                "resolves to a real owner-authored message in Command Center "
                "task_activities. An owner_action string alone is never proof of an "
                "owner decision — a skip record without a resolvable message id is "
                "self-forged and is DENIED. Re-run the phase or obtain a genuine "
                "owner approval message." % (rec["phase_id"], owner_action)
            )

        # (4) RESOLVE through the authoritative oracle. The id must be proven real.
        if _oracle_unavailable:
            raise ForgedApprovalError(
                "AF-FORGED-APPROVAL: phase %r references owner_msg_id %r, but the "
                "Command Center owner-message oracle is UNDETERMINED (no cc_task_id "
                "on the run / board unreachable / endpoint did not prove the id). "
                "A skip that cannot be proven authentic is DENIED — undetermined "
                "never opens the gate." % (rec["phase_id"], owner_msg_id)
            )
        if owner_msg_id not in real_owner_msg_ids:
            raise ForgedApprovalError(
                "AF-FORGED-APPROVAL: phase %r references owner_msg_id %r, which does "
                "not resolve to a real owner-authored message in Command Center "
                "task_activities. Presence of a string is never proof of an owner "
                "message. Re-run the phase or obtain a genuine owner approval."
                % (rec["phase_id"], owner_msg_id)
            )

        # (4) FIX-2 (Error 2): QC phases are STRUCTURALLY UNSKIPPABLE. No owner
        # record — real or forged — can waive a QC phase. A skip record for
        # P1Q-COPY-QC / P-PROMPT-QC / P-TYPO-QC / P-SHIFT-QC is REFUSED outright.
        pid = str(rec["phase_id"]).strip()
        if pid in bd.UNSKIPPABLE_QC_PHASES:
            print(
                f"[load_skip_approvals] REFUSED phase {pid!r}: QC phases are "
                "structurally unskippable (AF-QC-SKIP) — no owner record can waive "
                "a QC phase.",
                file=sys.stderr,
            )
            continue

        approvals[rec["phase_id"]] = rec
    return approvals


def _expand_artifact_spec(run_dir: Path, spec: str) -> str:
    """Resolve a manifest produces_artifact spec against the run's deck slug.

    The manifest declares deck-owned artifacts as '{deck_slug}-templated' (e.g.
    'working/delivery/{deck_slug}-WEBINAR.mp4' or 'working/deliverables/
    {deck_slug}-WORKBOOK.pdf') — the same convention DELIVERABLES_REQUIRED and
    the client_package_files set use. The filesystem never contains a literal
    '{deck_slug}' directory/file, so every artifact-presence / sha check that
    consumes a produces_artifact spec MUST expand the placeholder to the run's
    deck slug (via _deck_slug) before comparing against disk. Missing/empty
    specs and specs with no placeholder pass through unchanged."""
    spec = (spec or "").strip()
    if not spec or "{deck_slug}" not in spec:
        return spec
    slug = _deck_slug(run_dir) or "deck"
    return spec.replace("{deck_slug}", slug)

def _artifact_present(run_dir: Path, produces_artifact: str) -> bool:
    """True when a phase's declared produces_artifact exists in the run dir.
    Supports glob patterns (e.g. 'working/research/brief-*.md'). A null/empty
    artifact spec counts as satisfied (the phase declares no concrete artifact).

    '{deck_slug}' placeholder in the spec is expanded to the run's deck slug
    first (the manifest convention for deck-owned artifacts like
    '{deck_slug}-WORKBOOK.pdf' / '{deck_slug}-WEBINAR.mp4')."""
    spec = _expand_artifact_spec(run_dir, produces_artifact)
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
    It additionally enforces produces_artifact presence for each prior phase.

    FIX 4b: also enforces AF-PHASE-REPORT-MISSING — every prior attested phase must
    have AF-PHASE-REPORT-START + AF-PHASE-REPORT-DONE records in client_reports.json.
    U046: a record that exists but was never DELIVERED (no gateway_msg_id and no
    recorded undeliverable) is reported in WARN mode and becomes fatal only when
    PRESENTATION_REPORT_CONFIRM_ENFORCE=1. This docstring previously claimed the gate
    required a non-empty gateway_msg_id; it never did."""
    by_id = {ph["id"]: ph for ph in phases}
    target = by_id.get(target_phase_id)
    if target is None:
        return f"AF-PHASE-SKIPPED: unknown phase id {target_phase_id!r} (not in manifest)."
    target_order = target.get("order", 0)
    # DESIGN-OPUS.md §4.2 — a defers_unless-gated phase that is NOT satisfied by
    # the intake answers is deferred (never surfaced, never a prerequisite). It is
    # excluded from the prior-phase walk so a deck-only run never hard-aborts on a
    # missing optional P-U-* phase.
    deferred = _deferred_phase_ids(run_dir, phases)
    prior = sorted([ph for ph in phases
                    if ph.get("order", 0) < target_order and ph["id"] not in deferred],
                   key=lambda p: p.get("order", 0))
    prior_ids = [ph["id"] for ph in prior]
    # FIX-1 (AF-FORGED-APPROVAL): validate skip-record AUTHENTICITY FIRST, before
    # the shared attestation/owner-skip gate runs. The shared gate accepts an
    # owner_msg_id-bearing record without resolving it; if a forged/msg-id-less
    # record short-circuits the shared gate BEFORE load_skip_approvals runs, the
    # failure surfaces as AF-PHASE-SKIPPED instead of the required AF-FORGED-APPROVAL.
    # Authenticity must win: a forged record authorizes nothing, so the build fails
    # on the forgery itself (the QC row demands AF-FORGED-APPROVAL).
    try:
        approvals = load_skip_approvals(run_dir)
    except ForgedApprovalError as _fae:
        # A forged skip-approval is an attempt to self-authorize a phase skip — the
        # build gate FAILS CLOSED (fatal string => exit 2 at caller).
        return str(_fae)
    # Shared attestation / owner-skip decision (build_deck is the single source of truth).
    reason = bd.check_phase_preconditions(run_dir, target_phase_id, prior_ids)
    if reason:
        return reason
    # Additionally require each attested prior phase's produces_artifact to be present
    # (an attestation must correspond to a real artifact, unless owner-skip-approved).
    for ph in prior:
        pid = ph["id"]
        if pid in approvals:
            continue
        if not _artifact_present(run_dir, ph.get("produces_artifact", "")):
            return (f"AF-PHASE-SKIPPED: prior phase {pid!r} is attested but its "
                    f"produces_artifact {ph.get('produces_artifact')!r} is not present in "
                    f"the run dir — an attestation must correspond to a real artifact. "
                    f"Re-run {pid!r} or add a logged owner-authorized skip.")
    # FIX 4b + U046: AF-PHASE-REPORT-MISSING — every prior attested phase must have
    # START + DONE records; delivery confirmation is warned on, and enforced only under
    # PRESENTATION_REPORT_CONFIRM_ENFORCE=1.
    report_reason = _check_prior_phase_reports(run_dir, phases, target_phase_id)
    if report_reason:
        return report_reason
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
    """Phase-0: OCR-engine availability pre-flight (AF-OCR-ENGINE-MISSING, MASTER-SPEC
    7.4) + FIX-14 agent-env pre-flight (AF-AGENT-ENV-MISSING / AF-AGENT-ENV-UNMANAGED)
    + detect box type (resource note) + Kie balance pre-flight. HARD-ABORT
    (exit 4) on AF-OCR-ENGINE-MISSING, AF-AGENT-ENV-*, or AF-KIE-BALANCE before any
    phase is dispatched — this runs before research/copy/QC as well as before
    render, the earliest possible point in the entire run."""
    platform = bd.detect_platform(run_dir, override=platform_override)
    worker_note = "mac -> fewer parallel render workers" if platform == "mac" else \
                  "vps -> more parallel render workers"
    print(f"=== PHASE-0 PRE-FLIGHT — box_type={platform} ({worker_note}) ===", flush=True)

    slide_count = _slide_count(run_dir, slides_path)
    print(f"=== PHASE-0 — deck slide_count={slide_count} ===", flush=True)

    if adhoc:
        print("=== PHASE-0 — adhoc (owner-authorized): OCR-engine + Kie balance "
              "pre-flight skipped ===", flush=True)
        attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck",
                     "preflight_ok_adhoc", artifact_sha="preflight-no-artifact")
        return

    # MASTER-SPEC 7.4 / AF-OCR-ENGINE-MISSING — checked FIRST (fast, local, no
    # network) and BEFORE the Kie API key is even loaded, so a box with no OCR
    # engine refuses before any network call, let alone before any phase or paid
    # render. Same in-process bd.ocr_engine_preflight() build_deck.py's own
    # Phase-0 block calls for a direct-invocation bypass — checking it HERE too
    # means the run refuses before research/copy/QC time is spent, not merely
    # before render.
    ocr_reason = bd.ocr_engine_preflight(run_dir)
    if ocr_reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + ocr_reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — OCR-engine pre-flight PASSED (engine available in this "
          "render environment) ===", flush=True)

    # FIX-14 — MC_API_TOKEN / MISSION_CONTROL_URL regression guard (Error 8 / D-8).
    # The 15-day 401 stall happened because the token was NOT in the gateway
    # service-env. check_agent_env.py probes the agent runtime env live-process-first
    # across the gateway service-env + secrets stores, AND verifies both labels are
    # in the OPENCLAW_SERVICE_MANAGED_ENV_KEYS regeneration allow-list (a token in a
    # store but not in that list is dropped on the next regeneration — the exact
    # regression shape). HARD-ABORT (exit 4) here, before any phase is dispatched,
    # so a box whose CC registration would silently 401 stops at minute zero.
    #
    # FAIL-CLOSED ON A MISSING MODULE: this preflight is wired into the canonical
    # runner, so a deployment that drops check_agent_env.py must NOT silently pass
    # the guard — a missing module reads as UNKNOWN and fails closed (AF-AGENT-ENV-
    # UNKNOWN), so a regression can never hide behind an absent probe.
    if _agent_env is not None:
        _env_report = _agent_env.probe()
        if _env_report["exit_code"] != 0:
            print("\n" + "!" * 78, file=sys.stderr)
            print("FATAL PHASE-0: %s (%s) — Command Center registration/delivery "
                  "would silently 401. See the stores checked + per-label presence "
                  "above; run regenerate-gateway-env.sh to wire the labels, restart "
                  "the gateway, then re-run." % (
                      _env_report["verdict"], _env_report["exit_code"]), file=sys.stderr)
            print("!" * 78 + "\n", file=sys.stderr)
            sys.exit(4)
        print("=== PHASE-0 — agent-env pre-flight PASSED (MC_API_TOKEN + "
              "MISSION_CONTROL_URL present and managed) ===", flush=True)
    else:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: AF-AGENT-ENV-UNKNOWN — check_agent_env.py is not "
              "co-located beside run_signature_deck.py. The FIX-14 regression guard "
              "cannot run, so this box refuses (fail-closed; a missing probe must "
              "never read as PASS). Install check_agent_env.py into the department "
              "scripts dir and re-run.", file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)

    # FIX-18 — TOOL-SCHEMA LOOP ALERT (Error 10 / D17). The 2026-08-06 E2E logged
    # 12x "args: must be object" + 3x "missing path" — the model serialized tool
    # args as a STRING and re-emitted schema dumps, burning a retry cycle per turn.
    # tool_schema_validator.py returns a NORMALIZED schema hint on a malformed
    # call (so the model self-corrects in one turn) and writes an AF-TOOL-SCHEMA-LOOP
    # event when a tool hits 5 CONSECUTIVE failures (so a loop is ALERTED, not
    # silently re-tried forever). This preflight HARD-ABORTS (exit 4) when a
    # prior phase already recorded such a loop event in this run's ledger.
    #
    # A missing validator module is NOT a delivery blocker (unlike FIX-14's env
    # probe): the validator is a mitigation, and the dept verify.sh self-test
    # catches a box that dropped it. Presence here proves the ledger is readable.
    if _tool_schema is not None:
        _loops = _tool_schema.active_loop_events(run_dir)
        if _loops:
            print("\n" + "!" * 78, file=sys.stderr)
            print("FATAL PHASE-0: %s — %d tool(s) hit %d consecutive schema "
                  "failures in this run. The model is looping on malformed tool "
                  "args; it must be re-oriented, not re-run. %s" % (
                      _loops[0]["event"]["code"], len(_loops),
                      _tool_schema.CONSECUTIVE_FAILURE_LIMIT,
                      _loops[0]["event"]["message"]), file=sys.stderr)
            print("!" * 78 + "\n", file=sys.stderr)
            sys.exit(4)
        print("=== PHASE-0 — tool-schema loop alert CLEAR (no AF-TOOL-SCHEMA-LOOP "
              "event in this run's ledger) ===", flush=True)
    else:
        print("=== PHASE-0 — tool_schema_validator.py not co-located; FIX-18 "
              "loop-alert SKIPPED (verify.sh self-test covers this; delivery "
              "proceeds) ===", flush=True)

    api_key = ""
    try:
        api_key = bd.load_api_key()
    except SystemExit:
        # No key on this box — the render-phase subprocess will fail loud on its own.
        print("=== PHASE-0 — no Kie API key on this box; balance pre-flight deferred to "
              "the render subprocess ===", flush=True)
    # FIX-E2E (incremental resume): mirror build_deck — count only the
    # UN-rendered slides for the balance floor so a resume/re-render (e.g. an
    # OCR-retry on 2 of 20 slides) needs credit for the remaining 2, not the
    # full deck. The pre-render phase passes the full slide_count; a
    # low-but-sufficient balance would otherwise brick every resume.
    try:
        _remaining_count = max(0, slide_count - len(bd._gather_rendered_pngs(run_dir)))
    except Exception:  # noqa: BLE001 — helper unavailable; fall back to full count
        _remaining_count = slide_count
    reason = bd.kie_balance_preflight(run_dir, _remaining_count, api_key or None)
    if reason:
        print("\n" + "!" * 78, file=sys.stderr)
        print("FATAL PHASE-0: " + reason, file=sys.stderr)
        print("!" * 78 + "\n", file=sys.stderr)
        sys.exit(4)
    print("=== PHASE-0 — Kie balance pre-flight PASSED (balance >= estimated floor) ===",
          flush=True)
    attest_phase(run_dir, "P-0-PREFLIGHT", "run_signature_deck", "preflight_ok",
                 artifact_sha="preflight-no-artifact")


# ---------------------------------------------------------------------------
# Plan printing
# ---------------------------------------------------------------------------
def _load_run_intake(run_dir: Path) -> dict:
    """Load the run's intake answers (working/copy/intake.json) for defers_unless
    gating. Best-effort — an absent/unparseable intake record returns {} and the
    gate then resolves to the questions' defaults (see presentation_job/defers.py)."""
    try:
        return load_intake(run_dir)
    except Exception:  # noqa: BLE001
        return {}


def _deferred_phase_ids(run_dir: Path, phases: list) -> set:
    """Return the set of phase ids whose defers_unless gate is NOT satisfied by
    the run's intake answers (DESIGN-OPUS.md §4.2). Deck-only runs (Q1=no, Q2=no)
    defer all 16 P-U-* phases; the deck core is unchanged."""
    intake = _load_run_intake(run_dir)
    return {p["id"] for p in phases if phase_is_deferred(p, intake)}


def print_plan(run_dir: Path, phases: list) -> None:
    attested = _attested_phase_ids(run_dir)
    deferred = _deferred_phase_ids(run_dir, phases)
    forged = None
    try:
        approvals = load_skip_approvals(run_dir)
    except ForgedApprovalError as _fae:
        # FIX-1: a forged skip-approval record must never print as
        # SKIP(owner-authorized). The phase shows `pending` and the fatal
        # AF-FORGED-APPROVAL is surfaced on stderr (the build gate fails on it).
        forged = str(_fae)
        approvals = {}
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    if forged:
        print("[load_skip_approvals] " + forged, file=sys.stderr, flush=True)
    print("=== SIGNATURE-DECK PHASE PLAN (manifest order) ===")
    for ph in ordered:
        pid = ph["id"]
        if pid in deferred:
            state = "DEFERRED"
        elif pid in attested:
            state = "ATTESTED"
        elif pid in approvals:
            state = "SKIP(owner-authorized)"
        else:
            state = "pending"
        print(f"  [{ph.get('order'):>5}] {pid:<16} {state:<22} "
              f"owner={ph.get('owning_role')}  -> {ph.get('produces_artifact')}")


# ---------------------------------------------------------------------------
# --next PHASE TURN-GATE (the runner is the agent's interface to "what is next")
# ---------------------------------------------------------------------------
def _next_required_phase(run_dir: Path, phases: list):
    """Return (phase_dict, k, N) for the FIRST phase in ascending `order` that is
    NEITHER attested NOR covered by a logged owner-authorized skip; or (None, N, N)
    when every phase is attested / skip-approved. This is the same ordered set the
    precondition gate walks, so the phase --next names is exactly the phase the next
    --phase call is allowed to attest."""
    attested = _attested_phase_ids(run_dir)
    deferred = _deferred_phase_ids(run_dir, phases)
    try:
        approvals = set(load_skip_approvals(run_dir).keys())
    except ForgedApprovalError as _fae:
        # FIX-1: a forged skip-approval must not count as skip-approved — the
        # phase stays `pending` and --next serves it as the required next phase.
        print("[load_skip_approvals] " + str(_fae), file=sys.stderr, flush=True)
        approvals = set()
    ordered = sorted(phases, key=lambda p: p.get("order", 0))
    total = len(ordered)
    for i, ph in enumerate(ordered):
        pid = ph["id"]
        if pid in deferred or pid in attested or pid in approvals:
            continue
        return ph, i + 1, total
    return None, total, total


# ---------------------------------------------------------------------------
# FIX-19 (D18) — right-size tool results. The --next payload hands the agent SOP
# refs as bare filenames; reading one WHOLE (a 34-102KB SOP/role file) returns a
# tool result the harness truncates ([tool-result-truncation] fired 33x in the
# 2026-08-06 E2E). Each sop_ref is enriched with its resolved size + a
# read_slice hint so the agent fetches ONLY the slice it needs.
# ---------------------------------------------------------------------------
def _sop_slice_guidance(sop_refs: list, run_dir: Path) -> list:
    """Return [{ref, size_bytes, resolved, read_slice_hint, kind}] per sop_ref.

    The hint is the exact CLI that returns just that slice; 'index' means the
    ref is > MAX_SLICE_BYTES and the agent should run read_slice.py --index
    first to find the section, then --lines to fetch it. Never raises: a ref
    that cannot be resolved is returned with a null hint (the agent still has
    the filename to read conventionally)."""
    try:
        import read_slice as _rs
    except Exception:  # noqa: BLE001
        _rs = None
    out = []
    for ref in sop_refs:
        entry = {"ref": ref}
        if _rs is not None:
            try:
                resolved = _rs._find_sop_file(ref, Path(__file__).resolve().parent)
            except Exception:  # noqa: BLE001
                resolved = None
            if resolved is not None and resolved.is_file():
                size = resolved.stat().st_size
                entry.update({
                    "resolved": str(resolved),
                    "size_bytes": size,
                    "kind": "sop",
                    "read_slice_hint":
                        f"python3 read_slice.py {ref} --index   # {size}B SOP — find the section"
                        if size > _rs.MAX_SLICE_BYTES
                        else f"python3 read_slice.py {ref} --lines A-B   # {size}B SOP",
                    "sliced_read_required": size > _rs.MAX_SLICE_BYTES,
                })
            else:
                entry.update({"resolved": None, "size_bytes": None,
                              "kind": "unresolved",
                              "read_slice_hint": None})
        out.append(entry)
    return out


def emit_next(run_dir: Path, phases: list) -> None:
    """--next PHASE TURN-GATE. Emits ONE JSON payload for ONLY the single next
    required phase — its id/order/owning role, the artifact contract
    (produces_artifact path + the manifest's required_brief_categories 'keys' + a
    flag for whether a substance verifier runs at attest time), the SOP refs, the
    gate codes, and the EXACT attest command to run next. It DELIBERATELY does not
    reveal any phase further ahead: the process is served one step at a time so the
    orchestrating agent cannot 'go off the laid-out process'. Read-only (no run
    work, no nonce needed); use --plan for the full phase list."""
    runner_rel = "run_signature_deck.py"
    ph, k, total = _next_required_phase(run_dir, phases)
    if ph is None:
        print(json.dumps({
            "schema": "phase_turn_gate/v1",
            "run_dir": str(run_dir),
            "next_phase": None,
            "status": "all_phases_complete",
            "attested_of_total": [total, total],
            "doctrine_home": "universal-sops/PRESENTATION-MASTER-DOCTRINE.md",
            "message": ("Every manifest phase is attested (or covered by a logged "
                        "owner-authorized skip). There is no next phase to serve; the "
                        "governed pipeline is complete."),
        }, indent=2))
        return

    pid = ph["id"]
    needs_out = pid == "P4-RENDER"
    attest_cmd = (
        f"python3 {runner_rel} --run-dir {run_dir} --slides <slides.json>"
        + (" --out <out.pptx>" if needs_out else "")
        + f" --phase {pid}"
    )
    payload = {
        "schema": "phase_turn_gate/v1",
        "run_dir": str(run_dir),
        "position": {"step": k, "of": total},
        "next_phase": {
            "id": pid,
            "order": ph.get("order"),
            "name": ph.get("name", pid),
            "owning_role": ph.get("owning_role", ""),
            "artifact_contract": {
                "produces_artifact": ph.get("produces_artifact", ""),
                "required_brief_categories": ph.get("required_brief_categories", []),
                "has_substance_verifier": pid in _GOVERNED_VERIFIER_PHASES,
            },
            "sop_refs": _sop_slice_guidance(ph.get("sop_refs", []), run_dir),
            "gate_codes": ph.get("gate_codes", []),
            "client_report": ph.get("client_report"),
            "attest_command": attest_cmd,
        },
        "doctrine_home": "universal-sops/PRESENTATION-MASTER-DOCTRINE.md",
        "read_slice_doctrine": (
            "FIX-19: SOP files are 25-125KB. NEVER read one whole — a whole-file "
            "tool result is truncated ([tool-result-truncation], D18) and you "
            "reason from incomplete context. For each sop_ref use its "
            "read_slice_hint: run `python3 read_slice.py <ref> --index` to find "
            "the section, then `--lines A-B` to fetch only that slice. A sliced "
            "read returns just the slice; the truncation counter stays 0."
        ),
        "instruction": (
            "Do EXACTLY this one phase: produce its produces_artifact per the cited "
            "sop_refs, then run the attest_command to verify + attest it. Then run "
            "--next again for the following step. This runner will not reveal any "
            "phase further ahead, and will refuse (AF-PHASE-SKIPPED) to attest out of "
            "order — the process is served one step at a time."
        ),
    }
    print(json.dumps(payload, indent=2))


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
    # FIX-1 / D20: adhoc authorization is folded into the SAME authenticity oracle
    # as phase-skip approvals. EVERY adhoc record MUST carry a non-empty owner_msg_id
    # and that id must resolve to a real owner-authored message. A record with only
    # owner_approved/approved_by/reason but NO owner_msg_id is exactly the self-written
    # bypass (D20) — it has no message to resolve through the oracle, so it is FORGED
    # and the run is refused. Undetermined is DENIED too (never opens the gate).
    _adhoc_obj = json.loads(p.read_text())
    _adhoc_owner_msg_id = str(_adhoc_obj.get("owner_msg_id", "") or "").strip()
    if not _adhoc_owner_msg_id:
        print("FATAL: AF-FORGED-APPROVAL — --adhoc record has NO owner_msg_id. "
              "Every adhoc authorization must carry a non-empty owner_msg_id that "
              "resolves to a real owner-authored message in Command Center "
              "task_activities. An owner_action/approved_by string alone is never "
              "proof of an owner decision — a self-written ad-hoc authorization "
              "with no message id is FORGED and is DENIED.", file=sys.stderr)
        sys.exit(2)
    _real_ids = _resolve_owner_msg_ids(run_dir)
    if _real_ids is None:
        print("FATAL: AF-FORGED-APPROVAL — --adhoc references owner_msg_id "
              f"{_adhoc_owner_msg_id!r}, but the Command Center owner-message "
              "oracle is UNDETERMINED (no cc_task_id on the run / board "
              "unreachable). A self-authored ad-hoc authorization that cannot be "
              "proven is DENIED.", file=sys.stderr)
        sys.exit(2)
    if _adhoc_owner_msg_id not in _real_ids:
        print("FATAL: AF-FORGED-APPROVAL — --adhoc references owner_msg_id "
              f"{_adhoc_owner_msg_id!r}, which does not resolve to a real "
              "owner-authored message in Command Center task_activities. A "
              "self-written ad-hoc authorization is not a genuine owner approval.",
              file=sys.stderr)
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
                 max_attempts=None, phases=None) -> int:
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
    refused so the failing work physically cannot advance.

    FIX 4/E: computes a real artifact sha for the QC report before attesting (sha must
    be non-empty). FIX 5d: records substance_verified=True on qc_pass_measurer attest."""
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

    # Resolve produces_artifact spec for sha computation (FIX 4/E).
    _produces_art = _QC_PRODUCES_ARTIFACT.get(phase, "")
    if phases is not None:
        ph_entry = next((p for p in phases if p["id"] == phase_id), None)
        if ph_entry:
            _produces_art = ph_entry.get("produces_artifact", _produces_art)

    routeback_path = None
    consumed = _count_routebacks(run_dir, phase)  # attempts already written (cross-invocation)
    while True:
        if routeback_path is not None and reauthor is not None:
            print(f"=== {phase} attempt {consumed}: re-authoring FAILING slides only via "
                  f"{role} ({routeback_path.name}) ===", flush=True)
            reauthor(role, routeback_path, consumed)

        verdict = measurer(run_dir)
        if _verdict_pass(verdict):
            sha = _compute_artifact_sha(run_dir, _produces_art)
            attest_phase(run_dir, phase_id, owning_role, "qc_pass_measurer",
                         artifact_sha=sha, substance_verified=True)
            print(f"=== {phase} PASS (deterministic measurer) — phase {phase_id} attested; "
                  f"downstream unblocked ===", flush=True)
            return 0

        if consumed >= max_attempts:
            rec = bd._owner_skip_approved(run_dir, af_code)
            if rec:
                sha = _compute_artifact_sha(run_dir, _produces_art)
                attest_phase(run_dir, phase_id, owning_role, "qc_owner_override",
                             artifact_sha=sha, substance_verified=False)
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
                        reauthor=reauthor, max_attempts=max_attempts, phases=phases)


def run_copy_qc_loop(run_dir: Path, phases=None, *, reauthor=None,
                     max_attempts=None) -> int:
    """COPY-QC send-back loop (G8). Fires AFTER the script is written, BEFORE any image
    prompt is authored. Exit gate is the composed WRITING + PRICING engine measurer
    (Story villain-before-hero, Emotional felt-stakes, pricing promise-before-price +
    cadence, narrative harmony). A broken script routes back; no prompts are authored
    until the copy passes."""
    return _run_qc_loop(run_dir, "COPY-QC", _measure_copy_qc,
                        reauthor=reauthor, max_attempts=max_attempts, phases=phases)


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
# Command Center board — TERMINAL delivery close (FAIL-SOFT). Ownership note:
# build_deck.py runs the RENDER phase and drives the card's in-run motion — the
# P4-RENDER START (backlog->in_progress) and the P4/P8 render/assemble PROGRESS
# ACTIVITY posts — but it CANNOT close the card: the terminal producer close is a
# task-level status='review' that carries the process_certificate_sha (the ticket
# INTO review) + the real per-gate QC scores, and that certificate does not exist
# until prove-deck.py mints delivery/<SLUG>-FINAL/PROCESS-CERTIFICATE.json here in the
# P9-DELIVER phase. So the RUNNER owns the terminal close and fires it right after
# prove-deck PASS. The producer NEVER self-closes to 'done' — the CC-side QC scorer /
# Devil's-Advocate gate promotes 'review'->'done'. The move receipt
# (working/checkpoints/cc-board.json) is the SAME run dir build_deck wrote to, so the
# render-phase activities and this close land on one consistent ledger.
# ---------------------------------------------------------------------------
def _board_ingest_preflight(run_dir, adhoc: bool = False) -> None:
    """FIX-PRES-08(a): ensure the deck's Command Center card exists at Phase-0,
    BEFORE any phase is dispatched — so the hours of pre-render phases are
    board-visible and a pre-render death still lands a card (build_deck previously
    created the card only at render-begin). Idempotent + FAIL-SOFT: a card already
    stamped in the manifest (this run, an earlier --phase invocation) is a clean
    no-op; a disabled/unreachable board is a no-op; NEVER raises (the board is a
    view, never a gate). Skipped for adhoc runs (not CC-tracked). The later
    build_deck render-begin ingest is idempotent and reuses this task_id."""
    if adhoc:
        return
    try:
        import cc_board
        if cc_board._read_manifest(run_dir).get("cc_task_id"):
            return  # already ingested earlier this run
        slug = _deck_slug(run_dir)
        rcid, rchan = cc_board.resolve_requester(run_dir)
        if not rcid:
            # Rule 3.5 WARN-MODE, stage 1 of 3
            print("[cc_board] WARN-REQUESTER-MISSING: this deck has no requester chat id "
                  "(checked working/copy/intake.json and the PRESENTATION_REQUESTER_CHAT_ID / "
                  "ROUTE_PRES_REQUESTER_CHAT_ID / MC_ROUTE_REQUESTER_CHAT_ID environment keys). "
                  "The client will receive NO acknowledgement, progress or completion message "
                  "for this build. Route presentation requests with the chat id set.",
                  file=sys.stderr, flush=True)
        cc_board.ingest_deck_task(
            run_dir, slug, title=slug, description=f"Deck build: {slug}",
            requester_chat_id=rcid, requester_channel=rchan)
    except Exception as exc:  # noqa: BLE001 — board is best-effort, never a gate
        print(f"[cc_board] Phase-0 pre-flight ingest raised ({exc}) — run continues; "
              "the card will be (re)ingested idempotently at render-begin.",
              file=sys.stderr, flush=True)


def _board_close_delivery(run_dir) -> None:
    """Fire the TERMINAL Command Center card close for a delivered deck, FAIL-SOFT.

    The producer STOPS at 'review': the presentations pipeline never self-closes to
    'done'. Promotion 'review'->'done' is the CC-side QC scorer / Devil's-Advocate
    gate's job — the same interlock every sibling department respects. This close
    hands the card to that reviewer with (a) the real per-gate QC scores posted as
    activities and folded into the review note + a structured qc_scores key, and
    (b) the PROCESS-CERTIFICATE sha as the ticket INTO review.

    Precondition: called ONLY after prove-deck.py has minted the run's
    PROCESS-CERTIFICATE, so cc_board.patch_phase(status='review') can read and attach
    its process_certificate_sha. The task_id is recovered from
    working/checkpoints/process_manifest.json (stamped at run-begin by build_deck's
    ingest). A disabled board or a missing id is a clean no-op. NEVER raises — the
    board is a view, never a gate."""
    try:
        import cc_board
        tid = None
        try:
            _pm = Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"
            if _pm.exists():
                tid = (json.loads(_pm.read_text()) or {}).get("cc_task_id")
        except Exception:  # noqa: BLE001 — a bad manifest read is never fatal
            tid = None
        if not tid:
            return
        # Per-gate QC grades onto the activity feed FIRST (so they precede the
        # status move in the timeline), then the terminal producer close to 'review'.
        cc_board.post_qc_activities(run_dir, tid)
        cc_board.patch_phase(run_dir, tid, DELIVERY_PHASE_ID, "review",
                             note="bundle complete — deck delivered; awaiting CC QC "
                                  "scorer / Devil's-Advocate promotion to done")
    except Exception as exc:  # noqa: BLE001 — the board is a view, never a gate
        print(f"[cc_board] terminal delivery close raised ({exc}) — run continues; "
              "the board update is best-effort.", file=sys.stderr, flush=True)


def _board_assert_advanced(run_dir) -> None:
    """VISIBILITY-ONLY, at the runner's true end: note when a completed run recorded
    ZERO successful board advances (board disabled, or every advance failed — the
    detail is in working/checkpoints/cc-board.json). NEVER blocks and NEVER raises."""
    try:
        import cc_board
        # FIX-PRES-08(b): before reporting, replay any outstanding failed advance
        # (e.g. a transport-failed terminal close) so a delivered deck is not left
        # stranded at in_progress with no retry. FAIL-SOFT, idempotent.
        try:
            cc_board.reconcile(run_dir)
        except Exception:  # noqa: BLE001 — reconcile is best-effort
            pass
        if not cc_board.assert_min_one_advance(run_dir):
            print("[cc_board] NOTE: no successful board advance recorded for this run "
                  "(board disabled, or every advance failed — see "
                  "working/checkpoints/cc-board.json).", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 — the visibility check is best-effort
        pass


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
    ap.add_argument("--next", dest="want_next", action="store_true",
                    help="print ONLY the single next required phase (turn-gate) as one "
                         "JSON payload and exit; read-only, no nonce needed")
    ap.add_argument("--adhoc", action="store_true",
                    help="owner-authorized + logged escape (refused without the record)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        sys.exit(2)

    manifest = load_manifest()
    phases = manifest["phases"]

    # --plan inspect is allowed without the front-door marker (read-only, no run work).
    if args.plan:
        print_plan(run_dir, phases)
        sys.exit(0)

    # --next PHASE TURN-GATE: the runner (not prose) is the agent's interface to
    # "what is next." Read-only — emits ONLY the single next required phase and does
    # no run work, so (like --plan) it is exempt from the front-door nonce handshake.
    if args.want_next:
        emit_next(run_dir, phases)
        sys.exit(0)

    # FRONT-DOOR NONCE HANDSHAKE (CONTRACT #8): run_signature_deck.py MUST be invoked
    # via presentation-canonical-entry.sh, which mints a per-run random nonce (exports
    # OC_DECK_ENTRY_NONCE and writes the matching 0600 file
    # <run-dir>/working/checkpoints/.canonical-entry-nonce). This SUPERSEDES the retired
    # OC_DECK_CANONICAL_ENTRY env marker, which shipped in box-visible comments and was
    # forgeable by any model that read the repo. Direct `python3 run_signature_deck.py`
    # — or a guessed/stale nonce — is structurally denied. --plan is exempt (handled
    # above, read-only inspection). The nonce check is the single source of truth
    # (build_deck._verify_entry_nonce) shared with the render subprocess.
    if not bd._verify_entry_nonce(run_dir):
        print(
            "FATAL: must be invoked via presentation-canonical-entry.sh — the per-run "
            "front-door nonce (OC_DECK_ENTRY_NONCE) is missing or does not match "
            "<run-dir>/working/checkpoints/.canonical-entry-nonce. Direct invocation is "
            "denied (front-door enforcement; retired marker: OC_DECK_CANONICAL_ENTRY).",
            file=sys.stderr,
        )
        sys.exit(2)

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

    # FIX-PRES-08(a): open the CC card NOW (Phase-0), so every pre-render phase is
    # board-visible and a pre-render death still lands a card. Idempotent + fail-soft.
    _board_ingest_preflight(run_dir, adhoc=args.adhoc)

    # FIX 4a: write the step contract + emit the up-front step-list client message.
    # IDEMPOTENT — skips if declared_plan.json already exists on a re-run of any phase.
    declare_plan(run_dir, phases)

    # Single-phase dispatch: enforce preconditions (AF-PHASE-SKIPPED), then dispatch.
    if args.phase:
        if not args.adhoc:
            reason = check_phase_preconditions(run_dir, phases, args.phase)
            if reason:
                print("\nFATAL: " + reason, file=sys.stderr)
                sys.exit(2)
        target = next((p for p in phases if p["id"] == args.phase), None)

        # FIX 4b: emit AF-PHASE-REPORT-START so the next phase's precondition gate
        # can confirm this phase was properly started (AF-PHASE-REPORT-MISSING check).
        _k, _N = _phase_index(args.phase, phases)
        emit_client_report(run_dir, args.phase, "start", k=_k, N=_N)

        # --- SHIFT-LEFT QC SEND-BACK LOOPS (v15.0.0) ---
        # COPY-QC fires before ANY prompt is authored; PROMPT-QC before ANY render. The
        # exit gate is the deterministic measurer, never the QC agent's self-score. On a
        # fail the loop writes a per-slide work order and DOES NOT attest, so the next
        # phase (prompt authoring / render) is structurally blocked until it passes.
        if args.phase == COPY_QC_PHASE_ID:
            rc = run_copy_qc_loop(run_dir, phases)
            if rc == 0:
                # FIX 4b: emit AF-PHASE-REPORT-DONE after measurer confirms pass.
                emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)
            sys.exit(rc)
        if args.phase == PROMPT_QC_PHASE_ID:
            rc = run_prompt_qc_loop(run_dir, phases)
            if rc == 0:
                # FIX 4b: emit AF-PHASE-REPORT-DONE after measurer confirms pass.
                emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)
            sys.exit(rc)
        # PRE-ASSEMBLY deck-harmony checkpoint (G5, placement 3) — fires before the deck
        # is assembled, then falls through to the normal artifact-present attestation.
        if args.phase == ASSEMBLE_PHASE_ID:
            rc = pre_assembly_harmony_checkpoint(run_dir)
            if rc != 0:
                sys.exit(rc)

        # The render phase and P9.5-NOTES-SYNC are the two phases this runner
        # dispatches into build_deck.py as a subprocess; all other phases are
        # produced by their owning department role/agent, and the runner records
        # their attestation once their produces_artifact is present.
        if args.phase == "P4-RENDER":
            if not args.out:
                print("FATAL: --out is required to dispatch the render phase.",
                      file=sys.stderr)
                sys.exit(2)
            # FIX-E2E attest-existing: if ALL rendered slides are already present
            # AND every post-render gate passes (OCR readback 20/20, image-QC
            # present + vision, visual-variety), attest P4-RENDER from the
            # existing verified renders instead of unconditionally re-submitting
            # the batch. This makes a genuine canonical render (already produced,
            # verified) attestable without a wasteful, non-deterministic
            # re-render that overwrites the verified set. Still goes through the
            # canonical runner's front-door nonce + phase-precondition chain; no
            # bypass. Mirrors the resume design intent (count only un-rendered
            # slides at the balance gate) — the batch submit honoring it here.
            _rendered = bd._gather_rendered_pngs(run_dir)
            _expected_n = _slide_count(run_dir, slides_path)
            if _rendered and len(_rendered) >= _expected_n:
                _gates_ok = True
                _gate_msgs = []
                for _gfn in (bd.check_ocr_readback, bd.check_image_qc_present,
                             bd.check_image_qc_vision, bd.check_visual_variety):
                    try:
                        _msg = _gfn(run_dir)
                    except Exception as _e:  # noqa: BLE001
                        _msg = f"{getattr(_gfn, '__name__', _gfn)} raised: {_e}"
                    if _msg:
                        _gates_ok = False
                        _gate_msgs.append(str(_msg))
                if _gates_ok:
                    # Genuine canonical renders verified — attest P4-RENDER from
                    # the existing set. artifact_sha = hash of the renders' names
                    # (proves the produces_artifact was inspected; FIX 4/E).
                    _render_sha = _hash_render_set(run_dir)
                    # Also record the genuine build_deck 'render' phase record
                    # (real taskIds/sha256s from pending_tasks.json) so the
                    # delivery boundary gate's AF-NOT-KIE-RENDERED check passes
                    # with the actual render that happened (FIX-E2E).
                    _write_render_record_from_existing(run_dir, Path(args.out).resolve())
                    attest_phase(run_dir, "P4-RENDER", "run_signature_deck",
                                 "artifact_present",
                                 artifact_sha=_render_sha,
                                 substance_verified=True)
                    print("=== P4-RENDER ATTESTED from existing verified renders "
                          f"({len(_rendered)}/{_expected_n} slides, all gates "
                          "passing) — no re-render needed (FIX-E2E attest-existing) ===",
                          flush=True)
                    emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)
                    sys.exit(0)
                print("NOTE: existing renders present but gates not all green "
                      f"({_gate_msgs}) — falling through to the canonical batch "
                      "render.", file=sys.stderr, flush=True)
            rc = _dispatch_render(run_dir, slides_path, Path(args.out).resolve(),
                                  platform=args.platform, adhoc=args.adhoc)
            if rc == 0:
                # FIX 4b: emit AF-PHASE-REPORT-DONE after successful render subprocess.
                emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)
            sys.exit(rc)
        # P9.5-NOTES-SYNC: reorder the notes-pane injection to AFTER the speech has
        # been written and QC-passed (P9-SPEECH + P-SPEECH-QC attested — the
        # ordinary precondition gate above already enforces that before this branch
        # is reached). Reopens the assembled .pptx and re-injects per-slide notes.
        if args.phase == NOTES_SYNC_PHASE_ID:
            if not args.out:
                print("FATAL: --out is required to dispatch P9.5-NOTES-SYNC.",
                      file=sys.stderr)
                sys.exit(2)
            rc = _dispatch_notes_sync(run_dir, slides_path, Path(args.out).resolve(),
                                      adhoc=args.adhoc)
            if rc == 0:
                # FIX 5d parity: run the substance verifier (same governed-phase
                # contract as the generic artifact-present branch below) before
                # attesting. Explicit attestation is needed here (unlike P4-RENDER)
                # because build_deck.py's --notes-sync writes notes_sync.json, not a
                # process_manifest.json "phases" record with the render special-case.
                if _pv is not None:
                    _ns_ok, _ns_reasons = _pv.verify(args.phase, run_dir)
                elif args.phase in _GOVERNED_VERIFIER_PHASES and not _degraded_verifiers_allowed(run_dir):
                    _ns_ok, _ns_reasons = False, [
                        "phase_verifiers.py missing beside the runner — P9.5-NOTES-SYNC "
                        "cannot attest without its substance verifier."]
                else:
                    _ns_ok, _ns_reasons = True, ["phase_verifiers unavailable — degraded pass"]
                if not _ns_ok:
                    print("\n" + "!" * 78, file=sys.stderr)
                    print(f"FATAL: substance verifier failed for phase {args.phase!r}:",
                          file=sys.stderr)
                    for _r in _ns_reasons:
                        print("  - " + str(_r), file=sys.stderr)
                    print("!" * 78 + "\n", file=sys.stderr)
                    sys.exit(EXIT_QC_ROUTEBACK)
                _sha = _compute_artifact_sha(run_dir, "working/checkpoints/notes_sync.json")
                attest_phase(run_dir, args.phase, "pptx-assembly-specialist",
                            "artifact_present", artifact_sha=_sha,
                            substance_verified=True)
                emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)
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
            try:
                phase_skips = set(load_skip_approvals(run_dir).keys())
            except ForgedApprovalError as _fae:
                # FIX-1: delivery may not proceed past a forged skip-approval — the
                # forged record authorizes nothing, so the attestation chain is
                # incomplete and delivery FAILS CLOSED (AF-FORGED-APPROVAL).
                print("\n" + "!" * 78, file=sys.stderr)
                print("FATAL PRE-DELIVERY: " + str(_fae), file=sys.stderr)
                print("!" * 78 + "\n", file=sys.stderr)
                sys.exit(EXIT_GUARD_BLOCK)
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

            # OUT-OF-BAND DELIVERY BOUNDARY GATE — inspect the SHIPPED ARTIFACT itself,
            # fail-closed, regardless of how it was produced.
            try:
                import delivery_gate as dg
                deck_art = None
                for cand in sorted(run_dir.glob("delivery/*-FINAL/*-FINAL.pptx")):
                    if not cand.name.startswith("~$"):
                        deck_art = cand
                        break
                if deck_art is None:
                    pptxs = [p for p in sorted(run_dir.glob("**/*.pptx"))
                             if not p.name.startswith("~$")]
                    deck_art = pptxs[-1] if pptxs else None
                if deck_art is None:
                    print("\n" + "!" * 78, file=sys.stderr)
                    print("FATAL PRE-DELIVERY: AF-BUNDLE-COMPLETE — no delivered *-FINAL.pptx "
                          "artifact found in the run dir; nothing to deliver.", file=sys.stderr)
                    print("!" * 78 + "\n", file=sys.stderr)
                    sys.exit(EXIT_GUARD_BLOCK)
                ok_art, reasons_art = dg.gate_delivered_artifact(deck_art, run_dir)
                if not ok_art:
                    hard = [r for r in reasons_art if not r.startswith("NOTE")]
                    print("\n" + "!" * 78, file=sys.stderr)
                    print("FATAL PRE-DELIVERY (BOUNDARY GATE): the SHIPPED artifact "
                          f"{deck_art.name} cannot be delivered:", file=sys.stderr)
                    for r in hard:
                        print("  - " + r, file=sys.stderr)
                    print("The ONLY bypass is a logged owner_skip_approval token "
                          "(gate=<AF code>). An agent may NOT self-approve.", file=sys.stderr)
                    print("!" * 78 + "\n", file=sys.stderr)
                    sys.exit(EXIT_GUARD_BLOCK)
                print("=== DELIVERY-BOUNDARY-GATE: PASS — shipped artifact is a kie-baked, "
                      "image-only deck with a complete deliverable bundle ===", flush=True)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                print("\n" + "!" * 78, file=sys.stderr)
                print(f"FATAL PRE-DELIVERY (BOUNDARY GATE): delivery_gate boundary check "
                      f"raised {exc!r} — cannot prove the shipped artifact is deliverable "
                      "(fail-closed).", file=sys.stderr)
                print("!" * 78 + "\n", file=sys.stderr)
                sys.exit(EXIT_GUARD_BLOCK)

            # FIX-8: FULL 9-DELIVERABLE BUNDLE GATE (AF-BUNDLE-INCOMPLETE).
            # The delivery boundary gate above proves the SHIPPED .pptx/.pdf and the
            # SIX-file client package. This gate separately enforces the NINE-file
            # OPERATOR build bundle (deck_pptx, deck_pdf, guide_pdf, speech_md,
            # speech_pdf, speech_fish_md, audio_mp3, infographic_png,
            # teleprompter_html) — the M2-M9 gap from the live E2E (task e738cff0),
            # where only the deck PPTX existed. Fail-closed: a partial bundle can
            # never be reported 'done', and the gate writes bundle_complete.json only
            # when all nine are present and non-empty. The ONLY bypass is a logged
            # owner_skip_approval token (gate=AF-BUNDLE-INCOMPLETE) — never an
            # agent's own choice.
            try:
                import fix_bundle_complete as fbc
                _bundle_dir = fbc.resolve_bundle_dir(run_dir)
                _bundle_ok, _bundle_missing, _bundle_gate = fbc.run_bundle_gate(
                    _bundle_dir, deck_slug=_deck_slug(run_dir))
                if not _bundle_ok:
                    print("\n" + "!" * 78, file=sys.stderr)
                    print("FATAL PRE-DELIVERY (BUNDLE GATE): AF-BUNDLE-INCOMPLETE — the "
                          f"full 9-deliverable bundle is incomplete in {_bundle_dir}:",
                          file=sys.stderr)
                    for _k in sorted(_bundle_missing):
                        print(f"  - {_k}", file=sys.stderr)
                    print("Re-run the upstream producer roles (guide / speech / audio / "
                          "infographic / teleprompter) until all nine exist and are "
                          "non-empty before attesting P9-DELIVER.", file=sys.stderr)
                    print("The ONLY bypass is a logged owner_skip_approval token "
                          "(gate=AF-BUNDLE-INCOMPLETE). An agent may NOT self-approve.",
                          file=sys.stderr)
                    print("!" * 78 + "\n", file=sys.stderr)
                    sys.exit(EXIT_GUARD_BLOCK)
                print("=== FULL-9-BUNDLE GATE: PASS — all nine operator deliverables "
                      f"present and non-empty (bundle_complete.json: {_bundle_gate}) ===",
                      flush=True)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                print("\n" + "!" * 78, file=sys.stderr)
                print(f"FATAL PRE-DELIVERY (BUNDLE GATE): fix_bundle_complete raised "
                      f"{exc!r} — the full 9-deliverable bundle cannot be proven "
                      "(fail-closed).", file=sys.stderr)
                print("!" * 78 + "\n", file=sys.stderr)
                sys.exit(EXIT_GUARD_BLOCK)

            # FIX 2: prove-deck.py — end-of-process no-skip proof (AF-PROCESS-INTEGRITY).
            # Walks every declared step and asserts ordered / validated / reported.
            # Exit 9 from prove-deck is a HARD block on delivery attestation.
            prove_deck_path = HERE / "prove-deck.py"
            try:
                pd_proc = subprocess.run(
                    [sys.executable, str(prove_deck_path), "--run-dir", str(run_dir)],
                    capture_output=True, text=True, timeout=300,
                )
                if pd_proc.returncode != 0:
                    print("\n" + "!" * 78, file=sys.stderr)
                    print(
                        "FATAL PRE-DELIVERY: AF-PROCESS-INTEGRITY — "
                        + (pd_proc.stdout + pd_proc.stderr).strip(),
                        file=sys.stderr,
                    )
                    print("!" * 78 + "\n", file=sys.stderr)
                    sys.exit(EXIT_GUARD_BLOCK)
                print("=== PROVE-DECK: PASS — AF-PROCESS-INTEGRITY satisfied; "
                      "PROCESS-CERTIFICATE written ===", flush=True)
            except FileNotFoundError:
                print(
                    f"FATAL PRE-DELIVERY: AF-PROCESS-INTEGRITY — prove-deck.py not found "
                    f"at {prove_deck_path}; delivery is blocked (fail-closed).",
                    file=sys.stderr,
                )
                sys.exit(EXIT_GUARD_BLOCK)
            except subprocess.TimeoutExpired:
                print(
                    "FATAL PRE-DELIVERY: AF-PROCESS-INTEGRITY — prove-deck.py timed out "
                    "(>300s); delivery is blocked (fail-closed).",
                    file=sys.stderr,
                )
                sys.exit(EXIT_GUARD_BLOCK)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"FATAL PRE-DELIVERY: AF-PROCESS-INTEGRITY — prove-deck.py raised "
                    f"{exc!r}; delivery is blocked (fail-closed).",
                    file=sys.stderr,
                )
                sys.exit(EXIT_GUARD_BLOCK)

            # BOARD (terminal close): prove-deck just minted the run's
            # PROCESS-CERTIFICATE, so this is the ONLY correct moment to close the CC
            # card — a task-level status='review' whose process_certificate_sha cc_board
            # reads from that freshly-minted cert (the ticket INTO review) plus the real
            # per-gate QC scores. The producer STOPS at review; the CC QC scorer /
            # Devil's-Advocate gate promotes to done. build_deck ran the RENDER phase
            # before any cert existed and therefore never emits this close. FAIL-SOFT:
            # never raises, never blocks.
            _board_close_delivery(run_dir)

        # OPT-IN EXECUTOR DISPATCH — the central fix: a phase whose manifest entry
        # declares a non-null, well-formed script executor (currently P8.1-PDF-EXPORT,
        # P8.2-GUIDE, P8.4-FISH-TAG, P9.1-SPEECH-PDF, P9.2-GHL-UPLOAD, P7-TELEPROMPTER —
        # and any future phase declaring the same shape, e.g. P-QC-AGGREGATE) is
        # DISPATCHED here, before the produces_artifact check below. Dispatch is
        # strictly opt-in: a phase with executor: null (the large majority — agent-
        # attested, produced out of band by a human/agent) leaves `_executor` None and
        # this whole block is skipped, falling straight into the pre-existing
        # artifact-present + verify + attest logic UNCHANGED. A declared executor whose
        # kind is not "script" (e.g. an explicit future {"kind": "agent"}) is likewise
        # left alone — only "script" is ever dispatched. A malformed non-null executor
        # (wrong type, "script" kind with an empty/missing cmd) is a manifest contract
        # error and FAILS LOUD rather than silently skipping or silently dispatching
        # something ambiguous. An executor that fails (non-zero exit, or cannot even
        # start) exits here — the artifact-present/attest code below is never reached,
        # so the phase is NEVER attested on a failed executor.
        _executor = target.get("executor") if target else None
        if isinstance(_executor, dict) and str(_executor.get("kind", "")).strip() == "script":
            if not str(_executor.get("cmd", "")).strip():
                print(
                    f"FATAL: phase {args.phase!r} declares executor kind='script' but "
                    f"cmd is empty/missing ({_executor!r}) — fix the manifest; refusing "
                    "to guess what to run.",
                    file=sys.stderr,
                )
                sys.exit(EXIT_EXECUTOR_FAILED)
            _rc = _dispatch_generic_executor(run_dir, _executor, args.phase)
            if _rc != 0:
                sys.exit(_rc)
        elif _executor is not None and not isinstance(_executor, dict):
            print(
                f"FATAL: phase {args.phase!r} declares a malformed executor "
                f"{_executor!r} (expected an object with kind/cmd, got "
                f"{type(_executor).__name__}) — fix the manifest; refusing to guess.",
                file=sys.stderr,
            )
            sys.exit(EXIT_EXECUTOR_FAILED)

        # Non-render phase: verify the artifact landed + run substance verifier +
        # emit done-report + compute sha + attest.
        _art_spec = target.get("produces_artifact", "") if target else ""
        if _artifact_present(run_dir, _art_spec):
            # FIX 5d: substance verifier must pass BEFORE the done-report is emitted and
            # the attestation is written. On verifier fail: DO NOT attest, DO NOT emit
            # AF-PHASE-REPORT-DONE, exit 6 (route-back) consistent with the QC loops.
            if _pv is not None:
                _ok, _reasons = _pv.verify(args.phase, run_dir)
            elif args.phase in _GOVERNED_VERIFIER_PHASES and not _degraded_verifiers_allowed(run_dir):
                # FIX-PRES-07: phase_verifiers.py is missing beside the runner on a
                # REAL run of a governed phase — fail CLOSED. Attesting a governed
                # phase with no substance verifier is exactly the silent no-op this
                # gate exists to prevent.
                _ok = False
                _reasons = [
                    f"phase_verifiers.py missing beside the runner — governed phase "
                    f"{args.phase!r} cannot attest without its substance verifier. "
                    "Restore phase_verifiers.py (it ships beside run_signature_deck.py). "
                    "A degraded pass is allowed ONLY in a test/CI context "
                    "(PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1 / CI / OPENCLAW_TEST / "
                    "the .test-context run-dir marker).",
                ]
            else:
                _ok, _reasons = True, [
                    "phase_verifiers unavailable — pass (degraded: non-governed phase "
                    "or explicit test/CI marker present)"
                ]
            if not _ok:
                print("\n" + "!" * 78, file=sys.stderr)
                print(f"FATAL: substance verifier failed for phase {args.phase!r}:",
                      file=sys.stderr)
                for _r in _reasons:
                    print("  - " + str(_r), file=sys.stderr)
                print(
                    "Phase NOT attested; route back and re-run after fixing the listed "
                    "issues. AF-PHASE-REPORT-DONE not emitted (verifier pass required).",
                    file=sys.stderr,
                )
                print("!" * 78 + "\n", file=sys.stderr)
                sys.exit(EXIT_QC_ROUTEBACK)  # exit 6 — route-back

            # FIX 4b: emit AF-PHASE-REPORT-DONE now that substance is verified.
            emit_client_report(run_dir, args.phase, "done", k=_k, N=_N)

            # FIX 4/E: compute verified artifact sha (non-empty required by attest_phase).
            _sha = _compute_artifact_sha(run_dir, _art_spec)
            attest_phase(
                run_dir, args.phase,
                target.get("owning_role", "") if target else "",
                "artifact_present",
                artifact_sha=_sha,
                substance_verified=True,
            )
            print(
                f"=== PHASE {args.phase} attested (produces_artifact present, "
                f"substance verified, sha={_sha[:16]}…) ===",
                flush=True,
            )
            # RUNNER TRUE END: for the terminal delivery phase, surface (never block)
            # a run that closed with zero successful board advances.
            if args.phase == DELIVERY_PHASE_ID:
                _board_assert_advanced(run_dir)
                # FIX-13 (M12): the deck is registered and delivered — send the OWNER
                # the deck LOCATION via the CC report-back loop (openclaw message send,
                # never the raw Telegram API). Recorded in client_reports.json as a
                # `delivery_link` row whose text carries the deck link + msg id.
                # Fail-soft by contract: a box with no owner target records an honest
                # undeliverable and the run still exits clean (delivery is complete).
                emit_delivery_link(run_dir)
            sys.exit(0)
        print(
            f"FATAL: phase {args.phase} produces_artifact "
            f"{_art_spec!r} is not present; cannot attest.",
            file=sys.stderr,
        )
        sys.exit(2)

    # FIX 5e: no --phase is a HARD ERROR — the runner never blindly fans out every
    # department role; it dispatches the render and attests artifacts one phase at a
    # time. Use --plan for read-only inspection (exit 0), or --phase <ID> to advance
    # a single named phase.
    print(
        "FATAL: no --phase given. The runner never blindly fans out; "
        "pass --phase or --plan.",
        file=sys.stderr,
    )
    print_plan(run_dir, phases)
    sys.exit(2)


def _build_executor_argvs(executor_cmd: str, run_dir: Path, phase_id: str) -> list:
    """Turn a manifest phase's executor.cmd into one or more argv lists, ready for
    subprocess.run(argv, shell=False, ...).

    TOKENISE FIRST, SUBSTITUTE SECOND — this mirrors presentation_job/phases.py's
    Engine._build_executor_argv (the reference implementation this fix reuses; see
    that module's own docstring for the full rationale) and is the ONLY sanctioned
    way to turn an executor.cmd into an argv anywhere in this file. run_dir can
    contain arbitrary characters (it is derived from client-controlled intake text
    upstream) — if it were substituted into the raw command string before that
    string is split, a run_dir crafted with shell metacharacters would be
    re-interpreted as shell syntax. Splitting first means substitution only ever
    lands inside an already-tokenised argument, so it can never introduce a new
    token or a shell operator. shell=False at the call site (see
    _dispatch_generic_executor) is what makes that guarantee hold; this function
    does not itself run anything.

    EXTENSION over the reference implementation: exactly one manifest executor
    (P9.1-SPEECH-PDF) chains two commands with a trusted, manifest-authored ` && `
    (never introducing shell=True — see below). That `&&` is split OUT of the raw
    cmd string BEFORE shlex.split/substitution, on the raw executor.cmd TEMPLATE
    itself (authored in PIPELINE-MANIFEST.json, not client-controlled), so the same
    tokenise-then-substitute ordering — and the same run_dir-is-untrusted guarantee
    — holds for every resulting stage. Returns a list of argv lists; the caller
    must run each in order and stop at the first non-zero exit."""
    raw = (executor_cmd or "").strip()
    if not raw:
        raise PhaseExecutorContractError(f"phase {phase_id!r}: executor.cmd is empty")
    run_dir_str = str(run_dir)
    argvs = []
    for seg in re.split(r"\s+&&\s+", raw):
        seg = seg.strip()
        if not seg:
            raise PhaseExecutorContractError(
                f"phase {phase_id!r}: executor.cmd {raw!r} contains an empty "
                "`&&`-chained segment")
        try:
            argv = shlex.split(seg)
        except ValueError as exc:
            raise PhaseExecutorContractError(
                f"phase {phase_id!r}: executor.cmd segment {seg!r} is not a "
                f"parseable argument vector ({exc}). Fix the manifest; this is not "
                "sanitised for you.") from exc
        if not argv:
            raise PhaseExecutorContractError(
                f"phase {phase_id!r}: executor.cmd segment {seg!r} tokenised to an "
                "empty argument vector")
        argv = [run_dir_str if tok == "{run_dir}" else tok.replace("{run_dir}", run_dir_str)
                for tok in argv]
        argvs.append(argv)
    return argvs


def _dispatch_generic_executor(run_dir: Path, executor: dict, phase_id: str) -> int:
    """OPT-IN dispatch for a manifest phase declaring {"kind": "script", "cmd": "..."}.

    The caller (main()) has already confirmed `executor` is a dict with a non-empty
    "script" cmd — this function tokenises+substitutes (via
    _build_executor_argvs), then runs each resulting stage with shell=False,
    streaming output exactly like the existing _dispatch_render /
    _dispatch_notes_sync subprocess dispatchers (no capture, so the script's own
    stdout/stderr is visible in the runner's output).

    Script paths in executor.cmd are authored relative to the "presentations"
    directory that CONTAINS this scripts/ dir (e.g. "scripts/pdf_export.py"
    resolves to HERE/pdf_export.py, since HERE.name == "scripts") — the same
    convention the manifest already uses for every declared executor — so the
    subprocess cwd is HERE.parent, not run_dir.

    Returns 0 iff every `&&`-chained stage exits 0. A non-zero return is the
    caller's signal to sys.exit() WITHOUT reaching the produces_artifact/attest
    code below it — an executor that fails is never attested."""
    try:
        argvs = _build_executor_argvs(executor.get("cmd"), run_dir, phase_id)
    except PhaseExecutorContractError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return EXIT_EXECUTOR_FAILED
    n = len(argvs)
    for i, argv in enumerate(argvs, start=1):
        stage = f" (stage {i}/{n})" if n > 1 else ""
        print(f"=== DISPATCH {phase_id}{stage} (executor): {' '.join(argv)} ===", flush=True)
        try:
            # FIX-21 (D21): process-group exec + timeout so a hung executor can never
            # orphan. TimeoutExpired is caught below and surfaces as a phase FAIL
            # (AF-EXECUTOR-TIMEOUT via the exit code) — never a silent hang.
            if run_with_cleanup is not None:
                proc = run_with_cleanup(argv, cwd=str(HERE.parent),
                                        timeout=EXECUTOR_TIMEOUT_SECONDS, capture=False)
            else:
                proc = subprocess.run(argv, shell=False, cwd=str(HERE.parent))
        except subprocess.TimeoutExpired as exc:
            print(
                f"FATAL: phase {phase_id!r} executor{stage} exceeded the "
                f"{EXECUTOR_TIMEOUT_SECONDS}s outer cap (AF-EXECUTOR-TIMEOUT). "
                f"Process group killed — no orphan left. Phase NOT attested.",
                file=sys.stderr,
            )
            return EXIT_EXECUTOR_FAILED
        except OSError as exc:
            print(
                f"FATAL: phase {phase_id!r} executor{stage} could not start "
                f"({argv[0]!r}): {exc}. Phase NOT attested.",
                file=sys.stderr,
            )
            return EXIT_EXECUTOR_FAILED
        if proc.returncode != 0:
            print(
                f"FATAL: phase {phase_id!r} executor{stage} exited "
                f"{proc.returncode}. Phase NOT attested.",
                file=sys.stderr,
            )
            return EXIT_EXECUTOR_FAILED
    print(f"=== EXECUTOR for {phase_id} completed — all {n} stage(s) exit 0 ===", flush=True)
    return 0


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
    # FIX-21 (D21): this dispatcher previously had NO timeout — a hung build_deck.py
    # ran forever and its scanning orphans masked the dead render. Now: process-group
    # exec with a hard wall-clock cap; on timeout the whole group is killed and the
    # render FAILS LOUD (no silent hang, no orphan).
    try:
        if run_with_cleanup is not None:
            proc = run_with_cleanup(cmd, timeout=RENDER_DISPATCH_TIMEOUT_SECONDS,
                                    capture=False)
        else:
            proc = subprocess.run(cmd)
    except subprocess.TimeoutExpired:
        print("FATAL PRE-DELIVERY: AF-RENDER-TIMEOUT — build_deck.py render exceeded "
              f"{RENDER_DISPATCH_TIMEOUT_SECONDS}s and was killed (process group "
              "cleaned up). No orphan remains.", file=sys.stderr)
        return EXIT_GUARD_BLOCK
    if proc.returncode == 0:
        # build_deck.py appends its own render record; the attestation reader counts it.
        print("=== RENDER phase complete — build_deck.py render record attested ===",
              flush=True)
    return proc.returncode


def _dispatch_notes_sync(run_dir: Path, slides_path: Path, out_path: Path,
                         adhoc: bool = False) -> int:
    """Dispatch P9.5-NOTES-SYNC by invoking build_deck.py --notes-sync as a
    SUBPROCESS. Reopens the already-assembled bundle .pptx (located from out_path's
    deck-slug stem, same convention _resolve_bundle_dir/assemble use) and re-injects
    per-slide speaker notes now that the presenter speech exists and (per the
    ordinary phase-precondition gate) has already passed P-SPEECH-QC. Returns the
    subprocess return code. No pre-render guard here — this phase only rewrites the
    notes pane of an already-assembled deck; it renders nothing and calls kie.ai
    for nothing."""
    # Same (slides_path, out_path, --run-dir) shape as _dispatch_render, and
    # deliberately NO --out override here: build_deck.py's default bundle-dir
    # resolution (slug-from-out_path.stem) must land on the SAME bundle dir the
    # render dispatch used, so P9.5-NOTES-SYNC re-opens the deck P8-ASSEMBLE wrote.
    cmd = [sys.executable, str(HERE / "build_deck.py"), str(slides_path), str(out_path),
           "--notes-sync", "--run-dir", str(run_dir)]
    if adhoc:
        cmd += ["--adhoc-no-process"]
    print(f"=== DISPATCH P9.5-NOTES-SYNC (subprocess): {' '.join(cmd)} ===", flush=True)
    # FIX-21 (D21): process-group exec + timeout, same discipline as _dispatch_render.
    try:
        if run_with_cleanup is not None:
            proc = run_with_cleanup(cmd, timeout=EXECUTOR_TIMEOUT_SECONDS,
                                    capture=False)
        else:
            proc = subprocess.run(cmd)
    except subprocess.TimeoutExpired:
        print("FATAL PRE-DELIVERY: AF-NOTES-SYNC-TIMEOUT — notes-sync exceeded "
              f"{EXECUTOR_TIMEOUT_SECONDS}s and was killed (process group cleaned up).",
              file=sys.stderr)
        return EXIT_GUARD_BLOCK
    if proc.returncode == 0:
        print("=== P9.5-NOTES-SYNC complete — notes_sync.json written ===", flush=True)
    return proc.returncode


if __name__ == "__main__":
    main()
