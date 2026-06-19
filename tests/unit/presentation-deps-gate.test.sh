#!/usr/bin/env bash
# tests/unit/presentation-deps-gate.test.sh
#
# CI guard for the presentation-pipeline runtime dependency fix (deps-fix).
#
# The Skill 23 presentation pipeline needs FOUR runtime deps:
#   - soffice   (LibreOffice / libreoffice-impress) — PPTX -> PDF export
#   - pdftoppm  (poppler / poppler-utils)           — PDF -> PNG for Phase-6 QC
#   - reportlab (Python)                             — presenter-guide PDF
#   - python-pptx (Python module "pptx")            — deck assembly
#
# This test breaks CI if a future edit drops either:
#   (A) install.sh Step 6.5 installing all four deps for BOTH platforms
#       - MAC arm: reportlab + python-pptx (via _install_py_pkg_mac), poppler,
#         and LibreOffice (brew --cask, NONINTERACTIVE).
#       - VPS arm: reportlab + python-pptx (pip --break-system-packages),
#         libreoffice-impress + poppler-utils via the REAL /usr/bin/apt-get
#         (NOT the /usr/local/bin brew shim), re-asserted via `openclaw cron
#         create` (the OpenClaw scheduler), NOT a system @reboot crontab.
#   (B) qc-completeness.sh HARD-FAILING (exit 6, PRESENTATION_DEPS_MISSING) when
#       any of the four deps is missing — verified by actually running the gate
#       with a stubbed PATH. Also asserts it does NOT exit 6 when the bypass var
#       is set, proving the gate is the thing producing the failure.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
QC_SH="$REPO_ROOT/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# Assert a regex matches somewhere in install.sh. ("--" guards -e against
# being parsed as an option when the pattern itself begins with a dash.)
assert_install_has() {
    local label="$1" re="$2"
    if grep -Eq -e "$re" "$INSTALL_SH"; then pass "$label"; else fail "$label (regex: $re)"; fi
}

echo "[presentation-deps-gate] files:"
echo "  install.sh: $INSTALL_SH"
echo "  qc gate:    $QC_SH"

# Both files must exist and be syntactically valid bash.
[ -f "$INSTALL_SH" ] && pass "install.sh present" || fail "install.sh missing"
[ -f "$QC_SH" ] && pass "qc-completeness.sh present" || fail "qc-completeness.sh missing"
bash -n "$INSTALL_SH" 2>/dev/null && pass "install.sh parses (bash -n)" || fail "install.sh bash -n FAILED"
bash -n "$QC_SH" 2>/dev/null && pass "qc-completeness.sh parses (bash -n)" || fail "qc-completeness.sh bash -n FAILED"

echo
echo "(A) install.sh Step 6.5 installs the four deps for BOTH platforms"

# Step 6.5 marker present.
assert_install_has "Step 6.5 block present" 'Step 6\.5: (Installing|Presentation)'

# --- MAC arm: all four deps ---
assert_install_has "MAC: reportlab via _install_py_pkg_mac"   '_install_py_pkg_mac "reportlab"'
assert_install_has "MAC: python-pptx via _install_py_pkg_mac" '_install_py_pkg_mac "python-pptx"'
assert_install_has "MAC: poppler via brew"                    'brew install poppler'
assert_install_has "MAC: LibreOffice via NONINTERACTIVE cask" 'NONINTERACTIVE=1 brew install --cask libreoffice'

# --- VPS arm: all four deps via the REAL apt + pip ---
assert_install_has "VPS: real apt-get path /usr/bin/apt-get"  '_APT_GET="/usr/bin/apt-get"'
assert_install_has "VPS: installs libreoffice-impress + poppler-utils via apt" 'apt.*install.*libreoffice-impress.*poppler-utils|libreoffice-impress poppler-utils'
assert_install_has "VPS: reportlab via pip --break-system-packages" 'pip install --break-system-packages.*reportlab'
assert_install_has "VPS: python-pptx via pip --break-system-packages" 'pip install --break-system-packages.*python-pptx'

# --- VPS durability: OpenClaw scheduler cron, NOT a system @reboot crontab ---
assert_install_has "VPS: re-assert via openclaw cron create" 'openclaw cron create "\$\{BASE\[@\]\}" --message "\$REASSERT_PROMPT"'
assert_install_has "VPS: cron named reassert-presentation-deps" '--name "reassert-presentation-deps"'

# Negative guard: the old fictional durability path piped the reassert script
# into a system @reboot crontab. That must NOT return — durability is now the
# openclaw scheduler. (Scoped to the reassert-presentation-deps context so it
# does not false-match unrelated system crontabs elsewhere in install.sh.)
if grep -Eq -e '@reboot.*reassert-presentation-deps|reassert-presentation-deps.*\| *crontab -|_VPS_REASSERT_CRON' "$INSTALL_SH"; then
    fail "VPS: stale system @reboot crontab path for reassert is back (must use openclaw cron create)"
else
    pass "VPS: no system @reboot crontab path for reassert (uses openclaw scheduler)"
fi
# The old soffice-tarball-into-/data download path must NOT return.
if grep -Eq 'LibreOfficePortable_.*Linux_x86-64_deb\.tar\.gz' "$INSTALL_SH"; then
    fail "VPS: stale LibreOffice tarball-into-/data path is back (removed; use apt)"
else
    pass "VPS: no LibreOffice tarball-into-/data path"
fi

echo
echo "(B) qc-completeness.sh HARD-FAILS (exit 6) when a dep is missing"

# The gate needs python3 to write its JSON output. Build a minimal stub PATH that
# contains the coreutils the gate uses but DELIBERATELY omits soffice + pdftoppm.
STUB_BIN="$TMPDIR_TEST/bin"
mkdir -p "$STUB_BIN"
for b in bash python3 date mkdir dirname tee sed cat printf grep env; do
    src="$(command -v "$b" 2>/dev/null || true)"
    [ -n "$src" ] && ln -sf "$src" "$STUB_BIN/$b"
done

# (b1) soffice + pdftoppm absent -> expect exit 6.
GATE_RC=0
PATH="$STUB_BIN" "$STUB_BIN/bash" "$QC_SH" --quiet > "$TMPDIR_TEST/missing-bins.log" 2>&1 || GATE_RC=$?
if [ "$GATE_RC" -eq 6 ]; then
    pass "gate exits 6 when soffice/pdftoppm missing"
else
    fail "gate did NOT exit 6 with binaries missing (got $GATE_RC)"
    sed -n '1,20p' "$TMPDIR_TEST/missing-bins.log" | sed 's/^/    > /'
fi
if grep -q "PRESENTATION_DEPS_MISSING" "$TMPDIR_TEST/missing-bins.log"; then
    pass "gate logs PRESENTATION_DEPS_MISSING"
else
    fail "gate did not log PRESENTATION_DEPS_MISSING"
fi

# (b2) python import broken -> expect exit 6. Intercept the import-check call with
# a python3 shim and pass everything else through to the real interpreter.
REAL_PY="$(command -v python3)"
PYSHIM_DIR="$TMPDIR_TEST/pyshim"
mkdir -p "$PYSHIM_DIR"
for b in bash date mkdir dirname tee sed cat printf grep env; do
    src="$(command -v "$b" 2>/dev/null || true)"
    [ -n "$src" ] && ln -sf "$src" "$PYSHIM_DIR/$b"
done
# soffice + pdftoppm present so they are NOT the cause of failure.
for b in soffice pdftoppm; do
    src="$(command -v "$b" 2>/dev/null || true)"
    [ -n "$src" ] && ln -sf "$src" "$PYSHIM_DIR/$b"
done
cat > "$PYSHIM_DIR/python3" <<PYSHIM
#!/usr/bin/env bash
if [ "\$1" = "-c" ] && printf '%s' "\$2" | grep -q "import reportlab, pptx"; then exit 1; fi
exec "$REAL_PY" "\$@"
PYSHIM
chmod +x "$PYSHIM_DIR/python3"

# Only meaningful if soffice + pdftoppm actually resolved on this runner.
if [ -e "$PYSHIM_DIR/soffice" ] && [ -e "$PYSHIM_DIR/pdftoppm" ]; then
    GATE_RC=0
    PATH="$PYSHIM_DIR" "$PYSHIM_DIR/bash" "$QC_SH" --quiet > "$TMPDIR_TEST/missing-py.log" 2>&1 || GATE_RC=$?
    if [ "$GATE_RC" -eq 6 ] && grep -q "python(reportlab+python-pptx)" "$TMPDIR_TEST/missing-py.log"; then
        pass "gate exits 6 when reportlab/python-pptx import fails"
    else
        fail "gate did NOT exit 6 on broken python import (got $GATE_RC)"
        sed -n '1,20p' "$TMPDIR_TEST/missing-py.log" | sed 's/^/    > /'
    fi
else
    echo "  SKIP: soffice/pdftoppm not installed on this runner — python-import sub-check skipped"
fi

# (b3) bypass var -> gate must NOT exit 6 (proves the gate is the failure source).
GATE_RC=0
QC_SKIP_PRESENTATION_DEPS=1 PATH="$STUB_BIN" "$STUB_BIN/bash" "$QC_SH" --quiet > "$TMPDIR_TEST/bypass.log" 2>&1 || GATE_RC=$?
if [ "$GATE_RC" -ne 6 ]; then
    pass "gate does NOT exit 6 when QC_SKIP_PRESENTATION_DEPS=1 (got $GATE_RC)"
else
    fail "gate still exited 6 despite QC_SKIP_PRESENTATION_DEPS=1 bypass"
fi

# Static guards on the gate source: the three real checks + exit 6 must be present.
assert_qc_has() {
    local label="$1" re="$2"
    if grep -Eq "$re" "$QC_SH"; then pass "$label"; else fail "$label (regex: $re)"; fi
}
echo
echo "(B-static) qc-completeness.sh contains the real dep checks"
assert_qc_has "gate: command -v soffice check"   'command -v soffice'
assert_qc_has "gate: command -v pdftoppm check"  'command -v pdftoppm'
assert_qc_has "gate: python import reportlab,pptx check" 'import reportlab, pptx'
assert_qc_has "gate: exit 6 on missing dep"      'exit 6'

echo
echo "============================================"
echo "presentation-deps-gate: PASS=$PASS FAIL=$FAIL"
echo "============================================"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
