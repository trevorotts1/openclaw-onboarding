#!/usr/bin/env python3
"""Generate the actual producer progress fixtures consumed by lane L12.

These are not hand-written examples: every file is written by the real
``progress.py`` producer and the real ``scheduler/model.py`` envelope, with one
fixed clock so the bytes are reproducible.  ``--check`` regenerates in memory
and fails when a committed fixture has drifted.

    python3 shared-utils/signature_launch/scheduler/make_progress_fixtures.py
    python3 shared-utils/signature_launch/scheduler/make_progress_fixtures.py --check

Synthetic local data only: no live sends, no purchases, no credentials.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH_DIR = HERE.parent
OUT_DIR = HERE / "fixtures" / "progress"
STAMP = "2030-01-01T00:00:00Z"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


progress = _load("signature_launch_progress", LAUNCH_DIR / "progress.py")
model = _load("signature_launch_scheduler_model", HERE / "model.py")


def clock():
    return STAMP


def _now():
    return progress._parse_time(STAMP)


def _plan(name):
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


def _record(plan):
    return progress.new_progress(plan, clock=clock)


def _claim(record, uid, owner, ttl_seconds=900):
    decision = progress.claim(record, uid, owner, ttl_seconds=ttl_seconds,
                              now=_now(), clock=clock)
    if not decision.get("claimed"):
        raise SystemExit("fixture claim refused for %s: %s" % (uid, decision))
    return decision


def _complete(record, uid, owner, status, **kwargs):
    result = model.envelope(status, **kwargs)
    if not progress.complete(record, uid, result, owner=owner, clock=clock):
        raise SystemExit("fixture completion refused for %s" % uid)


def build_ai_on():
    """AI requested and wired; one unit still running under a live lease."""
    record = _record(_plan("plan_ai_on.json"))
    _claim(record, "page_landing", "runner-a")
    _complete(record, "page_landing", "runner-a", model.VERIFIED_SUCCESS,
              detail="synthetic local build", artifacts=["artifacts/page_landing.html"])
    _claim(record, "email_pre_launch", "runner-a")
    _complete(record, "email_pre_launch", "runner-a", model.VERIFIED_SUCCESS,
              detail="synthetic local drafts", artifacts=["artifacts/email_pre_launch.json"])
    _claim(record, "auto_ai_reply", "runner-b", ttl_seconds=3600)
    return record


def build_ai_off():
    """AI not requested, no reply unit, every unit verified done."""
    record = _record(_plan("plan_ai_off.json"))
    _claim(record, "page_landing", "runner-a")
    _complete(record, "page_landing", "runner-a", model.VERIFIED_SUCCESS,
              detail="synthetic local build", artifacts=["artifacts/page_landing.html"])
    _claim(record, "email_pre_launch", "runner-a")
    _complete(record, "email_pre_launch", "runner-a", model.VERIFIED_SUCCESS,
              detail="synthetic local drafts", artifacts=["artifacts/email_pre_launch.json"])
    return record


def build_stalled():
    """A normally returned failure plus awaiting facts: partial results kept."""
    record = _record(_plan("plan_stall.json"))
    _claim(record, "page_landing", "runner-a")
    _complete(record, "page_landing", "runner-a", model.FAILED,
              detail="synthetic provider timeout; no artifact")
    _claim(record, "text_doors", "runner-b")
    _complete(record, "text_doors", "runner-b", model.AWAITING_FACTS,
              detail="two answers are missing",
              missing_facts=["sender_name", "reply_to_email"])
    return record


def build_empty():
    """A plan with no units."""
    return _record(_plan("plan_empty.json"))


BUILDERS = {
    "progress-ai-on.json": build_ai_on,
    "progress-ai-off.json": build_ai_off,
    "progress-stalled.json": build_stalled,
    "progress-empty.json": build_empty,
}


def render(name, builder):
    record = builder()
    path = OUT_DIR / name
    record["updated_at"] = STAMP
    record["percent"] = progress.percent(record)
    record["counts"] = progress.counts(record)
    record["empty"] = not record["units"]
    record["stall"] = progress.stall_report(record)["units"]
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail when a committed fixture differs from the producer")
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    drift = []
    for name, builder in sorted(BUILDERS.items()):
        text = render(name, builder)
        path = OUT_DIR / name
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != text:
                drift.append(name)
            continue
        path.write_text(text, encoding="utf-8")
        print(path)
    if drift:
        for name in drift:
            print("DRIFT %s" % name, file=sys.stderr)
        return 1
    if args.check:
        print("progress fixtures: UP TO DATE (%d)" % len(BUILDERS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
