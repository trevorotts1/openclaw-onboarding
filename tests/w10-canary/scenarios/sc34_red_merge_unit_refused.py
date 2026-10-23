#!/usr/bin/env python3
"""sc34_red_merge_unit_refused.py — acceptance row SC-34 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-34, verbatim):
    "Red merge units"

Required result (verbatim):
    "NEGATIVE: a red merge unit is never merged; the merge train refuses it and
     records the failing gate"

The enforcement is the REAL merge train of the tree under test:
``.claude/skills/spec-protocol/tools/merge-train.sh`` (installed copy under
``~/.claude/skills/spec-protocol/tools`` unless an explicit root is named) —
its ``--batch`` contract: one pass over the passed QC units, the gate run once,
a red gate BISECTED until the offending unit is found, that unit undone and
parked with its failing output:

    REPAIR: unit=<branch> reason=batch-gate-red log=<file>

and nothing after it claimed. Merged is only ever "the commit is reachable on
the remote trunk". Fixtures only: two tmp git repos, a bare origin, a tmp
profiled project home, a shell gate command. No real repository, no network,
no provider, no channel.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc34"
TITLE = "a red merge unit is refused by the train with its failing gate recorded"
TOOLS_REL = Path(".claude/skills/spec-protocol/tools")
RED_UNIT = "R1"
GREEN_UNIT = "G1"
RED_CMD = ('if [ -e bad ]; then echo "GATE-FAIL: the red unit file bad is '
           'present" >&2; exit 1; fi')


def _real_home():
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


def resolve_tools(args):
    """The spec-protocol tools dir under test.

    An explicitly named --tools-root is AUTHORITATIVE: if it holds no
    merge-train.sh the harness exits 2 and names the path. It never falls back
    to the installed copy, which would let the row pass against a revision the
    operator did not name.
    """
    if args.tools_root:
        named = Path(args.tools_root).expanduser()
        if (named / "merge-train.sh").is_file():
            return named
        print("TOOLING: --tools-root %s contains no merge-train.sh; refusing to "
              "fall back to a different copy" % named)
        raise SystemExit(2)
    cands = []
    env = os.environ.get("SPEC_PROTOCOL_TOOLS_ROOT")
    if env:
        # Same authority rule as the flag: a named tools root without the
        # expected script must refuse rather than fall through.
        named_env = Path(env).expanduser()
        if not (named_env / "merge-train.sh").is_file():
            print("TOOLING: SPEC_PROTOCOL_TOOLS_ROOT=%s contains no merge-train.sh; "
                  "refusing to fall back to a different copy" % named_env)
            raise SystemExit(2)
        cands.append(named_env)
    cands.append(_real_home() / TOOLS_REL)
    cands.append(Path(args.tree) / TOOLS_REL)
    for c in cands:
        if (c / "merge-train.sh").is_file():
            return c
    print("TOOLING: merge-train.sh not found; looked at %s"
          % ", ".join(str(c) for c in cands))
    raise SystemExit(2)


def child_env(base):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "OPENCLAW_HOME")}
    env.update({
        "HOME": str(Path(base) / "home"),
        "GIT_CONFIG_GLOBAL": str(Path(base) / "gitconfig"),
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "sc34", "GIT_AUTHOR_EMAIL": "sc34@example.invalid",
        "GIT_COMMITTER_NAME": "sc34",
        "GIT_COMMITTER_EMAIL": "sc34@example.invalid",
    })
    Path(env["GIT_CONFIG_GLOBAL"]).write_text("")
    return env


def git(env, cwd, *argv, timeout=180):
    return subprocess.run(["git"] + list(argv), cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=timeout)


def ledger(units):
    out = []
    for unit in units:
        out.append("2026-01-01T00:00:00Z | QC-RECORD unit=%s judge=j bar=b | "
                   "writer=ledger.sh" % unit)
        out.append("bar-fetch=f")
        out.append("verdict=PASS")
        out.append("outcome=PASSED")
        out.append("blind=yes model-independence=PROVEN self-qc=no")
        out.append("provenance=STRIPPED")
        out.append("")
    return "\n".join(out)


def fixture(base, label, units):
    """A bare origin, a clone with one branch per unit, and a profiled home."""
    env = child_env(base)
    root = Path(base) / label
    origin = root / "origin.git"
    repo = root / "r"
    project = root / "p"
    (root).mkdir(parents=True)
    git(env, root, "init", "-q", "--bare", str(origin))
    git(env, root, "init", "-q", "-b", "main", str(repo))
    (repo / "f").write_text("base\n")
    git(env, repo, "add", "f")
    git(env, repo, "commit", "-qm", "base")
    git(env, repo, "remote", "add", "origin", str(origin))
    git(env, repo, "push", "-q", "origin", "main")
    (project / "state" / "spec-protocol").mkdir(parents=True)
    (project / ".spec-protocol.json").write_text(
        json.dumps({"documents": {"state": "state/state.json"}}) + "\n")
    (project / "state" / "repo-anchor.json").write_text(
        json.dumps({"repoRoot": str(repo), "source": "existing"}) + "\n")
    (project / "state" / "spec-protocol" / "LEDGER.md").write_text(
        ledger([u for u, _ in units]))
    for name, files in units:
        git(env, repo, "checkout", "-q", "-b", "unit/" + name, "main")
        for filename, content in files.items():
            (repo / filename).write_text(content)
        git(env, repo, "add", "-A")
        git(env, repo, "commit", "-qm", name)
        git(env, repo, "checkout", "-q", "main")
    return env, repo, project, origin


def batch(tools, env, project):
    try:
        p = subprocess.run(["bash", str(tools / "merge-train.sh"),
                            str(project), "--batch"],
                           capture_output=True, text=True, env=env, timeout=600)
        return p.returncode, p.stdout + p.stderr, ""
    except subprocess.TimeoutExpired:
        return None, "", "merge-train.sh exceeded 600s"


def line_for(out, prefix):
    return next((l for l in out.splitlines() if l.startswith(prefix)), "")


def scenario(tools, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC34 %s — merge-train %s%s"
          % (TITLE, tools / "merge-train.sh",
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    with H.Scratch() as tmp:
        base = Path(tmp)
        (base / "home").mkdir()
        units = [(RED_UNIT, {"bad": "red\n"}), (GREEN_UNIT, {"good_r": "green\n"})]
        env, repo, project, _origin = fixture(base, "main", units)
        tc = RED_CMD
        if "gate_never_red" in muts:
            tc = "true"
        elif "gate_always_red" in muts:
            tc = "exit 1"
        rc, out, err = batch(tools, dict(env, MERGE_TRAIN_TEST_CMD=tc), project)

        red_branch = "unit/" + RED_UNIT
        keep = git(env, repo, "rev-parse", "--verify", "--quiet",
                   "refs/heads/" + red_branch)
        ancestor = git(env, repo, "merge-base", "--is-ancestor",
                       red_branch, "origin/main")
        red_file = git(env, repo, "cat-file", "-e", "origin/main:bad")
        merged_red = line_for(out, "MERGED: unit=%s " % red_branch)
        c.check("sc34:red-unit-never-merged",
                red_file.returncode != 0
                and ancestor.returncode != 0
                and merged_red == ""
                and keep.returncode == 0,
                "observed origin/main:bad present=%r, %s is an ancestor of "
                "origin/main=%r, a MERGED line for it=%r, its local branch "
                "kept=%r, run error=%r"
                % (red_file.returncode == 0, red_branch,
                   ancestor.returncode == 0, merged_red, keep.returncode == 0,
                   err))

        repair = line_for(out, "REPAIR: unit=%s reason=batch-gate-red log="
                          % red_branch)
        c.check("sc34:red-unit-refused-with-the-named-gate",
                rc == 3 and repair != "",
                "observed exit=%r (want 3, stopped) and the repair line=%r"
                % (rc, repair))

        log = repair.split("log=", 1)[1].strip() if "log=" in repair else ""
        if "gate_log_dropped" in muts and log:
            Path(log).unlink(missing_ok=True)
        park_rows = []
        parked = Path(project) / "state" / "spec-protocol" / "merge-train" \
            / "parked.tsv"
        if parked.is_file():
            park_rows = [l for l in parked.read_text().splitlines()
                         if red_branch in l]
        log_text = Path(log).read_text() if log and Path(log).is_file() else ""
        c.check("sc34:failing-gate-recorded",
                bool(log) and Path(log).is_file()
                and "GATE-FAIL" in log_text
                and any("red" in l for l in park_rows),
                "observed repair log=%r exists=%r containing the gate's own "
                "failure text=%r; parked.tsv rows naming %s=%r"
                % (log, bool(log) and Path(log).is_file(),
                   "GATE-FAIL" in log_text, red_branch, park_rows))

        green_file = git(env, repo, "cat-file", "-e", "origin/main:good_r")
        merged_green = line_for(out, "MERGED: unit=unit/%s " % GREEN_UNIT)
        c.check("sc34:green-unit-still-merged",
                merged_green != "" and green_file.returncode == 0,
                "observed a MERGED line for unit/%s=%r and origin/main:good_r "
                "present=%r — the red unit was isolated, not the batch"
                % (GREEN_UNIT, merged_green, green_file.returncode == 0))

        cenv, crepo, cproject, _ = fixture(base, "control",
                                           [(RED_UNIT, {"bad": "red\n"})])
        crc, cout, cerr = batch(tools, dict(cenv, MERGE_TRAIN_TEST_CMD="true"),
                                cproject)
        c_file = git(cenv, crepo, "cat-file", "-e", "origin/main:bad")
        c_merged = line_for(cout, "MERGED: unit=unit/%s " % RED_UNIT)
        c.check("sc34:control-a-green-gate-merges-the-same-unit",
                crc == 0 and c_merged != "" and c_file.returncode == 0,
                "control with the gate green: observed exit=%r, a MERGED line "
                "for unit/%s=%r, origin/main:bad present=%r — the refusal is "
                "the red gate, not a blanket refusal, run error=%r"
                % (crc, RED_UNIT, c_merged, c_file.returncode == 0, cerr))
    return c


MUTATIONS = {
    # The gate never goes red, so the red unit merges and nothing is recorded.
    "gate_never_red": ["sc34:red-unit-never-merged",
                       "sc34:red-unit-refused-with-the-named-gate",
                       "sc34:failing-gate-recorded"],
    # The gate is red for every unit, so the green unit is parked too.
    "gate_always_red": ["sc34:green-unit-still-merged"],
    # The named failing-gate log was deleted after the refusal.
    "gate_log_dropped": ["sc34:failing-gate-recorded"],
}


def selftest(tools):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(tools, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on every defect" if ok
                             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = H.add_args(description=__doc__)
    ap.add_argument("--tools-root", default=None,
                    help="the spec-protocol tools dir under test")
    ap.add_argument("--dry-run", action="store_true")
    if argv and argv[0] == "selftest":
        args = ap.parse_args(argv[1:])
        return selftest(resolve_tools(args))
    args = ap.parse_args(argv)
    result = scenario(resolve_tools(args))
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / ("%s.scenario.json" % ROW)
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
