"""run_preflight package: one command that lists every missing or unusable
input at once (plan N-01). stdlib only."""
from . import run_preflight as _mod  # noqa: F401

globals().update(
    {n: v for n, v in vars(_mod).items()
     if not (n.startswith("__") and n.endswith("__"))})
