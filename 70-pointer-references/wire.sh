#!/usr/bin/env bash
# wire.sh - Skill 70 (Pointer References) installer. update-skills.sh runs it
# automatically on every fleet update (`bash wire.sh --idempotent`); INSTALL.md
# runs it by hand. Safe to run any number of times.
#
# WHAT IT DOES, IN ORDER
#   1. Installs the playbook where the AGENTS.md pointer says it lives:
#        <master-files>/70-pointer-references/pointer-references-full.md
#      (refreshed only when the skill's copy differs).
#   2. Creates <master-files>/playbooks/ and its README.md master index if they
#      do not exist. An existing index is never touched.
#   3. Writes the two CORE_UPDATES.md payloads (the AGENTS.md pointer and the
#      MEMORY.md "core files" definition) between this skill's own
#      BEGIN/END markers, REPLACE-IN-PLACE, with [MASTER_FILES_FOLDER] resolved.
#      Each file is backed up into <backups>/pointer-references/wire-<stamp>/
#      before it changes; an unchanged file is neither backed up nor written.
#   4. Stamps <!-- skill:70-pointer-references:core-update-applied --> into
#      AGENTS.md (add-only) so the generic CORE_UPDATES merger never pastes the
#      payloads a second time.
#   5. Registers the weekly cron job (scripts/install-weekly-cron.sh --apply).
#      If that is refused (model identifiers not provable on this box, or the
#      command line lacks a flag) or fails, wire.sh exits non-zero so the next
#      fleet update retries it; steps 1 to 4 have already landed by then.
#
# It only ever touches its OWN skill:70-pointer-references markers; no other
# skill's block or stamp is read, moved or removed. It never reads or writes
# agents.defaults.bootstrapMaxChars or bootstrapTotalMaxChars.
#
# --no-cron skips step 5 (used by the tests and by an operator who wants the
# core-file wiring without the job). --idempotent is accepted and ignored.
# EXIT: 0 done | non-zero = the step that failed (see the message).

set -euo pipefail
SKILL_SLUG="70-pointer-references"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib-paths.sh
. "$SKILL_DIR/scripts/lib-paths.sh"

DO_CRON=1
for a in "$@"; do
  case "$a" in
    --no-cron) DO_CRON=0 ;;
    --idempotent) ;;
    *) echo "[skill 70] unknown argument: $a" >&2; exit 3 ;;
  esac
done
command -v python3 >/dev/null 2>&1 || { echo "[skill 70] python3 is required" >&2; exit 2; }

WS="$(pr_workspace)"
MFD="$(pr_master_files)"
HOME70="$MFD/$SKILL_SLUG"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$(pr_backup_root)/pointer-references/wire-$STAMP"
mkdir -p "$WS" "$HOME70/reports" "$MFD/playbooks"

# 1. Playbook copy -------------------------------------------------------------
SRC="$SKILL_DIR/pointer-references-full.md"
DST="$HOME70/pointer-references-full.md"
if [ "$SRC" != "$DST" ] && ! cmp -s "$SRC" "$DST" 2>/dev/null; then
  cp "$SRC" "$DST"
  echo "[skill 70] installed playbook -> $DST"
fi

# 2. Master index (create once, never overwrite) --------------------------------
INDEX="$MFD/playbooks/README.md"
if [ ! -f "$INDEX" ]; then
  cat > "$INDEX" <<'EOF'
# Playbooks master index

One line per playbook: a dash, the system name as a link to its file, what it
covers, and its last verified date (full format and an example: section 5 of
the Pointer References playbook, skill 70). Every playbook in this folder is
listed here exactly once, and every playbook has a one-line pointer in a core
file. One system = one playbook.

EOF
  echo "[skill 70] created master index $INDEX"
fi

# 3. Core-file blocks from CORE_UPDATES.md --------------------------------------
write_block() { # <file> <target: agents|memory>
  local file="$1" target="$2" tmp
  [ -f "$file" ] || : > "$file"
  tmp="$(mktemp)"
  CU="$SKILL_DIR/CORE_UPDATES.md" TARGET="$target" MFD="$MFD" FILE="$file" OUT="$tmp" \
  SLUG="$SKILL_SLUG" python3 - <<'PY'
import os, re, sys
cu = open(os.environ["CU"], encoding="utf-8").read()
target = os.environ["TARGET"]
m = re.search(r"^## %s\.md - UPDATE REQUIRED\n(.*?)(?=^## [A-Z]+\.md |\Z)" % target.upper(), cu, re.S | re.M)
fence = re.search(r"^```[^\n]*\n(.*?)^```", m.group(1), re.S | re.M) if m else None
if not fence:
    sys.exit("CORE_UPDATES.md has no fenced payload for %s.md" % target.upper())
body = fence.group(1).rstrip("\n").replace("[MASTER_FILES_FOLDER]", os.environ["MFD"])
begin = "<!-- BEGIN skill:%s:%s -->" % (os.environ["SLUG"], target)
end = "<!-- END skill:%s:%s -->" % (os.environ["SLUG"], target)
lines = open(os.environ["FILE"], encoding="utf-8", errors="surrogateescape").read().split("\n")
kept, first, i = [], None, 0
while i < len(lines):
    if lines[i].strip() == begin:
        j = i + 1
        while j < len(lines) and lines[j].strip() != end:
            j += 1
        if j < len(lines):
            if kept and kept[-1] == "":
                kept.pop()
            if first is None:
                first = len(kept)
            i = j + 1
            continue
    kept.append(lines[i])
    i += 1
block = ["", begin] + body.split("\n") + [end]
if first is None:
    while kept and kept[-1] == "":
        kept.pop()
    kept.extend(block)
else:
    kept[first:first] = block
open(os.environ["OUT"], "w", encoding="utf-8", errors="surrogateescape").write("\n".join(kept).rstrip("\n") + "\n")
PY
  if cmp -s "$file" "$tmp"; then
    rm -f "$tmp"; echo "[skill 70] $(basename "$file"): block '$target' already current, no change"
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  cp -p "$file" "$BACKUP_DIR/$(basename "$file")"
  cat "$tmp" > "$file"; rm -f "$tmp"
  echo "[skill 70] $(basename "$file"): wrote block '$target' (backup: $BACKUP_DIR/$(basename "$file"))"
}
write_block "$WS/AGENTS.md" agents
write_block "$WS/MEMORY.md" memory

# 4. Sentinel (add-only) ---------------------------------------------------------
SENTINEL="<!-- skill:${SKILL_SLUG}:core-update-applied -->"
if ! grep -qF "$SENTINEL" "$WS/AGENTS.md"; then
  mkdir -p "$BACKUP_DIR"; [ -f "$BACKUP_DIR/AGENTS.md" ] || cp -p "$WS/AGENTS.md" "$BACKUP_DIR/AGENTS.md"
  printf '\n%s\n' "$SENTINEL" >> "$WS/AGENTS.md"
  echo "[skill 70] stamped $SENTINEL"
fi

# 5. Weekly cron job ------------------------------------------------------------
if [ "$DO_CRON" -eq 1 ]; then
  rc=0; bash "$SKILL_DIR/scripts/install-weekly-cron.sh" --apply || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "[skill 70] weekly cron job NOT in place (install-weekly-cron.sh exit $rc); core files are wired, the next update retries the job" >&2
    exit "$rc"
  fi
fi
echo "[skill 70] wiring complete (workspace: $WS; playbook: $DST)"
