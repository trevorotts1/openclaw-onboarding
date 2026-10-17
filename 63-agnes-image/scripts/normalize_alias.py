#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_alias.py -- normalizes voice/transcription and casual model aliases to canonical IDs.

Authority: Spec §13 (Alias Normalization).
"""

from __future__ import annotations

import argparse
import json
import sys

ALIAS_MAP = {
    # Generic (unpinned) aliases resolve to the current default, 2.5 Flash.
    "agnes image": "agnes-image-2.5-flash",
    "agnes image flash": "agnes-image-2.5-flash",
    "agnes-image-flash": "agnes-image-2.5-flash",
    "agnes-image": "agnes-image-2.5-flash",
    # Explicit 2.5 aliases.
    "agnes image 2.5": "agnes-image-2.5-flash",
    "agnes image 2.5 flash": "agnes-image-2.5-flash",
    "agnes-image-25-flash": "agnes-image-2.5-flash",
    "agnes-image-2.5-flash": "agnes-image-2.5-flash",
    # Explicit legacy 2.1 pins are preserved, never silently rewritten.
    "agnes image 2.1": "agnes-image-2.1-flash",
    "agnes image 2.1 flash": "agnes-image-2.1-flash",
    "agnes-image-21-flash": "agnes-image-2.1-flash",
    "agnes-image-2.1-flash": "agnes-image-2.1-flash",
}


def normalize(name: str) -> str:
    cleaned = name.strip().lower()
    return ALIAS_MAP.get(cleaned, name.strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize Agnes Image model alias.")
    parser.add_argument("model_name", nargs="?", help="Model alias or name to normalize.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test.")
    args = parser.parse_args(argv)

    if args.self_test:
        assert normalize("agnes image") == "agnes-image-2.5-flash"
        assert normalize("agnes image 2.5 flash") == "agnes-image-2.5-flash"
        assert normalize("agnes image 2.1 flash") == "agnes-image-2.1-flash"
        assert normalize("agnes-image-21-flash") == "agnes-image-2.1-flash"
        print("normalize_alias.py --self-test: PASS")
        return 0

    if not args.model_name:
        parser.print_usage(sys.stderr)
        return 1

    canonical = normalize(args.model_name)
    print(canonical)
    return 0


if __name__ == "__main__":
    sys.exit(main())
