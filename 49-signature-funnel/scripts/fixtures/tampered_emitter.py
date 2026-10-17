#!/usr/bin/env python3
"""TEST STUB ONLY. Stands in for a tampered or confused Skill 78 emitter:
it prints a result in the real emitter's exact stdout shape (the
selection-result profile fields, pretty-printed JSON) but with a
request_id that is NOT the --request-id it was invoked with. The wrapper
must refuse it (fail closed), never correct an identity it cannot vouch
for. Used by tests/test_selection_wrapper.py case D only; the real
emitter from main is used in every other case."""
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
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
