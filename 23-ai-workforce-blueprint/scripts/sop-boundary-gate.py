#!/usr/bin/env python3
"""
sop-boundary-gate.py — CLI entry point shim for PRD 2.12 boundary gate.

The boundary gate logic lives in sop_boundary_gate.py (underscore name) so it
is importable as a Python module.  This shim forwards all CLI invocations to
that module so shell scripts can call:
  python3 sop-boundary-gate.py --check-manifest /path/to/manifest.json

Importing this file directly will also work via the module re-export below.
"""
import sys
import os

# Ensure the scripts directory is on the path so sop_boundary_gate is found.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from sop_boundary_gate import _cli  # type: ignore  # noqa: E402

# Re-export everything for `from sop-boundary-gate import ...` attempts
# (not standard Python, but some scripts do this via importlib).
from sop_boundary_gate import (  # noqa: F401, E402
    CANONICAL_LIBRARY_DEPT_IDS,
    ROLE_LIBRARY_DIR,
    CanonicalDeptAuthError,
    is_canonical_dept,
    refuse_if_canonical,
    classify_manifest_depts,
    assert_no_canonical_in_authoring_path,
)

if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
