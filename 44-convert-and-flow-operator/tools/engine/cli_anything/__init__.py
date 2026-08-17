"""cli_anything — top-level package.

This filter MUST stay the very first statement executed here (before any
other import in this file, and before any submodule of cli_anything is
reached): Python always runs a parent package's __init__.py in full before
any of its submodules, so registering the filter first is what guarantees it
is active before urllib3 itself is ever imported anywhere in the CLI's import
chain — urllib3 raises NotOpenSSLWarning as a side effect of importing
urllib3/__init__.py itself (venvs pairing Python 3.9 with LibreSSL, i.e.
stock macOS python3), so a filter registered any later, or one that tries to
reference urllib3.exceptions.NotOpenSSLWarning directly, is too late: naming
the class requires importing urllib3.exceptions, which first runs
urllib3/__init__.py in full and the warning has already fired by then.
Matched by module (regex on the warning's origin module name) rather than a
blanket `ignore`, so this stays scoped to urllib3's own warnings and doesn't
hide a real deprecation warning raised by this package or its dependencies.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=Warning, module=r"^urllib3(\.|$)")
