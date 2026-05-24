#!/usr/bin/env bash
# backfill-dept-agent-personalization.sh — retroactive fix for finding #89.
#
# Background:
#   Before v10.14.35, scaffold-agent-files.sh wrote IDENTITY.md / SOUL.md /
#   MEMORY.md / HEARTBEAT.md for each dept-head with no company-name
#   substitution — the files just referenced the dept slug ("marketing
#   department's performance") with no mention of the owner's company.
#
#   v10.14.35 fixes this for fresh installs. This backfill script patches
#   already-installed clients in place. Safe to re-run.
#
# What it does (per dept folder under $OC_ROOT/workspace/departments/):
#   1. Detect the four scaffolder-written files (IDENTITY/SOUL/MEMORY/HEARTBEAT)
#      that have NO company-name reference.
#   2. Move them to a `.backfill-backup/` subfolder with timestamp
#      (we never destroy operator-edited content).
#   3. Re-run scaffold-agent-files.sh with --force so the new personalized
#      templates land in their place.
#
# Skips dept-head files that already contain the company name (no churn).
#
# Usage:
#   bash backfill-dept-agent-personalization.sh             # apply
#   bash backfill-dept-agent-personalization.sh --dry-run   # report only
#   bash backfill-dept-agent-personalization.sh --force-all # re-run even if
#                                                            company name found
#
# Exit codes:
#   0 — success (zero or more depts backfilled)
#   1 — fatal (missing dependencies, no OC_ROOT, etc.)

set -euo pipefail

DRY_RUN=0
FORCE_ALL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --force-all)  FORCE_ALL=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
  esac
done

# ─── Platform detection ──────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[backfill] FATAL: no OpenClaw root found" >&2
  exit 1
fi

SCAFFOLDER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scaffold-agent-files.sh"
if [[ ! -x "$SCAFFOLDER" ]]; then
  echo "[backfill] FATAL: scaffold-agent-files.sh not executable at $SCAFFOLDER" >&2
  exit 1
fi

# Pretty-name map (mirror of materialize-dept-agents.sh).
# Implemented as a case statement so this script works on macOS's stock
# bash 3.2 (no `declare -A` support) in addition to Linux bash 4+.
pretty_name() {
  local slug="$1"
  case "$slug" in
    marketing)            echo "Chief Marketing Officer" ;;
    sales)                echo "Chief Revenue Officer" ;;
    billing-finance)      echo "Chief Financial Officer" ;;
    customer-support)     echo "Director of Customer Success" ;;
    web-development)      echo "Head of Web Development" ;;
    app-development)      echo "Head of App Development" ;;
    graphics)             echo "Creative Director — Graphics" ;;
    video)                echo "Creative Director — Video" ;;
    audio)                echo "Creative Director — Audio" ;;
    research)             echo "Director of Research" ;;
    communications)       echo "Director of Communications" ;;
    crm)                  echo "Head of CRM" ;;
    openclaw-maintenance) echo "OpenClaw Maintenance Lead" ;;
    legal-compliance)     echo "General Counsel" ;;
    social-media)         echo "Head of Social Media" ;;
    paid-advertisement)   echo "Head of Paid Advertising" ;;
    master-orchestrator)  echo "Master Orchestrator (CEO Agent)" ;;
    *)
      # Default: title-case the slug ("vertical-pack" → "Vertical Pack")
      echo "$slug" | tr '-' ' ' | awk '{for (i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1'
      ;;
  esac
}

DEPT_ROOT="$OC_ROOT/workspace/departments"
if [[ ! -d "$DEPT_ROOT" ]]; then
  echo "[backfill] no departments dir at $DEPT_ROOT — nothing to backfill"
  exit 0
fi

# Resolve company name once (for the "already personalized" check).
# Order of truth, in case company-config.json is unset (early v10.14.x clients):
#   1. <company_dir>/company-config.json companyName / company_name / name
#   2. workspace/zero-human-company/company-config.json
#   3. workspace/company-config.json (legacy)
#   4. workspace/memory/workforce-interview-answers.md — first "Company Name"
#      Q&A in markdown (real source of truth before Skill 23 v2.1)
COMPANY_NAME=""
COMPANY_INDUSTRY=""
if command -v python3 >/dev/null 2>&1; then
  _BACKFILL_TOKENS=$(python3 - "$OC_ROOT" <<'PYEOF' 2>/dev/null || true
import json, re, sys
from pathlib import Path
oc_root = Path(sys.argv[1])

company_name = ""
company_industry = ""

# 1+2+3: company-config.json candidates
candidates = []
zhc = oc_root / "workspace" / "zero-human-company"
if zhc.is_dir():
    for c in sorted(zhc.iterdir()):
        if c.is_dir():
            p = c / "company-config.json"
            if p.exists(): candidates.append(p)
candidates.append(zhc / "company-config.json")
candidates.append(oc_root / "workspace" / "company-config.json")
for c in candidates:
    if c.exists():
        try:
            d = json.loads(c.read_text())
            if not company_name:
                for k in ("companyName","company_name","name"):
                    if d.get(k):
                        company_name = str(d[k]); break
            if not company_industry:
                for k in ("companyIndustry","industry","industryVertical"):
                    if d.get(k):
                        company_industry = str(d[k]); break
            if company_name and company_industry:
                break
        except Exception:
            pass

# 4: workforce-interview-answers.md fallback
if not company_name:
    answers_md = oc_root / "workspace" / "memory" / "workforce-interview-answers.md"
    if answers_md.exists():
        try:
            text = answers_md.read_text(encoding="utf-8", errors="ignore")
            # Look for "### Q?: Company Name\n...\n**Answer:** XYZ"
            # (an "**Asked:**" line may appear between the heading and answer)
            m = re.search(r"Company Name\s*\n(?:[^\n]*\n){0,3}\*\*Answer:\*\*\s*([^\n]+)", text, re.IGNORECASE)
            if m:
                company_name = m.group(1).strip()
            if not company_industry:
                m2 = re.search(r"Industry\s*\n(?:[^\n]*\n){0,3}\*\*Answer:\*\*\s*([^\n]+)", text, re.IGNORECASE)
                if m2:
                    company_industry = m2.group(1).strip()
        except Exception:
            pass

print(f"NAME={company_name}")
print(f"INDUSTRY={company_industry}")
PYEOF
  )
  if [[ -n "$_BACKFILL_TOKENS" ]]; then
    while IFS='=' read -r key val; do
      case "$key" in
        NAME)     COMPANY_NAME="$val" ;;
        INDUSTRY) COMPANY_INDUSTRY="$val" ;;
      esac
    done <<< "$_BACKFILL_TOKENS"
  fi
fi

# Export so scaffold-agent-files.sh picks these up via OC_COMPANY_NAME / OC_COMPANY_INDUSTRY
export OC_COMPANY_NAME="$COMPANY_NAME"
export OC_COMPANY_INDUSTRY="$COMPANY_INDUSTRY"

if [[ -z "$COMPANY_NAME" ]]; then
  echo "[backfill] WARN: could not detect company name — backfilled files will fall back to \"the company\""
fi
echo "[backfill] OC_ROOT=$OC_ROOT  COMPANY_NAME=\"${COMPANY_NAME:-<unset>}\""
echo "[backfill] mode: $( [[ $DRY_RUN -eq 1 ]] && echo dry-run || echo apply )  force-all: $FORCE_ALL"
echo ""

BACKFILLED=0
SKIPPED_ALREADY=0
SKIPPED_NO_FILES=0

for dept_dir in "$DEPT_ROOT"/*/; do
  [[ -d "$dept_dir" ]] || continue
  slug=$(basename "$dept_dir")
  # Skip non-dept files / dirs (README.md etc. are filtered by the -d check above)
  case "$slug" in
    .git|.cache|_archive|node_modules|shared|templates) continue ;;
  esac

  echo "── $slug ──"

  identity="$dept_dir/IDENTITY.md"
  if [[ ! -f "$identity" ]]; then
    echo "  ! no IDENTITY.md — skipping (not a dept-head folder)"
    SKIPPED_NO_FILES=$((SKIPPED_NO_FILES+1))
    continue
  fi

  # Decide: does this IDENTITY.md need backfill?
  needs_backfill=1
  if [[ $FORCE_ALL -eq 0 && -n "$COMPANY_NAME" ]]; then
    if grep -qF "$COMPANY_NAME" "$identity"; then
      echo "  = already personalized (found \"$COMPANY_NAME\" in IDENTITY.md)"
      needs_backfill=0
      SKIPPED_ALREADY=$((SKIPPED_ALREADY+1))
    fi
  fi

  if [[ $needs_backfill -eq 0 ]]; then
    continue
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  ~ would backfill (dry-run)"
    BACKFILLED=$((BACKFILLED+1))
    continue
  fi

  # Backup the four scaffolder-written files before re-writing them
  backup_dir="$dept_dir/.backfill-backup-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$backup_dir"
  for f in IDENTITY.md SOUL.md MEMORY.md HEARTBEAT.md; do
    if [[ -f "$dept_dir/$f" ]]; then
      cp "$dept_dir/$f" "$backup_dir/$f"
      rm "$dept_dir/$f"
    fi
  done
  echo "  + backed up to $backup_dir"

  # Re-scaffold with the personalized templates
  agent_name=$(pretty_name "$slug")
  if bash "$SCAFFOLDER" \
      --agent-slug "$slug" \
      --agent-name "$agent_name" \
      --department "$slug" \
      --workspace-dir "$(realpath "$dept_dir")" \
      --shared-root "$OC_ROOT/workspace" >/dev/null 2>&1; then
    echo "  + re-scaffolded with company personalization"
    BACKFILLED=$((BACKFILLED+1))
  else
    echo "  ! scaffold-agent-files failed for $slug — restoring from backup" >&2
    for f in IDENTITY.md SOUL.md MEMORY.md HEARTBEAT.md; do
      if [[ -f "$backup_dir/$f" ]]; then
        cp "$backup_dir/$f" "$dept_dir/$f"
      fi
    done
  fi
done

echo ""
echo "[backfill] summary:"
echo "  backfilled:        $BACKFILLED"
echo "  already-good:      $SKIPPED_ALREADY"
echo "  no-files (skipped): $SKIPPED_NO_FILES"
exit 0
