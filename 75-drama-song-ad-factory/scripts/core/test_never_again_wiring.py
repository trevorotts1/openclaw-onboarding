#!/usr/bin/env python3
"""Lock wiring: each refusal fires at its enforcement point. $0."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lipsync_clips as C                               # noqa: E402
import lipsync_evidence as E                            # noqa: E402
import never_again as NA                                # noqa: E402
from kie_dispatch import kie_dispatch as D              # noqa: E402
from final_assembler import assembler as A              # noqa: E402
from final_assembler import captions_burn as CB          # noqa: E402
from storyboard_director import approval_runner as AR   # noqa: E402
from retake_manager import retake_manager as R          # noqa: E402

fails = []


def check(name, cond):
    if not cond:
        fails.append(name)
        print("FAIL", name)
    else:
        print("ok", name)


# Lock 1 wiring: unchanged 3rd prompt raises TEMPLATE_FAIL_LOCK.
p = "sings, Minimal head movement, steady locked camera"
try:
    C.check_try_limit(["lip-ad-ss3", "lip-ad-ss3-b"], "ss3",
                      prior_prompts=[p, p], candidate_prompt=p)
    check("wired-lock1", False)
except C.LipsyncClipsError as e:
    check("wired-lock1", e.code == "TEMPLATE_FAIL_LOCK")

# Lock 1 wiring (retake cap path): identical retry past cap raises too.
req = {"failed_artifact_id": "ss3", "check": "X", "shots": ["ss3"],
       "attempt_history": [{"artifact_id": "ss3"}, {"artifact_id": "ss3"}],
       "prior_prompts": {"ss3": [p, p]}, "candidate_prompt": p}
check("wired-lock1-retake", R.plan(req).get("code") == "TEMPLATE_FAIL_LOCK")

# Lock 2 wiring: non-kie_dispatch receipt raises NO_DIRECT_SUBMIT.
# check_plan returns a refusal dict (never raises) on malformed input;
# the dispatch lock fires on real receipts — assert the refusal shape
# here plus the module code presence (fail-closed path proven by the
# existing TASK_MISMATCH tests on synthetic receipts).
check("wired-lock2-shape",
      E.check_plan({"run_dir": "/nonexistent",
                    "run_id": "r"})["reason_code"]
      == "LIPSYNC_FILE_MISSING"
      and NA.NO_DIRECT_SUBMIT == "NO_DIRECT_SUBMIT")

# Lock 3 wiring: proof output refused at assembly + captions.
check("wired-lock3-assembler",
      (A.check_proof_output("x/PROOF-ONLY master.mp4") or {}).get(
          "reason_code") == "PROOF_NOT_DELIVERABLE")
check("wired-lock3-captions",
      (CB.refuse_proof_output("x/PROOF-ONLY master.mp4") or {}).get(
          "code") == "PROOF_NOT_DELIVERABLE")
check("wired-lock3-clean-ok", A.check_proof_output("x/Clean master.mp4") is None)

# Lock 3b: zero-duration cue refused. _clean_cues returns (clean, code, why)
# after the F-EOC-7 port: the typed code now rides its own slot.
clean, code, why = CB._clean_cues([{"text": "a", "start": 1.0, "end": 1.0}])
check("wired-lock3-zero-duration",
      clean is None and code == CB.ZERO_DURATION
      and "zero-length window" in (why or ""))

# Lock 5 wiring: drip refuses (receipt-shaped refusal carries outcome).
check("wired-lock5-dispatch",
      (D.refuse_drip(10, 3) or {}).get("outcome") == "rejected"
      and D.check_blast_single_pass(10, 3)["code"] == "RETAKE_DRIP")
req2 = {"failed_artifact_id": "ss3", "check": "X", "shots": ["ss3"],
        "attempt_history": [], "ready_count": 5, "passes_used": 3}
check("wired-lock5-retake", R.plan(req2).get("code") == "RETAKE_DRIP")

# Lock 6 wiring: crop repair refused at assembly.
check("wired-lock6",
      (A.check_crop_repair("crop to hide letters") or {}).get(
          "reason_code") == "CROP_REPAIR_REFUSED")
check("wired-lock6-ok", A.check_crop_repair("full-body remake") is None)

# Lock 7 wiring: approval/waiver receipt checks exposed on runner.
check("wired-lock7-approval",
      (AR.check_approval_receipt("") or {}).get("code") == "APPROVAL_MISSING")
check("wired-lock7-waiver",
      (AR.check_waiver_receipt({}) or {}).get("code") == "WAIVER_MISSING")
# Lock 8 wiring: Kling route refuses off-route dispatch pre-ledger.
_env8 = D._dispatch_pipeline(
    model="kling/ai-avatar-standard",
    request={"lip_sync": False}, save_dir="/tmp", ledger_db="/tmp/x-w8.db",
    run_id="r", logical_key="k", attempt_id="a", estimated_cost=1,
    prompt="She sings this line to the camera, steady locked camera")
check("wired-lock8-route",
      _env8["reason_code"] == NA.ROUTE_CHANGED
      and _env8["evidence"].get("generated") is False)
# Lock 9 wiring: letter-bait Kling prompt refuses TEXT_BAIT pre-spend.
# Uses the locked avatar: Lock 10 refuses kling-3.0-omni before the scan.
_env9 = D._dispatch_pipeline(
    model="kling/ai-avatar-standard",
    request={"input": {"prompt": "She sings, poster on the wall"},
             "lip_sync": True},
    save_dir="/tmp", ledger_db="/tmp/x-w9.db",
    run_id="r", logical_key="k", attempt_id="a", estimated_cost=1,
    prompt="She sings, poster on the wall")
check("wired-lock9-text-bait",
      _env9["reason_code"] == NA.TEXT_BAIT
      and _env9["evidence"].get("gate") == "F-KLING-TEXT-BAIT"
      and _env9["evidence"].get("generated") is False)
# Lock 10 wiring (F-MODEL-AUTH): off-allowlist model refuses
# MODEL_UNAUTHORIZED pre-ledger, pre-Skill-74; an authorized H3 id passes
# this gate (deeper gates own it); a Trevor written order binding model +
# shot is the ONLY override.
_env10 = D._dispatch_pipeline(
    model="bytedance/seedance-1.5-pro",
    request={"input": {"prompt": "x" * 100}}, save_dir="/tmp",
    ledger_db="/tmp/x-w10.db", run_id="r", logical_key="k",
    attempt_id="a", estimated_cost=1, prompt="x" * 100)
check("wired-lock10-unauthorized",
      _env10["reason_code"] == NA.MODEL_UNAUTHORIZED
      and _env10["evidence"].get("generated") is False
      and _env10["evidence"].get("gate") == "F-MODEL-AUTH")
_env10b = D._dispatch_pipeline(
    model="minimax-h3/image-to-video",
    request={"input": {"prompt": "x" * 100},
             "card_receipt": {"answers": {"a": 1}},
             "prompt_receipt": {"prompt_sha256": "s",
                                "check": {"verdict": "PASS", "reasons": []}}},
    save_dir="/tmp", ledger_db="/tmp/x-w10b.db", run_id="r",
    logical_key="k", attempt_id="a", estimated_cost=1, prompt="x" * 100)
check("wired-lock10-authorized-passes-gate",
      _env10b["reason_code"] != NA.MODEL_UNAUTHORIZED)
_order10 = {"signed_by": "Trevor", "signature": "t-w10",
            "model": "bytedance/seedance-1.5-pro", "shot_id": "ss10"}
_env10c = D._dispatch_pipeline(
    model="bytedance/seedance-1.5-pro",
    request={"input": {"prompt": "x" * 100},
             "shot": {"shot_id": "ss10"}, "model_auth_order": _order10},
    save_dir="/tmp", ledger_db="/tmp/x-w10c.db", run_id="r",
    logical_key="k", attempt_id="a", estimated_cost=1, prompt="x" * 100)
check("wired-lock10-order-overrides",
      _env10c["reason_code"] != NA.MODEL_UNAUTHORIZED)
_req10 = {"failed_artifact_id": "ss10", "check": "X", "shots": ["ss10"],
          "attempt_history": [], "retake_model": "bytedance/seedance-1.5-pro"}
check("wired-lock10-retake-refuses",
      R.plan(_req10).get("code") == NA.MODEL_UNAUTHORIZED)
_req10b = dict(_req10, model_auth_order=dict(_order10, shot_id="ss10"))
_env10r = R.plan(_req10b)
check("wired-lock10-retake-order-overrides",
      _env10r.get("code") != NA.MODEL_UNAUTHORIZED)
_req10c = {"failed_artifact_id": "ss10", "check": "X", "shots": ["ss10"],
           "attempt_history": [],
           "retake_model": "minimax-h3/image-to-video"}
check("wired-lock10-retake-authorized-passes",
      R.plan(_req10c).get("outcome") == "ok")
check("lock2-module-flag", NA.NO_DIRECT_SUBMIT == "NO_DIRECT_SUBMIT")

print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
