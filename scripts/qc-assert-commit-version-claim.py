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
     must equal that version when the commit edits that CHANGELOG — a heading
     the commit never touched is inherited history, not its claim;
  4. a "bumps Skill 38 to vX.Y.Z" claim in the NEWEST root CHANGELOG.md entry
     (the text before the second `^## [` heading) must equal that version, and
     an entry with no such claim makes no claim to check.

Merge commits are skipped: their message is GitHub's, not a task record.

Scope (PBB-905 D2): a base..head range is narrowed to the batch's own bump
commits. Two filters: the guard's own adoption commit and its descendants only
(a batch range also carries pre-existing unit history written BEFORE this rule
existed — judging it is a false failure that no batch could ever pass), and
commits that write a version record (a version file touched, or a version claim
in the message). Code and docs commits are not blamed for the tree they
inherited from main. When the guard is already on the range base, every commit
in the range is checked, exactly as before.

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

GUARD_PATH = "scripts/qc-assert-commit-version-claim.py"
VERSION_FILE = "38-conversational-ai-system/skill-version.txt"
SKILL_CHANGELOG = "38-conversational-ai-system/CHANGELOG.md"
ROOT_CHANGELOG = "CHANGELOG.md"

CLAIM_RE = re.compile(r"Skill\s*38\b[^\n]*?\bto\s+v?(\d+\.\d+\.\d+)(?!\.\d)(?!\d)", re.I)
HEADING_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]", re.M)
ENTRY_RE = re.compile(r"^##\s*\[", re.M)
ROOT_CLAIM_RE = re.compile(
    r"bumps?\s+Skill\s*38\s+to\s+v?(\d+\.\d+\.\d+)(?!\.\d)(?!\d)", re.I
)


def newest_entry(text):
    """The newest CHANGELOG entry only: text from the first `^## [` heading up
    to the next one (or end of file).

    PBB-339 D1: rule 4 used to scan the whole root CHANGELOG, so the first
    "bumps Skill 38 to" line ever written became the stale match for every
    later bump and a wholly true record was refused. The root CHANGELOG is
    append-at-top, so the commit's own entry is the first section.
    """
    starts = [m.start() for m in ENTRY_RE.finditer(text)]
    if not starts:
        return text
    end = starts[1] if len(starts) > 1 else len(text)
    return text[starts[0]:end]


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


def git_ok(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True).returncode == 0


def bump_commit(rev):
    """True when the commit writes a version record of its own: it touches a
    version file, or its message claims a Skill 38 version.

    A code- or docs-only commit inherits the tree it was handed; it makes no
    version claim, so a stale number inherited from history is not its lie.
    """
    if any(p in (VERSION_FILE, SKILL_CHANGELOG, ROOT_CHANGELOG) for p in changed_paths(rev)):
        return True
    body = git("log", "-1", "--format=%B", rev)
    return bool(CLAIM_RE.search(body) or ROOT_CLAIM_RE.search(body))


def scope(revs, base):
    """Split a range into (in_scope, out_of_scope) — the batch's own bumps.

    Two filters, both from PBB-905 D2:

      * adoption — the first commit in base..head that contains this file. Only
        it and its descendants are the batch's own commits; everything older
        was written before this rule existed and is never judged by it;
      * relevance — only commits that write a version record (bump_commit), so
        the batch's code and docs commits are not blamed for the tree they
        inherited from main.

    With no range base, or with the guard already on the base, nothing is out of
    scope and the pre-PBB-905 behaviour is kept.
    ponytail: scope needs a range base; upgrade path is to record the adoption
    sha in a committed marker file so a bare push event can scope too.
    """
    if not revs or not base:
        return revs, []
    try:
        if show(base, GUARD_PATH) is not None:
            return revs, []
        history = git("rev-list", "--reverse", "%s..%s" % (base, revs[-1])).split()
    except EnvError:
        return revs, []
    adoption = next((r for r in history if show(r, GUARD_PATH) is not None), None)
    if adoption is None:
        return revs, []
    kept = [
        r
        for r in revs
        if git_ok("merge-base", "--is-ancestor", adoption, r) and bump_commit(r)
    ]
    return kept, [r for r in revs if r not in kept]


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
    if skill_log is not None and SKILL_CHANGELOG in changed_paths(rev):
        m = HEADING_RE.search(skill_log)
        if m and norm(m.group(1)) != norm(actual):
            v.append(
                "%s: %s's first heading is [%s] but %s is %s"
                % (rev, SKILL_CHANGELOG, m.group(1), VERSION_FILE, actual)
            )

    root_log = show(rev, ROOT_CHANGELOG)
    if root_log is not None:
        m = ROOT_CLAIM_RE.search(newest_entry(root_log))
        if m and norm(m.group(1)) != norm(actual):
            v.append(
                "%s: %s's newest entry says 'bumps Skill 38 to v%s' but %s is %s"
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
            return git("rev-list", "--reverse", "%s..%s" % (base, head)).split(), base
        except EnvError:
            pass  # shallow or garbage range -> fall back to HEAD, loudly
        print(
            "NOTE: range %s..%s not available in this clone; checking %s only"
            % (base[:12], head[:12], head[:12])
        )
    return [head], base


def report(revs, base=None):
    revs, out_of_scope = scope(revs, base)
    for rev in out_of_scope:
        print(
            "SKIP %s (outside the batch's own bump commits: pre-adoption history "
            "or not a version record)" % rev[:12]
        )
    if out_of_scope and not revs:
        print(
            "NOTE: no commit in range is both at or after this guard's adoption "
            "commit and a version record."
        )
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
        with open(SKILL_CHANGELOG, "a") as f:
            f.write("- a note written under the stale heading\n")
        results.append((
            "stale skill CHANGELOG heading edited by the commit",
            [commit("Bumps Skill 38 to v2.0.5")], 1,
        ))

        book("2.0.6", "2.0.6", "2.0.5")
        results.append(("stale root CHANGELOG claim", [commit("Bumps Skill 38 to v2.0.6")], 1))

        def book_entries(v, heading, newest, older):
            write(VERSION_FILE, "v%s\n" % v)
            write(SKILL_CHANGELOG, "# Skill 38\n\n## [%s] - 2026-01-01 - entry\n" % heading)
            write(
                ROOT_CHANGELOG,
                "# Changelog\n\n## [Unreleased] - newest\n\n%s\n\n## [v1.0.0] - older\n\n%s\n"
                % (newest, older),
            )

        book_entries(
            "2.0.9", "2.0.9",
            "- Fix the widget pipeline; no Skill 38 wording in this entry.",
            "- Bumps Skill 38 to v2.0.8 in this release.",
        )
        results.append((
            "PBB-339 D1: wholly true record, only 'bumps Skill 38 to' line is older",
            [commit("Bumps Skill 38 to v2.0.9")], 0,
        ))

        book_entries(
            "2.0.11", "2.0.11",
            "- Bumps Skill 38 to v2.0.10 in this release.",
            "- Bumps Skill 38 to v2.0.11 in this release.",
        )
        results.append((
            "stale claim in the NEWEST root entry still fails",
            [commit("Bumps Skill 38 to v2.0.11")], 1,
        ))

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

        # PBB-905 D2: history written before this guard existed is out of scope,
        # while the batch's own bump commit stays checked.
        subprocess.run(["git", "checkout", "-q", "-b", "legacy", base], check=True)
        book("2.0.20", "2.0.20", "2.0.20")
        legacy = commit("chore: renumber skill 38 (pre-guard unit history)")
        subprocess.run(["git", "checkout", "-q", trunk], check=True)
        os.makedirs(os.path.dirname(GUARD_PATH), exist_ok=True)
        write(GUARD_PATH, "# version-claim guard adopted here\n")
        commit("chore: adopt the version-claim guard")
        subprocess.run(
            ["git", "merge", "-q", "--no-ff", "-s", "ours", "-m", "Merge legacy", "legacy"],
            check=True,
        )
        book("2.0.21", "2.0.21", "2.0.21")
        batch_bump = commit("Bumps Skill 38 to v2.0.21")
        docs_only = commit("chore: docs only")
        scoped_kept, scoped_out = scope([legacy, batch_bump, docs_only], base)
        scope_results = [
            (
                "pre-adoption and non-record commits are out of scope, batch bump stays in",
                [scoped_kept, scoped_out],
                [[batch_bump], [legacy, docs_only]],
            ),
            (
                "no range base leaves every commit in scope",
                [scope([legacy, batch_bump], "")[0]],
                [[legacy, batch_bump]],
            ),
        ]

        failures = 0
        for label, revs, want in results:
            print("  -- " + label)
            got = report(revs)
            if got != want:
                failures += 1
                print("SELF-TEST FAIL — wanted rc %d, got rc %d" % (want, got))
        for label, got, want in scope_results:
            print("  -- " + label)
            if got != want:
                failures += 1
                print("SELF-TEST FAIL — wanted %r, got %r" % (want, got))
        if failures:
            print("SELF-TEST FAIL — %d fixture(s) behaved wrongly" % failures)
            return 1
        print(
            "SELF-TEST PASS — %d fixtures: wrong records fail, right records pass"
            % (len(results) + len(scope_results))
        )
        return 0
    finally:
        os.chdir(saved)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    try:
        if "--self-test" in argv:
            return self_test()
        if "--ci" in argv:
            revs, base = commits_for_ci()
            return report(revs, base)
        if "--commit" in argv:
            return report([argv[argv.index("--commit") + 1]])
        if "--range" in argv:
            spec = argv[argv.index("--range") + 1]
            if ".." not in spec:
                raise EnvError("--range needs BASE..HEAD, got %r" % spec)
            base, head = spec.split("..", 1)
            return report(
                git("rev-list", "--reverse", "%s..%s" % (base, head or "HEAD")).split(), base
            )
        return report(["HEAD"])
    except (EnvError, IndexError, KeyError, ValueError) as e:
        print("CANNOT RESOLVE — %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
