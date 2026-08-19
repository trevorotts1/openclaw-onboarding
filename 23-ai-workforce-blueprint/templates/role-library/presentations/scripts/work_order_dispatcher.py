#!/usr/bin/env python3
"""
work_order_dispatcher.py -- standalone entry point for the Work-Order Dispatcher.

Same code as `python3 -m presentation_job.dispatcher` (this file just makes it
runnable directly, e.g. by an operator, a cron, or the Engine's own auto-spawn
in presentation_job/__main__.py, without requiring `-m` package invocation).

    python3 work_order_dispatcher.py --run-dir <run_dir> --watch
    python3 work_order_dispatcher.py --run-dir <run_dir> --once
    python3 work_order_dispatcher.py --scan-root <department>/runs --watch

See presentation_job/dispatcher.py for the implementation and
CONTROL/DISPATCHER-SPEC.md for the design this implements.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job.dispatcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
