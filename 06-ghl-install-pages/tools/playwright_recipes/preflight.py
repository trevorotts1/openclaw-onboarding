#!/usr/bin/env python3
"""Read-only runtime check. Does not launch Chrome or read client tokens."""
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse


def browser_runtime():
    """Ask Playwright for its installed executable; never infer it from pip."""
    if importlib.util.find_spec('playwright') is None:
        return {'package_installed':False, 'chromium_installed':False,
                'driver_usable':False, 'reason':'PLAYWRIGHT_PACKAGE_MISSING'}
    try:
        from playwright.sync_api import sync_playwright
        # Starting the bundled driver does not launch a browser or attach a tab.
        with sync_playwright() as playwright:
            installed = Path(playwright.chromium.executable_path).is_file()
        return {'package_installed':True, 'chromium_installed':installed,
                'driver_usable':True,
                'reason':'READY' if installed else 'CHROMIUM_EXECUTABLE_MISSING'}
    except Exception as exc:
        # No raw exception text; paths and environment may contain client data.
        return {'package_installed':True, 'chromium_installed':False,
                'driver_usable':False, 'reason':'PLAYWRIGHT_DRIVER_UNAVAILABLE',
                'error_type':type(exc).__name__}


def check():
    tools = Path(__file__).resolve().parent.parent
    runtime = browser_runtime()
    endpoint = os.environ.get('GHL_MANAGED_CDP_URL', '')
    endpoint_parts = urlparse(endpoint)
    cdp = bool(endpoint and endpoint_parts.scheme in ('http','ws')
        and endpoint_parts.hostname in ('localhost','127.0.0.1','::1')
        and not endpoint_parts.username and not endpoint_parts.password)
    checks = {
        'os': platform.system(),
        'os_supported': platform.system() in ('Darwin','Linux'),
        'python_supported': sys.version_info >= (3, 10),
        'playwright_installed': runtime['package_installed'],
        'chromium_installed': runtime['chromium_installed'],
        'playwright_driver_usable': runtime['driver_usable'],
        'browser_runtime_reason': runtime['reason'],
        'managed_loopback_cdp_configured': cdp,
        'existing_browser_manager': (tools / 'browser_manager.py').is_file(),
        'existing_firebase_bridge': (tools / 'ghl_auth.py').is_file(),
        'openclaw_cli_present': shutil.which('openclaw') is not None,
        'agent_browser_cli_present': shutil.which('agent-browser') is not None,
        'extension_current': 'Run the existing check-openclaw-extension-version.sh; CLI presence is not proof',
        'browser_used': False,
    }
    ready = all(checks[k] for k in ('os_supported','python_supported',
        'playwright_installed','playwright_driver_usable',
        'existing_browser_manager','existing_firebase_bridge'))
    ready = ready and (runtime['chromium_installed'] or cdp)
    checks['status'] = 'READY_FOR_HOST_PROBE' if ready else 'HOST_SETUP_REQUIRED'
    checks['meaning'] = 'Runtime dependencies only; no authentication, tenant access or live job proved'
    return checks


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY_FOR_HOST_PROBE' else 2)
