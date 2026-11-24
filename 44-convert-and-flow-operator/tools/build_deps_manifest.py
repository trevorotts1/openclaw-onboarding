#!/usr/bin/env python3
"""Build the WF-18 --deps manifest from a LIVE read of the location.

qc-built-workflow.sh WF-18 needs a machine-readable manifest of the tags,
custom fields, custom values, calendars and pipelines that EXIST. It must
come from the location, never from the workflow export under test: a
manifest derived from the export would list every reference as present and
prove nothing. This tool reads the five lists with read-only `caf` commands
and writes {"tags": [...], "custom_fields": [...], "custom_values": [...],
"calendars": [...], "pipelines": [...]} plus provenance fields. Each kind
holds every name AND id/key a reference may use. If any live read fails the
tool exits 3 and writes nothing: no network means no manifest.

    python3 build_deps_manifest.py --out deps.json [--caf PATH] [--timeout 60]
    bash qc-built-workflow.sh <workflow-id> --deps deps.json ...
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

READS = (
    ("tags", ["--json", "locations", "tags"], ("tags", "data", "items")),
    ("custom_fields", ["--json", "locations", "custom-fields"], ("customFields", "custom_fields", "fields", "data", "items")),
    ("custom_values", ["--json", "locations", "custom-values"], ("customValues", "custom_values", "values", "data", "items")),
    ("calendars", ["--json", "calendars", "list"], ("calendars", "data", "items")),
    ("pipelines", ["--json", "opportunities", "pipelines"], ("pipelines", "data", "items")),
)
NAME_KEYS = ("name", "fieldKey", "key", "id", "_id", "label")


def rows(payload, keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("no list of rows in the response")


def names(row):
    if isinstance(row, str):
        return [row]
    out = []
    for key in NAME_KEYS:
        value = row.get(key) if isinstance(row, dict) else None
        if isinstance(value, str) and value.strip():
            value = value.strip()
            out.append(value)
            for prefix in ("contact.", "custom_values."):
                if value.startswith(prefix):
                    out.append(value[len(prefix):])
    return out


def build_manifest(fetch):
    """fetch(label, argv) -> parsed JSON. Raises on any failed read."""
    manifest = {}
    for kind, argv, keys in READS:
        collected = []
        for row in rows(fetch(kind, argv), keys):
            for name in names(row):
                if name not in collected:
                    collected.append(name)
        manifest[kind] = collected
    manifest["source"] = "live-read"
    manifest["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--caf", default="caf")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    def fetch(label, command):
        done = subprocess.run([args.caf] + command, capture_output=True, text=True,
                              timeout=args.timeout)
        if done.returncode != 0:
            raise RuntimeError("%s read failed (exit %d)" % (label, done.returncode))
        return json.loads(done.stdout)

    try:
        manifest = build_manifest(fetch)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print("NO MANIFEST: %s" % exc, file=sys.stderr)
        return 3
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    print(json.dumps({"out": args.out, **{k: len(manifest[k]) for k, _a, _b in READS}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
