#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kie74_receipt.py - turn one Skill 74 result into run evidence.

Skill 74 (74-kie-live-adapter) is the single approved KIE transport. Skill 66 (images) or
Skill 67 (video) picks the model; nothing in a funnel run calls KIE any other way. After each
successful `kie_live_adapter.py run ... --mode active` (or `wait` + `save`), pass the adapter's
JSON result here:

    python3 scripts/kie74_receipt.py --run-dir RUN --phase P3-IMAGES --result result.json [--covers KEY ...]

What it does, fail-closed:
  1. Refuses a result that did not come from the adapter in active mode, did not succeed, has no
     real task id or saved file, or leaks a bearer token.
  2. Writes <RUN>/receipts/kie74/<task_id>.json. The canonical entry shell's bypass scan allows
     exactly these files (it re-checks each with `--check`), so the adapter's own receipts never trip
     AF-FUN-CANONICAL-BYPASS / AF-SP56-CANONICAL-BYPASS, while a hand-rolled createTask still does.
  3. Appends one provider receipt to <RUN>/delegation_receipts.jsonl through
     delegation_receipt.record(); `recorded_by` resolves to this module, which is not a certified
     subject, so the delegation requirer accepts it.

Skill 49 and Skill 56 ship an identical copy of this file. stdlib only.
Exit 0 = ok, 2 = violation, 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegation_receipt  # noqa: E402

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3

ADAPTER = "74-kie-live-adapter"
RECEIPT_SUBDIR = Path("receipts") / "kie74"
BAD_IDS = frozenset(delegation_receipt.PLACEHOLDER_IDS)
_LEAK = re.compile(r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]{8,}")


def _real(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in BAD_IDS


def adapter_file_problems(obj: Any, text: str) -> List[str]:
    """Problems that disqualify a file from the bypass-scan allow-list (any state, any mode)."""
    problems: List[str] = []
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    if obj.get("adapter") != ADAPTER or obj.get("backend") != "native-live" or obj.get("provider") != "kie":
        problems.append("not a Skill 74 adapter result (adapter/backend/provider mismatch)")
    if _LEAK.search(text):
        problems.append("contains an unredacted bearer token")
    return problems


def dispatch_problems(obj: Any, text: str) -> List[str]:
    """Problems that disqualify a result from becoming delegation evidence."""
    problems = adapter_file_problems(obj, text)
    if problems:
        return problems
    if obj.get("adapter_mode") != "active":
        problems.append(f"adapter_mode is {obj.get('adapter_mode')!r}, not 'active' (shadow never dispatches)")
    if obj.get("state") != "success":
        problems.append(f"state is {obj.get('state')!r}, not 'success'")
    if obj.get("fallback_used"):
        problems.append("fallback_used is true: the adapter did not dispatch")
    if not _real(obj.get("task_id")):
        problems.append(f"task_id {obj.get('task_id')!r} is missing or a placeholder")
    if not _real(obj.get("model_id")):
        problems.append("model_id is missing")
    saved = obj.get("saved_paths")
    if not (isinstance(saved, list) and [p for p in saved if isinstance(p, str) and p.strip()]):
        problems.append("saved_paths is empty: the result was not saved immediately (links expire)")
    return problems


def check_file(path: Path) -> Tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8")
        obj = json.loads(text)
    except (OSError, ValueError) as exc:
        return False, f"unreadable or not JSON ({exc})"
    problems = adapter_file_problems(obj, text)
    return (not problems), "; ".join(problems)


def record_result(run_dir: Path, phase: str, result_text: str,
                  covers: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Validate one adapter result, store it, and append the delegation receipt."""
    try:
        obj = json.loads(result_text)
    except ValueError as exc:
        raise ValueError(f"result is not JSON ({exc})")
    problems = dispatch_problems(obj, result_text)
    if problems:
        raise ValueError("; ".join(problems))
    tid = obj["task_id"].strip()
    safe = re.sub(r"[^A-Za-z0-9_-]", "", tid)[:80] or "task"
    dest = Path(run_dir) / RECEIPT_SUBDIR / f"{safe}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return delegation_receipt.record(
        Path(run_dir), phase=phase, provider="kie", operation="createTask",
        provider_response_id=tid, http_status=200, remote_id=tid,
        covers=list(covers) if covers else [tid],
        extra={"transport": ADAPTER, "adapter_mode": "active", "model_id": obj["model_id"],
               "saved_files": len(obj["saved_paths"])})


def _self_test() -> int:
    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    def result(**over: Any) -> str:
        r = {"provider": "kie", "adapter": ADAPTER, "adapter_mode": "active", "backend": "native-live",
             "model_id": "model-from-skill-66", "task_id": "task-abc-001", "state": "success",
             "result_urls": ["https://example.invalid/a.png"], "saved_paths": ["/run/images/a.png"],
             "fallback_used": False, "warnings": [], "data": {"path": "/api/v1/jobs/createTask"}}
        r.update(over)
        return json.dumps(r, indent=2)

    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        entry = record_result(rd, "P3-IMAGES", result())
        say(entry["recorded_by"] == "kie74_receipt", f"receipt is stamped recorded_by={entry['recorded_by']!r}")
        good, detail = delegation_receipt.require(rd, "P3-IMAGES", must_cover=["task-abc-001"])
        say(good, f"delegation requirer accepts the adapter receipt ({detail})")
        say((rd / RECEIPT_SUBDIR / "task-abc-001.json").is_file(), "adapter result stored under receipts/kie74/")
        say(check_file(rd / RECEIPT_SUBDIR / "task-abc-001.json")[0], "--check accepts the stored adapter result")

    bad = {
        "shadow mode": result(adapter_mode="shadow"),
        "skipped state": result(state="skipped", fallback_used=True),
        "placeholder task id": result(task_id="placeholder"),
        "no saved file": result(saved_paths=[]),
        "other adapter": result(adapter="hand-rolled"),
        "leaked token": result(warnings=["Bearer abcdefghijklmnop"]),
    }
    for label, text in bad.items():
        with tempfile.TemporaryDirectory() as td:
            try:
                record_result(Path(td), "P3-IMAGES", text)
                say(False, f"{label} must be refused")
            except ValueError as exc:
                say(not (Path(td) / "delegation_receipts.jsonl").exists(), f"{label} refused ({str(exc)[:50]})")

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "forged.json"
        f.write_text('{"note": "requests.post(api.kie.ai createTask)"}', encoding="utf-8")
        say(not check_file(f)[0], "--check rejects a non-adapter file")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Record one Skill 74 result as run evidence "
                                             "(exit 0 ok, 2 violation, 3 usage).")
    ap.add_argument("--run-dir")
    ap.add_argument("--phase", help="delegated phase id, for example P3-IMAGES (Skill 49) or P2-IMAGES (Skill 56)")
    ap.add_argument("--result", help="adapter result JSON file, or - for stdin")
    ap.add_argument("--covers", nargs="*", default=None, help="ledger keys this call covers (default: the task id)")
    ap.add_argument("--check", metavar="FILE", help="exit 0 only if FILE is a Skill 74 adapter result")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return _self_test()
    if a.check:
        good, why = check_file(Path(a.check))
        if not good:
            print(f"FAIL: {a.check}: {why}")
        return EXIT_OK if good else EXIT_VIOLATION
    if not (a.run_dir and a.phase and a.result):
        print("USAGE ERROR: pass --run-dir, --phase and --result (or --check FILE, or --self-test).")
        return EXIT_FAILCLOSED
    try:
        text = sys.stdin.read() if a.result == "-" else Path(a.result).read_text(encoding="utf-8")
        entry = record_result(Path(a.run_dir).expanduser().resolve(), a.phase, text, a.covers)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    print(json.dumps(entry, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
