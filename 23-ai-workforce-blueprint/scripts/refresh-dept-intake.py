#!/usr/bin/env python3
"""
refresh-dept-intake.py — UNCONDITIONAL DEPARTMENT-INTAKE MIRROR (FAULT-11 / F20).

────────────────────────────────────────────────────────────────────────────
THE GAP THIS CLOSES
────────────────────────────────────────────────────────────────────────────
refresh-dept-scripts.py mirrors every role-library department's scripts/ tree
onto a materialized department, unconditionally, every roll. Its own module
docstring says so explicitly:

    OUT OF SCOPE (explicitly, not an oversight)
    Only role-library department directories that have a `scripts/`
    subdirectory are enumerated. `templates/role-library/presentations/intake/`
    (and `intake-miniapp/`) are SIBLINGS of `scripts/`, not inside it, and are
    left untouched by this script — delivering them is a separate, undesigned
    gap.

No other writer fills that gap either:
  * scaffold_department() (create_role_workspaces.py) never touches intake/
    at all — its scripts/sops/dept-file scaffolding has no intake/ branch.
  * detect-stale-artifacts.py's manifest walk only tracks "role" / "dept" /
    "sop" / "persona" kinds (see load_current()); intake/ files carry none of
    those kinds, so they can never be queued STALE or MISSING, and
    refresh-stale-roles.py's drain (which only consumes role/sop/dept rows)
    can never reach them either.
  * colocate_presentation_entry() (U006, update-skills.sh) and
    _u001_presentations_manifest_placement (U001, update-skills.sh) both
    write into scripts/ and sops/ respectively — neither touches intake/.

Result: `templates/role-library/presentations/intake/deck-intake-questions.json`
can ship a new version (e.g. FAULT-11's two anti-fabrication questions) and it
NEVER reaches a materialized department's `intake/deck-intake-questions.json`
on any roll, on any box, ever — proven live 2026-08-20 (dept copy stuck at
v1.5.0/55 questions while the library shipped v1.6.0/57).

This script is a FOURTH, independent path modelled directly on
refresh-dept-scripts.py (same self-locating skill-dir resolution, same
resolve_dept_dir() department detection, same _iter_scripts_tree_files()
recursive walk, same apply/dry-run contract, same post-write independent
verification-from-disk, same pipe-immune STATUS line + JSON receipt) so a
future reader who already understands refresh-dept-scripts.py can read this
one by diffing against it, not by learning a new shape.

────────────────────────────────────────────────────────────────────────────
OWNERSHIP POLICY — three buckets, not two
────────────────────────────────────────────────────────────────────────────
scripts/ only ever needed two buckets (fleet-owned mirror vs. box-owned
additive) because nothing under scripts/ is both (a) versioned canonical
content a client is expected to receive updates to AND (b) something a client
box might legitimately have hand-edited. intake/'s question banks are
BOTH — that is exactly the tension F20's brief calls out: "Do not clobber a
customized live bank blindly." A pure always-overwrite policy (like scripts/
.py/.sh files) would risk destroying a client's edited wording. A pure
additive/missing-only policy (like scripts/ .json config) would leave every
box that already has a stale bank on disk (i.e. EVERY box today, since no
delivery path has ever existed) permanently stuck — the exact defect this
script exists to close would survive its own fix.

So three buckets:

  1. _INTAKE_MIRROR_SUFFIXES (fleet-owned, always-overwrite-when-diverged):
     .py/.sh/.js/.mjs/.tpl/.sha256/.pdf/.md/.template/.html/.toml/.sql —
     the interview-app/ deployable source (Cloudflare Worker + pages + bridge
     + tests). None of this is client-editable; the app's own README says so
     verbatim ("Edit the canonical JSONs, not the app"). Treated exactly like
     scripts/'s canonical suffixes.

  2. _CANONICAL_BANK_FILENAMES (provenance-gated refresh — NOT a suffix rule,
     an exact top-level filename match): "deck-intake-questions.json" and
     "upsell-questions.json" — the two files FAULT-11 is actually about. See
     "PROVENANCE-GATED BANK REFRESH" below.

  3. Everything else with suffix ".json" (crw._ADDITIVE_SCRIPT_SUFFIXES) —
     e.g. interview-app/deployed-r2/package.json, interview-app/pages/
     questions.json (a generated curated snapshot) — additive/missing-only,
     identical to scripts/'s .json policy. Never overwritten once present.

────────────────────────────────────────────────────────────────────────────
PROVENANCE-GATED BANK REFRESH (bucket 2)
────────────────────────────────────────────────────────────────────────────
For deck-intake-questions.json / upsell-questions.json, sha256(dest) is
compared against BOTH sha256(library) and a persistent provenance record this
script itself writes: <dept_dir>/intake/.BANK-PROVENANCE.json, keyed by
filename, recording {installed_sha256, installed_at, library_source_path} —
same "sidecar receipt sitting next to what it describes" shape as U001's
sops/MANIFEST-SOURCE.txt.

  * dest missing                                  -> FRESH INSTALL (copy).
  * sha256(dest) == sha256(library)                -> already current, no-op.
  * sha256(dest) != sha256(library), AND
    (no provenance record yet OR
     provenance.installed_sha256 == sha256(dest))  -> REFRESH. The box's copy
       is either (a) untouched since this mechanism last delivered it, or
       (b) has no delivery history at all — which, before this script
       existed, means EVERY box's intake bank, including the one FAULT-11 was
       filed against. Case (b) is deliberately resolved in favor of shipping
       the fix now rather than freezing every already-stale box forever: the
       box is BACKED UP first (<file>.bak-intake-refresh-<UTC-timestamp>,
       byte-for-byte, restorable) and only then overwritten with the library
       version. Nothing is destroyed either way — a genuine pre-existing
       hand-edit survives, recoverable, in the backup; it is simply no longer
       what the live driver reads without the operator explicitly restoring
       it. Precedent: this exact backup-before-overwrite discipline is the
       standing house rule for content-bearing writes in this project.
  * sha256(dest) != sha256(library) AND
    provenance.installed_sha256 != sha256(dest)    -> PRESERVE. The box's
       copy diverges from BOTH the library AND from what this mechanism last
       delivered — i.e. it changed on disk after a real delivery, the
       signature of a genuine local edit. Left untouched; reported loudly as
       "preserved (local override)"; never counted as a materialization
       failure.

This means: a stale/never-delivered box gets fixed on its FIRST run of this
script (closing FAULT-11 immediately, this roll) — and from the SECOND run
onward, once provenance exists, a real client customization made in between
runs is protected exactly per FAULT-11's own instructions.

────────────────────────────────────────────────────────────────────────────
OUT OF SCOPE (explicitly, not an oversight)
────────────────────────────────────────────────────────────────────────────
`templates/role-library/presentations/intake-miniapp/` is NOT mirrored. Git
history (commit 6d0f941a1) explicitly marks intake/interview-app/ canonical
and intake-miniapp/ deprecated ("no deletion, recommendation left for
Trevor") — mirroring a deprecated tree onto every box would be shipping dead
code as if it were current. `memory/` is not a role-library-shipped tree at
all (no templates/role-library/presentations/memory/ exists; it is pure
per-box runtime state) so it is out of scope by construction, not by
omission.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --workspace <dir>   client workspace root (default: platform-appropriate
                       resolution, same as refresh-dept-scripts.py).
  --library <dir>     override the role-library root (default:
                       <skill_dir>/templates/role-library). Test-only escape
                       hatch; a real roll never passes this.
  --apply              actually write files. Without this flag the script is
                       DRY-RUN: it reports exactly what it would do but
                       touches nothing, and does not call the post-write
                       verifier (there is nothing to verify yet).

EXIT CODES
  0   every in-library department with an intake/ subdir either mirrored
      clean (post-write verify found zero problems) or was skipped because
      it is not materialized on this box (a benign, non-failure skip).
  3   at least one in-scope department's post-write verify found a missing
      or hash-diverged canonical/refreshed file, OR a per-file copy attempt
      itself failed. Also writes <workspace>/.dept-intake-refresh-receipt.json
      {ok, depts:[...], failed_inscope, ...} and prints
      "DEPT_INTAKE_STATUS ok=<0|1> failed_inscope=<n>" on stdout as a
      pipe-immune cross-check (same pattern as refresh-dept-scripts.py's
      DEPT_SCRIPTS_STATUS).
  1   only on a usage error (bad CLI args).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Self-locating skill-23 resolution (same pattern as refresh-dept-scripts.py) ──
_SCRIPT = Path(__file__).resolve()
_DEFAULT_SKILL_DIR = _SCRIPT.parent.parent


def _resolve_skill_dir():
    cands = []
    env = os.environ.get("OPENCLAW_SKILL23_DIR")
    if env:
        cands.append(Path(env))
    cands.append(_DEFAULT_SKILL_DIR)
    cands.append(Path.home() / ".openclaw/skills/23-ai-workforce-blueprint")
    cands.append(Path("/data/.openclaw/skills/23-ai-workforce-blueprint"))
    for c in cands:
        try:
            if (c / "scripts" / "create_role_workspaces.py").is_file():
                return c
        except OSError:
            continue
    return _DEFAULT_SKILL_DIR


SKILL_DIR = _resolve_skill_dir()
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))
import create_role_workspaces as crw  # type: ignore  # noqa: E402

HOME = os.path.expanduser("~")

# Bucket 1 — fleet-owned, always mirrored. Starts from the SAME shared
# constant refresh-dept-scripts.py and scaffold_department already source
# (never re-declared as an independent literal, so the three writers can
# never silently disagree about the shared subset), extended with suffixes
# that only appear under intake/interview-app/ (the Cloudflare-deployable
# app has file types scripts/ never carries: .html/.toml/.sql/.mjs). This
# extension is LOCAL to this module — it does not mutate
# crw._CANONICAL_SCRIPT_SUFFIXES, so scripts/ mirroring elsewhere is
# unaffected.
_INTAKE_MIRROR_SUFFIXES = tuple(
    sorted(set(crw._CANONICAL_SCRIPT_SUFFIXES) | {".html", ".toml", ".sql", ".mjs"})
)

# Bucket 3 — box-owned, additive/missing-only. Same constant scripts/ uses.
_ADDITIVE_SUFFIXES = crw._ADDITIVE_SCRIPT_SUFFIXES  # (".json",)

# Bucket 2 — the two files FAULT-11 is actually about. Matched by exact
# filename AND top-level position (rel_path has exactly one part) so a
# same-named file nested deeper in interview-app/ (there is none today, but
# nothing prevents one appearing later) is never mistaken for the canonical
# bank.
_CANONICAL_BANK_FILENAMES = {"deck-intake-questions.json", "upsell-questions.json"}

_PROVENANCE_FILENAME = ".BANK-PROVENANCE.json"


def resolve_workspace(explicit):
    """Mirrors refresh-dept-scripts.py's resolve_workspace()."""
    if explicit:
        return Path(explicit)
    candidates = [
        "/data/.openclaw/workspace",
        os.path.join(HOME, ".openclaw", "workspace"),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "departments")) or \
           os.path.isfile(os.path.join(c, ".workforce-build-state.json")):
            return Path(c)
    if os.path.isdir("/data/.openclaw"):
        return Path("/data/.openclaw/workspace")
    return Path(os.path.join(HOME, ".openclaw", "workspace"))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_library_depts_with_intake(library_root):
    """Yield (dept_slug, lib_intake_root) for every role-library department
    directory that ships an intake/ subdir. TODAY exactly one (presentations);
    every other department is a proven no-op for this generator, not a
    special case requiring its own branch — same shape as
    iter_library_depts_with_scripts()."""
    library_root = Path(library_root)
    if not library_root.is_dir():
        return
    for entry in sorted(library_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        intake_dir = entry / "intake"
        if intake_dir.is_dir():
            yield entry.name, intake_dir


def _load_provenance(intake_target):
    path = intake_target / _PROVENANCE_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_provenance(intake_target, provenance, apply_):
    if not apply_:
        return
    path = intake_target / _PROVENANCE_FILENAME
    try:
        path.write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as e:
        print(f"  refresh-dept-intake: WARN could not write provenance to {path}: {e}",
              file=sys.stderr)


def _try_copy(src_file, dest_file, rel_path, copy_failed):
    """Same contract as refresh-dept-scripts.py's _try_copy: a per-file write
    failure is CAUGHT and recorded, never raised past the caller."""
    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        return True
    except OSError as e:
        reason = f"{type(e).__name__}: {e}"
        copy_failed.append({"path": str(rel_path), "issue": "copy-failed", "reason": reason})
        print(f"  refresh-dept-intake: COPY FAILED -- {rel_path} -- {reason}",
              file=sys.stderr)
        return False


def _refresh_bank_file(rel_path, src_file, dest_file, provenance, apply_,
                        refreshed, preserved, fresh_installed, copy_failed):
    """Bucket 2 — provenance-gated refresh. See module docstring
    'PROVENANCE-GATED BANK REFRESH'. Mutates provenance in place."""
    name = str(rel_path)
    lib_sha = _sha256(src_file)

    if not dest_file.is_file():
        if apply_:
            if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                return
        provenance[name] = {
            "installed_sha256": lib_sha,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "library_source_path": str(src_file),
        }
        fresh_installed.append(name)
        return

    dest_sha = _sha256(dest_file)
    if dest_sha == lib_sha:
        # Already current. Still (re)record provenance so a future run has an
        # accurate "what we last confirmed installed" baseline even if this
        # is the first time the sidecar has ever been written.
        provenance[name] = {
            "installed_sha256": lib_sha,
            "installed_at": provenance.get(name, {}).get("installed_at")
                             or datetime.now(timezone.utc).isoformat(),
            "library_source_path": str(src_file),
        }
        return

    last_installed = provenance.get(name, {}).get("installed_sha256")
    if last_installed is None or last_installed == dest_sha:
        # Safe to refresh: either no delivery history at all (pre-existing
        # stale box — the FAULT-11 case), or the box's copy is exactly what
        # we ourselves last delivered and nothing has touched it since.
        if apply_:
            backup_name = (
                dest_file.name
                + f".bak-intake-refresh-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            backup_path = dest_file.with_name(backup_name)
            try:
                shutil.copy2(dest_file, backup_path)
            except OSError as e:
                copy_failed.append({"path": name, "issue": "backup-failed",
                                     "reason": f"{type(e).__name__}: {e}"})
                print(f"  refresh-dept-intake: BACKUP FAILED -- {name} -- {e} "
                      f"-- refusing to overwrite without a backup", file=sys.stderr)
                return
            if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                return
            refreshed.append({"path": name, "backup": str(backup_path)})
        else:
            refreshed.append({"path": name, "backup": "(dry-run, no backup written)"})
        provenance[name] = {
            "installed_sha256": lib_sha,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "library_source_path": str(src_file),
        }
        return

    # Diverges from BOTH the library and from what we last delivered —
    # a genuine local edit made since the last delivery. Preserve.
    preserved.append({
        "path": name,
        "reason": "diverges from library and from last-recorded delivery — "
                  "preserved as a local override, not overwritten",
    })


def mirror_dept_intake(lib_intake_root, intake_target, apply_):
    """Copy every file under lib_intake_root into intake_target per the
    three-bucket policy documented in the module docstring. Returns a dict:
      {"copied": [...], "skipped_owned": [...], "copy_failed": [...],
       "bank_refreshed": [...], "bank_preserved": [...], "bank_fresh": [...]}
    apply_=False performs every comparison (so the report is accurate) but
    writes nothing — same dry-run contract as refresh-dept-scripts.py."""
    copied = []
    skipped_owned = []
    copy_failed = []
    bank_refreshed = []
    bank_preserved = []
    bank_fresh = []

    provenance = _load_provenance(intake_target) if intake_target.is_dir() else {}

    for rel_path, src_file in crw._iter_scripts_tree_files(lib_intake_root):
        suffix = src_file.suffix
        dest_file = intake_target / rel_path

        is_bank_file = (
            len(rel_path.parts) == 1 and rel_path.name in _CANONICAL_BANK_FILENAMES
        )
        if is_bank_file:
            _refresh_bank_file(rel_path, src_file, dest_file, provenance, apply_,
                                bank_refreshed, bank_preserved, bank_fresh, copy_failed)
            continue

        if suffix in _ADDITIVE_SUFFIXES:
            if dest_file.exists():
                skipped_owned.append(str(rel_path))
                continue
            if apply_:
                if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                    continue
            copied.append(str(rel_path))
            continue

        if suffix not in _INTAKE_MIRROR_SUFFIXES:
            continue  # not a canonical asset -- not this mirror's concern

        if dest_file.is_file():
            try:
                if _sha256(dest_file) == _sha256(src_file):
                    continue  # already current -- idempotent no-op
            except OSError:
                pass
        if apply_:
            if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                continue
        copied.append(str(rel_path))

    _save_provenance(intake_target, provenance, apply_)

    return {
        "copied": copied,
        "skipped_owned": skipped_owned,
        "copy_failed": copy_failed,
        "bank_refreshed": bank_refreshed,
        "bank_preserved": bank_preserved,
        "bank_fresh": bank_fresh,
    }


def verify_intake_materialization(lib_intake_root, intake_target, result):
    """Post-materialization proof, independently re-derived from disk bytes
    AFTER the write step — same discipline as
    create_role_workspaces.verify_scripts_materialization(): never satisfied
    by the copy loop's own counters.

      * bucket 1 (mirror suffixes) and bucket 3-but-freshly-copied (additive
        .json that did not previously exist): must be present and
        byte-identical to the library.
      * bucket 2 bank files: if this run REFRESHED or FRESH-INSTALLED one,
        it must now be present and byte-identical to the library. If this
        run PRESERVED one (a detected local override), it only has to still
        EXIST — a preserved file is deliberately allowed to diverge; that
        divergence is the policy working, not a failure. A bank file going
        missing after a "preserve" decision (e.g. deleted out from under the
        run) IS a problem.
    """
    problems = []
    refreshed_or_fresh = {e["path"] for e in result["bank_refreshed"]} | set(result["bank_fresh"])
    preserved_paths = {e["path"] for e in result["bank_preserved"]}

    for rel_path, src_file in crw._iter_scripts_tree_files(lib_intake_root):
        rel_str = str(rel_path)
        dest_file = intake_target / rel_path

        if rel_str in preserved_paths:
            if not dest_file.is_file():
                problems.append({"path": rel_str, "issue": "missing"})
            continue

        if rel_str in refreshed_or_fresh:
            if not dest_file.is_file():
                problems.append({"path": rel_str, "issue": "missing"})
                continue
            if _sha256(dest_file) != _sha256(src_file):
                problems.append({"path": rel_str, "issue": "hash-mismatch"})
            continue

        if src_file.suffix not in _INTAKE_MIRROR_SUFFIXES:
            continue  # additive .json left alone by policy -- never checked here

        if not dest_file.is_file():
            problems.append({"path": rel_str, "issue": "missing"})
            continue
        if _sha256(dest_file) != _sha256(src_file):
            problems.append({"path": rel_str, "issue": "hash-mismatch"})

    return problems


def _write_receipt(workspace, ok, depts, failed_inscope, apply_):
    receipt = {
        "ok": bool(ok),
        "apply": bool(apply_),
        "depts": depts,
        "failed_inscope": failed_inscope,
        "generator": "refresh-dept-intake.py",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = workspace / ".dept-intake-refresh-receipt.json"
    try:
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  refresh-dept-intake: WARN could not write receipt to {receipt_path}: {e}",
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Unconditionally mirror role-library department intake/ trees onto "
                    "a materialized workspace, on every roll (fixes FAULT-11: intake/ was "
                    "never delivered by any existing writer). Interview-app source is "
                    "fleet-owned and always overwritten when diverged; the two named "
                    "question-bank JSON files are provenance-gated refresh (backed up "
                    "before any overwrite; preserved once a genuine post-delivery local "
                    "edit is detected); other .json is box-owned/additive.")
    parser.add_argument("--workspace", default=None,
                        help="Client workspace root (default: resolved platform-appropriately).")
    parser.add_argument("--library", default=None,
                        help="Override the role-library root (default: "
                             "<skill_dir>/templates/role-library). Test-only.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write files. Default: dry-run report only.")
    args = parser.parse_args(argv)

    workspace = resolve_workspace(args.workspace)
    library_root = Path(args.library) if args.library else (SKILL_DIR / "templates" / "role-library")
    departments_root = workspace / "departments"

    depts_report = []
    failed_inscope = 0
    total_copied = 0
    total_refreshed = 0
    total_preserved = 0
    skipped_not_materialized = 0
    in_library = 0

    for dept_slug, lib_intake_root in iter_library_depts_with_intake(library_root):
        in_library += 1
        dept_dir = crw.resolve_dept_dir(departments_root, dept_slug)
        if dept_dir is None:
            skipped_not_materialized += 1
            depts_report.append({
                "dept": dept_slug,
                "resolved_path": None,
                "status": "skipped_not_materialized",
            })
            print(f"  refresh-dept-intake: SKIP '{dept_slug}' -- not materialized on this "
                  f"box (no departments/{dept_slug}[-dept] directory found); not a failure.")
            continue

        intake_target = dept_dir / "intake"
        if args.apply:
            intake_target.mkdir(exist_ok=True)

        result = mirror_dept_intake(lib_intake_root, intake_target, args.apply)
        total_copied += len(result["copied"])
        total_refreshed += len(result["bank_refreshed"]) + len(result["bank_fresh"])
        total_preserved += len(result["bank_preserved"])

        problems = verify_intake_materialization(lib_intake_root, intake_target, result) \
            if args.apply else []

        copy_failed_paths = {p["path"] for p in result["copy_failed"]}
        problems = [p for p in problems if p["path"] not in copy_failed_paths] + result["copy_failed"]
        dept_failed = len(problems)
        failed_inscope += dept_failed

        depts_report.append({
            "dept": dept_slug,
            "resolved_path": str(dept_dir),
            "status": "ok" if dept_failed == 0 else "verify_failed",
            "copied": len(result["copied"]),
            "skipped_owned_json": len(result["skipped_owned"]),
            "bank_refreshed": result["bank_refreshed"],
            "bank_preserved": result["bank_preserved"],
            "bank_fresh_installed": result["bank_fresh"],
            "problems": problems,
        })

        if dept_failed:
            _lines = "\n".join(
                f"    - {p['issue']}: {p['path']}" + (f" ({p['reason']})" if p.get("reason") else "")
                for p in problems
            )
            print(f"  refresh-dept-intake: FAILED '{dept_slug}' -- {dept_failed} canonical "
                  f"file(s) missing, diverged, or failed to write under {lib_intake_root} "
                  f"-- a detected gap left unfilled, not a silent pass:\n{_lines}",
                  file=sys.stderr)
        else:
            mode = "" if args.apply else " (DRY-RUN)"
            print(f"  refresh-dept-intake: OK '{dept_slug}' -> {dept_dir} "
                  f"({len(result['copied'])} file(s) mirrored, "
                  f"{len(result['bank_refreshed']) + len(result['bank_fresh'])} bank file(s) "
                  f"refreshed/installed, {len(result['bank_preserved'])} local override(s) "
                  f"preserved, {len(result['skipped_owned'])} other client-local .json "
                  f"override(s) preserved){mode}")
            for e in result["bank_preserved"]:
                print(f"  refresh-dept-intake:   PRESERVED (local override) -- {e['path']}: "
                      f"{e['reason']}")
            for e in result["bank_refreshed"]:
                print(f"  refresh-dept-intake:   REFRESHED -- {e['path']} (backup: {e['backup']})")

    ok_contract = (failed_inscope == 0)
    _write_receipt(workspace, ok_contract, depts_report, failed_inscope, args.apply)
    mode = "" if args.apply else " (DRY-RUN -- pass --apply to write)"
    print(f"  refresh-dept-intake: {total_copied} file(s) mirrored, {total_refreshed} bank "
          f"file(s) refreshed/installed, {total_preserved} local override(s) preserved across "
          f"{in_library} in-library department(s) with an intake/ subdir "
          f"({skipped_not_materialized} not materialized on this box){mode}")
    print(f"  refresh-dept-intake: DEPT_INTAKE_STATUS ok={1 if ok_contract else 0} "
          f"failed_inscope={failed_inscope}")
    return 0 if ok_contract else 3


if __name__ == "__main__":
    sys.exit(main())
