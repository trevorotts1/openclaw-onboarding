"""Safe installation upgrade for Skill 72 on existing clients (MG-041).

WHY THIS EXISTS
    The fleet updater (update-skills.sh) delivers a new release by
    replacing each numbered skill directory wholesale (rm -rf + cp -r).
    That is safe for system code and fatal for anything client-owned that
    happens to live inside the skill tree, and it knows nothing about
    Skill 72's runtime pointer, its job storage root, or a render that is
    in flight right now. This tool is NOT a second installer: the
    repository mechanism still delivers the release, and the shared
    provisioner (shared-utils/motion-render-runtime/provision.sh) still
    builds and probes engine runtimes. This tool is the Skill 72 upgrade
    transaction that wraps the swap:

      discover   inventory the installation (skill, runtime, jobs)
      prepare    snapshot client-owned files to a vault, back up the
                 installed tree, stage the new tree, run readiness
                 checks, verify a staged runtime version, optionally
                 migrate V1 job manifests into new V2 revisions
      promote    atomically swap the skill tree, flip the runtime
                 pointer, restore client files, install compatibility
                 wrappers for any removed documented command, then
                 post-verify; any failure rolls the whole transaction
                 back automatically
      rollback   manually undo a promoted transaction from its journal
      upgrade    prepare + promote in one invocation
      status     report the last transaction and the runtime pointer

SAFETY RULES (each is enforced in code, not just documented)
    * The tool never deletes a client file. Snapshots are copies. The
      only trees removed are this tool's own staging and retired copies
      inside the transaction directory, and only on explicit cleanup.
    * Client-owned data inside the skill tree = the protected prefixes
      (client-data/, brand/, style-cards/, jobs/, renders/, history/)
      plus ANY file the new source tree does not ship. Unknown files are
      protected by default, never silently dropped.
    * Manifests are migrated into NEW revisions (a sibling .v2 job
      scaffold via scripts/migrate_manifest.py); the V1 original is
      hashed before and after and must be byte-identical.
    * Promotion is refused while a render is recorded active with a
      live process (finding MG_INSTALL_RENDER_ACTIVE). The tool makes
      no network calls at all, so no auto-upgrade can start mid-render
      through this path.
    * The runtime pointer flip reuses the provisioner's semantics:
      temp symlink + atomic rename; runtime versions are never deleted,
      so rollback is a flip back, never a rebuild.
    * A failed promotion restores the pre-upgrade skill tree and the
      pre-upgrade runtime pointer and writes a receipt saying so
      (status rolled_back). Job data under the storage root is never
      written by promote or rollback at all.

STATE LAYOUT (all under the skills root, outside the skill tree)
    .skill72-upgrade/
      transactions/<txn-id>/
        journal.json / journal.json.prev   atomic, MG-027 style
        vault/                             client file snapshot + hashes
        backup-skill/                      full copy of the old tree
        staging-skill/                     staged new tree (pre-promote)
        retired-skill/                     the old tree after the swap
        runtime-lock-before.json           pre-upgrade active lock copy
        receipt.json
      last-receipt.json

EXIT CODES
    0  success
    2  usage error or missing operator input (mirrors migrate_manifest)
    3  refused: a render is active
    4  readiness failed; nothing was promoted
    5  promotion failed and was rolled back
    6  rollback itself failed (loud; journal preserved for forensics)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR_NAME = "72-motion-video-plus"
RUNTIME_REL = Path("shared-utils") / "motion-render-runtime"
STATE_DIR_NAME = ".skill72-upgrade"
PROTECTED_PREFIXES = ("client-data/", "brand/", "style-cards/", "jobs/", "renders/", "history/")
MANDATORY_ENGINES = ("remotion", "hyperframes")

# Mirrors the required-file list in verify.sh (the install verifier).
REQUIRED_FILES = (
    "SKILL.md", "skill-version.txt", "MASTERDOC.md", "INSTRUCTIONS.md",
    "INSTALL.md", "QC.md", "REPO-INTEGRATION.md", "CORE_UPDATES.md",
    "references/authority-map.md", "references/animation-contract.md",
    "references/motion-grammar.md", "references/critique-protocol.md",
    "references/directors-brief-template.md", "references/manifest-schema.json",
    "references/beats-schema.json", "references/brand-bible-template.md",
    "references/fish-audio-tts.md", "references/untested-alternatives.md",
    "references/pre-production/01-studio-setup.md",
    "references/pre-production/02-house-rules.md",
    "references/pre-production/03-brand-assets.md",
    "references/pre-production/04-the-one-liner.md",
    "references/pre-production/05-steal-the-grammar.md",
    "references/pre-production/06-directors-brief.md",
    "assets/example-manifest.json",
    "scripts/render.js", "scripts/preflight.js", "scripts/tts.py",
    "scripts/verify-determinism.js", "scripts/lint-grammar.py",
    "scripts/synth-score.py", "scripts/beat-grid.py", "scripts/synth-sfx.py",
    "scripts/critique-bundle.sh", "scripts/assemble.sh", "scripts/qc.sh",
    "scripts/sweep-chromium.sh",
    "repo-integration/skill-department-map-entry.json",
)

# Documented commands (INSTALL.md / INSTRUCTIONS.md). If an upgrade ever
# removes one, promote installs a same-language wrapper that fails with a
# clear supported-migration error naming the replacement, exit code 3.
# A bare breakage is the one outcome this registry exists to prevent.
DOCUMENTED_COMMANDS = (
    {"path": "verify.sh", "kind": "sh",
     "replacement": "the install/update verification contract in INSTALL.md; restore verify.sh from the release tree"},
    {"path": "scripts/render.js", "kind": "js",
     "replacement": "the V2 render path through the production adapters (INSTRUCTIONS.md stages 10 to 12); the legacy renderer is retired"},
    {"path": "scripts/preflight.js", "kind": "js",
     "replacement": "the V2 resource preflight in the runtime adapter layer"},
    {"path": "scripts/verify-determinism.js", "kind": "js",
     "replacement": "the V2 determinism verification in the runtime test chain"},
    {"path": "scripts/tts.py", "kind": "py",
     "replacement": "narration measurement per INSTRUCTIONS.md stage 6, using scripts/tts.py from the release tree"},
    {"path": "scripts/lint-grammar.py", "kind": "py",
     "replacement": "the engine-aware lint in the V2 runtime (runtime/src/lint)"},
    {"path": "scripts/synth-score.py", "kind": "py",
     "replacement": "declared audio source assets per INSTRUCTIONS.md stage 13"},
    {"path": "scripts/synth-sfx.py", "kind": "py",
     "replacement": "declared audio source assets per INSTRUCTIONS.md stage 13"},
    {"path": "scripts/beat-grid.py", "kind": "py",
     "replacement": "the compiled timeline from the V2 timeline compiler"},
    {"path": "scripts/critique-bundle.sh", "kind": "sh",
     "replacement": "the V2 review bundle produced at INSTRUCTIONS.md stage 10"},
    {"path": "scripts/assemble.sh", "kind": "sh",
     "replacement": "assembly through the V2 production adapters"},
    {"path": "scripts/qc.sh", "kind": "sh",
     "replacement": "the V2 QC gate at INSTRUCTIONS.md stage 14, plus python3 scripts/motion_contracts.py validate for package checks"},
    {"path": "scripts/sweep-chromium.sh", "kind": "sh",
     "replacement": "the shared runtime process cleanup in shared-utils/motion-render-runtime"},
    {"path": "scripts/migrate_manifest.py", "kind": "py",
     "replacement": "no replacement exists; V1 jobs cannot migrate without it. Restore scripts/migrate_manifest.py from the release tree"},
    {"path": "scripts/motion_contracts.py", "kind": "py",
     "replacement": "no replacement exists; V2 job validation requires it. Restore scripts/motion_contracts.py from the release tree"},
    {"path": "scripts/prepare_assets.py", "kind": "py",
     "replacement": "the asset preparation layer described in references/asset-intake.md"},
    {"path": "scripts/validate_storyboard.py", "kind": "py",
     "replacement": "the storyboard validation in the V2 planner layer"},
    {"path": "scripts/check_style_frames.py", "kind": "py",
     "replacement": "the style-frame approval gate at INSTRUCTIONS.md stages 4 and 11"},
)

EM_DASH = b"\xe2\x80\x94"  # the em dash character, as bytes; never literal in this file
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mp3", ".wav", ".bin", ".ico", ".pdf"}


# ---------------------------------------------------------------------------
# Small helpers (MG-027 conventions: atomic JSON writes with .prev rotation)
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with open(tmp, "r+b") as fh:
        os.fsync(fh.fileno())
    prev = path.with_name(path.name + ".prev")
    if path.exists():
        os.replace(path, prev)
    os.replace(tmp, path)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tree_files(root: Path) -> dict[str, Path]:
    """relpath -> path for every regular file under root (no symlink following)."""
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        out[path.relative_to(root).as_posix()] = path
    return out


def tree_hashes(root: Path) -> dict[str, str]:
    return {rel: sha256_file(p) for rel, p in tree_files(root).items()}


def skill_identity(tree: Path) -> dict:
    """Name + version facts from SKILL.md frontmatter and skill-version.txt."""
    info = {"name": None, "frontmatter_version": None, "file_version": None}
    skill_md = tree / "SKILL.md"
    if skill_md.is_file():
        in_front = False
        for line in skill_md.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == "---":
                in_front = not in_front
                continue
            if in_front and line.startswith("name:"):
                info["name"] = line.split(":", 1)[1].strip().strip('"')
            if in_front and line.startswith("version:"):
                info["frontmatter_version"] = line.split(":", 1)[1].strip().strip('"')
    version_file = tree / "skill-version.txt"
    if version_file.is_file():
        info["file_version"] = version_file.read_text(encoding="utf-8").strip().lstrip("vV")
    return info


def runtime_state(skills_root: Path) -> dict:
    rt = skills_root / RUNTIME_REL
    state = rt / ".runtime"
    info = {
        "runtime_dir": str(rt),
        "present": rt.is_dir(),
        "pointer_target": None,
        "versions": {},
        "active_lock_sha256": None,
    }
    current = state / "current"
    if current.is_symlink():
        info["pointer_target"] = os.readlink(current)
    versions = state / "versions"
    if versions.is_dir():
        for vdir in sorted(versions.iterdir()):
            if not vdir.is_dir():
                continue
            lock = read_json(vdir / "runtime-lock.json")
            info["versions"][vdir.name] = {
                "lock_result": (lock or {}).get("result") if isinstance(lock, dict) else None,
                "lock_present": lock is not None,
            }
    active_lock = state / "runtime-lock.json"
    if active_lock.is_file():
        info["active_lock_sha256"] = sha256_file(active_lock)
    return info


def active_renders(skills_root: Path) -> tuple[list[dict], list[dict]]:
    """(live, stale) render records from .runtime/active-renders.json."""
    record = skills_root / RUNTIME_REL / ".runtime" / "active-renders.json"
    doc = read_json(record)
    live: list[dict] = []
    stale: list[dict] = []
    if isinstance(doc, dict) and isinstance(doc.get("renders"), list):
        for entry in doc["renders"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("pid"), int):
                continue
            try:
                os.kill(entry["pid"], 0)
                live.append(entry)
            except (ProcessLookupError, PermissionError, OSError):
                stale.append(entry)
    return live, stale


def classify_jobs(storage_root: Path | None) -> list[dict]:
    jobs: list[dict] = []
    if storage_root is None or not storage_root.is_dir():
        return jobs
    for child in sorted(storage_root.iterdir()):
        manifest = child / "manifest.json"
        if not child.is_dir() or not manifest.is_file():
            continue
        doc = read_json(manifest)
        kind = "unknown"
        if isinstance(doc, dict):
            if doc.get("schema_version") == "2.0":
                kind = "v2"
            elif "video_name" in doc and "scenes" in doc:
                kind = "v1"
        jobs.append({"job": child.name, "kind": kind, "manifest": str(manifest)})
    return jobs


def default_storage_root() -> Path | None:
    env = os.environ.get("MOTION_STORAGE_ROOT")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Downloads" / "openclaw-master-files" / "motion-videos"
    docker = Path("/data/motion-videos")
    if docker.is_dir():
        return docker
    return Path.home() / "Downloads" / "openclaw-master-files" / "motion-videos"


# ---------------------------------------------------------------------------
# Readiness checks (mirror verify.sh, in-process): a staged tree that would
# fail the install verifier is never promoted.
# ---------------------------------------------------------------------------

DOCUMENTED_COMMAND_PATHS = {c["path"] for c in DOCUMENTED_COMMANDS}


def readiness_problems(tree: Path, expected_name: str | None,
                       allow_missing_commands: bool = False) -> list[str]:
    problems: list[str] = []
    for rel in REQUIRED_FILES:
        if not (tree / rel).is_file():
            if allow_missing_commands and rel in DOCUMENTED_COMMAND_PATHS:
                # Not a readiness failure: promote installs the
                # compatibility wrapper for a removed documented command
                # (MG-041), and post-verify then requires the path to
                # exist. Any OTHER missing required file is a failure.
                continue
            problems.append(f"missing required file: {rel}")
    identity = skill_identity(tree)
    if expected_name and identity["name"] != expected_name:
        problems.append(
            f"skill identity changed: SKILL.md name {identity['name']!r} != installed {expected_name!r}"
        )
    if identity["frontmatter_version"] != identity["file_version"]:
        problems.append(
            f"version lockstep broken: SKILL.md {identity['frontmatter_version']!r} "
            f"!= skill-version.txt {identity['file_version']!r}"
        )
    for rel, path in tree_files(tree).items():
        suffix = Path(rel).suffix.lower()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(f"unreadable file {rel}: {exc}")
            continue
        if suffix not in BINARY_SUFFIXES and EM_DASH in raw:
            problems.append(f"em dash found in {rel} (repo rule: none, anywhere)")
        if suffix == ".py":
            try:
                compile(raw.decode("utf-8"), rel, "exec")
            except (SyntaxError, UnicodeDecodeError) as exc:
                problems.append(f"python syntax error in {rel}: {exc}")
        elif suffix == ".json":
            try:
                json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append(f"invalid JSON in {rel}: {exc}")
        elif suffix == ".sh":
            bash = shutil.which("bash")
            if bash:
                proc = subprocess.run([bash, "-n", str(path)], capture_output=True, text=True)
                if proc.returncode != 0:
                    problems.append(f"shell syntax error in {rel}: {proc.stderr.strip()}")
        elif suffix == ".js":
            node = shutil.which("node")
            if node:
                proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
                if proc.returncode != 0:
                    problems.append(f"node syntax error in {rel}: {proc.stderr.strip()}")
    return problems


def runtime_version_ready(vdir: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if not vdir.is_dir():
        return False, [f"runtime version dir does not exist: {vdir}"]
    lock = read_json(vdir / "runtime-lock.json")
    if not isinstance(lock, dict):
        problems.append(f"runtime version {vdir.name} has no readable runtime-lock.json probe record")
        return False, problems
    if lock.get("result") != "pass":
        problems.append(
            f"runtime version {vdir.name} probe record result is {lock.get('result')!r}, not 'pass'"
        )
    engines = lock.get("engines")
    if isinstance(engines, dict):
        for engine in MANDATORY_ENGINES:
            status = (engines.get(engine) or {}).get("status")
            if status != "pass":
                problems.append(f"runtime version {vdir.name} engine {engine} status is {status!r}, not 'pass'")
    return not problems, problems


# ---------------------------------------------------------------------------
# Compatibility wrappers
# ---------------------------------------------------------------------------

def wrapper_body(command: dict) -> str:
    msg = (
        f"MG_INSTALL_COMMAND_REMOVED: {command['path']} was removed by the Skill 72 "
        f"upgrade. Supported replacement: {command['replacement']}. This wrapper was "
        f"installed by scripts/migrate_install.py so the old command fails clearly "
        f"instead of breaking silently."
    )
    if command["kind"] == "sh":
        return f"#!/bin/sh\necho {json.dumps(msg)} >&2\nexit 3\n"
    if command["kind"] == "py":
        return (
            '"""Compatibility wrapper installed by scripts/migrate_install.py (MG-041)."""\n'
            "import sys\n\n"
            f"print({msg!r}, file=sys.stderr)\n"
            "sys.exit(3)\n"
        )
    return (
        '"use strict";\n// Compatibility wrapper installed by scripts/migrate_install.py (MG-041).\n'
        f"console.error({json.dumps(msg)});\n"
        "process.exit(3);\n"
    )


# ---------------------------------------------------------------------------
# Transaction plumbing
# ---------------------------------------------------------------------------

def state_root(skills_root: Path) -> Path:
    return skills_root / STATE_DIR_NAME


def new_txn_id() -> str:
    return time.strftime("txn-%Y%m%d%H%M%S") + f"-{os.getpid()}"


def write_journal(txn_dir: Path, journal: dict) -> None:
    journal["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    atomic_write_json(txn_dir / "journal.json", journal)


def find_txn(skills_root: Path, txn_id: str | None) -> Path | None:
    txns = state_root(skills_root) / "transactions"
    if txn_id:
        candidate = txns / txn_id
        return candidate if (candidate / "journal.json").is_file() else None
    if not txns.is_dir():
        return None
    candidates = [d for d in sorted(txns.iterdir()) if (d / "journal.json").is_file()]
    return candidates[-1] if candidates else None


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def flip_pointer(skills_root: Path, version_id: str) -> None:
    """Atomic symlink flip, same semantics as provision.sh promote()."""
    state = skills_root / RUNTIME_REL / ".runtime"
    state.mkdir(parents=True, exist_ok=True)
    tmp = state / f"current.tmp-{os.getpid()}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(f"versions/{version_id}")
    os.replace(tmp, state / "current")


def install_runtime_version(skills_root: Path, staged: Path) -> None:
    versions = skills_root / RUNTIME_REL / ".runtime" / "versions"
    target = versions / staged.name
    if target.exists():
        existing = read_json(target / "runtime-lock.json")
        incoming = read_json(staged / "runtime-lock.json")
        if existing != incoming:
            raise RuntimeError(
                f"MG_INSTALL_RUNTIME_VERSION_CONFLICT: versions/{staged.name} already exists "
                "with a different probe record; refusing to overwrite a verified runtime"
            )
        return
    versions.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staged, target)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_discover(args) -> int:
    skills_root = Path(args.skills_root).resolve()
    skill_dir = skills_root / SKILL_DIR_NAME
    if not skill_dir.is_dir():
        emit({"status": "error", "finding": "MG_INSTALL_SKILL_MISSING",
              "message": f"no {SKILL_DIR_NAME} directory under {skills_root}"})
        return 2
    storage = Path(args.storage_root).resolve() if args.storage_root else default_storage_root()
    live_renders, stale_renders = active_renders(skills_root)
    payload = {
        "status": "ok",
        "skills_root": str(skills_root),
        "skill": {"dir": str(skill_dir), **skill_identity(skill_dir),
                  "file_count": len(tree_files(skill_dir))},
        "runtime": runtime_state(skills_root),
        "active_renders": {"live": live_renders, "stale": stale_renders},
        "storage_root": str(storage) if storage else None,
        "jobs": classify_jobs(storage),
        "protected_client_files_in_skill_tree": sorted(
            rel for rel in tree_files(skill_dir) if rel.startswith(PROTECTED_PREFIXES)
        ),
    }
    if args.json_out:
        atomic_write_json(Path(args.json_out), payload)
    emit(payload)
    return 0


def cmd_prepare(args, emit_result: bool = True) -> int:
    skills_root = Path(args.skills_root).resolve()
    skill_dir = skills_root / SKILL_DIR_NAME
    source = Path(args.source).resolve()
    if not skill_dir.is_dir() or not source.is_dir():
        emit({"status": "error", "finding": "MG_INSTALL_INPUT_MISSING",
              "message": "installed skill dir or source tree is missing"})
        return 2
    if args.migrate_jobs and (not args.mode or not args.company_id):
        emit({"status": "error", "finding": "MG_INSTALL_NEEDS_INPUT",
              "message": "--migrate-jobs requires --mode and --company-id; destination and owner are operator decisions, never guessed (same rule as migrate_manifest.py)"})
        return 2
    live_renders, _stale = active_renders(skills_root)
    if live_renders:
        emit({"status": "refused", "finding": "MG_INSTALL_RENDER_ACTIVE",
              "message": "a render is recorded active with a live process; the upgrade is refused, not deferred silently. Re-run when it finishes.",
              "active_renders": live_renders})
        return 3

    storage = Path(args.storage_root).resolve() if args.storage_root else default_storage_root()
    txn_id = new_txn_id()
    txn_dir = state_root(skills_root) / "transactions" / txn_id
    txn_dir.mkdir(parents=True)
    installed_identity = skill_identity(skill_dir)
    journal: dict = {
        "txn_id": txn_id,
        "state": "preparing",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "skills_root": str(skills_root),
        "storage_root": str(storage) if storage else None,
        "source": {"path": str(source), **skill_identity(source)},
        "installed_before": installed_identity,
        "runtime": {"pointer_before": runtime_state(skills_root)["pointer_target"],
                    "staged_version_id": None, "staged_source": None},
        "client_files": {},
        "client_conflicts": [],
        "superseded_commands": {},
        "storage_snapshot": {},
        "migrated_jobs": [],
        "findings": [],
    }
    write_journal(txn_dir, journal)

    # 1. Snapshot storage root (jobs are client data; prove they never move).
    if storage and storage.is_dir():
        journal["storage_snapshot"] = {
            str(p): sha256_file(p) for p in sorted(storage.rglob("*")) if p.is_file()
        }

    # 2. Classify and vault client-owned files inside the skill tree.
    source_files = set(tree_files(source))
    vault = txn_dir / "vault"
    for rel, path in tree_files(skill_dir).items():
        protected = rel.startswith(PROTECTED_PREFIXES)
        unknown = rel not in source_files
        if not protected and unknown and rel in DOCUMENTED_COMMAND_PATHS:
            # A documented command is system surface, never client data.
            # When the release no longer ships it, the installed copy is
            # superseded, not preserved: the full backup keeps it
            # byte-exact, and promote installs a named compatibility
            # wrapper at its path instead of silently keeping the stale
            # implementation live.
            journal["superseded_commands"][rel] = sha256_file(path)
            continue
        if not (protected or unknown):
            continue
        dest = vault / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        journal["client_files"][rel] = sha256_file(path)
        if protected and not unknown:
            journal["client_conflicts"].append(rel)
    write_journal(txn_dir, journal)

    # 3. Full backup of the installed tree (rollback source of last resort).
    shutil.copytree(skill_dir, txn_dir / "backup-skill", symlinks=True)

    # 4. Stage the new tree and run readiness on the STAGED copy.
    staging = txn_dir / "staging-skill"
    shutil.copytree(source, staging, symlinks=True)
    problems = readiness_problems(staging, installed_identity["name"],
                                  allow_missing_commands=True)
    journal["missing_commands"] = sorted(
        c["path"] for c in DOCUMENTED_COMMANDS if not (staging / c["path"]).is_file()
    )
    for rel in journal["missing_commands"]:
        journal["findings"].append(
            f"MG_INSTALL_COMMAND_REMOVED_IN_RELEASE: {rel} (a compatibility wrapper will be installed at promote)"
        )
    if skill_identity(source)["file_version"] == installed_identity["file_version"]:
        journal["findings"].append(
            "MG_INSTALL_ALREADY_CURRENT: source version equals installed version; proceeding as an idempotent re-sync"
        )

    # 5. Verify a staged runtime version, if one is part of this upgrade.
    if args.runtime_version_dir:
        staged_rt = Path(args.runtime_version_dir).resolve()
        ok, rt_problems = runtime_version_ready(staged_rt)
        problems.extend(rt_problems)
        if ok:
            journal["runtime"]["staged_version_id"] = staged_rt.name
            journal["runtime"]["staged_source"] = str(staged_rt)

    # Preserve the pre-upgrade active lock record for rollback.
    active_lock = skills_root / RUNTIME_REL / ".runtime" / "runtime-lock.json"
    if active_lock.is_file():
        shutil.copy2(active_lock, txn_dir / "runtime-lock-before.json")

    if problems:
        journal["state"] = "readiness_failed"
        journal["findings"].append("MG_INSTALL_READINESS_FAILED")
        journal["readiness_problems"] = problems
        write_journal(txn_dir, journal)
        emit({"status": "readiness_failed", "finding": "MG_INSTALL_READINESS_FAILED",
              "txn_id": txn_id, "problems": problems,
              "message": "nothing was promoted; the installed tree and runtime pointer are untouched"})
        return 4

    # 6. Migrate V1 job manifests into new revisions (originals untouched).
    if args.migrate_jobs:
        migrator_path = source / "scripts" / "migrate_manifest.py"
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("mg041_source_migrator", migrator_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        for job in classify_jobs(storage):
            if job["kind"] != "v1":
                continue
            manifest_path = Path(job["manifest"])
            before = sha256_file(manifest_path)
            out_dir = storage / f"{job['job']}.v2"
            # The migrator prints its own JSON summary; capture it so
            # this tool's stdout stays exactly one JSON document.
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                code = module.migrate(
                    manifest_path, mode=args.mode, company_id=args.company_id,
                    job_id=None, engine="remotion", out_dir=out_dir,
                )
            after = sha256_file(manifest_path)
            entry = {"job": job["job"], "source_manifest": str(manifest_path),
                     "source_sha256_before": before, "source_sha256_after": after,
                     "out_dir": str(out_dir), "migrator_exit": code,
                     "migrator_summary": captured.getvalue().strip()[:500]}
            if before != after:
                journal["state"] = "readiness_failed"
                journal["findings"].append("MG_INSTALL_MANIFEST_SOURCE_MODIFIED")
                journal.setdefault("readiness_problems", []).append(
                    f"the migrator modified its input {manifest_path}; aborting")
                write_journal(txn_dir, journal)
                emit({"status": "readiness_failed", "finding": "MG_INSTALL_MANIFEST_SOURCE_MODIFIED",
                      "txn_id": txn_id})
                return 4
            journal["migrated_jobs"].append(entry)
            if code != 0:
                journal["state"] = "readiness_failed"
                journal["findings"].append(
                    f"MG_INSTALL_JOB_MIGRATION_FAILED: {job['job']} (migrator exit {code}); "
                    "the job stays on the V1 compatibility path and nothing was promoted")
                write_journal(txn_dir, journal)
                emit({"status": "readiness_failed", "finding": "MG_INSTALL_JOB_MIGRATION_FAILED",
                      "txn_id": txn_id, "job": job["job"]})
                return 4
        # Migrated scaffolds are new client data: extend the snapshot.
        if storage and storage.is_dir():
            for p in sorted(storage.rglob("*")):
                if p.is_file():
                    journal["storage_snapshot"][str(p)] = sha256_file(p)
        write_journal(txn_dir, journal)

    journal["state"] = "prepared"
    write_journal(txn_dir, journal)
    if emit_result:
        emit({"status": "prepared", "txn_id": txn_id,
              "from_version": installed_identity["file_version"],
              "to_version": journal["source"]["file_version"],
              "client_files_vaulted": len(journal["client_files"]),
              "client_conflicts": journal["client_conflicts"],
              "runtime_staged": journal["runtime"]["staged_version_id"],
              "migrated_jobs": [m["job"] for m in journal["migrated_jobs"]],
              "findings": journal["findings"]})
    return 0


def _restore_client_files(skills_root: Path, txn_dir: Path, journal: dict) -> list[str]:
    """Copy vault files into the live tree and verify every hash."""
    problems: list[str] = []
    skill_dir = skills_root / SKILL_DIR_NAME
    vault = txn_dir / "vault"
    conflicts = set(journal.get("client_conflicts", []))
    for rel, expected in journal.get("client_files", {}).items():
        src = vault / rel
        if not src.is_file():
            problems.append(f"vault file missing: {rel}")
            continue
        target_rel = rel + ".client-preserved" if rel in conflicts else rel
        dest = skill_dir / target_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if sha256_file(dest) != expected:
            problems.append(f"restored client file hash mismatch: {target_rel}")
    return problems


def _undo_promotion(skills_root: Path, txn_dir: Path, journal: dict,
                    swapped: bool, flipped: bool) -> list[str]:
    """Best-effort full undo. Returns problems encountered while undoing."""
    problems: list[str] = []
    skill_dir = skills_root / SKILL_DIR_NAME
    if flipped:
        before = journal["runtime"].get("pointer_before")
        try:
            if before:
                version_id = before.split("/", 1)[1] if "/" in before else before
                flip_pointer(skills_root, version_id)
            lock_before = txn_dir / "runtime-lock-before.json"
            active_lock = skills_root / RUNTIME_REL / ".runtime" / "runtime-lock.json"
            if lock_before.is_file():
                shutil.copy2(lock_before, active_lock)
        except OSError as exc:
            problems.append(f"runtime pointer undo failed: {exc}")
    if swapped:
        try:
            failed = txn_dir / "failed-skill"
            n = 1
            while failed.exists():
                n += 1
                failed = txn_dir / f"failed-skill-{n}"
            if skill_dir.exists():
                os.replace(skill_dir, failed)
            os.replace(txn_dir / "retired-skill", skill_dir)
        except OSError as exc:
            problems.append(f"skill tree undo failed: {exc}")
    return problems


def cmd_promote(args) -> int:
    skills_root = Path(args.skills_root).resolve()
    txn_dir = find_txn(skills_root, args.txn)
    if txn_dir is None:
        emit({"status": "error", "finding": "MG_INSTALL_NO_TRANSACTION",
              "message": "no prepared transaction found; run prepare first"})
        return 2
    journal = read_json(txn_dir / "journal.json")
    if not isinstance(journal, dict) or journal.get("state") != "prepared":
        emit({"status": "error", "finding": "MG_INSTALL_TXN_STATE",
              "message": f"transaction state is {(journal or {}).get('state')!r}, not 'prepared'"})
        return 2
    live_renders, _stale = active_renders(skills_root)
    if live_renders:
        emit({"status": "refused", "finding": "MG_INSTALL_RENDER_ACTIVE",
              "message": "a render became active after prepare; promotion refused, transaction left prepared",
              "active_renders": live_renders})
        return 3

    skill_dir = skills_root / SKILL_DIR_NAME
    swapped = False
    flipped = False
    findings: list[str] = list(journal.get("findings", []))
    wrappers: list[str] = []
    try:
        # 1. Atomic skill-tree swap (renames on one filesystem).
        os.replace(skill_dir, txn_dir / "retired-skill")
        os.replace(txn_dir / "staging-skill", skill_dir)
        swapped = True
        journal["state"] = "promoting"
        write_journal(txn_dir, journal)

        # 2. Runtime pointer flip, only after the tree swap succeeds.
        staged_id = journal["runtime"].get("staged_version_id")
        if staged_id:
            install_runtime_version(skills_root, Path(journal["runtime"]["staged_source"]))
            flip_pointer(skills_root, staged_id)
            flipped = True
            lock_src = skills_root / RUNTIME_REL / ".runtime" / "versions" / staged_id / "runtime-lock.json"
            active_lock = skills_root / RUNTIME_REL / ".runtime" / "runtime-lock.json"
            tmp = active_lock.with_name("runtime-lock.json.tmp")
            shutil.copy2(lock_src, tmp)
            os.replace(tmp, active_lock)

        # 3. Restore client files into the new tree, hash-verified.
        problems = _restore_client_files(skills_root, txn_dir, journal)
        if problems:
            raise RuntimeError("client restore failed: " + "; ".join(problems))

        # 4. Compatibility wrappers for removed documented commands.
        for command in DOCUMENTED_COMMANDS:
            target = skill_dir / command["path"]
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(wrapper_body(command), encoding="utf-8")
                if command["kind"] == "sh":
                    target.chmod(0o755)
                wrappers.append(command["path"])
                findings.append(f"MG_INSTALL_COMMAND_WRAPPED: {command['path']}")

        # 5. Post-verify: readiness on the live tree, every documented
        #    command present (real file or wrapper), storage untouched,
        #    pointer where the journal says it should be.
        problems = readiness_problems(skill_dir, journal["installed_before"]["name"])
        if problems:
            raise RuntimeError("post-promotion readiness failed: " + "; ".join(problems))
        missing = [c["path"] for c in DOCUMENTED_COMMANDS
                   if not (skill_dir / c["path"]).is_file()]
        if missing:
            raise RuntimeError(
                "documented commands missing after wrapper pass: " + ", ".join(missing))
        storage = Path(journal["storage_root"]) if journal.get("storage_root") else None
        if storage and storage.is_dir():
            now = {str(p): sha256_file(p) for p in sorted(storage.rglob("*")) if p.is_file()}
            if now != journal["storage_snapshot"]:
                raise RuntimeError("storage root changed during promotion; job data must never move")
        if staged_id:
            target = runtime_state(skills_root)["pointer_target"]
            if target != f"versions/{staged_id}":
                raise RuntimeError(f"runtime pointer is {target!r} after flip, expected versions/{staged_id}")
    except (OSError, RuntimeError) as exc:
        undo_problems = _undo_promotion(skills_root, txn_dir, journal, swapped, flipped)
        journal["state"] = "rolled_back" if not undo_problems else "rollback_failed"
        journal["findings"] = findings + ["MG_INSTALL_PROMOTE_FAILED_ROLLED_BACK", str(exc)]
        write_journal(txn_dir, journal)
        receipt = {"status": journal["state"], "txn_id": journal["txn_id"],
                   "error": str(exc), "undo_problems": undo_problems,
                   "runtime_pointer": runtime_state(skills_root)["pointer_target"],
                   "skill_version": skill_identity(skill_dir)["file_version"]}
        atomic_write_json(txn_dir / "receipt.json", receipt)
        atomic_write_json(state_root(skills_root) / "last-receipt.json", receipt)
        emit(receipt)
        return 5 if not undo_problems else 6

    journal["state"] = "promoted"
    journal["findings"] = findings
    journal["runtime"]["pointer_after"] = runtime_state(skills_root)["pointer_target"]
    write_journal(txn_dir, journal)
    receipt = {"status": "upgraded", "txn_id": journal["txn_id"],
               "from_version": journal["installed_before"]["file_version"],
               "to_version": journal["source"]["file_version"],
               "runtime_pointer": {"before": journal["runtime"]["pointer_before"],
                                   "after": journal["runtime"]["pointer_after"]},
               "client_files_restored": len(journal["client_files"]),
               "client_conflicts": journal["client_conflicts"],
               "wrappers_installed": wrappers,
               "superseded_commands": sorted(journal.get("superseded_commands", {})),
               "migrated_jobs": [m["job"] for m in journal["migrated_jobs"]],
               "findings": findings}
    atomic_write_json(txn_dir / "receipt.json", receipt)
    atomic_write_json(state_root(skills_root) / "last-receipt.json", receipt)
    emit(receipt)
    return 0


def cmd_rollback(args) -> int:
    skills_root = Path(args.skills_root).resolve()
    txn_dir = find_txn(skills_root, args.txn)
    if txn_dir is None:
        emit({"status": "error", "finding": "MG_INSTALL_NO_TRANSACTION",
              "message": "no transaction found to roll back"})
        return 2
    journal = read_json(txn_dir / "journal.json")
    if not isinstance(journal, dict):
        emit({"status": "error", "finding": "MG_INSTALL_TXN_STATE", "message": "journal unreadable"})
        return 2
    state = journal.get("state")
    if state == "rolled_back":
        emit({"status": "rolled_back", "txn_id": journal["txn_id"],
              "message": "already rolled back; nothing to do"})
        return 0
    if state == "prepared":
        journal["state"] = "aborted"
        write_journal(txn_dir, journal)
        emit({"status": "aborted", "txn_id": journal["txn_id"],
              "message": "transaction was never promoted; staging and vault retained in the transaction directory"})
        return 0
    if state != "promoted":
        emit({"status": "error", "finding": "MG_INSTALL_TXN_STATE",
              "message": f"cannot roll back from state {state!r}"})
        return 2
    skill_dir = skills_root / SKILL_DIR_NAME
    problems: list[str] = []
    # Flip the runtime pointer back first (cheap, reversible), then the tree.
    flipped_now = runtime_state(skills_root)["pointer_target"] == journal["runtime"].get("pointer_after")
    swapped_now = (txn_dir / "retired-skill").is_dir()
    undo = _undo_promotion(skills_root, txn_dir, journal, swapped_now, flipped_now)
    problems.extend(undo)
    journal["state"] = "rolled_back" if not problems else "rollback_failed"
    write_journal(txn_dir, journal)
    receipt = {"status": journal["state"], "txn_id": journal["txn_id"],
               "runtime_pointer": runtime_state(skills_root)["pointer_target"],
               "skill_version": skill_identity(skill_dir)["file_version"],
               "undo_problems": problems}
    atomic_write_json(txn_dir / "receipt.json", receipt)
    atomic_write_json(state_root(skills_root) / "last-receipt.json", receipt)
    emit(receipt)
    return 0 if not problems else 6


def cmd_upgrade(args) -> int:
    code = cmd_prepare(args, emit_result=False)
    if code != 0:
        return code
    promote_args = argparse.Namespace(skills_root=args.skills_root, txn=None)
    return cmd_promote(promote_args)


def cmd_status(args) -> int:
    skills_root = Path(args.skills_root).resolve()
    txn_dir = find_txn(skills_root, None)
    journal = read_json(txn_dir / "journal.json") if txn_dir else None
    emit({"status": "ok",
          "skill": skill_identity(skills_root / SKILL_DIR_NAME),
          "runtime_pointer": runtime_state(skills_root)["pointer_target"],
          "last_transaction": journal})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Skill 72 safe installation upgrade transaction (MG-041). "
                    "Not an installer: it guards the swap the fleet updater performs.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--skills-root", required=True,
                       help="Directory containing 72-motion-video-plus/ and shared-utils/")
        p.add_argument("--storage-root", default=None,
                       help="Job storage root. Defaults to MOTION_STORAGE_ROOT or the platform convention.")

    p = sub.add_parser("discover"); common(p)
    p.add_argument("--json-out", default=None)
    p.set_defaults(fn=cmd_discover)

    p = sub.add_parser("prepare"); common(p)
    p.add_argument("--source", required=True, help="Extracted release copy of 72-motion-video-plus/")
    p.add_argument("--runtime-version-dir", default=None,
                   help="A fully staged, probe-passed runtime version directory to promote with the upgrade")
    p.add_argument("--migrate-jobs", action="store_true",
                   help="Migrate V1 job manifests in the storage root into new V2 revisions during prepare")
    p.add_argument("--mode", default=None)
    p.add_argument("--company-id", default=None)
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("promote"); common(p)
    p.add_argument("--txn", default=None)
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("rollback"); common(p)
    p.add_argument("--txn", default=None)
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("upgrade"); common(p)
    p.add_argument("--source", required=True)
    p.add_argument("--runtime-version-dir", default=None)
    p.add_argument("--migrate-jobs", action="store_true")
    p.add_argument("--mode", default=None)
    p.add_argument("--company-id", default=None)
    p.set_defaults(fn=cmd_upgrade)

    p = sub.add_parser("status"); common(p)
    p.set_defaults(fn=cmd_status)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
