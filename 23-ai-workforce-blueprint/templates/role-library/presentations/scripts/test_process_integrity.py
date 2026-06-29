#!/usr/bin/env python3
"""
test_process_integrity.py — negative+positive tests for the FIX A-G process-integrity
gates added in v16.1.11. Run by presentations-lockstep CI alongside test_preflight.py.

Covers, per the /goal "guards/tests for each new gate":
  * no-skip proof certificate (prove-deck.py): empty-sha / skipped / out-of-order /
    self-authored-skip all FAIL; clean chain + valid owner-skip PASS.
  * one-question-per-turn intake (deck-intake-driver.py): mode-first, driver-owned
    next question, exact slide count honored, --complete blocks until confirmed,
    invalid typed answer rejected. (Delegates to the driver's own --selftest.)
  * mandatory + verified artifact_sha (run_signature_deck.attest_phase_verified):
    refuses a missing artifact; attests with a real sha + start/done reports.
  * producer != QC distinctness (build-workforce.enforce_producer_qc_distinctness):
    same->distinct heavy; already-distinct no-op; single-heavy independence.
  * fail-soft CC board (cc_board.chk_cc_registered): fail-closed on never-attempted,
    fail-soft on transport.
  * substance verifiers (phase_verifiers.verify_phase): unregistered -> existence-only;
    research evidence gate rejects an UNVERIFIED fact ledger (FM-5).
  * single-source departments / no duplicate slugs (canonical_slug): legacy aliases
    collapse to ONE canonical slug.

ZERO third-party deps. Exit 0 = all pass, 1 = any failure.
"""

import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if (detail and not cond) else ''}")
    if not cond:
        FAILS.append(name)


def _mk_run(plan_steps, atts, reports=None, skips=None):
    run = Path(tempfile.mkdtemp())
    ck = run / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    (ck / "declared_plan.json").write_text(json.dumps({"schema": "declared_plan/v1", "steps": plan_steps}))
    pm = {"phase_attestations": atts}
    if reports is not None:
        pm["client_reports"] = reports
    if skips is not None:
        pm["owner_skip_approvals"] = skips
    (ck / "process_manifest.json").write_text(json.dumps(pm))
    return run


def _prove(run):
    r = subprocess.run([sys.executable, str(HERE / "prove-deck.py"), "--run-dir", str(run), "--json"],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_no_skip_proof():
    print("test: no-skip proof certificate (FIX C)")
    # Non-report-required, no-substance-verifier phases isolate the skip/sha/order
    # logic from the report-gate; report_required:false is set explicitly so prove-deck
    # does not (correctly) also demand client reports for these.
    steps = [{"phase_id": "P-STYLE-PREVIEW", "order": 4.85, "name": "Style", "report_required": False},
             {"phase_id": "P-SHIFT-QC", "order": 7.5, "name": "Shift QC", "report_required": False}]
    ok = _mk_run(steps, [{"phase_id": "P-STYLE-PREVIEW", "artifact_sha": "a", "attested_at": "2026-06-29T10:00:00-04:00"},
                         {"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}])
    rc, _ = _prove(ok)
    check("clean chain PASS (exit 0) + certificate written", rc == 0 and (ok / "working/checkpoints/PROCESS-CERTIFICATE.json").exists())
    empty = _mk_run(steps, [{"phase_id": "P-STYLE-PREVIEW", "artifact_sha": "", "attested_at": "2026-06-29T10:00:00-04:00"},
                            {"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}])
    rc, out = _prove(empty)
    check("empty artifact_sha FAILS (exit 9)", rc == 9 and "empty artifact_sha" in out)
    skipped = _mk_run(steps, [{"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}])
    rc, _ = _prove(skipped)
    check("skipped step FAILS (exit 9)", rc == 9)
    ooo = _mk_run(steps, [{"phase_id": "P-STYLE-PREVIEW", "artifact_sha": "a", "attested_at": "2026-06-29T12:00:00-04:00"},
                          {"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}])
    rc, out = _prove(ooo)
    check("out-of-order FAILS (exit 9)", rc == 9 and "out-of-order" in out)
    selfauth = _mk_run(steps, [{"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}],
                       skips=[{"phase_id": "P-STYLE-PREVIEW", "owner_approved": True, "approved_by": "build_deck",
                               "reason": "x", "timestamp": "2026-06-29T00:00:00-04:00"}])
    rc, _ = _prove(selfauth)
    check("self-authored back-dated skip still FAILS (FM-4)", rc == 9)
    valid = _mk_run(steps, [{"phase_id": "P-SHIFT-QC", "artifact_sha": "b", "attested_at": "2026-06-29T11:00:00-04:00"}],
                    skips=[{"phase_id": "P-STYLE-PREVIEW", "owner_approved": True, "approved_by": "Owner (gateway)",
                            "reason": "client waived the style preview", "timestamp": "2026-06-29T09:00:00-04:00",
                            "gateway_msg_id": "tg-1"}])
    rc, _ = _prove(valid)
    check("valid owner skip PASSES (exit 0)", rc == 0)


def test_one_question_per_turn():
    print("test: one-question-per-turn intake driver (FIX D)")
    r = subprocess.run([sys.executable, str(HERE / "deck-intake-driver.py"), "--selftest"],
                       capture_output=True, text=True)
    check("deck-intake-driver --selftest passes", r.returncode == 0, r.stdout + r.stderr)


def test_artifact_sha_mandatory():
    print("test: mandatory verified artifact_sha + report-gated attest (FIX E)")
    rsd = importlib.import_module("run_signature_deck")
    rd = Path(tempfile.mkdtemp())
    (rd / "working/delivery").mkdir(parents=True)
    (rd / "working/delivery/PRESENTER-AUDIO.mp3").write_bytes(b"x" * 600000)
    target = {"id": "P9-DELIVER", "owning_role": "delivery-concierge",
              "produces_artifact": "working/delivery/PRESENTER-AUDIO.mp3",
              "client_report": {"required": True}}
    rc = rsd.attest_phase_verified(rd, target)
    pm = json.loads((rd / "working/checkpoints/process_manifest.json").read_text())
    att = pm["phase_attestations"][0]
    check("attests with non-empty artifact_sha + start/done reports",
          rc == 0 and att.get("artifact_sha") and rsd._report_recorded(rd, "P9-DELIVER", "start")
          and rsd._report_recorded(rd, "P9-DELIVER", "done"))
    rc2 = rsd.attest_phase_verified(Path(tempfile.mkdtemp()), target)
    check("refuses a missing artifact (rc=2)", rc2 == 2)


def test_producer_qc_distinctness():
    print("test: producer != QC distinctness (FIX A)")
    spec = importlib.util.spec_from_file_location(
        "bw", str(HERE.parent.parent.parent.parent / "scripts" / "build-workforce.py"))
    bw = importlib.util.module_from_spec(spec)
    sys.argv = ["build-workforce.py"]
    try:
        spec.loader.exec_module(bw)
    except SystemExit:
        pass
    fb = ["openrouter/moonshotai/kimi-k2.6", "ollama/deepseek-v4-pro:cloud", "openrouter/deepseek/deepseek-v4-pro"]
    same = {"agents": {"list": [
        {"id": "dept-presentations", "model": {"primary": "ollama/kimi-k2.6:cloud", "fallbacks": fb}},
        {"id": "dept-quality-control", "model": {"primary": "ollama/kimi-k2.6:cloud", "fallbacks": fb}}]}}
    r = bw.enforce_producer_qc_distinctness(same)
    qc = [a for a in same["agents"]["list"] if a["id"] == "dept-quality-control"][0]
    check("same model -> QC re-resolved to a DISTINCT heavy",
          r["changed"] and qc["model"]["primary"] != "ollama/kimi-k2.6:cloud")
    distinct = {"agents": {"list": [
        {"id": "dept-presentations", "model": {"primary": "ollama/kimi-k2.6:cloud", "fallbacks": []}},
        {"id": "dept-quality-control", "model": {"primary": "ollama/deepseek-v4-pro:cloud", "fallbacks": []}}]}}
    r2 = bw.enforce_producer_qc_distinctness(distinct)
    check("already-distinct -> no change", (not r2["changed"]) and r2["reason"] == "already_distinct")
    single = {"agents": {"list": [
        {"id": "dept-presentations", "model": {"primary": "ollama/kimi-k2.6:cloud", "fallbacks": []}},
        {"id": "dept-quality-control", "model": {"primary": "ollama/kimi-k2.6:cloud", "fallbacks": ["ollama/kimi-k2.6:cloud"]}}]}}
    r3 = bw.enforce_producer_qc_distinctness(single)
    check("single heavy model -> reasoning-config independence note",
          (not r3["changed"]) and r3["reason"] == "single_heavy_model_reasoning_independence")


def test_cc_board_failclosed():
    print("test: fail-soft CC board offline closeout (FIX G)")
    cc = importlib.import_module("cc_board")
    rd = Path(tempfile.mkdtemp())
    check("never-attempted -> AF-CC-UNREGISTERED (fail-closed)", bool(cc.chk_cc_registered(rd)))
    cc.stamp_task_id(rd, "task-1", attempted=True, registered=True)
    check("registered -> pass", cc.chk_cc_registered(rd) == "")
    rd2 = Path(tempfile.mkdtemp())
    cc.stamp_task_id(rd2, "deck:x", attempted=True, registered=False)
    check("attempted-but-transport-degraded -> pass (fail-soft)", cc.chk_cc_registered(rd2) == "")


def test_substance_verifiers():
    print("test: per-phase substance verifiers (FIX F)")
    pv = importlib.import_module("phase_verifiers")
    rd = Path(tempfile.mkdtemp())
    (rd / "working/research").mkdir(parents=True)
    ok, reason = pv.verify_phase("P9-DELIVER", rd)
    check("unregistered phase -> existence-only pass", ok and "existence-only" in reason)
    (rd / "working/research/fact_validation.json").write_text(
        json.dumps({"entries": [{"claim": "82% stat", "url": "http://x", "verified": False}]}))
    ok2, reason2 = pv.verify_phase("P-0.5-RESEARCH", rd)
    check("research evidence gate rejects UNVERIFIED fact ledger (FM-5)", (not ok2) and "UNVERIFIED" in reason2)


def test_single_source_departments():
    print("test: single-source departments / no duplicate slugs (ALSO)")
    spec = importlib.util.spec_from_file_location(
        "cs", str(HERE.parent.parent.parent.parent.parent / "shared-utils" / "canonical_slug.py"))
    cs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cs)
    # Forms the canonical map actually collapses: dept- prefix, case, and the
    # ALIAS_MAP legacy entries (suffix-only "-dept" is intentionally NOT collapsed).
    aliases = ["dept-marketing", "Dept-Marketing", "Marketing", "MARKETING", "marketing"]
    canon = {cs.canonical_dept_slug(a) for a in aliases}
    check("legacy marketing aliases collapse to ONE canonical slug", canon == {"marketing"}, str(canon))
    check("dept-quality-control normalises to quality-control",
          cs.canonical_dept_slug("dept-quality-control") == "quality-control")


def main():
    for t in (test_no_skip_proof, test_one_question_per_turn, test_artifact_sha_mandatory,
              test_producer_qc_distinctness, test_cc_board_failclosed, test_substance_verifiers,
              test_single_source_departments):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            FAILS.append(f"{t.__name__}:{exc!r}")
            print(f"  [FAIL] {t.__name__} raised {exc!r}")
    print()
    if FAILS:
        print(f"PROCESS-INTEGRITY TESTS FAILED: {len(FAILS)} failure(s): {FAILS}", file=sys.stderr)
        sys.exit(1)
    print("ALL PROCESS-INTEGRITY TESTS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
