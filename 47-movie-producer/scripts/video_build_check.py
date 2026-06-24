#!/usr/bin/env python3
"""
video_build_check.py — Movie Producer RECEIPT VALIDATORS + POSTFLIGHT GATE.

================================================================================
This is the enforcement library for the Movie Producer (Video Production)
department. It is the analogue of build_deck.py's preflight checkers for the
Presentations department: every PIPELINE autofail in VIDEO-PIPELINE-MANIFEST.json
whose enforced_by == "executive_producer" names a py_symbol that is DEFINED here
(and referenced on the enforcement path in executive_producer.py).

It validates RECEIPTS, not just their presence:
  * V-DEFINE   — job-manifest.json brief_complete + required fields.
  * V-MEASURE  — preflight_pass + provider_audit_pass + budget_gate_pass.
  * V-ANALYZE  — rule_zero_announced_at + approval_received_at + approved_by
                 (CONDITIONAL on a paid job; the free documentary path skips).
  * V-IMPROVE  — render receipt ffprobe_pass:true + ffprobe_duration>0 + a video
                 stream; when Kie was in scope a REAL (non-placeholder) kie_task_id
                 + kie_result_url; and NO native paid provider key present at
                 generation time.
  * V-CONTROL  — postflight completeness (status:complete + the deliverable bundle
                 above its min_bytes floor + a declared handoff) + budget reconcile.

It is AGPLv3-safe: it is OUR code that gates AROUND OpenMontage. It never imports
or vendors any OpenMontage source. Zero third-party deps (stdlib json / re /
pathlib / urllib only).

Each checker returns "" on PASS or a fatal "AF-VID-...: <reason>" string on FAIL.
A receipt that is ABSENT at the point a phase is dispatched is owned by the driver's
phase-precondition gate (AF-VID-PHASE-SKIPPED), so these checkers VALIDATE a
present receipt; absence is reported with the same AF code so the message is useful
when a checker is called directly (e.g. by the negative-test suite).
"""

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Module constants (the secondary_py_symbols the manifest autofails reference).
# ---------------------------------------------------------------------------
REQUIRED_BRIEF_FIELDS = [
    "topic",
    "target_duration_sec",
    "aspect_ratio",
    "budget_ceiling_usd",
    "tone",
]

# Native paid providers that must NEVER be present on the client box — assets
# route through Kie.AI ONLY. Matched case-insensitively against provider names
# and against env-var name prefixes recorded in a render receipt's generation_env.
NATIVE_PAID_PROVIDERS = [
    "fal", "runway", "heygen", "openai", "google", "imagen",
    "flux", "veo-native", "kling", "minimax", "xai", "elevenlabs",
]

# Env-var name fragments that, if present in a recorded generation environment,
# prove a native paid provider key was available at generation time.
NATIVE_PROVIDER_ENV_KEYS = [
    "FAL_KEY", "FAL_API_KEY", "RUNWAY", "HEYGEN", "OPENAI_API_KEY",
    "GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GEMINI_API_KEY",
    "KLING", "MINIMAX", "XAI_API_KEY", "ELEVENLABS",
]

# Placeholder / fabricated task-id tokens that are NOT a real Kie task id.
FABRICATED_TASK_ID_TOKENS = [
    "task_id", "taskid", "todo", "tbd", "xxxx", "xxx", "fake",
    "fabricated", "placeholder", "none", "null", "n/a", "na",
    "your_task_id", "example",
]

# The required-deliverable bundle (mirrors VIDEO-PIPELINE-MANIFEST.deliverables_required).
# Lockstep (video_sync_check.py D1/D2) requires this key set == the manifest key set.
DELIVERABLES_REQUIRED = [
    {"key": "job_manifest", "filename": "job-manifest.json", "min_bytes": 256,
     "label": "completed job manifest"},
    {"key": "render_receipt", "filename": "render-receipt.json", "min_bytes": 256,
     "label": "ffprobe-validated render receipt"},
    {"key": "final_mp4", "filename": "*.mp4", "min_bytes": 102400,
     "label": "finished MP4 deliverable"},
]

# Legitimate downstream handoff targets a finished job must declare (mirrors the
# manifest handoff_targets). At least one must be declared at V-CONTROL.
HANDOFF_TARGETS = [
    "captions", "tts", "edit", "storyboard", "delivery",
    "captioning--subtitling-specialist", "fish-audio", "video-editor",
    "storyboard-writer", "head-of-video-production",
]

# Phase-0 Kie balance pre-flight constants (AF-VID-KIE-BALANCE).
VID_KIE_CREDIT_URL = "https://api.kie.ai/api/v1/chat/credit"
VID_KIE_BALANCE_FLOOR_MULTIPLIER = 1.25  # headroom over the bare estimate (retries)
# Kie credits are denominated per-call; a job's estimated_cost_usd is in USD, so the
# balance floor is expressed in credits via this conservative USD->credit factor.
VID_CREDIT_PER_USD = 100


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path):
    """Return the parsed object, or None when absent/unreadable, or the sentinel
    {'__parse_error__': ...} on a JSON error so callers can distinguish."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"__parse_error__": str(exc)}


def _job_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "job-manifest.json"


def _checkpoints(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints"


def _load_job_manifest(run_dir: Path):
    return _read_json(_job_manifest_path(run_dir))


def _paid_in_scope(run_dir: Path) -> bool:
    """True when this job will dispatch (or has dispatched) at least one paid Kie
    call. Sourced from the job manifest's pipeline_selected / kie_in_scope flag and
    any render receipt. The free documentary-montage path is NOT paid."""
    jm = _load_job_manifest(run_dir)
    if isinstance(jm, dict) and "__parse_error__" not in jm:
        if jm.get("kie_in_scope") is True:
            return True
        if jm.get("kie_in_scope") is False:
            return False
        sel = str(jm.get("pipeline_selected", "")).lower()
        if "documentary-montage" in sel or "free" in sel:
            return False
        est = jm.get("estimated_cost_usd")
        if isinstance(est, (int, float)) and est > 0:
            return True
    # Fall back to the render receipt's explicit flag.
    rr = _read_json(_checkpoints(run_dir) / "render-receipt.json")
    if isinstance(rr, dict) and rr.get("kie_in_scope") is True:
        return True
    return False


# ===========================================================================
# V-DEFINE — AF-VID-BRIEF-INCOMPLETE
# ===========================================================================
def _chk_brief_complete(run_dir: Path) -> str:
    """AF-VID-BRIEF-INCOMPLETE. The job-manifest.json must set brief_complete:true
    and carry every REQUIRED_BRIEF_FIELDS field with a non-empty value."""
    jm = _load_job_manifest(run_dir)
    if jm is None:
        return ("AF-VID-BRIEF-INCOMPLETE: working/job-manifest.json is absent — the "
                "V-DEFINE brief is the precondition for every downstream phase.")
    if isinstance(jm, dict) and "__parse_error__" in jm:
        return (f"AF-VID-BRIEF-INCOMPLETE: job-manifest.json is not valid JSON "
                f"({jm['__parse_error__']}).")
    if jm.get("brief_complete") is not True:
        return ("AF-VID-BRIEF-INCOMPLETE: job-manifest.json does not set "
                "brief_complete:true. Return the gap list to the requestor before "
                "proceeding — never guess at a missing brief input.")
    missing = [f for f in REQUIRED_BRIEF_FIELDS
               if jm.get(f) in (None, "", [], {})]
    if missing:
        return ("AF-VID-BRIEF-INCOMPLETE: job-manifest.json is missing required brief "
                f"field(s): {', '.join(missing)}. All of {REQUIRED_BRIEF_FIELDS} must "
                "be present.")
    return ""


# ===========================================================================
# V-MEASURE — AF-VID-PREFLIGHT / AF-VID-PROVIDER-AUDIT / AF-VID-BUDGET-CAP
# ===========================================================================
def _measure_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "measure-receipt.json")


def _chk_measure_receipt(run_dir: Path) -> str:
    """AF-VID-PREFLIGHT. The V-MEASURE receipt must set preflight_pass:true."""
    mr = _measure_receipt(run_dir)
    if mr is None:
        return ("AF-VID-PREFLIGHT: working/checkpoints/measure-receipt.json is absent "
                "— the runtime-dependency preflight must run and pass before pipeline "
                "execution.")
    if isinstance(mr, dict) and "__parse_error__" in mr:
        return (f"AF-VID-PREFLIGHT: measure-receipt.json is not valid JSON "
                f"({mr['__parse_error__']}).")
    if mr.get("preflight_pass") is not True:
        return ("AF-VID-PREFLIGHT: measure-receipt.json does not set "
                "preflight_pass:true. NEVER proceed with a failing runtime-dependency "
                "preflight (ffmpeg / node>=18 / npx hyperframes / python deps); deliver "
                "the exact install instruction instead of a workaround.")
    return ""


def _chk_provider_audit(run_dir: Path) -> str:
    """AF-VID-PROVIDER-AUDIT. kie AVAILABLE; every native paid provider UNAVAILABLE."""
    mr = _measure_receipt(run_dir)
    if mr is None or (isinstance(mr, dict) and "__parse_error__" in mr):
        return ("AF-VID-PROVIDER-AUDIT: measure-receipt.json is absent/invalid; the "
                "provider availability audit could not be confirmed.")
    if mr.get("provider_audit_pass") is not True:
        return ("AF-VID-PROVIDER-AUDIT: measure-receipt.json does not set "
                "provider_audit_pass:true.")
    providers = mr.get("providers_available") or []
    avail = {str(p).lower() for p in providers} if isinstance(providers, list) else set()
    if "kie" not in avail:
        return ("AF-VID-PROVIDER-AUDIT: kie is not AVAILABLE in the provider audit. "
                "Verify KIE_API_KEY is set in a client env store before any generation.")
    leaked = sorted({p for p in avail
                     if any(nat in p for nat in NATIVE_PAID_PROVIDERS)})
    if leaked:
        return ("AF-VID-PROVIDER-AUDIT: native paid provider(s) reported AVAILABLE: "
                f"{', '.join(leaked)}. All assets must route through Kie.AI ONLY — an "
                "unexpected native key could misdirect generation. Remove the key.")
    return ""


def _chk_budget_cap(run_dir: Path) -> str:
    """AF-VID-BUDGET-CAP. estimated_cost_usd <= budget_ceiling_usd; budget_gate_pass."""
    mr = _measure_receipt(run_dir)
    if mr is None or (isinstance(mr, dict) and "__parse_error__" in mr):
        return ("AF-VID-BUDGET-CAP: measure-receipt.json is absent/invalid; the budget "
                "gate could not be confirmed.")
    if mr.get("budget_gate_pass") is not True:
        return ("AF-VID-BUDGET-CAP: measure-receipt.json does not set "
                "budget_gate_pass:true.")
    est = mr.get("estimated_cost_usd")
    cap = mr.get("budget_ceiling_usd")
    if cap is None:
        jm = _load_job_manifest(run_dir)
        cap = jm.get("budget_ceiling_usd") if isinstance(jm, dict) else None
    if isinstance(est, (int, float)) and isinstance(cap, (int, float)):
        if est > cap:
            return ("AF-VID-BUDGET-CAP: estimated_cost_usd "
                    f"({est}) exceeds the budget ceiling ({cap}). HARD STOP — switch to "
                    "the free documentary-montage path or obtain an explicit cap "
                    "increase before V-ANALYZE.")
    return ""


# ===========================================================================
# V-ANALYZE — AF-VID-RULE-ZERO / AF-VID-APPROVAL-MISSING (paid only)
# ===========================================================================
def _chk_rule_zero_approval(run_dir: Path) -> str:
    """AF-VID-RULE-ZERO + AF-VID-APPROVAL-MISSING. CONDITIONAL on a paid job. For a
    paid job the approval receipt must carry rule_zero_announced_at (announce) AND
    approval_received_at + approved_by (explicit human approval). For a free
    documentary-montage job this phase is owner-skipped (the driver logs it), and
    this checker passes (defers)."""
    if not _paid_in_scope(run_dir):
        return ""  # free path — Rule-Zero announce/approval not required; deferred.
    ar = _read_json(_checkpoints(run_dir) / "approval-receipt.json")
    if ar is None:
        return ("AF-VID-APPROVAL-MISSING: paid job reached V-ANALYZE with no "
                "working/checkpoints/approval-receipt.json. A paid Kie call requires a "
                "Rule-Zero announce + an explicit human APPROVE first.")
    if isinstance(ar, dict) and "__parse_error__" in ar:
        return (f"AF-VID-APPROVAL-MISSING: approval-receipt.json is not valid JSON "
                f"({ar['__parse_error__']}).")
    if not str(ar.get("rule_zero_announced_at", "")).strip():
        return ("AF-VID-RULE-ZERO: approval-receipt.json lacks rule_zero_announced_at. "
                "Provider + model + estimated USD MUST be announced BEFORE any paid "
                "call (Rule Zero is binding).")
    if (not str(ar.get("approval_received_at", "")).strip()
            or not str(ar.get("approved_by", "")).strip()):
        return ("AF-VID-APPROVAL-MISSING: approval-receipt.json lacks "
                "approval_received_at and/or approved_by. The job must WAIT for an "
                "explicit APPROVE (named approver) before any paid Kie call.")
    return ""


# ===========================================================================
# V-IMPROVE — AF-VID-NO-FFPROBE / AF-VID-FABRICATED-RECEIPT / AF-VID-NATIVE-PROVIDER
# ===========================================================================
def _render_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "render-receipt.json")


def _chk_render_receipt(run_dir: Path) -> str:
    """AF-VID-NO-FFPROBE. The render receipt must prove an ffprobe validation:
    ffprobe_pass:true + ffprobe_duration>0 + a video stream."""
    rr = _render_receipt(run_dir)
    if rr is None:
        return ("AF-VID-NO-FFPROBE: working/checkpoints/render-receipt.json is absent "
                "— ffprobe MUST validate every rendered MP4 before delivery.")
    if isinstance(rr, dict) and "__parse_error__" in rr:
        return (f"AF-VID-NO-FFPROBE: render-receipt.json is not valid JSON "
                f"({rr['__parse_error__']}).")
    if rr.get("ffprobe_pass") is not True:
        return ("AF-VID-NO-FFPROBE: render-receipt.json does not set ffprobe_pass:true. "
                "Do NOT deliver an MP4 that has not passed ffprobe validation.")
    dur = rr.get("ffprobe_duration")
    if not isinstance(dur, (int, float)) or dur <= 0:
        return ("AF-VID-NO-FFPROBE: render-receipt.json ffprobe_duration is missing or "
                f"<= 0 ({dur!r}). A zero-duration MP4 is not a valid render.")
    # A video stream must be recorded (codec or has_video_stream flag).
    has_video = (rr.get("has_video_stream") is True
                 or str(rr.get("ffprobe_codec", "")).strip() != ""
                 or str(rr.get("ffprobe_width", "")).strip() not in ("", "0"))
    if not has_video:
        return ("AF-VID-NO-FFPROBE: render-receipt.json records no video stream "
                "(ffprobe_codec / ffprobe_width / has_video_stream all empty).")
    return ""


def _chk_kie_receipt_real(run_dir: Path) -> str:
    """AF-VID-FABRICATED-RECEIPT. When Kie was in scope the render receipt must carry
    a REAL (non-null, non-placeholder) kie_task_id + kie_result_url. Defers for the
    free path (no Kie call -> no task id expected)."""
    if not _paid_in_scope(run_dir):
        return ""  # free path — no Kie task id expected.
    rr = _render_receipt(run_dir)
    if rr is None or (isinstance(rr, dict) and "__parse_error__" in rr):
        return ("AF-VID-FABRICATED-RECEIPT: render-receipt.json absent/invalid for a "
                "paid job — the Kie task id is the anti-fabrication proof.")
    tid = str(rr.get("kie_task_id", "") or "").strip()
    url = str(rr.get("kie_result_url", "") or "").strip()
    if not tid:
        return ("AF-VID-FABRICATED-RECEIPT: Kie was in scope but render-receipt.json "
                "carries no kie_task_id. A missing task id means the generation either "
                "did not happen (fabrication) or was not recorded — both fail.")
    if tid.lower() in FABRICATED_TASK_ID_TOKENS:
        return ("AF-VID-FABRICATED-RECEIPT: kie_task_id is a placeholder/fabricated "
                f"token ({tid!r}), not a real Kie task id.")
    if not url:
        return ("AF-VID-FABRICATED-RECEIPT: Kie was in scope but render-receipt.json "
                "carries no kie_result_url alongside the task id.")
    return ""


def _chk_native_provider(run_dir: Path) -> str:
    """AF-VID-NATIVE-PROVIDER. No native paid provider key was present in the recorded
    generation environment, and provider_used (if recorded) is not a native provider."""
    rr = _render_receipt(run_dir)
    if rr is None or (isinstance(rr, dict) and "__parse_error__" in rr):
        # Absence is owned by AF-VID-NO-FFPROBE / the driver precondition; nothing to
        # validate here when there is no receipt.
        return ""
    used = str(rr.get("provider_used", "") or "").lower()
    if used and any(nat in used for nat in NATIVE_PAID_PROVIDERS):
        return ("AF-VID-NATIVE-PROVIDER: render-receipt.json provider_used names a "
                f"native paid provider ({used!r}). All generative assets MUST route "
                "through Kie.AI only.")
    gen_env = rr.get("generation_env") or {}
    env_names = set()
    if isinstance(gen_env, dict):
        env_names = {str(k).upper() for k in gen_env.keys()}
    elif isinstance(gen_env, list):
        env_names = {str(k).upper() for k in gen_env}
    leaked = sorted({k for k in NATIVE_PROVIDER_ENV_KEYS
                     if any(k.upper() in n for n in env_names)})
    if leaked:
        return ("AF-VID-NATIVE-PROVIDER: a native paid provider key was present in the "
                f"recorded generation environment: {', '.join(leaked)}. Native providers "
                "must remain UNAVAILABLE so all asset generation routes through Kie.")
    return ""


# ===========================================================================
# V-CONTROL — AF-VID-DELIVERY-INCOMPLETE (postflight) / AF-VID-BUDGET-OVERRUN
# ===========================================================================
def _glob_min_bytes(run_dir: Path, filename: str, min_bytes: int) -> bool:
    """True when at least one file matching `filename` (glob ok) exists anywhere under
    run_dir at or above min_bytes."""
    if "*" in filename or "?" in filename:
        matches = list(run_dir.glob("**/" + filename))
    else:
        matches = list(run_dir.glob("**/" + filename))
    for m in matches:
        try:
            if m.is_file() and m.stat().st_size >= min_bytes:
                return True
        except OSError:
            continue
    return False


def run_postflight_gate(run_dir: Path) -> str:
    """AF-VID-DELIVERY-INCOMPLETE. The V-CONTROL completeness gate. Returns "" only
    when: job-manifest status == 'complete' AND every DELIVERABLES_REQUIRED file is
    present at/above its min_bytes floor AND a downstream handoff is declared."""
    jm = _load_job_manifest(run_dir)
    if jm is None or (isinstance(jm, dict) and "__parse_error__" in jm):
        return ("AF-VID-DELIVERY-INCOMPLETE: job-manifest.json is absent/invalid at "
                "V-CONTROL.")
    if str(jm.get("status", "")).lower() != "complete":
        return ("AF-VID-DELIVERY-INCOMPLETE: job-manifest status is "
                f"{jm.get('status')!r}, not 'complete'.")
    missing = []
    for d in DELIVERABLES_REQUIRED:
        if not _glob_min_bytes(run_dir, d["filename"], int(d["min_bytes"])):
            missing.append(f"{d['key']} ({d['label']}, >= {d['min_bytes']} bytes)")
    if missing:
        return ("AF-VID-DELIVERY-INCOMPLETE: required deliverable(s) missing or below "
                f"the size floor: {'; '.join(missing)}.")
    declared = jm.get("handoff") or jm.get("delivered_to") or jm.get("handoffs")
    declared_ok = False
    if isinstance(declared, str) and declared.strip():
        declared_ok = any(h in declared.lower() for h in HANDOFF_TARGETS)
    elif isinstance(declared, (list, dict)):
        flat = " ".join(str(x).lower() for x in
                        (declared if isinstance(declared, list) else declared.keys()))
        declared_ok = any(h in flat for h in HANDOFF_TARGETS)
    if not declared_ok:
        return ("AF-VID-DELIVERY-INCOMPLETE: no downstream handoff declared in "
                "job-manifest (handoff / delivered_to). Declare one of "
                "captions(26)/tts(30)/edit(27)/storyboard(24)/delivery(Head of Video "
                "Production).")
    return ""


def _chk_delivery_complete(run_dir: Path) -> str:
    """Preflight wrapper for the V-CONTROL phase — delegates to run_postflight_gate."""
    return run_postflight_gate(run_dir)


def _chk_budget_overrun(run_dir: Path) -> str:
    """AF-VID-BUDGET-OVERRUN. actual_cost_usd <= budget_ceiling_usd."""
    jm = _load_job_manifest(run_dir)
    if jm is None or (isinstance(jm, dict) and "__parse_error__" in jm):
        return ("AF-VID-BUDGET-OVERRUN: job-manifest.json absent/invalid; budget "
                "reconciliation could not be confirmed.")
    actual = jm.get("actual_cost_usd")
    cap = jm.get("budget_ceiling_usd")
    if isinstance(actual, (int, float)) and isinstance(cap, (int, float)):
        if actual > cap:
            breaker = jm.get("circuit_breaker") or jm.get("budget_override_approved")
            if not breaker:
                return ("AF-VID-BUDGET-OVERRUN: actual_cost_usd "
                        f"({actual}) exceeds the budget ceiling ({cap}) with no "
                        "circuit-breaker / override record. A run must never exceed the "
                        "client's funded budget cap.")
    return ""


# ===========================================================================
# Phase-0 Kie balance pre-flight — AF-VID-KIE-BALANCE (shared with the driver)
# ===========================================================================
def _fetch_kie_balance(api_key: str, url: str = VID_KIE_CREDIT_URL,
                       timeout: int = 30) -> float:
    """GET the live Kie credit balance. Returns the numeric balance. Raises
    RuntimeError on a network/parse error so the caller fails LOUD rather than
    treating an unknown balance as 'enough'. Parses the common Kie response shapes
    ({data:<number>} / {data:{credit|credits|balance}} / a top-level number)."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise RuntimeError(f"Kie credit endpoint unreachable ({url}): {exc}")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Kie credit response is not JSON: {exc}; body={raw[:200]!r}")
    candidates = []
    if isinstance(obj, (int, float)):
        candidates.append(obj)
    if isinstance(obj, dict):
        data_val = obj.get("data")
        if isinstance(data_val, (int, float)):
            candidates.append(data_val)
        for container in (data_val if isinstance(data_val, dict) else None, obj):
            if not isinstance(container, dict):
                continue
            for k in ("credit", "credits", "balance", "remaining", "available"):
                v = container.get(k)
                if isinstance(v, (int, float)):
                    candidates.append(v)
    if not candidates:
        raise RuntimeError(f"Kie credit response carried no numeric balance: {raw[:200]!r}")
    return float(candidates[0])


def kie_balance_preflight(run_dir: Path, estimated_cost_usd: float,
                          api_key=None) -> str:
    """AF-VID-KIE-BALANCE. Phase-0 balance gate for a PAID job. Computes the estimated
    credit floor (estimated_cost_usd x VID_CREDIT_PER_USD x
    VID_KIE_BALANCE_FLOOR_MULTIPLIER), fetches the live Kie balance, and returns a
    fatal AF-VID-KIE-BALANCE string when balance < floor or the balance cannot be
    verified. Returns "" on pass. Defers (passes) for a free job (estimated_cost<=0)
    or when no API key is available (an adhoc/offline path; the render path's own key
    load fails loud elsewhere). An UNVERIFIABLE balance is a HARD ABORT."""
    if not estimated_cost_usd or estimated_cost_usd <= 0:
        return ""  # free path — no paid floor to clear.
    if not api_key:
        return ""  # no key to query on this box; deferred to the render subprocess.
    estimated_floor = (float(estimated_cost_usd) * VID_CREDIT_PER_USD
                       * VID_KIE_BALANCE_FLOOR_MULTIPLIER)
    try:
        balance = _fetch_kie_balance(api_key)
    except RuntimeError as exc:
        return ("AF-VID-KIE-BALANCE: could not verify the Kie.ai credit balance before "
                f"generation ({exc}). An unverifiable balance is a HARD ABORT — never "
                "generate on an unknown balance. Fix the key/endpoint, or top up and "
                "retry.")
    if balance < estimated_floor:
        return ("AF-VID-KIE-BALANCE: Kie.ai credit balance is below the estimated floor "
                f"for this job. balance={balance:g} credits, "
                f"estimated_floor={estimated_floor:g} (estimated_cost "
                f"${estimated_cost_usd:g} x {VID_CREDIT_PER_USD} credits/USD x "
                f"{VID_KIE_BALANCE_FLOOR_MULTIPLIER} headroom). HARD ABORT before any "
                "paid dispatch so the run does not die mid-production. Top up and retry.")
    return ""


# ===========================================================================
# Convenience: the checker registry (used by tests / the driver dispatch table).
# ===========================================================================
CHECKERS = {
    "_chk_brief_complete": _chk_brief_complete,
    "_chk_measure_receipt": _chk_measure_receipt,
    "_chk_provider_audit": _chk_provider_audit,
    "_chk_budget_cap": _chk_budget_cap,
    "_chk_rule_zero_approval": _chk_rule_zero_approval,
    "_chk_render_receipt": _chk_render_receipt,
    "_chk_kie_receipt_real": _chk_kie_receipt_real,
    "_chk_native_provider": _chk_native_provider,
    "_chk_delivery_complete": _chk_delivery_complete,
    "_chk_budget_overrun": _chk_budget_overrun,
    "run_postflight_gate": run_postflight_gate,
}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: video_build_check.py RUN_DIR [checker_name]", file=sys.stderr)
        sys.exit(2)
    rd = Path(sys.argv[1]).resolve()
    if len(sys.argv) >= 3:
        fn = CHECKERS.get(sys.argv[2])
        if not fn:
            print(f"unknown checker {sys.argv[2]!r}; known: {sorted(CHECKERS)}",
                  file=sys.stderr)
            sys.exit(2)
        reason = fn(rd)
        print(reason or f"PASS — {sys.argv[2]}")
        sys.exit(3 if reason else 0)
    # Run every checker; report the first failure.
    for name, fn in CHECKERS.items():
        reason = fn(rd)
        status = "FAIL" if reason else "pass"
        print(f"[{status}] {name}: {reason or 'ok'}")
