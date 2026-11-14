#!/usr/bin/env python3
"""closeout_facts.py -- the one place the closeout reads the company's real identity.

Usage: closeout_facts.py <state-file> [--json]

Prints ONE JSON object (both with and without --json):

  companyName   the state value, else company-config.json `name`
  industry      company-config.json `industry` (falls back to the state value)
  brandPrimary  company-config.json `brand.primary` (falls back to state `brandColor`)
  ownerName     the state value
  agentName     the state value
  ownerChat     the state value when it is a non-zero number or a non-empty
                string other than "0"; else resolved with shared-utils
                resolve-owner-chat.sh when present; else ""
  departments   [{slug, name, roles}] -- one entry per folder under
                <companyRoot>/departments/; `roles` counts that department's
                sub-folders that contain how-to.md
  roleTotal     the sum of every department's `roles`

`companyRoot` is read from the state file; the config is
<companyRoot>/company-config.json. Missing files are never fatal -- an
unreadable file just contributes empty values.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SHARED_UTILS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils")
)


def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    return str(value).strip()


def parse_owner_chat(value) -> str:
    """Non-zero number or non-empty string other than "0"; anything else is empty."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        number = int(value) if float(value).is_integer() else value
        return "" if number == 0 else str(number)
    text = str(value).strip()
    if not text or text == "0":
        return ""
    return text


def resolve_owner_chat() -> str:
    """Run shared-utils/resolve-owner-chat.sh when present, else return ""."""
    script = os.path.join(SHARED_UTILS, "resolve-owner-chat.sh")
    if not os.path.isfile(script):
        return ""
    try:
        done = subprocess.run(
            ["bash", "-c", 'source "$1" >/dev/null 2>&1; resolve_owner_chat_id', "_", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.strip()


def display_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title() or slug


def collect_departments(company_root: str) -> list:
    base = os.path.join(company_root, "departments") if company_root else ""
    if not base or not os.path.isdir(base):
        return []
    try:
        slugs = sorted(os.listdir(base))
    except OSError:
        return []
    departments = []
    for slug in slugs:
        dept_dir = os.path.join(base, slug)
        if not os.path.isdir(dept_dir):
            continue
        roles = 0
        try:
            entries = sorted(os.listdir(dept_dir))
        except OSError:
            entries = []
        for entry in entries:
            role_dir = os.path.join(dept_dir, entry)
            if os.path.isdir(role_dir) and os.path.isfile(os.path.join(role_dir, "how-to.md")):
                roles += 1
        departments.append({"slug": slug, "name": display_name(slug), "roles": roles})
    return departments


def build_facts(state_path: str) -> dict:
    state = load_json(state_path)
    company_root = as_text(state.get("companyRoot"))
    config = load_json(os.path.join(company_root, "company-config.json")) if company_root else {}
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}

    company_name = as_text(state.get("companyName")) or as_text(config.get("name"))
    industry = as_text(config.get("industry")) or as_text(state.get("industry"))
    brand_primary = as_text(brand.get("primary")) or as_text(state.get("brandColor"))
    owner_chat = parse_owner_chat(state.get("ownerChat"))
    if not owner_chat:
        owner_chat = resolve_owner_chat()

    departments = collect_departments(company_root)
    return {
        "companyName": company_name,
        "industry": industry,
        "brandPrimary": brand_primary,
        "ownerName": as_text(state.get("ownerName")),
        "agentName": as_text(state.get("agentName")),
        "ownerChat": owner_chat,
        "departments": departments,
        "roleTotal": sum(dept["roles"] for dept in departments),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the closeout company facts as one JSON object.")
    parser.add_argument("state_file", help="path to .workforce-build-state.json")
    parser.add_argument("--json", action="store_true", help="print the JSON object (the default output)")
    args = parser.parse_args()

    facts = build_facts(args.state_file)
    sys.stdout.write(json.dumps(facts, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
