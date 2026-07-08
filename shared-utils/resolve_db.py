"""
resolve_db.py — ONE canonical find_dashboard_db() for every Python script.

PRD item 1.3: create a single resolver function with the complete candidate
list so stickiness, variety, weight overrides, and selection logging always
find the DB on a default install.  Delete every local copy of find_dashboard_db
/ find_db and replace with an import of this function.

Import pattern (add the shared-utils folder to sys.path first):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from resolve_db import find_dashboard_db

    db_path = find_dashboard_db()   # Path or Path("") if not found
    if not db_path.exists():
        print('[warn] mission-control.db not found — DB features disabled')

The function is intentionally pure (no side-effects, no logging) so callers
can decide how loudly to fail when the DB is absent.
"""

import os
from pathlib import Path


# Ordered candidate list — first existing path wins.
#
# Column explanations:
#   DASHBOARD_DB_PATH  env-var override (operator or Command Center passes this;
#                      the CC app forwards its resolved DB_PATH under this name)
#   DATABASE_PATH      the SAME var the CC app itself resolves against in
#                      src/lib/db/index.ts (DB_PATH = DATABASE_PATH || cwd/…).
#                      Honored right after DASHBOARD_DB_PATH so standalone Python
#                      lands on the app's DB and never a decoy (DATA-08).
#   ~/projects/command-center  default Mac install (INSTALL.md line 323-327,
#                              run-full-install.sh DASHBOARD_DIR)
#   /data/projects/command-center  VPS / Hostinger Docker canonical
#   /opt/mission-control  Linux bare-metal or managed-hosting fallback
#   /app/mission-control.db  container-only fallback (e.g. Railway / Render)
#   --- legacy candidates below (kept for existing installs) ---
#   /data/mission-control  pre-v10 VPS path
#   ~/projects/mission-control  pre-v10 Mac path
#   ~/blackceo-command-center  earliest Dev path (Trevor's own box)
_CANDIDATE_BUILDERS = [
    # 1 — env-var override (checked dynamically so hot-reload works)
    lambda: Path(os.environ["DASHBOARD_DB_PATH"]) if "DASHBOARD_DB_PATH" in os.environ else None,
    # 2 — DATABASE_PATH: the app's own resolution key (src/lib/db/index.ts).
    #     DATA-08 decoy-DB fix — honored before any install-layout candidate so a
    #     standalone script always opens the SAME file the app writes/reads.
    lambda: Path(os.environ["DATABASE_PATH"]) if "DATABASE_PATH" in os.environ else None,
    # 3 — Mac default install path  (~/projects/command-center/mission-control.db)
    lambda: Path.home() / "projects" / "command-center" / "mission-control.db",
    # 4 — VPS canonical  (/data/projects/command-center/mission-control.db)
    lambda: Path("/data/projects/command-center/mission-control.db"),
    # 5 — Linux managed  (/opt/mission-control/mission-control.db)
    lambda: Path("/opt/mission-control/mission-control.db"),
    # 6 — container catch-all  (/app/mission-control.db)
    lambda: Path("/app/mission-control.db"),
    # 7 — legacy VPS  (/data/mission-control/mission-control.db)
    lambda: Path("/data/mission-control/mission-control.db"),
    # 8 — legacy Mac path  (~/projects/mission-control/mission-control.db)
    lambda: Path.home() / "projects" / "mission-control" / "mission-control.db",
    # 9 — earliest dev path  (~/blackceo-command-center/mission-control.db)
    lambda: Path.home() / "blackceo-command-center" / "mission-control.db",
]


def find_dashboard_db() -> Path:
    """
    Locate mission-control.db using the canonical candidate list.

    Checks (in order):
      1. $DASHBOARD_DB_PATH env var (operator / Command Center override)
      2. $DATABASE_PATH env var (the app's own resolution key — DATA-08)
      3. ~/projects/command-center/mission-control.db   (Mac default)
      4. /data/projects/command-center/mission-control.db  (VPS default)
      5. /opt/mission-control/mission-control.db
      6. /app/mission-control.db
      7. /data/mission-control/mission-control.db       (legacy VPS)
      8. ~/projects/mission-control/mission-control.db  (legacy Mac)
      9. ~/blackceo-command-center/mission-control.db   (legacy dev)

    Returns the first existing Path.

    When the DB is not found, returns Path("") — the same sentinel value
    the legacy local implementations returned.  IMPORTANT: on some systems
    Path("").exists() returns True (it resolves as the current directory).
    Always guard with:  if not db_path or str(db_path) == "":
    OR use the provided helper is_db_found(db_path).
    """
    for builder in _CANDIDATE_BUILDERS:
        candidate = builder()
        if candidate is None:
            continue
        if candidate.exists():
            return candidate
    return Path("")


def is_db_found(db_path: "Path | None") -> bool:
    """
    Safe guard for the Path("") sentinel.  Use instead of db_path.exists()
    to avoid the macOS/Linux edge case where Path("").exists() is True
    (Path("") resolves as "." = the current directory, which always exists).

    Usage:
        db = find_dashboard_db()
        if not is_db_found(db):
            print("DB not found")
    """
    if db_path is None:
        return False
    # Path("") stringifies as "." on all platforms — that is the sentinel value.
    s = str(db_path)
    if s in ("", "."):
        return False
    return db_path.is_file()


def dashboard_db_path_str() -> str:
    """
    Convenience wrapper — returns str path or empty string.
    Mirrors the return type callers that used str(find_db()) expect.
    """
    p = find_dashboard_db()
    return str(p) if is_db_found(p) else ""


def app_db_path() -> Path:
    """
    The path the Command Center *app* resolves at runtime.

    Mirrors src/lib/db/index.ts exactly:
        DB_PATH = process.env.DATABASE_PATH || <cwd>/mission-control.db

    Used only by verify_db_path_parity() to detect the DATA-08 decoy-DB
    condition — NOT by find_dashboard_db() (which additionally honors the
    app-forwarded $DASHBOARD_DB_PATH and the install-layout candidate list).
    """
    env = os.environ.get("DATABASE_PATH")
    if env:
        return Path(env)
    return Path.cwd() / "mission-control.db"


def verify_db_path_parity(app_db: "str | Path | None" = None):
    """
    DATA-08 decoy-DB guard.

    Assert that the DB this Python resolver would open is the SAME file the
    Command Center app writes/reads. Returns (ok: bool, detail: str) so the
    caller decides how loudly to fail.

    `app_db` (optional): the app's resolved DB path when the caller knows it
    (e.g. a deploy/converge step that also knows the app's cwd / DATABASE_PATH).
    When omitted it is derived from $DATABASE_PATH / cwd via app_db_path().

    NOTE: when DATABASE_PATH (or an explicit app_db / DASHBOARD_DB_PATH) is set,
    both the app and this resolver key off the SAME absolute path, so parity is
    structural. When none is set, parity relies on the candidate ordering
    matching the app's cwd default — the detail string flags that weaker state.
    """
    script_db = find_dashboard_db()
    expected = Path(app_db) if app_db else app_db_path()

    if not is_db_found(script_db):
        return False, (
            f"scripts resolve NO existing mission-control.db (app expects "
            f"{expected}); either the DB is not created yet or none of "
            f"$DASHBOARD_DB_PATH / $DATABASE_PATH / the install candidates exist."
        )
    try:
        same = script_db.resolve() == expected.resolve()
    except OSError:
        same = str(script_db) == str(expected)
    if same:
        return True, f"OK: scripts and app both resolve {script_db.resolve()}"
    return False, (
        f"DECOY-DB MISMATCH: scripts open {script_db.resolve()} but the app "
        f"resolves {expected.resolve()}. Set DATABASE_PATH (and forward it as "
        f"DASHBOARD_DB_PATH to subprocesses) so both agree."
    )


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="Resolve mission-control.db (shared resolver) or verify "
                    "app<->scripts DB-path parity (DATA-08 decoy-DB guard).")
    ap.add_argument("--verify-parity", action="store_true",
                    help="exit non-zero if the scripts' resolved DB != the app's DB")
    ap.add_argument("--app-db", default=None,
                    help="the app's resolved DB path (defaults to $DATABASE_PATH / cwd)")
    args = ap.parse_args()

    if args.verify_parity:
        ok, detail = verify_db_path_parity(args.app_db)
        print(f"[resolve_db] {'PASS' if ok else 'FAIL'}: {detail}")
        sys.exit(0 if ok else 2)

    # Default: print the resolved path (or warn if not found).
    db = find_dashboard_db()
    if is_db_found(db):
        print(f"[resolve_db] Found: {db}")
    else:
        print("[resolve_db] WARN: mission-control.db not found in any candidate location.")
        print("  Set $DASHBOARD_DB_PATH / $DATABASE_PATH or install the Command Center (skill 32).")
