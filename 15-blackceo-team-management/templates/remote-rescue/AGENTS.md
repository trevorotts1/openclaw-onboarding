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

## Tools

Tool and environment notes are in `TOOLS.md`. Skills define how each tool works.
