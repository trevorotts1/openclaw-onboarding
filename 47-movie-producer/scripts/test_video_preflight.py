#!/usr/bin/env python3
"""
test_video_preflight.py — NEGATIVE-TEST SUITE for the Movie Producer gates.

================================================================================
For EVERY autofail in VIDEO-PIPELINE-MANIFEST.json whose enforced_by ==
"executive_producer", this suite builds a deliberately-failing run dir, calls the
enforcing checker, and asserts it TRIGGERS (returns a fatal string carrying the AF
code). It ALSO builds a GOOD run dir and asserts the checker PASSES. It then emits
working/af-coverage.json listing every AF code a failing fixture actually tripped —
the file Guard A (video_gate_integrity_check.py) consumes to prove "declared ==
enforced == tested".

Mirrors the Presentations test_preflight.py / af-coverage contract. AGPLv3-safe: it
exercises OUR validators only; no OpenMontage source is touched.

EXIT CODES:
    0 — every gate fixture behaved (negative tripped, positive passed); af-coverage emitted.
    1 — a gate did not trip on its failing fixture, or rejected its passing fixture.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import video_build_check as vbc  # noqa: E402
import executive_producer as ep  # noqa: E402

AF_COVERAGE = HERE / "working" / "af-coverage.json"

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _mk_run(tmp: Path) -> Path:
    rd = Path(tempfile.mkdtemp(dir=tmp))
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return rd


def _write(rd: Path, rel: str, obj) -> None:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        # pad so JSON receipts clear the 256-byte deliverable floor where relevant
        p.write_text(json.dumps(obj, indent=2))
    else:
        p.write_text(str(obj))


_GOOD_BRIEF = {
    "job_id": "job-good", "pipeline_selected": "documentary-montage.yaml",
    "kie_in_scope": False, "brief_complete": True, "topic": "the deep ocean",
    "target_duration_sec": 30, "aspect_ratio": "16:9", "budget_ceiling_usd": 1.0,
    "tone": "documentary", "estimated_cost_usd": 0.0,
    "_pad": "padding to clear the 256-byte deliverable size floor for job_manifest " * 3,
}
_GOOD_MEASURE = {
    "preflight_pass": True, "provider_audit_pass": True, "budget_gate_pass": True,
    "providers_available": ["kie", "piper"], "estimated_cost_usd": 0.0,
    "budget_ceiling_usd": 1.0,
}
_GOOD_RENDER = {
    "kie_in_scope": False, "ffprobe_pass": True, "ffprobe_duration": 30.0,
    "ffprobe_codec": "h264", "ffprobe_width": 1280, "ffprobe_height": 720,
    "has_video_stream": True, "provider_used": "ffmpeg",
    "final_mp4_path": "working/final.mp4",  # FIX-S36-44: the specific finished MP4
    "_pad": "padding to clear the 256-byte deliverable size floor for render_receipt " * 2,
}
_GOOD_PAID_RENDER = {
    "kie_in_scope": True, "ffprobe_pass": True, "ffprobe_duration": 8.0,
    "ffprobe_codec": "h264", "ffprobe_width": 1280, "ffprobe_height": 720,
    "has_video_stream": True, "provider_used": "kie",
    "kie_task_id": "a27542cb60343417e562afc2be65da5c",
    "kie_result_url": "https://tempfile.aiquickdraw.com/v/abc_123.mp4",
    "generation_env": {"KIE_API_KEY": "present"},
}


def _good_free(rd: Path):
    _write(rd, "working/job-manifest.json", dict(_GOOD_BRIEF))
    _write(rd, "working/checkpoints/measure-receipt.json", dict(_GOOD_MEASURE))
    _write(rd, "working/checkpoints/render-receipt.json", dict(_GOOD_RENDER))
    _write(rd, "working/render-receipt.json", dict(_GOOD_RENDER))
    (rd / "working" / "final.mp4").write_bytes(b"\x00" * 150_000)
    done = dict(_GOOD_BRIEF)
    done.update({"status": "complete", "actual_cost_usd": 0.0,
                 "handoff": "captions->Skill 26 (caption-creator)"})
    _write(rd, "working/job-manifest.json", done)


# ---------------------------------------------------------------------------
# Each entry: (af_code, checker_name, make_bad(rd)->None, make_good(rd)->None)
# make_bad sets up a run dir that MUST trip the checker; make_good MUST pass it.
# ---------------------------------------------------------------------------
def _bad_brief(rd):
    _write(rd, "working/job-manifest.json",
           {"brief_complete": True, "topic": "x"})  # missing required fields


def _good_brief(rd):
    _write(rd, "working/job-manifest.json", dict(_GOOD_BRIEF))


def _bad_measure(rd):
    _good_brief(rd)
    _write(rd, "working/checkpoints/measure-receipt.json",
           {"preflight_pass": False, "provider_audit_pass": True, "budget_gate_pass": True,
            "providers_available": ["kie"]})


def _good_measure(rd):
    _good_brief(rd)
    _write(rd, "working/checkpoints/measure-receipt.json", dict(_GOOD_MEASURE))


def _bad_provider_audit(rd):
    _good_brief(rd)
    m = dict(_GOOD_MEASURE)
    m["providers_available"] = ["kie", "runway"]  # native provider leaked
    _write(rd, "working/checkpoints/measure-receipt.json", m)


def _bad_budget_cap(rd):
    _good_brief(rd)
    m = dict(_GOOD_MEASURE)
    m.update({"estimated_cost_usd": 99.0, "budget_ceiling_usd": 1.0})
    _write(rd, "working/checkpoints/measure-receipt.json", m)


def _bad_rule_zero(rd):
    # paid job, approval receipt missing announce
    b = dict(_GOOD_BRIEF)
    b.update({"kie_in_scope": True, "pipeline_selected": "kie-video.yaml",
              "estimated_cost_usd": 2.0})
    _write(rd, "working/job-manifest.json", b)
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"approval_received_at": "2026-06-24T10:00:00Z", "approved_by": "X"})


def _good_rule_zero(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"kie_in_scope": True, "pipeline_selected": "kie-video.yaml",
              "estimated_cost_usd": 2.0})
    _write(rd, "working/job-manifest.json", b)
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"rule_zero_announced_at": "2026-06-24T09:59:00Z",
            "approval_received_at": "2026-06-24T10:00:00Z",
            "approved_by": "Head of Video Production"})


def _bad_approval_missing(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"kie_in_scope": True, "pipeline_selected": "kie-video.yaml",
              "estimated_cost_usd": 2.0})
    _write(rd, "working/job-manifest.json", b)
    # announce present, but no human approval
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"rule_zero_announced_at": "2026-06-24T09:59:00Z"})


def _bad_no_ffprobe(rd):
    _good_brief(rd)
    _write(rd, "working/checkpoints/render-receipt.json",
           {"kie_in_scope": False, "ffprobe_pass": False})


def _good_render(rd):
    _good_brief(rd)
    _write(rd, "working/checkpoints/render-receipt.json", dict(_GOOD_RENDER))


def _bad_fabricated(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"kie_in_scope": True, "pipeline_selected": "kie-video.yaml",
              "estimated_cost_usd": 2.0})
    _write(rd, "working/job-manifest.json", b)
    r = dict(_GOOD_PAID_RENDER)
    r["kie_task_id"] = "TASK_ID"  # placeholder token
    r["kie_result_url"] = ""
    _write(rd, "working/checkpoints/render-receipt.json", r)


def _good_paid_render(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"kie_in_scope": True, "pipeline_selected": "kie-video.yaml",
              "estimated_cost_usd": 2.0})
    _write(rd, "working/job-manifest.json", b)
    _write(rd, "working/checkpoints/render-receipt.json", dict(_GOOD_PAID_RENDER))


def _bad_native_provider(rd):
    _good_brief(rd)
    r = dict(_GOOD_RENDER)
    r["generation_env"] = {"KIE_API_KEY": "x", "RUNWAY_API_KEY": "leaked"}
    _write(rd, "working/checkpoints/render-receipt.json", r)


def _bad_delivery(rd):
    # status complete but no MP4 / no handoff
    b = dict(_GOOD_BRIEF)
    b.update({"status": "complete", "actual_cost_usd": 0.0})
    _write(rd, "working/job-manifest.json", b)


def _good_delivery(rd):
    _good_free(rd)


def _bad_budget_overrun(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"status": "complete", "actual_cost_usd": 50.0, "budget_ceiling_usd": 1.0})
    _write(rd, "working/job-manifest.json", b)


def _good_budget(rd):
    b = dict(_GOOD_BRIEF)
    b.update({"status": "complete", "actual_cost_usd": 0.0, "budget_ceiling_usd": 1.0})
    _write(rd, "working/job-manifest.json", b)


# Phase-0 balance: kie_balance_preflight is unverifiable -> HARD ABORT. Use a bad key
# against an unreachable host substitution. We call the checker directly with a key and
# a patched URL that cannot resolve, proving the "unverifiable balance = abort" branch.
def _probe_kie_balance() -> bool:
    """Trigger AF-VID-KIE-BALANCE via an unverifiable balance (unreachable endpoint)."""
    orig = vbc.VID_KIE_CREDIT_URL
    try:
        vbc.VID_KIE_CREDIT_URL = "http://127.0.0.1:0/nope"
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp)
            (rd / "working" / "checkpoints").mkdir(parents=True)
            reason = vbc.kie_balance_preflight(rd, estimated_cost_usd=2.0,
                                               api_key="dummy-key-not-real")
        return "AF-VID-KIE-BALANCE" in reason
    finally:
        vbc.VID_KIE_CREDIT_URL = orig


# FIX-S36-42 regression: a bare Google/Gemini EMBEDDING key must NOT trip the
# provider audit or the native-provider gate (fleet boxes carry it legitimately),
# while a real native GENERATION provider still fails.
def _probe_google_embedding_allowed() -> list:
    """Return a list of failure strings (empty == pass)."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        # (a) providers_available lists a bare 'google' embedding provider -> PASS.
        rd = _mk_run(Path(tmp))
        _good_brief(rd)
        m = dict(_GOOD_MEASURE)
        m["providers_available"] = ["kie", "piper", "google"]
        _write(rd, "working/checkpoints/measure-receipt.json", m)
        if vbc._chk_provider_audit(rd):
            fails.append("FIX-S36-42: a bare 'google' embedding provider tripped "
                         "_chk_provider_audit (should be allowlisted).")
        # (b) generation_env carries GOOGLE_API_KEY (embeddings) -> PASS.
        rd2 = _mk_run(Path(tmp))
        _good_brief(rd2)
        r = dict(_GOOD_RENDER)
        r["generation_env"] = {"KIE_API_KEY": "x", "GOOGLE_API_KEY": "embeddings"}
        _write(rd2, "working/checkpoints/render-receipt.json", r)
        if vbc._chk_native_provider(rd2):
            fails.append("FIX-S36-42: a GOOGLE_API_KEY embedding key in generation_env "
                         "tripped _chk_native_provider (should be allowlisted).")
        # (c) a real native GENERATION provider (imagen) still fails the audit.
        rd3 = _mk_run(Path(tmp))
        _good_brief(rd3)
        m3 = dict(_GOOD_MEASURE)
        m3["providers_available"] = ["kie", "imagen"]
        _write(rd3, "working/checkpoints/measure-receipt.json", m3)
        if "AF-VID-PROVIDER-AUDIT" not in vbc._chk_provider_audit(rd3):
            fails.append("FIX-S36-42: a native 'imagen' generation provider did NOT "
                         "trip _chk_provider_audit (over-scoped allowlist).")
    return fails


# FIX-S36-44 regression: an MP4 that exists only under assets/ (raw stock footage)
# must NOT satisfy the final_mp4 deliverable, and a non-enum handoff must fail.
def _probe_final_mp4_and_handoff() -> list:
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        # (a) render receipt points final_mp4_path under assets/ -> DELIVERY-INCOMPLETE.
        rd = _mk_run(Path(tmp))
        _good_free(rd)
        (rd / "working" / "assets").mkdir(parents=True, exist_ok=True)
        (rd / "working" / "assets" / "stock.mp4").write_bytes(b"\x00" * 200_000)
        (rd / "working" / "final.mp4").unlink(missing_ok=True)
        r = dict(_GOOD_RENDER)
        r["final_mp4_path"] = "working/assets/stock.mp4"
        _write(rd, "working/checkpoints/render-receipt.json", r)
        if "AF-VID-DELIVERY-INCOMPLETE" not in vbc.run_postflight_gate(rd):
            fails.append("FIX-S36-44: an assets/ stock MP4 satisfied the final_mp4 "
                         "deliverable (raw footage passed).")
        # (b) a bogus non-enum handoff must fail even with a valid deliverable.
        rd2 = _mk_run(Path(tmp))
        _good_free(rd2)
        done = dict(_GOOD_BRIEF)
        done.update({"status": "complete", "actual_cost_usd": 0.0,
                     "handoff": "predelivery notes to somewhere-random"})
        _write(rd2, "working/job-manifest.json", done)
        if "AF-VID-DELIVERY-INCOMPLETE" not in vbc.run_postflight_gate(rd2):
            fails.append("FIX-S36-44: a non-enum handoff ('predelivery...') passed the "
                         "exact-enum handoff check (substring match leaked).")
    return fails


# Driver-level: AF-VID-PHASE-SKIPPED (enforced_by:driver) — trip via the driver's
# precondition gate (dispatch V-IMPROVE with no priors attested).
def _probe_phase_skipped() -> bool:
    manifest = ep.load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        reason = ep.check_phase_preconditions(rd, manifest["phases"], "V-IMPROVE")
    return "AF-VID-PHASE-SKIPPED" in reason


CASES = [
    ("AF-VID-BRIEF-INCOMPLETE", "_chk_brief_complete", _bad_brief, _good_brief),
    ("AF-VID-PREFLIGHT", "_chk_measure_receipt", _bad_measure, _good_measure),
    ("AF-VID-PROVIDER-AUDIT", "_chk_provider_audit", _bad_provider_audit, _good_measure),
    ("AF-VID-BUDGET-CAP", "_chk_budget_cap", _bad_budget_cap, _good_measure),
    ("AF-VID-RULE-ZERO", "_chk_rule_zero_approval", _bad_rule_zero, _good_rule_zero),
    ("AF-VID-APPROVAL-MISSING", "_chk_rule_zero_approval", _bad_approval_missing, _good_rule_zero),
    ("AF-VID-NO-FFPROBE", "_chk_render_receipt", _bad_no_ffprobe, _good_render),
    ("AF-VID-FABRICATED-RECEIPT", "_chk_kie_receipt_real", _bad_fabricated, _good_paid_render),
    ("AF-VID-NATIVE-PROVIDER", "_chk_native_provider", _bad_native_provider, _good_render),
    ("AF-VID-DELIVERY-INCOMPLETE", "run_postflight_gate", _bad_delivery, _good_delivery),
    ("AF-VID-BUDGET-OVERRUN", "_chk_budget_overrun", _bad_budget_overrun, _good_budget),
]


def main():
    triggered = set()
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for code, checker_name, make_bad, make_good in CASES:
            fn = vbc.CHECKERS.get(checker_name)
            if fn is None:
                failures.append(f"{code}: checker {checker_name!r} is not defined in "
                                "video_build_check.CHECKERS.")
                continue
            # NEGATIVE: the failing fixture MUST trip the gate, naming its AF code.
            rd_bad = _mk_run(tmp)
            make_bad(rd_bad)
            reason = fn(rd_bad)
            if not reason:
                failures.append(f"{code}: negative fixture did NOT trip {checker_name} "
                                "(gate is a no-op).")
            elif code not in reason:
                failures.append(f"{code}: {checker_name} tripped but its message does not "
                                f"name {code} (got: {reason[:80]!r}).")
            else:
                triggered.add(code)
            # POSITIVE: the passing fixture MUST pass the gate.
            rd_good = _mk_run(tmp)
            make_good(rd_good)
            ok_reason = fn(rd_good)
            if ok_reason:
                failures.append(f"{code}: POSITIVE fixture was REJECTED by {checker_name} "
                                f"(false positive): {ok_reason[:120]!r}.")

    # Phase-0 balance + driver-level phase-skip (not in CHECKERS — probed directly).
    if _probe_kie_balance():
        triggered.add("AF-VID-KIE-BALANCE")
    else:
        failures.append("AF-VID-KIE-BALANCE: unverifiable-balance fixture did not trip "
                        "kie_balance_preflight.")
    if _probe_phase_skipped():
        triggered.add("AF-VID-PHASE-SKIPPED")
    else:
        failures.append("AF-VID-PHASE-SKIPPED: no-priors fixture did not trip "
                        "check_phase_preconditions.")

    # FIX-S36-42 / FIX-S36-44 regression probes (additive; no new AF codes).
    failures.extend(_probe_google_embedding_allowed())
    failures.extend(_probe_final_mp4_and_handoff())

    AF_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    AF_COVERAGE.write_text(json.dumps({"triggered": sorted(triggered)}, indent=2))

    if failures:
        print("=== test_video_preflight: FAILURES ===", file=sys.stderr)
        for f in failures:
            print(f"  FAIL: {f}", file=sys.stderr)
        print(f"\n{len(failures)} failure(s). af-coverage emitted with "
              f"{len(triggered)} triggered code(s) at {AF_COVERAGE}.", file=sys.stderr)
        sys.exit(1)

    print("=== test_video_preflight: ALL GATES BEHAVE (negative tripped, positive passed) ===")
    print(f"triggered AF codes: {len(triggered)}")
    for c in sorted(triggered):
        print(f"  TRIGGERED {c}")
    print(f"af-coverage emitted: {AF_COVERAGE}")
    sys.exit(0)


if __name__ == "__main__":
    main()
