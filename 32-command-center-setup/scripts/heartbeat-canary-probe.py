#!/usr/bin/env python3
"""Skill 32 — DEPRECATED compatibility shim (heartbeat-canary-probe.py)

This file has moved. As of the D20 rename (operator-box-proof vocabulary,
2026-07-16), the live script is `heartbeat-embedding-probe.py` in this same
directory. This shim execs the new file directly, in the SAME process
(`os.execv`), so any existing cron registration, doc example, or muscle-memory
invocation of this old path keeps working, unchanged, for ONE release.

Update your invocation to `heartbeat-embedding-probe.py`; this shim is
scheduled for removal in the release after next.
"""
from __future__ import annotations

import os
import sys

_NEW_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "heartbeat-embedding-probe.py"
)

if __name__ == "__main__":
    if not os.path.isfile(_NEW_SCRIPT):
        print(
            f"heartbeat-canary-probe.py (shim): target {_NEW_SCRIPT} not found "
            "— the shim and the live script have drifted apart.",
            file=sys.stderr,
        )
        sys.exit(3)
    os.execv(sys.executable, [sys.executable, _NEW_SCRIPT, *sys.argv[1:]])
