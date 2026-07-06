#!/usr/bin/env bash
# tests/unit/phase6-categories-fail-loud.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Hermetic tests for the F1.4 (DEP-12) Phase-6 categories FAIL-LOUD + AUTO-REPAIR
# contract in 22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py.
#
# The invariant (QC): every persona present as a blueprint dir in a finished run
# is EITHER a persona-categories.json key (registered/selectable) OR produced a
# non-zero exit — never a silent success with no categories entry.
#
# Cases:
#   1  happy path                 -> outcome "ok", registered w/ real tags, no needs_retag,
#                                    NO fail-loud recorded, exit gate is a no-op.
#   2  lint failure (auto-repair) -> normal append raises PersonaCategoriesSchemaError;
#                                    entry re-registered with SAFE-DEFAULT domain
#                                    ["leadership"] + needs_retag:true (never-to-zero),
#                                    folder recorded for the fail-loud exit.
#   3  fail-loud exit             -> after case 2, _exit_if_categories_failed() raises
#                                    SystemExit(9) (PHASE6_CATEGORIES_EXIT_CODE).
#   4  hard fail (repair fails)   -> both normal AND safe-default writes raise ->
#                                    outcome "failed", folder still recorded (exit 9);
#                                    the persona is NOT a categories key (loud, not silent).
#   5  never-to-zero visibility   -> after auto-repair the folder IS a key under
#                                    .personas (what list_available_personas() reads).
#   6  multi-book aggregation     -> the module-level accumulator collects >1 failing
#                                    folder across calls (async batch gather semantics).
#
# No network, no Gemini key, no aiohttp path exercised (functions imported directly).
# Real $HOME is preserved so aiohttp/idna user-site deps resolve; sandbox paths are
# injected by monkeypatching orchestrator module globals AFTER import.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
ORCH="$SKILL/pipeline/orchestrator.py"

[ -f "$ORCH" ] || { echo "FATAL: missing $ORCH"; exit 2; }

SB="$(mktemp -d -t p6-faillloud.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

PIPELINE_DIR="$SKILL/pipeline" SB="$SB" python3 - <<'PY'
import os, sys, json, importlib

sys.path.insert(0, os.environ["PIPELINE_DIR"])
SB = os.environ["SB"]

import orchestrator as o
from pathlib import Path

# ── Inject sandbox paths (avoid touching the real workspace / real seed). ──────
personas_dir = Path(SB) / "personas"
personas_dir.mkdir(parents=True, exist_ok=True)
catpath = Path(SB) / "persona-categories.json"
o.PERSONAS_DIR = personas_dir
o._persona_categories_path = lambda: catpath
# Redirect the module's log + status files into the sandbox so the test never
# writes to the real operator workspace (BASE resolves to ~/.openclaw/... on a
# dev box).
o.LOG_FILE = Path(SB) / "pipeline-log.txt"
o.STATUS_FILE = Path(SB) / "pipeline-status.json"

def seed_categories():
    catpath.write_text(json.dumps({
        "schemaVersion": "1.2",
        "domainTags": ["leadership", "coaching", "marketing"],
        "perspectiveTags": ["mens-challenges", "womens-challenges"],
        "personas": {},
    }, indent=2))

def mk_blueprint(folder, body="leadership leadership coaching"):
    d = personas_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "persona-blueprint.md").write_text(f"# {folder}\n\n{body}\n")

def read_cats():
    return json.loads(catpath.read_text())

PASS = 0; FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond:
        print("  PASS:", msg); PASS += 1
    else:
        print("  FAIL:", msg); FAIL += 1

_ORIG_AUTOCLASSIFY = o._auto_classify_persona_tags
_ORIG_APPEND = o._append_persona_to_categories

def reset():
    o._CATEGORIES_WRITE_FAILURES.clear()
    o._auto_classify_persona_tags = _ORIG_AUTOCLASSIFY
    o._append_persona_to_categories = _ORIG_APPEND
    seed_categories()

book = {"author": "Test Author", "title": "Test Book"}

# ── Case 1: happy path ────────────────────────────────────────────────────────
print("── Case 1: happy path (normal auto-classified registration) ──")
reset(); mk_blueprint("case1-ok")
outcome = o._phase6_register_categories(book, "case1-ok", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case1-ok")
check(outcome == "ok", f"outcome == 'ok' (got {outcome!r})")
check(entry is not None, "case1-ok is a categories key (registered)")
check(bool(entry and entry.get("domain")), "domain[] non-empty")
check(entry is not None and "needs_retag" not in entry, "no needs_retag marker on a clean write")
check(o.pipeline_had_categories_failures() is False, "no fail-loud recorded on happy path")

# ── Case 2: lint failure -> auto-repair with safe defaults ────────────────────
print("── Case 2: schema-lint failure -> auto-repair (safe default + needs_retag) ──")
reset(); mk_blueprint("case2-repair")
# Force the NORMAL path to fail the schema-lint gate with a malformed tag.
o._auto_classify_persona_tags = lambda *a, **k: (["Bad Tag!"], [])
outcome = o._phase6_register_categories(book, "case2-repair", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case2-repair")
check(outcome == "repaired", f"outcome == 'repaired' (got {outcome!r})")
check(entry is not None, "case2-repair IS registered (never-to-zero, not skipped)")
check(entry is not None and entry.get("domain") == ["leadership"],
      f"safe-default domain == ['leadership'] (got {entry and entry.get('domain')})")
check(entry is not None and entry.get("perspective") == [], "safe-default perspective == []")
check(entry is not None and entry.get("needs_retag") is True, "needs_retag:true marker present")
check("case2-repair" in o._CATEGORIES_WRITE_FAILURES, "folder recorded for fail-loud exit")
check(o.pipeline_had_categories_failures() is True, "pipeline_had_categories_failures() True after repair")
# safe-default domain must be a controlled-vocab member (publish-safe).
check("leadership" in cats.get("domainTags", []), "safe-default domain is controlled-vocab (publishable)")

# ── Case 3: fail-loud exit code 9 ─────────────────────────────────────────────
print("── Case 3: fail-loud exit -> SystemExit(9) ──")
# accumulator still holds case2-repair from Case 2.
raised = None
try:
    o._exit_if_categories_failed()
except SystemExit as e:
    raised = e.code
check(raised == o.PHASE6_CATEGORIES_EXIT_CODE == 9,
      f"_exit_if_categories_failed raises SystemExit({o.PHASE6_CATEGORIES_EXIT_CODE}) (got {raised!r})")

# ── Case 3b: exit gate is a no-op when there were no failures ─────────────────
reset()
noraise = "did-not-exit"
try:
    o._exit_if_categories_failed()
except SystemExit as e:
    noraise = e.code
check(noraise == "did-not-exit", "exit gate is a no-op on a clean run")

# ── Case 4: hard fail (auto-repair itself fails) ──────────────────────────────
print("── Case 4: normal AND safe-default writes fail -> outcome 'failed', still loud ──")
reset(); mk_blueprint("case4-hardfail")
def _always_raise(*a, **k):
    raise OSError("simulated unwritable persona-categories.json")
o._append_persona_to_categories = _always_raise
outcome = o._phase6_register_categories(book, "case4-hardfail", appendix_status="COMPLETE")
cats = read_cats()
check(outcome == "failed", f"outcome == 'failed' when both writes raise (got {outcome!r})")
check("case4-hardfail" in o._CATEGORIES_WRITE_FAILURES, "folder recorded even on hard fail (fail-loud, not silent)")
check("case4-hardfail" not in cats["personas"], "hard fail leaves NO categories key (loud, never silently 'ok')")

# ── Case 5: never-to-zero visibility (selector universe) ──────────────────────
print("── Case 5: after auto-repair the folder IS in list_available_personas() universe ──")
reset(); mk_blueprint("case5-visible")
o._auto_classify_persona_tags = lambda *a, **k: (["Bad Tag!"], [])
o._phase6_register_categories(book, "case5-visible", appendix_status="COMPLETE")
cats = read_cats()
# list_available_personas() returns list(data["personas"].keys()).
universe = list(cats.get("personas", {}).keys())
check("case5-visible" in universe, "repaired persona is visible to the selector universe (never invisible)")

# ── Case 6: multi-book aggregation across calls ───────────────────────────────
print("── Case 6: module-level accumulator aggregates >1 failing folder ──")
reset()
o._auto_classify_persona_tags = lambda *a, **k: (["Bad Tag!"], [])
for slug in ("case6-a", "case6-b", "case6-c"):
    mk_blueprint(slug)
    o._phase6_register_categories(book, slug, appendix_status="COMPLETE")
check(set(o._CATEGORIES_WRITE_FAILURES) == {"case6-a", "case6-b", "case6-c"},
      f"all 3 failing folders aggregated (got {o._CATEGORIES_WRITE_FAILURES})")
raised6 = None
try:
    o._exit_if_categories_failed()
except SystemExit as e:
    raised6 = e.code
check(raised6 == 9, "fail-loud exit fires once for the aggregated batch")

print(f"\n{'='*60}")
print(f"phase6-categories-fail-loud: PASS={PASS} FAIL={FAIL}")
print(f"{'='*60}")
sys.exit(1 if FAIL else 0)
PY
rc=$?
if [ "$rc" -eq 0 ]; then
    echo "ALL PHASE-6 FAIL-LOUD TESTS PASSED"
else
    echo "PHASE-6 FAIL-LOUD TESTS FAILED (rc=$rc)"
fi
exit "$rc"
