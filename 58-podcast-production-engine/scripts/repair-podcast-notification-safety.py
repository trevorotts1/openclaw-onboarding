#!/usr/bin/env python3
"""Put unsafe template notification placeholders into Draft, safely.

The source snapshot must not ship published client-facing Email/SMS placeholder
actions.  This utility changes only the *status* of the two named notification
workflows (04 and 06) from ``published`` to ``draft``.  It does not delete,
edit, or execute the actions, triggers, or any contact data.  ``--apply`` is
required for writes and exact pre-change workflow snapshots are captured first.

The internal Firebase workflow rail is used because it is the authenticated API
that backs the source-template account; no browser session is required.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-podcast-ghl-workflows.py"
DEFAULT_LOCATION = "CjxATjhv9Gt21qSqURIt"
TARGETS = {
    "04-Podcast is Completed": {"contact_changed", "email", "sms"},
    "06-Podcast_Episode_Is_Ready": {"contact_tag", "email", "sms"},
}
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


def put(module, token: str, path: str, body: dict) -> int:
    request = urllib.request.Request(
        module.BASE + path,
        data=json.dumps(body).encode("utf-8"), method="PUT",
        headers={
            "token-id": token, "channel": "APP", "source": "WEB_USER",
            "version": "2021-07-28", "Accept": "application/json",
            "Content-Type": "application/json", "User-Agent": module.UA,
        },
    )
    try:
        with urllib.request.urlopen(request, context=module.CTX, timeout=45) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def validate(name: str, workflow: dict, triggers: list[dict]) -> str:
    if workflow.get("status") not in {"published", "draft"}:
        raise ValueError(f"{name}: unexpected status")
    expected = TARGETS[name]
    types = {
        step.get("type") for step in (workflow.get("workflowData") or {}).get("templates", [])
        if isinstance(step, dict)
    }
    if not {"email", "sms"}.issubset(types):
        raise ValueError(f"{name}: not the expected Email/SMS notification workflow")
    if not isinstance(triggers, list) or not triggers or triggers[0].get("type") not in expected:
        raise ValueError(f"{name}: unexpected trigger shape")
    return "already-safe" if workflow.get("status") == "draft" else "draft-needed"


def backup(path: Path, workflow: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{workflow['id']}-{int(time.time())}-pre-notification-safety.json").write_text(
        json.dumps(workflow, indent=2), encoding="utf-8"
    )


def body(workflow: dict) -> dict:
    return {key: value for key, value in workflow.items() if key not in SERVER_KEYS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--apply", action="store_true", help="change the two source notification workflows to draft")
    parser.add_argument("--backup-dir", default=str(ROOT / "work" / "workflow-notification-backups"))
    args = parser.parse_args()

    module, token = load_rail()
    code, listing = module._get(token, f"/workflow/{args.location}/list?limit=200")
    if code != 200:
        raise RuntimeError(f"workflow list failed: HTTP {code}")
    rows = {row.get("name"): row for row in listing.get("rows", []) if isinstance(row, dict)}
    missing = set(TARGETS) - set(rows)
    if missing:
        raise RuntimeError(f"missing target workflow(s): {sorted(missing)}")

    planned: list[tuple[dict, str]] = []
    for name in sorted(TARGETS):
        code, workflow = module._get(token, f"/workflow/{args.location}/{rows[name]['id']}")
        code_t, triggers = module._get(token, f"/workflow/{args.location}/trigger?workflowId={rows[name]['id']}")
        if code != 200 or code_t != 200:
            raise RuntimeError(f"{name}: source read failed")
        state = validate(name, workflow, triggers)
        print(f"{name}: {state}")
        planned.append((workflow, state))

    if not args.apply:
        print("CHECK ONLY: no workflow changed")
        return 0

    changing = [workflow for workflow, state in planned if state == "draft-needed"]
    if not changing:
        print("APPLY NO-OP: both notification workflows are already draft")
        return 0
    for workflow in changing:
        backup(Path(args.backup_dir), workflow)
    print(f"snapshots captured: {len(changing)}")

    changed: list[dict] = []
    try:
        for workflow in changing:
            candidate = copy.deepcopy(workflow)
            candidate["status"] = "draft"
            code = put(module, token, f"/workflow/{args.location}/{workflow['id']}", body(candidate))
            if not 200 <= code < 300:
                raise RuntimeError(f"{workflow['name']}: PUT failed HTTP {code}")
            code, readback = module._get(token, f"/workflow/{args.location}/{workflow['id']}")
            if code != 200 or readback.get("status") != "draft":
                raise RuntimeError(f"{workflow['name']}: POST-PUT status readback failed")
            changed.append(workflow)
            print(f"{workflow['name']}: drafted and read back")
    except Exception:
        for workflow in reversed(changed):
            put(module, token, f"/workflow/{args.location}/{workflow['id']}", body(workflow))
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
