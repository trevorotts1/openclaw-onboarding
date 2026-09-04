#!/usr/bin/env python3
"""
refresh-dept-scripts.py — UNCONDITIONAL DEPARTMENT-SCRIPTS MIRROR (FIX-DELIVERY-02).

────────────────────────────────────────────────────────────────────────────
THE GAP THIS CLOSES (causes 2 and 3 of the delivery defect)
────────────────────────────────────────────────────────────────────────────
scaffold_department() (create_role_workspaces.py) is the only code in this
repo that writes a department's engine files (build_deck.py, capacity.py,
deliverables.py, self_audit.py, qc_check.py, ...) from the role library onto
a client workspace. It has exactly ONE runtime caller: floor-fill-driver.py,
which only ever iterates a gap map built by make-gap-from-staleness.py from
kind=="MISSING" queue rows. detect-stale-artifacts.py's load_current() never
emits a "scripts" kind at all (cause 3 — the literal string never appears in
_index.json and there is no code path that could produce it), so a dept
scripts file can never be queued STALE or MISSING once it has been written
once. On a HEALTHY steady-state box (no missing roles/sops/depts) gap.json
is `{}`, migrate-existing-workforce.sh's `FF_GAP_DEPTS -gt 0` gate is FALSE,
and floor-fill-driver.py never launches at all (cause 2) — so not even the
depth-1 files this repo already treats as fleet-owned ever refresh again
after day one. Only ONE writer reaches the dept scripts dir on every roll:
colocate_presentation_entry() (update-skills.sh) — a hardcoded two-file list
that knows nothing about the other department or about nested files.

This script is a THIRD, independent path to the same destination, run
UNCONDITIONALLY on every roll (no gap-map gate, modelled on
refresh-stale-roles.py, the one repair step that already runs every time
with no gap dependency): it mirrors every role-library department's
scripts/ tree onto the box's materialized department directory, honoring
the SAME ownership policy scaffold_department already enforces
(create_role_workspaces.py _CANONICAL_SCRIPT_SUFFIXES / _ADDITIVE_SCRIPT_SUFFIXES):

  .py / .sh / .js / .tpl / .sha256 /  FLEET-OWNED  — always mirrored (overwritten
  .pdf                                        whenever the sha256 diverges)
  .json                        BOX-OWNED    — additive / missing-only,
                                               NEVER overwritten if it exists
  anything else                             — not this mirror's concern,
                                               not copied

GAP-DELIVERY-JS: .js was added to the fleet-owned set above because
rescue-rangers/scripts/relay_brain_validation.js is a versioned tool (like
any .py/.sh generator), never a client-local override candidate. Before this
fix .js appeared in NEITHER suffix list in EITHER writer (this script nor
scaffold_department), so relay_brain_validation.js was silently dropped by
every delivery path that ever existed — never auto-delivered at all, on any
box, since day one. Both writers now source both suffix tuples from the
same two create_role_workspaces module-level constants, so they can no
longer independently hardcode and silently disagree.

Today exactly TWO role-library departments ship a scripts/ subdir
(presentations, rescue-rangers); on every other department this script's
loop body simply never executes for it — a proven no-op, not a special case.

────────────────────────────────────────────────────────────────────────────
OUT OF SCOPE (explicitly, not an oversight)
────────────────────────────────────────────────────────────────────────────
Only role-library department directories that have a `scripts/` subdirectory
are enumerated. `templates/role-library/presentations/intake/` (and
`intake-miniapp/`) are SIBLINGS of `scripts/`, not inside it, and are left
untouched by this script — delivering them is a separate, undesigned gap.
`.artifact-refresh-queue.json` STALE/MISSING drains (refresh-stale-roles.py,
floor-fill-driver.py) remain the only consumers of role/sop/dept kind rows;
this script neither reads nor writes that queue.

────────────────────────────────────────────────────────────────────────────
ALGORITHM
────────────────────────────────────────────────────────────────────────────
For every role-library department directory with a scripts/ subdir:
  1. Resolve the box's materialized department directory via
     create_role_workspaces.resolve_dept_dir() — DETECTED, never assumed
     (bare id / "-dept" suffixed / normalized-scan, the same probe
     refresh-stale-roles.py and floor-fill-driver.py already share).
  2. Not resolved -> SKIP, recorded "skipped_not_materialized". This is NOT
     a failure: a department the box owner never had (or explicitly
     declined) is not this script's business to create — that stays
     floor-fill-driver.py's MISSING-department job.
  3. Resolved -> walk the library scripts/ tree recursively
     (create_role_workspaces._iter_scripts_tree_files — the SAME walk
     scaffold_department's verifier uses, so this mirror and the
     verification below can never disagree about what the tree contains).
     For each file: .json is copied only if the destination does not yet
     exist (never clobbers a client-local override); every other canonical
     suffix (.py/.sh/.js/.tpl/.sha256/.pdf) is copied only when its sha256 differs
     from the current destination (idempotent no-op on an already-current
     box; a genuinely stale/corrupted file gets overwritten with the
     canonical library bytes). A per-file write failure here (an unwritable/
     locked destination, an unwritable parent dir, ...) is CAUGHT — never
     raised — and recorded with the exact path and reason (see
     mirror_dept_scripts's _try_copy); one locked file does not abort the
     loop or the run.
  4. AFTER the writes, independently RE-DERIVE the verdict from the
     filesystem: create_role_workspaces.verify_scripts_materialization()
     re-hashes every canonical-suffix library file against the destination.
     This is the check that catches an incomplete or sabotaged copy — it is
     never satisfied by this script's own copy-loop counter (see "NOT A
     BOOLEAN PREDICATE" below).
  5. Any problem verify_scripts_materialization() reports, OR any per-file
     copy failure step 3 caught, counts toward failed_inscope for that
     department, and for the whole run.

────────────────────────────────────────────────────────────────────────────
NOT A BOOLEAN PREDICATE OVER THE SAME UNTRUSTED INPUT
────────────────────────────────────────────────────────────────────────────
The pass/fail verdict this script prints and gates on is computed by
re-reading BOTH the library source bytes and the destination bytes AFTER
the copy step has finished — sha256(library file) vs sha256(destination
file) — via verify_scripts_materialization(), a function that does not
share any state with, and is never informed by, the mirror loop's own
"I copied N files" counter. A copy step that silently drops or truncates a
file is caught here exactly as if this script had never run the copy loop
at all: the destination is simply read straight off disk and compared to
the library. This is deliberately NOT "check a flag the writer set" guarded
a second time; it is an independent re-derivation from the one thing that
actually matters (what bytes are on disk right now).

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --workspace <dir>   client workspace root (default: platform-appropriate
                       resolution, same as refresh-stale-roles.py).
  --library <dir>     override the role-library root (default:
                       <skill_dir>/templates/role-library). Test-only escape
                       hatch; a real roll never passes this.
  --apply              actually write files. Without this flag the script is
                       DRY-RUN: it reports exactly what it would copy but
                       touches nothing, and does not call the post-write
                       verifier (there is nothing to verify yet).

EXIT CODES
  0   every in-library department with a scripts/ subdir either mirrored
      clean (post-write verify found zero problems) or was skipped because
      it is not materialized on this box (a benign, non-failure skip).
  3   at least one in-scope department's post-write verify found a missing
      or hash-diverged canonical file, OR a per-file copy attempt itself
      failed (e.g. an unwritable/locked destination raises OSError/
      PermissionError) — a detected gap left unfilled. A copy failure is
      CAUGHT per file (naming the exact path and the reason) and folded into
      this SAME graceful verify_failed/rc 3 contract; it never raises past
      mirror_dept_scripts() to crash the whole run with an uncaught
      traceback, and it never silently degrades to a bare pass/fail with no
      indication of which file could not be written. Also
      writes <workspace>/.dept-scripts-refresh-receipt.json
      {ok, depts:[...], failed_inscope, ...} and prints
      "DEPT_SCRIPTS_STATUS ok=<0|1> failed_inscope=<n>" on stdout as a
      pipe-immune cross-check (same pattern as refresh-stale-roles.py's
      DRAIN_STATUS).
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

# ── Self-locating skill-23 resolution (same pattern as refresh-stale-roles.py
#    and floor-fill-driver.py) ──
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

# Same ownership policy scaffold_department already enforces
# (create_role_workspaces.py _CANONICAL_SCRIPT_SUFFIXES / _ADDITIVE_SCRIPT_SUFFIXES):
# .py/.sh/.js/.tpl/.sha256/.pdf are FLEET-OWNED and ALWAYS mirrored (overwritten when
# divergent); .json is BOX-OWNED and additive/missing-only. BOTH tuples are
# sourced from create_role_workspaces (never re-declared as a second literal
# here) so the two writers can never drift apart — the exact bug class that
# let relay_brain_validation.js (.js) fall through every delivery path: it
# appeared in neither list, in either file, until this fix.
_MIRROR_SUFFIXES = crw._CANONICAL_SCRIPT_SUFFIXES  # (".py", ".sh", ".js", ".tpl", ".sha256", ".pdf")
_ADDITIVE_SUFFIXES = crw._ADDITIVE_SCRIPT_SUFFIXES  # (".json",)


def resolve_workspace(explicit):
    """Mirrors detect-stale-artifacts.py / refresh-stale-roles.py's
    resolve_workspace() so all three tools agree on the client workspace
    root with zero flags passed."""
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


def iter_library_depts_with_scripts(library_root):
    """Yield (dept_slug, lib_scripts_root) for every role-library department
    directory that ships a scripts/ subdir. TODAY exactly two
    (presentations, rescue-rangers); every other department is a proven
    no-op for this generator, not a special case requiring its own branch."""
    library_root = Path(library_root)
    if not library_root.is_dir():
        return
    for entry in sorted(library_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        scripts_dir = entry / "scripts"
        if scripts_dir.is_dir():
            yield entry.name, scripts_dir


def _try_copy(src_file, dest_file, rel_path, copy_failed):
    """shutil.copy2 wrapped so a per-file write failure (an unwritable/locked
    destination, an unwritable/missing parent directory, a full disk, ...)
    is CAUGHT here and recorded — naming the exact offending relative path
    and the concrete reason — instead of raising an uncaught OSError/
    PermissionError past mirror_dept_scripts() and crashing the whole mirror
    (and the whole roll's dept-scripts step) mid-loop with a raw Python
    traceback. Every OTHER file already queued still gets its own copy
    attempt; one locked file degrades the run to the documented graceful
    verify_failed/rc 3 outcome, never an unhandled exit 1 crash.

    Returns True if the write succeeded, False if it was caught and recorded
    in copy_failed (caller must NOT count this path as copied)."""
    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        return True
    except OSError as e:
        reason = f"{type(e).__name__}: {e}"
        copy_failed.append({"path": str(rel_path), "issue": "copy-failed", "reason": reason})
        print(f"  refresh-dept-scripts: COPY FAILED -- {rel_path} -- {reason}",
              file=sys.stderr)
        return False


def mirror_dept_scripts(lib_scripts_root, scripts_target, apply_):
    """Copy .py/.sh/.js/.tpl/.sha256/.pdf files from lib_scripts_root into
    scripts_target whenever the destination is missing or its sha256
    diverges from the source (idempotent no-op on an already-current box);
    .json files are copied ONLY when absent at the destination (additive —
    a client-local override that already exists is NEVER touched). Returns
    {"copied": [rel_path, ...], "skipped_owned": [rel_path, ...],
     "copy_failed": [{"path", "issue": "copy-failed", "reason"}, ...]}.

    A per-file copy failure (see _try_copy) is caught and appended to
    copy_failed — it is NEVER allowed to raise past this function.

    apply_=False performs every comparison (so the report is accurate) but
    writes nothing — the dry-run contract (nothing can fail to write)."""
    copied = []
    skipped_owned = []
    copy_failed = []
    for rel_path, src_file in crw._iter_scripts_tree_files(lib_scripts_root):
        suffix = src_file.suffix
        dest_file = scripts_target / rel_path

        if suffix in _ADDITIVE_SUFFIXES:
            if dest_file.exists():
                skipped_owned.append(str(rel_path))
                continue
            if apply_:
                if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                    continue
            copied.append(str(rel_path))
            continue

        if suffix not in _MIRROR_SUFFIXES:
            continue  # not a canonical script asset -- not this mirror's concern

        if dest_file.is_file():
            try:
                if _sha256(dest_file) == _sha256(src_file):
                    continue  # already current -- idempotent no-op
            except OSError:
                pass  # unreadable destination -- fall through and (re)write it
        if apply_:
            if not _try_copy(src_file, dest_file, rel_path, copy_failed):
                continue
        copied.append(str(rel_path))
    return {"copied": copied, "skipped_owned": skipped_owned, "copy_failed": copy_failed}


def _write_receipt(workspace, ok, depts, failed_inscope, apply_):
    receipt = {
        "ok": bool(ok),
        "apply": bool(apply_),
        "depts": depts,
        "failed_inscope": failed_inscope,
        "generator": "refresh-dept-scripts.py",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = workspace / ".dept-scripts-refresh-receipt.json"
    try:
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  refresh-dept-scripts: WARN could not write receipt to {receipt_path}: {e}",
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Unconditionally mirror role-library department scripts/ trees onto "
                    "a materialized workspace, on every roll, independent of any "
                    "MISSING-only gap map (fixes causes 2 and 3 of the delivery defect). "
                    ".py/.sh/.js/.tpl/.sha256/.pdf are fleet-owned and always overwritten when they "
                    "diverge; .json is box-owned and additive/missing-only.")
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
    skipped_not_materialized = 0
    in_library = 0

    for dept_slug, lib_scripts_root in iter_library_depts_with_scripts(library_root):
        in_library += 1
        dept_dir = crw.resolve_dept_dir(departments_root, dept_slug)
        if dept_dir is None:
            skipped_not_materialized += 1
            depts_report.append({
                "dept": dept_slug,
                "resolved_path": None,
                "status": "skipped_not_materialized",
            })
            print(f"  refresh-dept-scripts: SKIP '{dept_slug}' -- not materialized on this "
                  f"box (no departments/{dept_slug}[-dept] directory found); not a failure.")
            continue

        scripts_target = dept_dir / "scripts"
        if args.apply:
            scripts_target.mkdir(exist_ok=True)

        result = mirror_dept_scripts(lib_scripts_root, scripts_target, args.apply)
        total_copied += len(result["copied"])

        # Re-derive the verdict from the filesystem AFTER the write -- never
        # from mirror_dept_scripts()'s own "copied" counter (see "NOT A
        # BOOLEAN PREDICATE" in the module docstring). Dry-run wrote nothing,
        # so there is nothing to verify yet (mirrors scaffold_department's
        # own dry_run contract).
        problems = crw.verify_scripts_materialization(lib_scripts_root, scripts_target) if args.apply else []

        # Fold mirror_dept_scripts()'s own copy_failed list (GAP-COPY-ERR: a
        # per-file write failure -- e.g. an unwritable/locked destination --
        # caught in _try_copy instead of raised) into the SAME problems list
        # verify_scripts_materialization feeds, so a copy failure degrades
        # this department to the documented graceful verify_failed/rc 3
        # outcome exactly like a hash-mismatch does -- never an uncaught
        # PermissionError crashing the whole run with a raw traceback. A path
        # that failed to copy would ALSO show up in `problems` as a generic
        # "missing"/"hash-mismatch" (verify has no way to know WHY); drop
        # that generic duplicate and keep only the copy_failed entry, since
        # it names the concrete reason and is strictly more informative --
        # one line per offending file, not two, so the log unambiguously
        # names which file could not be written and why.
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
            "problems": problems,
        })

        if dept_failed:
            _lines = "\n".join(
                f"    - {p['issue']}: {p['path']}" + (f" ({p['reason']})" if p.get("reason") else "")
                for p in problems
            )
            print(f"  refresh-dept-scripts: FAILED '{dept_slug}' -- {dept_failed} canonical "
                  f"file(s) missing, diverged, or failed to write under {lib_scripts_root} "
                  f"-- a detected gap left unfilled, not a silent pass:\n{_lines}",
                  file=sys.stderr)
        else:
            mode = "" if args.apply else " (DRY-RUN)"
            print(f"  refresh-dept-scripts: OK '{dept_slug}' -> {dept_dir} "
                  f"({len(result['copied'])} file(s) copied, "
                  f"{len(result['skipped_owned'])} client-local .json override(s) preserved)"
                  f"{mode}")

    ok_contract = (failed_inscope == 0)
    _write_receipt(workspace, ok_contract, depts_report, failed_inscope, args.apply)
    mode = "" if args.apply else " (DRY-RUN -- pass --apply to write)"
    print(f"  refresh-dept-scripts: {total_copied} file(s) copied across {in_library} "
          f"in-library department(s) with a scripts/ subdir "
          f"({skipped_not_materialized} not materialized on this box){mode}")
    print(f"  refresh-dept-scripts: DEPT_SCRIPTS_STATUS ok={1 if ok_contract else 0} "
          f"failed_inscope={failed_inscope}")
    return 0 if ok_contract else 3


if __name__ == "__main__":
    sys.exit(main())
