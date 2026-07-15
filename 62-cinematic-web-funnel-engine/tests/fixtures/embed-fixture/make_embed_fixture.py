#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_embed_fixture.py — the DETERMINISTIC fixture spec Section 19.3
requires, scoped to build unit U18 (GHL whole-page iframe embed package).

Named make_embed_fixture.py rather than make_fixture.py deliberately:
tests/fixtures/site-fixture/ already ships its own unrelated make_fixture.py
for U15, and a single `unittest discover` process loads both fixture
directories' test modules together — two files sharing the literal module
name `make_fixture` would collide in sys.modules and silently shadow each
other depending on import order (caught during this unit's own test run;
see the aliased `import make_embed_fixture as make_fixture` call sites in
scripts/build_embed_package.py and tests/{unit,integration}/*.py).

Materializes a schema-valid `deployment-receipt.json`
(structure/deployment-receipt.schema.json, U6) + `embed-request.json`
(structure/embed-request.schema.json, this unit) into a caller-supplied
run_dir — exactly the two artifacts `scripts/build_embed_package.py` reads,
with no randomness, so re-running this against an empty target directory
always produces byte-identical input JSON (build_embed_package.py's own
`created_at` stamp on its OUTPUT receipt is the only thing that varies
between runs, same as every other build_*.py in this skill).

CLI:
    python3 make_embed_fixture.py --run-dir /path/to/run_dir

Library:
    write_fixture_run_dir(run_dir: Path) -> dict
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

SCHEMA_VERSION = "1.0.0"
PROJECT_ID = "u18-fixture-project"
PROJECT_SLUG = "u18-fixture-project"
FIXTURE_TIMESTAMP = "2026-07-15T00:00:00Z"

HOSTED_URL = "https://u18-fixture-project-preview.vercel.app"
FALLBACK_URL = "https://u18-fixture-project-preview.vercel.app/"
ALLOWED_ANCESTOR_ORIGINS = [
    "https://fixture-client.gohighlevel.com",
    "https://fixture-client.msgsndr.com",
]
IFRAME_TITLE = 'U18 Fixture — Cinematic Funnel Experience'


def build_deployment_receipt() -> Dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "environment": "preview",
        "host": "vercel",
        "host_project_id": "prj_fixture123456",
        "host_deployment_id": "dpl_fixture123456",
        "url": HOSTED_URL,
        "commit_sha": "deadbeefcafefeedfacefeedfacefeedfacefeed",
        "status": "ready",
        "restart_verified": True,
        "created_at": FIXTURE_TIMESTAMP,
        "updated_at": FIXTURE_TIMESTAMP,
    }


def build_embed_request() -> Dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "project_slug": PROJECT_SLUG,
        "allowed_ancestor_origins": list(ALLOWED_ANCESTOR_ORIGINS),
        "iframe_title": IFRAME_TITLE,
        "fallback_url": FALLBACK_URL,
        "default_height_px": 900,
        "created_at": FIXTURE_TIMESTAMP,
    }


def write_fixture_run_dir(run_dir: Path) -> Dict[str, Path]:
    """Writes deployment-receipt.json + embed-request.json into run_dir
    (creating it if needed). Returns the paths written so callers
    (build_embed_package.py's --fixture mode, tests) don't have to
    re-derive the layout convention."""
    run_dir.mkdir(parents=True, exist_ok=True)

    deployment_path = run_dir / "deployment-receipt.json"
    request_path = run_dir / "embed-request.json"

    deployment_path.write_text(
        json.dumps(build_deployment_receipt(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    request_path.write_text(
        json.dumps(build_embed_request(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return {"deployment_receipt": deployment_path, "embed_request": request_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    paths = write_fixture_run_dir(args.run_dir)
    print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
