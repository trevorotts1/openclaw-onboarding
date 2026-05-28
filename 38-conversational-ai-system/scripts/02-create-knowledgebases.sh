#!/usr/bin/env bash
# 02-create-knowledgebases.sh — Skill 38 / Step 9.22 (Typed Knowledge Bases, v5.6)
# Creates the four typed knowledge bases under <MASTER_FILES_DIR>/KnowledgeBases/.
# Bases: business, products, sales, conversations. Idempotent (does NOT overwrite existing).

set -euo pipefail
[ -f "$HOME/.openclaw/.skill-38-master-files-dir" ] && . "$HOME/.openclaw/.skill-38-master-files-dir"
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set — run 01-locate-master-files-folder.sh first}"

KB_ROOT="$MASTER_FILES_DIR/KnowledgeBases"
mkdir -p "$KB_ROOT"

for kb in business products sales conversations; do
  KB_DIR="$KB_ROOT/$kb"
  mkdir -p "$KB_DIR"
  if [ ! -f "$KB_DIR/registry.md" ]; then
    cat > "$KB_DIR/registry.md" <<MD
# $kb Knowledge Base — Registry

Per v5.14 playbook Step 9.22 (Typed Knowledge Bases, v5.6). This base
holds $kb-typed documents the agent retrieves from when answering. See
\`protocols/typed-knowledge-bases-protocol.md\` for the typing rules.

## Documents in this base

(none yet — populated by the operator or by skill 38 web-scraper)
MD
    echo "[skill 38] created $KB_DIR/registry.md"
  else
    echo "[skill 38] $kb registry already exists — preserved"
  fi
done

echo "[skill 38] 4 typed knowledge bases ready at $KB_ROOT"
