#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_entry_front_door.py — the documented front door must WORK, end to end (A6).

Runs `bash signature-funnel-entry.sh --run-dir <run>` exactly as the SOP documents it, on a
run dir built by the orchestrator's own valid-run fixture, and requires exit 0 and a signed
PROCESS-CERTIFICATE. The fixture produces every ledger through the same modules the pipeline
judges with; the test asserts the door's outcome, never edits evidence.

Exit 0 = the door certified the run; 1 = the door refused or crashed (its output is printed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL_DIR))
import run_signature_funnel as runner  # noqa: E402

KEY = "a" * 64


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sf-entry-e2e-") as td:
        tmp = Path(td)
        key_file = tmp / "operator.key"
        key_file.write_text(KEY, encoding="utf-8")
        rd = tmp / "run"
        rd.mkdir()
        runner._write_valid_run(rd, KEY)
        env = dict(os.environ)
        env.pop("SF_RUN_NONCE", None)
        env.update({
            "SF_OPERATOR_KEY_FILE": str(key_file),
            "SF_CONTENT_MODEL": "selftest-strong-model",
            "SF_CONTENT_PROVIDER": "selftest",
            "SF_CONTENT_TIER": "content",
        })
        proc = subprocess.run(
            ["bash", str(SKILL_DIR / "signature-funnel-entry.sh"), "--run-dir", str(rd)],
            capture_output=True, text=True, env=env)
        cert = rd / "PROCESS-CERTIFICATE.json"
        if proc.returncode != 0 or not cert.is_file():
            print(proc.stdout[-3000:])
            print(proc.stderr[-3000:], file=sys.stderr)
            print(f"FAIL: the documented front door did not certify a valid run "
                  f"(exit {proc.returncode}, certificate {cert.is_file()})")
            return 1
        doc = json.loads(cert.read_text(encoding="utf-8"))
        print(f"PASS: signature-funnel-entry.sh certified a valid run end to end "
              f"(exit 0, certificate phases={len(doc.get('phases') or [])})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
