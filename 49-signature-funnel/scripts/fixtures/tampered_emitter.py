#!/usr/bin/env python3
"""TEST STUB ONLY. Stands in for a tampered or confused Skill 78 emitter:
it writes a result in the real emitter's exact output shape (the
selection-result profile fields, delivered at the --output path the
real emitter's current CLI uses) but with a request_id that is NOT the
request it was invoked with. The wrapper must refuse it (fail closed),
never correct an identity it cannot vouch for. Used by
tests/test_selection_wrapper.py case D only; the real emitter from main
is used in every other case."""
import json
import sys
from pathlib import Path


def main(argv):
    plan = json.loads(Path(argv[1]).read_text())
    result = {
        "schema_version": "1.0",
        "tenant_id": plan.get("tenant_id"),
        "location_id": plan.get("location_id"),
        "launch_id": plan.get("launch_id"),
        "revision": plan.get("revision"),
        "request_id": "FORGED-REQUEST-ID",
        "input_hash": "0" * 64,
        "page_id": "selection",
        "outcome": plan.get("outcome"),
        "status": "locally_verified",
        "artifacts": [],
        "author_session": "tampered-stub",
        "reviewer_session": None,
        "independent_review": False,
        "proof_class": "L1",
        "blockers": [],
        "native_bindings_ref": None,
        "test_only": True,
    }
    text = json.dumps(result, indent=2)
    if "--output" in argv:
        out = Path(argv[argv.index("--output") + 1])
        if out.parent and str(out.parent) not in ("", "."):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
