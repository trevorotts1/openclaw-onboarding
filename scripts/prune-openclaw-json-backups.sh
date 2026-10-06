#!/usr/bin/env bash
# prune-openclaw-json-backups.sh [config-dir ...]
# Every repo script that edits openclaw.json writes its own timestamped copy
# (openclaw.json.bak-*, .clobbered*, ...) and nothing ever pruned them: one box
# carried 102. KEEP: openclaw.json, openclaw.json.last-good, and the newest
# KEEP_N (default 3) other openclaw.json.* copies. DELETE the rest.
# Never touches openclaw.json, .last-good, lock or in-flight .tmp files. Safe to run
# any time; scripts that write a backup call this right after writing it.
# Default dirs: $OPENCLAW_ROOT, ~/.openclaw, /data/.openclaw.
set -u
KEEP_N="${OPENCLAW_JSON_BACKUPS_KEEP:-3}"
case "$KEEP_N" in ''|*[!0-9]*) KEEP_N=3 ;; esac
if [ "$#" -gt 0 ]; then dirs=("$@"); else dirs=("${OPENCLAW_ROOT:-}" "$HOME/.openclaw" /data/.openclaw); fi
pruned=0
# protected / in-flight names (a plain function: bash 3.2 cannot parse case patterns inside $(...))
_skip() {
  case "${1##*/}" in
    openclaw.json.last-good|openclaw.json.lock*|openclaw.json.tmp*|*.tmp|*.tmp.*) return 0 ;;
  esac
  return 1
}
for d in "${dirs[@]}"; do
  [ -n "$d" ] && [ -d "$d" ] || continue
  # newest first; names are only the candidates, mtime decides
  files=()
  while IFS= read -r f; do
    _skip "$f" && continue
    [ -f "$f" ] && [ ! -L "$f" ] && files+=("$f")
  done < <(ls -1t "$d"/openclaw.json.* 2>/dev/null)
  i=0
  for f in ${files[@]+"${files[@]}"}; do
    i=$((i + 1))
    [ "$i" -le "$KEEP_N" ] && continue
    rm -f -- "$f" 2>/dev/null && pruned=$((pruned + 1))
  done
done
echo "backup-prune: removed $pruned stale openclaw.json copies (kept newest $KEEP_N + last-good)"
exit 0
