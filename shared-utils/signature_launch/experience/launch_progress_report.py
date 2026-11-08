#!/usr/bin/env python3
"""Human launch-progress report and Command Center projection (F15.6).

Both are DERIVED views over ``progress.report()``.  Neither is an authority:
the percentage, the delivered count and every stage come from current admission
evidence re-validated by ``progress.evidence_view``.  Generating a report never
re-renders an image, rebuilds a page or dispatches a unit -- intact evidence is
enough (F15.8).

The five stages are distinct on purpose and are never collapsed into "done":

    draft created           bytes/artifacts exist, nothing proves them
    design ready for review  a design artifact is waiting on independent review
    approved                verified production work approved for the next step
    installed               verified and draft-installed on the target
    live                    verified, approved and published/observed

USAGE
    python3 launch_progress_report.py --file progress-<launch>.json
    python3 launch_progress_report.py --file progress-<launch>.json --shape lines
    python3 launch_progress_report.py --file progress-<launch>.json --projection
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROGRESS = None

STAGE_LABELS = {
    "not_started": "not started",
    "draft_created": "draft created",
    "design_ready_for_review": "design ready for review",
    "approved": "approved",
    "installed": "installed",
    "live": "live",
}


def _progress():
    """Load the owning ledger (shared-utils/signature_launch/progress.py)."""
    global _PROGRESS
    if _PROGRESS is None:
        path = _HERE.parent / "progress.py"
        spec = importlib.util.spec_from_file_location("signature_launch_report_progress", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PROGRESS = module
    return _PROGRESS


def label(stage):
    return STAGE_LABELS.get(str(stage), str(stage).replace("_", " "))


def _rows(doc):
    return list(doc.get("units") or [])


def headline(doc):
    return ("%s%% delivered (%d of %d required units verified from current evidence)."
            % (doc["percent"], doc["delivered"], doc["required"]))


def table(doc):
    out = ["| Unit | Stage | Production | Review | Deployment | Availability | Evidence |",
           "|---|---|---|---|---|---|---|"]
    for row in _rows(doc):
        evidence = "verified" if row["trusted"] else (
            row.get("evidence_reason") or "unverified")
        out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["id"], label(row["stage"]), row["production"], row["review"],
            row["deployment"], row["availability"], evidence))
    out += ["", headline(doc)]
    unattributed = [row["id"] for row in _rows(doc)
                    if row["state"] == "done" and not row["trusted"]]
    if unattributed:
        out.append("Not counted (done claim without current evidence): "
                   + ", ".join(unattributed))
    return "\n".join(out)


def lines(doc):
    out = [headline(doc), ""]
    for row in _rows(doc):
        note = "" if row["trusted"] or not row.get("evidence_reason") \
            else " - %s" % row["evidence_reason"]
        blocker = " [blocked: %s]" % row["blocker"] if row.get("blocker") else ""
        facts = row.get("missing_facts") or []
        missing = " [needs: %s]" % ", ".join(facts) if facts else ""
        out.append("%s: %s%s%s%s" % (row["id"], label(row["stage"]), note,
                                     blocker, missing))
    unattributed = [row["id"] for row in _rows(doc)
                    if row["state"] == "done" and not row["trusted"]]
    if unattributed:
        out += ["", "Not counted (done claim without current evidence): "
                + ", ".join(unattributed)]
    return "\n".join(out)


def render(doc, shape="table"):
    return table(doc) if shape == "table" else lines(doc)


def projection(doc):
    """The Command Center projection: the same facts, never a second authority."""
    stages = doc.get("stages") or {}
    return {
        "schema": "signature-launch-progress-projection/v1",
        "derived_from": doc.get("schema"),
        "authority": "derived-view",
        "editable": False,
        "launch_id": doc.get("launch_id"),
        "plan_hash": doc.get("plan_hash"),
        "percent": doc["percent"],
        "delivered": doc["delivered"],
        "required": doc["required"],
        "excluded": doc.get("excluded"),
        "stages": {name: list(ids) for name, ids in stages.items()},
        "units": [{
            "id": row["id"],
            "stage": row["stage"],
            "production": row["production"],
            "review": row["review"],
            "deployment": row["deployment"],
            "availability": row["availability"],
            "trusted": row["trusted"],
            "reason": row.get("evidence_reason"),
            "blocker": row.get("blocker"),
            "missing_facts": row.get("missing_facts") or [],
        } for row in _rows(doc)],
        "event": {
            "event_type": "run_progress",
            "percent": doc["percent"],
            "delivered": doc["delivered"],
            "required": doc["required"],
            "stages": {name: len(ids) for name, ids in stages.items()},
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--shape", choices=("table", "lines"), default="table")
    ap.add_argument("--projection", action="store_true")
    args = ap.parse_args(argv)
    progress = _progress()
    doc = progress.report(progress.load(args.file))
    if args.projection:
        print(json.dumps(projection(doc), indent=2, sort_keys=True))
    else:
        print(render(doc, args.shape))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
