#!/usr/bin/env python3
"""Run the V2-13 lip-sync canary through the scripted mock harness.

Writes the recorded result beside this file. Live mode is refused: this window
spends nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import mock_harness as mh

HERE = pathlib.Path(__file__).resolve().parent


def build_report(paths: list[str]) -> dict:
    spec = mh.load_spec()
    mh.validate_spec(spec)
    shot = mh.load_fixture("shot_painful_moment.json")
    runs = [mh.run_path(spec, shot, path) for path in paths]
    paid = sum(int(r["paid_calls"]) for r in runs)
    spend = sum(float(r["spend_usd"]) for r in runs)
    if paid or spend:
        raise mh.LiveCallRefused(
            f"canary recorded paid_calls={paid} spend_usd={spend}; refusing to write"
        )
    return {
        "schema": "blackceo.v2-13-canary/run/v1",
        "canary_id": spec["canary_id"],
        "owner_decision": spec["owner_decision"],
        "mode": spec["mode"],
        "providers": [p["model"] for p in spec["providers"]],
        "shot": {
            "shot_id": shot["shot_id"],
            "style": shot["style"],
            "count": spec["shots"]["count"],
        },
        "paid_calls": paid,
        "spend_usd": spend,
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="attempt the live (paid) canary; always refused in this window",
    )
    parser.add_argument(
        "--out",
        default=str(HERE / "outcomes"),
        help="directory for run.json (default: outcomes beside this file)",
    )
    args = parser.parse_args(argv)

    if args.live:
        try:
            mh.run_live()
        except mh.LiveCallRefused as exc:
            print(f"live-refused: {exc}", file=sys.stderr)
            return 3

    try:
        report = build_report(list(mh.PATHS))
    except (mh.SpecError, mh.LiveCallRefused) as exc:
        print(f"canary-refused: {exc}", file=sys.stderr)
        return 1

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "run.json"
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    for run in report["runs"]:
        print(
            f"{run['path']}: attempts={run['attempts']} winner={run['winner']} "
            f"status={run['final_status']}"
        )
    print(f"paid_calls={report['paid_calls']} spend_usd={report['spend_usd']} mode={report['mode']}")
    try:
        shown = target.resolve().relative_to(HERE)
    except ValueError:
        shown = target.name
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
