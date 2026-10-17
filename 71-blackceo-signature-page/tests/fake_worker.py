#!/usr/bin/env python3
"""Fake swarm worker for tests/test_swarm_runner.py.

Driven by <run_dir>/private/test-scenario.json:
  {"items": {"IMG-001": ["bad-content", "ok"]},
   "stages": {"desktop-wireframe": ["ok"]}}
Behaviors are consumed per attempt of that stage+item+kind. Work behaviors:
ok, bad-content, exit3, sleep, gen-ok, gen-transport-fail, gen-poll-ok,
gen-success-exit2. Review behaviors: review-ok (default), review-fail.

The worker mimics a real one: it reads its brief, writes only artifacts (and,
for the generation stage, the operator bookkeeping a real Skill 74 operator
writes: the kie74 task receipt and the stage receipt's cost/transport blocks),
prints "SESSION: <id>", and exits with the lane-signaling code.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
LONG_NOTE = "Checked against the artifact bytes and the stage rubric line by line."


def bump(run_dir, name):
    path = run_dir / "private" / "attempts" / f"{name}.count"
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(path.read_text()) + 1 if path.exists() else 1
    path.write_text(str(n))
    return n


def read_brief_outputs(brief_path):
    outs, capture = [], False
    for line in Path(brief_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## Expected outputs"):
            capture = True
            continue
        if capture:
            if line.startswith("## "):
                break
            if line.startswith("- "):
                outs.append(line[2:].strip())
    return outs


def write_artifact(run_dir, rel, bad=False):
    path = run_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith(".png"):
        path.write_bytes(PNG_1PX)
    elif rel.endswith(".json"):
        path.write_text("{}", encoding="utf-8")
    elif rel.endswith(".txt"):
        path.write_text("BAD prompt, no marker\n" if bad else "OK prompt body\n",
                        encoding="utf-8")
    else:
        path.write_text("stub OK\n", encoding="utf-8")


def gen_bookkeeping(run_dir, item, session, state, artifact_rel, bump_create):
    num = "".join(ch for ch in item if ch.isdigit()) or "001"
    task_id = f"task-{num}"
    if bump_create:
        bump(run_dir, "createtask")
    kdir = run_dir / "receipts" / "kie74"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / f"{task_id}.json").write_text(json.dumps({
        "provider": "kie", "adapter": "74-kie-live-adapter",
        "adapter_mode": "active", "backend": "native-live",
        "model_id": "gpt-image-2", "task_id": task_id, "state": state,
        "saved_paths": [artifact_rel], "warnings": [], "data": {}}),
        encoding="utf-8")
    if state == "success":
        receipt = {"stage": "image-generation-qc", "status": "pass",
                   "author_agent": "fake-operator", "author_session": session,
                   "started_at": "2026-10-13T10:00:00+00:00",
                   "finished_at": "2026-10-13T10:30:00+00:00", "artifacts": [],
                   "cost": {"provider": "kie", "credits_before": 100.0,
                            "credits_after": 96.0},
                   "transport": {"skill": "74-kie-live-adapter",
                                 "policy": "66-kie-image", "mode": "active",
                                 "tasks": [{"file": artifact_rel,
                                            "task_id": task_id,
                                            "preflight_ok": True,
                                            "budget_exit": 0,
                                            "model_id": "gpt-image-2",
                                            "model_source": "latest-family",
                                            "requested_ratio": "16:9",
                                            "generated_ratio": "16:9"}]}}
        path = run_dir / "private" / "receipts" / "image-generation-qc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt), encoding="utf-8")
        write_artifact(run_dir, "image-generation-qc/image-qc.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--item", required=True)
    ap.add_argument("--kind", required=True)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--note", required=True)
    args = ap.parse_args()
    run_dir = Path(args.run)
    attempt = bump(run_dir, f"{args.stage}-{args.item}-{args.kind}")
    session = f"fake-{args.stage}-{args.item}-{args.kind}-{attempt}"
    print(f"SESSION: {session}")
    sys.stdout.flush()
    scenario = {}
    spath = run_dir / "private" / "test-scenario.json"
    if spath.exists():
        scenario = json.loads(spath.read_text(encoding="utf-8"))
    table = scenario.get("items", {}) if args.item != "stage" \
        else scenario.get("stages", {})
    behaviors = table.get(args.item if args.item != "stage" else args.stage, [])
    behavior = behaviors[attempt - 1] if attempt - 1 < len(behaviors) else None

    if args.kind == "review":
        behavior = behavior or "review-ok"
        scores = {"criteria": {"quality": {"score": 10, "note": LONG_NOTE}},
                  "verdict": "pass"}
        if behavior == "review-fail":
            scores["verdict"] = "fail"
            scores["defects"] = "The artifact misses the rubric on quality."
        Path(str(args.note) + ".scores.json").write_text(
            json.dumps(scores), encoding="utf-8")
        return 0

    behavior = behavior or "ok"
    if behavior == "sleep":
        time.sleep(30)
        return 0
    if behavior == "exit3":
        return 3
    outputs = read_brief_outputs(args.brief)
    if args.stage == "image-generation-qc":
        artifact_rel = outputs[0] if outputs else None
        if behavior == "gen-transport-fail":
            gen_bookkeeping(run_dir, args.item, session, "submitted",
                            artifact_rel, bump_create=True)
            return 2
        if behavior == "gen-success-exit2":
            write_artifact(run_dir, artifact_rel)
            gen_bookkeeping(run_dir, args.item, session, "success",
                            artifact_rel, bump_create=True)
            return 2
        if behavior == "gen-poll-ok":
            write_artifact(run_dir, artifact_rel)
            gen_bookkeeping(run_dir, args.item, session, "success",
                            artifact_rel, bump_create=False)
            return 0
        # gen-ok
        write_artifact(run_dir, artifact_rel)
        gen_bookkeeping(run_dir, args.item, session, "success",
                        artifact_rel, bump_create=True)
        return 0
    t0 = time.time()
    for rel in outputs:
        write_artifact(run_dir, rel, bad=(behavior == "bad-content"))
    if args.stage == "image-inventory-prompts":
        time.sleep(0.4)  # hold the slot so the fan-out test can measure overlap
    # Record a concurrency interval for the fan-out test.
    with open(run_dir / "private" / "attempts" / "intervals.jsonl", "a",
              encoding="utf-8") as f:
        f.write(json.dumps({"item": args.item, "kind": args.kind,
                            "start": t0, "end": time.time()}) + "\n")
    if behavior == "bad-content":
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
