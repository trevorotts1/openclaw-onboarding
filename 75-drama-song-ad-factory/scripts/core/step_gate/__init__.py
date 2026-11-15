"""step_gate package: re-export the gate module so both import styles bind it.

scripts/core/step_gate/ is a package (it ships __init__.py) whose
executable lives in step_gate.py. A bare import step_gate therefore
binds the package -- which exports nothing -- and every gate function
vanishes (AttributeError: module step_gate has no attribute cmd_init)
whenever the package directory reaches sys.path first (whole-tree
pytest, one process). Re-exporting the module surface here (including the
underscore helpers the gate test uses) keeps the documented per-file solo
invocation AND the one-process collection on the same module object.
"""
from . import step_gate as _mod  # noqa: F401

globals().update(
    {n: v for n, v in vars(_mod).items()
     if not (n.startswith("__") and n.endswith("__"))})
