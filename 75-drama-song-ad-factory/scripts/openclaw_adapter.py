#!/usr/bin/env python3
"""OpenClaw runtime adapter (Skill 75) — thin shell over the shared control CLI.

Directive 24.1/25/26: both distributions run ONE Python control entrypoint; a
runtime adapter may not reimplement or bypass it. This file does exactly
three things:

  1. resolve the shared entrypoint ``core/intake_preflight/factory.py``
     sitting next to this file (repo convention for ``scripts/factory.py``),
  2. run it as ``[sys.executable, entrypoint, *argv]`` — an argument array,
     never a shell string (no shell=True, no string join, no interpolation),
  3. relay its stdout/stderr and exit code unchanged.

Zero intake/preflight/QC/guard logic lives here, so no core behavior can
drift between distributions. A nonzero entrypoint exit is returned as-is:
a failed shared guard is never masked, retried, or routed to a fallback.

Exit codes are core's map, relayed not re-derived:
ok 0, error 1, waiting 2, parked 3, rejected 4. Every envelope a caller
sees is the one ``factory.py`` itself printed (schema_version
blackceo.intake-preflight/envelope/v1); the adapter never wraps or rewrites it.
"""
import os
import subprocess
import sys

ENTRYPOINT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "core", "intake_preflight", "factory.py",
)

# ponytail: single hardcoded path; if the shared entrypoint moves to
# scripts/factory.py (directive 24.1 wording), change this one line.


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not os.path.isfile(ENTRYPOINT):
        sys.stderr.write(
            "openclaw_adapter: shared entrypoint missing: %s\n" % ENTRYPOINT)
        return 1
    proc = subprocess.run([sys.executable, ENTRYPOINT] + argv)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
