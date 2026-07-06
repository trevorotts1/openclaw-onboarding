#!/usr/bin/env python3
"""
test_ad_recovery.py — SELF-CORRECT + PARK-AND-RESUME proof suite (Skill 48).

================================================================================
Proves the two-tier recovery contract and emits working/recovery-coverage.json,
the file Guard A (ad_gate_integrity_check.py) consumes to require, per autofail:
  * recovery:"auto"  ⇒ a REDO probe AND a budget→PARK probe both tripped;
  * recovery:"park"  ⇒ an immediate-PARK-no-retry probe tripped.

It then runs three end-to-end proofs through the real ad_director foreman:
  (A) RECOVERABLE: a fixable gate failure self-heals — REDO the one artifact, fix
      it, the run ADVANCES to completion.
  (B) NON-RECOVERABLE + RESUME: a human-gated / park condition writes a DURABLE
      checkpoint (PARKED.json + a box pointer under workspace/.park/fbad/), PAUSES,
      and a resume re-enters at the exact last-incomplete phase once the blocker
      clears — with ZERO new paid ledger events (never re-charges / re-uploads).
  (C) DANGEROUS GATE STOPS: a fabrication/tampering gate (image task-id) cannot be
      self-corrected past — it parks immediately, no REDO is ever offered, and a
      resume while still broken stays parked.
  (D) DURABILITY REFUSAL: a PAID run pinned to a reboot-wiped tmp dir is REFUSED.

EXIT CODES:
    0 — every probe behaved + every end-to-end proof passed; coverage emitted.
    1 — a recovery probe or proof failed.
"""

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ad_recovery as rec        # noqa: E402
import ad_director as ad         # noqa: E402
import ad_build_check as abc     # noqa: E402
from test_ad_preflight import _good, _load, _write, _mk_run  # noqa: E402

RECOVERY_COVERAGE = HERE / "working" / "recovery-coverage.json"


def _fresh(tmp: Path) -> Path:
    rd = Path(tempfile.mkdtemp(dir=tmp))
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return rd


# ---------------------------------------------------------------------------
# Per-code coverage probes (drive the pure engine decision, ad_recovery.classify_fail)
# ---------------------------------------------------------------------------
def _coverage(manifest, tmp: Path):
    auto_redo, auto_budget_park, park_immediate = set(), set(), set()
    failures = []
    for a in manifest["autofails"]:
        code = a["code"]
        recovery, maxn = rec.policy(code, manifest)
        key = f"PHASE:{code}:*"
        if recovery == "park":
            rd = _fresh(tmp)
            d = rec.classify_fail(rd, manifest, "PHASE", code, artifact_bytes=b"x")
            if d["decision"] != "PARK" or d["reason"] != "park_gate":
                failures.append(f"{code}: park gate did not PARK immediately "
                                f"(got {d['decision']}/{d.get('reason')}).")
            elif rec.attempts(rd, key) != 0:
                failures.append(f"{code}: park gate WAS bumped — a dangerous gate must "
                                "never get a retry path.")
            else:
                park_immediate.add(code)
            continue
        # recovery == "auto": one fresh run, REDO until the budget parks it.
        rd = _fresh(tmp)
        saw_redo = False
        parked = None
        for i in range(maxn + 3):
            d = rec.classify_fail(rd, manifest, "PHASE", code,
                                  artifact_bytes=f"v{i}".encode())
            if d["decision"] == "REDO":
                saw_redo = True
                continue
            if d["decision"] == "PARK":
                parked = d
                break
        if saw_redo:
            auto_redo.add(code)
        else:
            failures.append(f"{code}: auto gate never offered a REDO.")
        if parked and parked.get("reason") == "budget_exhausted":
            auto_budget_park.add(code)
        else:
            failures.append(f"{code}: auto gate did not PARK with budget_exhausted after "
                            f"max={maxn} attempts (got {parked}).")
    return ({"auto_redo": sorted(auto_redo),
             "auto_budget_park": sorted(auto_budget_park),
             "park_immediate": sorted(park_immediate)}, failures)


# ---------------------------------------------------------------------------
# End-to-end proofs through the real ad_director foreman
# ---------------------------------------------------------------------------
def _proof_recoverable(manifest, tmp, oc_root) -> list:
    """(A) A fixable BODY-CTA failure: REDO the one artifact, fix it, run completes."""
    f = []
    rd = _mk_run(tmp)
    _good(rd)
    r = _load(rd, "working/checkpoints/s2-receipt.json")
    r["bodies"][2]["cta_count"] = 1   # break AF-FBAD-BODY-CTA (recovery:auto)
    _write(rd, "working/checkpoints/s2-receipt.json", r)

    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "REDO" and v.get("failing_af") == "AF-FBAD-BODY-CTA"
            and v.get("attempt") == 1 and code == 0):
        f.append(f"(A) expected REDO AF-FBAD-BODY-CTA attempt 1 (exit 0), got "
                 f"{v.get('action')}/{v.get('failing_af')}/attempt={v.get('attempt')}/exit={code}.")
        return f
    # fix the one failing artifact (what the maker would do with the feedback)
    r = _load(rd, "working/checkpoints/s2-receipt.json")
    r["bodies"][2]["cta_count"] = 3
    _write(rd, "working/checkpoints/s2-receipt.json", r)
    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "DONE" and code == 0):
        f.append(f"(A) after the fix expected DONE (exit 0), got {v.get('action')}/exit={code}.")
    if rec.read_park(rd) is not None:
        f.append("(A) a recoverable failure must NOT have left a park behind.")
    return f


def _proof_park_and_resume(manifest, tmp, oc_root) -> list:
    """(B) Missing human approval parks durably, then resumes from the exact spot with
    ZERO new paid ledger events."""
    f = []
    rd = _mk_run(tmp)
    _good(rd)
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"approved_by": "Owner Name", "approval_received_at": "2026-06-26T10:00:00-0400",
            "owner_confirmed": False})   # human gate NOT satisfied (AF-FBAD-APPROVE)

    led_before = abc._ledger(rd)
    events_before = len(led_before.get("events", []))
    spent_before = led_before.get("spent_usd")

    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "AWAIT_HUMAN" and v.get("parked_by") == "AF-FBAD-APPROVE"
            and code == 5):
        f.append(f"(B) expected AWAIT_HUMAN AF-FBAD-APPROVE (exit 5), got "
                 f"{v.get('action')}/{v.get('parked_by')}/exit={code}.")
        return f
    park = rec.read_park(rd)
    if park is None:
        f.append("(B) no PARKED.json checkpoint written.")
        return f
    ptr = rec.box_park_dir() / f"{park.get('run_id')}.parked"
    if not ptr.exists():
        f.append(f"(B) no box-level park pointer at {ptr}.")
    if str(rec.box_park_dir()).find("/workspace/.park/fbad") < 0:
        f.append(f"(B) box park dir is not under workspace/.park/fbad ({rec.box_park_dir()}).")
    # S7 (paid-downstream) must already be attested in the checkpoint (re-enter at PUBLISH).
    if "S7-DELIVER" not in park.get("attested_phases", []):
        f.append("(B) checkpoint did not preserve the already-attested S7-DELIVER phase.")

    # resume while STILL unapproved -> stays parked (never auto-clears).
    v, code = ad.cmd_resume(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "STILL_PARKED" and code == 5):
        f.append(f"(B) resume before approval should STAY parked, got {v.get('action')}/exit={code}.")

    # owner approves -> resume clears and completes.
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"approved_by": "Owner Name", "approval_received_at": "2026-06-26T10:05:00-0400",
            "owner_confirmed": True})
    v, code = ad.cmd_resume(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "DONE" and code == 0):
        f.append(f"(B) resume after approval expected DONE (exit 0), got {v.get('action')}/exit={code}.")
    if rec.read_park(rd) is not None or ptr.exists():
        f.append("(B) the park (PARKED.json / box pointer) was not cleared after resume.")

    led_after = abc._ledger(rd)
    if len(led_after.get("events", [])) != events_before or led_after.get("spent_usd") != spent_before:
        f.append(f"(B) RESUME RE-CHARGED: ledger events {events_before}->"
                 f"{len(led_after.get('events', []))}, spent {spent_before}->"
                 f"{led_after.get('spent_usd')}. Resume must skip paid work idempotently.")
    return f


def _proof_dangerous_stops(manifest, tmp, oc_root) -> list:
    """(C) A fabrication gate (image task-id) cannot be self-corrected past."""
    f = []
    rd = _mk_run(tmp)
    _good(rd)
    r = _load(rd, "working/checkpoints/s5-image-receipt.json")
    r["images"][3]["kie_task_id"] = "TASK_ID"   # placeholder => AF-FBAD-IMAGE-TASKID (park)
    _write(rd, "working/checkpoints/s5-image-receipt.json", r)

    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "PARK" and v.get("parked_by") == "AF-FBAD-IMAGE-TASKID"
            and v.get("park_class") == "fabrication" and code == 5):
        f.append(f"(C) expected immediate PARK AF-FBAD-IMAGE-TASKID/fabrication (exit 5), got "
                 f"{v.get('action')}/{v.get('parked_by')}/{v.get('park_class')}/exit={code}.")
        return f
    # no REDO was ever offered: the attempt counter for this gate stays 0.
    if rec.attempts(rd, "S5-IMAGE-GEN:AF-FBAD-IMAGE-TASKID:*") != 0:
        f.append("(C) a dangerous gate was given a retry budget — it must park with no retry.")
    # recover again -> still parked, never advances past the gate.
    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "PARKED" and code == 5):
        f.append(f"(C) a second recover must stay PARKED, got {v.get('action')}/exit={code}.")
    # resume while still fabricated -> stays parked (the real checker still fails).
    v, code = ad.cmd_resume(rd, manifest, allow_ephemeral=True)
    if not (v.get("action") == "STILL_PARKED" and code == 5):
        f.append(f"(C) resume while still fabricated must STAY parked, got "
                 f"{v.get('action')}/exit={code}.")
    return f


def _proof_paid_tmp_refused(manifest, tmp, oc_root) -> list:
    """(D) A PAID run pinned to a reboot-wiped tmp dir is refused (durability guard)."""
    f = []
    rd = _mk_run(tmp)          # tmp is a /var/folders or /tmp temp dir
    _good(rd)                  # estimated_cost_usd 0.65 => paid_in_scope
    if not abc._paid_in_scope(rd):
        f.append("(D) fixture was not paid_in_scope — refusal probe is meaningless.")
        return f
    v, code = ad.cmd_recover(rd, manifest, allow_ephemeral=False)
    if not (v.get("action") == "REFUSE" and code == 2):
        f.append(f"(D) a paid run under a tmp dir must be REFUSED (exit 2), got "
                 f"{v.get('action')}/exit={code}.")
    return f


def _proof_ghl_resume_recovers(tmp) -> list:
    """(E) FIX-S36-45(ii): on a resume where the receipt LOST an already-hosted image
    entry, ad_ghl_push recovers it from the durable ledger — never re-uploading (no
    re-charge) and never dropping it from delivered[]."""
    f = []
    import ad_ghl_push          # noqa: PLC0415
    import ad_run_ledger as led  # noqa: PLC0415
    import ghl_media            # noqa: PLC0415

    rd = Path(tempfile.mkdtemp(dir=tmp))
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    led.init(rd, "fbad-ghl-001", 5.0)
    # image 0 was hosted on a prior run; the ledger stored its delivered entry.
    stored = {"idx": 0, "image_url": "https://storage.googleapis.com/msgsndr/loc/ad0.png",
              "http_status": 200, "file_id": "f0", "folder_id": "fold0"}
    led.record(rd, "upload", "upload:ad0.png", 0.0, stored)
    # ...but the receipt's delivered[] is now empty (the campaign is already filed —
    # campaign_id stamped — yet the hosted-image list was lost / regenerated).
    (rd / "working" / "checkpoints" / "s7-deliver-receipt.json").write_text(
        json.dumps({"campaign_id": "fbad-ghl-001", "delivered": []}))

    calls = {"upload": 0}

    def _no_upload(*_a, **_k):
        calls["upload"] += 1
        return {"url": "https://SHOULD-NOT-BE-CALLED", "http": 200, "fileId": "x"}

    orig = (ghl_media.resolve_location_pit, ghl_media.resolve_location_id,
            ghl_media.create_media_folder, ghl_media.upload_media)
    ghl_media.resolve_location_pit = lambda *a, **k: "pit"
    ghl_media.resolve_location_id = lambda *a, **k: "loc"
    ghl_media.create_media_folder = lambda *a, **k: {"folderId": "fold0"}
    ghl_media.upload_media = _no_upload
    try:
        receipt = ad_ghl_push.push(rd, [str(rd / "ad0.png")])
    finally:
        (ghl_media.resolve_location_pit, ghl_media.resolve_location_id,
         ghl_media.create_media_folder, ghl_media.upload_media) = orig

    if calls["upload"] != 0:
        f.append(f"(E) an already-hosted image was RE-UPLOADED ({calls['upload']} call(s)) "
                 "— a resume must recover from the ledger, never re-pay.")
    delivered = receipt.get("delivered", [])
    if not any(d.get("image_url") == stored["image_url"] for d in delivered):
        f.append("(E) the already-hosted image was DROPPED from delivered[] — the entry "
                 "must be recovered from the ledger, not lost when the receipt was.")
    return f


def main():
    manifest = ad.load_manifest()
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        oc_root = tmp / "oc-root"
        (oc_root / "workspace").mkdir(parents=True, exist_ok=True)
        os.environ["FBAD_OC_ROOT"] = str(oc_root)   # durable root -> a writable temp

        coverage, cov_fail = _coverage(manifest, tmp)
        failures += cov_fail

        # per-code coverage completeness (mirrors Guard A's requirement).
        for a in manifest["autofails"]:
            code = a["code"]
            recovery, _ = rec.policy(code, manifest)
            if recovery == "auto":
                if code not in coverage["auto_redo"]:
                    failures.append(f"{code}: auto gate missing from auto_redo coverage.")
                if code not in coverage["auto_budget_park"]:
                    failures.append(f"{code}: auto gate missing from auto_budget_park coverage.")
            else:
                if code not in coverage["park_immediate"]:
                    failures.append(f"{code}: park gate missing from park_immediate coverage.")

        failures += _proof_recoverable(manifest, tmp, oc_root)
        failures += _proof_park_and_resume(manifest, tmp, oc_root)
        failures += _proof_dangerous_stops(manifest, tmp, oc_root)
        failures += _proof_paid_tmp_refused(manifest, tmp, oc_root)
        failures += _proof_ghl_resume_recovers(tmp)

    RECOVERY_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY_COVERAGE.write_text(json.dumps(coverage, indent=2))

    if failures:
        print("=== test_ad_recovery: FAILURES ===", file=sys.stderr)
        for fl in failures:
            print(f"  FAIL: {fl}", file=sys.stderr)
        print(f"\n{len(failures)} failure(s). recovery-coverage emitted at "
              f"{RECOVERY_COVERAGE}.", file=sys.stderr)
        sys.exit(1)

    print("=== test_ad_recovery: SELF-CORRECT + PARK-AND-RESUME ALL PROVEN ===")
    print(f"auto gates (redo + budget-park): {len(coverage['auto_redo'])} / "
          f"{len(coverage['auto_budget_park'])}")
    print(f"park gates (immediate park):     {len(coverage['park_immediate'])}")
    print("end-to-end: (A) recoverable self-heals  (B) park+resume, no re-charge  "
          "(C) dangerous gate stops  (D) paid-tmp refused")
    print(f"recovery-coverage emitted: {RECOVERY_COVERAGE}")
    sys.exit(0)


if __name__ == "__main__":
    main()
