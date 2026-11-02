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

Skill 56 ships the older copy without the transport binding (binding_problems / write_bound_receipt /
store_problems); Skill 71's stage_executor loads this Skill 49 copy. stdlib only.
Exit 0 = ok, 2 = violation, 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
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


# Every top-level key kie_live_adapter.py result() can emit. Anything else is not an adapter result.
ADAPTER_KEYS = frozenset({
    "provider", "adapter", "adapter_mode", "backend", "model_id", "capability", "schema_source",
    "schema_fetched_at", "task_id", "state", "result_urls", "saved_paths", "credits_consumed",
    "warnings", "fallback_used", "raw_family", "error", "data", "binding"})
ADAPTER_STATES = frozenset({"validated", "queued", "running", "success", "fail", "skipped"})


def adapter_file_problems(obj: Any, text: str) -> List[str]:
    """Problems that disqualify a file from the bypass-scan allow-list (any state, any mode)."""
    problems: List[str] = []
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    if obj.get("adapter") != ADAPTER or obj.get("backend") != "native-live" or obj.get("provider") != "kie":
        problems.append("not a Skill 74 adapter result (adapter/backend/provider mismatch)")
    extra = sorted(set(obj) - ADAPTER_KEYS)
    if extra:
        problems.append(f"unknown top-level key(s) {extra[:3]}: not an adapter result")
    if obj.get("adapter_mode") not in ("active", "shadow", "off"):
        problems.append("adapter_mode is not active, shadow or off")
    if obj.get("state") not in ADAPTER_STATES:
        problems.append(f"state {obj.get('state')!r} is not an adapter state")
    if not _real(obj.get("task_id")):
        problems.append(f"task_id {obj.get('task_id')!r} is missing or a placeholder")
    if not (isinstance(obj.get("saved_paths"), list) or isinstance(obj.get("result_urls"), list)):
        problems.append("neither saved_paths nor result_urls is a list")
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


# --- transport binding: the receipt, not the agent, ties one provider task to one set of saved bytes.
_SHA = re.compile(r"[0-9a-f]{64}")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _sha_of(run_dir: Path, rel: Any) -> Optional[str]:
    root = Path(run_dir).resolve()
    f = (root / str(rel)).resolve()
    if root not in f.parents or not f.is_file():
        return None
    return hashlib.sha256(f.read_bytes()).hexdigest()


def binding_problems(obj: Any, run_dir: Optional[Path] = None) -> List[str]:
    """Problems with obj["binding"] = {task_id, sha256, file, credits_before, credits_after}.
    With run_dir the saved bytes are re-hashed, so a swapped PNG or an invented task id fails."""
    b = obj.get("binding") if isinstance(obj, dict) else None
    if not isinstance(b, dict):
        return ["no binding block {task_id, sha256, file, credits_before, credits_after}"]
    problems: List[str] = []
    if not _real(b.get("task_id")) or b.get("task_id") != obj.get("task_id"):
        problems.append("binding.task_id does not match the result's task_id")
    if not (isinstance(b.get("sha256"), str) and _SHA.fullmatch(b["sha256"])):
        problems.append("binding.sha256 is not a 64-character hex digest")
    before, after = b.get("credits_before"), b.get("credits_after")
    if not (_number(before) and _number(after)):
        problems.append("binding.credits_before and credits_after must both be numbers")
    elif after > before:
        problems.append(f"binding.credits_after {after} is above credits_before {before}")
    if run_dir is not None and not problems:
        pairs = [("file", "sha256")] + ([("delivered_file", "delivered_sha256")] if b.get("delivered_file") else [])
        for rel_key, sha_key in pairs:
            if _sha_of(run_dir, b.get(rel_key)) != b.get(sha_key):
                problems.append(f"binding.{rel_key} {b.get(rel_key)!r} is missing or does not hash to "
                                f"binding.{sha_key}")
    return problems


def write_bound_receipt(run_dir: Path, result: Dict[str, Any], file_rel: str,
                        credits_before: Any, credits_after: Any) -> Path:
    """Store one dispatched adapter result plus its binding under receipts/kie74/<task_id>.json.
    Called by the code that ran the transport (stage_executor.py), never by an agent's hand."""
    obj = dict(result)
    obj["binding"] = {"task_id": obj.get("task_id"), "file": file_rel,
                      "sha256": _sha_of(run_dir, file_rel) or "",
                      "credits_before": credits_before, "credits_after": credits_after}
    text = json.dumps(obj, sort_keys=True)
    problems = dispatch_problems(obj, text) or binding_problems(obj, run_dir)
    if problems:
        raise ValueError("; ".join(problems))
    safe = re.sub(r"[^A-Za-z0-9_-]", "", obj["task_id"].strip())[:80] or "task"
    dest = Path(run_dir) / RECEIPT_SUBDIR / f"{safe}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest


def rebind_derived(receipt: Path, run_dir: Path, raw_rel: str, delivered_rel: str) -> None:
    """A circle slot is masked in place after delivery: keep the proven provider bytes (raw_rel) as the
    bound file and record the masked delivered file beside it."""
    obj = json.loads(Path(receipt).read_text(encoding="utf-8"))
    b = obj["binding"]
    if _sha_of(run_dir, raw_rel) != b["sha256"]:
        raise ValueError(f"{raw_rel} is not the bytes the provider returned")
    b.update(file=raw_rel, delivered_file=delivered_rel, delivered_sha256=_sha_of(run_dir, delivered_rel))
    Path(receipt).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def store_problems(run_dir: Path, expect_files: Sequence[str] = ()) -> List[str]:
    """The production gate: the receipt store must exist, every receipt must be a dispatched adapter
    result with a binding whose bytes re-hash, and every file in expect_files must be bound."""
    files = sorted((Path(run_dir) / RECEIPT_SUBDIR).glob("*.json")) if (Path(run_dir) / RECEIPT_SUBDIR).is_dir() else []
    if not files:
        return [f"receipt store {RECEIPT_SUBDIR} is absent or empty: nothing binds any image to a provider task"]
    problems: List[str] = []
    covered = set()
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            obj = json.loads(text)
        except (OSError, ValueError) as exc:
            problems.append(f"{f.name}: unreadable or not JSON ({exc})")
            continue
        why = dispatch_problems(obj, text) or binding_problems(obj, run_dir)
        problems += [f"{f.name}: {w}" for w in why]
        if not why:
            covered |= {obj["binding"].get("file"), obj["binding"].get("delivered_file")}
    problems += [f"{rel}: no receipt binds this image" for rel in expect_files if rel not in covered]
    return problems


def check_file(path: Path) -> Tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8")
        obj = json.loads(text)
    except (OSError, ValueError) as exc:
        return False, f"unreadable or not JSON ({exc})"
    problems = adapter_file_problems(obj, text)
    if not problems and "binding" in obj:  # a bound receipt must still hash; unbound legacy files stay allowed here
        problems = binding_problems(obj, path.resolve().parents[2] if len(path.resolve().parents) > 2 else None)
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

    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / "a.png").write_bytes(b"png-bytes")
        res = json.loads(result())
        say(bool(store_problems(rd)), "store_problems refuses an absent receipt store")
        write_bound_receipt(rd, res, "a.png", 10, 6)
        say(not store_problems(rd, ["a.png"]), "bound receipt accepted and covers its file")
        (rd / "a.png").write_bytes(b"swapped")
        say(bool(store_problems(rd)), "store_problems refuses a PNG whose hash differs from the receipt")
        try:
            write_bound_receipt(rd, res, "a.png", 5, 9)
            say(False, "credits_after above credits_before must be refused")
        except ValueError:
            say(True, "credits_after above credits_before refused")

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
