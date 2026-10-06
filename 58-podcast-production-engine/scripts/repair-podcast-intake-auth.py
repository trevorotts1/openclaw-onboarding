#!/usr/bin/env python3
"""Repair the two source-template intake workflow auth headers, safely.

The public podcast hooks ingress accepts only ``Authorization: Bearer <token>``
or ``X-OpenClaw-Token``.  This utility repairs the stale source-template
``X-Podcast-Intake-Secret`` header without touching payload fields, triggers,
status, or any other workflow asset.  ``--apply`` is deliberately opt-in and
writes exact pre-change workflow snapshots before either PUT.

It uses the proven Firebase/internal GHL workflow rail, not a browser session.
Secrets are read only in memory and are never printed or written to backups.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-podcast-ghl-workflows.py"
DEFAULT_LOCATION = "CjxATjhv9Gt21qSqURIt"
TARGETS = {
    "01-Podcast Intake Submitted (Interview)",
    "02-Podcast Intake Submitted (Personal)",
}
OLD_HEADER = "X-Podcast-Intake-Secret"
NEW_HEADER = "Authorization"
NEW_VALUE = "Bearer {{custom_values.podcast_intake_hook_secret}}"
SERVER_KEYS = {
    "_id", "id", "__v", "createdAt", "updatedAt", "companyId", "locationId",
    "companyAge", "creationSource", "originType", "deleted",
    "isTriggerBucketMigrated", "permissionMeta",
}


def load_rail():
    spec = importlib.util.spec_from_file_location("podcast_wf_qc", VERIFY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verified internal rail: {VERIFY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = ["PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN", "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"]
    module._source_secrets_if_needed(names)
    refresh = next((module.os.environ[n] for n in names if module.os.environ.get(n, "").strip()), "")
    if not refresh:
        raise RuntimeError("no Firebase refresh token label is configured")
    token = module._mint(refresh)
    if not token:
        raise RuntimeError("Firebase mint returned an empty token")
    return module, token


def put(module, token: str, path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        module.BASE + path,
        data=data,
        method="PUT",
        headers={
            "token-id": token,
            "channel": "APP",
            "source": "WEB_USER",
            "version": "2021-07-28",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": module.UA,
        },
    )
    try:
        with urllib.request.urlopen(request, context=module.CTX, timeout=45) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {"_error": "HTTP error"}


def webhook_steps(workflow: dict) -> list[dict]:
    templates = (workflow.get("workflowData") or {}).get("templates") or []
    return [step for step in templates if isinstance(step, dict) and step.get("type") == "webhook"]


def inspect(workflow: dict) -> tuple[str, list[dict]]:
    hits: list[dict] = []
    for step in webhook_steps(workflow):
        attrs = step.get("attributes") or {}
        if "podcast_intake_webhook_url" not in str(attrs):
            continue
        headers = attrs.get("headers")
        if not isinstance(headers, list) or len(headers) != 1 or not isinstance(headers[0], dict):
            raise ValueError(f"{workflow.get('name')}: expected exactly one intake header")
        hits.append(headers[0])
    if len(hits) != 1:
        raise ValueError(f"{workflow.get('name')}: expected exactly one intake webhook step")
    header = hits[0]
    key, value = header.get("key"), header.get("value")
    if key == NEW_HEADER and value == NEW_VALUE:
        return "already-correct", hits
    if key == OLD_HEADER and value == "{{custom_values.podcast_intake_hook_secret}}":
        return "repair-needed", hits
    raise ValueError(f"{workflow.get('name')}: unexpected intake header shape")


def backup(path: Path, workflow: dict) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"{workflow['id']}-{int(time.time())}-pre-auth-repair.json"
    out.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--apply", action="store_true", help="write the two minimal header repairs")
    parser.add_argument("--backup-dir", default=str(ROOT / "work" / "workflow-auth-backups"))
    args = parser.parse_args()

    module, token = load_rail()
    code, listing = module._get(token, f"/workflow/{args.location}/list?limit=200")
    if code != 200:
        raise RuntimeError(f"workflow list failed: HTTP {code}")
    rows = {row.get("name"): row for row in listing.get("rows", []) if isinstance(row, dict)}
    missing = TARGETS - set(rows)
    if missing:
        raise RuntimeError(f"missing target workflow(s): {sorted(missing)}")

    planned: list[tuple[dict, str]] = []
    for name in sorted(TARGETS):
        row = rows[name]
        code, workflow = module._get(token, f"/workflow/{args.location}/{row['id']}")
        if code != 200:
            raise RuntimeError(f"{name}: GET failed HTTP {code}")
        state, _ = inspect(workflow)
        print(f"{name}: {state}")
        planned.append((workflow, state))

    if not args.apply:
        print("CHECK ONLY: no workflow changed")
        return 0

    backups: list[Path] = []
    for workflow, state in planned:
        if state == "repair-needed":
            backups.append(backup(Path(args.backup_dir), workflow))
    if not backups:
        print("APPLY NO-OP: both workflows already use Authorization Bearer")
        return 0
    print(f"snapshots captured: {len(backups)}")

    changed: list[dict] = []
    try:
        for workflow, state in planned:
            if state != "repair-needed":
                continue
            candidate = copy.deepcopy(workflow)
            _, headers = inspect(candidate)
            headers[0]["key"] = NEW_HEADER
            headers[0]["value"] = NEW_VALUE
            body = {key: value for key, value in candidate.items() if key not in SERVER_KEYS}
            code, _ = put(module, token, f"/workflow/{args.location}/{workflow['id']}", body)
            if code < 200 or code >= 300:
                raise RuntimeError(f"{workflow['name']}: PUT failed HTTP {code}")
            code, readback = module._get(token, f"/workflow/{args.location}/{workflow['id']}")
            if code != 200 or inspect(readback)[0] != "already-correct":
                raise RuntimeError(f"{workflow['name']}: POST-PUT header readback failed")
            changed.append(workflow)
            print(f"{workflow['name']}: repaired and read back")
    except Exception:
        # Revert only workflows this invocation actually changed, using their exact
        # captured source bodies.  Preserve the original error for the caller.
        originals = {workflow["id"]: workflow for workflow, state in planned if state == "repair-needed"}
        for workflow in reversed(changed):
            original = originals[workflow["id"]]
            body = {key: value for key, value in original.items() if key not in SERVER_KEYS}
            put(module, token, f"/workflow/{args.location}/{workflow['id']}", body)
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # Avoid emitting bodies or secrets on failures.
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
