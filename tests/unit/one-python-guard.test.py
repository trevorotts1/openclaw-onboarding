#!/usr/bin/env python3
"""tests/unit/one-python-guard.test.py: scripts/ci/one-python-guard.py discriminates.

Every forbidden pattern is caught (one fixture line each), the compliant
rewrite of the same line passes, comments are ignored, the allowlist covers ONLY
the resolver block in platform/common.sh (the same line one line outside the
block fails), the path scope excludes tests/CI, and the real repo is clean.
Run: python3 tests/unit/one-python-guard.test.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUARD = os.path.join(REPO, "scripts", "ci", "one-python-guard.py")
spec = importlib.util.spec_from_file_location("one_python_guard", GUARD)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

FAILS = []
PASSES = 0


def check(name, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
        print("  PASS: " + name)
    else:
        FAILS.append(name)
        print("  FAIL: %s %s" % (name, detail))


# (rule, forbidden line, compliant rewrite)
CASES = [
    ("BARE_PIP", 'pip install requests', 'oc_pip_install requests'),
    ("BARE_PIP", 'pip3 install --user yt-dlp', 'oc_pip_install yt-dlp'),
    ("BARE_PIP", 'echo "Fix: pip3 install weasyprint"', 'echo "Fix: bash ~/.openclaw/skills/shared-utils/oc-python.sh pip-install weasyprint"'),
    ("PIPX", 'pipx install whisper-ctranslate2', 'oc_uv_tool_install whisper-ctranslate2'),
    ("PIPX", 'pipx inject skill22-shared "$pkg"', 'oc_pip_install "$pkg"'),
    ("PATH_PYTHON", 'python3 -m pip install --user google-genai', 'oc_pip_install google-genai'),
    ("PATH_PYTHON", 'python -m pip install x', '"$VENV_DIR/bin/python" -m pip install x'),
    ("PATH_PYTHON", 'python3.13 -m pip install x', '"$(oc_python)" -m pip --version'),
    ("PATH_PYTHON", '/usr/bin/python3 -m pip install x', '"$_py" -m pip install --target "$_dir" x'),
    ("VENV", 'python3 -m venv "$VENV_DIR"', 'oc_venv "$VENV_DIR"'),
    ("VENV", '"$PY" -m venv "$VENV_DIR"', 'oc_venv "$VENV_DIR"'),
    ("UV_NO_PYTHON", 'uv venv "$DIR"', 'uv venv --python "$(oc_python)" --seed "$DIR"'),
    ("UV_NO_PYTHON", 'uv pip install "$pkg"', 'oc_pip_install "$pkg"'),
    ("UV_NO_PYTHON", 'uv tool install whisper-ctranslate2', 'oc_uv_tool_install whisper-ctranslate2'),
    ("UV_NO_PYTHON", 'uv tool install --python python3 whisper-ctranslate2', 'uv tool install --python "$PY" whisper-ctranslate2'),
    ("BSP_NO_USER", '"$_py" -m pip install --break-system-packages mediapipe', '"$_py" -m pip install --user --break-system-packages mediapipe'),
    ("BSP_NO_USER", 'PIP_BREAK_SYSTEM_PACKAGES=1 "$py" -m pip install x', 'PIP_BREAK_SYSTEM_PACKAGES=1 "$py" -m pip install --user x'),
    ("BREW_PYTHON", '/data/linuxbrew/.linuxbrew/bin/python3 -c "import x"', '"$(oc_python)" -c "import x"'),
    ("BREW_PYTHON", 'PY=/opt/homebrew/bin/python3', 'PY="$(oc_python)"'),
    ("BREW_PYTHON", 'home=/data/linuxbrew/.linuxbrew/opt/python@3.14/bin', 'home=/usr/bin'),
]


def run_cases():
    for rule, bad_line, good_line in CASES:
        got = G.check_line(bad_line)
        check("%s caught: %s" % (rule, bad_line), rule in got, repr(got))
        got = G.check_line(good_line)
        check("compliant passes: %s" % good_line, got == [], repr(got))


def run_scope_and_allowlist():
    check("comment lines ignored", G.scan_text("x.sh", "# python3 -m venv x\n  # pip install y\n") == [])
    check("prose without a pip install line is not BSP", G.check_line(
        'echo "never --break-system-packages, never a venv"') == [])
    block = ("#!/usr/bin/env bash\n" + G.ALLOW_BEGIN + " (vX)\n"
             '"$py" -m venv "$dir"\n' + G.ALLOW_END + "\n")
    check("resolver block in platform/common.sh is allowlisted",
          G.scan_text("platform/common.sh", block) == [])
    outside = block + '"$py" -m venv "$dir"\n'
    got = G.scan_text("platform/common.sh", outside)
    check("same line OUTSIDE the resolver block fails", [r for _f, _n, r, _t in got] == ["VENV"], repr(got))
    check("the allowlist is file-specific (block markers in another file do not exempt it)",
          [r for _f, _n, r, _t in G.scan_text("lib-shared.sh", block)] == ["VENV"])
    for path, want in [("install.sh", True), ("25-video-creator/wire.sh", True),
                       ("shared-utils/lipsync-deps.sh", True), ("tests/unit/x.test.sh", False),
                       ("scripts/ci/fast-guards.d/x.sh", False), ("44-x/tests/test_qc_gate.sh", False),
                       ("scripts/test-prereqs-schema-enforcement.sh", True),
                       ("23-x/scripts/test-wiring-gate.sh", True), ("README.md", False)]:
        check("scope %s -> %s" % (path, want), G.in_scope(path) is want)


def run_cli():
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "bad.sh")
        good = os.path.join(td, "good.sh")
        with open(bad, "w") as fh:
            fh.write("#!/usr/bin/env bash\npython3 -m pip install --user x\n")
        with open(good, "w") as fh:
            fh.write('#!/usr/bin/env bash\n"$(oc_python)" -m pip --version\n')
        r = subprocess.run([sys.executable, GUARD, bad], capture_output=True, text=True)
        check("CLI exits 1 on a violation", r.returncode == 1 and "PATH_PYTHON" in r.stdout, r.stdout)
        r = subprocess.run([sys.executable, GUARD, good], capture_output=True, text=True)
        check("CLI exits 0 on compliant code", r.returncode == 0, r.stdout)
    r = subprocess.run([sys.executable, GUARD], capture_output=True, text=True, cwd=REPO)
    check("the whole repo passes the guard", r.returncode == 0, r.stdout[-2000:])


if __name__ == "__main__":
    run_cases()
    run_scope_and_allowlist()
    run_cli()
    print("\none-python-guard tests: %d passed, %d failed" % (PASSES, len(FAILS)))
    sys.exit(1 if FAILS else 0)
