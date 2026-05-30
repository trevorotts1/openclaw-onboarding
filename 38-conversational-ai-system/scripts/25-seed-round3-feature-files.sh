#!/usr/bin/env bash
# 25-seed-round3-feature-files.sh — Skill 38 v1.5.0 (Round-3 Queue-A)
#
# Seeds the supporting data files the Round-3 Queue-A features read/write, all
# under <MASTER_FILES_DIR>. Idempotent (NEVER overwrites an existing file — the
# operator's real content is preserved). Universal: placeholders only, zero
# personal/client data (machine-enforced by qc-no-personal-data.sh).
#
# Files seeded:
#   F45  KnowledgeBases/sales/service-areas.md      — per-product service areas (ZIP/county/state/radius)
#   F47  KnowledgeBases/business/faqs.md            — Q/A pairs the inline-FAQ tool matches
#   F46  crm-field-mappings.md                      — per-workflow CRM custom-field map (ZHC_ created fields)
#   F50/F44/F45/F46/F47  *.jsonl + aggression-detection-log.md  — the F52 data-contract log sinks (created empty)
#
# OS-aware (Darwin + Linux). bash -n clean. set -euo pipefail.

set -euo pipefail

# Resolve MASTER_FILES_DIR the same way the other numbered scripts do: READ the
# pointer file (it holds a bare directory string — do NOT source it).
MASTER_FILES_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"
if [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(cat "$MASTER_FILES_POINTER")"
fi
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set — run 01-locate-master-files-folder.sh first}"

KB_ROOT="$MASTER_FILES_DIR/KnowledgeBases"
mkdir -p "$KB_ROOT/sales" "$KB_ROOT/business"

# seed_file PATH < heredoc — write only if absent.
seed_file() {
  local path="$1"
  if [ -f "$path" ]; then
    echo "[skill 38] $(basename "$path") already exists — preserved"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  echo "[skill 38] seeded $path"
}

# ---------------------------------------------------------------------------
# F45 — per-product service areas (geo-qualification-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$KB_ROOT/sales/service-areas.md" <<'MD'
# Service Areas (F45 — geo-qualification)

Per-product service-area definitions the agent checks when
`geo_qualification.enabled` is true. Supports type `radius` / `zips` / `states` /
`counties`. A product with NO entry here is treated as "served everywhere" (no
geo-gate); the per-product `skill38.geo_qualification.per_product` toggle can also
force a product on/off (e.g. gate an in-person consult, never gate a digital
course) without disabling the feature globally. Signals are HINTS — the agent
ALWAYS confirms with the customer before any out-of-area handling, and "vacation,"
"moving," or a non-answer never disqualify. See protocols/geo-qualification-protocol.md.

## Out-of-area mode (operator-configured)
mode: decline_plus_referral   # decline_plus_referral | limited_remote | waitlist | full_decline

## Product: <PRODUCT_NAME>
- type: radius
- center: <CENTER_ZIP_OR_CITY>
- radius_miles: <MILES>

## Product: <PRODUCT_NAME_2>
- type: zips
- zips: <ZIP_LIST>            # comma-separated ZIP codes

## Product: <PRODUCT_NAME_3>
- type: states
- states: <STATE_LIST>        # two-letter state codes
MD

# ---------------------------------------------------------------------------
# F47 — FAQ knowledge base (smart-faq-tool-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$KB_ROOT/business/faqs.md" <<'MD'
# Frequently Asked Questions (F47 — smart inline FAQ)

Q/A pairs the inline-FAQ tool matches during an active workflow. A confident
match is answered in ONE sentence inline, then the workflow continues on the same
step. Low-confidence matches fall through to the normal reply path (Step 9.11
confidence gate). See protocols/smart-faq-tool-protocol.md.

## Q: <QUESTION>
A: <ANSWER — one or two sentences>

## Q: <QUESTION_2>
A: <ANSWER — one or two sentences>

## Q: <QUESTION_3>
A: <ANSWER — one or two sentences>
MD

# ---------------------------------------------------------------------------
# F46 — CRM field mappings (crm-field-write-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$MASTER_FILES_DIR/crm-field-mappings.md" <<'MD'
# CRM Field Mappings (F46 — CRM field write + create-if-missing)

Per-workflow record of the GHL contact custom fields the agent writes. Fields the
agent CREATES are named `ZHC_<snake_purpose>` (the field-side parallel of the
`ZHC-` tag namespace). The agent consults this map before a write to reuse an
existing field instead of creating a duplicate, and to know the exact field
id/dataType. See protocols/crm-field-write-protocol.md.

## Workflow: <WORKFLOW_ID>
| value captured | GHL field name | field id | dataType | created by AI? |
|---|---|---|---|---|
| <VALUE> | ZHC_<snake_purpose> | <FIELD_ID> | TEXT | yes |
MD

# ---------------------------------------------------------------------------
# F52 data-contract log sinks — created empty so the agent appends from turn 1.
# JSONL files start empty (0 lines); the human-readable aggression log gets a
# one-line header comment.
# ---------------------------------------------------------------------------
for jsonl in \
  aggression-detection-log.jsonl \
  interrupt-log.jsonl \
  geo-qualification-log.jsonl \
  crm-field-writes-log.jsonl \
  faq-detour-log.jsonl; do
  p="$MASTER_FILES_DIR/$jsonl"
  if [ -f "$p" ]; then
    echo "[skill 38] $jsonl already exists — preserved"
  else
    : > "$p"
    echo "[skill 38] created empty JSONL sink $p"
  fi
done

seed_file "$MASTER_FILES_DIR/aggression-detection-log.md" <<'MD'
# Aggression Detection Log (F50)

Human-readable record of aggression-classifier firings (Tier 1 tension / Tier 2
aggression), one short paragraph per firing with the tier, signals, and the
agent's reasoning. The machine-readable counterpart is
aggression-detection-log.jsonl. See protocols/aggression-detection-protocol.md.
MD

echo "[skill 38] Round-3 Queue-A feature files ready under $MASTER_FILES_DIR"
