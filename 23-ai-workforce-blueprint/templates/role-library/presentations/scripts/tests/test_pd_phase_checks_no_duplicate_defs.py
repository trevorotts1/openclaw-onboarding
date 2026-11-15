#!/usr/bin/env python3
"""No duplicate top-level defs in phase_verifiers.py.

A second ``def`` of the same name silently REPLACES the first at import, so an
edit to the first copy is dead code and the module runs something else. That
happened on main to four SP verifiers; PD-209's content-proving step checks
were only live once the duplicates were gone.
"""
import ast
import collections
from pathlib import Path

PV = Path(__file__).resolve().parent.parent / "phase_verifiers.py"


def test_no_duplicate_toplevel_defs():
    tree = ast.parse(PV.read_text(encoding="utf-8"))
    counts = collections.Counter(
        node.name for node in tree.body if isinstance(node, ast.FunctionDef))
    dups = {name: n for name, n in counts.items() if n > 1}
    assert dups == {}, f"duplicate top-level defs in phase_verifiers.py: {dups}"
