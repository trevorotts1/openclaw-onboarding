#!/usr/bin/env bash
# 53-book-writer/qc-book-writer.sh — CI battery for the Book Writer skill (idempotent).
# ============================================================================
#   * manifest <-> prompts-dir sync (every manifest stage has a prompt_dir path;
#     tone stages 04-08 exist as the baked shared core)
#   * every prover --self-test (via verify.sh)
#   * broken-variants reject + golden PASS (via verify.sh, prose-gated)
#   * verify-deps (zero external services) + anon lint
#   * --repin : recompute source_prompt_pins for the NON-tone prompt triplets and
#     write them into BOOK-WRITER-MANIFEST.json (mechanism; no-op until Wave-1
#     authors the prompts). Tone stages 04-08 are pinned via verify_tone_core_sync.
# Exit 0 = green.
# ============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY="${PYTHON:-python3}"
MODE="${1:-}"

command -v "$PY" >/dev/null 2>&1 || { echo "qc: python3 required" >&2; exit 6; }

if [ "$MODE" = "--repin" ]; then
    echo "== qc --repin :: recomputing source_prompt_pins (non-tone triplets) =="
    SELF_DIR="$SELF_DIR" "$PY" - <<'PY'
import hashlib, json, os, sys
skill = os.environ["SELF_DIR"]
man_path = os.path.join(skill, "BOOK-WRITER-MANIFEST.json")
man = json.load(open(man_path))
tone = {"04-tone-style-1","05-tone-style-2","06-tone-style-3","07-tone-style-4","08-blended-tone"}
pins = {}
pdir = os.path.join(skill, "prompts")
if os.path.isdir(pdir):
    for stage in sorted(os.listdir(pdir)):
        if stage in tone:
            continue
        for f in ("system.md", "methodology.md", "user.md"):
            fp = os.path.join(pdir, stage, f)
            if os.path.isfile(fp):
                rel = os.path.relpath(fp, skill)
                pins[rel] = hashlib.sha256(open(fp,"rb").read()).hexdigest()
man["source_prompt_pins"] = pins
json.dump(man, open(man_path,"w"), indent=2, ensure_ascii=False)
print("repinned %d non-tone prompt file(s)." % len(pins))
if not pins:
    print("WARN: 0 non-tone prompt files pinned — declared prompt dirs under 'prompts/' are absent; repin was a no-op, not a completed pin.", file=sys.stderr)
PY
    exit 0
fi

fails=0
step() { echo "-- $1 --"; shift; if "$@"; then echo "  [PASS]"; else echo "  [FAIL]"; fails=$((fails+1)); fi; }

echo "== Skill 53 (Book Writer) :: qc battery =="

# manifest <-> prompts-dir sync
step "manifest<->prompts sync" "$PY" - "$SELF_DIR" <<'PY'
import json, os, sys
skill = sys.argv[1]
man = json.load(open(os.path.join(skill, "BOOK-WRITER-MANIFEST.json")))
tone = {"04-tone-style-1","05-tone-style-2","06-tone-style-3","07-tone-style-4","08-blended-tone"}
missing = []
for s in man.get("stages", []):
    pd = s.get("prompt_dir", "")
    # tone stages must exist as baked dirs; others may be authored in Wave-1 (advisory)
    stage_id = s.get("stage_id")
    full = os.path.join(skill, pd)
    if stage_id in tone and not os.path.isdir(full):
        missing.append(pd)
if missing:
    print("tone prompt dirs missing:", missing); sys.exit(1)
print("all tone stage prompt dirs present; %d stages declared." % len(man.get("stages", [])))
sys.exit(0)
PY

# the full self-verification gate (self-tests + avatar gate + tone sync + broken-variants + scans + routing)
step "verify.sh" bash "$SELF_DIR/verify.sh"

# avatar prover: golden run-dir PASS + missing-artifact fail-closed reject
step "avatar prover (golden run-dir PASS)" "$PY" "$SELF_DIR/scripts/prove_bw_avatar.py" --run-dir "$SELF_DIR/examples/golden-marcus-halloway/run"
echo "-- avatar prover (missing artifact AUTOFAIL) --"
if "$PY" "$SELF_DIR/scripts/prove_bw_avatar.py" --run-dir "$SELF_DIR/examples/golden-marcus-halloway" >/dev/null 2>&1; then
    echo "  [FAIL] avatar prover PASSED a run dir without the artifact (must fail-closed)"; fails=$((fails+1))
else
    echo "  [PASS]"
fi

# zero external services
step "verify-deps.sh" bash "$SELF_DIR/verify-deps.sh"

echo "=================================================="
if [ "$fails" -eq 0 ]; then echo "QC RESULT: PASS"; exit 0; fi
echo "QC RESULT: FAIL ($fails)"; exit 1
