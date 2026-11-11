"""STAND-IN for Skill 50's ``50-email-engine/tools/validate_delivery.py``, for Skill 83's tests only.

Skill 83 re-runs Skill 50's validator by path (``validate_delivery.py --check <receipt.json>``) before it
seals an email unit. The real validator is Skill 50's own tool; these tests prove Skill 83's side of the
contract, so they run the launcher against this stand-in, which keeps the contract's observable behaviour:

* exit 0 only when the receipt names the Skill 50 email contract, every artifact still hashes to what the
  receipt says (paths resolve against the receipt file's own folder) and ``certificate_sha256`` is the
  certificate for exactly those artifacts;
* any other receipt, or any drift in an artifact byte or name, exits non-zero.

It is run by path under ``python3 -I`` like the real one, so it imports nothing from the test tree. A test
that needs a delivery the stand-in accepts calls ``certificate`` for the artifact list it staged.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

CONTRACT = "skill50.email-delivery.v1"


def certificate(artifacts) -> str:
    """The certificate for a list of ``{"path", "sha256", ...}``: it moves if any name or hash moves."""
    body = json.dumps(sorted((a["path"], a["sha256"]) for a in artifacts), separators=(",", ":"))
    return hashlib.sha256(("stand-in-certificate:" + body).encode("utf-8")).hexdigest()


def check(receipt_path: str) -> int:
    path = Path(receipt_path).resolve()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        lane = doc["lane_validation"]
        artifacts = doc["artifacts"]
        if lane.get("contract") != CONTRACT or lane.get("state") != "passed" or not artifacts:
            return 1
        for art in artifacts:
            target = path.parent / art["path"]
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != art["sha256"]:
                return 1
        return 0 if lane.get("certificate_sha256") == certificate(artifacts) else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        raise SystemExit(check(sys.argv[2]))
    sys.stderr.write("usage: lane83_stand_in_validate_delivery.py --check <receipt.json>\n")
    raise SystemExit(2)
