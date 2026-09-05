#!/usr/bin/env python3
"""Read-only CC security floor, shared by fresh installs and fleet updates.

Keep SECURITY_MIN_VERSION aligned with cc-compat.json when raising the floor.
The installed shared-utils tree may not contain that repository-root JSON file.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SECURITY_MIN_VERSION = (7, 1, 0)
NODE_RANGE = '^20.19.0 || ^22.13.0 || >=24'


def stable_version(raw: str) -> tuple[int, int, int]:
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', raw.strip())
    if not match:
        raise ValueError(f'Cannot verify stable version {raw!r}')
    return tuple(map(int, match.groups()))


def assert_node_version(raw: str) -> None:
    major, minor, patch = stable_version(raw)
    if not ((major == 20 and (minor, patch) >= (19, 0))
            or (major == 22 and (minor, patch) >= (13, 0)) or major >= 24):
        raise ValueError(f'Command Center requires Node {NODE_RANGE}; found {raw.strip()}. '
                         'Install a compatible Node runtime and rerun; no automatic runtime replacement is performed.')


def check_node() -> None:
    result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=10, check=True)
    assert_node_version(result.stdout)


def assert_cc_package(package: dict) -> None:
    if stable_version(package.get('version', '')) < SECURITY_MIN_VERSION:
        raise ValueError('Command Center security minimum is v7.1.0; refusing an older checkout. '
                         'Publish/fetch the paired security release before retrying.')


def check_checkout(directory: Path) -> None:
    assert_cc_package(json.loads((directory / 'package.json').read_text()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path)
    args = parser.parse_args()
    try:
        check_node()
        if args.checkout is not None:
            check_checkout(args.checkout)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'CC compatibility preflight failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
