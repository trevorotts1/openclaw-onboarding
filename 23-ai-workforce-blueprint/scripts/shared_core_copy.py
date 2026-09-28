"""Place a workspace's shared AGENTS.md / TOOLS.md / USER.md as REAL-FILE copies (N29).

Never a symlink: the OpenClaw workspace-root boundary guard rejects a symlink that
resolves outside the reading agent's own workspace and injects a ~107-char stub, so
the agent silently runs with no instructions (N29, amended 2026-07-31).

Never destructive: a real, non-empty file already in place is left byte-identical.
Refreshing it to the box canonical is the updater's job (link_shared_core_files in
update-skills.sh / install.sh: backup + content preservation + verified copy).
"""
import os
from pathlib import Path

SHARED_CORE_FILES = ("AGENTS.md", "TOOLS.md", "USER.md")


def ensure_core_copy(src, dst):
    """Make `dst` a real copy of `src` unless it already is a real, non-empty file.

    Returns "kept" (real non-empty file left untouched), "copied" (missing, empty or
    symlinked dst replaced by a real copy) or "skipped" (src unreadable/empty or the
    write failed -- dst is left exactly as it was, fail-open).
    """
    src, dst = Path(src), Path(dst)
    if not dst.is_symlink() and dst.is_file() and dst.stat().st_size > 0:
        return "kept"
    try:
        data = src.read_bytes()
    except OSError:
        return "skipped"
    if not data:
        return "skipped"
    tmp = dst.with_name(f".{dst.name}.tmp-core-{os.getpid()}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dst)  # replaces a symlink itself, never the file it points at
    except OSError:
        tmp.unlink(missing_ok=True)
        return "skipped"
    return "copied"
