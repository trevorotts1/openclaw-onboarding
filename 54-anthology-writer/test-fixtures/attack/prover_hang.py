#!/usr/bin/env python3
"""prover_hang.py — adversarial prover fixture that hangs forever (sleep 9999s).
Used by --prover-self-test-hang to verify the AF-AW-PROVER-TIMEOUT path is live."""
import time
time.sleep(9999)
