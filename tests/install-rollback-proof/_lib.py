"""Shared helpers for the W4-04-U1 clean-install / migration / rollback proof.

Stdlib only. Never imported as a test (runner executes test_*.py only).

Scratch lives under /tmp/<box-slug>-W4-04-U1-* per lane hygiene; each test
removes the scratch it owns in a finally block. Reads outside this folder are
read-only: the two distribution sources and their git history.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[1]                      # drama-song-factory-build/

UNIT_ID = "W4-04-U1"
SCHEMA = "blackceo.install-rollback-proof/v1"
BOX_SLUG = os.environ.get("BOX_SLUG", "local")
TMP_PREFIX = "%s-%s-" % (BOX_SLUG, UNIT_ID)

# Distribution A — OpenClaw twin, home onboarding repo (has SKILL.md).
ONB_REPO = Path(os.environ.get(
    "DSAF_ONBOARDING_REPO", str(Path.home() / "openclaw-onboarding")))
OPENCLAW_DIR = "75-drama-song-ad-factory"
OPENCLAW_SRC = Path(os.environ["DSAF_OPENCLAW_SKILL"]) if os.environ.get(
    "DSAF_OPENCLAW_SKILL") else ONB_REPO / OPENCLAW_DIR

# Distribution B — Claude-Nine / Claude Code twin, inside the 999 repo.
NINE_REPO = Path(os.environ.get(
    "DSAF_NINE_REPO", str(BUILD / "999-setup")))
DEPT_SLUG = "drama-song-ad-factory"
NINE_SRC = Path(os.environ["DSAF_999_SKILL"]) if os.environ.get(
    "DSAF_999_SKILL") else NINE_REPO / ".claude" / "skills" / DEPT_SLUG

# Fixed pre-current release points used as the migration baseline.
# A: skill-version.txt == v1.0.0, SKILL.md not yet shipped.
OLD_A_COMMIT = "f2b99f2927a9d731918f33eb9e8c033b670f324d"
# B: CONTROL/bundled-skills.txt has no drama-song-ad-factory entry.
OLD_B_COMMIT = "8203088763d1bb93c402dc88db0c916e0a099f78"

RECEIPTS = HERE / "receipts"
EVIDENCE = HERE / "evidence"
FIXTURES = HERE / "fixtures"
RELEASE_CHECK = HERE / "release_check.py"

# Boxes these tests build. Layout mirrors a fresh box holding both installs:
#   <box>/openclaw-onboarding/<dir>/          distribution A
#   <box>/999-setup/.claude/skills/<slug>/    distribution B
#   <box>/999-setup/CONTROL/bundled-skills.txt    999 install manifest
#   <box>/999-setup/THIRD_PARTY_NOTICES.md    notices shipped with B
def box_paths(box):
    box = Path(box)
    return {
        "box": box,
        "a": box / "openclaw-onboarding" / OPENCLAW_DIR,
        "b": box / "999-setup" / ".claude" / "skills" / DEPT_SLUG,
        "registry": box / "999-setup" / "CONTROL" / "bundled-skills.txt",
        "notices_b": box / "999-setup" / "THIRD_PARTY_NOTICES.md",
        "core_a": box / "openclaw-onboarding" / OPENCLAW_DIR / "scripts" / "core",
        "core_b": box / "999-setup" / ".claude" / "skills" / DEPT_SLUG
                  / "scripts" / "core",
        "factory_a": box / "openclaw-onboarding" / OPENCLAW_DIR / "scripts"
                     / "core" / "intake_preflight" / "factory.py",
        "factory_b": box / "999-setup" / ".claude" / "skills" / DEPT_SLUG
                     / "scripts" / "core" / "intake_preflight" / "factory.py",
    }


def mktmp(tag):
    """Box temp dir: /tmp/<box>-W4-04-U1-<tag>-XXXX."""
    return Path(tempfile.mkdtemp(prefix=TMP_PREFIX + tag + "-", dir="/tmp"))


def rm_tmp(path):
    if not path:
        return
    p = Path(path)
    if p.is_dir() and p.name.startswith(TMP_PREFIX):
        shutil.rmtree(p, ignore_errors=True)


def check(name, cond, detail=""):
    """Record one evidence check; assert so a failure stops the suite."""
    row = {"check": name, "pass": bool(cond)}
    if detail != "":
        row["detail"] = detail
    CHECKS.append(row)
    assert cond, "FAILED: %s%s" % (name, (" -- " + str(detail)) if detail else "")
    print("ok: %s" % name)


CHECKS = []


def _ignore(_dir, names):
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]


def copy_tree(src, dst):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=_ignore)
    return dst


def tree_digest(root):
    """(sha256, [relpaths]): content digest, path + file sha per entry.

    Mode bits are not part of the digest — nothing in either distribution is
    executed directly; every entrypoint runs as `python3 <path>`.
    """
    root = Path(root)
    h = hashlib.sha256()
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if "__pycache__" in parts or rel.endswith(".pyc"):
            continue
        fh = hashlib.sha256(p.read_bytes()).hexdigest()
        h.update(("%s\0%s\n" % (rel, fh)).encode())
        files.append(rel)
    return h.hexdigest(), files


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo)] + [str(a) for a in args],
                         capture_output=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError("git %s failed in %s: %s"
                           % (" ".join(str(a) for a in args), repo,
                              out.stderr.decode("utf-8", "replace").strip()))
    if binary:
        return out.stdout
    return out.stdout.decode("utf-8", "replace")


def git_head(repo):
    return git(repo, "rev-parse", "HEAD").strip()


def git_files(repo, commit, prefix):
    """Blob paths under `prefix` at `commit`, relative to that prefix."""
    raw = git(repo, "ls-tree", "-r", "--name-only", commit, "--", prefix)
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(prefix + "/"):
            out.append(line[len(prefix) + 1:])
    return sorted(out)


def git_read(repo, commit, path):
    return git(repo, "show", "%s:%s" % (commit, path), binary=True)


def git_install(repo, commit, prefix, dest):
    """Materialise `prefix` at `commit` into `dest` (replaces dest)."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for rel in git_files(repo, commit, prefix):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_read(repo, commit, "%s/%s" % (prefix, rel)))
    return dest


def build_fresh_box(box):
    """Clean install of BOTH distributions from their current sources."""
    p = box_paths(box)
    rm = Path(box)
    if rm.exists():
        shutil.rmtree(rm)
    copy_tree(OPENCLAW_SRC, p["a"])
    copy_tree(NINE_SRC, p["b"])
    p["registry"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(NINE_REPO / "CONTROL" / "bundled-skills.txt", p["registry"])
    shutil.copy2(NINE_REPO / "THIRD_PARTY_NOTICES.md", p["notices_b"])
    return p


def build_migration_box(box):
    """Install box in its PRE-current state (the migration baseline).

    A at OLD_A_COMMIT (v1.0.0, no SKILL.md), B skill + 999 registry at
    OLD_B_COMMIT (registry has no drama-song-ad-factory entry).
    """
    p = box_paths(box)
    rm = Path(box)
    if rm.exists():
        shutil.rmtree(rm)
    git_install(ONB_REPO, OLD_A_COMMIT, OPENCLAW_DIR, p["a"])
    git_install(NINE_REPO, OLD_B_COMMIT, ".claude/skills/" + DEPT_SLUG, p["b"])
    p["registry"].parent.mkdir(parents=True, exist_ok=True)
    p["registry"].write_bytes(
        git_read(NINE_REPO, OLD_B_COMMIT, "CONTROL/bundled-skills.txt"))
    shutil.copy2(NINE_REPO / "THIRD_PARTY_NOTICES.md", p["notices_b"])
    return p


def _file_map(root):
    """{relpath: sha256} for one install tree (content only)."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if "__pycache__" in parts or rel.endswith(".pyc"):
            continue
        out[rel] = file_sha(p)
    return out


def migrate_box(box):
    """Upgrade a box install to the current release of BOTH distributions.

    Returns the A-tree digest change plus added/removed/changed paths, and
    the 999 registry digest change (B's skill folder is compared too).
    """
    p = box_paths(box)
    before_a = _file_map(p["a"])
    before_b = _file_map(p["b"])
    before_reg = file_sha(p["registry"])

    git_install(ONB_REPO, git_head(ONB_REPO), OPENCLAW_DIR, p["a"])
    git_install(NINE_REPO, git_head(NINE_REPO), ".claude/skills/" + DEPT_SLUG,
                p["b"])
    p["registry"].write_bytes(
        git_read(NINE_REPO, git_head(NINE_REPO), "CONTROL/bundled-skills.txt"))

    after_a = _file_map(p["a"])
    after_b = _file_map(p["b"])
    return {
        "openclaw_before_sha256": _map_sha(before_a),
        "openclaw_after_sha256": _map_sha(after_a),
        "nine_before_sha256": _map_sha(before_b),
        "nine_after_sha256": _map_sha(after_b),
        "registry_before_sha256": before_reg,
        "registry_after_sha256": file_sha(p["registry"]),
        "added": sorted(set(after_a) - set(before_a)),
        "removed": sorted(set(before_a) - set(after_a)),
        "changed": sorted(r for r in set(before_a) & set(after_a)
                          if before_a[r] != after_a[r]),
        "nine_changed": sorted(
            r for r in set(before_b) | set(after_b)
            if before_b.get(r) != after_b.get(r)),
    }


def _map_sha(filemap):
    h = hashlib.sha256()
    for rel in sorted(filemap):
        h.update(("%s\0%s\n" % (rel, filemap[rel])).encode())
    return h.hexdigest()


def rollback_box(box, snapshot):
    """Restore a box install from a pre-migration snapshot directory.

    `snapshot` holds the same box layout captured before migrate_box().
    Returns the restored A tree digest and registry digest.
    """
    p = box_paths(box)
    s = box_paths(snapshot)
    copy_tree(s["a"], p["a"])
    copy_tree(s["b"], p["b"])
    shutil.copy2(s["registry"], p["registry"])
    digest, _ = tree_digest(p["a"])
    return digest, file_sha(p["registry"])


def snapshot_box(box, dest):
    """Byte-copy the install-relevant parts of a box (rollback source)."""
    p = box_paths(box)
    s = box_paths(dest)
    rm = Path(dest)
    if rm.exists():
        shutil.rmtree(rm)
    copy_tree(p["a"], s["a"])
    copy_tree(p["b"], s["b"])
    s["registry"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p["registry"], s["registry"])
    shutil.copy2(p["notices_b"], s["notices_b"])
    return dest


def make_run_state(core_dir, db_path):
    """Create a local run-state DB using the core at `core_dir`.

    Local state lives OUTSIDE the install tree (directive 24.4: caller-chosen
    DB path), so it must survive a distribution upgrade untouched.
    """
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import state_store as s;"
        "st = s.Store(%r);"
        "st.init_run('w404-run', ['intake', 'preflight', 'qc']);"
        "st.transition('w404-run', 'intake', 'READY', 'w404');"
        "st.close();"
        "print('state-built')"
    ) % (str(core_dir), str(db_path))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=60)
    if out.returncode != 0 or "state-built" not in out.stdout:
        raise RuntimeError("run-state build failed: %s" % out.stderr.strip())
    return db_path


def run_state_digest(db_path):
    """sha256 over ordered (stage, state, version, owner, reason) rows."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT run_id, stage, state, version, owner, reason"
            " FROM stages ORDER BY run_id, stage").fetchall()
        events = con.execute(
            "SELECT run_id, stage, kind, detail FROM events"
            " ORDER BY run_id, stage, kind, detail").fetchall()
        meta = con.execute("SELECT k, v FROM meta ORDER BY k").fetchall()
    finally:
        con.close()
    blob = json.dumps([rows, events, meta], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest(), len(rows)


def run_release_check(box, require_receipts=False, receipt=None,
                      receipts_dir=None):
    """Run release_check.py against a box; return (exit, receipt-dict|None)."""
    cmd = [sys.executable, str(RELEASE_CHECK), "--box", str(box), "--json"]
    if require_receipts:
        cmd.append("--require-receipts")
    if receipt:
        cmd += ["--receipt", str(receipt)]
    if receipts_dir:
        cmd += ["--receipts-dir", str(receipts_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    data = None
    if receipt and Path(receipt).is_file():
        data = json.loads(Path(receipt).read_text())
    elif proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            data = None
    return proc.returncode, data, proc.stdout, proc.stderr


def write_receipt(name, obj):
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    path = RECEIPTS / name
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    print("receipt: %s" % path)
    return path


def stamp(obj):
    obj.setdefault("schema", SCHEMA)
    obj.setdefault("unit_id", UNIT_ID)
    obj.setdefault("generated_at", time.strftime(
        "%Y-%m-%dT%H:%M:%S%z"))
    return obj
