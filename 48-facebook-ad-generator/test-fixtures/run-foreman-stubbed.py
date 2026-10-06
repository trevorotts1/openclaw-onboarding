#!/usr/bin/env python3
"""Run ad_director.py --phase PH on a fixture run dir with a SYNTHETIC key and a stubbed
live KIE balance (no network, no real credential). The fixtures are PAID runs, and a paid
run with no real key now aborts at Phase-0 (exit 4), so CI exercises the dependency and
receipt gates through this wrapper. The keyless abort itself is proven in
scripts/test_ad_recovery.py (F).

Usage: python3 run-foreman-stubbed.py RUN_DIR PHASE_ID
"""
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ad_build_check as abc  # noqa: E402
import ad_director as ad      # noqa: E402

os.environ["KIE_API_KEY"] = "".join(
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"[(i * 37 + 11) % 57]
    for i in range(32))
abc._fetch_kie_balance = lambda *a, **k: 1.0e9
sys.argv = ["ad_director.py", "--run-dir", sys.argv[1], "--phase", sys.argv[2]]
ad.main()
