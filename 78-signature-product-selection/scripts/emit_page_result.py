#!/usr/bin/env python3
"""emit_page_result.py - Skill 78 page-result emitter (S78-08, Path A follow-on).

Follow-on candidate after PR #2158 landed (batch train #2220,
2026-10-17T15:32:02Z). Implements the native Path A fix committed to S49
in the S78 reply to CR-S49-002 (the S49 Path B wrapper retires when this
candidate lands):

  1. The CLI takes an output file path (--output) and writes the bare
     JSON result file at that path. It no longer only prints to stdout.
  2. page_id is echoed from the request, never the literal "selection".
  3. input_hash is echoed from the request, never computed as the
     SHA-256 of the serialized selection plan.
  4. The emitted page-result document carries NO outcome field: it is
     exactly the 17-field packet page-result 1.0 document
     (schema/page-result.schema.json, additionalProperties: false).
     The plan outcome remains meaningful in Skill 78's own
     selection-result profile (schema/selection-result.schema.json);
     emit_selection_result() returns that profile document, which is
     the page result plus the outcome field.

The request echo source is either a request document passed to emit()
(the `request` argument, or a --request <file> on the CLI) or explicit
page_id / input_hash values (--page-id / --input-hash on the CLI). If
neither source supplies page_id and input_hash, the emitter fails
closed: it never falls back to the old literal or plan hash.

A locally authored checkpoint result is L1 with independent_review
false and reviewer_session null until a real independent review exists;
an installed proof class is emitted only by an authorized installation
run, never by this emitter.

--image-run-dir <dir> (the --run-dir run_image_stages.py drew into) makes every file of that run
the page's artifacts, sha256 each, so a multiple-options launch no longer returns a page result with
zero artifacts (STR-03). The run's copy/internal-manuscript.md is gated first with
validate_selection_content.validate_manuscript against the plan; a missing manuscript, an empty run
dir or a violation is a fail-closed error and no result file is written. Only the page's own
pipeline outputs are listed: the runtime and session scripts (selection_runtime.py,
selection_session_store.py, selection_session.py) have no host yet (PRD-05) and are not part of
what this result claims.

Usage:
  emit_page_result.py <plan.json> --output <result.json> \
      --author-session <id> --request <request.json> \
      [--status authored|locally_verified|blocked] [--review <record.json> --review-ledger <ledger.json>] [--test-only] \
      [--artifact <path> ...] [--image-run-dir <dir>] [--reviewer-session <id>] \
      [--native-bindings-ref <ref>] [--blocker <text> ...]
  emit_page_result.py <plan.json> --output <result.json> \
      --author-session <id> --request-id <id> \
      --page-id <id> --input-hash <hash> [...]
  emit_page_result.py --self-test
Exit: 0 emitted, 3 fail-closed error.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from selection_core import Violation  # noqa: E402
from validate_selection_content import validate_manuscript  # noqa: E402

LOCAL_STATUSES = {"authored", "locally_verified", "blocked"}
PAGE_RESULT_FIELDS = (
    "schema_version", "tenant_id", "location_id", "launch_id", "revision",
    "request_id", "input_hash", "page_id", "status", "artifacts",
    "author_session", "reviewer_session", "independent_review",
    "proof_class", "blockers", "native_bindings_ref", "test_only",
)


def _echoed(request, explicit, field):
    if explicit is not None:
        return explicit
    if request is not None:
        return request.get(field)
    return None


def run_dir_artifacts(plan, run_dir):
    """Every file the image run wrote, after the run's manuscript passes the content gate."""
    run_dir = Path(run_dir)
    manuscript = run_dir / "copy" / "internal-manuscript.md"
    if not manuscript.is_file():
        raise ValueError(f"image run dir {run_dir} has no copy/internal-manuscript.md; the page copy cannot be checked")
    try:
        validate_manuscript(manuscript.read_text(encoding="utf-8"), plan)
    except Violation as exc:
        raise ValueError(f"[{exc.code}] {exc.message}")
    files = sorted(p for p in run_dir.rglob("*") if p.is_file() and not p.is_symlink())
    if not files:
        raise ValueError(f"image run dir {run_dir} holds no output files")
    return files


def emit(plan, *, author_session, request_id=None, page_id=None, input_hash=None,
         request=None, artifact_paths=(), status="authored",
         test_only=False, reviewer_session=None, native_bindings_ref=None, blockers=(),
         image_run_dir=None):
    if status not in LOCAL_STATUSES:
        raise ValueError(f"Status {status!r} is not emittable by the local emitter; installed/live statuses come from installation runs.")
    outcome = plan.get("outcome")
    if outcome not in ("plan", "declined_single_offer"):
        raise ValueError(f"Plan outcome {outcome!r} is not a page-result outcome.")
    request_id = _echoed(request, request_id, "request_id")
    page_id = _echoed(request, page_id, "page_id")
    input_hash = _echoed(request, input_hash, "input_hash")
    if not request_id:
        raise ValueError("request_id is required (pass --request-id or a request document).")
    if not page_id:
        raise ValueError("page_id must be echoed from the request (pass --page-id or a request document); the emitter does not invent one.")
    if not input_hash:
        raise ValueError("input_hash must be echoed from the request (pass --input-hash or a request document); the emitter does not hash the plan in its place.")
    if request is not None and "test_only" in request:
        test_only = bool(request["test_only"])
    if status == "locally_verified" and reviewer_session is None:
        raise ValueError("status locally_verified needs --reviewer-session and a valid review record; the default is authored.")
    if reviewer_session is not None and reviewer_session == author_session:
        raise ValueError("reviewer_session equals author_session; an independent review needs a different session.")
    artifact_paths = list(artifact_paths)
    if image_run_dir is not None:
        if outcome != "plan":
            raise ValueError("a declined single-offer plan has no order page images to list.")
        artifact_paths += run_dir_artifacts(plan, image_run_dir)
    artifacts = []
    for p in artifact_paths:
        path = Path(p)
        artifacts.append({"path": str(p), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {
        "schema_version": "1.0",
        "tenant_id": plan.get("tenant_id"),
        "location_id": plan.get("location_id"),
        "launch_id": plan.get("launch_id"),
        "revision": plan.get("revision"),
        "request_id": request_id,
        "input_hash": input_hash,
        "page_id": page_id,
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


def emit_selection_result(plan, **kwargs):
    """Skill 78's own selection-result profile of the page result.

    Same document emit() returns, plus the plan outcome, which belongs
    to this profile (schema/selection-result.schema.json) and not to
    the packet page-result 1.0 document.
    """
    result = emit(plan, **kwargs)
    profile = {}
    for key, value in result.items():
        profile[key] = value
        if key == "page_id":
            profile["outcome"] = plan.get("outcome")
    return profile


def check_review(result, record, ledger):
    """A reviewer_session / locally_verified claim needs a record the shared validator accepts."""
    for parent in Path(__file__).resolve().parents:
        path = parent / "shared-utils" / "signature_launch_contract" / "review_record.py"
        if path.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("review_record", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fails = mod.validate_review_record(
                record, ledger=ledger, author_session=result["author_session"],
                artifacts=result["artifacts"], request_id=result["request_id"])
            if fails:
                raise ValueError("review record refused: " + "; ".join(fails))
            if record.get("reviewer_session") != result["reviewer_session"]:
                raise ValueError("review record reviewer_session differs from --reviewer-session")
            return
    raise ValueError("review_record validator not found; cannot accept a review")


def self_test():
    request = {
        "request_id": "self-test-request",
        "page_id": "SELF-TEST-SELECTION-PAGE",
        "input_hash": "a" * 64,
        "test_only": True,
    }
    plan = build_plan(SELF_TEST_LAUNCH)
    result = emit(plan, author_session="self-test", request=request)
    assert result["page_id"] == "SELF-TEST-SELECTION-PAGE", result["page_id"]
    assert result["input_hash"] == "a" * 64
    assert result["request_id"] == "self-test-request"
    assert "outcome" not in result, "page-result 1.0 document must not carry outcome"
    assert tuple(result.keys()) == PAGE_RESULT_FIELDS, tuple(result.keys())
    assert result["proof_class"] == "L1"
    assert result["independent_review"] is False and result["reviewer_session"] is None
    assert result["artifacts"] == []
    profile = emit_selection_result(plan, author_session="self-test", request=request)
    assert profile["outcome"] == "plan"
    assert profile["page_id"] == "SELF-TEST-SELECTION-PAGE" and profile["input_hash"] == "a" * 64
    explicit = emit(plan, author_session="author-x", request_id="r2",
                    page_id="EXPLICIT-PAGE", input_hash="b" * 64, reviewer_session="reviewer-y")
    assert explicit["independent_review"] is True
    assert explicit["page_id"] == "EXPLICIT-PAGE" and explicit["input_hash"] == "b" * 64
    try:
        emit(plan, author_session="self-test", request_id="r-no-echo")
    except ValueError as e:
        assert "page_id" in str(e), e
    else:
        raise AssertionError("emit without a request echo source was not refused")
    declined = build_plan(dict(SELF_TEST_LAUNCH, journey_mode="single_simple", offers=SELF_TEST_LAUNCH["offers"][:1]))
    d = emit(declined, author_session="self-test", request=request)
    assert "outcome" not in d and d["tenant_id"] == "TEST-TENANT"
    d_profile = emit_selection_result(declined, author_session="self-test", request=request)
    assert d_profile["outcome"] == "declined_single_offer"
    import tempfile
    from emit_section_manuscript import write as write_manuscript
    with tempfile.TemporaryDirectory() as td:
        write_manuscript_plan = Path(td) / "plan.json"
        write_manuscript_plan.write_text(json.dumps(plan))
        write_manuscript(write_manuscript_plan, Path(td) / "run")
        listed = emit(plan, author_session="self-test", request=request, image_run_dir=Path(td) / "run")["artifacts"]
        assert {Path(a["path"]).name for a in listed} == {"internal-manuscript.md", "copy-manifest.json"}, listed
        try:
            emit(plan, author_session="self-test", request=request, image_run_dir=Path(td) / "no-such-run")
        except ValueError:
            pass
        else:
            raise AssertionError("an image run dir with no manuscript was accepted")
    print("emit_page_result --self-test: PASS (page-result 1.0 shape, page_id/input_hash echoed from request, no outcome in page result, outcome carried in selection-result profile, L1, review flags honest, missing echo source refused)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]

    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    output = opt("--output") or opt("--out")
    if not args or "--author-session" not in argv or output is None:
        print("usage: emit_page_result.py <plan.json> --output <result.json> --author-session <id> (--request <request.json> | --request-id <id> --page-id <id> --input-hash <hash>) [--status ...] [--artifact <path> ...] [--image-run-dir <dir>]", file=sys.stderr)
        return 3
    try:
        plan = json.loads(Path(args[0]).read_text())
        request = None
        if "--request" in argv:
            request = json.loads(Path(opt("--request")).read_text())
        result = emit(
            plan,
            author_session=opt("--author-session"),
            request_id=opt("--request-id"),
            page_id=opt("--page-id"),
            input_hash=opt("--input-hash"),
            request=request,
            artifact_paths=[argv[i + 1] for i, a in enumerate(argv) if a == "--artifact"],
            image_run_dir=opt("--image-run-dir"),
            status=opt("--status", "authored"),
            test_only="--test-only" in argv,
            reviewer_session=opt("--reviewer-session"),
            native_bindings_ref=opt("--native-bindings-ref"),
            blockers=[argv[i + 1] for i, a in enumerate(argv) if a == "--blocker"],
        )
        if result["reviewer_session"] is not None or result["status"] == "locally_verified":
            if "--review" not in argv:
                raise ValueError("--reviewer-session / locally_verified need --review <record.json> (--review-ledger <ledger.json>)")
            ledger = json.loads(Path(opt("--review-ledger")).read_text()) if "--review-ledger" in argv else None
            check_review(result, json.loads(Path(opt("--review")).read_text()), ledger)
        out_path = Path(output)
        if out_path.parent and str(out_path.parent) not in ("", "."):
            out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n")
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
