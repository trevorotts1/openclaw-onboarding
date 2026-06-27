#!/usr/bin/env bash
# generate-governing-personas.sh — RC-1: Generate governing-personas.md for every department.
#
# Called by the Skill 23 build pipeline (Phase 5-PERSONA) to produce the
# Layers 1+2 pre-qualified persona pool for each department. Also callable
# standalone for audits / partial re-runs.
#
# What it does:
#   1. Locates persona-categories.json + the departments dir from environment
#      variables or from well-known paths (Mac + VPS).
#   2. For each department folder that LACKS a governing-personas.md (or has
#      an empty/stub one that lacks the "## Primary Persona" heading), writes
#      a minimal but valid governing-personas.md.
#   3. Exits 0 if every department now has a valid governing-personas.md.
#   4. Exits 1 (HARD FAIL) if any department is still missing one — the caller
#      MUST NOT proceed to Phase 5-ORG until this exits 0.
#
# Environment variables (all optional — auto-detected if absent):
#   DEPARTMENTS_DIR      — absolute path to the departments folder
#   COMPANY_SLUG         — company slug (auto-detected from ZHC tree if absent)
#   PERSONA_CATEGORIES   — path to persona-categories.json
#   COACHING_PERSONAS_DIR — path to coaching-personas/personas/ folder
#
# Exit codes:
#   0 = all departments have valid governing-personas.md
#   1 = one or more departments still missing a valid governing-personas.md
#   2 = DEPARTMENTS_DIR not resolvable (no ZHC tree found)
#
# Usage:
#   bash generate-governing-personas.sh
#   bash generate-governing-personas.sh --dry-run   # check only, no writes
#   DEPARTMENTS_DIR=/path/to/departments bash generate-governing-personas.sh

set -euo pipefail

DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "[governing-personas] WARN: unknown arg '$1' — ignoring" >&2; shift ;;
  esac
done

# ─── Path resolution ──────────────────────────────────────────────────────────

HOME_DIR="$HOME"

# Locate DEPARTMENTS_DIR
if [[ -z "${DEPARTMENTS_DIR:-}" ]]; then
  # Try ZHC canonical tree first
  for ZHC_ROOT in \
      "$HOME_DIR/clawd/zero-human-company" \
      "/data/clawd/zero-human-company" \
      "$HOME_DIR/clawd/zhc" \
      "/data/clawd/zhc"
  do
    if [[ -d "$ZHC_ROOT" ]]; then
      # Pick most-recently-modified company
      COMPANY_DIR=$(find "$ZHC_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name '.*' \
                    -printf '%T@ %p\n' 2>/dev/null \
                    | sort -rn | head -1 | awk '{print $2}') 2>/dev/null || true
      if [[ -n "$COMPANY_DIR" && -d "$COMPANY_DIR/departments" ]]; then
        DEPARTMENTS_DIR="$COMPANY_DIR/departments"
        break
      fi
    fi
  done
fi

# Mac fallback
if [[ -z "${DEPARTMENTS_DIR:-}" ]]; then
  for cand in \
      "$HOME_DIR/.openclaw/workspace/departments" \
      "/data/.openclaw/workspace/departments"
  do
    if [[ -d "$cand" ]]; then
      DEPARTMENTS_DIR="$cand"
      break
    fi
  done
fi

if [[ -z "${DEPARTMENTS_DIR:-}" || ! -d "${DEPARTMENTS_DIR}" ]]; then
  echo "[governing-personas] FATAL: DEPARTMENTS_DIR not resolvable. Set DEPARTMENTS_DIR or run Skill 23 first." >&2
  exit 2
fi

echo "[governing-personas] Using departments dir: $DEPARTMENTS_DIR"

# Locate persona-categories.json
# §1.7: Use the shared canonical resolver to reconcile path drift between
# orchestrator.py (workspace/data/coaching-personas/) and this script.
if [[ -z "${PERSONA_CATEGORIES:-}" ]]; then
  # Try the shared resolver first (preferred — single resolution chain)
  RESOLVER_CANDIDATES=(
    "/data/.openclaw/skills/shared-utils/resolve_persona_categories_path.py"
    "$HOME_DIR/.openclaw/skills/shared-utils/resolve_persona_categories_path.py"
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../shared-utils" 2>/dev/null && pwd)/resolve_persona_categories_path.py"
  )
  RESOLVER_PY=""
  for cand in "${RESOLVER_CANDIDATES[@]}"; do
    if [[ -f "$cand" ]]; then
      RESOLVER_PY="$cand"
      break
    fi
  done

  if [[ -n "$RESOLVER_PY" ]]; then
    PERSONA_CATEGORIES="$(python3 "$RESOLVER_PY" 2>/dev/null)" || PERSONA_CATEGORIES=""
    [[ -n "$PERSONA_CATEGORIES" ]] && [[ -f "$PERSONA_CATEGORIES" ]] && \
      echo "[governing-personas] persona-categories resolved via shared resolver: $PERSONA_CATEGORIES"
  fi

  # Fallback: legacy search order (kept for boxes where shared-utils not yet installed)
  if [[ -z "${PERSONA_CATEGORIES:-}" || ! -f "${PERSONA_CATEGORIES:-}" ]]; then
    for cand in \
        "$HOME_DIR/.openclaw/workspace/data/coaching-personas/persona-categories.json" \
        "/data/.openclaw/workspace/data/coaching-personas/persona-categories.json" \
        "$HOME_DIR/.openclaw/workspace/coaching-personas/persona-categories.json" \
        "/data/.openclaw/workspace/coaching-personas/persona-categories.json" \
        "$HOME_DIR/clawd/coaching-personas/persona-categories.json" \
        "$HOME_DIR/Downloads/openclaw-master-files/coaching-personas/persona-categories.json" \
        "$HOME_DIR/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"
    do
      if [[ -f "$cand" ]]; then
        PERSONA_CATEGORIES="$cand"
        echo "[governing-personas] persona-categories (fallback search): $PERSONA_CATEGORIES"
        break
      fi
    done
  fi
fi

# Locate coaching-personas/personas dir
if [[ -z "${COACHING_PERSONAS_DIR:-}" ]]; then
  for cand in \
      "$HOME_DIR/.openclaw/workspace/data/coaching-personas/personas" \
      "/data/.openclaw/workspace/data/coaching-personas/personas" \
      "$HOME_DIR/.openclaw/workspace/coaching-personas/personas" \
      "/data/.openclaw/workspace/coaching-personas/personas"
  do
    if [[ -d "$cand" ]]; then
      COACHING_PERSONAS_DIR="$cand"
      break
    fi
  done
fi

SKILL22_INSTALLED=false
if [[ -n "${PERSONA_CATEGORIES:-}" && -f "$PERSONA_CATEGORIES" ]] || \
   [[ -n "${COACHING_PERSONAS_DIR:-}" && -d "$COACHING_PERSONAS_DIR" ]]; then
  SKILL22_INSTALLED=true
fi

echo "[governing-personas] Skill 22 installed: $SKILL22_INSTALLED"
[[ -n "${PERSONA_CATEGORIES:-}" ]] && echo "[governing-personas] persona-categories: $PERSONA_CATEGORIES"
[[ -n "${COACHING_PERSONAS_DIR:-}" ]] && echo "[governing-personas] coaching-personas dir: $COACHING_PERSONAS_DIR"

# ─── Domain-tag → persona hint map (fallback when Skill 22 not installed) ─────

declare -A DOMAIN_HINT
DOMAIN_HINT[marketing]="Gary Halbert (The Gary Halbert Letter) | Gary Vaynerchuk (Crushing It) | Jay Abraham (Getting Everything You Can)"
DOMAIN_HINT[sales]="Alex Hormozi (100M Offers) | Oren Klaff (Pitch Anything) | Jeb Blount (Fanatical Prospecting)"
DOMAIN_HINT[billing-finance]="Profit First (Mike Michalowicz) | Warren Buffett (The Warren Buffett Way)"
DOMAIN_HINT[customer-support]="Tony Hsieh (Delivering Happiness) | Chip Bell (Wired and Dangerous)"
DOMAIN_HINT[web-development]="Martin Fowler (Refactoring) | Steve Krug (Don't Make Me Think)"
DOMAIN_HINT[app-development]="Frederick Brooks (Mythical Man-Month) | Eric Ries (The Lean Startup)"
DOMAIN_HINT[graphics]="Robin Williams (The Non-Designer's Design Book) | Paul Rand (A Designer's Art)"
DOMAIN_HINT[video]="Michael Wiese (Film Directing Shot by Shot) | Syd Field (Screenplay)"
DOMAIN_HINT[audio]="Mike Senior (Mixing Secrets for the Small Studio)"
DOMAIN_HINT[research]="Clayton Christensen (The Innovator's Dilemma) | Robert Cialdini (Influence)"
DOMAIN_HINT[communications]="Chip Heath (Made to Stick) | Carmine Gallo (Talk Like TED)"
DOMAIN_HINT[crm]="Aaron Ross (Predictable Revenue) | Jay Baer (Hug Your Haters)"
DOMAIN_HINT[openclaw-maintenance]="Gene Kim (The Phoenix Project) | Gene Kim (The DevOps Handbook)"
DOMAIN_HINT[legal]="Bryan Garner (Legal Writing in Plain English)"
DOMAIN_HINT[social-media]="Gary Vaynerchuk (Crushing It) | Jonah Berger (Contagious)"
DOMAIN_HINT[paid-advertisement]="Perry Marshall (Ultimate Guide to Google AdWords) | Ryan Deiss (Digital Marketing)"
DOMAIN_HINT[master-orchestrator]="Patrick Lencioni (The Five Dysfunctions of a Team) | Jim Collins (Good to Great)"
DOMAIN_HINT[presentations]="Nancy Duarte (Resonate) | Carmine Gallo (The Presentation Secrets of Steve Jobs)"
DOMAIN_HINT[personal-assistant]="David Allen (Getting Things Done) | Cal Newport (Deep Work)"
DOMAIN_HINT[podcast]="John Lee Dumas (The Common Path to Uncommon Success)"
DOMAIN_HINT[community-management]="Jono Bacon (People Powered)"
DOMAIN_HINT[course-creator]="Brendon Burchard (The Motivation Manifesto)"
DOMAIN_HINT[client-coaches]="Tony Robbins (Awaken the Giant Within)"

# ─── Generate governing-personas.md per department ────────────────────────────

TOTAL=0
MISSING=0
WRITTEN=0
VALID=0

# Gather available personas list from categories file if possible
AVAILABLE_PERSONAS=""
if [[ -f "${PERSONA_CATEGORIES:-/dev/null}" ]]; then
  AVAILABLE_PERSONAS=$(python3 - <<'PYEOF' 2>/dev/null
import json, sys, os
f = os.environ.get("PERSONA_CATEGORIES", "")
if not f: sys.exit(0)
try:
    data = json.load(open(f))
    ps = data.get("personas", data) if isinstance(data, dict) else {}
    if isinstance(ps, dict):
        for pid, info in list(ps.items())[:40]:
            if isinstance(info, dict):
                print(f"{pid}|{info.get('author','?')}|{info.get('book','?')}|{','.join(info.get('domain_tags', info.get('domain', [])))}")
except Exception as e:
    pass
PYEOF
) || true
fi
export PERSONA_CATEGORIES

for DEPT_DIR in "$DEPARTMENTS_DIR"/*/; do
  [[ -d "$DEPT_DIR" ]] || continue
  DEPT_NAME=$(basename "$DEPT_DIR")
  [[ "$DEPT_NAME" == .* ]] && continue
  ((TOTAL++)) || true

  GOVERNING="$DEPT_DIR/governing-personas.md"

  # Check validity: must exist AND contain "## Primary Persona" heading
  if [[ -f "$GOVERNING" ]] && grep -q "## Primary Persona" "$GOVERNING" 2>/dev/null; then
    ((VALID++)) || true
    echo "[governing-personas] OK: $DEPT_NAME — valid governing-personas.md"
    continue
  fi

  # Missing or stub
  ((MISSING++)) || true
  echo "[governing-personas] MISSING/STUB: $DEPT_NAME — will generate"

  if [[ "$DRY_RUN" == "true" ]]; then
    continue
  fi

  # Determine persona hint for this dept
  DEPT_KEY="${DEPT_NAME,,}"  # lowercase
  HINT="${DOMAIN_HINT[$DEPT_KEY]:-}"
  if [[ -z "$HINT" ]]; then
    # Try partial match for variant slugs
    for KEY in "${!DOMAIN_HINT[@]}"; do
      if [[ "$DEPT_KEY" == *"$KEY"* ]] || [[ "$KEY" == *"$DEPT_KEY"* ]]; then
        HINT="${DOMAIN_HINT[$KEY]}"
        break
      fi
    done
  fi
  [[ -z "$HINT" ]] && HINT="Gary Vaynerchuk (Crushing It) | Alex Hormozi (100M Offers)"

  # Extract first persona from hint for Primary slot.
  # NOTE: trim with sed, NOT xargs — xargs treats an apostrophe in a persona/book
  # title (e.g. "The Non-Designer's Design Book", "The Innovator's Dilemma") as an
  # unmatched quote and aborts, halting the whole persona refresh. sed is quote-safe.
  PRIMARY_LINE=$(echo "$HINT" | cut -d'|' -f1 | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
  SECONDARY_LINES=$(echo "$HINT" | cut -d'|' -f2- | tr '|' '\n' | sed 's/^ *//; s/ *$//' | grep -v '^$')

  DEPT_DISPLAY=$(echo "$DEPT_NAME" | tr '-' ' ' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1))substr($i,2)}1')

  # Get available personas for this dept from categories
  PERSONAS_SECTION=""
  if [[ -n "$AVAILABLE_PERSONAS" ]]; then
    PERSONAS_SECTION=$(echo "$AVAILABLE_PERSONAS" | head -20 | awk -F'|' '{print "- **"$2"** ("$3") — "$4}')
  fi

  cat > "$GOVERNING" <<MDEOF
# Governing Personas — ${DEPT_DISPLAY}

## Primary Persona
- **Name:** ${PRIMARY_LINE}
- **Why This Fits:** Aligns with the ${DEPT_DISPLAY} department's core mission and the owner's drive for excellence. Provides a proven methodology that guides task execution in this domain.
- **3 Task Types:**
  1. Strategy and planning tasks — applying the persona's core frameworks
  2. Execution and delivery tasks — using the persona's standards for quality
  3. Review and optimisation tasks — leveraging the persona's definition of done

## Secondary Personas
$(echo "$SECONDARY_LINES" | head -3 | while IFS= read -r line; do [[ -n "$line" ]] && echo "- $line — use when the primary doesn't fully address the task domain"; done)

## Available Persona Pool
$(if [[ -n "$PERSONAS_SECTION" ]]; then echo "$PERSONAS_SECTION"; else echo "*(Install Skill 22 to populate the full persona library)*"; fi)

## Runtime Selection
Personas are selected PER TASK using the 5-layer alignment:
1. Company Mission alignment
2. Owner Values alignment (from USER.md)
3. Company Goals/KPI alignment
4. Department Goals/KPI alignment
5. Task Fit

Run persona selection at task time:
\`\`\`bash
python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py \\
    --task "<describe the task here>" \\
    --department ${DEPT_NAME} \\
    --format json
\`\`\`

*Auto-generated by generate-governing-personas.sh on $(date +%Y-%m-%d). Update after installing Skill 22 or adding new personas.*
MDEOF

  echo "[governing-personas] WROTE: $DEPT_DIR/governing-personas.md"
  ((WRITTEN++)) || true
done

echo ""
echo "[governing-personas] Summary: $TOTAL departments scanned"
echo "[governing-personas]   $VALID already valid"
echo "[governing-personas]   $WRITTEN newly written"
echo "[governing-personas]   $MISSING missing before this run"

if [[ "$DRY_RUN" == "true" ]]; then
  STILL_MISSING=$MISSING
else
  # Re-count after writes
  STILL_MISSING=0
  for DEPT_DIR in "$DEPARTMENTS_DIR"/*/; do
    [[ -d "$DEPT_DIR" ]] || continue
    DEPT_NAME=$(basename "$DEPT_DIR")
    [[ "$DEPT_NAME" == .* ]] && continue
    GOVERNING="$DEPT_DIR/governing-personas.md"
    if [[ ! -f "$GOVERNING" ]] || ! grep -q "## Primary Persona" "$GOVERNING" 2>/dev/null; then
      echo "[governing-personas] STILL MISSING: $DEPT_NAME" >&2
      ((STILL_MISSING++)) || true
    fi
  done
fi

if [[ "$STILL_MISSING" -gt 0 ]]; then
  echo "[governing-personas] HARD FAIL: $STILL_MISSING department(s) still lack a valid governing-personas.md." >&2
  echo "[governing-personas] DO NOT proceed to Phase 5-ORG until every department has one." >&2
  exit 1
fi

echo "[governing-personas] PASS: all departments have valid governing-personas.md"
exit 0
