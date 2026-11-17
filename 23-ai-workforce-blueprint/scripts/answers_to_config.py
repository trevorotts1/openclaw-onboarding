#!/usr/bin/env python3
"""answers_to_config.py -- turn the gate's accepted answers into the build's config file.

Reads the gate state (interview-gate-state.json, through interview_gate.py itself),
the live canonical department list, and the owner's recorded department decisions,
then writes the JSON that a non-interactive build consumes
(`build-workforce.py --non-interactive --config-file <this file>`).

Every value comes from an answer or is left empty. This program invents nothing:
no wording is improved, no department is guessed, no value is defaulted to a
plausible-sounding string.

Usage
  answers_to_config.py --state FILE --state-dir DIR --out FILE

Exit codes (interface contract, 01-BUILD-SPEC.md section 2.5)
  0  config written
  3  the gate's complete-check did not pass; nothing written
  1  tooling error (unreadable build state, registry or gate state, naming map or
     department-list script failure, write failure). Never reported as "not complete".

INDUSTRY PACK. When the build state records no industryPack.slug, this program
writes no pack and says so on standard error. record-industry-pack.sh's documented
flags take a blob file (--blob-file) or an already-chosen slug (--slug); none takes
a plain industry string, so the industry answer is never converted into a pack here
and industryPack is never written by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import interview_gate  # noqa: E402  (the gate reads and validates its own state)
import canonical_decline  # noqa: E402  (the one shared owner-decision reader)

# Never an interview decision: build-workforce.load_canonical_floor() filters these
# back out (master-orchestrator is provisioned once, outside the interview, and has
# no decline path), so the buildable, declinable floor is what remains.
NOT_DECLINABLE = ("ceo", "master-orchestrator", "dept-ceo")

# The question whose answer names the team the owner cares about first, and the
# question whose answer is that team's first piece of work.
FOCUS_QUESTION = "focus_dept_1"


def load_build_state(path: Path) -> dict:
    """The build-state object. Absent is {} (no decisions recorded); unreadable is an error."""
    if not path.exists():
        print(f"answers_to_config: no build state at {path}; no department decisions read", file=sys.stderr)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise interview_gate.GateError(f"build state unreadable ({exc}): {path}")
    if not isinstance(data, dict):
        raise interview_gate.GateError(f"build state is not a JSON object: {path}")
    return data


def department_ids() -> list:
    """The live canonical department ids, in the naming map's order, minus the undeclinable ones."""
    script = HERE / "list-canonical-departments.py"
    proc = subprocess.run([sys.executable, "-B", str(script), "--json"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise interview_gate.GateError(
            f"list-canonical-departments.py exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    try:
        data = json.loads(proc.stdout)
    except ValueError as exc:
        raise interview_gate.GateError(f"list-canonical-departments.py printed no JSON ({exc})")
    if not isinstance(data, dict):
        raise interview_gate.GateError("list-canonical-departments.py printed a non-object")
    ids = []
    for group in ("mandatory", "universal_primary_vertical"):
        for dept in data.get(group) or []:
            did = str((dept or {}).get("id") or "").strip()
            if did and did not in ids:
                ids.append(did)
    return [d for d in ids if d not in NOT_DECLINABLE]


def write_json(path: Path, data: dict) -> None:
    """Temp file then rename, mode 0600: a reader never sees half a config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_config(state_path: Path, state_dir: Path, out_path: Path) -> tuple:
    """Write the config. Returns (exit code, number of departments)."""
    registry = interview_gate._registry_default(HERE)
    gate = interview_gate.Gate(registry, state_dir)
    rc, report = gate.cmd_complete_check()
    if rc != 0:
        print(f"answers_to_config: interview not complete; nothing written. {json.dumps(report, ensure_ascii=False)}",
              file=sys.stderr)
        return 3, 0

    answers = {qid: (str(entry.get("value", "")) if isinstance(entry, dict) else "")
               for qid, entry in gate.state["answers"].items()}

    def ans(qid: str) -> str:
        return answers.get(qid, "")

    tools = ans("tools_used").replace("|", ", ")
    state = load_build_state(state_path)
    declined = canonical_decline.canonical_decline_set(state)   # normalized ids

    departments = {}
    for did in department_ids():
        if canonical_decline.norm(did) in declined:
            continue
        departments[did] = {"enabled": True, "activities": "", "kpis": "", "tools": tools, "challenges": ""}

    # The team the owner named as most important gets the two answers about it.
    spec = (gate.by_id.get(FOCUS_QUESTION) or {}).get("teamFrom") or {}
    focus = (spec.get("map") or {}).get(ans(spec.get("question") or ""), spec.get("default") or "")
    if focus in departments:
        departments[focus]["activities"] = ans(FOCUS_QUESTION)
        departments[focus]["kpis"] = ans("revenue_goal_12mo")

    config = {
        "company_name": ans("company_name"),
        "industry": ans("industry"),
        "company_description": ans("what_you_sell"),
        "tools": tools,
        "biggest_challenge": ans("time_drain"),
        "option": "A",
        "departments": departments,
        "_source": "answers_to_config.py",
        "_answersLog": str(state_dir / interview_gate.LOG_NAME),
    }

    if not ((state.get("industryPack") or {}).get("slug")):
        print("answers_to_config: the build state records no industryPack.slug. record-industry-pack.sh "
              "takes --blob-file or --slug and has no flag that accepts a plain industry string, so no "
              "pack was recorded and industryPack is not written here. Record the pack with that script "
              "if the build lane needs it.", file=sys.stderr)

    write_json(out_path, config)
    print(f"answers_to_config: wrote {len(departments)} departments to {out_path}")
    return 0, len(departments)


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn interview answers into the build's config file")
    ap.add_argument("--state", required=True, help="the build state file (.workforce-build-state.json)")
    ap.add_argument("--state-dir", help="the company-discovery folder (default: the platform workspace's)")
    ap.add_argument("--out", required=True, help="output config JSON")
    args = ap.parse_args()
    try:
        state_dir = Path(args.state_dir) if args.state_dir else interview_gate.default_state_dir()
        rc, _ = build_config(Path(args.state), state_dir, Path(args.out))
        return rc
    except interview_gate.GateError as exc:
        print(f"answers_to_config: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"answers_to_config: file error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
