#!/usr/bin/env python3
"""emit_page_result.py - Skill 78 page-result emitter (S78-08).

Builds one page result conforming exactly to
schema/selection-result.schema.json (the Skill 78 profile of the packet
page-result contract, doc 02 section 6): identity fields, input hash of
the plan it was built from, artifact paths with sha256 hashes computed at
emit time, author and reviewer sessions, and an honest proof class. A
locally authored checkpoint result is L1 with independent_review false and
reviewer_session null until a real independent review exists; an installed
proof class is emitted only by an authorized installation run, never by
this emitter.

Usage:
  emit_page_result.py <plan.json> --author-session <id> --request-id <id> \
      [--status authored|locally_verified|blocked] [--test-only] \
      [--artifact <path> ...] [--reviewer-session <id>] \
      [--native-bindings-ref <ref>] [--blocker <text> ...]
  emit_page_result.py --self-test
Exit: 0 emitted, 3 fail-closed error.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402

LOCAL_STATUSES = {"authored", "locally_verified", "blocked"}


def emit(plan, *, author_session, request_id, artifact_paths=(), status="locally_verified",
         test_only=False, reviewer_session=None, native_bindings_ref=None, blockers=()):
    if status not in LOCAL_STATUSES:
        raise ValueError(f"Status {status!r} is not emittable by the local emitter; installed/live statuses come from installation runs.")
    outcome = plan.get("outcome")
    if outcome not in ("plan", "declined_single_offer"):
        raise ValueError(f"Plan outcome {outcome!r} is not a page-result outcome.")
    artifacts = []
    for p in artifact_paths:
        path = Path(p)
        artifacts.append({"path": str(p), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    input_hash = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": "1.0",
        "tenant_id": plan.get("tenant_id"),
        "location_id": plan.get("location_id"),
        "launch_id": plan.get("launch_id"),
        "revision": plan.get("revision"),
        "request_id": request_id,
        "input_hash": input_hash,
        "page_id": "selection",
        "outcome": outcome,
        "status": status,
        "artifacts": artifacts,
        "author_session": author_session,
        "reviewer_session": reviewer_session,
        "independent_review": reviewer_session is not None,
        "proof_class": "L1",
        "blockers": list(blockers),
        "native_bindings_ref": native_bindings_ref,
        "test_only": bool(test_only),
    }


def self_test():
    plan = build_plan(SELF_TEST_LAUNCH)
    result = emit(plan, author_session="self-test", request_id="self-test-request", test_only=True)
    assert result["outcome"] == "plan"
    assert result["proof_class"] == "L1"
    assert result["independent_review"] is False and result["reviewer_session"] is None
    assert result["artifacts"] == [] and len(result["input_hash"]) == 64
    reviewed = emit(plan, author_session="author-x", request_id="r2", reviewer_session="reviewer-y")
    assert reviewed["independent_review"] is True
    declined = build_plan(dict(SELF_TEST_LAUNCH, journey_mode="single_simple", offers=SELF_TEST_LAUNCH["offers"][:1]))
    d = emit(declined, author_session="self-test", request_id="r3")
    assert d["outcome"] == "declined_single_offer" and d["tenant_id"] == "TEST-TENANT"
    print("emit_page_result --self-test: PASS (schema-shaped result, L1, review flags honest, decline outcome carried)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args or "--author-session" not in argv or "--request-id" not in argv:
        print("usage: emit_page_result.py <plan.json> --author-session <id> --request-id <id> [--status ...] [--artifact <path> ...]", file=sys.stderr)
        return 3
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    try:
        plan = json.loads(Path(args[0]).read_text())
        result = emit(
            plan,
            author_session=opt("--author-session"),
            request_id=opt("--request-id"),
            artifact_paths=[argv[i + 1] for i, a in enumerate(argv) if a == "--artifact"],
            status=opt("--status", "locally_verified"),
            test_only="--test-only" in argv,
            reviewer_session=opt("--reviewer-session"),
            native_bindings_ref=opt("--native-bindings-ref"),
            blockers=[argv[i + 1] for i, a in enumerate(argv) if a == "--blocker"],
        )
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
