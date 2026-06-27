#!/usr/bin/env bash
# tests/unit/section-tagger-indexer-agreement.test.sh
#
# Proves the FLEET section tagger (23-ai-workforce-blueprint/scripts/section-tag-migration.py)
# and the indexer (23-ai-workforce-blueprint/scripts/gemini-section-indexer.py) agree on the
# persona-blueprint section -> mode mapping, and that both derive it from the single source
# of truth in shared-utils/embedding_engine.py. This is the guard against the historical
# drift where the indexer hardcoded COACHING_SECTIONS={6} while the live tagger used
# Section 3 = coaching / Section 4 = leadership.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$REPO_ROOT" << 'PY'
import importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "shared-utils"))

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, root / rel)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

import embedding_engine as E
gsi = load("gsi", "23-ai-workforce-blueprint/scripts/gemini-section-indexer.py")
stm = load("stm", "23-ai-workforce-blueprint/scripts/section-tag-migration.py")

# 1) constants: single source of truth, no hardcoded drift
assert E.LEADERSHIP_SECTION_NUMBER == 4, E.LEADERSHIP_SECTION_NUMBER
assert E.COACHING_SECTION_NUMBER == 3, E.COACHING_SECTION_NUMBER
assert gsi.LEADERSHIP_SECTIONS == {E.LEADERSHIP_SECTION_NUMBER} == {stm.LEADERSHIP_SECTION} == {4}, \
    (gsi.LEADERSHIP_SECTIONS, stm.LEADERSHIP_SECTION)
assert gsi.COACHING_SECTIONS == {E.COACHING_SECTION_NUMBER} == {stm.COACHING_SECTION} == {3}, \
    (gsi.COACHING_SECTIONS, stm.COACHING_SECTION)

# 2) behaviour: identical mode for every section number (no name-keyword influence)
def tagger_mode(sec):
    return ("leadership" if sec == stm.LEADERSHIP_SECTION
            else "coaching" if sec == stm.COACHING_SECTION else "both")
for n in range(0, 12):
    a, b = gsi.get_section_mode(n, ""), tagger_mode(n)
    assert a == b, f"section {n}: indexer={a} tagger={b}"

# 3) the specific regression: Section 6 must NOT be coaching
assert gsi.get_section_mode(6, "") == "both", "Section 6 wrongly tagged coaching (the {6} bug)"
assert gsi.get_section_mode(3, "") == "coaching"
assert gsi.get_section_mode(4, "") == "leadership"
print("OK section tagger and indexer AGREE (coaching=Section3, leadership=Section4); Section6=both")
PY
rc=$?
if [ $rc -eq 0 ]; then
    echo "  PASS: section-tagger / indexer agreement"
    exit 0
else
    echo "  FAIL: section-tagger / indexer disagree"
    exit 1
fi
