#!/usr/bin/env bash
# 59-anthology-engine/verify-deps.sh -- minimal dependency check.
# The engine's gates are stdlib-only Python EXCEPT the output-side font-floor gate
# (scripts/guard-font-floor.py), which HARD-requires PyMuPDF (fitz) to parse the
# rendered PDF -- without it that gate exits 3 (EX_DEP) and the 14pt font floor is
# silently unenforced. So the three hard deps are python3, PyMuPDF/fitz AND pytest.
# pytest is a HARD dep because the shipped tooling CLIs' OFFLINE --self-test
# batteries are pytest batteries: every one of the ten assemblers imports its
# u0N_modules/test_*.py modules, which `import pytest` at module scope. Without
# pytest those self-tests raise ModuleNotFoundError and verify.sh reports DRIFT
# (exit 4) on a perfectly healthy tree -- so it is named HERE, at dependency
# time, instead of surfacing later as an opaque verify failure.
# Runtime delivery also needs a deterministic HTML-to-PDF renderer (WeasyPrint-class);
# that is checked at install/preflight time on a client box and degrades to a
# named prerequisite, never a crash. Exit 0 = ok, nonzero = a hard dep missing.
set -uo pipefail  # Intentional: no -e; exit codes handled explicitly per house contract (ENGINE-MANIFEST.json rows 30-32)
missing=0
# ONE-PYTHON (v27.1.80): check the box's ONE canonical interpreter (oc_python,
# platform/common.sh) -- the one install.sh installs into and the gateway runs
# on a Linux box -- not whatever python3 a `docker exec` PATH lists first. When
# the resolver is not delivered next to this skill, python3 from PATH is checked.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY=""
for _c in "$SELF_DIR/../platform/common.sh" "$SELF_DIR/../../platform/common.sh" \
          "${OPENCLAW_ROOT:-/nonexistent}/platform/common.sh"; do
    # shellcheck source=/dev/null
    if [ -f "$_c" ]; then . "$_c"; PY="$(oc_python 2>/dev/null || true)"; break; fi
done
[ -n "$PY" ] || PY="$(command -v python3 2>/dev/null || true)"
if [ -n "$PY" ]; then
    echo "  OK: python3 $PY ($("$PY" --version 2>&1))"
else
    echo "  MISSING: python3 (required)"; missing=1; PY=python3
fi
if command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1; then
    echo "  OK: a sha256 tool is present (the entry hash-pin gate is active)"
else
    echo "  NOTE: no sha256 tool -- the entry hash-pin gate is skipped (non-fatal)"
fi
if "$PY" -c "import pytest" >/dev/null 2>&1; then
    echo "  OK: pytest is importable ($("$PY" -c 'import pytest,sys; sys.stdout.write(pytest.__version__)' 2>/dev/null)) -- the shipped CLIs' pytest self-test batteries can run"
else
    echo "  MISSING: pytest (required) -- the ten tooling CLIs' --self-test batteries import pytest, so every one of them would FAIL and verify.sh would report DRIFT on a healthy tree. Fix: bash <root>/skills/shared-utils/oc-python.sh pip-install pytest"; missing=1
fi
if "$PY" -c "import fitz" >/dev/null 2>&1; then
    echo "  OK: PyMuPDF (fitz) is importable ($("$PY" -c 'import fitz,sys; sys.stdout.write(getattr(fitz,"__doc__","") or "")' 2>/dev/null | head -1)) -- the output-side font-floor gate is active"
else
    echo "  MISSING: PyMuPDF/fitz (required) -- scripts/guard-font-floor.py cannot inspect the rendered PDF, so the 14pt font-floor gate would be SILENTLY DEAD. Fix: bash <root>/skills/shared-utils/oc-python.sh pip-install PyMuPDF"; missing=1
fi
if "$PY" -c "import weasyprint" >/dev/null 2>&1; then
    echo "  OK: a WeasyPrint-class HTML-to-PDF renderer is importable (runtime delivery ready)"
else
    echo "  NOTE: no WeasyPrint-class renderer importable -- pdf_render.py names it as a prerequisite at install (non-fatal here)"
fi
if [ "$missing" -eq 0 ]; then
    echo "verify-deps: PASS"; exit 0
fi
echo "verify-deps: FAIL -- install the missing hard dep(s) named above (python3 and/or PyMuPDF/fitz and/or pytest)"; exit 1
