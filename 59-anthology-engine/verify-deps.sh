#!/usr/bin/env bash
# 59-anthology-engine/verify-deps.sh -- minimal dependency check.
# The engine's gates are stdlib-only Python EXCEPT the output-side font-floor gate
# (scripts/guard-font-floor.py), which HARD-requires PyMuPDF (fitz) to parse the
# rendered PDF -- without it that gate exits 3 (EX_DEP) and the 14pt font floor is
# silently unenforced. So the two hard deps are python3 AND PyMuPDF/fitz.
# Runtime delivery also needs a deterministic HTML-to-PDF renderer (WeasyPrint-class);
# that is checked at install/preflight time on a client box and degrades to a
# named prerequisite, never a crash. Exit 0 = ok, nonzero = a hard dep missing.
set -uo pipefail
missing=0
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 ($(python3 --version 2>&1))"
else
    echo "  MISSING: python3 (required)"; missing=1
fi
if command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1; then
    echo "  OK: a sha256 tool is present (the entry hash-pin gate is active)"
else
    echo "  NOTE: no sha256 tool -- the entry hash-pin gate is skipped (non-fatal)"
fi
if python3 -c "import fitz" >/dev/null 2>&1; then
    echo "  OK: PyMuPDF (fitz) is importable ($(python3 -c 'import fitz,sys; sys.stdout.write(getattr(fitz,"__doc__","") or "")' 2>/dev/null | head -1)) -- the output-side font-floor gate is active"
else
    echo "  MISSING: PyMuPDF/fitz (required) -- scripts/guard-font-floor.py cannot inspect the rendered PDF, so the 14pt font-floor gate would be SILENTLY DEAD. Fix: python3 -m pip install --user --break-system-packages PyMuPDF"; missing=1
fi
if python3 -c "import weasyprint" >/dev/null 2>&1; then
    echo "  OK: a WeasyPrint-class HTML-to-PDF renderer is importable (runtime delivery ready)"
else
    echo "  NOTE: no WeasyPrint-class renderer importable -- pdf_render.py names it as a prerequisite at install (non-fatal here)"
fi
if [ "$missing" -eq 0 ]; then
    echo "verify-deps: PASS"; exit 0
fi
echo "verify-deps: FAIL -- install the missing hard dep(s) named above (python3 and/or PyMuPDF/fitz)"; exit 1
