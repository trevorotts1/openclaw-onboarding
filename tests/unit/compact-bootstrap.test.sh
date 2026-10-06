#!/usr/bin/env bash
# compact-bootstrap.test.sh — the properties the compact-core procedure must hold.
#
# Each test states the DEFECT it exists to catch. The tool moves OWNER-AUTHORED
# text out of files that are re-billed to the model on every turn, so a bug here
# does not cost tokens, it loses the owner's words or silently disarms a rule
# that was supposed to fire every turn.
#
# Companion suite: bootstrap-pointerize.test.sh covers the ROLL's side of the
# same contract (managed blocks stamped as pointers). Both tools must write the
# SAME pointer shape, and T7 below proves this one does not fork it.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE="$REPO/scripts/compact-bootstrap.py"
POINTERIZE="$REPO/scripts/bootstrap-pointerize.py"
VALIDATOR="$REPO/scripts/validate-core-references.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  ✓ PASS — $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ FAIL — $1"; }

echo "═══ compact-bootstrap — compact core, verbatim or nothing ═══"

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 2; }
for f in "$ENGINE" "$POINTERIZE" "$VALIDATOR"; do
  [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

WS="$TMP/ws"
REF="$TMP/ref"
# A small lean target so a small fixture is genuinely over budget. The budget
# override is the validator's own, so the tool and the daily check cannot
# disagree about what "over" means.
BUDGET=(--budget AGENTS.md=2000)

_fixture() {
  rm -rf "$WS" "$REF"
  mkdir -p "$WS" "$REF"
  python3 - "$WS" <<'PYEOF'
import os, sys
ws = sys.argv[1]
filler = "\n".join(
    "Line %d of procedural detail that only matters once you are already doing this job." % i
    for i in range(1, 40))
agents = """# Bootstrap

<!-- CORE_REFERENCE_POLICY_V1 -->

## PRIME DIRECTIVE
You are the agent. This fires on every single turn and must never be moved out.
%s

<!-- BEGIN skill:99-demo:agents -->
## Managed demo block
Stamped into this file by a fleet script and re-injected in full on the next roll.
%s
<!-- END skill:99-demo:agents -->

## Zoom meeting automation
How to create, list and delete meetings, which credential each call needs, and the
retry rule for a 429.
%s
""" % (filler, filler, filler)
with open(os.path.join(ws, "AGENTS.md"), "w") as fh:
    fh.write(agents)
for name in ("TOOLS.md", "MEMORY.md", "USER.md", "SOUL.md", "IDENTITY.md"):
    with open(os.path.join(ws, name), "w") as fh:
        fh.write("# %s\n\n<!-- CORE_REFERENCE_POLICY_V1 -->\n\nshort.\n" % name)
PYEOF
}

_run() { python3 "$ENGINE" --workspace "$WS" --references "$REF" "${BUDGET[@]}" "$@"; }

# ── T1: VERBATIM OR NOTHING — the moved bytes land unchanged, behind a pointer ─
# DEFECT: a "compaction" that paraphrases, tightens or merges is a rewrite of the
# owner's words wearing a maintenance job's clothes.
_fixture
BEFORE=$(wc -c < "$WS/AGENTS.md")
_run --apply >"$TMP/apply1.txt" 2>&1
AFTER=$(wc -c < "$WS/AGENTS.md")
DEST="$REF/zoom-meeting-automation.md"
if [ "$AFTER" -lt "$BEFORE" ] && [ -f "$DEST" ] &&
   grep -q 'Line 1 of procedural detail' "$DEST" &&
   grep -q 'Line 39 of procedural detail' "$DEST" &&
   grep -q 'retry rule for a 429' "$DEST"; then
  pass "a cold section moves out verbatim and the file shrinks ($BEFORE -> $AFTER bytes)"
else
  fail "content was not moved verbatim ($BEFORE -> $AFTER bytes); see $TMP/apply1.txt"
fi

# The pointer left behind must name an ABSOLUTE path that EXISTS. A pointer to a
# file that is not there is worse than the bloat it replaced.
PTR_PATH="$(grep -m1 -o '\*\*Full text:\*\* [^ ]*' "$WS/AGENTS.md" | awk '{print $3}')"
if [ -n "$PTR_PATH" ] && [ "${PTR_PATH#/}" != "$PTR_PATH" ] && [ -f "$PTR_PATH" ]; then
  pass "the pointer names an absolute path that exists"
else
  fail "pointer target is relative or missing: ${PTR_PATH:-<none>}"
fi

# The ledger is the proof. Its sha256 must be recomputable from the destination.
LEDGER="$REF/migration-map.json"
if [ -f "$LEDGER" ] && python3 - "$LEDGER" "$REF" <<'PYEOF'
import hashlib, json, os, re, sys
entries = json.load(open(sys.argv[1]))
root = sys.argv[2]
assert entries, "ledger is empty"
for e in entries:
    rel, anchor = e["destination"].split("#", 1)
    text = open(os.path.join(root, rel)).read()
    key = '<a id="%s"></a>\n' % anchor
    end = "<!-- end-block %s -->" % anchor
    i = text.index(key) + len(key)
    block = text[i:text.index(end, i)]
    assert hashlib.sha256(block.encode()).hexdigest() == e["sha256"], e["destination"]
    for field in ("workspace", "class", "migrated_utc", "start_line", "end_line", "heading"):
        assert field in e, field
PYEOF
then
  pass "every ledger entry's sha256 recomputes from the block in the reference doc"
else
  fail "a ledgered sha256 does not match the block it points at"
fi

# ── T2: IDEMPOTENCY — a second run is a byte-for-byte no-op ──────────────────
# DEFECT: a weekly job that re-moves what it already moved appends a duplicate
# block on every run and grows the reference corpus forever.
cp "$WS/AGENTS.md" "$TMP/after1.md"
cp "$DEST" "$TMP/dest1.md"
_run --apply >"$TMP/apply2.txt" 2>&1
if cmp -s "$TMP/after1.md" "$WS/AGENTS.md" && cmp -s "$TMP/dest1.md" "$DEST"; then
  pass "second run is a byte-identical no-op in both the bootstrap file and the reference"
else
  fail "second run changed a file — the move is not idempotent"
fi

# ── T3: SCRIPT-OWNED IS REFUSED ─────────────────────────────────────────────
# DEFECT: moving a block a fleet script stamps buys nothing — the next roll
# re-appends the full text — and deleting its marker breaks every idempotency
# guard that keys on the pair.
# NOTE the BODY, not the heading, and NOT under previous/. The heading
# legitimately appears in pending-updates.md, where the proposal LISTS
# script-owned bulk for the owner, and the whole pre-move file legitimately
# appears under previous/, which is the rollback copy. Listing it and backing it
# up are both correct; FILING its text as a reference block is the defect.
if grep -q '<!-- BEGIN skill:99-demo:agents -->' "$WS/AGENTS.md" &&
   grep -q '<!-- END skill:99-demo:agents -->' "$WS/AGENTS.md" &&
   grep -q 'Stamped into this file by a fleet script' "$WS/AGENTS.md" &&
   ! grep -rq --exclude-dir=previous 'Stamped into this file by a fleet script' "$REF"; then
  pass "a script-owned block is refused: marker pair and body stay inline, nothing moved"
else
  fail "a script-owned block was moved or its marker pair was damaged"
fi

# ROLLBACK — an untracked bootstrap file is backed up before it is touched, and
# the backup is the WHOLE pre-move file, so one cp undoes the run.
BACKUP="$(ls "$REF/previous"/AGENTS-*.md 2>/dev/null | head -1)"
if [ -n "$BACKUP" ] && grep -q 'Line 39 of procedural detail' "$BACKUP" &&
   grep -q '## Zoom meeting automation' "$BACKUP"; then
  pass "an untracked bootstrap file is backed up whole before the first move"
else
  fail "no usable rollback copy was written to previous/"
fi

# The decision table must SAY so, with a reason — a silent skip is unreviewable.
if grep -q 'script .*Managed demo block' "$TMP/apply1.txt" ||
   grep -qE 'script +[0-9]+ +Managed demo block' "$TMP/apply1.txt"; then
  pass "the report records the script class and its reason for that block"
else
  fail "the report did not classify the managed block as script-owned"
fi

# ── T4: A HOT SECTION BECOMES A PROPOSAL, NEVER A MOVE ──────────────────────
# DEFECT: a rule that fires every turn, moved behind a pointer, stops firing.
# Size is the trigger for compaction, never the authority to disarm a reflex.
if grep -q '^## PRIME DIRECTIVE' "$WS/AGENTS.md" &&
   grep -q 'This fires on every single turn' "$WS/AGENTS.md" &&
   [ -f "$REF/pending-updates.md" ] &&
   grep -q 'still over its lean target' "$REF/pending-updates.md" &&
   grep -q 'PRIME DIRECTIVE' "$REF/pending-updates.md"; then
  pass "an over-target file leaves hot content inline and writes a proposal instead"
else
  fail "a hot section was moved, or no proposal was written for the remainder"
fi

if grep -q 'bootstrap-pointerize.py' "$REF/pending-updates.md"; then
  pass "the proposal names where script-owned bulk is actually fixed (the roll's stamper)"
else
  fail "the proposal does not say script-owned bulk is fixed at the source"
fi

# ── T5: --check CATCHES A BROKEN ANCHOR AND A CHANGED HASH ──────────────────
# DEFECT: a negative result nobody can trust. The control below proves the check
# can return ok on a healthy tree, so a FAIL is a fact about the tree and not a
# broken instrument.
cp "$DEST" "$TMP/dest-good.md"
if _run --check >/dev/null 2>&1; then
  pass "CONTROL: --check returns ok on a healthy tree (the instrument works)"
else
  fail "CONTROL: --check failed on a healthy tree — every FAIL below is meaningless"
fi

python3 - "$DEST" <<'PYEOF'
import re, sys
p = sys.argv[1]
t = open(p).read()
open(p, "w").write(re.sub(r'<a id="[^"]+"></a>\n', "", t, count=1))
PYEOF
if _run --check >"$TMP/check-anchor.txt" 2>&1; then
  fail "--check passed with the anchor removed from the target doc"
else
  if grep -q 'anchor not in target' "$TMP/check-anchor.txt"; then
    pass "--check catches a pointer whose anchor is no longer in the target doc"
  else
    fail "--check failed but not for the anchor reason (see $TMP/check-anchor.txt)"
  fi
fi

cp "$TMP/dest-good.md" "$DEST"
python3 - "$DEST" <<'PYEOF'
import sys
p = sys.argv[1]
t = open(p).read().replace("Line 12 of procedural detail", "Line 12 of TAMPERED detail")
open(p, "w").write(t)
PYEOF
if _run --check >"$TMP/check-hash.txt" 2>&1; then
  fail "--check passed after the stored block was edited — the sha256 gate is dead"
else
  if grep -q 'sha256 drift' "$TMP/check-hash.txt"; then
    pass "--check catches a stored block edited after the move (sha256 drift)"
  else
    fail "--check failed but not for the sha256 reason (see $TMP/check-hash.txt)"
  fi
fi
cp "$TMP/dest-good.md" "$DEST"

# ── T6: WORKSPACES ARE DEDUPED BY RESOLVED REAL PATH ────────────────────────
# DEFECT (fleet-wide, every Mac client box): ~/clawd is a SYMLINK to
# ~/.openclaw/workspace. Treating the two as separate workspaces compacts the
# same file twice in one run, double-writes the ledger, and stamps the second
# pointer over the first.
LINKROOT="$TMP/link"
mkdir -p "$LINKROOT/.openclaw/workspace"
ln -s "$LINKROOT/.openclaw/workspace" "$LINKROOT/clawd"
cat > "$TMP/link-config.json" <<EOF
{"agents":{"defaults":{"workspace":"$LINKROOT/clawd"},
 "entries":{"main":{"workspace":"$LINKROOT/clawd"},
            "dept":{"workspace":"$LINKROOT/.openclaw/workspace"}}}}
EOF
COUNT=$(python3 "$ENGINE" --from-config "$TMP/link-config.json" --list-workspaces 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" = "1" ]; then
  pass "a symlinked workspace and its target resolve to ONE workspace, not two"
else
  fail "workspace dedupe returned $COUNT entries for one real directory"
fi

# Two genuinely distinct workspaces must both survive (the operator box's shape).
mkdir -p "$LINKROOT/second"
cat > "$TMP/two-config.json" <<EOF
{"agents":{"defaults":{"workspace":"$LINKROOT/clawd"},
 "entries":{"main":{"workspace":"$LINKROOT/clawd"},
            "other":{"workspace":"$LINKROOT/second"}}}}
EOF
COUNT2=$(python3 "$ENGINE" --from-config "$TMP/two-config.json" --list-workspaces 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT2" = "2" ]; then
  pass "two genuinely distinct workspaces are both kept (the operator-box shape)"
else
  fail "distinct workspaces collapsed to $COUNT2 — a real workspace would go uncompacted"
fi

# ── T7: ONE POINTER STANDARD ACROSS BOTH WRITERS ────────────────────────────
# DEFECT: two implementations of one format. The roll stamps pointers with
# bootstrap-pointerize.build_pointer; if this tool re-implemented the shape, a
# box would end up with pointers only half of its own tooling can resolve, and
# validate-core-references.py's dangling-pointer check would silently skip them.
if grep -q 'build_pointer = _PTR.build_pointer' "$ENGINE" &&
   grep -q 'POINTER_SENTINEL = _PTR.POINTER_SENTINEL' "$ENGINE"; then
  pass "the pointer writer is IMPORTED from bootstrap-pointerize, not re-implemented"
else
  fail "compact-bootstrap defines its own pointer shape — two standards now exist"
fi

# And the validator must actually resolve what this tool writes.
if python3 "$VALIDATOR" --workspace "$WS" "${BUDGET[@]}" 2>&1 | grep -q 'DANGLING POINTER'; then
  fail "the validator reports a dangling pointer against a freshly compacted workspace"
else
  pass "validate-core-references.py resolves every pointer this tool wrote"
fi

# ── T8: a workspace already under target is measured and left alone ─────────
# DEFECT: a weekly job that moves content on a healthy box is pure churn.
_fixture
python3 "$ENGINE" --workspace "$WS" --references "$REF" --apply >"$TMP/under.txt" 2>&1
if cmp -s "$WS/AGENTS.md" <(python3 - "$WS" <<'PYEOF'
import sys
sys.stdout.write(open(sys.argv[1] + "/AGENTS.md").read())
PYEOF
) && ! grep -q 'Full text:' "$WS/AGENTS.md"; then
  pass "a file under its lean target is measured and nothing is moved"
else
  fail "content moved out of a file that was already under target"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
[ "$FAIL" -eq 0 ] || exit 1
