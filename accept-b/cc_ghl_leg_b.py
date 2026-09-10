#!/usr/bin/env python3
"""PRES-055 leg B CC/GHL leg (W6 WF23, SOURCE leg helper).

CC leg (real, offline, source-tree):
- Verifies the EXACT released carriers read-only: wheel / sdist / plugin
  sha256 vs ARTIFACT-RECEIPT.json (3/3 MATCH expected, same digests as leg A
  carriers per packet: no re-download, no mutation of the artifact dir).
- Runs the static Command Center TaskStatus contract test
  (test_cc_contract.py) from the source tree. Label: SOURCE-RUN.

GHL leg (honest NOT-VERIFIED):
- No scoped live GHL test location, no live credentials, no network calls in
  this packet. Refuses to fabricate IDs. Synthetic fixture constants come
  from checkout_form_builder.py (pres025 leg) and are labeled synthetic.

Connected CC/GHL acceptance against live resources stays NOT-VERIFIED and
is recorded as such -- never a silent pass.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

PACKET = Path("/Users/blackceomacmini/Downloads/September eighth presentation "
              "department fixes")
ARTDIR = (PACKET / "run" / "artifacts" / "pres-package" /
          "build-4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391")
WORKTREE = HERE.parent
SCRIPTS = (WORKTREE / "23-ai-workforce-blueprint" / "templates" /
           "role-library" / "presentations" / "scripts")

EXPECTED = {
    "presentation_department-0.1.0-py3-none-any.whl": (
        "pkg/dist/presentation_department-0.1.0-py3-none-any.whl",
        "d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206",
        6419813),
    "presentation_department-0.1.0.tar.gz": (
        "pkg/dist/presentation_department-0.1.0.tar.gz",
        "2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4",
        10037881),
    "presentation-department-skill-plugin-0.1.0.zip": (
        "presentation-department-skill-plugin-0.1.0.zip",
        "9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487",
        4518),
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def carrier_check() -> dict:
    receipt_path = ARTDIR / "ARTIFACT-RECEIPT.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    rows = []
    for name, (rel, want_sha, want_bytes) in EXPECTED.items():
        fp = ARTDIR / rel
        got_sha = _sha256(fp)
        got_bytes = fp.stat().st_size
        receipt_sha = receipt["artifacts"][name]["sha256"]
        rows.append({
            "carrier": name, "path": rel,
            "bytes": got_bytes, "bytes_match": got_bytes == want_bytes,
            "sha256": got_sha,
            "match_expected": got_sha == want_sha,
            "match_receipt": got_sha == receipt_sha,
        })
    manifest = receipt.get("manifest", {})
    return {
        "receipt": str(receipt_path),
        "carriers": rows,
        "all_match": all(r["match_expected"] and r["match_receipt"]
                         and r["bytes_match"] for r in rows),
        "manifest": {"version": manifest.get("version"),
                     "phases": manifest.get("phases"),
                     "sha256": manifest.get("sha256"),
                     "staged_content_sha256": receipt.get("source", {}).get(
                         "staged_content_sha256")},
        "wrote_nothing": True,
    }


def cc_contract_test() -> dict:
    t = SCRIPTS / "test_cc_contract.py"
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", str(t), "-q"],
                           capture_output=True, text=True, timeout=300,
                           cwd=str(SCRIPTS))
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ran": True, "returncode": r.returncode,
            "status": ("SOURCE-RUN-PASS" if r.returncode == 0
                       else "SOURCE-RUN-FAIL"),
            "stdout_tail": (r.stdout or "")[-2500:],
            "stderr_tail": (r.stderr or "")[-1500:]}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    carriers = carrier_check()
    cc = cc_contract_test()
    receipt = {
        "schema": "pres055-b/cc-ghl-v1",
        "generated_at": _utcnow(),
        "exact_released_artifact": carriers,
        "cc_contract_static": cc,
        "connected_cc_acceptance": {
            "status": "NOT-VERIFIED",
            "reason": ("no scoped live Command Center designated in this "
                       "packet; zero live calls made, zero receipts forged"),
        },
        "connected_ghl_acceptance": {
            "status": "NOT-VERIFIED",
            "reason": ("no scoped live GHL test location / credentials in "
                       "this packet; zero live calls made; synthetic fixture "
                       "proof runs in pres025 leg and is labeled synthetic"),
        },
        "label": ("Carriers verified read-only vs ARTIFACT-RECEIPT.json; CC "
                  "contract is a static SOURCE-RUN; connected legs honestly "
                  "NOT-VERIFIED."),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out),
                      "carriers_all_match": carriers["all_match"],
                      "cc": cc.get("status")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
