#!/usr/bin/env python3
"""S75-010: stage commands have ONE source.

Proves, statically (it reads files and runs nothing else):

  * the Markdown runbook's human copy and
    `scripts/core/intake_preflight/stage_commands.json` agree row for row --
    same stage ids, and each row's command is `shlex.join` of the JSON `argv`;
  * the twelve canonical stages plus `agnes-keyframes`,
    `agnes-video-segment`, `clips`, `trailers` and `platform-fit` are present;
  * every command's script resolves on disk (argv[1] after a leading
    interpreter, or argv[0]);
  * every `{PLACEHOLDER}` token is one of the declared allowed names;
  * the human copy carries the note that says it is a copy.

Run from the skill root:
    python3 scripts/core/intake_preflight/test_stage_commands_s75_010.py

stdlib only, no network, no provider, writes nothing.
"""
import json
import re
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent.parent          # 75-drama-song-ad-factory/
RUNBOOK = SKILL / "references" / "stage-runbook.md"
COMMANDS = HERE / "stage_commands.json"

ADDITION_STAGES = ("agnes-keyframes", "agnes-video-segment", "clips",
                   "trailers", "platform-fit")

#: The only placeholder names a stage command may use (S75-010 step 4).
ALLOWED_PLACEHOLDERS = {
    "RUN", "RUN_ID", "MODEL", "COST_MINOR", "OWNER", "SEGMENT",
    "LENGTH_S", "REQUIRED_CHECKS",
}

INTERPRETERS = ("python3", "python", "/opt/homebrew/bin/python3")

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append("%s: %s" % (name, detail))
    print("  %s %s" % ("ok" if ok else "FAIL", name))


def canonical_stages():
    """The 12-stage order, from the same list factory.py reads."""
    core = str(HERE.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    from batch_mode.batch import STAGES       # noqa: PLC0415
    return tuple(sid for sid, _title in STAGES)


def runbook_rows():
    """Parse the human table the same way the control tool used to."""
    rows = {}
    for line in RUNBOOK.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        sid = cells[0]
        if (re.fullmatch(r"[a-z0-9-]+", sid)
                and cells[1].startswith("`") and cells[1].endswith("`")
                and cells[2]):
            rows[sid] = cells[1][1:-1]
    return rows


def command_script(argv):
    """argv[1] after a leading interpreter, else argv[0]; "" when none runs a
    script (`python3 -c ...`). Mirrors factory._command_script."""
    tokens = [str(t) for t in argv]
    if not tokens:
        return ""
    if tokens[0] in INTERPRETERS:
        if len(tokens) < 2 or tokens[1].startswith("-"):
            return ""
        return tokens[1]
    return tokens[0]


def main():
    text = RUNBOOK.read_text(encoding="utf-8")
    doc = json.loads(COMMANDS.read_text(encoding="utf-8"))
    table = runbook_rows()
    canonical = canonical_stages()
    wanted = tuple(canonical) + tuple(ADDITION_STAGES)

    check("stage_commands.json is one object per stage id",
          isinstance(doc, dict) and bool(doc), repr(type(doc)))
    check("human copy and JSON list the same stage ids",
          set(table) == set(doc),
          "table=%r json=%r" % (sorted(table), sorted(doc)))
    for sid in wanted:
        check("stage %r present in JSON" % sid, sid in doc, "missing")
        check("stage %r present in the human copy" % sid, sid in table, "missing")

    for sid in sorted(set(table) & set(doc)):
        row = doc[sid]
        argv = row.get("argv")
        check("stage %r has a non-empty argv list" % sid,
              isinstance(argv, list) and bool(argv), repr(argv))
        if not (isinstance(argv, list) and argv):
            continue
        joined = shlex.join([str(t) for t in argv])
        check("stage %r human copy matches the JSON argv" % sid,
              table[sid] == joined, "table=%r json=%r" % (table[sid], joined))
        # every placeholder is one of the declared allowed names
        used = []
        for tok in argv:
            used.extend(re.findall(r"\{([A-Za-z0-9_]+)\}", str(tok)))
        unknown = sorted({n for n in used if n not in ALLOWED_PLACEHOLDERS})
        check("stage %r uses only allowed placeholders" % sid,
              not unknown, "unknown=%r" % unknown)
        # the script the command runs exists on disk
        head = command_script(argv)
        if head:
            check("stage %r script %r exists" % (sid, head),
                  (SKILL / head).is_file(), "missing on disk")
        else:
            check("stage %r names no script (inline probe, allowed)" % sid, True)

    check("human copy says it is a copy",
          "This table is a human copy." in text, "note missing")
    check("human copy names the JSON source",
          "scripts/core/intake_preflight/stage_commands.json" in text,
          "source path missing")

    print("test_stage_commands_s75_010: %s (%d checks, %d failures)"
          % ("PASS" if not FAILS else "FAIL", CHECKS, len(FAILS)))
    for failure in FAILS:
        print(" -", failure)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
