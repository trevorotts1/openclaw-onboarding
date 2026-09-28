#!/usr/bin/env bash
# pointer-audit.sh - Skill 70 (Pointer References) audit, backup and
# content-preservation proof.
#
# WHAT IT DOES (read-only against core files and playbooks, always):
#   1. Size report: character count of each core file (AGENTS.md, TOOLS.md,
#      MEMORY.md, USER.md, IDENTITY.md, SOUL.md) against the 40,000 target.
#   2. Candidate blocks: sections longer than a short paragraph (about five
#      sentences), tagged when they look like always-on rules (keep inline) or
#      when they sit inside a block another skill's installer manages (never
#      move those by hand).
#   3. Pointers: every master-files path named in a core file must exist; every
#      pointer into the playbooks folder must carry a WHEN trigger and stay
#      within two sentences; unresolved placeholders are findings.
#   4. Orphans: every playbook must be listed in the master index AND pointed
#      to from at least one core file.
#   5. Duplicates: two playbooks for one system (same "System:" line, same
#      normalized file name, or identical content) are findings.
#   6. Index consistency: every index entry resolves, no entry is listed twice.
#   7. Playbook hygiene: each playbook carries "System:", "Last verified:" and a
#      "## What changed" section.
#   The moving and rewriting itself is agent judgment (see the playbook); this
#   script never edits a core file or a playbook.
#
# MODES
#   (default)            audit, print summary, write a report file
#   --dry-run            audit, print the full report to stdout, write nothing
#   --backup             copy every core file and the playbooks folder into a
#                        new timestamped backup folder, print its path, exit
#   --prove-moved OLD NEW
#                        content-preservation proof: every paragraph of OLD
#                        (the pre-edit backup) that is no longer in NEW (the
#                        edited core file) must exist verbatim (whitespace
#                        normalized) somewhere in the playbooks folder
#
# EXIT CODES (distinct on purpose)
#   0  PASS      no findings (or, for --prove-moved, every paragraph proven;
#                for --backup, backup written)
#   1  FINDINGS  one or more findings (or unproven paragraphs)
#   2  TOOLING   bad arguments, missing workspace, missing utility, or a
#                write that failed; nothing about the box was concluded
#
# OPTIONS
#   --workspace DIR     core files folder (default: main agent workspace)
#   --master-files DIR  master files folder (default: platform rule)
#   --playbooks DIR     playbooks folder (default: <master-files>/playbooks)
#   --index FILE        master index (default: <playbooks>/README.md)
#   --limit N           per-file target in characters (default 40000)
#   --report FILE       report path (default: <master-files>/70-pointer-references/reports/pointer-audit-<UTC stamp>.md)
#   --backup-root DIR   backup root (default: platform rule)
#   -h, --help
#
# HARD WALL: this script never reads or writes agents.defaults.bootstrapMaxChars
# or agents.defaults.bootstrapTotalMaxChars. It does not open openclaw.json
# except through lib-paths.sh, which reads only the workspace key.
#
# Compatible with macOS bash 3.2 and Linux bash. Idempotent: a re-run with no
# changes produces the same findings.

set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=lib-paths.sh
. "$SELF_DIR/lib-paths.sh"

PROG="pointer-audit.sh"
CORE_FILES="AGENTS.md TOOLS.md MEMORY.md USER.md IDENTITY.md SOUL.md"
LIMIT=40000
WS="" MFD="" PBD="" INDEX="" REPORT="" BACKUP_ROOT=""
MODE="audit" DRY=0 OLD="" NEW=""

die_tool() { echo "TOOLING ERROR [$PROG]: $*" >&2; exit 2; }
need_val() { [ $# -ge 2 ] && [ -n "$2" ] || die_tool "option $1 needs a value"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace)    need_val "$@"; WS="$2"; shift 2 ;;
    --master-files) need_val "$@"; MFD="$2"; shift 2 ;;
    --playbooks)    need_val "$@"; PBD="$2"; shift 2 ;;
    --index)        need_val "$@"; INDEX="$2"; shift 2 ;;
    --limit)        need_val "$@"; LIMIT="$2"; shift 2 ;;
    --report)       need_val "$@"; REPORT="$2"; shift 2 ;;
    --backup-root)  need_val "$@"; BACKUP_ROOT="$2"; shift 2 ;;
    --dry-run)      DRY=1; shift ;;
    --backup)       MODE="backup"; shift ;;
    --prove-moved)  [ $# -ge 3 ] || die_tool "--prove-moved needs OLD and NEW"
                    MODE="prove"; OLD="$2"; NEW="$3"; shift 3 ;;
    -h|--help)      sed -n '2,62p' "$0"; exit 0 ;;
    *)              die_tool "unknown argument: $1 (see --help)" ;;
  esac
done

case "$LIMIT" in ''|*[!0-9]*) die_tool "--limit must be a whole number" ;; esac
for u in awk sed grep wc find sort uniq cksum date mkdir cp tr; do
  command -v "$u" >/dev/null 2>&1 || die_tool "required utility missing: $u"
done

[ -n "$WS" ]  || WS="$(pr_workspace)"
[ -n "$MFD" ] || MFD="$(pr_master_files)"
[ -n "$PBD" ] || PBD="$MFD/playbooks"
[ -n "$INDEX" ] || INDEX="$PBD/README.md"
[ -n "$BACKUP_ROOT" ] || BACKUP_ROOT="$(pr_backup_root)"

# Character counting: OpenClaw measures in characters, not bytes. Use a UTF-8
# locale for wc -m when one exists; otherwise fall back to bytes and say so.
UTF8_LOCALE=""
for l in C.UTF-8 en_US.UTF-8 C.utf8 en_US.utf8; do
  if [ "$(printf '\303\251' | LC_ALL=$l wc -m 2>/dev/null | tr -d ' ')" = "1" ]; then UTF8_LOCALE="$l"; break; fi
done
count_chars() {
  if [ -n "$UTF8_LOCALE" ]; then LC_ALL=$UTF8_LOCALE wc -m < "$1" | tr -d ' '
  else wc -c < "$1" | tr -d ' '; fi
}

# ─────────────────────────────── --prove-moved ───────────────────────────────
if [ "$MODE" = "prove" ]; then
  [ -f "$OLD" ] || die_tool "OLD file not found: $OLD"
  [ -f "$NEW" ] || die_tool "NEW file not found: $NEW"
  [ -d "$PBD" ] || die_tool "playbooks folder not found: $PBD"
  PB_LIST="$(find "$PBD" -type f -name '*.md' 2>/dev/null)"
  # Normalize: every run of whitespace becomes one space; compare substrings.
  # shellcheck disable=SC2086
  RESULT="$(
    { printf '%s\n' "$PB_LIST" | while IFS= read -r f; do [ -n "$f" ] && cat "$f"; echo; done; } \
    | awk -v NEWF="$NEW" -v OLDF="$OLD" '
      function norm(s) { gsub(/[ \t\r\n]+/, " ", s); sub(/^ /, "", s); sub(/ $/, "", s); return s }
      function check(raw,   p) {
        p = norm(raw)
        if (p == "" || index(nw, p) > 0) return
        checked++
        if (index(pb, p) == 0) { missing++; print "UNPROVEN: " substr(p, 1, 160) }
      }
      { pb = pb " " $0 }
      END {
        pb = norm(pb)
        nw = ""; while ((getline line < NEWF) > 0) nw = nw " " line; close(NEWF); nw = norm(nw)
        para = ""; missing = 0; checked = 0
        # A paragraph is a run of non-blank lines; a markdown heading line is
        # always a paragraph of its own (headings usually stay behind as the
        # home of the new pointer, while the body moves).
        while (1) {
          r = (getline line < OLDF)
          heading = (r > 0 && line ~ /^#+[ \t]/)
          if (r > 0 && !heading && line !~ /^[ \t\r]*$/) { para = para " " line; continue }
          check(para); para = ""
          if (heading) { check(line); continue }
          if (r <= 0) break
        }
        print "SUMMARY: removed-or-changed paragraphs=" checked " unproven=" missing
        exit (missing > 0 ? 1 : 0)
      }'
  )"
  rc=$?
  printf '%s\n' "$RESULT"
  if [ "$rc" -eq 0 ]; then echo "PASS [$PROG]: every paragraph removed from $(basename "$NEW") exists in $PBD"; exit 0; fi
  echo "FINDINGS [$PROG]: restore the UNPROVEN paragraphs to the core file or copy them verbatim into the playbook's Moved-text archive, then re-run" >&2
  exit 1
fi

[ -d "$WS" ] || die_tool "workspace folder not found: $WS (pass --workspace)"

# ─────────────────────────────── --backup ────────────────────────────────────
if [ "$MODE" = "backup" ]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  DEST="$BACKUP_ROOT/pointer-references/$STAMP"
  mkdir -p "$DEST/core" || die_tool "cannot create backup folder $DEST"
  n=0
  for f in $CORE_FILES; do
    if [ -f "$WS/$f" ]; then cp -p "$WS/$f" "$DEST/core/$f" || die_tool "backup copy failed: $f"; n=$((n+1)); fi
  done
  if [ -d "$PBD" ]; then cp -Rp "$PBD" "$DEST/playbooks" || die_tool "backup copy of playbooks failed"; fi
  ( cd "$DEST" && find . -type f -exec cksum {} \; | sort -k3 ) > "$DEST/MANIFEST.txt" 2>/dev/null \
    || die_tool "could not write $DEST/MANIFEST.txt"
  echo "BACKUP [$PROG]: $n core file(s) and playbooks copied to $DEST"
  echo "$DEST"
  exit 0
fi

# ─────────────────────────────── audit ───────────────────────────────────────
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t pointeraudit)" || die_tool "mktemp failed"
trap 'rm -rf "$TMP"' EXIT
FIND="$TMP/findings"; INFO="$TMP/info"; : > "$FIND"; : > "$INFO"
finding() { printf -- '- %s\n' "$*" >> "$FIND"; }
info()    { printf -- '- %s\n' "$*" >> "$INFO"; }

HOME_ESC="$HOME"
expand_path() { # expand a leading ~ to $HOME
  case "$1" in "~/"*) printf '%s' "$HOME_ESC/${1#\~/}" ;; *) printf '%s' "$1" ;; esac
}
canon() { # canonical absolute path of an existing file
  local d b; d="$(dirname "$1")"; b="$(basename "$1")"
  ( cd "$d" 2>/dev/null && printf '%s/%s' "$(pwd -P)" "$b" )
}
PBD_CANON=""
[ -d "$PBD" ] && PBD_CANON="$(cd "$PBD" && pwd -P)"

# 1. Size report ------------------------------------------------------------
SIZES="$TMP/sizes"; : > "$SIZES"; TOTAL=0
for f in $CORE_FILES; do
  p="$WS/$f"
  if [ -f "$p" ]; then
    c="$(count_chars "$p")"; TOTAL=$((TOTAL + c))
    if [ "$c" -gt "$LIMIT" ]; then
      printf '| %s | %s | OVER by %s |\n' "$f" "$c" "$((c - LIMIT))" >> "$SIZES"
      finding "SIZE: $f is $c characters, over the $LIMIT target by $((c - LIMIT))"
    else
      printf '| %s | %s | ok |\n' "$f" "$c" >> "$SIZES"
    fi
  else
    printf '| %s | absent | - |\n' "$f" >> "$SIZES"
  fi
done
if [ -f "$WS/TOOLS.md" ] && grep -q '^## Tools' "$WS/AGENTS.md" 2>/dev/null; then
  info "TOOLS.md exists AND AGENTS.md has a '## Tools' section: on OpenClaw 2026.9 and later TOOLS.md is no longer injected and doctor merges it into AGENTS.md. Check the two do not say the same thing twice."
fi

# 2. Candidate blocks ---------------------------------------------------------
CAND="$TMP/candidates"; : > "$CAND"
for f in AGENTS.md TOOLS.md MEMORY.md; do
  p="$WS/$f"; [ -f "$p" ] || continue
  awk -v FN="$f" '
    function flush() {
      if (nchars > 0 && (sent >= 6 || nchars > 1000)) {
        tag = "situational?"
        if (managed) tag = "MANAGED by a skill installer: do not move by hand"
        else if (tolower(body) ~ /never|do not|don.t|must not|forbidden|safety|hard rule|non-negotiable|identity|priority: critical/) tag = "ALWAYS-ON? keep inline, shorten"
        printf("| %s | %d | %s | %d | %d | %s |\n", FN, start, title, nchars, sent, tag)
      }
      nchars = 0; sent = 0; body = ""
    }
    BEGIN { start = 1; title = "(top of file)"; managed = 0; mstart = 0 }
    /^<!-- BEGIN skill:/ { flush(); managed = 1; start = NR; title = $0; gsub(/\|/, "/", title); next }
    /^<!-- END skill:/   { flush(); managed = 0; start = NR + 1; title = "(after managed block)"; next }
    /^#{1,6} / { flush(); start = NR; title = $0; gsub(/\|/, "/", title); if (length(title) > 70) title = substr(title, 1, 67) "..."; next }
    {
      line = $0
      nchars += length(line) + 1
      body = body " " line
      tmp = line; n = gsub(/[.!?]([ \t]|$)/, "", tmp)
      if (n == 0 && line ~ /^[ \t]*([-*+]|[0-9]+\.)[ \t]/) n = 1
      sent += n
    }
    END { flush() }
  ' "$p" >> "$CAND"
done

# 3. Pointers -----------------------------------------------------------------
PTRS="$TMP/pointers"; : > "$PTRS"   # canonical targets of playbook pointers
for f in $CORE_FILES; do
  p="$WS/$f"; [ -f "$p" ] || continue
  # (a) unresolved placeholders
  grep -n -E '\[MASTER[-_]FILES[-_](FOLDER|DIR)\]|\{\{MASTER_FILES_(FOLDER|DIR)\}\}|<master-files>' "$p" 2>/dev/null \
    | while IFS= read -r hit; do
        finding "UNRESOLVED: $f line ${hit%%:*} names a master-files placeholder instead of a real path"
      done
  # (b) every master-files path must exist
  grep -n -o -E "(~/Downloads/openclaw-master-files|/data/\.openclaw/master-files|$MFD)/[^][:space:]\`'\"()<>,;|*]+" "$p" 2>/dev/null \
    | sort -u | while IFS= read -r hit; do
        ln="${hit%%:*}"; tok="${hit#*:}"; tok="${tok%.}"; tok="${tok%:}"
        path="$(expand_path "$tok")"
        if [ ! -e "$path" ]; then
          finding "BROKEN POINTER: $f line $ln -> $tok (not found)"
        fi
      done
  # (c) playbook pointers: collect targets, require an absolute path, a WHEN
  #     trigger, and at most two sentences
  grep -n -E "playbooks/[^][:space:]\`'\"()<>,;|*]+\.md" "$p" 2>/dev/null | while IFS= read -r hit; do
    ln="${hit%%:*}"; text="${hit#*:}"
    toks="$(printf '%s\n' "$text" | grep -o -E "(~/Downloads/openclaw-master-files|/data/\.openclaw/master-files|$MFD)/playbooks/[^][:space:]\`'\"()<>,;|*]+\.md")"
    if [ -z "$toks" ]; then
      printf '%s\n' "$text" | grep -q -E '\[MASTER|<master-files>|\{\{MASTER' \
        || finding "RELATIVE POINTER: $f line $ln names a playbook without the absolute master-files path"
    fi
    printf '%s\n' "$toks" | while IFS= read -r tok; do
      [ -n "$tok" ] || continue
      path="$(expand_path "$tok")"
      if [ -f "$path" ]; then canon "$path" >> "$PTRS"; echo >> "$PTRS"; fi
    done
    next_line="$(sed -n "$((ln + 1))p" "$p")"
    if ! printf '%s %s\n' "$text" "$next_line" | grep -qiE '(^|[^a-z])(when|whenever|if the user|if a user|anytime|any time)([^a-z]|$)'; then
      finding "POINTER WITHOUT WHEN: $f line $ln points to a playbook but names no trigger (add 'Read it whenever the user mentions ...')"
    fi
    nsent="$(printf '%s\n' "$text" | awk '{ t = $0; gsub(/[a-zA-Z0-9_~\/.-]+\.md/, "F", t); print gsub(/[.!?]([ \t]|$)/, "", t) }')"
    if [ "${nsent:-0}" -gt 2 ]; then
      finding "LONG POINTER: $f line $ln has $nsent sentences (a pointer is one line, at most two sentences)"
    fi
  done
done
sed -i.bak '/^$/d' "$PTRS" 2>/dev/null; rm -f "$PTRS.bak"

# 4-7. Playbooks, index, orphans, duplicates, hygiene ------------------------
PB_COUNT=0
IDX_T="$TMP/index-targets"; : > "$IDX_T"
if [ ! -d "$PBD" ]; then
  info "Playbooks folder $PBD does not exist yet (no playbooks to check). wire.sh creates it."
else
  if [ ! -f "$INDEX" ]; then
    finding "INDEX MISSING: $INDEX does not exist (every playbooks folder needs the master index)"
  else
    grep -o -E '\]\([^)]+\.md\)' "$INDEX" 2>/dev/null | sed 's/^](//; s/)$//' | while IFS= read -r t; do
      case "$t" in
        /*|"~/"*) path="$(expand_path "$t")" ;;
        *) path="$PBD/$t" ;;
      esac
      if [ -f "$path" ]; then canon "$path" >> "$IDX_T"; echo >> "$IDX_T"
      else finding "BROKEN INDEX ENTRY: $(basename "$INDEX") lists $t, which does not exist"; fi
    done
    sed -i.bak '/^$/d' "$IDX_T" 2>/dev/null; rm -f "$IDX_T.bak"
    sort "$IDX_T" | uniq -d | while IFS= read -r d; do
      finding "DUPLICATE INDEX ENTRY: ${d#"$PBD_CANON"/} is listed more than once"
    done
  fi
  INDEX_CANON=""; [ -f "$INDEX" ] && INDEX_CANON="$(canon "$INDEX")"
  SYS="$TMP/systems"; SLUG="$TMP/slugs"; SUMS="$TMP/sums"; : > "$SYS"; : > "$SLUG"; : > "$SUMS"
  find "$PBD" -type f -name '*.md' ! -path '*/.*' 2>/dev/null | sort > "$TMP/pblist"
  while IFS= read -r pb; do
    [ -n "$pb" ] || continue
    c="$(canon "$pb")"
    [ "$c" = "$INDEX_CANON" ] && continue
    PB_COUNT=$((PB_COUNT + 1))
    rel="${c#"$PBD_CANON"/}"
    grep -qxF "$c" "$IDX_T" || finding "ORPHAN (not indexed): $rel is not listed in $(basename "$INDEX")"
    grep -qxF "$c" "$PTRS"  || finding "ORPHAN (no pointer): no core file points to $rel"
    sysname="$(grep -m1 -E '^\**System:?\**:?[[:space:]]' "$pb" 2>/dev/null | sed -E 's/^\**System:?\**:?[[:space:]]*//')"
    if [ -z "$sysname" ]; then finding "HYGIENE: $rel has no 'System:' line"
    else printf '%s\t%s\n' "$(printf '%s' "$sysname" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9')" "$rel" >> "$SYS"; fi
    lv="$(grep -m1 -E '^\**Last verified:?\**:?[[:space:]]*[0-9]{4}-[0-9]{2}-[0-9]{2}' "$pb" 2>/dev/null)"
    [ -n "$lv" ] || finding "HYGIENE: $rel has no 'Last verified: YYYY-MM-DD' line"
    grep -q -E '^#{1,3} What changed' "$pb" 2>/dev/null || finding "HYGIENE: $rel has no '## What changed' section"
    base="$(basename "$rel" .md | tr 'A-Z' 'a-z' \
      | sed -E 's/(^|[-_ ])(playbook|rules|guide|notes|reference|sop|v[0-9]+|[0-9]{4}-?[0-9]{2}-?[0-9]{2}|new|old|copy|final)([-_ ]|$)/\1\3/g' \
      | tr -cd 'a-z0-9')"
    printf '%s\t%s\n' "$base" "$rel" >> "$SLUG"
    printf '%s\t%s\n' "$(cksum < "$pb" | awk '{print $1"-"$2}')" "$rel" >> "$SUMS"
  done < "$TMP/pblist"
  for kind in SYS SLUG SUMS; do
    eval "fl=\$$kind"
    case "$kind" in SYS) label="same System: line";; SLUG) label="same file name once normalized";; SUMS) label="identical content";; esac
    cut -f1 "$fl" | sort | uniq -d | while IFS= read -r key; do
      [ -n "$key" ] || continue
      files="$(awk -F'\t' -v k="$key" '$1 == k { printf("%s%s", sep, $2); sep = ", " }' "$fl")"
      finding "DUPLICATE PLAYBOOKS ($label): $files (one system = one playbook; merge them)"
    done
  done
fi

# ─────────────────────────────── report ──────────────────────────────────────
NF="$(grep -c '^- ' "$FIND" 2>/dev/null || true)"; NF="${NF:-0}"
NC="$(grep -c '^|' "$CAND" 2>/dev/null || true)"; NC="${NC:-0}"
VERDICT="PASS"; [ "$NF" -gt 0 ] && VERDICT="FINDINGS"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
build_report() {
  echo "# Pointer References audit"
  echo
  echo "Run: $NOW (Coordinated Universal Time). Verdict: **$VERDICT** ($NF finding(s), $NC candidate block(s), $PB_COUNT playbook(s))."
  echo "Workspace: $WS"
  echo "Playbooks: $PBD (index: $INDEX)"
  [ -n "$UTF8_LOCALE" ] || echo "Note: no UTF-8 locale found, sizes below are bytes, not characters."
  echo
  echo "## Size report (target: $LIMIT characters per core file)"
  echo
  echo "| File | Characters | Status |"
  echo "| --- | --- | --- |"
  cat "$SIZES"
  echo
  echo "Total across core files: $TOTAL characters."
  echo
  echo "## Findings"
  echo
  if [ "$NF" -gt 0 ]; then cat "$FIND"; else echo "None."; fi
  echo
  echo "## Candidate blocks (agent judgment: move situational knowledge, keep always-on rules inline)"
  echo
  if [ "$NC" -gt 0 ]; then
    echo "| File | Line | Heading | Characters | Sentences | Hint |"
    echo "| --- | --- | --- | --- | --- | --- |"
    cat "$CAND"
  else
    echo "None."
  fi
  if [ -s "$INFO" ]; then echo; echo "## Notes"; echo; cat "$INFO"; fi
}

if [ "$DRY" -eq 1 ]; then
  build_report
  echo
  echo "(dry run: no report file written)"
else
  [ -n "$REPORT" ] || REPORT="$MFD/70-pointer-references/reports/pointer-audit-$(date -u +%Y%m%dT%H%M%SZ).md"
  mkdir -p "$(dirname "$REPORT")" 2>/dev/null || die_tool "cannot create report folder for $REPORT"
  build_report > "$REPORT" || die_tool "cannot write report $REPORT"
  echo "Report: $REPORT"
fi
echo "$VERDICT [$PROG]: $NF finding(s), $NC candidate block(s), $PB_COUNT playbook(s), $TOTAL total core characters"
[ "$NF" -gt 0 ] && exit 1
exit 0
