#!/usr/bin/env python3
"""Tests for interview_gate.py (moved out of the gate's own --selftest).

Run: python3 -B scripts/test_interview_gate.py
Prints PASS for every case, exits 0 when all pass. Nothing is written outside the
temporary folder this file creates, and the HOME folder an acceptance run hands in
(env -i HOME="$(mktemp -d)") is asserted empty at the end.
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
GATE = HERE / "interview_gate.py"
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


def run_gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(GATE), "--registry", str(REGISTRY), *args],
                          capture_output=True, text=True)


def main() -> int:
    if not REGISTRY.exists():
        print(f"FAIL registry missing at {REGISTRY}")
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="interview-gate-test-"))
    try:
        sd = tmp_root / "answers"
        sd.mkdir()

        def g() -> Gate:
            return Gate(REGISTRY, sd)

        rc, n = g().cmd_next(); check("first question is company_name", n["id"] == "company_name")
        rc, n2 = g().cmd_next(); check("next is idempotent", n2["id"] == "company_name")
        check("required total is 15 before any answer", n["requiredTotal"] == 15)
        rc, r = g().cmd_answer("industry", "Coaching", "test", None); check("out-of-order refused", rc == 2)
        rc, r = g().cmd_answer("company_name", "", "test", None); check("empty refused", rc == 3)
        rc, r = g().cmd_answer("company_name", "Acme", "test", None); check("4-letter company name accepted", rc == 0)
        rc, r = g().cmd_skip("industry", False); check("required skip refused", rc == 2)
        rc, r = g().cmd_answer("industry", "coaching", "test", None); check("one-word industry accepted", rc == 0)
        rc, r = g().cmd_answer("what_you_sell", "Stuff", "test", None)
        check("short answer gets one follow-up", rc == 3 and r["reason"] == "too-short")
        rc, r = g().cmd_answer("what_you_sell", "Stuff", "test", None)
        check("second short answer accepted, flagged", rc == 0 and r["shortAccepted"])
        rc, r = g().cmd_complete_check(); check("not complete early", rc == 3)

        answers = {"business_stage": "Steady customers", "ideal_customer": "New managers at mid-size firms",
                   "unique_differentiator": "I did their job for ten years", "customer_feeling": "Relieved",
                   "brand_descriptors": "Honest, fast, friendly"}
        for k, v in answers.items():
            rc, r = g().cmd_answer(k, v, "test", None); check(f"{k} accepted", rc == 0)
        for opt in ("brand_evokes", "brand_voice", "brand_primary_color", "brand_logo"):
            rc, r = g().cmd_skip(opt, False); check(f"{opt} optional skip", rc == 0)
        rc, n = g().cmd_next(); check("resume lands on revenue goal after cold reload", n["id"] == "revenue_goal_12mo")
        rc, r = g().cmd_answer("revenue_goal_12mo", "A zillion", "test", None); check("bad choice refused", rc == 3)
        for k, v in {"revenue_goal_12mo": "Up to $100,000", "top_priority_90d": "Get more leads",
                     "time_drain": "Chasing invoices", "tools_used": "Stripe|Canva",
                     "customer_channels": "Instagram"}.items():
            rc, r = g().cmd_answer(k, v, "test", None); check(f"{k} accepted", rc == 0)
        rc, r = g().cmd_answer("department_review", "whatever", "test", None)
        check("board refuses a value that is not keep-all or edited", rc == 3)
        rc, r = g().cmd_answer("department_review", "keep-all", "test", None); check("board keep-all accepted", rc == 0)
        rc, n = g().cmd_next()
        check("{team} renders Marketing for Get more leads", n["id"] == "focus_dept_1" and "Marketing team" in n["prompt"])
        rc, n = g().cmd_next("Growth"); check("--team-name overrides the map", "Growth team" in n["prompt"])
        rc, r = g().cmd_answer("focus_dept_1", "Twenty new leads a month", "test", None); check("focus_dept_1 accepted", rc == 0)
        rc, r = g().cmd_complete_check(); check("complete with required only", rc == 0 and r["requiredAnswered"] == 15)
        rc, r = g().cmd_answer("brand_logo", "https://example.com/l.png", "test", None); check("circle back to a skip", rc == 0)

        before = (sd / LOG_NAME).read_text().strip().splitlines()
        rc, r = g().cmd_answer("company_name", "Acme", "test", None)
        check("identical re-submission is a no-op", rc == 0 and r.get("duplicate"))
        after = (sd / LOG_NAME).read_text().strip().splitlines()
        check("no log line for an identical re-submission", len(after) == len(before))
        check("log holds one line per accepted answer", len(after) == len(g().state["answers"]))
        check("answers log is mode 0600", (os.stat(sd / LOG_NAME).st_mode & 0o777) == 0o600)
        check("state file is mode 0600", (os.stat(sd / STATE_NAME).st_mode & 0o777) == 0o600)

        p = g().write_handoff()
        text = p.read_text()
        keys = ["status:", "next_question_number:", "last_question_number:", "total_questions_answered:",
                "total_questions_estimated:", "skipped_questions:", "started_date:", "last_updated:"]
        starts = [ln.split(" ")[0] for ln in text.splitlines()]
        check("handoff holds the eight keys at line starts", all(k in starts for k in keys))
        check("handoff says ready and 15 planned",
              "status: ready" in text.splitlines() and "total_questions_estimated: 15" in text.splitlines())

        # a torn last line in the answers log must not stop `next` or `status`
        with (sd / LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write('{"qid": "torn", "val')
        rc, n = g().cmd_next(); check("torn log line does not stop next", rc == 0)
        rc, s = g().cmd_status(); check("torn log line does not stop status", rc == 0)

        # two processes answering the same question at once -> exactly one log line
        d2 = tmp_root / "concurrent"
        d2.mkdir()
        cmd = [sys.executable, "-B", str(GATE), "--registry", str(REGISTRY), "--state-dir", str(d2),
               "answer", "--qid", "company_name", "--text", "Acme", "--source", "test"]
        procs = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(6)]
        codes = [p.wait() for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        lines = (d2 / LOG_NAME).read_text().strip().splitlines()
        check("six concurrent identical answers all exit 0", codes == [0] * 6)
        check("six concurrent identical answers leave exactly one log line", len(lines) == 1)

        # an unreadable state file is a TOOLING error (exit 1), never "not complete" (exit 3)
        d3 = tmp_root / "unreadable"
        d3.mkdir()
        (d3 / STATE_NAME).write_text("{ this is not json", encoding="utf-8")
        p = run_gate("--state-dir", str(d3), "complete-check")
        check("unreadable state -> exit 1, not 3", p.returncode == 1)
        p = run_gate("--state-dir", str(d3), "next")
        out = json.loads(p.stdout or "{}")
        check("unreadable state says undetermined, never 'not answered'", out.get("undetermined") is True)
        missing = tmp_root / "no-such-registry.json"
        p = subprocess.run([sys.executable, "-B", str(GATE), "--registry", str(missing),
                            "--state-dir", str(d3), "next"], capture_output=True, text=True)
        check("missing registry -> exit 1", p.returncode == 1)

        # the platform workspace resolver: environment first, then $HOME/.openclaw/workspace
        p = subprocess.run([sys.executable, "-B", "-c",
                            "import sys; sys.path.insert(0, sys.argv[1]); import interview_gate as g;"
                            " print(g.default_state_dir())",
                            str(HERE)],
                           capture_output=True, text=True,
                           env={"HOME": str(tmp_root / "fake-home"), "PATH": os.environ.get("PATH", ""),
                                "OPENCLAW_WORKSPACE_PATH": str(tmp_root / "ws")})
        check("default state dir follows OPENCLAW_WORKSPACE_PATH",
              p.returncode == 0 and p.stdout.strip() == str(tmp_root / "ws" / "company-discovery"))
        p = subprocess.run([sys.executable, "-B", "-c",
                            "import sys; sys.path.insert(0, sys.argv[1]); import interview_gate as g;"
                            " print(g.default_state_dir())",
                            str(HERE)],
                           capture_output=True, text=True,
                           env={"HOME": str(tmp_root / "fake-home"), "PATH": os.environ.get("PATH", ""),
                                "OPENCLAW_WORKSPACE_ROOT": str(tmp_root / "ws2")})
        check("default state dir follows OPENCLAW_WORKSPACE_ROOT",
              p.returncode == 0 and p.stdout.strip() == str(tmp_root / "ws2" / "company-discovery"))

        # nothing was written into the HOME folder handed in by the acceptance run
        home = Path(os.environ.get("HOME", ""))
        home_entries = sorted(p.name for p in home.iterdir()) if home.is_dir() else []
        check("HOME folder stays empty", not (home.is_dir() and home_entries))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    if FAILS:
        print(f"FAIL {len(FAILS)} of {CASES} cases: {FAILS}")
        return 1
    print(f"PASS {CASES} cases, registry {REGISTRY.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
