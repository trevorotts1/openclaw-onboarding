#!/usr/bin/env bash
# Skill 85 — Android SMS System — Static QC
#
# Verifies the packaged skill against its offline documentation set:
#   SKILL.md exists and its frontmatter name is android-sms-system
#   docs folder exists, 00-INDEX.md exists, 156 articles, _labels.json has 156 entries
#   android-sms-system-full.md carries 156 MCS doc entries
#   local image links are counted (INFO only — assets are intentionally absent)
#   any referenced image file that exists but is zero bytes fails
#
# Prints PASS or FAIL per check. Exits 1 if any check fails.
# Dependencies: bash, coreutils, python3 -I (JSON count only).
#
# Optional overrides:
#   ASMS_DOCS_DIR   absolute path to the offline docs set
#   ASMS_FULL_MD    absolute path to android-sms-system-full.md
#
# Usage: ./qc-android-sms-system.sh

set -u
set -o pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_MD="$SKILL_DIR/SKILL.md"
FULL_MD="${ASMS_FULL_MD:-$SKILL_DIR/android-sms-system-full.md}"

if [ -t 1 ]; then R=$'\033[31m'; G=$'\033[32m'; N=$'\033[0m'; else R=; G=; N=; fi
PASS=0
FAIL=0
pass() { printf '  %sPASS%s — %s\n' "$G" "$N" "$1"; PASS=$((PASS + 1)); }
fail() { printf '  %sFAIL%s — %s\n' "$R" "$N" "$1"; FAIL=$((FAIL + 1)); }
info() { printf '  INFO — %s\n' "$1"; }

# ── resolve the docs folder ───────────────────────────────────────────────────
DOCS_DIR="${ASMS_DOCS_DIR:-}"
[ -n "$DOCS_DIR" ] && [ ! -d "$DOCS_DIR" ] && DOCS_DIR=""
if [ -z "$DOCS_DIR" ]; then
  for d in "$SKILL_DIR/docs" \
           "$SKILL_DIR/85-android-sms-system-docs" \
           "$HOME/Downloads/openclaw-master-files/mycrmsim"; do
    if [ -d "$d" ]; then DOCS_DIR="$d"; break; fi
  done
fi

echo ""
echo "═══ Skill 85 — Android SMS System — Static QC ═══"
echo "  skill   : $SKILL_DIR"
echo "  docs    : ${DOCS_DIR:-<not found>}"
echo "  full md : $FULL_MD"
echo ""

# ── 1. SKILL.md exists ────────────────────────────────────────────────────────
if [ -f "$SKILL_MD" ]; then
  pass "SKILL.md exists ($SKILL_MD)"
else
  fail "SKILL.md missing at $SKILL_MD"
fi

# ── 2. SKILL.md frontmatter declares name: android-sms-system ────────────────
skill_name=""
if [ -f "$SKILL_MD" ]; then
  skill_name=$(tr -d '\r' < "$SKILL_MD" | awk '
    NR == 1 && $0 !~ /^---[ \t]*$/ { exit }
    NR == 1                        { infm = 1; next }
    infm && $0 ~ /^---[ \t]*$/      { exit }
    infm && $0 ~ /^name[ \t]*:/     { sub(/^name[ \t]*:[ \t]*/, ""); print; exit }
  ' | sed -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
fi
if [ "$skill_name" = "android-sms-system" ]; then
  pass "SKILL.md frontmatter name is android-sms-system"
else
  fail "SKILL.md frontmatter name is '${skill_name:-<missing>}', expected 'android-sms-system'"
fi

# ── 3. docs folder exists ────────────────────────────────────────────────────
if [ -n "$DOCS_DIR" ] && [ -d "$DOCS_DIR" ]; then
  pass "docs folder exists ($DOCS_DIR)"
else
  fail "docs folder not found (set ASMS_DOCS_DIR to the offline documentation set)"
fi

# ── 4. 00-INDEX.md exists ────────────────────────────────────────────────────
if [ -n "$DOCS_DIR" ] && [ -f "$DOCS_DIR/00-INDEX.md" ]; then
  pass "docs 00-INDEX.md exists"
else
  fail "docs 00-INDEX.md missing under ${DOCS_DIR:-<not found>}"
fi

# ── 5. articles count is 156 ─────────────────────────────────────────────────
articles=""
if [ -n "$DOCS_DIR" ] && [ -d "$DOCS_DIR/articles" ]; then
  articles=$(find "$DOCS_DIR/articles" -type f -name '*.md' | wc -l | tr -d ' ')
elif [ -n "$DOCS_DIR" ]; then
  articles=0
fi
if [ "$articles" = "156" ]; then
  pass "articles/ holds 156 markdown articles"
else
  fail "articles/ holds ${articles:-<missing docs>} markdown articles, expected 156"
fi

# ── 6. _labels.json has 156 entries ─────────────────────────────────────────
labels_n=""
if [ -z "$DOCS_DIR" ] || [ ! -f "$DOCS_DIR/_labels.json" ]; then
  fail "_labels.json missing under ${DOCS_DIR:-<not found>}"
elif ! command -v python3 >/dev/null 2>&1; then
  fail "_labels.json entry count not checkable — python3 not available"
else
  labels_n=$(python3 -I -c 'import json,sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print("ERR:%s" % exc)
else:
    print(len(d) if isinstance(d, (list, dict)) else "ERR:not-a-collection")
' "$DOCS_DIR/_labels.json" 2>&1 | tr -d '\r')
  if [ "$labels_n" = "156" ]; then
    pass "_labels.json holds 156 entries"
  else
    fail "_labels.json holds ${labels_n:-<unreadable>} entries, expected 156"
  fi
fi

# ── 7. full guide carries 156 MCS doc entries ────────────────────────────────
if [ ! -f "$FULL_MD" ]; then
  fail "android-sms-system-full.md missing at $FULL_MD"
else
  mcs_ids=$(grep -oE 'MCS-[0-9]{3}' "$FULL_MD" | sort -u | wc -l | tr -d ' ')
  mcs_lines=$(grep -cE 'MCS-[0-9]{3}' "$FULL_MD" | tr -d ' ')
  if [ "$mcs_ids" = "156" ] && [ "${mcs_lines:-0}" -ge 156 ]; then
    pass "android-sms-system-full.md carries 156 MCS doc entries (156 unique ids, $mcs_lines MCS lines)"
  else
    fail "android-sms-system-full.md has $mcs_ids unique MCS ids and $mcs_lines MCS lines, expected 156/156"
  fi
fi

# ── 8. local image links: count them, fail only on zero-byte files ───────────
# The image/GIF assets are intentionally absent from the doc set, so a missing
# file is reported as INFO and never fails. A file that exists but is empty is
# still a real defect.
img_total=0
img_missing=0
img_empty=0
img_empty_list=""
if [ -n "$DOCS_DIR" ] && [ -d "$DOCS_DIR/articles" ]; then
  while IFS= read -r -d '' f; do
    dname=$(dirname "$f")
    while IFS= read -r link; do
      [ -z "$link" ] && continue
      case "$link" in
        http://* | https://* | //* | data:* | mailto:* | '#'*) continue ;;
      esac
      target=${link%%#*}
      target=${target%%\?*}
      target=${target#<}
      target=${target%>}
      [ -z "$target" ] && continue
      img_total=$((img_total + 1))
      if [ ! -e "$dname/$target" ]; then
        img_missing=$((img_missing + 1))
      elif [ ! -s "$dname/$target" ]; then
        img_empty=$((img_empty + 1))
        if [ ${#img_empty_list} -lt 2000 ]; then
          img_empty_list="$img_empty_list
      zero-byte: ${f#"$DOCS_DIR"/} -> $link"
        fi
      fi
    done < <(grep -oE '!\[[^]]*\]\([^)[:space:]]+' "$f" 2>/dev/null | sed -E 's/^!\[[^]]*\]\(//')
  done < <(find "$DOCS_DIR/articles" -type f -name '*.md' -print0)
fi
if [ "$img_total" -eq 0 ]; then
  fail "no local image links found in the articles"
else
  info "SKIP — $img_total local image references counted; $img_missing have no file on disk (assets intentionally removed)"
  if [ "$img_empty" -gt 0 ]; then
    fail "$img_empty of $img_total local image links point at zero-byte files$img_empty_list"
  else
    pass "local image links checked ($img_total references, 0 zero-byte files)"
  fi
fi

# ── result ───────────────────────────────────────────────────────────────────
echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
if [ "$FAIL" -gt 0 ]; then
  printf '%sSkill 85 QC FAILED%s\n' "$R" "$N"
  exit 1
fi
printf '%sSkill 85 QC PASS%s\n' "$G" "$N"
exit 0
