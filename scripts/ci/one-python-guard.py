#!/usr/bin/env python3
"""one-python-guard.py: fail CI when install code picks a Python by itself.

ONE canonical interpreter per box (v27.1.80). Every Python package install and
every venv in shipped shell code goes through the resolver in
platform/common.sh (oc_python / oc_pip_install / oc_venv / oc_uv_tool_install,
or the shared-utils/oc-python.sh front door). Anything else lets PATH choose the
interpreter, which is how Hostinger boxes grew a Debian 3.13 tree, a Homebrew
3.14 user tree and Homebrew's own site-packages side by side.

Scanned: every git-tracked *.sh / *.bash file outside tests, CI and archive
folders. A file is skipped for its folder, never for its name: an install script
called test-*.sh outside a tests folder is still scanned. Comment lines (first non-blank character `#`) are ignored; echo /
warn strings are NOT ignored, because a remediation line an agent copies is an
install site too.

Rules (one finding per rule per line):
  BARE_PIP      `pip install` / `pip3 install` / `pip uninstall` run as a command
                (not `<python> -m pip`, not a venv's `.../bin/pip`)
  PIPX          `pipx install` / `pipx inject` (a separate interpreter per app)
  PATH_PYTHON   `python3 -m pip` with a literal interpreter name (python,
                python3, python3.X) or a literal system / Homebrew path
  VENV          `-m venv` anywhere: venvs come from oc_venv (uv --seed; Debian's
                python has no ensurepip, so `-m venv` makes hollow venvs)
  UV_NO_PYTHON  `uv venv` / `uv pip install` / `uv tool install` without an
                explicit `--python <resolver value>` (a literal python3 is not one)
  BSP_NO_USER   `--break-system-packages` / PIP_BREAK_SYSTEM_PACKAGES on a pip
                install line without `--user`
  BREW_PYTHON   a Homebrew / Linuxbrew python path

Allowlist: ONLY the resolver block itself, platform/common.sh between
`# >>> OC-ONE-PYTHON BEGIN` and `# <<< OC-ONE-PYTHON END`.

Usage:
  python3 scripts/ci/one-python-guard.py                 # scan the repo
  python3 scripts/ci/one-python-guard.py FILE [FILE...]  # scan these files
Exit 0 clean, 1 findings, 2 usage / IO error.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

RESOLVER_FILE = "platform/common.sh"
ALLOW_BEGIN = "# >>> OC-ONE-PYTHON BEGIN"
ALLOW_END = "# <<< OC-ONE-PYTHON END"

EXCLUDE_DIR_PARTS = {"tests", "test", "fixtures", ".github", "QUALITY-CONTROL", "evidence",
                     "ledgers", "working", "live-run", "node_modules"}
EXCLUDE_PREFIXES = ("scripts/ci/",)
SHELL_EXT = (".sh", ".bash")

_BARE_PIP = re.compile(r"\bpip(?:3(?:\.\d+)?)?\s+(?:install|uninstall)\b")
_PIPX = re.compile(r"\bpipx\s+(?:install|inject)\b")
_PATH_PYTHON = re.compile(
    r"(?<![\w$}/.\-])"
    r"(?:(?:/usr/bin/|/usr/local/bin/|/opt/homebrew/bin/|/bin/)?python(?:3(?:\.\d+)?)?)"
    r"\s+(?:-[A-Za-z]+\s+)*-m\s+pip\b")
_VENV = re.compile(r"(?<![\w-])-m\s+venv\b")
_UV = re.compile(r"\buv\s+(?:venv|pip\s+install|tool\s+install)\b")
_UV_PYTHON = re.compile(r"--python[\s=]+(\S+)")
_LITERAL_PY = re.compile(r"""^["']?(?:python(?:3(?:\.\d+)?)?|/usr/bin/python3?(?:\.\d+)?)["']?$""")
_BSP = re.compile(r"--break-system-packages|PIP_BREAK_SYSTEM_PACKAGES")
_PIP_INSTALL = re.compile(r"\bpip3?\s+install\b|-m\s+pip\s+install\b|\boc_pip_install\b")
_BREW_PY = re.compile(r"linuxbrew[^\s\"']*/bin/python|/opt/homebrew/bin/python|"
                      r"opt/python@3|/usr/local/opt/python|Cellar/python@")


def check_line(line: str) -> list[str]:
    """Rule names violated by one line of shell code (comments already removed)."""
    found = []
    for m in _BARE_PIP.finditer(line):
        before = line[:m.start()]
        if re.search(r"-m\s+$", before) or (before and before[-1] in "/\\.-_"):
            continue
        found.append("BARE_PIP")
        break
    if _PIPX.search(line):
        found.append("PIPX")
    if _PATH_PYTHON.search(line):
        found.append("PATH_PYTHON")
    if _VENV.search(line):
        found.append("VENV")
    if _UV.search(line):
        m = _UV_PYTHON.search(line)
        if not m or _LITERAL_PY.match(m.group(1)) or _BREW_PY.search(m.group(1)):
            found.append("UV_NO_PYTHON")
    if _BSP.search(line) and _PIP_INSTALL.search(line) and "--user" not in line:
        found.append("BSP_NO_USER")
    if _BREW_PY.search(line):
        found.append("BREW_PYTHON")
    return found


def scan_text(rel: str, text: str) -> list[tuple[str, int, str, str]]:
    out = []
    allow = False
    is_resolver = rel.replace(os.sep, "/") == RESOLVER_FILE
    for n, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if is_resolver and stripped.startswith(ALLOW_BEGIN):
            allow = True
            continue
        if is_resolver and stripped.startswith(ALLOW_END):
            allow = False
            continue
        if allow or not stripped or stripped.startswith("#"):
            continue
        for rule in check_line(raw):
            out.append((rel, n, rule, stripped[:160]))
    return out


def in_scope(rel: str) -> bool:
    rel = rel.replace(os.sep, "/")
    if not rel.endswith(SHELL_EXT):
        return False
    if rel.startswith(EXCLUDE_PREFIXES) or "ARCHIVED" in rel:
        return False
    parts = rel.split("/")
    return not any(p in EXCLUDE_DIR_PARTS for p in parts[:-1])


def repo_files(root: str) -> list[str]:
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True,
                             check=True).stdout.decode("utf-8", "replace")
        return [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for d, _dirs, names in os.walk(root):
            if "/.git" in d:
                continue
            files += [os.path.relpath(os.path.join(d, n), root) for n in names]
        return files


def main(argv: list[str]) -> int:
    root = os.environ.get("ONE_PYTHON_GUARD_ROOT") or os.getcwd()
    if argv:
        targets = [(a, a) for a in argv]
    else:
        targets = [(f, os.path.join(root, f)) for f in repo_files(root) if in_scope(f)]
    findings = []
    for rel, path in targets:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("one-python-guard: cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 2
        findings += scan_text(rel, text)
    for rel, n, rule, text in findings:
        print("FAIL %s:%d: %s: %s" % (rel, n, rule, text))
    if findings:
        print("one-python-guard: %d finding(s) in %d file(s). Use the resolver in platform/common.sh "
              "(oc_python / oc_pip_install / oc_venv / oc_uv_tool_install) or "
              "shared-utils/oc-python.sh." % (len(findings), len({f[0] for f in findings})))
        return 1
    print("one-python-guard: PASS (%d shell file(s) scanned)" % len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
