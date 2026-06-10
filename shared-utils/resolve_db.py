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
#   DASHBOARD_DB_PATH  env-var override (operator or Command Center passes this)
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
    # 2 — Mac default install path  (~/projects/command-center/mission-control.db)
    lambda: Path.home() / "projects" / "command-center" / "mission-control.db",
    # 3 — VPS canonical  (/data/projects/command-center/mission-control.db)
    lambda: Path("/data/projects/command-center/mission-control.db"),
    # 4 — Linux managed  (/opt/mission-control/mission-control.db)
    lambda: Path("/opt/mission-control/mission-control.db"),
    # 5 — container catch-all  (/app/mission-control.db)
    lambda: Path("/app/mission-control.db"),
    # 6 — legacy VPS  (/data/mission-control/mission-control.db)
    lambda: Path("/data/mission-control/mission-control.db"),
    # 7 — legacy Mac path  (~/projects/mission-control/mission-control.db)
    lambda: Path.home() / "projects" / "mission-control" / "mission-control.db",
    # 8 — earliest dev path  (~/blackceo-command-center/mission-control.db)
    lambda: Path.home() / "blackceo-command-center" / "mission-control.db",
]


def find_dashboard_db() -> Path:
    """
    Locate mission-control.db using the canonical candidate list.

    Checks (in order):
      1. $DASHBOARD_DB_PATH env var (operator / Command Center override)
      2. ~/projects/command-center/mission-control.db   (Mac default)
      3. /data/projects/command-center/mission-control.db  (VPS default)
      4. /opt/mission-control/mission-control.db
      5. /app/mission-control.db
      6. /data/mission-control/mission-control.db       (legacy VPS)
      7. ~/projects/mission-control/mission-control.db  (legacy Mac)
      8. ~/blackceo-command-center/mission-control.db   (legacy dev)

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


if __name__ == "__main__":
    # Quick self-test: print the resolved path (or warn if not found).
    db = find_dashboard_db()
    if is_db_found(db):
        print(f"[resolve_db] Found: {db}")
    else:
        print("[resolve_db] WARN: mission-control.db not found in any candidate location.")
        print("  Set $DASHBOARD_DB_PATH or install the Command Center (skill 32).")
