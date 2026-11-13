#!/usr/bin/env python3
"""S75-041: one meaning per exit code, and every child code is mapped by tool.

Proves:

  * a mistyped factory command is an ERROR: ``factory.py card --no-such-option``
    exits 1, never 2 (which this CLI spells "waiting");
  * every table in ``factory.CHILD_EXIT_CODES`` agrees with the exit map the
    tool itself declares in its own source (so the table cannot drift);
  * ``child_exit(tool, code)`` answers the outcome word by tool name --
    ``spend_ledger.py`` 5 is ``rejected``, ``video_router.py`` 3 is ``waiting``,
    ``delivery_checklist.py`` 5 is ``rejected`` -- and an unknown tool or code
    answers ``error``, never the raw number;
  * ``next`` carries the tool's ``exit_codes`` table on its envelope.

Run from the skill root:
    python3 scripts/core/intake_preflight/test_exit_codes_s75_041.py

stdlib only, no network, no provider, writes nothing.
"""
import ast
import io
import sys
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent.parent          # 75-drama-song-ad-factory/
FACTORY = HERE / "factory.py"

#: tool name -> the file that declares its own EXIT map (None: no map to
#: compare; the number is read from the module's documented TICK_EXIT_STOP).
DECLARERS = {
    "factory.py": FACTORY,
    "spend_ledger.py": SKILL / "scripts/core/spend_ledger.py",
    "qc_gate.py": SKILL / "scripts/core/qc_gate.py",
    "video_router.py": SKILL / "scripts/core/video_router/video_router.py",
    "narrator_rule.py": (SKILL / "scripts/core/lip_sync/narrator_rule/"
                                "narrator_rule.py"),
    "ceiling_cli.py": None,
    "delivery_checklist.py": (SKILL / "scripts/core/delivery_checklist/"
                                     "delivery_checklist.py"),
    # run_watch.py declares no EXIT map -- only TICK_EXIT_STOP = 10, which the
    # dedicated checks below compare against; None keeps it out of the EXIT-map
    # comparison instead of asserting a map the tool never declares.
    "run_watch.py": None,
    "prompt-budget": None,
}

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append("%s: %s" % (name, detail))
    print("  %s %s" % ("ok" if ok else "FAIL", name))


def declared_exit_map(path):
    """The last module-level``EXIT = {outcome: code}`` the file declares,
    inverted to ``{code: outcome}``. ``{}`` when it declares none."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "EXIT"
                   for t in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, dict):
            found = value
    if found is None:
        return {}
    return {int(code): str(outcome) for outcome, code in found.items()}


def declared_int(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
    return None


def next_sets_exit_codes():
    """``_next_stage`` must assign ``nxt["exit_codes"]`` -- the map by tool."""
    tree = ast.parse(FACTORY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_next_stage":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign)
                        and isinstance(sub.targets[0], ast.Subscript)
                        and isinstance(sub.targets[0].value, ast.Name)
                        and sub.targets[0].value.id == "nxt"
                        and isinstance(sub.targets[0].slice, ast.Constant)
                        and sub.targets[0].slice.value == "exit_codes"):
                    return True
    return False


def main():
    core = str(HERE.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    from intake_preflight import factory            # noqa: PLC0415

    # 1. a mistyped command is an error (1), never "waiting" (2) ------------
    for argv in (["card", "--no-such-option"],
                 ["no-such-command"]):
        code, stderr = None, ""
        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                factory.main(argv)
        except SystemExit as exc:
            code = exc.code
        except Exception as exc:                     # noqa: BLE001
            code = "raised %r" % (exc,)
        stderr = buf.getvalue()
        check("%r exits 1" % (" ".join(argv),), code == 1, repr(code))
        check("%r prints usage" % (" ".join(argv),),
              "usage:" in stderr, repr(stderr[:120]))

    # --help must stay a success (0): the override changes only error() -----
    help_code = None
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            factory.main(["--help"])
    except SystemExit as exc:
        help_code = exc.code
    check("--help still exits 0", help_code == 0, repr(help_code))

    # 2. the table agrees with each tool's own declared map -----------------
    for tool, path in DECLARERS.items():
        if path is None:
            check("table carries %r" % tool, tool in factory.CHILD_EXIT_CODES,
                  "missing")
            continue
        check("%r source file exists" % tool, path.is_file(), str(path))
        if not path.is_file():
            continue
        declared = declared_exit_map(path)
        if not declared:
            check("%r declares an EXIT map" % tool, False, "none found")
            continue
        check("%r map matches its own source" % tool,
              factory.CHILD_EXIT_CODES.get(tool) == declared,
              "table=%r source=%r" % (factory.CHILD_EXIT_CODES.get(tool),
                                      declared))

    watch = SKILL / "scripts/core/heartbeat/run_watch.py"
    check("run_watch stop code matches TICK_EXIT_STOP",
          watch.is_file() and declared_int(watch, "TICK_EXIT_STOP") == 10,
          repr(declared_int(watch, "TICK_EXIT_STOP") if watch.is_file() else None))
    check("table carries run_watch stop as 10 -> stop",
          factory.CHILD_EXIT_CODES.get("run_watch.py", {}).get(10) == "stop",
          repr(factory.CHILD_EXIT_CODES.get("run_watch.py")))

    # 3. child_exit names the outcome, never a raw number -------------------
    cases = (
        ("factory.py", 0, "ok"),
        ("factory.py", 1, "error"),
        ("factory.py", 2, "waiting"),
        ("spend_ledger.py", 5, "rejected"),
        ("spend_ledger.py", 3, "waiting"),
        ("qc_gate.py", 5, "rejected"),
        ("video_router.py", 3, "waiting"),
        ("video_router.py", 5, "rejected"),
        ("narrator_rule.py", 4, "parked"),
        ("narrator_rule.py", 5, "rejected"),
        ("ceiling_cli.py", 4, "parked"),
        ("delivery_checklist.py", 5, "rejected"),
        ("delivery_checklist.py", 1, "error"),
        ("run_watch.py", 10, "stop"),
        ("prompt-budget", 3, "waiting"),
        ("scripts/core/spend_ledger.py", 5, "rejected"),
    )
    for tool, code, want in cases:
        got = factory.child_exit(tool, code)
        check("child_exit(%r, %d) is %r" % (tool, code, want), got == want,
              repr(got))
        check("child_exit(%r, %d) is a word, not a number" % (tool, code),
              isinstance(got, str), repr(got))

    for tool, code in (("no-such-tool.py", 0), ("spend_ledger.py", 2),
                       ("spend_ledger.py", "x"), ("spend_ledger.py", None)):
        got = factory.child_exit(tool, code)
        check("unknown %r/%r answers error" % (tool, code), got == "error",
              repr(got))

    # 4. next hands the caller the tool's table, by name --------------------
    check("_next_stage sets nxt['exit_codes']", next_sets_exit_codes(), "absent")

    print("test_exit_codes_s75_041: %s (%d checks, %d failures)"
          % ("PASS" if not FAILS else "FAIL", CHECKS, len(FAILS)))
    for failure in FAILS:
        print(" -", failure)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
