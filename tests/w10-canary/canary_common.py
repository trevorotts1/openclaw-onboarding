#!/usr/bin/env python3
"""canary_common.py — shared sandbox, source-vector and receipt plumbing for the
Skill 75 W10 canary harnesses (SFR-007 preparation).

Stdlib only. One safety rule every caller relies on: nothing here ever writes to,
or runs an installer against, a real config root. Every canary runs inside a fresh
scratch sandbox whose HOME / OC_CONFIG / SKILLS_DIR / CLAUDE_CONFIG_DIR are all
redirected into it, with `openclaw` and network verbs stubbed out so a canary can
never notify a client, never fetch from the network, and never touch a live box.
A real config root is never a default and never a fallback.

Scratch convention (Trevor standing rule): sandbox dirs live under /tmp and are
prefixed  /tmp/<box-slug>-<UNIT-ID>-  ->  /tmp/skill75-repair-SFR-007-canary-*.
They self-clean on exit; `keep=True` preserves one for inspection.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UNIT_ID = "SFR-007"
BOX_SLUG = "skill75-repair"
SCRATCH_PREFIX = "%s-%s-canary-" % (BOX_SLUG, UNIT_ID)   # /tmp/skill75-repair-SFR-007-canary-
VECTOR_SCHEMA = "blackceo.skill75.source-vector/v1"
MAPPING_SCHEMA = "blackceo.skill75.receipt-mapping/v1"

#: The four repositories whose pinned revisions form the accepted source vector
#: (Skill_75_Universal_Repair_Spec_v1.1 section 3). The canaries bind to these.
VECTOR_REPOS = (
    "openclaw-onboarding",
    "999-setup",
    "blackceo-command-center",
    "blackceo-graphify-infrastructure",
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n",
                 encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ vector --
def load_vector(path):
    with open(path, "r", encoding="utf-8") as f:
        v = json.load(f)
    return v


def validate_vector(v):
    """Return (ok, problems). Schema + shape only; does not require pinned."""
    problems = []
    if v.get("schema") != VECTOR_SCHEMA:
        problems.append("schema=%r expected %r" % (v.get("schema"), VECTOR_SCHEMA))
    repos = v.get("repositories")
    if not isinstance(repos, dict):
        problems.append("repositories missing or not an object")
        return False, problems
    for name in VECTOR_REPOS:
        r = repos.get(name)
        if not isinstance(r, dict):
            problems.append("repositories.%s missing" % name)
            continue
        rev = r.get("revision")
        if rev is not None and not _is_sha(rev):
            problems.append("repositories.%s.revision not a 40-hex sha" % name)
    return not problems, problems


def _is_sha(s):
    return isinstance(s, str) and len(s) == 40 and all(
        c in "0123456789abcdef" for c in s.lower())


def _is_sha256(s):
    return isinstance(s, str) and len(s) == 64 and all(
        c in "0123456789abcdef" for c in s.lower())


def require_pinned(v):
    """Gate every REAL canary run. Returns (ok, reason).

    Fail-closed: a real canary never runs against a moving or unpinned vector.
    """
    ok, problems = validate_vector(v)
    if not ok:
        return False, "vector invalid: " + "; ".join(problems)
    if not v.get("pinned"):
        return False, ("source vector NOT pinned (pinned=false). The accepted "
                       "onboarding/999-setup/command-center/graphify revisions "
                       "are not finalized. Pin source-vector.json after the final "
                       "merges land, then rerun.")
    for name in VECTOR_REPOS:
        rev = v["repositories"][name].get("revision")
        if not _is_sha(rev):
            return False, "source vector pinned but %s.revision missing/not a sha" % name
    return True, "pinned at %s by %s" % (v.get("pinned_at"), v.get("pinned_by"))


# ------------------------------------------------------------------ shims ----
_OPENCLAW_STUB = """#!/bin/sh
# canary shim: capture, never send. `openclaw message send` would notify a live
# client/Telegram; a canary must never do that. Every call is logged and dropped.
echo "[canary-shim] openclaw $* (captured, never sent)" >> "__LOG__"
exit 0
"""

_CURL_STUB = """#!/bin/sh
# canary shim: hermetic. No network fetch during a canary.
echo "[canary-shim] curl $* (suppressed, hermetic)" >> "__LOG__"
exit 0
"""

_GIT_STUB = """#!/bin/sh
# canary shim: forward local git verbs to the real git; suppress network verbs.
REAL_GIT="__REAL_GIT__"
case "$1" in
  fetch|pull|push|clone|ls-remote|remote|submodule)
    echo "[canary-shim] git $1 (suppressed, hermetic)" >> "__LOG__"
    exit 0 ;;
esac
exec "$REAL_GIT" "$@"
"""

#: The installers obtain their source with `git clone <url> <dest>`. A real
#: install canary must run that code path, but it must never touch the network
#: and it must install EXACTLY the pinned revision. This shim answers the clone
#: from a tree already materialized at that revision and answers the two
#: provenance reads the installer performs afterwards. Everything else falls
#: through to the real git binary.
_GIT_CLONE_STUB = """#!/bin/sh
REAL_GIT="__REAL_GIT__"
PINNED_TREE="__PINNED_TREE__"
PINNED_SHA="__PINNED_SHA__"
CANON_URL="__CANON_URL__"
case "$*" in
  clone*)
    _dest=""
    for _a in "$@"; do _dest="$_a"; done
    rm -rf "$_dest"; mkdir -p "$_dest" || exit 1
    tar -C "$PINNED_TREE" -cf - . | tar -C "$_dest" -xf - || exit 1
    echo "[canary-shim] git clone -> pinned tree $PINNED_TREE @ $PINNED_SHA" >> "__LOG__"
    exit 0 ;;
  *"remote get-url origin"*) printf '%s\\n' "$CANON_URL"; exit 0 ;;
  *"rev-parse HEAD"*) printf '%s\\n' "$PINNED_SHA"; exit 0 ;;
  fetch*|pull*|push*|ls-remote*|submodule*)
    echo "[canary-shim] git (network verb suppressed, hermetic)" >> "__LOG__"
    exit 0 ;;
esac
exec "$REAL_GIT" "$@"
"""


def build_shims(shim_dir, log_path, real_git=None, clone_source=None):
    """Write openclaw/curl/git stubs into shim_dir. Return shim_dir.

    clone_source: optional (pinned_tree, pinned_sha, canonical_url). When given,
    `git clone` is answered from that already-materialized tree instead of being
    suppressed, so the installer's real clone path runs with no network.
    """
    shim = Path(shim_dir)
    shim.mkdir(parents=True, exist_ok=True)
    real_git = real_git or shutil.which("git") or "/usr/bin/git"
    git_body = _GIT_STUB.replace("__REAL_GIT__", real_git)
    if clone_source:
        tree, sha, url = clone_source
        git_body = (_GIT_CLONE_STUB.replace("__REAL_GIT__", real_git)
                    .replace("__PINNED_TREE__", str(tree))
                    .replace("__PINNED_SHA__", str(sha))
                    .replace("__CANON_URL__", str(url)))
    for name, body in (
        ("openclaw", _OPENCLAW_STUB),
        ("curl", _CURL_STUB),
        ("git", git_body),
    ):
        p = shim / name
        p.write_text(body.replace("__LOG__", str(log_path)), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


# ---------------------------------------------------------------- sandbox ----
class Sandbox(object):
    """A disposable fake box. Redirects every install target into scratch.

    Usage:
        with Sandbox() as sb:
            subprocess.run([bash, installer], env=sb.env, ...)
    """

    def __init__(self, prefix=SCRATCH_PREFIX, keep=False, base_dir=None,
                 clone_source=None):
        self.prefix = prefix
        self.keep = keep
        self.base_dir = base_dir
        self.clone_source = clone_source
        self.dir = None
        self.env = {}
        self.shim_log = None

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix=self.prefix,
                                         dir=str(self.base_dir or "/tmp")))
        home = self.dir / "home"
        oc = self.dir / "oc"
        skills = self.dir / "skills"
        claude = self.dir / "claude"
        tmp = self.dir / "tmp"
        for d in (home, oc, skills, claude, tmp):
            d.mkdir(parents=True, exist_ok=True)
        self.shim_log = self.dir / "shim.log"
        self.shim_log.write_text("", encoding="utf-8")
        shim = build_shims(self.dir / "shims", self.shim_log,
                           clone_source=self.clone_source)

        env = dict(os.environ)
        env.update({
            "HOME": str(home),
            "OC_CONFIG": str(oc),
            "SKILLS_DIR": str(skills),
            "CLAUDE_CONFIG_DIR": str(claude),
            "TMPDIR": str(tmp),
            "PATH": "%s:%s" % (shim, env.get("PATH", "")),
            "PYTHONDONTWRITEBYTECODE": "1",
            # belt-and-suspenders: any child that still resolves a network tool
            # through a full path is still blocked by these inert proxies.
            "GIT_TERMINAL_PROMPT": "0",
            "CANARY_SANDBOX": str(self.dir),
        })
        self.env = env
        return self

    def __exit__(self, *exc):
        if not self.keep and self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
        return False

    # convenience accessors
    @property
    def root(self):
        return self.dir

    def shim_entries(self):
        try:
            return [l for l in self.shim_log.read_text(encoding="utf-8").splitlines()
                    if l.strip()]
        except OSError:
            return []


# ------------------------------------------------------------ run helpers ----
def run_capture(cmd, env, cwd=None, timeout=600):
    """Run a command in the sandbox env; capture rc/stdout/stderr. Never throws."""
    try:
        p = subprocess.run(cmd, env=env, cwd=cwd, timeout=timeout,
                           capture_output=True, text=True)
        return {"cmd": [str(c) for c in cmd], "rc": p.returncode,
                "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
    except subprocess.TimeoutExpired as e:
        return {"cmd": [str(c) for c in cmd], "rc": 124, "stdout": "",
                "stderr": "timeout after %ss" % timeout}
    except OSError as e:
        return {"cmd": [str(c) for c in cmd], "rc": 127, "stdout": "",
                "stderr": "os error: %s" % e}


def summarize_checks(results):
    """results: {name: {"ok": bool, "detail": str}} -> (passed, failed, total)."""
    passed = [k for k, v in results.items() if v.get("ok")]
    failed = [k for k, v in results.items() if not v.get("ok")]
    return passed, failed, len(results)


# ------------------------------------------------------- pinned sources ----
def materialize_revision(repo, revision, dest):
    """Extract EXACTLY `revision` from a local checkout into `dest`. No network.

    Returns (ok, detail). Fail closed: a revision that is not in the local object
    database is refused rather than silently substituted with HEAD, so a canary
    can never claim it installed a revision it never checked out.
    """
    repo = Path(repo)
    dest = Path(dest)
    if not _is_sha(revision):
        return False, "revision is not a 40-hex sha: %r" % (revision,)
    if not (repo / ".git").exists():
        return False, "not a git checkout: %s" % repo
    v = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify",
                        revision + "^{commit}"], capture_output=True, text=True)
    if v.returncode != 0:
        return False, "revision %s not present in %s" % (revision, repo)
    got = v.stdout.strip()
    if got != revision:
        return False, "revision %s resolved to %s (ref, not an exact sha)" % (
            revision, got)
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as tf:
        a = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar",
                            "-o", tf.name, got], capture_output=True, text=True)
        if a.returncode != 0:
            return False, "git archive failed: %s" % a.stderr.strip()[:300]
        t = subprocess.run(["tar", "-x", "-C", str(dest), "-f", tf.name],
                           capture_output=True, text=True)
        if t.returncode != 0:
            return False, "tar extract failed: %s" % t.stderr.strip()[:300]
    return True, "%s @ %s -> %s" % (repo.name, got[:12], dest)


SKIP_DIRS = (".git", "__pycache__")


def manifest_tree(root, skip_dirs=SKIP_DIRS):
    """{relative posix path: sha256} for every regular file under root."""
    root = Path(root)
    man = {}
    if not root.is_dir():
        return man
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        man[rel.as_posix()] = sha256_file(p)
    return man


def manifest_digest(manifest):
    """Order-free sha256 over a {path: digest} manifest."""
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def diff_manifests(old, new):
    """Return (added, changed, removed) as sorted lists of paths."""
    old = old or {}
    new = new or {}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    return added, changed, removed


#: The Skill 75 tree's real shipped shape. A manifest that is non-empty but does
#: not carry these cannot be a real install of the skill — it is a placeholder or
#: a single seeded fixture file. "Non-empty" alone is a fail-open test.
REQUIRED_SKILL_TOP_LEVEL = ("SKILL.md", "scripts")
MIN_SKILL_FILES = 100


def _manifest_shape_problems(manifest, min_files, required):
    problems = []
    if len(manifest) < min_files:
        problems.append("manifest has %d file(s), below the %d this skill tree "
                        "ships — refusing a placeholder/single-file install"
                        % (len(manifest), min_files))
    for top in required:
        if not any(k == top or k.startswith(top + "/") for k in manifest):
            problems.append("manifest is missing the required top-level path %r"
                            % top)
    return problems


def verify_manifest(root, manifest, ignore=(), min_files=MIN_SKILL_FILES,
                    required=REQUIRED_SKILL_TOP_LEVEL):
    """Recompute an installed tree against a recorded manifest.

    Returns (ok, problems). A manifest is refused unless it can only be the
    result of a real install: it must be non-empty AND carry at least `min_files`
    entries AND include every path in `required`. "Non-empty" alone is not enough
    — one seeded fixture file would otherwise pass, which is exactly how a tree
    where the installer did nothing got blessed.
    `ignore` names paths the caller seeded deliberately (user state that is not
    installer output); they are named in the receipt, never silently dropped.
    """
    root = Path(root)
    ignore = set(ignore or ())
    if not isinstance(manifest, dict) or not manifest:
        return False, ["manifest is empty — nothing to verify"]
    bad = [k for k, v in manifest.items() if not _is_sha256(v)]
    if bad:
        return False, ["manifest carries a non-sha256 digest for %s" % k
                       for k in bad[:10]]
    shape = _manifest_shape_problems(manifest, min_files, required)
    if shape:
        return False, shape
    problems = []
    for rel, want in sorted(manifest.items()):
        p = root / rel
        if not p.is_file():
            problems.append("MISSING %s" % rel)
            continue
        got = sha256_file(p)
        if got != want:
            problems.append("CHANGED %s (manifest %s != installed %s)"
                            % (rel, want[:12], got[:12]))
    for rel in sorted(set(manifest_tree(root)) - set(manifest) - ignore):
        problems.append("EXTRA %s (not in manifest)" % rel)
    return (not problems), problems


def compare_to_source(installed, source, ignore=()):
    """Is the installed tree the pinned source tree, in BOTH directions?

    Returns (ok, detail). A source file that never got installed fails (the
    installer did less than the source requires), an installed file that is not
    in the source fails (placeholder or foreign content), and a differing digest
    fails. Checking only one direction lets a one-file tree satisfy a 858-file
    source, so completeness is enforced here rather than in a separate check.
    """
    ignore = set(ignore or ())
    not_installed = sorted(set(source) - set(installed) - ignore)
    absent_from_source = sorted(set(installed) - set(source) - ignore)
    differing = sorted(k for k in set(installed) & set(source)
                       if installed[k] != source[k])
    detail = ("%d installed / %d source; %d source file(s) NOT installed %s; "
              "%d installed file(s) absent-from-source %s; %d differing %s"
              % (len(installed), len(source), len(not_installed),
                 not_installed[:3], len(absent_from_source),
                 absent_from_source[:3], len(differing), differing[:3]))
    ok = (bool(installed) and not not_installed and not absent_from_source
          and not differing)
    return ok, detail


def distribution_manifest(dist, install_root, files, source):
    """The real distribution manifest: files + digests + install path + revision."""
    return {
        "schema": "blackceo.skill75.distribution-manifest/v1",
        "distribution": dist,
        "installed_path": str(install_root),
        "source": source,
        "file_count": len(files),
        "manifest_sha256": manifest_digest(files),
        "files": files,
    }


#: Where the loaded-source proof tool lives in the agents-skills tree. Printed,
#: never executed here: running it needs a live process and an execution GO.
RUNTIME_PROOF_HINT = ("<agents-skills>/S75-W07-U2/tools/runtime_proof.py")


def loaded_source_proof(manifest_path, install_root, runtime_proof=None,
                        ignore=()):
    """Validate a distribution manifest before the loaded-source proof runs.

    Prints (and returns) the exact runtime_proof.py command the acceptance run
    would execute, and independently recomputes every digest in the manifest so
    a missing, empty or tampered manifest is refused here rather than being
    handed to a proof step that would trust it.
    """
    cmd = ("python3 %s record --manifest %s --root %s"
           % (runtime_proof or RUNTIME_PROOF_HINT, manifest_path, install_root))
    mp = Path(manifest_path)
    if not mp.is_file():
        return False, "manifest missing: %s" % mp, cmd
    try:
        doc = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, "manifest unreadable: %s" % e, cmd
    files = doc.get("files")
    if not isinstance(files, dict) or not files:
        return False, "manifest has no files (empty/placeholder manifest refused)", cmd
    ok, problems = verify_manifest(install_root, files, ignore=ignore)
    if not ok:
        return False, ("manifest does not match the installed tree: "
                       + "; ".join(problems[:5])), cmd
    return True, "%d files verified against %s" % (len(files), mp), cmd
