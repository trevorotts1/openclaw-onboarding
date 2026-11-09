"""Suite path setup for the launcher.

Lives at the skill root, not in tests/: tests/test_version_cli_parity.py forbids a test-module stem that a
sibling skill's scripts directory also uses (75-drama-song-ad-factory/scripts/conftest.py), and pytest finds a
conftest.py in any parent of the tests it collects.

There is no account-entitlement read-back any more: the client is never asked to declare a membership
or a purchase, so there is nothing to install and nothing that can block a build.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
