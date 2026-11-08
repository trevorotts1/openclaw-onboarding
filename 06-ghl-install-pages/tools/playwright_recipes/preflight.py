#!/usr/bin/env python3
"""Read-only runtime check. Does not launch Chrome or read client tokens."""
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path


def check():
    tools = Path(__file__).resolve().parent.parent
    checks = {
        'os': platform.system(),
        'python_supported': sys.version_info >= (3, 10),
        'playwright_installed': importlib.util.find_spec('playwright') is not None,
        'existing_browser_manager': (tools / 'browser_manager.py').is_file(),
        'existing_firebase_bridge': (tools / 'ghl_auth.py').is_file(),
        'openclaw_cli_present': shutil.which('openclaw') is not None,
        'agent_browser_cli_present': shutil.which('agent-browser') is not None,
        'extension_current': 'Run the existing check-openclaw-extension-version.sh; CLI presence is not proof',
        'browser_used': False,
    }
    checks['status'] = 'READY_FOR_HOST_PROBE' if all(checks[k] for k in ('python_supported','playwright_installed','existing_browser_manager','existing_firebase_bridge')) else 'HOST_SETUP_REQUIRED'
    return checks


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY_FOR_HOST_PROBE' else 2)
