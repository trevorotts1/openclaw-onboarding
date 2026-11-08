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


def headless_shell_executable(full_executable, *, package_root=None, system=None, machine=None):
    """Find only this Playwright package's expected headless-shell revision.

    The public Chromium executable path is supplied by the installed driver, so
    its browser cache root already follows OS defaults, PLAYWRIGHT_BROWSERS_PATH
    (including 0), and relative-path/INIT_CWD semantics. No directory glob can
    accidentally accept an older installed revision. Detection proves presence,
    not launch/authentication. Layouts below are the vendor's old/new layouts.
    """
    if package_root is None:
        import playwright
        package_root = Path(playwright.__file__).resolve().parent / 'driver' / 'package'
    manifest = json.loads((Path(package_root) / 'browsers.json').read_text())
    descriptors = {entry['name']:entry for entry in manifest.get('browsers', [])}
    shell = descriptors.get('chromium-headless-shell')
    chromium = descriptors.get('chromium', {})
    if not shell:
        return None
    supported_revisions = {str(chromium.get('revision'))}
    supported_revisions.update(str(value) for value in chromium.get('revisionOverrides', {}).values())
    full_dir = next((parent for parent in Path(full_executable).parents
        if parent.name.startswith('chromium-') and parent.name.rsplit('-', 1)[-1] in supported_revisions), None)
    if full_dir is None:
        return None
    # Chromium currently has no shell platform overrides. Do not guess a platform
    # key if a future package introduces them; remain conservative for a probe.
    if shell.get('revisionOverrides'):
        return None
    revision = str(shell.get('revision', ''))
    if not revision.isdigit():
        return None
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if machine not in ('arm64','aarch64','x86_64','amd64','x64'):
        return None
    arm = machine in ('arm64','aarch64')
    if system == 'Darwin':
        layouts = [('chrome-headless-shell-mac-' + ('arm64' if arm else 'x64'), 'chrome-headless-shell'),
                   ('chrome-mac', 'headless_shell')]
    elif system == 'Linux':
        layouts = [('chrome-headless-shell-linux-' + 'arm64', 'chrome-headless-shell')] if arm else [('chrome-headless-shell-linux64','chrome-headless-shell')]
        layouts.append(('chrome-linux', 'headless_shell'))
    else:
        return None
    directory = full_dir.parent / ('chromium_headless_shell-' + revision)
    for parts in layouts:
        candidate = directory.joinpath(*parts)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def browser_runtime():
    """Ask Playwright for its installed executable; never infer it from pip."""
    if importlib.util.find_spec('playwright') is None:
        return {'package_installed':False, 'chromium_installed':False,
                'driver_usable':False, 'reason':'PLAYWRIGHT_PACKAGE_MISSING'}
    try:
        from playwright.sync_api import sync_playwright
        # Starting the bundled driver does not launch a browser or attach a tab.
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            installed = executable.is_file() and os.access(executable, os.X_OK)
            shell_installed = headless_shell_executable(executable) is not None
        return {'package_installed':True, 'chromium_installed':installed,
                'headless_shell_installed':shell_installed, 'driver_usable':True,
                'reason':'READY' if shell_installed else 'HEADLESS_RUNTIME_EXECUTABLE_MISSING'}
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
        'headless_shell_installed': runtime.get('headless_shell_installed', False),
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
    ready = ready and (runtime.get('headless_shell_installed', runtime['chromium_installed']) or cdp)
    checks['status'] = 'READY_FOR_HOST_PROBE' if ready else 'HOST_SETUP_REQUIRED'
    checks['meaning'] = 'Runtime dependencies only; no authentication, tenant access or live job proved'
    return checks


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY_FOR_HOST_PROBE' else 2)
