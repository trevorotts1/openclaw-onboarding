#!/usr/bin/env python3
"""Tests for answers_to_config.py.

Run: python3 -B scripts/test_answers_to_config.py
Prints PASS for every case, exits 0 when all pass. Nothing is written outside the
temporary folder this file creates.

The completed interview is the gate self-test's own fixture, answered through the
gate itself, so the gate state this file hands in is the shape a real interview
leaves behind.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "answers_to_config.py"
REGISTRY = HERE.parent / "interview" / "questions.v2.json"

sys.path.insert(0, str(HERE))
from interview_gate import Gate, LOG_NAME, STATE_NAME  # noqa: E402

FAILS = []
CASES = 0


def check(name: str, cond) -> None:
    global CASES
    CASES += 1
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")
        FAILS.append(name)


def completed_fixture(state_dir: Path) -> None:
    """Answer the whole interview through the gate: the gate self-test's completed case."""
    def g() -> Gate:
        return Gate(REGISTRY, state_dir)

    def answer(qid: str, text: str, times: int = 1) -> None:
        for _ in range(times):
            rc, _out = g().cmd_answer(qid, text, "test", None)
        if rc != 0:
            raise SystemExit(f"fixture: answering {qid} exited {rc}")

    answer("company_name", "Acme")
    answer("industry", "coaching")
    answer("what_you_sell", "Stuff", times=2)          # one too-short follow-up, then accepted
    answer("business_stage", "Steady customers")
    answer("ideal_customer", "New managers at mid-size firms")
    answer("unique_differentiator", "I did their job for ten years")
    answer("customer_feeling", "Relieved")
    answer("brand_descriptors", "Honest, fast, friendly")
    for qid in ("brand_evokes", "brand_voice", "brand_primary_color", "brand_logo"):
        rc, _out = g().cmd_skip(qid, False)
        if rc != 0:
            raise SystemExit(f"fixture: skipping {qid} exited {rc}")
    answer("revenue_goal_12mo", "Up to $100,000")
    answer("top_priority_90d", "Get more leads")
    answer("time_drain", "Chasing invoices")
    answer("tools_used", "Stripe|Canva")
    answer("customer_channels", "Instagram")
    answer("department_review", "keep-all")
    answer("focus_dept_1", "Twenty new leads a month")
    rc, _out = g().cmd_complete_check()
    if rc != 0:
        raise SystemExit("fixture: the interview did not complete")


def run_config(state: Path, state_dir: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(CONFIG), "--state", str(state),
                           "--state-dir", str(state_dir), "--out", str(out)],
                          capture_output=True, text=True)


def main() -> int:
    if not REGISTRY.exists():
        print(f"FAIL registry missing at {REGISTRY}")
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="answers-to-config-test-"))
    try:
        # ---- a completed interview becomes the build's config ----------------------------
        sd = tmp_root / "answers"
        sd.mkdir()
        completed_fixture(sd)
        state = tmp_root / "build-state.json"
        state.write_text(json.dumps({"canonicalReconciliation": {"decisions": {}}}), encoding="utf-8")
        out = tmp_root / "workforce-config.generated.json"

        p = run_config(state, sd, out)
        check("completed interview exits 0", p.returncode == 0)
        check("config file written", out.is_file())
        config = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}

        check("company_name is the answer", config.get("company_name") == "Acme")
        check("industry is the answer", config.get("industry") == "coaching")
        check("company_description is the what_you_sell answer", config.get("company_description") == "Stuff")
        check("biggest_challenge is the time_drain answer", config.get("biggest_challenge") == "Chasing invoices")
        check("option is A", config.get("option") == "A")
        check("tools turns the pipe into a comma", config.get("tools") == "Stripe, Canva")
        check("the answers log path is recorded",
              str(config.get("_answersLog", "")).endswith(LOG_NAME) and str(sd) in str(config.get("_answersLog")))

        departments = config.get("departments") or {}
        check("29 department keys, one per declinable canonical department", len(departments) == 29)
        check("master-orchestrator is not a config key", "master-orchestrator" not in departments)
        check("the answered team carries the focus answer",
              (departments.get("marketing") or {}).get("activities") == "Twenty new leads a month")
        check("the answered team carries the revenue goal as its kpi",
              (departments.get("marketing") or {}).get("kpis") == "Up to $100,000")
        check("every department is enabled",
              all(isinstance(d, dict) and d.get("enabled") is True for d in departments.values()))
        check("every department shares the one tools string",
              all(d.get("tools") == "Stripe, Canva" for d in departments.values()))

        # nothing invented: every leaf is an answer string, an empty string, true, or "A"
        gate_state = json.loads((sd / STATE_NAME).read_text(encoding="utf-8"))
        answers = {entry["value"] for entry in gate_state["answers"].values()}
        allowed = answers | {v.replace("|", ", ") for v in answers}
        allowed |= {"", "A", "answers_to_config.py", str(sd / LOG_NAME)}
        leaves = [v for k, v in config.items() if k != "departments"]
        for dept in departments.values():
            leaves.extend(v for k, v in dept.items() if k != "enabled")
        check("no value is invented", all(isinstance(v, str) and v in allowed for v in leaves))
        check("no industryPack is written by hand", "industryPack" not in config)
        check("config is mode 0600", (os.stat(out).st_mode & 0o777) == 0o600)

        # ---- a provenanced decline removes exactly that department -----------------------
        decline_state = tmp_root / "build-state-declined.json"
        decline_state.write_text(json.dumps({"canonicalReconciliation": {"decisions": {
            "video": {"decision": "no", "source": "owner-interview",
                      "decidedAt": "2026-01-01T00:00:00Z", "decidedBy": "owner"}}}}), encoding="utf-8")
        out2 = tmp_root / "declined.json"
        p = run_config(decline_state, sd, out2)
        declined_cfg = json.loads(out2.read_text(encoding="utf-8")) if out2.is_file() else {}
        check("a declined department exits 0", p.returncode == 0)
        check("a declined department is dropped", "video" not in (declined_cfg.get("departments") or {}))
        check("a decline leaves 28 department keys", len(declined_cfg.get("departments") or {}) == 28)

        # ---- an incomplete interview writes nothing -------------------------------------
        short_sd = tmp_root / "incomplete"
        short_sd.mkdir()
        completed_fixture(short_sd)
        gs = json.loads((short_sd / STATE_NAME).read_text(encoding="utf-8"))
        gs["answers"].pop("company_name", None)
        (short_sd / STATE_NAME).write_text(json.dumps(gs), encoding="utf-8")
        out3 = tmp_root / "incomplete.json"
        p = run_config(state, short_sd, out3)
        check("one required answer missing exits 3", p.returncode == 3)
        check("nothing is written when the interview is incomplete", not out3.exists())
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    if FAILS:
        print(f"FAIL {len(FAILS)} of {CASES} cases: {FAILS}")
        return 1
    print(f"PASS {CASES} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
