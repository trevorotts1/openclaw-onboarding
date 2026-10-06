#!/usr/bin/env python3
"""Owner-sends hold: one durable switch that stops the AUTOMATIC messages to a
client OWNER (the Skill 23 Presentations welcome and the Skill 37 closeout
celebration), on every path that reaches them.

Stored in .workforce-build-state.json (OPT-IN -- never on by default):
  ownerSendsHold: true    HELD
  anything else / absent  clear (unchanged behaviour)

Nothing in the build, the resume crons or the closeout ever writes this key;
only `hold` and `release` below do. It never auto-clears.

CLI:
  owner_sends_hold.py check   <state-file>           exit 0 = HELD (reason printed), 1 = clear
  owner_sends_hold.py hold    <state-file> [reason]  set the hold
  owner_sends_hold.py release <state-file>           release it (explicit false)
Callers treat ANY other exit (python or this helper missing, unreadable
state) as HELD: an unrequested owner message cannot be taken back.
"""
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def hold_reason(state):
    """Why sends are held, or None when they may go out. Opt-in: only an
    explicit ownerSendsHold=true holds."""
    if state.get("ownerSendsHold") is True:
        return "ownerSendsHold=true" + (f" ({state['ownerSendsHoldReason']})"
                                        if state.get("ownerSendsHoldReason") else "")
    return None


def _update(path, mutate):
    # Same lock protocol as 23-ai-workforce-blueprint/scripts/workforce_state.py.
    path = Path(path)
    with open(str(path) + ".write.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(path.read_text(encoding="utf-8"))
        mutate(state)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".owner-hold.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("check", "hold", "release"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, state_file = argv[1], Path(argv[2])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if cmd == "check":
        if not state_file.exists():
            return 1
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"state unreadable ({e}); holding")
            return 0
        reason = hold_reason(state if isinstance(state, dict) else {})
        if reason:
            print(reason)
            return 0
        return 1
    if cmd == "hold":
        reason = " ".join(argv[3:]) or "operator hold"
        _update(state_file, lambda s: s.update(ownerSendsHold=True, ownerSendsHoldReason=reason,
                                               ownerSendsHoldAt=now))
        print(f"ownerSendsHold=true ({reason})")
        return 0
    _update(state_file, lambda s: s.update(ownerSendsHold=False, ownerSendsReleasedAt=now))
    print("ownerSendsHold=false (released)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
