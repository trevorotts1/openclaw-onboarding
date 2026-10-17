#!/usr/bin/env python3
"""Check the pinned external authorities (Skill 71, Item 11).

Skill 71 silently obeys rule sources that live outside the skill:
KIE common rules, the shared prompt enforcer, Skill 74's live adapter,
and Skill 66's model registry. references/external-authorities.json pins
each one to the exact git blob SHA this version of the skill was verified
against. This script hashes the installed counterpart of each pin and
prints, per authority:

  PIN OK:     <name>  (found at <path>)
  PIN DRIFT:  <name>  expected <sha> found <sha>  (at <path>)
  PIN MISSING: <name>  no installed counterpart found at <path>

Drift is a WARNING, not a failure: the external source may have moved
legitimately, but it stops being invisible. Updating a pin is a
deliberate act: change the SHA in external-authorities.json, bump
checked_on, and note it in the skill CHANGELOG. With --strict, drift
and missing both exit 1 (for CI use); verify.sh calls this script
without --strict.

Resolution: each pin's repo-relative path is resolved against every
search root: --repo-root values, the SKILL71_REPO_ROOT environment
variable, the skill folder's parent (the normal in-repo install), and
the skill folder's grandparent. The git blob SHA is computed locally
(sha1 of "blob <len>\\0" + file bytes), so no git binary and no network
are needed.

Usage:
  check_authority_pins.py [--pins <external-authorities.json>]
                          [--repo-root <path>]... [--strict]

Exit codes: 0 all pins OK or warning-only mode, 1 strict-mode drift or
missing, 2 unreadable input.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def blob_sha(path):
    data = Path(path).read_bytes()
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def default_skill_root():
    return Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Check pinned external authorities (Skill 71, Item 11).")
    parser.add_argument("--pins", type=Path, default=None,
                        help="external-authorities.json (default: the skill's "
                             "references/external-authorities.json)")
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="when given, drift/missing records are written to "
                             "<run-dir>/private/pin-drift.json so the first gate "
                             "init afterward emits them as pin_drift run events "
                             "(Item 11 rider, run-events schema section 6.7)")
    parser.add_argument("--repo-root", type=Path, action="append", default=[],
                        help="repo root to resolve pin paths against; repeatable")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on drift or missing (default: warn only)")
    args = parser.parse_args()

    skill_root = default_skill_root()
    pins_path = args.pins or (skill_root / "references" / "external-authorities.json")
    try:
        data = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read pins file {pins_path}: {exc}")
        return 2
    authorities = data.get("authorities") if isinstance(data, dict) else data
    if not isinstance(authorities, list) or not authorities:
        print(f"FAIL: pins file {pins_path} has no authorities array.")
        return 2

    roots = list(args.repo_root)
    env_root = os.environ.get("SKILL71_REPO_ROOT")
    if env_root:
        roots.append(Path(env_root))
    roots.extend([skill_root.parent, skill_root.parent.parent, Path.cwd()])
    seen = set()
    unique_roots = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique_roots.append(root)

    problems = 0
    drift_records = []
    for entry in authorities:
        name = entry.get("name", "<unnamed>")
        rel = entry.get("path", "")
        expected = entry.get("blob_sha", "")
        found_path = None
        for root in unique_roots:
            candidate = Path(root) / rel
            if candidate.is_file():
                found_path = candidate
                break
        if found_path is None:
            problems += 1
            drift_records.append({"authority_id": rel, "pinned_sha": expected,
                                  "observed_sha": None})
            print(f"PIN MISSING: {name}  no installed counterpart found at {rel} "
                  f"(searched: {', '.join(str(r) for r in unique_roots)})")
            continue
        actual = blob_sha(found_path)
        if actual == expected:
            print(f"PIN OK: {name} (found at {found_path})")
        else:
            problems += 1
            drift_records.append({"authority_id": rel, "pinned_sha": expected,
                                  "observed_sha": actual})
            print(f"PIN DRIFT: {name} expected {expected} found {actual} "
                  f"(at {found_path})")

    if args.run_dir is not None:
        record_path = args.run_dir / "private" / "pin-drift.json"
        if drift_records:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(json.dumps(drift_records, indent=2) + "\n",
                                   encoding="utf-8")
            print(f"pin drift recorded at {record_path} for the run's event feed")
        elif record_path.is_file():
            record_path.unlink()
            print("pin drift record cleared (all pins OK)")

    if problems and args.strict:
        print(f"FAIL: {problems} pinned authority problem(s) in strict mode.")
        return 1
    if problems:
        print(f"WARN: {problems} pinned authority problem(s) above; drift is "
              "reported, not failed. Update the pin deliberately or run with "
              "--strict in CI to make it a failure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
