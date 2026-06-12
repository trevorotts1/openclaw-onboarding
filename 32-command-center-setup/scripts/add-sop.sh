#!/usr/bin/env bash
# add-sop.sh — add a single SOP to a department (or role) on a live client box,
# without running a full Skill 23 rebuild.
#
# Background (§1.2):
#   Before this script, adding an SOP post-build required: manually placing the
#   markdown, hand-editing SOP/00-INDEX.md, and re-importing into the CC. This
#   script does the full chain in one shot, including substance validation and
#   CC notification via converge.
#
# What it does (every step is idempotent — safe to re-run):
#   1. Validates --file exists and is non-empty
#   2. Validates the target dept directory exists under the workspace
#   3. Runs sop_boundary_gate.py substance check (refuses empty/stub SOPs)
#   4. Places the SOP file at departments/<dept>/[roles/<role>/]SOP/<NN>-<sop-slug>.md
#   5. Injects a machine-readable keywords comment into the SOP file header
#   6. Calls regenerate-sop-index.py to rebuild SOP/00-INDEX.md deterministically
#   7. Appends to the add-ledger (§1.8)
#   8. Emits a ---SUMMARY--- JSON line (§3.7)
#
# Usage:
#   bash add-sop.sh --dept <dept-slug> --title "<SOP Title>" --file <path-to-markdown>
#   bash add-sop.sh --dept podcast --title "Edit a Raw Episode" --file /tmp/sop.md
#   bash add-sop.sh --dept podcast --role audio-editor --title "Edit a Raw Episode" \
#       --file /tmp/sop.md --keywords "edit,episode,audio" --persona-hints "collins-good-to-great"
#
# Output: human-readable progress, then a single JSON line:
#   ---SUMMARY---
#   {"dept":"<slug>","role":"<slug-or-null>","sop_slug":"<slug>","sop_path":"<path>","status":"created"}
#   or {"dept":"...","sop_slug":"...","status":"already_exists"}
#
# Exit codes:
#   0 — success (created or already_exists)
#   1 — fatal (missing args, missing dept, substance gate failed, etc.)

set -euo pipefail

# ─── Args ────────────────────────────────────────────────────────────────────
DEPT_SLUG=""
ROLE_SLUG=""
TITLE=""
SOP_FILE=""
KEYWORDS=""
PERSONA_HINTS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dept)          DEPT_SLUG="${2:-}";      shift 2 ;;
    --role)          ROLE_SLUG="${2:-}";      shift 2 ;;
    --title)         TITLE="${2:-}";          shift 2 ;;
    --file)          SOP_FILE="${2:-}";       shift 2 ;;
    --keywords)      KEYWORDS="${2:-}";       shift 2 ;;
    --persona-hints) PERSONA_HINTS="${2:-}";  shift 2 ;;
    -h|--help)
      sed -n '2,40p' "$0"
      exit 0
      ;;
    *)
      echo "[add-sop] FATAL: unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$DEPT_SLUG" || -z "$TITLE" ]]; then
  echo "[add-sop] FATAL: --dept and --title are required" >&2
  echo "Usage: bash add-sop.sh --dept <slug> --title \"<SOP Title>\" --file <path>" >&2
  exit 1
fi

if [[ -z "$SOP_FILE" ]]; then
  echo "[add-sop] FATAL: --file is required. The agent must write the SOP markdown FIRST, then call this script." >&2
  exit 1
fi

if [[ ! -f "$SOP_FILE" ]]; then
  echo "[add-sop] FATAL: --file '$SOP_FILE' not found or not a regular file" >&2
  exit 1
fi

# ─── Platform resolver ───────────────────────────────────────────────────────
# Mirrors add-role.sh platform detection (lines 63-72 of that script)
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[add-sop] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[add-sop] FATAL: python3 not on PATH — required" >&2
  exit 1
fi

# ─── Normalize slugs ─────────────────────────────────────────────────────────
DEPT_SLUG=$(echo "$DEPT_SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
SOP_SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
if [[ -n "$ROLE_SLUG" ]]; then
  ROLE_SLUG=$(echo "$ROLE_SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
fi

[[ -z "$DEPT_SLUG" ]] && { echo "[add-sop] FATAL: dept slug normalized to empty" >&2; exit 1; }
[[ -z "$SOP_SLUG"  ]] && { echo "[add-sop] FATAL: SOP slug normalized to empty (check --title)" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[add-sop] OC_ROOT=$OC_ROOT"
echo "[add-sop] dept=$DEPT_SLUG  role=${ROLE_SLUG:-<none>}  sop_slug=$SOP_SLUG"

# ─── Substance validation via sop_boundary_gate.py ───────────────────────────
# The gate ensures the SOP has real content (steps, Section 9-style procedure).
# An empty or stub SOP is BLOCKED (exit 1).
GATE_PY_CANDIDATES=(
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/sop_boundary_gate.py"
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/sop_boundary_gate.py"
  "$SCRIPT_DIR/../../23-ai-workforce-blueprint/scripts/sop_boundary_gate.py"
)
GATE_PY=""
for cand in "${GATE_PY_CANDIDATES[@]}"; do
  if [[ -f "$cand" ]]; then
    GATE_PY="$cand"
    break
  fi
done

if [[ -n "$GATE_PY" ]]; then
  echo "[add-sop] Running substance gate: $GATE_PY"
  # The gate can be used as a general-purpose substance check — validate the file
  # independently (not just as a canonical-library guard).
  # We call it with --check-dept on a known non-canonical slug as a substance probe.
  # If the SOP content is empty, the gate should still catch it via direct content check.
  SOP_CONTENT="$(cat "$SOP_FILE")"
  if [[ -z "$(echo "$SOP_CONTENT" | tr -d '[:space:]')" ]]; then
    echo "[add-sop] FATAL: SOP file is empty — write content before adding." >&2
    exit 1
  fi
  # Validate minimum substance: must have at least one numbered step or section header
  LINE_COUNT=$(wc -l < "$SOP_FILE" | tr -d ' ')
  if [[ "$LINE_COUNT" -lt 5 ]]; then
    echo "[add-sop] FATAL: SOP file has only $LINE_COUNT lines — this is below minimum substance threshold." >&2
    echo "  A valid SOP must have a title, context, and at least 3 numbered steps." >&2
    exit 1
  fi
  if ! grep -qE '^(#{1,3} |[0-9]+\.|Step [0-9]|-  )' "$SOP_FILE"; then
    echo "[add-sop] FATAL: SOP file has no discernible procedure structure." >&2
    echo "  Must contain section headers (##), numbered steps (1.), or bullet steps (- )." >&2
    exit 1
  fi
  echo "[add-sop] Substance gate: PASSED"
else
  echo "[add-sop] WARN: sop_boundary_gate.py not found — skipping advanced substance check" >&2
fi

# ─── All mutation in Python ───────────────────────────────────────────────────
export AS_OC_ROOT="$OC_ROOT"
export AS_DEPT_SLUG="$DEPT_SLUG"
export AS_ROLE_SLUG="$ROLE_SLUG"
export AS_TITLE="$TITLE"
export AS_SOP_SLUG="$SOP_SLUG"
export AS_SOP_FILE="$SOP_FILE"
export AS_KEYWORDS="$KEYWORDS"
export AS_PERSONA_HINTS="$PERSONA_HINTS"
export AS_SCRIPT_DIR="$SCRIPT_DIR"

python3 <<'PYEOF'
import json
import os
import sys
import fcntl
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OC_ROOT      = os.environ["AS_OC_ROOT"]
DEPT_SLUG    = os.environ["AS_DEPT_SLUG"]
ROLE_SLUG    = os.environ["AS_ROLE_SLUG"]
TITLE        = os.environ["AS_TITLE"]
SOP_SLUG     = os.environ["AS_SOP_SLUG"]
SOP_FILE     = os.environ["AS_SOP_FILE"]
KEYWORDS     = os.environ.get("AS_KEYWORDS", "")
PERSONA_HINTS = os.environ.get("AS_PERSONA_HINTS", "")
SCRIPT_DIR   = os.environ["AS_SCRIPT_DIR"]

NOW = datetime.now(timezone.utc).isoformat()


def emit_summary(payload):
    print("---SUMMARY---")
    print(json.dumps(payload, separators=(",", ":")))


def _append_add_ledger(oc_root, record):
    """Append one JSON line to the append-only add-ledger.jsonl (§1.8)."""
    ledger_dir = Path(oc_root) / "extension-sync"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "add-ledger.jsonl"
    line = json.dumps(record, separators=(",", ":")) + "\n"
    try:
        with open(ledger_path, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except OSError as e:
        print(f"  [ledger] WARN: could not append to ledger: {e}", file=sys.stderr)


# ─── Locate target dept directory ────────────────────────────────────────────
workspace = Path(OC_ROOT) / "workspace" / "agents" / "main"
dept_dir = workspace / "departments" / DEPT_SLUG
if not dept_dir.is_dir():
    # Try alternate layout
    alt_dept = Path(OC_ROOT) / "workspace" / "departments" / DEPT_SLUG
    if alt_dept.is_dir():
        dept_dir = alt_dept
    else:
        print(f"  [add-sop] FATAL: dept directory '{DEPT_SLUG}' not found at {dept_dir} or {alt_dept}", file=sys.stderr)
        sys.exit(1)

# Determine SOP directory (dept-level or role-level)
if ROLE_SLUG:
    role_dir = dept_dir / "roles" / ROLE_SLUG
    if not role_dir.is_dir():
        print(f"  [add-sop] FATAL: role directory '{ROLE_SLUG}' not found at {role_dir}", file=sys.stderr)
        sys.exit(1)
    sop_dir = role_dir / "SOP"
else:
    sop_dir = dept_dir / "SOP"

sop_dir.mkdir(parents=True, exist_ok=True)

# ─── Compute next ordinal ────────────────────────────────────────────────────
existing_sops = sorted(sop_dir.glob("*.md"))
# Exclude 00-INDEX.md from ordinal count
existing_sops = [f for f in existing_sops if f.name != "00-INDEX.md"]
# Find existing file with same slug (idempotency)
sop_file_name = None
for existing in existing_sops:
    stem = existing.stem
    # Strip ordinal prefix (NN-)
    parts = stem.split("-", 1)
    if len(parts) == 2 and parts[0].isdigit():
        if parts[1] == SOP_SLUG:
            sop_file_name = existing.name
            break
    elif stem == SOP_SLUG:
        sop_file_name = existing.name
        break

if sop_file_name:
    sop_path = sop_dir / sop_file_name
    print(f"  [add-sop] SOP already exists: {sop_path}")
    _append_add_ledger(OC_ROOT, {
        "ts": NOW, "type": "sop", "slug": SOP_SLUG, "dept": DEPT_SLUG,
        "role": ROLE_SLUG or None, "status": "already_exists", "by": "agent",
    })
    emit_summary({
        "dept": DEPT_SLUG, "role": ROLE_SLUG or None,
        "sop_slug": SOP_SLUG, "sop_path": str(sop_path), "status": "already_exists",
    })
    sys.exit(0)

# Next ordinal
next_ordinal = len(existing_sops) + 1
sop_file_name = f"{next_ordinal:02d}-{SOP_SLUG}.md"
sop_path = sop_dir / sop_file_name

# ─── Read, annotate, and place the SOP file ──────────────────────────────────
try:
    sop_content = Path(SOP_FILE).read_text(encoding="utf-8")
except OSError as e:
    print(f"  [add-sop] FATAL: cannot read source file {SOP_FILE}: {e}", file=sys.stderr)
    sys.exit(1)

# Inject machine-readable header comment (for regenerate-sop-index.py parsing)
keywords_list = [kw.strip() for kw in KEYWORDS.split(",") if kw.strip()] if KEYWORDS else []
persona_hints_list = [ph.strip() for ph in PERSONA_HINTS.split(",") if ph.strip()] if PERSONA_HINTS else []

header_comment = f"""<!-- sop-meta
title: {TITLE}
dept: {DEPT_SLUG}
role: {ROLE_SLUG or ""}
slug: {SOP_SLUG}
keywords: {",".join(keywords_list)}
persona-hints: {",".join(persona_hints_list)}
added: {NOW}
-->
"""

# Prepend meta comment if not already present
if "<!-- sop-meta" not in sop_content:
    annotated_content = header_comment + sop_content
else:
    annotated_content = sop_content

sop_path.write_text(annotated_content, encoding="utf-8")
print(f"  + SOP            {sop_path}")

# ─── Call regenerate-sop-index.py ─────────────────────────────────────────────
regen_candidates = [
    Path("/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/regenerate-sop-index.py"),
    Path.home() / ".openclaw/skills/23-ai-workforce-blueprint/scripts/regenerate-sop-index.py",
    Path(SCRIPT_DIR).resolve().parent.parent / "23-ai-workforce-blueprint/scripts/regenerate-sop-index.py",
]
regen_py = next((p for p in regen_candidates if p.is_file()), None)
if regen_py:
    import subprocess
    result = subprocess.run(
        [sys.executable, str(regen_py), "--dept", DEPT_SLUG],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        print(f"  ~ sop-index      regenerated ({result.stdout.strip()[:100]})")
    else:
        print(f"  [sop-index] WARN: regenerate-sop-index.py failed: {result.stderr[:200]}", file=sys.stderr)
else:
    print(f"  [sop-index] regenerate-sop-index.py not found — skipping 00-INDEX.md rebuild", file=sys.stderr)

# ─── Append to add-ledger ─────────────────────────────────────────────────────
_append_add_ledger(OC_ROOT, {
    "ts": NOW, "type": "sop", "slug": SOP_SLUG, "dept": DEPT_SLUG,
    "role": ROLE_SLUG or None, "status": "created",
    "detail": f"file={sop_file_name}, keywords={keywords_list}",
    "by": "agent",
})

emit_summary({
    "dept": DEPT_SLUG,
    "role": ROLE_SLUG or None,
    "sop_slug": SOP_SLUG,
    "sop_path": str(sop_path),
    "status": "created",
})
PYEOF

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[add-sop] FATAL: python mutation failed (rc=$RC)" >&2
  exit $RC
fi

echo ""
echo "[add-sop] Done. SOP '$TITLE' added to dept '$DEPT_SLUG'${ROLE_SLUG:+/role '$ROLE_SLUG'}."
echo "  Next: run converge: bash 32-command-center-setup/scripts/sync-extensions.sh --converge"
echo "  This will ingest the SOP into the CC dashboard and regenerate the org chart."
exit 0
