#!/usr/bin/env python3
"""The 15-minute finish check must not rewrite the state and progress files (WF-121, WF-122).

Fixture copied from test_reliability_contracts.py setUp. Run:
  python3 test-finalize-does-not-churn.py   (exit 0 = PASS)
"""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workforce_state import atomic_write, read
from workforce_completion import finalize, REQUIRED_CHECKS

_failures = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        _failures.append(msg)


def setUp(root):
    state = root / "state.json"
    art = root / "company" / "departments"
    art.mkdir(parents=True)
    (art / "role.md").write_text("Current fixture role")
    atomic_write(state, {"companyId": "fixture", "companySlug": "fixture", "buildId": "build-1",
                         "interviewComplete": True, "interviewQc": {"status": "pass"},
                         "interviewCompletedAt": "now", "roleLibraryStatus": "done",
                         "sopLibraryStatus": "done", "commsAutomationStatus": "not-applicable",
                         "departments": [{"slug": "engineering", "status": "done"}]})
    return state, art


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state, art = setUp(root)
        progress = art.parent / "build-progress.json"

        print("[1] repeated finalize leaves the state file byte-identical")
        check(finalize(state, {k: 0 for k in REQUIRED_CHECKS}, art) is True, "four zero checks verify")
        first = state.read_bytes()
        finalize(state)
        finalize(state)
        check(state.read_bytes() == first, "state file bytes unchanged after two more finalize calls")
        check(read(state)["stateRevision"] == 1, "stateRevision not bumped by an unchanged call")

        print("[2] a missing progress file is rebuilt with the required defaults")
        progress.unlink()
        results = {k: 0 for k in REQUIRED_CHECKS}
        results["qc"] = 1
        check(finalize(state, results, art) is False, "one failed check is not verified")
        written = json.loads(progress.read_text())
        check(written.get("departments") == [], "departments defaults to an empty list")
        check(isinstance(written.get("documents_total"), int), "documents_total is an int")
        check(isinstance(written.get("documents_complete"), int), "documents_complete is an int")
        check(isinstance(written.get("eta_minutes"), int), "eta_minutes is an int")

        print("[3] an unverified finalize keeps a running build's stage")
        progress.write_text(json.dumps({"stage": "roles", "message": "Generating roles...",
                                        "build_id": read(state)["buildId"],
                                        "updated_at": datetime.now(timezone.utc).isoformat()}))
        check(finalize(state, results, art) is False, "still unverified")
        check(json.loads(progress.read_text()).get("stage") == "roles", "stage stays 'roles'")

    print()
    if _failures:
        print("RESULT: FAIL - %d check(s) failed" % len(_failures))
        return 1
    print("RESULT: PASS - finalize does not churn the state or progress file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
