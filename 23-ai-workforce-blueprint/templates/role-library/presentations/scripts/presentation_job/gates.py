from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES
WARN_ONLY_GATES = ("qc", "ocr_readback")
QC_PASS_THRESHOLD = 8.5

assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES)), 'overlap: ' + str(set(GATE_KEYS) & set(NON_WAIVABLE_GATES))

