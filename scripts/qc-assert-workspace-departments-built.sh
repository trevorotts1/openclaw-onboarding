#!/usr/bin/env bash
# ============================================================
# qc-assert-workspace-departments-built.sh
#   AF-WORKSPACE-SHELL — fail-closed gate that makes "department installed /
#   client updated / airtight" IMPOSSIBLE to report while the client's actual
#   WORKSPACE department is an empty SHELL.
# ------------------------------------------------------------
# v12.23.0 — WORKSPACE-MATERIALIZATION HONESTY
#
# THE FAILURE THIS KILLS (it happened and cost the owner real money):
#   The onboarding/update path copies the role-library TEMPLATE to disk under
#     /data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/<dept>/
#   (a SKILLS-tree path), and THAT got reported as "the client is updated / the
#   department is installed / done — airtight." But the client's actual WORKSPACE
#   department —
#     <workspace>/zero-human-company/<company>/departments/<dept>/
#   — was left an empty SHELL: only DREAMS.md + memory/, NO numbered role
#   subdirs, NO IDENTITY.md, NO SOUL.md, NO real SOPs. A template copied to the
#   skills/ tree is NOT a materialized workspace department. They are TWO SEPARATE
#   STATES ("TEMPLATE DEPLOYED" vs "WORKSPACE INSTANTIATED") and each must be
#   verified separately. This gate verifies the WORKSPACE — a template on disk
#   can NEVER satisfy it.
#
# FAIL-CLOSED DESIGN (when in doubt, FAIL):
#   * Resolves the CLIENT WORKSPACE departments dir the SAME way the repo's
#     working resolver does (department-floor.resolve_departments_dir(), which is
#     itself fed by lib/detect_platform.py + _qc_company_info.py's _is_template_path
#     guard). If a template-tree (openclaw-master-files / skills/role-library)
#     path is the ONLY thing that resolves, that is NOT a workspace and the gate
#     FAILS — it does not "pass for lack of a workspace".
#   * The required-department list is the department FLOOR
#     (department-floor.evaluate_floor) — the same single source of truth that
#     gates the on-disk department COUNT. This gate then goes one layer deeper:
#     for EACH required dept it classifies the WORKSPACE materialization as
#     FULL / PARTIAL / SHELL using RAW counts.
#   * ANY required department that is SHELL or PARTIAL → exit 3 (AF-WORKSPACE-SHELL).
#   * Resolver error / no workspace / unreadable floor → exit non-zero. Never
#     "all good" on uncertainty.
#
# FULL / SHELL / PARTIAL classification (RAW facts only — no JSON state trusted):
#   For a workspace department dir <dept>/:
#     role subdirs  = immediate child dirs that are REAL role folders, in EITHER
#                     recognized naming shape:
#                       (a) NN-prefixed (00-*, 01-*…), OR
#                       (b) slug-named (chief-marketing-officer/, head-of-sales/)
#                           that carry the role-file fingerprint (IDENTITY.md or
#                           SOUL.md, OR a real SOP). Structural non-role dirs
#                           (memory/, devils-advocate/, SOP/) are never counted.
#     director IDENTITY.md = <dept>/IDENTITY.md present?
#     director SOUL.md     = <dept>/SOUL.md present?
#     real SOPs            = a role subdir carries a real SOP in ANY shape:
#                            how-to.md >= SOP_MIN_BYTES (3072, the same 3 KB floor
#                            verify-wiring.sh enforces), OR a standalone
#                            substantive SOP file (role-subdir 0[1-9]-*.md >= 7168
#                            bytes), OR a populated SOP/ (sops/) subdir holding
#                            a how-to.md >= 3072 B or a *.md >= 7168 B.
#   SHELL   = 0 role subdirs of EITHER naming  (the DREAMS.md + memory/-only shell)
#   PARTIAL = has role subdirs BUT (no director IDENTITY.md OR no SOUL.md OR no
#             real SOPs in any role)
#   FULL    = >=1 role subdir AND director IDENTITY.md AND SOUL.md AND
#             >=1 real SOP somewhere in the dept
#
# The CLIENT WORKSPACE HOME is canonically UNDER openclaw-master-files
# (<openclaw-master-files>/zero-human-company/<company>/departments/), exactly
# where department-floor.resolve_departments_dir() resolves it — so a path
# containing 'openclaw-master-files' is a VALID workspace and is accepted. Only a
# shipped role-library template subtree (skills/.../templates/role-library) or a
# deployed skills/ tree is rejected as TEMPLATE-NOT-WORKSPACE. A department dir
# whose REAL path is such a template tree (the "I pointed the workspace at the
# template" trick) is treated as NOT materialized → SHELL/FAIL.
#
# AF-PHANTOM-DEPT-TREE (C5) — PHANTOM DUPLICATE DEPARTMENT TREES:
#   A second failure this gate now makes impossible: the SAME canonical department
#   materialized TWICE side-by-side under departments/ as two sibling dirs whose
#   names normalize to ONE canonical slug (billing + billing-finance, legal +
#   legal-compliance, Sales + sales), plus phantom '.bak' dept dirs
#   (Presentations.bak-20260615-024720/). The variant-aware presence check counts
#   the pair as ONE department, so the floor gate can never see the duplication —
#   both trees keep diverging rosters on disk, agents get pointed at whichever dir
#   resolved first, and the '.bak' trees poison the SOP/substance gate. Detection
#   is department-floor.sibling_slug_collisions() + the '.bak' scan (single source
#   of truth). Remediation is reconcile-legacy-tree.py --merge-duplicates --apply
#   (keeps the canonical winner, layers the loser's unique roles in, archives the
#   loser OUT of departments/ — never deletes).
#
# EXIT CODES (fail-closed):
#   0  every REQUIRED department is FULL in the WORKSPACE (and no phantom trees)
#   3  AF-WORKSPACE-SHELL — at least one required dept is SHELL or PARTIAL
#   5  AF-PHANTOM-DEPT-TREE — two sibling dirs resolve to the same canonical slug,
#      or a phantom '.bak' dept dir is on disk
#   4  no workspace / cannot resolve a real (non-template) departments dir
#   2  could not run the gate (missing department-floor.py / python3)
#
# Read-only. Never writes. Idempotent. Safe to re-run any number of times.
# Mirrors the lib-onboarding-state.sh honesty philosophy, extended to the
# workspace layer: "materialized" is a VERIFIED claim with RAW counts, never a
# file-copy claim.
# ============================================================

set -uo pipefail

# ── Locate department-floor.py (single source of truth for the required set
#    AND the workspace-departments-dir resolver). Try repo layout + the two
#    canonical deployed skill layouts (Mac ~/.openclaw, VPS /data/.openclaw). ──
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOOR_PY=""
for _cand in \
  "$SELF_DIR/../23-ai-workforce-blueprint/scripts/department-floor.py" \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/department-floor.py" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/department-floor.py"; do
  if [ -f "$_cand" ]; then FLOOR_PY="$_cand"; break; fi
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "AF-WORKSPACE-SHELL: GATE CANNOT RUN — python3 not found." >&2
  exit 2
fi
if [ -z "$FLOOR_PY" ]; then
  echo "AF-WORKSPACE-SHELL: GATE CANNOT RUN — department-floor.py not found (looked in repo + ~/.openclaw + /data/.openclaw skills trees)." >&2
  exit 2
fi

# Allow the test harness (and operators) to point the gate at an explicit
# workspace departments dir, bypassing live detect_platform resolution.
EXPLICIT_DEPT_DIR=""
for _a in "$@"; do
  case "$_a" in
    --departments-dir=*) EXPLICIT_DEPT_DIR="${_a#*=}" ;;
  esac
done
# Positional form: --departments-dir <path>
_prev=""
for _a in "$@"; do
  if [ "$_prev" = "--departments-dir" ]; then EXPLICIT_DEPT_DIR="$_a"; fi
  _prev="$_a"
done

FLOOR_PY="$FLOOR_PY" EXPLICIT_DEPT_DIR="$EXPLICIT_DEPT_DIR" python3 - <<'PYEOF'
import importlib.util
import os
import sys
from pathlib import Path

FLOOR_PY = os.environ["FLOOR_PY"]
EXPLICIT = os.environ.get("EXPLICIT_DEPT_DIR", "").strip()

SOP_MIN_BYTES = 3072          # how-to.md SOP floor — matches verify-wiring.sh HOW_TO_MIN_BYTES
STANDALONE_SOP_MIN_BYTES = 7168  # standalone SOP file floor — matches qc-completeness SUBSTANTIVE_MIN_BYTES

# ── Load department-floor.py (filename has a hyphen → load via spec) ──
spec = importlib.util.spec_from_file_location("department_floor", FLOOR_PY)
df = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(df)
except Exception as e:  # noqa: BLE001
    print(f"AF-WORKSPACE-SHELL: GATE CANNOT RUN — could not import department-floor.py: {e}", file=sys.stderr)
    sys.exit(2)


def _is_template_path(p: Path) -> bool:
    """A path is a TEMPLATE (never a materialized workspace) if it lives in a
    shipped role-library template tree OR inside a deployed skills/ tree. A
    template on disk must NEVER satisfy this gate.

    DETECTION-BUG FIX (master-files IS the workspace home): the canonical
    architecture places the client's REAL workspace at
        <openclaw-master-files>/zero-human-company/<company>/departments/<dept>/
    — see department-floor.resolve_departments_dir(), build-workforce.py and
    post-build-role-workspaces.py, all of which resolve the workspace UNDER
    openclaw-master-files. The Zero Human Company lives inside master-files, so
    rejecting any path merely because it contains 'openclaw-master-files' is a
    BUG that false-flagged legitimately-built workforces (slug-named or
    master-files layouts) as SHELL. We therefore do NOT treat openclaw-master-files as a
    template marker. The genuine TEMPLATE markers are unchanged:
      * a shipped role-library template subtree (skills/.../templates/role-library)
      * a path under a deployed skills/ tree that is not itself a workspace
    A real workspace under master-files passes; a 'role-library' tree does not."""
    try:
        parts = Path(p).resolve().parts
    except Exception:
        return True  # fail-closed: unresolvable → treat as template/non-workspace
    # .../skills/<skill>/templates/role-library/...  (the shipped template tree)
    if "role-library" in parts:
        return True
    # any path under a skills/ tree is the deployed template, not the workspace
    if "skills" in parts and "workspace" not in parts:
        return True
    # NOTE: 'openclaw-master-files' is intentionally NOT a template marker — it is
    # the canonical workspace HOME (zero-human-company lives inside it).
    return False


# ── Resolve the CLIENT WORKSPACE departments dir ──
if EXPLICIT:
    departments_dir = Path(EXPLICIT)
else:
    departments_dir = df.resolve_departments_dir()

if departments_dir is None:
    print("AF-WORKSPACE-SHELL: NO WORKSPACE — could not resolve a departments dir "
          "on disk. A template copied into the skills/ tree is NOT a workspace; "
          "the client's workspace department was never instantiated.", file=sys.stderr)
    sys.exit(4)

departments_dir = Path(departments_dir)
if not departments_dir.is_dir():
    print(f"AF-WORKSPACE-SHELL: NO WORKSPACE — resolved departments dir does not "
          f"exist: {departments_dir}", file=sys.stderr)
    sys.exit(4)

# FAIL-CLOSED: the resolved dir must be a real WORKSPACE, not a template tree.
if _is_template_path(departments_dir):
    print(f"AF-WORKSPACE-SHELL: TEMPLATE-NOT-WORKSPACE — the only departments dir "
          f"that resolved is inside the skills/role-library/master-files TEMPLATE "
          f"tree, not a materialized client workspace:\n  {departments_dir.resolve()}\n"
          f"  'TEMPLATE DEPLOYED' is not 'WORKSPACE INSTANTIATED'. The workspace "
          f"department was never built.", file=sys.stderr)
    sys.exit(4)

# ── AF-PHANTOM-DEPT-TREE (C5): no two sibling dirs may resolve to ONE canonical
#    slug, and no phantom '.bak' dept dir may sit inside departments/. Checked
#    BEFORE the per-dept materialization table: while a canonical department is
#    materialized twice, "which tree is the department?" has no answer, so no
#    FULL/PARTIAL/SHELL verdict about it can be trusted. Detection lives in
#    department-floor.py (single source of truth) — a department-floor.py that
#    predates C5 cannot answer, and the check is loudly SKIPPED (never silently
#    passed) so the shell dimension still gates.
_collide = getattr(df, "sibling_slug_collisions", None)
_raw_dirs = getattr(df, "_raw_department_dirs", None)
if _collide is None or _raw_dirs is None:
    print("AF-PHANTOM-DEPT-TREE: CHECK SKIPPED — department-floor.py predates the "
          "C5 collision detector (no sibling_slug_collisions). Update Skill 23; the "
          "workspace-shell checks below still ran.", file=sys.stderr)
else:
    try:
        collisions = _collide(departments_dir)
        backup_dirs = _raw_dirs(departments_dir)[1]
    except Exception as e:  # noqa: BLE001 — fail-closed: cannot prove clean → FAIL
        print(f"AF-PHANTOM-DEPT-TREE: GATE CANNOT RUN — collision scan failed: {e}",
              file=sys.stderr)
        sys.exit(2)
    if collisions or backup_dirs:
        print("=" * 72)
        print("AF-PHANTOM-DEPT-TREE gate — phantom duplicate department trees")
        print(f"workspace departments dir : {departments_dir.resolve()}")
        print("-" * 72)
        for g in collisions:
            print(f"  COLLISION: canonical '{g['canonical']}' is materialized as "
                  f"{len(g['dirs'])} sibling dirs: {', '.join(g['dirs'])}")
        for b in backup_dirs:
            print(f"  PHANTOM BACKUP DIR: {b} (a backup tree is not a department)")
        print("-" * 72)
        print(f"COLLISIONS={len(collisions)}  PHANTOM_BACKUP_DIRS={len(backup_dirs)}")
        print("", file=sys.stderr)
        print("INVARIANT VIOLATED — AF-PHANTOM-DEPT-TREE: the same canonical department "
              "is materialized more than once (or a '.bak' tree is being carried as a "
              "department). The floor check counts the duplicate pair as ONE department, "
              "so the duplication is invisible to it — the trees diverge, agents resolve "
              "to whichever dir wins, and '.bak' trees poison the SOP/substance gate.",
              file=sys.stderr)
        print("REMEDIATION (operator, on the client box): "
              "python3 23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py "
              "--merge-duplicates            # dry-run, shows the plan\n"
              "                              "
              "python3 23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py "
              "--merge-duplicates --apply    # keep canonical winner, layer unique roles, "
              "archive loser OUT of departments/ (never deletes)", file=sys.stderr)
        sys.exit(5)

# ── Required department set = the department FLOOR (single source of truth) ──
try:
    verdict = df.evaluate_floor(departments_dir=departments_dir)
except Exception as e:  # noqa: BLE001
    print(f"AF-WORKSPACE-SHELL: GATE CANNOT RUN — evaluate_floor failed: {e}", file=sys.stderr)
    sys.exit(2)

if verdict.get("rc") == 7:
    print("AF-WORKSPACE-SHELL: NO WORKSPACE — department-floor reports no resolvable "
          "workforce on disk.", file=sys.stderr)
    sys.exit(4)

required = list(verdict.get("expected_floor", []))  # mandatory(−declined) + universal-primary(−declined)
variant_slugs = getattr(df, "CANONICAL_VARIANT_SLUGS", {})
_norm = getattr(df, "_norm", lambda s: str(s).lower().replace("-", ""))


def find_dept_dir(canonical_id):
    """Find the on-disk workspace dir for a canonical/required dept id, honoring
    the same variant slugs department-floor uses (finance == billing-finance …).
    Returns a Path or None."""
    wanted = {_norm(canonical_id)}
    for v in variant_slugs.get(canonical_id, []):
        wanted.add(_norm(v))
    for child in sorted(departments_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith((".", "_")):
            continue
        if _norm(child.name) in wanted:
            return child
    return None


def _role_has_real_sop(r):
    """RAW check for ONE role dir: does it carry a real SOP in any recognized
    shape? Returns True if any of the following holds:
      * how-to.md >= SOP_MIN_BYTES directly in the role dir, OR
      * a standalone substantive 0[1-9]-*.md file >= STANDALONE_SOP_MIN_BYTES
        directly in the role dir, OR
      * the role keeps its SOPs in a SOP/ subdir (case-insensitive: SOP/ or
        sops/) containing a substantive SOP file — a how-to.md >= SOP_MIN_BYTES
        or any 0[1-9]-*.md / *.md >= STANDALONE_SOP_MIN_BYTES.
    (Substance depth is qc-completeness's job; this gate only proves SOPs are not
    absent — the shell case.) ADDITIVE: recognizes MORE valid shapes, never
    weakens the empty-shell check."""
    # 1. how-to.md directly in the role dir
    try:
        howto = r / "how-to.md"
        if howto.is_file() and howto.stat().st_size >= SOP_MIN_BYTES:
            return True
    except Exception:
        pass
    # 2. standalone substantive 0[1-9]-*.md directly in the role dir
    try:
        for sf in r.glob("0[1-9]-*.md"):
            if sf.is_file() and sf.stat().st_size >= STANDALONE_SOP_MIN_BYTES:
                return True
    except Exception:
        pass
    # 3. a populated SOP/ (or sops/) subdir — the SOP-subdir shape
    try:
        for child in r.iterdir():
            if not child.is_dir():
                continue
            if child.name.lower() not in ("sop", "sops"):
                continue
            # a how-to.md inside the SOP subdir
            try:
                sub_howto = child / "how-to.md"
                if sub_howto.is_file() and sub_howto.stat().st_size >= SOP_MIN_BYTES:
                    return True
            except Exception:
                pass
            # any substantive markdown SOP file inside the SOP subdir
            try:
                for sf in child.glob("*.md"):
                    if sf.is_file() and sf.stat().st_size >= STANDALONE_SOP_MIN_BYTES:
                        return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def real_sop_present(dept_dir, role_subdirs):
    """RAW check: does ANY role subdir carry a real SOP, in any recognized shape
    (direct how-to.md, direct standalone SOP file, or a populated SOP/ subdir)?"""
    for r in role_subdirs:
        if _role_has_real_sop(r):
            return True
    return False


# Non-role child dirs that exist in EVERY dept and must never be counted as a
# role folder (they carry no role files). Matched case-insensitively.
NON_ROLE_DIR_NAMES = {"memory", "devils-advocate", "devil-s-advocate", "sop", "sops"}


def _is_role_folder(child):
    """RAW check: is this immediate child dir a real ROLE folder, regardless of
    naming convention?

    DETECTION-BUG FIX (slug-named roles): the old gate counted a role folder ONLY
    if its name started with a digit (NN-prefixed: 00-head, 01-specialist…). But
    legitimately-built workforces (and the master-files correction) use SLUG-named
    role folders (chief-marketing-officer/, head-of-sales/…). Those are real roles
    and must count. We accept a child dir as a role folder if EITHER:
      (a) it is NN-prefixed (name[:1].isdigit()), OR
      (b) it is slug-named AND carries the role-file fingerprint of a real role:
          IDENTITY.md or SOUL.md present, OR a real SOP in any shape
          (how-to.md / standalone SOP file / a populated SOP/ subdir).
    The role-file requirement on slug folders is what keeps NON-role dirs
    (memory/, devils-advocate/) from being miscounted as roles — they carry no
    IDENTITY/SOUL/SOP. This is ADDITIVE: it recognizes MORE valid role shapes and
    never weakens the empty-shell check (a dept with ZERO role folders of EITHER
    naming still classifies SHELL)."""
    if not child.is_dir():
        return False
    name = child.name
    if name.startswith((".", "_")):
        return False
    # (a) NN-prefixed role folder — always a role (legacy/canonical shape).
    if name[:1].isdigit():
        return True
    # Never treat a structural non-role dir as a role, even if it somehow has files.
    if name.lower() in NON_ROLE_DIR_NAMES:
        return False
    # (b) slug-named role folder — only if it carries the role-file fingerprint.
    try:
        if (child / "IDENTITY.md").is_file() or (child / "SOUL.md").is_file():
            return True
    except Exception:
        pass
    try:
        if _role_has_real_sop(child):
            return True
    except Exception:
        pass
    return False


def classify(dept_dir):
    """Return (status, facts) for a workspace dept dir. status ∈ FULL/PARTIAL/SHELL."""
    facts = {
        "numbered_roles": 0,   # count of REAL role folders (NN-prefixed OR slug-named)
        "identity_md": False,
        "soul_md": False,
        "real_sops": False,
        "symlink_to_template": False,
    }
    # A dept dir whose REAL path is a template tree is not materialized.
    try:
        if _is_template_path(dept_dir):
            facts["symlink_to_template"] = True
            return "SHELL", facts
    except Exception:
        return "SHELL", facts

    # Real role folders — EITHER NN-prefixed OR slug-named-with-role-files.
    role_dirs = []
    try:
        for child in dept_dir.iterdir():
            if _is_role_folder(child):
                role_dirs.append(child)
    except Exception:
        return "SHELL", facts
    facts["numbered_roles"] = len(role_dirs)
    facts["identity_md"] = (dept_dir / "IDENTITY.md").is_file()
    facts["soul_md"] = (dept_dir / "SOUL.md").is_file()

    if not role_dirs:
        return "SHELL", facts          # the DREAMS.md + memory/-only empty shell

    facts["real_sops"] = real_sop_present(dept_dir, role_dirs)

    if facts["identity_md"] and facts["soul_md"] and facts["real_sops"]:
        return "FULL", facts
    return "PARTIAL", facts


# ── Per-department report (RAW counts) ──
print("=" * 72)
print("AF-WORKSPACE-SHELL gate — WORKSPACE department materialization")
print(f"workspace departments dir : {departments_dir.resolve()}")
print(f"required departments (floor): {len(required)}")
print("-" * 72)
print(f"{'DEPARTMENT':<28} {'ROLES':>5} {'ID':>3} {'SOUL':>4} {'SOP':>4}  {'STATUS':<8}")
print("-" * 72)

shells = []
partials = []
missing = []
full = []

for cid in required:
    dd = find_dept_dir(cid)
    if dd is None:
        # Missing entirely from disk — department-floor already FAILs the count
        # for this; here we surface it as a workspace shell of the hardest kind.
        print(f"{cid:<28} {'—':>5} {'—':>3} {'—':>4} {'—':>4}  {'MISSING':<8}")
        missing.append(cid)
        continue
    status, f = classify(dd)
    roles = str(f["numbered_roles"])
    idflag = "Y" if f["identity_md"] else "n"
    soulflag = "Y" if f["soul_md"] else "n"
    sopflag = "Y" if f["real_sops"] else "n"
    note = "  (symlink→template)" if f["symlink_to_template"] else ""
    print(f"{cid:<28} {roles:>5} {idflag:>3} {soulflag:>4} {sopflag:>4}  {status:<8}{note}")
    if status == "FULL":
        full.append(cid)
    elif status == "PARTIAL":
        partials.append(cid)
    else:
        shells.append(cid)

print("-" * 72)
print(f"FULL={len(full)}  PARTIAL={len(partials)}  SHELL={len(shells)}  MISSING={len(missing)}  "
      f"REQUIRED={len(required)}")

bad = bool(shells or partials or missing)
if bad:
    if missing:
        print(f"  MISSING (not on disk at all): {', '.join(missing)}", file=sys.stderr)
    if shells:
        print(f"  SHELL (0 role subdirs — empty DREAMS/memory shell): {', '.join(shells)}", file=sys.stderr)
    if partials:
        print(f"  PARTIAL (role dirs present but no IDENTITY/SOUL or no real SOPs): "
              f"{', '.join(partials)}", file=sys.stderr)
    print("", file=sys.stderr)
    print("INVARIANT VIOLATED — AF-WORKSPACE-SHELL: a required department's WORKSPACE "
          "is not materialized.", file=sys.stderr)
    print("A role-library TEMPLATE copied to the skills/ tree does NOT make a "
          "workspace department. Run the workforce build (build-workforce.py / "
          "post-build-role-workspaces.py) so each department gets numbered role "
          "subdirs + IDENTITY.md + SOUL.md + real SOPs. Re-run this gate; it must "
          "pass with raw counts before reporting the client/department done.", file=sys.stderr)
    sys.exit(3)

print("ALL REQUIRED WORKSPACE DEPARTMENTS FULLY MATERIALIZED (raw counts above).")
sys.exit(0)
PYEOF
