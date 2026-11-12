#!/usr/bin/env python3
"""qc_static_checks.py - Python replacements for the Skill 75 shell checks that
decide pass/fail from grep output. Stdlib only.

WHY
  scripts/qc-no-direct-kie.sh and scripts/qc-no-local-asr.sh run
  `grep ... 2>/dev/null ... || true` with no pipefail. If grep itself fails
  (unreadable file, a flag the local grep does not know), the hit list is empty
  and the script prints "clean" and exits 0. Silence is being read as proof.

HOW THIS IS DIFFERENT
  * Every file in scope is opened and read. A file that cannot be read is a
    FAILURE (exit 1), never skipped.
  * Python files are parsed; imports are found in the syntax tree, not by
    matching text, so a comment or a string cannot hide or fake an import.
  * Zero files scanned is a FAILURE.
  * Each check first runs a planted positive control in a throwaway folder; if
    the check cannot find its own planted offender it reports itself broken
    (exit 1) instead of reporting the tree clean.

Commands
  no-direct-kie   --core DIR
  no-local-asr    --core DIR [--run-dir DIR ...]
  no-operator-paths --core DIR
  selftest

Exit: 0 clean, 2 offender(s) found (listed), 1 the check could not run.
"""
import argparse
import ast
import json
import os
import sys
import tempfile
from urllib.parse import urlsplit

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
KIE_ALLOWED_DIR = "kie_dispatch"
DOCS_HOST = "docs.kie.ai"
BANNED_ASR_MODULES = {"whisper", "openai_whisper"}
ALLOWED_FASTER_WHISPER_FILE = os.path.join("audio_c3", "lyric_timing.py")
OPERATOR_NEEDLES = ("Downloads", "drama-song-factory-build", "openclaw-onboarding/")


class CheckBroken(Exception):
    pass


def is_test_file(name):
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def source_files(root, suffixes=(".py",)):
    if not os.path.isdir(root):
        raise CheckBroken("not a folder: %s" % root)
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if is_test_file(name):
                continue
            if suffixes and not name.endswith(suffixes):
                continue
            out.append(os.path.join(base, name))
    if not out:
        raise CheckBroken("no files in scope under %s (a moved tree must not pass)" % root)
    return out


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise CheckBroken("cannot read %s: %s" % (path, exc))


def string_constants(path):
    """Every string literal in a Python file, with its line number."""
    try:
        tree = ast.parse(read_text(path), filename=path)
    except SyntaxError as exc:
        raise CheckBroken("cannot parse %s: %s" % (path, exc))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def imported_modules(path):
    try:
        tree = ast.parse(read_text(path), filename=path)
    except SyntaxError as exc:
        raise CheckBroken("cannot parse %s: %s" % (path, exc))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module.split(".")[0]))
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in ("import_module", "__import__") and node.args \
                    and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                found.append((node.lineno, node.args[0].value.split(".")[0]))
    return found


def kie_hosts(text):
    """Hosts ending in kie.ai that appear in one string literal."""
    hosts = []
    for token in text.replace('"', " ").replace("'", " ").split():
        candidate = token if "://" in token else "//" + token
        try:
            host = (urlsplit(candidate).hostname or "").lower()
        except ValueError:
            continue
        if host == "kie.ai" or host.endswith(".kie.ai"):
            hosts.append(host)
    return hosts


def check_no_direct_kie(core):
    offenders = []
    for path in source_files(core):
        rel = os.path.relpath(path, core)
        if rel.split(os.sep)[0] == KIE_ALLOWED_DIR:
            continue
        for lineno, value in string_constants(path):
            for host in kie_hosts(value):
                if host != DOCS_HOST:
                    offenders.append({"file": rel, "line": lineno, "host": host})
    return offenders


def check_no_local_asr(core, run_dirs=()):
    offenders = []
    for root, is_core in [(core, True)] + [(d, False) for d in run_dirs]:
        for path in source_files(root):
            rel = os.path.relpath(path, root)
            for lineno, module in imported_modules(path):
                if module in BANNED_ASR_MODULES:
                    offenders.append({"file": path, "line": lineno, "import": module})
                if module == "faster_whisper" and not (
                        is_core and rel == ALLOWED_FASTER_WHISPER_FILE):
                    offenders.append({"file": path, "line": lineno, "import": module,
                                      "why": "only audio_c3/lyric_timing.py may import it"})
    return offenders


def check_no_operator_paths(core):
    offenders = []
    for path in source_files(core, suffixes=()):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise CheckBroken("cannot read %s: %s" % (path, exc))
        if b"\x00" in raw[:8192]:
            continue                                   # binary file
        text = raw.decode("utf-8", "replace")
        for number, line in enumerate(text.splitlines(), 1):
            for needle in OPERATOR_NEEDLES:
                if needle in line:
                    offenders.append({"file": os.path.relpath(path, core),
                                      "line": number, "needle": needle})
    return offenders


def controls():
    """Planted positives and negatives. Returns a list of (name, ok)."""
    proofs = []
    with tempfile.TemporaryDirectory() as core:
        os.makedirs(os.path.join(core, "kie_dispatch"))
        os.makedirs(os.path.join(core, "audio_c3"))
        os.makedirs(os.path.join(core, "bad"))
        open(os.path.join(core, "kie_dispatch", "ok.py"), "w").write(
            'URL = "https://api.kie.ai/api/v1/jobs/createTask"\n')
        open(os.path.join(core, "audio_c3", "lyric_timing.py"), "w").write(
            "import faster_whisper\n")
        open(os.path.join(core, "clean.py"), "w").write(
            '# import whisper  (a comment is not an import)\n'
            'DOC = "see https://docs.kie.ai/market for the docs"\n'
            'NOTE = "the word whisper in a string is not an import"\n')
        proofs.append(("clean tree: no direct-KIE offender", check_no_direct_kie(core) == []))
        proofs.append(("clean tree: no ASR offender", check_no_local_asr(core) == []))
        open(os.path.join(core, "bad", "direct.py"), "w").write(
            'import urllib.request\nurllib.request.urlopen("https://api.kie.ai/x")\n')
        open(os.path.join(core, "bad", "asr.py"), "w").write(
            "import importlib\nm = importlib.import_module('whisper')\n")
        open(os.path.join(core, "bad", "second.py"), "w").write("from faster_whisper import X\n")
        open(os.path.join(core, "bad", "paths.py"), "w").write('ROOT = "~/Downloads/x"\n')
        proofs.append(("planted direct KIE call is found",
                       [o["file"] for o in check_no_direct_kie(core)]
                       == [os.path.join("bad", "direct.py")]))
        asr = sorted(os.path.basename(o["file"]) for o in check_no_local_asr(core))
        proofs.append(("planted whisper import (even a dynamic one) is found",
                       asr == ["asr.py", "second.py"]))
        proofs.append(("planted operator path is found",
                       [o["file"] for o in check_no_operator_paths(core)]
                       == [os.path.join("bad", "paths.py")]))
        open(os.path.join(core, "bad", "broken.py"), "w").write("def (:\n")
        try:
            check_no_local_asr(core)
            proofs.append(("an unparseable file breaks the check, never passes", False))
        except CheckBroken:
            proofs.append(("an unparseable file breaks the check, never passes", True))
    with tempfile.TemporaryDirectory() as empty:
        try:
            check_no_direct_kie(empty)
            proofs.append(("an empty tree fails closed", False))
        except CheckBroken:
            proofs.append(("an empty tree fails closed", True))
    return proofs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("no-direct-kie", "no-local-asr", "no-operator-paths"):
        p = sub.add_parser(name)
        p.add_argument("--core", required=True)
        if name == "no-local-asr":
            p.add_argument("--run-dir", action="append", default=[])
    sub.add_parser("selftest")
    a = ap.parse_args(argv)
    proofs = controls()
    if a.cmd == "selftest":
        for name, ok in proofs:
            print(("ok   " if ok else "FAIL ") + name)
        return 0 if all(ok for _, ok in proofs) else 1
    if not all(ok for _, ok in proofs):
        print(json.dumps({"outcome": "error", "reason_code": "CHECK_INSTRUMENT_BROKEN",
                          "failed_controls": [n for n, ok in proofs if not ok]}, indent=2))
        return 1
    try:
        if a.cmd == "no-direct-kie":
            offenders = check_no_direct_kie(a.core)
        elif a.cmd == "no-local-asr":
            offenders = check_no_local_asr(a.core, a.run_dir)
        else:
            offenders = check_no_operator_paths(a.core)
        scanned = len(source_files(a.core, suffixes=() if a.cmd == "no-operator-paths"
                                   else (".py",)))
    except CheckBroken as exc:
        print(json.dumps({"outcome": "error", "reason_code": "CHECK_COULD_NOT_RUN",
                          "detail": str(exc)}, indent=2))
        return 1
    # The two shell checks this replaces named their offenders on stderr (a
    # caller-visible contract the tests pin); keep that, and keep the JSON
    # summary on stdout for machine readers.
    for offender in offenders:
        print("  offender: %s:%s" % (offender.get("file"), offender.get("line")),
              file=sys.stderr)
    print(json.dumps({"outcome": "rejected" if offenders else "ok", "check": a.cmd,
                      "files_scanned": scanned, "offenders": offenders}, indent=2))
    return 2 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
