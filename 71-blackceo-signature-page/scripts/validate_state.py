#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ORDER = [
    "intake",
    "copy",
    "font-action-plan",
    "desktop-wireframe",
    "mobile-tablet",
    "visual-mockup",
    "image-inventory-prompts",
    "image-generation-qc",
    "image-map-upload",
    "final-mockups",
    "responsive-html",
    "ghl-install-test",
    "publish-verify",
]
STATUSES = {"blocked", "working", "qc_failed", "ready"}
VERSIONS = {"standard", "long-form"}


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["Top-level JSON must be an object."]

    if data.get("page_version") not in VERSIONS:
        errors.append("page_version must be 'standard' or 'long-form'.")

    stages = data.get("stages")
    if not isinstance(stages, dict):
        return errors + ["stages must be an object keyed by canonical stage name."]

    missing = [name for name in ORDER if name not in stages]
    extra = [name for name in stages if name not in ORDER]
    if missing:
        errors.append("Missing stages: " + ", ".join(missing))
    if extra:
        errors.append("Unknown stages: " + ", ".join(extra))

    for name in ORDER:
        item = stages.get(name)
        if not isinstance(item, dict):
            if name in stages:
                errors.append(f"Stage {name} must be an object.")
            continue
        status = item.get("status")
        attempts = item.get("attempts")
        if status not in STATUSES:
            errors.append(f"Stage {name} has invalid status {status!r}.")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or not 0 <= attempts <= 3:
            errors.append(f"Stage {name} attempts must be an integer from 0 to 3.")
        if status == "qc_failed" and attempts == 0:
            errors.append(f"Stage {name} is qc_failed but attempts is 0.")

    prior_ready = True
    for name in ORDER:
        item = stages.get(name)
        if not isinstance(item, dict):
            prior_ready = False
            continue
        status = item.get("status")
        if status in {"working", "qc_failed", "ready"} and not prior_ready:
            errors.append(f"Stage {name} cannot be {status} before all required earlier stages are ready.")
        if status != "ready":
            prior_ready = False

    current = data.get("current_stage")
    if current not in ORDER:
        errors.append("current_stage must be one of the canonical stage names.")
    else:
        first_not_ready = next((name for name in ORDER if stages.get(name, {}).get("status") != "ready"), None)
        expected = first_not_ready or ORDER[-1]
        if current != expected:
            errors.append(f"current_stage is {current!r}; expected {expected!r} from stage statuses.")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate BlackCEO private workflow-state JSON.")
    parser.add_argument("state_json", type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.state_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read JSON: {exc}")
        return 2

    errors = validate(data)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: workflow state is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
