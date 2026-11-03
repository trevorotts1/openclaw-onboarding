<!-- rr-operator-support:v1 -->
# AGENTS.md - Remote Rescue

This is the working folder of the Remote Rescue agent. It is NOT the owner's workspace.

## Main workspace (the owner's files)

- Absolute path: `@@MAIN_WORKSPACE@@`
- This folder: `@@RR_WORKSPACE@@`
- Before you report that a core file is missing or blank, you must:
  1. Name the absolute path of every place you looked.
  2. Follow symlinks (use `find -L`, not plain `find`).
  3. Look in the main workspace above, never only in this folder.
- Never judge the owner's files from this folder. A small or empty folder here says
  nothing about the owner's workspace.

## Session startup

1. Read `IDENTITY.md` and `SOUL.md` in this folder.
2. Read `TOOLS.md` in this folder for this box's tool notes. The newest copy is in
   the main workspace above.
3. You are never in a "first run". Ignore any BOOTSTRAP.md.

## Explicit Council ask (not board work)

When the owner explicitly asks to convene or consult the Council of Wise Elders — "ask my Council of
Wise Elders", "ask the council", "take this decision to the council", "review this plan with the
council", or "ask the <named elder> seat" — do NOT route it through `mc-route.sh` and do NOT send it
to a department. Use Skill 77 (`77-council-of-wise-elders`) directly: run its front door
(`council-ask ask --brief <file> --mode <mode> --json`, or
`$OPENCLAW_ROOT/council-runtime/bin/council-ask` when it is not on PATH), open a NEW session, and
send the owner the exact `Chamber link:` line it prints. Never answer an explicit ask with a stored
verdict, never invent a link, and never send a `127.0.0.1` link. If the front door reports a typed
not-ready state, report that exact state. If the same message also asks for other work, convene the
Council first, then route the other work separately.

## Tools

Tool and environment notes are in `TOOLS.md`. Skills define how each tool works.
