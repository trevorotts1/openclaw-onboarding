#!/usr/bin/env python3
"""run_a_rows.py — execution driver for the Skill 75 acceptance rows A01–A12.

WHY THIS FILE EXISTS
  W10-U1 must run the A-rows the moment the canary batch lands. This driver holds
  the exact command for every row, runs one row at a time in a throwaway
  environment, captures the output verbatim, and decides PASS from the exit code
  AND the row's own check lines. It cannot report a pass from text alone.

ROW CLASSES
  executable      A01 A02 A03 A04 A05 A07 A08 A09 A12  =  73/100 weighted points
  BLOCKED_OWNER   A06 (real song file), A10 (graph mutation), A11 (paid render
                  + live channel) = 27/100. There is no code path that executes
                  these three; they are written as BLOCKED_OWNER receipts.

MODES
  --dry-run (default)  evidence_class "DRY"; acceptance_usable is ALWAYS false.
                       Harnesses that support --dry-run get it; the rest still
                       execute, but the receipt is DRY because the tree/pin are
                       not the landed acceptance vector.
  --real               requires --expect-head; the repo head must equal it, the
                       tree must be clean, and the source vector's
                       openclaw-onboarding revision must be an ancestor of that
                       head whose only post-pin canary change is the vector
                       file itself (a stale pin is BLOCKED_VECTOR, never a
                       pass). Exact equality is still accepted.

VERDICTS (fail-closed)
  PASS            rc==0 AND every required check line present AND the row's
                  summary/count assertions hold AND no [FAIL]/forbidden marker.
                  Only producible in --real mode.
  PASS_DRY        same evidence, but the run was --dry-run. NOT acceptance.
  FAIL            step exit code != 0 (never a pass; failure_class CONTENT/ENV/
                  TIMEOUT names whether it looks environmental).
  DISAGREEMENT    exit code 0 but the output contradicts it — a [FAIL] line, a
                  missing required assertion, a wrong total, or a forbidden
                  marker (BLOCKED_A11 / REFUSED / TOOLING: / Traceback). The
                  runner fails closed rather than believe the exit code.
  BLOCKED_OWNER   owner-gated row; never executed.
  BLOCKED_HARNESS harness/tool/manifest absent at this head.
  BLOCKED_ENV     required checkout absent, real mode without --expect-head,
                  dirty tree in --real, timeout, or (A01) npm missing / its
                  disposable install failing. A01 never touches the pinned 999
                  checkout: it copies workflow-guard into the row's TMPDIR,
                  installs the declared dependency there, and runs in the copy.
  BLOCKED_VECTOR  pin unusable: vector unpinned, pin not a commit, pin not an
                  ancestor of head, or a canary file other than
                  source-vector.json changed after the pin.
  BLOCKED_HEAD    --real but repo head != --expect-head.
  BLOCKED_A11     harness exited 4 with BLOCKED_A11 (live artifact required).

RECEIPT SCHEMA  blackceo.skill75.a-row-runner/v1
  work/S75-W10-U1/RECEIPTS/<row>.json
  {
    "schema", "row", "weight", "title", "mode", "verdict", "reason",
    "evidence_class",            # DRY | REAL | NONE
    "acceptance_usable",         # true only for REAL + PASS
    "head_sha",                  # repo under test
    "vector": {"path","pinned","pinned_at","revision_openclaw_onboarding",
               "revision_999","revision_matches_head","pin_is_ancestor",
               "pin_to_head_diff","revisions":{...}},
    "tree": {"path","head_sha","dirty"},
    "nine_tree": {"path","head_sha","revision_matches_vector"} | null,
    "command",                   # shell-quoted, verbatim
    "argv",                      # exact argv of the row (single step) or per step
    "cwd", "env",                # isolated HOME/TMPDIR; OPENCLAW_HOME unset
    "exit_code", "stdout", "stderr",
    "stdout_sha256", "stderr_sha256", "duration_ms",
    "steps": [{"index","command","argv","cwd","exit_code","stdout","stderr",
               "duration_ms","env"}],
    "assertions": {"pass_lines","fail_lines","summary_line","expected_total",
                   "observed_total","group","missing_required",
                   "missing_required_re","forbidden_present","disagreement"},
    "installer_rc": int|null,
    "installer_rc_note": str,
    "limitations": [str],
    "timestamp", "runner": {"path","sha256","head_sha"}
  }

  stdout/stderr are verbatim. For a multi-step row the top-level stdout joins
  the steps with a "===== step N =====" banner; each step's own stdout/stderr
  in "steps" is untouched.

EXIT CODES
  0 all targeted rows PASS/PASS_DRY or declared owner gates
  1 any FAIL or DISAGREEMENT
  2 tooling (bad args, unreadable vector)
  3 any BLOCKED_* that is not an owner gate
  0 on --self-test only when every self-check holds.

SAFETY  stdlib only; local rows only; no network, no paid provider, no channel
  send, no client box, no real config root. Every harness runs in a scratch
  HOME/TMPDIR that is deleted afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "blackceo.skill75.a-row-runner/v1"
FROZEN_WEIGHTS = {
    "A01": 8, "A02": 8, "A03": 8, "A04": 8, "A05": 7, "A06": 7,
    "A07": 8, "A08": 8, "A09": 8, "A10": 6, "A11": 14, "A12": 10,
}
CORE_REL = Path("75-drama-song-ad-factory") / "scripts" / "core"
NINE_HARNESS = ".claude/skills/hook-skill/hooks/workflow-guard/test_u3_canaries.py"
A12_HARNESS = Path("tests/w10-canary/scenarios/a12_runtime_proof.py")
A12_MANIFEST_GLOB = "clean-install-*.manifest.json"
A12_REQUIRED = [
    "loaded-source proof: OK",
    "loaded-module proof: OK",
    "both distributions present = True",
    "a12_creditable = True",
]
# The loaded-module line names the module the child interpreter actually
# imported and the digest of the bytes it read. A digest-only proof, a stub, or
# a skipped load cannot print it. The two side counts are written as
# number-equals-denominator so an extra manifest in A08's dir cannot turn a
# clean run into a missing-string FAIL.
A12_REQUIRED_RE = [
    r"loaded-module proof: OK — loaded lyric_timing from .+lyric_timing\.py; "
    r"sha256 [0-9a-f]{12} matches the manifest",
    r"^\[A12\] record: ([1-9]\d*)/\1 side\(s\) proven;",
    r"^\[A12\] check: ([1-9]\d*)/\1 side\(s\) clean$",
]
A12_FORBIDDEN = ["MISMATCH:", "NOT RECORDED", "DISAGREE",
                 "a12_creditable = False"]

ENV_STRIP = ("OPENCLAW_HOME", "PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS",
             "PYTHONSTARTUP", "S75_TREE", "S75_NINE_ROOT")
ENV_ERROR_MARKERS = (
    # most specific first: ERR_MODULE_NOT_FOUND contains MODULE_NOT_FOUND
    "ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND", "Cannot find module",
    "command not found",
    "No such file or directory", "ENOENT", "Permission denied",
    "Address already in use", "No space left on device", "EACCES",
    # A child process that produced no parseable output is a tooling symptom,
    # not this row's contract. Verdict stays FAIL either way.
    "JSONDecodeError", "ERR_MODULE_NOT_FOUND",
    # npm install failures (offline, registry, permissions) are BLOCKED_ENV.
    "EAI_AGAIN", "ENOTFOUND", "ETIMEDOUT", "ECONNREFUSED", "ECONNRESET",
    "npm ERR!", "registry.npmjs.org",
)

LIMITATION_COMMON = (
    "Local row only: no network, no paid provider, no channel send, no client box.",
    "HOME and TMPDIR are fresh per row and deleted after the row; OPENCLAW_HOME "
    "and PYTHONPATH are unset for the row.",
    "The runner decides PASS from exit code AND its own required-assertion / "
    "summary-count checks; text that says PASS with a non-zero exit is FAIL.",
)


class Blocked(Exception):
    def __init__(self, kind, reason):
        Exception.__init__(self, reason)
        self.kind = kind
        self.reason = reason


class Step(object):
    def __init__(self, argv, cwd, env=None, note="", blocked_on_failure=None):
        self.argv = [str(a) for a in argv]
        self.cwd = str(cwd)
        self.env = dict(env or {})
        self.note = note
        self.blocked_on_failure = blocked_on_failure


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def parse_installer_rcs(text):
    """Every installer rc the canary printed, in order.

    The canary formats the rc as a list — "installer rc=[0, 1]", one entry per
    installer command it ran — so a bare `installer rc=(\\d+)` never matches.
    Both forms are read here; callers take the last value as installer_rc.
    """
    groups = re.findall(r"installer rc=(\[[\d,\s]*\]|\d+)", text)
    return [int(n) for g in groups for n in re.findall(r"\d+", g)]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_out(path, *args):
    try:
        r = subprocess.run(["git", "-C", str(path)] + list(args),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def git_rc(path, *args):
    """Run git and keep the return code. (rc, stdout, stderr).

    git_out() collapses every failure to None, which cannot distinguish "no
    output" from "the command failed". The pin gate needs that distinction:
    a nonzero rc must never be read as an empty result. rc None means the
    subprocess could not be started at all.
    """
    try:
        r = subprocess.run(["git", "-C", str(path)] + list(args),
                           capture_output=True, text=True, timeout=60)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, "", "%s: %s" % (type(exc).__name__, exc)
    return r.returncode, r.stdout or "", r.stderr or ""


def tree_state(path):
    return {"path": str(path),
            "head_sha": git_out(path, "rev-parse", "HEAD"),
            "dirty": bool(git_out(path, "status", "--porcelain"))}


def load_vector(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            v = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read vector %s: %s" % (path, exc))
    repos = v.get("repositories") or {}
    return {
        "path": str(path),
        "pinned": v.get("pinned") is True,
        "pinned_at": v.get("pinned_at"),
        "raw": v,
        "revision_openclaw_onboarding":
            (repos.get("openclaw-onboarding") or {}).get("revision"),
        "revision_999": (repos.get("999-setup") or {}).get("revision"),
        "revisions": {k: (val or {}).get("revision")
                      for k, val in repos.items()},
    }


# --------------------------------------------------------------------------
# row plans — the exact command per A-ROW-RUNBOOK.md
# --------------------------------------------------------------------------

def plan_a01(ctx, mode, sandbox):
    """A01 runs on a DISPOSABLE copy of the 999 tree, never the protected clone.

    The 999 checkout may be a symlink into the protected persist-home tree and
    is read-only by standing rule, so the row copies the workflow-guard subtree
    into this row's TMPDIR, installs its declared dependencies there with the
    npm cache inside the same temp tree, and executes the runbook command in the
    copy. A missing npm, a failed/offline install, or a failed copy is
    BLOCKED_ENV naming npm; it is never a pass.
    """
    nine = ctx["nine_root"]
    if not nine:
        raise Blocked("BLOCKED_ENV", "no 999-setup checkout; pass --nine-root")
    guard_rel = Path(NINE_HARNESS).parent
    src = Path(nine) / guard_rel
    if not (src / "test_u3_canaries.py").is_file():
        raise Blocked("BLOCKED_HARNESS", "missing %s in %s" % (NINE_HARNESS, nine))
    npm = shutil.which("npm")
    if not npm:
        raise Blocked("BLOCKED_ENV",
                      "npm is not on PATH; A01 needs a disposable npm install "
                      "of the workflow-guard dependencies (acorn)")
    dest_repo = Path(sandbox["tmpdir"]) / "nine-copy"
    dest_guard = dest_repo / guard_rel
    # The canary also drives .claude/skills/spec-protocol/tools/swarm-plan.mjs
    # (via ROOT.parent x3), so the disposable copy carries that subtree too.
    needed = [guard_rel, Path(".claude/skills/spec-protocol")]
    try:
        for rel in needed:
            src_dir = Path(nine) / rel
            if not src_dir.is_dir():
                raise Blocked("BLOCKED_HARNESS",
                              "999 tree is missing %s, which the A01 canary "
                              "drives" % rel)
            shutil.copytree(src_dir, dest_repo / rel)
    except Blocked:
        raise
    except OSError as exc:
        raise Blocked("BLOCKED_ENV",
                      "cannot provision the disposable 999 copy: %s" % exc)
    cache = Path(sandbox["tmpdir"]) / "npm-cache"
    return [
        Step([npm, "install", "--no-audit", "--no-fund", "--prefer-offline"],
             cwd=dest_guard,
             env={"npm_config_cache": str(cache),
                  "npm_config_update_notifier": "false"},
             note="disposable npm install (acorn)",
             blocked_on_failure="BLOCKED_ENV"),
        Step(["python3", "-m", "pytest", NINE_HARNESS, "-q"],
             cwd=dest_repo,
             env={"PYTEST_ADDOPTS": "-p no:cacheprovider"}),
    ]


def _multirun(ctx, mode, sandbox):
    argv = ["python3", "tests/w10-canary/multi_run_canary.py",
            "--vector", str(ctx["vector_path"]),
            "--core-root", str(ctx["tree"]),
            "--out", str(ctx["artifacts"])]
    if mode == "dry":
        argv.append("--dry-run")
    return [Step(argv, cwd=ctx["tree"])]


def _scenario(name):
    def plan(ctx, mode, sandbox):
        core = Path(ctx["tree"]) / CORE_REL
        if not (core / "state_store.py").is_file():
            raise Blocked("BLOCKED_HARNESS", "no Skill 75 core at %s" % core)
        argv = ["python3", "tests/w10-canary/scenarios/%s" % name,
                "--core-root", str(core), "--out", str(ctx["artifacts"])]
        return [Step(argv, cwd=ctx["tree"])]
    return plan


def plan_a08(ctx, mode, sandbox):
    # One invocation with --dist both: the canary prints ONE aggregate
    # "real: N/M checks passed", which is what this row's min_total=7 floor
    # describes. Two per-dist processes print two 6/6 summaries, so the last
    # one read by evaluate() can never clear the floor.
    argv = ["python3", "tests/w10-canary/clean_install_canary.py",
            "--vector", str(ctx["vector_path"]),
            "--dist", "both", "--out", str(ctx["artifacts"])]
    # The canary resolves each distribution's source checkout itself: vector
    # path, then --repo-root, then a sibling directory. A runner temp tree has
    # no sibling, so without these the row refuses SOURCE_CHECKOUT_UNRESOLVED
    # before any installer runs and reports no installer_rc.
    argv += ["--repo-root", "openclaw-onboarding=%s" % ctx["tree"]]
    if ctx.get("nine_root"):
        argv += ["--repo-root", "999-setup=%s" % ctx["nine_root"]]
    # A12 consumes these manifests AND hashes/imports the installed trees they
    # point at, so the trees must survive this row's exit. Without --keep the
    # canary deletes its sandbox and every A08 manifest is left dangling.
    argv.append("--keep")
    if mode == "dry":
        argv.append("--dry-run")
    else:
        # The canary defaults sandbox_base to --out when --sandbox-base is
        # absent, so the retained trees land under the ROW's artifacts dir, not
        # under /tmp. Print the real location: an operator who cleans /tmp finds
        # nothing and ~1.2 GB rots in the receipts tree.
        print("[A08] keeping install trees under %s/skill75-repair-"
              "SFR-007-canary-* (~1.2 GB across both dists). A12 reads them; "
              "delete by hand." % ctx["artifacts"], flush=True)
    return [Step(argv, cwd=ctx["tree"], note="dist=both")]



def _require_a08_trees(manifests):
    """Refuse before the harness runs if A08's kept trees are gone.

    A12 hashes the bytes at each manifest's installed_path and imports the
    module from that tree. A manifest whose tree was deleted (an A08 run
    without --keep) would otherwise surface as an obscure harness error after
    a step had already been launched, so this fires first and names the path.
    """
    missing = []
    for m in manifests:
        try:
            data = json.loads(Path(m).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            missing.append("%s (unreadable: %s)" % (m, exc))
            continue
        ip = data.get("installed_path")
        if not ip or not Path(ip).is_dir():
            missing.append("%s -> %s" % (m, ip))
    if missing:
        raise Blocked(
            "BLOCKED_HARNESS",
            "A08 installed tree missing (that A08 run deleted its sandbox, i.e. "
            "ran without --keep): %s. Rerun A08 with --keep; A12 hashes and "
            "imports the tree at installed_path." % "; ".join(missing))


def plan_a12(ctx, mode, sandbox):
    tree = Path(ctx["tree"])
    tool = tree / A12_HARNESS
    if not tool.is_file():
        raise Blocked("BLOCKED_HARNESS",
                      "missing %s (A12 harness not landed at this head)" % tool)
    # A08 writes its manifests into its OWN row artifacts dir, i.e.
    # <receipts>/artifacts/A08/clean-install-<dist>.manifest.json.
    a08 = Path(ctx["artifacts"]).parent / "A08"
    manifests = sorted(a08.glob(A12_MANIFEST_GLOB))
    if not manifests:
        raise Blocked("BLOCKED_HARNESS",
                      "A08 wrote no %s into %s; A12 consumes A08's clean-install "
                      "manifest and cannot pass without it"
                      % (A12_MANIFEST_GLOB, a08))
    # The trees those manifests point at must still exist; refuse by name
    # rather than letting the harness fail obscurely after launch.
    _require_a08_trees(manifests)
    # Every manifest A08 produced, not just the last: `record` credits the row
    # only when BOTH distributions are present, and `check --side installed`
    # proves each manifest's own side. Passing one manifest would cap the row
    # at 1/2 sides by construction.
    sel = []
    for m in manifests:
        sel += ["--manifest", str(m)]
    return [
        Step(["python3", str(tool), "record"] + sel
             + ["--out", str(ctx["artifacts"])],
             cwd=tree, note="record loaded-source proof"),
        Step(["python3", str(tool), "check"] + sel
             + ["--side", "installed"],
             cwd=tree, note="check installed digests"),
    ]


A02_TERMINAL = [
    "terminal:all-parked never delivered",
    "terminal:parked stage cannot be promoted to COMPLETE",
    "terminal:all-failed never delivered",
    "terminal:failed stage cannot be promoted to COMPLETE",
    "terminal:empty run has no complete stages",
    "terminal:empty/unknown stage = actionable state error",
    "terminal:mixed run is genuinely mixed",
    "terminal:mixed never reports all-complete",
    "terminal:mixed failed member cannot be promoted",
]
A03_CONTINUATION = [
    "continuation:event enqueues one pending row",
    "continuation:replayed event adds no second row",
    "continuation:restart finds the same pending work",
    "continuation:restart resumes with the original attempt ordinal",
    "continuation:second restart claims nothing (exactly once)",
    "continuation:event ordinals enqueue then resume",
    "continuation:resume event carries the same identity",
]


def rows():
    R = []

    R.append(dict(
        id="A01", weight=8,
        title="workflow-guard harness against the 999 tree at pin",
        plan=plan_a01,
        required_real=["passed"], required_dry=["passed"],
        required_re_real=[r"^\d+ passed in [\d.]+s"],
        required_re_dry=[r"^\d+ passed in [\d.]+s"],
        forbidden_real=[r"\bfailed\b", r"\berrors?\b", r"\bERROR\b", r"FAILED"],
        forbidden_dry=[r"\bfailed\b", r"\berrors?\b", r"\bERROR\b", r"FAILED"],
        summary_re=None, expected_total=None,
        min_passed=12,
        notes=["Runbook command verbatim, executed in a DISPOSABLE copy of the "
               "999 tree under this row's TMPDIR (the pinned checkout may be a "
               "symlink into the protected persist-home tree and is never "
               "written to). The copy's workflow-guard dependencies are "
               "installed with npm using a cache inside the same temp tree.",
               "Missing npm, a failed or offline npm install, or a failed copy "
               "is BLOCKED_ENV naming npm, never a pass.",
               "The 999 workflow-guard shells out to node; a missing node "
               "module surfaces as an empty subprocess stdout and is recorded "
               "as failure_class ENV, never as a pass and never as a contract "
               "red. The harness never reads the child's stderr, so it hides "
               "its own cause."],
    ))

    R.append(dict(
        id="A02", weight=8,
        title="multi-run terminal non-delivery + ILLEGAL_TRANSITION refusals",
        plan=_multirun,
        required_real=A02_TERMINAL, required_dry=A02_TERMINAL,
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^(dry-run|real): (\d+)/(\d+) checks passed$",
        expected_total=None, min_total=31,
        group={"prefix": "terminal:", "count": 9},
        min_occurrences={"ILLEGAL_TRANSITION": 3},
    ))

    R.append(dict(
        id="A03", weight=8,
        title="event continuation: enqueue once, replay, restart ordinal",
        plan=_multirun,
        required_real=A03_CONTINUATION, required_dry=A03_CONTINUATION,
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^(dry-run|real): (\d+)/(\d+) checks passed$",
        expected_total=None, min_total=31,
        group={"prefix": "continuation:", "count": 7},
    ))

    R.append(dict(
        id="A04", weight=8, title="script/lyrics/hook versioned visibility",
        plan=_scenario("a04_versioned_visibility.py"),
        required_real=[
            "a04:presentation-displays-both-revisions",
            "a04:unchanged-script-keeps-revision",
            "a04:stale-revision-not-displayed",
            "a04:hook-change-advances-lyrics-revision",
            "a04:changed-hook-displayed",
            "a04:stale-hook-not-displayed"],
        required_dry=[
            "a04:presentation-displays-both-revisions",
            "a04:unchanged-script-keeps-revision",
            "a04:stale-revision-not-displayed",
            "a04:hook-change-advances-lyrics-revision",
            "a04:changed-hook-displayed",
            "a04:stale-hook-not-displayed"],
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^a04: (\d+)/(\d+) checks passed$", expected_total=13,
    ))

    R.append(dict(
        id="A05", weight=7, title="character bible approval boundary",
        plan=_scenario("a05_character_bible_approval.py"),
        required_real=[
            "a05:gate-refuses-before-approval",
            "a05:gate-opens-after-approval",
            "a05:replayed-approval-enqueues-nothing",
            "a05:content-change-bumps-revision",
            "a05:gate-closes-on-revised-bible",
            "a05:revision-invalidates-downstream-by-class"],
        required_dry=[
            "a05:gate-refuses-before-approval",
            "a05:gate-opens-after-approval",
            "a05:replayed-approval-enqueues-nothing",
            "a05:content-change-bumps-revision",
            "a05:gate-closes-on-revised-bible",
            "a05:revision-invalidates-downstream-by-class"],
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^a05: (\d+)/(\d+) checks passed$", expected_total=10,
    ))

    R.append(dict(
        id="A06", weight=7, owner_gated=True,
        title="song playable storyboard (needs a produced song file)",
        reason="Real-audio credit needs a produced AAC-LC 48 kHz song file; "
               "producing it is a paid provider run (A11). The harness can print "
               "exit 4 BLOCKED_A11, which earns nothing. Owner decision required.",
    ))

    R.append(dict(
        id="A07", weight=8, title="opening sync + duration band",
        plan=_scenario("a07_opening_sync_duration.py"),
        required_real=[
            "a07:hook-first-sheet-rejected",
            "a07:62s-passes-with-named-warning",
            "a07:master-overshoot-named-on-receipt",
            "a07:unmeasured-duration-never-passes",
            "a07:short-side-keeps-5-10-band",
            "a07:receipt-records-duration-profile"],
        required_dry=[
            "a07:hook-first-sheet-rejected",
            "a07:62s-passes-with-named-warning",
            "a07:master-overshoot-named-on-receipt",
            "a07:unmeasured-duration-never-passes",
            "a07:short-side-keeps-5-10-band",
            "a07:receipt-records-duration-profile"],
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^a07: (\d+)/(\d+) checks passed$", expected_total=15,
    ))

    R.append(dict(
        id="A08", weight=8, title="clean install canary, both distributions",
        plan=plan_a08,
        required_real=[
            "real:onboarding:installer delivered the skill tree",
            "real:onboarding:skill tree installed",
            "real:onboarding:manifest has files",
            "real:onboarding:installed tree matches pinned source",
            "real:onboarding:manifest digests verified",
            "real:999:installer delivered the skill tree",
            "real:999:skill tree installed",
            "real:999:manifest has files",
            "real:999:installed tree matches pinned source",
            "real:999:manifest digests verified"],
        required_dry=[
            "dry:onboarding:scoped files installed",
            "dry:onboarding:manifest hash recorded",
            "dry:parity negative control (tamper detected)",
            "dry:no legacy mirror tree"],
        required_re_real=[r"installer rc=\[?\d+", r"\d+ files, digest [0-9a-f]{16,}"],
        required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^(dry-run|real): (\d+)/(\d+) checks passed$",
        expected_total=None, min_total=7,
        expects_installer_rc=True,
        notes=["installer_rc is captured but NEVER a pass signal: the acceptance "
               "text must state the scratch-sandbox condition alongside it."],
    ))

    R.append(dict(
        id="A09", weight=8, title="factory lifecycle + adapter/outbox + guards",
        plan=_scenario("a09_factory_lifecycle_outbox.py"),
        required_real=[
            "a09:continuation-queue-is-durable-log",
            "a09:completion-guard-all-parked-not-delivered",
            "a09:completion-guard-all-failed-not-delivered",
            "a09:completion-guard-empty-run-not-delivered",
            "a09:completion-guard-delivers-complete-run",
            "a09:outbox-resume-sends-each-piece-once",
            "a09:outbox-refuses-sent-without-receipt"],
        required_dry=[
            "a09:continuation-queue-is-durable-log",
            "a09:completion-guard-all-parked-not-delivered",
            "a09:completion-guard-all-failed-not-delivered",
            "a09:completion-guard-empty-run-not-delivered",
            "a09:completion-guard-delivers-complete-run",
            "a09:outbox-resume-sends-each-piece-once",
            "a09:outbox-refuses-sent-without-receipt"],
        required_re_real=[], required_re_dry=[],
        forbidden_real=[], forbidden_dry=[],
        summary_re=r"^a09: (\d+)/(\d+) checks passed$", expected_total=13,
    ))

    R.append(dict(
        id="A10", weight=6, owner_gated=True,
        title="graphify rebuild + verify against the accepted vector",
        reason="Needs an owner GO for graph mutation (W09-U1 Phase B).",
    ))

    R.append(dict(
        id="A11", weight=14, owner_gated=True,
        title="live channel + paid provider run",
        reason="BLOCKED_NEEDS_AUTHORIZATION: one KIE render + one Telegram "
               "delivery, operator keys, <=10 USD. Owner GO required.",
    ))

    R.append(dict(
        id="A12", weight=10, title="loaded-source proof on both distributions",
        plan=plan_a12,
        # These strings are a12_runtime_proof.py's own output at this head:
        # the per-side loaded-source and loaded-module verdicts, the two-count
        # summaries, and the authoritative `a12_creditable` line. A side that
        # did not record prints "NOT RECORDED", a stale/tampered tree prints
        # "MISMATCH:" or "DISAGREE", and a one-sided record prints "1/2", so
        # none of them can satisfy these.
        required_real=A12_REQUIRED,
        required_dry=A12_REQUIRED,
        required_re_real=A12_REQUIRED_RE, required_re_dry=A12_REQUIRED_RE,
        forbidden_real=A12_FORBIDDEN, forbidden_dry=A12_FORBIDDEN,
        # record and check each print the loaded-module verdict once per side.
        min_occurrences={"loaded-module proof: OK": 4},
        summary_re=None, expected_total=None,
        notes=["A12 consumes A08's clean-install manifest; without it this row "
               "is BLOCKED_HARNESS naming A08, never a pass.",
               "The harness is tests/w10-canary/scenarios/a12_runtime_proof.py "
               "and its flags were read from its own --help at this head."],
    ))
    return R


# --------------------------------------------------------------------------
# evaluation — exit code and assertion output must agree
# --------------------------------------------------------------------------

def evaluate(spec, step_records, overall_rc, mode):
    text = "\n".join((s["stdout"] or "") + (s["stderr"] or "")
                     for s in step_records)
    lines = text.splitlines()
    pass_lines = [l for l in lines if "[PASS]" in l]
    fail_lines = [l for l in lines if "[FAIL]" in l]
    key = "required_%s" % mode
    re_key = "required_re_%s" % mode
    forb_key = "forbidden_%s" % mode
    required = list(spec.get(key) or [])
    required_re = list(spec.get(re_key) or [])
    forbidden = [re.compile(p) if p.startswith("^") or "\\b" in p else p
                 for p in (spec.get(forb_key) or [])]
    missing = [p for p in required if p not in text]
    missing_re = [p for p in required_re if not re.search(p, text, re.M)]

    forbidden_present = []
    for p in forbidden:
        if isinstance(p, re.Pattern):
            if p.search(text):
                forbidden_present.append(p.pattern)
        elif p in text:
            forbidden_present.append(p)

    summary_line = None
    observed_total = None
    observed_passed = None
    summary_re = spec.get("summary_re")
    summary_ok = None
    if summary_re:
        matches = [m for m in re.finditer(summary_re, text, re.M)]
        if matches:
            m = matches[-1]
            summary_line = m.group(0)
            nums = re.findall(r"\d+", summary_line)
            observed_passed, observed_total = int(nums[-2]), int(nums[-1])
            summary_ok = (observed_passed == observed_total)
            if spec.get("expected_total") is not None:
                summary_ok = summary_ok and observed_total == spec["expected_total"]
            if spec.get("min_total") is not None:
                summary_ok = summary_ok and observed_total >= spec["min_total"]
        else:
            summary_ok = False

    group_ok = None
    group_observed = None
    group = spec.get("group")
    if group:
        prefix = "  [PASS] " + group["prefix"]
        group_observed = len([l for l in lines if l.startswith(prefix)])
        group_ok = group_observed == group["count"]

    min_occ_missing = []
    for needle, n in (spec.get("min_occurrences") or {}).items():
        if text.count(needle) < n:
            min_occ_missing.append("%s>=%d (saw %d)"
                                   % (needle, n, text.count(needle)))

    min_passed_ok = None
    if spec.get("min_passed") is not None and spec.get("id") == "A01":
        m = re.search(r"^(\d+) passed in [\d.]+s", text, re.M)
        min_passed_ok = bool(m) and int(m.group(1)) >= spec["min_passed"]

    installer_rcs = parse_installer_rcs(text)
    installer_rc = installer_rcs[-1] if installer_rcs else None
    installer_rc_note = ""
    if installer_rc is not None:
        installer_rc_note = (
            "installer_rc=%d was observed inside the canary's scratch sandbox "
            "only (no real config root, no client box, no paid call). "
            "installer_rc is NOT a pass signal — the row's verdict comes from "
            "its own check lines and summary." % installer_rc)

    assertions = {
        "pass_lines": len(pass_lines),
        "fail_lines": len(fail_lines),
        "summary_line": summary_line,
        "expected_total": spec.get("expected_total"),
        "observed_total": observed_total,
        "group": (None if not group else
                  {"prefix": group["prefix"], "expected": group["count"],
                   "observed": group_observed, "ok": group_ok}),
        "missing_required": missing,
        "missing_required_re": missing_re,
        "min_occurrences_missing": min_occ_missing,
        "min_passed_ok": min_passed_ok,
        "forbidden_present": forbidden_present,
        "disagreement": None,
    }

    if overall_rc != 0:
        return {"verdict": "FAIL", "reason": "exit code %s" % overall_rc,
                "assertions": assertions}

    problems = []
    if fail_lines:
        problems.append("%d [FAIL] line(s) with exit 0" % len(fail_lines))
    if missing:
        problems.append("missing required check line(s): %s" % ", ".join(missing))
    if missing_re:
        problems.append("missing required pattern(s): %s" % ", ".join(missing_re))
    if forbidden_present:
        problems.append("forbidden marker(s): %s" % ", ".join(forbidden_present))
    if summary_ok is False:
        problems.append("summary line missing or counts disagree (%s)"
                        % (summary_line or "no summary line"))
    if group_ok is False:
        problems.append("%s* checks: expected %d, saw %s"
                        % (group["prefix"], group["count"], group_observed))
    if min_occ_missing:
        problems.append("occurrence floor unmet: %s" % ", ".join(min_occ_missing))
    if min_passed_ok is False:
        problems.append("pytest 'passed' count absent or below %d"
                        % spec["min_passed"])

    if problems:
        assertions["disagreement"] = "; ".join(problems)
        return {"verdict": "DISAGREEMENT",
                "reason": "exit 0 contradicts output: " + "; ".join(problems),
                "assertions": assertions}

    verdict = "PASS_DRY" if mode == "dry" else "PASS"
    reason = ("all required assertions present and summary counts agree"
              if summary_ok or group_ok or min_passed_ok
              else "all required assertions present")
    return {"verdict": verdict, "reason": reason, "assertions": assertions}


def failure_class(step_records):
    text = "\n".join((s["stdout"] or "") + (s["stderr"] or "")
                     for s in step_records)
    for marker in ENV_ERROR_MARKERS:
        if marker in text:
            return "ENV", marker
    return "CONTENT", ""


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

def make_env(step):
    env = {k: v for k, v in os.environ.items() if k not in ENV_STRIP}
    env["HOME"] = step.env.pop("_HOME")
    env["TMPDIR"] = step.env.pop("_TMPDIR")
    env["TMP"] = env["TMPDIR"]
    env["TEMP"] = env["TMPDIR"]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(step.env)
    return env


def run_step(step, home, tmpdir, timeout, label=None, logdir=None):
    step.env = dict(step.env)
    step.env["_HOME"] = home
    step.env["_TMPDIR"] = tmpdir
    env = make_env(step)
    started = time.time()
    label = label or "step-%d" % int(started * 1000)
    log_dir = Path(logdir) if logdir else Path(tmpdir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tmpdir)
    out_log = log_dir / ("%s.out.log" % label)
    err_log = log_dir / ("%s.err.log" % label)
    rec = {"index": None, "command": shlex.join(step.argv), "argv": step.argv,
           "cwd": step.cwd, "note": step.note,
           "env": {"HOME": home, "TMPDIR": tmpdir, "OPENCLAW_HOME": "<unset>",
                   "PYTHONPATH": "<unset>",
                   "PYTHONDONTWRITEBYTECODE": "1"},
           "exit_code": None, "stdout": "", "stderr": "",
           "log": str(out_log), "duration_ms": None, "classification": None}
    # The child writes straight to these files, so an operator can tail the row
    # while it runs instead of seeing nothing until it exits.
    print("  [%s] start: %s (timeout %ss, log %s)"
          % (label, rec["command"], timeout, out_log), flush=True)
    rc, timeout_hit = None, False
    with open(str(out_log), "w+", encoding="utf-8", errors="replace") as fo, \
            open(str(err_log), "w+", encoding="utf-8", errors="replace") as fe:
        try:
            proc = subprocess.Popen(step.argv, cwd=step.cwd, env=env,
                                    stdin=subprocess.DEVNULL, stdout=fo, stderr=fe)
        except (OSError, ValueError) as exc:
            fe.write("%s: %s\n" % (type(exc).__name__, exc))
            rc = None
        else:
            tick = started
            while True:
                try:
                    rc = proc.poll()
                except OSError:
                    rc = None
                if rc is not None:
                    break
                now = time.time()
                if now - started > timeout:
                    proc.kill()
                    proc.wait()
                    rc, timeout_hit = None, True
                    fo.write("\n[runner] step %s timed out after %ss: %s\n"
                             % (label, timeout, rec["command"]))
                    print("  [%s] TIMEOUT after %ss, killed" % (label, timeout),
                          flush=True)
                    break
                if now - tick >= 15.0:
                    tick = now
                    print("  [%s] running %.0fs, %d/%d bytes captured"
                          % (label, now - started, _size_of(out_log),
                             _size_of(err_log)), flush=True)
                time.sleep(0.5)
        fo.flush()
        fe.flush()
    try:
        rec["stdout"] = out_log.read_text(encoding="utf-8", errors="replace")
        rec["stderr"] = err_log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        rec["stderr"] = "os error reading step log: %s" % exc
    rec["exit_code"] = rc
    if timeout_hit:
        rec["classification"] = "TIMEOUT"
        if not (rec["stdout"].strip() or rec["stderr"].strip()):
            rec["stderr"] = ("[runner] step %s timed out after %ss and produced "
                             "no output: %s\n" % (label, timeout, rec["command"]))
    elif rc is None:
        rec["classification"] = "ENV"
    rec["duration_ms"] = int((time.time() - started) * 1000)
    print("  [%s] rc=%s after %.0fs" % (label, rc, rec["duration_ms"] / 1000.0),
          flush=True)
    return rec


def _size_of(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def base_receipt(spec, ctx, mode):
    return {
        "schema": SCHEMA,
        "row": spec["id"],
        "weight": spec["weight"],
        "title": spec.get("title", ""),
        "mode": mode,
        "verdict": None,
        "reason": "",
        "evidence_class": "DRY" if mode == "dry" else "NONE",
        "acceptance_usable": False,
        "head_sha": ctx["tree_head"],
        "vector": {
            "path": ctx["vector"]["path"],
            "pinned": ctx["vector"]["pinned"],
            "pinned_at": ctx["vector"]["pinned_at"],
            "revision_openclaw_onboarding":
                ctx["vector"]["revision_openclaw_onboarding"],
            "revision_999": ctx["vector"]["revision_999"],
            "revision_matches_head":
                ctx["vector"]["revision_openclaw_onboarding"] == ctx["tree_head"],
            "pin_is_ancestor": None,
            "pin_to_head_diff": None,
            "revisions": ctx["vector"]["revisions"],
        },
        "tree": ctx["tree_state"],
        "nine_tree": ctx.get("nine_state"),
        "command": None,
        "argv": None,
        "cwd": None,
        "env": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "stdout_sha256": None,
        "stderr_sha256": None,
        "duration_ms": None,
        "steps": [],
        "assertions": None,
        "installer_rc": None,
        "installer_rc_note": "",
        "limitations": list(LIMITATION_COMMON),
        "timestamp": now_iso(),
        "runner": ctx["runner"],
    }


VECTOR_PIN_PATH = "tests/w10-canary/source-vector.json"
CANARY_DIR = "tests/w10-canary"


def pin_probe(tree, pin, head):
    """Is this pin still a faithful description of the code under test?

    Exact equality is unsatisfiable here: source-vector.json is itself tracked,
    so the commit that refreshes the pin can never name itself. The pin is
    therefore accepted when it is an ancestor of head and the ONLY thing that
    changed under tests/w10-canary after the pin is the vector file itself.

    Returns (probe, refusal). refusal is None when the pin may be credited;
    probe is then a dict of facts for the receipt. Fail closed on every git
    failure: a nonzero rc is never read as "no differences".
    """
    if not pin:
        return None, ("BLOCKED_VECTOR",
                      "source vector names no openclaw-onboarding revision")
    rc, _, err = git_rc(tree, "rev-parse", "--git-dir")
    if rc != 0:
        return None, ("BLOCKED_ENV",
                      "tree under test is not a readable git repo (rc=%s): %s"
                      % (rc, err.strip() or "no stderr"))
    rc, out, _ = git_rc(tree, "rev-parse", "--verify", "--quiet",
                        "%s^{commit}" % pin)
    if rc != 0:
        return None, ("BLOCKED_VECTOR",
                      "vector pin %s is not a commit in this tree" % pin)
    pinned = out.strip()
    rc, _, err = git_rc(tree, "merge-base", "--is-ancestor", pinned, head)
    if rc == 1:
        return None, ("BLOCKED_VECTOR",
                      "pin %s is not an ancestor of head %s"
                      % (pinned, head))
    if rc != 0:
        return None, ("BLOCKED_ENV",
                      "git merge-base --is-ancestor failed (rc=%s): %s"
                      % (rc, err.strip() or "no stderr"))
    rc, out, err = git_rc(tree, "diff", "--name-status", pinned, head,
                          "--", CANARY_DIR)
    if rc != 0:
        return None, ("BLOCKED_ENV",
                      "git diff --name-status failed (rc=%s): %s"
                      % (rc, err.strip() or "no stderr"))
    changed = []
    for line in out.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            return None, ("BLOCKED_ENV",
                          "unparsable git diff --name-status line: %r" % line)
        changed.extend(fields[1:])
    changed = sorted(set(changed))
    offending = [p for p in changed if p != VECTOR_PIN_PATH]
    probe = {"pin_is_ancestor": True, "pin_to_head_diff": changed}
    if offending:
        return probe, ("BLOCKED_VECTOR",
                       "pin %s no longer describes the code under test; "
                       "files under %s changed after the pin: %s"
                       % (pinned, CANARY_DIR, ", ".join(offending)))
    return probe, None


def real_gate(spec, ctx):
    if not ctx.get("expect_head"):
        return "BLOCKED_ENV", "--real requires --expect-head <landed sha>"
    if ctx["tree_state"]["dirty"]:
        return ("BLOCKED_ENV", "tree under test is dirty; --real accepts only "
                               "the committed head")
    if ctx["tree_head"] != ctx["expect_head"]:
        return ("BLOCKED_HEAD", "repo head %s != --expect-head %s"
                % (ctx["tree_head"], ctx["expect_head"]))
    vec = ctx["vector"]
    if not vec["pinned"]:
        return "BLOCKED_VECTOR", "source vector is not pinned"
    probe, refusal = pin_probe(ctx["tree"],
                               vec["revision_openclaw_onboarding"],
                               ctx["tree_head"])
    if probe is not None:
        ctx["pin_probe"] = probe
    if refusal is not None:
        return refusal
    if spec["id"] == "A01":
        nine = ctx.get("nine_state") or {}
        if vec["revision_999"] and nine.get("head_sha") != vec["revision_999"]:
            return ("BLOCKED_VECTOR",
                    "999 head %s != vector 999 revision %s"
                    % (nine.get("head_sha"), vec["revision_999"]))
    return None


def run_row(spec, ctx, mode, receipts_dir, timeout):
    rec = base_receipt(spec, ctx, mode)
    out_path = Path(receipts_dir) / ("%s.json" % spec["id"])

    if spec.get("owner_gated"):
        rec["verdict"] = "BLOCKED_OWNER"
        rec["reason"] = spec["reason"]
        rec["limitations"].append("Not executed by this runner: owner gate.")
        write_receipt(rec, out_path)
        return rec

    if mode == "real":
        gate = real_gate(spec, ctx)
        probe = ctx.pop("pin_probe", None)
        if probe:
            rec["vector"].update(probe)
        if gate:
            rec["verdict"], rec["reason"] = gate
            rec["limitations"].append("Real-mode gate refused before execution.")
            write_receipt(rec, out_path)
            return rec

    homes = tempfile.mkdtemp(prefix="s75-arow-home-")
    tmps = tempfile.mkdtemp(prefix="s75-arow-tmp-")
    sandbox = {"home": homes, "tmpdir": tmps}
    try:
        try:
            row_artifacts = Path(receipts_dir) / "artifacts" / spec["id"]
            row_artifacts.mkdir(parents=True, exist_ok=True)
            steps = spec["plan"](dict(ctx, artifacts=str(row_artifacts)), mode,
                                 sandbox)
        except Blocked as b:
            rec["verdict"] = b.kind
            rec["reason"] = b.reason
            rec["limitations"].append("Not executed: %s" % b.reason)
            write_receipt(rec, out_path)
            return rec

        records = []
        overall = 0
        blocked = None
        for i, step in enumerate(steps, 1):
            r = run_step(step, homes, tmps, timeout,
                         label="%s-%d" % (spec["id"], i),
                         logdir=row_artifacts)
            r["index"] = i
            records.append(r)
            step_failed = (r["classification"] is not None
                           or r["exit_code"] not in (0, None))
            if step_failed:
                if step.blocked_on_failure:
                    cls, marker = failure_class(records)
                    blocked = (
                        step.blocked_on_failure,
                        "%s failed (%s%s); the row cannot run without it"
                        % (step.note or step.argv[0], cls,
                           (": " + marker) if marker else ""))
                else:
                    overall = (1 if r["classification"] is not None
                               else r["exit_code"])
                break
        if overall == 0 and blocked is None and len(records) != len(steps):
            overall = 1

        rec["steps"] = records
        rec["command"] = " && ".join(r["command"] for r in records)
        rec["argv"] = (records[0]["argv"] if len(records) == 1
                       else [r["argv"] for r in records])
        rec["cwd"] = records[0]["cwd"] if records else None
        rec["env"] = records[0]["env"] if records else None
        rec["exit_code"] = overall
        if len(records) == 1:
            rec["stdout"] = records[0]["stdout"]
            rec["stderr"] = records[0]["stderr"]
        else:
            parts = []
            for r in records:
                parts.append("===== step %d: %s =====\n%s%s"
                             % (r["index"], r["command"], r["stdout"],
                                (r["stderr"] or "")))
            rec["stdout"] = "\n".join(parts)
            rec["stderr"] = "\n\n".join(r["stderr"] for r in records)
        rec["stdout_sha256"] = sha256_text(rec["stdout"])
        rec["stderr_sha256"] = sha256_text(rec["stderr"])
        rec["duration_ms"] = sum((r["duration_ms"] or 0) for r in records)

        timed_out = [r for r in records
                     if r.get("classification") == "TIMEOUT"]
        if blocked is not None:
            rec["verdict"], rec["reason"] = blocked
            rec["limitations"].append("Not executed: %s" % blocked[1])
        elif timed_out:
            # A timeout is never "no installer_rc", and never silent: the step
            # that ran out of time is named in the verdict.
            rec["verdict"] = "FAIL"
            rec["reason"] = ("step timed out after %ss: %s (%s)"
                             % (timeout, timed_out[0].get("note")
                                or timed_out[0]["command"][:120],
                                timed_out[0]["command"][:120]))
        else:
            verdict = evaluate(spec, records, overall, mode)
            rec["verdict"] = verdict["verdict"]
            rec["reason"] = verdict["reason"]
            rec["assertions"] = verdict["assertions"]
        found_rc = parse_installer_rcs(rec["stdout"])
        rec["installer_rc"] = found_rc[-1] if found_rc else None
        rec["installer_rc_all"] = found_rc or None
        if rec["installer_rc"] is not None:
            rec["installer_rc_note"] = (
                "installer_rc=%d was observed inside the canary's scratch "
                "sandbox only (no real config root, no client box, no paid "
                "call). installer_rc is NOT a pass signal — the verdict comes "
                "from the row's own check lines and summary."
                % rec["installer_rc"])
        if (mode == "real" and spec.get("expects_installer_rc")
                and rec["installer_rc"] is None and not timed_out
                and blocked is None):
            rec["verdict"] = "DISAGREEMENT"
            rec["reason"] = (rec["reason"] + "; A08 output carried no "
                             "installer_rc field")
            rec["assertions"]["disagreement"] = "installer_rc absent"

        if rec["verdict"] == "FAIL":
            cls, marker = failure_class(records)
            if any(r.get("classification") == "TIMEOUT" for r in records):
                cls, marker = "TIMEOUT", "per-row timeout of %ss" % timeout
            rec["failure_class"] = cls
            rec["failure_marker"] = marker
        if rec["exit_code"] in (3, 4):
            if rec["exit_code"] == 3:
                rec["verdict"] = "BLOCKED_VECTOR"
            elif "BLOCKED_A11" in rec["stdout"]:
                rec["verdict"] = "BLOCKED_A11"
            rec["acceptance_usable"] = False

        if mode == "dry":
            rec["evidence_class"] = "DRY"
            rec["acceptance_usable"] = False
            rec["limitations"].append(
                "evidence_class DRY: --dry-run output is never acceptance "
                "evidence and this receipt is not usable for the A-row score.")
        else:
            rec["acceptance_usable"] = (rec["verdict"] == "PASS")
            rec["evidence_class"] = "REAL"

        if (mode == "real" and rec["verdict"] in (
                "BLOCKED_VECTOR", "BLOCKED_HEAD", "BLOCKED_ENV",
                "BLOCKED_HARNESS", "BLOCKED_A11")):
            rec["evidence_class"] = "NONE"
            rec["acceptance_usable"] = False

        rec["limitations"].append(
            "Required assertions for this row: %s"
            % ", ".join(spec.get("required_%s" % mode) or [])
            if spec.get("required_%s" % mode) else
            "Required assertions for this row: see assertions block.")
        for note in (spec.get("notes") or []):
            rec["limitations"].append(note)
        if spec["id"] in ("A04", "A05", "A07", "A09"):
            rec["limitations"].append(
                "Runbook writes '--core-root <landed tree>'; the harness "
                "resolves core_root directly, so the runner passes the resolved "
                "core directory <tree>/%s." % CORE_REL)
        write_receipt(rec, out_path)
        return rec
    finally:
        shutil.rmtree(homes, ignore_errors=True)
        shutil.rmtree(tmps, ignore_errors=True)


def write_receipt(rec, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, sort_keys=False) + "\n",
                 encoding="utf-8")


# --------------------------------------------------------------------------
# self-test: red on a fixture that lies, green only on exit 0 + real assertions
# --------------------------------------------------------------------------

SELFTEST_BODY = (
    'print("[PASS] fake:row-condition")\n'
    'print("A99: 13/13 checks passed")\n'
    'print("PASS")\n'
)
SELFTEST_DISAGREE = (
    'print("[FAIL] fake:row-condition")\n'
    'print("A99: 13/13 checks passed")\n'
    'sys.exit(0)\n'
)


def self_test():
    root = Path(tempfile.mkdtemp(prefix="s75-arow-selftest-"))
    checks = []

    def check(name, ok, detail=""):
        checks.append(bool(ok))
        print("  [%s] %s%s" % ("SELFTEST PASS" if ok else "SELFTEST FAIL", name,
                               (" — " + detail) if detail else ""))
        return ok

    try:
        fixture = root / "fixture.py"
        fixture.write_text("import sys\n" + SELFTEST_BODY + "sys.exit(1)\n",
                           encoding="utf-8")
        spec = {
            "id": "A99", "weight": 0, "title": "self-test synthetic row",
            "plan": lambda ctx, mode, sandbox: [
                Step([sys.executable, str(fixture)], cwd=str(root))],
            "required_dry": ["fake:row-condition"],
            "required_real": ["fake:row-condition"],
            "required_re_dry": [], "required_re_real": [],
            "forbidden_dry": [], "forbidden_real": [],
            "summary_re": r"^A99: (\d+)/(\d+) checks passed$",
            "expected_total": 13,
        }
        ctx = {
            "tree": str(root), "tree_head": "d" * 40,
            "tree_state": {"path": str(root), "head_sha": "d" * 40,
                           "dirty": False},
            "nine_root": None, "nine_state": None,
            "vector_path": str(root / "vector.json"),
            "vector": {"path": str(root / "vector.json"), "pinned": True,
                       "pinned_at": "self-test",
                       "revision_openclaw_onboarding": "d" * 40,
                       "revision_999": "e" * 40, "revisions": {}},
            "artifacts": str(root / "artifacts"),
            "runner": {"path": str(Path(__file__).resolve()),
                       "sha256": sha256_file(Path(__file__).resolve()),
                       "head_sha": None},
            "expect_head": None,
        }
        Path(ctx["artifacts"]).mkdir(parents=True, exist_ok=True)

        # git fixture for the vector-pin gate: a linear history where a pin
        # refresh touches only source-vector.json, then a commit that also
        # changes a second canary file, plus a diverged side branch.
        grepo = root / "gate-repo"
        (grepo / "tests/w10-canary").mkdir(parents=True)
        gvec = grepo / "tests/w10-canary/source-vector.json"
        gother = grepo / "tests/w10-canary/other-canary.py"
        gvec.write_text('{"pinned": true}\n', encoding="utf-8")
        gother.write_text("v1\n", encoding="utf-8")

        def ggit(*args):
            p = subprocess.run(["git", "-C", str(grepo)] + list(args),
                               capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError("git %r failed: %s" % (args, p.stderr))
            return p.stdout.strip()

        ggit("init", "-q")
        ggit("config", "user.email", "selftest@example.invalid")
        ggit("config", "user.name", "self-test")
        ggit("config", "commit.gpgsign", "false")
        ggit("add", "-A")
        ggit("commit", "-qm", "base")
        g_base = ggit("rev-parse", "HEAD")
        gvec.write_text('{"pinned": true, "refreshed": 1}\n', encoding="utf-8")
        ggit("add", "-A")
        ggit("commit", "-qm", "refresh pin only")
        g_vec_only = ggit("rev-parse", "HEAD")
        gother.write_text("v2\n", encoding="utf-8")
        ggit("add", "-A")
        ggit("commit", "-qm", "canary change too")
        g_head = ggit("rev-parse", "HEAD")
        ggit("checkout", "-q", "-b", "side", g_base)
        gvec.write_text('{"pinned": false}\n', encoding="utf-8")
        ggit("add", "-A")
        ggit("commit", "-qm", "diverged")
        g_side = ggit("rev-parse", "HEAD")
        ggit("checkout", "-q", g_head)

        def gate_ctx(pin, head, tree=None):
            t = str(tree or grepo)
            c = dict(ctx, tree=t, tree_head=head, expect_head=head,
                     tree_state={"path": t, "head_sha": head, "dirty": False})
            c["vector"] = dict(ctx["vector"],
                               revision_openclaw_onboarding=pin)
            return c

        # 1. broken fixture prints PASS and a full score, exits 1 -> FAIL.
        rec = run_row(spec, ctx, "dry", root / "rc-broken", 60)
        check("broken fixture (exit 1 while printing PASS) is FAIL",
              rec["verdict"] == "FAIL",
              "verdict=%s rc=%s" % (rec["verdict"], rec["exit_code"]))
        check("broken fixture stdout was captured verbatim",
              "A99: 13/13 checks passed" in rec["stdout"]
              and "PASS" in rec["stdout"],
              "captured %d bytes" % len(rec["stdout"]))
        check("broken fixture is not acceptance-usable",
              rec["acceptance_usable"] is False
              and rec["evidence_class"] == "DRY",
              "%s/%s" % (rec["evidence_class"], rec["acceptance_usable"]))

        # 2. same text, exit 0 -> PASS_DRY, receipt still unusable.
        fixture.write_text("import sys\n" + SELFTEST_BODY + "sys.exit(0)\n",
                           encoding="utf-8")
        rec2 = run_row(spec, ctx, "dry", root / "rc-green", 60)
        check("green fixture (exit 0 + assertions) is PASS_DRY",
              rec2["verdict"] == "PASS_DRY",
              "verdict=%s rc=%s" % (rec2["verdict"], rec2["exit_code"]))
        check("dry-run receipt carries evidence_class=DRY and "
              "acceptance_usable=false",
              rec2["evidence_class"] == "DRY"
              and rec2["acceptance_usable"] is False,
              "%s/%s" % (rec2["evidence_class"], rec2["acceptance_usable"]))
        check("dry-run receipt records the exact command line",
              rec2["command"] == shlex.join([sys.executable, str(fixture)]),
              rec2["command"])
        check("dry-run receipt records isolated HOME/TMPDIR and unset "
              "OPENCLAW_HOME",
              rec2["env"]["OPENCLAW_HOME"] == "<unset>"
              and bool(rec2["env"]["HOME"]) and bool(rec2["env"]["TMPDIR"]),
              "HOME=%s" % rec2["env"]["HOME"])

        # 3. exit 0 but a [FAIL] line -> DISAGREEMENT, never PASS.
        fixture.write_text("import sys\n" + SELFTEST_DISAGREE,
                           encoding="utf-8")
        rec3 = run_row(spec, ctx, "dry", root / "rc-disagree", 60)
        check("exit 0 with a [FAIL] line is DISAGREEMENT (fail closed)",
              rec3["verdict"] == "DISAGREEMENT",
              "verdict=%s" % rec3["verdict"])

        # 4. exit 0 but the required assertion is absent -> DISAGREEMENT.
        fixture.write_text('import sys\nprint("A99: 13/13 checks passed")\n'
                           'sys.exit(0)\n', encoding="utf-8")
        rec4 = run_row(spec, ctx, "dry", root / "rc-missing", 60)
        check("exit 0 without the required check line is DISAGREEMENT",
              rec4["verdict"] == "DISAGREEMENT",
              "verdict=%s" % rec4["verdict"])

        # 4b. classification control: an environment marker and a genuine
        #     assertion failure share exit code 1 but must not share a class.
        envfixture = root / "envfixture.py"
        envfixture.write_text(
            "import sys\n"
            "sys.stderr.write(\"Error [ERR_MODULE_NOT_FOUND]: Cannot find "
            "package 'acorn' imported from validate.mjs\\n\")\n"
            "sys.exit(1)\n", encoding="utf-8")
        spec_env = dict(spec, plan=lambda ctx, mode, sandbox: [
            Step([sys.executable, str(envfixture)], cwd=str(root))])
        rec_env = run_row(spec_env, ctx, "dry", root / "rc-env", 60)
        check("ERR_MODULE_NOT_FOUND classifies as failure_class=ENV",
              rec_env["verdict"] == "FAIL"
              and rec_env.get("failure_class") == "ENV"
              and rec_env.get("failure_marker") == "ERR_MODULE_NOT_FOUND",
              "verdict=%s class=%s marker=%s"
              % (rec_env["verdict"], rec_env.get("failure_class"),
                 rec_env.get("failure_marker")))
        check("a genuine assertion failure keeps failure_class=CONTENT",
              rec.get("failure_class") == "CONTENT"
              and not rec.get("failure_marker"),
              "class=%s marker=%r" % (rec.get("failure_class"),
                                      rec.get("failure_marker")))

        # 4c. a failed preflight marked blocked_on_failure is BLOCKED_ENV.
        npmfixture = root / "npmfixture.py"
        npmfixture.write_text(
            "import sys\nsys.stderr.write('npm ERR! network EAI_AGAIN\\n')\n"
            "sys.exit(1)\n", encoding="utf-8")
        spec_npm = dict(spec, plan=lambda ctx, mode, sandbox: [
            Step([sys.executable, str(npmfixture)], cwd=str(root),
                 note="disposable npm install (acorn)",
                 blocked_on_failure="BLOCKED_ENV")])
        rec_npm = run_row(spec_npm, ctx, "dry", root / "rc-npm", 60)
        check("failed npm install is BLOCKED_ENV naming npm, never PASS",
              rec_npm["verdict"] == "BLOCKED_ENV"
              and rec_npm["acceptance_usable"] is False
              and "npm" in rec_npm["reason"],
              "verdict=%s reason=%s" % (rec_npm["verdict"],
                                        rec_npm["reason"][:80]))

        # 5. real mode, matching head and pinned vector, lying fixture -> FAIL.
        ctx_real = gate_ctx(g_head, g_head)
        fixture.write_text("import sys\n" + SELFTEST_BODY + "sys.exit(1)\n",
                           encoding="utf-8")
        rec5 = run_row(spec, ctx_real, "real", root / "rc-real-broken", 60)
        check("real-mode broken fixture is FAIL with REAL evidence",
              rec5["verdict"] == "FAIL"
              and rec5["evidence_class"] == "REAL"
              and rec5["acceptance_usable"] is False,
              "verdict=%s class=%s" % (rec5["verdict"],
                                       rec5["evidence_class"]))

        # 6. real mode, genuine rc==0 + assertions -> PASS, usable.
        fixture.write_text("import sys\n" + SELFTEST_BODY + "sys.exit(0)\n",
                           encoding="utf-8")
        rec6 = run_row(spec, ctx_real, "real", root / "rc-real-green", 60)
        check("real-mode green fixture is PASS and acceptance_usable",
              rec6["verdict"] == "PASS"
              and rec6["evidence_class"] == "REAL"
              and rec6["acceptance_usable"] is True,
              "verdict=%s class=%s usable=%s"
              % (rec6["verdict"], rec6["evidence_class"],
                 rec6["acceptance_usable"]))

        # 7. real mode with an unusable pin refuses before executing.
        ctx_stale = gate_ctx(g_side, g_head)
        rec7 = run_row(spec, ctx_stale, "real", root / "rc-stale", 60)
        check("stale pin in real mode is BLOCKED_VECTOR, never PASS",
              rec7["verdict"] == "BLOCKED_VECTOR"
              and rec7["acceptance_usable"] is False
              and rec7["exit_code"] is None,
              "verdict=%s" % rec7["verdict"])

        # 8. pin gate: exact equality is unsatisfiable in practice, so an
        #    ancestor pin whose only post-pin canary change is the vector
        #    itself must be accepted — while every loosening stays fail-closed.
        ctx_exact = gate_ctx(g_head, g_head)
        g_exact = real_gate(spec, ctx_exact)
        exact_probe = ctx_exact.get("pin_probe") or {}
        check("pin == head passes the vector gate and records an empty "
              "pin->head diff",
              g_exact is None
              and exact_probe.get("pin_is_ancestor") is True
              and exact_probe.get("pin_to_head_diff") == [],
              "gate=%r probe=%r" % (g_exact, exact_probe))

        ctx_vec = gate_ctx(g_base, g_vec_only)
        g_vec = real_gate(spec, ctx_vec)
        check("ancestor pin whose only post-pin change is source-vector.json "
              "passes the vector gate",
              g_vec is None, "got %r" % (g_vec,))
        vec_probe = ctx_vec.get("pin_probe") or {}
        check("ancestor-pin probe names the vector file as the whole diff",
              vec_probe.get("pin_is_ancestor") is True
              and vec_probe.get("pin_to_head_diff")
              == ["tests/w10-canary/source-vector.json"],
              "probe=%r" % (vec_probe,))

        g_two = real_gate(spec, gate_ctx(g_base, g_head))
        check("ancestor pin is BLOCKED_VECTOR when a second canary file "
              "changed after it, naming that file",
              g_two is not None and g_two[0] == "BLOCKED_VECTOR"
              and "other-canary.py" in g_two[1],
              "got %r" % (g_two,))

        g_side = real_gate(spec, gate_ctx(g_side, g_head))
        check("pin that is not an ancestor of head is BLOCKED_VECTOR",
              g_side is not None and g_side[0] == "BLOCKED_VECTOR"
              and "not an ancestor" in g_side[1],
              "got %r" % (g_side,))

        g_garbage = real_gate(spec, gate_ctx("f" * 40, g_head))
        check("garbage pin is BLOCKED_VECTOR, never a traceback",
              g_garbage is not None and g_garbage[0] == "BLOCKED_VECTOR"
              and "not a commit" in g_garbage[1],
              "got %r" % (g_garbage,))

        nonrepo = root / "not-a-git-repo"
        nonrepo.mkdir()
        g_nonrepo = real_gate(spec, gate_ctx(g_base, g_head, tree=nonrepo))
        check("a tree that is not a git repo is BLOCKED_ENV, never a pass",
              g_nonrepo is not None and g_nonrepo[0] == "BLOCKED_ENV",
              "got %r" % (g_nonrepo,))

        # a nonzero git rc must never be read as "no differences"
        kept_git_rc = globals()["git_rc"]

        def failing_diff(path, *args):
            if args and args[0] == "diff":
                return 128, "", "simulated git diff failure"
            return kept_git_rc(path, *args)

        globals()["git_rc"] = failing_diff
        try:
            g_diff_rc = real_gate(spec, gate_ctx(g_base, g_vec_only))
        finally:
            globals()["git_rc"] = kept_git_rc
        check("nonzero git diff rc is BLOCKED_ENV, not 'no differences'",
              g_diff_rc is not None and g_diff_rc[0] == "BLOCKED_ENV"
              and "rc=128" in g_diff_rc[1],
              "got %r" % (g_diff_rc,))

        # the facts must reach the receipt, and revision_matches_head must
        # stay exact equality even when the gate passes on ancestry.
        fixture.write_text("import sys\n" + SELFTEST_BODY + "sys.exit(0)\n",
                           encoding="utf-8")
        rec_pin = run_row(spec, gate_ctx(g_base, g_vec_only), "real",
                          root / "rc-pin-ancestor", 60)
        check("real receipt records pin_is_ancestor and the pin->head diff "
              "while revision_matches_head stays exact",
              rec_pin["verdict"] == "PASS"
              and rec_pin["vector"]["pin_is_ancestor"] is True
              and rec_pin["vector"]["pin_to_head_diff"]
              == ["tests/w10-canary/source-vector.json"]
              and rec_pin["vector"]["revision_matches_head"] is False,
              "verdict=%s diff=%r matches=%r"
              % (rec_pin["verdict"],
                 rec_pin["vector"].get("pin_to_head_diff"),
                 rec_pin["vector"].get("revision_matches_head")))

        # 9. the A01 999-revision check sits behind the same gate and must
        #    still fire exactly as before.
        a01 = dict(spec, id="A01")
        ctx_a01_bad = gate_ctx(g_head, g_head)
        ctx_a01_bad["nine_state"] = {"head_sha": "a" * 40}
        g_a01_bad = real_gate(a01, ctx_a01_bad)
        check("A01's 999 revision check still fires after the pin gate change",
              g_a01_bad is not None and g_a01_bad[0] == "BLOCKED_VECTOR"
              and "999 head" in g_a01_bad[1], "got %r" % (g_a01_bad,))
        ctx_a01_ok = gate_ctx(g_head, g_head)
        ctx_a01_ok["nine_state"] = {"head_sha": ctx["vector"]["revision_999"]}
        g_a01_ok = real_gate(a01, ctx_a01_ok)
        check("A01 passes the 999 revision check when the heads agree",
              g_a01_ok is None, "got %r" % (g_a01_ok,))

        print("self-test: %d/%d checks passed"
              % (sum(checks), len(checks)))
        return 0 if all(checks) else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    here = Path(__file__).resolve()
    tree_default = here.parents[2]
    ap = argparse.ArgumentParser(
        description="Execute the non-owner-gated Skill 75 acceptance rows.")
    ap.add_argument("--tree", default=str(tree_default),
                    help="repo under test (default: the worktree holding this "
                         "harness)")
    ap.add_argument("--nine-root", default=None,
                    help="999-setup checkout for A01 (default: <tree>/../999-setup "
                         "when it exists)")
    ap.add_argument("--vector", default=None,
                    help="source vector (default: <tree>/tests/w10-canary/"
                         "source-vector.json)")
    ap.add_argument("--receipts", default=None,
                    help="receipt dir (default: <tree>/work/S75-W10-U1/RECEIPTS)")
    ap.add_argument("--rows", default=None,
                    help="comma-separated subset, e.g. A02,A04")
    ap.add_argument("--dry-run", action="store_true",
                    help="DRY evidence (default)")
    ap.add_argument("--real", action="store_true",
                    help="REAL evidence; requires --expect-head and a matching "
                         "pin")
    ap.add_argument("--expect-head", default=None,
                    help="landed full 40-char head sha for --real")
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-row timeout in seconds (default 900)")
    ap.add_argument("--list", action="store_true", help="list rows and exit")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the runner goes red on a lying fixture")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()

    all_rows = rows()
    if a.list:
        for spec in all_rows:
            kind = "BLOCKED_OWNER" if spec.get("owner_gated") else "executable"
            print("%s  wt=%-2d  %-13s  %s"
                  % (spec["id"], spec["weight"], kind, spec.get("title", "")))
        print("executable weight: %d/100; owner-gated weight: %d/100"
              % (sum(r["weight"] for r in all_rows if not r.get("owner_gated")),
                 sum(r["weight"] for r in all_rows if r.get("owner_gated"))))
        return 0

    if a.real and a.dry_run:
        print("--real and --dry-run are mutually exclusive", file=sys.stderr)
        return 2
    mode = "real" if a.real else "dry"

    tree = Path(a.tree).resolve()
    nine = Path(a.nine_root).resolve() if a.nine_root else None
    if nine is None:
        candidate = tree.parent / "999-setup"
        nine = candidate if candidate.is_dir() else None
    vector_path = Path(a.vector) if a.vector else (
        tree / "tests/w10-canary/source-vector.json")
    receipts = Path(a.receipts) if a.receipts else (
        tree / "work/S75-W10-U1/RECEIPTS")

    selected = None
    if a.rows:
        selected = {x.strip().upper() for x in a.rows.split(",") if x.strip()}
        unknown = selected - set(FROZEN_WEIGHTS)
        if unknown:
            print("unknown row(s): %s" % sorted(unknown), file=sys.stderr)
            return 2

    vector = load_vector(vector_path)
    state = tree_state(tree)
    nine_state = None
    if nine:
        nine_state = tree_state(nine)
        nine_state["revision_matches_vector"] = (
            nine_state["head_sha"] == vector["revision_999"])
    ctx = {
        "tree": str(tree),
        "tree_head": state["head_sha"],
        "tree_state": state,
        "nine_root": str(nine) if nine else None,
        "nine_state": nine_state,
        "vector_path": str(vector_path),
        "vector": vector,
        "artifacts": str(receipts / "artifacts" / "A08"),
        "expect_head": a.expect_head,
        "runner": {"path": str(here), "sha256": sha256_file(here),
                   "head_sha": git_out(tree, "rev-parse", "HEAD")},
    }

    print("run_a_rows: mode=%s tree=%s head=%s vector=%s(pinned=%s)"
          % (mode, tree, str(state["head_sha"])[:12], vector_path,
             vector["pinned"]))
    if mode == "dry":
        print("DRY: receipts carry evidence_class=DRY and "
              "acceptance_usable=false; no row can be credited from this run.")
    receipts.mkdir(parents=True, exist_ok=True)

    results = []
    for spec in all_rows:
        if selected is not None and spec["id"] not in selected:
            continue
        rec = run_row(spec, ctx, mode, receipts, a.timeout)
        results.append(rec)
        print("  %s  %-14s rc=%-4s %6sms  %s"
              % (spec["id"], rec["verdict"],
                 "null" if rec["exit_code"] is None else rec["exit_code"],
                 rec["duration_ms"] if rec["duration_ms"] is not None else "-",
                 rec["reason"][:90]))

    run_summary = {
        "schema": SCHEMA + ".run",
        "mode": mode,
        "tree": str(tree),
        "head_sha": state["head_sha"],
        "vector": {"path": str(vector_path), "pinned": vector["pinned"],
                   "revision_openclaw_onboarding":
                       vector["revision_openclaw_onboarding"],
                   "revision_999": vector["revision_999"]},
        "expect_head": a.expect_head,
        "timestamp": now_iso(),
        "rows": {r["row"]: {"verdict": r["verdict"],
                            "weight": r["weight"],
                            "evidence_class": r["evidence_class"],
                            "acceptance_usable": r["acceptance_usable"]}
                 for r in results},
        "executable_weight": sum(
            r["weight"] for r in results
            if r["row"] not in ("A06", "A10", "A11")),
        "credited_weight": sum(r["weight"] for r in results
                               if r["verdict"] == "PASS"
                               and r["acceptance_usable"] is True),
        "runner": ctx["runner"],
    }
    write_receipt(run_summary, receipts / "RUN.json")
    print("wrote %d receipts to %s" % (len(results), receipts))

    if any(r["verdict"] in ("FAIL", "DISAGREEMENT") for r in results):
        return 1
    if any(r["verdict"].startswith("BLOCKED_") for r in results):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
