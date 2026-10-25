#!/usr/bin/env python3
"""qc-assert-commit-version-claim.py — the commit's own record of itself must
be true (PBB-263 D1, repaired under PBB-318 T-04).

D1 was a commit whose message said "Bumps Skill 38 to v2.0.32" while its own
`38-conversational-ai-system/skill-version.txt` and CHANGELOG both said
v2.0.34. Nothing was wrong with the code; the record was false. This gate
refuses that class, for every commit it is pointed at:

  1. every "Skill 38 ... to vX.Y.Z" claim in the message must equal the
     skill version the commit actually contains;
  2. a commit that changes skill-version.txt must name the new version in its
     message (a silent bump is the same defect from the other side);
  3. the first `## [x.y.z]` heading in 38-conversational-ai-system/CHANGELOG.md
     must equal that version;
  4. the first "bumps Skill 38 to vX.Y.Z" line in the root CHANGELOG.md must
     equal that version.

Merge commits are skipped: their message is GitHub's, not a task record.

Usage:
  python3 scripts/qc-assert-commit-version-claim.py --commit REV
  python3 scripts/qc-assert-commit-version-claim.py --range BASE..HEAD
  python3 scripts/qc-assert-commit-version-claim.py --ci      # from GitHub env
  python3 scripts/qc-assert-commit-version-claim.py --self-test

Exit: 0 pass (including "no claim to check"), 1 invariant violated,
      2 environment error (missing git / can't read the commit).

Wired into scripts/ci/fast-guards.d/skill-version-newline-guard.sh, which
already runs whenever any **/skill-version.txt changes.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VERSION_FILE = "38-conversational-ai-system/skill-version.txt"
SKILL_CHANGELOG = "38-conversational-ai-system/CHANGELOG.md"
ROOT_CHANGELOG = "CHANGELOG.md"

CLAIM_RE = re.compile(r"Skill\s*38\b[^\n]*?\bto\s+v?(\d+\.\d+\.\d+)(?!\.\d)(?!\d)", re.I)
HEADING_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]", re.M)
ROOT_CLAIM_RE = re.compile(
    r"bumps?\s+Skill\s*38\s+to\s+v?(\d+\.\d+\.\d+)(?!\.\d)(?!\d)", re.I
)


class EnvError(Exception):
    pass


def git(*args, text=True):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=text)
    if r.returncode != 0:
        raise EnvError("git %s failed: %s" % (" ".join(args), (r.stderr or "").strip()))
    return r.stdout


def show(rev, path):
    r = subprocess.run(["git", "show", "%s:%s" % (rev, path)], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def norm(version):
    return tuple(int(p) for p in version.lstrip("vV").split("."))


def parents(rev):
    out = git("rev-list", "--parents", "-n", "1", rev).split()
    return out[1:]


def changed_paths(rev):
    return [p for p in git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", rev).split("\n") if p]


def check_commit(rev):
    """Return (violations, skipped_reason). Empty violations means pass."""
    if len(parents(rev)) > 1:
        return [], "merge commit"
    actual_raw = show(rev, VERSION_FILE)
    if actual_raw is None:
        raise EnvError("%s has no %s" % (rev, VERSION_FILE))
    actual = actual_raw.strip()
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", actual):
        return ["%s: %s is not a plain version: %r" % (rev, VERSION_FILE, actual)], None

    subject = git("log", "-1", "--format=%B", rev)
    claims = CLAIM_RE.findall(subject)
    v = []

    for claim in claims:
        if norm(claim) != norm(actual):
            v.append(
                "%s: commit message claims Skill 38 %s but the commit contains %s"
                % (rev, claim, actual)
            )

    if VERSION_FILE in changed_paths(rev) and parents(rev) and not claims:
        v.append(
            "%s: commit changes %s to %s but its message never says so"
            % (rev, VERSION_FILE, actual)
        )

    skill_log = show(rev, SKILL_CHANGELOG)
    if skill_log is not None:
        m = HEADING_RE.search(skill_log)
        if m and norm(m.group(1)) != norm(actual):
            v.append(
                "%s: %s's first heading is [%s] but %s is %s"
                % (rev, SKILL_CHANGELOG, m.group(1), VERSION_FILE, actual)
            )

    root_log = show(rev, ROOT_CHANGELOG)
    if root_log is not None:
        m = ROOT_CLAIM_RE.search(root_log)
        if m and norm(m.group(1)) != norm(actual):
            v.append(
                "%s: %s's first 'bumps Skill 38 to' line is v%s but %s is %s"
                % (rev, ROOT_CHANGELOG, m.group(1), VERSION_FILE, actual)
            )

    return v, None


def commits_for_ci():
    ev = os.environ.get("GITHUB_EVENT_NAME", "")
    head = os.environ.get("GITHUB_SHA", "") or "HEAD"
    base = ""
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if ev in ("pull_request", "pull_request_target") and path:
        d = json.load(open(path))["pull_request"]
        base, head = d["base"]["sha"], d["head"]["sha"]
    elif ev == "push" and path:
        d = json.load(open(path))
        base, head = d.get("before", ""), d.get("after", "") or head
    else:
        base = os.environ.get("GITHUB_BASE_SHA", "")
    if base and set(base) <= {"0"}:
        base = ""
    if base and head:
        try:
            return git("rev-list", "--reverse", "%s..%s" % (base, head)).split()
        except EnvError:
            pass  # shallow or garbage range -> fall back to HEAD, loudly
        print(
            "NOTE: range %s..%s not available in this clone; checking %s only"
            % (base[:12], head[:12], head[:12])
        )
    return [head]


def report(revs):
    bad = 0
    checked = 0
    for rev in revs:
        violations, skipped = check_commit(rev)
        if skipped:
            print("SKIP %s (%s)" % (rev[:12], skipped))
            continue
        checked += 1
        if violations:
            bad += 1
            for line in violations:
                print("VIOLATION " + line)
        else:
            print("ok   %s" % rev[:12])
    if bad:
        print(
            "\nINVARIANT VIOLATED — %d of %d commit(s) carry a false Skill 38 version record."
            % (bad, checked)
        )
        return 1
    print("PASS — %d commit(s) checked; every Skill 38 version claim matches its commit." % checked)
    return 0


def self_test():
    """Fail on each wrong fixture, pass on each right one. No frameworks."""
    tmp = tempfile.mkdtemp(prefix="qc-commit-claim.")
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="selftest", GIT_AUTHOR_EMAIL="selftest@example.invalid",
        GIT_COMMITTER_NAME="selftest", GIT_COMMITTER_EMAIL="selftest@example.invalid",
    )
    saved = os.getcwd()
    os.environ.update(env)
    try:
        os.chdir(tmp)
        subprocess.run(["git", "init", "-q"], check=True)
        os.makedirs(os.path.dirname(VERSION_FILE), exist_ok=True)

        def write(path, text):
            with open(path, "w") as f:
                f.write(text)

        def commit(msg):
            subprocess.run(["git", "add", "-A"], check=True)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", msg], check=True)
            return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

        def book(v, heading, root):
            write(VERSION_FILE, "v%s\n" % v)
            write(SKILL_CHANGELOG, "# Skill 38\n\n## [%s] - 2026-01-01 - entry\n" % heading)
            write(ROOT_CHANGELOG, "# Changelog\n\n- Bumps Skill 38 to v%s in this release.\n" % root)

        results = []

        book("2.0.1", "2.0.1", "2.0.1")
        base = commit("chore: base")
        results.append(("base commit (creates files, no bump)", [base], 0))

        book("2.0.2", "2.0.2", "2.0.2")
        results.append(("bump named correctly", [commit("Bumps Skill 38 to v2.0.2")], 0))

        book("2.0.3", "2.0.3", "2.0.3")
        results.append((
            "D1 clone: message says v2.0.2, commit contains v2.0.3",
            [commit("Bumps Skill 38 to v2.0.2 with its own changelog entry")], 1,
        ))

        book("2.0.4", "2.0.4", "2.0.4")
        results.append(("bump with no claim", [commit("chore: bump skill 38")], 1))

        results.append(("non-bump commit with no claim", [commit("chore: docs only")], 0))

        book("2.0.5", "2.0.4", "2.0.5")
        results.append(("stale skill CHANGELOG heading", [commit("Bumps Skill 38 to v2.0.5")], 1))

        book("2.0.6", "2.0.6", "2.0.5")
        results.append(("stale root CHANGELOG claim", [commit("Bumps Skill 38 to v2.0.6")], 1))

        book("2.0.7", "2.0.7", "2.0.7")
        results.append((
            "substring trap: v2.0.70 must not satisfy v2.0.7",
            [commit("Bumps Skill 38 to v2.0.70")], 1,
        ))

        book("2.0.8", "2.0.8", "2.0.8")
        results.append((
            "transition message names the new version",
            [commit("Bumps Skill 38 from v2.0.7 to v2.0.8")], 0,
        ))

        # A two-parent commit is skipped: GitHub's merge message is not a task record.
        trunk = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
        subprocess.run(["git", "checkout", "-q", "-b", "side", base], check=True)
        write("side.txt", "side\n")
        commit("side work")
        subprocess.run(["git", "checkout", "-q", trunk], check=True)
        subprocess.run(
            ["git", "merge", "-q", "--no-ff", "-m", "Merge branch side", "side"], check=True
        )
        merge = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        results.append(("merge commit skipped", [merge], 0))

        failures = 0
        for label, revs, want in results:
            print("  -- " + label)
            got = report(revs)
            if got != want:
                failures += 1
                print("SELF-TEST FAIL — wanted rc %d, got rc %d" % (want, got))
        if failures:
            print("SELF-TEST FAIL — %d fixture(s) behaved wrongly" % failures)
            return 1
        print("SELF-TEST PASS — %d fixtures: wrong records fail, right records pass" % len(results))
        return 0
    finally:
        os.chdir(saved)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    try:
        if "--self-test" in argv:
            return self_test()
        if "--ci" in argv:
            return report(commits_for_ci())
        if "--commit" in argv:
            return report([argv[argv.index("--commit") + 1]])
        if "--range" in argv:
            spec = argv[argv.index("--range") + 1]
            if ".." not in spec:
                raise EnvError("--range needs BASE..HEAD, got %r" % spec)
            base, head = spec.split("..", 1)
            return report(git("rev-list", "--reverse", "%s..%s" % (base, head or "HEAD")).split())
        return report(["HEAD"])
    except (EnvError, IndexError, KeyError, ValueError) as e:
        print("CANNOT RESOLVE — %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
