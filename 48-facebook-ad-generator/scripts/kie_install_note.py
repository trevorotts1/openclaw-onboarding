#!/usr/bin/env python3
"""Skill 48 install-time KIE key note (INF002). ALWAYS exits 0: a missing key never
blocks the install, it only leaves one honest note. Prints/writes names, never values.

  keyless  -> NOTE printed (install log) + written to the skill's status file
  has key  -> source printed, stale note removed, nothing else written
  unknown  -> shared secret helper not found: say so, never claim keyless
The Kie credit-balance check stays a RUN-TIME gate (ad_director Phase-0); it is not here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NOTE = ("Installed. KIE API key needed before ads can be generated. "
        "Add KIE_API_KEY to ~/.openclaw/secrets/.env.")
UNCHECKED = ("Installed. Could not check for a KIE API key here (shared secret helper not "
             "found); the key is verified when an ad run starts.")


def run(status_file: Path, out=print) -> str:
    """Returns 'found' | 'missing' | 'unchecked'."""
    status_file = Path(status_file)
    try:
        import ad_build_check as abc
        if abc._secret_helper() is None:
            out(UNCHECKED)
            return "unchecked"
        found = []
        key = abc.resolve_kie_key(found.append)
    except Exception as exc:  # noqa: BLE001 - never block an install
        out(f"{UNCHECKED} ({type(exc).__name__})")
        return "unchecked"
    try:
        if key:
            if status_file.exists():
                status_file.unlink()
            out("  [ok]   " + (found[0] if found else "KIE key found"))
            return "found"
        out(NOTE)
        status_file.write_text(NOTE + "\n")
        return "missing"
    except OSError as exc:
        out(f"  [note] could not write {status_file}: {exc.__class__.__name__}")
        return "missing" if not key else "found"


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("install-status.txt"))
    sys.exit(0)
